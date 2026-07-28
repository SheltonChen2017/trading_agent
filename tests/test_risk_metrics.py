"""
Sanity tests for backtest/risk_metrics.py. Run with:
python tests/test_risk_metrics.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import backtest.portfolio_simulator as portfolio_simulator
from backtest.risk_metrics import (
    downside_capture_pct,
    expected_shortfall_pct,
    max_drawdown_pct,
    time_under_water,
    upside_capture_pct,
)
from strategies.leverage_rotation import max_drawdown_pct as leverage_rotation_max_drawdown_pct


def _series(values: list[float]) -> pd.Series:
    dates = pd.bdate_range("2024-01-01", periods=len(values))
    return pd.Series(values, index=dates)


# --- max_drawdown_pct: same canonical implementation everywhere
# (docs/ARCHITECTURE_DEBT.md: this used to be two independently drifting
# copies -- backtest/portfolio_simulator.py's private _max_drawdown_pct
# and strategies/leverage_rotation.py's public max_drawdown_pct).

def test_max_drawdown_pct_matches_existing_hand_computed_value():
    series = _series([100, 120, 90, 100])  # peak 120 -> trough 90 = -25%
    assert abs(max_drawdown_pct(series) - (-25.0)) < 0.01
    assert abs(leverage_rotation_max_drawdown_pct(series) - (-25.0)) < 0.01


def test_portfolio_simulator_delegates_to_the_same_canonical_function():
    # Identity check, not just equal output -- confirms
    # portfolio_simulator.py imports the SAME function object rather than
    # a second implementation that merely happens to agree today.
    assert portfolio_simulator._max_drawdown_pct is max_drawdown_pct


def test_max_drawdown_pct_empty_series_returns_zero():
    assert max_drawdown_pct(pd.Series(dtype=float)) == 0.0


# --- expected_shortfall_pct

def test_expected_shortfall_pct_hand_computed():
    # 10 observations, confidence=0.9 -> tail_size = int(10 * 0.1) = 1 ->
    # the single worst observation is the whole tail.
    returns = _series([-5, -3, -1, 0, 1, 2, 3, 4, 5, 6])
    assert abs(expected_shortfall_pct(returns, confidence=0.9) - (-5.0)) < 0.01


def test_expected_shortfall_pct_insufficient_observations_returns_zero():
    # 5 observations, confidence=0.99 -> tail_size = int(5 * 0.01) = 0.
    returns = _series([-2, -1, 0, 1, 2])
    assert expected_shortfall_pct(returns, confidence=0.99) == 0.0


def test_expected_shortfall_pct_empty_series_returns_zero():
    assert expected_shortfall_pct(pd.Series(dtype=float)) == 0.0


# --- time_under_water

def test_time_under_water_hand_computed():
    # running peak: [100,110,110,110,110,111] -> under water at indices
    # 2,3,4 (values 90,95,105), a streak of 3; back at/above peak at index
    # 5 (111), so current_days_under_water is 0.
    equity = _series([100, 110, 90, 95, 105, 111])
    result = time_under_water(equity)
    assert result["max_days_under_water"] == 3
    assert result["current_days_under_water"] == 0
    assert abs(result["pct_of_period_under_water"] - 50.0) < 0.01


def test_time_under_water_still_under_water_at_end():
    equity = _series([100, 110, 90, 95])
    result = time_under_water(equity)
    assert result["max_days_under_water"] == 2
    assert result["current_days_under_water"] == 2


def test_time_under_water_empty_series():
    result = time_under_water(pd.Series(dtype=float))
    assert result == {"max_days_under_water": 0, "pct_of_period_under_water": 0.0, "current_days_under_water": 0}


# --- downside_capture_pct / upside_capture_pct

def test_downside_capture_pct_hand_computed():
    benchmark = _series([-2, -4, 1, 3])
    strategy = _series([-1, -2, 0.5, 1.5])
    # benchmark down-periods: [-2, -4], mean -3; strategy over those same
    # periods: [-1, -2], mean -1.5 -> capture = -1.5 / -3 * 100 = 50%.
    assert abs(downside_capture_pct(strategy, benchmark) - 50.0) < 0.01


def test_upside_capture_pct_hand_computed():
    benchmark = _series([-2, -4, 1, 3])
    strategy = _series([-1, -2, 0.5, 1.5])
    # benchmark up-periods: [1, 3], mean 2; strategy over those same
    # periods: [0.5, 1.5], mean 1.0 -> capture = 1.0 / 2 * 100 = 50%.
    assert abs(upside_capture_pct(strategy, benchmark) - 50.0) < 0.01


def test_downside_capture_pct_raises_on_misaligned_index():
    benchmark = _series([-2, -4, 1, 3])
    strategy = pd.Series([-1, -2, 0.5, 1.5], index=pd.bdate_range("2025-01-01", periods=4))
    try:
        downside_capture_pct(strategy, benchmark)
        assert False, "expected ValueError on misaligned index"
    except ValueError:
        pass


def test_downside_capture_pct_returns_none_when_benchmark_never_down():
    benchmark = _series([1, 2, 3])
    strategy = _series([0.5, 0.5, 0.5])
    assert downside_capture_pct(strategy, benchmark) is None


def test_upside_capture_pct_returns_none_when_benchmark_never_up():
    benchmark = _series([-1, -2, -3])
    strategy = _series([-0.5, -0.5, -0.5])
    assert upside_capture_pct(strategy, benchmark) is None


if __name__ == "__main__":
    test_max_drawdown_pct_matches_existing_hand_computed_value()
    test_portfolio_simulator_delegates_to_the_same_canonical_function()
    test_max_drawdown_pct_empty_series_returns_zero()
    test_expected_shortfall_pct_hand_computed()
    test_expected_shortfall_pct_insufficient_observations_returns_zero()
    test_expected_shortfall_pct_empty_series_returns_zero()
    test_time_under_water_hand_computed()
    test_time_under_water_still_under_water_at_end()
    test_time_under_water_empty_series()
    test_downside_capture_pct_hand_computed()
    test_upside_capture_pct_hand_computed()
    test_downside_capture_pct_raises_on_misaligned_index()
    test_downside_capture_pct_returns_none_when_benchmark_never_down()
    test_upside_capture_pct_returns_none_when_benchmark_never_up()
    print("All risk_metrics tests passed.")
