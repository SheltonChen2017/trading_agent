# Phase 5 deployment session — owner checklist and preflight record

Prepared: 2026-08-03, immediately after Phase 4 closed (GR-2 counter-review
confirmed, `main = d5fab71`). This document sequences the one owner-led
session that takes the platform from "code complete" to "collecting formal
paper evidence." It references `docs/OPERATIONS_RUNBOOK.md` for every
procedure rather than duplicating it; if the two ever disagree, the runbook
wins.

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
| `install_windows_operational_tasks.ps1 -WhatIf` | plans all 4 operational tasks (S4U, Limited); correctly REFUSED the Microsoft Store python alias until given a real interpreter | yes — with the operational machine's python and chosen DB path |
| `install_windows_ml_shadow_tasks.ps1 -WhatIf` | correctly fail-closed: refuses to plan without a real `artifacts/shadow.json` (machine-local, absent on the dev machine) | yes — where the shadow config exists |
| GR-3 fault-drill harness (`run_fault_drill.py`) | 11/11 fault IDs passed, report bound to clean commit `d5fab71` | yes — with `--record-database` once an epoch is active |
| `platform-readiness` against a disposable DB | fails closed exactly as designed: policy/paper-mode/DB-integrity/kill-switch green; broker `unauthorized` and never-run reconciliation reported as blockers, nonzero exit | yes — should go green stepwise as the session proceeds |

Preflight finding worth knowing: the operational-tasks installer exits
nonzero after a successful `-WhatIf` preview. Judge the preview by its
planned-task output, not the exit code.

## 2. Decisions the owner must make first (blocking, in order)

1. **Epoch model 1 vs 2** (action plan §7): freeze this machine's runtime
   for the whole 60-session window (model 1) or dedicate the operational
   machine to the frozen commit while development continues elsewhere
   un-deployed (model 2). Everything below assumes a decision.
2. **Approve the mandate** (or revise its DRAFT §2 targets first):
   `python scripts/run_personal_assistant.py --database <db> mandate-status`
   shows the current state. The epoch binds the mandate fingerprint, so
   this precedes `paper-epoch-start`.
3. **Operator DB path**: keep `data/trading_assistant.db` or adopt the
   runbook's `data/paper.db`. Every command below uses the chosen path;
   mixing paths splits the evidence.
4. **Task account**: dedicated least-privilege account (recommended by the
   runbook) or current user. Dedicated requires the elevated window below.

## 3. The session itself (operational machine, in order)

Every step is in `docs/OPERATIONS_RUNBOOK.md`; this is the ordering with
its gates.

1. **Freeze**: `git pull`, confirm `main = d5fab71` (or the later
   owner-chosen epoch commit), clean worktree. Run the full suite once on
   this exact tree.
2. **Elevated window** (owner, admin shell): create the task account if
   decided; grant "Log on as a batch job" and the runbook's minimal ACLs.
3. **Install operational tasks**: runbook §Windows Task Scheduler —
   `-WhatIf` first, review every resolved path, then install and start the
   boot-triggered tasks manually once. ML shadow tasks only if the shadow
   config exists and ML evidence collection is wanted this epoch.
4. **Verify tasks**: `verify_windows_evidence_tasks.ps1` as the task
   account; then check each task produced real output at least once.
5. **Bootstrap the ledger**: `readiness`, then `ledger-bootstrap --confirm
   bootstrap` (once), then `ledger-reconcile` — runbook §Before starting a
   paper evidence epoch.
6. **Approve the mandate** (decision 2 executed).
7. **Start the epoch**: `paper-epoch-start <epoch-id> --strategy-id ...
   --strategy-version ... --model-id ...` on the frozen commit. From this
   moment the commit, mandate/policy fingerprints, strategy/model IDs, and
   the Alpaca paper account ID are immutable for the epoch.
8. **Run all 5 drills inside the epoch** (runbook §Required drills):
   `kill_switch`, `ambiguous_submission`, `restart_recovery` (via
   `run_fault_drill.py --record-database <db> --operator "<name>"`),
   `recovery-drill`, and `alert-self-test --record-drill`. Store evidence
   under `data/drill_evidence/` (git-ignored).
9. **Confirm green**: `platform-readiness` exits zero;
   `paper-evidence-status <epoch-id>` shows session counting begun.
10. **Let the 60-session clock run.** The pre-epoch informal paper trading
    data remains useful for execution realism but does not count toward
    the mandate's 60-session minimum.

## 4. What must NOT happen in this session

- No live/funded account, credential, or endpoint anywhere.
- No epoch start from a dirty worktree or unmerged branch (the tooling
  refuses; do not work around it).
- No manual edits to evidence tables, ever — a persistent alert is an
  incident, not permission.
- No ML/signal promotion; shadow tasks observe only.
- After the epoch starts: no runtime change on the operational machine
  without `paper-epoch-close` first (model 2) or at all (model 1).
