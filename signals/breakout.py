"""
52-week high/low breakout continuation signal.

A documented variant of momentum: stocks making a new N-day high on
above-average volume have historically tended to keep going (breakout
continuation) rather than immediately reversing. "up" = new N-day high;
"dip" = new N-day low, included for symmetry with the rest of this
project's dip/up structure — breakdown continuation is less strongly
supported in the literature than the high-breakout leg, so treat "dip"
signals from this scanner with extra skepticism.

Same output column contract as scan_dips_and_ups(). `return_zscore` is
the stock's own trailing daily-return z-score (same definition as
scan_dips_and_ups, via compute_features), reported for context — the
actual FILTER criterion here is "today's close is the highest/lowest
close of the trailing `lookback_days`", not a z-score threshold.
"""
from __future__ import annotations

import pandas as pd

from config import BREAKOUT_LOOKBACK_DAYS, ROLLING_WINDOW, VOLUME_Z_THRESHOLD
from signals.scanner import compute_features

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]


def scan_52_week_breakout(
    data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    lookback_days: int = BREAKOUT_LOOKBACK_DAYS,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
) -> pd.DataFrame:
    """
    Flag a stock when today's close is a new `lookback_days`-day high
    ("up") or low ("dip"), confirmed by above-average volume.
    """
    rows = []
    for ticker, df in data.items():
        if len(df) < max(ROLLING_WINDOW, lookback_days) + 1:
            continue
        if as_of is not None and as_of not in df.index:
            continue

        features = compute_features(df)
        idx = df.index.get_loc(as_of) if as_of is not None else len(df) - 1
        if idx - lookback_days < 0:
            continue

        row = features.iloc[idx]
        if pd.isna(row["volume_zscore"]):
            continue

        trailing_window = df["close"].iloc[idx - lookback_days : idx]  # excludes today
        today_close = row["close"]
        is_new_high = today_close > trailing_window.max()
        is_new_low = today_close < trailing_window.min()
        if not (is_new_high or is_new_low):
            continue
        if row["volume_zscore"] < volume_z_threshold:
            continue

        rows.append(
            {
                "ticker": ticker,
                "date": row.name,
                "close": round(today_close, 2),
                "return_pct": round(row["return_pct"] * 100, 2) if not pd.isna(row["return_pct"]) else 0.0,
                "return_zscore": round(row["return_zscore"], 2) if not pd.isna(row["return_zscore"]) else 0.0,
                "volume_zscore": round(row["volume_zscore"], 2),
                "direction": "up" if is_new_high else "dip",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["volume_zscore"].sort_values(ascending=False).index).reset_index(drop=True)
