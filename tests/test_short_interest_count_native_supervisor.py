"""Named fabricated kernel/native/Git seams; never creates an image or job."""
import ast
import json
import os
from pathlib import Path
import plistlib
import socket
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_payload
from scripts import short_interest_count_native_supervisor as proof

HEAD, REMOTE = "a" * 40, "b" * 40
pytestmark = pytest.mark.skipif(os.name != "posix" or not all(hasattr(os, n) for n in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")),
    reason="Native custody software uses explicit POSIX descriptor semantics")


@pytest.fixture(autouse=True)
def deny_external(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError("actual native/provider/process operation forbidden")
    for name in ("connect", "connect_ex"): monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(proof.subprocess, "run", denied); monkeypatch.setattr(proof.subprocess, "Popen", denied)
    monkeypatch.setattr(proof.native.ctypes, "CDLL", denied)
    for name, value in (("_USED", False), ("_HELD", []), ("_RESULTS", {}), ("_FAILURES", {}), ("_FIELDS", {}), ("_BUFFER_ORIGINS", {}), ("_PRESERVATION_ORIGINS", {})):
        monkeypatch.setattr(proof, name, value)
    monkeypatch.setattr(proof.worker, "_CHILDREN", {}); monkeypatch.setattr(proof.worker, "_WAITS", {})


@pytest.fixture
def fabricated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setattr(proof, "ROOT", tmp_path)
    (tmp_path / proof.PARENT).mkdir(parents=True, mode=0o700)
    for name in proof.CODE_FILES:
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"# NAMED FABRICATED CODE\n")
    monkeypatch.setattr(proof, "POLICY_SHA256", hash_payload(proof.policy()))
    h = SimpleNamespace(events=[], processes=[], status=0, raw=None, terminal_callback=None,
        named_callback=None, close_callback=None, volumes=[], wait_error=None)
    monkeypatch.setattr(proof.worker, "_guard", lambda *args: None)
    def git(arguments):
        assert arguments[:1] == ["show"] and arguments[1].startswith(HEAD + ":")
        return (tmp_path / arguments[1].partition(":")[2]).read_bytes()
    monkeypatch.setattr(proof.worker, "_git", git)
    class FabricatedVolume:
        """Ordinary temp metadata seam, explicitly NOT an APFS/native proof."""
        def __init__(self, clock):
            h.events.append("volume-created"); self.clock = clock; self.directory = proof._Directory(proof.DOMAIN, create=True)
            self.path = self.directory.path; self.origins = {role: plistlib.dumps({"fabricated": role}) for role in ("before", "create", "attach", "initial")}
            self.fds = []; h.volumes.append(self)
        def check(self): self.directory.check(); self.clock.check()
        def outputs(self):
            self.check(); self.inner = self.path / "proof"; self.inner.mkdir(mode=0o700)
            fd = os.open(self.inner, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); self.fds.append(fd)
            return proof._Files(fd, self.directory.fd, self.inner, self.check, proof.ROLES)
        def terminal(self):
            self.origins["terminal"] = plistlib.dumps({"fabricated": "terminal"})
            if h.terminal_callback: h.terminal_callback(self)
        def inventory(self):
            self.check(); return {"explicit_fabricated_native_inventory": True}
        def named(self):
            self.directory.named()
            if h.named_callback: h.named_callback(self)
        def close(self):
            proof._drain(self.fds); self.directory.close()
            if h.close_callback: h.close_callback(self)
    monkeypatch.setattr(proof, "_Volume", FabricatedVolume)
    def popen(arguments, **kwargs):
        assert h.events == ["volume-created"]
        h.events.append("child-launched")
        raw = h.raw if h.raw is not None else b"".join(canonical_json(proof.worker._worker_line(stage, 4321, os.getpid())).encode() + b"\n" for stage in ("entered", "completed"))
        read_fd, write_fd = os.pipe(); os.write(write_fd, raw); os.close(write_fd)
        class Child:
            pid = 4321
            def __init__(self): self.stdout = os.fdopen(read_fd, "rb", buffering=0); self.waits = []
            def wait(self, *, timeout):
                self.waits.append(timeout)
                if h.wait_error is not None: raise h.wait_error
                return h.status
        child = Child(); h.processes.append(child); return child
    monkeypatch.setattr(proof.subprocess, "Popen", popen)
    try: yield h
    finally:
        for row in proof._HELD:
            process, code, bootstrap, descriptors, volume, outputs = row
            for obj in (outputs, volume, code, bootstrap):
                if obj is not None:
                    try: obj.close()
                    except BaseException: pass
            for fd in descriptors:
                try: os.close(fd)
                except OSError: pass
            if process.stdout is not None: process.stdout.close()
        for child in h.processes:
            if not child.stdout.closed: child.stdout.close()


def prepare(): return proof.prepare_bootstrap(HEAD, REMOTE)["bootstrap_sha256"]


def test_pending_policy_refuses_before_any_native_or_child(monkeypatch):
    monkeypatch.setattr(proof, "POLICY_SHA256", "PENDING")
    monkeypatch.setattr(proof.worker, "_guard", lambda *a: pytest.fail("pending policy reached Git"))
    monkeypatch.setattr(proof.native, "_platform", lambda: pytest.fail("pending policy reached platform"))
    with pytest.raises(proof.NativeProofRefusal, match="unregistered"):
        proof.run_registered(HEAD, REMOTE, "c" * 64)


def test_capture_cli_refuses_before_registration_or_domain(monkeypatch, capsys):
    monkeypatch.setattr(proof, "registered", lambda: pytest.fail("capture reached registration"))
    assert proof.main(["capture"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["failure"]["contract_code"] == "native_proof_source_refused"
    assert result["authority"]["provider_HTTP"] == 0


def test_bootstrap_never_creates_native_domain_and_job_is_one_shot(fabricated):
    digest = prepare(); base = proof.ROOT / proof.PARENT / proof.BOOTSTRAP
    assert set(os.listdir(base)) == {"launch.spec.json", "job.plist"}
    assert not (base.parent / proof.DOMAIN).exists() and not fabricated.events
    job = plistlib.loads((base / "job.plist").read_bytes())
    assert job == proof.build_launchd_plist(HEAD, REMOTE, digest)
    assert job["RunAtLoad"] is True and job["KeepAlive"] is False
    assert job["StandardOutPath"] == job["StandardErrorPath"] == "/dev/null"
    assert not {"StartInterval", "StartCalendarInterval", "WatchPaths", "QueueDirectories"} & set(job)
    with pytest.raises(proof.NativeProofRefusal, match="exists"): prepare()


def test_config_only_ctime_drift_after_writer_close_does_not_become_evidence_admission(fabricated, monkeypatch):
    monkeypatch.setattr(proof.native, "_platform", lambda: None)  # Named wrapped-os.open capability seam.
    real_open, real_close, real_stat, real_fstat = os.open, os.close, os.stat, os.fstat
    writers, drifted = {}, set()
    def observed(info):
        return _ProjectedStat(info, st_ctime_ns=info.st_ctime_ns + 1) if info.st_ino in drifted else info
    def opened(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if path in ("launch.spec.json", "job.plist") and flags & os.O_CREAT:
            writers[fd] = real_fstat(fd).st_ino
        return fd
    def closed(fd):
        inode = writers.pop(fd, None); value = real_close(fd)
        if inode is not None: drifted.add(inode)
        return value
    monkeypatch.setattr(proof.os, "open", opened); monkeypatch.setattr(proof.os, "close", closed)
    monkeypatch.setattr(proof.os, "stat", lambda *a, **k: observed(real_stat(*a, **k)))
    monkeypatch.setattr(proof.os, "fstat", lambda fd: observed(real_fstat(fd)))
    digest = prepare()
    assert drifted and len(digest) == 64 and not fabricated.events
    base = proof.ROOT / proof.PARENT / proof.BOOTSTRAP
    assert set(os.listdir(base)) == {"launch.spec.json", "job.plist"}


@pytest.fixture
def config_only(fabricated):
    directory = proof._Directory(proof.BOOTSTRAP, create=True); config = proof._Config(directory)
    config.write("launch.spec.json", b'{"fixed":true}')
    try: yield config, directory
    finally: config.close(); directory.close()


@pytest.mark.parametrize("mutation", ["bytes", "mtime_and_bytes", "mode", "hardlink", "identity", "symlink", "fifo"])
def test_config_identity_protection_and_exact_bytes_remain_required(config_only, mutation):
    config, directory = config_only; path = directory.path / "launch.spec.json"
    raw = path.read_bytes()
    if mutation in ("bytes", "mtime_and_bytes"):
        path.write_bytes(b"X" + raw[1:])
        if mutation == "mtime_and_bytes": os.utime(path, None)
    elif mutation == "mode": path.chmod(0o644)
    elif mutation == "hardlink": os.link(path, directory.path.parent / "extra-hardlink")
    else:
        retained = directory.path.parent / "retained-original-config"; path.rename(retained)
        if mutation == "identity": path.write_bytes(raw); path.chmod(0o600)
        elif mutation == "symlink": path.symlink_to(retained)
        else: os.mkfifo(path, 0o600)
    with pytest.raises(proof.NativeProofRefusal): config.audit()


def test_config_full9_still_required_during_each_descriptor_read(config_only, monkeypatch):
    config, directory = config_only; inode = (directory.path / "launch.spec.json").lstat().st_ino
    real_read, real_stat, real_fstat = os.read, os.stat, os.fstat; changed = []
    def observed(info): return _ProjectedStat(info, st_ctime_ns=info.st_ctime_ns + 1) if changed and info.st_ino == inode else info
    def read(fd, maximum):
        result = real_read(fd, maximum)
        if real_fstat(fd).st_ino == inode: changed.append(True)
        return result
    monkeypatch.setattr(proof.os, "read", read)
    monkeypatch.setattr(proof.os, "stat", lambda *a, **k: observed(real_stat(*a, **k)))
    monkeypatch.setattr(proof.os, "fstat", lambda fd: observed(real_fstat(fd)))
    with pytest.raises(proof.NativeProofRefusal, match="stamp"): config.audit()


@pytest.mark.parametrize("mutation", ["bytes", "ctime"])
def test_config_read_close_is_inside_that_reads_full9_barrier(config_only, monkeypatch, mutation):
    config, directory = config_only; path = directory.path / "launch.spec.json"; inode = path.lstat().st_ino
    real_open, real_close, real_stat, real_fstat = os.open, os.close, os.stat, os.fstat
    readers, changed = set(), []
    def opened(name, flags, *args, **kwargs):
        fd = real_open(name, flags, *args, **kwargs)
        if name == "launch.spec.json" and flags & os.O_ACCMODE == os.O_RDONLY: readers.add(fd)
        return fd
    def closed(fd):
        value = real_close(fd)
        if fd in readers and not changed:
            changed.append(True)
            if mutation == "bytes":
                with path.open("r+b") as f: f.write(b"X")
        return value
    def observed(info):
        return _ProjectedStat(info, st_ctime_ns=info.st_ctime_ns + 1) if mutation == "ctime" and changed and info.st_ino == inode else info
    monkeypatch.setattr(proof.os, "open", opened); monkeypatch.setattr(proof.os, "close", closed)
    monkeypatch.setattr(proof.os, "stat", lambda *a, **k: observed(real_stat(*a, **k)))
    monkeypatch.setattr(proof.os, "fstat", lambda fd: observed(real_fstat(fd)))
    with pytest.raises(proof.NativeProofRefusal, match="stamp"): config.audit()


def test_config_role_cannot_publish_evidence_or_supply_a_source_seal(config_only):
    config, unused = config_only
    assert not hasattr(config, "seal") and not hasattr(config, "inventory")
    with pytest.raises(proof.NativeProofRefusal): config.write("run.started.json", b"{}")


@pytest.mark.parametrize("failure", ["write_zero", "fsync", "writer_close"])
def test_config_publication_io_failures_are_fatal_and_original_fds_drain(config_only, monkeypatch, failure):
    config, directory = config_only
    original_open, original_close, original_write, original_fsync = os.open, os.close, os.write, os.fsync
    targets, failed = set(), []
    def opened(name, flags, *args, **kwargs):
        fd = original_open(name, flags, *args, **kwargs)
        if name == "job.plist" and flags & os.O_CREAT: targets.add(fd)
        return fd
    def closed(fd):
        value = original_close(fd)
        if failure == "writer_close" and fd in targets and not failed:
            failed.append(True); raise OSError(5, "PRIVATE_WRITER_CLOSE_FAILURE")
        return value
    def write(fd, raw):
        if failure == "write_zero" and fd in targets: failed.append(True); return 0
        return original_write(fd, raw)
    def fsync(fd):
        if failure == "fsync" and fd in targets: failed.append(True); raise OSError(5, "PRIVATE_FSYNC_FAILURE")
        return original_fsync(fd)
    monkeypatch.setattr(proof.os, "open", opened); monkeypatch.setattr(proof.os, "close", closed)
    monkeypatch.setattr(proof.os, "write", write); monkeypatch.setattr(proof.os, "fsync", fsync)
    expected = proof.NativeProofRefusal if failure == "write_zero" else OSError
    try: raise ValueError("UNRELATED_CALLER_EXCEPTION")
    except ValueError:
        with pytest.raises(expected): config.write("job.plist", b"FIXED_FAKE_PLIST")
    assert targets and failed
    for fd in targets:
        with pytest.raises(OSError): os.fstat(fd)


def test_prepare_failure_records_entered_phase_fixed_component_and_ordinal(fabricated, monkeypatch):
    original = proof._Config.write
    def fail(self, name, raw):
        if name == "job.plist": raise OSError(5, "PRIVATE_UNCONTROLLED_ERROR_PATH")
        return original(self, name, raw)
    monkeypatch.setattr(proof._Config, "write", fail)
    with pytest.raises(OSError) as caught: prepare()
    detail = proof.failure_summary(caught.value)
    assert (detail["stage"], detail["component"], detail["ordinal"]) == ("bootstrap", "bootstrap_job", 2)
    assert detail["errno_name"] == "EIO" and "PRIVATE" not in canonical_json(detail)
    assert detail["component_scope"] == "entered_phase_including_callbacks_not_forensic_attribution"


def test_code_ctime_epoch_stays_strict_after_config_role_correction(fabricated, monkeypatch):
    original_close, real_stat, real_fstat = proof._Code.close, os.stat, os.fstat
    inode = (proof.ROOT / proof.CODE_FILES[0]).lstat().st_ino; changed = []
    def close(self): original_close(self); changed.append(True)
    def observed(info): return _ProjectedStat(info, st_ctime_ns=info.st_ctime_ns + 1) if changed and info.st_ino == inode else info
    monkeypatch.setattr(proof._Code, "close", close)
    monkeypatch.setattr(proof.os, "stat", lambda *a, **k: observed(real_stat(*a, **k)))
    monkeypatch.setattr(proof.os, "fstat", lambda fd: observed(real_fstat(fd)))
    with pytest.raises(proof.NativeProofRefusal, match="stamp"): prepare()


def test_inner_evidence_ctime_epoch_stays_strict_after_config_role_correction(fabricated, monkeypatch):
    real_stat, real_fstat = os.stat, os.fstat; changed = []
    fabricated.terminal_callback = lambda volume: changed.append((volume.path / "proof/run.started.json").lstat().st_ino)
    def observed(info): return _ProjectedStat(info, st_ctime_ns=info.st_ctime_ns + 1) if info.st_ino in changed else info
    monkeypatch.setattr(proof.os, "stat", lambda *a, **k: observed(real_stat(*a, **k)))
    monkeypatch.setattr(proof.os, "fstat", lambda fd: observed(real_fstat(fd)))
    with pytest.raises(proof.NativeProofRefusal, match="stamp"): proof.run_registered(HEAD, REMOTE, prepare())


@pytest.mark.parametrize("entry", ["bootstrap", "volume"])
def test_unsupported_platform_refuses_before_consuming_any_new_namespace(fabricated, monkeypatch, entry):
    def unsupported(): raise proof.native.IsolatedVolumeRefusal("isolated_platform_refused")
    monkeypatch.setattr(proof.native, "_platform", unsupported)
    with pytest.raises(proof.native.IsolatedVolumeRefusal, match="platform_refused"):
        if entry == "bootstrap": prepare()
        else: REAL_VOLUME(proof._Clock())
    parent = proof.ROOT / proof.PARENT
    assert not (parent / proof.BOOTSTRAP).exists() and not (parent / proof.DOMAIN).exists()


def test_same_creator_volume_precedes_original_child_wait_and_all_results_are_provisional(fabricated):
    result = proof.run_registered(HEAD, REMOTE, prepare()).public_summary()
    assert fabricated.events == ["volume-created", "child-launched"]
    assert len(fabricated.processes[0].waits) == 1 and 0 < fabricated.processes[0].waits[0] <= 5
    assert result["actual_child_exit"] == 0 and result["known_Codex_exec_session"] is None
    assert result["supervisor_process_exit_attested"] is result["launcher_independence_verified"] is False
    assert result["authority"]["source_dispatch_authority"] is False
    path = proof.ROOT / proof.PARENT / proof.DOMAIN / "proof"
    assert set(os.listdir(path)) == set(proof.RAW_ROLES) | {"run.started.json", "stdout.jsonl", "child.exit.provisional.json", "run.completed.provisional.json", proof.INVENTORY_ROLE}
    assert not proof._HELD and fabricated.processes[0].stdout.closed
    with pytest.raises(proof.NativeProofRefusal, match="already_used"): proof.run_registered(HEAD, REMOTE, "c" * 64)


def test_private_inventory_binds_only_original_preceding_seals_without_self_cycle(fabricated):
    result = proof.run_registered(HEAD, REMOTE, prepare()).public_summary()
    path = proof.ROOT / proof.PARENT / proof.DOMAIN / "proof"
    inventory_raw = (path / proof.INVENTORY_ROLE).read_bytes(); inventory = json.loads(inventory_raw)
    marker = json.loads((path / "run.completed.provisional.json").read_bytes())
    assert marker["inventory_sha256"] == result["inventory_sha256"] == proof.hash_bytes(inventory_raw)
    assert marker["inventory_original_stamp"] == list(proof._stamp((path / proof.INVENTORY_ROLE).lstat()))
    assert "inventory_original_stamp" not in result
    names = {row["name"] for row in inventory["controls"]}
    assert names == set(os.listdir(path)) - {proof.INVENTORY_ROLE, "run.completed.provisional.json"}
    for row in inventory["controls"]:
        assert row["original_stamp"] == list(proof._stamp((path / row["name"]).lstat()))
        assert row["sha256"] == proof.hash_bytes((path / row["name"]).read_bytes())


def test_json_flags_and_copied_payload_cannot_mint_result():
    with pytest.raises(proof.NativeProofRefusal, match="factory"): proof.NativeProofResult()
    forged = object.__new__(proof.NativeProofResult); forged._anchor = (forged, "{}", {"exit": 0})
    with pytest.raises(proof.NativeProofRefusal, match="changed"): forged.public_summary()


def test_nonzero_original_wait_preserves_negative_without_positive_or_retry(fabricated):
    fabricated.status = 2
    with pytest.raises(proof.worker.ProcessSupervisorRefusal): proof.run_registered(HEAD, REMOTE, prepare())
    path = proof.ROOT / proof.PARENT / proof.DOMAIN / "proof"
    assert "run.refused.json" in os.listdir(path) and "run.completed.provisional.json" not in os.listdir(path)
    assert len(fabricated.processes) == 1 and not proof._RESULTS


@pytest.mark.parametrize("boundary", ["terminal", "named", "close"])
def test_last_native_or_cleanup_callback_cannot_hide_original_stamp_drift(fabricated, boundary):
    def changed(volume):
        path = volume.path / "proof/run.started.json"
        with path.open("r+b") as f: f.write(b"X")
    setattr(fabricated, {"terminal": "terminal_callback", "named": "named_callback", "close": "close_callback"}[boundary], changed)
    with pytest.raises(proof.NativeProofRefusal): proof.run_registered(HEAD, REMOTE, prepare())
    assert not proof._RESULTS


def test_negative_after_last_context_cleanup_vetoes_provisional_positive(fabricated):
    def negative(volume): (volume.path / "proof/run.refused.json").write_bytes(b'{"fabricated":true}')
    fabricated.close_callback = negative
    with pytest.raises(proof.NativeProofRefusal, match="membership"): proof.run_registered(HEAD, REMOTE, prepare())
    assert not proof._RESULTS


def test_unknown_child_retains_all_original_contexts_without_closing_or_restarting(fabricated, monkeypatch):
    fabricated.raw = b"FABRICATED_UNRECOGNIZED_OUTPUT\n"
    fabricated.wait_error = OSError(5, "FABRICATED_ORIGINAL_WAIT_UNAVAILABLE")
    class Held(BaseException): pass
    monkeypatch.setattr(proof.time, "sleep", lambda seconds: (_ for _ in ()).throw(Held()))
    with pytest.raises(Held): proof.run_registered(HEAD, REMOTE, prepare())
    assert len(proof._HELD) == len(fabricated.processes) == 1
    process, code, bootstrap, descriptors, volume, outputs = proof._HELD[0]
    assert process.waits == [30] and not process.stdout.closed
    assert code.fds and bootstrap.fds and descriptors and volume.fds and outputs.fds
    assert not outputs.closed and not proof._RESULTS


def test_caller_collect_status_without_original_wait_record_remains_held(fabricated, monkeypatch):
    class Held(BaseException): pass
    monkeypatch.setattr(proof.worker, "_collect", lambda *args: (0, "c" * 64, (0,) * 9))
    monkeypatch.setattr(proof.time, "sleep", lambda seconds: (_ for _ in ()).throw(Held()))
    with pytest.raises(Held): proof.run_registered(HEAD, REMOTE, prepare())
    assert len(proof._HELD) == 1 and not proof._RESULTS
    assert fabricated.processes[0].waits == []


def test_late_original_wait0_is_negative_only_and_preserves_every_original_buffer(fabricated):
    raw = b"FABRICATED_UNRECOGNIZED_OUTPUT\n"; fabricated.raw = raw
    with pytest.raises(proof.worker.ProcessSupervisorRefusal): proof.run_registered(HEAD, REMOTE, prepare())
    base = proof.ROOT / proof.PARENT / proof.DOMAIN / "proof"
    buffers = json.loads((base / "child.failure.buffers.private.json").read_bytes())["private_buffers_hex"]
    assert set(buffers) == {"pending", "output", "line", "block"}
    assert bytes.fromhex(buffers["block"]) == raw and bytes.fromhex(buffers["line"]) == raw[:-1]
    assert json.loads((base / "child.remaining.pipe.private.json").read_bytes())["private_bytes_hex"] == ""
    negative = json.loads((base / "child.late.exit.negative.json").read_bytes())
    assert negative["actual_child_exit"] == 0 and negative["status"].startswith("permanent_negative")
    assert not proof._RESULTS and not proof._HELD and fabricated.processes[0].waits == [30]
    assert "run.refused.json" in os.listdir(base) and "run.completed.provisional.json" not in os.listdir(base)


def test_known_original_wait0_still_preserves_trailing_pending_bytes(fabricated):
    lines = b"".join(canonical_json(proof.worker._worker_line(stage, 4321, os.getpid())).encode() + b"\n" for stage in ("entered", "completed"))
    fabricated.raw = lines + b"FABRICATED_PRIVATE_PENDING"
    with pytest.raises(proof.worker.ProcessSupervisorRefusal): proof.run_registered(HEAD, REMOTE, prepare())
    base = proof.ROOT / proof.PARENT / proof.DOMAIN / "proof"
    buffers = json.loads((base / "child.failure.buffers.private.json").read_bytes())["private_buffers_hex"]
    assert bytes.fromhex(buffers["pending"]) == b"FABRICATED_PRIVATE_PENDING"
    assert (base / "stdout.jsonl").read_bytes() == lines
    assert len(fabricated.processes[0].waits) == 1 and not proof._RESULTS and not proof._HELD


def test_failed_buffer_persistence_keeps_original_frame_and_every_context(fabricated, monkeypatch):
    fabricated.raw = b"FABRICATED_UNRECOGNIZED_OUTPUT\n"
    original = proof._Files.write
    def fail(self, name, raw):
        if name == "child.failure.buffers.private.json": raise OSError(5, "FABRICATED_PRIVATE_PRESERVATION_FAILURE")
        return original(self, name, raw)
    monkeypatch.setattr(proof._Files, "write", fail)
    class Held(BaseException): pass
    monkeypatch.setattr(proof.time, "sleep", lambda seconds: (_ for _ in ()).throw(Held()))
    with pytest.raises(Held): proof.run_registered(HEAD, REMOTE, prepare())
    assert len(proof._HELD) == len(proof._BUFFER_ORIGINS) == 1 and not proof._RESULTS
    origin = next(iter(proof._BUFFER_ORIGINS.values()))
    assert {name for name, unused in origin[5]} == {"pending", "output", "line", "block"}
    assert not fabricated.processes[0].stdout.closed


def test_known_wait0_with_unavailable_original_buffer_provenance_stays_held(fabricated, monkeypatch):
    lines = b"".join(canonical_json(proof.worker._worker_line(stage, 4321, os.getpid())).encode() + b"\n" for stage in ("entered", "completed"))
    fabricated.raw = lines + b"FABRICATED_PRIVATE_PENDING"
    monkeypatch.setattr(proof, "_collect_buffers", lambda *args: None)  # Explicit failed provenance seam.
    class Held(BaseException): pass
    monkeypatch.setattr(proof.time, "sleep", lambda seconds: (_ for _ in ()).throw(Held()))
    with pytest.raises(Held): proof.run_registered(HEAD, REMOTE, prepare())
    assert len(proof._HELD) == 1 and not proof._RESULTS and not fabricated.processes[0].stdout.closed


@pytest.mark.parametrize("failure", ["remaining_write", "cap_after_read"])
def test_newly_consumed_preservation_buffers_remain_strongly_held_on_failure(fabricated, monkeypatch, failure):
    fabricated.raw = b"BAD\n" + (b"UNIQUE_FABRICATED_REMAINDER" * (120 if failure == "remaining_write" else 400))
    original_read, original_write = os.read, proof._Files.write; consumed = []
    def read(fd, maximum):
        block = original_read(fd, maximum)
        if fabricated.processes and fd == fabricated.processes[0].stdout.fileno(): consumed.append(block)
        return block
    def write(self, name, raw):
        if failure == "remaining_write" and name == "child.remaining.pipe.private.json":
            raise OSError(5, "FABRICATED_SECOND_PERSISTENCE_FAILURE")
        return original_write(self, name, raw)
    monkeypatch.setattr(proof.os, "read", read); monkeypatch.setattr(proof._Files, "write", write)
    class Held(BaseException): pass
    monkeypatch.setattr(proof.time, "sleep", lambda seconds: (_ for _ in ()).throw(Held()))
    with pytest.raises(Held): proof.run_registered(HEAD, REMOTE, prepare())
    assert proof._HELD and not proof._RESULTS
    states = getattr(proof, "_PRESERVATION_ORIGINS", {})
    assert len(states) == 1
    state = next(iter(states.values()))[-1]
    assert len(state["blocks"]) == len(consumed) - 1
    assert all(a is b for a, b in zip(state["blocks"], consumed[1:]))
    assert state["remaining"] == b"".join(consumed[1:])
    assert state["failure"] is not None and state["failure_frame"] is not None
    assert not fabricated.processes[0].stdout.closed


@pytest.mark.parametrize("mutation", ["mode", "hardlink", "bytes"])
def test_original_control_protection_and_full_stamp_never_rebaseline(fabricated, mutation):
    def mutate(volume):
        path = volume.path / "proof/run.started.json"
        if mutation == "mode": path.chmod(0o644)
        elif mutation == "hardlink": os.link(path, volume.path / "proof/foreign")
        else:
            with path.open("r+b") as f: f.write(b"X")
    fabricated.terminal_callback = mutate
    with pytest.raises(proof.NativeProofRefusal): proof.run_registered(HEAD, REMOTE, prepare())
    assert not proof._RESULTS


def test_final_git_callback_cannot_hide_an_earlier_control_mutation(fabricated, monkeypatch):
    original = proof.worker._git; changed = []
    def git(arguments):
        raw = original(arguments)
        if fabricated.processes and fabricated.processes[0].waits and not changed:
            path = fabricated.volumes[0].path / "proof/run.started.json"
            with path.open("r+b") as f: f.write(b"X")
            changed.append(True)
        return raw
    monkeypatch.setattr(proof.worker, "_git", git)
    with pytest.raises(proof.NativeProofRefusal): proof.run_registered(HEAD, REMOTE, prepare())
    assert changed and not proof._RESULTS


def test_clean_context_close_error_is_fatal_even_under_unrelated_caller_exception(fabricated, monkeypatch):
    digest = prepare(); original = proof._Files.close; failures = []
    def close(self):
        original(self)
        if self.path.name == "proof" and not failures:
            failures.append(True); raise OSError(5, "PRIVATE_CLEAN_OUTPUT_CLOSE")
    monkeypatch.setattr(proof._Files, "close", close)
    try: raise ValueError("PRIVATE_UNRELATED_CALLER")
    except ValueError:
        with pytest.raises(OSError) as caught: proof.run_registered(HEAD, REMOTE, digest)
    assert caught.value.errno == 5 and not proof._RESULTS
    assert proof.failure_summary(caught.value)["errno_name"] == "EIO"


@pytest.mark.parametrize("field,value", [("fstype", "hfs"), ("owner", -1), ("flags", 0),
    ("flags", proof.native.MNT_LOCAL | proof.native.MNT_DONTBROWSE | proof.native.MNT_RDONLY),
    ("flags", proof.native.MNT_LOCAL | proof.native.MNT_DONTBROWSE | proof.native.MNT_IGNORE_OWNERSHIP)])
def test_native_contract_rejects_unsupported_or_weakened_mount_masks(field, value):
    volume, unused, unused_image = association(); volume.device = "/dev/disk99s1"
    current = {"fsid": (1, 2), "owner": os.getuid(), "flags": proof.native.MNT_LOCAL | proof.native.MNT_DONTBROWSE,
        "flags_ext": 0, "type": 26, "subtype": 0, "fstype": "apfs", "mounted_on": str(volume.mount), "mounted_from": volume.device}
    volume.mount_native = proof.native._mount_identity(current); current[field] = value
    with pytest.raises(proof.NativeProofRefusal, match="mount"): volume._native(current)


def test_whole_context_clock_is_monotonic_and_not_extended():
    clock = proof._Clock(); clock.clock = lambda: clock.begin + 301
    with pytest.raises(proof.NativeProofRefusal, match="deadline"): clock.check()
    clock.clock = lambda: clock.begin - 1
    with pytest.raises(proof.NativeProofRefusal, match="clock"): clock.check()


def test_native_commands_have_fixed_fresh_targets_and_no_destructive_or_retry_surface():
    volume = object.__new__(REAL_VOLUME); volume.image = Path("/FABRICATED/new/backing.sparseimage"); volume.mount = Path("/FABRICATED/new/mount")
    create, attach, info = (volume.arguments(v) for v in ("create", "attach", "info"))
    assert create[:9] == ["/usr/bin/hdiutil", "create", "-type", "SPARSE", "-size", "8g", "-fs", "APFS", "-uid"]
    assert "-nospotlight" in create and "-nobrowse" in attach and attach[attach.index("-owners") + 1] == "on"
    assert info == ["/usr/bin/hdiutil", "info", "-plist"]
    for verb in ("detach", "resize", "convert", "erase", "mount"):
        with pytest.raises(proof.NativeProofRefusal, match="command"): volume.arguments(verb)


REAL_VOLUME = proof._Volume


def association(images=None):
    volume = object.__new__(REAL_VOLUME); volume.image = Path("/FABRICATED/new/backing.sparseimage"); volume.mount = Path("/FABRICATED/new/mount")
    entity = {"dev-entry": "/dev/disk99s1", "content-hint": "Apple_APFS", "volume-kind": "apfs", "mount-point": str(volume.mount)}
    volume.attach_entities = proof.native._entities({"system-entities": [entity]})
    image = {"image-path": str(volume.image), "system-entities": [entity]}
    return volume, entity, image


@pytest.mark.parametrize("mutation", ["image_duplicate", "device_alias", "mount_alias", "shadow", "wrong_attach"])
def test_native_global_association_and_original_attach_reject_aliases(mutation):
    volume, entity, image = association(); images = [image]
    if mutation == "image_duplicate": images.append(dict(image))
    elif mutation == "device_alias": images.append({"image-path": "/FABRICATED/other", "system-entities": [{"dev-entry": entity["dev-entry"]}]})
    elif mutation == "mount_alias": images.append({"image-path": "/FABRICATED/other", "system-entities": [{"dev-entry": "/dev/disk98s1", "mount-point": str(volume.mount)}]})
    elif mutation == "shadow": image["shadow-path"] = "/FABRICATED/overlay"
    else: volume.attach_entities = (("/dev/disk98s1", "Apple_APFS", "apfs", str(volume.mount)),)
    with pytest.raises(proof.NativeProofRefusal, match="association"): volume._association(plistlib.dumps({"images": images}))


def test_valid_native_association_uses_original_unique_device_and_mount():
    volume, unused, image = association()
    assert volume._association(plistlib.dumps({"images": [image]})) == "/dev/disk99s1"


def test_global_alias_of_an_original_parent_device_refuses_even_with_unique_leaf():
    volume, entity, image = association()
    parent = {"dev-entry": "/dev/disk99"}
    image["system-entities"].insert(0, parent)
    volume.attach_entities = proof.native._entities({"system-entities": [parent, entity]})
    other = {"image-path": "/FABRICATED/other/backing.sparseimage", "system-entities": [parent]}
    with pytest.raises(proof.NativeProofRefusal, match="association"):
        volume._association(plistlib.dumps({"images": [image, other]}))


def test_original_native_create_list_shape_is_accepted_only_for_exact_fresh_image(monkeypatch):
    volume, unused, unused_image = association(); volume.origins = {}; volume.clock = proof._Clock()
    volume._pre_command = lambda role: None  # Named command-shape-only seam.
    raw = plistlib.dumps([str(volume.image)])
    calls = []
    def run(arguments, **kwargs):
        calls.append((arguments, kwargs)); return SimpleNamespace(returncode=0, stdout=raw)
    monkeypatch.setattr(proof.subprocess, "run", run)
    volume.command("create", "create")
    assert volume.origins["create"] == raw and len(calls) == 1
    assert calls[0][1]["timeout"] <= 120 and calls[0][1]["env"] == {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}


def test_bootstrap_replacement_during_read_refuses_before_native_side_effect(fabricated, monkeypatch):
    digest = prepare(); original, original_fstat = os.read, os.fstat; changed, armed = [], []
    path = proof.ROOT / proof.PARENT / proof.BOOTSTRAP / "launch.spec.json"
    inode = path.lstat().st_ino
    def read(fd, maximum):
        raw = original(fd, maximum)
        if original_fstat(fd).st_ino == inode: armed.append(True)
        return raw
    def fstat(fd):
        info = original_fstat(fd)
        # Exact boundary seam: the FD observation precedes a namespace race;
        # the final named audit must still run before any native creation.
        if info.st_ino == inode and armed and not changed:
            old = path.with_name("retained-original-spec")
            raw = path.read_bytes(); path.rename(old); path.write_bytes(raw); path.chmod(0o600); changed.append(True)
        return info
    monkeypatch.setattr(proof.os, "read", read)
    monkeypatch.setattr(proof.os, "fstat", fstat)
    with pytest.raises(proof.NativeProofRefusal): proof.run_registered(HEAD, REMOTE, digest)
    assert changed and fabricated.events == []


class _ProjectedStat:
    def __init__(self, original, **overrides): self.original, self.overrides = original, overrides
    def __getattr__(self, name): return self.overrides.get(name, getattr(self.original, name))


@pytest.mark.parametrize("race", [None, "backing", "under_mount"])
def test_real_native_constructor_has_original_creator_fd_lifetime_with_fabricated_kernel(tmp_path, monkeypatch, race):
    """Every APFS/kernel/command observation is an explicit fake projection."""
    monkeypatch.chdir(tmp_path); monkeypatch.setattr(proof, "ROOT", tmp_path)
    (tmp_path / proof.PARENT).mkdir(parents=True, mode=0o700)
    base = tmp_path / proof.PARENT / proof.DOMAIN; mount = base / "mount"
    real_open, real_stat, real_fstat, real_close, real_mkdir, real_listdir = os.open, os.stat, os.fstat, os.close, os.mkdir, os.listdir
    attached, calls, mounted_fds, all_fds, under_fds, changed = [], [], set(), set(), set(), []
    def opened(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs); all_fds.add(fd)
        if str(path) == "mount" and not attached: under_fds.add(fd)
        if attached and (str(path) == "mount" or kwargs.get("dir_fd") in mounted_fds): mounted_fds.add(fd)
        return fd
    def closed(fd):
        value = real_close(fd); all_fds.discard(fd); mounted_fds.discard(fd); return value
    def fst(fd):
        info = real_fstat(fd)
        return _ProjectedStat(info, st_dev=info.st_dev + 1) if fd in mounted_fds else info
    def st(path, *args, **kwargs):
        info = real_stat(path, *args, **kwargs)
        if attached and (Path(path) == mount or str(path).startswith(str(mount) + "/") or kwargs.get("dir_fd") in mounted_fds):
            return _ProjectedStat(info, st_dev=info.st_dev + 1)
        return info
    monkeypatch.setattr(proof.os, "open", opened); monkeypatch.setattr(proof.os, "close", closed)
    monkeypatch.setattr(proof.os, "fstat", fst); monkeypatch.setattr(proof.os, "stat", st)
    def mkdir(path, *args, **kwargs):
        result = real_mkdir(path, *args, **kwargs)
        if race == "backing" and str(path) == "mount" and not changed:
            backing = base / "backing.sparseimage"
            backing.rename(tmp_path / "retained-original-backing")
            backing.write_bytes(b"FABRICATED_REPLACEMENT_NOT_AN_IMAGE"); backing.chmod(0o600); changed.append(True)
        return result
    def listdir(path):
        names = real_listdir(path)
        if race == "under_mount" and path in under_fds and not changed:
            mount.rename(tmp_path / "retained-original-under-mount")
            real_mkdir(mount, 0o700); changed.append(True)
        return names
    monkeypatch.setattr(proof.os, "mkdir", mkdir); monkeypatch.setattr(proof.os, "listdir", listdir)
    def statfs(fd):
        mounted = fd in mounted_fds
        return {"bsize": 4096, "blocks": 2 ** 21, "bavail": 3 * 2 ** 20, "fsid": (2 if mounted else 1, 0),
            "owner": os.getuid(), "flags": proof.native.MNT_LOCAL | (proof.native.MNT_DONTBROWSE if mounted else 0),
            "flags_ext": 0, "type": 26, "subtype": 0, "fstype": "apfs", "mounted_on": str(mount if mounted else tmp_path),
            "mounted_from": "/dev/disk99s1" if mounted else "/dev/disk98s1"}
    monkeypatch.setattr(proof.native, "_native_statfs", statfs)
    monkeypatch.setattr(proof.native, "_platform", lambda: None)  # Explicit fabricated SDK/platform seam.
    monkeypatch.setattr(proof.native, "_node_pin", lambda device, dev: (device, dev))
    entity = {"dev-entry": "/dev/disk99s1", "content-hint": "Apple_APFS", "volume-kind": "apfs", "mount-point": str(mount)}
    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "create":
            (base / "backing.sparseimage").write_bytes(b"FABRICATED_NOT_AN_IMAGE"); value = [str(base / "backing.sparseimage")]
        elif args[1] == "attach": attached.append(True); value = {"system-entities": [entity]}
        else: value = {"images": [{"image-path": str(base / "backing.sparseimage"), "system-entities": [entity]}] if attached else []}
        return SimpleNamespace(returncode=0, stdout=plistlib.dumps(value))
    monkeypatch.setattr(proof.subprocess, "run", run)
    volume = None; output = None
    try:
        if race:
            with pytest.raises(proof.NativeProofRefusal): volume = REAL_VOLUME(proof._Clock())
            assert changed and not any(args[1] == "attach" for args in calls)
            return
        volume = REAL_VOLUME(proof._Clock()); output = volume.outputs()
        output.write("run.started.json", b'{"fabricated":true}'); volume.terminal(); output.audit()
        assert [args[1] for args in calls] == ["info", "create", "attach", "info", "info"]
        output.close(); volume.close(); output.named(); volume.named()
        assert not all_fds
    finally:
        if output is not None:
            try: output.close()
            except OSError: pass
        if volume is not None:
            try: volume.close()
            except OSError: pass
        for fd in tuple(all_fds): real_close(fd)


def test_source_free_import_boundary_and_no_old_factory_or_mutating_device_api():
    tree = ast.parse(Path(proof.__file__).read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    forbidden = {"prepare_registered_volume", "detach", "unlink", "remove", "rmtree", "kill", "terminate", "send_signal", "setattr"}
    assert not any(isinstance(n.func, ast.Attribute) and n.func.attr in forbidden for n in calls)
    assert not any(isinstance(n.func, ast.Name) and n.func.id in forbidden for n in calls)
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports == {"pathlib", "data.hashing", "scripts"}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module == "scripts":
            assert {a.name for a in n.names} <= {"short_interest_count_process_supervisor", "short_interest_isolated_custody_volume"}
