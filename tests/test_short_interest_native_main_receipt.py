"""Source-free fabricated Root→Main custody tests; no actual native job.

The named kernel/profile/original-reader boundaries use ordinary temporary
inodes and real raw pipes. They are not APFS, launchd, source or OS proof.
Unchanged original _Files creation/freeze/RO transfer code executes throughout.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_native_main_receipt as m

p = m.p
HEAD, REMOTE, OPERATION = "a" * 40, "b" * 40, "c" * 32


@pytest.fixture(autouse=True)
def no_actual_external_operations(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Actual native/source/credential operation forbidden")
    for name in ("_native_command", "_launch_worker", "_launch_service", "_platform", "_native_statfs", "_device_node", "_guard"):
        monkeypatch.setattr(p, name, denied)
    for name in ("_CHILDREN", "_WAITS", "_OBSERVED", "_AUTHENTICATED"):
        monkeypatch.setattr(m, name, {})
    for name in ("_OBSERVED_FAILED", "_AUTHENTICATED_FAILED"): monkeypatch.setattr(m, name, set())
    monkeypatch.setattr(m, "_HELD", []); monkeypatch.setattr(m, "_USED", False)
    for name in ("_FILE_CREATORS", "_RO_ORIGINS", "_RO_HANDOFFS"):
        monkeypatch.setattr(p, name, {})
    class HoldObserved(BaseException): pass
    holds = []
    def hold(state):
        holds.append(state); m._HELD.append(state); raise HoldObserved()
    monkeypatch.setattr(m, "_hold", hold)
    yield SimpleNamespace(holds=holds, HoldObserved=HoldObserved)
    # Explicit test-only descriptor drain of fabricated states; production has
    # no corresponding recovery/disposal route and never resets old evidence.
    for state in holds:
        for name in ("publication", "root_file", "reader", "config", "main_directory", "root_directory", "directory", "config_directory", "code"):
            value = state.get(name)
            if value is not None:
                try: value.close()
                except BaseException: pass


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    """Named fabricated immutable flags; real original publication and RO FDs."""
    flags, offsets, events, directories, directory_paths, links = {}, {}, [], [], {}, {}
    actual_fstat, actual_stat, actual_lstat = os.fstat, os.stat, os.lstat
    def overlay(info):
        key = info.st_dev, info.st_ino
        result = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
        result["st_flags"] = flags.get(key, getattr(info, "st_flags", 0))
        result["st_ctime_ns"] += offsets.get(key, 0)
        # Named APFS all-entry-nlink seam. Ordinary POSIX temporary-directory
        # nlink semantics are not evidence of this fixed Darwin/APFS profile.
        if key in directory_paths:
            result["st_nlink"] = links[key] + len(os.listdir(directory_paths[key]))
        return SimpleNamespace(**result)
    monkeypatch.setattr(os, "fstat", lambda fd: overlay(actual_fstat(fd)))
    monkeypatch.setattr(os, "stat", lambda path, *args, **kw: overlay(actual_stat(path, *args, **kw)))
    monkeypatch.setattr(os, "lstat", lambda path, *args, **kw: overlay(actual_lstat(path, *args, **kw)))
    def set_flags(fd, value):
        info = actual_fstat(fd); key = info.st_dev, info.st_ino
        assert type(value) is int and value == flags.get(key, getattr(info, "st_flags", 0)) | p.UF_IMMUTABLE
        flags[key] = value; offsets[key] = offsets.get(key, 0) + 1; events.append((key, value))
    monkeypatch.setattr(p, "_set_file_flags", set_flags)
    class Directory:
        """Explicit temporary-host ancestry seam, not a real local profile."""
        def __init__(self, kind, *, create=False, profile=None):
            assert create is False and profile is p.LOCAL_MAIN_V1
            self.path = tmp_path / kind; self.path.mkdir(mode=0o700, exist_ok=True)
            self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.parent = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            native = actual_fstat(self.fd); key = native.st_dev, native.st_ino
            if key not in directory_paths: directory_paths[key] = self.path; links[key] = native.st_nlink
            self.initial5 = p._stamp(os.fstat(self.fd))[:5]; self.closed = False
            p._bind_profile(self, profile); directories.append(self)
        def check(self):
            assert not self.closed
            assert p._stamp(self.path.lstat())[:5] == p._stamp(os.fstat(self.fd))[:5] == self.initial5
        def named(self): assert p._stamp(self.path.lstat())[:5] == self.initial5
        def close(self):
            if not self.closed:
                os.close(self.fd); os.close(self.parent); self.closed = True
    monkeypatch.setattr(p, "_Directory", Directory)
    clock = SimpleNamespace(check=lambda: 290.0)
    def publication(kind="root-export", name=m.ROOT_PROJECTION, raw=b'{"fixed":"fabricated"}'):
        directory = Directory(kind, profile=p.LOCAL_MAIN_V1)
        initial = p._stamp(os.fstat(directory.fd))
        value = m._Publication(directory, initial, clock, name); value.write(raw)
        return value, directory
    try: yield SimpleNamespace(root=tmp_path, flags=flags, offsets=offsets, events=events,
        directories=directories, links=links, clock=clock, publication=publication)
    finally:
        for directory in directories: directory.close()


@pytest.fixture
def process_boundary(monkeypatch):
    """Real raw pipes and original _launch_root/owned wait; no process launched."""
    processes = []
    class Child:
        status, wait_error, on_ack, initial_stdout, initial_stderr = 0, None, None, b"", b""
        write_error, poll_override, on_wait = None, None, None
        def __init__(self, arguments, **kwargs):
            assert kwargs["shell"] is False and kwargs["close_fds"] is True
            self.args, self.pid, self.waits, self.acks = arguments, 7654, [], []
            ro, self.wo = os.pipe(); re, self.we = os.pipe()
            self.stdout, self.stderr = os.fdopen(ro, "rb", buffering=0), os.fdopen(re, "rb", buffering=0)
            child = self
            class Input:
                closed = False
                def write(self, raw):
                    if child.write_error is not None: raise child.write_error
                    child.acks.append(raw); return len(raw)
                def flush(self): pass
                def close(self):
                    if not self.closed:
                        self.closed = True
                        if child.on_ack is not None: child.on_ack(child)
            self.stdin = Input(); processes.append(self)
            if self.initial_stdout: os.write(self.wo, self.initial_stdout)
            if self.initial_stderr: os.write(self.we, self.initial_stderr)
        def finish_writes(self):
            for name in ("wo", "we"):
                fd = getattr(self, name)
                if fd is not None: os.close(fd); setattr(self, name, None)
        def wait(self, *, timeout):
            self.waits.append(timeout)
            if self.wait_error is not None: raise self.wait_error
            if self.on_wait is not None: self.on_wait()
            return self.status
        def poll(self): return self.poll_override if self.poll_override is not None else self.status if self.wo is None and self.we is None else None
    monkeypatch.setattr(m.subprocess, "Popen", Child)
    try: yield SimpleNamespace(Child=Child, processes=processes)
    finally:
        for child in processes:
            child.finish_writes(); child.stdout.close(); child.stderr.close()


def test_policy_freeze_exact_eight_source_closure_and_no_source_authority():
    m.registered()
    assert len(m.code_paths()) == len(set(m.code_paths())) == 8
    assert hash_payload(m.policy()) == m.PROTOCOL_SHA256
    assert m.authority()["durable_custody_observation_only"] is True
    assert all(value is False or type(value) is int and value == 0
        for key, value in m.authority().items() if key != "durable_custody_observation_only")
    assert p.policy(p.LOCAL_MAIN_V1)["Main_receipt"] != "durable_writing_unavailable"


@pytest.mark.parametrize("raw", [b'{"x":1,"x":1}', b'{"x":NaN}', b'{"x":1.0}', b'{ "x":1}', b'{"x":1}\n', b'[]', b'{}\n\n'])
def test_strict_canonical_no_boolean_alias_or_duplicate_json(raw):
    with pytest.raises(m.NativeMainReceiptRefusal): m._json(raw)


def test_strict_types_and_large_native_timestamps():
    assert m._exact({"x": 0}, {"x": False}) is False
    assert m._stamp([1, 2, 3, 4, 384, 1, 9, 1762000000000000001, 1762000000000000002])[-1] == 1762000000000000002
    with pytest.raises(m.NativeMainReceiptRefusal): m._stamp([True] * 9)
    with pytest.raises(m.NativeMainReceiptRefusal): m._flags(True)
    with pytest.raises(m.NativeMainReceiptRefusal): m._flags(0)


def test_pending_anchor_refuses_before_private_or_code_open(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "ROOT", tmp_path); monkeypatch.setattr(m, "registered", lambda: None)
    monkeypatch.setattr(p, "_guard", lambda *args: None)
    def denied(*args, **kwargs): raise AssertionError("private/code read before pending anchor refusal")
    monkeypatch.setattr(p, "_Code7", denied); monkeypatch.setattr(m, "_directory", denied)
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_anchor_pending"):
        with m.load_registered(HEAD, REMOTE): pytest.fail("pending receipt yielded")


def test_raw_reader_drains_two_coalesced_lines_without_textio_buffer_loss():
    r, w = os.pipe(); os.write(w, b'{"n":1762000000000000001}\n{"n":2}\n'); os.close(w)
    value = m._Lines(r, SimpleNamespace(check=lambda: 1))
    try:
        assert m._json(value.read(), wire=True)["n"] == 1762000000000000001
        assert value.read() == b'{"n":2}\n'; value.finish()
    finally: os.close(r)


@pytest.mark.parametrize("raw", [b"missing-newline", b"x" * 4096 + b"\n", b"{}\nextra"])
def test_raw_reader_refuses_incomplete_overlong_or_extra_after_ack(raw):
    r, w = os.pipe(); os.write(w, raw); os.close(w)
    value = m._Lines(r, SimpleNamespace(check=lambda: 1))
    try:
        with pytest.raises(m.NativeMainReceiptRefusal): value.read(); value.finish()
        with pytest.raises(m.NativeMainReceiptRefusal, match="main_latched"): value.read()
    finally: os.close(r)


def test_clock_permanently_latches_regression_and_late_deadline(monkeypatch):
    ticks = iter([5.0, 5.0, 305.001, 6.0]); monkeypatch.setattr(m.time, "monotonic", lambda: next(ticks))
    clock = m._Deadline()
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_deadline"): clock.check()
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_latched"): clock.check()


def test_original_publication_ro_handoff_and_original_descriptor_held(kernel):
    value, directory = kernel.publication(); descriptor = value.descriptor()
    assert value.initial != tuple(descriptor["directory_native_full9"])
    assert type(value.files) is p._Files and kernel.events
    assert p._descriptor_access(value.files.originals[m.ROOT_PROJECTION][0]) == os.O_RDONLY
    held = m._HeldArtifact(directory, descriptor, m.ROOT_PROJECTION, kernel.clock)
    descriptor["native_full9"][8] += 1
    assert held.raw == b'{"fixed":"fabricated"}'
    held.audit(); value.close(); value.named(); held.audit(); held.close(); held.named()


@pytest.mark.parametrize("mutation", ["ctime", "flags", "bytes", "mode", "hardlink", "rename", "extra", "directory", "nlink"])
def test_original_metadata_drift_never_reseals_or_rebaselines(kernel, mutation):
    value, directory = kernel.publication(); descriptor = value.descriptor()
    held = m._HeldArtifact(directory, descriptor, m.ROOT_PROJECTION, kernel.clock)
    path = directory.path / m.ROOT_PROJECTION; info = path.lstat(); key = info.st_dev, info.st_ino
    if mutation == "ctime": kernel.offsets[key] += 1
    elif mutation == "flags": kernel.flags[key] = 0
    elif mutation == "bytes": path.write_bytes(b'{"fixed":"fabricated!"}')
    elif mutation == "mode": path.chmod(0o640)
    elif mutation == "hardlink": os.link(path, directory.path / "other")
    elif mutation == "rename": path.rename(directory.path / "other")
    elif mutation == "extra": (directory.path / "other").write_bytes(b"extra")
    elif mutation == "directory": os.utime(directory.path, None)
    elif mutation == "nlink":
        info = directory.path.lstat(); kernel.links[(info.st_dev, info.st_ino)] += 1
    with pytest.raises((m.NativeMainReceiptRefusal, p.SupervisionRefusal)): held.audit()
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_latched"): held.audit()
    held.close(); value.close()


def test_postclose_original_metadata_drift_is_still_negative(kernel):
    value, directory = kernel.publication(); held = m._HeldArtifact(directory, value.descriptor(), m.ROOT_PROJECTION, kernel.clock)
    value.close(); held.close(); key = tuple((directory.path / m.ROOT_PROJECTION).lstat().__dict__[name] for name in ("st_dev", "st_ino"))
    kernel.offsets[key] += 1
    with pytest.raises(m.NativeMainReceiptRefusal): held.named()


def test_original_owned_root_wait_requires_both_raw_eof_and_actual_zero(process_boundary):
    Child = process_boundary.Child; Child.initial_stdout = b'{"one":1}\n{"two":2}\n'
    child = m._launch_root(HEAD, REMOTE, OPERATION); child.finish_writes()
    pump = m._Pump(child, SimpleNamespace(check=lambda: 2))
    assert pump.read() == b'{"one":1}\n'; assert pump.read() == b'{"two":2}\n'
    with pytest.raises(m.NativeMainReceiptRefusal): m._wait(child, pump)
    pump.finish(); row = m._wait(child, pump)
    assert type(row[1]) is int and row[1] == 0 and len(child.waits) == 1
    assert row[2] == hash_bytes(b'{"one":1}\n{"two":2}\n')


@pytest.mark.parametrize("copy_kind", ["origin", "wait", "wait_and_stdout"])
def test_original_launch_and_wait_tuple_identity_cannot_be_copied_or_rebaselined(process_boundary, copy_kind):
    child = m._launch_root(HEAD, REMOTE, OPERATION); child.finish_writes()
    pump = m._Pump(child, SimpleNamespace(check=lambda: 1)); pump.finish()
    if copy_kind == "origin":
        m._CHILDREN[child] = tuple(list(m._CHILDREN[child]))
    else:
        row = list(m._WAITS[child])
        if copy_kind == "wait_and_stdout":
            pump.stdout.extend(b"new caller baseline"); row[2] = hash_bytes(bytes(pump.stdout))
        m._WAITS[child] = tuple(row)
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_factory"): m._wait(child, pump)


@pytest.mark.parametrize("status", [True, False, 1, -9, None])
def test_nonzero_unknown_and_boolean_root_wait_cannot_issue_receipt(process_boundary, status):
    process_boundary.Child.status = status
    child = m._launch_root(HEAD, REMOTE, OPERATION); child.finish_writes(); pump = m._Pump(child, SimpleNamespace(check=lambda: 1))
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_exit"): pump.finish()
    assert child not in m._WAITS


def test_wait_failure_and_late_clock_are_not_a_success(process_boundary):
    child = m._launch_root(HEAD, REMOTE, OPERATION); child.finish_writes()
    child.wait_error = subprocess.TimeoutExpired("fabricated-controlled-command", 1)
    pump = m._Pump(child, SimpleNamespace(check=lambda: 1))
    with pytest.raises(subprocess.TimeoutExpired): pump.finish()
    assert child not in m._WAITS


def test_original_deadline_is_rechecked_after_actual_zero_wait(process_boundary):
    state = {"late": False}
    def check():
        m.require(not state["late"], "main_deadline"); return 1
    process_boundary.Child.on_wait = staticmethod(lambda: state.update(late=True))
    child = m._launch_root(HEAD, REMOTE, OPERATION); child.finish_writes(); pump = m._Pump(child, SimpleNamespace(check=check))
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_deadline"): pump.finish()
    assert child not in m._WAITS and len(child.waits) == 1


@pytest.mark.parametrize("problem", ["stderr", "extra_stdout", "overlong", "args", "forged_wait"])
def test_pipe_negative_bytes_and_forged_launch_wait_are_rejected(process_boundary, problem):
    Child = process_boundary.Child
    if problem == "stderr": Child.initial_stderr = b"sensitive dynamic text must never become diagnostics"
    elif problem == "extra_stdout": Child.initial_stdout = b"extra"
    elif problem == "overlong": Child.initial_stdout = b"x" * 4096
    child = m._launch_root(HEAD, REMOTE, OPERATION); child.finish_writes()
    if problem == "args":
        child.args = ["forged"]
        with pytest.raises(m.NativeMainReceiptRefusal): m._Pump(child, SimpleNamespace(check=lambda: 1))
        return
    pump = m._Pump(child, SimpleNamespace(check=lambda: 1))
    if problem == "forged_wait":
        m._WAITS[child] = (m._origin(child), 0, hash_bytes(b""), hash_bytes(b""), None, object())
        with pytest.raises((m.NativeMainReceiptRefusal, AttributeError)): m._wait(child, pump)
    else:
        with pytest.raises(m.NativeMainReceiptRefusal): pump.finish() if problem == "extra_stdout" else pump.read()
    if problem == "stderr": assert pump.stderr and pump.blocks


def test_failure_diagnostics_never_emit_exception_text_or_dynamic_type():
    secret = "SECRET /private/path dynamic actor"
    error = RuntimeError(secret); result = m.failure_summary(error)
    assert secret not in canonical_json(result) and "RuntimeError" not in canonical_json(result)
    assert m.failure_summary(m.NativeMainReceiptRefusal("REFUSED: main_bytes"))["contract_code"] == "main_bytes"


def _fabricated_body(kernel, manifest):
    def native9(size): return [1, 2, os.getuid(), os.getgid(), 384, 1, size, 1762000000000000001, 1762000000000000002]
    dirs = {name: m._directory(name) for name in ("root-export", "main-receipt")}
    return {"schema": "si-native-root-closure-projection-v1", "storage_profile": "local-main-v1",
        "runtime_head": HEAD, "actual_remote": REMOTE, "policy_sha256": p._policy_sha(p.LOCAL_MAIN_V1),
        "spec_sha256": "1" * 64, "nonce": "2" * 32, "producer_pid": 4321,
        "actual_kernel_exit": 0, "actual_child_exit": 0,
        "marker": {"sha256": "3" * 64, "native_full9": native9(500), "original_flags": 2},
        "inventory": {"sha256": "4" * 64, "native_full9": native9(1000), "original_flags": 2, "bytes": 1000},
        "code_manifest_sha256": hash_payload(manifest), "native_inventory_sha256": "5" * 64,
        "config_identity7_sha256": "6" * 64, "load_window9_sha256": "7" * 64,
        "root_context_snapshot_sha256": "8" * 64,
        "host_directory_originals": {name: list(p._stamp(os.fstat(value.fd))) for name, value in dirs.items()},
        "authority": p.authority()}


@pytest.mark.parametrize("drift", [None, "sha256", "native_full9", "original_flags", "bytes", "boolean_flags"])
def test_projection_inventory_reference_matches_authenticated_original_marker(kernel, monkeypatch, drift):
    manifest = {name: hash_bytes(name.encode()) for name in m.code_paths()}
    body = _fabricated_body(kernel, manifest); native = {"EXPLICIT_FABRICATED_NATIVE": True}
    body["native_inventory_sha256"] = hash_payload(native)
    original = dict(body["inventory"]); instances = []
    class OriginalReader:
        def __init__(self, head, remote, spec, observer, pid, marker, *, profile):
            assert head == HEAD and remote == REMOTE and profile is p.LOCAL_MAIN_V1
            assert marker["stamp"] is body["marker"]["native_full9"]
            self.inventory, self.native, self.closed = {"code_manifest": manifest}, native, False
            self.marker = {"inventory_sha256": original["sha256"], "inventory_original_stamp": original["native_full9"],
                "inventory_original_flags": original["original_flags"], "inventory_bytes": original["bytes"]}
            instances.append(self)
        def audit(self): pass
        def current_association(self, clock): clock.check()
        def close(self): self.closed = True
    monkeypatch.setattr(p, "_OriginalRead", OriginalReader)
    if drift == "sha256": body["inventory"][drift] = "9" * 64
    elif drift == "native_full9": body["inventory"][drift] = [*body["inventory"][drift][:-1], 9]
    elif drift == "original_flags": body["inventory"][drift] = 6
    elif drift == "bytes": body["inventory"][drift] += 1
    elif drift == "boolean_flags": body["inventory"]["original_flags"] = True
    if drift:
        with pytest.raises(m.NativeMainReceiptRefusal, match="main_original"):
            m._originals(HEAD, REMOTE, body, SimpleNamespace(manifest=manifest), kernel.clock)
        assert instances[0].closed
    else:
        assert m._originals(HEAD, REMOTE, body, SimpleNamespace(manifest=manifest), kernel.clock) is instances[0]
        instances[0].close()


@pytest.fixture
def composition(kernel, process_boundary, monkeypatch):
    """Explicit Root projection/native-config seams; whole Main path is real."""
    manifest = {name: hash_bytes(("FABRICATED " + name).encode()) for name in m.code_paths()}
    class Code:
        def __init__(self): self.manifest, self.closed, self.fail_close = manifest, False, False
        def audit(self): assert not self.closed
        def close(self):
            self.closed = True
            if self.fail_close: raise m.NativeMainReceiptRefusal("REFUSED: main_code")
        def named(self): pass
    class Source:
        def __init__(self): self.closed = False
        def audit(self, named=False): assert named or not self.closed
        def current_association(self, clock): clock.check()
        def close(self): self.closed = True
        def named(self): pass
    code = Code(); clock = kernel.clock
    binding = m._binding(HEAD, REMOTE, OPERATION); body = _fabricated_body(kernel, manifest)
    pub, root_dir = kernel.publication(raw=canonical_json(body).encode()); descriptor = pub.descriptor()
    monkeypatch.setattr(m, "_entry", lambda *args: (clock, binding, code))
    sources, configs = [], []
    def originals(*args): value = Source(); sources.append(value); return value
    def config(*args): value = Source(); configs.append(value); return m._directory("bootstrap"), value
    monkeypatch.setattr(m, "_originals", originals); monkeypatch.setattr(m, "_config", config)
    Child = process_boundary.Child
    ready = {**binding, "event": "projection_ready", "root_pid": 7654, "projection": descriptor}
    Child.initial_stdout = (canonical_json(ready) + "\n").encode()
    def on_ack(child):
        assert len(child.acks) == 1 and m._json(child.acks[0], wire=True)["event"] == "main_original_projection_open"
        # Original projection has been opened RO before Root publisher closes.
        pub.audit(); pub.close(); pub.named()
        os.write(child.wo, (canonical_json({**ready, "event": "projection_closed"}) + "\n").encode())
        child.finish_writes()
    Child.on_ack = staticmethod(on_ack)
    yield SimpleNamespace(kernel=kernel, Child=Child, Code=Code, code=code, clock=clock, body=body,
        pub=pub, root_dir=root_dir, descriptor=descriptor, sources=sources, configs=configs)
    pub.close()


def test_full_main_handoff_actual_owned_wait_and_original_counterreceipt(composition, process_boundary):
    value = m.coordinate_registered(HEAD, REMOTE, OPERATION); summary = value.public_summary()
    child = process_boundary.processes[0]
    assert len(child.waits) == 1 and child.acks
    assert summary["actual_root_exit"] == 0 and summary["authority"] == m.authority()
    assert summary["status"] == "closed_candidate_requires_outer_actual_exit_and_committed_anchor"
    raw = (composition.kernel.root / "main-receipt" / m.MAIN_RECEIPT).read_bytes(); body = m._json(raw)
    assert body["actual_root_exit"] == 0 and body["root_projection"] == composition.descriptor
    assert summary["receipt_sha256"] == hash_bytes(raw)
    assert type(summary["receipt_native_full9_json"]) is str
    assert hash_payload(json.loads(summary["receipt_native_full9_json"])) == summary["receipt_native_full9_sha256"]
    assert len(raw) <= 4096 and composition.sources[0].closed and composition.code.closed


def test_main_observation_copied_factory_frame_and_restored_bytes_do_not_undo_failure(composition):
    value = m.coordinate_registered(HEAD, REMOTE, OPERATION); row = m._OBSERVED[id(value)]
    forged = object.__new__(m.MainReceiptObservation)
    copy = (forged, *row[1:]); forged._anchor = copy; m._OBSERVED[id(forged)] = copy
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_factory"): forged.public_summary()
    pump = row[3]; original = bytes(pump.stdout); pump.stdout.extend(b"drift")
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_factory"): value.public_summary()
    pump.stdout[:] = original
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_latched"): value.public_summary()


def test_final_code_close_failure_vetoes_main_observation_and_retains_evidence(composition, no_actual_external_operations):
    composition.code.fail_close = True
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_code"):
        m.coordinate_registered(HEAD, REMOTE, OPERATION)
    assert not m._OBSERVED
    # Counterreceipt may exist provisionally; no outer successful completion
    # or committed independent anchor exists and no loader admits it.
    assert (composition.kernel.root / "main-receipt" / m.MAIN_RECEIPT).exists()


def test_missing_closed_frame_can_never_publish_main_receipt(composition, process_boundary, no_actual_external_operations):
    def no_closed(child): child.finish_writes()
    composition.Child.on_ack = staticmethod(no_closed)
    with pytest.raises(no_actual_external_operations.HoldObserved): m.coordinate_registered(HEAD, REMOTE, OPERATION)
    assert not m._OBSERVED and not (composition.kernel.root / "main-receipt" / m.MAIN_RECEIPT).exists()
    assert no_actual_external_operations.holds[0]["root_file"].fd is not None


def test_epipe_before_owned_wait_retains_original_fds_and_raw_bytes_even_if_poll_claims_zero(composition,
        process_boundary, no_actual_external_operations):
    process_boundary.Child.poll_override = 0  # Insufficient caller-poll seam.
    process_boundary.Child.write_error = BrokenPipeError(32, "SECRET must never be printed")
    with pytest.raises(no_actual_external_operations.HoldObserved): m.coordinate_registered(HEAD, REMOTE, OPERATION)
    state = no_actual_external_operations.holds[0]
    assert state["root_file"].fd is not None and state["pump"].stdout and not m._WAITS
    assert not (composition.kernel.root / "main-receipt" / m.MAIN_RECEIPT).exists()


def test_public_factories_reject_json_and_constructor_flags():
    for cls in (m.MainReceiptObservation, m.AuthenticatedDurableMainReceipt):
        with pytest.raises(m.NativeMainReceiptRefusal, match="main_factory"): cls()
        forged = object.__new__(cls)
        with pytest.raises(m.NativeMainReceiptRefusal, match="main_factory"): forged.public_summary()


def test_strict_anchor_rejects_boolean_wait_and_overbudget_elapsed(monkeypatch):
    anchor = {"schema": "si-native-main-committed-anchor-v1", "runtime_head": HEAD,
        "native_policy_sha256": p._policy_sha(p.LOCAL_MAIN_V1), "protocol_sha256": m.PROTOCOL_SHA256,
        "receipt_sha256": "1" * 64, "receipt_native_full9_sha256": "2" * 64,
        "receipt_directory_full9_sha256": "3" * 64, "receipt_original_flags": 2,
        "projection_sha256": "4" * 64, "projection_native_full9_sha256": "5" * 64,
        "outer_stdout_sha256": "6" * 64, "outer_actual_exit": 0, "outer_stderr_bytes": 0, "outer_elapsed_ns": 1000}
    monkeypatch.setattr(m.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    assert m._anchor_value(anchor, HEAD) is anchor
    for key, value in (("outer_actual_exit", False), ("outer_stderr_bytes", False),
                       ("outer_elapsed_ns", 300000000001), ("receipt_original_flags", True)):
        with pytest.raises(m.NativeMainReceiptRefusal): m._anchor_value({**anchor, key: value}, HEAD)


def test_caller_fabricated_registry_row_is_not_an_authenticated_factory_receipt(monkeypatch):
    class Held(m._Latched):
        def __init__(self): super().__init__(); self.closed = False
        def validate(self): return self._run(lambda: m.require(not self.closed, "main_closed"))
    held = Held(); value = object.__new__(m.AuthenticatedDurableMainReceipt)
    row = value, canonical_json({"authority": m.authority()}), held
    value._anchor = row; m._AUTHENTICATED[id(value)] = row
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_factory"): value.public_summary()


@pytest.mark.parametrize("late_error", [False, True])
def test_root_exports_ready_then_same_original_closed_only_after_ack_and_all_exits(kernel, monkeypatch,
        no_actual_external_operations, late_error):
    manifest = {name: hash_bytes(("FABRICATED " + name).encode()) for name in m.code_paths()}
    body = _fabricated_body(kernel, manifest); raw = canonical_json(body).encode(); frames = []
    class Code:
        manifest = None
        def audit(self): pass
        def named(self): pass
        def close(self):
            if late_error: raise m.NativeMainReceiptRefusal("REFUSED: main_code")
    code = Code(); code.manifest = manifest
    monkeypatch.setattr(m, "_entry", lambda *args: (kernel.clock, m._binding(HEAD, REMOTE, OPERATION), code))
    root_value = object()
    def coordinate(*args, profile):
        assert args == (HEAD, REMOTE) and profile is p.LOCAL_MAIN_V1
        return root_value
    class Projection:
        def canonical_bytes(self): return raw
        def remaining_seconds(self): return 280.0
    def project(value):
        assert value is root_value  # Explicit LIVE Root factory boundary, never JSON reconstruction.
        return Projection()
    monkeypatch.setattr(p, "coordinate_registered", coordinate); monkeypatch.setattr(p, "project_root_closure", project)
    monkeypatch.setattr(m, "_wire", lambda value, fd=1: frames.append(value))
    ack = {**m._binding(HEAD, REMOTE, OPERATION), "event": "main_original_projection_open",
        "root_pid": os.getpid(), "main_pid": os.getppid(), "projection_sha256": hash_bytes(raw)}
    r, w = os.pipe(); os.write(w, (canonical_json(ack) + "\n").encode()); os.close(w)
    try:
        if late_error:
            with pytest.raises(no_actual_external_operations.HoldObserved): m.root_export(HEAD, REMOTE, OPERATION, input_fd=r)
            assert [frame["event"] for frame in frames] == ["projection_ready"]
            assert no_actual_external_operations.holds[0]["projection"] is not None
        else:
            m.root_export(HEAD, REMOTE, OPERATION, input_fd=r)
            assert [frame["event"] for frame in frames] == ["projection_ready", "projection_closed"]
            assert frames[0]["projection"] == frames[1]["projection"]
            assert frames[0]["projection"]["native_full9"][6] == len(raw)
    finally: os.close(r)


@pytest.fixture
def durable(composition, monkeypatch):
    """Committed Git/outer observation seam after genuine Main composition.

    The anchor pins the original published receipt seal. This fixture never
    supplies a Root capability or a caller-selected Popen wait to the loader.
    """
    public = m.coordinate_registered(HEAD, REMOTE, OPERATION).public_summary()
    anchor = {"schema": "si-native-main-committed-anchor-v1", "runtime_head": HEAD,
        "native_policy_sha256": p._policy_sha(p.LOCAL_MAIN_V1), "protocol_sha256": m.PROTOCOL_SHA256,
        **{name: public[name] for name in ("receipt_sha256", "receipt_native_full9_sha256",
            "receipt_directory_full9_sha256", "receipt_original_flags", "projection_sha256", "projection_native_full9_sha256")},
        "outer_stdout_sha256": hash_bytes((canonical_json(public) + "\n").encode()),
        "outer_actual_exit": 0, "outer_stderr_bytes": 0, "outer_elapsed_ns": 1000000000}
    monkeypatch.setattr(m, "ROOT", composition.kernel.root)
    path = m.ROOT / m.ANCHOR; path.parent.mkdir(parents=True); path.write_bytes((canonical_json(anchor) + "\n").encode()); path.chmod(0o600)
    anchor_raw = path.read_bytes()
    def git(arguments):
        assert arguments[0] == "show"
        head, name = arguments[1].split(":", 1)
        assert head == HEAD
        if name == m.ANCHOR.as_posix(): return anchor_raw
        assert name in m.code_paths()
        return ("FABRICATED " + name).encode()
    monkeypatch.setattr(p, "_git", git); monkeypatch.setattr(m, "registered", lambda: None)
    monkeypatch.setattr(p, "_guard", lambda *args: None)
    monkeypatch.setattr(p, "_Code7", lambda *args: composition.Code())
    monkeypatch.setattr(m.subprocess, "run", lambda *args, **kw: SimpleNamespace(returncode=0))
    yield SimpleNamespace(anchor=anchor, path=path, composition=composition)


def test_durable_loader_uses_committed_original_seal_and_historical_code_and_stays_held(durable):
    with m.load_registered(HEAD, REMOTE) as receipt:
        assert type(receipt) is m.AuthenticatedDurableMainReceipt
        assert receipt.public_summary()["status"] == "authenticated_durable_main_custody_observation"
        row = m._AUTHENTICATED[id(receipt)]; held = row[2]
        assert held.main_file.fd is not None and held.root_file.fd is not None
        assert held.anchor_holder.fd is not None
        assert receipt.public_summary()["authority"]["accounting_resolution_admitted"] is False
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_closed"): receipt.public_summary()


def test_original_factory_frame_cannot_be_transplanted_to_copied_receipt(durable):
    with m.load_registered(HEAD, REMOTE) as receipt:
        original = m._AUTHENTICATED[id(receipt)]
        forged = object.__new__(m.AuthenticatedDurableMainReceipt)
        row = (forged, *original[1:]); forged._anchor = row; m._AUTHENTICATED[id(forged)] = row
        with pytest.raises(m.NativeMainReceiptRefusal, match="main_factory"): forged.public_summary()
        assert receipt.public_summary()["authority"]["source_admitted"] is False


@pytest.mark.parametrize("after_close", [False, True])
def test_anchor_ancestor_redirection_is_negative_even_when_original_file_stamp_and_bytes_match(durable, after_close):
    holder = m._Anchor(HEAD); original = holder.original
    if after_close: holder.close()
    parent = durable.path.parent; renamed = parent.with_name(parent.name + "-moved")
    parent.rename(renamed); parent.symlink_to(renamed, target_is_directory=True)
    assert p._stamp(durable.path.lstat()) == original
    try:
        with pytest.raises(m.NativeMainReceiptRefusal, match="main_anchor_changed"):
            holder.named() if after_close else holder.audit()
    finally: holder.close()


@pytest.mark.parametrize("mutation", ["copied_receipt", "receipt_flags", "root_flags", "anchor", "root_dir", "historical_code"])
def test_durable_loader_never_adopts_copied_changed_or_wrong_epoch_evidence(durable, monkeypatch, mutation):
    kernel = durable.composition.kernel
    receipt = kernel.root / "main-receipt" / m.MAIN_RECEIPT
    root = kernel.root / "root-export" / m.ROOT_PROJECTION
    if mutation == "copied_receipt":
        raw = receipt.read_bytes(); receipt.unlink(); receipt.write_bytes(raw); receipt.chmod(0o600)
    elif mutation in {"receipt_flags", "root_flags"}:
        info = (receipt if mutation == "receipt_flags" else root).lstat(); kernel.flags[(info.st_dev, info.st_ino)] = 0
    elif mutation == "anchor": durable.path.write_bytes(b"{}\n")
    elif mutation == "root_dir": os.utime(root.parent, None)
    elif mutation == "historical_code":
        original = p._git
        monkeypatch.setattr(p, "_git", lambda args: b"CHANGED HISTORICAL CODE" if args[1].endswith(":" + m.DRIVER) else original(args))
    with pytest.raises((m.NativeMainReceiptRefusal, p.SupervisionRefusal)):
        with m.load_registered(HEAD, REMOTE): pytest.fail("changed original admitted")


def test_well_formed_but_uncommitted_anchor_is_never_admitted(durable, monkeypatch):
    """SI-CR27-005: the held anchor must equal the committed bytes, not just parse."""
    committed = {**durable.anchor, "outer_elapsed_ns": durable.anchor["outer_elapsed_ns"] + 1}
    original = p._git
    monkeypatch.setattr(p, "_git", lambda args: (canonical_json(committed) + "\n").encode()
        if args[1].endswith(":" + m.ANCHOR.as_posix()) else original(args))
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_anchor_changed"):
        with m.load_registered(HEAD, REMOTE): pytest.fail("uncommitted anchor admitted")


def test_anchor_runtime_head_must_be_an_ancestor_of_the_loading_head(durable, monkeypatch):
    """SI-CR27-005: a failed merge-base ancestry check refuses the anchor."""
    monkeypatch.setattr(m.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_anchor_changed"):
        with m.load_registered(HEAD, REMOTE): pytest.fail("non-ancestor runtime head admitted")


@pytest.mark.parametrize("mutation", ["root_flags", "anchor", "clock", "association"])
def test_held_durable_getter_permanently_latches_late_mutation(durable, monkeypatch, mutation):
    # SI-CR27-005: record each getter refusal inside the context; a close-time
    # refusal must not stand in for a getter that stopped rechecking.
    codes = []
    with pytest.raises((m.NativeMainReceiptRefusal, AssertionError)):
        with m.load_registered(HEAD, REMOTE) as receipt:
            held = m._AUTHENTICATED[id(receipt)][2]
            if mutation == "root_flags":
                info = held.root_file.path.lstat(); durable.composition.kernel.flags[(info.st_dev, info.st_ino)] = 0
            elif mutation == "anchor": durable.path.write_bytes(b"{}\n")
            elif mutation == "clock":
                monkeypatch.setattr(held.clock, "check", lambda: m.require(False, "main_deadline"))
            else:
                monkeypatch.setattr(held.reader, "current_association", lambda *args: m.require(False, "main_original"))
            for unused in range(2):
                try: receipt.public_summary()
                except m.NativeMainReceiptRefusal as error: codes.append(str(error))
    assert len(codes) == 2 and "main_latched" not in codes[0] and "main_latched" in codes[1]


def test_anchor_is_closed_when_current_code_constructor_fails(durable, monkeypatch):
    holders = []; original = m._Anchor
    def anchor(head):
        value = original(head); holders.append(value); return value
    monkeypatch.setattr(m, "_Anchor", anchor)
    def fail(*args): raise m.NativeMainReceiptRefusal("REFUSED: main_code")
    monkeypatch.setattr(p, "_Code7", fail)
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_code"):
        with m.load_registered(HEAD, REMOTE): pytest.fail("failed code yielded")
    assert len(holders) == 1 and holders[0].closed and holders[0].fd is None


def test_final_durable_close_clock_check_vetoes_after_last_context(durable, monkeypatch):
    with pytest.raises(m.NativeMainReceiptRefusal, match="main_deadline"):
        with m.load_registered(HEAD, REMOTE) as receipt:
            held = m._AUTHENTICATED[id(receipt)][2]; original = held.anchor_holder.named
            def late():
                original(); monkeypatch.setattr(held.clock, "check", lambda: m.require(False, "main_deadline"))
            monkeypatch.setattr(held.anchor_holder, "named", late)
