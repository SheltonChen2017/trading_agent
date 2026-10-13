"""Synthetic status-only protocol tests; no operational path or credential read."""
from __future__ import annotations

import ast
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace

import pytest

from scripts import run_arv2_massive_http_status_diagnostic as d

HEAD = "a" * 40
SHA = "b" * 64
KEY = "SYNTHETIC-NOT-A-CREDENTIAL"


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch):
    safe = {key: os.environ[key] for key in (
        "TMPDIR", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX", "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    ) if key in os.environ}
    safe["PATH"] = os.defpath
    monkeypatch.setattr(os, "environ", safe)


@pytest.fixture
def private_control(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    target = tmp_path / "R295-SYNTHETIC"
    monkeypatch.setattr(d, "CONTROL", target)
    monkeypatch.setattr(d.capture, "_require_operational_artifact_scope", lambda _: None)
    monkeypatch.setattr(d, "_preflight", lambda *_: None)
    monkeypatch.setattr(d.capture, "_api_key", lambda: KEY)
    return target


class PoisonResponse:
    def __init__(self, request, status):
        self.request = request
        self.url = request.url
        self.status_code = status
        self.closed = 0

    def __getattribute__(self, name):
        if name in {"content", "text", "json", "iter_content", "raw", "headers", "history", "next", "ok", "raise_for_status"}:
            raise AssertionError("body/headers forbidden")
        return object.__getattribute__(self, name)

    def close(self):
        self.closed += 1


class FakeAdapter:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []
        self.responses = []
        self.closed = 0

    def send(self, request, **kwargs):
        self.calls.append((request, kwargs))
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        response = PoisonResponse(request, outcome)
        self.responses.append(response)
        return response

    def close(self):
        self.closed += 1


def install_adapter(monkeypatch, outcomes):
    adapter = FakeAdapter(outcomes)
    monkeypatch.setattr(d, "_new_adapter", lambda: adapter)
    return adapter


def execute(monkeypatch, outcomes):
    adapter = install_adapter(monkeypatch, outcomes)
    code = d._run(HEAD, SHA, time.monotonic() + 60)
    return code, adapter


def read_synthetic_report(control):
    return d.helpers._decode((control / "report.json").read_bytes())


def test_three_first_headers_no_bodies_no_session(private_control, monkeypatch, capsys):
    import requests
    monkeypatch.setattr(requests, "Session", lambda: pytest.fail("Session forbidden"))
    code, adapter = execute(monkeypatch, [200, 200, 200])
    assert code == 0
    report = read_synthetic_report(private_control)
    assert report["terminal"] == "all_statuses_200"
    assert report["send_attempt_count"] == 3
    assert report["provider_request_count"] is None
    assert report["capture_accepted"] is False
    assert adapter.closed == 1
    assert [r.closed for r in adapter.responses] == [1, 1, 1]
    for (request, kwargs), (role, path) in zip(adapter.calls, d.ROLE_PATHS, strict=True):
        assert request.url == "https://api.massive.com" + path + "?date.gte=2026-10-12&date.lte=2026-10-12&limit=1&sort=date.asc"
        assert request.body is None and request.method == "GET"
        assert dict(request.headers) == {"Authorization": "Bearer " + KEY}
        assert kwargs == {"stream": True, "verify": True, "cert": None, "proxies": {}, "timeout": 15}
    assert sorted(p.name for p in private_control.iterdir()) == ["claim.json", "observation-started.json",
        "report.json", "send-1-started.json", "send-2-started.json", "send-3-started.json"]
    output = capsys.readouterr()
    assert output.err == "" and output.out.endswith("\n\n")
    assert KEY not in output.out and KEY not in (private_control / "report.json").read_text()
    envelope = d.helpers._decode(output.out[:-1].encode())
    assert envelope["report_sha256"] == hashlib.sha256((private_control / "report.json").read_bytes()).hexdigest()


@pytest.mark.parametrize("status", [100, 199, 201, 204, 301, 302, 307, 308, 400, 401, 403, 404, 429, 500, 599])
def test_first_non200_stops_without_redirect_or_retry(private_control, monkeypatch, status):
    code, adapter = execute(monkeypatch, [status, 200, 200])
    assert code == 2 and len(adapter.calls) == 1 and adapter.closed == 1
    report = read_synthetic_report(private_control)
    assert report["terminal"] == "http_status" and report["send_attempt_count"] == 1
    assert report["observations"][0]["status_code"] == status
    assert adapter.responses[0].closed == 1


@pytest.mark.parametrize("index", [1, 2])
def test_ordered_stop_later_role(private_control, monkeypatch, index):
    code, adapter = execute(monkeypatch, [200] * index + [403])
    assert code == 2 and len(adapter.calls) == index + 1
    report = read_synthetic_report(private_control)
    assert report["observations"][-1]["role"] == d.ROLE_PATHS[index][0]
    assert report["send_attempt_count"] == index + 1


@pytest.mark.parametrize("status", [None, True, False, 200.0, "200", -1, 0, 99, 600, {}, []])
def test_invalid_numeric_status_never_retained(private_control, monkeypatch, status):
    code, adapter = execute(monkeypatch, [status])
    assert code == 2 and len(adapter.calls) == 1
    row = read_synthetic_report(private_control)["observations"][0]
    assert row["status_code"] is None and row["terminal"] == "invalid_status"


@pytest.mark.parametrize("error", [RuntimeError("EXAMPLE-SECRET"), KeyboardInterrupt("EXAMPLE-SECRET"),
                                  SystemExit("EXAMPLE-SECRET")])
def test_transport_exception_finite_no_retry(private_control, monkeypatch, capsys, error):
    code, adapter = execute(monkeypatch, [error])
    assert code == 2 and len(adapter.calls) == 1 and adapter.closed == 1
    report = read_synthetic_report(private_control)
    assert report["terminal"] == "transport_failure" and report["send_attempt_count"] == 1
    assert "EXAMPLE-SECRET" not in capsys.readouterr().out
    assert "EXAMPLE-SECRET" not in (private_control / "report.json").read_text()


def test_key_only_after_claim_and_start_fsync(private_control, monkeypatch):
    def credential():
        assert (private_control / "claim.json").is_file()
        assert (private_control / "observation-started.json").is_file()
        raise RuntimeError("EXAMPLE-SECRET")
    monkeypatch.setattr(d.capture, "_api_key", credential)
    monkeypatch.setattr(d, "_new_adapter", lambda: pytest.fail("no adapter after credential refusal"))
    assert d._run(HEAD, SHA, time.monotonic() + 60) == 2
    report = read_synthetic_report(private_control)
    assert report["terminal"] == "credentials_unavailable"
    assert report["send_attempt_count"] == 0 and report["observations"] == []


def test_preflight_failure_never_claims_or_credentials(private_control, monkeypatch, capsys):
    monkeypatch.setattr(d, "_preflight", lambda *_: (_ for _ in ()).throw(ValueError("EXAMPLE-SECRET")))
    monkeypatch.setattr(d.capture, "_api_key", lambda: pytest.fail("no credential"))
    assert d._run(HEAD, SHA, time.monotonic() + 60) == 2
    assert not private_control.exists()
    value = d.helpers._decode(capsys.readouterr().out[:-1].encode())
    assert value == {"terminal": "preclaim_refusal", "attempt_consumed": False, "provider_request_count": None}


def test_claim_existing_or_duplicate_never_retries(private_control, monkeypatch, capsys):
    code, adapter = execute(monkeypatch, [403])
    assert code == 2
    before = (private_control / "report.json").read_bytes()
    monkeypatch.setattr(d.capture, "_api_key", lambda: pytest.fail("no credential on duplicate"))
    assert d._run(HEAD, SHA, time.monotonic() + 60) == 2
    assert (private_control / "report.json").read_bytes() == before
    assert len(adapter.calls) == 1
    assert '"attempt_consumed":null' in capsys.readouterr().out


def test_claim_fsync_failure_before_credentials(private_control, monkeypatch):
    monkeypatch.setattr(d.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("EXAMPLE-SECRET")))
    monkeypatch.setattr(d.capture, "_api_key", lambda: pytest.fail("no credential before durable claim"))
    assert d._run(HEAD, SHA, time.monotonic() + 60) == 2


def test_every_send_has_exclusive_intent_before_dispatch(private_control, monkeypatch):
    adapter = install_adapter(monkeypatch, [200, 200, 200])
    original = adapter.send
    def send(request, **kwargs):
        index = len(adapter.calls) + 1
        marker = private_control / f"send-{index}-started.json"
        assert marker.is_file()
        value = d.helpers._decode(marker.read_bytes())
        assert value["endpoint_path"] in request.url
        return original(request, **kwargs)
    adapter.send = send
    assert d._run(HEAD, SHA, time.monotonic() + 60) == 0


def test_duplicate_observation_marker_no_second_credentials(private_control, monkeypatch):
    directory, claim, identity = d._claim(HEAD, SHA)
    result = result_fixture()
    adapter = install_adapter(monkeypatch, [403])
    try:
        d._observe(directory, claim, identity, time.monotonic() + 60, result)
        monkeypatch.setattr(d.capture, "_api_key", lambda: pytest.fail("duplicate credential access"))
        with pytest.raises(FileExistsError):
            d._observe(directory, claim, identity, time.monotonic() + 60, result_fixture())
        assert len(adapter.calls) == 1
    finally:
        os.close(claim)
        os.close(directory)


@pytest.mark.parametrize("mutation", ["method", "query", "body", "headers", "hooks"])
def test_prepared_request_changes_refuse_before_send(private_control, monkeypatch, mutation):
    import requests
    real_prepare = requests.Request.prepare
    def mutated(request):
        prepared = real_prepare(request)
        if mutation == "method": prepared.method = "POST"
        if mutation == "query": prepared.url = prepared.url.replace("limit=1", "limit=2")
        if mutation == "body": prepared.body = b"example"
        if mutation == "headers": prepared.headers["X-Extra"] = "example"
        if mutation == "hooks": prepared.hooks["response"] = [lambda _: None]
        return prepared
    monkeypatch.setattr(requests.Request, "prepare", mutated)
    code, adapter = execute(monkeypatch, [])
    assert code == 2 and not adapter.calls
    assert read_synthetic_report(private_control)["terminal"] == "request_preparation_refused"
    assert not (private_control / "send-1-started.json").exists()


@pytest.mark.parametrize("mutation", ["request", "url", "method", "header", "query"])
def test_response_binding_mismatch_drops_status(private_control, monkeypatch, mutation):
    adapter = install_adapter(monkeypatch, [403])
    original = adapter.send
    def mutated(request, **kwargs):
        response = original(request, **kwargs)
        if mutation == "request": response.request = SimpleNamespace(method=request.method, url=request.url)
        if mutation == "url": response.url = "https://example.invalid/"
        if mutation == "method": request.method = "POST"
        if mutation == "header": request.headers["X-Extra"] = "example"
        if mutation == "query": request.url = request.url.replace("limit=1", "limit=2")
        return response
    adapter.send = mutated
    assert d._run(HEAD, SHA, time.monotonic() + 60) == 2
    row = read_synthetic_report(private_control)["observations"][0]
    assert row["terminal"] == "response_binding_refused" and row["status_code"] is None


@pytest.mark.parametrize("closing", ["response", "adapter"])
def test_close_failure_cannot_be_success(private_control, monkeypatch, closing):
    adapter = install_adapter(monkeypatch, [200, 200, 200])
    def broken_close():
        raise ValueError("EXAMPLE-SECRET")
    if closing == "adapter":
        adapter.close = broken_close
    else:
        original = adapter.send
        def send(*args, **kwargs):
            response = original(*args, **kwargs)
            response.close = broken_close
            return response
        adapter.send = send
    assert d._run(HEAD, SHA, time.monotonic() + 60) == 2
    assert read_synthetic_report(private_control)["terminal"] == "close_refused"


def test_deadline_exception_closes_and_retains_intent(private_control, monkeypatch):
    code, adapter = execute(monkeypatch, [d.helpers.Deadline()])
    assert code == 2 and adapter.closed == 1
    report = read_synthetic_report(private_control)
    assert report["terminal"] == "deadline_timeout" and report["send_attempt_count"] == 1


def test_request_timeout_uses_remaining_budget(private_control, monkeypatch):
    adapter = install_adapter(monkeypatch, [403])
    assert d._run(HEAD, SHA, time.monotonic() + 5) == 2
    assert 0 < adapter.calls[0][1]["timeout"] <= 5


def test_run_alarm_covers_entire_run(monkeypatch):
    events = []
    @contextmanager
    def alarm(deadline):
        events.append("alarm")
        assert 59 < deadline - time.monotonic() <= 60
        yield
        events.append("closed")
    monkeypatch.setattr(d.helpers, "_alarm", alarm)
    monkeypatch.setattr(d, "_run", lambda *args: events.append("run") or 2)
    assert d.run(HEAD, SHA) == 2
    assert events == ["alarm", "run", "closed"]


def test_real_alarm_interrupts_synthetic_sleep():
    original = signal.getsignal(signal.SIGALRM)
    with pytest.raises(d.helpers.Deadline):
        with d.helpers._alarm(time.monotonic() + 0.01):
            time.sleep(0.1)
    assert signal.getsignal(signal.SIGALRM) == original
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0


def test_late_publication_exit2_even_report_all200(private_control, monkeypatch, capsys):
    original = d._write_held
    def late(directory, name, value):
        answer = original(directory, name, value)
        if name == "report.json":
            monkeypatch.setattr(d.helpers, "_remaining", lambda *_: (_ for _ in ()).throw(d.helpers.Deadline()))
        return answer
    monkeypatch.setattr(d, "_write_held", late)
    code, _ = execute(monkeypatch, [200, 200, 200])
    assert code == 2
    assert read_synthetic_report(private_control)["terminal"] == "all_statuses_200"
    assert "publication_ambiguous" in capsys.readouterr().out


def claim_fixture():
    return {"schema": d.SCHEMA, "profile_sha256": d.PROFILE_SHA256,
        "expected_head": HEAD, "caller_sha256": SHA, "parent_pid": 1,
        "claimed_at": "2026-10-13T22:00:00.000000Z", "attempt_consumed": True}


def result_fixture():
    return {"schema": d.SCHEMA, "profile_sha256": d.PROFILE_SHA256,
        "expected_head": HEAD, "caller_sha256": SHA,
        "parent_started_at": "2026-10-13T22:00:00.000000Z",
        "parent_observed_terminal_at": "2026-10-13T22:00:01.000000Z",
        "terminal": "http_status", "attempt_consumed": True,
        "observations": [{"role": d.ROLE_PATHS[0][0], "endpoint_path": d.ROLE_PATHS[0][1],
            "status_code": 403, "send_intent_recorded": True, "terminal": "http_status"}],
        "send_attempt_count": 1, "provider_request_count": None, "capture_accepted": False,
        "point_in_time_proven": False, "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0}


def test_validate_failure_not_capture_success():
    value = d._validate(claim_fixture(), result_fixture(), HEAD, SHA, 2)
    assert value["output_authenticated"] is True
    assert value["diagnostic_complete"] is False and value["capture_accepted"] is False
    assert value["observations"][0]["status_code"] == 403


@pytest.mark.parametrize("actual", [None, True, False, 1, 3, -1, "2", 2.0])
def test_invalid_actual_exit_refused(actual):
    with pytest.raises((ValueError, TypeError)):
        d._validate(claim_fixture(), result_fixture(), HEAD, SHA, actual)


def test_actual_zero_cannot_accept_failure():
    with pytest.raises(ValueError):
        d._validate(claim_fixture(), result_fixture(), HEAD, SHA, 0)


def test_actual_nonzero_cannot_accept_all200_report():
    result = result_fixture()
    result.update(terminal="all_statuses_200", send_attempt_count=3,
        observations=[{"role": role, "endpoint_path": path, "status_code": 200,
            "send_intent_recorded": True, "terminal": "status_200"} for role, path in d.ROLE_PATHS])
    assert d._validate(claim_fixture(), result, HEAD, SHA, 2)["diagnostic_complete"] is False
    assert d._validate(claim_fixture(), result, HEAD, SHA, 0)["diagnostic_complete"] is True


@pytest.mark.parametrize("field,value", [
    ("schema", "bad"), ("profile_sha256", "0" * 64), ("expected_head", "0" * 40),
    ("caller_sha256", "0" * 64), ("attempt_consumed", False),
    ("provider_request_count", 0), ("capture_accepted", True), ("point_in_time_proven", True),
    ("paper_look_committed", True), ("qc_calls", True), ("outcome_reads", 1),
    ("terminal", "accepted"), ("terminal", []), ("send_attempt_count", True),
    ("send_attempt_count", 0), ("send_attempt_count", 4), ("observations", ()),
    ("parent_started_at", "2026-10-13T22:00:02.000000Z"),
    ("parent_observed_terminal_at", "2026-10-13T21:59:59.000000Z"),
])
def test_report_field_refusals(field, value):
    result = result_fixture()
    result[field] = value
    with pytest.raises((ValueError, TypeError)):
        d._validate(claim_fixture(), result, HEAD, SHA, 2)


@pytest.mark.parametrize("field,value", [
    ("role", "wrong"), ("endpoint_path", "/wrong"), ("status_code", True),
    ("status_code", "403"), ("status_code", 600), ("status_code", None),
    ("send_intent_recorded", False), ("send_intent_recorded", 1),
    ("terminal", "bad"), ("terminal", "status_200"),
    ("terminal", "transport_failure"), ("terminal", "request_preparation_refused"),
])
def test_row_refusals(field, value):
    result = result_fixture()
    result["observations"][0][field] = value
    with pytest.raises((ValueError, TypeError)):
        d._validate(claim_fixture(), result, HEAD, SHA, 2)


@pytest.mark.parametrize("target", ["claim", "report", "row"])
def test_unknown_fields_refused(target):
    claim, result = claim_fixture(), result_fixture()
    {"claim": claim, "report": result, "row": result["observations"][0]}[target]["extra"] = "EXAMPLE-SECRET"
    with pytest.raises(ValueError):
        d._validate(claim, result, HEAD, SHA, 2)


def test_continuation_after_non200_refused():
    result = result_fixture()
    result["observations"].append({"role": d.ROLE_PATHS[1][0], "endpoint_path": d.ROLE_PATHS[1][1],
        "status_code": 403, "terminal": "http_status", "send_intent_recorded": True})
    result["send_attempt_count"] = 2
    with pytest.raises(ValueError):
        d._validate(claim_fixture(), result, HEAD, SHA, 2)


def test_reader_reads_only_new_report_claim(private_control, monkeypatch):
    execute(monkeypatch, [403])
    payload = (private_control / "report.json").read_bytes()
    monkeypatch.setattr(d.capture, "_api_key", lambda: pytest.fail("reader credential forbidden"))
    monkeypatch.setattr(d, "_new_adapter", lambda: pytest.fail("reader transport forbidden"))
    names = []
    original = d._read_leaf
    def leaf(directory, name, stack):
        names.append(name)
        return original(directory, name, stack)
    monkeypatch.setattr(d, "_read_leaf", leaf)
    value = d.read_output(HEAD, SHA, hashlib.sha256(payload).hexdigest(), len(payload), 2)
    assert names == ["report.json", "claim.json"]
    assert value["output_authenticated"] and not value["diagnostic_complete"]


@pytest.mark.parametrize("bad_pin", ["hash", "size"])
def test_external_pin_checked_before_decode(private_control, monkeypatch, bad_pin):
    execute(monkeypatch, [403])
    payload = (private_control / "report.json").read_bytes()
    digest, size = hashlib.sha256(payload).hexdigest(), len(payload)
    if bad_pin == "hash": digest = "0" * 64
    else: size += 1
    monkeypatch.setattr(d.helpers, "_decode", lambda _: pytest.fail("decode reached before pin"))
    with pytest.raises(ValueError):
        d.read_output(HEAD, SHA, digest, size, 2)


@pytest.mark.parametrize("change", ["mode", "symlink", "trailing", "empty", "oversize"])
def test_output_physical_and_canonical_refusals(private_control, monkeypatch, change):
    execute(monkeypatch, [403])
    path = private_control / "report.json"
    if change == "mode": path.chmod(0o644)
    if change == "symlink":
        original = private_control / "synthetic-original.json"
        path.rename(original)
        path.symlink_to(original)
    if change == "trailing": path.write_bytes(path.read_bytes() + b"\n")
    if change == "empty": path.write_bytes(b"")
    if change == "oversize": path.write_bytes(b"x" * (d.MAX_BYTES + 1))
    payload = path.read_bytes()
    with pytest.raises((ValueError, OSError)):
        d.read_output(HEAD, SHA, hashlib.sha256(payload).hexdigest(), len(payload), 2)


def test_published_report_mutation_refuses_exit(private_control, monkeypatch, capsys):
    original = d._write_held
    def corrupt(directory, name, value):
        fd, payload, identity = original(directory, name, value)
        if name == "report.json":
            os.pwrite(fd, b"x", 0)
        return fd, payload, identity
    monkeypatch.setattr(d, "_write_held", corrupt)
    code, _ = execute(monkeypatch, [200, 200, 200])
    assert code == 2 and "publication_ambiguous" in capsys.readouterr().out


def test_reader_last_deadline_check(private_control, monkeypatch):
    execute(monkeypatch, [403])
    payload = (private_control / "report.json").read_bytes()
    original = d._validate
    def late(*args):
        result = original(*args)
        monkeypatch.setattr(d.helpers, "_remaining", lambda *_: (_ for _ in ()).throw(d.helpers.Deadline()))
        return result
    monkeypatch.setattr(d, "_validate", late)
    with pytest.raises(d.helpers.Deadline):
        d.read_output(HEAD, SHA, hashlib.sha256(payload).hexdigest(), len(payload), 2)


def test_owned_real_adapter_disables_retries_without_session():
    adapter = d._new_adapter()
    try:
        assert adapter.max_retries.total == 0
        assert adapter.max_retries.read is False
    finally:
        adapter.close()


def test_real_adapter_send_never_preloads_redirect_body(monkeypatch):
    import requests
    adapter = d._new_adapter()
    calls = []
    class Raw:
        status = 302
        headers = {"Location": "https://example.invalid/never-follow"}
        reason = "Found"
        _original_response = None
        closed = False
        released = False
        def read(self, *args, **kwargs):
            pytest.fail("redirect body read")
        def stream(self, *args, **kwargs):
            pytest.fail("redirect body stream")
        def close(self):
            self.closed = True
        def release_conn(self):
            self.released = True
    raw = Raw()
    class Pool:
        def urlopen(self, **kwargs):
            calls.append(kwargs)
            return raw
    monkeypatch.setattr(requests.Session, "send", lambda *a, **k: pytest.fail("Session forbidden"))
    monkeypatch.setattr(adapter, "get_connection_with_tls_context", lambda *a, **k: Pool())
    monkeypatch.setattr(adapter, "cert_verify", lambda *a, **k: None)
    request, _ = d._prepare(d.capture.ROLE_ORDER[0], KEY)
    try:
        response = adapter.send(request, stream=True, timeout=15, verify=True, cert=None, proxies={})
        assert response.status_code == 302 and response.request is request
        assert len(calls) == 1
        assert calls[0]["redirect"] is False and calls[0]["preload_content"] is False
        assert calls[0]["decode_content"] is False and calls[0]["retries"].total == 0
        assert not raw.closed
        response.close()
        assert raw.closed and raw.released
    finally:
        adapter.close()


def test_requests_version_mismatch_refuses(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "__version__", "0.synthetic")
    monkeypatch.setattr(requests.adapters, "HTTPAdapter", lambda *a, **k: pytest.fail("adapter before version"))
    with pytest.raises(ValueError):
        d._new_adapter()


def test_send_marker_partial_failure_no_send_and_explicit_ambiguity(private_control, monkeypatch):
    original = d._write_held
    def broken(directory, name, value):
        answer = original(directory, name, value)
        if name == "send-1-started.json":
            os.close(answer[0])
            raise ValueError("EXAMPLE-SECRET")
        return answer
    monkeypatch.setattr(d, "_write_held", broken)
    code, adapter = execute(monkeypatch, [200])
    assert code == 2 and not adapter.calls
    assert (private_control / "send-1-started.json").is_file()
    report = read_synthetic_report(private_control)
    assert report["terminal"] == "send_intent_ambiguous"
    assert report["send_attempt_count"] == 0  # Acknowledged boundaries, not marker census.
    assert report["observations"][0]["send_intent_recorded"] is False


@pytest.mark.parametrize("value", ["", "synthetic-keylog-path"])
def test_tls_keylog_presence_refuses_before_any_preflight_io(monkeypatch, value):
    monkeypatch.setitem(os.environ, "SSLKEYLOGFILE", value)
    monkeypatch.setattr(d.subprocess, "run", lambda *a, **k: pytest.fail("preflight subprocess"))
    with pytest.raises(ValueError):
        d._preflight(HEAD, SHA, time.monotonic() + 60)


def fake_preflight(monkeypatch, bad=None):
    outputs = {"--show-toplevel": str(d.ROOT), "--show-current": d.BRANCH,
               "HEAD": HEAD, "--porcelain": ""}
    if bad in outputs:
        outputs[bad] = "mismatch"
    commands = []
    def git(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(returncode=1 if bad == "exit" else 0,
            stderr=b"refused" if bad == "stderr" else b"", stdout=outputs[command[-1]].encode() + b"\n")
    monkeypatch.setattr(d.subprocess, "run", git)
    def digest(path):
        if path == d.SOURCE:
            return "0" * 64 if bad == "caller" else SHA
        relative = str(path.relative_to(d.ROOT))
        return "0" * 64 if bad == "dependency" else d.SOURCE_PINS[relative]
    monkeypatch.setattr(d.helpers, "_source_digest", digest)
    return commands


def test_preflight_exact_host_git_and_pins(monkeypatch):
    commands = fake_preflight(monkeypatch)
    d._preflight(HEAD, SHA, time.monotonic() + 60)
    assert len(commands) == 4
    assert all(kwargs["cwd"] == d.ROOT for _, kwargs in commands)


@pytest.mark.parametrize("bad", ["--show-toplevel", "--show-current", "HEAD", "--porcelain",
                                 "exit", "stderr", "caller", "dependency"])
def test_preflight_mismatch_refuses(monkeypatch, bad):
    fake_preflight(monkeypatch, bad)
    with pytest.raises(ValueError):
        d._preflight(HEAD, SHA, time.monotonic() + 60)


@pytest.mark.parametrize("bad", ["platform", "python", "version", "source", "root", "head", "hash"])
def test_unsupported_preflight_refuses(monkeypatch, bad):
    fake_preflight(monkeypatch)
    if bad == "platform": monkeypatch.setattr(d.sys, "platform", "win32")
    if bad == "python": monkeypatch.setattr(d.sys, "executable", "/synthetic/python")
    if bad == "version": monkeypatch.setattr(d.sys, "version_info", (3, 12))
    if bad == "source": monkeypatch.setattr(d, "SOURCE", Path("/synthetic/source.py"))
    if bad == "root": monkeypatch.setattr(d, "ROOT", Path("/synthetic/root"))
    with pytest.raises(ValueError):
        d._preflight("bad" if bad == "head" else HEAD, "bad" if bad == "hash" else SHA,
                     time.monotonic() + 60)


def test_no_spent_or_body_call_sites():
    tree = ast.parse(Path(d.__file__).read_text())
    forbidden = {"capture_massive_history", "_capture_once", "_run_worker", "_worker", "Session",
                 "iter_content", "json", "raise_for_status", "get", "_load_massive_capture_artifact_bounded"}
    # dictionary .get is not needed by this frozen exact-schema implementation.
    assert not [(n.lineno, n.func.attr) for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in forbidden]
    assert "assistant.dispatch_fence" not in sys.modules


def test_profile_pins_and_finite_scope():
    value = d.helpers._decode(d.PROFILE)
    assert value["maximum_send_intents"] == 3
    assert value["query"] == {"date.gte": "2026-10-12", "date.lte": "2026-10-12", "limit": "1", "sort": "date.asc"}
    assert value["stop_first_non200"] and value["capture_accepted"] is False
    assert len(d.SOURCE_PINS) == 8
    assert d.PROFILE_SHA256 == hashlib.sha256(d.PROFILE).hexdigest()


def test_reader_cli_never_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(d, "run", lambda *_: pytest.fail("operational dispatch"))
    monkeypatch.setattr(d, "read_output", lambda *args: {"diagnostic_complete": False})
    assert d.main(["--expected-head", HEAD, "--caller-sha256", SHA, "--read-output",
        "--report-sha256", "c" * 64, "--report-bytes", "623", "--actual-parent-exit", "2"]) == 2
    assert "false" in capsys.readouterr().out


def test_wrong_mode_arguments_never_dispatch(monkeypatch):
    monkeypatch.setattr(d, "run", lambda *_: pytest.fail("wrong-mode dispatch"))
    assert d.main(["--expected-head", HEAD, "--caller-sha256", SHA, "--report-bytes", "623"]) == 2
