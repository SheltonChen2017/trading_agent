# Allocation-policy QuantConnect family — implementation plan

Status: **COMPLETE AND CLOSED (A-003, 2026-08-19).** Prepared
2026-08-18; implemented as APQ-1..3, executed once as R-029, and
observed once as A-003. All three preregistered comparisons were null
at the frozen 0.05/3 gate; no variant or rerun is authorized.

This file is the authority for *how* to implement the family. Frozen
weights, window, and gates live in
`docs/Archive/Research/ALLOCATION_POLICY_2026-08-18_PREREGISTRATION.md` and must
not be changed in this document after a result exists.

`docs/Archive/Plans/ACTION_PLAN_2026-08-02.md` remains the sequencing authority and
records this family as closed. The instructions below remain the
historical frozen contract; they do not authorize another run.

This plan does **not** authorize a trade, a registry promotion, an Alpaca
order, or a reopening of the closed cross-sectional alpha program (A-002).
QuantConnect is historical comparison only.

## Why this exists

Stage 0 and Stage 1 closed US stock-selection on this universe with a
null. The useful remaining QC question is **portfolio policy under the
August 2026 tape** (long yields ~5.3%, oil elevated, equities near
records): bills + a modest equity sleeve, less equity duration, a capped
energy satellite — versus 100% SPY — after costs.

QC's job is one fair, costed, same-date comparison. It is not a place to
implement options insurance or to live-trade the mix.

## Constraints (do not weaken)

- One algorithm, **one** cloud backtest, four policies in one log.
- Review + counter-review of APQ-1/APQ-2/APQ-3 **before** any QC launch.
- Launch with the existing driver conventions: clean commit, evidence
  JSON under `artifacts/`, serial wait, log SHA-256, append-only ledger.
- First ledger status is **UNANALYSED**. One analyser pass. Then VALID.
- Stop. No variant after seeing numbers.
- `require_clean=True` and log-fetch `query=""` stay on. Do not copy
  `alpha_battery_monthly.py` or Stage 1 score machinery.

## Milestones

Implement **one milestone per branch**, stop for review, do not start the
next until the owner says so.

### APQ-0 — Owner adoption (no code)

**Done when:** this plan and the preregistration are on a pushed branch
and the action plan either schedules APQ-1 or explicitly defers it.

No LEAN, no tests, no QC.

### APQ-1 — LEAN algorithm + local tests (no QC)

**New file:** `research/lean/allocation_policy.py`

Behavior:

1. `add_equity` SPY, BIL, XLP, XLV, XLE at daily resolution, adjusted
   normalization. `set_cash` is only a buffer; the bill sleeve is **BIL**,
   never Lean cash interest.
2. On the last session of each calendar month, for each policy P0–P3,
   compute one-way drift turnover from the prior month's holdings to the
   frozen weights, then equal-weight? **No** — use the preregistered
   percent weights on that session's adjusted close.
3. Hold until the next month-end close. Monthly return is the
   weighted total return of the names that priced. If any targeted name
   is unpriceable, **do not substitute**; that policy-date is refused
   (empty/unavailable path) and must not silently drop only one policy
   (all four policies share the date set — if one name is missing, skip
   the date for everyone or refuse the run; **refuse the date for all
   four**, keep the series aligned).
4. Emit a completeness header then rows:

   ```text
   POLICIES|P0|P1|P2|P3
   DATES|<n>
   PROW|<YYYYMM>|<policy>|<ret>|<turnover>|<priced>|<targeted>
   ```

   Empty turnover field = declared unavailability (analyser charges 1.0).
   `INCOMPLETE` + no rows if any policy has `< 24` months or dates differ
   across policies.

5. No `ACTIVE_UNIVERSE`. No universe screen. Start/end dates match the
   preregistration (start 2022-01-01; end = last complete session ≤
   2026-08-18, as a named constant the tests can read).

**Do not** add this file to `scripts/run_qc_stage0.py` `FAMILIES` in
APQ-1 (that is APQ-3). Keep the algorithm launchable only after review.

**Tests** (`tests/test_allocation_policy.py`), stub-load like Stage 1
hardening tests:

- Frozen weights sum to 1.0 per policy; P3 XLE is exactly 0.10.
- One missing close on a rebalance date drops **all four** policies for
  that date (alignment).
- Duplicate `ACTIVE_UNIVERSE` is N/A; assert the source contains **zero**
  `ACTIVE_UNIVERSE` assignments so the Stage 0 retargeter cannot silently
  rewrite this file.
- Emitter: empty turnover round-trips; `DATES` matches unique months;
  four policies every date.
- Vacuous-pass guard: at least one assertion on `len(rows) == 4 * n_months`.

**Definition of done:** tests green; `compileall` of the new module;
no QC; no analyser yet.

### APQ-2 — Analyser + tests (no QC)

**New file:** `scripts/analyse_qc_allocation_policy.py`

Must:

- `sys.path.insert` bootstrap (same as the battery analyser; do not
  repeat S1R-001).
- Parse `PROW` only; refuse unknown policies, duplicate dates, non-finite
  present turnover, `priced > targeted`, truncated `DATES`.
- **`priced`/`targeted` semantics (APQ1-003, counter-review note
  2026-08-19):** both fields count the POLICY'S OWN members (P0 emits
  `1|1`), while the refusal gate is UNION-wide across all five tickers.
  `priced == targeted` therefore holds on every emitted row by
  construction; the analyser must treat these as the policy's member
  count, never as "names that priced in the union", and may refuse
  `priced != targeted` as a corruption signal.
- Join P1/P2/P3 to P0 on **identical** dates; refuse if any date is
  missing from P0.
- `performance()` from the reviewed local battery helper; costs via
  `fillna(1.0)` on turnover, 0/5/10/25 bps.
- Write JSON: per-policy gross/net block **and** a `versus_p0` block
  (excess mean, maxDD, Sharpe difference — descriptive). Optional
  bootstrap excess-mean p-values only if the JSON schema includes the
  frozen 0.05/3 gate and both stage and "this family only" labels.
  **Do not call** `analyse()` from the alpha battery (that computes IC /
  long-short).

**Tests:**

- Magnitude pin: one empty turnover month → net 10 bps vs gross delta
  equals `1.0 * 2 * 10 / 10000 / n` (S0R-008 class).
- Present `nan` turnover token → refuse.
- Misaligned policy dates → refuse.
- Script-mode import of the analyser module succeeds (bootstrap).

**Decision fixed at APQ-2 review (counter-review note, 2026-08-18):**
whether the optional excess-mean test family is reported AT ALL is
decided by the reviewed APQ-2 JSON schema — before any run exists —
never after seeing the descriptive table. Leaving it open past APQ-2
would create a peek-then-decide channel.

**Definition of done:** tests green; no QC.

### APQ-3 — Launch driver hook + tests (no QC)

Extend `scripts/run_qc_stage0.py` **without** breaking Stage 0/1:

- New family key `allocation` → label `ALLOCATION_POLICY`, path
  `research/lean/allocation_policy.py`.
- `_retarget_universe` must **not** run for this family (there is no
  `ACTIVE_UNIVERSE`). Launch path: if family is `allocation`, upload the
  file bytes unchanged (still hash them; still `require_clean=True`).
- `--universe` is awkward. Prefer: `--family allocation` does not
  require `--universe`; project name
  `{n}. ALLOCATION_POLICY - {YYYYMMDD}`.
- Existing `test_every_family_file_retargets_each_universe_by_one_line`
  will break if `allocation` is in `FAMILIES` and has no
  `ACTIVE_UNIVERSE`. **Fix the test** to skip families in a
  `UNIVERSE_FREE_FAMILIES` frozenset, and add
  `test_allocation_family_is_not_universe_retargeted`.

Reverse mutations (must go red):

1. Put `allocation` through `_retarget_universe` anyway → launch refuses
   or the new skip-test fails.
2. Drop `require_clean=True` → existing spy test still red (do not
   weaken it).

**Definition of done:** full `tests/test_qc_stage0_runner.py` + new
allocation tests green. Still no QC.

### APQ-4 — Review, then one cloud run

1. Independent review of APQ-1..3 (commit-by-commit). Counter-review.
2. Owner go for **one** backtest (node pool: one at a time).
3. Launch via the reviewed driver; append **R-nnn UNANALYSED** to
   `docs/research/alpha-result.md` with full identity (treat as allocation-policy,
   not an alpha cell). Run-level look +1.
4. Structural parser round-trip on the raw log. If incomplete, ledger
   REFUSED/INCOMPLETE; do not "fix and quietly rerun" on the same
   R-number.

**Definition of done:** UNANALYSED entry with hashes; log round-trips;
no statistic.

### APQ-5 — One analyser pass, then stop

**`mean_turnover` semantics (APQ2-001, counter-review note 2026-08-19):**
the descriptive `mean_turnover` averages AVAILABLE months only (pandas
skipna); declared-unavailable months are charged 1.0 in the NET blocks
but excluded from this mean, so it understates costed activity whenever
the empty-field path fired. Read it beside
`unavailable_turnover_periods`, never alone. Substituting the charged
series' mean is a schema change for a later, separately reviewed
version — not a post-hoc edit.

1. `python -m scripts.analyse_qc_allocation_policy` once, full identity.
2. Append **A-nnn** (or a named allocation observation). Upgrade that
   run UNANALYSED → VALID in the **same** commit.
3. Interpret vs P0 on the confirmatory window only. Do not mine P3.
4. Stop. Paper/live of these weights is a **separate** owner decision
   on the Alpaca/REBAL stack, not a QC follow-up.

**Definition of done:** one observation in the ledger; family closed.

## Files (expected)

| Path | Milestone |
|---|---|
| `docs/Archive/Research/ALLOCATION_POLICY_2026-08-18_PREREGISTRATION.md` | APQ-0 (this branch) |
| `docs/Archive/Plans/ALLOCATION_POLICY_QC_PLAN.md` | APQ-0 (this document) |
| `research/lean/allocation_policy.py` | APQ-1 |
| `tests/test_allocation_policy.py` | APQ-1 |
| `scripts/analyse_qc_allocation_policy.py` | APQ-2 |
| `tests/test_allocation_policy_analyser.py` | APQ-2 |
| `scripts/run_qc_stage0.py` | APQ-3 |
| `tests/test_qc_stage0_runner.py` | APQ-3 |
| `docs/research/alpha-result.md` | APQ-4, APQ-5 only |

## Explicitly out of scope

- Options / vol overlays (idea 5 is P1 vs P0, smaller equity weight)
- Levered short TLT, SH, sector rotation signals
- Universe A/B/C or PIT factors
- Changing REBAL-1 sleeve targets to match P1/P2/P3
- Deploying to `paper-epoch-005`
- Folding this into SHW1 overlay work
- A 2012–2024 headline backtest

## Validation for a completed code milestone (APQ-1..3)

```text
python -m pytest -q tests/test_allocation_policy.py tests/test_allocation_policy_analyser.py tests/test_qc_stage0_runner.py
python -m compileall -q research/lean/allocation_policy.py scripts/analyse_qc_allocation_policy.py scripts/run_qc_stage0.py
git diff --check
```

Full suite before calling APQ-3 done. No QC from the implementation branch.
