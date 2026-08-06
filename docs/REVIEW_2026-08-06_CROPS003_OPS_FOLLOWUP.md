# Independent review — CROPS-003 follow-up (ops hardening) — 2026-08-06

Audience: repository owner, Claude Code, and future reviewers.

Outcome: **accepted after correction**.

Claude's tip `6f9a82a` ("Pin the CLI policy-resolution invariant and record
observed self-heal") landed on `main` via PR #157 without a separate Codex
pass. This review covers that commit and the live-host observations it
depends on.

## 1. Reviewed commits

Base: `dafaec6` (Codex ops-hardening acceptance).
Claude follow-up: `6f9a82a`.
Merge: `37d3fca` (PR #157).
Review branch: `codex/review-crops003-ops-followup-20260806`.

| Commit | Disposition |
|---|---|
| `6f9a82a` Pin the CLI policy-resolution invariant and record observed self-heal | accepted after correction (CCROPS-001..003) |

No live, funded, autonomous, model-promotion, or order authority was granted.
Operational checkout remains frozen at `8a2233c` (verified this session).

## 2. Issue ledger

| ID | Priority | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| CROPS-003 | P2 | Resolved (accepted) | `tests/test_policy_path_resolution.py` | OPSREV-006 converted call sites but did not pin the invariant against a future `load_policy(args.policy)`. | AST guard (Claude). | Green on current tree; reverse-mutation claim accepted as described. |
| CCROPS-001 | P2 | Resolved | same AST guard | Guard accepted any `_cli_policy_path(...)` expression and did not require the argument `args`, so `_cli_policy_path(other)` would pass. | Require exact `_cli_policy_path(args)`; floor of 13 sites. | Strengthened test. |
| CCROPS-002 | P1 | Resolved (code; deploy deferred) | OrderMonitor / Watchdog | Live host 2026-08-06 ~09:35: two `monitor-orders` and two `watchdog` processes against the same DB despite `MultipleInstances=IgnoreNew`. IgnoreNew only covers scheduler-tracked instances; orphaned console processes let a heal/logon start a second worker. Claude's "kill-and-recover verified" claim understated this failure mode. | `assistant/process_singleton.py` + acquire in `command_monitor_orders` and `run_operations_watchdog.main`. | Unit tests + CLI wiring refusal test. **Not deployed** mid-epoch. |
| CCROPS-003 | P3 | Resolved | `docs/SESSION_HANDOFF.md` | §6 still said "Push/PR of ops-hardening when owner asks" after PR #157 merged; CROPS-003 omitted from outcome summary. | Handoff rewritten for post-merge / post-this-review state. | Doc review. |

## 3. Machine-local observations (this session)

Verified on the review host:

- Operational checkout: `8a2233c`, clean `main`.
- Tasks: OrderMonitor/Watchdog `Running`; PaperObservation/OperationsCycle `Ready`.
- **Duplicate workers present:** PIDs 7804+22708 (`monitor-orders`) and 5180+22716 (`watchdog`), started 09:34:59 and 09:35:08 against `data/trading_assistant.db`.
- Task XML confirms `MultipleInstancesPolicy=IgnoreNew` and the 5-minute heal trigger.

Owner action recommended (manual, not performed by this review): stop the
duplicate processes / restart the two long-runner tasks so only one pair
remains, then deploy the singleton fix only at the next epoch boundary
(or under an explicit owner deploy authorization).

## 4. Quality score

Claude follow-up (`6f9a82a`) submitted: **8.5/10**.
After Codex correction: **9.4/10**.

CROPS-003 was the right invariant and correctly used an AST test. The
material miss was treating Task Scheduler IgnoreNew as process uniqueness
while documenting recovery as verified.

## 5. Validation

Review machine: Windows, Python 3.13.

- Focused: **32 passed**.
- Exact final tree: **2875 passed / 1 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.

No test contacted a funded account. Process singleton is in the development
tree only; operational checkout stays at `8a2233c`.
