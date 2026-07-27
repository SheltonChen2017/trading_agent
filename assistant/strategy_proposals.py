"""
Proposal generator for the one validated non-risk-reduction idea in this
project: continuous inverse-volatility-targeted rotation between SOXX
(stable) and SOXL (leveraged), using a WIDE (15%) rebalance band. See
assistant/research_findings.json for the underlying evidence:

  - "Wide rebalance band vs. tight/continuous vol-targeting" (CONFIRMED):
    ~89% less tax/turnover for essentially the same performance as
    continuous vol-targeting.
  - "SOXX/SOXL trend+volatility regime rotation -- drawdown" (CONFIRMED):
    the underlying rotation mechanism reduces max drawdown vs 50/50
    buy-and-hold.
  - "SOXX/SOXL trend+volatility regime rotation -- return" (REJECTED),
    and memory: project_vol_target_rotation -- NONE of the 5 pairs
    tested (including SOXX/SOXL) beat buy-and-hold on CAGR. This is a
    RISK-SHAPE trade (less drawdown, less tax drag), not an alpha claim.
    Never represent a proposal from this module as "beats buy-and-hold."

PRODUCTION_PARAMS was chosen by grid-searching Calmar ratio (CAGR /
|max drawdown|) on the FULL available SOXX/SOXL history (not a held-out
confirmation split -- there's no more history left to hold out for a
live-forward config). That makes these SPECIFIC numbers in-sample /
unconfirmed even though the underlying wide-band MECHANISM is confirmed
research. Every proposal this module generates is tagged
evidence_status="promising_unconfirmed_strategy", never "confirmed", for
exactly this reason -- see the disclosure in `uncertainties` on each
proposal.

Deliberately scoped to REBALANCING an existing SOXX+SOXL allocation
only. It never proposes opening a first position in either ticker -- if
the account doesn't already hold BOTH, this generator returns nothing.
TradingPolicy.allow_new_positions stays False project-wide; nothing here
needs or requests an exception to it. Every proposal still goes through
the same TradeProposal -> "APPROVE <id>" -> execution_gate pipeline as
risk-reduction proposals; policy limits and human confirmation are
untouched.

Single-leg per call, by design: proposes at most ONE trade (whichever
leg needs to move to close the gap to target) rather than bundling a
simultaneous two-leg rebalance. A sell's proceeds aren't reflected in
the account snapshot until settlement, so a same-pass paired buy could
be validated against stale cash. Re-running the CLI's `propose` command
after an approval naturally converges toward the target over successive
cycles -- the same pattern the risk-reduction generator already relies
on.

Also a simplification worth naming: the original backtest only checks
for a rebalance every `rebalance_check_days` (21) SIMULATED trading
days from an arbitrary start. There's no equivalent fixed counter here
-- each time a caller runs this (e.g. each `propose` invocation), that
IS the check. Running it far more often than every ~21 trading days
will trigger rebalances the backtest never actually modeled at that
frequency.
"""
from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime, timedelta, timezone

import pandas as pd

from data.market_data import fetch_historical
from signals.regime import compute_trailing_market_volatility
from strategies.trend_vol_rotation import classify_trend
from strategies.vol_target_rotation import compute_target_leveraged_weight
from assistant.policy import TradingPolicy
from assistant.portfolio_analytics import preview_trade_impact
from assistant.proposals import TradeProposal
from assistant.schemas import DecisionPacket
from risk.execution_gate import TradeIntent

STABLE_TICKER = "SOXX"
LEVERAGED_TICKER = "SOXL"
LOOKBACK_DAYS_FOR_SIGNAL = 300  # comfortably covers trend_lookback_days=200 plus warmup

PRODUCTION_PARAMS = {
    "target_vol_pct": 0.5,
    "max_leveraged_weight": 0.6,
    "band_pct": 15.0,
    "trend_lookback_days": 200,
    "vol_lookback_days": 20,
}

EVIDENCE_STATUS = "promising_unconfirmed_strategy"


def _stable_id(packet: DecisionPacket, policy: TradingPolicy, intent: TradeIntent) -> str:
    raw = (
        f"soxx_soxl_rebalance|{packet.portfolio.as_of}|{policy.version}|{intent.ticker.upper()}|"
        f"{intent.side}|{intent.shares}"
    )
    return "tp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _target_leveraged_weight(stable_close: pd.Series, leveraged_close: pd.Series, as_of: pd.Timestamp) -> tuple[float | None, str]:
    """Returns (target_leveraged_weight, label). None if not computable
    (insufficient history) -- caller should skip generating a proposal."""
    trend = classify_trend(stable_close, as_of, lookback_days=PRODUCTION_PARAMS["trend_lookback_days"])
    if trend is None:
        return None, "insufficient_trend_history"
    if trend == "downtrend":
        return 0.0, "downtrend_defensive"

    leveraged_df = pd.DataFrame({"close": leveraged_close})
    realized_vol = compute_trailing_market_volatility(leveraged_df, as_of, lookback_days=PRODUCTION_PARAMS["vol_lookback_days"])
    if realized_vol is None:
        return None, "insufficient_volatility_history"

    target = compute_target_leveraged_weight(
        realized_vol, PRODUCTION_PARAMS["target_vol_pct"], PRODUCTION_PARAMS["max_leveraged_weight"]
    )
    return target, f"uptrend_vol_target(realized={realized_vol:.2f}%)"


def generate_soxx_soxl_rebalance_proposals(
    packet: DecisionPacket,
    policy: TradingPolicy,
    ttl_minutes: int = 15,
    market_data: dict[str, pd.DataFrame] | None = None,
) -> list[TradeProposal]:
    """
    At most one proposal: rebalance SOXX/SOXL toward the target leveraged
    weight if drift exceeds the 15% band. Returns [] if either ticker
    isn't currently held, if history is insufficient to compute a
    target, or if the account is already within the band.

    `market_data` lets a caller/test inject price history instead of
    hitting the network; production callers can omit it.
    """
    snapshot = packet.portfolio
    position_by_ticker = {p.ticker.upper(): p for p in snapshot.positions}
    stable_position = position_by_ticker.get(STABLE_TICKER)
    leveraged_position = position_by_ticker.get(LEVERAGED_TICKER)
    if stable_position is None or leveraged_position is None:
        return []

    combined_value = stable_position.market_value + leveraged_position.market_value
    if combined_value <= 0:
        return []

    if market_data is None:
        market_data = fetch_historical([STABLE_TICKER, LEVERAGED_TICKER], lookback_days=LOOKBACK_DAYS_FOR_SIGNAL)
    if STABLE_TICKER not in market_data or LEVERAGED_TICKER not in market_data:
        return []
    stable_close = market_data[STABLE_TICKER]["close"]
    leveraged_close = market_data[LEVERAGED_TICKER]["close"]
    if stable_close.empty or leveraged_close.empty:
        return []
    as_of = min(stable_close.index[-1], leveraged_close.index[-1])

    target_leveraged_weight, label = _target_leveraged_weight(stable_close, leveraged_close, as_of)
    if target_leveraged_weight is None:
        return []

    current_leveraged_weight = leveraged_position.market_value / combined_value
    drift_pct = abs(current_leveraged_weight - target_leveraged_weight) * 100
    if drift_pct <= PRODUCTION_PARAMS["band_pct"]:
        return []

    target_leveraged_value = combined_value * target_leveraged_weight
    now = datetime.now(timezone.utc)

    if leveraged_position.market_value > target_leveraged_value:
        excess_value = leveraged_position.market_value - target_leveraged_value
        shares = min(int(leveraged_position.shares), int(excess_value / leveraged_position.current_price))
        side = "sell"
        reason = (
            f"{LEVERAGED_TICKER} is {current_leveraged_weight * 100:.1f}% of the SOXX+SOXL allocation, "
            f"{drift_pct:.1f} points outside the {PRODUCTION_PARAMS['band_pct']:.0f}% band around the "
            f"{target_leveraged_weight * 100:.1f}% target ({label})."
        )
    else:
        shortfall_value = target_leveraged_value - leveraged_position.market_value
        max_order_shares = int(policy.max_order_value / leveraged_position.current_price)
        shares = min(max_order_shares, int(shortfall_value / leveraged_position.current_price))
        side = "buy"
        reason = (
            f"{LEVERAGED_TICKER} is {current_leveraged_weight * 100:.1f}% of the SOXX+SOXL allocation, "
            f"{drift_pct:.1f} points below the {PRODUCTION_PARAMS['band_pct']:.0f}% band around the "
            f"{target_leveraged_weight * 100:.1f}% target ({label}). Sized against currently available "
            f"cash/order-value limits -- may only partially close the gap in one pass."
        )

    if shares <= 0:
        return []

    intent = TradeIntent(
        ticker=LEVERAGED_TICKER,
        side=side,
        shares=shares,
        order_type="market",
        rationale=reason,
    )
    proposal_id = _stable_id(packet, policy, intent)
    return [
        TradeProposal(
            proposal_id=proposal_id,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=ttl_minutes)).isoformat(),
            status="proposed",
            idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
            policy_version=policy.version,
            intent=intent,
            reference_price=leveraged_position.current_price,
            price_timestamp=now.isoformat(),
            reasons=[reason],
            evidence_status=EVIDENCE_STATUS,
            expected_impact=preview_trade_impact(
                snapshot, LEVERAGED_TICKER, side, shares, leveraged_position.current_price
            ),
            alternatives=[
                "Take no action -- drift outside the band costs tax-efficiency, not immediate risk.",
                "Rebalance manually to a different target than this strategy's frozen production parameters.",
                "Re-run the grid search on updated history before trusting these exact parameters again.",
            ],
            uncertainties=[
                "PRODUCTION_PARAMS (target_vol_pct=0.5, max_leveraged_weight=0.6) were selected via "
                "full-history grid search, not an out-of-sample confirmation split -- these specific "
                "numbers are unconfirmed even though the wide-band mechanism itself is confirmed research.",
                "This strategy has NOT been shown to beat SOXX/SOXL buy-and-hold on CAGR in any tested "
                "configuration -- it is a risk-shape (drawdown/tax) trade, not an alpha claim.",
                "Single-leg proposal: only SOXL is adjusted this pass. SOXX's own weight will look "
                "correspondingly off-target until cash/proceeds settle and a later `propose` run rebalances it.",
                "Market orders can fill away from the displayed reference price.",
            ],
        )
    ]
