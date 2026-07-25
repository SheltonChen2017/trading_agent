"""
Sanity tests for the backtest engine. Run with: python -m pytest tests/ -v
(or `python tests/test_backtest.py` for a quick manual check).

Uses hand-built data with a KNOWN forward outcome (a shock day followed by
a deliberate bounce-back or continuation), so we can assert the engine
measures exactly the return we planted — not just "runs without crashing".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from backtest.engine import (
    compare_signal_to_baseline,
    run_backtest,
    run_baseline_forward_returns,
    run_multi_horizon_backtest,
    summarize_backtest,
    summarize_multi_horizon,
)


def _series_with_shock_and_known_forward_move(
    days: int, shock_index: int, shock_return: float, forward_daily_return: float, hold_days: int
) -> pd.DataFrame:
    """Flat/quiet series, one shock day, then a deliberate, known drift for
    the following `hold_days` so the backtest's measured forward return is
    predictable and assertable."""
    rng = np.random.default_rng(0)
    returns = rng.normal(loc=0.0, scale=0.002, size=days)
    returns[shock_index] = shock_return
    for i in range(1, hold_days + 1):
        if shock_index + i < days:
            returns[shock_index + i] = forward_daily_return

    close = 100 * np.cumprod(1 + returns)
    volume = np.full(days, 1_000_000.0)
    volume[shock_index] = 4_000_000.0

    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": volume},
        index=dates,
    )


def test_scores_a_winning_dip_reversion():
    hold_days = 5
    # Dip on day 40, then bounces back +1%/day for the next 5 days -> win.
    df = _series_with_shock_and_known_forward_move(
        days=60, shock_index=40, shock_return=-0.08, forward_daily_return=0.01, hold_days=hold_days
    )
    results = run_backtest({"TEST": df}, hold_days=hold_days, slippage_pct=0.0)

    assert not results.empty, "expected the backtest to score the injected dip"
    row = results.iloc[0]
    assert row["direction"] == "dip"
    assert row["net_return_pct"] > 0, "bounce-back after a dip should score as a win"
    assert bool(row["win"]) is True


def test_scores_a_losing_up_fade():
    hold_days = 5
    # Up-shock on day 40, then fades -1%/day for the next 5 days -> loss.
    df = _series_with_shock_and_known_forward_move(
        days=60, shock_index=40, shock_return=0.09, forward_daily_return=-0.01, hold_days=hold_days
    )
    results = run_backtest({"TEST": df}, hold_days=hold_days, slippage_pct=0.0)

    assert not results.empty
    row = results.iloc[0]
    assert row["direction"] == "up"
    assert row["net_return_pct"] < 0, "fading after an up-shock should score as a loss"
    assert bool(row["win"]) is False


def test_slippage_reduces_net_return():
    hold_days = 5
    df = _series_with_shock_and_known_forward_move(
        days=60, shock_index=40, shock_return=-0.08, forward_daily_return=0.01, hold_days=hold_days
    )
    no_slip = run_backtest({"TEST": df}, hold_days=hold_days, slippage_pct=0.0)
    with_slip = run_backtest({"TEST": df}, hold_days=hold_days, slippage_pct=0.01)

    assert with_slip.iloc[0]["net_return_pct"] < no_slip.iloc[0]["net_return_pct"]


def test_summarize_groups_by_direction():
    hold_days = 5
    dip_df = _series_with_shock_and_known_forward_move(
        days=60, shock_index=40, shock_return=-0.08, forward_daily_return=0.01, hold_days=hold_days
    )
    results = run_backtest({"TEST": dip_df}, hold_days=hold_days, slippage_pct=0.0)
    summary = summarize_backtest(results)

    assert not summary.empty
    assert set(summary.columns) == {
        "direction", "count", "win_rate_pct", "mean_net_return_pct", "median_net_return_pct",
        "mean_return_zscore", "mean_volume_zscore",
    }
    assert summary.loc[summary["direction"] == "dip", "count"].iloc[0] == 1


def test_empty_data_returns_empty_frame():
    results = run_backtest({})
    assert results.empty
    summary = summarize_backtest(results)
    assert summary.empty


def test_multi_horizon_backtest_runs_each_hold_period_separately():
    # A dip that bounces back consistently for the next 10 days -> every
    # horizon up to 10 should measure a positive net return, and later
    # horizons should be scored on the same signal, just held longer.
    df = _series_with_shock_and_known_forward_move(
        days=60, shock_index=40, shock_return=-0.08, forward_daily_return=0.01, hold_days=10
    )
    results_by_horizon = run_multi_horizon_backtest({"TEST": df}, hold_days_options=[1, 5, 10], slippage_pct=0.0)

    assert set(results_by_horizon.keys()) == {1, 5, 10}
    for hold_days, results in results_by_horizon.items():
        assert not results.empty, f"expected a scored signal at hold_days={hold_days}"
        assert results.iloc[0]["net_return_pct"] > 0


def test_summarize_multi_horizon_includes_hold_days_and_horizon_columns():
    df = _series_with_shock_and_known_forward_move(
        days=60, shock_index=40, shock_return=-0.08, forward_daily_return=0.01, hold_days=10
    )
    results_by_horizon = run_multi_horizon_backtest({"TEST": df}, hold_days_options=[1, 5, 10], slippage_pct=0.0)
    summary = summarize_multi_horizon(results_by_horizon)

    assert set(summary["hold_days"]) == {1, 5, 10}
    assert set(summary["horizon"]) == {"1 day", "1 week", "2 weeks"}
    assert "mean_return_zscore" in summary.columns


def test_summarize_multi_horizon_empty_input():
    summary = summarize_multi_horizon({})
    assert summary.empty
    assert list(summary.columns) == [
        "hold_days", "horizon", "direction", "count", "win_rate_pct",
        "mean_net_return_pct", "median_net_return_pct", "mean_return_zscore", "mean_volume_zscore",
    ]


def test_baseline_forward_returns_matches_hand_computed_value():
    # Pure 0.5%/day drift, no shocks at all -> the 5-day forward return
    # from any starting day is exactly (1.005**5 - 1) * 100, minus slippage.
    days = 30
    hold_days = 5
    returns = np.full(days, 0.005)
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    df = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )

    baseline = run_baseline_forward_returns({"TEST": df}, hold_days=hold_days, slippage_pct=0.0)
    expected = (1.005**hold_days - 1) * 100

    assert not baseline.empty
    assert baseline["net_return_pct"].round(2).unique().tolist() == [round(expected, 2)]


def test_baseline_forward_returns_empty_when_no_forward_history():
    df = _series_with_shock_and_known_forward_move(
        days=3, shock_index=0, shock_return=0.001, forward_daily_return=0.0, hold_days=1
    )
    baseline = run_baseline_forward_returns({"TEST": df}, hold_days=10)
    assert baseline.empty


def test_compare_signal_to_baseline_edge_matches_independently_computed_means():
    # edge_vs_baseline_pct should be exactly signal_mean - baseline_mean,
    # where each mean is independently verifiable from run_backtest() and
    # run_baseline_forward_returns() directly — this is what actually needs
    # to be correct: the arithmetic tying the two together.
    hold_days = 5
    df = _series_with_shock_and_known_forward_move(
        days=60, shock_index=40, shock_return=-0.08, forward_daily_return=0.01, hold_days=hold_days
    )
    data = {"TEST": df}
    comparison = compare_signal_to_baseline(data, hold_days_options=[hold_days], slippage_pct=0.0)

    results = run_backtest(data, hold_days=hold_days, slippage_pct=0.0)
    baseline = run_baseline_forward_returns(data, hold_days=hold_days, slippage_pct=0.0)

    dip_row = comparison[(comparison["hold_days"] == hold_days) & (comparison["direction"] == "dip")].iloc[0]
    expected_signal_mean = round(results[results["direction"] == "dip"]["net_return_pct"].mean(), 3)
    expected_baseline_mean = round(baseline["net_return_pct"].mean(), 3)

    assert dip_row["signal_mean_return_pct"] == expected_signal_mean
    assert dip_row["baseline_mean_return_pct"] == expected_baseline_mean
    assert dip_row["edge_vs_baseline_pct"] == round(expected_signal_mean - expected_baseline_mean, 3)


def test_compare_signal_to_baseline_handles_no_signals():
    hold_days = 5
    rng = np.random.default_rng(2)
    days = 40
    close = 100 * np.cumprod(1 + rng.normal(0, 0.001, size=days))  # quiet, nothing to flag
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    df = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )
    comparison = compare_signal_to_baseline({"TEST": df}, hold_days_options=[hold_days])
    assert (comparison["signal_count"] == 0).all()
    assert comparison["signal_mean_return_pct"].isna().all()


if __name__ == "__main__":
    test_scores_a_winning_dip_reversion()
    test_scores_a_losing_up_fade()
    test_slippage_reduces_net_return()
    test_summarize_groups_by_direction()
    test_empty_data_returns_empty_frame()
    test_multi_horizon_backtest_runs_each_hold_period_separately()
    test_summarize_multi_horizon_includes_hold_days_and_horizon_columns()
    test_summarize_multi_horizon_empty_input()
    test_baseline_forward_returns_matches_hand_computed_value()
    test_baseline_forward_returns_empty_when_no_forward_history()
    test_compare_signal_to_baseline_edge_matches_independently_computed_means()
    test_compare_signal_to_baseline_handles_no_signals()
    print("All backtest tests passed.")
