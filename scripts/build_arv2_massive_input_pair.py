"""Build the ARV2 accepted-risk pair from one immutable Massive capture.

This module is a filesystem-only bridge.  It never acquires a credential,
opens a network client, calls QuantConnect, reads outcomes, or accepts a
caller-authored completeness or point-in-time claim.  The public entry point
admits only an artifact produced by the production Massive transport under the
repository's private ``artifacts/`` tree.  A private entry point exists solely
for offline tests and admits only the capture adapter's explicit test marker.

The bridge authenticates exact persisted raw responses first, then creates a
raw-response-free ``CaptureBinding`` that shares the already-authenticated
canonical JSONL bytes.  The physical capture frame is released before the
accepted-risk rows are derived.  Consequently complete raw response history
and complete normalized history are never retained together.  Retained source
payload is capped at 192 MiB.  Including the bounded reader's one-page
read/join transient, the exact source-byte-buffer peak is 264 MiB; Python
objects, decoded text, and transient canonical serialization are additional
and are bounded indirectly by the page, row, and source limits.
"""
from __future__ import annotations

import dataclasses
import gc
import os
import re
import threading
import weakref
from collections import Counter
from pathlib import Path
from typing import Any

from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskInputError,
    AcceptedRiskInputPair,
    CaptureBinding,
    InputView,
    MassiveSourceRole,
    RowDisposition,
    bind_capture_page,
    build_accepted_risk_input_pair,
    build_capture_binding,
    require_accepted_risk_input_pair,
    require_capture_binding,
)
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    require_identifier,
    sha256_bytes,
    strict_json_loads,
)
from scripts import capture_arv2_massive as _massive


BRIDGE_SCHEMA = "arv2-massive-accepted-risk-physical-bridge-v1"
BRIDGE_CONTRACT_ID = "arv2-4f-c1-massive-physical-bridge-v1"
MAX_BRIDGE_PAGE_COUNT = 96
MAX_BRIDGE_ROW_COUNT = 300_000
MAX_BRIDGE_RETAINED_SOURCE_BYTES = 192 * 1024 * 1024
MAX_BRIDGE_PROVIDER_ROWS_BYTES = 96 * 1024 * 1024
MAX_BRIDGE_ROW_BYTES = 256 * 1024
MAX_BRIDGE_SOURCE_PAYLOAD_PEAK_BYTES = (
    MAX_BRIDGE_RETAINED_SOURCE_BYTES + _massive.MAX_RAW_RESPONSE_BYTES
)

_ROLE_ORDER = (
    MassiveSourceRole.ANALYST_RATINGS,
    MassiveSourceRole.EARNINGS,
    MassiveSourceRole.CORPORATE_GUIDANCE,
)
_CLOCK_SEMANTICS = (
    (
        MassiveSourceRole.ANALYST_RATINGS,
        "documented_utc_time_audit_only_date_only_two_session_eligibility",
    ),
    (
        MassiveSourceRole.EARNINGS,
        "literal_est_time_audit_only_no_dst_inference_date_only_two_session_eligibility",
    ),
    (
        MassiveSourceRole.CORPORATE_GUIDANCE,
        "unresolved_intraday_timezones_date_only_three_session_lag_and_"
        "exact_offset_or_prior_calendar_date_censoring",
    ),
)
_KNOWN_RATING_ACTIONS = frozenset(
    {
        "assumes",
        "downgrades",
        "firm_dissolved",
        "initiates_coverage_on",
        "maintains",
        "reinstates",
        "reiterates",
        "removes",
        "suspends",
        "terminates_coverage_on",
        "upgrades",
    }
)
_ACTION_SPACE_RE = re.compile(r" +")


class MassiveInputPairBridgeError(ValueError):
    """The physical artifact cannot establish the bounded accepted-risk pair."""


@dataclasses.dataclass(frozen=True, init=False)
class MassiveAcceptedRiskBridge:
    schema: str
    contract_id: str
    bridge_id: str
    bridge_sha256: str
    artifact_path: Path
    artifact_id: str
    manifest_sha256: str
    capture_transport: str
    physical_capture_id: str
    physical_capture_sha256: str
    derived_capture_id: str
    derived_capture_sha256: str
    source_page_root_sha256: str
    source_page_count: int
    source_row_count: int
    raw_response_total_byte_count: int
    provider_rows_total_byte_count: int
    role_row_counts: tuple[tuple[MassiveSourceRole, int], ...]
    clock_semantics: tuple[tuple[MassiveSourceRole, str], ...]
    disposition_counts: tuple[tuple[InputView, RowDisposition, int], ...]
    pair: AcceptedRiskInputPair
    physical_raw_extraction_authenticated: bool
    raw_response_bytes_retained_in_pair: bool
    pristine_point_in_time: bool
    caller_completeness_claim_accepted: bool
    filesystem_io_performed: bool
    provider_io_performed: bool
    credential_access_performed: bool
    quantconnect_io_performed: bool
    outcome_access_performed: bool


@dataclasses.dataclass(frozen=True)
class _PhysicalProof:
    artifact_path: Path
    artifact_id: str
    manifest_sha256: str
    capture_transport: str
    physical_capture_id: str
    physical_capture_sha256: str
    source_page_root_sha256: str
    source_page_count: int
    source_row_count: int
    raw_response_total_byte_count: int
    provider_rows_total_byte_count: int
    role_row_counts: tuple[tuple[MassiveSourceRole, int], ...]


_BRIDGE_AUTHORITIES: dict[
    int,
    tuple[weakref.ReferenceType[MassiveAcceptedRiskBridge], tuple[object, ...]],
] = {}
_BRIDGE_AUTHORITIES_LOCK = threading.RLock()


def _forget_bridge(
    identity: int, reference: weakref.ReferenceType[MassiveAcceptedRiskBridge]
) -> None:
    with _BRIDGE_AUTHORITIES_LOCK:
        current = _BRIDGE_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _BRIDGE_AUTHORITIES.pop(identity, None)


def _bridge_fingerprint(value: MassiveAcceptedRiskBridge) -> tuple[object, ...]:
    return tuple(getattr(value, field.name) for field in dataclasses.fields(value))


def _canonical_rating_action(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 64
    ):
        raise MassiveInputPairBridgeError(
            "rating_action is not a reviewed provider action"
        )
    normalized = _ACTION_SPACE_RE.sub("_", value.casefold())
    if normalized not in _KNOWN_RATING_ACTIONS:
        raise MassiveInputPairBridgeError(
            "rating_action is not a reviewed provider action"
        )
    return normalized


def _iter_page_rows(payload: bytes):
    """Parse one bounded JSONL row at a time without a second page-sized list."""

    start = 0
    offset = 0
    while start < len(payload):
        end = payload.find(b"\n", start)
        if end < 0:
            raise MassiveInputPairBridgeError(
                "provider row page lost its LF terminator"
            )
        raw = payload[start:end]
        if not raw or len(raw) + 1 > MAX_BRIDGE_ROW_BYTES:
            raise MassiveInputPairBridgeError(
                "provider row exceeds the bridge row-byte budget"
            )
        try:
            value = strict_json_loads(
                decode_utf8(raw, f"Massive bridge row {offset}"),
                f"Massive bridge row {offset}",
            )
        except CanonicalEvidenceError as exc:
            raise MassiveInputPairBridgeError(
                "provider row is not strict JSON"
            ) from exc
        if type(value) is not dict:
            raise MassiveInputPairBridgeError(
                "provider row is not a JSON object"
            )
        yield offset, value
        offset += 1
        start = end + 1


def _page_root_record(capture: CaptureBinding) -> dict[str, object]:
    return {
        "schema": "arv2-massive-physical-source-page-root-v1",
        "pages": [
            {
                "source_role": page.source_role.value,
                "endpoint_path": _massive.ENDPOINT_PATHS[page.source_role],
                "endpoint_identifier": page.endpoint_identifier,
                "redacted_query_sha256": page.redacted_query_sha256,
                "page_number": page.page_number,
                "request_cursor_sha256": page.request_cursor_sha256,
                "next_cursor_sha256": page.next_cursor_sha256,
                "terminal_page": page.terminal_page,
                "response_received_at": page.response_received_at,
                "raw_response_sha256": page.raw_response_sha256,
                "provider_rows_sha256": page.provider_rows_sha256,
                "row_count": page.row_count,
                "raw_response_extraction_authenticated": True,
            }
            for page in capture.pages
        ],
    }


def _source_page_root(capture: CaptureBinding) -> str:
    return sha256_bytes(canonical_json_bytes(_page_root_record(capture)))


def _slim_authenticated_capture(
    artifact_path: Path, expected_transport: str
) -> tuple[CaptureBinding, _PhysicalProof]:
    try:
        loaded = _massive._load_massive_capture_artifact_bounded(
            artifact_path,
            maximum_page_count=MAX_BRIDGE_PAGE_COUNT,
            maximum_row_count=MAX_BRIDGE_ROW_COUNT,
            maximum_retained_byte_count=MAX_BRIDGE_RETAINED_SOURCE_BYTES,
            maximum_provider_rows_byte_count=MAX_BRIDGE_PROVIDER_ROWS_BYTES,
        )
        physical = require_capture_binding(loaded.capture)
    except (AcceptedRiskInputError, CanonicalEvidenceError, _massive.MassiveCaptureError) as exc:
        raise MassiveInputPairBridgeError(
            "Massive artifact failed physical authentication"
        ) from exc
    if loaded.capture_transport != expected_transport:
        raise MassiveInputPairBridgeError(
            "Massive artifact transport does not match this bridge entry point"
        )

    seen_provider_ids: set[str] = set()
    observed_rows = 0
    raw_total = 0
    rows_total = 0
    slim_pages = []
    for page in physical.pages:
        if page.raw_response_bytes is None:
            raise MassiveInputPairBridgeError(
                "physical capture did not authenticate an exact raw response"
            )
        raw_total += len(page.raw_response_bytes)
        rows_total += len(page.provider_rows_bytes)
        page_rows = 0
        for _, row in _iter_page_rows(page.provider_rows_bytes):
            page_rows += 1
            observed_rows += 1
            candidate_id = row.get("benzinga_id")
            try:
                provider_id = require_identifier(candidate_id, "benzinga_id")
            except CanonicalEvidenceError:
                provider_id = None
            if provider_id is not None:
                if provider_id in seen_provider_ids:
                    raise MassiveInputPairBridgeError(
                        "duplicate or conflicting benzinga_id invalidates the capture"
                    )
                seen_provider_ids.add(provider_id)
            if (
                page.source_role is MassiveSourceRole.ANALYST_RATINGS
                and row.get("rating_action") is not None
            ):
                _canonical_rating_action(row["rating_action"])
        if page_rows != page.row_count:
            raise MassiveInputPairBridgeError(
                "streamed page census does not match its authenticated row count"
            )
        try:
            slim_pages.append(
                bind_capture_page(
                    source_role=page.source_role,
                    redacted_query_bytes=page.redacted_query_bytes,
                    page_number=page.page_number,
                    request_cursor_sha256=page.request_cursor_sha256,
                    next_cursor_sha256=page.next_cursor_sha256,
                    terminal_page=page.terminal_page,
                    response_received_at=page.response_received_at,
                    raw_response_sha256=page.raw_response_sha256,
                    provider_rows_bytes=page.provider_rows_bytes,
                    raw_response_bytes=None,
                )
            )
        except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
            raise MassiveInputPairBridgeError(
                "authenticated provider rows failed bounded rebinding"
            ) from exc

    if (
        observed_rows != physical.total_row_count
        or raw_total + rows_total > MAX_BRIDGE_RETAINED_SOURCE_BYTES
        or rows_total > MAX_BRIDGE_PROVIDER_ROWS_BYTES
    ):
        raise MassiveInputPairBridgeError(
            "physical source census exceeds or disagrees with the bridge bounds"
        )
    source_page_root = _source_page_root(physical)
    proof = _PhysicalProof(
        artifact_path=loaded.artifact_path,
        artifact_id=loaded.artifact_path.name,
        manifest_sha256=loaded.manifest_sha256,
        capture_transport=loaded.capture_transport,
        physical_capture_id=physical.capture_id,
        physical_capture_sha256=physical.capture_sha256,
        source_page_root_sha256=source_page_root,
        source_page_count=physical.total_page_count,
        source_row_count=physical.total_row_count,
        raw_response_total_byte_count=raw_total,
        provider_rows_total_byte_count=rows_total,
        role_row_counts=physical.role_row_counts,
    )
    try:
        slim = build_capture_binding(
            capture_started_at=physical.capture_started_at,
            capture_completed_at=physical.capture_completed_at,
            pages=tuple(slim_pages),
        )
    except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
        raise MassiveInputPairBridgeError(
            "bounded capture failed accepted-risk authentication"
        ) from exc
    if (
        slim.total_row_count != proof.source_row_count
        or slim.total_page_count != proof.source_page_count
        or slim.role_row_counts != proof.role_row_counts
        or _source_page_root(slim) != proof.source_page_root_sha256
        or any(page.raw_response_bytes is not None for page in slim.pages)
    ):
        raise MassiveInputPairBridgeError(
            "raw-free capture does not preserve the physical source root"
        )
    return slim, proof


def _disposition_census(
    pair: AcceptedRiskInputPair,
) -> tuple[tuple[InputView, RowDisposition, int], ...]:
    counts: Counter[tuple[InputView, RowDisposition]] = Counter()
    for row in pair.rows:
        counts[(InputView.CURRENT_ROW, row.current_view.disposition)] += 1
        counts[(InputView.CONSERVATIVE_CENSORED, row.censored_view.disposition)] += 1
        if row.censored_view.included:
            if (
                row.censored_view.disposition
                is not RowDisposition.INCLUDED_CONSERVATIVE_CENSORED_NON_PRISTINE
                or row.censored_view.last_updated_not_after_cutoff is not True
            ):
                raise MassiveInputPairBridgeError(
                    "conservative inclusion lacks an exact conservative disposition"
                )
        elif row.current_view.included and row.censored_view.disposition not in {
            RowDisposition.INVALID_LAST_UPDATED_EXPLICIT_OFFSET,
            RowDisposition.CENSORED_LAST_TOUCH_AFTER_DECISION_CUTOFF,
        }:
            raise MassiveInputPairBridgeError(
                "revised/current row lacks a conservative exclusion disposition"
            )
    return tuple(
        (view, disposition, counts[(view, disposition)])
        for view in InputView
        for disposition in RowDisposition
    )


def _bridge_record(
    *,
    proof: _PhysicalProof,
    pair: AcceptedRiskInputPair,
    disposition_counts: tuple[tuple[InputView, RowDisposition, int], ...],
) -> dict[str, Any]:
    return {
        "schema": BRIDGE_SCHEMA,
        "contract_id": BRIDGE_CONTRACT_ID,
        "artifact_id": proof.artifact_id,
        "manifest_sha256": proof.manifest_sha256,
        "capture_transport": proof.capture_transport,
        "physical_capture_id": proof.physical_capture_id,
        "physical_capture_sha256": proof.physical_capture_sha256,
        "derived_capture_id": pair.capture.capture_id,
        "derived_capture_sha256": pair.capture.capture_sha256,
        "source_page_root_sha256": proof.source_page_root_sha256,
        "source_page_count": proof.source_page_count,
        "source_row_count": proof.source_row_count,
        "raw_response_total_byte_count": proof.raw_response_total_byte_count,
        "provider_rows_total_byte_count": proof.provider_rows_total_byte_count,
        "role_row_counts": [
            {"source_role": role.value, "row_count": count}
            for role, count in proof.role_row_counts
        ],
        "source_endpoints": [
            {
                "source_role": role.value,
                "endpoint_path": _massive.ENDPOINT_PATHS[role],
                "endpoint_identifier": next(
                    page.endpoint_identifier
                    for page in pair.capture.pages
                    if page.source_role is role
                ),
            }
            for role in _ROLE_ORDER
        ],
        "capture_vintage": {
            "capture_started_at": pair.capture.capture_started_at,
            "capture_completed_at": pair.capture.capture_completed_at,
            "requested_first_event_date": pair.capture.requested_first_event_date,
            "requested_last_event_date": pair.capture.requested_last_event_date,
        },
        "clock_semantics": [
            {"source_role": role.value, "interpretation": interpretation}
            for role, interpretation in _CLOCK_SEMANTICS
        ],
        "disposition_counts": [
            {
                "view": view.value,
                "disposition": disposition.value,
                "count": count,
            }
            for view, disposition, count in disposition_counts
        ],
        "pair_id": pair.pair_id,
        "pair_sha256": pair.pair_sha256,
        "physical_raw_extraction_authenticated": True,
        "raw_response_bytes_retained_in_pair": False,
        "pristine_point_in_time": False,
        "caller_completeness_claim_accepted": False,
        "filesystem_io_performed": True,
        "provider_io_performed": False,
        "credential_access_performed": False,
        "quantconnect_io_performed": False,
        "outcome_access_performed": False,
    }


def _construct_bridge(
    artifact_path: Path, *, expected_transport: str
) -> MassiveAcceptedRiskBridge:
    slim, proof = _slim_authenticated_capture(artifact_path, expected_transport)
    # The preceding helper owns the only references to the complete physical
    # capture.  Collect before row derivation so raw responses and normalized
    # full history cannot overlap even on non-refcounting Python runtimes.
    gc.collect()
    try:
        pair = require_accepted_risk_input_pair(
            build_accepted_risk_input_pair(slim)
        )
    except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
        raise MassiveInputPairBridgeError(
            "accepted-risk pair construction refused the physical capture"
        ) from exc
    if (
        pair.report.total_row_count != proof.source_row_count
        or len(pair.rows) != proof.source_row_count
        or any(page.raw_response_bytes is not None for page in pair.capture.pages)
    ):
        raise MassiveInputPairBridgeError(
            "accepted-risk pair is not exhaustive or retained raw responses"
        )
    disposition_counts = _disposition_census(pair)
    record = _bridge_record(
        proof=proof, pair=pair, disposition_counts=disposition_counts
    )
    bridge_sha256 = sha256_bytes(canonical_json_bytes(record))
    bridge = object.__new__(MassiveAcceptedRiskBridge)
    values: dict[str, object] = {
        "schema": BRIDGE_SCHEMA,
        "contract_id": BRIDGE_CONTRACT_ID,
        "bridge_id": f"arv2-massive-accepted-risk-bridge-{bridge_sha256[:24]}",
        "bridge_sha256": bridge_sha256,
        "artifact_path": proof.artifact_path,
        "artifact_id": proof.artifact_id,
        "manifest_sha256": proof.manifest_sha256,
        "capture_transport": proof.capture_transport,
        "physical_capture_id": proof.physical_capture_id,
        "physical_capture_sha256": proof.physical_capture_sha256,
        "derived_capture_id": pair.capture.capture_id,
        "derived_capture_sha256": pair.capture.capture_sha256,
        "source_page_root_sha256": proof.source_page_root_sha256,
        "source_page_count": proof.source_page_count,
        "source_row_count": proof.source_row_count,
        "raw_response_total_byte_count": proof.raw_response_total_byte_count,
        "provider_rows_total_byte_count": proof.provider_rows_total_byte_count,
        "role_row_counts": proof.role_row_counts,
        "clock_semantics": _CLOCK_SEMANTICS,
        "disposition_counts": disposition_counts,
        "pair": pair,
        "physical_raw_extraction_authenticated": True,
        "raw_response_bytes_retained_in_pair": False,
        "pristine_point_in_time": False,
        "caller_completeness_claim_accepted": False,
        "filesystem_io_performed": True,
        "provider_io_performed": False,
        "credential_access_performed": False,
        "quantconnect_io_performed": False,
        "outcome_access_performed": False,
    }
    for name, value in values.items():
        object.__setattr__(bridge, name, value)
    identity = id(bridge)
    reference = weakref.ref(
        bridge, lambda ref, key=identity: _forget_bridge(key, ref)
    )
    with _BRIDGE_AUTHORITIES_LOCK:
        _BRIDGE_AUTHORITIES[identity] = (
            reference,
            _bridge_fingerprint(bridge),
        )
    return bridge


def require_massive_accepted_risk_bridge(
    value: MassiveAcceptedRiskBridge,
) -> MassiveAcceptedRiskBridge:
    if type(value) is not MassiveAcceptedRiskBridge:
        raise MassiveInputPairBridgeError(
            "bridge authority requires an exact MassiveAcceptedRiskBridge"
        )
    with _BRIDGE_AUTHORITIES_LOCK:
        authority = _BRIDGE_AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or _bridge_fingerprint(value) != authority[1]
    ):
        raise MassiveInputPairBridgeError(
            "bridge is not current builder-authenticated authority"
        )
    try:
        pair = require_accepted_risk_input_pair(value.pair)
    except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
        raise MassiveInputPairBridgeError("accepted-risk pair changed") from exc
    if (
        value.schema != BRIDGE_SCHEMA
        or value.contract_id != BRIDGE_CONTRACT_ID
        or value.bridge_id
        != f"arv2-massive-accepted-risk-bridge-{value.bridge_sha256[:24]}"
        or value.derived_capture_id != pair.capture.capture_id
        or value.derived_capture_sha256 != pair.capture.capture_sha256
        or value.source_page_root_sha256 != _source_page_root(pair.capture)
        or value.source_page_count != pair.capture.total_page_count
        or value.source_row_count != len(pair.rows)
        or value.role_row_counts != pair.capture.role_row_counts
        or value.clock_semantics != _CLOCK_SEMANTICS
        or value.disposition_counts != _disposition_census(pair)
        or any(page.raw_response_bytes is not None for page in pair.capture.pages)
    ):
        raise MassiveInputPairBridgeError("bridge semantic binding changed")
    truth = (
        value.physical_raw_extraction_authenticated,
        not value.raw_response_bytes_retained_in_pair,
        not value.pristine_point_in_time,
        not value.caller_completeness_claim_accepted,
        value.filesystem_io_performed,
        not value.provider_io_performed,
        not value.credential_access_performed,
        not value.quantconnect_io_performed,
        not value.outcome_access_performed,
    )
    if any(type(item) is not bool or item is not True for item in truth):
        raise MassiveInputPairBridgeError("bridge truth classification changed")
    proof = _PhysicalProof(
        artifact_path=value.artifact_path,
        artifact_id=value.artifact_id,
        manifest_sha256=value.manifest_sha256,
        capture_transport=value.capture_transport,
        physical_capture_id=value.physical_capture_id,
        physical_capture_sha256=value.physical_capture_sha256,
        source_page_root_sha256=value.source_page_root_sha256,
        source_page_count=value.source_page_count,
        source_row_count=value.source_row_count,
        raw_response_total_byte_count=value.raw_response_total_byte_count,
        provider_rows_total_byte_count=value.provider_rows_total_byte_count,
        role_row_counts=value.role_row_counts,
    )
    expected_sha256 = sha256_bytes(
        canonical_json_bytes(
            _bridge_record(
                proof=proof,
                pair=pair,
                disposition_counts=value.disposition_counts,
            )
        )
    )
    if value.bridge_sha256 != expected_sha256:
        raise MassiveInputPairBridgeError("bridge content root changed")
    return value


def build_massive_accepted_risk_input_pair(
    artifact_path: Path,
) -> MassiveAcceptedRiskBridge:
    """Authenticate one production capture and derive its two-view pair."""

    candidate = Path(artifact_path).absolute()
    allowed_root = _massive.REPOSITORY_ARTIFACTS_ROOT.absolute()
    try:
        within_root = os.path.commonpath((str(candidate), str(allowed_root))) == str(
            allowed_root
        )
    except ValueError:
        within_root = False
    if not within_root or candidate == allowed_root:
        raise MassiveInputPairBridgeError(
            "production bridge artifacts must be beneath repository artifacts/"
        )
    return require_massive_accepted_risk_bridge(
        _construct_bridge(
            candidate,
            expected_transport=_massive.PRODUCTION_TRANSPORT,
        )
    )


def _build_massive_accepted_risk_input_pair_for_test(
    artifact_path: Path,
) -> MassiveAcceptedRiskBridge:
    """Private offline seam; accepts only the capture adapter's test marker."""

    return require_massive_accepted_risk_bridge(
        _construct_bridge(
            Path(artifact_path).absolute(),
            expected_transport=_massive.TEST_TRANSPORT,
        )
    )


__all__ = [
    "BRIDGE_CONTRACT_ID",
    "BRIDGE_SCHEMA",
    "MAX_BRIDGE_PAGE_COUNT",
    "MAX_BRIDGE_PROVIDER_ROWS_BYTES",
    "MAX_BRIDGE_RETAINED_SOURCE_BYTES",
    "MAX_BRIDGE_ROW_BYTES",
    "MAX_BRIDGE_ROW_COUNT",
    "MAX_BRIDGE_SOURCE_PAYLOAD_PEAK_BYTES",
    "MassiveAcceptedRiskBridge",
    "MassiveInputPairBridgeError",
    "build_massive_accepted_risk_input_pair",
    "require_massive_accepted_risk_bridge",
]
