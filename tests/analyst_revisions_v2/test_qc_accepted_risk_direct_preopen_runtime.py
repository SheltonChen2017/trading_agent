from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import accepted_risk_qc_symbol_resolution as symbols


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "research/analyst_revisions_v2_qc/preopen_control_runtime.py"


class _Sid:
    def __init__(self, ticker: str) -> None:
        self.encoded = "QC SID " + ticker
        self.market = "usa"

    def __str__(self) -> str:
        return self.encoded


class _Symbol:
    def __init__(self, ticker: str) -> None:
        self.id = _Sid(ticker)
        self.value = ticker
        self.security_type = "Equity"


def _runtime(monkeypatch):
    imports = types.ModuleType("AlgorithmImports")
    imports.DataNormalizationMode = types.SimpleNamespace(
        TOTAL_RETURN="total_return", RAW="raw"
    )
    imports.Resolution = types.SimpleNamespace(DAILY="daily")
    imports.TradeBar = type("TradeBar", (), {})
    worker = types.ModuleType("preopen_control_worker")
    worker.accumulate_peer_aggregates = lambda **_kwargs: None
    worker.build_market_control_summaries = lambda **_kwargs: ([], [])
    worker.build_security_batch_terminals = lambda **_kwargs: []
    worker.peer_aggregate_records = lambda _state: []
    monkeypatch.setitem(sys.modules, "AlgorithmImports", imports)
    monkeypatch.setitem(sys.modules, "preopen_control_worker", worker)
    spec = importlib.util.spec_from_file_location(
        "arv2_test_direct_preopen_runtime", RUNTIME
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _binding(security_id: str, ticker: str, count: int) -> dict[str, object]:
    return symbols.build_runtime_ticker_binding(
        security_id=security_id,
        issuer_id="issuer-" + ticker,
        share_class_id="share-" + ticker,
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


def _history_bindings(*, refuse_b: bool = False):
    rows = [_binding("logical-A", "AAA", 2), _binding("logical-B", "BBB", 2)]
    resolution = symbols.resolve_owner_accepted_qc_symbols(
        rows,
        symbol_factory=lambda ticker: None
        if refuse_b and ticker == "BBB"
        else _Symbol(ticker),
    )
    return rows, symbols.build_accepted_risk_qc_history_bindings(resolution)


def _seed(row: dict[str, object], session: str = "2021-01-04") -> dict[str, object]:
    return {
        "schema": "arv2-preopen-control-universe-terminal-seed-v1",
        "disposition": "accepted",
        "decision_session": session,
        "decision_session_ordinal": 1,
        "decision_open_utc": session + "T14:30:00.000000Z",
        "security_id": row["security_id"],
        "qc_security_id": None,
        "issuer_id": row["issuer_id"],
        "share_class_id": row["share_class_id"],
        "listing_id": row["listing_id"],
        "historical_ticker": row["current_snapshot_ticker"],
        "sector_id": "sector-tech",
        "industry_id": "industry-software",
        "security_master_row_sha256": row["source_row_sha256"],
        "q_data": "0",
        "source_id": "accepted-risk-seed",
        "q_data_measurement": {"fixture": True},
        "qc_sid_mapping_row_sha256": row["row_sha256"],
        "source_sha256": "c" * 64,
        "identity_evidence_sha256": row["identity_evidence_sha256"],
        "identity_available_at": "2021-01-04T13:00:00.000000Z",
        "classification_evidence_sha256": "d" * 64,
        "classification_available_at": "2021-01-04T13:00:00.000000Z",
        "q_data_evidence_sha256": "e" * 64,
        "q_data_available_at": "2021-01-04T13:00:00.000000Z",
    }


def test_runtime_binding_rewrites_resolved_sid_and_names_resolution_refusal(monkeypatch):
    runtime = _runtime(monkeypatch)
    rows, bindings = _history_bindings(refuse_b=True)
    algorithm = types.SimpleNamespace(_accepted_risk_history_bindings=bindings)
    inputs = {
        "universe": [_seed(rows[0]), _seed(rows[1])],
        "sid_mapping": [],
        "fundamentals": [],
        "earnings": [],
        "guidance": [],
        "ratings": [],
    }

    rebound = runtime._apply_accepted_risk_runtime_bindings(algorithm, inputs)

    assert inputs["universe"][0]["qc_security_id"] is None
    assert rebound["universe"][0]["qc_security_id"] == "QC SID AAA"
    assert rebound["universe"][1]["disposition"] == "named_refusal"
    assert rebound["universe"][1]["census_refusal"]["reason"] == (
        "qc_runtime_symbol_resolution_unavailable"
    )
    requested, reverse = runtime._reviewed_batch_symbols(algorithm, rebound)
    assert [symbol.value for symbol in requested] == ["AAA"]
    assert reverse == {"QC SID AAA": "logical-A"}


def test_runtime_binding_refuses_historical_ticker_or_external_id_drift(monkeypatch):
    runtime = _runtime(monkeypatch)
    rows, bindings = _history_bindings()
    algorithm = types.SimpleNamespace(_accepted_risk_history_bindings=bindings)
    seed = _seed(rows[0])
    seed["historical_ticker"] = "WRONG"
    with pytest.raises(
        symbols.AcceptedRiskQcSymbolResolutionError,
        match="ticker or external listing identity differs from admission",
    ):
        runtime._apply_accepted_risk_runtime_bindings(
            algorithm,
            {
                "universe": [seed],
                "sid_mapping": [],
                "fundamentals": [],
                "earnings": [],
                "guidance": [],
                "ratings": [],
            },
        )


def test_direct_runtime_returns_exact_nonformal_summary_and_never_flushes(monkeypatch):
    runtime = _runtime(monkeypatch)
    _rows, bindings = _history_bindings()
    algorithm = types.SimpleNamespace(
        _accepted_risk_history_bindings=bindings,
        _output_shards=[],
        _manifest={"schema": "fixture-input-manifest", "value": 1},
        _peer_records=None,
        _market_records=None,
        _benchmark_rows=None,
    )
    peer = [{"decision_session": "2021-01-04", "peer": "commitment"}]
    market = [{"decision_session": "2021-01-04", "market": "commitment"}]
    terminal = {"decision_session": "2021-01-04", "security_id": "logical-A"}
    passes = 0

    monkeypatch.setattr(runtime, "_market_bounds", lambda _algorithm: (1, 2))
    monkeypatch.setattr(runtime, "_benchmark_history", lambda *_args: ["benchmark"])
    monkeypatch.setattr(
        runtime,
        "_flush_physical_shard",
        lambda *_args: (_ for _ in ()).throw(AssertionError("terminal write")),
    )

    def market_pass(_algorithm, *, emit_terminals, terminal_consumer=None,
                    emission_state=None, **_kwargs):
        nonlocal passes
        passes += 1
        if emit_terminals:
            terminal_consumer(dict(terminal))
            emission_state["terminal_emission_count"] += 1
        return list(peer), list(market)

    monkeypatch.setattr(runtime, "_market_pass", market_pass)
    observed: list[dict[str, object]] = []

    summary = runtime.run_preopen_control_construction_in_process(
        algorithm, observed.append
    )

    assert passes == 2
    assert observed == [terminal]
    assert summary["schema"] == runtime.DIRECT_EMISSION_SUMMARY_SCHEMA
    assert summary["terminal_emission_count"] == 1
    assert summary["object_store_terminal_writes"] == 0
    assert summary["preliminary_evaluation_only"] is True
    assert summary["formal_security_master_authority"] is False
    assert summary["frozen_formal_evaluation_completed"] is False
    semantic = dict(summary)
    declared_id = semantic.pop("summary_id")
    declared_sha = semantic.pop("summary_sha256")
    semantic["summary_id"] = None
    semantic["summary_sha256"] = None
    assert declared_sha == hashlib.sha256(
        (json.dumps(semantic, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    assert declared_id == "arv2-direct-preopen-emission-" + declared_sha[:24]


def test_direct_runtime_refuses_zero_terminal_completion(monkeypatch):
    runtime = _runtime(monkeypatch)
    _rows, bindings = _history_bindings()
    algorithm = types.SimpleNamespace(
        _accepted_risk_history_bindings=bindings,
        _output_shards=[],
        _manifest={"schema": "fixture-input-manifest"},
        _benchmark_rows=None,
    )
    monkeypatch.setattr(runtime, "_market_bounds", lambda _algorithm: (1, 2))
    monkeypatch.setattr(runtime, "_benchmark_history", lambda *_args: [])
    monkeypatch.setattr(runtime, "_market_pass", lambda *_args, **_kwargs: ([], []))
    with pytest.raises(ValueError, match="emitted no terminals"):
        runtime.run_preopen_control_construction_in_process(
            algorithm, lambda _row: None
        )


def test_incremental_runtime_processes_one_batch_per_callback_and_only_then_summarizes(
    monkeypatch,
):
    runtime = _runtime(monkeypatch)
    _rows, bindings = _history_bindings()
    batches = [
        {"security_batch_ordinal": 0},
        {"security_batch_ordinal": 1},
    ]
    algorithm = types.SimpleNamespace(
        _accepted_risk_history_bindings=bindings,
        _output_shards=[],
        _manifest={"resource_census": {"security_batches": batches}},
        _benchmark_rows=None,
        _peer_records=None,
        _market_records=None,
    )
    calls: list[tuple[int, bool]] = []

    class BatchConsumer:
        def __init__(self):
            self.batches: list[list[dict[str, object]]] = []

        def consume_terminal_batch(self, rows):
            self.batches.append(list(rows))

    consumer = BatchConsumer()
    monkeypatch.setattr(runtime, "_market_bounds", lambda _algorithm: (1, 2))
    monkeypatch.setattr(runtime, "_benchmark_history", lambda *_args: ["benchmark"])
    monkeypatch.setattr(runtime, "_market_records", lambda *_args: [])

    def market_batch(_algorithm, *, batch, emit_terminals, terminal_consumer=None,
                     emission_state=None, **_kwargs):
        calls.append((batch["security_batch_ordinal"], emit_terminals))
        if emit_terminals:
            runtime._emit_direct_terminal_rows(
                terminal_consumer,
                [{
                    "decision_session": "2021-01-04",
                    "security_id": f"logical-{batch['security_batch_ordinal']}",
                }],
                emission_state,
            )

    monkeypatch.setattr(runtime, "_market_batch", market_batch)

    begun = runtime.begin_preopen_control_construction_in_process(
        algorithm, consumer
    )
    assert begun["completed_security_batch_passes"] == 0
    assert calls == []
    first = runtime.advance_preopen_control_construction_in_process(algorithm)
    assert first["phase"] == "first_pass"
    assert calls == [(0, False)]
    transitioned = runtime.advance_preopen_control_construction_in_process(algorithm)
    assert transitioned["phase"] == "second_pass"
    assert calls[-1] == (1, False)
    completed = runtime.advance_preopen_control_construction_in_process(
        algorithm, maximum_security_batches=2
    )
    assert completed["complete"] is True
    assert completed["completed_security_batch_passes"] == 4
    assert completed["terminal_emission_count"] == 2
    assert calls == [(0, False), (1, False), (0, True), (1, True)]
    assert [len(rows) for rows in consumer.batches] == [1, 1]
    summary = runtime.finalized_preopen_control_construction_in_process(algorithm)
    assert summary["terminal_emission_count"] == 2
    assert summary["object_store_terminal_writes"] == 0
    assert summary["frozen_formal_evaluation_completed"] is False


def test_direct_terminal_emission_prefers_batch_sink_and_preserves_callable_fallback(
    monkeypatch,
):
    runtime = _runtime(monkeypatch)
    rows = [
        {"decision_session": "2021-01-05", "security_id": "B"},
        {"decision_session": "2021-01-04", "security_id": "A"},
    ]

    class BatchConsumer:
        def __init__(self):
            self.calls = []

        def consume_terminal_batch(self, value):
            self.calls.append(list(value))

    batch = BatchConsumer()
    state = {"terminal_emission_count": 0}
    runtime._emit_direct_terminal_rows(batch, rows, state)
    assert len(batch.calls) == 1
    assert [item["security_id"] for item in batch.calls[0]] == ["A", "B"]
    assert state["terminal_emission_count"] == 2

    observed = []
    fallback_state = {"terminal_emission_count": 0}
    runtime._emit_direct_terminal_rows(observed.append, rows, fallback_state)
    assert [item["security_id"] for item in observed] == ["A", "B"]
    assert fallback_state["terminal_emission_count"] == 2


def test_persisted_preopen_shard_uses_live_verified_single_extension_key(monkeypatch):
    runtime = _runtime(monkeypatch)

    class Store:
        key = None

        def save_bytes(self, key, _payload):
            self.key = key
            return True

    store = Store()
    algorithm = types.SimpleNamespace(
        object_store=store,
        _manifest={
            "resource_census": {"maximum_buffered_terminal_count": 10}
        },
        _output_shards=[],
    )
    runtime._flush_physical_shard(
        algorithm,
        0,
        0,
        [{"decision_session": "2021-01-04", "security_id": "logical-A"}],
    )
    assert store.key.endswith("-jsonl.gz")
    assert ".jsonl.gz" not in store.key
