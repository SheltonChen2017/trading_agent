# Counter-review: SHW-3 sufficiency review

Status: **counter-review complete. The review is VERIFIED; SHW3-001 is
FIXED; SHW3-002 was correct at its snapshot and is DISCHARGED BY
EVENTS.** Prepared: 2026-08-19. Counter-reviewer: Claude (Fable 5),
author of the range under review. No QuantConnect run; no operator
database opened; no stream registered.

## 1. Findings

| ID | Classification | Resolution |
|---|---|---|
| SHW3-001 | **Confirmed by reproduction**: `sufficiency` on a `closed` epoch exited 1 ("never accepts new observations") — closing a stream made its evidence unreadable. | **FIXED**: `command_sufficiency` gained its own read path accepting `shadow` and `closed` registrations (a report is a READ; the record must stay reportable forever); the report now carries `stream_status`; `observe`/`mature` keep the strict shadow-only write gate, pinned in the same test (observe on the closed epoch still exits 1). Reverse mutation (strict gate restored in sufficiency) red, restored green. |
| SHW3-002 | **Confirmed as written at the review's snapshot — and DISCHARGED by the owner's freeze**, which the reviewer could not see: the review ran against `a384be7`, and the owner froze the preregistration afterward ("yes accept as is", commits `d0912e0`/`9e8f46d` on `user/claude/dc-gate-freeze-20260819`) with `required_observation_count=24` among the frozen values. The operational guard stands in stronger form: SHW-4's registration binds the FROZEN document's SHA-256, and no registration against any draft ever occurred (verified: the overlay tables exist only in test databases; the operator DB was never opened by this tree). | No change needed beyond the freeze already on record. |

## 2. Review-quality verification

Both reverse mutations match the tests they cite (they are the
boundary and drift guards this round's implementation added, re-run
independently). The reviewer worked in an isolated sibling worktree and
left the shared checkout untouched — the shared-worktree hazard is now
fully institutionalized. The verdict's constraints (no SHW-4 from that
review, no gate freeze implied by the example config) were respected:
the freeze happened as its own owner-decision round, not as a side
effect.

## 3. Verdict

The review stands as the review of record for `553da76..a384be7`; this
round extends the review branch with the SHW3-001 fix. With SHW-1..3
implemented and reviewed and the preregistration frozen, SHW-4 (stream
registration binding the frozen SHA-256, first baseline, release
advance + scheduler on the operational clone, dedicated
`data/shadow_overlay.db`) is the next milestone, per the recorded owner
decisions. Nothing here starts it.
