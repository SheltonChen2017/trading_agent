"""
Daily dip/up scanner.

The core idea: a stock's "normal" daily move is specific to that stock — a
10% day is unremarkable for a volatile small-cap and extreme for a utility.
So instead of a flat "% move" threshold across the whole universe, we score
each day's return against that ticker's OWN recent rolling mean/std (a
z-score). This makes signals comparable across very different stocks.

IMPORTANT: everything here only uses data available up to and including the
current row — no forward-looking values. This same function is what the
backtester will call, so whatever it flags historically is exactly what it
would have flagged in real time. Keeping one code path for both is what
prevents look-ahead bias from creeping in silently.
"""
from __future__ import annotations

import pandas as pd

from config import RETURN_Z_THRESHOLD, ROLLING_WINDOW, VOLUME_Z_THRESHOLD


def compute_features(df: pd.DataFrame, window: int = ROLLING_WINDOW) -> pd.DataFrame:
    """
    Add return, rolling z-score, and volume z-score columns to a single
    ticker's OHLCV DataFrame. Uses only trailing data at each row (rolling
    windows naturally exclude the current-and-future rows from their own
    mean/std by shifting), so it's safe to call on the full history and
    then just read off the last row.
    """
    out = df.copy()
    out["return_pct"] = out["close"].pct_change()

    rolling_mean = out["return_pct"].rolling(window).mean()
    rolling_std = out["return_pct"].rolling(window).std()
    out["return_zscore"] = (out["return_pct"] - rolling_mean) / rolling_std

    vol_mean = out["volume"].rolling(window).mean()
    vol_std = out["volume"].rolling(window).std()
    out["volume_zscore"] = (out["volume"] - vol_mean) / vol_std

    return out


def scan_dips_and_ups(
    data: dict[str, pd.DataFrame],
    return_z_threshold: float = RETURN_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Scan every ticker's most recent day (or `as_of`, if given — useful for
    backtesting a specific historical date) and flag statistically unusual
    moves confirmed by above-average volume.

    Returns a DataFrame with one row per flagged ticker, sorted by the
    magnitude of the anomaly, with columns:
        ticker, date, close, return_pct, return_zscore, volume_zscore, direction
    """
    rows = []

    for ticker, df in data.items():
        if len(df) < ROLLING_WINDOW + 1:
            continue  # not enough history to compute a stable rolling stat

        features = compute_features(df)
        row = features.loc[as_of] if as_of is not None else features.iloc[-1]

        if pd.isna(row["return_zscore"]) or pd.isna(row["volume_zscore"]):
            continue

        is_significant_move = abs(row["return_zscore"]) >= return_z_threshold
        is_confirmed_by_volume = row["volume_zscore"] >= volume_z_threshold

        if is_significant_move and is_confirmed_by_volume:
            rows.append(
                {
                    "ticker": ticker,
                    "date": row.name,
                    "close": round(row["close"], 2),
                    "return_pct": round(row["return_pct"] * 100, 2),
                    "return_zscore": round(row["return_zscore"], 2),
                    "volume_zscore": round(row["volume_zscore"], 2),
                    "direction": "up" if row["return_zscore"] > 0 else "dip",
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]
        )

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
