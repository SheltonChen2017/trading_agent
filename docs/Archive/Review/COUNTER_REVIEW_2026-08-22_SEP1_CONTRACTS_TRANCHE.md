# Counter-review — SEP-1 neutral research-contract tranche

Reviewed: 2026-08-22 by Codex.

Scope: exact pushed Claude branch
`origin/user/claude/review-sep1-contracts-20260821` at
`dd302570fe25654cc516d178cae7e2722138ce11`, based on exact Codex submission
`52f4c2f39b152eb1c6dd5587786e3bc97b60ce15`. The ordered Claude range is
`e6384b7e67d03a3b3a1f690ec16c34cb194a4514`,
`072382b817274c72cc3e3a5c9fca327095dfa627`, and
`dd302570fe25654cc516d178cae7e2722138ce11`.

Counter-review branch: `codex/counterreview-sep1-contracts-20260822`, created
in an isolated worktree from the exact pushed Claude object.

**Outcome: accepted after correction.** Claude's code-review finding is
confirmed and its three rationale restorations are accurate. No product-code
correction was required. One P3 regression-coverage gap and two P3
documentation-precision issues are corrected; archived review history remains
unchanged.

## Independent reproduction

- The import scanner resolves no ambiguous import and reports exactly the four
  declared crossings:
  `assistant.explanations -> signals.breakout`,
  `assistant.explanations -> signals.scanner`,
  `assistant.strategy_proposals -> signals.regime`, and
  `assistant.strategy_proposals -> strategies.vol_target_rotation`.
- The shared roots import no product-owned module, the authority exception
  ledger is empty, and the focused boundary guards pass.
- Runtime aliases preserve the tested function and exception object identities.
  Existing `except ResearchReportError` behavior remains valid because the
  facade and canonical exception names resolve to the same object.
- The approved mandate fingerprint recomputes exactly as
  `693799c0acb440040064eaa69a57d87c32186e63709f49ffa52f6feb39956487`.
- Each restored rationale is present in the pre-move tree and accurate: bool
  rejection prevents `True`/`False` from becoming numeric metrics; rounding
  prevents binary-float truncation of a one-observation tail; and the regime
  calibration threshold must remain fixed after discovery.
- No provider, credential, licensed row, broker, database, task, deployment,
  backtest, outcome, research look, or evidence epoch was accessed.

## Commit dispositions

| Claude commit | Disposition | Reason |
|---|---|---|
| `e6384b7` | Accepted | The three comment/docstring restorations match the original locations and preserve behavior. |
| `072382b` | Accepted after correction | The substantive review and SEP1B-001 ledger are sound. Its compatibility-seam total says eleven although the enumerated set is twelve, and its serialization wording is broader than the evidence: same-object catch behavior is proven, but the moved exception now reports `data.portfolio_metrics.PortfolioMetricsError` rather than the old module/name metadata. Its manual identity census also exceeded the committed guard, which pinned only 8 of 12 function aliases and omitted the exception alias. The archived report is preserved; this counter-review, expanded regression guard, and active separation plan carry the corrections. |
| `dd30257` | Accepted after correction | The plan/handoff status is otherwise accurate. The handoff repeats the eleven-versus-twelve count and its current resume prompt retained the inherited blanket permission-letter blocker. Both are superseded by the dated counter-review handoff correction. |

## P0–P3 issue ledger

| ID | Priority | Status | Location | Issue and impact | Evidence | Correction | Verification |
|---|---|---|---|---|---|---|---|
| SEP1CCR-001 | P3 | Resolved | Claude review report; active separation plan; handoff §7di | The review enumerates twelve public compatibility seams but calls them eleven. It also describes serialization as preserved even though the exception's public catch identity is preserved while its `__module__`, `__name__`, and repr metadata changed. This does not alter runtime refusal/catch behavior, but it overstates the compatibility proof. | Runtime census: 2 mandate + 5 risk metric + 1 portfolio aggregation + 1 Bonferroni + 3 regime aliases = 12. `ResearchReportError is PortfolioMetricsError` is true; the object reports module/name `data.portfolio_metrics.PortfolioMetricsError`. | Current plan narrows the claim to same-object runtime type and exception-catching compatibility. This report and the new handoff section correct the count without retro-editing Claude's archived record. | Identity checks and focused suites pass. |
| SEP1CCR-002 | P3 | Resolved | Current ACER action plan, program plan, ACER-0A freeze, capability audit, and handoff resume prompt | Current records still treated a separate written-permission letter as an automatic ACER-2 blocker. That inherited Claude interpretation conflated an investment-advice disclaimer with a research/use restriction. It could block authorized personal research even when the purchase-specific terms already grant the intended processing. | Massive's current Analyst Ratings documentation explicitly lists “backtesting rating impact” as a use case. The quoted §11 language disclaims investment advice; it does not prohibit personal, non-commercial strategy research. The private order form/additional terms were not available to this review, so third-party cloud-processing permission remains a narrow verification, not a presumed prohibition or grant. | Current governing records now state the narrow rule. Archived review records remain unchanged. No upload, vendor audit, data work, backtest, or research look is authorized by the correction. | Active-document checks and repository text search confirm the current surfaces no longer require a permission letter merely because ACER tests a strategy. |
| SEP1CCR-003 | P3 | Resolved | `tests/test_project_separation_boundary.py::test_neutral_contract_compatibility_facades_preserve_identity` | Claude reports a manual runtime check of every facade, but the durable guard pinned only 8 of the 12 function aliases and omitted the exception alias. A later edit could split any of the four unguarded risk functions or break the old exception catch seam while the named compatibility test stayed green. | Direct test inspection and runtime identity census. The missing assertions were expected shortfall, time under water, downside capture, upside capture, and `ResearchReportError is PortfolioMetricsError`. | Expanded the existing dangerous-direction guard to pin all 12 function aliases plus the exception alias. | Focused boundary/document suite passes with the expanded assertions. |

Retained open: **CDR2-005 (P3)**, the boundary scanner's limited dynamic-import
coverage, remains deferred to the planned boundary evolution. It did not mask
an import in this range.

## Validation

- Focused separation/document/mandate/metric/regime/affected-caller suite:
  **253 passed / 0 failed / 1 warning** in 33.62 seconds.
- Complete repository suite: **4,499 passed / 0 failed / 25 warnings** in
  699.19 seconds.
- Required `compileall`, including `research/`: passed.
- `git diff --check`, final status/commit inspection, narrow secret scan,
  exact Claude remote-head recheck, and shared-checkout branch/HEAD/status
  verification: passed before handoff.

No SEP milestone completes in this counter-review, so
`docs/FEATURE_MILESTONE_RECORD.md` remains unchanged.

## Assessment

**9.0/10.** Claude found a real documentation-preservation defect, reproduced
the important behavior and authority invariants, and kept the correction
non-behavioral. The deductions are for a small but repeated arithmetic error,
an overbroad compatibility phrase, and a committed regression guard narrower
than the manual claim; none changes product behavior. The inherited licensing
blocker was not introduced by this review but needed correction because the
current handoff continued to present it as governing truth.
