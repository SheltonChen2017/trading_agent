"""Pure, bounded, in-memory TPR-D1 synthetic-fixture normalization candidate.

No loader, publication, provider, price/outcome join, or trading path exists.
Caller-supplied clocks, calendar opens and SYNTHETIC labels are fixture inputs,
not authenticated data provenance or verified canonical 18:00 New York timing.
Synthetic evidence does not establish vendor facts or point-in-time admission.
Only exact same-currency, compatible raw targets are compared; no repair,
score, percentage revision, FX/split/ADR adjustment or money authority exists.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

_AUTHORITY = (("canonical_admission", False), ("point_in_time_data", False),
              ("outcomes", False), ("qc", False), ("trading", False))
# Explicit fixture units only; no FX, entitlement or vendor semantics follow.
_FIXTURE_CURRENCIES = frozenset({"USD", "CAD", "EUR", "GBP", "CHF", "JPY", "AUD", "CNY", "HKD"})
_HEADERS = {"event_id", "version_id", "version_available_at_utc", "payload"}
_PAYLOAD = {
    "effective_date", "public_precision", "public_available_at_utc", "public_available_date",
    "public_evidence_id", "compatibility_evidence_id", "ingested_at_utc", "action",
    "new_target", "prior_target", "new_security_id", "prior_security_id",
    "new_share_class_id", "prior_share_class_id", "new_currency", "prior_currency",
    "new_horizon", "prior_horizon", "new_basis", "prior_basis",
    "new_adjustment_vintage", "prior_adjustment_vintage",
}


class FixtureNormalizationError(ValueError):
    """Malformed fixture framing; messages never include caller values."""


@dataclass(frozen=True)
class VersionDisposition:
    event_id: str
    version_id: str
    version_available_at_utc: str
    status: str
    reasons: tuple[str, ...]
    occurrences: int


@dataclass(frozen=True)
class NormalizedFixtureEvent:
    event_id: str
    version_id: str
    security_id: str
    share_class_id: str
    currency: str
    horizon: str
    basis: str
    adjustment_vintage: str
    new_target: str
    prior_target: str
    direction: int
    effective_date: str
    public_available_at_utc: str | None
    public_available_date: str | None
    version_available_at_utc: str
    ingested_at_utc: str
    eligible_open_utc: str


@dataclass(frozen=True)
class FixtureBatchResult:
    input_versions: int
    duplicate_versions: int
    dispositions: tuple[VersionDisposition, ...]
    selected_events: tuple[NormalizedFixtureEvent, ...]
    mode: str = "synthetic-fixture-only"
    authority: tuple[tuple[str, bool], ...] = _AUTHORITY


def _synthetic(value: Any) -> bool:
    return type(value) is str and len(value) <= 128 and re.fullmatch(r"SYNTHETIC-[A-Z0-9][A-Z0-9_-]*", value) is not None


def _utc(value: Any) -> datetime:
    if type(value) is not str or len(value) > 64:
        raise FixtureNormalizationError("invalid synthetic clock")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise FixtureNormalizationError("invalid synthetic clock") from None


def _day(value: Any) -> date:
    try:
        if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise FixtureNormalizationError("invalid synthetic date") from None


def _calendar(sessions: Any) -> tuple[tuple[date, datetime], ...]:
    if type(sessions) not in (tuple, list) or len(sessions) > 3660:
        raise FixtureNormalizationError("invalid synthetic calendar")
    result = []
    try:
        for item in sessions:
            if type(item) is not dict or len(item) != 2 or any(type(key) is not str for key in item) or set(item) != {"session_date", "open_utc"}:
                raise ValueError
            day, opened = _day(item["session_date"]), _utc(item["open_utc"])
            if opened.date() != day or (result and (day <= result[-1][0] or opened <= result[-1][1])):
                raise ValueError
            result.append((day, opened))
    except (ValueError, FixtureNormalizationError):
        raise FixtureNormalizationError("invalid synthetic calendar") from None
    return tuple(result)


def _target(payload: dict[str, Any], name: str) -> tuple[Decimal | None, str | None]:
    value = payload.get(name)
    if value is None:
        return None, "missing_" + name
    if type(value) is not str or not value or len(value) > 128 or value != value.strip():
        return None, "invalid_" + name
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None, "invalid_" + name
    if not number.is_finite():
        return None, "nonfinite_" + name
    if re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value) is None:
        return None, "invalid_" + name
    if number.is_zero():
        return None, "zero_" + name
    if number < 0:
        return None, "negative_" + name
    return number, None


def _signature(payload: Any) -> tuple | None:
    """Compare visible flat fixtures only, without interpreting financial data."""
    if type(payload) is not dict or len(payload) > 64 or any(type(k) is not str or len(k) > 128 for k in payload):
        return None
    result = []
    for key in sorted(payload):
        value = payload[key]
        if type(value) is str and len(value) <= 256:
            encoded = value
        elif value is None or type(value) is bool:
            encoded = str(value)
        elif type(value) is int and value.bit_length() <= 1024:
            encoded = str(value)
        elif type(value) is float:
            encoded = value.hex()
        else:
            return None
        result.append((key, type(value).__name__, encoded))
    return tuple(result)


def _select(record: dict, cutoff: datetime, calendar: tuple) -> tuple[str, tuple[str, ...], NormalizedFixtureEvent | None]:
    def refuse(reason: str, status: str = "refused"):
        return status, (reason,), None
    p = record["payload"]
    # Primitive admission precedes comparisons; caller objects are not evaluated.
    if _signature(p) is None or len(p) > len(_PAYLOAD) or not set(p) <= _PAYLOAD or not (_PAYLOAD - {"new_target", "prior_target"}) <= set(p):
        return refuse("invalid_payload")
    if p["action"] == "withdraws":
        return refuse("visible_withdrawal")
    try:
        effective = _day(p["effective_date"])
        ingested = _utc(p["ingested_at_utc"])
    except FixtureNormalizationError:
        return refuse("invalid_payload_clock")
    if ingested > cutoff:
        return refuse("uncaptured_by_cutoff")
    # Conservative public-only fixture proposal, not proven vendor ordering.
    if record["available"] > ingested:
        return refuse("contradictory_availability_clocks")
    if not _synthetic(p["public_evidence_id"]):
        return refuse("missing_public_evidence")
    if not _synthetic(p["compatibility_evidence_id"]):
        return refuse("missing_compatibility_evidence")
    public = public_day = None
    try:
        if p["public_precision"] == "instant" and p["public_available_date"] is None:
            public = _utc(p["public_available_at_utc"])
            if public > cutoff:
                return refuse("public_unavailable_by_cutoff")
            if public > record["available"] or public > ingested:
                return refuse("contradictory_availability_clocks")
        elif p["public_precision"] == "date-only" and p["public_available_at_utc"] is None:
            public_day = _day(p["public_available_date"])
            if public_day > cutoff.date():
                return refuse("public_unavailable_by_cutoff")
            # Explicit UTC-day fixture proposal; not verified market clock semantics.
            if public_day > record["available"].date() or public_day > ingested.date():
                return refuse("contradictory_availability_clocks")
        else:
            return refuse("invalid_public_precision")
    except FixtureNormalizationError:
        return refuse("invalid_public_clock")
    new_number, error = _target(p, "new_target")
    if error:
        return refuse(error)
    prior_number, prior_error = _target(p, "prior_target")
    if p["action"] in ("sets", "announces"):
        return refuse("initiation_without_prior" if prior_error else "initiation_not_revision", "ineligible")
    for field, reason in (("security_id", "security_identity"), ("share_class_id", "share_class"),
                          ("currency", "currency"), ("horizon", "horizon"),
                          ("basis", "basis"), ("adjustment_vintage", "adjustment_vintage")):
        new, prior = p["new_" + field], p["prior_" + field]
        if new is None or prior is None:
            return refuse("missing_" + reason)
        if type(new) is not str or type(prior) is not str or not new or not prior:
            return refuse("invalid_" + reason)
        if new != prior:
            return refuse(reason + "_mismatch")
        if field == "currency":
            valid = new in _FIXTURE_CURRENCIES
        elif field == "basis":
            valid = new == "raw"
        elif field == "horizon":
            valid = re.fullmatch(r"SYNTHETIC-[1-9][0-9]{0,2}-MONTH", new) is not None
        elif field == "adjustment_vintage":
            valid = new == "SYNTHETIC-NO-ADJUSTMENT"
        else:
            valid = _synthetic(new)
        if not valid:
            return refuse("invalid_" + reason)
    if prior_error:
        return refuse(prior_error)
    direction = (new_number > prior_number) - (new_number < prior_number)
    expected = {"raises": 1, "lowers": -1, "maintains": 0}
    if type(p["action"]) is not str or p["action"] not in expected:
        return refuse("unsupported_action")
    if direction != expected[p["action"]]:
        return refuse("action_direction_conflict")
    threshold = max(cutoff, record["available"], ingested, public or cutoff)
    minimum = None
    if public_day is not None:
        later = [opened for day, opened in calendar if day > public_day]
        if len(later) < 2:
            return refuse("insufficient_calendar")
        minimum = later[1]
    opened = next((opened for _, opened in calendar if opened > threshold and (minimum is None or opened >= minimum)), None)
    if opened is None:
        return refuse("insufficient_calendar")
    event = NormalizedFixtureEvent(
        record["event_id"], record["version_id"], p["new_security_id"], p["new_share_class_id"],
        p["new_currency"], p["new_horizon"], "raw", p["new_adjustment_vintage"],
        format(new_number, "f"), format(prior_number, "f"), direction, effective.isoformat(),
        public.isoformat() if public else None, public_day.isoformat() if public_day else None,
        record["available"].isoformat(), ingested.isoformat(), opened.isoformat(),
    )
    return "selected", (("valid_zero",) if direction == 0 else ()), event


def normalize_fixture_events(versions: Any, *, decision_cutoff_utc: str, sessions: Any) -> FixtureBatchResult:
    """Normalize at most 1,024 explicitly supplied fixture versions, no I/O.

    Visibility screens version headers before payload inspection. A latest
    visible bad/withdrawn/uncaptured version blocks fallback. Visible exact
    duplicates collapse with occurrence counts; future payloads are untouched
    and their occurrences remain separate. Every framed input is accounted.
    The synthetic cutoff/calendar do not prove canonical or market timing.
    """
    cutoff, calendar = _utc(decision_cutoff_utc), _calendar(sessions)
    if type(versions) not in (tuple, list) or len(versions) > 1024:
        raise FixtureNormalizationError("invalid synthetic version batch")
    visible, future = [], []
    groups = {}
    for index, item in enumerate(versions):
        if type(item) is not dict or len(item) != len(_HEADERS) or any(type(key) is not str for key in item) or set(item) != _HEADERS or not all(_synthetic(item[k]) for k in ("event_id", "version_id")):
            raise FixtureNormalizationError("invalid synthetic version header")
        available = _utc(item["version_available_at_utc"])
        record = {"event_id": item["event_id"], "version_id": item["version_id"], "available": available, "occurrences": 1}
        if available > cutoff:
            future.append(record)
            continue
        payload = item["payload"]
        signature = _signature(payload)
        key = (record["event_id"], record["version_id"], available, signature if signature is not None else index)
        if key in groups:
            groups[key]["occurrences"] += 1
        else:
            record["payload"] = dict(payload) if type(payload) is dict and len(payload) <= 64 else payload
            groups[key] = record
            visible.append(record)
    dispositions, selected = [], []
    for record in future:
        dispositions.append(VersionDisposition(record["event_id"], record["version_id"], record["available"].isoformat(), "not_visible", ("version_after_cutoff",), 1))
    for event_id in sorted({r["event_id"] for r in visible}):
        records = [r for r in visible if r["event_id"] == event_id]
        conflict = len({r["version_id"] for r in records}) != len(records) or len({r["available"] for r in records}) != len(records)
        latest = max(records, key=lambda r: r["available"])
        for record in records:
            if conflict:
                status, reasons, event = "refused", ("lineage_conflict",), None
            elif record is not latest:
                status, reasons, event = "superseded", (), None
            else:
                status, reasons, event = _select(record, cutoff, calendar)
            if event is not None:
                selected.append(event)
            dispositions.append(VersionDisposition(event_id, record["version_id"], record["available"].isoformat(), status, reasons, record["occurrences"]))
    dispositions.sort(key=lambda d: (d.event_id, d.version_id, d.version_available_at_utc, d.status, d.reasons, d.occurrences))
    return FixtureBatchResult(len(versions), sum(r["occurrences"] - 1 for r in visible), tuple(dispositions), tuple(sorted(selected, key=lambda e: (e.event_id, e.version_id))))
