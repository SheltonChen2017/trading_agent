"""Upcoming corporate-event data with explicit availability and provenance."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd


def fetch_upcoming_earnings(tickers: list[str], as_of: date | None = None) -> dict[str, dict]:
    """
    Fetch the next known earnings date for each ticker from yfinance.

    Missing or malformed calendars are returned as unavailable records;
    they are never guessed and never silently omitted.
    """
    import yfinance as yf

    today = as_of or datetime.now(timezone.utc).date()
    fetched_at = datetime.now(timezone.utc).isoformat()
    results: dict[str, dict] = {}
    for ticker in tickers:
        record = {
            "ticker": ticker,
            "event_type": "earnings",
            "event_date": None,
            "days_away": None,
            "available": False,
            "source": "yfinance.calendar",
            "fetched_at": fetched_at,
        }
        try:
            calendar = yf.Ticker(ticker).calendar
            raw_date = None
            if isinstance(calendar, dict):
                raw_date = calendar.get("Earnings Date")
            elif hasattr(calendar, "loc") and "Earnings Date" in calendar.index:
                raw_date = calendar.loc["Earnings Date"]
            if isinstance(raw_date, (list, tuple)):
                raw_date = raw_date[0] if raw_date else None
            if isinstance(raw_date, pd.Series):
                raw_date = raw_date.iloc[0] if not raw_date.empty else None
            if raw_date is not None:
                event_date = pd.Timestamp(raw_date).date()
                if event_date >= today:
                    record.update(
                        {
                            "event_date": event_date.isoformat(),
                            "days_away": (event_date - today).days,
                            "available": True,
                        }
                    )
        except (KeyError, TypeError, AttributeError, ValueError, IndexError):
            pass
        results[ticker] = record
    return results
