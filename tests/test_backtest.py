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
    bonferroni_threshold,
    bootstrap_edge_significance,
    compare_signal_to_baseline,
    compare_signal_to_baseline_per_ticker,
    compare_signal_to_market_index,
    compute_benchmark_forward_returns,
    out_of_sample_backtest,
    out_of_sample_baseline_comparison,
    out_of_sample_market_comparison,
    out_of_sample_significance,
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


def test_compare_signal_to_baseline_per_ticker_isolates_own_stock_not_pooled():
    hold_days = 5
    # A: quiet noise (own-baseline drift ~0%) + one dip shock that bounces back.
    df_a = _series_with_shock_and_known_forward_move(
        days=60, shock_index=40, shock_return=-0.08, forward_daily_return=0.01, hold_days=hold_days
    )
    # B: a separate stock with strong drift and negligible noise, so it never
    # fires a signal itself but pulls the POOLED baseline up a lot if included.
    days_b = 60
    rng_b = np.random.default_rng(9)
    returns_b = rng_b.normal(loc=0.01, scale=0.0005, size=days_b)
    close_b = 100 * np.cumprod(1 + returns_b)
    dates_b = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days_b + 5)[-days_b:]
    df_b = pd.DataFrame(
        {"open": close_b, "high": close_b, "low": close_b, "close": close_b, "volume": np.full(days_b, 1_000_000.0)},
        index=dates_b,
    )
    data = {"A": df_a, "B": df_b}

    per_ticker = compare_signal_to_baseline_per_ticker(data, hold_days_options=[hold_days], slippage_pct=0.0)
    pooled = compare_signal_to_baseline(data, hold_days_options=[hold_days], slippage_pct=0.0)
    a_only_baseline = run_baseline_forward_returns({"A": df_a}, hold_days=hold_days, slippage_pct=0.0)

    dip_row = per_ticker[(per_ticker["hold_days"] == hold_days) & (per_ticker["direction"] == "dip")].iloc[0]
    pooled_dip_row = pooled[(pooled["hold_days"] == hold_days) & (pooled["direction"] == "dip")].iloc[0]

    assert dip_row["signal_count"] == 1
    # Per-ticker baseline should match A's OWN any-day baseline almost exactly...
    assert abs(dip_row["mean_own_ticker_baseline_pct"] - a_only_baseline["net_return_pct"].mean()) < 0.01
    # ...and should clearly differ from the pooled baseline, which B's much higher drift dilutes.
    assert abs(dip_row["mean_own_ticker_baseline_pct"] - pooled_dip_row["baseline_mean_return_pct"]) > 1.0


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


def test_compare_signal_to_baseline_per_ticker_handles_no_signals():
    hold_days = 5
    rng = np.random.default_rng(2)
    days = 40
    close = 100 * np.cumprod(1 + rng.normal(0, 0.001, size=days))  # quiet, nothing to flag
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    df = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )
    comparison = compare_signal_to_baseline_per_ticker({"TEST": df}, hold_days_options=[hold_days])
    assert (comparison["signal_count"] == 0).all()
    assert comparison["signal_mean_return_pct"].isna().all()
    assert comparison["mean_edge_vs_own_ticker_pct"].isna().all()


def test_compute_benchmark_forward_returns_matches_hand_computed_value():
    days = 30
    hold_days = 5
    returns = np.full(days, 0.004)
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    benchmark_df = pd.DataFrame({"close": close}, index=dates)

    forward = compute_benchmark_forward_returns(benchmark_df, hold_days=hold_days, slippage_pct=0.0)
    expected = (1.004**hold_days - 1) * 100

    assert not forward.empty
    assert forward.round(2).unique().tolist() == [round(expected, 2)]


def test_compare_signal_to_market_index_edge_matches_hand_computed_difference():
    hold_days = 5
    days = 60
    df = _series_with_shock_and_known_forward_move(
        days=days, shock_index=40, shock_return=-0.08, forward_daily_return=0.01, hold_days=hold_days
    )
    data = {"TEST": df}

    # Benchmark shares df's exact date index with a known, constant daily return.
    benchmark_daily_return = 0.002
    benchmark_close = 100 * np.cumprod(np.full(days, 1 + benchmark_daily_return))
    benchmark_df = pd.DataFrame({"close": benchmark_close}, index=df.index)

    comparison = compare_signal_to_market_index(data, benchmark_df, hold_days_options=[hold_days], slippage_pct=0.0)
    dip_row = comparison[(comparison["hold_days"] == hold_days) & (comparison["direction"] == "dip")].iloc[0]

    expected_market_return = round(((1 + benchmark_daily_return) ** hold_days - 1) * 100, 3)
    assert dip_row["signal_count"] == 1
    assert abs(dip_row["mean_market_return_pct"] - expected_market_return) < 0.01
    assert dip_row["mean_edge_vs_market_pct"] == round(
        dip_row["signal_mean_return_pct"] - dip_row["mean_market_return_pct"], 3
    )


def test_compare_signal_to_market_index_drops_signals_outside_benchmark_history():
    hold_days = 5
    days = 60
    df = _series_with_shock_and_known_forward_move(
        days=days, shock_index=40, shock_return=-0.08, forward_daily_return=0.01, hold_days=hold_days
    )
    data = {"TEST": df}
    # Benchmark covers a completely different, non-overlapping date range.
    other_dates = pd.bdate_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(days=365), periods=days)
    benchmark_df = pd.DataFrame({"close": np.full(days, 100.0)}, index=other_dates)

    comparison = compare_signal_to_market_index(data, benchmark_df, hold_days_options=[hold_days])
    dip_row = comparison[(comparison["hold_days"] == hold_days) & (comparison["direction"] == "dip")].iloc[0]
    assert dip_row["signal_count"] == 0
    assert dip_row["signal_mean_return_pct"] is None


def _series_with_two_shocks(
    days: int, early_index: int, late_index: int, shock_return: float, forward_daily_return: float, hold_days: int
) -> pd.DataFrame:
    """Quiet series with two deliberate shocks (each followed by a known
    drift) at different points in time, for testing date-based splitting."""
    rng = np.random.default_rng(0)
    returns = rng.normal(loc=0.0, scale=0.002, size=days)
    volume = np.full(days, 1_000_000.0)
    for idx in (early_index, late_index):
        returns[idx] = shock_return
        volume[idx] = 4_000_000.0
        for i in range(1, hold_days + 1):
            if idx + i < days:
                returns[idx + i] = forward_daily_return

    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": volume},
        index=dates,
    )


def test_out_of_sample_backtest_splits_signals_by_period():
    hold_days = 5
    days = 100
    # Early shock at day 20 should land in "discovery"; late shock at day
    # 80 should land in "confirmation" under a 0.6 discovery_frac split.
    df = _series_with_two_shocks(
        days=days, early_index=20, late_index=80, shock_return=-0.08, forward_daily_return=0.01, hold_days=hold_days
    )
    result = out_of_sample_backtest({"TEST": df}, discovery_frac=0.6, hold_days=hold_days, slippage_pct=0.0)

    assert set(result["period"]) == {"discovery", "confirmation"}
    discovery_count = result.loc[result["period"] == "discovery", "count"].sum()
    confirmation_count = result.loc[result["period"] == "confirmation", "count"].sum()
    assert discovery_count == 1
    assert confirmation_count == 1


def test_out_of_sample_backtest_handles_no_signals():
    days = 60
    rng = np.random.default_rng(3)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.001, size=days))
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    df = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )
    result = out_of_sample_backtest({"TEST": df})
    assert result.empty


def test_out_of_sample_baseline_comparison_splits_signals_by_period():
    hold_days = 5
    days = 100
    df = _series_with_two_shocks(
        days=days, early_index=20, late_index=80, shock_return=-0.08, forward_daily_return=0.01, hold_days=hold_days
    )
    result = out_of_sample_baseline_comparison(
        {"TEST": df}, discovery_frac=0.6, hold_days=hold_days, slippage_pct=0.0
    )

    assert set(result["period"]) == {"discovery", "confirmation"}
    assert result.loc[result["period"] == "discovery", "signal_count"].sum() == 1
    assert result.loc[result["period"] == "confirmation", "signal_count"].sum() == 1


def test_out_of_sample_baseline_comparison_handles_no_signals():
    days = 60
    rng = np.random.default_rng(3)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.001, size=days))
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    df = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )
    result = out_of_sample_baseline_comparison({"TEST": df})
    assert result.empty


def test_out_of_sample_market_comparison_splits_signals_by_period():
    hold_days = 5
    days = 100
    df = _series_with_two_shocks(
        days=days, early_index=20, late_index=80, shock_return=-0.08, forward_daily_return=0.01, hold_days=hold_days
    )
    benchmark_df = pd.DataFrame({"close": 100 * np.cumprod(np.full(days, 1.001))}, index=df.index)

    result = out_of_sample_market_comparison(
        {"TEST": df}, benchmark_df, discovery_frac=0.6, hold_days=hold_days, slippage_pct=0.0
    )

    assert set(result["period"]) == {"discovery", "confirmation"}
    assert result.loc[result["period"] == "discovery", "signal_count"].sum() == 1
    assert result.loc[result["period"] == "confirmation", "signal_count"].sum() == 1


def test_out_of_sample_market_comparison_handles_no_signals():
    days = 60
    rng = np.random.default_rng(3)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.001, size=days))
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    df = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )
    benchmark_df = pd.DataFrame({"close": 100 * np.cumprod(np.full(days, 1.001))}, index=df.index)
    result = out_of_sample_market_comparison({"TEST": df}, benchmark_df)
    assert result.empty


def test_bootstrap_edge_significance_detects_clear_positive_edge():
    rng = np.random.default_rng(42)
    values = pd.Series(rng.normal(loc=2.0, scale=0.5, size=50))
    result = bootstrap_edge_significance(values, n_bootstrap=1000, seed=0)

    assert result["n"] == 50
    assert result["mean"] > 1.5
    assert result["ci_low"] > 0, "a clearly positive edge should have a CI that excludes zero"
    assert result["p_value"] < 0.05


def test_bootstrap_edge_significance_does_not_flag_pure_noise():
    rng = np.random.default_rng(42)
    values = pd.Series(rng.normal(loc=0.0, scale=1.0, size=50))
    result = bootstrap_edge_significance(values, n_bootstrap=1000, seed=0)

    assert result["p_value"] > 0.1, "a zero-mean noise sample shouldn't look statistically significant"


def test_bootstrap_edge_significance_handles_tiny_sample():
    result = bootstrap_edge_significance(pd.Series([1.0, 2.0, 3.0]))
    assert result["n"] == 3
    assert result["mean"] is None
    assert result["p_value"] is None


def test_bonferroni_threshold_scales_with_test_count():
    assert bonferroni_threshold(10, alpha=0.05) == 0.005
    assert bonferroni_threshold(1, alpha=0.05) == 0.05
    assert bonferroni_threshold(0, alpha=0.05) == 0.05


def _flag_every_day_as_up(data, as_of=None, **_ignored):
    """A trivial custom scan function (matching scan_dips_and_ups's output
    contract) used only to prove run_backtest()'s scan_fn plumbing
    actually invokes what it's given, instead of always calling the
    default scanner regardless of what's passed."""
    rows = []
    for ticker, df in data.items():
        row = df.loc[as_of] if as_of is not None else df.iloc[-1]
        rows.append(
            {
                "ticker": ticker,
                "date": row.name,
                "close": row["close"],
                "return_pct": 0.0,
                "return_zscore": 9.0,
                "volume_zscore": 9.0,
                "direction": "up",
            }
        )
    return pd.DataFrame(rows)


def test_run_backtest_uses_custom_scan_fn():
    days = 40
    rng = np.random.default_rng(5)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.001, size=days))  # quiet -- default scanner would flag nothing
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    df = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )
    data = {"TEST": df}

    default_results = run_backtest(data, hold_days=1, slippage_pct=0.0)
    assert default_results.empty, "the default scanner shouldn't flag anything on this quiet series"

    custom_results = run_backtest(data, hold_days=1, slippage_pct=0.0, scan_fn=_flag_every_day_as_up, scan_kwargs={})
    assert not custom_results.empty, "the custom scan_fn should have flagged every usable day"
    assert (custom_results["direction"] == "up").all()


def test_out_of_sample_significance_flags_discovery_only_effect_correctly():
    # Reproduces the exact real-world trap this function exists to catch:
    # a strong, consistent effect concentrated in the discovery period,
    # and pure noise (no consistent effect) in the confirmation period.
    # Pooling the two would look "significant"; splitting them correctly
    # should show discovery significant and confirmation NOT significant.
    days = 300
    rng = np.random.default_rng(2)
    returns = rng.normal(loc=0.0, scale=0.002, size=days)
    volume = np.full(days, 1_000_000.0)

    # Discovery-period shocks (well within the first 60% of 300 days):
    # strong, consistent, low-noise bounce every time.
    for idx in range(30, 150, 15):
        returns[idx] = -0.08
        volume[idx] = 4_000_000.0
        for i in range(1, 6):
            returns[idx + i] = 0.02

    # Confirmation-period shocks (within the last 40%): bounce direction
    # is random noise, no consistent effect.
    rng2 = np.random.default_rng(99)
    for idx in range(200, 280, 15):
        returns[idx] = -0.08
        volume[idx] = 4_000_000.0
        for i in range(1, 6):
            returns[idx + i] = rng2.normal(0, 0.03)

    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    df = pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": volume},
        index=dates,
    )
    data = {"A": df, "B": df}

    result = out_of_sample_significance(data, discovery_frac=0.6, hold_days=5, slippage_pct=0.0, n_tests=2)

    dip_discovery = result[(result["period"] == "discovery") & (result["direction"] == "dip")].iloc[0]
    dip_confirmation = result[(result["period"] == "confirmation") & (result["direction"] == "dip")].iloc[0]

    assert dip_discovery["mean_edge_pct"] > 0
    assert bool(dip_discovery["significant"]) is True
    assert bool(dip_confirmation["significant"]) is False


def test_out_of_sample_significance_handles_no_signals():
    days = 60
    rng = np.random.default_rng(3)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.001, size=days))
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    df = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )
    result = out_of_sample_significance({"TEST": df})
    assert result.empty


def test_out_of_sample_significance_n_tests_changes_threshold():
    hold_days = 5
    df = _series_with_shock_and_known_forward_move(
        days=60, shock_index=40, shock_return=-0.08, forward_daily_return=0.01, hold_days=hold_days
    )
    data = {"TEST": df}
    loose = out_of_sample_significance(data, hold_days=hold_days, slippage_pct=0.0, n_tests=1)
    strict = out_of_sample_significance(data, hold_days=hold_days, slippage_pct=0.0, n_tests=100)

    assert loose.iloc[0]["bonferroni_threshold"] > strict.iloc[0]["bonferroni_threshold"]


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
    test_compare_signal_to_baseline_per_ticker_isolates_own_stock_not_pooled()
    test_compare_signal_to_baseline_per_ticker_handles_no_signals()
    test_compute_benchmark_forward_returns_matches_hand_computed_value()
    test_compare_signal_to_market_index_edge_matches_hand_computed_difference()
    test_compare_signal_to_market_index_drops_signals_outside_benchmark_history()
    test_out_of_sample_backtest_splits_signals_by_period()
    test_out_of_sample_backtest_handles_no_signals()
    test_out_of_sample_baseline_comparison_splits_signals_by_period()
    test_out_of_sample_baseline_comparison_handles_no_signals()
    test_out_of_sample_market_comparison_splits_signals_by_period()
    test_out_of_sample_market_comparison_handles_no_signals()
    test_bootstrap_edge_significance_detects_clear_positive_edge()
    test_bootstrap_edge_significance_does_not_flag_pure_noise()
    test_bootstrap_edge_significance_handles_tiny_sample()
    test_bonferroni_threshold_scales_with_test_count()
    test_run_backtest_uses_custom_scan_fn()
    test_out_of_sample_significance_flags_discovery_only_effect_correctly()
    test_out_of_sample_significance_handles_no_signals()
    test_out_of_sample_significance_n_tests_changes_threshold()
    print("All backtest tests passed.")
