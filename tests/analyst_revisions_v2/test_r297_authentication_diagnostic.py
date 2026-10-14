"""Synthetic-only retained-byte diagnostic protocol checks."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from scripts import diagnose_arv2_r297_authentication as d

HEAD, SHA = "a" * 40, "b" * 64


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(d.subprocess, "run", lambda *_a, **_k: pytest.fail("real commands forbidden"))
    monkeypatch.setattr(d.delta, "authenticate_capture", lambda *_a, **_k: pytest.fail("private reads forbidden"))
    monkeypatch.setattr(d.original.credentials, "load_key", lambda *_a, **_k: pytest.fail("credentials forbidden"))
    for name in ("run", "read_output", "_run", "_worker", "_run_worker", "_capture_once", "_claim", "_authenticate"):
        monkeypatch.setattr(d.original, name, lambda *_a, **_k: pytest.fail("spent operation forbidden"))


@pytest.fixture
def control(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    value = tmp_path / "D3-SYNTHETIC"
    monkeypatch.setattr(d, "CONTROL", value)
    monkeypatch.setattr(d, "_preflight", lambda *_a: None)
    monkeypatch.setattr(d.capture, "_require_operational_artifact_scope", lambda *_a: None)
    return value


class Opaque:
    def __repr__(self):
        raise AssertionError("opaque rendering forbidden")
    def __str__(self):
        raise AssertionError("opaque rendering forbidden")


def test_claim_precedes_exact_single_offline_call_and_return_is_not_acceptance(control, monkeypatch, capsys):
    calls = []
    def authenticate(path, **kwargs):
        assert (control / "claim.json").is_file()
        assert path == d.CAPTURE_PATH
        assert kwargs == {"expected_manifest_sha256": d.MANIFEST_SHA256,
            "expected_manifest_byte_count": 2628}
        calls.append(True)
        return Opaque()
    monkeypatch.setattr(d.delta, "authenticate_capture", authenticate)
    assert d.run(HEAD, SHA) == 0
    envelope = json.loads(capsys.readouterr().out)
    report = envelope["report"]
    assert report["terminal"] == "retained_authentication_returned" and calls == [True]
    assert report["diagnostic_only"] is True
    for field in ("original_capture_accepted", "changes_original_exit", "provider_contact_authorized",
            "point_in_time_proven", "backtest_ready", "paper_or_live_ready"):
        assert report[field] is False
    assert report["provider_request_count"] is None
    raw = (control / "report.json").read_bytes()
    assert envelope["report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert envelope["report_bytes"] == len(raw)
    assert set(p.name for p in control.iterdir()) == {"claim.json", "report.json"}
    assert "assistant.dispatch_fence" not in sys.modules


@pytest.mark.parametrize("code", sorted(d.KNOWN_CODES))
def test_each_reviewed_literal_is_finite(code):
    assert d._failure(d.delta.RatingsDeltaError(code)) == ("ratings_delta_error", code)


@pytest.mark.parametrize("args", [("SECRET-NOT-A-LITERAL",), (Opaque(),), ("private_leaf", Opaque()), ()])
def test_unrecognized_error_arguments_are_not_rendered(args):
    assert d._failure(d.delta.RatingsDeltaError(*args)) == ("ratings_delta_error", "unknown")


def test_hostile_exception_metaclass_and_rendering_are_not_called():
    class HostileMeta(type):
        def __hash__(cls):
            raise AssertionError("hostile class hash")
        def __eq__(cls, other):
            raise AssertionError("hostile class equality")
    class Hostile(Exception, metaclass=HostileMeta):
        def __str__(self):
            raise AssertionError("rendering")
        def __repr__(self):
            raise AssertionError("rendering")
    assert d._failure(Hostile(Opaque())) == ("unknown_exception", "unknown")


def test_ratings_error_subclass_never_reads_arguments():
    class Derived(d.delta.RatingsDeltaError):
        def __getattribute__(self, name):
            if name == "args":
                raise AssertionError("subclass argument hook")
            return super().__getattribute__(name)
    assert d._failure(Derived("private_leaf")) == ("unknown_exception", "unknown")


@pytest.mark.parametrize("error,label", [(ValueError, "value_error"), (TypeError, "type_error"),
    (FileNotFoundError, "file_missing"), (PermissionError, "permission_error"),
    (d.delta._input.AcceptedRiskInputError, "accepted_risk_input_error"),
    (d.delta.CanonicalEvidenceError, "canonical_evidence_error"),
    (KeyboardInterrupt, "cancelled"), (SystemExit, "cancelled")])
def test_finite_exact_error_types(error, label):
    assert d._failure(error(Opaque())) == (label, "unknown")


def test_refusal_retained_as_failure_evidence(control, monkeypatch, capsys):
    def refuse(*_a, **_k):
        raise d.delta.RatingsDeltaError("duplicate_rating_provider_id")
    monkeypatch.setattr(d.delta, "authenticate_capture", refuse)
    assert d.run(HEAD, SHA) == 2
    report = json.loads(capsys.readouterr().out)["report"]
    assert report["refusal_code"] == "duplicate_rating_provider_id"
    assert report["stage"] == "source_authentication"
    assert report["original_capture_accepted"] is False


def test_collision_never_reads_private_source(control, monkeypatch, capsys):
    control.mkdir(mode=0o700)
    assert d.run(HEAD, SHA) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["stage"] == "claim" and report["attempt_consumed"] is None


def test_completed_diagnostic_cannot_be_repeated(control, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(d.delta, "authenticate_capture", lambda *_a, **_k: calls.append(True))
    assert d.run(HEAD, SHA) == 0
    capsys.readouterr()
    assert d.run(HEAD, SHA) == 2
    assert calls == [True]
    assert json.loads(capsys.readouterr().out)["stage"] == "claim"


def test_preflight_refusal_never_claims(control, monkeypatch, capsys):
    def refuse(*_a):
        raise d.DiagnosticRefusal("diagnostic_refused")
    monkeypatch.setattr(d, "_preflight", refuse)
    assert d.run(HEAD, SHA) == 2
    assert not control.exists()
    assert json.loads(capsys.readouterr().out)["attempt_consumed"] is False


def test_held_claim_change_prevents_report(control, monkeypatch, capsys):
    def change(*_a, **_k):
        (control / "claim.json").chmod(0o644)
        return Opaque()
    monkeypatch.setattr(d.delta, "authenticate_capture", change)
    assert d.run(HEAD, SHA) == 2
    assert not (control / "report.json").exists()
    assert json.loads(capsys.readouterr().out)["terminal"] == "diagnostic_publication_ambiguous"


def test_alarm_covers_private_authentication(control, monkeypatch, capsys):
    monkeypatch.setattr(d, "DEADLINE_SECONDS", 0.03)
    monkeypatch.setattr(d.delta, "authenticate_capture", lambda *_a, **_k: time.sleep(1))
    started = time.monotonic()
    assert d.run(HEAD, SHA) == 2
    assert time.monotonic() - started < 0.5
    assert "original_capture_accepted\":false" in capsys.readouterr().out


@pytest.mark.parametrize("mutation", ["none", "root", "branch", "head", "dirty", "stderr", "returncode", "pin", "caller"])
def test_exact_preflight_bindings(monkeypatch, mutation):
    monkeypatch.setattr(d, "SOURCE_PINS", {"synthetic.py": SHA})
    results = [str(d.ROOT), d.BRANCH, HEAD, ""]
    changes = {"root": 0, "branch": 1, "head": 2, "dirty": 3}
    if mutation in changes:
        results[changes[mutation]] = "wrong"
    def command(*_a, **_k):
        return SimpleNamespace(stdout=(results.pop(0) + "\n").encode(),
            stderr=b"bad" if mutation == "stderr" else b"", returncode=1 if mutation == "returncode" else 0)
    monkeypatch.setattr(d.subprocess, "run", command)
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: "c" * 64
        if mutation == "pin" and path != d.SOURCE or mutation == "caller" and path == d.SOURCE else SHA)
    if mutation == "none":
        d._preflight(HEAD, SHA, time.monotonic() + 10)
    else:
        with pytest.raises(ValueError):
            d._preflight(HEAD, SHA, time.monotonic() + 10)


@pytest.mark.parametrize("field,value", [("platform", "win32"), ("executable", "/wrong/python"), ("version_info", (3, 12))])
def test_host_refuses_before_commands(monkeypatch, field, value):
    monkeypatch.setattr(sys, field, value)
    with pytest.raises(ValueError):
        d._preflight(HEAD, SHA, time.monotonic() + 10)


def test_literal_inventory_covers_frozen_delta_refusal_sites():
    tree = ast.parse(Path(d.delta.__file__).read_text())
    literals = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            index = 0 if node.func.id == "_refuse" else 3 if node.func.id == "_integer" else None
            if index is not None and len(node.args) > index:
                value = node.args[index]
                if isinstance(value, ast.Constant) and type(value.value) is str:
                    literals.add(value.value)
    assert literals <= d.KNOWN_CODES
