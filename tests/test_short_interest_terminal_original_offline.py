"""Fabricated protected originals only; no actual source or key read."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from short_interest_capture_fixtures import portable_capture_platform
from data.hashing import canonical_json, hash_bytes, hash_payload
import scripts.qualify_short_interest_terminal_original_offline as build
from test_short_interest_terminal_original_evidence import descriptor

_POSIX = pytest.mark.skipif(not hasattr(os, "getuid"), reason="protected POSIX custody required; SI-CR-WIN-20261012-002")
HEAD, REMOTE = "a" * 40, "b" * 40
START = "2026-10-14T00:01:00Z"
END = "2026-10-14T00:02:00Z"


@pytest.fixture
def source(tmp_path, monkeypatch):
    spec = descriptor()
    protocol = {"requests": [spec], "missing_cases": [{"case": "FRC", "code": "terminal_original_candidate_unavailable"}]}
    digest = hash_payload(protocol)
    monkeypatch.setattr(build, "SOURCE_PROTOCOL_SHA256", digest)
    monkeypatch.setattr(build.originals, "EXPECTED_PROTOCOL_SHA256", digest)
    monkeypatch.setattr(build.originals, "_source", lambda *args, **kwargs: {"completed_at": "2026-10-13T23:00:00Z"})
    monkeypatch.setattr(build.originals, "build_protocol", lambda *args: protocol)
    monkeypatch.setattr(build, "_historical_identity", lambda *args, **kwargs: "c" * 64)
    guards = []
    monkeypatch.setattr(build, "_guard", lambda *args: guards.append(args))
    monkeypatch.setattr(build.originals, "_guard", lambda *args: guards.append(args))
    monkeypatch.setattr(build, "_git", lambda *args: args[-1])
    monkeypatch.setattr(build, "_CODE_FILES", ())
    clocks = iter((START, END, END))
    monkeypatch.setattr(build, "_utc_now", lambda: next(clocks, END))
    directory = build._prepare_capture_directory(tmp_path / build.SOURCE)
    began, received_at = "2026-10-13T23:00:10Z", "2026-10-13T23:00:11Z"
    raw = b"<p>USD 12.50 per share of common stock, excluding appraisal holders. Payment upon surrender.</p>"
    request_sha = hash_payload(spec)
    received = {"schema": "si-terminal-original-response-v1", "attempt": 1,
                "request_id": spec["request_id"], "request_sha256": request_sha,
                "http_status": 200, "content_type": "text/html", "raw_path": "attempt-01.raw",
                "raw_bytes": len(raw), "raw_sha256": hash_bytes(raw), "received_at": received_at}
    report = {"schema": "si-terminal-original-evidence-v1", "protocol_sha256": digest,
              "source_report_sha256": build.originals.SOURCE_REPORT_SHA256, "retrieved_at": received_at,
              "documents": [{"descriptor": spec, "receipt": received, "HTTPS_transport_origin_verified": True,
                             "terminal_economics_admitted": False, "payment_cash_settlement_verified": False}],
              "missing_cases": protocol["missing_cases"], "terminal_economics_admitted": False,
              "payment_cash_settlement_verified": False, "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
    report["report_sha256"] = hash_payload(report)
    encoded = (canonical_json(report) + "\n").encode()
    monkeypatch.setattr(build, "SOURCE_REPORT_SHA256", report["report_sha256"])
    monkeypatch.setattr(build, "SOURCE_REPORT_BYTES_SHA256", hash_bytes(encoded))
    def publish(name, value, raw=False):
        (build.originals._publish if raw else build.originals._publish_json)(directory, name, value)
    publish("protocol.private.json", protocol)
    publish("started.json", {"schema": "si-terminal-original-start-v1", "code_head": build.SOURCE_HEAD,
        "remote_head": REMOTE, "code_identity_sha256": "c" * 64, "protocol_sha256": digest,
        "started_at": began, "maximum_attempts": 1, "outcome_looks": 0, "qc_attempts": 0})
    publish("completed.json", {"schema": "si-terminal-original-completion-v1", "status": "capture_complete",
        "code_head": build.SOURCE_HEAD, "protocol_sha256": digest, "http_attempts": 1,
        "private_report_sha256": report["report_sha256"], "completed_at": received_at,
        "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False})
    build.originals._publish_json(directory.parent, "budget-" + digest + ".json", {
        "schema": "si-terminal-original-budget-v1", "code_head": build.SOURCE_HEAD, "remote_head": REMOTE,
        "run_id": directory.name, "protocol_sha256": digest, "source_report_sha256": build.originals.SOURCE_REPORT_SHA256,
        "maximum_attempts": 1, "started_at": began, "resumption_or_restart_allowed": False})
    publish("attempt-01.started.json", {"schema": "si-terminal-original-request-start-v1", "attempt": 1,
        "request_id": spec["request_id"], "request": spec, "request_sha256": request_sha,
        "code_head": build.SOURCE_HEAD, "protocol_sha256": digest, "started_at": began})
    publish("attempt-01.raw", raw, raw=True)
    publish("attempt-01.received.json", received)
    publish("originals.private.json", encoded, raw=True)
    return directory, guards


@_POSIX
def test_fixed_original_receipts_budget_and_report_rebuild_before_private_language_qualification(tmp_path, source):
    directory, guards = source
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    result = build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert result["status"] == "terminal_original_offline_complete"
    assert all(result[key] == 0 for key in ("provider_requests", "credential_reads", "outcome_looks", "qc_attempts"))
    assert result["backtest_result_exists"] is False
    output = tmp_path / build.OUTPUT
    report = json.loads((output / "evidence.private.json").read_bytes())
    assert report["report_sha256"] == result["private_report_sha256"]
    assert result["private_report_bytes_sha256"] == hash_bytes((output / "evidence.private.json").read_bytes())
    assert report["authority"]["payment_cash_settlement_verified"] is False
    assert report["documents"][0]["assertions"]
    assert before == {path.name: path.read_bytes() for path in directory.iterdir()}
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in output.iterdir())
    assert guards


@pytest.mark.parametrize("change", ["raw", "report", "budget", "status", "descriptor", "counter", "clock", "extra", "mode", "symlink"])
@_POSIX
def test_exact_source_custody_changes_refuse_before_any_new_output(tmp_path, source, change):
    directory, _ = source
    if change in {"raw", "report"}:
        path = directory / ("attempt-01.raw" if change == "raw" else "originals.private.json")
        path.write_bytes(path.read_bytes() + b" ")
    elif change == "extra":
        build.originals._publish_json(directory, "unknown.json", {})
    elif change == "mode":
        (directory / "attempt-01.raw").chmod(0o644)
    elif change == "symlink":
        path = directory / "attempt-01.raw"
        old = tmp_path / "old-fixture"
        path.rename(old)
        path.symlink_to(old)
    else:
        path = (directory.parent / ("budget-" + build.SOURCE_PROTOCOL_SHA256 + ".json") if change == "budget"
                else directory / ("attempt-01.received.json" if change == "status"
                                   else "attempt-01.started.json" if change == "descriptor" else "completed.json"))
        value = json.loads(path.read_bytes())
        if change == "budget":
            value["resumption_or_restart_allowed"] = True
        elif change == "status":
            value["http_status"] = 403
        elif change == "descriptor":
            value["request"]["url"] = "https://www.sec.gov/Archives/other.htm"
        elif change == "counter":
            value["qc_attempts"] = False
        else:
            value["completed_at"] = "2026-10-13T23:00:10Z"
        path.write_bytes((canonical_json(value) + "\n").encode())
    with pytest.raises(build.CaptureRefusal):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert not (tmp_path / build.OUTPUT).exists()


@_POSIX
def test_owned_output_cannot_be_overwritten_or_refusal_written_on_rerun(tmp_path, source):
    build._build(tmp_path, head=HEAD, remote=REMOTE)
    output = tmp_path / build.OUTPUT
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    with pytest.raises(build.TerminalOriginalOfflineRefusal, match="already_exists"):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    assert before == {path.name: path.read_bytes() for path in output.iterdir()}


@_POSIX
def test_bad_completion_clock_retains_private_partial_and_owned_refusal_not_completed(tmp_path, source, monkeypatch):
    clocks = iter((START, "2026-10-14T00:00:59Z", END))
    monkeypatch.setattr(build, "_utc_now", lambda: next(clocks))
    with pytest.raises(build.CaptureRefusal, match="chronology"):
        build._build(tmp_path, head=HEAD, remote=REMOTE)
    output = tmp_path / build.OUTPUT
    assert (output / "evidence.private.json").exists() and (output / "refused.json").exists()
    assert not (output / "completed.json").exists()


@pytest.mark.usefixtures("portable_capture_platform")
def test_historical_identity_uses_exact_binary_old_blobs_not_current_source(monkeypatch):
    names = ("scripts/fixture-one.py", "scripts/fixture-two.py")
    monkeypatch.setattr(build.originals, "_CODE_FILES", names)
    monkeypatch.setattr(build, "_guard", lambda *args: None)
    def run(command, **kwargs):
        assert command[:2] == ["git", "show"] and command[2].startswith(build.SOURCE_HEAD + ":")
        name = command[2].split(":", 1)[1]
        return SimpleNamespace(returncode=0, stdout=("historical-" + name + "\n").encode())
    monkeypatch.setattr(build, "subprocess", SimpleNamespace(run=run))
    assert build._historical_identity(Path("/fixture"), head=HEAD, remote=REMOTE) == hash_payload({
        "git_commit": build.SOURCE_HEAD, "files": [{"path": name, "sha256": hash_bytes(("historical-" + name + "\n").encode())} for name in names]})


@pytest.mark.parametrize("entry", ["_source", "_historical_identity", "_build", "main"])
def test_first_host_guard_prevents_all_offline_sensitive_access(tmp_path, monkeypatch, entry):
    def deny():
        raise build.CapturePlatformRefusal()
    monkeypatch.setattr(build, "_require_capture_platform", deny)
    monkeypatch.setattr(build, "_guard", lambda *args: pytest.fail("lane read before host guard"))
    monkeypatch.setattr(build.originals, "_source", lambda *args, **kwargs: pytest.fail("original read before host guard"))
    if entry == "main":
        monkeypatch.setattr(build, "_build", lambda *args, **kwargs: pytest.fail("offline build before CLI host guard"))
        assert build.main(["--expected-head", HEAD, "--expected-remote", REMOTE]) == 2
    else:
        with pytest.raises(build.CapturePlatformRefusal):
            getattr(build, entry)(tmp_path, head=HEAD, remote=REMOTE)
    assert not list(tmp_path.iterdir())
