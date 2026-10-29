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
    monkeypatch.setattr(supervisor, "NAMESPACE", parent / "count-process-supervisor-proof-v2")
    monkeypatch.setattr(supervisor, "PROOF_POLICY_SHA256", hash_payload(supervisor.policy()))
    calls = []
    monkeypatch.setattr(supervisor, "_guard", lambda head, remote: calls.append((head, remote)))
    manifest = {name: "c" * 64 for name in supervisor.CODE_FILES}
    monkeypatch.setattr(supervisor, "_code_manifest", lambda head, remote: dict(manifest))
    monkeypatch.setattr(supervisor, "_CHILDREN", {})
    monkeypatch.setattr(supervisor, "_WAITS", {})
    monkeypatch.setattr(supervisor, "_EXITS", {})
    monkeypatch.setattr(supervisor, "_HELD", [])
    for name in ("_FAILURES", "_FIELDS", "_REFUSALS"): monkeypatch.setattr(supervisor, name, {})
    monkeypatch.setattr(supervisor, "_CLI_CHANNEL", None)
    h = SimpleNamespace(calls=calls, manifest=manifest, processes=[], launches=[], status=0, raw=None,
        monkeypatch=monkeypatch, terminal_fd=None)
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
    if h.terminal_fd is not None: os.close(h.terminal_fd)


def prepare(proof):
    value = supervisor.prepare_proof(HEAD, REMOTE)
    assert value["job_submitted"] is False
    proof.terminal_fd = os.open(supervisor.NAMESPACE / "supervisor.jsonl", os.O_RDWR | os.O_NOFOLLOW)
    proof.monkeypatch.setattr(supervisor, "_terminal_fd", lambda: proof.terminal_fd)
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
    assert output["failure"]["contract_code"] == "supervisor_source_mode_unregistered"
    assert output["authority"]["provider_HTTP"] == 0


def test_launchd_builder_is_fixed_one_shot_and_has_no_submission_seam():
    job = supervisor.build_launchd_plist(HEAD, REMOTE, "c" * 64)
    assert job["RunAtLoad"] is True and job["KeepAlive"] is False
    assert not {"StartInterval", "StartCalendarInterval", "WatchPaths", "QueueDirectories"} & set(job)
    assert job["StandardOutPath"] == str(supervisor.NAMESPACE / "supervisor.jsonl")
    assert job["StandardErrorPath"] == "/dev/null"
    assert job["ProgramArguments"][:5] == [supervisor.PYTHON, "-B", "-m", supervisor.MODULE, "supervise-proof"]
    assert job["EnvironmentVariables"] == supervisor._environment()
    assert "HOME" not in job["EnvironmentVariables"]
    assert not hasattr(supervisor, "bootstrap") and not hasattr(supervisor, "launchctl")


def test_prepare_creates_only_exclusive_spec_and_reserved_job(proof):
    digest = prepare(proof)
    names = {path.name for path in supervisor.NAMESPACE.iterdir()}
    assert names == {"launch.spec.json", "job.plist", "supervisor.jsonl"} and not proof.launches
    spec = (supervisor.NAMESPACE / "launch.spec.json").read_bytes()
    assert hash_bytes(spec) == digest and json.loads(spec)["code_manifest"] == proof.manifest
    assert tuple(json.loads(spec)["supervisor_stdout_initial_stamp"]) == supervisor._stamp(
        (supervisor.NAMESPACE / "supervisor.jsonl").lstat())
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
    # V2 keeps the child observation distinct from the dominating supervisor
    # refusal; a nonzero child never receives a positive result control.
    result = json.loads((supervisor.NAMESPACE / "run.refused.json").read_bytes())
    assert result["status"] == "proof_supervisor_refused" and result["actual_child_exit"] == 2
    assert not (supervisor.NAMESPACE / "result.json").exists()
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
    # Preserve the original cleanup exception instead of replacing it with a
    # synthetic aggregate contract. No exception text enters diagnostics.
    with pytest.raises(OSError, match="FABRICATED_PRIVATE_CLOSE"):
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
    assert imported == {"argparse", "errno", "json", "math", "os", "pathlib", "plistlib", "re", "selectors",
        "stat", "subprocess", "sys", "time", "data.hashing"}
    assert not any(isinstance(node, ast.Attribute) and node.attr in {"kill", "terminate", "send_signal"}
        for node in ast.walk(tree))


def test_cli_post_result_refusal_has_a_distinct_dominating_negative(proof, monkeypatch, capsys):
    digest = prepare(proof)
    original = supervisor._Namespace.write
    def changed_after_result(self, name, raw):
        original(self, name, raw)
        if name == "result.json":
            fd = os.open("stdout.jsonl", os.O_WRONLY, dir_fd=self.fd)
            try: os.write(fd, b"X")
            finally: os.close(fd)
    monkeypatch.setattr(supervisor._Namespace, "write", changed_after_result)
    assert supervisor.main(["supervise-proof", "--head", HEAD, "--remote", REMOTE,
        "--spec-sha256", digest]) == 2
    assert (supervisor.NAMESPACE / "result.json").exists()
    negative = json.loads((supervisor.NAMESPACE / "run.refused.json").read_bytes())
    assert negative["failure"]["contract_code"] == "supervisor_file_changed"
    assert negative["actual_child_exit"] == 0


def test_cli_after_anchor_cleanup_reports_original_failure_without_reopening(proof, monkeypatch, capsys):
    digest = prepare(proof)
    original = supervisor._Namespace.close
    def failed_cleanup(self):
        original(self)
        raise OSError(5, "FABRICATED_PRIVATE_PATH_AND_SECRET")
    monkeypatch.setattr(supervisor._Namespace, "close", failed_cleanup)
    assert supervisor.main(["supervise-proof", "--head", HEAD, "--remote", REMOTE,
        "--spec-sha256", digest]) == 2
    result = json.loads((supervisor.NAMESPACE / "supervisor.jsonl").read_bytes())
    assert result["failure"]["stage"] == "context_cleanup"
    assert result["failure"]["errno_name"] == "EIO"
    assert result["failure"]["contract_code"] is None
    assert "FABRICATED_PRIVATE" not in canonical_json(result)


def run_cli(digest):
    return supervisor.main(["supervise-proof", "--head", HEAD, "--remote", REMOTE, "--spec-sha256", digest])


def terminal():
    raw = (supervisor.NAMESPACE / "supervisor.jsonl").read_bytes()
    assert raw.count(b"\n") == 1 and len(raw) <= supervisor.MAXIMUM_TERMINAL_BYTES
    return json.loads(raw)


def test_full_main_success_is_one_fixed_preopened_terminal_line(proof, capsys):
    digest = prepare(proof)
    assert run_cli(digest) == 0
    result = terminal()
    assert result["status"] == "proof_supervisor_contexts_closed" and result["actual_child_exit"] == 0
    assert result["supervisor_process_exit_attested"] is result["launcher_independence_verified"] is False
    assert result["failure"] is None and result["refusal_record"] == "not_applicable"
    assert capsys.readouterr().out == ""
    assert not (supervisor.NAMESPACE / "run.refused.json").exists()
    assert len(proof.launches) == len(proof.processes[0].waits) == 1


def test_post_context_original_stamp_failure_uses_original_dup_anchors(proof, monkeypatch):
    digest = prepare(proof); original = supervisor._Namespace.close; closes = []
    def changed_after_primary_cleanup(self):
        original(self); closes.append(self)
        if len(closes) == 1:
            with (supervisor.NAMESPACE / "stdout.jsonl").open("r+b") as f: f.write(b"X")
    monkeypatch.setattr(supervisor._Namespace, "close", changed_after_primary_cleanup)
    assert run_cli(digest) == 2
    result = terminal()
    assert result["failure"]["stage"] == "post_context_audit"
    assert result["failure"]["mismatching_fields"]
    assert set(result["failure"]["mismatching_fields"]) <= {"mtime_ns", "ctime_ns"}
    assert result["refusal_record"] == "published"
    negative = json.loads((supervisor.NAMESPACE / "run.refused.json").read_bytes())
    assert negative["failure"] == result["failure"] and negative["actual_child_exit"] == 0
    assert len(closes) == 2 and all(value.fd is value.parent is None for value in closes)


def test_final_reporter_cleanup_failure_does_not_reopen_or_adopt_namespace(proof, monkeypatch):
    digest = prepare(proof); original = supervisor._Namespace.close; calls = []
    def failed_last_cleanup(self):
        original(self); calls.append(self)
        if len(calls) == 2: raise OSError(5, "PRIVATE_FINAL_REPORTER_CLOSE")
    monkeypatch.setattr(supervisor._Namespace, "close", failed_last_cleanup)
    constructor = supervisor._Namespace.__init__; opened = []
    def initial_only(self, **kwargs): opened.append(True); return constructor(self, **kwargs)
    monkeypatch.setattr(supervisor._Namespace, "__init__", initial_only)
    assert run_cli(digest) == 2
    result = terminal()
    assert result["failure"]["errno_name"] == "EIO"
    assert result["refusal_record"] == "original_anchors_closed"
    assert len(opened) == 1 and not (supervisor.NAMESPACE / "run.refused.json").exists()
    assert supervisor._EXITS == {}


def test_public_summary_failure_reaches_independent_channel_without_false_success(proof, monkeypatch):
    digest = prepare(proof)
    def fail(self): raise OSError(5, "PRIVATE_SUMMARY_SECRET")
    monkeypatch.setattr(supervisor.ParentObservedProofExit, "public_summary", fail)
    assert run_cli(digest) == 2
    result = terminal()
    assert result["status"] == "refused" and result["failure"]["stage"] == "public_summary"
    assert result["failure"]["errno_name"] == "EIO" and "PRIVATE" not in canonical_json(result)
    assert result["refusal_record"] == "original_anchors_closed"
    assert json.loads((supervisor.NAMESPACE / "result.json").read_bytes())["actual_process_exit"] == 0


def test_failed_negative_publication_keeps_first_actual_failure(proof, monkeypatch):
    digest = prepare(proof); original = supervisor._Namespace.write
    def fail(self, name, raw):
        if name == "run.refused.json": raise PermissionError(1, "PRIVATE_REPORTING_ERROR")
        original(self, name, raw)
        if name == "result.json":
            with (supervisor.NAMESPACE / "stdout.jsonl").open("r+b") as f: f.write(b"X")
    monkeypatch.setattr(supervisor._Namespace, "write", fail)
    assert run_cli(digest) == 2
    result = terminal()
    assert result["failure"]["contract_code"] == "supervisor_file_changed"
    assert result["failure"]["errno_name"] is None and result["refusal_record"] == "unavailable"
    assert not (supervisor.NAMESPACE / "run.refused.json").exists()


def test_v2_preparation_preserves_existing_v1_namespace_and_controls(proof):
    old = supervisor.NAMESPACE.with_name("count-process-supervisor-proof-v1")
    old.mkdir(mode=0o700)
    raw = b"FABRICATED_V1_UNTOUCHED"
    for name in ("job.plist", "launch.spec.json", "result.json", "stdout.jsonl"):
        (old / name).write_bytes(raw); (old / name).chmod(0o600)
    before = {p.name: (p.read_bytes(), supervisor._stamp(p.lstat())) for p in old.iterdir()}
    prepare(proof)
    assert {p.name: (p.read_bytes(), supervisor._stamp(p.lstat())) for p in old.iterdir()} == before
    assert supervisor.LABEL.endswith("-v2") and "-v2" in supervisor.NAMESPACE.name


@pytest.mark.parametrize("hazard", ["mode", "hardlink", "nonempty"])
def test_preopened_channel_protection_and_zero_size_refuse_before_child(proof, hazard):
    digest = prepare(proof); channel = supervisor.NAMESPACE / "supervisor.jsonl"
    if hazard == "mode": channel.chmod(0o644)
    elif hazard == "hardlink": os.link(channel, supervisor.NAMESPACE.parent / "extra-link")
    else: os.write(proof.terminal_fd, b"FOREIGN")
    before = channel.read_bytes()
    assert run_cli(digest) == 2 and not proof.launches
    assert channel.read_bytes() == before


def test_terminal_channel_rejects_arbitrary_payload_and_cannot_emit_twice(proof):
    prepare(proof); channel = supervisor._TerminalChannel(); ns = supervisor._Namespace(create=False)
    try:
        original = json.loads((supervisor.NAMESPACE / "launch.spec.json").read_bytes())["supervisor_stdout_initial_stamp"]
        channel.bind(ns, tuple(original))
    finally: ns.close()
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="terminal_refused"):
        channel.emit("PRIVATE_UNCONTROLLED_TEXT")
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="terminal_refused"):
        channel.emit("proof_supervisor_contexts_closed", child_exit=0)
    assert (supervisor.NAMESPACE / "supervisor.jsonl").read_bytes() == b""


def test_replacement_opened_by_launcher_cannot_be_adopted_for_refusal_output(proof):
    digest = prepare(proof)
    channel = supervisor.NAMESPACE / "supervisor.jsonl"
    original = supervisor.NAMESPACE.parent / "retained-precreated-channel"
    os.close(proof.terminal_fd); proof.terminal_fd = None
    channel.rename(original); channel.write_bytes(b""); channel.chmod(0o600)
    proof.terminal_fd = os.open(channel, os.O_RDWR | os.O_NOFOLLOW)
    assert run_cli(digest) == 2 and not proof.launches
    assert channel.read_bytes() == original.read_bytes() == b""
    assert json.loads((supervisor.NAMESPACE / "run.refused.json").read_bytes())["failure"]["contract_code"] == "supervisor_channel_changed"


def test_pre_spec_channel_is_unavailable_for_diagnostics_without_original_binding(proof, monkeypatch):
    digest = prepare(proof)
    def refuse(*args): raise supervisor.ProcessSupervisorRefusal("REFUSED: supervisor_lane_changed")
    monkeypatch.setattr(supervisor, "_guard", refuse)
    assert run_cli(digest) == 2 and not proof.launches
    assert (supervisor.NAMESPACE / "supervisor.jsonl").read_bytes() == b""


def test_terminal_partial_or_no_progress_write_is_never_retried_as_a_second_line(proof, monkeypatch):
    digest = prepare(proof); original = os.write; attempts = []
    def write(fd, raw):
        if fd == proof.terminal_fd:
            attempts.append(True); return 0
        return original(fd, raw)
    monkeypatch.setattr(supervisor.os, "write", write)
    assert run_cli(digest) == 2
    assert attempts == [True] and (supervisor.NAMESPACE / "supervisor.jsonl").read_bytes() == b""
    assert json.loads((supervisor.NAMESPACE / "result.json").read_bytes())["actual_process_exit"] == 0


def test_channel_must_match_spec_original_stamp_even_if_new_file_is_private(proof, monkeypatch):
    digest = prepare(proof)
    channel = supervisor.NAMESPACE / "supervisor.jsonl"
    old = supervisor.NAMESPACE.parent / "retained-original-terminal"
    channel.rename(old)
    channel.write_bytes(b""); channel.chmod(0o600)
    assert run_cli(digest) == 2 and not proof.launches
    # The original FD receives the bounded refusal; the replacement is never
    # accepted or used as the terminal channel.
    raw = old.read_bytes(); result = json.loads(raw)
    assert result["failure"]["contract_code"] == "supervisor_channel_changed"
    # Rename changes the original FD's ctime, so its earlier comparison must
    # refuse before the later named-inode comparison is reached.
    assert result["failure"]["mismatching_fields"] == ["ctime_ns"]
    assert channel.read_bytes() == b""


def test_negative_created_during_last_original_reporter_close_vetoes_witness(proof, monkeypatch):
    digest = prepare(proof); original = supervisor._Namespace.close; calls = []
    def late_negative(self):
        original(self); calls.append(self)
        if len(calls) == 2:
            path = supervisor.NAMESPACE / "run.refused.json"
            path.write_bytes(b'{"fabricated_late_negative":true}'); path.chmod(0o600)
    monkeypatch.setattr(supervisor._Namespace, "close", late_negative)
    assert run_cli(digest) == 2
    assert supervisor._EXITS == {}
    assert terminal()["failure"]["stage"] == "post_context_audit"


def test_dup_failure_is_not_replaced_by_cleanup_failure_and_dup_fd_is_drained(proof, monkeypatch):
    prepare(proof); ns = supervisor._Namespace(create=False)
    real_dup, real_close = os.dup, os.close
    duplicates, closed = [], []
    def dup(fd):
        if duplicates: raise OSError(24, "PRIVATE_ORIGINAL_DUP_FAILURE")
        value = real_dup(fd); duplicates.append(value); return value
    def close(fd):
        result = real_close(fd)
        if fd in duplicates:
            closed.append(fd); raise OSError(5, "PRIVATE_SECONDARY_CLEANUP_FAILURE")
        return result
    monkeypatch.setattr(supervisor.os, "dup", dup)
    monkeypatch.setattr(supervisor.os, "close", close)
    try:
        with pytest.raises(OSError) as caught: ns.duplicate_original()
        assert caught.value.errno == 24
        assert closed == duplicates
    finally: ns.close()


@pytest.mark.parametrize("role", ["fd", "parent"])
def test_original_namespace_close_errno_is_preserved_while_both_anchors_drain(proof, monkeypatch, role):
    digest = prepare(proof)
    original_init, original_close = supervisor._Namespace.__init__, os.close
    contexts, closed, failed = [], [], []
    def initial(self, **kwargs):
        original_init(self, **kwargs); contexts.append((self, self.fd, self.parent))
    def close(fd):
        result = original_close(fd); closed.append(fd)
        if contexts and fd == getattr(contexts[0][0], role) and not failed:
            failed.append(fd); raise OSError(5, "PRIVATE_ORIGINAL_NAMESPACE_CLOSE")
        return result
    monkeypatch.setattr(supervisor._Namespace, "__init__", initial)
    monkeypatch.setattr(supervisor.os, "close", close)
    assert run_cli(digest) == 2
    result = terminal()
    assert result["failure"]["stage"] == "context_cleanup"
    assert result["failure"]["errno_name"] == "EIO" and result["failure"]["contract_code"] is None
    assert failed and set(contexts[0][1:]) <= set(closed)
    assert contexts[0][0].fd is contexts[0][0].parent is None and supervisor._EXITS == {}


@pytest.mark.parametrize("phase,number", [("create", 1), ("write", 28), ("read", 13)])
def test_metadata_primary_failure_survives_secondary_original_fd_close_error(proof, monkeypatch, phase, number):
    prepare(proof); ns = supervisor._Namespace(create=False)
    real_open, real_close = os.open, os.close
    target, closed = [], []
    name = "launch.spec.json" if phase == "read" else "run.refused.json"
    def opened(path, *args, **kwargs):
        fd = real_open(path, *args, **kwargs)
        if path == name: target.append(fd)
        return fd
    def close(fd):
        result = real_close(fd)
        if fd in target:
            closed.append(fd); raise OSError(5, "PRIVATE_SECONDARY_CLOSE")
        return result
    monkeypatch.setattr(supervisor.os, "open", opened)
    monkeypatch.setattr(supervisor.os, "close", close)
    def primary(*args): raise OSError(number, "PRIVATE_PRIMARY_METADATA_ERROR")
    monkeypatch.setattr(supervisor.os, {"create": "fchmod", "write": "write", "read": "read"}[phase], primary)
    try:
        with pytest.raises(OSError) as caught:
            if phase == "create": ns.create(name)
            elif phase == "write": ns.write(name, b"FIXED_FABRICATED_JSON")
            else: ns.read(name)
        assert caught.value.errno == number
        assert closed == target
    finally: ns.close()


@pytest.mark.parametrize("phase", ["read", "write"])
def test_clean_metadata_path_close_failure_still_refuses(proof, monkeypatch, phase):
    prepare(proof); ns = supervisor._Namespace(create=False)
    real_open, real_close = os.open, os.close
    name = "launch.spec.json" if phase == "read" else "run.refused.json"; target = []
    def opened(path, *args, **kwargs):
        fd = real_open(path, *args, **kwargs)
        if path == name: target.append(fd)
        return fd
    def close(fd):
        result = real_close(fd)
        if fd in target: raise OSError(5, "PRIVATE_CLEAN_CLOSE_FAILURE")
        return result
    monkeypatch.setattr(supervisor.os, "open", opened); monkeypatch.setattr(supervisor.os, "close", close)
    try:
        with pytest.raises(OSError) as caught:
            if phase == "read": ns.read(name)
            else: ns.write(name, b"FIXED_FABRICATED_JSON")
        assert caught.value.errno == 5
    finally: ns.close()


def test_code_mismatch_is_not_replaced_by_original_code_fd_close_failure(proof, monkeypatch):
    path = supervisor.ROOT / "fabricated-code.py"; path.write_bytes(b"FABRICATED")
    monkeypatch.setattr(supervisor, "CODE_FILES", (path.name,))
    monkeypatch.setattr(supervisor, "_git", lambda args: b"WRONG_FABRICATED_COMMITTED_BYTES")
    real_close = os.close
    def close(fd): real_close(fd); raise OSError(5, "PRIVATE_CODE_CLOSE")
    monkeypatch.setattr(supervisor.os, "close", close)
    with pytest.raises(supervisor.ProcessSupervisorRefusal, match="code_changed"):
        # Restore the real helper hidden only by the named fabricated fixture.
        import inspect
        tree = ast.parse(Path(supervisor.__file__).read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_code_manifest")
        code = compile(ast.Module(body=[node], type_ignores=[]), str(supervisor.__file__), "exec")
        namespace = dict(supervisor.__dict__); exec(code, namespace)
        namespace["_code_manifest"](HEAD, REMOTE)


def test_unrelated_caller_exception_does_not_hide_clean_close_failure(monkeypatch):
    attempts = []
    def close(fd): attempts.append(fd); raise OSError(5, "PRIVATE_OWN_CLEAN_CLOSE")
    monkeypatch.setattr(supervisor.os, "close", close)
    try: raise ValueError("PRIVATE_UNRELATED_CALLER_EXCEPTION")
    except ValueError:
        with pytest.raises(OSError) as caught: supervisor._close_fd(-999)
    assert caught.value.errno == 5 and attempts == [-999]


@pytest.mark.parametrize("name", ["launch.spec.json", "result.json"])
def test_ambient_caller_exception_cannot_turn_metadata_close_failure_into_success(proof, monkeypatch, name):
    digest = prepare(proof); original_open, original_close = os.open, os.close
    target, failed = [], []
    def opened(path, *args, **kwargs):
        fd = original_open(path, *args, **kwargs)
        if path == name: target.append(fd)
        return fd
    def close(fd):
        value = original_close(fd)
        if fd in target and not failed: failed.append(fd); raise OSError(5, "PRIVATE_RESULT_CLOSE")
        return value
    monkeypatch.setattr(supervisor.os, "open", opened); monkeypatch.setattr(supervisor.os, "close", close)
    try: raise ValueError("PRIVATE_AMBIENT_CALLER")
    except ValueError: assert run_cli(digest) == 2
    # An unread/unclosed launch spec cannot authorize even diagnostic stdout;
    # its original still-held namespace anchors can retain the EIO negative.
    result = (json.loads((supervisor.NAMESPACE / "run.refused.json").read_bytes())
        if name == "launch.spec.json" else terminal())
    assert result["failure"]["errno_name"] == "EIO" and supervisor._EXITS == {}
    if name == "launch.spec.json": assert (supervisor.NAMESPACE / "supervisor.jsonl").read_bytes() == b""


def test_negative_write_own_close_failure_is_not_labelled_published(proof, monkeypatch):
    digest = prepare(proof)
    original_create, original_write, original_close = supervisor._Namespace.create, supervisor._Namespace.write, os.close
    target, failed = [], []
    def create(self, name):
        fd = original_create(self, name)
        if name == "run.refused.json": target.append(fd)
        return fd
    def write(self, name, raw):
        original_write(self, name, raw)
        if name == "result.json":
            with (supervisor.NAMESPACE / "stdout.jsonl").open("r+b") as f: f.write(b"X")
    def close(fd):
        value = original_close(fd)
        if fd in target and not failed: failed.append(fd); raise OSError(5, "PRIVATE_REFUSAL_CLOSE")
        return value
    monkeypatch.setattr(supervisor._Namespace, "create", create)
    monkeypatch.setattr(supervisor._Namespace, "write", write); monkeypatch.setattr(supervisor.os, "close", close)
    assert run_cli(digest) == 2
    result = terminal()
    assert result["failure"]["contract_code"] == "supervisor_file_changed"
    assert failed and result["refusal_record"] == "unavailable"
