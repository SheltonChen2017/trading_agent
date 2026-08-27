"""Adversarial regression tests for SYS-P2-010 input contracts."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import compute_benchmark_forward_returns, run_backtest
from backtest.portfolio_simulator import simulate_portfolio
from strategies.decline_grid import (
    find_entry_dates,
    run_decline_grid_backtest,
    simulate_buy_and_hold,
    simulate_episode,
)
from strategies.kelly_rotation import simulate_kelly_rotation
from strategies.leverage_rotation import buy_and_hold, cagr_pct, simulate_leverage_rotation
from strategies.trend_vol_rotation import build_state_weights, simulate_regime_rotation
from strategies.vol_target_rotation import simulate_vol_target_rotation


def _frame(periods: int = 45) -> pd.DataFrame:
    index = pd.bdate_range("2025-01-02", periods=periods)
    prices = np.linspace(100.0, 110.0, periods)
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices + 1.0,
            "low": prices - 1.0,
            "close": prices,
            "volume": np.full(periods, 1_000_000.0),
        },
        index=index,
    )


def _series(periods: int = 8) -> pd.Series:
    return pd.Series(
        np.linspace(100.0, 105.0, periods),
        index=pd.bdate_range("2025-01-02", periods=periods),
    )


def _rotation_series() -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    stable = _series()
    leveraged = stable * 1.5
    return stable, leveraged, stable.copy(), leveraged.copy()


@pytest.mark.parametrize("invalid_horizon", [True, 0, -1, 1.5])
def test_forward_backtests_reject_non_positive_integer_horizons(invalid_horizon):
    frame = _frame()
    with pytest.raises(ValueError, match="hold_days"):
        run_backtest({"TEST": frame}, hold_days=invalid_horizon)
    with pytest.raises(ValueError, match="hold_days"):
        compute_benchmark_forward_returns(frame, hold_days=invalid_horizon)
    with pytest.raises(ValueError, match="hold_days"):
        simulate_portfolio({"TEST": frame}, hold_days=invalid_horizon)


def test_same_session_mode_has_explicit_zero_horizon_exception_only():
    frame = _frame()
    result = run_backtest(
        {"TEST": frame},
        hold_days=0,
        slippage_pct=0.0,
        entry_timing="same_day_open_to_close",
    )
    assert isinstance(result, pd.DataFrame)
    benchmark = compute_benchmark_forward_returns(
        frame,
        hold_days=0,
        slippage_pct=0.0,
        entry_timing="same_day_open_to_close",
    )
    assert len(benchmark) == len(frame)
    for invalid in (True, -1, 0.5):
        with pytest.raises(ValueError, match="hold_days"):
            run_backtest(
                {"TEST": frame},
                hold_days=invalid,
                entry_timing="same_day_open_to_close",
            )


@pytest.mark.parametrize("invalid_cost", [True, float("nan"), float("inf"), -0.01, 1.0])
def test_slippage_refuses_nonfinite_negative_and_unbounded_values(invalid_cost):
    frame = _frame()
    with pytest.raises(ValueError, match="slippage_pct"):
        run_backtest({"TEST": frame}, slippage_pct=invalid_cost)
    with pytest.raises(ValueError, match="slippage_pct"):
        compute_benchmark_forward_returns(frame, slippage_pct=invalid_cost)
    with pytest.raises(ValueError, match="slippage_pct"):
        simulate_portfolio({"TEST": frame}, slippage_pct=invalid_cost)
    with pytest.raises(ValueError, match="slippage_pct"):
        simulate_episode(frame, signal_idx=0, slippage_pct=invalid_cost)
    with pytest.raises(ValueError, match="slippage_pct"):
        run_decline_grid_backtest({"TEST": frame}, slippage_pct=invalid_cost)


@pytest.mark.parametrize("invalid_cost", [True, float("nan"), float("inf"), -0.01, 1.0])
def test_rotation_strategies_refuse_invalid_transaction_costs(invalid_cost):
    args = _rotation_series()
    with pytest.raises(ValueError, match="cost_pct"):
        simulate_leverage_rotation(*args, cost_pct=invalid_cost)
    with pytest.raises(ValueError, match="cost_pct"):
        simulate_regime_rotation(*args, vol_threshold_pct=2.0, cost_pct=invalid_cost)
    with pytest.raises(ValueError, match="cost_pct"):
        simulate_vol_target_rotation(*args, target_vol_pct=1.0, cost_pct=invalid_cost)
    with pytest.raises(ValueError, match="cost_pct"):
        simulate_kelly_rotation(*args, kelly_fraction=0.5, cost_pct=invalid_cost)


def test_rotation_strategies_refuse_invalid_or_overcombined_taxes_and_costs():
    args = _rotation_series()
    for call in (
        lambda: simulate_leverage_rotation(*args, tax_rate=-0.01),
        lambda: simulate_regime_rotation(*args, vol_threshold_pct=2.0, tax_rate=float("nan")),
        lambda: simulate_vol_target_rotation(*args, target_vol_pct=1.0, tax_rate=float("inf")),
        lambda: simulate_kelly_rotation(*args, kelly_fraction=0.5, tax_rate=-0.01),
    ):
        with pytest.raises(ValueError, match="tax_rate"):
            call()
    with pytest.raises(ValueError, match=r"cost_pct \+ tax_rate"):
        simulate_leverage_rotation(*args, cost_pct=0.6, tax_rate=0.5)


@pytest.mark.parametrize("invalid_cadence", [True, 0, -1, 1.5])
def test_rotation_rebalance_cadence_is_a_positive_integer(invalid_cadence):
    args = _rotation_series()
    with pytest.raises(ValueError, match="rebalance_check_days"):
        simulate_regime_rotation(
            *args,
            vol_threshold_pct=2.0,
            rebalance_check_days=invalid_cadence,
        )
    with pytest.raises(ValueError, match="rebalance_check_days"):
        simulate_vol_target_rotation(
            *args,
            target_vol_pct=1.0,
            rebalance_check_days=invalid_cadence,
        )
    with pytest.raises(ValueError, match="rebalance_check_days"):
        simulate_kelly_rotation(
            *args,
            kelly_fraction=0.5,
            rebalance_check_days=invalid_cadence,
        )


def test_counts_and_lookbacks_refuse_bool_zero_negative_and_float():
    frame = _frame()
    for invalid in (True, 0, -1, 1.5):
        with pytest.raises(ValueError, match="max_concurrent_positions"):
            simulate_portfolio({"TEST": frame}, max_concurrent_positions=invalid)
        with pytest.raises(ValueError, match="low_lookback_days"):
            find_entry_dates(frame, low_lookback_days=invalid)
        with pytest.raises(ValueError, match="max_hold_days"):
            simulate_episode(frame, signal_idx=0, max_hold_days=invalid)
        with pytest.raises(ValueError, match="trading_days_per_year"):
            cagr_pct(_series(), trading_days_per_year=invalid)


def test_long_only_weights_and_capital_are_bounded():
    args = _rotation_series()
    with pytest.raises(ValueError, match="state_weights"):
        simulate_regime_rotation(
            *args,
            vol_threshold_pct=2.0,
            state_weights={"uptrend_low_vol": (1.1, -0.1)},
        )
    with pytest.raises(ValueError, match="fallback_weights"):
        simulate_vol_target_rotation(
            *args,
            target_vol_pct=1.0,
            fallback_weights=(0.7, 0.2),
        )
    with pytest.raises(ValueError, match="max_leveraged_weight"):
        simulate_kelly_rotation(
            *args,
            kelly_fraction=0.5,
            max_leveraged_weight=1.01,
        )
    with pytest.raises(ValueError, match="position_size_pct"):
        simulate_portfolio({"TEST": _frame()}, position_size_pct=1.01)
    with pytest.raises(ValueError, match="weights"):
        buy_and_hold(args[0], args[1], stable_weight=1.1, leveraged_weight=-0.1)
    with pytest.raises(ValueError, match="low_vol_lev_weight"):
        build_state_weights(low_vol_lev_weight=True, high_vol_lev_weight=0.5)
    with pytest.raises(ValueError, match="initial_cash"):
        simulate_portfolio({}, initial_cash=0.0)
    with pytest.raises(ValueError, match="initial_total"):
        simulate_vol_target_rotation(*args, target_vol_pct=1.0, initial_total=0.0)


def test_nonpositive_or_nonfinite_prices_are_refused_at_every_boundary():
    bad_frame = _frame()
    bad_frame.loc[bad_frame.index[5], "close"] = 0.0
    with pytest.raises(ValueError, match="positive prices"):
        run_backtest({"TEST": bad_frame})

    bad_frame = _frame()
    bad_frame.loc[bad_frame.index[5], "open"] = np.nan
    with pytest.raises(ValueError, match="finite prices"):
        simulate_portfolio({"TEST": bad_frame})

    args = list(_rotation_series())
    args[1] = args[1].copy()
    args[1].iloc[2] = -1.0
    with pytest.raises(ValueError, match="positive prices"):
        simulate_leverage_rotation(*args)

    bad_frame = _frame()
    bad_frame.loc[bad_frame.index[1], "open"] = float("inf")
    with pytest.raises(ValueError, match="finite prices"):
        simulate_episode(bad_frame, signal_idx=0)


def test_rotation_prices_require_exact_unique_monotonic_alignment():
    stable, leveraged, stable_open, leveraged_open = _rotation_series()

    misaligned = leveraged_open.copy()
    misaligned.index = misaligned.index + pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="exactly align"):
        simulate_leverage_rotation(stable, leveraged, stable_open, misaligned)

    duplicate = leveraged.copy()
    duplicate.index = duplicate.index.where(
        np.arange(len(duplicate)) != 2,
        duplicate.index[1],
    )
    with pytest.raises(ValueError, match="unique sessions"):
        simulate_regime_rotation(
            stable,
            duplicate,
            stable_open,
            leveraged_open,
            vol_threshold_pct=2.0,
        )

    with pytest.raises(ValueError, match="monotonically increasing"):
        simulate_vol_target_rotation(
            stable.iloc[::-1],
            leveraged.iloc[::-1],
            stable_open.iloc[::-1],
            leveraged_open.iloc[::-1],
            target_vol_pct=1.0,
        )


def test_exit_index_can_equal_but_never_precede_entry_index():
    frame = _frame(periods=5)
    same_session = simulate_buy_and_hold(
        frame,
        entry_idx=2,
        exit_idx=2,
        slippage_pct=0.0,
        exit_price_column="close",
    )
    assert np.isfinite(same_session)
    with pytest.raises(ValueError, match="must not precede"):
        simulate_buy_and_hold(
            frame,
            entry_idx=3,
            exit_idx=2,
            slippage_pct=0.0,
            exit_price_column="close",
        )
    with pytest.raises(ValueError, match="signal_idx"):
        simulate_episode(frame, signal_idx=-1)
