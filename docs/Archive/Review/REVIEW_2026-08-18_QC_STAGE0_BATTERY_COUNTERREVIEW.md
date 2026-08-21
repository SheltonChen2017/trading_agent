# Counter-review: Cursor/Grok Stage 0 battery review (S0R-001..008)

Status: **counter-review complete; all eight findings verified.** The
Cursor Grok 4.6 review of range `81db126..de1beac` is **accepted as a
genuine independent review of the Stage 0 battery range**, with the
classifications below. Owner acceptance is still required before the
nine PENDING_REVIEW runs are upgraded or the frozen analysers run.

Prepared: 2026-08-18. Counter-reviewer: Claude (Fable 5) — the author of
the five product fixes under review; this document verifies the
*independent reviewer's findings*, it does not substitute for that
reviewer's independence on the fixes themselves.

Frozen analysers were **not** run on the nine PENDING_REVIEW logs. No
Sharpe, IC, p-value, or net-return statistic was observed. The only code
executed was synthetic-fixture probes and one reverse mutation, both
described below, on throwaway fixtures.

## 1. Exact range verified

| Item | Value |
|---|---|
| Range | `81db126..de1beac` (27 commits), matching the reviewer's snapshot |
| Head at verification | `de1beac16930690cda0f23dbe6f584e99600ac66` |
| `origin/main` at verification | `c9e7a69` (PR #249) — **now contains `de1beac`**, unlike the reviewer's snapshot `28e4c02` |
| Reviewer's record | `docs/Archive/Review/REVIEW_2026-08-18_QC_STAGE0_BATTERY_COMPLETION.md` (committed alongside this document) |

## 2. Finding classifications

| ID | Classification | Verification |
|---|---|---|
| S0R-001 | **Confirmed.** | `research/lean/alpha_stage1_replications.py:444-445`: `if any(value is None for value in turns): continue` sits immediately before the `previous_weights`/`previous_entries` update (lines 446-450). Exactly the R-010 shape. The reviewer's 108-test focused run (which included `test_alpha_stage1_replications.py`) passes with the gate in place, so no existing Stage 1 test pins its absence. Stage 1 launch stays blocked until this is ported. |
| S0R-002 | **Confirmed.** | `research/lean/alpha_stage1_benchmark.py`: bind returns on any unpriceable prior name (line 173-174) and again on `turnover is None` (177-178) before updating `previous_weights` (R-017 class, and stricter — one unpriceable name kills the bind); settle requires `len(outcomes) == len(cohort["entry"])` (line 204, R-019 class); `on_end_of_algorithm` emits four-field BROW with `round(turnover, 4)` and no empty-field path (lines 228-232). `scripts/analyse_qc_alpha_stage1.py:129,133` takes `matched["turnover"].mean()` and subtracts costs with no `fillna(1.0)`. All four copies confirmed by source. |
| S0R-003 | **Partially correct.** | Verified **by execution** on synthetic logs: a literal `nan` turnover token is ACCEPTED by both `parse_log` (stored `turnover_ls=nan`) and `parse_benchmark` (stored `turnover=nan`), then flows into the declared-unavailability channel (`dropna()` removes NaN before the finite check; `fillna(1.0)` charges it). The `inf` half of the claim is a **false alarm**: `inf` and `-inf` are REFUSED by both parsers (`InvalidLog: turnover_ls contains non-finite values` / `SystemExit: invalid benchmark turnover`), because infinity survives `dropna()` and fails the `isfinite` check. Core defect stands at P3: corruption is relabelled as declared unavailability instead of refused. Conservative direction (charged 1.0), does not affect the nine logs (empty fields or finite values only), but it silently inflates `unavailable_turnover_periods` and violates the fail-closed comment beside it. |
| S0R-004 | **Confirmed.** | `scripts/run_alpha_universes_20260816.py:202-206`: `if drifted is None: continue` records the month's return (line 200) but skips the turnover, `previous = weights`, AND `previous_outcomes` updates — so after one unpriceable month the book never heals and every later month's turnover is silently absent. Local-battery sibling of the class `d305ea0` fixed in `run_alpha_battery_20260815.py`. Does not affect QC Stage 0 logs. |
| S0R-005 | **Confirmed.** | `research/lean/alpha_battery_monthly.py:519-527`: the `_rebalance_turnover` docstring still describes the superseded retry contract ("a month whose turnover refuses simply retries next month") and additionally cites "the same self-contained pattern the Stage 1 replications and both benchmarks already use" — which now names the *defective* Stage 1 pattern (S0R-001/S0R-002) as the exemplar. Doubly stale. |
| S0R-006 | **Confirmed at the reviewer's snapshot; RESOLVED since.** | At verification time `git merge-base --is-ancestor de1beac origin/main` succeeds: PR #249 (`c9e7a69`) merged `de1beac` into main after the reviewer's snapshot at `28e4c02`. The four-line deferral note is on main. No action remains. |
| S0R-007 | **Confirmed (wording).** | `docs/research/alpha-result.md` R-022 reports "max absolute return difference **0.0**" against R-018 over 149 shared months and then says "Parsing only; no statistic observed." The identity check is a legitimate replication control and reveals nothing about performance (a 0.0 difference between two emissions of the same computation carries no directional information and is not a family look), but the sentence "no statistic observed" is imprecise: a numeric comparison over return values was computed outside the frozen analyser. Because the ledger is append-only, the fix is a clarifying amendment in a later entry or the analyser-run records commit — not an edit of R-022. |
| S0R-008 | **Confirmed and STRENGTHENED by mutation.** | Reverse mutation executed: `scripts/analyse_qc_alpha_battery.py:420` `fillna(1.0)` → `fillna(0.0)`, then ran `tests/test_alpha_battery_monthly_sim.py`, `tests/test_alpha_battery_short_emitter.py`, AND `tests/test_qc_alpha_battery.py`: **57 passed** — the mutation survives not just the two tests the reviewer cited but the entire alpha-analyser test population. Only the benchmark analyser (`test_benchmark_analyser_charges_full_turnover_for_unavailable_months`) and the local runner pin their charges. Real code restored via `git checkout --`; post-restore run green (50 passed on `test_qc_alpha_battery.py`). Production `fillna(1.0)` is correct; the gap is test-only. |

## 3. Additional sibling search

Re-ran the generalized-instance grep (`if any(value is None for value in
turns)`, `if turnover is None`, `if drifted is None`, sibling `is None`
gates) across `research/lean/` and `scripts/`. Result matches the
reviewer's map exactly. Notable non-defects checked and cleared:

- `research/lean/alpha_battery_short.py:115` (`if exit_turnover is None:
  return None`) — propagates declared unavailability upward; the emitter
  converts it to the v2 sentinel. Correct contract.
- `research/lean/universe_benchmark.py:232` — the empty-field BROW emit
  path. Correct contract.
- `scripts/run_qc_stage0.py:71` — `current_commit(require_clean=True)`
  present, as the reviewer's `df59519` disposition claims.

**No new sibling found.** The unfixed set is exactly S0R-001, S0R-002
(including `analyse_qc_alpha_stage1.py`), and S0R-004.

## 4. Verdict

1. **Stage 0:** I agree the seven product/test commits and twenty record
   commits stand as reviewed. None of the eight findings invalidates the
   nine PENDING_REVIEW logs: S0R-001/002/004 are outside the Stage 0
   execution path, S0R-003's nan channel is unexercised by the nine logs
   (verified: they emit empty fields or finite values only), and
   S0R-005/006/007/008 are documentation, topology (resolved), wording,
   and test-coverage items.
2. **The single frozen-analyser pass may proceed once the owner accepts
   the review pair** (Cursor review + this counter-review). Ledger
   upgrades and the analyser run remain owner-gated, per the reviewer's
   own §7.
3. **Stage 1 remains blocked** until S0R-001 and S0R-002 are ported with
   regression tests, and S0R-008's charge-magnitude pin should land with
   them. S0R-003/004/005 belong in the same hardening round. None of
   these blocks the Stage 0 analyser pass.

## 5. What this counter-review does not authorize

Identical to the reviewer's §7: no analyser run on the nine logs before
owner acceptance; no PENDING_REVIEW upgrade before that pass and a
records commit; no Stage 1 QC execution; no deployment, epoch roll,
operator-database mutation, paper orders, or live trading.
