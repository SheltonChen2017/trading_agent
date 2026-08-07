"""
Relative (cross-sectional) dip/up scanner.

signals/scanner.py's scan_dips_and_ups() flags a stock when TODAY's move
is unusual FOR THAT STOCK — a z-score vs. its own trailing history. This
project's own testing showed that design lets a signal ride the whole
market's drift undetected until compared against a benchmark after the
fact (see README's out-of-sample section) — several apparent "edges"
weakened or inverted once measured against SPY on the same dates.

This scanner builds that comparison directly into the signal instead of
checking for it afterward: it flags a stock when TODAY's move is unusual
RELATIVE TO THE REST OF THE UNIVERSE that same day (a cross-sectional
z-score across all tickers on that date), not relative to its own
history. A day where the whole market moves together washes out in a
same-day cross-sectional comparison, so it can't by itself flag every
stock as a "dip"/"up" the way the original scanner's design could.

Same output column contract as scan_dips_and_ups().
"""
from __future__ import annotations

import pandas as pd

from config import RELATIVE_Z_THRESHOLD, ROLLING_WINDOW, VOLUME_Z_THRESHOLD
from signals.scanner import compute_features

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]


def scan_relative_dips_and_ups(
    data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    relative_z_threshold: float = RELATIVE_Z_THRESHOLD,
    volume_z_threshold: float = VOLUME_Z_THRESHOLD,
) -> pd.DataFrame:
    """
    Flag stocks whose SAME-DAY return is unusual relative to the rest of
    the universe that day (cross-sectional z-score), confirmed by
    above-average volume (the stock's own trailing volume z-score, same
    as scan_dips_and_ups). `return_zscore` in the output is this
    cross-sectional z-score, not a vs-own-history one.
    """
    today_returns: dict[str, float] = {}
    volume_zscores: dict[str, float] = {}
    prices: dict[str, float] = {}
    dates: dict[str, pd.Timestamp] = {}

    for ticker, df in data.items():
        if len(df) < ROLLING_WINDOW + 1:
            continue
        if as_of is not None and as_of not in df.index:
            continue

        features = compute_features(df)
        row = features.loc[as_of] if as_of is not None else features.iloc[-1]
        if pd.isna(row["return_pct"]) or pd.isna(row["volume_zscore"]):
            continue

        today_returns[ticker] = row["return_pct"] * 100
        volume_zscores[ticker] = row["volume_zscore"]
        prices[ticker] = row["close"]
        dates[ticker] = row.name

    if len(today_returns) < 5:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    returns_series = pd.Series(today_returns)
    mean, std = returns_series.mean(), returns_series.std()
    if std == 0 or pd.isna(std):
        return pd.DataFrame(columns=RESULT_COLUMNS)
    cross_sectional_z = (returns_series - mean) / std

    rows = []
    for ticker, z in cross_sectional_z.items():
        if pd.isna(z) or abs(z) < relative_z_threshold:
            continue
        if volume_zscores[ticker] < volume_z_threshold:
            continue
        rows.append(
            {
                "ticker": ticker,
                "date": dates[ticker],
                "close": round(prices[ticker], 2),
                "return_pct": round(today_returns[ticker], 2),
                "return_zscore": round(float(z), 2),
                "volume_zscore": round(float(volume_zscores[ticker]), 2),
                "direction": "up" if z > 0 else "dip",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
