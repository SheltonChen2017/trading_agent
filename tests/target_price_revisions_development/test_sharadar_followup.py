"""Follow-up safety and useful projection; all responses are synthetic."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from research.target_price_revisions_development import sharadar_followup as followup
from research.target_price_revisions_development import source_audit as audit

NOW = datetime(2026, 10, 7, 8, tzinfo=timezone.utc)
KEY = "SYNTHETIC_SHARADAR_FOLLOWUP_KEY"
FILE = {"name": "SYNTHETIC-private.zip", "size": 1234,
        "sizeLabel": "SYNTHETIC-private-label", "modified": "2026-10-06T12:00:00Z"}
BODY = {"table": "tickers", "files": [dict(FILE, extension="PRIVATE_VALUE")]}


@pytest.fixture(autouse=True)
def forbid_actual_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual credential or network operation in follow-up fixtures")
    for module in (followup, audit):
        monkeypatch.setattr(module, "_production_credential", forbidden)
        monkeypatch.setattr(module, "_https_get", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def plan(mode="offline-fixture", **changes):
    kwargs = dict(code_sha256="1" * 64, projector_sha256="4" * 64, git_sha="2" * 40,
        owner_instruction_sha256="3" * 64, created_utc=NOW.isoformat(),
        expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode=mode)
    kwargs.update(changes)
    return followup.freeze_followup_plan(**kwargs)


@pytest.fixture
def private_root(tmp_path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    return root


def execute(root, *, body=None, response=None, frozen=None, resolver=None, calls=None):
    if response is None:
        response = audit.AuditResponse(200, (("content-type", "application/json"),),
            json.dumps(BODY if body is None else body).encode())
    def transport(request, key):
        if calls is not None:
            calls.append((request, key))
        return response
    return followup.execute_followup(plan() if frozen is None else frozen, root, now=NOW,
        credential_resolver=resolver or (lambda provider: KEY), transport=transport)


def test_unknown_sibling_no_longer_hides_known_descriptor_types(private_root):
    report = json.loads(execute(private_root).payload)
    descriptor = report["projection"]["files"]["descriptors"][0]
    assert descriptor["fields"]["name"] == descriptor["fields"]["modified"] == "string"
    assert descriptor["fields"]["size"] == "integer"
    assert descriptor["unknown_key_count"] == 1
    assert descriptor["unknown_types"] == {"string": 1}
    assert all(descriptor["components"].values())
    assert descriptor["metadata_candidate"]["refusal"] == "unknown_fields"
    assert report["table_literal"] == "tickers"
    assert report["classification"] == "status_structure_observed"
    assert "PRIVATE" not in json.dumps(report)


def test_metadata_transport_does_not_follow_advertised_urls_or_retain_values(private_root, capsys):
    calls = []
    result = execute(private_root, body={"table": "tickers", "files": [dict(FILE,
        url="https://PRIVATE_HOST/download?api_key=" + "OTHER_PRIVATE_KEY")]}, calls=calls)
    report = json.loads(result.payload)
    assert calls == [(audit.REQUESTS[1], KEY)]
    assert report["provider_requests"] == 0 and report["fixture_transport_calls"] == 1
    assert report["provider"]["response_sha256"] is None
    assert report["credential_state"] == "not_proven"
    assert report["provider"]["authenticated_access_observed"] is False
    assert report["canonical_admission"] is report["real_development_backtest_ready"] is False
    assert all(value is False for value in report["authority"].values())
    for path in private_root.iterdir():
        assert not path.is_symlink() and path.stat().st_mode & 0o777 == 0o600
        assert all(value not in path.read_bytes() for value in (KEY.encode(), b"PRIVATE", b"SYNTHETIC-private"))
    assert result.aggregate_path.read_bytes() == result.payload
    assert json.loads(result.terminal_path.read_bytes())["aggregate_sha256"] == result.sha256
    assert capsys.readouterr() == ("", "")


def test_closed_plan_binds_projector_and_one_new_status_only_scope():
    body = plan().body()
    assert body["followup_id"] == "TPR-SHARADAR-FOLLOWUP-20261007-001"
    assert body["projector_sha256"] == "4" * 64
    assert body["requests"] == [audit.REQUESTS[1].body()]
    assert body["limits"]["requests"] == 1 and body["limits"]["rows"] == 0
    assert body["previous_shape_renewed"] is body["original_audit_renewed"] is body["d0_renewed"] is False


@pytest.mark.parametrize("changes", [
    {"code_sha256": True}, {"projector_sha256": "A" * 64}, {"git_sha": "a" * 39},
    {"owner_instruction_sha256": None}, {"mode": True}, {"mode": "unknown"},
    {"expires_utc": NOW.isoformat()}, {"expires_utc": (NOW + timedelta(hours=49)).isoformat()},
])
def test_invalid_plan_refuses(changes):
    with pytest.raises(audit.SourceAuditError):
        plan(**changes)


@pytest.mark.parametrize("mutation", [lambda body: body.update(extra=True),
    lambda body: body["limits"].update(requests=2),
    lambda body: body["requests"][0]["query"].update(status="False"),
    lambda body: body.update(previous_shape_renewed=True)])
def test_rehashed_scope_changes_refuse_before_claim(private_root, mutation):
    frozen = plan()
    body = frozen.body()
    mutation(body)
    payload = audit._canonical(body)
    forged = replace(frozen, payload=payload, sha256=hashlib.sha256(payload).hexdigest())
    with pytest.raises(audit.SourceAuditError):
        execute(private_root, frozen=forged)
    assert list(private_root.iterdir()) == []


def test_claim_precedes_credentials_and_plan_rehash_cannot_rearm(private_root):
    def resolver(provider):
        assert provider == "sharadar"
        assert (private_root / (followup.FOLLOWUP_ID + ".spent.json")).exists()
        return KEY
    execute(private_root, resolver=resolver)
    with pytest.raises(audit.SourceAuditError, match="already spent"):
        execute(private_root, frozen=plan(code_sha256="a" * 64), resolver=lambda _: pytest.fail("second lookup"))


@pytest.mark.parametrize("payload", [
    b'{"files":[{"name":"SYNTHETIC_SHARADAR_FOLLOWUP_KEY"}]}',
    b'{"files":[{"name":"SYNTHETIC_SHARADAR_FOLLOWUP_\\u004bEY"}]}',
    b'{"files":[{"SYNTHETIC_SHARADAR_FOLLOWUP_KEY":"PRIVATE"}]}',
    b'{"files":[{"SYNTHETIC_SHARADAR_FOLLOWUP_\\u004bEY":"PRIVATE"}]}',
])
def test_raw_and_decoded_credential_echo_precede_projection(private_root, payload, monkeypatch):
    monkeypatch.setattr(followup.sharadar_projection, "project_metadata_shape",
        lambda _: pytest.fail("projected secret echo"))
    report = json.loads(execute(private_root, response=audit.AuditResponse(200, (), payload)).payload)
    assert report["provider"]["disposition"] == "credential_echo_refused"
    assert report["projection"] is None and report["provider"]["response_sha256"] is None


@pytest.mark.parametrize("response", [
    audit.AuditResponse(200, (), b'{"table":"tickers","table":"PRIVATE"}'),
    audit.AuditResponse(200, (), b'{"bad":'),
    audit.AuditResponse(200, (), b'x' * 65536, "response_byte_limit_refused", 65536),
    audit.AuditResponse(302, (), b'', "redirect_refused"),
])
def test_transport_refusals_and_invalid_json_do_not_project(private_root, response):
    report = json.loads(execute(private_root, response=response).payload)
    assert report["projection"] is None and report["provider"]["response_sha256"] is None


def test_row_marked_descriptor_never_reaches_component_semantics(private_root, monkeypatch):
    monkeypatch.setattr(followup.sharadar_projection, "_components", lambda _: pytest.fail("row semantics"))
    report = json.loads(execute(private_root, body={"files": [dict(FILE, ticker="PRIVATE")]}).payload)
    assert report["projection"]["files"]["descriptors"] == [{"index": 0, "row_shape_refused": True}]
    assert report["provider"]["response_sha256"] is None
    assert "PRIVATE" not in json.dumps(report)


def test_transport_exception_is_sanitized_and_scope_remains_spent(private_root):
    def failure(*_args):
        raise RuntimeError(KEY + " PRIVATE_URL")
    result = followup.execute_followup(plan(), private_root, now=NOW,
        credential_resolver=lambda _: KEY, transport=failure)
    assert json.loads(result.payload)["status"] == "FAILED"
    assert KEY.encode() not in result.payload and b"PRIVATE" not in result.payload
    with pytest.raises(audit.SourceAuditError, match="already spent"):
        execute(private_root)


def test_interruption_has_terminal_and_does_not_relaunch(private_root):
    def interrupted(*_args):
        raise KeyboardInterrupt("PRIVATE")
    with pytest.raises(KeyboardInterrupt, match="one-shot scope remains spent"):
        followup.execute_followup(plan(), private_root, now=NOW,
            credential_resolver=lambda _: KEY, transport=interrupted)
    terminal = json.loads((private_root / (followup.FOLLOWUP_ID + ".terminal.json")).read_bytes())
    assert terminal["status"] == "INTERRUPTED"
    with pytest.raises(audit.SourceAuditError, match="already spent"):
        execute(private_root)


@pytest.mark.parametrize("credential", [None, "NOT_SYNTHETIC_VALID_KEY", "SYNTHETIC_BAD\nHEADER"])
def test_invalid_fixture_credential_never_calls_transport(private_root, credential):
    calls = []
    report = json.loads(execute(private_root, resolver=lambda _: credential, calls=calls).payload)
    assert calls == [] and report["provider"]["disposition"] == "credential_unavailable"


def test_injections_and_production_root_are_separated_before_claim(private_root):
    with pytest.raises(audit.SourceAuditError, match="offline fixture mode"):
        followup.execute_followup(plan("production"), private_root, now=NOW,
            credential_resolver=lambda _: KEY, transport=lambda *_: None)
    with pytest.raises(audit.SourceAuditError, match="production follow-up"):
        followup.execute_followup(plan(), audit.PRIVATE_ROOT, now=NOW,
            credential_resolver=lambda _: KEY, transport=lambda *_: None)
    with pytest.raises(audit.SourceAuditError, match="synthetic fixtures"):
        followup.execute_followup(plan(), private_root, now=NOW,
            credential_resolver=followup._production_credential, transport=lambda *_: None)
    assert list(private_root.iterdir()) == []


@pytest.mark.parametrize("clock", [NOW - timedelta(seconds=1), NOW + timedelta(hours=24), NOW.replace(tzinfo=None)])
def test_invalid_execution_clock_refuses_before_claim(private_root, clock):
    with pytest.raises(audit.SourceAuditError):
        followup.execute_followup(plan(), private_root, now=clock,
            credential_resolver=lambda _: pytest.fail("lookup"), transport=lambda *_: pytest.fail("request"))
    assert list(private_root.iterdir()) == []


def test_source_identity_binds_both_wrapper_and_projector_before_provider_access(monkeypatch):
    checked = []
    monkeypatch.setattr(followup, "_verify_execution_identity", checked.append)
    body = {"git_sha": "a" * 40,
        "code_sha256": hashlib.sha256(Path(followup.__file__).read_bytes()).hexdigest(),
        "projector_sha256": hashlib.sha256(Path(followup.sharadar_projection.__file__).read_bytes()).hexdigest()}
    followup._verify_identity(body)
    assert checked == [{"git_sha": "a" * 40, "code_sha256": followup.AUDITOR_CODE_SHA256}]
    for key in ("code_sha256", "projector_sha256"):
        with pytest.raises(audit.SourceAuditError, match="code identity mismatch"):
            followup._verify_identity(dict(body, **{key: "f" * 64}))


def test_identity_refuses_nonregular_source_before_read(monkeypatch):
    monkeypatch.setattr(followup.os, "open", lambda *_args: 918273)
    monkeypatch.setattr(followup.os, "fstat", lambda _: SimpleNamespace(st_mode=0o010600, st_size=4))
    monkeypatch.setattr(followup.os, "read", lambda *_args: pytest.fail("nonregular read"))
    closed = []
    monkeypatch.setattr(followup.os, "close", closed.append)
    with pytest.raises(audit.SourceAuditError, match="code identity mismatch"):
        followup._verify_file(Path(followup.__file__), "sharadar_followup.py", "f" * 64)
    assert closed == [918273]
