# Counter-review — SEP-1 final research-result adapter tranche

Counter-reviewed: 2026-08-22 by Codex.

Scope: exact pushed review branch
`origin/user/claude/review-sep1-adapters-20260822` at
`6f8228f2b6703007938c14fbed5bfc09e2b69687`, based on the submitted Codex
head `71d8500548514e6f864f8f31d033e58beff8961d`. Ordered Claude commits:
`2553493`, `6ddc787`, `6f8228f`.

Counter-review branch: `codex/counterreview-sep1-adapters-20260822`, created
from that exact pushed review head.

**Outcome: accepted after correction.** No P0, P1, or P2. One P3 test-harness
truth defect was reproduced and corrected at `00d5abe`. Claude's cap-refusal
test is load-bearing, the dated source verification is accurate, and the
review's zero-edge, zero-authority-path, compatibility, safety, and milestone
claims reproduce.

---

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `2553493` | Accepted after correction | The over-cap refusal test is correct and fails when the guard is disabled. The Massive Analyst Ratings page still visibly names “backtesting rating impact” as a use case on 2026-08-22. The test was appended below the file's direct-run block, however, so that built-in runner skipped it and three earlier contract tests; `00d5abe` makes the runner execute all eight tests. |
| `6ddc787` | Accepted | All seven submitted Codex commits are dispositioned, both P3 findings are supported, and the report distinguishes input-binding integrity from proof that a computed target is mathematically correct. The stated operational and research boundaries remain fail-closed. |
| `6f8228f` | Accepted | The handoff and separation plan accurately record an implementation-complete but not-yet-counter-reviewed SEP-1. This counter-review now closes that final condition and advances the current records separately. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Correction | Verification |
|---|---|---|---|---|---|---|---|---|
| SEP1CR2-001 | P3 | Resolved | `2553493` | `tests/test_strategy_proposals_generic.py` | The module's direct-run harness printed “All strategy_proposals_generic tests passed” while executing only four of eight tests. It skipped the missing-result, altered-history, immutable-contract, and new over-cap refusal tests. A developer running the file directly could therefore receive a false green result after breaking a fail-closed research-result boundary. | With the production cap check temporarily disabled, direct execution still printed success while the focused pytest cap case failed `DID NOT RAISE`. | `00d5abe` moves the runner below every test and calls all eight explicitly. | Direct execution and the eight-case pytest module both pass after restoration. The same cap-disable mutation is now reached by either runner. |

Claude's retained **CDR2-005 (P3)** remains open and unchanged. No dynamic or
relative import in this review range creates a hidden product crossing.

## Independent reproduction

- The cap-refusal test passes on the reviewed implementation and fails when
  `_validated_research_target`'s configured-cap check is disabled.
- A temporary reverse mutation proved the pre-correction direct runner stayed
  falsely green; the focused pytest case failed on the same mutated tree.
- The official Massive Analyst Ratings documentation was inspected on
  2026-08-22 and visibly lists “Market sentiment tracking, portfolio alerts,
  backtesting rating impact, trend analysis.” This is evidence for the narrow
  use-case statement, not evidence about private order-form or third-party
  processing terms; the current documents preserve that separate gate.
- An independent source search found no direct product-to-product imports,
  no product import of `scripts.product_composition`, and only the known
  optional `importlib.import_module("pandas_market_calendars")` use in ACER
  capability code. The machine-readable ledgers remain empty.
- Focused boundary, generic-proposal, explanation, and active-document tests
  passed 77/77 on Claude's exact review head. The corrected direct runner and
  proposal module passed 8/8.

## SEP-1 definition-of-done disposition

SEP-1 is complete after this counter-review. Its three reviewed tranches
remove the single transitive authority violation, extract the neutral shared
contracts, replace assistant-to-research calculations with typed immutable
input-bound results, reduce direct crossings 13 → 9 → 4 → 0 without an
exception, and keep every proposal, approval, execution, and reconciliation
authority in the trading assistant. `scripts/` classification and the
temporary composition seam's permanent ownership are explicitly SEP-2 work.

## Safety and scope

No broker, provider account, licensed row, operator database, scheduled task,
deployment, backtest, outcome, research look, or evidence epoch was accessed
or changed. Paper-trading authority and `paper-epoch-006` are unchanged. The
public vendor-document check does not authorize any ACER data transfer or
outcome work.

## Validation

Focused and mutation results are recorded above. On the corrected tree, the
focused boundary/proposal/explanation/document set passed **77/77**, the
direct runner completed all eight tests, and the complete suite passed
**4,506 tests / 0 failed / 25 warnings** in 685.05 seconds under Python
3.13.14. Required `compileall`, including `research/`, passed. Final diff,
secret, remote-head, ordered-commit, and shared-checkout checks are recorded
in the closing handoff section on the exact committed tree.

## Assessment

**9.5/10.** Claude's review was careful, technically accurate, and materially
improved a dangerous refusal boundary. The remaining half point is the
direct-run harness placement: the new test was excellent under pytest, but a
supported alternate runner could claim success without executing it.
