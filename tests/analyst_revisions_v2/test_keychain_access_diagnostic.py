"""Synthetic native-command outcomes only; no real Keychain/provider access."""
from __future__ import annotations

import ast
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from scripts import diagnose_arv2_keychain_access as d

HEAD = "a" * 40
SHA = "b" * 64
SECRET = b"SYNTHETIC-NEVER-A-REAL-KEY"


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch):
    safe = {key: os.environ[key] for key in (
        "TMPDIR", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX", "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    ) if key in os.environ}
    safe["PATH"] = os.defpath
    monkeypatch.setattr(os, "environ", safe)
    monkeypatch.setattr(d.subprocess, "run", lambda *_a, **_k: pytest.fail("no real subprocess"))
    monkeypatch.setattr(d.keymap, "load_key", lambda *_a, **_k: pytest.fail("old loader forbidden"))


@pytest.fixture
def control(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    target = tmp_path / "R296B-SYNTHETIC"
    monkeypatch.setattr(d, "CONTROL", target)
    monkeypatch.setattr(d.capture, "_require_operational_artifact_scope", lambda _: None)
    monkeypatch.setattr(d, "_preflight", lambda *_: None)
    return target


def install(monkeypatch, outcomes=None, control=None):
    calls = []
    def run(command, **kwargs):
        provider = command[command.index("-a") + 1]
        calls.append((provider, command, kwargs))
        if control:
            assert (control / "claim.json").is_file()
            assert (control / f"read-{len(calls)}-started.json").is_file()
        outcome = (outcomes or {}).get(provider, (0, SECRET + b"\n"))
        if isinstance(outcome, BaseException):
            raise outcome
        return SimpleNamespace(returncode=outcome[0], stdout=outcome[1])
    monkeypatch.setattr(d.subprocess, "run", run)
    return calls


def execute(monkeypatch, control, outcomes=None):
    calls = install(monkeypatch, outcomes, control)
    return d._run(HEAD, SHA, time.monotonic() + 200), calls


def report(control):
    return d.helpers._decode((control / "report.json").read_bytes())


def read(control, actual_exit=0, **changes):
    raw = (control / "report.json").read_bytes()
    args = dict(expected_head=HEAD, caller_sha256=SHA, report_sha256=hashlib.sha256(raw).hexdigest(),
        report_bytes=len(raw), actual_exit=actual_exit)
    args.update(changes)
    return d.read_output(**args)


def test_exact_three_commands_claim_before_credentials(control, monkeypatch, capsys):
    code, calls = execute(monkeypatch, control)
    assert code == 0 and [row[0] for row in calls] == ["fmp", "massive", "eodhd"]
    for provider, command, kwargs in calls:
        service, account = d.keymap.SERVICES[provider]
        assert command == ["/usr/bin/security", "find-generic-password", "-s", service,
            "-a", account, "-w", "/Users/sheltonchen/Library/Keychains/login.keychain-db"]
        assert kwargs == {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL, "timeout": 60, "check": False}
    value = report(control)
    assert value["terminal"] == "all_credentials_valid_shape" and value["read_attempt_count"] == 3
    assert value["provider_calls_dispatched"] == 0 and value["provider_request_count"] is None
    assert value["capture_accepted"] is value["backtest_ready"] is False
    out = capsys.readouterr()
    assert out.err == "" and out.out.endswith("\n\n") and SECRET.decode() not in out.out
    assert sorted(path.name for path in control.iterdir()) == ["claim.json", "read-1-started.json",
        "read-2-started.json", "read-3-started.json", "report.json"]
    assert all(SECRET not in path.read_bytes() for path in control.iterdir())


@pytest.mark.parametrize("code", [-255, -9, 1, 36, 44, 128, 255])
def test_actual_nonzero_code_retained_no_reason_invented(control, monkeypatch, code):
    result, calls = execute(monkeypatch, control, {"fmp": (code, SECRET)})
    assert result == 2 and len(calls) == 3
    row = report(control)["observations"][0]
    assert row == {"provider": "fmp", "read_intent_recorded": True, "terminal": "command_failed",
        "returncode": code, "shape_code": None}
    assert read(control, actual_exit=2)["all_credentials_valid_shape"] is False


@pytest.mark.parametrize("code", [True, None, "0", 0.0, -256, 256])
def test_malformed_returncode_never_fabricated(control, monkeypatch, code):
    result, _calls = execute(monkeypatch, control, {"fmp": (code, SECRET)})
    assert result == 2
    row = report(control)["observations"][0]
    assert row["terminal"] == "command_unavailable" and row["returncode"] is None


@pytest.mark.parametrize("value,shape", [(SECRET, "missing_final_lf"), (b"", "missing_final_lf"),
    (b"1234567\n", "short_or_long"), (b"a" * 4097 + b"\n", "short_or_long"),
    (b"1234567 \n", "invalid_ascii"), (b"1234567\0\n", "invalid_ascii"),
    (b"1234567\x80\n", "invalid_ascii"), (SECRET + b"\r\n", "invalid_ascii"),
    (SECRET + b"\n\n", "invalid_ascii"), (None, "invalid_output_type"),
    ("not-bytes", "invalid_output_type")])
def test_finite_shape_categories_no_length_or_values(control, monkeypatch, value, shape):
    code, _calls = execute(monkeypatch, control, {"massive": (0, value)})
    assert code == 2
    row = report(control)["observations"][1]
    assert row["terminal"] == "command_completed_invalid_shape" and row["shape_code"] == shape
    assert row["returncode"] == 0 and "length" not in row


@pytest.mark.parametrize("length", [8, 4096])
def test_accepted_shape_boundaries(length):
    assert d._shape(b"a" * length + b"\n") == "valid"


def test_timeout_is_separate_from_nonzero_without_leaked_output(control, monkeypatch, capsys):
    exception = subprocess.TimeoutExpired(["EXAMPLE-SECRET"], 60, output=SECRET, stderr=SECRET)
    code, calls = execute(monkeypatch, control, {"fmp": exception})
    assert code == 2 and len(calls) == 3
    row = report(control)["observations"][0]
    assert row["terminal"] == "timed_out" and row["returncode"] is row["shape_code"] is None
    assert SECRET.decode() not in capsys.readouterr().out


@pytest.mark.parametrize("exception", [OSError("EXAMPLE-SECRET"), RuntimeError("EXAMPLE-SECRET")])
def test_unavailable_command_finite_without_fallback(control, monkeypatch, exception, capsys):
    code, calls = execute(monkeypatch, control, {"fmp": exception})
    assert code == 2 and len(calls) == 3
    assert report(control)["observations"][0]["terminal"] == "command_unavailable"
    assert "EXAMPLE-SECRET" not in capsys.readouterr().out


@pytest.mark.parametrize("exception,terminal", [(KeyboardInterrupt(), "cancelled"),
    (SystemExit(2), "cancelled"), (d.helpers.Deadline(), "deadline_timeout")])
def test_cancellation_deadline_stop_remaining_reads(control, monkeypatch, exception, terminal):
    code, calls = execute(monkeypatch, control, {"massive": exception})
    assert code == 2 and len(calls) == 2
    value = report(control)
    assert value["terminal"] == terminal and value["observations"][2]["terminal"] == "not_attempted"
    assert read(control, actual_exit=2)["all_credentials_valid_shape"] is False


def test_request_timeout_never_exceeds_remaining_budget(monkeypatch):
    calls = install(monkeypatch)
    assert d._observe_key("fmp", time.monotonic() + 2)[0] == "command_completed_valid_shape"
    assert 0 < calls[0][2]["timeout"] <= 2


def test_marker_ambiguity_stops_before_read(control, monkeypatch):
    original = d._write_held
    def write(directory, name, value):
        result = original(directory, name, value)
        if name == "read-2-started.json":
            os.close(result[0])
            raise OSError("EXAMPLE-SECRET")
        return result
    monkeypatch.setattr(d, "_write_held", write)
    code, calls = execute(monkeypatch, control)
    assert code == 2 and len(calls) == 1
    value = report(control)
    assert value["terminal"] == "read_intent_ambiguous" and value["read_attempt_count"] == 1


def test_duplicate_claim_no_read(control, monkeypatch, capsys):
    assert execute(monkeypatch, control)[0] == 0
    capsys.readouterr()
    code, calls = execute(monkeypatch, control)
    assert code == 2 and not calls
    assert "claim_ambiguous" in capsys.readouterr().out


def test_preflight_refusal_no_claim_or_read(control, monkeypatch, capsys):
    monkeypatch.setattr(d, "_preflight", lambda *_: (_ for _ in ()).throw(d.Refusal("control_refused")))
    code, calls = execute(monkeypatch, control)
    assert code == 2 and not calls and not control.exists()
    assert "preclaim_refusal" in capsys.readouterr().out


def test_late_publication_failure_not_positive_exit(control, monkeypatch, capsys):
    original = d._check_held
    def check(directory, name, fd, identity):
        if name == "report.json":
            raise d.Refusal("control_refused")
        return original(directory, name, fd, identity)
    monkeypatch.setattr(d, "_check_held", check)
    code, _ = execute(monkeypatch, control)
    assert code == 2 and report(control)["terminal"] == "all_credentials_valid_shape"
    assert "publication_ambiguous" in capsys.readouterr().out


def test_reader_only_claim_report_no_key(control, monkeypatch):
    assert execute(monkeypatch, control)[0] == 0
    monkeypatch.setattr(d.subprocess, "run", lambda *_a, **_k: pytest.fail("no reader command"))
    value = read(control)
    assert value["output_authenticated"] is value["all_credentials_valid_shape"] is True
    assert value["capture_accepted"] is value["backtest_ready"] is False


def test_actual_exit_overrides_positive_report(control, monkeypatch):
    assert execute(monkeypatch, control)[0] == 0
    assert read(control, actual_exit=2)["all_credentials_valid_shape"] is False


@pytest.mark.parametrize("change", [{"report_bytes": 1}, {"report_sha256": "c" * 64},
    {"actual_exit": None}, {"actual_exit": True}, {"actual_exit": -9},
    {"expected_head": "c" * 40}, {"caller_sha256": "c" * 64}])
def test_reader_external_bindings(control, monkeypatch, change):
    assert execute(monkeypatch, control)[0] == 0
    with pytest.raises((d.Refusal, d.helpers.Refusal)):
        read(control, **change)


@pytest.mark.parametrize("field,value", [("returncode", True), ("returncode", 1),
    ("shape_code", "invalid_ascii"), ("read_intent_recorded", False),
    ("provider", "sharadar"), ("terminal", "command_failed")])
def test_strict_row_schema(control, monkeypatch, field, value):
    assert execute(monkeypatch, control)[0] == 0
    claim = d.helpers._decode((control / "claim.json").read_bytes())
    value_map = report(control)
    value_map["observations"][0][field] = value
    with pytest.raises((d.Refusal, d.helpers.Refusal)):
        d._validate(claim, value_map, HEAD, SHA, 0)


@pytest.mark.parametrize("field,value", [("read_attempt_count", True), ("read_attempt_count", 2),
    ("provider_calls_dispatched", True), ("provider_request_count", 0), ("capture_accepted", True),
    ("backtest_ready", True), ("point_in_time_proven", True), ("paper_look_committed", True),
    ("qc_calls", 1), ("outcome_reads", 1), ("observations", []),
    ("profile_sha256", "c" * 64), ("parent_observed_terminal_at", "2020-01-01T00:00:00.000000Z")])
def test_strict_report_schema(control, monkeypatch, field, value):
    assert execute(monkeypatch, control)[0] == 0
    claim = d.helpers._decode((control / "claim.json").read_bytes())
    value_map = report(control)
    value_map[field] = value
    with pytest.raises((d.Refusal, d.helpers.Refusal)):
        d._validate(claim, value_map, HEAD, SHA, 0)


def configure_preflight(monkeypatch):
    answers = {("rev-parse", "--show-toplevel"): str(d.ROOT),
        ("branch", "--show-current"): d.BRANCH, ("rev-parse", "HEAD"): HEAD,
        ("status", "--porcelain"): ""}
    monkeypatch.setattr(d.subprocess, "run", lambda command, **kwargs: SimpleNamespace(
        returncode=0, stderr=b"", stdout=(answers[tuple(command[1:])] + "\n").encode()))
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: SHA if path == d.SOURCE
        else d.SOURCE_PINS[str(path.relative_to(d.ROOT))])
    return answers


def test_preflight_exact_clean_host_and_pins(monkeypatch):
    configure_preflight(monkeypatch)
    d._preflight(HEAD, SHA, time.monotonic() + 200)


@pytest.mark.parametrize("command", [("rev-parse", "--show-toplevel"), ("branch", "--show-current"),
    ("rev-parse", "HEAD"), ("status", "--porcelain")])
def test_root_branch_head_dirty_refuse(monkeypatch, command):
    answers = configure_preflight(monkeypatch)
    answers[command] = "wrong"
    with pytest.raises(d.Refusal):
        d._preflight(HEAD, SHA, time.monotonic() + 200)


@pytest.mark.parametrize("relative", list(d.SOURCE_PINS) + ["scripts/diagnose_arv2_keychain_access.py"])
def test_selected_pins_refuse(monkeypatch, relative):
    configure_preflight(monkeypatch)
    original = d.helpers._source_digest
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: "c" * 64 if path == d.ROOT / relative else original(path))
    with pytest.raises(d.Refusal):
        d._preflight(HEAD, SHA, time.monotonic() + 200)


@pytest.mark.parametrize("name,value", [("platform", "linux"), ("version_info", (3, 12, 0)),
    ("executable", "/other/python")])
def test_wrong_host_refuses(monkeypatch, name, value):
    with monkeypatch.context() as patch:
        patch.setattr(sys, name, value)
        with pytest.raises(d.Refusal):
            d._preflight(HEAD, SHA, time.monotonic() + 200)


def test_parent_and_reader_alarm(monkeypatch):
    bounds = []
    @contextmanager
    def alarm(deadline):
        bounds.append(deadline - time.monotonic())
        yield
    monkeypatch.setattr(d.helpers, "_alarm", alarm)
    monkeypatch.setattr(d, "_run", lambda *_: 2)
    assert d.run(HEAD, SHA) == 2
    with pytest.raises(d.Refusal):
        d.read_output(HEAD, SHA, SHA, 0, 0)
    assert 199 <= bounds[0] <= 200 and 29 <= bounds[1] <= 30


def test_no_network_module_imports_or_old_operational_calls():
    tree = ast.parse(d.SOURCE.read_text())
    imports = {alias.name.split(".")[0] for node in ast.walk(tree)
        if isinstance(node, ast.Import) for alias in node.names}
    assert not imports & {"requests", "urllib3", "socket", "http"}
    source = d.SOURCE.read_text()
    for forbidden in ("keymap.load_key(", "helpers.run(", "helpers._preflight(", "helpers._worker("):
        assert forbidden not in source
    assert "assistant.dispatch_fence" not in sys.modules
