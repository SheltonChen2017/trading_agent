# Audit of the independent SBP amendments review

- Date: 2026-08-20
- Reviewer: Claude (owner-requested audit of a completed review)
- Subject: `docs/Review/REVIEW_2026-08-19_SBP_PLAN_AMENDMENTS.md` (Codex)
- Range that report reviewed: `5e3708e..5c42bfd` (one commit), correction
  `5c3bf45`, record `2a26353`
- Repository state at audit: `origin/main` = `c289f95`; the whole SBP chain is
  merged history
- Audit branch: `user/claude/sbp-review-audit-20260820`, based on `a2b69eb`
  (the 2026-08-20 topology-refresh round)

This audits a *review*, not the plan chain again. It asks two questions: are
the report's findings and corrections correct, and did the report leave
anything material unfound. It adopts nothing, freezes nothing, changes no
proposed value, and authorizes nothing.

## Verdict

**SUSTAINED.** All seven findings verify, every claimed correction is present
in `5c3bf45`, and the obligations in
`docs/process/GENERAL_CODE_REVIEW_INSTRUCTIONS.md` are met. SBPR-001 and
SBPR-003 had to be made before any owner adoption, and SBPR-001 was right
against my own submission.

Six findings the report did not make are recorded in part 2. Four are defects
in the plan that outlast the report (SBPX-001..004), one is ledger hygiene in
the report itself (SBPX-005), and one extends a requirement the report created
(SBPX-006). **SBPX-001 and SBPX-002 should be resolved before the owner
freezes SBP-0**, because both concern gates the plan presents as protections.

## Part 1 — verification of the report's seven findings

Each was checked against the plan text, the correction commit, and Git rather
than accepted from the report's own account.

| Finding | Audit result | How it was checked |
|---|---|---|
| SBPR-001 (P2, probe not evidence; 33.8% is not a ceiling) | **Confirmed, and load-bearing** | No probe code, input artifact, or hash exists in `5c42bfd` or anywhere in the tree. The logical half is decisive: an all-candidate overlap vector cannot upper-bound overlaps of renormalized subsets. Re-running my own probe over index-weight-led baskets produced 51–68%, refuting the "50% is unreachable" claim outright. Those re-check numbers carry the same provenance defect and are used only to withdraw a claim, never to establish one. |
| SBPR-002 (P2, ticker-level exclusion redefines membership) | **Confirmed** | The signal selects the ticker first, so deleting it afterwards is the silent row drop this repository's rules forbid, and the missingness is plausibly outcome-correlated. Ratings-unavailable names are genuinely different: they never pass the rule. |
| SBPR-003 (P2, look-through omitted the 95% scaling and used literal leveraged holdings) | **Confirmed** | `5c3bf45` introduces `0.95*core + 0.05*ordinary` (P3) and `0.95*core + 0.05*leverage*ordinary` (P4). A same-index 3x fund's economic exposure is the index multiple; its literal holdings are commonly derivatives, so the original formula measured the wrong portfolio. |
| SBPR-004 (P2, withdrawn 35–40% and 0.6%/month claims) | **Confirmed** | `1.2%/sqrt(24) = 0.245%` reproduces. The submitted figure was a two-sided rejection boundary against an assumed tracking error, not power, while the frozen test is one-sided. |
| SBPR-005 (P3, frozen SBR preregistration declared itself superseded early) | **Confirmed** | `5c3bf45` removes the nine-line SUPERSEDED block from the frozen capture contract; the plan now records only a conditional supersession on explicit adoption. |
| SBPR-006 (P2, minimum basket 8 incompatible with a 10% cap) | **Confirmed** | `n * 10% < 100%` for `n < 10`. The disclosure that exactly 10 names force `P1 = P2` is also correct: the cap admits only 10% each, which is equal weight. SBPX-003 records the consequence this created. |
| SBPR-007 (P3, 63 returns need 64 closes; price lineage) | **Confirmed** | Direct arithmetic, and the immutable price-input requirement is now in the monthly timeline. |

Range and disposition integrity: `5c42bfd`'s parent is exactly `5e3708e`, so
the one-commit range is complete, and the commit touches documentation only,
which supports the report's out-of-scope declaration for execution, broker,
kill-switch, and operational-database surfaces. The ledger retains closed
items rather than deleting them, as required.

## Part 2 — findings the report did not make

| ID | Priority | Location | Finding and impact | Evidence | Reason it must be addressed | Proposed correction |
|---|---|---|---|---|---|---|
| SBPX-001 | P2 | plan §5, §8 | The 15% look-through issuer cap is **structurally non-binding**, so the "mandatory" concentration gate and the `look-through cap breach` refusal class can never fire. | Exposure is `0.95*core_i + 0.05*L*w_i` with `core_i <= 0.10` and `L = 3`. Binding needs `w_i >= (0.15 - 0.095)/0.15 = 36.7%` of the ordinary fund in one issuer — unreachable for QQQ, XLK, or SOXX. For P3 (`L = 1`) it needs `w_i >= 110%`, which is impossible. | This is SBPR-006's defect class inverted: the report caught a state the rule always refuses and missed a gate that never fires. A cap that cannot bind reads as protection while providing none. | Owner decision at SBP-0: either set a cap that can bind under the frozen sleeve and leverage (roughly 11% or below), or keep 15% and state plainly that it is a corrupt-data tripwire rather than a live constraint. Do not enlarge the sleeve or leverage to make the cap bind — that would tune the portfolio to a gate. |
| SBPX-002 | P2 | plan §4 | The plan names a real risk of inverse-volatility weighting — concentration in "slowly moving but economically related stocks" — and cites the look-through cap as the reason it is controlled. A **per-issuer** cap cannot constrain a cluster of *distinct* issuers in one industry, and no sector or industry limit exists anywhere in the plan. | §4 attributes the mitigation to the §5 issuer cap. Nothing in §§2–8 bounds industry weight. Low-volatility screening inside one index selects correlated names by construction. | An owner reading §4 would adopt believing this risk is controlled. Either the control exists or the claim must go; a stated mitigation that cannot mitigate is worse than an acknowledged open risk. | Add a frozen industry-concentration rule (a cap plus its own named refusal, using a declared classification source), or delete the mitigation claim and record unmanaged industry concentration as a disclosed limitation. |
| SBPX-003 | P3 | plan §2, §6, §7 | Raising the minimum basket to 10 (SBPR-006, correctly) created **structural zeros** in the P2−P1 cell: whenever exactly 10 names qualify, the 10% cap forces equal weights, so that month's paired excess is identically 0. The plan discloses the identity but not its inferential consequence. | With `n = 10` and a 10% cap every weight is 10%, which is P1. Those months enter the bootstrap sample as exact zeros, deflating both the P2−P1 mean and its variance. | A confirmatory family must know in advance which months can contribute signal to which cell; deciding after outcomes are scored is a post-hoc sample choice. | Declare in advance whether `n = 10` months are excluded from the P2−P1 cell (and if excluded, that they still count for P1−P0 and P3−P2), and record the expected frequency at SBP-0. |
| SBPX-004 | P3 | plan §6 | The overlay-block alignment rule gates the **inferential** P3−P2 cell on the availability of **descriptive-only** P4, so missing leveraged-fund evidence deletes confirmatory months from a cell that does not use P4. | §6: "P2–P4 form the overlay block and use only dates on which all three overlay-block portfolios are available." P4−P3 is explicitly descriptive. Holdings or mapping unavailability need not be independent of market conditions. | Identical-observation alignment is the right instinct, but paying confirmatory months out of a 24-month budget for a variant that carries no test is a real cost, and the missingness may not be random. | Either align P3−P2 on P2/P3 availability alone and align P4 descriptively where all three exist, or keep the current rule and record at SBP-0 that P4 evidence gaps consume inferential months. |
| SBPX-005 | P3 | the report's own ledger | The Verification column for SBPR-001/002/004/005 reads "focused document-consistency tests pass." That suite is **insensitive** to every one of those defects and would pass identically on the uncorrected text. | `tests/test_active_document_consistency.py` asserts epoch status, published balances, and merge-reachability claims; it contains nothing about overlap floors, basket membership, power statements, or supersession wording. | The process document requires verification that discriminates. Citing a green but unrelated suite makes a prose correction look mechanically proven when it was established by reading. | For prose corrections, name the real evidence — inspection, arithmetic, or cross-document search — as SBPR-006 and SBPR-007 correctly did. |
| SBPX-006 | P3 | plan §7 | The pre-adoption sensitivity table SBPR-004 requires covers tracking error and dependence but not the **frozen estimator's own small-sample behavior**. | The frozen contract is a stationary bootstrap with mean block length 3 over 24 monthly observations: roughly eight effective blocks. | A minimum-detectable-effect table computed from a normal approximation can materially misstate what the frozen 20,000-draw block bootstrap will reject at `0.05/3`. | Extend the required table to report the bootstrap's behavior at the frozen block length and horizon, so the power statement describes the test that will actually run. |

No P0 or P1 findings. This audit read documents only. No code, contract,
schema, migration, research result, QuantConnect access, broker access,
scheduled task, deployment, or operational database was touched.

## Part 3 — what this audit does not do

It does not adopt, freeze, schedule, or implement SBP, and it does not
re-open SBPA-001..006, whose dispositions stand exactly as the review and
counter-review left them. SBPX-001..004 and SBPX-006 are recorded as pending
proposals in the plan's section 11 amendment log, in the same shape SBPA-006
uses, for the owner's SBP-0 decision. SBPX-005 concerns the review report only
and needs no plan change. Nothing here is evidence about returns: the plan
still has zero captured months and zero admissible outcomes.

## Validation

- `tests/test_active_document_consistency.py`: 31 passed.
- Full suite on the immediately preceding tree of this branch's base:
  **4,348 passed, 25 warnings** in 844.38 seconds, exit 0. This round changes
  documentation only and exercises no code path.
- `git diff --check`: passed.
- Python 3.13.14.
