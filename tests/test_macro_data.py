"""
Sanity tests for data/macro_data.py. Run with:
python tests/test_macro_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.macro_data import build_credit_spread_proxy, build_yield_curve_proxy


def _ohlcv(dates: pd.DatetimeIndex, closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1_000_000.0},
        index=dates,
    )


def test_credit_spread_proxy_rises_when_high_yield_underperforms():
    dates = pd.bdate_range("2026-01-01", periods=3)
    hy = _ohlcv(dates, [100.0, 95.0, 90.0])   # HYG falling (high-yield sold off)
    ig = _ohlcv(dates, [100.0, 100.0, 100.0])  # LQD flat
    proxy = build_credit_spread_proxy(hy, ig)
    assert list(proxy["close"]) == [1.0, 100.0 / 95.0, 100.0 / 90.0]
    assert proxy["close"].is_monotonic_increasing


def test_credit_spread_proxy_intersects_dates():
    dates_hy = pd.bdate_range("2026-01-01", periods=3)
    dates_ig = pd.bdate_range("2026-01-02", periods=3)  # one-day offset
    hy = _ohlcv(dates_hy, [100.0, 100.0, 100.0])
    ig = _ohlcv(dates_ig, [100.0, 100.0, 100.0])
    proxy = build_credit_spread_proxy(hy, ig)
    assert len(proxy) == 2  # only the overlapping dates


def test_yield_curve_proxy_is_short_minus_long():
    dates = pd.bdate_range("2026-01-01", periods=3)
    short = _ohlcv(dates, [5.0, 5.2, 5.5])
    long = _ohlcv(dates, [4.0, 4.0, 4.0])
    proxy = build_yield_curve_proxy(short, long)
    assert list(proxy["close"]) == [1.0, 1.2000000000000002, 1.5]


def test_yield_curve_proxy_rises_as_curve_inverts_further():
    dates = pd.bdate_range("2026-01-01", periods=3)
    short = _ohlcv(dates, [4.0, 4.5, 5.0])  # short rate rising toward/above long
    long = _ohlcv(dates, [5.0, 5.0, 5.0])
    proxy = build_yield_curve_proxy(short, long)
    assert proxy["close"].is_monotonic_increasing


def test_proxy_output_has_ohlcv_shape():
    dates = pd.bdate_range("2026-01-01", periods=2)
    hy = _ohlcv(dates, [100.0, 100.0])
    ig = _ohlcv(dates, [100.0, 100.0])
    proxy = build_credit_spread_proxy(hy, ig)
    assert list(proxy.columns) == ["open", "high", "low", "close", "volume"]
    assert (proxy["open"] == proxy["close"]).all()
    assert (proxy["volume"] == 0.0).all()


if __name__ == "__main__":
    test_credit_spread_proxy_rises_when_high_yield_underperforms()
    test_credit_spread_proxy_intersects_dates()
    test_yield_curve_proxy_is_short_minus_long()
    test_yield_curve_proxy_rises_as_curve_inverts_further()
    test_proxy_output_has_ohlcv_shape()
    print("All macro_data tests passed.")
