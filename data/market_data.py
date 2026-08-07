"""
Market data layer.

fetch_historical() pulls real daily bars via yfinance — use this once you're
running locally with internet access.

generate_synthetic() builds a fake-but-realistic universe of price/volume
series with occasional injected shocks, so you can develop and test the
scanner and backtester logic without hitting any external API.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

_NYSE_CALENDAR = mcal.get_calendar("NYSE")
_REQUIRED_OHLCV_COLUMNS = {"open", "high", "low", "close", "volume"}


def _trading_session_start_date(lookback_days: int, end_date: pd.Timestamp | None = None) -> str:
    """
    Returns the calendar start date (YYYY-MM-DD) such that the NYSE
    calendar's real trading sessions from that date through `end_date`
    (default: today) include AT LEAST `lookback_days` sessions.

    fetch_historical() used to request yfinance's `period=f"{N+10}d"`,
    which is CALENDAR days, not trading sessions -- a requested 252-
    session lookback silently returned only ~180-190 actual bars (2026-
    07-28, GPT review), and every consumer (signals, regime calculation,
    risk analytics, Watchlist analytics, strategy research) had no way to
    know it got less history than asked for. Deriving the start date from
    the REAL NYSE calendar instead means the request always spans enough
    actual sessions for a ticker with that much real history.
    """
    end = end_date if end_date is not None else pd.Timestamp.today().normalize()
    # NYSE trading days run roughly 5/7 of calendar days, minus ~9
    # holidays/year -- 1.6x plus a flat margin comfortably covers that
    # even through a holiday-heavy stretch (e.g. Nov-Jan).
    calendar_buffer_days = int(lookback_days * 1.6) + 30
    candidate_start = end - pd.Timedelta(days=calendar_buffer_days)
    schedule = _NYSE_CALENDAR.schedule(
        start_date=candidate_start.date().isoformat(), end_date=end.date().isoformat()
    )
    if len(schedule) < lookback_days:
        # A very long lookback or an unusually holiday-dense window --
        # widen further rather than silently under-filling.
        calendar_buffer_days = int(lookback_days * 2.5) + 60
        candidate_start = end - pd.Timedelta(days=calendar_buffer_days)
        schedule = _NYSE_CALENDAR.schedule(
            start_date=candidate_start.date().isoformat(), end_date=end.date().isoformat()
        )
    sessions = schedule.index
    if len(sessions) >= lookback_days:
        return sessions[-lookback_days].date().isoformat()
    return candidate_start.date().isoformat()


def fetch_historical(tickers: list[str], lookback_days: int = 252) -> dict[str, pd.DataFrame]:
    """
    Fetch daily OHLCV bars for each ticker using yfinance.

    Returns a dict mapping ticker -> DataFrame with columns
    [open, high, low, close, volume], indexed by date, sorted ascending
    with no duplicate dates, trimmed to at most `lookback_days` real
    trading sessions. A ticker with genuinely less history than
    `lookback_days` (e.g. a recent IPO) legitimately returns fewer rows --
    that's an honest reflection of what exists, not a bug; callers that
    need a strict minimum should check `len(data[ticker])` themselves
    (see the real-data-check project skill).

    Requires `pip install yfinance` and internet access.
    """
    import yfinance as yf  # imported lazily so this module still loads without the package

    start_date = _trading_session_start_date(lookback_days)
    data: dict[str, pd.DataFrame] = {}

    raw = yf.download(
        tickers=tickers,
        start=start_date,
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
    )

    for ticker in tickers:
        try:
            # yfinance returns MultiIndex (ticker, field) columns with
            # group_by="ticker" regardless of how many tickers were
            # requested — including a single-ticker request — so always
            # index by ticker when that's the shape we got back.
            df = raw[ticker].copy() if isinstance(raw.columns, pd.MultiIndex) else raw.copy()
            df.columns = [c.lower() for c in df.columns]
            if not _REQUIRED_OHLCV_COLUMNS.issubset(df.columns):
                continue
            df = df.dropna(subset=["close"])
            # Defensive: a provider response should already be sorted and
            # unique, but never trust that silently -- a duplicated or
            # out-of-order index would corrupt every rolling-window
            # calculation downstream (scanner z-scores, volatility, trend).
            df = df[~df.index.duplicated(keep="last")].sort_index()
            data[ticker] = df.tail(lookback_days)
        except (KeyError, TypeError):
            # Ticker delisted, typo'd, or no data returned — skip rather than crash the whole scan
            continue

    return data


def generate_synthetic(
    tickers: list[str],
    days: int = 252,
    seed: int = 7,
    shock_probability: float = 0.03,
) -> dict[str, pd.DataFrame]:
    """
    Generate synthetic daily OHLCV data for development and testing.

    Each ticker follows a geometric random walk with small daily drift,
    plus occasional larger "shock" days (both up and down) so the scanner
    has real anomalies to find. This is for pipeline development only —
    it has no relationship to any real stock's actual behavior.
    """
    rng = np.random.default_rng(seed)
    # Small buffer + trim: bdate_range's periods count can be off by one when
    # `end` itself falls on a weekend, so over-request slightly and slice.
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days + 5)[-days:]

    data: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        daily_returns = rng.normal(loc=0.0004, scale=0.015, size=days)

        shock_mask = rng.random(days) < shock_probability
        shock_sizes = rng.normal(loc=0.0, scale=0.05, size=days)
        daily_returns = np.where(shock_mask, daily_returns + shock_sizes, daily_returns)

        start_price = rng.uniform(50, 400)
        close = start_price * np.cumprod(1 + daily_returns)

        intraday_range = np.abs(rng.normal(loc=0.01, scale=0.005, size=days))
        high = close * (1 + intraday_range)
        low = close * (1 - intraday_range)
        open_ = low + (high - low) * rng.random(days)

        base_volume = rng.uniform(5_000_000, 30_000_000)
        volume = base_volume * (1 + np.abs(daily_returns) * 8) * rng.uniform(0.8, 1.2, size=days)

        data[ticker] = pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume.astype(int),
            },
            index=dates,
        )

    return data
