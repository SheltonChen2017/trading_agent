"""Fresh authentication of one retained transport with one identical duplicate.

This contract does not retroactively accept the spent v1 run. It independently
authenticates its exact retained bytes and creates a different, process-local
authority. Every original occurrence is committed; only a byte-identical repeat
is idempotently collapsed. A conflicting ID refuses the complete source.
No acquisition, response recovery, diagnostic-report trust, or legacy authority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
from pathlib import Path
import weakref

from . import accepted_risk_massive_ratings_delta as _transport

ROOT = _transport.ROOT
CAPTURE_PATH = _transport.CAPTURE_PATH
FIRST_DATE = _transport.FIRST_DATE
LAST_DATE = _transport.LAST_DATE
SCHEMA = "arv2-retained-ratings-identical-duplicate-normalization-v2"
OCCURRENCE_SCHEMA = "arv2-retained-rating-occurrence-disposition-v2"
EXPECTED_MANIFEST_SHA256 = "2594cf2379c4a88c6ee53dc0ab3791235a01a4069f77505b7f98d560d8e9da00"
EXPECTED_MANIFEST_BYTE_COUNT = 2628
EXPECTED_SOURCE_ROW_COUNT = 3261
EXPECTED_UNIQUE_ROW_COUNT = 3260
EXPECTED_DUPLICATE_GROUP_COUNT = 1
EXPECTED_DUPLICATE_EXCESS_COUNT = 1
_PINNED_HELPERS = {name: getattr(_transport, name) for name in (
    "_open_chain", "_read_held", "_metadata", "_directory_binding", "_validate_manifest",
    "build_page_record", "page_names", "_normalize_bound_rating", "_frozen_field_types",
)}
_input = _transport._input
_AUTHORITIES = {}
FINITE_REFUSAL_CODES = frozenset((
    "retained_transport_dependency_changed", "occurrence_type", "authority_type",
    "authority_container", "authority_count_type", "authority_row_type", "authority_disposition_binding",
    "authority_changed", "authority_unavailable", "leaf_final_changed", "directory_final_changed",
    "ancestor_changed", "invalid_provider_id", "conflicting_provider_id",
    "cross_page_duplicate_outside_scope", "exact_duplicate_census", "operational_path",
    "exact_retained_manifest_scope", "artifact_path", "manifest_external_pin", "manifest_digest_marker",
    "manifest_canonical", "retained_source_count", "artifact_inventory", "page_external_pin",
    "page_binding", "normalized_occurrence_count", "retained_authentication_failed",
))


class RatingsDeltaV2Error(ValueError):
    """Finite non-secret failure code only."""


def _refuse(code):
    raise RatingsDeltaV2Error(code)


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def source_profile_record():
    return {
        "schema": SCHEMA, "transport_source_profile_sha256": _transport.SOURCE_PROFILE_SHA256,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "manifest_byte_count": EXPECTED_MANIFEST_BYTE_COUNT,
        "first_event_date": FIRST_DATE, "last_event_date": LAST_DATE,
        "source_row_count": EXPECTED_SOURCE_ROW_COUNT, "unique_row_count": EXPECTED_UNIQUE_ROW_COUNT,
        "duplicate_group_count": EXPECTED_DUPLICATE_GROUP_COUNT,
        "duplicate_excess_count": EXPECTED_DUPLICATE_EXCESS_COUNT,
        "duplicate_policy": "exact_canonical_row_bytes_only;first_occurrence;one_within_page_group;conflicts_refuse_all",
        "complete_evidence_before_collapse": True,
        "all_occurrence_locators_committed": True,
        "per_row_economics": "unchanged_v1_date_only_two_session_eligibility",
        "max_pages": _transport.MAX_PAGES, "max_rows": _transport.MAX_ROWS,
        "max_raw_page_bytes": _transport.MAX_PAGE_BYTES,
        "max_raw_bytes": _transport.MAX_RAW_BYTES, "max_rows_bytes": _transport.MAX_ROWS_BYTES,
        "max_manifest_bytes": _transport.MAX_MANIFEST_BYTES,
        "point_in_time_safe": False, "three_role_complete": False,
        "paper_or_live_ready": False, "retroactive_v1_acceptance": False,
    }


SOURCE_PROFILE_SHA256 = _sha(_transport.canonical_bytes(source_profile_record()))


@dataclasses.dataclass(frozen=True)
class RatingOccurrenceDisposition:
    provider_event_id: str
    locator: _input.CaptureRowLocator
    representative_locator: _input.CaptureRowLocator
    representative: bool


@dataclasses.dataclass(frozen=True)
class AuthenticatedRatingsDeltaV2:
    context: _transport.RatingsDeltaContext
    manifest_sha256: str
    manifest_byte_count: int
    page_count: int
    source_row_count: int
    row_count: int
    raw_byte_count: int
    rows_byte_count: int
    duplicate_group_count: int
    duplicate_excess_count: int
    duplicate_disposition_sha256: str
    _rows: tuple[_input.AcceptedRiskSourceRow, ...] = dataclasses.field(repr=False)
    _occurrences: tuple[RatingOccurrenceDisposition, ...] = dataclasses.field(repr=False)


def _require_helpers():
    if any(getattr(_transport, name) is not function for name, function in _PINNED_HELPERS.items()):
        _refuse("retained_transport_dependency_changed")


def _occurrence_record(value):
    if (type(value) is not RatingOccurrenceDisposition
            or type(value.provider_event_id) is not str or type(value.representative) is not bool
            or type(value.locator) is not _input.CaptureRowLocator
            or type(value.representative_locator) is not _input.CaptureRowLocator):
        _refuse("occurrence_type")
    _PINNED_HELPERS["_frozen_field_types"](value.locator)
    _PINNED_HELPERS["_frozen_field_types"](value.representative_locator)
    return {"schema": OCCURRENCE_SCHEMA, "provider_event_id": value.provider_event_id,
        "locator": value.locator.to_record(), "representative_locator": value.representative_locator.to_record(),
        "representative": value.representative}


def _disposition_digest(occurrences):
    digest = hashlib.sha256()
    for item in occurrences:
        digest.update(_transport.canonical_bytes(_occurrence_record(item)))
    return digest.hexdigest()


def _fingerprint(value):
    if type(value) is not AuthenticatedRatingsDeltaV2 or type(value.context) is not _transport.RatingsDeltaContext:
        _refuse("authority_type")
    context = tuple(getattr(value.context, field.name) for field in dataclasses.fields(_transport.RatingsDeltaContext))
    if (any(type(item) is not str for item in context) or type(value._rows) is not tuple
            or type(value._occurrences) is not tuple or type(value.manifest_sha256) is not str
            or type(value.duplicate_disposition_sha256) is not str):
        _refuse("authority_container")
    counts = tuple(getattr(value, key) for key in (
        "manifest_byte_count", "page_count", "source_row_count", "row_count", "raw_byte_count",
        "rows_byte_count", "duplicate_group_count", "duplicate_excess_count"))
    if any(type(count) is not int for count in counts):
        _refuse("authority_count_type")
    digest = hashlib.sha256()
    for row in value._rows:
        if type(row) is not _input.AcceptedRiskSourceRow or type(row.raw_row_bytes) is not bytes:
            _refuse("authority_row_type")
        digest.update(_transport.canonical_bytes(_PINNED_HELPERS["_frozen_field_types"](row)))
        digest.update(_transport.canonical_bytes(row.to_record()))
        digest.update(_sha(row.raw_row_bytes).encode("ascii"))
    disposition = _disposition_digest(value._occurrences)
    if (disposition != value.duplicate_disposition_sha256 or len(value._rows) != value.row_count
            or len(value._occurrences) != value.source_row_count):
        _refuse("authority_disposition_binding")
    return (context, value.manifest_sha256, counts, value.duplicate_disposition_sha256,
            digest.hexdigest(), disposition, os.getpid())


def require_authenticated_ratings_delta_v2(value):
    try:
        reference, fingerprint = _AUTHORITIES[id(value)]
        if reference() is not value or fingerprint != _fingerprint(value):
            _refuse("authority_changed")
    except (KeyError, AttributeError, TypeError, ValueError):
        _refuse("authority_unavailable")
    return value


def iter_authenticated_rating_rows(value):
    return iter(require_authenticated_ratings_delta_v2(value)._rows)


def iter_authenticated_occurrence_dispositions(value):
    """Private metadata iterator; never print/serialize its provider identifiers."""
    return iter(require_authenticated_ratings_delta_v2(value)._occurrences)


def _final_guards(chain, held, inventory, directory_identity):
    root_fd = chain[-1][0]
    metadata = _PINNED_HELPERS["_metadata"]
    directory = _PINNED_HELPERS["_directory_binding"]
    for fd, name, identity in held:
        if metadata(os.fstat(fd)) != identity or metadata(os.stat(name, dir_fd=root_fd, follow_symlinks=False)) != identity:
            _refuse("leaf_final_changed")
    if set(os.listdir(root_fd)) != inventory or metadata(os.fstat(root_fd)) != directory_identity:
        _refuse("directory_final_changed")
    for fd, parent, name, identity in chain:
        if directory(os.fstat(fd)) != identity or (parent is not None and
                directory(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity):
            _refuse("ancestor_changed")


def _normalize_complete_occurrences(rows):
    """Collapse only exact repeated bytes after complete source authentication.

    This is a separately versioned normalization of occurrence multiplicity;
    per-row rating/availability economics remain the pinned stateless rules.
    """
    first, unique, occurrences, duplicate_ids = {}, [], [], set()
    for row in rows:
        event = row.provider_event_id
        if type(event) is not str or not event:
            _refuse("invalid_provider_id")
        representative = first.get(event)
        if representative is None:
            first[event] = row
            unique.append(row)
            representative = row
            selected = True
        else:
            if row.raw_row_bytes != representative.raw_row_bytes:
                _refuse("conflicting_provider_id")
            if row.locator.page_number != representative.locator.page_number:
                _refuse("cross_page_duplicate_outside_scope")
            duplicate_ids.add(event)
            selected = False
        occurrences.append(RatingOccurrenceDisposition(event, row.locator, representative.locator, selected))
    counts = (len(rows), len(unique), len(duplicate_ids), len(rows) - len(unique))
    if counts != (EXPECTED_SOURCE_ROW_COUNT, EXPECTED_UNIQUE_ROW_COUNT,
                  EXPECTED_DUPLICATE_GROUP_COUNT, EXPECTED_DUPLICATE_EXCESS_COUNT):
        _refuse("exact_duplicate_census")
    return tuple(unique), tuple(occurrences), len(duplicate_ids), len(rows) - len(unique)


def authenticate_retained_capture(artifact_path, *, expected_manifest_sha256, expected_manifest_byte_count):
    if type(artifact_path) is not type(Path()) or artifact_path != CAPTURE_PATH:
        _refuse("operational_path")
    return _authenticate_retained_capture(artifact_path, expected_manifest_sha256, expected_manifest_byte_count)


def _authenticate_retained_capture(artifact_path, expected_manifest_sha256, expected_manifest_byte_count):
    """Synthetic seam still uses exact source pins/counts and in-root paths."""
    _require_helpers()
    if (type(expected_manifest_sha256) is not str or expected_manifest_sha256 != EXPECTED_MANIFEST_SHA256
            or type(expected_manifest_byte_count) is not int or expected_manifest_byte_count != EXPECTED_MANIFEST_BYTE_COUNT):
        _refuse("exact_retained_manifest_scope")
    if (type(artifact_path) is not type(Path()) or not artifact_path.is_absolute()
            or ".." in artifact_path.parts or not artifact_path.is_relative_to(ROOT)):
        _refuse("artifact_path")
    chain, held = [], []
    try:
        chain = _PINNED_HELPERS["_open_chain"](artifact_path)
        root_fd = chain[-1][0]
        initial_directory = _PINNED_HELPERS["_metadata"](os.fstat(root_fd))
        read = _PINNED_HELPERS["_read_held"]
        payload = read(root_fd, "manifest.json", _transport.MAX_MANIFEST_BYTES, held,
            expected_size=expected_manifest_byte_count)
        if len(payload) != expected_manifest_byte_count or _sha(payload) != expected_manifest_sha256:
            _refuse("manifest_external_pin")
        marker = read(root_fd, "manifest.sha256", 65, held, expected_size=65)
        if marker != (expected_manifest_sha256 + "\n").encode("ascii"):
            _refuse("manifest_digest_marker")
        manifest = _transport.strict_json_loads(payload.decode("ascii"), "retained ratings manifest")
        if _transport.canonical_bytes(manifest) != payload:
            _refuse("manifest_canonical")
        _PINNED_HELPERS["_validate_manifest"](manifest)
        if manifest["row_count"] != EXPECTED_SOURCE_ROW_COUNT:
            _refuse("retained_source_count")
        inventory = {"manifest.json", "manifest.sha256"}
        for number in range(1, manifest["page_count"] + 1):
            inventory.update(_PINNED_HELPERS["page_names"](number))
        if set(os.listdir(root_fd)) != inventory:
            _refuse("artifact_inventory")
        context = _transport.RatingsDeltaContext(
            "arv2-ratings-delta-" + expected_manifest_sha256[:24], FIRST_DATE, LAST_DATE,
            manifest["capture_started_at"], manifest["capture_completed_at"])
        query = _input.render_redacted_capture_query_bytes(source_role=_transport.ROLE,
            requested_first_event_date=FIRST_DATE, requested_last_event_date=LAST_DATE, limit=_transport.PAGE_LIMIT)
        all_rows = []
        for record in manifest["pages"]:
            raw_name, rows_name = _PINNED_HELPERS["page_names"](record["page_number"])
            raw = read(root_fd, raw_name, _transport.MAX_PAGE_BYTES, held, expected_size=record["raw_response_bytes"])
            extracted = read(root_fd, rows_name, _transport.MAX_ROWS_BYTES, held, expected_size=record["provider_rows_bytes"])
            if _sha(raw) != record["raw_response_sha256"] or _sha(extracted) != record["provider_rows_sha256"]:
                _refuse("page_external_pin")
            observed = _PINNED_HELPERS["build_page_record"](page_number=record["page_number"],
                raw_response=raw, provider_rows=extracted, response_received_at=record["response_received_at"],
                request_cursor_sha256=record["request_cursor_sha256"])
            if observed != record:
                _refuse("page_binding")
            page = _input.bind_capture_page(source_role=_transport.ROLE, redacted_query_bytes=query,
                page_number=record["page_number"], request_cursor_sha256=record["request_cursor_sha256"],
                next_cursor_sha256=record["next_cursor_sha256"], terminal_page=record["terminal_page"],
                response_received_at=record["response_received_at"], raw_response_sha256=record["raw_response_sha256"],
                provider_rows_bytes=extracted, raw_response_bytes=raw)
            for offset, raw_row in enumerate(page.raw_rows):
                all_rows.append(_PINNED_HELPERS["_normalize_bound_rating"](
                    page=page, row_offset=offset, raw_row_bytes=raw_row, context=context))
        if len(all_rows) != manifest["row_count"]:
            _refuse("normalized_occurrence_count")
        # No duplicate collapse or authority is permitted before complete
        # authenticated traversal, terminal chain, inventory and postguards.
        _final_guards(chain, held, inventory, initial_directory)
        rows, occurrences, groups, excess = _normalize_complete_occurrences(tuple(all_rows))
        disposition = _disposition_digest(occurrences)
        _final_guards(chain, held, inventory, initial_directory)
        result = AuthenticatedRatingsDeltaV2(context, expected_manifest_sha256, expected_manifest_byte_count,
            manifest["page_count"], len(all_rows), len(rows), manifest["raw_byte_count"], manifest["rows_byte_count"],
            groups, excess, disposition, rows, occurrences)
        fingerprint = _fingerprint(result)
        _require_helpers()
        _final_guards(chain, held, inventory, initial_directory)
        identifier = id(result)
        reference = weakref.ref(result, lambda _ref, key=identifier: _AUTHORITIES.pop(key, None))
        _AUTHORITIES[identifier] = (reference, fingerprint)
        return result
    except (_transport.RatingsDeltaError, _input.AcceptedRiskInputError, OSError, UnicodeError, _transport.CanonicalEvidenceError,
            RecursionError, TypeError, KeyError):
        _refuse("retained_authentication_failed")
    finally:
        for fd, _, _ in reversed(held):
            os.close(fd)
        for fd, _, _, _ in reversed(chain):
            os.close(fd)
