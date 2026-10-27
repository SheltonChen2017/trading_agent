"""Caller-supplied GDR calendar and dated reference inputs for offline planning.

Hashes establish byte identity only. These contracts neither discover exchange
sessions nor authenticate vendor provenance, rights, historical availability,
point-in-time status, settlement policy, outcomes, or execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from data.financial_primitives import exact_decimal_multiply, exact_decimal_sum
from data.hashing import hash_bytes
from research.guidance_revision_drift.input_contracts import (
    InputError, amount, canonical_bytes, day, decode_object, digest, identifier,
    keys, utc,
)


NY = ZoneInfo("America/New_York")
PROTECTED_FROM = date(2026, 9, 1)
MAX_CALENDAR_BYTES = 2_097_152
MAX_REFERENCE_BYTES = 4_194_304
MAX_SESSIONS = 10_000
MAX_REFERENCES = 256
MAX_DAILY_BARS = 10_000
_CALENDAR_KEYS = frozenset({
    "schema", "calendar_id", "source_sha256", "covered_from", "covered_through", "sessions",
})
_SESSION_KEYS = frozenset({"date", "open_utc", "close_utc"})
_REFERENCE_BOOK_KEYS = frozenset({"schema", "calendar_sha256", "references", "daily_bars"})
_REFERENCE_KEYS = frozenset({
    "security_id", "issuer_id", "symbol", "exchange", "instrument_type", "primary",
    "sector", "status", "listed_on", "valid_from", "valid_through", "published_at",
    "received_at", "validated_at",
})
_DAILY_BAR_KEYS = frozenset({
    "security_id", "session_date", "raw_close", "volume", "published_at",
    "received_at", "validated_at",
})


class ResearchReferenceError(InputError):
    """Invalid neutral input or unavailable planning date; source values are omitted."""


def _refuse(code: str) -> None:
    raise ResearchReferenceError(code)


def _utc_datetime(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        _refuse("aware_utc_datetime_required")
    return value


def _utc_text(value: datetime) -> str:
    return _utc_datetime(value).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class CalendarSession:
    session_date: date
    open_utc: datetime
    close_utc: datetime

    def __post_init__(self) -> None:
        if type(self.session_date) is not date:
            _refuse("exact_calendar_date_required")
        opening, closing = _utc_datetime(self.open_utc), _utc_datetime(self.close_utc)
        local_open, local_close = opening.astimezone(NY), closing.astimezone(NY)
        if (
            self.session_date.weekday() >= 5
            or local_open.date() != self.session_date
            or local_close.date() != self.session_date
            or local_open.time() != time(9, 30)
            or local_close.time() not in (time(13), time(16))
            or opening >= closing
        ):
            _refuse("invalid_supplied_regular_session")


def _calendar(raw: bytes) -> tuple[dict, tuple[CalendarSession, ...]]:
    try:
        body = keys(decode_object(raw, MAX_CALENDAR_BYTES), _CALENDAR_KEYS)
        if body["schema"] != "gdr.research-calendar.v1" or canonical_bytes(body) != raw:
            _refuse("canonical_research_calendar_required")
        identifier(body["calendar_id"])
        digest(body["source_sha256"])
        first, last = day(body["covered_from"]), day(body["covered_through"])
        if first > last:
            _refuse("inverted_calendar_coverage")
        rows = body["sessions"]
        if type(rows) is not list or not 1 <= len(rows) <= MAX_SESSIONS:
            _refuse("bounded_session_inventory_required")
        sessions = []
        previous = None
        for row in rows:
            row = keys(row, _SESSION_KEYS)
            session = CalendarSession(day(row["date"]), utc(row["open_utc"]), utc(row["close_utc"]))
            if not first <= session.session_date <= last or (
                previous is not None and session.session_date <= previous
            ):
                _refuse("calendar_session_order_or_coverage")
            sessions.append(session)
            previous = session.session_date
        return body, tuple(sessions)
    except ResearchReferenceError:
        raise
    except (InputError, ValueError, TypeError, RecursionError) as exc:
        raise ResearchReferenceError("invalid_research_calendar") from exc


@dataclass(frozen=True, slots=True)
class CalendarInput:
    """Explicit NYSE-shaped regular-session inventory; no holiday inference."""

    canonical_bytes: bytes

    def __post_init__(self) -> None:
        _calendar(self.canonical_bytes)

    @classmethod
    def from_dict(cls, body: dict) -> CalendarInput:
        try:
            return cls(canonical_bytes(body))
        except ResearchReferenceError:
            raise
        except (InputError, ValueError, TypeError, RecursionError) as exc:
            raise ResearchReferenceError("invalid_research_calendar") from exc

    @classmethod
    def from_bytes(cls, raw: bytes) -> CalendarInput:
        return cls(raw)

    def to_dict(self) -> dict:
        return _calendar(self.canonical_bytes)[0]

    @property
    def sha256(self) -> str:
        _calendar(self.canonical_bytes)
        return hash_bytes(self.canonical_bytes)

    @property
    def sessions(self) -> tuple[CalendarSession, ...]:
        return _calendar(self.canonical_bytes)[1]

    def index(self, session_date: date) -> int:
        if type(session_date) is not date:
            _refuse("exact_calendar_date_required")
        for index, session in enumerate(self.sessions):
            if session.session_date == session_date:
                return index
        _refuse("date_not_in_supplied_calendar")

    def cutoff(self, entry_session: date) -> datetime:
        if type(entry_session) is not date or entry_session >= PROTECTED_FROM:
            _refuse("protected_or_invalid_callback_date")
        index = self.index(entry_session)
        if index == 0:
            _refuse("preceding_session_not_supplied")
        previous_day = self.sessions[index - 1].session_date
        return datetime.combine(previous_day, time(18), NY).astimezone(timezone.utc)

    def entry_window(self, published_at: datetime) -> tuple[date, date, date]:
        announced = _utc_datetime(published_at).astimezone(NY).date()
        body = self.to_dict()
        if announced >= PROTECTED_FROM or not day(body["covered_from"]) <= announced <= day(body["covered_through"]):
            _refuse("protected_or_uncovered_announcement")
        after = tuple(session.session_date for session in self.sessions if session.session_date > announced)
        if len(after) < 5 or after[4] >= PROTECTED_FROM:
            _refuse("entry_window_not_within_supplied_unprotected_calendar")
        return after[2], after[3], after[4]

    def time_exit(self, filled_entry_session: date) -> date:
        if type(filled_entry_session) is not date or filled_entry_session >= PROTECTED_FROM:
            _refuse("protected_or_invalid_callback_date")
        target = self.index(filled_entry_session) + 20
        sessions = self.sessions
        if target >= len(sessions) or sessions[target].session_date >= PROTECTED_FROM:
            _refuse("time_exit_not_within_supplied_unprotected_calendar")
        return sessions[target].session_date


def _clocks(row: dict) -> tuple[datetime, datetime, datetime]:
    published, received, validated = (utc(row[name]) for name in (
        "published_at", "received_at", "validated_at"
    ))
    if not published <= received <= validated:
        _refuse("reference_clock_order")
    return published, received, validated


def _reference(row: object) -> dict:
    row = keys(row, _REFERENCE_KEYS)
    for name in ("security_id", "issuer_id", "symbol", "exchange"):
        identifier(row[name])
    if row["sector"] is not None:
        identifier(row["sector"])
    if type(row["primary"]) is not bool:
        _refuse("exact_primary_flag_required")
    if row["instrument_type"] not in ("COMMON_STOCK", "ETF") or row["status"] not in ("listed", "delisted"):
        _refuse("unsupported_reference_type_or_status")
    listed, first, last = (day(row[name]) for name in ("listed_on", "valid_from", "valid_through"))
    if first > last or listed > last:
        _refuse("invalid_reference_validity")
    _clocks(row)
    return row


def _daily_bar(row: object) -> dict:
    row = keys(row, _DAILY_BAR_KEYS)
    identifier(row["security_id"])
    day(row["session_date"])
    if row["raw_close"] is not None:
        if type(row["raw_close"]) is not str:
            _refuse("exact_raw_close_text_required")
        amount(row["raw_close"])
    if row["volume"] is not None and (
        type(row["volume"]) is not int or not 0 <= row["volume"] <= 10**18
    ):
        _refuse("bounded_integral_daily_volume_required")
    _clocks(row)
    return row


def _reference_book(raw: bytes) -> dict:
    try:
        body = keys(decode_object(raw, MAX_REFERENCE_BYTES), _REFERENCE_BOOK_KEYS)
        if body["schema"] != "gdr.research-reference.v1" or canonical_bytes(body) != raw:
            _refuse("canonical_research_reference_required")
        digest(body["calendar_sha256"])
        references, bars = body["references"], body["daily_bars"]
        if (type(references) is not list or len(references) > MAX_REFERENCES
                or type(bars) is not list or len(bars) > MAX_DAILY_BARS):
            _refuse("bounded_reference_and_bar_inventories_required")
        for row in references:
            _reference(row)
        for row in bars:
            _daily_bar(row)
        return body
    except ResearchReferenceError:
        raise
    except (InputError, ValueError, TypeError, RecursionError) as exc:
        raise ResearchReferenceError("invalid_research_reference") from exc


@dataclass(frozen=True, slots=True)
class ReferenceBook:
    """Dated caller assertions, retained without provenance or PIT promotion."""

    canonical_bytes: bytes

    def __post_init__(self) -> None:
        _reference_book(self.canonical_bytes)

    @classmethod
    def from_dict(cls, body: dict) -> ReferenceBook:
        try:
            return cls(canonical_bytes(body))
        except ResearchReferenceError:
            raise
        except (InputError, ValueError, TypeError, RecursionError) as exc:
            raise ResearchReferenceError("invalid_research_reference") from exc

    @classmethod
    def from_bytes(cls, raw: bytes) -> ReferenceBook:
        return cls(raw)

    def to_dict(self) -> dict:
        return _reference_book(self.canonical_bytes)

    @property
    def sha256(self) -> str:
        _reference_book(self.canonical_bytes)
        return hash_bytes(self.canonical_bytes)

    def eligibility(
        self, calendar: CalendarInput, security_id: str, entry_session: date, *, role: str = "stock",
    ) -> dict:
        """Evaluate one as-of opportunity, retaining fixed-code refusals."""
        if type(calendar) is not CalendarInput or type(role) is not str or role not in ("stock", "benchmark"):
            _refuse("exact_calendar_and_role_required")
        identifier(security_id)
        body = self.to_dict()
        if body["calendar_sha256"] != calendar.sha256:
            _refuse("calendar_reference_hash_mismatch")
        cutoff = calendar.cutoff(entry_session)
        index = calendar.index(entry_session)
        reasons = []
        dated = [row for row in body["references"] if row["security_id"] == security_id
                 and day(row["valid_from"]) <= entry_session <= day(row["valid_through"])]
        visible = [row for row in dated if _clocks(row)[0] < cutoff and _clocks(row)[2] <= cutoff]
        reference = visible[0] if len(visible) == 1 else None
        if not dated:
            reasons.append("missing_dated_security_mapping")
        elif not visible:
            reasons.append("reference_unavailable_at_cutoff")
        elif len(visible) != 1:
            reasons.append("ambiguous_dated_security_mapping")
        completed_listing_sessions = None
        if reference is not None:
            if reference["status"] != "listed":
                reasons.append("security_not_listed")
            if role == "stock":
                if reference["exchange"] not in ("NYSE", "NASDAQ", "NYSE_AMERICAN"):
                    reasons.append("ineligible_exchange")
                if reference["instrument_type"] != "COMMON_STOCK" or not reference["primary"]:
                    reasons.append("not_primary_common_share")
                if reference["sector"] is None:
                    reasons.append("missing_dated_sector")
                listed_on = day(reference["listed_on"])
                completed_listing_sessions = sum(
                    listed_on <= session.session_date < entry_session for session in calendar.sessions
                )
                if completed_listing_sessions < 60:
                    reasons.append(
                        "insufficient_listing_schedule_evidence"
                        if listed_on < day(calendar.to_dict()["covered_from"])
                        else "fewer_than_60_completed_listing_sessions"
                    )
            elif reference["symbol"] != "SPY" or reference["instrument_type"] != "ETF":
                reasons.append("benchmark_identity_or_type_mismatch")
        previous_close, adv20 = None, None
        if index < 20:
            reasons.append("insufficient_prior_schedule_sessions")
        else:
            previous = calendar.sessions[index - 20:index]
            selected = {}
            valid_history = True
            for session in previous:
                candidates = [row for row in body["daily_bars"] if row["security_id"] == security_id
                              and day(row["session_date"]) == session.session_date]
                as_of = [row for row in candidates if _clocks(row)[0] < cutoff and _clocks(row)[2] <= cutoff]
                if not candidates:
                    reasons.append("missing_history_session")
                    valid_history = False
                elif not as_of:
                    reasons.append("history_unavailable_at_cutoff")
                    valid_history = False
                elif len(as_of) != 1:
                    reasons.append("ambiguous_history_session")
                    valid_history = False
                else:
                    row = as_of[0]
                    selected[session.session_date] = row
                    if _clocks(row)[0] < session.close_utc:
                        reasons.append("daily_bar_publication_before_session_close")
                        valid_history = False
                    if row["raw_close"] is None or amount(row["raw_close"]) <= 0:
                        reasons.append("missing_or_nonpositive_raw_close")
                        valid_history = False
                    if row["volume"] is None:
                        reasons.append("missing_volume")
                        valid_history = False
            if valid_history:
                last = selected[previous[-1].session_date]
                previous_close = last["raw_close"]
                dollar_total = exact_decimal_sum(
                    exact_decimal_multiply(
                        amount(selected[session.session_date]["raw_close"]),
                        Decimal(selected[session.session_date]["volume"]),
                    )
                    for session in previous
                )
                adv20_amount = exact_decimal_multiply(dollar_total, Decimal("0.05"))
                adv20 = format(adv20_amount, "f")
                if role == "stock":
                    if amount(previous_close) < Decimal("5"):
                        reasons.append("previous_raw_close_below_5")
                    if dollar_total < Decimal("400000000"):
                        reasons.append("adv20_below_20000000")
        return {
            "eligible": not reasons, "reasons": list(dict.fromkeys(reasons)),
            "issuer_id": reference["issuer_id"] if reference else None,
            "sector": reference["sector"] if reference else None,
            "symbol": reference["symbol"] if reference else None,
            "previous_close": previous_close, "adv20": adv20,
            "completed_listing_sessions": completed_listing_sessions,
            "cutoff": _utc_text(cutoff), "reference_sha256": self.sha256,
            "calendar_sha256": calendar.sha256,
            "provenance_verified": False, "source_rights_verified": False,
            "calendar_verified": False, "point_in_time_data": False,
            "execution_authority": False,
        }
