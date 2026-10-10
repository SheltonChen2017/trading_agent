"""Rich metadata structure uses synthetic bodies and never real adapters."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import socket
from pathlib import Path

import pytest

from research.target_price_revisions_development import sharadar_shape as shape
from research.target_price_revisions_development import source_audit as audit

NOW = datetime(2026, 10, 7, 8, tzinfo=timezone.utc)
KEY = "SYNTHETIC_SHARADAR_SHAPE_KEY"
FILE = {"name": "SYNTHETIC-private.zip", "size": 1234,
        "sizeLabel": "SYNTHETIC-private-label", "modified": "2026-10-06T12:00:00Z"}
BODY = {"table": "tickers", "files": [FILE]}


@pytest.fixture(autouse=True)
def forbid_actual_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("actual credential or network operation in shape fixtures")
    monkeypatch.setattr(shape, "_production_credential", forbidden)
    monkeypatch.setattr(shape, "_https_get", forbidden)
    monkeypatch.setattr(audit, "_production_credential", forbidden)
    monkeypatch.setattr(audit, "_https_get", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def plan(mode="offline-fixture", **changes):
    kwargs = dict(code_sha256="1" * 64, git_sha="2" * 40,
        owner_instruction_sha256="3" * 64, created_utc=NOW.isoformat(),
        expires_utc=(NOW + timedelta(hours=24)).isoformat(), mode=mode)
    kwargs.update(changes)
    return shape.freeze_shape_plan(**kwargs)


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
    return shape.execute_shape(plan() if frozen is None else frozen, root, now=NOW,
        credential_resolver=resolver or (lambda provider: KEY), transport=transport)


def test_rich_shape_observes_singleton_file_descriptor_without_literal_values():
    observed = shape.inspect_metadata(BODY)
    assert observed["profile"] == "table_files_singleton_v1"
    assert observed["classification"] == "metadata_shape_observed"
    nodes = {node["path"]: node for node in observed["nodes"]}
    assert nodes["root"]["fields"]["table"] == "string"
    assert nodes["root/files"]["kind"] == "array"
    assert nodes["root/files"]["length"] == 1
    assert nodes["root/files/0"]["fields"]["name"] == "string"
    assert nodes["root/files/0"]["components"]["size_valid"] is True
    assert observed["metadata"] == {"metadata_shape_observed": True,
        "size_bytes": 1234, "snapshot_utc": "2026-10-06T12:00:00+00:00"}
    assert "SYNTHETIC-private" not in json.dumps(observed)


def test_flat_shape_stays_explicitly_separate_from_new_envelope():
    observed = shape.inspect_metadata(dict(FILE, table="tickers"))
    assert observed["profile"] == "flat_metadata_v1"
    assert observed["metadata"]["metadata_shape_observed"] is True


def test_unknown_names_and_values_are_only_bounded_type_counts():
    observed = shape.inspect_metadata({"table": "PRIVATE-TABLE", "PRIVATE-NAME": {"PRIVATE": "VALUE"}})
    node = observed["nodes"][0]
    assert node["unknown_key_count"] == 1
    assert node["unknown_types"] == {"object": 1}
    assert observed["table_literal"] == "other"
    assert "PRIVATE" not in json.dumps(observed)


@pytest.mark.parametrize("wrapper", ["data", "results", "result"])
def test_potential_row_arrays_stay_opaque(wrapper):
    class UnreadRow(dict):
        def items(self):
            pytest.fail("row items processed")
        def values(self):
            pytest.fail("row values processed")
    observed = shape.inspect_metadata({"table": "tickers", wrapper: [UnreadRow(PRIVATE="VALUE")]})
    node = next(node for node in observed["nodes"] if node["path"] == "root/" + wrapper)
    assert node["opaque"] is True and node["length"] == 1
    assert "PRIVATE" not in json.dumps(observed)
    assert observed["metadata"]["metadata_shape_observed"] is False


def test_file_array_non_descriptor_refuses_without_inspecting_row_values():
    observed = shape.inspect_metadata({"table": "tickers", "files": [{"ticker": "PRIVATE", "name": "PRIVATE"}]})
    assert observed["classification"] == "metadata_shape_unmapped"
    assert next(node for node in observed["nodes"] if node["path"] == "root/files")["opaque"] is True
    assert not any(node["path"] == "root/files/0" for node in observed["nodes"])
    assert "PRIVATE" not in json.dumps(observed)


def test_row_like_object_stays_opaque_before_components(monkeypatch):
    row = {"ticker": "PRIVATE", "name": "PRIVATE", "size": 12}
    original = shape._components
    def components(body):
        if body is row:
            pytest.fail("row values semantically examined")
        return original(body)
    monkeypatch.setattr(shape, "_components", components)
    observed = shape.inspect_metadata({"table": "tickers", "data": row})
    node = next(node for node in observed["nodes"] if node["path"] == "root/data")
    assert node["opaque"] is True and node["row_shape_refused"] is True
    assert "fields" not in node and "PRIVATE" not in json.dumps(observed)


def test_custom_table_cannot_forge_literal_or_verified_metadata():
    class Forged:
        def __eq__(self, _value):
            pytest.fail("untrusted equality evaluated")
    observed = shape.inspect_metadata(dict(FILE, table=Forged()))
    assert observed["table_literal"] == "not_string"
    assert observed["metadata"]["metadata_shape_observed"] is False


@pytest.mark.parametrize("body", [
    dict(BODY, error="PRIVATE"),
    {"table": "tickers", "metadata": {"error": {"code": "INVALID_API_KEY"}}},
    {"table": "tickers", "files": [dict(FILE, error={"message": "PRIVATE"})]},
])
def test_nested_or_mixed_error_prevents_metadata_observation(body):
    observed = shape.inspect_metadata(body)
    assert observed["classification"] == "application_error"
    assert observed["metadata"]["metadata_shape_observed"] is False
    assert "PRIVATE" not in json.dumps(observed)


@pytest.mark.parametrize("inactive", [False, "", 0, [], {}, None])
def test_inactive_error_is_not_fabricated_as_rejection(inactive):
    observed = shape.inspect_metadata(dict(BODY, error=inactive))
    assert observed["application_error"] is None
    assert observed["metadata"]["metadata_shape_observed"] is False  # non-exact frozen profile


@pytest.mark.parametrize("changes", [
    {"size": True}, {"size": Decimal("1234")}, {"size": -1},
    {"modified": "2026-10-06T12:00:00"}, {"name": ""},
])
def test_invalid_metadata_components_do_not_become_verified_mapping(changes):
    observed = shape.inspect_metadata({"table": "tickers", "files": [dict(FILE, **changes)]})
    assert observed["metadata"]["metadata_shape_observed"] is False


def test_alias_types_remain_visible_but_no_mapping_is_invented():
    observed = shape.inspect_metadata({"table": "tickers", "file": {
        "filename": "PRIVATE.zip", "size": 1234, "lastModified": "PRIVATE-CLOCK", "url": "PRIVATE-URL"}})
    node = next(node for node in observed["nodes"] if node["path"] == "root/file")
    assert node["fields"]["filename"] == node["fields"]["lastModified"] == node["fields"]["url"] == "string"
    assert observed["profile"] == "unmapped"
    assert "PRIVATE" not in json.dumps(observed)


def test_file_object_fixed_selectors_and_metadata_wrapper_are_observed():
    observed = shape.inspect_metadata({"table": "tickers", "files": {"full": {
        "metadata": dict(FILE, years="full", type="PRIVATE-TYPE", url="PRIVATE-URL")}}})
    nodes = {node["path"]: node for node in observed["nodes"]}
    assert nodes["root/files"]["kind"] == "object"
    assert nodes["root/files/full/metadata"]["fields"]["type"] == "string"
    assert nodes["root/files/full/metadata"]["selector"] == "full"
    assert observed["profile"] == "unmapped"
    assert "PRIVATE" not in json.dumps(observed)


def test_file_array_closed_nested_metadata_is_not_hidden_as_a_row():
    observed = shape.inspect_metadata({"table": "tickers", "files": [{"metadata": FILE}]})
    nodes = {node["path"]: node for node in observed["nodes"]}
    assert nodes["root/files"]["opaque"] is False
    assert nodes["root/files/0/metadata"]["components"]["modified_utc_valid"] is True
    assert observed["metadata"]["metadata_shape_observed"] is False


@pytest.mark.parametrize("years, expected", [("full", "full"), (5, "5"), (10, "10"),
    ("5", "5"), ("PRIVATE", "other"), (True, "not_selector"), (None, "not_selector")])
def test_descriptor_selector_is_closed_and_not_an_authority_claim(years, expected):
    observed = shape.inspect_metadata({"table": "tickers", "files": [dict(FILE, years=years)]})
    assert observed["nodes"][2]["selector"] == expected
    assert observed["profile"] == "unmapped"
    assert "PRIVATE" not in json.dumps(observed)


def test_shape_budget_and_multifile_ambiguity_fail_closed():
    observed = shape.inspect_metadata({"table": "tickers", "files": [FILE] * 9})
    assert observed["profile"] == "unmapped"
    assert next(node for node in observed["nodes"] if node["path"] == "root/files")["opaque"] is True
    observed = shape.inspect_metadata({"table": "tickers", "files": [FILE, FILE]})
    assert observed["metadata"]["metadata_shape_observed"] is False


def test_plan_has_only_one_status_request_and_no_data_authority():
    body = plan().body()
    assert body["shape_id"] == "TPR-SHARADAR-SHAPE-20261007-001"
    assert body["requests"] == [audit.REQUESTS[1].body()]
    assert body["limits"]["requests"] == 1 and body["limits"]["rows"] == 0
    assert all(value is False for value in body["authority"].values())


@pytest.mark.parametrize("changes", [
    {"code_sha256": True}, {"git_sha": "A" * 40}, {"mode": "unknown"},
    {"expires_utc": NOW.isoformat()}, {"expires_utc": (NOW + timedelta(hours=49)).isoformat()},
])
def test_invalid_plan_refuses(changes):
    with pytest.raises(audit.SourceAuditError):
        plan(**changes)


def test_rehashed_extra_policy_field_refuses_before_claim(private_root):
    frozen = plan()
    payload = audit._canonical(dict(frozen.body(), extra=True))
    forged = replace(frozen, payload=payload, sha256=hashlib.sha256(payload).hexdigest())
    with pytest.raises(audit.SourceAuditError):
        execute(private_root, frozen=forged)
    assert list(private_root.iterdir()) == []


def test_claim_precedes_lookup_and_one_shot_is_not_renewed(private_root):
    def resolver(provider):
        assert provider == "sharadar"
        assert (private_root / (shape.SHAPE_ID + ".spent.json")).exists()
        return KEY
    execute(private_root, resolver=resolver)
    with pytest.raises(audit.SourceAuditError, match="already spent"):
        execute(private_root, frozen=plan(code_sha256="a" * 64), resolver=lambda _: pytest.fail("lookup twice"))


def test_publication_is_sanitized_private_and_does_not_admit_backtesting(private_root, capsys):
    calls = []
    result = execute(private_root, calls=calls)
    report = json.loads(result.payload)
    assert calls == [(audit.REQUESTS[1], KEY)]
    assert report["provider_requests"] == 0 and report["fixture_transport_calls"] == 1
    assert report["credential_state"] == "not_proven"
    assert report["real_development_backtest_ready"] is False
    assert report["diagnosis"]["profile"] == "table_files_singleton_v1"
    assert report["provider"]["response_sha256"] == hashlib.sha256(json.dumps(BODY).encode()).hexdigest()
    assert report["provider"]["authenticated_access_observed"] is False
    for file in private_root.iterdir():
        assert KEY.encode() not in file.read_bytes() and b"SYNTHETIC-private" not in file.read_bytes()
        assert file.stat().st_mode & 0o777 == 0o600
    assert result.aggregate_path.read_bytes() == result.payload
    assert json.loads(result.terminal_path.read_bytes())["aggregate_sha256"] == result.sha256
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("payload", [
    b'{"files":[{"name":"SYNTHETIC_SHARADAR_SHAPE_KEY"}]}',
    b'{"files":[{"name":"SYNTHETIC_SHARADAR_SHAPE_\\u004bEY"}]}',
])
def test_secret_echo_refuses_before_hash_or_shape(private_root, payload):
    report = json.loads(execute(private_root, response=audit.AuditResponse(200, (), payload)).payload)
    assert report["provider"]["response_sha256"] is None
    assert report["provider"]["disposition"] == "credential_echo_refused"
    assert report["diagnosis"]["nodes"] == []


@pytest.mark.parametrize("body", [
    {"table": "tickers", "data": [{"ticker": "SYNTHETIC", "price": 123}]},
    {"table": "tickers", "data": {"ticker": "SYNTHETIC", "name": "SYNTHETIC"}},
    {"table": "tickers", "PRIVATE-UNKNOWN": {"ticker": "SYNTHETIC"}},
    {"table": "tickers", "metadata": {"metadata": {"metadata": {"metadata": {"metadata": FILE}}}}},
])
def test_unexamined_or_row_like_body_has_no_durable_raw_identity(private_root, body):
    report = json.loads(execute(private_root, body=body).payload)
    assert report["provider"]["response_sha256"] is None
    assert report["diagnosis"]["nodes"]  # safe structural presence remains useful
    assert report["diagnosis"]["metadata"]["metadata_shape_observed"] is False
    assert "PRIVATE" not in json.dumps(report)


def test_transport_failure_and_interrupt_are_sanitized_and_spent(private_root):
    def transport(*_args):
        raise RuntimeError(KEY + " PRIVATE-URL")
    result = shape.execute_shape(plan(), private_root, now=NOW, credential_resolver=lambda _: KEY, transport=transport)
    assert json.loads(result.payload)["status"] == "FAILED"
    assert KEY.encode() not in result.payload and b"PRIVATE" not in result.payload
    with pytest.raises(audit.SourceAuditError, match="already spent"):
        execute(private_root)


def test_production_injections_refuse_before_claim(private_root):
    with pytest.raises(audit.SourceAuditError, match="offline fixture"):
        shape.execute_shape(plan("production"), private_root, now=NOW,
            credential_resolver=lambda _: KEY, transport=lambda *_: None)
    assert list(private_root.iterdir()) == []


def test_offline_root_and_actual_adapters_refuse(private_root):
    with pytest.raises(audit.SourceAuditError, match="production shape"):
        shape.execute_shape(plan(), audit.PRIVATE_ROOT, now=NOW,
            credential_resolver=lambda _: KEY, transport=lambda *_: None)
    with pytest.raises(audit.SourceAuditError, match="synthetic fixtures"):
        shape.execute_shape(plan(), private_root, now=NOW,
            credential_resolver=shape._production_credential, transport=lambda *_: None)


def test_source_identity_requires_this_module_and_old_auditor_hash(monkeypatch):
    checked = []
    monkeypatch.setattr(shape, "_verify_execution_identity", lambda body: checked.append(body))
    source = Path(shape.__file__)
    shape._verify_identity({"git_sha": "a" * 40, "code_sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    assert checked == [{"git_sha": "a" * 40, "code_sha256": shape.AUDITOR_CODE_SHA256}]
    with pytest.raises(audit.SourceAuditError, match="code identity mismatch"):
        shape._verify_identity({"git_sha": "a" * 40, "code_sha256": "f" * 64})


def test_identity_refuses_nonregular_file_before_read(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(shape, "_verify_execution_identity", lambda _: None)
    monkeypatch.setattr(shape.os, "open", lambda *_args: 918273)
    monkeypatch.setattr(shape.os, "fstat", lambda _: SimpleNamespace(st_mode=0o010600, st_size=4))
    monkeypatch.setattr(shape.os, "read", lambda *_args: pytest.fail("read nonregular source"))
    closed = []
    monkeypatch.setattr(shape.os, "close", closed.append)
    with pytest.raises(audit.SourceAuditError, match="code identity mismatch"):
        shape._verify_identity({"git_sha": "a" * 40, "code_sha256": "f" * 64})
    assert closed == [918273]


def test_interruption_has_terminal_and_no_relaunch(private_root):
    def interrupted(*_args):
        raise KeyboardInterrupt("PRIVATE-CONTENT")
    with pytest.raises(KeyboardInterrupt, match="one-shot scope remains spent"):
        shape.execute_shape(plan(), private_root, now=NOW,
            credential_resolver=lambda _: KEY, transport=interrupted)
    terminal = json.loads((private_root / (shape.SHAPE_ID + ".terminal.json")).read_bytes())
    assert terminal["status"] == "INTERRUPTED"
    with pytest.raises(audit.SourceAuditError, match="already spent"):
        execute(private_root)


@pytest.mark.parametrize("response", [
    audit.AuditResponse(200, (), b'{"table":"tickers","table":"PRIVATE"}'),
    audit.AuditResponse(200, (), b'{"bad":'),
    audit.AuditResponse(200, (), b'x' * 65536, "response_byte_limit_refused", 65536),
    audit.AuditResponse(302, (), b'', "redirect_refused"),
])
def test_refused_transport_or_invalid_json_never_reaches_shape(private_root, response):
    report = json.loads(execute(private_root, response=response).payload)
    assert report["provider"]["response_sha256"] is None
    assert report["diagnosis"]["nodes"] == []


@pytest.mark.parametrize("credential", [None, "NOT_SYNTHETIC_VALID_KEY", "SYNTHETIC_BAD\nHEADER"])
def test_offline_non_synthetic_credential_never_reaches_transport(private_root, credential):
    calls = []
    report = json.loads(execute(private_root, resolver=lambda _: credential, calls=calls).payload)
    assert calls == [] and report["provider"]["disposition"] == "credential_unavailable"


@pytest.mark.parametrize("clock", [NOW - timedelta(seconds=1), NOW + timedelta(hours=24), NOW.replace(tzinfo=None)])
def test_bad_execution_clock_refuses_before_claim(private_root, clock):
    with pytest.raises(audit.SourceAuditError):
        shape.execute_shape(plan(), private_root, now=clock,
            credential_resolver=lambda _: pytest.fail("lookup"), transport=lambda *_: pytest.fail("request"))
    assert list(private_root.iterdir()) == []
