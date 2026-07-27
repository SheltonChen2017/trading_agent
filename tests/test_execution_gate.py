"""
Sanity tests for risk/execution_gate.py. Run with:
python tests/test_execution_gate.py
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot
from risk.execution_gate import TradeIntent, validate_trade_intent

_MARKET_HOURS_WEEKDAY = datetime(2026, 7, 27, 10, 0)  # a Monday, 10:00am


def _snapshot(positions=None, cash=10_000.0):
    return build_portfolio_snapshot(positions or [], cash=cash)


def test_clean_trade_is_approved():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=5)  # $300 = 3% of equity, under every default cap
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY)
    assert result.approved is True
    assert result.violations == []


def test_kill_switch_blocks_everything_else():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=10)
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, kill_switch_active=True)
    assert result.approved is False
    assert result.violations == ["Kill switch is active — no trades are permitted."]


def test_max_position_size_exceeded():
    snapshot = _snapshot(cash=10_000.0)  # total equity = 10,000
    # buying $6,000 of a single name on a 10,000 account with default 5% cap
    intent = TradeIntent(ticker="KO", side="buy", shares=100)
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY)
    assert result.approved is False
    assert any("per-position limit" in v for v in result.violations)


def test_insufficient_cash_flagged():
    snapshot = _snapshot(cash=100.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=10)  # $600 trade, only $100 cash
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, max_position_pct=1.0)
    assert any("exceeds available cash" in v for v in result.violations)


def test_max_total_exposure_exceeded():
    snapshot = _snapshot(
        positions=[{"ticker": "AAA", "shares": 90, "entry_price": 100.0, "current_price": 100.0}],  # $9000 already invested
        cash=1000.0,  # total equity = 10,000, already 90% invested
    )
    intent = TradeIntent(ticker="KO", side="buy", shares=10)  # +$600 -> 96% invested
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY,
        max_position_pct=1.0, max_total_exposure_pct=0.90,
    )
    assert any("total-exposure limit" in v for v in result.violations)


def test_basket_concentration_exceeded():
    snapshot = _snapshot(
        positions=[{"ticker": "NVDA", "shares": 30, "entry_price": 100.0, "current_price": 100.0}],  # $3000, semiconductors
        cash=7000.0,  # total equity = 10,000
    )
    intent = TradeIntent(ticker="AMD", side="buy", shares=20)  # +$2000 (AMD price=100) -> semis = $5000 = 50%
    result = validate_trade_intent(
        intent, snapshot, reference_price=100.0, now=_MARKET_HOURS_WEEKDAY,
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=40.0,
    )
    assert any("semiconductors" in v and "basket concentration limit" in v for v in result.violations)


def test_leveraged_etf_exposure_exceeded():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="TQQQ", side="buy", shares=50)  # $2500 -> 25% leveraged, over 20% cap
    result = validate_trade_intent(
        intent, snapshot, reference_price=50.0, now=_MARKET_HOURS_WEEKDAY,
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_leveraged_etf_pct=20.0,
    )
    assert any("leveraged-ETF limit" in v for v in result.violations)


def test_sell_side_skips_exposure_checks():
    snapshot = _snapshot(
        positions=[{"ticker": "TQQQ", "shares": 100, "entry_price": 50.0, "current_price": 50.0}], cash=5000.0,
    )
    intent = TradeIntent(ticker="TQQQ", side="sell", shares=100)  # selling a big leveraged position -- should be fine
    result = validate_trade_intent(intent, snapshot, reference_price=50.0, now=_MARKET_HOURS_WEEKDAY)
    assert result.approved is True


def test_stale_price_flagged():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0,
        price_timestamp=datetime(2026, 7, 27, 9, 0), now=datetime(2026, 7, 27, 9, 30),
        max_stale_price_minutes=15.0,
    )
    assert any("staleness limit" in v for v in result.violations)


def test_outside_trading_hours_flagged():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    weekend = datetime(2026, 8, 1, 10, 0)  # a Saturday
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=weekend)
    assert any("weekend" in v for v in result.violations)

    after_hours = datetime(2026, 7, 27, 20, 0)  # Monday 8pm
    result2 = validate_trade_intent(intent, snapshot, reference_price=60.0, now=after_hours)
    assert any("outside today's trading session" in v for v in result2.violations)


def test_market_holiday_flagged_even_on_a_weekday():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    thanksgiving_2026 = datetime(2026, 11, 26, 10, 0)  # a Thursday, but NYSE is closed
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=thanksgiving_2026)
    assert any("exchange holiday" in v for v in result.violations)


def test_early_close_flagged_after_1pm_the_day_after_thanksgiving():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    # NYSE closes at 13:00 ET the day after Thanksgiving, not the usual 16:00.
    day_after_thanksgiving_afternoon = datetime(2026, 11, 27, 14, 0)
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=day_after_thanksgiving_afternoon,
    )
    assert any("outside today's trading session" in v for v in result.violations)

    day_after_thanksgiving_morning = datetime(2026, 11, 27, 10, 0)
    result_ok = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=day_after_thanksgiving_morning,
    )
    assert not any("trading session" in v or "exchange holiday" in v for v in result_ok.violations)


def test_duplicate_order_detected():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    prior = TradeIntent(ticker="KO", side="buy", shares=5)
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, recent_intents=[prior])
    assert any("Duplicate order" in v for v in result.violations)


def test_max_slippage_on_limit_order():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1, order_type="limit", limit_price=70.0)  # ref=60, ~16.7% away
    result = validate_trade_intent(intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, max_slippage_pct=1.0)
    assert any("max-slippage limit" in v for v in result.violations)


def test_earnings_blackout_flagged():
    snapshot = _snapshot(cash=10_000.0)
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    result = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, earnings_days_away=1, earnings_blackout_days=2,
    )
    assert any("earnings blackout" in v for v in result.violations)

    # Outside the window -> not flagged
    result_ok = validate_trade_intent(
        intent, snapshot, reference_price=60.0, now=_MARKET_HOURS_WEEKDAY, earnings_days_away=10, earnings_blackout_days=2,
    )
    assert not any("earnings blackout" in v for v in result_ok.violations)


if __name__ == "__main__":
    test_clean_trade_is_approved()
    test_kill_switch_blocks_everything_else()
    test_max_position_size_exceeded()
    test_insufficient_cash_flagged()
    test_max_total_exposure_exceeded()
    test_basket_concentration_exceeded()
    test_leveraged_etf_exposure_exceeded()
    test_sell_side_skips_exposure_checks()
    test_stale_price_flagged()
    test_outside_trading_hours_flagged()
    test_market_holiday_flagged_even_on_a_weekday()
    test_early_close_flagged_after_1pm_the_day_after_thanksgiving()
    test_duplicate_order_detected()
    test_max_slippage_on_limit_order()
    test_earnings_blackout_flagged()
    print("All execution gate tests passed.")
