# Counter-review: APQ-1 allocation-policy review

Status: **counter-review complete. The review is VERIFIED, its P2 fix
independently re-verified by mutation, and the two open P3s are
closed.** Prepared: 2026-08-19. Counter-reviewer: Claude (Fable 5),
author of the range. No QC, no analyser, no driver change.

## 1. Findings

| ID | Classification | Resolution |
|---|---|---|
| APQ1-001 (P2) | **Confirmed — a defect in MY implementation.** The positivity check accepted `inf` (`inf > 0` is True) into emitted PROW returns, and `NaN` slipped past the boundary check (`NaN <= 0` is False) to crash in `_member_returns` — while the frozen preregistration section 3 explicitly requires a non-finite close to refuse the date. This is the same non-finite class the parsers were hardened against (SHR/S0R-003), reproduced on the emitter side; I hardened parsers against it days ago and then wrote the same hole into a new emitter. Lesson recorded. | Closed by the reviewer (`_usable_close` with `math.isfinite` + regression test). Counter-verified: their mutation (isfinite dropped) re-run — RED on the new test, restored, 7 passed. |
| APQ1-002 (P3) | **Confirmed** — my handoff section 8 still carried the pre-roll text while section 7av in the same file recorded the roll as executed; the reviewer's commit repointed it at APQ-2-after-review. Verified at HEAD. | Closed by the reviewer. |
| APQ1-003 (P3) | **Confirmed** — `priced`/`targeted` always equal the policy's member count while refusal is union-wide, so an analyser reading `priced` as union coverage would be wrong. | **Closed as documented**: the plan's APQ-2 section now states the semantics (policy-member counts; `priced == targeted` holds by construction; `priced != targeted` may be refused as corruption). No product change — matching the reviewer's recommendation. |

## 2. Review-quality verification

The review reproduced both non-finite behaviors on the submitted tree
before fixing, matched the frozen preregistration field by field
(weights, window, floor, cadence, turnover definition, union refusal,
no-ACTIVE_UNIVERSE, not-in-FAMILIES), verified the definition of done,
and correctly scoped its non-findings (Symbol-key identity fails
CLOSED into INCOMPLETE; costs are APQ-2's job). Its out-of-range note
(PR #270 merged before the review finished; merge tree equals the
implementation tree) is accurate.

## 3. Verdict

The review stands as the review of record for `01508b1..e2c4a2b` plus
the fix commit `d50a30a`. APQ-1 is complete and reviewed; **APQ-2 (the
analyser) is unblocked**, and its review is where the optional
excess-mean reporting decision gets fixed before any run exists.
Nothing here authorizes APQ-3, a cloud launch, or any statistic.
