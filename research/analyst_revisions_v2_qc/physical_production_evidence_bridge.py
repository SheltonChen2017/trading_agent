"""Disk-backed C1-to-C2 production-evidence composition boundary.

The legacy production-evidence composer accepts an ``AcceptedRiskInputPair``
and therefore retains every captured Massive row.  A production capture is
too large for that object graph.  This module instead replays the authenticated
``PhysicalAcceptedRiskArchive`` and yields one ``ProductionRowEvidence`` at a
time to ``PhysicalProductionInputArchive``.  The completed bridge retains only
small parent authorities, scalar censuses, hashes, and the disk-backed C2
archive.

This is an outcome-free, pre-review candidate.  It cannot mint the separately
owner-signed production-evidence acquisition receipt and cannot launch QC.
The epoch API below is the narrow hand-off for the next scorer migration: each
epoch traverses each source arm exactly once and yields one normalized/evidence
row at a time without reconstructing either the accepted-risk pair or a legacy
``ProductionInputBatch``.
"""
from __future__ import annotations

import dataclasses
import heapq
import hashlib
import os
import sqlite3
import tempfile
import threading
import weakref
from collections.abc import Iterator, Mapping
from pathlib import Path

from research.analyst_revisions_v2 import firm_ontology as _firm_module
from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskSourceRow,
    MassiveSourceRole,
)
from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes,
    require_identifier,
    require_sha256,
    sha256_bytes,
)
from research.analyst_revisions_v2.firm_ontology import ReviewedFirmRatingOntology
from research.analyst_revisions_v2.preopen_control_acquisition import (
    PreopenControlAcquisitionReceipt,
    acquisition_truth_source_binding_records,
    require_reviewed_preopen_control_acquisition_receipt,
)
from research.analyst_revisions_v2.production_input_pipeline import (
    EvidenceSourceBinding,
    EvidenceSourceKind,
    ProductionRowEvidence,
    SECTION72_OWNER_WAIVED_FIRM_ADMISSION_MODE,
    Section72OwnerWaivedFirmSourceBinding,
    SignalArm,
)
from research.analyst_revisions_v2.production_scoring import (
    EndpointLabelEvidence,
    build_endpoint_label_evidence,
)
from research.analyst_revisions_v2_qc import (
    physical_accepted_risk_archive as _physical_c1,
)
from research.analyst_revisions_v2_qc import (
    physical_production_input_archive as _physical_c2,
)
from research.analyst_revisions_v2_qc import production_evidence_composer as _composer
from research.analyst_revisions_v2_qc import (
    preopen_control_acquisition_io as _preopen_io,
)
from research.analyst_revisions_v2_qc import (
    preopen_control_prereview_downloader as _prereview,
)
from research.analyst_revisions_v2_qc import formal_streaming_input as _streaming
from research.analyst_revisions_v2_qc.physical_accepted_risk_archive import (
    PhysicalAcceptedRiskArchive,
)
from research.analyst_revisions_v2_qc.physical_production_input_archive import (
    PhysicalNormalizedEvidenceRow,
    PhysicalProductionInputArchive,
)
from scripts import build_arv2_historical_preopen_bridge as _historical


BRIDGE_SCHEMA = "arv2-physical-production-evidence-bridge-v1"
REVIEW_CANDIDATE_SCHEMA = "arv2-physical-production-evidence-review-candidate-v1"
EPOCH_SCHEMA = "arv2-physical-production-evidence-epoch-v1"
EPOCH_RECEIPT_SCHEMA = "arv2-physical-production-evidence-epoch-receipt-v1"
MAX_COMPOSITION_TERMINAL_ROWS = 2_000_000
NORMAL_FIRM_AUTHORITY_MODE = "independently_reviewed_registry"
SECTION72_FIRM_AUTHORITY_MODE = "section72_owner_waived_deterministic_defaults"
SECTION72_OWNER_WAIVER_SCOPE = _composer.SECTION72_OWNER_WAIVER_SCOPE
_ARM_ORDER = (
    SignalArm.CURRENT_VINTAGE,
    SignalArm.CONSERVATIVE_CENSORED,
)


class PhysicalProductionEvidenceBridgeError(ValueError):
    """Physical production-evidence parents or streaming state are invalid."""


class PhysicalProductionEvidenceBridgeCapacityError(
    PhysicalProductionEvidenceBridgeError
):
    """A fixed row or disk limit was exceeded without truncation."""


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class PhysicalProductionEvidenceBridge:
    schema: str
    bridge_id: str
    bridge_sha256: str
    accepted_risk_archive: PhysicalAcceptedRiskArchive = dataclasses.field(repr=False)
    production_input_archive: PhysicalProductionInputArchive = dataclasses.field(
        repr=False
    )
    historical_bridge: object = dataclasses.field(repr=False)
    firm_ontology: (
        ReviewedFirmRatingOntology
        | _composer.OwnerWaivedAcceptedRiskFirmAdmission
    ) = dataclasses.field(repr=False)
    firm_availability: (
        _composer.ReviewedFirmOntologyAvailability
        | _composer.OwnerWaivedAcceptedRiskFirmAdmission
    ) = dataclasses.field(repr=False)
    preopen_acquisition_receipt: (
        PreopenControlAcquisitionReceipt
        | _prereview.PreopenControlPreReviewArchive
    ) = dataclasses.field(repr=False)
    terminal_archive: object = dataclasses.field(repr=False)
    firm_authority_mode: str
    owner_waived_firm_admission_id: str | None
    owner_waived_firm_admission_sha256: str | None
    firm_owner_decision_id: str | None
    firm_owner_decision_sha256: str | None
    firm_refusal_ledger_id: str | None
    firm_refusal_ledger_sha256: str | None
    owner_waiver_scope: str | None
    accepted_risk_archive_id: str
    accepted_risk_archive_sha256: str
    production_input_archive_id: str
    production_input_archive_sha256: str
    historical_bridge_id: str
    historical_bridge_sha256: str
    firm_ontology_id: str
    firm_ontology_sha256: str
    firm_availability_id: str
    firm_availability_sha256: str
    preopen_acquisition_id: str
    preopen_acquisition_sha256: str
    terminal_archive_id: str
    terminal_archive_sha256: str
    source_bindings: tuple[EvidenceSourceBinding, ...]
    source_projection_sha256: str
    row_projection_sha256: str
    composition_terminal_count: int
    composition_terminal_projection_sha256: str
    sidecar_row_count: int
    physical_terminal_count: int
    physical_accepted_count: int
    physical_refusal_count: int
    sqlite_peak_page_bytes: int
    full_accepted_risk_pair_materialized: bool
    full_production_evidence_materialized: bool
    independently_reviewed: bool
    historical_availability_claimed: bool
    owner_waiver_signature_required: bool
    production_evidence_receipt_available: bool
    provider_access: bool
    credential_access: bool
    quantconnect_access: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool

    def to_record(self) -> dict[str, object]:
        return _bridge_record(self)


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalProductionScoringRow:
    """One physical C2 row plus its exact endpoint-label evidence."""

    normalized_evidence: PhysicalNormalizedEvidenceRow
    endpoint_label: EndpointLabelEvidence

    def __post_init__(self) -> None:
        if type(self.normalized_evidence) is not PhysicalNormalizedEvidenceRow:
            raise PhysicalProductionEvidenceBridgeError(
                "physical scoring row normalized evidence changed type"
            )
        if type(self.endpoint_label) is not EndpointLabelEvidence:
            raise PhysicalProductionEvidenceBridgeError(
                "physical scoring row endpoint label changed type"
            )
        self.endpoint_label.__post_init__()
        normalized = self.normalized_evidence.normalized_row
        evidence = self.normalized_evidence.evidence
        if (
            self.endpoint_label.c2_row_sha256 != normalized.row_sha256
            or self.endpoint_label.provider_event_id != normalized.provider_event_id
            or evidence.locator != normalized.source_locator
            or evidence.firm is None
            or self.endpoint_label.raw_previous_label
            != evidence.firm.raw_previous_label
            or self.endpoint_label.raw_current_label != evidence.firm.raw_current_label
            or self.endpoint_label.source_sha256
            != normalized.source_locator.raw_row_sha256
            or self.endpoint_label.available_at != evidence.firm.available_at
        ):
            raise PhysicalProductionEvidenceBridgeError(
                "physical scoring row endpoint lineage changed"
            )


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class PhysicalProductionEvidenceEpoch:
    schema: str
    epoch_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalProductionEvidenceEpochReceipt:
    schema: str
    receipt_id: str
    receipt_sha256: str
    bridge_id: str
    bridge_sha256: str
    epoch_id: str
    arm_row_counts: tuple[tuple[str, int], ...]
    arm_row_projection_sha256s: tuple[tuple[str, str], ...]
    complete_two_arm_census: bool
    full_pair_materialized: bool
    provider_access: bool
    quantconnect_access: bool
    outcome_access: bool

    def to_record(self, *, include_identity: bool = True) -> dict[str, object]:
        record: dict[str, object] = {
            "schema": self.schema,
            "bridge_id": self.bridge_id,
            "bridge_sha256": self.bridge_sha256,
            "epoch_id": self.epoch_id,
            "arm_row_counts": [list(item) for item in self.arm_row_counts],
            "arm_row_projection_sha256s": [
                list(item) for item in self.arm_row_projection_sha256s
            ],
            "complete_two_arm_census": self.complete_two_arm_census,
            "full_pair_materialized": self.full_pair_materialized,
            "capabilities": {
                "provider_access": self.provider_access,
                "quantconnect_access": self.quantconnect_access,
                "outcome_access": self.outcome_access,
            },
        }
        if include_identity:
            record["receipt_id"] = self.receipt_id
            record["receipt_sha256"] = self.receipt_sha256
        return record


@dataclasses.dataclass(slots=True)
class _CompositionState:
    terminal_count: int = 0
    next_ordinal: int = 0


@dataclasses.dataclass(slots=True)
class _EpochState:
    bridge: PhysicalProductionEvidenceBridge
    next_arm_index: int
    active: bool
    failed: bool
    complete: bool
    arm_counts: list[tuple[str, int]]
    arm_hashes: list[tuple[str, str]]
    pid: int
    owner_thread_id: int


_BRIDGES: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalProductionEvidenceBridge],
        bytes,
        tuple[object, ...],
    ],
] = {}
_BRIDGE_EPOCH_COUNTERS: dict[int, int] = {}
_EPOCHS: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalProductionEvidenceEpoch],
        bytes,
        _EpochState,
    ],
] = {}
_LOCK = threading.RLock()
_MISSING = object()


def _forget_bridge(identity: int, reference: object) -> None:
    with _LOCK:
        current = _BRIDGES.get(identity)
        if current is not None and current[0] is reference:
            _BRIDGES.pop(identity, None)
            _BRIDGE_EPOCH_COUNTERS.pop(identity, None)


def _forget_epoch(identity: int, reference: object) -> None:
    with _LOCK:
        current = _EPOCHS.get(identity)
        if current is not None and current[0] is reference:
            _EPOCHS.pop(identity, None)


_PINNED_DEPENDENCIES = (
    (_physical_c1, "PhysicalAcceptedRiskArchive", PhysicalAcceptedRiskArchive),
    (
        _physical_c1,
        "require_physical_accepted_risk_archive",
        _physical_c1.require_physical_accepted_risk_archive,
    ),
    (
        _physical_c1,
        "iter_physical_accepted_risk_rows",
        _physical_c1.iter_physical_accepted_risk_rows,
    ),
    (_physical_c2, "PhysicalProductionInputArchive", PhysicalProductionInputArchive),
    (
        _physical_c2,
        "build_physical_production_input_archive",
        _physical_c2.build_physical_production_input_archive,
    ),
    (
        _physical_c2,
        "require_physical_production_input_archive",
        _physical_c2.require_physical_production_input_archive,
    ),
    (
        _physical_c2,
        "require_reviewable_physical_production_archive",
        _physical_c2.require_reviewable_physical_production_archive,
    ),
    (
        _physical_c2,
        "iter_physical_normalized_evidence_rows",
        _physical_c2.iter_physical_normalized_evidence_rows,
    ),
    (
        _historical,
        "require_reviewed_historical_universe_to_preopen_bridge",
        _historical.require_reviewed_historical_universe_to_preopen_bridge,
    ),
    (
        _historical,
        "iter_reviewed_historical_analyst_event_binding_shards",
        _historical.iter_reviewed_historical_analyst_event_binding_shards,
    ),
    (
        _firm_module,
        "require_registered_production_firm_ontology",
        _firm_module.require_registered_production_firm_ontology,
    ),
    (
        _composer,
        "require_reviewed_firm_ontology_availability",
        _composer.require_reviewed_firm_ontology_availability,
    ),
    (
        _composer,
        "require_physical_preopen_terminal_archive",
        _composer.require_physical_preopen_terminal_archive,
    ),
    (
        _composer,
        "require_physical_production_evidence_terminal_archive",
        _composer.require_physical_production_evidence_terminal_archive,
    ),
    (
        _composer,
        "iter_physical_preopen_terminal_sessions",
        _composer.iter_physical_preopen_terminal_sessions,
    ),
    (_composer, "_open_spool", _composer._open_spool),
    (_composer, "_sqlite_bytes", _composer._sqlite_bytes),
    (_composer, "_spool_sidecars", _composer._spool_sidecars),
    (_composer, "_spool_terminals", _composer._spool_terminals),
    (_composer, "_one_sidecar", _composer._one_sidecar),
    (_composer, "_one_terminal", _composer._one_terminal),
    (_composer, "_rating_object", _composer._rating_object),
    (_composer, "_firm_component", _composer._firm_component),
    (
        _composer,
        "require_section72_owner_waived_firm_admission",
        _composer.require_section72_owner_waived_firm_admission,
    ),
    (
        _composer,
        "_owner_waived_firm_component",
        _composer._owner_waived_firm_component,
    ),
    (_composer, "_common_component", _composer._common_component),
    (_composer, "_physical_components", _composer._physical_components),
    (_composer, "_composition_terminal", _composer._composition_terminal),
    (
        _prereview,
        "require_preopen_control_prereview_archive",
        _prereview.require_preopen_control_prereview_archive,
    ),
    (
        _prereview,
        "read_preopen_control_prereview_manifest_bytes",
        _prereview.read_preopen_control_prereview_manifest_bytes,
    ),
    (
        _prereview,
        "iter_preopen_control_prereview_output_shard_payloads",
        _prereview.iter_preopen_control_prereview_output_shard_payloads,
    ),
    (
        _preopen_io,
        "_validated_batch_major_output_payloads",
        _preopen_io._validated_batch_major_output_payloads,
    ),
    (_preopen_io, "_PhysicalShardCursor", _preopen_io._PhysicalShardCursor),
    (_preopen_io, "_strict", _preopen_io._strict),
    (
        _preopen_io.core,
        "_parse_control_sessions",
        _preopen_io.core._parse_control_sessions,
    ),
    (
        _preopen_io.core,
        "_parse_universe_sessions",
        _preopen_io.core._parse_universe_sessions,
    ),
    (_preopen_io, "_merkle", _preopen_io._merkle),
    (_streaming, "_eligible_from_record", _streaming._eligible_from_record),
    (_streaming, "_refusal_from_record", _streaming._refusal_from_record),
    (
        _streaming,
        "PhysicalTerminalSessionBlock",
        _streaming.PhysicalTerminalSessionBlock,
    ),
)
_PINNED_LOCAL_DEPENDENCIES = (
    ("canonical_json_bytes", canonical_json_bytes),
    ("require_identifier", require_identifier),
    ("require_sha256", require_sha256),
    ("sha256_bytes", sha256_bytes),
    ("EvidenceSourceBinding", EvidenceSourceBinding),
    (
        "Section72OwnerWaivedFirmSourceBinding",
        Section72OwnerWaivedFirmSourceBinding,
    ),
    (
        "SECTION72_OWNER_WAIVED_FIRM_ADMISSION_MODE",
        SECTION72_OWNER_WAIVED_FIRM_ADMISSION_MODE,
    ),
    (
        "acquisition_truth_source_binding_records",
        acquisition_truth_source_binding_records,
    ),
    (
        "require_reviewed_preopen_control_acquisition_receipt",
        require_reviewed_preopen_control_acquisition_receipt,
    ),
    ("build_endpoint_label_evidence", build_endpoint_label_evidence),
)


def _require_dependencies() -> None:
    if any(
        getattr(module, name, _MISSING) is not expected
        for module, name, expected in _PINNED_DEPENDENCIES
    ) or any(
        globals().get(name, _MISSING) is not expected
        for name, expected in _PINNED_LOCAL_DEPENDENCIES
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence dependency binding changed"
        )


def _install_sqlite_capacity(connection: sqlite3.Connection) -> None:
    try:
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        if type(page_size) is not int or page_size <= 0:
            raise PhysicalProductionEvidenceBridgeCapacityError(
                "physical composition SQLite page geometry changed"
            )
        requested = _composer.MAX_COMPOSER_SPOOL_BYTES // page_size
        observed = connection.execute(
            f"PRAGMA max_page_count={requested}"
        ).fetchone()[0]
    except sqlite3.Error as exc:
        raise PhysicalProductionEvidenceBridgeCapacityError(
            "physical composition SQLite hard capacity is unavailable"
        ) from exc
    if observed != requested:
        raise PhysicalProductionEvidenceBridgeCapacityError(
            "physical composition SQLite hard capacity was not installed"
        )


def _sqlite_is_full(error: BaseException) -> bool:
    code = getattr(error, "sqlite_errorcode", None)
    if type(code) is int and code & 0xFF == sqlite3.SQLITE_FULL:
        return True
    return str(error).casefold() == "database or disk is full"


def _truth_sources(
    receipt: PreopenControlAcquisitionReceipt,
) -> dict[str, tuple[str, str]]:
    records = acquisition_truth_source_binding_records(receipt)
    return {
        item["kind"]: (item["artifact_id"], item["artifact_sha256"])
        for item in records
    }


def _require_terminal_archive(value: object) -> object:
    if type(value) is _composer.PhysicalPreopenTerminalArchive:
        return _composer.require_physical_preopen_terminal_archive(value)
    if type(value) is _composer.PhysicalProductionEvidenceTerminalArchive:
        return _composer.require_physical_production_evidence_terminal_archive(value)
    raise PhysicalProductionEvidenceBridgeError(
        "physical production-evidence terminal archive changed type"
    )


def _reauthenticate_parents(
    *,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    historical_bridge: object,
    firm_ontology: ReviewedFirmRatingOntology,
    firm_availability: _composer.ReviewedFirmOntologyAvailability,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    terminal_archive: object,
) -> tuple[dict[str, tuple[str, str]], tuple[EvidenceSourceBinding, ...]]:
    _require_dependencies()
    try:
        c1 = _physical_c1.require_physical_accepted_risk_archive(
            accepted_risk_archive
        )
        historical = (
            _historical.require_reviewed_historical_universe_to_preopen_bridge(
                historical_bridge
            )
        )
        ontology = _firm_module.require_registered_production_firm_ontology(
            firm_ontology
        )
        availability = _composer.require_reviewed_firm_ontology_availability(
            firm_availability
        )
        preopen = require_reviewed_preopen_control_acquisition_receipt(
            preopen_acquisition_receipt
        )
        terminals = _require_terminal_archive(terminal_archive)
    except (TypeError, ValueError, AttributeError) as exc:
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence parent authority did not authenticate"
        ) from exc
    sources = _truth_sources(preopen)
    required_truth = {
        "accepted_risk_capture",
        "eligible_universe",
        "security_master",
        "firm_ontology",
        "common_event",
        "sector_classification",
        "preopen_control",
        "data_quality",
    }
    if set(sources) != required_truth:
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence truth-source census changed"
        )
    if (
        type(c1) is not PhysicalAcceptedRiskArchive
        or historical.pair_id != c1.pair_id
        or historical.pair_sha256 != c1.pair_sha256
        or historical.derived_capture_id != c1.capture_id
        or historical.derived_capture_sha256 != c1.capture_sha256
        or historical.accepted_risk_bridge_id != c1.archive_id
        or historical.accepted_risk_bridge_sha256 != c1.archive_sha256
        or preopen.input_manifest_sha256 != historical.closed_input_manifest_sha256
        or preopen.input_source_inventory_sha256
        != historical.input_shard_inventory_sha256
        or sources["accepted_risk_capture"]
        != (
            historical.accepted_risk_bridge_id,
            historical.accepted_risk_bridge_sha256,
        )
        or sources["eligible_universe"]
        != (
            historical.discovery_eligible_universe_artifact_id,
            historical.discovery_eligible_universe_artifact_sha256,
        )
        or sources["security_master"]
        != (
            historical.security_master_artifact_id,
            historical.security_master_artifact_sha256,
        )
        or sources["preopen_control"]
        != (historical.physical_candidate_id, historical.physical_candidate_sha256)
        or sources["firm_ontology"] != (ontology.ontology_id, ontology.payload_sha256)
        or availability.ontology is not ontology
        or terminals.preopen_acquisition_receipt is not preopen
        or preopen.control_sessions[0].decision_session != historical.first_session
        or preopen.control_sessions[-1].decision_session != historical.last_session
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence parents do not share exact lineage"
        )
    kind_to_truth = {
        EvidenceSourceKind.SECURITY_MASTER: "security_master",
        EvidenceSourceKind.FIRM_ONTOLOGY: "firm_ontology",
        EvidenceSourceKind.COMMON_EVENT: "common_event",
        EvidenceSourceKind.SECTOR_CLASSIFICATION: "sector_classification",
        EvidenceSourceKind.PREOPEN_CONTROL: "preopen_control",
        EvidenceSourceKind.DATA_QUALITY: "data_quality",
    }
    bindings = tuple(
        EvidenceSourceBinding(
            kind=kind,
            artifact_id=sources[kind_to_truth[kind]][0],
            artifact_sha256=sources[kind_to_truth[kind]][1],
            reviewed=True,
            point_in_time=True,
        )
        for kind in EvidenceSourceKind
    )
    _require_dependencies()
    return sources, bindings


def _owner_waived_manifest(
    archive: _prereview.PreopenControlPreReviewArchive,
) -> tuple[dict[str, object], dict[str, tuple[str, str]]]:
    archive = _prereview.require_preopen_control_prereview_archive(archive)
    payload = _prereview.read_preopen_control_prereview_manifest_bytes(archive)
    try:
        manifest = _preopen_io._strict(payload, "owner-waived preopen manifest")
    except (TypeError, ValueError) as exc:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen manifest did not authenticate"
        ) from exc
    bindings = manifest.get("truth_source_bindings")
    if type(bindings) is not list:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen truth-source bindings changed type"
        )
    sources: dict[str, tuple[str, str]] = {}
    for item in bindings:
        if (
            type(item) is not dict
            or set(item) != {"kind", "artifact_id", "artifact_sha256"}
            or type(item.get("kind")) is not str
            or type(item.get("artifact_id")) is not str
            or type(item.get("artifact_sha256")) is not str
            or item["kind"] in sources
        ):
            raise PhysicalProductionEvidenceBridgeError(
                "owner-waived preopen truth-source binding changed"
            )
        try:
            require_identifier(item["artifact_id"], "preopen truth artifact")
            require_sha256(item["artifact_sha256"], "preopen truth artifact")
        except (TypeError, ValueError) as exc:
            raise PhysicalProductionEvidenceBridgeError(
                "owner-waived preopen truth-source binding changed"
            ) from exc
        sources[item["kind"]] = (
            item["artifact_id"], item["artifact_sha256"]
        )
    required_truth = {
        "accepted_risk_capture",
        "eligible_universe",
        "security_master",
        "firm_ontology",
        "common_event",
        "sector_classification",
        "preopen_control",
        "data_quality",
    }
    if set(sources) != required_truth:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen truth-source census changed"
        )
    _prereview.require_preopen_control_prereview_archive(archive)
    return manifest, sources


def _reauthenticate_owner_waived_parents(
    *,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    historical_bridge: object,
    firm_admission: _composer.OwnerWaivedAcceptedRiskFirmAdmission,
    preopen_prereview_archive: _prereview.PreopenControlPreReviewArchive,
) -> tuple[dict[str, tuple[str, str]], tuple[EvidenceSourceBinding, ...]]:
    _require_dependencies()
    if (
        type(firm_admission)
        is not _composer.OwnerWaivedAcceptedRiskFirmAdmission
        or type(preopen_prereview_archive)
        is not _prereview.PreopenControlPreReviewArchive
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived physical production parents changed exact type"
        )
    try:
        c1 = _physical_c1.require_physical_accepted_risk_archive(
            accepted_risk_archive
        )
        historical = (
            _historical.require_reviewed_historical_universe_to_preopen_bridge(
                historical_bridge
            )
        )
        admission = _composer.require_section72_owner_waived_firm_admission(
            firm_admission
        )
        prereview = _prereview.require_preopen_control_prereview_archive(
            preopen_prereview_archive
        )
        manifest, sources = _owner_waived_manifest(prereview)
    except (TypeError, ValueError, AttributeError) as exc:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived physical production parent did not authenticate"
        ) from exc
    packet = admission.review_packet
    if (
        admission.owner_waiver_scope != _composer.SECTION72_OWNER_WAIVER_SCOPE
        or admission.independently_reviewed is not False
        or admission.historical_availability_claimed is not False
        or admission.normal_registry_populated is not False
        or admission.owner_signature_required_downstream is not True
        or prereview.review_disposition != "NOT_PERFORMED_OWNER_WAIVED"
        or prereview.independent_review_complete is not False
        or prereview.owner_review_waiver_scope
        != _composer.SECTION72_OWNER_WAIVER_SCOPE
        or prereview.post_first_formal_backtest_independent_review_required
        is not True
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived physical production policy disposition changed"
        )
    if (
        type(c1) is not PhysicalAcceptedRiskArchive
        or packet.accepted_risk_archive_id != c1.archive_id
        or packet.accepted_risk_archive_sha256 != c1.archive_sha256
        or historical.pair_id != c1.pair_id
        or historical.pair_sha256 != c1.pair_sha256
        or historical.derived_capture_id != c1.capture_id
        or historical.derived_capture_sha256 != c1.capture_sha256
        or historical.accepted_risk_bridge_id != c1.archive_id
        or historical.accepted_risk_bridge_sha256 != c1.archive_sha256
        or manifest["input_manifest"]["content_sha256"]
        != historical.closed_input_manifest_sha256
        or manifest.get("input_source_inventory_sha256")
        != historical.input_shard_inventory_sha256
        or sources["accepted_risk_capture"]
        != (
            historical.accepted_risk_bridge_id,
            historical.accepted_risk_bridge_sha256,
        )
        or sources["eligible_universe"]
        != (
            historical.discovery_eligible_universe_artifact_id,
            historical.discovery_eligible_universe_artifact_sha256,
        )
        or sources["security_master"]
        != (
            historical.security_master_artifact_id,
            historical.security_master_artifact_sha256,
        )
        or sources["preopen_control"]
        != (historical.physical_candidate_id, historical.physical_candidate_sha256)
        or sources["firm_ontology"][1]
        != historical.firm_review_candidate_sha256
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived physical production parents do not share exact lineage"
        )
    operational_sources = dict(sources)
    operational_sources["firm_ontology"] = (
        admission.admission_id, admission.admission_sha256
    )
    kind_to_truth = {
        EvidenceSourceKind.SECURITY_MASTER: "security_master",
        EvidenceSourceKind.FIRM_ONTOLOGY: "firm_ontology",
        EvidenceSourceKind.COMMON_EVENT: "common_event",
        EvidenceSourceKind.SECTOR_CLASSIFICATION: "sector_classification",
        EvidenceSourceKind.PREOPEN_CONTROL: "preopen_control",
        EvidenceSourceKind.DATA_QUALITY: "data_quality",
    }
    bindings = tuple(
        Section72OwnerWaivedFirmSourceBinding(
            kind=kind,
            artifact_id=operational_sources[kind_to_truth[kind]][0],
            artifact_sha256=operational_sources[kind_to_truth[kind]][1],
            reviewed=False,
            point_in_time=False,
            admission_mode=SECTION72_OWNER_WAIVED_FIRM_ADMISSION_MODE,
            owner_waiver_scope=SECTION72_OWNER_WAIVER_SCOPE,
            independently_reviewed=False,
            historical_availability_claimed=False,
        )
        if kind is EvidenceSourceKind.FIRM_ONTOLOGY
        else EvidenceSourceBinding(
            kind=kind,
            artifact_id=operational_sources[kind_to_truth[kind]][0],
            artifact_sha256=operational_sources[kind_to_truth[kind]][1],
            reviewed=True,
            point_in_time=True,
        )
        for kind in EvidenceSourceKind
    )
    _physical_c1.require_physical_accepted_risk_archive(c1)
    _composer.require_section72_owner_waived_firm_admission(admission)
    _prereview.require_preopen_control_prereview_archive(prereview)
    _require_dependencies()
    return operational_sources, bindings


def _spool_owner_waived_prereview_terminals(
    connection: sqlite3.Connection,
    archive: _prereview.PreopenControlPreReviewArchive,
) -> tuple[tuple[int, int, int], int]:
    """Revalidate inert physical shards and spool only their terminal values."""

    archive = _prereview.require_preopen_control_prereview_archive(archive)
    manifest, _sources = _owner_waived_manifest(archive)
    try:
        projection, totals = _preopen_io._validated_batch_major_output_payloads(
            manifest,
            _prereview.iter_preopen_control_prereview_output_shard_payloads(
                archive
            ),
        )
    except (TypeError, ValueError) as exc:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal shards did not authenticate"
        ) from exc
    expected_totals = (
        archive.terminal_count, archive.accepted_count, archive.refusal_count
    )
    if (
        projection != archive.output_shard_payload_projection_sha256
        or (
            totals.get("terminal_count"),
            totals.get("accepted_count"),
            totals.get("refusal_count"),
        )
        != expected_totals
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal projection changed"
        )
    descriptors = manifest.get("output_shards")
    if type(descriptors) is not list:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen output-shard descriptors changed type"
        )
    total = accepted_count = refusal_count = 0
    peak = _composer._sqlite_bytes(connection)
    connection.execute("BEGIN")
    try:
        payloads = _prereview.iter_preopen_control_prereview_output_shard_payloads(
            archive
        )
        for descriptor, payload in zip(descriptors, payloads, strict=True):
            if type(descriptor) is not dict:
                raise PhysicalProductionEvidenceBridgeError(
                    "owner-waived preopen output-shard descriptor changed type"
                )
            cursor = _preopen_io._PhysicalShardCursor(descriptor, payload)
            while True:
                row = cursor.next()
                if row is None:
                    break
                disposition = row["disposition"]
                record = (
                    row["eligible_security_session"]
                    if disposition == "accepted"
                    else row["census_refusal"]
                )
                if type(record) is not dict:
                    raise PhysicalProductionEvidenceBridgeError(
                        "owner-waived preopen terminal lost its value"
                    )
                connection.execute(
                    "INSERT INTO terminals(decision_session, security_id, "
                    "disposition, record) VALUES (?, ?, ?, ?)",
                    (
                        row["decision_session"], row["security_id"], disposition,
                        sqlite3.Binary(canonical_json_bytes(record)),
                    ),
                )
                total += 1
                accepted_count += int(disposition == "accepted")
                refusal_count += int(disposition == "named_refusal")
                if total > MAX_COMPOSITION_TERMINAL_ROWS:
                    raise PhysicalProductionEvidenceBridgeCapacityError(
                        "owner-waived preopen terminal census exceeded capacity"
                    )
                if total % 1024 == 0:
                    peak = max(peak, _composer._sqlite_bytes(connection))
        connection.execute("COMMIT")
    except ValueError as exc:
        connection.execute("ROLLBACK")
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen shard payload census changed"
        ) from exc
    except sqlite3.IntegrityError as exc:
        connection.execute("ROLLBACK")
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal security/session repeats"
        ) from exc
    except Exception:
        connection.execute("ROLLBACK")
        raise
    observed = (total, accepted_count, refusal_count)
    if observed != expected_totals:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal census changed"
        )
    _prereview.require_preopen_control_prereview_archive(archive)
    return observed, max(peak, _composer._sqlite_bytes(connection))


def _insert_composition_terminal(
    connection: sqlite3.Connection,
    state: _CompositionState,
    terminal: _composer.ProductionEvidenceCompositionTerminal,
) -> None:
    if state.terminal_count >= MAX_COMPOSITION_TERMINAL_ROWS:
        raise PhysicalProductionEvidenceBridgeCapacityError(
            "physical composition-terminal census exceeded fixed capacity"
        )
    payload = canonical_json_bytes(terminal.to_record())
    try:
        connection.execute(
            "INSERT INTO physical_composition(ordinal, payload) VALUES (?, ?)",
            (state.next_ordinal, sqlite3.Binary(payload)),
        )
    except sqlite3.Error as exc:
        if _sqlite_is_full(exc):
            raise PhysicalProductionEvidenceBridgeCapacityError(
                "physical composition SQLite spool reached its hard capacity"
            ) from exc
        raise PhysicalProductionEvidenceBridgeError(
            "physical composition terminal could not be spooled"
        ) from exc
    state.next_ordinal += 1
    state.terminal_count += 1


def _iter_composed_evidence_rows(
    *,
    source_rows: Iterator[AcceptedRiskSourceRow],
    connection: sqlite3.Connection,
    state: _CompositionState,
    truth_sources: Mapping[str, tuple[str, str]],
    firm_ontology: ReviewedFirmRatingOntology | None = None,
    firm_availability: _composer.ReviewedFirmOntologyAvailability | None = None,
    firm_admission: _composer.OwnerWaivedAcceptedRiskFirmAdmission | None = None,
) -> Iterator[ProductionRowEvidence]:
    normal_firm_path = firm_admission is None
    if normal_firm_path is not (
        firm_ontology is not None and firm_availability is not None
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "physical firm authority mode is overlapping or incomplete"
        )
    previous: tuple[int, int, int] | None = None
    for source in source_rows:
        _require_dependencies()
        if type(source) is not AcceptedRiskSourceRow:
            raise PhysicalProductionEvidenceBridgeError(
                "physical C1 evidence traversal yielded the wrong row type"
            )
        source.__post_init__()
        if previous is not None and source.locator.sort_key <= previous:
            raise PhysicalProductionEvidenceBridgeError(
                "physical C1 evidence traversal order changed"
            )
        previous = source.locator.sort_key
        if (
            source.locator.source_role is not MassiveSourceRole.ANALYST_RATINGS
            or not source.current_view.included
        ):
            continue
        locator_sha = sha256_bytes(canonical_json_bytes(source.locator.to_record()))
        sidecar, sidecar_status = _composer._one_sidecar(connection, locator_sha)
        dispositions = {
            "security": "missing",
            "firm": "missing",
            "common_event": "missing",
            "sector": "missing",
            "control": "missing",
            "q_data": "missing",
        }
        upstream_reason: str | None = None
        if sidecar_status == "ambiguous":
            dispositions["security"] = "ambiguous"
            upstream_reason = "analyst_event_binding_ambiguous"
        elif sidecar is None:
            upstream_reason = "analyst_event_binding_missing"
        elif sidecar["binding_disposition"] == "named_refusal":
            for name in ("security", "sector", "control", "q_data"):
                dispositions[name] = "upstream_named_refusal"
            upstream_reason = sidecar["binding_reason"]

        raw = _composer._rating_object(source)
        if normal_firm_path:
            firm, firm_status = _composer._firm_component(
                source=source,
                raw=raw,
                ontology=firm_ontology,
                availability=firm_availability,
            )
        else:
            firm, firm_status = _composer._owner_waived_firm_component(
                source=source,
                raw=raw,
                admission=firm_admission,
            )
        dispositions["firm"] = firm_status
        common, common_status = _composer._common_component(
            source=source,
            sidecar=sidecar,
            truth_sources=truth_sources,
        )
        dispositions["common_event"] = common_status
        security = sector = control = quality = None
        if sidecar is not None and sidecar["binding_disposition"] == "accepted":
            terminal_disposition, terminal = _composer._one_terminal(
                connection,
                sidecar["decision_session"],
                sidecar["physical_security_id"],
            )
            if terminal_disposition is None:
                for name in ("security", "sector", "control", "q_data"):
                    dispositions[name] = "physical_terminal_missing"
                upstream_reason = "same_key_physical_terminal_missing"
            elif terminal_disposition == "named_refusal":
                for name in ("security", "sector", "control", "q_data"):
                    dispositions[name] = "physical_terminal_refused"
                if terminal is None:
                    raise PhysicalProductionEvidenceBridgeError(
                        "physical named-refusal terminal payload is missing"
                    )
                upstream_reason = str(terminal.get("reason"))
            elif terminal_disposition == "accepted" and terminal is not None:
                try:
                    security, sector, control, quality = _composer._physical_components(
                        source=source,
                        sidecar=sidecar,
                        terminal=terminal,
                        truth_sources=truth_sources,
                    )
                except (TypeError, ValueError, AttributeError, KeyError) as exc:
                    raise PhysicalProductionEvidenceBridgeError(
                        "physical production-evidence parents contradict one row"
                    ) from exc
                for name in ("security", "sector", "control", "q_data"):
                    dispositions[name] = "accepted"
            else:
                raise PhysicalProductionEvidenceBridgeError(
                    "physical terminal disposition changed"
                )
        evidence = ProductionRowEvidence(
            locator=source.locator,
            security=security,
            firm=firm,
            common_event=common,
            sector=sector,
            control=control,
            q_data=quality,
        )
        terminal = _composer._composition_terminal(
            locator_sha256=locator_sha,
            dispositions=dispositions,
            upstream_reason=upstream_reason,
        )
        _insert_composition_terminal(connection, state, terminal)
        yield evidence
    _require_dependencies()


def _composition_projection(connection: sqlite3.Connection, count: int) -> str:
    hasher = hashlib.sha256()
    hasher.update(b"[")
    observed = 0
    try:
        cursor = connection.execute(
            "SELECT ordinal, payload FROM physical_composition ORDER BY ordinal"
        )
        for ordinal, payload in cursor:
            if type(ordinal) is not int or ordinal != observed:
                raise PhysicalProductionEvidenceBridgeError(
                    "physical composition-terminal order changed"
                )
            raw = bytes(payload)
            if not raw.endswith(b"\n"):
                raise PhysicalProductionEvidenceBridgeError(
                    "physical composition-terminal encoding changed"
                )
            if observed:
                hasher.update(b",")
            hasher.update(raw[:-1])
            observed += 1
    except sqlite3.Error as exc:
        raise PhysicalProductionEvidenceBridgeError(
            "physical composition-terminal projection could not be read"
        ) from exc
    hasher.update(b"]\n")
    if observed != count:
        raise PhysicalProductionEvidenceBridgeError(
            "physical composition-terminal census changed"
        )
    return hasher.hexdigest()


def _bridge_record(value: PhysicalProductionEvidenceBridge) -> dict[str, object]:
    return {
        "schema": value.schema,
        "firm_authority_mode": value.firm_authority_mode,
        "owner_waived_firm_admission_id": (
            value.owner_waived_firm_admission_id
        ),
        "owner_waived_firm_admission_sha256": (
            value.owner_waived_firm_admission_sha256
        ),
        "firm_owner_decision_id": value.firm_owner_decision_id,
        "firm_owner_decision_sha256": value.firm_owner_decision_sha256,
        "firm_refusal_ledger_id": value.firm_refusal_ledger_id,
        "firm_refusal_ledger_sha256": value.firm_refusal_ledger_sha256,
        "owner_waiver_scope": value.owner_waiver_scope,
        "accepted_risk_archive_id": value.accepted_risk_archive_id,
        "accepted_risk_archive_sha256": value.accepted_risk_archive_sha256,
        "production_input_archive_id": value.production_input_archive_id,
        "production_input_archive_sha256": value.production_input_archive_sha256,
        "historical_bridge_id": value.historical_bridge_id,
        "historical_bridge_sha256": value.historical_bridge_sha256,
        "firm_ontology_id": value.firm_ontology_id,
        "firm_ontology_sha256": value.firm_ontology_sha256,
        "firm_availability_id": value.firm_availability_id,
        "firm_availability_sha256": value.firm_availability_sha256,
        "preopen_acquisition_id": value.preopen_acquisition_id,
        "preopen_acquisition_sha256": value.preopen_acquisition_sha256,
        "terminal_archive_id": value.terminal_archive_id,
        "terminal_archive_sha256": value.terminal_archive_sha256,
        "source_projection_sha256": value.source_projection_sha256,
        "row_projection_sha256": value.row_projection_sha256,
        "composition_terminal_count": value.composition_terminal_count,
        "composition_terminal_projection_sha256": (
            value.composition_terminal_projection_sha256
        ),
        "sidecar_row_count": value.sidecar_row_count,
        "physical_terminal_count": value.physical_terminal_count,
        "physical_accepted_count": value.physical_accepted_count,
        "physical_refusal_count": value.physical_refusal_count,
        "sqlite_peak_page_bytes": value.sqlite_peak_page_bytes,
        "full_accepted_risk_pair_materialized": False,
        "full_production_evidence_materialized": False,
        "independently_reviewed": False,
        "historical_availability_claimed": (
            value.historical_availability_claimed
        ),
        "owner_waiver_signature_required": (
            value.owner_waiver_signature_required
        ),
        "production_evidence_receipt_available": False,
        "capabilities": {
            "provider_access": False,
            "credential_access": False,
            "quantconnect_access": False,
            "outcome_access": False,
            "result_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


def _bridge_topology(value: PhysicalProductionEvidenceBridge) -> tuple[object, ...]:
    return (
        id(value.accepted_risk_archive),
        id(value.production_input_archive),
        id(value.historical_bridge),
        id(value.firm_ontology),
        id(value.firm_availability),
        id(value.preopen_acquisition_receipt),
        id(value.terminal_archive),
        id(value.source_bindings),
        tuple(id(item) for item in value.source_bindings),
    )


def _validate_bridge_surface(value: PhysicalProductionEvidenceBridge) -> None:
    if type(value.accepted_risk_archive) is not PhysicalAcceptedRiskArchive:
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge C1 type changed"
        )
    if type(value.production_input_archive) is not PhysicalProductionInputArchive:
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge C2 type changed"
        )
    allowed_source_types = (
        EvidenceSourceBinding,
        Section72OwnerWaivedFirmSourceBinding,
    )
    if type(value.source_bindings) is not tuple or any(
        type(item) not in allowed_source_types for item in value.source_bindings
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge source topology changed"
        )
    waived_sources = tuple(
        item for item in value.source_bindings
        if type(item) is Section72OwnerWaivedFirmSourceBinding
    )
    if value.firm_authority_mode == SECTION72_FIRM_AUTHORITY_MODE:
        if (
            len(waived_sources) != 1
            or waived_sources[0].kind is not EvidenceSourceKind.FIRM_ONTOLOGY
        ):
            raise PhysicalProductionEvidenceBridgeError(
                "owner-waived bridge firm-source binding changed"
            )
    elif waived_sources:
        raise PhysicalProductionEvidenceBridgeError(
            "normal bridge acquired an owner-waived firm source"
        )
    scalar_names = (
        "schema",
        "firm_authority_mode",
        "bridge_id",
        "bridge_sha256",
        "accepted_risk_archive_id",
        "accepted_risk_archive_sha256",
        "production_input_archive_id",
        "production_input_archive_sha256",
        "historical_bridge_id",
        "historical_bridge_sha256",
        "firm_ontology_id",
        "firm_ontology_sha256",
        "firm_availability_id",
        "firm_availability_sha256",
        "preopen_acquisition_id",
        "preopen_acquisition_sha256",
        "terminal_archive_id",
        "terminal_archive_sha256",
        "source_projection_sha256",
        "row_projection_sha256",
        "composition_terminal_projection_sha256",
    )
    if any(type(getattr(value, name)) is not str for name in scalar_names):
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge scalar type changed"
        )
    optional_scalar_names = (
        "owner_waived_firm_admission_id",
        "owner_waived_firm_admission_sha256",
        "firm_owner_decision_id",
        "firm_owner_decision_sha256",
        "firm_refusal_ledger_id",
        "firm_refusal_ledger_sha256",
        "owner_waiver_scope",
    )
    if any(
        getattr(value, name) is not None
        and type(getattr(value, name)) is not str
        for name in optional_scalar_names
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge waiver scalar type changed"
        )
    count_names = (
        "composition_terminal_count",
        "sidecar_row_count",
        "physical_terminal_count",
        "physical_accepted_count",
        "physical_refusal_count",
        "sqlite_peak_page_bytes",
    )
    if any(
        type(getattr(value, name)) is not int or getattr(value, name) < 0
        for name in count_names
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge count type changed"
        )
    flag_names = (
        "full_accepted_risk_pair_materialized",
        "full_production_evidence_materialized",
        "independently_reviewed",
        "historical_availability_claimed",
        "owner_waiver_signature_required",
        "production_evidence_receipt_available",
        "provider_access",
        "credential_access",
        "quantconnect_access",
        "outcome_access",
        "result_access",
        "deployment",
        "orders",
        "trading",
    )
    if any(type(getattr(value, name)) is not bool for name in flag_names):
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge flag type changed"
        )


def _mint_bridge(
    *,
    c1: PhysicalAcceptedRiskArchive,
    c2: PhysicalProductionInputArchive,
    historical_bridge: object,
    firm_ontology: object,
    firm_availability: object,
    preopen: object,
    terminal_archive: object,
    firm_authority_mode: str,
    source_bindings: tuple[EvidenceSourceBinding, ...],
    composition_count: int,
    composition_projection: str,
    sidecar_count: int,
    physical_counts: tuple[int, int, int],
    peak: int,
) -> PhysicalProductionEvidenceBridge:
    normal = firm_authority_mode == NORMAL_FIRM_AUTHORITY_MODE
    waived = firm_authority_mode == SECTION72_FIRM_AUTHORITY_MODE
    if normal is waived or not (normal or waived):
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence firm authority mode changed"
        )
    admission = None if normal else firm_ontology
    if waived and (
        type(admission) is not _composer.OwnerWaivedAcceptedRiskFirmAdmission
        or firm_availability is not admission
        or preopen is not terminal_archive
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived bridge parent projection changed"
        )
    value = object.__new__(PhysicalProductionEvidenceBridge)
    fields: dict[str, object] = {
        "schema": BRIDGE_SCHEMA,
        "bridge_id": "",
        "bridge_sha256": "",
        "accepted_risk_archive": c1,
        "production_input_archive": c2,
        "historical_bridge": historical_bridge,
        "firm_ontology": firm_ontology,
        "firm_availability": firm_availability,
        "preopen_acquisition_receipt": preopen,
        "terminal_archive": terminal_archive,
        "firm_authority_mode": firm_authority_mode,
        "owner_waived_firm_admission_id": (
            None if normal else admission.admission_id
        ),
        "owner_waived_firm_admission_sha256": (
            None if normal else admission.admission_sha256
        ),
        "firm_owner_decision_id": (
            None if normal else admission.owner_decision_id
        ),
        "firm_owner_decision_sha256": (
            None if normal else admission.owner_decision_sha256
        ),
        "firm_refusal_ledger_id": (
            None if normal else admission.refusal_ledger_id
        ),
        "firm_refusal_ledger_sha256": (
            None if normal else admission.refusal_ledger_sha256
        ),
        "owner_waiver_scope": (
            None if normal else admission.owner_waiver_scope
        ),
        "accepted_risk_archive_id": c1.archive_id,
        "accepted_risk_archive_sha256": c1.archive_sha256,
        "production_input_archive_id": c2.archive_id,
        "production_input_archive_sha256": c2.archive_sha256,
        "historical_bridge_id": historical_bridge.bridge_id,
        "historical_bridge_sha256": historical_bridge.bridge_sha256,
        "firm_ontology_id": (
            firm_ontology.ontology_id if normal else admission.admission_id
        ),
        "firm_ontology_sha256": (
            firm_ontology.payload_sha256 if normal else admission.admission_sha256
        ),
        "firm_availability_id": (
            firm_availability.artifact_id
            if normal else admission.owner_decision_id
        ),
        "firm_availability_sha256": (
            firm_availability.artifact_sha256
            if normal else admission.owner_decision_sha256
        ),
        "preopen_acquisition_id": (
            preopen.artifact_id if normal else preopen.capture_id
        ),
        "preopen_acquisition_sha256": (
            preopen.artifact_sha256 if normal else preopen.capture_sha256
        ),
        "terminal_archive_id": (
            terminal_archive.archive_id if normal else terminal_archive.capture_id
        ),
        "terminal_archive_sha256": (
            terminal_archive.archive_sha256
            if normal else terminal_archive.capture_sha256
        ),
        "source_bindings": source_bindings,
        "source_projection_sha256": c2.source_projection_sha256,
        "row_projection_sha256": c2.row_projection_sha256,
        "composition_terminal_count": composition_count,
        "composition_terminal_projection_sha256": composition_projection,
        "sidecar_row_count": sidecar_count,
        "physical_terminal_count": physical_counts[0],
        "physical_accepted_count": physical_counts[1],
        "physical_refusal_count": physical_counts[2],
        "sqlite_peak_page_bytes": peak,
        "full_accepted_risk_pair_materialized": False,
        "full_production_evidence_materialized": False,
        "independently_reviewed": False,
        "historical_availability_claimed": normal,
        "owner_waiver_signature_required": waived,
        "production_evidence_receipt_available": False,
        "provider_access": False,
        "credential_access": False,
        "quantconnect_access": False,
        "outcome_access": False,
        "result_access": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    if set(fields) != {item.name for item in dataclasses.fields(value)}:
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge field inventory changed"
        )
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    digest = sha256_bytes(canonical_json_bytes(_bridge_record(value)))
    object.__setattr__(value, "bridge_sha256", digest)
    object.__setattr__(
        value, "bridge_id", f"arv2-physical-production-evidence-{digest[:24]}"
    )
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_bridge(key, ref)
    )
    with _LOCK:
        _BRIDGES[identity] = (
            reference,
            canonical_json_bytes(_bridge_record(value)),
            _bridge_topology(value),
        )
    return require_physical_production_evidence_bridge(value)


def _build_bridge(
    *,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    historical_bridge: object,
    firm_ontology: ReviewedFirmRatingOntology,
    firm_availability: _composer.ReviewedFirmOntologyAvailability,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    terminal_archive: object,
    output_root: Path,
    fixture_only: bool,
) -> PhysicalProductionEvidenceBridge:
    truth_sources, source_bindings = _reauthenticate_parents(
        accepted_risk_archive=accepted_risk_archive,
        historical_bridge=historical_bridge,
        firm_ontology=firm_ontology,
        firm_availability=firm_availability,
        preopen_acquisition_receipt=preopen_acquisition_receipt,
        terminal_archive=terminal_archive,
    )
    c1 = _physical_c1.require_physical_accepted_risk_archive(
        accepted_risk_archive
    )
    with tempfile.TemporaryDirectory(
        prefix="arv2-physical-production-evidence-"
    ) as directory_text:
        directory = Path(directory_text)
        os.chmod(directory, 0o700)
        connection, _spool_path = _composer._open_spool(directory)
        state = _CompositionState()
        try:
            _install_sqlite_capacity(connection)
            connection.execute(
                "CREATE TABLE physical_composition("
                "ordinal INTEGER PRIMARY KEY, payload BLOB NOT NULL)"
            )
            sidecar_count, sidecar_peak = _composer._spool_sidecars(
                connection, historical_bridge
            )
            physical_counts, terminal_peak = _composer._spool_terminals(
                connection, terminal_archive
            )
            peak = max(
                sidecar_peak,
                terminal_peak,
                _composer._sqlite_bytes(connection),
            )
            rows = _iter_composed_evidence_rows(
                source_rows=_physical_c1.iter_physical_accepted_risk_rows(c1),
                connection=connection,
                state=state,
                truth_sources=truth_sources,
                firm_ontology=firm_ontology,
                firm_availability=firm_availability,
            )
            if fixture_only:
                fixture_builder = getattr(
                    _physical_c2,
                    "_build_test_fixture_"
                    "physical_production_input_archive_from_physical_c1",
                )
                c2 = fixture_builder(
                    c1,
                    source_bindings=source_bindings,
                    row_evidence=rows,
                    output_root=output_root,
                )
            else:
                c2 = _physical_c2.build_physical_production_input_archive(
                    c1,
                    source_bindings=source_bindings,
                    row_evidence=rows,
                    output_root=output_root,
                )
            projection = _composition_projection(connection, state.terminal_count)
            peak = max(peak, _composer._sqlite_bytes(connection))
        except sqlite3.Error as exc:
            if _sqlite_is_full(exc):
                raise PhysicalProductionEvidenceBridgeCapacityError(
                    "physical composition SQLite spool reached its hard capacity"
                ) from exc
            raise PhysicalProductionEvidenceBridgeError(
                "physical composition SQLite operation failed"
            ) from exc
        finally:
            connection.close()
    if c2.evidence_row_count != state.terminal_count:
        raise PhysicalProductionEvidenceBridgeError(
            "physical C2 evidence census differs from composition terminals"
        )
    if c2.source_bindings != source_bindings:
        raise PhysicalProductionEvidenceBridgeError(
            "physical C2 source bindings differ from composition authority"
        )
    _reauthenticate_parents(
        accepted_risk_archive=c1,
        historical_bridge=historical_bridge,
        firm_ontology=firm_ontology,
        firm_availability=firm_availability,
        preopen_acquisition_receipt=preopen_acquisition_receipt,
        terminal_archive=terminal_archive,
    )
    _physical_c2.require_physical_production_input_archive(c2)
    return _mint_bridge(
        c1=c1,
        c2=c2,
        historical_bridge=historical_bridge,
        firm_ontology=firm_ontology,
        firm_availability=firm_availability,
        preopen=preopen_acquisition_receipt,
        terminal_archive=terminal_archive,
        firm_authority_mode=NORMAL_FIRM_AUTHORITY_MODE,
        source_bindings=source_bindings,
        composition_count=state.terminal_count,
        composition_projection=projection,
        sidecar_count=sidecar_count,
        physical_counts=physical_counts,
        peak=peak,
    )


def _build_section72_owner_waived_bridge(
    *,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    historical_bridge: object,
    firm_admission: _composer.OwnerWaivedAcceptedRiskFirmAdmission,
    preopen_prereview_archive: _prereview.PreopenControlPreReviewArchive,
    output_root: Path,
    fixture_only: bool,
) -> PhysicalProductionEvidenceBridge:
    truth_sources, source_bindings = _reauthenticate_owner_waived_parents(
        accepted_risk_archive=accepted_risk_archive,
        historical_bridge=historical_bridge,
        firm_admission=firm_admission,
        preopen_prereview_archive=preopen_prereview_archive,
    )
    c1 = _physical_c1.require_physical_accepted_risk_archive(
        accepted_risk_archive
    )
    with tempfile.TemporaryDirectory(
        prefix="arv2-owner-waived-production-evidence-"
    ) as directory_text:
        directory = Path(directory_text)
        os.chmod(directory, 0o700)
        connection, _spool_path = _composer._open_spool(directory)
        state = _CompositionState()
        try:
            _install_sqlite_capacity(connection)
            connection.execute(
                "CREATE TABLE physical_composition("
                "ordinal INTEGER PRIMARY KEY, payload BLOB NOT NULL)"
            )
            sidecar_count, sidecar_peak = _composer._spool_sidecars(
                connection, historical_bridge
            )
            physical_counts, terminal_peak = (
                _spool_owner_waived_prereview_terminals(
                    connection, preopen_prereview_archive
                )
            )
            peak = max(
                sidecar_peak,
                terminal_peak,
                _composer._sqlite_bytes(connection),
            )
            rows = _iter_composed_evidence_rows(
                source_rows=_physical_c1.iter_physical_accepted_risk_rows(c1),
                connection=connection,
                state=state,
                truth_sources=truth_sources,
                firm_admission=firm_admission,
            )
            if fixture_only:
                fixture_builder = getattr(
                    _physical_c2,
                    "_build_test_fixture_"
                    "physical_production_input_archive_from_physical_c1",
                )
                c2 = fixture_builder(
                    c1,
                    source_bindings=source_bindings,
                    row_evidence=rows,
                    output_root=output_root,
                )
            else:
                c2 = _physical_c2.build_physical_production_input_archive(
                    c1,
                    source_bindings=source_bindings,
                    row_evidence=rows,
                    output_root=output_root,
                )
            projection = _composition_projection(
                connection, state.terminal_count
            )
            peak = max(peak, _composer._sqlite_bytes(connection))
        except sqlite3.Error as exc:
            if _sqlite_is_full(exc):
                raise PhysicalProductionEvidenceBridgeCapacityError(
                    "owner-waived physical composition SQLite spool reached capacity"
                ) from exc
            raise PhysicalProductionEvidenceBridgeError(
                "owner-waived physical composition SQLite operation failed"
            ) from exc
        finally:
            connection.close()
    if c2.evidence_row_count != state.terminal_count:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived physical C2 census differs from composition terminals"
        )
    if c2.source_bindings != source_bindings:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived physical C2 source bindings differ from admission"
        )
    _reauthenticate_owner_waived_parents(
        accepted_risk_archive=c1,
        historical_bridge=historical_bridge,
        firm_admission=firm_admission,
        preopen_prereview_archive=preopen_prereview_archive,
    )
    _physical_c2.require_physical_production_input_archive(c2)
    return _mint_bridge(
        c1=c1,
        c2=c2,
        historical_bridge=historical_bridge,
        firm_ontology=firm_admission,
        firm_availability=firm_admission,
        preopen=preopen_prereview_archive,
        terminal_archive=preopen_prereview_archive,
        firm_authority_mode=SECTION72_FIRM_AUTHORITY_MODE,
        source_bindings=source_bindings,
        composition_count=state.terminal_count,
        composition_projection=projection,
        sidecar_count=sidecar_count,
        physical_counts=physical_counts,
        peak=peak,
    )


def build_section72_owner_waived_physical_production_evidence_bridge(
    *,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    historical_bridge: object,
    firm_admission: _composer.OwnerWaivedAcceptedRiskFirmAdmission,
    preopen_prereview_archive: _prereview.PreopenControlPreReviewArchive,
    output_root: Path,
) -> PhysicalProductionEvidenceBridge:
    """Build physical C2 under the exact, bounded section-72 owner waiver."""

    return _build_section72_owner_waived_bridge(
        accepted_risk_archive=accepted_risk_archive,
        historical_bridge=historical_bridge,
        firm_admission=firm_admission,
        preopen_prereview_archive=preopen_prereview_archive,
        output_root=output_root,
        fixture_only=False,
    )


def _build_test_fixture_section72_owner_waived_bridge(
    **kwargs: object,
) -> PhysicalProductionEvidenceBridge:
    return _build_section72_owner_waived_bridge(
        **kwargs, fixture_only=True  # type: ignore[arg-type]
    )


def build_physical_production_evidence_bridge(
    *,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    historical_bridge: object,
    firm_ontology: ReviewedFirmRatingOntology,
    firm_availability: _composer.ReviewedFirmOntologyAvailability,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    terminal_archive: object,
    output_root: Path,
) -> PhysicalProductionEvidenceBridge:
    """Build production C2 directly from physical C1 without full-pair state."""

    return _build_bridge(
        accepted_risk_archive=accepted_risk_archive,
        historical_bridge=historical_bridge,
        firm_ontology=firm_ontology,
        firm_availability=firm_availability,
        preopen_acquisition_receipt=preopen_acquisition_receipt,
        terminal_archive=terminal_archive,
        output_root=output_root,
        fixture_only=False,
    )


def _build_test_fixture_physical_production_evidence_bridge(
    **kwargs: object,
) -> PhysicalProductionEvidenceBridge:
    """Offline integration seam; its C2 archive remains formally ineligible."""

    return _build_bridge(**kwargs, fixture_only=True)  # type: ignore[arg-type]


def require_physical_production_evidence_bridge(
    value: PhysicalProductionEvidenceBridge,
) -> PhysicalProductionEvidenceBridge:
    _require_dependencies()
    if type(value) is not PhysicalProductionEvidenceBridge:
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge changed type"
        )
    _validate_bridge_surface(value)
    with _LOCK:
        registered = _BRIDGES.get(id(value))
    if (
        registered is None
        or registered[0]() is not value
        or registered[1] != canonical_json_bytes(_bridge_record(value))
        or registered[2] != _bridge_topology(value)
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge lost builder authority"
        )
    try:
        c2 = _physical_c2.require_physical_production_input_archive(
            value.production_input_archive
        )
        if value.firm_authority_mode == NORMAL_FIRM_AUTHORITY_MODE:
            _reauthenticate_parents(
                accepted_risk_archive=value.accepted_risk_archive,
                historical_bridge=value.historical_bridge,
                firm_ontology=value.firm_ontology,
                firm_availability=value.firm_availability,
                preopen_acquisition_receipt=value.preopen_acquisition_receipt,
                terminal_archive=value.terminal_archive,
            )
        elif value.firm_authority_mode == SECTION72_FIRM_AUTHORITY_MODE:
            if (
                value.firm_ontology is not value.firm_availability
                or value.preopen_acquisition_receipt is not value.terminal_archive
            ):
                raise PhysicalProductionEvidenceBridgeError(
                    "owner-waived bridge parent topology changed"
                )
            _reauthenticate_owner_waived_parents(
                accepted_risk_archive=value.accepted_risk_archive,
                historical_bridge=value.historical_bridge,
                firm_admission=value.firm_ontology,
                preopen_prereview_archive=value.preopen_acquisition_receipt,
            )
        else:
            raise PhysicalProductionEvidenceBridgeError(
                "physical production-evidence firm authority mode changed"
            )
    except (TypeError, ValueError, AttributeError) as exc:
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge parent changed"
        ) from exc
    false_flags = (
        value.full_accepted_risk_pair_materialized,
        value.full_production_evidence_materialized,
        value.independently_reviewed,
        value.production_evidence_receipt_available,
        value.provider_access,
        value.credential_access,
        value.quantconnect_access,
        value.outcome_access,
        value.result_access,
        value.deployment,
        value.orders,
        value.trading,
    )
    record = _bridge_record(value)
    digest = sha256_bytes(canonical_json_bytes(record))
    normal = value.firm_authority_mode == NORMAL_FIRM_AUTHORITY_MODE
    waived = value.firm_authority_mode == SECTION72_FIRM_AUTHORITY_MODE
    if normal:
        waiver_fields_are_exact = (
            value.owner_waived_firm_admission_id is None
            and value.owner_waived_firm_admission_sha256 is None
            and value.firm_owner_decision_id is None
            and value.firm_owner_decision_sha256 is None
            and value.firm_refusal_ledger_id is None
            and value.firm_refusal_ledger_sha256 is None
            and value.owner_waiver_scope is None
            and value.historical_availability_claimed is True
            and value.owner_waiver_signature_required is False
        )
    elif waived:
        admission = value.firm_ontology
        prereview = value.preopen_acquisition_receipt
        waiver_fields_are_exact = (
            type(admission) is _composer.OwnerWaivedAcceptedRiskFirmAdmission
            and type(prereview) is _prereview.PreopenControlPreReviewArchive
            and value.owner_waived_firm_admission_id == admission.admission_id
            and value.owner_waived_firm_admission_sha256
            == admission.admission_sha256
            and value.firm_owner_decision_id == admission.owner_decision_id
            and value.firm_owner_decision_sha256
            == admission.owner_decision_sha256
            and value.firm_refusal_ledger_id == admission.refusal_ledger_id
            and value.firm_refusal_ledger_sha256
            == admission.refusal_ledger_sha256
            and value.owner_waiver_scope == admission.owner_waiver_scope
            and value.historical_availability_claimed is False
            and value.owner_waiver_signature_required is True
        )
        waiver_parent_bindings_are_exact = (
            value.firm_ontology_id == admission.admission_id
            and value.firm_ontology_sha256 == admission.admission_sha256
            and value.firm_availability_id == admission.owner_decision_id
            and value.firm_availability_sha256
            == admission.owner_decision_sha256
            and value.preopen_acquisition_id == prereview.capture_id
            and value.preopen_acquisition_sha256 == prereview.capture_sha256
            and value.terminal_archive_id == prereview.capture_id
            and value.terminal_archive_sha256 == prereview.capture_sha256
            and value.sidecar_row_count
            == value.historical_bridge.analyst_event_binding_row_count
            and value.physical_terminal_count == prereview.terminal_count
            and value.physical_accepted_count == prereview.accepted_count
            and value.physical_refusal_count == prereview.refusal_count
        )
    else:
        waiver_fields_are_exact = False
        waiver_parent_bindings_are_exact = False
    if waived and not waiver_parent_bindings_are_exact:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived bridge retained parent binding changed"
        )
    if (
        any(type(item) is not bool or item for item in false_flags)
        or not waiver_fields_are_exact
        or value.schema != BRIDGE_SCHEMA
        or value.bridge_sha256 != digest
        or value.bridge_id
        != f"arv2-physical-production-evidence-{digest[:24]}"
        or value.accepted_risk_archive_id != value.accepted_risk_archive.archive_id
        or value.accepted_risk_archive_sha256
        != value.accepted_risk_archive.archive_sha256
        or value.production_input_archive_id != c2.archive_id
        or value.production_input_archive_sha256 != c2.archive_sha256
        or value.source_bindings != c2.source_bindings
        or value.source_projection_sha256 != c2.source_projection_sha256
        or value.row_projection_sha256 != c2.row_projection_sha256
        or value.composition_terminal_count != c2.evidence_row_count
        or value.composition_terminal_count > MAX_COMPOSITION_TERMINAL_ROWS
        or type(value.sqlite_peak_page_bytes) is not int
        or value.sqlite_peak_page_bytes < 0
        or value.sqlite_peak_page_bytes > _composer.MAX_COMPOSER_SPOOL_BYTES
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge semantic binding changed"
        )
    require_sha256(
        value.composition_terminal_projection_sha256,
        "composition terminal projection SHA-256",
    )
    return value


def render_physical_production_evidence_review_candidate(
    value: PhysicalProductionEvidenceBridge,
) -> bytes:
    """Render a bounded, row-free surface for later independent review.

    The document is intentionally non-affirmative.  It cannot be used as the
    owner-signed acquisition receipt; a later milestone must define and review
    that affirmative receipt loader explicitly.
    """

    bridge = require_physical_production_evidence_bridge(value)
    try:
        c2 = _physical_c2.require_reviewable_physical_production_archive(
            bridge.production_input_archive
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence review candidate is not production eligible"
        ) from exc
    return canonical_json_bytes(
        {
            "schema": REVIEW_CANDIDATE_SCHEMA,
            "firm_authority_mode": bridge.firm_authority_mode,
            "owner_waived_firm_admission_id": (
                bridge.owner_waived_firm_admission_id
            ),
            "owner_waived_firm_admission_sha256": (
                bridge.owner_waived_firm_admission_sha256
            ),
            "firm_owner_decision_id": bridge.firm_owner_decision_id,
            "firm_owner_decision_sha256": bridge.firm_owner_decision_sha256,
            "firm_refusal_ledger_id": bridge.firm_refusal_ledger_id,
            "firm_refusal_ledger_sha256": bridge.firm_refusal_ledger_sha256,
            "owner_waiver_scope": bridge.owner_waiver_scope,
            "historical_availability_claimed": (
                bridge.historical_availability_claimed
            ),
            "independently_reviewed": False,
            "bridge_id": bridge.bridge_id,
            "bridge_sha256": bridge.bridge_sha256,
            "accepted_risk_archive_id": bridge.accepted_risk_archive_id,
            "accepted_risk_archive_sha256": bridge.accepted_risk_archive_sha256,
            "production_input_archive_id": bridge.production_input_archive_id,
            "production_input_archive_sha256": bridge.production_input_archive_sha256,
            "evidence_authority_id": c2.evidence_authority_id,
            "evidence_authority_sha256": c2.evidence_authority_sha256,
            "source_projection_sha256": bridge.source_projection_sha256,
            "row_projection_sha256": bridge.row_projection_sha256,
            "composition_terminal_count": bridge.composition_terminal_count,
            "composition_terminal_projection_sha256": (
                bridge.composition_terminal_projection_sha256
            ),
            "evidence_row_count": c2.evidence_row_count,
            "evidence_rows": c2.evidence_rows.to_record(),
            "evidence_package": c2.evidence_package.to_record(),
            "comparison_report": c2.comparison_report.to_record(),
            "comparison_report_sha256": c2.comparison_report_sha256,
            "batches": [item.to_record() for item in c2.batches],
            "independent_review_status": "pending",
            "production_evidence_receipt_available": False,
            "full_accepted_risk_pair_materialized": False,
            "full_production_evidence_materialized": False,
            "contains_provider_rows": False,
            "contains_outcome_or_price": False,
            "qc_launch_available": False,
        }
    )


def section72_owner_waived_preopen_session_axis(
    value: PhysicalProductionEvidenceBridge,
) -> tuple[str, ...]:
    """Return the validated session axis of an exact owner-waived bridge."""

    bridge = require_physical_production_evidence_bridge(value)
    if bridge.firm_authority_mode != SECTION72_FIRM_AUTHORITY_MODE:
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge is not section-72 owner waived"
        )
    manifest, _sources = _owner_waived_manifest(
        bridge.preopen_acquisition_receipt
    )
    try:
        sessions = tuple(
            item.decision_session
            for item in _preopen_io.core._parse_control_sessions(
                manifest["control_sessions"]
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen session axis changed"
        ) from exc
    if not sessions or sessions != tuple(sorted(set(sessions))):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen session axis changed"
        )
    _prereview.require_preopen_control_prereview_archive(
        bridge.preopen_acquisition_receipt
    )
    return sessions


def iter_section72_owner_waived_preopen_terminal_sessions(
    value: PhysicalProductionEvidenceBridge,
) -> Iterator[_streaming.PhysicalTerminalSessionBlock]:
    """Replay the inert waiver capture without minting a reviewed archive.

    The prereview boundary intentionally exposes only authenticated bytes.  This
    adapter validates those bytes once as a complete batch-major output, then
    performs a second bounded merge into the existing immutable per-session
    terminal-block vocabulary.  It never upgrades the capture to an independent
    review receipt or to ``PhysicalPreopenTerminalArchive``.
    """

    bridge = require_physical_production_evidence_bridge(value)
    if bridge.firm_authority_mode != SECTION72_FIRM_AUTHORITY_MODE:
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence bridge is not section-72 owner waived"
        )
    archive = bridge.preopen_acquisition_receipt
    if type(archive) is not _prereview.PreopenControlPreReviewArchive:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal archive changed exact type"
        )
    archive = _prereview.require_preopen_control_prereview_archive(archive)
    manifest, _sources = _owner_waived_manifest(archive)
    try:
        projection, totals = _preopen_io._validated_batch_major_output_payloads(
            manifest,
            _prereview.iter_preopen_control_prereview_output_shard_payloads(
                archive
            ),
        )
        controls = _preopen_io.core._parse_control_sessions(
            manifest["control_sessions"]
        )
        universes = _preopen_io.core._parse_universe_sessions(
            manifest["universe_sessions"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal session authority did not authenticate"
        ) from exc
    expected_totals = {
        "terminal_count": archive.terminal_count,
        "accepted_count": archive.accepted_count,
        "refusal_count": archive.refusal_count,
    }
    if projection != archive.output_shard_payload_projection_sha256:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal payload projection changed"
        )
    if totals != expected_totals:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal aggregate census changed"
        )
    if (
        bridge.physical_terminal_count != archive.terminal_count
        or bridge.physical_accepted_count != archive.accepted_count
        or bridge.physical_refusal_count != archive.refusal_count
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived bridge terminal census binding changed"
        )
    control_by_session = {item.decision_session: item for item in controls}
    universe_by_session = {item.decision_session: item for item in universes}
    if len(control_by_session) != len(controls):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen control session axis changed"
        )
    if len(universe_by_session) != len(universes):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen universe session axis changed"
        )
    sessions = tuple(control_by_session)
    if sessions != tuple(sorted(set(sessions))):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen control session axis changed"
        )
    if tuple(universe_by_session) != sessions:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen universe session axis changed"
        )
    descriptors = manifest.get("output_shards")
    if type(descriptors) is not list:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal descriptor inventory changed type"
        )
    if any(type(item) is not dict for item in descriptors):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal descriptor changed exact type"
        )

    session_index = 0
    pending_rows: list[dict[str, object]] = []
    pending_raw_bytes = 0
    last_key: tuple[str, str] | None = None
    yielded_count = accepted_count = refusal_count = 0

    def emit_until(
        target: str, *, include_target: bool,
    ) -> Iterator[_streaming.PhysicalTerminalSessionBlock]:
        nonlocal session_index, pending_rows, pending_raw_bytes
        nonlocal yielded_count, accepted_count, refusal_count
        while session_index < len(sessions):
            session = sessions[session_index]
            if session > target or (session == target and not include_target):
                return
            rows = pending_rows if session == target else []
            if session == target:
                pending_rows = []
                raw_bytes = pending_raw_bytes
                pending_raw_bytes = 0
            else:
                raw_bytes = 0
            if len(rows) > MAX_COMPOSITION_TERMINAL_ROWS:
                raise PhysicalProductionEvidenceBridgeCapacityError(
                    "owner-waived preopen session terminal census exceeded capacity"
                )
            try:
                accepted_raw = [
                    row for row in rows if row["disposition"] == "accepted"
                ]
                refused_raw = [
                    row for row in rows if row["disposition"] == "named_refusal"
                ]
                accepted = tuple(
                    _streaming._eligible_from_record(
                        row["eligible_security_session"]
                    )
                    for row in accepted_raw
                )
                refused = tuple(
                    _streaming._refusal_from_record(row["census_refusal"])
                    for row in refused_raw
                )
                control_root = _preopen_io._merkle(rows)
                universe_root = _preopen_io._merkle([
                    {
                        "terminal": (
                            "accepted"
                            if row["disposition"] == "accepted"
                            else "refused"
                        ),
                        "value": (
                            row["eligible_security_session"]
                            if row["disposition"] == "accepted"
                            else row["census_refusal"]
                        ),
                    }
                    for row in rows
                ])
            except (KeyError, TypeError, ValueError) as exc:
                raise PhysicalProductionEvidenceBridgeError(
                    "owner-waived preopen terminal row could not be reconstructed"
                ) from exc
            control = control_by_session[session]
            universe = universe_by_session[session]
            observed = (len(accepted), len(refused), len(rows))
            if observed != (
                control.accepted_count,
                control.refusal_count,
                control.terminal_count,
            ):
                raise PhysicalProductionEvidenceBridgeError(
                    "owner-waived preopen control session census changed"
                )
            if observed != (
                universe.accepted_count,
                universe.refusal_count,
                universe.terminal_count,
            ):
                raise PhysicalProductionEvidenceBridgeError(
                    "owner-waived preopen universe session census changed"
                )
            if control_root != control.terminal_merkle_root:
                raise PhysicalProductionEvidenceBridgeError(
                    "owner-waived preopen control session root changed"
                )
            if universe_root != universe.terminal_merkle_root:
                raise PhysicalProductionEvidenceBridgeError(
                    "owner-waived preopen universe session root changed"
                )
            yielded_count += len(rows)
            accepted_count += len(accepted)
            refusal_count += len(refused)
            session_index += 1
            yield _streaming.PhysicalTerminalSessionBlock(
                decision_session=session,
                accepted=accepted,
                refused=refused,
                terminal_count=len(rows),
                control_terminal_merkle_root=control_root,
                universe_terminal_merkle_root=universe_root,
                raw_byte_count=raw_bytes,
            )

    payloads = iter(
        _prereview.iter_preopen_control_prereview_output_shard_payloads(archive)
    )
    offset = 0
    try:
        while offset < len(descriptors):
            chunk = descriptors[offset]["decision_chunk_ordinal"]
            group: list[tuple[dict[str, object], bytes]] = []
            while (
                offset < len(descriptors)
                and descriptors[offset]["decision_chunk_ordinal"] == chunk
            ):
                try:
                    payload = next(payloads)
                except StopIteration as exc:
                    raise PhysicalProductionEvidenceBridgeError(
                        "owner-waived preopen terminal shard census changed"
                    ) from exc
                group.append((descriptors[offset], payload))
                offset += 1
            cursors = [
                _preopen_io._PhysicalShardCursor(descriptor, payload)
                for descriptor, payload in group
            ]
            heap: list[tuple[str, str, int, dict[str, object]]] = []
            for cursor_index, cursor in enumerate(cursors):
                row = cursor.next()
                if row is not None:
                    heapq.heappush(heap, (
                        row["decision_session"], row["security_id"],
                        cursor_index, row,
                    ))
            while heap:
                session, security_id, cursor_index, row = heapq.heappop(heap)
                key = (session, security_id)
                if last_key is not None and key <= last_key:
                    raise PhysicalProductionEvidenceBridgeError(
                        "owner-waived preopen terminal order changed"
                    )
                if session not in control_by_session:
                    raise PhysicalProductionEvidenceBridgeError(
                        "owner-waived preopen terminal escaped declared sessions"
                    )
                if pending_rows and pending_rows[0]["decision_session"] != session:
                    yield from emit_until(
                        pending_rows[0]["decision_session"], include_target=True
                    )
                elif not pending_rows:
                    yield from emit_until(session, include_target=False)
                pending_rows.append(row)
                pending_raw_bytes += len(canonical_json_bytes(row))
                last_key = key
                following = cursors[cursor_index].next()
                if following is not None:
                    heapq.heappush(heap, (
                        following["decision_session"], following["security_id"],
                        cursor_index, following,
                    ))
        sentinel = object()
        if next(payloads, sentinel) is not sentinel:
            raise PhysicalProductionEvidenceBridgeError(
                "owner-waived preopen terminal shard census changed"
            )
        if pending_rows:
            yield from emit_until(
                pending_rows[0]["decision_session"], include_target=True
            )
        if session_index < len(sessions):
            yield from emit_until(sessions[-1], include_target=True)
    except PhysicalProductionEvidenceBridgeError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal replay changed"
        ) from exc
    if yielded_count != archive.terminal_count:
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal replay row census changed"
        )
    if (
        accepted_count != archive.accepted_count
        or refusal_count != archive.refusal_count
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal replay disposition census changed"
        )
    if session_index != len(sessions):
        raise PhysicalProductionEvidenceBridgeError(
            "owner-waived preopen terminal replay session census changed"
        )
    _prereview.require_preopen_control_prereview_archive(archive)
    _require_dependencies()


def begin_physical_production_evidence_epoch(
    bridge: PhysicalProductionEvidenceBridge,
) -> PhysicalProductionEvidenceEpoch:
    """Open one exclusive current-then-censored replay epoch."""

    bridge = require_physical_production_evidence_bridge(bridge)
    with _LOCK:
        if any(
            state.bridge is bridge and not (state.failed or state.complete)
            for _ref, _static, state in _EPOCHS.values()
        ):
            raise PhysicalProductionEvidenceBridgeError(
                "physical production-evidence bridge already has an active epoch"
            )
        bridge_identity = id(bridge)
        ordinal = _BRIDGE_EPOCH_COUNTERS.get(bridge_identity, 0) + 1
        _BRIDGE_EPOCH_COUNTERS[bridge_identity] = ordinal
        seed = {
            "schema": EPOCH_SCHEMA,
            "bridge_id": bridge.bridge_id,
            "bridge_sha256": bridge.bridge_sha256,
            "epoch_ordinal": ordinal,
            "pid": os.getpid(),
            "owner_thread_id": threading.get_ident(),
        }
        digest = sha256_bytes(canonical_json_bytes(seed))
        value = object.__new__(PhysicalProductionEvidenceEpoch)
        object.__setattr__(value, "schema", EPOCH_SCHEMA)
        object.__setattr__(value, "epoch_id", f"arv2-physical-c2-epoch-{digest[:24]}")
        state = _EpochState(
            bridge=bridge,
            next_arm_index=0,
            active=False,
            failed=False,
            complete=False,
            arm_counts=[],
            arm_hashes=[],
            pid=os.getpid(),
            owner_thread_id=threading.get_ident(),
        )
        static = canonical_json_bytes(
            {"schema": value.schema, "epoch_id": value.epoch_id}
        )
        identity = id(value)
        reference = weakref.ref(
            value, lambda ref, key=identity: _forget_epoch(key, ref)
        )
        _EPOCHS[identity] = (reference, static, state)
    return value


def _epoch_state(value: PhysicalProductionEvidenceEpoch) -> _EpochState:
    if type(value) is not PhysicalProductionEvidenceEpoch:
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence epoch changed type"
        )
    with _LOCK:
        registered = _EPOCHS.get(id(value))
    expected = canonical_json_bytes(
        {"schema": value.schema, "epoch_id": value.epoch_id}
    )
    if (
        registered is None
        or registered[0]() is not value
        or registered[1] != expected
        or value.schema != EPOCH_SCHEMA
    ):
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence epoch lost builder authority"
        )
    state = registered[2]
    if (
        state.pid != os.getpid()
        or state.owner_thread_id != threading.get_ident()
    ):
        state.failed = True
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence epoch process or thread changed"
        )
    require_physical_production_evidence_bridge(state.bridge)
    return state


def iter_physical_production_scoring_rows(
    epoch: PhysicalProductionEvidenceEpoch,
    signal_arm: SignalArm,
) -> Iterator[PhysicalProductionScoringRow]:
    """Yield exactly one arm once; early close permanently invalidates the epoch."""

    state = _epoch_state(epoch)
    if type(signal_arm) is not SignalArm:
        state.failed = True
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence epoch arm changed type"
        )
    if (
        state.failed
        or state.complete
        or state.active
        or state.next_arm_index >= len(_ARM_ORDER)
        or signal_arm is not _ARM_ORDER[state.next_arm_index]
    ):
        state.failed = True
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence epoch arm order or lease changed"
        )
    state.active = True
    completed = False
    count = 0
    hasher = hashlib.sha256()
    hasher.update(b"[")
    try:
        for joined in _physical_c2.iter_physical_normalized_evidence_rows(
            state.bridge.production_input_archive, signal_arm
        ):
            _require_dependencies()
            normalized = joined.normalized_row
            evidence = joined.evidence
            if evidence.firm is None:
                raise PhysicalProductionEvidenceBridgeError(
                    "physical normalized row lost firm endpoint evidence"
                )
            label = build_endpoint_label_evidence(
                c2_row_sha256=normalized.row_sha256,
                provider_event_id=normalized.provider_event_id,
                raw_previous_label=evidence.firm.raw_previous_label,
                raw_current_label=evidence.firm.raw_current_label,
                source_sha256=normalized.source_locator.raw_row_sha256,
                available_at=evidence.firm.available_at,
            )
            row = PhysicalProductionScoringRow(
                normalized_evidence=joined,
                endpoint_label=label,
            )
            payload = canonical_json_bytes(
                {
                    "normalized": normalized.to_record(),
                    "evidence": evidence.to_record(),
                    "endpoint_label": {
                        **label.semantic_record(),
                        "evidence_sha256": label.evidence_sha256,
                    },
                }
            )
            if count:
                hasher.update(b",")
            hasher.update(payload[:-1])
            count += 1
            yield row
        _require_dependencies()
        hasher.update(b"]\n")
        expected = _physical_c2.physical_production_batch(
            state.bridge.production_input_archive, signal_arm
        ).normalized_row_count
        if count != expected:
            raise PhysicalProductionEvidenceBridgeError(
                "physical production-evidence epoch arm census changed"
            )
        state.arm_counts.append((signal_arm.value, count))
        state.arm_hashes.append((signal_arm.value, hasher.hexdigest()))
        state.next_arm_index += 1
        completed = True
    finally:
        state.active = False
        if not completed:
            state.failed = True


def finish_physical_production_evidence_epoch(
    epoch: PhysicalProductionEvidenceEpoch,
) -> PhysicalProductionEvidenceEpochReceipt:
    """Seal only an exhausted two-arm epoch; it cannot be replayed."""

    state = _epoch_state(epoch)
    if (
        state.failed
        or state.active
        or state.complete
        or state.next_arm_index != len(_ARM_ORDER)
        or tuple(name for name, _ in state.arm_counts)
        != tuple(arm.value for arm in _ARM_ORDER)
        or tuple(name for name, _ in state.arm_hashes)
        != tuple(arm.value for arm in _ARM_ORDER)
    ):
        state.failed = True
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence epoch is incomplete, failed, or spent"
        )
    seed = {
        "schema": EPOCH_RECEIPT_SCHEMA,
        "bridge_id": state.bridge.bridge_id,
        "bridge_sha256": state.bridge.bridge_sha256,
        "epoch_id": epoch.epoch_id,
        "arm_row_counts": [list(item) for item in state.arm_counts],
        "arm_row_projection_sha256s": [list(item) for item in state.arm_hashes],
        "complete_two_arm_census": True,
        "full_pair_materialized": False,
        "capabilities": {
            "provider_access": False,
            "quantconnect_access": False,
            "outcome_access": False,
        },
    }
    digest = sha256_bytes(canonical_json_bytes(seed))
    receipt = PhysicalProductionEvidenceEpochReceipt(
        schema=EPOCH_RECEIPT_SCHEMA,
        receipt_id=f"arv2-physical-c2-epoch-receipt-{digest[:24]}",
        receipt_sha256=digest,
        bridge_id=state.bridge.bridge_id,
        bridge_sha256=state.bridge.bridge_sha256,
        epoch_id=epoch.epoch_id,
        arm_row_counts=tuple(state.arm_counts),
        arm_row_projection_sha256s=tuple(state.arm_hashes),
        complete_two_arm_census=True,
        full_pair_materialized=False,
        provider_access=False,
        quantconnect_access=False,
        outcome_access=False,
    )
    if receipt.to_record(include_identity=False) != seed:
        state.failed = True
        raise PhysicalProductionEvidenceBridgeError(
            "physical production-evidence epoch receipt changed"
        )
    state.complete = True
    return receipt


__all__ = (
    "BRIDGE_SCHEMA",
    "EPOCH_RECEIPT_SCHEMA",
    "EPOCH_SCHEMA",
    "NORMAL_FIRM_AUTHORITY_MODE",
    "REVIEW_CANDIDATE_SCHEMA",
    "SECTION72_FIRM_AUTHORITY_MODE",
    "SECTION72_OWNER_WAIVER_SCOPE",
    "PhysicalProductionEvidenceBridge",
    "PhysicalProductionEvidenceBridgeCapacityError",
    "PhysicalProductionEvidenceBridgeError",
    "PhysicalProductionEvidenceEpoch",
    "PhysicalProductionEvidenceEpochReceipt",
    "PhysicalProductionScoringRow",
    "begin_physical_production_evidence_epoch",
    "build_physical_production_evidence_bridge",
    "build_section72_owner_waived_physical_production_evidence_bridge",
    "finish_physical_production_evidence_epoch",
    "iter_physical_production_scoring_rows",
    "iter_section72_owner_waived_preopen_terminal_sessions",
    "render_physical_production_evidence_review_candidate",
    "require_physical_production_evidence_bridge",
    "section72_owner_waived_preopen_session_axis",
)
