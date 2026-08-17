# AI debate surface — design

**Status: DESIGN — not implemented pending user review.** No code ships
alongside this document. Nothing in `assistant/`, `risk/`, or `execution/`
changes until this design is accepted.

> **Relationship to the shipped committee (added 2026-07-30).** A different,
> narrower surface shipped since this was written: `assistant/llm/`, governed
> by `docs/architecture/ADR_INVESTMENT_COMMITTEE_BOUNDARY.md`. It is **one** reviewer
> examining **one** deterministically-generated risk-reducing candidate, and
> it does have a `verdict` field. That does not contradict §6/§7 below. The
> "no verdict field" constraint here is about refusing to *adjudicate between
> two model-generated positions* — the synthesis step that would turn a
> debate into a recommendation. The committee has no second position to
> adjudicate against; its verdict is bounded by deterministic checks (a
> supportive verdict requires a counterargument, an invalidation condition,
> and production-authoritative sources) and is advisory to a human approval
> that is still mandatory.
>
> The multi-position debate described below remains **unbuilt**. If it is
> built, §7's non-goals still apply to it, and the ADR's measured limitation
> on action-language filtering applies with more force, since N positions
> means N times the free prose to filter.

## 1. Why this document exists

Asked on 2026-07-30 whether the app has AI debate functionality. It does
not: there are exactly four `messages.create` call sites
(`assistant/ai_advisor.py:676`, `:739`, `:817` and
`assistant/news_summary.py:115`), each a single-shot request with no
follow-up turn, and no reference to debate, critique, adversarial framing,
bull/bear cases, or counterarguments anywhere in the codebase.

Its absence is a design consequence, not an oversight. The LLM in this
project is a prose layer over deterministic output — it phrases numbers
that `assistant/*.py` already computed, and is structurally unable to
reach a `TradeProposal` or `TradingPolicy`. A debate produces a
*conclusion*, and a conclusion is exactly the thing this architecture
declines to let a model produce. This document exists to describe the one
shape of debate that does not break that property, and to say plainly
which shapes do.

## 2. The governing distinction

**Debate over deterministic facts fits. Debate over what to do does not.**

- **Fits:** two grounded readings of the *same* `DecisionPacket` — one
  arguing the SOXX/SOXL concentration is the dominant risk, another
  arguing the 82% total exposure is — where every number in both readings
  appears in the deterministic packet.
- **Does not fit:** a bull/bear debate on whether a stock rises. That is
  stock-selection alpha, which this project does not claim and has 13
  rejected findings supporting its refusal to claim
  (`assistant/research_findings.json`).

If a proposed debate feature cannot be expressed as "two ways to read
numbers we already computed", it is out of scope for this design.

## 3. What's already reusable as-is

- **`assistant/ai_advisor.py::_reject_unsafe_prose(text, allowed_tickers,
  *, source_text)`** — the deterministic output guard. `source_text` is
  required and keyword-only as of 2026-07-30, so a new prose surface
  cannot silently ship ungrounded numbers; it fails with a `TypeError`
  instead. Its three checks (`_contains_action_language`,
  `_mentions_unknown_ticker`, `_unsupported_numbers`) apply unchanged to
  a debate position.
- **`assistant/ai_advisor.py::_record_run(...)`** — writes every model
  call to the `ai_runs` table with function name, prompt version, input
  hash, and duration. A debate must record one row per position, not one
  per debate, or the audit trail cannot show which side said what.
- **`assistant/risk_copilot.py`** — `check_concentration`,
  `find_correlated_clusters`, `estimate_stress_impact`,
  `portfolio_risk_decomposition`, `check_policy_compliance`. These are
  the deterministic facts a debate would argue over; all return computed
  structures, none call a model.
- **`assistant/portfolio_history.py::portfolio_performance_report`** —
  flow-adjusted return, volatility, drawdown, and benchmark-relative
  figures. The "how am I actually doing" half of the fact base.
- **`assistant/macro_context.py`** — the isolation precedent. It is
  imported only by `scripts/personal_assistant_ui.py` and
  `scripts/run_personal_assistant.py`, never by `assistant/proposals.py`,
  `assistant/policy.py`, or `risk/execution_gate.py`. A debate module
  must follow the same rule and be pinned by the same kind of test.

## 4. Architecture

```
DecisionPacket + risk_copilot outputs + performance report
        │
        └──> build_debate_facts()   ← deterministic, no model, no network
                    │
                    │  ONE fact block, used as BOTH the prompt input
                    │  AND the grounding source_text for every position
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
   position A               position B          (independent calls)
        │                       │
   _reject_unsafe_prose    _reject_unsafe_prose  (each vs the SAME facts)
        │                       │
        └───────────┬───────────┘
                    ▼
            display both, or neither
                 NO synthesis
```

New module `assistant/ai_debate.py`. Two positions to start; the shape
generalizes to N but N>2 multiplies cost with fast-diminishing returns.

## 5. The contamination rule — the load-bearing decision

There are two ways to build this, and only one is safe.

**Parallel framings (recommended).** Each position sees only the
deterministic fact block. They never see each other. This is not a
"debate" in the conversational sense — it is two independent readings,
presented side by side.

**Sequential rebuttal (rejected).** Position B sees position A's text and
responds to it. This is a real debate, and it breaks grounding: B's
`source_text` would have to include A's output, which means **any number A
fabricated becomes grounded for B**. The guard would certify B's
repetition of A's invention.

That is not hypothetical — it is the same defect already found and fixed
in this codebase on 2026-07-30, where headline text was treated as trusted
grounding and an injected headline could authorize its own invented
ticker. Sequential rebuttal reintroduces it deliberately.

**Rule: `source_text` is the deterministic fact block and nothing else,
for every position, always.** If a future variant wants rebuttal, B may
receive A's text as *prompt input* while still being grounded only against
the fact block — A's inventions then fail B's guard rather than passing it.
That is the only acceptable sequential form, and it is not in scope here.

## 6. Failure modes this design must handle

- **The balance illusion.** Presenting two positions implies both are
  equally supported. If the deterministic facts support one reading and
  not the other, manufacturing a counter-position is worse than showing
  one. **A position with no supporting facts must be suppressed, and the
  UI must say why** — not filled with a plausible-sounding alternative.
- **The synthesis temptation.** The obvious next feature is "and which
  side is right?" That is the whole thing this design exists to prevent.
  There is no third call. There is no verdict field in the output schema —
  not left empty, absent.
- **Anchoring by order.** Whichever position renders first is read as the
  default. Order should be derived from something deterministic (e.g. the
  magnitude of the cap breach each position addresses), not from call
  order, and the ordering basis should be stated in the UI.
- **Cost.** N positions is N× the calls. At Opus 5 pricing ($5/$25 per
  MTok) with the existing surfaces' token sizes, a two-position debate is
  roughly 2–3 cents. Button-gated, never on Streamlit rerun — the
  convention `scripts/personal_assistant_ui.py` already follows.
- **Partial failure.** If one position fails its guard and the other
  passes, showing the survivor alone silently converts a debate into a
  single recommendation. **Both or neither.**

## 7. Explicit non-goals

- **No verdict, winner, score, or confidence ranking** between positions.
- **No probability of return, price target, or directional call** on any
  ticker — already forbidden on every existing surface, restated here
  because a debate format invites it.
- **No path to proposals, policy, or the execution gate.** The module must
  not be imported by `assistant/proposals.py`, `assistant/policy.py`,
  `assistant/strategy_proposals.py`, or `risk/execution_gate.py`, pinned
  by a source-level test in the style of
  `tests/test_kill_switch_env.py::test_no_module_reimplements_the_check_inline`.
- **No new evidence status.** A debate position is not a research
  finding, never appears in `research_findings.json`, and never becomes
  `production_authoritative`.
- **No memory across debates.** Each is stateless against the current
  packet; no accumulating "the AI has been arguing X for weeks".

## 8. Testing requirements

Beyond ordinary unit tests, this surface needs the adversarial eval the
execution gate already has an equivalent of — a fixed set of inputs the
guard must reject on every CI run:

- A position citing a number absent from the fact block → rejected.
- A position naming a ticker not in the portfolio → rejected.
- A position phrased as advice ("trim SOXL") → rejected.
- A fact block supporting only one reading → the other is suppressed, and
  the suppression is visible, not silent.
- One position failing its guard → neither is displayed.
- A fact block containing NaN/inf → refused before any model call, in
  keeping with `build_portfolio_snapshot`'s boundary validation.

Every guard added must be mutation-verified — revert it, confirm its test
fails — per `.claude/skills/external-review-response/SKILL.md`.

## 9. Open questions for review

1. **Is parallel framing enough to be useful?** If the value you want is
   genuine back-and-forth, this design deliberately does not deliver it,
   and the honest answer may be that the safe version isn't worth
   building.
2. **What are the two axes?** "Concentration vs total exposure" is one
   candidate. Others: "risk now vs tax cost of reducing it" (the tax-lot
   ledger makes this computable), "your return vs the benchmark's".
3. **Should positions be fixed or model-chosen?** Fixed axes are
   auditable; model-chosen axes are more interesting and less pinnable.

## Change control

- **2026-07-30** — initial design, written in response to a question
  about whether debate functionality exists. Nothing implemented.
