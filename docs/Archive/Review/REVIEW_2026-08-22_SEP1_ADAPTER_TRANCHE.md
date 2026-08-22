# Independent review — SEP-1 final research-result adapter tranche

Reviewed: 2026-08-22 by Claude.

Scope: exact remote `origin/codex/sep1-research-result-adapters-20260822` at
head `71d8500`, based on this reviewer's own prior head `dd30257`. Ordered
commits: `5fcdd41`, `43d49c7`, `c89a900`, `a57ab4e`, `a8c2b77`, `3785404`,
`71d8500`. The range contains both the counter-review of my second-tranche
review and the final SEP-1 implementation tranche; both are dispositioned
here.

Review branch: `user/claude/review-sep1-adapters-20260822`, created from the
exact pushed head.

**Outcome: accepted after correction.** No P0, P1, or P2. Two P3 findings,
both corrected here. The adapter tranche is the piece I predicted would be
the genuinely hard part of SEP-1, and it is done the way this repository
does things: refusals instead of defaults, hashes instead of trust, and the
authority chain untouched.

---

## What was verified independently

**The zero-edge claim reproduces.** My own scanner over the new tree finds
**zero** direct cross-product imports (4 → 0), **zero**
execution-authority-to-research paths, no product module importing
`scripts.*`, and `research.assistant_results` importing nothing from the
assistant. The manifest's two ledgers are empty because the coupling is
gone, not redefined: the remaining meeting point is
`scripts/product_composition.py`, which is exactly the "script-level
composition" `CLAUDE.md` §4 states as this repository's preferred endpoint,
and a new guard (`test_temporary_composition_seam_is_not_imported_by_either_product`)
pins that neither product may import the seam.

**The adapter fails closed in every direction that matters, and the assistant
does not take the research product's word for anything it can check itself.**
`_validated_research_target` re-derives the expected ticker pair, `as_of`
date, parameters SHA-256, and the exact close-series SHA-256s from data the
assistant itself loaded and validated, and refuses on any mismatch; a missing
result raises `MissingResearchResultError` rather than reading as "no
rebalance"; `explain_ticker` refuses a missing or wrong-ticker signal result
rather than rendering "no signal". The pair-not-held path returns `[]`
*before* any research-result use, so composition's `research_result=None` on
that path is unreachable by the validator — checked in source order, not
assumed.

**Behaviour is preserved where it moved.** The producer
(`research/assistant_results.py`) computes the identical trend →
vol-target sequence the assistant previously ran inline (same
`classify_trend` / trailing-volatility / `compute_target_leveraged_weight`
calls, same insufficient-history and downtrend labels, same
`min(last dates)` as-of and `.loc[:as_of]` slicing), and the explanation
trigger rows carry the same keys and 2-decimal rounding through
`SignalTriggerResult.to_dict()`. The UI/CLI swap is import-aliasing onto
composition wrappers that keep the old signatures, so both existing UI call
sites (including the Briefing double-fetch optimization) work unchanged, and
no assistant-internal caller of `explain_ticker` remains.

**The heavy input validation stayed on the assistant side.** Provider
failure, missing tickers, malformed frames, empty series, and the GR-4
staleness SLA all live in `prepare_leveraged_pair_market_data`, which is
assistant-owned — the research product computes measurements from data the
assistant has already refused-or-accepted. That is the right ownership.

**What the construction cannot prove, stated plainly:** binding hashes prove
the result was computed *for* those exact inputs, not that the target value
was computed *correctly from* them. The assistant no longer recomputes the
strategy. The trust level is unchanged from before the split — the same
first-party research code, previously imported directly — and every target
still flows into a proposal that the deterministic execution gate, policy
caps, and typed human approval validate. The authority chain is intact.

---

## Commit dispositions

| Commit | Disposition | Reason |
|---|---|---|
| `5fcdd41` | Accepted | Closes SEP1CCR-003 by pinning all 12 function aliases plus the exception alias. The expanded guard now matches the manual census. |
| `43d49c7` | Accepted | The counter-review of my round. All three findings against me are correct and I accept them: **SEP1CCR-001** — I enumerated twelve compatibility seams and called them eleven, my second arithmetic slip in two rounds; the serialization wording was also broader than my evidence (same-object catching proven; `__module__`/`__name__` metadata changed). **SEP1CCR-003** — my "manual check of every facade" exceeded the durable guard I shipped, which pinned 8 of 12. Both fixes are right. |
| `c89a900` | Accepted after verification | The licence-boundary correction (SEP1CCR-002). I verified the load-bearing factual claim at the source on 2026-08-22: Massive's Analyst Ratings documentation lists "Market sentiment tracking, portfolio alerts, **backtesting rating impact**, trend analysis" as use cases, and the page carries no restriction language. The rewrite keeps the operational gate fail-closed — "verify the order form and additional terms... must not claim either permission or prohibition... no upload is authorized by this correction" — and "any ratings representation" preserves the earlier breadth (raw, reconstructable, normalized, derived alike). What changed is the presumption, not the gate, and per the repository's own preserved audit (§5/§7: the Market Data ToS's applicability to this expansion was itself unresolved) the no-presumption posture is the honest epistemic state. The new doc-guard pins the narrow interpretation while forcing the verification sentence to remain. SEP1C-002 adds the dated verification note. |
| `a57ab4e` | Accepted | Handoff for the counter-review; no false state claims. |
| `a8c2b77` | Accepted after correction | The adapter implementation. Everything above verifies; SEP1C-001 covers the one untested refusal path. |
| `3785404` | Accepted | The completion record is honest: "not yet a reviewed milestone... No feature-milestone entry is recorded before that review chain closes." Correct restraint. |
| `71d8500` | Accepted | Handoff. Validation claims reproduce (full suite matches my independent run); the historical "local-only" hits are all in preserved history sections. |

---

## P0–P3 issue ledger

| ID | Priority | Status | Commit | Location | Issue and impact | Evidence | Reason for fix | Correction | Verification |
|---|---|---|---|---|---|---|---|---|---|
| SEP1C-001 | P3 | Resolved | `a8c2b77` | `assistant/strategy_proposals.py::_validated_research_target`; `tests/test_strategy_proposals_generic.py` | The assistant-side cap refusal — a research target above the pair's configured `max_leveraged_weight` must raise — had no regression coverage. The producer self-caps through `compute_target_leveraged_weight`, so **no honest fixture can reach the check with a violating value**, which is exactly how a dangerous-direction guard ends up untested: every existing test exercised it only with honest targets. A later refactor could delete the check with the whole suite green, and an over-cap result would then size a larger leveraged buy with only the downstream policy gate left to catch it. | Grep over both strategy-proposal test files: the only `max_leveraged_weight` references are fixtures computing honest targets. | This repository's testing rule is to pin the dangerous failure direction, and this is the one refusal in the new validator that the tamper tests (wrong history, wrong ticker, missing result, frozen contract) did not cover. | Added `test_assistant_refuses_research_target_above_the_configured_cap`: builds an honest result with valid bindings, `dataclasses.replace`s the target above the cap, asserts `ResearchResultContractError`. | Mutation: disabling the cap check turns the new test red; restored green; source byte-identical after the `finally`. Focused file 8/8. |
| SEP1C-002 | P3 | Resolved | `c89a900` | `docs/research/ACER_2026-08-20_ACER0A_FREEZE.md` | The loosened licence presumption rests on a claim about a live vendor page ("backtesting rating impact"), now load-bearing in four current documents and pinned by a test — with no byte preservation and no dated verification record. The repository's own audit preserved ToS bytes for exactly this reason ("ToS pages change without notice"), and the wire-format lesson is to verify claims at the source. | The claim appeared in-repo with no URL, date, or quote of the surrounding list. | A licence-boundary presumption should not rest on an unpreserved, undated web claim. Cheap to fix now; expensive to litigate later when the page has changed. | Added a dated verification note to the freeze bullet: URL, the full quoted use-case list, the absence of restriction language on the page, and an instruction to re-verify or preserve bytes before any preregistration relies on the quote. | Verified live 2026-08-22 via direct fetch of the Massive documentation page; doc guards 53/53 after the edit. |

Retained open: **CDR2-005 (P3)** — unchanged disposition. No dynamic import
masked anything in this range.

**Observations recorded without a change:**

- `LeveragedPairResearchResult` enforces only `>= 0` and finite on the
  target; the upper bound is deliberately the *assistant's* check against its
  own configured cap (now regression-pinned). That is the right place — the
  contract stays policy-free — recorded so nobody later "hardens" the
  contract with a policy number.
- Composition's `_pair_is_held` duplicates the generator's holding rule. If
  they ever drift, the failure direction is loud
  (`MissingResearchResultError`), not silent — acceptable.
- The c89a900 doc-guard splits the handoff at a literal section heading;
  a rename breaks the split loudly (IndexError), not vacuously — acceptable.

---

## SEP-1 definition-of-done assessment

Against the plan's SEP-1 milestone: the authority path was removed first
(tranche 1); neutral schemas and financial primitives extracted (tranches
1–2); assistant-to-research calculation imports replaced with typed,
read-only, input-bound research results (this tranche); ledger edges removed
rather than exceptions broadened (13 → 9 → 4 → **0**); and proposal,
approval, execution, and reconciliation authority stayed solely in the
trading assistant. **The implementation side of SEP-1 is complete.** Per the
rule the submitted tree itself records, SEP-1 is *marked* complete — and the
feature-milestone entry written — only after Codex counter-reviews this
review's corrections. `scripts/` classification (including the temporary
composition seam's permanent home) is SEP-2.

## Safety and authority disposition

- Paper mode, typed approval, kill switch, atomic claiming, reconciliation:
  untouched; no execution-capable module changed.
- Authority-to-research paths remain zero, verified independently; the new
  seam guard and zero-edge guard are mutation-tested (Codex's) and the cap
  refusal now is too (mine).
- ML/LLM boundaries unchanged; research results are observations feeding
  APPROVE-gated proposals through the unchanged deterministic gate.
- ACER: the licence correction changes a *presumption*, not an authorization
  — no upload, no provider call, no outcome join, no backtest, no research
  look is authorized, and the QC scope limit and open owner decisions stand.
- `paper-epoch-006` undisturbed. No vendor API beyond one read-only public
  documentation-page fetch (no credential, no data endpoint); no broker,
  database, task, or deployment touched.

## Validation

Recorded in handoff section 7dl with exact counts.

## Assessment

**9.5/10.** The hard tranche, done right: input-bound results, refusal on
every mismatch the assistant can check, ownership of validation kept on the
authority side, honest completion framing, and a counter-review of my own
work whose every finding I accept. The half point: the one refusal path only
a dishonest producer can reach was the one refusal path without a test —
the exact blind spot this repository's mutation discipline exists to catch.
