"""Offline parent-bound 2026 Massive successor contract.

This module composes two already-authenticated physical accepted-risk archives.
It has no provider, credential, QuantConnect, outcome, deployment, order, or
trading capability.  The parent remains the 2013--2025 vintage; the successor
is the literal 2026-01-01 through 2026-09-16 delta captured only after that
session's close.  The composite deliberately preserves both vintages instead
of relabelling them as one transactional or pristine point-in-time capture.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import threading
import weakref
from collections import Counter
from datetime import timedelta
from typing import Iterator

from research.analyst_revisions_v2 import (
    accepted_risk_input_pair as _accepted_risk,
)
from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskSourceRow,
    MassiveSourceRole,
)
from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes,
    parse_date,
    parse_utc_timestamp,
    require_identifier,
    require_sha256,
    sha256_bytes,
)
from research.analyst_revisions_v2_qc import (
    physical_accepted_risk_archive as _physical_archive,
)
from research.analyst_revisions_v2_qc.physical_accepted_risk_archive import (
    PhysicalAcceptedRiskArchive,
    iter_physical_accepted_risk_rows,
    require_physical_accepted_risk_archive,
)


SCHEMA = "arv2-parent-bound-massive-delta-v1"
CONTRACT_ID = "arv2-parent-bound-massive-delta-contract-v1"
PARENT_FIRST_EVENT_DATE = "2013-01-02"
PARENT_LAST_EVENT_DATE = "2025-12-31"
DELTA_FIRST_EVENT_DATE = "2026-01-01"
LITERAL_CUTOFF_SESSION = "2026-09-16"
LITERAL_CUTOFF_CLOSE_AT = "2026-09-16T20:00:00.000000Z"
CURRENT_VIEW = _accepted_risk.CURRENT_VIEW_LABEL
CENSORED_VIEW = _accepted_risk.CENSORED_VIEW_LABEL
ROW_PROJECTION_DOMAIN = b"arv2-parent-bound-massive-delta-rows-v1\0"
_ROLE_ORDER = (
    MassiveSourceRole.ANALYST_RATINGS,
    MassiveSourceRole.EARNINGS,
    MassiveSourceRole.CORPORATE_GUIDANCE,
)

_PINNED_ARCHIVE_TYPE = PhysicalAcceptedRiskArchive
_PINNED_REQUIRE_ARCHIVE = require_physical_accepted_risk_archive
_PINNED_ITER_ARCHIVE_ROWS = iter_physical_accepted_risk_rows
_PINNED_FOLD_ARCHIVE_ROWS = (
    _physical_archive._fold_authenticated_physical_accepted_risk_rows
)
_PINNED_AUTHENTICATED_ROW_TYPE = (
    _physical_archive._AuthenticatedAcceptedRiskSemanticRow
)
_PINNED_ROW_TYPE = AcceptedRiskSourceRow
_PINNED_ROW_TO_RECORD = AcceptedRiskSourceRow.to_record
_PINNED_PRODUCTION_TRANSPORT = _physical_archive._PINNED_PRODUCTION_TRANSPORT
_PINNED_TEST_TRANSPORT = _physical_archive._PINNED_TEST_TRANSPORT
_PINNED_HASHLIB_SHA256 = hashlib.sha256
_PINNED_CURRENT_VIEW = _accepted_risk.CURRENT_VIEW_LABEL
_PINNED_CENSORED_VIEW = _accepted_risk.CENSORED_VIEW_LABEL


class ParentBoundMassiveDeltaError(ValueError):
    """The parent/delta composite is not current authenticated authority."""


@dataclasses.dataclass(frozen=True, slots=True)
class CrossBoundaryGuidanceRefusal:
    refusal_id: str
    provider_event_id_sha256: str
    parent_occurrence_count: int
    delta_occurrence_count: int
    excluded_occurrence_count: int

    def to_record(self) -> dict[str, object]:
        return {
            "refusal_id": self.refusal_id,
            "source_role": MassiveSourceRole.CORPORATE_GUIDANCE.value,
            "provider_event_id_sha256": self.provider_event_id_sha256,
            "parent_occurrence_count": self.parent_occurrence_count,
            "delta_occurrence_count": self.delta_occurrence_count,
            "excluded_occurrence_count": self.excluded_occurrence_count,
            "disposition": "cross_boundary_duplicate_provider_event_id",
        }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class ParentBoundMassiveDelta:
    schema: str
    contract_id: str
    composite_id: str
    composite_sha256: str
    parent_archive: PhysicalAcceptedRiskArchive
    delta_archive: PhysicalAcceptedRiskArchive
    literal_cutoff_session: str
    literal_cutoff_close_at: str
    source_row_count: int
    admitted_row_count: int
    excluded_row_count: int
    current_view_included_count: int
    censored_view_included_count: int
    view_disagreement_count: int
    role_source_row_counts: tuple[tuple[MassiveSourceRole, int], ...]
    role_admitted_row_counts: tuple[tuple[MassiveSourceRole, int], ...]
    row_projection_sha256: str
    cross_boundary_guidance_refusals: tuple[
        CrossBoundaryGuidanceRefusal, ...
    ]
    multi_vintage: bool
    transactional_snapshot: bool
    pristine_point_in_time: bool
    complete_version_history: bool
    complete_deletion_tombstones: bool
    earlier_version_imputation_performed: bool
    production_transport: bool
    provider_access: bool
    credential_access: bool
    quantconnect_access: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool


_PINNED_COMPOSITE_TYPE = ParentBoundMassiveDelta
_PINNED_REFUSAL_TYPE = CrossBoundaryGuidanceRefusal
_PINNED_REFUSAL_TO_RECORD = CrossBoundaryGuidanceRefusal.to_record
_PINNED_COUNTER_TYPE = Counter
_PINNED_GETPID = os.getpid
_PINNED_WEAKREF_REF = weakref.ref
_PINNED_OBJECT_NEW = object.__new__
_PINNED_OBJECT_SETATTR = object.__setattr__


_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[ParentBoundMassiveDelta],
        str,
        int,
    ],
] = {}
_AUTHORITY_LOCK = threading.RLock()


def _forget(identity: int, reference: object) -> None:
    with _AUTHORITY_LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _AUTHORITIES.pop(identity, None)


def _archive_binding(archive: PhysicalAcceptedRiskArchive) -> dict[str, object]:
    return {
        "archive_id": archive.archive_id,
        "archive_sha256": archive.archive_sha256,
        "source_artifact_id": archive.source_artifact_id,
        "source_manifest_sha256": archive.source_manifest_sha256,
        "physical_capture_id": archive.physical_capture_id,
        "physical_capture_sha256": archive.physical_capture_sha256,
        "capture_id": archive.capture_id,
        "capture_sha256": archive.capture_sha256,
        "pair_id": archive.pair_id,
        "pair_sha256": archive.pair_sha256,
        "capture_transport": archive.capture_transport,
        "capture_started_at": archive.capture_started_at,
        "capture_completed_at": archive.capture_completed_at,
        "requested_first_event_date": archive.requested_first_event_date,
        "requested_last_event_date": archive.requested_last_event_date,
        "source_page_count": archive.source_page_count,
        "source_row_count": archive.source_row_count,
        "current_view_included_count": archive.current_included_count,
        "censored_view_included_count": archive.censored_included_count,
        "view_disagreement_count": archive.disagreement_count,
        "role_row_counts": [
            {"source_role": role.value, "row_count": count}
            for role, count in archive.role_row_counts
        ],
    }


def _manifest_seed(value: ParentBoundMassiveDelta) -> dict[str, object]:
    return {
        "schema": value.schema,
        "contract_id": value.contract_id,
        "parent": _archive_binding(value.parent_archive),
        "delta": _archive_binding(value.delta_archive),
        "boundary": {
            "parent_last_event_date": PARENT_LAST_EVENT_DATE,
            "delta_first_event_date": DELTA_FIRST_EVENT_DATE,
            "exact_calendar_adjacency": True,
            "literal_cutoff_session": value.literal_cutoff_session,
            "literal_cutoff_close_at": value.literal_cutoff_close_at,
            "delta_capture_started_not_before_cutoff_close": True,
        },
        "source_roles": [role.value for role in _ROLE_ORDER],
        "row_stream": {
            "order": "authenticated_parent_rows_then_authenticated_delta_rows",
            "source_row_count": value.source_row_count,
            "admitted_row_count": value.admitted_row_count,
            "excluded_row_count": value.excluded_row_count,
            "admitted_row_count_semantics": (
                "source_rows_not_excluded_by_cross_boundary_guidance_policy"
            ),
            "current_view_included_count": value.current_view_included_count,
            "censored_view_included_count": value.censored_view_included_count,
            "view_disagreement_count": value.view_disagreement_count,
            "role_source_row_counts": [
                {"source_role": role.value, "row_count": count}
                for role, count in value.role_source_row_counts
            ],
            "role_admitted_row_counts": [
                {"source_role": role.value, "row_count": count}
                for role, count in value.role_admitted_row_counts
            ],
            "projection_domain": ROW_PROJECTION_DOMAIN[:-1].decode("ascii"),
            "projection_sha256": value.row_projection_sha256,
        },
        "cross_boundary_duplicate_policy": {
            "analyst_ratings": "refuse_entire_composite",
            "earnings": "refuse_entire_composite",
            "role_mismatch": "refuse_entire_composite",
            "corporate_guidance": (
                "exclude_every_parent_and_delta_occurrence_and_emit_named_refusal"
            ),
            "refusals": [
                _PINNED_REFUSAL_TO_RECORD(refusal)
                for refusal in value.cross_boundary_guidance_refusals
            ],
        },
        "accepted_risk_disclosures": {
            "current_view": CURRENT_VIEW,
            "censored_view": CENSORED_VIEW,
            "multi_vintage": value.multi_vintage,
            "transactional_snapshot": value.transactional_snapshot,
            "pristine_point_in_time": value.pristine_point_in_time,
            "complete_version_history": value.complete_version_history,
            "complete_deletion_tombstones": value.complete_deletion_tombstones,
            "earlier_version_imputation_performed": (
                value.earlier_version_imputation_performed
            ),
            "production_transport": value.production_transport,
            "ticker_semantics": "current_restated_security_label",
            "last_updated_semantics": "last_vendor_touch_not_revision_time",
            "guidance_intraday_clock": "unresolved",
            "transactional_cross_vintage_claim": False,
            "security_admission": (
                "not_provided_by_massive_requires_separate_point_in_time_"
                "sharadar_authority"
            ),
        },
        "capabilities": {
            "provider_access": value.provider_access,
            "credential_access": value.credential_access,
            "quantconnect_access": value.quantconnect_access,
            "outcome_access": value.outcome_access,
            "result_access": value.result_access,
            "deployment": value.deployment,
            "orders": value.orders,
            "trading": value.trading,
        },
    }


def _fingerprint(value: ParentBoundMassiveDelta) -> str:
    return sha256_bytes(canonical_json_bytes(_manifest_seed(value)))


def _validate_geometry(
    parent: PhysicalAcceptedRiskArchive,
    delta: PhysicalAcceptedRiskArchive,
) -> None:
    if (
        parent.requested_first_event_date != PARENT_FIRST_EVENT_DATE
        or parent.requested_last_event_date != PARENT_LAST_EVENT_DATE
    ):
        raise ParentBoundMassiveDeltaError(
            "parent archive is not the exact 2013-01-02 through 2025-12-31 authority"
        )
    if (
        delta.requested_first_event_date != DELTA_FIRST_EVENT_DATE
        or delta.requested_last_event_date != LITERAL_CUTOFF_SESSION
    ):
        raise ParentBoundMassiveDeltaError(
            "delta archive is not the exact 2026-01-01 through 2026-09-16 successor"
        )
    if (
        parse_date(DELTA_FIRST_EVENT_DATE, "delta first event date")
        != parse_date(PARENT_LAST_EVENT_DATE, "parent last event date")
        + timedelta(days=1)
    ):
        raise ParentBoundMassiveDeltaError(
            "parent and delta event-date ranges are not exactly adjacent"
        )
    cutoff_close = parse_utc_timestamp(
        LITERAL_CUTOFF_CLOSE_AT, "literal cutoff close"
    )
    delta_started = parse_utc_timestamp(
        delta.capture_started_at, "delta capture_started_at"
    )
    parent_completed = parse_utc_timestamp(
        parent.capture_completed_at, "parent capture_completed_at"
    )
    if delta_started < cutoff_close:
        raise ParentBoundMassiveDeltaError(
            "delta capture started before the literal cutoff session close"
        )
    if parent_completed >= delta_started:
        raise ParentBoundMassiveDeltaError(
            "parent and delta do not preserve two ordered capture vintages"
        )
    if tuple(role for role, _ in parent.role_row_counts) != _ROLE_ORDER:
        raise ParentBoundMassiveDeltaError(
            "parent archive does not bind all three roles"
        )
    if tuple(role for role, _ in delta.role_row_counts) != _ROLE_ORDER:
        raise ParentBoundMassiveDeltaError(
            "delta archive does not bind all three roles"
        )
    identity_pairs = (
        (parent.archive_id, delta.archive_id),
        (parent.archive_sha256, delta.archive_sha256),
        (parent.source_artifact_id, delta.source_artifact_id),
        (parent.source_manifest_sha256, delta.source_manifest_sha256),
        (parent.physical_capture_id, delta.physical_capture_id),
        (parent.physical_capture_sha256, delta.physical_capture_sha256),
        (parent.capture_id, delta.capture_id),
        (parent.capture_sha256, delta.capture_sha256),
        (parent.pair_id, delta.pair_id),
        (parent.pair_sha256, delta.pair_sha256),
    )
    if any(left == right for left, right in identity_pairs):
        raise ParentBoundMassiveDeltaError(
            "parent and delta identities are not distinct"
        )


def _event_id_sha256(provider_event_id: str) -> str:
    return sha256_bytes(
        canonical_json_bytes({"provider_event_id": provider_event_id})
    )


def _require_row_type(row: AcceptedRiskSourceRow) -> None:
    if type(row) is not _PINNED_ROW_TYPE:
        raise ParentBoundMassiveDeltaError(
            "physical archive yielded a non-canonical source row"
        )


def _row_payload(row: AcceptedRiskSourceRow) -> bytes:
    _require_row_type(row)
    return canonical_json_bytes(_PINNED_ROW_TO_RECORD(row))


def _add_projected_row(
    row: AcceptedRiskSourceRow,
    payload: bytes,
    *,
    digest: object,
    role_counts: Counter[MassiveSourceRole],
) -> None:
    if type(payload) is not bytes:
        raise ParentBoundMassiveDeltaError("row projection payload changed type")
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)
    role_counts[row.locator.source_role] += 1


def _authenticated_fold_parts(item: object) -> tuple[AcceptedRiskSourceRow, bytes]:
    if type(item) is not _PINNED_AUTHENTICATED_ROW_TYPE:
        raise ParentBoundMassiveDeltaError(
            "physical archive fold yielded a non-canonical wrapper"
        )
    row = item.row
    payload = item.canonical_record_bytes
    _require_row_type(row)
    if type(payload) is not bytes:
        raise ParentBoundMassiveDeltaError(
            "physical archive fold payload changed type"
        )
    return row, payload


def _analyze_parent_and_delta(
    parent: PhysicalAcceptedRiskArchive,
    delta: PhysicalAcceptedRiskArchive,
) -> tuple[
    tuple[CrossBoundaryGuidanceRefusal, ...],
    int,
    tuple[tuple[MassiveSourceRole, int], ...],
    str,
    int,
    int,
]:
    """Index the small delta, then authenticate and project the parent once."""

    delta_ids: dict[str, tuple[MassiveSourceRole, int]] = {}

    def index_delta(item: object) -> None:
        row, _payload = _authenticated_fold_parts(item)
        if row.provider_event_id is None:
            return
        prior = delta_ids.get(row.provider_event_id)
        if prior is None:
            delta_ids[row.provider_event_id] = (row.locator.source_role, 1)
        elif prior[0] is not row.locator.source_role:
            raise ParentBoundMassiveDeltaError(
                "delta provider event ID crosses source roles"
            )
        else:
            delta_ids[row.provider_event_id] = (prior[0], prior[1] + 1)

    _PINNED_FOLD_ARCHIVE_ROWS(delta, index_delta)

    digest = _PINNED_HASHLIB_SHA256(ROW_PROJECTION_DOMAIN)
    role_counts: Counter[MassiveSourceRole] = _PINNED_COUNTER_TYPE()
    admitted_count = 0
    excluded_current_count = 0
    excluded_censored_count = 0
    parent_overlap_counts: Counter[str] = _PINNED_COUNTER_TYPE()
    def project_parent(item: object) -> None:
        nonlocal admitted_count, excluded_current_count, excluded_censored_count
        row, payload = _authenticated_fold_parts(item)
        delta_identity = (
            None
            if row.provider_event_id is None
            else delta_ids.get(row.provider_event_id)
        )
        if delta_identity is not None:
            delta_role, _delta_count = delta_identity
            if delta_role is not row.locator.source_role:
                raise ParentBoundMassiveDeltaError(
                    "cross-boundary provider event ID changes source role"
                )
            if row.locator.source_role is not MassiveSourceRole.CORPORATE_GUIDANCE:
                raise ParentBoundMassiveDeltaError(
                    "cross-boundary "
                    f"{row.locator.source_role.value} provider event ID is forbidden"
                )
            parent_overlap_counts[row.provider_event_id] += 1
            excluded_current_count += int(row.current_view.included)
            excluded_censored_count += int(row.censored_view.included)
            return
        _add_projected_row(
            row, payload, digest=digest, role_counts=role_counts
        )
        admitted_count += 1

    _PINNED_FOLD_ARCHIVE_ROWS(parent, project_parent)

    refusal_rows: list[tuple[str, str, int, int]] = []
    seen_hashes: dict[str, str] = {}
    for event_id, parent_count in parent_overlap_counts.items():
        event_hash = _event_id_sha256(event_id)
        prior_event_id = seen_hashes.get(event_hash)
        if prior_event_id is not None and prior_event_id != event_id:
            raise ParentBoundMassiveDeltaError(
                "provider event ID digest collision"
            )
        seen_hashes[event_hash] = event_id
        refusal_rows.append(
            (event_hash, event_id, parent_count, delta_ids[event_id][1])
        )
    refusal_rows.sort(key=lambda item: item[0])
    refused_event_ids = frozenset(item[1] for item in refusal_rows)

    def project_delta(item: object) -> None:
        nonlocal admitted_count, excluded_current_count, excluded_censored_count
        row, payload = _authenticated_fold_parts(item)
        if row.provider_event_id in refused_event_ids:
            excluded_current_count += int(row.current_view.included)
            excluded_censored_count += int(row.censored_view.included)
            return
        _add_projected_row(
            row, payload, digest=digest, role_counts=role_counts
        )
        admitted_count += 1

    _PINNED_FOLD_ARCHIVE_ROWS(delta, project_delta)

    refusals: list[CrossBoundaryGuidanceRefusal] = []
    for event_hash, _event_id, parent_count, delta_count in refusal_rows:
        refusal_seed = {
            "schema": "arv2-cross-boundary-guidance-refusal-v1",
            "provider_event_id_sha256": event_hash,
            "parent_occurrence_count": parent_count,
            "delta_occurrence_count": delta_count,
            "excluded_occurrence_count": parent_count + delta_count,
        }
        refusal_sha256 = sha256_bytes(canonical_json_bytes(refusal_seed))
        refusals.append(
            _PINNED_REFUSAL_TYPE(
                refusal_id=(
                    "arv2-cross-boundary-guidance-refusal-"
                    f"{refusal_sha256[:24]}"
                ),
                provider_event_id_sha256=event_hash,
                parent_occurrence_count=parent_count,
                delta_occurrence_count=delta_count,
                excluded_occurrence_count=parent_count + delta_count,
            )
        )
    return (
        tuple(refusals),
        admitted_count,
        tuple((role, role_counts[role]) for role in _ROLE_ORDER),
        digest.hexdigest(),
        excluded_current_count,
        excluded_censored_count,
    )


def _iter_admitted_rows_unchecked(
    parent: PhysicalAcceptedRiskArchive,
    delta: PhysicalAcceptedRiskArchive,
    refused_hashes: frozenset[str],
) -> Iterator[AcceptedRiskSourceRow]:
    for archive in (parent, delta):
        for row in _PINNED_ITER_ARCHIVE_ROWS(archive):
            if (
                row.locator.source_role is MassiveSourceRole.CORPORATE_GUIDANCE
                and row.provider_event_id is not None
                and _PINNED_EVENT_ID_SHA256(row.provider_event_id) in refused_hashes
            ):
                continue
            yield row


_MISSING = object()
_PINNED_AUTHORITIES = _AUTHORITIES
_PINNED_AUTHORITY_LOCK = _AUTHORITY_LOCK
_PINNED_ROLE_ORDER = _ROLE_ORDER
_PINNED_LOCAL_BINDINGS = (
    ("PhysicalAcceptedRiskArchive", PhysicalAcceptedRiskArchive),
    ("AcceptedRiskSourceRow", AcceptedRiskSourceRow),
    ("MassiveSourceRole", MassiveSourceRole),
    ("ParentBoundMassiveDelta", ParentBoundMassiveDelta),
    ("CrossBoundaryGuidanceRefusal", CrossBoundaryGuidanceRefusal),
    ("Counter", Counter),
    (
        "iter_physical_accepted_risk_rows",
        iter_physical_accepted_risk_rows,
    ),
    (
        "require_physical_accepted_risk_archive",
        require_physical_accepted_risk_archive,
    ),
    ("canonical_json_bytes", canonical_json_bytes),
    ("parse_date", parse_date),
    ("parse_utc_timestamp", parse_utc_timestamp),
    ("require_identifier", require_identifier),
    ("require_sha256", require_sha256),
    ("sha256_bytes", sha256_bytes),
    ("_forget", _forget),
    ("_archive_binding", _archive_binding),
    ("_manifest_seed", _manifest_seed),
    ("_fingerprint", _fingerprint),
    ("_validate_geometry", _validate_geometry),
    ("_event_id_sha256", _event_id_sha256),
    ("_require_row_type", _require_row_type),
    ("_row_payload", _row_payload),
    ("_add_projected_row", _add_projected_row),
    ("_authenticated_fold_parts", _authenticated_fold_parts),
    ("_analyze_parent_and_delta", _analyze_parent_and_delta),
    ("_iter_admitted_rows_unchecked", _iter_admitted_rows_unchecked),
)
_PINNED_SCALARS = (
    SCHEMA,
    CONTRACT_ID,
    PARENT_FIRST_EVENT_DATE,
    PARENT_LAST_EVENT_DATE,
    DELTA_FIRST_EVENT_DATE,
    LITERAL_CUTOFF_SESSION,
    LITERAL_CUTOFF_CLOSE_AT,
    CURRENT_VIEW,
    CENSORED_VIEW,
    ROW_PROJECTION_DOMAIN,
)
_PINNED_VALIDATE_GEOMETRY = _validate_geometry
_PINNED_FORGET = _forget
_PINNED_ANALYZE_PARENT_AND_DELTA = _analyze_parent_and_delta
_PINNED_FINGERPRINT = _fingerprint
_PINNED_MANIFEST_SEED = _manifest_seed
_PINNED_EVENT_ID_SHA256 = _event_id_sha256
_PINNED_ITER_ADMITTED_ROWS_UNCHECKED = _iter_admitted_rows_unchecked
_PINNED_ROW_PAYLOAD = _row_payload
_PINNED_LOCAL_BINDINGS += (
    ("_PINNED_PRODUCTION_TRANSPORT", _PINNED_PRODUCTION_TRANSPORT),
    ("_PINNED_TEST_TRANSPORT", _PINNED_TEST_TRANSPORT),
    ("_PINNED_CURRENT_VIEW", _PINNED_CURRENT_VIEW),
    ("_PINNED_CENSORED_VIEW", _PINNED_CENSORED_VIEW),
    ("_PINNED_ARCHIVE_TYPE", _PINNED_ARCHIVE_TYPE),
    ("_PINNED_REQUIRE_ARCHIVE", _PINNED_REQUIRE_ARCHIVE),
    ("_PINNED_ITER_ARCHIVE_ROWS", _PINNED_ITER_ARCHIVE_ROWS),
    ("_PINNED_FOLD_ARCHIVE_ROWS", _PINNED_FOLD_ARCHIVE_ROWS),
    ("_PINNED_AUTHENTICATED_ROW_TYPE", _PINNED_AUTHENTICATED_ROW_TYPE),
    ("_PINNED_ROW_TYPE", _PINNED_ROW_TYPE),
    ("_PINNED_ROW_TO_RECORD", _PINNED_ROW_TO_RECORD),
    ("_PINNED_HASHLIB_SHA256", _PINNED_HASHLIB_SHA256),
    ("_PINNED_VALIDATE_GEOMETRY", _PINNED_VALIDATE_GEOMETRY),
    ("_PINNED_FORGET", _PINNED_FORGET),
    (
        "_PINNED_ANALYZE_PARENT_AND_DELTA",
        _PINNED_ANALYZE_PARENT_AND_DELTA,
    ),
    ("_PINNED_FINGERPRINT", _PINNED_FINGERPRINT),
    ("_PINNED_MANIFEST_SEED", _PINNED_MANIFEST_SEED),
    ("_PINNED_EVENT_ID_SHA256", _PINNED_EVENT_ID_SHA256),
    (
        "_PINNED_ITER_ADMITTED_ROWS_UNCHECKED",
        _PINNED_ITER_ADMITTED_ROWS_UNCHECKED,
    ),
    ("_PINNED_ROW_PAYLOAD", _PINNED_ROW_PAYLOAD),
    ("_PINNED_COMPOSITE_TYPE", _PINNED_COMPOSITE_TYPE),
    ("_PINNED_REFUSAL_TYPE", _PINNED_REFUSAL_TYPE),
    ("_PINNED_REFUSAL_TO_RECORD", _PINNED_REFUSAL_TO_RECORD),
    ("_PINNED_COUNTER_TYPE", _PINNED_COUNTER_TYPE),
    ("_PINNED_GETPID", _PINNED_GETPID),
    ("_PINNED_WEAKREF_REF", _PINNED_WEAKREF_REF),
    ("_PINNED_OBJECT_NEW", _PINNED_OBJECT_NEW),
    ("_PINNED_OBJECT_SETATTR", _PINNED_OBJECT_SETATTR),
)


def _require_dependencies(
    _bindings: tuple[tuple[str, object], ...] = _PINNED_LOCAL_BINDINGS,
    _scalars: tuple[object, ...] = _PINNED_SCALARS,
    _module_globals: dict[str, object] = globals(),
    _authority_root: object = _AUTHORITIES,
    _authority_lock: object = _AUTHORITY_LOCK,
) -> None:
    current_scalars = (
        SCHEMA,
        CONTRACT_ID,
        PARENT_FIRST_EVENT_DATE,
        PARENT_LAST_EVENT_DATE,
        DELTA_FIRST_EVENT_DATE,
        LITERAL_CUTOFF_SESSION,
        LITERAL_CUTOFF_CLOSE_AT,
        CURRENT_VIEW,
        CENSORED_VIEW,
        ROW_PROJECTION_DOMAIN,
    )
    if (
        globals() is not _module_globals
        or any(
            _module_globals.get(name, _MISSING) is not expected
            for name, expected in _bindings
        )
        or len(current_scalars) != len(_scalars)
        or any(
            current is not expected
            for current, expected in zip(current_scalars, _scalars, strict=True)
        )
        or _ROLE_ORDER is not _PINNED_ROLE_ORDER
        or _AUTHORITIES is not _authority_root
        or _AUTHORITY_LOCK is not _authority_lock
        or _PINNED_AUTHORITIES is not _authority_root
        or _PINNED_AUTHORITY_LOCK is not _authority_lock
        or _physical_archive._PINNED_PRODUCTION_TRANSPORT
        is not _PINNED_PRODUCTION_TRANSPORT
        or _physical_archive._PINNED_TEST_TRANSPORT is not _PINNED_TEST_TRANSPORT
        or _physical_archive._fold_authenticated_physical_accepted_risk_rows
        is not _PINNED_FOLD_ARCHIVE_ROWS
        or _physical_archive._AuthenticatedAcceptedRiskSemanticRow
        is not _PINNED_AUTHENTICATED_ROW_TYPE
        or _accepted_risk.CURRENT_VIEW_LABEL is not _PINNED_CURRENT_VIEW
        or _accepted_risk.CENSORED_VIEW_LABEL is not _PINNED_CENSORED_VIEW
        or hashlib.sha256 is not _PINNED_HASHLIB_SHA256
    ):
        raise ParentBoundMassiveDeltaError(
            "parent-bound Massive delta dependency changed"
        )


_PINNED_REQUIRE_DEPENDENCIES = _require_dependencies


def _build_parent_bound_massive_delta(
    *,
    parent_archive: PhysicalAcceptedRiskArchive,
    delta_archive: PhysicalAcceptedRiskArchive,
    expected_parent_archive_id: str,
    expected_parent_archive_sha256: str,
    expected_delta_archive_id: str,
    expected_delta_archive_sha256: str,
    fixture_only: bool,
) -> ParentBoundMassiveDelta:
    _PINNED_REQUIRE_DEPENDENCIES()
    if type(fixture_only) is not bool:
        raise ParentBoundMassiveDeltaError("fixture_only must be an exact boolean")
    if not all(
        type(value) is str
        for value in (
            expected_parent_archive_id,
            expected_parent_archive_sha256,
            expected_delta_archive_id,
            expected_delta_archive_sha256,
        )
    ):
        raise ParentBoundMassiveDeltaError(
            "archive identity pins must be exact strings"
        )

    require_identifier(expected_parent_archive_id, "expected parent archive ID")
    require_sha256(expected_parent_archive_sha256, "expected parent archive SHA-256")
    require_identifier(expected_delta_archive_id, "expected delta archive ID")
    require_sha256(expected_delta_archive_sha256, "expected delta archive SHA-256")
    if type(parent_archive) is not _PINNED_ARCHIVE_TYPE:
        raise ParentBoundMassiveDeltaError("parent archive has the wrong type")
    if type(delta_archive) is not _PINNED_ARCHIVE_TYPE:
        raise ParentBoundMassiveDeltaError("delta archive has the wrong type")
    parent = _PINNED_REQUIRE_ARCHIVE(parent_archive)
    delta = _PINNED_REQUIRE_ARCHIVE(delta_archive)
    if (
        parent.archive_id != expected_parent_archive_id
        or parent.archive_sha256 != expected_parent_archive_sha256
    ):
        raise ParentBoundMassiveDeltaError("parent archive identity pin mismatch")
    if (
        delta.archive_id != expected_delta_archive_id
        or delta.archive_sha256 != expected_delta_archive_sha256
    ):
        raise ParentBoundMassiveDeltaError("delta archive identity pin mismatch")
    expected_transport = (
        _PINNED_TEST_TRANSPORT if fixture_only else _PINNED_PRODUCTION_TRANSPORT
    )
    if (
        type(parent.capture_transport) is not str
        or type(delta.capture_transport) is not str
        or parent.capture_transport != expected_transport
        or delta.capture_transport != expected_transport
    ):
        message = (
            "fixture parent-bound Massive delta requires exact test transports"
            if fixture_only
            else "production parent-bound Massive delta requires production transports"
        )
        raise ParentBoundMassiveDeltaError(message)
    _PINNED_VALIDATE_GEOMETRY(parent, delta)
    (
        refusals,
        admitted_count,
        admitted_role_counts,
        projection_sha256,
        excluded_current_count,
        excluded_censored_count,
    ) = _PINNED_ANALYZE_PARENT_AND_DELTA(
        parent,
        delta,
    )
    source_role_counts = tuple(
        (
            role,
            dict(parent.role_row_counts)[role] + dict(delta.role_row_counts)[role],
        )
        for role in _ROLE_ORDER
    )
    source_count = parent.source_row_count + delta.source_row_count
    excluded_count = sum(
        refusal.excluded_occurrence_count for refusal in refusals
    )
    if admitted_count + excluded_count != source_count:
        raise ParentBoundMassiveDeltaError(
            "composite row census does not reconcile"
        )
    current_included_count = (
        parent.current_included_count
        + delta.current_included_count
        - excluded_current_count
    )
    censored_included_count = (
        parent.censored_included_count
        + delta.censored_included_count
        - excluded_censored_count
    )
    disagreement_count = current_included_count - censored_included_count
    if not (
        0 <= censored_included_count <= current_included_count <= admitted_count
        and disagreement_count
        == parent.disagreement_count
        + delta.disagreement_count
        - excluded_current_count
        + excluded_censored_count
    ):
        raise ParentBoundMassiveDeltaError(
            "composite view census does not reconcile"
        )

    value = _PINNED_OBJECT_NEW(_PINNED_COMPOSITE_TYPE)
    fields: dict[str, object] = {
        "schema": SCHEMA,
        "contract_id": CONTRACT_ID,
        "composite_id": "",
        "composite_sha256": "",
        "parent_archive": parent,
        "delta_archive": delta,
        "literal_cutoff_session": LITERAL_CUTOFF_SESSION,
        "literal_cutoff_close_at": LITERAL_CUTOFF_CLOSE_AT,
        "source_row_count": source_count,
        "admitted_row_count": admitted_count,
        "excluded_row_count": excluded_count,
        "current_view_included_count": current_included_count,
        "censored_view_included_count": censored_included_count,
        "view_disagreement_count": disagreement_count,
        "role_source_row_counts": source_role_counts,
        "role_admitted_row_counts": admitted_role_counts,
        "row_projection_sha256": projection_sha256,
        "cross_boundary_guidance_refusals": refusals,
        "multi_vintage": True,
        "transactional_snapshot": False,
        "pristine_point_in_time": False,
        "complete_version_history": False,
        "complete_deletion_tombstones": False,
        "earlier_version_imputation_performed": False,
        "production_transport": not fixture_only,
        "provider_access": False,
        "credential_access": False,
        "quantconnect_access": False,
        "outcome_access": False,
        "result_access": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    for name, field_value in fields.items():
        _PINNED_OBJECT_SETATTR(value, name, field_value)
    composite_sha256 = _PINNED_FINGERPRINT(value)
    _PINNED_OBJECT_SETATTR(value, "composite_sha256", composite_sha256)
    _PINNED_OBJECT_SETATTR(
        value,
        "composite_id",
        f"arv2-parent-bound-massive-delta-{composite_sha256[:24]}",
    )
    fingerprint = _PINNED_FINGERPRINT(value)
    reference = _PINNED_WEAKREF_REF(
        value, lambda ref, identity=id(value): _PINNED_FORGET(identity, ref)
    )
    with _AUTHORITY_LOCK:
        _AUTHORITIES[id(value)] = (reference, fingerprint, _PINNED_GETPID())
    return value


_PINNED_INTERNAL_BUILD = _build_parent_bound_massive_delta


def build_parent_bound_massive_delta(
    *,
    parent_archive: PhysicalAcceptedRiskArchive,
    delta_archive: PhysicalAcceptedRiskArchive,
    expected_parent_archive_id: str,
    expected_parent_archive_sha256: str,
    expected_delta_archive_id: str,
    expected_delta_archive_sha256: str,
) -> ParentBoundMassiveDelta:
    """Bind two exact production Massive archives without external access."""

    _PINNED_REQUIRE_DEPENDENCIES()
    if globals().get("_build_parent_bound_massive_delta") is not _PINNED_INTERNAL_BUILD:
        raise ParentBoundMassiveDeltaError(
            "parent-bound Massive delta dependency changed"
        )
    return _PINNED_INTERNAL_BUILD(
        parent_archive=parent_archive,
        delta_archive=delta_archive,
        expected_parent_archive_id=expected_parent_archive_id,
        expected_parent_archive_sha256=expected_parent_archive_sha256,
        expected_delta_archive_id=expected_delta_archive_id,
        expected_delta_archive_sha256=expected_delta_archive_sha256,
        fixture_only=False,
    )


def _build_parent_bound_massive_delta_for_test(
    *,
    parent_archive: PhysicalAcceptedRiskArchive,
    delta_archive: PhysicalAcceptedRiskArchive,
    expected_parent_archive_id: str,
    expected_parent_archive_sha256: str,
    expected_delta_archive_id: str,
    expected_delta_archive_sha256: str,
) -> ParentBoundMassiveDelta:
    """Narrow fixture seam; its output is explicitly non-production authority."""

    _PINNED_REQUIRE_DEPENDENCIES()
    return _PINNED_INTERNAL_BUILD(
        parent_archive=parent_archive,
        delta_archive=delta_archive,
        expected_parent_archive_id=expected_parent_archive_id,
        expected_parent_archive_sha256=expected_parent_archive_sha256,
        expected_delta_archive_id=expected_delta_archive_id,
        expected_delta_archive_sha256=expected_delta_archive_sha256,
        fixture_only=True,
    )


def require_parent_bound_massive_delta(
    value: ParentBoundMassiveDelta,
) -> ParentBoundMassiveDelta:
    """Reauthenticate a builder-issued composite and both physical archives."""

    _PINNED_REQUIRE_DEPENDENCIES()
    if globals().get("_build_parent_bound_massive_delta") is not _PINNED_INTERNAL_BUILD:
        raise ParentBoundMassiveDeltaError(
            "parent-bound Massive delta dependency changed"
        )
    if type(value) is not _PINNED_COMPOSITE_TYPE:
        raise ParentBoundMassiveDeltaError("composite has the wrong type")
    with _AUTHORITY_LOCK:
        authority = _AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or authority[2] != _PINNED_GETPID()
    ):
        raise ParentBoundMassiveDeltaError(
            "composite is not current builder authority"
        )
    _PINNED_REQUIRE_ARCHIVE(value.parent_archive)
    _PINNED_REQUIRE_ARCHIVE(value.delta_archive)
    if type(value.production_transport) is not bool:
        raise ParentBoundMassiveDeltaError(
            "composite production transport flag changed type"
        )
    expected_transport = (
        _PINNED_PRODUCTION_TRANSPORT
        if value.production_transport
        else _PINNED_TEST_TRANSPORT
    )
    if (
        value.parent_archive.capture_transport != expected_transport
        or value.delta_archive.capture_transport != expected_transport
    ):
        raise ParentBoundMassiveDeltaError("composite capture transport changed")
    _PINNED_VALIDATE_GEOMETRY(value.parent_archive, value.delta_archive)
    if _PINNED_FINGERPRINT(value) != authority[1]:
        raise ParentBoundMassiveDeltaError("composite authority changed")
    seed_sha256 = sha256_bytes(
        canonical_json_bytes(_PINNED_MANIFEST_SEED(value))
    )
    if seed_sha256 != value.composite_sha256:
        raise ParentBoundMassiveDeltaError("composite content root changed")
    if value.composite_id != f"arv2-parent-bound-massive-delta-{seed_sha256[:24]}":
        raise ParentBoundMassiveDeltaError("composite ID/content root mismatch")
    return value


_PINNED_REQUIRE_COMPOSITE = require_parent_bound_massive_delta


_FINAL_LOCAL_BINDINGS = (
    ("_require_dependencies", _require_dependencies),
    ("_PINNED_REQUIRE_DEPENDENCIES", _PINNED_REQUIRE_DEPENDENCIES),
    ("_build_parent_bound_massive_delta", _build_parent_bound_massive_delta),
    ("_PINNED_INTERNAL_BUILD", _PINNED_INTERNAL_BUILD),
    ("_PINNED_REQUIRE_COMPOSITE", _PINNED_REQUIRE_COMPOSITE),
)


def _require_final_dependencies(
    _base: object = _require_dependencies,
    _bindings: tuple[tuple[str, object], ...] = _FINAL_LOCAL_BINDINGS,
    _module_globals: dict[str, object] = globals(),
    _missing: object = _MISSING,
) -> None:
    _base()
    if globals() is not _module_globals or any(
        _module_globals.get(name, _missing) is not expected
        for name, expected in _bindings
    ):
        raise ParentBoundMassiveDeltaError(
            "parent-bound Massive delta dependency changed"
        )


def render_parent_bound_massive_delta_manifest_bytes(
    value: ParentBoundMassiveDelta,
) -> bytes:
    """Render the deterministic composite manifest."""

    _PINNED_REQUIRE_DEPENDENCIES()
    current = _PINNED_REQUIRE_COMPOSITE(value)
    return canonical_json_bytes(
        {
            **_PINNED_MANIFEST_SEED(current),
            "composite_id": current.composite_id,
            "composite_sha256": current.composite_sha256,
        }
    )


def iter_parent_bound_massive_delta_rows(
    value: ParentBoundMassiveDelta,
) -> Iterator[AcceptedRiskSourceRow]:
    """Stream the authenticated composite, excluding named guidance refusals."""

    _PINNED_REQUIRE_DEPENDENCIES()
    current = _PINNED_REQUIRE_COMPOSITE(value)
    refused = frozenset(
        refusal.provider_event_id_sha256
        for refusal in current.cross_boundary_guidance_refusals
    )
    digest = _PINNED_HASHLIB_SHA256(ROW_PROJECTION_DOMAIN)
    count = 0
    role_counts: Counter[MassiveSourceRole] = _PINNED_COUNTER_TYPE()
    for row in _PINNED_ITER_ADMITTED_ROWS_UNCHECKED(
        current.parent_archive, current.delta_archive, refused
    ):
        payload = _PINNED_ROW_PAYLOAD(row)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
        count += 1
        role_counts[row.locator.source_role] += 1
        yield row
    actual_role_counts = tuple((role, role_counts[role]) for role in _ROLE_ORDER)
    if (
        count != current.admitted_row_count
        or actual_role_counts != current.role_admitted_row_counts
        or digest.hexdigest() != current.row_projection_sha256
    ):
        raise ParentBoundMassiveDeltaError(
            "composite stream no longer matches its deterministic projection"
        )


def _seal_entry(function: object, checker: object, *, generator: bool = False):
    """Capture the checker in a closure so rebinding its module name cannot bypass it."""

    if generator:
        def sealed(*args, **kwargs):
            checker()
            iterator = function(*args, **kwargs)

            def guarded():
                while True:
                    checker()
                    try:
                        item = next(iterator)
                    except StopIteration:
                        checker()
                        return
                    checker()
                    yield item

            return guarded()
    else:
        def sealed(*args, **kwargs):
            checker()
            return function(*args, **kwargs)
    sealed.__name__ = function.__name__
    sealed.__qualname__ = function.__qualname__
    sealed.__doc__ = function.__doc__
    sealed.__module__ = function.__module__
    return sealed


build_parent_bound_massive_delta = _seal_entry(
    build_parent_bound_massive_delta,
    _require_final_dependencies,
)
_build_parent_bound_massive_delta_for_test = _seal_entry(
    _build_parent_bound_massive_delta_for_test,
    _require_final_dependencies,
)
require_parent_bound_massive_delta = _seal_entry(
    require_parent_bound_massive_delta,
    _require_final_dependencies,
)
render_parent_bound_massive_delta_manifest_bytes = _seal_entry(
    render_parent_bound_massive_delta_manifest_bytes,
    _require_final_dependencies,
)
iter_parent_bound_massive_delta_rows = _seal_entry(
    iter_parent_bound_massive_delta_rows,
    _require_final_dependencies,
    generator=True,
)
del _seal_entry


__all__ = [
    "CENSORED_VIEW",
    "CONTRACT_ID",
    "CURRENT_VIEW",
    "CrossBoundaryGuidanceRefusal",
    "DELTA_FIRST_EVENT_DATE",
    "LITERAL_CUTOFF_CLOSE_AT",
    "LITERAL_CUTOFF_SESSION",
    "PARENT_FIRST_EVENT_DATE",
    "PARENT_LAST_EVENT_DATE",
    "ParentBoundMassiveDelta",
    "ParentBoundMassiveDeltaError",
    "build_parent_bound_massive_delta",
    "iter_parent_bound_massive_delta_rows",
    "render_parent_bound_massive_delta_manifest_bytes",
    "require_parent_bound_massive_delta",
]
