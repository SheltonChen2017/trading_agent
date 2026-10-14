"""Synthetic output-only reader checks, never real diagnostic output reads."""
from __future__ import annotations

import ast
import copy
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import os
from pathlib import Path

import pytest

from scripts import read_arv2_massive_oct12_diagnostic as r

d = r.caller
HEAD = "c" * 40


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch):
    safe = {key: os.environ[key] for key in (
        "TMPDIR", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX", "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    ) if key in os.environ}
    safe["PATH"] = os.defpath
    monkeypatch.setattr(os, "environ", safe)


@pytest.fixture
def documents():
    started = "2026-10-13T22:00:02.000000Z"
    binding = dict(artifact_path=str(d.CAPTURE_ROOT / d.capture._artifact_id_from_timestamp(started)),
                   manifest_sha256="a" * 64, capture_id="arv2-capture-" + "b" * 24, capture_sha256="b" * 64,
                   capture_started_at=started, capture_completed_at="2026-10-13T22:00:03.000000Z",
                   total_page_count=3, total_row_count=0,
                   role_row_counts=[[role.value, 0] for role in d.quality.ROLE_ORDER],
                   capture_transport=d.capture.PRODUCTION_TRANSPORT)
    claim = dict(schema=d.SCHEMA, profile_sha256=r.PROFILE_SHA256, expected_head=HEAD,
                 caller_sha256=r.CALLER_SHA256, parent_pid=42, deadline_monotonic_ns=500_000_000_000,
                 claimed_at="2026-10-13T22:00:01.000000Z", attempt_consumed=True)
    authentication = dict(binding=copy.deepcopy(binding), authenticated=True, receipt_sha256="d" * 64,
                          receipt_byte_count=500, receipt_published=False, point_in_time_proven=False,
                          paper_look_committed=False, qc_calls=0, outcome_reads=0)
    report = dict(schema=d.SCHEMA, profile_sha256=r.PROFILE_SHA256, terminal="accepted", attempt_consumed=True,
                  capture_observation=asdict(d.CaptureObservation(True, True, "producer_returned", None)),
                  binding=binding, parent_started_at="2026-10-13T22:00:00.000000Z",
                  parent_observed_terminal_at="2026-10-13T22:00:04.000000Z", authentication=authentication,
                  provider_request_count=None, point_in_time_proven=False, paper_look_committed=False,
                  qc_calls=0, outcome_reads=0)
    return claim, report


@pytest.fixture
def stored(tmp_path, monkeypatch, documents):
    tmp_path.chmod(0o700)
    monkeypatch.setattr(r, "CONTROL", tmp_path)
    monkeypatch.setattr(r, "_source_pins", lambda *_: None)
    for name, value in zip(("claim.json", "report.json"), documents, strict=True):
        (tmp_path / name).write_bytes(d.canonical_json_bytes(value))
        (tmp_path / name).chmod(0o600)
    payload = (tmp_path / "report.json").read_bytes()
    return tmp_path, hashlib.sha256(payload).hexdigest(), len(payload)


def test_acceptance_is_finite_and_not_capture_traversal(stored, monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError("operational function reached")
    monkeypatch.setattr(d.capture, "capture_massive_history", forbidden)
    monkeypatch.setattr(d, "_authenticate", forbidden)
    monkeypatch.setattr(d, "_run_worker", forbidden)
    monkeypatch.setattr(d.capture, "_visit_authenticated_massive_capture_pages_for_bridge", forbidden)
    result = r.read_output(HEAD, stored[1], stored[2], 0)
    assert result["accepted"] and result["output_authenticated"]
    assert result["source_row_count"] == 0 and result["page_count"] == 3
    assert result["provider_request_count"] is None
    assert result["first_event_date"] == result["last_event_date"] == "2026-10-12"
    assert not {"binding", "artifact_path", "capture_id"} & result.keys()
    assert sorted(p.name for p in stored[0].iterdir()) == ["claim.json", "report.json"]


def test_actual_exit_nonzero_never_accepts_apparently_accepted_report(stored):
    result = r.read_output(HEAD, stored[1], stored[2], 2)
    assert result["output_authenticated"] and not result["accepted"]
    assert result["terminal"] == "accepted" and result["actual_parent_exit"] == 2
    assert "capture_sha256" not in result


@pytest.mark.parametrize("code", ["credential", "unsafe_configuration", "network_request", "http_status",
                                  "response_schema", "persistence_publication", "unknown"])
def test_finite_producer_failure_retained_but_not_accepted(documents, code):
    claim, report = documents
    report.update(terminal="producer_raised", binding=None, authentication=None,
                  capture_observation=asdict(d.CaptureObservation(True, False, "producer_raised", code)))
    result = r._validate(claim, report, HEAD, 2)
    assert result["failure_code"] == code and not result["accepted"]
    with pytest.raises(ValueError):
        r._validate(claim, report, HEAD, 0)


@pytest.mark.parametrize("terminal", ["worker_nonzero", "worker_channel_refused", "worker_timeout", "control_refused"])
def test_pre_observation_failures_have_unknown_evidence(documents, terminal):
    claim, report = documents
    report.update(terminal=terminal, binding=None, authentication=None, capture_observation=None)
    result = r._validate(claim, report, HEAD, 2)
    assert result["failure_code"] is None and not result["accepted"]


@pytest.mark.parametrize("location,key,bad", [
    ("claim", "schema", "other"), ("claim", "profile_sha256", "e" * 64),
    ("claim", "expected_head", "e" * 40), ("claim", "caller_sha256", "e" * 64),
    ("claim", "attempt_consumed", 1), ("claim", "parent_pid", True),
    ("claim", "parent_pid", 0), ("claim", "deadline_monotonic_ns", False),
    ("claim", "claimed_at", "2026-10-13T21:59:59.000000Z"),
    ("report", "schema", "other"), ("report", "profile_sha256", "e" * 64),
    ("report", "attempt_consumed", False), ("report", "provider_request_count", 0),
    ("report", "point_in_time_proven", 0), ("report", "paper_look_committed", True),
    ("report", "qc_calls", False), ("report", "outcome_reads", 1),
    ("report", "terminal", "SECRET-EXAMPLE-ONLY"), ("report", "terminal", "claim_ambiguous"),
    ("report", "parent_observed_terminal_at", "2026-10-13T22:00:00.000000Z"),
    ("report", "binding", None), ("report", "authentication", None),
    ("report", "capture_observation", None),
    ("binding", "total_page_count", True), ("binding", "total_row_count", False),
    ("binding", "capture_started_at", "2026-10-13T22:00:00.000000Z"),
    ("binding", "capture_completed_at", "2026-10-13T22:00:05.000000Z"),
    ("auth", "authenticated", 1), ("auth", "receipt_published", True),
    ("auth", "receipt_byte_count", True), ("auth", "qc_calls", False),
    ("auth", "receipt_sha256", "bad"),
    ("observation", "failure_code", "SECRET-EXAMPLE-ONLY"),
    ("observation", "capture_invoked", 1), ("observation", "provider_request_count", 0),
])
def test_single_corruptions_refuse(documents, location, key, bad):
    claim, report = documents
    target = {"claim": claim, "report": report, "binding": report["binding"],
              "auth": report["authentication"], "observation": report["capture_observation"]}[location]
    target[key] = bad
    with pytest.raises(ValueError):
        r._validate(claim, report, HEAD, 0)


@pytest.mark.parametrize("location", ["claim", "report", "binding", "auth", "observation"])
@pytest.mark.parametrize("operation", ["missing", "extra"])
def test_exact_keys(documents, location, operation):
    claim, report = documents
    target = {"claim": claim, "report": report, "binding": report["binding"],
              "auth": report["authentication"], "observation": report["capture_observation"]}[location]
    if operation == "missing":
        target.pop(next(iter(target)))
    else:
        target["unknown"] = "SECRET-EXAMPLE-ONLY"
    with pytest.raises(ValueError):
        r._validate(claim, report, HEAD, 0)


@pytest.mark.parametrize("head,exit_code", [("bad", 0), (HEAD, True), (HEAD, None), (HEAD, 1), (HEAD, -9)])
def test_external_context_invalid(documents, head, exit_code):
    with pytest.raises(ValueError):
        r._validate(*documents, head, exit_code)


@pytest.mark.parametrize("field", ["hash", "size"])
def test_external_pin_precedes_any_parse(stored, monkeypatch, field):
    calls = []
    monkeypatch.setattr(d, "_decode", lambda *_: calls.append(True))
    with pytest.raises(ValueError):
        r.read_output(HEAD, "f" * 64 if field == "hash" else stored[1],
                      stored[2] + 1 if field == "size" else stored[2], 0)
    assert calls == []


@pytest.mark.parametrize("name", ["claim.json", "report.json"])
@pytest.mark.parametrize("corruption", ["symlink", "hardlink", "mode", "oversize", "noncanonical", "missing"])
def test_private_leaf_refusals(stored, name, corruption):
    path = stored[0] / name
    if corruption in ("symlink", "hardlink"):
        path.rename(stored[0] / "held")
        if corruption == "symlink":
            path.symlink_to("held")
        else:
            os.link(stored[0] / "held", path)
    elif corruption == "mode":
        path.chmod(0o644)
    elif corruption == "oversize":
        path.write_bytes(b" " * (d.MAX_CHANNEL + 1))
    elif corruption == "noncanonical":
        path.write_bytes(b" {}\n")
    else:
        path.unlink()
    payload = (stored[0] / "report.json").read_bytes() if name != "report.json" or corruption != "missing" else b"x"
    with pytest.raises((ValueError, OSError)):
        r.read_output(HEAD, hashlib.sha256(payload).hexdigest(), len(payload), 0)


@pytest.mark.parametrize("name", ["report.json", "claim.json"])
def test_changed_leaf_after_validation_refuses(stored, monkeypatch, name):
    original = r._validate
    def change(*args):
        result = original(*args)
        path = stored[0] / name
        path.write_bytes(path.read_bytes() + b"\n")
        return result
    monkeypatch.setattr(r, "_validate", change)
    with pytest.raises(ValueError):
        r.read_output(HEAD, stored[1], stored[2], 0)


def test_source_pin_mismatch_precedes_output_open(monkeypatch):
    monkeypatch.setattr(d, "PROFILE_SHA256", "f" * 64)
    calls = []
    monkeypatch.setattr(d.capture, "_open_directory_path", lambda *a, **k: calls.append(True))
    with pytest.raises(ValueError):
        r.read_output(HEAD, "a" * 64, 1, 0)
    assert calls == []


def test_cli_never_prints_raw_failure(monkeypatch, capsys):
    def fail(*_):
        raise RuntimeError("SECRET-EXAMPLE-ONLY")
    monkeypatch.setattr(r, "read_output", fail)
    assert r.main(["--expected-head", HEAD, "--report-sha256", "a" * 64,
                   "--report-bytes", "1", "--actual-parent-exit", "2"]) == 2
    output = capsys.readouterr()
    assert "SECRET" not in output.out + output.err
    assert '"output_authenticated":false' in output.out


def test_reader_has_no_dispatch_or_creation_call_sites():
    tree = ast.parse(Path(r.__file__).read_text())
    calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not calls & {"capture_massive_history", "_authenticate", "_run_worker", "_claim", "Popen", "mkdir", "write_bytes"}


def test_exact_clean_host_head_preflight_is_used(monkeypatch):
    calls = []
    monkeypatch.setattr(d, "_preflight", lambda *args: calls.append(args))
    r._source_pins(HEAD, 999.0)
    assert calls == [(HEAD, r.CALLER_SHA256, 999.0)]


def test_reader_alarm_covers_entire_read(monkeypatch):
    events = []
    monkeypatch.setattr(r.time, "monotonic", lambda: 100.0)
    @contextmanager
    def alarm(deadline):
        assert deadline == 130.0
        events.append("entered")
        yield
        events.append("left")
    monkeypatch.setattr(d, "_alarm", alarm)
    def read(*args):
        assert events == ["entered"] and args[-1] == 130.0
        return {"accepted": True}
    monkeypatch.setattr(r, "_read_output", read)
    assert r.read_output(HEAD, "a" * 64, 1, 0) == {"accepted": True}
    assert events == ["entered", "left"]


def test_late_return_is_not_accepted(monkeypatch):
    monkeypatch.setattr(r, "_read_output", lambda *_: {"accepted": True})
    remaining = d._remaining
    calls = []
    def late(deadline, reserve=0.0):
        calls.append(True)
        if len(calls) > 1:
            raise d.Deadline()
        return remaining(deadline, reserve)
    monkeypatch.setattr(d, "_remaining", late)
    with pytest.raises(d.Deadline):
        r.read_output(HEAD, "a" * 64, 1, 0)


@pytest.mark.parametrize("terminal", ["producer_raised", "invalid_producer_return", "authentication_refused",
                                    "worker_nonzero", "worker_channel_refused", "control_refused"])
def test_incompatible_authenticated_failure_states_refuse(documents, terminal):
    claim, report = documents
    report["terminal"] = terminal
    with pytest.raises(ValueError):
        r._validate(claim, report, HEAD, 2)


def test_timeout_after_authentication_is_retained_but_unaccepted(documents):
    claim, report = documents
    report["terminal"] = "worker_timeout"
    result = r._validate(claim, report, HEAD, 2)
    assert result["output_authenticated"] and not result["accepted"]
    assert "capture_sha256" not in result


@pytest.mark.parametrize("exit_code", [0, 2])
def test_cli_success_code_requires_both_accepted_and_actual_exit(stored, capsys, exit_code):
    assert r.main(["--expected-head", HEAD, "--report-sha256", stored[1],
                   "--report-bytes", str(stored[2]), "--actual-parent-exit", str(exit_code)]) == exit_code
    summary = d._decode(capsys.readouterr().out.encode())
    assert summary["accepted"] is (exit_code == 0)
    assert summary["actual_parent_exit"] == exit_code
