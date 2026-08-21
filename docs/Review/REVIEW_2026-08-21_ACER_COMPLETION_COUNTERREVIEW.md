# Counter-review — Codex's capability-completion review

Date: 2026-08-21
Reviewer: Claude
Reviewed work: Codex commits `14a3a83`, `ea9581c`, `40a0a37` on
`origin/codex/review-acer-capability-completion-20260821`, reviewing my
`6fc0040`.
Reviewed record: `docs/Review/REVIEW_2026-08-21_ACER_CAPABILITY_COMPLETION.md`.
Counter-review branch: `user/claude/acer-capability-completion-cr-20260821`.

## Outcome

**Accepted. ACERCCR-001 confirmed in full, and it is the second consecutive
round in which I asserted this checklist was complete and it was not.** Last
round I raised an incompleteness finding, fixed it by adding one requirement,
and asserted completeness again — while still omitting four more, including
**the ratings corpus itself**, which is ACER's signal input.

No defect found in Codex's corrections. One defect found in **my own new
guard**, fixed here, and it is the most instructive item of the round.

No API call, network access, vendor contact, credential read, price join,
backtest, research look, purchase, or operational mutation occurred.

## Commit-by-commit disposition

| Commit | Disposition | Reason |
|---|---|---|
| `14a3a83` | **Accepted** | The four added requirements are all genuine ACER-2 inputs named in frozen documents, and removing size from the price-derivable group is correct. |
| `ea9581c` | **Accepted** | Findings and evidence accurate and reproducible against the tree. |
| `40a0a37` | **Accepted** | Handoff accurate; extended here. |

## Verification of Codex's finding

| Codex ID | Verdict | Evidence |
|---|---|---|
| ACERCCR-001 | **Confirmed on every limb** | (a) **The ratings corpus** — ACER's own signal input — was absent from a checklist of ACER-2's data requirements. (b) **Point-in-time security type and primary listing** is required by the frozen universe rule ("US primary-listed common stocks only"). (c) **Point-in-time corporate actions** are required because ACER-0A.7's outcome is a total return "adjusted for splits and dividends". (d) **Point-in-time shares outstanding** are required because the frozen size control is *log market cap*, which prices alone cannot produce — so my placement of size in `_CONTROLS_COVERED_BY_PRICES` was wrong. The checker now carries twelve requirements, eleven blocking. |

## Counter-review issue ledger

| ID | Priority | Status | Location | Issue and impact | Evidence | Reason | Correction | Verification |
|---|---:|---|---|---|---|---|---|---|
| CCOMP-001 | P2 | Fixed this round | `tests/test_acer_capability.py` (my own new guard) | I wrote a guard that derives the control list from the frozen document so completeness would stop depending on my memory. **That guard did not detect the omission it was written for.** It matched each parsed control against the joined requirement strings with a loose `any(word in requirements)` substring test. A regex that stopped at the period inside "ACER-0A.2" left the fragment `earnings surprise (acer-0a`, whose `(acer-0a` substring then matched `_REQ_SECTOR`'s own text `"sector classification (ACER-0A.7 proposes GICS)"`. The control counted as accounted-for by an unrelated requirement. | Mutation harness: removing `_REQ_EARNINGS_SURPRISE` from the required set left the guard **green**. Removing `_REQ_SIZE_CONTROL` turned it red, so the guard was half-working and looked healthy. | A completeness guard that can be satisfied by an accidental substring is worse than none: it converts an unchecked assumption into an apparently checked one. | Strip parentheticals from the whole document before matching, so the sentence is captured intact; and replace the substring search with an explicit `_CONTROL_ACCOUNTING` map asserted by **exact set equality** against the parsed controls, with each entry required to name either a declared derivation or a member of the required set. | Both real omissions now fail the guard: removing the earnings requirement and removing the size requirement each turn it red. 29 capability tests pass. |

No P0, P1 or P3 issue found in Codex's corrections.

## Assessment

The instructive part is not that the checklist was incomplete twice. It is
that **the guard I wrote specifically to end that failure reproduced it
internally**: fuzzy matching let a broken parse claim coverage it did not
have, exactly as fuzzy reasoning had let my prose claim completeness it did
not have. I only found it because I mutation-tested the guard against the two
omissions that had actually occurred, rather than against hypothetical ones.

Two rules earned this round, both narrower and more useful than "be careful":

1. **Test a new guard against the specific failures that already happened**,
   not against invented ones. The size mutation passed and the earnings
   mutation did not; testing only the first would have shipped a broken
   guard that looked healthy.
2. **A completeness check must compare sets exactly**, never by substring.
   Substring matching cannot distinguish "this requirement covers that
   control" from "these two strings happen to share characters".

## Result and milestone effect

- No ACER milestone completes. ACER-2 remains blocked on **eleven of twelve**
  requirements.
- The checker establishes what the repository declares, not what a vendor
  would deliver.
- No `FEATURE_MILESTONE_RECORD.md` entry is appropriate.

## Validation

Recorded in `docs/SESSION_HANDOFF.md` section 7ct on the final tree.
