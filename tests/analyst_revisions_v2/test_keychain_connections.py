"""Synthetic-only Keychain/transport tests. Never touch real credentials."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, quote_plus, urlsplit

import pytest

from tests.analyst_revisions_v2._dispatch_fence_closure import assert_lane_closure_excludes_dispatch_fence

from scripts import arv2_keychain_connections as keys
from scripts import run_arv2_keychain_connection_check as d

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
    monkeypatch.setattr(keys.subprocess, "run", lambda *_a, **_k: pytest.fail("no real subprocess"))
    monkeypatch.setattr(keys, "load_key", lambda *_a, **_k: KEY)
    # Isolate only this synthetic process; operational code refuses unsafe
    # logging rather than altering the caller's configuration.
    safe_root = logging.RootLogger(logging.WARNING)
    monkeypatch.setattr(d, "logging", SimpleNamespace(
        getLogger=lambda name="": logging.getLogger(name) if name else safe_root,
        Logger=logging.Logger, NullHandler=logging.NullHandler, WARNING=logging.WARNING))
    loggers = [logger for name, logger in tuple(logging.Logger.manager.loggerDict.items())
        if isinstance(logger, logging.Logger)
        and (name in {"requests", "urllib3"} or name.startswith(("requests.", "urllib3.")))]
    for logger in loggers:
        monkeypatch.setattr(logger, "handlers", [])
        monkeypatch.setattr(logger, "level", logging.WARNING)


ORIGINAL_LOAD = keys.load_key


@pytest.mark.parametrize("provider", list(keys.SERVICES))
def test_keychain_exact_service_account_path(provider, monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=KEY.encode() + b"\n")
    monkeypatch.setattr(keys.subprocess, "run", run)
    assert ORIGINAL_LOAD(provider, timeout_seconds=12) == KEY
    service, account = keys.SERVICES[provider]
    assert calls == [(["/usr/bin/security", "find-generic-password", "-s", service,
        "-a", account, "-w", "/Users/sheltonchen/Library/Keychains/login.keychain-db"],
        {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL,
         "timeout": 12, "check": False})]


@pytest.mark.parametrize("payload", [b"short\n", b"abcdefgh", b"abcdefgh\n\n", b"abcdefgh\r\n",
    b" abcdefgh\n", b"abcdefgh \n", b"abcdefgh\t\n", b"abcdefgh\0\n", b"abcdefg\x80\n",
    b"a" * 4097 + b"\n", None, "abcdefgh\n"])
def test_keyshape_refuses_without_trimming_arbitrary_whitespace(payload, monkeypatch):
    monkeypatch.setattr(keys.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=payload))
    with pytest.raises(keys.KeychainUnavailable, match="^credentials_unavailable$"):
        ORIGINAL_LOAD("fmp", timeout_seconds=20)


@pytest.mark.parametrize("length", [8, 4096])
def test_key_length_boundaries(length, monkeypatch):
    monkeypatch.setattr(keys.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=b"a" * length + b"\n"))
    assert ORIGINAL_LOAD("fmp", timeout_seconds=1) == "a" * length


@pytest.mark.parametrize("provider,timeout", [("other", 1), (None, 1), (True, 1), ("fmp", 0),
    ("fmp", 21), ("fmp", True), ("fmp", float("nan")), ("fmp", float("inf")), ("fmp", "1")])
def test_invalid_key_request_never_dispatches(provider, timeout):
    with pytest.raises(keys.KeychainUnavailable):
        ORIGINAL_LOAD(provider, timeout_seconds=timeout)


@pytest.mark.parametrize("outcome", [1, True, "0", -9, subprocess.TimeoutExpired("EXAMPLE-SECRET", 1,
    output=b"EXAMPLE-SECRET"), RuntimeError("EXAMPLE-SECRET")])
def test_keychain_failure_not_formatted_or_fallback(outcome, monkeypatch, capsys):
    def run(*_a, **_k):
        if isinstance(outcome, BaseException):
            raise outcome
        return SimpleNamespace(returncode=outcome, stdout=b"EXAMPLE-SECRET\n")
    monkeypatch.setattr(keys.subprocess, "run", run)
    monkeypatch.setitem(os.environ, "FMP_API_KEY", "EXAMPLE-FALLBACK-SECRET")
    with pytest.raises(keys.KeychainUnavailable) as caught:
        ORIGINAL_LOAD("fmp", timeout_seconds=1)
    assert caught.value.args == ("credentials_unavailable",)
    assert caught.value.__suppress_context__ is True
    assert capsys.readouterr().out == ""


def payload(index):
    if index == 0:
        return [{"symbol": "AAPL", "date": "2026-10-12", "gradingCompany": "Fixture Firm",
            "previousGrade": "Hold", "newGrade": "Buy", "action": "upgrade"}]
    if index in {1, 2, 3}:
        return {"status": "OK", "results": [{"ticker": "AAPL", "date": "2026-10-12"}]}
    if index == 4:
        return [{"date": "2026-10-12", "open": 100, "high": 110, "low": 90,
            "close": 101, "adjusted_close": 100, "volume": 10000}]
    if index == 5:
        return {"type": "Earnings", "symbols": "AAPL.US", "earnings": [{"code": "AAPL.US",
            "report_date": "2026-07-30", "date": "2026-06-30", "actual": 1.5,
            "estimate": 1.4, "difference": .1, "percent": 7.14}]}
    return b"ticker,permaticker\nAAPL,1980\n"


def encoded(value):
    return value if type(value) is bytes else json.dumps(value).encode()


class FakeRaw:
    def __init__(self, body):
        self.body = body
        self.reads = 0

    def stream(self, **kwargs):
        assert kwargs == {"amt": 16384, "decode_content": False}
        self.reads += 1
        for start in range(0, len(self.body), 16384):
            yield self.body[start:start + 16384]


class FakeResponse:
    def __init__(self, request, status, body, index):
        self.request = request
        self.url = request.url
        self.status_code = status
        self.headers = {"Content-Type": "text/csv" if index == 6 else "application/json"}
        self.raw = FakeRaw(encoded(body))
        self.closed = 0

    def close(self):
        self.closed += 1

    @property
    def content(self):
        pytest.fail("response convenience body APIs forbidden")

    text = json = content


class FakeAdapter:
    def __init__(self, outcomes=None, change=None):
        self.outcomes = outcomes or {}
        self.change = change
        self.calls = []
        self.responses = []
        self.closed = 0

    def send(self, request, **kwargs):
        index = next(index for index, e in enumerate(d.ENDPOINTS)
            if request.url.startswith(e.origin + e.path + "?"))
        self.calls.append((index, request, kwargs))
        status, body = self.outcomes.get(index, (200, payload(index)))
        if isinstance(status, BaseException):
            raise status
        response = FakeResponse(request, status, body, index)
        self.responses.append(response)
        if self.change:
            self.change(response, index)
        return response

    def close(self):
        self.closed += 1


@pytest.fixture
def private_control(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    target = tmp_path / "R296-SYNTHETIC"
    monkeypatch.setattr(d, "CONTROL", target)
    monkeypatch.setattr(d.capture, "_require_operational_artifact_scope", lambda _: None)
    monkeypatch.setattr(d, "_preflight", lambda *_: None)
    return target


def execute(monkeypatch, outcomes=None, change=None):
    adapter = FakeAdapter(outcomes, change)
    monkeypatch.setattr(d, "_new_adapter", lambda: adapter)
    result = d._run(HEAD, SHA, time.monotonic() + 180)
    return result, adapter


def read_report(control):
    return d.helpers._decode((control / "report.json").read_bytes())


def test_all_seven_connections_one_key_each_no_rows_retained(private_control, monkeypatch, capsys):
    reads = []
    def load(provider, **kwargs):
        assert (private_control / "claim.json").is_file()
        assert (private_control / "observation-started.json").is_file()
        reads.append(provider)
        assert 0 < kwargs["timeout_seconds"] <= 20
        return KEY
    monkeypatch.setattr(keys, "load_key", load)
    code, adapter = execute(monkeypatch)
    assert code == 0 and len(adapter.calls) == 7 and adapter.closed == 1
    assert reads == ["fmp", "massive", "eodhd", "sharadar"]
    report = read_report(private_control)
    assert report["terminal"] == "all_connections_responded"
    assert report["send_attempt_count"] == 7 and report["provider_request_count"] is None
    assert report["capture_accepted"] is report["point_in_time_proven"] is report["backtest_ready"] is False
    assert all(row["terminal"] == "valid_nonempty" and row["row_count"] == 1 for row in report["observations"])
    for index, request, kwargs in adapter.calls:
        endpoint = d.ENDPOINTS[index]
        query = dict(endpoint.query)
        if endpoint.auth_query:
            query[endpoint.auth_query] = KEY
        assert parse_qs(urlsplit(request.url).query) == {key: [value] for key, value in query.items()}
        assert dict(request.headers) == ({} if endpoint.auth_query else {"Authorization": "Bearer " + KEY})
        assert kwargs == {"stream": True, "verify": True, "cert": None, "proxies": {}, "timeout": 15}
    assert all(response.closed == 1 for response in adapter.responses)
    assert sorted(path.name for path in private_control.iterdir()) == ["claim.json", "observation-started.json",
        "report.json", *[f"send-{index}-started.json" for index in range(1, 8)]]
    out = capsys.readouterr()
    assert out.err == "" and out.out.endswith("\n\n")
    assert KEY not in out.out and "Fixture Firm" not in out.out
    for path in private_control.iterdir():
        assert KEY.encode() not in path.read_bytes() and b"Fixture Firm" not in path.read_bytes()


@pytest.mark.parametrize("provider", list(keys.SERVICES))
def test_key_refusal_no_fallback_other_providers_continue(private_control, monkeypatch, provider):
    reads = []
    def load(name, **_kwargs):
        reads.append(name)
        if name == provider:
            raise keys.KeychainUnavailable("credentials_unavailable")
        return KEY
    monkeypatch.setattr(keys, "load_key", load)
    code, adapter = execute(monkeypatch)
    assert code == 2 and reads.count(provider) == 1
    report = read_report(private_control)
    assert report["terminal"] == "completed_with_failures"
    for row in report["observations"]:
        assert row["terminal"] == ("credentials_unavailable" if row["provider"] == provider else "valid_nonempty")
    assert all(d.ENDPOINTS[index].provider != provider for index, *_ in adapter.calls)


@pytest.mark.parametrize("status", [100, 199, 201, 204, 301, 302, 307, 308, 400, 401, 403, 404, 429, 500, 599])
def test_non200_never_reads_body_redirects_or_retries(private_control, monkeypatch, status):
    code, adapter = execute(monkeypatch, {1: (status, b"SECRET-FAILED-BODY")})
    assert code == 2 and len(adapter.calls) == 7
    row = read_report(private_control)["observations"][1]
    assert row["terminal"] == "http_status" and row["status_code"] == status
    assert adapter.responses[1].raw.reads == 0
    assert adapter.responses[1].closed == 1


@pytest.mark.parametrize("status", [None, True, False, 200.0, "200", -1, 0, 99, 600, {}, []])
def test_invalid_status_never_retained(private_control, monkeypatch, status):
    code, adapter = execute(monkeypatch, {0: (status, [])})
    assert code == 2 and len(adapter.calls) == 7
    row = read_report(private_control)["observations"][0]
    assert row["status_code"] is None and row["terminal"] == "invalid_status"
    assert adapter.responses[0].raw.reads == 0


@pytest.mark.parametrize("index", range(7))
def test_transport_failure_no_retry_continues_exact_matrix(private_control, monkeypatch, capsys, index):
    code, adapter = execute(monkeypatch, {index: (RuntimeError("EXAMPLE-SECRET"), None)})
    assert code == 2 and len(adapter.calls) == 7
    row = read_report(private_control)["observations"][index]
    assert row["terminal"] == "transport_failure" and row["status_code"] is None
    assert "EXAMPLE-SECRET" not in capsys.readouterr().out


@pytest.mark.parametrize("index", range(7))
def test_empty_responses_connection_not_usable_capture(private_control, monkeypatch, index):
    value = payload(index)
    if index == 6:
        value = b"ticker,permaticker\n"
    elif type(value) is list:
        value = []
    else:
        value["earnings" if index == 5 else "results"] = []
    code, _ = execute(monkeypatch, {index: (200, value)})
    assert code == 0
    row = read_report(private_control)["observations"][index]
    assert row["terminal"] == "valid_empty" and row["row_count"] == 0
    assert not any(row["fields_available"].values())


@pytest.mark.parametrize("body", [b"<html>bad</html>", b"", b"{}", b"{\"error\":\"bad\"}",
    b"[{\"symbol\":\"AAPL\",\"symbol\":\"AAPL\"}]", b"[NaN]", b"[Infinity]", b"[] trailing",
    b"null", b"true", b"[1]", b"[{}]", b"\xff"])
def test_invalid_schema_not_success(private_control, monkeypatch, body):
    code, _ = execute(monkeypatch, {0: (200, body)})
    assert code == 2
    row = read_report(private_control)["observations"][0]
    assert row["terminal"] in {"body_refused", "schema_refused"}
    assert row["row_count"] is None and not any(row["fields_available"].values())


@pytest.mark.parametrize("index", [0, 1, 2, 3, 5])
def test_nullable_optional_fields_are_coverage_not_authentication_failure(index):
    value = payload(index)
    row = value[0] if index == 0 else value["earnings" if index == 5 else "results"][0]
    optional = "action" if index == 0 else "actual" if index == 5 else "time"
    row[optional] = None
    count, fields = d._schema(d.ENDPOINTS[index], encoded(value), KEY)
    assert count == 1 and fields[optional] is False


@pytest.mark.parametrize("index", range(7))
def test_wrong_symbol_rejected(index):
    value = payload(index)
    if index == 6:
        value = b"ticker,permaticker\nMSFT,123\n"
    elif index == 4:
        value[0]["date"] = "2026-10-09"
    else:
        row = value[0] if index == 0 else value["earnings" if index == 5 else "results"][0]
        row["symbol" if index == 0 else "code" if index == 5 else "ticker"] = "OTHER"
    with pytest.raises(d.Refusal):
        d._schema(d.ENDPOINTS[index], encoded(value), KEY)


@pytest.mark.parametrize("field,value", [("report_date", "2026-06-30"), ("report_date", "2026-10-01"),
    ("report_date", "2026-02-30"), ("date", "not-a-date"), ("actual", True), ("estimate", "wrong")])
def test_calendar_window_and_nullable_numbers(field, value):
    value_map = payload(5)
    value_map["earnings"][0][field] = value
    with pytest.raises(d.Refusal):
        d._schema(d.ENDPOINTS[5], encoded(value_map), KEY)


@pytest.mark.parametrize("value", [True, None, "101", -1, 0])
def test_price_numbers_strict(value):
    value_map = payload(4)
    value_map[0]["close"] = value
    with pytest.raises(d.Refusal):
        d._schema(d.ENDPOINTS[4], encoded(value_map), KEY)


@pytest.mark.parametrize("body", [b"ticker,id\nAAPL,123\n", b"ticker,permaticker\nAAPL,\n",
    b"ticker,permaticker\nAAPL,123\nAAPL,123\n", b"ticker,permaticker\nAAPL,123,extra\n",
    b"ticker,permaticker\nAAPL,12 34\n"])
def test_sharadar_csv_shape(body):
    with pytest.raises(d.Refusal):
        d._schema(d.ENDPOINTS[6], body, KEY)


@pytest.mark.parametrize("encoded_key", [KEY, "".join("\\u%04x" % ord(char) for char in KEY)])
def test_credential_echo_rejected_without_output(private_control, monkeypatch, capsys, encoded_key):
    body = ('[{"symbol":"AAPL","date":"2026-10-12","extra":"' + encoded_key + '"}]').encode()
    code, _ = execute(monkeypatch, {0: (200, body)})
    assert code == 2
    assert read_report(private_control)["observations"][0]["terminal"] == "credential_echo_refused"
    assert KEY not in capsys.readouterr().out


@pytest.mark.parametrize("header,value", [("Content-Encoding", "gzip"), ("Content-Type", "text/html"),
    ("Content-Length", "1048577"), ("Content-Length", "0"), ("Content-Length", "wrong"),
    ("Content-Length", "1")])
def test_body_headers_bounded(private_control, monkeypatch, header, value):
    def change(response, index):
        if index == 0:
            response.headers[header] = value
    code, _ = execute(monkeypatch, change=change)
    assert code == 2 and read_report(private_control)["observations"][0]["terminal"] == "body_refused"


def test_stream_ceiling_without_retention(private_control, monkeypatch):
    code, _ = execute(monkeypatch, {0: (200, b"a" * (d.MAX_BODY_BYTES + 1))})
    assert code == 2
    assert read_report(private_control)["observations"][0]["terminal"] == "body_refused"


@pytest.mark.parametrize("mutation", ["response_url", "response_request", "method", "body", "headers", "hooks", "request_url"])
def test_transport_binding_refused(private_control, monkeypatch, mutation):
    def change(response, index):
        if index:
            return
        if mutation == "response_url":
            response.url += "&bad=1"
        elif mutation == "response_request":
            response.request = SimpleNamespace()
        else:
            setattr(response.request, {"request_url": "url"}.get(mutation, mutation), {
                "method": "POST", "body": b"x", "headers": {"Other": "x"},
                "hooks": {"response": [lambda: None]}, "request_url": "https://other.invalid",
            }[mutation])
    code, adapter = execute(monkeypatch, change=change)
    assert code == 2 and len(adapter.calls) == 7
    assert read_report(private_control)["observations"][0]["terminal"] == "response_binding_refused"
    assert adapter.responses[0].raw.reads == 0


def test_marker_failure_stops_before_send(private_control, monkeypatch):
    original = d._write_held
    def write(directory, name, value):
        result = original(directory, name, value)
        if name == "send-2-started.json":
            os.close(result[0])
            raise OSError("EXAMPLE-SECRET")
        return result
    monkeypatch.setattr(d, "_write_held", write)
    code, adapter = execute(monkeypatch)
    assert code == 2 and len(adapter.calls) == 1
    report = read_report(private_control)
    assert report["terminal"] == "send_intent_ambiguous" and report["send_attempt_count"] == 1
    assert report["observations"][1]["terminal"] == "send_intent_ambiguous"
    assert all(row["terminal"] == "not_attempted" for row in report["observations"][2:])


def test_duplicate_claim_no_key_or_network(private_control, monkeypatch, capsys):
    code, _ = execute(monkeypatch)
    assert code == 0
    capsys.readouterr()
    monkeypatch.setattr(keys, "load_key", lambda *_a, **_k: pytest.fail("no second key read"))
    code, adapter = execute(monkeypatch)
    assert code == 2 and not adapter.calls
    assert d.helpers._decode(capsys.readouterr().out[:-1].encode())["terminal"] == "claim_ambiguous"


def test_preflight_refusal_no_allocation(private_control, monkeypatch, capsys):
    monkeypatch.setattr(d, "_preflight", lambda *_: (_ for _ in ()).throw(ValueError("EXAMPLE-SECRET")))
    code, adapter = execute(monkeypatch)
    assert code == 2 and not private_control.exists() and not adapter.calls
    assert "EXAMPLE-SECRET" not in capsys.readouterr().out


def test_early_deadline_stops_matrix(private_control, monkeypatch):
    code, adapter = execute(monkeypatch, {1: (d.helpers.Deadline(), None)})
    assert code == 2 and len(adapter.calls) == 2
    report = read_report(private_control)
    assert report["terminal"] == "deadline_timeout"
    assert all(row["terminal"] == "not_attempted" for row in report["observations"][2:])


@pytest.mark.parametrize("status", [200, 403])
def test_response_close_failure_stops_later_endpoints(private_control, monkeypatch, status):
    def change(response, index):
        if index == 0:
            response.close = lambda: (_ for _ in ()).throw(OSError("EXAMPLE-SECRET"))
    code, adapter = execute(monkeypatch, {0: (status, payload(0))}, change)
    assert code == 2 and len(adapter.calls) == 1
    assert read_report(private_control)["terminal"] == "close_refused"


def test_postprepare_control_failure_stops(private_control, monkeypatch):
    original = d._check_held
    calls = 0
    def check(*args):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise d.Refusal("control_refused")
        return original(*args)
    monkeypatch.setattr(d, "_check_held", check)
    code, adapter = execute(monkeypatch)
    assert code == 2 and not adapter.calls
    assert read_report(private_control)["terminal"] == "control_refused"


def test_final_publication_failure_actual_exit_nonzero(private_control, monkeypatch, capsys):
    original = d._check_held
    def check(directory, name, fd, identity):
        if name == "report.json":
            raise d.Refusal("control_refused")
        return original(directory, name, fd, identity)
    monkeypatch.setattr(d, "_check_held", check)
    code, _ = execute(monkeypatch)
    assert code == 2 and read_report(private_control)["terminal"] == "all_connections_responded"
    assert "publication_ambiguous" in capsys.readouterr().out


def synthetic_read(control, actual_exit=0, **overrides):
    raw = (control / "report.json").read_bytes()
    args = dict(expected_head=HEAD, caller_sha256=SHA, report_sha256=hashlib.sha256(raw).hexdigest(),
        report_bytes=len(raw), actual_exit=actual_exit)
    args.update(overrides)
    return d.read_output(**args)


def test_reader_authenticates_only_new_claim_report(private_control, monkeypatch):
    assert execute(monkeypatch)[0] == 0
    monkeypatch.setattr(keys, "load_key", lambda *_a, **_k: pytest.fail("reader no secret"))
    monkeypatch.setattr(d, "_new_adapter", lambda: pytest.fail("reader no network"))
    summary = synthetic_read(private_control)
    assert summary["output_authenticated"] is summary["connections_responded"] is True
    assert summary["capture_accepted"] is summary["backtest_ready"] is False


def test_reader_actual_exit_overrides_positive_report(private_control, monkeypatch):
    assert execute(monkeypatch)[0] == 0
    summary = synthetic_read(private_control, actual_exit=2)
    assert summary["output_authenticated"] is True and summary["connections_responded"] is False


@pytest.mark.parametrize("overrides", [{"report_sha256": "c" * 64}, {"report_bytes": 1},
    {"actual_exit": None}, {"actual_exit": True}, {"actual_exit": -9}, {"expected_head": "c" * 40},
    {"caller_sha256": "c" * 64}, {"report_bytes": True}])
def test_reader_external_bindings_required(private_control, monkeypatch, overrides):
    assert execute(monkeypatch)[0] == 0
    with pytest.raises((d.Refusal, d.helpers.Refusal)):
        synthetic_read(private_control, **overrides)


@pytest.mark.parametrize("field,value", [("provider_request_count", 0), ("capture_accepted", True),
    ("point_in_time_proven", True), ("backtest_ready", True), ("qc_calls", True),
    ("outcome_reads", 1), ("send_attempt_count", True), ("send_attempt_count", 6),
    ("observations", []), ("terminal", "accepted"), ("profile_sha256", "c" * 64),
    ("parent_observed_terminal_at", "2020-01-01T00:00:00.000000Z")])
def test_report_strict_fields(private_control, monkeypatch, field, value):
    assert execute(monkeypatch)[0] == 0
    claim = d.helpers._decode((private_control / "claim.json").read_bytes())
    report = read_report(private_control)
    report[field] = value
    with pytest.raises((d.Refusal, d.helpers.Refusal)):
        d._validate(claim, report, HEAD, SHA, 0)


@pytest.mark.parametrize("field,value", [("role", "other"), ("provider", "other"),
    ("status_code", True), ("send_intent_recorded", False), ("row_count", True),
    ("row_count", 0), ("fields_available", {}), ("terminal", "http_status"),
    ("endpoint_path", "https://secret.invalid")])
def test_report_rows_strict(private_control, monkeypatch, field, value):
    assert execute(monkeypatch)[0] == 0
    claim = d.helpers._decode((private_control / "claim.json").read_bytes())
    report = read_report(private_control)
    report["observations"][0][field] = value
    with pytest.raises((d.Refusal, d.helpers.Refusal)):
        d._validate(claim, report, HEAD, SHA, 0)


@pytest.mark.parametrize("value", ["", "synthetic-path"])
def test_keylog_environment_refuses_before_any_subprocess_or_transport(monkeypatch, value):
    monkeypatch.setitem(os.environ, "SSLKEYLOGFILE", value)
    with pytest.raises(d.Refusal):
        d._preflight(HEAD, SHA, time.monotonic() + 180)
    with pytest.raises(d.Refusal):
        d._new_adapter()


def test_direct_adapter_does_not_create_session(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "Session", lambda: pytest.fail("no Session"))
    adapter = d._new_adapter()
    try:
        assert adapter.max_retries.total == 0
    finally:
        adapter.close()


def test_wrong_requests_version_refuses(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "__version__", "wrong")
    with pytest.raises(d.Refusal):
        d._new_adapter()


def test_parent_and_reader_alarm_boundaries(monkeypatch):
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


def test_no_dispatch_fence_imported():
    assert_lane_closure_excludes_dispatch_fence()


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(2)])
@pytest.mark.parametrize("stage", ["key", "send", "body", "schema", "close"])
def test_cancellation_stops_all_later_provider_requests(private_control, monkeypatch, error, stage):
    outcomes = None
    change = None
    def stop(*_args, **_kwargs):
        raise error
    if stage == "key":
        monkeypatch.setattr(keys, "load_key", stop)
    elif stage == "send":
        outcomes = {0: (error, None)}
    elif stage == "body":
        monkeypatch.setattr(d, "_body_bytes", stop)
    elif stage == "schema":
        monkeypatch.setattr(d, "_schema", stop)
    elif stage == "close":
        change = lambda response, _index: setattr(response, "close", stop)
    code, adapter = execute(monkeypatch, outcomes, change)
    assert code == 2 and len(adapter.calls) == (0 if stage == "key" else 1)
    report = read_report(private_control)
    assert report["terminal"] == "cancelled"
    assert all(row["terminal"] == "not_attempted" for row in report["observations"][1:])
    assert synthetic_read(private_control, actual_exit=2)["connections_responded"] is False


@pytest.mark.parametrize("index", [1, 2, 3, 4, 6])
def test_reader_same_endpoint_row_ceiling_as_producer(private_control, monkeypatch, index):
    assert execute(monkeypatch)[0] == 0
    claim = d.helpers._decode((private_control / "claim.json").read_bytes())
    report = read_report(private_control)
    report["observations"][index]["row_count"] = 2
    with pytest.raises(d.Refusal):
        d._validate(claim, report, HEAD, SHA, 0)


def test_sharadar_bom_and_exact_header():
    count, fields = d._schema(d.ENDPOINTS[6], b"\xef\xbb\xbfticker,permaticker\nAAPL,123\n", KEY)
    assert count == 1 and all(fields.values())


def test_fields_available_is_non_null_presence_not_economic_usability():
    value = payload(0)
    value[0]["action"] = ""
    assert d._schema(d.ENDPOINTS[0], encoded(value), KEY)[1]["action"] is True


def configured_preflight(monkeypatch):
    answers = {("rev-parse", "--show-toplevel"): str(d.ROOT),
        ("branch", "--show-current"): d.BRANCH, ("rev-parse", "HEAD"): HEAD,
        ("status", "--porcelain"): ""}
    calls = []
    def git(command, **kwargs):
        calls.append(command)
        assert kwargs["cwd"] == d.ROOT and kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["capture_output"] is True and 0 < kwargs["timeout"] <= 3
        return SimpleNamespace(returncode=0, stderr=b"", stdout=(answers[tuple(command[1:])] + "\n").encode())
    monkeypatch.setattr(d.subprocess, "run", git)
    def digest(path):
        return SHA if path == d.SOURCE else d.SOURCE_PINS[str(path.relative_to(d.ROOT))]
    monkeypatch.setattr(d.helpers, "_source_digest", digest)
    return answers, calls


def test_preflight_exact_clean_host_and_pins(monkeypatch):
    _answers, calls = configured_preflight(monkeypatch)
    d._preflight(HEAD, SHA, time.monotonic() + 180)
    assert len(calls) == 4


@pytest.mark.parametrize("command", [("rev-parse", "--show-toplevel"), ("branch", "--show-current"),
    ("rev-parse", "HEAD"), ("status", "--porcelain")])
def test_preflight_wrong_root_branch_head_or_dirty_refuses(monkeypatch, command):
    answers, _calls = configured_preflight(monkeypatch)
    answers[command] = "wrong"
    with pytest.raises(d.Refusal):
        d._preflight(HEAD, SHA, time.monotonic() + 180)


@pytest.mark.parametrize("attribute,value", [("platform", "linux"), ("version_info", (3, 12, 0)),
    ("executable", "/other/python")])
def test_preflight_wrong_platform_runtime_or_executable_refuses(monkeypatch, attribute, value):
    configured_preflight(monkeypatch)
    with monkeypatch.context() as patch:
        patch.setattr(sys, attribute, value)
        with pytest.raises(d.Refusal):
            d._preflight(HEAD, SHA, time.monotonic() + 180)


def test_preflight_wrong_cwd_refuses_before_git(monkeypatch):
    _answers, calls = configured_preflight(monkeypatch)
    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: Path("/not-the-designated-root")))
    with pytest.raises(d.Refusal):
        d._preflight(HEAD, SHA, time.monotonic() + 180)
    assert not calls


@pytest.mark.parametrize("path", list(d.SOURCE_PINS) + ["scripts/run_arv2_keychain_connection_check.py"])
def test_every_selected_source_pin_enforced(monkeypatch, path):
    configured_preflight(monkeypatch)
    original = d.helpers._source_digest
    monkeypatch.setattr(d.helpers, "_source_digest", lambda p: "c" * 64 if p == d.ROOT / path else original(p))
    with pytest.raises(d.Refusal):
        d._preflight(HEAD, SHA, time.monotonic() + 180)


def test_direct_adapter_uses_stream_no_redirect_preload_or_decode(monkeypatch):
    import requests
    adapter = d._new_adapter()
    calls = []
    class Pool:
        def urlopen(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(status=302, headers={"location": "https://other.invalid"},
                reason="fixture", _original_response=None)
    pool = Pool()
    monkeypatch.setattr(adapter, "get_connection_with_tls_context", lambda *_a, **_k: pool)
    monkeypatch.setattr(adapter, "cert_verify", lambda _conn, _url, verify, cert: (
        pytest.fail("TLS settings changed") if verify is not True or cert is not None else None))
    request, _url = d._prepare(d.ENDPOINTS[0], KEY)
    response = adapter.send(request, stream=True, verify=True, cert=None, proxies={}, timeout=15)
    assert response.status_code == 302 and response.request is request
    assert len(calls) == 1
    assert calls[0]["redirect"] is False and calls[0]["preload_content"] is False
    assert calls[0]["decode_content"] is False and calls[0]["retries"].total == 0
    adapter.close()


@pytest.mark.parametrize("target", ["", "requests", "urllib3", "urllib3.connectionpool", "requests.packages.urllib3"])
@pytest.mark.parametrize("unsafe", ["handler", "level"])
def test_unsafe_logging_refused_without_settings_change(monkeypatch, target, unsafe):
    logger = d.logging.getLogger(target)
    handler = logging.StreamHandler()
    monkeypatch.setattr(logger, "level", logging.DEBUG if unsafe == "level" else logging.WARNING)
    monkeypatch.setattr(logger, "handlers", [handler] if unsafe == "handler" else [])
    before = (logger.level, tuple(logger.handlers))
    with pytest.raises(d.Refusal):
        d._new_adapter()
    assert (logger.level, tuple(logger.handlers)) == before


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("level", [True, 1])
def test_http_debug_printing_refused(monkeypatch, index, level):
    import http.client
    import urllib3.connection
    classes = (http.client.HTTPConnection, http.client.HTTPSConnection,
        urllib3.connection.HTTPConnection, urllib3.connection.HTTPSConnection)
    monkeypatch.setattr(classes[index], "debuglevel", level)
    with pytest.raises(d.Refusal):
        d._new_adapter()
    assert classes[index].debuglevel == level


def test_exact_nullhandler_allowed_subclass_refused(monkeypatch):
    logger = logging.getLogger("urllib3")
    monkeypatch.setattr(logger, "handlers", [logging.NullHandler()])
    d._check_transport_logging()
    class NotActuallyNull(logging.NullHandler):
        pass
    monkeypatch.setattr(logger, "handlers", [NotActuallyNull()])
    with pytest.raises(d.Refusal):
        d._check_transport_logging()


def test_new_debug_configuration_before_send_refuses_without_dispatch(private_control, monkeypatch):
    original = d._write_held
    logger = logging.getLogger("urllib3.connectionpool")
    def write(directory, name, value):
        result = original(directory, name, value)
        if name == "send-1-started.json":
            monkeypatch.setattr(logger, "level", logging.DEBUG)
        return result
    monkeypatch.setattr(d, "_write_held", write)
    code, adapter = execute(monkeypatch)
    assert code == 2 and not adapter.calls
    report = read_report(private_control)
    assert report["terminal"] == "control_refused" and report["send_attempt_count"] == 1


@pytest.mark.parametrize("encoding", [quote, quote_plus])
@pytest.mark.parametrize("lower", [False, True])
def test_percent_encoded_key_echo_refused(encoding, lower):
    key = "SYNTHETIC+PUNCTUATION/KEY"
    echo = encoding(key, safe="")
    if lower:
        echo = echo.lower()
    value = payload(0)
    value[0]["extra"] = "https://example.invalid/?apikey=" + echo
    with pytest.raises(d.Refusal, match="credential_echo_refused"):
        d._schema(d.ENDPOINTS[0], encoded(value), key)


@pytest.mark.parametrize("index", range(7))
@pytest.mark.parametrize("terminal", ["valid_nonempty", "close_refused", "deadline_timeout", "cancelled"])
def test_reader_requires_producer_mandatory_presence(private_control, monkeypatch, index, terminal):
    assert execute(monkeypatch)[0] == 0
    claim = d.helpers._decode((private_control / "claim.json").read_bytes())
    report = read_report(private_control)
    row = report["observations"][index]
    row["terminal"] = terminal
    if terminal != "valid_nonempty":
        report["terminal"] = terminal
    row["fields_available"][d._required_fields(d.ENDPOINTS[index])[0]] = False
    with pytest.raises(d.Refusal):
        d._validate(claim, report, HEAD, SHA, 2)


def test_each_request_carries_only_its_own_providers_key(private_control, monkeypatch):
    # Section 301 (ARV2R301-009): distinct synthetic keys per provider prove the key
    # is reloaded on every provider change and never sent to another provider's host.
    keys_by_provider = {provider: f"SYNTHETIC-{provider.upper()}-NOT-A-CREDENTIAL"
                        for provider in keys.SERVICES}
    monkeypatch.setattr(keys, "load_key", lambda provider, **_kwargs: keys_by_provider[provider])
    code, adapter = execute(monkeypatch)
    assert code == 0 and len(adapter.calls) == 7
    for index, request, _kwargs in adapter.calls:
        endpoint = d.ENDPOINTS[index]
        own = keys_by_provider[endpoint.provider]
        carried = request.url + json.dumps(dict(request.headers))
        assert own in carried
        assert not any(other in carried for provider, other in keys_by_provider.items()
                       if provider != endpoint.provider)
