"""New-scope supervision composition with named fabricated I/O boundaries.

Ordinary temporary directories are NOT APFS evidence. The fake worker uses a
pipe and the unchanged original collector/wait registries; it runs no process,
source operation, launchd command, image command or native syscall.
"""
import json
import os
import plistlib
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
                        ("_ADVISORIES", {})):
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
        assert head == HEAD and remote in (REMOTE, proof.startup.REMOTE)
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
