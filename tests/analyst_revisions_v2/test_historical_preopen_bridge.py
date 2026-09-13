"""Focused offline tests for the historical discovery-to-preopen bridge."""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import types
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc.fundamental_universe_discovery import (
    build_fundamental_universe_discovery_plan_bytes,
    build_fundamental_universe_discovery_qc_projection,
    load_reviewed_fundamental_universe_discovery_receipt,
)
from research.analyst_revisions_v2_qc.preopen_control_stage import (
    INPUT_ROLE_ORDER,
    PreopenInputShard,
    build_preopen_input_manifest_bytes,
)
from scripts.build_arv2_historical_preopen_bridge import (
    ANALYST_EVENT_BINDING_SCHEMA,
    ARCHIVE_SHARD_DIRECTORY,
    UNIVERSE_LIFECYCLE_BINDING_SCHEMA,
    HistoricalPreopenBridgeError,
    build_reviewed_historical_universe_to_preopen_bridge,
    historical_preopen_bridge_binding_record,
    iter_reviewed_historical_analyst_event_binding_shards,
    iter_reviewed_historical_preopen_input_shards,
    iter_reviewed_historical_universe_lifecycle_binding_shards,
    require_reviewed_historical_universe_to_preopen_bridge,
)
from scripts.build_arv2_preopen_input import build_physical_preopen_input_candidate
from tests.analyst_revisions_v2 import test_physical_preopen_input_composer as physical
from tests.analyst_revisions_v2 import test_qc_fundamental_universe_discovery as fundamental


ROOT = Path(__file__).resolve().parents[2]
NEW_YORK = ZoneInfo("America/New_York")
FIRST = date(2013, 1, 2)
LAST = date(2025, 12, 31)


def _full_projection():
    sessions = []
    for ordinal, session in enumerate(trading_sessions(FIRST, LAST), start=1):
        opened = datetime.combine(session, time(9, 30), tzinfo=NEW_YORK)
        sessions.append({
            "decision_session": session.isoformat(),
            "decision_session_ordinal": ordinal,
            "decision_open_utc": opened.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
        })
    assert len(sessions) == 3270
    plan = build_fundamental_universe_discovery_plan_bytes(
        decision_sessions=sessions, calculation_session="2026-01-02"
    )
    projection = build_fundamental_universe_discovery_qc_projection(
        plan_bytes=plan,
        worker_source_bytes=fundamental.WORKER_PATH.read_bytes(),
        runtime_source_bytes=fundamental.RUNTIME_PATH.read_bytes(),
    )
    return sessions, plan, projection


def _discovery_receipt(monkeypatch, tmp_path):
    prepared = _full_projection()
    monkeypatch.setattr(
        fundamental, "_projection", lambda _count, sessions=None: prepared
    )
    sessions, plan, projection, runtime, algorithm, constants = (
        fundamental._runtime_fixture(monkeypatch, count=3270)
    )
    rows = [
        fundamental._fundamental(
            1, ticker="NOT-CURRENT-AAA", cusip="000000AA0",
            qc_sid="AAA R735QTJ8XC9X", delisting_date=date(2025, 1, 2),
        ),
        fundamental._fundamental(
            2, ticker="OLD", cusip="000000BB8", qc_sid="OLD R735QTJ8XC9Y"
        ),
        fundamental._fundamental(
            3, ticker="OLD2", cusip="000000BB8", qc_sid="OLD R735QTJ8XC9Z"
        ),
        fundamental._fundamental(
            4, ticker="AMB", cusip="000000CC6", qc_sid="AMB R735QTJ8XC9A"
        ),
        fundamental._fundamental(
            5, ticker="MISSING", cusip="000000DD4", qc_sid="MIS R735QTJ8XC9B"
        ),
        fundamental._fundamental(
            6, ticker="NO-CUSIP", qc_sid="NOC R735QTJ8XC9C"
        ),
    ]
    rows[-1].symbol.cusip = ""
    algorithm.history.collections = [
        fundamental._Node(
            time=datetime.combine(
                date.fromisoformat(geometry["decision_session"]), time(0)
            ),
            data=rows,
        )
        for geometry in sessions
    ]
    runtime.execute_fundamental_universe_discovery(algorithm, constants)
    archive = fundamental._write_archive(tmp_path, projection, algorithm.object_store)
    return load_reviewed_fundamental_universe_discovery_receipt(
        plan_bytes=plan, projection=projection, archive_root=archive
    )


def _physical_candidate(monkeypatch, tmp_path):
    extra = (
        b"fundamentals,DUP1,100003,N,Dup One,Domestic Common Stock,NASDAQ,"
        b"Technology,Software,2010-01-04,,BBG001DUP111,000000CC6\n"
        b"fundamentals,DUP2,100004,N,Dup Two,Domestic Common Stock,NYSE,"
        b"Technology,Software,2010-01-04,,BBG001DUP222,000000CC6\n"
    )
    monkeypatch.setattr(physical, "TICKERS", physical.TICKERS + extra)
    return build_physical_preopen_input_candidate(*physical._physical_sources(tmp_path))


def _json_lines(payload: bytes):
    return [json.loads(line) for line in payload.splitlines()]


def test_full_axis_bridge_preserves_exact_joins_refusals_lineage_and_lifecycle(
    monkeypatch, tmp_path
):
    discovery = _discovery_receipt(monkeypatch, tmp_path)
    candidate = _physical_candidate(monkeypatch, tmp_path)
    bridge = build_reviewed_historical_universe_to_preopen_bridge(
        discovery, candidate, tmp_path / "historical-preopen-bridge"
    )

    assert require_reviewed_historical_universe_to_preopen_bridge(bridge) is bridge
    assert (bridge.first_session, bridge.last_session) == (
        "2013-01-02", "2025-12-31"
    )
    assert bridge.pair_id == candidate.pair_id
    assert bridge.pair_sha256 == candidate.pair_sha256
    assert bridge.derived_capture_id == candidate.derived_capture_id
    assert bridge.sharadar_capture_id == candidate.sharadar_capture_id
    assert bridge.accepted_security_count == 1
    assert bridge.named_refusal_security_count == 4
    assert bridge.current_ticker_match_count == 0
    assert bridge.current_ticker_mismatch_count == 1
    assert bridge.production_preopen_input_available is False
    assert bridge.firm_ontology_human_reviewed is False

    input_shards = list(iter_reviewed_historical_preopen_input_shards(bridge))
    assert set(item.role for item in input_shards) == set(INPUT_ROLE_ORDER)
    bridge_manifest = json.loads(bridge.closed_input_manifest_bytes)
    reconstructed = []
    for item, descriptor in zip(
        input_shards, bridge_manifest["shards"], strict=True
    ):
        reconstructed.append(PreopenInputShard(
            role=descriptor["role"],
            security_batch_ordinal=descriptor["security_batch_ordinal"],
            ordinal=descriptor["ordinal"],
            partition_first_session=descriptor["partition_first_session"],
            partition_last_session=descriptor["partition_last_session"],
            object_store_key=descriptor["object_store_key"],
            compressed_sha256=descriptor["compressed_sha256"],
            compressed_byte_count=descriptor["compressed_byte_count"],
            uncompressed_sha256=descriptor["uncompressed_sha256"],
            uncompressed_byte_count=descriptor["uncompressed_byte_count"],
            row_count=descriptor["row_count"], payload=item.payload,
        ))
    canonical_manifest = json.loads(build_preopen_input_manifest_bytes(
        shards=tuple(reconstructed),
        benchmark_security_id=bridge_manifest["benchmark_security_id"],
        benchmark_ticker=bridge_manifest["benchmark_ticker"],
        first_session=bridge_manifest["first_session"],
        last_session=bridge_manifest["last_session"],
        calculation_session=bridge_manifest["calculation_session"],
        rating_source_complete=bridge_manifest["source_policy"]["rating_source_complete"],
        earnings_source_complete=bridge_manifest["source_policy"]["earnings_source_complete"],
        guidance_source_complete=bridge_manifest["source_policy"]["guidance_source_complete"],
        earnings_pit_policy_id=bridge_manifest["source_policy"]["earnings_pit_policy_id"],
        guidance_clock_policy_id=bridge_manifest["source_policy"]["guidance_clock_policy_id"],
        eligible_universe_artifact_id=bridge_manifest["eligible_universe_source"]["artifact_id"],
        eligible_universe_artifact_sha256=bridge_manifest["eligible_universe_source"]["artifact_sha256"],
        eligible_universe_artifact_byte_count=bridge_manifest["eligible_universe_source"]["byte_count"],
        truth_source_bindings=tuple(bridge_manifest["truth_source_bindings"]),
    ))
    canonical_manifest["resource_census"][
        "host_manifest_projection_retains_all_compressed_input_payloads"
    ] = False
    assert {
        key: (canonical_manifest["resource_census"].get(key),
              bridge_manifest["resource_census"].get(key))
        for key in set(canonical_manifest["resource_census"]) |
        set(bridge_manifest["resource_census"])
        if canonical_manifest["resource_census"].get(key)
        != bridge_manifest["resource_census"].get(key)
    } == {}
    canonical_manifest["resource_census"] = bridge_manifest["resource_census"]
    assert canonical_manifest == bridge_manifest
    by_role = {
        role: [
            row for shard in input_shards if shard.role == role
            for row in _json_lines(gzip.decompress(shard.payload))
        ]
        for role in INPUT_ROLE_ORDER
    }
    accepted_mapping = next(
        row for row in by_role["sid_mapping"]
        if row["mapping_status"]
        == "reviewed_qc_fundamental_discovery_exact_cusip_join"
    )
    assert accepted_mapping["qc_security_id"] == "AAA R735QTJ8XC9X"
    assert accepted_mapping["cusip"] == "000000AA0"
    assert accepted_mapping["current_ticker_matches"] is False
    refusal_reasons = {
        row["census_refusal"]["reason"]
        for row in by_role["universe"] if row["disposition"] == "named_refusal"
    }
    assert {
        "CUSIP_reused_by_multiple_QC_SIDs",
        "CUSIP_ambiguous_across_Sharadar_identities",
        "CUSIP_missing_from_Sharadar_identity_seeds",
    } <= refusal_reasons

    analyst_shards = list(
        iter_reviewed_historical_analyst_event_binding_shards(bridge)
    )
    analyst_rows = [
        row for shard in analyst_shards for row in _json_lines(shard.canonical_json_lines)
    ]
    assert len(analyst_rows) == bridge.analyst_event_binding_row_count == 1
    event = analyst_rows[0]
    assert event["schema"] == ANALYST_EVENT_BINDING_SCHEMA
    assert event["binding_disposition"] == "accepted"
    assert event["qc_security_id"] == "AAA R735QTJ8XC9X"
    assert event["q_data"] == "0"
    assert event["mapping_closure_available_at"] is None
    assert event["locator_sha256"] and event["raw_row_sha256"]

    lifecycle_shards = list(
        iter_reviewed_historical_universe_lifecycle_binding_shards(bridge)
    )
    lifecycle_rows = [
        row for shard in lifecycle_shards
        for row in _json_lines(shard.canonical_json_lines)
    ]
    assert len(lifecycle_rows) == bridge.universe_lifecycle_binding_row_count == 6 * 3270
    assert all(row["schema"] == UNIVERSE_LIFECYCLE_BINDING_SCHEMA for row in lifecycle_rows)
    assert any(
        row["discovery_refusal_reason"]
        == "missing_or_invalid_CUSIP_cross_vendor_join_key"
        for row in lifecycle_rows
    )
    assert any(row["delisting_date"] == "2025-01-02" for row in lifecycle_rows)
    assert all(row["payoff_semantics_assigned"] is False for row in lifecycle_rows)
    binding = historical_preopen_bridge_binding_record(bridge)
    assert binding["pair_sha256"] == candidate.pair_sha256
    assert binding["universe_lifecycle_binding_row_count"] == 6 * 3270


def test_bridge_archive_mutation_and_extra_leaf_are_refused(monkeypatch, tmp_path):
    discovery = _discovery_receipt(monkeypatch, tmp_path)
    candidate = _physical_candidate(monkeypatch, tmp_path)
    root = tmp_path / "historical-preopen-bridge"
    bridge = build_reviewed_historical_universe_to_preopen_bridge(
        discovery, candidate, root
    )
    extra = root / ARCHIVE_SHARD_DIRECTORY / "unbound"
    extra.write_bytes(b"x")
    extra.chmod(0o600)
    with pytest.raises(HistoricalPreopenBridgeError, match="inventory|directory changed"):
        require_reviewed_historical_universe_to_preopen_bridge(bridge)


def test_preopen_runtime_uses_only_prebound_encoded_security_identifiers():
    source = (
        ROOT / "research" / "analyst_revisions_v2_qc" / "preopen_control_runtime.py"
    ).read_text()
    assert "algorithm.symbol(encoded_sid)" in source
    assert ".add_equity(" not in source
    assert ".remove_security(" not in source
    assert "add_equity" not in source
    assert "remove_security" not in source
    assert hashlib.sha256(source.encode()).hexdigest()


def test_preopen_runtime_refuses_sid_deserialization_or_universe_mismatch(monkeypatch):
    imports = types.ModuleType("AlgorithmImports")
    imports.DataNormalizationMode = types.SimpleNamespace()
    imports.Resolution = types.SimpleNamespace()
    imports.TradeBar = type("TradeBar", (), {})
    worker = types.ModuleType("preopen_control_worker")
    for name in (
        "accumulate_peer_aggregates", "build_market_control_summaries",
        "build_security_batch_terminals", "peer_aggregate_records",
    ):
        setattr(worker, name, lambda *_args, **_kwargs: None)
    monkeypatch.setitem(sys.modules, "AlgorithmImports", imports)
    monkeypatch.setitem(sys.modules, "preopen_control_worker", worker)
    namespace: dict[str, object] = {}
    runtime_path = (
        ROOT / "research" / "analyst_revisions_v2_qc" / "preopen_control_runtime.py"
    )
    exec(compile(runtime_path.read_bytes(), str(runtime_path), "exec"), namespace)
    mapping = {
        "security_id": "logical-one", "qc_security_id": "SID-EXACT",
        "row_sha256": "a" * 64,
        "mapping_status": "reviewed_qc_fundamental_discovery_exact_cusip_join",
    }
    universe = {
        "security_id": "logical-one", "qc_security_id": "SID-EXACT",
        "disposition": "accepted",
    }

    class WrongAlgorithm:
        def symbol(self, _encoded):
            return types.SimpleNamespace(id="SID-WRONG")

    with pytest.raises(ValueError, match="permanent QC SecurityIdentifier changed"):
        namespace["_reviewed_batch_symbols"](
            WrongAlgorithm(), {"sid_mapping": [mapping], "universe": [universe]}
        )

    class ExactAlgorithm:
        def symbol(self, encoded):
            return types.SimpleNamespace(id=encoded)

    with pytest.raises(ValueError, match="universe QC SID differs"):
        namespace["_reviewed_batch_symbols"](
            ExactAlgorithm(), {
                "sid_mapping": [mapping],
                "universe": [{**universe, "qc_security_id": "SID-OTHER"}],
            },
        )
