# Independent verification: SHW-2 counter-review fixes

Status: **verified**. Prepared: 2026-08-19. Reviewer: Cursor Grok 4.6.
Verifies Claude's counter-review of `d4c04c4..354a233`, not a second
review of that original range. No QuantConnect run. No operator DB.
No product correction in this round.

## 1. Snapshot

| Item | Value |
|---|---|
| Requested | check Claude's SHW-2 revisions after confirming the P2s |
| Base | `78258af` (Cursor SHW-2 review record) |
| Review head | `128aac8b57e643b4eb8cfa098dc164ea31fb8a52` |
| Branch | `origin/user/cursor/review-shw2-overlay-runner-20260819` |
| Note | product fixes landed on this review branch, not on `user/claude/shw2-overlay-runner-20260818` (still `354a233`) |

Fetched. Both commits in `git log --reverse --oneline 78258af..128aac8`
are dispositioned below. Temporary reverse mutations restored; tree
ended clean at `128aac8`.

## 2. Verdict

**Accept `27cb6dc` and `128aac8`.** SHW2-001 and SHW2-002 are closed.
SHW2-003 and SHW2-004 are closed. SHW2-005 PIT half is closed; Decimal
declination accepted.

SHW-3 is unblocked **for these findings**. It still needs its own
scheduled milestone. SHW-4, gate freeze, scheduler, and live epoch
registration remain unauthorized.

No P0. No P1. No reopened P2. One leftover P3.

## 3. Per-commit dispositions

| Commit | Disposition | Verification |
|---|---|---|
| `27cb6dc` Close SHW2-001/002 (P2) and SHW2-003/004/005 | **Accepted.** | Baseline calls `sleeve_return` on the target session for every member before writing an available t0. `mature` zips consecutive observation rows (so gap/refusal slots break the pair) and also requires the later cycle to fall in the next calendar month. Closed-epoch observe test added. Design SHW-2 bullet defers scheduler to SHW-4. `point_in_time_data` may only be `False` and is persisted. Reverse mutations (a)(b) red. Focused tests 32 passed. |
| `128aac8` Record the counter-review | **Accepted** as a record. | Counter-review document + handoff/ACTION_PLAN. Decimal decline rationale matches the observation-only path. |

## 4. Reverse mutations

| Mutation | Result |
|---|---|
| (a) Skip the baseline missing-member block (`if False and baseline_missing`) | `test_baseline_refuses_when_any_member_is_unpriced` **RED**: available t0 at 2026-02-27. Restored. |
| (b) Zip **available** pairs only and drop calendar adjacency | `test_mature_never_settles_a_multi_month_span_as_monthly` **RED**: one outcome for 2026-02-27. Restored. |
| (c) Drop calendar adjacency only; keep row-adjacent zip | Same test **still GREEN**. Calendar belt is real code but unpinned by the fixture (gap rows already break adjacency). |

## 5. Issue ledger

| ID | Priority | Status | Commit | Issue | Evidence | Reason | Correction | Verification |
|---|---|---|---|---|---|---|---|---|
| SHW2-001 | P2 | **Closed** | `27cb6dc` | Unpriced-member baseline | Test + mutation (a) | — | Baseline refusal + next-month heal | 32 passed |
| SHW2-002 | P2 | **Closed** | `27cb6dc` | Multi-month `monthly_returns` | Test + mutation (b) | — | Row-adjacent available pairs + calendar month follow | 32 passed |
| SHW2-003 | P3 | **Closed** | `27cb6dc` | Closed-epoch untested | `test_observe_refuses_a_closed_epoch_with_an_alert` | — | Register `status=closed`, observe exits 1 | green |
| SHW2-004 | P3 | **Closed** | `27cb6dc` | Design listed SHW-2 scheduler | Design §4 | — | Scheduler moved to SHW-4 | docs |
| SHW2-005 | P3 | **Closed (PIT) / declined (Decimal)** | `27cb6dc` | PIT unmarked; float band math | Contract refuses `point_in_time_data=True` | Decimal-on-float-closes is not an authoritative money path | Keep float analytics; config remains Decimal strings | green |
| SHW2-006 | P3 | Open | `27cb6dc` | Calendar adjacency unpinned | Mutation (c) green | Claude called both guards mutation-verified; deleting calendar alone does not redden the test | Optional: a fixture of two available rows spanning two months with **no** intervening refusal row | that test red if calendar check deleted |
| SHW2-007 | P3 | Open | pre-existing | Old test name still says `or_closed` | `test_observe_refuses_an_unregistered_or_closed_stream` still only covers unregistered | Misleading name after SHW2-003 | Rename | n/a |

## 6. What this does not authorize

SHW-3 implementation until the owner schedules it. SHW-4 stream start.
Defensive-carry gate freeze. Operator DB. Any order.
