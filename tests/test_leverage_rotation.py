"""
Sanity tests for strategies/leverage_rotation.py. Run with:
python tests/test_leverage_rotation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from strategies.leverage_rotation import (
    buy_and_hold,
    cagr_pct,
    max_drawdown_pct,
    simulate_leverage_rotation,
)


def _series(prices: list[float]) -> pd.Series:
    dates = pd.bdate_range("2024-01-01", periods=len(prices))
    return pd.Series(prices, index=dates)


def test_trade_fires_on_up_move_above_threshold():
    stable_close = _series([100, 101, 101, 101])
    leveraged_close = _series([100, 110, 110, 110])  # +10% day 1, then flat

    result = simulate_leverage_rotation(
        stable_close, leveraged_close, stable_close, leveraged_close,
        initial_stable=5000, initial_leveraged=5000, threshold_pct=2.0, trade_size=500,
    )
    assert result["n_trades"] == 1
    assert result["trade_log"][0]["action"] == "trim_leveraged"


def test_trade_fires_on_down_move_below_threshold():
    stable_close = _series([100, 99, 99, 99])
    leveraged_close = _series([100, 85, 85, 85])  # -15% day 1

    result = simulate_leverage_rotation(
        stable_close, leveraged_close, stable_close, leveraged_close,
        initial_stable=5000, initial_leveraged=5000, threshold_pct=2.0, trade_size=500,
    )
    assert result["n_trades"] == 1
    assert result["trade_log"][0]["action"] == "buy_leveraged_dip"


def test_no_trade_when_move_within_threshold():
    stable_close = _series([100, 100.5, 101, 101.5])
    leveraged_close = _series([100, 101, 102, 103])  # 1%/day moves, threshold is 2%

    result = simulate_leverage_rotation(
        stable_close, leveraged_close, stable_close, leveraged_close,
        initial_stable=5000, initial_leveraged=5000, threshold_pct=2.0, trade_size=500,
    )
    assert result["n_trades"] == 0


def test_trade_executes_at_next_day_open_not_decision_day_close():
    # Regression test for a real look-ahead bug: the decision to trade is
    # only knowable once day 1's close prints (a +10% move), but the
    # trade must execute at day 2's OPEN, not day 1's own close. Make
    # day 2's open deliberately far from day 1's close so a same-close
    # bug would produce a visibly different (and wrong) result.
    stable_close = _series([100, 101, 101, 101])
    leveraged_close = _series([100, 110, 110, 110])
    stable_open = _series([100, 101, 200, 200])      # day 2 open deliberately != day 1 close (101)
    leveraged_open = _series([100, 110, 300, 300])    # day 2 open deliberately != day 1 close (110)

    result = simulate_leverage_rotation(
        stable_close, leveraged_close, stable_open, leveraged_open,
        initial_stable=5000, initial_leveraged=5000, threshold_pct=2.0, trade_size=500,
    )
    assert result["n_trades"] == 1
    assert result["trade_log"][0]["date"] == leveraged_close.index[2]  # executes on day 2, not day 1

    # Hand-computed expected value using day-2 OPEN prices (200/300) for
    # the trade, then marked to market at day-2 CLOSE (101/110).
    expected_leveraged_shares = 50 - 500 / 300
    expected_stable_shares = 50 + 500 / 200
    expected_day2_value = expected_stable_shares * 101 + expected_leveraged_shares * 110
    assert abs(result["series"].iloc[2] - expected_day2_value) < 0.01

    # A same-close bug would instead have traded at day-1's close (101/110),
    # giving a visibly different value -- confirm we do NOT match that.
    buggy_leveraged_shares = 50 - 500 / 110
    buggy_stable_shares = 50 + 500 / 101
    buggy_day2_value = buggy_stable_shares * 101 + buggy_leveraged_shares * 110
    assert abs(result["series"].iloc[2] - buggy_day2_value) > 1.0


def test_zero_tax_and_cost_are_backward_compatible():
    stable_close = _series([100, 101, 101, 101])
    leveraged_close = _series([100, 110, 110, 110])
    stable_open = _series([100, 101, 200, 200])
    leveraged_open = _series([100, 110, 300, 300])

    result = simulate_leverage_rotation(
        stable_close, leveraged_close, stable_open, leveraged_open,
        initial_stable=5000, initial_leveraged=5000, threshold_pct=2.0, trade_size=500,
    )
    assert result["total_tax_paid"] == 0.0
    assert result["total_cost_paid"] == 0.0
    assert result["trade_log"][0]["tax_paid"] == 0.0
    assert result["trade_log"][0]["cost_paid"] == 0.0


def test_tax_reduces_reinvested_proceeds_on_realized_gain():
    # Same scenario as the next-day-open regression test: leveraged
    # bought at close 100 (cost basis 100), trimmed at day-2's open of
    # 300 -- a real gain of (300-100) per share sold, which should owe
    # tax at tax_rate and leave less to reinvest into stable.
    stable_close = _series([100, 101, 101, 101])
    leveraged_close = _series([100, 110, 110, 110])
    stable_open = _series([100, 101, 200, 200])
    leveraged_open = _series([100, 110, 300, 300])
    tax_rate = 0.37

    result = simulate_leverage_rotation(
        stable_close, leveraged_close, stable_open, leveraged_open,
        initial_stable=5000, initial_leveraged=5000, threshold_pct=2.0, trade_size=500,
        tax_rate=tax_rate,
    )
    sell_value = 500.0  # not capped: 50 shares * $300 = $15,000 available
    shares_sold = sell_value / 300.0
    expected_gain = (300.0 - 100.0) * shares_sold
    expected_tax = tax_rate * expected_gain

    trade = result["trade_log"][0]
    assert abs(trade["tax_paid"] - expected_tax) < 0.01
    assert abs(result["total_tax_paid"] - expected_tax) < 0.01

    expected_net_proceeds = sell_value - expected_tax
    expected_stable_shares = 50 + expected_net_proceeds / 200.0
    expected_leveraged_shares = 50 - shares_sold
    expected_day2_value = expected_stable_shares * 101 + expected_leveraged_shares * 110
    assert abs(result["series"].iloc[2] - expected_day2_value) < 0.01


def test_no_tax_owed_on_realized_loss():
    # Stable bought at close 200 (cost basis 200), sold at day-2's open of
    # 90 -- a real LOSS, which should owe zero tax (no benefit assumed
    # for losses, but also no penalty).
    stable_close = _series([200, 150, 150, 150])
    leveraged_close = _series([100, 80, 80, 80])  # -20% day 1 -> buy_leveraged_dip
    stable_open = _series([200, 150, 90, 90])
    leveraged_open = _series([100, 80, 80, 80])

    result = simulate_leverage_rotation(
        stable_close, leveraged_close, stable_open, leveraged_open,
        initial_stable=5000, initial_leveraged=5000, threshold_pct=2.0, trade_size=500,
        tax_rate=0.37,
    )
    assert result["n_trades"] == 1
    assert result["trade_log"][0]["action"] == "buy_leveraged_dip"
    assert result["trade_log"][0]["tax_paid"] == 0.0


def test_cost_pct_reduces_reinvested_proceeds():
    stable_close = _series([100, 101, 101, 101])
    leveraged_close = _series([100, 110, 110, 110])
    stable_open = _series([100, 101, 200, 200])
    leveraged_open = _series([100, 110, 300, 300])
    cost_pct = 0.01  # 1% of trade value

    result = simulate_leverage_rotation(
        stable_close, leveraged_close, stable_open, leveraged_open,
        initial_stable=5000, initial_leveraged=5000, threshold_pct=2.0, trade_size=500,
        cost_pct=cost_pct,
    )
    expected_cost = cost_pct * 500.0
    assert abs(result["trade_log"][0]["cost_paid"] - expected_cost) < 0.01
    assert abs(result["total_cost_paid"] - expected_cost) < 0.01


def test_trade_size_capped_at_available_holding():
    stable_close = _series([100, 200, 200, 200])  # stable moons, tiny holding to sell from later
    leveraged_close = _series([100, 90, 60, 60])  # then leveraged craters hard

    result = simulate_leverage_rotation(
        stable_close, leveraged_close, stable_close, leveraged_close,
        initial_stable=100, initial_leveraged=5000, threshold_pct=2.0, trade_size=500,
    )
    # Day 1's -10% move triggers a dip-buy executed day 2, fully draining
    # the small stable holding (capped well under $500); day 2's further
    # -33% move triggers a second dip-buy executed day 3, but stable is
    # now empty, so that one is capped at ~$0.
    assert result["n_trades"] == 2
    second_trade = result["trade_log"][1]
    assert second_trade["value"] <= 0.01


def test_buy_and_hold_matches_static_weights():
    stable = _series([100, 110])
    leveraged = _series([100, 130])

    result = buy_and_hold(stable, leveraged, stable_weight=0.5, leveraged_weight=0.5, initial_total=10_000)
    expected_final = 5000 * 1.10 + 5000 * 1.30
    assert abs(result["final_value"] - expected_final) < 0.01


def test_max_drawdown_pct_on_known_series():
    series = _series([100, 120, 90, 100])  # peak 120 -> trough 90 = -25%
    dd = max_drawdown_pct(series)
    assert abs(dd - (-25.0)) < 0.01


def test_cagr_pct_on_known_series():
    dates = pd.bdate_range("2024-01-01", periods=252)  # ~1 trading year
    series = pd.Series([100] * 251 + [110], index=dates)
    cagr = cagr_pct(series, trading_days_per_year=252)
    assert abs(cagr - 10.0) < 0.5


if __name__ == "__main__":
    test_trade_fires_on_up_move_above_threshold()
    test_trade_fires_on_down_move_below_threshold()
    test_no_trade_when_move_within_threshold()
    test_trade_executes_at_next_day_open_not_decision_day_close()
    test_zero_tax_and_cost_are_backward_compatible()
    test_tax_reduces_reinvested_proceeds_on_realized_gain()
    test_no_tax_owed_on_realized_loss()
    test_cost_pct_reduces_reinvested_proceeds()
    test_trade_size_capped_at_available_holding()
    test_buy_and_hold_matches_static_weights()
    test_max_drawdown_pct_on_known_series()
    test_cagr_pct_on_known_series()
    print("All leverage rotation tests passed.")
