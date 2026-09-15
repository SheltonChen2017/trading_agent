from __future__ import annotations

import gzip
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import accepted_risk_qc_symbol_resolution as symbols
from research.analyst_revisions_v2_qc import in_qc_preopen_terminal_stream as subject
from research.analyst_revisions_v2.preopen_control_acquisition import (
    BINARY_CONTROL_NAMES as BINARY_NAMES,
    CONTINUOUS_CONTROL_NAMES as CONTINUOUS_NAMES,
)


ROOT = Path(__file__).resolve().parents[2]


class _Sid:
    def __init__(self, value: str) -> None:
        self.value = value
        self.market = "usa"

    def __str__(self) -> str:
        return self.value


class _Symbol:
    def __init__(self, ticker: str) -> None:
        self.id = _Sid("QC SID " + ticker)
        self.value = ticker
        self.security_type = "Equity"


class _Store:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads
        self.reads: list[str] = []

    def read_bytes(self, key: str) -> bytes:
        self.reads.append(key)
        return self.payloads[key]


class _Algorithm:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.object_store = _Store(payloads)


def _binding(security_id: str, ticker: str, *, count: int) -> dict[str, object]:
    return symbols.build_runtime_ticker_binding(
        security_id=security_id,
        issuer_id="issuer-" + ticker,
        share_class_id="share-class-" + ticker,
        listing_id="listing-" + ticker,
        current_snapshot_ticker=ticker,
        exchange_mic="XNAS",
        candidate_first_session="2021-01-04",
        candidate_last_session="2025-12-31",
        source_snapshot_available_at="2026-09-14T00:00:00.000000Z",
        source_row_sha256=hashlib.sha256(("source-" + ticker).encode()).hexdigest(),
        identity_evidence_sha256=hashlib.sha256(
            ("identity-" + ticker).encode()
        ).hexdigest(),
        security_master_admission_sha256="a" * 64,
        admitted_mapping_inventory_sha256="b" * 64,
        admitted_mapping_count=count,
    )


def _resolution(
    pairs: list[tuple[str, str]], *, unresolved: set[str] | None = None
) -> symbols.AcceptedRiskQcSymbolResolution:
    unresolved = unresolved or set()
    rows = [_binding(security_id, ticker, count=len(pairs)) for security_id, ticker in pairs]
    rows.sort(key=lambda row: row["security_id"])
    return symbols.resolve_owner_accepted_qc_symbols(
        rows,
        symbol_factory=lambda ticker: None if ticker in unresolved else _Symbol(ticker),
    )


def _terminal(
    session: str,
    security_id: str,
    ticker: str,
    *,
    disposition: str = "accepted",
) -> dict[str, object]:
    available = "2021-01-01T13:00:00.000000Z"
    components = []
    for index, (kind, quality) in enumerate(
        (
            ("timestamp_quality", "0.8"),
            ("firm_label_mapping_quality", "0.9"),
            ("security_entity_mapping_quality", "0.95"),
        )
    ):
        component = {
            "kind": kind,
            "value": quality,
            "source_id": f"quality-source-{index}",
            "source_sha256": hashlib.sha256(f"source-{index}".encode()).hexdigest(),
            "payload_sha256": hashlib.sha256(f"payload-{index}".encode()).hexdigest(),
            "available_at": available,
            "point_in_time": index != 0,
            "accepted_risk_non_pristine": index == 0,
        }
        component["evidence_sha256"] = hashlib.sha256(
            canonical_json_bytes(component)
        ).hexdigest()
        components.append(component)
    measurement = {
        "security_id": security_id,
        "measured_session": session,
        "source_id": "quality-aggregate-source",
        "source_sha256": hashlib.sha256(b"quality-aggregate-source").hexdigest(),
        "components": components,
        "measurement_method_id": "arv2-qdata-conservative-min-v1",
        "q_data": "0.8",
        "available_at": available,
        "point_in_time": True,
    }
    measurement["evidence_sha256"] = hashlib.sha256(
        canonical_json_bytes(measurement)
    ).hexdigest()
    controls = [[name, "0"] for name in CONTINUOUS_NAMES] + [
        [name, 0] for name in BINARY_NAMES
    ]
    eligible = {
        "decision_session": session,
        "security_id": security_id,
        "issuer_id": "issuer-" + ticker,
        "share_class_id": "share-class-" + ticker,
        "listing_id": "listing-" + ticker,
        "historical_ticker": ticker,
        "sector_id": "sector-one",
        "industry_id": "industry-one",
        "q_data": "0.8",
        "controls": controls,
        "source_id": "preopen-source",
        "source_sha256": hashlib.sha256(b"preopen-source").hexdigest(),
        "identity_evidence_sha256": hashlib.sha256(b"identity").hexdigest(),
        "identity_available_at": available,
        "classification_evidence_sha256": hashlib.sha256(b"classification").hexdigest(),
        "classification_available_at": available,
        "q_data_evidence_sha256": measurement["evidence_sha256"],
        "q_data_available_at": available,
        "control_evidence_sha256": hashlib.sha256(b"control-evidence").hexdigest(),
        "control_available_at": available,
        "control_vector_sha256": hashlib.sha256(canonical_json_bytes(controls)).hexdigest(),
        "point_in_time": True,
        "earnings_anchor_signed_session_distance": None,
    }
    eligible["evidence_sha256"] = hashlib.sha256(
        canonical_json_bytes(eligible)
    ).hexdigest()
    refusal = {
        "decision_session": session,
        "security_id": security_id,
        "issuer_id": "issuer-" + ticker,
        "share_class_id": "share-class-" + ticker,
        "listing_id": "listing-" + ticker,
        "historical_ticker": ticker,
        "reason": "named reason",
        "source_id": "preopen-source",
        "source_sha256": hashlib.sha256(b"preopen-source").hexdigest(),
        "available_at": None,
    }
    refusal["refusal_sha256"] = hashlib.sha256(
        canonical_json_bytes(refusal)
    ).hexdigest()
    semantic: dict[str, object] = {
        "schema": subject.OUTPUT_ROW_SCHEMA,
        "decision_session": session,
        "security_id": security_id,
        "qc_security_id": "QC SID " + ticker if disposition == "accepted" else None,
        "issuer_id": "issuer-" + ticker,
        "share_class_id": "share-class-" + ticker,
        "listing_id": "listing-" + ticker,
        "security_master_row_sha256": hashlib.sha256(
            ("source-" + ticker).encode()
        ).hexdigest(),
        "disposition": disposition,
        "detail_reason": None if disposition == "accepted" else "named reason",
        "eligible_security_session": eligible if disposition == "accepted" else None,
        "q_data_measurement": measurement if disposition == "accepted" else None,
        "census_refusal": None if disposition == "accepted" else refusal,
        "input_roots": {
            role: hashlib.sha256(role.encode()).hexdigest()
            for role in (
                "universe",
                "sid_mapping",
                "fundamentals",
                "earnings",
                "guidance",
                "ratings",
                "market_observations",
            )
        },
    }
    return {
        **semantic,
        "terminal_sha256": hashlib.sha256(canonical_json_bytes(semantic)).hexdigest(),
    }


def _shard(
    rows: list[dict[str, object]], *, ordinal: int, chunk: int, batch: int
) -> tuple[dict[str, object], bytes]:
    rows = sorted(rows, key=lambda row: (row["decision_session"], row["security_id"]))
    raw = b"".join(canonical_json_bytes(row) for row in rows)
    payload = gzip.compress(raw, compresslevel=9, mtime=0)
    digest = hashlib.sha256(payload).hexdigest()
    descriptor = {
        "schema": subject.OUTPUT_SHARD_SCHEMA,
        "role": "control_terminals",
        "ordinal": ordinal,
        "decision_chunk_ordinal": chunk,
        "security_batch_ordinal": batch,
        "partition_first_session": rows[0]["decision_session"],
        "partition_last_session": rows[-1]["decision_session"],
        "first_security_id": min(str(row["security_id"]) for row in rows),
        "last_security_id": max(str(row["security_id"]) for row in rows),
        "object_store_key": (
            "arv2/preopen/output/content/control_terminals/"
            f"chunk-{chunk:04d}/security-batch-{batch:04d}/{digest}-jsonl.gz"
        ),
        "compression": "gzip-level9-mtime0",
        "encoding": "canonical-json-lines-utf8-lf",
        "row_schema": subject.OUTPUT_ROW_SCHEMA,
        "compressed_sha256": digest,
        "compressed_byte_count": len(payload),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "uncompressed_byte_count": len(raw),
        "row_count": len(rows),
    }
    return descriptor, payload


def _manifest_bytes(
    descriptors: list[dict[str, object]],
    *,
    terminal_count: int,
    accepted_count: int,
    refusal_count: int,
    inventory_sha256: str | None = None,
) -> bytes:
    session = min(str(item["partition_first_session"]) for item in descriptors)
    universe = [
        {
            "schema": subject.UNIVERSE_SESSION_SCHEMA,
            "decision_session": session,
            "accepted_count": accepted_count,
            "refusal_count": refusal_count,
            "terminal_count": terminal_count,
            "terminal_merkle_root": "a" * 64,
        }
    ]
    controls = [
        {
            **universe[0],
            "schema": subject.CONTROL_SESSION_SCHEMA,
            "market_observation_count": 1,
            "market_observation_sha256": "b" * 64,
        }
    ]
    manifest = {
        "schema": subject.OUTPUT_MANIFEST_SCHEMA,
        "contract_id": "fixture-contract",
        "contract_sha256": "c" * 64,
        "input_manifest": {},
        "eligible_universe_source": {},
        "qc_sid_mapping_source": {},
        "source_policy": {},
        "construction_resource_census": {},
        "run_authority": {},
        "input_role_bindings": [],
        "truth_source_bindings": [],
        "input_source_inventory_sha256": "d" * 64,
        "project_source_set_sha256": "e" * 64,
        "construction_intermediates": {
            "schema": "arv2-preopen-control-construction-intermediate-commitment-v1",
            "peer_aggregate_record_count": 0,
            "peer_aggregate_projection_sha256": "f" * 64,
            "market_session_commitment_count": 1,
            "market_session_projection_sha256": "0" * 64,
            "physical_terminal_shard_count": len(descriptors),
            "logical_terminal_order": "decision_session_then_security_id",
            "q_data_measurement_count": accepted_count,
            "q_data_measurement_projection_sha256": "1" * 64,
        },
        "output_shards": descriptors,
        "output_shard_inventory_sha256": inventory_sha256
        or hashlib.sha256(canonical_json_bytes(descriptors)).hexdigest(),
        "universe_sessions": universe,
        "control_sessions": controls,
        "universe_terminal_projection_sha256": hashlib.sha256(
            canonical_json_bytes(
                {
                    "domain": "arv2-preopen-universe-session-projection-v1",
                    "records": universe,
                }
            )
        ).hexdigest(),
        "control_terminal_projection_sha256": hashlib.sha256(
            canonical_json_bytes(
                {
                    "domain": "arv2-preopen-control-session-projection-v1",
                    "records": controls,
                }
            )
        ).hexdigest(),
        "census": {
            "universe_terminal_count": terminal_count,
            "control_accepted_count": accepted_count,
            "control_refusal_count": refusal_count,
            "control_terminal_count": terminal_count,
        },
        "capabilities": {
            name: False
            for name in (
                "provider_access", "credential_access", "filesystem_access",
                "quantconnect_access", "object_store_access", "price_access",
                "outcome_access", "result_access", "deployment", "orders", "trading",
            )
        },
    }
    return canonical_json_bytes(manifest)


def _run(
    descriptors: list[dict[str, object]],
    payloads: list[bytes],
    resolution: symbols.AcceptedRiskQcSymbolResolution,
    consumer,
    *,
    terminal_count: int,
    accepted_count: int,
    refusal_count: int,
):
    algorithm = _Algorithm(
        {
            descriptor["object_store_key"]: payload
            for descriptor, payload in zip(descriptors, payloads, strict=True)
        }
    )
    manifest = subject.bind_preopen_output_manifest_for_cloud_stream(
        _manifest_bytes(
            descriptors,
            terminal_count=terminal_count,
            accepted_count=accepted_count,
            refusal_count=refusal_count,
        )
    )
    receipt = subject.stream_preopen_terminals_cloud_locally(
        algorithm=algorithm,
        output_manifest=manifest,
        symbol_resolution=resolution,
        consumer=consumer,
    )
    return algorithm, receipt


def test_streams_two_shards_in_global_order_and_returns_transport_only_receipt():
    pairs = [("logical-A", "AAA"), ("logical-B", "BBB")]
    resolution = _resolution(pairs)
    first = _shard(
        [
            _terminal("2021-01-04", "logical-A", "AAA"),
            _terminal("2021-01-05", "logical-A", "AAA"),
        ],
        ordinal=0,
        chunk=0,
        batch=0,
    )
    second = _shard(
        [
            _terminal("2021-01-04", "logical-B", "BBB"),
            _terminal("2021-01-05", "logical-B", "BBB"),
        ],
        ordinal=1,
        chunk=0,
        batch=1,
    )
    observed: list[tuple[str, str]] = []

    algorithm, receipt = _run(
        [first[0], second[0]],
        [first[1], second[1]],
        resolution,
        lambda row: observed.append((row["decision_session"], row["security_id"])),
        terminal_count=4,
        accepted_count=4,
        refusal_count=0,
    )

    assert observed == [
        ("2021-01-04", "logical-A"),
        ("2021-01-04", "logical-B"),
        ("2021-01-05", "logical-A"),
        ("2021-01-05", "logical-B"),
    ]
    assert algorithm.object_store.reads == [
        first[0]["object_store_key"],
        second[0]["object_store_key"],
    ]
    assert receipt.transport_only is True
    assert receipt.consumer_effects_attested is False
    assert receipt.eligible_as_formal_evidence is False
    assert receipt.host_object_store_export_performed is False
    assert receipt.source_output_manifest_sha256 == hashlib.sha256(
        _manifest_bytes(
            [first[0], second[0]],
            terminal_count=4,
            accepted_count=4,
            refusal_count=0,
        )
    ).hexdigest()
    assert subject.require_in_qc_preopen_terminal_stream_receipt(receipt) is receipt


def test_multidot_legacy_object_key_is_refused_before_any_read():
    resolution = _resolution([("logical-A", "AAA")])
    descriptor, payload = _shard(
        [_terminal("2021-01-04", "logical-A", "AAA")],
        ordinal=0,
        chunk=0,
        batch=0,
    )
    descriptor["object_store_key"] = descriptor["object_store_key"].replace(
        "-jsonl.gz", ".jsonl.gz"
    )
    algorithm = _Algorithm({descriptor["object_store_key"]: payload})
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="Object Store key is not QC-legal and content-derived",
    ):
        subject.bind_preopen_output_manifest_for_cloud_stream(
            _manifest_bytes(
                [descriptor], terminal_count=1, accepted_count=1, refusal_count=0
            )
        )
    assert algorithm.object_store.reads == []


def test_descriptor_inventory_hash_refuses_truncation_before_object_store_read():
    resolution = _resolution([("logical-A", "AAA")])
    descriptor, payload = _shard(
        [_terminal("2021-01-04", "logical-A", "AAA")],
        ordinal=0,
        chunk=0,
        batch=0,
    )
    algorithm = _Algorithm({descriptor["object_store_key"]: payload})
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="output-manifest shard inventory hash changed",
    ):
        subject.bind_preopen_output_manifest_for_cloud_stream(
            _manifest_bytes(
                [descriptor],
                terminal_count=1,
                accepted_count=1,
                refusal_count=0,
                inventory_sha256="d" * 64,
            )
        )
    assert algorithm.object_store.reads == []


def test_payload_corruption_is_refused_before_consumer():
    resolution = _resolution([("logical-A", "AAA")])
    descriptor, payload = _shard(
        [_terminal("2021-01-04", "logical-A", "AAA")],
        ordinal=0,
        chunk=0,
        batch=0,
    )
    observed: list[dict[str, object]] = []
    algorithm = _Algorithm({descriptor["object_store_key"]: payload[:-1] + b"0"})
    manifest = subject.bind_preopen_output_manifest_for_cloud_stream(
        _manifest_bytes(
            [descriptor], terminal_count=1, accepted_count=1, refusal_count=0
        )
    )
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="compressed shard identity changed",
    ):
        subject.stream_preopen_terminals_cloud_locally(
            algorithm=algorithm,
            output_manifest=manifest,
            symbol_resolution=resolution,
            consumer=observed.append,
        )
    assert observed == []


def test_each_payload_is_authenticated_before_the_next_object_store_read():
    resolution = _resolution([("logical-A", "AAA"), ("logical-B", "BBB")])
    first = _shard(
        [_terminal("2021-01-04", "logical-A", "AAA")],
        ordinal=0,
        chunk=0,
        batch=0,
    )
    second = _shard(
        [_terminal("2021-01-04", "logical-B", "BBB")],
        ordinal=1,
        chunk=0,
        batch=1,
    )
    algorithm = _Algorithm(
        {
            first[0]["object_store_key"]: first[1] + b"corrupt",
            second[0]["object_store_key"]: second[1],
        }
    )
    descriptors = [first[0], second[0]]
    manifest = subject.bind_preopen_output_manifest_for_cloud_stream(
        _manifest_bytes(
            descriptors, terminal_count=2, accepted_count=2, refusal_count=0
        )
    )
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="compressed shard identity changed",
    ):
        subject.stream_preopen_terminals_cloud_locally(
            algorithm=algorithm,
            output_manifest=manifest,
            symbol_resolution=resolution,
            consumer=lambda _row: None,
        )
    assert algorithm.object_store.reads == [first[0]["object_store_key"]]


@pytest.mark.parametrize("hostile_level", ["algorithm", "store"])
def test_hostile_object_store_accessor_is_normalized_without_detail(hostile_level: str):
    resolution = _resolution([("logical-A", "AAA")])
    descriptor, _payload = _shard(
        [_terminal("2021-01-04", "logical-A", "AAA")],
        ordinal=0,
        chunk=0,
        batch=0,
    )
    manifest = subject.bind_preopen_output_manifest_for_cloud_stream(
        _manifest_bytes(
            [descriptor], terminal_count=1, accepted_count=1, refusal_count=0
        )
    )

    class HostileStore:
        @property
        def read_bytes(self):
            raise RuntimeError("SECRET HOSTILE ACCESSOR")

    class HostileAlgorithm:
        @property
        def object_store(self):
            raise RuntimeError("SECRET HOSTILE ACCESSOR")

    algorithm = HostileAlgorithm() if hostile_level == "algorithm" else type(
        "Algorithm", (), {"object_store": HostileStore()}
    )()
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="^cloud-local pre-open Object Store bytes API is unreadable$",
    ) as error:
        subject.stream_preopen_terminals_cloud_locally(
            algorithm=algorithm,
            output_manifest=manifest,
            symbol_resolution=resolution,
            consumer=lambda _row: None,
        )
    assert "SECRET HOSTILE ACCESSOR" not in str(error.value)


def test_unresolved_or_wrong_qc_sid_cannot_appear_as_accepted_terminal():
    unresolved = _resolution([("logical-A", "AAA")], unresolved={"AAA"})
    descriptor, payload = _shard(
        [_terminal("2021-01-04", "logical-A", "AAA")],
        ordinal=0,
        chunk=0,
        batch=0,
    )
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="runtime-unresolved security appeared as an accepted",
    ):
        _run(
            [descriptor], [payload], unresolved, lambda _row: None,
            terminal_count=1, accepted_count=1, refusal_count=0,
        )

    resolution = _resolution([("logical-A", "AAA")])
    row = _terminal("2021-01-04", "logical-A", "AAA")
    row["qc_security_id"] = "QC SID OTHER"
    semantic = dict(row)
    semantic.pop("terminal_sha256")
    row["terminal_sha256"] = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    descriptor, payload = _shard([row], ordinal=0, chunk=0, batch=0)
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="differs from its runtime QC SecurityIdentifier",
    ):
        _run(
            [descriptor], [payload], resolution, lambda _row: None,
            terminal_count=1, accepted_count=1, refusal_count=0,
        )


def test_resolved_named_refusal_cannot_substitute_an_unbound_qc_sid():
    resolution = _resolution([("logical-A", "AAA")])
    row = _terminal(
        "2021-01-04", "logical-A", "AAA", disposition="named_refusal"
    )
    row["qc_security_id"] = "QC SID OTHER"
    semantic = dict(row)
    semantic.pop("terminal_sha256")
    row["terminal_sha256"] = hashlib.sha256(
        canonical_json_bytes(semantic)
    ).hexdigest()
    descriptor, payload = _shard([row], ordinal=0, chunk=0, batch=0)

    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="differs from its runtime QC SecurityIdentifier",
    ):
        _run(
            [descriptor], [payload], resolution, lambda _row: None,
            terminal_count=1, accepted_count=0, refusal_count=1,
        )


def test_unknown_or_omitted_logical_security_is_not_silent():
    resolution = _resolution([("logical-A", "AAA"), ("logical-B", "BBB")])
    descriptor, payload = _shard(
        [_terminal("2021-01-04", "logical-X", "XXX")],
        ordinal=0,
        chunk=0,
        batch=0,
    )
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="escaped symbol-resolution authority",
    ):
        _run(
            [descriptor], [payload], resolution, lambda _row: None,
            terminal_count=1, accepted_count=1, refusal_count=0,
        )

    descriptor, payload = _shard(
        [_terminal("2021-01-04", "logical-A", "AAA")],
        ordinal=0,
        chunk=0,
        batch=0,
    )
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="omitted a symbol-resolution terminal",
    ):
        _run(
            [descriptor], [payload], resolution, lambda _row: None,
            terminal_count=1, accepted_count=1, refusal_count=0,
        )


def test_terminal_field_inventory_and_terminal_hash_have_distinct_refusals():
    resolution = _resolution([("logical-A", "AAA")])
    row = _terminal("2021-01-04", "logical-A", "AAA")
    row.pop("input_roots")
    semantic = dict(row)
    semantic.pop("terminal_sha256")
    row["terminal_sha256"] = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    descriptor, payload = _shard([row], ordinal=0, chunk=0, batch=0)
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="not exact canonical terminal schema",
    ):
        _run(
            [descriptor], [payload], resolution, lambda _row: None,
            terminal_count=1, accepted_count=1, refusal_count=0,
        )


def test_self_hashed_but_semantically_impossible_terminal_is_refused():
    resolution = _resolution([("logical-A", "AAA")])
    row = _terminal("2021-01-04", "logical-A", "AAA")
    row["issuer_id"] = ""
    semantic = dict(row)
    semantic.pop("terminal_sha256")
    row["terminal_sha256"] = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    descriptor, payload = _shard([row], ordinal=0, chunk=0, batch=0)
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="terminal semantic schema did not authenticate",
    ):
        _run(
            [descriptor], [payload], resolution, lambda _row: None,
            terminal_count=1, accepted_count=1, refusal_count=0,
        )

    row = _terminal("2021-01-04", "logical-A", "AAA")
    row["terminal_sha256"] = "0" * 64
    descriptor, payload = _shard([row], ordinal=0, chunk=0, batch=0)
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="terminal content hash changed",
    ):
        _run(
            [descriptor], [payload], resolution, lambda _row: None,
            terminal_count=1, accepted_count=1, refusal_count=0,
        )


def test_consumer_nested_mutation_cannot_change_receipt_chain():
    resolution = _resolution([("logical-A", "AAA")])
    row = _terminal("2021-01-04", "logical-A", "AAA")
    descriptor, payload = _shard([row], ordinal=0, chunk=0, batch=0)
    expected_chain: str | None = None

    def mutate(delivered: dict[str, object]) -> None:
        delivered["input_roots"]["ratings"] = "0" * 64

    _algorithm, receipt = _run(
        [descriptor], [payload], resolution, mutate,
        terminal_count=1, accepted_count=1, refusal_count=0,
    )
    expected_chain = hashlib.sha256(
        canonical_json_bytes(
            {
                "domain": "arv2-in-qc-preopen-terminal-chain-node-v1",
                "previous_sha256": hashlib.sha256(
                    canonical_json_bytes(
                        {"domain": "arv2-in-qc-preopen-terminal-chain-v1"}
                    )
                ).hexdigest(),
                "record_sha256": hashlib.sha256(canonical_json_bytes(row)).hexdigest(),
            }
        )
    ).hexdigest()
    assert receipt.logical_terminal_chain_sha256 == expected_chain


def test_receipt_exact_gate_types_and_nonempty_census_are_reauthenticated():
    resolution = _resolution([("logical-A", "AAA")])
    descriptor, payload = _shard(
        [_terminal("2021-01-04", "logical-A", "AAA")],
        ordinal=0,
        chunk=0,
        batch=0,
    )
    _algorithm, receipt = _run(
        [descriptor], [payload], resolution, lambda _row: None,
        terminal_count=1, accepted_count=1, refusal_count=0,
    )
    object.__setattr__(receipt, "transport_only", 1)
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="receipt gate type changed",
    ):
        subject.require_in_qc_preopen_terminal_stream_receipt(receipt)

    _algorithm, zero = _run(
        [descriptor], [payload], resolution, lambda _row: None,
        terminal_count=1, accepted_count=1, refusal_count=0,
    )
    object.__setattr__(zero, "shard_count", 0)
    object.__setattr__(zero, "terminal_count", 0)
    object.__setattr__(zero, "accepted_terminal_count", 0)
    object.__setattr__(zero, "cloud_local_object_store_reads", 0)
    with pytest.raises(subject.InQcPreopenTerminalStreamError):
        subject.require_in_qc_preopen_terminal_stream_receipt(zero)


def test_structurally_valid_forged_receipt_lacks_process_local_authority():
    seed = subject._receipt_seed(
        source_output_manifest_sha256="a" * 64,
        resolution_sha256="b" * 64,
        descriptor_inventory_sha256="c" * 64,
        shard_count=1,
        terminal_count=1,
        accepted_count=1,
        refusal_count=0,
        chain_sha256="d" * 64,
    )
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    seed["receipt_id"] = "arv2-in-qc-preopen-stream-" + digest[:24]
    seed["receipt_sha256"] = digest
    forged = subject.InQcPreopenTerminalStreamReceipt(**seed)
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="lacks process-local stream authority",
    ):
        subject.require_in_qc_preopen_terminal_stream_receipt(forged)


def test_registered_manifest_and_receipt_reject_equal_string_subclasses():
    resolution = _resolution([("logical-A", "AAA")])
    descriptor, payload = _shard(
        [_terminal("2021-01-04", "logical-A", "AAA")],
        ordinal=0,
        chunk=0,
        batch=0,
    )
    authority = subject.bind_preopen_output_manifest_for_cloud_stream(
        _manifest_bytes(
            [descriptor], terminal_count=1, accepted_count=1, refusal_count=0
        )
    )

    class StringSubtype(str):
        pass

    object.__setattr__(authority, "binding_id", StringSubtype(authority.binding_id))
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="binding scalar or container type changed",
    ):
        subject.require_bound_preopen_output_manifest(authority)

    _algorithm, receipt = _run(
        [descriptor], [payload], resolution, lambda _row: None,
        terminal_count=1, accepted_count=1, refusal_count=0,
    )
    object.__setattr__(receipt, "receipt_id", StringSubtype(receipt.receipt_id))
    with pytest.raises(
        subject.InQcPreopenTerminalStreamError,
        match="receipt identity type changed",
    ):
        subject.require_in_qc_preopen_terminal_stream_receipt(receipt)


def test_cloud_stream_source_imports_from_flat_qc_projection(tmp_path: Path):
    source = ROOT / "research" / "analyst_revisions_v2_qc"
    for name in (
        "accepted_risk_qc_symbol_resolution.py",
        "in_qc_preopen_terminal_stream.py",
        "preopen_terminal_semantics.py",
        "preopen_control_worker.py",
        "preopen_quality_worker.py",
    ):
        shutil.copyfile(source / name, tmp_path / name)
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(tmp_path)!r}); "
                "import in_qc_preopen_terminal_stream as stream; "
                "assert stream.RECEIPT_SCHEMA.endswith('-v1')"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
