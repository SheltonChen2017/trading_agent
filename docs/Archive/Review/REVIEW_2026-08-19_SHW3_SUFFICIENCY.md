# Independent review: SHW-3 sufficiency reporting

Status: **accepted**. Prepared: 2026-08-19. Reviewer: Cursor Grok 4.6.
No QuantConnect run. No operator-database open. No gate freeze. No
product correction in this review (two P3s left open).

## 1. Snapshot

| Item | Value |
|---|---|
| Requested range | `553da76..a384be7` |
| Base | `553da76fa04ec5a8588f95c531a749f05d8fbd65` (PR #264) |
| Review head | `a384be7b3c332dc40f9996fd2706ab4c01fd0d3d` |
| Implementation branch | `origin/user/claude/shw3-sufficiency-20260819` |
| Review branch | `user/cursor/review-shw3-sufficiency-20260819` from that exact head |
| Isolation | sibling worktree `trading_agent-review-shw3`; shared checkout left on Claude's freeze branch |

Fetched. Both commits in
`git log --reverse --oneline 553da76..a384be7` are dispositioned.
Temporary reverse mutations restored; the implementation tree was not
modified on the shared checkout.

## 2. Verdict

**Accept both commits.** The `sufficiency` subcommand emits the
section-6 count fields only: observation unit, preregistered required
count, independent matured count, MET/NOT_MET, insufficiency reasons,
and an explicit statement that gate evaluation is a separate
owner-authorized pass. The required count is a registration contract
field with no universal default. A drifted live config refuses with a
`shadow_overlay` alert. The success path is read-only against the
database.

**Do not start SHW-4** from this review. Defensive-carry `[TO FREEZE]`
gates remain unfrozen. Example `required_observation_count: 24` is a
placeholder, not an owner freeze.

No P0. No P1. No P2. Two P3.

## 3. Per-commit dispositions

| Commit | Disposition | Verification |
|---|---|---|
| `4c66406` SHW-3: sufficiency reporting | **Accepted** with SHW3-001/002. | `required_observation_count` is a required positive int (bool/`"24"`/0 refused). Report JSON has no Sharpe/CAGR/returns keys. MET at exactly the registered boundary. Config drift exit 1 + alert. Read-only snapshot test. Reverse mutations (a)(b) red. Focused overlay tests 38 passed. |
| `a384be7` Record the SHW-3 round | **Accepted** as a record. | ACTION_PLAN + handoff §7ap. §8 still said SHW-3 “may be scheduled” (addressed in this review record). |

## 4. Reverse mutations

| Mutation | Result |
|---|---|
| (a) `matured >= required` → `matured > required` | `test_sufficiency_met_exactly_at_the_preregistered_boundary` **RED**: `NOT_MET` at 1/1. Restored. |
| (b) Read required count from live config and skip drift check | `test_sufficiency_refuses_a_drifted_config_count` **RED**: exit 0, reported `0/6`. Restored. |

## 5. Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SHW3-001 | P3 | Open | `4c66406` | `command_sufficiency` via `_registration_or_refuse` | A closed epoch cannot be reported. The error still says the epoch “never accepts new observations.” | Source: sufficiency calls `_registration_or_refuse`, which requires `status == "shadow"`. | After SHW-4 close, a read-only count report should still be possible. | Allow sufficiency on `closed`, or a dedicated read path; keep observe/mature refused. | Test: register closed, `sufficiency` exits 0 with MET/NOT_MET. |
| SHW3-002 | P3 | Open | `4c66406` | example config / harness | `required_observation_count: 24` while the prereg marks that count `[TO FREEZE]`. | Example JSON; prereg §4. | A live `register` now would freeze 24 against a **draft** SHA-256. | SHW-4 must bind the frozen document first; do not treat 24 as adopted. | Operational: no register against the draft on the paper host. |

## 6. Explicit non-findings

- MET/NOT_MET is count sufficiency, not tail-gate evaluation.
- Independent unit is matured adjacent-month outcomes (SHW2-002).
- Boolean `True` cannot register as count 1.
- No order/proposal/execution writes on the success path.

## 7. What this review does not authorize

SHW-4 stream start, scheduler install, defensive-carry gate freeze,
opening the frozen paper DB, or any order.
