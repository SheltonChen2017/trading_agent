"""Invented reportDate bytes only; deny the whole process-tree network."""
import hashlib
import io
import json
import os
from pathlib import Path
import ssl
from urllib import error

import pytest

if os.name != "posix":
    pytest.skip(
        "IBWIN-CR01: EODHD private custody tests require POSIX filesystem primitives; Windows custody port deferred",
        allow_module_level=True,
    )

from research import insider_buying_eodhd_earnings_demo as m

HEAD = "a" * 40
IDENTITY = {"root": "invented", "branch": m.LANE_BRANCH, "head": HEAD,
            "source_sha256": {"invented.py": "b" * 64},
            "source_inventory_sha256": "c" * 64, "clean": True}
RAW = b'"2006-02-08"'  # Invented fixture, no claim about the requested issuer.
AUDIT_ID = "ib-eodhd-demo-invented"


def response(raw=RAW, status=200, complete=True, disposition=None):
    return m.ProviderMetadataResponse(status, raw, complete, disposition)


def run(tmp_path, *, transport=None, identity=None, audit_id=AUDIT_ID):
    return m.run_demo(audit_id, HEAD, root=tmp_path,
                      identity=identity or (lambda head, root: dict(IDENTITY)),
                      transport=transport or (lambda: response()),
                      clock=lambda: "2026-10-13T00:00:00Z")


def artifact(tmp_path):
    return tmp_path.joinpath(*m.ARTIFACT_PARTS, AUDIT_ID)


def test_started_reservation_and_fsync_precede_exactly_one_transport(tmp_path, monkeypatch):
    calls, fsyncs = [], []
    real_fsync = m.os.fsync
    monkeypatch.setattr(m.os, "fsync", lambda fd: (fsyncs.append(fd), real_fsync(fd))[1])
    def transport():
        directory = artifact(tmp_path)
        assert (directory.parent / "scope-reservation.json").is_file()
        assert (directory / "reservation.json").is_file()
        assert (directory / "started.json").is_file()
        assert not (directory / "complete.json").exists()
        assert len(fsyncs) >= 8
        reservation = json.loads((directory / "reservation.json").read_bytes())
        assert reservation["url"] == m.URL
        assert reservation["maximum_attempts"] == 1
        assert reservation["retry_resume_permitted"] is False
        calls.append(True)
        return response()
    result = run(tmp_path, transport=transport)
    assert calls == [True]
    receipt = result["receipt"]
    assert result["fixture_only"] is True
    assert receipt["disposition"] == "date-field-observed"
    assert receipt["date_field_observed"] is True
    assert receipt["body_sha256"] == hashlib.sha256(RAW).hexdigest()
    assert receipt["body_size_bytes"] == len(RAW)
    assert receipt["transport_invocation_count"] == 1
    assert receipt["http_response_observed"] is True
    assert "request_count" not in receipt
    assert all(receipt[name] is False for name in m.FALSE_FLAGS)
    assert RAW.decode()[1:-1] not in json.dumps(result)
    assert (artifact(tmp_path) / "response.json").read_bytes() == RAW
    assert hashlib.sha256((artifact(tmp_path) / "complete.json").read_bytes()).hexdigest() == result["complete_sha256"]
    assert artifact(tmp_path).stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in artifact(tmp_path).iterdir())


@pytest.mark.parametrize("audit_id", [AUDIT_ID, "ib-eodhd-demo-different"])
def test_completed_scope_cannot_repeat_even_with_another_audit_id(tmp_path, audit_id):
    run(tmp_path)
    calls = []
    with pytest.raises(m.EodhdDemoError, match="completed_or_ambiguous_scope_cannot_repeat"):
        run(tmp_path, audit_id=audit_id, transport=lambda: calls.append(True))
    assert not calls


def test_transport_exception_retains_ambiguous_scope_and_never_echoes(tmp_path):
    def failed():
        raise OSError("invented-private-sentinel")
    with pytest.raises(m.EodhdDemoError, match="transport_failed_started_reservation_preserved") as exc:
        run(tmp_path, transport=failed)
    assert "sentinel" not in str(exc.value)
    assert (artifact(tmp_path) / "started.json").is_file()
    assert not (artifact(tmp_path) / "complete.json").exists()
    with pytest.raises(m.EodhdDemoError, match="completed_or_ambiguous_scope"):
        run(tmp_path, audit_id="ib-eodhd-demo-different")


def test_keyboard_interrupt_preserves_no_retry_boundary(tmp_path):
    def stop():
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, transport=stop)
    assert (artifact(tmp_path) / "started.json").is_file()
    with pytest.raises(m.EodhdDemoError, match="completed_or_ambiguous_scope"):
        run(tmp_path)


def test_ambiguous_no_response_does_not_claim_measured_server_request_count(tmp_path):
    result = run(tmp_path, transport=lambda: response(b"", None, False, "transport-timeout"))
    receipt = result["receipt"]
    assert receipt["transport_invocation_count"] == 1
    assert receipt["http_response_observed"] is False
    assert "request_count" not in receipt
    assert receipt["date_field_observed"] is False


@pytest.mark.parametrize("raw", [b"null", b"{}", b"[]", b'{"reportDate":"2006-02-08"}',
    b'{"reportDate":"2006-02-08","epsActual":1}', b'"2005-12-31"', b'"2006-04-01"',
    b'"2006-02-30"', b'"2006-2-8"', b'"2006-02-08T00:00:00Z"', b'"2006-02-08" "extra"',
    b'"invented-private-sentinel"', b"NaN", b"Infinity", b"1e20", b"\xff", b""])
def test_schema_refuses_null_objects_extra_fields_non_dates_and_wrong_window(tmp_path, raw):
    result = run(tmp_path, transport=lambda: response(raw))
    assert result["receipt"]["disposition"] == "reportdate-schema-refused"
    assert result["receipt"]["date_field_observed"] is False
    assert result["receipt"]["response_body_retained"] is False
    assert not (artifact(tmp_path) / "response.json").exists()
    assert b"invented-private-sentinel" not in b"".join(p.read_bytes() for p in artifact(tmp_path).iterdir())


@pytest.mark.parametrize("status", [201, 204, 301, 307, 401, 403, 429, 500])
def test_only_http_200_scalar_is_success_and_error_bodies_are_not_retained(tmp_path, status):
    result = run(tmp_path, transport=lambda: response(b"invented-private-sentinel", status))
    receipt = result["receipt"]
    assert receipt["date_field_observed"] is False
    assert receipt["disposition"] in {"redirect-refused", "http-refused"}
    assert not (artifact(tmp_path) / "response.json").exists()
    assert "sentinel" not in json.dumps(result)


@pytest.mark.parametrize("raw,complete,disposition,expected", [
    (RAW, False, None, "partial-read"),
    (RAW, False, "partial-read", "partial-read"),
    (b"x" * (m.MAX_BODY_BYTES + 10), True, None, "oversized-response"),
    (b"", False, "response-origin-mismatch", "response-origin-mismatch"),
])
def test_incomplete_or_oversized_transport_refuses(tmp_path, raw, complete, disposition, expected):
    result = run(tmp_path, transport=lambda: response(raw, complete=complete, disposition=disposition))
    assert result["receipt"]["disposition"] == expected
    assert result["receipt"]["date_field_observed"] is False
    assert result["receipt"]["body_size_bytes"] <= m.MAX_BODY_BYTES + 1
    assert not (artifact(tmp_path) / "response.json").exists()


@pytest.mark.parametrize("bad", [None, {}, (200, RAW), m.ProviderMetadataResponse(True, RAW),
    m.ProviderMetadataResponse(200, bytearray(RAW)), m.ProviderMetadataResponse(200, RAW, 1),
    m.ProviderMetadataResponse(200, RAW, True, "invented-private-sentinel"),
    m.ProviderMetadataResponse(200, RAW, True, {}), m.ProviderMetadataResponse(None, RAW),
    m.ProviderMetadataResponse(None, b"", False, None)])
def test_typed_invalid_transport_refusal_retains_started_journal(tmp_path, bad):
    with pytest.raises(m.EodhdDemoError, match="invalid_transport_result_started"):
        run(tmp_path, transport=lambda: bad)
    assert (artifact(tmp_path) / "started.json").is_file()
    assert not (artifact(tmp_path) / "complete.json").exists()


@pytest.mark.parametrize("count,expected", [(1, "before_transport"), (2, "before_transport"), (3, "after_transport")])
def test_source_or_identity_change_refuses_and_preserves_journal(tmp_path, count, expected):
    calls, checks = [], []
    def identity(head, root):
        checks.append(True)
        return IDENTITY if len(checks) <= count else {**IDENTITY, "source_inventory_sha256": "d" * 64}
    with pytest.raises(m.EodhdDemoError, match="changed_" + expected):
        run(tmp_path, identity=identity, transport=lambda: (calls.append(True), response())[1])
    assert len(calls) == (1 if count == 3 else 0)
    assert not (artifact(tmp_path) / "complete.json").exists()


@pytest.mark.parametrize("audit_id", [None, "../escape", "ib-eodhd-demo-", "ib-eodhd-demo-/x",
                                      "ib-eodhd-demo-" + "x" * 81, "ib-eodhd-demo-x\n"])
def test_invalid_id_refuses_before_any_journal_or_transport(tmp_path, audit_id):
    with pytest.raises(m.EodhdDemoError, match="audit_id_format"):
        run(tmp_path, audit_id=audit_id)
    assert not list(tmp_path.iterdir())


def test_fake_identity_cannot_enable_real_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_default_transport", lambda: pytest.fail("real transport"))
    with pytest.raises(m.EodhdDemoError, match="real_transport_requires_real_lane_identity"):
        m.run_demo(AUDIT_ID, HEAD, root=tmp_path, identity=lambda head, root: IDENTITY)
    assert not list(tmp_path.iterdir())


def test_explicit_default_transport_cannot_bypass_real_identity_with_injection(tmp_path, monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("network opener"))
    with pytest.raises(m.EodhdDemoError, match="real_transport_requires_real_lane_identity"):
        run(tmp_path, transport=m._default_transport)
    assert not list(tmp_path.iterdir())


def test_wrong_root_refuses_before_git_or_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_git", lambda *a: pytest.fail("git"))
    monkeypatch.setattr(m, "_default_transport", lambda: pytest.fail("transport"))
    with pytest.raises(m.EodhdDemoError, match="designated_worktree_required"):
        m._identity(HEAD, root=tmp_path)


@pytest.mark.parametrize("head", [None, "A" * 40, "a" * 39, "a" * 40 + "\n", 3])
def test_expected_head_strict_before_git(head, monkeypatch):
    monkeypatch.setattr(m, "_git", lambda *a: pytest.fail("git"))
    with pytest.raises(m.EodhdDemoError, match="expected_head_format"):
        m._identity(head)


def identity_fixture(tmp_path, monkeypatch, *, status=b"", branch=m.LANE_BRANCH, source=b"source"):
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(m, "SOURCE_FILES", ("source.py",))
    (tmp_path / "source.py").write_bytes(source)
    def git(root, *args):
        if args == ("rev-parse", "--show-toplevel"):
            return str(tmp_path).encode()
        if args == ("branch", "--show-current"):
            return branch.encode()
        if args == ("rev-parse", "HEAD"):
            return HEAD.encode()
        if args[0] == "status":
            return status
        assert args == ("show", HEAD + ":source.py")
        return b"source"
    monkeypatch.setattr(m, "_git", git)


def test_identity_inventory_checks_current_against_tracked_committed_bytes(tmp_path, monkeypatch):
    identity_fixture(tmp_path, monkeypatch)
    identity = m._identity(HEAD, root=tmp_path)
    assert identity["clean"] is True
    assert identity["source_sha256"] == {"source.py": hashlib.sha256(b"source").hexdigest()}
    inventory = json.dumps(identity["source_sha256"], sort_keys=True, separators=(",", ":")).encode()
    assert identity["source_inventory_sha256"] == hashlib.sha256(inventory).hexdigest()
    (tmp_path / "source.py").write_bytes(b"changed")
    with pytest.raises(m.EodhdDemoError, match="tracked_source_bytes_mismatch"):
        m._identity(HEAD, root=tmp_path)


@pytest.mark.parametrize("status,branch,expected", [(b" M source.py\n", m.LANE_BRANCH, "clean_committed_lane"),
    (b"?? source.py\n", m.LANE_BRANCH, "clean_committed_lane"), (b"", "main", "worktree_branch_head")])
def test_identity_refuses_dirt_or_wrong_branch(tmp_path, monkeypatch, status, branch, expected):
    identity_fixture(tmp_path, monkeypatch, status=status, branch=branch)
    with pytest.raises(m.EodhdDemoError, match=expected):
        m._identity(HEAD, root=tmp_path)


@pytest.mark.parametrize("mutation", ["symlink", "hardlink"])
def test_source_symlink_or_hardlink_refused(tmp_path, monkeypatch, mutation):
    identity_fixture(tmp_path, monkeypatch)
    other = tmp_path / "other.py"
    source = tmp_path / "source.py"
    if mutation == "hardlink":
        os.link(source, other)
    else:
        source.rename(other)
        source.symlink_to(other)
    with pytest.raises(m.EodhdDemoError):
        m._identity(HEAD, root=tmp_path)


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_symlink_journal_ancestor_refused_without_external_writes(tmp_path, depth):
    outside = tmp_path / "outside"
    outside.mkdir()
    parent = tmp_path
    for name in m.ARTIFACT_PARTS[:depth]:
        parent /= name
        parent.mkdir()
    (parent / m.ARTIFACT_PARTS[depth]).symlink_to(outside, target_is_directory=True)
    with pytest.raises(m.EodhdDemoError, match="private_journal_or_identity"):
        run(tmp_path)
    assert not list(outside.iterdir())


@pytest.mark.parametrize("leaf", ["reservation.json", "started.json", "scope-reservation.json"])
@pytest.mark.parametrize("mutation", ["bytes", "symlink", "hardlink", "mode", "missing"])
def test_hash_mode_link_custody_rechecked_before_completion(tmp_path, leaf, mutation):
    def transport():
        path = artifact(tmp_path) / leaf
        if leaf == "scope-reservation.json":
            path = path.parent.parent / leaf
        if mutation == "bytes":
            path.write_bytes(b"changed")
        elif mutation == "mode":
            path.chmod(0o644)
        elif mutation == "missing":
            path.unlink()
        else:
            kept = tmp_path / "kept"
            kept.write_bytes(path.read_bytes())
            path.unlink()
            if mutation == "symlink":
                path.symlink_to(kept)
            else:
                os.link(kept, path)
        return response()
    with pytest.raises(m.EodhdDemoError):
        run(tmp_path, transport=transport)
    assert not (artifact(tmp_path) / "complete.json").exists()
    assert not (artifact(tmp_path) / "response.json").exists()


def test_unexpected_leaf_and_changed_artifact_directory_refuse(tmp_path):
    def transport():
        (artifact(tmp_path) / "extra").write_bytes(b"invented")
        return response()
    with pytest.raises(m.EodhdDemoError, match="journal_custody"):
        run(tmp_path, transport=transport)


@pytest.mark.parametrize("depth", [1, 2, 3, 4])
def test_renamed_journal_ancestors_cannot_complete(tmp_path, depth):
    moved = tmp_path / "moved"
    def transport():
        parts = (*m.ARTIFACT_PARTS, AUDIT_ID)
        ancestor = tmp_path.joinpath(*parts[:depth])
        ancestor.rename(moved)
        ancestor.mkdir(mode=0o700)
        return response()
    with pytest.raises(m.EodhdDemoError):
        run(tmp_path, transport=transport)
    assert not tuple(moved.rglob("complete.json"))


@pytest.mark.parametrize("mutation", ["swap", "mode", "hardlink"])
def test_leaf_read_binds_named_identity_permission_and_links_after_read(tmp_path, monkeypatch, mutation):
    path = tmp_path / "leaf.json"
    path.write_bytes(b"invented")
    path.chmod(0o600)
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    real_fdopen = m.os.fdopen
    class DuringRead:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            self.stream.__enter__()
            return self
        def __exit__(self, *args):
            return self.stream.__exit__(*args)
        def fileno(self):
            return self.stream.fileno()
        def read(self, size):
            raw = self.stream.read(size)
            if mutation == "swap":
                path.rename(tmp_path / "displaced.json")
                path.write_bytes(raw)
                path.chmod(0o600)
            elif mutation == "mode":
                path.chmod(0o644)
            else:
                os.link(path, tmp_path / "other.json")
            return raw
    monkeypatch.setattr(m.os, "fdopen", lambda fd, mode: DuringRead(real_fdopen(fd, mode)))
    try:
        with pytest.raises(m.EodhdDemoError, match="custody_leaf"):
            m._read_leaf(directory, path.name, limit=100)
    finally:
        os.close(directory)


def test_fifo_named_leaf_refused_before_open_can_block(tmp_path, monkeypatch):
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    os.mkfifo(tmp_path / "leaf.json", 0o600)
    real_open = m.os.open
    def safe_open(name, flags, *args, **kwargs):
        if name == "leaf.json":
            assert flags & os.O_NONBLOCK, "a FIFO must never be opened in blocking mode"
        return real_open(name, flags, *args, **kwargs)
    monkeypatch.setattr(m.os, "open", safe_open)
    try:
        with pytest.raises(m.EodhdDemoError, match="custody_leaf"):
            m._read_leaf(directory, "leaf.json", limit=100)
    finally:
        os.close(directory)


def test_regular_to_fifo_swap_before_open_is_nonblocking_and_refused(tmp_path, monkeypatch):
    path = tmp_path / "leaf.json"
    path.write_bytes(b"invented")
    path.chmod(0o600)
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    real_open = m.os.open
    def swapped_open(name, flags, *args, **kwargs):
        if name == "leaf.json":
            assert flags & os.O_NONBLOCK, "a raced FIFO must never block"
            path.unlink()
            os.mkfifo(path, 0o600)
        return real_open(name, flags, *args, **kwargs)
    monkeypatch.setattr(m.os, "open", swapped_open)
    try:
        with pytest.raises(m.EodhdDemoError, match="custody_leaf"):
            m._read_leaf(directory, "leaf.json", limit=100)
    finally:
        os.close(directory)


def test_journal_directory_is_reattached_after_last_leaf_read(tmp_path, monkeypatch):
    run(tmp_path)
    parent_path = artifact(tmp_path).parent
    parent = os.open(parent_path, os.O_RDONLY | os.O_DIRECTORY)
    directory = os.open(artifact(tmp_path), os.O_RDONLY | os.O_DIRECTORY)
    latch_sha = hashlib.sha256((parent_path / "scope-reservation.json").read_bytes()).hexdigest()
    published = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifact(tmp_path).iterdir()}
    real_read = m._read_leaf
    def displaced_after_read(fd, name, **kwargs):
        raw = real_read(fd, name, **kwargs)
        if name == list(published)[-1]:
            artifact(tmp_path).rename(tmp_path / "moved")
            artifact(tmp_path).mkdir(mode=0o700)
        return raw
    monkeypatch.setattr(m, "_read_leaf", displaced_after_read)
    try:
        with pytest.raises(m.EodhdDemoError, match="journal_custody"):
            m._check_journal(parent, directory, AUDIT_ID, latch_sha, published, root=tmp_path)
    finally:
        os.close(directory)
        os.close(parent)


class Stream(io.BytesIO):
    def __init__(self, raw=RAW, *, status=200, url=m.URL, headers=None):
        super().__init__(raw)
        self.status, self.url = status, url
        self.headers = headers or {}
    def getcode(self):
        return self.status
    def geturl(self):
        return self.url


def stub_opener(monkeypatch, stream=None, exc=None):
    calls = []
    class Opener:
        def open(self, item, timeout):
            calls.append((item, timeout))
            if exc is not None:
                raise exc
            return stream
    def build(*handlers):
        calls.append(handlers)
        return Opener()
    # Patch before the direct default transport is invoked, under OS network denial.
    monkeypatch.setattr(m.request, "build_opener", build)
    return calls


def run_default_fixture(tmp_path, monkeypatch):
    # Real-root checking is replaced only within this invented offline fixture;
    # the actual opener has already been stubbed and OS network denial applies.
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    monkeypatch.setattr(m, "_identity", lambda head, root=None: dict(IDENTITY))
    return m.run_demo(AUDIT_ID, HEAD, root=tmp_path, identity=m._identity)["receipt"]


def test_default_rechecks_source_inventory_before_any_opener(tmp_path, monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("network opener"))
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    checks = []
    def identity(head, root=None):
        checks.append(True)
        return IDENTITY if len(checks) < 4 else {**IDENTITY, "source_inventory_sha256": "d" * 64}
    monkeypatch.setattr(m, "_identity", identity)
    with pytest.raises(m.EodhdDemoError, match="transport_failed_started_reservation_preserved"):
        m.run_demo(AUDIT_ID, HEAD, root=tmp_path, identity=identity)
    assert len(checks) == 4
    assert (artifact(tmp_path) / "started.json").is_file()


def test_default_rechecks_started_custody_before_any_opener(tmp_path, monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("network opener"))
    monkeypatch.setattr(m, "LANE_ROOT", tmp_path)
    checks = []
    def identity(head, root=None):
        checks.append(True)
        if len(checks) == 4:
            (artifact(tmp_path) / "started.json").write_bytes(b"tampered")
        return IDENTITY
    monkeypatch.setattr(m, "_identity", identity)
    with pytest.raises(m.EodhdDemoError, match="transport_failed_started_reservation_preserved"):
        m.run_demo(AUDIT_ID, HEAD, root=tmp_path, identity=identity)
    assert len(checks) == 4
    assert not (artifact(tmp_path) / "complete.json").exists()


def test_default_refuses_absent_started_journal_before_any_opener(monkeypatch):
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("network opener"))
    monkeypatch.setattr(m, "_identity", lambda head, root=None: IDENTITY)
    with pytest.raises(m.EodhdDemoError, match="real_transport_started_journal_required"):
        m._default_transport(expected_head=HEAD, baseline=IDENTITY, parent=-1, directory=-1,
                             audit_id=AUDIT_ID, latch_sha="b" * 64, published={})


def test_default_transport_exact_public_scalar_profile_no_proxy_redirect_or_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://invented.proxy:1")
    stream = Stream(headers={"Content-Length": str(len(RAW))})
    calls = stub_opener(monkeypatch, stream)
    result = run_default_fixture(tmp_path, monkeypatch)
    assert len(calls) == 2
    handlers = calls[0]
    assert handlers[0].proxies == {}
    assert isinstance(handlers[1], m._DenyRedirect)
    assert handlers[1].redirect_request(None, None, 302, "invented", {}, "https://other.invalid") is None
    assert handlers[2]._context.verify_mode == ssl.CERT_REQUIRED
    assert handlers[2]._context.check_hostname is True
    item, timeout = calls[1]
    assert item.full_url == m.URL
    assert item.get_method() == "GET" and item.data is None and timeout == 15
    assert item.get_header("Accept-encoding") == "identity"
    assert item.get_header("Authorization") is None
    assert result["date_field_observed"] is True
    assert result["body_sha256"] == hashlib.sha256(RAW).hexdigest()
    assert stream.closed


@pytest.mark.parametrize("headers,raw,expected", [
    ({"Content-Length": str(m.MAX_BODY_BYTES + 1)}, b"private", "oversized-response"),
    ({}, b"x" * (m.MAX_BODY_BYTES + 1), "oversized-response"),
    ({"Content-Encoding": "gzip"}, b"private", "unsupported-content-encoding"),
    ({"Content-Length": "-1"}, b"private", "invalid-content-length"),
    ({"Content-Length": "100"}, RAW, "truncated-response"),
])
def test_default_transport_reuses_bounded_read_controls(tmp_path, monkeypatch, headers, raw, expected):
    stream = Stream(raw, headers=headers)
    calls = stub_opener(monkeypatch, stream)
    result = run_default_fixture(tmp_path, monkeypatch)
    assert result["disposition"] == expected
    assert result["body_size_bytes"] <= m.MAX_BODY_BYTES + 1
    assert len(calls) == 2 and stream.closed


@pytest.mark.parametrize("status,url,expected", [(302, m.URL, "redirect-refused"),
    (200, "https://other.invalid", "response-origin-mismatch"), (True, m.URL, "invalid-http-status")])
def test_default_origin_redirect_and_status_checks(tmp_path, monkeypatch, status, url, expected):
    stream = Stream(status=status, url=url)
    calls = stub_opener(monkeypatch, stream)
    result = run_default_fixture(tmp_path, monkeypatch)
    assert result["disposition"] == expected
    assert len(calls) == 2 and stream.closed


@pytest.mark.parametrize("exc,expected", [(TimeoutError("private"), "transport-timeout"),
    (error.URLError(TimeoutError("private")), "transport-timeout"),
    (error.URLError("private"), "transport-error"), (OSError("private"), "transport-error")])
def test_default_transport_sanitizes_errors_and_never_retries(tmp_path, monkeypatch, exc, expected):
    calls = stub_opener(monkeypatch, exc=exc)
    result = run_default_fixture(tmp_path, monkeypatch)
    assert result["disposition"] == expected and len(calls) == 2
    assert result["body_size_bytes"] == 0 and result["body_complete"] is False
    assert "private" not in json.dumps(result)


def test_http_error_is_bounded_and_never_followed(tmp_path, monkeypatch):
    exc = error.HTTPError(m.URL, 302, "private", {"Location": "https://other.invalid"}, io.BytesIO(b"private"))
    calls = stub_opener(monkeypatch, exc=exc)
    result = run_default_fixture(tmp_path, monkeypatch)
    assert result["disposition"] == "redirect-refused" and len(calls) == 2
    assert result["body_size_bytes"] == 7


def test_import_is_inert_and_reads_no_credentials(monkeypatch):
    import importlib.util
    import sys
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("transport"))
    class NoCredentials(dict):
        def get(self, *a):
            pytest.fail("credentials")
    monkeypatch.setattr(m.os, "environ", NoCredentials())
    spec = importlib.util.spec_from_file_location("eodhd_demo_inert_fixture", m.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert module.URL == m.URL


def test_cli_typed_refusal_and_private_result_does_not_echo(monkeypatch, capsys):
    def refuse(*a):
        raise m.EodhdDemoError("worktree_branch_head_mismatch")
    monkeypatch.setattr(m, "run_demo", refuse)
    assert m.main(["--audit-id", AUDIT_ID, "--expected-head", HEAD]) == 2
    assert json.loads(capsys.readouterr().out) == {"probe_refused": "worktree_branch_head_mismatch"}
    result = {"receipt": {"date_field_observed": True}, "complete_sha256": "b" * 64}
    monkeypatch.setattr(m, "run_demo", lambda *a: result)
    assert m.main(["--audit-id", AUDIT_ID, "--expected-head", HEAD]) == 0
    assert json.loads(capsys.readouterr().out) == result
