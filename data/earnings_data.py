"""
Earnings surprise data — for the post-earnings-announcement-drift signal
(signals/pead.py).

REAL DATA NOTE: yfinance's free earnings calendar
(Ticker.get_earnings_dates()) turned out to have more depth than
expected when checked against live data — often back to ~2020 (~20+
quarters) rather than just a handful. Still, that's roughly 4 events per
ticker per year, far fewer than the daily signals elsewhere in this
project can fire, so PEAD backtests will still have a much smaller
sample per ticker than everything else here — treat results with
correspondingly more caution about small-sample noise.

Reported earnings times matter: an earnings release AT OR AFTER market
close means the market only reacts the NEXT trading day, not the same
day — `effective_date` below accounts for that (see signals/pead.py for
how it's matched against actual trading days, including weekend
spillover).
"""
from __future__ import annotations

import pandas as pd

MARKET_CLOSE_HOUR = 16  # 4:00 PM — earnings at/after this time react the next trading day


def fetch_earnings_surprises(tickers: list[str], limit: int = 20) -> dict[str, pd.DataFrame]:
    """
    Fetch each ticker's available earnings surprise history via yfinance.

    Returns a dict mapping ticker -> DataFrame indexed by `effective_date`
    (timezone-naive, date-only — the trading day the market should react
    on, given the earnings announcement's own timestamp) with a
    `surprise_pct` column (reported EPS vs. estimate, as a % — e.g. 3.46
    means +3.46%, already in percent units, not a fraction). Tickers with
    no data, or without a usable numeric surprise, are skipped — same
    pattern as fetch_historical(), which skips rather than crashes the
    whole fetch over one bad ticker.
    """
    import yfinance as yf  # imported lazily, same pattern as fetch_historical

    data: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            raw = yf.Ticker(ticker).get_earnings_dates(limit=limit)
            if raw is None or raw.empty or "Surprise(%)" not in raw.columns:
                continue
            raw = raw.dropna(subset=["Surprise(%)"]).copy()
            if raw.empty:
                continue

            announced_at = raw.index.tz_localize(None) if raw.index.tz is not None else raw.index
            after_close = announced_at.hour >= MARKET_CLOSE_HOUR
            effective_date = announced_at.normalize() + pd.to_timedelta(after_close.astype(int), unit="D")

            df = pd.DataFrame({"surprise_pct": raw["Surprise(%)"].to_numpy()}, index=effective_date)
            data[ticker] = df.sort_index()
        except (KeyError, TypeError, AttributeError, ValueError):
            continue

    return data
