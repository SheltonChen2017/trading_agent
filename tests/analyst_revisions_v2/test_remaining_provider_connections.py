"""C lifecycle tests reuse pinned stateless validators, never old operations."""
from __future__ import annotations

import ast
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from scripts import check_arv2_remaining_provider_connections as d

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
    monkeypatch.setattr(d.subprocess, "run", lambda *_a, **_k: pytest.fail("no real command"))
    monkeypatch.setattr(d.credentials, "load_key", lambda *_a, **_k: KEY)
    monkeypatch.setattr(d.contract, "_check_transport_logging", lambda: None)
    def prepare(endpoint, key):
        query = list(endpoint.query) + ([(endpoint.auth_query, key)] if endpoint.auth_query else [])
        url = endpoint.origin + endpoint.path + "?" + urlencode(query)
        return SimpleNamespace(url=url, method="GET", body=None, hooks={"response": []},
            headers={} if endpoint.auth_query else {"Authorization": "Bearer " + key}), url
    monkeypatch.setattr(d.contract, "_prepare", prepare)
    for name in ("_preflight", "_claim", "_check_held", "_observe", "_validate", "_run", "run", "read_output"):
        monkeypatch.setattr(d.contract, name, lambda *_a, **_k: pytest.fail("old operational function forbidden"))


@pytest.fixture
def control(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    target = tmp_path / "R296C-SYNTHETIC"
    monkeypatch.setattr(d, "CONTROL", target)
    monkeypatch.setattr(d.capture, "_require_operational_artifact_scope", lambda _: None)
    monkeypatch.setattr(d, "_preflight", lambda *_: None)
    return target


def body(index):
    if index == 0:
        return [{"symbol": "AAPL", "date": "2026-10-12", "gradingCompany": "Synthetic Firm",
            "previousGrade": "Hold", "newGrade": "Buy", "action": "upgrade"}]
    if index in {1, 2, 3}:
        return {"status": "OK", "results": [{"ticker": "AAPL", "date": "2026-10-12"}]}
    if index == 4:
        return [{"date": "2026-10-12", "open": 100, "high": 101, "low": 99,
            "close": 100, "adjusted_close": 100, "volume": 1000}]
    return {"type": "Earnings", "symbols": "AAPL.US", "earnings": [{"code": "AAPL.US",
        "report_date": "2026-07-30", "date": "2026-06-30", "actual": 1, "estimate": 1}]}


class Response:
    def __init__(self, request, status, payload):
        self.request, self.url, self.status_code = request, request.url, status
        self.headers = {"Content-Type": "application/json"}
        self.raw = self
        self.payload = payload if type(payload) is bytes else json.dumps(payload).encode()
        self.reads = self.closed = 0

    def stream(self, **kwargs):
        assert kwargs == {"amt": 16384, "decode_content": False}
        self.reads += 1
        yield self.payload

    def close(self):
        self.closed += 1


class Adapter:
    def __init__(self, outcomes=None, change=None):
        self.outcomes, self.change = outcomes or {}, change
        self.calls, self.responses, self.closed = [], [], 0

    def send(self, request, **kwargs):
        index = next(i for i, endpoint in enumerate(d.ENDPOINTS)
            if request.url.startswith(endpoint.origin + endpoint.path + "?"))
        self.calls.append((index, request, kwargs))
        status, payload = self.outcomes.get(index, (200, body(index)))
        if isinstance(status, BaseException):
            raise status
        response = Response(request, status, payload)
        self.responses.append(response)
        if self.change:
            self.change(response, index)
        return response

    def close(self):
        self.closed += 1


def execute(monkeypatch, outcomes=None, change=None):
    adapter = Adapter(outcomes, change)
    monkeypatch.setattr(d.contract, "_new_adapter", lambda: adapter)
    return d._run(HEAD, SHA, time.monotonic() + 180), adapter


def report(control):
    return d.helpers._decode((control / "report.json").read_bytes())


def read(control, actual_exit=0, **changes):
    raw = (control / "report.json").read_bytes()
    args = dict(head=HEAD, caller=SHA, report_sha256=hashlib.sha256(raw).hexdigest(),
        report_bytes=len(raw), actual_exit=actual_exit)
    args.update(changes)
    return d.read_output(**args)


def test_six_only_and_one_key_each_claimed_before_read(control, monkeypatch, capsys):
    reads = []
    original_send = Adapter.send
    def send_after_persistent_intent(adapter, request, **kwargs):
        index = next(i for i, endpoint in enumerate(d.ENDPOINTS)
            if request.url.startswith(endpoint.origin + endpoint.path + "?"))
        endpoint = d.ENDPOINTS[index]
        claim = d.helpers._decode((control / "claim.json").read_bytes())
        marker = d.helpers._decode((control / f"send-{index + 1}-started.json").read_bytes())
        assert claim["expected_head"] == HEAD and claim["caller_sha256"] == SHA
        assert marker == {"schema": d.SCHEMA, "profile_sha256": d.PROFILE_SHA256,
            "provider": endpoint.provider, "role": endpoint.role, "endpoint_path": endpoint.path}
        return original_send(adapter, request, **kwargs)
    monkeypatch.setattr(Adapter, "send", send_after_persistent_intent)
    def load(provider, **kwargs):
        assert (control / "claim.json").is_file() and (control / "observation-started.json").is_file()
        reads.append(provider)
        assert 0 < kwargs["timeout_seconds"] <= 20
        return KEY
    monkeypatch.setattr(d.credentials, "load_key", load)
    code, adapter = execute(monkeypatch)
    assert code == 0 and [index for index, *_ in adapter.calls] == list(range(6))
    assert reads == ["fmp", "massive", "eodhd"] and adapter.closed == 1
    assert all(response.closed == 1 for response in adapter.responses)
    for index, request, kwargs in adapter.calls:
        assert "sharadar" not in request.url
        assert (control / f"send-{index + 1}-started.json").is_file()
        assert kwargs == {"stream": True, "verify": True, "cert": None, "proxies": {}, "timeout": 15}
    value = report(control)
    assert value["terminal"] == "all_connections_responded" and value["send_attempt_count"] == 6
    assert value["provider_request_count"] is None and value["backtest_ready"] is False
    out = capsys.readouterr()
    assert out.err == "" and out.out.endswith("\n\n") and KEY not in out.out
    assert all(KEY.encode() not in path.read_bytes() and b"Synthetic Firm" not in path.read_bytes()
        for path in control.iterdir())


@pytest.mark.parametrize("status", [100, 201, 301, 302, 401, 403, 429, 500, 599])
def test_non200_body_unread_no_retry_independent_roles_continue(control, monkeypatch, status):
    code, adapter = execute(monkeypatch, {2: (status, b"SECRET-BODY")})
    assert code == 2 and len(adapter.calls) == 6 and adapter.responses[2].reads == 0
    assert report(control)["observations"][2]["terminal"] == "http_status"


@pytest.mark.parametrize("provider", ["fmp", "massive", "eodhd"])
def test_missing_key_not_provider_request_or_fallback(control, monkeypatch, provider):
    reads = []
    def load(name, **kwargs):
        reads.append(name)
        if name == provider:
            raise d.credentials.KeychainUnavailable("credentials_unavailable")
        return KEY
    monkeypatch.setattr(d.credentials, "load_key", load)
    code, adapter = execute(monkeypatch)
    assert code == 2 and reads == ["fmp", "massive", "eodhd"]
    assert all(d.ENDPOINTS[index].provider != provider for index, *_ in adapter.calls)
    assert report(control)["terminal"] == "completed_with_failures"


@pytest.mark.parametrize("index", range(6))
def test_transport_error_finite_and_no_retry(control, monkeypatch, capsys, index):
    code, adapter = execute(monkeypatch, {index: (RuntimeError("EXAMPLE-SECRET"), None)})
    assert code == 2 and len(adapter.calls) == 6
    assert report(control)["observations"][index]["terminal"] == "transport_failure"
    assert "EXAMPLE-SECRET" not in capsys.readouterr().out


@pytest.mark.parametrize("exception,terminal", [(KeyboardInterrupt(), "cancelled"), (SystemExit(2), "cancelled"),
    (d.helpers.Deadline(), "deadline_timeout")])
@pytest.mark.parametrize("stage", ["key", "send", "body", "schema", "close"])
def test_cancellation_deadline_stop(control, monkeypatch, exception, terminal, stage):
    def stop(*_a, **_k):
        raise exception
    outcomes = change = None
    if stage == "key":
        monkeypatch.setattr(d.credentials, "load_key", stop)
    elif stage == "send":
        outcomes = {0: (exception, None)}
    elif stage == "body":
        monkeypatch.setattr(d.contract, "_body_bytes", stop)
    elif stage == "schema":
        monkeypatch.setattr(d.contract, "_schema", stop)
    else:
        change = lambda response, _: setattr(response, "close", stop)
    code, adapter = execute(monkeypatch, outcomes, change)
    assert code == 2 and len(adapter.calls) == (0 if stage == "key" else 1)
    value = report(control)
    assert value["terminal"] == terminal
    assert all(row["terminal"] == "not_attempted" for row in value["observations"][1:])


@pytest.mark.parametrize("status", [None, True, "200", 200.0, 99, 600])
def test_invalid_status_never_retained(control, monkeypatch, status):
    code, adapter = execute(monkeypatch, {0: (status, body(0))})
    assert code == 2 and adapter.responses[0].reads == 0
    row = report(control)["observations"][0]
    assert row["terminal"] == "invalid_status" and row["status_code"] is None


@pytest.mark.parametrize("payload,terminal", [(b"<html>bad</html>", "schema_refused"),
    (b"{\"error\":\"bad\"}", "schema_refused"), (b"[]", "valid_empty"),
    (b"[{\"symbol\":\"AAPL\",\"date\":\"2026-10-12\",\"extra\":\"" + KEY.encode() + b"\"}]", "credential_echo_refused"),
    (b"a" * 1048577, "body_refused")])
def test_body_validators_reused_without_retention(control, monkeypatch, payload, terminal):
    code, _adapter = execute(monkeypatch, {0: (200, payload)})
    assert code == (0 if terminal == "valid_empty" else 2)
    assert report(control)["observations"][0]["terminal"] == terminal


def test_response_binding_failure_precedes_body(control, monkeypatch):
    def change(response, index):
        if index == 0:
            response.url = "https://wrong.invalid/"
    code, adapter = execute(monkeypatch, change=change)
    assert code == 2 and adapter.responses[0].reads == 0
    assert report(control)["observations"][0]["terminal"] == "response_binding_refused"


@pytest.mark.parametrize("field,value", [("method", "POST"), ("body", b"unexpected"),
    ("headers", {"Extra": "synthetic"}), ("hooks", {"response": ["synthetic"]})])
def test_mutated_prepared_request_is_refused(control, monkeypatch, field, value):
    def change(response, index):
        if index == 0:
            setattr(response.request, field, value)
    code, adapter = execute(monkeypatch, change=change)
    assert code == 2 and adapter.responses[0].reads == 0
    assert report(control)["observations"][0]["terminal"] == "response_binding_refused"


def test_response_must_reference_exact_prepared_request(control, monkeypatch):
    def change(response, index):
        if index == 0:
            response.request = SimpleNamespace(**vars(response.request))
    code, adapter = execute(monkeypatch, change=change)
    assert code == 2 and adapter.responses[0].reads == 0
    assert report(control)["observations"][0]["terminal"] == "response_binding_refused"


@pytest.mark.parametrize("status", [200, 403])
def test_ordinary_close_failure_stops(control, monkeypatch, status):
    def change(response, index):
        if index == 0:
            response.close = lambda: (_ for _ in ()).throw(OSError("EXAMPLE-SECRET"))
    code, adapter = execute(monkeypatch, {0: (status, body(0))}, change)
    assert code == 2 and len(adapter.calls) == 1
    assert report(control)["terminal"] == "close_refused"


def test_logging_guard_immediately_precedes_send(control, monkeypatch):
    checks = 0
    def guard():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise d.contract.Refusal("control_refused")
    monkeypatch.setattr(d.contract, "_check_transport_logging", guard)
    code, adapter = execute(monkeypatch)
    assert code == 2 and not adapter.calls and checks == 2
    assert report(control)["send_attempt_count"] == 1


def test_partial_marker_prevents_send(control, monkeypatch):
    original = d._write_held
    def write(directory, name, value):
        result = original(directory, name, value)
        if name == "send-2-started.json":
            os.close(result[0])
            raise OSError("synthetic")
        return result
    monkeypatch.setattr(d, "_write_held", write)
    code, adapter = execute(monkeypatch)
    assert code == 2 and len(adapter.calls) == 1
    assert report(control)["terminal"] == "send_intent_ambiguous"


def test_duplicate_claim_no_secret_or_send(control, monkeypatch):
    assert execute(monkeypatch)[0] == 0
    monkeypatch.setattr(d.credentials, "load_key", lambda *_a, **_k: pytest.fail("duplicate credential read"))
    code, adapter = execute(monkeypatch)
    assert code == 2 and not adapter.calls


def test_preflight_refusal_no_allocation(control, monkeypatch):
    monkeypatch.setattr(d, "_preflight", lambda *_: (_ for _ in ()).throw(d.Refusal("control_refused")))
    code, adapter = execute(monkeypatch)
    assert code == 2 and not adapter.calls and not control.exists()


def test_late_publication_exit_is_not_report_success(control, monkeypatch):
    original = d._check_held
    def check(directory, name, fd, identity):
        if name == "report.json":
            raise d.Refusal("control_refused")
        return original(directory, name, fd, identity)
    monkeypatch.setattr(d, "_check_held", check)
    assert execute(monkeypatch)[0] == 2
    assert report(control)["terminal"] == "all_connections_responded"


def test_reader_positive_and_actual_exit_override(control, monkeypatch):
    assert execute(monkeypatch)[0] == 0
    monkeypatch.setattr(d.credentials, "load_key", lambda *_a, **_k: pytest.fail("reader no secret"))
    assert read(control)["connections_responded"] is True
    assert read(control, actual_exit=2)["connections_responded"] is False


@pytest.mark.parametrize("changes", [{"report_sha256": "c" * 64}, {"report_bytes": 1}, {"actual_exit": None},
    {"actual_exit": True}, {"actual_exit": -9}, {"head": "c" * 40}, {"caller": "c" * 64}])
def test_reader_external_bindings(control, monkeypatch, changes):
    assert execute(monkeypatch)[0] == 0
    with pytest.raises((d.Refusal, d.helpers.Refusal)):
        read(control, **changes)


@pytest.mark.parametrize("field,value", [("send_attempt_count", 7), ("send_attempt_count", True),
    ("provider_request_count", 0), ("capture_accepted", True), ("backtest_ready", True),
    ("point_in_time_proven", True), ("paper_look_committed", True), ("qc_calls", True),
    ("outcome_reads", 1), ("observations", []), ("profile_sha256", "c" * 64)])
def test_strict_report(control, monkeypatch, field, value):
    assert execute(monkeypatch)[0] == 0
    claim = d.helpers._decode((control / "claim.json").read_bytes())
    value_map = report(control)
    value_map[field] = value
    with pytest.raises((d.Refusal, d.helpers.Refusal)):
        d._validate(claim, value_map, HEAD, SHA, 0)


@pytest.mark.parametrize("index", range(6))
def test_core_field_presence_required(control, monkeypatch, index):
    assert execute(monkeypatch)[0] == 0
    claim = d.helpers._decode((control / "claim.json").read_bytes())
    value_map = report(control)
    value_map["observations"][index]["fields_available"][d.contract._required_fields(d.ENDPOINTS[index])[0]] = False
    with pytest.raises(d.Refusal):
        d._validate(claim, value_map, HEAD, SHA, 0)


@pytest.mark.parametrize("index", [1, 2, 3, 4])
def test_row_ceiling_matches_producer(control, monkeypatch, index):
    assert execute(monkeypatch)[0] == 0
    claim = d.helpers._decode((control / "claim.json").read_bytes())
    value_map = report(control)
    value_map["observations"][index]["row_count"] = 2
    with pytest.raises(d.Refusal):
        d._validate(claim, value_map, HEAD, SHA, 0)


def configure_preflight(monkeypatch):
    answers = {("rev-parse", "--show-toplevel"): str(d.ROOT), ("branch", "--show-current"): d.BRANCH,
        ("rev-parse", "HEAD"): HEAD, ("status", "--porcelain"): ""}
    monkeypatch.setattr(d.subprocess, "run", lambda command, **kwargs: SimpleNamespace(returncode=0,
        stderr=b"", stdout=(answers[tuple(command[1:])] + "\n").encode()))
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: SHA if path == d.SOURCE
        else d.SOURCE_PINS[str(path.relative_to(d.ROOT))])
    return answers


def test_preflight_good(monkeypatch):
    configure_preflight(monkeypatch)
    d._preflight(HEAD, SHA, time.monotonic() + 180)


@pytest.mark.parametrize("command", [("rev-parse", "--show-toplevel"), ("branch", "--show-current"),
    ("rev-parse", "HEAD"), ("status", "--porcelain")])
def test_preflight_root_branch_head_dirty(monkeypatch, command):
    configure_preflight(monkeypatch)[command] = "wrong"
    with pytest.raises(d.Refusal):
        d._preflight(HEAD, SHA, time.monotonic() + 180)


@pytest.mark.parametrize("relative", list(d.SOURCE_PINS) + ["scripts/check_arv2_remaining_provider_connections.py"])
def test_all_selected_pins(monkeypatch, relative):
    configure_preflight(monkeypatch)
    original = d.helpers._source_digest
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: "c" * 64 if path == d.ROOT / relative else original(path))
    with pytest.raises(d.Refusal):
        d._preflight(HEAD, SHA, time.monotonic() + 180)


@pytest.mark.parametrize("name,value", [("platform", "linux"), ("version_info", (3, 12, 0)), ("executable", "/other/python")])
def test_wrong_host(monkeypatch, name, value):
    with monkeypatch.context() as patch:
        patch.setattr(sys, name, value)
        with pytest.raises(d.Refusal):
            d._preflight(HEAD, SHA, time.monotonic() + 180)


@pytest.mark.parametrize("value", ["", "synthetic"])
def test_ssl_keylog_refuses_without_subprocess(monkeypatch, value):
    monkeypatch.setitem(os.environ, "SSLKEYLOGFILE", value)
    with pytest.raises(d.Refusal):
        d._preflight(HEAD, SHA, time.monotonic() + 180)


def test_deadline_alarm_bounds(monkeypatch):
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
    assert 179 <= bounds[0] <= 180 and 29 <= bounds[1] <= 30


def test_only_allowed_stateless_a_calls():
    allowed = {"_new_adapter", "_check_transport_logging", "_prepare", "_validate_request", "_body_bytes",
        "_schema", "_row", "_row_limit", "_required_fields"}
    tree = ast.parse(d.SOURCE.read_text())
    calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "contract"}
    assert calls <= allowed
    assert d._write_held is d.contract._write_held
    assert all(e.provider != "sharadar" for e in d.ENDPOINTS)
    assert "assistant.dispatch_fence" not in sys.modules
