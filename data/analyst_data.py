"""
Analyst rating-change data — for the analyst-actions signal
(signals/analyst.py).

Genuinely different data category from every other signal in this
project: institutional analyst opinions (upgrades/downgrades/price
targets), not price/volume technicals or company fundamentals.

Multiple firms often issue actions on the same calendar day for the same
ticker — these are aggregated into ONE row per (ticker, effective_date)
before use, so data.earnings_data.match_effective_date() (the same
weekend-spillover matching used by PEAD/fundamentals) can be reused
unchanged.
"""
from __future__ import annotations

import pandas as pd

from data.earnings_data import MARKET_CLOSE_HOUR


def fetch_analyst_actions(tickers: list[str], limit: int | None = None) -> dict[str, pd.DataFrame]:
    """
    Fetch each ticker's analyst upgrade/downgrade history via yfinance,
    aggregated to one row per (ticker, effective_date) — the trading day
    the market should react on, given each action's own timestamp (an
    action at/after market close reacts the next trading day, same
    convention as earnings — see data/earnings_data.py).

    Returns a dict mapping ticker -> DataFrame indexed by `effective_date`
    with columns:
      - `net_actions`: count of upgrades minus count of downgrades that day
      - `n_actions`: total number of analyst actions that day (any type —
        upgrade, downgrade, maintain, initiate)
      - `avg_price_target_change_pct`: average % change in price target
        across that day's actions (NaN where no prior target exists)

    `limit` is accepted for interface consistency with
    fetch_earnings_history() but yfinance's upgrades_downgrades doesn't
    support server-side limiting — the full available history always
    comes back (typically 1-2+ years for large caps).
    """
    import yfinance as yf  # imported lazily, same pattern as fetch_historical

    data: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            raw = yf.Ticker(ticker).upgrades_downgrades
            if raw is None or raw.empty or "Action" not in raw.columns:
                continue
            raw = raw.copy()
            if raw.index.tz is not None:
                raw.index = raw.index.tz_localize(None)

            after_close = raw.index.hour >= MARKET_CLOSE_HOUR
            effective_date = raw.index.normalize() + pd.to_timedelta(after_close.astype(int), unit="D")

            prior = raw["priorPriceTarget"].replace(0, pd.NA)
            pct_change = (raw["currentPriceTarget"] - prior) / prior * 100

            events = pd.DataFrame(
                {
                    "effective_date": effective_date,
                    "is_up": (raw["Action"] == "up").astype(int).to_numpy(),
                    "is_down": (raw["Action"] == "down").astype(int).to_numpy(),
                    "pct_change": pct_change.to_numpy(),
                }
            )
            grouped = events.groupby("effective_date").agg(
                up_count=("is_up", "sum"),
                down_count=("is_down", "sum"),
                n_actions=("is_up", "size"),
                avg_price_target_change_pct=("pct_change", "mean"),
            )
            grouped["net_actions"] = grouped["up_count"] - grouped["down_count"]

            data[ticker] = grouped[["net_actions", "n_actions", "avg_price_target_change_pct"]].sort_index()
        except (KeyError, TypeError, AttributeError, ValueError):
            continue

    return data
