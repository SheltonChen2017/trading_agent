# Phase 5 deployment session — owner checklist and preflight record

Prepared: 2026-08-03, immediately after Phase 4 closed (GR-2 counter-review
confirmed, `main = d5fab71`). This document sequences the one owner-led
session that takes the platform from "code complete" to "collecting formal
paper evidence." It references `docs/OPERATIONS_RUNBOOK.md` for every
procedure rather than duplicating it; if the two ever disagree, the runbook
wins.

Updated 2026-08-04 after the owner resolved all four blocking decisions:
model 2, the owner-approved mandate, `data/trading_assistant.db` as the single
operator record, and the owner's account for scheduled tasks.

Nothing in this document authorizes live trading. `config.PAPER_TRADING`
stays `True` throughout.

## 1. What is already verified (preflight, 2026-08-03, development machine)

Run on the development machine (no broker credentials installed) against
commit `d5fab71` with a clean worktree. These results verify the *tooling*,
not the operational host — re-run the marked items on the operational
machine before deploying.

| Check | Result | Re-run on operational machine? |
|---|---|---|
| Full test suite | 2,543 passed / 1 skipped / 25 warnings | yes — must pass on the exact frozen commit |
| All Phase 5 CLI producers exist (`readiness`, `platform-readiness`, `ledger-bootstrap`, `ledger-reconcile`, `paper-epoch-start/close`, `paper-observation`, `paper-evidence-status`, `record-drill`, `recovery-drill`, `deliver-alerts`, `alert-self-test`, `operations-cycle`, `monitor-orders`) | all present | no |
| `install_windows_operational_tasks.ps1 -WhatIf` | the original preflight hit Task Scheduler `Access denied` before printing a plan; the independent review corrected both installers to emit a four-task, data-only preview without elevation | yes — with the operational machine's python and chosen DB path; require exit 0 and inspect every resolved action |
| `install_windows_ml_shadow_tasks.ps1 -WhatIf` | correctly fail-closed: refuses to plan without a real `artifacts/shadow.json` (machine-local, absent on the dev machine) | yes — where the shadow config exists |
| GR-3 fault-drill harness (`run_fault_drill.py`) | 11/11 fault IDs passed, report bound to clean commit `d5fab71` | yes — with `--record-database` once an epoch is active |
| `platform-readiness` against a disposable DB | fails closed exactly as designed: policy/paper-mode/DB-integrity/kill-switch green; broker `unauthorized` and never-run reconciliation reported as blockers, nonzero exit | yes — individual deployment checks should improve stepwise; evidence and strategy dimensions remain blocked until their independent gates are met |

The independent review reproduced the original operational preview with exit
1 and no planned-task output. That was a failed preview, not a success whose
exit code could be ignored. The corrected preview must exit zero and list all
four resolved actions; any nonzero exit remains a blocker to investigate.

Follow-up 2026-08-04: PR #148 added
`verify_windows_evidence_tasks.ps1 -Scope operational` for the intentional
four-task installation. It verifies the four operational tasks and reports the
six omitted ML path/task checks explicitly under `SkippedChecks`; default
scope `all` preserves the complete eight-task contract.

## 2. Owner decisions (resolved 2026-08-04)

1. **Epoch model 2**: the frozen operational checkout collects evidence while
   development continues elsewhere and is not deployed into that checkout.
2. **Mandate approved with targets unchanged**: the separately committed
   `assistant/default_mandate.json` binds the owner's approval to the exact
   behavior fingerprint. The implementation and independent review merged as
   PRs #146/#147.
3. **Operator DB path**: keep `data/trading_assistant.db` as the single record.
   The operational checkout reaches the same absolute file through
   `TRADING_ASSISTANT_DB`; mixing paths would split the evidence.
4. **Task account**: use the owner's own account. No dedicated account is
   created; scheduler registration still uses an owner-led elevated shell.

## 3. The session itself (operational machine, in order)

Every step is in `docs/OPERATIONS_RUNBOOK.md`; this is the ordering with
its gates.

1. **Freeze**: after the reviewed mandate branch merges, update the operational
   checkout to that exact `main` commit and confirm a clean worktree. Run the
   full suite once on this exact tree.
2. **Elevated window** (owner, admin shell): use the owner's selected account
   and confirm it has the runbook's minimum file/credential access. No account
   creation is required.
3. **Install operational tasks**: runbook §Windows Task Scheduler —
   `-WhatIf` first, review every resolved path, then install and start the
   4 operational tasks manually once. Install the additional 4 ML shadow
   tasks only if a reviewed shadow config/artifact exists and ML evidence
   collection is wanted this epoch.
4. **Verify tasks**: run
   `verify_windows_evidence_tasks.ps1 -Scope operational` with the same
   Python/database paths and the full current-user name
   (`REDMOND\sheltonchen` on this host), then check each of the four tasks
   produced real output at least once. If the optional ML task set is
   installed, use the default `-Scope all` with its config/artifact paths
   instead. In either scope, any failed check or nonzero exit is a blocker.
5. **Bootstrap the ledger**: `readiness`, then `ledger-bootstrap --confirm
   bootstrap` (once), then `ledger-reconcile` — runbook §Before starting a
   paper evidence epoch.
6. **Verify the approved mandate**: run `mandate-status` from the pinned
   checkout and confirm the reported status and computed fingerprint match the
   reviewed owner-approved file. There is no approval CLI.
7. **Start the epoch**: `paper-epoch-start <epoch-id> --strategy-id ...
   --strategy-version ... --model-id ...` on the frozen commit. From this
   moment the commit, mandate/policy fingerprints, strategy/model IDs, and
   the Alpaca paper account ID are immutable for the epoch.
8. **Run all 5 drills inside the epoch** (runbook §Required drills):
   `kill_switch`, `ambiguous_submission`, `restart_recovery` (via
   `run_fault_drill.py --record-database <db> --operator "<name>"`),
   `recovery-drill`, and `alert-self-test --record-drill`. Store evidence
   under `data/drill_evidence/` (git-ignored).
9. **Confirm the expected staged state**: run `platform-readiness` and inspect
   every dimension independently. It is expected to remain nonzero while the
   60-session/30-order evidence minimums are unmet and while no confirmed,
   production-authoritative strategy exists; do not relabel those blockers as
   deployment failures or bypass them. `paper-evidence-status <epoch-id>`
   should show that the epoch exists and will count qualifying post-close
   observations as they are recorded.
10. **Let the 60-session clock run.** The pre-epoch informal paper trading
    data remains useful for execution realism but does not count toward
    the mandate's 60-session minimum.

## 4. What must NOT happen in this session

- No live/funded account, credential, or endpoint anywhere. Alpaca **paper**
  credentials and the paper endpoint are required on the operational host and
  must never be committed or printed.
- No epoch start from a dirty worktree or unmerged branch (the tooling
  refuses; do not work around it).
- No manual edits to evidence tables, ever — a persistent alert is an
  incident, not permission.
- No ML/signal promotion; shadow tasks observe only.
- After the epoch starts: no runtime change on the operational machine
  without `paper-epoch-close` first (model 2) or at all (model 1).
