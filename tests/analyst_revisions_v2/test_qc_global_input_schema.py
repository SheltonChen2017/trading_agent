from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import global_input_schema as schema_module
from research.analyst_revisions_v2_qc.event_study import (
    BENCHMARK_LISTING_ID,
    BENCHMARK_SECURITY_ID,
    BENCHMARK_TICKER,
    BENCHMARK_TOTAL_RETURN_SERIES_ID,
    SYNTHETIC_LIFECYCLE_SOURCE,
    SYNTHETIC_OPEN_SOURCE,
    SYNTHETIC_TERMINAL_SOURCE,
    SYNTHETIC_TERMINAL_VALUE_BASIS,
    SYNTHETIC_TOTAL_RETURN_VALUE_BASIS,
    BenchmarkOpenValue,
    DecisionRow,
    SecurityOpenValue,
    SecurityLifecycleCoverage,
    TerminalLifecycle,
    TerminalRequirement,
    TerminalShareholderPayoff,
    build_synthetic_partition_binding,
)
from research.analyst_revisions_v2_qc.global_input_schema import (
    GlobalInputPartitionDescriptor,
    MANIFEST_NESTED_FIELD_INVENTORIES,
    MANIFEST_ROOT_FIELDS,
    MANIFEST_ROOT_WIRE_TYPES,
    MAX_SAFE_ID_CHARS,
    MAX_SYNTHETIC_MANIFEST_BYTES,
    PARTITION_BINDING_HASH_DOMAIN,
    PARTITION_DESCRIPTOR_FIELDS,
    PARTITION_DESCRIPTOR_WIRE_TYPES,
    PARTITION_IMMUTABLE_ID_RECIPE,
    QcGlobalInputSchemaError,
    ROLE_ORDER,
    ROW_CONTRACTS,
    EVENT_STUDY_SOURCE_BYTE_COUNT,
    EVENT_STUDY_SOURCE_SHA256,
    RUN_CONTRACT_SOURCE_BYTE_COUNT,
    RUN_CONTRACT_SOURCE_SHA256,
    SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID,
    SCHEMA_SHA256,
    TERMINAL_EVENT_KINDS,
    TERMINAL_LIFECYCLE_FIELDS,
    TERMINAL_LIFECYCLE_WIRE_TYPES,
    SyntheticQcGlobalInputManifest,
    build_synthetic_qc_global_input_manifest,
    load_synthetic_qc_global_input_manifest_bytes,
    render_qc_global_input_schema_bytes,
    render_synthetic_qc_global_input_manifest_bytes,
    require_synthetic_qc_global_input_manifest,
)
from research.analyst_revisions_v2_qc.run_contract import (
    CORE_RELATIVE_PATH,
    CORE_UPLOAD_NAME,
    CodeFileBinding,
    QcRunContractError,
    SyntheticQcRunCandidate,
    build_synthetic_qc_run_candidate,
    canonical_lf_python_source_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "research/analyst_revisions_v2_qc/global_input_schema.py"
CORE = ROOT / CORE_RELATIVE_PATH
RUN_CONTRACT = ROOT / "research/analyst_revisions_v2_qc/run_contract.py"

EXPECTED_ROLES = (
    "session_axis",
    "decision_rows",
    "security_open_values",
    "benchmark_open_values",
    "security_lifecycle_coverages",
    "terminal_requirements",
    "terminal_shareholder_payoffs",
)


def _core_binding(**changes: object) -> CodeFileBinding:
    payload = canonical_lf_python_source_bytes(CORE.read_bytes())
    values: dict[str, object] = {
        "role": "event_study_core",
        "relative_path": CORE_RELATIVE_PATH,
        "upload_name": CORE_UPLOAD_NAME,
        "byte_count": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    values.update(changes)
    return CodeFileBinding(**values)


def _reviewed_axis() -> tuple[date, ...]:
    return trading_sessions(date(2013, 1, 2), date(2026, 8, 28))


def _nonempty_role_rows() -> dict[str, tuple]:
    decision_session = date(2021, 1, 4)
    terminal_session = date(2021, 1, 5)
    source_hash = "1" * 64
    decision = DecisionRow(
        row_id="decision-acme-2021-01-04",
        decision_session=decision_session,
        security_id="security-acme",
        listing_id="listing-acme",
        historical_ticker="ACME",
        evaluation_segment_id="arv2-wf-test-2021",
        fold_id="arv2-wf-test-2021",
        firm_specific_score=Decimal("0.25"),
        global_score=Decimal("-0.10"),
        common_event_component_id="component-acme-2021-01-04",
        input_row_sha256="2" * 64,
    )
    lifecycle = TerminalLifecycle(
        security_id="security-acme",
        terminal_listing_id="listing-acme",
        terminal_historical_ticker="ACME",
        terminal_session=terminal_session,
        event_kind="bankruptcy",
        successor_security_id=None,
        successor_listing_id=None,
        successor_historical_ticker=None,
        total_return_series_id="series-acme",
    )
    requirement = TerminalRequirement(
        decision_row_id=decision.row_id,
        security_id="security-acme",
        terminal_listing_id="listing-acme",
        terminal_historical_ticker="ACME",
        terminal_session=terminal_session,
        requirement_id="requirement-acme-2021-01-05",
        event_kind="bankruptcy",
        successor_security_id=None,
        successor_listing_id=None,
        successor_historical_ticker=None,
        total_return_series_id="series-acme",
    )
    return {
        "decision_rows": (decision,),
        "security_open_values": (
            SecurityOpenValue(
                session=decision_session,
                security_id="security-acme",
                listing_id="listing-acme",
                historical_ticker="ACME",
                total_return_open_value=Decimal("100"),
                total_return_series_id="series-acme",
                value_basis=SYNTHETIC_TOTAL_RETURN_VALUE_BASIS,
                source_role=SYNTHETIC_OPEN_SOURCE,
                source_sha256=source_hash,
            ),
        ),
        "benchmark_open_values": (
            BenchmarkOpenValue(
                session=decision_session,
                security_id=BENCHMARK_SECURITY_ID,
                listing_id=BENCHMARK_LISTING_ID,
                historical_ticker=BENCHMARK_TICKER,
                total_return_open_value=Decimal("400"),
                total_return_series_id=BENCHMARK_TOTAL_RETURN_SERIES_ID,
                value_basis=SYNTHETIC_TOTAL_RETURN_VALUE_BASIS,
                source_role=SYNTHETIC_OPEN_SOURCE,
                source_sha256=source_hash,
            ),
        ),
        "security_lifecycle_coverages": (
            SecurityLifecycleCoverage(
                security_id="security-acme",
                observed_through_session=date(2026, 8, 28),
                terminal_lifecycle=lifecycle,
                source_role=SYNTHETIC_LIFECYCLE_SOURCE,
                source_sha256="3" * 64,
            ),
        ),
        "terminal_requirements": (requirement,),
        "terminal_shareholder_payoffs": (
            TerminalShareholderPayoff(
                decision_row_id=decision.row_id,
                security_id="security-acme",
                terminal_listing_id="listing-acme",
                terminal_historical_ticker="ACME",
                terminal_session=terminal_session,
                valuation_session=terminal_session,
                valuation_security_id="security-acme",
                valuation_listing_id="listing-acme",
                valuation_historical_ticker="ACME",
                terminal_total_return_index_value=Decimal("5"),
                total_return_series_id="series-acme",
                value_basis=SYNTHETIC_TERMINAL_VALUE_BASIS,
                requirement_id=requirement.requirement_id,
                event_kind="bankruptcy",
                successor_security_id=None,
                successor_listing_id=None,
                successor_historical_ticker=None,
                source_role=SYNTHETIC_TERMINAL_SOURCE,
                source_sha256="4" * 64,
            ),
        ),
    }


def _candidate(
    *,
    code_binding: CodeFileBinding | None = None,
    role_rows: dict[str, tuple] | None = None,
    partition_ids: dict[str, str] | None = None,
) -> SyntheticQcRunCandidate:
    rows = {role: () for role in EXPECTED_ROLES}
    rows["session_axis"] = _reviewed_axis()
    if role_rows:
        rows.update(role_rows)
    partitions = tuple(
        build_synthetic_partition_binding(
            role=role,
            partition_id=(
                (partition_ids or {}).get(role)
                or f"fixture/{index:02d}-{role.replace('_', '-')}.jsonl"
            ),
            rows=rows[role],
        )
        for index, role in enumerate(EXPECTED_ROLES)
    )
    return build_synthetic_qc_run_candidate(
        code_files=(code_binding or _core_binding(),),
        synthetic_partitions=partitions,
    )


def _manifest() -> SyntheticQcGlobalInputManifest:
    return build_synthetic_qc_global_input_manifest(run_candidate=_candidate())


def _render_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _decoded_manifest() -> dict[str, object]:
    value = json.loads(
        render_synthetic_qc_global_input_manifest_bytes(_manifest())
    )
    assert type(value) is dict
    return value


def _replace_manifest(**changes: object) -> SyntheticQcGlobalInputManifest:
    return dataclasses.replace(_manifest(), **changes)


def _replace_partition(
    index: int, **changes: object
) -> SyntheticQcGlobalInputManifest:
    manifest = _manifest()
    partitions = list(manifest.partitions)
    partitions[index] = dataclasses.replace(partitions[index], **changes)
    return dataclasses.replace(manifest, partitions=tuple(partitions))


def test_role_order_is_the_exact_event_study_input_inventory():
    assert type(ROLE_ORDER) is tuple
    assert ROLE_ORDER == EXPECTED_ROLES
    assert len(ROLE_ORDER) == len(set(ROLE_ORDER)) == 7


def test_row_contracts_pin_every_role_and_exact_event_study_fields():
    assert type(ROW_CONTRACTS) is tuple
    assert tuple(item.role for item in ROW_CONTRACTS) == EXPECTED_ROLES
    expected = {
        "session_axis": ("session",),
        "decision_rows": tuple(field.name for field in dataclasses.fields(DecisionRow)),
        "security_open_values": tuple(
            field.name for field in dataclasses.fields(SecurityOpenValue)
        ),
        "benchmark_open_values": tuple(
            field.name for field in dataclasses.fields(BenchmarkOpenValue)
        ),
        "security_lifecycle_coverages": tuple(
            field.name for field in dataclasses.fields(SecurityLifecycleCoverage)
        ),
        "terminal_requirements": tuple(
            field.name for field in dataclasses.fields(TerminalRequirement)
        ),
        "terminal_shareholder_payoffs": tuple(
            field.name for field in dataclasses.fields(TerminalShareholderPayoff)
        ),
    }
    assert {item.role: item.fields for item in ROW_CONTRACTS} == expected


def test_row_contracts_pin_exact_wire_envelopes_types_and_ordering():
    expected_envelopes = {
        "session_axis": "$object",
        "decision_rows": "$dataclass:DecisionRow/$fields",
        "security_open_values": "$dataclass:SecurityOpenValue/$fields",
        "benchmark_open_values": "$dataclass:BenchmarkOpenValue/$fields",
        "security_lifecycle_coverages": (
            "$dataclass:SecurityLifecycleCoverage/$fields"
        ),
        "terminal_requirements": "$dataclass:TerminalRequirement/$fields",
        "terminal_shareholder_payoffs": (
            "$dataclass:TerminalShareholderPayoff/$fields"
        ),
    }
    expected_wire_types = {
        "session_axis": ("date_tag",),
        "decision_rows": (
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
        "security_open_values": (
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
        "benchmark_open_values": (
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
        "security_lifecycle_coverages": (
            "string",
            "date_tag",
            "terminal_lifecycle_dataclass_or_null",
            "string",
            "lowercase_sha256_string",
        ),
        "terminal_requirements": (
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
        "terminal_shareholder_payoffs": (
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
    }
    assert {item.role: item.root_envelope for item in ROW_CONTRACTS} == (
        expected_envelopes
    )
    assert {item.role: item.wire_types for item in ROW_CONTRACTS} == (
        expected_wire_types
    )
    for item in ROW_CONTRACTS:
        assert len(item.fields) == len(item.wire_types)
        assert type(item.canonical_order) is tuple
        assert set(item.canonical_order) <= set(item.fields)


def test_nested_terminal_lifecycle_and_event_kinds_are_exact():
    assert TERMINAL_LIFECYCLE_FIELDS == tuple(
        field.name for field in dataclasses.fields(TerminalLifecycle)
    )
    assert TERMINAL_LIFECYCLE_WIRE_TYPES == (
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
    assert len(TERMINAL_LIFECYCLE_FIELDS) == len(
        TERMINAL_LIFECYCLE_WIRE_TYPES
    )
    assert TERMINAL_EVENT_KINDS == (
        "delisting",
        "bankruptcy",
        "cash_merger",
        "stock_merger",
        "mixed_merger",
    )


def test_manifest_and_descriptor_wire_contracts_are_exact_and_self_describing():
    expected_manifest_fields = (
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
    expected_descriptor_fields = tuple(
        field.name for field in dataclasses.fields(GlobalInputPartitionDescriptor)
    )
    assert MANIFEST_ROOT_FIELDS == expected_manifest_fields
    assert len(MANIFEST_ROOT_FIELDS) == len(MANIFEST_ROOT_WIRE_TYPES)
    assert PARTITION_DESCRIPTOR_FIELDS == expected_descriptor_fields
    assert len(PARTITION_DESCRIPTOR_FIELDS) == len(
        PARTITION_DESCRIPTOR_WIRE_TYPES
    )
    assert MAX_SYNTHETIC_MANIFEST_BYTES == 1_048_576
    assert MAX_SAFE_ID_CHARS == 512
    assert PARTITION_BINDING_HASH_DOMAIN == (
        "arv2-qc-global-input-partition-binding-v1"
    )
    assert PARTITION_IMMUTABLE_ID_RECIPE == (
        "synthetic-arv2-global-input-<hyphenated-role>-<binding_sha256>"
    )
    schema = json.loads(render_qc_global_input_schema_bytes())
    contract = schema["synthetic_manifest_wire_contract"]
    assert contract["fields"] == list(MANIFEST_ROOT_FIELDS)
    assert contract["wire_types"] == list(MANIFEST_ROOT_WIRE_TYPES)
    assert contract["root_fixed_values"] == {
        "schema": "arv2-qc-global-input-manifest-v1",
        "status": (
            "synthetic_fixture_only_production_shaped_schema_not_production_truth"
        ),
        "authority": (
            "schema_and_synthetic_metadata_only_no_input_qc_outcome_result_or_"
            "trading_authority"
        ),
        "algorithm_id": "arv2-qc-stock-event-study-core-v2",
        "evaluation_id": "arv2-eval-stock-historical-qc-001",
        "horizons_sessions": [1, 5, 20, 60],
        "primary_horizon_sessions": 20,
        "terminal_payoff_reinvestment_policy_id": (
            "arv2-terminal-payoff-benchmark-splice-v1"
        ),
    }
    assert contract["maximum_rendered_byte_count"] == (
        MAX_SYNTHETIC_MANIFEST_BYTES
    )
    assert contract["nested_field_inventories"] == {
        name: list(fields) for name, fields in MANIFEST_NESTED_FIELD_INVENTORIES
    }
    nested = contract["nested_value_contracts"]
    assert nested["run_candidate_binding"]["fixed_values"] == {
        "declared_code_is_runtime_authenticated": False,
        "declared_partition_payloads_are_runtime_authenticated": False,
        "partition_rows_validated_against_row_contracts": False,
    }
    assert nested["lineage"]["fixed_values"] == {
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
    }
    assert nested["transport"]["fixed_values"] == {
        "physical_transport": None,
        "qc_object_store_manifest_key": None,
        "qc_project_file_path": None,
        "lean_adapter": None,
    }
    assert nested["external_bindings"] == {
        "exact_keys": list(schema_module._EXTERNAL_BINDING_NAMES),
        "all_values": "null",
    }
    assert nested["capabilities"] == {
        "exact_keys": list(schema_module._CAPABILITY_NAMES),
        "all_values": "boolean_false",
    }
    assert contract["partition_descriptor"] == {
        "root_envelope": "json_object",
        "fields": list(PARTITION_DESCRIPTOR_FIELDS),
        "wire_types": list(PARTITION_DESCRIPTOR_WIRE_TYPES),
        "fixed_values": {
            "encoding": "canonical_tagged_jsonl_strict_utf8_lf-v1",
            "synthetic_fixture": True,
            "contains_licensed_rows": False,
            "contains_real_outcomes": False,
            "qc_object_store_key": None,
            "qc_project_file_path": None,
        },
        "derived_values": {
            "ordinal": "one_based_position_in_role_order",
            "role": "role_order_at_ordinal",
            "partition_id": "run_candidate_partition_id_for_role",
            "partition_schema": "run_candidate_partition_schema_for_role",
            "row_schema": "row_contract_schema_for_role",
            "immutable_artifact_id": "immutable_artifact_id_recipe",
            "byte_count": "run_candidate_partition_byte_count_for_role",
            "row_count": "run_candidate_partition_row_count_for_role",
            "artifact_sha256": "run_candidate_partition_sha256_for_role",
            "binding_sha256": "binding_hash_recipe",
        },
        "binding_hash_domain": PARTITION_BINDING_HASH_DOMAIN,
        "binding_hash_recipe": (
            "sha256(canonical_json_of_domain_schema_hash_candidate_hash_and_"
            "descriptor_with_identity_fields_null)"
        ),
        "immutable_artifact_id_recipe": PARTITION_IMMUTABLE_ID_RECIPE,
        "safe_id_contract": {
            "maximum_characters": 512,
            "first_character": "ascii_alphanumeric",
            "remaining_characters": (
                "ascii_alphanumeric_dot_underscore_slash_hyphen"
            ),
            "absolute_or_trailing_slash_allowed": False,
            "empty_dot_or_dotdot_path_segment_allowed": False,
        },
    }
    assert schema["partition_schemas"] == {
        "session_axis": "arv2-synthetic-session_axis-v1",
        "decision_rows": "arv2-synthetic-decision_rows-v1",
        "security_open_values": "arv2-synthetic-security_open_values-v1",
        "benchmark_open_values": "arv2-synthetic-benchmark_open_values-v1",
        "security_lifecycle_coverages": (
            "arv2-synthetic-security_lifecycle_coverages-v1"
        ),
        "terminal_requirements": "arv2-synthetic-terminal_requirements-v1",
        "terminal_shareholder_payoffs": (
            "arv2-synthetic-terminal_shareholder_payoffs-v1"
        ),
    }
    manifest = _decoded_manifest()
    assert set(manifest) == set(MANIFEST_ROOT_FIELDS)
    for name, fields in MANIFEST_NESTED_FIELD_INVENTORIES:
        assert set(manifest[name]) == set(fields)
        assert len(manifest[name]) == len(fields)
    assert set(manifest["partitions"][0]) == set(PARTITION_DESCRIPTOR_FIELDS)


@pytest.mark.parametrize(
    ("path", "byte_count", "digest"),
    [
        (
            RUN_CONTRACT,
            RUN_CONTRACT_SOURCE_BYTE_COUNT,
            RUN_CONTRACT_SOURCE_SHA256,
        ),
        (CORE, EVENT_STUDY_SOURCE_BYTE_COUNT, EVENT_STUDY_SOURCE_SHA256),
    ],
)
def test_accepted_python_sources_match_cross_checkout_canonical_lf_pins(
    path, byte_count, digest
):
    payload = canonical_lf_python_source_bytes(path.read_bytes())
    assert len(payload) == byte_count
    assert hashlib.sha256(payload).hexdigest() == digest


def test_static_schema_bytes_are_content_addressed_canonical_and_stable():
    first = render_qc_global_input_schema_bytes()
    second = render_qc_global_input_schema_bytes()
    assert first == second
    assert first.endswith(b"\n")
    assert not first.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff"))
    document = json.loads(first)
    assert _render_json(document) == first
    assert hashlib.sha256(first).hexdigest() == SCHEMA_ARTIFACT_SHA256
    assert document["schema_id"] == SCHEMA_ID
    assert document["schema_sha256"] == SCHEMA_SHA256


def test_static_schema_hash_uses_null_identity_fields():
    document = json.loads(render_qc_global_input_schema_bytes())
    document["schema_id"] = None
    document["schema_sha256"] = None
    compact = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(compact).hexdigest() == SCHEMA_SHA256
    assert SCHEMA_ID.endswith(SCHEMA_SHA256[:16])


def test_schema_preserves_formal_2020_and_owner_directed_2021_geometry():
    payload = render_qc_global_input_schema_bytes()
    assert b"arv2-wf-test-2020" in payload
    assert b"arv2-wf-test-2021" in payload
    assert b"formal_primary" in payload
    assert b"owner_directed_post_pandemic_sensitivity" in payload


def test_schema_pins_the_full_reviewed_xnys_axis_and_corrected_estimator():
    payload = render_qc_global_input_schema_bytes()
    for value in (
        b"2013-01-02",
        b"2026-08-28",
        b"3435",
        b"b303555af32bda7d3f2caf6c43f3ae1c43723613086ab3dc848cfb86ab88d732",
        b"arv2-terminal-payoff-benchmark-splice-v1",
    ):
        assert value in payload


def test_schema_pins_pit_terminal_transport_and_lineage_hash_boundaries():
    document = json.loads(render_qc_global_input_schema_bytes())
    assert document["point_in_time_contract"] == {
        "vendor_calls_inside_backtest": False,
        "rating_semantics_inferred_inside_backtest": False,
        "current_ticker_resolution_inside_backtest": False,
        "timestamps_revised_inside_backtest": False,
        "decision_rows_require_upstream_effective_available_version_lineage": True,
        "manifest_self_assertion_proves_point_in_time": False,
    }
    assert document["authority_role_scopes"] == {
        "production_input_read_roles": ["session_axis", "decision_rows"],
        "real_outcome_read_roles": [
            "security_open_values",
            "benchmark_open_values",
            "security_lifecycle_coverages",
            "terminal_requirements",
            "terminal_shareholder_payoffs",
        ],
        "input_read_authority_implies_real_outcome_read_authority": False,
        "schema_or_manifest_identity_grants_either_authority": False,
    }
    assert document["terminal_contract"] == {
        "qc_delisting_price_is_total_shareholder_payoff": False,
        "terminal_date_alone_proves_economic_availability": False,
        "cash_bankruptcy_delisting_policy": (
            "proven_payoff_reinvested_in_spy_to_fixed_horizon"
        ),
        "stock_and_mixed_merger_policy": "successor_valued_at_fixed_horizon",
        "missing_or_ambiguous_evidence": "named_refusal_or_invalid_data",
    }
    assert document["transport_contract"] == {
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
            "sha256(canonical_json_of_explicit_domain_schema_hash_candidate_"
            "hash_and_role_descriptor_with_identity_fields_null)"
        ),
    }
    assert document["lineage_hash_contract"] == {
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
    }
    assert document["terminal_event_kinds"] == list(TERMINAL_EVENT_KINDS)
    assert document["nested_terminal_lifecycle_wire_contract"] == {
        "root_envelope": "$dataclass:TerminalLifecycle/$fields",
        "fields": list(TERMINAL_LIFECYCLE_FIELDS),
        "wire_types": list(TERMINAL_LIFECYCLE_WIRE_TYPES),
    }
    assert document["serialization"]["canonical_order_interpretation"] == {
        "direction": "ascending_by_the_declared_field_tuple",
        "null_order": "all_canonical_order_fields_are_non_null",
        "date_comparison": "chronological_equivalent_to_iso_yyyy_mm_dd",
        "string_comparison": (
            "exact_unicode_code_point_lexicographic_no_locale_or_casefold"
        ),
        "duplicate_ordering_key_allowed": False,
    }


def test_valid_manifest_derives_exactly_one_descriptor_for_each_partition():
    candidate = _candidate()
    manifest = build_synthetic_qc_global_input_manifest(run_candidate=candidate)
    assert require_synthetic_qc_global_input_manifest(manifest) is manifest
    assert type(manifest.partitions) is tuple
    assert tuple(item.role for item in manifest.partitions) == EXPECTED_ROLES
    assert all(
        type(item) is GlobalInputPartitionDescriptor
        for item in manifest.partitions
    )
    by_role = {item.role: item for item in candidate.synthetic_partitions}
    for descriptor in manifest.partitions:
        original = by_role[descriptor.role]
        assert descriptor.immutable_artifact_id == (
            "synthetic-arv2-global-input-"
            f"{descriptor.role.replace('_', '-')}-{descriptor.binding_sha256}"
        )
        assert (
            descriptor.partition_id,
            descriptor.partition_schema,
            descriptor.byte_count,
            descriptor.row_count,
            descriptor.artifact_sha256,
            descriptor.synthetic_fixture,
            descriptor.contains_licensed_rows,
            descriptor.contains_real_outcomes,
        ) == (
            original.partition_id,
            original.schema,
            original.byte_count,
            original.row_count,
            original.sha256,
            True,
            False,
            False,
        )


def test_full_axis_partition_is_not_reduced_to_the_2021_run_period():
    descriptor = _manifest().partitions[0]
    expected = build_synthetic_partition_binding(
        role="session_axis",
        partition_id="fixture/00-session-axis.jsonl",
        rows=_reviewed_axis(),
    )
    assert descriptor.row_count == 3435
    assert descriptor.byte_count == expected.byte_count == 161445
    assert descriptor.artifact_sha256 == expected.sha256


def test_production_shaped_nonempty_rows_bind_all_six_data_roles():
    manifest = build_synthetic_qc_global_input_manifest(
        run_candidate=_candidate(role_rows=_nonempty_role_rows())
    )
    assert require_synthetic_qc_global_input_manifest(manifest) is manifest
    assert manifest.partitions[0].row_count == 3435
    assert tuple(item.row_count for item in manifest.partitions[1:]) == (
        1,
        1,
        1,
        1,
        1,
        1,
    )


def test_one_row_change_rebinds_partition_candidate_and_manifest_identity():
    first_rows = _nonempty_role_rows()
    second_rows = dict(first_rows)
    decision = second_rows["decision_rows"][0]
    second_rows["decision_rows"] = (
        dataclasses.replace(decision, input_row_sha256="9" * 64),
    )
    first = build_synthetic_qc_global_input_manifest(
        run_candidate=_candidate(role_rows=first_rows)
    )
    second = build_synthetic_qc_global_input_manifest(
        run_candidate=_candidate(role_rows=second_rows)
    )
    assert first.partitions[1].artifact_sha256 != (
        second.partitions[1].artifact_sha256
    )
    assert first.partitions[1].binding_sha256 != (
        second.partitions[1].binding_sha256
    )
    assert first.run_candidate_hash != second.run_candidate_hash
    assert first.manifest_sha256 != second.manifest_sha256
    assert first.manifest_artifact_sha256 != second.manifest_artifact_sha256


def test_declared_nonaxis_metadata_is_not_misrepresented_as_payload_proof():
    candidate = _candidate()
    partitions = list(candidate.synthetic_partitions)
    partitions[1] = dataclasses.replace(
        partitions[1],
        byte_count=987_654,
        row_count=12_345,
        sha256="f" * 64,
    )
    declared = build_synthetic_qc_run_candidate(
        code_files=candidate.code_files,
        synthetic_partitions=tuple(partitions),
    )
    manifest = build_synthetic_qc_global_input_manifest(
        run_candidate=declared
    )
    assert manifest.partitions[1].byte_count == 987_654
    assert manifest.partitions[1].row_count == 12_345
    document = json.loads(
        render_synthetic_qc_global_input_manifest_bytes(manifest)
    )
    binding = document["run_candidate_binding"]
    assert binding["declared_partition_payloads_are_runtime_authenticated"] is False
    assert binding["partition_rows_validated_against_row_contracts"] is False


def test_builder_refuses_a_run_contract_id_that_cannot_round_trip():
    accepted = _candidate(partition_ids={"decision_rows": "a" * 512})
    assert build_synthetic_qc_global_input_manifest(
        run_candidate=accepted
    ).partitions[1].partition_id == "a" * 512
    candidate = _candidate(partition_ids={"decision_rows": "a" * 513})
    with pytest.raises(QcGlobalInputSchemaError, match="partition_id|unsafe"):
        build_synthetic_qc_global_input_manifest(run_candidate=candidate)


def test_partition_role_binding_hashes_are_domain_separated():
    descriptors = _manifest().partitions
    empty = [item for item in descriptors if item.row_count == 0]
    assert len({item.artifact_sha256 for item in empty}) == 1
    assert len({item.binding_sha256 for item in empty}) == len(empty)
    assert all(
        item.binding_sha256 != item.artifact_sha256 for item in descriptors
    )


def test_partition_binding_hash_binds_domain_schema_candidate_and_role():
    candidate = _candidate()
    manifest = build_synthetic_qc_global_input_manifest(run_candidate=candidate)
    by_role = {item.role: item for item in candidate.synthetic_partitions}
    for descriptor in manifest.partitions:
        partition = by_role[descriptor.role]
        seed = {
            "hash_domain": "arv2-qc-global-input-partition-binding-v1",
            "global_input_schema_sha256": SCHEMA_SHA256,
            "run_candidate_hash": candidate.candidate_hash,
            "ordinal": descriptor.ordinal,
            "role": descriptor.role,
            "partition_id": partition.partition_id,
            "partition_schema": partition.schema,
            "row_schema": descriptor.row_schema,
            "encoding": descriptor.encoding,
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
        assert descriptor.binding_sha256 == hashlib.sha256(
            json.dumps(
                seed,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()


def test_manifest_build_is_deterministic_for_equivalent_candidate_reconstruction():
    first = _manifest()
    second = build_synthetic_qc_global_input_manifest(run_candidate=_candidate())
    assert first.manifest_id == second.manifest_id
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.manifest_artifact_sha256 == second.manifest_artifact_sha256
    assert first.partitions == second.partitions
    assert render_synthetic_qc_global_input_manifest_bytes(first) == (
        render_synthetic_qc_global_input_manifest_bytes(second)
    )


def test_manifest_bytes_are_canonical_and_round_trip_with_exact_candidate():
    candidate = _candidate()
    manifest = build_synthetic_qc_global_input_manifest(run_candidate=candidate)
    payload = render_synthetic_qc_global_input_manifest_bytes(manifest)
    assert payload.endswith(b"\n")
    assert _render_json(json.loads(payload)) == payload
    assert hashlib.sha256(payload).hexdigest() == (
        manifest.manifest_artifact_sha256
    )
    assert manifest.schema_artifact_sha256 == SCHEMA_ARTIFACT_SHA256
    document = json.loads(payload)
    assert document["schema_binding"] == {
        "schema_id": SCHEMA_ID,
        "schema_sha256": SCHEMA_SHA256,
        "schema_artifact_sha256": SCHEMA_ARTIFACT_SHA256,
    }
    assert document["run_candidate_binding"] == {
        "candidate_id": candidate.candidate_id,
        "candidate_hash": candidate.candidate_hash,
        "declared_code_is_runtime_authenticated": False,
        "declared_partition_payloads_are_runtime_authenticated": False,
        "partition_rows_validated_against_row_contracts": False,
    }
    loaded = load_synthetic_qc_global_input_manifest_bytes(
        payload, run_candidate=candidate
    )
    assert require_synthetic_qc_global_input_manifest(loaded) is loaded
    assert loaded.manifest_id == manifest.manifest_id
    assert loaded.manifest_sha256 == manifest.manifest_sha256
    assert loaded.manifest_artifact_sha256 == (
        manifest.manifest_artifact_sha256
    )
    assert loaded.partitions == manifest.partitions
    assert render_synthetic_qc_global_input_manifest_bytes(loaded) == payload


def test_manifest_hash_uses_null_identity_fields():
    document = _decoded_manifest()
    declared = document["manifest_sha256"]
    assert declared == _manifest().manifest_sha256
    document["manifest_id"] = None
    document["manifest_sha256"] = None
    compact = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(compact).hexdigest() == declared


def test_manifest_counts_match_the_closed_partition_inventory():
    document = _decoded_manifest()
    assert len(document["partitions"]) == 7
    census = document["partition_census"]
    assert type(census) is dict
    assert census["role_count"] == len(EXPECTED_ROLES)
    assert census["total_row_count"] == sum(
        item.row_count for item in _manifest().partitions
    )
    assert census["total_byte_count"] == sum(
        item.byte_count for item in _manifest().partitions
    )


def test_builder_copies_caller_owned_candidate_state():
    candidate = _candidate()
    manifest = build_synthetic_qc_global_input_manifest(run_candidate=candidate)
    original_hash = manifest.manifest_sha256
    original_partition_hash = manifest.partitions[0].artifact_sha256
    object.__setattr__(
        candidate.synthetic_partitions[0], "sha256", "f" * 64
    )
    assert manifest.partitions[0].artifact_sha256 == original_partition_hash
    assert manifest.manifest_sha256 == original_hash
    assert require_synthetic_qc_global_input_manifest(manifest) is manifest


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("manifest_id", "wrong", "identity|manifest"),
        ("manifest_sha256", "f" * 64, "identity|changed|manifest"),
        (
            "manifest_artifact_sha256",
            "f" * 64,
            "artifact|identity|changed|manifest",
        ),
        ("schema_id", "wrong", "schema|identity|manifest|changed"),
        ("schema_sha256", "f" * 64, "schema|identity|manifest|changed"),
        (
            "schema_artifact_sha256",
            "f" * 64,
            "schema|artifact|identity|manifest|changed",
        ),
        ("_canonical_document", b"{}\n", "changed|canonical|manifest"),
    ],
)
def test_manifest_top_level_tampering_refuses(field, value, message):
    with pytest.raises(QcGlobalInputSchemaError, match=message):
        require_synthetic_qc_global_input_manifest(
            _replace_manifest(**{field: value})
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ordinal", 99),
        ("role", "security_open_values"),
        ("partition_id", "fixture/rebound.jsonl"),
        ("partition_schema", "arv2-synthetic-wrong-v1"),
        ("row_schema", "arv2-qc-global-input-wrong-v1"),
        ("encoding", "wrong-encoding"),
        ("immutable_artifact_id", "synthetic-rebound"),
        ("byte_count", 1),
        ("row_count", 1),
        ("artifact_sha256", "f" * 64),
        ("binding_sha256", "f" * 64),
        ("qc_object_store_key", "object-store/key"),
        ("qc_project_file_path", "project/file"),
    ],
)
def test_partition_descriptor_tampering_refuses(field, value):
    with pytest.raises(QcGlobalInputSchemaError, match="partition|binding|changed"):
        require_synthetic_qc_global_input_manifest(
            _replace_partition(1, **{field: value})
        )


def test_partition_reordering_refuses_even_when_all_descriptors_remain_present():
    manifest = _manifest()
    changed = dataclasses.replace(
        manifest, partitions=tuple(reversed(manifest.partitions))
    )
    with pytest.raises(QcGlobalInputSchemaError, match="order|partition|changed"):
        require_synthetic_qc_global_input_manifest(changed)


def test_partition_deletion_refuses():
    manifest = _manifest()
    with pytest.raises(
        QcGlobalInputSchemaError,
        match="partition|role|complete|manifest|changed",
    ):
        require_synthetic_qc_global_input_manifest(
            dataclasses.replace(manifest, partitions=manifest.partitions[:-1])
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("synthetic_fixture", False),
        ("contains_licensed_rows", True),
        ("contains_real_outcomes", True),
    ],
)
def test_only_synthetic_unlicensed_nonoutcome_metadata_is_admitted(field, value):
    with pytest.raises(
        QcGlobalInputSchemaError,
        match="synthetic|licensed|outcome|production",
    ):
        require_synthetic_qc_global_input_manifest(
            _replace_partition(1, **{field: value})
        )


def test_nonnull_external_binding_and_true_capability_refuse():
    manifest = _manifest()
    external = list(manifest.external_bindings)
    external[0] = (external[0][0], "claimed-authority")
    with pytest.raises(QcGlobalInputSchemaError, match="external|authority|binding"):
        require_synthetic_qc_global_input_manifest(
            dataclasses.replace(manifest, external_bindings=tuple(external))
        )
    capabilities = list(manifest.capabilities)
    capabilities[0] = (capabilities[0][0], True)
    with pytest.raises(QcGlobalInputSchemaError, match="capability|authority"):
        require_synthetic_qc_global_input_manifest(
            dataclasses.replace(manifest, capabilities=tuple(capabilities))
        )


def test_all_external_bindings_are_null_and_all_capabilities_false():
    manifest = _manifest()
    assert manifest.external_bindings
    assert manifest.capabilities
    assert all(value is None for _, value in manifest.external_bindings)
    assert all(value is False for _, value in manifest.capabilities)
    assert tuple(name for name, _ in manifest.external_bindings) == (
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
    assert tuple(name for name, _ in manifest.capabilities) == (
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


def test_wrong_core_code_hash_refuses_even_when_run_candidate_rehashes():
    candidate = _candidate(code_binding=_core_binding(sha256="f" * 64))
    with pytest.raises(QcGlobalInputSchemaError, match="code|core|source"):
        build_synthetic_qc_global_input_manifest(run_candidate=candidate)


def test_wrong_core_byte_count_refuses_even_when_run_candidate_rehashes():
    binding = _core_binding()
    candidate = _candidate(
        code_binding=dataclasses.replace(binding, byte_count=binding.byte_count + 1)
    )
    with pytest.raises(QcGlobalInputSchemaError, match="code|core|source"):
        build_synthetic_qc_global_input_manifest(run_candidate=candidate)


def test_wrong_session_axis_descriptor_refuses_even_when_candidate_rehashes():
    candidate = _candidate(role_rows={"session_axis": _reviewed_axis()[:-1]})
    with pytest.raises(QcGlobalInputSchemaError, match="axis|session"):
        build_synthetic_qc_global_input_manifest(run_candidate=candidate)


def test_tampered_candidate_identity_refuses():
    candidate = _candidate()
    object.__setattr__(candidate, "candidate_hash", "f" * 64)
    with pytest.raises(QcGlobalInputSchemaError, match="candidate|authenticated"):
        build_synthetic_qc_global_input_manifest(run_candidate=candidate)


def test_tampered_candidate_role_inventory_refuses():
    candidate = _candidate()
    object.__setattr__(
        candidate,
        "synthetic_partitions",
        candidate.synthetic_partitions[:-1],
    )
    with pytest.raises(QcGlobalInputSchemaError, match="candidate|partition|role"):
        build_synthetic_qc_global_input_manifest(run_candidate=candidate)


def test_candidate_reconstruction_errors_are_normalized(monkeypatch):
    def fail_reconstruction(candidate):
        raise QcRunContractError("simulated reconstruction race")

    monkeypatch.setattr(schema_module, "_copy_candidate", fail_reconstruction)
    monkeypatch.setattr(
        schema_module,
        "_PINNED_COPY_CANDIDATE",
        fail_reconstruction,
    )
    with pytest.raises(
        QcGlobalInputSchemaError,
        match="candidate.*reconstruction|reconstruction.*candidate",
    ):
        build_synthetic_qc_global_input_manifest(run_candidate=_candidate())


def test_candidate_reconstruction_cannot_substitute_another_candidate(
    monkeypatch,
):
    alternate = _candidate(
        partition_ids={
            "decision_rows": "fixture/alternate-decision-rows.jsonl"
        }
    )

    def substitute_candidate(candidate):
        return alternate

    monkeypatch.setattr(schema_module, "_copy_candidate", substitute_candidate)
    monkeypatch.setattr(
        schema_module,
        "_PINNED_COPY_CANDIDATE",
        substitute_candidate,
    )
    with pytest.raises(QcGlobalInputSchemaError, match="reconstruction"):
        build_synthetic_qc_global_input_manifest(run_candidate=_candidate())


def test_hostile_candidate_scalar_is_refused_before_comparison_dispatch():
    calls: list[str] = []

    class HostileText(str):
        def __eq__(self, other):
            calls.append("eq")
            raise AssertionError("hostile comparison executed")

        def __hash__(self):
            return str.__hash__(self)

    candidate = _candidate()
    object.__setattr__(
        candidate,
        "candidate_hash",
        HostileText(candidate.candidate_hash),
    )
    with pytest.raises(QcGlobalInputSchemaError):
        build_synthetic_qc_global_input_manifest(run_candidate=candidate)
    assert calls == []


def test_hostile_exported_schema_scalar_is_refused_before_dispatch(monkeypatch):
    calls: list[str] = []

    class HostileText(str):
        def __eq__(self, other):
            calls.append("eq")
            raise AssertionError("hostile comparison executed")

        def __hash__(self):
            return str.__hash__(self)

    monkeypatch.setattr(schema_module, "SCHEMA_ID", HostileText(SCHEMA_ID))
    with pytest.raises(QcGlobalInputSchemaError):
        build_synthetic_qc_global_input_manifest(run_candidate=_candidate())
    assert calls == []


def test_hostile_static_registries_refuse_before_callback_dispatch(monkeypatch):
    calls: list[str] = []

    class HostileText(str):
        def __eq__(self, other):
            calls.append("text-eq")
            raise AssertionError("hostile comparison executed")

        def __hash__(self):
            return str.__hash__(self)

    class HostileInt(int):
        def __eq__(self, other):
            calls.append("int-eq")
            raise AssertionError("hostile comparison executed")

        def __hash__(self):
            return int.__hash__(self)

    registry_trials = (
        ("HORIZONS", (HostileInt(1), 5, 20, 60)),
        ("ROLE_ORDER", (HostileText(ROLE_ORDER[0]),) + ROLE_ORDER[1:]),
        (
            "TERMINAL_LIFECYCLE_FIELDS",
            (HostileText(TERMINAL_LIFECYCLE_FIELDS[0]),)
            + TERMINAL_LIFECYCLE_FIELDS[1:],
        ),
        (
            "TERMINAL_LIFECYCLE_WIRE_TYPES",
            (HostileText(TERMINAL_LIFECYCLE_WIRE_TYPES[0]),)
            + TERMINAL_LIFECYCLE_WIRE_TYPES[1:],
        ),
        (
            "TERMINAL_EVENT_KINDS",
            (HostileText(TERMINAL_EVENT_KINDS[0]),)
            + TERMINAL_EVENT_KINDS[1:],
        ),
        (
            "_EXPECTED_PARTITION_SCHEMAS",
            (
                (
                    HostileText("session_axis"),
                    "arv2-synthetic-session_axis-v1",
                ),
            )
            + schema_module._EXPECTED_PARTITION_SCHEMAS[1:],
        ),
        (
            "_EXTERNAL_BINDING_NAMES",
            (HostileText(schema_module._EXTERNAL_BINDING_NAMES[0]),)
            + schema_module._EXTERNAL_BINDING_NAMES[1:],
        ),
        (
            "_CAPABILITY_NAMES",
            (HostileText(schema_module._CAPABILITY_NAMES[0]),)
            + schema_module._CAPABILITY_NAMES[1:],
        ),
        (
            "ROW_CONTRACTS",
            (
                dataclasses.replace(
                    ROW_CONTRACTS[0], role=HostileText("session_axis")
                ),
            )
            + ROW_CONTRACTS[1:],
        ),
    )
    for name, value in registry_trials:
        with monkeypatch.context() as patch:
            patch.setattr(schema_module, name, value)
            with pytest.raises(QcGlobalInputSchemaError):
                render_qc_global_input_schema_bytes()
        assert calls == []


def test_hostile_partition_schema_container_refuses_before_items_dispatch(
    monkeypatch,
):
    calls: list[str] = []

    class HostileMapping:
        def items(self):
            calls.append("items")
            raise AssertionError("hostile mapping traversal executed")

    monkeypatch.setattr(schema_module, "PARTITION_SCHEMAS", HostileMapping())
    with pytest.raises(QcGlobalInputSchemaError):
        render_qc_global_input_schema_bytes()
    assert calls == []


def test_hostile_mappingproxy_backing_refuses_before_items_dispatch(monkeypatch):
    calls: list[str] = []

    class HostileDict(dict):
        def items(self):
            calls.append("items")
            raise AssertionError("hostile proxy backing traversal executed")

    backing = HostileDict(dict(schema_module.PARTITION_SCHEMAS))
    proxy = schema_module.MappingProxyType(backing)
    monkeypatch.setattr(schema_module, "PARTITION_SCHEMAS", proxy)
    with pytest.raises(QcGlobalInputSchemaError):
        render_qc_global_input_schema_bytes()
    assert calls == []


def test_hostile_descriptor_and_null_binding_refuse_without_equality_dispatch():
    calls: list[str] = []

    class HostileText(str):
        def __eq__(self, other):
            calls.append("text-eq")
            raise AssertionError("hostile comparison executed")

        def __hash__(self):
            return str.__hash__(self)

    class HostileNull:
        def __eq__(self, other):
            calls.append("null-eq")
            raise AssertionError("hostile comparison executed")

    with pytest.raises(QcGlobalInputSchemaError):
        require_synthetic_qc_global_input_manifest(
            _replace_partition(0, role=HostileText("session_axis"))
        )
    manifest = _manifest()
    external = list(manifest.external_bindings)
    external[0] = (external[0][0], HostileNull())
    with pytest.raises(QcGlobalInputSchemaError):
        require_synthetic_qc_global_input_manifest(
            dataclasses.replace(manifest, external_bindings=tuple(external))
        )
    assert calls == []


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("lineage", "production_truth_bound", True),
        ("lineage", "rights_bound", True),
        ("lineage", "operation_authority_bound", True),
        ("transport", "physical_transport", "hostile-unreviewed-binding"),
        ("transport", "qc_object_store_manifest_key", "hostile/key"),
        ("transport", "qc_project_file_path", "hostile.py"),
        ("transport", "lean_adapter", "hostile-adapter"),
        (
            "run_candidate_binding",
            "declared_code_is_runtime_authenticated",
            True,
        ),
        (
            "run_candidate_binding",
            "declared_partition_payloads_are_runtime_authenticated",
            True,
        ),
        (
            "run_candidate_binding",
            "partition_rows_validated_against_row_contracts",
            True,
        ),
    ],
)
def test_exact_manifest_contract_refuses_nested_authority_drift(
    section, field, value
):
    manifest = _manifest()
    document = schema_module._contract_manifest_document(
        candidate=manifest._run_candidate,
        partitions=manifest.partitions,
        manifest_id=manifest.manifest_id,
        manifest_sha256=manifest.manifest_sha256,
    )
    document[section][field] = value
    with pytest.raises(
        QcGlobalInputSchemaError,
        match="authority|transport|authentication|fixed contract|wire contract",
    ):
        schema_module._require_exact_manifest_document_contract(
            document,
            candidate=manifest._run_candidate,
            partitions=manifest.partitions,
            manifest_id=manifest.manifest_id,
            manifest_sha256=manifest.manifest_sha256,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", "wrong-manifest-schema"),
        ("status", "production"),
        ("authority", "claimed-production-authority"),
        ("algorithm_id", "wrong-algorithm"),
        ("evaluation_id", "wrong-evaluation"),
        ("horizons_sessions", [1, 5, 20]),
        ("primary_horizon_sessions", 60),
        (
            "terminal_payoff_reinvestment_policy_id",
            "wrong-terminal-policy",
        ),
    ],
)
def test_exact_manifest_contract_refuses_root_fixed_value_drift(field, value):
    manifest = _manifest()
    document = schema_module._contract_manifest_document(
        candidate=manifest._run_candidate,
        partitions=manifest.partitions,
        manifest_id=manifest.manifest_id,
        manifest_sha256=manifest.manifest_sha256,
    )
    document[field] = value
    with pytest.raises(QcGlobalInputSchemaError, match="root fixed"):
        schema_module._require_exact_manifest_document_contract(
            document,
            candidate=manifest._run_candidate,
            partitions=manifest.partitions,
            manifest_id=manifest.manifest_id,
            manifest_sha256=manifest.manifest_sha256,
        )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("identity_recipe", "manifest_id", "wrong-recipe"),
        ("schema_binding", "schema_id", "wrong-schema"),
        ("run_candidate_binding", "candidate_id", "wrong-candidate"),
        ("session_axis_binding", "first_session", "2021-01-04"),
        ("partition_census", "role_count", 6),
        ("lineage", "manifest_parents", ["wrong-parent"]),
    ],
)
def test_exact_manifest_contract_refuses_other_nested_fixed_value_drift(
    section, field, value
):
    manifest = _manifest()
    document = schema_module._contract_manifest_document(
        candidate=manifest._run_candidate,
        partitions=manifest.partitions,
        manifest_id=manifest.manifest_id,
        manifest_sha256=manifest.manifest_sha256,
    )
    document[section][field] = value
    with pytest.raises(QcGlobalInputSchemaError, match="fixed contract"):
        schema_module._require_exact_manifest_document_contract(
            document,
            candidate=manifest._run_candidate,
            partitions=manifest.partitions,
            manifest_id=manifest.manifest_id,
            manifest_sha256=manifest.manifest_sha256,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contains_real_outcomes", True),
        ("contains_licensed_rows", True),
        ("qc_object_store_key", "hostile/key"),
        ("qc_project_file_path", "hostile.py"),
    ],
)
def test_exact_manifest_contract_refuses_serialized_descriptor_drift(
    field, value
):
    manifest = _manifest()
    document = schema_module._contract_manifest_document(
        candidate=manifest._run_candidate,
        partitions=manifest.partitions,
        manifest_id=manifest.manifest_id,
        manifest_sha256=manifest.manifest_sha256,
    )
    document["partitions"][0][field] = value
    with pytest.raises(
        QcGlobalInputSchemaError,
        match="partition|wire contract",
    ):
        schema_module._require_exact_manifest_document_contract(
            document,
            candidate=manifest._run_candidate,
            partitions=manifest.partitions,
            manifest_id=manifest.manifest_id,
            manifest_sha256=manifest.manifest_sha256,
        )


def test_builder_refuses_a_rebound_manifest_document_helper(monkeypatch):
    original = schema_module._manifest_document

    def authority_drift(**kwargs):
        document = original(**kwargs)
        document["lineage"]["operation_authority_bound"] = True
        return document

    monkeypatch.setattr(schema_module, "_manifest_document", authority_drift)
    with pytest.raises(QcGlobalInputSchemaError, match="builder identity"):
        build_synthetic_qc_global_input_manifest(run_candidate=_candidate())


def test_builder_refuses_a_coherently_rebound_descriptor_builder(monkeypatch):
    original = schema_module._build_descriptor

    def drift(**kwargs):
        return dataclasses.replace(
            original(**kwargs),
            partition_schema="hostile-partition-v9",
            row_schema="hostile-row-v9",
        )

    monkeypatch.setattr(schema_module, "_build_descriptor", drift)
    monkeypatch.setattr(schema_module, "_PINNED_BUILD_DESCRIPTOR", drift)
    with pytest.raises(QcGlobalInputSchemaError, match="candidate inputs"):
        build_synthetic_qc_global_input_manifest(run_candidate=_candidate())


def test_builder_refuses_descriptor_seed_drift(monkeypatch):
    original = schema_module._descriptor_seed_document

    def drift(**kwargs):
        document = original(**kwargs)
        document["binding_sha256"] = "f" * 64
        return document

    monkeypatch.setattr(schema_module, "_descriptor_seed_document", drift)
    with pytest.raises(QcGlobalInputSchemaError, match="candidate inputs"):
        build_synthetic_qc_global_input_manifest(run_candidate=_candidate())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("synthetic_fixture", False),
        ("contains_licensed_rows", True),
        ("contains_real_outcomes", True),
        ("qc_object_store_key", "hostile/key"),
        ("qc_project_file_path", "hostile.py"),
        ("partition_schema", "hostile-partition-v9"),
    ],
)
def test_manifest_refuses_a_coherently_rebound_descriptor_renderer(
    monkeypatch, field, value
):
    original = schema_module._descriptor_document

    def drift(descriptor):
        document = original(descriptor)
        document[field] = value
        return document

    monkeypatch.setattr(schema_module, "_descriptor_document", drift)
    monkeypatch.setattr(schema_module, "_PINNED_DESCRIPTOR_DOCUMENT", drift)
    with pytest.raises(QcGlobalInputSchemaError, match="partition projection"):
        build_synthetic_qc_global_input_manifest(run_candidate=_candidate())


def test_builder_refuses_a_rebound_descriptor_input_checker(monkeypatch):
    monkeypatch.setattr(
        schema_module,
        "_require_descriptor_matches_inputs",
        lambda *args, **kwargs: None,
    )
    with pytest.raises(QcGlobalInputSchemaError, match="builder identity"):
        build_synthetic_qc_global_input_manifest(run_candidate=_candidate())


@pytest.mark.parametrize(
    ("section", "value"),
    [("external_bindings", "claimed-authority"), ("capabilities", True)],
)
def test_exact_manifest_contract_refuses_serialized_gate_drift(section, value):
    manifest = _manifest()
    document = schema_module._contract_manifest_document(
        candidate=manifest._run_candidate,
        partitions=manifest.partitions,
        manifest_id=manifest.manifest_id,
        manifest_sha256=manifest.manifest_sha256,
    )
    first = next(iter(document[section]))
    document[section][first] = value
    with pytest.raises(QcGlobalInputSchemaError, match="authority|wire contract"):
        schema_module._require_exact_manifest_document_contract(
            document,
            candidate=manifest._run_candidate,
            partitions=manifest.partitions,
            manifest_id=manifest.manifest_id,
            manifest_sha256=manifest.manifest_sha256,
        )


def test_false_capabilities_and_null_transport_are_identity_exact():
    manifest = _manifest()
    capabilities = list(manifest.capabilities)
    capabilities[0] = (capabilities[0][0], 0)
    with pytest.raises(QcGlobalInputSchemaError, match="capability"):
        require_synthetic_qc_global_input_manifest(
            dataclasses.replace(manifest, capabilities=tuple(capabilities))
        )
    with pytest.raises(QcGlobalInputSchemaError, match="physical|binding"):
        require_synthetic_qc_global_input_manifest(
            _replace_partition(0, qc_object_store_key=0)
        )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: b"\xef\xbb\xbf" + payload,
        lambda payload: payload.replace(b"\n", b"\r\n"),
        lambda payload: payload.rstrip(b"\n"),
        lambda payload: payload + b"\n",
    ],
)
def test_loader_refuses_noncanonical_byte_encodings(mutator):
    candidate = _candidate()
    payload = render_synthetic_qc_global_input_manifest_bytes(
        build_synthetic_qc_global_input_manifest(run_candidate=candidate)
    )
    with pytest.raises(QcGlobalInputSchemaError, match="canonical|UTF|BOM|bytes"):
        load_synthetic_qc_global_input_manifest_bytes(
            mutator(payload), run_candidate=candidate
        )


@pytest.mark.parametrize("payload", [bytearray(b"{}\n"), memoryview(b"{}\n")])
def test_loader_requires_exact_immutable_bytes(payload):
    with pytest.raises(QcGlobalInputSchemaError, match="exact bytes"):
        load_synthetic_qc_global_input_manifest_bytes(
            payload, run_candidate=_candidate()
        )


def test_loader_checks_size_before_json_parsing(monkeypatch):
    calls: list[str] = []

    def hostile_loads(*args, **kwargs):
        calls.append("loads")
        raise AssertionError("oversize payload reached JSON parser")

    monkeypatch.setattr(schema_module.json, "loads", hostile_loads)
    payload = b"x" * (schema_module.MAX_SYNTHETIC_MANIFEST_BYTES + 1)
    with pytest.raises(QcGlobalInputSchemaError, match="too large"):
        load_synthetic_qc_global_input_manifest_bytes(
            payload, run_candidate=_candidate()
        )
    assert calls == []


def test_loader_refuses_unknown_missing_and_duplicate_root_fields():
    candidate = _candidate()
    document = json.loads(
        render_synthetic_qc_global_input_manifest_bytes(
            build_synthetic_qc_global_input_manifest(run_candidate=candidate)
        )
    )
    unknown = dict(document, unknown_field=None)
    missing = dict(document)
    missing.pop("manifest_sha256")
    payload = render_synthetic_qc_global_input_manifest_bytes(
        build_synthetic_qc_global_input_manifest(run_candidate=candidate)
    )
    duplicate = payload[:-2] + b',"manifest_id":"duplicate"}\n'
    for changed in (_render_json(unknown), _render_json(missing), duplicate):
        with pytest.raises(
            QcGlobalInputSchemaError,
            match="field|duplicate|exact|authenticated declaration",
        ):
            load_synthetic_qc_global_input_manifest_bytes(
                changed, run_candidate=candidate
            )


def test_loader_refuses_duplicate_nested_fields_and_boolean_counts():
    candidate = _candidate()
    nested_duplicate = b'{"nested":{"same":1,"same":2}}\n'
    with pytest.raises(QcGlobalInputSchemaError, match="duplicate"):
        load_synthetic_qc_global_input_manifest_bytes(
            nested_duplicate, run_candidate=candidate
        )
    document = _decoded_manifest()
    document["partition_census"]["total_row_count"] = True
    with pytest.raises(
        QcGlobalInputSchemaError,
        match="field|exact|authenticated declaration",
    ):
        load_synthetic_qc_global_input_manifest_bytes(
            _render_json(document), run_candidate=candidate
        )


def test_manifest_census_rejects_boolean_as_integer_alias():
    with pytest.raises(QcGlobalInputSchemaError, match="count|container"):
        require_synthetic_qc_global_input_manifest(
            _replace_manifest(total_row_count=True)
        )


def test_loader_refuses_float_and_nonfinite_json_numbers():
    candidate = _candidate()
    payload = render_synthetic_qc_global_input_manifest_bytes(
        build_synthetic_qc_global_input_manifest(run_candidate=candidate)
    )
    document = json.loads(payload)
    document["partition_census"]["total_row_count"] = 3435.0
    with pytest.raises(QcGlobalInputSchemaError, match="float|canonical|integer"):
        load_synthetic_qc_global_input_manifest_bytes(
            _render_json(document), run_candidate=candidate
        )
    nonfinite = payload.replace(
        b'"total_row_count":3435', b'"total_row_count":NaN'
    )
    with pytest.raises(
        QcGlobalInputSchemaError,
        match="finite|constant|JSON|exact integers",
    ):
        load_synthetic_qc_global_input_manifest_bytes(
            nonfinite, run_candidate=candidate
        )


def test_loader_requires_the_exact_candidate_binding():
    first = _candidate()
    payload = render_synthetic_qc_global_input_manifest_bytes(
        build_synthetic_qc_global_input_manifest(run_candidate=first)
    )
    partitions = list(_candidate().synthetic_partitions)
    partitions[1] = dataclasses.replace(
        partitions[1], partition_id="fixture/changed-decision-rows.jsonl"
    )
    second = build_synthetic_qc_run_candidate(
        code_files=(_core_binding(),), synthetic_partitions=tuple(partitions)
    )
    with pytest.raises(
        QcGlobalInputSchemaError,
        match="candidate|binding|hash|authenticated declaration",
    ):
        load_synthetic_qc_global_input_manifest_bytes(
            payload, run_candidate=second
        )


def test_manifest_runtime_and_action_accessors_are_literal_false():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    classes = {
        node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
    }
    manifest_class = classes["SyntheticQcGlobalInputManifest"]
    properties = {
        node.name: node
        for node in manifest_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(decorator, ast.Name) and decorator.id == "property"
            for decorator in node.decorator_list
        )
    }
    expected = {
        "filesystem_read_available",
        "environment_read_available",
        "provider_access_available",
        "licensed_input_read_available",
        "production_manifest_available",
        "production_input_read_available",
        "real_outcome_access_available",
        "qc_object_store_read_available",
        "qc_object_store_write_available",
        "qc_project_create_available",
        "upload_available",
        "compile_available",
        "launch_available",
        "result_access_available",
        "result_disposition_available",
        "deployment_available",
        "orders_available",
        "trading_available",
    }
    assert expected <= properties.keys()
    for name in expected:
        body = properties[name].body
        assert len(body) == 1
        assert isinstance(body[0], ast.Return)
        assert isinstance(body[0].value, ast.Constant)
        assert body[0].value.value is False


def test_schema_module_has_no_io_dynamic_import_qc_or_adapter_surface():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported_roots = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imported_roots <= {
        "__future__",
        "dataclasses",
        "datetime",
        "event_study",
        "hashlib",
        "json",
        "re",
        "run_contract",
        "types",
        "typing",
    }
    assert not any(
        isinstance(node, ast.ClassDef)
        and any(
            isinstance(base, ast.Name) and base.id == "QCAlgorithm"
            for base in node.bases
        )
        for node in ast.walk(tree)
    )
    forbidden = {
        "open",
        "__import__",
        "eval",
        "exec",
        "compile",
        "requests",
        "urlopen",
        "read",
        "read_bytes",
        "write",
        "write_bytes",
        "save",
        "save_bytes",
        "create_project",
        "update_file",
        "create_compile",
        "create_backtest",
        "read_backtest",
        "set_holdings",
        "market_order",
        "liquidate",
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not forbidden & called_names
    # ``re.compile`` is a harmless schema primitive; only the dynamic built-in
    # ``compile`` call is prohibited.
    assert not (forbidden - {"compile"}) & called_attributes
    names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert not {"QCAlgorithm", "AlgorithmImports", "ObjectStore"} & names
