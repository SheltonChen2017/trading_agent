"""Reviewed, date-versioned firm rating scales for Analyst Revisions V2.

The V2 blueprint forbids a global Buy/Hold/Sell lookup.  This module loads an
exact, content-addressed table of firm-specific labels and ordered ranks.  It
does not infer an order from rating actions or from outcome data: an absent
firm, date interval, or raw label is a named refusal.
"""
from __future__ import annotations

import dataclasses
import threading
import weakref
from collections import defaultdict
from datetime import date
from enum import Enum
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

from .canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    parse_date,
    parse_utc_timestamp,
    require_canonical_json_bytes,
    require_exact_keys,
    require_identifier,
    require_int,
    require_sha256,
    require_text,
    sha256_bytes,
)
from .production_registry import require_production_registry_entry


FIRM_ONTOLOGY_SCHEMA = "arv2-firm-rating-ontology-v1"
FIRM_ONTOLOGY_REGISTRY_SCHEMA = "arv2-firm-ontology-registry-v2"
FIRM_ONTOLOGY_REGISTRY_PATH = (
    Path(__file__).resolve().parent / "specs" / "firm_ontology_registry.json"
)
_ONTOLOGY_KEYS = frozenset(
    {"schema", "ontology_id", "version", "status", "reviewed_at", "entries"}
)
_ENTRY_KEYS = frozenset(
    {
        "provider_firm_id",
        "firm_name",
        "valid_from",
        "valid_to",
        "raw_label",
        "ordered_rank",
        "scale_size",
        "scope",
        "mapping_quality",
        "reviewer",
        "source_evidence_id",
        "source_evidence_sha256",
    }
)


class FirmOntologyError(CanonicalEvidenceError):
    """A firm-rating ontology or requested mapping is not admissible."""


class RatingScope(str, Enum):
    COMPANY_RELATIVE = "company_relative"
    SECTOR_RELATIVE = "sector_relative"
    ABSOLUTE = "absolute"


class MappingQuality(str, Enum):
    REVIEWED_PRIMARY = "reviewed_primary"
    REVIEWED_ALIAS = "reviewed_alias"


class RatingMappingRefusalReason(str, Enum):
    NO_ACTIVE_FIRM_SCALE = "no_active_firm_scale"
    UNREVIEWED_RATING_LABEL = "unreviewed_rating_label"


def _enum(value: object, enum_type: type[Enum], name: str):
    if not isinstance(value, str):
        raise FirmOntologyError(f"{name} must be a string enum")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise FirmOntologyError(f"unknown {name}: {value!r}") from exc


@dataclasses.dataclass(frozen=True)
class FirmRatingMapEntry:
    provider_firm_id: str
    firm_name: str
    valid_from: str
    valid_to: str | None
    raw_label: str
    ordered_rank: int
    scale_size: int
    scope: RatingScope
    mapping_quality: MappingQuality
    reviewer: str
    source_evidence_id: str
    source_evidence_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.provider_firm_id, "provider_firm_id")
        require_text(self.firm_name, "firm_name")
        start = parse_date(self.valid_from, "valid_from")
        end = None if self.valid_to is None else parse_date(self.valid_to, "valid_to")
        if end is not None and end <= start:
            raise FirmOntologyError("firm rating validity interval is empty/reversed")
        require_text(self.raw_label, "raw_label")
        require_int(self.scale_size, "scale_size", minimum=2)
        require_int(
            self.ordered_rank,
            "ordered_rank",
            minimum=1,
            maximum=self.scale_size,
        )
        if not isinstance(self.scope, RatingScope):
            raise FirmOntologyError("scope must be a RatingScope")
        if not isinstance(self.mapping_quality, MappingQuality):
            raise FirmOntologyError("mapping_quality must be a MappingQuality")
        require_text(self.reviewer, "reviewer")
        require_identifier(self.source_evidence_id, "source_evidence_id")
        require_sha256(self.source_evidence_sha256, "source_evidence_sha256")

    @property
    def normalized_score(self) -> Fraction:
        """Return the exact blueprint score in [-1, 1] as a rational number."""
        return Fraction(
            2 * (self.ordered_rank - 1) - (self.scale_size - 1),
            self.scale_size - 1,
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "provider_firm_id": self.provider_firm_id,
            "firm_name": self.firm_name,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "raw_label": self.raw_label,
            "ordered_rank": self.ordered_rank,
            "scale_size": self.scale_size,
            "scope": self.scope.value,
            "mapping_quality": self.mapping_quality.value,
            "reviewer": self.reviewer,
            "source_evidence_id": self.source_evidence_id,
            "source_evidence_sha256": self.source_evidence_sha256,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "FirmRatingMapEntry":
        require_exact_keys(record, _ENTRY_KEYS, "firm rating ontology entry")
        fields = dict(record)
        fields["scope"] = _enum(fields["scope"], RatingScope, "scope")
        fields["mapping_quality"] = _enum(
            fields["mapping_quality"], MappingQuality, "mapping_quality"
        )
        return cls(**fields)


@dataclasses.dataclass(frozen=True)
class RatingMapping:
    ontology_id: str
    ontology_sha256: str
    entry: FirmRatingMapEntry

    @property
    def score(self) -> Fraction:
        return self.entry.normalized_score


@dataclasses.dataclass(frozen=True)
class RatingMappingRefusal:
    provider_firm_id: str
    event_date: str
    raw_label: str
    reason: RatingMappingRefusalReason


@dataclasses.dataclass(frozen=True, init=False)
class ReviewedFirmRatingOntology:
    schema: str
    ontology_id: str
    version: str
    status: str
    reviewed_at: str
    entries: tuple[FirmRatingMapEntry, ...]
    payload_sha256: str
    source_path: str


_ONTOLOGY_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[ReviewedFirmRatingOntology],
        Path,
        tuple[object, ...],
    ],
] = {}
_ONTOLOGY_AUTHORITIES_LOCK = threading.RLock()


def _ontology_fingerprint(
    ontology: ReviewedFirmRatingOntology,
) -> tuple[object, ...]:
    return (
        ontology.schema,
        ontology.ontology_id,
        ontology.version,
        ontology.status,
        ontology.reviewed_at,
        tuple(canonical_json_bytes(entry.to_record()) for entry in ontology.entries),
        ontology.payload_sha256,
        ontology.source_path,
    )


def _forget_ontology_authority(
    identity: int, reference: weakref.ReferenceType[ReviewedFirmRatingOntology]
) -> None:
    with _ONTOLOGY_AUTHORITIES_LOCK:
        current = _ONTOLOGY_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _ONTOLOGY_AUTHORITIES.pop(identity, None)


def _validate_entry_set(entries: tuple[FirmRatingMapEntry, ...]) -> None:
    if not entries:
        raise FirmOntologyError("a reviewed firm ontology cannot be empty")
    canonical_order = tuple(
        sorted(
            entries,
            key=lambda entry: (
                entry.provider_firm_id,
                entry.valid_from,
                "9999-12-31" if entry.valid_to is None else entry.valid_to,
                entry.ordered_rank,
                entry.raw_label.casefold(),
                entry.raw_label,
            ),
        )
    )
    if entries != canonical_order:
        raise FirmOntologyError("firm rating ontology entries are not canonical-sorted")

    grouped: dict[tuple[str, str, str | None], list[FirmRatingMapEntry]] = defaultdict(list)
    for entry in entries:
        grouped[
            (entry.provider_firm_id, entry.valid_from, entry.valid_to)
        ].append(entry)

    intervals_by_firm: dict[str, list[tuple[date, date | None]]] = defaultdict(list)
    for (firm_id, valid_from, valid_to), scale_entries in grouped.items():
        sizes = {entry.scale_size for entry in scale_entries}
        if len(sizes) != 1:
            raise FirmOntologyError("one firm/date scale has inconsistent scale_size")
        scale_size = next(iter(sizes))
        firm_names = {entry.firm_name for entry in scale_entries}
        if len(firm_names) != 1:
            raise FirmOntologyError("one firm/date scale has inconsistent firm_name")
        ranks = {entry.ordered_rank for entry in scale_entries}
        if ranks != set(range(1, scale_size + 1)):
            raise FirmOntologyError(
                "one firm/date scale must cover every ordered rank"
            )
        labels = [entry.raw_label for entry in scale_entries]
        if len(labels) != len(set(labels)):
            raise FirmOntologyError("one firm/date scale contains duplicate raw labels")
        ranks_by_casefolded_label: dict[str, set[int]] = defaultdict(set)
        for entry in scale_entries:
            ranks_by_casefolded_label[entry.raw_label.casefold()].add(
                entry.ordered_rank
            )
        if any(len(ranks) != 1 for ranks in ranks_by_casefolded_label.values()):
            raise FirmOntologyError(
                "case variants of one raw label cannot have different ranks"
            )
        intervals_by_firm[firm_id].append(
            (
                parse_date(valid_from, "valid_from"),
                None if valid_to is None else parse_date(valid_to, "valid_to"),
            )
        )

    for intervals in intervals_by_firm.values():
        intervals.sort(key=lambda interval: interval[0])
        for previous, current in zip(intervals, intervals[1:]):
            if previous[1] is None or current[0] < previous[1]:
                raise FirmOntologyError(
                    "firm rating validity intervals overlap"
                )


def _ontology_from_payload(path: Path, payload: bytes) -> ReviewedFirmRatingOntology:
    record = require_canonical_json_bytes(payload, "firm rating ontology")
    if not isinstance(record, dict):
        raise FirmOntologyError("firm rating ontology must be an object")
    require_exact_keys(record, _ONTOLOGY_KEYS, "firm rating ontology")
    if record["schema"] != FIRM_ONTOLOGY_SCHEMA:
        raise FirmOntologyError("unsupported firm rating ontology schema")
    require_identifier(record["ontology_id"], "ontology_id")
    require_identifier(record["version"], "version")
    if record["status"] != "reviewed":
        raise FirmOntologyError("firm rating ontology status must be reviewed")
    parse_utc_timestamp(record["reviewed_at"], "reviewed_at")
    raw_entries = record["entries"]
    if not isinstance(raw_entries, list):
        raise FirmOntologyError("firm rating ontology entries must be an array")
    parsed_entries: list[FirmRatingMapEntry] = []
    for entry in raw_entries:
        if not isinstance(entry, Mapping):
            raise FirmOntologyError("firm rating ontology entry must be an object")
        parsed_entries.append(FirmRatingMapEntry.from_record(entry))
    entries = tuple(parsed_entries)
    _validate_entry_set(entries)

    value = object.__new__(ReviewedFirmRatingOntology)
    fields: dict[str, object] = {
        "schema": record["schema"],
        "ontology_id": record["ontology_id"],
        "version": record["version"],
        "status": record["status"],
        "reviewed_at": record["reviewed_at"],
        "entries": entries,
        "payload_sha256": sha256_bytes(payload),
        "source_path": str(path),
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    fingerprint = _ontology_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_ontology_authority(key, ref)
    )
    with _ONTOLOGY_AUTHORITIES_LOCK:
        _ONTOLOGY_AUTHORITIES[identity] = (reference, path, fingerprint)
    return value


def load_reviewed_firm_rating_ontology(
    path: str | Path,
) -> ReviewedFirmRatingOntology:
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise FirmOntologyError("firm rating ontology must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise FirmOntologyError("firm rating ontology is absent or unreadable") from exc
    if not resolved.is_file() or resolved.is_symlink():
        raise FirmOntologyError("firm rating ontology must be a regular file")
    return _ontology_from_payload(resolved, resolved.read_bytes())


def revalidate_firm_rating_ontology(
    ontology: ReviewedFirmRatingOntology,
) -> ReviewedFirmRatingOntology:
    if type(ontology) is not ReviewedFirmRatingOntology:
        raise FirmOntologyError(
            "firm rating ontology authority requires the exact reviewed type"
        )
    with _ONTOLOGY_AUTHORITIES_LOCK:
        authority = _ONTOLOGY_AUTHORITIES.get(id(ontology))
    if authority is None or authority[0]() is not ontology:
        raise FirmOntologyError("firm rating ontology is not loader-authenticated")
    if authority[2] != _ontology_fingerprint(ontology):
        raise FirmOntologyError("firm rating ontology changed after authentication")
    path = authority[1]
    if not path.is_file() or path.is_symlink():
        raise FirmOntologyError("firm rating ontology source changed or disappeared")
    payload = path.read_bytes()
    if sha256_bytes(payload) != ontology.payload_sha256:
        raise FirmOntologyError("firm rating ontology source hash changed")
    record = require_canonical_json_bytes(payload, "firm rating ontology")
    if not isinstance(record, dict):
        raise FirmOntologyError("firm rating ontology must remain an object")
    reparsed = tuple(
        FirmRatingMapEntry.from_record(entry) for entry in record["entries"]
    )
    _validate_entry_set(reparsed)
    if reparsed != ontology.entries:
        raise FirmOntologyError("firm rating ontology entries changed")
    return ontology


def require_registered_production_firm_ontology(
    ontology: ReviewedFirmRatingOntology,
) -> ReviewedFirmRatingOntology:
    """Require the exact structural ontology to have an external review anchor.

    The checked-in registry is intentionally empty.  Structural/synthetic
    fixtures can still exercise ontology semantics, but no local file can bind
    a production event until an independent review adds its exact bytes.
    """
    revalidate_firm_rating_ontology(ontology)
    require_production_registry_entry(
        artifact_path=Path(ontology.source_path),
        artifact_id=ontology.ontology_id,
        artifact_sha256=ontology.payload_sha256,
        registry_path=FIRM_ONTOLOGY_REGISTRY_PATH,
        registry_schema=FIRM_ONTOLOGY_REGISTRY_SCHEMA,
        artifact_kind="firm rating ontology",
    )
    return revalidate_firm_rating_ontology(ontology)


def resolve_firm_rating(
    ontology: ReviewedFirmRatingOntology,
    *,
    provider_firm_id: str,
    event_date: str,
    raw_label: str,
) -> RatingMapping | RatingMappingRefusal:
    """Resolve one raw label without guessing or applying a global scale."""
    revalidate_firm_rating_ontology(ontology)
    require_identifier(provider_firm_id, "provider_firm_id")
    when = parse_date(event_date, "event_date")
    require_text(raw_label, "raw_label")
    active = tuple(
        entry
        for entry in ontology.entries
        if entry.provider_firm_id == provider_firm_id
        and parse_date(entry.valid_from, "valid_from") <= when
        and (
            entry.valid_to is None
            or when < parse_date(entry.valid_to, "valid_to")
        )
    )
    if not active:
        return RatingMappingRefusal(
            provider_firm_id=provider_firm_id,
            event_date=event_date,
            raw_label=raw_label,
            reason=RatingMappingRefusalReason.NO_ACTIVE_FIRM_SCALE,
        )
    matches = tuple(
        entry for entry in active if entry.raw_label == raw_label
    )
    if len(matches) != 1:
        return RatingMappingRefusal(
            provider_firm_id=provider_firm_id,
            event_date=event_date,
            raw_label=raw_label,
            reason=RatingMappingRefusalReason.UNREVIEWED_RATING_LABEL,
        )
    return RatingMapping(
        ontology_id=ontology.ontology_id,
        ontology_sha256=ontology.payload_sha256,
        entry=matches[0],
    )
