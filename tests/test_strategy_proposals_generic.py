"""Tests for the generic leveraged-pair research/assistant composition.

Confirms the temporary composition adapter is ticker-agnostic and that the
SOXX/SOXL adapter delegates without divergent behavior. Uses hand-injected
market data (no network).
"""
import dataclasses
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pytest

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import TradingPolicy
from assistant.schemas import DecisionPacket, MarketRegime
from assistant.storage import AssistantStore
from assistant.strategy_proposals import (
    CONFIGURED_LEVERAGED_PAIRS,
    LEVERAGED_TICKER,
    PRODUCTION_PARAMS,
    SOXX_SOXL_PAIR,
    STABLE_TICKER,
    LeveragedPairConfig,
    MissingResearchResultError,
    generate_leveraged_pair_rebalance_proposals as generate_without_research,
)
from data.research_results import ResearchResultContractError
from research.assistant_results import build_leveraged_pair_research_result
from scripts.product_composition import (
    generate_leveraged_pair_rebalance_proposals_with_research
    as generate_leveraged_pair_rebalance_proposals,
    generate_soxx_soxl_rebalance_proposals_with_research
    as generate_soxx_soxl_rebalance_proposals,
)
from market_analytics import classify_trend
from data.price_source import expected_latest_completed_session
from signals.regime import compute_trailing_market_volatility
from strategies.vol_target_rotation import compute_target_leveraged_weight

FAKE_STABLE = "FAKEA"
FAKE_LEVERAGED = "FAKEB"

FAKE_PAIR = LeveragedPairConfig(
    stable_ticker=FAKE_STABLE,
    leveraged_ticker=FAKE_LEVERAGED,
    strategy_key="fake_pair_rebalance",
    production_params=dict(PRODUCTION_PARAMS),
    relied_upon_finding_labels={},  # no dependencies required for this synthetic pair
    evidence_status="promising_unconfirmed_strategy_fake",
)


def _price_history(days: int = 260, seed: int = 0, drift: float = 0.001, vol: float = 0.02) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=drift, scale=vol, size=days)
    close = 50 * np.cumprod(1 + returns)
    dates = pd.bdate_range(
        end=pd.Timestamp(expected_latest_completed_session()), periods=days
    )
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )


def _fake_market_data(days: int = 260):
    return {FAKE_STABLE: _price_history(days=days, seed=1, drift=0.0015), FAKE_LEVERAGED: _price_history(days=days, seed=2, drift=0.001)}


def _soxx_soxl_market_data(days: int = 260):
    return {STABLE_TICKER: _price_history(days=days, seed=1, drift=0.0015), LEVERAGED_TICKER: _price_history(days=days, seed=2, drift=0.001)}


def _expected_target(market_data: dict, stable_ticker: str, leveraged_ticker: str) -> float:
    stable_close = market_data[stable_ticker]["close"]
    leveraged_close = market_data[leveraged_ticker]["close"]
    as_of = min(stable_close.index[-1], leveraged_close.index[-1])
    trend = classify_trend(stable_close, as_of, lookback_days=PRODUCTION_PARAMS["trend_lookback_days"])
    if trend == "downtrend":
        return 0.0
    leveraged_df = pd.DataFrame({"close": leveraged_close})
    vol = compute_trailing_market_volatility(leveraged_df, as_of, lookback_days=PRODUCTION_PARAMS["vol_lookback_days"])
    return compute_target_leveraged_weight(vol, PRODUCTION_PARAMS["target_vol_pct"], PRODUCTION_PARAMS["max_leveraged_weight"])


def _packet(positions: list[dict], cash: float = 5_000.0) -> DecisionPacket:
    snapshot = build_portfolio_snapshot(positions, cash=cash)
    return DecisionPacket(
        generated_at="2026-07-26T12:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-07-25",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _policy(max_order_value: float = 50_000.0) -> TradingPolicy:
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=max_order_value,
    )


def _overweight_packet(market_data, stable_ticker, leveraged_ticker):
    target = _expected_target(market_data, stable_ticker, leveraged_ticker)
    overweight = min(target + 0.30, 0.95)
    combined = 10_000.0
    leveraged_value = combined * overweight
    stable_value = combined - leveraged_value
    leveraged_price = 20.0
    return _packet(
        [
            {"ticker": stable_ticker, "shares": stable_value / 50.0, "entry_price": 50.0, "current_price": 50.0},
            {"ticker": leveraged_ticker, "shares": leveraged_value / leveraged_price, "entry_price": leveraged_price, "current_price": leveraged_price},
        ]
    )


def test_generate_leveraged_pair_rebalance_proposals_is_ticker_agnostic():
    market_data = _fake_market_data()
    packet = _overweight_packet(market_data, FAKE_STABLE, FAKE_LEVERAGED)
    proposals = generate_leveraged_pair_rebalance_proposals(packet, _policy(), FAKE_PAIR, market_data=market_data)
    assert len(proposals) == 1
    assert proposals[0].intent.ticker == FAKE_LEVERAGED
    assert proposals[0].evidence_status == "promising_unconfirmed_strategy_fake"


def test_generate_leveraged_pair_rebalance_proposals_records_evaluation_under_its_own_strategy_key():
    market_data = _fake_market_data()
    packet = _overweight_packet(market_data, FAKE_STABLE, FAKE_LEVERAGED)
    with tempfile.TemporaryDirectory() as tmp:
        store = AssistantStore(Path(tmp) / "assistant.db")
        proposals = generate_leveraged_pair_rebalance_proposals(packet, _policy(), FAKE_PAIR, market_data=market_data, store=store)
        assert len(proposals) == 1
        result = store.get_last_strategy_evaluation("fake_pair_rebalance")
        assert result is not None
        assert result["last_result"] == {"fired": True, "proposal_count": 1}
        # Must NOT have written under the unrelated SOXX/SOXL strategy_key.
        assert store.get_last_strategy_evaluation("soxx_soxl_rebalance") is None


def test_soxx_soxl_wrapper_produces_identical_proposals_to_generic_call():
    market_data = _soxx_soxl_market_data()
    packet = _overweight_packet(market_data, STABLE_TICKER, LEVERAGED_TICKER)
    policy = _policy()

    wrapper_proposals = generate_soxx_soxl_rebalance_proposals(packet, policy, market_data=market_data)
    generic_proposals = generate_leveraged_pair_rebalance_proposals(packet, policy, SOXX_SOXL_PAIR, market_data=market_data)

    assert len(wrapper_proposals) == len(generic_proposals) == 1
    w, g = wrapper_proposals[0], generic_proposals[0]
    assert w.proposal_id == g.proposal_id
    assert w.intent == g.intent
    assert w.evidence_status == g.evidence_status
    assert w.reasons == g.reasons


def test_configured_leveraged_pairs_each_have_distinct_strategy_keys():
    keys = [pair.strategy_key for pair in CONFIGURED_LEVERAGED_PAIRS]
    assert len(keys) == len(set(keys))


def test_assistant_generator_fails_closed_without_research_result():
    market_data = _fake_market_data()
    packet = _overweight_packet(market_data, FAKE_STABLE, FAKE_LEVERAGED)
    with pytest.raises(MissingResearchResultError, match="research result"):
        generate_without_research(
            packet,
            _policy(),
            FAKE_PAIR,
            market_data=market_data,
        )


def test_assistant_rejects_result_bound_to_different_close_history():
    market_data = _fake_market_data()
    packet = _overweight_packet(market_data, FAKE_STABLE, FAKE_LEVERAGED)
    result = build_leveraged_pair_research_result(
        stable_ticker=FAKE_STABLE,
        leveraged_ticker=FAKE_LEVERAGED,
        market_data=market_data,
        production_params=FAKE_PAIR.production_params,
    )
    altered = {ticker: frame.copy() for ticker, frame in market_data.items()}
    altered[FAKE_LEVERAGED].iloc[-2, altered[FAKE_LEVERAGED].columns.get_loc("close")] *= 1.01
    with pytest.raises(ResearchResultContractError, match="does not match"):
        generate_without_research(
            packet,
            _policy(),
            FAKE_PAIR,
            market_data=altered,
            research_result=result,
        )


def test_research_result_contract_is_immutable():
    market_data = _fake_market_data()
    result = build_leveraged_pair_research_result(
        stable_ticker=FAKE_STABLE,
        leveraged_ticker=FAKE_LEVERAGED,
        market_data=market_data,
        production_params=FAKE_PAIR.production_params,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.label = "forged"  # type: ignore[misc]


if __name__ == "__main__":
    test_generate_leveraged_pair_rebalance_proposals_is_ticker_agnostic()
    test_generate_leveraged_pair_rebalance_proposals_records_evaluation_under_its_own_strategy_key()
    test_soxx_soxl_wrapper_produces_identical_proposals_to_generic_call()
    test_configured_leveraged_pairs_each_have_distinct_strategy_keys()
    print("All strategy_proposals_generic tests passed.")


def test_assistant_refuses_research_target_above_the_configured_cap():
    """SEP1C-001: the cap refusal is the assistant's own guard, so pin it.

    The producer self-caps through compute_target_leveraged_weight, so no
    honest run produces an over-cap target -- which is exactly why the
    assistant-side check `target > max_leveraged_weight` had no regression
    coverage: every fixture reached it with an honest value. A result whose
    bindings all verify but whose target exceeds the pair's configured cap
    must refuse loudly rather than size a larger leveraged buy and hope the
    downstream policy gate catches it.
    """
    market_data = _fake_market_data()
    packet = _overweight_packet(market_data, FAKE_STABLE, FAKE_LEVERAGED)
    honest = build_leveraged_pair_research_result(
        stable_ticker=FAKE_STABLE,
        leveraged_ticker=FAKE_LEVERAGED,
        market_data=market_data,
        production_params=FAKE_PAIR.production_params,
    )
    over_cap = dataclasses.replace(
        honest,
        target_leveraged_weight=(
            float(FAKE_PAIR.production_params["max_leveraged_weight"]) + 0.25
        ),
    )
    with pytest.raises(ResearchResultContractError, match="cap"):
        generate_without_research(
            packet,
            _policy(),
            FAKE_PAIR,
            market_data=market_data,
            research_result=over_cap,
        )
