"""Regression proofs for exact risk math and authorization consumption."""
from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from assistant.context_builder import build_portfolio_snapshot
from assistant.execution_kernel.revalidate import _pending_buy_value_by_ticker
from assistant.schemas import PortfolioPosition, PortfolioSnapshot
from risk.execution_gate import (
    TradeIntent,
    ViolationCode,
    authorize_overridden_trade_intent,
    authorize_trade_intent,
    validate_trade_intent,
    verify_execution_authorization,
)


def _clean_validation() -> tuple[TradeIntent, object]:
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    validation = validate_trade_intent(
        intent,
        build_portfolio_snapshot([], cash=10_000),
        reference_price=10,
    )
    assert validation.approved
    return intent, validation


def _position(
    *,
    ticker: str,
    shares: str,
    price: str,
    market_value: str,
) -> PortfolioPosition:
    return PortfolioPosition(
        ticker=ticker,
        shares=float(Decimal(shares)),
        entry_price=float(Decimal(price)),
        current_price=float(Decimal(price)),
        market_value=float(round(Decimal(market_value), 2)),
        unrealized_pnl_pct=0.0,
        is_leveraged_etf=False,
        shares_exact=shares,
        entry_price_exact=price,
        current_price_exact=price,
        market_value_exact=market_value,
    )


def test_sub_cent_exact_position_value_controls_cap_decision() -> None:
    snapshot = PortfolioSnapshot(
        positions=[
            _position(
                ticker="KO", shares="1", price="49.994", market_value="49.994"
            )
        ],
        cash=50.01,
        cash_exact="50.006",
        total_equity=100.0,
        total_equity_exact="100",
        buying_power=50.01,
        buying_power_exact="50.006",
        as_of="2026-08-26",
    )

    result = validate_trade_intent(
        TradeIntent(ticker="KO", side="buy", shares=1),
        snapshot,
        reference_price=0.01,
        max_position_pct=0.5,
        max_total_exposure_pct=1.0,
    )

    assert ViolationCode.MAX_POSITION_PCT.value in result.violation_codes


def test_exact_values_accumulate_before_any_display_rounding() -> None:
    snapshot = PortfolioSnapshot(
        positions=[
            _position(
                ticker="KO-A", shares="1", price="24.997", market_value="24.997"
            ),
            _position(
                ticker="KO", shares="1", price="24.997", market_value="24.997"
            ),
        ],
        cash=50.01,
        cash_exact="50.006",
        total_equity=100.0,
        total_equity_exact="100",
        buying_power=50.01,
        buying_power_exact="50.006",
        as_of="2026-08-26",
    )

    result = validate_trade_intent(
        TradeIntent(ticker="IBM", side="buy", shares=1),
        snapshot,
        reference_price=0.01,
        max_position_pct=1.0,
        max_total_exposure_pct=0.5,
    )

    assert ViolationCode.MAX_TOTAL_EXPOSURE_PCT.value in result.violation_codes


def test_display_and_exact_disagreement_fails_closed() -> None:
    position = _position(
        ticker="KO", shares="1", price="10", market_value="10"
    )
    position.market_value = 9.99
    snapshot = PortfolioSnapshot(
        positions=[position],
        cash=90.0,
        cash_exact="90",
        total_equity=100.0,
        total_equity_exact="100",
        as_of="2026-08-26",
    )

    result = validate_trade_intent(
        TradeIntent(ticker="KO", side="sell", shares=1),
        snapshot,
        reference_price=10,
    )

    assert ViolationCode.INVALID_POSITION_DATA.value in result.violation_codes


def test_fractional_pending_order_and_quote_use_exact_fields() -> None:
    class Broker:
        @staticmethod
        def get_latest_quote(_ticker: str) -> dict:
            return {"price": 1.0, "price_decimal": "1.0009"}

    totals = _pending_buy_value_by_ticker(
        [
            {
                "side": "buy",
                "ticker": "KO",
                "shares": 0.5,
                "shares_decimal": "0.500000001",
                "filled_qty": 0.0,
                "filled_qty_decimal": "0",
                "limit_price": None,
                "limit_price_decimal": None,
            }
        ],
        Broker,
    )

    assert totals == {"KO": Decimal("0.5004500010009")}


def test_earnings_blackout_blocks_buys_but_never_a_valid_long_only_sell() -> None:
    snapshot = build_portfolio_snapshot(
        [{"ticker": "KO", "shares": 10, "entry_price": 10, "current_price": 10}],
        cash=900,
    )

    buy = validate_trade_intent(
        TradeIntent(ticker="KO", side="buy", shares=1),
        snapshot,
        reference_price=10,
        earnings_days_away=0,
        max_position_pct=1.0,
        max_total_exposure_pct=1.0,
    )
    sell = validate_trade_intent(
        TradeIntent(ticker="KO", side="sell", shares=5),
        snapshot,
        reference_price=10,
        earnings_days_away=0,
    )
    oversell = validate_trade_intent(
        TradeIntent(ticker="KO", side="sell", shares=11),
        snapshot,
        reference_price=10,
        earnings_days_away=0,
    )

    assert ViolationCode.EARNINGS_BLACKOUT.value in buy.violation_codes
    assert sell.approved
    assert ViolationCode.EARNINGS_BLACKOUT.value not in sell.violation_codes
    assert oversell.violation_codes == (ViolationCode.SELL_EXCEEDS_HELD.value,)


@pytest.mark.parametrize(
    "bad_ttl", [True, False, 0, -1, 301, 1.0, float("inf"), "120"]
)
def test_authorizers_reject_unbounded_or_non_integer_ttl(bad_ttl: object) -> None:
    intent, validation = _clean_validation()
    with pytest.raises(ValueError, match="ttl_seconds"):
        authorize_trade_intent(intent, validation, ttl_seconds=bad_ttl)
    with pytest.raises(ValueError, match="ttl_seconds"):
        authorize_overridden_trade_intent(intent, validation, ttl_seconds=bad_ttl)


def test_authorization_consume_is_atomic_across_two_threads() -> None:
    intent, validation = _clean_validation()
    authorization = authorize_trade_intent(intent, validation)
    barrier = threading.Barrier(3)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def verify() -> None:
        barrier.wait(timeout=5)
        try:
            verify_execution_authorization(intent, authorization)
        except PermissionError:
            result = "rejected"
        else:
            result = "accepted"
        with outcomes_lock:
            outcomes.append(result)

    threads = [threading.Thread(target=verify) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)

    assert not any(thread.is_alive() for thread in threads)
    assert sorted(outcomes) == ["accepted", "rejected"]
