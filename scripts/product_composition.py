"""Temporary composition seam between the two products during separation.

Entry points in ``scripts/`` are deliberately unclassified until SEP-2. This
module is therefore the one place that may call a research builder and pass its
immutable result into the trading assistant. Neither product imports this
module or the other product.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from assistant.explanations import explain_ticker
from assistant.policy import TradingPolicy
from assistant.schemas import DecisionPacket, MarketRegime, PortfolioSnapshot
from assistant.storage import AssistantStore
from assistant.strategy_proposals import (
    SOXX_SOXL_PAIR,
    LeveragedPairConfig,
    generate_leveraged_pair_rebalance_proposals,
    prepare_leveraged_pair_market_data,
)
from data.market_data import fetch_historical
from research.assistant_results import (
    build_leveraged_pair_research_result,
    build_ticker_signal_result,
)


def explain_ticker_with_research(
    ticker: str,
    portfolio: PortfolioSnapshot | None = None,
    lookback_days: int = 300,
    market_regime: MarketRegime | None = None,
    data: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    """Compose existing signal research with the assistant explanation."""
    canonical_ticker = ticker.upper()
    if data is None:
        data = fetch_historical([canonical_ticker], lookback_days=lookback_days)
    research_result = build_ticker_signal_result(canonical_ticker, data)
    return explain_ticker(
        canonical_ticker,
        portfolio=portfolio,
        market_regime=market_regime,
        signal_result=research_result,
    )


def _pair_is_held(packet: DecisionPacket, pair_config: LeveragedPairConfig) -> bool:
    held = {position.ticker.upper() for position in packet.portfolio.positions}
    return {
        pair_config.stable_ticker.upper(),
        pair_config.leveraged_ticker.upper(),
    }.issubset(held)


def generate_leveraged_pair_rebalance_proposals_with_research(
    packet: DecisionPacket,
    policy: TradingPolicy,
    pair_config: LeveragedPairConfig,
    ttl_minutes: int = 15,
    market_data: dict[str, pd.DataFrame] | None = None,
    store: AssistantStore | None = None,
):
    """Compose an input-bound research target with assistant proposal policy."""
    if not _pair_is_held(packet, pair_config):
        return generate_leveraged_pair_rebalance_proposals(
            packet,
            policy,
            pair_config,
            ttl_minutes=ttl_minutes,
            market_data=market_data,
            store=store,
            research_result=None,
        )

    prepared_data = prepare_leveraged_pair_market_data(
        pair_config,
        market_data=market_data,
        store=store,
    )
    research_result = build_leveraged_pair_research_result(
        stable_ticker=pair_config.stable_ticker,
        leveraged_ticker=pair_config.leveraged_ticker,
        market_data=prepared_data,
        production_params=pair_config.production_params,
    )
    return generate_leveraged_pair_rebalance_proposals(
        packet,
        policy,
        pair_config,
        ttl_minutes=ttl_minutes,
        market_data=prepared_data,
        store=store,
        research_result=research_result,
    )


def generate_soxx_soxl_rebalance_proposals_with_research(
    packet: DecisionPacket,
    policy: TradingPolicy,
    ttl_minutes: int = 15,
    market_data: dict[str, pd.DataFrame] | None = None,
    store: AssistantStore | None = None,
):
    """Backward-facing composition wrapper for the configured SOXX/SOXL pair."""
    return generate_leveraged_pair_rebalance_proposals_with_research(
        packet,
        policy,
        SOXX_SOXL_PAIR,
        ttl_minutes=ttl_minutes,
        market_data=market_data,
        store=store,
    )


__all__ = [
    "explain_ticker_with_research",
    "generate_leveraged_pair_rebalance_proposals_with_research",
    "generate_soxx_soxl_rebalance_proposals_with_research",
]
