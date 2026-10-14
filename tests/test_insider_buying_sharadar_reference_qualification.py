"""Invented Sharadar metadata and Keychain values only; deny process-tree network."""
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib import error

import pytest

if os.name != "posix":
    pytest.skip("IBWIN-CR01: reference qualification requires POSIX custody; Windows port deferred",
                allow_module_level=True)

from research import insider_buying_sharadar_reference_qualification as m


HEAD = "a" * 40
TOKEN = "invented_sharadar_key_1234"
AUDIT = "ib-sharadar-reference-invented"
BASELINE = {"root": "invented", "branch": m.LANE_BRANCH, "head": HEAD,
            "source_sha256": {"invented.py": "b" * 64}, "source_inventory_sha256": "c" * 64, "clean": True}
TICKERS = {"table": "tickers", "name": "tickers.csv.zip", "size": 1234,
           "sizeLabel": "1.21 KB", "modified": "2026-10-13T03:57:16.344000+00:00"}
ACTIONS = {"table": "actions", "files": [{"history": "full", "historyLabel": "Full History",
           "name": "actions.csv.zip", "size": 9876, "sizeLabel": "9.64 KB",
           "modified": "2026-10-13T03:57:16Z", "available": True}]}


def encode(value):
    return json.dumps(value, separators=(",", ":")).encode()


def credential():
    return m.KeychainCredential("sharadar", TOKEN, True)


def response(table, *, status=200, raw=None, complete=True, disposition=None):
    if raw is None:
        raw = encode(TICKERS if table == "tickers" else ACTIONS)
    return m.ProviderMetadataResponse(status, raw, complete, disposition)


def run(tmp_path, *, transport=None, reader=None, identity=None, audit_id=AUDIT):
    return m.run_qualification(audit_id, HEAD, root=tmp_path,
        identity=identity or (lambda head, root: dict(BASELINE)),
        credential_reader=reader or (lambda provider: credential()),
        transport=transport or (lambda table, token: response(table)),
        clock=lambda: "2026-10-13T00:00:00Z")


def directory(tmp_path):
    return tmp_path.joinpath(*m.ARTIFACT_PARTS, AUDIT)


def test_two_exact_requests_are_started_and_reserved_before_credential_or_dispatch(tmp_path):
    calls = []
    def reader(provider):
        target = directory(tmp_path)
        assert provider == "sharadar"
        assert (target.parent / "scope-reservation.json").is_file()
        assert (target / "reservation.json").is_file()
        assert (target / "credential-read-started.json").is_file()
        assert not any("-tickers-started" in name for name in os.listdir(target))
        calls.append("credential")
        return credential()
    def transport(table, token):
        target = directory(tmp_path)
        ordinal = 1 if table == "tickers" else 2
        started = json.loads((target / f"{ordinal:02d}-{table}-started.json").read_bytes())
        assert started["url"] == m.PROFILES[table][1]
        assert started["profile"] == m.PROFILES[table][0] and started["maximum_attempts"] == 1
        assert token.value == TOKEN and (target / "credential-read-completed.json").is_file()
        calls.append(table)
        return response(table)
    result = run(tmp_path, reader=reader, transport=transport)
    assert calls == ["credential", "tickers", "actions"]
    assert result["fixture_only"] is True
    assert result["planned_status_requests"] == result["transport_invocation_count"] == result["observed_status_metadata_count"] == 2
    assert result["disposition"] == "completed-status-qualification"
    assert [row["disposition"] for row in result["receipts"]] == ["current-reference-file-status-observed", "full-history-available-status-observed"]
    assert result["receipts"][1]["provider_reported_full_history_available"] is True
    assert all(result[flag] is False for flag in m.FALSE_FLAGS)
    assert result["source_table_rows_requested_or_downloaded"] is False
    assert result["research_looks"] == result["qc_jobs"] == result["backtests"] == 0
    assert TOKEN not in json.dumps(result)
    target = directory(tmp_path)
    assert (target / "01-tickers-response.json").read_bytes() == encode(TICKERS)
    assert (target / "02-actions-response.json").read_bytes() == encode(ACTIONS)
    assert json.loads((target / "complete.json").read_bytes()) == result
    for name, digest in result["published_leaf_sha256"].items():
        leaf = target / name
        assert hashlib.sha256(leaf.read_bytes()).hexdigest() == digest
        assert leaf.stat().st_mode & 0o777 == 0o600 and leaf.stat().st_nlink == 1
        assert TOKEN.encode() not in leaf.read_bytes()
    assert target.stat().st_mode & 0o777 == target.parent.stat().st_mode & 0o777 == 0o700


def test_provider_full_history_unavailable_is_retained_negative_metadata_not_authority(tmp_path):
    body = json.loads(encode(ACTIONS))
    body["files"][0]["available"] = False
    result = run(tmp_path, transport=lambda table, token: response(table, raw=encode(body) if table == "actions" else None))
    row = result["receipts"][1]
    assert row["disposition"] == "full-history-unavailable-status-observed"
    assert row["status_metadata_observed"] is True
    assert row["provider_reported_full_history_available"] is False
    assert row["body_sha256"] == hashlib.sha256(encode(body)).hexdigest()
    assert all(row[flag] is False for flag in m.FALSE_FLAGS)


@pytest.mark.parametrize("status", [301, 302, 400, 401, 403, 404, 429, 500, 503])
def test_non200_body_is_never_hashed_or_retained_and_stops_second_scope(tmp_path, status):
    calls = []
    def transport(table, token):
        calls.append(table)
        return response(table, status=status, raw=("private upstream " + TOKEN).encode())
    result = run(tmp_path, transport=transport)
    assert calls == ["tickers"] and result["transport_invocation_count"] == 1
    assert result["disposition"] == "stopped-status-qualification"
    row = result["receipts"][0]
    assert row["body_sha256"] is row["body_size_bytes"] is None
    assert row["response_body_retained"] is False and row["untrusted_error_body_hashed_or_retained"] is False
    assert result["receipts"][1]["transport_invocation_count"] == 0
    assert not (directory(tmp_path) / "01-tickers-response.json").exists()
    assert TOKEN not in json.dumps(result)


@pytest.mark.parametrize("raw", [b"not-json", b"[]", b"{}", b'{"table":"tickers","table":"tickers"}',
                             b'{"table":"tickers","size":NaN}', b'{"table":"tickers","size":1.1}'])
def test_invalid_successful_schema_is_not_hashed_or_retained(tmp_path, raw):
    result = run(tmp_path, transport=lambda table, token: response(table, raw=raw))
    assert result["observed_status_metadata_count"] == 0
    assert result["receipts"][0]["body_sha256"] is None
    assert not (directory(tmp_path) / "01-tickers-response.json").exists()


@pytest.mark.parametrize("table", ["tickers", "actions"])
@pytest.mark.parametrize("style", ["literal", "unicode", "percent", "dict-key", "nested"])
def test_credential_echo_is_refused_before_any_successful_body_hash(table, style):
    body = json.loads(encode(TICKERS if table == "tickers" else ACTIONS))
    if style == "dict-key":
        body[TOKEN] = "ignored"
    elif style == "nested":
        body["ignored"] = {"nested": [TOKEN]}
    else:
        body["ignored"] = TOKEN if style != "percent" else "".join("%" + format(ord(c), "02x") for c in TOKEN)
    raw = encode(body)
    if style == "unicode":
        raw = raw.replace(TOKEN.encode(), "".join("\\u" + format(ord(c), "04x") for c in TOKEN).encode())
    receipt, projection = m._receipt(table, response(table, raw=raw), credential())
    assert projection is None and receipt["disposition"] == "credential_echo_refused"
    assert receipt["body_sha256"] is receipt["body_size_bytes"] is None
    assert TOKEN not in json.dumps(receipt)


@pytest.mark.parametrize("field,bad", [("table", "actions"), ("table", True), ("name", "evil.csv.zip"),
    ("size", True), ("size", -1), ("size", 2**63), ("size", "1"), ("size", 1.5),
    ("sizeLabel", "secret"), ("sizeLabel", 123), ("modified", "2026-10-13"),
    ("modified", "2026-99-13T00:00:00Z"), ("modified", "2026-10-13T00:00:00-05:00"), ("modified", None)])
def test_tickers_exact_descriptor_types_and_utc_metadata(field, bad):
    body = dict(TICKERS)
    body[field] = bad
    receipt, projected = m._receipt("tickers", response("tickers", raw=encode(body)), credential())
    assert projected is None and receipt["body_sha256"] is None


@pytest.mark.parametrize("field,bad", [("history", "5y"), ("history", True), ("historyLabel", "5 Years"),
    ("name", "actions-5Y.csv.zip"), ("size", True), ("available", None), ("available", 1),
    ("available", "true"), ("modified", "2026-10-13T00:00:00")])
def test_actions_full_descriptor_has_no_inferred_availability(field, bad):
    body = json.loads(encode(ACTIONS))
    body["files"][0][field] = bad
    receipt, projected = m._receipt("actions", response("actions", raw=encode(body)), credential())
    assert projected is None and receipt["provider_reported_full_history_available"] is None


@pytest.mark.parametrize("files", [[], {}, None, [ACTIONS["files"][0], ACTIONS["files"][0]]])
def test_actions_requested_full_profile_rejects_missing_duplicate_or_broader_inventory(files):
    body = {"table": "actions", "files": files}
    receipt, projection = m._receipt("actions", response("actions", raw=encode(body)), credential())
    assert projection is None and receipt["body_sha256"] is None


@pytest.mark.parametrize("changed", [{"body_complete": False}, {"body": b"a" * (m.MAX_BODY_BYTES + 1)},
    {"disposition": "transport-error"}, {"disposition": "response-origin-mismatch"}])
def test_partial_oversized_or_transport_refused_response_has_no_body_hash(changed):
    from dataclasses import replace
    receipt, projection = m._receipt("tickers", replace(response("tickers"), **changed), credential())
    assert projection is None and receipt["body_sha256"] is None


@pytest.mark.parametrize("changed", [{"status": True}, {"status": 1999}, {"body": "secret"},
    {"body_complete": 1}, {"disposition": "secret"}, {"status": None}, {"status": None, "body": b""}])
def test_bad_transport_result_preserves_started_scope(changed):
    from dataclasses import replace
    with pytest.raises(m.SharadarReferenceQualificationError, match="invalid_transport_result_started_reservation_preserved"):
        m._receipt("tickers", replace(response("tickers"), **changed), credential())


def test_missing_keychain_consumes_zero_http_and_records_both_unattempted_scopes(tmp_path):
    def reader(provider):
        raise m.KeychainCredentialError("keychain_item_missing")
    result = run(tmp_path, reader=reader, transport=lambda *a: pytest.fail("provider call"))
    assert result["transport_invocation_count"] == result["observed_status_metadata_count"] == 0
    assert result["credential_disposition"] == "keychain_item_missing"
    assert all(row["disposition"] == "not-attempted-after-prior-refusal" for row in result["receipts"])


@pytest.mark.parametrize("item", [TOKEN, None, m.KeychainCredential("fmp", TOKEN, True),
    m.KeychainCredential("sharadar", "bad\r\nheader", True), m.KeychainCredential("sharadar", "test-api-key", True),
    m.KeychainCredential("sharadar", TOKEN, 1)])
def test_invalid_reader_results_do_not_invoke_transport(tmp_path, item):
    result = run(tmp_path, reader=lambda provider: item, transport=lambda *a: pytest.fail("provider call"))
    assert result["transport_invocation_count"] == 0 and result["credential_disposition"] == "credential_read_refused"


@pytest.mark.parametrize("exception", [RuntimeError(TOKEN), m.KeychainCredentialError(TOKEN)])
def test_reader_failures_never_echo_secret(tmp_path, exception):
    def reader(provider):
        raise exception
    result = run(tmp_path, reader=reader)
    assert result["credential_disposition"] == "credential_read_refused" and TOKEN not in json.dumps(result)


def test_injection_cannot_fall_through_to_actual_keychain_or_actual_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "read_keychain_credential", lambda *a: pytest.fail("actual Keychain"))
    monkeypatch.setattr(m, "_default_transport", lambda *a, **k: pytest.fail("actual provider"))
    with pytest.raises(m.SharadarReferenceQualificationError, match="fixture_requires_invented_credential_reader"):
        m.run_qualification(AUDIT, HEAD, root=tmp_path, transport=lambda *a: response("tickers"))
    with pytest.raises(m.SharadarReferenceQualificationError, match="fixture_requires_invented_transport"):
        m.run_qualification(AUDIT, HEAD, root=tmp_path, credential_reader=lambda *a: credential())
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_completed_or_ambiguous_scope_cannot_resume_under_new_id(tmp_path):
    run(tmp_path)
    with pytest.raises(m.SharadarReferenceQualificationError, match="existing_completed_or_ambiguous_scope_refused"):
        run(tmp_path, audit_id=AUDIT + "-different", reader=lambda *a: pytest.fail("second credential read"))


def test_source_or_journal_change_after_start_prevents_dispatch(tmp_path):
    calls = []
    def reader(provider):
        (directory(tmp_path) / "reservation.json").write_bytes(b"tampered")
        return credential()
    with pytest.raises(m.SharadarReferenceQualificationError, match="private_journal_custody_refused"):
        run(tmp_path, reader=reader, transport=lambda *a: calls.append(a))
    assert calls == []
    assert (directory(tmp_path) / "credential-read-started.json").exists()
    assert not (directory(tmp_path) / "complete.json").exists()


def test_displaced_parent_directory_fd_is_not_admitted(tmp_path):
    def transport(table, token):
        parent = directory(tmp_path).parent
        parent.rename(parent.with_name(parent.name + "-displaced"))
        parent.mkdir(mode=0o700)
        return response(table)
    with pytest.raises(m.SharadarReferenceQualificationError, match="private_journal_custody_refused"):
        run(tmp_path, transport=transport)
    assert not (directory(tmp_path) / "complete.json").exists()


def test_private_extra_leaf_or_symlink_is_refused(tmp_path):
    def transport(table, token):
        (directory(tmp_path) / "extra").symlink_to("reservation.json")
        return response(table)
    with pytest.raises(m.SharadarReferenceQualificationError, match="private_journal_custody_refused"):
        run(tmp_path, transport=transport)


def test_header_status_scope_is_fixed_in_immutable_mapping():
    assert m.PROFILES["tickers"][1] == "https://api.sharadar.com/v1.0/data/tickers?status=True"
    assert m.PROFILES["actions"][1] == "https://api.sharadar.com/v1.0/data/actions?status=True&years=full"
    assert len(m.SOURCE_FILES) == len(set(m.SOURCE_FILES)) == 7
    assert "research/insider_buying_keychain_credentials.py" in m.SOURCE_FILES
    with pytest.raises(TypeError):
        m.PROFILES["actions"] = ("evil", "https://evil.example")


def actual_transport_context(monkeypatch, table):
    reservation = {"identity": BASELINE, "fixture_only": False, "owner_direction": m.OWNER_DIRECTION,
        "requests": [{"table": name, "profile": profile, "method": "GET", "url": url, "maximum_attempts": 1}
                     for name, (profile, url) in m.PROFILES.items()]}
    started = {"profile": m.PROFILES[table][0], "url": m.PROFILES[table][1],
               "maximum_attempts": 1, "reservation_sha256": "d" * 64}
    ordinal = 1 if table == "tickers" else 2
    published = {"reservation.json": "d" * 64, "credential-read-started.json": "a" * 64,
                 "credential-read-completed.json": "b" * 64,
                 f"{ordinal:02d}-{table}-started.json": "e" * 64}
    if table == "actions":
        published.update({name: "c" * 64 for name in ("01-tickers-started.json", "01-tickers-response.json",
                         "01-tickers-metadata.json", "01-tickers-completed.json")})
    credential_completed = {"schema": m.SCHEMA, "fixture_only": False, "credential_read_observed": True,
                            "started_sha256": published["credential-read-started.json"],
                            "disposition": "configured-keychain-credential-read"}
    monkeypatch.setattr(m, "_identity", lambda *a, **k: BASELINE)
    monkeypatch.setattr(m, "_check_journal", lambda *a, **k: None)
    monkeypatch.setattr(m, "_read_leaf", lambda directory, name, limit: encode(
        reservation if name == "reservation.json" else credential_completed if name == "credential-read-completed.json" else started))
    return {"expected_head": HEAD, "baseline": BASELINE, "parent": 1, "directory": 2,
            "audit_id": AUDIT, "latch_sha": "f" * 64, "published": published}


class Stream(io.BytesIO):
    def __init__(self, body, table, status=200):
        super().__init__(body)
        self.table, self.status = table, status
        self.headers = {"Content-Length": str(len(body))}
        self.read_calls = 0
    def getcode(self):
        return self.status
    def geturl(self):
        return m.PROFILES[self.table][1]
    def read(self, count=-1):
        self.read_calls += 1
        return super().read(count)


@pytest.mark.parametrize("table", ["tickers", "actions"])
def test_default_transport_tls_empty_proxy_exact_header_and_no_query_key(monkeypatch, table):
    context = actual_transport_context(monkeypatch, table)
    stream, calls, handlers = Stream(encode(TICKERS if table == "tickers" else ACTIONS), table), [], []
    def opener(*items):
        handlers.extend(items)
        return SimpleNamespace(open=lambda item, timeout: (calls.append((item, timeout)), stream)[1])
    monkeypatch.setattr(m.request, "build_opener", opener)
    result = m._default_transport(table, m.KeychainCredential("sharadar", TOKEN, False), **context)
    assert result.status == 200 and result.body_complete is True
    item, timeout = calls[0]
    assert item.full_url == m.PROFILES[table][1] and TOKEN not in item.full_url
    assert item.get_method() == "GET" and item.get_header("X-api-key") == TOKEN
    assert item.get_header("Accept") == "application/json" and item.get_header("Accept-encoding") == "identity"
    assert timeout == 15 and handlers[0].proxies == {} and isinstance(handlers[1], m._DenyRedirect)
    assert handlers[2]._context.verify_mode == m.ssl.CERT_REQUIRED
    assert handlers[2]._context.check_hostname is True
    assert stream.closed


@pytest.mark.parametrize("status", [301, 302, 401, 403, 429, 500])
def test_default_non200_never_reads_stream(monkeypatch, status):
    context = actual_transport_context(monkeypatch, "tickers")
    stream = Stream(("secret " + TOKEN).encode(), "tickers", status)
    monkeypatch.setattr(m.request, "build_opener", lambda *a: SimpleNamespace(open=lambda *a, **k: stream))
    result = m._default_transport("tickers", m.KeychainCredential("sharadar", TOKEN, False), **context)
    assert result.body == b"" and result.body_complete is False and stream.read_calls == 0 and stream.closed


@pytest.mark.parametrize("exception", [TimeoutError(TOKEN), error.URLError(TOKEN), error.URLError(TimeoutError(TOKEN))])
def test_default_network_exception_is_sanitized(monkeypatch, exception):
    context = actual_transport_context(monkeypatch, "tickers")
    def refuse(*args, **kwargs):
        raise exception
    monkeypatch.setattr(m.request, "build_opener", lambda *a: SimpleNamespace(open=refuse))
    result = m._default_transport("tickers", m.KeychainCredential("sharadar", TOKEN, False), **context)
    assert result.body == b"" and result.status is None and TOKEN not in repr(result)


def test_default_transport_refuses_fixture_credentials_before_opener(monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("opener"))
    with pytest.raises(m.SharadarReferenceQualificationError, match="real_transport_profile_refused"):
        m._default_transport("tickers", credential(), expected_head=HEAD, baseline=BASELINE,
            parent=1, directory=2, audit_id=AUDIT, latch_sha="d" * 64, published={})


def test_real_identity_rejects_dirty_tree_before_source_or_credential_reads(monkeypatch):
    def git(root, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(m.LANE_ROOT).encode()
        if args == ("branch", "--show-current"):
            return m.LANE_BRANCH.encode()
        if args == ("rev-parse", "HEAD"):
            return HEAD.encode()
        return b"?? invented-uncommitted.py\n"
    monkeypatch.setattr(m, "_git", git)
    monkeypatch.setattr(m, "_read_leaf", lambda *a, **k: pytest.fail("source read"))
    with pytest.raises(m.SharadarReferenceQualificationError, match="clean_committed_lane_required"):
        m._identity(HEAD)


@pytest.mark.parametrize("audit_id", [None, "secret", "ib-sharadar-reference-A", "ib-sharadar-reference-../x"])
def test_invalid_audit_id_is_refused_before_identity(audit_id):
    with pytest.raises(m.SharadarReferenceQualificationError, match="audit_id_format_refused"):
        m.run_qualification(audit_id, HEAD, identity=lambda *a, **k: pytest.fail("identity"))


def test_main_reports_only_sanitized_summary_and_has_no_credential_cli(monkeypatch, capsys):
    monkeypatch.setattr(m, "run_qualification", lambda *a: {"disposition": "completed-status-qualification", "fixture_only": True})
    assert m.main(["--audit-id", AUDIT, "--expected-head", HEAD]) == 0
    assert TOKEN not in capsys.readouterr().out
    with pytest.raises(SystemExit):
        m.main(["--audit-id", AUDIT, "--expected-head", HEAD, "--token", TOKEN])


def test_typed_fixture_transport_error_cannot_echo_secret(tmp_path):
    def transport(*args):
        raise m.SharadarReferenceQualificationError(TOKEN)
    result = run(tmp_path, transport=transport)
    assert result["disposition"] == "stopped-status-qualification"
    assert result["receipts"][0]["disposition"] == "transport-error"
    assert TOKEN not in json.dumps(result)


def test_default_transport_requires_completed_credential_read_before_opener(monkeypatch):
    context = actual_transport_context(monkeypatch, "tickers")
    del context["published"]["credential-read-completed.json"]
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("unsealed credential read reached opener"))
    with pytest.raises(m.SharadarReferenceQualificationError, match="real_transport_started_journal_required"):
        m._default_transport("tickers", m.KeychainCredential("sharadar", TOKEN, False), **context)


# Section 194 (Claude review): fixture seams cannot reach the real lane scope or the real key.
@pytest.mark.parametrize("lane_root", ["default", "inside", "parent"])
def test_fixture_run_cannot_create_or_consume_the_real_lane_scope(monkeypatch, lane_root):
    monkeypatch.setattr(m, "_mkdir_chain", lambda *a, **k: pytest.fail("real lane namespace touched"))
    kwargs = {} if lane_root == "default" else {
        "root": m.LANE_ROOT / "artifacts" if lane_root == "inside" else m.LANE_ROOT.parent}
    with pytest.raises(m.SharadarReferenceQualificationError, match="^fixture_root_overlaps_lane_refused$"):
        m.run_qualification(AUDIT, HEAD, identity=lambda head, root: dict(BASELINE),
            credential_reader=lambda provider: credential(), transport=lambda table, token: response(table),
            clock=lambda: "2026-10-13T00:00:00Z", **kwargs)


@pytest.mark.parametrize("real", ["reader", "transport"])
def test_fixture_run_cannot_be_handed_the_real_keychain_reader_or_transport(tmp_path, monkeypatch, real):
    from research import insider_buying_keychain_credentials as keychain
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("real opener"))
    monkeypatch.setattr(keychain.subprocess, "Popen", lambda *a, **k: pytest.fail("real Keychain read"))
    with pytest.raises(m.SharadarReferenceQualificationError, match="^fixture_real_callback_refused$"):
        m.run_qualification(AUDIT, HEAD, root=tmp_path, identity=lambda head, root: dict(BASELINE),
            credential_reader=m.read_keychain_credential if real == "reader" else (lambda provider: credential()),
            transport=m._default_transport if real == "transport" else (lambda table, token: response(table)),
            clock=lambda: "2026-10-13T00:00:00Z")
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()
