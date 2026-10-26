"""Synthetic comparative responses; no actual source or credential access."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
import socket
from urllib.parse import parse_qs, urlsplit

import pytest

from research.target_price_revisions_development import raw_market_request_probe as probe

market, detail, prior = probe.market, probe.detail, probe.prior
NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
KEY = "SYNTHETIC_PROBE_KEY"
TICKERS = ("AAATEST", "BBBTEST", "CCCTEST", "DDDTEST")


def original():
    return market.freeze_capture_plan(structure_sha256="a" * 64, waiver_sha256="b" * 64,
        tickers=TICKERS, code_hashes={name: "c" * 64 for name in market.CODE_FILES}, candidate_policy_sha256="d" * 64,
        git_sha="e" * 40, owner_instruction_sha256=market.raw_run.OWNER_WAIVER_INSTRUCTION_SHA256,
        created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode="offline-fixture")


def previous():
    return {"schema": "tpr-raw-market-error-detail-report-v1", "market_plan_sha256": original().sha256,
        "mode": "offline-fixture", "http_status": 400, "status": "EXPLAINED", "plan_sha256": "f" * 64,
        "outcome_reads": 0, "successful_body_reads": 0, "additional_development_looks": 0}


def plan(**changes):
    values = dict(code_sha256="1" * 64, market_plan_sha256=original().sha256,
        detail_report_sha256=market.source._digest(market.source._canonical(previous())), git_sha=detail.HEAD,
        owner_instruction_sha256=detail.OWNER, created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode="offline-fixture")
    values.update(changes)
    return probe.freeze_probe_plan(**values)


@pytest.fixture(autouse=True)
def no_actual_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual provider or credential access in probe fixtures")
    monkeypatch.setattr(probe, "_FIXED_RESOLVER", forbidden)
    monkeypatch.setattr(probe, "_FIXED_TRANSPORT", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def root(tmp_path):
    directory = tmp_path / "probe"
    directory.mkdir(mode=0o700)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        market._reserve(fd, original(), NOW)
        payload = market.source._canonical(previous())
        market.source._publish(fd, detail.DETAIL_ID + "." + market.source._digest(payload) + ".aggregate.json", payload)
        market.source._publish(fd, detail.DETAIL_ID + ".spent.json", market.source._canonical({
            "schema": "tpr-error-detail-spent-v1", "detail_id": detail.DETAIL_ID, "plan_sha256": previous()["plan_sha256"], "started_utc": NOW.isoformat()}))
    finally:
        os.close(fd)
    return directory


def execute(root, statuses=(400, 200), *, frozen=None, resolver=None, transport=None):
    calls = []
    def fetch(inventory, key):
        assert key == KEY
        calls.append(inventory)
        status = statuses[len(calls) - 1]
        return prior.DiagnosticResponse(status, (), b'{"error":{"message":"Invalid ticker parameter"}}' if status >= 400 else b"")
    result = probe._execute_fixture(frozen or plan(), original(), root, now=NOW,
        resolver=resolver or (lambda _: KEY), transport=transport or fetch)
    return result, calls


def test_full_http_400_then_three_success_is_observation_not_limit_proof(root):
    result, calls = execute(root)
    report = json.loads(result.payload)
    assert report["status"] == "PROBED" and calls == [TICKERS, TICKERS[:3]]
    assert [row["http_status"] for row in report["variants"]] == [400, 200]
    assert [row["ticker_count"] for row in report["variants"]] == [4, 3]
    assert report["variants"][0]["error_detail"]["sanitized_error_detail"] == "Invalid ticker parameter"
    assert report["maximum_ticker_limit_established"] is False
    assert report["fixture_transport_calls"] == 2 and report["provider_requests"] == 0
    assert report["additional_development_looks"] == report["outcome_reads"] == report["successful_body_reads"] == report["quantconnect_attempts"] == 0
    assert report["trading"] is report["raw_error_retained"] is report["raw_error_identity_retained"] is False
    assert KEY.encode() not in result.payload and all(t.encode() not in result.payload for t in TICKERS)
    assert result.projection_path is None and not list(root.glob("*.csv"))


@pytest.mark.parametrize("status", [200, 201, 206, 302, 401, 403, 422, 500])
def test_variant_b_only_for_exact_http_400(root, status):
    result, calls = execute(root, (status,))
    report = json.loads(result.payload)
    assert calls == [TICKERS] and report["fixture_transport_calls"] == 1
    assert len(report["variants"]) == 1 and report["variants"][0]["http_status"] == status


def test_two_errors_stop_without_third_request(root):
    result, calls = execute(root, (400, 400))
    assert calls == [TICKERS, TICKERS[:3]] and json.loads(result.payload)["status"] == "PROBED"


def test_claim_precedes_credentials_and_changed_plan_cannot_rearm(root, capsys):
    def resolve(provider):
        assert provider == "sharadar" and (root / (probe.PROBE_ID + ".spent.json")).exists()
        return KEY
    execute(root, (200,), resolver=resolve)
    with pytest.raises(ValueError, match="already spent"):
        execute(root, frozen=plan(code_sha256="2" * 64), resolver=lambda _: pytest.fail("second credential lookup"))
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("status", [200, 206, 302])
def test_literal_comma_transport_preserves_all_other_query_fields_and_never_reads_success(monkeypatch, status):
    requests, closed = [], []
    class Response:
        def getheaders(self):
            return [("content-type", "text/csv")]
        def read(self, _budget):
            pytest.fail("successful or redirect body read")
    Response.status = status
    class Connection:
        def __init__(self, host, port, *, timeout, context):
            assert (host, port, timeout, context.keylog_filename) == ("api.sharadar.com", 443, 30, None)
        def set_debuglevel(self, value):
            assert value == 0
        def request(self, method, path, headers):
            assert method == "GET" and headers["Accept-Encoding"] == "identity"
            assert path.startswith("/v1.0/data/stocks?") and "ticker=" + ",".join(TICKERS) in path
            assert "fields=ticker%2Cdate%2Copen%2Cclose%2Ccloseunadj%2Cvolume" in path
            parsed = parse_qs(urlsplit(path).query)
            assert parsed == {key: [value] for key, value in market.request_query("stocks", 0, TICKERS) + (("api_key", KEY),)}
            requests.append(path)
        def getresponse(self):
            return Response()
        def close(self):
            closed.append(True)
    monkeypatch.setattr(probe.http.client, "HTTPSConnection", Connection)
    response = probe._https_get(TICKERS, KEY)
    assert response.status == status and response.body == b"" and len(requests) == len(closed) == 1


def test_error_transport_bounded_to_8192_and_secret_echo_suppressed(root, monkeypatch):
    class Response:
        status = 400
        def getheaders(self):
            return [("content-type", "application/json")]
        def read(self, budget):
            assert budget == 8192
            return json.dumps({"error": {"message": "Invalid key " + KEY}}).encode()
    class Connection:
        def __init__(self, *_args, **_kwargs):
            pass
        def set_debuglevel(self, _value):
            pass
        def request(self, *_args, **_kwargs):
            pass
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(probe.http.client, "HTTPSConnection", Connection)
    result, _ = execute(root, transport=probe._https_get)
    assert all(row["error_detail"]["suppression"] == "credential_echo" for row in json.loads(result.payload)["variants"])
    assert KEY.encode() not in result.payload


def test_missing_detail_receipt_refuses_before_claim_or_credentials(root):
    (root / (detail.DETAIL_ID + ".spent.json")).unlink()
    with pytest.raises(FileNotFoundError):
        execute(root, resolver=lambda _: pytest.fail("lookup before prior receipt"))
    assert not (root / (probe.PROBE_ID + ".spent.json")).exists()


@pytest.mark.parametrize("mutate", [lambda body: body.update(requests=3), lambda body: body.update(second_variant_only_after_http_400=False),
    lambda body: body.update(successful_body_reads=1), lambda body: body.update(additional_development_looks=1)])
def test_forged_rehashed_policy_refuses_before_claim(root, mutate):
    frozen = plan()
    body = frozen.body()
    mutate(body)
    payload = market.source._canonical(body)
    with pytest.raises(ValueError, match="plan"):
        execute(root, frozen=replace(frozen, payload=payload, sha256=market.source._digest(payload)))
    assert not (root / (probe.PROBE_ID + ".spent.json")).exists()


def test_exception_text_never_enters_terminal_or_report(root):
    def fail(*_args):
        raise RuntimeError("SYNTHETIC_PRIVATE " + KEY)
    result, _ = execute(root, transport=fail)
    assert json.loads(result.payload)["status"] == "FAILED" and json.loads(result.payload)["fixture_transport_calls"] == 1
    assert b"PRIVATE" not in result.payload and KEY.encode() not in result.payload
    assert json.loads(result.terminal_path.read_bytes())["status"] == "FAILED"


def test_exact_production_history_and_public_fixture_refusal():
    values = dict(code_sha256="a" * 64, market_plan_sha256=prior.ORIGINAL_PLAN_SHA256, detail_report_sha256=probe.DETAIL_REPORT,
        git_sha=detail.HEAD, owner_instruction_sha256=detail.OWNER, created_utc=NOW.isoformat(), expires_utc=(NOW + timedelta(hours=24)).isoformat())
    assert probe.freeze_probe_plan(**values).body()["requests"] == 2
    for key in ("git_sha", "market_plan_sha256", "detail_report_sha256"):
        with pytest.raises(ValueError, match="history"):
            probe.freeze_probe_plan(**dict(values, **{key: "f" * len(values[key])}))
    with pytest.raises(ValueError, match="production-only"):
        probe.execute_request_probe(plan(), original())
