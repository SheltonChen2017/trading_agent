"""New-scope supervision composition with named fabricated I/O boundaries.

Ordinary temporary directories are NOT APFS evidence. The fake worker uses a
pipe and the unchanged original collector/wait registries; it runs no process,
source operation, launchd command, image command or native syscall.
"""
import json
import os
import plistlib
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import prove_short_interest_native_supervision as proof


HEAD, REMOTE = "a" * 40, "b" * 40
pytestmark = pytest.mark.skipif(os.name != "posix" or not all(hasattr(os, n) for n in
    ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "openpty")), reason="Explicit POSIX descriptor/PTY contract")


@pytest.fixture(autouse=True)
def owned_external_boundaries(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("actual native, launchd or worker operation forbidden")
    for name in ("_native_command", "_launch_worker", "_launch_service", "_platform",
                 "_native_statfs", "_device_node"):
        if hasattr(proof, name): monkeypatch.setattr(proof, name, denied)
    for name, value in (("_USED", False), ("_PRODUCERS", {}), ("_CLOSED", {}), ("_PREPARED", {}),
                        ("_HELD", []), ("_FAILURES", {}), ("_KERNEL_ORIGINS", {}), ("_ROOT_RECEIPTS", {}),
                        ("_ADVISORIES", {}), ("_COMPARISONS", {}), ("_PRESERVATIONS", {}),
                        ("_NEGATIVE_CLOSURES", {}), ("_NEGATIVE_WAITS", {}),
                        ("_CAPTURED", []), ("_PRIVATE_FAILURES", {}),
                        ("_CREATION_STATES", {}), ("_CREATION_FAILURES", {}),
                        ("_CREATION_MANIFESTS", {}), ("_SYSTEM_FAILURES", {}), ("_PRODUCTION_SCOPES", {}),
                        ("_NATIVE_PLANS", {}), ("_NATIVE_INVOCATIONS", {}), ("_SYSTEM_BASELINES", {})):
        monkeypatch.setattr(proof, name, value)


@pytest.fixture
def fabricated(tmp_path, monkeypatch):
    """Only new-owned I/O seams vary; original file and collector code executes."""
    monkeypatch.chdir(tmp_path); monkeypatch.setattr(proof, "ROOT", tmp_path)
    (tmp_path / proof.PARENT).mkdir(parents=True, mode=0o700)
    for name in proof.CODE_FILES:
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# EXPLICIT FABRICATED COMMITTED CODE\n")
    h = SimpleNamespace(root=tmp_path, events=[], processes=[], volumes=[], status=0, raw=None,
        wait_error=None, terminal_callback=None, named_callback=None, close_callback=None,
        output_callback=None, guard_callback=None)
    master, slave = os.openpty()
    h.master, h.slave = master, slave
    h.observer = {"nonce": "c" * 32, "terminal": list(proof.startup._tty_pin(slave)),
        "slave_path": os.ttyname(slave)}
    monkeypatch.setattr(proof, "_observer_fd", lambda: slave)
    def guard(head, remote):
        assert (head, remote) == (HEAD, REMOTE)
        if h.guard_callback is not None: h.guard_callback()
    def git(arguments):
        assert type(arguments) is list and len(arguments) == 2 and arguments[0] == "show"
        prefix, separator, name = arguments[1].partition(":")
        assert separator and prefix == HEAD and name in proof.CODE_FILES
        return (tmp_path / name).read_bytes()
    monkeypatch.setattr(proof, "_guard", guard); monkeypatch.setattr(proof, "_git", git)

    class FabricatedDomain:
        """Explicit ordinary-temp-volume seam; never an actual native witness."""
        def __init__(self, clock):
            h.events.append("new-domain")
            self.clock, self.fds = clock, []
            self.directory = proof._Directory(proof.DOMAIN, create=True)
            self.path = self.directory.path; self.mount = self.path / "mount"
            self.image = self.path / "backing.sparseimage"; self.image.write_bytes(b"FABRICATED_IMAGE_IDENTITY")
            self.image.chmod(0o600); self.backing_pin = proof.native._backing(self.image.lstat())
            self.mount.mkdir(mode=0o700)
            self.mount_fd = os.open(self.mount, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fds.append(self.mount_fd)
            (self.mount / "main").mkdir(mode=0o700)
            self.main_fd = os.open(self.mount / "main", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fds.append(self.main_fd); self.main_pin = proof._stamp(os.fstat(self.main_fd))
            self.system_pin = None
            self.origins = {role: plistlib.dumps({"named_fabricated_native": role})
                for role in ("before", "create", "attach", "initial")}
            h.volumes.append(self)
        def check(self):
            self.directory.check(); self.clock.check()
            proof._same(proof._stamp(os.fstat(self.main_fd)), self.main_pin)
            proof._same(proof._stamp((self.mount / "main").lstat()), self.main_pin)
            assert not os.listdir(self.main_fd)
        def outputs(self):
            self.check(); path = self.mount / "proof"; path.mkdir(mode=0o700)
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); self.fds.append(fd)
            self.output = proof._Files(fd, self.mount_fd, path, self.check, proof.ROLES)
            if h.output_callback is not None: h.output_callback(self.output)
            return self.output
        def terminal(self):
            self.check(); self.origins["terminal"] = plistlib.dumps({"named_fabricated_native": "terminal"})
            if h.terminal_callback is not None: h.terminal_callback(self)
        def inventory(self):
            self.check(); return {"explicit_fabricated_native_inventory": True}
        def named(self):
            self.directory.named()
            proof._same(proof._stamp((self.mount / "main").lstat()), self.main_pin)
            assert not os.listdir(self.mount / "main")
            if h.named_callback is not None: h.named_callback(self)
        def close(self):
            proof._drain(self.fds); self.directory.close()
            if h.close_callback is not None: h.close_callback(self)
    monkeypatch.setattr(proof, "_new_domain", FabricatedDomain)
    def launch(head, remote):
        assert (head, remote) == (HEAD, REMOTE)
        h.events.append("worker-launched")
        raw = h.raw if h.raw is not None else b"".join(canonical_json(proof.worker._worker_line(stage, 4321, os.getpid())).encode()
            + b"\n" for stage in ("entered", "completed"))
        read_fd, write_fd = os.pipe(); os.write(write_fd, raw); os.close(write_fd)
        class Child:
            pid = 4321
            def __init__(self): self.stdout = os.fdopen(read_fd, "rb", buffering=0); self.waits = []
            def wait(self, *, timeout):
                self.waits.append(timeout)
                if h.wait_error is not None: raise h.wait_error
                return h.status
        child = Child(); h.processes.append(child); return child
    monkeypatch.setattr(proof, "_launch_worker", launch)
    monkeypatch.setattr(proof, "POLICY_SHA256", hash_payload(proof.policy()))
    h.prepare = lambda: proof.prepare_bootstrap(HEAD, REMOTE, h.observer)["spec_sha256"]
    h.produce = lambda digest: proof.run_registered(HEAD, REMOTE, digest, h.observer)
    try: yield h
    finally:
        # Test-only drain of this fixture's retained unknown handles, never a
        # production disposal/recovery path or another scope's global reset.
        for state in proof._HELD:
            for name in ("outputs", "volume", "code", "config", "directory", "config_directory", "reporter"):
                obj = state.get(name)
                if obj is not None:
                    try: obj.close()
                    except BaseException: pass
        for child in h.processes:
            if not child.stdout.closed: child.stdout.close()
            proof.worker._CHILDREN.pop(child, None); proof.worker._WAITS.pop(child, None)
        os.close(master); os.close(slave)


@pytest.fixture
def genuine_domain(fabricated, monkeypatch):
    """Original DomainVolume lifecycle with explicitly FABRICATED native facts.

    There is no image command, APFS mount, root-owned directory or device node.
    Temporary files, descriptors, exclusive creation and original Python
    constructor/check/output methods are real. Only mounted-device/native/root
    metadata is projected at the syscall/native boundary.
    """
    h = fabricated
    h.native_calls, h.system_changes, h.system_reads = [], {}, 0
    h.root_changes = {}
    h.native_callback = h.native_transform = h.before_outputs = h.before_system = None
    h.attached = False
    h.include_system = True
    h.domain_path = h.root / proof.PARENT / proof.DOMAIN
    h.mount_path = h.domain_path / "mount"
    h.image_path = h.domain_path / "backing.sparseimage"
    actual_open, actual_dup, actual_fstat = os.open, os.dup, os.fstat
    actual_stat, actual_lstat = os.stat, os.lstat
    fd_paths = {}
    fake_device = actual_stat(h.root).st_dev + 987654321
    def full_path(path, dir_fd=None):
        if isinstance(path, int): return fd_paths.get(path, (None, False))[0]
        value = Path(path)
        if value.is_absolute(): return value
        parent = fd_paths.get(dir_fd, (h.root, False))[0] if dir_fd is not None else Path.cwd()
        return parent / value
    def mounted(path):
        return path is not None and (path == h.mount_path or h.mount_path in path.parents)
    def projected(info, path, is_mounted):
        values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
        if is_mounted: values["st_dev"] = fake_device
        if path == h.mount_path and is_mounted: values.update(h.root_changes)
        if path == h.mount_path / ".fseventsd" and is_mounted:
            h.system_reads += 1
            if h.before_system is not None: h.before_system()
            values["st_uid"] = 0  # Explicit fabricated root-ownership/native fact.
            values.update(h.system_changes)
        return SimpleNamespace(**values)
    def open_file(path, flags, mode=0o777, *, dir_fd=None):
        fd = actual_open(path, flags, mode, dir_fd=dir_fd)
        resolved = full_path(path, dir_fd)
        fd_paths[fd] = (resolved, h.attached and mounted(resolved))
        return fd
    def duplicate(fd):
        result = actual_dup(fd)
        if fd in fd_paths: fd_paths[result] = fd_paths[fd]
        return result
    def fstat(fd):
        path, on_mount = fd_paths.get(fd, (None, False))
        return projected(actual_fstat(fd), path, on_mount)
    def stat_path(path, *, dir_fd=None, follow_symlinks=True):
        resolved = full_path(path, dir_fd)
        return projected(actual_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks), resolved,
            h.attached and mounted(resolved))
    def lstat_path(path, *, dir_fd=None):
        resolved = full_path(path, dir_fd)
        return projected(actual_lstat(path, dir_fd=dir_fd), resolved, h.attached and mounted(resolved))
    monkeypatch.setattr(os, "open", open_file); monkeypatch.setattr(os, "dup", duplicate)
    monkeypatch.setattr(os, "fstat", fstat); monkeypatch.setattr(os, "stat", stat_path)
    monkeypatch.setattr(os, "lstat", lstat_path)
    monkeypatch.setattr(proof, "_platform", lambda: None)
    def statfs(fd):
        on_mount = fd_paths.get(fd, (None, False))[1]
        return {"bsize": 4096, "blocks": 2 ** 21, "bavail": 2 ** 21 if on_mount else 2 ** 24,
            "fsid": (123, 456), "owner": os.getuid(), "flags": proof.native.MNT_LOCAL | proof.native.MNT_DONTBROWSE,
            "flags_ext": 0, "type": 26, "subtype": 0, "fstype": "apfs" if on_mount else "explicit_fake_host",
            "mounted_on": str(h.mount_path) if on_mount else str(h.root),
            "mounted_from": "/dev/disk987s1" if on_mount else "/dev/explicit_fake_host"}
    monkeypatch.setattr(proof, "_native_statfs", statfs)
    monkeypatch.setattr(proof, "_device_node", lambda device, dev: ("explicit_fake_node", device, dev))
    def command(arguments, timeout):
        h.native_calls.append(tuple(arguments))
        assert arguments[0] == proof.native.HDIUTIL and 0 < timeout <= proof.COMMAND_SECONDS
        if h.native_callback is not None: h.native_callback(arguments, timeout)
        verb = arguments[1]
        entities = [{"dev-entry": "/dev/disk987s1", "content-hint": "Apple_APFS", "volume-kind": "apfs", "mount-point": str(h.mount_path)}]
        if verb == "create":
            assert not h.attached and arguments[-1] == str(h.image_path)
            h.image_path.write_bytes(b"EXPLICIT FABRICATED BACKING CONTENTS")
            raw = plistlib.dumps([str(h.image_path)])
        elif verb == "attach":
            assert not h.attached
            if h.include_system: (h.mount_path / ".fseventsd").mkdir(mode=0o700)
            h.attached = True
            raw = plistlib.dumps({"system-entities": entities})
        else:
            assert verb == "info"
            raw = plistlib.dumps({"images": [{"image-path": str(h.image_path), "system-entities": entities}] if h.attached else []})
        result = subprocess.CompletedProcess(arguments, 0, raw, b"")
        return h.native_transform(result) if h.native_transform is not None else result
    monkeypatch.setattr(proof, "_native_command", command)
    def create(clock):
        # Test retention is not production preservation: tests separately
        # require the driver's exact issued creation state and original FDs.
        volume = object.__new__(proof._DomainVolume); h.volumes.append(volume)
        proof._DomainVolume.__init__(volume, clock)
        original = volume.outputs
        def outputs():
            if h.before_outputs is not None: h.before_outputs(volume)
            result = original(); volume.output = result
            if h.output_callback is not None: h.output_callback(result)
            return result
        volume.outputs = outputs
        return volume
    monkeypatch.setattr(proof, "_new_domain", create)
    h.create_domain = lambda: create(proof._Clock())
    try: yield h
    finally:
        for volume in h.volumes:
            # Test-only closure of this fixture's original, possibly held
            # carrier descriptors; never a production recovery/disposal path.
            state = proof._CREATION_STATES.get(volume)
            if state is not None and state["carrier"] is not None:
                try: state["carrier"].close()
                except BaseException: pass
            try: volume.close()
            except BaseException: pass


@pytest.fixture
def coordinator(fabricated, monkeypatch):
    """Coordinator lifecycle seam, explicitly NOT original APFS requalification.

The launchd boundary emits genuine CompletedProcess records parsed by the
original new query issuer. Bootstrap, PTY observation, inner wait and producer
controls are real; only the independent APFS reader is fabricated.
"""
    h = fabricated; h.loaded = h.started = False; h.kernel_exit = 0; h.kernel_pending = False
    h.reader_event = None; h.reader_count = 0; h.kernel_calls = []; h.observation_suffix = b""; h.start_failure = None
    h.pty_writer = None
    def kernel_raw():
        lines = [proof._target() + " = {", "\tpath = " + str(h.root / proof.PARENT / proof.BOOTSTRAP / "job.plist"),
            "\tstate = not running", "\truns = " + str(int(h.started)), "\tactive count = 0"]
        lines.append("\tlast exit code = " + ("(never exited)" if not h.started or h.kernel_pending else str(h.kernel_exit)))
        return ("\n".join(lines) + "\n}\n").encode()
    def launch(role):
        assert role in ("query", "load", "start"); h.kernel_calls.append(role)
        if role == "query":
            return subprocess.CompletedProcess([proof.LAUNCHCTL, "print", proof._target()], 0 if h.loaded else 113,
                kernel_raw() if h.loaded else b"", b"")
        if role == "load":
            assert h.loaded is False; h.loaded = True
            return subprocess.CompletedProcess([proof.LAUNCHCTL, "bootstrap", "gui/" + str(os.getuid()),
                str(h.root / proof.PARENT / proof.BOOTSTRAP / "job.plist")], 0, b"", b"")
        assert h.loaded and not h.started; h.started = True
        if h.start_failure == "timeout": raise TimeoutError()
        if h.start_failure in ("empty", "malformed"):
            return subprocess.CompletedProcess([proof.LAUNCHCTL, "kickstart", "-p", proof._target()], 0,
                b"" if h.start_failure == "empty" else b"PID_NOT_AUTHENTICATED", b"")
        path = h.root / proof.PARENT / proof.BOOTSTRAP / "launch.spec.json"
        raw = path.read_bytes(); spec = json.loads(raw); digest = hash_bytes(raw)
        h.pty_writer = os.open(spec["observer"]["slave_path"], os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_NOCTTY", 0))
        result = proof.run_registered(HEAD, REMOTE, digest, spec["observer"])
        monkeypatch.setattr(proof, "_observer_fd", lambda: h.pty_writer)
        proof._Observer(spec["observer"], digest).emit(result=result)
        if h.observation_suffix: os.write(h.pty_writer, h.observation_suffix)
        return subprocess.CompletedProcess([proof.LAUNCHCTL, "kickstart", "-p", proof._target()], 0,
            str(os.getpid()).encode() + b"\n", b"")
    monkeypatch.setattr(proof, "_launch_service", launch)
    OriginalRead = proof._OriginalRead
    class FabricatedOriginalRead(OriginalRead):
        def __init__(self, head, remote, digest, observer, pid, marker):
            h.reader_count += 1
            assert (head, remote, pid) == (HEAD, REMOTE, os.getpid())
            self.head, self.remote, self.digest, self.observer, self.producer_pid = head, remote, digest, observer, pid
            volume = h.volumes[-1]; outputs = volume.output
            self.path, self.mount, self.image, self.proof_path = volume.path, volume.mount, volume.image, outputs.path
            self.directory = proof._Directory(proof.DOMAIN, create=False)
            self.inventory = json.loads((self.proof_path / proof.INVENTORY_ROLE).read_bytes())
            self.fds, self.files = [], []
            self.mount_fd = os.open(self.mount, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); self.fds.append(self.mount_fd)
            self.proof_fd = os.open(self.proof_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); self.fds.append(self.proof_fd)
            self.backing_fd = os.open(self.image, os.O_RDONLY | os.O_NOFOLLOW); self.fds.append(self.backing_fd)
            self.main_fd = os.open(self.mount / "main", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); self.fds.append(self.main_fd)
            self.anchors = [(self.path, self.directory.fd, proof._dir(os.fstat(self.directory.fd), True)),
                (self.mount, self.mount_fd, proof._dir(os.fstat(self.mount_fd), True)),
                (self.proof_path, self.proof_fd, proof._dir(os.fstat(self.proof_fd), True))]
            self.native = {"named_fabricated_APFS_boundary": True, "backing_original_identity": volume.backing_pin,
                "main_original_seal": volume.main_pin, "system_original_metadata": volume.system_pin,
                "fresh_root_creation_identity": proof.native._fresh_root_identity(os.fstat(self.mount_fd)),
                "mount_original_identity": proof._dir(os.fstat(self.mount_fd), True),
                "domain_original_identity": proof._dir(os.fstat(self.directory.fd), True)}
            self.device = "fabricated_device"
            self.attach_entities = ()
            self.marker = marker
            for name, (unused, unused_pin, seal, raw) in outputs.originals.items():
                fd = os.open(self.proof_path / name, os.O_RDONLY | os.O_NOFOLLOW); self.fds.append(fd)
                proof._same(proof._stamp(os.fstat(fd)), seal)
                self.files.append((name, fd, seal, raw))
            self.audit_local()
            if h.reader_event: h.reader_event("entry", self)
        def native_audit(self):
            self._native_originals(self.mount_fd, self.backing_fd, self.main_fd, self.directory.fd)
        def _native_originals(self, mount_fd, backing_fd, main_fd, domain_fd):
            # APFS/device syscalls alone are fabricated. Every local backing,
            # root roster, system and main ORIGINAL pin comparison is real.
            proof.require(proof.native._backing(os.fstat(backing_fd))
                == proof.native._backing(self.image.lstat()) == tuple(self.native["backing_original_identity"]), "supervision_original")
            proof.require(set(os.listdir(domain_fd)) == {"backing.sparseimage", "mount"}, "supervision_original")
            proof.require(set(os.listdir(mount_fd)) == {"proof", "main"}, "supervision_original")
            proof._same(proof._stamp(os.fstat(main_fd)), tuple(self.native["main_original_seal"]))
            proof._same(proof._stamp((self.mount / "main").lstat()), tuple(self.native["main_original_seal"]))
            proof.require(not os.listdir(main_fd), "supervision_original")
        def current_association(self, clock):
            clock.check(); self.native_audit()
            if h.reader_event: h.reader_event("native", self)
        def audit_local(self):
            OriginalRead.audit_local(self)
            if h.reader_event: h.reader_event("audit", self)
        def close(self):
            OriginalRead.close(self)
            if h.reader_event: h.reader_event("close", self)
        def named(self):
            OriginalRead.named(self)
            if h.reader_event: h.reader_event("named", self)
    monkeypatch.setattr(proof, "_OriginalRead", FabricatedOriginalRead)
    try: yield h
    finally:
        if h.pty_writer is not None: os.close(h.pty_writer)


def test_policy_is_new_scope_with_zero_source_authority():
    assert proof.MODULE == "scripts.prove_short_interest_native_supervision"
    assert proof.CODE_FILES == (*proof.old.CODE_FILES, proof.startup.DRIVER, proof.DRIVER)
    assert len(proof.CODE_FILES) == len(set(proof.CODE_FILES)) == 7
    assert proof._COLLECT is proof.worker._collect
    a = proof.authority()
    assert a["source_free_native_supervision_only"] is True
    assert all(a[key] is False for key in ("source_admitted", "source_dispatch_authority", "budget_release_authority",
        "old_V1_admitted", "durable_Main_receipt", "ready_for_backtest", "QC_or_Safari"))
    assert all(type(a[key]) is int and a[key] == 0 for key in
        ("provider_HTTP", "credential_reads", "source_STARTs", "source_bytes", "new_source_claims", "qc_attempts"))


def test_genuine_domain_constructor_and_outputs_keep_all_original_checks(genuine_domain):
    h = genuine_domain; early = []
    def before_system():
        state = proof._CREATION_STATES[h.volumes[0]]
        if not early:
            assert state["system_baseline"] is None and state["carrier"] is not None
            assert state["carrier"].fds and all(os.fstat(fd).st_ino > 0 for fd in state["carrier"].fds)
        early.append(state)
    h.before_system = before_system
    volume = h.create_domain()
    assert type(volume) is proof._DomainVolume
    assert [row[1] for row in h.native_calls] == ["info", "create", "attach", "info"]
    assert volume.system == proof._stamp(os.stat(".fseventsd", dir_fd=volume.mount_fd, follow_symlinks=False))[:6]
    assert h.system_reads >= 2 and volume.system[2] == 0
    assert early and all(state is proof._CREATION_STATES[volume] for state in early)
    volume.check()
    files = volume.outputs()
    assert type(files) is proof._Files and files.path == h.mount_path / "proof"
    assert proof._PRODUCERS == proof._CLOSED == {} and h.processes == []


def test_genuine_domain_producer_closes_empty_carrier_but_remains_provisional(genuine_domain):
    h = genuine_domain; result = h.produce(h.prepare())
    assert type(result) is proof.ProducerObservation
    volume = h.volumes[0]; state = proof._CREATION_STATES[volume]
    assert state["failure"] is None and state["carrier"].closed and state["carrier"].originals == {}
    assert state["carrier"].attempted == set() and proof._CREATION_MANIFESTS == {}
    assert result.public_summary()["actual_child_exit"] == 0
    assert result.public_summary()["authority"] == proof.authority()
    assert result.public_summary()["kernel_exit_attested"] is False
    assert len(proof._PRODUCERS) == 1 and proof._CLOSED == {}


@pytest.mark.parametrize("field,value,relation,projected_field", [("st_mode", stat.S_IFREG | 0o700, "system_directory_type", "mode"),
    ("st_mode", stat.S_IFLNK | 0o700, "system_directory_type", "mode"),
    ("st_mode", stat.S_IFDIR | 0o600, "system_directory_mode", "mode"),
    ("st_mode", stat.S_IFDIR | 0o750, "system_directory_mode", "mode"),
    ("st_uid", 12345, "system_directory_uid", "uid"), ("st_gid", -1, "system_directory_gid", "gid"),
    ("st_dev", -1, "system_directory_dev", "dev")])
def test_original_system_current_protection_predicates_remain_mandatory(genuine_domain, field, value, relation, projected_field):
    h = genuine_domain; volume = h.create_domain(); original = volume.system
    h.system_changes[field] = value
    with pytest.raises((proof.SupervisionRefusal, proof.old.NativeProofRefusal)) as caught:
        volume._system()
    public = proof.failure_summary(caught.value)
    assert public["comparison_relation"] == relation and public["mismatching_fields"] == [projected_field]
    assert public["creation_manifest_sha256"] is None
    assert volume.system is original
    assert proof._PRODUCERS == proof._CLOSED == {} and h.processes == []


@pytest.mark.parametrize("field,value,reads", [("st_mode", stat.S_IFREG | 0o700, 0),
    ("st_mode", stat.S_IFDIR | 0o750, 0), ("st_uid", 12345, 0), ("st_gid", -1, 1), ("st_dev", -1, 2)])
def test_system_telemetry_preserves_original_short_circuit_reference_order(genuine_domain, monkeypatch, field, value, reads):
    h = genuine_domain; volume = h.create_domain()
    h.system_changes[field] = value
    original = os.fstat; references = []
    def fstat(fd):
        if fd == volume.mount_fd: references.append(fd)
        return original(fd)
    monkeypatch.setattr(os, "fstat", fstat)
    with pytest.raises(proof.SupervisionRefusal): volume._system()
    assert len(references) == reads


@pytest.mark.parametrize("field,index", [("st_ino", 1), ("st_nlink", 5)])
@pytest.mark.parametrize("entry", ["check", "named"])
def test_original_system_identity_and_link_count_never_rebaseline_or_gain_exceptions(genuine_domain, field, index, entry):
    h = genuine_domain; volume = h.create_domain(); original = volume.system
    volume.outputs()  # named() also requires the original proof directory.
    h.system_changes[field] = original[index] + 1
    assert volume._system()[index] != original[index]  # Current protection still passes.
    with pytest.raises((proof.SupervisionRefusal, proof.old.NativeProofRefusal)) as caught:
        getattr(volume, entry)()
    public = proof.failure_summary(caught.value)
    assert public["comparison_relation"] == ("system_original_metadata" if entry == "check" else "system_named_original_metadata")
    assert public["mismatching_fields"] == [proof.old._STAMP_NAMES[index]]
    assert public["creation_manifest_sha256"] is None
    assert volume.system is original
    assert proof._PRODUCERS == proof._CLOSED == {} and h.processes == []


@pytest.mark.parametrize("field", ["st_size", "st_mtime_ns", "st_ctime_ns"])
def test_system_original_identity_keeps_the_existing_six_field_contract(genuine_domain, field):
    h = genuine_domain; volume = h.create_domain(); original = volume.system
    current = os.stat(".fseventsd", dir_fd=volume.mount_fd, follow_symlinks=False)
    h.system_changes[field] = getattr(current, field) + 1
    assert volume._system() == original
    volume.check()
    assert volume.system is original


@pytest.mark.parametrize("entry", ["check", "named"])
@pytest.mark.parametrize("replace", ["instance", "state", "both"])
def test_original_system_baseline_cannot_be_replaced_to_adopt_current_link_drift(genuine_domain, entry, replace):
    h = genuine_domain; volume = h.create_domain(); volume.outputs()
    state = proof._CREATION_STATES[volume]
    original = volume.system
    h.system_changes["st_nlink"] = original[5] + 1
    changed = volume._system()
    if replace in ("instance", "both"): volume.system = changed
    if replace in ("state", "both"): state["system_baseline"] = changed
    with pytest.raises((proof.SupervisionRefusal, proof.old.NativeProofRefusal)):
        getattr(volume, entry)()
    assert proof._SYSTEM_BASELINES[volume][1] is original
    assert proof._PRODUCERS == proof._CLOSED == {}


@pytest.mark.parametrize("field", ["st_mode", "st_uid", "st_gid", "st_dev", "st_ino"])
def test_genuine_domain_root_protection_and_original_identity_still_precede_system_checks(genuine_domain, field):
    h = genuine_domain; volume = h.create_domain()
    current = os.fstat(volume.mount_fd)
    h.root_changes[field] = (stat.S_IFDIR | 0o755) if field == "st_mode" else getattr(current, field) + 1
    before_system = h.system_reads
    with pytest.raises((proof.SupervisionRefusal, proof.old.NativeProofRefusal, proof.native.IsolatedVolumeRefusal)):
        volume.check()
    assert h.system_reads == before_system
    assert proof._PRODUCERS == proof._CLOSED == {} and h.processes == []


def test_system_relation_requires_original_created_instance_and_original_error(genuine_domain):
    h = genuine_domain; volume = h.create_domain()
    h.system_changes["st_uid"] = 12345
    with pytest.raises((proof.SupervisionRefusal, proof.old.NativeProofRefusal)) as genuine:
        volume._system()
    assert proof.failure_summary(genuine.value)["comparison_relation"] == "system_directory_uid"
    clone = type(genuine.value)(*BaseException.args.__get__(genuine.value, BaseException))
    copied = proof.failure_summary(clone)
    assert copied["comparison_relation"] is copied["creation_manifest_sha256"] is None
    assert copied["mismatching_fields"] == []
    unissued = object.__new__(proof._DomainVolume)
    unissued.mount_fd = volume.mount_fd
    with pytest.raises((proof.SupervisionRefusal, proof.old.NativeProofRefusal)) as forged:
        unissued._system()
    public = proof.failure_summary(forged.value)
    assert public["comparison_relation"] is public["creation_manifest_sha256"] is None
    assert public["mismatching_fields"] == []


@pytest.mark.parametrize("kind", ["predicate", "original_comparison"])
def test_outside_system_helper_call_cannot_claim_original_system_relation(genuine_domain, kind):
    h = genuine_domain; volume = h.create_domain()
    with pytest.raises(proof.SupervisionRefusal) as caught:
        if kind == "predicate": proof._system_require(volume, False, "system_directory_uid", {})
        else: proof._compared_system(volume, (1,) * 6, (2,) * 6, "system_original_metadata")
    public = proof.failure_summary(caught.value)
    assert public["comparison_relation"] is public["creation_manifest_sha256"] is None
    assert public["mismatching_fields"] == []


@pytest.mark.parametrize("case,relation,field", [("first_system", "system_directory_uid", "uid"),
    ("outputs_predicate", "system_directory_mode", "mode"),
    ("outputs_original", "system_original_metadata", "nlink")])
def test_original_preoutput_failure_preserves_private_native_and_system_origins_before_any_worker(genuine_domain, monkeypatch, case, relation, field):
    h = genuine_domain
    held = _bounded_test_hold(monkeypatch)
    expected_baseline = []
    if case == "first_system": h.system_changes["st_uid"] = 12345
    else:
        def before_outputs(volume):
            expected_baseline.append(volume.system)
            if case == "outputs_predicate": h.system_changes["st_mode"] = stat.S_IFDIR | 0o750
            else: h.system_changes["st_nlink"] = volume.system[5] + 1
        h.before_outputs = before_outputs
    original_publish = proof._CreationCarrier.publish
    observed = []
    def publish(carrier, name, raw):
        state = carrier.state
        assert proof._CREATION_STATES[state["volume"]] is state
        assert proof._CREATION_FAILURES[id(state["failure"])][1] is state
        assert state["trace"] is not None
        assert h.processes == [] and proof._PRODUCERS == proof._CLOSED == {}
        observed.append(name)
        return original_publish(carrier, name, raw)
    monkeypatch.setattr(proof._CreationCarrier, "publish", publish)
    with pytest.raises((proof.SupervisionRefusal, proof.old.NativeProofRefusal)) as caught:
        h.produce(h.prepare())
    assert held == [] and observed
    volume = h.volumes[0]; state = proof._CREATION_STATES[volume]; carrier = state["carrier"]
    assert state["failure"] is caught.value and state["trace"] is not None
    assert list(state["commands"]) == ["before", "create", "attach", "initial"]
    assert carrier.closed and carrier.originals
    assert h.processes == [] and proof._PRODUCERS == proof._CLOSED == {}
    assert not (h.mount_path / "proof").exists()
    assert not (h.mount_path / "run.started.json").exists()
    system = json.loads((carrier.path / proof.CREATION_SYSTEM_ROLE).read_bytes())
    if case == "first_system":
        assert state["system_baseline"] is None and system["original_baseline"] is None
        assert system["baseline_established"] is False
    else:
        assert state["system_baseline"] is expected_baseline[0]
        assert system["original_baseline"] == list(expected_baseline[0])
        assert system["baseline_established"] is True
    assert system["present_observations"] and state["system_observations"]
    for role, command in state["commands"].items():
        name = "creation.native." + role + ".private.plist"
        assert (carrier.path / name).read_bytes() == command["stdout"]
    for name, (unused, seal, raw) in carrier.originals.items():
        assert (carrier.path / name).read_bytes() == raw
        assert proof._stamp((carrier.path / name).lstat()) == seal
        assert seal[4:6] == (0o600, 1)
    public = proof.failure_summary(caught.value)
    assert public["comparison_relation"] == relation and public["mismatching_fields"] == [field]
    receipt = proof._CREATION_MANIFESTS[id(caught.value)]
    assert receipt[0] is caught.value and receipt[1] is state and receipt[2] is carrier
    assert receipt[3] is state["manifest_raw"]
    assert public["creation_manifest_sha256"] == hash_bytes(receipt[3]) == receipt[4]
    assert public["creation_manifest_sha256"] != hash_payload(json.loads((h.root / proof.PARENT / proof.BOOTSTRAP / "launch.spec.json").read_bytes())["code_manifest"])
    assert str(h.root) not in canonical_json(public)


def test_direct_constructor_failure_retains_original_state_but_cannot_issue_producer_manifest(genuine_domain, monkeypatch):
    h = genuine_domain; h.system_changes["st_uid"] = 12345
    _bounded_test_hold(monkeypatch)
    with pytest.raises((proof.SupervisionRefusal, proof.old.NativeProofRefusal)) as caught:
        h.create_domain()
    volume = h.volumes[0]; state = proof._CREATION_STATES[volume]
    assert proof._CREATION_FAILURES[id(caught.value)][1] is state
    assert state["failure"] is caught.value and state["system_baseline"] is None
    assert state["commands"] and state["system_observations"]
    assert state["operation"] is None
    assert proof.failure_summary(caught.value)["creation_manifest_sha256"] is None
    assert proof._CREATION_MANIFESTS == proof._PRODUCERS == proof._CLOSED == {}


def test_creation_state_exists_before_platform_or_any_directory_effect(genuine_domain, monkeypatch):
    h = genuine_domain; held = _bounded_test_hold(monkeypatch); observed = []
    def refused():
        assert len(proof._CREATION_STATES) == len(h.volumes) == 1
        state = proof._CREATION_STATES[h.volumes[0]]
        assert state["commands"] == {} and state["system_observations"] == []
        assert state["system_baseline"] is state["carrier"] is None
        assert state["volume"].directory is None and not h.domain_path.exists()
        observed.append(state)
        raise OSError(38, "fabricated pre-effect platform refusal")
    monkeypatch.setattr(proof, "_platform", refused)
    with pytest.raises(OSError) as caught: h.produce(h.prepare())
    assert len(observed) == len(held) == 1
    state = observed[0]
    assert state["failure"] is caught.value and state["trace"] is not None
    assert proof._CREATION_FAILURES[id(caught.value)][1] is state
    assert proof.failure_summary(caught.value)["creation_manifest_sha256"] is None
    assert h.native_calls == h.processes == [] and not h.domain_path.exists()
    assert proof._CREATION_MANIFESTS == proof._PRODUCERS == proof._CLOSED == {}


def test_native_timeout_output_is_retained_without_inventing_terminal_or_system_baseline(genuine_domain, monkeypatch):
    h = genuine_domain; held = _bounded_test_hold(monkeypatch)
    original_output = b"EXACT_GENERATED_LOCAL_TIMEOUT_BYTES"
    timeout = []
    def fail(arguments, seconds):
        if arguments[1] == "create":
            error = subprocess.TimeoutExpired(arguments, seconds, output=original_output)
            timeout.append(error)
            raise error
    h.native_callback = fail
    with pytest.raises(subprocess.TimeoutExpired) as caught: h.produce(h.prepare())
    assert caught.value is timeout[0] and len(held) == 1
    volume = h.volumes[0]; state = proof._CREATION_STATES[volume]
    assert state["failure"] is caught.value and state["trace"] is not None
    assert state["system_baseline"] is None and state["system_observations"] == []
    assert state["commands"]["create"]["stdout"] is original_output
    assert state["commands"]["create"]["known_terminal"] is False
    assert state["carrier"] is None
    assert os.fstat(volume.directory.fd).st_ino > 0
    assert h.processes == [] and proof._CREATION_MANIFESTS == proof._PRODUCERS == proof._CLOSED == {}


def test_native_output_is_strongly_retained_before_its_acceptance_size_guard(genuine_domain, monkeypatch):
    h = genuine_domain; held = _bounded_test_hold(monkeypatch)
    oversized = b"F" * (proof.MAXIMUM_NATIVE_BYTES + 1)
    def transform(result):
        result.stdout = oversized
        return result
    h.native_transform = transform
    with pytest.raises((proof.SupervisionRefusal, proof.old.NativeProofRefusal)) as caught:
        h.produce(h.prepare())
    assert len(held) == 1
    state = proof._CREATION_STATES[h.volumes[0]]
    assert state["failure"] is caught.value and state["commands"]["before"]["stdout"] is oversized
    assert state["commands"]["before"]["known_terminal"] is True
    assert state["carrier"] is state["system_baseline"] is None
    assert state["system_observations"] == []
    assert os.fstat(h.volumes[0].directory.fd).st_ino > 0
    assert proof.failure_summary(caught.value)["creation_manifest_sha256"] is None
    assert h.processes == [] and proof._CREATION_MANIFESTS == proof._PRODUCERS == proof._CLOSED == {}


@pytest.mark.parametrize("fault", ["nonzero", "bad_plist"])
def test_terminal_native_failure_after_worker_wait0_preserves_original_new_native_bytes(genuine_domain, monkeypatch, fault):
    h = genuine_domain; held = _bounded_test_hold(monkeypatch)
    terminal_raw = b"EXACT_PRIVATE_GENERATED_TERMINAL_NATIVE_BYTES"
    def transform(result):
        if len(h.native_calls) == 5:
            assert result.args[1] == "info"
            result.returncode = 2 if fault == "nonzero" else 0
            result.stdout, result.stderr = terminal_raw, None
        return result
    h.native_transform = transform
    with pytest.raises((proof.SupervisionRefusal, proof.old.NativeProofRefusal, plistlib.InvalidFileException)) as caught:
        h.produce(h.prepare())
    assert held == [] and len(h.processes) == 1 and len(h.native_calls) == 5
    child = h.processes[0]
    assert proof.worker._WAITS[child][1] == 0 and child.stdout.closed
    state = proof._CREATION_STATES[h.volumes[0]]; carrier = state["carrier"]
    assert state["failure"] is caught.value and state["commands"]["terminal"]["stdout"] is terminal_raw
    assert state["commands"]["terminal"]["known_terminal"] is True
    assert (carrier.path / "creation.native.terminal.private.plist").read_bytes() == terminal_raw
    assert proof.failure_summary(caught.value)["creation_manifest_sha256"] == hash_bytes(state["manifest_raw"])
    assert proof._PRODUCERS == proof._CLOSED == {}
    assert not (h.mount_path / "proof" / proof.MARKER_ROLE).exists()
    assert (h.mount_path / "proof" / "stdout.jsonl").read_bytes() == _two_original_lines()


def test_known_absent_system_baseline_is_distinct_from_failed_before_baseline(genuine_domain, monkeypatch):
    h = genuine_domain; h.include_system = False
    held = _bounded_test_hold(monkeypatch)
    def transform(result):
        if len(h.native_calls) == 5:
            result.returncode, result.stdout = 2, b"FIXED_LOCAL_TERMINAL_REFUSAL"
        return result
    h.native_transform = transform
    with pytest.raises(proof.SupervisionRefusal) as caught: h.produce(h.prepare())
    assert held == [] and len(h.processes) == 1
    volume = h.volumes[0]; state = proof._CREATION_STATES[volume]
    assert proof._SYSTEM_BASELINES[volume][1] is None and state["system_baseline"] is None
    system = json.loads((volume.mount / proof.CREATION_SYSTEM_ROLE).read_bytes())
    assert system["original_baseline"] is None and system["baseline_established"] is True
    assert system["present_observations"] == []
    assert proof.failure_summary(caught.value)["creation_manifest_sha256"] == hash_bytes(state["manifest_raw"])
    assert proof._PRODUCERS == proof._CLOSED == {}


def test_unknown_terminal_native_timeout_keeps_original_worker_and_all_creation_contexts(genuine_domain, monkeypatch):
    h = genuine_domain; held = _bounded_test_hold(monkeypatch)
    terminal_raw = b"EXACT_PARTIAL_TERMINAL_NATIVE_TIMEOUT_BYTES"
    def timeout(arguments, seconds):
        if len(h.native_calls) == 5: raise subprocess.TimeoutExpired(arguments, seconds, output=terminal_raw)
    h.native_callback = timeout
    with pytest.raises(subprocess.TimeoutExpired) as caught: h.produce(h.prepare())
    assert len(held) == 1 and len(h.processes) == 1 and len(h.native_calls) == 5
    child = h.processes[0]; state = proof._CREATION_STATES[h.volumes[0]]
    assert state["failure"] is caught.value and state["commands"]["terminal"]["stdout"] is terminal_raw
    assert state["commands"]["terminal"]["known_terminal"] is False
    assert proof.worker._WAITS[child][1] == 0 and child.stdout.closed is False
    assert state["carrier"].fds and os.fstat(h.volumes[0].mount_fd).st_ino > 0
    assert proof.failure_summary(caught.value)["creation_manifest_sha256"] is None
    assert proof._CREATION_MANIFESTS == proof._PRODUCERS == proof._CLOSED == {}


def test_terminal_precondition_failure_preserves_exact_not_invoked_fact_without_empty_native_output(genuine_domain, monkeypatch):
    h = genuine_domain; held = _bounded_test_hold(monkeypatch); changed = []
    def guard():
        if proof._STAGE == "terminal_code" and not changed:
            volume = h.volumes[0]
            h.system_changes["st_nlink"] = volume.system[5] + 1
            changed.append(volume)
    h.guard_callback = guard
    with pytest.raises(proof.SupervisionRefusal) as caught: h.produce(h.prepare())
    assert held == [] and len(changed) == len(h.processes) == 1 and len(h.native_calls) == 4
    child = h.processes[0]; volume = h.volumes[0]; state = proof._CREATION_STATES[volume]
    assert proof.worker._WAITS[child][1] == 0 and child.stdout.closed
    terminal = state["commands"]["terminal"]
    assert terminal["invocation_attempted"] is False and terminal["stdout"] is terminal["result"] is terminal["failure"] is None
    assert (volume, "terminal") in proof._NATIVE_PLANS and (volume, "terminal") not in proof._NATIVE_INVOCATIONS
    assert not (volume.mount / "creation.native.terminal.private.plist").exists()
    failure = json.loads((volume.mount / proof.CREATION_FAILURE_ROLE).read_bytes())
    assert failure["native_invocations"] == [{"role": role, "invocation_attempted": role != "terminal"}
        for role in ("before", "create", "attach", "initial", "terminal")]
    public = proof.failure_summary(caught.value)
    assert public["comparison_relation"] == "system_original_metadata" and public["mismatching_fields"] == ["nlink"]
    assert public["creation_manifest_sha256"] == hash_bytes(state["manifest_raw"])
    assert proof._PRODUCERS == proof._CLOSED == {}


def test_caller_false_invocation_flag_cannot_hide_original_entered_native_timeout(genuine_domain, monkeypatch):
    h = genuine_domain; held = _bounded_test_hold(monkeypatch)
    raw = b"EXACT_ENTERED_TERMINAL_TIMEOUT_BYTES"
    def timeout(arguments, seconds):
        if len(h.native_calls) == 5:
            state = proof._CREATION_STATES[h.volumes[0]]
            state["commands"]["terminal"]["invocation_attempted"] = False
            raise subprocess.TimeoutExpired(arguments, seconds, output=raw)
    h.native_callback = timeout
    with pytest.raises(subprocess.TimeoutExpired) as caught: h.produce(h.prepare())
    volume = h.volumes[0]; state = proof._CREATION_STATES[volume]
    assert len(held) == 1 and len(h.native_calls) == 5
    assert (volume, "terminal") in proof._NATIVE_INVOCATIONS
    assert state["commands"]["terminal"]["stdout"] is raw and state["failure"] is caught.value
    assert h.processes[0].stdout.closed is False and state["carrier"].fds
    assert proof.failure_summary(caught.value)["creation_manifest_sha256"] is None
    assert proof._CREATION_MANIFESTS == proof._PRODUCERS == proof._CLOSED == {}


@pytest.mark.parametrize("fault", ["partial_write", "readback", "fsync", "cleanup", "postclose_stamp"])
def test_early_creation_preservation_failure_holds_all_original_state_without_manifest_authority(genuine_domain, monkeypatch, fault):
    h = genuine_domain; h.system_changes["st_uid"] = 12345
    held = _bounded_test_hold(monkeypatch)
    original_write, original_read, original_fsync = proof._write, os.read, os.fsync
    original_volume_close, original_carrier_close = proof._DomainVolume.close, proof._CreationCarrier.close
    def carrier():
        return proof._CREATION_STATES.get(h.volumes[0], {}).get("carrier") if h.volumes else None
    with monkeypatch.context() as patch:
        if fault == "partial_write":
            def write(fd, raw):
                current = carrier()
                if current is not None and fd in current.file_fds:
                    original_write(fd, raw[:1]); raise OSError(28, "fabricated early private partial write")
                return original_write(fd, raw)
            patch.setattr(proof, "_write", write)
        elif fault == "readback":
            def read(fd, maximum):
                raw = original_read(fd, maximum); current = carrier()
                return b"X" + raw[1:] if current is not None and fd in current.file_fds and raw else raw
            patch.setattr(os, "read", read)
        elif fault == "fsync":
            def fsync(fd):
                current = carrier()
                if current is not None and fd in current.file_fds: raise OSError(5, "fabricated early private fsync")
                return original_fsync(fd)
            patch.setattr(os, "fsync", fsync)
        elif fault == "cleanup":
            def close(volume):
                state = proof._CREATION_STATES.get(volume)
                if state is not None and state["failure"] is not None: raise OSError(5, "fabricated early original cleanup")
                return original_volume_close(volume)
            patch.setattr(proof._DomainVolume, "close", close)
        else:
            def close(current):
                original_carrier_close(current)
                if current.originals:
                    name = next(iter(current.originals))
                    (current.path / name).chmod(0o600)  # Same bytes/mode; changed ORIGINAL ctime still refuses.
            patch.setattr(proof._CreationCarrier, "close", close)
        with pytest.raises((proof.SupervisionRefusal, proof.old.NativeProofRefusal)) as caught:
            h.produce(h.prepare())
        assert len(held) == 1
        state = proof._CREATION_STATES[h.volumes[0]]
        assert state["failure"] is caught.value and state["trace"] is not None
        assert state["system_baseline"] is None and state["system_observations"]
        assert list(state["commands"]) == ["before", "create", "attach", "initial"]
        assert state["carrier"] is carrier()
        if fault != "postclose_stamp":
            assert carrier().fds and all(os.fstat(fd).st_ino > 0 for fd in carrier().fds)
        assert proof.failure_summary(caught.value)["creation_manifest_sha256"] is None
        assert proof._CREATION_MANIFESTS == proof._PRODUCERS == proof._CLOSED == {} and h.processes == []


def test_pending_registration_refuses_before_owned_io(monkeypatch):
    monkeypatch.setattr(proof, "POLICY_SHA256", "PENDING")
    monkeypatch.setattr(proof, "_guard", lambda *a: pytest.fail("pending registration reached guard"))
    with pytest.raises(proof.SupervisionRefusal, match="supervision_unregistered"):
        proof.prepare_bootstrap(HEAD, REMOTE, {})


def test_capture_cli_stays_source_blocked_before_registration(monkeypatch, capsys):
    monkeypatch.setattr(proof, "registered", lambda: pytest.fail("source mode reached registration"))
    assert proof.main(["capture"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["failure"]["contract_code"] == "supervision_source_refused"
    assert result["authority"]["source_dispatch_authority"] is False


def test_kernel_never_exited_is_pending_not_zero():
    raw = (proof._target() + " = {\n\tpath = " + str(proof.ROOT / proof.PARENT / proof.BOOTSTRAP / "job.plist")
        + "\n\tstate = not running\n\truns = 0\n\tactive count = 0\n\tlast exit code = (never exited)\n}\n").encode()
    kernel = proof._kernel_metadata(raw)
    assert kernel["exit"] is None and kernel["pending"] is True
    proof._never_started(kernel)
    assert not proof._terminal(kernel)


@pytest.mark.parametrize("change", [{"runs": 0}, {"pid": 123}, {"active_count": 1}, {"state": "running"},
    {"pending": True}, {"exit": None}, {"exit": False}])
def test_terminal_kernel_needs_actual_single_inactive_integer_exit(change):
    kernel = {"state": "not running", "runs": 1, "active_count": 0, "pid": None, "exit": 0, "pending": False}
    assert proof._terminal(kernel)
    kernel.update(change)
    assert not proof._terminal(kernel)


@pytest.mark.parametrize("typ", [proof.ProducerObservation, proof.ClosedNativeSupervision])
def test_result_types_cannot_be_caller_constructed(typ):
    with pytest.raises(proof.SupervisionRefusal, match="supervision_factory"): typ()
    forged = object.__new__(typ); forged._anchor = ()
    with pytest.raises(proof.SupervisionRefusal, match="supervision_factory"): forged.public_summary()


def test_prepare_authenticates_two_original_new_configuration_files(fabricated):
    h = fabricated; digest = h.prepare()
    path = h.root / proof.PARENT / proof.BOOTSTRAP
    assert set(os.listdir(path)) == {"launch.spec.json", "job.plist"}
    assert hash_bytes((path / "launch.spec.json").read_bytes()) == digest
    assert h.events == []
    job = plistlib.loads((path / "job.plist").read_bytes())
    assert job["Label"] == proof.LABEL and job["RunAtLoad"] is False and job["KeepAlive"] is False
    assert job["StandardOutPath"] == "/dev/null" and job["StandardErrorPath"] == h.observer["slave_path"]
    assert not any("status" in name for name in os.listdir(path))


def test_prepare_existing_namespace_is_spent_not_adopted(fabricated):
    h = fabricated; h.prepare()
    with pytest.raises(proof.SupervisionRefusal, match="exists"): h.prepare()
    assert h.events == []


def test_wrong_digest_refuses_before_domain_creation(fabricated):
    h = fabricated; h.prepare()
    with pytest.raises(proof.SupervisionRefusal): h.produce("d" * 64)
    assert h.events == []


def test_genuine_producer_is_only_provisional_even_after_original_worker_wait0(fabricated):
    h = fabricated; result = h.produce(h.prepare())
    assert type(result) is proof.ProducerObservation
    public = result.public_summary()
    assert public["status"] == "producer_checks_complete_provisional"
    assert public["actual_child_exit"] == 0 and public["kernel_exit_attested"] is False
    assert public["durable_Main_receipt"] is False
    assert proof._CLOSED == {}
    child = h.processes[0]
    assert len(child.waits) == 1 and 0 < child.waits[0] <= proof.worker.MAXIMUM_SECONDS
    assert proof.worker._WAITS[child][0] is proof.worker._CHILDREN[child]
    outputs = h.volumes[0].output
    assert set(os.listdir(outputs.path)) == proof.POSITIVE_ROLES
    marker_raw = (outputs.path / proof.MARKER_ROLE).read_bytes()
    assert public["marker"] == {"sha256": hash_bytes(marker_raw), "stamp": list(proof._stamp((outputs.path / proof.MARKER_ROLE).lstat()))}
    inventory = json.loads((outputs.path / proof.INVENTORY_ROLE).read_bytes())
    assert all(len(row["original_stamp"]) == 9 for row in inventory["controls"])
    assert all(row["sha256"] == hash_bytes((outputs.path / row["name"]).read_bytes()) for row in inventory["controls"])


def test_producer_public_payload_is_a_copy_and_anchor_cannot_be_replaced(fabricated):
    h = fabricated; result = h.produce(h.prepare()); public = result.public_summary()
    public["marker"]["stamp"][0] += 1; public["authority"]["source_admitted"] = True
    assert result.public_summary()["authority"]["source_admitted"] is False
    result._anchor = tuple(list(result._anchor))
    with pytest.raises(proof.SupervisionRefusal, match="supervision_factory"): result.public_summary()


@pytest.mark.parametrize("name", ["launch.spec.json", "job.plist"])
def test_bootstrap_bytes_changed_cannot_create_domain(fabricated, name):
    h = fabricated; digest = h.prepare(); path = h.root / proof.PARENT / proof.BOOTSTRAP / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(proof.SupervisionRefusal): h.produce(digest)
    assert h.events == []


@pytest.mark.parametrize("mutation", ["bytes", "protection", "hardlink", "sibling"])
def test_new_files_retained_original_integrity(mutation, tmp_path):
    path = tmp_path / "owned"; path.mkdir(mode=0o700)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    parent = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    files = proof._Files(fd, parent, path, lambda: None, {"run.started.json"})
    try:
        files.write("run.started.json", b"original")
        target = path / "run.started.json"
        if mutation == "bytes": target.write_bytes(b"changed!")
        elif mutation == "protection": target.chmod(0o640)
        elif mutation == "hardlink": os.link(target, tmp_path / "linked")
        else: (path / "foreign").write_bytes(b"negative")
        with pytest.raises((proof.SupervisionRefusal, proof.old.NativeProofRefusal)): files.audit()
    finally: files.close(); os.close(fd); os.close(parent)


def test_original_terminal_native_failure_dominates_worker_wait0(fabricated):
    h = fabricated
    def refused(volume): raise proof.SupervisionRefusal("REFUSED: native_proof_mount")
    h.terminal_callback = refused
    with pytest.raises(proof.SupervisionRefusal, match="native_proof_mount"): h.produce(h.prepare())
    assert proof.worker._WAITS[h.processes[0]][1] == 0
    assert proof._PRODUCERS == {} and proof._CLOSED == {}
    assert (h.volumes[0].output.path / "run.refused.json").is_file()


def test_close_failure_dominates_provisional_marker(fabricated):
    h = fabricated
    def refused(volume): raise proof.SupervisionRefusal("REFUSED: supervision_original")
    h.close_callback = refused
    with pytest.raises(proof.SupervisionRefusal, match="supervision_original"): h.produce(h.prepare())
    path = h.volumes[0].output.path
    assert (path / proof.MARKER_ROLE).is_file() and (path / "run.refused.json").is_file()
    assert proof._PRODUCERS == {} and proof._CLOSED == {}


def test_named_negative_after_context_close_vetoes_producer(fabricated):
    h = fabricated
    def negative(volume):
        path = volume.output.path / "run.refused.json"
        if not path.exists(): path.write_bytes(b"negative")
    h.named_callback = negative
    with pytest.raises(proof.SupervisionRefusal): h.produce(h.prepare())
    assert proof._PRODUCERS == {} and proof._CLOSED == {}


@pytest.mark.parametrize("case", ["unknown_wait", "nonzero", "partial_tail", "extra_line"])
def test_unverified_or_unpreserved_worker_keeps_all_original_contexts(fabricated, monkeypatch, case):
    h = fabricated; retained = []
    # A known terminal child may now close NEGATIVELY after complete private
    # preservation. This case deliberately makes that preservation unavailable;
    # the historical hold assertion remains required in that failure direction.
    original_preserve = proof._NegativeReporter.preserve
    def fail_private(reporter, name, raw):
        if name == "child.failure.buffers.private.json": raise OSError(28, "fabricated disk full")
        return original_preserve(reporter, name, raw)
    monkeypatch.setattr(proof._NegativeReporter, "preserve", fail_private)
    class StopTestHold(BaseException): pass
    def hold(state):
        retained.append(state); proof._HELD.append(state)
        raise StopTestHold()
    monkeypatch.setattr(proof, "_hold", hold)
    if case == "unknown_wait": h.wait_error = TimeoutError()
    elif case == "nonzero": h.status = 2
    else:
        h.raw = b"".join(canonical_json(proof.worker._worker_line(stage, 4321, os.getpid())).encode()
            + b"\n" for stage in ("entered", "completed"))
        h.raw += b"UNVERIFIED_PARTIAL_TAIL" + (b"\n" if case == "extra_line" else b"")
    with pytest.raises(BaseException) as caught: h.produce(h.prepare())
    assert not isinstance(caught.value, StopTestHold)
    assert len(retained) == len(proof._HELD) == 1
    state = retained[0]; child = h.processes[0]
    assert state["process"] is child and state["origin"] is proof.worker._CHILDREN[child]
    assert state["failure"] is caught.value and state["trace"] is not None
    assert child.stdout.closed is False and len(child.waits) == (0 if case == "extra_line" else 1)
    assert not state["outputs"].closed and not state["directory"].closed
    for obj, field in ((state["outputs"], "fd"), (state["volume"], "mount_fd")):
        assert os.fstat(getattr(obj, field)).st_ino > 0
    assert h.events == ["new-domain", "worker-launched"]
    assert proof._PRODUCERS == {} and proof._CLOSED == {}
    if case in ("partial_tail", "extra_line"):
        frames = []
        trace = state["trace"]
        while trace is not None: frames.append(trace.tb_frame.f_locals); trace = trace.tb_next
        assert any(b"UNVERIFIED_PARTIAL_TAIL" in frame.get("pending", b"") + frame.get("block", b"")
            for frame in frames if type(frame.get("pending", b"")) is bytes and type(frame.get("block", b"")) is bytes)


def _bounded_test_hold(monkeypatch):
    retained = []
    class StopTestHold(BaseException): pass
    def hold(state):
        retained.append(state); proof._HELD.append(state)
        raise StopTestHold()
    monkeypatch.setattr(proof, "_hold", hold)
    return retained


def _two_original_lines():
    return b"".join(canonical_json(proof.worker._worker_line(stage, 4321, os.getpid())).encode() + b"\n"
        for stage in ("entered", "completed"))


def _collection_fault(h, monkeypatch, case):
    h.raw = _two_original_lines()
    h.injected = False
    if case == "third_line": h.raw += b"UNVERIFIED_THIRD_LINE\n"
    elif case == "partial_tail": h.raw += b"UNVERIFIED_PARTIAL_TAIL"
    elif case == "nonzero": h.status = 2
    elif case == "unknown_wait": h.wait_error = TimeoutError()
    elif case in ("postwrite", "prewrite"):
        original_write = proof.worker._write
        def fail_write(fd, raw):
            if case == "postwrite": original_write(fd, raw)
            h.injected = True
            raise OSError(28, "fabricated original collector write refusal")
        monkeypatch.setattr(proof.worker, "_write", fail_write)
    elif case in ("stdout_relation", "postwait_relation"):
        original_stat = os.stat
        def fail_named(path, *args, **kwargs):
            info = original_stat(path, *args, **kwargs)
            if (path == "stdout.jsonl" and h.volumes and not h.injected
                    and kwargs.get("dir_fd") == h.volumes[-1].output.fd
                    and info.st_size > 0 and (case == "stdout_relation" or h.processes[0].waits)):
                h.injected = True
                return _only_ctime_changed(info)
            return info
        monkeypatch.setattr(os, "stat", fail_named)
    else: raise AssertionError("unknown explicit fabricated fault")
    def forbid_positive_callback_after_capture(files):
        original = files.callback
        def check():
            assert not proof._CAPTURED, "negative preservation called a failed positive source/native guard"
            return original()
        files.callback = check
    h.output_callback = forbid_positive_callback_after_capture


@pytest.mark.parametrize("case", ["stdout_relation", "postwait_relation", "prewrite", "postwrite", "third_line", "partial_tail", "nonzero"])
def test_genuine_collection_failure_preserves_every_present_buffer_and_closes_only_negative(fabricated, monkeypatch, case):
    h = fabricated; _collection_fault(h, monkeypatch, case)
    held = _bounded_test_hold(monkeypatch)
    original = proof._preserve_collection_failure
    tokens = []
    def preserve(state):
        assert proof._CAPTURED[-1] is state
        assert proof._PRESERVATIONS[id(state["failure"])][1] is state
        token = original(state)
        if token is not None:
            assert proof._negative_closed(token, state) is True
            assert proof._negative_closed(object(), state) is False
            assert proof._negative_closed(token, dict(state)) is False
            tokens.append(token)
        return token
    monkeypatch.setattr(proof, "_preserve_collection_failure", preserve)
    with pytest.raises((proof.old.NativeProofRefusal, proof.worker.ProcessSupervisorRefusal, OSError)) as caught:
        h.produce(h.prepare())
    assert held == [] and len(tokens) == len(proof._NEGATIVE_CLOSURES) == 1
    state = proof._CAPTURED[0]; child = h.processes[0]
    assert state["failure"] is caught.value and state["capture_error"] is state["preservation_error"] is None
    assert state["frame"].f_code is proof._COLLECT_CODE and state["frame"].f_globals is proof.worker.__dict__
    local = state["frame"].f_locals
    assert set(state["buffers"]) == {name for name in ("output", "pending", "line", "block") if name in local}
    assert all(local[name] is raw for name, raw in state["buffers"].items())
    path = h.volumes[0].output.path
    encoded = json.loads((path / "child.failure.buffers.private.json").read_bytes())
    assert encoded["present"] == sorted(state["buffers"])
    assert encoded["private_bytes_hex"] == {name: raw.hex() for name, raw in state["buffers"].items()}
    assert state["tail"] == b"".join(state["blocks"])
    assert (path / "child.remaining.pipe.private.bin").read_bytes() == state["tail"]
    assert (path / "child.partial.stdout.private.bin").read_bytes() == state["partial_log"] == (path / "stdout.jsonl").read_bytes()
    closed = json.loads((path / "child.negative.closed.json").read_bytes())
    assert closed["status"] == "all_original_collection_bytes_preserved_negative_only"
    assert closed["actual_child_exit"] == h.status and closed["collector_returned"] is False and closed["pipe_EOF"] is True
    assert (path / "run.refused.json").is_file()
    assert not any((path / name).exists() for name in (proof.MARKER_ROLE, proof.INVENTORY_ROLE, "child.exit.provisional.json"))
    assert proof._PRODUCERS == proof._CLOSED == {} and child.stdout.closed
    assert len(child.waits) == 1
    if case in ("stdout_relation", "prewrite", "postwrite", "third_line"):
        assert child not in proof.worker._WAITS
        assert proof._NEGATIVE_WAITS[child][0] is state["origin"]
    else: assert child in proof.worker._WAITS and child not in proof._NEGATIVE_WAITS
    if case in ("stdout_relation", "postwait_relation"):
        assert closed["original_failure"]["comparison_relation"] == "stdout_fd_named_pair"
        assert closed["original_failure"]["mismatching_fields"] == ["ctime_ns"]
    if case == "postwait_relation": assert state["tail"] == b"" and state["partial_log"] == h.raw
    if case == "prewrite": assert state["partial_log"] == b"" and state["buffers"]["line"]
    if case == "postwrite": assert state["partial_log"] == state["buffers"]["line"] + b"\n" and state["buffers"]["output"] == b""
    for name in proof.PRIVATE_ROLES:
        info = (path / name).lstat()
        assert info.st_mode & 0o777 == 0o600 and info.st_nlink == 1


@pytest.mark.parametrize("case", ["third_line", "nonzero", "postwrite"])
def test_genuine_domain_collector_failure_finishes_both_private_negative_preservations(genuine_domain, monkeypatch, case):
    h = genuine_domain; _collection_fault(h, monkeypatch, case)
    held = _bounded_test_hold(monkeypatch)
    with pytest.raises((proof.worker.ProcessSupervisorRefusal, OSError)) as caught:
        h.produce(h.prepare())
    assert held == []
    volume = h.volumes[0]; creation = proof._CREATION_STATES[volume]
    collection = proof._CAPTURED[0]
    assert creation["failure"] is collection["failure"] is caught.value
    assert collection["preservation_error"] is None and collection["eof"] is True
    assert creation["carrier"].closed and creation["carrier"].originals
    assert (volume.mount / "proof" / "child.negative.closed.json").is_file()
    assert (volume.mount / "proof" / "child.failure.buffers.private.json").is_file()
    assert (volume.mount / proof.CREATION_MANIFEST_ROLE).is_file()
    assert proof.failure_summary(caught.value)["creation_manifest_sha256"] == hash_bytes(creation["manifest_raw"])
    failure = json.loads((volume.mount / proof.CREATION_FAILURE_ROLE).read_bytes())
    assert any(row["site"] == "original_producer" for row in failure["original_own_trace_sites"])
    assert h.processes[0].stdout.closed and proof._PRODUCERS == proof._CLOSED == {}
    assert not (volume.mount / "proof" / proof.MARKER_ROLE).exists()


def test_unknown_negative_wait_retains_every_original_context_and_never_marks_closed(fabricated, monkeypatch):
    h = fabricated; _collection_fault(h, monkeypatch, "unknown_wait")
    held = _bounded_test_hold(monkeypatch)
    with pytest.raises(TimeoutError) as caught: h.produce(h.prepare())
    assert len(held) == 1 and held[0] is proof._CAPTURED[0]
    state = held[0]
    assert state["failure"] is caught.value and isinstance(state["preservation_error"], TimeoutError)
    assert state["frame"] is not None and state["buffers"] and state["eof"] is True
    assert state["process"].stdout.closed is False
    assert state["reporter"].fds and not state["outputs"].closed and not state["directory"].closed
    assert not (state["outputs"].path / "child.negative.closed.json").exists()
    assert proof._NEGATIVE_CLOSURES == proof._PRODUCERS == proof._CLOSED == {}


@pytest.mark.parametrize("fault", ["fileno", "missing_buffer", "partial_write", "readback", "fsync", "cleanup"])
def test_negative_preservation_faults_hold_original_buffers_and_surviving_anchors(fabricated, monkeypatch, fault):
    h = fabricated; _collection_fault(h, monkeypatch, "postwrite")
    held = _bounded_test_hold(monkeypatch)
    if fault in ("fileno", "missing_buffer"):
        original_capture = proof._capture_collection_failure
        def capture(*args):
            state = original_capture(*args)
            if fault == "fileno":
                def refused(): raise OSError(9, "fabricated live descriptor callback")
                monkeypatch.setattr(state["stdout"], "fileno", refused)
            else: state["buffers"].pop("pending")
            return state
        monkeypatch.setattr(proof, "_capture_collection_failure", capture)
    elif fault == "cleanup":
        def refused(volume): raise OSError(5, "fabricated negative context cleanup")
        h.close_callback = refused
    else:
        armed = []
        original_preserve = proof._NegativeReporter.preserve
        def preserve(reporter, name, raw):
            if name == "child.failure.buffers.private.json": armed.append(reporter)
            return original_preserve(reporter, name, raw)
        monkeypatch.setattr(proof._NegativeReporter, "preserve", preserve)
        if fault == "partial_write":
            original_write = proof._write
            def write(fd, raw):
                if armed and fd in armed[-1].private_fds:
                    original_write(fd, raw[:1])
                    raise OSError(28, "fabricated private partial write")
                return original_write(fd, raw)
            monkeypatch.setattr(proof, "_write", write)
        elif fault == "readback":
            original_read = os.read
            def read(fd, maximum):
                raw = original_read(fd, maximum)
                return b"X" + raw[1:] if armed and fd in armed[-1].private_fds and raw else raw
            monkeypatch.setattr(os, "read", read)
        else:
            original_fsync = os.fsync
            def fsync(fd):
                if armed and fd in armed[-1].private_fds: raise OSError(5, "fabricated private fsync")
                return original_fsync(fd)
            monkeypatch.setattr(os, "fsync", fsync)
    with pytest.raises(OSError) as caught: h.produce(h.prepare())
    assert len(held) == 1 and held[0] is proof._CAPTURED[0]
    state = held[0]
    assert state["failure"] is caught.value and state["trace"] is not None
    assert state["frame"].f_locals["line"] + b"\n" == (state["outputs"].path / "stdout.jsonl").read_bytes()
    assert state["frame"].f_locals["pending"] is not None
    assert state["reporter"].fds and all(os.fstat(fd).st_ino > 0 for fd in state["reporter"].fds)
    assert proof._PRODUCERS == proof._CLOSED == {}
    if fault != "cleanup":
        assert state["process"].stdout.closed is False and not state["outputs"].closed
        assert state["preservation_error"] is not None
        assert proof._NEGATIVE_CLOSURES == {}
        assert not (state["outputs"].path / "child.negative.closed.json").exists()
    else:
        assert state["cleanup_error"] is not None
        assert (state["outputs"].path / "child.negative.closed.json").is_file()


def test_tail_overflow_retains_the_newly_consumed_block_before_holding(fabricated, monkeypatch):
    h = fabricated; _collection_fault(h, monkeypatch, "postwrite")
    h.raw += b"UNVERIFIED_REMAINING_PIPE" * 120
    original_read = os.read
    def small_original_reads(fd, maximum):
        # Keep the genuine original collector/frame, but make its first failed
        # line arrive in bounded small pipe reads so the buffer report itself
        # fits the explicit smaller fabricated preservation cap.
        if h.processes and fd == h.processes[0].stdout.fileno() and not proof._CAPTURED:
            maximum = min(maximum, 32)
        return original_read(fd, maximum)
    monkeypatch.setattr(os, "read", small_original_reads)
    monkeypatch.setattr(proof, "MAXIMUM_PRIVATE_BYTES", 2048)
    monkeypatch.setattr(proof, "POLICY_SHA256", hash_payload(proof.policy()))
    held = _bounded_test_hold(monkeypatch)
    with pytest.raises(OSError): h.produce(h.prepare())
    assert len(held) == 1
    state = held[0]
    assert len(state["tail"]) > proof.MAXIMUM_PRIVATE_BYTES
    assert state["tail"] == b"".join(state["blocks"]) and state["blocks"][-1]
    assert isinstance(state["preservation_error"], proof.SupervisionRefusal)
    assert state["process"].stdout.closed is False and state["reporter"].fds
    assert proof._NEGATIVE_CLOSURES == proof._PRODUCERS == proof._CLOSED == {}


def test_missing_genuine_collector_frame_or_copied_state_cannot_preserve_anything(monkeypatch):
    class HostileError(ValueError):
        def __str__(self): raise AssertionError("do not format a private error")
    error = HostileError("PRIVATE_UNFORMATTED_DETAIL")
    state = proof._capture_collection_failure(error, None, None, None, None, None)
    assert proof._CAPTURED == [state] and state["failure"] is error
    assert state["capture_error"] is not None and state["frame"] is None
    assert proof._preserve_collection_failure(dict(state)) is None
    assert proof._preserve_collection_failure(state) is None
    assert proof._NEGATIVE_CLOSURES == proof._NEGATIVE_WAITS == {}


@pytest.mark.parametrize("when", ["context_close", "reporter_close"])
def test_final_partial_log_original_seal_drift_holds_after_negative_copies_exist(fabricated, monkeypatch, when):
    h = fabricated; _collection_fault(h, monkeypatch, "postwrite")
    held = _bounded_test_hold(monkeypatch)
    changed = []
    def mutate():
        path = h.volumes[0].output.path / "stdout.jsonl"
        raw = path.read_bytes()
        path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
        changed.append(path)
    if when == "context_close": h.close_callback = lambda volume: mutate()
    else:
        original = proof._NegativeReporter.close
        def close(reporter):
            original(reporter)
            if proof._CAPTURED: mutate()
        monkeypatch.setattr(proof._NegativeReporter, "close", close)
    with pytest.raises(OSError): h.produce(h.prepare())
    assert len(held) == len(changed) == 1
    state = held[0]
    assert state is proof._CAPTURED[0] and isinstance(state["cleanup_error"], proof.old.NativeProofRefusal)
    assert (state["reporter"].path / "child.negative.closed.json").is_file()
    assert (state["reporter"].path / "child.partial.stdout.private.bin").read_bytes() == state["partial_log"]
    assert changed[0].read_bytes() != state["partial_log"]
    assert proof._PRODUCERS == proof._CLOSED == {}


def test_root_private_overflow_retains_the_exact_consumed_block_and_latches_reads(monkeypatch):
    read_fd, write_fd = os.pipe()
    previous = b"P" * (65536 + 4096)
    consumed = b"SOURCE_FREE_DIAGNOSTIC_BLOCK"
    try:
        os.write(write_fd, consumed)
        with pytest.raises(proof.SupervisionRefusal) as caught:
            proof._read_private(read_fd, previous)
        row = proof._private_failure(caught.value, read_fd)
        assert row is proof._PRIVATE_FAILURES[id(caught.value)]
        assert row[2] is previous and row[3] == consumed and row[4] == previous + consumed
        assert proof._private_failure(caught.value, write_fd) is None
        os.write(write_fd, b"MUST_REMAIN_UNREAD")
        calls = []
        original = proof._read_private
        def read(*args): calls.append(args); return original(*args)
        monkeypatch.setattr(proof, "_read_private", read)
        class StopTestHold(BaseException): pass
        monkeypatch.setattr(proof.time, "sleep", lambda seconds: (_ for _ in ()).throw(StopTestHold()))
        state = {"master": read_fd, "raw": row[4], "private_failure": row, "private_error": caught.value}
        with pytest.raises(StopTestHold): proof._hold(state)
        assert calls == [] and os.read(read_fd, 4096) == b"MUST_REMAIN_UNREAD"
    finally:
        os.close(read_fd); os.close(write_fd)


def test_unexpected_prestart_private_bytes_are_held_and_never_reset(coordinator, monkeypatch):
    h = coordinator; original = proof._launch_service
    unexpected = b"UNEXPECTED_PRIVATE_PRESTART_BYTES"
    def launch(role):
        result = original(role)
        if role == "load":
            spec = json.loads((h.root / proof.PARENT / proof.BOOTSTRAP / "launch.spec.json").read_bytes())
            fd = os.open(spec["observer"]["slave_path"], os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_NOCTTY", 0))
            try: os.write(fd, unexpected)
            finally: os.close(fd)
        return result
    monkeypatch.setattr(proof, "_launch_service", launch)
    held = _bounded_test_hold(monkeypatch)
    with pytest.raises(proof.SupervisionRefusal): proof.coordinate_registered(HEAD, REMOTE)
    assert len(held) == 1
    state = held[0]
    assert state["raw"] == unexpected and state["private_failure"][4] == unexpected
    assert h.kernel_calls.count("start") == 0 and h.processes == []
    assert proof._PRODUCERS == proof._CLOSED == {}
    os.close(state["master"]); os.close(state["slave"])
    state["master"] = state["slave"] = None


def test_observer_emits_only_genuine_factory_result_as_pending_pty_observation(fabricated):
    h = fabricated; digest = h.prepare(); result = h.produce(digest)
    channel = proof._Observer(h.observer, digest); channel.emit(result=result)
    raw = os.read(h.master, proof.MAX_WIRE + 1)
    # The real PTY is only a transport; its ONLCR may map the one logical LF.
    raw = raw.replace(b"\r\n", b"\n")
    public = json.loads(raw)
    assert public["status"] == "producer_complete_provisional" and public["failure"] is None
    assert proof._filtered_observation(raw, h.observer, digest, os.getpid()) == result.public_summary()["marker"]
    with pytest.raises(proof.SupervisionRefusal): channel.emit(result=result)


def test_observer_cannot_accept_caller_summary(fabricated):
    h = fabricated; channel = proof._Observer(h.observer, "d" * 64)
    with pytest.raises(proof.SupervisionRefusal, match="supervision_factory"):
        channel.emit(result={"status": "producer_checks_complete_provisional"})
    assert channel.attempted is True


def test_largest_allowlisted_failure_fits_original_wire_and_roundtrips_exact_correlation(fabricated, monkeypatch):
    h = fabricated
    detail = {"stage": max(proof._STAGES, key=len), "component": max(proof._COMPONENTS, key=len),
        "contract_code": max(proof._CODES, key=len),
        "upstream_contract_code": max(proof.old._CODES | proof.worker._CODES | proof.native._CODES, key=len),
        "errno_name": max(set(proof._ERRNOS.values()) | set(proof.native._ERRNOS.values())
            | set(proof.worker._ERRNOS.values()), key=len),
        "mismatching_fields": list(proof.old._STAMP_NAMES),
        "comparison_relation": max(proof._COMPARISON_ROLES, key=len), "creation_manifest_sha256": "f" * 64}
    monkeypatch.setattr(proof, "failure_summary", lambda error: dict(detail))  # Explicit maximal fixed-diagnostic seam.
    digest = "d" * 64
    proof._Observer(h.observer, digest).emit(error=ValueError("never formatted"))
    raw = os.read(h.master, proof.MAX_WIRE + 1).replace(b"\r\n", b"\n")
    assert 0 < len(raw) <= proof.MAX_WIRE == 1024
    checked = proof._validated_observation(raw, h.observer, digest, os.getpid())
    assert checked["failure"] == detail and checked["nonce"] == h.observer["nonce"]
    assert checked["status"] == "refused" and checked["marker"] is None
    assert checked["authority_sha256"] == hash_payload(proof.authority())
    worst_pid = dict(checked); worst_pid["pid"] = 2 ** 31 - 1
    # Serialization upper bound only, not another observed process/PTY result.
    assert len(canonical_json(worst_pid).encode() + b"\n") <= proof.MAX_WIRE


@pytest.mark.parametrize("value", ["unknown_relation", 1, True, [], {}])
def test_failure_wire_rejects_unregistered_or_nonliteral_comparison_relation(value):
    detail = {"stage": "child_observation", "component": "operation", "contract_code": None,
        "upstream_contract_code": None, "errno_name": None, "mismatching_fields": [], "comparison_relation": value,
        "creation_manifest_sha256": None}
    with pytest.raises(proof.SupervisionRefusal): proof._checked_failure(detail)


@pytest.mark.parametrize("value", [True, 123, "", "a" * 63, "A" * 64, {"sha256": "a" * 64}])
def test_failure_wire_rejects_malformed_creation_manifest_identity(value):
    detail = {"stage": "output_creation", "component": "native_system", "contract_code": None,
        "upstream_contract_code": None, "errno_name": None, "mismatching_fields": [], "comparison_relation": None,
        "creation_manifest_sha256": value}
    with pytest.raises(proof.SupervisionRefusal): proof._checked_failure(detail)


def test_root_accepts_only_kernel0_plus_genuine_inner_wait_and_independent_reader(coordinator):
    h = coordinator; result = proof.coordinate_registered(HEAD, REMOTE)
    assert type(result) is proof.ClosedNativeSupervision
    public = result.public_summary()
    assert public["status"] == "closed_source_free_native_supervision_in_memory_only"
    assert public["actual_kernel_exit"] == public["actual_child_exit"] == 0
    assert public["durable_Main_receipt"] is False and public["sourceAUTH_blocked"] is True
    assert public["authority"] == proof.authority()
    assert h.reader_count == 1 and h.kernel_calls.count("start") == h.kernel_calls.count("load") == 1
    child = h.processes[0]
    assert proof.worker._WAITS[child][0] is proof.worker._CHILDREN[child]
    assert proof.worker._WAITS[child][1] == 0 and len(child.waits) == 1
    assert len(proof._PRODUCERS) == len(proof._CLOSED) == 1


def test_query_uses_explicit_current_remote_after_prior_startup_epoch(coordinator, monkeypatch):
    h = coordinator
    assert REMOTE != proof.startup.REMOTE
    guarded = []
    def guard(head, remote):
        guarded.append((head, remote))
        assert (head, remote) == (HEAD, REMOTE)
    monkeypatch.setattr(proof, "_guard", guard)
    assert proof._query_service(HEAD, REMOTE) is None
    assert guarded == [(HEAD, REMOTE)] and h.kernel_calls == ["query"]


def test_root_kernel_nonzero_vetoes_positive_marker_and_pty(coordinator):
    h = coordinator; h.kernel_exit = 2
    with pytest.raises(proof.SupervisionRefusal, match="supervision_negative"):
        proof.coordinate_registered(HEAD, REMOTE)
    assert len(proof._PRODUCERS) == 1 and proof._CLOSED == {} and h.reader_count == 0
    assert h.kernel_calls.count("start") == 1


@pytest.mark.parametrize("tail", [b"UNVERIFIED_TAIL", b"\n", b"{}\n"])
def test_root_kernel0_does_not_cure_unknown_observer_tail(coordinator, tail):
    h = coordinator; h.observation_suffix = tail
    with pytest.raises(proof.SupervisionRefusal, match="supervision_negative"):
        proof.coordinate_registered(HEAD, REMOTE)
    assert proof._CLOSED == {} and h.reader_count == 0 and h.kernel_calls.count("start") == 1


@pytest.mark.parametrize("when", ["entry", "native", "audit", "close", "named"])
def test_root_reader_failure_and_postclose_drift_never_issue_closed_result(coordinator, when):
    h = coordinator
    def fail(stage, read):
        if stage == when: raise proof.SupervisionRefusal("REFUSED: supervision_original")
    h.reader_event = fail
    with pytest.raises(proof.SupervisionRefusal, match="supervision_original"):
        proof.coordinate_registered(HEAD, REMOTE)
    assert proof._CLOSED == {} and h.kernel_calls.count("start") == 1


def test_root_result_anchor_copy_and_public_payload_cannot_grant_source(coordinator):
    result = proof.coordinate_registered(HEAD, REMOTE)
    public = result.public_summary(); public["authority"]["source_admitted"] = True
    assert result.public_summary()["authority"]["source_admitted"] is False
    result._anchor = tuple(list(result._anchor))
    with pytest.raises(proof.SupervisionRefusal, match="supervision_factory"): result.public_summary()


@pytest.mark.parametrize("mutation", ["backing", "mount_sibling", "system_presence", "main"])
def test_last_code_callback_native_metadata_drift_vetoes_root_result(coordinator, mutation):
    h = coordinator; armed = False; changed = []
    def reader_event(stage, reader):
        nonlocal armed
        if stage == "native": armed = True
    def final_guard():
        if not armed or changed: return
        volume = h.volumes[-1]
        if mutation == "backing": volume.image.chmod(0o640)
        elif mutation == "mount_sibling": (volume.mount / "late.foreign").mkdir(mode=0o700)
        elif mutation == "system_presence": (volume.mount / ".fseventsd").mkdir(mode=0o700)
        else: (volume.mount / "main" / "late.foreign").write_bytes(b"foreign")
        changed.append(mutation)
    h.reader_event, h.guard_callback = reader_event, final_guard
    with pytest.raises((proof.SupervisionRefusal, proof.native.IsolatedVolumeRefusal, proof.old.NativeProofRefusal)):
        proof.coordinate_registered(HEAD, REMOTE)
    assert changed == [mutation] and proof._CLOSED == {} and h.kernel_calls.count("start") == 1


@pytest.mark.parametrize("mutation", ["backing", "mount_sibling", "system_presence", "main"])
def test_postclose_original_named_metadata_drift_vetoes_root_result(coordinator, mutation):
    h = coordinator; changed = []
    def reader_event(stage, reader):
        if stage != "close": return
        volume = h.volumes[-1]
        if mutation == "backing": volume.image.chmod(0o640)
        elif mutation == "mount_sibling": (volume.mount / "late.foreign").mkdir(mode=0o700)
        elif mutation == "system_presence": (volume.mount / ".fseventsd").mkdir(mode=0o700)
        else: (volume.mount / "main" / "late.foreign").write_bytes(b"foreign")
        changed.append(mutation)
    h.reader_event = reader_event
    with pytest.raises((proof.SupervisionRefusal, proof.native.IsolatedVolumeRefusal, proof.old.NativeProofRefusal)):
        proof.coordinate_registered(HEAD, REMOTE)
    assert changed == [mutation] and proof._CLOSED == {} and h.kernel_calls.count("start") == 1


@pytest.mark.parametrize("fault", ["empty", "malformed", "timeout"])
def test_start_attempt_without_authenticated_pid_retains_original_root_contexts(coordinator, monkeypatch, fault):
    h = coordinator; h.start_failure = fault; retained = []
    class StopTestHold(BaseException): pass
    def hold(state):
        retained.append(state); proof._HELD.append(state)
        raise StopTestHold()
    monkeypatch.setattr(proof, "_hold", hold)
    with pytest.raises((proof.SupervisionRefusal, TimeoutError)) as caught:
        proof.coordinate_registered(HEAD, REMOTE)
    assert len(retained) == 1
    state = retained[0]
    assert state["failure"] is caught.value and state["start_attempted"] is True
    assert state["start_PID_validated"] is False and state["kernel"] is None
    assert state["code"].fds and not state["config_directory"].closed
    assert state["config"].directory is state["config_directory"]
    assert os.fstat(state["master"]).st_ino > 0 and os.fstat(state["slave"]).st_ino > 0
    assert h.kernel_calls.count("start") == 1 and h.processes == [] and h.reader_count == 0
    assert proof._PRODUCERS == {} and proof._CLOSED == {}
    # Test-only closure of the exact retained original PTY endpoints.
    os.close(state["master"]); os.close(state["slave"])
    state["master"] = state["slave"] = None


def test_root_kernel_json_copy_is_not_an_original_query_record(coordinator):
    result = proof.coordinate_registered(HEAD, REMOTE)
    receipt = proof._ROOT_RECEIPTS[result._anchor[2]]
    original = receipt[2][0]
    assert proof._kernel_origin(original) is receipt[2]
    with pytest.raises(proof.SupervisionRefusal, match="supervision_factory"):
        proof._kernel_origin(json.loads(canonical_json(original)))


@pytest.mark.parametrize("change", ["parsed", "argv", "returncode", "raw", "reader_lineage", "code_manifest", "load_rows"])
def test_closed_summary_rechecks_original_kernel_and_context_anchors(coordinator, change):
    result = proof.coordinate_registered(HEAD, REMOTE)
    receipt = proof._ROOT_RECEIPTS[result._anchor[2]]; kernel = receipt[2]
    reader, code, config, load = receipt[3]
    if change == "parsed": kernel[0]["exit"] = False
    elif change == "argv": kernel[1].args.append("--unregistered")
    elif change == "returncode": kernel[1].returncode = 2
    elif change == "raw": kernel[1].stdout += b"\nUNREGISTERED"
    elif change == "reader_lineage": reader.head = "d" * 40
    elif change == "code_manifest": code.manifest[next(iter(code.manifest))] = "d" * 64
    else: load.rows = []
    with pytest.raises(proof.SupervisionRefusal): result.public_summary()


def test_fixed_failure_summary_never_formats_arbitrary_error_text():
    class HostileError(ValueError):
        def __str__(self): raise AssertionError("exception formatting forbidden")
    public = proof.failure_summary(HostileError("PRIVATE_SECRET_PATH"))
    assert "PRIVATE_SECRET_PATH" not in canonical_json(public)
    assert public["contract_code"] is None


def _only_ctime_changed(info):
    fields = ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink",
              "st_size", "st_mtime_ns", "st_ctime_ns")
    value = {name: getattr(info, name) for name in fields}
    value["st_ctime_ns"] += 1
    return SimpleNamespace(**value)


@pytest.mark.parametrize("relation", ["main_fd_original_seal", "main_named_original_seal"])
def test_exact_original_main_comparison_names_only_the_failed_relation(genuine_domain, monkeypatch, relation):
    # Native APFS/device facts remain an explicitly fabricated boundary. The
    # actual new DomainVolume.check and unchanged old._same execute against
    # real temporary directory/backing/main originals.
    h = genuine_domain; volume = h.create_domain()
    if relation == "main_fd_original_seal":
        volume.main_seal = (*volume.main_seal[:-1], volume.main_seal[-1] - 1)
    else:
        actual = Path.lstat
        main = volume.mount / "main"
        monkeypatch.setattr(Path, "lstat", lambda path: _only_ctime_changed(actual(path))
            if path == main else actual(path))
    with pytest.raises(proof.old.NativeProofRefusal, match="native_proof_stamp") as caught:
        volume.check()
    public = proof.failure_summary(caught.value)
    assert public["comparison_relation"] == relation
    assert public["mismatching_fields"] == ["ctime_ns"]
    assert str(volume.mount) not in canonical_json(public)
    assert proof._PRODUCERS == proof._CLOSED == {}


@pytest.mark.parametrize("relation", ["main_fd_original_seal", "main_named_original_seal", "stdout_fd_named_pair"])
def test_outside_helper_call_cannot_claim_a_production_comparison_relation(relation):
    original = tuple(range(9))
    with pytest.raises(proof.old.NativeProofRefusal) as caught:
        proof._compared_stamp((*original[:-1], 999), original, relation)
    public = proof.failure_summary(caught.value)
    assert public["comparison_relation"] is None
    assert proof._comparison(caught.value) is None


@pytest.mark.parametrize("mutation", ["extra", "wrong_nonce", "wrong_pid", "bool_pid", "wrong_authority", "bad_marker", "negative", "trailing", "duplicate"])
def test_observation_wire_is_strict_and_cannot_attest_kernel(mutation):
    observer = {"nonce": "a" * 32}; digest = "b" * 64; pid = 123
    payload = {"schema": "si-native-supervision-observation-v1", "nonce": observer["nonce"], "spec_sha256": digest,
        "pid": pid, "status": "producer_complete_provisional", "marker": {"sha256": "c" * 64, "stamp": [1] * 9},
        "failure": None, "authority_sha256": hash_payload(proof.authority())}
    if mutation == "extra": payload["kernel_exit"] = 0
    elif mutation == "wrong_nonce": payload["nonce"] = "d" * 32
    elif mutation == "wrong_pid": payload["pid"] += 1
    elif mutation == "bool_pid": payload["pid"] = True
    elif mutation == "wrong_authority": payload["authority_sha256"] = "d" * 64
    elif mutation == "bad_marker": payload["marker"]["stamp"][0] = True
    elif mutation == "negative": payload["status"] = "refused"
    raw = canonical_json(payload).encode() + b"\n"
    if mutation == "trailing": raw += b"unverified"
    elif mutation == "duplicate": raw = raw.replace(b'"pid":123', b'"pid":123,"pid":123')
    with pytest.raises((proof.SupervisionRefusal, json.JSONDecodeError)):
        proof._filtered_observation(raw, observer, digest, pid)
