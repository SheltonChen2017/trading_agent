"""Sanitized failure fixtures only; no real inputs, source actor or output roots."""
import base64
import errno
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
pytest.importorskip("fcntl", reason="macOS/POSIX custody support")

SOURCE = Path(__file__).resolve().parents[1] / "research/insider_buying_sec_2006q1_parent_projection_v1.py"
SPEC = importlib.util.spec_from_file_location("projection_diagnostics_qa180", SOURCE)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


@pytest.mark.parametrize("stage", ["parent_original_sources", "parent_output_reservation"])
def test_parent_cli_preserves_fixed_phase_class_errno_without_arbitrary_exception_fields(monkeypatch, capsys, stage):
    monkeypatch.setattr(module, "_fixed_source_identity", lambda _: ({"source_sha256": {}}, {}))
    secret = "INVENTED PRIVATE TEXT /not/an/actual/source"
    error = PermissionError(errno.EACCES, secret, secret)
    def refused(*args, **kwargs): raise error
    monkeypatch.setattr(module.capture, "_verify_original_committed_sources", refused if stage == "parent_original_sources" else lambda *_: None)
    monkeypatch.setattr(module, "_output_directory", refused if stage == "parent_output_reservation" else lambda *_args, **_kwargs: pytest.fail("must refuse before output"))
    assert module.main(["--audit-id", "ib-2006q1-parent-projection-invented", "--expected-head", "a" * 40,
        "--expected-capture-report-sha256", "b" * 64]) == 2
    raw = capsys.readouterr().out
    assert secret not in raw
    assert json.loads(raw) == {"disposition": "offline_parent_projection_refused_outputs_preserved",
        "failure_phase": stage, "failure_class": "OSError", "os_errno": errno.EACCES}


def test_child_bootstrap_failure_prints_only_strict_sanitized_control_and_exit2():
    helper_path = "research/insider_buying_affected_quarter_isolation.py"
    fixture_code = b'''import errno, json
def _worker(audit_id, **kwargs):
    raise PermissionError(errno.EPERM, "INVENTED PRIVATE SECRET", "/invented/private/source")
def _raw(value): return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
'''
    sources = {helper_path: module.isolation._read_source(helper_path), "research/__init__.py": b"", module.SELF_PATH: fixture_code}
    envelope = {"sources": [{"path": name, "sha256": module._sha(raw), "source_b64": base64.b64encode(raw).decode()}
        for name, raw in sorted(sources.items())], "parent_context": {"identity": {"source_sha256": {
            name: module._sha(raw) for name, raw in sources.items()}}, "frozen_sources": {}},
        "audit_id": "invented-child-failure", "expected_head": "a" * 40, "report_sha256": "b" * 64}
    module.capture.bootstrap.custody._effective_denial(require_fork=False)
    child = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", module.SOURCE_ONLY_BOOTSTRAP],
        input=module._raw(envelope), capture_output=True, cwd=module.capture.bootstrap.custody.LANE_ROOT, timeout=30)
    assert child.returncode == 2
    assert child.stderr == b""
    assert b"PRIVATE SECRET" not in child.stdout and b"/invented/private/source" not in child.stdout
    assert json.loads(child.stdout) == {"disposition": "offline_parent_projection_refused_outputs_preserved",
        "failure_phase": "worker_execution", "failure_class": "OSError", "os_errno": errno.EPERM}


def test_valid_failed_child_is_retained_as_failure_never_laundered_as_success(tmp_path, monkeypatch, capsys):
    identity = {"source_sha256": {}}
    observed = []
    output = SimpleNamespace(path=tmp_path, close=lambda: None,
        publish=lambda name, raw, **kwargs: observed.append((name, json.loads(raw))) or "c" * 64)
    diagnostic = {"disposition": "offline_parent_projection_refused_outputs_preserved",
        "failure_phase": "worker_preparation", "failure_class": "OSError", "os_errno": errno.EACCES}
    monkeypatch.setattr(module, "_fixed_source_identity", lambda _: (identity, {}))
    monkeypatch.setattr(module.capture, "_verify_original_committed_sources", lambda *_: None)
    monkeypatch.setattr(module, "_output_directory", lambda *_args, **_kwargs: output)
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs:
        SimpleNamespace(returncode=2, stderr=b"", stdout=module._raw(diagnostic) + b"\n"))
    assert module.main(["--audit-id", "ib-2006q1-parent-projection-invented", "--expected-head", "a" * 40,
        "--expected-capture-report-sha256", "b" * 64]) == 2
    assert json.loads(capsys.readouterr().out) == diagnostic
    assert [name for name, _ in observed] == ["reservation.json", "worker-failure.json"]
    assert observed[-1][1]["diagnostic"] == diagnostic
    assert observed[-1][1]["authority"] == module._authority()
    assert not any(name == "complete.json" for name, _ in observed)


@pytest.mark.parametrize("change", ["extra_key", "private_phase", "private_class", "bool_errno", "unknown_errno", "positive_disposition"])
def test_rehashed_child_diagnostic_cannot_supply_arbitrary_fields_or_success(change):
    body = {"disposition": "offline_parent_projection_refused_outputs_preserved", "failure_phase": "worker_preparation",
        "failure_class": "OSError", "os_errno": errno.EPERM}
    if change == "extra_key": body["secret"] = "INVENTED SECRET"
    elif change == "private_phase": body["failure_phase"] = "INVENTED SECRET"
    elif change == "private_class": body["failure_class"] = "INVENTED SECRET"
    elif change == "bool_errno": body["os_errno"] = True
    elif change == "unknown_errno": body["os_errno"] = 999999
    else: body["disposition"] = "completed"
    with pytest.raises(module.EarlyParentProjectionError): module._strict_failure(body)


def test_phase_wrapper_keeps_original_exception_identity_and_does_not_print(monkeypatch, capsys):
    error = ValueError("INVENTED PRIVATE SECRET")
    def refused(): raise error
    with pytest.raises(ValueError) as observed: module._at_phase("worker_capture", refused)
    assert observed.value is error
    assert module._failure_diagnostic(error)["failure_phase"] == "worker_capture"
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("mutation", ["extra_field", "replace", "private_class"])
def test_reported_exception_diagnostic_is_revalidated_at_every_serialization(mutation):
    error = module.ReportedProjectionWorkerError({"disposition": "offline_parent_projection_refused_outputs_preserved",
        "failure_phase": "worker_preparation", "failure_class": "OSError", "os_errno": errno.EPERM})
    if mutation == "extra_field": error.diagnostic["private"] = "INVENTED SECRET"
    elif mutation == "replace": error.diagnostic = "INVENTED SECRET"
    else: error.diagnostic["failure_class"] = "INVENTED SECRET"
    diagnostic = module._failure_diagnostic(error)
    assert diagnostic == {"disposition": "offline_parent_projection_refused_outputs_preserved",
        "failure_phase": "parent_worker_result", "failure_class": "EarlyParentProjectionError", "os_errno": None}
    assert "INVENTED SECRET" not in module._raw(diagnostic).decode()
