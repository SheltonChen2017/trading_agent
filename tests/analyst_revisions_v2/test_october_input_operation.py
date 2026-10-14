"""Synthetic one-shot orchestration only; no retained source or credentials."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from scripts import build_arv2_october_comparison_inputs as d

HEAD, SHA = "a" * 40, "b" * 64


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    monkeypatch.setattr(d.subprocess, "run", lambda *_a, **_k: pytest.fail("real command forbidden"))
    monkeypatch.setattr(d.diagnostic.original.credentials, "load_key", lambda *_a, **_k: pytest.fail("credentials forbidden"))
    for name in ("run", "_run", "_claim", "_preflight"):
        monkeypatch.setattr(d.diagnostic, name, lambda *_a, **_k: pytest.fail("spent operation forbidden"))
    monkeypatch.setattr(d.recovered, "authenticate_retained_capture", lambda *_a, **_k: pytest.fail("real source forbidden"))


@pytest.fixture
def control(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    path = tmp_path / "D5-SYNTHETIC"
    monkeypatch.setattr(d, "CONTROL", path)
    monkeypatch.setattr(d, "_preflight", lambda *_a: None)
    monkeypatch.setattr(d.capture, "_require_operational_artifact_scope", lambda *_a: None)
    return path


def test_claim_precedes_only_composition_and_normal_exit_bound(control, monkeypatch, capsys):
    def compose(deadline, stage):
        assert (control / "claim.json").is_file()
        stage[0] = "new_package_authentication"
        return {"synthetic_only": True}
    monkeypatch.setattr(d, "_compose", compose)
    assert d.run(HEAD, SHA) == 0
    envelope = json.loads(capsys.readouterr().out)
    report = envelope["report"]
    assert report["terminal"] == "october_package_prepared"
    assert report["attempt_consumed"] is True
    for key in ("original_capture_accepted", "formal_source_admitted", "provider_contact_authorized",
                "point_in_time_proven", "backtest_ready", "paper_or_live_ready"):
        assert report[key] is False
    assert report["qc_calls"] == report["outcome_reads"] == 0
    assert report["provider_request_count"] is None
    payload = (control / "report.json").read_bytes()
    assert envelope["report_bytes"] == len(payload)
    assert envelope["report_sha256"] == hashlib.sha256(payload).hexdigest()
    assert "assistant.dispatch_fence" not in sys.modules


def test_claim_collision_spends_ambiguously_without_source(control, monkeypatch, capsys):
    control.mkdir(mode=0o700)
    monkeypatch.setattr(d, "_compose", lambda *_a: pytest.fail("duplicate source call"))
    assert d.run(HEAD, SHA) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["attempt_consumed"] is None and report["stage"] == "claim"


def test_preflight_failure_never_claims(control, monkeypatch, capsys):
    def refuse(*_a):
        raise d.InputOperationError("private irrelevant")
    monkeypatch.setattr(d, "_preflight", refuse)
    monkeypatch.setattr(d, "_compose", lambda *_a: pytest.fail("source"))
    assert d.run(HEAD, SHA) == 2
    assert not control.exists()
    text = capsys.readouterr().out
    assert "private irrelevant" not in text
    assert json.loads(text)["attempt_consumed"] is False


@pytest.mark.parametrize("exc,expected", [
    (d.recovered.RatingsDeltaV2Error("conflicting_provider_id"), "conflicting_provider_id"),
    (d.recovered.RatingsDeltaV2Error("PRIVATE ROW"), "unknown"),
    (d.october.OctoberOrderInputPackageError("PRIVATE ROW"), "unknown"),
    (RuntimeError("PRIVATE ROW"), "unknown"),
])
def test_failure_is_finite_and_never_success(control, monkeypatch, capsys, exc, expected):
    def refuse(_deadline, stage):
        stage[0] = "october_composition"
        raise exc
    monkeypatch.setattr(d, "_compose", refuse)
    assert d.run(HEAD, SHA) == 2
    text = capsys.readouterr().out
    assert "PRIVATE" not in text
    report = json.loads(text)["report"]
    assert report["package"] is None and report["refusal_code"] == expected
    assert report["stage"] == "october_composition"


def test_hostile_exception_payload_never_rendered():
    class Opaque:
        def __str__(self):
            pytest.fail("str private exception")
        def __repr__(self):
            pytest.fail("repr private exception")
    assert d._failure(d.recovered.RatingsDeltaV2Error(Opaque())) == ("ratings_delta_v2_error", "unknown")
    assert d._failure(ValueError(Opaque())) == ("value_error", "unknown")


def test_known_frozen_archive_message_is_retained_as_finite_code():
    exc = d.historical.load_physical_accepted_risk_archive.__globals__["PhysicalAcceptedRiskArchiveError"](
        "accepted-risk reload does not match its external trust pin")
    assert d._failure(exc) == ("physical_accepted_risk_archive_error",
        "physical_accepted_risk_archive_error:literal_8b8f1d9150d9328a")


def test_oversized_report_is_not_published(control, monkeypatch, capsys):
    monkeypatch.setattr(d, "_compose", lambda *_a: {"synthetic_only": "x" * d.MAX_REPORT_BYTES})
    assert d.run(HEAD, SHA) == 2
    assert json.loads(capsys.readouterr().out)["terminal"] == "input_publication_ambiguous"
    assert not (control / "report.json").exists()


def test_selected_frozen_source_pins_match():
    assert len(d.SOURCE_PINS) == 34
    for relative, expected in d.SOURCE_PINS.items():
        assert hashlib.sha256((d.ROOT / relative).read_bytes()).hexdigest() == expected
    assert set(d.failure.SOURCE_PINS.items()) <= set(d.SOURCE_PINS.items())


def test_alarm_spends_without_retry(control, monkeypatch, capsys):
    calls = []
    def hang(*_a):
        calls.append(True)
        time.sleep(1)
    monkeypatch.setattr(d, "DEADLINE_SECONDS", 0.03)
    monkeypatch.setattr(d, "_compose", hang)
    start = time.monotonic()
    assert d.run(HEAD, SHA) == 2
    assert time.monotonic() - start < 0.5 and calls == [True]
    assert json.loads(capsys.readouterr().out)["backtest_ready"] is False


def test_late_positive_report_does_not_override_actual_exit(control, monkeypatch, capsys):
    monkeypatch.setattr(d, "_compose", lambda *_a: {"synthetic_only": True})
    write, clock, late = d.transport._write_held, time.monotonic, []
    def publish(directory, name, value):
        result = write(directory, name, value)
        if name == "report.json":
            late.append(True)
        return result
    monkeypatch.setattr(d.transport, "_write_held", publish)
    monkeypatch.setattr(time, "monotonic", lambda: 10**20 if late else clock())
    assert d.run(HEAD, SHA) == 2
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["terminal"] == "input_publication_ambiguous" and "report" not in envelope
    assert json.loads((control / "report.json").read_bytes())["terminal"] == "october_package_prepared"


@pytest.mark.parametrize("mutation", ["none", "root", "branch", "head", "dirty", "stderr", "returncode", "pin", "caller", "empty"])
def test_exact_preflight(monkeypatch, mutation):
    monkeypatch.setattr(d, "SOURCE_PINS", {} if mutation == "empty" else {f"fixture-{n}.py": SHA for n in range(20)})
    output = [str(d.ROOT), d.BRANCH, HEAD, ""]
    if mutation in ("root", "branch", "head", "dirty"):
        output[("root", "branch", "head", "dirty").index(mutation)] = "wrong"
    monkeypatch.setattr(d.subprocess, "run", lambda *_a, **_k: SimpleNamespace(
        stdout=(output.pop(0)+"\n").encode(), stderr=b"unexpected" if mutation == "stderr" else b"",
        returncode=1 if mutation == "returncode" else 0))
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: "c"*64 if (
        mutation == "pin" and path != d.SOURCE or mutation == "caller" and path == d.SOURCE) else SHA)
    if mutation == "none":
        d._preflight(HEAD, SHA, time.monotonic()+10)
    else:
        with pytest.raises(ValueError):
            d._preflight(HEAD, SHA, time.monotonic()+10)


def test_source_failure_precedes_all_history_reads(monkeypatch):
    def refuse(*_a, **_k):
        raise d.recovered.RatingsDeltaV2Error("conflicting_provider_id")
    monkeypatch.setattr(d.recovered, "authenticate_retained_capture", refuse)
    monkeypatch.setattr(d.latest, "load_latest_order_input_package", lambda *_a, **_k: pytest.fail("history after refused source"))
    stage = ["start"]
    with pytest.raises(d.recovered.RatingsDeltaV2Error):
        d._compose(time.monotonic()+10, stage)
    assert stage == ["retained_source_reauthentication"]


def test_composition_routes_exact_bound_inputs_retains_reconstruction_and_reloads(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "CONTROL", tmp_path / "D5-synthetic")
    calls, source, predecessor, parent, prior, tail, packet, proposal, decision, firms, contract = [], *[object() for _ in range(10)]
    activation = SimpleNamespace(object_store_key="arv2/synthetic/activation.json", content_sha256="c"*64, byte_count=100)
    package = SimpleNamespace(package_path=d.CONTROL/"package"/"synthetic-package", package_sha256="d"*64,
        upload_objects=(activation,), total_upload_byte_count=200, contribution_census=(("combined_contribution_count",13020),))
    value = SimpleNamespace(package=package, lineage_sha256="e"*64, lineage_bytes=b"synthetic-lineage",
        lineage={"session_count":3466}, recovered_tail_contribution_count=2, fresh_contribution_count=3)
    sidecar = d.CONTROL/"package"/"synthetic-lineage"/"lineage.json"
    def source_call(path, **kwargs):
        assert path == d.RETAINED
        assert kwargs == dict(expected_manifest_sha256=d.diagnostic.MANIFEST_SHA256,
                              expected_manifest_byte_count=d.diagnostic.MANIFEST_BYTES)
        calls.append("source")
        return source
    monkeypatch.setattr(d.recovered, "authenticate_retained_capture", source_call)
    monkeypatch.setattr(d.latest, "load_latest_order_input_package", lambda *a, **k: predecessor)
    def archive(**kwargs):
        calls.append("archive")
        return {d.historical.PARENT_ARCHIVE_PATH:parent,d.historical.DELTA_ARCHIVE_PATH:prior,d.TAIL:tail}[kwargs["archive_path"]]
    monkeypatch.setattr(d.historical, "load_physical_accepted_risk_archive", archive)
    monkeypatch.setattr(d.historical, "load_physical_firm_ontology_review_packet", lambda **k: packet)
    def propose(**kwargs):
        assert kwargs == dict(review_packet=packet,output_root=d.CONTROL/"firm-proposal")
        return proposal
    monkeypatch.setattr(d.historical, "build_firm_ontology_proposal", propose)
    monkeypatch.setattr(d.historical, "build_firm_ontology_owner_decision", lambda **k: decision)
    monkeypatch.setattr(d.historical, "build_section72_owner_waived_firm_admission", lambda **k: firms)
    monkeypatch.setattr(d.historical, "_global_contract", lambda: contract)
    def compose(**kwargs):
        assert kwargs == dict(predecessor=predecessor,parent_archive=parent,prior_delta_archive=prior,
            tail_archive=tail,ratings_delta=source,firm_admission=firms,global_contract=contract,output_root=d.CONTROL/"package")
        calls.append("compose")
        return value
    monkeypatch.setattr(d.october, "build_october_order_input_package", compose)
    monkeypatch.setattr(d.october, "persist_october_order_input_lineage", lambda *a: sidecar)
    def reload(path, **kwargs):
        assert path == package.package_path and kwargs == dict(expected_package_sha256=package.package_sha256,
            lineage_path=sidecar,expected_lineage_sha256=value.lineage_sha256)
        calls.append("reload")
        return value
    monkeypatch.setattr(d.october, "load_october_order_input_package", reload)
    result = d._compose(time.monotonic()+10,["start"])
    assert calls == ["source","archive","archive","archive","compose","reload"]
    assert result["combined_contribution_count"] == 13020
    assert result["valuation_end_session"] == "2026-10-13"
    assert result["decision_cutoff_session"] == "2026-10-12"
    assert "rows" not in json.dumps(result) and "source" not in result
