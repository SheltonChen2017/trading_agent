"""
Market data layer.

fetch_historical() pulls real daily bars via yfinance — use this once you're
running locally with internet access.

generate_synthetic() builds a fake-but-realistic universe of price/volume
series with occasional injected shocks, so you can develop and test the
scanner and backtester logic without hitting any external API.
"""
from __future__ import annotations

import dataclasses
import re

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

_NYSE_CALENDAR = mcal.get_calendar("NYSE")
_REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
_CANONICAL_TICKER_PATTERN = re.compile(r"[A-Z0-9^][A-Z0-9.^=_-]{0,31}")


@dataclasses.dataclass(frozen=True)
class DailyBarValidation:
    """Result of the one authoritative daily-bar usability check.

    A bad frame is data-quality evidence, not an exception that should erase
    usable sibling tickers. Invalid requested ticker identities remain
    programmer/input errors and therefore raise from ``canonical_ticker``.
    """

    ticker: str
    usable: bool
    latest_session: str | None
    error: str | None


def canonical_ticker(raw_ticker: object) -> str:
    """Return the canonical provider symbol or reject an ambiguous identity.

    Yahoo symbols used by this project include ordinary equities (``AAPL``),
    class shares (``BRK.B``), indices (``^VIX``), and rate proxies
    (``^IRX``/``^TNX``), so the allowed alphabet intentionally covers those
    provider identities without accepting whitespace or control characters.
    """

    if not isinstance(raw_ticker, str):
        raise ValueError("ticker must be a string")
    ticker = raw_ticker.strip().upper()
    if not ticker or _CANONICAL_TICKER_PATTERN.fullmatch(ticker) is None:
        raise ValueError(f"ticker is not a canonical provider symbol: {raw_ticker!r}")
    return ticker


def _invalid_bars(ticker: str, error: str) -> DailyBarValidation:
    return DailyBarValidation(
        ticker=ticker,
        usable=False,
        latest_session=None,
        error=error,
    )


def validate_daily_bar_frame(
    ticker: object,
    frame: object,
) -> DailyBarValidation:
    """Validate one provider's daily OHLCV frame without repairing it.

    The index is a sequence of NYSE session *labels*, not arbitrary business
    days or intraday timestamps. It must be strictly ascending and unique.
    Required numeric observations must all be finite; OHLC must be positive
    and internally possible; volume must be non-negative. Rows that are
    entirely absent across all required fields are provider alignment padding
    and are ignored, but a partially populated or otherwise malformed row
    makes the ticker unusable. At least one complete row must remain.
    """

    name = canonical_ticker(ticker)
    if not isinstance(frame, pd.DataFrame):
        return _invalid_bars(name, "provider value is not a DataFrame")
    if frame.empty:
        return _invalid_bars(name, "provider frame has no rows")
    if not frame.columns.is_unique:
        return _invalid_bars(name, "provider frame has duplicate columns")

    missing_columns = [
        column for column in _REQUIRED_OHLCV_COLUMNS if column not in frame.columns
    ]
    if missing_columns:
        return _invalid_bars(
            name,
            "provider frame is missing required columns: "
            + ", ".join(missing_columns),
        )

    index = frame.index
    if not isinstance(index, pd.DatetimeIndex):
        return _invalid_bars(name, "provider frame index must be a DatetimeIndex")
    if index.hasnans:
        return _invalid_bars(name, "provider frame index contains NaT")

    # Daily labels may be timezone-aware. Dropping (rather than converting)
    # the timezone preserves the provider's exchange-local session date.
    local_index = index.tz_localize(None) if index.tz is not None else index
    all_session_index = local_index.normalize()
    if not local_index.equals(all_session_index):
        return _invalid_bars(name, "provider frame index contains intraday timestamps")
    if not all_session_index.is_unique:
        return _invalid_bars(name, "provider frame index contains duplicate sessions")
    if not all_session_index.is_monotonic_increasing:
        return _invalid_bars(name, "provider frame index is not ascending")

    try:
        schedule = _NYSE_CALENDAR.schedule(
            start_date=all_session_index[0].date().isoformat(),
            end_date=all_session_index[-1].date().isoformat(),
        )
    except (OverflowError, TypeError, ValueError):
        return _invalid_bars(name, "provider frame index is outside calendar bounds")
    exchange_sessions = pd.DatetimeIndex(schedule.index).tz_localize(None).normalize()
    non_sessions = all_session_index.difference(exchange_sessions)
    if not non_sessions.empty:
        return _invalid_bars(
            name,
            "provider frame index contains non-NYSE sessions: "
            + ", ".join(value.date().isoformat() for value in non_sessions[:3]),
        )

    # A multi-ticker provider response commonly aligns every symbol to the
    # union of all dates. Fully absent rows are not bars and may be ignored;
    # partially absent bars are malformed and fail below.
    required = frame.loc[:, list(_REQUIRED_OHLCV_COLUMNS)]
    present_mask = ~required.isna().all(axis=1)
    required = required.loc[present_mask]
    if required.empty:
        return _invalid_bars(name, "provider frame has no usable rows")
    usable_session_index = all_session_index[present_mask.to_numpy()]

    contains_boolean = any(
        required[column].map(lambda value: isinstance(value, (bool, np.bool_))).any()
        for column in _REQUIRED_OHLCV_COLUMNS
    )
    if contains_boolean:
        return _invalid_bars(name, "provider frame contains boolean numerics")
    non_numeric_columns = [
        column
        for column in _REQUIRED_OHLCV_COLUMNS
        if (
            not pd.api.types.is_numeric_dtype(required[column].dtype)
            or pd.api.types.is_complex_dtype(required[column].dtype)
        )
    ]
    if non_numeric_columns:
        return _invalid_bars(
            name,
            "provider frame contains non-numeric required columns: "
            + ", ".join(non_numeric_columns),
        )
    numeric = required.apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all():
        return _invalid_bars(name, "provider frame contains non-finite numerics")

    ohlc = numeric.loc[:, ["open", "high", "low", "close"]]
    if (ohlc <= 0).to_numpy().any():
        return _invalid_bars(name, "provider frame contains non-positive OHLC")
    if (numeric["volume"] < 0).any():
        return _invalid_bars(name, "provider frame contains negative volume")

    impossible = (
        (numeric["high"] < numeric["open"])
        | (numeric["high"] < numeric["close"])
        | (numeric["high"] < numeric["low"])
        | (numeric["low"] > numeric["open"])
        | (numeric["low"] > numeric["close"])
    )
    if impossible.any():
        return _invalid_bars(name, "provider frame contains inconsistent OHLC")

    return DailyBarValidation(
        ticker=name,
        usable=True,
        latest_session=usable_session_index[-1].date().isoformat(),
        error=None,
    )


def validated_daily_bar_frame(
    ticker: object,
    frame: object,
) -> tuple[DailyBarValidation, pd.DataFrame | None]:
    """Return validation plus the unmodified usable observations.

    For an already clean frame the same object is returned. The only allowed
    filtering is removal of rows that are absent across every required field,
    which are multi-ticker alignment padding rather than market observations.
    """

    validation = validate_daily_bar_frame(ticker, frame)
    if not validation.usable or not isinstance(frame, pd.DataFrame):
        return validation, None
    required = frame.loc[:, list(_REQUIRED_OHLCV_COLUMNS)]
    present_mask = ~required.isna().all(axis=1)
    if present_mask.all():
        return validation, frame
    return validation, frame.loc[present_mask]


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

    requested = [canonical_ticker(ticker) for ticker in tickers]
    if not requested:
        raise ValueError("tickers must contain at least one ticker")
    if len(set(requested)) != len(requested):
        raise ValueError("tickers must be unique after canonicalization")
    start_date = _trading_session_start_date(lookback_days)
    data: dict[str, pd.DataFrame] = {}

    raw = yf.download(
        tickers=requested,
        start=start_date,
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
    )
    if not isinstance(raw, pd.DataFrame):
        return {}
    if len(requested) > 1 and not isinstance(raw.columns, pd.MultiIndex):
        # A flat multi-symbol response has no trustworthy symbol identity.
        return {}

    for ticker in requested:
        try:
            # yfinance returns MultiIndex (ticker, field) columns with
            # group_by="ticker" regardless of how many tickers were
            # requested — including a single-ticker request — so always
            # index by ticker when that's the shape we got back.
            df = raw[ticker].copy() if isinstance(raw.columns, pd.MultiIndex) else raw.copy()
            df.columns = [c.lower() for c in df.columns]
            candidate = df.tail(lookback_days)
            validation, usable_frame = validated_daily_bar_frame(ticker, candidate)
            if validation.usable and usable_frame is not None:
                # No malformed observation is sorted, deduplicated, filled,
                # coerced, or otherwise repaired into apparent market data.
                data[ticker] = usable_frame
        except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
            # One missing/malformed ticker must not erase usable siblings.
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
    end = pd.Timestamp.today().normalize()
    start = _trading_session_start_date(days, end_date=end)
    dates = pd.DatetimeIndex(
        _NYSE_CALENDAR.schedule(
            start_date=start,
            end_date=end.date().isoformat(),
        ).index
    ).tz_localize(None)[-days:]

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
