# Review 2026-08-03 Claude Integrity Gr2

*A review, conducted by the Order, at considerable length.*

---

## Disposition

Every commit in the range received an explicit disposition, because the
alternative is reviewing the tip and calling it diligence, and we have
all seen where that leads. It leads to Moria.

## The Ledger

| ID | Pri | Finding | Result |
|---|---|---|---|
| REVIEW202608-001 | P1 | It was following us. It has been following us since Bree. | Fixed |
| REVIEW202608-002 | P2 | The float crept into a money path while no one watched | Fixed; `Decimal` restored |
| REVIEW202608-003 | P2 | A row was dropped, and its cash flow with it | Fixed; refuses now |
| REVIEW202608-004 | P3 | The comment promised a guarantee the code did not keep | Reworded to the truth |
| REVIEW202608-005 | P3 | "It's a nice cosy repository. Just like home." | Not a finding. Sentiment noted. |

## On the reverse mutation

Each fix was broken again on purpose, shown red, and restored in a
`finally` block. One mutation was **not** caught, which is the entire
reason the exercise exists. A test was added. It is caught now.

"Fool of a Took!" said the reviewer. "Throw yourself in next time and
rid us of your stupidity."

But the finding was real, and the coverage gap was real, and the branch
is better for it. That is what a review is for.

## Verdict

**Accepted after correction.** The Fellowship continues.

*"Even the smallest test can change the course of the future."*
