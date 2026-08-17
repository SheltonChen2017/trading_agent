# Verification of Fable's final alpha/QC counter-review

Date: 2026-08-17
Reviewer: Codex
Reviewed remote: `origin/user/claude/alpha-qc-full-counterreview-20260817`
Base: `f937bfb11fe82f45fd0f4715a98217a3aa957c92`
Exact reviewed head: `6bd962fac9e417f0f1d014b4128c2a9597d45e5b`
Ordered range: `5816f6f`, `ee58aa5`, `6bd962f`
Merge topology: PR #243 merged that head to `origin/main` at `4151b3f`
Correction branch: `codex/review-alpha-qc-fable-counterreview-20260817`
Product/test correction: `ac96d47`

## Outcome

**Not ready for a QuantConnect run yet.** Fable's added tests are useful and
all three commits are acceptable after the follow-up corrections below, but
its conclusion that no product defect existed was wrong. Verification found
two P2 Stage 0 result-calculation defects and two P3 fail-closed data edges.
All four are corrected locally with behavioral tests. Because the correction
changes potential Stage 0 results, another independent counter-review of the
exact pushed Codex head is required before QC is launched.

No QuantConnect authentication, upload, compile, backtest, or result read was
performed. No research look, broker action, database mutation, scheduler
change, deployment, order, or evidence-epoch change occurred.

## Commit-by-commit dispositions

| Commit | Disposition |
|---|---|
| `5816f6f` | **Accepted.** The Stage 1 look-gate, outer polling deadline, and expanded LEAN legacy-name tests are correctly scoped and load-bearing. They did not cover the Stage 0 findings below. |
| `ee58aa5` | **Accepted after correction.** The CRLF hash-convention clarification is reproducible, but its report/action-plan claim that no product defect remained and the QC gate was open is superseded by this review. |
| `6bd962f` | **Accepted after correction.** It accurately handed off Fable's own review, but its topology and launch-gate status became stale after PR #243 and after the defects below were reproduced. The canonical handoff is corrected in this review. |

## P0-P3 issue ledger

Summary: **0 P0, 0 P1, 2 closed P2, 3 closed P3, 0 open code findings.**
The launch gate remains closed only because independent review of the new
result-changing correction has not yet occurred.

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| FQCV-001 | P2 | Closed | `6bd962f` | `research/lean/alpha_battery_short.py::_settle` | The short battery settles and exits after five sessions, waits through score staging, then enters on the next session, but turnover was calculated as a direct rebalance. Overlapping old/new books could record near-zero cost although each holding requires an entry and exit. It also shifted no exit cost onto the return that caused it. | With a flat gross-1 holding, the submitted cross-period helper could record 0 for an unchanged next target; the required same-period entry plus liquidation is 1.0 one-way turnover. | Realized turnover and transaction costs are frozen Stage 0 outcome fields; undercharging or period-shifting them changes net returns and fails the milestone definition of done. | Each staged portfolio stores its target weights; `_settle` computes `_round_trip_turnover` from that period's target and realized outcomes, charging entry plus drifted exit on the same row. Cross-period weight/outcome state was removed. | Behavioral regression proves a flat gross-1 holding costs 1.0 and missing outcomes refuse; AST pins the helper to settlement and proves binding does not calculate a direct rebalance. |
| FQCV-002 | P2 | Closed | `6bd962f` | `scripts/analyse_qc_alpha_battery.py::main` | One global default annualized every family at 12 periods/year. The short battery emits one non-overlapping observation per six sessions, or 42/year, so its Sharpe/annualized return/downside figures were materially wrong unless an operator supplied an undocumented override. A mixed monthly+short invocation could not be correct at all. | The CLI default was `12.0` and was passed unchanged to every parsed spec family. | Cadence is part of the frozen statistical definition and cannot depend on an operator remembering an unstated flag. | Cadence is inferred per recognized frozen family: monthly 12, short `252/6 = 42`; an optional CLI value is now only an assertion and conflicting values refuse. The report records the selected cadence. | Behavioral tests pin both family mappings, the CLI wiring, unknown-family refusal, and rejection of a 12/year short override. |
| FQCV-003 | P3 | Closed | `6bd962f` | `research/lean/alpha_battery_short.py::_form_scores` | MAX(20) silently skipped a return when its denominator close was non-positive, then scored a shorter window as though all 20 returns existed. | A 21-close window with one zero produced 19 returns instead of refusal. | Method V2 requires exact windows and fail-closed invalid input; a low-likelihood data edge must not change the signal definition. | Added `_max_daily_return`, requiring exactly 21 finite positive closes and exactly 20 returns. | Behavioral tests cover valid input plus short, zero, negative, NaN, and infinity refusal; AST pins the scoring call. |
| FQCV-004 | P3 | Closed | `6bd962f` | `research/lean/alpha_battery_monthly.py::_fine`; `research/lean/alpha_battery_short.py::_fine` | Missing Morningstar codes were stored as `0`, grouping unrelated unknown companies into one fictitious industry for residual/industry-relative signals. | `int(code or 0)` fed the same zero bucket for every missing value. | The frozen method requires a real point-in-time industry and explicitly forbids approximation. | Only positive integer codes enter membership/buckets. Missing/invalid classifications remain missing; non-industry signals may still use the name. Monthly market-factor membership is no longer incorrectly restricted to industry-classified names. | Pure-helper regressions cover valid and invalid codes; existing leave-one-out tests prove missing membership refuses the industry factor. |
| FQCV-005 | P3 | Closed | `ee58aa5`, `6bd962f` | Action Plan, alpha plan/ledger, Session Handoff | The records said `origin/main` was `f937bfb`, Fable's branch awaited merge, and the QC gate was satisfied. PR #243 and this result-changing correction made all three statements false. | Read-only remote inspection found `origin/main=4151b3f`; correction `ac96d47` is not yet counter-reviewed. | A stale handoff could cause an operator to run the wrong source and consume another invalid research look. | Canonical records now name the exact topology, defects, correction, unchanged look counts, and closed launch gate. | Active-document checks and final Git/diff inspection. |

## Validation

- Red-first focused reproduction: the original tests failed for missing
  same-period round-trip turnover, strict MAX(20), and cadence behavior.
- Corrected QC alpha-battery file: **36 passed**.
- Broader research/QC gate: **222 passed** across Stage 0, Stage 1, LEAN
  dialect/safety, QuantConnect client, and analyzer tests.
- Full repository suite: **4,203 passed / 0 failed / 25 known dependency
  warnings in 867.87 seconds**.
- Repository-wide compilation including `research/`: clean.
- Active-document consistency: **31 passed**. Markdown relative links and
  tracked JSON: clean. Final diff/status/ordered-commit checks: clean before
  each records commit.

## Exact next gate

Publish this one Codex review branch after final validation. The independent
reviewer must start from its exact remote head, review `ac96d47` and the
documentation/handoff commits individually, rerun the research/QC tests, and
specifically mutate FQCV-001 and FQCV-002. Only an accepted counter-review
reopens the QC gate. The next run is then recorded as R-005 or later with full
project/compile/backtest/source/log identity and unchanged 428-cell/five-run
starting counts.
