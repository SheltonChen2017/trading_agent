"""
Sanity tests for signals/breakout.py. Run with: python -m pytest tests/ -v
(or `python tests/test_breakout.py` for a quick manual check).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.breakout import scan_52_week_breakout


def _series_with_final_day_move(
    days: int, final_return: float, final_volume: float = 4_000_000.0, base_volatility: float = 0.005
) -> pd.DataFrame:
    """A choppy-but-bounded series, with a deliberate move on the LAST day
    so it's easy to control whether that day is a new high/low."""
    rng = np.random.default_rng(0)
    returns = rng.normal(loc=0.0, scale=base_volatility, size=days)
    returns[-1] = final_return
    close = 100 * np.cumprod(1 + returns)
    volume = np.full(days, 1_000_000.0)
    volume[-1] = final_volume
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": volume},
        index=dates,
    )


def test_flags_new_high_with_volume_confirmation():
    days = 280
    df = _series_with_final_day_move(days, final_return=0.5)  # +50% -> guaranteed new high
    result = scan_52_week_breakout({"TEST": df}, lookback_days=252)
    assert not result.empty
    assert result.iloc[0]["ticker"] == "TEST"
    assert result.iloc[0]["direction"] == "up"


def test_flags_new_low_with_volume_confirmation():
    days = 280
    df = _series_with_final_day_move(days, final_return=-0.5)  # -50% -> guaranteed new low
    result = scan_52_week_breakout({"TEST": df}, lookback_days=252)
    assert not result.empty
    assert result.iloc[0]["direction"] == "dip"


def test_no_signal_without_volume_confirmation():
    days = 280
    # Big move, but volume stays flat -> shouldn't clear the volume filter.
    df = _series_with_final_day_move(days, final_return=0.5, final_volume=1_000_000.0)
    result = scan_52_week_breakout({"TEST": df}, lookback_days=252)
    assert result.empty


def test_no_signal_when_not_a_breakout():
    days = 280
    rng = np.random.default_rng(1)
    returns = rng.normal(loc=0.0, scale=0.005, size=days)
    close = 100 * np.cumprod(1 + returns)
    volume = np.full(days, 1_000_000.0)
    volume[-1] = 4_000_000.0  # volume spike, but no breakout -- shouldn't fire on volume alone
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    df = pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": volume}, index=dates
    )
    # Force the final close to sit mid-range, not a new high/low.
    df.iloc[-1, df.columns.get_loc("close")] = df["close"].iloc[:-1].median()

    result = scan_52_week_breakout({"TEST": df}, lookback_days=252)
    assert result.empty


def test_returns_empty_with_insufficient_history():
    df = _series_with_final_day_move(days=100, final_return=0.5)  # shorter than lookback_days
    result = scan_52_week_breakout({"TEST": df}, lookback_days=252)
    assert result.empty


if __name__ == "__main__":
    test_flags_new_high_with_volume_confirmation()
    test_flags_new_low_with_volume_confirmation()
    test_no_signal_without_volume_confirmation()
    test_no_signal_when_not_a_breakout()
    test_returns_empty_with_insufficient_history()
    print("All breakout tests passed.")
