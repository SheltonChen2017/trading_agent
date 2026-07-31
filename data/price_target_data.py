"""
Analyst PRICE TARGET consensus data.

Genuinely different from data/analyst_data.py's net-upgrades/downgrades
signal (rating DIRECTION — already tested, REJECTED, see memory:
project_signal_findings). This uses the actual DOLLAR price targets
analysts publish, aggregated into a point-in-time "consensus fair value"
estimate per the user's own proposed method (2026-07): for each firm,
take their most recent still-active target as of a given date, drop the
single highest and lowest, then take the mean or median of the rest.

Point-in-time discipline: a firm's price target is only "active" for a
configurable staleness window (default 365 days) after it was issued —
older targets are dropped rather than treated as still representing that
firm's current view, matching how real consensus-estimate services
(FactSet, Bloomberg) typically only include trailing-12-month estimates.
This avoids two look-ahead traps at once: (1) never uses a target dated
AFTER `as_of`, and (2) never lets a target from years ago silently keep
influencing "today's" consensus just because that firm never
re-published.
"""
from __future__ import annotations

import pandas as pd

from config import ANALYST_TARGET_MIN_ANALYSTS, ANALYST_TARGET_METHOD, ANALYST_TARGET_STALENESS_DAYS
from data.earnings_data import MARKET_CLOSE_HOUR


def fetch_price_target_history(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """
    Fetch each ticker's full analyst price-target history via yfinance,
    one row per (ticker, effective_date, Firm) with a real
    currentPriceTarget (rows with a missing/zero target are dropped —
    yfinance uses 0.0 for actions that didn't include a price target, e.g.
    some "Maintains"/"Announces" entries). Returns a dict mapping ticker ->
    DataFrame indexed by `effective_date` with columns [firm, price_target].

    `effective_date` applies the same after-close correction as
    data/analyst_data.py and data/earnings_data.py to this same
    `upgrades_downgrades` field (GradeDate): an action at/after market
    close is attributed to the next trading day, not the day it was
    published, so compute_consensus_price_target()'s `as_of` comparisons
    can't look ahead into a same-day target published after the close
    (independent review, 2026-07-31).
    """
    import yfinance as yf  # imported lazily, same pattern as fetch_historical

    data: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            raw = yf.Ticker(ticker).upgrades_downgrades
            if raw is None or raw.empty or "currentPriceTarget" not in raw.columns:
                continue
            raw = raw.copy()
            if raw.index.tz is not None:
                raw.index = raw.index.tz_localize(None)
            after_close = raw.index.hour >= MARKET_CLOSE_HOUR
            raw.index = raw.index.normalize() + pd.to_timedelta(after_close.astype(int), unit="D")
            valid = raw[raw["currentPriceTarget"] > 0][["Firm", "currentPriceTarget"]].copy()
            valid.columns = ["firm", "price_target"]
            data[ticker] = valid.sort_index()
        except (KeyError, TypeError, AttributeError, ValueError):
            continue

    return data


def compute_consensus_price_target(
    history: pd.DataFrame,
    as_of: pd.Timestamp,
    staleness_days: int = ANALYST_TARGET_STALENESS_DAYS,
    min_analysts: int = ANALYST_TARGET_MIN_ANALYSTS,
    method: str = ANALYST_TARGET_METHOD,
) -> float | None:
    """
    Point-in-time trimmed consensus price target as of `as_of`: for each
    firm, its most recent price target dated on/before `as_of` and within
    `staleness_days` of it; drops the single highest and single lowest of
    the remaining per-firm targets, then returns the mean or median of
    what's left. Returns None if fewer than `min_analysts` firms have a
    still-active target, or if `history` is empty.
    """
    if history.empty:
        return None
    window_start = as_of - pd.Timedelta(days=staleness_days)
    window = history[(history.index <= as_of) & (history.index >= window_start)]
    if window.empty:
        return None

    latest_per_firm = window.sort_index().groupby("firm")["price_target"].last()
    if len(latest_per_firm) < min_analysts:
        return None

    trimmed = latest_per_firm.sort_values().iloc[1:-1]  # drop single highest and single lowest
    if trimmed.empty:
        return None
    return float(trimmed.median() if method == "median" else trimmed.mean())
