"""Synthetic-only normalized guidance and deterministic event replay.

This is not a vendor decoder, evidence verifier, data collector, or order
authorizer. SYN-* identities and the synthetic schema make the fixture scope
explicit; a content hash proves consistency, never provenance or availability.
Replay retains every observation and never rewrites an earlier decision.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from data.financial_primitives import exact_decimal_add
from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.formulas import (
    GuidanceRange, RangeRevisionEvaluation, evaluate_range_revisions,
)

MAX_DISCLOSURE_BYTES = 32_768
MAX_EVENTS = 256
_ID = re.compile(r"SYN-[A-Za-z0-9_-]{1,60}\Z")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_DECIMAL = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_PERIOD_KEYS = frozenset((
    "fiscal_year", "fiscal_start", "fiscal_end", "period", "currency",
    "revenue_units", "eps_units", "revenue_basis", "eps_basis",
    "adjustment_definition", "share_basis", "scope", "revenue", "eps",
))
_DISCLOSURE_KEYS = frozenset((
    "schema", "issuer_id", "disclosure_id", "version", "kind", "published_at",
    "received_at", "validated_at", "supersedes", "release_type", "positioning",
    "periods", "metadata",
))


class EventError(ValueError):
    """Malformed fixture contract, ambiguous replay, or resource limit."""


def _fail_number(_: str) -> None:
    raise EventError("JSON floats and nonfinite numbers are forbidden")


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EventError("duplicate JSON key")
        result[key] = value
    return result


def decode_fixture_object(raw: bytes, maximum: int) -> dict[str, object]:
    """Strict bounded JSON decoder shared only with the fixture archive."""
    if type(raw) is not bytes or not raw or len(raw) > maximum:
        raise EventError("fixture must be nonempty bounded bytes")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                            parse_float=_fail_number, parse_constant=_fail_number)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise EventError("fixture must be strict UTF-8 JSON") from exc
    if type(result) is not dict:
        raise EventError("fixture root must be an object")
    return result


def _keys(value: object, expected: frozenset[str], name: str) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise EventError(f"{name} has missing or unknown fields")
    return value


def _text(value: object, name: str, maximum: int = 80) -> str:
    if type(value) is not str or not 1 <= len(value) <= maximum:
        raise EventError(f"{name} must be bounded nonempty text")
    if not value.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise EventError(f"{name} contains unsupported text")
    return value


def _identifier(value: object) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise EventError("fixture identity must be SYN-* text")
    return value


def _date(value: object) -> date:
    if type(value) is not str or not _DATE.fullmatch(value):
        raise EventError("date must be canonical YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise EventError("invalid calendar date") from exc


def _utc(value: object) -> datetime:
    if type(value) is not str or not _UTC.fullmatch(value):
        raise EventError("timestamp must be explicit canonical UTC ending Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EventError("invalid UTC timestamp") from exc


def _range(value: object) -> GuidanceRange:
    values = _keys(value, frozenset(("lower", "upper", "kind")), "guidance range")
    if values["kind"] not in ("point", "range"):
        raise EventError("range kind must explicitly be point or range")
    endpoints = []
    for key in ("lower", "upper"):
        endpoint = values[key]
        if type(endpoint) is not str or len(endpoint) > 260 or not _DECIMAL.fullmatch(endpoint):
            raise EventError("bounds must be bounded exact non-exponent decimal text")
        endpoints.append(Decimal(endpoint))
    try:
        result = GuidanceRange(*endpoints)
    except ValueError as exc:
        raise EventError("invalid guidance range") from exc
    if (result.lower == result.upper) != (values["kind"] == "point"):
        raise EventError("equal bounds require explicit point guidance; ranges require two bounds")
    return result


@dataclass(frozen=True, slots=True)
class GuidancePeriod:
    """Immutable normalized fixture-period bytes; projections are fresh."""

    canonical_bytes: bytes

    def __post_init__(self) -> None:
        values = _keys(decode_fixture_object(self.canonical_bytes, 8_192), _PERIOD_KEYS, "period")
        if canonical_json(values).encode() != self.canonical_bytes:
            raise EventError("period requires canonical bytes")
        if type(values["fiscal_year"]) is not int or not 1900 <= values["fiscal_year"] <= 2100:
            raise EventError("fiscal year must be an integer")
        start, end = _date(values["fiscal_start"]), _date(values["fiscal_end"])
        if not start < end or not 1 <= (end - start).days <= 400:
            raise EventError("invalid fiscal interval")
        for key in _PERIOD_KEYS - {"fiscal_year", "fiscal_start", "fiscal_end", "revenue", "eps"}:
            _text(values[key], key)
        _range(values["revenue"])
        _range(values["eps"])

    @classmethod
    def from_dict(cls, values: dict) -> GuidancePeriod:
        _keys(values, _PERIOD_KEYS, "period")
        try:
            return cls(canonical_json(values).encode("utf-8"))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise EventError("invalid period") from exc

    def to_dict(self) -> dict:
        return decode_fixture_object(self.canonical_bytes, 8_192)

    @property
    def fiscal_year(self) -> int:
        return self.to_dict()["fiscal_year"]

    @property
    def fiscal_end(self) -> date:
        return _date(self.to_dict()["fiscal_end"])

    @property
    def revenue(self) -> GuidanceRange:
        return _range(self.to_dict()["revenue"])

    @property
    def eps(self) -> GuidanceRange:
        return _range(self.to_dict()["eps"])


@dataclass(frozen=True, slots=True)
class NormalizedDisclosure:
    """Synthetic semantic fixture, explicitly not a provider/PIT attestation."""

    canonical_bytes: bytes

    def __post_init__(self) -> None:
        values = _keys(decode_fixture_object(self.canonical_bytes, MAX_DISCLOSURE_BYTES),
                       _DISCLOSURE_KEYS, "disclosure")
        if canonical_json(values).encode() != self.canonical_bytes:
            raise EventError("disclosure requires canonical bytes")
        if values["schema"] != "gdr.synthetic.disclosure.v1":
            raise EventError("only the synthetic disclosure schema is supported")
        _identifier(values["issuer_id"])
        _identifier(values["disclosure_id"])
        if type(values["version"]) is not int or not 1 <= values["version"] <= MAX_EVENTS:
            raise EventError("version must be a bounded positive integer")
        if values["kind"] not in ("disclosure", "correction", "withdrawal"):
            raise EventError("unsupported event kind")
        clocks = tuple(_utc(values[key]) for key in ("published_at", "received_at", "validated_at"))
        if not clocks[0] <= clocks[1] <= clocks[2]:
            raise EventError("publication, receipt and validation must be ordered")
        # These explicitly artificial clocks cannot be loaded as protected-date
        # fixtures or silently repurposed for a current vendor archive.
        if any(clock.year not in (2024, 2025) for clock in clocks):
            raise EventError("this fixture contract supports only synthetic 2024/2025 clocks")
        if values["kind"] == "disclosure":
            if values["supersedes"] is not None:
                raise EventError("new management disclosures cannot supersede a record")
        else:
            _identifier(values["supersedes"])
        if values["release_type"] not in ("official", "preliminary"):
            raise EventError("unsupported release type")
        if values["positioning"] not in ("primary", "secondary"):
            raise EventError("unsupported positioning")
        _text(values["metadata"], "metadata", 512)
        periods = values["periods"]
        if type(periods) is not list or len(periods) > 8:
            raise EventError("periods must be a bounded list")
        if bool(periods) != (values["kind"] != "withdrawal"):
            raise EventError("only a withdrawal has no guidance periods")
        parsed = tuple(GuidancePeriod.from_dict(period) for period in periods)
        identities = [(period.to_dict()["period"], period.fiscal_year) for period in parsed]
        if len(set(identities)) != len(identities):
            raise EventError("ambiguous duplicate fiscal-period identity")
        if identities != sorted(identities):
            raise EventError("periods must be sorted by period then fiscal year")

    @classmethod
    def from_dict(cls, values: dict) -> NormalizedDisclosure:
        _keys(values, _DISCLOSURE_KEYS, "disclosure")
        try:
            return cls(canonical_json(values).encode("utf-8"))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise EventError("invalid normalized synthetic disclosure") from exc

    @classmethod
    def from_bytes(cls, raw: bytes) -> NormalizedDisclosure:
        return cls.from_dict(decode_fixture_object(raw, MAX_DISCLOSURE_BYTES))

    def to_dict(self) -> dict:
        return decode_fixture_object(self.canonical_bytes, MAX_DISCLOSURE_BYTES)

    @property
    def sha256(self) -> str:
        return hash_bytes(self.canonical_bytes)

    @property
    def issuer_id(self) -> str:
        return self.to_dict()["issuer_id"]

    @property
    def disclosure_id(self) -> str:
        return self.to_dict()["disclosure_id"]

    @property
    def published_at(self) -> datetime:
        return _utc(self.to_dict()["published_at"])

    @property
    def received_at(self) -> datetime:
        return _utc(self.to_dict()["received_at"])

    @property
    def validated_at(self) -> datetime:
        return _utc(self.to_dict()["validated_at"])

    @property
    def periods(self) -> tuple[GuidancePeriod, ...]:
        return tuple(GuidancePeriod.from_dict(period) for period in self.to_dict()["periods"])


def _checked(record: object) -> NormalizedDisclosure:
    if type(record) is not NormalizedDisclosure:
        raise EventError("expected an exact NormalizedDisclosure")
    return NormalizedDisclosure(record.canonical_bytes)


def _nearest(record: NormalizedDisclosure) -> GuidancePeriod | None:
    announcement_date = record.published_at.astimezone(ZoneInfo("America/New_York")).date()
    periods = [period for period in record.periods
               if period.to_dict()["period"] == "FY" and period.fiscal_end >= announcement_date]
    return min(periods, key=lambda value: value.fiscal_end) if periods else None


def _same_year(record: NormalizedDisclosure, current: GuidancePeriod) -> GuidancePeriod | None:
    return next((period for period in record.periods
                 if period.to_dict()["period"] == "FY" and period.fiscal_year == current.fiscal_year), None)


def _economic_refusals(current: NormalizedDisclosure, previous: NormalizedDisclosure,
                       current_period: GuidancePeriod, previous_period: GuidancePeriod) -> tuple[str, ...]:
    reasons = []
    old, new = previous_period.to_dict(), current_period.to_dict()
    if current.issuer_id != previous.issuer_id:
        reasons.append("different_permanent_issuer")
    for name in sorted(_PERIOD_KEYS - {"revenue", "eps"}):
        if old[name] != new[name]:
            reasons.append("changed_" + name)
    for name, expected in (("period", "FY"), ("currency", "USD"), ("revenue_basis", "gaap"),
                           ("eps_basis", "adj"), ("revenue_units", "USD_millions"),
                           ("eps_units", "USD_per_share")):
        if old[name] != expected or new[name] != expected:
            reasons.append("unsupported_" + name)
    if any(record.to_dict()["positioning"] != "primary" for record in (current, previous)):
        reasons.append("not_primary_guidance")
    return tuple(reasons)


def _comparison_refusals(current: NormalizedDisclosure, previous: NormalizedDisclosure,
                         current_period: GuidancePeriod, previous_period: GuidancePeriod) -> tuple[str, ...]:
    """Positive entries require an immutable predecessor captured before news."""
    reasons = list(_economic_refusals(current, previous, current_period, previous_period))
    if previous.published_at >= current.published_at:
        reasons.append("predecessor_not_earlier_disclosure")
    if previous.validated_at >= current.published_at:
        reasons.append("predecessor_not_captured_before_disclosure")
    return tuple(reasons)


@dataclass(frozen=True, slots=True)
class EventCandidate:
    """A synthetic event match, never proof of universe, timing, or authority."""

    previous: NormalizedDisclosure
    current: NormalizedDisclosure

    def __post_init__(self) -> None:
        object.__setattr__(self, "previous", _checked(self.previous))
        object.__setattr__(self, "current", _checked(self.current))
        current_period = _nearest(self.current)
        previous_period = _same_year(self.previous, current_period) if current_period else None
        if current_period is None or previous_period is None:
            raise EventError("candidate has no same-period predecessor")
        if self.current.to_dict()["kind"] != "disclosure":
            raise EventError("corrections cannot create candidates")
        if _comparison_refusals(self.current, self.previous, current_period, previous_period):
            raise EventError("candidate inputs are incomparable")
        if not self.arithmetic.passes_arithmetic:
            raise EventError("candidate fails range arithmetic")

    @property
    def current_period(self) -> GuidancePeriod:
        return _nearest(_checked(self.current))

    @property
    def previous_period(self) -> GuidancePeriod:
        return _same_year(_checked(self.previous), self.current_period)

    @property
    def arithmetic(self) -> RangeRevisionEvaluation:
        return evaluate_range_revisions(previous_revenue=self.previous_period.revenue,
            current_revenue=self.current_period.revenue, previous_eps=self.previous_period.eps,
            current_eps=self.current_period.eps)

    @property
    def issuer_id(self) -> str:
        return self.current.issuer_id

    @property
    def disclosure_id(self) -> str:
        return self.current.disclosure_id

    @property
    def fiscal_end(self) -> date:
        return self.current_period.fiscal_end

    @property
    def published_at(self) -> datetime:
        return self.current.published_at

    @property
    def received_at(self) -> datetime:
        return self.current.received_at

    @property
    def validated_at(self) -> datetime:
        return self.current.validated_at


@dataclass(frozen=True, slots=True)
class EventDecision:
    record_sha256: str
    disposition: str
    refusal_reasons: tuple[str, ...] = ()
    candidate: EventCandidate | None = None
    invalidated_disclosure_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.record_sha256) is not str or not _HASH.fullmatch(self.record_sha256):
            raise EventError("decision requires a normalized record hash")
        if self.disposition not in ("duplicate", "metadata_edit", "quarantined", "refused",
                                     "correction", "withdrawal", "bootstrap", "baseline", "candidate"):
            raise EventError("unsupported event disposition")
        if type(self.refusal_reasons) is not tuple or len(self.refusal_reasons) > 64:
            raise EventError("decision reasons must be a bounded tuple")
        for reason in self.refusal_reasons:
            _text(reason, "refusal reason")
        if type(self.invalidated_disclosure_ids) is not tuple or len(self.invalidated_disclosure_ids) > MAX_EVENTS:
            raise EventError("invalidated identities must be a bounded tuple")
        for identity in self.invalidated_disclosure_ids:
            _identifier(identity)
        if tuple(sorted(set(self.invalidated_disclosure_ids))) != self.invalidated_disclosure_ids:
            raise EventError("invalidated identities must be sorted and unique")
        if (self.candidate is not None) != (self.disposition == "candidate"):
            raise EventError("only a candidate disposition can contain a candidate")
        if self.candidate is not None:
            if type(self.candidate) is not EventCandidate or self.refusal_reasons:
                raise EventError("candidate decision has invalid inputs")
            checked = EventCandidate(self.candidate.previous, self.candidate.current)
            if checked.current.sha256 != self.record_sha256:
                raise EventError("candidate decision differs from its source hash")
            object.__setattr__(self, "candidate", checked)


def _economics(record: NormalizedDisclosure) -> bytes:
    values = record.to_dict()
    for name in ("version", "received_at", "validated_at", "metadata"):
        del values[name]
    return canonical_json(values).encode()


def _midpoint_cut(old: GuidancePeriod, new: GuidancePeriod) -> bool:
    return any(exact_decimal_add(after.lower, after.upper) < exact_decimal_add(before.lower, before.upper)
               for before, after in ((old.revenue, new.revenue), (old.eps, new.eps)))


def _replay(entries: tuple[tuple[NormalizedDisclosure, bool], ...]) -> tuple[EventDecision, ...]:
    seen: dict[tuple[str, int], NormalizedDisclosure] = {}
    latest_version: dict[str, NormalizedDisclosure] = {}
    # Original publication controls management-disclosure order even when an
    # effective predecessor is later corrected. We never cherry-pick an older
    # comparable disclosure around a newer same-period basis change.
    originals: dict[str, NormalizedDisclosure] = {}
    effective: dict[str, NormalizedDisclosure] = {}
    quarantined: set[str] = set()
    withdrawn: set[str] = set()
    active: dict[str, EventCandidate] = {}
    decisions: list[EventDecision] = []
    last_clock = datetime(2024, 1, 1, tzinfo=timezone.utc)
    normal_started = False
    for record, bootstrap in entries:
        record = _checked(record)
        values, identity = record.to_dict(), record.disclosure_id
        if type(bootstrap) is not bool:
            raise EventError("bootstrap must be a strict boolean")
        if bootstrap and normal_started:
            raise EventError("bootstrap is permitted only during the initial contiguous baseline")
        normal_started |= not bootstrap
        key = (identity, values["version"])
        existing = seen.get(key)
        if existing is not None and existing.canonical_bytes == record.canonical_bytes:
            decisions.append(EventDecision(record.sha256, "duplicate"))
            continue
        if record.validated_at < last_clock:
            raise EventError("replay must follow nondecreasing validation instants")
        last_clock = record.validated_at
        invalidated: list[str] = []
        conflict = existing is not None
        prior_version = latest_version.get(identity)
        if prior_version is not None:
            conflict |= record.issuer_id != prior_version.issuer_id
            conflict |= values["version"] != prior_version.to_dict()["version"] + 1
            if values["kind"] == "disclosure":
                if not conflict and _economics(prior_version) == _economics(record):
                    seen[key], latest_version[identity] = record, record
                    decisions.append(EventDecision(record.sha256, "metadata_edit"))
                    continue
                conflict = True
        elif values["version"] != 1:
            conflict = True
        if conflict:
            affected = {record.issuer_id}
            if prior_version is not None:
                affected.add(prior_version.issuer_id)
            quarantined.update(affected)
            invalidated = sorted(name for name, candidate in active.items() if candidate.issuer_id in affected)
            for name in invalidated:
                del active[name]
            decisions.append(EventDecision(record.sha256, "quarantined", ("conflicting_disclosure_version",),
                                           invalidated_disclosure_ids=tuple(invalidated)))
            continue
        seen[key], latest_version[identity] = record, record
        if record.issuer_id in quarantined:
            decisions.append(EventDecision(record.sha256, "refused", ("issuer_quarantined",)))
            continue
        if values["kind"] in ("correction", "withdrawal"):
            target = values["supersedes"]
            original = originals.get(target)
            if original is None or original.issuer_id != record.issuer_id:
                decisions.append(EventDecision(record.sha256, "refused", ("unknown_or_wrong_issuer_superseded_disclosure",)))
                continue
            if record.published_at <= original.published_at:
                decisions.append(EventDecision(record.sha256, "refused", ("correction_not_later_than_original",)))
                continue
            # Conservatively invalidate all candidates whose own source or
            # predecessor is touched. Corrections can only reduce authority;
            # they never create/re-time a positive candidate.
            invalidated = sorted(name for name, candidate in active.items()
                if name == target or candidate.previous.disclosure_id in (target, effective[target].disclosure_id))
            for name in invalidated:
                del active[name]
            if values["kind"] == "withdrawal":
                withdrawn.add(target)
            elif target not in withdrawn:
                effective[target] = record
            decisions.append(EventDecision(record.sha256, values["kind"],
                invalidated_disclosure_ids=tuple(invalidated)))
            continue
        same_issuer = [old for old in originals.values() if old.issuer_id == record.issuer_id]
        # Late-discovered management releases remain in the observation ledger
        # but cannot overwrite a more recent baseline or become fresh news.
        if any(old.published_at == record.published_at for old in same_issuer):
            quarantined.add(record.issuer_id)
            invalidated = sorted(name for name, candidate in active.items() if candidate.issuer_id == record.issuer_id)
            for name in invalidated:
                del active[name]
            decisions.append(EventDecision(record.sha256, "quarantined", ("simultaneous_disclosure_identity_ambiguous",),
                                           invalidated_disclosure_ids=tuple(invalidated)))
            continue
        if any(old.published_at > record.published_at for old in same_issuer):
            reasons = ("simultaneous_or_late_discovered_disclosure",)
            decisions.append(EventDecision(record.sha256, "refused", reasons))
            continue
        period = _nearest(record)
        originals[identity], effective[identity] = record, record
        if bootstrap:
            decisions.append(EventDecision(record.sha256, "bootstrap"))
            continue
        # Risk invalidation is independent of the new-entry predecessor and
        # nearest-FY selection. An old held FY can be cut in the same disclosure
        # that introduces the next FY, and an incompatible immediate entry
        # predecessor must not hide a comparable cut to an existing position.
        for name, candidate in tuple(active.items()):
            if candidate.issuer_id != record.issuer_id:
                continue
            updated_period = _same_year(record, candidate.current_period)
            # A later published cut becomes risk information when received,
            # even if our receipt of the original raise was delayed until
            # after that cut's publication. Positive-entry capture constraints
            # must not suppress this risk reduction once both inputs are known.
            if updated_period is not None and candidate.current.published_at < record.published_at and not _economic_refusals(
                record, candidate.current, updated_period, candidate.current_period
            ) and _midpoint_cut(candidate.current_period, updated_period):
                invalidated.append(name)
                del active[name]
        if period is None:
            decisions.append(EventDecision(record.sha256, "refused", ("no_unexpired_full_year",),
                invalidated_disclosure_ids=tuple(sorted(invalidated))))
            continue
        preceding = [old for old in same_issuer if _same_year(old, period) is not None]
        if not preceding:
            decisions.append(EventDecision(record.sha256, "baseline", ("no_same_period_predecessor",),
                invalidated_disclosure_ids=tuple(sorted(invalidated))))
            continue
        original_previous = max(preceding, key=lambda old: old.published_at)
        if original_previous.disclosure_id in withdrawn:
            decisions.append(EventDecision(record.sha256, "refused", ("immediate_predecessor_withdrawn",),
                invalidated_disclosure_ids=tuple(sorted(invalidated))))
            continue
        previous = effective[original_previous.disclosure_id]
        previous_period = _same_year(previous, period)
        if previous_period is None:
            decisions.append(EventDecision(record.sha256, "refused", ("corrected_predecessor_lost_period",),
                invalidated_disclosure_ids=tuple(sorted(invalidated))))
            continue
        reasons = _comparison_refusals(record, previous, period, previous_period)
        if not reasons:
            arithmetic = evaluate_range_revisions(previous_revenue=previous_period.revenue,
                current_revenue=period.revenue, previous_eps=previous_period.eps, current_eps=period.eps)
            reasons = arithmetic.refusal_reasons
        candidate = EventCandidate(previous, record) if not reasons else None
        if candidate is not None:
            active[identity] = candidate
        decisions.append(EventDecision(record.sha256, "candidate" if candidate else "refused", reasons,
            candidate, tuple(sorted(invalidated))))
    return tuple(decisions)


@dataclass(frozen=True, slots=True)
class EventBook:
    """Bounded immutable replay input; every boundary revalidates all records."""

    entries: tuple[tuple[NormalizedDisclosure, bool], ...] = ()

    def __post_init__(self) -> None:
        if type(self.entries) is not tuple or len(self.entries) > MAX_EVENTS:
            raise EventError("event book requires a bounded tuple")
        normalized = []
        for entry in self.entries:
            if type(entry) is not tuple or len(entry) != 2:
                raise EventError("event-book entry must be a record/bootstrap pair")
            normalized.append((_checked(entry[0]), entry[1]))
        object.__setattr__(self, "entries", tuple(normalized))
        _replay(self.entries)

    def ingest(self, record: NormalizedDisclosure, *, bootstrap: bool = False) -> EventBook:
        checked = EventBook(self.entries)
        return EventBook(checked.entries + ((_checked(record), bootstrap),))

    @property
    def decisions(self) -> tuple[EventDecision, ...]:
        checked = EventBook(self.entries)
        return _replay(checked.entries)
