"""
Sanity tests for signals/vix_spike.py. Run with:
python tests/test_vix_spike.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.vix_spike import scan_vix_spike


def _flat_series_with_shock(days: int, shock_index: int, shock_return: float) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    returns = rng.normal(loc=0.0, scale=0.003, size=days)
    returns[shock_index] = shock_return
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": 1_000_000.0},
        index=dates,
    )


def _flat_stock_data(dates: pd.DatetimeIndex, close: float = 50.0) -> pd.DataFrame:
    closes = np.full(len(dates), close)
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1_000_000.0},
        index=dates,
    )


def test_flags_entire_universe_dip_on_vix_spike():
    days = 60
    vix_df = _flat_series_with_shock(days, shock_index=days - 1, shock_return=0.35)
    as_of = vix_df.index[-1]
    data = {
        "AAA": _flat_stock_data(vix_df.index, close=50.0),
        "BBB": _flat_stock_data(vix_df.index, close=200.0),
    }

    result = scan_vix_spike(data, vix_data=vix_df, as_of=as_of)
    assert not result.empty
    assert set(result["ticker"]) == {"AAA", "BBB"}
    assert (result["direction"] == "dip").all()
    # every ticker shares the identical VIX-level z-score, not a stock-specific one
    assert result["return_zscore"].nunique() == 1


def test_flags_entire_universe_up_on_vix_collapse():
    days = 60
    vix_df = _flat_series_with_shock(days, shock_index=days - 1, shock_return=-0.30)
    as_of = vix_df.index[-1]
    data = {"AAA": _flat_stock_data(vix_df.index)}

    result = scan_vix_spike(data, vix_data=vix_df, as_of=as_of)
    assert not result.empty
    assert (result["direction"] == "up").all()


def test_no_signal_on_quiet_vix_day():
    days = 60
    rng = np.random.default_rng(1)
    returns = rng.normal(loc=0.0, scale=0.005, size=days)
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    vix_df = pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": 1_000_000.0},
        index=dates,
    )
    as_of = vix_df.index[-1]
    data = {"AAA": _flat_stock_data(vix_df.index)}

    result = scan_vix_spike(data, vix_data=vix_df, as_of=as_of)
    assert result.empty


def test_no_signal_when_as_of_is_none():
    days = 60
    vix_df = _flat_series_with_shock(days, shock_index=days - 1, shock_return=0.35)
    data = {"AAA": _flat_stock_data(vix_df.index)}
    result = scan_vix_spike(data, vix_data=vix_df, as_of=None)
    assert result.empty


def test_no_signal_when_as_of_missing_from_vix_index():
    days = 60
    vix_df = _flat_series_with_shock(days, shock_index=days - 1, shock_return=0.35)
    data = {"AAA": _flat_stock_data(vix_df.index)}
    missing_date = pd.Timestamp("1999-01-01")
    result = scan_vix_spike(data, vix_data=vix_df, as_of=missing_date)
    assert result.empty


def test_skips_ticker_missing_on_as_of_date():
    days = 60
    vix_df = _flat_series_with_shock(days, shock_index=days - 1, shock_return=0.35)
    as_of = vix_df.index[-1]
    full_history = _flat_stock_data(vix_df.index)
    short_history = full_history.iloc[:-1]  # doesn't cover as_of

    result = scan_vix_spike({"FULL": full_history, "SHORT": short_history}, vix_data=vix_df, as_of=as_of)
    assert "FULL" in result["ticker"].values
    assert "SHORT" not in result["ticker"].values


if __name__ == "__main__":
    test_flags_entire_universe_dip_on_vix_spike()
    test_flags_entire_universe_up_on_vix_collapse()
    test_no_signal_on_quiet_vix_day()
    test_no_signal_when_as_of_is_none()
    test_no_signal_when_as_of_missing_from_vix_index()
    test_skips_ticker_missing_on_as_of_date()
    print("All vix_spike signal tests passed.")
