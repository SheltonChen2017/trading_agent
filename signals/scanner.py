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


def compute_features(df: pd.DataFrame, window: int = ROLLING_WINDOW, return_mode: str = "pct_change") -> pd.DataFrame:
    """
    Add return, rolling z-score, and volume z-score columns to a single
    ticker's OHLCV DataFrame. Uses only trailing data at each row -- the
    rolling mean/std are shifted by 1 so a row's own value is EXCLUDED
    from its own baseline (pandas' rolling() includes the current row by
    default; without the shift, a big move dilutes/inflates the very
    mean/std it's then compared against, systematically understating its
    own z-score -- Codex review, 2026-07-30, caught this in the module
    that had been claiming, incorrectly, to already exclude the current
    row). Safe to call on the full history and then just read off the
    last row.

    `return_mode="pct_change"` (default) is correct for any `close` series
    that's a genuine price (always positive) -- every per-ticker signal,
    plus the VIX and credit-spread macro proxies. `return_mode="diff"`
    must be used instead for a series that can be zero or cross zero (the
    yield-curve short-minus-long spread proxy in data/macro_data.py): a
    percent change is undefined/sign-reversing across a zero crossing
    (e.g. -0.1 -> +0.1 computes as -200%, which looks like a collapse in
    stress when inversion actually just got worse) (Codex review,
    2026-07-27).
    """
    if return_mode not in ("pct_change", "diff"):
        raise ValueError(f"return_mode must be 'pct_change' or 'diff', got {return_mode!r}.")
    out = df.copy()
    out["return_pct"] = out["close"].pct_change() if return_mode == "pct_change" else out["close"].diff()

    rolling_mean = out["return_pct"].shift(1).rolling(window).mean()
    rolling_std = out["return_pct"].shift(1).rolling(window).std()
    out["return_zscore"] = (out["return_pct"] - rolling_mean) / rolling_std

    vol_mean = out["volume"].shift(1).rolling(window).mean()
    vol_std = out["volume"].shift(1).rolling(window).std()
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
        if as_of is not None and as_of not in df.index:
            continue  # ticker didn't exist yet (e.g. a recent IPO) as of this date

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
