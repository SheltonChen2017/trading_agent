"""
Sanity tests for strategies/trend_vol_rotation.py. Run with:
python tests/test_trend_vol_rotation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from strategies.trend_vol_rotation import (
    DEFAULT_STATE_WEIGHTS,
    build_state_weights,
    classify_trend,
    grid_search_state_weights,
    simulate_regime_rotation,
)


def _series(prices: list[float]) -> pd.Series:
    dates = pd.bdate_range("2020-01-01", periods=len(prices))
    return pd.Series(prices, index=dates)


def test_classify_trend_none_without_enough_history():
    close = _series(list(range(100, 150)))  # only 50 days, lookback 200
    assert classify_trend(close, close.index[-1], lookback_days=200) is None


def test_classify_trend_uptrend_when_above_sma():
    # flat at 100 for 200 days, then a jump to 150 on the last day
    prices = [100.0] * 200 + [150.0]
    close = _series(prices)
    assert classify_trend(close, close.index[-1], lookback_days=200) == "uptrend"


def test_classify_trend_downtrend_when_below_sma():
    prices = [100.0] * 200 + [50.0]
    close = _series(prices)
    assert classify_trend(close, close.index[-1], lookback_days=200) == "downtrend"


def _steady_uptrend_low_vol_series(days: int) -> pd.Series:
    rng = np.random.default_rng(1)
    returns = rng.normal(0.0006, 0.003, size=days)  # small steady drift, low vol
    close = 100 * np.cumprod(1 + returns)
    return _series(list(close))


def test_simulate_regime_rotation_trades_less_than_daily_threshold_version():
    # A calm, steadily rising series shouldn't trigger many rebalances:
    # only checked every rebalance_check_days, and state should mostly
    # stay in one bucket (uptrend_low_vol) the whole way.
    stable = _steady_uptrend_low_vol_series(500)
    leveraged = _series(list(100 * (stable / stable.iloc[0]) ** 3))  # crude 3x-ish proxy

    result = simulate_regime_rotation(
        stable, leveraged, stable, leveraged, vol_threshold_pct=5.0,
        trend_lookback_days=50, vol_lookback_days=30, rebalance_check_days=21,
    )
    # 500 days / 21-day checks ~= 24 checks; expect far fewer actual trades
    # than checks since state should stay stable, and nowhere near one
    # trade per trading day.
    assert result["n_trades"] < 500 / 21


def test_simulate_regime_rotation_respects_start_date_for_warmup():
    # Build a series where a real uptrend was already established BEFORE
    # start_date. If start_date is used purely for warmup, the very first
    # simulated date should already classify correctly (not "warming_up").
    stable = _steady_uptrend_low_vol_series(400)
    leveraged = _series(list(100 * (stable / stable.iloc[0]) ** 3))
    start_date = stable.index[300]

    result = simulate_regime_rotation(
        stable, leveraged, stable, leveraged, vol_threshold_pct=5.0,
        trend_lookback_days=50, vol_lookback_days=30, rebalance_check_days=21,
        start_date=start_date,
    )
    first_state = result["trade_log"][0]["state"]
    assert first_state != "warming_up"


def test_rebalance_executes_at_next_day_open_not_check_day_close():
    # Regression test for a real look-ahead bug: the regime state on a
    # check date is only knowable from that date's own completed close,
    # but the rebalance trade must execute at the FOLLOWING day's open,
    # not the check date's own close. Build 250 flat days (enough
    # trailing history for a 200-day SMA), then a jump on the day
    # simulation STARTS (via start_date), so the only check happens on
    # day 0 of the sim and the only trade executes on day 1 -- with day
    # 1's open deliberately far from day 0's close.
    flat_days = 250
    stable_close_prices = [100.0] * flat_days + [140.0, 140.0, 140.0]
    stable_close = _series(stable_close_prices)
    leveraged_close = _series([100.0 * (p / 100.0) ** 3 for p in stable_close_prices])

    stable_open_prices = list(stable_close_prices)
    leveraged_open_prices = list(leveraged_close.tolist())
    stable_open_prices[flat_days + 1] = 500.0  # day AFTER the jump/check day: deliberately far from its close
    leveraged_open_prices[flat_days + 1] = 700.0
    stable_open = _series(stable_open_prices)
    leveraged_open = _series(leveraged_open_prices)

    result = simulate_regime_rotation(
        stable_close, leveraged_close, stable_open, leveraged_open, vol_threshold_pct=50.0,
        state_weights={"uptrend_low_vol": (0.2, 0.8), "uptrend_high_vol": (0.2, 0.8),
                        "downtrend_low_vol": (1.0, 0.0), "downtrend_high_vol": (1.0, 0.0)},
        trend_lookback_days=200, vol_lookback_days=30, rebalance_check_days=100,
        fallback_weights=(1.0, 0.0), start_date=stable_close.index[flat_days],
    )
    assert result["n_trades"] == 1
    trade = result["trade_log"][0]
    assert trade["state"] == "uptrend_low_vol"
    assert trade["date"] == stable_close.index[flat_days + 1]  # executes the day AFTER the check/jump day


def test_default_state_weights_sum_to_one():
    for state, (stable_w, lev_w) in DEFAULT_STATE_WEIGHTS.items():
        assert abs((stable_w + lev_w) - 1.0) < 1e-9, state


def test_build_state_weights_keeps_downtrend_fully_defensive():
    weights = build_state_weights(low_vol_lev_weight=0.85, high_vol_lev_weight=0.6)
    assert abs(weights["uptrend_low_vol"][0] - 0.15) < 1e-9
    assert abs(weights["uptrend_low_vol"][1] - 0.85) < 1e-9
    assert abs(weights["uptrend_high_vol"][0] - 0.4) < 1e-9
    assert abs(weights["uptrend_high_vol"][1] - 0.6) < 1e-9
    assert weights["downtrend_low_vol"] == (1.0, 0.0)
    assert weights["downtrend_high_vol"] == (1.0, 0.0)


def test_grid_search_state_weights_skips_incoherent_combos_and_ranks_by_calmar():
    stable = _steady_uptrend_low_vol_series(300)
    leveraged = _series(list(100 * (stable / stable.iloc[0]) ** 3))

    grid_df = grid_search_state_weights(
        stable, leveraged, stable, leveraged, vol_threshold_pct=5.0,
        low_vol_weights=(0.5, 1.0), high_vol_weights=(0.3, 0.8),
        trend_lookback_days=50, vol_lookback_days=30, rebalance_check_days=21,
    )
    # (0.5, 0.8) is incoherent (choppier state more aggressive than calm state) -> skipped
    combos = set(zip(grid_df["low_vol_lev_weight"], grid_df["high_vol_lev_weight"]))
    assert (0.5, 0.8) not in combos
    assert (1.0, 0.8) in combos
    # sorted descending by calmar_ratio
    assert list(grid_df["calmar_ratio"]) == sorted(grid_df["calmar_ratio"], reverse=True)


if __name__ == "__main__":
    test_classify_trend_none_without_enough_history()
    test_classify_trend_uptrend_when_above_sma()
    test_classify_trend_downtrend_when_below_sma()
    test_simulate_regime_rotation_trades_less_than_daily_threshold_version()
    test_simulate_regime_rotation_respects_start_date_for_warmup()
    test_rebalance_executes_at_next_day_open_not_check_day_close()
    test_default_state_weights_sum_to_one()
    test_build_state_weights_keeps_downtrend_fully_defensive()
    test_grid_search_state_weights_skips_incoherent_combos_and_ranks_by_calmar()
    print("All trend/vol rotation tests passed.")
