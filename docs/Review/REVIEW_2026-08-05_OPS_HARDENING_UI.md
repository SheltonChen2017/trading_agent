# Independent review — ops hardening, policy default, UI chrome — 2026-08-05

Audience: repository owner, Claude Code, and future reviewers.

Owner request (three items): apply auto-restart to the operational
scheduled tasks; make the app load `my_policy.json` without retyping it;
rename the title to "Trading Assistant" and modernise the type.

Outcome: **accepted after correction**.

Codex reviewed the working tree before Claude committed it and corrected it
in place on `codex/review-ops-hardening-ui-20260805`. This document holds
the ledger, Claude's counter-review, and the final validation.

## 1. Scope and dispositions

Base: `6d4f9f0` (`main`, post GR-7a / PR #156).
Claude implementation branch name: `user/claude/ops-hardening-and-ui-20260805`
(work was uncommitted at review start).
Review branch: `codex/review-ops-hardening-ui-20260805`.

| Unit | Disposition |
|---|---|
| Claude working-tree submission (policy resolver, CLI/UI wiring, task self-heal + battery guards, HOW_TO_USE / handoff, three new test modules) | accepted after correction (OPSREV-001..006; CROPS-001) |
| Claude counter-review additions (CROPS-001/002) | CROPS-001 accepted and merged into the final tree; CROPS-002 documented open (Watchdog heartbeat remains the crash-loop detector) |

No P0 remains open after correction. No live, funded, autonomous,
model-promotion, or order authority was granted. The active paper epoch on
frozen commit `8a2233c` was not deployed to or altered.

| Area | Risk |
|---|---|
| `assistant/policy.py` — `resolve_policy_path()` | HIGH: decides which policy governs proposals |
| `scripts/run_personal_assistant.py` — `--policy` default | HIGH: same, plus epoch-lineage inputs |
| `scripts/personal_assistant_ui.py` — sidebar default | HIGH (policy), NIL (typography) |
| `scripts/install_windows_operational_tasks.ps1` | MEDIUM: future host installs |
| `scripts/verify_windows_evidence_tasks.ps1` | MEDIUM: install-time gate |

## 2. Issue ledger

| ID | Priority | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| OPSREV-001 | P1 | Resolved | `run_personal_assistant.py` | `--policy` default was `str(resolve_policy_path())`, evaluated at **parser construction**. A `TRADING_ASSISTANT_POLICY` pointing at a missing file therefore raised before argparse existed — bricking `--help` and even an explicit `--policy` that named a valid file. | Lazy `default=None`; resolve after parse. | `test_cli_parser_survives_a_broken_policy_env_and_honors_explicit_policy` |
| OPSREV-002 | P1 | Resolved | `verify_windows_evidence_tasks.ps1` | Self-heal + `IgnoreNew` sets `LastTaskResult=0x800710E0` while the task is still `Running`. Verifier required 0 / 267009, so healthy long-runners would fail `setup_operational_host.ps1`. | Treat `State=Running` as healthy process identity. | Observed live: Running + `0x800710E0` after heal tick; source assertions in resilience tests |
| OPSREV-003 | P2 | Resolved | `install_windows_operational_tasks.ps1` | Heal `-At ((Get-Date).Date.AddMinutes(1))` is a past midnight boundary; existing cycle trigger uses `(Get-Date).AddMinutes(1)`. | Align heal `-At` with cycle convention. | `test_recovery_trigger_cannot_stack_duplicate_instances` |
| OPSREV-004 | P2 | Resolved | `personal_assistant_ui.py` | Broken env var fell back to hard-coded `DEFAULT_POLICY_PATH`, skipping an existing `my_policy.json`. | Continue implicit chain after reporting the broken env. | `test_a_broken_policy_env_var_degrades_visibly_instead_of_crashing` |
| OPSREV-005 | P2 | Resolved | `test_operational_task_resilience.py` | PaperObservation was not bound to battery-cleared short settings. | Explicit pairing assertion. | `test_paper_observation_uses_battery_cleared_short_settings` |
| OPSREV-006 | P1 | Resolved | `run_personal_assistant.py` | After OPSREV-001, handlers that call `load_policy(args.policy)` still saw `None` when invoked after `parse_args()` without `main()` (suite regression on epoch lineage). | `_cli_policy_path(args)` used by `main()` and every `load_policy` call site. | `test_cli_handlers_resolve_none_policy_without_going_through_main`; `test_active_epoch_rejects_changed_runtime_lineage` |
| CROPS-001 | P3 | Resolved | `policy.py` / UI | Env fallback mutated `os.environ` (pop/restore) in a Streamlit render path shared across session threads. | `resolve_policy_path(..., use_env=False)`; UI no longer mutates environ. | `test_use_env_false_skips_the_variable_without_touching_os_environ` |
| CROPS-002 | P3 | Open (documented) | verifier | `State=Running` cannot detect a crash-loop; self-heal makes a looping task look healthier. | No code change — Watchdog DB heartbeat is the correct detector. | Documented only |
| CROPS-003 | P2 | Resolved | `tests/test_policy_path_resolution.py` | OPSREV-006 converted all 13 `load_policy(args.policy)` sites and added a unit test of `_cli_policy_path` itself, but nothing pinned the **invariant**. Since `--policy` defaults to `None`, a newly added handler writing `load_policy(args.policy)` would raise `TypeError` only on the one command that happened to be exercised — which is exactly how the original regression passed a green focused run and failed the full suite. The fix was complete; its coverage was not. | Added `test_every_cli_load_policy_call_goes_through_the_resolver`, an AST walk asserting every `load_policy` call in the CLI takes `_cli_policy_path(args)`. Source-level is correct here: the defect is a wrong *argument* to a correct function, which `load_policy` cannot observe. | Reverse mutation reintroducing the bug at exactly ONE of the 13 sites: DETECTED (the two behavioural tests were also re-proven load-bearing against the helper mutation). Restored and re-verified green. Independently re-reviewed 2026-08-06: shape check tightened and live orphan/duplicate-worker failure mode recorded in `docs/Review/REVIEW_2026-08-06_CROPS003_OPS_FOLLOWUP.md`. |

## 3. Claude counter-review (incorporated)

All five original Codex findings were accepted by Claude. OPSREV-002 was
confirmed empirically against live tasks (`Running` + `0x800710E0`).
CROPS-001 is in the final tree. CROPS-002 remains an honesty note, not a
blocker.

## 4. Compatibility and boundary assessment

- `load_policy()` with no argument still means the committed default —
  suite and library behavior stay machine-independent.
- Named-but-missing explicit/env paths still raise (fail closed toward the
  wrong policy).
- No proposal/approve/size/submit/dismiss path changed.
- Import boundary clean (no `ml`).
- Deploying this to the operational checkout under the active epoch would
  change the resolved policy fingerprint (`my_policy.json` vs the epoch's
  bound `default_policy.json`) and correctly refuse observation until the
  owner rebinds — see SESSION_HANDOFF §2.

## 5. Quality score

Submitted quality: **7.5/10**.
Corrected quality: **9.4/10**.

Core design was sound: explicit precedence, personal-over-default only for
entry points, visible active filename, self-heal + battery guards, and
leaving bare `load_policy()` alone. The material misses were the eager
argparse default, the verifier/self-heal interaction, and the post-lazy
handler `None` path.

## 6. Validation

Review machine: Windows, Python 3.13.

- Focused after final correction: **25 passed**
  (`test_policy_path_resolution`, `test_ui_chrome`,
  `test_operational_task_resilience`,
  `test_active_epoch_rejects_changed_runtime_lineage`).
- Exact final tree: **2869 passed / 1 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.

No test contacted a funded account. Typography was not visually inspected.

Self-heal recovery was originally recorded here as unproven end to end,
because deliberately terminating a live task to watch it return was
declined by the sandbox. **It has since been observed in production on the
review host, unplanned.** At 18:28 local, OrderMonitor and Watchdog were
running as the PIDs started 16:56:25. At 18:51 both were running as new
PIDs started **18:48:25** — they died in that window and the 5-minute
repeating trigger restored both within its interval, with the tasks back
to `State=Running`. That is the whole mechanism exercised for real:
death, tick, restart.

Two caveats keep this honest. The cause of death was not captured (the
host has been losing console-hosted processes to `0xC000013A` all
session), and recovery was observed once, not measured for reliability.
What is now established is that the trigger does restart a dead
long-runner unattended — which is exactly what the logon-only
configuration could not do.

## 7. What is deliberately not claimed

- Visual QA of the typography block.
- Reliability of self-heal beyond the single observed recovery, and the
  cause of the deaths that keep occurring on this host.
- Resolution of the open owner decision to re-bind `paper-epoch-001` to
  `my_policy.json` (handoff §2 options A/B).
- Any change to the frozen operational checkout at `8a2233c`.
