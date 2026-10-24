"""Offline, one-role current-vintage rating evidence; no acquisition authority.

This is deliberately not a legacy three-role CaptureBinding/archive. The public
reader authenticates the fixed new capture once, against external byte pins,
and returns an immutable in-memory snapshot. It proves neither immutable vendor
history nor continuous filesystem/native ACL/xattr integrity.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
import hashlib
import os
from pathlib import Path
import stat
import weakref

from research.analyst_revisions_v2 import accepted_risk_input_pair as _input
from research.analyst_revisions_v2.availability import AvailabilityError, derive_event_availability
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError, canonical_json_bytes, parse_date, parse_utc_timestamp,
    require_sha256, strict_json_loads,
)
from scripts import capture_arv2_massive as _capture

ROOT = Path(__file__).absolute().parents[2]
CONTROL_PATH = ROOT / "artifacts/analyst_revisions_v2/massive_ratings_delta/R297-20261013-A"
CAPTURE_PATH = CONTROL_PATH / "capture"
SCHEMA = "arv2-massive-ratings-delta-v1"
FIRST_DATE = "2026-09-26"
LAST_DATE = "2026-10-12"
ROLE = _input.MassiveSourceRole.ANALYST_RATINGS
ENDPOINT = "/benzinga/v1/ratings"
PAGE_LIMIT = 1000
MAX_PAGES = 16
MAX_ROWS = 16_000
MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_RAW_BYTES = 32 * 1024 * 1024
MAX_ROWS_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024


class RatingsDeltaError(ValueError):
    """Finite, non-secret refusal label; never contain provider data."""


def _refuse(code):
    raise RatingsDeltaError(code)


def canonical_bytes(value):
    return canonical_json_bytes(value)


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def source_profile_record():
    return {
        "schema": SCHEMA, "role": ROLE.value, "endpoint": ENDPOINT,
        "first_event_date": FIRST_DATE, "last_event_date": LAST_DATE,
        "page_limit": PAGE_LIMIT, "max_pages": MAX_PAGES, "max_rows": MAX_ROWS,
        "max_raw_page_bytes": MAX_PAGE_BYTES, "max_raw_bytes": MAX_RAW_BYTES,
        "max_rows_bytes": MAX_ROWS_BYTES, "max_manifest_bytes": MAX_MANIFEST_BYTES,
        "policy": "exact-one-role-terminal-chain-duplicate-ids-refuse-current-vintage-v1",
        "date_only_session_lag": 2, "point_in_time_safe": False,
        "paper_or_live_ready": False, "three_role_complete": False,
    }


SOURCE_PROFILE_SHA256 = _sha(canonical_bytes(source_profile_record()))
_PAGE_KEYS = frozenset((
    "page_number", "request_cursor_sha256", "next_cursor_sha256", "terminal_page",
    "response_received_at", "raw_response_sha256", "raw_response_bytes",
    "provider_rows_sha256", "provider_rows_bytes", "row_count", "http_status",
))
_MANIFEST_KEYS = frozenset((
    "schema", "source_profile_sha256", "role", "endpoint", "first_event_date",
    "last_event_date", "page_limit", "capture_started_at", "capture_completed_at",
    "page_count", "row_count", "raw_byte_count", "rows_byte_count",
    "attempted_request_count", "pages", "point_in_time_safe", "paper_or_live_ready",
    "three_role_complete",
))


def _integer(value, lower, upper, code):
    if type(value) is not int or not lower <= value <= upper:
        _refuse(code)
    return value


def _digest(value):
    try:
        if type(value) is not str:
            _refuse("digest_type")
        require_sha256(value, "digest")
    except CanonicalEvidenceError:
        _refuse("digest_value")
    return value


def _instant(value):
    try:
        if type(value) is not str:
            _refuse("clock_type")
        return parse_utc_timestamp(value, "clock")
    except (CanonicalEvidenceError, ValueError, TypeError, OverflowError):
        _refuse("clock_value")


def page_names(number):
    _integer(number, 1, MAX_PAGES, "page_number")
    return f"page{number:04d}.raw.json", f"page{number:04d}.rows.jsonl"


def build_page_record(*, page_number, raw_response, provider_rows,
                      response_received_at, request_cursor_sha256):
    page_names(page_number)
    _instant(response_received_at)
    if request_cursor_sha256 is not None:
        _digest(request_cursor_sha256)
    if (type(raw_response) is not bytes or not 0 < len(raw_response) <= MAX_PAGE_BYTES
            or type(provider_rows) is not bytes or len(provider_rows) > MAX_ROWS_BYTES):
        _refuse("page_bytes")
    try:
        extracted, next_url = _capture._response_rows_and_next_url(raw_response, page_limit=PAGE_LIMIT)
        if extracted != provider_rows:
            _refuse("extraction_mismatch")
        next_hash = None if next_url is None else _capture._cursor_hash_and_validated_url(
            next_url, source_role=ROLE, requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE, page_limit=PAGE_LIMIT,
        )[0]
    except _capture.MassiveCaptureError:
        _refuse("page_semantics")
    return {
        "page_number": page_number, "request_cursor_sha256": request_cursor_sha256,
        "next_cursor_sha256": next_hash, "terminal_page": next_hash is None,
        "response_received_at": response_received_at,
        "raw_response_sha256": _sha(raw_response), "raw_response_bytes": len(raw_response),
        "provider_rows_sha256": _sha(provider_rows), "provider_rows_bytes": len(provider_rows),
        "row_count": len(provider_rows.splitlines()), "http_status": 200,
    }


def build_manifest(*, pages, capture_started_at, capture_completed_at):
    if type(pages) is not list or not 1 <= len(pages) <= MAX_PAGES:
        _refuse("page_count")
    value = {
        "schema": SCHEMA, "source_profile_sha256": SOURCE_PROFILE_SHA256,
        "role": ROLE.value, "endpoint": ENDPOINT, "first_event_date": FIRST_DATE,
        "last_event_date": LAST_DATE, "page_limit": PAGE_LIMIT,
        "capture_started_at": capture_started_at, "capture_completed_at": capture_completed_at,
        "page_count": len(pages), "row_count": sum(p["row_count"] for p in pages),
        "raw_byte_count": sum(p["raw_response_bytes"] for p in pages),
        "rows_byte_count": sum(p["provider_rows_bytes"] for p in pages),
        "attempted_request_count": len(pages), "pages": pages,
        "point_in_time_safe": False, "paper_or_live_ready": False, "three_role_complete": False,
    }
    _validate_manifest(value)
    if len(canonical_bytes(value)) > MAX_MANIFEST_BYTES:
        _refuse("manifest_size")
    return value


def _validate_manifest(value):
    if type(value) is not dict or set(value) != _MANIFEST_KEYS:
        _refuse("manifest_inventory")
    for key, expected in (
        ("schema", SCHEMA), ("source_profile_sha256", SOURCE_PROFILE_SHA256),
        ("role", ROLE.value), ("endpoint", ENDPOINT), ("first_event_date", FIRST_DATE),
        ("last_event_date", LAST_DATE),
    ):
        if type(value[key]) is not str or value[key] != expected:
            _refuse("manifest_binding")
    for key in ("point_in_time_safe", "paper_or_live_ready", "three_role_complete"):
        if value[key] is not False:
            _refuse("readiness_flag")
    _integer(value["page_limit"], PAGE_LIMIT, PAGE_LIMIT, "page_limit")
    pages = value["pages"]
    if type(pages) is not list:
        _refuse("pages_type")
    _integer(value["page_count"], 1, MAX_PAGES, "page_count")
    if value["page_count"] != len(pages):
        _refuse("page_count")
    _integer(value["attempted_request_count"], len(pages), len(pages), "attempted_count")
    _integer(value["row_count"], 0, MAX_ROWS, "row_count")
    _integer(value["raw_byte_count"], 1, MAX_RAW_BYTES, "raw_total")
    _integer(value["rows_byte_count"], 0, MAX_ROWS_BYTES, "rows_total")
    started, completed = _instant(value["capture_started_at"]), _instant(value["capture_completed_at"])
    if not _instant("2026-10-12T20:00:00.000000Z") <= started <= completed:
        _refuse("capture_chronology")
    previous_cursor, previous_time = None, started
    seen_cursors, seen_raw = set(), set()
    sums = [0, 0, 0]
    for number, page in enumerate(pages, 1):
        if type(page) is not dict or set(page) != _PAGE_KEYS:
            _refuse("page_inventory")
        _integer(page["page_number"], number, number, "page_order")
        _integer(page["http_status"], 200, 200, "http_status")
        _integer(page["row_count"], 0, PAGE_LIMIT, "page_rows")
        _integer(page["raw_response_bytes"], 1, MAX_PAGE_BYTES, "page_raw_bytes")
        _integer(page["provider_rows_bytes"], 0, MAX_ROWS_BYTES, "page_rows_bytes")
        for key in ("raw_response_sha256", "provider_rows_sha256"):
            _digest(page[key])
        for key in ("request_cursor_sha256", "next_cursor_sha256"):
            if page[key] is not None:
                _digest(page[key])
        if page["request_cursor_sha256"] != previous_cursor:
            _refuse("cursor_chain")
        next_cursor = page["next_cursor_sha256"]
        if type(page["terminal_page"]) is not bool or page["terminal_page"] != (next_cursor is None):
            _refuse("terminal_flag")
        if page["terminal_page"] != (number == len(pages)):
            _refuse("terminal_chain")
        if next_cursor is not None:
            if next_cursor in seen_cursors:
                _refuse("cursor_replay")
            seen_cursors.add(next_cursor)
        if page["raw_response_sha256"] in seen_raw:
            _refuse("response_replay")
        seen_raw.add(page["raw_response_sha256"])
        instant = _instant(page["response_received_at"])
        if not previous_time <= instant <= completed:
            _refuse("page_chronology")
        previous_time, previous_cursor = instant, next_cursor
        sums = [sums[0] + page["row_count"], sums[1] + page["raw_response_bytes"],
                sums[2] + page["provider_rows_bytes"]]
    if sums != [value["row_count"], value["raw_byte_count"], value["rows_byte_count"]]:
        _refuse("manifest_totals")


@dataclasses.dataclass(frozen=True)
class RatingsDeltaContext:
    capture_id: str
    first_event_date: str
    last_event_date: str
    capture_started_at: str
    capture_completed_at: str


@dataclasses.dataclass(frozen=True)
class AuthenticatedRatingsDelta:
    context: RatingsDeltaContext
    manifest_sha256: str
    manifest_byte_count: int
    page_count: int
    row_count: int
    raw_byte_count: int
    rows_byte_count: int
    _rows: tuple[_input.AcceptedRiskSourceRow, ...] = dataclasses.field(repr=False)


_AUTHORITIES = {}


def _frozen_field_types(value):
    """Type-only shape, checked before methods/copy hooks on nested values.

    The original minted shape joins the value fingerprint. A same-value
    mutable buffer, subclass, enum substitute or record-shaped object cannot
    inherit authority by serializing like an original frozen field.
    """
    kind = type(value)
    if kind in {_input.AcceptedRiskSourceRow, _input.CaptureRowLocator, _input.ViewEligibility}:
        fields = [kind.__name__]
        for field in dataclasses.fields(kind):
            fields.extend(_frozen_field_types(getattr(value, field.name)))
        return fields
    if kind in {type(None), str, int, bool, bytes, _input.MassiveSourceRole,
            _input.InputView, _input.RowDisposition}:
        return [kind.__name__]
    _refuse("authority_field_type")


def _fingerprint(value):
    if type(value) is not AuthenticatedRatingsDelta or type(value.context) is not RatingsDeltaContext:
        _refuse("authority_type")
    context = tuple(getattr(value.context, field.name) for field in dataclasses.fields(RatingsDeltaContext))
    if (type(value._rows) is not tuple or type(value.manifest_sha256) is not str
            or any(type(item) is not str for item in context)):
        _refuse("authority_container")
    if any(type(getattr(value, key)) is not int for key in (
            "manifest_byte_count", "page_count", "row_count", "raw_byte_count", "rows_byte_count")):
        _refuse("authority_scalar")
    digest = hashlib.sha256()
    for row in value._rows:
        if (type(row) is not _input.AcceptedRiskSourceRow or type(row.raw_row_bytes) is not bytes
                or type(row.locator) is not _input.CaptureRowLocator
                or type(row.current_view) is not _input.ViewEligibility
                or type(row.censored_view) is not _input.ViewEligibility):
            _refuse("row_type")
        digest.update(canonical_bytes(_frozen_field_types(row)))
        digest.update(canonical_bytes(row.to_record()))
        digest.update(_sha(row.raw_row_bytes).encode("ascii"))
    return (context, value.manifest_sha256, value.manifest_byte_count,
            value.page_count, value.row_count, value.raw_byte_count, value.rows_byte_count,
            digest.hexdigest(), os.getpid())


def require_authenticated_ratings_delta(value):
    try:
        ref, fingerprint = _AUTHORITIES[id(value)]
        if ref() is not value or fingerprint != _fingerprint(value):
            _refuse("authority_changed")
    except (KeyError, AttributeError, TypeError, ValueError):
        _refuse("authority_unavailable")
    return value


def iter_authenticated_rating_rows(value):
    """Read the authenticated in-memory snapshot, not a filesystem re-open."""
    return iter(require_authenticated_ratings_delta(value)._rows)


def normalize_rating(*, page, row_offset, raw_row_bytes, context):
    """Same ratings-only economic semantics as the frozen legacy row derivation."""
    if type(page) is not _input.CapturePageBinding:
        _refuse("normalization_page")
    _integer(row_offset, 0, page.row_count - 1, "row_offset")
    if page.raw_rows[row_offset] != raw_row_bytes:
        _refuse("row_page_binding")
    return _normalize_bound_rating(page=page, row_offset=row_offset, raw_row_bytes=raw_row_bytes, context=context)


def _normalize_bound_rating(*, page, row_offset, raw_row_bytes, context):
    """Internal already-bound single row avoids reparsing a whole page per row."""
    if (type(page) is not _input.CapturePageBinding or page.source_role is not ROLE
            or type(context) is not RatingsDeltaContext
            or context.first_event_date != FIRST_DATE or context.last_event_date != LAST_DATE):
        _refuse("normalization_context")
    try:
        parsed = _input._parse_provider_rows_bytes(raw_row_bytes)
        if len(parsed) != 1:
            _refuse("normalization_row")
        row = parsed[0][0]
        _integer(row_offset, 0, page.row_count - 1, "row_offset")
        provider_id = _input._candidate_provider_event_id(row)
        try:
            event = parse_date(row.get("date"), "event date")
        except CanonicalEvidenceError:
            event = None
        invalid_time = False
        try:
            raw_time = _input._valid_raw_time(row.get("time"))
        except _input.AcceptedRiskInputError:
            raw_time, invalid_time = None, True
        updated = _input._normalize_explicit_offset_timestamp(row.get("last_updated"))
        disposition = None
        D = _input.RowDisposition
        if provider_id is None:
            disposition = D.INVALID_PROVIDER_EVENT_ID
        elif event is None:
            disposition = D.INVALID_EVENT_DATE
        elif invalid_time:
            disposition = D.INVALID_EVENT_TIME
        elif event.isoformat() < "2013-01-01":
            disposition = D.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
        elif not FIRST_DATE <= event.isoformat() <= LAST_DATE:
            disposition = D.EVENT_OUTSIDE_REQUESTED_CAPTURE_RANGE
        eligible_session, eligible_at = None, None
        if disposition is None:
            try:
                availability = derive_event_availability(
                    evidence_id=f"{context.capture_id}:{ROLE.value}:{provider_id}",
                    public_date=event.isoformat(),
                )
                eligible_session = availability.eligible_session
                eligible_at = _input.format_utc_timestamp(
                    datetime.fromisoformat(availability.eligible_at.replace("Z", "+00:00")))
            except (AvailabilityError, CanonicalEvidenceError, OSError, OverflowError, ValueError):
                disposition = D.EVENT_OUTSIDE_EXCHANGE_CALENDAR_AUTHORITY
        if disposition is not None:
            current, censored = _input._joint_exclusion(disposition)
        elif updated is not None and _instant(updated) > _instant(page.response_received_at):
            current = _input._excluded_view(
                view=_input.InputView.CURRENT_ROW, disposition=D.LAST_UPDATED_AFTER_CAPTURE,
                eligible_session=eligible_session, eligible_at=eligible_at,
                event_clock_not_after_cutoff=True,
            )
            censored = _input._excluded_view(
                view=_input.InputView.CONSERVATIVE_CENSORED, disposition=D.LAST_UPDATED_AFTER_CAPTURE,
                eligible_session=eligible_session, eligible_at=eligible_at,
                event_clock_not_after_cutoff=True, last_updated_not_after_cutoff=False,
            )
        else:
            current = _input.ViewEligibility(
                _input.InputView.CURRENT_ROW, True, D.INCLUDED_CURRENT_ROW_NON_PRISTINE,
                eligible_session, eligible_at, eligible_at, True, None,
            )
            if updated is None:
                censored = _input._excluded_view(
                    view=_input.InputView.CONSERVATIVE_CENSORED,
                    disposition=D.INVALID_LAST_UPDATED_EXPLICIT_OFFSET,
                    eligible_session=eligible_session, eligible_at=eligible_at,
                    event_clock_not_after_cutoff=True,
                )
            elif _instant(updated) <= _instant(eligible_at):
                censored = _input.ViewEligibility(
                    _input.InputView.CONSERVATIVE_CENSORED, True,
                    D.INCLUDED_CONSERVATIVE_CENSORED_NON_PRISTINE,
                    eligible_session, eligible_at, eligible_at, True, True,
                )
            else:
                censored = _input._excluded_view(
                    view=_input.InputView.CONSERVATIVE_CENSORED,
                    disposition=D.CENSORED_LAST_TOUCH_AFTER_DECISION_CUTOFF,
                    eligible_session=eligible_session, eligible_at=eligible_at,
                    event_clock_not_after_cutoff=True, last_updated_not_after_cutoff=False,
                )
        action, firm, security = _input._row_dimension_labels(ROLE, row)
        return _input.AcceptedRiskSourceRow(
            locator=_input.CaptureRowLocator(context.capture_id, ROLE, page.page_number,
                                            page.provider_rows_sha256, row_offset, _sha(raw_row_bytes)),
            raw_row_bytes=raw_row_bytes, provider_event_id=provider_id,
            event_date=None if event is None else event.isoformat(),
            event_year=None if event is None else event.year, raw_event_time=raw_time,
            normalized_last_updated_at=updated, last_updated_calendar_date=None,
            clock_interpretation="documented_utc_time_audit_only_date_only_two_session_eligibility",
            action_label=action, firm_label=firm, current_restated_security_label=security,
            current_view=current, censored_view=censored,
        )
    except (CanonicalEvidenceError, RecursionError, TypeError, KeyError, OverflowError):
        _refuse("normalization_invalid")


def _metadata(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_mode, info.st_uid, info.st_gid, info.st_nlink, getattr(info, "st_flags", None))


def _directory_binding(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            getattr(info, "st_flags", None))


def _open_chain(path):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptors = []
    try:
        descriptors.append((os.open("/", flags), None, None))
        for part in path.parts[1:]:
            parent = descriptors[-1][0]
            before = os.stat(part, dir_fd=parent, follow_symlinks=False)
            fd = os.open(part, flags, dir_fd=parent)
            descriptors.append((fd, parent, part))
            if _directory_binding(before) != _directory_binding(os.fstat(fd)):
                _refuse("directory_preopen_changed")
        snapshots = [(fd, parent, name, _directory_binding(os.fstat(fd)))
                     for fd, parent, name in descriptors]
        final = os.fstat(snapshots[-1][0])
        if stat.S_IMODE(final.st_mode) != 0o700 or final.st_uid != os.getuid():
            _refuse("private_directory")
        return snapshots
    except BaseException:
        for fd, _, _ in reversed(descriptors):
            os.close(fd)
        raise


def _read_held(root_fd, name, maximum, held, *, expected_size):
    _integer(expected_size, 0, maximum, "leaf_expected_size")
    before = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    if (not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_uid != os.getuid() or before.st_nlink != 1
            or before.st_size != expected_size):
        _refuse("private_leaf")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=root_fd)
    held.append((fd, name, _metadata(before)))
    if _metadata(before) != _metadata(os.fstat(fd)):
        _refuse("leaf_preopen_changed")
    chunks, count = [], 0
    while True:
        chunk = os.read(fd, min(65536, maximum + 1 - count))
        if not chunk:
            break
        chunks.append(chunk)
        count += len(chunk)
        if count > maximum:
            _refuse("leaf_size")
    if count != before.st_size:
        _refuse("leaf_size_changed")
    if (_metadata(os.fstat(fd)) != _metadata(before)
            or _metadata(os.stat(name, dir_fd=root_fd, follow_symlinks=False)) != _metadata(before)):
        _refuse("leaf_read_changed")
    return b"".join(chunks)


def authenticate_capture(artifact_path, *, expected_manifest_sha256, expected_manifest_byte_count):
    if type(artifact_path) is not type(Path()) or artifact_path != CAPTURE_PATH:
        _refuse("operational_path")
    return _authenticate_capture(artifact_path, expected_manifest_sha256, expected_manifest_byte_count)


def _authenticate_capture(artifact_path, expected_manifest_sha256, expected_manifest_byte_count):
    """Internal synthetic-test seam: still confines paths to the designated root."""
    _digest(expected_manifest_sha256)
    _integer(expected_manifest_byte_count, 1, MAX_MANIFEST_BYTES, "manifest_size")
    if (type(artifact_path) is not type(Path()) or not artifact_path.is_absolute()
            or ".." in artifact_path.parts or not artifact_path.is_relative_to(ROOT)):
        _refuse("artifact_path")
    chain, held = [], []
    try:
        chain = _open_chain(artifact_path)
        root_fd = chain[-1][0]
        initial_directory = _metadata(os.fstat(root_fd))
        payload = _read_held(root_fd, "manifest.json", MAX_MANIFEST_BYTES, held,
                             expected_size=expected_manifest_byte_count)
        if len(payload) != expected_manifest_byte_count or _sha(payload) != expected_manifest_sha256:
            _refuse("manifest_external_pin")
        marker = _read_held(root_fd, "manifest.sha256", 65, held, expected_size=65)
        if marker != (expected_manifest_sha256 + "\n").encode("ascii"):
            _refuse("manifest_digest_marker")
        manifest = strict_json_loads(payload.decode("ascii"), "ratings manifest")
        if canonical_bytes(manifest) != payload:
            _refuse("manifest_canonical")
        _validate_manifest(manifest)
        inventory = {"manifest.json", "manifest.sha256"}
        for number in range(1, manifest["page_count"] + 1):
            inventory.update(page_names(number))
        if set(os.listdir(root_fd)) != inventory:
            _refuse("artifact_inventory")
        context = RatingsDeltaContext(
            "arv2-ratings-delta-" + expected_manifest_sha256[:24], FIRST_DATE, LAST_DATE,
            manifest["capture_started_at"], manifest["capture_completed_at"],
        )
        rows, seen_ids = [], set()
        query = _input.render_redacted_capture_query_bytes(
            source_role=ROLE, requested_first_event_date=FIRST_DATE,
            requested_last_event_date=LAST_DATE, limit=PAGE_LIMIT,
        )
        for record in manifest["pages"]:
            raw_name, rows_name = page_names(record["page_number"])
            raw = _read_held(root_fd, raw_name, MAX_PAGE_BYTES, held,
                             expected_size=record["raw_response_bytes"])
            extracted = _read_held(root_fd, rows_name, MAX_ROWS_BYTES, held,
                                   expected_size=record["provider_rows_bytes"])
            # The manifest was externally authenticated before parsing it.
            # Bind each exact-size leaf to those authenticated page pins
            # before parsing either provider representation.
            if (_sha(raw) != record["raw_response_sha256"]
                    or _sha(extracted) != record["provider_rows_sha256"]):
                _refuse("page_external_pin")
            observed = build_page_record(
                page_number=record["page_number"], raw_response=raw, provider_rows=extracted,
                response_received_at=record["response_received_at"],
                request_cursor_sha256=record["request_cursor_sha256"],
            )
            if observed != record:
                _refuse("page_binding")
            page = _input.bind_capture_page(
                source_role=ROLE, redacted_query_bytes=query, page_number=record["page_number"],
                request_cursor_sha256=record["request_cursor_sha256"],
                next_cursor_sha256=record["next_cursor_sha256"], terminal_page=record["terminal_page"],
                response_received_at=record["response_received_at"],
                raw_response_sha256=record["raw_response_sha256"],
                provider_rows_bytes=extracted, raw_response_bytes=raw,
            )
            for offset, raw_row in enumerate(page.raw_rows):
                normalized = _normalize_bound_rating(page=page, row_offset=offset, raw_row_bytes=raw_row, context=context)
                if normalized.provider_event_id is not None:
                    if normalized.provider_event_id in seen_ids:
                        _refuse("duplicate_rating_provider_id")
                    seen_ids.add(normalized.provider_event_id)
                rows.append(normalized)
        if len(rows) != manifest["row_count"]:
            _refuse("normalized_count")
        for fd, name, identity in held:
            if (_metadata(os.fstat(fd)) != identity
                    or _metadata(os.stat(name, dir_fd=root_fd, follow_symlinks=False)) != identity):
                _refuse("leaf_final_changed")
        if set(os.listdir(root_fd)) != inventory or _metadata(os.fstat(root_fd)) != initial_directory:
            _refuse("directory_final_changed")
        for fd, parent, name, identity in chain:
            if _directory_binding(os.fstat(fd)) != identity or (parent is not None and
                    _directory_binding(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity):
                _refuse("ancestor_changed")
        result = AuthenticatedRatingsDelta(
            context, expected_manifest_sha256, expected_manifest_byte_count,
            manifest["page_count"], manifest["row_count"], manifest["raw_byte_count"],
            manifest["rows_byte_count"], tuple(rows),
        )
        identifier = id(result)
        ref = weakref.ref(result, lambda _ref, key=identifier: _AUTHORITIES.pop(key, None))
        _AUTHORITIES[identifier] = (ref, _fingerprint(result))
        return result
    except (OSError, UnicodeError, CanonicalEvidenceError, RecursionError, TypeError, KeyError):
        _refuse("authentication_failed")
    finally:
        for fd, _, _ in reversed(held):
            os.close(fd)
        for fd, _, _, _ in reversed(chain):
            os.close(fd)
