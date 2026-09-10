"""Synthetic wire-to-core contract for the ARV2 QC global-input bundle."""
from __future__ import annotations


import ast
import dataclasses
import hashlib
import json
import subprocess
import sys
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import event_study as event_study_module
from research.analyst_revisions_v2_qc import global_input_bundle as bundle_module
from research.analyst_revisions_v2_qc import (
    global_input_schema as global_input_schema_module,
)
from research.analyst_revisions_v2_qc.event_study import (
    BENCHMARK_LISTING_ID,
    BENCHMARK_SECURITY_ID,
    BENCHMARK_TICKER,
    BENCHMARK_TOTAL_RETURN_SERIES_ID,
    HORIZONS,
    SYNTHETIC_LIFECYCLE_SOURCE,
    SYNTHETIC_OPEN_SOURCE,
    SYNTHETIC_TERMINAL_SOURCE,
    SYNTHETIC_TERMINAL_VALUE_BASIS,
    SYNTHETIC_TOTAL_RETURN_VALUE_BASIS,
    BenchmarkOpenValue,
    DecisionRow,
    EventStudyBatch,
    SecurityLifecycleCoverage,
    SecurityOpenValue,
    TerminalLifecycle,
    TerminalRequirement,
    TerminalShareholderPayoff,
    collect_synthetic_event_study,
    require_synthetic_event_study_batch,
)
from research.analyst_revisions_v2_qc.global_input_bundle import (
    QcGlobalInputBundleError,
    SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID,
    SCHEMA_SHA256,
    SyntheticGlobalInputPartitionPayload,
    SyntheticQcGlobalInputBundle,
    collect_synthetic_event_study_from_global_input_bundle,
    load_synthetic_qc_global_input_bundle,
    render_qc_global_input_bundle_schema_bytes,
    require_synthetic_qc_global_input_bundle,
)
from research.analyst_revisions_v2_qc.global_input_schema import (
    ROLE_ORDER,
    build_synthetic_qc_global_input_manifest,
    load_synthetic_qc_global_input_manifest_bytes,
    render_synthetic_qc_global_input_manifest_bytes,
)
from research.analyst_revisions_v2_qc.run_contract import (
    CORE_RELATIVE_PATH,
    CORE_UPLOAD_NAME,
    PARTITION_SCHEMAS,
    CodeFileBinding,
    SyntheticPartitionBinding,
    SyntheticQcRunCandidate,
    build_synthetic_qc_run_candidate,
    canonical_lf_python_source_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "research/analyst_revisions_v2_qc/global_input_bundle.py"
CORE = ROOT / CORE_RELATIVE_PATH
B1_SCHEMA_SOURCE = ROOT / "research/analyst_revisions_v2_qc/global_input_schema.py"
_ARV2_TEST_AUTHORITY_PROPERTY_CALLS: list[bool] = []
_ARV2_TEST_DECODE_PARTITION_CALLS: list[bool] = []


def _hostile_true_authority_property(_self):
    _ARV2_TEST_AUTHORITY_PROPERTY_CALLS.append(True)
    return True


def _hostile_decode_partition(
    *,
    role,
    payload,
    expected_row_count,
    contract,
):
    _ARV2_TEST_DECODE_PARTITION_CALLS.append(True)
    return ()


def _hostile_json_dumps(*_args, **_kwargs):
    raise AssertionError("mutated json.dumps code executed")


def _hostile_trading_sessions(_start, _end):
    raise AssertionError("mutated trading_sessions code executed")


def _hostile_require_static_contract():
    global _ARV2_TEST_REQUIRE_STATIC_CONTRACT_EXECUTED
    _ARV2_TEST_REQUIRE_STATIC_CONTRACT_EXECUTED = True


EXPECTED_PARTITION_PAYLOAD_FIELDS = ("role", "payload")
EXPECTED_BUNDLE_FIELDS = (
    "bundle_id",
    "bundle_hash",
    "bundle_artifact_sha256",
    "schema_id",
    "schema_sha256",
    "schema_artifact_sha256",
    "manifest_id",
    "manifest_sha256",
    "manifest_artifact_sha256",
    "run_candidate_id",
    "run_candidate_hash",
    "session_axis",
    "decisions",
    "security_opens",
    "benchmark_opens",
    "security_lifecycle_coverages",
    "terminal_requirements",
    "terminal_payoffs",
    "partition_payloads",
    "total_byte_count",
    "total_row_count",
    "caller_declared_synthetic_bytes_match_manifest",
    "row_contracts_validated",
    "external_bindings",
    "capabilities",
    "_manifest_bytes",
    "_run_candidate",
    "_canonical_document",
)
EXPECTED_BUNDLE_DOCUMENT_ROOT_FIELDS = (
    "schema",
    "status",
    "authority",
    "bundle_id",
    "bundle_hash",
    "schema_binding",
    "manifest_binding",
    "run_candidate_binding",
    "payload_validation",
    "partitions",
    "partition_census",
    "external_bindings",
    "capabilities",
)
EXPECTED_BUNDLE_NESTED_FIELDS = {
    "schema_binding": (
        "schema_id",
        "schema_sha256",
        "schema_artifact_sha256",
    ),
    "manifest_binding": (
        "manifest_id",
        "manifest_sha256",
        "manifest_artifact_sha256",
    ),
    "run_candidate_binding": (
        "candidate_id",
        "candidate_hash",
        "runtime_code_authenticated",
    ),
    "payload_validation": (
        "caller_declared_synthetic_bytes_match_manifest",
        "row_wire_contracts_validated",
        "canonical_order_validated",
        "canonical_rerender_validated",
        "production_truth_authenticated",
        "rights_authenticated",
        "point_in_time_provenance_authenticated",
        "row_source_provenance_authenticated",
        "real_outcome_authority",
        "synthetic_provenance_authenticated",
    ),
    "partition_census": (
        "role_count",
        "total_byte_count",
        "total_row_count",
    ),
}
EXPECTED_BUNDLE_PARTITION_FIELDS = (
    "ordinal",
    "role",
    "partition_id",
    "row_schema",
    "immutable_artifact_id",
    "byte_count",
    "row_count",
    "artifact_sha256",
)


def _sha(character: str) -> str:
    return character * 64


@lru_cache(maxsize=1)
def _sessions() -> tuple[date, ...]:
    values = trading_sessions(date(2013, 1, 2), date(2026, 8, 28))
    assert len(values) == 3_435
    return values


def _core_binding() -> CodeFileBinding:
    payload = canonical_lf_python_source_bytes(CORE.read_bytes())
    return CodeFileBinding(
        role="event_study_core",
        relative_path=CORE_RELATIVE_PATH,
        upload_name=CORE_UPLOAD_NAME,
        byte_count=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _decision(
    *,
    row_id: str = "decision-1",
    security_id: str = "security-1",
    listing_id: str = "listing-1",
    ticker: str = "AAA",
) -> DecisionRow:
    return DecisionRow(
        row_id=row_id,
        decision_session=date(2021, 3, 31),
        security_id=security_id,
        listing_id=listing_id,
        historical_ticker=ticker,
        evaluation_segment_id="arv2-wf-test-2021",
        fold_id="arv2-wf-test-2021",
        firm_specific_score=Decimal("1.25"),
        global_score=Decimal("0.75"),
        common_event_component_id=f"component-{security_id}",
        input_row_sha256=_sha("a"),
    )


def _security_open(session: date, value: str) -> SecurityOpenValue:
    return SecurityOpenValue(
        session=session,
        security_id="security-1",
        listing_id="listing-1",
        historical_ticker="AAA",
        total_return_open_value=Decimal(value),
        total_return_series_id="security-1-total-return-series",
        value_basis=SYNTHETIC_TOTAL_RETURN_VALUE_BASIS,
        source_role=SYNTHETIC_OPEN_SOURCE,
        source_sha256=_sha("b"),
    )


def _benchmark_open(session: date, value: str) -> BenchmarkOpenValue:
    return BenchmarkOpenValue(
        session=session,
        security_id=BENCHMARK_SECURITY_ID,
        listing_id=BENCHMARK_LISTING_ID,
        historical_ticker=BENCHMARK_TICKER,
        total_return_open_value=Decimal(value),
        total_return_series_id=BENCHMARK_TOTAL_RETURN_SERIES_ID,
        value_basis=SYNTHETIC_TOTAL_RETURN_VALUE_BASIS,
        source_role=SYNTHETIC_OPEN_SOURCE,
        source_sha256=_sha("c"),
    )


def _active_rows() -> dict[str, tuple]:
    sessions = _sessions()
    entry = sessions.index(date(2021, 3, 31))
    valuation_offsets = (0, *HORIZONS)
    return {
        "session_axis": sessions,
        "decision_rows": (_decision(),),
        "security_open_values": tuple(
            _security_open(sessions[entry + offset], str(100 + offset))
            for offset in valuation_offsets
        ),
        "benchmark_open_values": tuple(
            _benchmark_open(sessions[entry + offset], str(400 + offset))
            for offset in valuation_offsets
        ),
        "security_lifecycle_coverages": (
            SecurityLifecycleCoverage(
                security_id="security-1",
                observed_through_session=date(2026, 8, 28),
                terminal_lifecycle=None,
                source_role=SYNTHETIC_LIFECYCLE_SOURCE,
                source_sha256=_sha("d"),
            ),
        ),
        "terminal_requirements": (),
        "terminal_shareholder_payoffs": (),
    }


def _terminal_rows() -> dict[str, tuple]:
    rows = _active_rows()
    sessions = _sessions()
    entry = sessions.index(date(2021, 3, 31))
    terminal_session = sessions[entry + 10]
    lifecycle = TerminalLifecycle(
        security_id="security-1",
        terminal_listing_id="listing-1",
        terminal_historical_ticker="AAA",
        terminal_session=terminal_session,
        event_kind="bankruptcy",
        successor_security_id=None,
        successor_listing_id=None,
        successor_historical_ticker=None,
        total_return_series_id="security-1-total-return-series",
    )
    requirement = TerminalRequirement(
        decision_row_id="decision-1",
        security_id="security-1",
        terminal_listing_id="listing-1",
        terminal_historical_ticker="AAA",
        terminal_session=terminal_session,
        requirement_id="terminal-requirement-1",
        event_kind="bankruptcy",
        successor_security_id=None,
        successor_listing_id=None,
        successor_historical_ticker=None,
        total_return_series_id="security-1-total-return-series",
    )
    rows["security_open_values"] = rows["security_open_values"][:3]
    rows["benchmark_open_values"] = tuple(
        sorted(
            (*rows["benchmark_open_values"], _benchmark_open(terminal_session, "410")),
            key=lambda item: item.session,
        )
    )
    rows["security_lifecycle_coverages"] = (
        SecurityLifecycleCoverage(
            security_id="security-1",
            observed_through_session=date(2026, 8, 28),
            terminal_lifecycle=lifecycle,
            source_role=SYNTHETIC_LIFECYCLE_SOURCE,
            source_sha256=_sha("d"),
        ),
    )
    rows["terminal_requirements"] = (requirement,)
    rows["terminal_shareholder_payoffs"] = (
        TerminalShareholderPayoff(
            decision_row_id="decision-1",
            security_id="security-1",
            terminal_listing_id="listing-1",
            terminal_historical_ticker="AAA",
            terminal_session=terminal_session,
            valuation_session=terminal_session,
            valuation_security_id="security-1",
            valuation_listing_id="listing-1",
            valuation_historical_ticker="AAA",
            terminal_total_return_index_value=Decimal("25"),
            total_return_series_id="security-1-total-return-series",
            value_basis=SYNTHETIC_TERMINAL_VALUE_BASIS,
            requirement_id="terminal-requirement-1",
            event_kind="bankruptcy",
            successor_security_id=None,
            successor_listing_id=None,
            successor_historical_ticker=None,
            source_role=SYNTHETIC_TERMINAL_SOURCE,
            source_sha256=_sha("e"),
        ),
    )
    return rows


def _tagged(value: object) -> object:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "$dataclass": type(value).__qualname__,
            "$fields": {
                field.name: _tagged(getattr(value, field.name))
                for field in dataclasses.fields(value)
            },
        }
    if type(value) is date:
        return {"$date": value.isoformat()}
    if type(value) is Decimal:
        return {"$decimal": str(value)}
    if type(value) in (str, int, bool) or value is None:
        return value
    if type(value) is dict:
        return {"$object": {key: _tagged(item) for key, item in value.items()}}
    raise AssertionError(f"unsupported fixture value: {type(value).__name__}")


def _line(value: object, *, sort_keys: bool = True) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=sort_keys,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _payload_for_role(role: str, rows: tuple) -> bytes:
    if role == "session_axis":
        values = ({"session": session} for session in rows)
    else:
        values = iter(rows)
    return b"".join(_line(_tagged(value)) for value in values)


def _payload_map(rows: dict[str, tuple]) -> dict[str, bytes]:
    return {role: _payload_for_role(role, rows[role]) for role in ROLE_ORDER}


def _candidate_for_payloads(
    payloads: dict[str, bytes],
    *,
    row_counts: dict[str, int] | None = None,
    partition_suffix: str = "",
) -> SyntheticQcRunCandidate:
    counts = row_counts or {
        role: (payload.count(b"\n") if payload else 0)
        for role, payload in payloads.items()
    }
    partitions = tuple(
        SyntheticPartitionBinding(
            role=role,
            partition_id=(
                f"fixture/{ordinal:02d}-{role.replace('_', '-')}{partition_suffix}.jsonl"
            ),
            schema=PARTITION_SCHEMAS[role],
            byte_count=len(payloads[role]),
            row_count=counts[role],
            sha256=hashlib.sha256(payloads[role]).hexdigest(),
        )
        for ordinal, role in enumerate(ROLE_ORDER, start=1)
    )
    return build_synthetic_qc_run_candidate(
        code_files=(_core_binding(),),
        synthetic_partitions=partitions,
    )


def _wire_inputs(
    rows: dict[str, tuple],
    *,
    payloads: dict[str, bytes] | None = None,
    row_counts: dict[str, int] | None = None,
    partition_suffix: str = "",
) -> tuple[
    SyntheticQcRunCandidate,
    bytes,
    tuple[SyntheticGlobalInputPartitionPayload, ...],
]:
    exact_payloads = _payload_map(rows) if payloads is None else payloads
    candidate = _candidate_for_payloads(
        exact_payloads,
        row_counts=row_counts,
        partition_suffix=partition_suffix,
    )
    manifest = build_synthetic_qc_global_input_manifest(run_candidate=candidate)
    manifest_payload = render_synthetic_qc_global_input_manifest_bytes(manifest)
    partition_payloads = tuple(
        SyntheticGlobalInputPartitionPayload(
            role=role,
            payload=exact_payloads[role],
        )
        for role in ROLE_ORDER
    )
    return candidate, manifest_payload, partition_payloads


def _wire_inputs_with_declared_census(
    *,
    byte_counts: dict[str, int] | None = None,
    row_counts: dict[str, int] | None = None,
) -> tuple[
    SyntheticQcRunCandidate,
    bytes,
    tuple[SyntheticGlobalInputPartitionPayload, ...],
]:
    rows = _active_rows()
    payloads = _payload_map(rows)
    candidate = _candidate_for_payloads(payloads)
    changed_partitions = tuple(
        dataclasses.replace(
            item,
            byte_count=(
                item.byte_count
                if byte_counts is None
                else byte_counts.get(item.role, item.byte_count)
            ),
            row_count=(
                item.row_count
                if row_counts is None
                else row_counts.get(item.role, item.row_count)
            ),
        )
        for item in candidate.synthetic_partitions
    )
    changed_candidate = build_synthetic_qc_run_candidate(
        code_files=candidate.code_files,
        synthetic_partitions=changed_partitions,
    )
    manifest = build_synthetic_qc_global_input_manifest(
        run_candidate=changed_candidate
    )
    manifest_bytes = render_synthetic_qc_global_input_manifest_bytes(manifest)
    partition_payloads = tuple(
        SyntheticGlobalInputPartitionPayload(role=role, payload=payloads[role])
        for role in ROLE_ORDER
    )
    return changed_candidate, manifest_bytes, partition_payloads


def _load(
    rows: dict[str, tuple] | None = None,
    *,
    payloads: dict[str, bytes] | None = None,
    row_counts: dict[str, int] | None = None,
) -> SyntheticQcGlobalInputBundle:
    candidate, manifest_payload, partition_payloads = _wire_inputs(
        _active_rows() if rows is None else rows,
        payloads=payloads,
        row_counts=row_counts,
    )
    return load_synthetic_qc_global_input_bundle(
        run_candidate=candidate,
        manifest_bytes=manifest_payload,
        partition_payloads=partition_payloads,
    )


def _collect_direct(
    candidate: SyntheticQcRunCandidate,
    rows: dict[str, tuple],
):
    return collect_synthetic_event_study(
        run_candidate=candidate,
        session_axis=rows["session_axis"],
        decisions=rows["decision_rows"],
        security_opens=rows["security_open_values"],
        benchmark_opens=rows["benchmark_open_values"],
        security_lifecycle_coverages=rows["security_lifecycle_coverages"],
        terminal_requirements=rows["terminal_requirements"],
        terminal_payoffs=rows["terminal_shareholder_payoffs"],
    )


def _replace_role_payload(
    partition_payloads: tuple[SyntheticGlobalInputPartitionPayload, ...],
    role: str,
    payload: object,
) -> tuple[SyntheticGlobalInputPartitionPayload, ...]:
    return tuple(
        SyntheticGlobalInputPartitionPayload(
            role=item.role,
            payload=payload if item.role == role else item.payload,
        )
        for item in partition_payloads
    )


def _decision_document() -> dict[str, object]:
    document = json.loads(_payload_for_role("decision_rows", (_decision(),)))
    assert type(document) is dict
    return document


def _declared_decision_payload(payload: bytes, *, row_count: int = 1):
    rows = _active_rows()
    payloads = _payload_map(rows)
    payloads["decision_rows"] = payload
    counts = {role: len(rows[role]) for role in ROLE_ORDER}
    counts["decision_rows"] = row_count
    return _wire_inputs(rows, payloads=payloads, row_counts=counts)


def test_happy_path_matches_the_direct_reviewed_core_exactly():
    rows = _active_rows()
    candidate, manifest_payload, partition_payloads = _wire_inputs(rows)
    bundle = load_synthetic_qc_global_input_bundle(
        run_candidate=candidate,
        manifest_bytes=manifest_payload,
        partition_payloads=partition_payloads,
    )

    assert type(bundle) is SyntheticQcGlobalInputBundle
    assert require_synthetic_qc_global_input_bundle(bundle) is bundle
    indirect = collect_synthetic_event_study_from_global_input_bundle(bundle)
    direct = _collect_direct(candidate, rows)
    assert indirect == direct
    assert require_synthetic_event_study_batch(indirect) is indirect
    assert indirect.batch_hash == direct.batch_hash
    assert bundle.terminal_requirements == ()
    assert bundle.terminal_payoffs == ()
    assert partition_payloads[5].payload == b""
    assert partition_payloads[6].payload == b""


def test_bundle_schema_identity_and_rendered_artifact_reproduce_exactly():
    first = render_qc_global_input_bundle_schema_bytes()
    second = render_qc_global_input_bundle_schema_bytes()
    assert first == second
    assert first.endswith(b"\n") and not first.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in first
    assert hashlib.sha256(first).hexdigest() == SCHEMA_ARTIFACT_SHA256

    document = json.loads(first)
    assert document["schema_id"] == SCHEMA_ID
    assert document["schema_sha256"] == SCHEMA_SHA256
    document["schema_id"] = None
    document["schema_sha256"] = None
    assert hashlib.sha256(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest() == SCHEMA_SHA256


def test_schema_freezes_the_complete_authority_truth_and_transport_boundary():
    document = json.loads(render_qc_global_input_bundle_schema_bytes())
    authority = (
        "exact_in_memory_synthetic_payload_decode_and_pure_core_composition_"
        "only_no_production_truth_rights_outcome_qc_result_or_trading_authority"
    )
    expected_truth = {
        "caller_declared_synthetic_bytes_match_manifest": True,
        "row_wire_contracts_validated": True,
        "production_truth_authenticated": False,
        "rights_authenticated": False,
        "point_in_time_provenance_authenticated": False,
        "row_source_provenance_authenticated": False,
        "runtime_code_authenticated": False,
        "real_outcome_authority": False,
        "quantconnect_operation_authority": False,
        "result_access_authority": False,
        "synthetic_provenance_authenticated": False,
    }
    expected_transport = {
        "physical_transport": None,
        "filesystem_path": None,
        "qc_object_store_key": None,
        "qc_project_file_path": None,
        "lean_adapter": None,
        "qc_algorithm": None,
    }
    expected_payload_validation = {
        "caller_declared_synthetic_bytes_match_manifest": True,
        "row_wire_contracts_validated": True,
        "canonical_order_validated": True,
        "canonical_rerender_validated": True,
        "production_truth_authenticated": False,
        "rights_authenticated": False,
        "point_in_time_provenance_authenticated": False,
        "row_source_provenance_authenticated": False,
        "real_outcome_authority": False,
        "synthetic_provenance_authenticated": False,
    }

    assert document["status"] == (
        "offline_synthetic_fixture_payloads_only_not_production_admission"
    )
    assert document["authority"] == authority
    assert document["admitted_truth"] == expected_truth
    assert document["transport"] == expected_transport
    assert document["accepted_parent"]["runtime_source_authenticated"] is False
    wire = document["bundle_wire_contract"]
    assert wire["root_fixed_values"] == {
        "schema": "arv2-qc-global-input-bundle-v1",
        "status": document["status"],
        "authority": authority,
    }
    assert wire["payload_validation_fixed_values"] == expected_payload_validation


def test_runtime_code_authentication_contract_remains_literal_false():
    document = json.loads(render_qc_global_input_bundle_schema_bytes())
    bundle = _load()
    retained = json.loads(bundle._canonical_document)

    assert document["admitted_truth"]["runtime_code_authenticated"] is False
    assert (
        retained["run_candidate_binding"]["runtime_code_authenticated"]
        is False
    )
    assert bundle.runtime_code_authenticated is False


def test_schema_freezes_every_remaining_section_to_independent_literals():
    document = json.loads(render_qc_global_input_bundle_schema_bytes())
    assert tuple(document) == (
        "accepted_parent",
        "admitted_truth",
        "authority",
        "bundle_wire_contract",
        "identity_recipe",
        "payload_contract",
        "resource_bounds",
        "row_contracts",
        "schema",
        "schema_id",
        "schema_sha256",
        "status",
        "terminal_lifecycle_contract",
        "transport",
    )
    assert document["schema"] == "arv2-qc-global-input-bundle-schema-v1"
    assert document["schema_id"] == (
        "arv2-qc-global-input-bundle-schema-78e279a8b81c5be4"
    )
    assert document["schema_sha256"] == (
        "78e279a8b81c5be484b93f20600aba5c45f0c4524e06eaed60c378a53b085a90"
    )
    assert document["identity_recipe"] == {
        "schema_sha256": (
            "sha256(canonical_compact_json_with_schema_id_and_schema_sha256_null)"
        ),
        "schema_id": (
            "arv2-qc-global-input-bundle-schema-<first16_schema_sha256>"
        ),
        "artifact_sha256": "sha256(exact_rendered_schema_bytes)",
    }
    assert document["accepted_parent"] == {
        "schema_id": "arv2-qc-global-input-schema-d56e2b5ec26d4068",
        "schema_sha256": (
            "d56e2b5ec26d4068876bff3b549c1f9c7a83014c1372403d7bf33e511bd8e640"
        ),
        "schema_artifact_sha256": (
            "0f60cb3badec36fa9589b220cf91aee43a965865244c7c2726d16da71f6ae3d2"
        ),
        "source_byte_count": 94_959,
        "source_sha256": (
            "f0da3f016cdd794514146a7811d3606b3c8be9d94ffca80e1c28790af519016a"
        ),
        "runtime_source_authenticated": False,
    }
    assert document["payload_contract"] == {
        "role_order": [
            "session_axis",
            "decision_rows",
            "security_open_values",
            "benchmark_open_values",
            "security_lifecycle_coverages",
            "terminal_requirements",
            "terminal_shareholder_payoffs",
        ],
        "encoding": "canonical_tagged_jsonl_strict_utf8_lf-v1",
        "exact_bytes_only": True,
        "manifest_bound": True,
        "candidate_bound": True,
        "descriptor_bound": True,
        "canonical_rerender_required": True,
        "row_contract_validation_required": True,
        "canonical_order_required": True,
        "complete_role_inventory_required": True,
    }
    assert document["row_contracts"] == [
        {
            "role": "session_axis",
            "row_schema": "arv2-qc-global-input-session-v1",
            "record_type": "session_axis_row",
            "root_envelope": "$object",
            "fields": ["session"],
            "wire_types": ["date_tag"],
            "canonical_order": ["session"],
        },
        {
            "role": "decision_rows",
            "row_schema": "arv2-qc-global-input-decision-row-v1",
            "record_type": "DecisionRow",
            "root_envelope": "$dataclass:DecisionRow/$fields",
            "fields": [
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
            ],
            "wire_types": [
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
            ],
            "canonical_order": [
                "decision_session",
                "security_id",
                "listing_id",
                "row_id",
            ],
        },
        {
            "role": "security_open_values",
            "row_schema": "arv2-qc-global-input-security-open-value-v1",
            "record_type": "SecurityOpenValue",
            "root_envelope": "$dataclass:SecurityOpenValue/$fields",
            "fields": [
                "session",
                "security_id",
                "listing_id",
                "historical_ticker",
                "total_return_open_value",
                "total_return_series_id",
                "value_basis",
                "source_role",
                "source_sha256",
            ],
            "wire_types": [
                "date_tag",
                "string",
                "string",
                "string",
                "decimal_tag",
                "string",
                "string",
                "string",
                "lowercase_sha256_string",
            ],
            "canonical_order": [
                "session",
                "security_id",
                "listing_id",
                "total_return_series_id",
            ],
        },
        {
            "role": "benchmark_open_values",
            "row_schema": "arv2-qc-global-input-benchmark-open-value-v1",
            "record_type": "BenchmarkOpenValue",
            "root_envelope": "$dataclass:BenchmarkOpenValue/$fields",
            "fields": [
                "session",
                "security_id",
                "listing_id",
                "historical_ticker",
                "total_return_open_value",
                "total_return_series_id",
                "value_basis",
                "source_role",
                "source_sha256",
            ],
            "wire_types": [
                "date_tag",
                "string",
                "string",
                "string",
                "decimal_tag",
                "string",
                "string",
                "string",
                "lowercase_sha256_string",
            ],
            "canonical_order": ["session"],
        },
        {
            "role": "security_lifecycle_coverages",
            "row_schema": "arv2-qc-global-input-security-lifecycle-coverage-v1",
            "record_type": "SecurityLifecycleCoverage",
            "root_envelope": "$dataclass:SecurityLifecycleCoverage/$fields",
            "fields": [
                "security_id",
                "observed_through_session",
                "terminal_lifecycle",
                "source_role",
                "source_sha256",
            ],
            "wire_types": [
                "string",
                "date_tag",
                "terminal_lifecycle_dataclass_or_null",
                "string",
                "lowercase_sha256_string",
            ],
            "canonical_order": ["security_id"],
        },
        {
            "role": "terminal_requirements",
            "row_schema": "arv2-qc-global-input-terminal-requirement-v1",
            "record_type": "TerminalRequirement",
            "root_envelope": "$dataclass:TerminalRequirement/$fields",
            "fields": [
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
            ],
            "wire_types": [
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
            ],
            "canonical_order": [
                "decision_row_id",
                "terminal_session",
                "requirement_id",
            ],
        },
        {
            "role": "terminal_shareholder_payoffs",
            "row_schema": "arv2-qc-global-input-terminal-shareholder-payoff-v1",
            "record_type": "TerminalShareholderPayoff",
            "root_envelope": "$dataclass:TerminalShareholderPayoff/$fields",
            "fields": [
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
            ],
            "wire_types": [
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
            ],
            "canonical_order": [
                "decision_row_id",
                "valuation_session",
                "requirement_id",
            ],
        },
    ]
    assert document["terminal_lifecycle_contract"] == {
        "record_type": "TerminalLifecycle",
        "fields": [
            "security_id",
            "terminal_listing_id",
            "terminal_historical_ticker",
            "terminal_session",
            "event_kind",
            "successor_security_id",
            "successor_listing_id",
            "successor_historical_ticker",
            "total_return_series_id",
        ],
        "wire_types": [
            "string",
            "string",
            "string",
            "date_tag",
            "string",
            "optional_string",
            "optional_string",
            "optional_string",
            "string",
        ],
    }
    assert document["resource_bounds"] == {
        "maximum_partition_bytes": 67_108_864,
        "maximum_bundle_bytes": 268_435_456,
        "maximum_partition_rows": 2_000_000,
        "maximum_bundle_rows": 5_000_000,
        "maximum_row_bytes": 1_048_576,
        "maximum_json_depth": 16,
    }


def test_schema_and_dataclasses_freeze_every_bundle_wire_inventory():
    document = json.loads(render_qc_global_input_bundle_schema_bytes())
    wire = document["bundle_wire_contract"]
    assert tuple(wire) == (
        "bundle_dataclass_fields",
        "identity_recipe",
        "nested_field_inventories",
        "partition_fields",
        "partition_payload_dataclass_fields",
        "payload_validation_fixed_values",
        "root_fields",
        "root_fixed_values",
    )
    assert tuple(wire["partition_payload_dataclass_fields"]) == (
        EXPECTED_PARTITION_PAYLOAD_FIELDS
    )
    assert tuple(wire["bundle_dataclass_fields"]) == EXPECTED_BUNDLE_FIELDS
    assert tuple(wire["root_fields"]) == EXPECTED_BUNDLE_DOCUMENT_ROOT_FIELDS
    assert {
        name: tuple(fields)
        for name, fields in wire["nested_field_inventories"].items()
    } == EXPECTED_BUNDLE_NESTED_FIELDS
    assert tuple(wire["partition_fields"]) == EXPECTED_BUNDLE_PARTITION_FIELDS
    assert wire["identity_recipe"] == {
        "bundle_hash": (
            "sha256(canonical_compact_json_with_bundle_id_and_bundle_hash_null)"
        ),
        "bundle_id": (
            "synthetic-arv2-qc-global-input-bundle-<first16_bundle_hash>"
        ),
        "artifact_sha256": (
            "sha256(exact_canonical_bundle_document_with_one_lf)"
        ),
    }
    assert tuple(
        field.name
        for field in dataclasses.fields(SyntheticGlobalInputPartitionPayload)
    ) == EXPECTED_PARTITION_PAYLOAD_FIELDS
    assert tuple(
        field.name for field in dataclasses.fields(SyntheticQcGlobalInputBundle)
    ) == EXPECTED_BUNDLE_FIELDS


def test_accepted_b1_schema_source_identity_reproduces_from_canonical_lf_bytes():
    payload = canonical_lf_python_source_bytes(B1_SCHEMA_SOURCE.read_bytes())
    assert len(payload) == 94_959
    assert hashlib.sha256(payload).hexdigest() == (
        "f0da3f016cdd794514146a7811d3606b3c8be9d94ffca80e1c28790af519016a"
    )


def test_nested_terminal_lifecycle_and_payoff_round_trip_to_the_core():
    rows = _terminal_rows()
    candidate, manifest_payload, partition_payloads = _wire_inputs(rows)
    bundle = load_synthetic_qc_global_input_bundle(
        run_candidate=candidate,
        manifest_bytes=manifest_payload,
        partition_payloads=partition_payloads,
    )

    assert bundle.security_lifecycle_coverages == rows[
        "security_lifecycle_coverages"
    ]
    assert bundle.security_lifecycle_coverages[0].terminal_lifecycle is not None
    assert bundle.terminal_requirements == rows["terminal_requirements"]
    assert bundle.terminal_payoffs == rows["terminal_shareholder_payoffs"]
    assert collect_synthetic_event_study_from_global_input_bundle(
        bundle
    ) == _collect_direct(candidate, rows)


def test_bundle_is_deterministic_and_exposes_the_exact_decoded_roles():
    first = _load()
    second = _load()

    assert first.bundle_id == second.bundle_id
    assert first.bundle_hash == second.bundle_hash
    assert first.manifest_id == second.manifest_id
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.run_candidate_id == second.run_candidate_id
    assert first.run_candidate_hash == second.run_candidate_hash
    assert first.session_axis == _active_rows()["session_axis"]
    assert first.decisions == _active_rows()["decision_rows"]
    assert first.security_opens == _active_rows()["security_open_values"]
    assert first.benchmark_opens == _active_rows()["benchmark_open_values"]


def test_bundle_semantic_id_hash_and_exact_artifact_recompute_independently():
    bundle = _load()
    document = json.loads(bundle._canonical_document)
    assert tuple(document) == tuple(sorted(EXPECTED_BUNDLE_DOCUMENT_ROOT_FIELDS))
    assert bundle._canonical_document == _line(document)
    assert hashlib.sha256(bundle._canonical_document).hexdigest() == (
        bundle.bundle_artifact_sha256
    )

    document["bundle_id"] = None
    document["bundle_hash"] = None
    seed = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    assert digest == bundle.bundle_hash
    assert bundle.bundle_id == (
        f"synthetic-arv2-qc-global-input-bundle-{digest[:16]}"
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("authority", "production_authority"),
        ("production_truth_authenticated", True),
        ("rights_authenticated", True),
        ("real_outcome_authority", True),
        ("synthetic_provenance_authenticated", True),
    ),
)
def test_independent_bundle_document_contract_refuses_authority_tamper(
    field: str,
    replacement: object,
):
    bundle = _load()
    manifest = load_synthetic_qc_global_input_manifest_bytes(
        bundle._manifest_bytes,
        run_candidate=bundle._run_candidate,
    )
    document = bundle_module._bundle_document(
        manifest=manifest,
        payloads=bundle.partition_payloads,
        bundle_id=bundle.bundle_id,
        bundle_hash=bundle.bundle_hash,
    )
    if field == "authority":
        document[field] = replacement
    else:
        document["payload_validation"][field] = replacement

    with pytest.raises(QcGlobalInputBundleError):
        bundle_module._require_bundle_document_contract(
            document,
            manifest=manifest,
            payloads=bundle.partition_payloads,
            bundle_id=bundle.bundle_id,
            bundle_hash=bundle.bundle_hash,
        )


@pytest.mark.parametrize("change", ["reverse", "missing", "duplicate", "unknown"])
def test_partition_payload_role_inventory_and_order_are_exact(change: str):
    candidate, manifest_payload, partition_payloads = _wire_inputs(_active_rows())
    if change == "reverse":
        changed = tuple(reversed(partition_payloads))
    elif change == "missing":
        changed = partition_payloads[:-1]
    elif change == "duplicate":
        changed = (*partition_payloads[:-1], partition_payloads[0])
    else:
        changed = (
            *partition_payloads[:-1],
            SyntheticGlobalInputPartitionPayload(role="unknown", payload=b""),
        )

    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_payload,
            partition_payloads=changed,
        )


def test_partition_payload_container_and_scalars_must_be_exact_types():
    candidate, manifest_payload, partition_payloads = _wire_inputs(_active_rows())
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_payload,
            partition_payloads=list(partition_payloads),
        )
    changed = _replace_role_payload(
        partition_payloads,
        "decision_rows",
        bytearray(partition_payloads[1].payload),
    )
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_payload,
            partition_payloads=changed,
        )


def test_exact_payload_shell_is_normalized_at_load_boundary():
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    shell = object.__new__(SyntheticGlobalInputPartitionPayload)
    changed = (shell, *partition_payloads[1:])

    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=changed,
        )


def test_exact_payload_shell_is_normalized_in_accepted_bundle():
    bundle = _load()
    shell = object.__new__(SyntheticGlobalInputPartitionPayload)
    changed = dataclasses.replace(
        bundle,
        partition_payloads=(shell, *bundle.partition_payloads[1:]),
    )

    with pytest.raises(QcGlobalInputBundleError):
        require_synthetic_qc_global_input_bundle(changed)


def test_exact_candidate_shell_is_normalized_at_load_boundary():
    _candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    shell = object.__new__(SyntheticQcRunCandidate)

    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=shell,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )


def test_exact_bundle_shell_is_normalized_at_validation_boundary():
    shell = object.__new__(SyntheticQcGlobalInputBundle)

    with pytest.raises(QcGlobalInputBundleError):
        require_synthetic_qc_global_input_bundle(shell)


def test_deleted_decision_slot_is_normalized_at_validation_boundary():
    bundle = _load()
    row = bundle.decisions[0]
    original_row_id = row.row_id
    object.__delattr__(row, "row_id")
    try:
        with pytest.raises(QcGlobalInputBundleError):
            require_synthetic_qc_global_input_bundle(bundle)
    finally:
        object.__setattr__(row, "row_id", original_row_id)


@pytest.mark.parametrize(
    "bound_name",
    (
        "MAX_SYNTHETIC_PARTITION_ROWS",
        "MAX_SYNTHETIC_BUNDLE_ROWS",
        "MAX_SYNTHETIC_PARTITION_BYTES",
        "MAX_SYNTHETIC_BUNDLE_BYTES",
    ),
)
def test_bundle_revalidation_resource_caps_refuse_before_rerender(
    bound_name: str,
):
    bundle = _load()
    if bound_name == "MAX_SYNTHETIC_PARTITION_ROWS":
        changed_bound = max(
            len(rows)
            for rows in (
                bundle.session_axis,
                bundle.decisions,
                bundle.security_opens,
                bundle.benchmark_opens,
                bundle.security_lifecycle_coverages,
                bundle.terminal_requirements,
                bundle.terminal_payoffs,
            )
        ) - 1
    elif bound_name == "MAX_SYNTHETIC_BUNDLE_ROWS":
        changed_bound = bundle.total_row_count - 1
    elif bound_name == "MAX_SYNTHETIC_PARTITION_BYTES":
        changed_bound = max(
            len(item.payload) for item in bundle.partition_payloads
        ) - 1
    else:
        changed_bound = bundle.total_byte_count - 1

    original_bound = getattr(bundle_module, bound_name)
    original_renderer = bundle_module._PINNED_RENDER_DECODED_PARTITION
    render_calls = []
    loader_calls = []

    def hostile_renderer(*args, **kwargs):
        render_calls.append((args, kwargs))
        return original_renderer(*args, **kwargs)

    def hostile_loader(**kwargs):
        loader_calls.append(kwargs)
        raise AssertionError("bundle loader ran after a resource refusal")

    setattr(bundle_module, bound_name, changed_bound)
    bundle_module._PINNED_RENDER_DECODED_PARTITION = hostile_renderer
    try:
        with pytest.raises(QcGlobalInputBundleError):
            bundle_module._BUNDLE_VALIDATOR_IMPLEMENTATION(
                bundle,
                _static_check=lambda: None,
                _loader=hostile_loader,
            )
    finally:
        bundle_module._PINNED_RENDER_DECODED_PARTITION = original_renderer
        setattr(bundle_module, bound_name, original_bound)
    assert render_calls == []
    assert loader_calls == []


def test_payload_byte_hash_and_census_must_match_the_manifest_descriptor():
    candidate, manifest_payload, partition_payloads = _wire_inputs(_active_rows())
    changed = _replace_role_payload(
        partition_payloads,
        "decision_rows",
        partition_payloads[1].payload + b" ",
    )
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_payload,
            partition_payloads=changed,
        )

    rows = _active_rows()
    payloads = _payload_map(rows)
    counts = {role: len(rows[role]) for role in ROLE_ORDER}
    counts["decision_rows"] = 2
    candidate, manifest_payload, partition_payloads = _wire_inputs(
        rows,
        payloads=payloads,
        row_counts=counts,
    )
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_payload,
            partition_payloads=partition_payloads,
        )


def test_manifest_must_authenticate_the_exact_candidate_and_payload_set():
    rows = _active_rows()
    candidate, _, partition_payloads = _wire_inputs(rows)
    other_candidate, other_manifest, _ = _wire_inputs(
        rows,
        partition_suffix="-other",
    )
    assert candidate.candidate_hash != other_candidate.candidate_hash

    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=other_manifest,
            partition_payloads=partition_payloads,
        )


@pytest.mark.parametrize(
    ("declared_bytes", "expected_message"),
    (
        (67_108_864, "partition bytes do not match the manifest"),
        (67_108_865, "bundle exceeds synthetic resource bounds"),
    ),
)
def test_per_partition_byte_limit_is_an_exact_predecode_boundary(
    declared_bytes: int,
    expected_message: str,
):
    candidate, manifest_bytes, partition_payloads = (
        _wire_inputs_with_declared_census(
            byte_counts={"decision_rows": declared_bytes}
        )
    )
    with pytest.raises(
        QcGlobalInputBundleError,
        match=f"^{expected_message}$",
    ):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )


@pytest.mark.parametrize(
    ("last_count", "expected_message"),
    (
        (0, "partition bytes do not match the manifest"),
        (1, "bundle exceeds synthetic resource bounds"),
    ),
)
def test_total_bundle_byte_limit_is_exact(
    last_count: int,
    expected_message: str,
):
    axis_byte_count = len(_payload_map(_active_rows())["session_axis"])
    assert axis_byte_count == 161_445
    fourth_count = 268_435_456 - axis_byte_count - (3 * 67_108_864)
    assert 0 < fourth_count < 67_108_864
    byte_counts = {
        "decision_rows": 67_108_864,
        "security_open_values": 67_108_864,
        "benchmark_open_values": 67_108_864,
        "security_lifecycle_coverages": fourth_count + last_count,
        "terminal_requirements": 0,
        "terminal_shareholder_payoffs": 0,
    }
    assert sum(byte_counts.values()) + axis_byte_count == (
        268_435_456 + last_count
    )
    candidate, manifest_bytes, partition_payloads = (
        _wire_inputs_with_declared_census(byte_counts=byte_counts)
    )
    with pytest.raises(
        QcGlobalInputBundleError,
        match=f"^{expected_message}$",
    ):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )


@pytest.mark.parametrize(
    ("last_count", "expected_message"),
    (
        (1_000_000, "partition is not canonical tagged JSONL for its row contract"),
        (1_000_001, "bundle exceeds synthetic resource bounds"),
    ),
)
def test_total_bundle_row_limit_is_exact(
    last_count: int,
    expected_message: str,
):
    axis_row_count = len(_active_rows()["session_axis"])
    third_count = 5_000_000 - axis_row_count - 4_000_000
    assert third_count == 996_565
    row_counts = {
        "decision_rows": 2_000_000,
        "security_open_values": 2_000_000,
        "benchmark_open_values": third_count + (last_count - 1_000_000),
        "security_lifecycle_coverages": 0,
        "terminal_requirements": 0,
        "terminal_shareholder_payoffs": 0,
    }
    assert sum(row_counts.values()) + axis_row_count == (
        4_000_000 + last_count
    )
    candidate, manifest_bytes, partition_payloads = (
        _wire_inputs_with_declared_census(row_counts=row_counts)
    )
    with pytest.raises(
        QcGlobalInputBundleError,
        match=f"^{expected_message}$",
    ):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )


@pytest.mark.parametrize(
    ("declared_rows", "expected_message"),
    (
        (2_000_000, "partition is not canonical tagged JSONL for its row contract"),
        (2_000_001, "bundle exceeds synthetic resource bounds"),
    ),
)
def test_per_partition_row_limit_is_exact(
    declared_rows: int,
    expected_message: str,
):
    candidate, manifest_bytes, partition_payloads = (
        _wire_inputs_with_declared_census(
            row_counts={"decision_rows": declared_rows}
        )
    )
    with pytest.raises(
        QcGlobalInputBundleError,
        match=f"^{expected_message}$",
    ):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )


def test_exact_row_byte_limit_accepts_the_last_byte_and_refuses_one_more():
    document = _decision_document()
    document["$fields"]["historical_ticker"] = ""
    empty_line = _line(document)[:-1]
    padding = "X" * (1_048_576 - len(empty_line))
    document["$fields"]["historical_ticker"] = padding
    at_limit = _line(document)
    assert len(at_limit[:-1]) == 1_048_576

    contract = bundle_module._EXPECTED_ROW_CONTRACTS[1]
    decoded = bundle_module._decode_partition(
        role="decision_rows",
        payload=at_limit,
        expected_row_count=1,
        contract=contract,
    )
    assert type(decoded) is tuple and len(decoded) == 1

    document["$fields"]["historical_ticker"] = padding + "X"
    over_limit = _line(document)
    assert len(over_limit[:-1]) == 1_048_577
    assert bundle_module._decode_partition(
        role="decision_rows",
        payload=over_limit,
        expected_row_count=1,
        contract=contract,
    ) is None


def test_exact_json_depth_limit_accepts_depth_16_and_refuses_depth_17():
    def nested(depth: int):
        value = "leaf"
        for _ in range(depth):
            value = [value]
        return value

    assert bundle_module._json_tree_is_exact(nested(16)) is True
    assert bundle_module._json_tree_is_exact(nested(17)) is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: b"\xef\xbb\xbf" + payload,
        lambda payload: payload.replace(b"\n", b"\r\n", 1),
        lambda payload: b"\xff" + payload[1:],
        lambda payload: payload[:-1],
        lambda payload: payload + b"\n",
        lambda payload: b" " + payload,
    ],
    ids=("bom", "crlf", "non_utf8", "missing_lf", "blank_line", "whitespace"),
)
def test_even_redeclared_noncanonical_partition_bytes_are_refused(mutate):
    payload = mutate(_payload_for_role("decision_rows", (_decision(),)))
    candidate, manifest_payload, partition_payloads = _declared_decision_payload(
        payload
    )
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_payload,
            partition_payloads=partition_payloads,
        )


def _missing_field(document: dict[str, object]) -> dict[str, object]:
    del document["$fields"]["row_id"]
    return document


def _extra_field(document: dict[str, object]) -> dict[str, object]:
    document["$fields"]["extra"] = "forbidden"
    return document


def _wrong_dataclass(document: dict[str, object]) -> dict[str, object]:
    document["$dataclass"] = "BenchmarkOpenValue"
    return document


def _wrong_root(document: dict[str, object]) -> dict[str, object]:
    return {"$object": document["$fields"]}


def _wrong_string_type(document: dict[str, object]) -> dict[str, object]:
    document["$fields"]["row_id"] = 1
    return document


def _wrong_optional_type(document: dict[str, object]) -> dict[str, object]:
    document["$fields"]["fold_id"] = False
    return document


def _wrong_date_tag(document: dict[str, object]) -> dict[str, object]:
    document["$fields"]["decision_session"] = {"$datex": "2021-03-31"}
    return document


def _invalid_date(document: dict[str, object]) -> dict[str, object]:
    document["$fields"]["decision_session"] = {"$date": "2021-02-30"}
    return document


def _wrong_decimal_type(document: dict[str, object]) -> dict[str, object]:
    document["$fields"]["firm_specific_score"] = 1.25
    return document


def _nonfinite_decimal(document: dict[str, object]) -> dict[str, object]:
    document["$fields"]["firm_specific_score"] = {"$decimal": "NaN"}
    return document


def _noncanonical_decimal(document: dict[str, object]) -> dict[str, object]:
    document["$fields"]["firm_specific_score"] = {"$decimal": "+1"}
    return document


def _uppercase_sha(document: dict[str, object]) -> dict[str, object]:
    document["$fields"]["input_row_sha256"] = "A" * 64
    return document


@pytest.mark.parametrize(
    "mutation",
    (
        _missing_field,
        _extra_field,
        _wrong_dataclass,
        _wrong_root,
        _wrong_string_type,
        _wrong_optional_type,
        _wrong_date_tag,
        _invalid_date,
        _wrong_decimal_type,
        _nonfinite_decimal,
        _noncanonical_decimal,
        _uppercase_sha,
    ),
)
def test_redeclared_row_envelope_fields_tags_and_wire_types_are_exact(mutation):
    payload = _line(mutation(_decision_document()))
    candidate, manifest_payload, partition_payloads = _declared_decision_payload(
        payload
    )
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_payload,
            partition_payloads=partition_payloads,
        )


def test_duplicate_json_keys_and_json_nonfinite_numbers_are_refused():
    canonical = _payload_for_role("decision_rows", (_decision(),))
    duplicate = canonical.replace(
        b'{"$dataclass":"DecisionRow",',
        b'{"$dataclass":"DecisionRow","$dataclass":"DecisionRow",',
        1,
    )
    for payload in (
        duplicate,
        canonical.replace(
            b'{"$decimal":"1.25"}',
            b"NaN",
            1,
        ),
    ):
        candidate, manifest_payload, partition_payloads = (
            _declared_decision_payload(payload)
        )
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_payload,
                partition_payloads=partition_payloads,
            )


def test_json_key_order_and_row_order_are_canonical_not_merely_equivalent():
    document = _decision_document()
    noncanonical_keys = _line(
        {"$fields": document["$fields"], "$dataclass": "DecisionRow"},
        sort_keys=False,
    )
    candidate, manifest_payload, partition_payloads = _declared_decision_payload(
        noncanonical_keys
    )
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_payload,
            partition_payloads=partition_payloads,
        )

    rows = _active_rows()
    first = _decision()
    second = _decision(
        row_id="decision-2",
        security_id="security-2",
        listing_id="listing-2",
        ticker="BBB",
    )
    reversed_rows = _payload_for_role("decision_rows", (second, first))
    candidate, manifest_payload, partition_payloads = _declared_decision_payload(
        reversed_rows,
        row_count=2,
    )
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_payload,
            partition_payloads=partition_payloads,
        )

    duplicate_rows = _payload_for_role("decision_rows", (first, first))
    candidate, manifest_payload, partition_payloads = _declared_decision_payload(
        duplicate_rows,
        row_count=2,
    )
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_payload,
            partition_payloads=partition_payloads,
        )


def test_nested_terminal_lifecycle_envelope_is_exact():
    rows = _terminal_rows()
    payloads = _payload_map(rows)
    document = json.loads(payloads["security_lifecycle_coverages"])
    nested = document["$fields"]["terminal_lifecycle"]
    nested["$dataclass"] = "TerminalRequirement"
    payloads["security_lifecycle_coverages"] = _line(document)
    counts = {role: len(rows[role]) for role in ROLE_ORDER}
    candidate, manifest_payload, partition_payloads = _wire_inputs(
        rows,
        payloads=payloads,
        row_counts=counts,
    )
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_payload,
            partition_payloads=partition_payloads,
        )


def test_malformed_last_role_reaches_its_wire_guard_before_composition():
    rows = _active_rows()
    payloads = _payload_map(rows)
    malformed = _line(
        {
            "$dataclass": "TerminalShareholderPayoff",
            "$fields": {},
        }
    )
    payloads["terminal_shareholder_payoffs"] = malformed
    counts = {role: len(rows[role]) for role in ROLE_ORDER}
    counts["terminal_shareholder_payoffs"] = 1
    candidate, manifest_bytes, partition_payloads = _wire_inputs(
        rows,
        payloads=payloads,
        row_counts=counts,
    )
    with pytest.raises(
        QcGlobalInputBundleError,
        match=(
            "^partition is not canonical tagged JSONL for its row contract$"
        ),
    ):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )


def test_wire_valid_but_core_invalid_rows_are_normalised_to_bundle_error():
    rows = _active_rows()
    rows["security_open_values"] = tuple(
        dataclasses.replace(item, source_role="synthetic-but-unreviewed-source")
        for item in rows["security_open_values"]
    )
    candidate, manifest_bytes, partition_payloads = _wire_inputs(rows)
    bundle = load_synthetic_qc_global_input_bundle(
        run_candidate=candidate,
        manifest_bytes=manifest_bytes,
        partition_payloads=partition_payloads,
    )
    with pytest.raises(QcGlobalInputBundleError):
        collect_synthetic_event_study_from_global_input_bundle(bundle)


def test_bundle_identity_and_decoded_rows_are_revalidated_after_mutation():
    bundle = _load()
    changed_hash = dataclasses.replace(bundle, bundle_hash=_sha("0"))
    with pytest.raises(QcGlobalInputBundleError):
        require_synthetic_qc_global_input_bundle(changed_hash)

    decision = dataclasses.replace(bundle.decisions[0], global_score=Decimal("9"))
    changed_rows = dataclasses.replace(bundle, decisions=(decision,))
    with pytest.raises(QcGlobalInputBundleError):
        require_synthetic_qc_global_input_bundle(changed_rows)


@pytest.mark.parametrize("cycle_target", ("decision_scalar", "lifecycle_nested"))
def test_caller_mutated_bundle_row_cycles_are_normalized(cycle_target: str):
    bundle = _load()
    if cycle_target == "decision_scalar":
        row = bundle.decisions[0]
        field_name = "row_id"
    else:
        row = bundle.security_lifecycle_coverages[0]
        field_name = "terminal_lifecycle"
    original_value = getattr(row, field_name)
    object.__setattr__(row, field_name, row)
    try:
        with pytest.raises(QcGlobalInputBundleError):
            require_synthetic_qc_global_input_bundle(bundle)
    finally:
        object.__setattr__(row, field_name, original_value)


def test_loader_copies_payload_records_before_caller_reassignment():
    rows = _active_rows()
    candidate, manifest_bytes, partition_payloads = _wire_inputs(rows)
    bundle = load_synthetic_qc_global_input_bundle(
        run_candidate=candidate,
        manifest_bytes=manifest_bytes,
        partition_payloads=partition_payloads,
    )
    original = bundle.partition_payloads[1].payload
    object.__setattr__(partition_payloads[1], "payload", b"changed")

    assert bundle.partition_payloads[1] is not partition_payloads[1]
    assert bundle.partition_payloads[1].payload == original
    assert require_synthetic_qc_global_input_bundle(bundle) is bundle


def test_hostile_scalar_subclasses_are_refused_before_comparison_callbacks():
    class HostileString(str):
        calls = 0

        def __eq__(self, other):
            type(self).calls += 1
            return super().__eq__(other)

        def __hash__(self):
            type(self).calls += 1
            return super().__hash__()

    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    changed = (
        SyntheticGlobalInputPartitionPayload(
            role=HostileString(partition_payloads[0].role),
            payload=partition_payloads[0].payload,
        ),
        *partition_payloads[1:],
    )
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=changed,
        )
    assert HostileString.calls == 0


def test_rebound_internal_helper_refuses_before_the_replacement_runs(monkeypatch):
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    calls = []

    def hostile_helper(**_kwargs):
        calls.append(True)
        return ()

    monkeypatch.setattr(bundle_module, "_decode_partition", hostile_helper)
    with pytest.raises(QcGlobalInputBundleError, match="callable topology"):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )
    assert calls == []


def test_rebound_public_loader_refuses_before_the_replacement_runs(monkeypatch):
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    calls = []

    def hostile_loader(**_kwargs):
        calls.append(True)
        raise AssertionError("rebound public loader ran")

    monkeypatch.setattr(
        bundle_module,
        "load_synthetic_qc_global_input_bundle",
        hostile_loader,
    )
    with pytest.raises(QcGlobalInputBundleError, match="callable topology"):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )
    assert calls == []


@pytest.mark.parametrize(
    "class_name",
    ("SyntheticGlobalInputPartitionPayload", "SyntheticQcGlobalInputBundle"),
)
def test_rebinding_an_owned_dataclass_is_refused(
    monkeypatch,
    class_name: str,
):
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    monkeypatch.setattr(bundle_module, class_name, object)
    with pytest.raises(QcGlobalInputBundleError, match="class identity"):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )


@pytest.mark.parametrize("row_class", (DecisionRow, SyntheticPartitionBinding))
def test_rebound_row_equality_refuses_without_calling_the_mutant(
    monkeypatch,
    row_class: type,
):
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    calls = []
    original = row_class.__eq__

    def hostile_equality(self, other):
        calls.append((self, other))
        return original(self, other)

    monkeypatch.setattr(row_class, "__eq__", hostile_equality)
    with pytest.raises(QcGlobalInputBundleError, match="equality topology"):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )
    assert calls == []


def test_rebound_expected_role_root_refuses_before_hostile_children_run(monkeypatch):
    class HostileString(str):
        calls = 0

        def __eq__(self, other):
            type(self).calls += 1
            return super().__eq__(other)

        def __hash__(self):
            type(self).calls += 1
            return super().__hash__()

    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    hostile_root = tuple(HostileString(role) for role in ROLE_ORDER)
    monkeypatch.setattr(bundle_module, "_EXPECTED_ROLE_ORDER", hostile_root)
    with pytest.raises(QcGlobalInputBundleError, match="static topology"):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )
    assert HostileString.calls == 0


def test_rebound_hex_matcher_refuses_before_the_hostile_matcher_runs(monkeypatch):
    class HostileMatcher:
        calls = 0

        def fullmatch(self, _value):
            type(self).calls += 1
            return object()

    bundle = _load()
    monkeypatch.setattr(bundle_module, "_HEX_64", HostileMatcher())
    with pytest.raises(QcGlobalInputBundleError, match="static topology"):
        require_synthetic_qc_global_input_bundle(bundle)
    assert HostileMatcher.calls == 0


def test_hostile_internal_helper_pin_refuses_before_len_callback(monkeypatch):
    class HostileHelperList(list):
        calls = 0

        def __len__(self):
            type(self).calls += 1
            return super().__len__()

    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    hostile_root = HostileHelperList(bundle_module._PINNED_INTERNAL_HELPERS)
    monkeypatch.setattr(bundle_module, "_PINNED_INTERNAL_HELPERS", hostile_root)
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )
    assert HostileHelperList.calls == 0


def test_rebound_invalid_operation_never_leaks_from_invalid_decimal(monkeypatch):
    document = _decision_document()
    document["$fields"]["global_score"] = {"$decimal": "not-a-decimal"}
    candidate, manifest_bytes, partition_payloads = _declared_decision_payload(
        _line(document)
    )
    monkeypatch.setattr(bundle_module, "InvalidOperation", KeyError)

    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )


def test_rebound_parent_error_alias_is_rejected_at_the_static_boundary(monkeypatch):
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    monkeypatch.setattr(bundle_module, "QcGlobalInputSchemaError", KeyError)

    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )


def test_hostile_decision_equality_descriptor_is_never_bound(monkeypatch):
    calls = []
    original_equality = vars(DecisionRow)["__eq__"]

    class HostileEqualityDescriptor:
        def __get__(self, instance, owner=None):
            calls.append((instance, owner))
            return original_equality.__get__(instance, owner)

    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    monkeypatch.setattr(DecisionRow, "__eq__", HostileEqualityDescriptor())
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )
    assert calls == []


@pytest.mark.parametrize("boundary", ("load", "require"))
@pytest.mark.parametrize("attribute_name", ("__init__", "__getattribute__", "row_id"))
def test_decision_row_execution_surface_changes_are_rejected_before_callbacks(
    monkeypatch,
    attribute_name: str,
    boundary: str,
):
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    bundle = None
    if boundary == "require":
        bundle = load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )

    calls = []
    if attribute_name == "__init__":
        original = vars(DecisionRow)[attribute_name]

        def replacement(self, *args, **kwargs):
            calls.append((args, kwargs))
            return original(self, *args, **kwargs)

    elif attribute_name == "__getattribute__":
        original = DecisionRow.__getattribute__

        def replacement(self, name):
            calls.append(name)
            return original(self, name)

    else:
        original = vars(DecisionRow)[attribute_name]

        class HostileFieldDescriptor:
            def __get__(self, instance, owner=None):
                calls.append(("get", instance, owner))
                return original.__get__(instance, owner)

            def __set__(self, instance, value):
                calls.append(("set", instance, value))
                return original.__set__(instance, value)

        replacement = HostileFieldDescriptor()

    monkeypatch.setattr(DecisionRow, attribute_name, replacement)
    with pytest.raises(QcGlobalInputBundleError):
        if boundary == "load":
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
        else:
            assert bundle is not None
            require_synthetic_qc_global_input_bundle(bundle)
    assert calls == []


@pytest.mark.parametrize("boundary", ("load", "require"))
@pytest.mark.parametrize("attribute_name", ("__setattr__", "__delattr__"))
def test_frozen_decision_mutator_changes_are_rejected_before_callbacks(
    monkeypatch,
    attribute_name: str,
    boundary: str,
):
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    bundle = None
    if boundary == "require":
        bundle = load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )
    original = vars(DecisionRow)[attribute_name]
    calls = []

    def hostile_mutator(self, *args):
        calls.append(args)
        return original(self, *args)

    monkeypatch.setattr(DecisionRow, attribute_name, hostile_mutator)
    with pytest.raises(QcGlobalInputBundleError):
        if boundary == "load":
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
        else:
            assert bundle is not None
            require_synthetic_qc_global_input_bundle(bundle)
    assert calls == []


def test_returned_decision_row_remains_frozen_for_assignment_and_deletion():
    row = _load().decisions[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.row_id = "changed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        del row.row_id


@pytest.mark.parametrize("mutation", ("descriptor", "fget_code"))
@pytest.mark.parametrize(
    ("owner_class", "property_name", "boundary"),
    (
        (SyntheticQcGlobalInputBundle, "provider_access_available", "load"),
        (SyntheticQcRunCandidate, "upload_available", "load"),
        (EventStudyBatch, "result_publication_available", "collect"),
    ),
)
def test_false_authority_property_changes_are_rejected_before_execution(
    monkeypatch,
    owner_class: type,
    property_name: str,
    boundary: str,
    mutation: str,
):
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    bundle = load_synthetic_qc_global_input_bundle(
        run_candidate=candidate,
        manifest_bytes=manifest_bytes,
        partition_payloads=partition_payloads,
    )
    calls = []
    original_property = vars(owner_class)[property_name]
    assert type(original_property) is property
    assert original_property.fget is not None

    def invoke_boundary():
        with pytest.raises(QcGlobalInputBundleError):
            if boundary == "load":
                load_synthetic_qc_global_input_bundle(
                    run_candidate=candidate,
                    manifest_bytes=manifest_bytes,
                    partition_payloads=partition_payloads,
                )
            else:
                collect_synthetic_event_study_from_global_input_bundle(bundle)

    if mutation == "descriptor":
        class HostilePropertyDescriptor:
            def __get__(self, instance, owner=None):
                calls.append((instance, owner))
                return original_property.__get__(instance, owner)

        monkeypatch.setattr(
            owner_class,
            property_name,
            HostilePropertyDescriptor(),
        )
        invoke_boundary()
    else:
        fget = original_property.fget
        dependency_globals = fget.__globals__
        probe_name = "_ARV2_TEST_AUTHORITY_PROPERTY_CALLS"
        missing = object()
        previous_probe = dependency_globals.get(probe_name, missing)
        original_code = fget.__code__
        dependency_globals[probe_name] = calls
        fget.__code__ = _hostile_true_authority_property.__code__
        try:
            invoke_boundary()
        finally:
            fget.__code__ = original_code
            if previous_probe is missing:
                del dependency_globals[probe_name]
            else:
                dependency_globals[probe_name] = previous_probe
    assert calls == []


def test_hostile_decision_dataclass_registry_descriptor_is_never_bound(
    monkeypatch,
):
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    original_registry = vars(DecisionRow)["__dataclass_fields__"]
    calls = []

    class HostileRegistryDescriptor:
        def __get__(self, instance, owner=None):
            calls.append((instance, owner))
            return original_registry

    monkeypatch.setattr(
        DecisionRow,
        "__dataclass_fields__",
        HostileRegistryDescriptor(),
    )
    with pytest.raises(QcGlobalInputBundleError):
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )
    assert calls == []


def test_in_place_decision_dataclass_field_replacement_has_zero_callbacks():
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    registry = vars(DecisionRow)["__dataclass_fields__"]
    original_field = registry["row_id"]
    calls = []

    class HostileField(dataclasses.Field):
        def __getattribute__(self, name):
            calls.append(name)
            raise AssertionError("hostile dataclass field was inspected")

    hostile_field = HostileField(
        default=dataclasses.MISSING,
        default_factory=dataclasses.MISSING,
        init=True,
        repr=True,
        hash=None,
        compare=True,
        metadata=None,
        kw_only=False,
    )
    calls.clear()
    registry["row_id"] = hostile_field
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        registry["row_id"] = original_field
    assert calls == []


def test_in_place_exact_dataclass_field_identity_change_is_rejected():
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    registry = vars(DecisionRow)["__dataclass_fields__"]
    original_field = registry["row_id"]
    replacement = dataclasses.field()
    replacement.name = "row_id"
    replacement._field_type = original_field._field_type
    registry["row_id"] = replacement
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        registry["row_id"] = original_field


def test_decision_init_closure_cell_change_is_rejected_before_execution():
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    implementation = vars(DecisionRow)["__init__"]
    assert implementation.__code__.co_freevars == (
        "__dataclass_builtins_object__",
    )
    assert implementation.__closure__ is not None
    cell = implementation.__closure__[0]
    original_value = cell.cell_contents
    calls = []

    class HostileBuiltinsObject:
        def __getattribute__(self, name):
            calls.append(name)
            if name == "__setattr__":
                return object.__setattr__
            return object.__getattribute__(self, name)

    cell.cell_contents = HostileBuiltinsObject()
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        cell.cell_contents = original_value
    assert calls == []


def test_decode_partition_code_change_is_rejected_before_delegation():
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    implementation = bundle_module._decode_partition
    original_code = implementation.__code__
    dependency_globals = implementation.__globals__
    probe_name = "_ARV2_TEST_DECODE_PARTITION_CALLS"
    missing = object()
    previous_probe = dependency_globals.get(probe_name, missing)
    calls = []
    dependency_globals[probe_name] = calls
    implementation.__code__ = _hostile_decode_partition.__code__
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        implementation.__code__ = original_code
        if previous_probe is missing:
            del dependency_globals[probe_name]
        else:
            dependency_globals[probe_name] = previous_probe
    assert calls == []


def test_sealed_loader_implementation_cell_change_preserves_the_checker():
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    loader = bundle_module.load_synthetic_qc_global_input_bundle
    assert loader.__closure__ is not None
    freevars = loader.__code__.co_freevars
    implementation_cell = loader.__closure__[freevars.index("implementation_a")]
    checker_cells = tuple(
        loader.__closure__[index]
        for index, name in enumerate(freevars)
        if name.startswith("static_check_")
    )
    assert len(checker_cells) == 3
    original_implementation = implementation_cell.cell_contents
    original_checkers = tuple(cell.cell_contents for cell in checker_cells)
    assert len(set(original_checkers)) == 1
    calls = []

    def hostile_implementation(**kwargs):
        calls.append(kwargs)
        return original_implementation(**kwargs)

    implementation_cell.cell_contents = hostile_implementation
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        implementation_cell.cell_contents = original_implementation
    assert tuple(cell.cell_contents for cell in checker_cells) == original_checkers
    assert calls == []


def test_sealed_loader_checker_cell_change_never_runs_the_replacement():
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    loader = bundle_module.load_synthetic_qc_global_input_bundle
    assert loader.__closure__ is not None
    freevars = loader.__code__.co_freevars
    checker_cell = loader.__closure__[freevars.index("static_check_a")]
    original_checker = checker_cell.cell_contents
    calls = []

    def hostile_checker():
        calls.append(True)
        return original_checker()

    checker_cell.cell_contents = hostile_checker
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        checker_cell.cell_contents = original_checker
    assert calls == []


def test_empty_generated_init_closure_cell_is_normalized_and_restored():
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    implementation = vars(DecisionRow)["__init__"]
    assert implementation.__closure__ is not None
    cell = implementation.__closure__[0]
    original_value = cell.cell_contents
    del cell.cell_contents
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        cell.cell_contents = original_value


@pytest.mark.parametrize(
    "closure_name",
    (
        "implementation_a",
        "implementation_b",
        "implementation_c",
        "static_check_a",
        "static_check_b",
        "static_check_c",
    ),
)
def test_each_empty_sealed_loader_closure_cell_is_normalized_and_restored(
    closure_name: str,
):
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    loader = bundle_module.load_synthetic_qc_global_input_bundle
    assert loader.__closure__ is not None
    freevars = loader.__code__.co_freevars
    cell = loader.__closure__[freevars.index(closure_name)]
    original_value = cell.cell_contents
    del cell.cell_contents
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        cell.cell_contents = original_value


@pytest.mark.parametrize(
    "entrypoint",
    ("renderer", "loader", "validator", "composer"),
)
@pytest.mark.parametrize(
    "guard_name",
    ("static_guard_a", "static_guard_b", "static_guard_c"),
)
def test_each_empty_public_static_guard_is_normalized_before_cache_callbacks(
    entrypoint: str,
    guard_name: str,
):
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    bundle = load_synthetic_qc_global_input_bundle(
        run_candidate=candidate,
        manifest_bytes=manifest_bytes,
        partition_payloads=partition_payloads,
    )
    wrappers = {
        "renderer": bundle_module.render_qc_global_input_bundle_schema_bytes,
        "loader": bundle_module.load_synthetic_qc_global_input_bundle,
        "validator": bundle_module.require_synthetic_qc_global_input_bundle,
        "composer": (
            bundle_module.collect_synthetic_event_study_from_global_input_bundle
        ),
    }
    operations = {
        "renderer": lambda: wrappers["renderer"](),
        "loader": lambda: wrappers["loader"](
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        ),
        "validator": lambda: wrappers["validator"](bundle),
        "composer": lambda: wrappers["composer"](bundle),
    }
    wrapper = wrappers[entrypoint]
    assert wrapper.__closure__ is not None
    freevars = wrapper.__code__.co_freevars
    cell = wrapper.__closure__[freevars.index(guard_name)]
    original_value = cell.cell_contents
    axis_before = event_study_module._reviewed_session_axis.cache_info()
    index_before = event_study_module._reviewed_session_index.cache_info()
    del cell.cell_contents
    try:
        with pytest.raises(QcGlobalInputBundleError):
            operations[entrypoint]()
    finally:
        cell.cell_contents = original_value
    axis_after = event_study_module._reviewed_session_axis.cache_info()
    index_after = event_study_module._reviewed_session_index.cache_info()
    assert axis_after == axis_before
    assert index_after == index_before


def test_static_checker_code_change_is_rejected_by_unmodified_public_wrapper():
    document = json.loads(render_qc_global_input_bundle_schema_bytes())
    assert document["admitted_truth"]["runtime_code_authenticated"] is False
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    implementation = bundle_module._require_static_contract
    assert implementation.__code__.co_freevars == ()
    assert _hostile_require_static_contract.__code__.co_freevars == ()
    original_code = implementation.__code__
    probe_name = "_ARV2_TEST_REQUIRE_STATIC_CONTRACT_EXECUTED"
    module_globals = implementation.__globals__
    assert probe_name not in module_globals
    implementation.__code__ = _hostile_require_static_contract.__code__
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
        assert probe_name not in module_globals
    finally:
        implementation.__code__ = original_code
        module_globals.pop(probe_name, None)


def test_stdlib_json_code_change_is_rejected_before_delegation():
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    implementation = json.dumps
    original_code = implementation.__code__
    implementation.__code__ = _hostile_json_dumps.__code__
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        implementation.__code__ = original_code


def test_bundle_module_builtin_shadow_is_rejected_before_callback():
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    module_globals = bundle_module.__dict__
    binding_name = "getattr"
    missing = object()
    previous = module_globals.get(binding_name, missing)
    original_getattr = getattr
    calls = []

    def hostile_getattr(*args):
        calls.append(args)
        return original_getattr(*args)

    module_globals[binding_name] = hostile_getattr
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        if previous is missing:
            del module_globals[binding_name]
        else:
            module_globals[binding_name] = previous
    assert calls == []


def test_bundle_module_type_shadow_is_rejected_before_callback():
    module_globals = bundle_module.__dict__
    binding_name = "type"
    assert binding_name not in module_globals
    original_type = type
    calls = []

    def hostile_type(*args):
        calls.append(args)
        return original_type(*args)

    module_globals[binding_name] = hostile_type
    try:
        with pytest.raises(QcGlobalInputBundleError):
            render_qc_global_input_bundle_schema_bytes()
    finally:
        del module_globals[binding_name]
    assert calls == []


@pytest.mark.parametrize(
    "binding_name",
    (
        "_PINNED_OBJECT_GETATTRIBUTE",
        "_PINNED_ANY",
        "_PINNED_DICT_ITEMS",
        "_PINNED_TUPLE",
        "_PINNED_TUPLE_LEN",
        "_PINNED_TUPLE_GETITEM",
    ),
)
def test_pinned_bootstrap_primitive_change_is_rejected_before_callback(
    binding_name: str,
):
    original = getattr(bundle_module, binding_name)
    calls = []

    def hostile(*args):
        calls.append(args)
        return original(*args)

    setattr(bundle_module, binding_name, hostile)
    try:
        with pytest.raises(QcGlobalInputBundleError):
            render_qc_global_input_bundle_schema_bytes()
    finally:
        setattr(bundle_module, binding_name, original)
    assert calls == []


def test_bundle_module_hostile_builtin_shadow_key_has_zero_callbacks():
    class HostileKey(str):
        calls = 0

        def __hash__(self):
            type(self).calls += 1
            return super().__hash__()

        def __eq__(self, other):
            type(self).calls += 1
            return super().__eq__(other)

    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    module_globals = bundle_module.__dict__
    assert "getattr" not in module_globals
    hostile_key = HostileKey("getattr")
    calls = []

    def hostile_getattr(*args):
        calls.append(args)
        return getattr(*args)

    module_globals[hostile_key] = hostile_getattr
    boundary_key_calls = None
    try:
        HostileKey.calls = 0
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
        boundary_key_calls = HostileKey.calls
    finally:
        del module_globals[hostile_key]
    assert boundary_key_calls == 0
    assert calls == []


def test_imported_trading_sessions_code_change_is_rejected_before_execution():
    bundle = _load()
    implementation = event_study_module.trading_sessions
    original_code = implementation.__code__
    implementation.__code__ = _hostile_trading_sessions.__code__
    try:
        with pytest.raises(QcGlobalInputBundleError):
            collect_synthetic_event_study_from_global_input_bundle(bundle)
    finally:
        implementation.__code__ = original_code


def test_nyse_schedule_shadow_is_refused_before_callback_in_subprocess():
    script = r'''
from data import exchange_calendar
from research.analyst_revisions_v2_qc import event_study
from research.analyst_revisions_v2_qc.global_input_bundle import (
    QcGlobalInputBundleError,
    collect_synthetic_event_study_from_global_input_bundle,
)
from tests.analyst_revisions_v2.test_qc_global_input_bundle import _load

bundle = _load()
axis_cache = event_study._reviewed_session_axis
index_cache = event_study._reviewed_session_index
original_axis = axis_cache()
original_index = index_cache()
calendar = exchange_calendar._NYSE
missing = object()
original_own_schedule = vars(calendar).get("schedule", missing)
calls = []

def hostile_schedule(*args, **kwargs):
    calls.append((args, kwargs))
    raise AssertionError("shadowed NYSE schedule executed")

setattr(calendar, "schedule", hostile_schedule)
axis_cache.cache_clear()
index_cache.cache_clear()
try:
    try:
        collect_synthetic_event_study_from_global_input_bundle(bundle)
    except QcGlobalInputBundleError:
        pass
    else:
        raise AssertionError("composer accepted a shadowed NYSE schedule")
    if calls:
        raise AssertionError("shadowed NYSE schedule executed before refusal")
finally:
    if original_own_schedule is missing:
        delattr(calendar, "schedule")
    else:
        setattr(calendar, "schedule", original_own_schedule)
    axis_cache.cache_clear()
    index_cache.cache_clear()
    restored_axis = axis_cache()
    restored_index = index_cache()
    if restored_axis != original_axis:
        raise AssertionError("reviewed session-axis value was not restored")
    if tuple(restored_index.items()) != tuple(original_index.items()):
        raise AssertionError("reviewed session-index value was not restored")
    if axis_cache.cache_info().currsize != 1:
        raise AssertionError("reviewed session-axis cache was not repopulated")
    if index_cache.cache_info().currsize != 1:
        raise AssertionError("reviewed session-index cache was not repopulated")
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_dataclasses_module_class_change_has_zero_callbacks_in_subprocess():
    script = r'''
import dataclasses
from types import ModuleType

from research.analyst_revisions_v2_qc.global_input_bundle import (
    QcGlobalInputBundleError,
    load_synthetic_qc_global_input_bundle,
)
from tests.analyst_revisions_v2.test_qc_global_input_bundle import (
    _active_rows,
    _wire_inputs,
)

candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
original_class = dataclasses.__class__
calls = []

class HostileModule(ModuleType):
    def __getattribute__(self, name):
        calls.append(name)
        return ModuleType.__getattribute__(self, name)

dataclasses.__class__ = HostileModule
try:
    try:
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )
    except QcGlobalInputBundleError:
        pass
    else:
        raise AssertionError("loader accepted a changed dataclasses module class")
finally:
    dataclasses.__class__ = original_class
if calls:
    raise AssertionError("changed dataclasses module class received a callback")
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_hashlib_sha256_equal_hostile_key_has_zero_callbacks_in_subprocess():
    script = r'''
import hashlib

from research.analyst_revisions_v2_qc.global_input_bundle import (
    QcGlobalInputBundleError,
    load_synthetic_qc_global_input_bundle,
    render_qc_global_input_bundle_schema_bytes,
)
from tests.analyst_revisions_v2.test_qc_global_input_bundle import (
    _active_rows,
    _wire_inputs,
)

candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
module_dict = hashlib.__dict__
original_items = tuple(module_dict.items())
original_key, original_value = next(
    item
    for item in original_items
    if type(item[0]) is str and item[0] == "sha256"
)

class HostileKey(str):
    calls = 0

    def __eq__(self, other):
        type(self).calls += 1
        return super().__eq__(other)

    __hash__ = str.__hash__

hostile_key = HostileKey("sha256")
del module_dict[original_key]
module_dict[hostile_key] = original_value
HostileKey.calls = 0
try:
    for operation in (
        render_qc_global_input_bundle_schema_bytes,
        lambda: load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        ),
    ):
        try:
            operation()
        except QcGlobalInputBundleError:
            pass
        else:
            raise AssertionError("public boundary accepted hostile sha256 key")
finally:
    module_dict.clear()
    module_dict.update(original_items)
if HostileKey.calls:
    raise AssertionError("hostile sha256 key received an equality callback")
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_builtins_any_equal_hostile_key_has_zero_callbacks_in_subprocess():
    script = r'''
from research.analyst_revisions_v2_qc import global_input_bundle
from research.analyst_revisions_v2_qc.global_input_bundle import (
    QcGlobalInputBundleError,
    render_qc_global_input_bundle_schema_bytes,
)

builtins_dict = global_input_bundle.__dict__["__builtins__"]
original_items = tuple(builtins_dict.items())
original_key, original_value = next(
    item
    for item in original_items
    if type(item[0]) is str and item[0] == "any"
)
dict_clear = dict.clear
dict_update = dict.update

class HostileKey(str):
    calls = 0

    def __eq__(self, other):
        type(self).calls += 1
        return super().__eq__(other)

    __hash__ = str.__hash__

hostile_key = HostileKey("any")
del builtins_dict[original_key]
builtins_dict[hostile_key] = original_value
HostileKey.calls = 0
try:
    try:
        render_qc_global_input_bundle_schema_bytes()
    except QcGlobalInputBundleError:
        pass
    else:
        raise AssertionError("renderer accepted an equal hostile builtin key")
finally:
    dict_clear(builtins_dict)
    dict_update(builtins_dict, original_items)
if HostileKey.calls:
    raise AssertionError("hostile builtin key received an equality callback")
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("mutation", ("__new__", "__init__"))
def test_cache_info_constructor_change_has_zero_callbacks_in_subprocess(
    mutation: str,
):
    script = r'''
import sys

from research.analyst_revisions_v2_qc import event_study
from research.analyst_revisions_v2_qc.global_input_bundle import (
    QcGlobalInputBundleError,
    render_qc_global_input_bundle_schema_bytes,
)

mutation = sys.argv[1]
cache_info_class = type(event_study._reviewed_session_axis.cache_info())
missing = object()
original_raw = vars(cache_info_class).get(mutation, missing)
calls = []
if mutation == "__new__":
    original_delegate = cache_info_class.__new__

    def hostile_new(cls, *args, **kwargs):
        calls.append((args, kwargs))
        return original_delegate(cls, *args, **kwargs)

    replacement = staticmethod(hostile_new)
else:
    original_delegate = cache_info_class.__init__

    def hostile_init(self, *args, **kwargs):
        calls.append((args, kwargs))
        return original_delegate(self)

    replacement = hostile_init

setattr(cache_info_class, mutation, replacement)
try:
    try:
        render_qc_global_input_bundle_schema_bytes()
    except QcGlobalInputBundleError:
        pass
    else:
        raise AssertionError("schema renderer accepted changed CacheInfo construction")
finally:
    if original_raw is missing:
        delattr(cache_info_class, mutation)
    else:
        setattr(cache_info_class, mutation, original_raw)
if calls:
    raise AssertionError("changed CacheInfo constructor ran before refusal")
'''
    completed = subprocess.run(
        [sys.executable, "-c", script, mutation],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_json_scanner_module_class_change_has_zero_callbacks_in_subprocess():
    script = r'''
import json
from types import ModuleType

from research.analyst_revisions_v2_qc.global_input_bundle import (
    QcGlobalInputBundleError,
    collect_synthetic_event_study_from_global_input_bundle,
    load_synthetic_qc_global_input_bundle,
)
from tests.analyst_revisions_v2.test_qc_global_input_bundle import (
    _active_rows,
    _wire_inputs,
)

candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
bundle = load_synthetic_qc_global_input_bundle(
    run_candidate=candidate,
    manifest_bytes=manifest_bytes,
    partition_payloads=partition_payloads,
)
scanner = json.JSONDecoder.__init__.__globals__["scanner"]
original_class = scanner.__class__
attribute_calls = []
make_scanner_calls = []

class HostileScannerModule(ModuleType):
    def __getattribute__(self, name):
        attribute_calls.append(name)
        value = ModuleType.__getattribute__(self, name)
        if name != "make_scanner":
            return value

        def hostile_make_scanner(*args, **kwargs):
            make_scanner_calls.append((args, kwargs))
            return value(*args, **kwargs)

        return hostile_make_scanner

scanner.__class__ = HostileScannerModule
try:
    for operation in (
        lambda: load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        ),
        lambda: collect_synthetic_event_study_from_global_input_bundle(bundle),
    ):
        try:
            operation()
        except QcGlobalInputBundleError:
            pass
        else:
            raise AssertionError("public boundary accepted changed scanner class")
finally:
    scanner.__class__ = original_class
if attribute_calls:
    raise AssertionError("changed scanner module received attribute callbacks")
if make_scanner_calls:
    raise AssertionError("changed scanner make_scanner was executed")
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize(
    "wrapper_name",
    ("_reviewed_session_axis", "_reviewed_session_index"),
)
def test_lru_cache_info_shadow_has_zero_callbacks_in_subprocess(
    wrapper_name: str,
):
    script = f'''
from research.analyst_revisions_v2_qc import event_study
from research.analyst_revisions_v2_qc.global_input_bundle import (
    QcGlobalInputBundleError,
    collect_synthetic_event_study_from_global_input_bundle,
)
from tests.analyst_revisions_v2.test_qc_global_input_bundle import _load

bundle = _load()
wrapper = getattr(event_study, {wrapper_name!r})
missing = object()
original_own_cache_info = vars(wrapper).get("cache_info", missing)
calls = []

def hostile_cache_info():
    calls.append(True)
    return type(wrapper).cache_info(wrapper)

setattr(wrapper, "cache_info", hostile_cache_info)
try:
    try:
        collect_synthetic_event_study_from_global_input_bundle(bundle)
    except QcGlobalInputBundleError:
        pass
    else:
        raise AssertionError("composer accepted a shadowed cache_info")
finally:
    if original_own_cache_info is missing:
        delattr(wrapper, "cache_info")
    else:
        setattr(wrapper, "cache_info", original_own_cache_info)
if calls:
    raise AssertionError("shadowed cache_info executed before refusal")
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_cache_info_getitem_is_not_used_by_static_validation_subprocess():
    script = r'''
from research.analyst_revisions_v2_qc import event_study
from research.analyst_revisions_v2_qc.global_input_bundle import (
    QcGlobalInputBundleError,
    load_synthetic_qc_global_input_bundle,
)
from tests.analyst_revisions_v2.test_qc_global_input_bundle import (
    _active_rows,
    _wire_inputs,
)

candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
cache_info_class = type(event_study._reviewed_session_axis.cache_info())
missing = object()
original_own_getitem = vars(cache_info_class).get("__getitem__", missing)
calls = []

def hostile_getitem(self, key):
    calls.append(key)
    return tuple.__getitem__(self, key)

setattr(cache_info_class, "__getitem__", hostile_getitem)
try:
    try:
        load_synthetic_qc_global_input_bundle(
            run_candidate=candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )
    except QcGlobalInputBundleError:
        pass
    else:
        raise AssertionError("loader accepted changed CacheInfo.__getitem__")
finally:
    if original_own_getitem is missing:
        delattr(cache_info_class, "__getitem__")
    else:
        setattr(cache_info_class, "__getitem__", original_own_getitem)
if calls:
    raise AssertionError("CacheInfo.__getitem__ ran during static validation")
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_parent_horizon_root_change_is_rejected_before_iteration():
    class HostileHorizons(tuple):
        calls = 0

        def __iter__(self):
            type(self).calls += 1
            return super().__iter__()

        def __len__(self):
            type(self).calls += 1
            return super().__len__()

    bundle = _load()
    original = event_study_module.HORIZONS
    event_study_module.HORIZONS = HostileHorizons(original)
    try:
        with pytest.raises(QcGlobalInputBundleError):
            collect_synthetic_event_study_from_global_input_bundle(bundle)
    finally:
        event_study_module.HORIZONS = original
    assert HostileHorizons.calls == 0


def test_nested_event_study_geometry_mutation_is_rejected_before_core_call():
    def disclosed_mapping(proxy):
        captured = []

        class ReflectiveProbe:
            def __eq__(self, other):
                captured.append(other)
                return False

        assert (proxy == ReflectiveProbe()) is False
        assert len(captured) == 1 and type(captured[0]) is dict
        return captured[0]

    bundle = _load()
    accepted_batch = collect_synthetic_event_study_from_global_input_bundle(bundle)
    outer = disclosed_mapping(
        event_study_module._EVALUATION_SEGMENT_HORIZON_BOUNDS
    )
    inner = disclosed_mapping(outer["arv2-wf-test-2021"])
    original_bound = inner[60]
    calls = []

    def hostile_core(_bundle):
        calls.append(True)
        return accepted_batch

    inner[60] = (date(2021, 4, 1), original_bound[1])
    try:
        with pytest.raises(QcGlobalInputBundleError):
            bundle_module._COMPOSER_IMPLEMENTATION(
                bundle,
                _call_core=hostile_core,
                _validate_batch=lambda _batch: True,
            )
    finally:
        inner[60] = original_bound
    assert calls == []


@pytest.mark.parametrize("codec_name", ("JSONDecoder", "JSONEncoder"))
def test_json_codec_alias_subclass_is_rejected_before_construction(
    codec_name: str,
):
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    original = getattr(json, codec_name)
    calls = []

    class HostileCodec(original):
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))
            super().__init__(*args, **kwargs)

    setattr(json, codec_name, HostileCodec)
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        setattr(json, codec_name, original)
    assert calls == []


def test_dataclasses_fields_builtin_shadow_is_rejected_before_callback():
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    dependency_globals = dataclasses.fields.__globals__
    binding_name = "getattr"
    missing = object()
    previous = dependency_globals.get(binding_name, missing)
    original_getattr = getattr
    calls = []

    def hostile_getattr(*args):
        calls.append(args)
        return original_getattr(*args)

    dependency_globals[binding_name] = hostile_getattr
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        if previous is missing:
            del dependency_globals[binding_name]
        else:
            dependency_globals[binding_name] = previous
    assert calls == []


def test_aggregate_census_rebind_is_rejected_before_forged_census_runs():
    bundle = _load()
    original = EventStudyBatch.aggregate_census
    calls = []

    def hostile_census(_self):
        calls.append(True)
        return {"forged": True}

    EventStudyBatch.aggregate_census = hostile_census
    try:
        with pytest.raises(QcGlobalInputBundleError):
            batch = collect_synthetic_event_study_from_global_input_bundle(bundle)
            batch.aggregate_census()
    finally:
        EventStudyBatch.aggregate_census = original
    assert calls == []


def test_aggregate_census_counter_global_change_is_rejected_before_use():
    bundle = _load()
    original = event_study_module.Counter
    calls = []

    class HostileCounter(original):
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))
            super().__init__(*args, **kwargs)

    event_study_module.Counter = HostileCounter
    try:
        with pytest.raises(QcGlobalInputBundleError):
            batch = collect_synthetic_event_study_from_global_input_bundle(bundle)
            batch.aggregate_census()
    finally:
        event_study_module.Counter = original
    assert calls == []


@pytest.mark.parametrize("method_name", ("__init__", "update"))
def test_aggregate_census_counter_method_change_is_rejected_before_use(
    method_name: str,
):
    bundle = _load()
    counter_class = event_study_module.Counter
    original = vars(counter_class)[method_name]
    calls = []

    def hostile_method(self, *args, **kwargs):
        calls.append((args, kwargs))
        return original(self, *args, **kwargs)

    setattr(counter_class, method_name, hostile_method)
    try:
        with pytest.raises(QcGlobalInputBundleError):
            batch = collect_synthetic_event_study_from_global_input_bundle(bundle)
            batch.aggregate_census()
    finally:
        setattr(counter_class, method_name, original)
    assert calls == []


def test_counter_mapping_alias_change_has_zero_callbacks_in_subprocess():
    script = r'''
from collections import Counter

from research.analyst_revisions_v2_qc.global_input_bundle import (
    QcGlobalInputBundleError,
    collect_synthetic_event_study_from_global_input_bundle,
)
from tests.analyst_revisions_v2.test_qc_global_input_bundle import _load

bundle = _load()
collections_abc = Counter.update.__globals__["_collections_abc"]
original_mapping = collections_abc.Mapping
mapping_calls = []
accessor_calls = []

class RecordingMappingMeta(type(original_mapping)):
    def __instancecheck__(cls, instance):
        mapping_calls.append(instance)
        return isinstance(instance, original_mapping)

class RecordingMapping(original_mapping, metaclass=RecordingMappingMeta):
    pass

mapping_calls.clear()
collections_abc.Mapping = RecordingMapping
try:
    try:
        batch = collect_synthetic_event_study_from_global_input_bundle(bundle)
    except QcGlobalInputBundleError:
        pass
    else:
        accessor_calls.append(True)
        batch.aggregate_census()
        raise AssertionError("composer accepted changed Mapping authority")
finally:
    collections_abc.Mapping = original_mapping
if mapping_calls:
    raise AssertionError("changed Mapping authority received a callback")
if accessor_calls:
    raise AssertionError("aggregate census accessor was reached")
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_counter_mapping_equal_hostile_key_has_zero_callbacks_in_subprocess():
    script = r'''
from collections import Counter

from research.analyst_revisions_v2_qc.global_input_bundle import (
    QcGlobalInputBundleError,
    collect_synthetic_event_study_from_global_input_bundle,
)
from tests.analyst_revisions_v2.test_qc_global_input_bundle import _load

bundle = _load()
collections_abc = Counter.update.__globals__["_collections_abc"]
module_dict = collections_abc.__dict__
original_items = tuple(module_dict.items())
original_key, original_value = next(
    item
    for item in original_items
    if type(item[0]) is str and item[0] == "Mapping"
)

class HostileKey(str):
    calls = 0

    def __eq__(self, other):
        type(self).calls += 1
        return super().__eq__(other)

    __hash__ = str.__hash__

hostile_key = HostileKey("Mapping")
del module_dict[original_key]
module_dict[hostile_key] = original_value
HostileKey.calls = 0
try:
    try:
        collect_synthetic_event_study_from_global_input_bundle(bundle)
    except QcGlobalInputBundleError:
        pass
    else:
        raise AssertionError("composer accepted an equal hostile Mapping key")
finally:
    module_dict.clear()
    module_dict.update(original_items)
if HostileKey.calls:
    raise AssertionError("hostile Mapping key received an equality callback")
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_abcmeta_instancecheck_change_has_zero_callbacks_in_subprocess():
    script = r'''
import abc

from research.analyst_revisions_v2_qc.global_input_bundle import (
    QcGlobalInputBundleError,
    collect_synthetic_event_study_from_global_input_bundle,
)
from tests.analyst_revisions_v2.test_qc_global_input_bundle import _load

bundle = _load()
original_raw_instancecheck = vars(abc.ABCMeta)["__instancecheck__"]
original_delegate = abc.ABCMeta.__instancecheck__
instancecheck_calls = []
accessor_calls = []

def hostile_instancecheck(self, instance):
    instancecheck_calls.append((self, instance))
    return original_delegate(self, instance)

abc.ABCMeta.__instancecheck__ = hostile_instancecheck
try:
    try:
        batch = collect_synthetic_event_study_from_global_input_bundle(bundle)
    except QcGlobalInputBundleError:
        pass
    else:
        accessor_calls.append(True)
        batch.aggregate_census()
        raise AssertionError("composer accepted changed ABCMeta authority")
finally:
    abc.ABCMeta.__instancecheck__ = original_raw_instancecheck
if instancecheck_calls:
    raise AssertionError("changed ABCMeta.__instancecheck__ received a callback")
if accessor_calls:
    raise AssertionError("aggregate census accessor was reached")
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_parent_manifest_descriptor_alias_is_rejected_before_construction():
    candidate, manifest_bytes, partition_payloads = _wire_inputs(_active_rows())
    original = global_input_schema_module.GlobalInputPartitionDescriptor
    calls = []

    def hostile_descriptor(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    global_input_schema_module.GlobalInputPartitionDescriptor = hostile_descriptor
    try:
        with pytest.raises(QcGlobalInputBundleError):
            load_synthetic_qc_global_input_bundle(
                run_candidate=candidate,
                manifest_bytes=manifest_bytes,
                partition_payloads=partition_payloads,
            )
    finally:
        global_input_schema_module.GlobalInputPartitionDescriptor = original
    assert calls == []


def test_parent_event_observation_alias_is_rejected_before_construction():
    bundle = _load()
    original = event_study_module.EventStudyObservation
    calls = []

    def hostile_observation(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    event_study_module.EventStudyObservation = hostile_observation
    try:
        with pytest.raises(QcGlobalInputBundleError):
            collect_synthetic_event_study_from_global_input_bundle(bundle)
    finally:
        event_study_module.EventStudyObservation = original
    assert calls == []


def test_parent_transitive_validation_helper_is_rejected_before_delegation():
    bundle = _load()
    original = event_study_module._validate_decision
    calls = []

    def hostile_validation(value):
        calls.append(value)
        return original(value)

    event_study_module._validate_decision = hostile_validation
    try:
        with pytest.raises(QcGlobalInputBundleError):
            collect_synthetic_event_study_from_global_input_bundle(bundle)
    finally:
        event_study_module._validate_decision = original
    assert calls == []


def test_exact_event_study_batch_shell_is_normalized_after_core_return():
    bundle = _load()
    shell = object.__new__(EventStudyBatch)

    with pytest.raises(QcGlobalInputBundleError):
        bundle_module._COMPOSER_IMPLEMENTATION(
            bundle,
            _call_core=lambda _bundle: shell,
            _validate_batch=lambda _batch: True,
        )


@pytest.mark.parametrize(
    ("row_class", "field_name"),
    (
        (event_study_module.EventStudyObservation, "observations"),
        (event_study_module.EventStudyRefusal, "refusals"),
        (SecurityLifecycleCoverage, "security_lifecycle_coverages"),
    ),
)
def test_exact_event_study_row_shells_are_normalized_before_validation(
    row_class: type,
    field_name: str,
):
    bundle = _load()
    batch = collect_synthetic_event_study_from_global_input_bundle(bundle)
    shell = object.__new__(row_class)
    changed_batch = dataclasses.replace(batch, **{field_name: (shell,)})
    validator_calls = []

    def hostile_validator(_batch):
        validator_calls.append(True)
        return True

    with pytest.raises(QcGlobalInputBundleError):
        bundle_module._COMPOSER_IMPLEMENTATION(
            bundle,
            _call_core=lambda _bundle: changed_batch,
            _validate_batch=hostile_validator,
        )
    assert validator_calls == []


def test_exact_terminal_lifecycle_shell_is_refused_before_injected_validator():
    bundle = _load()
    batch = collect_synthetic_event_study_from_global_input_bundle(bundle)
    shell = object.__new__(TerminalLifecycle)
    coverage = dataclasses.replace(
        batch.security_lifecycle_coverages[0],
        terminal_lifecycle=shell,
    )
    changed_batch = dataclasses.replace(
        batch,
        security_lifecycle_coverages=(coverage,),
    )
    validator_calls = []

    def hostile_validator(_batch):
        validator_calls.append(True)
        return True

    with pytest.raises(QcGlobalInputBundleError):
        bundle_module._COMPOSER_IMPLEMENTATION(
            bundle,
            _call_core=lambda _bundle: changed_batch,
            _validate_batch=hostile_validator,
        )
    assert validator_calls == []


def test_deleted_non_key_observation_field_is_refused_before_validator():
    bundle = _load()
    batch = collect_synthetic_event_study_from_global_input_bundle(bundle)
    observation = batch.observations[0]
    original_security_id = observation.security_id
    validator_calls = []

    def hostile_validator(_batch):
        validator_calls.append(True)
        return True

    object.__delattr__(observation, "security_id")
    try:
        with pytest.raises(QcGlobalInputBundleError):
            bundle_module._COMPOSER_IMPLEMENTATION(
                bundle,
                _call_core=lambda _bundle: batch,
                _validate_batch=hostile_validator,
            )
    finally:
        object.__setattr__(observation, "security_id", original_security_id)
    assert validator_calls == []


def test_composer_exposes_only_the_exact_reviewed_horizon_census_and_policy():
    batch = collect_synthetic_event_study_from_global_input_bundle(_load())
    assert HORIZONS == (1, 5, 20, 60)
    assert batch.expected_decision_horizons == 4
    assert tuple(item.horizon_sessions for item in batch.observations) == (
        1,
        5,
        20,
        60,
    )
    assert len(batch.observations) == 4
    assert len(batch.refusals) == 0
    assert len(batch.security_lifecycle_coverages) == 1
    assert batch.terminal_payoff_reinvestment_policy_id == (
        "arv2-terminal-payoff-benchmark-splice-v1"
    )

    terminal = collect_synthetic_event_study_from_global_input_bundle(
        _load(_terminal_rows())
    )
    assert tuple(item.horizon_sessions for item in terminal.observations) == (
        1,
        5,
        20,
        60,
    )
    assert tuple(item.terminal_payoff_used for item in terminal.observations) == (
        False,
        False,
        True,
        True,
    )
    assert terminal.expected_decision_horizons == 4
    assert terminal.terminal_payoff_reinvestment_policy_id == (
        "arv2-terminal-payoff-benchmark-splice-v1"
    )


@pytest.mark.parametrize(
    "field_name",
    (
        "observations",
        "refusals",
        "security_lifecycle_coverages",
        "terminal_lifecycle",
    ),
)
def test_composer_requires_exact_post_output_row_types(field_name: str):
    bundle = _load(_terminal_rows()) if field_name == "terminal_lifecycle" else _load()
    batch = collect_synthetic_event_study_from_global_input_bundle(bundle)
    if field_name == "observations":
        source = batch.observations[0]
    elif field_name == "refusals":
        source = event_study_module.EventStudyRefusal(
            row_id="decision-1",
            decision_session=date(2024, 1, 2),
            horizon_sessions=1,
            security_id="security-1",
            listing_id="listing-1",
            historical_ticker="AAA",
            evaluation_segment_id="holdout_2024_2025",
            fold_id=None,
            common_event_component_id="component-1",
            firm_specific_score=Decimal("1"),
            global_score=Decimal("1"),
            decision_input_sha256=_sha("1"),
            reason="synthetic refusal",
        )
    elif field_name == "security_lifecycle_coverages":
        source = batch.security_lifecycle_coverages[0]
    else:
        source = batch.security_lifecycle_coverages[0].terminal_lifecycle
        assert source is not None

    calls = []
    source_type = type(source)

    class HostileRow(source_type):
        def __getattribute__(self, name):
            calls.append(name)
            return super().__getattribute__(name)

    field_values = {
        field.name: getattr(source, field.name)
        for field in dataclasses.fields(source_type)
    }
    hostile_row = HostileRow(**field_values)
    calls.clear()
    if field_name == "terminal_lifecycle":
        changed_coverage = dataclasses.replace(
            batch.security_lifecycle_coverages[0],
            terminal_lifecycle=hostile_row,
        )
        changed_batch = dataclasses.replace(
            batch,
            security_lifecycle_coverages=(changed_coverage,),
        )
    else:
        changed_batch = dataclasses.replace(batch, **{field_name: (hostile_row,)})

    with pytest.raises(QcGlobalInputBundleError, match="output topology"):
        bundle_module._COMPOSER_IMPLEMENTATION(
            bundle,
            _call_core=lambda _bundle: changed_batch,
            _validate_batch=lambda _batch: True,
        )
    assert calls == []


@pytest.mark.parametrize(
    "target",
    (
        "batch_hash",
        "observation_row_id",
        "observation_horizon",
        "refusal_row_id",
    ),
)
def test_composer_refuses_hostile_output_scalars_before_injected_validator(
    target: str,
):
    class HostileString(str):
        calls = 0

        def __eq__(self, other):
            type(self).calls += 1
            return super().__eq__(other)

        def __hash__(self):
            type(self).calls += 1
            return super().__hash__()

    class HostileInt(int):
        calls = 0

        def __eq__(self, other):
            type(self).calls += 1
            return super().__eq__(other)

        def __hash__(self):
            type(self).calls += 1
            return super().__hash__()

    bundle = _load()
    batch = collect_synthetic_event_study_from_global_input_bundle(bundle)
    if target == "batch_hash":
        changed_batch = dataclasses.replace(
            batch,
            batch_hash=HostileString(batch.batch_hash),
        )
    elif target == "observation_row_id":
        observation = dataclasses.replace(
            batch.observations[0],
            row_id=HostileString(batch.observations[0].row_id),
        )
        changed_batch = dataclasses.replace(
            batch,
            observations=(observation, *batch.observations[1:]),
        )
    elif target == "observation_horizon":
        observation = dataclasses.replace(
            batch.observations[0],
            horizon_sessions=HostileInt(
                batch.observations[0].horizon_sessions
            ),
        )
        changed_batch = dataclasses.replace(
            batch,
            observations=(observation, *batch.observations[1:]),
        )
    else:
        refusal = event_study_module.EventStudyRefusal(
            row_id=HostileString("decision-1"),
            decision_session=date(2024, 1, 2),
            horizon_sessions=1,
            security_id="security-1",
            listing_id="listing-1",
            historical_ticker="AAA",
            evaluation_segment_id="holdout_2024_2025",
            fold_id=None,
            common_event_component_id="component-1",
            firm_specific_score=Decimal("1"),
            global_score=Decimal("1"),
            decision_input_sha256=_sha("1"),
            reason="synthetic refusal",
        )
        changed_batch = dataclasses.replace(batch, refusals=(refusal,))

    HostileString.calls = 0
    HostileInt.calls = 0
    validator_calls = []

    def hostile_validator(_batch):
        validator_calls.append(True)
        return True

    with pytest.raises(QcGlobalInputBundleError):
        bundle_module._COMPOSER_IMPLEMENTATION(
            bundle,
            _call_core=lambda _bundle: changed_batch,
            _validate_batch=hostile_validator,
        )
    assert validator_calls == []
    assert HostileString.calls == 0
    assert HostileInt.calls == 0


def test_bundle_cannot_acquire_external_authority_or_an_action_capability():
    bundle = _load()
    assert bundle.external_bindings
    assert all(value is None for _, value in bundle.external_bindings)
    assert bundle.capabilities
    assert all(value is False for _, value in bundle.capabilities)

    name, _ = bundle.external_bindings[0]
    changed_external = dataclasses.replace(
        bundle,
        external_bindings=((name, "authority"), *bundle.external_bindings[1:]),
    )
    with pytest.raises(QcGlobalInputBundleError):
        require_synthetic_qc_global_input_bundle(changed_external)

    name, _ = bundle.capabilities[0]
    changed_capability = dataclasses.replace(
        bundle,
        capabilities=((name, True), *bundle.capabilities[1:]),
    )
    with pytest.raises(QcGlobalInputBundleError):
        require_synthetic_qc_global_input_bundle(changed_capability)


def test_external_binding_and_capability_inventories_match_the_b1_manifest():
    rows = _active_rows()
    candidate, manifest_payload, partition_payloads = _wire_inputs(rows)
    manifest = build_synthetic_qc_global_input_manifest(run_candidate=candidate)
    bundle = load_synthetic_qc_global_input_bundle(
        run_candidate=candidate,
        manifest_bytes=manifest_payload,
        partition_payloads=partition_payloads,
    )
    assert bundle.external_bindings == manifest.external_bindings
    assert bundle.capabilities == manifest.capabilities


def test_every_external_action_accessor_is_one_literal_false_return():
    expected = {
        "filesystem_read_available",
        "environment_read_available",
        "provider_access_available",
        "licensed_input_read_available",
        "production_manifest_available",
        "production_input_read_available",
        "real_outcome_access_available",
        "runtime_code_authenticated",
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
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    bundle_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SyntheticQcGlobalInputBundle"
    )
    methods = {
        node.name: node
        for node in bundle_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert expected <= methods.keys()
    for name in expected:
        method = methods[name]
        assert len(method.body) == 1
        statement = method.body[0]
        assert isinstance(statement, ast.Return)
        assert isinstance(statement.value, ast.Constant)
        assert statement.value.value is False


def test_bundle_module_has_no_io_dynamic_import_or_qc_runtime_surface():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    forbidden_import_roots = {
        "AlgorithmImports",
        "QuantConnect",
        "builtins",
        "importlib",
        "os",
        "pathlib",
        "requests",
        "socket",
        "subprocess",
        "sys",
        "urllib",
    }
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(item.name.split(".", 1)[0] for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots.isdisjoint(forbidden_import_roots)

    forbidden_names = {
        "AlgorithmImports",
        "ObjectStore",
        "QCAlgorithm",
        "__import__",
        "compile",
        "eval",
        "exec",
        "open",
    }
    assert not {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }.intersection(forbidden_names)
    assert not {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }.intersection(
        {
            "create_project",
            "download",
            "environ",
            "getenv",
            "read_bytes",
            "read_text",
            "request",
            "upload",
            "urlopen",
            "write_bytes",
            "write_text",
        }
    )


def test_public_entrypoint_signatures_accept_only_in_memory_values():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    expected = {
        "_seal_schema_renderer": ((), ()),
        "_seal_loader": (
            (),
            ("run_candidate", "manifest_bytes", "partition_payloads"),
        ),
        "_seal_bundle_validator": (("bundle",), ()),
        "_seal_composer": (("bundle",), ()),
    }
    factories = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in expected
    }
    assert factories.keys() == expected.keys()
    for factory_name, (positional, keyword_only) in expected.items():
        sealed = next(
            node
            for node in factories[factory_name].body
            if isinstance(node, ast.FunctionDef) and node.name == "sealed"
        )
        assert tuple(item.arg for item in sealed.args.posonlyargs) == ()
        assert tuple(item.arg for item in sealed.args.args) == positional
        assert tuple(item.arg for item in sealed.args.kwonlyargs) == keyword_only
        assert sealed.args.defaults == []
        assert all(value is None for value in sealed.args.kw_defaults)
        assert sealed.args.vararg is None
        assert sealed.args.kwarg is None
