"""
Earnings history data — for the two event-driven signals that need real
disclosure dates and figures: post-earnings-announcement-drift
(signals/pead.py) and the fundamentals/earnings-growth signal
(signals/fundamentals.py).

REAL DATA NOTE: yfinance's free earnings calendar
(Ticker.get_earnings_dates()) turned out to have more depth than
expected when checked against live data — often back to ~2020 (~20+
quarters) rather than just a handful. Still, that's roughly 4 events per
ticker per year, far fewer than the daily signals elsewhere in this
project can fire, so backtests built on this data will still have a much
smaller sample per ticker than everything else here — treat results with
correspondingly more caution about small-sample noise.

Reported earnings times matter: an earnings release AT OR AFTER market
close means the market only reacts the NEXT trading day, not the same
day — `effective_date` below accounts for that. `match_effective_date()`
then handles matching an effective_date to an actual trading day,
including weekend/holiday spillover (an event whose effective_date isn't
itself a trading day fires on the FIRST trading day afterward — and only
once, not on every subsequent day).
"""
from __future__ import annotations

import pandas as pd

MARKET_CLOSE_HOUR = 16  # 4:00 PM — earnings at/after this time react the next trading day
MAX_FORWARD_SEARCH_DAYS = 3  # weekend/holiday spillover: how far forward to look for the next trading day


def fetch_earnings_history(tickers: list[str], limit: int = 20) -> dict[str, pd.DataFrame]:
    """
    Fetch each ticker's available earnings history via yfinance.

    Returns a dict mapping ticker -> DataFrame indexed by `effective_date`
    (timezone-naive, date-only — the trading day the market should react
    on, given the earnings announcement's own timestamp), with columns:
      - `surprise_pct`: reported EPS vs. estimate, as a % (e.g. 3.46 means
        +3.46%, already in percent units, not a fraction)
      - `reported_eps`: the actual reported EPS that quarter (for
        computing YoY earnings growth — see signals/fundamentals.py)

    Tickers with no data, or without usable numeric figures, are skipped
    — same pattern as fetch_historical(), which skips rather than
    crashes the whole fetch over one bad ticker.
    """
    import yfinance as yf  # imported lazily, same pattern as fetch_historical

    data: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            raw = yf.Ticker(ticker).get_earnings_dates(limit=limit)
            if raw is None or raw.empty:
                continue
            raw = raw.dropna(subset=["Reported EPS"], how="all").copy()
            if raw.empty:
                continue

            announced_at = raw.index.tz_localize(None) if raw.index.tz is not None else raw.index
            after_close = announced_at.hour >= MARKET_CLOSE_HOUR
            effective_date = announced_at.normalize() + pd.to_timedelta(after_close.astype(int), unit="D")

            df = pd.DataFrame(
                {
                    "surprise_pct": raw["Surprise(%)"].to_numpy() if "Surprise(%)" in raw.columns else float("nan"),
                    "reported_eps": raw["Reported EPS"].to_numpy(),
                },
                index=effective_date,
            )
            data[ticker] = df.sort_index()
        except (KeyError, TypeError, AttributeError, ValueError):
            continue

    return data


def match_effective_date(
    target_date: pd.Timestamp,
    event_dates: pd.Index,
    price_index: pd.Index,
    max_forward_search_days: int = MAX_FORWARD_SEARCH_DAYS,
) -> pd.Timestamp | None:
    """
    Does `target_date` (a real trading day, from a ticker's price index)
    correspond to an event in `event_dates`? Handles the case where an
    event's own `effective_date` isn't itself a trading day (weekend/
    holiday) — such an event should fire on the FIRST trading day
    afterward, and ONLY that day, not every subsequent day too.

    Returns the matched event date, or None if `target_date` doesn't
    correspond to any event.
    """
    target = pd.Timestamp(target_date).normalize()

    if target in event_dates:
        return target

    for offset in range(1, max_forward_search_days + 1):
        candidate_date = target - pd.Timedelta(days=offset)
        if candidate_date not in event_dates or candidate_date in price_index:
            continue
        already_claimed = price_index[(price_index > candidate_date) & (price_index < target)]
        if len(already_claimed) > 0:
            continue
        return candidate_date

    return None
