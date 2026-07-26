"""
Post-Earnings-Announcement-Drift (PEAD) signal.

Documented anomaly (Bernard & Thomas 1989, replicated many times since):
stocks that beat earnings estimates have historically tended to keep
drifting up for weeks afterward, and vice versa for misses — arguably
the most robust anomaly in the academic literature. Different in kind
from every other signal in this project: it's EVENT-DRIVEN (fires only
around earnings dates, a handful of times per year per ticker), not a
daily technical signal — see data/earnings_data.py for the real data
depth/limitation this implies.

Same output column contract as scan_dips_and_ups(), with `return_zscore`
repurposed as the earnings surprise % (a stock's own trailing
daily-return z-score isn't the relevant concept here).

Usage note: unlike the two technical signals (momentum, relative), this
one needs a second input (`earnings_data`, from
data.earnings_data.fetch_earnings_history()) that must be fixed for a
given backtest run. Bind it with functools.partial before passing as
`scan_fn` to anything in backtest/engine.py:

    from functools import partial
    from data.earnings_data import fetch_earnings_history
    from signals.pead import scan_pead

    earnings = fetch_earnings_history(list(data.keys()))
    run_backtest(data, scan_fn=partial(scan_pead, earnings_data=earnings), scan_kwargs={})
"""
from __future__ import annotations

import pandas as pd

from config import PEAD_SURPRISE_THRESHOLD_PCT
from data.earnings_data import match_effective_date

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]


def scan_pead(
    data: dict[str, pd.DataFrame],
    earnings_data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    surprise_threshold_pct: float = PEAD_SURPRISE_THRESHOLD_PCT,
) -> pd.DataFrame:
    """
    Flag a stock on the trading day its earnings reaction should hit
    (data.earnings_data's `effective_date`, already adjusted for
    after-close announcements — see match_effective_date() for how
    weekend/holiday spillover is handled) if the reported surprise
    exceeds `surprise_threshold_pct` in either direction.
    """
    if as_of is None:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    rows = []
    for ticker, price_df in data.items():
        if ticker not in earnings_data or as_of not in price_df.index:
            continue

        surprises = earnings_data[ticker]
        matched = match_effective_date(as_of, surprises.index, price_df.index)
        if matched is None:
            continue

        surprise_pct = float(surprises.loc[matched, "surprise_pct"])
        if pd.isna(surprise_pct) or abs(surprise_pct) < surprise_threshold_pct:
            continue

        close = float(price_df.loc[as_of, "close"])
        rows.append(
            {
                "ticker": ticker,
                "date": as_of,
                "close": round(close, 2),
                "return_pct": 0.0,
                "return_zscore": round(surprise_pct, 2),
                "volume_zscore": float("nan"),
                "direction": "up" if surprise_pct > 0 else "dip",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
