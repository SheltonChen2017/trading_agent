"""Invented one-page responses only; all tests run with OS network denial."""
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import stat

import pytest

from research import insider_buying_benzinga_earnings_access as m
from research.insider_buying_provider_metadata_transport import ProviderMetadataResponse


AUDIT = "ib-earnings-access-fixture-once"
HEAD = "a" * 40
KEY = "fixture-private-credential-not-a-real-key"
NOW = "2026-10-07T12:00:00Z"


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def body(**changes):
    row = {"benzinga_id": "invented-id", "ticker": "INVENTED", "company_name": "Invented source fixture",
           "date": "2010-04-30", "date_status": "confirmed", "time": "07:30:00",
           "last_updated": "2026-10-06T14:00:00Z", "actual_eps": -12.3456,
           "actual_revenue": 123456789, "eps_surprise_percent": 654.321, "fiscal_year": 2010}
    row.update(changes)
    return {"status": "OK", "results": [row], "count": 1, "request_id": "invented-request"}


def identity(expected_head, *, root):
    assert expected_head == HEAD
    return {"root": str(root), "branch": m.LANE_BRANCH, "head": HEAD, "status_sha256": "b" * 64,
            "source_sha256": {"invented-source": "c" * 64}}


def directory(root):
    return root.joinpath(*m.ARTIFACT_PARTS, AUDIT)


def run(tmp_path, *, raw=None, status=200, response=None, transport=None, environ=None, identity_callback=identity):
    calls = []
    if raw is None: raw = encoded(body())
    def supplied(item):
        calls.append(item)
        assert directory(tmp_path).joinpath("started.json").is_file()
        m._validate_request(item)
        return ProviderMetadataResponse(status, raw) if response is None else response
    result = m.run_earnings_access_audit(AUDIT, HEAD, root=tmp_path, identity=identity_callback,
        transport=supplied if transport is None else transport,
        environ={"MASSIVE_API_KEY": KEY} if environ is None else environ, clock=lambda: NOW)
    return result, calls


def test_one_fixed_request_private_raw_independent_replay_and_no_financial_output(tmp_path):
    raw = encoded(body())
    result, calls = run(tmp_path, raw=raw)
    assert len(calls) == 1 and calls[0].url == m.REQUEST_URL
    assert calls[0].method == "GET" and calls[0].timeout_seconds == 15
    assert "limit=1&sort=date.asc" in calls[0].url
    assert KEY not in repr(calls[0])
    assert result["receipt"]["disposition"] == "product-access-source-schema-observed"
    assert result["receipt"]["body_size_bytes"] == len(raw)
    assert result["receipt"]["body_sha256"] == hashlib.sha256(raw).hexdigest()
    schema = result["receipt"]["source_schema"]
    assert schema["results_count"] == 1 and schema["schedule_dates"] == ["2010-04-30"]
    assert schema["last_updated_instants_utc"] == ["2026-10-06T14:00:00Z"]
    assert schema["schedule_time_present"] is True
    assert schema["financial_values_evaluated_or_reported"] is False
    output = encoded(result)
    assert b"-12.3456" not in output and b"123456789" not in output and b"654.321" not in output and KEY.encode() not in output
    folder = directory(tmp_path)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert {p.name for p in folder.iterdir()} == {"reservation.json", "started.json", "successful-response.json", "complete.json"}
    for leaf in folder.iterdir():
        assert stat.S_IMODE(leaf.stat().st_mode) == 0o600 and leaf.stat().st_nlink == 1
    assert (folder / "successful-response.json").read_bytes() == raw
    assert m.replay_supplied_earnings_schema(raw, hashlib.sha256(raw).hexdigest()) == schema
    complete = json.loads((folder / "complete.json").read_bytes())
    assert complete["raw_response_retained_privately"] is True and complete["error_response_body_persisted"] is False
    assert complete["injected_transport"] is True
    assert result["looks_jobs_backtests"] == [0, 0, 0] and result["research_ready"] is False
    for name in ("full_history_coverage_verified", "original_publication_or_pit_verified", "rights_verified",
        "qc_entitlement_verified", "research_ready", "strategy_outcome_access_authorized", "qc_backtest_authorized",
        "source_pit_rights_look_qc_backtest_execution_authority"):
        assert result["receipt"][name] is False


def test_reservation_and_started_are_fsynced_before_even_credential_lookup(tmp_path, monkeypatch):
    events = []
    original = m._exclusive_json
    def publish(fd, name, value):
        result = original(fd, name, value)
        events.append(name + "-fsynced")
        return result
    monkeypatch.setattr(m, "_exclusive_json", publish)
    class Environment(dict):
        def get(self, name, default=None):
            assert events == ["reservation.json-fsynced", "started.json-fsynced"]
            assert directory(tmp_path).joinpath("started.json").is_file()
            events.append("credential-read")
            return KEY
    def transport(item):
        assert events[-1] == "credential-read"
        events.append("transport-once")
        return ProviderMetadataResponse(200, encoded(body()))
    result, _ = run(tmp_path, environ=Environment(), transport=transport)
    assert result["receipt"]["disposition"] == "product-access-source-schema-observed"
    assert events == ["reservation.json-fsynced", "started.json-fsynced", "credential-read", "transport-once", "complete.json-fsynced"]


def test_missing_credential_consumes_zero_transport_but_immutable_attempt_stays_reserved(tmp_path):
    result, calls = run(tmp_path, environ={})
    assert not calls
    assert result["receipt"]["disposition"] == "credentials-unavailable-or-invalid"
    assert result["receipt"]["body_sha256"] is None
    assert directory(tmp_path).joinpath("started.json").is_file()
    with pytest.raises(m.EarningsAccessAuditError, match="existing-completed-or-ambiguous"):
        run(tmp_path)


@pytest.mark.parametrize("status,disposition", [(401, "configured-product-request-refused"), (403, "configured-product-request-refused"),
    (429, "rate-limited-no-retry"), (500, "http-error"), (301, "redirect-refused")])
def test_error_body_never_persisted_or_echoed_and_no_retry(tmp_path, status, disposition):
    secret_error = encoded({"error": KEY, "private-row": "not permissible output"})
    result, calls = run(tmp_path, status=status, raw=secret_error)
    assert len(calls) == 1 and result["receipt"]["disposition"] == disposition
    assert result["successful_response_sha256"] is None
    assert result["receipt"]["body_size_bytes"] == len(secret_error)
    assert KEY.encode() not in encoded(result)
    for leaf in directory(tmp_path).iterdir():
        assert KEY.encode() not in leaf.read_bytes() and b"not permissible output" not in leaf.read_bytes()
    assert not directory(tmp_path).joinpath("successful-response.json").exists()


@pytest.mark.parametrize("disposition", sorted(m._TRANSPORT_FAILURES))
def test_failed_or_partial_transport_never_persists_body_or_retries(tmp_path, disposition):
    result, calls = run(tmp_path, response=ProviderMetadataResponse(200, KEY.encode(), False, disposition))
    assert len(calls) == 1 and result["receipt"]["disposition"] == disposition
    assert result["successful_response_sha256"] is None
    assert KEY.encode() not in encoded(result)


def test_exception_is_not_provider_text_and_no_retry(tmp_path):
    calls = []
    def fail(item):
        calls.append(item)
        raise RuntimeError(KEY)
    result, _ = run(tmp_path, transport=fail)
    assert len(calls) == 1 and result["receipt"]["disposition"] == "transport-error"
    assert KEY.encode() not in encoded(result)


@pytest.mark.parametrize("response", [None, {}, ProviderMetadataResponse(True, b"{}"), ProviderMetadataResponse(200, bytearray(b"{}")),
    ProviderMetadataResponse(200, b"{}", 1), ProviderMetadataResponse(200, b"{}", True, []),
    ProviderMetadataResponse(200, b"{}", True, "not-allowed")])
def test_arbitrary_transport_results_are_refused_safely(tmp_path, response):
    result, _ = run(tmp_path, transport=lambda _: response)
    assert result["receipt"]["disposition"] == "transport-result-refused"
    assert result["successful_response_sha256"] is None


def test_one_mebibyte_cap_and_no_oversized_body_retention(tmp_path):
    result, calls = run(tmp_path, raw=b"x" * (m.MAX_BODY_BYTES + 20))
    assert len(calls) == 1 and result["receipt"]["disposition"] == "oversized-response"
    assert result["receipt"]["body_size_bytes"] == m.MAX_BODY_BYTES + 1
    assert not directory(tmp_path).joinpath("successful-response.json").exists()


@pytest.mark.parametrize("mutation", ("unknown-top", "unknown-row", "wrong-date", "bad-update", "bad-time", "bad-date-status",
    "financial-string", "two-rows", "credential-echo", "next-origin", "next-key", "status-error", "numeric-bool"))
def test_reconstructed_or_unsafe_success_body_is_not_retained(tmp_path, mutation):
    value = body()
    row = value["results"][0]
    if mutation == "unknown-top": value["errors"] = [KEY]
    if mutation == "unknown-row": row["api_key"] = KEY
    if mutation == "wrong-date": row["date"] = "2010-05-01"
    if mutation == "bad-update": row["last_updated"] = "2026-10-06"
    if mutation == "bad-time": row["time"] = "24:00:00"
    if mutation == "bad-date-status": row["date_status"] = "rumored"
    if mutation == "financial-string": row["actual_eps"] = "12.0"
    if mutation == "two-rows": value["results"] += value["results"]
    if mutation == "credential-echo": row["notes"] = KEY
    if mutation == "next-origin": value["next_url"] = "https://other.invalid/benzinga/v1/earnings?cursor=abc"
    if mutation == "next-key": value["next_url"] = "https://api.massive.com/benzinga/v1/earnings?cursor=abc&apiKey=secret"
    if mutation == "status-error": value["status"] = "ERROR"
    if mutation == "numeric-bool": row["actual_eps"] = True
    result, calls = run(tmp_path, raw=encoded(value))
    assert len(calls) == 1 and result["receipt"]["disposition"] != "product-access-source-schema-observed"
    assert result["successful_response_sha256"] is None
    assert not directory(tmp_path).joinpath("successful-response.json").exists()
    assert KEY.encode() not in encoded(result)


@pytest.mark.parametrize("raw", [b'{"status":"OK","status":"OK","results":[]}', b'{"status":"OK","results":[],"count":NaN}',
    b'{"status":"OK","results":[],"count":Infinity}', b'\xff', b'[]', b'{}'])
def test_duplicate_nonfinite_nonutf8_or_invalid_envelope_refused(tmp_path, raw):
    result, _ = run(tmp_path, raw=raw)
    assert result["successful_response_sha256"] is None


def test_empty_success_is_access_not_no_coverage_and_next_cursor_is_not_followed(tmp_path):
    value = {"status": "OK", "results": [], "next_url": "https://api.massive.com/benzinga/v1/earnings?cursor=opaque"}
    result, calls = run(tmp_path, raw=encoded(value))
    assert len(calls) == 1 and result["receipt"]["source_schema"]["results_count"] == 0
    assert result["receipt"]["source_schema"]["pagination_present_not_followed"] is True
    assert result["receipt"]["full_history_coverage_verified"] is False


@pytest.mark.parametrize("count", (-1, 1.5, 0, 2))
def test_advertised_count_is_an_exact_integer_matching_the_observed_one_page_rows(tmp_path, count):
    value = body()
    value["count"] = count
    result, _ = run(tmp_path, raw=encoded(value))
    assert result["receipt"]["disposition"] == "count-schema-refused"
    assert not directory(tmp_path).joinpath("successful-response.json").exists()


def test_current_update_timestamp_is_not_backdated_to_historical_earnings_knowledge(tmp_path):
    result, _ = run(tmp_path, raw=encoded(body(last_updated="2026-10-06T10:00:00-04:00")))
    schema = result["receipt"]["source_schema"]
    assert schema["schedule_dates"] == ["2010-04-30"]
    assert schema["last_updated_instants_utc"] == ["2026-10-06T14:00:00Z"]
    assert result["receipt"]["original_publication_or_pit_verified"] is False


@pytest.mark.parametrize("field", ("notes", "request_id"))
def test_unicode_escaped_credential_echo_cannot_be_retained_as_success(tmp_path, field):
    value = body()
    if field == "notes": value["results"][0][field] = KEY
    else: value[field] = KEY
    escaped = encoded(value).replace(KEY.encode(), b"\\u0066" + KEY[1:].encode())
    assert KEY.encode() not in escaped
    result, calls = run(tmp_path, raw=escaped)
    assert len(calls) == 1
    assert result["receipt"]["disposition"] == "credential-echo-refused"
    assert not directory(tmp_path).joinpath("successful-response.json").exists()


@pytest.mark.parametrize("name", ("reservation.json", "started.json"))
@pytest.mark.parametrize("tamper", ("bytes", "mode", "hardlink", "symlink", "extra-leaf"))
def test_concurrent_journal_corruption_blocks_completion_and_preserves_started(tmp_path, name, tamper):
    def corrupt(_):
        folder, leaf = directory(tmp_path), directory(tmp_path) / name
        if tamper == "bytes": leaf.write_bytes(b"{}")
        if tamper == "mode": leaf.chmod(0o644)
        if tamper == "hardlink": os.link(leaf, tmp_path / "linked-leaf")
        if tamper == "symlink":
            leaf.unlink()
            leaf.symlink_to(tmp_path / "outside")
        if tamper == "extra-leaf": (folder / "extra.json").write_bytes(b"{}")
        return ProviderMetadataResponse(200, encoded(body()))
    with pytest.raises(m.EarningsAccessAuditError, match="custody|private-audit-operation"):
        run(tmp_path, transport=corrupt)
    assert not directory(tmp_path).joinpath("complete.json").exists()
    assert not directory(tmp_path).joinpath("successful-response.json").exists()
    with pytest.raises(m.EarningsAccessAuditError, match="existing-completed-or-ambiguous"):
        run(tmp_path)


def test_ancestor_rename_replacement_cannot_publish_to_displaced_journal(tmp_path):
    original_parent = tmp_path.joinpath(*m.ARTIFACT_PARTS)
    def move(_):
        original_parent.rename(tmp_path / "displaced")
        original_parent.mkdir()
        return ProviderMetadataResponse(200, encoded(body()))
    with pytest.raises(m.EarningsAccessAuditError, match="ancestor-custody"):
        run(tmp_path, transport=move)
    assert not tmp_path.joinpath("displaced", AUDIT, "complete.json").exists()
    assert not tmp_path.joinpath("displaced", AUDIT, "successful-response.json").exists()


@pytest.mark.parametrize("part", m.ARTIFACT_PARTS)
def test_symlink_parent_refuses_before_loading_credentials_or_transport(tmp_path, part):
    parent = tmp_path
    for component in m.ARTIFACT_PARTS:
        if component == part:
            outside = tmp_path / "outside"
            outside.mkdir()
            (parent / component).symlink_to(outside, target_is_directory=True)
            break
        parent = parent / component
        parent.mkdir()
    class Environment(dict):
        def get(self, *_): pytest.fail("credential accessed")
    with pytest.raises(m.EarningsAccessAuditError):
        run(tmp_path, environ=Environment(), transport=lambda _: pytest.fail("transport called"))
    assert not (tmp_path / "outside" / AUDIT).exists()


def test_identity_change_after_transport_preserves_ambiguous_started_without_response_or_completion(tmp_path):
    switched = False
    def current(head, *, root):
        result = identity(head, root=root)
        if switched: result["head"] = "e" * 40
        return result
    def change(_):
        nonlocal switched
        switched = True
        return ProviderMetadataResponse(200, encoded(body()))
    with pytest.raises(m.EarningsAccessAuditError, match="lane-identity-changed"):
        run(tmp_path, transport=change, identity_callback=current)
    assert directory(tmp_path).joinpath("started.json").exists()
    assert not directory(tmp_path).joinpath("complete.json").exists()


@pytest.mark.parametrize("error_type", (OSError, TimeoutError, RuntimeError))
def test_initial_identity_failure_is_sanitized_before_journal_or_credential_access(tmp_path, error_type):
    def failure(*_, **__): raise error_type("INVENTED_PRIVATE_IDENTITY_DETAIL")
    with pytest.raises(m.EarningsAccessAuditError) as caught:
        run(tmp_path, identity_callback=failure)
    assert "INVENTED_PRIVATE_IDENTITY_DETAIL" not in str(caught.value)
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_named_complete_replacement_during_fstat_cannot_evade_held_descriptor_hash(tmp_path, monkeypatch):
    original = os.fstat
    switched = False
    def replace_named(fd):
        nonlocal switched
        info = original(fd)
        named = directory(tmp_path) / "complete.json"
        if not switched and named.exists() and named.stat().st_ino == info.st_ino:
            switched = True
            named.rename(tmp_path / "displaced-complete.json")
            named.write_bytes(b"{}")
            named.chmod(0o600)
        return info
    monkeypatch.setattr(m.os, "fstat", replace_named)
    with pytest.raises(m.EarningsAccessAuditError, match="custody"):
        run(tmp_path)
    assert switched
    assert directory(tmp_path).joinpath("complete.json").read_bytes() == b"{}"


def test_all_journal_leaf_reads_use_nofollow_nonblocking_flags(tmp_path, monkeypatch):
    original, reads = os.open, []
    def record(path, flags, *args, **kwargs):
        if (type(path) is str and path in {"reservation.json", "started.json", "successful-response.json", "complete.json"}
                and not flags & os.O_CREAT):
            reads.append(flags)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(m.os, "open", record)
    run(tmp_path)
    assert reads and all(flags & os.O_NOFOLLOW and flags & os.O_NONBLOCK for flags in reads)


def test_in_read_ancestor_displacement_is_rechecked_after_last_leaf(tmp_path, monkeypatch):
    original, switched = os.fstat, False
    def displace(fd):
        nonlocal switched
        info = original(fd)
        named = directory(tmp_path) / "complete.json"
        if not switched and named.exists() and named.stat().st_ino == info.st_ino:
            switched = True
            parent = tmp_path.joinpath(*m.ARTIFACT_PARTS)
            parent.rename(tmp_path / "displaced-during-read")
            parent.mkdir()
        return info
    monkeypatch.setattr(m.os, "fstat", displace)
    with pytest.raises(m.EarningsAccessAuditError, match="ancestor-custody"):
        run(tmp_path)
    assert switched
    assert not directory(tmp_path).joinpath("complete.json").exists()
    assert tmp_path.joinpath("displaced-during-read", AUDIT, "complete.json").exists()


def test_regular_leaf_replaced_by_fifo_between_stat_and_open_refuses_without_blocking(tmp_path, monkeypatch):
    original, switched = os.open, False
    def substitute(path, flags, *args, **kwargs):
        nonlocal switched
        named = directory(tmp_path) / "complete.json"
        if not switched and path == "complete.json" and not flags & os.O_CREAT and named.exists():
            assert flags & os.O_NONBLOCK  # never attempt a blocking FIFO open in a test
            switched = True
            named.rename(tmp_path / "fifo-displaced-complete.json")
            os.mkfifo(named, 0o600)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(m.os, "open", substitute)
    with pytest.raises(m.EarningsAccessAuditError, match="leaf-custody"):
        run(tmp_path)
    assert switched and stat.S_ISFIFO(directory(tmp_path).joinpath("complete.json").stat().st_mode)


@pytest.mark.parametrize("audit_id", ("../outside", "ib-earnings-access-", "wrong", True, []))
def test_invalid_audit_name_cannot_load_credential_or_create_journal(tmp_path, audit_id):
    with pytest.raises(m.EarningsAccessAuditError, match="audit-id-refused"):
        m.run_earnings_access_audit(audit_id, HEAD, root=tmp_path, identity=identity,
                                  transport=lambda _: pytest.fail("transport called"), environ={})
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_actual_transport_cannot_use_fixture_root_or_identity(tmp_path):
    with pytest.raises(m.EarningsAccessAuditError, match="real-transport-designated"):
        m.run_earnings_access_audit(AUDIT, HEAD, root=tmp_path, identity=identity, environ={})


@pytest.mark.parametrize("field,value", [("url", "https://api.massive.com/benzinga/v1/earnings?limit=100"),
    ("method", "POST"), ("timeout_seconds", True), ("timeout_seconds", 60),
    ("headers", (("Authorization", "Bearer secret"),)),
    ("headers", (("Accept", "application/json"), ("Accept-Encoding", "identity"), ("Authorization", "Bearer secret\nheader")))])
def test_fixed_transport_request_rejects_mutation(field, value):
    item = m.EarningsAccessRequest(m.REQUEST_URL, (("Accept", "application/json"), ("Accept-Encoding", "identity"),
                                                 ("Authorization", "Bearer " + KEY)))
    with pytest.raises(m.EarningsAccessAuditError):
        m._validate_request(replace(item, **{field: value}))


def test_default_transport_uses_empty_proxy_deny_redirect_tls_and_exact_fixed_request(monkeypatch):
    seen = {}
    class Stream:
        headers = {"Content-Length": str(len(encoded(body())))}
        def __init__(self): self.pending = encoded(body())
        def getcode(self): return 200
        def geturl(self): return m.REQUEST_URL
        def read(self, size):
            value, self.pending = self.pending[:size], self.pending[size:]
            return value
        def close(self): seen["closed"] = True
    class Opener:
        def open(self, req, timeout):
            seen["request"] = req
            assert timeout == 15
            return Stream()
    def opener(*handlers):
        seen["handlers"] = handlers
        return Opener()
    monkeypatch.setattr(m.request, "build_opener", opener)
    item = m.EarningsAccessRequest(m.REQUEST_URL, (("Accept", "application/json"), ("Accept-Encoding", "identity"),
                                                 ("Authorization", "Bearer " + KEY)))
    response = m._default_transport(item)
    assert response.status == 200 and response.body == encoded(body())
    assert seen["handlers"][0].proxies == {}
    assert type(seen["handlers"][1]) is m._DenyRedirect
    assert seen["request"].full_url == m.REQUEST_URL and seen["request"].data is None
    assert seen["closed"] is True


@pytest.mark.parametrize("mutation", ("digest", "bytes", "mutable", "empty", "oversized"))
def test_independent_replay_requires_exact_finite_immutable_external_body_root(mutation):
    raw = encoded(body())
    digest = hashlib.sha256(raw).hexdigest()
    if mutation == "digest": digest = "e" * 64
    if mutation == "bytes": raw += b" "
    if mutation == "mutable": raw = bytearray(raw)
    if mutation == "empty": raw = b""
    if mutation == "oversized": raw = b"x" * (m.MAX_BODY_BYTES + 1)
    with pytest.raises(m.EarningsAccessAuditError, match="body-root-refused"):
        m.replay_supplied_earnings_schema(raw, digest)
