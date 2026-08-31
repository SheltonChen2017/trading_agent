"""Point-in-time availability rules for Analyst Revisions V2 events."""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone
from enum import Enum

from data.exchange_calendar import (
    ExchangeCalendarError,
    next_session_open_strictly_after,
    resolve_nth_session_after,
    session_open_instant,
)


class AvailabilityError(ValueError):
    """Timing evidence is ambiguous, inconsistent, or noncanonical."""


class AvailabilityQuality(str, Enum):
    EXACT_PUBLIC_INSTANT = "exact_public_instant"
    DATE_ONLY_TWO_SESSION_DELAY = "date_only_two_session_delay"


@dataclasses.dataclass(frozen=True)
class EligibleAvailability:
    public_at: str | None
    public_date: str
    eligible_at: str
    eligible_session: str
    quality: AvailabilityQuality
    evidence_id: str


def _canonical_instant(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AvailabilityError(f"{name} must be a canonical aware ISO-8601 instant")
    if value.endswith("Z"):
        candidate = value[:-1] + "+00:00"
    else:
        candidate = value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise AvailabilityError(f"{name} must be a canonical aware ISO-8601 instant") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AvailabilityError(f"{name} must be timezone-aware")
    canonical = parsed.isoformat()
    if value not in {canonical, canonical.replace("+00:00", "Z")}:
        raise AvailabilityError(f"{name} must use canonical ISO-8601 spelling")
    return parsed.astimezone(timezone.utc)


def _canonical_date(value: object, name: str) -> date:
    if not isinstance(value, str):
        raise AvailabilityError(f"{name} must use canonical YYYY-MM-DD format")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise AvailabilityError(f"{name} must use canonical YYYY-MM-DD format") from exc
    if parsed.isoformat() != value:
        raise AvailabilityError(f"{name} must use canonical YYYY-MM-DD format")
    return parsed


def derive_event_availability(
    *,
    evidence_id: str,
    public_at: str | None = None,
    public_date: str | None = None,
) -> EligibleAvailability:
    """Derive the only session in which an event may first enter a signal.

    Exact clock evidence uses the first market open strictly after the public
    instant. Date-only evidence uses the literal blueprint rule: the second
    exchange session strictly after the stated date. The two evidence forms
    are mutually exclusive so a caller cannot silently downgrade a bad clock
    to the less conservative legacy rule.
    """
    if not isinstance(evidence_id, str) or not evidence_id or evidence_id != evidence_id.strip():
        raise AvailabilityError("evidence_id must be a canonical non-empty string")
    if (public_at is None) == (public_date is None):
        raise AvailabilityError("provide exactly one of public_at or public_date")
    try:
        if public_at is not None:
            public = _canonical_instant(public_at, "public_at")
            session, market_open = next_session_open_strictly_after(public)
            return EligibleAvailability(
                public_at=public_at,
                public_date=public.date().isoformat(),
                eligible_at=market_open.astimezone(timezone.utc).isoformat(),
                eligible_session=session,
                quality=AvailabilityQuality.EXACT_PUBLIC_INSTANT,
                evidence_id=evidence_id,
            )
        parsed_date = _canonical_date(public_date, "public_date")
        session = resolve_nth_session_after(parsed_date.isoformat(), 2)
        market_open = session_open_instant(session)
        return EligibleAvailability(
            public_at=None,
            public_date=parsed_date.isoformat(),
            eligible_at=market_open.astimezone(timezone.utc).isoformat(),
            eligible_session=session,
            quality=AvailabilityQuality.DATE_ONLY_TWO_SESSION_DELAY,
            evidence_id=evidence_id,
        )
    except ExchangeCalendarError as exc:
        raise AvailabilityError(str(exc)) from exc


def prove_timing_order(
    *,
    effective_at: str,
    provider_published_at: str,
    available_at: str,
    ingested_at: str,
) -> None:
    """Refuse rows whose four point-in-time clocks cannot coexist."""
    effective = _canonical_instant(effective_at, "effective_at")
    published = _canonical_instant(provider_published_at, "provider_published_at")
    available = _canonical_instant(available_at, "available_at")
    ingested = _canonical_instant(ingested_at, "ingested_at")
    if effective > published:
        raise AvailabilityError("effective_at cannot follow provider_published_at")
    if published > available:
        raise AvailabilityError("provider_published_at cannot follow available_at")
    if available > ingested:
        raise AvailabilityError("available_at cannot follow ingested_at")
