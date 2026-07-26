"""
VIX spike mean-reversion signal.

Genuinely different data category from every other signal in this
project: a market-wide fear gauge (CBOE VIX index), not any ticker's own
price/volume/fundamentals/analyst data. Well-documented, real phenomenon:
VIX spikes (sudden surges in options-implied volatility, reflecting
panic/fear) have historically tended to mean-revert, with the broad
market often bouncing shortly after.

UNLIKE every other signal in this project, this one is NOT ticker-
specific: on a day the VIX itself spikes beyond a z-score threshold,
EVERY ticker in the universe gets flagged simultaneously with
direction="dip" (expect a broad bounce). This creates strong same-day
cross-sectional correlation BY CONSTRUCTION — the whole universe fires
together on the same handful of dates — exactly the situation
`out_of_sample_significance_by_block()` was built to handle correctly
(see memory: project_rigor_toolkit). Never evaluate this signal with a
row-level or by-date-only bootstrap; it would be even more misleading
here than for the other signals that already caught that trap.

"up" leg (VIX COLLAPSE — an unusually sharp drop in the fear gauge) is
included for symmetry with every other signal in this project, not
because there's a strong a priori reason to expect it to work.

Same output contract as every other signal (ticker, date, close,
return_pct, return_zscore, volume_zscore, direction). `return_zscore` is
repurposed to hold the VIX's OWN return z-score (not the stock's) —
every ticker flagged on the same date shares the identical value, since
the trigger is market-wide, not stock-specific.

Sibling signals sharing this exact mechanism: signals/credit_spread.py,
signals/yield_curve.py (see data/macro_data.py for their proxy series).

Usage (needs a second bound argument — same pattern as PEAD/fundamentals/
analyst_target):

    from functools import partial
    from data.market_data import fetch_historical
    from signals.vix_spike import scan_vix_spike

    vix_data = fetch_historical(["^VIX"], lookback_days=1764)["^VIX"]
    run_backtest(data, scan_fn=partial(scan_vix_spike, vix_data=vix_data), scan_kwargs={})
"""
from __future__ import annotations

import pandas as pd

from config import VIX_SPIKE_Z_THRESHOLD
from signals.scanner import compute_features

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]


def scan_vix_spike(
    data: dict[str, pd.DataFrame],
    vix_data: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    z_threshold: float = VIX_SPIKE_Z_THRESHOLD,
) -> pd.DataFrame:
    """
    Flags EVERY ticker in `data` when the VIX itself (`vix_data`, a
    single ticker's OHLCV DataFrame — see
    data.market_data.fetch_historical(["^VIX"])) has an extreme trailing
    return z-score on `as_of`: "dip" for a VIX SPIKE (fear surge, expect
    a broad bounce), "up" for a VIX COLLAPSE (included for symmetry).
    """
    if as_of is None or as_of not in vix_data.index:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    vix_features = compute_features(vix_data)
    vix_zscore = vix_features.loc[as_of, "return_zscore"]
    if pd.isna(vix_zscore) or abs(vix_zscore) < z_threshold:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    direction = "dip" if vix_zscore > 0 else "up"

    rows = []
    for ticker, df in data.items():
        if as_of not in df.index:
            continue
        close = float(df.loc[as_of, "close"])
        rows.append(
            {
                "ticker": ticker,
                "date": as_of,
                "close": round(close, 2),
                "return_pct": 0.0,
                "return_zscore": round(float(vix_zscore), 2),
                "volume_zscore": float("nan"),
                "direction": direction,
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)
