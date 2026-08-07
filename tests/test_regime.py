"""
Sanity tests for signals/regime.py. Run with:
python -m pytest tests/ -v (or `python tests/test_regime.py`).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.regime import (
    calibrate_threshold_from_discovery,
    classify_regime,
    compute_trailing_market_volatility,
)


def _benchmark_with_two_vol_regimes(quiet_days: int, wild_days: int) -> pd.DataFrame:
    """A benchmark series that's calm for the first `quiet_days`, then
    much more volatile for the next `wild_days`."""
    rng = np.random.default_rng(0)
    quiet_returns = rng.normal(0, 0.002, size=quiet_days)
    wild_returns = rng.normal(0, 0.03, size=wild_days)
    returns = np.concatenate([quiet_returns, wild_returns])
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=len(returns) + 5)[-len(returns):]
    return pd.DataFrame({"close": close}, index=dates)


def test_compute_trailing_market_volatility_higher_in_wild_period():
    df = _benchmark_with_two_vol_regimes(quiet_days=100, wild_days=100)
    quiet_vol = compute_trailing_market_volatility(df, df.index[90], lookback_days=60)
    wild_vol = compute_trailing_market_volatility(df, df.index[190], lookback_days=60)

    assert quiet_vol is not None and wild_vol is not None
    assert wild_vol > quiet_vol * 3  # should be dramatically higher, not just marginally


def test_compute_trailing_market_volatility_none_without_enough_history():
    df = _benchmark_with_two_vol_regimes(quiet_days=100, wild_days=100)
    assert compute_trailing_market_volatility(df, df.index[5], lookback_days=60) is None


def test_compute_trailing_market_volatility_none_when_date_missing():
    df = _benchmark_with_two_vol_regimes(quiet_days=100, wild_days=100)
    assert compute_trailing_market_volatility(df, pd.Timestamp("1999-01-01"), lookback_days=60) is None


def test_classify_regime_separates_quiet_from_wild():
    df = _benchmark_with_two_vol_regimes(quiet_days=100, wild_days=100)
    threshold = compute_trailing_market_volatility(df, df.index[100], lookback_days=60)  # boundary-ish value

    quiet_label = classify_regime(df, df.index[90], threshold_pct=threshold, lookback_days=60)
    wild_label = classify_regime(df, df.index[190], threshold_pct=threshold, lookback_days=60)

    assert quiet_label == "low_vol"
    assert wild_label == "high_vol"


def test_calibrate_threshold_from_discovery_uses_only_discovery_data():
    # Discovery = quiet period only; confirmation = wild period. The
    # calibrated threshold should reflect the quiet period's own low
    # volatility, not be inflated by the wild period it never saw.
    df = _benchmark_with_two_vol_regimes(quiet_days=100, wild_days=100)
    discovery_end = df.index[99]  # last quiet-period date

    threshold = calibrate_threshold_from_discovery(df, discovery_end, lookback_days=60)
    wild_vol = compute_trailing_market_volatility(df, df.index[190], lookback_days=60)

    assert threshold < wild_vol  # a discovery-only threshold should NOT already reflect the wild period


def test_calibrate_threshold_raises_without_enough_history():
    df = _benchmark_with_two_vol_regimes(quiet_days=100, wild_days=100)
    try:
        calibrate_threshold_from_discovery(df, df.index[5], lookback_days=60)
        assert False, "expected ValueError with too little discovery history"
    except ValueError:
        pass


if __name__ == "__main__":
    test_compute_trailing_market_volatility_higher_in_wild_period()
    test_compute_trailing_market_volatility_none_without_enough_history()
    test_compute_trailing_market_volatility_none_when_date_missing()
    test_classify_regime_separates_quiet_from_wild()
    test_calibrate_threshold_from_discovery_uses_only_discovery_data()
    test_calibrate_threshold_raises_without_enough_history()
    print("All regime tests passed.")
