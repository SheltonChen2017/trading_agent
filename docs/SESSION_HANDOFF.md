# Development session handoff

Prepared: 2026-08-05 (late evening), after Codex independently reviewed and
corrected Claude's owner-requested operations hardening / policy-default /
UI chrome work on `codex/review-ops-hardening-ui-20260805`.

Code changes are DEV-SIDE ONLY: nothing was deployed to the frozen
operational checkout. The scheduled-task settings on THIS machine were
changed earlier in place (triggers and battery guards only — no task
command line, no checkout, no database, no epoch record).

Audience: Codex, Claude Code, and the repository owner after a computer,
model, or session change. This file completely replaces the prior handoff.

## 1. Standing state: THE EPOCH (do not disturb)

`paper-epoch-001` ACTIVE since 2026-08-05T18:27Z on frozen commit
`8a2233c`. Operational checkout stays on that commit until
`paper-epoch-close`. Never deploy development commits mid-epoch.

Session 1 of 60 recorded (`paperobs-94882d5da9668087e99355c5`, captured
2026-08-05T21:42:57Z). Exactly one observation exists for that session
date; the 16:30 scheduled run correctly deduplicated against the earlier
manual capture.

## 2. OPEN OWNER DECISION — the epoch is bound to the wrong policy file

Measured, not inferred:

| Thing | Policy | Fingerprint |
|---|---|---|
| `paper-epoch-001` lineage | `assistant/default_policy.json` | `66dd70e1…d759f` |
| What the owner actually trades under | `assistant/my_policy.json` | `4a942cbc…f01ea` |

`default_policy.json` sets `allow_new_positions=False`. The epoch record
therefore claims its evidence is being collected under a policy that
forbids the very buys the account is making — the owner has been typing
`my_policy.json` into the sidebar each session, which is what this round's
change was requested to automate.

This predates the change and is not caused by it. `paper-epoch-start`
bound whatever `--policy` resolved to (the committed default), and the
owner's manual sidebar override was never reflected in the lineage.

The runtime lineage check fails CLOSED, which is why nothing broke:
`_active_runtime_lineage()` recomputes the policy fingerprint on every
`paper-observation` and refuses when it differs, rather than absorbing the
difference into the evidence.

Consequence of this round's change, once merged AND deployed: the resolved
default becomes `my_policy.json`, so `paper-observation` would compute
`4a942cbc…` against a recorded `66dd70e1…` and exit with "Active evidence
lineage differs from the current runtime; close this epoch and start a new
one." That is the control working as designed.

Two ways forward, owner's call:

- **A (recommended): re-bind now.** `paper-epoch-close paper-epoch-001`,
  deploy the merged commit to the operational checkout, then
  `paper-epoch-start paper-epoch-002`. Cost is one session — today's. The
  lineage then describes the policy actually governing trades from session
  1 onward, and epoch-start/observation agree because both resolve the
  same file.
- **B: keep the epoch.** The operational checkout stays at `8a2233c`, so
  this change has no operational effect until the next epoch boundary. The
  lineage keeps naming `default_policy.json` for the epoch's full 60
  sessions while trades are governed by `my_policy.json`.

Do not deploy this branch to the operational checkout under option B.

## 3. This round's outcome

**Accepted after independent review and correction.**

| Area | Change |
|---|---|
| `assistant/policy.py` | `resolve_policy_path(explicit=None, *, use_env=True)`: explicit → env → `my_policy.json` → `default_policy.json`. Named missing paths raise; only 3→4 falls back. `use_env=False` continues the chain without mutating `os.environ` (CROPS-001). |
| `scripts/run_personal_assistant.py` | `--policy` default `None`; `_cli_policy_path()` binds after parse and inside every handler `load_policy` call (OPSREV-001/006). |
| `scripts/personal_assistant_ui.py` | Sidebar seeded from resolver; active filename captioned; broken env warns and continues the implicit chain; title "Trading Assistant"; system-local typography (no webfont). |
| `scripts/install_windows_operational_tasks.ps1` | 5-min self-heal for long-runners; battery guards cleared; heal `-At` uses `(Get-Date).AddMinutes(1)`. |
| `scripts/verify_windows_evidence_tasks.ps1` | `State=Running` treated as healthy (self-heal `0x800710E0` no longer false-fails installs). |

`load_policy()`'s own default is deliberately UNCHANGED.

Review ledger: `docs/REVIEW_2026-08-05_OPS_HARDENING_UI.md`
(OPSREV-001..006, CROPS-001 resolved; CROPS-002 documented open).

Claude quality: **7.5/10 submitted; 9.4/10 corrected**.

## 4. Machine state changed on this host (not in git)

The two console-hosted tasks were found stopped, both with last result
`3221225786` (`0xC000013A`, STATUS_CONTROL_C_EXIT) — their windows were
closed. Only an `AtLogOn` trigger existed, so nothing restarted them;
`RestartCount` does not cover that exit because Task Scheduler treats a
console close as stopped rather than failed.

Applied via `C:\git\harden_trading_tasks_elevated.ps1` (elevated,
idempotent):

- OrderMonitor and Watchdog gained a 5-minute repeating trigger
  (`MultipleInstances=IgnoreNew` makes a tick against a healthy task a
  no-op);
- all four tasks had `DisallowStartIfOnBatteries` and
  `StopIfGoingOnBatteries` cleared. **This host has a battery**, so
  PaperObservation would have silently skipped the 16:30 capture whenever
  the machine was unplugged — an evidence gap indistinguishable afterwards
  from a defect.

Verified after: OperationsCycle/OrderMonitor/Watchdog `Running`,
PaperObservation `Ready`, next heal tick scheduled, no task interrupted.
Live tasks after a heal tick report `LastTaskResult=0x800710E0` while
`State=Running` — the verifier correction matches that observation.

NOT verified end to end: an actual kill-and-recover cycle.

## 5. Validation (exact final tree)

- Focused: **25 passed**.
- Full suite: **2869 passed / 1 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.

## 6. What is next

1. Owner decision on §2 (epoch re-binding A vs B).
2. Push/PR of `codex/review-ops-hardening-ui-20260805` when the owner asks.
3. Roadmap next: GR-7b / GR-7c / GR-6, or the GR-7d owner decision — this
   ops/UI round does not reorder the action plan.

## 7. Non-negotiable boundaries

- Paper only; never deploy mid-epoch.
- Reporting may not propose/approve/size/submit/dismiss.
- Incomplete/unverified reports must say so in the artifact.
- Wash-sale output stays advisory.
- Which policy file governs must always be visible on screen.
