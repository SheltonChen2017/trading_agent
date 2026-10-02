from __future__ import annotations

import ast
import base64
import dataclasses
import gzip
import hashlib
import json
import types
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc.formal_run_protocol import ArtifactBinding
from research.analyst_revisions_v2_qc.formal_runtime_projection import (
    AGGREGATE_RESULT_SCHEMA,
    CAPACITY_LIMIT_NAMES,
    CAPACITY_REVIEW_SCHEMA,
    CONTRIBUTION_SEED_SCHEMA,
    DAILY_REQUIREMENT_SCHEMA,
    DECISION_JOIN_SCHEMA,
    ECONOMIC_JOIN_SCHEMA,
    FORMAL_CONTRACT_SCHEMA,
    FORMAL_EVALUATOR_PROJECT_PATH,
    FORMAL_INPUT_PREFIX,
    FORMAL_RESULT_PERSISTENCE_PROJECT_PATH,
    FORMAL_RESULT_FAMILY_OBJECT_COUNT,
    FORMAL_RESULT_WORKING_SET_MEMORY_BYTES,
    INPUT_MANIFEST_SCHEMA,
    MAX_PROJECTED_SOURCE_CHARACTERS,
    MINUTE_REQUIREMENT_SCHEMA,
    REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX,
    REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA,
    PROJECT_NAME,
    SHARD_ROLE_ORDER,
    SUMMARY_CHUNK_PREFIX,
    SUMMARY_META_NAME,
    SUMMARY_RECEIPT_SCHEMA,
    FormalQcRuntimeProjectionError,
    build_daily_market_requirement_id,
    build_formal_qc_compressed_shard,
    build_formal_qc_input_manifest_bytes,
    build_formal_qc_runtime_projection,
    build_minute_market_requirement_id,
    build_qc_object_payload_binding,
    canonical_json_bytes,
    derive_formal_qc_runtime_resource_census,
    formal_cloud_evaluator_binding,
    load_formal_qc_runtime_capacity_binding,
    render_formal_qc_capacity_review_candidate,
    render_formal_qc_runtime_projection_bytes,
    require_formal_qc_compressed_shard,
    require_formal_qc_runtime_projection,
    validate_formal_qc_runtime_resource_candidate,
)


ROOT = Path(__file__).resolve().parents[2]


def _install_projected_persistence_module(monkeypatch, projection):
    projected = next(
        item for item in projection.source_files
        if item.project_path == FORMAL_RESULT_PERSISTENCE_PROJECT_PATH
    )
    name = "research.analyst_revisions_v2_qc.formal_result_persistence"
    module = types.ModuleType(name)
    exec(
        compile(
            projected.content,
            FORMAL_RESULT_PERSISTENCE_PROJECT_PATH,
            "exec",
        ),
        module.__dict__,
    )
    monkeypatch.setitem(__import__("sys").modules, name, module)
    return projected.content.decode("utf-8")


def _artifact(name: str) -> ArtifactBinding:
    payload = name.encode("ascii")
    return ArtifactBinding(
        artifact_id="arv2-" + name,
        content_sha256=hashlib.sha256(payload).hexdigest(),
        artifact_sha256=hashlib.sha256(payload + b"-artifact").hexdigest(),
        byte_count=len(payload),
    )


def _limits() -> dict[str, int]:
    result = {name: 10_000_000 for name in CAPACITY_LIMIT_NAMES}
    result.update(
        max_project_file_count=100,
        max_project_source_character_count=2_000_000,
        max_summary_chunk_characters=4_000,
        max_summary_payload_byte_count=200_000,
        max_summary_chunk_count=100,
        max_single_object_byte_count=48 * 1024 * 1024,
        max_object_store_total_input_byte_count=50 * 1024 * 1024,
        max_node_memory_byte_count=2_000_000_000,
        min_object_store_available_output_byte_count=109_200_000,
        min_object_store_available_output_file_count=26,
    )
    return result


def _capacity(census, **overrides):
    limits = _limits()
    limits.update(overrides)
    candidate = render_formal_qc_capacity_review_candidate(
        census=census, limits=limits
    )
    candidate_hash = hashlib.sha256(candidate).hexdigest()
    seed = {
        "schema": CAPACITY_REVIEW_SCHEMA,
        "candidate_sha256": candidate_hash,
        "receipt_id": None,
        "receipt_sha256": None,
        "limits": limits,
        "representative_full_census_verified": True,
        "target_tier_limits_observed": True,
        "cloud_evaluator_equivalence_verified": True,
        "object_store_input_transport_verified": True,
        "object_store_output_write_once_transport_verified": True,
        "summary_statistics_channel_verified": True,
        "summary_root_result_channel_verified": True,
    }
    receipt_hash = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    seed["receipt_id"] = "arv2-formal-qc-capacity-review-" + receipt_hash
    seed["receipt_sha256"] = receipt_hash
    return load_formal_qc_runtime_capacity_binding(
        candidate_bytes=candidate,
        reviewed_receipt_bytes=canonical_json_bytes(seed),
    )


def _fixture():
    security_id = "AAPL R735QTJ8XC9X"
    publication = "2021-01-04T13:00:00Z"
    rows = {
        "formal_contract": [{"schema": FORMAL_CONTRACT_SCHEMA}],
        "contribution_seeds": [{
            "schema": CONTRIBUTION_SEED_SCHEMA,
            "seed_id": "arv2-seed-test",
            "source_view_id": "current_row_current_vintage_non_pristine_pit",
            "fold_id": "arv2-wf-test-2021",
            "security_id": security_id,
            "minute_requirement_id": build_minute_market_requirement_id(
                security_id=security_id, publication_at_utc=publication
            ),
            "active_intervals": [[100, 101]],
        }],
        "decision_joins": [{
            "schema": DECISION_JOIN_SCHEMA,
            "decision_id": "arv2-decision-test",
            "source_view_id": "current_row_current_vintage_non_pristine_pit",
            "fold_id": "arv2-wf-test-2021",
            "decision_session": "2021-01-04",
            "session_position": 100,
            "security_id": security_id,
            "disposition": "named_preoutcome_refusal",
        }],
        "economic_joins": [{
            "schema": ECONOMIC_JOIN_SCHEMA,
            "source_view_id": "current_row_current_vintage_non_pristine_pit",
            "fold_id": "arv2-wf-test-2021",
            "session": "2021-01-04",
            "session_position": 100,
            "next_session": "2021-01-05",
            "economic_observation_kind": "h20_decision_return_interval",
            "h20_decision_eligible": True,
        }],
        "daily_requirements": [
            {
                "schema": DAILY_REQUIREMENT_SCHEMA,
                "requirement_id": build_daily_market_requirement_id(
                    security_id=security_id, session="2021-01-04"
                ),
                "security_id": security_id,
                "session": "2021-01-04",
            },
            {
                "schema": DAILY_REQUIREMENT_SCHEMA,
                "requirement_id": build_daily_market_requirement_id(
                    security_id=security_id, session="2021-01-05"
                ),
                "security_id": security_id,
                "session": "2021-01-05",
            }
        ],
        "minute_requirements": [
            {
                "schema": MINUTE_REQUIREMENT_SCHEMA,
                "requirement_id": build_minute_market_requirement_id(
                    security_id=security_id, publication_at_utc=publication
                ),
                "security_id": security_id,
                "publication_at_utc": publication,
                "first_active_session_position": 100,
                "last_active_session_position": 100,
            }
        ],
        "terminal_dispositions": [],
    }
    shards = tuple(
        build_formal_qc_compressed_shard(role=role, ordinal=0, rows=rows[role])
        for role in SHARD_ROLE_ORDER
    )
    census = derive_formal_qc_runtime_resource_census(
        shards=shards,
        distinct_security_count=1,
        daily_history_batch_count=2,
        minute_history_batch_count=2,
        maximum_dynamic_subscription_count=1,
        projected_summary_payload_byte_count=100_000,
        projected_summary_chunk_count=34,
    )
    evaluator_source = (ROOT / FORMAL_EVALUATOR_PROJECT_PATH).read_bytes()
    cloud_source = (
        ROOT / "research/analyst_revisions_v2_qc/formal_cloud_evaluator.py"
    ).read_bytes()
    evaluator = formal_cloud_evaluator_binding(
        formal_evaluator_source=evaluator_source,
        cloud_evaluator_source=cloud_source,
    )
    manifest_payload = build_formal_qc_input_manifest_bytes(
        production_input_package=_artifact("formal-input"),
        preopen_control_stage_output=_artifact("preopen-control"),
        runtime_start=date(2020, 1, 1),
        runtime_end=date(2025, 12, 31),
        calculation_as_of_date=date(2026, 1, 2),
        benchmark_security_id="SPY R735QTJ8XC9X",
        shards=shards,
        resource_census=census,
        capacity=_capacity(census),
        cloud_evaluator=evaluator,
    )
    digest = hashlib.sha256(manifest_payload).hexdigest()
    binding = build_qc_object_payload_binding(
        role="input_manifest",
        schema=INPUT_MANIFEST_SCHEMA,
        object_store_key=FORMAL_INPUT_PREFIX + digest + ".json",
        payload=manifest_payload,
    )
    projection = build_formal_qc_runtime_projection(
        input_manifest=binding,
        formal_evaluator_source=evaluator_source,
        cloud_evaluator_source=cloud_source,
    )
    return projection, manifest_payload, shards, census


def test_compact_shards_are_deterministic_content_addressed_and_reauthenticated():
    first = build_formal_qc_compressed_shard(
        role="formal_contract", ordinal=0,
        rows=[{"schema": FORMAL_CONTRACT_SCHEMA, "value": "x"}],
    )
    second = build_formal_qc_compressed_shard(
        role="formal_contract", ordinal=0,
        rows=[{"schema": FORMAL_CONTRACT_SCHEMA, "value": "x"}],
    )
    assert first == second
    assert first.payload[:2] == b"\x1f\x8b"
    assert first.compressed_sha256 in first.object_store_key
    require_formal_qc_compressed_shard(first)
    with pytest.raises(FormalQcRuntimeProjectionError, match="identity"):
        require_formal_qc_compressed_shard(dataclasses.replace(first, row_count=2))


def test_projection_is_exact_sharded_enabled_no_orders_source():
    projection, _, _, _ = _fixture()
    require_formal_qc_runtime_projection(projection)
    assert projection.project_name == PROJECT_NAME
    assert projection.enabled_runtime_source is True
    assert projection.places_orders is False
    assert projection.cloud_compile_verified is False
    assert projection.cloud_execution_verified is False
    assert len(projection.source_files) == 28
    assert max(item.character_count for item in projection.source_files) <= MAX_PROJECTED_SOURCE_CHARACTERS
    for item in projection.source_files:
        assert hashlib.sha256(item.content).hexdigest() == item.content_sha256
        ast.parse(item.content.decode("utf-8"), filename=item.project_path)
    main = projection.source_files[0].content.decode("utf-8")
    assert "DataNormalizationMode.TOTAL_RETURN" in main
    assert "self.history[TradeBar]" in main
    assert "symbols, start, end, Resolution.DAILY" in main
    assert "self.set_start_date(calculation.year" in main
    assert "if calculation <= runtime_end" in main
    assert "except Exception:\n                    history = None" in main
    assert "MAX_DAILY_HISTORY_REQUEST_SPAN_DAYS" in main
    assert "if ended < instant" in main
    assert "begin_compact_formal_evaluation(" in main
    assert "consume_compact_formal_session_block(" in main
    assert "finish_compact_formal_evaluation_output(stream, resamples=19999)" in main
    assert "consume_formal_cloud_evaluation_output" in main
    assert "from research.analyst_revisions_v2_qc.formal_result_persistence import" in main
    assert "persist_formal_result_families(" in main
    assert "begin_formal_market_panel_digest" in main
    assert "input_rows_are_incrementally_decoded" in main
    assert "self._read_shards" not in main
    assert "gzip.compress(root_manifest, compresslevel=9, mtime=0)" in main
    assert "payload_buffer[9] = 255" in main
    assert "gzip-mtime-zero-os-255-plus-urlsafe-base64" in main
    assert SUMMARY_META_NAME in main and SUMMARY_CHUNK_PREFIX in main
    assert "set_summary_statistic" in main
    assert "market_order" not in main.casefold()
    assert "set_holdings" not in main.casefold()
    assert "liquidate(" not in main.casefold()
    helper = next(
        item.content.decode("utf-8") for item in projection.source_files
        if item.project_path == FORMAL_RESULT_PERSISTENCE_PROJECT_PATH
    )
    assert "def persist_formal_result_families(" in helper
    assert "contains_key(key)" in helper
    assert "save_bytes(key, payload) is not True" in helper
    assert "reopened = bytes(read_bytes(key))" in helper
    assert "Object Store key collision changed bytes" in helper


def test_manifest_preserves_period_market_terminal_and_capacity_separation():
    projection, manifest_payload, shards, census = _fixture()
    manifest = json.loads(manifest_payload)
    assert manifest["formal_primary_fold_ids"] == [
        f"arv2-wf-test-{year}" for year in range(2020, 2026)
    ]
    assert manifest["descriptive_sensitivity_fold_ids"] == [
        f"arv2-wf-test-{year}" for year in range(2021, 2026)
    ]
    assert manifest["descriptive_sensitivity_cannot_replace_or_rescue_primary"] is True
    assert manifest["capacity_evidence_is_submission_authority"] is False
    assert manifest["external_owner_execution_authority_pin_required"] is True
    assert manifest["calculation_as_of_date"] == "2026-01-02"
    assert manifest["resource_model"]["history_requests_use_multi_symbol_batches"] is True
    market = manifest["market_contract"]
    assert market["daily_normalization"] == "TotalReturn"
    assert market["publication_price"] == "last_tradable_minute_strictly_before_publication"
    assert market["empty_positive_firm_weight_set_jump"] == "0"
    assert market["qc_delisting_price_is_terminal_payoff"] is False
    assert market["failed_arm_omission_forbidden"] is True
    assert market["shared_market_panel_across_views"] is True
    assert manifest["cloud_evaluator"] == projection.evaluator_source_closure.to_record()
    assert manifest["preopen_control_stage_output"]["artifact_id"] == "arv2-preopen-control"
    assert validate_formal_qc_runtime_resource_candidate(
        manifest_payload=manifest_payload, shards=shards
    ) == census


def test_projection_and_capacity_mutations_fail_closed():
    projection, manifest_payload, shards, census = _fixture()
    with pytest.raises(FormalQcRuntimeProjectionError, match="changed"):
        require_formal_qc_runtime_projection(
            dataclasses.replace(projection, places_orders=True)
        )
    manifest = json.loads(manifest_payload)
    manifest["capacity_review"]["target_tier_limits_observed"] = False
    with pytest.raises(FormalQcRuntimeProjectionError, match="closed"):
        validate_formal_qc_runtime_resource_candidate(
            manifest_payload=canonical_json_bytes(manifest), shards=shards
        )
    manifest = json.loads(manifest_payload)
    manifest["capacity_review"][
        "object_store_output_write_once_transport_verified"
    ] = False
    with pytest.raises(FormalQcRuntimeProjectionError, match="closed"):
        validate_formal_qc_runtime_resource_candidate(
            manifest_payload=canonical_json_bytes(manifest), shards=shards
        )
    manifest = json.loads(manifest_payload)
    manifest["capacity_evidence_is_submission_authority"] = True
    with pytest.raises(FormalQcRuntimeProjectionError, match="submission authority"):
        validate_formal_qc_runtime_resource_candidate(
            manifest_payload=canonical_json_bytes(manifest), shards=shards
        )
    assert census.formal_contract_count == 1
    assert census.contribution_seed_count == 1
    assert census.maximum_compressed_object_byte_count > 0
    assert census.estimated_peak_node_memory_byte_count > 0
    assert (
        census.estimated_peak_node_memory_byte_count
        > FORMAL_RESULT_WORKING_SET_MEMORY_BYTES
    )


def test_projection_document_claims_no_cloud_truth_or_result_read_authority():
    projection, _, _, _ = _fixture()
    document = json.loads(render_formal_qc_runtime_projection_bytes(projection))
    assert document["truth_state"] == {
        "cloud_compile_verified": False,
        "cloud_execution_verified": False,
    }
    result = document["result_channel"]
    assert result["object_store_output_required_for_result_read"] is True
    assert result["summary_statistics_result_channel"] is True
    assert result["summary_statistics_carries_root_only"] is True
    assert result["report_family_object_count"] == 26
    assert document["places_orders"] is False


def test_capacity_node_memory_object_store_and_calculation_boundaries_refuse():
    projection, manifest_payload, shards, census = _fixture()
    assert _capacity(census).submission_authority is False
    assert not hasattr(
        __import__(
            "research.analyst_revisions_v2_qc.formal_runtime_projection",
            fromlist=["require_formal_qc_runtime_resource_readiness"],
        ),
        "require_formal_qc_runtime_resource_readiness",
    )
    manifest = json.loads(manifest_payload)
    kwargs = {
        "production_input_package": _artifact("formal-input"),
        "preopen_control_stage_output": _artifact("preopen-control"),
        "runtime_start": date(2020, 1, 1),
        "runtime_end": date(2025, 12, 31),
        "calculation_as_of_date": date(2026, 1, 2),
        "benchmark_security_id": "SPY R735QTJ8XC9X",
        "shards": shards,
        "resource_census": census,
        "cloud_evaluator": projection.evaluator_source_closure,
    }
    kwargs["capacity"] = _capacity(
        census,
        max_node_memory_byte_count=census.estimated_peak_node_memory_byte_count,
        max_object_store_total_input_byte_count=census.compressed_input_byte_count,
    )
    assert build_formal_qc_input_manifest_bytes(**kwargs)
    kwargs["capacity"] = _capacity(
        census,
        max_node_memory_byte_count=census.estimated_peak_node_memory_byte_count - 1,
    )
    with pytest.raises(FormalQcRuntimeProjectionError, match="estimated_peak"):
        build_formal_qc_input_manifest_bytes(**kwargs)
    kwargs["capacity"] = _capacity(
        census,
        max_object_store_total_input_byte_count=census.compressed_input_byte_count - 1,
    )
    with pytest.raises(FormalQcRuntimeProjectionError, match="Object Store"):
        build_formal_qc_input_manifest_bytes(**kwargs)
    kwargs["capacity"] = _capacity(
        census,
        min_object_store_available_output_byte_count=109_199_999,
    )
    with pytest.raises(FormalQcRuntimeProjectionError, match="output capacity"):
        build_formal_qc_input_manifest_bytes(**kwargs)
    kwargs["capacity"] = _capacity(
        census,
        min_object_store_available_output_file_count=25,
    )
    with pytest.raises(FormalQcRuntimeProjectionError, match="output capacity"):
        build_formal_qc_input_manifest_bytes(**kwargs)
    kwargs["capacity"] = _capacity(census)
    kwargs["calculation_as_of_date"] = date(2025, 12, 31)
    with pytest.raises(FormalQcRuntimeProjectionError, match="runtime dates"):
        build_formal_qc_input_manifest_bytes(**kwargs)


def test_full_run_component_commitments_are_counted_and_capacity_bounded():
    projection, _, shards, base = _fixture()
    decision_rows = [
        {
            "schema": DECISION_JOIN_SCHEMA,
            "decision_id": f"arv2-decision-{index:04d}",
            "source_view_id": "current_row_current_vintage_non_pristine_pit",
            "fold_id": "arv2-wf-test-2021",
            "decision_session": "2021-01-04",
            "session_position": 100,
            "security_id": f"S{index:04d} R735QTJ8X{index:04d}",
            "disposition": "scored_decision",
            "common_event_component_id": f"arv2-component-{index:04d}",
        }
        for index in range(100)
    ]
    expanded = tuple(
        build_formal_qc_compressed_shard(
            role=item.role,
            ordinal=item.ordinal,
            rows=(
                decision_rows
                if item.role == "decision_joins"
                else [
                    json.loads(line)
                    for line in gzip.decompress(item.payload).splitlines()
                ]
            ),
        )
        for item in shards
    )
    census = derive_formal_qc_runtime_resource_census(
        shards=expanded,
        distinct_security_count=base.distinct_security_count,
        daily_history_batch_count=base.daily_history_batch_count,
        minute_history_batch_count=base.minute_history_batch_count,
        maximum_dynamic_subscription_count=base.maximum_dynamic_subscription_count,
        projected_summary_payload_byte_count=base.projected_summary_payload_byte_count,
        projected_summary_chunk_count=base.projected_summary_chunk_count,
    )
    assert base.component_commitment_count == 0
    assert census.component_commitment_count == 100
    assert (
        census.estimated_peak_node_memory_byte_count
        >= base.estimated_peak_node_memory_byte_count + 100 * 1_024
    )
    with pytest.raises(
        FormalQcRuntimeProjectionError, match="component_commitment_count"
    ):
        build_formal_qc_input_manifest_bytes(
            production_input_package=_artifact("formal-input"),
            preopen_control_stage_output=_artifact("preopen-control"),
            runtime_start=date(2020, 1, 1),
            runtime_end=date(2025, 12, 31),
            calculation_as_of_date=date(2026, 1, 2),
            benchmark_security_id="SPY R735QTJ8XC9X",
            shards=expanded,
            resource_census=census,
            capacity=_capacity(census, max_component_commitment_count=99),
            cloud_evaluator=projection.evaluator_source_closure,
        )


def test_generated_daily_collector_does_not_mask_parser_defects(monkeypatch):
    projection, _, _, _ = _fixture()
    source = projection.source_files[0].content.decode("utf-8")
    _install_projected_persistence_module(monkeypatch, projection)
    algorithm_imports = types.ModuleType("AlgorithmImports")
    algorithm_imports.QCAlgorithm = object
    algorithm_imports.TradeBar = type("TradeBar", (), {})
    algorithm_imports.Resolution = types.SimpleNamespace(DAILY="daily", MINUTE="minute")
    algorithm_imports.DataNormalizationMode = types.SimpleNamespace(
        TOTAL_RETURN="total-return"
    )
    algorithm_imports.TimeZones = types.SimpleNamespace(NEW_YORK="New York")
    monkeypatch.setitem(__import__("sys").modules, "AlgorithmImports", algorithm_imports)
    namespace = {}
    exec(compile(source, "projected-main.py", "exec"), namespace)
    algorithm = namespace["AnalystRevisionsV2FormalOutcomeRuntime"]()
    algorithm._calculation_as_of = datetime(2026, 1, 2)
    security_id = "AAPL R735QTJ8XC9X"
    algorithm.symbol = lambda value: types.SimpleNamespace(id=value)
    requirement = [{
        "schema": DAILY_REQUIREMENT_SCHEMA,
        "requirement_id": build_daily_market_requirement_id(
            security_id=security_id, session="2021-01-04"
        ),
        "security_id": security_id,
        "session": "2021-01-04",
    }]

    class History:
        def __init__(self, rows=None, error=None):
            self.rows = rows
            self.error = error

        def __getitem__(self, item):
            return self

        def __call__(self, *args, **kwargs):
            if self.error is not None:
                raise self.error
            return self.rows

    bar = types.SimpleNamespace(
        symbol=types.SimpleNamespace(id=security_id),
        time=datetime(2021, 1, 4),
        open="100",
    )
    algorithm.history = History([bar, bar])
    with pytest.raises(ValueError, match="duplicated"):
        algorithm._collect_daily_observations(requirement, 1)
    bad_bar = types.SimpleNamespace(
        symbol=types.SimpleNamespace(id=security_id),
        time=datetime(2021, 1, 4),
        open="not-a-decimal",
    )
    algorithm.history = History([bad_bar])
    with pytest.raises(ValueError, match="exact decimal"):
        algorithm._collect_daily_observations(requirement, 1)
    algorithm.history = History(error=RuntimeError("offline missing history"))
    refused = algorithm._collect_daily_observations(requirement, 1)
    assert refused[0]["disposition"] == "named_refusal"
    assert refused[0]["reason"] == "qc_total_return_daily_open_unavailable"


def test_generated_runtime_rederives_panel_and_consumes_one_bounded_session(
    monkeypatch,
):
    projection, manifest_payload, shards, census = _fixture()
    source = projection.source_files[0].content.decode("utf-8")
    _install_projected_persistence_module(monkeypatch, projection)
    algorithm_imports = types.ModuleType("AlgorithmImports")
    algorithm_imports.QCAlgorithm = object
    algorithm_imports.TradeBar = type("TradeBar", (), {})
    algorithm_imports.Resolution = types.SimpleNamespace(
        DAILY="daily", MINUTE="minute"
    )
    algorithm_imports.DataNormalizationMode = types.SimpleNamespace(
        TOTAL_RETURN="total-return"
    )
    algorithm_imports.TimeZones = types.SimpleNamespace(NEW_YORK="New York")
    monkeypatch.setitem(__import__("sys").modules, "AlgorithmImports", algorithm_imports)

    calls = []

    class Digest:
        def __init__(self, expected):
            self.expected = expected
            self.rows = []

    def begin_digest(expected):
        return Digest(expected)

    def consume_digest(value, *, requirement, observation):
        value.rows.append(canonical_json_bytes({
            "requirement": requirement, "observation": observation,
        }))
        return value

    def finish_digest(value):
        assert len(value.rows) == value.expected
        payload = b"".join(sorted(value.rows))
        return hashlib.sha256(payload).hexdigest(), len(value.rows)

    cloud = types.ModuleType(
        "research.analyst_revisions_v2_qc.formal_cloud_evaluator"
    )
    cloud.begin_formal_market_panel_digest = begin_digest
    cloud.consume_formal_market_panel_digest_row = consume_digest
    cloud.finish_formal_market_panel_digest = finish_digest
    cloud.begin_compact_formal_evaluation = lambda **kwargs: object()

    def consume_block(value, **kwargs):
        calls.append(kwargs)
        return value

    cloud.consume_compact_formal_session_block = consume_block
    expected_output = object()
    cloud.finish_compact_formal_evaluation_output = (
        lambda value, *, resamples: expected_output
    )
    cloud.consume_formal_cloud_evaluation_output = lambda value: (_ for _ in ()).throw(
        AssertionError("the streaming-only test must not publish")
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "research.analyst_revisions_v2_qc.formal_cloud_evaluator",
        cloud,
    )
    namespace = {}
    exec(compile(source, "projected-main.py", "exec"), namespace)
    algorithm = namespace["AnalystRevisionsV2FormalOutcomeRuntime"]()
    algorithm._calculation_as_of = datetime(2026, 1, 2)
    algorithm._history_call_counts = {"daily": 0, "minute": 0}
    algorithm.symbol = lambda value: types.SimpleNamespace(id=value)
    object_payloads = {item.object_store_key: item.payload for item in shards}
    algorithm.object_store = types.SimpleNamespace(
        contains_key=lambda key: key in object_payloads,
        read_bytes=lambda key: object_payloads[key],
    )

    class History:
        def __getitem__(self, _item):
            return self

        def __call__(self, symbols, _start, _end, resolution, **_kwargs):
            if resolution == "daily":
                return [
                    types.SimpleNamespace(
                        symbol=symbol,
                        time=datetime(2021, 1, day),
                        open=str(100 + day),
                    )
                    for symbol in symbols for day in (4, 5)
                ]
            return [
                types.SimpleNamespace(
                    symbol=symbol,
                    end_time=datetime(2021, 1, 4, 12, 59),
                    close="100",
                )
                for symbol in symbols
            ]

    algorithm.history = History()
    manifest = json.loads(manifest_payload)
    panel_hash, panel_count = algorithm._seal_market_panel(manifest)
    aggregate = algorithm._stream_formal_evaluation(
        manifest, panel_hash, panel_count
    )
    assert aggregate is expected_output
    assert algorithm._history_call_counts == {
        "daily": census.daily_history_batch_count,
        "minute": census.minute_history_batch_count,
    }
    assert len(calls) == 1
    assert len(calls[0]["decision_joins"]) == 1
    assert len(calls[0]["new_contribution_seeds"]) == 1
    assert len(calls[0]["daily_requirements"]) == 2
    assert len(calls[0]["minute_requirements"]) == 1


def test_generated_runtime_writes_reopens_and_only_then_publishes_root(
    monkeypatch,
):
    projection, manifest_payload, _shards, _census = _fixture()
    source = projection.source_files[0].content.decode("utf-8")
    _install_projected_persistence_module(monkeypatch, projection)
    algorithm_imports = types.ModuleType("AlgorithmImports")
    algorithm_imports.QCAlgorithm = object
    algorithm_imports.TradeBar = type("TradeBar", (), {})
    algorithm_imports.Resolution = types.SimpleNamespace(
        DAILY="daily", MINUTE="minute"
    )
    algorithm_imports.DataNormalizationMode = types.SimpleNamespace(
        TOTAL_RETURN="total-return"
    )
    algorithm_imports.TimeZones = types.SimpleNamespace(NEW_YORK="New York")
    monkeypatch.setitem(
        __import__("sys").modules, "AlgorithmImports", algorithm_imports
    )

    objects = []
    references = []
    input_sha256 = projection.input_manifest.content_sha256
    for ordinal in range(FORMAL_RESULT_FAMILY_OBJECT_COUNT):
        raw = canonical_json_bytes({"family_ordinal": ordinal})
        buffer = bytearray(gzip.compress(raw, compresslevel=9, mtime=0))
        buffer[9] = 255
        payload = bytes(buffer)
        compressed_sha256 = hashlib.sha256(payload).hexdigest()
        suffix = (
            REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX
            + input_sha256
            + f"/{ordinal:02d}-{compressed_sha256}-json.gz"
        )
        reference = {
            "schema": REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA,
            "role": "formal_report_family",
            "ordinal": ordinal,
            "source_view_id": (
                "current_row_current_vintage_non_pristine_pit"
                if ordinal < 13
                else "conservative_censored_current_vintage_non_pristine_pit"
            ),
            "family_id": f"f{ordinal % 13}_test",
            "family_output_id": f"arv2-family-{ordinal:02d}",
            "family_output_sha256": hashlib.sha256(raw + b"family").hexdigest(),
            "payload_schema": "arv2-formal-report-family-output-v1",
            "row_count": 1,
            "formal_cloud_evaluator_contract_sha256": hashlib.sha256(
                b"cloud"
            ).hexdigest(),
            "input_manifest_sha256": input_sha256,
            "formal_report_contract_sha256": hashlib.sha256(
                b"report"
            ).hexdigest(),
            "object_store_key_suffix": suffix,
            "uncompressed_byte_count": len(raw),
            "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
            "compressed_byte_count": len(payload),
            "compressed_sha256": compressed_sha256,
            "encoding": (
                "gzip-mtime-zero-os-255-plus-urlsafe-base64-no-linebreaks"
            ),
        }
        references.append(reference)
        objects.append((suffix, payload))
    root_document = {
        "schema": AGGREGATE_RESULT_SCHEMA,
        "evaluation_id": json.loads(manifest_payload)["evaluation_id"],
        "bindings": {"input_manifest_sha256": input_sha256},
        "fold_horizon_axis_count": 24,
        "source_view_fold_horizon_axis_count": 48,
        "failed_arm_omission_count": 0,
        "orders_placed": 0,
        "report_family_count": FORMAL_RESULT_FAMILY_OBJECT_COUNT,
        "report_family_objects": references,
        "report_family_object_inventory_sha256": hashlib.sha256(
            canonical_json_bytes(references)
        ).hexdigest(),
        "report_family_object_total_uncompressed_byte_count": sum(
            item["uncompressed_byte_count"] for item in references
        ),
        "report_family_object_total_compressed_byte_count": sum(
            item["compressed_byte_count"] for item in references
        ),
    }
    root = canonical_json_bytes(root_document)
    carrier = object()

    cloud = types.ModuleType(
        "research.analyst_revisions_v2_qc.formal_cloud_evaluator"
    )
    cloud.begin_compact_formal_evaluation = lambda **_kwargs: None
    cloud.begin_formal_market_panel_digest = lambda _count: None
    cloud.consume_compact_formal_session_block = lambda *_args, **_kwargs: None
    cloud.consume_formal_market_panel_digest_row = (
        lambda *_args, **_kwargs: None
    )
    cloud.finish_compact_formal_evaluation_output = (
        lambda *_args, **_kwargs: carrier
    )
    cloud.finish_formal_market_panel_digest = lambda _value: ("0" * 64, 0)
    cloud.consume_formal_cloud_evaluation_output = (
        lambda value: (root, tuple(objects)) if value is carrier else None
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "research.analyst_revisions_v2_qc.formal_cloud_evaluator",
        cloud,
    )
    namespace = {}
    exec(compile(source, "projected-main.py", "exec"), namespace)
    runtime_type = namespace["AnalystRevisionsV2FormalOutcomeRuntime"]
    manifest = json.loads(manifest_payload)

    class Store:
        max_size = 109_200_000
        max_files = 26

        def __init__(self, values=None, corrupt_reopen_key=None):
            self.values = dict(values or {})
            self.save_calls = []
            self.corrupt_reopen_key = corrupt_reopen_key
            self.saved = set()

        def contains_key(self, key):
            return key in self.values

        def save_bytes(self, key, payload):
            self.save_calls.append(key)
            self.values[key] = bytes(payload)
            self.saved.add(key)
            return True

        def read_bytes(self, key):
            payload = self.values[key]
            if key == self.corrupt_reopen_key and key in self.saved:
                return payload[:-1] + bytes([payload[-1] ^ 1])
            return payload

    def algorithm(store):
        value = runtime_type()
        value.project_id = 12345
        value.object_store = store
        value.summaries = {}
        value.set_summary_statistic = value.summaries.__setitem__
        value._preflight_result_output(manifest)
        return value

    store = Store()
    first = algorithm(store)
    first._publish_aggregate(manifest, carrier)
    assert len(store.values) == len(store.save_calls) == 26
    chunk_names = tuple(
        sorted(
            name
            for name in first.summaries
            if name.startswith(SUMMARY_CHUNK_PREFIX)
            and name != SUMMARY_META_NAME
        )
    )
    assert set(first.summaries) == {SUMMARY_META_NAME, *chunk_names}
    meta = json.loads(base64.urlsafe_b64decode(
        first.summaries[SUMMARY_META_NAME]
    ))
    assert meta["schema"] == SUMMARY_RECEIPT_SCHEMA
    assert meta["report_family_object_count"] == 26
    assert meta["object_store_reopened_object_count"] == 26
    assert meta["raw_report_family_rows_in_summary"] is False
    encoded_root = "".join(
        first.summaries[name]
        for name in chunk_names
    )
    assert gzip.decompress(base64.urlsafe_b64decode(encoded_root)) == root

    reused = algorithm(store)
    reused._publish_aggregate(manifest, carrier)
    assert len(store.save_calls) == 26

    first_key = "12345/" + objects[0][0]
    collision = Store({first_key: b"different"})
    refused = algorithm(collision)
    with pytest.raises(ValueError, match="collision"):
        refused._publish_aggregate(manifest, carrier)
    assert refused.summaries == {}

    tampered = Store(corrupt_reopen_key=first_key)
    refused = algorithm(tampered)
    with pytest.raises(ValueError, match="reopen changed"):
        refused._publish_aggregate(manifest, carrier)
    assert refused.summaries == {}


def test_daily_history_census_counts_bounded_date_blocks_not_security_lifetimes():
    _, _, shards, _ = _fixture()
    security_id = "AAPL R735QTJ8XC9X"
    daily_rows = [
        {
            "schema": DAILY_REQUIREMENT_SCHEMA,
            "requirement_id": build_daily_market_requirement_id(
                security_id=security_id, session=session
            ),
            "security_id": security_id,
            "session": session,
        }
        for session in ("2021-01-04", "2021-06-04")
    ]
    replacement = build_formal_qc_compressed_shard(
        role="daily_requirements", ordinal=0, rows=daily_rows
    )
    changed = tuple(
        replacement if item.role == "daily_requirements" else item
        for item in shards
    )
    with pytest.raises(FormalQcRuntimeProjectionError, match="History request geometry"):
        derive_formal_qc_runtime_resource_census(
            shards=changed,
            distinct_security_count=1,
            daily_history_batch_count=2,
            minute_history_batch_count=2,
            maximum_dynamic_subscription_count=1,
            projected_summary_payload_byte_count=100_000,
            projected_summary_chunk_count=34,
        )
    census = derive_formal_qc_runtime_resource_census(
        shards=changed,
        distinct_security_count=1,
        daily_history_batch_count=4,
        minute_history_batch_count=2,
        maximum_dynamic_subscription_count=1,
        projected_summary_payload_byte_count=100_000,
        projected_summary_chunk_count=34,
    )
    assert census.daily_history_batch_count == 4


def test_streaming_peak_is_not_total_uncompressed_input_size():
    _, _, base_shards, _ = _fixture()
    security_id = "AAPL R735QTJ8XC9X"

    def census_for_sessions(session_count):
        start = date(2021, 1, 1)
        daily_shards = []
        for ordinal in range(session_count):
            session = (start + timedelta(days=ordinal)).isoformat()
            daily_shards.append(build_formal_qc_compressed_shard(
                role="daily_requirements",
                ordinal=ordinal,
                rows=[{
                    "schema": DAILY_REQUIREMENT_SCHEMA,
                    "requirement_id": build_daily_market_requirement_id(
                        security_id=security_id, session=session
                    ),
                    "security_id": security_id,
                    "session": session,
                }],
            ))
        shards = tuple(
            item for item in base_shards if item.role != "daily_requirements"
        )
        role_groups = {
            role: [item for item in shards if item.role == role]
            for role in SHARD_ROLE_ORDER
        }
        role_groups["daily_requirements"] = daily_shards
        ordered = tuple(
            item for role in SHARD_ROLE_ORDER for item in role_groups[role]
        )
        daily_blocks = len({
            (start + timedelta(days=offset)).toordinal() // 32
            for offset in range(session_count)
        })
        return derive_formal_qc_runtime_resource_census(
            shards=ordered,
            distinct_security_count=1,
            daily_history_batch_count=2 * daily_blocks,
            minute_history_batch_count=2,
            maximum_dynamic_subscription_count=1,
            projected_summary_payload_byte_count=100_000,
            projected_summary_chunk_count=34,
        )

    sixty_one = census_for_sessions(61)
    one_twenty_two = census_for_sessions(122)
    assert (
        one_twenty_two.uncompressed_input_byte_count
        > sixty_one.uncompressed_input_byte_count
    )
    assert sixty_one.maximum_live_daily_observation_count == 61
    assert one_twenty_two.maximum_live_daily_observation_count == 61
    # Only bounded single-object encoding variance may affect this estimate;
    # total uncompressed input bytes are deliberately absent from the formula.
    assert abs(
        one_twenty_two.estimated_peak_node_memory_byte_count
        - sixty_one.estimated_peak_node_memory_byte_count
    ) <= 64
