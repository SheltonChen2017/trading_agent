# Reusable allocation service — design

**Status: DESIGN — not implemented pending user review.** The only code
change shipped alongside this document is the `strategy_evaluations`
storage table (`assistant/storage.py`) and its wiring into
`assistant/strategy_proposals.py::generate_soxx_soxl_rebalance_proposals`
-- a small, bounded, low-risk piece of bookkeeping this design also
depends on. No scheduler, no new allocation logic, no autonomous order
submission is implemented here.

## 1. Why this document exists

The current Watchlist allocation feature (`scripts/personal_assistant_ui.py`)
is **user-directed inverse-volatility splitting**, not market-volatility-
driven allocation: the user manually picks tickers, manually enters a
dollar amount, and per-ticker volatility determines the RELATIVE split —
market-wide volatility does not determine the TOTAL amount deployed. A
2026-08 GPT review asked for a concrete design for a more automated,
reusable allocation service before any of that gets built. This document
is that design, scoped against what already exists in this codebase
rather than proposed from scratch.

## 2. What's already reusable as-is

- **`assistant/allocation_batch.py`**'s `preflight_allocation_batch()` /
  `execute_allocation_batch()` / `AssistantStore.create_allocation_batch()`
  — confirmed fully generic: they operate on `proposal_ids`/`batch_id`
  plus a generic `TradingPolicy`/`PortfolioSnapshot`, with zero
  Watchlist-specific coupling in the logic itself (only in naming/
  docstring framing). A new service's proposal generator can feed
  `proposal_ids` into this exact same resumable-batch-execution backend
  with no changes to it.
- **`assistant/stock_lookup.py`**'s `inverse_volatility_weights()` /
  `compute_blended_volatility()` — pure functions (math/pandas only, no
  Streamlit/DB/network side effects), already reusable outside the UI.
- **`signals/regime.py`**'s `classify_regime(benchmark_df, as_of,
  threshold_pct, lookback_days=...)` — a genuinely MARKET-WIDE (not
  per-ticker) high-vol/low-vol classifier, a valid input for a
  market-vol-driven total-exposure sizing rule.
- **`assistant/strategy_evaluations` table** (shipped alongside this
  document) — persisted last-evaluated-at + result JSON, keyed by a
  strategy name. Designed to be reused by this future service under its
  own key (e.g. `"allocation_service"`), not just by the SOXX/SOXL
  generator.

## 3. The rebalance-vs-just-spend gap

`assistant/allocation_proposals.py::build_allocation_plan()` computes
`target_dollars = dollar_amount * weight_pct / 100` per ticker **from
scratch** — it does not reduce the target based on existing positions or
pending orders; those are only used to compute a POST-trade projected
percentage for display/limit-distance purposes. It answers "how do I
split this NEW dollar amount," not "how do I move my CURRENT portfolio
toward a target weight."

A rebalancing allocation service needs a different primitive:
`target_dollars_per_ticker - current_position_value_per_ticker = delta`,
clamped so a negative delta either becomes a sell leg or is treated as
"no action" depending on whether sell-leg support is in scope (see §6 —
`allocation_batch.py`'s docstring today frames legs as "N independent buy
proposals," so extending it to mixed buy/sell legs is itself a design
decision, not a given).

## 4. Where the live market-vol threshold comes from

`classify_regime()`'s `threshold_pct` is not a fixed constant — it must
be supplied, and the honest way to get it (per `signals/regime.py`'s own
existing `calibrate_threshold_from_discovery()`) is fit on a discovery
period, not tuned after seeing live results. For a LIVE service (not a
backtest), this raises a question the SOXX/SOXL generator never had to
answer: is the threshold computed once and frozen, or recomputed on some
cadence?

Recommendation: compute once per calibration event, store it via
`strategy_evaluations` (e.g. `strategy_key="allocation_service_regime_threshold"`,
`last_result={"threshold_pct": ..., "calibrated_through": ...}`), and
require an explicit, user-triggered recalibration command rather than
silent drift — staleness should be surfaced (e.g. "this threshold was
calibrated N days ago, consider recalibrating") rather than silently
degrading.

## 5. Cadence

Reuse the `strategy_evaluations` table shipped with this document as the
persistence layer for this service's own last-evaluated state, under its
own `strategy_key` — one mechanism, two consumers (the existing SOXX/SOXL
generator and this future service), rather than inventing a second
cadence-tracking scheme.

Explicitly **CLI/manual-trigger only** in this design — no literal OS
scheduler (cron/systemd) is proposed. This matches `docs/MANDATE.md`'s
already-stated "event-driven, not calendar-driven" rebalancing stance
(§2, Rebalancing frequency row). A future scheduler, if ever wanted, would
call the same CLI/proposal-generation entry point this design specifies
below — it would not need its own allocation logic.

## 6. Universe selection and sizing-rule shape (sketch, no code)

- **Candidate universe**: a new, explicit config list — similar to how
  `config.DEFENSIVE_CARRY_TICKERS` was deliberately kept OUT of
  `UNIVERSE`/`BASKETS` — rather than assuming the full `UNIVERSE` or an
  existing basket is automatically in scope for automated allocation.
  Membership in this new list should not itself be an allocation
  authorization, same discipline as `DEFENSIVE_CARRY_TICKERS`.
- **Total exposure sizing**: market-vol-driven total exposure could
  compose with `TradingPolicy.max_total_exposure_pct` in one of two
  shapes — (a) a multiplier applied AT proposal-generation time (e.g.
  "deploy `max_total_exposure_pct * regime_scalar`"), computed by the
  service and passed through as an ordinary proposal, going through the
  existing policy caps unchanged; or (b) a distinct policy-level field
  the execution gate itself understands. (a) is lower-risk — it reuses
  `risk/execution_gate.py`'s existing caps as the enforcement backstop
  rather than adding a new enforcement path — and is the recommended
  starting shape.
- **Sell-leg support in `allocation_batch.py`**: open question, not
  resolved here. If §3's rebalance-toward-target logic needs to trim
  existing positions, `allocation_batch.py`'s current buy-only framing
  needs either a documented scope decision to exclude sells from this
  service (simplest — new money only, positions can only grow toward
  target, never shrink automatically) or an actual extension to the batch
  leg model. Recommend the simplest option (buy-only, no automated
  trimming) for a first version.

## 7. Explicit non-goals for this design

- No autonomous order submission — every proposal this service would
  generate still goes through the existing explicit-approval workflow
  (`execution_service.py`'s claim → validate → authorize → submit state
  machine), unchanged.
- No new `TradingPolicy` scheduling fields — cadence data belongs in
  storage ("what happened"), not policy ("what's allowed"); conflating
  the two would make policy files carry mutable runtime state, which the
  rest of this project deliberately avoids (policy is loaded fresh and
  fingerprinted per proposal).
- No literal scheduler process — CLI-triggered only, per §5.
- No claim that `classify_regime()`'s threshold or this service's sizing
  rule is validated research — this document is architecture, not a
  research finding; any such claim would need its own entry in
  `research_findings.json` following this project's existing
  out-of-sample/confirmation-only/by-block rigor discipline before being
  trusted.

## Change control

- **2026-07-28** — initial design, written alongside the
  `strategy_evaluations` storage addition. Not implemented beyond that
  one table/wiring.
