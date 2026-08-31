"""Strict, outcome-free contracts for official short-interest snapshots."""
from __future__ import annotations

import dataclasses
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from enum import Enum
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from data.financial_primitives import decimal_text
from data.hashing import hash_payload

SCHEMA_VERSION = "1.0"
DAYS_TO_COVER_DECIMAL_PLACES = 12
_DTC_QUANTUM = Decimal(1).scaleb(-DAYS_TO_COVER_DECIMAL_PLACES)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_EASTERN = ZoneInfo("America/New_York")


class ShortInterestContractError(ValueError):
    """A source, identity, release, or snapshot contract failed closed."""


class SourceSemantic(str, Enum):
    OFFICIAL_OPEN_SHORT_POSITION_SNAPSHOT = (
        "official_open_short_position_snapshot"
    )


class SourceEntitlement(str, Enum):
    SYNTHETIC_FIXTURE_ONLY = "synthetic_fixture_only"
    LICENSED_HISTORICAL_VINTAGE = "licensed_historical_vintage"
    OFFICIAL_PUBLICATION_CALENDAR = "official_publication_calendar"


class ReleasePrecision(str, Enum):
    EXACT_TIMESTAMP = "exact_timestamp"
    DATE_ONLY = "date_only"


class DenominatorKind(str, Enum):
    POINT_IN_TIME_FLOAT = "point_in_time_float"
    POINT_IN_TIME_SHARES_OUTSTANDING = "point_in_time_shares_outstanding"


def _required_text(value: Any, name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ShortInterestContractError(
            f"{name} must be a non-empty canonical string"
        )
    return value


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, name)


def _canonical_date(value: Any, name: str) -> date:
    text = _required_text(value, name)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ShortInterestContractError(
            f"{name} must use canonical YYYY-MM-DD format"
        ) from exc
    if parsed.isoformat() != text:
        raise ShortInterestContractError(
            f"{name} must use canonical YYYY-MM-DD format"
        )
    return parsed


def parse_utc_timestamp(value: Any, name: str) -> datetime:
    """Parse one canonical UTC timestamp; local/naive times are forbidden."""
    text = _required_text(value, name)
    if not text.endswith("Z"):
        raise ShortInterestContractError(f"{name} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(f"{text[:-1]}+00:00")
    except ValueError as exc:
        raise ShortInterestContractError(
            f"{name} must be a canonical UTC timestamp"
        ) from exc
    canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed) or canonical != text:
        raise ShortInterestContractError(f"{name} must be a canonical UTC timestamp")
    return parsed


def format_utc_timestamp(value: datetime) -> str:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ShortInterestContractError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(value: Any, name: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ShortInterestContractError(
            f"{name} must be one lowercase 64-character sha256 digest"
        )
    return value


def _git_commit(value: Any, name: str) -> str:
    if type(value) is not str or _GIT_COMMIT_RE.fullmatch(value) is None:
        raise ShortInterestContractError(
            f"{name} must be one lowercase 40- or 64-character git commit"
        )
    return value


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ShortInterestContractError(
            f"{name} must be an exact integer >= {minimum}"
        )
    return value


def _decimal_text(value: Any, name: str, *, positive: bool) -> str:
    if type(value) is not str:
        raise ShortInterestContractError(
            f"{name} must be an exact canonical decimal string; "
            "JSON numbers are refused"
        )
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ShortInterestContractError(
            f"{name} must be a canonical finite decimal string"
        ) from None
    if not parsed.is_finite() or (parsed <= 0 if positive else parsed < 0):
        qualifier = "positive" if positive else "non-negative"
        raise ShortInterestContractError(
            f"{name} must be a canonical finite {qualifier} decimal string"
        )
    canonical = decimal_text(parsed)
    if canonical != value:
        raise ShortInterestContractError(
            f"{name} must be canonical decimal text {canonical!r}"
        )
    return value


def _enum(value: Any, enum_type: type[Enum], name: str) -> Enum:
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        supported = [item.value for item in enum_type]
        raise ShortInterestContractError(
            f"{name} must be one of {supported}, got {value!r}"
        ) from None


def _payload_fields(
    contract_type: type[Any], payload: Mapping[str, Any]
) -> dict[str, Any]:
    name = contract_type.__name__
    if not isinstance(payload, Mapping):
        raise ShortInterestContractError(f"{name} payload must be a JSON object")
    fields = {field.name for field in dataclasses.fields(contract_type)}
    unknown = set(payload) - fields
    missing = {
        field.name
        for field in dataclasses.fields(contract_type)
        if field.default is dataclasses.MISSING
        and field.default_factory is dataclasses.MISSING
        and field.name not in payload
    }
    if unknown or missing:
        raise ShortInterestContractError(
            f"{name} fields mismatch; missing={sorted(missing)}, "
            f"unknown={sorted(unknown, key=str)}"
        )
    return dict(payload)


@dataclasses.dataclass(frozen=True)
class CollectionManifest:
    source_dataset_id: str
    snapshot_name: str
    source_id: str
    source_version: str
    endpoint_schema_version: str
    semantic: SourceSemantic
    entitlement: SourceEntitlement
    retrieved_at: str
    settlement_start: str
    settlement_end: str
    requested_record_count: int
    input_row_count: int
    accepted_record_count: int
    refusal_count: int
    raw_artifact_sha256: str
    collector_git_commit: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "source_dataset_id",
            "snapshot_name",
            "source_id",
            "source_version",
            "endpoint_schema_version",
        ):
            _required_text(getattr(self, name), name)
        if type(self.schema_version) is not str or self.schema_version != SCHEMA_VERSION:
            raise ShortInterestContractError(
                f"unsupported CollectionManifest schema_version {self.schema_version!r}"
            )
        if self.semantic is not SourceSemantic.OFFICIAL_OPEN_SHORT_POSITION_SNAPSHOT:
            raise ShortInterestContractError(
                "collection semantic must be official open short-position snapshots"
            )
        if not isinstance(self.entitlement, SourceEntitlement):
            raise ShortInterestContractError("entitlement must be a SourceEntitlement")
        parse_utc_timestamp(self.retrieved_at, "retrieved_at")
        start = _canonical_date(self.settlement_start, "settlement_start")
        end = _canonical_date(self.settlement_end, "settlement_end")
        if end < start:
            raise ShortInterestContractError(
                "settlement_end must not precede settlement_start"
            )
        requested = _integer(
            self.requested_record_count, "requested_record_count"
        )
        input_count = _integer(self.input_row_count, "input_row_count")
        accepted = _integer(self.accepted_record_count, "accepted_record_count")
        refused = _integer(self.refusal_count, "refusal_count")
        if input_count > requested:
            raise ShortInterestContractError(
                "input_row_count must not exceed requested_record_count"
            )
        if accepted + refused != input_count:
            raise ShortInterestContractError(
                "accepted_record_count + refusal_count must equal input_row_count"
            )
        _sha256(self.raw_artifact_sha256, "raw_artifact_sha256")
        _git_commit(self.collector_git_commit, "collector_git_commit")

    def to_payload(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["semantic"] = self.semantic.value
        payload["entitlement"] = self.entitlement.value
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "CollectionManifest":
        values = _payload_fields(cls, payload)
        values["semantic"] = _enum(values.get("semantic"), SourceSemantic, "semantic")
        values["entitlement"] = _enum(
            values.get("entitlement"), SourceEntitlement, "entitlement"
        )
        return cls(**values)

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


@dataclasses.dataclass(frozen=True)
class SecurityIdentity:
    security_id: str
    vendor_security_id: str
    qc_symbol: str | None
    ticker: str
    share_class: str
    primary_venue: str
    country: str
    security_type: str
    valid_from: str
    valid_to: str | None
    predecessor_security_id: str | None
    successor_security_id: str | None
    identity_source_id: str
    identity_source_version: str
    raw_record_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "security_id",
            "vendor_security_id",
            "ticker",
            "share_class",
            "primary_venue",
            "country",
            "security_type",
            "identity_source_id",
            "identity_source_version",
        ):
            _required_text(getattr(self, name), name)
        for name in (
            "qc_symbol",
            "predecessor_security_id",
            "successor_security_id",
        ):
            _optional_text(getattr(self, name), name)
        if self.ticker != self.ticker.upper():
            raise ShortInterestContractError("ticker must be canonical uppercase")
        for name in ("primary_venue", "country", "security_type"):
            if getattr(self, name) != getattr(self, name).upper():
                raise ShortInterestContractError(f"{name} must be canonical uppercase")
        for link_name in ("predecessor_security_id", "successor_security_id"):
            if getattr(self, link_name) == self.security_id:
                raise ShortInterestContractError(
                    f"{link_name} must not point to the same security_id"
                )
        start = _canonical_date(self.valid_from, "valid_from")
        if self.valid_to is not None:
            end = _canonical_date(self.valid_to, "valid_to")
            if end < start:
                raise ShortInterestContractError(
                    "valid_to must not precede valid_from"
                )
        _sha256(self.raw_record_sha256, "raw_record_sha256")

    def valid_on(self, session: str) -> bool:
        target = _canonical_date(session, "session")
        if target < _canonical_date(self.valid_from, "valid_from"):
            return False
        return self.valid_to is None or target <= _canonical_date(
            self.valid_to, "valid_to"
        )

    def to_payload(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "SecurityIdentity":
        return cls(**_payload_fields(cls, payload))


@dataclasses.dataclass(frozen=True)
class ReleaseCalendarEntry:
    calendar_id: str
    settlement_date: str
    filing_deadline_date: str | None
    public_release_date: str
    public_release_at: str | None
    precision: ReleasePrecision
    source_id: str
    source_version: str
    evidence_sha256: str
    observed_at: str
    execution_calendar: str = "XNYS"

    def __post_init__(self) -> None:
        for name in ("calendar_id", "source_id", "source_version"):
            _required_text(getattr(self, name), name)
        settlement = _canonical_date(self.settlement_date, "settlement_date")
        release_date = _canonical_date(self.public_release_date, "public_release_date")
        if release_date <= settlement:
            raise ShortInterestContractError(
                "public_release_date must strictly follow settlement_date"
            )
        if self.filing_deadline_date is not None:
            deadline = _canonical_date(
                self.filing_deadline_date, "filing_deadline_date"
            )
            if deadline < settlement or deadline > release_date:
                raise ShortInterestContractError(
                    "filing_deadline_date must be between settlement and publication"
                )
        if not isinstance(self.precision, ReleasePrecision):
            raise ShortInterestContractError("precision must be a ReleasePrecision")
        observed = parse_utc_timestamp(self.observed_at, "observed_at")
        if self.precision is ReleasePrecision.EXACT_TIMESTAMP:
            if self.public_release_at is None:
                raise ShortInterestContractError(
                    "exact_timestamp release requires public_release_at"
                )
            published = parse_utc_timestamp(
                self.public_release_at, "public_release_at"
            )
            if published.astimezone(_EASTERN).date() != release_date:
                raise ShortInterestContractError(
                    "public_release_at Eastern date must match public_release_date"
                )
            if observed < published:
                raise ShortInterestContractError(
                    "observed_at must not precede public_release_at"
                )
        elif self.public_release_at is not None:
            raise ShortInterestContractError(
                "date_only release must not invent public_release_at"
            )
        if observed.astimezone(_EASTERN).date() < release_date:
            raise ShortInterestContractError(
                "observed_at must not precede public_release_date"
            )
        if self.execution_calendar != "XNYS":
            raise ShortInterestContractError("the frozen execution_calendar is XNYS")
        _sha256(self.evidence_sha256, "evidence_sha256")

    @property
    def key(self) -> str:
        return f"{self.calendar_id}:{self.settlement_date}"

    def to_payload(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["precision"] = self.precision.value
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ReleaseCalendarEntry":
        values = _payload_fields(cls, payload)
        values["precision"] = _enum(
            values.get("precision"), ReleasePrecision, "precision"
        )
        return cls(**values)


@dataclasses.dataclass(frozen=True)
class VolumeBasis:
    security_id: str
    average_daily_share_volume: str
    lookback_sessions: int
    window_start_date: str
    window_end_date: str
    available_at: str
    observed_at: str
    definition_id: str
    source_id: str
    source_version: str
    raw_record_sha256: str

    def __post_init__(self) -> None:
        _required_text(self.security_id, "volume_basis.security_id")
        _decimal_text(
            self.average_daily_share_volume,
            "average_daily_share_volume",
            positive=True,
        )
        _integer(self.lookback_sessions, "lookback_sessions", minimum=1)
        start = _canonical_date(self.window_start_date, "window_start_date")
        end = _canonical_date(self.window_end_date, "window_end_date")
        if end < start:
            raise ShortInterestContractError(
                "window_end_date must not precede window_start_date"
            )
        available = parse_utc_timestamp(
            self.available_at, "volume_basis.available_at"
        )
        observed = parse_utc_timestamp(self.observed_at, "volume_basis.observed_at")
        if observed < available:
            raise ShortInterestContractError(
                "volume_basis.observed_at must not precede available_at"
            )
        for name in ("definition_id", "source_id", "source_version"):
            _required_text(getattr(self, name), name)
        _sha256(self.raw_record_sha256, "volume_basis.raw_record_sha256")

    def to_payload(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "VolumeBasis":
        return cls(**_payload_fields(cls, payload))


@dataclasses.dataclass(frozen=True)
class DenominatorObservation:
    security_id: str
    kind: DenominatorKind
    value: str
    effective_date: str
    available_at: str
    observed_at: str
    source_id: str
    source_version: str
    raw_record_sha256: str

    def __post_init__(self) -> None:
        _required_text(self.security_id, "denominator.security_id")
        if not isinstance(self.kind, DenominatorKind):
            raise ShortInterestContractError("kind must be a DenominatorKind")
        _decimal_text(self.value, "denominator.value", positive=True)
        if (
            self.kind is DenominatorKind.POINT_IN_TIME_SHARES_OUTSTANDING
            and Decimal(self.value) != Decimal(self.value).to_integral_value()
        ):
            raise ShortInterestContractError(
                "point_in_time_shares_outstanding denominator must be whole shares"
            )
        _canonical_date(self.effective_date, "denominator.effective_date")
        available = parse_utc_timestamp(
            self.available_at, "denominator.available_at"
        )
        observed = parse_utc_timestamp(
            self.observed_at, "denominator.observed_at"
        )
        if observed < available:
            raise ShortInterestContractError(
                "denominator.observed_at must not precede available_at"
            )
        for name in ("source_id", "source_version"):
            _required_text(getattr(self, name), name)
        _sha256(self.raw_record_sha256, "denominator.raw_record_sha256")

    def to_payload(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["kind"] = self.kind.value
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "DenominatorObservation":
        values = _payload_fields(cls, payload)
        values["kind"] = _enum(values.get("kind"), DenominatorKind, "kind")
        return cls(**values)


def recompute_days_to_cover(short_shares: int, average_daily_volume: str) -> str:
    shares = _integer(short_shares, "short_shares")
    _decimal_text(average_daily_volume, "average_daily_volume", positive=True)
    volume = Decimal(average_daily_volume)
    try:
        with localcontext() as context:
            context.prec = max(
                50,
                len(str(shares))
                + abs(volume.adjusted())
                + DAYS_TO_COVER_DECIMAL_PLACES
                + 10,
            )
            value = (Decimal(shares) / volume).quantize(
                _DTC_QUANTUM, rounding=ROUND_HALF_EVEN
            )
    except InvalidOperation as exc:
        raise ShortInterestContractError(
            "days-to-cover inputs exceed the supported exact decimal range"
        ) from exc
    return decimal_text(value)


@dataclasses.dataclass(frozen=True)
class ShortInterestSnapshot:
    semantic: SourceSemantic
    source_id: str
    source_version: str
    source_record_id: str
    security: SecurityIdentity
    settlement_date: str
    current_short_shares: int
    previous_settlement_date: str
    previous_short_shares: int
    release_calendar_key: str
    volume_basis: VolumeBasis
    reported_days_to_cover: str
    recomputed_days_to_cover: str
    denominator: DenominatorObservation
    revision_id: str
    revision_published_at: str
    observed_at: str
    supersedes_event_id: str | None
    raw_record_sha256: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.schema_version) is not str or self.schema_version != SCHEMA_VERSION:
            raise ShortInterestContractError(
                f"unsupported ShortInterestSnapshot schema_version {self.schema_version!r}"
            )
        if self.semantic is not SourceSemantic.OFFICIAL_OPEN_SHORT_POSITION_SNAPSHOT:
            raise ShortInterestContractError(
                "snapshot semantic must be official open short-position snapshots"
            )
        for name in (
            "source_id",
            "source_version",
            "source_record_id",
            "release_calendar_key",
            "revision_id",
        ):
            _required_text(getattr(self, name), name)
        if type(self.security) is not SecurityIdentity:
            raise ShortInterestContractError(
                "security must be the exact SecurityIdentity type"
            )
        settlement = _canonical_date(self.settlement_date, "settlement_date")
        previous = _canonical_date(
            self.previous_settlement_date, "previous_settlement_date"
        )
        if previous >= settlement:
            raise ShortInterestContractError(
                "previous_settlement_date must precede settlement_date"
            )
        if not self.security.valid_on(self.settlement_date):
            raise ShortInterestContractError(
                "security identity is not valid on settlement_date"
            )
        _integer(self.current_short_shares, "current_short_shares")
        _integer(self.previous_short_shares, "previous_short_shares")
        if type(self.volume_basis) is not VolumeBasis:
            raise ShortInterestContractError(
                "volume_basis must be the exact VolumeBasis type"
            )
        if type(self.denominator) is not DenominatorObservation:
            raise ShortInterestContractError(
                "denominator must be the exact DenominatorObservation type"
            )
        if self.volume_basis.security_id != self.security.security_id:
            raise ShortInterestContractError(
                "volume_basis.security_id must match snapshot security_id"
            )
        if self.denominator.security_id != self.security.security_id:
            raise ShortInterestContractError(
                "denominator.security_id must match snapshot security_id"
            )
        if _canonical_date(
            self.volume_basis.window_end_date, "volume_basis.window_end_date"
        ) > settlement:
            raise ShortInterestContractError(
                "volume basis must not use sessions after settlement_date"
            )
        if _canonical_date(
            self.denominator.effective_date, "denominator.effective_date"
        ) > settlement:
            raise ShortInterestContractError(
                "denominator effective_date must not follow settlement_date"
            )
        _decimal_text(
            self.reported_days_to_cover,
            "reported_days_to_cover",
            positive=False,
        )
        _decimal_text(
            self.recomputed_days_to_cover,
            "recomputed_days_to_cover",
            positive=False,
        )
        expected_dtc = recompute_days_to_cover(
            self.current_short_shares,
            self.volume_basis.average_daily_share_volume,
        )
        if self.recomputed_days_to_cover != expected_dtc:
            raise ShortInterestContractError(
                "recomputed_days_to_cover must equal current_short_shares / "
                f"average_daily_share_volume at {DAYS_TO_COVER_DECIMAL_PLACES} "
                f"decimal places; expected {expected_dtc!r}"
            )
        published = parse_utc_timestamp(
            self.revision_published_at, "revision_published_at"
        )
        observed = parse_utc_timestamp(self.observed_at, "snapshot.observed_at")
        if observed < published:
            raise ShortInterestContractError(
                "snapshot.observed_at must not precede revision_published_at"
            )
        if published.date() < settlement:
            raise ShortInterestContractError(
                "revision_published_at must not precede settlement_date"
            )
        if self.supersedes_event_id is not None:
            _sha256(self.supersedes_event_id, "supersedes_event_id")
        _sha256(self.raw_record_sha256, "snapshot.raw_record_sha256")

    @property
    def logical_id(self) -> str:
        return hash_payload(
            {
                "security_id": self.security.security_id,
                "semantic": self.semantic.value,
                "settlement_date": self.settlement_date,
                "source_id": self.source_id,
            }
        )

    @property
    def event_id(self) -> str:
        # The vendor/raw digest is lineage supplied by the caller, not proof
        # that normalized facts were serialized faithfully. Bind the complete
        # canonical event so one immutable ID can never denote two payloads.
        return hash_payload(self.to_payload())

    def to_payload(self) -> dict[str, Any]:
        return {
            "current_short_shares": self.current_short_shares,
            "denominator": self.denominator.to_payload(),
            "observed_at": self.observed_at,
            "previous_settlement_date": self.previous_settlement_date,
            "previous_short_shares": self.previous_short_shares,
            "raw_record_sha256": self.raw_record_sha256,
            "recomputed_days_to_cover": self.recomputed_days_to_cover,
            "release_calendar_key": self.release_calendar_key,
            "reported_days_to_cover": self.reported_days_to_cover,
            "revision_id": self.revision_id,
            "revision_published_at": self.revision_published_at,
            "schema_version": self.schema_version,
            "security": self.security.to_payload(),
            "semantic": self.semantic.value,
            "settlement_date": self.settlement_date,
            "source_id": self.source_id,
            "source_record_id": self.source_record_id,
            "source_version": self.source_version,
            "supersedes_event_id": self.supersedes_event_id,
            "volume_basis": self.volume_basis.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ShortInterestSnapshot":
        values = _payload_fields(cls, payload)
        values["semantic"] = _enum(values.get("semantic"), SourceSemantic, "semantic")
        values["security"] = SecurityIdentity.from_payload(values.get("security"))
        values["volume_basis"] = VolumeBasis.from_payload(values.get("volume_basis"))
        values["denominator"] = DenominatorObservation.from_payload(
            values.get("denominator")
        )
        return cls(**values)
