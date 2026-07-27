"""Tests for assistant/allocation_proposals.py -- the Watchlist
"Buy with recommended allocation" proposal generator."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.allocation_proposals import EVIDENCE_STATUS, generate_allocation_buy_proposals
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import TradingPolicy
from assistant.schemas import DecisionPacket, MarketRegime


def _packet(cash=10_000.0):
    snapshot = build_portfolio_snapshot([], cash=cash)
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


def _policy():
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
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


if __name__ == "__main__":
    test_splits_dollar_amount_by_weight()
    test_rounds_shares_down_not_up()
    test_skips_ticker_when_allocation_buys_less_than_one_share()
    test_skips_ticker_with_missing_price()
    test_returns_empty_for_non_positive_dollar_amount()
    test_returns_empty_for_empty_weights()
    test_evidence_status_is_user_directed_never_confirmed()
    print("All allocation_proposals tests passed.")
