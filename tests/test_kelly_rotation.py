"""
Sanity tests for strategies/kelly_rotation.py. Run with:
python tests/test_kelly_rotation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from strategies.kelly_rotation import (
    compute_kelly_leveraged_weight,
    compute_trailing_mean_and_variance,
    compute_trend_acceleration_multiplier,
    grid_search_kelly,
    simulate_kelly_rotation,
)


def _series(prices: list[float]) -> pd.Series:
    dates = pd.bdate_range("2020-01-01", periods=len(prices))
    return pd.Series(prices, index=dates)


def test_compute_trailing_mean_and_variance_matches_hand_computation():
    # Constant +1%/day for 20 days -> mean should be ~0.01, variance ~0
    prices = [100.0]
    for _ in range(25):
        prices.append(prices[-1] * 1.01)
    close = _series(prices)
    mean, var = compute_trailing_mean_and_variance(close, close.index[-1], lookback_days=20)
    assert abs(mean - 0.01) < 1e-6
    assert var < 1e-8


def test_compute_trailing_mean_and_variance_none_without_enough_history():
    close = _series([100.0, 101.0, 102.0])
    assert compute_trailing_mean_and_variance(close, close.index[-1], lookback_days=20) == (None, None)


def test_compute_kelly_leveraged_weight_scales_with_signed_mean_return():
    # Strong positive mean, low variance -> large weight (capped)
    assert compute_kelly_leveraged_weight(0.01, 0.0001, kelly_fraction=0.5, max_leveraged_weight=1.0) == 1.0
    # Negative mean -> zero, regardless of variance
    assert compute_kelly_leveraged_weight(-0.01, 0.0001, kelly_fraction=0.5, max_leveraged_weight=1.0) == 0.0
    # Missing or zero variance -> zero
    assert compute_kelly_leveraged_weight(0.01, None, kelly_fraction=0.5, max_leveraged_weight=1.0) == 0.0
    assert compute_kelly_leveraged_weight(0.01, 0.0, kelly_fraction=0.5, max_leveraged_weight=1.0) == 0.0
    # Exact formula check on an unclipped case
    result = compute_kelly_leveraged_weight(0.001, 0.01, kelly_fraction=0.5, max_leveraged_weight=1.0)
    assert abs(result - (0.5 * 0.001 / 0.01)) < 1e-9


def test_trend_acceleration_multiplier_detects_deceleration():
    # SMA rising throughout -> "now" should be >= "before" -> no dampening
    rising_prices = [100.0 + i * 0.5 for i in range(150)]
    close = _series(rising_prices)
    mult = compute_trend_acceleration_multiplier(close, close.index[-1], medium_lookback_days=50, slope_lookback_days=20)
    assert mult == 1.0

    # Flat-then-falling tail -> the medium SMA should now be BELOW where it was
    decelerating_prices = [100.0 + i * 0.5 for i in range(100)] + [100.0 + 99 * 0.5 - i * 0.3 for i in range(50)]
    close2 = _series(decelerating_prices)
    mult2 = compute_trend_acceleration_multiplier(close2, close2.index[-1], medium_lookback_days=50, slope_lookback_days=20)
    assert mult2 < 1.0


def test_downtrend_forces_zero_leveraged_weight():
    flat_days = 250
    stable_close = _series([100.0] * flat_days + [60.0, 60.0, 60.0])
    leveraged_close = _series([100.0 * (p / 100.0) ** 3 for p in [100.0] * flat_days + [60.0, 60.0, 60.0]])

    result = simulate_kelly_rotation(
        stable_close, leveraged_close, stable_close, leveraged_close,
        kelly_fraction=0.5, max_leveraged_weight=1.0,
        trend_lookback_days=200, kelly_lookback_days=20, rebalance_check_days=100,
        fallback_weights=(0.0, 1.0), start_date=stable_close.index[flat_days],
    )
    assert result["n_trades"] == 1
    assert result["trade_log"][0]["label"] == "downtrend_defensive"
    assert result["trade_log"][0]["target_lev_w"] == 0.0


def test_one_way_ratchet_skips_buying_up():
    # Build a series with an uptrend that would call for INCREASING
    # leveraged weight at the second check -- with the ratchet on, that
    # increase should be skipped (only trims execute).
    flat_days = 250
    rng = np.random.default_rng(2)
    # First jump: modest positive drift+low variance -> some initial Kelly weight
    tail1 = 140.0 * np.cumprod(1 + rng.normal(0.001, 0.002, size=21))
    # Second jump: even stronger, lower-variance drift -> Kelly weight would INCREASE
    tail2 = tail1[-1] * np.cumprod(1 + rng.normal(0.003, 0.001, size=21))
    stable_prices = [100.0] * flat_days + [140.0] + list(tail1) + list(tail2)
    stable_close = _series(stable_prices)
    leveraged_close = _series([100.0 * (p / 100.0) ** 3 for p in stable_prices])

    no_ratchet = simulate_kelly_rotation(
        stable_close, leveraged_close, stable_close, leveraged_close,
        kelly_fraction=0.5, max_leveraged_weight=1.0,
        trend_lookback_days=200, kelly_lookback_days=20, rebalance_check_days=21,
        fallback_weights=(1.0, 0.0), start_date=stable_close.index[flat_days], band_pct=0.01,
    )
    ratcheted = simulate_kelly_rotation(
        stable_close, leveraged_close, stable_close, leveraged_close,
        kelly_fraction=0.5, max_leveraged_weight=1.0,
        trend_lookback_days=200, kelly_lookback_days=20, rebalance_check_days=21,
        fallback_weights=(1.0, 0.0), start_date=stable_close.index[flat_days], band_pct=0.01,
        one_way_ratchet=True,
    )
    # The ratcheted version should never have MORE trades than the free version,
    # since every "buy up" trade the free version takes, the ratchet skips.
    assert ratcheted["n_trades"] <= no_ratchet["n_trades"]


def test_zero_tax_and_cost_are_backward_compatible():
    stable_close = _series([100.0] * 250 + [60.0, 60.0, 60.0])
    leveraged_close = _series([100.0 * (p / 100.0) ** 3 for p in [100.0] * 250 + [60.0, 60.0, 60.0]])
    result = simulate_kelly_rotation(
        stable_close, leveraged_close, stable_close, leveraged_close,
        kelly_fraction=0.5, max_leveraged_weight=1.0,
        trend_lookback_days=200, kelly_lookback_days=20, rebalance_check_days=100,
        fallback_weights=(0.0, 1.0), start_date=stable_close.index[250],
    )
    assert result["total_tax_paid"] == 0.0
    assert result["total_cost_paid"] == 0.0


def test_grid_search_kelly_produces_expected_columns():
    rng = np.random.default_rng(1)
    returns = rng.normal(0.0006, 0.003, size=300)
    stable = _series(list(100 * np.cumprod(1 + returns)))
    leveraged = _series(list(100 * (stable / stable.iloc[0]) ** 3))

    grid_df = grid_search_kelly(
        stable, leveraged, stable, leveraged,
        kelly_fraction_options=(0.25, 0.5), max_leveraged_weight_options=(0.8, 1.0),
        trend_lookback_days=50, kelly_lookback_days=20, rebalance_check_days=21,
    )
    assert set(grid_df.columns) == {
        "kelly_fraction", "max_leveraged_weight", "n_trades", "cagr_pct",
        "max_drawdown_pct", "calmar_ratio", "total_tax_paid", "total_cost_paid",
    }
    assert len(grid_df) == 4


if __name__ == "__main__":
    test_compute_trailing_mean_and_variance_matches_hand_computation()
    test_compute_trailing_mean_and_variance_none_without_enough_history()
    test_compute_kelly_leveraged_weight_scales_with_signed_mean_return()
    test_trend_acceleration_multiplier_detects_deceleration()
    test_downtrend_forces_zero_leveraged_weight()
    test_one_way_ratchet_skips_buying_up()
    test_zero_tax_and_cost_are_backward_compatible()
    test_grid_search_kelly_produces_expected_columns()
    print("All Kelly rotation tests passed.")


def test_unknown_kelly_inputs_never_produce_maximum_leverage():
    # Independent review, 2026-07-29, reproduced: NaN defeats `<= 0`, so
    # min(max_leveraged_weight, NaN) returned max_leveraged_weight --
    # unknown mean/variance produced the MAXIMUM leveraged weight. Same
    # class as vol_target_rotation.compute_target_leveraged_weight().
    assert compute_kelly_leveraged_weight(float("nan"), 0.0004, 0.5, 0.6) == 0.0
    assert compute_kelly_leveraged_weight(0.001, float("nan"), 0.5, 0.6) == 0.0
    assert compute_kelly_leveraged_weight(None, 0.0004, 0.5, 0.6) == 0.0
    assert compute_kelly_leveraged_weight(0.001, None, 0.5, 0.6) == 0.0
    assert compute_kelly_leveraged_weight(0.001, float("inf"), 0.5, 0.6) == 0.0
    assert compute_kelly_leveraged_weight(0.001, 0.0, 0.5, 0.6) == 0.0
    # Ordinary sizing unchanged.
    assert compute_kelly_leveraged_weight(0.0001, 0.0004, 0.5, 0.6) == 0.125
