"""Tests for ml/features.py -- point-in-time correctness (no feature may
change if future rows are appended), structural rejects (bad index,
missing columns), and documented handling of degenerate price/volume."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.features import FeatureError, compute_point_in_time_features


def _session_index(n: int, start: str = "2020-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _ohlcv(n: int, *, base: float = 100.0, daily_pct: float = 0.1, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = _session_index(n)
    close = base * (1 + daily_pct / 100) ** np.arange(n) + rng.normal(0, 0.1, n)
    close = np.abs(close) + 1.0
    open_ = close * (1 + rng.normal(0, 0.001, n))
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


def _benchmarks(n: int, seed: int = 1) -> dict[str, pd.Series]:
    rng = np.random.default_rng(seed)
    index = _session_index(n)
    out = {}
    for name, s in (("QQQ", 2), ("SOXX", 3), ("SPY", 4)):
        vals = 100.0 * (1 + rng.normal(0.0005, 0.01, n)).cumprod()
        out[name] = pd.Series(vals, index=index)
    return out


def test_basic_shape_has_one_row_per_session_and_key_columns():
    n = 260
    price = _ohlcv(n)
    benchmarks = _benchmarks(n)

    result = compute_point_in_time_features("AAA", price, benchmarks=benchmarks)

    assert len(result) == n
    assert list(result["as_of_session"]) == [str(ts.date()) for ts in price.index]
    assert (result["ticker"] == "AAA").all()
    for column in (
        "return_1d_pct",
        "return_252d_pct",
        "residual_return_qqq_20d_pct",
        "residual_return_soxx_20d_pct",
        "distance_from_sma_200d_pct",
        "realized_vol_20d_pct",
        "downside_semivol_20d_pct",
        "max_drawdown_252d_pct",
        "avg_dollar_volume_20d",
        "volume_ratio_20d",
        "beta_spy_60d",
        "correlation_qqq_60d",
        "overnight_gap_mean_20d_pct",
        "market_trend",
        "market_trailing_volatility_pct",
        "day_of_week",
        "sessions_since_last_earnings",
    ):
        assert column in result.columns, column


def test_early_rows_have_nan_for_long_lookback_features():
    n = 260
    price = _ohlcv(n)
    benchmarks = _benchmarks(n)
    result = compute_point_in_time_features("AAA", price, benchmarks=benchmarks)

    assert pd.isna(result["return_252d_pct"].iloc[0])
    assert pd.isna(result["realized_vol_60d_pct"].iloc[0])
    assert not pd.isna(result["return_1d_pct"].iloc[-1])


def test_point_in_time_correctness_prefix_is_unaffected_by_appending_future_rows():
    n = 260
    price_full = _ohlcv(n + 30)
    price_prefix = price_full.iloc[:n]
    benchmarks_full = {
        name: series for name, series in _benchmarks(n + 30).items()
    }
    benchmarks_prefix = {name: series.iloc[:n] for name, series in benchmarks_full.items()}

    result_prefix = compute_point_in_time_features(
        "AAA", price_prefix, benchmarks=benchmarks_prefix
    )
    result_full = compute_point_in_time_features(
        "AAA", price_full, benchmarks=benchmarks_full
    )

    numeric_columns = [
        c for c in result_prefix.columns if c not in ("ticker", "as_of_session", "market_trend")
    ]
    prefix_values = result_prefix[numeric_columns].to_numpy(dtype=float)
    full_prefix_values = result_full[numeric_columns].iloc[:n].to_numpy(dtype=float)
    np.testing.assert_allclose(prefix_values, full_prefix_values, equal_nan=True)


def test_zero_and_negative_close_treated_as_missing_not_zero_return():
    n = 30
    price = _ohlcv(n)
    price = price.copy()
    price.iloc[10, price.columns.get_loc("close")] = 0.0
    price.iloc[15, price.columns.get_loc("close")] = -5.0
    benchmarks = _benchmarks(n)

    result = compute_point_in_time_features("AAA", price, benchmarks=benchmarks)

    # a bad close feeds NaN forward through return_1d_pct at the bad row and
    # the row immediately after it (pct_change needs both endpoints)
    assert pd.isna(result["return_1d_pct"].iloc[10])
    assert pd.isna(result["return_1d_pct"].iloc[11])
    assert pd.isna(result["return_1d_pct"].iloc[15])


def test_negative_volume_treated_as_missing():
    n = 30
    price = _ohlcv(n)
    price = price.copy()
    price.iloc[10, price.columns.get_loc("volume")] = -100.0
    benchmarks = _benchmarks(n)

    result = compute_point_in_time_features("AAA", price, benchmarks=benchmarks)
    assert pd.isna(result["avg_dollar_volume_20d"].iloc[10:29]).any()


def test_rejects_unsorted_index():
    n = 30
    price = _ohlcv(n).iloc[::-1]
    benchmarks = _benchmarks(n)
    with pytest.raises(FeatureError, match="not sorted"):
        compute_point_in_time_features("AAA", price, benchmarks=benchmarks)


def test_rejects_duplicate_index():
    n = 30
    price = _ohlcv(n)
    price = pd.concat([price, price.iloc[-1:]])
    benchmarks = _benchmarks(n)
    with pytest.raises(FeatureError, match="duplicate"):
        compute_point_in_time_features("AAA", price, benchmarks=benchmarks)


def test_rejects_missing_columns():
    n = 30
    price = _ohlcv(n).drop(columns=["volume"])
    benchmarks = _benchmarks(n)
    with pytest.raises(FeatureError, match="missing required columns"):
        compute_point_in_time_features("AAA", price, benchmarks=benchmarks)


def test_rejects_empty_price():
    price = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    with pytest.raises(FeatureError, match="empty"):
        compute_point_in_time_features("AAA", price, benchmarks={"QQQ": pd.Series(dtype=float)})


def test_rejects_missing_market_benchmark():
    n = 30
    price = _ohlcv(n)
    with pytest.raises(FeatureError, match="market_benchmark"):
        compute_point_in_time_features(
            "AAA", price, benchmarks={"SOXX": _benchmarks(n)["SOXX"]}, market_benchmark="QQQ"
        )


def test_sessions_since_last_earnings_never_negative_and_zero_on_announcement_day():
    n = 30
    price = _ohlcv(n)
    benchmarks = _benchmarks(n)
    earnings_date = str(price.index[10].date())

    result = compute_point_in_time_features(
        "AAA", price, benchmarks=benchmarks, earnings_dates=[earnings_date]
    )

    assert pd.isna(result["sessions_since_last_earnings"].iloc[:10]).all()
    assert result["sessions_since_last_earnings"].iloc[10] == 0
    assert result["sessions_since_last_earnings"].iloc[15] == 5
    assert (result["sessions_since_last_earnings"].dropna() >= 0).all()


def test_context_series_is_forward_filled_never_backward():
    n = 30
    price = _ohlcv(n)
    benchmarks = _benchmarks(n)
    sparse_index = price.index[2::5]  # first coverage starts at position 2, not 0
    context = {
        "vix": pd.Series([20.0 + 5.0 * i for i in range(len(sparse_index))], index=sparse_index)
    }

    result = compute_point_in_time_features(
        "AAA", price, benchmarks=benchmarks, context_series=context
    )

    assert pd.isna(result["context_vix_level"].iloc[:2]).all()  # before first known value
    assert result["context_vix_level"].iloc[2] == 20.0
    assert result["context_vix_level"].iloc[6] == 20.0  # still ffilled from position 2
    assert result["context_vix_level"].iloc[7] == 25.0  # ffilled from position 7


def test_day_of_week_matches_calendar_weekday():
    n = 10
    price = _ohlcv(n)
    benchmarks = _benchmarks(n)
    result = compute_point_in_time_features("AAA", price, benchmarks=benchmarks)
    for i, ts in enumerate(price.index):
        assert result["day_of_week"].iloc[i] == ts.dayofweek
