"""Physical, session-streamed ARV2 formal-input successor.

The legacy formal composer intentionally refuses because it retains a complete
``ProductionTruthArtifact`` and six complete ``ProductionScoringResult``
graphs.  This module is a separate offline path.  It replays independently
reviewed pre-open terminal shards from private regular files, keeps only one
logical security/session cross-section at a time, fits train-only controls with
a bounded disk-spooled Decimal modified-Gram-Schmidt state, and persists bounded content-addressed
formal shards.  It never reads a provider, outcome, QuantConnect account, or
broker and it never grants launch, result, deployment, order, or trading
authority.

The streamed path deliberately does not accept caller-computed labels, scores,
roots, row counts, or peak-use assertions.  Endpoint labels are reconstructed
from the physically reviewed C2 evidence receipt; terminal counts and roots are
derived while replaying the physically pinned shards; and peak counters are
updated by the implementation which owns the corresponding live containers.
"""
from __future__ import annotations

import dataclasses
import gzip
import hashlib
import itertools
import heapq
import io
import json
import os
import stat
import sys
import tempfile
import threading
import weakref
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import date, timedelta
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from enum import Enum
from fractions import Fraction
from pathlib import Path
from typing import Any

from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes,
    require_identifier,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2.global_benchmark_contract import (
    GlobalBenchmarkContract,
    GlobalBenchmarkContractError,
    bootstrap_seed_record,
    require_loaded_global_benchmark_contract,
)
from research.analyst_revisions_v2.preopen_control_acquisition import (
    PreopenControlAcquisitionError,
    PreopenControlAcquisitionReceipt,
    acquisition_output_shard_descriptor_records,
    acquisition_q_data_measurement_projection_record,
    acquisition_receipt_artifact_binding_record,
    require_reviewed_preopen_control_acquisition_receipt,
)
from research.analyst_revisions_v2.production_evidence_acquisition import (
    ProductionEvidenceAcquisitionError,
    ProductionEvidenceAcquisitionReceipt,
    require_production_evidence_acquisition_receipt,
)
from research.analyst_revisions_v2.production_input_pipeline import (
    EvidenceSourceKind,
    NormalizedPreOutcomeRow,
    ProductionInputBatch,
    ProductionInputError,
    SignalArm,
    build_production_input_batch,
    require_production_input_batch,
)
from research.analyst_revisions_v2.production_scoring import (
    CLIP_HIGH,
    CLIP_LOW,
    BINARY_COLUMNS,
    CONTINUOUS_COLUMNS,
    CONTROL_COLUMNS,
    FORMAL_PRIMARY_FOLD_IDS,
    FORMAL_HORIZON_FOLD_BOUNDARIES,
    HALF_LIFE_SESSIONS,
    RANK_RELATIVE_THRESHOLD,
    SCORING_CONTRACT_ID,
    SCORING_CONTRACT_SHA256,
    CensusRefusalReason,
    EligibleSecuritySession,
    EligibleSecuritySessionRefusal,
    EndpointLabelEvidence,
    FinalDecisionInput,
    FoldPartition,
    PrecontrolDecisionRow,
    ProductionControlVector,
    ProductionScoringError,
    ProductionScoringFold,
    ScoreDisposition,
    ScoreState,
    ScoringRefusal,
    _build_precontrol_session_terminals,
    _decimal_text,
    _firm_evidence_by_c2_hash,
    _normalized_union,
    _row_evidence_by_c2_hash,
    _session_ordinals,
    build_eligible_security_session,
    build_eligible_security_session_refusal,
    build_endpoint_label_evidence,
    build_formal_production_scoring_fold,
    formal_horizon_fold_boundary,
)
from research.analyst_revisions_v2.production_truth_gate import (
    FORMAL_SESSION_GEOMETRY,
    FORMAL_SESSION_GEOMETRY_SHA256,
)
from scripts import build_arv2_historical_preopen_bridge as historical_module
from data.exchange_calendar import ExchangeCalendarError, trading_sessions

from . import preopen_control_acquisition_io as preopen_io
from .formal_input_bundle import (
    CURRENT_VIEW_LABEL,
    CENSORED_VIEW_LABEL,
    HORIZONS,
    FormalGlobalComparatorCoverage,
    FormalGlobalComparatorCoverageSource,
    FormalInputBundleError,
    FormalPowerCalibrationBinding,
    SCORING_LINEAGE_SCHEMA,
    SCORING_REFUSAL_SCHEMA,
    ProductionScoredDecisionLineage,
    ProductionScoringCensusRefusal,
    ScoringResultBinding,
    _post_identified,
    _require_production_scored_decision,
    _require_production_scoring_refusal,
    begin_formal_global_comparator_fold_coverage_from_source,
    build_formal_global_comparator_coverage_source,
    finish_formal_global_comparator_fold_coverage,
    formal_global_comparator_coverage_accumulator_retained_bytes,
    formal_global_comparator_coverage_source_retained_bytes,
    formal_global_comparator_coverage_source_scoring_inputs,
    formal_global_comparator_coverage_source_visible_contributions,
    pool_formal_global_comparator_coverages,
    record_formal_global_comparator_coverage_session,
    require_formal_power_calibration_binding,
    require_formal_global_comparator_coverage,
)
from .formal_economic_execution_definition import (
    FormalEconomicExecutionBinding,
    FormalEconomicExecutionDefinitionError,
    formal_economic_execution_binding_record,
    formal_economic_execution_definition_record,
    require_formal_economic_execution_binding,
)
from .formal_run_protocol import (
    EVALUATION_ID,
    SOURCE_VIEW_IDS,
    TERMINAL_POLICY_ID,
    AcceptedRiskPairBinding,
    ArtifactBinding,
    PowerFloorBinding,
    require_accepted_risk_pair_binding,
    require_artifact_binding,
    require_power_floor_binding,
)
from .formal_report_contract import (
    FormalReportContract,
    FormalReportContractError,
    build_formal_report_contract,
    formal_report_contract_record,
    require_formal_report_contract,
)
from .formal_runtime_projection import (
    ABSOLUTE_MAX_SHARD_COMPRESSED_BYTES,
    ABSOLUTE_MAX_SHARD_ROWS,
    ABSOLUTE_MAX_SHARD_UNCOMPRESSED_BYTES,
    COMPRESSED_SHARD_SCHEMA,
    FORMAL_INPUT_CONTENT_PREFIX,
    SHARD_COMPRESSION,
    SHARD_CONTENT_ENCODING,
    SHARD_ROLE_ORDER,
    SHARD_ROW_SCHEMAS,
    FormalQcCompressedShard,
    build_daily_market_requirement_id,
    build_minute_market_requirement_id,
    require_formal_qc_compressed_shard,
)
from .formal_input_composer import (
    FormalTerminalDispositionPackage,
    _axis,
    _decision_terminal_slot_id,
    _economic_terminal_slot_id,
    _identified,
    _selected_sleeve,
    require_formal_terminal_disposition_package,
)
from .formal_terminal_disposition_builder import (
    FormalTerminalDispositionBuild,
    FormalTerminalDispositionBuildError,
    FormalTerminalDispositionRecorder,
    begin_formal_terminal_disposition_recording,
    finalize_formal_terminal_disposition_recording,
    record_formal_terminal_security,
    record_formal_terminal_slot,
    require_formal_terminal_disposition_build,
    require_fresh_formal_terminal_disposition_recorder,
)


class FormalStreamingInputError(ValueError):
    """The physical stream, bounded fit, or formal shard output is invalid."""


class FormalStreamingRefusalReason(str, Enum):
    PHYSICAL_SHARD_CHANGED = "physical_preopen_shard_changed"
    PHYSICAL_SHARD_CENSUS_CHANGED = "physical_preopen_shard_census_changed"
    PHYSICAL_SESSION_CAPACITY_EXCEEDED = "physical_session_capacity_exceeded"
    EVENT_CAPACITY_EXCEEDED = "c2_event_capacity_exceeded"
    CONTRIBUTION_CAPACITY_EXCEEDED = "session_contribution_capacity_exceeded"
    IDENTITY_CAPACITY_EXCEEDED = "retained_identity_capacity_exceeded"
    RETAINED_GRAPH_CAPACITY_EXCEEDED = "retained_input_graph_capacity_exceeded"
    RESOURCE_CENSUS_CAPACITY_EXCEEDED = "disk_resource_census_capacity_exceeded"
    QR_CAPACITY_EXCEEDED = "disk_mgs_capacity_exceeded"
    FORMAL_BLOCK_CAPACITY_EXCEEDED = "formal_session_block_capacity_exceeded"
    FORMAL_OUTPUT_CAPACITY_EXCEEDED = "formal_output_capacity_exceeded"
    C2_EVENT_TERMINAL_MISSING = "c2_event_terminal_missing"
    C2_EVENT_TERMINAL_REFUSED = "c2_event_terminal_refused"
    C2_EVENT_TERMINAL_MISMATCH = "c2_event_terminal_mismatch"
    TRAINING_FIT_UNDERFILLED = "training_fit_underfilled"
    TRAINING_FIT_RANK_DEFICIENT = "training_fit_rank_deficient"
    GLOBAL_COMPARATOR_COVERAGE_UNDERFILLED = (
        "global_comparator_coverage_underfilled"
    )


class FormalStreamingRunRefusal(FormalStreamingInputError):
    """Named fail-closed refusal which never embeds row values."""

    def __init__(self, reason: FormalStreamingRefusalReason, detail: str):
        if type(reason) is not FormalStreamingRefusalReason:
            raise TypeError("streaming refusal reason changed type")
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason.value}: {detail}")


STREAMING_METHOD_ID = "arv2-formal-session-streamed-disk-mgs-qr-v1"
STREAMING_CAPACITY_SCHEMA = "arv2-formal-streaming-capacity-review-v1"
STREAMING_ARCHIVE_SCHEMA = "arv2-physical-preopen-terminal-archive-v1"
PRODUCTION_EVIDENCE_ARCHIVE_SCHEMA = (
    "arv2-physical-production-evidence-terminal-archive-v1"
)
STREAMING_OBSERVED_SCHEMA = "arv2-formal-streaming-observed-capacity-v1"
STREAMING_MODEL_SCHEMA = "arv2-streamed-production-control-model-v1"
STREAMING_FOLD_SCHEMA = "arv2-streamed-production-fold-commitment-v1"
STREAMING_SCORING_SCHEMA = "arv2-formal-streamed-scoring-artifact-v1"
STREAMING_BUILDER_SCHEMA = "arv2-formal-streamed-scoring-builder-v1"
STREAMING_SESSION_BLOCK_SCHEMA = "arv2-formal-streamed-test-session-block-v1"
STREAMING_DISK_ARCHIVE_SCHEMA = "arv2-formal-physical-shard-archive-v1"
STREAMING_FORMAL_CANDIDATE_SCHEMA = "arv2-formal-streamed-input-candidate-v1"
STREAMED_FORMAL_CONTRACT_VARIANT = "arv2-streamed-physical-formal-input-v1"
ECONOMIC_OBSERVATION_KINDS = (
    "non_economic_decision_session",
    "h20_decision_return_interval",
    "h20_runoff_return_interval",
    "terminal_liquidation_cost",
)
STREAM_LAYOUT_ID = "arv2-formal-qc-fold-session-stream-layout-v1"
APPEARANCE_SEED_SEMANTICS = (
    "one_exact_single_session_seed_per_active_decision_contribution"
)
STREAM_ROLE_SORT_KEYS = {
    "formal_contract": ("singleton",),
    "contribution_seeds": (
        "first_active_session_position", "source_view_id", "fold_id",
        "security_id", "seed_id",
    ),
    "decision_joins": (
        "fold_id", "session_position", "source_view_id", "security_id",
    ),
    "economic_joins": ("fold_id", "session_position", "source_view_id"),
    "daily_requirements": ("session", "security_id", "requirement_id"),
    "minute_requirements": (
        "first_active_session_position", "publication_at_utc", "security_id",
        "requirement_id",
    ),
    "terminal_dispositions": ("slot_kind", "slot_id", "horizon"),
}

MAX_CAPACITY_REVIEW_BYTES = 256 * 1024
MAX_PHYSICAL_SHARD_BYTES = 256 * 1024 * 1024
MAX_EVIDENCE_ARCHIVE_SHARD_COUNT = 20_000
MAX_EVIDENCE_ARCHIVE_CHUNK_COMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_EVIDENCE_ARCHIVE_SESSION_TERMINAL_COUNT = 100_000
MAX_EVIDENCE_ARCHIVE_SESSION_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
_DECIMAL_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)
_EMPTY_MERKLE = preopen_io._merkle([])

STREAMING_CAPACITY_LIMIT_NAMES = (
    "max_physical_shard_count",
    "max_physical_chunk_compressed_bytes",
    "max_physical_session_terminal_count",
    "max_physical_session_uncompressed_bytes",
    "max_c2_normalized_row_count",
    "max_retained_institution_count",
    "max_retained_security_count",
    "max_retained_minute_requirement_count",
    "max_retained_input_graph_bytes",
    "max_active_contribution_count_per_arm_session",
    "max_session_contribution_lineage_count",
    "max_industry_level_count_per_arm_fold",
    "max_disk_mgs_width",
    "max_disk_mgs_live_decimal_count",
    "max_disk_mgs_spool_row_count",
    "max_disk_mgs_spool_byte_count",
    "max_disk_mgs_spool_file_count",
    "max_formal_session_block_row_count",
    "max_formal_session_block_uncompressed_bytes",
    "max_formal_shard_row_count",
    "max_formal_shard_uncompressed_bytes",
    "max_formal_shard_count",
    "max_formal_total_compressed_bytes",
    "max_runtime_resource_spool_byte_count",
    "max_daily_requirement_sessions_retained",
    "max_daily_requirement_keys_retained",
    "max_archive_passes_per_fold",
)


def _strict_object(payload: bytes, name: str) -> dict[str, Any]:
    if type(payload) is not bytes or not payload:
        raise FormalStreamingInputError(f"{name} must be nonempty exact bytes")
    try:
        raw = strict_json_loads(payload.decode("utf-8"), name)
    except (UnicodeError, ValueError) as exc:
        raise FormalStreamingInputError(f"{name} is not strict UTF-8 JSON") from exc
    if type(raw) is not dict or canonical_json_bytes(raw) != payload:
        raise FormalStreamingInputError(f"{name} is not one canonical JSON object")
    return raw


def _positive_int(value: object, name: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if type(value) is not int or value < minimum:
        raise FormalStreamingInputError(
            f"{name} must be an exact integer >= {minimum}"
        )
    return value


def _checked_limits(limits: Mapping[str, int]) -> tuple[tuple[str, int], ...]:
    if type(limits) is not dict or tuple(sorted(limits)) != tuple(
        sorted(STREAMING_CAPACITY_LIMIT_NAMES)
    ):
        raise FormalStreamingInputError("streaming capacity limit inventory changed")
    checked = []
    for name in STREAMING_CAPACITY_LIMIT_NAMES:
        value = _positive_int(limits[name], name)
        checked.append((name, value))
    if limits["max_physical_shard_count"] > 100_000:
        raise FormalStreamingInputError("physical shard-count limit exceeds safety ceiling")
    if limits["max_physical_chunk_compressed_bytes"] > 2 * 1024 * 1024 * 1024:
        raise FormalStreamingInputError("physical chunk-byte limit exceeds safety ceiling")
    if limits["max_physical_session_terminal_count"] > 2_000_000:
        raise FormalStreamingInputError("session terminal limit exceeds safety ceiling")
    if limits["max_physical_session_uncompressed_bytes"] > 2 * 1024 * 1024 * 1024:
        raise FormalStreamingInputError("session byte limit exceeds safety ceiling")
    if limits["max_disk_mgs_spool_byte_count"] > 64 * 1024 * 1024 * 1024:
        raise FormalStreamingInputError("MGS spool-byte limit exceeds safety ceiling")
    if limits["max_disk_mgs_spool_file_count"] > 100_000:
        raise FormalStreamingInputError("MGS spool-file limit exceeds safety ceiling")
    if limits["max_retained_input_graph_bytes"] > 64 * 1024 * 1024 * 1024:
        raise FormalStreamingInputError(
            "retained input-graph byte limit exceeds safety ceiling"
        )
    if limits["max_runtime_resource_spool_byte_count"] > 64 * 1024 * 1024 * 1024:
        raise FormalStreamingInputError(
            "runtime resource-spool byte limit exceeds safety ceiling"
        )
    if limits["max_formal_shard_row_count"] > ABSOLUTE_MAX_SHARD_ROWS:
        raise FormalStreamingInputError("formal shard row limit exceeds absolute ceiling")
    if limits["max_formal_shard_uncompressed_bytes"] > ABSOLUTE_MAX_SHARD_UNCOMPRESSED_BYTES:
        raise FormalStreamingInputError("formal shard byte limit exceeds absolute ceiling")
    if limits["max_archive_passes_per_fold"] != 3:
        raise FormalStreamingInputError("streamed scoring requires exactly three passes per fold")
    return tuple(checked)


def _capacity_projection(
    *,
    preopen: PreopenControlAcquisitionReceipt,
    evidence: ProductionEvidenceAcquisitionReceipt,
) -> dict[str, object]:
    descriptors = acquisition_output_shard_descriptor_records(preopen)
    union = {
        row.row_sha256
        for batch in (
            build_production_input_batch(
                evidence.authority, signal_arm=SignalArm.CURRENT_VINTAGE
            ),
            build_production_input_batch(
                evidence.authority, signal_arm=SignalArm.CONSERVATIVE_CENSORED
            ),
        )
        for row in batch.normalized_rows
    }
    maximum_session_count = max(
        (item.terminal_count for item in preopen.control_sessions), default=0
    )
    return {
        "preopen_acquisition_id": preopen.artifact_id,
        "preopen_acquisition_sha256": preopen.artifact_sha256,
        "production_evidence_receipt_id": evidence.receipt_id,
        "production_evidence_receipt_sha256": evidence.receipt_sha256,
        "physical_shard_count": len(descriptors),
        "declared_terminal_count": preopen.control_terminal_count,
        "declared_maximum_session_terminal_count": maximum_session_count,
        "c2_normalized_union_count": len(union),
        "q_data_measurement_projection": (
            acquisition_q_data_measurement_projection_record(preopen)
        ),
        "formal_session_geometry_sha256": FORMAL_SESSION_GEOMETRY_SHA256,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "streaming_method_id": STREAMING_METHOD_ID,
        "algorithmic_disclosure": {
            "session_score_kernel": "byte_identical_shared_legacy_kernel",
            "control_fit": "bounded_disk_spooled_decimal_modified_gram_schmidt_qr_train_active_only",
            "legacy_fit": "decimal_modified_gram_schmidt_qr_train_active_only",
            "coefficient_bytes_expected_identical": True,
            "operation_order_expected_identical": True,
            "rank_threshold_unchanged": _decimal_text(RANK_RELATIVE_THRESHOLD),
            "rounding": "ROUND_HALF_EVEN",
            "precision": 50,
            "formal_seed_packaging": (
                "one_seed_per_active_decision_appearance_to_avoid_full_graph_retention"
            ),
            "score_or_observation_truncation": False,
            "retained_input_graph_measurement": (
                "recursive_exact_python_object_graph_sys_getsizeof_once_per_identity"
            ),
        },
    }


def render_formal_streaming_capacity_review_candidate(
    *,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    production_evidence_receipt: ProductionEvidenceAcquisitionReceipt,
    limits: Mapping[str, int],
) -> bytes:
    """Render a non-authorizing candidate for independent capacity review."""

    try:
        preopen = require_reviewed_preopen_control_acquisition_receipt(
            preopen_acquisition_receipt
        )
        evidence = require_production_evidence_acquisition_receipt(
            production_evidence_receipt
        )
    except (PreopenControlAcquisitionError, ProductionEvidenceAcquisitionError) as exc:
        raise FormalStreamingInputError(
            "streaming capacity parents are not physically authenticated"
        ) from exc
    if evidence.preopen_acquisition_receipt is not preopen:
        raise FormalStreamingInputError(
            "production evidence and streaming capacity do not share pre-open acquisition"
        )
    checked = _checked_limits(limits)
    projection = _capacity_projection(preopen=preopen, evidence=evidence)
    if (
        len(acquisition_output_shard_descriptor_records(preopen))
        > dict(checked)["max_physical_shard_count"]
        or preopen.control_terminal_count
        > dict(checked)["max_physical_session_terminal_count"]
        * max(1, len(preopen.control_sessions))
        or projection["declared_maximum_session_terminal_count"]
        > dict(checked)["max_physical_session_terminal_count"]
        or projection["c2_normalized_union_count"]
        > dict(checked)["max_c2_normalized_row_count"]
    ):
        raise FormalStreamingInputError(
            "proposed streaming limits are below authenticated source geometry"
        )
    return canonical_json_bytes(
        {
            "schema": STREAMING_CAPACITY_SCHEMA,
            "status": "review_required_not_authorized",
            "receipt_id": None,
            "receipt_sha256": None,
            "source_projection": projection,
            "limits": dict(checked),
            "representative_full_census_verified": False,
            "physical_replay_geometry_verified": False,
            "disk_spooled_mgs_peak_model_verified": False,
            "bounded_formal_shard_builder_verified": False,
            "no_caller_authored_score_or_peak_claim_verified": False,
            "retained_input_graph_peak_verified": False,
            "outcome_or_qc_action_authorized": False,
        }
    )


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class FormalStreamingCapacityBinding:
    receipt_id: str
    receipt_sha256: str
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt
    production_evidence_receipt: ProductionEvidenceAcquisitionReceipt
    source_projection_sha256: str
    limits: tuple[tuple[str, int], ...]
    review_receipt_bytes: bytes = dataclasses.field(repr=False)
    representative_full_census_verified: bool = True
    physical_replay_geometry_verified: bool = True
    disk_spooled_mgs_peak_model_verified: bool = True
    bounded_formal_shard_builder_verified: bool = True
    no_caller_authored_score_or_peak_claim_verified: bool = True
    retained_input_graph_peak_verified: bool = True
    outcome_or_qc_action_authorized: bool = False

    @property
    def qc_launch_available(self) -> bool:
        return False


_CAPACITY_BINDINGS: dict[
    int, tuple[weakref.ReferenceType[FormalStreamingCapacityBinding], tuple[object, ...]]
] = {}
_CAPACITY_LOCK = threading.RLock()


def _make_capacity_binding_authority():
    records: dict[
        int,
        tuple[
            tuple[
                weakref.ReferenceType[FormalStreamingCapacityBinding],
                tuple[object, ...],
            ],
            bytes,
            int,
        ],
    ] = {}

    def forget(identity: int, reference: object) -> None:
        with _CAPACITY_LOCK:
            private = records.get(identity)
            if private is not None and private[0][0] is reference:
                records.pop(identity, None)
                if _CAPACITY_BINDINGS.get(identity) is private[0]:
                    _CAPACITY_BINDINGS.pop(identity, None)

    def register(
        value: FormalStreamingCapacityBinding,
        fingerprint: tuple[object, ...],
        reviewed_record: bytes,
    ) -> None:
        identity = id(value)
        reference = weakref.ref(
            value, lambda ref, key=identity: forget(key, ref)
        )
        public = (reference, fingerprint)
        with _CAPACITY_LOCK:
            if identity in records or identity in _CAPACITY_BINDINGS:
                raise FormalStreamingInputError(
                    "streaming capacity identity was reused"
                )
            records[identity] = (public, reviewed_record, os.getpid())
            _CAPACITY_BINDINGS[identity] = public

    def current(
        value: FormalStreamingCapacityBinding,
    ) -> tuple[object, ...] | None:
        identity = id(value)
        with _CAPACITY_LOCK:
            private = records.get(identity)
            public = _CAPACITY_BINDINGS.get(identity)
            if (
                private is None
                or public is not private[0]
                or private[0][0]() is not value
                or private[2] != os.getpid()
            ):
                records.pop(identity, None)
                _CAPACITY_BINDINGS.pop(identity, None)
                return None
            return private

    def reset_after_fork() -> None:
        global _CAPACITY_BINDINGS, _CAPACITY_LOCK

        records.clear()
        _CAPACITY_BINDINGS = {}
        _CAPACITY_LOCK = threading.RLock()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)
    return register, current


(
    _capacity_authority_register,
    _capacity_authority_current,
) = _make_capacity_binding_authority()


def _read_private_regular(
    path: Path, *, maximum_bytes: int, name: str
) -> tuple[bytes, tuple[object, ...]]:
    if type(path) is not type(Path()) or not path.is_absolute() or path.is_symlink():
        raise FormalStreamingInputError(f"{name} must be an absolute nonsymlink Path")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FormalStreamingInputError(f"{name} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > maximum_bytes
            or (
                os.name != "nt"
                and (
                    stat.S_IMODE(before.st_mode) != 0o600
                    or (hasattr(os, "getuid") and before.st_uid != os.getuid())
                )
            )
        ):
            raise FormalStreamingInputError(
                f"{name} is not an owned private bounded regular file"
            )
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        fingerprint = (
            str(path), after.st_dev, after.st_ino, after.st_size,
            after.st_mtime_ns, after.st_ctime_ns,
        )
        if (
            len(payload) != before.st_size
            or len(payload) > maximum_bytes
            or tuple(
                getattr(before, name)
                for name in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            )
            != tuple(
                getattr(after, name)
                for name in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            )
        ):
            raise FormalStreamingInputError(f"{name} changed while read")
    finally:
        os.close(descriptor)
    return payload, fingerprint


def _load_formal_streaming_capacity_binding_impl(
    *,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    production_evidence_receipt: ProductionEvidenceAcquisitionReceipt,
    limits: Mapping[str, int],
    reviewed_receipt_path: Path,
    _authority_register: object,
) -> FormalStreamingCapacityBinding:
    """Load one independently edited private affirmative capacity receipt."""

    candidate = render_formal_streaming_capacity_review_candidate(
        preopen_acquisition_receipt=preopen_acquisition_receipt,
        production_evidence_receipt=production_evidence_receipt,
        limits=limits,
    )
    payload, _fingerprint = _read_private_regular(
        reviewed_receipt_path,
        maximum_bytes=MAX_CAPACITY_REVIEW_BYTES,
        name="streaming capacity review receipt",
    )
    raw = _strict_object(payload, "streaming capacity review receipt")
    candidate_raw = _strict_object(candidate, "streaming capacity candidate")
    if set(raw) != set(candidate_raw):
        raise FormalStreamingInputError("streaming capacity receipt fields changed")
    semantic = dict(raw)
    supplied_id = semantic["receipt_id"]
    supplied_sha = semantic["receipt_sha256"]
    semantic["receipt_id"] = None
    semantic["receipt_sha256"] = None
    digest = sha256_bytes(canonical_json_bytes(semantic))
    if (
        raw["status"] != "independently_reviewed_streaming_capacity_affirmative"
        or supplied_id != f"arv2-formal-streaming-capacity-{digest[:24]}"
        or supplied_sha != digest
        or raw["source_projection"] != candidate_raw["source_projection"]
        or raw["limits"] != candidate_raw["limits"]
        or any(
            raw[name] is not True
            for name in (
                "representative_full_census_verified",
                "physical_replay_geometry_verified",
                "disk_spooled_mgs_peak_model_verified",
                "bounded_formal_shard_builder_verified",
                "no_caller_authored_score_or_peak_claim_verified",
                "retained_input_graph_peak_verified",
            )
        )
        or raw["outcome_or_qc_action_authorized"] is not False
    ):
        raise FormalStreamingInputError(
            "streaming capacity receipt is not an independent affirmative review"
        )
    value = FormalStreamingCapacityBinding(
        receipt_id=str(supplied_id),
        receipt_sha256=str(supplied_sha),
        preopen_acquisition_receipt=preopen_acquisition_receipt,
        production_evidence_receipt=production_evidence_receipt,
        source_projection_sha256=sha256_bytes(
            canonical_json_bytes(raw["source_projection"])
        ),
        limits=_checked_limits(limits),
        review_receipt_bytes=payload,
    )
    fingerprint = (
        id(preopen_acquisition_receipt),
        id(production_evidence_receipt),
        id(value.limits),
        id(value.review_receipt_bytes),
        canonical_json_bytes(raw),
    )
    _authority_register(value, fingerprint, canonical_json_bytes(raw))
    return value


def _require_formal_streaming_capacity_binding_impl(
    value: FormalStreamingCapacityBinding,
    *,
    _authority_current: object,
) -> FormalStreamingCapacityBinding:
    if type(value) is not FormalStreamingCapacityBinding:
        raise FormalStreamingInputError("streaming capacity binding changed type")
    private = _authority_current(value)
    if private is None:
        raise FormalStreamingInputError(
            "streaming capacity is not physically loader-authenticated"
        )
    registered = private[0]
    try:
        preopen = require_reviewed_preopen_control_acquisition_receipt(
            value.preopen_acquisition_receipt
        )
        evidence = require_production_evidence_acquisition_receipt(
            value.production_evidence_receipt
        )
        raw = _strict_object(
            value.review_receipt_bytes, "streaming capacity review receipt"
        )
    except (PreopenControlAcquisitionError, ProductionEvidenceAcquisitionError) as exc:
        raise FormalStreamingInputError("streaming capacity parent changed") from exc
    flags = (
        value.representative_full_census_verified,
        value.physical_replay_geometry_verified,
        value.disk_spooled_mgs_peak_model_verified,
        value.bounded_formal_shard_builder_verified,
        value.no_caller_authored_score_or_peak_claim_verified,
        value.retained_input_graph_peak_verified,
    )
    fingerprint = (
        id(preopen), id(evidence), id(value.limits), id(value.review_receipt_bytes),
        canonical_json_bytes(raw),
    )
    if (
        evidence.preopen_acquisition_receipt is not preopen
        or registered[1] != fingerprint
        or private[1] != canonical_json_bytes(raw)
        or private[2] != os.getpid()
        or value.limits != _checked_limits(dict(value.limits))
        or dict(value.limits) != raw.get("limits")
        or any(type(flag) is not bool or flag is not True for flag in flags)
        or type(value.outcome_or_qc_action_authorized) is not bool
        or value.outcome_or_qc_action_authorized is not False
        or value.qc_launch_available is not False
        or value.receipt_id != raw.get("receipt_id")
        or value.receipt_sha256 != raw.get("receipt_sha256")
        or value.source_projection_sha256
        != sha256_bytes(canonical_json_bytes(raw.get("source_projection")))
    ):
        raise FormalStreamingInputError("streaming capacity changed after review")
    return value


def _bind_capacity_binding_authority(
    *,
    load_impl: object,
    require_impl: object,
    register: object,
    current: object,
) -> tuple[object, object]:
    def load(
        *,
        preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
        production_evidence_receipt: ProductionEvidenceAcquisitionReceipt,
        limits: Mapping[str, int],
        reviewed_receipt_path: Path,
    ) -> FormalStreamingCapacityBinding:
        value = load_impl(
            preopen_acquisition_receipt=preopen_acquisition_receipt,
            production_evidence_receipt=production_evidence_receipt,
            limits=limits,
            reviewed_receipt_path=reviewed_receipt_path,
            _authority_register=register,
        )
        return require_impl(value, _authority_current=current)

    def require(
        value: FormalStreamingCapacityBinding,
    ) -> FormalStreamingCapacityBinding:
        return require_impl(value, _authority_current=current)

    return load, require


(
    load_formal_streaming_capacity_binding,
    require_formal_streaming_capacity_binding,
) = _bind_capacity_binding_authority(
    load_impl=_load_formal_streaming_capacity_binding_impl,
    require_impl=_require_formal_streaming_capacity_binding_impl,
    register=_capacity_authority_register,
    current=_capacity_authority_current,
)

del _bind_capacity_binding_authority
del _load_formal_streaming_capacity_binding_impl
del _require_formal_streaming_capacity_binding_impl
del _capacity_authority_register
del _capacity_authority_current
del _make_capacity_binding_authority


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PhysicalPreopenTerminalArchive:
    archive_id: str
    archive_sha256: str
    schema: str
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt
    capacity: FormalStreamingCapacityBinding
    shard_paths: tuple[Path, ...] = dataclasses.field(repr=False)
    path_fingerprints: tuple[tuple[object, ...], ...] = dataclasses.field(repr=False)
    descriptor_projection_sha256: str
    physical_payload_projection_sha256: str
    terminal_count: int
    accepted_count: int
    refusal_count: int
    filesystem_access_retained: bool = False
    provider_access: bool = False
    outcome_access: bool = False
    quantconnect_access: bool = False


_ARCHIVES: dict[
    int, tuple[weakref.ReferenceType[PhysicalPreopenTerminalArchive], tuple[object, ...]]
] = {}
_ARCHIVE_LOCK = threading.RLock()


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PhysicalProductionEvidenceTerminalArchive:
    """A fixed-hard-bound pre-open archive usable before C2 review exists.

    The formal streaming archive is intentionally tied to a reviewed C2
    capacity receipt.  Production-evidence composition necessarily precedes
    that receipt, so this additive archive authenticates the same physical
    files under immutable, conservative host ceilings and grants no formal-run
    authority.
    """

    archive_id: str
    archive_sha256: str
    schema: str
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt
    shard_paths: tuple[Path, ...] = dataclasses.field(repr=False)
    path_fingerprints: tuple[tuple[object, ...], ...] = dataclasses.field(repr=False)
    descriptor_projection_sha256: str
    physical_payload_projection_sha256: str
    terminal_count: int
    accepted_count: int
    refusal_count: int
    filesystem_access_retained: bool = False
    provider_access: bool = False
    outcome_access: bool = False
    quantconnect_access: bool = False
    formal_run_authority: bool = False


_EVIDENCE_ARCHIVES: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalProductionEvidenceTerminalArchive],
        tuple[object, ...],
    ],
] = {}
_EVIDENCE_ARCHIVE_LOCK = threading.RLock()


def _forget_evidence_archive(identity: int, reference: object) -> None:
    with _EVIDENCE_ARCHIVE_LOCK:
        current = _EVIDENCE_ARCHIVES.get(identity)
        if current is not None and current[0] is reference:
            _EVIDENCE_ARCHIVES.pop(identity, None)


def _forget_archive(identity: int, reference: object) -> None:
    with _ARCHIVE_LOCK:
        current = _ARCHIVES.get(identity)
        if current is not None and current[0] is reference:
            _ARCHIVES.pop(identity, None)


def load_physical_preopen_terminal_archive(
    *,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    capacity: FormalStreamingCapacityBinding,
    shard_paths: tuple[Path, ...],
) -> PhysicalPreopenTerminalArchive:
    """Authenticate exact private files and mint a re-iterable archive."""

    preopen = require_reviewed_preopen_control_acquisition_receipt(
        preopen_acquisition_receipt
    )
    capacity = require_formal_streaming_capacity_binding(capacity)
    if capacity.preopen_acquisition_receipt is not preopen:
        raise FormalStreamingInputError("archive and capacity pre-open parents differ")
    descriptors = acquisition_output_shard_descriptor_records(preopen)
    limits = dict(capacity.limits)
    if (
        type(shard_paths) is not tuple
        or len(shard_paths) != len(descriptors)
        or len(shard_paths) > limits["max_physical_shard_count"]
    ):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.PHYSICAL_SHARD_CENSUS_CHANGED,
            "private shard-path census differs from the reviewed descriptor census",
        )
    fingerprints: list[tuple[object, ...]] = []

    def iter_authenticated_payloads() -> Iterator[bytes]:
        for ordinal, (path, descriptor) in enumerate(
            zip(shard_paths, descriptors, strict=True)
        ):
            maximum = min(
                MAX_PHYSICAL_SHARD_BYTES,
                _positive_int(
                    descriptor["compressed_byte_count"],
                    f"physical shard {ordinal} byte count",
                ),
            )
            payload, fingerprint = _read_private_regular(
                path,
                maximum_bytes=maximum,
                name=f"physical pre-open shard {ordinal}",
            )
            if (
                len(payload) != descriptor["compressed_byte_count"]
                or sha256_bytes(payload) != descriptor["compressed_sha256"]
            ):
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED,
                    f"physical pre-open shard {ordinal} does not match its reviewed descriptor",
                )
            fingerprints.append(fingerprint)
            yield payload

    try:
        projection, totals = preopen_io._validated_batch_major_output_payloads(
            _strict_object(preopen.output_manifest_bytes, "pre-open output manifest"),
            iter_authenticated_payloads(),
        )
    except (preopen_io.PreopenControlAcquisitionIoError, TypeError, ValueError) as exc:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.PHYSICAL_SHARD_CENSUS_CHANGED,
            "physical pre-open archive failed complete logical validation",
        ) from exc
    if projection != preopen.output_shard_payload_projection_sha256:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED,
            "physical payload projection differs from the acquisition receipt",
        )
    descriptor_sha = sha256_bytes(canonical_json_bytes(list(descriptors)))
    seed = {
        "schema": STREAMING_ARCHIVE_SCHEMA,
        "preopen_acquisition_id": preopen.artifact_id,
        "preopen_acquisition_sha256": preopen.artifact_sha256,
        "capacity_receipt_id": capacity.receipt_id,
        "capacity_receipt_sha256": capacity.receipt_sha256,
        "descriptor_projection_sha256": descriptor_sha,
        "physical_payload_projection_sha256": projection,
        **totals,
        "shard_count": len(descriptors),
        "replayable_private_regular_files": True,
        "outcome_or_qc_action_authorized": False,
    }
    digest = sha256_bytes(canonical_json_bytes(seed))
    value = PhysicalPreopenTerminalArchive(
        archive_id=f"arv2-physical-preopen-archive-{digest[:24]}",
        archive_sha256=digest,
        schema=STREAMING_ARCHIVE_SCHEMA,
        preopen_acquisition_receipt=preopen,
        capacity=capacity,
        shard_paths=shard_paths,
        path_fingerprints=tuple(fingerprints),
        descriptor_projection_sha256=descriptor_sha,
        physical_payload_projection_sha256=projection,
        terminal_count=totals["terminal_count"],
        accepted_count=totals["accepted_count"],
        refusal_count=totals["refusal_count"],
    )
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget_archive(key, ref))
    fingerprint = (
        id(preopen), id(capacity), id(value.shard_paths),
        tuple(id(item) for item in value.shard_paths), id(value.path_fingerprints),
        seed,
    )
    with _ARCHIVE_LOCK:
        _ARCHIVES[identity] = (reference, fingerprint)
    return require_physical_preopen_terminal_archive(value)


def require_physical_preopen_terminal_archive(
    value: PhysicalPreopenTerminalArchive,
) -> PhysicalPreopenTerminalArchive:
    if type(value) is not PhysicalPreopenTerminalArchive:
        raise FormalStreamingInputError("physical archive changed type")
    with _ARCHIVE_LOCK:
        registered = _ARCHIVES.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalStreamingInputError("physical archive is not loader-authenticated")
    preopen = require_reviewed_preopen_control_acquisition_receipt(
        value.preopen_acquisition_receipt
    )
    capacity = require_formal_streaming_capacity_binding(value.capacity)
    descriptors = acquisition_output_shard_descriptor_records(preopen)
    seed = {
        "schema": STREAMING_ARCHIVE_SCHEMA,
        "preopen_acquisition_id": preopen.artifact_id,
        "preopen_acquisition_sha256": preopen.artifact_sha256,
        "capacity_receipt_id": capacity.receipt_id,
        "capacity_receipt_sha256": capacity.receipt_sha256,
        "descriptor_projection_sha256": sha256_bytes(
            canonical_json_bytes(list(descriptors))
        ),
        "physical_payload_projection_sha256": value.physical_payload_projection_sha256,
        "terminal_count": value.terminal_count,
        "accepted_count": value.accepted_count,
        "refusal_count": value.refusal_count,
        "shard_count": len(descriptors),
        "replayable_private_regular_files": True,
        "outcome_or_qc_action_authorized": False,
    }
    fingerprint = (
        id(preopen), id(capacity), id(value.shard_paths),
        tuple(id(item) for item in value.shard_paths), id(value.path_fingerprints), seed,
    )
    if (
        registered[1] != fingerprint
        or value.schema != STREAMING_ARCHIVE_SCHEMA
        or value.archive_sha256 != sha256_bytes(canonical_json_bytes(seed))
        or value.archive_id != f"arv2-physical-preopen-archive-{value.archive_sha256[:24]}"
        or value.descriptor_projection_sha256
        != sha256_bytes(canonical_json_bytes(list(descriptors)))
        or value.terminal_count != preopen.control_terminal_count
        or value.accepted_count != preopen.control_accepted_count
        or value.refusal_count != preopen.control_refusal_count
        or any(
            type(flag) is not bool or flag
            for flag in (
                value.filesystem_access_retained, value.provider_access,
                value.outcome_access, value.quantconnect_access,
            )
        )
    ):
        raise FormalStreamingInputError("physical archive changed after authentication")
    for path, expected in zip(value.shard_paths, value.path_fingerprints, strict=True):
        try:
            observed = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise FormalStreamingInputError("physical archive file is unavailable") from exc
        current = (
            str(path), observed.st_dev, observed.st_ino, observed.st_size,
            observed.st_mtime_ns, observed.st_ctime_ns,
        )
        if path.is_symlink() or current != expected:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED,
                "physical pre-open shard identity changed after archive load",
            )
    return value


def load_physical_production_evidence_terminal_archive(
    *,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    shard_paths: tuple[Path, ...],
) -> PhysicalProductionEvidenceTerminalArchive:
    """Authenticate pre-open outputs for the strictly earlier C2 composition step.

    This boundary intentionally does not accept a caller capacity claim and
    cannot be used as a formal streaming archive.  Its ceilings are immutable
    module constants, while every count/hash is derived from reviewed manifest
    bytes and exact private files.
    """

    preopen = require_reviewed_preopen_control_acquisition_receipt(
        preopen_acquisition_receipt
    )
    descriptors = acquisition_output_shard_descriptor_records(preopen)
    if (
        type(shard_paths) is not tuple
        or len(shard_paths) != len(descriptors)
        or not shard_paths
        or len(shard_paths) > MAX_EVIDENCE_ARCHIVE_SHARD_COUNT
    ):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.PHYSICAL_SHARD_CENSUS_CHANGED,
            "production-evidence shard-path census differs from reviewed output",
        )
    fingerprints: list[tuple[object, ...]] = []

    def iter_authenticated_payloads() -> Iterator[bytes]:
        for ordinal, (path, descriptor) in enumerate(
            zip(shard_paths, descriptors, strict=True)
        ):
            expected = _positive_int(
                descriptor["compressed_byte_count"],
                f"production-evidence physical shard {ordinal} byte count",
            )
            if expected > MAX_PHYSICAL_SHARD_BYTES:
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.PHYSICAL_SESSION_CAPACITY_EXCEEDED,
                    "one production-evidence physical shard exceeds the fixed ceiling",
                )
            payload, fingerprint = _read_private_regular(
                path,
                maximum_bytes=expected,
                name=f"production-evidence physical pre-open shard {ordinal}",
            )
            if len(payload) != expected or sha256_bytes(payload) != descriptor[
                "compressed_sha256"
            ]:
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED,
                    f"production-evidence physical shard {ordinal} changed",
                )
            fingerprints.append(fingerprint)
            yield payload

    try:
        projection, totals = preopen_io._validated_batch_major_output_payloads(
            _strict_object(preopen.output_manifest_bytes, "pre-open output manifest"),
            iter_authenticated_payloads(),
        )
    except (preopen_io.PreopenControlAcquisitionIoError, TypeError, ValueError) as exc:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.PHYSICAL_SHARD_CENSUS_CHANGED,
            "production-evidence archive failed complete logical validation",
        ) from exc
    if projection != preopen.output_shard_payload_projection_sha256:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED,
            "production-evidence physical projection differs from reviewed receipt",
        )
    descriptor_sha = sha256_bytes(canonical_json_bytes(list(descriptors)))
    seed = {
        "schema": PRODUCTION_EVIDENCE_ARCHIVE_SCHEMA,
        "preopen_acquisition_id": preopen.artifact_id,
        "preopen_acquisition_sha256": preopen.artifact_sha256,
        "descriptor_projection_sha256": descriptor_sha,
        "physical_payload_projection_sha256": projection,
        **totals,
        "shard_count": len(descriptors),
        "fixed_hard_capacity": {
            "max_shard_count": MAX_EVIDENCE_ARCHIVE_SHARD_COUNT,
            "max_chunk_compressed_bytes": MAX_EVIDENCE_ARCHIVE_CHUNK_COMPRESSED_BYTES,
            "max_session_terminal_count": MAX_EVIDENCE_ARCHIVE_SESSION_TERMINAL_COUNT,
            "max_session_uncompressed_bytes": MAX_EVIDENCE_ARCHIVE_SESSION_UNCOMPRESSED_BYTES,
        },
        "formal_run_authority": False,
        "outcome_or_qc_action_authorized": False,
    }
    digest = sha256_bytes(canonical_json_bytes(seed))
    value = PhysicalProductionEvidenceTerminalArchive(
        archive_id=f"arv2-physical-production-evidence-archive-{digest[:24]}",
        archive_sha256=digest,
        schema=PRODUCTION_EVIDENCE_ARCHIVE_SCHEMA,
        preopen_acquisition_receipt=preopen,
        shard_paths=shard_paths,
        path_fingerprints=tuple(fingerprints),
        descriptor_projection_sha256=descriptor_sha,
        physical_payload_projection_sha256=projection,
        terminal_count=totals["terminal_count"],
        accepted_count=totals["accepted_count"],
        refusal_count=totals["refusal_count"],
    )
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_evidence_archive(key, ref)
    )
    fingerprint = (
        id(preopen),
        id(value.shard_paths),
        tuple(id(item) for item in value.shard_paths),
        id(value.path_fingerprints),
        seed,
    )
    with _EVIDENCE_ARCHIVE_LOCK:
        _EVIDENCE_ARCHIVES[identity] = (reference, fingerprint)
    return require_physical_production_evidence_terminal_archive(value)


def require_physical_production_evidence_terminal_archive(
    value: PhysicalProductionEvidenceTerminalArchive,
) -> PhysicalProductionEvidenceTerminalArchive:
    if type(value) is not PhysicalProductionEvidenceTerminalArchive:
        raise FormalStreamingInputError(
            "production-evidence physical archive changed type"
        )
    with _EVIDENCE_ARCHIVE_LOCK:
        registered = _EVIDENCE_ARCHIVES.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalStreamingInputError(
            "production-evidence physical archive is not loader-authenticated"
        )
    preopen = require_reviewed_preopen_control_acquisition_receipt(
        value.preopen_acquisition_receipt
    )
    descriptors = acquisition_output_shard_descriptor_records(preopen)
    seed = {
        "schema": PRODUCTION_EVIDENCE_ARCHIVE_SCHEMA,
        "preopen_acquisition_id": preopen.artifact_id,
        "preopen_acquisition_sha256": preopen.artifact_sha256,
        "descriptor_projection_sha256": sha256_bytes(
            canonical_json_bytes(list(descriptors))
        ),
        "physical_payload_projection_sha256": value.physical_payload_projection_sha256,
        "terminal_count": value.terminal_count,
        "accepted_count": value.accepted_count,
        "refusal_count": value.refusal_count,
        "shard_count": len(descriptors),
        "fixed_hard_capacity": {
            "max_shard_count": MAX_EVIDENCE_ARCHIVE_SHARD_COUNT,
            "max_chunk_compressed_bytes": MAX_EVIDENCE_ARCHIVE_CHUNK_COMPRESSED_BYTES,
            "max_session_terminal_count": MAX_EVIDENCE_ARCHIVE_SESSION_TERMINAL_COUNT,
            "max_session_uncompressed_bytes": MAX_EVIDENCE_ARCHIVE_SESSION_UNCOMPRESSED_BYTES,
        },
        "formal_run_authority": False,
        "outcome_or_qc_action_authorized": False,
    }
    fingerprint = (
        id(preopen),
        id(value.shard_paths),
        tuple(id(item) for item in value.shard_paths),
        id(value.path_fingerprints),
        seed,
    )
    if (
        registered[1] != fingerprint
        or value.schema != PRODUCTION_EVIDENCE_ARCHIVE_SCHEMA
        or value.archive_sha256 != sha256_bytes(canonical_json_bytes(seed))
        or value.archive_id
        != f"arv2-physical-production-evidence-archive-{value.archive_sha256[:24]}"
        or value.descriptor_projection_sha256
        != sha256_bytes(canonical_json_bytes(list(descriptors)))
        or value.terminal_count != preopen.control_terminal_count
        or value.accepted_count != preopen.control_accepted_count
        or value.refusal_count != preopen.control_refusal_count
        or len(value.shard_paths) != len(descriptors)
        or len(value.shard_paths) > MAX_EVIDENCE_ARCHIVE_SHARD_COUNT
        or any(
            type(flag) is not bool or flag
            for flag in (
                value.filesystem_access_retained,
                value.provider_access,
                value.outcome_access,
                value.quantconnect_access,
                value.formal_run_authority,
            )
        )
    ):
        raise FormalStreamingInputError(
            "production-evidence physical archive changed after authentication"
        )
    for path, expected in zip(
        value.shard_paths, value.path_fingerprints, strict=True
    ):
        try:
            observed = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise FormalStreamingInputError(
                "production-evidence physical archive file is unavailable"
            ) from exc
        current = (
            str(path), observed.st_dev, observed.st_ino, observed.st_size,
            observed.st_mtime_ns, observed.st_ctime_ns,
        )
        if path.is_symlink() or current != expected:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED,
                "production-evidence physical archive file identity changed",
            )
    return value


def _parse_controls(value: object) -> ProductionControlVector:
    if type(value) is not list or len(value) != len(CONTROL_COLUMNS):
        raise FormalStreamingInputError("physical control vector changed shape")
    parsed: list[tuple[str, object]] = []
    for index, raw in enumerate(value):
        if type(raw) is not list or len(raw) != 2 or raw[0] != CONTROL_COLUMNS[index]:
            raise FormalStreamingInputError("physical control vector changed order")
        if index < len(CONTROL_COLUMNS) - 6:
            if type(raw[1]) is not str:
                raise FormalStreamingInputError("physical continuous control changed type")
            try:
                numeric: object = Decimal(raw[1])
            except (InvalidOperation, ValueError) as exc:
                raise FormalStreamingInputError("physical control is not Decimal") from exc
        else:
            numeric = raw[1]
        parsed.append((raw[0], numeric))
    return ProductionControlVector(tuple(parsed))


def _eligible_from_record(raw: object) -> EligibleSecuritySession:
    if type(raw) is not dict:
        raise FormalStreamingInputError("accepted physical terminal lost eligible row")
    expected = {
        "decision_session", "security_id", "issuer_id", "share_class_id",
        "listing_id", "historical_ticker", "sector_id", "industry_id",
        "q_data", "controls", "source_id", "source_sha256",
        "identity_evidence_sha256", "identity_available_at",
        "classification_evidence_sha256", "classification_available_at",
        "q_data_evidence_sha256", "q_data_available_at",
        "control_evidence_sha256", "control_available_at",
        "control_vector_sha256", "point_in_time", "evidence_sha256",
        "earnings_anchor_signed_session_distance",
    }
    if set(raw) != expected or type(raw["q_data"]) is not str:
        raise FormalStreamingInputError("eligible physical row fields changed")
    controls = _parse_controls(raw["controls"])
    try:
        built = build_eligible_security_session(
            decision_session=raw["decision_session"],
            security_id=raw["security_id"],
            issuer_id=raw["issuer_id"],
            share_class_id=raw["share_class_id"],
            listing_id=raw["listing_id"],
            historical_ticker=raw["historical_ticker"],
            sector_id=raw["sector_id"],
            industry_id=raw["industry_id"],
            q_data=Decimal(raw["q_data"]),
            controls=controls,
            source_id=raw["source_id"],
            source_sha256=raw["source_sha256"],
            identity_evidence_sha256=raw["identity_evidence_sha256"],
            identity_available_at=raw["identity_available_at"],
            classification_evidence_sha256=raw["classification_evidence_sha256"],
            classification_available_at=raw["classification_available_at"],
            q_data_evidence_sha256=raw["q_data_evidence_sha256"],
            q_data_available_at=raw["q_data_available_at"],
            control_evidence_sha256=raw["control_evidence_sha256"],
            control_available_at=raw["control_available_at"],
            earnings_anchor_signed_session_distance=(
                raw["earnings_anchor_signed_session_distance"]
            ),
        )
    except (ArithmeticError, ProductionScoringError, TypeError, ValueError) as exc:
        raise FormalStreamingInputError("eligible physical row cannot be reconstructed") from exc
    if built.to_record() != raw:
        raise FormalStreamingInputError("eligible physical row content identity changed")
    return built


def _refusal_from_record(raw: object) -> EligibleSecuritySessionRefusal:
    if type(raw) is not dict:
        raise FormalStreamingInputError("refused physical terminal lost refusal row")
    expected = {
        "decision_session", "security_id", "issuer_id", "share_class_id",
        "listing_id", "historical_ticker", "reason", "source_id",
        "source_sha256", "available_at", "refusal_sha256",
    }
    if set(raw) != expected:
        raise FormalStreamingInputError("physical census refusal fields changed")
    try:
        built = build_eligible_security_session_refusal(
            decision_session=raw["decision_session"],
            security_id=raw["security_id"],
            issuer_id=raw["issuer_id"],
            share_class_id=raw["share_class_id"],
            listing_id=raw["listing_id"],
            historical_ticker=raw["historical_ticker"],
            reason=CensusRefusalReason(raw["reason"]),
            source_id=raw["source_id"],
            source_sha256=raw["source_sha256"],
            available_at=raw["available_at"],
        )
    except (ProductionScoringError, TypeError, ValueError) as exc:
        raise FormalStreamingInputError("physical census refusal cannot be reconstructed") from exc
    if built.to_record() != raw:
        raise FormalStreamingInputError("physical census refusal identity changed")
    return built


@dataclasses.dataclass(frozen=True)
class PhysicalTerminalSessionBlock:
    decision_session: str
    accepted: tuple[EligibleSecuritySession, ...]
    refused: tuple[EligibleSecuritySessionRefusal, ...]
    terminal_count: int
    control_terminal_merkle_root: str
    universe_terminal_merkle_root: str
    raw_byte_count: int


def _read_archive_payload(
    archive: PhysicalPreopenTerminalArchive
    | PhysicalProductionEvidenceTerminalArchive,
    index: int,
    descriptor: Mapping[str, object],
) -> bytes:
    payload, fingerprint = _read_private_regular(
        archive.shard_paths[index],
        maximum_bytes=min(
            MAX_PHYSICAL_SHARD_BYTES,
            _positive_int(descriptor["compressed_byte_count"], "physical shard bytes"),
        ),
        name=f"physical pre-open shard {index}",
    )
    if (
        fingerprint != archive.path_fingerprints[index]
        or len(payload) != descriptor["compressed_byte_count"]
        or sha256_bytes(payload) != descriptor["compressed_sha256"]
    ):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED,
            f"physical pre-open shard {index} changed during replay",
        )
    return payload


def _physical_archive_limits(
    archive: PhysicalPreopenTerminalArchive
    | PhysicalProductionEvidenceTerminalArchive,
) -> Mapping[str, int]:
    if type(archive) is PhysicalPreopenTerminalArchive:
        require_physical_preopen_terminal_archive(archive)
        return archive.capacity.limits
    if type(archive) is PhysicalProductionEvidenceTerminalArchive:
        require_physical_production_evidence_terminal_archive(archive)
        return {
            "max_physical_chunk_compressed_bytes": (
                MAX_EVIDENCE_ARCHIVE_CHUNK_COMPRESSED_BYTES
            ),
            "max_physical_session_terminal_count": (
                MAX_EVIDENCE_ARCHIVE_SESSION_TERMINAL_COUNT
            ),
            "max_physical_session_uncompressed_bytes": (
                MAX_EVIDENCE_ARCHIVE_SESSION_UNCOMPRESSED_BYTES
            ),
        }
    raise FormalStreamingInputError("physical archive changed type")


def _iter_physical_terminal_sessions(
    archive: PhysicalPreopenTerminalArchive
    | PhysicalProductionEvidenceTerminalArchive,
) -> Iterator[PhysicalTerminalSessionBlock]:
    """Replay and reauthenticate every declared session, including exact zeroes."""

    if type(archive) is PhysicalPreopenTerminalArchive:
        archive = require_physical_preopen_terminal_archive(archive)
    elif type(archive) is PhysicalProductionEvidenceTerminalArchive:
        archive = require_physical_production_evidence_terminal_archive(archive)
    else:
        raise FormalStreamingInputError("physical archive changed type")
    preopen = archive.preopen_acquisition_receipt
    manifest = _strict_object(preopen.output_manifest_bytes, "pre-open output manifest")
    descriptors = list(acquisition_output_shard_descriptor_records(preopen))
    limits = dict(_physical_archive_limits(archive))
    commitments = {item.decision_session: item for item in preopen.control_sessions}
    universe = {item.decision_session: item for item in preopen.universe_sessions}
    declared_sessions = tuple(commitments)
    if declared_sessions != tuple(sorted(declared_sessions)) or set(commitments) != set(universe):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.PHYSICAL_SHARD_CENSUS_CHANGED,
            "reviewed pre-open session commitments changed order or census",
        )
    physical_records: list[dict[str, object]] = []
    quality = hashlib.sha256()
    quality.update(b'{"measurements":[')
    quality_first = True
    quality_count = 0
    yielded_count = accepted_count = refusal_count = 0
    session_index = 0
    pending_rows: list[dict[str, object]] = []
    pending_raw_bytes = 0
    last_key: tuple[str, str] | None = None

    def emit_until(target: str, *, include_target: bool) -> Iterator[PhysicalTerminalSessionBlock]:
        nonlocal session_index, pending_rows, pending_raw_bytes
        nonlocal yielded_count, accepted_count, refusal_count
        while session_index < len(declared_sessions):
            session = declared_sessions[session_index]
            if session > target or (session == target and not include_target):
                return
            rows = pending_rows if session == target else []
            if session == target:
                pending_rows = []
                raw_bytes = pending_raw_bytes
                pending_raw_bytes = 0
            else:
                raw_bytes = 0
            accepted_raw = [row for row in rows if row["disposition"] == "accepted"]
            refused_raw = [row for row in rows if row["disposition"] == "named_refusal"]
            accepted = tuple(_eligible_from_record(row["eligible_security_session"]) for row in accepted_raw)
            refused = tuple(_refusal_from_record(row["census_refusal"]) for row in refused_raw)
            control_root = preopen_io._merkle(rows)
            universe_rows = [
                {
                    "terminal": "accepted" if row["disposition"] == "accepted" else "refused",
                    "value": row["eligible_security_session"] if row["disposition"] == "accepted" else row["census_refusal"],
                }
                for row in rows
            ]
            universe_root = preopen_io._merkle(universe_rows)
            control = commitments[session]
            universe_commitment = universe[session]
            if (
                len(rows) > limits["max_physical_session_terminal_count"]
                or raw_bytes > limits["max_physical_session_uncompressed_bytes"]
            ):
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.PHYSICAL_SESSION_CAPACITY_EXCEEDED,
                    "one physical pre-open session exceeded reviewed capacity",
                )
            if (
                (len(accepted), len(refused), len(rows), control_root)
                != (
                    control.accepted_count, control.refusal_count,
                    control.terminal_count, control.terminal_merkle_root,
                )
                or (len(accepted), len(refused), len(rows), universe_root)
                != (
                    universe_commitment.accepted_count,
                    universe_commitment.refusal_count,
                    universe_commitment.terminal_count,
                    universe_commitment.terminal_merkle_root,
                )
            ):
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.PHYSICAL_SHARD_CENSUS_CHANGED,
                    "one physical session differs from reviewed terminal commitments",
                )
            yielded_count += len(rows)
            accepted_count += len(accepted)
            refusal_count += len(refused)
            session_index += 1
            yield PhysicalTerminalSessionBlock(
                decision_session=session,
                accepted=accepted,
                refused=refused,
                terminal_count=len(rows),
                control_terminal_merkle_root=control_root,
                universe_terminal_merkle_root=universe_root,
                raw_byte_count=raw_bytes,
            )

    offset = 0
    while offset < len(descriptors):
        chunk = descriptors[offset]["decision_chunk_ordinal"]
        indexed_group: list[tuple[int, dict[str, object]]] = []
        while offset < len(descriptors) and descriptors[offset]["decision_chunk_ordinal"] == chunk:
            indexed_group.append((offset, descriptors[offset]))
            offset += 1
        payloads = [
            _read_archive_payload(archive, index, descriptor)
            for index, descriptor in indexed_group
        ]
        if sum(map(len, payloads)) > limits["max_physical_chunk_compressed_bytes"]:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.PHYSICAL_SESSION_CAPACITY_EXCEEDED,
                "one physical decision chunk exceeded reviewed compressed capacity",
            )
        for (_index, descriptor), payload in zip(indexed_group, payloads, strict=True):
            physical_records.append(
                {
                    "ordinal": descriptor["ordinal"],
                    "object_store_key": descriptor["object_store_key"],
                    "payload_sha256": sha256_bytes(payload),
                    "payload_byte_count": len(payload),
                }
            )
        cursors = [
            preopen_io._PhysicalShardCursor(descriptor, payload)
            for (_index, descriptor), payload in zip(indexed_group, payloads, strict=True)
        ]
        heap: list[tuple[str, str, int, dict[str, object]]] = []
        for cursor_index, cursor in enumerate(cursors):
            row = cursor.next()
            if row is not None:
                heapq.heappush(
                    heap,
                    (row["decision_session"], row["security_id"], cursor_index, row),
                )
        while heap:
            session, security_id, cursor_index, row = heapq.heappop(heap)
            key = (session, security_id)
            if last_key is not None and key <= last_key:
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.PHYSICAL_SHARD_CENSUS_CHANGED,
                    "physical logical terminal stream repeated or reordered",
                )
            if session not in commitments:
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.PHYSICAL_SHARD_CENSUS_CHANGED,
                    "physical terminal escaped declared sessions",
                )
            if pending_rows and pending_rows[0]["decision_session"] != session:
                prior = pending_rows[0]["decision_session"]
                yield from emit_until(prior, include_target=True)
            elif not pending_rows:
                yield from emit_until(session, include_target=False)
            pending_rows.append(row)
            pending_raw_bytes += len(canonical_json_bytes(row))
            if row["disposition"] == "accepted":
                measurement = row["q_data_measurement"]
                if not quality_first:
                    quality.update(b",")
                quality.update(canonical_json_bytes(measurement)[:-1])
                quality_first = False
                quality_count += 1
            last_key = key
            following = cursors[cursor_index].next()
            if following is not None:
                heapq.heappush(
                    heap,
                    (
                        following["decision_session"], following["security_id"],
                        cursor_index, following,
                    ),
                )
        del cursors, payloads
    if pending_rows:
        yield from emit_until(pending_rows[0]["decision_session"], include_target=True)
    if session_index < len(declared_sessions):
        yield from emit_until(declared_sessions[-1], include_target=True)
    quality.update(b'],"schema":"arv2-qdata-physical-measurement-projection-v1"}\n')
    qdata = acquisition_q_data_measurement_projection_record(preopen)
    if (
        yielded_count != archive.terminal_count
        or accepted_count != archive.accepted_count
        or refusal_count != archive.refusal_count
        or quality_count != qdata["measurement_count"]
        or quality.hexdigest() != qdata["projection_sha256"]
        or sha256_bytes(canonical_json_bytes(physical_records))
        != archive.physical_payload_projection_sha256
    ):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.PHYSICAL_SHARD_CENSUS_CHANGED,
            "physical replay totals, q-data, or payload projection changed",
        )


def iter_physical_preopen_terminal_sessions(
    archive: PhysicalPreopenTerminalArchive
    | PhysicalProductionEvidenceTerminalArchive,
) -> Iterator[PhysicalTerminalSessionBlock]:
    """Sequentially reauthenticate and replay one physical pre-open session.

    The public iterator deliberately delegates to the same exhaustive physical
    verifier used by streamed scoring.  It does not expose paths or let a
    caller substitute reconstructed terminal records.
    """

    yield from _iter_physical_terminal_sessions(archive)


class _DiskBackedDecimalMgs:
    """Bounded disk-spooled clone of the frozen Decimal MGS operation order."""

    def __init__(self, width: int, limits: Mapping[str, int]):
        if (
            type(width) is not int
            or width <= 0
            or width > limits["max_disk_mgs_width"]
            or width * width + 6 * width
            > limits["max_disk_mgs_live_decimal_count"]
            or width + 4 > limits["max_disk_mgs_spool_file_count"]
        ):
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.QR_CAPACITY_EXCEEDED,
                "disk MGS width, live state, or file census exceeds reviewed capacity",
            )
        self.width = width
        self._limits = limits
        self.row_count = 0
        self._spool_bytes = 0
        self.peak_spool_bytes = 0
        self._spool_files = 1
        self.peak_spool_files = 1
        self._solved = False
        self._temporary = tempfile.TemporaryDirectory(
            prefix="arv2-formal-mgs-", dir="/private/tmp"
        )
        self._directory = Path(self._temporary.name)
        os.chmod(self._directory, 0o700)
        self._design_path = self._directory / "design.jsonl"
        descriptor = os.open(
            self._design_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        self._design = os.fdopen(descriptor, "wb", buffering=0)

    @property
    def decimal_count(self) -> int:
        return self.width * self.width + 6 * self.width

    def _account_write(self, count: int) -> None:
        if self._spool_bytes + count > self._limits["max_disk_mgs_spool_byte_count"]:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.QR_CAPACITY_EXCEEDED,
                "disk MGS spool bytes exceeded reviewed capacity",
            )
        self._spool_bytes += count
        self.peak_spool_bytes = max(self.peak_spool_bytes, self._spool_bytes)

    def _new_value_file(self, name: str, values: Iterable[Decimal]) -> tuple[Path, int]:
        if self._spool_files + 1 > self._limits["max_disk_mgs_spool_file_count"]:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.QR_CAPACITY_EXCEEDED,
                "disk MGS spool files exceeded reviewed capacity",
            )
        path = self._directory / name
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        size = 0
        self._spool_files += 1
        self.peak_spool_files = max(self.peak_spool_files, self._spool_files)
        try:
            with os.fdopen(descriptor, "wb", buffering=0) as stream:
                for value in values:
                    if type(value) is not Decimal or not value.is_finite():
                        raise FormalStreamingInputError(
                            "disk MGS generated a non-finite Decimal"
                        )
                    payload = (_decimal_text(value) + "\n").encode("ascii")
                    self._account_write(len(payload))
                    written = stream.write(payload)
                    if written != len(payload):
                        raise FormalStreamingInputError("disk MGS spool write was short")
                    size += written
            return path, size
        except Exception:
            self._spool_bytes -= size
            self._spool_files -= 1
            try:
                path.unlink()
            except OSError:
                pass
            raise

    @staticmethod
    def _value_rows(path: Path) -> Iterator[Decimal]:
        with path.open("rb") as stream:
            for line in stream:
                try:
                    value = Decimal(line.rstrip(b"\n").decode("ascii"))
                except (UnicodeError, InvalidOperation) as exc:
                    raise FormalStreamingInputError(
                        "disk MGS spool value changed"
                    ) from exc
                if not value.is_finite():
                    raise FormalStreamingInputError("disk MGS spool value is non-finite")
                yield value

    def _design_rows(self) -> Iterator[tuple[tuple[Decimal, ...], Decimal, Decimal]]:
        self._design.flush()
        with self._design_path.open("rb") as stream:
            for line in stream:
                try:
                    raw = json.loads(line)
                    values = tuple(Decimal(item) for item in raw)
                except (UnicodeError, ValueError, TypeError, InvalidOperation) as exc:
                    raise FormalStreamingInputError("disk MGS design spool changed") from exc
                if (
                    type(raw) is not list
                    or len(values) != self.width + 2
                    or any(not item.is_finite() for item in values)
                ):
                    raise FormalStreamingInputError("disk MGS design spool shape changed")
                yield values[: self.width], values[-2], values[-1]

    def _drop(self, path: Path, size: int) -> None:
        path.unlink()
        self._spool_bytes -= size
        self._spool_files -= 1

    def _cleanup(self) -> None:
        try:
            if not self._design.closed:
                self._design.close()
        finally:
            self._temporary.cleanup()

    def update(
        self,
        design: tuple[Decimal, ...],
        firm_response: Decimal,
        global_response: Decimal,
    ) -> None:
        if self._solved:
            raise FormalStreamingInputError("disk MGS fit is already sealed")
        if (
            type(design) is not tuple
            or len(design) != self.width
            or any(type(item) is not Decimal or not item.is_finite() for item in design)
            or type(firm_response) is not Decimal
            or not firm_response.is_finite()
            or type(global_response) is not Decimal
            or not global_response.is_finite()
        ):
            raise FormalStreamingInputError("disk MGS row is not exact finite Decimal")
        if self.row_count + 1 > self._limits["max_disk_mgs_spool_row_count"]:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.QR_CAPACITY_EXCEEDED,
                "disk MGS row count exceeded reviewed capacity",
            )
        payload = canonical_json_bytes(
            [_decimal_text(item) for item in (*design, firm_response, global_response)]
        )
        self._account_write(len(payload))
        if self._design.write(payload) != len(payload):
            raise FormalStreamingInputError("disk MGS design spool write was short")
        self.row_count += 1

    def solve(self) -> tuple[tuple[Decimal, ...], tuple[Decimal, ...]]:
        if self._solved:
            raise FormalStreamingInputError("disk MGS fit is already sealed")
        self._solved = True
        if self.row_count <= self.width + 20:
            self._cleanup()
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.TRAINING_FIT_UNDERFILLED,
                "active training rows do not exceed the frozen parameter floor",
            )
        upper = [[Decimal(0) for _ in range(self.width)] for _ in range(self.width)]
        q_paths: list[tuple[Path, int]] = []
        try:
            self._design.flush()
            with localcontext(_DECIMAL_CONTEXT) as context:
                for column in range(self.width):
                    vector_path, vector_size = self._new_value_file(
                        f"vector-{column:04d}-0000.txt",
                        (row[0][column] for row in self._design_rows()),
                    )
                    for prior, (q_path, _q_size) in enumerate(q_paths):
                        projection = sum(
                            (
                                q_value * vector_value
                                for q_value, vector_value in zip(
                                    self._value_rows(q_path),
                                    self._value_rows(vector_path),
                                    strict=True,
                                )
                            ),
                            Decimal(0),
                        )
                        upper[prior][column] = projection
                        next_path, next_size = self._new_value_file(
                            f"vector-{column:04d}-{prior + 1:04d}.txt",
                            (
                                vector_value - projection * q_value
                                for vector_value, q_value in zip(
                                    self._value_rows(vector_path),
                                    self._value_rows(q_path),
                                    strict=True,
                                )
                            ),
                        )
                        self._drop(vector_path, vector_size)
                        vector_path, vector_size = next_path, next_size
                    residual_norm_squared = sum(
                        (value * value for value in self._value_rows(vector_path)),
                        Decimal(0),
                    )
                    original_norm_squared = sum(
                        (
                            row[0][column] * row[0][column]
                            for row in self._design_rows()
                        ),
                        Decimal(0),
                    )
                    relative_floor = (
                        RANK_RELATIVE_THRESHOLD
                        * RANK_RELATIVE_THRESHOLD
                        * max(Decimal(1), original_norm_squared)
                    )
                    if residual_norm_squared <= relative_floor:
                        raise FormalStreamingRunRefusal(
                            FormalStreamingRefusalReason.TRAINING_FIT_RANK_DEFICIENT,
                            "disk MGS training design is rank deficient",
                        )
                    norm = context.sqrt(residual_norm_squared)
                    upper[column][column] = norm
                    q_path, q_size = self._new_value_file(
                        f"q-{column:04d}.txt",
                        (value / norm for value in self._value_rows(vector_path)),
                    )
                    q_paths.append((q_path, q_size))
                    self._drop(vector_path, vector_size)

                q_firm: list[Decimal] = []
                q_global: list[Decimal] = []
                for q_path, _q_size in q_paths:
                    q_firm.append(
                        sum(
                            (
                                q_value * row[1]
                                for q_value, row in zip(
                                    self._value_rows(q_path),
                                    self._design_rows(),
                                    strict=True,
                                )
                            ),
                            Decimal(0),
                        )
                    )
                    q_global.append(
                        sum(
                            (
                                q_value * row[2]
                                for q_value, row in zip(
                                    self._value_rows(q_path),
                                    self._design_rows(),
                                    strict=True,
                                )
                            ),
                            Decimal(0),
                        )
                    )

                def backsolve(response: Sequence[Decimal]) -> tuple[Decimal, ...]:
                    values = [Decimal(0) for _ in range(self.width)]
                    for row in range(self.width - 1, -1, -1):
                        remainder = sum(
                            (
                                upper[row][column] * values[column]
                                for column in range(row + 1, self.width)
                            ),
                            Decimal(0),
                        )
                        values[row] = (
                            response[row] - remainder
                        ) / upper[row][row]
                    return tuple(values)

                return backsolve(q_firm), backsolve(q_global)
        finally:
            self._cleanup()


@dataclasses.dataclass(frozen=True)
class StreamedControlModel:
    model_id: str
    model_sha256: str
    schema: str
    signal_arm: SignalArm
    fold_id: str
    columns: tuple[str, ...]
    industry_levels: tuple[str, ...]
    reference_industry: str
    firm_coefficients: tuple[Decimal, ...]
    global_coefficients: tuple[Decimal, ...]
    active_training_rows: int
    fit_method_id: str = STREAMING_METHOD_ID

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "signal_arm": self.signal_arm.value,
            "fold_id": self.fold_id,
            "columns": list(self.columns),
            "industry_levels": list(self.industry_levels),
            "reference_industry": self.reference_industry,
            "firm_coefficients": [_decimal_text(item) for item in self.firm_coefficients],
            "global_coefficients": [_decimal_text(item) for item in self.global_coefficients],
            "active_training_rows": self.active_training_rows,
            "fit_method_id": self.fit_method_id,
            "model_id": self.model_id,
            "model_sha256": self.model_sha256,
        }


def _build_streamed_model(
    *,
    arm: SignalArm,
    fold: ProductionScoringFold,
    levels: tuple[str, ...],
    qr: _DiskBackedDecimalMgs,
) -> StreamedControlModel:
    if not levels or levels != tuple(sorted(set(levels))):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.TRAINING_FIT_UNDERFILLED,
            f"{arm.value} has no exact active training industry census",
        )
    firm, global_values = qr.solve()
    record = {
        "schema": STREAMING_MODEL_SCHEMA,
        "signal_arm": arm.value,
        "fold_id": fold.fold_id,
        "columns": [
            "intercept", *CONTROL_COLUMNS,
            *(f"industry::{item}" for item in levels[1:]),
        ],
        "industry_levels": list(levels),
        "reference_industry": levels[0],
        "firm_coefficients": [_decimal_text(item) for item in firm],
        "global_coefficients": [_decimal_text(item) for item in global_values],
        "active_training_rows": qr.row_count,
        "fit_method_id": STREAMING_METHOD_ID,
    }
    digest = sha256_bytes(canonical_json_bytes(record))
    return StreamedControlModel(
        model_id=f"arv2-streamed-production-control-{arm.value}-{digest[:20]}",
        model_sha256=digest,
        schema=STREAMING_MODEL_SCHEMA,
        signal_arm=arm,
        fold_id=fold.fold_id,
        columns=tuple(record["columns"]),
        industry_levels=levels,
        reference_industry=levels[0],
        firm_coefficients=firm,
        global_coefficients=global_values,
        active_training_rows=qr.row_count,
    )


def _prediction(
    model: StreamedControlModel,
    row: PrecontrolDecisionRow,
    response: str,
) -> Decimal:
    coefficients = (
        model.firm_coefficients if response == "firm" else model.global_coefficients
    )
    by_column = dict(zip(model.columns, coefficients, strict=True))
    with localcontext(_DECIMAL_CONTEXT):
        result = by_column["intercept"]
        for name, value in zip(CONTROL_COLUMNS, row.transformed_controls, strict=True):
            result += by_column[name] * value
        if row.industry_id != model.reference_industry:
            result += by_column[f"industry::{row.industry_id}"]
        return result


def _apply_streamed_model(
    model: StreamedControlModel,
    row: PrecontrolDecisionRow,
) -> FinalDecisionInput | ScoringRefusal:
    if row.state is ScoreState.ACTIVE and row.industry_id not in model.industry_levels:
        seed = {
            "signal_arm": row.signal_arm.value,
            "fold_id": row.fold_id,
            "partition": row.partition.value,
            "decision_session": row.decision_session,
            "security_id": row.security_id,
            "disposition": ScoreDisposition.UNSEEN_TRAINING_INDUSTRY.value,
            "evidence_sha256": row.census_evidence_sha256,
        }
        return ScoringRefusal(
            signal_arm=row.signal_arm,
            fold_id=row.fold_id,
            partition=row.partition,
            decision_session=row.decision_session,
            security_id=row.security_id,
            disposition=ScoreDisposition.UNSEEN_TRAINING_INDUSTRY,
            evidence_sha256=row.census_evidence_sha256,
            refusal_sha256=sha256_bytes(canonical_json_bytes(seed)),
        )
    if row.state is ScoreState.STRUCTURAL_ZERO:
        firm = global_value = Decimal(0)
    else:
        with localcontext(_DECIMAL_CONTEXT):
            firm = max(CLIP_LOW, min(CLIP_HIGH, row.firm_reliable_score - _prediction(model, row, "firm")))
            global_value = max(CLIP_LOW, min(CLIP_HIGH, row.global_reliable_score - _prediction(model, row, "global")))
    seed = {
        "signal_arm": row.signal_arm.value,
        "fold_id": row.fold_id,
        "partition": row.partition.value,
        "decision_session": row.decision_session,
        "security_id": row.security_id,
        "issuer_id": row.issuer_id,
        "share_class_id": row.share_class_id,
        "listing_id": row.listing_id,
        "historical_ticker": row.historical_ticker,
        "sector_id": row.sector_id,
        "industry_id": row.industry_id,
        "state": row.state.value,
        "firm_specific_score": _decimal_text(firm),
        "global_score": _decimal_text(global_value),
        "transformed_controls": [_decimal_text(item) for item in row.transformed_controls],
        "realized_volatility_60d": _decimal_text(
            row.realized_volatility_60d
        ),
        "earnings_anchor_signed_session_distance": (
            row.earnings_anchor_signed_session_distance
        ),
        "common_event_component_id": row.common_event_component_id,
        "contributing_c2_row_sha256s": list(row.contributing_c2_row_sha256s),
        "contributions": [item.to_record() for item in row.contributions],
        "precontrol_row_sha256": row.row_sha256,
        "firm_model_sha256": model.model_sha256,
        "global_model_sha256": model.model_sha256,
    }
    return FinalDecisionInput(
        signal_arm=row.signal_arm,
        fold_id=row.fold_id,
        partition=row.partition,
        decision_session=row.decision_session,
        security_id=row.security_id,
        issuer_id=row.issuer_id,
        share_class_id=row.share_class_id,
        listing_id=row.listing_id,
        historical_ticker=row.historical_ticker,
        sector_id=row.sector_id,
        industry_id=row.industry_id,
        state=row.state,
        firm_specific_score=firm,
        global_score=global_value,
        transformed_controls=row.transformed_controls,
        realized_volatility_60d=row.realized_volatility_60d,
        earnings_anchor_signed_session_distance=(
            row.earnings_anchor_signed_session_distance
        ),
        common_event_component_id=row.common_event_component_id,
        contributing_c2_row_sha256s=row.contributing_c2_row_sha256s,
        contributions=row.contributions,
        precontrol_row_sha256=row.row_sha256,
        firm_model_sha256=model.model_sha256,
        global_model_sha256=model.model_sha256,
        row_sha256=sha256_bytes(canonical_json_bytes(seed)),
    )


def _chain_hasher(domain: str) -> object:
    value = hashlib.sha256()
    value.update(domain.encode("ascii") + b"\0")
    return value


def _chain_update(hasher: object, record: object) -> None:
    payload = canonical_json_bytes(record)
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)


def _rolling_chain_seed(domain: str) -> str:
    return sha256_bytes(domain.encode("ascii") + b"\0")


def _rolling_chain_update(root_sha256: str, record: object) -> str:
    payload = canonical_json_bytes(record)
    return sha256_bytes(
        bytes.fromhex(require_sha256(root_sha256, "rolling chain root"))
        + len(payload).to_bytes(8, "big")
        + payload
    )


def _stream_ordinals(contributions: Sequence[object]) -> dict[str, int]:
    eligible = tuple(item.eligible_session for item in contributions)
    start = min((FORMAL_SESSION_GEOMETRY[0], *eligible))
    end = date.fromisoformat(FORMAL_SESSION_GEOMETRY[-1]) + timedelta(days=1)
    try:
        sessions = trading_sessions(date.fromisoformat(start), end - timedelta(days=1))
    except ExchangeCalendarError as exc:
        raise FormalStreamingInputError(
            "streamed scoring session axis cannot be resolved"
        ) from exc
    result = {item.isoformat(): index for index, item in enumerate(sessions)}
    if any(item not in result for item in (*FORMAL_SESSION_GEOMETRY, *eligible)):
        raise FormalStreamingInputError(
            "streamed event or decision session escaped the NYSE axis"
        )
    return result


def _source_view(arm: SignalArm) -> str:
    if arm is SignalArm.CURRENT_VINTAGE:
        return CURRENT_VIEW_LABEL
    if arm is SignalArm.CONSERVATIVE_CENSORED:
        return CENSORED_VIEW_LABEL
    raise FormalStreamingInputError("streamed score has an unknown signal arm")


def _streamed_decision(
    binding: ScoringResultBinding,
    row: FinalDecisionInput,
) -> ProductionScoredDecisionLineage:
    record = {
        "source_view_id": _source_view(row.signal_arm),
        "fold_id": row.fold_id,
        "decision_session": row.decision_session,
        "security_id": row.security_id,
        "final_scoring_row_sha256": row.row_sha256,
        "scoring_result_id": binding.result_id,
        "scoring_result_sha256": binding.result_sha256,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
    }
    decision_id, digest, _payload = _post_identified(
        prefix="arv2-formal-production-decision-",
        schema=SCORING_LINEAGE_SCHEMA,
        record=record,
    )
    value = ProductionScoredDecisionLineage(
        schema=SCORING_LINEAGE_SCHEMA,
        decision_id=decision_id,
        lineage_sha256=digest,
        source_view_id=_source_view(row.signal_arm),
        fold_id=row.fold_id,
        decision_session=date.fromisoformat(row.decision_session),
        security_id=row.security_id,
        issuer_id=row.issuer_id,
        share_class_id=row.share_class_id,
        listing_id=row.listing_id,
        historical_ticker=row.historical_ticker,
        sector_id=row.sector_id,
        industry_id=row.industry_id,
        structural_zero=row.state is ScoreState.STRUCTURAL_ZERO,
        firm_specific_score=row.firm_specific_score,
        global_score=row.global_score,
        transformed_controls=row.transformed_controls,
        realized_volatility_60d=row.realized_volatility_60d,
        earnings_anchor_signed_session_distance=(
            row.earnings_anchor_signed_session_distance
        ),
        common_event_component_id=row.common_event_component_id,
        contributions=row.contributions,
        final_scoring_row_sha256=row.row_sha256,
        scoring_result_id=binding.result_id,
        scoring_result_sha256=binding.result_sha256,
        scoring_contract_id=SCORING_CONTRACT_ID,
        scoring_contract_sha256=SCORING_CONTRACT_SHA256,
    )
    return _require_production_scored_decision(value)


def _streamed_refusal(
    binding: ScoringResultBinding,
    refusal: ScoringRefusal,
) -> ProductionScoringCensusRefusal:
    record = {
        "source_view_id": _source_view(refusal.signal_arm),
        "fold_id": refusal.fold_id,
        "decision_session": refusal.decision_session,
        "security_id": refusal.security_id,
        "disposition": refusal.disposition.value,
        "source_refusal_sha256": refusal.refusal_sha256,
        "scoring_result_id": binding.result_id,
        "scoring_result_sha256": binding.result_sha256,
    }
    refusal_id, digest, _payload = _post_identified(
        prefix="arv2-formal-production-refusal-",
        schema=SCORING_REFUSAL_SCHEMA,
        record=record,
    )
    value = ProductionScoringCensusRefusal(
        schema=SCORING_REFUSAL_SCHEMA,
        refusal_id=refusal_id,
        refusal_sha256=digest,
        source_view_id=_source_view(refusal.signal_arm),
        fold_id=refusal.fold_id,
        decision_session=date.fromisoformat(refusal.decision_session),
        security_id=refusal.security_id,
        disposition=refusal.disposition.value,
        source_refusal_sha256=refusal.refusal_sha256,
        scoring_result_id=binding.result_id,
        scoring_result_sha256=binding.result_sha256,
    )
    return _require_production_scoring_refusal(value)


@dataclasses.dataclass(frozen=True, slots=True)
class StreamedFoldCommitment:
    schema: str
    fold_id: str
    result_binding: ScoringResultBinding
    fold_geometry: tuple[str, ...]
    model_records: tuple[dict[str, object], dict[str, object]]
    global_comparator_coverages: tuple[
        FormalGlobalComparatorCoverage,
        FormalGlobalComparatorCoverage,
    ]
    partition_terminal_counts: tuple[tuple[str, int, int], ...]
    partition_terminal_roots: tuple[tuple[str, str, str], ...]
    event_terminal_projection_sha256: str
    physical_replay_pass_count: int

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "fold_id": self.fold_id,
            "result_binding": self.result_binding.to_record(),
            "fold_geometry": list(self.fold_geometry),
            "model_records": list(self.model_records),
            "global_comparator_coverages": [
                item.to_record() for item in self.global_comparator_coverages
            ],
            "partition_terminal_counts": [
                list(item) for item in self.partition_terminal_counts
            ],
            "partition_terminal_roots": [
                list(item) for item in self.partition_terminal_roots
            ],
            "event_terminal_projection_sha256": (
                self.event_terminal_projection_sha256
            ),
            "physical_replay_pass_count": self.physical_replay_pass_count,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class StreamedTestSessionBlock:
    schema: str
    block_id: str
    block_sha256: str
    fold_id: str
    decision_session: date
    current_accepted: tuple[ProductionScoredDecisionLineage, ...]
    current_refused: tuple[ProductionScoringCensusRefusal, ...]
    censored_accepted: tuple[ProductionScoredDecisionLineage, ...]
    censored_refused: tuple[ProductionScoringCensusRefusal, ...]
    matched_terminal_count: int
    matched_terminal_sha256: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class StreamedProductionScoringBuilder:
    builder_id: str
    schema: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class StreamedProductionScoringArtifact:
    artifact_id: str
    artifact_sha256: str
    schema: str
    archive_id: str
    archive_sha256: str
    production_evidence_receipt_id: str
    production_evidence_receipt_sha256: str
    capacity_receipt_id: str
    capacity_receipt_sha256: str
    scoring_contract_id: str
    scoring_contract_sha256: str
    method_id: str
    global_contract: GlobalBenchmarkContract = dataclasses.field(repr=False)
    result_bindings: tuple[ScoringResultBinding, ...]
    fold_commitments: tuple[StreamedFoldCommitment, ...]
    pooled_global_comparator_coverages: tuple[
        FormalGlobalComparatorCoverage,
        FormalGlobalComparatorCoverage,
    ]
    matched_test_terminal_count: int
    matched_test_terminal_sha256: str
    observed_capacity: tuple[tuple[str, int], ...]
    upstream_materialized_truth_count: int
    upstream_materialized_result_count: int
    provider_access: bool
    outcome_access: bool
    quantconnect_access: bool
    qc_launch_available: bool

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "archive_id": self.archive_id,
            "archive_sha256": self.archive_sha256,
            "production_evidence_receipt_id": self.production_evidence_receipt_id,
            "production_evidence_receipt_sha256": self.production_evidence_receipt_sha256,
            "capacity_receipt_id": self.capacity_receipt_id,
            "capacity_receipt_sha256": self.capacity_receipt_sha256,
            "scoring_contract_id": self.scoring_contract_id,
            "scoring_contract_sha256": self.scoring_contract_sha256,
            "method_id": self.method_id,
            "paired_bootstrap_authority": _paired_bootstrap_authority_record(
                self.global_contract
            ),
            "result_bindings": [item.to_record() for item in self.result_bindings],
            "fold_commitments": [item.to_record() for item in self.fold_commitments],
            "pooled_global_comparator_coverages": [
                item.to_record() for item in self.pooled_global_comparator_coverages
            ],
            "matched_test_terminal_count": self.matched_test_terminal_count,
            "matched_test_terminal_sha256": self.matched_test_terminal_sha256,
            "observed_capacity": dict(self.observed_capacity),
            "upstream_materialized_truth_count": self.upstream_materialized_truth_count,
            "upstream_materialized_result_count": self.upstream_materialized_result_count,
            "capabilities": {
                "provider_access": self.provider_access,
                "outcome_access": self.outcome_access,
                "quantconnect_access": self.quantconnect_access,
                "qc_launch_available": self.qc_launch_available,
            },
        }


@dataclasses.dataclass(frozen=True, slots=True)
class _FrozenStringMapping(Mapping[str, object]):
    """Small immutable lookup whose backing storage cannot be resealed."""

    keys: tuple[str, ...]
    values: tuple[object, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> _FrozenStringMapping:
        keys = tuple(sorted(value))
        return cls(keys=keys, values=tuple(value[key] for key in keys))

    def __getitem__(self, key: str) -> object:
        position = bisect_left(self.keys, key)
        if position == len(self.keys) or self.keys[position] != key:
            raise KeyError(key)
        return self.values[position]

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys)

    def __len__(self) -> int:
        return len(self.keys)


@dataclasses.dataclass(frozen=True, slots=True)
class _StreamingBuilderState:
    archive: PhysicalPreopenTerminalArchive
    evidence: ProductionEvidenceAcquisitionReceipt
    global_contract: GlobalBenchmarkContract
    current_batch: ProductionInputBatch
    censored_batch: ProductionInputBatch
    current_coverage_source: FormalGlobalComparatorCoverageSource
    censored_coverage_source: FormalGlobalComparatorCoverageSource
    event_terminal_projection_sha256: str
    union: _FrozenStringMapping
    row_evidence: _FrozenStringMapping
    expected_by_session: _FrozenStringMapping
    ordinals: _FrozenStringMapping
    base_retained_input_graph_bytes: int
    next_fold_index: int
    fold_commitments: tuple[StreamedFoldCommitment, ...]
    matched_test_terminal_count: int
    matched_test_terminal_sha256: str
    observed: tuple[tuple[str, int], ...]
    active_fold: bool
    finalized: bool
    epoch: int
    pid: int
    owner_thread_id: int


_STREAM_BUILDERS: dict[
    int,
    tuple[
        weakref.ReferenceType[StreamedProductionScoringBuilder],
        bytes,
        _StreamingBuilderState,
        tuple[object, ...],
        str | None,
    ],
] = {}
_STREAM_ARTIFACTS: dict[
    int,
    tuple[
        weakref.ReferenceType[StreamedProductionScoringArtifact],
        bytes,
        tuple[object, ...],
    ],
] = {}
_STREAM_LOCK = threading.RLock()


def _endpoint_labels(
    evidence: ProductionEvidenceAcquisitionReceipt,
    union: dict[str, NormalizedPreOutcomeRow],
) -> tuple[EndpointLabelEvidence, ...]:
    firm = _firm_evidence_by_c2_hash(evidence.authority, union)
    return tuple(
        build_endpoint_label_evidence(
            c2_row_sha256=digest,
            provider_event_id=union[digest].provider_event_id,
            raw_previous_label=firm[digest].raw_previous_label,
            raw_current_label=firm[digest].raw_current_label,
            source_sha256=union[digest].source_locator.raw_row_sha256,
            available_at=firm[digest].available_at,
        )
        for digest in sorted(union)
    )


def _event_projection(*terminal_groups: Sequence[object]) -> str:
    records = [
        item.to_record()
        for group in terminal_groups
        for item in group
    ]
    records.sort(key=lambda item: (item["signal_arm"], item["c2_row_sha256"]))
    return sha256_bytes(canonical_json_bytes(records))


def _stream_builder_static(value: StreamedProductionScoringBuilder) -> bytes:
    return canonical_json_bytes(
        {"builder_id": value.builder_id, "schema": value.schema}
    )


def _frozen_mapping_authority(value: object) -> tuple[object, ...]:
    if (
        type(value) is not _FrozenStringMapping
        or type(value.keys) is not tuple
        or type(value.values) is not tuple
        or len(value.keys) != len(value.values)
        or any(type(item) is not str for item in value.keys)
        or value.keys != tuple(sorted(set(value.keys)))
    ):
        raise FormalStreamingInputError("streaming immutable lookup changed")
    return (id(value), id(value.keys), id(value.values), len(value.keys))


def _stream_state_authority(
    state: _StreamingBuilderState,
) -> tuple[object, ...]:
    """Capture the exact compact state; no caller can reseal a replacement."""

    if (
        type(state) is not _StreamingBuilderState
        or type(state.fold_commitments) is not tuple
        or any(type(item) is not StreamedFoldCommitment for item in state.fold_commitments)
        or type(state.observed) is not tuple
        or any(type(item) is not tuple or len(item) != 2 for item in state.observed)
        or state.observed != tuple(sorted(state.observed))
        or len(state.observed) != len({item[0] for item in state.observed})
        or any(
            type(name) is not str or type(value) is not int or value < 0
            for name, value in state.observed
        )
        or any(
            type(value) is not int or value < 0
            for value in (
                state.base_retained_input_graph_bytes,
                state.next_fold_index,
                state.matched_test_terminal_count,
                state.epoch,
            )
        )
        or state.next_fold_index > 6
        or len(state.fold_commitments) != state.next_fold_index
        or type(state.active_fold) is not bool
        or type(state.finalized) is not bool
        or (state.active_fold and state.finalized)
        or type(state.pid) is not int
        or type(state.owner_thread_id) is not int
        or type(state.event_terminal_projection_sha256) is not str
        or type(state.matched_test_terminal_sha256) is not str
    ):
        raise FormalStreamingInputError("streaming builder state changed type")
    try:
        require_sha256(
            state.event_terminal_projection_sha256,
            "event terminal projection SHA-256",
        )
        require_sha256(
            state.matched_test_terminal_sha256,
            "matched test terminal SHA-256",
        )
        commitment_bytes = canonical_json_bytes(
            [item.to_record() for item in state.fold_commitments]
        )
    except (TypeError, ValueError, AttributeError) as exc:
        raise FormalStreamingInputError(
            "streaming fold commitment state changed"
        ) from exc
    return (
        id(state.archive),
        id(state.evidence),
        id(state.global_contract),
        id(state.current_batch),
        id(state.censored_batch),
        id(state.current_coverage_source),
        id(state.censored_coverage_source),
        state.event_terminal_projection_sha256,
        _frozen_mapping_authority(state.union),
        _frozen_mapping_authority(state.row_evidence),
        _frozen_mapping_authority(state.expected_by_session),
        _frozen_mapping_authority(state.ordinals),
        state.base_retained_input_graph_bytes,
        state.next_fold_index,
        id(state.fold_commitments),
        commitment_bytes,
        state.matched_test_terminal_count,
        state.matched_test_terminal_sha256,
        id(state.observed),
        state.observed,
        state.active_fold,
        state.finalized,
        state.epoch,
        state.pid,
        state.owner_thread_id,
    )


def _stream_artifact_topology(
    value: StreamedProductionScoringArtifact,
) -> tuple[object, ...]:
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


def _make_stream_state_vault():
    """Create the independent state authority and only legal transitions.

    The closure-held record is intentionally separate from the inspectable
    compatibility registry.  No returned operation accepts a caller-supplied
    next state, authority digest, epoch, counter, or rolling root.
    """

    records: dict[
        int,
        tuple[
            weakref.ReferenceType[StreamedProductionScoringBuilder],
            bytes,
            _StreamingBuilderState,
            tuple[object, ...],
            object | None,
            str | None,
        ],
    ] = {}
    artifact_records: dict[
        int,
        tuple[
            tuple[
                weakref.ReferenceType[StreamedProductionScoringArtifact],
                bytes,
                tuple[object, ...],
            ],
            tuple[object, ...],
            int,
        ],
    ] = {}

    def revoke_locked(identity: int) -> None:
        records.pop(identity, None)
        _STREAM_BUILDERS.pop(identity, None)

    def current_locked(
        builder: StreamedProductionScoringBuilder,
    ) -> tuple[_StreamingBuilderState, object | None, str | None] | None:
        identity = id(builder)
        private = records.get(identity)
        public = _STREAM_BUILDERS.get(identity)
        try:
            valid = (
                private is not None
                and public is not None
                and len(public) == 5
                and private[0]() is builder
                and public[0]() is builder
                and private[1] == public[1] == _stream_builder_static(builder)
                and private[2] is public[2]
                and private[3] == public[3] == _stream_state_authority(private[2])
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
        builder: StreamedProductionScoringBuilder,
        state: _StreamingBuilderState,
        lease: object | None,
        purpose: str | None,
    ) -> None:
        identity = id(builder)
        prior = records[identity]
        authority = _stream_state_authority(state)
        records[identity] = (
            prior[0], prior[1], state, authority, lease, purpose,
        )
        _STREAM_BUILDERS[identity] = (
            prior[0], prior[1], state, authority, purpose,
        )

    def initialize(
        builder: StreamedProductionScoringBuilder,
        reference: weakref.ReferenceType[StreamedProductionScoringBuilder],
        static: bytes,
        state: _StreamingBuilderState,
    ) -> None:
        identity = id(builder)
        if (
            reference() is not builder
            or type(static) is not bytes
            or state.next_fold_index != 0
            or state.fold_commitments != ()
            or state.matched_test_terminal_count != 0
            or state.active_fold
            or state.finalized
            or state.epoch != 0
            or state.pid != os.getpid()
            or state.owner_thread_id != threading.get_ident()
        ):
            raise FormalStreamingInputError("initial streaming state changed")
        authority = _stream_state_authority(state)
        with _STREAM_LOCK:
            if identity in records or identity in _STREAM_BUILDERS:
                raise FormalStreamingInputError("streaming builder identity was reused")
            records[identity] = (
                reference, static, state, authority, None, None,
            )
            _STREAM_BUILDERS[identity] = (
                reference, static, state, authority, None,
            )

    def is_current(
        builder: StreamedProductionScoringBuilder,
        state: _StreamingBuilderState,
    ) -> bool:
        with _STREAM_LOCK:
            current = current_locked(builder)
            return current is not None and current[0] is state

    def acquire(
        builder: StreamedProductionScoringBuilder,
        purpose: str,
    ) -> tuple[_StreamingBuilderState, object]:
        if purpose not in {"formal_fold", "accepted_risk_power_calibration"}:
            raise FormalStreamingInputError("streaming consumer purpose changed")
        with _STREAM_LOCK:
            current = current_locked(builder)
            if current is None:
                raise FormalStreamingInputError("streaming scorer authority changed")
            state, lease, active_purpose = current
            if state.finalized or state.active_fold or lease is not None or active_purpose is not None:
                raise FormalStreamingInputError("streaming scorer is busy or sealed")
            next_state = dataclasses.replace(
                state, active_fold=True, epoch=state.epoch + 1
            )
            next_lease = object()
            store_locked(builder, next_state, next_lease, purpose)
            return next_state, next_lease

    def require_lease(
        builder: StreamedProductionScoringBuilder,
        lease: object,
        purpose: str,
    ) -> _StreamingBuilderState:
        with _STREAM_LOCK:
            current = current_locked(builder)
            if (
                current is None
                or current[1] is not lease
                or current[2] != purpose
            ):
                revoke_locked(id(builder))
                raise FormalStreamingInputError(
                    "streaming scorer lease or state changed"
                )
            return current[0]

    def block(
        builder: StreamedProductionScoringBuilder,
        lease: object,
        value: StreamedTestSessionBlock,
    ) -> _StreamingBuilderState:
        if type(value) is not StreamedTestSessionBlock:
            raise FormalStreamingInputError("streaming test block changed type")
        with _STREAM_LOCK:
            current = current_locked(builder)
            if (
                current is None
                or current[1] is not lease
                or current[2] != "formal_fold"
            ):
                revoke_locked(id(builder))
                raise FormalStreamingInputError("streaming block lease changed")
            state = current[0]
            expected_fold = build_formal_production_scoring_fold(
                2020 + state.next_fold_index
            )
            if (
                value.schema != STREAMING_SESSION_BLOCK_SCHEMA
                or value.fold_id != expected_fold.fold_id
                or value.decision_session.isoformat() < expected_fold.test_start
                or value.decision_session.isoformat() >= expected_fold.test_end_exclusive
                or type(value.matched_terminal_count) is not int
                or value.matched_terminal_count < 0
            ):
                revoke_locked(id(builder))
                raise FormalStreamingInputError("streaming test block escaped its fold")
            record = {
                "fold_id": value.fold_id,
                "decision_session": value.decision_session.isoformat(),
                "matched_terminal_sha256": value.matched_terminal_sha256,
            }
            next_state = dataclasses.replace(
                state,
                matched_test_terminal_count=(
                    state.matched_test_terminal_count + value.matched_terminal_count
                ),
                matched_test_terminal_sha256=_rolling_chain_update(
                    state.matched_test_terminal_sha256, record
                ),
                epoch=state.epoch + 1,
            )
            store_locked(builder, next_state, lease, "formal_fold")
            return next_state

    def fold(
        builder: StreamedProductionScoringBuilder,
        lease: object,
        commitment: StreamedFoldCommitment,
        observed: dict[str, int],
    ) -> _StreamingBuilderState:
        if type(commitment) is not StreamedFoldCommitment or type(observed) is not dict:
            raise FormalStreamingInputError("streaming fold transition changed type")
        with _STREAM_LOCK:
            current = current_locked(builder)
            if (
                current is None
                or current[1] is not lease
                or current[2] != "formal_fold"
            ):
                revoke_locked(id(builder))
                raise FormalStreamingInputError("streaming fold lease changed")
            state = current[0]
            expected_fold = build_formal_production_scoring_fold(
                2020 + state.next_fold_index
            )
            prior_observed = dict(state.observed)
            if (
                commitment.fold_id != expected_fold.fold_id
                or commitment.schema != STREAMING_FOLD_SCHEMA
                or commitment.event_terminal_projection_sha256
                != state.event_terminal_projection_sha256
                or commitment.physical_replay_pass_count != 3
                or type(commitment.global_comparator_coverages) is not tuple
                or len(commitment.global_comparator_coverages) != len(SignalArm)
                or set(observed) != set(prior_observed)
                or any(
                    type(value) is not int or value < prior_observed[name]
                    for name, value in observed.items()
                )
            ):
                revoke_locked(id(builder))
                raise FormalStreamingInputError("streaming fold transition changed")
            try:
                for coverage in commitment.global_comparator_coverages:
                    require_formal_global_comparator_coverage(coverage)
            except FormalInputBundleError as exc:
                revoke_locked(id(builder))
                raise FormalStreamingInputError(
                    "streaming fold coverage changed"
                ) from exc
            next_state = dataclasses.replace(
                state,
                next_fold_index=state.next_fold_index + 1,
                fold_commitments=(*state.fold_commitments, commitment),
                observed=tuple(sorted(observed.items())),
                active_fold=False,
                epoch=state.epoch + 1,
            )
            store_locked(builder, next_state, None, None)
            return next_state

    def external_finish(
        builder: StreamedProductionScoringBuilder,
        lease: object,
        observed: dict[str, int],
    ) -> _StreamingBuilderState:
        if type(observed) is not dict:
            raise FormalStreamingInputError("external streaming observations changed type")
        with _STREAM_LOCK:
            current = current_locked(builder)
            if (
                current is None
                or current[1] is not lease
                or current[2] != "accepted_risk_power_calibration"
            ):
                revoke_locked(id(builder))
                raise FormalStreamingInputError("external streaming lease changed")
            state = current[0]
            prior_observed = dict(state.observed)
            if set(observed) != set(prior_observed) or any(
                type(value) is not int or value < prior_observed[name]
                for name, value in observed.items()
            ):
                revoke_locked(id(builder))
                raise FormalStreamingInputError(
                    "external streaming observations changed"
                )
            next_state = dataclasses.replace(
                state,
                observed=tuple(sorted(observed.items())),
                active_fold=False,
                finalized=True,
                epoch=state.epoch + 1,
            )
            store_locked(builder, next_state, None, None)
            return next_state

    def finalize_artifact(
        builder: StreamedProductionScoringBuilder,
        value: StreamedProductionScoringArtifact,
    ) -> None:
        with _STREAM_LOCK:
            current = current_locked(builder)
            if current is None:
                raise FormalStreamingInputError("streaming scorer authority changed")
            state, lease, purpose = current
            if (
                lease is not None
                or purpose is not None
                or state.active_fold
                or state.finalized
                or state.next_fold_index != 6
                or len(state.fold_commitments) != 6
            ):
                raise FormalStreamingInputError(
                    "streaming scoring is incomplete, busy, or already sealed"
                )
            try:
                record = canonical_json_bytes(value.to_record())
                topology = _stream_artifact_topology(value)
                digest = sha256_bytes(record)
                lineage_is_exact = (
                    type(value) is StreamedProductionScoringArtifact
                    and value.global_contract is state.global_contract
                    and value.archive_id == state.archive.archive_id
                    and value.archive_sha256 == state.archive.archive_sha256
                    and value.production_evidence_receipt_id
                    == state.evidence.receipt_id
                    and value.production_evidence_receipt_sha256
                    == state.evidence.receipt_sha256
                    and value.capacity_receipt_id
                    == state.archive.capacity.receipt_id
                    and value.capacity_receipt_sha256
                    == state.archive.capacity.receipt_sha256
                    and value.fold_commitments is state.fold_commitments
                    and value.result_bindings
                    == tuple(
                        item.result_binding for item in state.fold_commitments
                    )
                    and all(
                        actual is commitment.result_binding
                        for actual, commitment in zip(
                            value.result_bindings,
                            state.fold_commitments,
                            strict=True,
                        )
                    )
                    and value.matched_test_terminal_count
                    == state.matched_test_terminal_count
                    and value.matched_test_terminal_sha256
                    == state.matched_test_terminal_sha256
                    and value.observed_capacity is state.observed
                    and value.artifact_sha256 == digest
                    and value.artifact_id
                    == f"arv2-formal-streamed-scoring-{digest[:24]}"
                )
            except (AttributeError, TypeError, ValueError) as exc:
                revoke_locked(id(builder))
                raise FormalStreamingInputError(
                    "streamed scoring artifact lineage changed"
                ) from exc
            if not lineage_is_exact:
                revoke_locked(id(builder))
                raise FormalStreamingInputError(
                    "streamed scoring artifact lineage changed"
                )
            identity = id(value)
            if identity in artifact_records or identity in _STREAM_ARTIFACTS:
                revoke_locked(id(builder))
                raise FormalStreamingInputError(
                    "streamed scoring artifact identity was reused"
                )

            def forget_artifact(reference: object, *, key: int = identity) -> None:
                with _STREAM_LOCK:
                    private = artifact_records.get(key)
                    if private is not None and private[0][0] is reference:
                        artifact_records.pop(key, None)
                        if _STREAM_ARTIFACTS.get(key) is private[0]:
                            _STREAM_ARTIFACTS.pop(key, None)

            reference = weakref.ref(value, forget_artifact)
            public = (reference, record, topology)
            next_state = dataclasses.replace(
                state, finalized=True, epoch=state.epoch + 1
            )
            store_locked(builder, next_state, None, None)
            artifact_records[identity] = (
                public,
                (
                    id(state.archive),
                    id(state.evidence),
                    id(state.global_contract),
                    _stream_state_authority(next_state),
                ),
                os.getpid(),
            )
            _STREAM_ARTIFACTS[identity] = public

    def current_artifact(
        value: StreamedProductionScoringArtifact,
    ) -> tuple[object, ...] | None:
        identity = id(value)
        with _STREAM_LOCK:
            private = artifact_records.get(identity)
            public = _STREAM_ARTIFACTS.get(identity)
            if (
                private is None
                or public is not private[0]
                or private[0][0]() is not value
                or private[2] != os.getpid()
            ):
                artifact_records.pop(identity, None)
                _STREAM_ARTIFACTS.pop(identity, None)
                return None
            return private[0]

    def revoke(builder: StreamedProductionScoringBuilder) -> None:
        with _STREAM_LOCK:
            revoke_locked(id(builder))

    def forget(identity: int, reference: object) -> None:
        with _STREAM_LOCK:
            private = records.get(identity)
            if private is not None and private[0] is reference:
                revoke_locked(identity)

    def reset_after_fork() -> None:
        global _STREAM_BUILDERS, _STREAM_ARTIFACTS, _STREAM_LOCK

        records.clear()
        artifact_records.clear()
        _STREAM_BUILDERS = {}
        _STREAM_ARTIFACTS = {}
        _STREAM_LOCK = threading.RLock()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)

    return (
        initialize,
        is_current,
        acquire,
        require_lease,
        block,
        fold,
        external_finish,
        finalize_artifact,
        current_artifact,
        revoke,
        forget,
    )


(
    _stream_vault_initialize,
    _stream_vault_is_current,
    _stream_vault_acquire,
    _stream_vault_require_lease,
    _stream_vault_block,
    _stream_vault_fold,
    _stream_vault_external_finish,
    _stream_vault_finalize_artifact,
    _stream_vault_current_artifact,
    _stream_vault_revoke,
    _stream_vault_forget,
) = _make_stream_state_vault()


def _retained_object_graph_bytes(*roots: object) -> int:
    """Measure the exact retained Python object graph once per identity.

    Only the closed value/container vocabulary used by the authenticated input
    contracts is traversable.  Unknown objects refuse instead of being counted
    only by their shallow header, which would understate a caller-controlled
    payload hidden behind an opaque object.
    """

    seen: set[int] = set()
    stack = list(roots)
    total = 0
    while stack:
        value = stack.pop()
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            total += sys.getsizeof(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise FormalStreamingInputError(
                "retained input graph contains an unmeasurable value"
            ) from exc
        if value is None or type(value) in (
            object, bool, int, str, bytes, Decimal, date
        ):
            continue
        if isinstance(value, Enum):
            # Enum classes are immutable code/global state, not retained input.
            continue
        if isinstance(value, Path):
            continue
        if type(value) is Fraction:
            stack.append(value.numerator)
            stack.append(value.denominator)
            continue
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            stack.extend(getattr(value, field.name) for field in dataclasses.fields(value))
            continue
        if type(value) is dict:
            for key, item in value.items():
                stack.append(key)
                stack.append(item)
            continue
        if type(value) in (tuple, list, set, frozenset):
            stack.extend(value)
            continue
        if isinstance(value, Mapping):
            for key, item in value.items():
                stack.append(key)
                stack.append(item)
            continue
        raise FormalStreamingInputError(
            "retained input graph contains an opaque value type: "
            f"{type(value).__module__}.{type(value).__qualname__}"
        )
    return total


def _begin_streamed_production_scoring_impl(
    *,
    archive: PhysicalPreopenTerminalArchive,
    production_evidence_receipt: ProductionEvidenceAcquisitionReceipt,
    global_contract: GlobalBenchmarkContract,
    _vault_initialize: object,
    _vault_forget: object,
) -> StreamedProductionScoringBuilder:
    """Open a sequential six-fold scorer without constructing production truth."""

    archive = require_physical_preopen_terminal_archive(archive)
    limits = dict(archive.capacity.limits)
    try:
        evidence = require_production_evidence_acquisition_receipt(
            production_evidence_receipt
        )
        contract = require_loaded_global_benchmark_contract(global_contract)
    except (ProductionEvidenceAcquisitionError, GlobalBenchmarkContractError) as exc:
        raise FormalStreamingInputError(
            "streaming scorer parents did not authenticate"
        ) from exc
    if (
        evidence is not archive.capacity.production_evidence_receipt
        or evidence.preopen_acquisition_receipt is not archive.preopen_acquisition_receipt
    ):
        raise FormalStreamingInputError(
            "streaming scorer evidence and terminal archive parents differ"
        )
    try:
        current = build_production_input_batch(
            evidence.authority, signal_arm=SignalArm.CURRENT_VINTAGE
        )
        censored = build_production_input_batch(
            evidence.authority, signal_arm=SignalArm.CONSERVATIVE_CENSORED
        )
        union = _normalized_union(current, censored)
        institutions = {item.institution_id for item in current.normalized_rows}
        institutions.update(item.institution_id for item in censored.normalized_rows)
        securities = {item.security_id for item in current.normalized_rows}
        securities.update(item.security_id for item in censored.normalized_rows)
        if (
            len(union) > limits["max_c2_normalized_row_count"]
            or len(institutions) > limits["max_retained_institution_count"]
            or len(securities) > limits["max_retained_security_count"]
        ):
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.IDENTITY_CAPACITY_EXCEEDED,
                "physical C2 identity state exceeds reviewed capacity",
            )
        labels = _endpoint_labels(evidence, union)
        labels_by_hash = {item.c2_row_sha256: item for item in labels}
        current_labels = tuple(
            labels_by_hash[digest]
            for digest in sorted(item.row_sha256 for item in current.normalized_rows)
        )
        censored_labels = tuple(
            labels_by_hash[digest]
            for digest in sorted(item.row_sha256 for item in censored.normalized_rows)
        )
        current_coverage_source = build_formal_global_comparator_coverage_source(
            signal_arm=SignalArm.CURRENT_VINTAGE,
            batch=current,
            global_contract=contract,
            endpoint_labels=current_labels,
        )
        censored_coverage_source = build_formal_global_comparator_coverage_source(
            signal_arm=SignalArm.CONSERVATIVE_CENSORED,
            batch=censored,
            global_contract=contract,
            endpoint_labels=censored_labels,
        )
        current_contributions, current_terminals = (
            formal_global_comparator_coverage_source_scoring_inputs(
                current_coverage_source
            )
        )
        censored_contributions, censored_terminals = (
            formal_global_comparator_coverage_source_scoring_inputs(
                censored_coverage_source
            )
        )
        row_evidence = _row_evidence_by_c2_hash(evidence.authority, union)
    except (
        FormalInputBundleError,
        ProductionInputError,
        ProductionScoringError,
    ) as exc:
        raise FormalStreamingInputError(
            "streaming scorer could not reconstruct exact physical C2 inputs"
        ) from exc
    expected_by_session: dict[str, list[NormalizedPreOutcomeRow]] = defaultdict(list)
    for row in union.values():
        expected_by_session[row.eligible_session].append(row)
    declared = {
        item.decision_session
        for item in archive.preopen_acquisition_receipt.control_sessions
    }
    if not set(expected_by_session).issubset(declared):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.C2_EVENT_TERMINAL_MISSING,
            "a physical C2 event session is absent from the terminal archive",
        )
    expected_by_session_frozen = {
        session: tuple(sorted(rows, key=lambda item: item.row_sha256))
        for session, rows in expected_by_session.items()
    }
    ordinals = _stream_ordinals(
        itertools.chain(current_contributions, censored_contributions)
    )
    retained_input_graph_bytes = _retained_object_graph_bytes(
        archive,
        evidence,
        contract,
        current,
        censored,
        union,
        row_evidence,
        expected_by_session_frozen,
        ordinals,
    ) + sum(
        formal_global_comparator_coverage_source_retained_bytes(item)
        for item in (current_coverage_source, censored_coverage_source)
    )
    if retained_input_graph_bytes > limits["max_retained_input_graph_bytes"]:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED,
            "whole retained input graph exceeded independently reviewed capacity",
        )
    projection = _event_projection(current_terminals, censored_terminals)
    seed = {
        "schema": STREAMING_BUILDER_SCHEMA,
        "archive_id": archive.archive_id,
        "archive_sha256": archive.archive_sha256,
        "production_evidence_receipt_id": evidence.receipt_id,
        "production_evidence_receipt_sha256": evidence.receipt_sha256,
        "capacity_receipt_id": archive.capacity.receipt_id,
        "capacity_receipt_sha256": archive.capacity.receipt_sha256,
        "global_map_id": contract.map_id,
        "global_map_sha256": contract.map_hash,
        "current_batch_id": current.batch_id,
        "current_batch_sha256": current.batch_sha256,
        "censored_batch_id": censored.batch_id,
        "censored_batch_sha256": censored.batch_sha256,
        "event_terminal_projection_sha256": projection,
        "retained_input_graph_bytes": retained_input_graph_bytes,
        "method_id": STREAMING_METHOD_ID,
        "paired_bootstrap_authority": _paired_bootstrap_authority_record(
            contract
        ),
    }
    digest = sha256_bytes(canonical_json_bytes(seed))
    value = object.__new__(StreamedProductionScoringBuilder)
    object.__setattr__(
        value, "builder_id", f"arv2-streamed-scoring-builder-{digest[:24]}"
    )
    object.__setattr__(value, "schema", STREAMING_BUILDER_SCHEMA)
    state = _StreamingBuilderState(
        archive=archive,
        evidence=evidence,
        global_contract=contract,
        current_batch=current,
        censored_batch=censored,
        current_coverage_source=current_coverage_source,
        censored_coverage_source=censored_coverage_source,
        event_terminal_projection_sha256=projection,
        union=_FrozenStringMapping.from_mapping(union),
        row_evidence=_FrozenStringMapping.from_mapping(row_evidence),
        expected_by_session=_FrozenStringMapping.from_mapping(
            expected_by_session_frozen
        ),
        ordinals=_FrozenStringMapping.from_mapping(ordinals),
        base_retained_input_graph_bytes=retained_input_graph_bytes,
        next_fold_index=0,
        fold_commitments=(),
        matched_test_terminal_count=0,
        matched_test_terminal_sha256=_rolling_chain_seed(
            "arv2-streamed-matched-test-terminal-census-v1"
        ),
        observed=tuple(sorted({
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
            "retained_input_graph_bytes": retained_input_graph_bytes,
        }.items())),
        active_fold=False,
        finalized=False,
        epoch=0,
        pid=os.getpid(),
        owner_thread_id=threading.get_ident(),
    )
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity, forget=_vault_forget: forget(key, ref)
    )
    _vault_initialize(
        value,
        reference,
        _stream_builder_static(value),
        state,
    )
    return require_streamed_production_scoring_builder(value)


def _require_streamed_production_scoring_builder_impl(
    value: StreamedProductionScoringBuilder,
    *,
    _vault_is_current: object,
) -> StreamedProductionScoringBuilder:
    if type(value) is not StreamedProductionScoringBuilder:
        raise FormalStreamingInputError("streaming scorer builder changed type")
    with _STREAM_LOCK:
        registered = _STREAM_BUILDERS.get(id(value))
    if (
        registered is None
        or len(registered) != 5
        or registered[0]() is not value
        or registered[1] != _stream_builder_static(value)
        or registered[3] != _stream_state_authority(registered[2])
        or not _vault_is_current(value, registered[2])
    ):
        raise FormalStreamingInputError(
            "streaming scorer builder is not builder-authenticated"
        )
    state = registered[2]
    if (
        state.pid != os.getpid()
        or state.owner_thread_id != threading.get_ident()
        or state.active_fold != (registered[4] is not None)
    ):
        raise FormalStreamingInputError(
            "streaming scorer process, thread, or lease changed"
        )
    try:
        require_physical_preopen_terminal_archive(state.archive)
        require_production_evidence_acquisition_receipt(state.evidence)
        require_loaded_global_benchmark_contract(state.global_contract)
        require_production_input_batch(state.current_batch)
        require_production_input_batch(state.censored_batch)
        formal_global_comparator_coverage_source_scoring_inputs(
            state.current_coverage_source
        )
        formal_global_comparator_coverage_source_scoring_inputs(
            state.censored_coverage_source
        )
    except (
        FormalInputBundleError,
        ProductionEvidenceAcquisitionError,
        ProductionInputError,
        GlobalBenchmarkContractError,
    ) as exc:
        raise FormalStreamingInputError(
            "streaming scorer parent changed after authentication"
        ) from exc
    return value


def _state(
    builder: StreamedProductionScoringBuilder,
) -> _StreamingBuilderState:
    require_streamed_production_scoring_builder(builder)
    with _STREAM_LOCK:
        return _STREAM_BUILDERS[id(builder)][2]


def _verify_c2_session(
    state: _StreamingBuilderState,
    block: PhysicalTerminalSessionBlock,
    seen: set[str],
) -> None:
    expected = state.expected_by_session.get(block.decision_session, ())
    if type(expected) is not tuple or any(
        type(item) is not NormalizedPreOutcomeRow for item in expected
    ):
        raise FormalStreamingInputError("streaming expected-session index changed")
    if not expected:
        return
    accepted = {item.security_id: item for item in block.accepted}
    refused = {item.security_id: item for item in block.refused}
    for row in expected:
        row.__post_init__()
        terminal = accepted.get(row.security_id)
        if terminal is None:
            reason = (
                FormalStreamingRefusalReason.C2_EVENT_TERMINAL_REFUSED
                if row.security_id in refused
                else FormalStreamingRefusalReason.C2_EVENT_TERMINAL_MISSING
            )
            raise FormalStreamingRunRefusal(
                reason,
                "an admitted physical C2 event lacks an accepted same-key terminal",
            )
        evidence = state.row_evidence[row.row_sha256]
        if not hasattr(evidence, "__post_init__"):
            raise FormalStreamingInputError("streaming row-evidence index changed")
        evidence.__post_init__()
        security = evidence.security
        sector = evidence.sector
        control = evidence.control
        quality = evidence.q_data
        if any(item is None for item in (security, sector, control, quality)):
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.C2_EVENT_TERMINAL_MISMATCH,
                "an admitted physical C2 event lacks complete evidence",
            )
        if (
            terminal.issuer_id != row.issuer_id
            or terminal.share_class_id != row.share_class_id
            or terminal.listing_id != row.listing_id
            or terminal.historical_ticker != row.historical_ticker
            or terminal.sector_id != row.sector_id
            or terminal.industry_id != row.industry_id
            or terminal.q_data != row.q_data
            or terminal.identity_evidence_sha256
            != row.identity_mapping_evidence_sha256
            or terminal.identity_available_at != security.available_at
            or terminal.classification_evidence_sha256
            != row.sector_evidence_sha256
            or terminal.classification_available_at != sector.available_at
            or terminal.q_data_evidence_sha256 != row.q_data_evidence_sha256
            or terminal.q_data_available_at != quality.available_at
            or terminal.control_evidence_sha256 != row.control_evidence_sha256
            or terminal.control_available_at != control.available_at
            or terminal.control_vector_sha256 != row.control_vector_sha256
        ):
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.C2_EVENT_TERMINAL_MISMATCH,
                "an admitted physical C2 event and same-key terminal disagree",
            )
        seen.add(row.row_sha256)


def _iter_verified_sessions(
    state: _StreamingBuilderState,
    observed: dict[str, int],
) -> Iterator[PhysicalTerminalSessionBlock]:
    seen: set[str] = set()
    for block in _iter_physical_terminal_sessions(state.archive):
        observed["maximum_physical_session_terminal_count"] = max(
            observed["maximum_physical_session_terminal_count"],
            block.terminal_count,
        )
        observed["maximum_physical_session_uncompressed_bytes"] = max(
            observed["maximum_physical_session_uncompressed_bytes"],
            block.raw_byte_count,
        )
        _verify_c2_session(state, block, seen)
        yield block
    if seen != set(state.union):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.C2_EVENT_TERMINAL_MISSING,
            "physical replay did not exhaust every admitted C2 row",
        )


def _score_session_arm(
    state: _StreamingBuilderState,
    fold: ProductionScoringFold,
    partition: FoldPartition,
    block: PhysicalTerminalSessionBlock,
    arm: SignalArm,
    observed: dict[str, int],
) -> tuple[tuple[PrecontrolDecisionRow, ...], tuple[ScoringRefusal, ...]]:
    batch, coverage_source = (
        (state.current_batch, state.current_coverage_source)
        if arm is SignalArm.CURRENT_VINTAGE
        else (state.censored_batch, state.censored_coverage_source)
    )
    security_ids = tuple(item.security_id for item in block.accepted)
    visible = formal_global_comparator_coverage_source_visible_contributions(
        coverage_source,
        decision_session=block.decision_session,
        security_ids=security_ids,
    )
    lineage_count = sum(len(item.linked_c2_row_sha256s) for item in visible)
    limits = dict(state.archive.capacity.limits)
    observed["maximum_active_contribution_count_per_arm_session"] = max(
        observed["maximum_active_contribution_count_per_arm_session"],
        len(visible),
    )
    observed["maximum_session_contribution_lineage_count"] = max(
        observed["maximum_session_contribution_lineage_count"],
        lineage_count,
    )
    if len(visible) > limits["max_active_contribution_count_per_arm_session"]:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.CONTRIBUTION_CAPACITY_EXCEEDED,
            "one arm/session active contribution state exceeded reviewed capacity",
        )
    if lineage_count > limits["max_session_contribution_lineage_count"]:
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.CONTRIBUTION_CAPACITY_EXCEEDED,
            "one arm/session contribution lineage exceeded reviewed capacity",
        )
    try:
        rows, refusals = _build_precontrol_session_terminals(
            batch=batch,
            fold=fold,
            partition=partition,
            session=block.decision_session,
            census_rows=block.accepted,
            refused_census_rows=block.refused,
            contributions=visible,
            ordinals=state.ordinals,
        )
    except ProductionScoringError as exc:
        raise FormalStreamingInputError(
            "streamed legacy-equivalent session score failed"
        ) from exc
    physical_keys = {
        (item.decision_session, item.security_id)
        for item in (*block.accepted, *block.refused)
    }
    output_keys = {
        (item.decision_session, item.security_id)
        for item in (*rows, *refusals)
    }
    if output_keys != physical_keys or len(rows) + len(refusals) != block.terminal_count:
        raise FormalStreamingInputError(
            "streamed session scoring is not exhaustive and exclusive"
        )
    return rows, refusals


def _model_record(model: StreamedControlModel) -> dict[str, object]:
    return model.to_record()


def _result_binding(
    state: _StreamingBuilderState,
    fold: ProductionScoringFold,
    models: tuple[StreamedControlModel, StreamedControlModel],
) -> ScoringResultBinding:
    precontrol_record = {
        "schema": "arv2-streamed-precontrol-commitment-v1",
        "archive_id": state.archive.archive_id,
        "archive_sha256": state.archive.archive_sha256,
        "production_evidence_receipt_id": state.evidence.receipt_id,
        "production_evidence_receipt_sha256": state.evidence.receipt_sha256,
        "fold": fold.to_record(),
        "current_batch_id": state.current_batch.batch_id,
        "current_batch_sha256": state.current_batch.batch_sha256,
        "censored_batch_id": state.censored_batch.batch_id,
        "censored_batch_sha256": state.censored_batch.batch_sha256,
        "event_terminal_projection_sha256": state.event_terminal_projection_sha256,
        "method_id": STREAMING_METHOD_ID,
    }
    precontrol_sha = sha256_bytes(canonical_json_bytes(precontrol_record))
    precontrol_id = f"arv2-streamed-precontrol-{precontrol_sha[:24]}"
    result_record = {
        "schema": "arv2-streamed-control-adjusted-result-binding-v1",
        "precontrol_batch_id": precontrol_id,
        "precontrol_batch_sha256": precontrol_sha,
        "fold_id": fold.fold_id,
        "models": [item.to_record() for item in models],
        "method_id": STREAMING_METHOD_ID,
        "final_terminal_roots_bound_by_fold_commitment": True,
    }
    result_sha = sha256_bytes(canonical_json_bytes(result_record))
    return ScoringResultBinding(
        fold_id=fold.fold_id,
        result_id=f"arv2-streamed-scoring-result-{result_sha[:24]}",
        result_sha256=result_sha,
        precontrol_batch_id=precontrol_id,
        precontrol_batch_sha256=precontrol_sha,
        model_sha256s=tuple(item.model_sha256 for item in models),
    )


def _test_block(
    *,
    fold: ProductionScoringFold,
    session: str,
    binding: ScoringResultBinding,
    current_rows: tuple[FinalDecisionInput, ...],
    current_refusals: tuple[ScoringRefusal, ...],
    censored_rows: tuple[FinalDecisionInput, ...],
    censored_refusals: tuple[ScoringRefusal, ...],
) -> StreamedTestSessionBlock:
    current_accepted = tuple(_streamed_decision(binding, item) for item in current_rows)
    current_refused = tuple(_streamed_refusal(binding, item) for item in current_refusals)
    censored_accepted = tuple(_streamed_decision(binding, item) for item in censored_rows)
    censored_refused = tuple(_streamed_refusal(binding, item) for item in censored_refusals)
    current_keys = tuple(
        sorted(item.security_id for item in (*current_accepted, *current_refused))
    )
    censored_keys = tuple(
        sorted(item.security_id for item in (*censored_accepted, *censored_refused))
    )
    if current_keys != censored_keys:
        raise FormalStreamingInputError(
            "streamed TEST source-view terminal blocks are omitted or unmatched"
        )
    matched_record = {
        "fold_id": fold.fold_id,
        "decision_session": session,
        "security_ids": list(current_keys),
    }
    matched_sha = sha256_bytes(canonical_json_bytes(matched_record))
    record = {
        "fold_id": fold.fold_id,
        "decision_session": session,
        "result_binding": binding.to_record(),
        "current_accepted": [item.to_record() for item in current_accepted],
        "current_refused": [item.to_record() for item in current_refused],
        "censored_accepted": [item.to_record() for item in censored_accepted],
        "censored_refused": [item.to_record() for item in censored_refused],
        "matched_terminal_count": len(current_keys),
        "matched_terminal_sha256": matched_sha,
    }
    block_id, digest, _payload = _post_identified(
        prefix="arv2-formal-streamed-test-block-",
        schema=STREAMING_SESSION_BLOCK_SCHEMA,
        record=record,
    )
    return StreamedTestSessionBlock(
        schema=STREAMING_SESSION_BLOCK_SCHEMA,
        block_id=block_id,
        block_sha256=digest,
        fold_id=fold.fold_id,
        decision_session=date.fromisoformat(session),
        current_accepted=current_accepted,
        current_refused=current_refused,
        censored_accepted=censored_accepted,
        censored_refused=censored_refused,
        matched_terminal_count=len(current_keys),
        matched_terminal_sha256=matched_sha,
    )


def _iter_streamed_production_scoring_fold_impl(
    builder: StreamedProductionScoringBuilder,
    *,
    _vault_acquire: object,
    _vault_require_lease: object,
    _vault_block: object,
    _vault_fold: object,
    _vault_revoke: object,
) -> Iterator[StreamedTestSessionBlock]:
    """Fit and consume exactly one next fold using three physical replay passes."""

    state = _state(builder)
    if state.finalized or state.active_fold or state.next_fold_index >= 6:
        raise FormalStreamingInputError("streaming scorer is busy, sealed, or exhausted")
    fold = build_formal_production_scoring_fold(2020 + state.next_fold_index)
    state, lease = _vault_acquire(builder, "formal_fold")
    observed = dict(state.observed)
    completed = False

    def commit_test_block(block: StreamedTestSessionBlock) -> None:
        nonlocal state
        state = _vault_block(builder, lease, block)

    def commit_fold(commitment: StreamedFoldCommitment) -> None:
        nonlocal state
        state = _vault_fold(builder, lease, commitment, observed)

    def enforce_coverage_capacity(
        accumulators: Mapping[SignalArm, object],
    ) -> None:
        try:
            coverage_bytes = sum(
                formal_global_comparator_coverage_accumulator_retained_bytes(
                    accumulators[arm]
                )
                for arm in SignalArm
            )
        except FormalInputBundleError as exc:
            raise FormalStreamingInputError(
                "streamed coverage retained-state measurement failed"
            ) from exc
        total = state.base_retained_input_graph_bytes + coverage_bytes
        observed["retained_input_graph_bytes"] = max(
            observed["retained_input_graph_bytes"], total
        )
        if total > dict(state.archive.capacity.limits)[
            "max_retained_input_graph_bytes"
        ]:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED,
                "streamed coverage state exceeded reviewed retained-graph capacity",
            )

    try:
        levels_by_arm = {arm: set() for arm in SignalArm}
        for block in _iter_verified_sessions(state, observed):
            partition = fold.partition(block.decision_session)
            if partition is not FoldPartition.TRAIN:
                continue
            for arm in SignalArm:
                rows, _refusals = _score_session_arm(
                    state, fold, partition, block, arm, observed
                )
                levels_by_arm[arm].update(
                    item.industry_id
                    for item in rows
                    if item.state is ScoreState.ACTIVE
                )
        levels = {
            arm: tuple(sorted(levels_by_arm[arm])) for arm in SignalArm
        }
        limits = dict(state.archive.capacity.limits)
        for arm in SignalArm:
            if not levels[arm]:
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.TRAINING_FIT_UNDERFILLED,
                    f"{arm.value} has no active train-only industry level",
                )
            if len(levels[arm]) > limits["max_industry_level_count_per_arm_fold"]:
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.IDENTITY_CAPACITY_EXCEEDED,
                    "train-only industry state exceeded reviewed capacity",
                )
            observed["maximum_industry_level_count_per_arm_fold"] = max(
                observed["maximum_industry_level_count_per_arm_fold"],
                len(levels[arm]),
            )
        qrs = {
            arm: _DiskBackedDecimalMgs(
                1 + len(CONTROL_COLUMNS) + len(levels[arm]) - 1, limits
            )
            for arm in SignalArm
        }
        for qr in qrs.values():
            observed["maximum_disk_mgs_width"] = max(
                observed["maximum_disk_mgs_width"], qr.width
            )
            observed["maximum_disk_mgs_live_decimal_count"] = max(
                observed["maximum_disk_mgs_live_decimal_count"], qr.decimal_count
            )
        for block in _iter_verified_sessions(state, observed):
            partition = fold.partition(block.decision_session)
            if partition is not FoldPartition.TRAIN:
                continue
            for arm in SignalArm:
                rows, _refusals = _score_session_arm(
                    state, fold, partition, block, arm, observed
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
                    qrs[arm].update(
                        design, row.firm_reliable_score, row.global_reliable_score
                    )
        for qr in qrs.values():
            observed["maximum_disk_mgs_spool_row_count"] = max(
                observed["maximum_disk_mgs_spool_row_count"], qr.row_count
            )
            observed["maximum_disk_mgs_spool_byte_count"] = max(
                observed["maximum_disk_mgs_spool_byte_count"],
                qr.peak_spool_bytes,
            )
            observed["maximum_disk_mgs_spool_file_count"] = max(
                observed["maximum_disk_mgs_spool_file_count"],
                qr.peak_spool_files,
            )
        models = tuple(
            _build_streamed_model(
                arm=arm, fold=fold, levels=levels[arm], qr=qrs[arm]
            )
            for arm in SignalArm
        )
        for qr in qrs.values():
            observed["maximum_disk_mgs_spool_byte_count"] = max(
                observed["maximum_disk_mgs_spool_byte_count"],
                qr.peak_spool_bytes,
            )
            observed["maximum_disk_mgs_spool_file_count"] = max(
                observed["maximum_disk_mgs_spool_file_count"],
                qr.peak_spool_files,
        )
        binding = _result_binding(state, fold, models)
        try:
            coverage_accumulators = {
                SignalArm.CURRENT_VINTAGE:
                    begin_formal_global_comparator_fold_coverage_from_source(
                        fold_id=fold.fold_id,
                        source=state.current_coverage_source,
                    ),
                SignalArm.CONSERVATIVE_CENSORED:
                    begin_formal_global_comparator_fold_coverage_from_source(
                        fold_id=fold.fold_id,
                        source=state.censored_coverage_source,
                    ),
            }
            enforce_coverage_capacity(coverage_accumulators)
            h20_boundary = formal_horizon_fold_boundary(fold.fold_id, 20)
        except (FormalInputBundleError, ProductionScoringError) as exc:
            raise FormalStreamingInputError(
                "streamed coverage parents or H20 axis failed authentication"
            ) from exc
        partition_counts = {
            (partition, arm): 0
            for partition in FoldPartition
            for arm in SignalArm
        }
        partition_hashers = {
            (partition, arm): _chain_hasher(
                f"arv2-streamed-{partition.value}-{arm.value}-terminal-v1"
            )
            for partition in FoldPartition
            for arm in SignalArm
        }
        for physical in _iter_verified_sessions(state, observed):
            partition = fold.partition(physical.decision_session)
            if partition is None:
                continue
            finals: dict[SignalArm, tuple[tuple[FinalDecisionInput, ...], tuple[ScoringRefusal, ...]]] = {}
            for arm, model in zip(SignalArm, models, strict=True):
                rows, refusals = _score_session_arm(
                    state, fold, partition, physical, arm, observed
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
                refusal_tuple = tuple(
                    sorted(terminal_refusals, key=lambda item: item.security_id)
                )
                if (
                    len(accepted_tuple) + len(refusal_tuple)
                    != physical.terminal_count
                ):
                    raise FormalStreamingInputError(
                        "streamed adjusted terminal census is not exhaustive"
                    )
                for item in sorted(
                    (*accepted_tuple, *refusal_tuple), key=lambda value: value.security_id
                ):
                    disposition = (
                        "accepted" if type(item) is FinalDecisionInput else "refused"
                    )
                    lineage = (
                        item.row_sha256
                        if type(item) is FinalDecisionInput
                        else item.refusal_sha256
                    )
                    _chain_update(
                        partition_hashers[(partition, arm)],
                        {
                            "decision_session": physical.decision_session,
                            "security_id": item.security_id,
                            "disposition": disposition,
                            "lineage_sha256": lineage,
                        },
                    )
                    partition_counts[(partition, arm)] += 1
                finals[arm] = (accepted_tuple, refusal_tuple)
            if (
                h20_boundary[6]
                <= physical.decision_session
                < h20_boundary[7]
            ):
                try:
                    for arm in SignalArm:
                        other_arm = (
                            SignalArm.CONSERVATIVE_CENSORED
                            if arm is SignalArm.CURRENT_VINTAGE
                            else SignalArm.CURRENT_VINTAGE
                        )
                        other_retained_bytes = (
                            formal_global_comparator_coverage_accumulator_retained_bytes(
                                coverage_accumulators[other_arm]
                            )
                        )
                        remaining_bytes = (
                            dict(state.archive.capacity.limits)[
                                "max_retained_input_graph_bytes"
                            ]
                            - state.base_retained_input_graph_bytes
                            - other_retained_bytes
                        )
                        if remaining_bytes <= 0:
                            raise FormalStreamingRunRefusal(
                                FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED,
                                "streamed coverage state exceeded reviewed retained-graph capacity",
                            )
                        transition_retained_bytes = record_formal_global_comparator_coverage_session(
                            coverage_accumulators[arm],
                            decision_session=physical.decision_session,
                            census_rows=physical.accepted,
                            final_rows=finals[arm][0],
                            final_refusals=finals[arm][1],
                            maximum_retained_bytes=remaining_bytes,
                        )
                        observed["retained_input_graph_bytes"] = max(
                            observed["retained_input_graph_bytes"],
                            state.base_retained_input_graph_bytes
                            + other_retained_bytes
                            + transition_retained_bytes,
                        )
                    enforce_coverage_capacity(coverage_accumulators)
                except FormalInputBundleError as exc:
                    if "exceeded reviewed capacity" in str(exc):
                        raise FormalStreamingRunRefusal(
                            FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED,
                            "streamed coverage state exceeded reviewed retained-graph capacity",
                        ) from exc
                    raise FormalStreamingInputError(
                        "streamed H20 coverage session failed authentication"
                    ) from exc
            # A physically authenticated zero-census session is still an
            # exact member of the frozen fold axis.  Emit its empty block so
            # downstream inference can distinguish zero eligible rows from a
            # silently omitted market session.
            if partition is FoldPartition.TEST:
                block = _test_block(
                    fold=fold,
                    session=physical.decision_session,
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
                commit_test_block(block)
                yield block
                if _vault_require_lease(builder, lease, "formal_fold") is not state:
                    _vault_revoke(builder)
                    raise FormalStreamingInputError(
                        "streaming scorer state changed"
                    )
        geometry = (
            fold.fold_id,
            fold.train_start,
            fold.train_end_exclusive,
            fold.validation_start,
            fold.validation_end_exclusive,
            fold.test_start,
            fold.test_end_exclusive,
        )
        try:
            coverages = tuple(
                finish_formal_global_comparator_fold_coverage(
                    coverage_accumulators[arm], result_binding=binding
                )
                for arm in SignalArm
            )
        except FormalInputBundleError as exc:
            raise FormalStreamingInputError(
                "streamed H20 coverage fold did not seal"
            ) from exc
        commitment = StreamedFoldCommitment(
            schema=STREAMING_FOLD_SCHEMA,
            fold_id=fold.fold_id,
            result_binding=binding,
            fold_geometry=geometry,
            model_records=tuple(_model_record(item) for item in models),
            global_comparator_coverages=coverages,
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
        commit_fold(commitment)
        completed = True
    finally:
        if not completed:
            _vault_revoke(builder)


def _finish_streamed_production_scoring_impl(
    builder: StreamedProductionScoringBuilder,
    *,
    _vault_finalize_artifact: object,
) -> StreamedProductionScoringArtifact:
    """Seal six exhausted streamed folds into a compact authenticated root."""

    state = _state(builder)
    if state.finalized or state.active_fold or state.next_fold_index != 6:
        raise FormalStreamingInputError(
            "streaming scoring is incomplete, busy, or already sealed"
        )
    fold_commitments = tuple(state.fold_commitments)
    result_bindings = tuple(item.result_binding for item in fold_commitments)
    try:
        pooled_coverages = tuple(
            pool_formal_global_comparator_coverages(tuple(
                commitment.global_comparator_coverages[arm_index]
                for commitment in fold_commitments
            ))
            for arm_index in range(len(SignalArm))
        )
    except FormalInputBundleError as exc:
        raise FormalStreamingInputError(
            "streamed global-comparator coverage did not pool"
        ) from exc
    record = {
        "schema": STREAMING_SCORING_SCHEMA,
        "archive_id": state.archive.archive_id,
        "archive_sha256": state.archive.archive_sha256,
        "production_evidence_receipt_id": state.evidence.receipt_id,
        "production_evidence_receipt_sha256": state.evidence.receipt_sha256,
        "capacity_receipt_id": state.archive.capacity.receipt_id,
        "capacity_receipt_sha256": state.archive.capacity.receipt_sha256,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "method_id": STREAMING_METHOD_ID,
        "paired_bootstrap_authority": _paired_bootstrap_authority_record(
            state.global_contract
        ),
        "result_bindings": [item.to_record() for item in result_bindings],
        "fold_commitments": [item.to_record() for item in fold_commitments],
        "pooled_global_comparator_coverages": [
            item.to_record() for item in pooled_coverages
        ],
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
    digest = sha256_bytes(canonical_json_bytes(record))
    value = object.__new__(StreamedProductionScoringArtifact)
    fields = {
        "artifact_id": f"arv2-formal-streamed-scoring-{digest[:24]}",
        "artifact_sha256": digest,
        "schema": STREAMING_SCORING_SCHEMA,
        "archive_id": state.archive.archive_id,
        "archive_sha256": state.archive.archive_sha256,
        "production_evidence_receipt_id": state.evidence.receipt_id,
        "production_evidence_receipt_sha256": state.evidence.receipt_sha256,
        "capacity_receipt_id": state.archive.capacity.receipt_id,
        "capacity_receipt_sha256": state.archive.capacity.receipt_sha256,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "method_id": STREAMING_METHOD_ID,
        "global_contract": state.global_contract,
        "result_bindings": result_bindings,
        "fold_commitments": fold_commitments,
        "pooled_global_comparator_coverages": pooled_coverages,
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
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    _vault_finalize_artifact(builder, value)
    return value


def _require_streamed_production_scoring_artifact_impl(
    value: StreamedProductionScoringArtifact,
    *,
    _artifact_current: object,
) -> StreamedProductionScoringArtifact:
    if type(value) is not StreamedProductionScoringArtifact:
        raise FormalStreamingInputError("streamed scoring artifact changed type")
    registered = _artifact_current(value)
    if registered is None or registered[0]() is not value:
        raise FormalStreamingInputError(
            "streamed scoring artifact is not builder-authenticated"
        )
    topology = _stream_artifact_topology(value)
    record = value.to_record()
    digest = sha256_bytes(canonical_json_bytes(record))
    if (
        registered[1] != canonical_json_bytes(record)
        or registered[2] != topology
        or require_loaded_global_benchmark_contract(value.global_contract)
        is not value.global_contract
        or value.artifact_sha256 != digest
        or value.artifact_id != f"arv2-formal-streamed-scoring-{digest[:24]}"
        or len(value.result_bindings) != 6
        or len(value.fold_commitments) != 6
        or tuple(item.fold_id for item in value.fold_commitments)
        != FORMAL_PRIMARY_FOLD_IDS
        or type(value.pooled_global_comparator_coverages) is not tuple
        or len(value.pooled_global_comparator_coverages) != 2
        or value.upstream_materialized_truth_count != 0
        or value.upstream_materialized_result_count != 0
        or any(
            type(flag) is not bool or flag
            for flag in (
                value.provider_access, value.outcome_access,
                value.quantconnect_access, value.qc_launch_available,
            )
        )
    ):
        raise FormalStreamingInputError(
            "streamed scoring artifact changed after authentication"
        )
    for fold_index, (commitment, binding) in enumerate(
        zip(value.fold_commitments, value.result_bindings, strict=True)
    ):
        if (
            commitment.result_binding is not binding
            or type(commitment.global_comparator_coverages) is not tuple
            or len(commitment.global_comparator_coverages) != 2
        ):
            raise FormalStreamingInputError(
                "streamed fold coverage topology changed"
            )
        for arm_index, coverage in enumerate(
            commitment.global_comparator_coverages
        ):
            try:
                require_formal_global_comparator_coverage(coverage)
            except FormalInputBundleError as exc:
                raise FormalStreamingInputError(
                    "streamed fold coverage failed authentication"
                ) from exc
            if (
                coverage.fold_ids != (FORMAL_PRIMARY_FOLD_IDS[fold_index],)
                or coverage.result_bindings != (binding,)
                or coverage.result_bindings[0] is not binding
                or coverage.source_view_id != SOURCE_VIEW_IDS[arm_index]
            ):
                raise FormalStreamingInputError(
                    "streamed fold coverage lineage changed"
                )
    for arm_index, coverage in enumerate(
        value.pooled_global_comparator_coverages
    ):
        try:
            require_formal_global_comparator_coverage(coverage)
        except FormalInputBundleError as exc:
            raise FormalStreamingInputError(
                "streamed pooled coverage failed authentication"
            ) from exc
        expected_parents = tuple(
            item.global_comparator_coverages[arm_index]
            for item in value.fold_commitments
        )
        if (
            coverage.fold_ids != FORMAL_PRIMARY_FOLD_IDS
            or coverage.source_view_id != SOURCE_VIEW_IDS[arm_index]
            or coverage.result_bindings
            != tuple(item.result_binding for item in value.fold_commitments)
            or any(
                actual is not parent.result_bindings[0]
                for actual, parent in zip(
                    coverage.result_bindings, expected_parents, strict=True
                )
            )
        ):
            raise FormalStreamingInputError(
                "streamed pooled coverage lineage changed"
            )
    return value


def _require_authoritative_scoring_replay(
    *,
    authoritative: StreamedProductionScoringArtifact,
    replay: StreamedProductionScoringArtifact,
    expected_global_contract: GlobalBenchmarkContract,
) -> StreamedProductionScoringArtifact:
    """Authenticate exact replay equivalence while retaining one authority.

    The census pass owns ``authoritative``.  The separate replay exists only
    because candidate construction must stream the same terminal rows into
    bounded physical shards.  Full canonical equality, exact parent lineage,
    and independent vault authentication make that replay substitutable while
    the candidate retains the census object's exact identity.
    """

    authoritative = require_streamed_production_scoring_artifact(authoritative)
    replay = require_streamed_production_scoring_artifact(replay)
    try:
        authoritative_record = canonical_json_bytes(authoritative.to_record())
        replay_record = canonical_json_bytes(replay.to_record())
    except (AttributeError, TypeError, ValueError) as exc:
        raise FormalStreamingInputError(
            "authoritative formal scorer did not authenticate"
        ) from exc
    if (
        authoritative is replay
        or authoritative.global_contract is not expected_global_contract
        or replay.global_contract is not expected_global_contract
        or authoritative.artifact_id != replay.artifact_id
        or authoritative.artifact_sha256 != replay.artifact_sha256
        or authoritative.archive_id != replay.archive_id
        or authoritative.archive_sha256 != replay.archive_sha256
        or authoritative.production_evidence_receipt_id
        != replay.production_evidence_receipt_id
        or authoritative.production_evidence_receipt_sha256
        != replay.production_evidence_receipt_sha256
        or authoritative.capacity_receipt_id != replay.capacity_receipt_id
        or authoritative.capacity_receipt_sha256 != replay.capacity_receipt_sha256
        or authoritative_record != replay_record
    ):
        raise FormalStreamingInputError(
            "formal scoring replay differs from the authoritative power census scorer"
        )
    return authoritative


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalFormalShardDescriptor:
    role: str
    ordinal: int
    schema: str
    object_store_key: str
    compression: str
    content_encoding: str
    compressed_sha256: str
    compressed_byte_count: int
    uncompressed_sha256: str
    uncompressed_byte_count: int
    row_count: int

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalFormalShardPayload:
    descriptor: PhysicalFormalShardDescriptor
    payload: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PhysicalFormalShardArchive:
    archive_id: str
    archive_sha256: str
    schema: str
    capacity: FormalStreamingCapacityBinding
    descriptors: tuple[PhysicalFormalShardDescriptor, ...]
    shard_paths: tuple[Path, ...] = dataclasses.field(repr=False)
    path_fingerprints: tuple[tuple[object, ...], ...] = dataclasses.field(repr=False)
    shard_count: int
    row_count: int
    compressed_byte_count: int
    maximum_live_block_row_count: int
    maximum_live_block_uncompressed_bytes: int
    maximum_live_shard_row_count: int
    maximum_live_shard_uncompressed_bytes: int
    outcome_access: bool = False
    quantconnect_access: bool = False
    qc_launch_available: bool = False


_FORMAL_ARCHIVES: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalFormalShardArchive], bytes,
        tuple[object, ...],
    ],
] = {}
_FORMAL_ARCHIVE_LOCK = threading.RLock()


def _forget_formal_archive(identity: int, reference: object) -> None:
    with _FORMAL_ARCHIVE_LOCK:
        current = _FORMAL_ARCHIVES.get(identity)
        if current is not None and current[0] is reference:
            _FORMAL_ARCHIVES.pop(identity, None)


def _formal_row_key(role: str, row: Mapping[str, object]) -> tuple[object, ...]:
    if role == "formal_contract":
        return (0,)
    if role == "contribution_seeds":
        intervals = row.get("active_intervals")
        if type(intervals) is not list or not intervals:
            raise FormalStreamingInputError("contribution seed lost active intervals")
        return (
            min(item[0] for item in intervals),
            SOURCE_VIEW_IDS.index(row["source_view_id"]),
            FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
            row["security_id"], row["seed_id"],
        )
    if role == "decision_joins":
        return (
            FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
            row["session_position"],
            SOURCE_VIEW_IDS.index(row["source_view_id"]),
            row["security_id"],
        )
    if role == "economic_joins":
        return (
            FORMAL_PRIMARY_FOLD_IDS.index(row["fold_id"]),
            row["session_position"],
            SOURCE_VIEW_IDS.index(row["source_view_id"]),
        )
    if role == "daily_requirements":
        return (row["session"], row["security_id"], row["requirement_id"])
    if role == "minute_requirements":
        return (
            row["first_active_session_position"], row["publication_at_utc"],
            row["security_id"], row["requirement_id"],
        )
    if role == "terminal_dispositions":
        return (
            row["slot_kind"], row["slot_id"],
            -1 if row["horizon"] is None else row["horizon"],
        )
    raise FormalStreamingInputError("formal shard role changed")


class _BoundedFormalDiskBuilder:
    """Internal writer whose measured live containers own every peak claim."""

    def __init__(
        self,
        *,
        output_directory: Path,
        capacity: FormalStreamingCapacityBinding,
    ) -> None:
        self.capacity = require_formal_streaming_capacity_binding(capacity)
        if type(output_directory) is not type(Path()) or not output_directory.is_absolute():
            raise FormalStreamingInputError("formal shard directory must be absolute")
        if output_directory.exists():
            if output_directory.is_symlink() or any(output_directory.iterdir()):
                raise FormalStreamingInputError(
                    "formal shard directory must be absent or an empty private directory"
                )
        else:
            output_directory.mkdir(mode=0o700, parents=False)
        observed = output_directory.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(observed.st_mode)
            or (os.name != "nt" and stat.S_IMODE(observed.st_mode) != 0o700)
            or (
                os.name != "nt" and hasattr(os, "getuid")
                and observed.st_uid != os.getuid()
            )
        ):
            raise FormalStreamingInputError("formal shard directory is not private")
        self.output_directory = output_directory
        self.limits = dict(self.capacity.limits)
        self.buffers: dict[str, list[tuple[tuple[object, ...], bytes]]] = {
            role: [] for role in SHARD_ROLE_ORDER
        }
        self.buffer_bytes = {role: 0 for role in SHARD_ROLE_ORDER}
        self.last_keys: dict[str, tuple[object, ...] | None] = {
            role: None for role in SHARD_ROLE_ORDER
        }
        self.ordinals = {role: 0 for role in SHARD_ROLE_ORDER}
        self.descriptors: list[PhysicalFormalShardDescriptor] = []
        self.paths: list[Path] = []
        self.fingerprints: list[tuple[object, ...]] = []
        self.total_compressed = 0
        self.maximum_live_block_row_count = 0
        self.maximum_live_block_uncompressed_bytes = 0
        self.maximum_live_shard_row_count = 0
        self.maximum_live_shard_uncompressed_bytes = 0
        self.sealed = False

    def add_block(self, role: str, rows: Sequence[Mapping[str, object]]) -> None:
        if self.sealed or role not in SHARD_ROLE_ORDER or type(rows) not in (tuple, list):
            raise FormalStreamingInputError("formal disk builder or block changed")
        encoded: list[tuple[tuple[object, ...], bytes]] = []
        for row in rows:
            if type(row) is not dict or row.get("schema") != SHARD_ROW_SCHEMAS[role]:
                raise FormalStreamingInputError("formal block row schema changed")
            key = _formal_row_key(role, row)
            payload = canonical_json_bytes(row)
            encoded.append((key, payload))
        encoded.sort(key=lambda item: item[0])
        keys = tuple(item[0] for item in encoded)
        if len(keys) != len(set(keys)) or (
            self.last_keys[role] is not None and keys and keys[0] <= self.last_keys[role]
        ):
            raise FormalStreamingInputError(
                "formal role stream repeated or reversed a canonical row key"
            )
        block_rows = len(encoded)
        block_bytes = sum(len(item[1]) for item in encoded)
        self.maximum_live_block_row_count = max(
            self.maximum_live_block_row_count, block_rows
        )
        self.maximum_live_block_uncompressed_bytes = max(
            self.maximum_live_block_uncompressed_bytes, block_bytes
        )
        if (
            block_rows > self.limits["max_formal_session_block_row_count"]
            or block_bytes
            > self.limits["max_formal_session_block_uncompressed_bytes"]
            or block_rows > self.limits["max_formal_shard_row_count"]
            or block_bytes > self.limits["max_formal_shard_uncompressed_bytes"]
        ):
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.FORMAL_BLOCK_CAPACITY_EXCEEDED,
                f"one {role} logical block exceeded reviewed capacity",
            )
        if self.buffers[role] and (
            len(self.buffers[role]) + block_rows
            > self.limits["max_formal_shard_row_count"]
            or self.buffer_bytes[role] + block_bytes
            > self.limits["max_formal_shard_uncompressed_bytes"]
        ):
            self._flush(role)
        self.buffers[role].extend(encoded)
        self.buffer_bytes[role] += block_bytes
        if keys:
            self.last_keys[role] = keys[-1]

    def _flush(self, role: str) -> None:
        rows = self.buffers[role]
        raw = b"".join(item[1] for item in rows)
        payload = gzip.compress(raw, compresslevel=9, mtime=0)
        if len(payload) > ABSOLUTE_MAX_SHARD_COMPRESSED_BYTES:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.FORMAL_OUTPUT_CAPACITY_EXCEEDED,
                f"one compressed {role} shard exceeded the absolute bound",
            )
        ordinal = self.ordinals[role]
        digest = sha256_bytes(payload)
        object_key = (
            f"{FORMAL_INPUT_CONTENT_PREFIX}{role}/"
            f"{ordinal:04d}-{digest}.jsonl.gz"
        )
        path = self.output_directory / (
            f"{SHARD_ROLE_ORDER.index(role):02d}-{role}-{ordinal:04d}-{digest}.jsonl.gz"
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags, 0o600)
            try:
                offset = 0
                while offset < len(payload):
                    offset += os.write(descriptor, payload[offset:])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise FormalStreamingInputError("formal content-addressed shard write failed") from exc
        _reloaded, fingerprint = _read_private_regular(
            path,
            maximum_bytes=max(1, len(payload)),
            name=f"formal {role} shard {ordinal}",
        )
        item = PhysicalFormalShardDescriptor(
            role=role,
            ordinal=ordinal,
            schema=COMPRESSED_SHARD_SCHEMA,
            object_store_key=object_key,
            compression=SHARD_COMPRESSION,
            content_encoding=SHARD_CONTENT_ENCODING,
            compressed_sha256=digest,
            compressed_byte_count=len(payload),
            uncompressed_sha256=sha256_bytes(raw),
            uncompressed_byte_count=len(raw),
            row_count=len(rows),
        )
        self.descriptors.append(item)
        self.paths.append(path)
        self.fingerprints.append(fingerprint)
        self.total_compressed += len(payload)
        self.maximum_live_shard_row_count = max(
            self.maximum_live_shard_row_count, len(rows)
        )
        self.maximum_live_shard_uncompressed_bytes = max(
            self.maximum_live_shard_uncompressed_bytes, len(raw)
        )
        if (
            len(self.descriptors) > self.limits["max_formal_shard_count"]
            or self.total_compressed
            > self.limits["max_formal_total_compressed_bytes"]
        ):
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.FORMAL_OUTPUT_CAPACITY_EXCEEDED,
                "physical formal shard inventory exceeded reviewed capacity",
            )
        self.ordinals[role] += 1
        self.buffers[role] = []
        self.buffer_bytes[role] = 0

    def finish(self) -> PhysicalFormalShardArchive:
        if self.sealed:
            raise FormalStreamingInputError("formal disk builder is already sealed")
        for role in SHARD_ROLE_ORDER:
            # One exact empty shard preserves the mandatory role inventory.
            if self.buffers[role] or self.ordinals[role] == 0:
                self._flush(role)
        ordered = tuple(
            sorted(
                zip(self.descriptors, self.paths, self.fingerprints, strict=True),
                key=lambda item: (
                    SHARD_ROLE_ORDER.index(item[0].role), item[0].ordinal
                ),
            )
        )
        descriptors = tuple(item[0] for item in ordered)
        paths = tuple(item[1] for item in ordered)
        fingerprints = tuple(item[2] for item in ordered)
        seed = {
            "schema": STREAMING_DISK_ARCHIVE_SCHEMA,
            "capacity_receipt_id": self.capacity.receipt_id,
            "capacity_receipt_sha256": self.capacity.receipt_sha256,
            "descriptors": [item.to_record() for item in descriptors],
            "shard_count": len(descriptors),
            "row_count": sum(item.row_count for item in descriptors),
            "compressed_byte_count": sum(
                item.compressed_byte_count for item in descriptors
            ),
            "measured_peaks": {
                "maximum_live_block_row_count": self.maximum_live_block_row_count,
                "maximum_live_block_uncompressed_bytes": (
                    self.maximum_live_block_uncompressed_bytes
                ),
                "maximum_live_shard_row_count": self.maximum_live_shard_row_count,
                "maximum_live_shard_uncompressed_bytes": (
                    self.maximum_live_shard_uncompressed_bytes
                ),
            },
            "payload_bytes_retained_in_archive": False,
            "sequential_reopen_and_rehash_required": True,
            "outcome_or_qc_action_authorized": False,
        }
        digest = sha256_bytes(canonical_json_bytes(seed))
        value = PhysicalFormalShardArchive(
            archive_id=f"arv2-formal-physical-shards-{digest[:24]}",
            archive_sha256=digest,
            schema=STREAMING_DISK_ARCHIVE_SCHEMA,
            capacity=self.capacity,
            descriptors=descriptors,
            shard_paths=paths,
            path_fingerprints=fingerprints,
            shard_count=len(descriptors),
            row_count=sum(item.row_count for item in descriptors),
            compressed_byte_count=sum(
                item.compressed_byte_count for item in descriptors
            ),
            maximum_live_block_row_count=self.maximum_live_block_row_count,
            maximum_live_block_uncompressed_bytes=(
                self.maximum_live_block_uncompressed_bytes
            ),
            maximum_live_shard_row_count=self.maximum_live_shard_row_count,
            maximum_live_shard_uncompressed_bytes=(
                self.maximum_live_shard_uncompressed_bytes
            ),
        )
        topology = (
            id(value.capacity), id(value.descriptors),
            tuple(id(item) for item in value.descriptors), id(value.shard_paths),
            tuple(id(item) for item in value.shard_paths), id(value.path_fingerprints),
        )
        identity = id(value)
        reference = weakref.ref(
            value, lambda ref, key=identity: _forget_formal_archive(key, ref)
        )
        with _FORMAL_ARCHIVE_LOCK:
            _FORMAL_ARCHIVES[identity] = (
                reference, canonical_json_bytes(seed), topology
            )
        self.sealed = True
        return require_physical_formal_shard_archive(value)


def _formal_archive_record(value: PhysicalFormalShardArchive) -> dict[str, object]:
    return {
        "schema": STREAMING_DISK_ARCHIVE_SCHEMA,
        "capacity_receipt_id": value.capacity.receipt_id,
        "capacity_receipt_sha256": value.capacity.receipt_sha256,
        "descriptors": [item.to_record() for item in value.descriptors],
        "shard_count": value.shard_count,
        "row_count": value.row_count,
        "compressed_byte_count": value.compressed_byte_count,
        "measured_peaks": {
            "maximum_live_block_row_count": value.maximum_live_block_row_count,
            "maximum_live_block_uncompressed_bytes": (
                value.maximum_live_block_uncompressed_bytes
            ),
            "maximum_live_shard_row_count": value.maximum_live_shard_row_count,
            "maximum_live_shard_uncompressed_bytes": (
                value.maximum_live_shard_uncompressed_bytes
            ),
        },
        "payload_bytes_retained_in_archive": False,
        "sequential_reopen_and_rehash_required": True,
        "outcome_or_qc_action_authorized": False,
    }


def require_physical_formal_shard_archive(
    value: PhysicalFormalShardArchive,
) -> PhysicalFormalShardArchive:
    if type(value) is not PhysicalFormalShardArchive:
        raise FormalStreamingInputError("physical formal archive changed type")
    with _FORMAL_ARCHIVE_LOCK:
        registered = _FORMAL_ARCHIVES.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalStreamingInputError(
            "physical formal archive is not writer-authenticated"
        )
    require_formal_streaming_capacity_binding(value.capacity)
    record = _formal_archive_record(value)
    digest = sha256_bytes(canonical_json_bytes(record))
    topology = (
        id(value.capacity), id(value.descriptors),
        tuple(id(item) for item in value.descriptors), id(value.shard_paths),
        tuple(id(item) for item in value.shard_paths), id(value.path_fingerprints),
    )
    if (
        registered[1] != canonical_json_bytes(record)
        or registered[2] != topology
        or value.archive_sha256 != digest
        or value.archive_id != f"arv2-formal-physical-shards-{digest[:24]}"
        or value.shard_count != len(value.descriptors)
        or value.shard_count != len(value.shard_paths)
        or value.row_count != sum(item.row_count for item in value.descriptors)
        or value.compressed_byte_count
        != sum(item.compressed_byte_count for item in value.descriptors)
        or tuple(
            sorted(
                value.descriptors,
                key=lambda item: (SHARD_ROLE_ORDER.index(item.role), item.ordinal),
            )
        ) != value.descriptors
        or any(
            type(flag) is not bool or flag
            for flag in (
                value.outcome_access, value.quantconnect_access,
                value.qc_launch_available,
            )
        )
    ):
        raise FormalStreamingInputError(
            "physical formal archive changed after construction"
        )
    for path, expected in zip(
        value.shard_paths, value.path_fingerprints, strict=True
    ):
        try:
            observed = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise FormalStreamingInputError("physical formal shard is unavailable") from exc
        current = (
            str(path), observed.st_dev, observed.st_ino, observed.st_size,
            observed.st_mtime_ns, observed.st_ctime_ns,
        )
        if path.is_symlink() or current != expected:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED,
                "physical formal shard identity changed after construction",
            )
    return value


def iter_physical_formal_shard_payloads(
    archive: PhysicalFormalShardArchive,
) -> Iterator[PhysicalFormalShardPayload]:
    """Reopen and re-hash one persisted formal shard at a time."""

    archive = require_physical_formal_shard_archive(archive)
    for index, (descriptor, path, expected) in enumerate(
        zip(
            archive.descriptors, archive.shard_paths,
            archive.path_fingerprints, strict=True,
        )
    ):
        payload, fingerprint = _read_private_regular(
            path,
            maximum_bytes=max(1, descriptor.compressed_byte_count),
            name=f"physical formal shard {index}",
        )
        if (
            fingerprint != expected
            or len(payload) != descriptor.compressed_byte_count
            or sha256_bytes(payload) != descriptor.compressed_sha256
        ):
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED,
                "physical formal shard content changed during sequential replay",
            )
        try:
            raw = gzip.decompress(payload)
        except (OSError, EOFError) as exc:
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED,
                "physical formal shard is not deterministic gzip",
            ) from exc
        lines = raw.splitlines(keepends=True)
        if (
            len(raw) != descriptor.uncompressed_byte_count
            or sha256_bytes(raw) != descriptor.uncompressed_sha256
            or len(lines) != descriptor.row_count
            or (raw and not raw.endswith(b"\n"))
        ):
            raise FormalStreamingRunRefusal(
                FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED,
                "physical formal shard decoded census changed",
            )
        for line in lines:
            row = _strict_object(line, "physical formal JSONL row")
            if row.get("schema") != SHARD_ROW_SCHEMAS[descriptor.role]:
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED,
                    "physical formal shard row schema changed",
                )
        # Do not pin an uncompressed payload and its line list in this
        # generator frame while the caller handles the one compressed payload.
        del raw, lines
        yield PhysicalFormalShardPayload(descriptor=descriptor, payload=payload)
        # Release the compressed payload before opening the successor.  The
        # caller may keep its emitted object, but this iterator never does.
        del payload


def iter_formal_qc_compressed_shards(
    archive: PhysicalFormalShardArchive,
) -> Iterator[FormalQcCompressedShard]:
    """Reopen one authenticated disk shard as one legacy transport value.

    The yielded value owns at most one compressed payload.  Consumers must not
    collect this iterator into a tuple; the legacy tuple upload path remains a
    prohibited materialization boundary for the streamed successor.
    """

    for physical in iter_physical_formal_shard_payloads(archive):
        descriptor = physical.descriptor
        value = FormalQcCompressedShard(
            role=descriptor.role,
            ordinal=descriptor.ordinal,
            schema=descriptor.schema,
            object_store_key=descriptor.object_store_key,
            compression=descriptor.compression,
            content_encoding=descriptor.content_encoding,
            compressed_sha256=descriptor.compressed_sha256,
            compressed_byte_count=descriptor.compressed_byte_count,
            uncompressed_sha256=descriptor.uncompressed_sha256,
            uncompressed_byte_count=descriptor.uncompressed_byte_count,
            row_count=descriptor.row_count,
            payload=physical.payload,
        )
        yield require_formal_qc_compressed_shard(value)


def _daily_requirement_row(security_id: str, session: date) -> dict[str, object]:
    text = session.isoformat()
    return {
        "schema": SHARD_ROW_SCHEMAS["daily_requirements"],
        "requirement_id": build_daily_market_requirement_id(
            security_id=security_id, session=text
        ),
        "security_id": security_id,
        "session": text,
    }


def _appearance_seeds(
    decision: ProductionScoredDecisionLineage,
    position: int,
    minute_rows: dict[tuple[str, str], dict[str, object]],
    limits: Mapping[str, int],
) -> tuple[list[dict[str, object]], dict[tuple[str, str], tuple[str, str | None]]]:
    rows: list[dict[str, object]] = []
    mapping: dict[tuple[str, str], tuple[str, str | None]] = {}
    for contribution in decision.contributions:
        with localcontext(_DECIMAL_CONTEXT):
            base = +(contribution.firm_absolute_decayed_weight / contribution.decay_weight)
        minute_id: str | None = None
        if contribution.publication_at_utc is not None:
            minute_id = build_minute_market_requirement_id(
                security_id=decision.security_id,
                publication_at_utc=contribution.publication_at_utc,
            )
            key = (decision.security_id, contribution.publication_at_utc)
            prior = minute_rows.get(key)
            first = position if prior is None else min(
                position, int(prior["first_active_session_position"])
            )
            last = position if prior is None else max(
                position, int(prior["last_active_session_position"])
            )
            minute_rows[key] = {
                "schema": SHARD_ROW_SCHEMAS["minute_requirements"],
                "requirement_id": minute_id,
                "security_id": decision.security_id,
                "publication_at_utc": contribution.publication_at_utc,
                "first_active_session_position": first,
                "last_active_session_position": last,
            }
            if len(minute_rows) > limits["max_retained_minute_requirement_count"]:
                raise FormalStreamingRunRefusal(
                    FormalStreamingRefusalReason.IDENTITY_CAPACITY_EXCEEDED,
                    "minute requirement identity state exceeded reviewed capacity",
                )
        record = {
            "source_view_id": decision.source_view_id,
            "fold_id": decision.fold_id,
            "security_id": decision.security_id,
            "representative_c2_row_sha256": (
                contribution.representative_c2_row_sha256
            ),
            "linked_c2_row_sha256s": list(contribution.linked_c2_row_sha256s),
            "representative_provider_event_id": (
                contribution.representative_provider_event_id
            ),
            "institution_id": contribution.institution_id,
            "common_event_id": contribution.common_event_id,
            "rating_action": contribution.rating_action,
            "publication_at_utc": contribution.publication_at_utc,
            "minute_requirement_id": minute_id,
            "eligible_session": contribution.eligible_session,
            "eligible_session_position": position - contribution.age_sessions,
            "base_absolute_firm_weight": _decimal_text(base),
            "active_intervals": [[position, position + 1]],
        }
        seed_id, seed_sha = _identified(
            "arv2-formal-contribution-seed-",
            SHARD_ROW_SCHEMAS["contribution_seeds"],
            record,
        )
        row = {
            "schema": SHARD_ROW_SCHEMAS["contribution_seeds"],
            "seed_id": seed_id,
            "seed_sha256": seed_sha,
            **record,
        }
        rows.append(row)
        map_key = (decision.decision_id, contribution.lineage_sha256)
        if map_key in mapping:
            raise FormalStreamingInputError(
                "one streamed contribution appearance repeated"
            )
        mapping[map_key] = (seed_id, minute_id)
    return rows, mapping


def _contribution_state_sha256(
    decision: ProductionScoredDecisionLineage,
    mapping: Mapping[tuple[str, str], tuple[str, str | None]],
) -> str:
    values = []
    for contribution in decision.contributions:
        seed_id, minute_id = mapping[(decision.decision_id, contribution.lineage_sha256)]
        values.append(
            {
                "contribution_seed_id": seed_id,
                "contribution_lineage_sha256": contribution.lineage_sha256,
                "publication_at_utc": contribution.publication_at_utc,
                "minute_requirement_id": minute_id,
                "firm_absolute_decayed_weight": _decimal_text(
                    contribution.firm_absolute_decayed_weight
                ),
            }
        )
    values.sort(key=lambda item: item["contribution_lineage_sha256"])
    return sha256_bytes(
        canonical_json_bytes(
            {
                "domain": "arv2-formal-qc-contribution-state-v1",
                "contributions": values,
            }
        )
    )


def _streamed_decision_row(
    *,
    decision: ProductionScoredDecisionLineage,
    position: int,
    axis: Sequence[date],
    benchmark_security_id: str,
    daily: dict[tuple[str, str], dict[str, object]],
    seed_mapping: Mapping[tuple[str, str], tuple[str, str | None]],
    horizons: tuple[int, ...],
) -> dict[str, object]:
    entry = _daily_requirement_row(decision.security_id, decision.decision_session)
    benchmark_entry = _daily_requirement_row(
        benchmark_security_id, decision.decision_session
    )
    daily[(decision.security_id, decision.decision_session.isoformat())] = entry
    daily[(benchmark_security_id, decision.decision_session.isoformat())] = benchmark_entry
    exits = []
    if (
        type(horizons) is not tuple
        or not horizons
        or tuple(item for item in HORIZONS if item in horizons) != horizons
    ):
        raise FormalStreamingInputError(
            "streamed decision horizon subset is not canonical"
        )
    for horizon in horizons:
        exit_position = position + horizon
        if exit_position >= len(axis):
            raise FormalStreamingInputError("streamed decision lacks its horizon exit")
        exit_session = axis[exit_position]
        stock = _daily_requirement_row(decision.security_id, exit_session)
        benchmark = _daily_requirement_row(benchmark_security_id, exit_session)
        daily[(decision.security_id, exit_session.isoformat())] = stock
        daily[(benchmark_security_id, exit_session.isoformat())] = benchmark
        exits.append(
            {
                "horizon": horizon,
                "exit_session": exit_session.isoformat(),
                "exit_session_position": exit_position,
                "stock_daily_requirement_id": stock["requirement_id"],
                "benchmark_daily_requirement_id": benchmark["requirement_id"],
            }
        )
    continuous = decision.transformed_controls[: len(CONTINUOUS_COLUMNS)]
    binary = decision.transformed_controls[len(CONTINUOUS_COLUMNS):]
    if len(continuous) != 19 or len(binary) != len(BINARY_COLUMNS) or any(
        item not in (Decimal(0), Decimal(1)) for item in binary
    ):
        raise FormalStreamingInputError("streamed decision lost exact 19+6 controls")
    return {
        "schema": SHARD_ROW_SCHEMAS["decision_joins"],
        "decision_id": decision.decision_id,
        "decision_lineage_sha256": decision.lineage_sha256,
        "source_view_id": decision.source_view_id,
        "fold_id": decision.fold_id,
        "decision_session": decision.decision_session.isoformat(),
        "session_position": position,
        "security_id": decision.security_id,
        "disposition": "scored_decision",
        "scoring_disposition": (
            "included_structural_zero" if decision.structural_zero
            else "included_active"
        ),
        "source_row_sha256": decision.final_scoring_row_sha256,
        "scoring_result_id": decision.scoring_result_id,
        "scoring_result_sha256": decision.scoring_result_sha256,
        "scoring_contract_id": decision.scoring_contract_id,
        "scoring_contract_sha256": decision.scoring_contract_sha256,
        "industry_id": decision.industry_id,
        "common_event_component_id": decision.common_event_component_id,
        "structural_zero": decision.structural_zero,
        "firm_specific_score": _decimal_text(decision.firm_specific_score),
        "global_score": _decimal_text(decision.global_score),
        "continuous_controls": [_decimal_text(item) for item in continuous],
        "binary_controls": [int(item) for item in binary],
        "realized_volatility_60d": _decimal_text(
            decision.realized_volatility_60d
        ),
        "earnings_anchor_signed_session_distance": (
            decision.earnings_anchor_signed_session_distance
        ),
        "contribution_count": len(decision.contributions),
        "contribution_state_sha256": _contribution_state_sha256(
            decision, seed_mapping
        ),
        "entry_daily_requirement_id": entry["requirement_id"],
        "benchmark_entry_daily_requirement_id": benchmark_entry["requirement_id"],
        "horizon_exits": exits,
    }


def _streamed_refusal_row(
    refusal: ProductionScoringCensusRefusal, position: int
) -> dict[str, object]:
    return {
        "schema": SHARD_ROW_SCHEMAS["decision_joins"],
        "decision_id": refusal.refusal_id,
        "decision_lineage_sha256": refusal.refusal_sha256,
        "source_view_id": refusal.source_view_id,
        "fold_id": refusal.fold_id,
        "decision_session": refusal.decision_session.isoformat(),
        "session_position": position,
        "security_id": refusal.security_id,
        "disposition": "named_preoutcome_refusal",
        "scoring_disposition": refusal.disposition,
        "source_row_sha256": refusal.source_refusal_sha256,
        "scoring_result_id": refusal.scoring_result_id,
        "scoring_result_sha256": refusal.scoring_result_sha256,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "industry_id": None,
        "common_event_component_id": None,
        "structural_zero": None,
        "firm_specific_score": None,
        "global_score": None,
        "continuous_controls": None,
        "binary_controls": None,
        "realized_volatility_60d": None,
        "earnings_anchor_signed_session_distance": None,
        "contribution_count": 0,
        "contribution_state_sha256": None,
        "entry_daily_requirement_id": None,
        "benchmark_entry_daily_requirement_id": None,
        "horizon_exits": [],
    }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class StreamedFormalInputCandidate:
    candidate_id: str
    candidate_sha256: str
    schema: str
    scoring: StreamedProductionScoringArtifact
    shards: PhysicalFormalShardArchive
    accepted_risk: AcceptedRiskPairBinding
    formal_power: FormalPowerCalibrationBinding
    power_floor: PowerFloorBinding
    economic_execution: FormalEconomicExecutionBinding
    report_contract: FormalReportContract
    terminal_package: FormalTerminalDispositionPackage
    terminal_build: FormalTerminalDispositionBuild | None
    benchmark_security_id: str
    calculation_as_of_date: date
    source_view_partitions: tuple[dict[str, object], dict[str, object]]
    contribution_seed_count: int
    decision_join_count: int
    economic_join_count: int
    daily_requirement_count: int
    minute_requirement_count: int
    terminal_disposition_count: int
    caller_authored_scores_accepted: bool
    physical_shard_payloads_retained: bool
    qc_launch_available: bool

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "streamed_scoring_id": self.scoring.artifact_id,
            "streamed_scoring_sha256": self.scoring.artifact_sha256,
            "physical_formal_shard_archive_id": self.shards.archive_id,
            "physical_formal_shard_archive_sha256": self.shards.archive_sha256,
            "accepted_risk": self.accepted_risk.to_record(),
            "formal_power": self.formal_power.to_record(),
            "power_floor": self.power_floor.to_record(),
            "economic_execution_binding": (
                formal_economic_execution_binding_record(
                    self.economic_execution
                )
            ),
            "economic_execution_definition_id": (
                self.economic_execution.definition_id
            ),
            "economic_execution_definition_sha256": (
                self.economic_execution.definition_sha256
            ),
            "formal_report_contract": formal_report_contract_record(
                self.report_contract
            ),
            "terminal_package_id": self.terminal_package.package_id,
            "terminal_package_sha256": self.terminal_package.package_sha256,
            "terminal_build_id": (
                None if self.terminal_build is None else self.terminal_build.build_id
            ),
            "terminal_build_sha256": (
                None
                if self.terminal_build is None
                else self.terminal_build.build_sha256
            ),
            "lifecycle_derived_terminal_build": self.terminal_build is not None,
            "benchmark_security_id": self.benchmark_security_id,
            "calculation_as_of_date": self.calculation_as_of_date.isoformat(),
            "source_view_partitions": list(self.source_view_partitions),
            "role_counts": {
                "contribution_seeds": self.contribution_seed_count,
                "decision_joins": self.decision_join_count,
                "economic_joins": self.economic_join_count,
                "daily_requirements": self.daily_requirement_count,
                "minute_requirements": self.minute_requirement_count,
                "terminal_dispositions": self.terminal_disposition_count,
            },
            "caller_authored_scores_accepted": self.caller_authored_scores_accepted,
            "physical_shard_payloads_retained": self.physical_shard_payloads_retained,
            "qc_launch_available": self.qc_launch_available,
        }


_STREAMED_FORMAL_CANDIDATES: dict[
    int,
    tuple[
        weakref.ReferenceType[StreamedFormalInputCandidate], bytes,
        tuple[object, ...],
    ],
] = {}
_STREAMED_FORMAL_LOCK = threading.RLock()


def _make_streamed_formal_candidate_authority():
    records: dict[
        int,
        tuple[
            tuple[
                weakref.ReferenceType[StreamedFormalInputCandidate],
                bytes,
                tuple[object, ...],
            ],
            int,
        ],
    ] = {}

    def forget(identity: int, reference: object) -> None:
        with _STREAMED_FORMAL_LOCK:
            private = records.get(identity)
            if private is not None and private[0][0] is reference:
                records.pop(identity, None)
                if _STREAMED_FORMAL_CANDIDATES.get(identity) is private[0]:
                    _STREAMED_FORMAL_CANDIDATES.pop(identity, None)

    def register(
        value: StreamedFormalInputCandidate,
        record: bytes,
        topology: tuple[object, ...],
    ) -> None:
        identity = id(value)
        reference = weakref.ref(
            value, lambda ref, key=identity: forget(key, ref)
        )
        public = (reference, record, topology)
        with _STREAMED_FORMAL_LOCK:
            if identity in records or identity in _STREAMED_FORMAL_CANDIDATES:
                raise FormalStreamingInputError(
                    "streamed formal candidate identity was reused"
                )
            records[identity] = (public, os.getpid())
            _STREAMED_FORMAL_CANDIDATES[identity] = public

    def current(
        value: StreamedFormalInputCandidate,
    ) -> tuple[object, ...] | None:
        identity = id(value)
        with _STREAMED_FORMAL_LOCK:
            private = records.get(identity)
            public = _STREAMED_FORMAL_CANDIDATES.get(identity)
            if (
                private is None
                or public is not private[0]
                or private[0][0]() is not value
                or private[1] != os.getpid()
            ):
                records.pop(identity, None)
                _STREAMED_FORMAL_CANDIDATES.pop(identity, None)
                return None
            return private[0]

    def reset_after_fork() -> None:
        global _STREAMED_FORMAL_CANDIDATES, _STREAMED_FORMAL_LOCK

        records.clear()
        _STREAMED_FORMAL_CANDIDATES = {}
        _STREAMED_FORMAL_LOCK = threading.RLock()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)
    return register, current


(
    _candidate_authority_register,
    _candidate_authority_current,
) = _make_streamed_formal_candidate_authority()


def _partition_terminal_update(
    state: dict[str, dict[str, object]],
    row: ProductionScoredDecisionLineage | ProductionScoringCensusRefusal,
) -> None:
    item = state[row.source_view_id]
    item["decision_count"] += 1
    if type(row) is ProductionScoredDecisionLineage:
        item["scored_decision_count"] += 1
    else:
        item["named_preoutcome_refusal_count"] += 1
    _chain_update(
        item["terminal_hasher"],
        {
            "fold_id": row.fold_id,
            "session_position": item["session_position"],
            "security_id": row.security_id,
        },
    )


def _flush_daily_through(
    *,
    daily: dict[tuple[str, str], dict[str, object]],
    through: date | None,
    writer: _BoundedFormalDiskBuilder,
    limits: Mapping[str, int],
) -> int:
    if (
        len(daily) > limits["max_daily_requirement_keys_retained"]
        or len({key[1] for key in daily})
        > limits["max_daily_requirement_sessions_retained"]
    ):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.IDENTITY_CAPACITY_EXCEEDED,
            "pending daily requirement window exceeded reviewed capacity",
        )
    ready_keys = tuple(
        sorted(
            (
                key for key in daily
                if through is None or date.fromisoformat(key[1]) <= through
            ),
            key=lambda key: (key[1], key[0]),
        )
    )
    by_session: dict[str, list[dict[str, object]]] = defaultdict(list)
    for key in ready_keys:
        by_session[key[1]].append(daily.pop(key))
    count = 0
    for session in sorted(by_session):
        rows = sorted(
            by_session[session], key=lambda row: (row["security_id"], row["requirement_id"])
        )
        writer.add_block("daily_requirements", rows)
        count += len(rows)
    return count


def _formal_stream_layout_record() -> dict[str, object]:
    return {
        "layout_id": STREAM_LAYOUT_ID,
        "role_sort_keys": {
            role: list(fields) for role, fields in STREAM_ROLE_SORT_KEYS.items()
        },
        "session_or_market_day_blocks_never_split_across_shards": True,
        "formal_contract_and_economic_axis_are_bounded_headers": True,
        "terminal_dispositions_are_the_actual_lifecycle_subset": True,
        "market_observation_collection_passes": 2,
        "maximum_horizon_session_lookahead": 60,
        "second_pass_rederives_observations": True,
        "terminal_subset_is_capacity_bounded_header": True,
    }


def _formal_terminal_census_record(
    terminal_package: FormalTerminalDispositionPackage,
) -> dict[str, object]:
    census = terminal_package.terminal_census
    return {
        "terminal_policy_id": census.terminal_policy_id,
        "terminal_requirement_count": census.terminal_requirement_count,
        "terminal_payoff_count": census.terminal_payoff_count,
        "benchmark_splice_continuation_count": (
            census.benchmark_splice_continuation_count
        ),
        "named_terminal_refusal_count": census.named_terminal_refusal_count,
        "silently_omitted_count": census.silently_omitted_count,
    }


def _paired_bootstrap_authority_record(
    global_contract: GlobalBenchmarkContract,
) -> dict[str, object]:
    contract = require_loaded_global_benchmark_contract(global_contract)
    seed = dict(bootstrap_seed_record(contract))
    seed_sha256 = sha256_bytes(canonical_json_bytes(seed))
    summaries = [dict(item) for item in contract.fold_axis_summaries]
    if (
        tuple(seed) != (
            "domain", "successor_stock_spec_sha256",
            "matched_row_contract_sha256", "global_rating_map_sha256",
            "fold_manifest_sha256", "evaluation_id", "sampler_version",
        )
        or seed["successor_stock_spec_sha256"] != contract.successor_spec_hash
        or seed["matched_row_contract_sha256"] != contract.matched_contract_hash
        or seed["global_rating_map_sha256"] != contract.map_hash
        or seed["evaluation_id"] != EVALUATION_ID
        or len(summaries) != 6
    ):
        raise FormalStreamingInputError(
            "paired bootstrap authority diverged from its authenticated contract"
        )
    return {
        "schema": "arv2-streamed-paired-bootstrap-authority-v1",
        "global_rating_map_id": contract.map_id,
        "global_rating_map_sha256": contract.map_hash,
        "matched_comparison_contract_id": contract.matched_contract_id,
        "matched_comparison_contract_sha256": contract.matched_contract_hash,
        "successor_stock_spec_id": contract.successor_spec_id,
        "successor_stock_spec_sha256": contract.successor_spec_hash,
        "evaluation_id": contract.evaluation_id,
        "seed_record": seed,
        "seed_record_sha256": seed_sha256,
        "fold_axis_summaries": summaries,
    }


def _formal_fold_horizon_axes_record() -> list[dict[str, object]]:
    axis, positions = _axis()
    records: list[dict[str, object]] = []
    for boundary in FORMAL_HORIZON_FOLD_BOUNDARIES:
        (
            fold_id, horizon, _train_start, _train_end, _validation_start,
            _validation_end, test_start, test_end,
        ) = boundary
        if formal_horizon_fold_boundary(fold_id, horizon) != boundary:
            raise FormalStreamingInputError(
                "formal horizon boundary no longer authenticates"
            )
        start = date.fromisoformat(test_start)
        end = date.fromisoformat(test_end)
        sessions = tuple(item for item in axis if start <= item < end)
        if (
            not sessions
            or sessions[0] != start
            or any(item not in positions for item in sessions)
        ):
            raise FormalStreamingInputError(
                "formal horizon session axis cannot be derived exactly"
            )
        session_payload = json.dumps(
            tuple(item.isoformat() for item in sessions),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        records.append({
            "fold_id": fold_id,
            "horizon_sessions": horizon,
            "test_start": test_start,
            "test_end_exclusive": test_end,
            "session_count": len(sessions),
            "session_axis_sha256": sha256_bytes(session_payload),
        })
    if len(records) != 24:
        raise FormalStreamingInputError("formal fold-horizon axis census changed")
    return records


def _active_horizons(fold_id: str, session: date) -> tuple[int, ...]:
    horizons = tuple(
        horizon
        for horizon in HORIZONS
        if (
            date.fromisoformat(
                formal_horizon_fold_boundary(fold_id, horizon)[6]
            )
            <= session
            < date.fromisoformat(
                formal_horizon_fold_boundary(fold_id, horizon)[7]
            )
        )
    )
    if not horizons or horizons[0] != 1:
        raise FormalStreamingInputError(
            "scored TEST session escaped the reviewed H1 union axis"
        )
    return horizons


def _economic_axis_sha256(sessions: Sequence[date]) -> str:
    payload = (
        json.dumps(
            [item.isoformat() for item in sessions],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        + b"\n"
    )
    return sha256_bytes(payload)


def _economic_fold_observation_geometry(
    economic_execution: FormalEconomicExecutionBinding,
    axis: Sequence[date],
    positions: Mapping[date, int],
) -> dict[str, dict[str, object]]:
    """Derive all runoff/liquidation sessions from the authenticated definition."""

    binding = require_formal_economic_execution_binding(economic_execution)
    definition = formal_economic_execution_definition_record(binding.definition)
    sample = definition.get("sample_and_clock")
    raw = None if type(sample) is not dict else sample.get("fold_geometry")
    if type(raw) is not list or len(raw) != len(FORMAL_PRIMARY_FOLD_IDS):
        raise FormalStreamingInputError(
            "economic execution definition lost its six fold geometries"
        )
    result: dict[str, dict[str, object]] = {}
    axis_tuple = tuple(axis)
    for expected_fold, item in zip(FORMAL_PRIMARY_FOLD_IDS, raw, strict=True):
        if type(item) is not dict or item.get("fold_id") != expected_fold:
            raise FormalStreamingInputError(
                "economic execution fold geometry changed order"
            )
        try:
            decision_start = date.fromisoformat(
                str(item["decision_axis_start_inclusive"])
            )
            decision_end = date.fromisoformat(
                str(item["decision_axis_end_exclusive"])
            )
            terminal_session = date.fromisoformat(
                str(item["terminal_liquidation_session"])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FormalStreamingInputError(
                "economic execution fold dates changed"
            ) from exc
        decisions = tuple(
            session
            for session in axis_tuple
            if decision_start <= session < decision_end
        )
        returns = tuple(
            session
            for session in axis_tuple
            if decision_start <= session < terminal_session
        )
        observations = (*returns, terminal_session)
        h20 = formal_horizon_fold_boundary(expected_fold, 20)
        if (
            decision_start.isoformat() != h20[6]
            or decision_end.isoformat() != h20[7]
            or not decisions
            or not returns
            or terminal_session not in positions
            or len(decisions) != item.get("decision_session_count")
            or _economic_axis_sha256(decisions)
            != item.get("decision_axis_sha256")
            or decisions[-1].isoformat() != item.get("last_decision_session")
            or len(returns) != item.get("return_interval_count")
            or _economic_axis_sha256(returns)
            != item.get("return_interval_start_axis_sha256")
            or len(observations)
            != item.get("economic_observation_count_including_terminal_cost")
            or _economic_axis_sha256(observations)
            != item.get("economic_observation_axis_sha256")
        ):
            raise FormalStreamingInputError(
                "economic execution geometry differs from the reviewed NYSE axis"
            )
        result[expected_fold] = {
            "decision_start": decision_start,
            "decision_end": decision_end,
            "decision_sessions": decisions,
            "return_sessions": returns,
            "runoff_sessions": tuple(
                session for session in returns if session >= decision_end
            ),
            "terminal_session": terminal_session,
            "observation_sessions": observations,
        }
    return result


def _streamed_economic_join_row(
    *,
    view: str,
    fold_id: str,
    session: date,
    session_position: int,
    next_session: date | None,
    next_session_position: int | None,
    observation_kind: str,
) -> dict[str, object]:
    if observation_kind not in ECONOMIC_OBSERVATION_KINDS:
        raise FormalStreamingInputError("economic observation kind changed")
    decision_eligible = observation_kind == "h20_decision_return_interval"
    terminal = observation_kind == "terminal_liquidation_cost"
    if terminal is not (next_session is None and next_session_position is None):
        raise FormalStreamingInputError(
            "economic terminal observation changed its next-session state"
        )
    if not terminal and (
        type(next_session) is not date
        or type(next_session_position) is not int
        or next_session_position != session_position + 1
    ):
        raise FormalStreamingInputError(
            "economic return observation lost its next NYSE session"
        )
    record = {
        "source_view_id": view,
        "fold_id": fold_id,
        "session": session.isoformat(),
        "session_position": session_position,
        "next_session": (
            None if next_session is None else next_session.isoformat()
        ),
        "next_session_position": next_session_position,
        "h20_decision_eligible": decision_eligible,
        "economic_observation_kind": observation_kind,
    }
    return {
        "schema": SHARD_ROW_SCHEMAS["economic_joins"],
        **record,
        "source_lineage_sha256": sha256_bytes(canonical_json_bytes({
            "schema": SHARD_ROW_SCHEMAS["economic_joins"],
            **record,
        })),
    }


def _build_streamed_formal_contract_record(
    *,
    scoring: StreamedProductionScoringArtifact,
    accepted_risk: AcceptedRiskPairBinding,
    formal_power: FormalPowerCalibrationBinding,
    power_floor: PowerFloorBinding,
    economic_execution: FormalEconomicExecutionBinding,
    report_contract: FormalReportContract,
    terminal_package: FormalTerminalDispositionPackage,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    source_view_partitions: tuple[dict[str, object], dict[str, object]],
    benchmark_security_id: str,
    calculation_as_of_date: date,
) -> dict[str, object]:
    """Render the exact streamed variant of the common shard-row envelope."""

    return {
        "schema": SHARD_ROW_SCHEMAS["formal_contract"],
        "contract_variant": STREAMED_FORMAL_CONTRACT_VARIANT,
        "evaluation_id": EVALUATION_ID,
        "streamed_scoring_id": scoring.artifact_id,
        "streamed_scoring_sha256": scoring.artifact_sha256,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "scoring_result_bindings": [
            item.to_record() for item in scoring.result_bindings
        ],
        "paired_bootstrap_authority": _paired_bootstrap_authority_record(
            scoring.global_contract
        ),
        "fold_horizon_axes": _formal_fold_horizon_axes_record(),
        "global_comparator_fold_coverages": [
            coverage.to_record()
            for commitment in scoring.fold_commitments
            for coverage in commitment.global_comparator_coverages
        ],
        "global_comparator_pooled_coverages": [
            coverage.to_record()
            for coverage in scoring.pooled_global_comparator_coverages
        ],
        "physical_preopen_archive": {
            "archive_id": scoring.archive_id,
            "archive_sha256": scoring.archive_sha256,
            "preopen_acquisition_id": preopen_acquisition_receipt.artifact_id,
            "preopen_acquisition_sha256": (
                preopen_acquisition_receipt.artifact_sha256
            ),
        },
        "production_evidence_receipt": {
            "receipt_id": scoring.production_evidence_receipt_id,
            "receipt_sha256": scoring.production_evidence_receipt_sha256,
        },
        "accepted_risk": accepted_risk.to_record(),
        "formal_power": formal_power.to_record(),
        "power_floor": power_floor.to_record(),
        "economic_execution_binding": (
            formal_economic_execution_binding_record(economic_execution)
        ),
        "economic_execution_definition": (
            formal_economic_execution_definition_record(
                economic_execution.definition
            )
        ),
        "formal_report_contract": formal_report_contract_record(
            report_contract
        ),
        "terminal_package_id": terminal_package.package_id,
        "terminal_package_sha256": terminal_package.package_sha256,
        "terminal_policy_id": TERMINAL_POLICY_ID,
        "terminal_census": _formal_terminal_census_record(terminal_package),
        "source_view_partitions": list(source_view_partitions),
        "stream_layout": _formal_stream_layout_record(),
        "benchmark_security_id": benchmark_security_id,
        "calculation_as_of_date": calculation_as_of_date.isoformat(),
        "streaming_method_id": STREAMING_METHOD_ID,
        "appearance_seed_semantics": APPEARANCE_SEED_SEMANTICS,
        "legacy_six_result_materialization_used": False,
        "outcome_or_qc_action_authorized": False,
    }


def _build_streamed_formal_input_candidate_impl(
    *,
    scoring_builder: StreamedProductionScoringBuilder,
    authoritative_scoring_artifact: StreamedProductionScoringArtifact | None,
    accepted_risk: AcceptedRiskPairBinding,
    formal_power: FormalPowerCalibrationBinding,
    power_floor: PowerFloorBinding,
    economic_execution: FormalEconomicExecutionBinding,
    terminal_package: FormalTerminalDispositionPackage | None,
    terminal_recorder: FormalTerminalDispositionRecorder | None,
    benchmark_security_id: str,
    calculation_as_of_date: date,
    output_directory: Path,
    _candidate_register: object,
) -> StreamedFormalInputCandidate:
    """Run six folds and persist every formal role without retaining payloads.

    ``output_directory`` is caller-owned.  A refusal before sealing deliberately
    leaves any already-written content-addressed files as recoverable, untrusted
    residue; no archive/candidate authority is minted for that directory.
    """

    state = _state(scoring_builder)
    if state.next_fold_index != 0 or state.active_fold or state.finalized:
        raise FormalStreamingInputError("formal streaming requires a fresh scorer")
    try:
        accepted_risk = require_accepted_risk_pair_binding(accepted_risk)
        formal_power = require_formal_power_calibration_binding(formal_power)
        power_floor = require_power_floor_binding(power_floor)
        economic_execution = require_formal_economic_execution_binding(
            economic_execution
        )
        report_contract = build_formal_report_contract(
            economic_execution_definition_sha256=(
                economic_execution.definition_sha256
            )
        )
        require_formal_report_contract(
            report_contract,
            expected_economic_execution_definition_sha256=(
                economic_execution.definition_sha256
            ),
        )
        require_identifier(benchmark_security_id, "benchmark_security_id")
    except (
        FormalEconomicExecutionDefinitionError,
        FormalReportContractError,
        TypeError,
        ValueError,
    ) as exc:
        raise FormalStreamingInputError(
            "streamed formal parents or accepted-risk pair did not authenticate"
        ) from exc
    if (terminal_package is None) == (terminal_recorder is None):
        raise FormalStreamingInputError(
            "exactly one terminal package or lifecycle recorder is required"
        )
    try:
        if terminal_recorder is None:
            assert terminal_package is not None
            terminal_package = require_formal_terminal_disposition_package(
                terminal_package
            )
        else:
            require_fresh_formal_terminal_disposition_recorder(terminal_recorder)
    except (TypeError, ValueError) as exc:
        raise FormalStreamingInputError(
            "formal terminal input did not authenticate"
        ) from exc
    if (
        accepted_risk.pair.artifact_id != state.current_batch.pair_id
        or accepted_risk.pair.content_sha256 != state.current_batch.pair_sha256
        or state.current_batch.pair_id != state.censored_batch.pair_id
        or state.current_batch.pair_sha256 != state.censored_batch.pair_sha256
        or accepted_risk.capture_id
        != state.evidence.authority.pair.capture.capture_id
        or accepted_risk.capture_sha256
        != state.evidence.authority.pair.capture.capture_sha256
        or accepted_risk.current_source_included_count
        != state.current_batch.source_view_included_count
        or accepted_risk.censored_source_included_count
        != state.censored_batch.source_view_included_count
        or accepted_risk.current_admitted_decision_count
        != state.current_batch.normalized_row_count
        or accepted_risk.current_named_preoutcome_refusal_count
        != (
            state.current_batch.source_view_included_count
            - state.current_batch.normalized_row_count
        )
        or accepted_risk.censored_admitted_decision_count
        != state.censored_batch.normalized_row_count
        or accepted_risk.censored_named_preoutcome_refusal_count
        != (
            state.censored_batch.source_view_included_count
            - state.censored_batch.normalized_row_count
        )
        or accepted_risk.guidance_admitted_count != 0
        or accepted_risk.pre_2013_admitted_count != 0
        or formal_power.receipt_id != power_floor.numeric_receipt.artifact_id
        or formal_power.receipt_sha256
        != power_floor.numeric_receipt.content_sha256
        or formal_power.disposition != power_floor.disposition
        or formal_power.required_valid_dates != power_floor.required_valid_dates
        or formal_power.required_connected_components
        != power_floor.required_connected_components
        or formal_power.fixed_h20_test_session_capacity
        != power_floor.h20_test_session_capacity
        or type(calculation_as_of_date) is not date
        or calculation_as_of_date <= date(2026, 1, 2)
    ):
        raise FormalStreamingInputError(
            "accepted-risk pair, source views, or calculation date changed"
        )
    if terminal_package is not None and any(
        date.fromisoformat(item.available_at_utc[:10]) > calculation_as_of_date
        for item in terminal_package.rows
    ):
        raise FormalStreamingInputError(
            "terminal disposition was unavailable at calculation_as_of_date"
        )
    axis, positions = _axis()
    economic_geometry = _economic_fold_observation_geometry(
        economic_execution, axis, positions
    )
    limits = dict(state.archive.capacity.limits)
    writer = _BoundedFormalDiskBuilder(
        output_directory=output_directory, capacity=state.archive.capacity
    )
    minute_rows: dict[tuple[str, str], dict[str, object]] = {}
    daily_rows: dict[tuple[str, str], dict[str, object]] = {}
    actual_terminal_keys = (
        {
            (item.slot_kind, item.slot_id, item.horizon_sessions)
            for item in terminal_package.rows
        }
        if terminal_package is not None
        else set()
    )
    unmatched_terminal = set(actual_terminal_keys)
    securities: set[str] = set()
    actual_terminal_slot_count = 0
    partition = {
        view: {
            "decision_count": 0,
            "scored_decision_count": 0,
            "named_preoutcome_refusal_count": 0,
            "terminal_hasher": _chain_hasher(
                "arv2-formal-terminal-key-census-v2"
            ),
        }
        for view in SOURCE_VIEW_IDS
    }
    active_holdings: dict[
        tuple[str, str], list[tuple[int, tuple[str, ...]]]
    ] = {}
    counts = {
        "contribution_seeds": 0,
        "decision_joins": 0,
        "economic_joins": 0,
        "daily_requirements": 0,
        "minute_requirements": 0,
        "terminal_dispositions": 0,
    }

    def add_economic_observation(
        *,
        view: str,
        fold_id: str,
        session: date,
        observation_kind: str,
        accepted: tuple[ProductionScoredDecisionLineage, ...] = (),
    ) -> dict[str, object]:
        nonlocal actual_terminal_slot_count

        position = positions.get(session)
        if position is None:
            raise FormalStreamingInputError(
                "economic observation escaped the reviewed runtime axis"
            )
        terminal = observation_kind == "terminal_liquidation_cost"
        next_position = None if terminal else position + 1
        if next_position is not None and next_position >= len(axis):
            raise FormalStreamingInputError(
                "economic return observation lacks a next session"
            )
        next_session = None if next_position is None else axis[next_position]
        holding_key = (view, fold_id)
        active = active_holdings.setdefault(holding_key, [])
        if observation_kind == "h20_decision_return_interval":
            active.append((20, _selected_sleeve(accepted)))
        elif accepted:
            raise FormalStreamingInputError(
                "nondecision economic observation received decisions"
            )
        if terminal:
            if active:
                raise FormalStreamingInputError(
                    "terminal liquidation preceded scheduled sleeve runoff"
                )
        elif observation_kind in {
            "h20_decision_return_interval",
            "h20_runoff_return_interval",
        }:
            assert next_session is not None
            held = tuple(sorted({
                security
                for _remaining, sleeve in active
                for security in sleeve
            }))
            for security, market_session in (
                (benchmark_security_id, session),
                (benchmark_security_id, next_session),
                *(
                    pair
                    for security in held
                    for pair in (
                        (security, session),
                        (security, next_session),
                    )
                ),
            ):
                daily_rows[(security, market_session.isoformat())] = (
                    _daily_requirement_row(security, market_session)
                )
            for security in held:
                slot_id = _economic_terminal_slot_id(
                    view_id=view,
                    fold_id=fold_id,
                    session_position=position,
                    security_id=security,
                )
                unmatched_terminal.discard(("economic_daily", slot_id, None))
                if terminal_recorder is not None:
                    inserted = record_formal_terminal_slot(
                        terminal_recorder,
                        slot_kind="economic_daily",
                        slot_id=slot_id,
                        horizon_sessions=None,
                        security_id=security,
                        first_session=session,
                        last_session=next_session,
                    )
                    actual_terminal_slot_count += int(inserted)
            active_holdings[holding_key] = [
                (remaining - 1, sleeve)
                for remaining, sleeve in active
                if remaining > 1
            ]
        elif observation_kind != "non_economic_decision_session":
            raise FormalStreamingInputError(
                "economic observation kind changed execution behavior"
            )
        return _streamed_economic_join_row(
            view=view,
            fold_id=fold_id,
            session=session,
            session_position=position,
            next_session=next_session,
            next_session_position=next_position,
            observation_kind=observation_kind,
        )

    for fold_index in range(6):
        expected_fold = FORMAL_PRIMARY_FOLD_IDS[fold_index]
        for block in iter_streamed_production_scoring_fold(scoring_builder):
            if block.fold_id != expected_fold:
                raise FormalStreamingInputError("streamed fold order changed")
            position = positions.get(block.decision_session)
            if position is None:
                raise FormalStreamingInputError(
                    "streamed TEST session escaped the reviewed runtime axis"
                )
            active_horizons = _active_horizons(
                block.fold_id, block.decision_session
            )
            seed_block: list[dict[str, object]] = []
            decision_block: list[dict[str, object]] = []
            economic_block: list[dict[str, object]] = []
            view_values = (
                (
                    CURRENT_VIEW_LABEL,
                    block.current_accepted,
                    block.current_refused,
                ),
                (
                    CENSORED_VIEW_LABEL,
                    block.censored_accepted,
                    block.censored_refused,
                ),
            )
            for view, accepted, refused in view_values:
                for item in (*accepted, *refused):
                    if (
                        terminal_recorder is not None
                        and item.security_id not in securities
                    ):
                        record_formal_terminal_security(
                            terminal_recorder, security_id=item.security_id
                        )
                    securities.add(item.security_id)
                    _chain_update(
                        partition[view]["terminal_hasher"],
                        {
                            "fold_id": item.fold_id,
                            "session_position": position,
                            "security_id": item.security_id,
                        },
                    )
                    partition[view]["decision_count"] += 1
                    if type(item) is ProductionScoredDecisionLineage:
                        partition[view]["scored_decision_count"] += 1
                    else:
                        partition[view]["named_preoutcome_refusal_count"] += 1
                if len(securities) > limits["max_retained_security_count"]:
                    raise FormalStreamingRunRefusal(
                        FormalStreamingRefusalReason.IDENTITY_CAPACITY_EXCEEDED,
                        "formal security identity state exceeded reviewed capacity",
                    )
                for decision in accepted:
                    seeds, mapping = _appearance_seeds(
                        decision, position, minute_rows, limits
                    )
                    seed_block.extend(seeds)
                    decision_row = _streamed_decision_row(
                        decision=decision,
                        position=position,
                        axis=axis,
                        benchmark_security_id=benchmark_security_id,
                        daily=daily_rows,
                        seed_mapping=mapping,
                        horizons=active_horizons,
                    )
                    decision_block.append(decision_row)
                    for exit_row in decision_row["horizon_exits"]:
                        horizon = int(exit_row["horizon"])
                        slot_id = _decision_terminal_slot_id(
                            decision_id=decision.decision_id,
                            horizon=horizon,
                        )
                        unmatched_terminal.discard(
                            ("decision_horizon", slot_id, horizon)
                        )
                        if terminal_recorder is not None:
                            inserted = record_formal_terminal_slot(
                                terminal_recorder,
                                slot_kind="decision_horizon",
                                slot_id=slot_id,
                                horizon_sessions=horizon,
                                security_id=decision.security_id,
                                first_session=decision.decision_session,
                                last_session=date.fromisoformat(
                                    str(exit_row["exit_session"])
                                ),
                            )
                            actual_terminal_slot_count += int(inserted)
                decision_block.extend(
                    _streamed_refusal_row(item, position) for item in refused
                )
                observation_kind = (
                    "h20_decision_return_interval"
                    if 20 in active_horizons
                    else "non_economic_decision_session"
                )
                economic_block.append(add_economic_observation(
                    view=view,
                    fold_id=block.fold_id,
                    session=block.decision_session,
                    observation_kind=observation_kind,
                    accepted=(accepted if 20 in active_horizons else ()),
                ))
            writer.add_block("contribution_seeds", seed_block)
            writer.add_block("decision_joins", decision_block)
            writer.add_block("economic_joins", economic_block)
            counts["contribution_seeds"] += len(seed_block)
            counts["decision_joins"] += len(decision_block)
            counts["economic_joins"] += len(economic_block)
            counts["daily_requirements"] += _flush_daily_through(
                daily=daily_rows,
                through=block.decision_session,
                writer=writer,
                limits=limits,
            )
        fold_geometry = economic_geometry[expected_fold]
        for runoff_session in fold_geometry["runoff_sessions"]:
            economic_block = [
                add_economic_observation(
                    view=view,
                    fold_id=expected_fold,
                    session=runoff_session,
                    observation_kind="h20_runoff_return_interval",
                )
                for view in SOURCE_VIEW_IDS
            ]
            writer.add_block("economic_joins", economic_block)
            counts["economic_joins"] += len(economic_block)
        terminal_session = fold_geometry["terminal_session"]
        economic_block = [
            add_economic_observation(
                view=view,
                fold_id=expected_fold,
                session=terminal_session,
                observation_kind="terminal_liquidation_cost",
            )
            for view in SOURCE_VIEW_IDS
        ]
        writer.add_block("economic_joins", economic_block)
        counts["economic_joins"] += len(economic_block)
    replay_scoring = finish_streamed_production_scoring(scoring_builder)
    scoring = replay_scoring
    if authoritative_scoring_artifact is not None:
        # The replay exists only to emit the bounded physical shards.  The
        # candidate retains the exact object already authenticated by the
        # formal power census, after proving byte-for-byte scoring equality.
        scoring = _require_authoritative_scoring_replay(
            authoritative=authoritative_scoring_artifact,
            replay=replay_scoring,
            expected_global_contract=state.global_contract,
        )
    all_coverages = (
        *(
            coverage
            for commitment in scoring.fold_commitments
            for coverage in commitment.global_comparator_coverages
        ),
        *scoring.pooled_global_comparator_coverages,
    )
    if len(all_coverages) != 14 or any(
        require_formal_global_comparator_coverage(coverage).ready is not True
        for coverage in all_coverages
    ):
        raise FormalStreamingRunRefusal(
            FormalStreamingRefusalReason.GLOBAL_COMPARATOR_COVERAGE_UNDERFILLED,
            "all five outcome-free ledgers must pass in both views, every fold, and pooled",
        )
    counts["daily_requirements"] += _flush_daily_through(
        daily=daily_rows,
        through=None,
        writer=writer,
        limits=limits,
    )
    minute_groups: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in minute_rows.values():
        minute_groups[int(row["first_active_session_position"])].append(row)
    for position in sorted(minute_groups):
        values = sorted(
            minute_groups[position],
            key=lambda row: (
                row["publication_at_utc"], row["security_id"], row["requirement_id"]
            ),
        )
        writer.add_block("minute_requirements", values)
        counts["minute_requirements"] += len(values)
    terminal_build: FormalTerminalDispositionBuild | None = None
    if terminal_recorder is not None:
        try:
            terminal_build = finalize_formal_terminal_disposition_recording(
                recorder=terminal_recorder,
                calculation_as_of_date=calculation_as_of_date,
            )
        except FormalTerminalDispositionBuildError as exc:
            raise FormalStreamingInputError(
                "lifecycle-derived terminal package could not be finalized"
            ) from exc
        terminal_package = terminal_build.terminal_package
        if (
            terminal_build.actual_slot_count != actual_terminal_slot_count
            or terminal_build.security_count != len(securities)
        ):
            raise FormalStreamingInputError(
                "lifecycle-derived terminal build disagrees with streamed slots"
            )
    assert terminal_package is not None
    if (
        unmatched_terminal
        or terminal_package.terminal_census.security_count != len(securities)
        or terminal_package.terminal_census.lifecycle_coverage_count != len(securities)
    ):
        raise FormalStreamingInputError(
            "actual lifecycle terminal package does not map exhaustively to the streamed census"
        )
    terminal_rows = [item.to_record() for item in terminal_package.rows]
    writer.add_block("terminal_dispositions", terminal_rows)
    counts["terminal_dispositions"] = len(terminal_rows)
    source_partitions = tuple(
        {
            "view_id": view,
            "decision_count": partition[view]["decision_count"],
            "scored_decision_count": partition[view]["scored_decision_count"],
            "named_preoutcome_refusal_count": partition[view][
                "named_preoutcome_refusal_count"
            ],
            "terminal_key_sha256": partition[view]["terminal_hasher"].hexdigest(),
        }
        for view in SOURCE_VIEW_IDS
    )
    if (
        source_partitions[0]["decision_count"]
        != source_partitions[1]["decision_count"]
        or source_partitions[0]["decision_count"]
        != scoring.matched_test_terminal_count
        or counts["contribution_seeds"] < 1
        or counts["decision_joins"] < 1
        or counts["economic_joins"] < 1
        or counts["daily_requirements"] < 1
    ):
        raise FormalStreamingInputError(
            "streamed formal role census is empty or source views are unmatched"
        )
    if authoritative_scoring_artifact is not None:
        scoring = _require_authoritative_scoring_replay(
            authoritative=authoritative_scoring_artifact,
            replay=replay_scoring,
            expected_global_contract=state.global_contract,
        )
    contract = _build_streamed_formal_contract_record(
        scoring=scoring,
        accepted_risk=accepted_risk,
        formal_power=formal_power,
        power_floor=power_floor,
        economic_execution=economic_execution,
        report_contract=report_contract,
        terminal_package=terminal_package,
        preopen_acquisition_receipt=state.archive.preopen_acquisition_receipt,
        source_view_partitions=source_partitions,
        benchmark_security_id=benchmark_security_id,
        calculation_as_of_date=calculation_as_of_date,
    )
    writer.add_block("formal_contract", [contract])
    shards = writer.finish()
    record = {
        "schema": STREAMING_FORMAL_CANDIDATE_SCHEMA,
        "streamed_scoring_id": scoring.artifact_id,
        "streamed_scoring_sha256": scoring.artifact_sha256,
        "physical_formal_shard_archive_id": shards.archive_id,
        "physical_formal_shard_archive_sha256": shards.archive_sha256,
        "accepted_risk": accepted_risk.to_record(),
        "formal_power": formal_power.to_record(),
        "power_floor": power_floor.to_record(),
        "economic_execution_binding": (
            formal_economic_execution_binding_record(economic_execution)
        ),
        "economic_execution_definition_id": economic_execution.definition_id,
        "economic_execution_definition_sha256": (
            economic_execution.definition_sha256
        ),
        "formal_report_contract": formal_report_contract_record(
            report_contract
        ),
        "terminal_package_id": terminal_package.package_id,
        "terminal_package_sha256": terminal_package.package_sha256,
        "terminal_build_id": (
            None if terminal_build is None else terminal_build.build_id
        ),
        "terminal_build_sha256": (
            None if terminal_build is None else terminal_build.build_sha256
        ),
        "lifecycle_derived_terminal_build": terminal_build is not None,
        "benchmark_security_id": benchmark_security_id,
        "calculation_as_of_date": calculation_as_of_date.isoformat(),
        "source_view_partitions": list(source_partitions),
        "role_counts": dict(counts),
        "caller_authored_scores_accepted": False,
        "physical_shard_payloads_retained": False,
        "qc_launch_available": False,
    }
    digest = sha256_bytes(canonical_json_bytes(record))
    value = object.__new__(StreamedFormalInputCandidate)
    fields = {
        "candidate_id": f"arv2-formal-streamed-input-{digest[:24]}",
        "candidate_sha256": digest,
        "schema": STREAMING_FORMAL_CANDIDATE_SCHEMA,
        "scoring": scoring,
        "shards": shards,
        "accepted_risk": accepted_risk,
        "formal_power": formal_power,
        "power_floor": power_floor,
        "economic_execution": economic_execution,
        "report_contract": report_contract,
        "terminal_package": terminal_package,
        "terminal_build": terminal_build,
        "benchmark_security_id": benchmark_security_id,
        "calculation_as_of_date": calculation_as_of_date,
        "source_view_partitions": source_partitions,
        "contribution_seed_count": counts["contribution_seeds"],
        "decision_join_count": counts["decision_joins"],
        "economic_join_count": counts["economic_joins"],
        "daily_requirement_count": counts["daily_requirements"],
        "minute_requirement_count": counts["minute_requirements"],
        "terminal_disposition_count": counts["terminal_dispositions"],
        "caller_authored_scores_accepted": False,
        "physical_shard_payloads_retained": False,
        "qc_launch_available": False,
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    topology = (
        id(value.scoring), id(value.shards), id(value.accepted_risk),
        id(value.formal_power), id(value.power_floor),
        id(value.economic_execution), id(value.economic_execution.definition),
        id(value.report_contract),
        id(value.terminal_package),
        id(value.terminal_build),
        id(value.source_view_partitions),
    )
    _candidate_register(value, canonical_json_bytes(record), topology)
    return value


def _build_streamed_formal_input_candidate_public_impl(
    *,
    scoring_builder: StreamedProductionScoringBuilder,
    authoritative_scoring_artifact: StreamedProductionScoringArtifact | None = None,
    accepted_risk: AcceptedRiskPairBinding,
    formal_power: FormalPowerCalibrationBinding,
    power_floor: PowerFloorBinding,
    economic_execution: FormalEconomicExecutionBinding,
    terminal_package: FormalTerminalDispositionPackage,
    benchmark_security_id: str,
    calculation_as_of_date: date,
    output_directory: Path,
    _candidate_register: object,
    _candidate_builder: object,
) -> StreamedFormalInputCandidate:
    """Legacy synthetic composition path; not eligible for runtime submission."""

    return _candidate_builder(
        scoring_builder=scoring_builder,
        authoritative_scoring_artifact=authoritative_scoring_artifact,
        accepted_risk=accepted_risk,
        formal_power=formal_power,
        power_floor=power_floor,
        economic_execution=economic_execution,
        terminal_package=terminal_package,
        terminal_recorder=None,
        benchmark_security_id=benchmark_security_id,
        calculation_as_of_date=calculation_as_of_date,
        output_directory=output_directory,
        _candidate_register=_candidate_register,
    )


def _build_lifecycle_streamed_formal_input_candidate_impl(
    *,
    scoring_builder: StreamedProductionScoringBuilder,
    authoritative_scoring_artifact: StreamedProductionScoringArtifact | None = None,
    accepted_risk: AcceptedRiskPairBinding,
    formal_power: FormalPowerCalibrationBinding,
    power_floor: PowerFloorBinding,
    economic_execution: FormalEconomicExecutionBinding,
    terminal_recorder: FormalTerminalDispositionRecorder,
    benchmark_security_id: str,
    calculation_as_of_date: date,
    output_directory: Path,
    _candidate_register: object,
    _candidate_builder: object,
) -> StreamedFormalInputCandidate:
    """Compose slots first, then finalize their lifecycle-derived package."""

    try:
        return _candidate_builder(
            scoring_builder=scoring_builder,
            authoritative_scoring_artifact=authoritative_scoring_artifact,
            accepted_risk=accepted_risk,
            formal_power=formal_power,
            power_floor=power_floor,
            economic_execution=economic_execution,
            terminal_package=None,
            terminal_recorder=terminal_recorder,
            benchmark_security_id=benchmark_security_id,
            calculation_as_of_date=calculation_as_of_date,
            output_directory=output_directory,
            _candidate_register=_candidate_register,
        )
    except FormalTerminalDispositionBuildError as exc:
        raise FormalStreamingInputError(
            "lifecycle-derived terminal recording failed during streamed emission"
        ) from exc


def _build_streamed_formal_input_candidate_from_reviewed_lifecycle_impl(
    *,
    scoring_builder: StreamedProductionScoringBuilder,
    authoritative_scoring_artifact: StreamedProductionScoringArtifact | None = None,
    accepted_risk: AcceptedRiskPairBinding,
    formal_power: FormalPowerCalibrationBinding,
    power_floor: PowerFloorBinding,
    economic_execution: FormalEconomicExecutionBinding,
    historical_bridge: historical_module.ReviewedHistoricalUniverseToPreopenBridge,
    terminal_output_directory: Path,
    benchmark_security_id: str,
    calculation_as_of_date: date,
    output_directory: Path,
    _candidate_register: object,
    _candidate_builder: object,
    _lifecycle_builder: object,
) -> StreamedFormalInputCandidate:
    """Authenticate the full-axis lifecycle sidecar and compose in one call."""

    try:
        recorder = begin_formal_terminal_disposition_recording(
            historical_bridge=historical_bridge,
            output_directory=terminal_output_directory,
        )
    except FormalTerminalDispositionBuildError as exc:
        raise FormalStreamingInputError(
            "reviewed lifecycle sidecar could not begin terminal recording"
        ) from exc
    return _lifecycle_builder(
        scoring_builder=scoring_builder,
        authoritative_scoring_artifact=authoritative_scoring_artifact,
        accepted_risk=accepted_risk,
        formal_power=formal_power,
        power_floor=power_floor,
        economic_execution=economic_execution,
        terminal_recorder=recorder,
        benchmark_security_id=benchmark_security_id,
        calculation_as_of_date=calculation_as_of_date,
        output_directory=output_directory,
        _candidate_register=_candidate_register,
        _candidate_builder=_candidate_builder,
    )


def _require_streamed_formal_input_candidate_impl(
    value: StreamedFormalInputCandidate,
    *,
    _candidate_current: object,
) -> StreamedFormalInputCandidate:
    if type(value) is not StreamedFormalInputCandidate:
        raise FormalStreamingInputError("streamed formal candidate changed type")
    registered = _candidate_current(value)
    if registered is None or registered[0]() is not value:
        raise FormalStreamingInputError(
            "streamed formal candidate is not builder-authenticated"
        )
    require_streamed_production_scoring_artifact(value.scoring)
    all_coverages = (
        *(
            coverage
            for commitment in value.scoring.fold_commitments
            for coverage in commitment.global_comparator_coverages
        ),
        *value.scoring.pooled_global_comparator_coverages,
    )
    if len(all_coverages) != 14 or any(
        require_formal_global_comparator_coverage(coverage).ready is not True
        for coverage in all_coverages
    ):
        raise FormalStreamingInputError(
            "streamed candidate global-comparator coverage gate is closed"
        )
    require_physical_formal_shard_archive(value.shards)
    require_accepted_risk_pair_binding(value.accepted_risk)
    require_formal_power_calibration_binding(value.formal_power)
    require_power_floor_binding(value.power_floor)
    try:
        require_formal_economic_execution_binding(value.economic_execution)
        require_formal_report_contract(
            value.report_contract,
            expected_economic_execution_definition_sha256=(
                value.economic_execution.definition_sha256
            ),
        )
    except (
        FormalEconomicExecutionDefinitionError,
        FormalReportContractError,
    ) as exc:
        raise FormalStreamingInputError(
            "streamed economic execution binding no longer authenticates"
        ) from exc
    require_formal_terminal_disposition_package(value.terminal_package)
    if value.terminal_build is not None:
        try:
            require_formal_terminal_disposition_build(value.terminal_build)
        except FormalTerminalDispositionBuildError as exc:
            raise FormalStreamingInputError(
                "streamed lifecycle terminal build no longer authenticates"
            ) from exc
    record = value.to_record()
    digest = sha256_bytes(canonical_json_bytes(record))
    topology = (
        id(value.scoring), id(value.shards), id(value.accepted_risk),
        id(value.formal_power), id(value.power_floor),
        id(value.economic_execution), id(value.economic_execution.definition),
        id(value.report_contract),
        id(value.terminal_package),
        id(value.terminal_build),
        id(value.source_view_partitions),
    )
    if (
        registered[1] != canonical_json_bytes(record)
        or registered[2] != topology
        or value.candidate_sha256 != digest
        or value.candidate_id != f"arv2-formal-streamed-input-{digest[:24]}"
        or (
            value.terminal_build is not None
            and (
                value.terminal_build.terminal_package is not value.terminal_package
                or value.terminal_build.terminal_census
                is not value.terminal_package.terminal_census
                or value.terminal_build.security_count
                != value.terminal_package.terminal_census.security_count
            )
        )
        or any(
            type(flag) is not bool or flag
            for flag in (
                value.caller_authored_scores_accepted,
                value.physical_shard_payloads_retained,
                value.qc_launch_available,
            )
        )
    ):
        raise FormalStreamingInputError(
            "streamed formal candidate changed after authentication"
        )
    return value


def _bind_streamed_formal_candidate_authority(
    *,
    candidate_builder: object,
    build_impl: object,
    lifecycle_impl: object,
    reviewed_lifecycle_impl: object,
    require_impl: object,
    register: object,
    current: object,
) -> tuple[object, object, object, object]:
    """Expose construction while keeping the candidate minter lexical."""

    def finish(value: StreamedFormalInputCandidate) -> StreamedFormalInputCandidate:
        return require_impl(value, _candidate_current=current)

    def build(
        *,
        scoring_builder: StreamedProductionScoringBuilder,
        authoritative_scoring_artifact: StreamedProductionScoringArtifact | None = None,
        accepted_risk: AcceptedRiskPairBinding,
        formal_power: FormalPowerCalibrationBinding,
        power_floor: PowerFloorBinding,
        economic_execution: FormalEconomicExecutionBinding,
        terminal_package: FormalTerminalDispositionPackage,
        benchmark_security_id: str,
        calculation_as_of_date: date,
        output_directory: Path,
    ) -> StreamedFormalInputCandidate:
        value = build_impl(
            scoring_builder=scoring_builder,
            authoritative_scoring_artifact=authoritative_scoring_artifact,
            accepted_risk=accepted_risk,
            formal_power=formal_power,
            power_floor=power_floor,
            economic_execution=economic_execution,
            terminal_package=terminal_package,
            benchmark_security_id=benchmark_security_id,
            calculation_as_of_date=calculation_as_of_date,
            output_directory=output_directory,
            _candidate_register=register,
            _candidate_builder=candidate_builder,
        )
        return finish(value)

    def build_lifecycle(
        *,
        scoring_builder: StreamedProductionScoringBuilder,
        authoritative_scoring_artifact: StreamedProductionScoringArtifact | None = None,
        accepted_risk: AcceptedRiskPairBinding,
        formal_power: FormalPowerCalibrationBinding,
        power_floor: PowerFloorBinding,
        economic_execution: FormalEconomicExecutionBinding,
        terminal_recorder: FormalTerminalDispositionRecorder,
        benchmark_security_id: str,
        calculation_as_of_date: date,
        output_directory: Path,
    ) -> StreamedFormalInputCandidate:
        value = lifecycle_impl(
            scoring_builder=scoring_builder,
            authoritative_scoring_artifact=authoritative_scoring_artifact,
            accepted_risk=accepted_risk,
            formal_power=formal_power,
            power_floor=power_floor,
            economic_execution=economic_execution,
            terminal_recorder=terminal_recorder,
            benchmark_security_id=benchmark_security_id,
            calculation_as_of_date=calculation_as_of_date,
            output_directory=output_directory,
            _candidate_register=register,
            _candidate_builder=candidate_builder,
        )
        return finish(value)

    def build_reviewed_lifecycle(
        *,
        scoring_builder: StreamedProductionScoringBuilder,
        authoritative_scoring_artifact: StreamedProductionScoringArtifact | None = None,
        accepted_risk: AcceptedRiskPairBinding,
        formal_power: FormalPowerCalibrationBinding,
        power_floor: PowerFloorBinding,
        economic_execution: FormalEconomicExecutionBinding,
        historical_bridge: historical_module.ReviewedHistoricalUniverseToPreopenBridge,
        terminal_output_directory: Path,
        benchmark_security_id: str,
        calculation_as_of_date: date,
        output_directory: Path,
    ) -> StreamedFormalInputCandidate:
        value = reviewed_lifecycle_impl(
            scoring_builder=scoring_builder,
            authoritative_scoring_artifact=authoritative_scoring_artifact,
            accepted_risk=accepted_risk,
            formal_power=formal_power,
            power_floor=power_floor,
            economic_execution=economic_execution,
            historical_bridge=historical_bridge,
            terminal_output_directory=terminal_output_directory,
            benchmark_security_id=benchmark_security_id,
            calculation_as_of_date=calculation_as_of_date,
            output_directory=output_directory,
            _candidate_register=register,
            _candidate_builder=candidate_builder,
            _lifecycle_builder=lifecycle_impl,
        )
        return finish(value)

    return build, build_lifecycle, build_reviewed_lifecycle, finish


(
    build_streamed_formal_input_candidate,
    build_lifecycle_streamed_formal_input_candidate,
    build_streamed_formal_input_candidate_from_reviewed_lifecycle,
    require_streamed_formal_input_candidate,
) = _bind_streamed_formal_candidate_authority(
    candidate_builder=_build_streamed_formal_input_candidate_impl,
    build_impl=_build_streamed_formal_input_candidate_public_impl,
    lifecycle_impl=_build_lifecycle_streamed_formal_input_candidate_impl,
    reviewed_lifecycle_impl=(
        _build_streamed_formal_input_candidate_from_reviewed_lifecycle_impl
    ),
    require_impl=_require_streamed_formal_input_candidate_impl,
    register=_candidate_authority_register,
    current=_candidate_authority_current,
)

del _bind_streamed_formal_candidate_authority
del _build_streamed_formal_input_candidate_impl
del _build_streamed_formal_input_candidate_public_impl
del _build_lifecycle_streamed_formal_input_candidate_impl
del _build_streamed_formal_input_candidate_from_reviewed_lifecycle_impl
del _require_streamed_formal_input_candidate_impl
del _candidate_authority_register
del _candidate_authority_current
del _make_streamed_formal_candidate_authority


def streamed_formal_contract_record(
    value: StreamedFormalInputCandidate,
) -> dict[str, object]:
    """Reauthenticate a candidate and reproduce its single contract row."""

    candidate = require_streamed_formal_input_candidate(value)
    return _build_streamed_formal_contract_record(
        scoring=candidate.scoring,
        accepted_risk=candidate.accepted_risk,
        formal_power=candidate.formal_power,
        power_floor=candidate.power_floor,
        economic_execution=candidate.economic_execution,
        report_contract=candidate.report_contract,
        terminal_package=candidate.terminal_package,
        preopen_acquisition_receipt=(
            candidate.shards.capacity.preopen_acquisition_receipt
        ),
        source_view_partitions=candidate.source_view_partitions,
        benchmark_security_id=candidate.benchmark_security_id,
        calculation_as_of_date=candidate.calculation_as_of_date,
    )


def _bind_stream_state_operations(
    *,
    begin_impl: object,
    require_impl: object,
    iter_impl: object,
    finish_impl: object,
    require_artifact_impl: object,
    initialize: object,
    is_current: object,
    acquire: object,
    require_lease: object,
    block: object,
    fold: object,
    external_finish: object,
    finalize_artifact: object,
    current_artifact: object,
    revoke: object,
    forget: object,
) -> tuple[object, object, object, object, object, object]:
    """Keep transition capabilities lexical to their one legal consumer.

    The compatibility registry remains inspectable for validation and testing,
    but neither its independent authority vault nor a lease-bearing transition
    primitive remains addressable through the module after this binder runs.
    """

    def begin(
        *,
        archive: PhysicalPreopenTerminalArchive,
        production_evidence_receipt: ProductionEvidenceAcquisitionReceipt,
        global_contract: GlobalBenchmarkContract,
    ) -> StreamedProductionScoringBuilder:
        return begin_impl(
            archive=archive,
            production_evidence_receipt=production_evidence_receipt,
            global_contract=global_contract,
            _vault_initialize=initialize,
            _vault_forget=forget,
        )

    def require(
        value: StreamedProductionScoringBuilder,
    ) -> StreamedProductionScoringBuilder:
        return require_impl(value, _vault_is_current=is_current)

    def iterate(
        builder: StreamedProductionScoringBuilder,
    ) -> Iterator[StreamedTestSessionBlock]:
        return iter_impl(
            builder,
            _vault_acquire=acquire,
            _vault_require_lease=require_lease,
            _vault_block=block,
            _vault_fold=fold,
            _vault_revoke=revoke,
        )

    def finish(
        builder: StreamedProductionScoringBuilder,
    ) -> StreamedProductionScoringArtifact:
        value = finish_impl(
            builder, _vault_finalize_artifact=finalize_artifact
        )
        return require_artifact_impl(
            value, _artifact_current=current_artifact
        )

    def require_artifact(
        value: StreamedProductionScoringArtifact,
    ) -> StreamedProductionScoringArtifact:
        return require_artifact_impl(
            value, _artifact_current=current_artifact
        )

    def run_power_calibration(
        builder: StreamedProductionScoringBuilder,
        consumer: object,
    ) -> object:
        """Run the sole non-fold consumer without exporting its lease.

        A caller can at most consume/revoke a fresh builder.  It cannot obtain
        a fold lease, submit a block or commitment, or reseal state.  The
        accepted-risk bridge remains responsible for authenticating the
        artifact it constructs inside ``consumer``.
        """

        if not callable(consumer):
            raise FormalStreamingInputError(
                "power-calibration stream consumer changed type"
            )
        state = _state(builder)
        if state.next_fold_index != 0 or state.active_fold or state.finalized:
            raise FormalStreamingInputError(
                "power calibration requires a fresh streaming scorer"
            )
        state, lease = acquire(builder, "accepted_risk_power_calibration")
        observed = dict(state.observed)
        completed = False
        try:
            result = consumer(state, observed)
            if (
                require_lease(
                    builder, lease, "accepted_risk_power_calibration"
                )
                is not state
            ):
                revoke(builder)
                raise FormalStreamingInputError(
                    "external streaming state changed"
                )
            external_finish(builder, lease, observed)
            completed = True
            return result
        finally:
            if not completed:
                revoke(builder)

    return begin, require, iterate, finish, run_power_calibration, require_artifact


(
    begin_streamed_production_scoring,
    require_streamed_production_scoring_builder,
    iter_streamed_production_scoring_fold,
    finish_streamed_production_scoring,
    _run_accepted_risk_power_calibration_stream,
    require_streamed_production_scoring_artifact,
) = _bind_stream_state_operations(
    begin_impl=_begin_streamed_production_scoring_impl,
    require_impl=_require_streamed_production_scoring_builder_impl,
    iter_impl=_iter_streamed_production_scoring_fold_impl,
    finish_impl=_finish_streamed_production_scoring_impl,
    require_artifact_impl=_require_streamed_production_scoring_artifact_impl,
    initialize=_stream_vault_initialize,
    is_current=_stream_vault_is_current,
    acquire=_stream_vault_acquire,
    require_lease=_stream_vault_require_lease,
    block=_stream_vault_block,
    fold=_stream_vault_fold,
    external_finish=_stream_vault_external_finish,
    finalize_artifact=_stream_vault_finalize_artifact,
    current_artifact=_stream_vault_current_artifact,
    revoke=_stream_vault_revoke,
    forget=_stream_vault_forget,
)

# The bound public operations above are the only retained references.  In
# particular, neither a lease-returning primitive nor a caller-driven state
# transition remains reachable through the module namespace.
del _bind_stream_state_operations
del _begin_streamed_production_scoring_impl
del _require_streamed_production_scoring_builder_impl
del _iter_streamed_production_scoring_fold_impl
del _finish_streamed_production_scoring_impl
del _require_streamed_production_scoring_artifact_impl
del _stream_vault_initialize
del _stream_vault_is_current
del _stream_vault_acquire
del _stream_vault_require_lease
del _stream_vault_block
del _stream_vault_fold
del _stream_vault_external_finish
del _stream_vault_finalize_artifact
del _stream_vault_current_artifact
del _stream_vault_revoke
del _stream_vault_forget
del _make_stream_state_vault
__all__ = (
    "FormalStreamingCapacityBinding",
    "FormalStreamingInputError",
    "FormalStreamingRefusalReason",
    "FormalStreamingRunRefusal",
    "PhysicalPreopenTerminalArchive",
    "PhysicalProductionEvidenceTerminalArchive",
    "PhysicalFormalShardArchive",
    "PhysicalFormalShardDescriptor",
    "PhysicalFormalShardPayload",
    "PhysicalTerminalSessionBlock",
    "STREAMING_CAPACITY_LIMIT_NAMES",
    "STREAMING_METHOD_ID",
    "STREAMED_FORMAL_CONTRACT_VARIANT",
    "StreamedControlModel",
    "StreamedFoldCommitment",
    "StreamedFormalInputCandidate",
    "StreamedProductionScoringArtifact",
    "StreamedProductionScoringBuilder",
    "StreamedTestSessionBlock",
    "begin_streamed_production_scoring",
    "build_lifecycle_streamed_formal_input_candidate",
    "build_streamed_formal_input_candidate",
    "build_streamed_formal_input_candidate_from_reviewed_lifecycle",
    "finish_streamed_production_scoring",
    "iter_formal_qc_compressed_shards",
    "iter_physical_preopen_terminal_sessions",
    "iter_physical_formal_shard_payloads",
    "iter_streamed_production_scoring_fold",
    "load_formal_streaming_capacity_binding",
    "load_physical_production_evidence_terminal_archive",
    "load_physical_preopen_terminal_archive",
    "render_formal_streaming_capacity_review_candidate",
    "require_formal_streaming_capacity_binding",
    "require_physical_production_evidence_terminal_archive",
    "require_physical_formal_shard_archive",
    "require_physical_preopen_terminal_archive",
    "require_streamed_formal_input_candidate",
    "require_streamed_production_scoring_artifact",
    "require_streamed_production_scoring_builder",
    "streamed_formal_contract_record",
)
