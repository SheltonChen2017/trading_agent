"""Synthetic error-only responses; no actual price, secret or provider access."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
import socket

import pytest

from research.target_price_revisions_development import raw_market_diagnostic as diagnostic

market = diagnostic.market
NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
KEY = "SYNTHETIC_DIAGNOSTIC_KEY"


def original():
    return market.freeze_capture_plan(structure_sha256="a" * 64, waiver_sha256="b" * 64,
        tickers=("ZZTEST",), code_hashes={name: "c" * 64 for name in market.CODE_FILES}, candidate_policy_sha256="d" * 64,
        git_sha="e" * 40, owner_instruction_sha256=market.raw_run.OWNER_WAIVER_INSTRUCTION_SHA256,
        created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode="offline-fixture")


def failed_report():
    return {"schema": "tpr-raw-market-capture-report-v1", "market_plan_sha256": original().sha256,
        "candidate_id": market.CANDIDATE_ID, "capture_id": market.CAPTURE_ID, "mode": "offline-fixture", "status": "FAILED",
        "last_http_status": 400, "failure_stage": "response", "projection_sha256": None,
        "native_source_row_counts": {"stocks": 0, "actions": 0}, "response_bytes": 0,
        "provider_requests": 0, "fixture_transport_calls": 1}


def plan(**changes):
    arguments = dict(code_sha256="1" * 64, market_plan_sha256=original().sha256,
        failed_capture_report_sha256=market.source._digest(market.source._canonical(failed_report())), git_sha="e" * 40,
        owner_instruction_sha256=market.raw_run.OWNER_WAIVER_INSTRUCTION_SHA256,
        created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode="offline-fixture")
    arguments.update(changes)
    return diagnostic.freeze_diagnostic_plan(**arguments)


@pytest.fixture(autouse=True)
def no_actual_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual provider or secret access in diagnostic fixtures")
    monkeypatch.setattr(diagnostic, "_production_credential", forbidden)
    monkeypatch.setattr(diagnostic, "_https_get", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def root(tmp_path):
    directory = tmp_path / "diagnostic"
    directory.mkdir(mode=0o700)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        market._reserve(fd, original(), NOW)
        payload = market.source._canonical(failed_report())
        market.source._publish(fd, market.CAPTURE_ID + "." + market.source._digest(payload) + ".aggregate.json", payload)
    finally:
        os.close(fd)
    return directory


def execute(root, *, frozen=None, resolver=None, response=None, fetch=None):
    return diagnostic._execute_fixture_diagnostic(frozen or plan(), original(), root, now=NOW,
        credential_resolver=resolver or (lambda _: KEY),
        transport=fetch or (lambda *_: response or diagnostic.DiagnosticResponse(400, (), b'{"error":"Invalid skip parameter"}')))


def test_one_diagnostic_claim_precedes_credentials_and_never_renews_look(root, capsys):
    def resolver(provider):
        assert provider == "sharadar"
        assert (root / (diagnostic.DIAGNOSTIC_ID + ".spent.json")).exists()
        return KEY
    result = execute(root, resolver=resolver)
    body = json.loads(result.payload)
    assert body["status"] == "DIAGNOSED" and body["http_status"] == 400
    assert body["error"] == {"category": "invalid_parameter", "parameter_names": ["skip"], "error_code": None}
    assert body["additional_development_looks"] == body["outcome_reads"] == body["successful_body_reads"] == body["quantconnect_attempts"] == 0
    assert body["raw_error_retained"] is body["raw_error_identity_retained"] is body["trading"] is False
    assert body["fixture_transport_calls"] == 1 and body["provider_requests"] == 0
    assert all(v not in result.payload for v in (KEY.encode(), b"ZZTEST", b"Invalid skip parameter"))
    assert not list(root.glob("*.csv"))
    with pytest.raises(diagnostic.DiagnosticError, match="already spent"):
        execute(root, frozen=plan(code_sha256="2" * 64), resolver=lambda _: pytest.fail("second lookup"))
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("text,category", [("Invalid ticker limit, too many tickers", "ticker_limit"),
    ("Invalid API key", "authentication"), ("Forbidden subscription entitlement", "entitlement"),
    ("Unsupported sort parameter", "invalid_parameter"), ("Unclassified service error", "unknown_response")])
def test_coarse_categories_never_emit_provider_text(text, category):
    payload = json.dumps({"message": text}).encode()
    reduced = diagnostic.classify_error_body(payload, KEY)
    assert reduced["category"] == category
    assert text not in json.dumps(reduced)


@pytest.mark.parametrize("payload", [KEY.encode(), KEY.replace("_", "%5F").encode(),
    json.dumps({"error": "invalid ticker https://PRIVATE/path?api_key=PRIVATE"}).encode(),
    b'{"message":"Invalid ticker https:\\/\\/PRIVATE/path"}',
    b'{"message":"invalid ticker https%3A%2F%2FPRIVATE"}'])
def test_secret_or_url_echo_suppresses_all_source_labels(payload):
    assert diagnostic.classify_error_body(payload, KEY) == {"category": "echo_suppressed", "parameter_names": [], "error_code": None}


def test_unknown_keys_or_native_row_envelopes_not_interpreted_as_errors():
    assert diagnostic.classify_error_body(b'{"error":"Invalid ticker","results":[{"open":1}]}', KEY)["category"] == "unknown_response"
    reduced = diagnostic.classify_error_body(b'{"error":"Invalid sort","code":"PRIVATE_VALUE"}', KEY)
    assert reduced["error_code"] is None


@pytest.mark.parametrize("status", [200, 201, 302])
def test_owned_transport_never_reads_success_or_redirect_body(monkeypatch, status):
    calls = []
    class Response:
        def getheaders(self):
            return [("content-type", "text/csv")]
        def read(self, _budget):
            pytest.fail("successful/redirect native body was read")
    Response.status = status
    class Connection:
        def __init__(self, host, port, *, timeout, context):
            assert (host, port, timeout, context.keylog_filename) == ("api.sharadar.com", 443, 30, None)
        def set_debuglevel(self, value):
            assert value == 0
        def request(self, method, path, headers):
            assert path.startswith("/v1.0/data/stocks?") and "ticker=ZZTEST" in path
            assert "from=2024-12-31" in path and "skip=0" in path
            assert headers["Accept-Encoding"] == "identity"
        def getresponse(self):
            return Response()
        def close(self):
            calls.append("closed")
    monkeypatch.setattr(diagnostic.http.client, "HTTPSConnection", Connection)
    response = diagnostic._FIXED_TRANSPORT(("ZZTEST",), KEY)
    assert response.body == b"" and response.status == status
    assert calls == ["closed"]


def test_unexpected_success_is_no_body_no_price_permission(root):
    body = json.loads(execute(root, response=diagnostic.DiagnosticResponse(200, (), b"", False)).payload)
    assert body["error"]["category"] == "unexpected_success_without_body"
    assert body["error_response_bytes"] == body["outcome_reads"] == 0


def test_partial_error_bytes_are_counted_without_retention(root):
    raw = b"SYNTHETIC_PARTIAL_ERROR"
    report = json.loads(execute(root, response=diagnostic.DiagnosticResponse(400, (), raw, False)).payload)
    assert report["error_response_bytes"] == len(raw)
    assert report["error"]["category"] == "error_body_refused_or_incomplete"
    assert raw not in market.source._canonical(report)


@pytest.mark.parametrize("mutation", [lambda body: body.update(requests=2), lambda body: body.update(error_bytes=65536),
    lambda body: body.update(successful_body_reads=1), lambda body: body.update(additional_development_looks=1)])
def test_rehashed_scope_change_refuses_before_claim(root, mutation):
    frozen = plan()
    body = frozen.body()
    mutation(body)
    payload = market.source._canonical(body)
    forged = replace(frozen, payload=payload, sha256=market.source._digest(payload))
    with pytest.raises(diagnostic.DiagnosticError):
        execute(root, frozen=forged)
    assert not (root / (diagnostic.DIAGNOSTIC_ID + ".spent.json")).exists()


def test_missing_original_look_refuses_before_diagnostic_claim(root):
    (root / (market.CANDIDATE_ID + ".spent.json")).write_bytes(b"{}\n")
    with pytest.raises(market.MarketCaptureError):
        execute(root, resolver=lambda _: pytest.fail("lookup without original reservation"))
    assert not (root / (diagnostic.DIAGNOSTIC_ID + ".spent.json")).exists()


def test_public_fixture_refuses_without_private_access():
    with pytest.raises(diagnostic.DiagnosticError, match="production-only"):
        diagnostic.execute_diagnostic(plan(), original())


def test_exception_and_interrupt_retained_without_private_values(root):
    def fail(*_):
        raise RuntimeError("PRIVATE_SECRET_" + KEY)
    result = execute(root, fetch=fail)
    assert json.loads(result.payload)["status"] == "FAILED"
    assert b"PRIVATE_SECRET" not in result.payload
    assert json.loads(result.terminal_path.read_bytes())["status"] == "FAILED"


def test_partial_claim_failure_never_resolves_credentials(root, monkeypatch):
    def fail(fd, _payload):
        os.write(fd, b"{")
        raise OSError(KEY)
    monkeypatch.setattr(market.source, "_write_fd", fail)
    result = execute(root, resolver=lambda _: pytest.fail("lookup after partial claim"))
    assert json.loads(result.payload)["failure_stage"] == "claim"
    assert json.loads(result.payload)["fixture_transport_calls"] == 0


def test_production_plan_only_names_actual_failed_operation():
    arguments = dict(code_sha256="a" * 64, market_plan_sha256=diagnostic.ORIGINAL_PLAN_SHA256,
        failed_capture_report_sha256=diagnostic.FAILED_REPORT_SHA256, git_sha="e" * 40,
        owner_instruction_sha256=market.raw_run.OWNER_WAIVER_INSTRUCTION_SHA256,
        created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=24)).isoformat())
    assert diagnostic.freeze_diagnostic_plan(**arguments).body()["successful_body_reads"] == 0
    arguments["market_plan_sha256"] = "f" * 64
    with pytest.raises(diagnostic.DiagnosticError, match="exact failed"):
        diagnostic.freeze_diagnostic_plan(**arguments)
