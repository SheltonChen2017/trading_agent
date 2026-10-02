"""Synthetic-only QC run-bundle contract for Analyst Revisions V2.

The contract is the first composition layer outside the outcome-free research
package.  It binds the reviewed structural ancestors and the files that would
be supplied to LEAN, but deliberately cannot bind production inputs or grant
upload, compile, launch, result, deployment, order, or trading authority.

Only caller-supplied *synthetic* file metadata is accepted in this milestone.
No file, provider, credential, QuantConnect service, or outcome is opened.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from types import MappingProxyType
from typing import Mapping


class QcRunContractError(ValueError):
    """A structural QC run candidate is malformed or falsely authoritative."""


SCHEMA = "arv2-qc-stock-event-study-run-candidate-v2"
STATUS = "synthetic_fixture_only_pending_independent_review_and_production_bindings"
AUTHORITY = "structure_only_no_source_outcome_qc_result_deployment_or_trading_authority"
EVALUATION_ID = "arv2-eval-stock-historical-qc-001"
ALGORITHM_ID = "arv2-qc-stock-event-study-core-v2"
CORE_RELATIVE_PATH = "research/analyst_revisions_v2_qc/event_study.py"
CORE_UPLOAD_NAME = "event_study.py"
HORIZONS = (1, 5, 20, 60)
PRIMARY_HORIZON = 20
TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID = (
    "arv2-terminal-payoff-benchmark-splice-v1"
)

_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")


@dataclasses.dataclass(frozen=True, slots=True)
class ParentArtifact:
    role: str
    relative_path: str
    artifact_sha256: str


def _expected_parent_artifacts() -> tuple[ParentArtifact, ...]:
    return (
        ParentArtifact(
            role="qc_first_plan",
            relative_path=(
                "research/analyst_revisions_v2/specs/arv2_qc_first.draft.json"
            ),
            artifact_sha256=(
                "8339238dd5ce32ed7b351aab2662fb408cc7d9a3c62ff89bf8b1d14f20acd081"
            ),
        ),
        ParentArtifact(
            role="stock_historical_successor_v2",
            relative_path=(
                "research/analyst_revisions_v2/specs/"
                "arv2_stock_historical_successor.structural.json"
            ),
            artifact_sha256=(
                "51718ee5ae278d1254e8efb01b2acdd9c6cbe51741dd72d5b5969c3b48576647"
            ),
        ),
        ParentArtifact(
            role="stock_walk_forward_folds",
            relative_path=(
                "research/analyst_revisions_v2/specs/"
                "arv2_stock_walk_forward_folds.structural.json"
            ),
            artifact_sha256=(
                "fecd984ad937fed57b860b15fdcb9cc994ff59ab62c3b72d5160ab62b342953c"
            ),
        ),
        ParentArtifact(
            role="post_pandemic_evaluation_supplement",
            relative_path=(
                "research/analyst_revisions_v2/specs/"
                "arv2_stock_post_pandemic_evaluation.structural.json"
            ),
            artifact_sha256=(
                "caa837b1e2797095dcb4cf5f30e21b72cc9d4254ff851a4fe5fb8779678e5e14"
            ),
        ),
        ParentArtifact(
            role="four_family_multiplicity",
            relative_path=(
                "research/analyst_revisions_v2/specs/"
                "arv2_four_family_multiplicity.structural.json"
            ),
            artifact_sha256=(
                "2e9f390ec54f01e6635b67972711c38212a5f853489e16c1de2a508212278648"
            ),
        ),
        ParentArtifact(
            role="power_calibration_protocol",
            relative_path=(
                "research/analyst_revisions_v2/specs/"
                "arv2_stock_power_calibration_protocol.structural.json"
            ),
            artifact_sha256=(
                "ff16117a258a1864438d11178a2b31af1b04a3f8b27d1f39c9c33552627f4a13"
            ),
        ),
    )


PARENT_ARTIFACTS = _expected_parent_artifacts()


@dataclasses.dataclass(frozen=True, slots=True)
class CodeFileBinding:
    """Caller-declared canonical-LF bytes of one future code component."""

    role: str
    relative_path: str
    upload_name: str
    byte_count: int
    sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticPartitionBinding:
    """Metadata for one synthetic fixture partition; never production data."""

    role: str
    partition_id: str
    schema: str
    byte_count: int
    row_count: int
    sha256: str
    synthetic_fixture: bool = True
    contains_licensed_rows: bool = False
    contains_real_outcomes: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class EvaluationWindow:
    role: str
    evaluation_segment_ids: tuple[str, ...]
    fold_ids: tuple[str, ...]
    claim: str
    pooled_with_primary: bool


def _expected_evaluation_windows() -> tuple[EvaluationWindow, ...]:
    return (
        EvaluationWindow(
            role="formal_primary",
            evaluation_segment_ids=tuple(
                f"arv2-wf-test-{year}" for year in range(2020, 2026)
            ),
            fold_ids=tuple(f"arv2-wf-test-{year}" for year in range(2020, 2026)),
            claim="development_stop_go_descriptive_not_confirmatory",
            pooled_with_primary=True,
        ),
        EvaluationWindow(
            role="owner_directed_post_pandemic_sensitivity",
            evaluation_segment_ids=tuple(
                f"arv2-wf-test-{year}" for year in range(2021, 2026)
            ),
            fold_ids=tuple(f"arv2-wf-test-{year}" for year in range(2021, 2026)),
            claim="descriptive_sensitivity_cannot_replace_or_rescue_primary",
            pooled_with_primary=False,
        ),
        EvaluationWindow(
            role="partial_2026_exploratory",
            evaluation_segment_ids=("arv2-partial-2026-exploratory",),
            fold_ids=(),
            claim=(
                "separate_fixed_cutoff_exploratory_geometry_never_a_complete_fold_"
                "and_never_pooled"
            ),
            pooled_with_primary=False,
        ),
    )


EVALUATION_WINDOWS = _expected_evaluation_windows()


def _require_static_contract() -> tuple[
    tuple[ParentArtifact, ...], tuple[EvaluationWindow, ...]
]:
    """Refuse mutation of exported frozen records; return fresh literal values."""

    scalar_identities = (
        (SCHEMA, "arv2-qc-stock-event-study-run-candidate-v2"),
        (
            STATUS,
            "synthetic_fixture_only_pending_independent_review_and_production_bindings",
        ),
        (
            AUTHORITY,
            "structure_only_no_source_outcome_qc_result_deployment_or_"
            "trading_authority",
        ),
        (EVALUATION_ID, "arv2-eval-stock-historical-qc-001"),
        (ALGORITHM_ID, "arv2-qc-stock-event-study-core-v2"),
        (CORE_RELATIVE_PATH, "research/analyst_revisions_v2_qc/event_study.py"),
        (CORE_UPLOAD_NAME, "event_study.py"),
    )
    if any(
        type(actual) is not str or actual != expected
        for actual, expected in scalar_identities
    ):
        raise QcRunContractError("static run-contract identity changed")
    if (
        type(HORIZONS) is not tuple
        or HORIZONS != (1, 5, 20, 60)
        or any(type(value) is not int for value in HORIZONS)
        or type(PRIMARY_HORIZON) is not int
        or PRIMARY_HORIZON != 20
    ):
        raise QcRunContractError("reviewed horizon contract changed")
    if (
        type(TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID) is not str
        or TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID
        != "arv2-terminal-payoff-benchmark-splice-v1"
    ):
        raise QcRunContractError("terminal-payoff reinvestment policy changed")

    expected_parents = _expected_parent_artifacts()
    if type(PARENT_ARTIFACTS) is not tuple or len(PARENT_ARTIFACTS) != len(
        expected_parents
    ):
        raise QcRunContractError("parent artifact inventory changed")
    for actual, expected in zip(PARENT_ARTIFACTS, expected_parents):
        if type(actual) is not ParentArtifact or any(
            type(value) is not str
            for value in (
                actual.role,
                actual.relative_path,
                actual.artifact_sha256,
            )
        ):
            raise QcRunContractError("parent artifact identity type changed")
        if (
            actual.role,
            actual.relative_path,
            actual.artifact_sha256,
        ) != (
            expected.role,
            expected.relative_path,
            expected.artifact_sha256,
        ):
            raise QcRunContractError("parent artifact identity changed")

    expected_windows = _expected_evaluation_windows()
    if type(EVALUATION_WINDOWS) is not tuple or len(EVALUATION_WINDOWS) != len(
        expected_windows
    ):
        raise QcRunContractError("evaluation-window inventory changed")
    for actual, expected in zip(EVALUATION_WINDOWS, expected_windows):
        if (
            type(actual) is not EvaluationWindow
            or type(actual.role) is not str
            or type(actual.evaluation_segment_ids) is not tuple
            or any(type(value) is not str for value in actual.evaluation_segment_ids)
            or type(actual.fold_ids) is not tuple
            or any(type(value) is not str for value in actual.fold_ids)
            or type(actual.claim) is not str
            or type(actual.pooled_with_primary) is not bool
        ):
            raise QcRunContractError("evaluation-window identity type changed")
        if (
            actual.role,
            actual.evaluation_segment_ids,
            actual.fold_ids,
            actual.claim,
            actual.pooled_with_primary,
        ) != (
            expected.role,
            expected.evaluation_segment_ids,
            expected.fold_ids,
            expected.claim,
            expected.pooled_with_primary,
        ):
            raise QcRunContractError("evaluation-window identity changed")
    return expected_parents, expected_windows


_EXTERNAL_BINDING_NAMES = (
    "reviewed_spec_hash",
    "qc_first_plan_hash",
    "review_commit",
    "counter_review_commit",
    "data_entitlement_audit_id",
    "vendor_to_qc_processing_rights_receipt_id",
    "owner_source_capture_authority_id",
    "immutable_snapshot_id",
    "raw_inventory_sha256",
    "reviewed_source_ontology_identity_contracts",
    "owner_normalization_authority_id",
    "dataset_id",
    "normalization_receipt_id",
    "owner_qc_upload_authority_id",
    "qc_project_id",
    "custom_data_sha256",
    "upload_receipt_id",
    "algorithm_sha256",
    "config_sha256",
    "owner_qc_compile_authority_id",
    "qc_compile_id",
    "compile_receipt_id",
    "authority_phase_lineage_sha256",
    "complete_reviewed_v2_spec_and_all_definition_hashes",
    "qc_plan_sha256",
    "owner_backtest_launch_authority_id",
    "external_evaluation_authority_id",
    "atomic_evaluation_receipt_id",
    "evaluation_claimed_at",
    "owner_qc_launch_authority_id",
    "qc_backtest_id_or_ambiguous_submission_lock",
    "code_identity",
    "deterministic_backtest_name",
    "lean_engine_version",
    "qc_data_version_disclosures",
    "period",
    "controls",
    "costs",
    "pre_outcome_power_plan_sha256",
    "production_input_manifest_id",
    "production_input_manifest_sha256",
    "production_truth_approval_id",
    "numeric_power_receipt_id",
    "numeric_power_receipt_sha256",
    "stock_power_successor_v3_id",
    "stock_power_successor_v3_sha256",
    "deterministic_project_name",
)

_CAPABILITY_NAMES = (
    "production_source_access",
    "licensed_input_read",
    "real_outcome_access",
    "qc_object_store_write",
    "qc_upload",
    "qc_compile",
    "qc_launch",
    "result_access",
    "result_disposition",
    "deployment",
    "orders",
    "trading",
)

_ALLOWED_CODE_ROLES = frozenset({"event_study_core"})
_ALLOWED_PARTITION_ROLES = frozenset(
    {
        "session_axis",
        "decision_rows",
        "security_open_values",
        "benchmark_open_values",
        "security_lifecycle_coverages",
        "terminal_requirements",
        "terminal_shareholder_payoffs",
    }
)
PARTITION_SCHEMAS = MappingProxyType(
    {
        role: f"arv2-synthetic-{role}-v1"
        for role in _ALLOWED_PARTITION_ROLES
    }
)


def _is_safe_relative_path(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and not value.startswith("/")
        and not value.endswith("/")
        and all(part not in {"", ".", ".."} for part in value.split("/"))
        and _SAFE_NAME.fullmatch(value) is not None
    )


def _is_safe_upload_name(value: object) -> bool:
    return _is_safe_relative_path(value) and "/" not in value


def _require_sha256(value: object, name: str) -> None:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise QcRunContractError(f"{name} must be a lowercase SHA-256")


def canonical_lf_python_source_bytes(value: bytes) -> bytes:
    """Normalize UTF-8 Python source for cross-checkout declaration identity."""

    if type(value) is not bytes:
        raise QcRunContractError("Python source must be exact bytes")
    if value.startswith(b"\xef\xbb\xbf"):
        raise QcRunContractError("Python source must not contain a UTF-8 BOM")
    normalized = value.replace(b"\r\n", b"\n")
    if b"\r" in normalized:
        raise QcRunContractError("Python source contains a bare carriage return")
    try:
        normalized.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise QcRunContractError("Python source must be strict UTF-8") from exc
    return normalized


def _validate_code_file(value: CodeFileBinding) -> None:
    if type(value) is not CodeFileBinding:
        raise QcRunContractError("code files must be exact CodeFileBinding values")
    if type(value.role) is not str or value.role not in _ALLOWED_CODE_ROLES:
        raise QcRunContractError("code file role is unknown")
    if not _is_safe_relative_path(value.relative_path) or not _is_safe_upload_name(
        value.upload_name
    ):
        raise QcRunContractError("code file path or upload name is unsafe")
    if value.upload_name == "main.py":
        raise QcRunContractError("this milestone has no LEAN main.py entry")
    if (
        value.role == "event_study_core"
        and (
            value.relative_path != CORE_RELATIVE_PATH
            or value.upload_name != CORE_UPLOAD_NAME
        )
    ):
        raise QcRunContractError("event-study core path identity changed")
    if type(value.byte_count) is not int or value.byte_count <= 0:
        raise QcRunContractError("code file byte_count must be a positive integer")
    _require_sha256(value.sha256, "code file sha256")


def _validate_partition(value: SyntheticPartitionBinding) -> None:
    if type(value) is not SyntheticPartitionBinding:
        raise QcRunContractError(
            "partitions must be exact SyntheticPartitionBinding values"
        )
    if type(value.role) is not str or value.role not in _ALLOWED_PARTITION_ROLES:
        raise QcRunContractError("synthetic partition role is unknown")
    if not _is_safe_relative_path(value.partition_id) or not _is_safe_relative_path(
        value.schema
    ):
        raise QcRunContractError("synthetic partition identity is unsafe")
    if type(value.byte_count) is not int or value.byte_count < 0:
        raise QcRunContractError("partition byte_count must be a nonnegative integer")
    if type(value.row_count) is not int or value.row_count < 0:
        raise QcRunContractError("partition row_count must be a nonnegative integer")
    _require_sha256(value.sha256, "partition sha256")
    if value.schema != PARTITION_SCHEMAS[value.role]:
        raise QcRunContractError("synthetic partition schema is not role-exact")
    if (
        value.synthetic_fixture is not True
        or value.contains_licensed_rows is not False
        or value.contains_real_outcomes is not False
    ):
        raise QcRunContractError("only outcome-free synthetic fixture metadata is allowed")


def _binding_document(value: object) -> dict[str, object]:
    return {
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(value)
    }


def _candidate_document(
    *,
    code_files: tuple[CodeFileBinding, ...],
    partitions: tuple[SyntheticPartitionBinding, ...],
) -> dict[str, object]:
    parent_artifacts, evaluation_windows = _require_static_contract()
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "candidate_id": None,
        "candidate_hash": None,
        "algorithm_id": ALGORITHM_ID,
        "evaluation_id": EVALUATION_ID,
        "horizons_sessions": list(HORIZONS),
        "primary_horizon_sessions": PRIMARY_HORIZON,
        "parent_artifacts": [_binding_document(item) for item in parent_artifacts],
        "code_files": [_binding_document(item) for item in code_files],
        "synthetic_partitions": [_binding_document(item) for item in partitions],
        "evaluation_windows": [
            {
                **_binding_document(item),
                "evaluation_segment_ids": list(item.evaluation_segment_ids),
                "fold_ids": list(item.fold_ids),
            }
            for item in evaluation_windows
        ],
        "input_policy": {
            "transport": "future_immutable_qc_custom_data_binding",
            "vendor_api_calls_inside_algorithm": False,
            "current_ticker_identity_allowed": False,
            "permanent_security_and_listing_identity_required": True,
            "complete_decision_and_successor_lifecycle_coverage_through": (
                "2026-08-28"
            ),
            "terminal_payoff_source_required_when_inventory_marks_terminal": True,
            "qc_delisting_price_is_terminal_shareholder_payoff": False,
            "terminal_payoff_reinvestment": {
                "policy_id": TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID,
                "applies_to": ["bankruptcy", "cash_merger", "delisting"],
                "reinvestment_session": (
                    "terminal_valuation_session_open_with_proven_economic_availability"
                ),
                "horizon_security_value": (
                    "terminal_payoff_times_spy_horizon_open_divided_by_"
                    "spy_reinvestment_open"
                ),
                "post_terminal_abnormal_exposure": "zero",
                "scheduled_horizon_is_preserved": True,
                "stock_and_mixed_mergers_follow_successor_to_horizon": True,
                "terminal_date_alone_proves_economic_availability": False,
            },
            "row_or_named_refusal_for_every_decision_horizon": True,
        },
        "result_policy": {
            "algorithm_places_orders": False,
            "security_level_prices_or_returns_exported": False,
            "aggregate_reports_only_after_separate_result_authority": True,
            "formal_primary_can_be_replaced_or_rescued_by_sensitivity": False,
            "partial_2026_can_be_pooled": False,
            "dispositions": ["PASS", "FAIL", "INCONCLUSIVE", "INVALID-DATA"],
        },
        "execution_policy": {
            "project_name_pattern": "[number]. ARV2_STOCK_EVENT_STUDY - [YYYYMMDD]",
            "one_frozen_run_computes_primary_and_sensitivities": True,
            "lean_algorithm_entry_present": False,
            "qc_compile_candidate": False,
            "atomic_claim_required_before_backtests_create": True,
            "ambiguous_submission_blocks_retry_until_reconciled": True,
            "generic_stage0_runner_allowed": False,
            "candidate_scope": (
                "partial_synthetic_candidate_requires_a_new_reviewed_"
                "production_run_schema"
            ),
            "code_binding_recipe": "strict_utf8_without_bom_canonical_lf_bytes",
            "candidate_hash_authenticates_loaded_code": False,
        },
        "external_bindings": {name: None for name in _EXTERNAL_BINDING_NAMES},
        "capabilities": {name: False for name in _CAPABILITY_NAMES},
    }


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise QcRunContractError("run candidate is not canonical JSON") from exc


def _identity_document(document: Mapping[str, object]) -> dict[str, object]:
    value = dict(document)
    value["candidate_id"] = None
    value["candidate_hash"] = None
    digest = hashlib.sha256(_canonical_bytes(value)).hexdigest()
    value["candidate_hash"] = digest
    value["candidate_id"] = f"arv2-qc-stock-run-candidate-{digest[:16]}"
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticQcRunCandidate:
    candidate_id: str
    candidate_hash: str
    code_files: tuple[CodeFileBinding, ...]
    synthetic_partitions: tuple[SyntheticPartitionBinding, ...]
    external_bindings: tuple[tuple[str, None], ...]
    capabilities: tuple[tuple[str, bool], ...]
    _canonical_document: bytes = dataclasses.field(repr=False)

    @property
    def upload_available(self) -> bool:
        return False

    @property
    def execution_code_authenticated(self) -> bool:
        return False

    @property
    def compile_available(self) -> bool:
        return False

    @property
    def launch_available(self) -> bool:
        return False

    @property
    def result_access_available(self) -> bool:
        return False

    @property
    def deployment_available(self) -> bool:
        return False

    @property
    def orders_available(self) -> bool:
        return False

    @property
    def trading_available(self) -> bool:
        return False


def build_synthetic_qc_run_candidate(
    *,
    code_files: tuple[CodeFileBinding, ...],
    synthetic_partitions: tuple[SyntheticPartitionBinding, ...],
) -> SyntheticQcRunCandidate:
    """Identify a caller-declared fixture candidate without reading any bytes."""

    # Authenticate exported identities before any caller-owned binding is
    # compared with them. The exact-type checks in this preflight refuse a
    # hostile ``str`` subclass without dispatching its comparison methods.
    _require_static_contract()
    if type(code_files) is not tuple or not code_files:
        raise QcRunContractError("code_files must be a nonempty tuple")
    if type(synthetic_partitions) is not tuple or not synthetic_partitions:
        raise QcRunContractError("synthetic_partitions must be a nonempty tuple")
    for item in code_files:
        _validate_code_file(item)
    for item in synthetic_partitions:
        _validate_partition(item)

    # Reconstruct exact values so later mutation of a caller-owned frozen
    # dataclass through object.__setattr__ cannot alter this candidate.
    copied_code = tuple(
        CodeFileBinding(
            role=item.role,
            relative_path=item.relative_path,
            upload_name=item.upload_name,
            byte_count=item.byte_count,
            sha256=item.sha256,
        )
        for item in code_files
    )
    copied_partitions = tuple(
        SyntheticPartitionBinding(
            role=item.role,
            partition_id=item.partition_id,
            schema=item.schema,
            byte_count=item.byte_count,
            row_count=item.row_count,
            sha256=item.sha256,
            synthetic_fixture=item.synthetic_fixture,
            contains_licensed_rows=item.contains_licensed_rows,
            contains_real_outcomes=item.contains_real_outcomes,
        )
        for item in synthetic_partitions
    )
    ordered_code = tuple(
        sorted(copied_code, key=lambda item: (item.upload_name, item.relative_path))
    )
    ordered_partitions = tuple(
        sorted(
            copied_partitions,
            key=lambda item: (item.role, item.partition_id),
        )
    )
    if len({item.relative_path for item in ordered_code}) != len(ordered_code):
        raise QcRunContractError("code relative paths must be unique")
    if len({item.upload_name for item in ordered_code}) != len(ordered_code):
        raise QcRunContractError("code upload names must be unique")
    if len({item.partition_id for item in ordered_partitions}) != len(
        ordered_partitions
    ):
        raise QcRunContractError("synthetic partition ids must be unique")
    if len(ordered_code) != 1 or ordered_code[0].role != "event_study_core":
        raise QcRunContractError("exactly one event_study_core file is required")
    present_roles = {item.role for item in ordered_partitions}
    required_roles = {
        "session_axis",
        "decision_rows",
        "security_open_values",
        "benchmark_open_values",
        "security_lifecycle_coverages",
        "terminal_requirements",
        "terminal_shareholder_payoffs",
    }
    if (
        present_roles != required_roles
        or len(ordered_partitions) != len(required_roles)
    ):
        raise QcRunContractError("synthetic partition roles must be complete and exact")

    document = _identity_document(
        _candidate_document(code_files=ordered_code, partitions=ordered_partitions)
    )
    canonical_document = _canonical_bytes(document)
    return SyntheticQcRunCandidate(
        candidate_id=str(document["candidate_id"]),
        candidate_hash=str(document["candidate_hash"]),
        code_files=ordered_code,
        synthetic_partitions=ordered_partitions,
        external_bindings=tuple((name, None) for name in _EXTERNAL_BINDING_NAMES),
        capabilities=tuple((name, False) for name in _CAPABILITY_NAMES),
        _canonical_document=canonical_document,
    )


def require_synthetic_qc_run_candidate(
    candidate: SyntheticQcRunCandidate,
) -> SyntheticQcRunCandidate:
    """Revalidate exact immutable candidate content and reject changed state."""

    if type(candidate) is not SyntheticQcRunCandidate:
        raise QcRunContractError("run candidate has not been built by this contract")
    if type(candidate.candidate_id) is not str or type(candidate.candidate_hash) is not str:
        raise QcRunContractError("run candidate identity type changed")
    if _HEX_64.fullmatch(candidate.candidate_hash) is None:
        raise QcRunContractError("run candidate hash changed")
    if candidate.candidate_id != (
        f"arv2-qc-stock-run-candidate-{candidate.candidate_hash[:16]}"
    ):
        raise QcRunContractError("run candidate id changed")
    if (
        type(candidate.code_files) is not tuple
        or type(candidate.synthetic_partitions) is not tuple
        or type(candidate._canonical_document) is not bytes
    ):
        raise QcRunContractError("run candidate container type changed")
    if type(candidate.external_bindings) is not tuple or any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or item[1] is not None
        for item in candidate.external_bindings
    ):
        raise QcRunContractError("run candidate acquired an external binding")
    if candidate.external_bindings != tuple(
        (name, None) for name in _EXTERNAL_BINDING_NAMES
    ):
        raise QcRunContractError("run candidate external-binding inventory changed")
    if type(candidate.capabilities) is not tuple or any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or item[1] is not False
        for item in candidate.capabilities
    ):
        raise QcRunContractError("run candidate acquired an action capability")
    if candidate.capabilities != tuple(
        (name, False) for name in _CAPABILITY_NAMES
    ):
        raise QcRunContractError("run candidate capability inventory changed")

    rebuilt = build_synthetic_qc_run_candidate(
        code_files=candidate.code_files,
        synthetic_partitions=candidate.synthetic_partitions,
    )
    if (
        rebuilt.candidate_id != candidate.candidate_id
        or rebuilt.candidate_hash != candidate.candidate_hash
        or rebuilt.code_files != candidate.code_files
        or rebuilt.synthetic_partitions != candidate.synthetic_partitions
        or rebuilt._canonical_document != candidate._canonical_document
    ):
        raise QcRunContractError("run candidate changed after construction")
    return candidate


def commit_identity_shape_is_valid(value: object) -> bool:
    """Shape helper for a future reviewed run instance; grants no authority."""

    return type(value) is str and _HEX_40.fullmatch(value) is not None
