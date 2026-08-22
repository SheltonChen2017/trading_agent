# Independent review — SEP-1 second extraction tranche (neutral research contracts)

Reviewed: 2026-08-22 by Claude.

Scope: exact remote `origin/codex/sep1-research-contracts-20260821` at head
`52f4c2f`, merge base `origin/main` at `d97d1d8`, ordered commits `636d164`,
`e36f480`, `52f4c2f`. Reviewed together with the three adjacent SEP-1
counter-review commits already merged in PR #298 (`9949983`, `af4f83e`,
`92b9a1b`), because they revise this reviewer's own prior corrections and had
no formal disposition from me yet.

Review branch: `user/claude/review-sep1-contracts-20260821`, created from the
exact pushed head.

**Outcome: accepted after correction.** No P0, P1, or P2. One P3, corrected
here. This is the largest calculation move of the separation so far —
mandate evaluation, portfolio risk metrics, the multiplicity statistic, and
regime measurement — and it is the cleanest tranche yet.

---

## What was verified independently, not taken from the submission

**Every moved function was AST-compared, ex-docstring, old tree against new.**
Thirteen functions moved across four extractions (mandate → 3, risk metrics →
6, engine → 1, regime → 3) plus `compute_portfolio_metrics` out of
`research_report`. Every difference decomposes into: annotation-only changes
(the new `MandateMetricContract` Protocol; a refined return annotation),
local-variable renames, temp-variable folds, one reworded `ValueError`
message no test pins, and one benign `float()` cast. **No control flow,
validation rule, boundary condition, or numeric expression changed.**

**The owner's approved mandate fingerprint is stable.**
`compute_mandate_fingerprint(load_mandate())` still equals the
`approved_fingerprint` stored in `assistant/default_mandate.json`
(status `approved`). The move could not silently invalidate the 2026-08-04
approval, and did not: the excluded metadata fields, canonical JSON
parameters, and hash are byte-identical, and the split keeps approval,
persistence, defaults, and promotion gates in the assistant while sharing
only the arithmetic.

**Exception identity is preserved by the strongest mechanism available.**
`compute_portfolio_metrics`'s refusal paths now raise
`PortfolioMetricsError`; `backtest/research_report.py` imports it **as**
`ResearchReportError`, so they are the *same object* — every existing
`except ResearchReportError` still catches, verified by raising through the
new path and catching under the old name. The base class is unchanged
(`ValueError` before and after, checked at `d97d1d8`).

**Facade identity holds at runtime for all eleven public seams** —
mandate fingerprint/evaluation, the five risk metrics,
`compute_portfolio_metrics`, `bonferroni_threshold`, and the three regime
functions — and the pre-existing `strategies.leverage_rotation` delegation
wrapper still reaches the canonical implementation (it was a wrapper before
this tranche, not a re-export; not a finding).

**The census and the authority boundary reproduce.** An independent scanner
finds exactly the **4** declared cross-product edges (down from 9) and
**zero** execution-authority-to-research paths. The four new/expanded shared
modules (`data/mandate_evaluation.py`, `data/portfolio_metrics.py`,
`data/research_statistics.py`, `market_analytics.py`) import **no** product
code. Mutation: restoring the removed
`assistant.research_looks -> backtest.engine` crossing turns the census guard
red; restored green, file byte-identical.

---

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `9949983` (PR #298) | Accepted | SEP1CR-001's fix to my guard. Verified by guard-swap: my guard passed against my own documents while Codex's failed against the same documents — my `assert current in text` was vacuous against a 344 KB handoff. Codex's canonical-marker approach keeps my no-literal-milestone-id property. One precision recorded: the guard requires the right statement in the right surfaces; it does not detect a stale instruction as such (an injected "review branch X" sentence passes both guards). Right finding, right fix. |
| `af4f83e` (PR #298) | Accepted | SEP1CR-002 is correct arithmetic: my report said five assistant→research calculation/context edges while my own parenthetical listed six. Six plus three is the manifest's nine. My historical report stands uncorrected per the retro-edit rule; the counter-review is the durable correction. |
| `92b9a1b` (PR #298) | Accepted | Handoff record; no false state claims. |
| `636d164` | Accepted after correction | The extraction. All equivalence, identity, fingerprint, and direction checks above pass. SEP1B-001: three load-bearing rationales did not survive the move. |
| `e36f480` | Accepted | The plan record is the best-written of the series: it names the policy line this reviewer was probing — "putting their calculations in the shared kernel would hide product policy rather than separate it" — and correctly classifies the four remaining edges as policy-heavy adapter work, not moves. |
| `52f4c2f` | Accepted | Handoff. No merge-state claims that its own push falsifies — the CCR-005 class did not recur. |

---

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SEP1B-001 | P3 | Resolved | `636d164` | `data/mandate_evaluation.py`, `data/portfolio_metrics.py`, `market_analytics.py` | Third consecutive tranche in which moved code arrives intact and its recorded *reasons* do not. Genuinely lost this time: (a) `_metric_check`'s "Independent review, 2026-07-31 (P2 #5)" comment explaining why booleans are rejected before `float()` — `isinstance(True, int)` is True, so a stray bool would silently score as 0.0/1.0; (b) `expected_shortfall_pct`'s round-before-int comment — `1.0 - 0.9 == 0.09999999999999998`, so without `round(..., 8)` an intended tail_size of 1 truncates to 0; (c) `calibrate_volatility_threshold`'s discipline sentence — apply the SAME fitted value to confirmation dates, never recalibrate — which is the look-ahead rule that justifies the function's existence, now absent from its canonical location. | Textual comparison of old function bodies/comments against the new modules; repo-wide grep for the provenance markers in the new files returns zero hits. | Each comment is a defect a review round paid for, invisible from the code alone. (c) is the exact discipline `CLAUDE.md` §6 mandates, at the one place a future caller will actually read. | All three restored at the new canonical locations, marked as restorations so the loss is visible. Graded P3 rather than repeating SEP1R-001's P2: this tranche demonstrably tried — `_capture_pct` kept its joint-masking rationale (reworded, with the reproduced 50%→16.67% figure), and `expected_shortfall_pct` *gained* a good fails-closed docstring — so the class is narrowing, not repeating wholesale. | Focused suites green after the edits (89 + boundary); fingerprint re-verified stable; no behaviour touched. |

Retained open: **CDR2-005 (P3)** — unchanged disposition, deferred to boundary
evolution.

**Observations recorded without a change:**

- **The shared kernel grew by three modules**, while plan §2 says the shared
  surface "must shrink **or be split as ownership becomes clear**". This
  tranche is the second clause happening: what moved is caller-parameterized
  measurement (trailing vol, threshold classification, metric arithmetic,
  fingerprint hashing), and the plan's new policy line explicitly fences off
  policy-carrying code from the same treatment. The SEP-0 ledger's per-edge
  remedy notes ("migrate behind a research-result adapter") were superseded
  for the regime edges by this documented, better-reasoned decision; the notes
  died with their ledger entries, and the plan narrative is the surviving
  record — acceptable, noted so nobody hunts for a missing adapter later.
- `_capture_pct`'s index-mismatch `ValueError` text was reworded; no test or
  caller pins the old wording; the fail-closed behaviour is identical.
- `assistant.strategy_proposals -> signals.regime` deliberately remains in the
  ledger even though the implementation moved to shared: the *module* it
  imports is research-owned, so the census honestly still counts it. Its
  removal belongs to the strategy-proposals adapter work.

---

## Safety and authority disposition

- No proposal, approval, execution, reconciliation, broker, or policy
  behaviour changed; the moved code is AST-equivalent and the mandate
  fingerprint binding is proven stable against the stored approval.
- Execution-authority-to-research paths remain **zero**, verified
  independently; the census guard catches a restored crossing (mutation red).
- ML/LLM boundaries unchanged; `test_ml_import_boundary.py` green.
- ACER untouched; the capability-audit authorization remains open and
  fail-closed. `paper-epoch-006` undisturbed. No vendor, broker, credential,
  operator database, task, or deployment was accessed by the work or review.
- No milestone completed: SEP-1 remains in progress with four policy-heavy
  edges left; `docs/FEATURE_MILESTONE_RECORD.md` correctly unchanged.

## Validation

Recorded in handoff section 7di with exact counts.

## Assessment

**9.5/10.** Ten of ten on mechanics: fingerprint-stable mandate split,
same-object exception aliasing, honest ledger handling of the regime facade
edge, a mutation-verified census, and a plan record that states the
shared-vs-policy line better than my own review had. The half point off is
the rationale-loss class recurring a third time — narrower each round, but
still requiring a reviewer to carry the project's memory back in.
