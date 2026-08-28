"""Authoritative US-equity exchange-session and close-time primitives.

This module is deliberately product-neutral. Research contracts, durable
storage, and the ML shadow scheduler all import the same functions so a
"session horizon" cannot mean calendar days at one boundary and NYSE sessions
at another. Every timestamp is an exchange-calendar close, including holidays,
half days, daylight-saving transitions, and weekend gaps.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import pandas_market_calendars as mcal

_NYSE = mcal.get_calendar("NYSE")
_EASTERN = "America/New_York"
# pandas-market-calendars can synthesize schedules arbitrarily far into the
# past or future.  That is useful library behaviour, but it is not evidence
# that an extreme date belongs to this project's operating horizon.  Bound the
# authority surface explicitly: 1990 retains the intended modern-history
# research window, while 2035 covers the pinned 2,000-session horizon through
# 2034.  This is an input-safety policy, not a claim that every session in the
# interval was independently audited; moving either edge requires review.
SUPPORTED_SESSION_START = date(1990, 1, 1)
SUPPORTED_SESSION_END = date(2035, 12, 31)


class ExchangeCalendarError(ValueError):
    """A date or horizon cannot be proved against the exchange calendar."""


def _require_supported_date(value: date, name: str) -> date:
    if type(value) is not date:
        raise ExchangeCalendarError(f"{name} must be a calendar date")
    if value < SUPPORTED_SESSION_START or value > SUPPORTED_SESSION_END:
        raise ExchangeCalendarError(
            f"{name} falls outside the configured project authority range "
            f"{SUPPORTED_SESSION_START.isoformat()}..{SUPPORTED_SESSION_END.isoformat()}"
        )
    return value


def parse_session_date(value: Any, name: str = "session") -> date:
    if type(value) is not str:
        raise ExchangeCalendarError(f"{name} must use canonical YYYY-MM-DD format")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ExchangeCalendarError(
            f"{name} must use canonical YYYY-MM-DD format"
        ) from exc
    if parsed.isoformat() != value:
        raise ExchangeCalendarError(f"{name} must use canonical YYYY-MM-DD format")
    return _require_supported_date(parsed, name)


def _schedule(start: date, end: date) -> pd.DataFrame:
    start = _require_supported_date(start, "start")
    end = _require_supported_date(end, "end")
    if end < start:
        raise ExchangeCalendarError("end must not precede start")
    return _NYSE.schedule(start_date=start.isoformat(), end_date=end.isoformat())


def trading_sessions(start: date, end: date) -> tuple[date, ...]:
    """Real NYSE sessions in the inclusive interval ``[start, end]``."""
    start = _require_supported_date(start, "start")
    end = _require_supported_date(end, "end")
    if end < start:
        raise ExchangeCalendarError("end must not precede start")
    schedule = _schedule(start, end)
    return tuple(pd.DatetimeIndex(schedule.index).date)


def is_trading_session(session: str) -> bool:
    target = parse_session_date(session, "session")
    return target in trading_sessions(target, target)


def session_close_instant(session: str) -> datetime:
    """Return the session's actual close as a timezone-aware UTC instant."""
    target = parse_session_date(session, "session")
    schedule = _schedule(target, target)
    if schedule.empty:
        raise ExchangeCalendarError(f"{session} is not an NYSE trading session")
    close = pd.Timestamp(schedule.iloc[0]["market_close"])
    if close.tzinfo is None:
        close = close.tz_localize(_EASTERN)
    return close.tz_convert("UTC").to_pydatetime()


def session_open_instant(session: str) -> datetime:
    """Return the session's actual open as a timezone-aware UTC instant."""
    target = parse_session_date(session, "session")
    schedule = _schedule(target, target)
    if schedule.empty:
        raise ExchangeCalendarError(f"{session} is not an NYSE trading session")
    market_open = pd.Timestamp(schedule.iloc[0]["market_open"])
    if market_open.tzinfo is None:
        market_open = market_open.tz_localize(_EASTERN)
    return market_open.tz_convert("UTC").to_pydatetime()


def resolve_nth_session_after(anchor_date: str, count: int) -> str:
    """Return the ``count``-th NYSE session strictly after a calendar date."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ExchangeCalendarError("count must be a positive integer")
    anchor = parse_session_date(anchor_date, "anchor_date")
    horizon_days = max(count * 3, count + 30)
    try:
        requested_end = anchor + timedelta(days=horizon_days)
        start = anchor + timedelta(days=1)
    except OverflowError as exc:
        raise ExchangeCalendarError("session search exceeds representable dates") from exc
    # The conservative calendar-day over-fetch can extend well beyond the
    # actual target session.  Clamp the query, not the requested session count,
    # so a target inside the authority range remains resolvable while a target
    # beyond it still fails on insufficient covered sessions.
    end = min(requested_end, SUPPORTED_SESSION_END)
    sessions = trading_sessions(start, end)
    if len(sessions) < count:
        raise ExchangeCalendarError(
            f"exchange calendar does not cover {count} sessions after {anchor_date}"
        )
    return sessions[count - 1].isoformat()


def next_session_open_strictly_after(instant: datetime) -> tuple[str, datetime]:
    """Return the first NYSE session/open whose open is strictly after ``instant``."""
    if not isinstance(instant, datetime) or instant.tzinfo is None:
        raise ExchangeCalendarError("instant must be a timezone-aware datetime")
    try:
        if instant.utcoffset() is None:
            raise ExchangeCalendarError("instant must be a timezone-aware datetime")
        instant_utc = instant.astimezone(timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError) as exc:
        raise ExchangeCalendarError(
            "instant must be a representable timezone-aware datetime"
        ) from exc
    anchor = _require_supported_date(instant_utc.date(), "instant")
    try:
        requested_end = anchor + timedelta(days=31)
        requested_start = anchor - timedelta(days=1)
    except OverflowError as exc:
        raise ExchangeCalendarError("session search exceeds representable dates") from exc
    start = max(requested_start, SUPPORTED_SESSION_START)
    end = min(requested_end, SUPPORTED_SESSION_END)
    for session in trading_sessions(start, end):
        session_text = session.isoformat()
        market_open = session_open_instant(session_text)
        if market_open > instant_utc:
            return session_text, market_open
    raise ExchangeCalendarError("exchange calendar cannot resolve a later session open")


def resolve_decision_cutoff(as_of_session: str) -> str:
    return session_close_instant(as_of_session).isoformat()


def resolve_target_session(as_of_session: str, horizon_sessions: int) -> str:
    """Resolve exactly ``horizon_sessions`` NYSE sessions after ``as_of``."""
    if (
        isinstance(horizon_sessions, bool)
        or not isinstance(horizon_sessions, int)
        or horizon_sessions < 1
    ):
        raise ExchangeCalendarError("horizon_sessions must be a positive integer")
    start = parse_session_date(as_of_session, "as_of_session")
    horizon_days = max(horizon_sessions * 3, horizon_sessions + 30)
    try:
        requested_window_end = start + timedelta(days=horizon_days)
    except OverflowError as exc:
        raise ExchangeCalendarError(
            f"horizon_sessions={horizon_sessions} extends beyond representable "
            "dates; no exchange calendar can cover it"
        ) from exc
    window_end = min(requested_window_end, SUPPORTED_SESSION_END)
    sessions = trading_sessions(start, window_end)
    if not sessions or sessions[0] != start:
        raise ExchangeCalendarError(
            f"{as_of_session} is not an NYSE trading session"
        )
    if len(sessions) <= horizon_sessions:
        raise ExchangeCalendarError(
            f"exchange calendar does not yet cover {horizon_sessions} sessions "
            f"after {as_of_session}"
        )
    return sessions[horizon_sessions].isoformat()


def resolve_target_availability(as_of_session: str, horizon_sessions: int) -> str:
    """Return the actual close when a session-horizon target is observable."""
    return session_close_instant(
        resolve_target_session(as_of_session, horizon_sessions)
    ).isoformat()
