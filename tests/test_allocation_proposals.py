"""Tests for assistant/allocation_proposals.py -- the Watchlist
"Create purchase proposals using this split" proposal generator."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.allocation_proposals import (
    DISCRETE_EVIDENCE_STATUS,
    EVIDENCE_STATUS,
    build_allocation_plan,
    estimate_pending_buy_value_by_ticker,
    generate_allocation_buy_proposals,
    generate_discrete_buy_proposal,
)
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import TradingPolicy
from assistant.schemas import DecisionPacket, MarketRegime


def _packet(cash=10_000.0, positions=None, open_orders=None):
    snapshot = build_portfolio_snapshot(positions or [], cash=cash, open_orders=open_orders)
    return DecisionPacket(
        generated_at="2026-07-27T12:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-07-26",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _policy(max_order_value=50_000.0, *, whole_shares_only=True):
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0,
        max_order_value=max_order_value,
        allow_new_positions=True,
        whole_shares_only=whole_shares_only,
    )


def test_splits_dollar_amount_by_weight():
    proposals = generate_allocation_buy_proposals(
        _packet(), _policy(),
        weights_pct={"NVDA": 30.0, "AAPL": 70.0},
        prices={"NVDA": 100.0, "AAPL": 70.0},
        dollar_amount=1000.0,
    )
    by_ticker = {p.intent.ticker: p for p in proposals}
    assert set(by_ticker) == {"NVDA", "AAPL"}
    # 30% of $1000 = $300 / $100 = 3 shares; 70% of $1000 = $700 / $70 = 10 shares
    assert by_ticker["NVDA"].intent.shares == 3
    assert by_ticker["AAPL"].intent.shares == 10
    assert by_ticker["NVDA"].intent.side == "buy"


def test_rounds_shares_down_not_up():
    proposals = generate_allocation_buy_proposals(
        _packet(), _policy(),
        weights_pct={"X": 100.0},
        prices={"X": 33.0},
        dollar_amount=100.0,  # 100/33 = 3.03 -> floor to 3, not round to 3
    )
    assert proposals[0].intent.shares == 3


def test_skips_ticker_when_allocation_buys_less_than_one_share():
    proposals = generate_allocation_buy_proposals(
        _packet(), _policy(),
        weights_pct={"CHEAP": 90.0, "EXPENSIVE": 10.0},
        prices={"CHEAP": 10.0, "EXPENSIVE": 5000.0},
        dollar_amount=100.0,  # EXPENSIVE gets $10, can't buy even 1 share at $5000
    )
    tickers = {p.intent.ticker for p in proposals}
    assert "CHEAP" in tickers
    assert "EXPENSIVE" not in tickers


def test_skips_ticker_with_missing_price():
    proposals = generate_allocation_buy_proposals(
        _packet(), _policy(),
        weights_pct={"A": 50.0, "B": 50.0},
        prices={"A": 100.0},  # B has no price
        dollar_amount=1000.0,
    )
    tickers = {p.intent.ticker for p in proposals}
    assert tickers == {"A"}


def test_returns_empty_for_non_positive_dollar_amount():
    proposals = generate_allocation_buy_proposals(
        _packet(), _policy(), weights_pct={"A": 100.0}, prices={"A": 10.0}, dollar_amount=0.0,
    )
    assert proposals == []


def test_returns_empty_for_empty_weights():
    proposals = generate_allocation_buy_proposals(
        _packet(), _policy(), weights_pct={}, prices={}, dollar_amount=1000.0,
    )
    assert proposals == []


def test_evidence_status_is_user_directed_never_confirmed():
    proposals = generate_allocation_buy_proposals(
        _packet(), _policy(), weights_pct={"A": 100.0}, prices={"A": 10.0}, dollar_amount=100.0,
    )
    assert proposals
    for p in proposals:
        assert p.evidence_status == EVIDENCE_STATUS == "user_directed_allocation"
        assert p.evidence_status not in ("confirmed", "promising_unconfirmed")


def test_discrete_buy_preserves_an_exact_share_request_at_the_policy_boundary():
    """Three shares at ten cents is exactly thirty cents; the generator must
    not reproduce the binary-float off-by-one that motivated TRADE-1."""
    policy = _policy(max_order_value="0.30")
    result = generate_discrete_buy_proposal(
        _packet(), policy, ticker="nvda", shares=3, price="0.10"
    )

    assert result["created"] is True
    proposal = result["proposal"]
    assert proposal.intent.ticker == "NVDA"
    assert proposal.intent.shares == 3
    assert proposal.intent.side == "buy"
    assert proposal.status == "proposed"
    assert proposal.evidence_status == DISCRETE_EVIDENCE_STATUS


def test_discrete_buy_refuses_to_edit_an_order_down_to_the_policy_cap():
    policy = _policy(max_order_value="29.99")
    result = generate_discrete_buy_proposal(
        _packet(), policy, ticker="NVDA", shares=3, price="10"
    )

    assert result["created"] is False
    assert "above your policy" in result["reason"]
    assert "up to 2 share(s) fit" in result["reason"]


@pytest.mark.parametrize("shares", [True, 1.5, "2", 0, -1, float("nan")])
def test_discrete_buy_refuses_non_exact_share_quantities(shares):
    result = generate_discrete_buy_proposal(
        _packet(), _policy(), ticker="NVDA", shares=shares, price="100"
    )
    assert result["created"] is False
    assert "whole number greater than zero" in result["reason"]


def test_discrete_buy_accepts_exact_fractional_quantity_only_when_policy_allows_it():
    permissive = _policy(whole_shares_only=False, max_order_value="100")
    result = generate_discrete_buy_proposal(
        _packet(), permissive, ticker="NVDA", shares="0.125", price="80"
    )
    assert result["created"] is True
    assert result["proposal"].intent.shares == "0.125"
    assert result["proposal"].expected_impact["trade_value"] == 10.0

    strict = generate_discrete_buy_proposal(
        _packet(), _policy(), ticker="NVDA", shares="0.125", price="80"
    )
    assert strict["created"] is False


def test_budgeted_buy_uses_fractional_shares_when_policy_allows_them():
    policy = _policy(whole_shares_only=False)
    plan = build_allocation_plan(
        _packet(), policy, {"NVDA": 100.0}, {"NVDA": 300.0}, dollar_amount=100.0
    )
    assert plan[0].shares == "0.333333333"
    assert plan[0].skipped is False
    proposals = generate_allocation_buy_proposals(
        _packet(), policy, {"NVDA": 100.0}, {"NVDA": 300.0}, dollar_amount=100.0
    )
    assert proposals[0].intent.shares == "0.333333333"


def test_plan_matches_proposals_shares_and_skips_exactly():
    # GPT review, 2026-07-28: the preview must never show a different plan
    # than generate_allocation_buy_proposals() actually produces.
    weights = {"CHEAP": 90.0, "EXPENSIVE": 10.0}
    prices = {"CHEAP": 10.0, "EXPENSIVE": 5000.0}
    packet, policy = _packet(), _policy()
    plan = build_allocation_plan(packet, policy, weights, prices, dollar_amount=100.0)
    by_ticker = {e.ticker: e for e in plan}
    assert by_ticker["CHEAP"].shares == 9  # 90% of $100 = $90 / $10 = 9 shares
    assert by_ticker["CHEAP"].skipped is False
    assert by_ticker["EXPENSIVE"].skipped is True
    assert by_ticker["EXPENSIVE"].shares == 0
    assert "5,000.00" in by_ticker["EXPENSIVE"].skip_reason or "$5000" in by_ticker["EXPENSIVE"].skip_reason

    proposals = generate_allocation_buy_proposals(packet, policy, weights, prices, dollar_amount=100.0)
    proposal_tickers = {p.intent.ticker: p.intent.shares for p in proposals}
    assert proposal_tickers == {"CHEAP": 9}


def test_plan_skips_ticker_with_missing_price_with_a_reason():
    plan = build_allocation_plan(
        _packet(), _policy(), weights_pct={"A": 50.0, "B": 50.0}, prices={"A": 100.0},
        dollar_amount=1000.0,
    )
    by_ticker = {e.ticker: e for e in plan}
    assert by_ticker["A"].skipped is False
    assert by_ticker["B"].skipped is True
    assert by_ticker["B"].shares == 0
    assert by_ticker["B"].skip_reason == "No current price available."


def test_plan_includes_existing_holdings_in_projected_weight():
    packet = _packet(
        cash=10_000.0,
        positions=[{"ticker": "NVDA", "shares": 10, "entry_price": 50.0, "current_price": 100.0}],
    )
    plan = build_allocation_plan(packet, _policy(), {"NVDA": 100.0}, {"NVDA": 100.0}, dollar_amount=1000.0)
    entry = plan[0]
    assert entry.existing_market_value == 1000.0  # 10 shares * $100
    # 1000/100 = 10 new shares * $100 = $1000 planned; projected = 1000 existing + 1000 new = 2000
    assert entry.shares == 10
    assert entry.projected_market_value == 2000.0
    total_equity = packet.portfolio.total_equity
    assert abs(entry.projected_pct_of_equity - (2000.0 / total_equity * 100)) < 1e-6


def test_estimate_pending_buy_value_from_notional_order():
    totals, unknown = estimate_pending_buy_value_by_ticker(
        [{"order_id": "o1", "ticker": "nvda", "side": "buy", "shares": None, "notional": 250.0,
          "type": "market", "status": "new", "submitted_at": None, "limit_price": None}]
    )
    assert totals == {"NVDA": 250.0}
    assert unknown == set()


def test_estimate_pending_buy_value_from_limit_order():
    totals, unknown = estimate_pending_buy_value_by_ticker(
        [{"order_id": "o1", "ticker": "AAPL", "side": "buy", "shares": 5, "notional": None,
          "type": "limit", "status": "new", "submitted_at": None, "limit_price": 20.0}]
    )
    assert totals == {"AAPL": 100.0}
    assert unknown == set()


def test_estimate_pending_buy_value_unknown_for_plain_market_order():
    # A plain market order (no notional, no shares+limit_price) can't be
    # priced without a live quote -- the preview must NOT silently treat
    # it as zero (GPT review, 2026-07-28).
    totals, unknown = estimate_pending_buy_value_by_ticker(
        [{"order_id": "o1", "ticker": "TSLA", "side": "buy", "shares": 3, "notional": None,
          "type": "market", "status": "new", "submitted_at": None, "limit_price": None}]
    )
    assert totals == {}
    assert unknown == {"TSLA"}


def test_estimate_pending_buy_value_ignores_sell_orders():
    totals, unknown = estimate_pending_buy_value_by_ticker(
        [{"order_id": "o1", "ticker": "TSLA", "side": "sell", "shares": 3, "notional": None,
          "type": "market", "status": "new", "submitted_at": None, "limit_price": None}]
    )
    assert totals == {}
    assert unknown == set()


def test_plan_reflects_pending_buy_value_in_projection():
    packet = _packet()
    plan = build_allocation_plan(
        packet, _policy(), {"NVDA": 100.0}, {"NVDA": 100.0}, dollar_amount=100.0,
        pending_buy_value_by_ticker={"NVDA": 500.0},
    )
    entry = plan[0]
    assert entry.pending_buy_value == 500.0
    assert entry.pending_value_unknown is False
    # 100% of $100 = 1 share @ $100 = $100 planned; projected = 0 existing + 500 pending + 100 planned
    assert entry.projected_market_value == 600.0


def test_plan_flags_pending_value_unknown_tickers():
    plan = build_allocation_plan(
        _packet(), _policy(), {"TSLA": 100.0}, {"TSLA": 100.0}, dollar_amount=100.0,
        pending_value_unknown_tickers={"TSLA"},
    )
    assert plan[0].pending_value_unknown is True


if __name__ == "__main__":
    test_splits_dollar_amount_by_weight()
    test_rounds_shares_down_not_up()
    test_skips_ticker_when_allocation_buys_less_than_one_share()
    test_skips_ticker_with_missing_price()
    test_returns_empty_for_non_positive_dollar_amount()
    test_returns_empty_for_empty_weights()
    test_evidence_status_is_user_directed_never_confirmed()
    test_plan_matches_proposals_shares_and_skips_exactly()
    test_plan_skips_ticker_with_missing_price_with_a_reason()
    test_plan_includes_existing_holdings_in_projected_weight()
    test_estimate_pending_buy_value_from_notional_order()
    test_estimate_pending_buy_value_from_limit_order()
    test_estimate_pending_buy_value_unknown_for_plain_market_order()
    test_estimate_pending_buy_value_ignores_sell_orders()
    test_plan_reflects_pending_buy_value_in_projection()
    test_plan_flags_pending_value_unknown_tickers()
    print("All allocation_proposals tests passed.")


def test_build_allocation_plan_skips_a_nan_price_instead_of_crashing():
    # Independent review, 2026-07-29, reproduced: every other bad price
    # (0, negative, None, inf) degraded to a skipped entry, but NaN passed
    # both `not price` (NaN is truthy) and `price <= 0` (NaN comparisons
    # are always False), then math.floor(target/NaN) raised ValueError and
    # took down the whole Watchlist tab. NaN is reachable --
    # get_latest_quote() builds its price from bare float(bid/ask).
    packet = _packet(cash=10_000.0)
    policy = _policy()
    plan = build_allocation_plan(packet, policy, {"AAA": 100.0}, {"AAA": float("nan")}, 1_000.0)
    assert len(plan) == 1
    assert plan[0].shares == 0
    assert plan[0].skipped is True


def test_build_allocation_plan_skips_infinite_price_too():
    packet = _packet(cash=10_000.0)
    policy = _policy()
    plan = build_allocation_plan(packet, policy, {"AAA": 100.0}, {"AAA": float("inf")}, 1_000.0)
    assert plan[0].shares == 0
    assert plan[0].skipped is True
