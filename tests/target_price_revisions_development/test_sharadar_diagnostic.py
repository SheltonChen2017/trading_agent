"""A separate one-shot metadata diagnosis uses synthetic responses only."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import socket
from pathlib import Path

import pytest

from research.target_price_revisions_development import sharadar_diagnostic as diagnostic
from research.target_price_revisions_development import source_audit as audit

NOW = datetime(2026, 10, 7, 6, tzinfo=timezone.utc)
KEY = "SYNTHETIC_SHARADAR_DIAGNOSTIC_KEY"
METADATA = {"table": "tickers", "name": "SYNTHETIC-private.zip", "size": 1234,
            "sizeLabel": "SYNTHETIC-private-label", "modified": "2026-10-06T12:00:00Z"}


@pytest.fixture(autouse=True)
def forbid_actual_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual credential or network operation in diagnostic fixtures")
    monkeypatch.setattr(diagnostic, "_production_credential", forbidden)
    monkeypatch.setattr(diagnostic, "_https_get", forbidden)
    monkeypatch.setattr(audit, "_production_credential", forbidden)
    monkeypatch.setattr(audit, "_https_get", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def plan(mode="offline-fixture", **changes):
    kwargs = dict(code_sha256="1" * 64, git_sha="2" * 40,
                  owner_instruction_sha256="3" * 64, created_utc=NOW.isoformat(),
                  expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode=mode)
    kwargs.update(changes)
    return diagnostic.freeze_diagnostic_plan(**kwargs)


@pytest.fixture
def private_root(tmp_path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    return root


def execute(root, *, body=None, response=None, frozen=None, resolver=None, calls=None):
    body = METADATA if body is None else body
    if response is None:
        response = audit.AuditResponse(200, (("content-type", "application/json"),),
                                       json.dumps(body).encode())
    def transport(request, key):
        if calls is not None:
            calls.append((request, key))
        return response
    return diagnostic.execute_diagnostic(frozen or plan(), root, now=NOW,
        credential_resolver=resolver or (lambda provider: KEY), transport=transport)


def test_frozen_operation_is_only_sharadar_metadata():
    body = plan().body()
    assert body["diagnostic_id"] == "TPR-SHARADAR-DIAGNOSTIC-20261006-001"
    assert body["requests"] == [audit.REQUESTS[1].body()]
    assert body["limits"] == {"requests": 1, "response_bytes": 65536,
        "request_timeout_seconds": 10, "redirects": 0, "retries": 0,
        "pages_followed": 0, "rows": 0, "max_report_bytes": 32768}
    assert body["auditor_code_sha256"] == "9f2674a47d0d62bb09e2dd5ba1ce7f37eed3c68dce254e40e0d11d1218f46960"
    assert all(value is False for value in body["authority"].values())
    body["requests"][0]["query"]["status"] = "False"
    assert plan().body()["requests"][0]["query"] == {"status": "True"}


@pytest.mark.parametrize("change", [
    {"code_sha256": True}, {"git_sha": "A" * 40}, {"owner_instruction_sha256": None},
    {"mode": "unknown"}, {"created_utc": "2026-10-07T06:00:00"},
    {"expires_utc": NOW.isoformat()}, {"expires_utc": (NOW + timedelta(hours=49)).isoformat()},
])
def test_invalid_plan_refuses(change):
    with pytest.raises(audit.SourceAuditError):
        plan(**change)


@pytest.mark.parametrize("mutation", [
    lambda body: body["limits"].update(requests=2),
    lambda body: body["requests"][0]["query"].update(years="full"),
    lambda body: body.update(auditor_code_sha256="a" * 64),
    lambda body: body["authority"].update(outcomes=True),
    lambda body: body.update(extra=True),
])
def test_rehashed_policy_change_refuses_before_claim(private_root, mutation):
    frozen = plan()
    body = frozen.body()
    mutation(body)
    payload = audit._canonical(body)
    forged = replace(frozen, payload=payload, sha256=hashlib.sha256(payload).hexdigest())
    with pytest.raises(audit.SourceAuditError):
        execute(private_root, frozen=forged)
    assert list(private_root.iterdir()) == []


def test_diagnosis_publishes_no_raw_metadata(private_root, capsys):
    calls = []
    result = execute(private_root, calls=calls)
    report = json.loads(result.payload)
    assert hashlib.sha256(result.payload).hexdigest() == result.sha256
    assert report["diagnosis"]["classification"] == "metadata_verified"
    assert report["diagnosis"]["metadata"] == {"metadata_shape_observed": True,
        "size_bytes": 1234, "snapshot_utc": "2026-10-06T12:00:00+00:00"}
    assert report["provider_requests"] == 0 and report["fixture_transport_calls"] == 1
    assert calls == [(audit.REQUESTS[1], KEY)]
    assert report["credential_state"] == "not_proven"
    assert report["real_development_backtest_ready"] is False
    assert report["d0_renewed"] is False and report["original_audit_renewed"] is False
    assert report["outcome_reads"] == report["qc_attempts"] == report["development_looks"] == 0
    for file in private_root.iterdir():
        payload = file.read_bytes()
        assert KEY.encode() not in payload
        assert b"SYNTHETIC-private" not in payload
        assert file.stat().st_mode & 0o777 == 0o600
    assert result.aggregate_path.read_bytes() == result.payload
    assert json.loads(result.terminal_path.read_bytes())["aggregate_sha256"] == result.sha256
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("value, expected", [
    ("TICKERS", "upper"), ("Tickers", "mixed_tickers"), ("TiCkErS", "mixed_tickers"), ("private-unknown", "other"),
    (False, "not_string"),
])
def test_table_literal_only_fixed_case_enum(value, expected):
    body = dict(METADATA, table=value)
    result = diagnostic.diagnose_metadata(body)
    assert result["classification"] == "metadata_schema_mismatch"
    assert result["table_literal"] == expected
    assert "table_literal_mismatch" in result["clauses"] if type(value) is str else "table_type" in result["clauses"]
    assert "private-unknown" not in json.dumps(result)


@pytest.mark.parametrize("change, clause", [
    ({"size": True}, "size_type"), ({"size": Decimal("1234")}, "size_type"),
    ({"size": -1}, "size_range"), ({"size": 10**15 + 1}, "size_range"),
    ({"name": ""}, "name_length"), ({"name": None}, "name_type"),
    ({"sizeLabel": []}, "size_label_type"), ({"sizeLabel": ""}, "size_label_length"),
    ({"modified": "2026-10-06T12:00:00"}, "modified_utc"),
    ({"modified": False}, "modified_type"),
])
def test_each_metadata_clause_is_diagnosed_without_admission(change, clause):
    result = diagnostic.diagnose_metadata(dict(METADATA, **change))
    assert clause in result["clauses"]
    assert result["metadata"]["metadata_shape_observed"] is False


def test_unknown_keys_are_counts_only_and_missing_fields_explicit():
    result = diagnostic.diagnose_metadata({"size": 42, "PRIVATE_UNKNOWN_NAME": "PRIVATE_UNKNOWN_VALUE"})
    assert result["shape"]["unknown_key_count"] == 1
    assert result["shape"]["fields"]["size"] == "integer"
    assert result["shape"]["fields"]["modified"] == "absent"
    assert "missing_modified" in result["clauses"]
    assert "PRIVATE_UNKNOWN" not in json.dumps(result)


@pytest.mark.parametrize("body, category", [
    ({"code": "INVALID_API_KEY", "message": "PRIVATE-message"}, "invalid_api_key"),
    ({"status": "ERROR", "message": "Invalid API key."}, "invalid_api_key"),
    ({"status": "ERROR", "message": "No invalid API key was supplied."}, "unclassified"),
    ({"error": "FORBIDDEN"}, "forbidden"),
    ({"code": "RATE_LIMITED"}, "rate_limit"),
    ({"error": "PRIVATE-error", "message": "PRIVATE-message"}, "unclassified"),
])
def test_application_errors_are_fixed_categories_not_raw_messages(body, category):
    result = diagnostic.diagnose_metadata(body)
    assert result["classification"] == "application_error"
    assert result["application_error"] == category
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("inactive", [False, "", 0, [], {}, None])
def test_inactive_error_flag_does_not_fabricate_application_rejection(inactive):
    result = diagnostic.diagnose_metadata(dict(METADATA, error=inactive))
    assert result["classification"] == "metadata_schema_mismatch"
    assert result["application_error"] is None
    assert "unexpected_keys" in result["clauses"]


@pytest.mark.parametrize("response", [
    audit.AuditResponse(200, (), b'{"message":"SYNTHETIC_SHARADAR_DIAGNOSTIC_KEY"}'),
    audit.AuditResponse(200, (), b'{"message":"SYNTHETIC_SHARADAR_DIAGNOSTIC_\\u004bEY"}'),
])
def test_credential_echo_precedes_body_hash_or_shape(private_root, response):
    result = json.loads(execute(private_root, response=response).payload)
    assert result["provider"]["disposition"] == "credential_echo_refused"
    assert result["provider"]["response_sha256"] is None
    assert result["diagnosis"]["classification"] == "not_observed"
    assert result["diagnosis"]["shape"]["fields"] == {}


@pytest.mark.parametrize("response, disposition, complete", [
    (audit.AuditResponse(200, (), b'{"bad":'), "body_schema_refused", True),
    (audit.AuditResponse(200, (), b'x' * 65536, "response_byte_limit_refused", 65536),
     "response_byte_limit_refused", False),
    (audit.AuditResponse(302, (), b'', "redirect_refused"), "redirect_refused", False),
    (audit.AuditResponse(200, (), b'{"size":42}', "body_schema_refused", 11),
     "body_schema_refused", False),
    (audit.AuditResponse(200, (), b'{"SYNTHETIC_SHARADAR_DIAGNOSTIC_\\u004bEY":42}'),
     "credential_echo_refused", True),
])
def test_nonadmitted_body_never_reaches_shape_and_counts_are_lower_bounds(private_root, response, disposition, complete):
    report = json.loads(execute(private_root, response=response).payload)
    assert report["provider"]["disposition"] == disposition
    assert report["provider"]["response_sha256"] is None
    assert report["provider"]["response_bytes_complete"] is complete
    assert report["diagnosis"]["shape"]["fields"] == {}


def test_complete_metadata_schema_mismatch_does_not_imply_incomplete_body(private_root):
    body = dict(METADATA, table="TICKERS")
    report = json.loads(execute(private_root, body=body).payload)
    assert report["provider"]["response_bytes"] == len(json.dumps(body).encode())
    assert report["provider"]["response_bytes_complete"] is True
    assert report["diagnosis"]["classification"] == "metadata_schema_mismatch"


def test_one_shot_claim_precedes_lookup_and_changed_hash_does_not_renew(private_root):
    def resolver(provider):
        assert provider == "sharadar"
        claim = private_root / (diagnostic.DIAGNOSTIC_ID + ".spent.json")
        assert claim.exists()
        assert json.loads(claim.read_bytes())["plan_sha256"] == plan().sha256
        return KEY
    execute(private_root, resolver=resolver)
    with pytest.raises(audit.SourceAuditError, match="already spent"):
        execute(private_root, frozen=plan(code_sha256="a" * 64), resolver=lambda _: pytest.fail("lookup again"))


def test_old_claim_is_never_touched(private_root):
    old = private_root / (audit.AUDIT_ID + ".spent.json")
    old.write_bytes(b"SYNTHETIC-old-claim")
    execute(private_root)
    assert old.read_bytes() == b"SYNTHETIC-old-claim"


@pytest.mark.parametrize("bad_key", [None, "not-synthetic-but-valid", "SYNTHETIC_BAD\nHEADER"])
def test_offline_nonsynthetic_credential_never_reaches_transport(private_root, bad_key):
    calls = []
    report = json.loads(execute(private_root, resolver=lambda _: bad_key, calls=calls).payload)
    assert calls == []
    assert report["provider"]["disposition"] == "credential_unavailable"


def test_production_injections_refuse_before_identity_or_claim(private_root):
    with pytest.raises(audit.SourceAuditError, match="offline fixture"):
        diagnostic.execute_diagnostic(plan("production"), private_root, now=NOW,
            credential_resolver=lambda _: KEY, transport=lambda *_: pytest.fail("transport"))
    assert list(private_root.iterdir()) == []


def test_offline_production_adapters_and_root_refuse(private_root):
    with pytest.raises(audit.SourceAuditError, match="synthetic fixtures"):
        diagnostic.execute_diagnostic(plan(), private_root, now=NOW,
            credential_resolver=diagnostic._production_credential, transport=lambda *_: None)
    with pytest.raises(audit.SourceAuditError, match="production diagnostic"):
        diagnostic.execute_diagnostic(plan(), audit.PRIVATE_ROOT, now=NOW,
            credential_resolver=lambda _: KEY, transport=lambda *_: None)


@pytest.mark.parametrize("clock", [NOW - timedelta(seconds=1), NOW + timedelta(hours=24), NOW.replace(tzinfo=None)])
def test_invalid_current_clock_refuses_before_claim(private_root, clock):
    with pytest.raises(audit.SourceAuditError):
        diagnostic.execute_diagnostic(plan(), private_root, now=clock,
            credential_resolver=lambda _: pytest.fail("lookup"), transport=lambda *_: pytest.fail("request"))
    assert list(private_root.iterdir()) == []


def test_transport_failure_is_spent_and_bytes_unknown(private_root):
    def fail(*_args):
        raise RuntimeError(KEY + " PRIVATE_URL")
    result = diagnostic.execute_diagnostic(plan(), private_root, now=NOW,
        credential_resolver=lambda _: KEY, transport=fail)
    body = json.loads(result.payload)
    assert body["status"] == "FAILED"
    assert body["provider"]["disposition"] == "transport_failed"
    assert body["provider"]["response_bytes_complete"] is False
    assert KEY.encode() not in result.payload and b"PRIVATE_URL" not in result.payload
    with pytest.raises(audit.SourceAuditError, match="already spent"):
        execute(private_root)


def test_interruption_has_terminal_and_cannot_relaunch(private_root):
    def interrupt(*_args):
        raise KeyboardInterrupt("PRIVATE-content")
    with pytest.raises(KeyboardInterrupt, match="one-shot scope remains spent"):
        diagnostic.execute_diagnostic(plan(), private_root, now=NOW,
            credential_resolver=lambda _: KEY, transport=interrupt)
    terminal = json.loads((private_root / (diagnostic.DIAGNOSTIC_ID + ".terminal.json")).read_bytes())
    assert terminal["status"] == "INTERRUPTED"
    with pytest.raises(audit.SourceAuditError, match="already spent"):
        execute(private_root)


def test_new_source_identity_binds_exact_source_hash_and_original_hash(monkeypatch):
    checked = []
    monkeypatch.setattr(diagnostic, "_verify_execution_identity", lambda body: checked.append(body))
    source = Path(diagnostic.__file__)
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    diagnostic._verify_identity({"git_sha": "a" * 40, "code_sha256": sha})
    assert checked == [{"git_sha": "a" * 40, "code_sha256": diagnostic.AUDITOR_CODE_SHA256}]
    with pytest.raises(audit.SourceAuditError, match="code identity mismatch"):
        diagnostic._verify_identity({"git_sha": "a" * 40, "code_sha256": "f" * 64})


def test_new_source_path_cannot_be_other_checkout_or_file(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostic, "_verify_execution_identity", lambda _: None)
    source = tmp_path / "sharadar_diagnostic.py"
    source.write_bytes(b"SYNTHETIC-other-file")
    monkeypatch.setattr(diagnostic, "__file__", str(source))
    with pytest.raises(audit.SourceAuditError, match="code identity"):
        diagnostic._verify_identity({"git_sha": "a" * 40,
            "code_sha256": hashlib.sha256(source.read_bytes()).hexdigest()})


def test_new_source_open_uses_nofollow_and_failed_stat_closes_descriptor(monkeypatch):
    monkeypatch.setattr(diagnostic, "_verify_execution_identity", lambda _: None)
    opened, closed = [], []
    def fake_open(path, flags):
        opened.append((path, flags))
        return 918273
    def failed_stat(_fd):
        raise OSError("SYNTHETIC-fstat-failure")
    monkeypatch.setattr(diagnostic.os, "open", fake_open)
    monkeypatch.setattr(diagnostic.os, "fstat", failed_stat)
    monkeypatch.setattr(diagnostic.os, "close", lambda fd: closed.append(fd))
    with pytest.raises(audit.SourceAuditError, match="code identity unavailable"):
        diagnostic._verify_identity({"git_sha": "a" * 40, "code_sha256": "f" * 64})
    assert opened[0][1] & diagnostic.os.O_NOFOLLOW
    assert closed == [918273]
