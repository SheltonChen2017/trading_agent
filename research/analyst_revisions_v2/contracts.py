"""Canonical ARV2 event, identity, availability, and revision contracts."""
from __future__ import annotations

import dataclasses
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Mapping

from . import CANONICAL_EVENT_SCHEMA
from .availability import (
    AvailabilityError,
    AvailabilityQuality,
    derive_event_availability,
)
from .canonical import (
    CanonicalEvidenceError,
    format_utc_timestamp,
    parse_date,
    parse_utc_timestamp,
    require_exact_keys,
    require_git_object,
    require_identifier,
    require_int,
    require_sha256,
    require_text,
    require_ticker,
)
from .evidence import SourceRowLocator, derive_event_id


class EventContractError(CanonicalEvidenceError):
    """A canonical event or its immutable revision lineage is invalid."""


class RevisionKind(str, Enum):
    ORIGINAL = "original"
    CORRECTION = "correction"
    WITHDRAWAL = "withdrawal"
    TOMBSTONE = "tombstone"


class EventState(str, Enum):
    ACTIVE_ORIGINAL = "active_original"
    ACTIVE_CORRECTED = "active_corrected"
    WITHDRAWN = "withdrawn"
    TOMBSTONE = "tombstone"


class DataAvailabilityQuality(str, Enum):
    PROVIDER_PUBLICATION = "provider_publication"
    PROVIDER_RECEIPT = "provider_receipt"
    CAPTURE_UPPER_BOUND = "capture_upper_bound"


class NormalizedRating(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


CANONICAL_EVENT_KEYS = frozenset(
    {
        "schema",
        "canonical_event_id",
        "source_locator",
        "provider_contract_id",
        "provider_contract_sha256",
        "provider_event_id",
        "event_version_id",
        "revision_sequence",
        "supersedes_event_version_id",
        "revision_kind",
        "event_state",
        "effective_at",
        "public_at",
        "public_date",
        "available_at",
        "ingested_at",
        "availability_quality",
        "availability_evidence_sha256",
        "eligibility_quality",
        "eligibility_evidence_id",
        "eligible_session",
        "eligible_at",
        "provider_firm_id",
        "provider_analyst_id",
        "raw_firm_name",
        "raw_analyst_name",
        "institution_id",
        "analyst_id",
        "issuer_id",
        "security_id",
        "share_class_id",
        "historical_ticker",
        "ticker_valid_from",
        "ticker_valid_to",
        "identity_mapping_version_id",
        "identity_mapping_valid_from",
        "identity_mapping_valid_to",
        "identity_mapping_available_at",
        "identity_mapping_evidence_sha256",
        "raw_rating",
        "normalized_rating",
        "rating_ontology_version_id",
        "rating_ontology_valid_from",
        "rating_ontology_valid_to",
        "rating_ontology_available_at",
        "rating_ontology_evidence_sha256",
        "normalizer_config_sha256",
        "normalizer_code_sha256",
        "producing_commit",
    }
)


def _enum(value: object, enum_type: type[Enum], name: str):
    if not isinstance(value, str):
        raise EventContractError(f"{name} must be a string enum")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise EventContractError(f"unknown {name}: {value!r}") from exc


def _optional_date(value: object, name: str):
    return None if value is None else parse_date(value, name)


@dataclasses.dataclass(frozen=True)
class CanonicalSourceEvent:
    schema: str
    canonical_event_id: str
    source_locator: SourceRowLocator
    provider_contract_id: str
    provider_contract_sha256: str
    provider_event_id: str
    event_version_id: str
    revision_sequence: int
    supersedes_event_version_id: str | None
    revision_kind: RevisionKind
    event_state: EventState
    effective_at: str
    public_at: str | None
    public_date: str
    available_at: str
    ingested_at: str
    availability_quality: DataAvailabilityQuality
    availability_evidence_sha256: str
    eligibility_quality: AvailabilityQuality
    eligibility_evidence_id: str
    eligible_session: str
    eligible_at: str
    provider_firm_id: str
    provider_analyst_id: str
    raw_firm_name: str
    raw_analyst_name: str
    institution_id: str
    analyst_id: str
    issuer_id: str
    security_id: str
    share_class_id: str
    historical_ticker: str
    ticker_valid_from: str
    ticker_valid_to: str | None
    identity_mapping_version_id: str
    identity_mapping_valid_from: str
    identity_mapping_valid_to: str | None
    identity_mapping_available_at: str
    identity_mapping_evidence_sha256: str
    raw_rating: str
    normalized_rating: NormalizedRating | None
    rating_ontology_version_id: str
    rating_ontology_valid_from: str
    rating_ontology_valid_to: str | None
    rating_ontology_available_at: str
    rating_ontology_evidence_sha256: str
    normalizer_config_sha256: str
    normalizer_code_sha256: str
    producing_commit: str

    def __post_init__(self) -> None:
        if self.schema != CANONICAL_EVENT_SCHEMA:
            raise EventContractError("unsupported canonical event schema")
        if type(self.source_locator) is not SourceRowLocator:
            raise EventContractError("source_locator must be a SourceRowLocator")
        require_identifier(self.provider_contract_id, "provider_contract_id")
        require_sha256(self.provider_contract_sha256, "provider_contract_sha256")
        for name in (
            "provider_event_id",
            "event_version_id",
            "provider_firm_id",
            "provider_analyst_id",
            "institution_id",
            "analyst_id",
            "issuer_id",
            "security_id",
            "share_class_id",
            "identity_mapping_version_id",
            "rating_ontology_version_id",
        ):
            require_identifier(getattr(self, name), name)
        expected_event_id = derive_event_id(
            self.source_locator, self.event_version_id
        )
        if self.canonical_event_id != expected_event_id:
            raise EventContractError("canonical_event_id does not match immutable source/version")
        sequence = require_int(
            self.revision_sequence, "revision_sequence", minimum=0
        )
        if not isinstance(self.revision_kind, RevisionKind):
            raise EventContractError("revision_kind must be a RevisionKind")
        if not isinstance(self.event_state, EventState):
            raise EventContractError("event_state must be an EventState")
        state_by_kind = {
            RevisionKind.ORIGINAL: EventState.ACTIVE_ORIGINAL,
            RevisionKind.CORRECTION: EventState.ACTIVE_CORRECTED,
            RevisionKind.WITHDRAWAL: EventState.WITHDRAWN,
            RevisionKind.TOMBSTONE: EventState.TOMBSTONE,
        }
        if self.event_state is not state_by_kind[self.revision_kind]:
            raise EventContractError("revision_kind and event_state disagree")
        if sequence == 0:
            if (
                self.revision_kind is not RevisionKind.ORIGINAL
                or self.supersedes_event_version_id is not None
            ):
                raise EventContractError(
                    "revision zero must be an original with no supersedes ID"
                )
        else:
            if self.revision_kind is RevisionKind.ORIGINAL:
                raise EventContractError("only revision zero may be original")
            require_identifier(
                self.supersedes_event_version_id,
                "supersedes_event_version_id",
            )
            if self.supersedes_event_version_id == self.event_version_id:
                raise EventContractError("a revision cannot supersede itself")

        effective = parse_utc_timestamp(self.effective_at, "effective_at")
        available = parse_utc_timestamp(self.available_at, "available_at")
        ingested = parse_utc_timestamp(self.ingested_at, "ingested_at")
        public_date = parse_date(self.public_date, "public_date")
        public = (
            None
            if self.public_at is None
            else parse_utc_timestamp(self.public_at, "public_at")
        )
        if not effective <= available <= ingested:
            raise EventContractError(
                "times must satisfy effective_at <= available_at <= ingested_at"
            )
        if public is not None and not effective <= public <= available:
            raise EventContractError(
                "exact public_at must satisfy effective_at <= public_at <= available_at"
            )
        if public is None and (
            effective.date() > public_date or available.date() < public_date
        ):
            raise EventContractError(
                "date-only evidence must fall between effective and available dates"
            )
        if not isinstance(self.availability_quality, DataAvailabilityQuality):
            raise EventContractError(
                "availability_quality must be a DataAvailabilityQuality"
            )
        if (
            self.availability_quality
            is DataAvailabilityQuality.PROVIDER_PUBLICATION
            and (public is None or available != public)
        ):
            raise EventContractError(
                "provider_publication quality requires an exact public_at equal to available_at"
            )
        if (
            self.availability_quality
            is DataAvailabilityQuality.CAPTURE_UPPER_BOUND
            and available != ingested
        ):
            raise EventContractError(
                "capture_upper_bound quality requires available_at == ingested_at"
            )
        require_sha256(
            self.availability_evidence_sha256,
            "availability_evidence_sha256",
        )
        if not isinstance(self.eligibility_quality, AvailabilityQuality):
            raise EventContractError(
                "eligibility_quality must be an AvailabilityQuality"
            )
        require_identifier(self.eligibility_evidence_id, "eligibility_evidence_id")
        eligible_session = parse_date(self.eligible_session, "eligible_session")
        eligible = parse_utc_timestamp(self.eligible_at, "eligible_at")
        try:
            if self.eligibility_quality is AvailabilityQuality.EXACT_PUBLIC_INSTANT:
                if public is None:
                    raise EventContractError(
                        "exact-public eligibility requires public_at evidence"
                    )
                derived = derive_event_availability(
                    evidence_id=self.eligibility_evidence_id,
                    public_at=public.isoformat(),
                )
            else:
                if public is not None:
                    raise EventContractError(
                        "date-only eligibility forbids a synthesized public_at"
                    )
                derived = derive_event_availability(
                    evidence_id=self.eligibility_evidence_id,
                    public_date=self.public_date,
                )
        except AvailabilityError as exc:
            raise EventContractError("eligibility evidence cannot be derived") from exc
        derived_eligible = format_utc_timestamp(
            datetime.fromisoformat(derived.eligible_at.replace("Z", "+00:00"))
        )
        if (
            derived.quality is not self.eligibility_quality
            or derived.public_date != self.public_date
            or derived.eligible_session != self.eligible_session
            or derived_eligible != self.eligible_at
            or derived.evidence_id != self.eligibility_evidence_id
            or eligible.date() != eligible_session
        ):
            raise EventContractError(
                "eligible session/instant does not match publication evidence"
            )
        require_text(self.raw_firm_name, "raw_firm_name")
        require_text(self.raw_analyst_name, "raw_analyst_name")
        require_text(self.raw_rating, "raw_rating")
        require_ticker(self.historical_ticker)

        effective_date = effective.date()
        ticker_from = parse_date(self.ticker_valid_from, "ticker_valid_from")
        ticker_to = _optional_date(self.ticker_valid_to, "ticker_valid_to")
        mapping_from = parse_date(
            self.identity_mapping_valid_from, "identity_mapping_valid_from"
        )
        mapping_to = _optional_date(
            self.identity_mapping_valid_to, "identity_mapping_valid_to"
        )
        ontology_from = parse_date(
            self.rating_ontology_valid_from, "rating_ontology_valid_from"
        )
        ontology_to = _optional_date(
            self.rating_ontology_valid_to, "rating_ontology_valid_to"
        )
        for label, start, end in (
            ("ticker", ticker_from, ticker_to),
            ("identity mapping", mapping_from, mapping_to),
            ("rating ontology", ontology_from, ontology_to),
        ):
            if end is not None and end <= start:
                raise EventContractError(f"{label} validity interval is empty/reversed")
            if effective_date < start or (end is not None and effective_date >= end):
                raise EventContractError(
                    f"effective event falls outside {label} validity interval"
                )
        mapping_available = parse_utc_timestamp(
            self.identity_mapping_available_at,
            "identity_mapping_available_at",
        )
        ontology_available = parse_utc_timestamp(
            self.rating_ontology_available_at,
            "rating_ontology_available_at",
        )
        if mapping_available > available or ontology_available > available:
            raise EventContractError(
                "identity/ontology evidence must be available by event available_at"
            )
        require_sha256(
            self.identity_mapping_evidence_sha256,
            "identity_mapping_evidence_sha256",
        )
        require_sha256(
            self.rating_ontology_evidence_sha256,
            "rating_ontology_evidence_sha256",
        )
        if self.revision_kind in (RevisionKind.ORIGINAL, RevisionKind.CORRECTION):
            if not isinstance(self.normalized_rating, NormalizedRating):
                raise EventContractError("active events require a normalized rating")
        elif self.normalized_rating is not None:
            raise EventContractError(
                "withdrawal/tombstone events cannot assert a normalized rating"
            )
        require_sha256(self.normalizer_config_sha256, "normalizer_config_sha256")
        require_sha256(self.normalizer_code_sha256, "normalizer_code_sha256")
        require_git_object(self.producing_commit, "producing_commit")

    @classmethod
    def create(cls, **fields: Any) -> "CanonicalSourceEvent":
        locator = fields.get("source_locator")
        version = fields.get("event_version_id")
        if type(locator) is not SourceRowLocator:
            raise EventContractError("source_locator must be supplied before deriving ID")
        fields = dict(fields)
        fields.setdefault("schema", CANONICAL_EVENT_SCHEMA)
        fields["canonical_event_id"] = derive_event_id(locator, version)
        return cls(**fields)

    def to_record(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "canonical_event_id": self.canonical_event_id,
            "source_locator": self.source_locator.to_record(),
            "provider_contract_id": self.provider_contract_id,
            "provider_contract_sha256": self.provider_contract_sha256,
            "provider_event_id": self.provider_event_id,
            "event_version_id": self.event_version_id,
            "revision_sequence": self.revision_sequence,
            "supersedes_event_version_id": self.supersedes_event_version_id,
            "revision_kind": self.revision_kind.value,
            "event_state": self.event_state.value,
            "effective_at": self.effective_at,
            "public_at": self.public_at,
            "public_date": self.public_date,
            "available_at": self.available_at,
            "ingested_at": self.ingested_at,
            "availability_quality": self.availability_quality.value,
            "availability_evidence_sha256": self.availability_evidence_sha256,
            "eligibility_quality": self.eligibility_quality.value,
            "eligibility_evidence_id": self.eligibility_evidence_id,
            "eligible_session": self.eligible_session,
            "eligible_at": self.eligible_at,
            "provider_firm_id": self.provider_firm_id,
            "provider_analyst_id": self.provider_analyst_id,
            "raw_firm_name": self.raw_firm_name,
            "raw_analyst_name": self.raw_analyst_name,
            "institution_id": self.institution_id,
            "analyst_id": self.analyst_id,
            "issuer_id": self.issuer_id,
            "security_id": self.security_id,
            "share_class_id": self.share_class_id,
            "historical_ticker": self.historical_ticker,
            "ticker_valid_from": self.ticker_valid_from,
            "ticker_valid_to": self.ticker_valid_to,
            "identity_mapping_version_id": self.identity_mapping_version_id,
            "identity_mapping_valid_from": self.identity_mapping_valid_from,
            "identity_mapping_valid_to": self.identity_mapping_valid_to,
            "identity_mapping_available_at": self.identity_mapping_available_at,
            "identity_mapping_evidence_sha256": self.identity_mapping_evidence_sha256,
            "raw_rating": self.raw_rating,
            "normalized_rating": (
                None if self.normalized_rating is None else self.normalized_rating.value
            ),
            "rating_ontology_version_id": self.rating_ontology_version_id,
            "rating_ontology_valid_from": self.rating_ontology_valid_from,
            "rating_ontology_valid_to": self.rating_ontology_valid_to,
            "rating_ontology_available_at": self.rating_ontology_available_at,
            "rating_ontology_evidence_sha256": self.rating_ontology_evidence_sha256,
            "normalizer_config_sha256": self.normalizer_config_sha256,
            "normalizer_code_sha256": self.normalizer_code_sha256,
            "producing_commit": self.producing_commit,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "CanonicalSourceEvent":
        require_exact_keys(record, CANONICAL_EVENT_KEYS, "canonical event")
        fields = dict(record)
        locator_record = fields.pop("source_locator")
        if not isinstance(locator_record, Mapping):
            raise EventContractError("source_locator must be an object")
        fields["source_locator"] = SourceRowLocator.from_record(locator_record)
        fields["revision_kind"] = _enum(
            fields["revision_kind"], RevisionKind, "revision_kind"
        )
        fields["event_state"] = _enum(
            fields["event_state"], EventState, "event_state"
        )
        fields["availability_quality"] = _enum(
            fields["availability_quality"],
            DataAvailabilityQuality,
            "availability_quality",
        )
        fields["eligibility_quality"] = _enum(
            fields["eligibility_quality"],
            AvailabilityQuality,
            "eligibility_quality",
        )
        if fields["normalized_rating"] is not None:
            fields["normalized_rating"] = _enum(
                fields["normalized_rating"],
                NormalizedRating,
                "normalized_rating",
            )
        return cls(**fields)


def validate_revision_lineage(events: Iterable[CanonicalSourceEvent]) -> None:
    materialized = tuple(events)
    if any(type(event) is not CanonicalSourceEvent for event in materialized):
        raise EventContractError("revision lineage contains a non-canonical event")
    event_ids = [event.canonical_event_id for event in materialized]
    if len(event_ids) != len(set(event_ids)):
        raise EventContractError("canonical_event_id must be globally unique")
    contract_hashes: dict[str, str] = {}
    for event in materialized:
        prior_hash = contract_hashes.setdefault(
            event.provider_contract_id, event.provider_contract_sha256
        )
        if prior_hash != event.provider_contract_sha256:
            raise EventContractError(
                "one provider_contract_id cannot name multiple contract hashes"
            )
    grouped: dict[tuple[str, str], list[CanonicalSourceEvent]] = defaultdict(list)
    for event in materialized:
        grouped[(event.provider_contract_id, event.provider_event_id)].append(event)
    for key, revisions in grouped.items():
        version_ids = [event.event_version_id for event in revisions]
        if len(version_ids) != len(set(version_ids)):
            raise EventContractError(
                f"event_version_id must be unique within provider event: {key}"
            )
        ordered = sorted(revisions, key=lambda event: event.revision_sequence)
        sequences = [event.revision_sequence for event in ordered]
        if sequences != list(range(len(ordered))):
            raise EventContractError(
                f"provider revision sequence must be contiguous from zero: {key}"
            )
        for index, event in enumerate(ordered):
            if index:
                previous = ordered[index - 1]
                if event.supersedes_event_version_id != previous.event_version_id:
                    raise EventContractError(
                        "each revision must supersede the immediately prior immutable version"
                    )
                if parse_utc_timestamp(
                    event.available_at, "available_at"
                ) < parse_utc_timestamp(previous.available_at, "available_at"):
                    raise EventContractError(
                        "later revisions cannot become available before prior revisions"
                    )
                if parse_utc_timestamp(
                    event.eligible_at, "eligible_at"
                ) < parse_utc_timestamp(previous.eligible_at, "eligible_at"):
                    raise EventContractError(
                        "later revisions cannot become eligible before prior revisions"
                    )
                if previous.event_state in (EventState.WITHDRAWN, EventState.TOMBSTONE):
                    raise EventContractError("terminal revisions cannot have successors")


def materialize_events_as_of(
    events: Iterable[CanonicalSourceEvent], *, as_of: str
) -> tuple[CanonicalSourceEvent, ...]:
    """Return the latest active version actually knowable at ``as_of``."""
    materialized = tuple(events)
    validate_revision_lineage(materialized)
    cutoff = parse_utc_timestamp(as_of, "as_of")
    grouped: dict[tuple[str, str], list[CanonicalSourceEvent]] = defaultdict(list)
    for event in materialized:
        if (
            parse_utc_timestamp(event.effective_at, "effective_at") <= cutoff
            and parse_utc_timestamp(event.available_at, "available_at") <= cutoff
            and parse_utc_timestamp(event.eligible_at, "eligible_at") <= cutoff
        ):
            grouped[(event.provider_contract_id, event.provider_event_id)].append(event)
    active: list[CanonicalSourceEvent] = []
    for revisions in grouped.values():
        latest = max(
            revisions,
            key=lambda event: (
                parse_utc_timestamp(event.available_at, "available_at"),
                event.revision_sequence,
            ),
        )
        if latest.event_state in (
            EventState.ACTIVE_ORIGINAL,
            EventState.ACTIVE_CORRECTED,
        ):
            active.append(latest)
    return tuple(
        sorted(
            active,
            key=lambda event: (
                event.security_id,
                event.provider_event_id,
                event.revision_sequence,
            ),
        )
    )
