"""Synthetic-only schema for a future ARV2 QuantConnect global input.

This module freezes the metadata layout that will describe the seven immutable
partitions consumed by the reviewed event-study core. It does not open or
parse a partition, authenticate production truth or rights, contact
QuantConnect, execute an event study, or expose a result or trading surface.

The sole manifest builder derives every descriptor from an already validated
``SyntheticQcRunCandidate``. The in-memory byte loader accepts only that
builder's canonical synthetic metadata. Production admission, physical
Object Store keys, a LEAN adapter, and every external action remain later,
separately reviewed milestones.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from datetime import date
from types import MappingProxyType

from .event_study import (
    BENCHMARK_LISTING_ID,
    BENCHMARK_SECURITY_ID,
    BENCHMARK_TICKER,
    BENCHMARK_TOTAL_RETURN_SERIES_ID,
    REVIEWED_AXIS_END,
    REVIEWED_AXIS_SESSION_COUNT,
    REVIEWED_AXIS_SHA256,
    REVIEWED_AXIS_START,
    SYNTHETIC_LIFECYCLE_SOURCE,
    SYNTHETIC_OPEN_SOURCE,
    SYNTHETIC_TERMINAL_SOURCE,
    SYNTHETIC_TERMINAL_VALUE_BASIS,
    SYNTHETIC_TOTAL_RETURN_VALUE_BASIS,
)
from .run_contract import (
    ALGORITHM_ID,
    CORE_RELATIVE_PATH,
    CORE_UPLOAD_NAME,
    EVALUATION_ID,
    HORIZONS,
    PARTITION_SCHEMAS,
    PRIMARY_HORIZON,
    SCHEMA as RUN_CANDIDATE_SCHEMA,
    TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID,
    CodeFileBinding,
    QcRunContractError,
    SyntheticPartitionBinding,
    SyntheticQcRunCandidate,
    build_synthetic_qc_run_candidate,
    require_synthetic_qc_run_candidate,
)


class QcGlobalInputSchemaError(ValueError):
    """The schema or a synthetic global-input manifest is malformed."""


SCHEMA = "arv2-qc-global-input-schema-v1"
SCHEMA_ID = "arv2-qc-global-input-schema-d56e2b5ec26d4068"
SCHEMA_SHA256 = (
    "d56e2b5ec26d4068876bff3b549c1f9c7a83014c1372403d7bf33e511bd8e640"
)
SCHEMA_ARTIFACT_SHA256 = (
    "0f60cb3badec36fa9589b220cf91aee43a965865244c7c2726d16da71f6ae3d2"
)
STATUS = "synthetic_fixture_only_production_shaped_schema_not_production_truth"
AUTHORITY = (
    "schema_and_synthetic_metadata_only_no_input_qc_outcome_result_or_"
    "trading_authority"
)
ENCODING = "canonical_tagged_jsonl_strict_utf8_lf-v1"
RUN_CONTRACT_SOURCE_SHA256 = (
    "a72aa500a5c2d2fe68cfe9a00e6531a8c1a241e212cb8df8e2a7a56dba3d77d5"
)
RUN_CONTRACT_SOURCE_BYTE_COUNT = 28_825
EVENT_STUDY_SOURCE_SHA256 = (
    "0f1e6f69c4bde56bb42a49d24d42b0a27cb2417d3c7bf8f1ea196e15fa0628fe"
)
EVENT_STUDY_SOURCE_BYTE_COUNT = 109_226
SESSION_AXIS_PARTITION_SHA256 = (
    "a4821282efee2048c31ea191fb3bc1c7cd1d854095b385a01cac2bcf69ca1de4"
)
SESSION_AXIS_PARTITION_BYTE_COUNT = 161_445
MAX_SYNTHETIC_MANIFEST_BYTES = 1_048_576
MAX_SAFE_ID_CHARS = 512
PARTITION_BINDING_HASH_DOMAIN = (
    "arv2-qc-global-input-partition-binding-v1"
)
PARTITION_IMMUTABLE_ID_RECIPE = (
    "synthetic-arv2-global-input-<hyphenated-role>-<binding_sha256>"
)

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,511}\Z")
_MAPPING_PROXY_TYPE = type(MappingProxyType({}))
_PINNED_PARTITION_SCHEMAS = PARTITION_SCHEMAS

ROLE_ORDER = (
    "session_axis",
    "decision_rows",
    "security_open_values",
    "benchmark_open_values",
    "security_lifecycle_coverages",
    "terminal_requirements",
    "terminal_shareholder_payoffs",
)


@dataclasses.dataclass(frozen=True, slots=True)
class RowContract:
    role: str
    row_schema: str
    record_type: str
    root_envelope: str
    fields: tuple[str, ...]
    wire_types: tuple[str, ...]
    canonical_order: tuple[str, ...]
    timing_semantics: str
    identity_semantics: str
    value_semantics: str


def _expected_row_contracts() -> tuple[RowContract, ...]:
    return (
        RowContract(
            role="session_axis",
            row_schema="arv2-qc-global-input-session-v1",
            record_type="session_axis_row",
            root_envelope="$object",
            fields=("session",),
            wire_types=("date_tag",),
            canonical_order=("session",),
            timing_semantics=(
                "complete_reviewed_xnys_reference_axis_not_a_decision_fact"
            ),
            identity_semantics="one_unique_strictly_increasing_session",
            value_semantics="canonical_iso_date_inside_the_reviewed_axis",
        ),
        RowContract(
            role="decision_rows",
            row_schema="arv2-qc-global-input-decision-row-v1",
            record_type="DecisionRow",
            root_envelope="$dataclass:DecisionRow/$fields",
            fields=(
                "row_id",
                "decision_session",
                "security_id",
                "listing_id",
                "historical_ticker",
                "evaluation_segment_id",
                "fold_id",
                "firm_specific_score",
                "global_score",
                "common_event_component_id",
                "input_row_sha256",
            ),
            wire_types=(
                "string",
                "date_tag",
                "string",
                "string",
                "string",
                "string",
                "optional_string",
                "decimal_tag",
                "decimal_tag",
                "string",
                "lowercase_sha256_string",
            ),
            canonical_order=(
                "decision_session",
                "security_id",
                "listing_id",
                "row_id",
            ),
            timing_semantics=(
                "score_is_eligible_only_when_all_upstream_facts_were_available_"
                "by_the_decision_session_open;the_row_does_not_self_prove_pit"
            ),
            identity_semantics=(
                "permanent_security_and_listing_identity_with_historical_ticker;"
                "current_ticker_resolution_forbidden"
            ),
            value_semantics=(
                "both_values_are_signed_final_control_adjusted_held_out_scores;"
                "firm_specific_uses_the_firm_ontology_arm;global_uses_the_39_"
                "alias_arm;each_arm_is_fit_separately_on_identical_training_and_"
                "held_out_censuses_with_shared_controls;bullish_and_bearish_"
                "transforms_occur_only_inside_the_accepted_core"
            ),
        ),
        RowContract(
            role="security_open_values",
            row_schema="arv2-qc-global-input-security-open-value-v1",
            record_type="SecurityOpenValue",
            root_envelope="$dataclass:SecurityOpenValue/$fields",
            fields=(
                "session",
                "security_id",
                "listing_id",
                "historical_ticker",
                "total_return_open_value",
                "total_return_series_id",
                "value_basis",
                "source_role",
                "source_sha256",
            ),
            wire_types=(
                "date_tag",
                "string",
                "string",
                "string",
                "decimal_tag",
                "string",
                "string",
                "string",
                "lowercase_sha256_string",
            ),
            canonical_order=(
                "session",
                "security_id",
                "listing_id",
                "total_return_series_id",
            ),
            timing_semantics=(
                "session_open_outcome_valuation;access_requires_later_outcome_"
                "authority"
            ),
            identity_semantics=(
                "listing_to_security_ticker_and_security_to_total_return_series_"
                "must_be_functional"
            ),
            value_semantics=(
                "split_distribution_adjusted_total_return_index_same_vintage"
            ),
        ),
        RowContract(
            role="benchmark_open_values",
            row_schema="arv2-qc-global-input-benchmark-open-value-v1",
            record_type="BenchmarkOpenValue",
            root_envelope="$dataclass:BenchmarkOpenValue/$fields",
            fields=(
                "session",
                "security_id",
                "listing_id",
                "historical_ticker",
                "total_return_open_value",
                "total_return_series_id",
                "value_basis",
                "source_role",
                "source_sha256",
            ),
            wire_types=(
                "date_tag",
                "string",
                "string",
                "string",
                "decimal_tag",
                "string",
                "string",
                "string",
                "lowercase_sha256_string",
            ),
            canonical_order=("session",),
            timing_semantics=(
                "matched_spy_session_open_outcome_valuation;access_requires_"
                "later_outcome_authority"
            ),
            identity_semantics="exact_reserved_spy_security_listing_ticker_and_series",
            value_semantics=(
                "same_vintage_total_return_index_for_entry_valuation_and_exit"
            ),
        ),
        RowContract(
            role="security_lifecycle_coverages",
            row_schema="arv2-qc-global-input-security-lifecycle-coverage-v1",
            record_type="SecurityLifecycleCoverage",
            root_envelope="$dataclass:SecurityLifecycleCoverage/$fields",
            fields=(
                "security_id",
                "observed_through_session",
                "terminal_lifecycle",
                "source_role",
                "source_sha256",
            ),
            wire_types=(
                "string",
                "date_tag",
                "terminal_lifecycle_dataclass_or_null",
                "string",
                "lowercase_sha256_string",
            ),
            canonical_order=("security_id",),
            timing_semantics=(
                "complete_ex_post_inventory_through_the_reviewed_cutoff_not_a_"
                "decision_time_fact"
            ),
            identity_semantics=(
                "every_decision_security_and_recursive_successor_exactly_once"
            ),
            value_semantics=(
                "active_or_one_terminal_lifecycle_with_exact_successor_lineage"
            ),
        ),
        RowContract(
            role="terminal_requirements",
            row_schema="arv2-qc-global-input-terminal-requirement-v1",
            record_type="TerminalRequirement",
            root_envelope="$dataclass:TerminalRequirement/$fields",
            fields=(
                "decision_row_id",
                "security_id",
                "terminal_listing_id",
                "terminal_historical_ticker",
                "terminal_session",
                "requirement_id",
                "event_kind",
                "successor_security_id",
                "successor_listing_id",
                "successor_historical_ticker",
                "total_return_series_id",
            ),
            wire_types=(
                "string",
                "string",
                "string",
                "string",
                "date_tag",
                "string",
                "string",
                "optional_string",
                "optional_string",
                "optional_string",
                "string",
            ),
            canonical_order=(
                "decision_row_id",
                "terminal_session",
                "requirement_id",
            ),
            timing_semantics=(
                "ex_post_requirement_inventory;corporate_action_date_alone_does_"
                "not_prove_payoff_availability"
            ),
            identity_semantics=(
                "exact_decision_security_listing_ticker_event_successor_and_"
                "series_lineage"
            ),
            value_semantics=(
                "missing_or_ambiguous_terminal_evidence_requires_named_refusal"
            ),
        ),
        RowContract(
            role="terminal_shareholder_payoffs",
            row_schema="arv2-qc-global-input-terminal-shareholder-payoff-v1",
            record_type="TerminalShareholderPayoff",
            root_envelope="$dataclass:TerminalShareholderPayoff/$fields",
            fields=(
                "decision_row_id",
                "security_id",
                "terminal_listing_id",
                "terminal_historical_ticker",
                "terminal_session",
                "valuation_session",
                "valuation_security_id",
                "valuation_listing_id",
                "valuation_historical_ticker",
                "terminal_total_return_index_value",
                "total_return_series_id",
                "value_basis",
                "requirement_id",
                "event_kind",
                "successor_security_id",
                "successor_listing_id",
                "successor_historical_ticker",
                "source_role",
                "source_sha256",
            ),
            wire_types=(
                "string",
                "string",
                "string",
                "string",
                "date_tag",
                "date_tag",
                "string",
                "string",
                "string",
                "decimal_tag",
                "string",
                "string",
                "string",
                "string",
                "optional_string",
                "optional_string",
                "optional_string",
                "string",
                "lowercase_sha256_string",
            ),
            canonical_order=(
                "decision_row_id",
                "valuation_session",
                "requirement_id",
            ),
            timing_semantics=(
                "valuation_session_requires_proven_economic_availability;"
                "terminal_date_alone_is_insufficient"
            ),
            identity_semantics=(
                "must_equal_the_complete_terminal_requirement_lineage"
            ),
            value_semantics=(
                "total_shareholder_payoff_only;qc_delisting_price_is_prohibited"
            ),
        ),
    )


ROW_CONTRACTS = _expected_row_contracts()

TERMINAL_LIFECYCLE_FIELDS = (
    "security_id",
    "terminal_listing_id",
    "terminal_historical_ticker",
    "terminal_session",
    "event_kind",
    "successor_security_id",
    "successor_listing_id",
    "successor_historical_ticker",
    "total_return_series_id",
)

TERMINAL_LIFECYCLE_WIRE_TYPES = (
    "string",
    "string",
    "string",
    "date_tag",
    "string",
    "optional_string",
    "optional_string",
    "optional_string",
    "string",
)

TERMINAL_EVENT_KINDS = (
    "delisting",
    "bankruptcy",
    "cash_merger",
    "stock_merger",
    "mixed_merger",
)

_EXTERNAL_BINDING_NAMES = (
    "schema_review_commit",
    "schema_counter_review_commit",
    "data_entitlement_audit_id",
    "vendor_to_qc_processing_rights_receipt_id",
    "production_truth_approval_id",
    "production_global_input_manifest_id",
    "production_global_input_manifest_sha256",
    "owner_production_input_read_authority_id",
    "owner_real_outcome_read_authority_id",
    "owner_qc_object_store_write_authority_id",
    "owner_qc_project_create_authority_id",
    "qc_project_id",
    "qc_object_store_manifest_key",
    "owner_qc_upload_authority_id",
    "qc_upload_receipt_id",
    "owner_qc_compile_authority_id",
    "qc_compile_id",
    "compile_receipt_id",
    "owner_backtest_launch_authority_id",
    "external_evaluation_authority_id",
    "atomic_evaluation_receipt_id",
    "qc_backtest_id_or_ambiguous_submission_lock",
    "result_access_authority_id",
    "result_disposition_authority_id",
    "deployment_authority_id",
    "order_authority_id",
    "trading_authority_id",
)

_CAPABILITY_NAMES = (
    "filesystem_read",
    "environment_read",
    "provider_access",
    "licensed_input_read",
    "production_input_read",
    "real_outcome_access",
    "qc_object_store_read",
    "qc_object_store_write",
    "qc_project_create",
    "qc_upload",
    "qc_compile",
    "qc_launch",
    "result_access",
    "result_disposition",
    "deployment",
    "orders",
    "trading",
)

_EXPECTED_PARTITION_SCHEMAS = (
    ("session_axis", "arv2-synthetic-session_axis-v1"),
    ("decision_rows", "arv2-synthetic-decision_rows-v1"),
    ("security_open_values", "arv2-synthetic-security_open_values-v1"),
    ("benchmark_open_values", "arv2-synthetic-benchmark_open_values-v1"),
    (
        "security_lifecycle_coverages",
        "arv2-synthetic-security_lifecycle_coverages-v1",
    ),
    ("terminal_requirements", "arv2-synthetic-terminal_requirements-v1"),
    (
        "terminal_shareholder_payoffs",
        "arv2-synthetic-terminal_shareholder_payoffs-v1",
    ),
)

MANIFEST_ROOT_FIELDS = (
    "schema",
    "status",
    "authority",
    "manifest_id",
    "manifest_sha256",
    "identity_recipe",
    "schema_binding",
    "run_candidate_binding",
    "algorithm_id",
    "evaluation_id",
    "horizons_sessions",
    "primary_horizon_sessions",
    "terminal_payoff_reinvestment_policy_id",
    "session_axis_binding",
    "partitions",
    "partition_census",
    "lineage",
    "transport",
    "external_bindings",
    "capabilities",
)

MANIFEST_ROOT_WIRE_TYPES = (
    "string",
    "string",
    "string",
    "string",
    "lowercase_sha256_string",
    "object",
    "object",
    "object",
    "string",
    "string",
    "integer_array",
    "integer",
    "string",
    "object",
    "partition_descriptor_array",
    "object",
    "object",
    "object",
    "null_binding_object",
    "false_capability_object",
)

MANIFEST_NESTED_FIELD_INVENTORIES = (
    (
        "identity_recipe",
        ("manifest_sha256", "manifest_id", "artifact_sha256"),
    ),
    (
        "schema_binding",
        ("schema_id", "schema_sha256", "schema_artifact_sha256"),
    ),
    (
        "run_candidate_binding",
        (
            "candidate_id",
            "candidate_hash",
            "declared_code_is_runtime_authenticated",
            "declared_partition_payloads_are_runtime_authenticated",
            "partition_rows_validated_against_row_contracts",
        ),
    ),
    (
        "session_axis_binding",
        (
            "first_session",
            "last_session",
            "session_count",
            "axis_sha256",
            "partition_byte_count",
            "partition_sha256",
        ),
    ),
    (
        "partition_census",
        ("role_count", "total_byte_count", "total_row_count"),
    ),
    (
        "lineage",
        (
            "manifest_parents",
            "ordered_partition_roles",
            "terminal_evidence_partition_roles",
            "production_truth_bound",
            "rights_bound",
            "operation_authority_bound",
        ),
    ),
    (
        "transport",
        (
            "physical_transport",
            "qc_object_store_manifest_key",
            "qc_project_file_path",
            "lean_adapter",
        ),
    ),
)

PARTITION_DESCRIPTOR_FIELDS = (
    "ordinal",
    "role",
    "partition_id",
    "partition_schema",
    "row_schema",
    "encoding",
    "immutable_artifact_id",
    "byte_count",
    "row_count",
    "artifact_sha256",
    "binding_sha256",
    "synthetic_fixture",
    "contains_licensed_rows",
    "contains_real_outcomes",
    "qc_object_store_key",
    "qc_project_file_path",
)

PARTITION_DESCRIPTOR_WIRE_TYPES = (
    "integer",
    "string",
    "safe_relative_id_string",
    "string",
    "string",
    "string",
    "safe_relative_id_string",
    "integer",
    "integer",
    "lowercase_sha256_string",
    "lowercase_sha256_string",
    "boolean",
    "boolean",
    "boolean",
    "null",
    "null",
)


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
        raise QcGlobalInputSchemaError(
            "global-input metadata is not canonical JSON"
        ) from exc


def _render_bytes(value: object) -> bytes:
    return _canonical_bytes(value) + b"\n"


def _require_sha256(value: object, name: str) -> None:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise QcGlobalInputSchemaError(f"{name} must be a lowercase SHA-256")


def _require_safe_id(value: object, name: str) -> None:
    if (
        type(value) is not str
        or len(value) > MAX_SAFE_ID_CHARS
        or _SAFE_ID.fullmatch(value) is None
        or value.startswith("/")
        or value.endswith("/")
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise QcGlobalInputSchemaError(f"{name} is unsafe")


def _row_contract_document(value: RowContract) -> dict[str, object]:
    return {
        "role": value.role,
        "row_schema": value.row_schema,
        "record_type": value.record_type,
        "root_envelope": value.root_envelope,
        "fields": list(value.fields),
        "wire_types": list(value.wire_types),
        "canonical_order": list(value.canonical_order),
        "timing_semantics": value.timing_semantics,
        "identity_semantics": value.identity_semantics,
        "value_semantics": value.value_semantics,
    }


def _evaluation_windows_document() -> list[dict[str, object]]:
    return [
        {
            "role": "formal_primary",
            "evaluation_segment_ids": [
                f"arv2-wf-test-{year}" for year in range(2020, 2026)
            ],
            "fold_ids": [f"arv2-wf-test-{year}" for year in range(2020, 2026)],
            "claim": "development_stop_go_descriptive_not_confirmatory",
            "pooled_with_primary": True,
        },
        {
            "role": "owner_directed_post_pandemic_sensitivity",
            "evaluation_segment_ids": [
                f"arv2-wf-test-{year}" for year in range(2021, 2026)
            ],
            "fold_ids": [f"arv2-wf-test-{year}" for year in range(2021, 2026)],
            "claim": "descriptive_sensitivity_cannot_replace_or_rescue_primary",
            "pooled_with_primary": False,
        },
        {
            "role": "partial_2026_exploratory",
            "evaluation_segment_ids": ["arv2-partial-2026-exploratory"],
            "fold_ids": [],
            "claim": (
                "separate_fixed_cutoff_exploratory_geometry_never_a_complete_"
                "fold_and_never_pooled"
            ),
            "pooled_with_primary": False,
        },
    ]


def _schema_document() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "schema_id": None,
        "schema_sha256": None,
        "status": STATUS,
        "authority": AUTHORITY,
        "identity_recipe": {
            "schema_sha256": (
                "sha256(canonical_compact_json_with_schema_id_and_"
                "schema_sha256_null)"
            ),
            "schema_id": (
                "arv2-qc-global-input-schema-<first16_schema_sha256>"
            ),
            "artifact_sha256": (
                "sha256(exact_rendered_schema_bytes);exported_separately_to_"
                "avoid_recursive_identity"
            ),
        },
        "accepted_core": {
            "run_candidate_schema": "arv2-qc-stock-event-study-run-candidate-v2",
            "algorithm_id": "arv2-qc-stock-event-study-core-v2",
            "evaluation_id": "arv2-eval-stock-historical-qc-001",
            "horizons_sessions": [1, 5, 20, 60],
            "primary_horizon_sessions": 20,
            "terminal_payoff_reinvestment_policy_id": (
                "arv2-terminal-payoff-benchmark-splice-v1"
            ),
            "run_contract_source": {
                "relative_path": "research/analyst_revisions_v2_qc/run_contract.py",
                "byte_count": 28_825,
                "sha256": (
                    "a72aa500a5c2d2fe68cfe9a00e6531a8c1a241e212cb8df8e2a7a56dba3d77d5"
                ),
                "canonicalization": (
                    "strict_utf8_no_bom_crlf_to_lf_no_bare_carriage_return"
                ),
            },
            "event_study_source": {
                "relative_path": "research/analyst_revisions_v2_qc/event_study.py",
                "upload_name": "event_study.py",
                "byte_count": 109_226,
                "sha256": (
                    "0f1e6f69c4bde56bb42a49d24d42b0a27cb2417d3c7bf8f1ea196e15fa0628fe"
                ),
                "canonicalization": (
                    "strict_utf8_no_bom_crlf_to_lf_no_bare_carriage_return"
                ),
            },
            "candidate_hash_authenticates_loaded_code": False,
        },
        "session_axis": {
            "calendar": "XNYS",
            "first_session": "2013-01-02",
            "last_session": "2026-08-28",
            "session_count": 3_435,
            "axis_sha256": (
                "b303555af32bda7d3f2caf6c43f3ae1c43723613086ab3dc848cfb86ab88d732"
            ),
            "canonical_partition_byte_count": 161_445,
            "canonical_partition_sha256": (
                "a4821282efee2048c31ea191fb3bc1c7cd1d854095b385a01cac2bcf69ca1de4"
            ),
            "pre_2021_state_may_be_truncated": False,
        },
        "evaluation_windows": _evaluation_windows_document(),
        "partition_schemas": {
            role: schema for role, schema in _EXPECTED_PARTITION_SCHEMAS
        },
        "synthetic_manifest_wire_contract": {
            "root_envelope": "json_object",
            "fields": list(MANIFEST_ROOT_FIELDS),
            "wire_types": list(MANIFEST_ROOT_WIRE_TYPES),
            "root_fixed_values": {
                "schema": "arv2-qc-global-input-manifest-v1",
                "status": STATUS,
                "authority": AUTHORITY,
                "algorithm_id": "arv2-qc-stock-event-study-core-v2",
                "evaluation_id": "arv2-eval-stock-historical-qc-001",
                "horizons_sessions": [1, 5, 20, 60],
                "primary_horizon_sessions": 20,
                "terminal_payoff_reinvestment_policy_id": (
                    "arv2-terminal-payoff-benchmark-splice-v1"
                ),
            },
            "root_derived_values": {
                "manifest_id": "semantic_hash_recipe",
                "manifest_sha256": "semantic_hash_recipe",
                "partitions": "exact_validated_descriptor_projection",
                "partition_census": "exact_sum_of_descriptor_counts",
                "external_bindings": "exact_null_inventory",
                "capabilities": "exact_false_inventory",
            },
            "semantic_identity_seed_null_fields": [
                "manifest_id",
                "manifest_sha256",
            ],
            "artifact_sha256_is_out_of_band": True,
            "maximum_rendered_byte_count": MAX_SYNTHETIC_MANIFEST_BYTES,
            "nested_field_inventories": {
                name: list(fields)
                for name, fields in MANIFEST_NESTED_FIELD_INVENTORIES
            },
            "nested_value_contracts": {
                "identity_recipe": {
                    "wire_types": {
                        "manifest_sha256": "string",
                        "manifest_id": "string",
                        "artifact_sha256": "string",
                    },
                    "fixed_values": {
                        "manifest_sha256": (
                            "sha256(canonical_compact_json_with_manifest_id_"
                            "and_manifest_sha256_null)"
                        ),
                        "manifest_id": (
                            "synthetic-arv2-qc-global-input-"
                            "<first16_manifest_sha256>"
                        ),
                        "artifact_sha256": (
                            "sha256(exact_rendered_manifest_bytes);held_in_"
                            "the_in_memory_object_and_not_embedded_to_avoid_"
                            "recursive_identity"
                        ),
                    },
                },
                "schema_binding": {
                    "wire_types": {
                        "schema_id": "string",
                        "schema_sha256": "lowercase_sha256_string",
                        "schema_artifact_sha256": "lowercase_sha256_string",
                    },
                    "fixed_values": {
                        "schema_id": "equals_enclosing_schema_id",
                        "schema_sha256": "equals_enclosing_schema_sha256",
                        "schema_artifact_sha256": (
                            "equals_exported_exact_schema_artifact_sha256"
                        ),
                    },
                },
                "run_candidate_binding": {
                    "wire_types": {
                        "candidate_id": "string",
                        "candidate_hash": "lowercase_sha256_string",
                        "declared_code_is_runtime_authenticated": "boolean",
                        "declared_partition_payloads_are_runtime_authenticated": (
                            "boolean"
                        ),
                        "partition_rows_validated_against_row_contracts": (
                            "boolean"
                        ),
                    },
                    "fixed_values": {
                        "declared_code_is_runtime_authenticated": False,
                        "declared_partition_payloads_are_runtime_authenticated": False,
                        "partition_rows_validated_against_row_contracts": False,
                    },
                },
                "session_axis_binding": {
                    "wire_types": {
                        "first_session": "iso_date_string",
                        "last_session": "iso_date_string",
                        "session_count": "integer",
                        "axis_sha256": "lowercase_sha256_string",
                        "partition_byte_count": "integer",
                        "partition_sha256": "lowercase_sha256_string",
                    },
                    "fixed_values": {
                        "first_session": "2013-01-02",
                        "last_session": "2026-08-28",
                        "session_count": 3_435,
                        "axis_sha256": (
                            "b303555af32bda7d3f2caf6c43f3ae1c43723613086ab3d"
                            "c848cfb86ab88d732"
                        ),
                        "partition_byte_count": 161_445,
                        "partition_sha256": (
                            "a4821282efee2048c31ea191fb3bc1c7cd1d854095b385a"
                            "01cac2bcf69ca1de4"
                        ),
                    },
                },
                "partition_census": {
                    "wire_types": {
                        "role_count": "integer",
                        "total_byte_count": "integer",
                        "total_row_count": "integer",
                    },
                    "fixed_values": {"role_count": 7},
                    "derived_values": {
                        "total_byte_count": "sum_descriptor_byte_count",
                        "total_row_count": "sum_descriptor_row_count",
                    },
                },
                "lineage": {
                    "wire_types": {
                        "manifest_parents": "string_array",
                        "ordered_partition_roles": "string_array",
                        "terminal_evidence_partition_roles": "string_array",
                        "production_truth_bound": "boolean",
                        "rights_bound": "boolean",
                        "operation_authority_bound": "boolean",
                    },
                    "fixed_values": {
                        "manifest_parents": [
                            "global_input_schema",
                            "synthetic_run_candidate",
                        ],
                        "ordered_partition_roles": list(ROLE_ORDER),
                        "terminal_evidence_partition_roles": [
                            "security_lifecycle_coverages",
                            "terminal_requirements",
                            "terminal_shareholder_payoffs",
                        ],
                        "production_truth_bound": False,
                        "rights_bound": False,
                        "operation_authority_bound": False,
                    },
                },
                "transport": {
                    "wire_types": {
                        "physical_transport": "null",
                        "qc_object_store_manifest_key": "null",
                        "qc_project_file_path": "null",
                        "lean_adapter": "null",
                    },
                    "fixed_values": {
                        "physical_transport": None,
                        "qc_object_store_manifest_key": None,
                        "qc_project_file_path": None,
                        "lean_adapter": None,
                    },
                },
                "external_bindings": {
                    "exact_keys": list(_EXTERNAL_BINDING_NAMES),
                    "all_values": "null",
                },
                "capabilities": {
                    "exact_keys": list(_CAPABILITY_NAMES),
                    "all_values": "boolean_false",
                },
            },
            "partition_descriptor": {
                "root_envelope": "json_object",
                "fields": list(PARTITION_DESCRIPTOR_FIELDS),
                "wire_types": list(PARTITION_DESCRIPTOR_WIRE_TYPES),
                "fixed_values": {
                    "encoding": ENCODING,
                    "synthetic_fixture": True,
                    "contains_licensed_rows": False,
                    "contains_real_outcomes": False,
                    "qc_object_store_key": None,
                    "qc_project_file_path": None,
                },
                "derived_values": {
                    "ordinal": "one_based_position_in_role_order",
                    "role": "role_order_at_ordinal",
                    "partition_id": (
                        "run_candidate_partition_id_for_role"
                    ),
                    "partition_schema": (
                        "run_candidate_partition_schema_for_role"
                    ),
                    "row_schema": "row_contract_schema_for_role",
                    "immutable_artifact_id": (
                        "immutable_artifact_id_recipe"
                    ),
                    "byte_count": (
                        "run_candidate_partition_byte_count_for_role"
                    ),
                    "row_count": (
                        "run_candidate_partition_row_count_for_role"
                    ),
                    "artifact_sha256": (
                        "run_candidate_partition_sha256_for_role"
                    ),
                    "binding_sha256": "binding_hash_recipe",
                },
                "binding_hash_domain": PARTITION_BINDING_HASH_DOMAIN,
                "binding_hash_recipe": (
                    "sha256(canonical_json_of_domain_schema_hash_candidate_"
                    "hash_and_descriptor_with_identity_fields_null)"
                ),
                "immutable_artifact_id_recipe": (
                    PARTITION_IMMUTABLE_ID_RECIPE
                ),
                "safe_id_contract": {
                    "maximum_characters": MAX_SAFE_ID_CHARS,
                    "first_character": "ascii_alphanumeric",
                    "remaining_characters": "ascii_alphanumeric_dot_underscore_slash_hyphen",
                    "absolute_or_trailing_slash_allowed": False,
                    "empty_dot_or_dotdot_path_segment_allowed": False,
                },
            },
        },
        "row_contracts": [
            _row_contract_document(item) for item in _expected_row_contracts()
        ],
        "nested_terminal_lifecycle_fields": list(TERMINAL_LIFECYCLE_FIELDS),
        "nested_terminal_lifecycle_wire_contract": {
            "root_envelope": "$dataclass:TerminalLifecycle/$fields",
            "fields": list(TERMINAL_LIFECYCLE_FIELDS),
            "wire_types": list(TERMINAL_LIFECYCLE_WIRE_TYPES),
        },
        "terminal_event_kinds": list(TERMINAL_EVENT_KINDS),
        "serialization": {
            "encoding": ENCODING,
            "manifest": "canonical_sorted_compact_json_exactly_one_lf",
            "partitions": "one_canonical_tagged_json_object_per_line",
            "date": "tagged_canonical_yyyy_mm_dd",
            "decimal": "tagged_finite_canonical_decimal_string",
            "floats_allowed": False,
            "unknown_or_duplicate_fields_allowed": False,
            "wire_type_encodings": {
                "string": "exact_json_string",
                "optional_string": "exact_json_string_or_null",
                "lowercase_sha256_string": "exact_64_character_lowercase_hex_json_string",
                "date_tag": {"$date": "canonical_yyyy_mm_dd_json_string"},
                "decimal_tag": {
                    "$decimal": (
                        "finite_python_decimal_str_preserving_exponent_and_"
                        "trailing_zero_representation"
                    )
                },
                "terminal_lifecycle_dataclass_or_null": (
                    "$dataclass:TerminalLifecycle/$fields_or_null"
                ),
            },
            "role_order": list(ROLE_ORDER),
            "canonical_order_interpretation": {
                "direction": "ascending_by_the_declared_field_tuple",
                "null_order": "all_canonical_order_fields_are_non_null",
                "date_comparison": "chronological_equivalent_to_iso_yyyy_mm_dd",
                "string_comparison": (
                    "exact_unicode_code_point_lexicographic_no_locale_or_casefold"
                ),
                "duplicate_ordering_key_allowed": False,
            },
        },
        "point_in_time_contract": {
            "vendor_calls_inside_backtest": False,
            "rating_semantics_inferred_inside_backtest": False,
            "current_ticker_resolution_inside_backtest": False,
            "timestamps_revised_inside_backtest": False,
            "decision_rows_require_upstream_effective_available_version_lineage": True,
            "manifest_self_assertion_proves_point_in_time": False,
        },
        "authority_role_scopes": {
            "production_input_read_roles": [
                "session_axis",
                "decision_rows",
            ],
            "real_outcome_read_roles": [
                "security_open_values",
                "benchmark_open_values",
                "security_lifecycle_coverages",
                "terminal_requirements",
                "terminal_shareholder_payoffs",
            ],
            "input_read_authority_implies_real_outcome_read_authority": False,
            "schema_or_manifest_identity_grants_either_authority": False,
        },
        "terminal_contract": {
            "qc_delisting_price_is_total_shareholder_payoff": False,
            "terminal_date_alone_proves_economic_availability": False,
            "cash_bankruptcy_delisting_policy": (
                "proven_payoff_reinvested_in_spy_to_fixed_horizon"
            ),
            "stock_and_mixed_merger_policy": "successor_valued_at_fixed_horizon",
            "missing_or_ambiguous_evidence": "named_refusal_or_invalid_data",
        },
        "reserved_benchmark_identity": {
            "security_id": "synthetic-benchmark-security-spy",
            "listing_id": "synthetic-benchmark-listing-spy",
            "historical_ticker": "SPY",
            "total_return_series_id": "synthetic-spy-total-return-series",
        },
        "synthetic_source_identities": {
            "open_source": "synthetic_qc_total_return_open",
            "lifecycle_source": "synthetic_complete_security_lifecycle_inventory",
            "terminal_source": "synthetic_total_shareholder_payoff",
            "total_return_value_basis": (
                "synthetic_split_distribution_adjusted_total_return_index_same_vintage"
            ),
            "terminal_value_basis": (
                "synthetic_split_distribution_adjusted_total_return_index_same_vintage"
            ),
        },
        "transport_contract": {
            "logical_shape": (
                "one_manifest_plus_seven_role_separated_immutable_partitions"
            ),
            "physical_transport": None,
            "qc_object_store_key": None,
            "qc_project_file_path": None,
            "lean_adapter": None,
            "production_admission_implemented": False,
            "synthetic_manifest_loader_reads_partition_payloads": False,
            "synthetic_manifest_loader_validates_partition_rows_against_contracts": False,
            "synthetic_descriptor_metadata_authenticates_payload_presence": False,
            "partition_binding_hash_recipe": (
                "sha256(canonical_json_of_explicit_domain_schema_hash_"
                "candidate_hash_and_role_descriptor_with_identity_fields_null)"
            ),
        },
        "lineage_hash_contract": {
            "hash_algorithm": "sha256",
            "input_row_sha256": (
                "caller_declared_hash_of_future_upstream_decision_feature_and_"
                "effective_available_version_lineage_artifact"
            ),
            "source_sha256": (
                "caller_declared_hash_of_future_upstream_value_or_lifecycle_"
                "source_artifact"
            ),
            "partition_artifact_sha256": (
                "sha256_of_exact_canonical_tagged_jsonl_partition_bytes"
            ),
            "source_artifact_manifest_bound": False,
            "row_lineage_hashes_recomputed_by_this_milestone": False,
            "row_lineage_provenance_authenticated_by_this_milestone": False,
            "production_recipe_and_admission_deferred": True,
        },
        "external_bindings": {name: None for name in _EXTERNAL_BINDING_NAMES},
        "capabilities": {name: False for name in _CAPABILITY_NAMES},
    }


def _schema_identity_document() -> dict[str, object]:
    document = _schema_document()
    digest = hashlib.sha256(_canonical_bytes(document)).hexdigest()
    document["schema_sha256"] = digest
    document["schema_id"] = f"arv2-qc-global-input-schema-{digest[:16]}"
    return document


def _require_static_schema() -> tuple[RowContract, ...]:
    if (
        _contract_manifest_document is not _PINNED_MANIFEST_CONTRACT_DOCUMENT
        or _manifest_document is not _PINNED_MANIFEST_DOCUMENT
        or _descriptor_document is not _PINNED_DESCRIPTOR_DOCUMENT
        or _build_descriptor is not _PINNED_BUILD_DESCRIPTOR
        or _require_descriptor_matches_inputs
        is not _PINNED_REQUIRE_DESCRIPTOR_MATCHES_INPUTS
        or _copy_candidate is not _PINNED_COPY_CANDIDATE
    ):
        raise QcGlobalInputSchemaError(
            "synthetic manifest builder identity changed"
        )
    scalar_identities = (
        (SCHEMA, "arv2-qc-global-input-schema-v1"),
        (STATUS, "synthetic_fixture_only_production_shaped_schema_not_production_truth"),
        (
            AUTHORITY,
            "schema_and_synthetic_metadata_only_no_input_qc_outcome_result_or_"
            "trading_authority",
        ),
        (ENCODING, "canonical_tagged_jsonl_strict_utf8_lf-v1"),
        (
            PARTITION_BINDING_HASH_DOMAIN,
            "arv2-qc-global-input-partition-binding-v1",
        ),
        (
            PARTITION_IMMUTABLE_ID_RECIPE,
            "synthetic-arv2-global-input-<hyphenated-role>-<binding_sha256>",
        ),
        (RUN_CANDIDATE_SCHEMA, "arv2-qc-stock-event-study-run-candidate-v2"),
        (ALGORITHM_ID, "arv2-qc-stock-event-study-core-v2"),
        (EVALUATION_ID, "arv2-eval-stock-historical-qc-001"),
        (
            TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID,
            "arv2-terminal-payoff-benchmark-splice-v1",
        ),
        (
            CORE_RELATIVE_PATH,
            "research/analyst_revisions_v2_qc/event_study.py",
        ),
        (CORE_UPLOAD_NAME, "event_study.py"),
        (
            RUN_CONTRACT_SOURCE_SHA256,
            "a72aa500a5c2d2fe68cfe9a00e6531a8c1a241e212cb8df8e2a7a56dba3d77d5",
        ),
        (
            EVENT_STUDY_SOURCE_SHA256,
            "0f1e6f69c4bde56bb42a49d24d42b0a27cb2417d3c7bf8f1ea196e15fa0628fe",
        ),
        (
            SESSION_AXIS_PARTITION_SHA256,
            "a4821282efee2048c31ea191fb3bc1c7cd1d854095b385a01cac2bcf69ca1de4",
        ),
        (BENCHMARK_SECURITY_ID, "synthetic-benchmark-security-spy"),
        (BENCHMARK_LISTING_ID, "synthetic-benchmark-listing-spy"),
        (BENCHMARK_TICKER, "SPY"),
        (
            BENCHMARK_TOTAL_RETURN_SERIES_ID,
            "synthetic-spy-total-return-series",
        ),
        (SYNTHETIC_OPEN_SOURCE, "synthetic_qc_total_return_open"),
        (
            SYNTHETIC_LIFECYCLE_SOURCE,
            "synthetic_complete_security_lifecycle_inventory",
        ),
        (SYNTHETIC_TERMINAL_SOURCE, "synthetic_total_shareholder_payoff"),
        (
            SYNTHETIC_TOTAL_RETURN_VALUE_BASIS,
            "synthetic_split_distribution_adjusted_total_return_index_same_vintage",
        ),
        (
            SYNTHETIC_TERMINAL_VALUE_BASIS,
            "synthetic_split_distribution_adjusted_total_return_index_same_vintage",
        ),
        (SCHEMA_ID, "arv2-qc-global-input-schema-d56e2b5ec26d4068"),
        (
            SCHEMA_SHA256,
            "d56e2b5ec26d4068876bff3b549c1f9c7a83014c1372403d7bf33e511bd8e640",
        ),
        (
            SCHEMA_ARTIFACT_SHA256,
            "0f60cb3badec36fa9589b220cf91aee43a965865244c7c2726d16da71f6ae3d2",
        ),
    )
    if any(
        type(actual) is not str or actual != expected
        for actual, expected in scalar_identities
    ):
        raise QcGlobalInputSchemaError(
            "static global-input schema identity changed"
        )
    integer_identities = (
        (RUN_CONTRACT_SOURCE_BYTE_COUNT, 28_825),
        (EVENT_STUDY_SOURCE_BYTE_COUNT, 109_226),
        (SESSION_AXIS_PARTITION_BYTE_COUNT, 161_445),
        (MAX_SYNTHETIC_MANIFEST_BYTES, 1_048_576),
        (MAX_SAFE_ID_CHARS, 512),
        (REVIEWED_AXIS_SESSION_COUNT, 3_435),
        (PRIMARY_HORIZON, 20),
    )
    if any(
        type(actual) is not int or actual != expected
        for actual, expected in integer_identities
    ):
        raise QcGlobalInputSchemaError(
            "static global-input integer identity changed"
        )
    if (
        type(HORIZONS) is not tuple
        or any(type(item) is not int for item in HORIZONS)
        or HORIZONS != (1, 5, 20, 60)
        or type(ROLE_ORDER) is not tuple
        or any(type(item) is not str for item in ROLE_ORDER)
        or ROLE_ORDER
        != (
            "session_axis",
            "decision_rows",
            "security_open_values",
            "benchmark_open_values",
            "security_lifecycle_coverages",
            "terminal_requirements",
            "terminal_shareholder_payoffs",
        )
        or type(TERMINAL_LIFECYCLE_FIELDS) is not tuple
        or any(type(item) is not str for item in TERMINAL_LIFECYCLE_FIELDS)
        or TERMINAL_LIFECYCLE_FIELDS
        != (
            "security_id",
            "terminal_listing_id",
            "terminal_historical_ticker",
            "terminal_session",
            "event_kind",
            "successor_security_id",
            "successor_listing_id",
            "successor_historical_ticker",
            "total_return_series_id",
        )
        or type(REVIEWED_AXIS_START) is not date
        or REVIEWED_AXIS_START.isoformat() != "2013-01-02"
        or type(REVIEWED_AXIS_END) is not date
        or REVIEWED_AXIS_END.isoformat() != "2026-08-28"
        or type(REVIEWED_AXIS_SHA256) is not str
        or REVIEWED_AXIS_SHA256
        != "b303555af32bda7d3f2caf6c43f3ae1c43723613086ab3dc848cfb86ab88d732"
    ):
        raise QcGlobalInputSchemaError("accepted event-study geometry changed")
    literal_terminal_lifecycle_wire_types = (
        "string",
        "string",
        "string",
        "date_tag",
        "string",
        "optional_string",
        "optional_string",
        "optional_string",
        "string",
    )
    literal_terminal_event_kinds = (
        "delisting",
        "bankruptcy",
        "cash_merger",
        "stock_merger",
        "mixed_merger",
    )
    literal_external_binding_names = (
        "schema_review_commit",
        "schema_counter_review_commit",
        "data_entitlement_audit_id",
        "vendor_to_qc_processing_rights_receipt_id",
        "production_truth_approval_id",
        "production_global_input_manifest_id",
        "production_global_input_manifest_sha256",
        "owner_production_input_read_authority_id",
        "owner_real_outcome_read_authority_id",
        "owner_qc_object_store_write_authority_id",
        "owner_qc_project_create_authority_id",
        "qc_project_id",
        "qc_object_store_manifest_key",
        "owner_qc_upload_authority_id",
        "qc_upload_receipt_id",
        "owner_qc_compile_authority_id",
        "qc_compile_id",
        "compile_receipt_id",
        "owner_backtest_launch_authority_id",
        "external_evaluation_authority_id",
        "atomic_evaluation_receipt_id",
        "qc_backtest_id_or_ambiguous_submission_lock",
        "result_access_authority_id",
        "result_disposition_authority_id",
        "deployment_authority_id",
        "order_authority_id",
        "trading_authority_id",
    )
    literal_capability_names = (
        "filesystem_read",
        "environment_read",
        "provider_access",
        "licensed_input_read",
        "production_input_read",
        "real_outcome_access",
        "qc_object_store_read",
        "qc_object_store_write",
        "qc_project_create",
        "qc_upload",
        "qc_compile",
        "qc_launch",
        "result_access",
        "result_disposition",
        "deployment",
        "orders",
        "trading",
    )
    for actual, expected, name in (
        (
            TERMINAL_LIFECYCLE_WIRE_TYPES,
            literal_terminal_lifecycle_wire_types,
            "terminal lifecycle wire-type inventory",
        ),
        (
            TERMINAL_EVENT_KINDS,
            literal_terminal_event_kinds,
            "terminal event-kind inventory",
        ),
        (
            _EXTERNAL_BINDING_NAMES,
            literal_external_binding_names,
            "external-binding inventory",
        ),
        (
            _CAPABILITY_NAMES,
            literal_capability_names,
            "capability inventory",
        ),
    ):
        if (
            type(actual) is not tuple
            or any(type(item) is not str for item in actual)
            or actual != expected
        ):
            raise QcGlobalInputSchemaError(f"static {name} changed")
    for actual, name in (
        (MANIFEST_ROOT_FIELDS, "manifest root field inventory"),
        (MANIFEST_ROOT_WIRE_TYPES, "manifest root wire-type inventory"),
        (PARTITION_DESCRIPTOR_FIELDS, "partition descriptor field inventory"),
        (
            PARTITION_DESCRIPTOR_WIRE_TYPES,
            "partition descriptor wire-type inventory",
        ),
    ):
        if type(actual) is not tuple or any(
            type(item) is not str for item in actual
        ):
            raise QcGlobalInputSchemaError(f"static {name} type changed")
    if (
        len(MANIFEST_ROOT_FIELDS) != len(MANIFEST_ROOT_WIRE_TYPES)
        or len(PARTITION_DESCRIPTOR_FIELDS)
        != len(PARTITION_DESCRIPTOR_WIRE_TYPES)
    ):
        raise QcGlobalInputSchemaError(
            "static manifest wire contract length changed"
        )
    if type(MANIFEST_NESTED_FIELD_INVENTORIES) is not tuple or any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or type(item[1]) is not tuple
        or any(type(field) is not str for field in item[1])
        for item in MANIFEST_NESTED_FIELD_INVENTORIES
    ):
        raise QcGlobalInputSchemaError(
            "static manifest nested-field inventory type changed"
        )
    literal_partition_schemas = (
        ("session_axis", "arv2-synthetic-session_axis-v1"),
        ("decision_rows", "arv2-synthetic-decision_rows-v1"),
        (
            "security_open_values",
            "arv2-synthetic-security_open_values-v1",
        ),
        (
            "benchmark_open_values",
            "arv2-synthetic-benchmark_open_values-v1",
        ),
        (
            "security_lifecycle_coverages",
            "arv2-synthetic-security_lifecycle_coverages-v1",
        ),
        (
            "terminal_requirements",
            "arv2-synthetic-terminal_requirements-v1",
        ),
        (
            "terminal_shareholder_payoffs",
            "arv2-synthetic-terminal_shareholder_payoffs-v1",
        ),
    )
    if type(_EXPECTED_PARTITION_SCHEMAS) is not tuple or any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or type(item[1]) is not str
        for item in _EXPECTED_PARTITION_SCHEMAS
    ):
        raise QcGlobalInputSchemaError(
            "expected partition-schema inventory type changed"
        )
    if _EXPECTED_PARTITION_SCHEMAS != literal_partition_schemas:
        raise QcGlobalInputSchemaError(
            "expected partition-schema inventory changed"
        )
    if (
        PARTITION_SCHEMAS is not _PINNED_PARTITION_SCHEMAS
        or type(PARTITION_SCHEMAS) is not _MAPPING_PROXY_TYPE
    ):
        raise QcGlobalInputSchemaError("accepted partition schemas changed")
    partition_schema_items = tuple(PARTITION_SCHEMAS.items())
    if any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or type(item[1]) is not str
        for item in partition_schema_items
    ):
        raise QcGlobalInputSchemaError(
            "accepted partition-schema item type changed"
        )
    if (
        tuple(sorted(partition_schema_items))
        != tuple(sorted(literal_partition_schemas))
        or len(PARTITION_SCHEMAS) != len(ROLE_ORDER)
    ):
        raise QcGlobalInputSchemaError("accepted partition schemas changed")
    expected_rows = _expected_row_contracts()
    if type(ROW_CONTRACTS) is not tuple or len(ROW_CONTRACTS) != len(
        expected_rows
    ):
        raise QcGlobalInputSchemaError("row-contract inventory changed")
    for actual, expected in zip(ROW_CONTRACTS, expected_rows):
        if type(actual) is not RowContract:
            raise QcGlobalInputSchemaError("row-contract type changed")
        values = tuple(
            getattr(actual, field.name) for field in dataclasses.fields(actual)
        )
        expected_values = tuple(
            getattr(expected, field.name)
            for field in dataclasses.fields(expected)
        )
        if (
            any(
                type(value) is not type(wanted)
                for value, wanted in zip(values, expected_values)
            )
            or any(
                type(value) is tuple
                and any(type(item) is not str for item in value)
                for value in values
            )
            or len(actual.fields) != len(actual.wire_types)
            or values != expected_values
        ):
            raise QcGlobalInputSchemaError("row-contract content changed")
    if tuple(
        field.name
        for field in dataclasses.fields(GlobalInputPartitionDescriptor)
    ) != PARTITION_DESCRIPTOR_FIELDS:
        raise QcGlobalInputSchemaError(
            "partition descriptor dataclass topology changed"
        )
    schema_document = _schema_identity_document()
    if (
        schema_document["schema_id"] != SCHEMA_ID
        or schema_document["schema_sha256"] != SCHEMA_SHA256
    ):
        raise QcGlobalInputSchemaError(
            "global-input schema identity does not reproduce"
        )
    return expected_rows


def render_qc_global_input_schema_bytes() -> bytes:
    """Return the canonical, content-addressed schema declaration bytes."""

    _require_static_schema()
    payload = _render_bytes(_schema_identity_document())
    if hashlib.sha256(payload).hexdigest() != SCHEMA_ARTIFACT_SHA256:
        raise QcGlobalInputSchemaError(
            "global-input schema artifact identity does not reproduce"
        )
    return payload


@dataclasses.dataclass(frozen=True, slots=True)
class GlobalInputPartitionDescriptor:
    ordinal: int
    role: str
    partition_id: str
    partition_schema: str
    row_schema: str
    encoding: str
    immutable_artifact_id: str
    byte_count: int
    row_count: int
    artifact_sha256: str
    binding_sha256: str
    synthetic_fixture: bool
    contains_licensed_rows: bool
    contains_real_outcomes: bool
    qc_object_store_key: None
    qc_project_file_path: None


def _descriptor_seed_document(
    *,
    ordinal: int,
    partition: SyntheticPartitionBinding,
    row: RowContract,
    run_candidate_hash: str,
) -> dict[str, object]:
    return {
        "hash_domain": PARTITION_BINDING_HASH_DOMAIN,
        "global_input_schema_sha256": SCHEMA_SHA256,
        "run_candidate_hash": run_candidate_hash,
        "ordinal": ordinal,
        "role": row.role,
        "partition_id": partition.partition_id,
        "partition_schema": partition.schema,
        "row_schema": row.row_schema,
        "encoding": ENCODING,
        "immutable_artifact_id": None,
        "byte_count": partition.byte_count,
        "row_count": partition.row_count,
        "artifact_sha256": partition.sha256,
        "binding_sha256": None,
        "synthetic_fixture": True,
        "contains_licensed_rows": False,
        "contains_real_outcomes": False,
        "qc_object_store_key": None,
        "qc_project_file_path": None,
    }


def _build_descriptor(
    *,
    ordinal: int,
    partition: SyntheticPartitionBinding,
    row: RowContract,
    run_candidate_hash: str,
) -> GlobalInputPartitionDescriptor:
    seed = _descriptor_seed_document(
        ordinal=ordinal,
        partition=partition,
        row=row,
        run_candidate_hash=run_candidate_hash,
    )
    digest = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
    return GlobalInputPartitionDescriptor(
        ordinal=ordinal,
        role=row.role,
        partition_id=partition.partition_id,
        partition_schema=partition.schema,
        row_schema=row.row_schema,
        encoding=ENCODING,
        immutable_artifact_id=(
            f"synthetic-arv2-global-input-{row.role.replace('_', '-')}-{digest}"
        ),
        byte_count=partition.byte_count,
        row_count=partition.row_count,
        artifact_sha256=partition.sha256,
        binding_sha256=digest,
        synthetic_fixture=True,
        contains_licensed_rows=False,
        contains_real_outcomes=False,
        qc_object_store_key=None,
        qc_project_file_path=None,
    )


_PINNED_BUILD_DESCRIPTOR = _build_descriptor


def _descriptor_document(
    value: GlobalInputPartitionDescriptor,
) -> dict[str, object]:
    if type(value) is not GlobalInputPartitionDescriptor:
        raise QcGlobalInputSchemaError("partition descriptor type changed")
    fields = dataclasses.fields(value)
    if tuple(field.name for field in fields) != PARTITION_DESCRIPTOR_FIELDS:
        raise QcGlobalInputSchemaError(
            "partition descriptor field inventory changed"
        )
    return {
        field.name: getattr(value, field.name)
        for field in fields
    }


_PINNED_DESCRIPTOR_DOCUMENT = _descriptor_document


def _validate_descriptor(value: GlobalInputPartitionDescriptor) -> None:
    if type(value) is not GlobalInputPartitionDescriptor:
        raise QcGlobalInputSchemaError("partition descriptor type changed")
    if type(value.ordinal) is not int or value.ordinal < 1:
        raise QcGlobalInputSchemaError("partition ordinal changed")
    for name in (
        "role",
        "partition_id",
        "partition_schema",
        "row_schema",
        "encoding",
        "immutable_artifact_id",
        "artifact_sha256",
        "binding_sha256",
    ):
        if type(getattr(value, name)) is not str:
            raise QcGlobalInputSchemaError(
                "partition descriptor scalar type changed"
            )
    _require_safe_id(value.partition_id, "partition_id")
    _require_safe_id(value.immutable_artifact_id, "immutable_artifact_id")
    _require_sha256(value.artifact_sha256, "partition artifact_sha256")
    _require_sha256(value.binding_sha256, "partition binding_sha256")
    if type(value.byte_count) is not int or value.byte_count < 0:
        raise QcGlobalInputSchemaError("partition byte_count changed")
    if type(value.row_count) is not int or value.row_count < 0:
        raise QcGlobalInputSchemaError("partition row_count changed")
    if value.synthetic_fixture is not True:
        raise QcGlobalInputSchemaError(
            "partition is not exact synthetic fixture metadata"
        )
    if value.contains_licensed_rows is not False:
        raise QcGlobalInputSchemaError(
            "partition claims licensed rows"
        )
    if value.contains_real_outcomes is not False:
        raise QcGlobalInputSchemaError(
            "partition claims real outcomes"
        )
    if (
        value.qc_object_store_key is not None
        or value.qc_project_file_path is not None
    ):
        raise QcGlobalInputSchemaError(
            "partition descriptor acquired a physical transport binding"
        )


def _require_descriptor_matches_inputs(
    value: GlobalInputPartitionDescriptor,
    *,
    ordinal: int,
    partition: SyntheticPartitionBinding,
    row: RowContract,
    run_candidate_hash: str,
) -> None:
    """Recompute one descriptor without trusting either descriptor builder."""

    _validate_descriptor(value)
    if (
        type(ordinal) is not int
        or ordinal < 1
        or type(partition) is not SyntheticPartitionBinding
        or type(row) is not RowContract
        or type(run_candidate_hash) is not str
    ):
        raise QcGlobalInputSchemaError(
            "partition descriptor derivation input type changed"
        )
    _require_sha256(run_candidate_hash, "run candidate hash")
    seed = {
        "hash_domain": "arv2-qc-global-input-partition-binding-v1",
        "global_input_schema_sha256": SCHEMA_SHA256,
        "run_candidate_hash": run_candidate_hash,
        "ordinal": ordinal,
        "role": row.role,
        "partition_id": partition.partition_id,
        "partition_schema": partition.schema,
        "row_schema": row.row_schema,
        "encoding": "canonical_tagged_jsonl_strict_utf8_lf-v1",
        "immutable_artifact_id": None,
        "byte_count": partition.byte_count,
        "row_count": partition.row_count,
        "artifact_sha256": partition.sha256,
        "binding_sha256": None,
        "synthetic_fixture": True,
        "contains_licensed_rows": False,
        "contains_real_outcomes": False,
        "qc_object_store_key": None,
        "qc_project_file_path": None,
    }
    digest = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
    immutable_artifact_id = (
        "synthetic-arv2-global-input-"
        f"{row.role.replace('_', '-')}-{digest}"
    )
    actual = (
        value.ordinal,
        value.role,
        value.partition_id,
        value.partition_schema,
        value.row_schema,
        value.encoding,
        value.immutable_artifact_id,
        value.byte_count,
        value.row_count,
        value.artifact_sha256,
        value.binding_sha256,
        value.synthetic_fixture,
        value.contains_licensed_rows,
        value.contains_real_outcomes,
        value.qc_object_store_key,
        value.qc_project_file_path,
    )
    expected = (
        ordinal,
        row.role,
        partition.partition_id,
        partition.schema,
        row.row_schema,
        "canonical_tagged_jsonl_strict_utf8_lf-v1",
        immutable_artifact_id,
        partition.byte_count,
        partition.row_count,
        partition.sha256,
        digest,
        True,
        False,
        False,
        None,
        None,
    )
    if actual != expected:
        raise QcGlobalInputSchemaError(
            "partition descriptor does not match its candidate inputs"
        )


_PINNED_REQUIRE_DESCRIPTOR_MATCHES_INPUTS = (
    _require_descriptor_matches_inputs
)


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticQcGlobalInputManifest:
    manifest_id: str
    manifest_sha256: str
    manifest_artifact_sha256: str
    schema_id: str
    schema_sha256: str
    schema_artifact_sha256: str
    run_candidate_id: str
    run_candidate_hash: str
    partitions: tuple[GlobalInputPartitionDescriptor, ...]
    total_byte_count: int
    total_row_count: int
    external_bindings: tuple[tuple[str, None], ...]
    capabilities: tuple[tuple[str, bool], ...]
    _run_candidate: SyntheticQcRunCandidate = dataclasses.field(repr=False)
    _canonical_document: bytes = dataclasses.field(repr=False)

    @property
    def filesystem_read_available(self) -> bool:
        return False

    @property
    def environment_read_available(self) -> bool:
        return False

    @property
    def provider_access_available(self) -> bool:
        return False

    @property
    def licensed_input_read_available(self) -> bool:
        return False

    @property
    def production_manifest_available(self) -> bool:
        return False

    @property
    def production_input_read_available(self) -> bool:
        return False

    @property
    def real_outcome_access_available(self) -> bool:
        return False

    @property
    def qc_object_store_read_available(self) -> bool:
        return False

    @property
    def qc_object_store_write_available(self) -> bool:
        return False

    @property
    def qc_project_create_available(self) -> bool:
        return False

    @property
    def upload_available(self) -> bool:
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
    def result_disposition_available(self) -> bool:
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


def _contract_manifest_document(
    *,
    candidate: SyntheticQcRunCandidate,
    partitions: tuple[GlobalInputPartitionDescriptor, ...],
    manifest_id: str | None,
    manifest_sha256: str | None,
) -> dict[str, object]:
    document = {
        "schema": "arv2-qc-global-input-manifest-v1",
        "status": STATUS,
        "authority": AUTHORITY,
        "manifest_id": manifest_id,
        "manifest_sha256": manifest_sha256,
        "identity_recipe": {
            "manifest_sha256": (
                "sha256(canonical_compact_json_with_manifest_id_and_"
                "manifest_sha256_null)"
            ),
            "manifest_id": (
                "synthetic-arv2-qc-global-input-<first16_manifest_sha256>"
            ),
            "artifact_sha256": (
                "sha256(exact_rendered_manifest_bytes);held_in_the_in_memory_"
                "object_and_not_embedded_to_avoid_recursive_identity"
            ),
        },
        "schema_binding": {
            "schema_id": SCHEMA_ID,
            "schema_sha256": SCHEMA_SHA256,
            "schema_artifact_sha256": SCHEMA_ARTIFACT_SHA256,
        },
        "run_candidate_binding": {
            "candidate_id": candidate.candidate_id,
            "candidate_hash": candidate.candidate_hash,
            "declared_code_is_runtime_authenticated": False,
            "declared_partition_payloads_are_runtime_authenticated": False,
            "partition_rows_validated_against_row_contracts": False,
        },
        "algorithm_id": ALGORITHM_ID,
        "evaluation_id": EVALUATION_ID,
        "horizons_sessions": list(HORIZONS),
        "primary_horizon_sessions": PRIMARY_HORIZON,
        "terminal_payoff_reinvestment_policy_id": (
            TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID
        ),
        "session_axis_binding": {
            "first_session": REVIEWED_AXIS_START.isoformat(),
            "last_session": REVIEWED_AXIS_END.isoformat(),
            "session_count": REVIEWED_AXIS_SESSION_COUNT,
            "axis_sha256": REVIEWED_AXIS_SHA256,
            "partition_byte_count": SESSION_AXIS_PARTITION_BYTE_COUNT,
            "partition_sha256": SESSION_AXIS_PARTITION_SHA256,
        },
        "partitions": [
            _PINNED_DESCRIPTOR_DOCUMENT(item) for item in partitions
        ],
        "partition_census": {
            "role_count": len(partitions),
            "total_byte_count": sum(
                item.byte_count for item in partitions
            ),
            "total_row_count": sum(item.row_count for item in partitions),
        },
        "lineage": {
            "manifest_parents": [
                "global_input_schema",
                "synthetic_run_candidate",
            ],
            "ordered_partition_roles": list(ROLE_ORDER),
            "terminal_evidence_partition_roles": [
                "security_lifecycle_coverages",
                "terminal_requirements",
                "terminal_shareholder_payoffs",
            ],
            "production_truth_bound": False,
            "rights_bound": False,
            "operation_authority_bound": False,
        },
        "transport": {
            "physical_transport": None,
            "qc_object_store_manifest_key": None,
            "qc_project_file_path": None,
            "lean_adapter": None,
        },
        "external_bindings": {
            name: None for name in _EXTERNAL_BINDING_NAMES
        },
        "capabilities": {name: False for name in _CAPABILITY_NAMES},
    }
    if tuple(document) != MANIFEST_ROOT_FIELDS:
        raise QcGlobalInputSchemaError(
            "synthetic manifest root field inventory changed"
        )
    for name, fields in MANIFEST_NESTED_FIELD_INVENTORIES:
        value = document[name]
        if type(value) is not dict or tuple(value) != fields:
            raise QcGlobalInputSchemaError(
                f"synthetic manifest {name} field inventory changed"
            )
    return document


_PINNED_MANIFEST_CONTRACT_DOCUMENT = _contract_manifest_document


def _manifest_document(
    *,
    candidate: SyntheticQcRunCandidate,
    partitions: tuple[GlobalInputPartitionDescriptor, ...],
    manifest_id: str | None,
    manifest_sha256: str | None,
) -> dict[str, object]:
    return _contract_manifest_document(
        candidate=candidate,
        partitions=partitions,
        manifest_id=manifest_id,
        manifest_sha256=manifest_sha256,
    )


_PINNED_MANIFEST_DOCUMENT = _manifest_document


def _require_exact_json_value(value: object, *, depth: int = 0) -> None:
    if depth > 32:
        raise QcGlobalInputSchemaError(
            "synthetic manifest nesting is too deep"
        )
    if value is None or type(value) in (str, int, bool):
        return
    if type(value) is list:
        for item in value:
            _require_exact_json_value(item, depth=depth + 1)
        return
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise QcGlobalInputSchemaError(
                "synthetic manifest keys must be exact strings"
            )
        for item in value.values():
            _require_exact_json_value(item, depth=depth + 1)
        return
    raise QcGlobalInputSchemaError(
        "synthetic manifest contains a noncanonical value"
    )


def _require_exact_manifest_document_contract(
    document: object,
    *,
    candidate: SyntheticQcRunCandidate,
    partitions: tuple[GlobalInputPartitionDescriptor, ...],
    manifest_id: str | None,
    manifest_sha256: str | None,
) -> None:
    if type(document) is not dict:
        raise QcGlobalInputSchemaError(
            "synthetic manifest root container changed"
        )
    _require_exact_json_value(document)
    encoded = _canonical_bytes(document)
    expected = _PINNED_MANIFEST_CONTRACT_DOCUMENT(
        candidate=candidate,
        partitions=partitions,
        manifest_id=manifest_id,
        manifest_sha256=manifest_sha256,
    )
    root_fixed_values = {
        "schema": "arv2-qc-global-input-manifest-v1",
        "status": STATUS,
        "authority": AUTHORITY,
        "algorithm_id": ALGORITHM_ID,
        "evaluation_id": EVALUATION_ID,
        "horizons_sessions": list(HORIZONS),
        "primary_horizon_sessions": PRIMARY_HORIZON,
        "terminal_payoff_reinvestment_policy_id": (
            TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID
        ),
        "manifest_id": manifest_id,
        "manifest_sha256": manifest_sha256,
    }
    if any(
        type(document.get(name)) is not type(value)
        or document.get(name) != value
        for name, value in root_fixed_values.items()
    ):
        raise QcGlobalInputSchemaError(
            "synthetic manifest root fixed value changed"
        )

    def require_section(name: str, value: dict[str, object]) -> None:
        actual = document.get(name)
        if (
            type(actual) is not dict
            or _canonical_bytes(actual) != _canonical_bytes(value)
        ):
            raise QcGlobalInputSchemaError(
                f"synthetic manifest {name} fixed contract changed"
            )

    require_section(
        "identity_recipe",
        {
            "manifest_sha256": (
                "sha256(canonical_compact_json_with_manifest_id_and_"
                "manifest_sha256_null)"
            ),
            "manifest_id": (
                "synthetic-arv2-qc-global-input-<first16_manifest_sha256>"
            ),
            "artifact_sha256": (
                "sha256(exact_rendered_manifest_bytes);held_in_the_in_memory_"
                "object_and_not_embedded_to_avoid_recursive_identity"
            ),
        },
    )
    require_section(
        "schema_binding",
        {
            "schema_id": SCHEMA_ID,
            "schema_sha256": SCHEMA_SHA256,
            "schema_artifact_sha256": SCHEMA_ARTIFACT_SHA256,
        },
    )
    require_section(
        "run_candidate_binding",
        {
            "candidate_id": candidate.candidate_id,
            "candidate_hash": candidate.candidate_hash,
            "declared_code_is_runtime_authenticated": False,
            "declared_partition_payloads_are_runtime_authenticated": False,
            "partition_rows_validated_against_row_contracts": False,
        },
    )
    require_section(
        "session_axis_binding",
        {
            "first_session": "2013-01-02",
            "last_session": "2026-08-28",
            "session_count": 3_435,
            "axis_sha256": (
                "b303555af32bda7d3f2caf6c43f3ae1c43723613086ab3dc848cfb86ab88d732"
            ),
            "partition_byte_count": 161_445,
            "partition_sha256": (
                "a4821282efee2048c31ea191fb3bc1c7cd1d854095b385a01cac2bcf69ca1de4"
            ),
        },
    )
    require_section(
        "partition_census",
        {
            "role_count": 7,
            "total_byte_count": sum(item.byte_count for item in partitions),
            "total_row_count": sum(item.row_count for item in partitions),
        },
    )
    require_section(
        "lineage",
        {
            "manifest_parents": [
                "global_input_schema",
                "synthetic_run_candidate",
            ],
            "ordered_partition_roles": list(ROLE_ORDER),
            "terminal_evidence_partition_roles": [
                "security_lifecycle_coverages",
                "terminal_requirements",
                "terminal_shareholder_payoffs",
            ],
            "production_truth_bound": False,
            "rights_bound": False,
            "operation_authority_bound": False,
        },
    )
    require_section(
        "transport",
        {
            "physical_transport": None,
            "qc_object_store_manifest_key": None,
            "qc_project_file_path": None,
            "lean_adapter": None,
        },
    )
    expected_descriptor_documents = [
        {
            "ordinal": descriptor.ordinal,
            "role": descriptor.role,
            "partition_id": descriptor.partition_id,
            "partition_schema": descriptor.partition_schema,
            "row_schema": descriptor.row_schema,
            "encoding": descriptor.encoding,
            "immutable_artifact_id": descriptor.immutable_artifact_id,
            "byte_count": descriptor.byte_count,
            "row_count": descriptor.row_count,
            "artifact_sha256": descriptor.artifact_sha256,
            "binding_sha256": descriptor.binding_sha256,
            "synthetic_fixture": descriptor.synthetic_fixture,
            "contains_licensed_rows": descriptor.contains_licensed_rows,
            "contains_real_outcomes": descriptor.contains_real_outcomes,
            "qc_object_store_key": descriptor.qc_object_store_key,
            "qc_project_file_path": descriptor.qc_project_file_path,
        }
        for descriptor in partitions
    ]
    declared_partitions = document.get("partitions")
    if (
        type(declared_partitions) is not list
        or len(declared_partitions) != len(partitions)
        or any(
            type(declared) is not dict
            or _canonical_bytes(declared)
            != _canonical_bytes(expected_descriptor)
            for declared, expected_descriptor in zip(
                declared_partitions,
                expected_descriptor_documents,
            )
        )
    ):
        raise QcGlobalInputSchemaError(
            "synthetic manifest partition projection changed"
        )
    external = document.get("external_bindings")
    capabilities = document.get("capabilities")
    if (
        type(external) is not dict
        or any(type(name) is not str for name in external)
        or tuple(external) != _EXTERNAL_BINDING_NAMES
        or any(external[name] is not None for name in _EXTERNAL_BINDING_NAMES)
        or type(capabilities) is not dict
        or any(type(name) is not str for name in capabilities)
        or tuple(capabilities) != _CAPABILITY_NAMES
        or any(capabilities[name] is not False for name in _CAPABILITY_NAMES)
    ):
        raise QcGlobalInputSchemaError(
            "synthetic manifest acquired an external authority"
        )
    if encoded != _canonical_bytes(expected):
        raise QcGlobalInputSchemaError(
            "synthetic manifest does not match its exact wire contract"
        )


def _copy_candidate(
    candidate: SyntheticQcRunCandidate,
) -> SyntheticQcRunCandidate:
    return build_synthetic_qc_run_candidate(
        code_files=tuple(
            CodeFileBinding(
                role=item.role,
                relative_path=item.relative_path,
                upload_name=item.upload_name,
                byte_count=item.byte_count,
                sha256=item.sha256,
            )
            for item in candidate.code_files
        ),
        synthetic_partitions=tuple(
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
            for item in candidate.synthetic_partitions
        ),
    )


_PINNED_COPY_CANDIDATE = _copy_candidate


def build_synthetic_qc_global_input_manifest(
    *, run_candidate: SyntheticQcRunCandidate
) -> SyntheticQcGlobalInputManifest:
    """Bind synthetic partition metadata without opening partition bytes."""

    row_contracts = _require_static_schema()
    try:
        require_synthetic_qc_run_candidate(run_candidate)
    except QcRunContractError as exc:
        raise QcGlobalInputSchemaError(
            "run candidate is not authenticated"
        ) from exc
    for partition in run_candidate.synthetic_partitions:
        _require_safe_id(partition.partition_id, "partition_id")
    try:
        candidate = _copy_candidate(run_candidate)
    except QcRunContractError as exc:
        raise QcGlobalInputSchemaError(
            "run candidate changed during reconstruction"
        ) from exc
    if (
        candidate.candidate_id != run_candidate.candidate_id
        or candidate.candidate_hash != run_candidate.candidate_hash
        or candidate.code_files != run_candidate.code_files
        or candidate.synthetic_partitions
        != run_candidate.synthetic_partitions
        or candidate.external_bindings != run_candidate.external_bindings
        or candidate.capabilities != run_candidate.capabilities
        or candidate._canonical_document != run_candidate._canonical_document
    ):
        raise QcGlobalInputSchemaError(
            "run candidate changed during reconstruction"
        )
    if (
        type(candidate.code_files) is not tuple
        or len(candidate.code_files) != 1
    ):
        raise QcGlobalInputSchemaError(
            "exactly one accepted event-study code file is required"
        )
    code = candidate.code_files[0]
    if (
        type(code) is not CodeFileBinding
        or type(code.role) is not str
        or type(code.relative_path) is not str
        or type(code.upload_name) is not str
        or type(code.byte_count) is not int
        or type(code.sha256) is not str
        or (
            code.role,
            code.relative_path,
            code.upload_name,
            code.byte_count,
            code.sha256,
        )
        != (
            "event_study_core",
            CORE_RELATIVE_PATH,
            CORE_UPLOAD_NAME,
            EVENT_STUDY_SOURCE_BYTE_COUNT,
            EVENT_STUDY_SOURCE_SHA256,
        )
    ):
        raise QcGlobalInputSchemaError(
            "run candidate does not bind the accepted v2 core"
        )
    by_role = {item.role: item for item in candidate.synthetic_partitions}
    if set(by_role) != set(ROLE_ORDER) or len(by_role) != len(ROLE_ORDER):
        raise QcGlobalInputSchemaError(
            "partition roles are not complete and exact"
        )
    axis = by_role["session_axis"]
    if (
        type(axis.byte_count) is not int
        or type(axis.row_count) is not int
        or type(axis.sha256) is not str
        or (axis.byte_count, axis.row_count, axis.sha256)
        != (
            SESSION_AXIS_PARTITION_BYTE_COUNT,
            REVIEWED_AXIS_SESSION_COUNT,
            SESSION_AXIS_PARTITION_SHA256,
        )
    ):
        raise QcGlobalInputSchemaError(
            "session-axis partition is not the exact reviewed axis"
        )
    descriptors = tuple(
        _build_descriptor(
            ordinal=index,
            partition=by_role[role],
            row=row_contracts[index - 1],
            run_candidate_hash=candidate.candidate_hash,
        )
        for index, role in enumerate(ROLE_ORDER, start=1)
    )
    for index, (descriptor, role, row) in enumerate(
        zip(descriptors, ROLE_ORDER, row_contracts),
        start=1,
    ):
        _validate_descriptor(descriptor)
        _require_descriptor_matches_inputs(
            descriptor,
            ordinal=index,
            partition=by_role[role],
            row=row,
            run_candidate_hash=candidate.candidate_hash,
        )
    seed = _manifest_document(
        candidate=candidate,
        partitions=descriptors,
        manifest_id=None,
        manifest_sha256=None,
    )
    _require_exact_manifest_document_contract(
        seed,
        candidate=candidate,
        partitions=descriptors,
        manifest_id=None,
        manifest_sha256=None,
    )
    digest = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
    manifest_id = f"synthetic-arv2-qc-global-input-{digest[:16]}"
    document = _manifest_document(
        candidate=candidate,
        partitions=descriptors,
        manifest_id=manifest_id,
        manifest_sha256=digest,
    )
    _require_exact_manifest_document_contract(
        document,
        candidate=candidate,
        partitions=descriptors,
        manifest_id=manifest_id,
        manifest_sha256=digest,
    )
    canonical_document = _render_bytes(document)
    if len(canonical_document) > MAX_SYNTHETIC_MANIFEST_BYTES:
        raise QcGlobalInputSchemaError(
            "synthetic manifest payload is too large"
        )
    return SyntheticQcGlobalInputManifest(
        manifest_id=manifest_id,
        manifest_sha256=digest,
        manifest_artifact_sha256=hashlib.sha256(
            canonical_document
        ).hexdigest(),
        schema_id=SCHEMA_ID,
        schema_sha256=SCHEMA_SHA256,
        schema_artifact_sha256=SCHEMA_ARTIFACT_SHA256,
        run_candidate_id=candidate.candidate_id,
        run_candidate_hash=candidate.candidate_hash,
        partitions=descriptors,
        total_byte_count=sum(item.byte_count for item in descriptors),
        total_row_count=sum(item.row_count for item in descriptors),
        external_bindings=tuple(
            (name, None) for name in _EXTERNAL_BINDING_NAMES
        ),
        capabilities=tuple((name, False) for name in _CAPABILITY_NAMES),
        _run_candidate=candidate,
        _canonical_document=canonical_document,
    )


def require_synthetic_qc_global_input_manifest(
    manifest: SyntheticQcGlobalInputManifest,
) -> SyntheticQcGlobalInputManifest:
    """Rebuild a manifest and refuse mutation or synthetic promotion."""

    _require_static_schema()
    if type(manifest) is not SyntheticQcGlobalInputManifest:
        raise QcGlobalInputSchemaError(
            "manifest was not built by this schema"
        )
    for name in (
        "manifest_id",
        "manifest_sha256",
        "manifest_artifact_sha256",
        "schema_id",
        "schema_sha256",
        "schema_artifact_sha256",
        "run_candidate_id",
        "run_candidate_hash",
    ):
        if type(getattr(manifest, name)) is not str:
            raise QcGlobalInputSchemaError("manifest scalar type changed")
    _require_sha256(manifest.manifest_sha256, "manifest_sha256")
    _require_sha256(
        manifest.manifest_artifact_sha256,
        "manifest_artifact_sha256",
    )
    _require_sha256(manifest.schema_sha256, "schema_sha256")
    _require_sha256(
        manifest.schema_artifact_sha256,
        "schema_artifact_sha256",
    )
    _require_sha256(manifest.run_candidate_hash, "run_candidate_hash")
    if (
        manifest.schema_id != SCHEMA_ID
        or manifest.schema_sha256 != SCHEMA_SHA256
        or manifest.schema_artifact_sha256 != SCHEMA_ARTIFACT_SHA256
    ):
        raise QcGlobalInputSchemaError("manifest schema identity changed")
    if type(manifest.partitions) is not tuple:
        raise QcGlobalInputSchemaError(
            "manifest partition container changed"
        )
    if any(
        type(item) is not GlobalInputPartitionDescriptor
        for item in manifest.partitions
    ):
        raise QcGlobalInputSchemaError("partition descriptor type changed")
    for item in manifest.partitions:
        _validate_descriptor(item)
    if (
        len(manifest.partitions) != len(ROLE_ORDER)
        or tuple(item.role for item in manifest.partitions) != ROLE_ORDER
        or tuple(item.ordinal for item in manifest.partitions)
        != tuple(range(1, len(ROLE_ORDER) + 1))
    ):
        raise QcGlobalInputSchemaError(
            "manifest partition role/order inventory is not complete"
        )
    if (
        type(manifest.total_byte_count) is not int
        or type(manifest.total_row_count) is not int
        or type(manifest.external_bindings) is not tuple
        or type(manifest.capabilities) is not tuple
        or type(manifest._run_candidate) is not SyntheticQcRunCandidate
        or type(manifest._canonical_document) is not bytes
    ):
        raise QcGlobalInputSchemaError(
            "manifest container or count type changed"
        )
    if len(manifest._canonical_document) > MAX_SYNTHETIC_MANIFEST_BYTES:
        raise QcGlobalInputSchemaError(
            "synthetic manifest payload is too large"
        )
    if (
        hashlib.sha256(manifest._canonical_document).hexdigest()
        != manifest.manifest_artifact_sha256
    ):
        raise QcGlobalInputSchemaError(
            "manifest artifact identity changed"
        )
    if (
        manifest.total_byte_count
        != sum(item.byte_count for item in manifest.partitions)
        or manifest.total_row_count
        != sum(item.row_count for item in manifest.partitions)
    ):
        raise QcGlobalInputSchemaError("manifest partition census changed")
    expected_external = tuple(
        (name, None) for name in _EXTERNAL_BINDING_NAMES
    )
    expected_capabilities = tuple(
        (name, False) for name in _CAPABILITY_NAMES
    )
    if (
        any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or item[1] is not None
            for item in manifest.external_bindings
        )
        or manifest.external_bindings != expected_external
    ):
        raise QcGlobalInputSchemaError(
            "manifest acquired an external binding"
        )
    if (
        any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or item[1] is not False
            for item in manifest.capabilities
        )
        or manifest.capabilities != expected_capabilities
    ):
        raise QcGlobalInputSchemaError(
            "manifest acquired an action capability"
        )
    try:
        rebuilt = build_synthetic_qc_global_input_manifest(
            run_candidate=manifest._run_candidate
        )
    except (QcGlobalInputSchemaError, QcRunContractError) as exc:
        raise QcGlobalInputSchemaError(
            "manifest run candidate changed"
        ) from exc
    if (
        manifest.manifest_id != rebuilt.manifest_id
        or manifest.manifest_sha256 != rebuilt.manifest_sha256
        or manifest.manifest_artifact_sha256
        != rebuilt.manifest_artifact_sha256
        or manifest.schema_id != rebuilt.schema_id
        or manifest.schema_sha256 != rebuilt.schema_sha256
        or manifest.schema_artifact_sha256
        != rebuilt.schema_artifact_sha256
        or manifest.run_candidate_id != rebuilt.run_candidate_id
        or manifest.run_candidate_hash != rebuilt.run_candidate_hash
        or manifest.total_byte_count != rebuilt.total_byte_count
        or manifest.total_row_count != rebuilt.total_row_count
        or _canonical_bytes(
            [_descriptor_document(item) for item in manifest.partitions]
        )
        != _canonical_bytes(
            [_descriptor_document(item) for item in rebuilt.partitions]
        )
        or manifest._canonical_document != rebuilt._canonical_document
    ):
        raise QcGlobalInputSchemaError(
            "manifest changed after construction"
        )
    return manifest


def render_synthetic_qc_global_input_manifest_bytes(
    manifest: SyntheticQcGlobalInputManifest,
) -> bytes:
    """Render canonical synthetic metadata, never partition rows."""

    require_synthetic_qc_global_input_manifest(manifest)
    return bytes(manifest._canonical_document)


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise QcGlobalInputSchemaError(
                "synthetic manifest contains a duplicate key"
            )
        result[key] = value
    return result


def _reject_float(_: str) -> object:
    raise QcGlobalInputSchemaError(
        "synthetic manifest numbers must be exact integers"
    )


def load_synthetic_qc_global_input_manifest_bytes(
    payload: bytes,
    *,
    run_candidate: SyntheticQcRunCandidate,
) -> SyntheticQcGlobalInputManifest:
    """Validate caller-supplied canonical synthetic metadata in memory."""

    _require_static_schema()
    if type(payload) is not bytes:
        raise QcGlobalInputSchemaError(
            "synthetic manifest payload must be exact bytes"
        )
    if len(payload) > MAX_SYNTHETIC_MANIFEST_BYTES:
        raise QcGlobalInputSchemaError(
            "synthetic manifest payload is too large"
        )
    if (
        payload.startswith(b"\xef\xbb\xbf")
        or not payload.endswith(b"\n")
        or payload.count(b"\n") != 1
        or b"\r" in payload
    ):
        raise QcGlobalInputSchemaError(
            "synthetic manifest must be strict UTF-8 canonical JSON with one LF"
        )
    try:
        text = payload[:-1].decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except QcGlobalInputSchemaError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        TypeError,
        RecursionError,
    ) as exc:
        raise QcGlobalInputSchemaError(
            "synthetic manifest is not valid canonical JSON"
        ) from exc
    if type(value) is not dict or _render_bytes(value) != payload:
        raise QcGlobalInputSchemaError(
            "synthetic manifest bytes are not canonical"
        )
    expected = build_synthetic_qc_global_input_manifest(
        run_candidate=run_candidate
    )
    if payload != render_synthetic_qc_global_input_manifest_bytes(expected):
        raise QcGlobalInputSchemaError(
            "synthetic manifest fields or candidate binding do not equal the "
            "authenticated declaration"
        )
    return expected
