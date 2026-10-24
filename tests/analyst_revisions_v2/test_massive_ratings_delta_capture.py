"""Synthetic R297 transport/lifecycle checks; never a real credential or send."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from tests.analyst_revisions_v2._dispatch_fence_closure import assert_lane_closure_excludes_dispatch_fence

from scripts import capture_arv2_massive_ratings_delta as d

HEAD, SHA, KEY = "a" * 40, "b" * 64, "SYNTHETIC-CREDENTIAL-NOT-REAL"


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    safe = {key: os.environ[key] for key in ("TMPDIR", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD") if key in os.environ}
    safe["PATH"] = os.defpath
    monkeypatch.setattr(os, "environ", safe)
    monkeypatch.setattr(d.subprocess, "run", lambda *_a, **_k: pytest.fail("no real command"))
    monkeypatch.setattr(d.credentials, "load_key", lambda *_a, **_k: KEY)
    monkeypatch.setattr(d.transport, "_check_transport_logging", lambda: None)
    for name in ("_preflight", "_claim", "_observe", "_validate", "_run", "run", "read_output"):
        monkeypatch.setattr(d.transport, name, lambda *_a, **_k: pytest.fail("spent A operation forbidden"))
    for name in ("_preflight", "_claim", "_worker", "_run_worker", "_run", "run", "_capture_once"):
        monkeypatch.setattr(d.helpers, name, lambda *_a, **_k: pytest.fail("spent R293 operation forbidden"))
    monkeypatch.setattr(d.capture, "capture_massive_history", lambda *_a, **_k: pytest.fail("legacy capture forbidden"))


@pytest.fixture
def control(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    target = tmp_path / "R297-SYNTHETIC"
    monkeypatch.setattr(d, "CONTROL", target)
    monkeypatch.setattr(d.delta, "CAPTURE_PATH", target / "capture")
    monkeypatch.setattr(d.capture, "_require_operational_artifact_scope", lambda _: None)
    monkeypatch.setattr(d, "_preflight", lambda *_: None)
    return target


@contextmanager
def claimed():
    deadline = time.monotonic() + 160
    directory, claim, identity = d._claim(HEAD, SHA, deadline)
    try:
        yield directory, claim, identity, deadline
    finally:
        os.close(claim)
        os.close(directory)


def payload(n=1, next_url=None):
    result = {"status": "OK", "results": [{"benzinga_id": str(1000 + n), "ticker": "AAPL",
        "date": "2026-10-12", "time": "08:00:00", "last_updated": "2026-10-12T12:01:00Z",
        "benzinga_firm_id": "17", "firm": "Synthetic Firm", "rating": "Buy",
        "previous_rating": "Hold", "rating_action": "Upgrades"}]}
    if next_url is not None:
        result["next_url"] = next_url
    return json.dumps(result).encode()


class Response:
    def __init__(self, request, body, status=200):
        self.request, self.url, self.status_code = request, request.url, status
        self.headers = {"Content-Type": "application/json"}
        self.raw, self.body, self.reads, self.closed = self, body, 0, 0

    def stream(self, **kwargs):
        assert kwargs == {"amt": 16384, "decode_content": False}
        self.reads += 1
        for offset in range(0, len(self.body), 16384):
            yield self.body[offset:offset + 16384]

    def close(self):
        self.closed += 1


class Adapter:
    def __init__(self, bodies=None, codes=None, change=None):
        self.bodies, self.codes, self.change = bodies or [payload()], codes or {}, change
        self.responses, self.calls, self.closed = [], [], 0

    def send(self, request, **kwargs):
        index = len(self.calls)
        marker = d.CONTROL / f"send-{index + 1:04d}-started.json"
        assert (d.CONTROL / "claim.json").is_file() and marker.is_file()
        intent = json.loads(marker.read_bytes())
        assert intent["profile_sha256"] == d.PROFILE_SHA256 and intent["endpoint"] == d.ENDPOINT
        assert intent["page_number"] == index + 1
        assert kwargs["stream"] is True and kwargs["verify"] is True
        assert kwargs["cert"] is None and kwargs["proxies"] == {}
        assert 0 < kwargs["timeout"][0] <= 5 and 0 < kwargs["timeout"][1] <= 15
        self.calls.append(request)
        response = Response(request, self.bodies[min(index, len(self.bodies) - 1)], self.codes.get(index, 200))
        self.responses.append(response)
        if self.change:
            self.change(response)
        return response

    def close(self):
        self.closed += 1


def invoke(monkeypatch, adapter):
    monkeypatch.setattr(d.transport, "_new_adapter", lambda: adapter)
    with claimed() as values:
        return d._capture_once(*values)


def test_complete_two_pages_and_authentication(control, monkeypatch):
    next_url = "https://api.massive.com/benzinga/v1/ratings?cursor=second"
    adapter = Adapter([payload(1, next_url), payload(2)])
    reads = []
    def key(provider, **kwargs):
        assert (control / "claim.json").is_file()
        reads.append(provider)
        assert 0 < kwargs["timeout_seconds"] <= 20
        return KEY
    monkeypatch.setattr(d.credentials, "load_key", key)
    result = invoke(monkeypatch, adapter)
    assert result["terminal"] == "capture_completed"
    assert reads == ["massive"] and len(adapter.calls) == 2
    assert result["binding"]["page_count"] == 2 and result["binding"]["row_count"] == 2
    assert d._capture_result(result) is result
    assert d._authenticate(result["binding"])["authenticated"] is True
    assert sorted(p.name for p in (control / "capture").iterdir()) == [
        "manifest.json", "manifest.sha256", "page0001.raw.json", "page0001.rows.jsonl",
        "page0002.raw.json", "page0002.rows.jsonl"]
    assert all(r.closed == 1 for r in adapter.responses) and adapter.closed == 1
    assert KEY not in json.dumps(result)
    assert_lane_closure_excludes_dispatch_fence()


@pytest.mark.parametrize("status", [201, 301, 302, 401, 403, 429, 500, 599])
def test_non200_never_reads_or_retries(control, monkeypatch, status):
    adapter = Adapter([b"NEVER READ"], {0: status})
    result = invoke(monkeypatch, adapter)
    assert result["terminal"] == "http_status" and result["status_code"] == status
    assert result["binding"] is None and result["send_attempt_count"] == 1
    assert adapter.responses[0].reads == 0 and len(adapter.calls) == 1
    assert not (control / "capture/manifest.json").exists()


@pytest.mark.parametrize("status", [True, None, "200", 99, 600])
def test_invalid_status_refuses(control, monkeypatch, status):
    result = invoke(monkeypatch, Adapter(codes={0: status}))
    assert result["terminal"] == "invalid_status" and result["status_code"] is None


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit, d.helpers.Deadline, ValueError])
def test_finite_poisoned_errors_stop(control, monkeypatch, exception):
    class Poison(exception):
        def __str__(self):
            raise AssertionError("never stringify")
        def __repr__(self):
            raise AssertionError("never repr")
    def fail(_):
        raise Poison(KEY)
    result = invoke(monkeypatch, Adapter(change=fail))
    assert result["terminal"] == ("cancelled" if exception in {KeyboardInterrupt, SystemExit}
        else "deadline_timeout" if exception is d.helpers.Deadline else "transport_failure")
    assert result["send_attempt_count"] == 1 and result["binding"] is None


@pytest.mark.parametrize("change", [lambda r: setattr(r, "url", r.url + "&bad=1"),
    lambda r: setattr(r, "request", SimpleNamespace()),
    lambda r: setattr(r.request, "method", "POST"),
    lambda r: r.request.headers.update({"Extra": "bad"}),
    lambda r: r.request.hooks["response"].append(lambda _: None)])
def test_response_request_binding(control, monkeypatch, change):
    adapter = Adapter(change=change)
    result = invoke(monkeypatch, adapter)
    assert result["terminal"] == "response_binding_refused"
    assert adapter.responses[0].reads == 0


@pytest.mark.parametrize("body", [b"<html/>", b'{"status":"ERROR","results":[]}',
    b'{"status":"OK","results":[],"status":"OK"}', b'{"status":"OK","results":[NaN]}',
    b'{"status":"OK","results":[],"next_url":true}', b'{"status":"OK","results":[3]}'])
def test_schema_failure(control, monkeypatch, body):
    result = invoke(monkeypatch, Adapter([body]))
    assert result["terminal"] == "schema_refused" and result["binding"] is None


@pytest.mark.parametrize("next_url", ["https://evil.example/benzinga/v1/ratings?cursor=x",
    "https://api.massive.com/benzinga/v1/earnings?cursor=x",
    "https://api.massive.com/benzinga/v1/ratings?cursor=x&apiKey=secret",
    "https://api.massive.com/benzinga/v1/ratings?cursor=x&limit=999",
    "https://api.massive.com/benzinga/v1/ratings?cursor=x&date.gte=2026-10-01",
    "https://api.massive.com/benzinga/v1/ratings?cursor=x&cursor=y"])
def test_cursor_scope(control, monkeypatch, next_url):
    result = invoke(monkeypatch, Adapter([payload(next_url=next_url)]))
    assert result["terminal"] == "schema_refused" and result["send_attempt_count"] == 1


def test_cycle_not_replayed(control, monkeypatch):
    url = "https://api.massive.com/benzinga/v1/ratings?cursor=same"
    result = invoke(monkeypatch, Adapter([payload(1, url), payload(2, url)]))
    assert result["terminal"] == "schema_refused" and result["send_attempt_count"] == 2


@pytest.mark.parametrize("location", ["row", "metadata", "unicode", "percent"])
def test_credential_echo_never_persisted(control, monkeypatch, location):
    key = "SYNTHETIC/+?KEY"
    monkeypatch.setattr(d.credentials, "load_key", lambda *_a, **_k: key)
    body = json.loads(payload())
    if location == "row":
        body["results"][0]["firm"] = key
    else:
        body["metadata"] = d.quote_plus(key) if location == "percent" else key
    encoded = json.dumps(body).encode()
    if location == "unicode":
        encoded = encoded.replace(key.encode(), "".join(f"\\u{ord(c):04x}" for c in key).encode())
    result = invoke(monkeypatch, Adapter([encoded]))
    assert result["terminal"] == "credential_echo_refused"
    assert not (control / "capture/page0001.raw.json").exists()


@pytest.mark.parametrize("name,value", [("Content-Type", "text/html"), ("Content-Encoding", "gzip"),
    ("Content-Length", "0"), ("Content-Length", "99999999"), ("Content-Length", "1")])
def test_body_transport_bounds(control, monkeypatch, name, value):
    result = invoke(monkeypatch, Adapter(change=lambda r: r.headers.update({name: value})))
    assert result["terminal"] == "body_refused"


@pytest.mark.parametrize("bound", ["MAX_RAW_PAGE", "MAX_RAW_TOTAL", "MAX_ROWS_TOTAL", "MAX_ROWS"])
def test_size_limits(control, monkeypatch, bound):
    monkeypatch.setattr(d, bound, 0 if bound == "MAX_ROWS" else 1)
    result = invoke(monkeypatch, Adapter())
    assert result["terminal"] in {"body_refused", "limits_refused"}


def test_page_budget_no_seventeenth_dispatch(control, monkeypatch):
    bodies = [payload(n, f"https://api.massive.com/benzinga/v1/ratings?cursor={n}") for n in range(1, 17)]
    adapter = Adapter(bodies)
    result = invoke(monkeypatch, adapter)
    assert result["terminal"] == "limits_refused" and len(adapter.calls) == 16
    assert not (control / "capture/manifest.json").exists()


def test_key_failure_no_send(control, monkeypatch):
    def fail(*_a, **_k):
        raise d.credentials.KeychainUnavailable("credentials_unavailable")
    monkeypatch.setattr(d.credentials, "load_key", fail)
    adapter = Adapter()
    result = invoke(monkeypatch, adapter)
    assert result["terminal"] == "credentials_unavailable" and not adapter.calls


def test_claim_collision_never_key(control, monkeypatch):
    with claimed():
        pass
    monkeypatch.setattr(d.credentials, "load_key", lambda *_a, **_k: pytest.fail("no key"))
    assert d.run(HEAD, SHA) == 2


def test_send_marker_collision_stops(control, monkeypatch):
    adapter = Adapter()
    monkeypatch.setattr(d.transport, "_new_adapter", lambda: adapter)
    with claimed() as values:
        d._marker(values[0], "send-0001-started.json", {"existing": True})
        result = d._capture_once(*values)
    assert result["terminal"] == "send_intent_ambiguous" and not adapter.calls


def test_close_failure_prevents_manifest(control, monkeypatch):
    def change(response):
        def fail():
            raise ValueError(KEY)
        response.close = fail
    result = invoke(monkeypatch, Adapter(change=change))
    assert result["terminal"] == "close_refused" and result["binding"] is None
    assert not (control / "capture/manifest.json").exists()


def inline_worker(stage, directory, claim, deadline, binding=None):
    if stage == "capture":
        return d._capture_once(directory, claim, d.helpers._identity(d.helpers._file_metadata(claim)), deadline)
    return d._authenticate(binding)


def parent(monkeypatch, capsys, adapter=None):
    monkeypatch.setattr(d.transport, "_new_adapter", lambda: adapter or Adapter())
    monkeypatch.setattr(d, "_run_worker", inline_worker)
    code = d.run(HEAD, SHA)
    envelope = json.loads(capsys.readouterr().out)
    return code, envelope


def test_parent_and_output_reader(control, monkeypatch, capsys):
    code, envelope = parent(monkeypatch, capsys)
    assert code == 0 and envelope["terminal"] == "accepted"
    result = d.read_output(HEAD, SHA, envelope["report_sha256"], envelope["report_bytes"], code)
    assert result["output_authenticated"] and result["capture_accepted"]
    assert result["capture"]["binding"]["row_count"] == 1
    assert result["backtest_ready"] is result["three_role_complete"] is result["point_in_time_proven"] is False


@pytest.mark.parametrize("wrong", ["exit", "digest", "size", "head", "caller"])
def test_reader_external_binding(control, monkeypatch, capsys, wrong):
    code, env = parent(monkeypatch, capsys)
    args = [HEAD, SHA, env["report_sha256"], env["report_bytes"], code]
    indexes = {"head": 0, "caller": 1, "digest": 2, "size": 3, "exit": 4}
    args[indexes[wrong]] = {"head": "c" * 40, "caller": "c" * 64,
        "digest": "c" * 64, "size": 1, "exit": 2}[wrong]
    with pytest.raises((ValueError, d.Refusal)):
        d.read_output(*args)


def test_failure_authenticated_not_success(control, monkeypatch, capsys):
    code, env = parent(monkeypatch, capsys, Adapter(codes={0: 403}))
    assert code == 2
    result = d.read_output(HEAD, SHA, env["report_sha256"], env["report_bytes"], code)
    assert result["output_authenticated"] and not result["capture_accepted"]
    assert result["capture"]["status_code"] == 403


def test_auth_failure_never_accepted(control, monkeypatch, capsys):
    monkeypatch.setattr(d, "_authenticate", lambda _: {"authenticated": False, "binding": None})
    code, envelope = parent(monkeypatch, capsys)
    assert code == 2 and envelope["terminal"] == "authentication_refused"


_AUTH_NUMERIC_ALIASES = [(name, "float") for name in (
    "manifest_byte_count", "page_count", "row_count", "raw_byte_count", "rows_byte_count")
] + [(name, "bool") for name in ("page_count", "row_count")]


@pytest.mark.parametrize("field,kind", _AUTH_NUMERIC_ALIASES)
def test_parent_refuses_auth_binding_numeric_alias(control, monkeypatch, capsys, field, kind):
    original = d._authenticate
    def malformed(binding):
        result = original(binding)
        result["binding"] = dict(result["binding"])
        value = result["binding"][field]
        result["binding"][field] = float(value) if kind == "float" else bool(value)
        return result
    monkeypatch.setattr(d, "_authenticate", malformed)
    code, envelope = parent(monkeypatch, capsys)
    assert code == 2 and envelope["terminal"] == "authentication_refused"


@pytest.mark.parametrize("field,kind", _AUTH_NUMERIC_ALIASES)
def test_output_validator_refuses_auth_binding_numeric_alias(control, monkeypatch, capsys, field, kind):
    code, _ = parent(monkeypatch, capsys)
    assert code == 0
    report = json.loads((control / "report.json").read_bytes())
    claim = json.loads((control / "claim.json").read_bytes())
    value = report["authentication"]["binding"][field]
    report["authentication"]["binding"][field] = float(value) if kind == "float" else bool(value)
    with pytest.raises(ValueError):
        d._validate(claim, report, HEAD, SHA, code)


@pytest.mark.parametrize("stage", ["capture", "authenticate"])
def test_worker_requires_parent_and_unique_start(control, monkeypatch, stage):
    with claimed() as (directory, claim, identity, deadline):
        context = d.helpers._read_channel(claim)
        monkeypatch.setattr(os, "getppid", lambda: context["parent_pid"])
        fd = os.open(f"{stage}-result.json", os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600, dir_fd=directory)
        try:
            monkeypatch.setattr(d, "_capture_once", lambda *_: d._blank_capture())
            monkeypatch.setattr(d, "_authenticate", lambda _: {"synthetic": True})
            monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"{}\n")))
            assert d._worker(stage, directory, claim, fd) == 0
            assert d._worker(stage, directory, claim, fd) == 2
        finally:
            os.close(fd)


def test_worker_wrong_parent_no_capture(control, monkeypatch):
    with claimed() as (directory, claim, identity, deadline):
        monkeypatch.setattr(os, "getppid", lambda: -1)
        monkeypatch.setattr(d, "_capture_once", lambda *_: pytest.fail("not dispatched"))
        assert d._worker("capture", directory, claim, 987654) == 2


@pytest.mark.parametrize("stage", ["capture", "authenticate"])
def test_dispatch_fd_environment_and_network_wrapper(control, monkeypatch, stage):
    observed = []
    class Process:
        returncode = 0
        def __init__(self, args, **kwargs):
            observed.append((args, kwargs))
            self.fd = kwargs["pass_fds"][2]
            assert kwargs["cwd"] == d.ROOT and kwargs["close_fds"] is True
            assert kwargs["stdout"] == kwargs["stderr"] == d.subprocess.DEVNULL
            assert set(kwargs["env"]) == {"PATH", "TMPDIR", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX",
                "PYTHONDONTWRITEBYTECODE", "PYTEST_DISABLE_PLUGIN_AUTOLOAD"}
        def communicate(self, payload, timeout):
            assert timeout > 0
            d.helpers._write_channel(self.fd, {"finite": True})
        def poll(self):
            return 0
    monkeypatch.setattr(d.subprocess, "Popen", Process)
    with claimed() as (directory, claim, identity, deadline):
        assert d._run_worker(stage, directory, claim, deadline) == {"finite": True}
    args, kwargs = observed[0]
    assert (args[:3] == ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)(deny network*)"]) == (stage == "authenticate")


def test_dispatch_timeout_kills_only_own_child(control, monkeypatch):
    calls = []
    class Process:
        def __init__(self, *_a, **_k):
            pass
        def communicate(self, *_a, **_k):
            raise d.subprocess.TimeoutExpired("synthetic", 1)
        def poll(self):
            return None
        def kill(self):
            calls.append("kill")
        def wait(self, timeout):
            calls.append(("wait", timeout))
    monkeypatch.setattr(d.subprocess, "Popen", Process)
    with claimed() as (directory, claim, identity, deadline):
        with pytest.raises(d.subprocess.TimeoutExpired):
            d._run_worker("capture", directory, claim, deadline)
    assert calls == ["kill", ("wait", 1)]


@pytest.mark.parametrize("mutation", ["none", "root", "branch", "head", "dirty", "stderr", "returncode", "pin", "caller"])
def test_preflight_exact_bindings(monkeypatch, mutation):
    monkeypatch.setattr(d, "SOURCE_PINS", {"synthetic.py": SHA})
    results = [str(d.ROOT), d.BRANCH, HEAD, ""]
    change = {"root": 0, "branch": 1, "head": 2, "dirty": 3}
    if mutation in change:
        results[change[mutation]] = "wrong"
    def command(*_a, **_k):
        return SimpleNamespace(stdout=(results.pop(0) + "\n").encode(),
            stderr=b"wrong" if mutation == "stderr" else b"", returncode=1 if mutation == "returncode" else 0)
    monkeypatch.setattr(d.subprocess, "run", command)
    def digest(path):
        return "c" * 64 if mutation == "pin" and path != d.SOURCE or mutation == "caller" and path == d.SOURCE else SHA
    monkeypatch.setattr(d.helpers, "_source_digest", digest)
    if mutation == "none":
        d._preflight(HEAD, SHA, time.monotonic() + 10)
    else:
        with pytest.raises(ValueError):
            d._preflight(HEAD, SHA, time.monotonic() + 10)


@pytest.mark.parametrize("field,value", [("platform", "win32"), ("executable", "/wrong/python"), ("version_info", (3, 12))])
def test_host_refusal(monkeypatch, field, value):
    monkeypatch.setattr(sys, field, value)
    with pytest.raises(ValueError):
        d._preflight(HEAD, SHA, time.monotonic() + 10)


def test_sslkeylog_refuses_before_command(monkeypatch):
    monkeypatch.setitem(os.environ, "SSLKEYLOGFILE", "/synthetic/never-created")
    with pytest.raises(ValueError):
        d._preflight(HEAD, SHA, time.monotonic() + 10)


@pytest.mark.parametrize("field,value", [("send_attempt_count", True), ("send_intent_count", 17),
    ("status_code", True), ("binding", {}), ("terminal", "not_a_terminal")])
def test_finite_capture_result_refusals(field, value):
    result = d._blank_capture()
    result[field] = value
    with pytest.raises(ValueError):
        d._capture_result(result)


@pytest.mark.parametrize("stage", ["capture", "authenticate"])
def test_real_tiny_child_fd_and_discarded_noise(control, monkeypatch, capsys, stage):
    real_launch = d.subprocess.Popen
    children = []
    def launch(args, **kwargs):
        fd = kwargs["pass_fds"][-1]
        program = f"import os; os.write({fd}, b'{{}}\\n'); os.fsync({fd}); print('SYNTHETIC'); os.write(2,b'NOISE')"
        command = [str(d.PYTHON), "-B", "-c", program]
        if stage == "authenticate":
            command = args[:3] + command
        child = real_launch(command, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(d.subprocess, "Popen", launch)
    with claimed() as (directory, claim, identity, deadline):
        assert d._run_worker(stage, directory, claim, deadline) == {}
    assert len(children) == 1 and children[0].returncode == 0
    assert capsys.readouterr() == ("", "")


def test_real_tiny_child_timeout_kill_and_reap(control, monkeypatch):
    real_launch = d.subprocess.Popen
    children = []
    def launch(args, **kwargs):
        child = real_launch([str(d.PYTHON), "-B", "-c", "import time; time.sleep(5)"], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(d.subprocess, "Popen", launch)
    with claimed() as (directory, claim, identity, deadline):
        with pytest.raises(d.subprocess.TimeoutExpired):
            d._run_worker("capture", directory, claim, time.monotonic() + 2.03)
    assert len(children) == 1 and children[0].poll() == -9


def test_parent_alarm_covers_nonworker_sections(monkeypatch, capsys):
    monkeypatch.setattr(d, "DEADLINE_SECONDS", 0.01)
    def bounded_slow(*_):
        time.sleep(0.05)
        return 0
    monkeypatch.setattr(d, "_run", bounded_slow)
    assert d.run(HEAD, SHA) == 2
    assert "parent_ambiguous" in capsys.readouterr().out


def test_late_publication_actual_nonzero_overrides_accepted_report(control, monkeypatch, capsys):
    real_write, real_clock = d.transport._write_held, time.monotonic
    late = []
    def write(directory, name, value):
        result = real_write(directory, name, value)
        if name == "report.json":
            late.append(True)
        return result
    monkeypatch.setattr(d.transport, "_write_held", write)
    monkeypatch.setattr(time, "monotonic", lambda: 10**20 if late else real_clock())
    code, envelope = parent(monkeypatch, capsys)
    assert code == 2 and envelope["terminal"] == "publication_ambiguous"
    report = json.loads((control / "report.json").read_bytes())
    assert report["terminal"] == "accepted"
    claim = json.loads((control / "claim.json").read_bytes())
    with pytest.raises(ValueError):
        d._validate(claim, report, HEAD, SHA, 2)


@pytest.mark.parametrize("wrong", ["past", "future"])
def test_stale_capture_binding_does_not_authenticate(control, monkeypatch, capsys, wrong):
    calls = []
    def worker(stage, directory, claim, deadline, binding=None):
        calls.append(stage)
        assert stage == "capture"
        result = inline_worker(stage, directory, claim, deadline)
        result["binding"]["capture_started_at" if wrong == "past" else "capture_completed_at"] = (
            "2026-10-13T00:00:00.000000Z" if wrong == "past" else "2099-10-13T00:00:00.000000Z")
        return result
    monkeypatch.setattr(d.transport, "_new_adapter", lambda: Adapter())
    monkeypatch.setattr(d, "_run_worker", worker)
    assert d.run(HEAD, SHA) == 2
    assert calls == ["capture"]
    assert "accepted" not in capsys.readouterr().out


@pytest.mark.parametrize("field,value", [("attempt_consumed", False), ("provider_request_count", 0),
    ("point_in_time_proven", True), ("three_role_complete", True), ("backtest_ready", True),
    ("paper_look_committed", True), ("qc_calls", True), ("outcome_reads", 1),
    ("authentication", None), ("extra", "synthetic")])
def test_report_validation_refuses_false_claims(control, monkeypatch, capsys, field, value):
    code, envelope = parent(monkeypatch, capsys)
    assert code == 0
    report = json.loads((control / "report.json").read_bytes())
    claim = json.loads((control / "claim.json").read_bytes())
    report[field] = value
    with pytest.raises(ValueError):
        d._validate(claim, report, HEAD, SHA, 0)


@pytest.mark.parametrize("tamper", ["symlink", "mode", "hardlink", "trailing"])
def test_reader_physical_output_refusals(control, monkeypatch, capsys, tamper):
    code, envelope = parent(monkeypatch, capsys)
    path = control / "report.json"
    if tamper == "symlink":
        renamed = control / "synthetic-original.json"
        path.rename(renamed)
        path.symlink_to(renamed)
    elif tamper == "mode":
        path.chmod(0o644)
    elif tamper == "hardlink":
        os.link(path, control / "synthetic-link.json")
    else:
        path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises((ValueError, OSError)):
        d.read_output(HEAD, SHA, envelope["report_sha256"], envelope["report_bytes"], code)


def test_claim_replaced_after_first_page_stops_before_second_send(control, monkeypatch):
    # Section 301 (ARV2R301-009): the claim is rechecked before every page's send,
    # so a claim swapped during the capture stops it before any further contact.
    next_url = "https://api.massive.com/benzinga/v1/ratings?cursor=second"

    def change(_response):
        if len(adapter.calls) == 1:
            claim = control / "claim.json"
            replacement = control / "claim-replacement.json"
            replacement.write_bytes(claim.read_bytes())
            replacement.chmod(0o600)
            replacement.replace(claim)

    adapter = Adapter([payload(1, next_url), payload(2)], change=change)
    result = invoke(monkeypatch, adapter)
    assert len(adapter.calls) == 1
    assert result["terminal"] != "capture_completed" and result["binding"] is None
    assert not (control / "capture/manifest.json").exists()
    assert not (control / "send-0002-started.json").exists()
