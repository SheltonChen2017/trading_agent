# Independent review — observation clock and epoch-005 roll

Prepared: 2026-08-13 by Codex

Review base: `752d3b7`

Implementation head: `4de784e`

Review branch: `codex/review-observation-clock-roll-20260813`

Final disposition: **accepted after correction**. The observation-clock
diagnosis and the executed roll itself were supported by read-only host and
database checks. The submitted documentation was not acceptable as current
operational state: its dedicated roll file still said the completed roll was
unauthorized, the action plan still called six deployed items undeployed, the
required session handoff was left at epoch-004, and one roll generalization
overstated a conditional freshness failure. No production Python, schema,
policy, proposal, execution, broker, scheduler, or database behavior changed
in this review.

Submitted implementation quality: **6.5/10**. The clock investigation was
careful and the runbook-ordered roll record contains useful operational
detail. The score is reduced because durable-state documentation is a safety
control in this repository, and the merged tree presented mutually exclusive
instructions about whether the roll had happened and what was deployed.

## Commit dispositions

| Commit | Disposition | Review result |
|---|---|---|
| `9e464d2` | Accepted after correction | The installed-trigger diagnosis and read-the-trigger guidance are correct. OBR-002 corrected the nonexistent status command; OBR-006 removed an unsafe absolute claim about roll tradeoffs. |
| `0f3f0b6` | Accepted after correction | The recorded roll facts agree with read-only host/storage checks. OBR-001, OBR-003, OBR-004, and OBR-005 corrected incomplete or overbroad current-state documentation. |
| `4de784e` | Accepted after correction | Merge-only commit. Both parent comparisons showed no conflict-resolution delta; cumulative documentation defects remained until this review. |

## Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| OBR-001 | P2 | Resolved | `0f3f0b6` | `docs/Archive/Plans/EPOCH_005_ROLL_PLAN.md` | The completed roll remained labeled not authorized and not executed, with an actionable “if authorized” section. A later operator could mistake it for current instructions and initiate a second epoch roll. | New active-document guard failed on the submitted tree; action plan and operational facts both said epoch-005 was active. | Current operational documents must not disagree about an epoch-changing action. | Converted the file into an unmistakable executed historical record, preserved preparation facts, recorded outcomes, and explicitly prohibited replay. | Red/green `test_epoch005_roll_record_replaces_its_unexecuted_plan`. |
| OBR-002 | P3 | Resolved | `9e464d2` | `docs/Archive/Plans/EPOCH_005_ROLL_PLAN.md` | The re-check table named `paper-epoch-status`, which is not a CLI command. It fails loudly but delays or confuses a high-care operation. | Direct CLI invocation returned argparse “invalid choice”; `paper-evidence-status` returned the active epoch summary. | A runbook companion must name an executable read-only verification command. | Replaced it with `paper-evidence-status`. | Red/green roll-record guard plus direct successful CLI check. |
| OBR-003 | P2 | Resolved | `0f3f0b6` | `docs/Archive/Plans/ACTION_PLAN_2026-08-02.md` | The summary said AP-8, AP-9, QC-2, AP-10, AP-11, M3, and SELL-1 deployed, while the detailed rows still said all but AP-11 were undeployed or awaiting deployment. | New row-by-row guard failed on the first stale row and manual enumeration found every affected row. | The owner-adopted sequencing authority cannot simultaneously call deployed runtime code undeployed. | Updated every affected current row, the M3 narrative, and Phase 5 to identify epoch-005 and deployed commit `752d3b7`. | Red/green `test_epoch005_deployment_status_is_consistent_in_the_action_plan`. |
| OBR-004 | P2 | Resolved in the required separate handoff commit | `0f3f0b6` | `docs/SESSION_HANDOFF.md` | No handoff update accompanied an epoch closure, deployment, new active epoch, drills, alerts, or branch-topology change. It still prohibited the roll and called epoch-004 active. | Direct inspection; the stale handoff named `c3d10ff` while fetched `origin/main` was `4de784e`. | Repository rules make the handoff the cross-computer state authority; omitting this update can send the next agent toward obsolete or prohibited work. | The separate handoff commit replaces the file with the reviewed epoch-005 and branch state and names this review. | Red/green `test_current_handoff_records_the_epoch005_roll_and_reviewable_head` in the handoff commit. |
| OBR-005 | P3 | Resolved | `0f3f0b6` | `docs/operations/OPERATIONAL_FACTS.md` | “Readiness fails ... during any roll” converted a one-run observation into a universal claim. Freshness fails only if the disabled interval exceeds the configured age window. | `assistant/readiness.py` compares age to `max_reconciliation_age_minutes`; a sufficiently short roll need not cross it. | Operators should expect the observed recovery without diagnosing every future roll as guaranteed to fail. | Reworded the fact conditionally and retained the exact observed five-minute behavior. | Red/green `test_roll_freshness_guidance_is_conditional_not_universal`. |
| OBR-006 | P3 | Resolved | `9e464d2` | `docs/Archive/Plans/EPOCH_005_ROLL_PLAN.md` | “The argument against rolling is only ever lost evidence” excluded deployment risk, broker availability, ledger disagreement, and task recovery from the decision. | The same plan requires explicit controls for each of those stop conditions, contradicting its own absolute claim. | An operational plan must not minimize independent reasons to abort a runtime and evidence-epoch replacement. | Reframed lost evidence as the primary cost considered in this roll while retaining the other preconditions as independent controls. | Red/green roll-record guard. |

Issue totals: **0 P0, 0 P1, 3 P2, 3 P3; all resolved by the correction and
handoff commits.**

## Read-only operational verification

The review did not mutate the operator database, tasks, operational checkout,
or brokerage state. It verified:

- epoch host identity `REDMOND\sheltonchen`;
- installed PaperObservation trigger `2026-08-05T16:30:00-07:00`;
- OperationsCycle and PaperObservation enabled/ready, with OrderMonitor and
  Watchdog running;
- operational checkout clean at exact commit `752d3b7`;
- `paper-epoch-005` active from `2026-08-13T23:59:07Z`, with zero observations
  at review time and all five required drill types passed; and
- the lineage-hash prefix matched the durable roll record.

No account identifier, balance, credential, or other sensitive value is
recorded here.

## Safety and scope

The reviewed commits contain documentation and document-consistency tests;
they do not change trading logic. Paper mode, typed approval, the kill switch,
storage-level claims, reservations, reconciliation, execution import
boundaries, and ML/LLM non-authority were therefore out of behavioral scope
and are not claimed as re-proven. The roll record reports the already executed
kill-switch and recovery drills; this review independently checked their
presence, not their internal behavior.

`docs/FEATURE_MILESTONE_RECORD.md` was not changed. The work records an
operational epoch roll and corrects current state; it does not complete a new
feature or roadmap milestone, and the deployed features already have their
own reviewed milestone records.

## Validation

- Submitted-tree red proof: **4 failed, 21 passed** in the active-document
  suite; each failure matched OBR-001, OBR-003, OBR-004, or OBR-005. A
  separate focused red run reproduced OBR-006. OBR-002 was additionally
  reproduced by direct CLI rejection.
- Pre-handoff corrected tree: active-document suite **24 passed**; full suite
  **3,622 passed, 0 failed, 0 skipped, 25 known dependency warnings** in
  706.47 s under Python 3.13.14 / Streamlit 1.60.0; compileall (including
  `research`) and `git diff --check` passed. The final handoff commit records
  the post-handoff exact-tree recheck.

## Remaining work

The first scheduled epoch-005 observation had not yet occurred when this
review checked the database. Until a lineage-bound observation exists,
`lineage_consistent: true` is vacuous and the 60-session evidence count is
zero. Verifying that scheduled capture is ordinary operations monitoring, not
authorization for a new deployment, another roll, M4, or live trading.
