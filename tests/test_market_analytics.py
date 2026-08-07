"""
Sanity tests for market_analytics.py. Run with:
python tests/test_market_analytics.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from market_analytics import classify_trend


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


if __name__ == "__main__":
    test_classify_trend_none_without_enough_history()
    test_classify_trend_uptrend_when_above_sma()
    test_classify_trend_downtrend_when_below_sma()
    print("All market_analytics tests passed.")
