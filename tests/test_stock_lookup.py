"""Tests for assistant/stock_lookup.py -- the deterministic (non-network)
math behind the Watchlist cart feature. latest_price_targets_by_firm's
own network fetch is exercised via a monkeypatched dependency so the
grouping/sorting logic is verified without hitting yfinance."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import assistant.stock_lookup as stock_lookup
from assistant.stock_lookup import (
    historical_hold_period_range,
    inverse_volatility_weights,
    latest_price_targets_by_firm,
)


def _flat_drift_series(days: int = 60, daily_return: float = 0.005) -> pd.DataFrame:
    returns = np.full(days, daily_return)
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )


def test_historical_hold_period_range_matches_hand_computed_value():
    # Constant daily drift -> every hold_days-day forward return is
    # identical and hand-computable: (1 + daily_return)**hold_days - 1.
    hold_days = 10
    df = _flat_drift_series(days=60, daily_return=0.005)
    result = historical_hold_period_range("A", {"A": df}, hold_days=hold_days)
    expected = round((1.005**hold_days - 1) * 100, 2)

    assert result is not None
    assert result["best_pct"] == expected
    assert result["worst_pct"] == expected
    assert result["median_pct"] == expected
    assert result["hold_days"] == hold_days


def test_historical_hold_period_range_none_for_missing_ticker():
    df = _flat_drift_series()
    assert historical_hold_period_range("MISSING", {"A": df}, hold_days=10) is None


def test_historical_hold_period_range_none_for_insufficient_history():
    df = _flat_drift_series(days=3)
    assert historical_hold_period_range("A", {"A": df}, hold_days=50) is None


def test_inverse_volatility_weights_favors_lower_vol():
    weights = inverse_volatility_weights({"CALM": 1.0, "WILD": 4.0})
    assert weights["CALM"] > weights["WILD"]
    assert abs(sum(weights.values()) - 100.0) < 0.01
    # CALM has 4x lower vol -> should get ~4x the weight (80/20 split)
    assert abs(weights["CALM"] - 80.0) < 0.5
    assert abs(weights["WILD"] - 20.0) < 0.5


def test_inverse_volatility_weights_equal_when_all_unknown():
    weights = inverse_volatility_weights({"A": None, "B": None, "C": 0.0})
    assert weights == {"A": round(100 / 3, 1), "B": round(100 / 3, 1), "C": round(100 / 3, 1)}


def test_inverse_volatility_weights_empty_input():
    assert inverse_volatility_weights({}) == {}


def test_latest_price_targets_by_firm_groups_and_sorts_by_recency(monkeypatch):
    dates = pd.to_datetime(["2026-01-01", "2026-03-01", "2026-02-01"])
    history = pd.DataFrame(
        {"firm": ["Alpha Bank", "Alpha Bank", "Beta Capital"], "price_target": [100.0, 120.0, 90.0]},
        index=dates,
    )

    def fake_fetch(tickers):
        return {"TEST": history}

    monkeypatch.setattr(stock_lookup, "fetch_price_target_history", fake_fetch)

    result = latest_price_targets_by_firm("TEST", max_firms=4)
    assert len(result) == 2  # one row per firm (Alpha Bank's older $100 target dropped)
    assert result[0]["firm"] == "Alpha Bank"
    assert result[0]["price_target"] == 120.0
    assert result[0]["as_of"] == "2026-03-01"
    assert result[1]["firm"] == "Beta Capital"


def test_latest_price_targets_by_firm_empty_when_no_data(monkeypatch):
    monkeypatch.setattr(stock_lookup, "fetch_price_target_history", lambda tickers: {})
    assert latest_price_targets_by_firm("TEST") == []


if __name__ == "__main__":
    test_historical_hold_period_range_matches_hand_computed_value()
    test_historical_hold_period_range_none_for_missing_ticker()
    test_historical_hold_period_range_none_for_insufficient_history()
    test_inverse_volatility_weights_favors_lower_vol()
    test_inverse_volatility_weights_equal_when_all_unknown()
    test_inverse_volatility_weights_empty_input()
    print("All stock_lookup tests passed (run via pytest for the monkeypatch-based tests).")
