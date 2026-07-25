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
    baskets_for_ticker,
    compare_baskets_to_baseline,
    compare_baskets_to_market_index,
    compute_high_volatility_basket,
    get_basket_tickers,
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
    print("All basket tests passed.")
