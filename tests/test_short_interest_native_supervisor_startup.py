"""Original startup guards with fabricated Git; no launchd/image/provider calls."""
import json
import os
from pathlib import Path
import plistlib
import socket
import stat
import subprocess
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import diagnose_short_interest_native_supervisor_startup as diag

HEAD = "a" * 40
ORIGINAL_POPEN = subprocess.Popen
pytestmark = pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="Explicit POSIX FD semantics")


@pytest.fixture(autouse=True)
def external_denied(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError("actual native/provider/job forbidden")
    monkeypatch.setattr(diag.subprocess, "run", denied); monkeypatch.setattr(diag.subprocess, "Popen", denied)
    monkeypatch.setattr(diag.proof.native.ctypes, "CDLL", denied)
    for name in ("connect", "connect_ex"): monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(diag, "_USED", False); monkeypatch.setattr(diag, "_FAILURES", {})
    monkeypatch.setattr(diag.proof, "_FAILURES", {}); monkeypatch.setattr(diag.proof, "_FIELDS", {})


@pytest.fixture
def fabricated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for module in (diag, diag.proof, diag.worker): monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / diag.PARENT).mkdir(parents=True, mode=0o700)
    manifest = {}
    for ordinal, name in enumerate(diag.CODE_FILES):
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True)
        raw = ("# FABRICATED_CODE_" + str(ordinal) + "\n").encode(); path.write_bytes(raw)
        if name != diag.DRIVER: manifest[name] = hash_bytes(raw)
    monkeypatch.setattr(diag, "TARGET_MANIFEST", manifest)
    old_directory = diag.proof._Directory(diag.proof.BOOTSTRAP, create=True)
    try:
        pin = diag.proof._prepare_status(old_directory)
        raw = canonical_json(diag.proof._spec(diag.TARGET_HEAD, diag.REMOTE, manifest, pin)).encode(); digest = hash_bytes(raw)
        for name, body in (("launch.spec.json", raw), ("job.plist", plistlib.dumps(diag.proof.build_launchd_plist(diag.TARGET_HEAD, diag.REMOTE, digest), sort_keys=True))):
            path = old_directory.path / name; path.write_bytes(body); path.chmod(0o600)
    finally: old_directory.close()
    monkeypatch.setattr(diag, "TARGET_SPEC", digest)
    monkeypatch.setattr(diag, "POLICY_SHA256", hash_payload(diag.policy()))
    h = SimpleNamespace(calls=[], fail_role=None, fail_code=128, malformed_status=False, missing_result=False,
        before_git=None, after_git=None, exception=None)
    def run(args, **kwargs):
        assert args[:1] == ["git"] and kwargs["timeout"] == 30 and kwargs["check"] is False
        role = diag._git_role(args[1:], HEAD); assert role is not None
        h.calls.append(role)
        if h.before_git: h.before_git(role)
        if h.missing_result: raise OSError(13, "PRIVATE_GIT_LAUNCH")
        if role[0] == "root": raw = (str(tmp_path) + "\n").encode()
        elif role[0] == "status":
            raw = ("# branch.oid " + HEAD + "\n# branch.head " + diag.worker.BRANCH + "\n").encode()
            if h.malformed_status: raw += b"1 PRIVATE_DIRTY_VALUE\n"
        elif role[0] == "tracking": raw = (diag.REMOTE + "\n").encode()
        elif role[0] == "actual_matching_ref": raw = (diag.REMOTE + "\t" + diag.worker.REF + "\n").encode()
        else:
            revision, _, name = args[2].partition(":"); assert revision == HEAD
            raw = (tmp_path / name).read_bytes()
        result = subprocess.CompletedProcess(args, h.fail_code if role[0] == h.fail_role else 0,
            stdout=raw, stderr=b"PRIVATE_STDERR_NEVER_EMIT")
        if h.after_git: h.after_git(role)
        return result
    monkeypatch.setattr(diag.subprocess, "run", run)
    h.old_status = (tmp_path / diag.PARENT / diag.proof.STATUS_NAME).read_bytes()
    return h


def prepare(): return diag.prepare_readonly(HEAD, diag.REMOTE)["spec_sha256"]


def cli(digest): return diag.main(["run-readonly", "--head", HEAD, "--remote", diag.REMOTE, "--spec-sha256", digest])


def observation():
    raw = (diag.ROOT / diag.PARENT / diag.STATUS).read_bytes()
    assert len(raw) <= 2048 and raw.count(b"\n") == 1
    assert b"PRIVATE" not in raw
    return json.loads(raw)


def test_pending_policy_refuses_before_git_or_config(tmp_path, monkeypatch):
    monkeypatch.setattr(diag, "POLICY_SHA256", "PENDING")
    with pytest.raises(diag.StartupRefusal, match="unregistered"): diag.prepare_readonly(HEAD, diag.REMOTE)
    assert not (tmp_path / diag.BOOTSTRAP).exists()


def test_canonical_config_and_original_status_precede_genuine_original_git_failure(fabricated):
    digest = prepare(); fabricated.calls.clear(); fabricated.fail_role = "root"
    assert cli(digest) == 2 and fabricated.calls == [("root", 0)]
    detail = observation()["failure"]
    assert detail["stage"] == "live_guard"
    assert detail["original_Git"] == {"role": "root", "code_ordinal": 0, "returncode": 128}
    assert observation()["authority"]["live_lane_admitted"] is False


def test_two_heads_and_all_six_original_live_code_files_are_kept_distinct(fabricated):
    digest = prepare(); fabricated.calls.clear()
    assert cli(digest) == 0
    assert {role[1] for role in fabricated.calls if role[0] == "code_file"} == set(range(1, 7))
    result = observation()
    assert result["status"] == "readonly_predicates_passed_observation_only" and result["failure"] is None
    assert not any(result["authority"][key] for key in ("source_dispatch_authority", "native_proof_authority", "old_proof_admitted", "supervisor_process_exit_attested"))
    assert (diag.ROOT / diag.PARENT / diag.proof.STATUS_NAME).read_bytes() == fabricated.old_status
    assert not (diag.ROOT / diag.PARENT / diag.proof.DOMAIN).exists()


@pytest.mark.parametrize("role", ["status", "tracking", "actual_matching_ref", "code_file"])
def test_original_git_frame_projects_only_role_and_actual_returncode(fabricated, role):
    digest = prepare(); fabricated.fail_role = role
    assert cli(digest) == 2
    found = observation()["failure"]["original_Git"]
    assert found["role"] == role and found["returncode"] == 128
    assert found["code_ordinal"] == (1 if role == "code_file" else 0)


def test_missing_completedprocess_is_null_never_zero(fabricated):
    digest = prepare(); fabricated.missing_result = True
    assert cli(digest) == 2
    assert observation()["failure"]["original_Git"] == {"role": "root", "code_ordinal": 0, "returncode": None}


def test_later_lane_predicate_failure_does_not_borrow_a_successful_git_frame(fabricated):
    digest = prepare(); fabricated.malformed_status = True
    assert cli(digest) == 2
    assert observation()["failure"]["original_Git"] == {"role": None, "code_ordinal": None, "returncode": None}


def test_caller_completedprocess_and_similarly_named_frame_cannot_forge_projection():
    def fake_git(arguments):
        result = subprocess.CompletedProcess(["git", *arguments], 0)
        raise RuntimeError("PRIVATE_FAKE")
    try: fake_git(["rev-parse", "--show-toplevel"])
    except RuntimeError as error:
        assert diag._git_failure(error, HEAD) == {"role": None, "code_ordinal": None, "returncode": None}


@pytest.mark.parametrize("hazard", ["digest", "extra_field", "wrong_runtime_head", "wrong_target_head", "wrong_manifest"])
def test_invalid_config_never_reaches_git_or_status_write(fabricated, hazard):
    digest = prepare(); fabricated.calls.clear(); path = diag.ROOT / diag.PARENT / diag.BOOTSTRAP / "launch.spec.json"
    if hazard == "digest": digest = "c" * 64
    else:
        payload = json.loads(path.read_bytes())
        if hazard == "extra_field": payload["unrecognized"] = False
        elif hazard == "wrong_runtime_head": payload["runtime_head"] = diag.TARGET_HEAD
        elif hazard == "wrong_target_head": payload["target_head"] = HEAD
        else: payload["code_manifest"][diag.proof.DRIVER] = "c" * 64
        raw = canonical_json(payload).encode(); path.write_bytes(raw); digest = hash_bytes(raw)
    assert cli(digest) == 2 and not fabricated.calls
    assert (diag.ROOT / diag.PARENT / diag.STATUS).read_bytes() == b""


@pytest.mark.parametrize("hazard", ["replace", "symlink", "fifo", "mode", "hardlink", "nonempty"])
def test_untrusted_status_never_opens_or_runs_git(fabricated, hazard):
    digest = prepare(); fabricated.calls.clear(); path = diag.ROOT / diag.PARENT / diag.STATUS
    if hazard in ("replace", "symlink", "fifo"):
        old = diag.ROOT / "preserved-original-status"; path.rename(old)
        if hazard == "replace": path.write_bytes(b""); path.chmod(0o600)
        elif hazard == "symlink": path.symlink_to(old)
        else: os.mkfifo(path, 0o600)
    elif hazard == "mode": path.chmod(0o644)
    elif hazard == "hardlink": os.link(path, diag.ROOT / "extra-status-link")
    else: path.write_bytes(b"EXISTING")
    assert cli(digest) == 2 and not fabricated.calls


def test_job_is_one_shot_no_native_domain_and_no_spec_job_hash_cycle(fabricated):
    digest = prepare(); path = diag.ROOT / diag.PARENT / diag.BOOTSTRAP
    spec = json.loads((path / "launch.spec.json").read_bytes()); job = plistlib.loads((path / "job.plist").read_bytes())
    assert set(os.listdir(path)) == {"launch.spec.json", "job.plist"}
    assert "job_sha256" not in spec and job == diag.build_launchd_plist(HEAD, diag.REMOTE, digest)
    assert job["KeepAlive"] is False and job["RunAtLoad"] is True and job["StandardOutPath"] == job["StandardErrorPath"] == "/dev/null"
    assert not {"StartInterval", "StartCalendarInterval", "WatchPaths", "QueueDirectories"} & set(job)
    with pytest.raises(diag.proof.NativeProofRefusal): prepare()


def test_readonly_fence_denies_native_network_non_git_and_file_creation(fabricated):
    with diag._fence(HEAD, readonly=True):
        for action in (lambda: socket.create_connection(("invalid", 1)), lambda: socket.getaddrinfo("invalid", 1),
            lambda: diag.proof._Volume(None), lambda: diag.subprocess.run(["/usr/bin/hdiutil", "info"]),
            lambda: os.open("unregistered", os.O_RDWR | os.O_CREAT, 0o600), lambda: Path("unregistered").write_bytes(b"X")):
            with pytest.raises(diag.StartupRefusal, match="forbidden"): action()
    assert not (diag.ROOT / "unregistered").exists()


class ProjectedStat:
    def __init__(self, original, **changes): self.original, self.changes = original, changes
    def __getattr__(self, name): return self.changes.get(name, getattr(self.original, name))


def test_original_code_ctime_change_during_last_git_callback_vetoes_success(fabricated, monkeypatch):
    digest = prepare(); inode = (diag.ROOT / diag.DRIVER).lstat().st_ino
    real_stat, real_fstat, changed = os.stat, os.fstat, []
    def observed(info): return ProjectedStat(info, st_ctime_ns=info.st_ctime_ns + 1) if changed and info.st_ino == inode else info
    fabricated.after_git = lambda role: changed.append(True) if role == ("code_file", 6) else None
    monkeypatch.setattr(diag.os, "stat", lambda *a, **k: observed(real_stat(*a, **k)))
    monkeypatch.setattr(diag.os, "fstat", lambda fd: observed(real_fstat(fd)))
    assert cli(digest) == 2
    assert observation()["failure"]["mismatching_fields"] == ["ctime_ns"]


def test_historical_live_bootstrap_full9_drift_is_not_rebaselined(fabricated, monkeypatch):
    digest = prepare(); inode = (diag.ROOT / diag.PARENT / diag.proof.BOOTSTRAP / "launch.spec.json").lstat().st_ino
    real_stat, real_fstat, changed, calls = os.stat, os.fstat, [], []
    def observed(info): return ProjectedStat(info, st_ctime_ns=info.st_ctime_ns + 1) if changed and info.st_ino == inode else info
    def after(role):
        if role == ("code_file", 6):
            calls.append(True)
            if len(calls) == 2: changed.append(True)
    fabricated.after_git = after
    monkeypatch.setattr(diag.os, "stat", lambda *a, **k: observed(real_stat(*a, **k)))
    monkeypatch.setattr(diag.os, "fstat", lambda fd: observed(real_fstat(fd)))
    assert cli(digest) == 2
    assert observation()["failure"]["mismatching_fields"] == ["ctime_ns"]


@pytest.mark.parametrize("failure", ["zero_write", "fsync", "close"])
def test_status_io_failure_never_claims_success_or_retries(fabricated, monkeypatch, failure):
    digest = prepare(); inode = (diag.ROOT / diag.PARENT / diag.STATUS).lstat().st_ino
    real_write, real_fsync, real_close, calls = os.write, os.fsync, os.close, []
    def targeted(fd): return os.fstat(fd).st_ino == inode
    def write(fd, body):
        if targeted(fd) and failure == "zero_write": calls.append(True); return 0
        return real_write(fd, body)
    def fsync(fd):
        if targeted(fd) and failure == "fsync": calls.append(True); raise OSError(5, "PRIVATE_STATUS_FSYNC")
        return real_fsync(fd)
    def close(fd):
        is_status = targeted(fd); value = real_close(fd)
        if is_status and failure == "close": calls.append(True); raise OSError(5, "PRIVATE_STATUS_CLOSE")
        return value
    monkeypatch.setattr(diag.os, "write", write); monkeypatch.setattr(diag.os, "fsync", fsync); monkeypatch.setattr(diag.os, "close", close)
    assert cli(digest) == 2 and calls == [True]
    raw = (diag.ROOT / diag.PARENT / diag.STATUS).read_bytes()
    if failure == "zero_write": assert raw == b""
    else: assert json.loads(raw)["authority"]["supervisor_process_exit_attested"] is False


def test_first_actual_git_cause_survives_cleanup_error(fabricated, monkeypatch):
    digest = prepare(); fabricated.fail_role = "root"
    original, failures = diag._Inputs.close, []
    def close(self): original(self); failures.append(True); raise OSError(5, "PRIVATE_CLEANUP")
    monkeypatch.setattr(diag._Inputs, "close", close)
    assert cli(digest) == 2 and failures == [True]
    assert observation()["failure"]["original_Git"]["returncode"] == 128
    assert observation()["failure"]["errno_name"] is None


def test_clean_context_close_failure_is_negative_even_under_ambient_exception(fabricated, monkeypatch):
    digest = prepare(); original, failures = diag._Inputs.close, []
    def close(self): original(self); failures.append(True); raise OSError(5, "PRIVATE_CLEAN_CLOSE")
    monkeypatch.setattr(diag._Inputs, "close", close)
    try: raise RuntimeError("UNRELATED")
    except RuntimeError: assert cli(digest) == 2
    assert failures == [True] and observation()["failure"]["errno_name"] == "EIO"


def test_elapsed_acceptance_catches_late_cleanup_without_claiming_hard_cutoff(fabricated, monkeypatch):
    digest = prepare(); original, elapsed = diag._Inputs.close, [10.0]
    monkeypatch.setattr(diag.time, "monotonic", lambda: elapsed[0])
    def close(self): original(self); elapsed[0] += diag.MAX_SECONDS + 1
    monkeypatch.setattr(diag._Inputs, "close", close)
    assert cli(digest) == 2
    # A deadline can prevent even diagnostic publication; no zero/source claim.
    assert "not_hard_wall_kill" in diag.policy()["deadline"]


def test_fixed_status_payload_refuses_arbitrary_exception_text(fabricated):
    digest = prepare(); directory = diag.proof._Directory(diag.BOOTSTRAP, create=False)
    pin = json.loads((directory.path / "launch.spec.json").read_bytes())["status_original_identity"]
    status = diag._Status()
    try:
        status.bind(directory, pin)
        with pytest.raises(diag.StartupRefusal): status.emit({"exception": "PRIVATE_SECRET"})
    finally: status.close(); directory.close()
    assert (diag.ROOT / diag.PARENT / diag.STATUS).read_bytes() == b""


def test_subprocess_executable_or_shell_escape_is_not_an_allowed_git_command(fabricated):
    kwargs = {"cwd": diag.ROOT, "stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL, "env": diag.worker._environment(), "check": False, "timeout": 30}
    with diag._fence(HEAD, readonly=True):
        for extra in ({"executable": "/usr/bin/hdiutil"}, {"shell": True}):
            with pytest.raises(diag.StartupRefusal, match="forbidden"):
                diag.subprocess.run(["git", "rev-parse", "--show-toplevel"], **kwargs, **extra)


def test_configuration_full9_change_during_first_read_cannot_reach_status_or_git(fabricated, monkeypatch):
    digest = prepare(); fabricated.calls.clear(); path = diag.ROOT / diag.PARENT / diag.BOOTSTRAP / "launch.spec.json"
    inode = path.lstat().st_ino; real_read, real_stat, real_fstat, changed = os.read, os.stat, os.fstat, []
    def observed(info): return ProjectedStat(info, st_ctime_ns=info.st_ctime_ns + 1) if changed and info.st_ino == inode else info
    def read(fd, maximum):
        body = real_read(fd, maximum)
        if real_fstat(fd).st_ino == inode: changed.append(True)
        return body
    monkeypatch.setattr(diag.os, "read", read)
    monkeypatch.setattr(diag.os, "stat", lambda *a, **k: observed(real_stat(*a, **k)))
    monkeypatch.setattr(diag.os, "fstat", lambda fd: observed(real_fstat(fd)))
    assert cli(digest) == 2 and changed and not fabricated.calls
    assert (diag.ROOT / diag.PARENT / diag.STATUS).read_bytes() == b""


def test_owned_status_exact_open_flags_and_all_original_fds_close(fabricated, monkeypatch):
    digest = prepare(); real_open, real_close, real_dup = os.open, os.close, os.dup
    live, status_opens = set(), []
    def opened(path, flags, *args, **kwargs):
        if path == diag.STATUS:
            assert flags == os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            assert kwargs.keys() == {"dir_fd"}
            assert not fabricated.calls
            status_opens.append(True)
        fd = real_open(path, flags, *args, **kwargs); live.add(fd); return fd
    def duplicate(fd):
        value = real_dup(fd); live.add(value); return value
    def close(fd):
        value = real_close(fd); live.discard(fd); return value
    fabricated.calls.clear()
    monkeypatch.setattr(diag.os, "open", opened); monkeypatch.setattr(diag.os, "dup", duplicate); monkeypatch.setattr(diag.os, "close", close)
    assert cli(digest) == 0 and status_opens == [True] and live == set()


def test_overlarge_config_is_not_parsed_and_no_channel_or_git_is_adopted(fabricated):
    digest = prepare(); fabricated.calls.clear(); path = diag.ROOT / diag.PARENT / diag.BOOTSTRAP / "launch.spec.json"
    raw = b"X" * (diag.MAX_CONFIG + 1); path.write_bytes(raw)
    assert cli(hash_bytes(raw)) == 2 and not fabricated.calls
    assert (diag.ROOT / diag.PARENT / diag.STATUS).read_bytes() == b""


@pytest.mark.parametrize("fake_result", ["wrong_argv", "subclass", "bool_returncode"])
def test_nonoriginal_completedprocess_projection_cannot_invent_zero(fabricated, monkeypatch, fake_result):
    digest = prepare(); original_run = diag.subprocess.run
    class Subclass(subprocess.CompletedProcess): pass
    def run(args, **kwargs):
        result = original_run(args, **kwargs)
        if fake_result == "wrong_argv": return subprocess.CompletedProcess(["git", "PRIVATE_FORGED_ARG"], 128, stdout=b"")
        if fake_result == "subclass": return Subclass(args, 128, stdout=b"")
        return subprocess.CompletedProcess(args, False, stdout=b"")
    monkeypatch.setattr(diag.subprocess, "run", run)
    assert cli(digest) == 2
    assert observation()["failure"]["original_Git"]["returncode"] is None


def test_diagnostic_namespace_has_no_capture_or_native_domain_entrypoint(fabricated):
    digest = prepare()
    assert cli(digest) == 0
    assert not hasattr(diag, "capture") and not hasattr(diag, "DOMAIN")
    assert not (diag.ROOT / diag.PARENT / diag.proof.DOMAIN).exists()
    assert all(observation()["authority"][key] == 0 for key in ("provider_HTTP", "credential_reads", "source_STARTs", "source_bytes", "native_commands", "new_source_claims"))


def test_original_stdlib_git_devnull_adapter_is_allowed_without_launching_child(fabricated):
    child = object.__new__(ORIGINAL_POPEN); fd = None
    try:
        with diag._fence(HEAD, readonly=True):
            fd = child._get_devnull()
            assert stat.S_ISCHR(os.fstat(fd).st_mode)
    finally:
        if fd is not None: os.close(fd)


@pytest.mark.parametrize("flags", [os.O_RDWR | os.O_CREAT, os.O_RDWR | os.O_TRUNC, os.O_WRONLY, os.O_RDWR | os.O_APPEND])
def test_devnull_exception_cannot_allow_other_write_open_flags(fabricated, flags):
    with diag._fence(HEAD, readonly=True):
        with pytest.raises(diag.StartupRefusal, match="forbidden"): os.open("/dev/null", flags)


def test_unscanned_trace_tail_cannot_claim_a_unique_original_git_frame(fabricated):
    from types import TracebackType
    fabricated.fail_role = "root"
    try: diag.worker._git(["rev-parse", "--show-toplevel"])
    except diag.worker.ProcessSupervisorRefusal as error:
        first = error.__traceback__; original = first
        while original.tb_frame.f_code is not diag._GIT_CODE: original = original.tb_next
        tail = None
        for unused in range(129): tail = TracebackType(tail, first.tb_frame, first.tb_lasti, first.tb_lineno)
        try:
            error.__traceback__ = TracebackType(tail, original.tb_frame, original.tb_lasti, original.tb_lineno)
            projected = diag._git_failure(error, HEAD)
        finally: error.__traceback__ = first
    assert projected == {"role": None, "code_ordinal": None, "returncode": None}


def test_prepare_refuses_same_size_job_mutation_after_original_writer_close(fabricated, monkeypatch):
    original_open, original_close, writers, changed = os.open, os.close, set(), []
    def opened(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        if path == "job.plist" and flags & os.O_CREAT: writers.add(fd)
        return fd
    def close(fd):
        is_writer = fd in writers; writers.discard(fd); result = original_close(fd)
        if is_writer:
            path = diag.ROOT / diag.PARENT / diag.BOOTSTRAP / "job.plist"
            raw = path.read_bytes(); path.write_bytes(b"X" + raw[1:]); changed.append(True)
        return result
    monkeypatch.setattr(diag.os, "open", opened); monkeypatch.setattr(diag.os, "close", close)
    with pytest.raises(diag.StartupRefusal, match="config"): prepare()
    assert changed == [True]


def test_config_only_cross_phase_ctime_drift_is_not_an_evidence_seal(fabricated, monkeypatch):
    digest = prepare(); inode = (diag.ROOT / diag.PARENT / diag.BOOTSTRAP / "launch.spec.json").lstat().st_ino
    real_stat, real_fstat, changed = os.stat, os.fstat, []
    def observed(info): return ProjectedStat(info, st_ctime_ns=info.st_ctime_ns + 1) if changed and info.st_ino == inode else info
    fabricated.after_git = lambda role: changed.append(True)
    monkeypatch.setattr(diag.os, "stat", lambda *a, **k: observed(real_stat(*a, **k)))
    monkeypatch.setattr(diag.os, "fstat", lambda fd: observed(real_fstat(fd)))
    assert cli(digest) == 0 and changed
    assert observation()["authority"]["source_dispatch_authority"] is False


@pytest.fixture
def config_inputs(fabricated):
    prepare(); directory = diag.proof._Directory(diag.BOOTSTRAP, create=False); inputs = diag._Inputs(directory)
    for name in inputs.ROLES: inputs.read(name)
    try: yield inputs, directory
    finally: inputs.close(); directory.close()


@pytest.mark.parametrize("hazard", ["bytes", "inode", "mode", "hardlink", "symlink", "fifo"])
def test_config_reauthentication_never_relearns_original_pin_or_bytes(config_inputs, hazard):
    inputs, directory = config_inputs; path = directory.path / "launch.spec.json"; original = inputs.rows.copy()
    raw = path.read_bytes()
    if hazard == "bytes": path.write_bytes(b"X" + raw[1:])
    elif hazard == "mode": path.chmod(0o644)
    elif hazard == "hardlink": os.link(path, directory.path.parent / "extra-link")
    else:
        retained = directory.path.parent / "retained-original-config"; path.rename(retained)
        if hazard == "inode": path.write_bytes(raw); path.chmod(0o600)
        elif hazard == "symlink": path.symlink_to(retained)
        else: os.mkfifo(path, 0o600)
    with pytest.raises((diag.StartupRefusal, diag.proof.NativeProofRefusal)): inputs.audit()
    assert inputs.rows == original


@pytest.mark.parametrize("hazard", ["ctime", "bytes"])
def test_each_config_read_close_is_inside_original_full9_barrier(config_inputs, monkeypatch, hazard):
    inputs, directory = config_inputs; path = directory.path / "launch.spec.json"; inode = path.lstat().st_ino
    real_open, real_close, real_stat, real_fstat = os.open, os.close, os.stat, os.fstat
    readers, changed = set(), []
    def observed(info): return ProjectedStat(info, st_ctime_ns=info.st_ctime_ns + 1) if changed and info.st_ino == inode else info
    def opened(name, flags, *args, **kwargs):
        fd = real_open(name, flags, *args, **kwargs)
        if real_fstat(fd).st_ino == inode: readers.add(fd)
        return fd
    def close(fd):
        target = fd in readers; readers.discard(fd); result = real_close(fd)
        if target:
            changed.append(True)
            if hazard == "bytes":
                raw = path.read_bytes(); path.write_bytes(b"X" + raw[1:])
        return result
    monkeypatch.setattr(diag.os, "open", opened); monkeypatch.setattr(diag.os, "close", close)
    monkeypatch.setattr(diag.os, "stat", lambda *a, **k: observed(real_stat(*a, **k)))
    monkeypatch.setattr(diag.os, "fstat", lambda fd: observed(real_fstat(fd)))
    with pytest.raises(diag.proof.NativeProofRefusal, match="stamp"): inputs.audit()
    assert changed == [True]


def test_prepare_never_adopts_a_replacement_after_original_creator_close(fabricated, monkeypatch):
    real_open, real_close, writers, changed = os.open, os.close, set(), []
    def opened(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if path == "job.plist" and flags & os.O_CREAT: writers.add(fd)
        return fd
    def close(fd):
        target = fd in writers; writers.discard(fd); result = real_close(fd)
        if target:
            path = diag.ROOT / diag.PARENT / diag.BOOTSTRAP / "job.plist"; raw = path.read_bytes()
            path.rename(diag.ROOT / "retained-creator-job"); path.write_bytes(raw); path.chmod(0o600); changed.append(True)
        return result
    monkeypatch.setattr(diag.os, "open", opened); monkeypatch.setattr(diag.os, "close", close)
    with pytest.raises(diag.StartupRefusal, match="config"): prepare()
    assert changed == [True]


def test_timestamp_only_change_after_config_writer_close_still_requires_canonical_read(fabricated, monkeypatch):
    real_open, real_close, real_stat, real_fstat = os.open, os.close, os.stat, os.fstat
    writers, drifted = {}, set()
    def observed(info): return ProjectedStat(info, st_ctime_ns=info.st_ctime_ns + 1) if info.st_ino in drifted else info
    def opened(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if path in ("launch.spec.json", "job.plist") and flags & os.O_CREAT: writers[fd] = real_fstat(fd).st_ino
        return fd
    def close(fd):
        inode = writers.pop(fd, None); result = real_close(fd)
        if inode is not None: drifted.add(inode)
        return result
    monkeypatch.setattr(diag.os, "open", opened); monkeypatch.setattr(diag.os, "close", close)
    monkeypatch.setattr(diag.os, "stat", lambda *a, **k: observed(real_stat(*a, **k)))
    monkeypatch.setattr(diag.os, "fstat", lambda fd: observed(real_fstat(fd)))
    assert len(prepare()) == 64 and len(drifted) == 2


def test_config_roles_are_exact_and_expose_no_source_evidence_conversion(config_inputs):
    inputs, unused = config_inputs
    assert inputs.ROLES == ("launch.spec.json", "job.plist")
    for name in ("seal", "inventory", "capture", "source", "authorize"): assert not hasattr(inputs, name)
    with pytest.raises(diag.StartupRefusal): inputs.read("other.json")


def test_prepare_carries_original_creator_pin_between_separate_config_operations(fabricated, monkeypatch):
    original, changed = diag._config_write, []
    def write(directory, name, raw):
        pin = original(directory, name, raw)
        if name == "job.plist":
            path = directory.path / "launch.spec.json"; body = path.read_bytes()
            path.rename(diag.ROOT / "retained-original-spec"); path.write_bytes(body); path.chmod(0o600); changed.append(True)
        return pin
    monkeypatch.setattr(diag, "_config_write", write)
    with pytest.raises(diag.StartupRefusal, match="config"): prepare()
    assert changed == [True]
