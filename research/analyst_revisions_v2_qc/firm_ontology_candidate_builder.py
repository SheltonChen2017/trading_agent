"""Deterministic, non-authorizing firm-ontology candidate composition.

The physical firm-review packet deliberately stops before a human orders any
firm scale.  This module accepts that authenticated packet and an owner-filled
copy of its 74-row adjudication template, then renders the exact structural
artifacts needed by the existing ontology and historical-availability
loaders.  It never infers a label order, scope, validity interval, evidence
clock, or alias.  It also never edits a production registry or represents the
result as independently reviewed.

The availability-review and registry-entry outputs are intentionally pending
review templates.  Their null/false review fields make them non-authorizing;
an independent reviewer must verify the exact content-addressed candidates
before creating either accepted artifact.
"""
from __future__ import annotations

import dataclasses
import enum
import os
import stat
import threading
import weakref
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable, NoReturn

from research.analyst_revisions_v2 import canonical as _canonical
from research.analyst_revisions_v2 import firm_ontology as _ontology
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    parse_date,
    parse_utc_timestamp,
    require_identifier,
    require_int,
    require_sha256,
    require_text,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2.firm_ontology import (
    FIRM_ONTOLOGY_REGISTRY_PATH,
    FIRM_ONTOLOGY_REGISTRY_SCHEMA,
    FIRM_ONTOLOGY_SCHEMA,
    FirmRatingMapEntry,
    MappingQuality,
    RatingScope,
)
from research.analyst_revisions_v2_qc import (
    physical_firm_ontology_review_packet as _packet,
)
from research.analyst_revisions_v2_qc.physical_firm_ontology_review_packet import (
    PhysicalFirmOntologyReviewPacket,
)
from research.analyst_revisions_v2_qc import production_evidence_composer as _composer
from research.analyst_revisions_v2_qc.production_evidence_composer import (
    FIRM_AVAILABILITY_REVIEW_SCHEMA,
    FIRM_AVAILABILITY_SCHEMA,
    FirmOntologyAvailabilityEntry,
)


CANDIDATE_SCHEMA = "arv2-firm-ontology-candidate-bundle-v1"
COVERAGE_SCHEMA = "arv2-firm-ontology-candidate-coverage-v1"
REGISTRY_CANDIDATE_SCHEMA = "arv2-firm-ontology-registry-entry-candidate-v1"
OWNER_ADJUDICATION_STATUS = "owner_reviewed_complete"
PENDING_REVIEW_STATUS = "independent_review_required_not_authorized"
EXPECTED_ADJUDICATION_FIRM_COUNT = 74
# The fixed 74-firm review should remain compact.  These limits allow an
# average of more than 220 KiB per firm and one exceptional 1 MiB row while
# refusing the former 64 MiB parse-tree amplification before it begins.
MAX_OWNER_ADJUDICATION_BYTES = 16 * 1024 * 1024
MAX_OWNER_ADJUDICATION_ROW_BYTES = 1024 * 1024
# Thirty-two explicit scale regimes cover more than two changes per year over
# the frozen 2013-2025 history.  The per-firm mapping ceilings are also several
# times larger than the lane's complete 39-alias global comparator.
MAX_VALIDITY_INTERVALS_PER_FIRM = 32
MAX_PRIMARY_MAPPINGS_PER_FIRM = 256
MAX_ALIAS_MAPPINGS_PER_FIRM = 256
MAX_MAPPINGS_PER_FIRM = 512
MAX_ONTOLOGY_ENTRY_COUNT = EXPECTED_ADJUDICATION_FIRM_COUNT * MAX_MAPPINGS_PER_FIRM
# Candidate ontology and availability files must fit the downstream 64 MiB
# loader/publisher bound.  Reserve 64 KiB for their fixed object envelopes.
MAX_CANDIDATE_FILE_BYTES = 64 * 1024 * 1024
MAX_PROJECTED_ENTRY_BYTES = MAX_CANDIDATE_FILE_BYTES - 64 * 1024
MAX_AVAILABILITY_REVIEW_BYTES = 1024 * 1024

_PATH_TYPE = type(Path())
_OUTER_KEYS = frozenset(
    {
        "ranking_ordinal",
        "provider_firm_id",
        "predeclared_2021_2025_volume_count",
        "observed_firm_names",
        "owner_adjudication",
        "ontology_authority_created",
        "availability_authority_created",
        "production_authority",
    }
)
_ADJUDICATION_KEYS = frozenset(
    {
        "review_status",
        "reviewer",
        "reviewed_at",
        "canonical_firm_name",
        "validity_intervals",
        "ordered_scale",
        "scope",
        "alias_mappings",
        "notes",
    }
)
_INTERVAL_KEYS = frozenset({"valid_from", "valid_to"})
_MAPPING_KEYS = frozenset(
    {
        "valid_from",
        "valid_to",
        "raw_label",
        "ordered_rank",
        "source_evidence_id",
        "source_evidence_sha256",
        "available_at",
        "valid_to_available_at",
    }
)
_FIRM_EVIDENCE_KEYS = frozenset(
    {
        "provider_firm_id",
        "observed_firm_names",
        "source_row_count",
        "current_admitted_count",
        "censored_admitted_count",
        "exact_censored_source_clock_count",
        "invalid_current_label_count",
        "invalid_previous_label_count",
        "first_event_date",
        "last_event_date",
        "observed_labels",
        "transition_counts",
        "action_diagnostics",
        "date_diagnostics",
        "earliest_exact_censored_admitted_source",
        "conflict_and_connectedness_diagnostics",
        "predeclared_2021_2025_volume_ranking",
        "ordered_scale",
        "scope",
        "ontology_reviewed",
        "production_authority",
    }
)
_OBSERVED_LABEL_KEYS = frozenset(
    {
        "field",
        "raw_label",
        "observed_count",
        "censored_admitted_count",
        "first_event_date",
        "last_event_date",
    }
)

_PINNED_PACKET_TYPE = PhysicalFirmOntologyReviewPacket
_PINNED_PACKET_REQUIRE = _packet.require_physical_firm_ontology_review_packet
_PINNED_TEMPLATE_ITERATOR = (
    _packet.iter_physical_firm_owner_adjudication_template
)
_PINNED_EVIDENCE_ITERATOR = _packet.iter_physical_firm_ontology_review_rows
_PINNED_ENTRY_TYPE = FirmRatingMapEntry
_PINNED_AVAILABILITY_ENTRY_TYPE = FirmOntologyAvailabilityEntry
_PINNED_VALIDATE_ENTRY_SET = _ontology._validate_entry_set
_PINNED_CANONICAL_JSON_BYTES = canonical_json_bytes
_PINNED_SHA256_BYTES = sha256_bytes
_PINNED_DECODE_UTF8 = decode_utf8
_PINNED_STRICT_JSON_LOADS = strict_json_loads
_PINNED_PARSE_DATE = parse_date
_PINNED_PARSE_UTC_TIMESTAMP = parse_utc_timestamp
_PINNED_REQUIRE_IDENTIFIER = require_identifier
_PINNED_REQUIRE_INT = require_int
_PINNED_REQUIRE_SHA256 = require_sha256
_PINNED_REQUIRE_TEXT = require_text


class FirmOntologyCandidateRefusalReason(str, enum.Enum):
    """Stable refusal vocabulary for owner-adjudication composition."""

    PACKET_AUTHENTICATION_FAILED = "packet_authentication_failed"
    PACKET_CENSUS_NOT_74 = "packet_census_not_74"
    ADJUDICATION_FILE_INVALID = "adjudication_file_invalid"
    ADJUDICATION_CENSUS_CHANGED = "adjudication_census_changed"
    TEMPLATE_BINDING_CHANGED = "template_binding_changed"
    REVIEW_INCOMPLETE = "review_incomplete"
    VALIDITY_INTERVALS_INVALID = "validity_intervals_invalid"
    SCALE_INCOMPLETE = "scale_incomplete"
    SCOPE_INVALID = "scope_invalid"
    EVIDENCE_INVALID = "evidence_invalid"
    DUPLICATE_MAPPING = "duplicate_mapping"
    OBSERVED_DATE_UNCOVERED = "observed_date_uncovered"
    OBSERVED_LABEL_UNMAPPED = "observed_label_unmapped"
    CANDIDATE_CAPACITY_EXCEEDED = "candidate_capacity_exceeded"
    OUTPUT_COMPATIBILITY_FAILED = "output_compatibility_failed"


class FirmOntologyCandidateError(ValueError):
    """One exact candidate-composition invariant was refused."""

    def __init__(
        self, reason: FirmOntologyCandidateRefusalReason, message: str
    ) -> None:
        if type(reason) is not FirmOntologyCandidateRefusalReason:
            raise TypeError("candidate refusal reason must use the exact enum")
        if type(message) is not str or not message:
            raise TypeError("candidate refusal message must be exact nonempty text")
        self.reason = reason
        super().__init__(f"{reason.value}: {message}")


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class FirmOntologyCandidateBundle:
    """Exact non-authorizing bytes rendered from all 74 owner decisions."""

    schema: str
    bundle_id: str
    bundle_sha256: str
    packet_id: str
    packet_sha256: str
    owner_adjudication_sha256: str
    owner_adjudication_byte_count: int
    owner_adjudication_bytes: bytes = dataclasses.field(repr=False)
    firm_count: int
    ontology_entry_count: int
    ontology_id: str
    ontology_sha256: str
    ontology_bytes: bytes = dataclasses.field(repr=False)
    availability_id: str
    availability_sha256: str
    availability_bytes: bytes = dataclasses.field(repr=False)
    availability_review_candidate_sha256: str
    availability_review_candidate_bytes: bytes = dataclasses.field(repr=False)
    registry_candidate_id: str
    registry_candidate_sha256: str
    registry_candidate_bytes: bytes = dataclasses.field(repr=False)
    coverage_diagnostic_id: str
    coverage_diagnostic_sha256: str
    coverage_diagnostic_bytes: bytes = dataclasses.field(repr=False)
    independently_reviewed: bool
    production_authority: bool
    provider_access: bool
    quantconnect_access: bool
    outcome_access: bool
    deployment: bool
    orders: bool
    trading: bool


@dataclasses.dataclass(frozen=True, slots=True)
class _MappingDecision:
    valid_from: str
    valid_to: str | None
    raw_label: str
    ordered_rank: int
    source_evidence_id: str
    source_evidence_sha256: str
    available_at: str
    valid_to_available_at: str | None
    quality: MappingQuality


_BUNDLE_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[FirmOntologyCandidateBundle],
        tuple[object, ...],
        int,
    ],
] = {}
_BUNDLE_AUTHORITY_LOCK = threading.RLock()
_BUNDLE_AUTHORITY_PID = os.getpid()


def _reset_bundle_authorities_after_fork() -> None:
    """Discard inherited authorities and replace a potentially orphaned lock."""

    global _BUNDLE_AUTHORITIES, _BUNDLE_AUTHORITY_LOCK, _BUNDLE_AUTHORITY_PID
    _BUNDLE_AUTHORITIES = {}
    _BUNDLE_AUTHORITY_LOCK = threading.RLock()
    _BUNDLE_AUTHORITY_PID = os.getpid()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_bundle_authorities_after_fork)


def _bundle_fingerprint(value: FirmOntologyCandidateBundle) -> tuple[object, ...]:
    return tuple(getattr(value, field.name) for field in dataclasses.fields(value))


def _forget_bundle(
    identity: int, reference: weakref.ReferenceType[FirmOntologyCandidateBundle]
) -> None:
    with _BUNDLE_AUTHORITY_LOCK:
        current = _BUNDLE_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _BUNDLE_AUTHORITIES.pop(identity, None)


def _refuse(
    reason: FirmOntologyCandidateRefusalReason, message: str
) -> NoReturn:
    raise FirmOntologyCandidateError(reason, message)


def _require_dependencies() -> None:
    if (
        _packet.PhysicalFirmOntologyReviewPacket is not _PINNED_PACKET_TYPE
        or _packet.require_physical_firm_ontology_review_packet
        is not _PINNED_PACKET_REQUIRE
        or _packet.iter_physical_firm_owner_adjudication_template
        is not _PINNED_TEMPLATE_ITERATOR
        or _packet.iter_physical_firm_ontology_review_rows
        is not _PINNED_EVIDENCE_ITERATOR
        or _ontology.FirmRatingMapEntry is not _PINNED_ENTRY_TYPE
        or _ontology.RatingScope is not RatingScope
        or _ontology.MappingQuality is not MappingQuality
        or _ontology._validate_entry_set is not _PINNED_VALIDATE_ENTRY_SET
        or _composer.FirmOntologyAvailabilityEntry
        is not _PINNED_AVAILABILITY_ENTRY_TYPE
        or _canonical.canonical_json_bytes is not _PINNED_CANONICAL_JSON_BYTES
        or _canonical.sha256_bytes is not _PINNED_SHA256_BYTES
        or _canonical.decode_utf8 is not _PINNED_DECODE_UTF8
        or _canonical.strict_json_loads is not _PINNED_STRICT_JSON_LOADS
        or _canonical.parse_date is not _PINNED_PARSE_DATE
        or _canonical.parse_utc_timestamp is not _PINNED_PARSE_UTC_TIMESTAMP
        or _canonical.require_identifier is not _PINNED_REQUIRE_IDENTIFIER
        or _canonical.require_int is not _PINNED_REQUIRE_INT
        or _canonical.require_sha256 is not _PINNED_REQUIRE_SHA256
        or _canonical.require_text is not _PINNED_REQUIRE_TEXT
        or canonical_json_bytes is not _PINNED_CANONICAL_JSON_BYTES
        or sha256_bytes is not _PINNED_SHA256_BYTES
        or decode_utf8 is not _PINNED_DECODE_UTF8
        or strict_json_loads is not _PINNED_STRICT_JSON_LOADS
        or parse_date is not _PINNED_PARSE_DATE
        or parse_utc_timestamp is not _PINNED_PARSE_UTC_TIMESTAMP
        or require_identifier is not _PINNED_REQUIRE_IDENTIFIER
        or require_int is not _PINNED_REQUIRE_INT
        or require_sha256 is not _PINNED_REQUIRE_SHA256
        or require_text is not _PINNED_REQUIRE_TEXT
        or _content_addressed_record is not _PINNED_CONTENT_ADDRESSED_RECORD
        or _require_candidate_content_bindings
        is not _PINNED_CANDIDATE_CONTENT_REQUIRE
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "candidate dependency binding changed",
        )


def _read_owner_file(
    path: Path,
) -> tuple[bytes, tuple[dict[str, Any], ...]]:
    if (
        type(path) is not _PATH_TYPE
        or not path.is_absolute()
        or ".." in path.parts
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.ADJUDICATION_FILE_INVALID,
            "owner adjudication path must be an exact absolute Path",
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.ADJUDICATION_FILE_INVALID,
            "owner adjudication file is unavailable",
        ) from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) & 0o077
            or not 0 < before.st_size <= MAX_OWNER_ADJUDICATION_BYTES
        ):
            _refuse(
                FirmOntologyCandidateRefusalReason.ADJUDICATION_FILE_INVALID,
                "owner adjudication must be one bounded owner-only regular file",
            )
        payload = bytearray()
        rows: list[dict[str, Any]] = []
        handle = os.fdopen(descriptor, "rb", buffering=0, closefd=False)
        while True:
            line = handle.readline(MAX_OWNER_ADJUDICATION_ROW_BYTES + 1)
            if not line:
                break
            if (
                len(line) > MAX_OWNER_ADJUDICATION_ROW_BYTES
                or not line.endswith(b"\n")
                or b"\r" in line
            ):
                _refuse(
                    FirmOntologyCandidateRefusalReason.ADJUDICATION_FILE_INVALID,
                    "owner adjudication contains a noncanonical or oversized row",
                )
            payload.extend(line)
            if len(payload) > MAX_OWNER_ADJUDICATION_BYTES:
                _refuse(
                    FirmOntologyCandidateRefusalReason.ADJUDICATION_FILE_INVALID,
                    "owner adjudication exceeds its fixed total byte bound",
                )
            try:
                parsed = strict_json_loads(
                    decode_utf8(line[:-1], "owner firm adjudication row"),
                    "owner firm adjudication row",
                )
            except CanonicalEvidenceError as exc:
                raise FirmOntologyCandidateError(
                    FirmOntologyCandidateRefusalReason.ADJUDICATION_FILE_INVALID,
                    "owner adjudication row is not strict JSON",
                ) from exc
            if type(parsed) is not dict or canonical_json_bytes(parsed) != line:
                _refuse(
                    FirmOntologyCandidateRefusalReason.ADJUDICATION_FILE_INVALID,
                    "owner adjudication row is not canonical JSON",
                )
            rows.append(parsed)
            if len(rows) > EXPECTED_ADJUDICATION_FIRM_COUNT:
                _refuse(
                    FirmOntologyCandidateRefusalReason.ADJUDICATION_CENSUS_CHANGED,
                    "owner adjudication contains more than 74 rows",
                )
        handle.close()
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_mode,
        before.st_uid,
        before.st_nlink,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_mode,
        after.st_uid,
        after.st_nlink,
    )
    if before_identity != after_identity:
        _refuse(
            FirmOntologyCandidateRefusalReason.ADJUDICATION_FILE_INVALID,
            "owner adjudication file changed while read",
        )
    if len(payload) != before.st_size or len(rows) != EXPECTED_ADJUDICATION_FIRM_COUNT:
        _refuse(
            FirmOntologyCandidateRefusalReason.ADJUDICATION_CENSUS_CHANGED,
            "owner adjudication must contain exactly 74 complete rows",
        )
    return bytes(payload), tuple(rows)


def _exact_keys(
    value: object,
    expected: frozenset[str],
    reason: FirmOntologyCandidateRefusalReason,
    name: str,
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        _refuse(reason, f"{name} fields changed")
    return value


def _validated_intervals(raw: object) -> tuple[tuple[str, str | None], ...]:
    if type(raw) is not list or not raw:
        _refuse(
            FirmOntologyCandidateRefusalReason.VALIDITY_INTERVALS_INVALID,
            "each firm needs at least one explicit validity interval",
        )
    if len(raw) > MAX_VALIDITY_INTERVALS_PER_FIRM:
        _refuse(
            FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED,
            "one firm exceeds the fixed validity-interval ceiling",
        )
    intervals: list[tuple[str, str | None]] = []
    for raw_interval in raw:
        interval = _exact_keys(
            raw_interval,
            _INTERVAL_KEYS,
            FirmOntologyCandidateRefusalReason.VALIDITY_INTERVALS_INVALID,
            "validity interval",
        )
        try:
            start = parse_date(interval["valid_from"], "valid_from")
            end = (
                None
                if interval["valid_to"] is None
                else parse_date(interval["valid_to"], "valid_to")
            )
        except CanonicalEvidenceError as exc:
            raise FirmOntologyCandidateError(
                FirmOntologyCandidateRefusalReason.VALIDITY_INTERVALS_INVALID,
                "validity interval date is invalid",
            ) from exc
        if end is not None and end <= start:
            _refuse(
                FirmOntologyCandidateRefusalReason.VALIDITY_INTERVALS_INVALID,
                "validity interval is empty or reversed",
            )
        intervals.append((start.isoformat(), None if end is None else end.isoformat()))
    expected = tuple(
        sorted(intervals, key=lambda item: (item[0], "9999-12-31" if item[1] is None else item[1]))
    )
    if tuple(intervals) != expected or len(set(intervals)) != len(intervals):
        _refuse(
            FirmOntologyCandidateRefusalReason.VALIDITY_INTERVALS_INVALID,
            "validity intervals must be unique and chronological",
        )
    for previous, current in zip(intervals, intervals[1:]):
        if previous[1] is None or previous[1] != current[0]:
            _refuse(
                FirmOntologyCandidateRefusalReason.VALIDITY_INTERVALS_INVALID,
                "validity intervals must form one contiguous half-open sequence",
            )
    return tuple(intervals)


def _mapping_decision(
    raw: object,
    *,
    quality: MappingQuality,
    intervals: tuple[tuple[str, str | None], ...],
) -> _MappingDecision:
    mapping = _exact_keys(
        raw,
        _MAPPING_KEYS,
        FirmOntologyCandidateRefusalReason.EVIDENCE_INVALID,
        "rating mapping",
    )
    try:
        valid_from = parse_date(mapping["valid_from"], "mapping valid_from").isoformat()
        valid_to = (
            None
            if mapping["valid_to"] is None
            else parse_date(mapping["valid_to"], "mapping valid_to").isoformat()
        )
        raw_label = require_text(mapping["raw_label"], "raw_label")
        ordered_rank = require_int(mapping["ordered_rank"], "ordered_rank", minimum=1)
        source_id = require_identifier(mapping["source_evidence_id"], "source_evidence_id")
        source_sha = require_sha256(
            mapping["source_evidence_sha256"], "source_evidence_sha256"
        )
        available_at = mapping["available_at"]
        base = parse_utc_timestamp(available_at, "historical evidence available_at")
        closure_raw = mapping["valid_to_available_at"]
        closure = None
        if closure_raw is not None:
            closure = parse_utc_timestamp(
                closure_raw, "historical closure available_at"
            )
    except CanonicalEvidenceError as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.EVIDENCE_INVALID,
            "rating mapping contains invalid explicit evidence",
        ) from exc
    if (valid_from, valid_to) not in intervals:
        _refuse(
            FirmOntologyCandidateRefusalReason.VALIDITY_INTERVALS_INVALID,
            "every mapping must bind one exact declared validity interval",
        )
    if (valid_to is None) != (closure_raw is None):
        _refuse(
            FirmOntologyCandidateRefusalReason.EVIDENCE_INVALID,
            "closure availability must be explicit exactly for closed intervals",
        )
    if closure is not None and closure < base:
        _refuse(
            FirmOntologyCandidateRefusalReason.EVIDENCE_INVALID,
            "closure availability predates the mapping evidence",
        )
    return _MappingDecision(
        valid_from=valid_from,
        valid_to=valid_to,
        raw_label=raw_label,
        ordered_rank=ordered_rank,
        source_evidence_id=source_id,
        source_evidence_sha256=source_sha,
        available_at=available_at,
        valid_to_available_at=closure_raw,
        quality=quality,
    )


def _interval_intersects_span(
    interval: tuple[str, str | None], first: date, last: date
) -> bool:
    start = parse_date(interval[0], "valid_from")
    end = None if interval[1] is None else parse_date(interval[1], "valid_to")
    return start <= last and (end is None or first < end)


def _validate_one_firm(
    *,
    owner_row: dict[str, Any],
    template_row: dict[str, Any],
    evidence_row: dict[str, Any],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object], str]:
    _exact_keys(
        owner_row,
        _OUTER_KEYS,
        FirmOntologyCandidateRefusalReason.TEMPLATE_BINDING_CHANGED,
        "owner adjudication outer row",
    )
    expected_outer = dict(template_row)
    expected_outer.pop("owner_adjudication")
    observed_outer = dict(owner_row)
    raw_adjudication = observed_outer.pop("owner_adjudication")
    if canonical_json_bytes(observed_outer) != canonical_json_bytes(expected_outer):
        _refuse(
            FirmOntologyCandidateRefusalReason.TEMPLATE_BINDING_CHANGED,
            "owner adjudication changed packet-derived ranking or firm fields",
        )
    adjudication = _exact_keys(
        raw_adjudication,
        _ADJUDICATION_KEYS,
        FirmOntologyCandidateRefusalReason.REVIEW_INCOMPLETE,
        "owner adjudication",
    )
    if adjudication["review_status"] != OWNER_ADJUDICATION_STATUS:
        _refuse(
            FirmOntologyCandidateRefusalReason.REVIEW_INCOMPLETE,
            "every firm review status must be owner_reviewed_complete",
        )
    try:
        reviewer = require_text(adjudication["reviewer"], "reviewer")
        reviewed_at = adjudication["reviewed_at"]
        review_instant = parse_utc_timestamp(reviewed_at, "reviewed_at")
        canonical_name = require_text(
            adjudication["canonical_firm_name"], "canonical_firm_name"
        )
        if adjudication["notes"] is not None:
            require_text(adjudication["notes"], "notes", maximum_length=4096)
    except CanonicalEvidenceError as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.REVIEW_INCOMPLETE,
            "reviewer, review time, canonical name, or notes is invalid",
        ) from exc
    try:
        scope = RatingScope(adjudication["scope"])
    except (TypeError, ValueError) as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.SCOPE_INVALID,
            "scope must be one exact reviewed RatingScope value",
        ) from exc
    intervals = _validated_intervals(adjudication["validity_intervals"])
    if type(adjudication["ordered_scale"]) is not list:
        _refuse(
            FirmOntologyCandidateRefusalReason.SCALE_INCOMPLETE,
            "ordered_scale must be an explicit array",
        )
    if type(adjudication["alias_mappings"]) is not list:
        _refuse(
            FirmOntologyCandidateRefusalReason.SCALE_INCOMPLETE,
            "alias_mappings must be an explicit array",
        )
    if (
        len(adjudication["ordered_scale"]) > MAX_PRIMARY_MAPPINGS_PER_FIRM
        or len(adjudication["alias_mappings"]) > MAX_ALIAS_MAPPINGS_PER_FIRM
        or len(adjudication["ordered_scale"])
        + len(adjudication["alias_mappings"])
        > MAX_MAPPINGS_PER_FIRM
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED,
            "one firm exceeds a fixed primary, alias, or total mapping ceiling",
        )
    primary = tuple(
        _mapping_decision(
            item,
            quality=MappingQuality.REVIEWED_PRIMARY,
            intervals=intervals,
        )
        for item in adjudication["ordered_scale"]
    )
    aliases = tuple(
        _mapping_decision(
            item,
            quality=MappingQuality.REVIEWED_ALIAS,
            intervals=intervals,
        )
        for item in adjudication["alias_mappings"]
    )
    if any(
        parse_utc_timestamp(item.available_at, "historical evidence available_at")
        > review_instant
        or (
            item.valid_to_available_at is not None
            and parse_utc_timestamp(
                item.valid_to_available_at,
                "historical closure available_at",
            )
            > review_instant
        )
        for item in primary + aliases
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.EVIDENCE_INVALID,
            "mapping evidence cannot become available after its explicit review time",
        )
    primary_by_interval: dict[
        tuple[str, str | None], list[_MappingDecision]
    ] = defaultdict(list)
    aliases_by_interval: dict[
        tuple[str, str | None], list[_MappingDecision]
    ] = defaultdict(list)
    for item in primary:
        primary_by_interval[(item.valid_from, item.valid_to)].append(item)
    for item in aliases:
        aliases_by_interval[(item.valid_from, item.valid_to)].append(item)
    for interval in intervals:
        levels = primary_by_interval[interval]
        if len(levels) < 2:
            _refuse(
                FirmOntologyCandidateRefusalReason.SCALE_INCOMPLETE,
                "every validity interval needs at least two primary scale levels",
            )
        ranks = [item.ordered_rank for item in levels]
        if len(set(ranks)) != len(ranks) or set(ranks) != set(range(1, len(levels) + 1)):
            _refuse(
                FirmOntologyCandidateRefusalReason.SCALE_INCOMPLETE,
                "every interval scale must cover contiguous unique ranks 1 through N",
            )
        labels = [item.raw_label for item in levels]
        if len(set(labels)) != len(labels):
            _refuse(
                FirmOntologyCandidateRefusalReason.DUPLICATE_MAPPING,
                "one interval repeats a primary raw label",
            )
        aliases_for_interval = aliases_by_interval[interval]
        if any(item.ordered_rank > len(levels) for item in aliases_for_interval):
            _refuse(
                FirmOntologyCandidateRefusalReason.SCALE_INCOMPLETE,
                "an alias rank falls outside its interval scale",
            )
        combined = levels + aliases_for_interval
        combined_labels = [item.raw_label for item in combined]
        if len(set(combined_labels)) != len(combined_labels):
            _refuse(
                FirmOntologyCandidateRefusalReason.DUPLICATE_MAPPING,
                "one interval maps the same raw label more than once",
            )
        ranks_by_casefolded: dict[str, set[int]] = defaultdict(set)
        for item in combined:
            ranks_by_casefolded[item.raw_label.casefold()].add(item.ordered_rank)
        if any(len(values) != 1 for values in ranks_by_casefolded.values()):
            _refuse(
                FirmOntologyCandidateRefusalReason.DUPLICATE_MAPPING,
                "case variants of one label map to different ranks",
            )

    _exact_keys(
        evidence_row,
        _FIRM_EVIDENCE_KEYS,
        FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
        "authenticated firm evidence row",
    )
    try:
        first_observed = parse_date(evidence_row["first_event_date"], "first_event_date")
        last_observed = parse_date(evidence_row["last_event_date"], "last_event_date")
    except CanonicalEvidenceError as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "authenticated firm evidence dates are invalid",
        ) from exc
    first_interval = parse_date(intervals[0][0], "valid_from")
    last_interval_end = (
        None if intervals[-1][1] is None else parse_date(intervals[-1][1], "valid_to")
    )
    if first_interval > first_observed or (
        last_interval_end is not None and last_observed >= last_interval_end
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.OBSERVED_DATE_UNCOVERED,
            "declared intervals do not cover the firm's full observed date span",
        )
    raw_observed = evidence_row["observed_labels"]
    if type(raw_observed) is not list:
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "authenticated observed-label diagnostics changed type",
        )
    observed_spans: dict[str, tuple[date, date]] = {}
    for item in raw_observed:
        observed = _exact_keys(
            item,
            _OBSERVED_LABEL_KEYS,
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "authenticated observed label",
        )
        try:
            raw_label = require_text(observed["raw_label"], "observed raw label")
            first = parse_date(observed["first_event_date"], "label first_event_date")
            last = parse_date(observed["last_event_date"], "label last_event_date")
        except CanonicalEvidenceError as exc:
            raise FirmOntologyCandidateError(
                FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
                "authenticated observed-label diagnostics are invalid",
            ) from exc
        prior = observed_spans.get(raw_label)
        observed_spans[raw_label] = (
            first if prior is None else min(first, prior[0]),
            last if prior is None else max(last, prior[1]),
        )
    mapped_by_interval = {
        interval: {
            item.raw_label for item in primary_by_interval[interval] + aliases_by_interval[interval]
        }
        for interval in intervals
    }
    for raw_label, (first, last) in observed_spans.items():
        relevant = tuple(
            interval for interval in intervals if _interval_intersects_span(interval, first, last)
        )
        if not relevant or any(
            raw_label not in mapped_by_interval[interval] for interval in relevant
        ):
            _refuse(
                FirmOntologyCandidateRefusalReason.OBSERVED_LABEL_UNMAPPED,
                "an observed label lacks an explicit mapping throughout its observed span",
            )

    provider_firm_id = owner_row["provider_firm_id"]
    entries: list[dict[str, object]] = []
    availability: list[dict[str, object]] = []
    for interval in intervals:
        scale_size = len(primary_by_interval[interval])
        decisions = primary_by_interval[interval] + aliases_by_interval[interval]
        for decision in decisions:
            entry = {
                "provider_firm_id": provider_firm_id,
                "firm_name": canonical_name,
                "valid_from": decision.valid_from,
                "valid_to": decision.valid_to,
                "raw_label": decision.raw_label,
                "ordered_rank": decision.ordered_rank,
                "scale_size": scale_size,
                "scope": scope.value,
                "mapping_quality": decision.quality.value,
                "reviewer": reviewer,
                "source_evidence_id": decision.source_evidence_id,
                "source_evidence_sha256": decision.source_evidence_sha256,
            }
            try:
                parsed = FirmRatingMapEntry.from_record(entry)
            except (CanonicalEvidenceError, TypeError, ValueError) as exc:
                raise FirmOntologyCandidateError(
                    FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
                    "a rendered ontology entry is not loader-compatible",
                ) from exc
            entry = parsed.to_record()
            entry_sha = sha256_bytes(canonical_json_bytes(entry))
            availability_entry = {
                "ontology_entry_sha256": entry_sha,
                "source_evidence_id": decision.source_evidence_id,
                "source_evidence_sha256": decision.source_evidence_sha256,
                "available_at": decision.available_at,
                "valid_to_available_at": decision.valid_to_available_at,
            }
            try:
                FirmOntologyAvailabilityEntry(**availability_entry)
            except (CanonicalEvidenceError, TypeError, ValueError) as exc:
                raise FirmOntologyCandidateError(
                    FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
                    "a rendered availability entry is not loader-compatible",
                ) from exc
            entries.append(entry)
            availability.append(availability_entry)
    diagnostic = {
        "ranking_ordinal": owner_row["ranking_ordinal"],
        "provider_firm_id": provider_firm_id,
        "first_observed_event_date": first_observed.isoformat(),
        "last_observed_event_date": last_observed.isoformat(),
        "validity_interval_count": len(intervals),
        "primary_scale_entry_count": len(primary),
        "alias_entry_count": len(aliases),
        "observed_label_count": len(observed_spans),
        "mapped_observed_label_count": len(observed_spans),
        "full_observed_date_span_covered": True,
        "all_observed_labels_covered": True,
        "historical_availability_explicit_for_every_entry": True,
        "review_status_explicit": True,
        "reviewer_and_time_explicit": True,
        "order_scope_aliases_and_intervals_inferred": False,
    }
    return entries, availability, diagnostic, reviewed_at


def _content_addressed_record(
    raw: dict[str, object], *, identifier_field: str, prefix: str
) -> dict[str, object]:
    seed = dict(raw)
    seed[identifier_field] = None
    seed[identifier_field.replace("_id", "_sha256")] = None
    digest = sha256_bytes(canonical_json_bytes(seed))
    raw[identifier_field] = f"{prefix}{digest[:24]}"
    raw[identifier_field.replace("_id", "_sha256")] = digest
    return raw


_PINNED_CONTENT_ADDRESSED_RECORD = _content_addressed_record


def require_firm_ontology_candidate_bundle(
    value: FirmOntologyCandidateBundle,
) -> FirmOntologyCandidateBundle:
    """Require exact, unchanged authority minted by this process's builder."""

    _require_dependencies()
    if type(value) is not FirmOntologyCandidateBundle:
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "candidate bundle requires the exact builder type",
        )
    current_pid = os.getpid()
    if current_pid != _BUNDLE_AUTHORITY_PID:
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "candidate bundle authority belongs to another process",
        )
    with _BUNDLE_AUTHORITY_LOCK:
        authority = _BUNDLE_AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or authority[1] != _bundle_fingerprint(value)
        or authority[2] != current_pid
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "candidate bundle is not current builder authority",
        )
    return _PINNED_CANDIDATE_CONTENT_REQUIRE(value)


def _json_object(payload: bytes, name: str) -> dict[str, Any]:
    """Decode one internal candidate object without relaxing canonical bytes."""

    try:
        raw = strict_json_loads(decode_utf8(payload, name), name)
    except CanonicalEvidenceError as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            f"{name} is not strict JSON",
        ) from exc
    if type(raw) is not dict or canonical_json_bytes(raw) != payload:
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            f"{name} is not a canonical object",
        )
    return raw


def _require_candidate_content_bindings(
    value: FirmOntologyCandidateBundle,
) -> FirmOntologyCandidateBundle:
    """Independently recompute every candidate address and cross-binding."""

    false_capabilities = {
        "independently_reviewed": False,
        "production_authority": False,
        "provider_access": False,
        "quantconnect_access": False,
        "outcome_access": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    if (
        value.schema != CANDIDATE_SCHEMA
        or type(value.firm_count) is not int
        or value.firm_count != EXPECTED_ADJUDICATION_FIRM_COUNT
        or type(value.ontology_entry_count) is not int
        or value.ontology_entry_count < EXPECTED_ADJUDICATION_FIRM_COUNT * 2
        or value.ontology_entry_count > MAX_ONTOLOGY_ENTRY_COUNT
        or type(value.owner_adjudication_byte_count) is not int
        or not 0
        < value.owner_adjudication_byte_count
        <= MAX_OWNER_ADJUDICATION_BYTES
        or type(value.owner_adjudication_bytes) is not bytes
        or value.owner_adjudication_byte_count != len(value.owner_adjudication_bytes)
        or value.owner_adjudication_sha256
        != sha256_bytes(value.owner_adjudication_bytes)
        or any(
            type(payload) is not bytes or not 0 < len(payload) <= maximum
            for payload, maximum in (
                (value.ontology_bytes, MAX_CANDIDATE_FILE_BYTES),
                (value.availability_bytes, MAX_CANDIDATE_FILE_BYTES),
                (
                    value.availability_review_candidate_bytes,
                    MAX_AVAILABILITY_REVIEW_BYTES,
                ),
                (value.registry_candidate_bytes, MAX_CANDIDATE_FILE_BYTES),
                (value.coverage_diagnostic_bytes, MAX_CANDIDATE_FILE_BYTES),
            )
        )
        or any(
            type(getattr(value, name)) is not bool
            or getattr(value, name) is not expected
            for name, expected in false_capabilities.items()
        )
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "candidate bundle authority or owner binding changed",
        )

    ontology = _json_object(value.ontology_bytes, "ontology")
    if set(ontology) != {
        "schema",
        "ontology_id",
        "version",
        "status",
        "reviewed_at",
        "entries",
    }:
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "ontology candidate fields changed",
        )
    entries = ontology["entries"]
    if type(entries) is not list or len(entries) != value.ontology_entry_count:
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "ontology candidate entry census changed",
        )
    try:
        parsed_entries = tuple(_PINNED_ENTRY_TYPE.from_record(item) for item in entries)
        _PINNED_VALIDATE_ENTRY_SET(parsed_entries)
        parse_utc_timestamp(ontology["reviewed_at"], "ontology reviewed_at")
    except (CanonicalEvidenceError, TypeError, ValueError) as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "ontology candidate is not loader-compatible",
        ) from exc
    semantic_seed = {
        "schema": FIRM_ONTOLOGY_SCHEMA,
        "source_packet_id": value.packet_id,
        "source_packet_sha256": value.packet_sha256,
        "owner_adjudication_sha256": value.owner_adjudication_sha256,
        "entries": entries,
    }
    semantic_sha = sha256_bytes(canonical_json_bytes(semantic_seed))
    expected_ontology_id = f"arv2-firm-rating-ontology-{semantic_sha[:24]}"
    if (
        ontology["schema"] != FIRM_ONTOLOGY_SCHEMA
        or ontology["ontology_id"] != expected_ontology_id
        or ontology["version"] != f"owner-adjudicated-{semantic_sha[:24]}"
        or ontology["status"] != "reviewed"
        or value.ontology_id != expected_ontology_id
        or value.ontology_sha256 != sha256_bytes(value.ontology_bytes)
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "ontology candidate semantic address or lineage changed",
        )

    availability = _json_object(value.availability_bytes, "availability")
    if set(availability) != {
        "schema",
        "ontology_id",
        "ontology_sha256",
        "entries",
    }:
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "availability candidate fields changed",
        )
    availability_entries = availability["entries"]
    if type(availability_entries) is not list:
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "availability candidate entries changed type",
        )
    try:
        parsed_availability = tuple(
            _PINNED_AVAILABILITY_ENTRY_TYPE(**item)
            for item in availability_entries
            if type(item) is dict
        )
    except (CanonicalEvidenceError, TypeError, ValueError) as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "availability candidate is not loader-compatible",
        ) from exc
    entry_bindings = {
        sha256_bytes(canonical_json_bytes(entry)): (
            entry["source_evidence_id"],
            entry["source_evidence_sha256"],
        )
        for entry in entries
    }
    availability_projection = tuple(item.to_record() for item in parsed_availability)
    if (
        len(parsed_availability) != len(availability_entries)
        or len(availability_entries) != value.ontology_entry_count
        or availability_entries
        != sorted(
            availability_entries,
            key=lambda item: item["ontology_entry_sha256"],
        )
        or len({item["ontology_entry_sha256"] for item in availability_entries})
        != len(availability_entries)
        or {item["ontology_entry_sha256"] for item in availability_entries}
        != set(entry_bindings)
        or any(
            entry_bindings[item["ontology_entry_sha256"]]
            != (item["source_evidence_id"], item["source_evidence_sha256"])
            for item in availability_entries
        )
        or list(availability_projection) != availability_entries
        or availability["schema"] != FIRM_AVAILABILITY_SCHEMA
        or availability["ontology_id"] != value.ontology_id
        or availability["ontology_sha256"] != value.ontology_sha256
        or value.availability_sha256 != sha256_bytes(value.availability_bytes)
        or value.availability_id
        != f"arv2-firm-availability-{value.availability_sha256[:24]}"
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "availability candidate address or ontology binding changed",
        )

    availability_review = _json_object(
        value.availability_review_candidate_bytes,
        "availability review candidate",
    )
    expected_review = {
        "schema": FIRM_AVAILABILITY_REVIEW_SCHEMA,
        "availability_sha256": value.availability_sha256,
        "availability_byte_count": len(value.availability_bytes),
        "ontology_id": value.ontology_id,
        "ontology_sha256": value.ontology_sha256,
        "entry_count": value.ontology_entry_count,
        "entry_projection_sha256": sha256_bytes(
            canonical_json_bytes(availability_entries)
        ),
        "status": PENDING_REVIEW_STATUS,
        "receipt_id": None,
        "receipt_sha256": None,
        "complete_ontology_entry_census_verified": False,
        "historical_availability_verified_from_external_source_evidence": False,
        "no_review_time_or_valid_from_imputation_verified": False,
        "contains_outcome_or_price": False,
    }
    if (
        availability_review != expected_review
        or value.availability_review_candidate_sha256
        != sha256_bytes(value.availability_review_candidate_bytes)
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "availability review candidate binding changed",
        )

    registry = _json_object(value.registry_candidate_bytes, "registry candidate")
    if set(registry) != {
        "schema",
        "candidate_id",
        "candidate_sha256",
        "status",
        "registry_schema",
        "registry_path",
        "ontology_byte_count",
        "entry",
    } or type(registry.get("entry")) is not dict:
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "registry candidate fields changed",
        )
    registry_entry = registry["entry"]
    expected_artifact_path = (
        "research/analyst_revisions_v2/specs/" f"{value.ontology_id}.json"
    )
    expected_registry_path = FIRM_ONTOLOGY_REGISTRY_PATH.relative_to(
        FIRM_ONTOLOGY_REGISTRY_PATH.parents[3]
    ).as_posix()
    registry_seed = dict(registry)
    registry_seed["candidate_id"] = None
    registry_seed["candidate_sha256"] = None
    expected_registry_sha = sha256_bytes(canonical_json_bytes(registry_seed))
    expected_registry_id = f"arv2-firm-registry-candidate-{expected_registry_sha[:24]}"
    if (
        set(registry_entry) != {
            "artifact_id",
            "artifact_sha256",
            "artifact_path",
            "review_commit",
            "reviewed_by",
            "reviewed_at",
        }
        or registry["schema"] != REGISTRY_CANDIDATE_SCHEMA
        or registry["candidate_id"] != expected_registry_id
        or registry["candidate_sha256"] != expected_registry_sha
        or registry["status"] != PENDING_REVIEW_STATUS
        or registry["registry_schema"] != FIRM_ONTOLOGY_REGISTRY_SCHEMA
        or registry["registry_path"] != expected_registry_path
        or registry["ontology_byte_count"] != len(value.ontology_bytes)
        or registry_entry
        != {
            "artifact_id": value.ontology_id,
            "artifact_sha256": value.ontology_sha256,
            "artifact_path": expected_artifact_path,
            "review_commit": None,
            "reviewed_by": None,
            "reviewed_at": None,
        }
        or value.registry_candidate_id != expected_registry_id
        or value.registry_candidate_sha256 != expected_registry_sha
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "registry candidate content address or ontology binding changed",
        )

    coverage = _json_object(value.coverage_diagnostic_bytes, "coverage diagnostic")
    coverage_seed = dict(coverage)
    coverage_seed["diagnostic_id"] = None
    coverage_seed["diagnostic_sha256"] = None
    expected_coverage_sha = sha256_bytes(canonical_json_bytes(coverage_seed))
    expected_coverage_id = f"arv2-firm-coverage-{expected_coverage_sha[:24]}"
    firms = coverage.get("firms")
    if (
        set(coverage) != {
            "schema",
            "diagnostic_id",
            "diagnostic_sha256",
            "packet_id",
            "packet_sha256",
            "owner_adjudication_sha256",
            "ontology_id",
            "ontology_sha256",
            "expected_firm_count",
            "reviewed_firm_count",
            "ontology_entry_count",
            "all_selected_firms_present_once",
            "all_observed_dates_and_labels_covered",
            "all_orders_scopes_aliases_intervals_and_evidence_explicit",
            "independently_reviewed",
            "production_authority",
            "firms",
        }
        or coverage["schema"] != COVERAGE_SCHEMA
        or coverage["diagnostic_id"] != expected_coverage_id
        or coverage["diagnostic_sha256"] != expected_coverage_sha
        or coverage["packet_id"] != value.packet_id
        or coverage["packet_sha256"] != value.packet_sha256
        or coverage["owner_adjudication_sha256"] != value.owner_adjudication_sha256
        or coverage["ontology_id"] != value.ontology_id
        or coverage["ontology_sha256"] != value.ontology_sha256
        or coverage["expected_firm_count"] != EXPECTED_ADJUDICATION_FIRM_COUNT
        or coverage["reviewed_firm_count"] != value.firm_count
        or coverage["ontology_entry_count"] != value.ontology_entry_count
        or coverage["all_selected_firms_present_once"] is not True
        or coverage["all_observed_dates_and_labels_covered"] is not True
        or coverage["all_orders_scopes_aliases_intervals_and_evidence_explicit"]
        is not True
        or coverage["independently_reviewed"] is not False
        or coverage["production_authority"] is not False
        or type(firms) is not list
        or len(firms) != value.firm_count
        or value.coverage_diagnostic_id != expected_coverage_id
        or value.coverage_diagnostic_sha256 != expected_coverage_sha
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "coverage diagnostic content address or lineage changed",
        )

    bundle_seed = {
        "schema": CANDIDATE_SCHEMA,
        "bundle_id": None,
        "bundle_sha256": None,
        "packet_id": value.packet_id,
        "packet_sha256": value.packet_sha256,
        "owner_adjudication_sha256": value.owner_adjudication_sha256,
        "owner_adjudication_byte_count": value.owner_adjudication_byte_count,
        "firm_count": value.firm_count,
        "ontology_entry_count": value.ontology_entry_count,
        "ontology_id": value.ontology_id,
        "ontology_sha256": value.ontology_sha256,
        "availability_id": value.availability_id,
        "availability_sha256": value.availability_sha256,
        "availability_review_candidate_sha256": (
            value.availability_review_candidate_sha256
        ),
        "registry_candidate_id": value.registry_candidate_id,
        "registry_candidate_sha256": value.registry_candidate_sha256,
        "coverage_diagnostic_id": value.coverage_diagnostic_id,
        "coverage_diagnostic_sha256": value.coverage_diagnostic_sha256,
        "capabilities": false_capabilities,
    }
    expected_bundle_sha = sha256_bytes(canonical_json_bytes(bundle_seed))
    if (
        value.bundle_sha256 != expected_bundle_sha
        or value.bundle_id != f"arv2-firm-candidate-bundle-{expected_bundle_sha[:24]}"
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "candidate bundle content address changed",
        )
    return value


_PINNED_CANDIDATE_CONTENT_REQUIRE = _require_candidate_content_bindings


def _select_authenticated_evidence_rows(
    rows: Iterable[dict[str, object]],
    *,
    selected_ids: tuple[str, ...],
    expected_row_count: int,
) -> dict[str, dict[str, object]]:
    """Exhaust all evidence while retaining only the predeclared 74 firms."""

    wanted = frozenset(selected_ids)
    selected: dict[str, dict[str, object]] = {}
    previous_id: str | None = None
    observed = 0
    for row in rows:
        observed += 1
        if observed > expected_row_count or type(row) is not dict:
            _refuse(
                FirmOntologyCandidateRefusalReason.PACKET_AUTHENTICATION_FAILED,
                "authenticated firm evidence census or row type changed",
            )
        firm_id = row.get("provider_firm_id")
        if type(firm_id) is not str or not firm_id:
            _refuse(
                FirmOntologyCandidateRefusalReason.PACKET_AUTHENTICATION_FAILED,
                "authenticated firm evidence identity changed",
            )
        if previous_id is not None and firm_id <= previous_id:
            _refuse(
                FirmOntologyCandidateRefusalReason.PACKET_AUTHENTICATION_FAILED,
                "authenticated firm evidence is duplicated or out of order",
            )
        previous_id = firm_id
        if firm_id in wanted:
            if firm_id in selected:
                _refuse(
                    FirmOntologyCandidateRefusalReason.PACKET_AUTHENTICATION_FAILED,
                    "selected firm evidence is duplicated",
                )
            selected[firm_id] = row
    if observed != expected_row_count or set(selected) != wanted:
        _refuse(
            FirmOntologyCandidateRefusalReason.PACKET_AUTHENTICATION_FAILED,
            "selected firms lack a complete authenticated evidence census",
        )
    return selected


def build_firm_ontology_candidate_bundle(
    *,
    review_packet: PhysicalFirmOntologyReviewPacket,
    owner_adjudication_path: Path,
) -> FirmOntologyCandidateBundle:
    """Render loader-compatible candidates without granting review authority."""

    _require_dependencies()
    if type(review_packet) is not _PINNED_PACKET_TYPE:
        _refuse(
            FirmOntologyCandidateRefusalReason.PACKET_AUTHENTICATION_FAILED,
            "review packet must use the exact authority type",
        )
    try:
        packet = _PINNED_PACKET_REQUIRE(review_packet)
    except _packet.PhysicalFirmOntologyReviewPacketError as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.PACKET_AUTHENTICATION_FAILED,
            "physical firm-review packet did not reauthenticate",
        ) from exc
    if (
        packet.adjudication_firm_count != EXPECTED_ADJUDICATION_FIRM_COUNT
        or packet.ranked_firm_count < EXPECTED_ADJUDICATION_FIRM_COUNT
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.PACKET_CENSUS_NOT_74,
            "candidate composition requires the predeclared top 74 firms",
        )
    try:
        template_rows = tuple(_PINNED_TEMPLATE_ITERATOR(packet))
    except _packet.PhysicalFirmOntologyReviewPacketError as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.PACKET_AUTHENTICATION_FAILED,
            "physical firm-review rows did not reauthenticate",
        ) from exc
    if len(template_rows) != EXPECTED_ADJUDICATION_FIRM_COUNT:
        _refuse(
            FirmOntologyCandidateRefusalReason.PACKET_CENSUS_NOT_74,
            "authenticated adjudication template does not contain 74 rows",
        )
    template_ids = tuple(row.get("provider_firm_id") for row in template_rows)
    if (
        tuple(row.get("ranking_ordinal") for row in template_rows)
        != tuple(range(1, EXPECTED_ADJUDICATION_FIRM_COUNT + 1))
        or any(type(item) is not str for item in template_ids)
        or len(set(template_ids)) != EXPECTED_ADJUDICATION_FIRM_COUNT
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.PACKET_CENSUS_NOT_74,
            "authenticated template firm identities or ranking are not exact",
        )
    try:
        evidence_by_id = _select_authenticated_evidence_rows(
            _PINNED_EVIDENCE_ITERATOR(packet),
            selected_ids=template_ids,
            expected_row_count=packet.firm_count,
        )
    except _packet.PhysicalFirmOntologyReviewPacketError as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.PACKET_AUTHENTICATION_FAILED,
            "physical firm-review rows did not reauthenticate",
        ) from exc

    owner_bytes, owner_rows = _read_owner_file(owner_adjudication_path)
    if len(owner_rows) != EXPECTED_ADJUDICATION_FIRM_COUNT:
        _refuse(
            FirmOntologyCandidateRefusalReason.ADJUDICATION_CENSUS_CHANGED,
            "owner adjudication must contain exactly 74 rows",
        )
    if tuple(row.get("provider_firm_id") for row in owner_rows) != template_ids:
        _refuse(
            FirmOntologyCandidateRefusalReason.ADJUDICATION_CENSUS_CHANGED,
            "owner adjudication omitted, added, duplicated, or reordered a firm",
        )

    ontology_entries: list[dict[str, object]] = []
    availability_entries: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    reviewed_at_values: list[str] = []
    projected_ontology_entry_bytes = 2
    projected_availability_entry_bytes = 2
    for owner_row, template_row, firm_id in zip(
        owner_rows, template_rows, template_ids, strict=True
    ):
        entries, availability, diagnostic, reviewed_at = _validate_one_firm(
            owner_row=owner_row,
            template_row=template_row,
            evidence_row=evidence_by_id[firm_id],
        )
        next_ontology_bytes = sum(
            len(canonical_json_bytes(entry)) for entry in entries
        )
        next_availability_bytes = sum(
            len(canonical_json_bytes(entry)) for entry in availability
        )
        if (
            len(ontology_entries) + len(entries) > MAX_ONTOLOGY_ENTRY_COUNT
            or projected_ontology_entry_bytes + next_ontology_bytes
            > MAX_PROJECTED_ENTRY_BYTES
            or projected_availability_entry_bytes + next_availability_bytes
            > MAX_PROJECTED_ENTRY_BYTES
        ):
            _refuse(
                FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED,
                "candidate entry census or projected output bytes exceed fixed bounds",
            )
        projected_ontology_entry_bytes += next_ontology_bytes
        projected_availability_entry_bytes += next_availability_bytes
        ontology_entries.extend(entries)
        availability_entries.extend(availability)
        diagnostics.append(diagnostic)
        reviewed_at_values.append(reviewed_at)
    ontology_entries.sort(
        key=lambda entry: (
            entry["provider_firm_id"],
            entry["valid_from"],
            "9999-12-31" if entry["valid_to"] is None else entry["valid_to"],
            entry["ordered_rank"],
            entry["raw_label"].casefold(),
            entry["raw_label"],
        )
    )
    if not ontology_entries:
        _refuse(
            FirmOntologyCandidateRefusalReason.SCALE_INCOMPLETE,
            "the 74 reviewed firms yielded no ontology entries",
        )
    if len(
        {
            (
                item["provider_firm_id"],
                item["valid_from"],
                item["valid_to"],
                item["raw_label"],
            )
            for item in ontology_entries
        }
    ) != len(ontology_entries):
        _refuse(
            FirmOntologyCandidateRefusalReason.DUPLICATE_MAPPING,
            "rendered ontology repeats a firm/interval/raw-label mapping",
        )
    evidence_hash_by_id: dict[str, str] = {}
    for entry in ontology_entries:
        evidence_id = entry["source_evidence_id"]
        evidence_sha = entry["source_evidence_sha256"]
        prior_sha = evidence_hash_by_id.setdefault(evidence_id, evidence_sha)
        if prior_sha != evidence_sha:
            _refuse(
                FirmOntologyCandidateRefusalReason.EVIDENCE_INVALID,
                "one source evidence ID is associated with conflicting hashes",
            )
    try:
        parsed_entries = tuple(
            FirmRatingMapEntry.from_record(item) for item in ontology_entries
        )
        _ontology._validate_entry_set(parsed_entries)
    except (CanonicalEvidenceError, TypeError, ValueError) as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "rendered ontology entry set is not loader-compatible",
        ) from exc

    owner_sha = sha256_bytes(owner_bytes)
    ontology_semantic = {
        "schema": FIRM_ONTOLOGY_SCHEMA,
        "source_packet_id": packet.packet_id,
        "source_packet_sha256": packet.packet_sha256,
        "owner_adjudication_sha256": owner_sha,
        "entries": ontology_entries,
    }
    semantic_sha = sha256_bytes(canonical_json_bytes(ontology_semantic))
    ontology_id = f"arv2-firm-rating-ontology-{semantic_sha[:24]}"
    ontology_record = {
        "schema": FIRM_ONTOLOGY_SCHEMA,
        "ontology_id": ontology_id,
        "version": f"owner-adjudicated-{semantic_sha[:24]}",
        "status": "reviewed",
        "reviewed_at": max(reviewed_at_values),
        "entries": ontology_entries,
    }
    ontology_bytes = canonical_json_bytes(ontology_record)
    if len(ontology_bytes) > MAX_CANDIDATE_FILE_BYTES:
        _refuse(
            FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED,
            "firm ontology candidate exceeds the downstream file byte bound",
        )
    ontology_sha = sha256_bytes(ontology_bytes)

    availability_entries.sort(key=lambda item: item["ontology_entry_sha256"])
    if len({item["ontology_entry_sha256"] for item in availability_entries}) != len(
        availability_entries
    ):
        _refuse(
            FirmOntologyCandidateRefusalReason.DUPLICATE_MAPPING,
            "rendered ontology entry hashes are not unique",
        )
    availability_record = {
        "schema": FIRM_AVAILABILITY_SCHEMA,
        "ontology_id": ontology_id,
        "ontology_sha256": ontology_sha,
        "entries": availability_entries,
    }
    availability_bytes = canonical_json_bytes(availability_record)
    if len(availability_bytes) > MAX_CANDIDATE_FILE_BYTES:
        _refuse(
            FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED,
            "firm availability candidate exceeds the downstream file byte bound",
        )
    availability_sha = sha256_bytes(availability_bytes)
    availability_id = f"arv2-firm-availability-{availability_sha[:24]}"
    entry_projection_sha = sha256_bytes(canonical_json_bytes(availability_entries))
    availability_review_candidate = {
        "schema": FIRM_AVAILABILITY_REVIEW_SCHEMA,
        "availability_sha256": availability_sha,
        "availability_byte_count": len(availability_bytes),
        "ontology_id": ontology_id,
        "ontology_sha256": ontology_sha,
        "entry_count": len(availability_entries),
        "entry_projection_sha256": entry_projection_sha,
        "status": PENDING_REVIEW_STATUS,
        "receipt_id": None,
        "receipt_sha256": None,
        "complete_ontology_entry_census_verified": False,
        "historical_availability_verified_from_external_source_evidence": False,
        "no_review_time_or_valid_from_imputation_verified": False,
        "contains_outcome_or_price": False,
    }
    availability_review_bytes = canonical_json_bytes(availability_review_candidate)
    if len(availability_review_bytes) > MAX_AVAILABILITY_REVIEW_BYTES:
        _refuse(
            FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED,
            "availability review candidate exceeds its downstream byte bound",
        )

    artifact_path = (
        "research/analyst_revisions_v2/specs/"
        f"{ontology_id}.json"
    )
    registry_candidate: dict[str, object] = {
        "schema": REGISTRY_CANDIDATE_SCHEMA,
        "candidate_id": None,
        "candidate_sha256": None,
        "status": PENDING_REVIEW_STATUS,
        "registry_schema": FIRM_ONTOLOGY_REGISTRY_SCHEMA,
        "registry_path": FIRM_ONTOLOGY_REGISTRY_PATH.relative_to(
            FIRM_ONTOLOGY_REGISTRY_PATH.parents[3]
        ).as_posix(),
        "ontology_byte_count": len(ontology_bytes),
        "entry": {
            "artifact_id": ontology_id,
            "artifact_sha256": ontology_sha,
            "artifact_path": artifact_path,
            "review_commit": None,
            "reviewed_by": None,
            "reviewed_at": None,
        },
    }
    _content_addressed_record(
        registry_candidate,
        identifier_field="candidate_id",
        prefix="arv2-firm-registry-candidate-",
    )
    registry_candidate_bytes = canonical_json_bytes(registry_candidate)
    if len(registry_candidate_bytes) > MAX_CANDIDATE_FILE_BYTES:
        _refuse(
            FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED,
            "registry candidate exceeds the downstream file byte bound",
        )

    coverage_record: dict[str, object] = {
        "schema": COVERAGE_SCHEMA,
        "diagnostic_id": None,
        "diagnostic_sha256": None,
        "packet_id": packet.packet_id,
        "packet_sha256": packet.packet_sha256,
        "owner_adjudication_sha256": owner_sha,
        "ontology_id": ontology_id,
        "ontology_sha256": ontology_sha,
        "expected_firm_count": EXPECTED_ADJUDICATION_FIRM_COUNT,
        "reviewed_firm_count": len(diagnostics),
        "ontology_entry_count": len(ontology_entries),
        "all_selected_firms_present_once": True,
        "all_observed_dates_and_labels_covered": True,
        "all_orders_scopes_aliases_intervals_and_evidence_explicit": True,
        "independently_reviewed": False,
        "production_authority": False,
        "firms": diagnostics,
    }
    _content_addressed_record(
        coverage_record,
        identifier_field="diagnostic_id",
        prefix="arv2-firm-coverage-",
    )
    coverage_bytes = canonical_json_bytes(coverage_record)
    if len(coverage_bytes) > MAX_CANDIDATE_FILE_BYTES:
        _refuse(
            FirmOntologyCandidateRefusalReason.CANDIDATE_CAPACITY_EXCEEDED,
            "coverage diagnostic exceeds the downstream file byte bound",
        )

    false_capabilities = {
        "independently_reviewed": False,
        "production_authority": False,
        "provider_access": False,
        "quantconnect_access": False,
        "outcome_access": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    bundle_seed: dict[str, object] = {
        "schema": CANDIDATE_SCHEMA,
        "bundle_id": None,
        "bundle_sha256": None,
        "packet_id": packet.packet_id,
        "packet_sha256": packet.packet_sha256,
        "owner_adjudication_sha256": owner_sha,
        "owner_adjudication_byte_count": len(owner_bytes),
        "firm_count": len(diagnostics),
        "ontology_entry_count": len(ontology_entries),
        "ontology_id": ontology_id,
        "ontology_sha256": ontology_sha,
        "availability_id": availability_id,
        "availability_sha256": availability_sha,
        "availability_review_candidate_sha256": sha256_bytes(
            availability_review_bytes
        ),
        "registry_candidate_id": registry_candidate["candidate_id"],
        "registry_candidate_sha256": registry_candidate["candidate_sha256"],
        "coverage_diagnostic_id": coverage_record["diagnostic_id"],
        "coverage_diagnostic_sha256": coverage_record["diagnostic_sha256"],
        "capabilities": false_capabilities,
    }
    _content_addressed_record(
        bundle_seed,
        identifier_field="bundle_id",
        prefix="arv2-firm-candidate-bundle-",
    )
    try:
        packet = _PINNED_PACKET_REQUIRE(packet)
    except _packet.PhysicalFirmOntologyReviewPacketError as exc:
        raise FirmOntologyCandidateError(
            FirmOntologyCandidateRefusalReason.PACKET_AUTHENTICATION_FAILED,
            "physical firm-review packet changed during composition",
        ) from exc
    values = {
        **bundle_seed,
        "owner_adjudication_bytes": owner_bytes,
        "ontology_bytes": ontology_bytes,
        "availability_bytes": availability_bytes,
        "availability_review_candidate_bytes": availability_review_bytes,
        "registry_candidate_bytes": registry_candidate_bytes,
        "coverage_diagnostic_bytes": coverage_bytes,
        **false_capabilities,
    }
    values.pop("capabilities")
    if set(values) != {field.name for field in dataclasses.fields(FirmOntologyCandidateBundle)}:
        _refuse(
            FirmOntologyCandidateRefusalReason.OUTPUT_COMPATIBILITY_FAILED,
            "candidate bundle field inventory changed",
        )
    value = FirmOntologyCandidateBundle(**values)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_bundle(key, ref)
    )
    with _BUNDLE_AUTHORITY_LOCK:
        _BUNDLE_AUTHORITIES[identity] = (
            reference,
            _bundle_fingerprint(value),
            os.getpid(),
        )
    return require_firm_ontology_candidate_bundle(value)


__all__ = [
    "CANDIDATE_SCHEMA",
    "COVERAGE_SCHEMA",
    "EXPECTED_ADJUDICATION_FIRM_COUNT",
    "FirmOntologyCandidateBundle",
    "FirmOntologyCandidateError",
    "FirmOntologyCandidateRefusalReason",
    "OWNER_ADJUDICATION_STATUS",
    "PENDING_REVIEW_STATUS",
    "REGISTRY_CANDIDATE_SCHEMA",
    "build_firm_ontology_candidate_bundle",
    "require_firm_ontology_candidate_bundle",
]
