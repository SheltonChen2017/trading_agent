"""Fabricated APFS/flags and temporary FD composition; no actual native proof.

Only this named fixture supplies virtual kernel flags/directory all-entry link
counts and a temporary fixed-base substitute. Genuine p._Files, creator/frame
checks, original RO handoff, seals and audits remain unmodified. These tests
cannot establish anything about FileProvider or actual private local storage.
"""
import ast
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from scripts import prove_short_interest_local_metadata as m

# Only protected-I/O cases require POSIX; pure parsing, transport and early
# refusal checks must remain active on the supported Windows host.
_POSIX_CAPTURE_ONLY = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason=(
        "the protected-capture runtime requires POSIX ownership and mode "
        "semantics (os.getuid, O_NOFOLLOW, 0o600/0o700, symlinks); it cannot "
        "execute on this host, see the lane record SI-CR17-002"
    ),
)

HEAD, REMOTE, OPERATION = "a" * 40, "b" * 40, "c" * 64


@pytest.fixture(autouse=True)
def forbid_actual_native_or_sources(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Actual native/source/subprocess work is forbidden in this fabricated selection")
    for name in ("_set_file_flags", "_native_statfs", "_native_command", "_launch_worker", "_launch_service"):
        monkeypatch.setattr(m.p, name, denied)
    monkeypatch.setattr(m.p, "_guard", denied)
    monkeypatch.setattr(m, "_USED", False)
    monkeypatch.setattr(m, "_COMPARISONS", {})


@pytest.fixture
def fabricated_local_profile(tmp_path, monkeypatch):
    """Explicit temporary/kernel/code seams, never actual registered evidence."""
    actual_os = os
    actual_fstat, actual_stat, actual_open = os.fstat, os.stat, os.open
    base = tmp_path / "AppSupport" / "CodexShortInterestCustody"
    base.parent.mkdir(mode=0o700)
    flags, directory_paths, emitted, checks, profiles = {}, {}, [], [], []
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(m.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(m.time, "sleep", lambda seconds: setattr(clock, "now", clock.now + seconds))
    monkeypatch.setattr(m, "BASE", base)
    monkeypatch.setattr(m, "registered", lambda: None)
    monkeypatch.setattr(m.p, "_guard", lambda head, remote: checks.append((head, remote)))
    def set_flags(fd, value):
        info = actual_fstat(fd)
        key = info.st_dev, info.st_ino
        assert value == flags.get(key, 0) | 2
        flags[key] = value
    monkeypatch.setattr(m.p, "_set_file_flags", set_flags)
    monkeypatch.setattr(m.p, "_file_flags", lambda info: flags.get((info.st_dev, info.st_ino), 0))
    monkeypatch.setattr(m.p, "_native_statfs", lambda fd: {"fstype": "apfs", "flags": m.p.native.MNT_LOCAL,
        "fsid": (1, 2), "mounted_on": "/fabricated", "mounted_from": "/dev/fabricated"})
    class ProxyOS:
        def __getattr__(self, name):
            return getattr(actual_os, name)
        def getpid(self):
            return self.pid
        def open(self, path, options, mode=0o777, *, dir_fd=None):
            fd = actual_open(path, options, mode, dir_fd=dir_fd)
            info = actual_fstat(fd)
            if stat.S_ISDIR(info.st_mode):
                if dir_fd is not None and dir_fd in directory_paths:
                    directory_paths[fd] = directory_paths[dir_fd] / path
                else:
                    directory_paths[fd] = Path(path)
            return fd
        def _overlay(self, info, path):
            if not stat.S_ISDIR(info.st_mode):
                return info
            values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            # Ancestor protection is fabricated explicitly; private directories
            # retain real modes, so wrong private modes remain sensitive.
            if path is None or base.parent not in (path, *path.parents):
                values["st_mode"] = stat.S_IFDIR | 0o700
                values["st_uid"] = actual_os.getuid()
            else:
                values["st_nlink"] = 2 + len(actual_os.listdir(path))
            return SimpleNamespace(**values)
        def fstat(self, fd):
            return self._overlay(actual_fstat(fd), directory_paths.get(fd))
        def stat(self, path, *args, **kwargs):
            full = Path(path)
            if kwargs.get("dir_fd") is not None:
                full = directory_paths[kwargs["dir_fd"]] / path
            return self._overlay(actual_stat(path, *args, **kwargs), full)
    proxy = ProxyOS()
    proxy.pid = 1101
    monkeypatch.setattr(m, "os", proxy)
    # Path.lstat bypasses the module proxy. Keep its exact native result for
    # files, and the same fabricated directory observation for this fixture.
    actual_lstat = Path.lstat
    monkeypatch.setattr(Path, "lstat", lambda path, *a, **kw: proxy._overlay(actual_lstat(path, *a, **kw), path))
    manifest = {name: m.SDK_SHA256 if name == m.p.DRIVER else "d" * 64 for name in m.CODE_FILES}
    class Code:
        def __init__(self, head, remote, elapsed):
            assert (head, remote) == (HEAD, REMOTE)
            self.fd, self.manifest, self.events = 999999, manifest.copy(), []
            self.elapsed = elapsed
        def audit(self):
            self.elapsed.check(); self.events.append("audit")
            return self.manifest
        def close(self):
            self.events.append("close"); self.fd = None
        def named(self):
            self.events.append("named")
    monkeypatch.setattr(m, "_Code8", Code)
    real_emit = m._emit
    def emit(value, fd=1):
        raw = (m.canonical_json(value) + "\n").encode()
        if value.get("event") == "producer_sealed":
            for cap, row in m.p._FILE_CREATORS.items():
                if row["path"] == base / m.NAMESPACE / "data":
                    profiles.append((m.p._descriptor_access(row["fd"]),
                        m.p._descriptor_access(row["original_ro_fd"]),
                        actual_os.get_inheritable(row["fd"]), actual_os.get_inheritable(row["original_ro_fd"])))
        emitted.append((value, raw))
        return raw
    monkeypatch.setattr(m, "_emit", emit)
    return SimpleNamespace(base=base, flags=flags, clock=clock, proxy=proxy,
        emitted=emitted, checks=checks, manifest=manifest, real_emit=real_emit,
        actual_fstat=actual_fstat, actual_os=actual_os, profiles=profiles)


def _run_producer(fixture, monkeypatch):
    class Input:
        def __init__(self, fd, clock):
            pass
        def read(self):
            raw = next(raw for value, raw in fixture.emitted if value["event"] == "producer_sealed")
            return (m.canonical_json({**m._binding(HEAD, REMOTE, OPERATION), "event": "observer_open",
                "pid": 1102, "producer_raw_sha256": m.hash_bytes(raw)}) + "\n").encode()
        def finish(self):
            pass
    monkeypatch.setattr(m, "_Lines", Input)
    m.producer(HEAD, REMOTE, OPERATION)
    return {value["event"]: (value, raw) for value, raw in fixture.emitted}


def _observer_input(fixture, packets, monkeypatch, *, returncode=0):
    rows = [packets["producer_sealed"][1], packets["producer_closed"][1],
        (m.canonical_json({**m._binding(HEAD, REMOTE, OPERATION), "event": "producer_exit",
            "pid": 1101, "returncode": returncode}) + "\n").encode()]
    class Input:
        def __init__(self, fd, clock):
            self.rows = iter(rows)
        def read(self):
            return next(self.rows)
        def finish(self):
            assert list(self.rows) == []
    monkeypatch.setattr(m, "_Lines", Input)
    monkeypatch.setattr(m, "_USED", False)
    fixture.proxy.pid = 1102
    return rows


@_POSIX_CAPTURE_ONLY
def test_policy_is_one_fixed_source_free_finite_profile():
    assert str(m.BASE) == "/Users/sheltonchen/Library/Application Support/CodexShortInterestCustody"
    assert m.NAMESPACE == "local-metadata-20261103-v1"
    assert len(m.LITERAL) == 41 and len(m.CODE_FILES) == len(set(m.CODE_FILES)) == 8
    assert m.CODE_FILES[:-1] == m.p.CODE_FILES
    assert m.MAXIMUM_SECONDS == 300 and m.TAIL_SECONDS == 40
    assert m.policy()["retry_count"] == 0 and m.policy()["maximum_control_bytes"] == 65536
    assert m.hash_payload(m.policy()) == m.POLICY_SHA256
    assert all(value is False for key, value in m.authority().items()
        if key not in {"location_metadata_observation_only", "provider_HTTP", "credential_reads", "new_source_claims", "source_STARTs", "source_bytes", "qc_attempts"})


@_POSIX_CAPTURE_ONLY
def test_registration_checks_frozen_profile_without_actual_platform_call(monkeypatch):
    calls = []
    monkeypatch.setattr(m.p, "_require_immutable_platform", lambda: calls.append("platform"))
    m.registered()
    assert calls == ["platform"]
    monkeypatch.setattr(m, "BASE", Path("/private/fabricated-override"))
    with pytest.raises(m.LocalMetadataRefusal, match="local_policy"):
        m.registered()


def test_no_path_override_or_native_domain_import_framework():
    tree = ast.parse(Path(m.__file__).read_text())
    assert not any(isinstance(node, ast.ClassDef) and node.bases
        and any(isinstance(base, ast.Attribute) and base.attr == "_Files" for base in node.bases) for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Assign) and any(isinstance(target, ast.Attribute)
        and target.attr in {"ROOT", "PARENT", "CODE_FILES", "_Files"} for target in node.targets) for node in ast.walk(tree))
    assert m.producer.__globals__["p"]._Files is m.p._Files


@_POSIX_CAPTURE_ONLY
def test_complete_fabricated_genuine_publisher_original_RO_and_independent_tail(fabricated_local_profile, monkeypatch):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    assert packets["producer_sealed"][0]["original9"][4:7] == [0o600, 1, 41]
    assert packets["producer_sealed"][0]["flags"] == 2
    assert (f.base / m.NAMESPACE / "data" / m.LITERAL_NAME).read_bytes() == m.LITERAL
    _observer_input(f, packets, monkeypatch)
    m.observer(HEAD, REMOTE, OPERATION)
    closed = f.emitted[-1][0]
    assert closed["event"] == "observer_closed" and closed["samples"] == 161
    assert closed["tail_seconds"] == 40 and f.clock.now == 140
    assert closed["producer_raw_sha256"] == m.hash_bytes(packets["producer_sealed"][1])
    assert closed["producer_closed_raw_sha256"] == m.hash_bytes(packets["producer_closed"][1])
    assert closed["controller_exit0_is_an_observation_claim_until_owned_wait_correlated"] is True
    assert closed["authority"] == m.authority()
    assert f.profiles == [(os.O_RDONLY, os.O_RDONLY, False, False)]
    assert all(len(raw) <= 4096 for value, raw in f.emitted)
    assert not list((f.base / m.NAMESPACE / "control").iterdir())


@_POSIX_CAPTURE_ONLY
def test_existing_base_is_not_adopted(fabricated_local_profile):
    f = fabricated_local_profile
    f.base.mkdir(mode=0o700)
    with pytest.raises(m.LocalMetadataRefusal, match="local_exists"):
        m._Scope(m._Clock(), create=True)


@_POSIX_CAPTURE_ONLY
def test_base_symlink_not_adopted(fabricated_local_profile):
    f = fabricated_local_profile
    target = f.base.parent / "target"
    target.mkdir(mode=0o700)
    f.base.symlink_to(target, target_is_directory=True)
    with pytest.raises(m.LocalMetadataRefusal, match="local_exists"):
        m._Scope(m._Clock(), create=True)


@pytest.mark.parametrize("field,value", [("st_uid", -1), ("st_mode", stat.S_IFDIR | 0o770), ("st_mode", stat.S_IFREG | 0o700)])
@_POSIX_CAPTURE_ONLY
def test_ancestry_owner_mode_and_type_refuse(field, value):
    info = dict(st_mode=stat.S_IFDIR | 0o700, st_uid=os.getuid(), st_gid=os.getgid(), st_dev=1, st_ino=2, st_nlink=2)
    info[field] = value
    with pytest.raises(m.LocalMetadataRefusal, match="local_directory"):
        m._directory_pin(SimpleNamespace(**info), True)


@pytest.mark.parametrize("fstype,flags", [("hfs", 0x1000), ("apfs", 0), ("apfs", 0x1001), ("apfs", 0x201000)])
def test_host_requires_local_writable_ownership_enabled_APFS(monkeypatch, fstype, flags):
    monkeypatch.setattr(m.p, "_native_statfs", lambda fd: {"fstype": fstype, "flags": flags})
    with pytest.raises(m.LocalMetadataRefusal, match="local_host"):
        m._host(9)


def test_host_does_not_claim_nobrowse_or_native_volume_admission(monkeypatch):
    monkeypatch.setattr(m.p, "_native_statfs", lambda fd: {"fstype": "apfs", "flags": 0x1000,
        "fsid": (1, 2), "mounted_on": "/", "mounted_from": "/dev/fabricated"})
    assert m._host(9)[1] == "apfs"
    assert m.authority()["native_supervision_admitted"] is False


@pytest.mark.parametrize("mutation", ["extra_data", "extra_control", "extra_namespace", "chmod", "missing_literal"])
@_POSIX_CAPTURE_ONLY
def test_exact_membership_and_private_mode_refuse(fabricated_local_profile, monkeypatch, mutation):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    _observer_input(f, packets, monkeypatch)
    root = f.base / m.NAMESPACE
    if mutation == "extra_data":
        (root / "data" / "extra").write_bytes(b"x")
    elif mutation == "extra_control":
        (root / "control" / "extra").write_bytes(b"x")
    elif mutation == "extra_namespace":
        (root / "extra").mkdir()
    elif mutation == "chmod":
        (root / "data").chmod(0o750)
    else:
        (root / "data" / m.LITERAL_NAME).unlink()
    with pytest.raises((m.LocalMetadataRefusal, OSError)):
        m.observer(HEAD, REMOTE, OPERATION)
    assert f.emitted[-1][0]["event"] == "observer_refused"


@pytest.mark.parametrize("mutation", ["flags", "ctime", "bytes", "replace", "mode", "link"])
@_POSIX_CAPTURE_ONLY
def test_original_file_drift_is_never_rebased(fabricated_local_profile, monkeypatch, mutation):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    _observer_input(f, packets, monkeypatch)
    path = f.base / m.NAMESPACE / "data" / m.LITERAL_NAME
    info = f.actual_os.stat(path)
    if mutation == "flags":
        f.flags[(info.st_dev, info.st_ino)] = 0
    elif mutation == "ctime":
        f.actual_os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1))
    elif mutation == "bytes":
        path.write_bytes(b"x" * 41)
    elif mutation == "replace":
        path.unlink(); path.write_bytes(m.LITERAL); path.chmod(0o600)
    elif mutation == "mode":
        path.chmod(0o640)
    else:
        f.actual_os.link(path, path.with_name("extra-link"))
    with pytest.raises((m.LocalMetadataRefusal, OSError)):
        m.observer(HEAD, REMOTE, OPERATION)


@pytest.mark.parametrize("returncode", [None, -15, 1, True, "0"])
@_POSIX_CAPTURE_ONLY
def test_unknown_or_nonzero_actual_exit_claim_vetoes(fabricated_local_profile, monkeypatch, returncode):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    _observer_input(f, packets, monkeypatch, returncode=returncode)
    with pytest.raises(m.LocalMetadataRefusal, match="local_exit"):
        m.observer(HEAD, REMOTE, OPERATION)
    assert f.clock.now == 100


@_POSIX_CAPTURE_ONLY
def test_raw_line_reader_preserves_coalesced_lines_exact_large_integers():
    reader_fd, writer_fd = os.pipe()
    try:
        raw = b'{"event":"x","ns":9007199254740993001}\n'
        os.write(writer_fd, raw + b'{"ack":true}\n')
        reader = m._Lines(reader_fd, m._Clock())
        assert reader.read() == raw
        assert reader.read() == b'{"ack":true}\n'
        assert m._decode(raw)["ns"] == 9007199254740993001
    finally:
        os.close(reader_fd); os.close(writer_fd)


@pytest.mark.parametrize("extra", [b"{}\n", b"x"])
@_POSIX_CAPTURE_ONLY
def test_raw_finish_refuses_coalesced_extra_packets_or_partial_bytes(extra):
    reader_fd, writer_fd = os.pipe()
    try:
        os.write(writer_fd, b"{}\n" + extra)
        os.close(writer_fd); writer_fd = None
        reader = m._Lines(reader_fd, m._Clock())
        assert reader.read() == b"{}\n"
        with pytest.raises(m.LocalMetadataRefusal, match="local_wire"):
            reader.finish()
    finally:
        os.close(reader_fd)
        if writer_fd is not None:
            os.close(writer_fd)


@_POSIX_CAPTURE_ONLY
def test_raw_finish_requires_actual_EOF_and_rejects_late_extra_byte():
    reader_fd, writer_fd = os.pipe()
    try:
        reader = m._Lines(reader_fd, m._Clock())
        os.write(writer_fd, b"x")
        with pytest.raises(m.LocalMetadataRefusal, match="local_wire"):
            reader.finish()
    finally:
        os.close(reader_fd); os.close(writer_fd)


@_POSIX_CAPTURE_ONLY
def test_raw_finish_accepts_exact_EOF():
    reader_fd, writer_fd = os.pipe()
    os.close(writer_fd)
    try:
        assert m._Lines(reader_fd, m._Clock()).finish() is None
    finally:
        os.close(reader_fd)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}\n', b'{"a":NaN}\n', b'{"a":1.0}\n', b'{}', b'{}\n{}\n', b'{ "a":1}\n', b'[]\n'])
def test_noncanonical_duplicate_float_or_extra_line_refuses(raw):
    with pytest.raises(m.LocalMetadataRefusal, match="local_wire"):
        m._decode(raw)


@_POSIX_CAPTURE_ONLY
def test_raw_reader_EOF_failure_is_permanently_latched():
    reader_fd, writer_fd = os.pipe()
    os.close(writer_fd)
    try:
        reader = m._Lines(reader_fd, m._Clock())
        with pytest.raises(m.LocalMetadataRefusal, match="local_wire"):
            reader.read()
        with pytest.raises(m.LocalMetadataRefusal, match="local_latched"):
            reader.read()
    finally:
        os.close(reader_fd)


def test_wire_limits_before_unbounded_read_and_total_input():
    reader_fd, writer_fd = os.pipe()
    try:
        reader = m._Lines(reader_fd, m._Clock())
        reader.pending.extend(b"x" * m.MAXIMUM_WIRE)
        with pytest.raises(m.LocalMetadataRefusal, match="local_wire"):
            reader.read()
    finally:
        os.close(reader_fd); os.close(writer_fd)


@pytest.mark.parametrize("delta", [-1, float("nan"), float("inf"), 301])
def test_clock_backward_nonfinite_deadline_refuse(monkeypatch, delta):
    now = [100.0]
    monkeypatch.setattr(m.time, "monotonic", lambda: now[0])
    clock = m._Clock()
    now[0] = 100 + delta
    with pytest.raises(m.LocalMetadataRefusal):
        clock.check()
    now[0] = 101
    with pytest.raises(m.LocalMetadataRefusal, match="local_latched"):
        clock.check()


def test_safe_diagnostics_never_format_error_text_or_dynamic_type():
    class SecretError(OSError):
        def __str__(self):
            raise AssertionError("no formatting")
    error = SecretError(errno.EACCES, "/private/SECRET")
    summary = m.failure_summary(error)
    assert summary["errno_name"] == "EACCES"
    assert "SECRET" not in json.dumps(summary) and "SecretError" not in json.dumps(summary)
    assert m.failure_summary(m.LocalMetadataRefusal("REFUSED: local_original"))["contract_code"] == "local_original"
    assert m.failure_summary(m.LocalMetadataRefusal("REFUSED: local_original SECRET"))["contract_code"] is None


def test_mismatch_projects_field_names_only():
    original = (1, 2, 3, 4, 384, 1, 41, 9007199254740993001, 9007199254740993002)
    changed = (*original[:-1], original[-1] + 1)
    with pytest.raises(m.LocalMetadataRefusal) as caught:
        m._same(changed, original)
    assert m.failure_summary(caught.value)["mismatching_fields"] == ["ctime_ns"]
    assert str(original[-1]) not in json.dumps(m.failure_summary(caught.value))


@_POSIX_CAPTURE_ONLY
def test_final_read_compares_original_seal_and_keeps_authority_false(fabricated_local_profile, monkeypatch):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    monkeypatch.setattr(m, "_USED", False)
    result = m.final_read(HEAD, REMOTE, OPERATION, packets["producer_sealed"][1])
    assert result["authority"] == m.authority()
    assert result["status"].endswith("external_waits_still_required")


@_POSIX_CAPTURE_ONLY
def test_control_must_remain_empty_until_final_read_finishes(fabricated_local_profile, monkeypatch):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    (f.base / m.NAMESPACE / "control" / "not-yet-admitted.json").write_bytes(b"{}\n")
    monkeypatch.setattr(m, "_USED", False)
    with pytest.raises(m.LocalMetadataRefusal):
        m.final_read(HEAD, REMOTE, OPERATION, packets["producer_sealed"][1])


@_POSIX_CAPTURE_ONLY
def test_partial_creation_never_reports_false_zero(fabricated_local_profile, monkeypatch):
    f = fabricated_local_profile
    def fail_after_open(self, name, raw):
        fd = self.create(name)
        os.write(fd, raw[:1])
        raise OSError(errno.ENOSPC, "PRIVATE")
    monkeypatch.setattr(m.p._Files, "write", fail_after_open)
    with pytest.raises(OSError):
        m.producer(HEAD, REMOTE, OPERATION)
    value = f.emitted[-1][0]
    assert value["event"] == "producer_refused" and value["literal_publications"] is None
    assert value["creation_accounting"] == "unknown" and "PRIVATE" not in json.dumps(value)


@_POSIX_CAPTURE_ONLY
def test_single_invocation_never_retries_existing_namespace(fabricated_local_profile, monkeypatch):
    _run_producer(fabricated_local_profile, monkeypatch)
    with pytest.raises(m.LocalMetadataRefusal, match="local_latched"):
        m.producer(HEAD, REMOTE, OPERATION)


@pytest.mark.parametrize("boundary", ["publisher_close", "publisher_named", "code_close", "code_named", "scope_close", "scope_named"])
def test_each_producer_closure_failure_vetoes_positive(fabricated_local_profile, monkeypatch, boundary):
    f = fabricated_local_profile
    owner, method = {"publisher_close": (m.p._Files, "close"), "publisher_named": (m.p._Files, "named"),
        "code_close": (m._Code8, "close"), "code_named": (m._Code8, "named"),
        "scope_close": (m._Scope, "close"), "scope_named": (m._Scope, "named")}[boundary]
    original = getattr(owner, method)
    def fail(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise m.LocalMetadataRefusal("REFUSED: local_original")
    monkeypatch.setattr(owner, method, fail)
    with pytest.raises(m.LocalMetadataRefusal):
        _run_producer(f, monkeypatch)
    assert not any(value["event"] == "producer_closed" for value, raw in f.emitted)


@pytest.mark.parametrize("boundary", ["literal_close", "literal_named", "code_close", "code_named", "scope_close", "scope_named"])
@_POSIX_CAPTURE_ONLY
def test_each_observer_closure_failure_vetoes_positive(fabricated_local_profile, monkeypatch, boundary):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    _observer_input(f, packets, monkeypatch)
    owner, method = {"literal_close": (m._OriginalLiteral, "close"), "literal_named": (m._OriginalLiteral, "named"),
        "code_close": (m._Code8, "close"), "code_named": (m._Code8, "named"),
        "scope_close": (m._Scope, "close"), "scope_named": (m._Scope, "named")}[boundary]
    original = getattr(owner, method)
    def fail(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise m.LocalMetadataRefusal("REFUSED: local_original")
    monkeypatch.setattr(owner, method, fail)
    with pytest.raises(m.LocalMetadataRefusal):
        m.observer(HEAD, REMOTE, OPERATION)
    assert not any(value["event"] == "observer_closed" for value, raw in f.emitted)


@pytest.mark.parametrize("actor,boundary", [("producer", "literal_close"), ("producer", "code_close"),
    ("producer", "scope_close"), ("observer", "literal_close"), ("observer", "code_close"), ("observer", "scope_close")])
@_POSIX_CAPTURE_ONLY
def test_mutation_after_each_real_close_cannot_emit_positive(fabricated_local_profile, monkeypatch, actor, boundary):
    f = fabricated_local_profile
    packets = None
    if actor == "observer":
        packets = _run_producer(f, monkeypatch)
        _observer_input(f, packets, monkeypatch)
    owner = {"literal_close": m.p._Files if actor == "producer" else m._OriginalLiteral,
        "code_close": m._Code8, "scope_close": m._Scope}[boundary]
    original_close = owner.close
    def close_then_mutate(self):
        original_close(self)
        path = f.base / m.NAMESPACE / "data" / m.LITERAL_NAME
        if path.exists():
            info = f.actual_os.stat(path)
            f.flags[(info.st_dev, info.st_ino)] = 64
    monkeypatch.setattr(owner, "close", close_then_mutate)
    with pytest.raises((m.LocalMetadataRefusal, m.p.SupervisionRefusal)):
        m.observer(HEAD, REMOTE, OPERATION) if actor == "observer" else _run_producer(f, monkeypatch)
    assert not any(value["event"] == actor + "_closed" for value, raw in f.emitted)


@pytest.mark.parametrize("mutation", ["bytes", "mode", "replace"])
@_POSIX_CAPTURE_ONLY
def test_last_original_named_read_checks_after_its_own_FD_close(fabricated_local_profile, monkeypatch, mutation):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    monkeypatch.setattr(m, "_USED", False)
    scope = m._Scope(m._Clock(), create=False, originals=packets["producer_sealed"][0]["directory_pins"])
    literal = m._OriginalLiteral(scope, packets["producer_sealed"][0]["original9"], 2)
    literal.close()
    path = scope.path / "data" / m.LITERAL_NAME
    real_close = m.p._close
    def close_then_mutate(fd, primary=None):
        real_close(fd, primary)
        if mutation == "bytes":
            path.write_bytes(b"x" * len(m.LITERAL))
        elif mutation == "mode":
            path.chmod(0o640)
        else:
            path.unlink(); path.write_bytes(m.LITERAL); path.chmod(0o600)
    monkeypatch.setattr(m.p, "_close", close_then_mutate)
    try:
        with pytest.raises(m.LocalMetadataRefusal):
            literal.named()
        # Restoring content cannot unlatch the original failed object.
        with pytest.raises(m.LocalMetadataRefusal, match="local_latched"):
            literal.named()
    finally:
        scope.close()


@pytest.fixture
def fabricated_code8(tmp_path, monkeypatch):
    """Genuine new-code RO custody with fabricated Git/old-seven boundaries."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    path = root / m.DRIVER
    raw = b"# fabricated eighth file\n"
    path.write_bytes(raw)
    monkeypatch.setattr(m, "ROOT", root)
    monkeypatch.setattr(m.p, "_guard", lambda head, remote: None)
    monkeypatch.setattr(m.p, "_git", lambda args: raw)
    manifest = {name: m.SDK_SHA256 if name == m.p.DRIVER else "d" * 64 for name in m.p.CODE_FILES}
    class Old7:
        def __init__(self, head, remote, clock):
            self.closed = False
            self.manifest = manifest.copy()
        def audit(self):
            return manifest.copy()
        def close(self):
            self.closed = True
        def named(self):
            pass
    monkeypatch.setattr(m.p, "_Code7", Old7)
    return SimpleNamespace(path=path, raw=raw, manifest=manifest)


@_POSIX_CAPTURE_ONLY
def test_new_eighth_code_file_is_committed_and_original_RO(fabricated_code8):
    f = fabricated_code8
    code = m._Code8(HEAD, REMOTE, m._Clock())
    assert set(code.manifest) == set(m.CODE_FILES)
    assert code.manifest[m.DRIVER] == m.hash_bytes(f.raw)
    assert m.p._descriptor_access(code.fd) == os.O_RDONLY
    code.audit(); code.close(); code.named()
    assert code.old.closed


@pytest.mark.parametrize("mutation", ["new_bytes", "rename", "uncommitted_Git", "SDK_hash", "missing_old_code"])
@_POSIX_CAPTURE_ONLY
def test_code_byte_stamp_manifest_or_sdk_drift_permanently_refuses(fabricated_code8, monkeypatch, mutation):
    f = fabricated_code8
    code = m._Code8(HEAD, REMOTE, m._Clock())
    if mutation == "new_bytes":
        f.path.write_bytes(b"# changed\n")
    elif mutation == "rename":
        f.path.unlink(); f.path.write_bytes(f.raw)
    elif mutation == "uncommitted_Git":
        monkeypatch.setattr(m.p, "_git", lambda args: b"# other committed bytes\n")
    elif mutation == "SDK_hash":
        f.manifest[m.p.DRIVER] = "f" * 64
    else:
        f.manifest.pop(next(iter(f.manifest)))
    try:
        with pytest.raises(m.LocalMetadataRefusal):
            code.audit()
        with pytest.raises(m.LocalMetadataRefusal, match="local_latched"):
            code.audit()
    finally:
        code.close()


@pytest.mark.parametrize("mutation", ["head", "remote", "operation", "policy", "authority", "original_ns_bool", "flags_bool"])
@_POSIX_CAPTURE_ONLY
def test_handoff_cannot_override_original_binding_or_integer_schema(fabricated_local_profile, monkeypatch, mutation):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    value = json.loads(packets["producer_sealed"][1])
    if mutation == "head":
        value["runtime_head"] = "e" * 40
    elif mutation == "remote":
        value["actual_remote"] = "e" * 40
    elif mutation == "operation":
        value["operation"] = "e" * 64
    elif mutation == "policy":
        value["policy_sha256"] = "e" * 64
    elif mutation == "authority":
        value["authority"]["source_admitted"] = True
    elif mutation == "original_ns_bool":
        value["original9"][-1] = True
    else:
        value["flags"] = True
    packets["producer_sealed"] = value, (m.canonical_json(value) + "\n").encode()
    _observer_input(f, packets, monkeypatch)
    with pytest.raises(m.LocalMetadataRefusal):
        m.observer(HEAD, REMOTE, OPERATION)


@_POSIX_CAPTURE_ONLY
def test_partial_directory_creation_keeps_data_FD_in_cleanup(fabricated_local_profile, monkeypatch):
    f = fabricated_local_profile
    actual_open = f.proxy.open
    opened = []
    def fail_control(path, options, mode=0o777, *, dir_fd=None):
        if path == "control":
            raise OSError(errno.EIO, "PRIVATE")
        fd = actual_open(path, options, mode, dir_fd=dir_fd)
        opened.append(fd)
        return fd
    monkeypatch.setattr(f.proxy, "open", fail_control)
    with pytest.raises(OSError):
        m._Scope(m._Clock(), create=True)
    assert opened
    for fd in opened:
        with pytest.raises(OSError):
            f.actual_fstat(fd)


@_POSIX_CAPTURE_ONLY
def test_original_host_contract_checked_after_last_directory_context_close(fabricated_local_profile, monkeypatch):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    _observer_input(f, packets, monkeypatch)
    real_close = m._Scope.close
    real_native = m.p._native_statfs
    def close_then_ignore_ownership(self):
        real_close(self)
        monkeypatch.setattr(m.p, "_native_statfs", lambda fd: {**real_native(fd),
            "flags": m.p.native.MNT_LOCAL | m.p.native.MNT_IGNORE_OWNERSHIP})
    monkeypatch.setattr(m._Scope, "close", close_then_ignore_ownership)
    with pytest.raises(m.LocalMetadataRefusal, match="local_host"):
        m.observer(HEAD, REMOTE, OPERATION)
    assert not any(value["event"] == "observer_closed" for value, raw in f.emitted)


def _held_controller(f, packets):
    scope = m._Scope(m._Clock(), create=False, originals=packets["producer_sealed"][0]["directory_pins"])
    literal = m._OriginalLiteral(scope, packets["producer_sealed"][0]["original9"], 2)
    controls = scope.attach_control_publisher(literal)
    return scope, literal, controls


@_POSIX_CAPTURE_ONLY
def test_postexit_explicit_controller_uses_original_literal_and_own_roles(fabricated_local_profile, monkeypatch):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    scope, literal, controls = _held_controller(f, packets)
    raw = (m.canonical_json({"authority": m.authority(), "schema": "fabricated-controller-observation"}) + "\n").encode()
    controls.write("registration.private.json", raw)
    controls.write("producer.sealed.private.json", packets["producer_sealed"][1])
    controls.audit(); literal.audit()
    assert type(controls) is m.p._Files
    assert controls.roles == frozenset(m.CONTROL_ROLES)
    controls.close(); literal.named(); scope.check()
    literal.close(); scope.close(); scope.named(); controls.named(); literal.named()
    assert m.authority()["durable_Main_receipt"] is False


@_POSIX_CAPTURE_ONLY
def test_postexit_control_named_original_drift_after_control_handle_close_refuses(fabricated_local_profile, monkeypatch):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    scope, literal, controls = _held_controller(f, packets)
    controls.write("registration.private.json", b"{}\n")
    controls.close()
    path = scope.path / "control" / "registration.private.json"
    info = f.actual_os.stat(path)
    f.flags[(info.st_dev, info.st_ino)] = 64
    try:
        with pytest.raises((m.LocalMetadataRefusal, m.p.SupervisionRefusal)):
            literal.named()
    finally:
        literal.close(); scope.close()


@pytest.mark.parametrize("mutation", ["extra", "old_literal_flag", "control_flag", "control_bytes", "wrong_role"])
@_POSIX_CAPTURE_ONLY
def test_controller_phase_cannot_adopt_extra_old_drift_or_bad_roles(fabricated_local_profile, monkeypatch, mutation):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    scope, literal, controls = _held_controller(f, packets)
    controls.write("registration.private.json", b"{}\n")
    root = scope.path
    if mutation == "extra":
        (root / "control" / "extra").write_bytes(b"x")
    elif mutation == "old_literal_flag":
        info = f.actual_os.stat(root / "data" / m.LITERAL_NAME)
        f.flags[(info.st_dev, info.st_ino)] = 64
    elif mutation == "control_flag":
        info = f.actual_os.stat(root / "control" / "registration.private.json")
        f.flags[(info.st_dev, info.st_ino)] = 64
    elif mutation == "control_bytes":
        (root / "control" / "registration.private.json").write_bytes(b"[]\n")
    try:
        with pytest.raises((m.LocalMetadataRefusal, m.p.SupervisionRefusal)):
            controls.write("unregistered.json", b"{}\n") if mutation == "wrong_role" else controls.audit()
    finally:
        literal.close(); controls.close(); scope.close()


@_POSIX_CAPTURE_ONLY
def test_controller_cannot_attach_to_fresh_unbound_scope_or_other_literal(fabricated_local_profile):
    scope = m._Scope(m._Clock(), create=True)
    try:
        with pytest.raises(m.LocalMetadataRefusal, match="local_arguments"):
            scope.attach_control_publisher(object())
    finally:
        scope.close()


@_POSIX_CAPTURE_ONLY
def test_per_role_wire_and_unchanged_publisher_control_size_bounds(fabricated_local_profile, monkeypatch):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    scope, literal, controls = _held_controller(f, packets)
    try:
        with pytest.raises(m.p.SupervisionRefusal, match="native_proof_write"):
            controls.write("registration.private.json", b"x" * 4097)
    finally:
        literal.close(); controls.close(); scope.close()
    assert m.MAXIMUM_WIRE == 4096 and m.MAXIMUM_CONTROL_BYTES == 65536


@pytest.mark.parametrize("key,alias", [("source_admitted", 0), ("source_STARTs", False),
    ("provider_HTTP", False), ("location_metadata_observation_only", 1)])
def test_authority_binding_rejects_boolean_integer_aliases(key, alias):
    binding = m._binding(HEAD, REMOTE, OPERATION)
    value = {**binding, "event": "observer_open", "pid": 1102, "producer_raw_sha256": "d" * 64}
    value["authority"] = {**value["authority"], key: alias}
    raw = (m.canonical_json(value) + "\n").encode()
    with pytest.raises(m.LocalMetadataRefusal, match="local_handshake"):
        m._packet(raw, binding, "observer_open", ("pid", "producer_raw_sha256"))


@pytest.mark.parametrize("field,alias", [("pid", True), ("flags", True), ("original9", True), ("literal_bytes", True)])
@_POSIX_CAPTURE_ONLY
def test_original_packet_fields_refuse_boolean_aliases(field, alias):
    value = {"pid": 1, "original9": [1, 2, os.getuid(), os.getgid(), 384, 1, 41, 9, 10], "flags": 3, "literal_bytes": 41}
    if field == "original9":
        value[field][0] = alias
    else:
        value[field] = alias
    with pytest.raises(m.LocalMetadataRefusal, match="local_handshake"):
        m._original_packet_fields(value)


@pytest.mark.parametrize("actor", ["producer", "observer"])
@_POSIX_CAPTURE_ONLY
def test_source_context_exit_after_terminal_packet_still_refuses(fabricated_local_profile, monkeypatch, actor):
    f = fabricated_local_profile
    if actor == "observer":
        packets = _run_producer(f, monkeypatch)
        _observer_input(f, packets, monkeypatch)
    @contextmanager
    def source_exit_failure():
        yield
        raise m.LocalMetadataRefusal("REFUSED: local_original")
    monkeypatch.setattr(m.p, "_source_denied", source_exit_failure)
    with pytest.raises(m.LocalMetadataRefusal):
        m.observer(HEAD, REMOTE, OPERATION) if actor == "observer" else _run_producer(f, monkeypatch)
    events = [value["event"] for value, raw in f.emitted]
    assert actor + "_closed" in events and events[-1] == actor + "_refused"


@_POSIX_CAPTURE_ONLY
def test_final_read_does_not_accept_untyped_pid_claim(fabricated_local_profile, monkeypatch):
    f = fabricated_local_profile
    packets = _run_producer(f, monkeypatch)
    value = json.loads(packets["producer_sealed"][1])
    value["pid"] = True
    monkeypatch.setattr(m, "_USED", False)
    with pytest.raises(m.LocalMetadataRefusal, match="local_handshake"):
        m.final_read(HEAD, REMOTE, OPERATION, (m.canonical_json(value) + "\n").encode())


def test_retirement_keeps_original_local_metadata_sdk_pin_frozen():
    original_sdk = "e477f8921c71410c36aa8c4b23e9c76f46aa68286b62bf2991882832b7a73237"
    assert m.SDK_SHA256 == original_sdk
    assert m.policy()["SDK_sha256"] == original_sdk


@pytest.mark.parametrize("actor", ["producer", "observer"])
@_POSIX_CAPTURE_ONLY
def test_retirement_changed_sdk_refuses_before_namespace_or_publication(tmp_path, monkeypatch, actor):
    """Only fabricated code custody reaches the old pin; no old namespace is opened."""
    original_sdk = "e477f8921c71410c36aa8c4b23e9c76f46aa68286b62bf2991882832b7a73237"
    assert m.SDK_SHA256 == original_sdk
    eighth = tmp_path / m.DRIVER
    eighth.parent.mkdir(mode=0o700)
    eighth_raw = b"FABRICATED eighth code bytes; no source or namespace data\n"
    eighth.write_bytes(eighth_raw)
    events, holders, git_reads, namespace_accesses, handshakes, publications, closed = [], [], [], [], [], [], []

    class ChangedSdkCode7:
        def __init__(self, head, remote, clock):
            assert (head, remote) == (HEAD, REMOTE)
            self.manifest = {path: "d" * 64 for path in m.p.CODE_FILES}
            self.manifest[m.p.DRIVER] = "f" * 64
            assert self.manifest[m.p.DRIVER] != original_sdk
            self.closed = False
            holders.append(self)

        def named(self):
            events.append("original_seven_named")

        def close(self):
            self.closed = True
            events.append("original_seven_closed")

    def fabricated_git(arguments):
        assert arguments == ["show", HEAD + ":" + m.DRIVER]
        git_reads.append(tuple(arguments))
        return eighth_raw

    def forbidden_namespace(*args, **kwargs):
        namespace_accesses.append((args, kwargs))
        raise AssertionError("Retired local SDK reached a namespace")

    def forbidden_handshake(*args, **kwargs):
        handshakes.append((args, kwargs))
        raise AssertionError("Retired local SDK reached a handshake")

    original_close = m.p._close

    def observed_close(fd):
        closed.append(fd)
        return original_close(fd)

    # These explicit fixture seams concern only code identity. The real old
    # _Code8 pin, entrypoint ordering and its temporary eighth-file FD remain.
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(m, "registered", lambda: None)
    monkeypatch.setattr(m.p, "_Code7", ChangedSdkCode7)
    monkeypatch.setattr(m.p, "_guard", lambda head, remote: events.append("lane_guard"))
    monkeypatch.setattr(m.p, "_git", fabricated_git)
    monkeypatch.setattr(m.p, "_close", observed_close)
    monkeypatch.setattr(m, "_Scope", forbidden_namespace)
    monkeypatch.setattr(m, "_Lines", forbidden_handshake)
    monkeypatch.setattr(m, "_emit", lambda *args, **kwargs: publications.append((args, kwargs)))

    with pytest.raises(m.LocalMetadataRefusal, match="local_code"):
        getattr(m, actor)(HEAD, REMOTE, OPERATION)

    assert len(holders) == 1 and holders[0].closed
    assert "original_seven_named" in events and "original_seven_closed" in events
    assert git_reads == namespace_accesses == handshakes == publications == []
    assert m.SDK_SHA256 == original_sdk and m._USED is True
    assert len(closed) == 1
    with pytest.raises(OSError) as caught:
        os.fstat(closed[0])
    assert caught.value.errno == errno.EBADF
