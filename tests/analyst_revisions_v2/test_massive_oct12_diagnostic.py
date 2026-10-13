"""Synthetic R293 protocol checks; never invoke production capture or roots."""
from __future__ import annotations

import ast
from dataclasses import asdict, replace
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from scripts import run_arv2_massive_oct12_diagnostic as d


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch):
    # Never retain real credentials in FakeProcess call records or tracebacks.
    # Keep only this denied test process's already-designated support paths.
    safe = {key: os.environ[key] for key in (
        "TMPDIR", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX", "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    ) if key in os.environ}
    safe["PATH"] = os.defpath
    monkeypatch.setattr(os, "environ", safe)


@pytest.fixture
def source():
    started = "2026-10-13T21:00:00.000000Z"
    return d.capture.SpooledMassiveCapture(
        artifact_path=d.CAPTURE_ROOT / d.capture._artifact_id_from_timestamp(started),
        manifest_sha256="a" * 64, capture_id="arv2-capture-" + "b" * 24, capture_sha256="b" * 64,
        capture_started_at=started, capture_completed_at="2026-10-13T21:00:01.000000Z",
        total_page_count=3, total_row_count=0,
        role_row_counts=tuple((r, 0) for r in d.quality.ROLE_ORDER),
        capture_transport=d.capture.PRODUCTION_TRANSPORT,
    )


@pytest.fixture
def private_control(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    target = tmp_path / "R293-synthetic"
    monkeypatch.setattr(d, "CONTROL", target)
    monkeypatch.setattr(d.capture, "_require_operational_artifact_scope", lambda _: None)
    times = iter(["2026-10-13T20:59:59.000000Z", "2026-10-13T20:59:59.000000Z",
                  "2026-10-13T21:00:02.000000Z", "2026-10-13T21:00:03.000000Z"])
    monkeypatch.setattr(d, "_utc_now", lambda: next(times, "2026-10-13T21:00:03.000000Z"))
    return target


def _claim():
    return d._claim("c" * 40, "d" * 64, time.monotonic() + 60)


def _close(*fds):
    for fd in fds:
        os.close(fd)


def _returned(source):
    return {"observation": asdict(d.CaptureObservation(True, True, "producer_returned", None)),
            "terminal": "producer_returned", "binding": d._binding(source)}


def _receipt(source):
    return {
        "schema": d.quality.SCHEMA, "purpose": d.quality.PURPOSE,
        "capture_id": source.capture_id, "capture_sha256": source.capture_sha256,
        "capture_manifest_sha256": source.manifest_sha256,
        "capture_started_at": source.capture_started_at,
        "capture_completed_at": source.capture_completed_at,
        "capture_transport": source.capture_transport,
        "first_event_date": d.EVENT_DATE, "last_event_date": d.EVENT_DATE,
        "source_row_count": 0,
        "roles": [{"role": r.value, "events": []} for r in d.quality.ROLE_ORDER],
        "point_in_time_proven": False, "paper_look_committed": False,
        "qc_calls": 0, "outcome_reads": 0,
    }


def test_capture_uses_exact_fixed_callback_once(monkeypatch, source):
    calls = []
    def producer(**kwargs):
        calls.append(kwargs)
        return source
    monkeypatch.setattr(d.capture, "capture_massive_history", producer)
    actual = d._require_capture_result(d._capture_once())
    assert actual == _returned(source)
    assert calls == [{"requested_first_event_date": "2026-10-12", "requested_last_event_date": "2026-10-12",
                      "artifact_root": d.CAPTURE_ROOT, "page_limit": 1000, "build_input_pair": False}]
    assert actual["observation"]["provider_request_count"] is None


@pytest.mark.parametrize("exc, code", [
    (d.capture.MassiveCaptureError("capture publication failed"), "persistence_publication"),
    (d.capture.MassiveCaptureError("SECRET-EXAMPLE-ONLY"), "unknown"),
    (KeyboardInterrupt("SECRET-EXAMPLE-ONLY"), "unknown"),
    (SystemExit("SECRET-EXAMPLE-ONLY"), "unknown"),
])
def test_capture_preserves_only_finite_failure_once(monkeypatch, capsys, exc, code):
    calls = []
    def producer(**kwargs):
        calls.append(True)
        raise exc
    monkeypatch.setattr(d.capture, "capture_massive_history", producer)
    actual = d._require_capture_result(d._capture_once())
    assert calls == [True]
    assert actual["terminal"] == "producer_raised"
    assert actual["observation"]["failure_code"] == code
    assert "SECRET" not in d.canonical_json_bytes(actual).decode()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("opaque", [None, False, 1, "SECRET-EXAMPLE-ONLY", {"secret": "example"}])
def test_invalid_opaque_return_is_never_serialized(monkeypatch, opaque):
    monkeypatch.setattr(d.capture, "capture_massive_history", lambda **_: opaque)
    actual = d._require_capture_result(d._capture_once())
    assert actual["terminal"] == "invalid_producer_return"
    assert actual["binding"] is None
    assert actual["observation"]["producer_return_received"] is True
    assert "SECRET" not in d.canonical_json_bytes(actual).decode()


def test_hostile_opaque_is_not_inspected(monkeypatch):
    class Hostile:
        def __getattribute__(self, _):
            raise AssertionError("must not inspect")
        def __repr__(self):
            raise AssertionError("must not render")
    monkeypatch.setattr(d.capture, "capture_massive_history", lambda **_: Hostile())
    assert d._capture_once()["terminal"] == "invalid_producer_return"


@pytest.mark.parametrize("field, value", [
    ("artifact_path", Path("/outside/synthetic")), ("artifact_path", "not Path"),
    ("manifest_sha256", "x"), ("capture_sha256", "x"), ("capture_id", "bad/path"),
    ("capture_started_at", "2026-10-12T21:00:00.000000Z"),
    ("capture_completed_at", "2026-10-13T20:00:00.000000Z"),
    ("total_page_count", True), ("total_page_count", 2), ("total_page_count", 513),
    ("total_row_count", True), ("total_row_count", -1), ("total_row_count", 100001),
    ("role_row_counts", ()), ("capture_transport", "offline_test_double"),
])
def test_producer_binding_validation(source, field, value):
    with pytest.raises((ValueError, TypeError)):
        d._binding(replace(source, **{field: value}))


@pytest.mark.parametrize("mutation", ["role_name", "role_order", "role_bool", "role_total", "extra"])
def test_serialized_binding_exact_shape(source, mutation):
    value = d._binding(source)
    if mutation == "role_name":
        value["role_row_counts"][0][0] = "unreviewed"
    elif mutation == "role_order":
        value["role_row_counts"].reverse()
    elif mutation == "role_bool":
        value["role_row_counts"][0][1] = False
    elif mutation == "role_total":
        value["role_row_counts"][0][1] = 1
    else:
        value["extra"] = "secret"
    with pytest.raises(ValueError):
        d._require_binding(value)


def test_authentication_real_quality_empty_pages_no_publication(monkeypatch, source):
    calls = []
    def bridge(path, **kwargs):
        calls.append((path, kwargs["expected_transport"]))
        return source
    monkeypatch.setattr(d.capture, "_visit_authenticated_massive_capture_pages_for_bridge", bridge)
    value = d._authenticate(d._binding(source))
    assert d._require_authentication(value, d._binding(source)) == value
    assert calls == [(source.artifact_path, d.capture.PRODUCTION_TRANSPORT)]
    assert value["authenticated"] is True
    assert value["receipt_published"] is False
    assert "events" not in value


@pytest.mark.parametrize("field, value", [
    ("manifest_sha256", "c" * 64), ("capture_sha256", "c" * 64),
    ("capture_id", "different"), ("capture_completed_at", "2026-10-13T21:00:02.000000Z"),
    ("capture_started_at", "2026-10-13T20:59:59.000000Z"),
    ("total_page_count", 4), ("total_row_count", 1),
    ("role_row_counts", tuple((r, 1) for r in d.quality.ROLE_ORDER)),
    ("capture_transport", "offline_test_double"), ("artifact_path", Path("/not/capture")),
])
def test_every_bridge_binding_field_is_compared(monkeypatch, source, field, value):
    changed = replace(source, **{field: value})
    monkeypatch.setattr(d.capture, "_visit_authenticated_massive_capture_pages_for_bridge", lambda *_, **__: changed)
    with pytest.raises(ValueError):
        d._authenticate(d._binding(source))


@pytest.mark.parametrize("field, value", [
    ("first_event_date", "2026-10-11"), ("last_event_date", "2026-10-13"),
    ("point_in_time_proven", True), ("paper_look_committed", True),
    ("qc_calls", False), ("outcome_reads", 1), ("capture_id", "different"),
])
def test_wrong_receipt_window_flags_or_binding_refused(monkeypatch, source, field, value):
    monkeypatch.setattr(d.capture, "_visit_authenticated_massive_capture_pages_for_bridge", lambda *_, **__: source)
    receipt = _receipt(source)
    receipt[field] = value
    real = d.quality.build_receipt_from_authenticated_pages
    def substitute(callback, *args, **kwargs):
        real(callback, *args, **kwargs)
        payload = d.canonical_json_bytes(receipt)
        return payload, d.hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(d.quality, "build_receipt_from_authenticated_pages", substitute)
    with pytest.raises(ValueError):
        d._authenticate(d._binding(source))


def test_real_quality_rejects_wrong_page_window(monkeypatch, source):
    def bridge(_path, *, visit_page, **_):
        visit_page(SimpleNamespace(redacted_query_bytes=d.canonical_json_bytes({
            "requested_first_event_date": "2026-10-07", "requested_last_event_date": "2026-10-11"})))
        return source
    monkeypatch.setattr(d.capture, "_visit_authenticated_massive_capture_pages_for_bridge", bridge)
    with pytest.raises(d.quality.ForwardDataQualityError):
        d._authenticate(d._binding(source))


@pytest.mark.parametrize("payload", [b"", b"{}\n\n", b"{}{}", b'{"x":1,"x":1}', b"[1]", b"x", b" " * (d.MAX_CHANNEL + 1)])
def test_channel_rejects_empty_malformed_duplicate_trailing_oversized(payload):
    with pytest.raises(ValueError):
        d._decode(payload)


def test_channel_accepts_exact_boundary():
    payload = d.canonical_json_bytes({"x": "a" * (d.MAX_CHANNEL - 9)})
    assert len(payload) == d.MAX_CHANNEL
    assert d._decode(payload)["x"] == "a" * (d.MAX_CHANNEL - 9)


@pytest.mark.parametrize("mutation", ["count_zero", "unknown_terminal", "extra", "false_invoked", "return_without_binding"])
def test_capture_channel_requires_consistent_finite_shape(source, mutation):
    value = _returned(source)
    if mutation == "count_zero":
        value["observation"]["provider_request_count"] = 0
    elif mutation == "unknown_terminal":
        value["terminal"] = "SECRET"
    elif mutation == "extra":
        value["extra"] = True
    elif mutation == "false_invoked":
        value["observation"]["capture_invoked"] = False
    else:
        value["binding"] = None
    with pytest.raises((ValueError, TypeError)):
        d._require_capture_result(value)


def test_duplicate_claim_is_spent_and_original_unchanged(private_control):
    directory, claim = _claim()
    try:
        before = os.pread(claim, d.MAX_CHANNEL, 0)
        with pytest.raises(FileExistsError):
            _claim()
        assert os.pread(claim, d.MAX_CHANNEL, 0) == before
        assert set(os.listdir(directory)) == {"claim.json", "runtime"}
    finally:
        _close(directory, claim)


@pytest.mark.parametrize("stage", ["claim_write", "runtime_mkdir", "first_fsync"])
def test_partial_claim_is_ambiguous_not_preclaim(private_control, monkeypatch, capsys, stage):
    monkeypatch.setattr(d, "_preflight", lambda *_: None)
    monkeypatch.setattr(d, "_run_worker", lambda *_: pytest.fail("must not dispatch"))
    if stage == "claim_write":
        monkeypatch.setattr(d.capture, "_exclusive_private_write_at", lambda *_: (_ for _ in ()).throw(OSError("synthetic")))
    elif stage == "runtime_mkdir":
        # os.supports_dir_fd stores original function identities; this fixture
        # must not let its mkdir wrapper trip the unrelated platform guard.
        monkeypatch.setattr(d.capture, "_require_dirfd_support", lambda: None)
        real = d.os.mkdir
        def mkdir(path, *args, **kwargs):
            if path == "runtime":
                raise OSError("synthetic")
            return real(path, *args, **kwargs)
        monkeypatch.setattr(d.os, "mkdir", mkdir)
    else:
        monkeypatch.setattr(d.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("synthetic")))
    assert d.run("c" * 40, "d" * 64) == 2
    assert private_control.exists()
    output = capsys.readouterr().out
    assert "claim_ambiguous" in output
    assert "preclaim_refusal" not in output
    assert '"attempt_consumed":null' in output


@pytest.mark.parametrize("mutation", ["bool_count", "bool_pages", "extra", "missing"])
def test_authentication_received_binding_exact_types(monkeypatch, source, mutation):
    monkeypatch.setattr(d.capture, "_visit_authenticated_massive_capture_pages_for_bridge", lambda *_, **__: source)
    value = d._authenticate(d._binding(source))
    if mutation == "bool_count":
        value["binding"]["total_row_count"] = False
    elif mutation == "bool_pages":
        value["binding"]["total_page_count"] = True
    elif mutation == "extra":
        value["binding"]["extra"] = 1
    else:
        del value["binding"]["capture_id"]
    with pytest.raises(ValueError):
        d._require_authentication(value, d._binding(source))


def test_preclaim_refusal_dispatches_nothing(monkeypatch, capsys):
    monkeypatch.setattr(d, "_preflight", lambda *_: (_ for _ in ()).throw(d.Refusal("control_refused")))
    monkeypatch.setattr(d, "_claim", lambda *_: pytest.fail("claim must not occur"))
    monkeypatch.setattr(d, "_run_worker", lambda *_: pytest.fail("worker must not occur"))
    assert d.run("c" * 40, "d" * 64) == 2
    assert "preclaim_refusal" in capsys.readouterr().out


def _preflight_fixture(monkeypatch):
    monkeypatch.setattr(d.sys, "platform", "darwin")
    monkeypatch.setattr(d.sys, "version_info", (3, 13))
    monkeypatch.setattr(d.sys, "executable", str(d.PYTHON))
    monkeypatch.setattr(d, "_source_digest", lambda p: "d" * 64 if p == d.SOURCE else d.SOURCE_PINS[str(p.relative_to(d.ROOT))])
    responses = [str(d.ROOT), d.BRANCH, "c" * 40, ""]
    calls = []
    def git(*args, **kwargs):
        calls.append(args[0])
        return SimpleNamespace(returncode=0, stdout=responses[len(calls)-1].encode(), stderr=b"")
    monkeypatch.setattr(d.subprocess, "run", git)
    return responses, calls


@pytest.mark.parametrize("changed", ["root", "branch", "head", "dirty", "pin", "host", "python"])
def test_preflight_mismatch_refuses(monkeypatch, changed):
    responses, calls = _preflight_fixture(monkeypatch)
    if changed in ("root", "branch", "head", "dirty"):
        responses[["root", "branch", "head", "dirty"].index(changed)] = "mismatch"
    elif changed == "pin":
        monkeypatch.setattr(d, "_source_digest", lambda _: "e" * 64)
    elif changed == "host":
        monkeypatch.setattr(d.sys, "platform", "win32")
    else:
        monkeypatch.setattr(d.sys, "version_info", (3, 12))
    with pytest.raises(ValueError):
        d._preflight("c" * 40, "d" * 64, time.monotonic() + 3)
    if changed in ("host", "python"):
        assert calls == []


def test_preflight_success_is_only_selected_pin_verification(monkeypatch):
    _, calls = _preflight_fixture(monkeypatch)
    d._preflight("c" * 40, "d" * 64, time.monotonic() + 3)
    assert len(calls) == 4


@pytest.mark.parametrize("args", [["_worker"], ["_worker", "capture", "-1", "-2", "-3"],
                                  ["_worker", "capture", "0", "0", "0"],
                                  ["_worker", "arbitrary", "0", "1", "2"]])
def test_direct_worker_without_inherited_claim_cannot_dispatch(args, monkeypatch):
    monkeypatch.setattr(d, "_capture_once", lambda: pytest.fail("must not dispatch"))
    assert d.main(args) == 2


def test_worker_checks_parent_context(private_control, monkeypatch):
    directory, claim = _claim()
    try:
        with pytest.raises(ValueError):
            d._require_context(directory, claim)
        monkeypatch.setattr(d.os, "getppid", d.os.getpid)
        context, deadline = d._require_context(directory, claim)
        assert context["attempt_consumed"] is True
        assert 0 < deadline - time.monotonic() < 60
    finally:
        _close(directory, claim)


def test_worker_capture_is_claimed_and_single_use(private_control, monkeypatch, source):
    directory, claim = _claim()
    channel = os.open("capture-result.json", os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600, dir_fd=directory)
    calls = []
    try:
        monkeypatch.setattr(d.os, "getppid", d.os.getpid)
        monkeypatch.setattr(d, "_preflight", lambda *_: None)
        monkeypatch.setattr(d, "_capture_once", lambda: calls.append(True) or _returned(source))
        assert d._worker("capture", directory, claim, channel) == 0
        os.ftruncate(channel, 0)  # Synthetic fixture isolates the spent start marker.
        assert d._worker("capture", directory, claim, channel) == 2
        assert calls == [True]
        assert "capture-started.json" in os.listdir(directory)
    finally:
        _close(channel, claim, directory)


class FakeProcess:
    def __init__(self, returncode=0, timeout=False):
        self.returncode = returncode
        self.timeout = timeout
        self.killed = False
        self.waited = False
        self.inputs = []
    def communicate(self, input, timeout):
        self.inputs.append((input, timeout))
        if self.timeout:
            self.returncode = None
            raise subprocess.TimeoutExpired("synthetic", timeout)
        return None, None
    def poll(self):
        return self.returncode
    def kill(self):
        self.killed = True
        self.returncode = -9
    def wait(self, timeout):
        self.waited = True
        return self.returncode


@pytest.mark.parametrize("mode, label", [("nonzero", "worker_nonzero"), ("timeout", "worker_timeout"),
                                        ("missing", "worker_channel_refused"), ("trailing", "worker_channel_refused")])
def test_parent_worker_failures_are_spent_without_retry(private_control, monkeypatch, mode, label):
    directory, claim = _claim()
    process = FakeProcess(2 if mode == "nonzero" else 0, mode == "timeout")
    calls = []
    def launch(args, **kwargs):
        calls.append((args, kwargs))
        if mode == "trailing":
            os.write(kwargs["pass_fds"][-1], b"{}{}")
        return process
    monkeypatch.setattr(d.subprocess, "Popen", launch)
    try:
        with pytest.raises(ValueError):
            d._run_worker("capture", directory, claim, time.monotonic() + 10)
        assert len(calls) == 1
        assert calls[0][1]["stdout"] == subprocess.DEVNULL
        assert calls[0][1]["stderr"] == subprocess.DEVNULL
        assert calls[0][1]["env"]["TMPDIR"] == str(private_control / "runtime")
        assert "capture-result.json" in os.listdir(directory)
        if mode == "timeout":
            assert process.killed and process.waited
    finally:
        _close(directory, claim)


def test_authentication_worker_has_native_network_denial(private_control, monkeypatch, source):
    directory, claim = _claim()
    args_seen = []
    def launch(args, **kwargs):
        args_seen.append((args, kwargs))
        os.write(kwargs["pass_fds"][-1], b"{}\n")
        return FakeProcess()
    monkeypatch.setattr(d.subprocess, "Popen", launch)
    monkeypatch.setenv("MASSIVE_API_KEY", "SECRET-EXAMPLE-ONLY")
    try:
        assert d._run_worker("authenticate", directory, claim, time.monotonic() + 10, d._binding(source)) == {}
        args, kwargs = args_seen[0]
        assert args[:3] == ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)(deny network*)"]
        assert "MASSIVE_API_KEY" not in kwargs["env"]
    finally:
        _close(directory, claim)


def test_parent_success_requires_authentication_and_durable_report(private_control, monkeypatch, source, capsys):
    monkeypatch.setattr(d, "_preflight", lambda *_: None)
    monkeypatch.setattr(d.capture, "_visit_authenticated_massive_capture_pages_for_bridge", lambda *_, **__: source)
    calls = []
    def worker(stage, directory, claim, deadline, binding=None):
        calls.append(stage)
        assert "claim.json" in os.listdir(directory)
        assert os.fstat(claim).st_size > 0
        return _returned(source) if stage == "capture" else d._authenticate(binding)
    monkeypatch.setattr(d, "_run_worker", worker)
    assert d.run("c" * 40, "d" * 64) == 0
    assert calls == ["capture", "authenticate"]
    report = d._decode((private_control / "report.json").read_bytes())
    assert report["terminal"] == "accepted"
    assert report["authentication"]["authenticated"] is True
    assert report["provider_request_count"] is None
    assert "report_sha256" in capsys.readouterr().out


def test_failed_authentication_never_accepts_return(private_control, monkeypatch, source):
    monkeypatch.setattr(d, "_preflight", lambda *_: None)
    def worker(stage, *args):
        if stage == "capture":
            return _returned(source)
        raise d.Refusal("worker_nonzero")
    monkeypatch.setattr(d, "_run_worker", worker)
    assert d.run("c" * 40, "d" * 64) == 2
    report = d._decode((private_control / "report.json").read_bytes())
    assert report["terminal"] == "worker_nonzero"
    assert report["capture_observation"]["producer_return_received"] is True
    assert report["authentication"] is None


def test_parent_alarm_covers_operation():
    with pytest.raises(d.Deadline):
        with d._alarm(time.monotonic() + 0.01):
            signal.pause()


def test_run_wraps_whole_operation_in_parent_alarm(monkeypatch, capsys):
    monkeypatch.setattr(d, "DEADLINE_SECONDS", 0.01)
    def bounded_slow_operation(*_):
        time.sleep(0.05)  # A reverse mutation must remain bounded too.
        return 0
    monkeypatch.setattr(d, "_run", bounded_slow_operation)
    assert d.run("c" * 40, "d" * 64) == 2
    assert "parent_ambiguous" in capsys.readouterr().out


@pytest.mark.parametrize("when", ["stale", "future"])
def test_parent_freshness_refuses_before_authentication(private_control, monkeypatch, source, when):
    monkeypatch.setattr(d, "_preflight", lambda *_: None)
    if when == "stale":
        started = "2026-10-13T20:00:00.000000Z"
        source = replace(source, capture_started_at=started,
                         artifact_path=d.CAPTURE_ROOT / d.capture._artifact_id_from_timestamp(started))
    else:
        source = replace(source, capture_completed_at="2026-10-13T21:00:04.000000Z")
    calls = []
    def worker(stage, *_):
        calls.append(stage)
        assert stage == "capture"
        return _returned(source)
    monkeypatch.setattr(d, "_run_worker", worker)
    assert d.run("c" * 40, "d" * 64) == 2
    assert calls == ["capture"]
    report = d._decode((private_control / "report.json").read_bytes())
    assert report["terminal"] == "invalid_producer_return"
    assert report["authentication"] is None


def test_late_publication_is_ambiguous_even_if_report_says_accepted(private_control, monkeypatch, source, capsys):
    monkeypatch.setattr(d, "_preflight", lambda *_: None)
    monkeypatch.setattr(d.capture, "_visit_authenticated_massive_capture_pages_for_bridge", lambda *_, **__: source)
    monkeypatch.setattr(d, "_run_worker", lambda stage, directory, claim, deadline, binding=None:
                        _returned(source) if stage == "capture" else d._authenticate(binding))
    real_write = d.capture._exclusive_private_write_at
    real_clock = d.time.monotonic
    late = []
    def write(directory, filename, payload, label):
        real_write(directory, filename, payload, label)
        if filename == "report.json":
            late.append(True)
    monkeypatch.setattr(d.capture, "_exclusive_private_write_at", write)
    monkeypatch.setattr(d.time, "monotonic", lambda: 10**20 if late else real_clock())
    assert d.run("c" * 40, "d" * 64) == 2
    assert "publication_ambiguous" in capsys.readouterr().out
    assert d._decode((private_control / "report.json").read_bytes())["terminal"] == "accepted"


def test_source_digest_refuses_named_replacement(tmp_path, monkeypatch):
    original = tmp_path / "source.py"
    replacement = tmp_path / "replacement.py"
    original.write_bytes(b"original\n")
    replacement.write_bytes(b"replacement\n")
    real_read = d.os.read
    def read(fd, size):
        value = real_read(fd, size)
        os.replace(replacement, original)  # Synthetic fixture only.
        return value
    monkeypatch.setattr(d.os, "read", read)
    with pytest.raises(ValueError):
        d._source_digest(original)


@pytest.mark.parametrize("stage", ["capture", "authenticate"])
def test_real_synthetic_child_fd_transport_and_noise_discard(private_control, monkeypatch, source, capsys, stage):
    directory, claim = _claim()
    real_launch = d.subprocess.Popen
    launches = []
    def launch(args, **kwargs):
        fd = kwargs["pass_fds"][-1]
        code = f"import os; os.write({fd}, b'{{}}\\n'); os.fsync({fd}); print('SYNTHETIC-NOISE'); os.write(2, b'SYNTHETIC-ERROR')"
        command = [str(d.PYTHON), "-B", "-c", code]
        if stage == "authenticate":
            command = args[:3] + command  # Preserve actual sandbox-exec denial.
        child = real_launch(command, **kwargs)
        launches.append(child)
        return child
    monkeypatch.setattr(d.subprocess, "Popen", launch)
    try:
        assert d._run_worker(stage, directory, claim, time.monotonic() + 10,
                             None if stage == "capture" else d._binding(source)) == {}
        assert len(launches) == 1 and launches[0].returncode == 0
        assert capsys.readouterr() == ("", "")
    finally:
        _close(directory, claim)


def test_real_synthetic_child_timeout_is_killed_and_reaped(private_control, monkeypatch):
    directory, claim = _claim()
    real_launch = d.subprocess.Popen
    children = []
    def launch(_args, **kwargs):
        child = real_launch([str(d.PYTHON), "-B", "-c", "import time; time.sleep(10)"], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(d.subprocess, "Popen", launch)
    try:
        with pytest.raises(d.Refusal, match="worker_timeout"):
            d._run_worker("capture", directory, claim, time.monotonic() + 2.03)
        assert len(children) == 1
        assert children[0].poll() == -signal.SIGKILL
    finally:
        _close(directory, claim)


def test_expired_deadline_refuses_immediately():
    with pytest.raises(d.Deadline):
        d._remaining(time.monotonic() - 1)


def test_direct_import_boundary_excludes_execution_and_dispatch_fence():
    source = Path(d.__file__).read_text()
    imports = [n for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.Import, ast.ImportFrom))]
    names = {n.module for n in imports if isinstance(n, ast.ImportFrom)}
    names.update(alias.name for node in imports if isinstance(node, ast.Import) for alias in node.names)
    assert not any(n and n.split(".")[0] in {"assistant", "execution", "ml", "risk", "quantconnect"} for n in names)
    assert "assistant.dispatch_fence" not in sys.modules
