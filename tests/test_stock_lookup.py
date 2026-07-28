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
    compute_blended_volatility,
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


def test_inverse_volatility_weights_max_weight_cap_redistributes_excess():
    # Regression test (GPT review, 2026-07-27): an unusually calm ticker's
    # raw inverse-vol share can otherwise dominate the split with no
    # limit. CALM (vol=1.0) vs two WILD tickers (vol=4.0 each) would
    # normally give CALM ~66.7%; capped at 40%, the excess should be
    # redistributed to the two WILD tickers proportionally (equally,
    # since they're identical).
    weights = inverse_volatility_weights({"CALM": 1.0, "WILD1": 4.0, "WILD2": 4.0}, max_weight_pct=40.0)
    assert weights["CALM"] == 40.0
    assert abs(sum(weights.values()) - 100.0) < 0.01
    assert abs(weights["WILD1"] - weights["WILD2"]) < 0.01
    assert weights["WILD1"] > 25.0  # each got a share of CALM's redistributed excess


def test_inverse_volatility_weights_no_cap_when_max_weight_pct_is_none():
    uncapped = inverse_volatility_weights({"CALM": 1.0, "WILD": 4.0})
    capped_high = inverse_volatility_weights({"CALM": 1.0, "WILD": 4.0}, max_weight_pct=99.0)
    assert uncapped == capped_high  # cap far above the natural split changes nothing


def test_inverse_volatility_weights_cap_below_natural_split_caps_every_ticker_at_it():
    # An infeasible cap (max_weight_pct * n_tickers < 100) can't be fully
    # satisfied -- every ticker ends up AT the cap, weights won't sum to
    # 100. Documented behavior, not a silent bug.
    weights = inverse_volatility_weights({"A": 1.0, "B": 1.0, "C": 1.0}, max_weight_pct=20.0)
    assert all(w == 20.0 for w in weights.values())


def test_compute_blended_volatility_between_short_and_medium_estimates():
    rng = np.random.default_rng(0)
    days = 120
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    # Quiet for the first 100 days, then a choppier last 20 -- short-term
    # (20d) vol should be noticeably higher than medium-term (60d), and
    # the blend should land strictly between the two.
    returns = np.concatenate([rng.normal(0, 0.002, days - 20), rng.normal(0, 0.02, 20)])
    close = pd.Series(100 * np.cumprod(1 + returns), index=dates)
    as_of = dates[-1]

    from signals.regime import compute_trailing_market_volatility

    short_vol = compute_trailing_market_volatility(pd.DataFrame({"close": close}), as_of, lookback_days=20)
    medium_vol = compute_trailing_market_volatility(pd.DataFrame({"close": close}), as_of, lookback_days=60)
    blended = compute_blended_volatility(close, as_of, short_days=20, medium_days=60, short_weight=0.5)

    assert short_vol > medium_vol  # the injected shock made the recent window choppier
    assert medium_vol < blended < short_vol


def test_compute_blended_volatility_falls_back_to_single_window_if_only_one_available():
    days = 25  # enough for a 20-day window, not enough for 60-day
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    rng = np.random.default_rng(1)
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.005, days)), index=dates)
    as_of = dates[-1]

    from signals.regime import compute_trailing_market_volatility

    short_vol = compute_trailing_market_volatility(pd.DataFrame({"close": close}), as_of, lookback_days=20)
    blended = compute_blended_volatility(close, as_of, short_days=20, medium_days=60)
    assert blended == short_vol


def test_compute_blended_volatility_none_when_insufficient_history():
    days = 5
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    close = pd.Series(np.full(days, 100.0), index=dates)
    assert compute_blended_volatility(close, dates[-1], short_days=20, medium_days=60) is None


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
    test_inverse_volatility_weights_max_weight_cap_redistributes_excess()
    test_inverse_volatility_weights_no_cap_when_max_weight_pct_is_none()
    test_inverse_volatility_weights_cap_below_natural_split_caps_every_ticker_at_it()
    test_compute_blended_volatility_between_short_and_medium_estimates()
    test_compute_blended_volatility_falls_back_to_single_window_if_only_one_available()
    test_compute_blended_volatility_none_when_insufficient_history()
    print("All stock_lookup tests passed (run via pytest for the monkeypatch-based tests).")
