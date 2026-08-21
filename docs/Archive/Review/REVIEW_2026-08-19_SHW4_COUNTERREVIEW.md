# Counter-review: SHW-4 stream-start review

Status: **counter-review complete. The review is VERIFIED, including
its correction of MY merge defect; the two open P3s are now closed.**
Prepared: 2026-08-19. Counter-reviewer: Claude (Fable 5), author of the
range. No stream writes, no epoch roll, no real task install, operator
DB untouched.

## 1. Findings verification

| ID | Classification | Resolution |
|---|---|---|
| SHW4-001 (P2) | **Confirmed — a defect in MY conflict resolution.** `git grep STAGE2-PEAD a6a690c` is empty: merge `039e5cf` silently dropped the owner's Stage-2-closed row from the sequencing authority while I asserted "no record was lost". The reviewer both caught and FIXED it (row restored on the review branch; verified present at HEAD). Lesson recorded: verifying a conflict resolution means grepping for every row/section of BOTH parents, not reading the resolved hunk. | Closed by the reviewer; verified here. |
| SHW4-002 (P3) | **Confirmed** — the ALLOCATION-POLICY row contradicted POST-CLOSURE on APQ-1's scheduling; the reviewer aligned it. Verified at HEAD. | Closed by the reviewer; verified. |
| SHW4-003 (P3) | **Confirmed by independent recomputation**: checkout CRLF bytes hash `5479d6b6459a…` (5549 B, what the live registration binds); the git blob hashes `96fc515cdf0f…` (5446 B, LF). Internally consistent on this host; cross-platform `git show`-based verification would refuse a valid stream. | **Closed as documented**: a comment now sits at the hash site in `run_overlay_shadow.py` stating the checkout-bytes semantics, the cross-platform caveat, and that LF normalization is only permitted in a NEW preregistration/epoch — never by re-registering the live one. The live binding is untouched. |
| SHW4-004 (P3) | **Confirmed** — the installer's "never touches Paper/ML-Shadow" claim was convention, not enforcement; `-TaskPrefix` + `-Force` could have built colliding names. | **Closed with enforcement**: a denylist refuses any `TaskPrefix` matching `TradingAgent-Paper*` or `TradingAgent-ML-Shadow*` before any preview or registration. Verified by execution: the forbidden prefix throws; the default prefix still WhatIf-previews exactly the three Overlay-Shadow tasks; no task was created. |

Also acknowledged: the review corrected my range arithmetic (12
commits, not the 11 my request claimed — I listed 12 and miscounted).

## 2. Claims re-verified

Merge trees `bea5310`==`8a543a8` and `f63ba89`==`a6a690c` re-hashed
exact; the freeze-before-registration chronology (`d0912e0` 10:14 →
config `3c9105d` 10:39 → DB `registered_at` 17:39:34Z) matches the
review; the SHW3-001 mutation was re-run by the reviewer independently
(their red/restore transcript is consistent with the fix's test). The
out-of-range fact — PR #267 merged the head before the review finished
— is accurately characterized: the roll plan's precondition 4 is
satisfied for the `a6a690c` tree now that the review and this
counter-review are recorded.

## 3. Verdict

The review stands as the review of record for `a384be7..a6a690c`.
All four findings closed. The reviewed-mainline precondition for the
epoch roll is now met; the roll itself and the real task install
remain owner-present operations. Nothing here performs them.
