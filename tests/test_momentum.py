"""
Sanity tests for signals/momentum.py. Run with: python -m pytest tests/ -v
(or `python tests/test_momentum.py` for a quick manual check).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.momentum import scan_momentum


def _constant_drift_series(days: int, daily_return: float) -> pd.DataFrame:
    close = 100 * np.cumprod(np.full(days, 1 + daily_return))
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )


def _universe_with_distinct_momentum(days: int = 200) -> dict[str, pd.DataFrame]:
    # Six tickers with clearly distinct, deterministic trailing drift so
    # the ranking (top/bottom) is unambiguous and exactly predictable.
    drifts = {"WINNER1": 0.006, "WINNER2": 0.004, "MID1": 0.001, "MID2": -0.001, "LOSER1": -0.004, "LOSER2": -0.006}
    return {ticker: _constant_drift_series(days, drift) for ticker, drift in drifts.items()}


def test_scan_momentum_flags_top_and_bottom_performers():
    data = _universe_with_distinct_momentum()
    result = scan_momentum(data, top_pct=1 / 6, bottom_pct=1 / 6, lookback_days=100, skip_days=10)

    assert not result.empty
    up_tickers = set(result.loc[result["direction"] == "up", "ticker"])
    dip_tickers = set(result.loc[result["direction"] == "dip", "ticker"])
    assert up_tickers == {"WINNER1"}
    assert dip_tickers == {"LOSER2"}


def test_scan_momentum_returns_empty_with_insufficient_history():
    data = _universe_with_distinct_momentum(days=50)  # shorter than default lookback+skip
    result = scan_momentum(data)  # default lookback_days=126, skip_days=21 -> needs 147+ days
    assert result.empty


def test_scan_momentum_returns_empty_with_too_few_tickers():
    data = {"ONLY_ONE": _constant_drift_series(200, 0.002)}
    result = scan_momentum(data, lookback_days=100, skip_days=10)
    assert result.empty  # fewer than 5 tickers -- not enough for a meaningful cross-sectional rank


def test_scan_momentum_volume_zscore_is_nan():
    data = _universe_with_distinct_momentum()
    result = scan_momentum(data, top_pct=1 / 6, bottom_pct=1 / 6, lookback_days=100, skip_days=10)
    assert result["volume_zscore"].isna().all()


def test_scan_momentum_as_of_matches_requested_date():
    data = _universe_with_distinct_momentum()
    as_of = list(data.values())[0].index[150]
    result = scan_momentum(data, as_of=as_of, top_pct=1 / 6, bottom_pct=1 / 6, lookback_days=100, skip_days=10)
    assert not result.empty
    assert (result["date"] == as_of).all()


if __name__ == "__main__":
    test_scan_momentum_flags_top_and_bottom_performers()
    test_scan_momentum_returns_empty_with_insufficient_history()
    test_scan_momentum_returns_empty_with_too_few_tickers()
    test_scan_momentum_volume_zscore_is_nan()
    test_scan_momentum_as_of_matches_requested_date()
    print("All momentum tests passed.")
