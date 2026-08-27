"""
Sanity tests for strategies/vol_target_rotation.py. Run with:
python tests/test_vol_target_rotation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from signals.regime import compute_trailing_market_volatility
from strategies.vol_target_rotation import (
    compute_target_leveraged_weight,
    grid_search_vol_target,
    simulate_vol_target_rotation,
)


def _series(prices: list[float]) -> pd.Series:
    dates = pd.bdate_range("2020-01-01", periods=len(prices))
    return pd.Series(prices, index=dates)


def test_compute_target_leveraged_weight_scales_inversely_with_realized_vol():
    assert compute_target_leveraged_weight(1.0, target_vol_pct=1.0, max_leveraged_weight=1.0) == 1.0
    assert compute_target_leveraged_weight(2.0, target_vol_pct=1.0, max_leveraged_weight=1.0) == 0.5
    # formula would give 2.0 (below target vol -> lever up) but must cap at max_leveraged_weight
    assert compute_target_leveraged_weight(0.5, target_vol_pct=1.0, max_leveraged_weight=1.0) == 1.0
    with pytest.raises(ValueError, match="max_leveraged_weight"):
        compute_target_leveraged_weight(0.5, target_vol_pct=1.0, max_leveraged_weight=1.5)


def test_compute_target_leveraged_weight_zero_on_missing_or_zero_vol():
    assert compute_target_leveraged_weight(None, target_vol_pct=1.0, max_leveraged_weight=1.0) == 0.0
    assert compute_target_leveraged_weight(0.0, target_vol_pct=1.0, max_leveraged_weight=1.0) == 0.0
    assert compute_target_leveraged_weight(-1.0, target_vol_pct=1.0, max_leveraged_weight=1.0) == 0.0


def _flat_then_crash(flat_days: int = 250, crash_price: float = 60.0) -> list[float]:
    return [100.0] * flat_days + [crash_price] * 3


def test_downtrend_forces_zero_leveraged_weight():
    flat_days = 250
    stable_close = _series(_flat_then_crash(flat_days, crash_price=60.0))  # well below 200-day SMA -> downtrend
    leveraged_close = _series([100.0 * (p / 100.0) ** 3 for p in _flat_then_crash(flat_days, crash_price=60.0)])

    result = simulate_vol_target_rotation(
        stable_close, leveraged_close, stable_close, leveraged_close,
        target_vol_pct=1.0, max_leveraged_weight=1.0,
        trend_lookback_days=200, vol_lookback_days=20, rebalance_check_days=100,
        fallback_weights=(0.0, 1.0), start_date=stable_close.index[flat_days],
    )
    assert result["n_trades"] == 1
    trade = result["trade_log"][0]
    assert trade["label"] == "downtrend_defensive"
    assert trade["target_lev_w"] == 0.0
    assert trade["target_stable_w"] == 1.0


def test_uptrend_uses_continuous_vol_targeting_matching_the_formula():
    # Steady uptrend (jump up, not down) so trend classifies "uptrend",
    # and the target weight should match compute_target_leveraged_weight()
    # applied to the SAME realized volatility independently computed.
    import numpy as np
    flat_days = 250
    rng = np.random.default_rng(3)
    quiet_returns = rng.normal(0.0005, 0.004, size=3)  # small additional noise on the "jump" tail
    tail_prices = [140.0 * float(np.prod(1 + quiet_returns[: i + 1])) for i in range(3)]
    stable_close = _series([100.0] * flat_days + [140.0] + tail_prices)
    leveraged_prices = [100.0 * (p / 100.0) ** 3 for p in stable_close.tolist()]
    leveraged_close = _series(leveraged_prices)

    target_vol_pct = 1.0
    result = simulate_vol_target_rotation(
        stable_close, leveraged_close, stable_close, leveraged_close,
        target_vol_pct=target_vol_pct, max_leveraged_weight=1.0,
        trend_lookback_days=200, vol_lookback_days=20, rebalance_check_days=200,
        fallback_weights=(0.0, 1.0), start_date=stable_close.index[flat_days],
    )
    assert result["n_trades"] == 1
    trade = result["trade_log"][0]
    assert "uptrend_vol_target" in trade["label"]

    # Independently recompute the realized vol at the check date and confirm
    # the target weight matches the formula applied to that exact number.
    check_date = stable_close.index[flat_days]
    benchmark_df = pd.DataFrame({"close": leveraged_close})
    realized_vol = compute_trailing_market_volatility(benchmark_df, check_date, lookback_days=20)
    expected_target_lev_w = compute_target_leveraged_weight(realized_vol, target_vol_pct, 1.0)
    assert abs(trade["target_lev_w"] - expected_target_lev_w) < 1e-9


def test_rebalance_executes_at_next_day_open_not_check_day_close():
    flat_days = 250
    stable_close_prices = [100.0] * flat_days + [140.0, 140.0, 140.0]
    stable_close = _series(stable_close_prices)
    leveraged_close = _series([100.0 * (p / 100.0) ** 3 for p in stable_close_prices])

    stable_open_prices = list(stable_close_prices)
    leveraged_open_prices = list(leveraged_close.tolist())
    stable_open_prices[flat_days + 1] = 500.0
    leveraged_open_prices[flat_days + 1] = 700.0
    stable_open = _series(stable_open_prices)
    leveraged_open = _series(leveraged_open_prices)

    result = simulate_vol_target_rotation(
        stable_close, leveraged_close, stable_open, leveraged_open,
        target_vol_pct=1.0, max_leveraged_weight=1.0,
        trend_lookback_days=200, vol_lookback_days=20, rebalance_check_days=100,
        fallback_weights=(1.0, 0.0), start_date=stable_close.index[flat_days],
    )
    assert result["n_trades"] == 1
    assert result["trade_log"][0]["date"] == stable_close.index[flat_days + 1]


def test_zero_tax_and_cost_are_backward_compatible():
    stable_close = _series(_flat_then_crash(250, crash_price=60.0))
    leveraged_close = _series([100.0 * (p / 100.0) ** 3 for p in _flat_then_crash(250, crash_price=60.0)])
    result = simulate_vol_target_rotation(
        stable_close, leveraged_close, stable_close, leveraged_close,
        target_vol_pct=1.0, max_leveraged_weight=1.0,
        trend_lookback_days=200, vol_lookback_days=20, rebalance_check_days=100,
        fallback_weights=(0.0, 1.0), start_date=stable_close.index[250],
    )
    assert result["total_tax_paid"] == 0.0
    assert result["total_cost_paid"] == 0.0


def test_grid_search_vol_target_produces_expected_columns():
    import numpy as np
    rng = np.random.default_rng(1)
    returns = rng.normal(0.0006, 0.003, size=300)
    stable = _series(list(100 * np.cumprod(1 + returns)))
    leveraged = _series(list(100 * (stable / stable.iloc[0]) ** 3))

    grid_df = grid_search_vol_target(
        stable, leveraged, stable, leveraged,
        target_vol_options=(1.0, 2.0), max_leveraged_weight_options=(0.8, 1.0),
        trend_lookback_days=50, vol_lookback_days=20, rebalance_check_days=21,
    )
    assert set(grid_df.columns) == {
        "target_vol_pct", "max_leveraged_weight", "n_trades", "cagr_pct",
        "max_drawdown_pct", "calmar_ratio", "total_tax_paid", "total_cost_paid",
    }
    assert len(grid_df) == 4
    assert list(grid_df["calmar_ratio"]) == sorted(grid_df["calmar_ratio"].tolist(), reverse=True)


if __name__ == "__main__":
    test_compute_target_leveraged_weight_scales_inversely_with_realized_vol()
    test_compute_target_leveraged_weight_zero_on_missing_or_zero_vol()
    test_downtrend_forces_zero_leveraged_weight()
    test_uptrend_uses_continuous_vol_targeting_matching_the_formula()
    test_rebalance_executes_at_next_day_open_not_check_day_close()
    test_zero_tax_and_cost_are_backward_compatible()
    test_grid_search_vol_target_produces_expected_columns()
    print("All vol target rotation tests passed.")


def test_unknown_volatility_never_produces_maximum_leverage():
    # Independent review, 2026-07-29, reproduced: NaN defeats `<= 0`, so
    # min(max_leveraged_weight, target/NaN) returned max_leveraged_weight --
    # UNKNOWN volatility produced the MAXIMUM leveraged weight, inverting
    # this function's whole purpose. None and inf were already correct;
    # only NaN failed, and it failed toward more leverage.
    assert compute_target_leveraged_weight(float("nan"), 0.5, 0.6) == 0.0
    assert compute_target_leveraged_weight(None, 0.5, 0.6) == 0.0
    assert compute_target_leveraged_weight(float("inf"), 0.5, 0.6) == 0.0
    assert compute_target_leveraged_weight(0.0, 0.5, 0.6) == 0.0
    assert compute_target_leveraged_weight(-1.0, 0.5, 0.6) == 0.0
    # Ordinary sizing is unchanged: higher realized vol -> smaller weight.
    assert compute_target_leveraged_weight(1.0, 0.5, 0.6) == 0.5
    assert compute_target_leveraged_weight(5.0, 0.5, 0.6) == 0.1
