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

from signals.scanner import scan_dips_and_ups


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


if __name__ == "__main__":
    test_flags_injected_dip()
    test_flags_injected_up()
    test_ignores_normal_noise()
    print("All scanner tests passed.")
