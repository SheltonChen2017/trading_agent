"""
Sanity tests for signals/overnight_gap.py. Run with:
python -m pytest tests/ -v (or `python tests/test_overnight_gap.py` for a
quick manual check).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.overnight_gap import compute_gap_features, scan_overnight_gap_reversal

WINDOW = 20


def _series_with_gap(days: int, gap_index: int, gap_pct: float, seed: int = 0) -> pd.DataFrame:
    """Quiet series (tiny, stable overnight gaps) with one deliberate,
    large gap on `gap_index`."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    close = np.full(days, 100.0)
    open_ = np.full(days, 100.0)
    for i in range(1, days):
        # Tiny, quiet overnight gaps every day except the injected one.
        prior_close = close[i - 1]
        open_[i] = prior_close * (1 + rng.normal(0, 0.0005))
        close[i] = open_[i] * (1 + rng.normal(0, 0.003))  # small intraday noise
    if gap_index > 0:
        open_[gap_index] = close[gap_index - 1] * (1 + gap_pct)
        close[gap_index] = open_[gap_index] * (1 + rng.normal(0, 0.003))
    return pd.DataFrame(
        {"open": open_, "high": np.maximum(open_, close), "low": np.minimum(open_, close), "close": close,
         "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )


def test_compute_gap_features_excludes_current_row_from_its_own_baseline():
    df = _series_with_gap(days=60, gap_index=59, gap_pct=-0.06)
    features = compute_gap_features(df, window=WINDOW)
    as_of = df.index[59]

    excluding_shock = features["gap_pct"].iloc[59 - WINDOW : 59]
    expected_z = (features.loc[as_of, "gap_pct"] - excluding_shock.mean()) / excluding_shock.std()
    assert abs(features.loc[as_of, "gap_zscore"] - expected_z) < 1e-9


def test_scan_overnight_gap_reversal_flags_gap_down_as_dip():
    df = _series_with_gap(days=60, gap_index=59, gap_pct=-0.06)
    as_of = df.index[59]
    result = scan_overnight_gap_reversal({"A": df}, as_of=as_of, window=WINDOW)
    assert not result.empty
    assert result.iloc[0]["direction"] == "dip"


def test_scan_overnight_gap_reversal_flags_gap_up_as_up():
    df = _series_with_gap(days=60, gap_index=59, gap_pct=0.06)
    as_of = df.index[59]
    result = scan_overnight_gap_reversal({"A": df}, as_of=as_of, window=WINDOW)
    assert not result.empty
    assert result.iloc[0]["direction"] == "up"


def test_scan_overnight_gap_reversal_ignores_quiet_days():
    df = _series_with_gap(days=60, gap_index=59, gap_pct=0.0001)  # negligible gap
    as_of = df.index[59]
    result = scan_overnight_gap_reversal({"A": df}, as_of=as_of, window=WINDOW)
    assert result.empty


def test_scan_overnight_gap_reversal_excludes_earnings_adjacent_dates():
    df = _series_with_gap(days=60, gap_index=59, gap_pct=-0.06)
    as_of = df.index[59]
    earnings_dates = {"A": {as_of}}
    result = scan_overnight_gap_reversal({"A": df}, as_of=as_of, window=WINDOW, earnings_dates=earnings_dates)
    assert result.empty


def test_scan_overnight_gap_reversal_earnings_exclusion_is_ticker_specific():
    df = _series_with_gap(days=60, gap_index=59, gap_pct=-0.06)
    as_of = df.index[59]
    earnings_dates = {"OTHER_TICKER": {as_of}}  # unrelated ticker -- should NOT exclude "A"
    result = scan_overnight_gap_reversal({"A": df}, as_of=as_of, window=WINDOW, earnings_dates=earnings_dates)
    assert not result.empty


def test_scan_overnight_gap_reversal_returns_empty_with_insufficient_history():
    df = _series_with_gap(days=10, gap_index=9, gap_pct=-0.06)
    as_of = df.index[-1]
    result = scan_overnight_gap_reversal({"A": df}, as_of=as_of, window=WINDOW)
    assert result.empty


if __name__ == "__main__":
    test_compute_gap_features_excludes_current_row_from_its_own_baseline()
    test_scan_overnight_gap_reversal_flags_gap_down_as_dip()
    test_scan_overnight_gap_reversal_flags_gap_up_as_up()
    test_scan_overnight_gap_reversal_ignores_quiet_days()
    test_scan_overnight_gap_reversal_excludes_earnings_adjacent_dates()
    test_scan_overnight_gap_reversal_earnings_exclusion_is_ticker_specific()
    test_scan_overnight_gap_reversal_returns_empty_with_insufficient_history()
    print("All overnight_gap tests passed.")
