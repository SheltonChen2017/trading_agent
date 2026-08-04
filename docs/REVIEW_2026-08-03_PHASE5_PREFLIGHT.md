# Independent review — Claude Phase 5 preflight

Reviewed: 2026-08-03

Scope: the single Claude commit `1273a06` on
`user/claude/phase5-preflight-20260803`, based on `d5fab71`. The commit is
documentation-only: it records a GR-2 counter-review, a Phase 5 tooling
preflight and owner checklist, and plan/handoff state. The counter-review is
accepted. The Phase 5 material is accepted after the corrections below.

## Commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `1273a06` | Accepted after correction | The counter-review evidence is coherent, but the deployment record mislabeled a failed scheduler preview as successful and overstated the immediate readiness/mandate workflow. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| P5REV-001 | P2 | Resolved | `1273a06` | `docs/PHASE5_DEPLOYMENT_SESSION.md`; both Windows task installers | The checklist instructed the operator to ignore a nonzero `-WhatIf` result even though no plan was produced. Both installers reached Task Scheduler CIM object construction before their preview summaries, so a non-elevated preflight could fail before showing any resolved task action. | Exact reproduction on the submitted tree: operational installer returned exit 1 at `New-ScheduledTaskAction` with `Access denied` and printed no four-task plan. | Phase 5 requires a safe pre-elevation review of exact task actions. Treating an access failure as success hides a broken deployment gate and trains the operator to disregard meaningful failures. | Both installers now return a data-only four-task preview before any `New-ScheduledTask*` call and include executable, arguments, working directory, principal, paths, and limited run level. The checklist requires exit zero. | Non-elevated operational and ML previews each returned exit 0 and four resolved actions. Static regression test proves the preview branch precedes the first scheduler-object construction; focused test file passed 12/12. |
| P5REV-002 | P3 | Resolved | `1273a06` | `docs/PHASE5_DEPLOYMENT_SESSION.md` steps 2, 6, and 9 | The checklist implied `mandate-status` could execute approval and that `platform-readiness` should exit zero immediately after epoch start/drills. The CLI is read-only for mandate status, while readiness deliberately remains blocked until minimum evidence and a confirmed authoritative strategy exist. | CLI parser exposes `mandate-status` but no approval command; `command_platform_readiness` exits 2 for any blocked dimension; evidence checks require 60 sessions/30 orders and strategy readiness blocks without an eligible finding. | An owner session would otherwise stop at a nonexistent approval action or mistake correct fail-closed readiness for deployment failure, inviting manual workarounds. | Documented the separately reviewed fingerprint-bound mandate-file update, removed the nonexistent approval CLI implication, and described the expected staged readiness blockers. | Cross-checked against `assistant/mandate.py`, `assistant/platform_readiness.py`, `scripts/run_personal_assistant.py`, README, mandate, and operations runbook. |
| P5REV-003 | P3 | Resolved | `1273a06` | `docs/SESSION_HANDOFF.md`; `docs/ACTION_PLAN_2026-08-02.md` | Durable state claims drifted: the handoff said origin had only `main` although Claude's pushed topic existed, said the app was healthy on port 8501 although nothing was listening, and the action plan retained a claim that `a656015` was present although it is unresolved. | `git branch -r` shows the Claude topic; `Get-NetTCPConnection -LocalPort 8501` returned no listener; `git rev-parse --verify a656015^{commit}` failed. | Cross-computer handoff and sequencing depend on measured branch/process/commit availability; stale claims can send the next agent to nonexistent state. | Replaced the handoff after the correction commit and corrected current action-plan state without treating machine-local process state as durable. | Final Git topology, port presence, and object resolution re-measured during review. |

No P0 or P1 issue was found. No reviewed issue remains open. This review did
not install or start scheduled tasks, connect to a broker, approve a mandate,
start an evidence epoch, record operational drills, or change paper/live
authority. Execution safety and trading behavior were unchanged except for
making installer previews genuinely non-elevated and read-only.

`docs/FEATURE_MILESTONE_RECORD.md` is intentionally unchanged: Phase 5 is an
owner-heavy deployment milestone and remains incomplete; this preflight is
not a completed product feature.

## Validation on the corrected tree

- Python 3.12.13.
- Red proof on submitted code: operational `-WhatIf` exited 1 with Task
  Scheduler `Access denied` before producing a plan.
- Corrected operational preview: exit 0, four resolved actions.
- Corrected ML preview: exit 0, four resolved actions.
- Focused test: 12 passed, 1 environment cache warning in 2.26 seconds.
- Full suite: 2,543 passed, 1 skipped, 27 warnings in 229.94 seconds.
- Compile and diff checks: clean.
