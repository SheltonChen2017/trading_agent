"""Source-audit safety contracts use synthetic bytes and explicit offline mode."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
from types import SimpleNamespace
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from research.target_price_revisions_development import source_audit as audit

_FIXED_TRANSPORT = audit._https_get


@pytest.fixture(autouse=True)
def refuse_actual_credentials_and_network(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual credential or network operation in offline source-audit tests")
    monkeypatch.setattr(audit, "_production_credential", forbidden)
    monkeypatch.setattr(audit, "_https_get", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


NOW = datetime(2026, 10, 6, 18, tzinfo=timezone.utc)
KEYS = {"massive": "SYNTHETIC_MASSIVE_KEY_ONLY", "sharadar": "SYNTHETIC_SHARADAR_KEY_ONLY"}
MASSIVE = {"status": "OK", "results": [{"price_target": "SYNTHETIC-PRIVATE-TARGET",
            "previous_price_target": 10, "date": "2025-01-02", "time": "12:00:00",
            "currency": "USD", "firm_id": "SYNTHETIC-PRIVATE-FIRM",
            "unknown_private_field": "DO-NOT-PUBLISH-UNKNOWN"}],
           "next_url": "https://api.massive.com/benzinga/v1/ratings?cursor=SYNTHETIC-CURSOR"}
SHARADAR = {"table": "tickers", "name": "SYNTHETIC-private.csv.zip", "size": 1234,
            "sizeLabel": "SYNTHETIC-size-label", "modified": "2025-01-02T00:00:00Z"}


def encoded(body):
    return json.dumps(body, separators=(",", ":")).encode()


def plan(mode="offline-fixture", **kwargs):
    args = dict(code_sha256="1" * 64, git_sha="2" * 40,
                owner_instruction_sha256="3" * 64, created_utc=NOW.isoformat(),
                expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode=mode)
    args.update(kwargs)
    return audit.freeze_audit_plan(**args)


@pytest.fixture
def private_root(tmp_path):
    root = tmp_path / "private-source-audit"
    root.mkdir(mode=0o700)
    return root


def fixture_transport(responses=None, calls=None):
    responses = responses or {
        "massive": audit.AuditResponse(200, (("content-type", "application/json"),), encoded(MASSIVE)),
        "sharadar": audit.AuditResponse(200, (("content-type", "application/json"),), encoded(SHARADAR)),
    }
    def transport(request, credential):
        if calls is not None:
            calls.append((request, credential))
        return responses[request.provider]
    return transport


def execute(private_root, *, frozen=None, responses=None, calls=None, resolver=None, **kwargs):
    return audit.execute_source_audit(
        frozen or plan(), private_root, now=NOW,
        credential_resolver=resolver or (lambda provider: KEYS[provider]),
        transport=fixture_transport(responses, calls), **kwargs)


def report(result):
    assert hashlib.sha256(result.payload).hexdigest() == result.sha256
    assert result.payload.endswith(b"\n")
    return json.loads(result.payload)


def test_frozen_plan_closes_exact_operations_and_limits():
    frozen = plan()
    body = frozen.body()
    assert frozen.sha256 == hashlib.sha256(frozen.payload).hexdigest()
    assert body["audit_id"] == "TPR-SOURCE-AUDIT-20261006-001"
    assert body["limits"] == {"requests": 2, "response_bytes": 65536, "aggregate_response_bytes": 131072,
                              "request_timeout_seconds": 10, "max_elapsed_seconds": 30,
                              "redirects": 0, "retries": 0, "pages_followed": 0,
                              "max_massive_rows": 1, "max_report_bytes": 32768}
    assert body["requests"][0] == {"provider": "massive", "method": "GET", "host": "api.massive.com",
                                  "port": 443, "path": "/benzinga/v1/ratings",
                                  "query": {"date": "2025-01-02", "limit": "1", "sort": "date.asc"},
                                  "credential": "env:MASSIVE_API_KEY", "authorization": "Bearer"}
    assert body["requests"][1]["query"] == {"status": "True"}
    assert body["requests"][1]["path"] == "/v1.0/data/tickers"
    body["requests"][0]["query"]["limit"] = "1000"
    assert frozen.body()["requests"][0]["query"]["limit"] == "1"


@pytest.mark.parametrize("kwargs", [
    {"mode": "anything"}, {"mode": True}, {"git_sha": "A" * 40}, {"code_sha256": True},
    {"owner_instruction_sha256": None}, {"created_utc": "2026-10-06T18:00:00"},
    {"expires_utc": "2026-10-06T18:00:00+00:00"},
    {"expires_utc": "2026-10-09T18:00:00+00:00"},
    {"created_utc": "2026-10-06T18:00:00-07:00"},
])
def test_invalid_identity_policy_or_duration_refuses(kwargs):
    with pytest.raises(audit.SourceAuditError):
        plan(**kwargs)


@pytest.mark.parametrize("edit", [
    lambda b: b["limits"].update(requests=3), lambda b: b["limits"].update(retries=1),
    lambda b: b["requests"][0].update(host="example.com"),
    lambda b: b["requests"][0]["query"].update(date="2026-10-06"),
    lambda b: b["requests"][1]["query"].update(status="False"),
    lambda b: b["authority"].update(outcomes=True), lambda b: b.update(unknown=True),
])
def test_rehash_cannot_override_plan(private_root, edit):
    frozen = plan()
    body = frozen.body()
    edit(body)
    payload = (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode()
    forged = replace(frozen, payload=payload, sha256=hashlib.sha256(payload).hexdigest())
    with pytest.raises(audit.SourceAuditError):
        execute(private_root, frozen=forged)
    assert list(private_root.iterdir()) == []


@pytest.mark.parametrize("when", [NOW - timedelta(seconds=1), NOW + timedelta(hours=24)])
def test_future_or_expired_plan_refuses_before_claim(private_root, when):
    with pytest.raises(audit.SourceAuditError, match="audit plan is not currently valid"):
        audit.execute_source_audit(plan(), private_root, now=when,
                                  credential_resolver=lambda _: pytest.fail("credential accessed"),
                                  transport=lambda *_: pytest.fail("transport called"))
    assert list(private_root.iterdir()) == []


def test_completed_report_is_aggregate_only_and_not_entitlement(private_root, capsys):
    calls = []
    result = execute(private_root, calls=calls)
    body = report(result)
    assert body["status"] == "COMPLETED"
    assert body["mode"] == "offline-fixture"
    assert body["provider_requests"] == 0
    assert body["fixture_transport_calls"] == 2
    assert body["response_bytes"] == len(encoded(MASSIVE)) + len(encoded(SHARADAR))
    assert len(calls) == 2
    assert [entry[0].provider for entry in calls] == ["massive", "sharadar"]
    assert body["providers"][0]["field_presence"]["price_target"] == 1
    assert body["providers"][0]["field_presence"]["price_target_horizon"] == 0
    assert body["providers"][0]["rows_observed"] == 1
    assert body["providers"][1]["metadata"]["size_bytes"] == 1234
    assert body["providers"][1]["metadata"]["snapshot_utc"] == "2025-01-02T00:00:00+00:00"
    assert all(v is False for v in body["authority"].values())
    assert body["real_development_backtest_ready"] is False
    assert body["license_entitlement"] == body["point_in_time_facts"] == "unestablished"
    assert body["working_assumption"] == "owner-authorized-outcome-free-access-not-vendor-attestation"
    assert body["d0_renewed"] is False
    assert body["outcome_reads"] == body["qc_attempts"] == body["development_looks"] == 0
    for forbidden in (*KEYS.values(), "SYNTHETIC-PRIVATE-TARGET", "SYNTHETIC-PRIVATE-FIRM",
                      "DO-NOT-PUBLISH-UNKNOWN", "private.csv.zip", "SYNTHETIC-CURSOR", "unknown_private_field"):
        assert forbidden.encode() not in result.payload
        for artifact in private_root.iterdir():
            assert forbidden.encode() not in artifact.read_bytes()
    assert capsys.readouterr() == ("", "")
    assert result.aggregate_path.read_bytes() == result.payload
    terminal = json.loads(result.terminal_path.read_bytes())
    assert terminal["aggregate_sha256"] == result.sha256
    assert terminal["status"] == "COMPLETED"


def test_claim_is_durable_before_credentials_or_transport(private_root):
    def credentials(provider):
        marker = private_root / (audit.AUDIT_ID + ".spent.json")
        assert marker.exists()
        assert json.loads(marker.read_bytes())["plan_sha256"] == plan().sha256
        return KEYS[provider]
    execute(private_root, resolver=credentials)
    with pytest.raises(audit.SourceAuditError, match="already spent"):
        audit.execute_source_audit(plan(), private_root, now=NOW,
                                  credential_resolver=lambda _: pytest.fail("credential read twice"),
                                  transport=lambda *_: pytest.fail("second request"))


@pytest.mark.parametrize("permissions", [0o777, 0o755, 0o710, 0o600])
def test_insecure_private_directory_refuses(private_root, permissions):
    private_root.chmod(permissions)
    with pytest.raises(audit.SourceAuditError, match="private audit directory"):
        execute(private_root)


def test_symlink_root_refuses(private_root, tmp_path):
    link = tmp_path / "unsafe-link"
    link.symlink_to(private_root, target_is_directory=True)
    with pytest.raises(audit.SourceAuditError, match="private audit directory"):
        execute(link)
    assert list(private_root.iterdir()) == []


def test_production_injections_and_arbitrary_root_refuse_without_any_io(private_root):
    with pytest.raises(audit.SourceAuditError, match="offline fixture"):
        audit.execute_source_audit(plan(mode="production"), private_root, now=NOW,
                                  credential_resolver=lambda _: pytest.fail("credential accessed"),
                                  transport=lambda *_: pytest.fail("transport accessed"))
    with pytest.raises(audit.SourceAuditError, match="fixed lane audit root"):
        audit.execute_source_audit(plan(mode="production"), private_root, now=NOW)
    assert list(private_root.iterdir()) == []


@pytest.mark.parametrize("body,status,headers,disposition", [
    (MASSIVE, 302, (("location", "https://secret.invalid"),), "redirect_refused"),
    (MASSIVE, 200, (("content-encoding", "gzip"),), "encoding_refused"),
    (MASSIVE, 200, (("content-type", "application/zip"),), "content_type_refused"),
    ({"status": "ERROR", "message": "SYNTHETIC-PRIVATE-MESSAGE"}, 403, (), "http_access_refused"),
    ({"results": [{}, {}], "status": "OK"}, 200, (), "row_limit_refused"),
    ({"results": [{"new_price": 1}], "status": "OK", "data": []}, 200, (), "body_schema_refused"),
    ({"results": [1], "status": "OK"}, 200, (), "body_schema_refused"),
    ({"status": "OK", "results": []}, 200, (), "empty_sample"),
])
def test_massive_closed_refusals_publish_no_unknown_data(private_root, body, status, headers, disposition):
    responses = {
        "massive": audit.AuditResponse(status, headers, encoded(body)),
        "sharadar": audit.AuditResponse(200, (), encoded(SHARADAR)),
    }
    result = execute(private_root, responses=responses)
    output = report(result)["providers"][0]
    assert output["disposition"] == disposition
    assert output["authenticated_access_observed"] is False
    assert b"PRIVATE-MESSAGE" not in result.payload
    assert b"secret.invalid" not in result.payload


@pytest.mark.parametrize("body", [b"x" * 65537, b"PK\x03\x04SYNTHETIC-ZIP", b'{"results":[],"results":[]}',
                                 b'{"results":[],"x":NaN}', b"\xff", b"[]"])
def test_oversized_or_invalid_raw_body_never_becomes_access_proof(private_root, body):
    result = execute(private_root, responses={
        "massive": audit.AuditResponse(200, (), body),
        "sharadar": audit.AuditResponse(200, (), encoded(SHARADAR))})
    observed = report(result)["providers"][0]
    assert observed["authenticated_access_observed"] is False
    assert observed["disposition"] in {"response_byte_limit_refused", "body_schema_refused"}
    if len(body) > 65536:
        assert observed["response_sha256"] is None
        assert observed["response_bytes"] == 0


@pytest.mark.parametrize("provider", ["massive", "sharadar"])
def test_secret_echo_checked_before_response_hash(private_root, provider, monkeypatch):
    responses = {
        "massive": audit.AuditResponse(200, (), encoded(MASSIVE)),
        "sharadar": audit.AuditResponse(200, (), encoded(SHARADAR)),
    }
    echoed = encoded({"status": "ERROR", "message": KEYS["massive"] + KEYS["sharadar"]})
    responses[provider] = audit.AuditResponse(403, (), echoed)
    original = audit._digest
    def deny_echo_hash(payload):
        assert payload != echoed, "credential-containing response hashed"
        return original(payload)
    monkeypatch.setattr(audit, "_digest", deny_echo_hash)
    result = execute(private_root, responses=responses)
    output = next(p for p in report(result)["providers"] if p["provider"] == provider)
    assert output["disposition"] == "credential_echo_refused"
    assert output["response_sha256"] is None


@pytest.mark.parametrize("status", [200, 403])
def test_unicode_escaped_secret_echo_refuses_before_any_hash(private_root, monkeypatch, status):
    escaped = "".join("\\u" + format(ord(character), "04x") for character in KEYS["massive"])
    raw = ('{"status":"ERROR","message":"' + escaped + '"}').encode()
    original = audit._digest
    def forbidden_hash(payload):
        assert payload != raw, "escaped credential-containing response hashed"
        return original(payload)
    monkeypatch.setattr(audit, "_digest", forbidden_hash)
    result = execute(private_root, responses={
        "massive": audit.AuditResponse(status, (), raw),
        "sharadar": audit.AuditResponse(200, (), encoded(SHARADAR))})
    output = report(result)["providers"][0]
    assert output["disposition"] == "credential_echo_refused"
    assert output["response_sha256"] is None


def test_offline_mode_cannot_consume_fixed_production_claim():
    with pytest.raises(audit.SourceAuditError, match="offline fixture directory"):
        execute(audit.PRIVATE_ROOT)


def test_offline_mode_cannot_use_production_resolver_or_transport(private_root):
    with pytest.raises(audit.SourceAuditError, match="synthetic fixtures"):
        audit.execute_source_audit(plan(), private_root, now=NOW,
                                  credential_resolver=audit._production_credential,
                                  transport=fixture_transport())
    with pytest.raises(audit.SourceAuditError, match="synthetic fixtures"):
        audit.execute_source_audit(plan(), private_root, now=NOW,
                                  credential_resolver=lambda provider: KEYS[provider], transport=audit._https_get)
    assert list(private_root.iterdir()) == []


def test_unknown_transport_bytes_are_not_reported_as_exact_zero(private_root):
    def fault(*_):
        raise OSError("SYNTHETIC-partial-response-detail")
    result = audit.execute_source_audit(plan(), private_root, now=NOW,
                                      credential_resolver=lambda provider: KEYS[provider], transport=fault)
    body = report(result)
    assert body["response_bytes"] == 0
    assert body["response_bytes_complete"] is False
    assert body["providers"][0]["response_bytes_complete"] is False
    assert body["providers"][1]["response_bytes_complete"] is True


def test_request_primitive_alias_refuses_without_equality_callback(monkeypatch):
    class Host(str):
        def __eq__(self, other):
            pytest.fail("custom host equality invoked")
    forged = replace(audit.REQUESTS[0], host=Host("api.massive.com"))
    monkeypatch.setattr(audit.http.client, "HTTPSConnection", lambda *_a, **_k: pytest.fail("request escaped"))
    with pytest.raises(audit.SourceAuditError, match="fixed source request"):
        _FIXED_TRANSPORT(forged, KEYS["massive"])


def test_tls_factory_never_honors_environment_keylogging(monkeypatch, tmp_path):
    logfile = tmp_path / "must-not-exist.keylog"
    monkeypatch.setenv("SSLKEYLOGFILE", str(logfile))
    monkeypatch.setattr(audit.ssl, "create_default_context", lambda *_a, **_k: pytest.fail("unsafe TLS factory"))
    response = FakeResponse()
    fake_connection(monkeypatch, response)
    _FIXED_TRANSPORT(audit.REQUESTS[0], KEYS["massive"])
    assert not logfile.exists()


@pytest.mark.parametrize("body", [
    {"datatable": {"data": [["SYNTHETIC-PRIVATE-ROW"]]}},
    {**SHARADAR, "size": True},
    {**SHARADAR, "size": -1},
    {**SHARADAR, "modified": "not-a-clock"},
    {**SHARADAR, "rows": []},
])
def test_sharadar_metadata_only_rejects_rows_and_bad_primitives(private_root, body):
    result = execute(private_root, responses={
        "massive": audit.AuditResponse(200, (), encoded(MASSIVE)),
        "sharadar": audit.AuditResponse(200, (), encoded(body))})
    output = report(result)["providers"][1]
    assert output["disposition"] == "body_schema_refused"
    assert output["metadata"] == {"metadata_shape_observed": False, "size_bytes": None, "snapshot_utc": None}
    assert b"PRIVATE-ROW" not in result.payload


@pytest.mark.parametrize("value", [None, "", True, "short", "secret\r\nheader", "bad key value"])
def test_missing_or_invalid_credentials_are_sanitized_and_spent(private_root, value):
    calls = []
    result = execute(private_root, resolver=lambda _: value, calls=calls)
    assert len(calls) == 0
    assert all(p["disposition"] == "credential_unavailable" for p in report(result)["providers"])
    assert (private_root / (audit.AUDIT_ID + ".spent.json")).exists()


def test_unexpected_exception_and_interrupt_leave_no_retry_or_raw_error(private_root):
    def fault(*_):
        raise RuntimeError(KEYS["massive"])
    result = audit.execute_source_audit(plan(), private_root, now=NOW,
                                      credential_resolver=lambda provider: KEYS[provider], transport=fault)
    body = report(result)
    assert body["status"] == "FAILED"
    assert body["fixture_transport_calls"] == 1
    assert body["providers"][0]["disposition"] == "transport_failed"
    assert body["providers"][1]["disposition"] == "not_attempted_after_failure"
    assert KEYS["massive"].encode() not in result.payload
    with pytest.raises(audit.SourceAuditError, match="already spent"):
        execute(private_root)


def test_keyboard_interrupt_publishes_fixed_terminal_then_propagates(private_root):
    def interrupt(*_):
        raise KeyboardInterrupt(KEYS["massive"])
    with pytest.raises(KeyboardInterrupt) as interrupted:
        audit.execute_source_audit(plan(), private_root, now=NOW,
                                  credential_resolver=lambda provider: KEYS[provider], transport=interrupt)
    assert str(interrupted.value) == "source audit interrupted; one-shot scope remains spent"
    terminal = json.loads((private_root / (audit.AUDIT_ID + ".terminal.json")).read_bytes())
    assert terminal["status"] == "INTERRUPTED"
    assert all(KEYS["massive"].encode() not in path.read_bytes() for path in private_root.iterdir())


class FakeResponse:
    def __init__(self, *, status=200, headers=None, body=b'{"status":"OK","results":[]}', complete=True):
        self.status, self.headers, self.body = status, headers or {"content-type": "application/json"}, body
        self.complete, self.reads = complete, []
    def getheaders(self):
        return list(self.headers.items())
    def getheader(self, name, default=None):
        return self.headers.get(name, default)
    def read(self, amount):
        self.reads.append(amount)
        return self.body[:amount]
    def isclosed(self):
        return self.complete


def fake_connection(monkeypatch, response, *, fault=None):
    calls, instances = [], []
    class Connection:
        def __init__(self, host, port, *, timeout, context):
            assert context.check_hostname is True
            assert context.verify_mode == audit.ssl.CERT_REQUIRED
            self.closed, self.debuglevel = False, None
            instances.append(self)
            calls.append((host, port, timeout))
        def set_debuglevel(self, value):
            self.debuglevel = value
        def request(self, method, path, *, headers):
            calls.append((method, path, headers))
            if fault:
                raise fault
        def getresponse(self):
            return response
        def close(self):
            self.closed = True
    monkeypatch.setattr(audit.http.client, "HTTPSConnection", Connection)
    return calls, instances


def test_https_transport_has_fixed_host_tls_auth_no_retry_and_closes(monkeypatch):
    response = FakeResponse()
    calls, instances = fake_connection(monkeypatch, response)
    result = _FIXED_TRANSPORT(audit.REQUESTS[0], KEYS["massive"])
    assert result.status == 200
    assert calls[0] == ("api.massive.com", 443, 10)
    assert calls[1][0:2] == ("GET", "/benzinga/v1/ratings?date=2025-01-02&limit=1&sort=date.asc")
    assert calls[1][2]["Authorization"] == "Bearer " + KEYS["massive"]
    assert calls[1][2]["Accept-Encoding"] == "identity"
    assert calls[1][2]["Connection"] == "close"
    assert response.reads == [65536]
    assert len(instances) == 1 and instances[0].closed and instances[0].debuglevel == 0


@pytest.mark.parametrize("status,headers", [(302, {"location": "https://synthetic.invalid"}),
                                            (200, {"content-encoding": "gzip"}),
                                            (200, {"content-length": "65537"}),
                                            (200, {"content-type": "application/zip"})])
def test_https_refuses_redirect_encoding_oversize_before_body_read(monkeypatch, status, headers):
    response = FakeResponse(status=status, headers=headers)
    _, instances = fake_connection(monkeypatch, response)
    _FIXED_TRANSPORT(audit.REQUESTS[0], KEYS["massive"])
    assert response.reads == []
    assert instances[0].closed


def test_https_undelimited_limit_boundary_refuses_without_extra_byte_read(monkeypatch):
    response = FakeResponse(body=b"x" * 65536, complete=False)
    _, instances = fake_connection(monkeypatch, response)
    result = _FIXED_TRANSPORT(audit.REQUESTS[0], KEYS["massive"])
    assert result.refusal == "response_byte_limit_refused"
    assert response.reads == [65536]
    assert result.body == response.body
    assert result.consumed_bytes == 65536
    assert instances[0].closed


def test_https_exception_closes_and_raises_no_secret_detail(monkeypatch):
    response = FakeResponse()
    _, instances = fake_connection(monkeypatch, response, fault=OSError(KEYS["massive"]))
    with pytest.raises(audit.SourceAuditError, match="transport failed") as raised:
        _FIXED_TRANSPORT(audit.REQUESTS[0], KEYS["massive"])
    assert instances[0].closed
    assert KEYS["massive"] not in str(raised.value)


def test_sharadar_transport_is_status_metadata_not_download(monkeypatch):
    response = FakeResponse(body=encoded(SHARADAR))
    calls, _ = fake_connection(monkeypatch, response)
    _FIXED_TRANSPORT(audit.REQUESTS[1], KEYS["sharadar"])
    assert calls[0] == ("api.sharadar.com", 443, 10)
    assert calls[1][1] == "/v1.0/data/tickers?status=True&api_key=" + KEYS["sharadar"]
    assert "Authorization" not in calls[1][2]


def test_elapsed_budget_prevents_second_operation_without_retry(private_root):
    clock_values = iter([0.0, 0.0, 0.0, 31.0, 31.0])
    result = execute(private_root, monotonic=lambda: next(clock_values))
    body = report(result)
    assert body["fixture_transport_calls"] == 1
    assert body["status"] == "FAILED"
    assert body["providers"][1]["disposition"] == "elapsed_budget_refused"


def test_publication_failure_keeps_spent_claim_and_never_overwrites(private_root, monkeypatch):
    original_link = os.link
    def fail_link(*args, **kwargs):
        raise OSError("SYNTHETIC-private-filesystem-detail")
    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(audit.SourceAuditError, match="publication failed") as raised:
        execute(private_root)
    assert "private-filesystem-detail" not in str(raised.value)
    assert (private_root / (audit.AUDIT_ID + ".spent.json")).exists()
    monkeypatch.setattr(os, "link", original_link)
    with pytest.raises(audit.SourceAuditError, match="already spent"):
        execute(private_root)


def test_private_directory_fstat_failure_closes_owned_descriptor(private_root, monkeypatch):
    closed = []
    monkeypatch.setattr(audit.os, "open", lambda *_a, **_k: 918273)
    def unavailable(*_args):
        raise OSError("SYNTHETIC-fstat-detail")
    monkeypatch.setattr(audit.os, "fstat", unavailable)
    monkeypatch.setattr(audit.os, "close", closed.append)
    with pytest.raises(audit.SourceAuditError, match="private audit directory unavailable"):
        audit._private_directory(private_root, "offline-fixture")
    assert closed == [918273]


@pytest.mark.parametrize("index,value", [(0, "/SYNTHETIC-wrong-root"),
                                         (1, "codex/SYNTHETIC-wrong-lane"), (2, "9" * 40)])
def test_git_identity_mismatch_refuses_before_private_claim_or_credentials(monkeypatch, index, value):
    values = [str(audit.LANE_ROOT), audit.LANE_BRANCH, "2" * 40]
    values[index] = value
    responses = iter(values)
    def git_metadata(command, **kwargs):
        assert command[0:2] == ["git", "rev-parse"]
        assert kwargs["cwd"] == audit.LANE_ROOT
        return SimpleNamespace(stdout=(next(responses) + "\n").encode(), returncode=0)
    monkeypatch.setattr(audit.subprocess, "run", git_metadata)
    monkeypatch.setattr(audit, "_private_directory", lambda *_a: pytest.fail("claim root reached before identity"))
    with pytest.raises(audit.SourceAuditError, match="lane identity mismatch"):
        audit.execute_source_audit(plan(mode="production"), audit.PRIVATE_ROOT)


def test_physical_cwd_mismatch_refuses_before_git_claim_or_credentials(monkeypatch):
    monkeypatch.setattr(audit.Path, "cwd", lambda: audit.Path("/SYNTHETIC-wrong-cwd"))
    monkeypatch.setattr(audit.subprocess, "run", lambda *_a, **_k: pytest.fail("git consulted outside lane"))
    monkeypatch.setattr(audit, "_private_directory", lambda *_a: pytest.fail("claim root reached outside lane"))
    with pytest.raises(audit.SourceAuditError, match="designated physical lane"):
        audit.execute_source_audit(plan(mode="production"), audit.PRIVATE_ROOT)


def matching_git(monkeypatch):
    values = iter([str(audit.LANE_ROOT), audit.LANE_BRANCH, "2" * 40])
    monkeypatch.setattr(audit.subprocess, "run", lambda *_a, **_k:
                        SimpleNamespace(stdout=(next(values) + "\n").encode(), returncode=0))


def test_executed_source_hash_mismatch_refuses_before_claim_or_credentials(monkeypatch):
    matching_git(monkeypatch)
    monkeypatch.setattr(audit, "_private_directory", lambda *_a: pytest.fail("claim reached after code drift"))
    with pytest.raises(audit.SourceAuditError, match="code identity mismatch"):
        audit.execute_source_audit(plan(mode="production"), audit.PRIVATE_ROOT)


def test_executed_source_nofollow_refuses_symlink_before_claim(tmp_path, monkeypatch):
    matching_git(monkeypatch)
    source = tmp_path / "SYNTHETIC-source.py"
    source.write_bytes(b"# SYNTHETIC-code-only\n")
    link = tmp_path / "SYNTHETIC-linked-source.py"
    link.symlink_to(source)
    monkeypatch.setattr(audit, "__file__", str(link))
    monkeypatch.setattr(audit, "_private_directory", lambda *_a: pytest.fail("claim reached through source symlink"))
    frozen = plan(mode="production", code_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    with pytest.raises(audit.SourceAuditError, match="execution identity unavailable"):
        audit.execute_source_audit(frozen, audit.PRIVATE_ROOT)


def test_executed_source_and_git_identity_positive_control_reads_only_own_code(monkeypatch):
    matching_git(monkeypatch)
    source = audit.Path(audit.__file__).read_bytes()
    frozen = plan(mode="production", code_sha256=hashlib.sha256(source).hexdigest())
    audit._verify_execution_identity(frozen.body())


def test_unrepresentable_json_decimal_refuses_with_known_body_accounting(private_root):
    payload = b'{"results":[{"price_target":1e99999999999999999999}],"status":"OK"}'
    result = execute(private_root, responses={
        "massive": audit.AuditResponse(200, (), payload),
        "sharadar": audit.AuditResponse(200, (), encoded(SHARADAR)),
    })
    body = report(result)
    observed = body["providers"][0]
    assert observed["disposition"] == "body_schema_refused"
    assert observed["response_bytes"] == len(payload)
    assert observed["response_bytes_complete"] is True
    assert observed["response_sha256"] is None
    assert body["fixture_transport_calls"] == 2
