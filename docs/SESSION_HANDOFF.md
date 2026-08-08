# Development session handoff

Prepared: 2026-08-08, after Codex combined both consecutive whole-codebase
finding lists and corrected every finding in discovery order, on
`codex/fix-combined-code-scan-findings-20260808`.

Audience: Codex, Claude Code, Grok, and the repository owner after a
computer, model, or session change. This is the canonical current-state
handoff. Durable standing rules and operational facts remain in their linked
authority documents so rewriting this state summary does not erase them.

> **Codex correction addendum (2026-08-08, current development state):** At
> owner instruction, Codex combined Claude's `FCS-001..018` list and Codex's
> `CXL-001..024` list in their discovery order, then processed all 42 entries.
> The correction authority is
> `docs/REVIEW_2026-08-08_COMBINED_SCAN_FIX_LEDGER.md`: every entry is now
> independently verified, superseded by its broader correction, or fixed with
> regression evidence. Final validation is **3166 passed, 0 failed, 26
> warnings** under Python 3.12.13; byte-compilation, every PowerShell parse,
> and `git diff --check` also passed. The correction branch is
> `codex/fix-combined-code-scan-findings-20260808`, based on `a48bb852`.
> Correction commit `e313836` is **accepted after correction** against that
> baseline: 0 P0, 0 P1, 0 P2, and 0 P3 findings remain open in this batch.
> This branch and its commits are **local-only and not pushed**; another
> computer cannot retrieve them with `git fetch` until the owner authorizes a
> push. The next step is owner review and, if accepted, explicit push/merge
> authorization. `paper-epoch-002` remains on the separate frozen computer at
> `9a91498`; this development tree was not deployed and must not be deployed
> into the active epoch.

> **Read `docs/OPERATIONAL_FACTS.md` first.** Standing owner decisions,
> machine-local operational knowledge, and engineering watch items live
> there because this file is rewritten every round. Do not copy them back
> into this file; link to them. **Seven watch items were added this round** —
> they are the generalizable lessons, and they matter more than any
> individual fix.

## 0. Latest round — Claude counter-review of the Codex corrections (2026-08-08)

`main` is `24d0cb2` (PR #171): Codex's line-by-line review (CXL-001..024) and
its combined correction batch for all 42 ordered findings.

**Counter-review outcome: accepted after correction.** Branch
`user/claude/counter-review-codex-scan-20260808`. Details in
`docs/REVIEW_2026-08-08_COMBINED_SCAN_FIX_LEDGER.md`.

- Independently reproduced CXL-001/002/008/009/012/022 against the merged
  tree; all hold. Full suite reproduces Codex's **3166** on Python 3.14.6
  (they ran 3.12.13).
- `tests/test_scanner.py` was **not** weakened — its old fixture was passing
  *because* of the infinite z-score it now rejects.
- **CCX-001 (P3, fixed):** CXL-001 corrected a 29-Feb *acquisition* but left
  the mirror case — a 29 Feb *inside* the window — one day **early**, the
  fail-open direction on the accountant-facing export. Boundary now anchors
  on `acquired + 1 day`; 9 leap positions checked against a Pub 550 helper
  guarded by the IRS's own worked example. Reverse mutation: 19 fail.
- **CCX-002 (P3, fixed):** the new doc-consistency guard pinned the *current*
  epoch by name, so the next epoch roll would fail the suite and be "fixed"
  by editing the assertion. Rewritten to assert relationships.
- Judgement disagreement, recorded not acted on: the batch reports 0 P1, but
  CXL-008/009 produced wrong durable financial state. Sequencing was right
  regardless of the label.

Final tree: **3180 passed / 0 failed / 0 skipped / 25 warnings**; compileall
and `git diff --check` clean. Nothing deployed.

## 1. Standing state: THE EPOCH (do not disturb)

`paper-epoch-002` ACTIVE since 2026-08-06T17:55Z on frozen commit
`9a91498`, bound to `my_policy.json`. Operational checkout pinned there.
**Never deploy development commits mid-epoch.** Nothing this round is
deployed; the operational checkout is untouched.

`paper-epoch-001` is CLOSED (plumbing shakedown only; do not cite).

## 2. What happened this round

The owner asked for a whole-repository scan for flaws, defects, bugs,
orphans and inconsistencies, then for every defect found to be fixed.

Branch: `user/claude/full-codebase-sweep-20260807`, **merged to `main`**
in two pull requests. Base was `011ae5c` (`main`, post PR #168).

- **PR #169** merged the sweep record and the seventeen P0-free findings.
- **PR #170** merged `c1df1d0`, the **P1** (FCS-018), which landed on the
  branch *after* #169 was created. For a short window `main` therefore
  carried every P2/P3 fix while still missing the P1 — worth knowing if
  anything was built or deployed from `main` in that gap. Nothing was;
  the operational checkout never left `9a91498`.

`main` is now `ceeddac` and contains all eighteen fixes.

Ledger: `docs/REVIEW_2026-08-07_FULL_CODEBASE_SWEEP.md`; findings in §2,
**corrections and their verification in §2b**, honest coverage in §3.

Commits, oldest first:

| Commit | Contents |
|---|---|
| `f2e1c2d` | Sweep recorded: FCS-001..015, documentation only, nothing fixed |
| `32e2751` | FCS-016 added (tax_lots anniversary misclassification) |
| `38373d3` | FCS-016's timezone dimension + corrected fix guidance |
| `05f82c8` | FCS-001 and FCS-016 fixed; FCS-017 recorded |
| `4e85dc2` | The remaining fifteen fixed; handoff rewritten |
| `adef540` | Handoff records the branch is on the remote |
| `c1df1d0` | **FCS-018 (P1)** found and fixed; four P1-class invariants re-derived |

**0 P0 · 1 P1 · 4 P2 · 13 P3 · all 18 fixed · none independently reviewed.**

### The P1 — FCS-018

The owner challenged an earlier "no P1 found" headline. That challenge was
right, and a second pass aimed at P1 classes found one.

Both Streamlit approval handlers rendered `Order not submitted: {exc}`. A
raising submit does **not** prove the broker rejected the order — the
response can be lost after acceptance — which is why the kernel leaves the
proposal in `submission_unknown`, keeps the reservation, and raises a message
that begins *"Could not confirm whether the order … was accepted"*. The
operator read a definite negative prefixed onto its own contradiction.

P1 rather than P2 because *incorrect broker outcome* and *duplicate orders*
are both in the P1 definition. The machine cannot itself duplicate — the
`submission_unknown` status holds the ticker/side slot — but the defect acts
on the **human**, and an operator told the order was not submitted has an
obvious next move: place it by hand at the broker, outside every guard here.

Fixed by `_render_submission_failure()`, which decides from the **durable
proposal status** the kernel already wrote (never the exception text) and
fails toward UNKNOWN when the row cannot be re-read. The CLI never had this
defect — it lets the exception propagate untouched.

### The four P2s

| ID | What was wrong | Fix |
|---|---|---|
| FCS-001 | `strategy_proposals` divided by `current_price` unguarded at four sites, while the sibling `proposals.py` has guarded that exact idiom since 2026-07-29. The UI caught only two narrow exception types, so the `ZeroDivisionError` escaped and **suppressed risk-reduction sells already computed in the same handler**. | Both legs validated → new `StrategyPositionDataError`, a `StrategyMarketDataError` subclass so existing callers already catch it. UI handler widened to `Exception`, matching the CLI. |
| FCS-016 | `tax_lots.is_long_term` compared **timestamps** where its own docstring and the IRS rule are **date**-based, and judged in UTC while `tax_reporting` prints and buckets in Eastern. An exported row could read `acquired 2025-03-10, sold 2026-03-10, LONG-TERM`. | One `_one_year_on()` comparing market-local dates; `MARKET_TIMEZONE` defined once in `tax_lots` and imported by `tax_reporting`. |
| FCS-002 | `calibration_error` divided a finite-pair numerator by the raw row count, so the reported error improved as coverage worsened (0.1500 → 0.0150 measured). | All five classification metrics scored on the same finite pairs; both counts published. Also closed a second half found while fixing: `NaN >= threshold` scored a declined prediction as a confident negative. |
| FCS-003 | The QuantConnect allowlist accepted percent-encoded traversal, one day after being hardened against the literal form. | Double percent-decode before the check, plus outright rejection of `%`. |

### The thirteen P3s

`FCS-004` headroom nets out committed capital · `FCS-005` AST lint banning
bare `Decimal(str(...))` — the guard `OPERATIONAL_FACTS` §3 demanded after a
fourth occurrence · `FCS-006` dead float `worst_case_fill_price` removed,
rationale relocated and corrected · `FCS-007` fourth risk-check scatter point
documented · `FCS-008` the gate's mixed pct/fraction units documented at the
signature and pinned · `FCS-009` telemetry states that decision and arrival
price are one observation · `FCS-010` stale doc line counts · `FCS-011` CI
gains Python 3.14 · `FCS-012` unwired validator applied; `list --limit -1` no
longer unbounded · `FCS-013` atomic tax-report write · `FCS-014` orphans ·
`FCS-015` `save_policy` temp-name race · `FCS-017` four freshness checks no
longer read a future timestamp as fresh.

### Two corrections I made to my own findings

Recorded because a review that only sharpens other people's work is not being
run honestly.

1. **FCS-001's severity was overstated.** The first write-up claimed NaN was
   reachable. It is not — `build_portfolio_snapshot` rejects non-finite
   prices and the Alpaca builder delegates to it; the reproduction had
   hand-built a `PortfolioPosition` and bypassed that boundary. **Zero and
   negative** are the reachable trigger.
2. **FCS-016's first fix guidance was wrong.** "Compare `.date()` values" was
   tested and still returns long-term on the UTC/Eastern case. The comparison
   has to use market-local dates.

## 3. Validation (exact final tree)

- Base `011ae5c` before any change: **3015 passed / 0 failed / 0 skipped /
  25 warnings**.
- **Final tree: 3100 passed / 0 failed / 0 skipped / 25 warnings** (261s).
  The +85 over baseline is entirely new regression tests; **no pre-existing
  test changed its result**, which is the claim that matters.
- `compileall` clean; `git diff --check` clean.
- Reverse mutations, each applied in the fixed code's own location and then
  restored: FCS-016 → **8 fail**, and **both original boundary tests still
  passed**, which is their insensitivity made executable; FCS-001 → **7
  fail**; FCS-002 → **1 fail**; FCS-003 → **5 fail** with both layers
  removed, **1** with only the `%` rule removed, **0 with only the decoding
  removed** — recorded because it shows which layer carries which input;
  FCS-004 → **1 fail**; FCS-018 (unknown branch disabled) → **1 fail**.
- Run on **Python 3.14.6**. CI now covers 3.12/3.13/3.14 (FCS-011), but the
  3.14 job has never executed — it will on first push.
- FPS-003 did not reproduce. It stays open — a green run is not evidence.

### The four P1-class invariants, re-derived not inherited

The previous round took these from the 2026-08-06 sweep. This round walked
them against the current tree:

| Invariant | Result |
|---|---|
| Every production proposal-status write is fenced | **holds** — 14 `update_proposal_status_if_current` call sites, **0** unfenced |
| Reservations release exactly once | **holds** — one `reserve_execution_budget` site, one `release_execution_reservation`, three `mark_submission_failed_and_release`, all through atomic primitives |
| No execution-capable module reaches `ml`/LLM | **holds** — 54 roots walked, 0 unresolvable import forms; the ADR direction (LLM → execution) is 0 across 13 advisory roots |
| Ledger double-entry | **holds** — validated at write *and* re-derived as a trial balance on every read |

Also re-verified directly: `reclaim_stale_status` is the one atomic primitive
without `BEGIN IMMEDIATE`, and it is **correct anyway** — its conditional
UPDATE is a compare-and-swap, with a 30s busy timeout under WAL. Do not
"fix" it.

One apparent violation was a **false alarm**: `recommended_stocks →
ai_advisor`. My root set treated every `assistant.*` module as
execution-capable; the project classifies `recommended_stocks` as a
*proposal-generation* module, which is correctly allowed to use the advisor
and is not reachable from any order path.

## 4. Coverage honesty — the sweep was NOT exhaustive

All 199 production modules received mechanical AST coverage: unguarded
division, `except: pass`, SQL interpolation, non-atomic artifact writes,
naive datetimes, mutable defaults, `Decimal(str())`, `or 0`, freshness
bounds, the FPS-004 count-vs-denominator class, and a full orphan graph.

**Only ~35 modules were read line by line; roughly 44K of 62K lines were
not.** Not read: most of `ml/`, most of `scripts/`, the bulk of
`storage.py`, `personal_assistant_ui.py`, `backtest/engine.py`,
`portfolio_ledger`, `paper_evidence`, `tax_reporting` beyond its row and
coverage layer, `operations` beyond its freshness checks, `assistant/llm/*`,
`signals/`, `strategies/`.

Every P2 was found by a scan flagging candidates **plus** reading the flagged
site beside its correct sibling. That pairing has not reached the packages
above, so "all findings fixed" means every finding *this sweep produced* —
not that the codebase is clean.

## 5. What is next

1. **Independent review of all 18 fixes is IN PROGRESS** (owner sent them to
   GPT/Codex, 2026-08-07). FCS-018 is the one to read first. Nothing here has
   been reviewed by anyone but its author, and this round produced two
   self-corrections plus one severity upgrade after the owner challenged a
   "no P1" headline — so treat the ledger as author-verified, not reviewed.
   When the feedback arrives, follow the `external-review-response` workflow:
   verify each finding before fixing it, classify it confirmed / partially
   correct / false alarm, search for generalized instances, and mutation-check
   every regression test.
2. **FCS-016 changes a value in an accountant-facing export.** A tax report
   generated before today may disagree with a regenerated one for any sale on
   a one-year anniversary — previously long-term, correctly short-term, so
   the earlier file understated tax. If one has already been sent, say so.
3. Continue the sweep over the packages in §4, using the scan-then-read
   pairing that produced every P2.
4. Owner sets QC credentials and runs one live `authenticate()` (watch
   CQC-001 in `OPERATIONAL_FACTS`).
5. Owner decision: news allowlist scope for holdings vs UNIVERSE/known.
6. **GR-6** off-machine backup is **blocked on this host** (owner,
   2026-08-07): corporate machine, no uploads permitted. Only a physical
   medium qualifies. See `docs/OPERATIONAL_FACTS.md` §2. Do not re-propose
   OneDrive.
7. Roadmap otherwise unchanged: remaining GR-6 items needing no off-machine
   copy, or the GR-7d owner decision (rebalance targets).

## 6. Non-negotiable boundaries

- Paper only; never deploy mid-epoch.
- Reporting may not propose/approve/size/submit/dismiss.
- Reports/CLI reporting must not write provider-fetch or execution evidence.
- Incomplete/insufficient samples must say so in the artifact.
- Selection residual is not a skill claim.
- **QuantConnect raw market data must never enter this repository.** Results
  only; the endpoint allowlist in `research/quantconnect.py` is the
  enforcement, and weakening it breaks their licence (see FCS-003).
- Snapshot `total_equity` is post-flow; subtract `net_external_flow` before
  any `Observation.value_before_flow` mapping.
- AI refusal reasons must be fixed labels — never withheld model prose or
  invented figures.
- **An optional feature's failure must never suppress a risk-reducing
  proposal** (FCS-001).
- **A metric's denominator must be the observations it actually scored**
  (FPS-004, FCS-002).
