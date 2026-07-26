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
    stable = _series([100, 101, 101, 101])
    leveraged = _series([100, 110, 110, 110])  # +10% day 1, then flat

    result = simulate_leverage_rotation(
        stable, leveraged, initial_stable=5000, initial_leveraged=5000,
        threshold_pct=2.0, trade_size=500,
    )
    assert result["n_trades"] == 1
    assert result["trade_log"][0]["action"] == "trim_leveraged"


def test_trade_fires_on_down_move_below_threshold():
    stable = _series([100, 99, 99, 99])
    leveraged = _series([100, 85, 85, 85])  # -15% day 1

    result = simulate_leverage_rotation(
        stable, leveraged, initial_stable=5000, initial_leveraged=5000,
        threshold_pct=2.0, trade_size=500,
    )
    assert result["n_trades"] == 1
    assert result["trade_log"][0]["action"] == "buy_leveraged_dip"


def test_no_trade_when_move_within_threshold():
    stable = _series([100, 100.5, 101, 101.5])
    leveraged = _series([100, 101, 102, 103])  # 1%/day moves, threshold is 2%

    result = simulate_leverage_rotation(
        stable, leveraged, initial_stable=5000, initial_leveraged=5000,
        threshold_pct=2.0, trade_size=500,
    )
    assert result["n_trades"] == 0


def test_trade_does_not_change_total_value_on_the_day_it_fires():
    # A trade is just a same-day reallocation at that day's prices, so
    # total portfolio value right after the trade must equal the
    # no-trade total for that same day.
    stable = _series([100, 101, 101])
    leveraged = _series([100, 110, 110])

    result = simulate_leverage_rotation(
        stable, leveraged, initial_stable=5000, initial_leveraged=5000,
        threshold_pct=2.0, trade_size=500,
    )
    expected_day1_value = 50 * 101 + 50 * 110  # pre-trade share counts at day-1 prices
    assert abs(result["series"].iloc[1] - expected_day1_value) < 0.01


def test_trade_size_capped_at_available_holding():
    stable = _series([100, 200, 200])  # stable moons, tiny holding to sell from later
    leveraged = _series([100, 90, 60])  # then leveraged craters hard

    result = simulate_leverage_rotation(
        stable, leveraged, initial_stable=100, initial_leveraged=5000,
        threshold_pct=2.0, trade_size=500,
    )
    # day 2: leveraged drops another ~33% -> triggers buy_leveraged_dip,
    # but stable only has ~$200 to sell from, far less than trade_size=500
    assert result["n_trades"] == 2
    second_trade = result["trade_log"][1]
    assert second_trade["value"] <= 200.01  # capped, not the full $500


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
    test_trade_does_not_change_total_value_on_the_day_it_fires()
    test_trade_size_capped_at_available_holding()
    test_buy_and_hold_matches_static_weights()
    test_max_drawdown_pct_on_known_series()
    test_cagr_pct_on_known_series()
    print("All leverage rotation tests passed.")
