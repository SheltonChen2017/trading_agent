"""Immutable runtime-v3 driver boundaries; synthetic inputs, no empirical I/O."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from research.target_price_revisions_qc import cap_tilt_driver_v3 as d
from tests.target_price_revisions_qc.test_qc_cap_tilt_bundle import build

OPERATION = "TPR-CAP-TILT-ACCESS-SYNTHETIC-001"


def test_rendered_actual_successor_contains_only_two_closed_six_file_candidates():
    rendered = d.render_sources()
    assert len(rendered["cases"]) == 2
    assert set(row["candidate_id"] for row in rendered["cases"]) == d.ops.CANDIDATES
    assert all(set(row["files"]) == d.ops.SOURCE_FILES for row in rendered["cases"])
    assert rendered["freeze_sha256"] == d.bundle.FREEZE_SHA256
    template = (d.PACKAGE / "cap_tilt_algorithm_v3.py").read_text()
    codec = (d.PACKAGE / "cap_log_transport.py").read_text()
    expanded = template.replace("__CAP_LOG_TRANSPORT_SOURCE_LITERAL__", repr(codec)).encode()
    assert rendered["template_sha256"] == d.ops.digest(expanded)
    for row in rendered["cases"]:
        assert "__CAP_LOG_TRANSPORT_SOURCE_LITERAL__" not in row["files"]["main.py"]
        assert repr(codec) in row["files"]["main.py"]
        assert len(row["files"]["main.py"].encode()) <= 60000
    assert rendered["template_sha256"] != d.ops.digest((d.PACKAGE / "matched_algorithm_v3.py").read_bytes())
    assert rendered["packet_key"].startswith("tpr-cap-tilt/" + d.bundle.STUDY + "/")


def test_prepare_records_fresh_scope_before_the_necessary_packet_read(monkeypatch, prepared_source=None):
    events, receipts = [], {}
    rendered = build()
    source_hashes = {path: "a" * 64 for path in d.REPOSITORY_SOURCES}
    source_hashes[d.ops.FREEZE_PATH] = d.ops.FREEZE_HASH
    monkeypatch.setattr(d, "preflight", lambda: {"head": d.ops.BASELINE, "status": " M record.md"})
    monkeypatch.setattr(d, "render_sources", lambda: rendered)
    def committed(head):
        assert head == d.ops.BASELINE
        events.append("committed")
        return source_hashes
    monkeypatch.setattr(d, "_committed_source_hashes", committed)
    class FakeController:
        def __init__(self, manifest, *, manifest_sha256):
            assert d.ops.digest(d.ops.canonical(manifest)) == manifest_sha256
            d.ops.validate_manifest(manifest, manifest_sha256)
            assert manifest["schema"] == "tpr-qc-cap-tilt-operations-manifest-v1"
            assert len(manifest["candidates"]) == 2
            assert manifest["prepared_packet_source"] == prepared_source
            self.operation = manifest["operation_id"]
        def prepare_access(self):
            events.append("access")
        def exclusive(self, name, value):
            receipts[name] = deepcopy(value)
            events.append(name.split(".", 1)[0])
        def prepare_packet(self):
            assert events == ["committed", "access", "manifest", "source-bundle"]
            events.append("packet")
        def read_private(self, name):
            assert name == "signal-packet." + self.operation + ".json"
            return b"synthetic packet never uploaded"
    monkeypatch.setattr(d.ops, "Operations", FakeController)
    monkeypatch.setattr(d.bundle, "validate_packet_bytes", lambda raw: events.append("validate"))
    result = d.prepare(OPERATION, prepared_packet_source=prepared_source)
    assert events == ["committed", "access", "manifest", "source-bundle", "packet", "validate"]
    manifest = receipts["manifest." + OPERATION + ".json"]
    assert set(manifest["repository_source_hashes"]) == set(d.REPOSITORY_SOURCES)
    assert 2 <= len(d.REPOSITORY_SOURCES) <= 32
    assert len(set(d.REPOSITORY_SOURCES)) == len(d.REPOSITORY_SOURCES)
    assert manifest["packet_path"] == d.ops.PACKET_PATH
    assert manifest["packet_sha256"] == d.bundle.PACKET_SHA256
    assert manifest["max_attempts_per_candidate"] == 3
    assert manifest["max_requests"] == 1000
    assert manifest["max_response_bytes"] == 16777216
    assert manifest["request_timeout_seconds"] == 30
    assert result["operation_id"] == OPERATION
    assert result["prepared_packet_source"] == prepared_source
    assert result["source_bytes_committed"] is True


def test_prepare_contains_no_implicit_network_or_credential_access(monkeypatch):
    monkeypatch.setattr(d.ops.http.client, "HTTPSConnection", lambda *args, **kwargs: pytest.fail("network"))
    original_get = d.ops.os.environ.get
    def guarded_get(key, *args, **kwargs):
        if key in {"QC_USER_ID", "QC_API_TOKEN"}:
            pytest.fail("credential")
        return original_get(key, *args, **kwargs)
    monkeypatch.setattr(d.ops.os.environ, "get", guarded_get)
    test_prepare_records_fresh_scope_before_the_necessary_packet_read(monkeypatch)


def test_successor_prepare_carries_explicit_first_study_copy_into_new_scope(monkeypatch):
    test_prepare_records_fresh_scope_before_the_necessary_packet_read(monkeypatch,
        prepared_source="signal-packet.TPR-CAP-TILT-ACCESS-SYNTHETIC-000.json")


@pytest.mark.parametrize("operation", [None, "", "../foreign", "a/b", "x" * 81])
def test_unbounded_operation_refuses_before_repository_or_private_reads(operation, monkeypatch):
    monkeypatch.setattr(d, "preflight", lambda: pytest.fail("repository read before operation validation"))
    monkeypatch.setattr(d.ops, "_read", lambda *args: pytest.fail("private read"))
    with pytest.raises(d.ops.Refusal, match="operation"):
        d.prepare(operation)
    with pytest.raises(d.ops.Refusal, match="operation"):
        d.controller_for(operation)


@pytest.mark.parametrize("mode", ["matching", "different", "uncommitted"])
def test_source_inventory_requires_exact_committed_bytes_without_operator_state(mode, monkeypatch):
    paths = ("research/target_price_revisions_qc/cloud_algorithm_v2.py", "research/target_price_revisions_qc/packet.py")
    monkeypatch.setattr(d, "REPOSITORY_SOURCES", paths)
    def git(args, **kwargs):
        assert args[:2] == ["git", "show"]
        assert kwargs["cwd"] == d.ops.LANE
        assert args[2].startswith(d.ops.BASELINE + ":")
        if mode == "uncommitted":
            raise subprocess.CalledProcessError(128, args)
        relative = args[2].split(":", 1)[1]
        raw = (d.ops.LANE / relative).read_bytes()
        return SimpleNamespace(stdout=raw if mode == "matching" else raw + b"# synthetic different source\n")
    monkeypatch.setattr(d.subprocess, "run", git)
    if mode == "matching":
        assert d._committed_source_hashes(d.ops.BASELINE) == {path: d.ops.digest((d.ops.LANE / path).read_bytes()) for path in paths}
    else:
        with pytest.raises(d.ops.Refusal, match="committed"):
            d._committed_source_hashes(d.ops.BASELINE)


def test_uncommitted_source_refuses_before_access_receipts_or_packet(monkeypatch):
    monkeypatch.setattr(d, "preflight", lambda: {"head": d.ops.BASELINE, "status": "?? source.py"})
    def uncommitted(head):
        raise d.ops.Refusal("every declared source must be committed before prepare")
    monkeypatch.setattr(d, "_committed_source_hashes", uncommitted)
    monkeypatch.setattr(d, "render_sources", lambda: pytest.fail("render after source refusal"))
    monkeypatch.setattr(d.ops, "Operations", lambda *args, **kwargs: pytest.fail("access after source refusal"))
    with pytest.raises(d.ops.Refusal, match="committed"):
        d.prepare(OPERATION)


@pytest.mark.parametrize("action", ["create", "source-upload", "reserve", "compile", "launch", "status", "collect"])
def test_explicit_candidate_is_required(action, monkeypatch):
    monkeypatch.setattr(d, "controller_for", lambda operation: object())
    with pytest.raises(SystemExit) as error:
        d.main([action, "--operation", OPERATION])
    assert error.value.code == 2


@pytest.mark.parametrize("action", ["compile", "compile-status", "launch", "status", "collect"])
def test_attempt_identity_is_required_for_attempt_stages(action, monkeypatch):
    monkeypatch.setattr(d, "controller_for", lambda operation: object())
    with pytest.raises(SystemExit) as error:
        d.main([action, "--operation", OPERATION, "--candidate", "TPR-CAP-TILT-ON-BASE-v1"])
    assert error.value.code == 2


def test_cli_never_implicitly_reuses_an_operation_or_old_matched_candidate(monkeypatch):
    monkeypatch.setattr(d, "controller_for", lambda operation: pytest.fail("unexpected operation"))
    for args in (["authenticate"], ["create", "--operation", OPERATION, "--candidate", "TPR-MATCHED-ON-BASE-v1"]):
        with pytest.raises(SystemExit) as error:
            d.main(args)
        assert error.value.code == 2


def test_prepared_packet_source_option_cannot_be_used_as_an_upload_or_launch_override(monkeypatch):
    monkeypatch.setattr(d, "controller_for", lambda *args: pytest.fail("operation after invalid copy option"))
    with pytest.raises(SystemExit) as error:
        d.main(["authenticate", "--operation", OPERATION, "--prepared-packet-source", "signal-packet.prior.json"])
    assert error.value.code == 2


def test_reachable_accounting_and_raw_backtest_sources_are_declared():
    assert {
        "research/target_price_revisions_qc/matched_audit.py",
        "research/target_price_revisions_qc/matched_bundle.py",
        "research/target_price_revisions_development/raw_backtest.py",
    } <= set(d.REPOSITORY_SOURCES)
    assert len(d.REPOSITORY_SOURCES) == 21
    assert "research/target_price_revisions_development/raw_execution.py" not in d.REPOSITORY_SOURCES


def test_import_does_not_prepare_or_launch(monkeypatch):
    import importlib
    monkeypatch.setattr(d.ops, "Operations", lambda *args, **kwargs: pytest.fail("operation on import"))
    importlib.reload(d)
    assert callable(d.main)


def collected_fixture(*, errors=False):
    return {"completion": {"collection_errors": ["incomplete"] if errors else [],
                           "strategy_accepted": False, "canonical_admission": False},
        "receipt_prefix": "synthetic.collection.0001", "collection_round": 1,
        "result_response": {"success": True, "backtest": {"statistics": {"Drawdown": "11%"},
            "totalPerformance": {"tradeStatistics": {"totalNumberOfTrades": 3}}}},
        "logs_response": {"success": True, "logs": []}, "order_pages": [],
        "source_receipt": {"evidence_hashes": {"result": "a" * 64}},
        "candidate_config": {"slippage": "0.001"}}


class CollectController:
    def __init__(self, value):
        self.value, self.receipts = value, {}
    def collect_terminal(self, candidate, attempt):
        assert candidate == "TPR-CAP-TILT-ON-BASE-v1" and attempt == 1
        return self.value
    def exclusive(self, name, value):
        assert name not in self.receipts
        self.receipts[name] = deepcopy(value)


def audit_stub(monkeypatch, function):
    monkeypatch.setitem(sys.modules, "research.target_price_revisions_qc.cap_tilt_audit",
                        SimpleNamespace(audit_result=function))


def test_collect_passes_original_evidence_to_auditor_without_rebinding(monkeypatch):
    value = collected_fixture()
    before = deepcopy(value)
    controller = CollectController(value)
    def audit(*args):
        for supplied, field in zip(args, ("result_response", "logs_response", "order_pages", "source_receipt", "candidate_config")):
            assert supplied is value[field]
        return {"meaningful_execution": False, "diagnostic_reasons": ["synthetic diagnostic"], "canonical_admission": False}
    audit_stub(monkeypatch, audit)
    evidence = d.collect_and_audit(controller, "TPR-CAP-TILT-ON-BASE-v1", 1)
    assert evidence["meaningful_execution"] is False
    assert evidence["diagnostic_reasons"] == ["synthetic diagnostic"]
    assert evidence["qc_headline_drawdown"] == "11%"
    assert evidence["native_closed_trades"] == 3
    assert evidence["drawdown_sampling_reconciled"] is False
    assert evidence["attempt"] == evidence["collection_round"] == 1
    assert controller.receipts["synthetic.collection.0001.interpreted.json"] == evidence
    assert value == before


def test_collection_failure_never_calls_auditor_or_claims_interpretation(monkeypatch):
    controller = CollectController(collected_fixture(errors=True))
    audit_stub(monkeypatch, lambda *args: pytest.fail("audit after collection failure"))
    assert d.collect_and_audit(controller, "TPR-CAP-TILT-ON-BASE-v1", 1) is controller.value["completion"]
    assert controller.receipts == {}


def test_audit_refusal_is_durably_retained_without_becoming_success(monkeypatch):
    controller = CollectController(collected_fixture())
    def refusal(*args):
        raise ValueError("synthetic private text must not be echoed")
    audit_stub(monkeypatch, refusal)
    result = d.collect_and_audit(controller, "TPR-CAP-TILT-ON-BASE-v1", 1)
    assert result["classification"] == "diagnostic_or_incomplete"
    assert result["pure_audit_errors"] == ["pure_audit_refused"]
    assert result["strategy_accepted"] is False and result["canonical_admission"] is False
    assert set(controller.receipts) == {"synthetic.collection.0001.audit-error.json"}
    assert "synthetic private text" not in str(controller.receipts)
    assert controller.value["completion"]["collection_errors"] == []  # Original receipt remains unchanged.


@pytest.mark.parametrize("performance", [None, {}, {"tradeStatistics": None}, {"tradeStatistics": []}])
def test_unavailable_qc_metadata_stays_unknown_not_zero(performance, monkeypatch):
    value = collected_fixture()
    value["result_response"]["backtest"].update(statistics=None, totalPerformance=performance)
    controller = CollectController(value)
    audit_stub(monkeypatch, lambda *args: {"meaningful_execution": False, "canonical_admission": False})
    result = d.collect_and_audit(controller, "TPR-CAP-TILT-ON-BASE-v1", 1)
    assert result["qc_headline_drawdown"] is None
    assert result["native_closed_trades"] is None
    assert result["meaningful_execution"] is False


def test_successor_keeps_executed_driver_template_controller_and_bundle_immutable():
    from research.target_price_revisions_qc import cap_tilt_driver_v2 as original
    expected = {
        "cap_tilt_driver.py": "e93f20264f24eb99406a41198e555912c7a86aaa38295afba734e0ef024b11ed",
        "cap_tilt_algorithm.py": "c8804b43b9a25b5fe1ce3f8b5fac424c129c9e7b39a4ad0480b3fbd98e98ab37",
        "cap_tilt_operations.py": "d4d9b8e7500388e294a703ad7262a1e825a6c99762d8b0367bc10a52beb2904a",
        "cap_tilt_bundle.py": "4815d53e8eff7038c67c39541eb29d56ea7072f17f64f749e3075e9898936f9a",
    }
    assert all(d.ops.digest((d.PACKAGE / name).read_bytes()) == value for name, value in expected.items())
    assert original.REPOSITORY_SOURCES == tuple(path for path in d.REPOSITORY_SOURCES
        if path not in {"research/target_price_revisions_qc/cap_tilt_driver_v3.py",
                        "research/target_price_revisions_qc/cap_tilt_algorithm_v3.py",
                        "research/target_price_revisions_qc/cap_log_transport.py"})
    assert d.ops is original.ops and d.bundle is original.bundle
    assert d.render_sources is not original.render_sources
    assert d.prepare is not original.prepare
    assert d.collect_and_audit is not original.collect_and_audit


def test_runtime_successor_changes_only_main_source_not_frozen_candidate_economics():
    from research.target_price_revisions_qc import cap_tilt_driver as original
    v1, v2 = original.render_sources(), d.render_sources()
    assert v1["template_sha256"] != v2["template_sha256"]
    assert v1["freeze_sha256"] == v2["freeze_sha256"] == d.bundle.FREEZE_SHA256
    assert v1["packet_key"] == v2["packet_key"]
    assert len(v2["cases"]) == 2
    for first, successor in zip(v1["cases"], v2["cases"]):
        assert first["candidate_id"] == successor["candidate_id"]
        assert first["arm"] == successor["arm"]
        assert first["cost"] == successor["cost"]
        assert first["config_sha256"] == successor["config_sha256"]
        assert set(successor["files"]) == d.ops.SOURCE_FILES
        assert first["source_hashes"]["main.py"] != successor["source_hashes"]["main.py"]
        for name in d.ops.SOURCE_FILES - {"main.py"}:
            assert first["files"][name] == successor["files"][name]
            assert first["source_hashes"][name] == successor["source_hashes"][name]


def test_cli_successor_prepare_preserves_explicit_original_study_capture(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(d, "preflight", lambda: {"head": d.ops.BASELINE, "status": ""})
    def capture(operation, *, prepared_packet_source=None):
        calls.append((operation, prepared_packet_source))
        return {"prepared_packet_source": prepared_packet_source}
    monkeypatch.setattr(d, "prepare", capture)
    d.main(["prepare", "--operation", "scope002",
            "--prepared-packet-source", "signal-packet.scope001.json"])
    assert calls == [("scope002", "signal-packet.scope001.json")]
    assert "signal-packet.scope001.json" in capsys.readouterr().out


def test_failed_native_runtime_evidence_is_not_rewritten_or_accepted(monkeypatch):
    value = collected_fixture()
    native = value["result_response"]["backtest"]
    native.update(status="Runtime Error", completed=False, progress="0.73",
                  error="synthetic native compatibility failure")
    before = deepcopy(value)
    controller = CollectController(value)
    def audit(*args):
        assert args[0] is value["result_response"]
        assert args[0]["backtest"]["status"] == "Runtime Error"
        assert args[0]["backtest"]["completed"] is False
        return {"meaningful_execution": False, "development_execution_qualified": False,
                "diagnostic_reasons": ["terminal_or_incomplete"], "canonical_admission": False}
    audit_stub(monkeypatch, audit)
    result = d.collect_and_audit(controller, "TPR-CAP-TILT-ON-BASE-v1", 1)
    assert result["meaningful_execution"] is False
    assert result["development_execution_qualified"] is False
    assert result["diagnostic_reasons"] == ["terminal_or_incomplete"]
    assert value == before


def test_new_runtime_source_must_be_committed_before_any_access_or_copy(monkeypatch):
    runtime = "research/target_price_revisions_qc/cap_tilt_algorithm_v3.py"
    assert runtime in d.REPOSITORY_SOURCES
    monkeypatch.setattr(d, "preflight", lambda: {"head": d.ops.BASELINE, "status": "?? " + runtime})
    def uncommitted(head):
        assert runtime in d.REPOSITORY_SOURCES
        raise d.ops.Refusal("new runtime is uncommitted")
    monkeypatch.setattr(d, "_committed_source_hashes", uncommitted)
    monkeypatch.setattr(d, "render_sources", lambda: pytest.fail("render after uncommitted runtime"))
    monkeypatch.setattr(d.ops, "Operations", lambda *args, **kwargs: pytest.fail("receipt or copy after refusal"))
    with pytest.raises(d.ops.Refusal, match="uncommitted"):
        d.prepare("scope002", prepared_packet_source="signal-packet.scope001.json")
