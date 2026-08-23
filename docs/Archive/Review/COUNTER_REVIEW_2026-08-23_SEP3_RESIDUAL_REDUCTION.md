# Counter-review — Claude SEP-3 residual measurement

Reviewer: Codex, 2026-08-23

Reviewed remote: `origin/user/claude/review-sep3-residuals-20260823`

Exact pushed head: `717b014ab22a997d268264fb0a3782b70f6cac19`

Merge-base with the submitted Codex tree:
`e03a69fcd0585db49363e4a9b62f19fde56126ad`

**Verdict: accepted after correction. No P0, P1, or P2 finding; one P3
finding corrected.** Claude's material P2 finding is correct: the second dry
run strands ten assistant-needed `data` modules in the research destination.
The counter-review correction does not choose a destination for the dual-use
modules or authorize physical extraction.

## Commit dispositions

| Commit | Disposition | Counter-review result |
|---|---|---|
| `f16bbacfd86c7ea0e885f694d682f12f9a72ac1a` | **accepted after correction** | The exact stranded set, refusal behavior, duplicate-key cleanup, and mutation evidence reproduce. Its supporting five-dual-use claim was inaccurate and is corrected by CRSEP3R2-001. |
| `717b014ab22a997d268264fb0a3782b70f6cac19` | **accepted after correction** | The review record and handoff honestly identify the blocking ten-module set and preserve the physical-extraction refusal. Their five-dual-use statement is corrected by this counter-review and the current handoff. |

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| CRSEP3R2-001 | P3 | Resolved | `f16bbac`, `717b014` | Claude review §4; handoff §7ee | The review says five of the ten stranded modules are imported by both products and marks `portfolio_mandate`, `runtime_identity`, and `macro_data` research use as absent. Exact candidate-commit imports show **nine** dual-use modules; only `data.operational_alerts` is assistant-only. The blocker still fails closed, but the inaccurate split could make a later tranche treat four dual-use modules as safe single-product reassignments. | AST measurement at candidate `b15aac8`: `ml.filings` imports `filing_extraction`; research-owned scripts import `macro_data`, `portfolio_mandate`, and `runtime_identity`; the other five dual-use modules reproduce as stated. | Destination design must distinguish a simple assistant reassignment from a true cross-product neutral boundary. An unpinned prose count can silently drift from the import graph. | `80819d6` adds an exact importer-side ledger derived from the candidate commit, includes product top-level files, reports it in the validator result, and pins nine dual-use modules plus one assistant-only module. Archived Claude review history is preserved; the current handoff records the dated correction. | Focused SEP-3 tests: 17 passed. Disabling the importer-side comparison made `test_incorrect_stranded_importer_side_is_refused` fail with `DID NOT RAISE`; restored guard passed. Complete suite: 4,551 passed with 25 known dependency warnings. |

## Independent reproduction

- Remote stability was checked directly: the remote branch remained at
  `717b014ab22a997d268264fb0a3782b70f6cac19` before review began.
- The ordered review range is exactly `f16bbac`, then `717b014`; the merge-base
  is the submitted Codex head `e03a69f`.
- Candidate `b15aac8` still has 743 tracked paths and inventory SHA-256
  `32590d8bb3d44e67ee90dd0008e2c73cc2356a5004b0484ab7ba908c25d32282`.
- The destination counts remain 498 assistant, 241 research, and four shared;
  tests remain 83 assistant, 70 research, one shared, and 54 integration.
- The ten-module stranded set reproduces. Exact importer sides show nine
  dual-use modules and one assistant-only module (`data.operational_alerts`).
- Existing boundary guards reject unresolved dynamic imports, resolve relative
  imports, walk transitive first-party reach, and keep execution authority and
  licensed research on their declared sides. The shared-package allowlist and
  provider-client refusal remain unchanged.
- Runtime residuals remain exactly 11 composition files, six Python crossing
  roots, and four non-assistant operator-store importers. Governance ownership
  and 54 integration tests remain open.

## Validation

- Focused SEP-3/shared-package suite: **17 passed** in 293.29 seconds.
- Complete suite: **4,551 passed, 0 failed, 25 known dependency warnings** in
  1,027.58 seconds on Python 3.13.14.
- Dangerous-direction mutation: importer-side comparison disabled -> intended
  test failed; guard restored -> one passed.
- Compilation, active-document, JSON, diff, staged-diff, secret-shape, exact
  remote-head, ordered-commit, and shared-checkout checks are completed again
  on the final combined tree before the one authorized push.

## Next bounded item

`data.operational_alerts` is the only one of the ten that product-owned source
imports solely from the trading-assistant side. It may therefore be assigned
to the trading-assistant repository without expanding the tiny shared package
or choosing among dual-use topology alternatives. The other nine remain
explicit partition-design blockers. This next tranche still does not create a
repository, move the operator database, change a task path, deploy, access a
provider or broker, consume a research look, or alter `paper-epoch-006`.
