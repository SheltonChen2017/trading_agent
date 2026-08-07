"""
Sanity tests for signals/relative.py. Run with: python -m pytest tests/ -v
(or `python tests/test_relative.py` for a quick manual check).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.relative import scan_relative_dips_and_ups


def _quiet_series(days: int, seed: int, shock_index: int | None = None, shock_return: float = 0.0, shock_volume: float = 1_000_000.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.0, scale=0.003, size=days)
    # Small volume noise (not literally constant) so rolling volume std
    # isn't zero -- a perfectly flat volume series makes volume_zscore
    # NaN (0/0), which isn't a realistic scenario worth testing here.
    volume = rng.normal(loc=1_000_000.0, scale=20_000.0, size=days)
    if shock_index is not None:
        returns[shock_index] = shock_return
        volume[shock_index] = shock_volume
    close = 100 * np.cumprod(1 + returns)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": volume},
        index=dates,
    )


def test_flags_outlier_relative_to_peers():
    days = 60
    shock_index = 40
    # 9 peers dilutes how much the outlier itself inflates the
    # cross-sectional std, so its z-score clearly clears the threshold
    # rather than being borderline with only a handful of tickers.
    data = {f"PEER{i}": _quiet_series(days, seed=i) for i in range(9)}
    data["OUTLIER"] = _quiet_series(days, seed=99, shock_index=shock_index, shock_return=0.15, shock_volume=5_000_000.0)

    as_of = data["OUTLIER"].index[shock_index]
    result = scan_relative_dips_and_ups(data, as_of=as_of)

    assert not result.empty
    assert "OUTLIER" in result["ticker"].values
    assert result.loc[result["ticker"] == "OUTLIER", "direction"].iloc[0] == "up"


def test_market_wide_move_does_not_flag_everything():
    # Every ticker moves by the EXACT same amount on the same day -> zero
    # cross-sectional spread -> nothing should be flagged, since nothing
    # is unusual RELATIVE TO PEERS even though every stock moved a lot.
    days = 60
    shock_index = 40
    data = {}
    for i in range(5):
        # Force the exact same shock return into every ticker on the same day.
        rng = np.random.default_rng(i)
        returns = rng.normal(loc=0.0, scale=0.003, size=days)
        returns[shock_index] = 0.10
        close = 100 * np.cumprod(1 + returns)
        volume = rng.normal(loc=1_000_000.0, scale=20_000.0, size=days)
        volume[shock_index] = 4_000_000.0
        dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]
        data[f"T{i}"] = pd.DataFrame(
            {"open": close, "high": close, "low": close, "close": close, "volume": volume}, index=dates
        )

    as_of = data["T0"].index[shock_index]
    result = scan_relative_dips_and_ups(data, as_of=as_of)
    assert result.empty, "identical same-day moves across the universe shouldn't flag anything"


def test_returns_empty_with_too_few_tickers():
    data = {"ONLY_ONE": _quiet_series(60, seed=1)}
    result = scan_relative_dips_and_ups(data)
    assert result.empty


if __name__ == "__main__":
    test_flags_outlier_relative_to_peers()
    test_market_wide_move_does_not_flag_everything()
    test_returns_empty_with_too_few_tickers()
    print("All relative scanner tests passed.")
