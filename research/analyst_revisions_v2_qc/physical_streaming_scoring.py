"""Bounded formal scoring directly from the reviewed physical C2 index.

This module is the disk-backed successor to the legacy formal scoring entry
point.  It accepts the reviewed physical production-session index and its
matching pre-open terminal archive, derives event contributions into a private
bounded SQLite spool, and retains only one decision session while scoring.
It never constructs ``ProductionEvidenceAuthority``, ``ProductionInputBatch``,
the normalized C2 union, or the full row-evidence lookup.

The module is deliberately standalone.  The formal submission/orchestration
modules must opt into it in a separately reviewed integration change.  Nothing
here grants provider, outcome, QuantConnect, deployment, order, or trading
authority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import threading
import weakref
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes,
    decode_utf8,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2.global_benchmark_contract import (
    GlobalBenchmarkContract,
    GlobalBenchmarkContractError,
    GlobalRatingMapping,
    GlobalRatingMappingRefusal,
    require_loaded_global_benchmark_contract,
    resolve_global_rating,
)
from research.analyst_revisions_v2.production_input_pipeline import SignalArm
from research.analyst_revisions_v2.production_scoring import (
    CONTROL_COLUMNS,
    FORMAL_PRIMARY_FOLD_IDS,
    SCORING_CONTRACT_ID,
    SCORING_CONTRACT_SHA256,
    EligibleSecuritySession,
    EligibleSecuritySessionRefusal,
    EventScoringTerminal,
    FinalDecisionInput,
    FoldPartition,
    PrecontrolDecisionRow,
    ProductionScoringError,
    ProductionScoringFold,
    ScoreDisposition,
    ScoreState,
    ScoringRefusal,
    _DailyContribution,
    _build_precontrol_session_terminals,
    _terminal,
    build_formal_production_scoring_fold,
    formal_horizon_fold_boundary,
)
from research.analyst_revisions_v2.production_truth_gate import (
    FORMAL_SESSION_GEOMETRY,
    FORMAL_SESSION_GEOMETRY_SHA256,
)
from research.analyst_revisions_v2_qc import formal_input_bundle as _bundle
from research.analyst_revisions_v2_qc import formal_streaming_input as _legacy
from research.analyst_revisions_v2_qc import (
    physical_production_evidence_acquisition as _physical_acquisition,
)
from research.analyst_revisions_v2_qc import physical_production_input_archive as _c2
from research.analyst_revisions_v2_qc import physical_production_session_index as _index
from research.analyst_revisions_v2_qc import (
    preopen_control_prereview_downloader as _prereview,
)
from research.analyst_revisions_v2_qc.formal_input_bundle import (
    CENSORED_VIEW_LABEL,
    CURRENT_VIEW_LABEL,
    GLOBAL_COMPARATOR_COVERAGE_SCHEMA,
    FormalGlobalComparatorCoverage,
    FormalInputBundleError,
    ScoringResultBinding,
    _FirmBaselineContribution,
    _GlobalLabelResolution,
    _active_component_topologies,
    _build_global_coverage_value,
    _cached_raw_canonical_label_key,
    _coverage_ledger,
    _coverage_ratio,
    _endpoint_status,
    _is_preoutcome_candidate_date,
    _label_digest,
    _pair_status,
    pool_formal_global_comparator_coverages,
    require_formal_global_comparator_coverage,
)
from research.analyst_revisions_v2_qc.formal_streaming_input import (
    STREAMING_BUILDER_SCHEMA,
    STREAMING_FOLD_SCHEMA,
    STREAMING_METHOD_ID,
    STREAMING_SCORING_SCHEMA,
    FormalStreamingInputError,
    FormalStreamingRefusalReason,
    FormalStreamingRunRefusal,
    PhysicalPreopenTerminalArchive,
    StreamedFoldCommitment,
    StreamedControlModel,
    StreamedProductionScoringArtifact,
    StreamedTestSessionBlock,
    _DiskBackedDecimalMgs,
    _apply_streamed_model,
    _build_streamed_model,
    _chain_hasher,
    _chain_update,
    _paired_bootstrap_authority_record,
    _retained_object_graph_bytes,
    _rolling_chain_seed,
    _rolling_chain_update,
    _test_block,
)
from research.analyst_revisions_v2_qc.physical_production_evidence_bridge import (
    PhysicalProductionScoringRow,
)
from research.analyst_revisions_v2_qc.physical_production_session_index import (
    PhysicalProductionScoringSessionInput,
    PhysicalProductionSessionIndex,
    PhysicalProductionSessionIndexError,
)


PHYSICAL_SCORING_BUILDER_SCHEMA = (
    "arv2-physical-production-streamed-scoring-builder-v1"
)
PHYSICAL_SCORING_SPOOL_SCHEMA = "arv2-physical-production-scoring-spool-v1"
PHYSICAL_SCORING_LINEAGE_SCHEMA = (
    "arv2-physical-production-streamed-scoring-lineage-v1"
)
PHYSICAL_POWER_CALIBRATION_STREAM_SCHEMA = (
    "arv2-physical-production-power-calibration-stream-v1"
)
SECTION72_PHYSICAL_CAPACITY_SCHEMA = (
    "arv2-section72-owner-waived-physical-scoring-capacity-v1"
)
SECTION72_PHYSICAL_CAPACITY_AUTHORITY_MODE = (
    "section72_owner_waived_frozen_physical_hard_ceilings"
)
MAX_PHYSICAL_SCORING_SPOOL_BYTES = 16 * 1024 * 1024 * 1024
MAX_PHYSICAL_SCORING_DERIVED_ROWS = 80_000_000
MAX_PHYSICAL_SCORING_RECORD_BYTES = 16 * 1024 * 1024
MAX_GLOBAL_LABEL_DIAGNOSTIC_ROWS = 4_096
SPOOL_CAPACITY_CHECK_INTERVAL = 1_024
SECTION72_PHYSICAL_CAPACITY_LIMITS = (
    ("max_active_contribution_count_per_arm_session", 10_000_000),
    ("max_archive_passes_per_fold", 3),
    ("max_c2_normalized_row_count", 40_000_000),
    ("max_daily_requirement_keys_retained", 40_000_000),
    ("max_daily_requirement_sessions_retained", 10_000),
    ("max_disk_mgs_live_decimal_count", 1_000_000_000),
    ("max_disk_mgs_spool_byte_count", 64 * 1024 * 1024 * 1024),
    ("max_disk_mgs_spool_file_count", 100_000),
    ("max_disk_mgs_spool_row_count", 80_000_000),
    ("max_disk_mgs_width", 100_000),
    ("max_formal_session_block_row_count", 2_000_000),
    ("max_formal_session_block_uncompressed_bytes", 192 * 1024 * 1024),
    ("max_formal_shard_count", 100_000),
    ("max_formal_shard_row_count", 2_000_000),
    ("max_formal_shard_uncompressed_bytes", 192 * 1024 * 1024),
    ("max_formal_total_compressed_bytes", 64 * 1024 * 1024 * 1024),
    ("max_industry_level_count_per_arm_fold", 100_000),
    ("max_physical_chunk_compressed_bytes", 2 * 1024 * 1024 * 1024),
    ("max_physical_session_terminal_count", 2_000_000),
    ("max_physical_session_uncompressed_bytes", 2 * 1024 * 1024 * 1024),
    ("max_physical_shard_count", 100_000),
    ("max_retained_input_graph_bytes", 64 * 1024 * 1024 * 1024),
    ("max_retained_institution_count", 5_000_000),
    ("max_retained_minute_requirement_count", 40_000_000),
    ("max_retained_security_count", 5_000_000),
    ("max_runtime_resource_spool_byte_count", 64 * 1024 * 1024 * 1024),
    ("max_session_contribution_lineage_count", 10_000_000),
)
_ARM_ORDER = (
    SignalArm.CURRENT_VINTAGE,
    SignalArm.CONSERVATIVE_CENSORED,
)
_ENDPOINT_STATUS_IDS = ("mapped", "measured_refusal", "unknown", "invalid")
_DIRECTION_STATUS_IDS = ("expected_sign", "opposite_sign", "zero_delta")
_NO_CANONICAL_LABEL_SHA256 = "0" * 64
_CREATE_DERIVED_SQL = (
    "CREATE TABLE contributions("
    "kind INTEGER NOT NULL, arm_rank INTEGER NOT NULL, ordinal INTEGER NOT NULL, "
    "eligible_session TEXT NOT NULL, security_id TEXT NOT NULL, "
    "institution_id TEXT NOT NULL, common_event_id TEXT NOT NULL, "
    "linked_sort BLOB NOT NULL, payload BLOB NOT NULL, "
    "PRIMARY KEY(kind, arm_rank, ordinal)) WITHOUT ROWID",
    "CREATE INDEX contribution_visibility ON contributions("
    "kind, arm_rank, security_id, eligible_session, institution_id, "
    "common_event_id, linked_sort)",
    "CREATE TABLE firm_lineage("
    "arm_rank INTEGER NOT NULL, security_id TEXT NOT NULL, "
    "eligible_session TEXT NOT NULL, row_sha256 TEXT NOT NULL, "
    "PRIMARY KEY(arm_rank, security_id, eligible_session, row_sha256)) "
    "WITHOUT ROWID",
    "CREATE TABLE labels("
    "arm_rank INTEGER NOT NULL, row_sha256 TEXT NOT NULL, raw_action TEXT NOT NULL, "
    "previous_payload BLOB NOT NULL, current_payload BLOB NOT NULL, "
    "PRIMARY KEY(arm_rank, row_sha256)) WITHOUT ROWID",
    "CREATE TABLE terminals("
    "arm_rank INTEGER NOT NULL, row_sha256 TEXT NOT NULL, payload BLOB NOT NULL, "
    "PRIMARY KEY(arm_rank, row_sha256)) WITHOUT ROWID",
    "CREATE TABLE sessions("
    "decision_session TEXT PRIMARY KEY, input_sha256 TEXT NOT NULL, "
    "terminal_count INTEGER NOT NULL, current_count INTEGER NOT NULL, "
    "censored_count INTEGER NOT NULL) WITHOUT ROWID",
    "CREATE TABLE metadata(key TEXT PRIMARY KEY, payload BLOB NOT NULL) WITHOUT ROWID",
)


class PhysicalStreamingScoringError(FormalStreamingInputError):
    """The physical scoring parents, spool, or state are invalid."""


class PhysicalStreamingScoringCapacityError(PhysicalStreamingScoringError):
    """A fixed physical-scoring disk or row capacity was exceeded."""


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalStreamingScoringLineage:
    """Canonical physical parents retained outside the legacy artifact record."""

    schema: str
    index_id: str
    index_sha256: str
    physical_production_evidence_receipt_id: str
    physical_production_evidence_receipt_sha256: str
    production_input_archive_id: str
    production_input_archive_sha256: str
    accepted_risk_binding_sha256: str
    terminal_archive_id: str
    terminal_archive_sha256: str
    preopen_acquisition_id: str
    preopen_acquisition_sha256: str
    capacity_receipt_id: str
    capacity_receipt_sha256: str
    global_map_id: str
    global_map_sha256: str
    session_count: int
    current_row_count: int
    censored_row_count: int
    review_mode: str
    terminal_parent_kind: str
    capacity_authority_mode: str
    independently_reviewed: bool
    owner_review_waived: bool
    historical_availability_claimed: bool
    post_first_formal_backtest_independent_review_required: bool

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalStreamingScoringCompositionContext:
    """Immediate, reauthenticated parents for the sealed formal composer."""

    accepted_risk_binding: object
    capacity: object
    preopen_acquisition_receipt: object
    global_contract: GlobalBenchmarkContract
    lineage: PhysicalStreamingScoringLineage
    next_fold_index: int
    active_fold: bool
    finalized: bool


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class Section72PhysicalStreamingCapacityBinding:
    """Truthful hard-cap authority for the one owner-waived section-72 path."""

    receipt_id: str
    receipt_sha256: str
    schema: str
    physical_index: PhysicalProductionSessionIndex = dataclasses.field(repr=False)
    preopen_acquisition_receipt: object = dataclasses.field(repr=False)
    production_evidence_receipt: object = dataclasses.field(repr=False)
    limits: tuple[tuple[str, int], ...]
    review_mode: str
    capacity_authority_mode: str
    owner_waiver_scope: str
    independently_reviewed: bool
    owner_review_waived: bool
    historical_availability_claimed: bool
    post_first_formal_backtest_independent_review_required: bool
    outcome_or_qc_action_authorized: bool

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "index_id": self.physical_index.index_id,
            "index_sha256": self.physical_index.index_sha256,
            "physical_production_evidence_receipt_id": (
                self.production_evidence_receipt.receipt_id
            ),
            "physical_production_evidence_receipt_sha256": (
                self.production_evidence_receipt.receipt_sha256
            ),
            "preopen_prereview_capture_id": (
                self.preopen_acquisition_receipt.capture_id
            ),
            "preopen_prereview_capture_sha256": (
                self.preopen_acquisition_receipt.capture_sha256
            ),
            "limits": dict(self.limits),
            "review_mode": self.review_mode,
            "capacity_authority_mode": self.capacity_authority_mode,
            "owner_waiver_scope": self.owner_waiver_scope,
            "independently_reviewed": self.independently_reviewed,
            "owner_review_waived": self.owner_review_waived,
            "historical_availability_claimed": (
                self.historical_availability_claimed
            ),
            "post_first_formal_backtest_independent_review_required": (
                self.post_first_formal_backtest_independent_review_required
            ),
            "outcome_or_qc_action_authorized": (
                self.outcome_or_qc_action_authorized
            ),
        }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class PhysicalStreamedProductionScoringBuilder:
    builder_id: str
    schema: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PhysicalPowerCalibrationSessionBlock:
    """One current-vintage calibration session, released after its callback."""

    decision_session: str
    session_position: int
    accepted: tuple[FinalDecisionInput, ...]
    refused: tuple[ScoringRefusal, ...]
    block_sha256: str

    def to_record(self) -> dict[str, object]:
        return {
            "decision_session": self.decision_session,
            "session_position": self.session_position,
            "accepted": [
                {
                    "security_id": item.security_id,
                    "decision_sha256": item.row_sha256,
                }
                for item in self.accepted
            ],
            "refused": [
                {
                    "security_id": item.security_id,
                    "refusal_sha256": item.refusal_sha256,
                }
                for item in self.refused
            ],
        }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PhysicalPowerCalibrationStream:
    """Sealed three-pass physical scorer result for nuisance calibration only."""

    stream_id: str
    stream_sha256: str
    schema: str
    physical_index: PhysicalProductionSessionIndex = dataclasses.field(repr=False)
    terminal_archive: object = dataclasses.field(repr=False)
    capacity: object = dataclasses.field(repr=False)
    global_contract: GlobalBenchmarkContract = dataclasses.field(repr=False)
    accepted_risk_binding: object | None = dataclasses.field(repr=False)
    model: StreamedControlModel = dataclasses.field(repr=False)
    index_id: str
    index_sha256: str
    physical_production_evidence_receipt_id: str
    physical_production_evidence_receipt_sha256: str
    production_input_archive_id: str
    production_input_archive_sha256: str
    accepted_risk_binding_sha256: str | None
    terminal_archive_id: str
    terminal_archive_sha256: str
    production_evidence_receipt_id: str
    production_evidence_receipt_sha256: str
    global_map_id: str
    global_map_sha256: str
    calibration_fold_id: str
    calibration_fold_sha256: str
    calibration_fold_geometry: tuple[str, str, str, str, str, str, str]
    calibration_axis_sha256: str
    calibration_session_count: int
    accepted_decision_count: int
    preoutcome_refusal_count: int
    calibration_terminal_sha256: str
    model_sha256: str
    physical_replay_pass_count: int
    observed_capacity: tuple[tuple[str, int], ...]
    provider_access: bool
    outcome_access: bool
    quantconnect_access: bool

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "index_id": self.index_id,
            "index_sha256": self.index_sha256,
            "physical_production_evidence_receipt_id": (
                self.physical_production_evidence_receipt_id
            ),
            "physical_production_evidence_receipt_sha256": (
                self.physical_production_evidence_receipt_sha256
            ),
            "production_input_archive_id": self.production_input_archive_id,
            "production_input_archive_sha256": (
                self.production_input_archive_sha256
            ),
            "accepted_risk_binding_sha256": self.accepted_risk_binding_sha256,
            "terminal_archive_id": self.terminal_archive_id,
            "terminal_archive_sha256": self.terminal_archive_sha256,
            "production_evidence_receipt_id": self.production_evidence_receipt_id,
            "production_evidence_receipt_sha256": (
                self.production_evidence_receipt_sha256
            ),
            "global_map_id": self.global_map_id,
            "global_map_sha256": self.global_map_sha256,
            "calibration_fold_id": self.calibration_fold_id,
            "calibration_fold_sha256": self.calibration_fold_sha256,
            "calibration_fold_geometry": list(self.calibration_fold_geometry),
            "calibration_axis_sha256": self.calibration_axis_sha256,
            "calibration_session_count": self.calibration_session_count,
            "accepted_decision_count": self.accepted_decision_count,
            "preoutcome_refusal_count": self.preoutcome_refusal_count,
            "calibration_terminal_sha256": self.calibration_terminal_sha256,
            "model": self.model.to_record(),
            "model_sha256": self.model_sha256,
            "physical_replay_pass_count": self.physical_replay_pass_count,
            "observed_capacity": dict(self.observed_capacity),
            "capabilities": {
                "provider_access": self.provider_access,
                "outcome_access": self.outcome_access,
                "quantconnect_access": self.quantconnect_access,
            },
        }


@dataclasses.dataclass(frozen=True, slots=True)
class _ArmDescriptor:
    signal_arm: SignalArm


@dataclasses.dataclass(frozen=True, slots=True)
class _EligibleSessionDescriptor:
    eligible_session: str


@dataclasses.dataclass(slots=True)
class _CoverageState:
    fold_id: str
    signal_arm: SignalArm
    expected_sessions: tuple[str, ...]
    next_session_index: int
    last_test_session_by_security: dict[str, str]
    firm_active_count: int = 0
    paired_active_count: int = 0
    firm_component_count: int = 0
    retained_component_count: int = 0
    firm_component_incidence: int = 0
    retained_component_incidence: int = 0
    candidate_dates: int = 0
    capable_dates: int = 0
    firm_totalized_dates: int = 0
    global_totalized_dates: int = 0
    both_constant_dates: int = 0
    score_refused_dates: int = 0


@dataclasses.dataclass(frozen=True, slots=True)
class _BuilderState:
    index: PhysicalProductionSessionIndex
    archive: object
    capacity: object
    global_contract: GlobalBenchmarkContract
    spool_directory: Path
    spool_path: Path
    spool_fingerprint: tuple[object, ...]
    current_batch_id: str
    current_batch_sha256: str
    censored_batch_id: str
    censored_batch_sha256: str
    event_terminal_projection_sha256: str
    base_retained_input_graph_bytes: int
    next_fold_index: int
    fold_commitments: tuple[StreamedFoldCommitment, ...]
    matched_test_terminal_count: int
    matched_test_terminal_sha256: str
    observed: tuple[tuple[str, int], ...]
    active_fold: bool
    finalized: bool
    fixture_only: bool
    pid: int
    owner_thread_id: int


_BUILDERS: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalStreamedProductionScoringBuilder],
        bytes,
        _BuilderState,
        tuple[object, ...],
        str | None,
    ],
] = {}
_ARTIFACTS: dict[
    int,
    tuple[
        weakref.ReferenceType[StreamedProductionScoringArtifact],
        bytes,
        tuple[object, ...],
        bool,
        int,
    ],
] = {}
_POWER_STREAMS: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalPowerCalibrationStream],
        bytes,
        tuple[object, ...],
        bool,
        int,
    ],
] = {}
_SECTION72_CAPACITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[Section72PhysicalStreamingCapacityBinding],
        bytes,
        tuple[object, ...],
        int,
    ],
] = {}
_LOCK = threading.RLock()
_MISSING = object()


def _section72_capacity_topology(
    value: Section72PhysicalStreamingCapacityBinding,
) -> tuple[object, ...]:
    return (
        id(value.physical_index),
        id(value.preopen_acquisition_receipt),
        id(value.production_evidence_receipt),
        id(value.limits),
    )


def _make_section72_capacity_authority():
    records: dict[
        int,
        tuple[
            tuple[
                weakref.ReferenceType[Section72PhysicalStreamingCapacityBinding],
                bytes,
                tuple[object, ...],
                int,
            ],
            PhysicalProductionSessionIndex,
            object,
            object,
        ],
    ] = {}

    def forget(identity: int, reference: object) -> None:
        with _LOCK:
            private = records.get(identity)
            if private is not None and private[0][0] is reference:
                records.pop(identity, None)
                if _SECTION72_CAPACITIES.get(identity) is private[0]:
                    _SECTION72_CAPACITIES.pop(identity, None)

    def register(value: Section72PhysicalStreamingCapacityBinding) -> None:
        identity = id(value)
        reference = weakref.ref(
            value, lambda ref, key=identity: forget(key, ref)
        )
        public = (
            reference,
            canonical_json_bytes(value.to_record()),
            _section72_capacity_topology(value),
            os.getpid(),
        )
        with _LOCK:
            if identity in records or identity in _SECTION72_CAPACITIES:
                raise PhysicalStreamingScoringError(
                    "section-72 physical capacity identity reused"
                )
            records[identity] = (
                public,
                value.physical_index,
                value.preopen_acquisition_receipt,
                value.production_evidence_receipt,
            )
            _SECTION72_CAPACITIES[identity] = public

    def current(
        value: Section72PhysicalStreamingCapacityBinding,
    ) -> tuple[object, ...] | None:
        with _LOCK:
            private = records.get(id(value))
            public = _SECTION72_CAPACITIES.get(id(value))
            if (
                private is None
                or public is not private[0]
                or private[0][0]() is not value
                or private[0][3] != os.getpid()
            ):
                records.pop(id(value), None)
                _SECTION72_CAPACITIES.pop(id(value), None)
                return None
            return (
                private[0][1],
                private[0][2],
                private[1],
                private[2],
                private[3],
            )

    def reset_after_fork() -> None:
        global _SECTION72_CAPACITIES
        records.clear()
        _SECTION72_CAPACITIES = {}

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)
    return register, current


(
    _section72_capacity_register,
    _section72_capacity_current,
) = _make_section72_capacity_authority()
del _make_section72_capacity_authority


_PINNED_DEPENDENCIES = (
    (_index, "require_formal_physical_production_session_index", _index.require_formal_physical_production_session_index),
    (_index, "require_physical_production_session_index", _index.require_physical_production_session_index),
    (_index, "iter_physical_production_scoring_session_inputs", _index.iter_physical_production_scoring_session_inputs),
    (_index, "_iter_test_fixture_physical_production_scoring_session_inputs", _index._iter_test_fixture_physical_production_scoring_session_inputs),
    (_legacy, "require_physical_preopen_terminal_archive", _legacy.require_physical_preopen_terminal_archive),
    (_legacy, "require_formal_streaming_capacity_binding", _legacy.require_formal_streaming_capacity_binding),
    (_legacy, "_checked_limits", _legacy._checked_limits),
    (_legacy, "_stream_ordinals", _legacy._stream_ordinals),
    (_prereview, "require_preopen_control_prereview_archive", _prereview.require_preopen_control_prereview_archive),
    (_c2, "physical_production_batch", _c2.physical_production_batch),
)
_PINNED_LOCALS = (
    ("canonical_json_bytes", canonical_json_bytes),
    ("decode_utf8", decode_utf8),
    ("require_sha256", require_sha256),
    ("sha256_bytes", sha256_bytes),
    ("strict_json_loads", strict_json_loads),
    ("require_loaded_global_benchmark_contract", require_loaded_global_benchmark_contract),
    ("resolve_global_rating", resolve_global_rating),
    ("_build_precontrol_session_terminals", _build_precontrol_session_terminals),
    ("_build_streamed_model", _build_streamed_model),
    ("_apply_streamed_model", _apply_streamed_model),
    ("_build_global_coverage_value", _build_global_coverage_value),
)
_PINNED_CAPACITY = (
    MAX_PHYSICAL_SCORING_SPOOL_BYTES,
    MAX_PHYSICAL_SCORING_DERIVED_ROWS,
    MAX_PHYSICAL_SCORING_RECORD_BYTES,
    MAX_GLOBAL_LABEL_DIAGNOSTIC_ROWS,
    SPOOL_CAPACITY_CHECK_INTERVAL,
    PHYSICAL_SCORING_LINEAGE_SCHEMA,
    PHYSICAL_POWER_CALIBRATION_STREAM_SCHEMA,
    SECTION72_PHYSICAL_CAPACITY_SCHEMA,
    SECTION72_PHYSICAL_CAPACITY_AUTHORITY_MODE,
    SECTION72_PHYSICAL_CAPACITY_LIMITS,
)


def _require_dependencies() -> None:
    if any(
        getattr(module, name, _MISSING) is not expected
        for module, name, expected in _PINNED_DEPENDENCIES
    ) or any(
        globals().get(name, _MISSING) is not expected
        for name, expected in _PINNED_LOCALS
    ) or (
        MAX_PHYSICAL_SCORING_SPOOL_BYTES,
        MAX_PHYSICAL_SCORING_DERIVED_ROWS,
        MAX_PHYSICAL_SCORING_RECORD_BYTES,
        MAX_GLOBAL_LABEL_DIAGNOSTIC_ROWS,
        SPOOL_CAPACITY_CHECK_INTERVAL,
        PHYSICAL_SCORING_LINEAGE_SCHEMA,
        PHYSICAL_POWER_CALIBRATION_STREAM_SCHEMA,
        SECTION72_PHYSICAL_CAPACITY_SCHEMA,
        SECTION72_PHYSICAL_CAPACITY_AUTHORITY_MODE,
        SECTION72_PHYSICAL_CAPACITY_LIMITS,
    ) != _PINNED_CAPACITY:
        raise PhysicalStreamingScoringError(
            "physical streaming scoring dependency changed"
        )


def _terminal_parent_identity(archive: object) -> tuple[str, str, str]:
    if type(archive) is PhysicalPreopenTerminalArchive:
        return archive.archive_id, archive.archive_sha256, "reviewed_terminal_archive"
    if type(archive) is _prereview.PreopenControlPreReviewArchive:
        return (
            archive.capture_id,
            archive.capture_sha256,
            "section72_owner_waived_prereview_archive",
        )
    raise PhysicalStreamingScoringError(
        "physical scoring terminal parent changed exact type"
    )


def _terminal_preopen_parent(archive: object) -> object:
    if type(archive) is _prereview.PreopenControlPreReviewArchive:
        return archive
    if type(archive) is PhysicalPreopenTerminalArchive:
        return archive.preopen_acquisition_receipt
    raise PhysicalStreamingScoringError(
        "physical scoring terminal parent changed exact type"
    )


def _evidence_authority_matches(
    index: PhysicalProductionSessionIndex, evidence: object
) -> bool:
    physical_receipt = index.production_evidence_receipt
    if (
        index.review_mode
        == _physical_acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE
    ):
        return evidence is physical_receipt
    try:
        return (
            physical_receipt.evidence_authority_id
            == evidence.authority.authority_id
            and physical_receipt.evidence_authority_sha256
            == evidence.authority.authority_sha256
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _require_terminal_parent(
    index: PhysicalProductionSessionIndex,
    archive: object,
    *,
    permit_fixture: bool,
) -> object:
    if (
        not permit_fixture
        and index.review_mode
        == _physical_acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE
    ):
        try:
            archive = _prereview.require_preopen_control_prereview_archive(archive)
        except (AttributeError, TypeError, ValueError, OSError) as exc:
            raise PhysicalStreamingScoringError(
                "section-72 physical scoring prereview archive did not authenticate"
            ) from exc
    else:
        try:
            archive = _legacy.require_physical_preopen_terminal_archive(archive)
        except (AttributeError, TypeError, ValueError, OSError) as exc:
            raise PhysicalStreamingScoringError(
                "reviewed physical scoring terminal archive did not authenticate"
            ) from exc
    if (
        archive is not index.production_evidence_receipt.preopen_acquisition_receipt
        and getattr(archive, "preopen_acquisition_receipt", None)
        is not index.production_evidence_receipt.preopen_acquisition_receipt
    ):
        raise PhysicalStreamingScoringError(
            "physical scorer index and terminal parents differ"
        )
    return archive


def _build_section72_capacity(
    *,
    index: PhysicalProductionSessionIndex,
    archive: object,
) -> Section72PhysicalStreamingCapacityBinding:
    index = _index.require_formal_physical_production_session_index(index)
    archive = _prereview.require_preopen_control_prereview_archive(archive)
    receipt = index.production_evidence_receipt
    checked = _legacy._checked_limits(dict(SECTION72_PHYSICAL_CAPACITY_LIMITS))
    if (
        index.review_mode
        != _physical_acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE
        or index.owner_review_waived is not True
        or index.independently_reviewed is not False
        or index.historical_availability_claimed is not False
        or index.post_first_formal_backtest_independent_review_required is not True
        or receipt.preopen_acquisition_receipt is not archive
        or index.owner_waiver_scope is None
    ):
        raise PhysicalStreamingScoringError(
            "section-72 physical capacity parents changed"
        )
    value = object.__new__(Section72PhysicalStreamingCapacityBinding)
    fields: dict[str, object] = {
        "receipt_id": "",
        "receipt_sha256": "",
        "schema": SECTION72_PHYSICAL_CAPACITY_SCHEMA,
        "physical_index": index,
        "preopen_acquisition_receipt": archive,
        "production_evidence_receipt": receipt,
        "limits": checked,
        "review_mode": index.review_mode,
        "capacity_authority_mode": SECTION72_PHYSICAL_CAPACITY_AUTHORITY_MODE,
        "owner_waiver_scope": index.owner_waiver_scope,
        "independently_reviewed": False,
        "owner_review_waived": True,
        "historical_availability_claimed": False,
        "post_first_formal_backtest_independent_review_required": True,
        "outcome_or_qc_action_authorized": False,
    }
    if set(fields) != {item.name for item in dataclasses.fields(value)}:
        raise PhysicalStreamingScoringError(
            "section-72 physical capacity field inventory changed"
        )
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    digest = sha256_bytes(canonical_json_bytes(value.to_record()))
    object.__setattr__(value, "receipt_sha256", digest)
    object.__setattr__(
        value,
        "receipt_id",
        f"arv2-section72-physical-capacity-{digest[:24]}",
    )
    _section72_capacity_register(value)
    return require_section72_physical_streaming_capacity_binding(value)


def require_section72_physical_streaming_capacity_binding(
    value: Section72PhysicalStreamingCapacityBinding,
) -> Section72PhysicalStreamingCapacityBinding:
    """Authenticate the distinct non-reviewed section-72 hard-cap authority."""

    _require_dependencies()
    if type(value) is not Section72PhysicalStreamingCapacityBinding:
        raise PhysicalStreamingScoringError(
            "section-72 physical capacity changed type"
        )
    current = _section72_capacity_current(value)
    if current is None:
        raise PhysicalStreamingScoringError(
            "section-72 physical capacity lacks builder authority"
        )
    record, topology, index, archive, receipt = current
    try:
        index = _index.require_formal_physical_production_session_index(index)
        archive = _prereview.require_preopen_control_prereview_archive(archive)
        checked = _legacy._checked_limits(dict(SECTION72_PHYSICAL_CAPACITY_LIMITS))
    except (AttributeError, TypeError, ValueError, OSError) as exc:
        raise PhysicalStreamingScoringError(
            "section-72 physical capacity retained parent changed"
        ) from exc
    digest = sha256_bytes(canonical_json_bytes(value.to_record()))
    if (
        value.physical_index is not index
        or value.preopen_acquisition_receipt is not archive
        or value.production_evidence_receipt is not receipt
        or receipt is not index.production_evidence_receipt
        or receipt.preopen_acquisition_receipt is not archive
        or record != canonical_json_bytes(value.to_record())
        or topology != _section72_capacity_topology(value)
        or value.receipt_sha256 != digest
        or value.receipt_id
        != f"arv2-section72-physical-capacity-{digest[:24]}"
        or value.schema != SECTION72_PHYSICAL_CAPACITY_SCHEMA
        or value.limits != checked
        or value.review_mode
        != _physical_acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE
        or value.capacity_authority_mode
        != SECTION72_PHYSICAL_CAPACITY_AUTHORITY_MODE
        or value.owner_waiver_scope != index.owner_waiver_scope
        or value.independently_reviewed is not False
        or value.owner_review_waived is not True
        or value.historical_availability_claimed is not False
        or value.post_first_formal_backtest_independent_review_required is not True
        or value.outcome_or_qc_action_authorized is not False
    ):
        raise PhysicalStreamingScoringError(
            "section-72 physical capacity changed after sealing"
        )
    return value


def require_physical_streaming_scoring_capacity(value: object) -> object:
    """Authenticate either the reviewed capacity or distinct waiver authority."""

    if type(value) is Section72PhysicalStreamingCapacityBinding:
        return require_section72_physical_streaming_capacity_binding(value)
    try:
        return _legacy.require_formal_streaming_capacity_binding(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise PhysicalStreamingScoringError(
            "physical streaming scoring capacity did not authenticate"
        ) from exc


def _capacity_for_parents(
    *,
    index: PhysicalProductionSessionIndex,
    archive: object,
    permit_fixture: bool,
) -> object:
    if (
        not permit_fixture
        and index.review_mode
        == _physical_acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE
    ):
        return _build_section72_capacity(index=index, archive=archive)
    return _legacy.require_formal_streaming_capacity_binding(archive.capacity)


def _parent_lineage_record(
    *,
    index: PhysicalProductionSessionIndex,
    archive: object,
    capacity: object,
    contract: GlobalBenchmarkContract,
) -> dict[str, object]:
    """Project the exact physical parents without changing the legacy artifact."""

    evidence = capacity.production_evidence_receipt
    archive_id, archive_sha256, terminal_parent_kind = (
        _terminal_parent_identity(archive)
    )
    preopen = _terminal_preopen_parent(archive)
    preopen_id = getattr(preopen, "artifact_id", None)
    preopen_sha256 = getattr(preopen, "artifact_sha256", None)
    if preopen_id is None and preopen_sha256 is None:
        preopen_id = getattr(preopen, "capture_id", None)
        preopen_sha256 = getattr(preopen, "capture_sha256", None)
    if type(preopen_id) is not str or type(preopen_sha256) is not str:
        raise PhysicalStreamingScoringError(
            "physical scoring preopen lineage changed"
        )
    return {
        "schema": PHYSICAL_SCORING_LINEAGE_SCHEMA,
        "index_id": index.index_id,
        "index_sha256": index.index_sha256,
        "physical_production_evidence_receipt_id": (
            index.production_evidence_receipt_id
        ),
        "physical_production_evidence_receipt_sha256": (
            index.production_evidence_receipt_sha256
        ),
        "production_input_archive_id": index.production_input_archive_id,
        "production_input_archive_sha256": (
            index.production_input_archive_sha256
        ),
        "accepted_risk_binding_sha256": index.accepted_risk_binding_sha256,
        "terminal_archive_id": archive_id,
        "terminal_archive_sha256": archive_sha256,
        "preopen_acquisition_id": preopen_id,
        "preopen_acquisition_sha256": preopen_sha256,
        "capacity_receipt_id": capacity.receipt_id,
        "capacity_receipt_sha256": capacity.receipt_sha256,
        "production_evidence_receipt_id": evidence.receipt_id,
        "production_evidence_receipt_sha256": evidence.receipt_sha256,
        "global_map_id": contract.map_id,
        "global_map_sha256": contract.map_hash,
        "session_count": index.session_count,
        "current_row_count": index.current_row_count,
        "censored_row_count": index.censored_row_count,
        "review_mode": index.review_mode,
        "terminal_parent_kind": terminal_parent_kind,
        "capacity_authority_mode": getattr(
            capacity, "capacity_authority_mode", "independently_reviewed"
        ),
        "independently_reviewed": index.independently_reviewed,
        "owner_review_waived": index.owner_review_waived,
        "historical_availability_claimed": index.historical_availability_claimed,
        "post_first_formal_backtest_independent_review_required": (
            index.post_first_formal_backtest_independent_review_required
        ),
    }


def _production_parent_lineage(
    *,
    index: PhysicalProductionSessionIndex,
    archive: object,
    capacity: object,
    contract: GlobalBenchmarkContract,
) -> PhysicalStreamingScoringLineage:
    record = _parent_lineage_record(
        index=index,
        archive=archive,
        capacity=capacity,
        contract=contract,
    )
    accepted_risk_sha256 = record.pop("accepted_risk_binding_sha256")
    # The separate evidence receipt is transitively reauthenticated through both
    # parents.  It remains in the private comparison record but is redundant in
    # the intentionally narrow public lineage carrier.
    record.pop("production_evidence_receipt_id")
    record.pop("production_evidence_receipt_sha256")
    if type(accepted_risk_sha256) is not str:
        raise PhysicalStreamingScoringError(
            "physical scoring parent lacks a formal accepted-risk binding"
        )
    try:
        require_sha256(accepted_risk_sha256, "physical accepted-risk binding")
        value = PhysicalStreamingScoringLineage(
            **record,
            accepted_risk_binding_sha256=accepted_risk_sha256,
        )
    except (TypeError, ValueError) as exc:
        raise PhysicalStreamingScoringError(
            "physical scoring parent lineage changed"
        ) from exc
    return value


_PINNED_LOCALS += (
    (
        "Section72PhysicalStreamingCapacityBinding",
        Section72PhysicalStreamingCapacityBinding,
    ),
    ("PhysicalStreamingScoringLineage", PhysicalStreamingScoringLineage),
    (
        "PhysicalStreamingScoringCompositionContext",
        PhysicalStreamingScoringCompositionContext,
    ),
    ("PhysicalPowerCalibrationSessionBlock", PhysicalPowerCalibrationSessionBlock),
    ("PhysicalPowerCalibrationStream", PhysicalPowerCalibrationStream),
    ("_section72_capacity_register", _section72_capacity_register),
    ("_section72_capacity_current", _section72_capacity_current),
    ("_terminal_parent_identity", _terminal_parent_identity),
    ("_terminal_preopen_parent", _terminal_preopen_parent),
    ("_evidence_authority_matches", _evidence_authority_matches),
    ("_require_terminal_parent", _require_terminal_parent),
    ("_build_section72_capacity", _build_section72_capacity),
    (
        "require_section72_physical_streaming_capacity_binding",
        require_section72_physical_streaming_capacity_binding,
    ),
    (
        "require_physical_streaming_scoring_capacity",
        require_physical_streaming_scoring_capacity,
    ),
    ("_capacity_for_parents", _capacity_for_parents),
    ("_parent_lineage_record", _parent_lineage_record),
    ("_production_parent_lineage", _production_parent_lineage),
)


def _source_view(arm: SignalArm) -> str:
    if arm is SignalArm.CURRENT_VINTAGE:
        return CURRENT_VIEW_LABEL
    if arm is SignalArm.CONSERVATIVE_CENSORED:
        return CENSORED_VIEW_LABEL
    raise PhysicalStreamingScoringError("physical scorer has unknown signal arm")


def _arm_rank(arm: SignalArm) -> int:
    if type(arm) is not SignalArm:
        raise PhysicalStreamingScoringError("physical scorer arm changed type")
    return _ARM_ORDER.index(arm)


def _strict_payload(payload: bytes, name: str) -> dict[str, Any]:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_PHYSICAL_SCORING_RECORD_BYTES:
        raise PhysicalStreamingScoringCapacityError(f"{name} exceeded record capacity")
    try:
        value = strict_json_loads(decode_utf8(payload, name), name)
    except (TypeError, ValueError) as exc:
        raise PhysicalStreamingScoringError(f"{name} is not strict UTF-8 JSON") from exc
    if type(value) is not dict or canonical_json_bytes(value) != payload:
        raise PhysicalStreamingScoringError(f"{name} is not canonical")
    return value


def _sqlite_bytes(connection: sqlite3.Connection) -> int:
    try:
        pages = connection.execute("PRAGMA page_count").fetchone()[0]
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    except sqlite3.Error as exc:
        raise PhysicalStreamingScoringError("physical scoring spool size is unavailable") from exc
    if type(pages) is not int or type(page_size) is not int:
        raise PhysicalStreamingScoringError("physical scoring spool counters changed type")
    size = pages * page_size
    if size > MAX_PHYSICAL_SCORING_SPOOL_BYTES:
        raise PhysicalStreamingScoringCapacityError(
            "physical scoring spool exceeded fixed byte capacity"
        )
    return size


def _open_spool_builder(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=FILE")
        connection.execute("PRAGMA foreign_keys=ON")
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        maximum = MAX_PHYSICAL_SCORING_SPOOL_BYTES // page_size
        installed = connection.execute(f"PRAGMA max_page_count={maximum}").fetchone()[0]
        if installed != maximum:
            raise PhysicalStreamingScoringCapacityError(
                "physical scoring SQLite hard capacity was not installed"
            )
        for statement in _CREATE_DERIVED_SQL:
            connection.execute(statement)
    except BaseException:
        connection.close()
        raise
    os.chmod(path, 0o600)
    return connection


def _descriptor_fingerprint(descriptor: int) -> tuple[object, ...]:
    digest = hashlib.sha256()
    before = os.fstat(descriptor)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size <= 0
        or before.st_size > MAX_PHYSICAL_SCORING_SPOOL_BYTES
        or (os.name != "nt" and stat.S_IMODE(before.st_mode) != 0o600)
        or (hasattr(os, "getuid") and before.st_uid != os.getuid())
    ):
        raise PhysicalStreamingScoringError(
            "physical scoring spool is not bounded private regular file"
        )
    os.lseek(descriptor, 0, os.SEEK_SET)
    remaining = before.st_size
    while remaining:
        chunk = os.read(descriptor, min(1024 * 1024, remaining))
        if not chunk:
            raise PhysicalStreamingScoringError("physical scoring spool ended during authentication")
        digest.update(chunk)
        remaining -= len(chunk)
    if os.read(descriptor, 1):
        raise PhysicalStreamingScoringError("physical scoring spool grew during authentication")
    after = os.fstat(descriptor)
    names = (
        "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns",
        "st_mode", "st_uid", "st_nlink",
    )
    if any(getattr(before, name) != getattr(after, name) for name in names):
        raise PhysicalStreamingScoringError("physical scoring spool changed during authentication")
    return tuple(getattr(before, name) for name in names) + (digest.hexdigest(),)


def _file_fingerprint(path: Path) -> tuple[object, ...]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PhysicalStreamingScoringError("physical scoring spool is unavailable") from exc
    try:
        return _descriptor_fingerprint(descriptor)
    finally:
        os.close(descriptor)


def _open_spool_reader(state: _BuilderState) -> sqlite3.Connection:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(state.spool_path, flags)
        if _descriptor_fingerprint(descriptor) != state.spool_fingerprint:
            raise PhysicalStreamingScoringError("physical scoring spool changed")
        # Bind SQLite to the already-authenticated inode rather than reopening
        # its pathname.  A same-UID path replacement between authentication
        # and sqlite3.connect therefore cannot select a different database.
        connection = sqlite3.connect(
            f"file:/dev/fd/{descriptor}?mode=ro&immutable=1",
            uri=True,
            isolation_level=None,
        )
        # ``mode=ro&immutable=1`` makes the authenticated main database
        # unwritable.  Do not also enable ``query_only``: the bounded joins
        # below deliberately use connection-private TEMP tables so a large
        # security census never becomes one unbounded SQL parameter graph.
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA temp_store=FILE")
    except PhysicalStreamingScoringError:
        raise
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise PhysicalStreamingScoringError(
            "physical scoring spool could not be opened read-only"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return connection


def _scoring_ordinals(connection: sqlite3.Connection) -> dict[str, int]:
    """Rebuild the frozen scorer's full NYSE decay axis from bounded disk state."""

    try:
        count = connection.execute(
            "SELECT count(DISTINCT eligible_session) FROM contributions"
        ).fetchone()
        if (
            type(count) is not tuple
            or len(count) != 1
            or type(count[0]) is not int
            or not 0 <= count[0] <= len(FORMAL_SESSION_GEOMETRY)
        ):
            raise PhysicalStreamingScoringCapacityError(
                "physical eligible-session ordinal census exceeded capacity"
            )
        descriptors = tuple(
            _EligibleSessionDescriptor(eligible_session)
            for (eligible_session,) in connection.execute(
                "SELECT DISTINCT eligible_session FROM contributions "
                "ORDER BY eligible_session"
            )
        )
        if len(descriptors) != count[0] or any(
            type(item.eligible_session) is not str for item in descriptors
        ):
            raise PhysicalStreamingScoringError(
                "physical eligible-session ordinal census changed"
            )
        result = _legacy._stream_ordinals(descriptors)
    except PhysicalStreamingScoringError:
        raise
    except (sqlite3.Error, TypeError, ValueError) as exc:
        raise PhysicalStreamingScoringError(
            "physical scoring NYSE ordinal axis could not be rebuilt"
        ) from exc
    if (
        type(result) is not dict
        or any(
            type(key) is not str or type(value) is not int or value < 0
            for key, value in result.items()
        )
        or any(item not in result for item in FORMAL_SESSION_GEOMETRY)
        or any(item.eligible_session not in result for item in descriptors)
    ):
        raise PhysicalStreamingScoringError(
            "physical scoring NYSE ordinal axis changed"
        )
    return result


def _resolution(raw_label: str, contract: GlobalBenchmarkContract) -> tuple[_GlobalLabelResolution, object]:
    try:
        resolved = resolve_global_rating(contract, raw_label)
        status = _endpoint_status(resolved)
    except (GlobalBenchmarkContractError, FormalInputBundleError) as exc:
        raise PhysicalStreamingScoringError("global endpoint resolution failed") from exc
    canonical = resolved.canonical_label
    canonical_sha = _NO_CANONICAL_LABEL_SHA256 if canonical is None else _label_digest(canonical)
    if type(resolved) is GlobalRatingMapping:
        numerator = resolved.entry.score_numerator
        denominator = resolved.entry.score_denominator
    elif type(resolved) is GlobalRatingMappingRefusal:
        numerator = denominator = None
    else:  # pragma: no cover - pinned helper already refuses this type
        raise PhysicalStreamingScoringError("global endpoint resolver returned hostile type")
    value = _GlobalLabelResolution(
        raw_label=raw_label,
        raw_label_sha256=_label_digest(raw_label),
        canonical_label_sha256=canonical_sha,
        status=status,
        score_numerator=numerator,
        score_denominator=denominator,
    )
    return value, resolved


def _resolution_payload(value: _GlobalLabelResolution) -> bytes:
    return canonical_json_bytes(dataclasses.asdict(value))


def _decode_resolution(payload: bytes) -> _GlobalLabelResolution:
    raw = _strict_payload(payload, "physical global-label resolution")
    expected = {
        "raw_label", "raw_label_sha256", "canonical_label_sha256", "status",
        "score_numerator", "score_denominator",
    }
    if set(raw) != expected:
        raise PhysicalStreamingScoringError("physical global-label resolution fields changed")
    value = _GlobalLabelResolution(**raw)
    if (
        type(value.raw_label) is not str
        or value.raw_label_sha256 != _label_digest(value.raw_label)
        or value.status not in _ENDPOINT_STATUS_IDS
        or (value.status == "mapped")
        != (type(value.score_numerator) is int and type(value.score_denominator) is int and value.score_denominator > 0)
    ):
        raise PhysicalStreamingScoringError("physical global-label resolution changed")
    return value


def _firm_payload(item: _FirmBaselineContribution) -> bytes:
    return canonical_json_bytes(dataclasses.asdict(item))


def _decode_firm(payload: bytes) -> _FirmBaselineContribution:
    raw = _strict_payload(payload, "physical firm contribution")
    if set(raw) != {"security_id", "common_event_id", "eligible_session", "linked_c2_row_sha256s"}:
        raise PhysicalStreamingScoringError("physical firm contribution fields changed")
    raw["linked_c2_row_sha256s"] = tuple(raw["linked_c2_row_sha256s"])
    value = _FirmBaselineContribution(**raw)
    if (
        type(value.security_id) is not str
        or type(value.common_event_id) is not str
        or type(value.eligible_session) is not str
        or value.linked_c2_row_sha256s != tuple(sorted(set(value.linked_c2_row_sha256s)))
    ):
        raise PhysicalStreamingScoringError("physical firm contribution changed")
    for digest in value.linked_c2_row_sha256s:
        require_sha256(digest, "physical firm contribution row hash")
    return value


def _paired_payload(item: _DailyContribution) -> bytes:
    return canonical_json_bytes(
        {
            "representative_c2_row_sha256": item.representative_c2_row_sha256,
            "provider_event_id": item.provider_event_id,
            "security_id": item.security_id,
            "institution_id": item.institution_id,
            "common_event_id": item.common_event_id,
            "rating_action": item.rating_action,
            "publication_at_utc": item.publication_at_utc,
            "eligible_session": item.eligible_session,
            "firm_delta": [item.firm_delta.numerator, item.firm_delta.denominator],
            "global_delta": [item.global_delta.numerator, item.global_delta.denominator],
            "linked_c2_row_sha256s": list(item.linked_c2_row_sha256s),
        }
    )


def _decode_paired(payload: bytes) -> _DailyContribution:
    raw = _strict_payload(payload, "physical paired contribution")
    expected = {
        "representative_c2_row_sha256", "provider_event_id", "security_id",
        "institution_id", "common_event_id", "rating_action", "publication_at_utc",
        "eligible_session", "firm_delta", "global_delta", "linked_c2_row_sha256s",
    }
    if set(raw) != expected:
        raise PhysicalStreamingScoringError("physical paired contribution fields changed")
    try:
        firm = raw.pop("firm_delta")
        global_value = raw.pop("global_delta")
        raw["firm_delta"] = Fraction(*firm)
        raw["global_delta"] = Fraction(*global_value)
        raw["linked_c2_row_sha256s"] = tuple(raw["linked_c2_row_sha256s"])
        value = _DailyContribution(**raw)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise PhysicalStreamingScoringError("physical paired contribution changed") from exc
    if (
        value.rating_action not in {"upgrades", "downgrades"}
        or value.linked_c2_row_sha256s != tuple(sorted(set(value.linked_c2_row_sha256s)))
    ):
        raise PhysicalStreamingScoringError("physical paired contribution changed")
    return value


def _event_projection(connection: sqlite3.Connection) -> str:
    hasher = hashlib.sha256()
    hasher.update(b"[")
    count = 0
    try:
        rows = connection.execute(
            "SELECT payload FROM terminals ORDER BY "
            "CASE arm_rank WHEN 1 THEN 0 ELSE 1 END, row_sha256"
        )
        for (payload,) in rows:
            raw = bytes(payload)
            _strict_payload(raw, "physical event terminal")
            if count:
                hasher.update(b",")
            hasher.update(raw[:-1])
            count += 1
    except sqlite3.Error as exc:
        raise PhysicalStreamingScoringError("physical event projection failed") from exc
    hasher.update(b"]\n")
    return hasher.hexdigest()


def _verify_event_terminal(row: PhysicalProductionScoringRow, terminal: object) -> None:
    normalized = row.normalized_evidence.normalized_row
    evidence = row.normalized_evidence.evidence
    accepted = {
        item.security_id: item for item in getattr(terminal, "accepted", ())
    }
    refused = {
        item.security_id: item for item in getattr(terminal, "refused", ())
    }
    census = accepted.get(normalized.security_id)
    if census is None:
        reason = (
            FormalStreamingRefusalReason.C2_EVENT_TERMINAL_REFUSED
            if normalized.security_id in refused
            else FormalStreamingRefusalReason.C2_EVENT_TERMINAL_MISSING
        )
        raise FormalStreamingRunRefusal(
            reason, "an admitted physical C2 event lacks an accepted same-key terminal"
        )
    security = evidence.security
    sector = evidence.sector
    quality = evidence.q_data
    control = evidence.control
    if any(item is None for item in (security, sector, quality, control)):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.C2_EVENT_TERMINAL_MISMATCH,
            "an admitted physical C2 event lacks complete evidence",
        )
    if (
        census.issuer_id != normalized.issuer_id
        or census.share_class_id != normalized.share_class_id
        or census.listing_id != normalized.listing_id
        or census.historical_ticker != normalized.historical_ticker
        or census.sector_id != normalized.sector_id
        or census.industry_id != normalized.industry_id
        or census.q_data != normalized.q_data
        or census.identity_evidence_sha256 != normalized.identity_mapping_evidence_sha256
        or census.identity_available_at != security.available_at
        or census.classification_evidence_sha256 != normalized.sector_evidence_sha256
        or census.classification_available_at != sector.available_at
        or census.q_data_evidence_sha256 != normalized.q_data_evidence_sha256
        or census.q_data_available_at != quality.available_at
        or census.control_evidence_sha256 != normalized.control_evidence_sha256
        or census.control_available_at != control.available_at
        or census.control_vector_sha256 != normalized.control_vector_sha256
    ):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.C2_EVENT_TERMINAL_MISMATCH,
            "an admitted physical C2 event and same-key terminal disagree",
        )


def _derive_session_arm(
    *,
    connection: sqlite3.Connection,
    arm: SignalArm,
    rows: tuple[PhysicalProductionScoringRow, ...],
    terminal: object,
    contract: GlobalBenchmarkContract,
    ordinal_start: int,
) -> tuple[int, int, int, int]:
    """Persist one arm/session's exact firm, paired, label, and terminal census."""

    rank = _arm_rank(arm)
    groups: dict[tuple[str, str, str], list[PhysicalProductionScoringRow]] = defaultdict(list)
    resolution_cache: dict[str, tuple[_GlobalLabelResolution, object]] = {}
    for item in rows:
        if type(item) is not PhysicalProductionScoringRow:
            raise PhysicalStreamingScoringError("physical session yielded wrong scoring-row type")
        item.__post_init__()
        _verify_event_terminal(item, terminal)
        normalized = item.normalized_evidence.normalized_row
        groups[(normalized.institution_id, normalized.security_id, normalized.eligible_session)].append(item)

    derived_count = 0
    paired_count = 0
    firm_count = 0
    terminal_count = 0
    ordinal = ordinal_start
    for key in sorted(groups):
        group = groups[key]
        normalized_group = [item.normalized_evidence.normalized_row for item in group]
        row_resolutions: dict[
            str,
            tuple[
                tuple[_GlobalLabelResolution, object],
                tuple[_GlobalLabelResolution, object],
            ],
        ] = {}
        for item in group:
            normalized = item.normalized_evidence.normalized_row
            label = item.endpoint_label
            previous = resolution_cache.get(label.raw_previous_label)
            if previous is None:
                previous = _resolution(label.raw_previous_label, contract)
                resolution_cache[label.raw_previous_label] = previous
            current = resolution_cache.get(label.raw_current_label)
            if current is None:
                current = _resolution(label.raw_current_label, contract)
                resolution_cache[label.raw_current_label] = current
            row_resolutions[normalized.row_sha256] = (previous, current)
            connection.execute(
                "INSERT INTO labels VALUES (?, ?, ?, ?, ?)",
                (
                    rank,
                    normalized.row_sha256,
                    normalized.raw_action,
                    sqlite3.Binary(_resolution_payload(previous[0])),
                    sqlite3.Binary(_resolution_payload(current[0])),
                ),
            )
            derived_count += 1
        firm_linked = tuple(sorted(item.row_sha256 for item in normalized_group))
        firm_signatures = {
            (item.previous_score, item.current_score, item.common_event_id)
            for item in normalized_group
        }
        if len(firm_signatures) == 1:
            representative = min(
                normalized_group,
                key=lambda item: (item.provider_event_id, item.row_sha256),
            )
            firm = _FirmBaselineContribution(
                security_id=representative.security_id,
                common_event_id=representative.common_event_id,
                eligible_session=representative.eligible_session,
                linked_c2_row_sha256s=firm_linked,
            )
            payload = _firm_payload(firm)
            connection.execute(
                "INSERT INTO contributions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (0, rank, ordinal, firm.eligible_session, firm.security_id, "", firm.common_event_id, canonical_json_bytes(list(firm.linked_c2_row_sha256s)), sqlite3.Binary(payload)),
            )
            for digest in firm.linked_c2_row_sha256s:
                connection.execute(
                    "INSERT INTO firm_lineage VALUES (?, ?, ?, ?)",
                    (rank, firm.security_id, firm.eligible_session, digest),
                )
            ordinal += 1
            firm_count += 1
            derived_count += 1 + len(firm.linked_c2_row_sha256s)

        paired_firm_signatures = {
            (item.previous_score, item.current_score, item.common_event_id, item.raw_action)
            for item in normalized_group
        }
        terminals: dict[str, EventScoringTerminal] = {}
        paired_group: list[tuple[PhysicalProductionScoringRow, Fraction]] = []
        if len(paired_firm_signatures) != 1:
            for item in group:
                normalized = item.normalized_evidence.normalized_row
                terminals[normalized.row_sha256] = _terminal(
                    arm, normalized, ScoreDisposition.DAILY_DEDUPE_CONFLICT, firm_linked
                )
        else:
            for item in group:
                normalized = item.normalized_evidence.normalized_row
                previous, current = row_resolutions[normalized.row_sha256]
                if type(previous[1]) is GlobalRatingMappingRefusal or type(current[1]) is GlobalRatingMappingRefusal:
                    terminals[normalized.row_sha256] = _terminal(
                        arm, normalized, ScoreDisposition.GLOBAL_LABEL_REFUSED, (normalized.row_sha256,)
                    )
                    continue
                if type(previous[1]) is not GlobalRatingMapping or type(current[1]) is not GlobalRatingMapping:
                    raise PhysicalStreamingScoringError("global endpoint resolution changed type")
                delta = current[1].score - previous[1].score
                if (normalized.raw_action == "upgrades" and delta < 0) or (
                    normalized.raw_action == "downgrades" and delta > 0
                ):
                    terminals[normalized.row_sha256] = _terminal(
                        arm, normalized, ScoreDisposition.GLOBAL_DIRECTION_CONFLICT, (normalized.row_sha256,)
                    )
                else:
                    paired_group.append((item, delta))
            if paired_group:
                linked = tuple(sorted(item[0].normalized_evidence.normalized_row.row_sha256 for item in paired_group))
                signatures = {
                    (delta, item.normalized_evidence.normalized_row.common_event_id, item.normalized_evidence.normalized_row.raw_action)
                    for item, delta in paired_group
                }
                if len(signatures) != 1:
                    for item, _delta in paired_group:
                        normalized = item.normalized_evidence.normalized_row
                        terminals[normalized.row_sha256] = _terminal(
                            arm, normalized, ScoreDisposition.DAILY_DEDUPE_CONFLICT, linked
                        )
                else:
                    chosen, global_delta = min(
                        paired_group,
                        key=lambda pair: (
                            pair[0].normalized_evidence.normalized_row.provider_event_id,
                            pair[0].normalized_evidence.normalized_row.row_sha256,
                        ),
                    )
                    normalized = chosen.normalized_evidence.normalized_row
                    publication = (
                        None
                        if any(item.normalized_evidence.normalized_row.publication_at_utc is None for item, _ in paired_group)
                        else min(
                            item.normalized_evidence.normalized_row.publication_at_utc
                            for item, _ in paired_group
                            if item.normalized_evidence.normalized_row.publication_at_utc is not None
                        )
                    )
                    contribution = _DailyContribution(
                        representative_c2_row_sha256=normalized.row_sha256,
                        provider_event_id=normalized.provider_event_id,
                        security_id=normalized.security_id,
                        institution_id=normalized.institution_id,
                        common_event_id=normalized.common_event_id,
                        rating_action=normalized.raw_action,
                        publication_at_utc=publication,
                        eligible_session=normalized.eligible_session,
                        firm_delta=normalized.rating_change,
                        global_delta=global_delta,
                        linked_c2_row_sha256s=linked,
                    )
                    payload = _paired_payload(contribution)
                    connection.execute(
                        "INSERT INTO contributions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (1, rank, ordinal, contribution.eligible_session, contribution.security_id, contribution.institution_id, contribution.common_event_id, canonical_json_bytes(list(contribution.linked_c2_row_sha256s)), sqlite3.Binary(payload)),
                    )
                    ordinal += 1
                    paired_count += 1
                    derived_count += 1
                    for item, _delta in paired_group:
                        member = item.normalized_evidence.normalized_row
                        terminals[member.row_sha256] = _terminal(
                            arm, member, ScoreDisposition.INCLUDED_ACTIVE, linked
                        )

        if set(terminals) != {item.row_sha256 for item in normalized_group}:
            raise PhysicalStreamingScoringError("physical event scoring census is not exhaustive")
        for digest in sorted(terminals):
            payload = canonical_json_bytes(terminals[digest].to_record())
            connection.execute(
                "INSERT INTO terminals VALUES (?, ?, ?)",
                (rank, digest, sqlite3.Binary(payload)),
            )
            terminal_count += 1
            derived_count += 1
    if terminal_count != len(rows):
        raise PhysicalStreamingScoringError("physical event terminal count changed")
    return ordinal, firm_count, paired_count, derived_count


def _spool_metadata(
    *,
    index: PhysicalProductionSessionIndex,
    archive: object,
    capacity: object,
    contract: GlobalBenchmarkContract,
    batches: tuple[object, object],
    event_projection: str,
    session_count: int,
    event_counts: tuple[int, int],
    firm_counts: tuple[int, int],
    paired_counts: tuple[int, int],
) -> dict[str, object]:
    archive_id, archive_sha256, _kind = _terminal_parent_identity(archive)
    return {
        "schema": PHYSICAL_SCORING_SPOOL_SCHEMA,
        "index_id": index.index_id,
        "index_sha256": index.index_sha256,
        "archive_id": archive_id,
        "archive_sha256": archive_sha256,
        "physical_production_evidence_receipt_id": index.production_evidence_receipt_id,
        "physical_production_evidence_receipt_sha256": index.production_evidence_receipt_sha256,
        "production_evidence_receipt_id": (
            capacity.production_evidence_receipt.receipt_id
        ),
        "production_evidence_receipt_sha256": (
            capacity.production_evidence_receipt.receipt_sha256
        ),
        "global_map_id": contract.map_id,
        "global_map_sha256": contract.map_hash,
        "current_batch_id": batches[0].batch_id,
        "current_batch_sha256": batches[0].batch_sha256,
        "censored_batch_id": batches[1].batch_id,
        "censored_batch_sha256": batches[1].batch_sha256,
        "formal_session_geometry_sha256": FORMAL_SESSION_GEOMETRY_SHA256,
        "event_terminal_projection_sha256": event_projection,
        "session_count": session_count,
        "event_counts": list(event_counts),
        "firm_contribution_counts": list(firm_counts),
        "paired_contribution_counts": list(paired_counts),
        "method_id": STREAMING_METHOD_ID,
    }


def _cleanup_spool(directory: Path) -> None:
    try:
        shutil.rmtree(directory)
    except FileNotFoundError:
        pass


def _build_spool(
    *,
    index: PhysicalProductionSessionIndex,
    archive: object,
    capacity: object,
    contract: GlobalBenchmarkContract,
    batches: tuple[object, object],
    permit_fixture: bool,
) -> tuple[Path, Path, tuple[object, ...], str, tuple[int, int], tuple[int, int]]:
    directory = Path(tempfile.mkdtemp(prefix="arv2-physical-scoring-"))
    os.chmod(directory, 0o700)
    path = directory / "derived.sqlite3"
    connection: sqlite3.Connection | None = None
    try:
        connection = _open_spool_builder(path)
        connection.execute("BEGIN")
        iterator = (
            _index._iter_test_fixture_physical_production_scoring_session_inputs(index, archive)
            if permit_fixture
            else _index.iter_physical_production_scoring_session_inputs(index, archive)
        )
        event_counts = [0, 0]
        firm_counts = [0, 0]
        paired_counts = [0, 0]
        derived_rows = 0
        ordinal = 0
        session_count = 0
        for position, session_input in enumerate(iterator):
            _require_dependencies()
            if type(session_input) is not PhysicalProductionScoringSessionInput:
                raise PhysicalStreamingScoringError("physical scorer input changed type")
            if position >= len(FORMAL_SESSION_GEOMETRY) or session_input.decision_session != FORMAL_SESSION_GEOMETRY[position]:
                raise PhysicalStreamingScoringError("physical scorer session geometry changed")
            if session_input.input_sha256 != sha256_bytes(canonical_json_bytes(session_input.to_record())):
                raise PhysicalStreamingScoringError("physical scorer session input hash changed")
            connection.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                (
                    session_input.decision_session,
                    session_input.input_sha256,
                    session_input.terminal_block.terminal_count,
                    len(session_input.current_event_rows),
                    len(session_input.censored_event_rows),
                ),
            )
            for rank, (arm, rows) in enumerate(zip(
                _ARM_ORDER,
                (session_input.current_event_rows, session_input.censored_event_rows),
                strict=True,
            )):
                ordinal, firm_count, paired_count, generated = _derive_session_arm(
                    connection=connection,
                    arm=arm,
                    rows=rows,
                    terminal=session_input.terminal_block,
                    contract=contract,
                    ordinal_start=ordinal,
                )
                event_counts[rank] += len(rows)
                firm_counts[rank] += firm_count
                paired_counts[rank] += paired_count
                derived_rows += generated
            session_count += 1
            if derived_rows > MAX_PHYSICAL_SCORING_DERIVED_ROWS:
                raise PhysicalStreamingScoringCapacityError(
                    "physical scoring derived row census exceeded capacity"
                )
            if session_count % SPOOL_CAPACITY_CHECK_INTERVAL == 0:
                _sqlite_bytes(connection)
        if session_count != len(FORMAL_SESSION_GEOMETRY):
            raise PhysicalStreamingScoringError("physical scorer did not exhaust formal session geometry")
        if tuple(event_counts) != (index.current_row_count, index.censored_row_count):
            raise PhysicalStreamingScoringError("physical scorer event census differs from index")
        projection = _event_projection(connection)
        metadata = _spool_metadata(
            index=index,
            archive=archive,
            capacity=capacity,
            contract=contract,
            batches=batches,
            event_projection=projection,
            session_count=session_count,
            event_counts=tuple(event_counts),
            firm_counts=tuple(firm_counts),
            paired_counts=tuple(paired_counts),
        )
        connection.execute(
            "INSERT INTO metadata VALUES ('authority', ?)",
            (sqlite3.Binary(canonical_json_bytes(metadata)),),
        )
        connection.execute("COMMIT")
        _sqlite_bytes(connection)
        connection.execute("PRAGMA optimize")
        connection.close()
        connection = None
        fingerprint = _file_fingerprint(path)
        return directory, path, fingerprint, projection, tuple(firm_counts), tuple(paired_counts)
    except BaseException:
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass
        _cleanup_spool(directory)
        raise


def _builder_static(value: PhysicalStreamedProductionScoringBuilder) -> bytes:
    return canonical_json_bytes(
        {"builder_id": value.builder_id, "schema": value.schema}
    )


def _state_authority(state: _BuilderState) -> tuple[object, ...]:
    if (
        type(state) is not _BuilderState
        or type(state.fold_commitments) is not tuple
        or any(type(item) is not StreamedFoldCommitment for item in state.fold_commitments)
        or len(state.fold_commitments) != state.next_fold_index
        or not 0 <= state.next_fold_index <= len(FORMAL_PRIMARY_FOLD_IDS)
        or type(state.observed) is not tuple
        or state.observed != tuple(sorted(state.observed))
        or any(type(item) is not tuple or len(item) != 2 for item in state.observed)
        or any(type(name) is not str or type(value) is not int or value < 0 for name, value in state.observed)
        or type(state.active_fold) is not bool
        or type(state.finalized) is not bool
        or type(state.fixture_only) is not bool
        or (state.active_fold and state.finalized)
        or type(state.pid) is not int
        or type(state.owner_thread_id) is not int
    ):
        raise PhysicalStreamingScoringError("physical scoring builder state changed")
    require_sha256(state.event_terminal_projection_sha256, "physical event projection")
    require_sha256(state.matched_test_terminal_sha256, "physical matched-terminal root")
    return (
        id(state.index), id(state.archive), id(state.capacity),
        id(state.global_contract),
        id(state.spool_directory), id(state.spool_path), id(state.spool_fingerprint),
        state.spool_fingerprint,
        state.current_batch_id, state.current_batch_sha256,
        state.censored_batch_id, state.censored_batch_sha256,
        state.event_terminal_projection_sha256,
        state.base_retained_input_graph_bytes,
        state.next_fold_index,
        id(state.fold_commitments),
        canonical_json_bytes([item.to_record() for item in state.fold_commitments]),
        state.matched_test_terminal_count, state.matched_test_terminal_sha256,
        id(state.observed), state.observed,
        state.active_fold, state.finalized, state.fixture_only,
        state.pid, state.owner_thread_id,
    )


def _artifact_topology(value: StreamedProductionScoringArtifact) -> tuple[object, ...]:
    return (
        id(value.global_contract),
        id(value.result_bindings),
        tuple(id(item) for item in value.result_bindings),
        id(value.fold_commitments),
        tuple(id(item) for item in value.fold_commitments),
        tuple(
            id(coverage)
            for commitment in value.fold_commitments
            for coverage in commitment.global_comparator_coverages
        ),
        id(value.pooled_global_comparator_coverages),
        tuple(id(item) for item in value.pooled_global_comparator_coverages),
        id(value.observed_capacity),
    )


def _power_stream_topology(
    value: PhysicalPowerCalibrationStream,
) -> tuple[object, ...]:
    return (
        id(value.physical_index),
        id(value.terminal_archive),
        id(value.capacity),
        id(value.global_contract),
        id(value.accepted_risk_binding),
        id(value.model),
        id(value.model.columns),
        id(value.model.industry_levels),
        id(value.model.firm_coefficients),
        id(value.model.global_coefficients),
        id(value.calibration_fold_geometry),
        id(value.observed_capacity),
    )


def _make_authority_vault():
    builders: dict[
        int,
        tuple[
            weakref.ReferenceType[PhysicalStreamedProductionScoringBuilder],
            bytes,
            _BuilderState,
            tuple[object, ...],
            object | None,
            str | None,
        ],
    ] = {}
    artifacts: dict[
        int,
        tuple[
            tuple[
                weakref.ReferenceType[StreamedProductionScoringArtifact],
                bytes,
                tuple[object, ...],
                bool,
                int,
            ],
            PhysicalProductionSessionIndex,
            object,
            object,
            GlobalBenchmarkContract,
            bytes,
        ],
    ] = {}
    power_streams: dict[
        int,
        tuple[
            tuple[
                weakref.ReferenceType[PhysicalPowerCalibrationStream],
                bytes,
                tuple[object, ...],
                bool,
                int,
            ],
            PhysicalProductionSessionIndex,
            object,
            object,
            GlobalBenchmarkContract,
            object | None,
            StreamedControlModel,
            bytes,
            bytes,
        ],
    ] = {}

    def revoke_locked(identity: int, *, cleanup: bool = True) -> None:
        entry = builders.pop(identity, None)
        _BUILDERS.pop(identity, None)
        if cleanup and entry is not None and entry[2].pid == os.getpid():
            _cleanup_spool(entry[2].spool_directory)

    def forget_builder(identity: int, reference: object) -> None:
        with _LOCK:
            entry = builders.get(identity)
            if entry is not None and entry[0] is reference:
                revoke_locked(identity)

    def forget_artifact(identity: int, reference: object) -> None:
        with _LOCK:
            entry = artifacts.get(identity)
            if entry is not None and entry[0][0] is reference:
                artifacts.pop(identity, None)
                if _ARTIFACTS.get(identity) is entry[0]:
                    _ARTIFACTS.pop(identity, None)

    def forget_power_stream(identity: int, reference: object) -> None:
        with _LOCK:
            entry = power_streams.get(identity)
            if entry is not None and entry[0][0] is reference:
                power_streams.pop(identity, None)
                if _POWER_STREAMS.get(identity) is entry[0]:
                    _POWER_STREAMS.pop(identity, None)

    def current_locked(
        value: PhysicalStreamedProductionScoringBuilder,
    ) -> tuple[_BuilderState, object | None, str | None] | None:
        identity = id(value)
        private = builders.get(identity)
        public = _BUILDERS.get(identity)
        try:
            valid = (
                private is not None
                and public is not None
                and len(public) == 5
                and private[0]() is value
                and public[0]() is value
                and private[1] == public[1] == _builder_static(value)
                and private[2] is public[2]
                and private[3] == public[3] == _state_authority(private[2])
                and private[5] == public[4]
                and private[2].active_fold == (private[4] is not None)
                and private[2].active_fold == (private[5] is not None)
                and private[2].pid == os.getpid()
                and private[2].owner_thread_id == threading.get_ident()
            )
        except (AttributeError, TypeError, ValueError, IndexError):
            valid = False
        if not valid:
            revoke_locked(identity)
            return None
        assert private is not None
        return private[2], private[4], private[5]

    def store_locked(
        value: PhysicalStreamedProductionScoringBuilder,
        state: _BuilderState,
        lease: object | None,
        purpose: str | None,
    ) -> None:
        prior = builders[id(value)]
        authority = _state_authority(state)
        private = (prior[0], prior[1], state, authority, lease, purpose)
        builders[id(value)] = private
        _BUILDERS[id(value)] = (prior[0], prior[1], state, authority, purpose)

    def initialize(
        value: PhysicalStreamedProductionScoringBuilder,
        state: _BuilderState,
    ) -> None:
        identity = id(value)
        reference = weakref.ref(
            value, lambda ref, key=identity: forget_builder(key, ref)
        )
        static = _builder_static(value)
        private = (reference, static, state, _state_authority(state), None, None)
        with _LOCK:
            if identity in builders or identity in _BUILDERS:
                raise PhysicalStreamingScoringError("physical scoring builder identity reused")
            builders[identity] = private
            _BUILDERS[identity] = (reference, static, state, private[3], None)

    def require(value: PhysicalStreamedProductionScoringBuilder) -> _BuilderState:
        with _LOCK:
            current = current_locked(value)
            if current is None:
                raise PhysicalStreamingScoringError(
                    "physical scoring builder is not builder-authenticated"
                )
            return current[0]

    def acquire(
        value: PhysicalStreamedProductionScoringBuilder, purpose: str
    ) -> tuple[_BuilderState, object]:
        if type(purpose) is not str or not purpose:
            raise PhysicalStreamingScoringError("physical scoring lease purpose changed")
        with _LOCK:
            current = current_locked(value)
            if current is None or current[1] is not None:
                raise PhysicalStreamingScoringError("physical scoring builder is busy or invalid")
            state = dataclasses.replace(current[0], active_fold=True)
            lease = object()
            store_locked(value, state, lease, purpose)
            return state, lease

    def require_lease(
        value: PhysicalStreamedProductionScoringBuilder,
        lease: object,
        purpose: str,
    ) -> _BuilderState:
        with _LOCK:
            current = current_locked(value)
            if current is None or current[1] is not lease or current[2] != purpose:
                raise PhysicalStreamingScoringError("physical scoring lease or state changed")
            return current[0]

    def commit_block(
        value: PhysicalStreamedProductionScoringBuilder,
        lease: object,
        block: StreamedTestSessionBlock,
    ) -> _BuilderState:
        state = require_lease(value, lease, "formal_fold")
        if type(block) is not StreamedTestSessionBlock:
            raise PhysicalStreamingScoringError("physical scoring block changed type")
        state = dataclasses.replace(
            state,
            matched_test_terminal_count=(
                state.matched_test_terminal_count + block.matched_terminal_count
            ),
            matched_test_terminal_sha256=_rolling_chain_update(
                state.matched_test_terminal_sha256,
                {
                    "fold_id": block.fold_id,
                    "decision_session": block.decision_session.isoformat(),
                    "matched_terminal_sha256": block.matched_terminal_sha256,
                },
            ),
        )
        with _LOCK:
            current = current_locked(value)
            if current is None or current[1] is not lease:
                raise PhysicalStreamingScoringError("physical scoring state changed during block")
            store_locked(value, state, lease, "formal_fold")
        return state

    def commit_fold(
        value: PhysicalStreamedProductionScoringBuilder,
        lease: object,
        commitment: StreamedFoldCommitment,
        observed: Mapping[str, int],
    ) -> _BuilderState:
        state = require_lease(value, lease, "formal_fold")
        expected = FORMAL_PRIMARY_FOLD_IDS[state.next_fold_index]
        if type(commitment) is not StreamedFoldCommitment or commitment.fold_id != expected:
            raise PhysicalStreamingScoringError("physical scoring fold order changed")
        state = dataclasses.replace(
            state,
            next_fold_index=state.next_fold_index + 1,
            fold_commitments=(*state.fold_commitments, commitment),
            observed=tuple(sorted(observed.items())),
            active_fold=False,
        )
        with _LOCK:
            current = current_locked(value)
            if current is None or current[1] is not lease:
                raise PhysicalStreamingScoringError("physical scoring state changed during fold")
            store_locked(value, state, None, None)
        return state

    def revoke(value: PhysicalStreamedProductionScoringBuilder) -> None:
        with _LOCK:
            revoke_locked(id(value))

    def finalize(
        value: PhysicalStreamedProductionScoringBuilder,
        artifact: StreamedProductionScoringArtifact,
    ) -> None:
        with _LOCK:
            current = current_locked(value)
            if current is None or current[1] is not None:
                raise PhysicalStreamingScoringError("physical scoring builder is busy or invalid")
            state = current[0]
            if state.finalized or state.next_fold_index != len(FORMAL_PRIMARY_FOLD_IDS):
                raise PhysicalStreamingScoringError("physical scoring builder is incomplete")
            record = canonical_json_bytes(artifact.to_record())
            topology = _artifact_topology(artifact)
            identity = id(artifact)
            reference = weakref.ref(
                artifact, lambda ref, key=identity: forget_artifact(key, ref)
            )
            public = (
                reference, record, topology, state.fixture_only, os.getpid(),
            )
            lineage = canonical_json_bytes(_parent_lineage_record(
                index=state.index,
                archive=state.archive,
                capacity=state.capacity,
                contract=state.global_contract,
            ))
            if identity in artifacts or identity in _ARTIFACTS:
                raise PhysicalStreamingScoringError("physical scoring artifact identity reused")
            artifacts[identity] = (
                public,
                state.index,
                state.archive,
                state.capacity,
                state.global_contract,
                lineage,
            )
            _ARTIFACTS[identity] = public
            revoke_locked(id(value))

    def artifact_current(
        value: StreamedProductionScoringArtifact,
    ) -> tuple[
        bytes,
        tuple[object, ...],
        bool,
        PhysicalProductionSessionIndex,
        object,
        object,
        GlobalBenchmarkContract,
        bytes,
    ] | None:
        with _LOCK:
            private = artifacts.get(id(value))
            public = _ARTIFACTS.get(id(value))
            if (
                private is None
                or public is not private[0]
                or private[0][0]() is not value
                or private[0][4] != os.getpid()
            ):
                artifacts.pop(id(value), None)
                _ARTIFACTS.pop(id(value), None)
                return None
            return (
                private[0][1],
                private[0][2],
                private[0][3],
                private[1],
                private[2],
                private[3],
                private[4],
                private[5],
            )

    def finalize_power_stream(
        builder: PhysicalStreamedProductionScoringBuilder,
        lease: object,
        value: PhysicalPowerCalibrationStream,
    ) -> None:
        with _LOCK:
            current = current_locked(builder)
            if (
                current is None
                or current[1] is not lease
                or current[2] != "power_calibration"
            ):
                raise PhysicalStreamingScoringError(
                    "physical power-calibration scorer lease changed"
                )
            state = current[0]
            if (
                state.finalized
                or state.next_fold_index != 0
                or not state.active_fold
                or type(value) is not PhysicalPowerCalibrationStream
            ):
                raise PhysicalStreamingScoringError(
                    "physical power-calibration scorer is not fresh"
                )
            record = canonical_json_bytes(value.to_record())
            topology = _power_stream_topology(value)
            identity = id(value)
            reference = weakref.ref(
                value, lambda ref, key=identity: forget_power_stream(key, ref)
            )
            public = (
                reference,
                record,
                topology,
                state.fixture_only,
                os.getpid(),
            )
            if identity in power_streams or identity in _POWER_STREAMS:
                raise PhysicalStreamingScoringError(
                    "physical power-calibration stream identity reused"
                )
            power_streams[identity] = (
                public,
                state.index,
                state.archive,
                state.capacity,
                state.global_contract,
                state.index.accepted_risk_binding,
                value.model,
                canonical_json_bytes(
                    _parent_lineage_record(
                        index=state.index,
                        archive=state.archive,
                        capacity=state.capacity,
                        contract=state.global_contract,
                    )
                ),
                canonical_json_bytes(value.model.to_record()),
            )
            _POWER_STREAMS[identity] = public
            revoke_locked(id(builder))

    def power_stream_current(
        value: PhysicalPowerCalibrationStream,
    ) -> tuple[
        bytes,
        tuple[object, ...],
        bool,
        PhysicalProductionSessionIndex,
        object,
        object,
        GlobalBenchmarkContract,
        object | None,
        StreamedControlModel,
        bytes,
        bytes,
    ] | None:
        with _LOCK:
            private = power_streams.get(id(value))
            public = _POWER_STREAMS.get(id(value))
            if (
                private is None
                or public is not private[0]
                or private[0][0]() is not value
                or private[0][4] != os.getpid()
            ):
                power_streams.pop(id(value), None)
                _POWER_STREAMS.pop(id(value), None)
                return None
            return (
                private[0][1],
                private[0][2],
                private[0][3],
                private[1],
                private[2],
                private[3],
                private[4],
                private[5],
                private[6],
                private[7],
                private[8],
            )

    def reset_after_fork() -> None:
        global _BUILDERS, _ARTIFACTS, _POWER_STREAMS, _LOCK
        builders.clear()
        artifacts.clear()
        power_streams.clear()
        _BUILDERS = {}
        _ARTIFACTS = {}
        _POWER_STREAMS = {}
        _LOCK = threading.RLock()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)
    return (
        initialize,
        require,
        acquire,
        require_lease,
        commit_block,
        commit_fold,
        revoke,
        finalize,
        artifact_current,
        finalize_power_stream,
        power_stream_current,
    )


(
    _vault_initialize,
    _vault_require,
    _vault_acquire,
    _vault_require_lease,
    _vault_commit_block,
    _vault_commit_fold,
    _vault_revoke,
    _vault_finalize,
    _vault_artifact_current,
    _vault_finalize_power_stream,
    _vault_power_stream_current,
) = _make_authority_vault()
del _make_authority_vault


def _begin(
    *,
    index: PhysicalProductionSessionIndex,
    archive: object,
    global_contract: GlobalBenchmarkContract,
    permit_fixture: bool,
) -> PhysicalStreamedProductionScoringBuilder:
    _require_dependencies()
    try:
        index = (
            _index.require_physical_production_session_index(index)
            if permit_fixture
            else _index.require_formal_physical_production_session_index(index)
        )
        archive = _require_terminal_parent(
            index, archive, permit_fixture=permit_fixture
        )
        capacity = _capacity_for_parents(
            index=index,
            archive=archive,
            permit_fixture=permit_fixture,
        )
        contract = require_loaded_global_benchmark_contract(global_contract)
    except (AttributeError, TypeError, ValueError) as exc:
        raise PhysicalStreamingScoringError(
            "physical streaming scorer parents did not authenticate"
        ) from exc
    if index.fixture_only is not permit_fixture:
        raise PhysicalStreamingScoringError("physical streaming scorer fixture eligibility changed")
    if (
        index.session_count != len(FORMAL_SESSION_GEOMETRY)
        or tuple(index.production_evidence_receipt.session_axis)
        != FORMAL_SESSION_GEOMETRY
    ):
        raise PhysicalStreamingScoringError("physical scorer session geometry is not exact 2013-2025")
    try:
        batches = tuple(
            _c2.physical_production_batch(
                index.production_evidence_receipt.production_input_archive, arm
            )
            for arm in _ARM_ORDER
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise PhysicalStreamingScoringError("physical scorer C2 batches did not authenticate") from exc
    if (
        batches[0].normalized_row_count != index.current_row_count
        or batches[1].normalized_row_count != index.censored_row_count
    ):
        raise PhysicalStreamingScoringError("physical scorer batch and index censuses differ")
    evidence = capacity.production_evidence_receipt
    if not _evidence_authority_matches(index, evidence):
        raise PhysicalStreamingScoringError(
            "physical scorer C2 and formal evidence authorities differ"
        )
    directory, path, fingerprint, projection, firm_counts, paired_counts = _build_spool(
        index=index,
        archive=archive,
        capacity=capacity,
        contract=contract,
        batches=batches,
        permit_fixture=permit_fixture,
    )
    try:
        base_bytes = (
            sum(
                sys.getsizeof(item)
                for item in (
                    index, archive, capacity, contract, batches,
                    FORMAL_SESSION_GEOMETRY,
                    directory, path, fingerprint,
                )
            )
            if permit_fixture
            else _retained_object_graph_bytes(
                index,
                archive,
                capacity,
                contract,
                batches,
                FORMAL_SESSION_GEOMETRY,
                directory,
                path,
                fingerprint,
            )
        )
        limit = dict(capacity.limits)["max_retained_input_graph_bytes"]
        if base_bytes > limit:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED,
                "physical scorer retained parent graph exceeded reviewed capacity",
            )
        seed = {
            "schema": PHYSICAL_SCORING_BUILDER_SCHEMA,
            "index_id": index.index_id,
            "index_sha256": index.index_sha256,
            "archive_id": _terminal_parent_identity(archive)[0],
            "archive_sha256": _terminal_parent_identity(archive)[1],
            "physical_production_evidence_receipt_id": index.production_evidence_receipt_id,
            "physical_production_evidence_receipt_sha256": index.production_evidence_receipt_sha256,
            "production_evidence_receipt_id": evidence.receipt_id,
            "production_evidence_receipt_sha256": evidence.receipt_sha256,
            "current_batch_id": batches[0].batch_id,
            "current_batch_sha256": batches[0].batch_sha256,
            "censored_batch_id": batches[1].batch_id,
            "censored_batch_sha256": batches[1].batch_sha256,
            "global_map_id": contract.map_id,
            "global_map_sha256": contract.map_hash,
            "event_terminal_projection_sha256": projection,
            "method_id": STREAMING_METHOD_ID,
        }
        digest = sha256_bytes(canonical_json_bytes(seed))
        value = object.__new__(PhysicalStreamedProductionScoringBuilder)
        object.__setattr__(value, "builder_id", f"arv2-physical-streamed-scoring-builder-{digest[:24]}")
        object.__setattr__(value, "schema", PHYSICAL_SCORING_BUILDER_SCHEMA)
        observed = {
            "maximum_physical_session_terminal_count": 0,
            "maximum_physical_session_uncompressed_bytes": 0,
            "maximum_active_contribution_count_per_arm_session": 0,
            "maximum_session_contribution_lineage_count": 0,
            "maximum_industry_level_count_per_arm_fold": 0,
            "maximum_disk_mgs_width": 0,
            "maximum_disk_mgs_live_decimal_count": 0,
            "maximum_disk_mgs_spool_row_count": 0,
            "maximum_disk_mgs_spool_byte_count": 0,
            "maximum_disk_mgs_spool_file_count": 0,
            "maximum_test_session_terminal_count_per_arm": 0,
            "retained_input_graph_bytes": base_bytes,
        }
        state = _BuilderState(
            index=index,
            archive=archive,
            capacity=capacity,
            global_contract=contract,
            spool_directory=directory,
            spool_path=path,
            spool_fingerprint=fingerprint,
            current_batch_id=batches[0].batch_id,
            current_batch_sha256=batches[0].batch_sha256,
            censored_batch_id=batches[1].batch_id,
            censored_batch_sha256=batches[1].batch_sha256,
            event_terminal_projection_sha256=projection,
            base_retained_input_graph_bytes=base_bytes,
            next_fold_index=0,
            fold_commitments=(),
            matched_test_terminal_count=0,
            matched_test_terminal_sha256=_rolling_chain_seed(
                "arv2-streamed-matched-test-terminal-census-v1"
            ),
            observed=tuple(sorted(observed.items())),
            active_fold=False,
            finalized=False,
            fixture_only=permit_fixture,
            pid=os.getpid(),
            owner_thread_id=threading.get_ident(),
        )
        _vault_initialize(value, state)
        return require_physical_streamed_production_scoring_builder(value)
    except BaseException:
        _cleanup_spool(directory)
        raise


def begin_physical_streaming_scoring(
    *,
    index: PhysicalProductionSessionIndex,
    archive: object,
    global_contract: GlobalBenchmarkContract,
) -> PhysicalStreamedProductionScoringBuilder:
    """Open the production physical scorer from reviewed parents only."""

    return _begin(
        index=index,
        archive=archive,
        global_contract=global_contract,
        permit_fixture=False,
    )


def _begin_test_fixture_physical_streaming_scoring(
    *,
    index: PhysicalProductionSessionIndex,
    archive: PhysicalPreopenTerminalArchive,
    global_contract: GlobalBenchmarkContract,
) -> PhysicalStreamedProductionScoringBuilder:
    """Explicit offline oracle seam; its artifact is never formally eligible."""

    return _begin(
        index=index,
        archive=archive,
        global_contract=global_contract,
        permit_fixture=True,
    )


def require_physical_streamed_production_scoring_builder(
    value: PhysicalStreamedProductionScoringBuilder,
) -> PhysicalStreamedProductionScoringBuilder:
    _require_dependencies()
    if type(value) is not PhysicalStreamedProductionScoringBuilder:
        raise PhysicalStreamingScoringError("physical scoring builder changed type")
    state = _vault_require(value)
    try:
        if state.fixture_only:
            _index.require_physical_production_session_index(state.index)
        else:
            _index.require_formal_physical_production_session_index(state.index)
        _require_terminal_parent(
            state.index, state.archive, permit_fixture=state.fixture_only
        )
        require_physical_streaming_scoring_capacity(state.capacity)
        require_loaded_global_benchmark_contract(state.global_contract)
    except (AttributeError, TypeError, ValueError) as exc:
        _vault_revoke(value)
        raise PhysicalStreamingScoringError("physical scoring parent changed") from exc
    if _file_fingerprint(state.spool_path) != state.spool_fingerprint:
        _vault_revoke(value)
        raise PhysicalStreamingScoringError("physical scoring spool changed")
    return value


def physical_streaming_scoring_composition_context(
    builder: PhysicalStreamedProductionScoringBuilder,
    *,
    accepted_risk_binding: object,
) -> PhysicalStreamingScoringCompositionContext:
    """Bind the formal composer to the exact production index parent.

    The returned value grants no transition capability.  Every scoring fold
    independently reauthenticates the retained parents, and the sealed artifact
    retains and reauthenticates the same graph after the builder is consumed.
    """

    state = _state(builder)
    if state.fixture_only:
        raise PhysicalStreamingScoringError(
            "fixture physical scoring cannot enter the formal composer"
        )
    if state.index.accepted_risk_binding is not accepted_risk_binding:
        raise PhysicalStreamingScoringError(
            "physical formal accepted-risk parent differs from scoring index"
        )
    lineage = _production_parent_lineage(
        index=state.index,
        archive=state.archive,
        capacity=state.capacity,
        contract=state.global_contract,
    )
    physical_receipt = state.index.production_evidence_receipt
    evidence_receipt = state.capacity.production_evidence_receipt
    preopen_parent = _terminal_preopen_parent(state.archive)
    try:
        accepted_risk_record = accepted_risk_binding.to_record()
    except (AttributeError, TypeError, ValueError) as exc:
        raise PhysicalStreamingScoringError(
            "physical formal accepted-risk parent changed"
        ) from exc
    if (
        accepted_risk_record != state.index.accepted_risk_binding.to_record()
        or sha256_bytes(canonical_json_bytes(accepted_risk_record))
        != lineage.accepted_risk_binding_sha256
        or accepted_risk_binding.current_admitted_decision_count
        != state.index.current_row_count
        or accepted_risk_binding.censored_admitted_decision_count
        != state.index.censored_row_count
        or preopen_parent is not physical_receipt.preopen_acquisition_receipt
        or state.capacity.preopen_acquisition_receipt is not preopen_parent
        or not _evidence_authority_matches(state.index, evidence_receipt)
        or state.global_contract.map_id != lineage.global_map_id
        or state.global_contract.map_hash != lineage.global_map_sha256
    ):
        raise PhysicalStreamingScoringError(
            "physical formal scoring parent census changed"
        )
    return PhysicalStreamingScoringCompositionContext(
        accepted_risk_binding=accepted_risk_binding,
        capacity=state.capacity,
        preopen_acquisition_receipt=preopen_parent,
        global_contract=state.global_contract,
        lineage=lineage,
        next_fold_index=state.next_fold_index,
        active_fold=state.active_fold,
        finalized=state.finalized,
    )


def _state(value: PhysicalStreamedProductionScoringBuilder) -> _BuilderState:
    require_physical_streamed_production_scoring_builder(value)
    return _vault_require(value)


def _session_iterator(state: _BuilderState) -> Iterator[PhysicalProductionScoringSessionInput]:
    return (
        _index._iter_test_fixture_physical_production_scoring_session_inputs(
            state.index, state.archive
        )
        if state.fixture_only
        else _index.iter_physical_production_scoring_session_inputs(
            state.index, state.archive
        )
    )


def _verify_replay_input(
    connection: sqlite3.Connection,
    position: int,
    item: PhysicalProductionScoringSessionInput,
) -> None:
    if (
        type(item) is not PhysicalProductionScoringSessionInput
        or position >= len(FORMAL_SESSION_GEOMETRY)
        or item.decision_session != FORMAL_SESSION_GEOMETRY[position]
        or item.input_sha256 != sha256_bytes(canonical_json_bytes(item.to_record()))
    ):
        raise PhysicalStreamingScoringError("physical scoring replay session changed")
    try:
        row = connection.execute(
            "SELECT input_sha256, terminal_count, current_count, censored_count "
            "FROM sessions WHERE decision_session=?",
            (item.decision_session,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise PhysicalStreamingScoringError("physical scoring session commitment unavailable") from exc
    expected = (
        item.input_sha256,
        item.terminal_block.terminal_count,
        len(item.current_event_rows),
        len(item.censored_event_rows),
    )
    if row != expected:
        raise PhysicalStreamingScoringError("physical scoring replay differs from derivation")


def _visible(
    connection: sqlite3.Connection,
    *,
    arm: SignalArm,
    kind: int,
    session: str,
    security_ids: tuple[str, ...],
    maximum_row_count: int,
    maximum_payload_bytes: int,
) -> tuple[_FirmBaselineContribution, ...] | tuple[_DailyContribution, ...]:
    if security_ids != tuple(sorted(set(security_ids))):
        raise PhysicalStreamingScoringError("physical scoring census keys changed order")
    if not security_ids:
        return ()
    # The temporary table keeps the SQL statement and Python parameter graph
    # bounded even for a large, independently reviewed session census.
    try:
        connection.execute("DROP TABLE IF EXISTS temp.active_security")
        connection.execute(
            "CREATE TEMP TABLE active_security(security_id TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        connection.executemany(
            "INSERT INTO active_security VALUES (?)",
            ((item,) for item in security_ids),
        )
        summary = connection.execute(
            "SELECT count(*), coalesce(sum(length(c.payload)), 0), "
            "coalesce(max(length(c.payload)), 0) "
            "FROM contributions AS c "
            "JOIN active_security AS a ON a.security_id=c.security_id "
            "WHERE c.kind=? AND c.arm_rank=? AND c.eligible_session<=?",
            (kind, _arm_rank(arm), session),
        ).fetchone()
        if (
            type(summary) is not tuple
            or len(summary) != 3
            or any(type(item) is not int or item < 0 for item in summary)
        ):
            raise PhysicalStreamingScoringError(
                "physical scoring visible contribution census changed"
            )
        row_count, payload_bytes, largest_payload = summary
        if (
            row_count > maximum_row_count
            or payload_bytes > maximum_payload_bytes
            or largest_payload > MAX_PHYSICAL_SCORING_RECORD_BYTES
        ):
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.CONTRIBUTION_CAPACITY_EXCEEDED,
                "physical visible contributions exceeded pre-materialization capacity",
            )
        cursor = connection.execute(
            "SELECT c.payload FROM contributions AS c "
            "JOIN active_security AS a ON a.security_id=c.security_id "
            "WHERE c.kind=? AND c.arm_rank=? AND c.eligible_session<=? "
            "ORDER BY c.security_id, c.eligible_session, c.institution_id, "
            "c.common_event_id, c.linked_sort, c.ordinal",
            (kind, _arm_rank(arm), session),
        )
        decoded = tuple(
            _decode_firm(bytes(payload)) if kind == 0 else _decode_paired(bytes(payload))
            for (payload,) in cursor
        )
        connection.execute("DROP TABLE temp.active_security")
    except sqlite3.Error as exc:
        raise PhysicalStreamingScoringError("physical scoring visible contribution query failed") from exc
    return decoded


def _score_session_arm(
    *,
    state: _BuilderState,
    connection: sqlite3.Connection,
    fold: ProductionScoringFold,
    partition: FoldPartition,
    session_input: PhysicalProductionScoringSessionInput,
    arm: SignalArm,
    observed: dict[str, int],
    ordinals: Mapping[str, int],
    ordinal_retained_bytes: int,
) -> tuple[
    tuple[PrecontrolDecisionRow, ...], tuple[ScoringRefusal, ...],
    tuple[_FirmBaselineContribution, ...], tuple[_DailyContribution, ...],
]:
    terminal = session_input.terminal_block
    security_ids = tuple(item.security_id for item in terminal.accepted)
    limits = dict(state.capacity.limits)
    session_bytes = _retained_object_graph_bytes(session_input)
    remaining_bytes = (
        limits["max_retained_input_graph_bytes"]
        - state.base_retained_input_graph_bytes
        - ordinal_retained_bytes
        - session_bytes
    )
    if remaining_bytes <= 0:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED,
            "one physical scoring session exceeded reviewed retained capacity",
        )
    # Two contribution graphs (firm and paired) are decoded for one arm.  Each
    # is bounded before materialization to one quarter of the remaining graph
    # allowance, leaving explicit headroom for JSON-to-object expansion and
    # the final rows/refusals produced below.  The exact graph is checked again
    # after decoding.
    pre_materialization_bytes = max(1, remaining_bytes // 4)
    firm = _visible(
        connection, arm=arm, kind=0,
        session=session_input.decision_session, security_ids=security_ids,
        maximum_row_count=limits["max_session_contribution_lineage_count"],
        maximum_payload_bytes=pre_materialization_bytes,
    )
    paired = _visible(
        connection, arm=arm, kind=1,
        session=session_input.decision_session, security_ids=security_ids,
        maximum_row_count=limits["max_active_contribution_count_per_arm_session"],
        maximum_payload_bytes=pre_materialization_bytes,
    )
    lineage_count = sum(len(item.linked_c2_row_sha256s) for item in paired)
    firm_lineage_count = sum(len(item.linked_c2_row_sha256s) for item in firm)
    observed["maximum_active_contribution_count_per_arm_session"] = max(
        observed["maximum_active_contribution_count_per_arm_session"], len(paired)
    )
    observed["maximum_session_contribution_lineage_count"] = max(
        observed["maximum_session_contribution_lineage_count"], lineage_count
    )
    if len(paired) > limits["max_active_contribution_count_per_arm_session"]:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.CONTRIBUTION_CAPACITY_EXCEEDED,
            "one physical arm/session contribution state exceeded reviewed capacity",
        )
    if max(lineage_count, firm_lineage_count) > limits["max_session_contribution_lineage_count"]:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.CONTRIBUTION_CAPACITY_EXCEEDED,
            "one physical arm/session contribution lineage exceeded reviewed capacity",
        )
    live_bytes = _retained_object_graph_bytes(session_input, firm, paired)
    live_total = (
        state.base_retained_input_graph_bytes
        + ordinal_retained_bytes
        + live_bytes
    )
    observed["retained_input_graph_bytes"] = max(
        observed["retained_input_graph_bytes"],
        live_total,
    )
    if live_total > limits["max_retained_input_graph_bytes"]:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED,
            "one physical scoring session exceeded reviewed retained capacity",
        )
    try:
        rows, refusals = _build_precontrol_session_terminals(
            batch=_ArmDescriptor(arm),
            fold=fold,
            partition=partition,
            session=session_input.decision_session,
            census_rows=terminal.accepted,
            refused_census_rows=terminal.refused,
            contributions=paired,
            ordinals=ordinals,
        )
    except ProductionScoringError as exc:
        raise PhysicalStreamingScoringError("physical session scoring failed") from exc
    physical_keys = {
        (item.decision_session, item.security_id)
        for item in (*terminal.accepted, *terminal.refused)
    }
    result_keys = {
        (item.decision_session, item.security_id)
        for item in (*rows, *refusals)
    }
    if physical_keys != result_keys or len(rows) + len(refusals) != terminal.terminal_count:
        raise PhysicalStreamingScoringError("physical session scoring is not exhaustive")
    complete_live_bytes = _retained_object_graph_bytes(
        session_input, firm, paired, rows, refusals
    )
    complete_live_total = (
        state.base_retained_input_graph_bytes
        + ordinal_retained_bytes
        + complete_live_bytes
    )
    observed["retained_input_graph_bytes"] = max(
        observed["retained_input_graph_bytes"],
        complete_live_total,
    )
    if complete_live_total > limits["max_retained_input_graph_bytes"]:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED,
            "one physical scoring result session exceeded reviewed retained capacity",
        )
    return rows, refusals, firm, paired


def _coverage_begin(fold: ProductionScoringFold, arm: SignalArm) -> _CoverageState:
    boundary = formal_horizon_fold_boundary(fold.fold_id, 20)
    expected = tuple(
        item for item in FORMAL_SESSION_GEOMETRY if boundary[6] <= item < boundary[7]
    )
    if not expected:
        raise PhysicalStreamingScoringError("physical H20 coverage axis is empty")
    return _CoverageState(
        fold_id=fold.fold_id,
        signal_arm=arm,
        expected_sessions=expected,
        next_session_index=0,
        last_test_session_by_security={},
    )


def _enforce_coverage_capacity(
    state: _BuilderState,
    coverages: Mapping[SignalArm, _CoverageState],
    observed: dict[str, int],
    ordinal_retained_bytes: int,
) -> None:
    """Bound both live incremental H20 accumulators as one retained graph."""

    coverage_bytes = _retained_object_graph_bytes(
        *(coverages[arm] for arm in _ARM_ORDER)
    )
    total = (
        state.base_retained_input_graph_bytes
        + ordinal_retained_bytes
        + coverage_bytes
    )
    observed["retained_input_graph_bytes"] = max(
        observed["retained_input_graph_bytes"], total
    )
    if total > dict(state.capacity.limits)[
        "max_retained_input_graph_bytes"
    ]:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED,
            "physical coverage state exceeded reviewed retained-graph capacity",
        )


def _coverage_record_session(
    state: _CoverageState,
    *,
    decision_session: str,
    census_rows: tuple[EligibleSecuritySession, ...],
    final_rows: tuple[FinalDecisionInput, ...],
    final_refusals: tuple[ScoringRefusal, ...],
    visible_firm: tuple[_FirmBaselineContribution, ...],
    visible_paired: tuple[_DailyContribution, ...],
    ordinals: Mapping[str, int],
) -> None:
    if (
        state.next_session_index >= len(state.expected_sessions)
        or decision_session != state.expected_sessions[state.next_session_index]
    ):
        raise PhysicalStreamingScoringError("physical H20 coverage session axis changed")
    if (
        type(census_rows) is not tuple
        or any(type(item) is not EligibleSecuritySession for item in census_rows)
        or type(final_rows) is not tuple
        or any(type(item) is not FinalDecisionInput for item in final_rows)
        or type(final_refusals) is not tuple
        or any(type(item) is not ScoringRefusal for item in final_refusals)
    ):
        raise PhysicalStreamingScoringError("physical H20 coverage types changed")
    for item in census_rows:
        item.__post_init__()
        if item.decision_session != decision_session:
            raise PhysicalStreamingScoringError("physical coverage census crossed session")
    for item in final_rows:
        item.__post_init__()
        if (
            item.signal_arm is not state.signal_arm
            or item.fold_id != state.fold_id
            or item.partition is not FoldPartition.TEST
            or item.decision_session != decision_session
        ):
            raise PhysicalStreamingScoringError("physical coverage result crossed fold/session")
    for item in final_refusals:
        item.__post_init__()
        if (
            item.signal_arm is not state.signal_arm
            or item.fold_id != state.fold_id
            or item.partition is not FoldPartition.TEST
            or item.decision_session != decision_session
        ):
            raise PhysicalStreamingScoringError("physical coverage refusal crossed fold/session")
    security_ids = tuple(item.security_id for item in census_rows)
    accepted_ids = tuple(item.security_id for item in final_rows)
    refusal_ids = tuple(item.security_id for item in final_refusals)
    if (
        security_ids != tuple(sorted(set(security_ids)))
        or accepted_ids != tuple(sorted(set(accepted_ids)))
        or refusal_ids != tuple(sorted(set(refusal_ids)))
        or set(accepted_ids) & set(refusal_ids)
    ):
        raise PhysicalStreamingScoringError("physical coverage terminal keys changed")

    firm_active = {item.security_id for item in visible_firm}
    paired_active = {item.security_id for item in visible_paired}
    if not paired_active <= firm_active:
        raise PhysicalStreamingScoringError("physical paired coverage exceeds firm baseline")
    try:
        firm_topologies, paired_topologies = _active_component_topologies(
            visible_firm, visible_paired
        )
        paired_topology_set = set(paired_topologies)
        retained = tuple(item for item in firm_topologies if item in paired_topology_set)
        candidate = _is_preoutcome_candidate_date(
            security_ids, accepted_ids, refusal_ids
        )
    except FormalInputBundleError as exc:
        raise PhysicalStreamingScoringError("physical coverage topology failed") from exc
    complete_scores = candidate and not final_refusals and accepted_ids == security_ids
    capable = both_constant = firm_totalized = global_totalized = False
    if complete_scores:
        firm_scores = {item.firm_specific_score for item in final_rows}
        global_scores = {item.global_score for item in final_rows}
        both_constant = len(firm_scores) == 1 and len(global_scores) == 1
        capable = not both_constant
    if candidate:
        # Reuse the frozen scorer's exact Decimal primitives through its
        # authenticated module bindings; only the active session is retained.
        by_security: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        for item in visible_paired:
            age = ordinals[decision_session] - ordinals[item.eligible_session]
            decay = _bundle._decay(age)
            with _bundle.analyst_decimal_context():
                by_security[item.security_id].append(
                    (
                        _bundle._fraction_decimal(item.firm_delta) * decay,
                        _bundle._fraction_decimal(item.global_delta) * decay,
                    )
                )
        sectors: dict[str, list[str]] = defaultdict(list)
        for census in census_rows:
            sectors[census.sector_id].append(census.security_id)
        for members in sectors.values():
            if len(members) < 20 or sum(item in by_security for item in members) < 5:
                continue
            firm_values = tuple(
                _bundle._stable_sum(value[0] for value in by_security.get(item, ()))
                for item in members
            )
            global_values = tuple(
                _bundle._stable_sum(value[1] for value in by_security.get(item, ()))
                for item in members
            )
            firm_totalized = firm_totalized or min(firm_values) == max(firm_values)
            global_totalized = global_totalized or min(global_values) == max(global_values)

    for security_id in security_ids:
        state.last_test_session_by_security[security_id] = decision_session
    state.firm_active_count += len(firm_active)
    state.paired_active_count += len(paired_active)
    state.firm_component_count += len(firm_topologies)
    state.retained_component_count += len(retained)
    state.firm_component_incidence += sum(len(item[0]) for item in firm_topologies)
    state.retained_component_incidence += sum(len(item[0]) for item in retained)
    state.candidate_dates += int(candidate)
    state.capable_dates += int(capable)
    state.firm_totalized_dates += int(firm_totalized)
    state.global_totalized_dates += int(global_totalized)
    state.both_constant_dates += int(both_constant)
    state.score_refused_dates += int(candidate and not complete_scores)
    state.next_session_index += 1


def _coverage_finish(
    state: _CoverageState,
    *,
    connection: sqlite3.Connection,
    result_binding: ScoringResultBinding,
) -> FormalGlobalComparatorCoverage:
    if state.next_session_index != len(state.expected_sessions):
        raise PhysicalStreamingScoringError("physical H20 coverage is incomplete")
    rank = _arm_rank(state.signal_arm)
    endpoint_counts: Counter[str] = Counter()
    pair_counts: Counter[str] = Counter()
    direction_counts: Counter[str] = Counter()
    raw_canonical_counts: Counter[tuple[str, str, str]] = Counter()
    mapped_and_admissible = 0
    try:
        connection.execute("DROP TABLE IF EXISTS temp.last_test_session")
        connection.execute(
            "CREATE TEMP TABLE last_test_session("
            "security_id TEXT PRIMARY KEY, decision_session TEXT NOT NULL) WITHOUT ROWID"
        )
        connection.executemany(
            "INSERT INTO last_test_session VALUES (?, ?)",
            sorted(state.last_test_session_by_security.items()),
        )
        expected_attributed = connection.execute(
            "SELECT count(*) FROM ("
            "SELECT DISTINCT f.row_sha256 FROM firm_lineage AS f "
            "JOIN last_test_session AS t ON t.security_id=f.security_id "
            "WHERE f.arm_rank=? AND f.eligible_session<=t.decision_session)",
            (rank,),
        ).fetchone()
        if (
            type(expected_attributed) is not tuple
            or len(expected_attributed) != 1
            or type(expected_attributed[0]) is not int
            or expected_attributed[0] < 0
        ):
            raise PhysicalStreamingScoringError(
                "physical coverage lineage census changed"
            )
        cursor = connection.execute(
            "SELECT DISTINCT f.row_sha256, l.raw_action, "
            "l.previous_payload, l.current_payload "
            "FROM firm_lineage AS f "
            "JOIN last_test_session AS t ON t.security_id=f.security_id "
            "JOIN labels AS l ON l.arm_rank=f.arm_rank AND l.row_sha256=f.row_sha256 "
            "WHERE f.arm_rank=? AND f.eligible_session<=t.decision_session "
            "ORDER BY f.row_sha256",
            (rank,),
        )
        for row_sha256, raw_action, previous_payload, current_payload in cursor:
            require_sha256(row_sha256, "physical attributed row hash")
            previous = _decode_resolution(bytes(previous_payload))
            current = _decode_resolution(bytes(current_payload))
            endpoint_counts[previous.status] += 1
            endpoint_counts[current.status] += 1
            raw_canonical_counts[_cached_raw_canonical_label_key(previous)] += 1
            raw_canonical_counts[_cached_raw_canonical_label_key(current)] += 1
            if len(raw_canonical_counts) > MAX_GLOBAL_LABEL_DIAGNOSTIC_ROWS:
                raise PhysicalStreamingScoringCapacityError(
                    "physical global-label diagnostic census exceeded capacity"
                )
            pair_status = _pair_status(previous.status, current.status)
            pair_counts[pair_status] += 1
            if pair_status != "mapped":
                continue
            if any(
                item is None
                for item in (
                    previous.score_numerator, previous.score_denominator,
                    current.score_numerator, current.score_denominator,
                )
            ):
                raise PhysicalStreamingScoringError("mapped physical endpoint lost score")
            delta = Fraction(current.score_numerator, current.score_denominator) - Fraction(
                previous.score_numerator, previous.score_denominator
            )
            if delta == 0:
                direction_counts["zero_delta"] += 1
                mapped_and_admissible += 1
            elif (raw_action == "upgrades" and delta > 0) or (
                raw_action == "downgrades" and delta < 0
            ):
                direction_counts["expected_sign"] += 1
                mapped_and_admissible += 1
            else:
                direction_counts["opposite_sign"] += 1
        attributed_count = sum(pair_counts.values())
        if attributed_count != expected_attributed[0]:
            raise PhysicalStreamingScoringError(
                "physical coverage endpoint evidence disappeared"
            )
        connection.execute("DROP TABLE temp.last_test_session")
    except PhysicalStreamingScoringError:
        raise
    except (sqlite3.Error, FormalInputBundleError, TypeError, ValueError) as exc:
        raise PhysicalStreamingScoringError("physical coverage attribution failed") from exc
    if len(raw_canonical_counts) > MAX_GLOBAL_LABEL_DIAGNOSTIC_ROWS:
        raise PhysicalStreamingScoringCapacityError(
            "physical global-label diagnostic census exceeded capacity"
        )
    ledgers = (
        _coverage_ledger("endpoint_pair_mapping", mapped_and_admissible, attributed_count),
        _coverage_ledger("active_security_date_rows", state.paired_active_count, state.firm_active_count),
        _coverage_ledger("common_event_components", state.retained_component_count, state.firm_component_count),
        _coverage_ledger("component_member_incidence", state.retained_component_incidence, state.firm_component_incidence),
        _coverage_ledger("score_capable_dates", state.capable_dates, state.candidate_dates),
    )
    date_counts = (
        ("firm_totalized_zero_dates", state.firm_totalized_dates),
        ("global_totalized_zero_dates", state.global_totalized_dates),
        ("both_arms_constant_dates", state.both_constant_dates),
        ("score_refused_candidate_dates", state.score_refused_dates),
        ("preoutcome_candidate_dates", state.candidate_dates),
    )
    mapped_pairs = pair_counts["mapped"]
    return _build_global_coverage_value(
        schema=GLOBAL_COMPARATOR_COVERAGE_SCHEMA,
        scope_id=state.fold_id,
        source_view_id=_source_view(state.signal_arm),
        fold_ids=(state.fold_id,),
        result_bindings=(result_binding,),
        h20_test_intervals=((
            state.fold_id,
            formal_horizon_fold_boundary(state.fold_id, 20)[6],
            formal_horizon_fold_boundary(state.fold_id, 20)[7],
        ),),
        ledgers=ledgers,
        endpoint_status_counts=tuple((name, endpoint_counts[name]) for name in _ENDPOINT_STATUS_IDS),
        endpoint_pair_status_counts=tuple((name, pair_counts[name]) for name in _ENDPOINT_STATUS_IDS),
        direction_status_counts=tuple((name, direction_counts[name]) for name in _DIRECTION_STATUS_IDS),
        raw_canonical_label_counts=tuple((*key, count) for key, count in sorted(raw_canonical_counts.items())),
        date_diagnostic_counts=date_counts,
        diagnostic_ratios=(
            _coverage_ratio("global_tier_collapse_zero_share", direction_counts["zero_delta"], mapped_pairs),
            _coverage_ratio("global_direction_conflict_share", direction_counts["opposite_sign"], mapped_pairs),
            _coverage_ratio("firm_totalized_zero_date_share", state.firm_totalized_dates, state.candidate_dates),
            _coverage_ratio("global_totalized_zero_date_share", state.global_totalized_dates, state.candidate_dates),
            _coverage_ratio("both_arms_constant_date_share", state.both_constant_dates, state.candidate_dates),
        ),
    )


def _result_binding(
    state: _BuilderState,
    fold: ProductionScoringFold,
    models: tuple[object, object],
) -> ScoringResultBinding:
    evidence = state.capacity.production_evidence_receipt
    precontrol = {
        "schema": "arv2-streamed-precontrol-commitment-v1",
        "archive_id": _terminal_parent_identity(state.archive)[0],
        "archive_sha256": _terminal_parent_identity(state.archive)[1],
        "production_evidence_receipt_id": evidence.receipt_id,
        "production_evidence_receipt_sha256": evidence.receipt_sha256,
        "fold": fold.to_record(),
        "current_batch_id": state.current_batch_id,
        "current_batch_sha256": state.current_batch_sha256,
        "censored_batch_id": state.censored_batch_id,
        "censored_batch_sha256": state.censored_batch_sha256,
        "event_terminal_projection_sha256": state.event_terminal_projection_sha256,
        "method_id": STREAMING_METHOD_ID,
    }
    precontrol_sha = sha256_bytes(canonical_json_bytes(precontrol))
    precontrol_id = f"arv2-streamed-precontrol-{precontrol_sha[:24]}"
    result = {
        "schema": "arv2-streamed-control-adjusted-result-binding-v1",
        "precontrol_batch_id": precontrol_id,
        "precontrol_batch_sha256": precontrol_sha,
        "fold_id": fold.fold_id,
        "models": [item.to_record() for item in models],
        "method_id": STREAMING_METHOD_ID,
        "final_terminal_roots_bound_by_fold_commitment": True,
    }
    digest = sha256_bytes(canonical_json_bytes(result))
    return ScoringResultBinding(
        fold_id=fold.fold_id,
        result_id=f"arv2-streamed-scoring-result-{digest[:24]}",
        result_sha256=digest,
        precontrol_batch_id=precontrol_id,
        precontrol_batch_sha256=precontrol_sha,
        model_sha256s=tuple(item.model_sha256 for item in models),
    )


def _verified_sessions(
    state: _BuilderState,
    connection: sqlite3.Connection,
    observed: dict[str, int],
) -> Iterator[PhysicalProductionScoringSessionInput]:
    count = 0
    for position, item in enumerate(_session_iterator(state)):
        _require_dependencies()
        _verify_replay_input(connection, position, item)
        terminal = item.terminal_block
        observed["maximum_physical_session_terminal_count"] = max(
            observed["maximum_physical_session_terminal_count"], terminal.terminal_count
        )
        observed["maximum_physical_session_uncompressed_bytes"] = max(
            observed["maximum_physical_session_uncompressed_bytes"], terminal.raw_byte_count
        )
        count += 1
        yield item
    if count != len(FORMAL_SESSION_GEOMETRY):
        raise PhysicalStreamingScoringError("physical scoring replay did not exhaust session axis")


def _power_calibration_block(
    *,
    decision_session: str,
    session_position: int,
    accepted: tuple[FinalDecisionInput, ...],
    refused: tuple[ScoringRefusal, ...],
) -> PhysicalPowerCalibrationSessionBlock:
    value = PhysicalPowerCalibrationSessionBlock(
        decision_session=decision_session,
        session_position=session_position,
        accepted=accepted,
        refused=refused,
        block_sha256="",
    )
    digest = sha256_bytes(canonical_json_bytes(value.to_record()))
    return dataclasses.replace(value, block_sha256=digest)


def _run_physical_power_calibration_stream(
    builder: PhysicalStreamedProductionScoringBuilder,
    *,
    accepted_risk_binding: object | None,
    calibration_fold: ProductionScoringFold,
    calibration_fold_sha256: str,
    calibration_sessions: tuple[str, ...],
    calibration_axis_sha256: str,
    consumer: Callable[[PhysicalPowerCalibrationSessionBlock], None],
    permit_fixture: bool,
) -> PhysicalPowerCalibrationStream:
    """Consume one fresh physical scorer in three current-vintage passes."""

    _require_dependencies()
    state = _state(builder)
    try:
        calibration_fold.__post_init__()
        require_sha256(calibration_fold_sha256, "physical calibration fold")
        require_sha256(calibration_axis_sha256, "physical calibration axis")
    except (AttributeError, TypeError, ValueError) as exc:
        raise PhysicalStreamingScoringError(
            "physical power-calibration geometry changed"
        ) from exc
    if (
        state.fixture_only is not permit_fixture
        or state.next_fold_index != 0
        or state.active_fold
        or state.finalized
    ):
        raise PhysicalStreamingScoringError(
            "physical power calibration requires a fresh matching scorer"
        )
    if permit_fixture:
        if (
            accepted_risk_binding is not state.index.accepted_risk_binding
            or accepted_risk_binding is not None
        ):
            raise PhysicalStreamingScoringError(
                "fixture physical calibration accepted-risk parent changed"
            )
    else:
        context = physical_streaming_scoring_composition_context(
            builder,
            accepted_risk_binding=accepted_risk_binding,
        )
        if (
            context.next_fold_index != 0
            or context.active_fold
            or context.finalized
        ):
            raise PhysicalStreamingScoringError(
                "physical power-calibration context is not fresh"
            )
    if (
        type(calibration_fold) is not ProductionScoringFold
        or type(calibration_sessions) is not tuple
        or not calibration_sessions
        or any(type(item) is not str for item in calibration_sessions)
        or calibration_sessions != tuple(sorted(set(calibration_sessions)))
        or tuple(
            item for item in FORMAL_SESSION_GEOMETRY
            if item in set(calibration_sessions)
        ) != calibration_sessions
        or any(
            calibration_fold.partition(item) is not FoldPartition.VALIDATION
            for item in calibration_sessions
        )
        or not callable(consumer)
    ):
        raise PhysicalStreamingScoringError(
            "physical power-calibration axis or consumer changed"
        )
    fold_geometry = (
        calibration_fold.fold_id,
        calibration_fold.train_start,
        calibration_fold.train_end_exclusive,
        calibration_fold.validation_start,
        calibration_fold.validation_end_exclusive,
        calibration_fold.test_start,
        calibration_fold.test_end_exclusive,
    )
    state, lease = _vault_acquire(builder, "power_calibration")
    observed = dict(state.observed)
    connection = _open_spool_reader(state)
    qr: _DiskBackedDecimalMgs | None = None
    completed = False
    try:
        ordinals = _scoring_ordinals(connection)
        ordinal_retained_bytes = _retained_object_graph_bytes(ordinals)
        retained_with_ordinals = (
            state.base_retained_input_graph_bytes + ordinal_retained_bytes
        )
        observed["retained_input_graph_bytes"] = max(
            observed["retained_input_graph_bytes"], retained_with_ordinals
        )
        limits = dict(state.capacity.limits)
        if retained_with_ordinals > limits["max_retained_input_graph_bytes"]:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED,
                "physical calibration ordinal axis exceeded retained capacity",
            )

        levels: set[str] = set()
        for session_input in _verified_sessions(state, connection, observed):
            partition = calibration_fold.partition(session_input.decision_session)
            if partition is not FoldPartition.TRAIN:
                continue
            rows, _refusals, _firm, _paired = _score_session_arm(
                state=state,
                connection=connection,
                fold=calibration_fold,
                partition=partition,
                session_input=session_input,
                arm=SignalArm.CURRENT_VINTAGE,
                observed=observed,
                ordinals=ordinals,
                ordinal_retained_bytes=ordinal_retained_bytes,
            )
            levels.update(
                item.industry_id for item in rows
                if item.state is ScoreState.ACTIVE
            )
        ordered_levels = tuple(sorted(levels))
        if not ordered_levels:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.TRAINING_FIT_UNDERFILLED,
                "current-vintage physical calibration has no active industry",
            )
        if len(ordered_levels) > limits["max_industry_level_count_per_arm_fold"]:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.IDENTITY_CAPACITY_EXCEEDED,
                "physical calibration industry state exceeded reviewed capacity",
            )
        observed["maximum_industry_level_count_per_arm_fold"] = max(
            observed["maximum_industry_level_count_per_arm_fold"],
            len(ordered_levels),
        )

        qr = _DiskBackedDecimalMgs(
            1 + len(CONTROL_COLUMNS) + len(ordered_levels) - 1,
            limits,
        )
        observed["maximum_disk_mgs_width"] = max(
            observed["maximum_disk_mgs_width"], qr.width
        )
        observed["maximum_disk_mgs_live_decimal_count"] = max(
            observed["maximum_disk_mgs_live_decimal_count"], qr.decimal_count
        )
        for session_input in _verified_sessions(state, connection, observed):
            partition = calibration_fold.partition(session_input.decision_session)
            if partition is not FoldPartition.TRAIN:
                continue
            rows, _refusals, _firm, _paired = _score_session_arm(
                state=state,
                connection=connection,
                fold=calibration_fold,
                partition=partition,
                session_input=session_input,
                arm=SignalArm.CURRENT_VINTAGE,
                observed=observed,
                ordinals=ordinals,
                ordinal_retained_bytes=ordinal_retained_bytes,
            )
            for row in rows:
                if row.state is not ScoreState.ACTIVE:
                    continue
                design = (
                    Decimal(1),
                    *row.transformed_controls,
                    *(
                        Decimal(1)
                        if row.industry_id == level
                        else Decimal(0)
                        for level in ordered_levels[1:]
                    ),
                )
                qr.update(
                    design,
                    row.firm_reliable_score,
                    row.global_reliable_score,
                )
        observed["maximum_disk_mgs_spool_row_count"] = max(
            observed["maximum_disk_mgs_spool_row_count"], qr.row_count
        )
        observed["maximum_disk_mgs_spool_byte_count"] = max(
            observed["maximum_disk_mgs_spool_byte_count"], qr.peak_spool_bytes
        )
        observed["maximum_disk_mgs_spool_file_count"] = max(
            observed["maximum_disk_mgs_spool_file_count"], qr.peak_spool_files
        )
        model = _build_streamed_model(
            arm=SignalArm.CURRENT_VINTAGE,
            fold=calibration_fold,
            levels=ordered_levels,
            qr=qr,
        )
        observed["maximum_disk_mgs_spool_byte_count"] = max(
            observed["maximum_disk_mgs_spool_byte_count"], qr.peak_spool_bytes
        )
        observed["maximum_disk_mgs_spool_file_count"] = max(
            observed["maximum_disk_mgs_spool_file_count"], qr.peak_spool_files
        )

        positions = {
            session: position
            for position, session in enumerate(calibration_sessions)
        }
        delivered = 0
        accepted_count = 0
        refusal_count = 0
        terminal_hasher = _chain_hasher(
            "arv2-physical-power-calibration-terminal-v1"
        )
        for session_input in _verified_sessions(state, connection, observed):
            position = positions.get(session_input.decision_session)
            if position is None:
                continue
            if position != delivered:
                raise PhysicalStreamingScoringError(
                    "physical calibration sessions changed order"
                )
            rows, refusals, _firm, _paired = _score_session_arm(
                state=state,
                connection=connection,
                fold=calibration_fold,
                partition=FoldPartition.VALIDATION,
                session_input=session_input,
                arm=SignalArm.CURRENT_VINTAGE,
                observed=observed,
                ordinals=ordinals,
                ordinal_retained_bytes=ordinal_retained_bytes,
            )
            accepted: list[FinalDecisionInput] = []
            terminal_refusals = list(refusals)
            for row in rows:
                adjusted = _apply_streamed_model(model, row)
                if type(adjusted) is FinalDecisionInput:
                    accepted.append(adjusted)
                else:
                    terminal_refusals.append(adjusted)
            accepted_tuple = tuple(
                sorted(accepted, key=lambda item: item.security_id)
            )
            refusal_tuple = tuple(
                sorted(terminal_refusals, key=lambda item: item.security_id)
            )
            if (
                len(accepted_tuple) + len(refusal_tuple)
                != session_input.terminal_block.terminal_count
            ):
                raise PhysicalStreamingScoringError(
                    "physical calibration terminal census is incomplete"
                )
            block = _power_calibration_block(
                decision_session=session_input.decision_session,
                session_position=position,
                accepted=accepted_tuple,
                refused=refusal_tuple,
            )
            block_record = canonical_json_bytes(block.to_record())
            block_sha256 = block.block_sha256
            if consumer(block) is not None:
                raise PhysicalStreamingScoringError(
                    "physical calibration consumer returned a value"
                )
            try:
                block_changed = (
                    type(block) is not PhysicalPowerCalibrationSessionBlock
                    or block.block_sha256 != block_sha256
                    or canonical_json_bytes(block.to_record()) != block_record
                    or sha256_bytes(block_record) != block_sha256
                )
            except (AttributeError, TypeError, ValueError) as exc:
                raise PhysicalStreamingScoringError(
                    "physical calibration callback mutated its block"
                ) from exc
            if block_changed:
                raise PhysicalStreamingScoringError(
                    "physical calibration callback mutated its block"
                )
            if _vault_require_lease(
                builder, lease, "power_calibration"
            ) is not state:
                raise PhysicalStreamingScoringError(
                    "physical calibration scorer changed after callback"
                )
            _chain_update(
                terminal_hasher,
                {
                    "decision_session": block.decision_session,
                    "session_position": block.session_position,
                    "block_sha256": block_sha256,
                },
            )
            accepted_count += len(accepted_tuple)
            refusal_count += len(refusal_tuple)
            delivered += 1
        if delivered != len(calibration_sessions):
            raise PhysicalStreamingScoringError(
                "physical replay omitted a calibration-axis session"
            )
        evidence = state.capacity.production_evidence_receipt
        fields: dict[str, object] = {
            "stream_id": "",
            "stream_sha256": "",
            "schema": PHYSICAL_POWER_CALIBRATION_STREAM_SCHEMA,
            "physical_index": state.index,
            "terminal_archive": state.archive,
            "capacity": state.capacity,
            "global_contract": state.global_contract,
            "accepted_risk_binding": state.index.accepted_risk_binding,
            "model": model,
            "index_id": state.index.index_id,
            "index_sha256": state.index.index_sha256,
            "physical_production_evidence_receipt_id": (
                state.index.production_evidence_receipt_id
            ),
            "physical_production_evidence_receipt_sha256": (
                state.index.production_evidence_receipt_sha256
            ),
            "production_input_archive_id": state.index.production_input_archive_id,
            "production_input_archive_sha256": (
                state.index.production_input_archive_sha256
            ),
            "accepted_risk_binding_sha256": (
                state.index.accepted_risk_binding_sha256
            ),
            "terminal_archive_id": _terminal_parent_identity(state.archive)[0],
            "terminal_archive_sha256": _terminal_parent_identity(state.archive)[1],
            "production_evidence_receipt_id": evidence.receipt_id,
            "production_evidence_receipt_sha256": evidence.receipt_sha256,
            "global_map_id": state.global_contract.map_id,
            "global_map_sha256": state.global_contract.map_hash,
            "calibration_fold_id": calibration_fold.fold_id,
            "calibration_fold_sha256": calibration_fold_sha256,
            "calibration_fold_geometry": fold_geometry,
            "calibration_axis_sha256": calibration_axis_sha256,
            "calibration_session_count": delivered,
            "accepted_decision_count": accepted_count,
            "preoutcome_refusal_count": refusal_count,
            "calibration_terminal_sha256": terminal_hasher.hexdigest(),
            "model_sha256": model.model_sha256,
            "physical_replay_pass_count": 3,
            "observed_capacity": tuple(sorted(observed.items())),
            "provider_access": False,
            "outcome_access": False,
            "quantconnect_access": False,
        }
        value = PhysicalPowerCalibrationStream(**fields)
        digest = sha256_bytes(canonical_json_bytes(value.to_record()))
        value = dataclasses.replace(
            value,
            stream_id=f"arv2-physical-power-calibration-{digest[:24]}",
            stream_sha256=digest,
        )
        if _file_fingerprint(state.spool_path) != state.spool_fingerprint:
            raise PhysicalStreamingScoringError(
                "physical scoring spool changed during calibration"
            )
        _vault_finalize_power_stream(builder, lease, value)
        completed = True
        return (
            _require_test_fixture_physical_power_calibration_stream(value)
            if permit_fixture
            else require_physical_power_calibration_stream(value)
        )
    finally:
        connection.close()
        if qr is not None:
            try:
                qr._cleanup()
            except (AttributeError, OSError):
                pass
        if not completed:
            _vault_revoke(builder)


def run_physical_power_calibration_stream(
    builder: PhysicalStreamedProductionScoringBuilder,
    *,
    accepted_risk_binding: object,
    calibration_fold: ProductionScoringFold,
    calibration_fold_sha256: str,
    calibration_sessions: tuple[str, ...],
    calibration_axis_sha256: str,
    consumer: Callable[[PhysicalPowerCalibrationSessionBlock], None],
) -> PhysicalPowerCalibrationStream:
    """Production-only current-vintage nuisance-calibration consumer."""

    return _run_physical_power_calibration_stream(
        builder,
        accepted_risk_binding=accepted_risk_binding,
        calibration_fold=calibration_fold,
        calibration_fold_sha256=calibration_fold_sha256,
        calibration_sessions=calibration_sessions,
        calibration_axis_sha256=calibration_axis_sha256,
        consumer=consumer,
        permit_fixture=False,
    )


def _run_test_fixture_physical_power_calibration_stream(
    builder: PhysicalStreamedProductionScoringBuilder,
    *,
    calibration_fold: ProductionScoringFold,
    calibration_fold_sha256: str,
    calibration_sessions: tuple[str, ...],
    calibration_axis_sha256: str,
    consumer: Callable[[PhysicalPowerCalibrationSessionBlock], None],
) -> PhysicalPowerCalibrationStream:
    return _run_physical_power_calibration_stream(
        builder,
        accepted_risk_binding=None,
        calibration_fold=calibration_fold,
        calibration_fold_sha256=calibration_fold_sha256,
        calibration_sessions=calibration_sessions,
        calibration_axis_sha256=calibration_axis_sha256,
        consumer=consumer,
        permit_fixture=True,
    )


def iter_physical_streaming_scoring_fold(
    builder: PhysicalStreamedProductionScoringBuilder,
) -> Iterator[StreamedTestSessionBlock]:
    """Fit and exhaust exactly the next formal fold in three physical passes."""

    state = _state(builder)
    if state.finalized or state.active_fold or state.next_fold_index >= len(FORMAL_PRIMARY_FOLD_IDS):
        raise PhysicalStreamingScoringError("physical scoring builder is busy, sealed, or exhausted")
    fold = build_formal_production_scoring_fold(2020 + state.next_fold_index)
    state, lease = _vault_acquire(builder, "formal_fold")
    observed = dict(state.observed)
    connection = _open_spool_reader(state)
    completed = False
    qrs: dict[SignalArm, _DiskBackedDecimalMgs] = {}
    try:
        ordinals = _scoring_ordinals(connection)
        ordinal_retained_bytes = _retained_object_graph_bytes(ordinals)
        retained_with_ordinals = (
            state.base_retained_input_graph_bytes
            + ordinal_retained_bytes
        )
        observed["retained_input_graph_bytes"] = max(
            observed["retained_input_graph_bytes"], retained_with_ordinals
        )
        if retained_with_ordinals > dict(state.capacity.limits)[
            "max_retained_input_graph_bytes"
        ]:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED,
                "physical NYSE ordinal axis exceeded reviewed retained capacity",
            )
        levels_by_arm = {arm: set() for arm in _ARM_ORDER}
        for session_input in _verified_sessions(state, connection, observed):
            partition = fold.partition(session_input.decision_session)
            if partition is not FoldPartition.TRAIN:
                continue
            for arm in _ARM_ORDER:
                rows, _refusals, _firm, _paired = _score_session_arm(
                    state=state, connection=connection, fold=fold,
                    partition=partition, session_input=session_input,
                    arm=arm, observed=observed, ordinals=ordinals,
                    ordinal_retained_bytes=ordinal_retained_bytes,
                )
                levels_by_arm[arm].update(
                    item.industry_id for item in rows if item.state is ScoreState.ACTIVE
                )
        levels = {arm: tuple(sorted(levels_by_arm[arm])) for arm in _ARM_ORDER}
        limits = dict(state.capacity.limits)
        for arm in _ARM_ORDER:
            if not levels[arm]:
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.TRAINING_FIT_UNDERFILLED,
                    f"{arm.value} has no active train-only industry level",
                )
            if len(levels[arm]) > limits["max_industry_level_count_per_arm_fold"]:
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.IDENTITY_CAPACITY_EXCEEDED,
                    "physical train-only industry state exceeded reviewed capacity",
                )
            observed["maximum_industry_level_count_per_arm_fold"] = max(
                observed["maximum_industry_level_count_per_arm_fold"], len(levels[arm])
            )
        qrs = {
            arm: _DiskBackedDecimalMgs(
                1 + len(CONTROL_COLUMNS) + len(levels[arm]) - 1,
                limits,
            )
            for arm in _ARM_ORDER
        }
        for qr in qrs.values():
            observed["maximum_disk_mgs_width"] = max(observed["maximum_disk_mgs_width"], qr.width)
            observed["maximum_disk_mgs_live_decimal_count"] = max(
                observed["maximum_disk_mgs_live_decimal_count"], qr.decimal_count
            )
        for session_input in _verified_sessions(state, connection, observed):
            partition = fold.partition(session_input.decision_session)
            if partition is not FoldPartition.TRAIN:
                continue
            for arm in _ARM_ORDER:
                rows, _refusals, _firm, _paired = _score_session_arm(
                    state=state, connection=connection, fold=fold,
                    partition=partition, session_input=session_input,
                    arm=arm, observed=observed, ordinals=ordinals,
                    ordinal_retained_bytes=ordinal_retained_bytes,
                )
                for row in rows:
                    if row.state is not ScoreState.ACTIVE:
                        continue
                    design = (
                        Decimal(1),
                        *row.transformed_controls,
                        *(
                            Decimal(1) if row.industry_id == level else Decimal(0)
                            for level in levels[arm][1:]
                        ),
                    )
                    qrs[arm].update(design, row.firm_reliable_score, row.global_reliable_score)
        for qr in qrs.values():
            observed["maximum_disk_mgs_spool_row_count"] = max(
                observed["maximum_disk_mgs_spool_row_count"], qr.row_count
            )
            observed["maximum_disk_mgs_spool_byte_count"] = max(
                observed["maximum_disk_mgs_spool_byte_count"], qr.peak_spool_bytes
            )
            observed["maximum_disk_mgs_spool_file_count"] = max(
                observed["maximum_disk_mgs_spool_file_count"], qr.peak_spool_files
            )
        models = tuple(
            _build_streamed_model(arm=arm, fold=fold, levels=levels[arm], qr=qrs[arm])
            for arm in _ARM_ORDER
        )
        for qr in qrs.values():
            observed["maximum_disk_mgs_spool_byte_count"] = max(
                observed["maximum_disk_mgs_spool_byte_count"], qr.peak_spool_bytes
            )
            observed["maximum_disk_mgs_spool_file_count"] = max(
                observed["maximum_disk_mgs_spool_file_count"], qr.peak_spool_files
            )
        binding = _result_binding(state, fold, models)
        coverages = {arm: _coverage_begin(fold, arm) for arm in _ARM_ORDER}
        partition_counts = {
            (partition, arm): 0 for partition in FoldPartition for arm in _ARM_ORDER
        }
        partition_hashers = {
            (partition, arm): _chain_hasher(
                f"arv2-streamed-{partition.value}-{arm.value}-terminal-v1"
            )
            for partition in FoldPartition for arm in _ARM_ORDER
        }
        h20 = formal_horizon_fold_boundary(fold.fold_id, 20)
        for session_input in _verified_sessions(state, connection, observed):
            partition = fold.partition(session_input.decision_session)
            if partition is None:
                continue
            finals: dict[
                SignalArm,
                tuple[
                    tuple[FinalDecisionInput, ...], tuple[ScoringRefusal, ...],
                    tuple[_FirmBaselineContribution, ...], tuple[_DailyContribution, ...],
                ],
            ] = {}
            for arm, model in zip(_ARM_ORDER, models, strict=True):
                rows, refusals, firm, paired = _score_session_arm(
                    state=state, connection=connection, fold=fold,
                    partition=partition, session_input=session_input,
                    arm=arm, observed=observed, ordinals=ordinals,
                    ordinal_retained_bytes=ordinal_retained_bytes,
                )
                accepted: list[FinalDecisionInput] = []
                terminal_refusals = list(refusals)
                for row in rows:
                    value = _apply_streamed_model(model, row)
                    if type(value) is FinalDecisionInput:
                        accepted.append(value)
                    else:
                        terminal_refusals.append(value)
                accepted_tuple = tuple(sorted(accepted, key=lambda item: item.security_id))
                refusal_tuple = tuple(sorted(terminal_refusals, key=lambda item: item.security_id))
                if len(accepted_tuple) + len(refusal_tuple) != session_input.terminal_block.terminal_count:
                    raise PhysicalStreamingScoringError("physical adjusted terminal census is incomplete")
                for item in sorted((*accepted_tuple, *refusal_tuple), key=lambda value: value.security_id):
                    disposition = "accepted" if type(item) is FinalDecisionInput else "refused"
                    lineage = item.row_sha256 if type(item) is FinalDecisionInput else item.refusal_sha256
                    _chain_update(
                        partition_hashers[(partition, arm)],
                        {
                            "decision_session": session_input.decision_session,
                            "security_id": item.security_id,
                            "disposition": disposition,
                            "lineage_sha256": lineage,
                        },
                    )
                    partition_counts[(partition, arm)] += 1
                finals[arm] = (accepted_tuple, refusal_tuple, firm, paired)
            if h20[6] <= session_input.decision_session < h20[7]:
                for arm in _ARM_ORDER:
                    _coverage_record_session(
                        coverages[arm],
                        decision_session=session_input.decision_session,
                        census_rows=session_input.terminal_block.accepted,
                        final_rows=finals[arm][0],
                        final_refusals=finals[arm][1],
                        visible_firm=finals[arm][2],
                        visible_paired=finals[arm][3],
                        ordinals=ordinals,
                    )
                    _enforce_coverage_capacity(
                        state, coverages, observed, ordinal_retained_bytes
                    )
            if partition is FoldPartition.TEST:
                block = _test_block(
                    fold=fold,
                    session=session_input.decision_session,
                    binding=binding,
                    current_rows=finals[SignalArm.CURRENT_VINTAGE][0],
                    current_refusals=finals[SignalArm.CURRENT_VINTAGE][1],
                    censored_rows=finals[SignalArm.CONSERVATIVE_CENSORED][0],
                    censored_refusals=finals[SignalArm.CONSERVATIVE_CENSORED][1],
                )
                observed["maximum_test_session_terminal_count_per_arm"] = max(
                    observed["maximum_test_session_terminal_count_per_arm"],
                    block.matched_terminal_count,
                )
                state = _vault_commit_block(builder, lease, block)
                yield block
                if _vault_require_lease(builder, lease, "formal_fold") is not state:
                    raise PhysicalStreamingScoringError("physical scoring state changed after yield")
        sealed_coverages = tuple(
            _coverage_finish(coverages[arm], connection=connection, result_binding=binding)
            for arm in _ARM_ORDER
        )
        geometry = (
            fold.fold_id, fold.train_start, fold.train_end_exclusive,
            fold.validation_start, fold.validation_end_exclusive,
            fold.test_start, fold.test_end_exclusive,
        )
        commitment = StreamedFoldCommitment(
            schema=STREAMING_FOLD_SCHEMA,
            fold_id=fold.fold_id,
            result_binding=binding,
            fold_geometry=geometry,
            model_records=tuple(item.to_record() for item in models),
            global_comparator_coverages=sealed_coverages,
            partition_terminal_counts=tuple(
                (
                    partition.value,
                    partition_counts[(partition, SignalArm.CURRENT_VINTAGE)],
                    partition_counts[(partition, SignalArm.CONSERVATIVE_CENSORED)],
                )
                for partition in FoldPartition
            ),
            partition_terminal_roots=tuple(
                (
                    partition.value,
                    partition_hashers[(partition, SignalArm.CURRENT_VINTAGE)].hexdigest(),
                    partition_hashers[(partition, SignalArm.CONSERVATIVE_CENSORED)].hexdigest(),
                )
                for partition in FoldPartition
            ),
            event_terminal_projection_sha256=state.event_terminal_projection_sha256,
            physical_replay_pass_count=3,
        )
        state = _vault_commit_fold(builder, lease, commitment, observed)
        completed = True
    finally:
        connection.close()
        if completed:
            if _file_fingerprint(state.spool_path) != state.spool_fingerprint:
                _vault_revoke(builder)
                raise PhysicalStreamingScoringError("physical scoring spool changed during fold")
        else:
            for qr in qrs.values():
                try:
                    qr._cleanup()
                except (AttributeError, OSError):
                    pass
            _vault_revoke(builder)


def _artifact_record(
    state: _BuilderState,
    pooled: tuple[FormalGlobalComparatorCoverage, FormalGlobalComparatorCoverage],
) -> dict[str, object]:
    bindings = tuple(item.result_binding for item in state.fold_commitments)
    evidence = state.capacity.production_evidence_receipt
    return {
        "schema": STREAMING_SCORING_SCHEMA,
        "archive_id": _terminal_parent_identity(state.archive)[0],
        "archive_sha256": _terminal_parent_identity(state.archive)[1],
        "production_evidence_receipt_id": evidence.receipt_id,
        "production_evidence_receipt_sha256": evidence.receipt_sha256,
        "capacity_receipt_id": state.capacity.receipt_id,
        "capacity_receipt_sha256": state.capacity.receipt_sha256,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "method_id": STREAMING_METHOD_ID,
        "paired_bootstrap_authority": _paired_bootstrap_authority_record(
            state.global_contract
        ),
        "result_bindings": [item.to_record() for item in bindings],
        "fold_commitments": [item.to_record() for item in state.fold_commitments],
        "pooled_global_comparator_coverages": [item.to_record() for item in pooled],
        "matched_test_terminal_count": state.matched_test_terminal_count,
        "matched_test_terminal_sha256": state.matched_test_terminal_sha256,
        "observed_capacity": dict(state.observed),
        "upstream_materialized_truth_count": 0,
        "upstream_materialized_result_count": 0,
        "capabilities": {
            "provider_access": False,
            "outcome_access": False,
            "quantconnect_access": False,
            "qc_launch_available": False,
        },
    }


def finish_physical_streaming_scoring(
    builder: PhysicalStreamedProductionScoringBuilder,
) -> StreamedProductionScoringArtifact:
    """Seal six exhausted physical folds into the existing compact artifact type."""

    state = _state(builder)
    if state.fixture_only:
        raise PhysicalStreamingScoringError(
            "fixture physical scoring cannot mint a formal scoring artifact"
        )
    return _finish(builder, permit_fixture=False)


def _finish_test_fixture_physical_streaming_scoring(
    builder: PhysicalStreamedProductionScoringBuilder,
) -> StreamedProductionScoringArtifact:
    """Seal an offline parity artifact under test-only authority."""

    state = _state(builder)
    if not state.fixture_only:
        raise PhysicalStreamingScoringError("production physical scoring used fixture finisher")
    return _finish(builder, permit_fixture=True)


def _finish(
    builder: PhysicalStreamedProductionScoringBuilder,
    *,
    permit_fixture: bool,
) -> StreamedProductionScoringArtifact:
    state = _state(builder)
    if (
        state.fixture_only is not permit_fixture
        or state.finalized
        or state.active_fold
        or state.next_fold_index != len(FORMAL_PRIMARY_FOLD_IDS)
    ):
        raise PhysicalStreamingScoringError(
            "physical scoring is incomplete, busy, or already sealed"
        )
    try:
        pooled = tuple(
            pool_formal_global_comparator_coverages(
                tuple(
                    commitment.global_comparator_coverages[arm_index]
                    for commitment in state.fold_commitments
                )
            )
            for arm_index in range(len(_ARM_ORDER))
        )
    except FormalInputBundleError as exc:
        _vault_revoke(builder)
        raise PhysicalStreamingScoringError("physical comparator coverage did not pool") from exc
    record = _artifact_record(state, pooled)
    digest = sha256_bytes(canonical_json_bytes(record))
    value = object.__new__(StreamedProductionScoringArtifact)
    evidence = state.capacity.production_evidence_receipt
    fields: dict[str, object] = {
        "artifact_id": f"arv2-formal-streamed-scoring-{digest[:24]}",
        "artifact_sha256": digest,
        "schema": STREAMING_SCORING_SCHEMA,
        "archive_id": _terminal_parent_identity(state.archive)[0],
        "archive_sha256": _terminal_parent_identity(state.archive)[1],
        "production_evidence_receipt_id": evidence.receipt_id,
        "production_evidence_receipt_sha256": evidence.receipt_sha256,
        "capacity_receipt_id": state.capacity.receipt_id,
        "capacity_receipt_sha256": state.capacity.receipt_sha256,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "method_id": STREAMING_METHOD_ID,
        "global_contract": state.global_contract,
        "result_bindings": tuple(item.result_binding for item in state.fold_commitments),
        "fold_commitments": state.fold_commitments,
        "pooled_global_comparator_coverages": pooled,
        "matched_test_terminal_count": state.matched_test_terminal_count,
        "matched_test_terminal_sha256": state.matched_test_terminal_sha256,
        "observed_capacity": state.observed,
        "upstream_materialized_truth_count": 0,
        "upstream_materialized_result_count": 0,
        "provider_access": False,
        "outcome_access": False,
        "quantconnect_access": False,
        "qc_launch_available": False,
    }
    if set(fields) != {item.name for item in dataclasses.fields(value)}:
        _vault_revoke(builder)
        raise PhysicalStreamingScoringError("streamed scoring artifact field inventory changed")
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    if value.to_record() != record:
        _vault_revoke(builder)
        raise PhysicalStreamingScoringError("physical scoring artifact changed during sealing")
    _vault_finalize(builder, value)
    return value


def _require_artifact(
    value: StreamedProductionScoringArtifact,
    *,
    permit_fixture: bool,
    expected_lineage: PhysicalStreamingScoringLineage | None = None,
) -> StreamedProductionScoringArtifact:
    _require_dependencies()
    if type(value) is not StreamedProductionScoringArtifact:
        raise PhysicalStreamingScoringError("physical scoring artifact changed type")
    current = _vault_artifact_current(value)
    if current is None:
        raise PhysicalStreamingScoringError(
            "physical scoring artifact is not builder-authenticated"
        )
    (
        record,
        topology,
        fixture_only,
        index,
        archive,
        capacity,
        contract,
        retained_lineage,
    ) = current
    try:
        if permit_fixture:
            _index.require_physical_production_session_index(index)
        else:
            _index.require_formal_physical_production_session_index(index)
        _require_terminal_parent(index, archive, permit_fixture=permit_fixture)
        require_physical_streaming_scoring_capacity(capacity)
        require_loaded_global_benchmark_contract(contract)
        lineage_record = _parent_lineage_record(
            index=index,
            archive=archive,
            capacity=capacity,
            contract=contract,
        )
        lineage = None
        if not permit_fixture:
            lineage = _production_parent_lineage(
                index=index,
                archive=archive,
                capacity=capacity,
                contract=contract,
            )
    except (AttributeError, TypeError, ValueError, OSError) as exc:
        raise PhysicalStreamingScoringError(
            "physical scoring artifact retained parent changed"
        ) from exc
    digest = sha256_bytes(canonical_json_bytes(value.to_record()))
    false_flags = (
        value.provider_access,
        value.outcome_access,
        value.quantconnect_access,
        value.qc_launch_available,
    )
    if (
        fixture_only is not permit_fixture
        or contract is not value.global_contract
        or _terminal_parent_identity(archive)[0] != value.archive_id
        or _terminal_parent_identity(archive)[1] != value.archive_sha256
        or capacity.receipt_id != value.capacity_receipt_id
        or capacity.receipt_sha256 != value.capacity_receipt_sha256
        or capacity.production_evidence_receipt.receipt_id
        != value.production_evidence_receipt_id
        or capacity.production_evidence_receipt.receipt_sha256
        != value.production_evidence_receipt_sha256
        or retained_lineage != canonical_json_bytes(lineage_record)
        or (
            expected_lineage is not None
            and (
                lineage is None
                or type(expected_lineage) is not PhysicalStreamingScoringLineage
                or expected_lineage.to_record() != lineage.to_record()
            )
        )
        or record != canonical_json_bytes(value.to_record())
        or topology != _artifact_topology(value)
        or value.artifact_sha256 != digest
        or value.artifact_id != f"arv2-formal-streamed-scoring-{digest[:24]}"
        or value.schema != STREAMING_SCORING_SCHEMA
        or value.scoring_contract_id != SCORING_CONTRACT_ID
        or value.scoring_contract_sha256 != SCORING_CONTRACT_SHA256
        or value.method_id != STREAMING_METHOD_ID
        or type(value.result_bindings) is not tuple
        or type(value.fold_commitments) is not tuple
        or len(value.result_bindings) != len(FORMAL_PRIMARY_FOLD_IDS)
        or len(value.fold_commitments) != len(FORMAL_PRIMARY_FOLD_IDS)
        or tuple(item.fold_id for item in value.fold_commitments) != FORMAL_PRIMARY_FOLD_IDS
        or any(type(flag) is not bool or flag for flag in false_flags)
        or value.upstream_materialized_truth_count != 0
        or value.upstream_materialized_result_count != 0
    ):
        raise PhysicalStreamingScoringError("physical scoring artifact changed after sealing")
    for fold_index, (commitment, binding) in enumerate(
        zip(value.fold_commitments, value.result_bindings, strict=True)
    ):
        if commitment.result_binding is not binding:
            raise PhysicalStreamingScoringError("physical fold binding topology changed")
        for arm_index, coverage in enumerate(commitment.global_comparator_coverages):
            try:
                require_formal_global_comparator_coverage(coverage)
            except FormalInputBundleError as exc:
                raise PhysicalStreamingScoringError("physical fold coverage changed") from exc
            if (
                coverage.fold_ids != (FORMAL_PRIMARY_FOLD_IDS[fold_index],)
                or coverage.result_bindings != (binding,)
                or coverage.result_bindings[0] is not binding
                or coverage.source_view_id != (CURRENT_VIEW_LABEL, CENSORED_VIEW_LABEL)[arm_index]
            ):
                raise PhysicalStreamingScoringError("physical fold coverage lineage changed")
    for arm_index, coverage in enumerate(value.pooled_global_comparator_coverages):
        try:
            require_formal_global_comparator_coverage(coverage)
        except FormalInputBundleError as exc:
            raise PhysicalStreamingScoringError("physical pooled coverage changed") from exc
        if (
            coverage.fold_ids != FORMAL_PRIMARY_FOLD_IDS
            or coverage.source_view_id != (CURRENT_VIEW_LABEL, CENSORED_VIEW_LABEL)[arm_index]
            or coverage.result_bindings != value.result_bindings
        ):
            raise PhysicalStreamingScoringError("physical pooled coverage lineage changed")
    return value


def _require_physical_power_calibration_stream(
    value: PhysicalPowerCalibrationStream,
    *,
    permit_fixture: bool,
) -> PhysicalPowerCalibrationStream:
    _require_dependencies()
    if type(value) is not PhysicalPowerCalibrationStream:
        raise PhysicalStreamingScoringError(
            "physical power-calibration stream changed type"
        )
    current = _vault_power_stream_current(value)
    if current is None:
        raise PhysicalStreamingScoringError(
            "physical power-calibration stream lacks scorer authority"
        )
    (
        record,
        topology,
        fixture_only,
        index,
        archive,
        capacity,
        contract,
        accepted_risk,
        model,
        retained_lineage,
        retained_model,
    ) = current
    try:
        if permit_fixture:
            _index.require_physical_production_session_index(index)
        else:
            _index.require_formal_physical_production_session_index(index)
        _require_terminal_parent(index, archive, permit_fixture=permit_fixture)
        require_physical_streaming_scoring_capacity(capacity)
        require_loaded_global_benchmark_contract(contract)
        parent_record = canonical_json_bytes(
            _parent_lineage_record(
                index=index,
                archive=archive,
                capacity=capacity,
                contract=contract,
            )
        )
    except (AttributeError, TypeError, ValueError, OSError) as exc:
        raise PhysicalStreamingScoringError(
            "physical power-calibration retained parent changed"
        ) from exc
    if type(model) is not StreamedControlModel:
        raise PhysicalStreamingScoringError(
            "physical power-calibration model changed type"
        )
    try:
        model_record = model.to_record()
        model_seed = dict(model_record)
        model_id = model_seed.pop("model_id")
        model_sha256 = model_seed.pop("model_sha256")
        computed_model_sha256 = sha256_bytes(canonical_json_bytes(model_seed))
    except (AttributeError, TypeError, ValueError, KeyError) as exc:
        raise PhysicalStreamingScoringError(
            "physical power-calibration model changed"
        ) from exc
    try:
        require_sha256(value.calibration_fold_sha256, "physical calibration fold")
        require_sha256(value.calibration_axis_sha256, "physical calibration axis")
        require_sha256(
            value.calibration_terminal_sha256,
            "physical calibration terminal root",
        )
    except ValueError as exc:
        raise PhysicalStreamingScoringError(
            "physical power-calibration commitment changed"
        ) from exc
    digest = sha256_bytes(canonical_json_bytes(value.to_record()))
    false_flags = (
        value.provider_access,
        value.outcome_access,
        value.quantconnect_access,
    )
    if (
        fixture_only is not permit_fixture
        or value.physical_index is not index
        or value.terminal_archive is not archive
        or value.capacity is not capacity
        or value.global_contract is not contract
        or value.accepted_risk_binding is not accepted_risk
        or value.model is not model
        or index.accepted_risk_binding is not accepted_risk
        or (permit_fixture and accepted_risk is not None)
        or (not permit_fixture and accepted_risk is None)
        or retained_lineage != parent_record
        or retained_model != canonical_json_bytes(model_record)
        or record != canonical_json_bytes(value.to_record())
        or topology != _power_stream_topology(value)
        or value.stream_sha256 != digest
        or value.stream_id
        != f"arv2-physical-power-calibration-{digest[:24]}"
        or value.schema != PHYSICAL_POWER_CALIBRATION_STREAM_SCHEMA
        or value.index_id != index.index_id
        or value.index_sha256 != index.index_sha256
        or value.physical_production_evidence_receipt_id
        != index.production_evidence_receipt_id
        or value.physical_production_evidence_receipt_sha256
        != index.production_evidence_receipt_sha256
        or value.production_input_archive_id
        != index.production_input_archive_id
        or value.production_input_archive_sha256
        != index.production_input_archive_sha256
        or value.accepted_risk_binding_sha256
        != index.accepted_risk_binding_sha256
        or value.terminal_archive_id != _terminal_parent_identity(archive)[0]
        or value.terminal_archive_sha256 != _terminal_parent_identity(archive)[1]
        or value.production_evidence_receipt_id
        != capacity.production_evidence_receipt.receipt_id
        or value.production_evidence_receipt_sha256
        != capacity.production_evidence_receipt.receipt_sha256
        or value.global_map_id != contract.map_id
        or value.global_map_sha256 != contract.map_hash
        or type(value.calibration_fold_geometry) is not tuple
        or len(value.calibration_fold_geometry) != 7
        or value.calibration_fold_geometry[0] != value.calibration_fold_id
        or model.signal_arm is not SignalArm.CURRENT_VINTAGE
        or model.fold_id != value.calibration_fold_id
        or model.model_id != model_id
        or model.model_sha256 != model_sha256
        or model.model_sha256 != computed_model_sha256
        or value.model_sha256 != model.model_sha256
        or type(value.observed_capacity) is not tuple
        or value.observed_capacity != tuple(sorted(value.observed_capacity))
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
            or item[1] < 0
            for item in value.observed_capacity
        )
        or any(
            type(item) is not int or item < 0
            for item in (
                value.calibration_session_count,
                value.accepted_decision_count,
                value.preoutcome_refusal_count,
            )
        )
        or value.physical_replay_pass_count != 3
        or any(type(flag) is not bool or flag for flag in false_flags)
    ):
        raise PhysicalStreamingScoringError(
            "physical power-calibration stream changed after sealing"
        )
    return value


def require_physical_power_calibration_stream(
    value: PhysicalPowerCalibrationStream,
) -> PhysicalPowerCalibrationStream:
    """Authenticate the production physical nuisance-calibration stream."""

    return _require_physical_power_calibration_stream(value, permit_fixture=False)


def _require_test_fixture_physical_power_calibration_stream(
    value: PhysicalPowerCalibrationStream,
) -> PhysicalPowerCalibrationStream:
    return _require_physical_power_calibration_stream(value, permit_fixture=True)


def require_physical_streamed_production_scoring_artifact(
    value: StreamedProductionScoringArtifact,
    *,
    expected_lineage: PhysicalStreamingScoringLineage | None = None,
) -> StreamedProductionScoringArtifact:
    """Require an artifact built from the reviewed production physical index."""

    return _require_artifact(
        value,
        permit_fixture=False,
        expected_lineage=expected_lineage,
    )


def _require_test_fixture_physical_streamed_production_scoring_artifact(
    value: StreamedProductionScoringArtifact,
) -> StreamedProductionScoringArtifact:
    return _require_artifact(value, permit_fixture=True)


__all__ = (
    "MAX_GLOBAL_LABEL_DIAGNOSTIC_ROWS",
    "MAX_PHYSICAL_SCORING_DERIVED_ROWS",
    "MAX_PHYSICAL_SCORING_RECORD_BYTES",
    "MAX_PHYSICAL_SCORING_SPOOL_BYTES",
    "PHYSICAL_SCORING_BUILDER_SCHEMA",
    "PHYSICAL_SCORING_LINEAGE_SCHEMA",
    "PHYSICAL_SCORING_SPOOL_SCHEMA",
    "PHYSICAL_POWER_CALIBRATION_STREAM_SCHEMA",
    "SECTION72_PHYSICAL_CAPACITY_AUTHORITY_MODE",
    "SECTION72_PHYSICAL_CAPACITY_LIMITS",
    "SECTION72_PHYSICAL_CAPACITY_SCHEMA",
    "Section72PhysicalStreamingCapacityBinding",
    "PhysicalPowerCalibrationSessionBlock",
    "PhysicalPowerCalibrationStream",
    "PhysicalStreamedProductionScoringBuilder",
    "PhysicalStreamingScoringCompositionContext",
    "PhysicalStreamingScoringCapacityError",
    "PhysicalStreamingScoringError",
    "PhysicalStreamingScoringLineage",
    "begin_physical_streaming_scoring",
    "finish_physical_streaming_scoring",
    "iter_physical_streaming_scoring_fold",
    "physical_streaming_scoring_composition_context",
    "require_physical_power_calibration_stream",
    "require_physical_streaming_scoring_capacity",
    "require_physical_streamed_production_scoring_artifact",
    "require_physical_streamed_production_scoring_builder",
    "require_section72_physical_streaming_capacity_binding",
    "run_physical_power_calibration_stream",
)
