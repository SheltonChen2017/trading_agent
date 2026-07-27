"""
Sanity tests for baskets.py. Run with: python -m pytest tests/ -v
(or `python tests/test_baskets.py` for a quick manual check).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from baskets import (
    all_basket_names,
    basket_out_of_sample_significance,
    basket_significance,
    baskets_for_ticker,
    compare_baskets_to_baseline,
    compare_baskets_to_market_index,
    compute_high_volatility_basket,
    get_basket_tickers,
    out_of_sample_backtest_by_basket,
    out_of_sample_baseline_by_basket,
    out_of_sample_market_by_basket,
    summarize_by_basket,
)
from config import BASKETS


def _flat_series_with_shock(days: int, shock_index: int, shock_return: float, base_volatility: float = 0.003) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    returns = rng.normal(loc=0.0, scale=base_volatility, size=days)
    returns[shock_index] = shock_return
    close = 100 * np.cumprod(1 + returns)
    volume = np.full(days, 1_000_000.0)
    volume[shock_index] = 4_000_000.0
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": volume},
        index=dates,
    )


def _flat_series_with_two_shocks(
    days: int, early_index: int, late_index: int, shock_return: float, base_volatility: float = 0.002
) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    returns = rng.normal(loc=0.0, scale=base_volatility, size=days)
    volume = np.full(days, 1_000_000.0)
    for idx in (early_index, late_index):
        returns[idx] = shock_return
        volume[idx] = 4_000_000.0
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": volume},
        index=dates,
    )


def test_get_basket_tickers_returns_known_basket():
    tickers = get_basket_tickers("semiconductors")
    assert "NVDA" in tickers
    assert "AMD" in tickers


def test_get_basket_tickers_raises_on_unknown_basket():
    try:
        get_basket_tickers("not_a_real_basket")
        assert False, "expected KeyError"
    except KeyError as e:
        assert "Unknown basket" in str(e)


def test_baskets_for_ticker_reflects_deliberate_overlap():
    # TSLA is deliberately in both ai_related and consumer_discretionary.
    membership = baskets_for_ticker("TSLA")
    assert "ai_related" in membership
    assert "consumer_discretionary" in membership
    assert len(membership) >= 2


def test_baskets_for_ticker_empty_for_unknown_ticker():
    assert baskets_for_ticker("NOT_A_TICKER") == []


def test_all_basket_names_matches_config():
    assert set(all_basket_names()) == set(BASKETS)


def test_compute_high_volatility_basket_ranks_by_realized_std():
    quiet = _flat_series_with_shock(days=60, shock_index=30, shock_return=0.0, base_volatility=0.001)
    wild = _flat_series_with_shock(days=60, shock_index=30, shock_return=0.0, base_volatility=0.05)
    data = {"QUIET": quiet, "WILD": wild}

    top1 = compute_high_volatility_basket(data, top_n=1)
    assert top1 == ["WILD"]


def test_compute_high_volatility_basket_respects_top_n():
    data = {
        f"T{i}": _flat_series_with_shock(days=40, shock_index=20, shock_return=0.0, base_volatility=0.001 * (i + 1))
        for i in range(5)
    }
    basket = compute_high_volatility_basket(data, top_n=2)
    assert len(basket) == 2
    # The two highest base_volatility tickers (T4, T3) should be picked.
    assert set(basket) == {"T4", "T3"}


def test_summarize_by_basket_restricts_to_basket_tickers():
    dip_df = _flat_series_with_shock(days=60, shock_index=40, shock_return=-0.08)
    quiet_df = _flat_series_with_shock(days=60, shock_index=40, shock_return=0.0)
    # Fake basket config content via data dict keys matching real basket tickers
    # would require monkeypatching config.BASKETS; simpler to test with a
    # basket_names filter against data keyed by two real UNIVERSE tickers.
    data = {"NVDA": dip_df, "AMD": quiet_df}

    summary = summarize_by_basket(data, basket_names=["semiconductors"])
    assert not summary.empty
    assert (summary["basket"] == "semiconductors").all()
    assert summary.loc[summary["direction"] == "dip", "count"].iloc[0] == 1


def test_summarize_by_basket_skips_baskets_with_no_data_overlap():
    data = {"NVDA": _flat_series_with_shock(days=60, shock_index=40, shock_return=-0.08)}
    # "utilities" basket tickers (DUK, NEE) aren't present in `data` at all.
    summary = summarize_by_basket(data, basket_names=["utilities"])
    assert summary.empty


def test_compare_baskets_to_baseline_tags_basket_column():
    dip_df = _flat_series_with_shock(days=60, shock_index=40, shock_return=-0.08)
    data = {"NVDA": dip_df, "AMD": dip_df}

    comparison = compare_baskets_to_baseline(data, basket_names=["semiconductors"])
    assert not comparison.empty
    assert (comparison["basket"] == "semiconductors").all()
    assert "mean_edge_vs_own_ticker_pct" in comparison.columns


def test_compare_baskets_to_market_index_tags_basket_column():
    dip_df = _flat_series_with_shock(days=60, shock_index=40, shock_return=-0.08)
    data = {"NVDA": dip_df, "AMD": dip_df}
    benchmark_df = pd.DataFrame({"close": 100 * np.cumprod(np.full(60, 1.002))}, index=dip_df.index)

    comparison = compare_baskets_to_market_index(data, benchmark_df, basket_names=["semiconductors"])
    assert not comparison.empty
    assert (comparison["basket"] == "semiconductors").all()
    assert "mean_edge_vs_market_pct" in comparison.columns


def test_out_of_sample_backtest_by_basket_tags_basket_and_period():
    df = _flat_series_with_two_shocks(days=100, early_index=25, late_index=80, shock_return=-0.08)
    data = {"NVDA": df, "AMD": df}

    result = out_of_sample_backtest_by_basket(data, basket_names=["semiconductors"], discovery_frac=0.6)
    assert not result.empty
    assert (result["basket"] == "semiconductors").all()
    assert set(result["period"]) == {"discovery", "confirmation"}


def test_out_of_sample_baseline_by_basket_tags_basket_and_period():
    df = _flat_series_with_two_shocks(days=100, early_index=25, late_index=80, shock_return=-0.08)
    data = {"NVDA": df, "AMD": df}

    result = out_of_sample_baseline_by_basket(data, basket_names=["semiconductors"], discovery_frac=0.6)
    assert not result.empty
    assert (result["basket"] == "semiconductors").all()
    assert set(result["period"]) == {"discovery", "confirmation"}


def test_out_of_sample_market_by_basket_tags_basket_and_period():
    df = _flat_series_with_two_shocks(days=100, early_index=25, late_index=80, shock_return=-0.08)
    data = {"NVDA": df, "AMD": df}
    benchmark_df = pd.DataFrame({"close": 100 * np.cumprod(np.full(100, 1.001))}, index=df.index)

    result = out_of_sample_market_by_basket(data, benchmark_df, basket_names=["semiconductors"], discovery_frac=0.6)
    assert not result.empty
    assert (result["basket"] == "semiconductors").all()
    assert set(result["period"]) == {"discovery", "confirmation"}


def test_basket_significance_flags_clear_edge_as_significant():
    # Many small, consistent, deliberately-planted shocks with a strong,
    # low-noise forward bounce -> a clearly non-zero edge that should
    # survive even a Bonferroni-corrected threshold.
    days = 300
    rng = np.random.default_rng(1)
    returns = rng.normal(loc=0.0, scale=0.002, size=days)
    volume = np.full(days, 1_000_000.0)
    shock_indices = range(25, days - 10, 15)
    for idx in shock_indices:
        returns[idx] = -0.08
        volume[idx] = 4_000_000.0
        for i in range(1, 6):
            returns[idx + i] = 0.02  # strong, consistent bounce every time
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    df = pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": volume},
        index=dates,
    )
    data = {"NVDA": df, "AMD": df}

    result = basket_significance(data, basket_names=["semiconductors"])
    dip_row = result[result["direction"] == "dip"].iloc[0]
    assert dip_row["mean_edge_pct"] > 0
    assert dip_row["ci_low"] > 0
    assert bool(dip_row["significant"]) is True


def test_basket_significance_bonferroni_threshold_scales_with_basket_count():
    df = _flat_series_with_shock(days=60, shock_index=40, shock_return=-0.08)
    data = {"NVDA": df, "AMD": df}

    one_basket = basket_significance(data, basket_names=["semiconductors"])
    many_baskets = basket_significance(data, basket_names=["semiconductors", "ai_related", "unstable"])

    # More simultaneously-tested baskets -> a stricter (smaller) threshold.
    assert many_baskets["bonferroni_threshold"].iloc[0] < one_basket["bonferroni_threshold"].iloc[0]


def test_basket_out_of_sample_significance_tags_basket_and_period():
    df = _flat_series_with_two_shocks(days=100, early_index=25, late_index=80, shock_return=-0.08)
    data = {"NVDA": df, "AMD": df}

    result = basket_out_of_sample_significance(data, basket_names=["semiconductors"], discovery_frac=0.6)
    assert not result.empty
    assert (result["basket"] == "semiconductors").all()
    assert set(result["period"]) <= {"discovery", "confirmation"}
    assert "significant" in result.columns


if __name__ == "__main__":
    test_get_basket_tickers_returns_known_basket()
    test_get_basket_tickers_raises_on_unknown_basket()
    test_baskets_for_ticker_reflects_deliberate_overlap()
    test_baskets_for_ticker_empty_for_unknown_ticker()
    test_all_basket_names_matches_config()
    test_compute_high_volatility_basket_ranks_by_realized_std()
    test_compute_high_volatility_basket_respects_top_n()
    test_summarize_by_basket_restricts_to_basket_tickers()
    test_summarize_by_basket_skips_baskets_with_no_data_overlap()
    test_compare_baskets_to_baseline_tags_basket_column()
    test_compare_baskets_to_market_index_tags_basket_column()
    test_out_of_sample_backtest_by_basket_tags_basket_and_period()
    test_out_of_sample_baseline_by_basket_tags_basket_and_period()
    test_out_of_sample_market_by_basket_tags_basket_and_period()
    test_basket_significance_flags_clear_edge_as_significant()
    test_basket_significance_bonferroni_threshold_scales_with_basket_count()
    test_basket_out_of_sample_significance_tags_basket_and_period()
    print("All basket tests passed.")
