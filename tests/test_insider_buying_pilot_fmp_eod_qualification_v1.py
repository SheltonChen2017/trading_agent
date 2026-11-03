"""Invented capture namespaces and transports only; real access stays denied."""
from copy import deepcopy
from email.message import Message
import hashlib
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
from urllib.parse import quote

import pytest

pytest.importorskip("fcntl", reason="supported macOS/POSIX private capture custody")
from research import insider_buying_pilot_fmp_eod_qualification_v1 as m


SECRET = "INVENTED-KEY+_UNIQUE-DO-NOT-RETAIN"


def _case(case_id="recent01", day="2023-02-06", cik="0000001234", ordinal=1):
    return {"case_id": case_id, "cik": cik, "accession": f"000000123423{ordinal:06d}",
        "form_type": "4", "filing_date": day, "acceptance_digits": day.replace("-", "") + "160102",
        "source_symbol": "PRIVATE-CONTROL-SYMBOL", "body_sha256": "a" * 64}


def _cases():
    return [_case("warm01", "2020-10-02", "0000009876", 3), _case(), _case("recent02", ordinal=2)]


def _context(tmp_path):
    root = tmp_path / "invented-lane"; root.mkdir(mode=0o700)
    return m._Context(root, {"head": "1" * 40}, fixture=True, checker=lambda: None)


def _credential(provider):
    return m.KeychainCredential(provider, SECRET, fixture_only=True)


def _body(item, cases):
    if item["family"] == "eod_mapping":
        return m._raw({"data": [], "meta": {"total": 0, "limit": 100, "offset": 0}, "links": {"next": None}})
    return b"[]"


def _project(raw, cases, item, credential):
    m._screen(raw, credential)
    return m._project(raw, cases, item)


def _drive(context, monkeypatch, *, cases=None, response=None, project=_project, reader=None, clock_step=None):
    selected = _cases() if cases is None else cases
    observed, reads, finishes, sleeps = [], [], [], []
    clock = [0]
    def ticks():
        value = clock[0]; clock[0] += 2 * m.SPACING_NS if clock_step is None else clock_step
        return value
    monkeypatch.setattr(m.time, "monotonic_ns", ticks)
    monkeypatch.setattr(m.time, "sleep", lambda seconds: sleeps.append(seconds))
    def credentials(provider):
        reads.append(provider)
        assert context.read(provider + "-credential-started.json")["maximum_reads"] == 1
        return _credential(provider) if reader is None else reader(provider)
    def transport(item, credential):
        assert credential.fixture_only is True and context.active is not None
        start = context.read(context.active)
        plan = context.read("request-plan.json")
        assert start["fingerprint"] == item["fingerprint"]
        assert start["maximum_attempts"] == 1
        assert start["reservation_sha256"] == context.pins["request-plan.json"]["sha256"]
        assert plan["requests"][start["request_index"]] == item
        observed.append(deepcopy(item))
        return m._Reply(200, _body(item, selected)) if response is None else response(item, credential, len(observed))
    result = m._drive(context, selected, {"head": "1" * 40}, fixture=True,
        credential_reader=credentials, transport=transport, project=project)
    return result, observed, reads, sleeps


def test_request_plan_deduplicates_fixed_queries_and_prioritizes_recent_within_provider():
    values = m.build_requests(_cases())
    assert len(values) == 6 and len({v["fingerprint"] for v in values}) == 6
    assert [v["family"] for v in values] == ["fmp_sec", "fmp_insider", "fmp_sec", "fmp_insider", "eod_mapping", "eod_mapping"]
    assert values[0]["case_ids"] == values[1]["case_ids"] == ["recent01", "recent02"]
    assert values[2]["case_ids"] == values[3]["case_ids"] == ["warm01"]
    for item in values:
        assert m._validate_item(item) == item
        query = dict(item["query"])
        assert item["method"] == "GET"
        if item["provider"] == "fmp": assert query["page"] == "0" and query["limit"] == "100"
        else: assert query["page[offset]"] == "0" and query["page[limit]"] == "100" and query["fmt"] == "json"


@pytest.mark.parametrize("fault", ("host", "endpoint", "query_limit", "query_page", "fingerprint", "duplicate_query", "case_ids"))
def test_request_mutations_refuse_even_with_recomputed_fingerprint(fault):
    item = deepcopy(m.build_requests([_case()])[0])
    if fault == "host": item["endpoint"] = "https://evil.invalid/stable/sec-filings-search/cik"
    if fault == "endpoint": item["endpoint"] += "/other"
    if fault == "query_limit": item["query"][-1][1] = "1000"
    if fault == "query_page": item["query"][-2][1] = "1"
    if fault == "duplicate_query": item["query"].append(item["query"][-1])
    if fault == "case_ids": item["case_ids"] = ["../foreign"]
    item["fingerprint"] = "0" * 64 if fault == "fingerprint" else m._sha(m._raw({k:v for k,v in item.items() if k not in {"case_ids", "fingerprint"}}))
    with pytest.raises(m.ProviderQualificationError, match="request_refused"): m._validate_item(item)


def test_context_exclusive_publication_and_namespace_never_reclaimed(tmp_path):
    context = _context(tmp_path)
    root = context.root
    try:
        context.publish("sample.json", {"fixture": True})
        assert context.read("sample.json") == {"fixture": True}
        with pytest.raises(FileExistsError): context.publish("sample.json", {"overwrite": True})
        assert context.read("sample.json") == {"fixture": True}
        for folder in (context.parent, context.directory): assert stat.S_IMODE(os.fstat(folder.fd).st_mode) == 0o700
        assert stat.S_IMODE(os.stat("sample.json", dir_fd=context.directory.fd).st_mode) == 0o600
    finally: context.close()
    with pytest.raises(m.ProviderQualificationError, match="namespace_consumed"):
        m._Context(root, {"head": "1" * 40}, fixture=True, checker=lambda: None)


@pytest.mark.parametrize("fault", ("extra", "mode", "symlink", "removed"))
def test_context_exact_inventory_modes_and_named_attachments_are_binding(tmp_path, fault):
    context = _context(tmp_path)
    try:
        context.publish("sample.json", {"value": "before"})
        parent = context.root.joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)
        path = parent / "sample.json"
        if fault == "extra": (parent / "foreign.json").write_bytes(b"{}"); (parent / "foreign.json").chmod(0o600)
        if fault == "mode": path.chmod(0o644)
        if fault == "removed": path.unlink()
        if fault == "symlink":
            target = context.root / "other.json"; target.write_bytes(path.read_bytes()); target.chmod(0o600)
            path.unlink(); path.symlink_to(target)
        with pytest.raises((m.ProviderQualificationError, OSError, ValueError)): context.check()
    finally: context.close()


def test_context_same_size_mtime_drift_and_independent_content_hash_refuse(tmp_path):
    context = _context(tmp_path)
    try:
        context.publish("sample.json", {"value": "before"})
        path = context.root.joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID, "sample.json")
        before = path.stat(); raw = path.read_bytes(); altered = raw.replace(b"before", b"forged")
        assert len(altered) == len(raw) and altered != raw
        path.write_bytes(altered); os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert path.stat().st_size == before.st_size and path.stat().st_mtime_ns == before.st_mtime_ns
        with pytest.raises(m.ProviderQualificationError, match="output_changed"): context.check()
        # Isolate the SHA check from changed ctime: a coherent current-version
        # test pin still cannot authenticate the old expected content digest.
        pin = {**context.pins["sample.json"], "version": m.custody._version(path.stat())}
        with pytest.raises(m.ProviderQualificationError, match="output_changed"):
            m._Context._verify(context.directory.fd, "sample.json", pin)
    finally: context.close()


class Stream:
    def __init__(self, chunks=(), headers=()):
        self.chunks, self.calls, self.closed = list(chunks), [], False
        self.headers = Message()
        for key, value in headers: self.headers[key] = value
    def read(self, count): self.calls.append(count); return self.chunks.pop(0) if self.chunks else b""
    def close(self): self.closed = True


@pytest.mark.parametrize("status", (301, 302, 401, 402, 403, 429, 500))
def test_refused_status_never_reads_or_hashes_error_body(status):
    stream = Stream([b"SECRET ERROR BODY"])
    reply = m._read_response(stream, status)
    assert reply.status == status and reply.body == b"" and stream.calls == []
    assert reply.code == ("redirect_refused" if status < 400 else "http_refused")


@pytest.mark.parametrize("headers,code", [((("Content-Encoding", "gzip"),), "framing_refused"),
    ((("Content-Length", "2"), ("Content-Length", "2")), "framing_refused"),
    ((("Transfer-Encoding", "chunked"), ("Content-Length", "2")), "framing_refused"),
    ((("Content-Length", "-1"),), "framing_refused"),
    ((("Content-Length", str(m.MAX_BODY + 1)),), "oversized_response")])
def test_framing_refusals_happen_before_body_read(headers, code):
    stream = Stream([b"PRIVATE"], headers)
    with pytest.raises(m.ProviderQualificationError, match=code): m._read_response(stream, 200)
    assert stream.calls == []


def test_identity_encoded_response_exact_length_and_unknown_length_are_bounded():
    for headers in ((), (("Content-Encoding", "identity"), ("Content-Length", "2")), (("Transfer-Encoding", "chunked"),)):
        stream = Stream([b"[]", b""], headers)
        reply = m._read_response(stream, 200)
        assert reply.status == 200 and reply.body == b"[]" and reply.code is None
        assert max(stream.calls) <= m.MAX_BODY + 1
    with pytest.raises(m.ProviderQualificationError, match="partial_response"):
        m._read_response(Stream([b"[", b""], (("Content-Length", "2"),)), 200)
    with pytest.raises(m.ProviderQualificationError, match="oversized_response"):
        m._read_response(Stream([b"x" * (m.MAX_BODY + 1)]), 200)
    with pytest.raises(m.ProviderQualificationError, match="partial_response"):
        m._read_response(Stream(["not bytes"]), 200)


@pytest.mark.parametrize("encoding", ("literal", "percent", "nested_percent", "unicode_value", "unicode_key"))
def test_credential_echo_screen_covers_keys_values_and_nested_encodings(encoding):
    secret = "INVENTED_KEY_123456789"
    escaped = "".join("\\u%04x" % ord(c) for c in secret)
    percent = "".join("%%%02X" % ord(c) for c in secret)
    raw = json.dumps({"x": secret}).encode()
    if encoding == "percent": raw = json.dumps({"x": percent}).encode()
    if encoding == "nested_percent": raw = json.dumps({"x": quote(percent, safe="")}).encode()
    if encoding == "unicode_value": raw = ('{"x":"' + escaped + '"}').encode()
    if encoding == "unicode_key": raw = ('{"' + escaped + '":"x"}').encode()
    with pytest.raises(m.ProviderQualificationError, match="credential_or_metadata_refused"):
        m._screen(raw, m.KeychainCredential("fmp", secret, fixture_only=True))
    m._screen(b'[{"symbol":"INVENTED"}]', m.KeychainCredential("fmp", secret, fixture_only=True))


def test_transport_refuses_fixture_and_unjournaled_context_before_any_opener(tmp_path, monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *a, **k: pytest.fail("opener before custody authority"))
    context = _context(tmp_path)
    try:
        item = m.build_requests([_case()])[0]
        with pytest.raises(m.ProviderQualificationError, match="started_journal_required"):
            m._transport(context, item, _credential("fmp"))
        fake = object.__new__(m._Context)
        fake.fixture, fake.token, fake.root, fake.active = False, m._ACTUAL, m.LANE_ROOT, None
        with pytest.raises(m.ProviderQualificationError, match="started_journal_required"):
            m._transport(fake, item, m.KeychainCredential("fmp", SECRET))
    finally: context.close()


def _invented_transport_context():
    cases = [_case()]; item = m.build_requests(cases)[0]
    plan = {"schema": m.SCHEMA+"/plan", "requests": m.build_requests(cases),
        "control_sha256": m._sha(m._raw(cases)), "fixture_only": False, "registration": m.registration()}
    pin = m._sha(m._raw(plan))
    start = {"request_index": 0, "fingerprint": item["fingerprint"], "maximum_attempts": 1, "reservation_sha256": pin}
    # A manually assembled internal seam has no filesystem namespace or real
    # credentials. All opener/deadline operations below are invented doubles.
    context = object.__new__(m._Context)
    context.fixture, context.token, context.root = False, m._ACTUAL, m.LANE_ROOT
    context.active, context.dispatched = "request-000-started.json", set()
    context.pins = {"request-plan.json": {"sha256": pin}}
    docs = {"request-plan.json": plan, context.active: start, "controls.json": {"cases": cases}}
    context.check = lambda: None
    context.read = lambda name: docs[name]
    return context, item, docs


@pytest.mark.parametrize("fault", ("plan", "controls", "reservation", "attempts", "already_dispatched"))
def test_transport_requires_exact_control_plan_and_one_shot_before_opener(monkeypatch, fault):
    context, item, docs = _invented_transport_context()
    if fault == "plan": docs["request-plan.json"]["control_sha256"] = "b" * 64
    if fault == "controls": docs["controls.json"]["cases"][0]["body_sha256"] = "b" * 64
    if fault == "reservation": docs[context.active]["reservation_sha256"] = "b" * 64
    if fault == "attempts": docs[context.active]["maximum_attempts"] = 2
    if fault == "already_dispatched": context.dispatched.add(item["fingerprint"])
    monkeypatch.setattr(m.request, "build_opener", lambda *a, **k: pytest.fail("opener before exact control/journal binding"))
    with pytest.raises(m.ProviderQualificationError, match="started_journal_required"):
        m._transport(context, item, m.KeychainCredential("fmp", SECRET))


def test_transport_closes_stream_inside_deadline_and_marks_dispatch_once(monkeypatch):
    context, item, _ = _invented_transport_context(); state = {"active": False, "opens": 0}
    credential = m.KeychainCredential("fmp", SECRET)
    url = m._live_url(item, credential)
    class Alarm:
        def __enter__(self): state["active"] = True; return self
        def arm_cleanup(self): assert state["active"] is True
        def __exit__(self, *_): state["active"] = False
    class Response(Stream):
        def getcode(self): return 200
        def geturl(self): return url
        def close(self):
            assert state["active"] is True
            super().close()
    stream = Response([b"[]", b""], (("Content-Length", "2"),))
    class Opener:
        def open(self, req, *, timeout):
            assert state["active"] is True and req.full_url == url and timeout == m.HTTP_SECONDS
            state["opens"] += 1
            return stream
    monkeypatch.setattr(m, "_Deadline", Alarm)
    monkeypatch.setattr(m.request, "build_opener", lambda *a, **k: Opener())
    monkeypatch.setattr(m.ssl, "create_default_context", lambda: None)
    reply = m._transport(context, item, credential)
    assert reply.status == 200 and reply.body == b"[]" and reply.code is None
    assert stream.closed and state == {"active": False, "opens": 1}
    with pytest.raises(m.ProviderQualificationError, match="started_journal_required"):
        m._transport(context, item, credential)
    assert state["opens"] == 1


def test_expired_one_shot_alarm_cannot_leave_response_cleanup_unbounded(monkeypatch):
    context, item, _ = _invented_transport_context()
    credential = m.KeychainCredential("fmp", SECRET)
    url = m._live_url(item, credential)
    state = {"handler": object(), "armed": False, "close_saw_armed": False}
    monkeypatch.setattr(m.signal, "getitimer", lambda _: (0.0, 0.0))
    monkeypatch.setattr(m.signal, "getsignal", lambda _: state["handler"])
    monkeypatch.setattr(m.signal, "signal", lambda _, value: state.update(handler=value))
    monkeypatch.setattr(m.signal, "setitimer", lambda _, seconds: state.update(armed=seconds > 0))
    class Response(Stream):
        def getcode(self): return 200
        def geturl(self): return url
        def read(self, count):
            state["armed"] = False  # The one-shot kernel timer is consumed.
            state["handler"](m.signal.SIGALRM, None)
        def close(self):
            state["close_saw_armed"] = state["armed"]
            assert state["armed"], "cleanup entered after the sole alarm was consumed"
            self.closed = True
    stream = Response()
    monkeypatch.setattr(m.request, "build_opener", lambda *a, **k: SimpleNamespace(open=lambda *a, **k: stream))
    monkeypatch.setattr(m.ssl, "create_default_context", lambda: None)
    reply = m._transport(context, item, credential)
    assert state["close_saw_armed"] is True and stream.closed is True
    assert reply.status is None and reply.body == b"" and reply.code == "transport_timeout"


def test_cleanup_alarm_installation_failure_skips_unbounded_close_and_refuses(monkeypatch):
    context, item, _ = _invented_transport_context()
    credential = m.KeychainCredential("fmp", SECRET)
    url = m._live_url(item, credential); old = object(); state = {"handler": old}
    monkeypatch.setattr(m.signal, "getitimer", lambda _: (0.0, 0.0))
    monkeypatch.setattr(m.signal, "getsignal", lambda _: state["handler"])
    monkeypatch.setattr(m.signal, "signal", lambda _, value: state.update(handler=value))
    def timer(_, seconds):
        if seconds == m.CLOSE_SECONDS: raise OSError("invented cleanup timer failure")
    monkeypatch.setattr(m.signal, "setitimer", timer)
    class Response(Stream):
        def getcode(self): return 200
        def geturl(self): return url
        def close(self): pytest.fail("close entered without a cleanup alarm")
    stream = Response([b"[]", b""], (("Content-Length", "2"),))
    monkeypatch.setattr(m.request, "build_opener", lambda *a, **k: SimpleNamespace(open=lambda *a, **k: stream))
    monkeypatch.setattr(m.ssl, "create_default_context", lambda: None)
    reply = m._transport(context, item, credential)
    assert reply.status is None and reply.body == b"" and reply.code == "deadline_unavailable"
    assert stream.closed is False and state["handler"] is old


def test_deadline_restores_previous_handler_after_normal_and_exceptional_exit(monkeypatch):
    old = object(); state = {"handler": old}; timers = []
    monkeypatch.setattr(m.signal, "getitimer", lambda _: (0.0, 0.0))
    monkeypatch.setattr(m.signal, "getsignal", lambda _: state["handler"])
    monkeypatch.setattr(m.signal, "signal", lambda _, value: state.update(handler=value))
    monkeypatch.setattr(m.signal, "setitimer", lambda _, seconds: timers.append(seconds))
    with pytest.raises(RuntimeError):
        with m._Deadline(): raise RuntimeError("invented")
    assert state["handler"] is old and timers == [m.HTTP_SECONDS, 0]


@pytest.mark.parametrize("fault", ("enter", "cancel"))
def test_deadline_setup_and_cancel_failures_still_restore_handler(monkeypatch, fault):
    old = object(); state = {"handler": old}
    monkeypatch.setattr(m.signal, "getitimer", lambda _: (0.0, 0.0))
    monkeypatch.setattr(m.signal, "getsignal", lambda _: state["handler"])
    monkeypatch.setattr(m.signal, "signal", lambda _, value: state.update(handler=value))
    def timer(_, seconds):
        if fault == "enter" and seconds or fault == "cancel" and seconds == 0: raise OSError("invented timer failure")
    monkeypatch.setattr(m.signal, "setitimer", timer)
    with pytest.raises((m.ProviderQualificationError, OSError)):
        with m._Deadline(): pass
    assert state["handler"] is old


def test_deadline_never_overwrites_an_existing_alarm(monkeypatch):
    monkeypatch.setattr(m.signal, "getitimer", lambda _: (1.0, 0.0))
    monkeypatch.setattr(m.signal, "signal", lambda *a: pytest.fail("existing alarm overwritten"))
    with pytest.raises(m.ProviderQualificationError, match="deadline_unavailable"):
        with m._Deadline(): pass


def test_drive_journals_before_transport_reads_credentials_once_and_retains_only_projection(tmp_path, monkeypatch):
    context = _context(tmp_path)
    try:
        result, attempted, reads, sleeps = _drive(context, monkeypatch)
        assert len(attempted) == result["planned_requests"] == result["transport_invocation_count"] == 6
        assert reads == ["fmp", "eodhd"] and result["credential_read_attempts"] == result["credential_reads_observed"] == 2
        assert result["unattempted_requests"] == 0 and result["clean_scoped_responses"] == 6
        assert context.active is None and not sleeps
        assert len({v["fingerprint"] for v in attempted}) == len(attempted)
        wire = m._raw(result)
        for private in (SECRET, "PRIVATE-CONTROL-SYMBOL", "0000001234", "0000009876", "a" * 64): assert private.encode() not in wire
        assert m._raw(m.public_summary(result)).find(b"case_checks") == -1
        assert result["raw_response_retained"] is False and result["remote_request_count_measured"] is False
        assert all(v is False or type(v) is int and v == 0 for v in result["authority"].values())
    finally: context.close()


def test_finish_to_next_start_spacing_is_enforced_without_actual_sleep(tmp_path, monkeypatch):
    context = _context(tmp_path)
    try:
        result, attempted, _, sleeps = _drive(context, monkeypatch, clock_step=0)
        assert len(sleeps) == len(attempted) - 1 == 5
        assert sleeps == [m.SPACING_NS / 1_000_000_000] * 5
    finally: context.close()


def test_processed_unscoped_response_is_not_counted_as_clean_success(tmp_path, monkeypatch):
    context = _context(tmp_path)
    def response(item, credential, ordinal):
        if ordinal == 1:
            return m._Reply(200, m._raw([{"cik": "1234", "filingDate": "2020-09-30"}]))
        return m._Reply(200, _body(item, _cases()))
    try:
        result, attempted, _, _ = _drive(context, monkeypatch, response=response)
        assert result["projected_responses"] == 5
        assert result["scoped_responses"] == result["clean_scoped_responses"] == 4
        assert result["receipts"][0]["code"] == "provider_scope_refused"
        assert result["receipts"][0]["projection"]["body_pin"] is None
        assert len(attempted) == 5 and result["unattempted_requests"] == 1
    finally: context.close()


@pytest.mark.parametrize("status,expected_fmp", ((401, 1), (429, 1), (500, 1), (402, 3), (403, 3), (404, 3)))
def test_refusal_stops_provider_or_family_without_query_retry(tmp_path, monkeypatch, status, expected_fmp):
    context = _context(tmp_path)
    def response(item, credential, ordinal):
        return m._Reply(status, b"", "http_refused") if ordinal == 1 else m._Reply(200, _body(item, _cases()))
    try:
        result, attempted, reads, _ = _drive(context, monkeypatch, response=response)
        assert sum(v["provider"] == "fmp" for v in attempted) == expected_fmp
        assert sum(v["provider"] == "eodhd" for v in attempted) == 2
        assert len({v["fingerprint"] for v in attempted}) == len(attempted)
        assert result["unattempted_requests"] == 6 - len(attempted)
        assert reads == ["fmp", "eodhd"]
    finally: context.close()


def test_transport_error_stops_provider_and_credential_failure_is_not_retried(tmp_path, monkeypatch):
    context = _context(tmp_path)
    def response(item, credential, ordinal):
        return m._Reply(None, b"", "transport_timeout") if ordinal == 1 else m._Reply(200, _body(item, _cases()))
    try:
        result, attempted, reads, _ = _drive(context, monkeypatch, response=response)
        assert len(attempted) == 3 and result["unattempted_requests"] == 3
        assert reads == ["fmp", "eodhd"]
    finally: context.close()
    second = tmp_path / "second"; second.mkdir(mode=0o700)
    context = _context(second)
    def reader(provider):
        if provider == "fmp": raise OSError("PRIVATE credential failure")
        return _credential(provider)
    try:
        result, attempted, reads, _ = _drive(context, monkeypatch, reader=reader)
        assert reads == ["fmp", "eodhd"] and len(attempted) == 2
        assert result["credential_read_attempts"] == 2 and result["credential_reads_observed"] == 1
        assert result["unattempted_requests"] == 4
        assert b"PRIVATE credential" not in m._raw(result)
    finally: context.close()


def test_bad_projection_cannot_store_rows_credentials_or_claim_readiness(tmp_path, monkeypatch):
    context = _context(tmp_path)
    def project(raw, cases, item, credential):
        value = _project(raw, cases, item, credential)
        value["upstream_rows"] = [{"SECRET": credential.value}]
        value["authority"]["backtesting_ready"] = True
        return value
    try:
        result, attempted, _, _ = _drive(context, monkeypatch, project=project)
        assert result["projected_responses"] == result["clean_scoped_responses"] == 0
        assert len(attempted) == 3 and result["unattempted_requests"] == 3
        assert SECRET.encode() not in m._raw(result) and b"upstream_rows" not in m._raw(result)
        assert all(r.get("projection") is None for r in result["receipts"])
        assert result["authority"]["backtesting_ready"] is False
    finally: context.close()


def test_unscoped_projection_is_not_success_and_cli_returns_refusal(monkeypatch, capsys):
    monkeypatch.setattr(m, "run_actual", lambda _, **kwargs: {"clean_scoped_responses": 0, "planned_requests": 1})
    assert m.main(["--expected-head", "1" * 40]) == 2
    assert "clean_scoped_responses" in capsys.readouterr().out


def test_worker_payload_is_anonymous_stdin_not_command_or_environment(monkeypatch):
    captured = {}
    def launch(command, payload, *, timeout):
        captured.update(command=command, payload=payload, timeout=timeout)
        return {"passed": False, "code": "projection_refused", "projection": None}
    monkeypatch.setattr(m.ipc, "_launch", launch)
    value = m._child("project", {"head": "1" * 40}, {"credential": {"value": SECRET}})
    assert value["passed"] is False and SECRET.encode() in captured["payload"]
    assert SECRET not in repr(captured["command"])
    assert captured["timeout"] == m.PROJECT_SECONDS
    assert "-I" in captured["command"] and "-S" in captured["command"] and "-B" in captured["command"]
    policy = captured["command"][captured["command"].index("-p") + 1]
    assert "(deny network*)" in policy and "(deny process-fork)" in policy and "/usr/bin/security" in policy


def test_registration_and_authority_remain_bounded_without_new_access():
    value = m.registration()
    assert value["maximum_unique_requests"] == 36 and value["rows_per_request"] == 100
    assert value["maximum_response_bytes"] == 128 * 1024
    assert value["maximum_attempts_per_request"] == 1 and value["credential_reads_per_provider"] == 1
    assert value["http_open_read_wall_seconds"] == 15 and value["http_close_wall_seconds"] == 1
    assert value["http_total_wall_seconds"] == 16
    assert value["redirect_retry_paging_fallback_or_resume_permitted"] is False
    assert value["raw_or_normalized_provider_rows_retained"] is False
    assert m.authority()["backtesting_ready"] is False


@pytest.mark.parametrize("fault", ("clean", "head", "branch", "dirt"))
def test_parent_current_requires_live_exact_head_branch_and_clean_status_without_git_mutation(monkeypatch, fault):
    identity = {"head": "1" * 40}; checks = []
    monkeypatch.setattr(m, "_current", lambda supplied: checks.append(supplied))
    head = "2" * 40 if fault == "head" else identity["head"]
    branch = "codex/foreign-lane" if fault == "branch" else m.LANE_BRANCH
    raw = ("# branch.oid " + head + "\n# branch.head " + branch + "\n# branch.ab +0 -0\n").encode()
    if fault == "dirt": raw += b"? invented-untracked.txt\n"
    def git(root, *args):
        assert root == m.LANE_ROOT
        assert args == ("status", "--porcelain=v2", "--branch", "--untracked-files=all")
        return raw
    monkeypatch.setattr(m.custody, "_git", git)
    if fault == "clean": m._parent_current(identity)
    else:
        with pytest.raises(m.ProviderQualificationError, match="identity_refused"): m._parent_current(identity)
    assert checks == [identity]


def _seed_preinput_predecessor(tmp_path):
    context = _context(tmp_path)
    root = context.root
    pin = {k: context.latch[k] for k in ("bytes", "sha256")}; pin["head"] = "1" * 40
    parent = root.joinpath(*m.OUTPUT_PARTS)
    raw = (parent / "scope-reservation.json").read_bytes()
    assert list((parent / m.AUDIT_ID).iterdir()) == []
    context.close()
    return root, parent, pin, raw


def _continuation(root, pin):
    return m._Context(root, {"head": "2" * 40}, fixture=True, checker=lambda: None,
        continuation=True, predecessor_pin=pin)


def test_one_preinput_continuation_preserves_failed_scope_and_never_claims_fixed_cause(tmp_path):
    root, parent, pin, old_raw = _seed_preinput_predecessor(tmp_path)
    context = _continuation(root, pin)
    try:
        assert context.latch_name == "scope-continuation-2.json"
        assert context.audit_name == m.AUDIT_ID + "-preinput-continuation-2"
        assert set(p.name for p in parent.iterdir()) == {"scope-reservation.json", m.AUDIT_ID,
            context.latch_name, context.audit_name}
        assert (parent / "scope-reservation.json").read_bytes() == old_raw
        assert list((parent / m.AUDIT_ID).iterdir()) == []
        new = json.loads((parent / context.latch_name).read_bytes())
        assert new["preinput_predecessor"] == pin
        assert new["execution_identity"]["head"] == "2" * 40
        assert new["original_failure_cause_established"] is False
        context.publish("invented-stage.json", {"fixture_only": True})
        assert context.read("invented-stage.json") == {"fixture_only": True}
        with pytest.raises(FileExistsError): context.publish("invented-stage.json", {"overwrite": True})
        assert (parent / "scope-reservation.json").read_bytes() == old_raw
    finally: context.close()
    snapshot = {p.name: p.read_bytes() for p in parent.iterdir() if p.is_file()}
    with pytest.raises(m.ProviderQualificationError, match="namespace_consumed"):
        _continuation(root, pin)
    with pytest.raises(m.ProviderQualificationError, match="namespace_consumed"):
        m._Context(root, {"head": "2" * 40}, fixture=True, checker=lambda: None)
    assert {p.name: p.read_bytes() for p in parent.iterdir() if p.is_file()} == snapshot
    assert list((parent / m.AUDIT_ID).iterdir()) == []


@pytest.mark.parametrize("leaf", ("controls-metadata-started.json", "controls.json", "fmp-credential-started.json",
    "request-000-started.json", "foreign.json"))
def test_continuation_refuses_any_old_input_credential_or_request_evidence_before_write(tmp_path, leaf):
    root, parent, pin, old_raw = _seed_preinput_predecessor(tmp_path)
    path = parent / m.AUDIT_ID / leaf; path.write_bytes(b"{}"); path.chmod(0o600)
    with pytest.raises(m.ProviderQualificationError, match="namespace_consumed"):
        _continuation(root, pin)
    assert set(p.name for p in parent.iterdir()) == {"scope-reservation.json", m.AUDIT_ID}
    assert (parent / "scope-reservation.json").read_bytes() == old_raw


@pytest.mark.parametrize("fault", ("bytes", "sha256", "head", "root_extra", "old_mode", "old_noncanonical"))
def test_continuation_external_predecessor_pin_and_exact_prior_inventory_are_binding(tmp_path, fault):
    root, parent, pin, old_raw = _seed_preinput_predecessor(tmp_path)
    if fault == "bytes": pin["bytes"] += 1
    if fault == "sha256": pin["sha256"] = "0" * 64
    if fault == "head": pin["head"] = "3" * 40
    if fault == "root_extra": (parent / "unexpected.json").write_bytes(b"{}")
    if fault == "old_mode": (parent / "scope-reservation.json").chmod(0o644)
    if fault == "old_noncanonical":
        altered = json.dumps(json.loads(old_raw), indent=2).encode()
        (parent / "scope-reservation.json").write_bytes(altered)
        pin.update(bytes=len(altered), sha256=m._sha(altered))
    before = set(p.name for p in parent.iterdir())
    with pytest.raises((m.ProviderQualificationError, ValueError)):
        _continuation(root, pin)
    assert set(p.name for p in parent.iterdir()) == before
    assert not (parent / "scope-continuation-2.json").exists()
    assert not (parent / (m.AUDIT_ID + m.CONTINUATION_SUFFIX)).exists()


@pytest.mark.parametrize("fault", ("old_body", "old_audit_leaf", "old_audit_mode", "root_extra"))
def test_continuation_rechecks_preserved_old_scope_at_every_check(tmp_path, fault):
    root, parent, pin, _ = _seed_preinput_predecessor(tmp_path)
    context = _continuation(root, pin)
    try:
        if fault == "old_body":
            path = parent / "scope-reservation.json"; previous = path.stat()
            raw = path.read_bytes(); altered = raw.replace(b"1" * 40, b"3" * 40, 1)
            assert altered != raw and len(altered) == len(raw)
            path.write_bytes(altered); os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        if fault == "old_audit_leaf": (parent / m.AUDIT_ID / "request-000-started.json").write_bytes(b"{}")
        if fault == "old_audit_mode": (parent / m.AUDIT_ID).chmod(0o750)
        if fault == "root_extra": (parent / "third-scope.json").write_bytes(b"{}")
        with pytest.raises((m.ProviderQualificationError, ValueError)): context.check()
    finally: context.close()


def test_fixture_requires_explicit_predecessor_pin_and_actual_pin_override_is_forbidden(tmp_path, monkeypatch):
    root, _, _, _ = _seed_preinput_predecessor(tmp_path)
    with pytest.raises(m.ProviderQualificationError, match="arguments_refused"):
        m._Context(root, {"head": "2" * 40}, fixture=True, checker=lambda: None, continuation=True)
    monkeypatch.setattr(m.custody, "_Chain", lambda *a, **k: pytest.fail("actual namespace opened from pin override"))
    with pytest.raises(m.ProviderQualificationError, match="arguments_refused"):
        m._Context(m.LANE_ROOT, {"head": "2" * 40}, continuation=True, predecessor_pin=dict(m.PREINPUT_PIN))


@pytest.mark.parametrize("continuation", (2, 3, None))
def test_no_numeric_third_or_implicit_continuation_namespace(tmp_path, monkeypatch, continuation):
    monkeypatch.setattr(m.custody, "_Chain", lambda *a, **k: pytest.fail("unbounded continuation opened a namespace"))
    with pytest.raises(m.ProviderQualificationError, match="arguments_refused"):
        m._Context(tmp_path, {"head": "2" * 40}, fixture=True, checker=lambda: None, continuation=continuation,
            predecessor_pin={"bytes": 1, "sha256": "a" * 64, "head": "1" * 40})


@pytest.mark.parametrize("continuation", (False, True))
def test_run_entry_preserves_finite_cause_and_continuation_selection_without_actual_access(monkeypatch, continuation):
    events = []; identity = {"head": "2" * 40}
    monkeypatch.setattr(m, "_identity", lambda head: identity)
    class Context:
        def __init__(self, root, supplied, **kwargs):
            assert root == m.LANE_ROOT and supplied is identity and kwargs == {"continuation": continuation}
        def publish(self, name, value):
            if name == "controls-metadata-started.json": raise m.ProviderQualificationError("output_changed")
            assert name == "failure.json"
            events.append(value)
        def close(self): events.append("closed")
    monkeypatch.setattr(m, "_Context", Context)
    with pytest.raises(m.ProviderQualificationError, match="^output_changed$"):
        m.run_actual(identity["head"], continuation=continuation)
    assert events[0]["stage"] == "controls_metadata" and events[0]["code"] == "output_changed"
    assert events[-1] == "closed"
    assert events[0]["authority"]["backtesting_ready"] is False


def test_continuation_cli_routes_only_explicit_flag_and_health_is_mutually_exclusive(monkeypatch, capsys):
    calls = []
    def run(head, *, continuation=False):
        calls.append((head, continuation))
        return {"clean_scoped_responses": 0, "planned_requests": 1}
    monkeypatch.setattr(m, "run_actual", run)
    monkeypatch.setattr(m, "preflight_actual", lambda *a: pytest.fail("health launched with continuation"))
    assert m.main(["--expected-head", "2" * 40]) == 2
    assert m.main(["--expected-head", "2" * 40, "--continue-pre-input"]) == 2
    assert calls == [("2" * 40, False), ("2" * 40, True)]
    assert m.main(["--expected-head", "2" * 40, "--continue-pre-input", "--health"]) == 2
    assert len(calls) == 2 and "arguments_refused" in capsys.readouterr().out


def test_continuation_budget_never_increases_provider_attempts():
    policy = m.registration()
    assert policy["one_explicit_preinput_continuation_only"] is True
    assert policy["continuation_requires_pinned_failed_reservation_and_empty_original_audit"] is True
    assert policy["provider_attempt_budget_shared_across_original_and_continuation"] == 1
    assert policy["maximum_attempts_per_request"] == 1 and policy["maximum_unique_requests"] == 36
