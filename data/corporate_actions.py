"""Reference discovery for dividends and splits.

Returned records are informational until confirmed against broker account
activity. Discovery must never mutate the journal or tax lots by itself.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd


def _calendar_value(calendar: Any, key: str) -> Any:
    if isinstance(calendar, dict):
        value = calendar.get(key)
    elif hasattr(calendar, "loc") and key in calendar.index:
        value = calendar.loc[key]
    else:
        return None
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    if isinstance(value, pd.Series):
        return value.iloc[0] if not value.empty else None
    return value


def fetch_upcoming_ex_dividends(
    tickers: list[str], *, as_of: date | None = None
) -> dict[str, dict]:
    import yfinance as yf

    today = as_of or datetime.now(timezone.utc).date()
    fetched_at = datetime.now(timezone.utc).isoformat()
    result: dict[str, dict] = {}
    for raw_ticker in tickers:
        ticker = raw_ticker.upper()
        record = {
            "ticker": ticker,
            "event_type": "ex_dividend",
            "event_date": None,
            "days_away": None,
            "available": False,
            "source": "yfinance.calendar",
            "fetched_at": fetched_at,
            "account_confirmed": False,
        }
        try:
            raw_date = _calendar_value(
                yf.Ticker(ticker).calendar, "Ex-Dividend Date"
            )
            if raw_date is not None:
                event_date = pd.Timestamp(raw_date).date()
                if event_date >= today:
                    record.update(
                        event_date=event_date.isoformat(),
                        days_away=(event_date - today).days,
                        available=True,
                    )
        except (KeyError, TypeError, AttributeError, ValueError, IndexError):
            pass
        result[ticker] = record
    return result


def fetch_recent_splits(
    tickers: list[str],
    *,
    since: date | None = None,
    as_of: date | None = None,
) -> dict[str, list[dict]]:
    """Discover provider-reported split ratios; never applies them."""
    import yfinance as yf

    through = as_of or datetime.now(timezone.utc).date()
    start = since or (through - timedelta(days=370))
    fetched_at = datetime.now(timezone.utc).isoformat()
    result: dict[str, list[dict]] = {}
    for raw_ticker in tickers:
        ticker = raw_ticker.upper()
        events: list[dict] = []
        try:
            series = yf.Ticker(ticker).splits
            for stamp, raw_ratio in series.items():
                event_date = pd.Timestamp(stamp).date()
                ratio = float(raw_ratio)
                if start <= event_date <= through and ratio > 0:
                    events.append(
                        {
                            "ticker": ticker,
                            "event_type": "split",
                            "event_date": event_date.isoformat(),
                            "ratio": ratio,
                            "source": "yfinance.splits",
                            "fetched_at": fetched_at,
                            "account_confirmed": False,
                        }
                    )
        except (KeyError, TypeError, AttributeError, ValueError, IndexError):
            pass
        result[ticker] = sorted(events, key=lambda item: item["event_date"])
    return result
