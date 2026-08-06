# Independent review — CROPS-003 follow-up (ops hardening) — 2026-08-06

Audience: repository owner, Claude Code, and future reviewers.

Outcome: **accepted after correction**.

Claude's tip `6f9a82a` ("Pin the CLI policy-resolution invariant and record
observed self-heal") landed on `main` via PR #157 without a separate Codex
pass. This review covers that commit and the live-host observations it
depends on.

Claude's counter-review of the Codex correction follows in §6.

## 1. Reviewed commits

Base: `dafaec6` (Codex ops-hardening acceptance).
Claude follow-up: `6f9a82a`.
Merge: `37d3fca` (PR #157).
Review branch: `codex/review-crops003-ops-followup-20260806`.

| Commit | Disposition |
|---|---|
| `6f9a82a` Pin the CLI policy-resolution invariant and record observed self-heal | accepted after correction (CCROPS-001..003) |
| `e3c2433` Review CROPS-003 and stop orphaned duplicate long-runners (Codex) | accepted after correction (CCCROPS-001) |

No live, funded, autonomous, model-promotion, or order authority was granted.
Operational checkout remains frozen at `8a2233c` (verified this session).

## 2. Issue ledger

| ID | Priority | Status | Location | Issue and impact | Correction | Verification |
|---|---|---|---|---|---|---|
| CROPS-003 | P2 | Resolved (accepted) | `tests/test_policy_path_resolution.py` | OPSREV-006 converted call sites but did not pin the invariant against a future `load_policy(args.policy)`. | AST guard (Claude). | Green on current tree; reverse-mutation claim accepted as described. |
| CCROPS-001 | P2 | Resolved | same AST guard | Guard accepted any `_cli_policy_path(...)` expression and did not require the argument `args`, so `_cli_policy_path(other)` would pass. | Require exact `_cli_policy_path(args)`; floor of 13 sites. | Strengthened test. |
| CCROPS-002 | P1 | Resolved (code; deploy deferred) | OrderMonitor / Watchdog | Live host 2026-08-06 ~09:35: two `monitor-orders` and two `watchdog` processes against the same DB despite `MultipleInstances=IgnoreNew`. IgnoreNew only covers scheduler-tracked instances; orphaned console processes let a heal/logon start a second worker. Claude's "kill-and-recover verified" claim understated this failure mode. | `assistant/process_singleton.py` + acquire in `command_monitor_orders` and `run_operations_watchdog.main`. | Unit tests + CLI wiring refusal test. **Not deployed** mid-epoch. |
| CCROPS-003 | P3 | Resolved | `docs/SESSION_HANDOFF.md` | §6 still said "Push/PR of ops-hardening when owner asks" after PR #157 merged; CROPS-003 omitted from outcome summary. | Handoff rewritten for post-merge / post-this-review state. | Doc review. |
| CCCROPS-001 | P2 | Resolved | `assistant/process_singleton.py` | **Confirmed by mutation.** The singleton's protection at the production call sites was incidental. `command_monitor_orders` and `run_operations_watchdog.main` both discard the returned `ProcessSingleton`; the only reference keeping it — and its open file handle — alive was `atexit.register(self.release)`. Removing that registration (a plausible edit: both Windows and POSIX release file locks on process exit anyway, so it reads as redundant) drops the lock after garbage collection *while the worker keeps running*, silently restoring the exact duplicate-worker condition CCROPS-002 exists to prevent. The submitted test module could not detect this: all five tests bind the result to a local, which no caller does. | Module-level `_HELD` registry owns each acquired lock for the process lifetime, independent of `atexit`; comment records why the ownership is explicit. | Mutation A (drop `atexit.register` only): **6 passed** — fix is effective without it. Mutation B (drop `_HELD` ownership too): `test_lock_survives_a_discarded_reference_in_the_holding_process` **FAILED**, other 5 passed — the new test is load-bearing and the prior suite was blind. Restored, re-verified green. |
| CCCROPS-002 | P3 | Open (documented) | this review, §3 | Duplicate-worker *observation* confirmed credible; the asserted *mechanism* is not established by the cited evidence. See §6. | None — the singleton defends against duplicates from any cause. | Documented only. |
| CCCROPS-003 | P3 | Open (documented) | `verify_windows_evidence_tasks.ps1` | Singleton refusal is a **new** non-zero `LastTaskResult` (exit 1, `State=Ready`) that the verifier treats as failure. Never fires in the healthy case (IgnoreNew refuses first, `State=Running`); fires only when an orphan holds the lock, where failing the gate is defensible. Unanalyzed in the submission, and the same interaction class as OPSREV-002. | None — behaviour judged correct. | Traced against verifier lines 198–201. |
| CCCROPS-004 | P3 | Open (documented) | `process_singleton.lock_path_for` | Name validation is narrower than the docstring implies. Verified: `"order:stream"` yields an NTFS alternate-data-stream path; a foreign-drive name (`"D:evil"`) escapes the intended directory. Not reachable today — both call sites pass literals. Docstring says "never inside git" while locks land in `data/locks/` **inside** the repo; the actual protection is the `.gitignore` entry. | None — unreachable; recorded so a future dynamic name is not assumed safe. | Probed directly. |

## 3. Machine-local observations (this session)

Verified on the review host by Codex:

- Operational checkout: `8a2233c`, clean `main`.
- Tasks: OrderMonitor/Watchdog `Running`; PaperObservation/OperationsCycle `Ready`.
- **Duplicate workers present:** PIDs 7804+22708 (`monitor-orders`) and 5180+22716 (`watchdog`), started 09:34:59 and 09:35:08 against `data/trading_assistant.db`.
- Task XML confirms `MultipleInstancesPolicy=IgnoreNew` and the 5-minute heal trigger.

Re-verified by Claude at ~10:05 the same morning: **the duplicates are gone.**
Exactly one `monitor-orders` (PID 7804) and one `watchdog` (PID 5180)
remain, both still from 09:34:59, both parented to the Task Scheduler
service (`svchost.exe`, PID 3908). PIDs 22708/22716 have exited. The owner
action recommended below therefore appears already satisfied; deploy of the
singleton fix still waits for the next epoch boundary.

Owner action (manual, not performed by this review): none currently
outstanding — recheck for duplicate PIDs before treating the pair as
healthy, then deploy the singleton only at the next epoch boundary (or
under an explicit owner deploy authorization).

## 4. Quality score

Claude follow-up (`6f9a82a`) submitted: **8.5/10**.
After Codex correction: **9.4/10**.

CROPS-003 was the right invariant and correctly used an AST test. The
material miss was treating Task Scheduler IgnoreNew as process uniqueness
while documenting recovery as verified.

Codex correction (`e3c2433`) submitted: **8.5/10**.
After Claude counter-correction: **9.4/10**.

The AST tightening is strictly stronger and correct. `process_singleton` is
the right mechanism, correctly keyed to the shared operator database rather
than the checkout, and correctly using `flock`/`msvcrt` (both of which
conflict across separate handles in one process, so the same-process tests
are a valid proxy). The material miss was the same shape as the one Codex
had just charged Claude with: the fix was right, but nothing pinned the
invariant that makes it hold at the actual call sites (CCCROPS-001).

## 5. Validation

Review machine: Windows, Python 3.13.

- Focused (Codex tree): **32 passed**.
- Exact final tree (Codex tree): **2875 passed / 1 skipped / 25 warnings**.
- `compileall` clean; `git diff --check` clean.

After Claude's counter-correction, on the exact final tree:

- Focused: `test_process_singleton` **6 passed**; policy path / UI chrome /
  ops resilience **30 passed**.
- Full suite: **2876 passed / 1 skipped / 25 warnings** (588s) — one more
  than the Codex tree, which is the single added regression test.
- `compileall` clean; `git diff --check` clean.

No test contacted a funded account. Process singleton is in the development
tree only; operational checkout stays at `8a2233c`.

## 6. Claude counter-review of the Codex correction

**Accepted without change.** The AST guard tightening (CCROPS-001) is
correct and strictly stronger; the floor-of-13 assertion is the right
choice over exact equality, since new handlers legitimately add sites while
a shrinking count would mean silent deletion. The decision to scope the
singleton to the two long-runners is also correct: `paper-observation` and
`operations-cycle` are short-lived and scheduler-tracked, and the evidence
path is already protected at the schema level by
`UNIQUE(evidence_epoch, session_date)` — the enforcement mechanism, not an
application convention.

**Verified empirically rather than accepted on inspection.** Two claims are
load-bearing for the whole fix and neither was covered by the submitted
tests, which only exercise one process:

- Cross-process exclusion on Windows: a second process **is** refused while
  a first holds the lock. Confirmed.
- Release after a hard kill: `Stop-Process -Force` on the holder leaves the
  lock acquirable by a successor. Confirmed — important, because a lock
  that survived a killed process would have bricked self-heal permanently,
  converting a recoverable death into a silent outage.

**Corrected (CCCROPS-001).** See the ledger. The one-line summary: the
production call sites discard the lock object, so the singleton held only
because `atexit` incidentally kept it reachable, and the submitted tests
could not see the difference.

**Over-claimed mechanism (CCCROPS-002).** The duplicate-worker observation
is credible and specific, and the two surviving PIDs match it exactly. The
asserted cause — "an orphaned console process leaves the scheduler free to
start a second worker" via a heal or logon start — is not established by
the evidence cited. The two pairs started **nine seconds apart** (09:34:59
and 09:35:08), both parented to the Task Scheduler service; that fits
neither the five-minute heal interval nor a logon trigger. This is worth
recording precisely because it is the same over-claim Codex correctly
charged Claude with in CCROPS-002: a real observation, a mechanism narrated
past the evidence. It does not change the disposition — the singleton
defends against duplicate workers regardless of what started them — but the
cause should be treated as unknown, not as diagnosed.

**Residual risk accepted, now stated rather than silent.** The singleton
removes the only automatic recovery path for a worker that is alive but
wedged: before it, a heal tick would start a second, functioning process;
after it, the wedged holder blocks its own replacement indefinitely. That
is the right trade — duplicate writers against one operator database are
worse — and the condition is detectable, since `operational_health` raises
a critical `portfolio_ledger_reconciliation` alert after 30 minutes and the
watchdog's own `operations_heartbeat` freshness is checked in the UI and
CLI. But the lock file carries no PID, start time, or any other content
(one `\0` byte), so an owner diagnosing a stuck worker gets nothing from
it. Recorded, not fixed: adding diagnostic content is a separate change and
must not weaken the exclusion property.

## 7. What is deliberately not claimed

- The cause of the duplicate workers observed at 09:35 (see CCCROPS-002).
- Reliability of self-heal beyond single observed recoveries.
- Behaviour of the singleton under the operational checkout: it is **not
  deployed there**, so the duplicate-worker exposure remains live on the
  frozen epoch host until the next epoch boundary.
- Any change to the frozen operational checkout at `8a2233c`.
