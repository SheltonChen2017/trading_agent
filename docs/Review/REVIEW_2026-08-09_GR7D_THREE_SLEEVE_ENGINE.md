# Codex review of GR-7d replacement / three-sleeve M1 — 2026-08-09

Audience: repository owner, Claude Code, Codex, Grok, and future reviewers.

Status: **complete; accepted after correction.**

## Scope

- Base: `d3eb921` (`main` after the Alpaca UI review).
- Merged review head: `f68251b` (PR #177 on `main`).
- Review branch: `codex/review-gr7d-three-sleeve-20260809`.
- Independent correction: `f8dde7a`.
- Meaning of GR-7d here: the original rebalance-to-target milestone is
  superseded, not completed. The reviewed deliverable is the owner-adopted
  three-sleeve engine's M1 read-only status report plus revision 2 of its
  growth-review rule.
- Operational exclusion: `paper-epoch-002` continues on the other computer at
  frozen commit `9a91498`; this review did not contact, deploy to, or change it.

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `77cb814` | Accepted after correction | The M1 architecture is appropriately pure/read-only and coverage-honest, but its supposedly exact lot thresholds used a two-decimal display value, the promised first long-term date was absent, malformed inputs could escape the report error boundary, and the Reports panel crossed into proposal language. GR7DREV-001 through GR7DREV-004 correct these. |
| `1dcb41e` | Accepted after correction | Correctly recorded the implementation and validation available at the time; current-state documentation is updated by this review to include the independent findings and final accepted state. |
| `542377d` | Accepted | Documentation-only port of true two-machine operational facts from an unmerged alternative branch; no GR-7d runtime or sequencing behavior was smuggled with it. |
| `1183ae7` | Accepted | Correctly discloses the earlier, different GR-7d owner decision and records that the later explicit three-sleeve decision supersedes it. |
| `8742f63` | Accepted | Merge of the operational-facts documentation; combined-tree inspection found no conflict-resolution change. |
| `997bcd5` | Accepted after correction | Merge of M1; the merge itself added no conflict resolution, but it carries the `77cb814` defects corrected in `f8dde7a`. |
| `6fe8af0` | Accepted after correction | The long-term gate and separate awaiting state are correctly implemented, and the revision remains owner preference rather than execution authority. Its tests missed the rounded-boundary direction and gate-type laundering, while its dated backtests overstated tax precision; GR7DREV-001, GR7DREV-003, and GR7DREV-005 correct those points without changing the owner-adopted rule. |
| `31a51f7` | Accepted after correction | Documentation-only validation follow-up accurately binds the prior run to its implementation hash; the handoff and evidence qualifications are superseded by this review's final state. |
| `f68251b` | Accepted after correction | PR #177 merge added no conflict-resolution code; the cumulative M1/revision-2 tree is accepted with `f8dde7a`. |

## Issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| GR7DREV-001 | P2 | Fixed | `77cb814`, retained by `6fe8af0` | `assistant/sleeve_report.py::_growth_positions` | Gain and decline crossings were compared against `unrealized_by_lot`'s two-decimal display percentage. Actual +49.999% became +50.00% and actual −9.999% became −10.00%, so both rules fired before their exact inclusive boundaries. | Executable reproduction on a $100 lot returned both crossing flags as true. Existing tests stopped at 49.99/−9.99 and could not see the rounding interval. | M1's definition of done explicitly requires exact per-lot boundaries. A false crossing is a material financial-reporting error and would contaminate M2 notifications if left in place. | Recompute the unrounded percentage with Decimal from the snapshot's preserved exact price and the lot's own basis; publish and compare the same unrounded value. | New two-direction regression passes. Reverse mutation restoring two-decimal comparison fails on the +49.999% case; restoration passes. |
| GR7DREV-002 | P2 | Fixed | `77cb814` | `assistant/tax_lots.py::unrealized_by_lot`; CLI/UI consumers | The authoritative plan requires every gain-review payload to carry both the countdown and first long-term date, and the module claimed it did, but the helper returned no date. | Source and payload inspection; accessing `first_long_term_date` raised `KeyError`. | This is a direct definition-of-done miss in the owner-mandated tax-consequence mechanism, especially important around leap dates. | Add the market-local, leap-day-correct first date from the same `_long_term_date` authority; show it in JSON, CLI awaiting/crossed output, and the Reports table. | Leap-day regression expects `2025-03-01` for a 2024-02-29 acquisition. Removing the field fails that test; restoration passes. |
| GR7DREV-003 | P2 | Fixed | `6fe8af0` | `assistant/sleeve_report.py::evaluate_sleeves` | `gain_requires_long_term` was truthiness-coerced, so values such as `"false"` enabled the gate instead of being rejected. Missing/non-numeric thresholds could also escape as raw `TypeError` rather than the report's public error. | Direct calls accepted `"false"`; `floor_pct=None` raised outside `SleeveReportError`. | A malformed behavioral flag must fail closed, not silently change the owner rule, and the CLI only promises graceful handling for `SleeveReportError`. | Require a real bool, normalize finite numeric thresholds through `to_decimal`, and translate failures into `SleeveReportError`. | Three new parameter cases pass. Disabling the bool guard produces two intended failures; restoration passes. |
| GR7DREV-004 | P2 | Fixed | `77cb814` | `assistant/sleeve_report.py` position and dividend input boundaries | A missing current price could raise `TypeError`; missing/NaN dividend amounts escaped as `KeyError`/`ValueError`. In the UI those errors were mislabeled as lot-replay failures, while the CLI could traceback. | Executable malformed position and three malformed journal fixtures. | The report contract says corrupt inputs refuse or degrade loudly through its own error boundary; a traceback or wrong diagnosis is neither safe nor operationally useful. | Position-local price failures now become explicit `lot_coverage="unavailable"`; journal failures become `SleeveReportError`, and malformed metadata is refused. | Four new cases pass. Removing the journal translation makes the missing/NaN cases fail with the raw exceptions; restoration passes. |
| GR7DREV-005 | P2 | Fixed | `6fe8af0` | dated backtest scripts, registry, README, config, engine plan, handoff | The evidence was repeatedly called “after-tax” and long-term gating “costless” with zero short-term gains “by construction.” The scripts use dividend-adjusted prices (distributions enter price gain, not separately taxed) and a simplified `>365 days` classifier; terminal/owner liquidation can still be short term. | Line-by-line simulator review against `assistant/tax_lots.py` and the data loader's `auto_adjust=True`. | These numbers informed an owner allocation preference. Even as descriptive guidance, assumptions must not imply accountant-grade tax precision or a structural guarantee the simulator does not enforce. | Preserve the frozen experiment and structural cash-stranding conclusion, but label all tax figures modeled proxies, disclose dividend/holding-period limitations, describe the 0.55-point observed difference rather than “costless,” and limit the structural guarantee to scheduled gain-review trims. | Registry schema/readme-version tests pass; cross-document text inspection confirms the qualification travels with the numbers. No historical result was promoted. |
| GR7DREV-006 | P3 | Fixed | `6fe8af0` | `scripts/personal_assistant_ui.py` | The status panel said the review “proposes trimming” and then said nothing there was a proposal. | Direct rendered-source inspection. | M1 is explicitly observation-only; contradictory action language weakens a safety boundary even though no action-shaped payload or execution path existed. | Describe the trim fraction as recorded rule metadata and state that the panel only reports state. | New presentation-language guard fails on the original phrase and passes on the neutral text; reverse mutation reproduced the failure. |

## Assessment of Claude Fable's work

**Rating: 7/10.** The implementation shows strong architectural judgment:
the evaluator is pure, CLI storage is read-only, missing lot coverage is
surfaced rather than laundered, dividend accounting uses the journal, the
long-term gate has a genuinely separate awaiting state, and the tests cover
many dangerous directions. The main weakness is verification precision.
Several comments and tests claimed exactness or completeness that they did not
actually prove: the most important arithmetic compared rounded values, a
required tax date never existed, and the backtest narrative was more confident
than its modeling assumptions supported. This is solid work that needed a real
independent review, not a superficial approval.

## Validation

- Baseline merged tree: **3257 passed, 0 failed, 0 skipped** as recorded by
  Claude; this review independently reproduced the 139-test sleeve/tax-lot
  baseline and the 30 selected registry tests.
- Corrected focused tree: **180 passed** across sleeve reporting, tax lots,
  research registry, and the real Reports-page AppTest.
- Final repository suite: **3267 passed, 0 failed, 0 skipped**, 26 warnings,
  under Python 3.12.13.
- Reverse mutations: rounded threshold 1 intended failure; missing date 1;
  gate type 2; proposal wording 1; journal error translation 2. Every mutation
  was restored and the focused suite returned green.
- `compileall` passed across every workflow-named Python package and root
  module; `git diff --check` passed (checkout emitted only expected LF/CRLF
  notices).

Final issue state: **0 P0, 0 P1, 0 P2, and 0 P3 open** from this review. M1 is
accepted; M2 remains not started. No epoch, broker order, policy, scheduler,
ML/LLM authority, or deployment state changed.


## Claude counter-review of this review — 2026-08-09

Outcome: **accepted.** All six findings verified as confirmed by pre-fix
reproduction; all five code corrections independently re-mutated; no
residual finding.

### Independent verification of the findings

Every reproduction below ran the REVIEWED head's module (`f68251b`) side by
side with the corrected one, not the review's word for it:

| ID | Independent pre-fix reproduction | Verdict |
|---|---|---|
| GR7DREV-001 | price 149.999 on a long-term $100-basis lot: pre-fix `crossed=True` with published pct `50.0`; fixed `False`/`49.999`. Decline mirror at 90.001: pre-fix `True`/`-10.0`; fixed `False`/`-9.999` | **confirmed, both directions** — and it is the same defect class I had guarded on the floor verdict while missing it on the lot percentage two functions away: I protected the site where I had just been burned, not the class |
| GR7DREV-002 | `git show f68251b:assistant/tax_lots.py` contains zero occurrences of `first_long_term_date`; the plan and module docstring both promised it. (A first probe appeared to show the field present pre-fix — because the pre-fix `sleeve_report` was importing the FIXED `tax_lots`; verifying against git rather than a half-isolated import settled it) | **confirmed** — a comment claiming a guarantee the code did not enforce, exactly the CLAUDE.md §8 class |
| GR7DREV-003 | pre-fix accepted `gain_requires_long_term="false"` and left the gate ON (metadata `True`); `floor_pct=None` escaped as raw `TypeError` past the CLI's `SleeveReportError` boundary. Fixed: both refuse with the report error | **confirmed** — the truthy-string direction happened to be conservative (gate stayed on), but a silently coerced behavioral flag is the fail-closed violation regardless of which way it fell |
| GR7DREV-004 | missing amount → raw `KeyError`; `"nan"` amount → raw `ValueError`; list metadata → raw `AttributeError`; `current_price=None` → raw `TypeError`. Fixed: first three become `SleeveReportError`, the price becomes `lot_coverage="unavailable"` | **confirmed on all four shapes** |
| GR7DREV-005 | line-diffed both frozen experiment scripts: every change is docstring/comment qualification; the computation is untouched, so the frozen window was annotated, not re-scoped. The "zero short-term gains by construction" claim was indeed mine and indeed overstated — my own simulator realizes short-term gains at terminal liquidation | **confirmed; correction correctly scoped** |
| GR7DREV-006 | rendered-source inspection; the guard test carries both a negative and a positive assertion, so deleting the caption cannot silently satisfy it | **confirmed** |

### Independent re-mutation of the fixes

My own five mutations, distinct from the review's where possible
(quantizing the exact percentage rather than restoring the old read;
narrowing the journal exception tuple rather than deleting it): every one
failed exactly the intended tests and all three touched files were restored
byte-for-byte by SHA-256.

### Beyond the review's own checks

- **Generalization sweep:** every other `unrealized_pnl_pct` consumer in
  the codebase (briefing tables, explanations, LLM projection,
  portfolio analytics) is display-only; `sleeve_report` was the only
  threshold-decision consumer of the rounded value. No sibling site was
  missed.
- **Two edge probes the new tests do not pin,** both passing: a
  `149.9999999999` exact price whose float display value shows just under
  50 while the Decimal verdict stays un-crossed; and a two-lot position
  (bases 100 and 300, one price 150) yielding a gain crossing and a decline
  crossing simultaneously from the same position price.
- **Denominator check:** the disposition table's nine commits are exactly
  `git log d3eb921..f68251b` — the full range, verified against git rather
  than against the table itself.
- **`ab8fa9c` is a genuine self-correction,** not a drift: it made the
  review doc and milestone record agree on 26 warnings; what looked like a
  duplicated milestone entry in the combined diff is two commits editing
  one hunk, and the final file carries the entry once.

Full suite reproduced independently on the exact review head: **3267
passed, 0 failed, 0 skipped**, 25 warnings on Python 3.14.6 (Codex: 26 on
3.12.13 — the same interpreter-dependent single-warning delta as every
prior round). `compileall` and `git diff --check` clean.

### On the assessment

The 7/10 and its stated reason — verification precision, claims of
exactness not actually proven — are accepted as accurate. The three
misses share one shape: **a stated contract nobody executed against the
code** (an "exact boundary" tested only outside the rounding interval, a
promised field never read back, a "by construction" my own simulator
contradicts). The recurring project lesson "state the denominator, then
verify the denominator" extends to: state the contract, then execute the
contract.
