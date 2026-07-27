"""
Sanity tests for the scanner. Run with: python -m pytest tests/ -v
(or just `python tests/test_scanner.py` for a quick manual check).

These use hand-built synthetic data with a KNOWN injected shock, so we can
assert the scanner finds exactly what we planted — not just "runs without
crashing".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.scanner import compute_features, scan_dips_and_ups


def _flat_series_with_shock(days: int, shock_index: int, shock_return: float) -> pd.DataFrame:
    """Build a low-volatility price series with one deliberate outlier day."""
    rng = np.random.default_rng(0)
    returns = rng.normal(loc=0.0, scale=0.003, size=days)  # tight, boring noise
    returns[shock_index] = shock_return

    close = 100 * np.cumprod(1 + returns)
    volume = np.full(days, 1_000_000.0)
    volume[shock_index] = 4_000_000.0  # volume spike confirms the move

    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    return pd.DataFrame(
        {
            "open": close, "high": close * 1.001, "low": close * 0.999,
            "close": close, "volume": volume,
        },
        index=dates,
    )


def test_flags_injected_dip():
    days = 60
    df = _flat_series_with_shock(days, shock_index=days - 1, shock_return=-0.08)
    result = scan_dips_and_ups({"TEST_DIP": df})

    assert not result.empty, "expected the scanner to flag the injected -8% shock day"
    assert result.iloc[0]["ticker"] == "TEST_DIP"
    assert result.iloc[0]["direction"] == "dip"


def test_flags_injected_up():
    days = 60
    df = _flat_series_with_shock(days, shock_index=days - 1, shock_return=0.09)
    result = scan_dips_and_ups({"TEST_UP": df})

    assert not result.empty, "expected the scanner to flag the injected +9% shock day"
    assert result.iloc[0]["direction"] == "up"


def test_ignores_normal_noise():
    days = 60
    rng = np.random.default_rng(1)
    returns = rng.normal(loc=0.0, scale=0.005, size=days)  # no shock at all
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]

    df = pd.DataFrame(
        {
            "open": close, "high": close * 1.001, "low": close * 0.999,
            "close": close, "volume": np.full(days, 1_000_000.0),
        },
        index=dates,
    )
    result = scan_dips_and_ups({"TEST_QUIET": df})
    assert result.empty, "a quiet, noise-only series should not trigger any signal"


def test_handles_ticker_with_shorter_history_than_as_of_date():
    # Mixing a long-history ticker with a "recent IPO" ticker whose index
    # doesn't cover an earlier as_of date shouldn't crash — the short
    # ticker should just be skipped for dates before it existed.
    days = 60
    long_df = _flat_series_with_shock(days, shock_index=days - 1, shock_return=-0.08)
    short_df = long_df.iloc[-10:].copy()
    as_of = long_df.index[30]  # predates short_df's entire history

    result = scan_dips_and_ups({"LONG": long_df, "SHORT": short_df}, as_of=as_of)
    assert isinstance(result, pd.DataFrame)
    if not result.empty:
        assert "SHORT" not in result["ticker"].values


def test_compute_features_diff_mode_handles_a_zero_crossing_correctly():
    # Regression test (Codex review, 2026-07-27): pct_change() is
    # undefined/sign-reversing across a zero crossing -- e.g. -0.1 -> 0.1
    # computes as -200%, which reads as a huge COLLAPSE even though the
    # series only just crossed zero from below. return_mode="diff" must
    # be used instead for a signed series that can cross zero (the
    # yield-curve short-minus-long spread proxy), so a genuine rise
    # through zero still reads as a genuine, correctly-signed rise.
    dates = pd.bdate_range("2026-01-01", periods=25)
    values = [-0.1] * 24 + [0.1]  # flat until the last day, which crosses zero upward
    df = pd.DataFrame(
        {"open": values, "high": values, "low": values, "close": values, "volume": 0.0}, index=dates
    )

    diff_features = compute_features(df, window=20, return_mode="diff")
    last_diff_return = diff_features["return_pct"].iloc[-1]
    assert abs(last_diff_return - 0.2) < 1e-9  # a genuine +0.2 rise

    pct_change_features = compute_features(df, window=20, return_mode="pct_change")
    last_pct_change_return = pct_change_features["return_pct"].iloc[-1]
    assert abs(last_pct_change_return - (-2.0)) < 1e-9  # the bug this replaces: -200%, backwards direction


def test_rolling_stats_exclude_the_current_row_from_its_own_baseline():
    # Regression test (Codex review, 2026-07-30): rolling(window) INCLUDES
    # the current row by default -- without an explicit shift, a big move
    # dilutes/inflates the very mean/std it's then compared against,
    # systematically understating its own z-score. Confirms the shock
    # row's z-score matches a baseline computed from the PRECEDING window
    # only (excluding the shock itself), not the window including it.
    days = 30
    window = 20
    rng = np.random.default_rng(2)
    returns = rng.normal(loc=0.0, scale=0.005, size=days)
    shock_index = days - 1
    returns[shock_index] = 0.20  # a huge +20% one-day return
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    df = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1_000_000.0}, index=dates
    )

    features = compute_features(df, window=window)
    return_pct = features["return_pct"]
    shock_return = return_pct.iloc[shock_index]

    # Window ending the day BEFORE the shock -- excludes it entirely.
    excluding_shock = return_pct.iloc[shock_index - window : shock_index]
    expected_zscore = (shock_return - excluding_shock.mean()) / excluding_shock.std()
    actual_zscore = features["return_zscore"].iloc[shock_index]
    assert abs(actual_zscore - expected_zscore) < 1e-9

    # The buggy (self-included) baseline gives a meaningfully different
    # answer -- confirms this isn't accidentally passing either way.
    including_shock = return_pct.iloc[shock_index - window + 1 : shock_index + 1]
    contaminated_zscore = (shock_return - including_shock.mean()) / including_shock.std()
    assert abs(actual_zscore - contaminated_zscore) > 0.01


def test_compute_features_rejects_unsupported_return_mode():
    dates = pd.bdate_range("2026-01-01", periods=25)
    df = pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0.0}, index=dates
    )
    try:
        compute_features(df, return_mode="bogus")
        assert False, "expected an unsupported return_mode to be rejected"
    except ValueError:
        pass


if __name__ == "__main__":
    test_flags_injected_dip()
    test_flags_injected_up()
    test_ignores_normal_noise()
    test_handles_ticker_with_shorter_history_than_as_of_date()
    test_compute_features_diff_mode_handles_a_zero_crossing_correctly()
    test_rolling_stats_exclude_the_current_row_from_its_own_baseline()
    test_compute_features_rejects_unsupported_return_mode()
    print("All scanner tests passed.")
