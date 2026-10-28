"""Fabricated child/Git seams and temporary metadata; no launchd or provider."""
import ast
import json
import os
from pathlib import Path
import plistlib
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_count_process_supervisor as supervisor

HEAD, REMOTE = "a" * 40, "b" * 40


@pytest.fixture
def proof(tmp_path, monkeypatch):
    parent = tmp_path / "artifacts" / "short_interest"; parent.mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(supervisor, "ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "NAMESPACE", parent / "count-process-supervisor-proof-v1")
    monkeypatch.setattr(supervisor, "PROOF_POLICY_SHA256", hash_payload(supervisor.policy()))
    calls = []
    monkeypatch.setattr(supervisor, "_guard", lambda head, remote: calls.append((head, remote)))
    manifest = {name: "c" * 64 for name in supervisor.CODE_FILES}
    monkeypatch.setattr(supervisor, "_code_manifest", lambda head, remote: dict(manifest))
    monkeypatch.setattr(supervisor, "_CHILDREN", {})
    monkeypatch.setattr(supervisor, "_WAITS", {})
    monkeypatch.setattr(supervisor, "_EXITS", {})
    monkeypatch.setattr(supervisor, "_HELD", [])
    h = SimpleNamespace(calls=calls, manifest=manifest, processes=[], launches=[], status=0, raw=None)
    def popen(arguments, **kwargs):
        h.launches.append((arguments, kwargs))
        pid = 4321
        raw = h.raw if h.raw is not None else b"".join(
            canonical_json(supervisor._worker_line(stage, pid, os.getpid())).encode() + b"\n"
            for stage in ("entered", "completed"))
        read_fd, write_fd = os.pipe(); os.write(write_fd, raw); os.close(write_fd)
        class Child:
            def __init__(self):
                self.pid = pid; self.stdout = os.fdopen(read_fd, "rb", buffering=0); self.waits = []
            def wait(self, *, timeout): self.waits.append(timeout); return h.status
        child = Child(); h.processes.append(child); return child
    monkeypatch.setattr(supervisor.subprocess, "Popen", popen)
    yield h
    # Test-only cleanup of fabricated pipes/metadata anchors. Production has no release API.
    for process, ns, fd in supervisor._HELD:
        if process.stdout is not None: process.stdout.close()
        try: os.close(fd)
        except OSError: pass
        ns.close()
    for process in h.processes:
        if process.stdout is not None and not process.stdout.closed: process.stdout.close()


def prepare(proof):
    value = supervisor.prepare_proof(HEAD, REMOTE)
    assert value["job_submitted"] is False
    return value["launch_spec_sha256"]


def test_frozen_proof_registration_and_pending_refusal_leave_capture_blocked(monkeypatch):
    monkeypatch.setattr(supervisor, "_guard", lambda *a: pytest.fail("I/O before refusal"))
    assert supervisor.PROOF_POLICY_SHA256 == hash_payload(supervisor.policy())
    supervisor._registered_proof()
    monkeypatch.setattr(supervisor, "PROOF_POLICY_SHA256", "PENDING")
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="proof_unregistered"):
        supervisor.prepare_proof(HEAD, REMOTE)
    monkeypatch.setattr(supervisor, "PROOF_POLICY_SHA256", hash_payload(supervisor.policy()))
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="source_mode_unregistered"):
        supervisor._capture_refused()


def test_capture_CLI_cannot_reach_Git_child_or_storage(monkeypatch, capsys):
    for name in ("_guard", "prepare_proof", "supervise_proof", "proof_worker"):
        monkeypatch.setattr(supervisor, name, lambda *a: pytest.fail("capture entered proof"))
    assert supervisor.main(["capture"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["contract_code"] == "supervisor_source_mode_unregistered"
    assert output["authority"]["provider_HTTP"] == 0


def test_launchd_builder_is_fixed_one_shot_and_has_no_submission_seam():
    job = supervisor.build_launchd_plist(HEAD, REMOTE, "c" * 64)
    assert job["RunAtLoad"] is True and job["KeepAlive"] is False
    assert not {"StartInterval", "StartCalendarInterval", "WatchPaths", "QueueDirectories"} & set(job)
    assert job["StandardOutPath"] == job["StandardErrorPath"] == "/dev/null"
    assert job["ProgramArguments"][:5] == [supervisor.PYTHON, "-B", "-m", supervisor.MODULE, "supervise-proof"]
    assert job["EnvironmentVariables"] == supervisor._environment()
    assert "HOME" not in job["EnvironmentVariables"]
    assert not hasattr(supervisor, "bootstrap") and not hasattr(supervisor, "launchctl")


def test_prepare_creates_only_exclusive_spec_and_reserved_job(proof):
    digest = prepare(proof)
    names = {path.name for path in supervisor.NAMESPACE.iterdir()}
    assert names == {"launch.spec.json", "job.plist"} and not proof.launches
    spec = (supervisor.NAMESPACE / "launch.spec.json").read_bytes()
    assert hash_bytes(spec) == digest and json.loads(spec)["code_manifest"] == proof.manifest
    job = plistlib.loads((supervisor.NAMESPACE / "job.plist").read_bytes())
    assert job == supervisor.build_launchd_plist(HEAD, REMOTE, digest)
    assert all(path.lstat().st_mode & 0o777 == 0o600 for path in supervisor.NAMESPACE.iterdir())
    with pytest.raises(FileExistsError): supervisor.prepare_proof(HEAD, REMOTE)


def test_original_child_wait_issues_distinct_source_free_exit_witness(proof):
    digest = prepare(proof)
    witness = supervisor.supervise_proof(HEAD, REMOTE, digest)
    result = witness.public_summary()
    assert len(proof.launches) == len(proof.processes) == 1 and len(proof.processes[0].waits) == 1
    arguments, kwargs = proof.launches[0]
    assert arguments == json.loads((supervisor.NAMESPACE / "launch.spec.json").read_bytes())["worker_arguments"]
    assert kwargs["shell"] is False and kwargs["start_new_session"] is True and kwargs["close_fds"] is True
    assert kwargs["env"] == supervisor._environment() and kwargs["stdin"] is supervisor.subprocess.DEVNULL
    assert kwargs["stderr"] is supervisor.subprocess.DEVNULL and kwargs["stdout"] is supervisor.subprocess.PIPE
    assert result["actual_process_exit"] == 0 and result["child_process_id"] == 4321
    assert result["known_Codex_exec_session"] is None and "known_exec_session" not in result
    assert result["launcher_independence_verified"] is False
    assert result["authority"]["checkpoint_v1_receipt_issued"] is False
    assert json.loads((supervisor.NAMESPACE / "result.json").read_bytes()) == result
    assert hash_bytes((supervisor.NAMESPACE / "stdout.jsonl").read_bytes()) == result["stdout_sha256"]
    assert proof.processes[0].stdout.closed
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="spec_changed"):
        supervisor.supervise_proof(HEAD, REMOTE, digest)
    assert len(proof.launches) == 1  # Existing log/result can never authorize a relaunch.


def test_caller_JSON_or_status_cannot_mint_OS_exit_witness():
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="factory_required"):
        supervisor.ParentObservedProofExit()
    forged = object.__new__(supervisor.ParentObservedProofExit)
    forged._anchor = forged._identity = (0, 0, "{}", object())
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="exit_changed"): forged.public_summary()


@pytest.mark.parametrize("raw", [b"PRIVATE_SECRET\n", b"{}\n", b"X" * 1025 + b"\n"])
def test_unknown_child_output_is_not_logged_or_relabelled_terminal(proof, monkeypatch, raw):
    digest = prepare(proof); proof.raw = raw
    class Held(BaseException): pass
    original = supervisor._hold_unknown
    def hold(*args):
        supervisor._HELD.append(args); raise Held()
    monkeypatch.setattr(supervisor, "_hold_unknown", hold)
    with pytest.raises(Held): supervisor.supervise_proof(HEAD, REMOTE, digest)
    assert len(proof.launches) == 1 and proof.processes[0].waits == []
    assert (supervisor.NAMESPACE / "stdout.jsonl").read_bytes() == b""
    assert not (supervisor.NAMESPACE / "result.json").exists() and supervisor._EXITS == {}
    assert not proof.processes[0].stdout.closed and supervisor._HELD


def test_nonzero_child_gets_truthful_negative_without_positive_witness_or_restart(proof, monkeypatch):
    digest = prepare(proof); proof.status = 2
    monkeypatch.setattr(supervisor, "_hold_unknown", lambda *a: pytest.fail("known actual exit became unknown"))
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="child_changed"):
        supervisor.supervise_proof(HEAD, REMOTE, digest)
    assert len(proof.launches) == 1 and len(proof.processes[0].waits) == 1
    assert supervisor._EXITS == {} and supervisor._HELD == []
    result = json.loads((supervisor.NAMESPACE / "result.json").read_bytes())
    assert result["status"] == "proof_rejected_after_known_child_exit" and result["actual_process_exit"] == 2
    assert proof.processes[0].stdout.closed


def test_spawn_failure_spends_launch_log_without_starting_or_retrying(proof, monkeypatch):
    digest = prepare(proof); attempts = []
    def fail(*args, **kwargs): attempts.append(True); raise OSError("PRIVATE_ERROR")
    monkeypatch.setattr(supervisor.subprocess, "Popen", fail)
    with pytest.raises(OSError): supervisor.supervise_proof(HEAD, REMOTE, digest)
    assert attempts == [True] and (supervisor.NAMESPACE / "stdout.jsonl").read_bytes() == b""
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="spec_changed"):
        supervisor.supervise_proof(HEAD, REMOTE, digest)
    assert attempts == [True]


def test_observation_deadline_retains_original_handle_and_records_unknown(proof, monkeypatch):
    digest = prepare(proof)
    clock = iter((100., 106.))
    monkeypatch.setattr(supervisor, "_now", lambda: next(clock))
    class Held(BaseException): pass
    monkeypatch.setattr(supervisor.time, "sleep", lambda seconds: (_ for _ in ()).throw(Held()))
    with pytest.raises(Held): supervisor.supervise_proof(HEAD, REMOTE, digest)
    assert len(proof.launches) == 1 and proof.processes[0].waits == []
    assert not proof.processes[0].stdout.closed and supervisor._EXITS == {}
    result = json.loads((supervisor.NAMESPACE / "result.json").read_bytes())
    assert result["requires_process_hold"] is True and result["actual_process_exit"] is None


def test_result_publication_cannot_hide_changed_stdout_binding(proof, monkeypatch):
    digest = prepare(proof); original = supervisor._Namespace.write
    def changed(self, name, raw):
        original(self, name, raw)
        if name == "result.json":
            log = supervisor.NAMESPACE / "stdout.jsonl"
            value = log.read_bytes(); log.write_bytes(b"X" + value[1:])
    monkeypatch.setattr(supervisor._Namespace, "write", changed)
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="file_changed"):
        supervisor.supervise_proof(HEAD, REMOTE, digest)
    assert len(proof.processes[0].waits) == 1 and supervisor._EXITS == {} and supervisor._HELD == []


def test_close_failure_drains_other_metadata_descriptors_and_cannot_issue_witness(proof, monkeypatch):
    digest = prepare(proof); real_close = os.close; failed = []
    original_create = supervisor._Namespace.create; target = []
    def create(self, name):
        fd = original_create(self, name)
        if name == "stdout.jsonl": target.append(fd)
        return fd
    monkeypatch.setattr(supervisor._Namespace, "create", create)
    def close(fd):
        result = real_close(fd)
        if not failed and target and fd == target[0] and supervisor._WAITS:
            failed.append(fd); raise OSError("FABRICATED_PRIVATE_CLOSE")
        return result
    monkeypatch.setattr(supervisor.os, "close", close)
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="file_changed"):
        supervisor.supervise_proof(HEAD, REMOTE, digest)
    assert failed and supervisor._EXITS == {} and proof.processes[0].stdout.closed


def test_fresh_file_constructor_closes_fd_if_mode_protection_fails(proof, monkeypatch):
    prepare(proof); ns = supervisor._Namespace(create=False)
    real_open, real_close = os.open, os.close
    opened, closed = [], []
    def create(*args, **kwargs):
        fd = real_open(*args, **kwargs); opened.append(fd); return fd
    def close(fd): closed.append(fd); return real_close(fd)
    monkeypatch.setattr(supervisor.os, "open", create)
    monkeypatch.setattr(supervisor.os, "close", close)
    monkeypatch.setattr(supervisor.os, "fchmod", lambda *a: (_ for _ in ()).throw(OSError("PRIVATE_MODE_ERROR")))
    try:
        with pytest.raises(OSError): ns.create("stdout.jsonl")
        assert len(opened) == 1 and opened[0] in closed
    finally: ns.close()


@pytest.mark.parametrize("hazard", ["symlink", "mode"])
def test_unsafe_namespace_refuses_before_child(proof, hazard):
    digest = prepare(proof)
    if hazard == "mode": supervisor.NAMESPACE.chmod(0o750)
    else:
        moved = supervisor.NAMESPACE.with_name("preserved")
        supervisor.NAMESPACE.rename(moved); supervisor.NAMESPACE.symlink_to(moved, target_is_directory=True)
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="namespace_changed"):
        supervisor.supervise_proof(HEAD, REMOTE, digest)
    assert not proof.launches


@pytest.mark.parametrize("hazard", ["mode", "hardlink", "symlink", "fifo"])
def test_metadata_read_refuses_unsafe_named_entry_before_open(proof, monkeypatch, hazard):
    prepare(proof); ns = supervisor._Namespace(create=False)
    path = supervisor.NAMESPACE / "launch.spec.json"
    if hazard == "mode": path.chmod(0o644)
    elif hazard == "hardlink": os.link(path, supervisor.NAMESPACE.with_name("preserved-hardlink"))
    else:
        original = supervisor.NAMESPACE.with_name("preserved-launch-spec")
        path.rename(original)
        if hazard == "symlink": path.symlink_to(original)
        else: os.mkfifo(path, 0o600)
    real_open = os.open; attempts = []
    def open_fd(name, flags, *args, **kwargs):
        if os.fspath(name).rsplit("/", 1)[-1] == "launch.spec.json":
            attempts.append(True); raise AssertionError("unsafe metadata was opened before validation")
        return real_open(name, flags, *args, **kwargs)
    monkeypatch.setattr(supervisor.os, "open", open_fd)
    try:
        with pytest.raises(supervisor.ProcessSupervisorRefusal, match="file_changed"):
            ns.read("launch.spec.json")
        assert attempts == []
    finally: ns.close()


def test_metadata_regular_to_FIFO_race_uses_nonblocking_open_and_never_reads(proof, monkeypatch):
    prepare(proof); ns = supervisor._Namespace(create=False)
    path = supervisor.NAMESPACE / "launch.spec.json"
    real_open = os.open; changed, reads = [], []
    def open_fd(name, flags, *args, **kwargs):
        if os.fspath(name).rsplit("/", 1)[-1] == "launch.spec.json" and not changed:
            path.rename(supervisor.NAMESPACE.with_name("preserved-before-FIFO-race"))
            os.mkfifo(path, 0o600); changed.append(True)
            assert flags & os.O_NONBLOCK, "raced FIFO open must never block"
        return real_open(name, flags, *args, **kwargs)
    monkeypatch.setattr(supervisor.os, "open", open_fd)
    monkeypatch.setattr(supervisor.os, "read", lambda *args: reads.append(True) or b"")
    try:
        with pytest.raises(supervisor.ProcessSupervisorRefusal, match="file_changed"):
            ns.read("launch.spec.json")
        assert changed == [True] and reads == []
    finally: ns.close()


def test_metadata_postclose_named_replacement_refuses_original_bytes(proof, monkeypatch):
    prepare(proof); ns = supervisor._Namespace(create=False)
    path = supervisor.NAMESPACE / "launch.spec.json"; inode = path.lstat().st_ino
    original = path.read_bytes(); real_close = os.close; changed = []
    def close(fd):
        info = os.fstat(fd); real_close(fd)
        if info.st_ino == inode and not changed:
            path.rename(supervisor.NAMESPACE.with_name("preserved-after-read-close"))
            path.write_bytes(original); path.chmod(0o600); changed.append(True)
    monkeypatch.setattr(supervisor.os, "close", close)
    try:
        with pytest.raises(supervisor.ProcessSupervisorRefusal, match="file_changed"):
            ns.read("launch.spec.json")
        assert changed == [True]
    finally: ns.close()


def test_write_no_progress_refuses_without_loop(monkeypatch):
    calls = []
    monkeypatch.setattr(supervisor.os, "write", lambda *args: calls.append(True) or 0)
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="write_refused"): supervisor._write(0, b"x")
    assert calls == [True]


def test_exact_lane_guard_checks_only_matching_origin_and_rejects_dirty(monkeypatch, tmp_path):
    monkeypatch.setattr(supervisor, "ROOT", tmp_path); monkeypatch.setattr(supervisor, "_physical", lambda: None)
    calls = []; dirty = []
    def git(arguments):
        calls.append(arguments)
        if arguments == ["rev-parse", "--show-toplevel"]: return (str(tmp_path) + "\n").encode()
        if arguments[:1] == ["status"]:
            return (f"# branch.oid {HEAD}\n# branch.head {supervisor.BRANCH}\n" + ("? foreign\n" if dirty else "")).encode()
        if arguments == ["rev-parse", "refs/remotes/origin/" + supervisor.BRANCH]: return (REMOTE + "\n").encode()
        assert arguments == ["ls-remote", "--refs", "origin", supervisor.REF]
        return (REMOTE + "\t" + supervisor.REF + "\n").encode()
    monkeypatch.setattr(supervisor, "_git", git)
    supervisor._guard(HEAD, REMOTE)
    assert sum(row[:1] == ["ls-remote"] for row in calls) == 1
    dirty.append(True)
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="lane_changed"): supervisor._guard(HEAD, REMOTE)


def test_supervisor_import_boundary_and_no_kill_or_submission_calls():
    tree = ast.parse(Path(supervisor.__file__).read_text())
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported == {"argparse", "json", "math", "os", "pathlib", "plistlib", "re", "selectors",
        "stat", "subprocess", "sys", "time", "data.hashing"}
    assert not any(isinstance(node, ast.Attribute) and node.attr in {"kill", "terminate", "send_signal"}
        for node in ast.walk(tree))
