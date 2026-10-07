"""Offline proposed GDR clocks over an explicitly pinned synthetic schedule.

No calendar is fetched or inferred from weekdays. A hash identifies the supplied
schedule, not its correctness against an exchange or its historical availability.
All results remain synthetic observations, never execution authorization.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from zoneinfo import ZoneInfo

from data.hashing import hash_payload
from research.guidance_revision_drift.formulas import _bounded_decimal


NY = ZoneInfo("America/New_York")
REQUIRED_INPUT_NAMES = ("payload", "predecessor", "mapping", "sector", "history")


class TimingError(ValueError):
    """Malformed synthetic clock or incomplete pinned schedule."""


def _date(value: object, name: str) -> date:
    if type(value) is not date:
        raise TimingError(f"{name} must be an exact date")
    return value


def _utc(value: object, name: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise TimingError(f"{name} must be an aware UTC datetime")
    return value


def _name(value: object, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 200:
        raise TimingError(f"{name} must be a nonempty bounded string")
    return value


@dataclass(frozen=True, slots=True)
class Session:
    session_date: date
    open_utc: datetime
    close_utc: datetime

    def __post_init__(self) -> None:
        _date(self.session_date, "session_date")
        local_open = _utc(self.open_utc, "open_utc").astimezone(NY)
        local_close = _utc(self.close_utc, "close_utc").astimezone(NY)
        if (local_open.date() != self.session_date or local_close.date() != self.session_date
                or self.session_date.weekday() >= 5 or local_open.time() != time(9, 30)
                or not time(10, 5) <= local_close.time() <= time(16)):
            raise TimingError("session must contain regular 09:30 open and 10:00/10:05 opportunities")


@dataclass(frozen=True, slots=True)
class PinnedSchedule:
    sessions: tuple[Session, ...]
    covered_from: date
    covered_through: date
    schedule_id: str
    provenance: str = "synthetic_fixture"
    exchange: str = "NYSE"
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        self._validate()
        object.__setattr__(self, "sha256", hash_payload(self._payload()))

    def _validate(self) -> None:
        _date(self.covered_from, "covered_from")
        _date(self.covered_through, "covered_through")
        _name(self.schedule_id, "schedule_id")
        if self.provenance != "synthetic_fixture" or self.exchange != "NYSE":
            raise TimingError("only explicitly synthetic NYSE schedule fixtures are supported")
        if type(self.sessions) is not tuple or not 1 <= len(self.sessions) <= 10000:
            raise TimingError("sessions must be a nonempty bounded immutable tuple")
        prior = None
        for session in self.sessions:
            if type(session) is not Session:
                raise TimingError("sessions must contain exact Session objects")
            Session.__post_init__(session)
            if not self.covered_from <= session.session_date <= self.covered_through:
                raise TimingError("session lies outside declared schedule coverage")
            if prior is not None and session.session_date <= prior:
                raise TimingError("sessions must be unique and strictly chronological")
            prior = session.session_date

    def _payload(self) -> dict:
        return {"schema": "gdr.synthetic_schedule.v1", "schedule_id": self.schedule_id,
                "provenance": self.provenance, "exchange": self.exchange,
                "covered_from": self.covered_from.isoformat(),
                "covered_through": self.covered_through.isoformat(),
                "sessions": [{"date": s.session_date.isoformat(), "open": s.open_utc.isoformat(),
                              "close": s.close_utc.isoformat()} for s in self.sessions]}

    def validate(self) -> None:
        self._validate()
        if hash_payload(self._payload()) != self.sha256:
            raise TimingError("pinned schedule content has changed")

    def index(self, session_date: date) -> int:
        self.validate()
        _date(session_date, "session_date")
        for index, session in enumerate(self.sessions):
            if session.session_date == session_date:
                return index
        raise TimingError("date is not a session in the pinned schedule")


def decision_cutoff(schedule: PinnedSchedule, entry_session: date) -> datetime:
    if type(schedule) is not PinnedSchedule:
        raise TimingError("schedule must be an exact PinnedSchedule")
    index = schedule.index(entry_session)
    if index == 0:
        raise TimingError("preceding session is outside pinned schedule")
    return datetime.combine(schedule.sessions[index - 1].session_date, time(18), NY).astimezone(timezone.utc)


def execution_times(schedule: PinnedSchedule, entry_session: date) -> tuple[datetime, datetime]:
    schedule.index(entry_session)
    return tuple(datetime.combine(entry_session, t, NY).astimezone(timezone.utc)
                 for t in (time(10), time(10, 5)))


def entry_window(schedule: PinnedSchedule, announcement_date: date) -> tuple[date, date, date]:
    """Return E/E+1/E+2: D+3 is counted strictly after D, including holiday D."""
    schedule.validate()
    _date(announcement_date, "announcement_date")
    if not schedule.covered_from <= announcement_date <= schedule.covered_through:
        raise TimingError("announcement lies outside pinned schedule coverage")
    after = tuple(s.session_date for s in schedule.sessions if s.session_date > announcement_date)
    if len(after) < 5:
        raise TimingError("E through E+2 are outside pinned schedule coverage")
    opportunities = after[2:5]
    for opportunity in opportunities:
        decision_cutoff(schedule, opportunity)
    return opportunities


def time_exit_session(schedule: PinnedSchedule, filled_entry_session: date) -> date:
    """Twenty session-to-session intervals means session 21, not session 20."""
    index = schedule.index(filled_entry_session) + 20
    if index >= len(schedule.sessions):
        raise TimingError("time exit lies outside pinned schedule; do not extend evidence access")
    return schedule.sessions[index].session_date


@dataclass(frozen=True, slots=True)
class Availability:
    name: str
    published_at: datetime | None
    received_at: datetime | None
    ingested_at: datetime | None

    def __post_init__(self) -> None:
        _name(self.name, "availability name")
        for name in ("published_at", "received_at", "ingested_at"):
            value = getattr(self, name)
            if value is not None:
                _utc(value, name)


def availability_refusals(value: Availability, cutoff: datetime) -> tuple[str, ...]:
    """Validate all three supplied clocks; timestamps are not PIT proof."""
    if type(value) is not Availability:
        raise TimingError("availability must be an exact Availability")
    Availability.__post_init__(value)
    _utc(cutoff, "cutoff")
    reasons = []
    for name in ("published_at", "received_at", "ingested_at"):
        timestamp = getattr(value, name)
        if timestamp is None:
            reasons.append(f"{value.name}:missing_{name}")
        elif name == "published_at" and timestamp == cutoff:
            reasons.append(f"{value.name}:publication_must_precede_cutoff")
        elif timestamp > cutoff:
            reasons.append(f"{value.name}:{name}_after_cutoff")
    if (value.published_at is not None and value.received_at is not None
            and value.published_at > value.received_at):
        reasons.append(f"{value.name}:publication_after_receipt")
    if (value.received_at is not None and value.ingested_at is not None
            and value.received_at > value.ingested_at):
        reasons.append(f"{value.name}:receipt_after_ingestion")
    return tuple(reasons)


def historical_update_refusals(last_update: datetime | date | None, cutoff: datetime) -> tuple[str, ...]:
    """Conservative historical censor only; a pass cannot establish PIT status."""
    _utc(cutoff, "cutoff")
    if last_update is None:
        return ("missing_historical_last_update",)
    if type(last_update) is date:
        return () if last_update < cutoff.astimezone(NY).date() else ("date_only_update_not_strictly_before_cutoff_date",)
    if type(last_update) is datetime:
        if last_update.tzinfo is None or last_update.utcoffset() is None:
            raise TimingError("historical update requires an explicit UTC offset")
        return () if last_update <= cutoff else ("historical_update_after_cutoff",)
    raise TimingError("historical update must be date, offset datetime, or missing")


@dataclass(frozen=True, slots=True)
class TimingDecision:
    opportunity_sessions: tuple[date, ...]
    eligible_session: date | None
    cutoff: datetime | None
    refusal_reasons: tuple[str, ...]
    missed_opportunities: tuple[tuple[date, tuple[str, ...]], ...]
    schedule_sha256: str
    point_in_time_data: bool = field(default=False, init=False)
    execution_authorized: bool = field(default=False, init=False)


def select_entry_opportunity(
    schedule: PinnedSchedule, announcement_date: date | None, inputs: tuple[Availability, ...],
    *, attempt_already_made: bool = False,
) -> TimingDecision:
    """Find first clock-eligible synthetic opportunity; no retry after an attempt.

    Required baseline names cannot be removed by a caller. Every additional
    supplied input is also enforced. Ambiguous dates must be resolved upstream
    to their later defensible date; an absent date refuses without guessing.
    """
    schedule.validate()
    if type(inputs) is not tuple or type(attempt_already_made) is not bool:
        raise TimingError("inputs must be immutable and attempt flag an exact bool")
    by_name = {}
    for value in inputs:
        if type(value) is not Availability:
            raise TimingError("inputs must contain exact Availability objects")
        Availability.__post_init__(value)
        if value.name in by_name:
            raise TimingError("duplicate availability input names")
        by_name[value.name] = value
    if announcement_date is None:
        return TimingDecision((), None, None, ("unresolved_announcement_date",), (), schedule.sha256)
    opportunities = entry_window(schedule, announcement_date)
    payload = by_name.get("payload")
    if payload is not None and payload.published_at is not None and payload.published_at.astimezone(NY).date() > announcement_date:
        return TimingDecision(opportunities, None, None, ("announcement_precedes_publication_date",), (), schedule.sha256)
    if attempt_already_made:
        return TimingDecision(opportunities, None, None, ("entry_attempt_already_consumed",), (), schedule.sha256)
    missing = tuple(f"missing_required_input:{name}" for name in REQUIRED_INPUT_NAMES if name not in by_name)
    missed = []
    for opportunity in opportunities:
        cutoff = decision_cutoff(schedule, opportunity)
        reasons = missing + tuple(reason for name in sorted(by_name)
                                  for reason in availability_refusals(by_name[name], cutoff))
        if not reasons:
            return TimingDecision(opportunities, opportunity, cutoff, (), tuple(missed), schedule.sha256)
        missed.append((opportunity, reasons))
    final = list(missed[-1][1])
    if payload is not None and payload.received_at is not None and payload.received_at > decision_cutoff(schedule, opportunities[-1]):
        final.append("stale_event")
    return TimingDecision(opportunities, None, None, tuple(final), tuple(missed), schedule.sha256)


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    event_id: str
    permanent_security_id: str
    eligible_session: date
    previous_revenue_sum: Decimal
    current_revenue_sum: Decimal
    previous_eps_sum: Decimal
    current_eps_sum: Decimal

    def __post_init__(self) -> None:
        _name(self.event_id, "event_id")
        _name(self.permanent_security_id, "permanent_security_id")
        _date(self.eligible_session, "eligible_session")
        for name in ("previous_revenue_sum", "current_revenue_sum", "previous_eps_sum", "current_eps_sum"):
            _bounded_decimal(getattr(self, name), name)
        if self.previous_revenue_sum <= 0 or self.previous_eps_sum < Decimal("0.50"):
            raise TimingError("ranking requires positive revenue and the prior EPS midpoint floor")


def rank_candidates(candidates: tuple[RankedCandidate, ...]) -> tuple[RankedCandidate, ...]:
    """Exact rational ordering; rounded 28-digit display ratios are never used."""
    if type(candidates) is not tuple:
        raise TimingError("candidates must be an immutable tuple")
    identities = set()
    for candidate in candidates:
        if type(candidate) is not RankedCandidate:
            raise TimingError("candidates must contain exact RankedCandidate objects")
        RankedCandidate.__post_init__(candidate)
        if candidate.permanent_security_id in identities:
            raise TimingError("duplicate security candidates require prior event-identity resolution")
        identities.add(candidate.permanent_security_id)
    return tuple(sorted(candidates, key=lambda c: (
        c.eligible_session,
        -Fraction(c.current_revenue_sum) / Fraction(c.previous_revenue_sum),
        -Fraction(c.current_eps_sum) / Fraction(c.previous_eps_sum),
        c.permanent_security_id,
    )))
