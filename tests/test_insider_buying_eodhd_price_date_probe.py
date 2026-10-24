"""Invented-only date capability tests; native network/Keychain denial required."""
from email.message import Message
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import time
from types import SimpleNamespace
from urllib.parse import quote, quote_plus

import pytest

if os.name != "posix":
    pytest.skip("IBWIN-CR01: supported lane custody is macOS/POSIX", allow_module_level=True)

from research import insider_buying_eodhd_price_date_probe as m


HEAD = "a" * 40
TOKEN = "invented_eod_date_key+/with?characters_123"
BODY = b'"2006-01-31"\n'


def credential(*, fixture=True):
    return m.KeychainCredential("eodhd", TOKEN, fixture)


def identity(root):
    source = {"invented.py": "b" * 64}
    return {"root": str(root), "branch": m.LANE_BRANCH, "head": HEAD, "clean": True,
            "source_sha256": source, "source_inventory_sha256": m._sha(m._canonical(source))}


def run(root, *, reader=None, transport=None, identify=None):
    return m.run_probe(HEAD, root=root, identity=identify or (lambda head, root: identity(root)),
        credential_reader=reader or (lambda provider: credential()),
        transport=transport or (lambda url, key: m.ProviderMetadataResponse(200, BODY, True)),
        clock=lambda: "2026-10-24T00:00:00Z")


def output(root):
    return root.joinpath(*m.OUTPUT_PARTS, m.AUDIT_ID)


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_one_fixed_date_request_bound_private_output_and_no_token(tmp_path):
    calls = []
    def reader(provider):
        assert provider == "eodhd"
        assert (output(tmp_path) / "credential-read-started.json").is_file()
        calls.append("credential"); return credential()
    def transport(url, key):
        assert url == m.REDACTED_URL and TOKEN not in url and key == credential()
        assert (output(tmp_path) / "01-date-started.json").is_file()
        calls.append("dispatch"); return m.ProviderMetadataResponse(200, BODY, True)
    result = run(tmp_path, reader=reader, transport=transport)
    assert calls == ["credential", "dispatch"]
    assert result["status"] == "completed-date-metadata-probe" and result["fixture_only"] is True
    assert result["transport_invocation_count"] == result["planned_requests"] == 1
    assert result["metadata"]["last_observed_source_date"] == "2006-01-31"
    assert all(result[name] is False for name in m.FALSE_FLAGS)
    assert result["research_looks"] == result["qc_jobs"] == result["backtests"] == 0
    assert result["price_volume_or_return_values_read"] is False
    assert result["full_study_population_coverage_verified"] is result["paid_bulk_entitlement_verified"] is False
    assert output(tmp_path).stat().st_mode & 0o777 == output(tmp_path).parent.stat().st_mode & 0o777 == 0o700
    for name, digest in result["published_leaf_sha256"].items():
        path = output(tmp_path) / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert path.stat().st_nlink == 1 and path.stat().st_mode & 0o777 == 0o600
    assert json.loads((output(tmp_path) / "complete.json").read_bytes()) == result
    all_bytes = b"".join(snapshot(tmp_path).values())
    assert TOKEN.encode() not in all_bytes and quote(TOKEN, safe="").encode() not in all_bytes


@pytest.mark.parametrize("raw", [b"2005-01-03", b"2005-01-03\n", b'"2006-01-31"', BODY])
def test_only_exact_optional_quoted_iso_date_is_accepted_without_json_decode(raw, monkeypatch):
    monkeypatch.setattr(m.json, "loads", lambda *args, **kwargs: pytest.fail("source JSON interpretation forbidden"))
    value = m._scalar_projection(raw, credential())
    assert value["last_observed_source_date"] in {"2005-01-03", "2006-01-31"}
    assert value["response_body_sha256"] == m._sha(raw)


@pytest.mark.parametrize("raw", [b"", b"null", b"[]", b"{}", b"123.5", b'[{"date":"2006-01-31","close":123.5}]',
    b"Date,Open,Close\n2006-01-31,1,2\n", b" 2006-01-31", b"2006-01-31 ", b"2006-01-31\n\n",
    b"2006-01-31\r\n", b"2006-1-31", b"2006-01-32", b"2006-01-31T00:00:00Z", b'"2006-01-31"x',
    b'"2006-01-31\\n"', b"2004-12-31", b"2006-02-01", b"x" * 4097, b"\xff"])
def test_unfiltered_financial_response_or_nonexact_date_is_not_decoded_hashed_or_retained(tmp_path, raw):
    result = run(tmp_path, transport=lambda *args: m.ProviderMetadataResponse(200, raw, True))
    assert result["status"] == "stopped-date-metadata-probe" and result["metadata"] is None
    assert not (output(tmp_path) / "01-date-response.txt").exists()
    completed = json.loads((output(tmp_path) / "01-date-completed.json").read_bytes())
    assert completed["body_sha256"] is completed["body_size_bytes"] is None
    assert completed["untrusted_error_body_hashed_or_retained"] is False


@pytest.mark.parametrize("encoding", [lambda value: value, quote, quote_plus,
    lambda value: quote(quote(value, safe=""), safe="")])
def test_raw_or_nested_encoded_credential_echo_never_retained(tmp_path, encoding):
    raw = ('"' + encoding(TOKEN) + '"').encode()
    result = run(tmp_path, transport=lambda *args: m.ProviderMetadataResponse(200, raw, True))
    assert result["disposition"] == "credential_echo_or_encoding_refused"
    assert result["metadata"] is None and raw not in snapshot(tmp_path).values()


@pytest.mark.parametrize("status", [None, 302, 401, 403, 429, 500])
def test_non200_fixture_body_is_never_interpreted_or_hashed(tmp_path, status, monkeypatch):
    monkeypatch.setattr(m, "_scalar_projection", lambda *args: pytest.fail("non200 source interpretation"))
    result = run(tmp_path, transport=lambda *args: m.ProviderMetadataResponse(status, TOKEN.encode(), False))
    assert result["http_status"] == status and result["metadata"] is None
    assert result["transport_invocation_count"] == 1
    assert TOKEN.encode() not in b"".join(snapshot(tmp_path).values())


def test_incomplete_transport_is_refused_without_partial_body_retention(tmp_path):
    result = run(tmp_path, transport=lambda *args: m.ProviderMetadataResponse(200, BODY, False))
    assert result["disposition"] == "partial-read" and result["metadata"] is None
    assert not (output(tmp_path) / "01-date-response.txt").exists()


@pytest.mark.parametrize("reader", [lambda provider: None, lambda provider: m.KeychainCredential("fmp", TOKEN, True),
    lambda provider: credential(fixture=False), lambda provider: m.KeychainCredential("eodhd", "demo", True),
    lambda provider: m.KeychainCredential("eodhd", "private\nvalue", True)])
def test_refused_credential_is_consumed_once_and_dispatch_never_occurs(tmp_path, reader):
    calls = []
    result = run(tmp_path, reader=reader, transport=lambda *args: calls.append("must-not-dispatch"))
    assert not calls and result["disposition"] == "credential_read_refused"
    assert result["transport_invocation_count"] == 0 and result["credential_read_observed"] is False
    before = snapshot(tmp_path)
    with pytest.raises(m.PriceDateProbeError, match="consumed_or_ambiguous_scope_refused"):
        run(tmp_path, reader=lambda *args: pytest.fail("repeat credential read"))
    assert snapshot(tmp_path) == before


def test_repeat_namespace_refuses_without_any_callback(tmp_path):
    run(tmp_path); before = snapshot(tmp_path)
    with pytest.raises(m.PriceDateProbeError):
        run(tmp_path, reader=lambda *args: pytest.fail("duplicate keychain scope"),
            transport=lambda *args: pytest.fail("duplicate dispatch"))
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("mutation", [lambda body: body.update(clean=False), lambda body: body.update(head="b" * 40),
    lambda body: body.update(branch="main"), lambda body: body.update(source_inventory_sha256="c" * 64),
    lambda body: body["source_sha256"].update({"../unsafe.py": "b" * 64})])
def test_bad_identity_refuses_before_scope_or_credential(tmp_path, mutation):
    value = identity(tmp_path); mutation(value)
    with pytest.raises(m.PriceDateProbeError):
        run(tmp_path, identify=lambda *args, **kwargs: value,
            reader=lambda *args: pytest.fail("bad identity read"), transport=lambda *args: pytest.fail("bad identity dispatch"))
    assert not tmp_path.joinpath(*m.OUTPUT_PARTS).exists()


def test_identity_change_after_started_journal_refuses_dispatch(tmp_path):
    current = identity(tmp_path)
    def identify(*args, **kwargs):
        if (output(tmp_path) / "01-date-started.json").exists():
            return {**current, "head": "c" * 40}
        return current
    with pytest.raises(m.PriceDateProbeError):
        run(tmp_path, identify=identify, transport=lambda *args: pytest.fail("changed identity dispatch"))
    assert (output(tmp_path) / "01-date-started.json").exists()


@pytest.mark.parametrize("root", [m.LANE_ROOT, m.LANE_ROOT.parent, m.LANE_ROOT / "invented-fixture"])
def test_fixture_root_cannot_reach_lane_or_its_ancestor(root):
    with pytest.raises(m.PriceDateProbeError, match="invented_outside_lane_callbacks_required"):
        run(root, reader=lambda *args: pytest.fail("unsafe fixture credential"),
            transport=lambda *args: pytest.fail("unsafe fixture transport"))


def test_fixture_callbacks_cannot_select_real_transports_or_reader(tmp_path, monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *args, **kwargs: pytest.fail("production opener must not run"))
    for kwargs in ({"credential_reader": m.read_keychain_credential, "transport": lambda *args: None},
                   {"credential_reader": lambda *args: None, "transport": m._default_transport}):
        with pytest.raises(m.PriceDateProbeError, match="invented_outside_lane_callbacks_required"):
            m.run_probe(HEAD, root=tmp_path, identity=lambda *args, **kwargs: identity(tmp_path), **kwargs)


@pytest.mark.parametrize("mutation", ["content", "mode", "hardlink", "extra"])
def test_output_changes_refuse_before_interpreting_response(tmp_path, mutation, monkeypatch):
    def transport(*args):
        leaf = output(tmp_path) / "reservation.json"
        if mutation == "content":leaf.write_bytes(b"{}")
        elif mutation == "mode":leaf.chmod(0o644)
        elif mutation == "hardlink":os.link(leaf, tmp_path / "extra-link")
        else:(output(tmp_path) / "foreign").write_bytes(b"private")
        return m.ProviderMetadataResponse(200, BODY, True)
    monkeypatch.setattr(m, "_scalar_projection", lambda *args: pytest.fail("changed custody source interpretation"))
    with pytest.raises(m.PriceDateProbeError):run(tmp_path, transport=transport)


def test_generated_output_ctime_may_settle_but_final_content_hash_is_binding(tmp_path, monkeypatch):
    original = m.publication.os.fstat
    def changed(fd):
        info = original(fd)
        fields = {name:getattr(info,name) for name in dir(info) if name.startswith("st_")}
        fields["st_ctime_ns"] += 10000
        return SimpleNamespace(**fields)
    # Existing settled-ctime helper excludes ctime, but retains all other held
    # properties and rehashes bytes. A real content mutation is covered above.
    monkeypatch.setattr(m.publication.os, "fstat", changed)
    assert run(tmp_path)["metadata"] is not None


def test_same_inode_size_and_restored_mtime_still_requires_fresh_content_hash(tmp_path):
    def transport(*args):
        leaf = output(tmp_path) / "reservation.json"
        before = leaf.stat(); raw = leaf.read_bytes()
        changed = raw.replace(b'"maximum_attempts":1', b'"maximum_attempts":2')
        assert len(changed) == len(raw) and changed != raw
        leaf.write_bytes(changed)
        os.utime(leaf, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert leaf.stat().st_ino == before.st_ino and leaf.stat().st_size == before.st_size
        return m.ProviderMetadataResponse(200, BODY, True)
    with pytest.raises(m.PriceDateProbeError):run(tmp_path, transport=transport)


class Stream:
    def __init__(self, body=BODY, *, status=200, url=None, headers=()):
        self.source = io.BytesIO(body); self.status = status; self.url = url
        self.headers = Message(); self.reads = 0; self.closed = False
        for name, value in headers:self.headers[name] = value
    def getcode(self):return self.status
    def geturl(self):return self.url
    def read(self, size):self.reads += 1; return self.source.read(size)
    def close(self):self.closed = True


@pytest.mark.parametrize("headers,code", [([("Content-Length", "1"), ("Content-Length", "1")], "invalid-content-length"),
    ([("Content-Length", "x")], "invalid-content-length"), ([("Content-Length", "4097")], "oversized-response"),
    ([("Content-Encoding", "gzip")], "unsupported-content-encoding"),
    ([("Content-Encoding", "identity"), ("Content-Encoding", "identity")], "unsupported-content-encoding"),
    ([("Transfer-Encoding", "chunked"), ("Content-Length", "1")], "partial-read"),
    ([("Transfer-Encoding", "gzip")], "partial-read"), ([("Content-Length", "999")], "truncated-response")])
def test_http_framing_refusals_discard_transient_body(headers, code):
    observed = m._read_bounded(Stream(headers=headers), 200)
    assert observed.disposition == code and observed.body == b"" and observed.body_complete is False


def test_actual_reader_four_kib_and_oversized_read_are_bounded():
    assert m._read_bounded(Stream(headers=[("Content-Length", str(len(BODY)))]), 200).body == BODY
    assert m._read_bounded(Stream(b"x" * 4097), 200).disposition == "oversized-response"
    class Wrong(Stream):
        def read(self, size):return b"x" * (size + 1)
    assert m._read_bounded(Wrong(), 200).disposition == "partial-read"


def default_context(monkeypatch):
    ctx = object.__new__(m._Context)
    ctx.root, ctx.fixture, ctx.baseline = m.LANE_ROOT, False, identity(m.LANE_ROOT)
    ctx.directory = SimpleNamespace(fd=42); ctx.check = lambda: None
    ctx.published = {name: "e" * 64 for name in ("reservation.json", "credential-read-started.json",
                    "credential-read-completed.json", "01-date-started.json")}
    leaves = {"reservation.json": m._reservation(ctx.baseline, False),
        "01-date-started.json": m._started(ctx.published["reservation.json"]),
        "credential-read-started.json": {"schema":m.SCHEMA, "maximum_credential_reads":1,
            "reservation_sha256":ctx.published["reservation.json"]},
        "credential-read-completed.json": {"schema":m.SCHEMA, "fixture_only":False,
            "started_sha256":ctx.published["credential-read-started.json"], "credential_read_observed":True,
            "disposition":"configured-keychain-credential-read"}}
    monkeypatch.setattr(m.publication, "_leaf", lambda directory, name, cap:(m._canonical(leaves[name]), ()))
    return ctx, leaves


@pytest.mark.parametrize("status", [200, 302, 401, 403, 429, 500])
def test_real_transport_fixed_query_tls_deadline_and_non200_no_read(monkeypatch, status):
    ctx, _ = default_context(monkeypatch)
    key = credential(fixture=False); url = m._live_url(key)
    stream = Stream(status=status, url=url); calls = []; handlers = []
    class Opener:
        def open(self, item, timeout):
            calls.append((item, timeout)); return stream
    monkeypatch.setattr(m.request, "build_opener", lambda *args:(handlers.extend(args), Opener())[1])
    observed = m._default_transport(m.REDACTED_URL, key, context=ctx)
    assert len(calls) == 1 and calls[0][1] == 15 and stream.closed
    item = calls[0][0]
    assert item.full_url == url and item.get_method() == "GET"
    assert item.get_header("Accept") == "application/json" and item.get_header("Accept-encoding") == "identity"
    assert quote_plus(TOKEN) in item.full_url and len(handlers) == 3
    assert type(handlers[0]) is m.request.ProxyHandler and handlers[0].proxies == {}
    assert type(handlers[1]) is m._DenyRedirect and type(handlers[2]) is m.request.HTTPSHandler
    assert (stream.reads > 0) is (status == 200)
    if status != 200:assert observed.body == b""
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


@pytest.mark.parametrize("failure", ["check", "missing-start", "bad-reservation", "read-start", "url", "fixture-context", "query"])
def test_real_transport_guards_refuse_before_opener(monkeypatch, failure):
    ctx, leaves = default_context(monkeypatch)
    monkeypatch.setattr(m.request, "build_opener", lambda *args:pytest.fail("unsafe opener construction"))
    url = m.REDACTED_URL
    if failure == "check":ctx.check = lambda: m._need(False, "lane_changed_during_probe")
    elif failure == "missing-start":ctx.published.pop("01-date-started.json")
    elif failure == "bad-reservation":leaves["reservation.json"]["request"]["filter"] = "last_close"
    elif failure == "read-start":leaves["credential-read-started.json"]["maximum_credential_reads"] = 2
    elif failure == "url":url += "&filter=last_close"
    elif failure == "fixture-context":ctx.fixture = True
    else:monkeypatch.setattr(m, "_live_url", lambda key:"https://eodhd.com/api/eod/A.US?filter=last_close")
    with pytest.raises(m.PriceDateProbeError):m._default_transport(url, credential(fixture=False), context=ctx)


def test_transport_exception_never_publishes_secret_url_or_upstream_text(tmp_path, capsys):
    def transport(*args):raise RuntimeError(m._live_url(credential()) + " PRIVATE_PROVIDER_ERROR")
    result = run(tmp_path, transport=transport)
    assert result["disposition"] == "transport-error" and result["metadata"] is None
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err
    assert b"PRIVATE_PROVIDER_ERROR" not in b"".join(snapshot(tmp_path).values())


def test_wall_deadline_bounds_open_and_read_and_restores_prior_handler(monkeypatch):
    old = signal.getsignal(signal.SIGALRM)
    monkeypatch.setattr(m, "TIMEOUT_SECONDS", 0.02)
    with pytest.raises(m.PriceDateProbeError, match="transport-timeout"):
        with m._Deadline():time.sleep(0.1)
    assert signal.getsignal(signal.SIGALRM) == old and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


@pytest.mark.parametrize("flag", ["isolated", "no_user_site", "no_site", "dont_write_bytecode", "cache"])
def test_production_interpreter_guard_precedes_git_identity(monkeypatch, flag):
    flags = {"isolated":1, "no_user_site":1, "no_site":1, "dont_write_bytecode":1}
    prefix = m.EMPTY_CACHE_PREFIX
    if flag == "cache":prefix = "unsafe"
    else:flags[flag] = 0
    monkeypatch.setattr(m, "sys", SimpleNamespace(flags=SimpleNamespace(**flags), pycache_prefix=prefix))
    monkeypatch.setattr(m.custody, "_identity", lambda *args:pytest.fail("pre-guard Git identity invoked"))
    with pytest.raises(m.PriceDateProbeError, match="isolated_source_interpreter_required"):m._identity(HEAD)


def test_cli_prints_only_fixed_summary_not_scalar_or_supplier_body(monkeypatch, capsys):
    monkeypatch.setattr(m, "run_probe", lambda head:{"status":"completed-date-metadata-probe", "http_status":200,
        "disposition":"date-only-capability-observed", "transport_invocation_count":1, "research_looks":0,
        "qc_jobs":0, "backtests":0, "metadata":{"private":TOKEN, "date":"2006-01-31"}})
    assert m.main(["--expected-head",HEAD]) == 0
    value = capsys.readouterr().out
    assert TOKEN not in value and "2006-01-31" not in value and "qc_jobs" in value


def test_cli_stopped_scope_is_nonzero_without_retry_or_success_label(monkeypatch, capsys):
    calls = []
    def stopped(head):
        calls.append(head)
        return {"status":"stopped-date-metadata-probe", "http_status":403, "disposition":"http_refused",
                "transport_invocation_count":1, "research_looks":0, "qc_jobs":0, "backtests":0}
    monkeypatch.setattr(m, "run_probe", stopped)
    assert m.main(["--expected-head", HEAD]) == 2
    assert calls == [HEAD] and "stopped-date-metadata-probe" in capsys.readouterr().out


def broken_context():
    ctx = object.__new__(m._Context); calls = []
    class Broken:
        def __init__(self, name):self.name = name
        def close(self):calls.append(self.name); raise OSError("PRIVATE_CLEANUP_DETAIL")
    ctx.directory, ctx.parent = Broken("directory"), Broken("parent")
    return ctx, calls


def test_cleanup_drains_both_owned_handles_and_sanitizes_standalone_failure():
    ctx, calls = broken_context()
    with pytest.raises(m.PriceDateProbeError, match="^context_cleanup_refused$"):ctx.close()
    assert calls == ["directory", "parent"] and ctx.directory is ctx.parent is None
    ctx.close()


def test_cleanup_failure_cannot_mask_active_primary_or_skip_parent():
    ctx, calls = broken_context()
    with pytest.raises(m.PriceDateProbeError, match="^primary_refused$"):
        try:
            raise m.PriceDateProbeError("primary_refused")
        finally:
            ctx.close()
    assert calls == ["directory", "parent"] and ctx.directory is ctx.parent is None


def test_constructor_failure_preserves_primary_and_drains_created_handles(tmp_path, monkeypatch):
    original = m.custody._Chain; calls = []
    class Wrapped:
        def __init__(self, root, parts, **kwargs):
            self.real = original(root, parts, **kwargs); self.fd = self.real.fd; self.parts = parts
        def recheck(self):self.real.recheck()
        def close(self):
            self.real.close(); calls.append(self.parts); raise OSError("PRIVATE_CLEANUP_DETAIL")
    monkeypatch.setattr(m.custody, "_Chain", Wrapped)
    monkeypatch.setattr(m._Context, "check", lambda self:m._need(False, "constructor_primary_refused"))
    with pytest.raises(m.PriceDateProbeError, match="^constructor_primary_refused$"):
        m._Context(tmp_path, True, HEAD, lambda head, root:identity(root), identity(tmp_path))
    assert calls == [(*m.OUTPUT_PARTS, m.AUDIT_ID), m.OUTPUT_PARTS]
