"""Regression proofs for exact risk math and authorization consumption."""
from __future__ import annotations

import threading
from decimal import Decimal, localcontext

import pytest

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
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


def test_malformed_collision_like_ticker_cannot_hide_existing_position() -> None:
    snapshot = PortfolioSnapshot(
        positions=[
            _position(
                ticker="AAPL ",
                shares="40",
                price="100",
                market_value="4000",
            )
        ],
        cash=6000.0,
        cash_exact="6000",
        total_equity=10000.0,
        total_equity_exact="10000",
        buying_power=6000.0,
        buying_power_exact="6000",
        as_of="2026-08-26",
    )

    result = validate_trade_intent(
        TradeIntent(ticker="AAPL", side="buy", shares=4),
        snapshot,
        reference_price=100,
        max_position_pct=0.05,
        max_total_exposure_pct=1.0,
        max_basket_pct=100,
        max_leveraged_etf_pct=100,
    )

    assert result.approved is False
    assert ViolationCode.INVALID_POSITION_DATA.value in result.violation_codes


def test_available_capital_overrides_can_tighten_but_never_loosen_cash() -> None:
    permissive_caps = {
        "max_position_pct": 10,
        "max_total_exposure_pct": 10,
        "max_basket_pct": 1000,
        "max_leveraged_etf_pct": 1000,
    }
    intent = TradeIntent(ticker="AAPL", side="buy", shares=2)

    inflated = validate_trade_intent(
        intent,
        build_portfolio_snapshot([], cash="100"),
        reference_price=100,
        available_cash_override=1000,
        available_buying_power_override=1000,
        **permissive_caps,
    )
    ordinarily_affordable = validate_trade_intent(
        intent,
        build_portfolio_snapshot([], cash="1000"),
        reference_price=100,
        **permissive_caps,
    )
    tightened = validate_trade_intent(
        intent,
        build_portfolio_snapshot([], cash="1000"),
        reference_price=100,
        available_cash_override=100,
        available_buying_power_override=100,
        **permissive_caps,
    )

    assert inflated.approved is False
    assert ViolationCode.INSUFFICIENT_CASH.value in inflated.violation_codes
    assert ordinarily_affordable.approved is True
    assert tightened.approved is False
    assert ViolationCode.INSUFFICIENT_CASH.value in tightened.violation_codes


def test_orphan_exact_buying_power_is_unavailable_to_reports_and_refused_by_gate() -> None:
    snapshot = PortfolioSnapshot(
        positions=[],
        cash=1000.0,
        cash_exact="1000",
        total_equity=1000.0,
        total_equity_exact="1000",
        buying_power=None,
        buying_power_exact="0",
        as_of="2026-08-28",
    )

    risk = build_risk_exposure(snapshot)
    result = validate_trade_intent(
        TradeIntent(ticker="KO", side="buy", shares=1),
        snapshot,
        reference_price=10,
    )

    assert snapshot.has_exact_numerics is False
    assert risk.available is False
    assert "buying_power_exact cannot exist" in risk.unavailable_reason
    assert result.approved is False
    assert ViolationCode.INVALID_BUYING_POWER.value in result.violation_codes


def test_absent_buying_power_and_exact_companion_remain_a_valid_optional_pair() -> None:
    snapshot = PortfolioSnapshot(
        positions=[],
        cash=1000.0,
        cash_exact="1000",
        total_equity=1000.0,
        total_equity_exact="1000",
        buying_power=None,
        buying_power_exact=None,
        as_of="2026-08-28",
    )

    risk = build_risk_exposure(snapshot)
    result = validate_trade_intent(
        TradeIntent(ticker="KO", side="buy", shares=1),
        snapshot,
        reference_price=10,
    )

    assert snapshot.has_exact_numerics is True
    assert risk.available is True
    assert result.approved is True


@pytest.mark.parametrize("override", [-1, "-0.01", Decimal("-1")])
def test_negative_available_capital_override_is_a_typed_hard_refusal(override) -> None:
    result = validate_trade_intent(
        TradeIntent(ticker="KO", side="buy", shares=1),
        build_portfolio_snapshot([], cash="1000"),
        reference_price=10,
        available_cash_override=override,
    )

    assert result.approved is False
    assert (
        ViolationCode.INVALID_AVAILABLE_CAPITAL_OVERRIDE.value
        in result.violation_codes
    )


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


def test_max_order_value_retains_digits_past_default_decimal_precision() -> None:
    result = validate_trade_intent(
        TradeIntent(ticker="KO", side="buy", shares=3),
        build_portfolio_snapshot([], cash="1000"),
        reference_price="33.33333333333333333333333334",
        max_order_value=Decimal("100"),
        max_position_pct=Decimal("1"),
        max_total_exposure_pct=Decimal("1"),
    )

    assert ViolationCode.MAX_ORDER_VALUE.value in result.violation_codes


def test_max_order_value_ignores_lowered_ambient_decimal_precision() -> None:
    snapshot = build_portfolio_snapshot([], cash="1000")

    with localcontext() as context:
        context.prec = 2
        result = validate_trade_intent(
            TradeIntent(ticker="KO", side="buy", shares=3),
            snapshot,
            reference_price="33.34",
            max_order_value=Decimal("100"),
            max_position_pct=Decimal("1"),
            max_total_exposure_pct=Decimal("1"),
        )

    assert ViolationCode.MAX_ORDER_VALUE.value in result.violation_codes


def test_unrepresentable_trade_value_is_a_hard_fail_closed_violation() -> None:
    result = validate_trade_intent(
        TradeIntent(ticker="KO", side="buy", shares=1),
        build_portfolio_snapshot([], cash="1000"),
        reference_price="1e1000000",
        max_order_value=Decimal("100"),
        max_position_pct=Decimal("1"),
        max_total_exposure_pct=Decimal("1"),
    )

    assert ViolationCode.MAX_ORDER_VALUE.value in result.violation_codes
    assert not result.approved
    assert not result.overridable


def test_exposure_and_reserve_boundaries_ignore_lowered_precision() -> None:
    snapshot = build_portfolio_snapshot([], cash="100")

    with localcontext() as context:
        context.prec = 2
        result = validate_trade_intent(
            TradeIntent(ticker="NVDA", side="buy", shares=1),
            snapshot,
            reference_price="5.004",
            max_position_pct=Decimal("0.05"),
            max_total_exposure_pct=Decimal("0.05"),
            max_basket_pct=Decimal("5"),
            max_leveraged_etf_pct=Decimal("100"),
            min_cash_reserve_pct=Decimal("0.95"),
        )

    assert ViolationCode.MAX_POSITION_PCT.value in result.violation_codes
    assert ViolationCode.MAX_TOTAL_EXPOSURE_PCT.value in result.violation_codes
    assert ViolationCode.MAX_BASKET_PCT.value in result.violation_codes
    assert ViolationCode.MIN_CASH_RESERVE.value in result.violation_codes


def test_leveraged_etf_boundary_ignores_lowered_precision() -> None:
    snapshot = build_portfolio_snapshot([], cash="100")

    with localcontext() as context:
        context.prec = 2
        result = validate_trade_intent(
            TradeIntent(ticker="TQQQ", side="buy", shares=1),
            snapshot,
            reference_price="5.004",
            max_position_pct=Decimal("1"),
            max_total_exposure_pct=Decimal("1"),
            max_basket_pct=Decimal("100"),
            max_leveraged_etf_pct=Decimal("5"),
        )

    assert ViolationCode.MAX_LEVERAGED_ETF_PCT.value in result.violation_codes


def test_slippage_and_spread_boundaries_ignore_lowered_precision() -> None:
    snapshot = build_portfolio_snapshot([], cash="10000")

    with localcontext() as context:
        context.prec = 2
        result = validate_trade_intent(
            TradeIntent(
                ticker="KO",
                side="buy",
                shares=1,
                order_type="limit",
                limit_price="101.004",
            ),
            snapshot,
            reference_price="100",
            bid_price="99.5",
            ask_price="100.504",
            max_position_pct=Decimal("1"),
            max_total_exposure_pct=Decimal("1"),
            max_slippage_pct=Decimal("1"),
            max_spread_pct=Decimal("1"),
        )

    assert ViolationCode.MAX_SLIPPAGE.value in result.violation_codes
    assert ViolationCode.MAX_SPREAD.value in result.violation_codes


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


def test_pending_order_value_ignores_lowered_ambient_precision() -> None:
    class Broker:
        @staticmethod
        def get_latest_quote(_ticker: str) -> dict:
            raise AssertionError("limit order must not fetch a quote")

    with localcontext() as context:
        context.prec = 2
        totals = _pending_buy_value_by_ticker(
            [
                {
                    "side": "buy",
                    "ticker": "KO",
                    "shares_decimal": "3",
                    "filled_qty_decimal": "0",
                    "limit_price_decimal": "33.34",
                    "notional_decimal": None,
                }
            ],
            Broker,
        )

    assert totals == {"KO": Decimal("100.02")}


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
