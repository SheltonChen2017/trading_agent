# Independent review: SHW-4 stream start (and interleaved rounds)

Status: **accepted after correction**. Prepared: 2026-08-19. Reviewer:
Cursor Grok 4.6. Isolated worktree
`C:\git\customizedAgent\trading_agent-review-shw4` on
`user/cursor/review-shw4-stream-start-20260819`. No QuantConnect run.
Operator DB `data/trading_assistant.db` was not opened. Shadow DB
`C:/git/trading_agent_operational/data/shadow_overlay.db` was opened
SQLite `mode=ro` only. No stream register/observe/close, no epoch
roll, no real scheduled-task install, no QC, no orders. Overlay
installer `-WhatIf` only.

The requested range listed 11 commits; `git log --reverse --oneline
a384be7..a6a690c` contains **12**. All 12 are dispositioned.

## 1. Snapshot

| Item | Value |
|---|---|
| Requested range | `a384be7..a6a690c` |
| Base | `a384be7b3c332dc40f9996fd2706ab4c01fd0d3d` (SHW-3 implementation head previously reviewed) |
| Review head | `a6a690c29b5eefef7d227d8fde5b4990cad6da19` |
| Implementation branch | `origin/user/claude/shw4-stream-start-20260819` |
| Review branch | `user/cursor/review-shw4-stream-start-20260819` from that exact head |
| Isolation | sibling worktree; shared checkout left on the implementation branch |

Fetched. Temporary SHW3-001 reverse mutation restored. Probe script
deleted, not committed.

**Out-of-range operational fact:** `origin/main` is already
`f63ba89` (`Merge pull request #267`), parents `08cec4c` + `a6a690c`.
`f63ba89^{tree}` equals `a6a690c^{tree}`. This review still
dispositions the named range. It does **not** execute or authorize the
epoch roll or a real task install. Precondition 4 of the roll plan
(reviewed mainline deploy target) is satisfied for the `a6a690c` tree
once this review is recorded; the merge itself happened before this
independent pass finished.

## 2. Verdict

**Accept all 12 commits after restoring the Stage 2 PEAD action-plan
row that merge `039e5cf` dropped (SHW4-001) and aligning the stale
ALLOCATION-POLICY row with the already-scheduled APQ-1 decision
(SHW4-002).** Product, config, freeze, installer, and live-stream
claims in the shadow DB check out. Daily weekday triggers plus runner
idempotency are a sound substitute for a native monthly trigger.

No P0. No P1. One P2 (closed in this review). Three P3 remain open.

This review does **not** install overlay tasks, advance the operational
clone, close paper-epoch-005, or start paper-epoch-006.

## 3. Per-commit dispositions

| Commit | Disposition | Verification |
|---|---|---|
| `d0912e0` Freeze defensive-carry gates; schedule APQ-1; close Stage 2 PEAD | **Accepted.** Load-bearing freeze. | Preregistration at HEAD has **zero** `[TO FREEZE]` tokens. Frozen values match the owner-accepted set: 15% relative maxDD, 10% relative ES, 80% upside-capture floor, ≥8 folds, 2/3-of-folds **and** block-bootstrap p<0.05 on the ES delta, 24 prospective months. Freeze `2026-08-19 10:14 -0700` precedes config `3c9105d` (`10:39`) and DB `registered_at` `2026-08-19T17:39:34Z` (`10:39` PDT). Section 6 still leaves calendar window/fold **boundaries** as study-start mechanics, not tunables. |
| `9e8f46d` Host decision: dedicated shadow DB, operational clone post-advance | **Accepted** as a record. | Matches the live path `C:/git/trading_agent_operational/data/shadow_overlay.db`. Operator DB was not opened in this review. |
| `9cb4bb5` Independent SHW-3 review record (this reviewer's prior pass) | **Accepted** for completeness. | Report of `553da76..a384be7`. Wall-clock `a384be7` (`09:49`) predates freeze `d0912e0` (`10:14`). Git ancestry: `a384be7` is **not** an ancestor of `d0912e0` (parallel branches); that does not undermine the snapshot claim. |
| `15b9f04` Close SHW3-001: sufficiency reads closed epochs | **Accepted.** Independently mutation-verified in this session. | `command_sufficiency` loads the registration without `_registration_or_refuse`; `observe`/`mature` still use that gate. `test_sufficiency_still_reports_a_closed_epoch` **green** (23 overlay-runner tests passed). Reverse mutation (sufficiency calls `_registration_or_refuse`) **red**: exit 1, stderr `status is 'closed'; a closed epoch never accepts new observations`. Restored; test green again. |
| `8a543a8` SHW-3 counter-review; SHW3-001 fixed, SHW3-002 discharged | **Accepted.** Chronology holds. | Review snapshot `a384be7` predates freeze `d0912e0`. No draft registration: DB `code_commit` is `3c9105d` after the freeze. SHW3-002 discharge is event-correct. |
| `bea5310` Merge PR #265 | **Accepted.** | Parents `553da76` + `8a543a8`. `git diff bea5310^2 bea5310` empty: merge tree equals second parent. |
| `039e5cf` Merge origin/main into dc-gate-freeze | **Accepted after correction (SHW4-001/002).** | Parents `9e8f46d` + `bea5310`. Handoff: parent1 had the decision batch numbered `7aq`; parent2 had `7ap`–`7ar`; merge keeps `7ap`–`7ar` and renames the decision batch to `7as`. **No handoff section lost.** Action plan: parent1's `STAGE2-PEAD-CLOSED-20260819` row is **absent** from the merge tree and from `a6a690c` (`git grep` empty; pickaxe only `d0912e0`). Handoff `7as` still recorded the PEAD close, so the decision was not deleted from narrative, but the sequencing table lost it. Restored in this review. ALLOCATION-POLICY row still said UNSCHEDULED while POST-CLOSURE said APQ-1 SCHEDULED (present on parent1 too); aligned here (SHW4-002). |
| `08cec4c` Merge PR #266 | **Accepted.** | Parents `bea5310` + `039e5cf`. `git diff 08cec4c^2 08cec4c` empty. |
| `3c9105d` Committed defensive-carry stream config | **Accepted.** | Python check: `universe_members == sorted(config.UNIVERSE)` (104, unique), `carry_members == sorted(["GLD","IEF","SHY","TLT"])`, overlap empty, `carry_weight=="0.20"`, `band_fraction=="0.25"`, `required_observation_count==24`. |
| `c948283` Record SHW-4 sub-step 1: stream is live | **Accepted.** Live claims re-verified read-only. | See §5. |
| `16ebb46` Paper-task pinning finding and sub-step-2 options | **Accepted.** Pinning claim independently confirmed. | `scripts/install_windows_operational_tasks.ps1` sets `WorkingDirectory = $resolvedRepository` on every paper action; no `git rev-parse` / commit pin in task arguments. Advancing the clone changes what paper-epoch-005 executes. Overlay installer uses the same WorkingDirectory pattern (intentional after the planned roll). |
| `a6a690c` Overlay shadow scheduler installer | **Accepted.** | Compared to `install_windows_ml_shadow_tasks.ps1`: elevation + Store-alias (zero-byte reparse) preconditions; `SkipElevationCheck:$WhatIfPreference`; WhatIf returns planned objects and **returns before** `New-ScheduledTask*` / `Register-ScheduledTask`; exact-name `Get-InstalledTaskExact` post-check; `RunLevel Limited`. Default names `TradingAgent-Overlay-Shadow-{Observe,Mature,Sufficiency}` only. `-WhatIf` with a non-zero `cmd.exe` stand-in produced those three planned rows and did not create a scheduled task (`Get-ScheduledTask` empty for Observe). Store-alias `WindowsApps\python.exe` throws before preview. Daily weekday 17:45/17:55/18:05 ET: `observe` targets the latest **completed month-end session**, not “today is month-end”, prints `up to date` when that cycle exists, and writes gap refusal rows for missed month-ends — sound for a monthly cadence on weekday triggers (`StartWhenAvailable` covers host-off). Comment “NEVER touches Paper/ML-Shadow” is default-prefix only (SHW4-004). |

## 4. Reverse mutation (SHW3-001)

| Mutation | Result |
|---|---|
| `command_sufficiency` uses `_registration_or_refuse` again | `test_sufficiency_still_reports_a_closed_epoch` **RED** (exit 1, closed-epoch write-gate message). Restored. Test **GREEN**. Overlay-runner suite **23 passed**. |

## 5. Live stream (shadow DB, read-only)

`file:C:/git/trading_agent_operational/data/shadow_overlay.db?mode=ro`

| Claim | Observed |
|---|---|
| Stream / epoch | `defensive-carry` / `overlay-epoch-001`, `status=shadow` |
| `registered_at` | `2026-08-19T17:39:34.462176+00:00` (after freeze) |
| Registration hash | `39fca6264e299d46a9d772675ac93f5a033d5a38504ca1436efcb198da4be64e` (prefix `39fca6264e29` matches the record) |
| `code_commit` | `3c9105d5bd4740377390ef258c4e5b5ae89e64cc` |
| Prereg SHA in DB | `5479d6b6459a0b6d6204f92732b5f55e7b448ec5bbc0e73616785bd59cea6a96` |
| Baseline | `2026-07-31`, `available=1`, levels 100.0 / 100.0 / 100.0, carry weight 0.2 |
| Observation hash | `56bfcd3cf351b02d31792adf52745807fd9ba0c11924ea2b38537f03916ea880` (prefix `56bfcd3cf351b02d` matches) |
| Outcomes | 0 (correct: August has not been observed, so July cannot mature) |

Prereg SHA recomputed two ways (SHW4-003):

- Working-tree bytes at HEAD / `3c9105d` checkout: **`5479d6b6459a…`** (5549 bytes, CRLF) — **matches the registration**.
- `git show 3c9105d:docs/research/DEFENSIVE_CARRY_2026-08-18_PREREGISTRATION.md`: **`96fc515cdf0f…`** (5446 bytes, LF). Register hashes `Path.read_bytes()` of the checkout, not the git blob. Internally consistent on this Windows host. A Linux `git show \| sha256sum` will not match the DB.

Carry/universe/weight/band/required on the registration row match the frozen config.

## 6. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SHW4-001 | P2 | Closed in this review | `039e5cf` | `docs/Archive/Plans/ACTION_PLAN_2026-08-02.md` | Owner-closed Stage 2 PEAD row `STAGE2-PEAD-CLOSED-20260819` present on `d0912e0` disappeared in the conflict-resolution merge. The go-to plan could be read as leaving Stage 2 open. | `git grep STAGE2-PEAD` hits `d0912e0` only in the range; empty at `039e5cf` and `a6a690c`. Handoff `7as` still narrates the close. | Action plan is the sequencing authority; a closed research track must not vanish from the table. | Restored the `d0912e0` row (plus a one-line restore note) on the review branch. | `git grep STAGE2-PEAD HEAD` after this commit. |
| SHW4-002 | P3 | Closed in this review | `d0912e0` / `039e5cf` | same file, ALLOCATION-POLICY row | POST-CLOSURE said APQ-1 SCHEDULED; ALLOCATION-POLICY still said UNSCHEDULED / APQ-0 incomplete. | Both strings present at `a6a690c`. | Two authoritative rows must not disagree on whether APQ-1 is scheduled. | ALLOCATION-POLICY status rewritten to SCHEDULED, pointing at POST-CLOSURE for serial order. | Read the two rows. |
| SHW4-003 | P3 | Open | `3c9105d` / register | `run_overlay_shadow.py` `_registration_contract` | Bound prereg SHA is checkout CRLF, not the git blob of the freeze commit. Cross-platform `git show` verification fails. | 5479d6 vs 96fc51 above. | Confirmation scripts must hash the same bytes register hashed, or they will refuse a valid stream. Do **not** re-register the live epoch to change the hash. | Document; hash-normalize (LF) only in a **new** named preregistration/epoch. | Hash pair above. |
| SHW4-004 | P3 | Open | `a6a690c` | `install_windows_overlay_shadow_task.ps1` `-TaskPrefix` | Comment claims the installer NEVER touches `TradingAgent-Paper-*` or `TradingAgent-ML-Shadow-*`. Default prefix is safe; `-TaskPrefix` is unconstrained and `-Force` would replace whatever names it builds. Same pattern as the ML/paper installers. | Param default `TradingAgent-Overlay-Shadow`; no denylist. WhatIf with default prefix listed only Overlay-Shadow-* names. | The safety claim is operational convention, not an enforcement. A hostile or mistaken prefix could clobber paper tasks. | Optional denylist of `TradingAgent-Paper` / `TradingAgent-ML-Shadow` prefixes. | Not blocking default install. |

## 7. Explicit non-findings

- Sufficiency on a closed epoch is a read; observe still refuses (mutation + test).
- Config members and frozen 0.20 / 0.25 / 24 match.
- WhatIf is data-only; this session did not call `Register-ScheduledTask` for a real install.
- Weekday daily triggers relying on `up to date` + gap rows are sound for monthly observation.
- Duplicate `## 7al` / `## 7an` / `## 7ao` headings pre-exist both merge parents.
- ML output still has no order authority. Overlay runner remains observation-only.

## 8. What this review does not authorize

Owner-present epoch roll (disable Paper tasks, close paper-epoch-005,
deploy into the operational clone, start paper-epoch-006, drills,
re-enable). Real overlay scheduled-task install. Any funded/live
brokerage action. Gate evaluation of the defensive-carry composite.
APQ-1 code start (scheduled, still after SHW-4 automation).
