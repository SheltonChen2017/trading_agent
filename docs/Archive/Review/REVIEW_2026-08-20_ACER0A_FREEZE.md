# Independent review — ACER-0A decision freeze and read-only measurements

Status: **accepted after correction**

Reviewed remote: `origin/user/claude/acer0a-freeze-20260820`

Base and merge-base: `b58947e589c6fa92ed498f57f68ba0590048303f`

Exact pushed review head: `3a98fefb0808e4e9e4b3bc185ee59c12b1449bac`

Ordered range: `b58947e589c6fa92ed498f57f68ba0590048303f..3a98fefb0808e4e9e4b3bc185ee59c12b1449bac`

Review branch: `codex/review-acer0a-freeze-20260820` (**local-only** until
the owner separately authorizes a push)

## Commit disposition

| Commit | Subject | Disposition | Reason |
|---|---|---|---|
| `3a98fefb0808e4e9e4b3bc185ee59c12b1449bac` | Freeze ACER-0A and record two read-only measurements | **Accepted after correction** | The owner decisions, read-only SBR measurement, alert facts and safety boundaries were useful and mostly careful. The commit nevertheless called an under-specified research design executable/frozen, left the run-slot failure rule contradictory, overstated seven sampled sleep correlations as universal, misstated `StartWhenAvailable` catch-up behavior, and left active sections internally stale. |

No other commit was present in the pushed range.

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| ACER0AR-001 | P2 | Resolved | `3a98fefb` | `docs/research/ACER_2026-08-20_ACER0A_FREEZE.md`; ACER plan/action plan/handoff | ACER-0A was called frozen and operative even though the signal, controls, residualization, folds, statistic, test periods and point-in-time membership semantics were not defined. A developer could implement materially different tests under the same alleged preregistration. | The submitted section 9 named only four open items, while the body used undefined terms such as ordinal notch change, per-firm mean, residualized IC and existing block toolkit. The repository toolkit itself exposes Pearson/Spearman, block length, draws, seed and fold choices rather than selecting them. | Research claims are not reproducible if outcome-sensitive choices remain available after the freeze label says they are settled. | Reclassified the document as a partial decision freeze, prohibited real signal/outcome joins, and expanded the completion ledger to ACER-0A.1–0A.10 covering rating scale, signal construction, controls/outcome, evaluation, slots/confirmation and universe semantics. | Relational active-document guard passes; focused suite recorded below. |
| ACER0AR-002 | P2 | Resolved | `3a98fefb` | Freeze section 4 | The budget capped development and confirmation at one execution each but also contemplated corrected reruns after errors/refusals, without saying whether a consumed slot could be replaced or what confirmation must pass. That permits an undeclared extra historical look. | Original text: every error/refusal counts; each category budget is one; a corrected rerun is also counted. No terminal rule reconciled those statements. | A run budget is not enforceable when the failure path can create another run by interpretation. | Marked the slots provisional, prohibited replacement/third runs, and added ACER-0A.9 for the owner to freeze refusal/error, period, ledger and confirmation rules before execution. | Document-consistency guard passes; no real-outcome run was performed. |
| ACER0AR-003 | P2 | Resolved | `3a98fefb` | `docs/Archive/Operations/RECONCILIATION_ALERTS_2026-08-20_DIAGNOSIS.md`; `OPERATIONAL_FACTS.md`; action plan/handoff | The diagnosis generalized seven checked sleep correlations to every long gap and said a missed scheduled observation was skipped/guaranteed lost despite installed `StartWhenAvailable=True`. That could misdirect an operational decision and misstated the evidence-capture failure path. | The submitted document itself says only seven of 22 long gaps were inspected. Read-only task measurement confirmed `WakeToRun=False`, `StartWhenAvailable=True` on both sampled tasks. Microsoft documents that setting as queueing missed time-based starts, normally with a delay. The capture code can succeed later on the same Eastern session date or refuse/no-op after its date/freshness bounds. | Operational records must distinguish a measured sample from a universal cause and must describe installed scheduler behavior accurately. | Scoped the causal statement to seven sampled gaps, recorded 15 unexamined gaps, corrected the task count from three to four, documented catch-up semantics and the conditional observation outcome, and time-bounded the health verdict. | New scheduler-semantics relationship test passes; read-only database check independently confirmed the two alert payloads, epoch counts and post-alert healthy runs. |
| ACER0AR-004 | P3 | Resolved | `3a98fefb` | ACER reference plan, action plan, handoff reading order | Active sections still said SBR was unmeasured, ratings history was not owned, ACER was a draft with no purchase, and the plan froze no value; the handoff also duplicated reading-order number 4. | These statements contradicted new sections in the same commit recording the SBR measurement, purchased/audited ratings and frozen owner decisions. | Conflicting active instructions make the next agent start from obsolete state. | Reconciled the active summaries/data table and corrected the handoff numbering. Added a relationship guard tying the ACER plan to the durable SBR measurement. | Focused active-document suite passes. |

No P0 or P1 issue was found. The commit changed no application or execution
code, so paper mode, human approval, kill switch, broker state transitions,
reservations and import boundaries were out of scope and are not claimed as
re-proven.

## Independent evidence checks

- Exact installed task settings were measured read-only; no task was changed.
- The operator database was opened with SQLite `mode=ro`. The two documented
  alerts had the submitted ids, occurrence counts, timestamps and no mismatch
  in their alert payloads. Epoch counts were `1,1,1,3,3,2`, including two for
  `paper-epoch-006`. At the later review query, 23 reconciliations (rather
  than the document's earlier 20) had completed after the last alert failure,
  all matched; that advancement supports rather than contradicts the
  time-stamped submitted measurement.
- No QuantConnect, Massive/Benzinga or broker API was accessed. No licensed
  row, outcome, signal, backtest or research look was consumed.

## Validation

- Focused documents/scheduler/evidence capture:
  `59 passed in 8.77s`.
- Complete repository suite: `4,420 passed / 0 failed / 25 warnings in
  834.29s` on Python 3.13.14. Warnings were the existing one `websockets`
  legacy deprecation and 24 NumPy/joblib shape deprecations.
- `compileall -q` passed over `assistant`, `backtest`, `data`, `execution`,
  `ml`, `research`, `risk`, `scripts`, `signals`, `strategies`, `tests` and
  the required root modules.
- `git diff --check` passed. Final clean status and commit-order checks are
  recorded after the review and handoff commits.

## Acceptance and remaining gates

The owner decisions are retained and frozen, but **ACER-0A is not yet an
executable preregistration and ACER-2 must not run**. The next research task is
to close ACER-0A.1–0A.10 without inspecting outcomes. ACER-0B remains
unfrozen and ACER-3 retains a zero-run budget.

The read-only operational diagnosis supports no automatic mutation. Alert
acknowledgement, wake settings, sleep policy, thresholds and epoch state still
require separate owner authority.
