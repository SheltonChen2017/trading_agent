# Counter-review: Codex's SBP audit and documentation-cleanup corrections

- Date: 2026-08-20
- Reviewer: Claude (counter-review of the review of its own round)
- Subject: `docs/Archive/Review/REVIEW_2026-08-20_SBP_DOCUMENTATION_CLEANUP.md` and
  correction commits `390f3ad` / `8d16632`
- Reviewed branch: `codex/review-sbp-doc-cleanup-20260820`, exact head
  `8d16632`, based on `origin/main` = `13355a6`
- Counter-review branch: `user/claude/sbp-doc-cleanup-counterreview-20260820`

**Snapshot deviation, recorded rather than glossed:** the process requires a
review to begin from a pushed remote head. Codex's branch was **local-only**
at the time of this counter-review, so the snapshot was frozen by branching
from the exact local object `8d16632` and pushing this branch, which publishes
both correction commits as ancestors. That is the same freeze-by-push pattern
used in the 2026-08-17 rounds.

## Verdict

**ACCEPTED.** All six findings are confirmed, including the P2 — which is a
real defect in my own submitted round, not a stylistic disagreement. The
corrections are accurate, the red proof reproduces independently, and both PR
merge trees are byte-identical to their submitted heads. Five smaller items
are closed here (CRV-001..005); none reverses a correction.

## Part 1 — verification of Codex's six findings

| Finding | Verdict | Independent evidence |
|---|---|---|
| SBDC-001 (P2, valid-null evidence called invalid) | **CONFIRMED — my error** | `docs/Archive/Research/alpha-result.md` marks R-009, R-011, R-012, R-014, R-015, R-016, R-020, R-021, R-022 and R-023..R-028 `VALID`; A-001/A-002 are null observations over valid runs. My sentence "every historical QuantConnect result remains invalid, refused, unanalysed, or provenance-incomplete" was true at the 2026-08-17 audit and I carried it forward without re-checking — the exact drift the round existed to remove. The floor is also 452 at A-002 (428 + the 24-cell Stage 1 family), not 428, and the ledger records 30 run-level looks, not five. Calling a null result invalid is not a wording slip: it invites re-running a question the project already answered. |
| SBDC-002 (P3, 15% cap overstated) | **CONFIRMED as an overstatement of mine** | My arithmetic was right (`0.95*0.10 + 0.05*3*w >= 0.15` needs `w >= 36.7%`; P3 maxes at 14.5%) but my conclusion moved from *empirically unreachable for QQQ/XLK/SOXX* to *structurally inert*, which the contract does not support: the draft freezes no maximum fund issuer weight. Codex's rare-tail framing is the defensible one. |
| SBDC-003 (P3, exclusion would change the estimand) | **CONFIRMED, and my variance claim was wrong** | At exactly 10 names the cap forces equal weights, so the zero is the true realized difference between two frozen strategies, and conditioning on `n > 10` answers a different question. My "deflates both the mean and its variance" was loose: appending a zero to a sample of positive values *raises* its variance. Keeping the months is correct. |
| SBDC-004 (P3, alignment resolved rather than left open) | **CONFIRMED** | P3−P2 uses no P4 return, so gating it on P4 evidence spends confirmatory months on a variant that carries no test. My audit left this as an owner choice; resolving it in the draft is better, because after data exists the choice becomes a sample decision. |
| SBDC-005 (P3, broken amendment table) | **CONFIRMED — my defect** | The diff shows my SBPA-007..010 rows separated from the ledger by a blank line, so they rendered outside the table. Splitting the bootstrap-power point out as SBPA-011 is also right: I had bundled two unrelated decisions into one amendment cell. |
| SBDC-006 (P3, stale current-state after the merges) | **CONFIRMED** | Verified independently: `9009239`'s tree equals `a2b69eb`'s and `13355a6`'s equals `a77c6a5`'s, so neither merge hid conflict-resolution edits, and the topology text I wrote was overtaken the moment PR #283/#284 landed. |

**Red proof reproduced independently.** Restoring the three pre-correction
documents from `origin/main` and running the new guards produced 3 failed / 31
deselected; restoring the corrected files returns 34 passed. The restore ran
through a shell `trap`, so the tree could not be left broken.

**Nothing was weakened.** The correction deletes no existing test and no
finding; my submitted audit is preserved verbatim with an addendum recording
the later dispositions, which is the right shape for a superseded record.

## Part 2 — counter-review findings (closed here)

| ID | Priority | Location | Finding | Correction and verification |
|---|---|---|---|---|
| CRV-001 | P3 | `docs/Archive/Research/alpha-result.md` R-029 | The entry's heading read `(UNANALYSED)` while its own Validity row reads `**VALID**` (upgraded with A-003). This is SBDC-001's exact class — a status claim contradicting the record beneath it — and neither review caught it while correcting the others. | Heading now reads `(VALID)`. The Validity row's upgrade history is untouched, so nothing is rewritten or hidden; only the contradiction is removed. |
| CRV-002 | P3 | the two new prose guards | Both pinned must-stay-true literals (`"VALID but null"`, `"remain in the primary P2−P1 series"`). The module's own docstring warns against exactly this: a legitimate rewording reddens the guard, and the obvious fix is to delete the assertion. | Replaced with window regexes asserting the relationship (valid *and* null; the months *remain* primary). Re-verified red on the pre-correction documents, so strength is unchanged. |
| CRV-003 | P3 | the contiguity guard | A missing amendment row raised `StopIteration` — an error with no message rather than a failure naming what vanished. | Rewritten to assert exactly one row per amendment with a diagnostic message, then assert contiguity with the position map in the failure text. Still red on the pre-correction table. |
| CRV-004 | P3 | SBP plan §6 | The correction states the alignment rule for P3−P2 and P4 but leaves the core block's rule unstated, so the defect SBDC-004 closed for one comparison remains arguable for P1−P0 and P2−P1. | §6 now states that each paired series aligns on its own two portfolios and nothing else. |
| CRV-005 | P3 | SBP plan §11, SBPA-011 | Rejecting the exclusion correctly dropped my proposal, but with it the useful half: exactly-10-name months are exact zeros that dilute the detectable effect, so a power statement that ignores their rate is incomplete. This is compatible with keeping them in the sample. | SBPA-011 now also requires the expected frequency of exactly-10-name months in the pre-adoption sensitivity table. |

No P0, P1, or P2 findings against the correction.

## Part 3 — one owner-facing consideration, explicitly unverified

SBPA-007 now asks the owner whether 15% is the intended rare-tail P4 limit. A
fact worth checking while deciding: US registered index funds operate under
diversification rules that ordinarily keep any single issuer far below the
36.7% weight the gate needs, which would make the tail effectively unreachable
for the proposed pairs. **This repository holds no evidence for that claim and
this counter-review establishes none** — it is exactly the kind of assertion
that sank my SBPA-001 probe. SBP-0 already verifies official issuer documents
for the eligible pair table; the per-issuer weight limit belongs in that same
check, where it can be sourced. It is recorded here as a question for that
step, not as a finding, and no plan text asserts it.

## Validation

- `tests/test_active_document_consistency.py`: **34 passed**; the three new
  guards verified red (3 failed) against the pre-correction documents both
  before and after the CRV-002/003 hardening.
- Focused document/contract pair
  (`test_active_document_consistency.py` + `test_proposal_outcome_groups.py`)
  and the full suite are recorded in `docs/SESSION_HANDOFF.md` §7bu for the
  exact final tree.
- Python 3.13.14. No product behaviour, schema, CLI, migration, research
  result, QuantConnect access, broker access, scheduled task, deployment,
  epoch action, or operational database changed. SBP remains a DRAFT and no
  section-2 value was adopted or frozen.
