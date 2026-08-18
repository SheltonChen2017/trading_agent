# Independent review: S0R hardening round and Stage 0 closure records

Status: **accepted**. Prepared: 2026-08-18. Reviewer: Claude (Fable 5),
independent session — did not author the range; every claim below was
re-verified against the tree by reading source and executing tests,
probes, and reverse mutations in this session.

Per the review instructions, the frozen analysers were **not** run on
the nine logs in `artifacts/qc_stage0_20260817` and **no new statistic
was computed from them**. The single authorized analyser pass remains
A-001. All executions below used synthetic fixtures, crafted throwaway
logs, or the test suite.

## 1. Snapshot

| Item | Value |
|---|---|
| Requested range | `de1beac..fba1c0b` (11 commits) |
| Base | `de1beac16930690cda0f23dbe6f584e99600ac66` (head accepted by the Cursor/Grok 2026-08-18 review) |
| Review head | `fba1c0bc163e5bbadd6dde4c3f0349e4a7c09d62` |
| `origin/main` at review start | `a2fec997939a6a01e8c3e7834dbc7dcfe00f1c6a` (merge of PR #253) |
| Tree identity | `fba1c0b^{tree}` == `a2fec99^{tree}` == `63ff84119baf7eed14b0b7eb90dae0006e05bd64` — validation on the current main checkout validates the review head's exact tree |
| Review branch | `user/claude/review-s0r-hardening-20260818` from `a2fec99` |
| Worktree at start | clean |

Governing documents read in full: `docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md`,
`docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` (Cursor/Grok,
defines S0R-001..008), `docs/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COUNTERREVIEW.md`.

## 2. Verdict

**All eleven commits accepted.** The primary commit `602dc0b` genuinely
closes S0R-001/002/003/004/005/008: every claimed fix was confirmed in
source, every new regression test went red under the exact reverse
mutation that reinstates the original defect (eight mutations executed
in this session, all red, all restored), and none of the new tests can
pass vacuously. The deliberate settle-side non-change is agreed correct
(section 6). The record commits contain no sneaked statistic, the VALID
upgrade demonstrably preceded the analyser outputs, A-001's arithmetic
and code-identity claims verify, and all five owner merges are clean
fast-merges of their second parents.

**`602dc0b` clears the code gate in front of a future Stage 1 launch.**
This acceptance does NOT itself authorize Stage 1 — that remains a
separate owner decision, which per the standing records should weigh
Stage 1's 24-cell family against the A-001 nulls.

No P0. No P1. No P2. Two P3 observations, both closed without code
change (section 7).

## 3. Per-commit dispositions

Order is `git log --reverse --oneline de1beac..fba1c0b`.

| Commit | Disposition | Verification |
|---|---|---|
| `ff3c45c` Merge PR #246 | **Accepted.** No issue found. | Merge tree `50afe55…` == second parent `e2ed7eb`'s tree. No hidden conflict resolution. Second parent is inside the previously accepted `81db126..de1beac` range. |
| `a9d253b` Merge PR #247 | **Accepted.** No issue found. | Merge tree `cfcb847…` == second parent `075e982`'s tree. Same as above. |
| `28e4c02` Merge PR #248 | **Accepted.** No issue found. | Merge tree `209b18a…` == second parent `32998e5`'s tree. Same as above. |
| `c9e7a69` Merge PR #249 | **Accepted.** No issue found. | Merge tree `d11de4d…` == second parent `de1beac`'s tree. This is the merge that resolved S0R-006 (the deferral note reached main). |
| `5e4b724` Record review + counter-review | **Accepted.** No issue found. | Adds the two review documents plus handoff/action-plan updates; document content matches what it claims to record. My dispositions on the two contested counter-review classifications are in section 6 — I **agree** with both, and verified S0R-003's split by executing the pre-fix parsers. |
| `c066b1e` Merge PR #250 | **Accepted.** No issue found. | Merge tree `9823c52…` == second parent `5e4b724`'s tree. |
| `2be903f` Nine runs PENDING_REVIEW → VALID | **Accepted.** No issue found. | Diff is exactly nine Validity-row swaps in `docs/alpha-result.md`; grep of the full diff finds no Sharpe/IC/p-value/CAGR/net statistic. Committed 11:02:17 −0700; the three machine-local analyser outputs carry mtime 11:03 and A-001 (11:09:02) records them — the upgrade preceded the outputs. Analyser code at `2be903f` is byte-identical to reviewed head `de1beac` (`git diff --name-only de1beac 2be903f` lists five docs only), confirming A-001's code-identity row. |
| `8c9fdc8` Record A-001 | **Accepted.** No issue found. | Internal arithmetic verified without recomputing anything from logs: 45 spec-universe cells (30 monthly + 15 short) × 4 hypotheses = 180; gate 0.05/180 = 2.7778e-4; one insufficient cell (MULTI_ALPHA_COMPOSITE/A_large, 23 < 24, required/observed/sufficiency all stated) removes 4 hypotheses → 44 IC + 44 long-short + 88 long-only = 176 defined; 6/88 long-only = 2 LO10 + 4 LO20, matching the six named cells; short-battery 0/60 is a consistent restatement of the 15 short cells' four hypotheses. The market-beta caveat is stated in the same entry as the result, including that the equal-weight benchmarks would pass the same gross-vs-zero test. The recorded output hashes match the three machine-local JSONs exactly (re-hashed this session). The S0R-007 closure is a clarifying amendment in a NEW entry with R-022 unedited — correct under the append-only rule. |
| `602dc0b` S0R hardening | **Accepted.** No issue found; two P3 observations closed without change (section 7). | Full claim-by-claim and mutation verification in sections 4–5. |
| `c0ec727` Hardening-round record + env note | **Accepted.** No issue found. | Handoff section 7aa matches what I independently verified (fix inventory, mutation list, deliberate non-change rationale). The machine-local observation (streamlit 1.52.2 vs pinned 1.60.0, 260-char wheel path, LongPathsEnabled=0) is recorded as environment, not code; 4,232/14 is attributed to it with the base-commit reproduction stated. |
| `fba1c0b` Fully green validation record | **Accepted.** No issue found. | Records the same-day resolution (LongPathsEnabled=1, streamlit 1.60.0 reinstalls, 4,246/0/25) while RETAINING the original observation paragraph. This session confirmed streamlit 1.60.0 is installed and reproduced the full-suite result on the identical tree (section 8). |

## 4. Primary commit `602dc0b` — claim-by-claim verification

**S0R-001 (replications bind) — CLOSED, verified.**
`research/lean/alpha_stage1_replications.py:449-455`: the
`if any(value is None for value in turns): continue` gate is gone; the
bind updates `previous_weights`/`previous_entries` unconditionally and
stores the per-construction `turns` (None allowed) on the cohort. The
emitter (`on_end_of_algorithm`) writes `""` for a None turnover via the
`_turn` helper and emits a per-spec `SPECMETA|spec|median_names=…|periods=…`
inventory. The port is **faithful to `alpha_battery_monthly.py`'s
emitter**: the `_turn` helper, the cell format, and the SPECMETA line
are structurally identical (side-by-side source comparison, monthly
lines 796-822 vs replications lines 626-651). The SPECMETA inventory is
**load-bearing, not decorative**: I generated a stage1 log through the
real emitter, stripped the SPECMETA lines, and `merge_logs` refused it
with `TruncatedLog: 1 ROW lines do not contain every declared spec and
no complete SPECMETA inventory declares the per-spec counts` — exactly
the R-007 class the commit claims to prevent. With SPECMETA present the
same ragged log round-trips (test
`test_replications_emitter_declares_unavailability_and_raggedness`,
which drives the REAL parser end to end).

**S0R-002 (stage1 benchmark + analyser) — CLOSED, verified against the
post-39b3b89 `universe_benchmark.py` contract.**
`research/lean/alpha_stage1_benchmark.py`: `_enter` collects
`prior_outcomes` over priceable prior names only (line 173-174
condition inverted from the old early-`return`) and never returns after
that point — `_drift_turnover` returns None for an unpriceable prior
book and the bind proceeds (lines 182-190). `_settle_due` emits at
`len(outcomes) >= MIN_NAMES` with BOTH `len(outcomes)` (priced) and
`len(cohort["entry"])` (entered) (lines 214-221). `on_end_of_algorithm`
emits the five-field BROW with the empty-string path for None turnover
(lines 239-244). All three match `universe_benchmark.py`'s
`_bind_staged_entry`/`_settle`/`on_end_of_algorithm` post-39b3b89; the
structural difference (overlapping 21-session cohorts vs one pending
cohort) is inherent to Stage 1's cadence, not a contract divergence.
`scripts/analyse_qc_alpha_stage1.py:125-126` charges
`pd.to_numeric(...).fillna(1.0)` and the report block discloses
`unavailable_turnover_periods` and `underfilled_months`;
`mean_turnover` is the mean of PRESENT turnovers only (None when all
are unavailable) so the charge cannot launder the disclosure.

**S0R-003 (parsers refuse present non-finite tokens) — CLOSED, verified
by execution.** `_optional_finite` in
`scripts/analyse_qc_alpha_battery.py:72-85` refuses a present
non-finite token with `InvalidLog` before the frame-level
dropna-then-finite check can relabel it; it is applied to `ic`,
`turnover_ls`, `turnover_l10`, `turnover_l20`.
`scripts/analyse_qc_benchmark.py:52-54` adds the equivalent guard.
Executed evidence:

- Current tree: a crafted `nan` turnover ROW raises
  `InvalidLog: non-finite turnover_ls`; a crafted `nan` ic raises
  `InvalidLog: non-finite ic`; a crafted `nan` BROW turnover raises
  `SystemExit: invalid benchmark turnover`
  (`test_parsers_refuse_present_nonfinite_turnover_or_ic_tokens`, run
  green, and mutation-verified below).
- Pre-fix parsers (extracted from `8c9fdc8`), executed on the same
  crafted logs: `nan` was **ACCEPTED** into the declared-unavailability
  channel by both parsers (stored `turnover_ls=nan` / `turnover=nan`);
  `inf` was **REFUSED** by both. This reproduces the original defect
  red and directly confirms the counter-review's nan/inf split.
- Empty fields still parse as declared unavailability: the hardening
  emitter tests round-trip `""` → `pd.isna` through both real parsers.
- Packed v1 compatibility intact:
  `test_v1_layout_keeps_65535_as_a_real_turnover_value` passes on the
  head tree (65535 → 6.5535 in layout 1; sentinel reserved to layout 2
  only, parser lines 206-211).

**S0R-004 (universes runner heals the book) — CLOSED, verified.**
`scripts/run_alpha_universes_20260816.py:200-215`: the month's return is
recorded, turnover is recorded only when `drifted is not None`, and
`previous`/`previous_outcomes` are updated unconditionally. A month
omitted from the turnover index is charged 1.0 downstream:
`net_of_costs` (`scripts/run_alpha_battery_20260815.py:348-350`) does
`turnover.reindex(gross.index).fillna(1.0)`. Matches the reviewed
`long_short_returns` contract. Reverse mutation red (below).

**S0R-005 (monthly docstring) — CLOSED, verified.** The
`_rebalance_turnover` docstring in `alpha_battery_monthly.py:519-527`
now teaches the never-gate contract (None ⇒ declared-unavailable month,
book replaced, analyser charges 1.0) and no longer cites the
then-defective Stage 1 files as its exemplar. Docstring-only; no
behavior change in that file (diff inspected).

**S0R-008 (charge-magnitude pins) — CLOSED, verified by mutation.**
`test_alpha_analyser_charges_full_turnover_for_unavailable_months`
(battery) and `test_stage1_analyser_charges_full_turnover_and_discloses`
(stage1) both pin the exact net-vs-gross `mean_period_return` delta
`1.0 * 2.0 * 10.0 / 10_000.0 / 13` attributable to the single
unavailable month, with a zero-delta control on the spec with no
unavailable months. Both went red under `fillna(1.0)→fillna(0.0)`
(below) — the exact mutation the counter-review showed previously
survived all 57 alpha-analyser tests.

## 5. Mutation re-verification (all executed this session)

Each mutation: defect reinstated by editing source, focused tests run,
red confirmed, real code restored with `git checkout --`, clean
`git status` confirmed after each restore.

| # | Mutation | Command | Result |
|---|---|---|---|
| (a) | Replications bind gate `if any(value is None for value in turns): continue` reinstated | `python -m pytest -q tests/test_alpha_stage1_hardening.py` | **RED**: `test_replications_bind_survives_unpriceable_turnover` fails `assert 0 == 1` on `len(algorithm.cohorts)` — a substantive assertion, not a skipped loop. 1 failed, 3 passed. |
| (b) | Stage1 benchmark `if turnover is None: return` reinstated | same | **RED**: `test_stage1_benchmark_zombie_month_cannot_kill_the_series` fails at line 187 (`len(cohorts) == 1`, cohorts empty). 1 failed, 3 passed. |
| (c) | Stage1 settle `len(outcomes) == len(cohort["entry"]) and …` reinstated | same | **RED**: same test fails at line 208 (`len(rows) == 1`, rows empty). 1 failed, 3 passed. |
| (d) | Battery analyser `fillna(1.0)` → `fillna(0.0)` | `python -m pytest -q tests/test_qc_alpha_battery.py tests/test_alpha_stage1_hardening.py tests/test_alpha_battery_monthly_sim.py tests/test_alpha_battery_short_emitter.py` | **RED**: `test_alpha_analyser_charges_full_turnover_for_unavailable_months` fails on the exact delta (`Expected: 0.00015384615384…`). 1 failed, 62 passed. |
| (d′) | Stage1 analyser `fillna(1.0)` → `fillna(0.0)` (extra, pins the second copy) | `python -m pytest -q tests/test_alpha_stage1_hardening.py` | **RED**: `test_stage1_analyser_charges_full_turnover_and_discloses`. 1 failed, 3 passed. |
| (e) | Battery parser `turnover_ls` reverted to `float(turn_ls) if turn_ls else None` | `python -m pytest -q tests/test_qc_alpha_battery.py` | **RED**: `test_parsers_refuse_present_nonfinite_turnover_or_ic_tokens` (pytest.raises gets no InvalidLog). 1 failed, 51 passed. |
| (e′) | Battery parser `ic` reverted to `float(ic) if ic else None` (extra, pins the generalized guard) | same | **RED**: same test, ic branch (line 676). 1 failed, 51 passed. |
| (f) | Universes `_portfolio` reverted to `if drifted is None: continue` before the book update (extra, pins S0R-004) | `python -m pytest -q tests/test_alpha_battery_research.py` | **RED**: `test_universe_portfolio_heals_after_an_unpriceable_book` fails at line 351 (`dates[2] in turnover.index`). 1 failed, 17 passed. |

**Vacuous-pass audit** (the 075e982 class): none of the seven new tests
can pass on empty results. The bind test asserts `len(cohorts) == 1`
and the full spec set in `cohort["portfolios"]` before its loop; the
benchmark test asserts `len(cohorts) == 1` / `len(rows) == 1` and exact
priced/entered counts; the emitter test asserts `len(frame) == 3` and a
specific ragged row; both analyser tests index concrete report keys
(KeyError on absence) and assert exact deltas; the universes test
asserts exact index membership on all three dates. The seven red
mutations above are direct behavioral proof of non-vacuity.

## 6. Deliberate non-change and contested classifications

**Settle-side `any(symbol not in outcomes …): continue`
(`alpha_stage1_replications.py:579`, `alpha_battery_monthly.py:750`,
`alpha_battery_short.py:442`) — I AGREE it is not an unfixed sibling of
the bind defect.** Four reasons. (1) The bind defect's harm was
persistent-state contamination: refusing to bind froze
`previous_weights` and killed every later period. The settle gate
mutates no persistent state — the book was already replaced at bind —
so the worst case is one missing (spec, date) row, never a die-off.
(2) The drop is visible and parser-enforced: SPECMETA `periods` counts
must match emitted rows exactly or the run refuses. (3) A fixed
portfolio's return is genuinely undefined without every member's
outcome — emitting the priced-subset mean would silently substitute a
different portfolio, which is worse than a disclosed gap. The benchmark
is different in kind: an equal-weight average over priceable members is
still that statistic, which is why R-019's fix (record underfill) is
correct there and not here. Note delistings do NOT trigger this gate
(terminal prices price them); only data-quality zombies do. (4) It is
the frozen, independently reviewed Stage 0 contract; changing Stage 1
alone would make the two stages' month-selection semantics diverge
mid-campaign. Residual caveat, disclosed rather than fixed: dropped
months could cluster in volatile stretches (an R-019-like selection
effect at the alpha-cell level); the stage1 analyser mitigates this by
matching the benchmark to alpha dates (`benchmark.loc[alpha_dates]`),
so the comparison stays sample-consistent.

**S0R-003 "partially correct" — AGREE, now confirmed by execution.**
The pre-fix parsers extracted from `8c9fdc8` accepted a literal `nan`
turnover token into the declared-unavailability channel and refused
`inf`/`-inf` (inf survives `dropna()` and fails the `isfinite` column
check; nan does not survive `dropna()`). The Cursor claim was half
right; the counter-review's split is exactly what execution shows.

**S0R-007 "wording" — AGREE.** The R-022 identity check (max absolute
difference 0.0 vs R-018 on 149 shared months) observes a quantity that
is invariant to the actual return values whenever the two emissions
agree — it carries no directional, magnitude, or significance
information about any counted hypothesis, so it is not a family look.
But it IS a numeric comparison of return values computed outside the
frozen analyser, so "no statistic observed" was imprecise wording. The
A-001 amendment (new entry, R-022 unedited) is the correct append-only
fix, and `8c9fdc8` delivered it.

## 7. Issue ledger

Both findings verified before classification; both closed without code
change. Resolved items retained per process.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix/closure | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SHR-001 | P3 | Closed — no change needed (false alarm as a defect; behavior note) | pre-existing, unchanged by `602dc0b` | `scripts/analyse_qc_alpha_battery.py:82` (`float(token)`), `scripts/analyse_qc_benchmark.py:52` | A malformed non-numeric token (e.g. `abc`) refuses the log via an uncaught `ValueError` traceback rather than a typed `InvalidLog`/`SystemExit`. | Executed: crafted `abc` turnover token → `ValueError: could not convert string to float: 'abc'`. Grep confirms no caller catches `InvalidLog`/`TruncatedLog` selectively, so both exception types terminate the CLI identically. | Failure direction is identical (run refused, nothing relabelled); the distinction is cosmetic diagnostics only, pre-existing before this range, and wrapping it now would be unrelated cleanup inside a records-frozen round. | None. | Probe output recorded in this report; fail-closed confirmed. |
| SHR-002 | P3 | Closed — accepted as adequate (test-sensitivity note) | `602dc0b` | `tests/test_alpha_stage1_hardening.py:98` | `test_replications_bind_survives_unpriceable_turnover` stubs `_rebalance_turnover` to return None, so the stage1 replications' own None-producing path (`alpha_stage1_replications.py:470-482`) is exercised only indirectly. | Source: the lambda override in the test. The path is a line-for-line copy of the monthly `_rebalance_turnover`, which has behavioral sim coverage, and the bind/emitter/parser contract around the None IS mutation-pinned (mutations a, e). | The contract under review (bind never gates; None round-trips) is fully covered; duplicating the monthly sim harness for stage1 would add coverage of already-reviewed copied code. Worth revisiting only if the stage1 `_rebalance_turnover` ever diverges from monthly's. | None. | Mutations (a)/(e) red; source comparison to `alpha_battery_monthly.py`. |

Prior-review S0R items, closure status as verified this session:
S0R-001 closed (`602dc0b`, mutation a), S0R-002 closed (`602dc0b`,
mutations b/c/d′), S0R-003 closed (`602dc0b`, mutations e/e′ + pre-fix
execution), S0R-004 closed (`602dc0b`, mutation f), S0R-005 closed
(`602dc0b`, docstring), S0R-006 resolved (`c9e7a69` merged `de1beac`),
S0R-007 closed (`8c9fdc8` amendment), S0R-008 closed (`602dc0b`,
mutations d/d′).

## 8. Generalized-instance search

Re-ran the sibling grep across `research/lean/`, `scripts/`, and
`backtest/`: `is None for value in turns`, `if turnover is None`,
`if drifted is None`, `if exit_turnover is None`, `dropna()` in the
three analysers, and `any(symbol not in outcomes`.

- **No bind-side turnover gate remains anywhere.** The surviving
  `turnover is None` hits are the two emitters' empty-field paths
  (correct contract) and `alpha_battery_short.py:115`, which propagates
  declared unavailability upward to the v2 sentinel (correct, cleared
  in the counter-review and re-checked here).
- The `any(symbol not in outcomes for symbol in previous)` hits are the
  `_drift_turnover` None-producing paths (the unavailability channel
  itself, not gates).
- The settle-side gates at monthly:750 / short:442 / replications:579
  are the deliberate non-change, symmetric across stages (section 6).
- The dropna-before-finite pattern survives at
  `analyse_qc_alpha_battery.py:314` and `analyse_qc_benchmark.py:77`,
  but nothing non-finite can now reach them from a present token: the
  decimal paths refuse at parse (`_optional_finite` / the BROW guard)
  and the packed u16 path cannot encode NaN. They are now redundant
  defense-in-depth, not relabelling channels.
- No new sibling found. `assistant/`, `execution/`, and `risk/` do not
  share this state machine (confirmed by the grep scope returning no
  hits there).

## 9. Validation on the final tree

All commands run in this session on the review branch (tree identical
to `fba1c0b`):

```text
git rev-parse fba1c0b^{tree} a2fec99^{tree}   # identical: 63ff8411…
python -m pytest -q tests/test_alpha_stage1_hardening.py tests/test_qc_alpha_battery.py
    tests/test_alpha_battery_research.py tests/test_alpha_stage1_replications.py
    tests/test_universe_benchmark_sim.py tests/test_alpha_battery_monthly_sim.py
    tests/test_alpha_battery_short_emitter.py
    -> 102 passed in 5.86s
python -m pytest -q
    -> 4246 passed, 25 warnings in 946.23s (0 failed) — independently
       reproduces the exact figure fba1c0b records
python -m compileall -q assistant backtest data execution ml risk scripts signals
    strategies tests baskets.py config.py market_analytics.py
    -> clean (exit 0)
git diff --check
    -> clean (exit 0)
git status --short --branch
    -> clean on user/claude/review-s0r-hardening-20260818
```

Environment: streamlit 1.60.0 installed (confirms `fba1c0b`'s
resolution record for the 14 previously machine-local UI failures).

Not tested here: QuantConnect cloud execution of the hardened Stage 1
algorithms (no cloud run is authorized); the stub harness exercises the
real classes but not LEAN's own callback ordering. That is the same
residual risk the Stage 0 rounds carried and is the reason Stage 1's
own first cloud run must still round-trip the frozen parsers before any
statistic is read.

## 10. What this review does and does not authorize

- The S0R hardening round (`602dc0b`) **passes independent review**:
  the code gate in front of Stage 1 is cleared.
- **Stage 1 execution is NOT authorized by this document.** Launching
  it is an owner decision (24 new counted cells weighed against the
  A-001 nulls, per `docs/SESSION_HANDOFF.md` 7aa).
- No analyser rerun on the nine Stage 0 logs; A-001 remains the single
  observation. No deployment, epoch roll, operator-database mutation,
  paper orders, or live trading.
- No entry added to `docs/FEATURE_MILESTONE_RECORD.md`: that record
  documents platform features; QC research/review rounds have
  deliberately been recorded in the alpha ledger, handoff, and review
  documents instead, and this round follows that precedent.
