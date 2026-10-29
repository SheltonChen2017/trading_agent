"""Original startup guards with fabricated Git; no launchd/image/provider calls."""
import json
import errno
import sys
import os
from pathlib import Path
import plistlib
import socket
import stat
try:
    import termios
except ImportError:
    termios = None
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
    monkeypatch.setattr(diag, "_PREPARED_INPUTS", {}); monkeypatch.setattr(diag, "_CONTROLLER_HELD", [])
    monkeypatch.setattr(diag.proof, "_FAILURES", {}); monkeypatch.setattr(diag.proof, "_FIELDS", {})


@pytest.fixture(autouse=True)
def private_observer_endpoint(monkeypatch):
    global _OBSERVER, _OBSERVER_MASTER
    master, slave = os.openpty(); os.set_blocking(master, False)
    settings = termios.tcgetattr(slave); settings[1] &= ~termios.ONLCR; settings[3] &= ~termios.ECHO
    termios.tcsetattr(slave, termios.TCSANOW, settings)
    _OBSERVER = {"nonce": "1" * 32, "terminal": list(diag._tty_pin(slave)), "slave_path": os.ttyname(slave)}; _OBSERVER_MASTER = master
    monkeypatch.setattr(diag, "_observer_fd", lambda: slave)
    try: yield master, slave
    finally: os.close(slave); os.close(master)


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


def prepare(): return diag.prepare_readonly(HEAD, diag.REMOTE, _OBSERVER)["spec_sha256"]


def cli(digest): return diag.main(["run-readonly", "--head", HEAD, "--remote", diag.REMOTE, "--spec-sha256", digest, "--observer", canonical_json(_OBSERVER)])


def observation():
    raw = (diag.ROOT / diag.PARENT / diag.STATUS).read_bytes()
    assert len(raw) <= 2048 and raw.count(b"\n") == 1
    assert b"PRIVATE" not in raw
    return json.loads(raw)


def test_pending_policy_refuses_before_git_or_config(tmp_path, monkeypatch):
    monkeypatch.setattr(diag, "POLICY_SHA256", "PENDING")
    with pytest.raises(diag.StartupRefusal, match="unregistered"): diag.prepare_readonly(HEAD, diag.REMOTE, _OBSERVER)
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
    assert "job_sha256" not in spec and job == diag.build_launchd_plist(HEAD, diag.REMOTE, digest, _OBSERVER)
    assert job["KeepAlive"] is False and job["RunAtLoad"] is False and job["StandardOutPath"] == "/dev/null" and job["StandardErrorPath"] == _OBSERVER["slave_path"]
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


def tty_bytes():
    raw = b""
    while True:
        try: block = os.read(_OBSERVER_MASTER, 4096)
        except BlockingIOError: break
        if not block: break
        raw += block
    return raw


@pytest.mark.parametrize("early", ["registration", "fence", "clock", "config"])
def test_outer_observer_reports_failure_before_subject_channel_exists(fabricated, monkeypatch, early):
    from contextlib import contextmanager
    digest = "c" * 64
    if early == "registration": monkeypatch.setattr(diag, "POLICY_SHA256", "PENDING")
    elif early == "fence":
        @contextmanager
        def refused(*args, **kwargs): raise diag.StartupRefusal("REFUSED: startup_forbidden"); yield
        monkeypatch.setattr(diag, "_fence", refused)
    elif early == "clock": monkeypatch.setattr(diag, "_Clock", lambda: (_ for _ in ()).throw(diag.StartupRefusal("REFUSED: startup_clock")))
    assert cli(digest) == 2
    result = diag.filter_observer(tty_bytes(), _OBSERVER, digest, os.getpid())
    assert result["status"] == "refused" and result["authority"]["source_dispatch_authority"] is False
    assert not (diag.ROOT / diag.PARENT / diag.STATUS).exists()


@pytest.mark.parametrize("hazard", ["nonce", "digest", "pid", "duplicate", "partial", "unrelated", "raw_prefix", "foreign_field"])
def test_private_raw_filter_never_emits_unrelated_or_uncorrelated_text(fabricated, hazard):
    value = {"schema": "si-startup-PTY-observation-v7", "nonce": _OBSERVER["nonce"], "spec_sha256": "c" * 64,
        "pid": 456, "status": "readonly_predicates_passed_observation_only", "failure": None, "authority": diag.authority()}
    if hazard == "nonce": value["nonce"] = "2" * 32
    elif hazard == "digest": value["spec_sha256"] = "d" * 64
    elif hazard == "pid": value["pid"] = 457
    elif hazard == "foreign_field": value["raw"] = "PRIVATE_STARTUP_TEXT"
    raw = diag._wire_encode(value)
    if hazard == "duplicate": raw += raw
    elif hazard == "partial": raw = raw[:-1]
    elif hazard == "unrelated": raw = b"PRIVATE_PYTHON_TRACEBACK\n"
    elif hazard == "raw_prefix": raw = b"PRIVATE_DEBUG_BANNER\n" + raw
    result = diag.filter_observer(raw, _OBSERVER, "c" * 64, 456)
    assert result["status"] == "observer_unavailable" and "PRIVATE" not in canonical_json(result)


def test_observer_one_nonblocking_attempt_no_fsync_retry_or_readback(fabricated, monkeypatch):
    observer = diag._Observer(_OBSERVER, "c" * 64); fd = observer.fd; original_write, calls = os.write, []
    def write(target, raw):
        if target == fd: calls.append(len(raw)); return len(raw) - 1
        return original_write(target, raw)
    monkeypatch.setattr(diag.os, "write", write)
    monkeypatch.setattr(diag.os, "fsync", lambda target: pytest.fail("observer fsync is forbidden"))
    with pytest.raises(diag.StartupRefusal): observer.emit(None)
    with pytest.raises(diag.StartupRefusal): observer.emit(None)
    assert len(calls) == 1 and not os.get_blocking(fd)


def test_observer_rejects_wrong_endpoint_and_arbitrary_failure_payload(fabricated):
    wrong = {**_OBSERVER, "terminal": [v + 1 for v in _OBSERVER["terminal"]]}
    with pytest.raises(diag.StartupRefusal): diag._Observer(wrong, "c" * 64)
    observer = diag._Observer(_OBSERVER, "c" * 64)
    with pytest.raises(diag.StartupRefusal): observer.emit({"exception": "PRIVATE_RAW"})
    assert tty_bytes() == b""


def test_job_initial_start_is_explicit_and_has_no_restart_or_auto_trigger(fabricated):
    digest = prepare(); job = diag.build_launchd_plist(HEAD, diag.REMOTE, digest, _OBSERVER)
    assert job["RunAtLoad"] is job["KeepAlive"] is False
    assert not {"StartInterval", "StartCalendarInterval", "WatchPaths", "QueueDirectories", "Sockets"} & set(job)
    assert job["ProgramArguments"][-2:] == ["--observer", canonical_json(_OBSERVER)]
    with pytest.raises(diag.StartupRefusal): diag._launch_argv("debug")
    assert diag._launch_argv("start") == [diag.LAUNCHCTL, "kickstart", "-p", diag._target()]
    assert "-k" not in diag._launch_argv("start")
    with pytest.raises(diag.StartupRefusal): diag._launch_argv("restart")


def kernel_bytes(runs=0, *, running=False, pid=None, exit_code=None):
    raw = (diag._target() + " = {\n\tpath = " + str(diag.ROOT / diag.PARENT / diag.BOOTSTRAP / "job.plist") + "\n\tstate = ").encode() + (b"running" if running else b"not running") + b"\n\tactive count = " + (b"1" if running else b"0") + b"\n\truns = " + str(runs).encode() + b"\n"
    if pid is not None: raw += b"\tpid = " + str(pid).encode() + b"\n"
    if exit_code is not None: raw += b"\tlast exit code = " + str(exit_code).encode() + b"\n"
    elif runs == 0 and not running and pid is None: raw += b"\tlast exit code = (never exited)\n"
    return raw + b"\tcoalition = {\n\t\tstate = active\n\t\tactive count = 1\n\t}\n}\n"


def test_kernel_parser_uses_top_level_fields_not_nested_coalitions():
    result = diag._kernel(kernel_bytes())
    assert result == {"runs": 0, "running": False, "active_count": 0, "pid": None, "exit": None}
    for raw in (b"", kernel_bytes().replace(b"\tstate = not running\n", b""), kernel_bytes() + b"\truns = 0\n"):
        with pytest.raises(diag.StartupRefusal): diag._kernel(raw)


@pytest.fixture
def controller_child(fabricated, monkeypatch):
    digest = prepare()
    original_run, calls = diag.subprocess.run, []
    h = SimpleNamespace(digest=digest, pins=diag._creator_pins(HEAD, diag.REMOTE, digest, _OBSERVER), calls=calls, query_states=[kernel_bytes(), kernel_bytes(), kernel_bytes(), kernel_bytes(1, exit_code=2)],
        debug_code=0, start_code=0, target_pid=456)
    def run(args, **kwargs):
        if args[:1] == ["git"]: return original_run(args, **kwargs)
        role = next((name for name in ("query", "start", "load") if args == diag._launch_argv(name)), None)
        assert role is not None and kwargs["shell"] is False and kwargs["timeout"] == 30
        calls.append(role)
        if role == "query": body, code = h.query_states.pop(0), 0
        else: body, code = str(h.target_pid).encode() + b"\n", h.start_code
        return subprocess.CompletedProcess(args, code, stdout=body, stderr=b"PRIVATE_CONTROL_TEXT")
    monkeypatch.setattr(diag.subprocess, "run", run)
    monkeypatch.setattr(diag, "_tty_check", lambda fd, value: tuple(value["terminal"]))
    monkeypatch.setattr(diag.os, "getsid", lambda pid: os.getpid())
    monkeypatch.setattr(diag.fcntl, "ioctl", lambda *args: pytest.fail("controller must not acquire a controlling terminal"))
    return h


def test_persistent_control_child_orders_barrier_single_start_and_terminal_ack(controller_child):
    read_fd, control_fd = os.pipe(); ack_fd, ack_write = os.pipe(); os.write(ack_write, b"12"); os.close(ack_write)
    try:
        result = diag.control_readonly(HEAD, diag.REMOTE, controller_child.digest, _OBSERVER, control_fd, ack_fd, controller_child.pins)
        messages = [json.loads(v) for v in os.read(read_fd, diag.MAX_RAW).splitlines()]
        assert controller_child.calls == ["query", "query", "query", "start", "query"]
        assert messages[0]["schema"] == "si-startup-prestart-barrier-v7"
        assert messages[1]["target_pid"] == 456 and result["kernel"]["exit"] == 2
        assert result["authority"]["source_dispatch_authority"] is False
    finally: os.close(read_fd)


def test_control_child_wont_start_an_already_running_service(controller_child):
    controller_child.query_states[0] = kernel_bytes(1, running=True, pid=456)
    read_fd, control_fd = os.pipe(); ack_fd, ack_write = os.pipe(); os.write(ack_write, b"2"); os.close(ack_write)
    try:
        with pytest.raises(diag.StartupRefusal): diag.control_readonly(HEAD, diag.REMOTE, controller_child.digest, _OBSERVER, control_fd, ack_fd, controller_child.pins)
        assert controller_child.calls == ["query"] and "start" not in controller_child.calls
    finally: os.close(read_fd)


@pytest.fixture
def root_controller(fabricated, monkeypatch):
    original_run = diag.subprocess.run
    h = SimpleNamespace(loaded=False, started=False, actions=[], children=[], early=False, raw_after_start=b"", held=[], query_git_counts=[], load_callback=None)
    def run(args, **kwargs):
        if args[:1] == ["git"]: return original_run(args, **kwargs)
        role = next((v for v in ("query", "load", "start") if args == diag._launch_argv(v)), None)
        assert role in ("query", "load") and kwargs["shell"] is False
        h.actions.append(role)
        if role == "load":
            h.loaded = True; body, code = b"", 0
            if h.load_callback: h.load_callback()
        elif not h.loaded: body, code = b"PRIVATE_ABSENT_MESSAGE", 113
        else: body, code = kernel_bytes(1, exit_code=2) if h.started else kernel_bytes(), 0
        if role == "query":
            assert fabricated.calls[-2:] == [("root", 0), ("status", 0)]
            h.query_git_counts.append(len(fabricated.calls))
        return subprocess.CompletedProcess(args, code, stdout=body, stderr=b"PRIVATE_NATIVE_ERROR")
    def popen(args, **kwargs):
        assert args[:5] == [diag.worker.PYTHON, "-B", "-m", diag.MODULE, "control-readonly"]
        assert kwargs["stdin"] == kwargs["stdout"] == kwargs["stderr"]
        assert kwargs["start_new_session"] is kwargs["close_fds"] is True and kwargs["shell"] is False
        values = dict(zip(args[5::2], args[6::2])); observer = json.loads(values["--observer"]); digest = values["--spec-sha256"]
        writer = os.dup(int(values["--control-fd"])); reader = os.dup(int(values["--ack-fd"])); slave = os.dup(kwargs["stderr"])
        os.set_blocking(reader, False)
        class Child:
            pid = 999
            def __init__(self): self.step = 0; self.exit = None; self.waits = []; self.fds = [writer, reader, slave]
            def line(self, value): os.write(writer, canonical_json(value).encode() + b"\n")
            def receipt(self, early=False):
                error = diag.StartupRefusal("REFUSED: startup_control")
                return {"schema": "si-startup-control-v7", "nonce": observer["nonce"], "spec_sha256": digest,
                    "control_pid": self.pid, "target_pid": None if early else 456,
                    "kernel": diag._kernel(kernel_bytes() if early else kernel_bytes(1, exit_code=2)),
                    "status": "refused" if early else "terminal_observed", "failure": diag.failure_summary(error, HEAD) if early else None,
                    "authority": diag.authority()}
            def poll(self):
                if self.step == 0:
                    os.write(slave, b"PRIVATE_CONTROL_SETUP_BANNER\n")
                    if h.early: self.line(self.receipt(True))
                    else: self.line({"schema": "si-startup-prestart-barrier-v7", "nonce": observer["nonce"],
                        "spec_sha256": digest, "control_pid": self.pid, "status": "runs0_before_initial_start"})
                    self.step = 1; return None
                if self.step == 1:
                    try: ack = os.read(reader, 1)
                    except BlockingIOError: return None
                    assert ack == (b"2" if h.early else b"1")
                    h.actions.append("ack" + ack.decode())
                    if h.early: self.exit = 2
                    else:
                        h.started = True; h.actions.append("initial_start")
                        body = {"schema": "si-startup-PTY-observation-v7", "nonce": observer["nonce"], "spec_sha256": digest,
                            "pid": 456, "status": "refused", "failure": diag.failure_summary(diag.StartupRefusal("REFUSED: startup_config"), HEAD), "authority": diag.authority()}
                        self.pending = h.raw_after_start + diag._wire_encode(body)
                        self.step = 15; return None
                elif self.step == 15:
                    written = os.write(slave, self.pending[:512]); self.pending = self.pending[written:]
                    if not self.pending: self.line(self.receipt()); self.step = 2
                    return None
                elif self.step == 2:
                    try: ack = os.read(reader, 1)
                    except BlockingIOError: return None
                    assert ack == b"2"; h.actions.append("ack2"); self.exit = 0
                if self.exit is not None:
                    for fd in self.fds: os.close(fd)
                    self.fds.clear(); self.step = 3
                return self.exit
            def wait(self, *, timeout): self.waits.append(timeout); assert self.exit is not None; return self.exit
        child = Child(); h.children.append(child); return child
    monkeypatch.setattr(diag.subprocess, "run", run); monkeypatch.setattr(diag.subprocess, "Popen", popen)
    monkeypatch.setattr(diag.time, "sleep", lambda seconds: None)
    class Held(BaseException): pass
    def hold(state): h.held.append(state); raise Held()
    monkeypatch.setattr(diag, "_hold_private_controller", hold)
    try: yield h
    finally:
        for child in h.children:
            for fd in child.fds:
                try: os.close(fd)
                except OSError: pass
        for state in h.held:
            for key in ("master", "slave", "read_fd", "write_fd", "ack_read", "ack_write"):
                if state[key] is not None:
                    try: os.close(state[key])
                    except OSError: pass


def test_root_private_controller_barrier_captures_only_poststart_correlated_line(root_controller):
    result = diag.observe_readonly(HEAD, diag.REMOTE)
    assert result["status"] == "terminal_observation_only" and result["kernel"]["exit"] == 2
    assert result["target_pid"] == 456
    assert result["observer"]["status"] == "refused" and result["control_failure"] is None
    assert root_controller.actions.count("initial_start") == 1 and root_controller.actions.count("ack1") == 1
    assert root_controller.actions.index("ack1") < root_controller.actions.index("initial_start") < root_controller.actions.index("ack2")
    assert root_controller.children[0].waits == [0] and not root_controller.held
    assert "PRIVATE" not in canonical_json(result)


def test_root_private_controller_preserves_prebarrier_refusal_without_start_or_hold(root_controller):
    root_controller.early = True
    result = diag.observe_readonly(HEAD, diag.REMOTE)
    assert result["status"] == "control_refused_before_initial_start" and result["target_started"] is False
    assert result["target_pid"] is None
    assert result["controller_exit"] == 2 and result["control_failure"]["contract_code"] == "startup_control"
    assert result["observer"]["status"] == "observer_unavailable"
    assert "ack1" not in root_controller.actions and "initial_start" not in root_controller.actions
    assert root_controller.actions.count("ack2") == 1 and not root_controller.held


def test_poststart_raw_text_is_unavailable_never_filtered_into_a_diagnosis(root_controller):
    root_controller.raw_after_start = b"PRIVATE_UNRELATED_STARTUP_TRACEBACK\n"
    result = diag.observe_readonly(HEAD, diag.REMOTE)
    assert result["observer"]["status"] == "observer_unavailable"
    assert "PRIVATE" not in canonical_json(result) and root_controller.actions.count("initial_start") == 1


def test_actual_ex_config_annotation_is_terminal_but_conflicts_are_refused():
    raw = kernel_bytes(1, exit_code=78).replace(b"last exit code = 78", b"last exit code = 78: EX_CONFIG")
    assert diag._kernel(raw)["exit"] == 78
    for altered in (raw.replace(b"EX_CONFIG", b"EX_USAGE"), raw.replace(b"EX_CONFIG", b"PRIVATE_UNKNOWN"),
        raw + b"\tlast exit code = 78: EX_CONFIG\n", raw.replace(b"78: EX_CONFIG", b"unavailable")):
        with pytest.raises(diag.StartupRefusal): diag._kernel(altered)
    assert diag._kernel(kernel_bytes(1))["exit"] is None


def test_control_child_config_failure_is_a_single_safe_prebarrier_receipt(controller_child, monkeypatch):
    def refused(*args): raise diag.StartupRefusal("REFUSED: startup_config")
    monkeypatch.setattr(diag, "_controller_config", refused)
    read_fd, control_fd = os.pipe(); ack_fd, ack_write = os.pipe(); os.write(ack_write, b"2"); os.close(ack_write)
    try:
        with pytest.raises(diag.StartupRefusal): diag.control_readonly(HEAD, diag.REMOTE, controller_child.digest, _OBSERVER, control_fd, ack_fd, controller_child.pins)
        messages = [json.loads(v) for v in os.read(read_fd, diag.MAX_RAW).splitlines()]
        assert controller_child.calls == ["query"] and len(messages) == 1
        assert messages[0]["status"] == "refused" and messages[0]["target_pid"] is None
        assert messages[0]["failure"]["stage"] == "controller_prestart"
    finally: os.close(read_fd)


def test_root_controller_cleanup_close_error_is_fatal_after_known_terminal(root_controller, monkeypatch):
    original_openpty, original_close, originals, failed = os.openpty, os.close, [], []
    def openpty():
        pair = original_openpty(); originals.extend(pair); return pair
    def close(fd):
        result = original_close(fd)
        if originals and fd == originals[0] and not failed: failed.append(True); raise OSError(5, "PRIVATE_FINAL_CLOSE")
        return result
    monkeypatch.setattr(diag.os, "openpty", openpty); monkeypatch.setattr(diag.os, "close", close)
    with pytest.raises(OSError): diag.observe_readonly(HEAD, diag.REMOTE)
    assert failed == [True] and not root_controller.held
    for fd in originals:
        with pytest.raises(OSError): os.fstat(fd)


@pytest.mark.parametrize("hazard", ["bytes", "replacement"])
def test_controller_authenticates_original_canonical_job_at_load_consumption(root_controller, monkeypatch, hazard):
    original = diag.prepare_readonly
    def prepared(*args):
        result = original(*args); path = diag.ROOT / diag.PARENT / diag.BOOTSTRAP / "job.plist"; raw = path.read_bytes()
        if hazard == "bytes": path.write_bytes(b"X" + raw[1:])
        else:
            path.rename(diag.ROOT / "retained-original-job"); path.write_bytes(raw); path.chmod(0o600)
        return result
    monkeypatch.setattr(diag, "prepare_readonly", prepared)
    with pytest.raises(diag.StartupRefusal): diag.observe_readonly(HEAD, diag.REMOTE)
    assert "load" not in root_controller.actions and not root_controller.children and not root_controller.held


def test_controller_detects_same_size_change_during_single_load_before_any_start(root_controller):
    def changed():
        path = diag.ROOT / diag.PARENT / diag.BOOTSTRAP / "job.plist"; raw = path.read_bytes(); path.write_bytes(b"X" + raw[1:])
    root_controller.load_callback = changed
    with pytest.raises(diag.proof.NativeProofRefusal): diag.observe_readonly(HEAD, diag.REMOTE)
    assert root_controller.actions.count("load") == 1 and not root_controller.children
    assert "initial_start" not in root_controller.actions and len(root_controller.held) == 1


def test_loaded_kernel_target_and_canonical_job_path_are_required(fabricated):
    raw = kernel_bytes()
    for changed in (raw.replace(diag._target().encode(), b"gui/501/FOREIGN", 1),
        raw.replace(str(diag.ROOT / diag.PARENT / diag.BOOTSTRAP / "job.plist").encode(), b"/PRIVATE_FOREIGN_JOB"),
        raw + b"\tpath = /PRIVATE_SECOND_PATH\n"):
        with pytest.raises(diag.StartupRefusal): diag._kernel(changed)


def test_child_reauthenticates_same_original_configuration_before_initial_start(controller_child, monkeypatch):
    original_run = diag.subprocess.run; changed = []
    def run(args, **kwargs):
        result = original_run(args, **kwargs)
        if args == diag._launch_argv("query") and not changed:
            path = diag.ROOT / diag.PARENT / diag.BOOTSTRAP / "job.plist"; raw = path.read_bytes(); path.write_bytes(b"X" + raw[1:]); changed.append(True)
        return result
    monkeypatch.setattr(diag.subprocess, "run", run)
    read_fd, control_fd = os.pipe(); ack_fd, ack_write = os.pipe(); os.write(ack_write, b"2"); os.close(ack_write)
    try:
        with pytest.raises(diag.StartupRefusal): diag.control_readonly(HEAD, diag.REMOTE, controller_child.digest, _OBSERVER, control_fd, ack_fd, controller_child.pins)
        assert controller_child.calls == ["query"] and "start" not in controller_child.calls
    finally: os.close(read_fd)


def test_load_transaction_includes_original_ancestry_full9_during_load(root_controller, monkeypatch):
    real_stat, real_fstat, changed = os.stat, os.fstat, []
    def observed(info):
        if changed and stat.S_ISDIR(info.st_mode): return ProjectedStat(info, st_ctime_ns=info.st_ctime_ns + 1)
        return info
    root_controller.load_callback = lambda: changed.append(True)
    monkeypatch.setattr(diag.os, "stat", lambda *a, **k: observed(real_stat(*a, **k)))
    monkeypatch.setattr(diag.os, "fstat", lambda fd: observed(real_fstat(fd)))
    with pytest.raises(diag.proof.NativeProofRefusal): diag.observe_readonly(HEAD, diag.REMOTE)
    assert changed == [True] and not root_controller.children


def test_actual_never_exited_marker_is_unknown_exit_only_for_never_started_service():
    raw = kernel_bytes()
    value = diag._kernel(raw)
    assert value == {"runs": 0, "running": False, "active_count": 0, "pid": None, "exit": None}
    assert value["exit"] != 0


@pytest.mark.parametrize("hazard", ["runs1", "running", "pid", "numeric", "duplicate", "malformed"])
def test_never_exited_marker_refuses_started_conflicting_or_duplicate_states(hazard):
    raw = {"runs1": lambda: kernel_bytes(1) + b"\tlast exit code = (never exited)\n",
        "running": lambda: kernel_bytes(0, running=True) + b"\tlast exit code = (never exited)\n",
        "pid": lambda: kernel_bytes(0, pid=123) + b"\tlast exit code = (never exited)\n",
        "numeric": lambda: kernel_bytes() + b"\tlast exit code = 0\n",
        "duplicate": lambda: kernel_bytes() + b"\tlast exit code = (never exited)\n",
        "malformed": lambda: kernel_bytes().replace(b"(never exited)", b"(never exited): EX_CONFIG")}[hazard]()
    with pytest.raises(diag.StartupRefusal): diag._kernel(raw)


def test_known_never_started_without_control_child_releases_only_owned_observer_fds(root_controller, monkeypatch):
    original, calls = diag._control_guard, []
    def guard(head, remote):
        calls.append(True)
        if len(calls) == 3: raise diag.StartupRefusal("REFUSED: startup_control")
        return original(head, remote)
    monkeypatch.setattr(diag, "_control_guard", guard)
    with pytest.raises(diag.StartupRefusal): diag.observe_readonly(HEAD, diag.REMOTE)
    assert root_controller.loaded and not root_controller.started and not root_controller.children and not root_controller.held
    assert root_controller.actions.count("load") == 1 and "initial_start" not in root_controller.actions


def test_loaded_unknown_state_still_retains_original_observation_endpoints(root_controller, monkeypatch):
    original = diag._kernel
    def kernel(raw):
        if root_controller.loaded: raise diag.StartupRefusal("REFUSED: startup_control_state")
        return original(raw)
    monkeypatch.setattr(diag, "_kernel", kernel)
    with pytest.raises(diag.StartupRefusal): diag.observe_readonly(HEAD, diag.REMOTE)
    assert len(root_controller.held) == 1 and not root_controller.children and not root_controller.started
    state = root_controller.held[0]
    assert os.isatty(state["master"]) and os.isatty(state["slave"])


def test_root_only_launchctl_debug_is_not_an_available_v5_backend():
    with pytest.raises(diag.StartupRefusal): diag._launch_argv("debug")


def test_v5_job_stderr_is_the_exact_held_slave_device_not_a_regular_file(fabricated, private_observer_endpoint):
    unused_master, slave = private_observer_endpoint
    assert diag._tty_check(slave, _OBSERVER) == tuple(_OBSERVER["terminal"])
    job = diag.build_launchd_plist(HEAD, diag.REMOTE, "c" * 64, _OBSERVER)
    assert job["StandardErrorPath"] == os.ttyname(slave) == _OBSERVER["slave_path"]
    assert job["StandardOutPath"] == "/dev/null"
    assert _OBSERVER["slave_path"].startswith("/dev/")
    with pytest.raises(diag.StartupRefusal): diag._tty_check(slave, {**_OBSERVER, "slave_path": "/dev/null"})


@pytest.mark.parametrize("hazard", ["symlink", "regular", "missing", "inode", "rdev", "owner", "mode"])
def test_slave_named_endpoint_replacement_or_bad_type_never_falls_back(fabricated, monkeypatch, private_observer_endpoint, hazard):
    unused_master, slave = private_observer_endpoint; original = os.stat
    def stat_result(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if str(path) != _OBSERVER["slave_path"] or kwargs.get("follow_symlinks", True): return info
        if hazard == "missing": raise FileNotFoundError(2, "PRIVATE_SLAVE_MISSING")
        changes = {"symlink": {"st_mode": stat.S_IFLNK | 0o777}, "regular": {"st_mode": stat.S_IFREG | 0o600},
            "inode": {"st_ino": info.st_ino + 1}, "rdev": {"st_rdev": info.st_rdev + 1},
            "owner": {"st_uid": info.st_uid + 1}, "mode": {"st_mode": stat.S_IFCHR | 0o666}}
        return ProjectedStat(info, **changes[hazard])
    monkeypatch.setattr(diag.os, "stat", stat_result)
    with pytest.raises((diag.StartupRefusal, OSError)): diag._tty_check(slave, _OBSERVER)


def test_master_endpoint_cannot_be_adopted_as_the_private_slave(private_observer_endpoint):
    master, unused_slave = private_observer_endpoint
    with pytest.raises((diag.StartupRefusal, OSError)):
        diag._tty_check(master, {"nonce": "1" * 32, "terminal": list(diag._tty_pin(master)), "slave_path": os.ttyname(master)})


def test_device_path_failure_before_load_prevents_any_service_load(root_controller, monkeypatch):
    original, calls = diag._tty_check, []
    def checked(fd, value):
        calls.append(True)
        if len(calls) == 2: raise diag.StartupRefusal("REFUSED: startup_observer")
        return original(fd, value)
    monkeypatch.setattr(diag, "_tty_check", checked)
    with pytest.raises(diag.StartupRefusal): diag.observe_readonly(HEAD, diag.REMOTE)
    assert "load" not in root_controller.actions and not root_controller.children and not root_controller.started


def test_device_path_change_during_load_never_reaches_initial_start(root_controller, monkeypatch):
    original = diag._tty_check; changed = []
    root_controller.load_callback = lambda: changed.append(True)
    def checked(fd, value):
        if changed: raise diag.StartupRefusal("REFUSED: startup_observer")
        return original(fd, value)
    monkeypatch.setattr(diag, "_tty_check", checked)
    with pytest.raises(diag.StartupRefusal): diag.observe_readonly(HEAD, diag.REMOTE)
    assert root_controller.loaded and not root_controller.started and not root_controller.children


def test_device_path_is_rechecked_immediately_before_the_only_initial_start(controller_child, monkeypatch):
    def checked(fd, value):
        if diag._STAGE == "controller_initial_start": raise diag.StartupRefusal("REFUSED: startup_observer")
        return tuple(value["terminal"])
    monkeypatch.setattr(diag, "_tty_check", checked)
    read_fd, control_fd = os.pipe(); ack_fd, ack_write = os.pipe(); os.write(ack_write, b"12"); os.close(ack_write)
    try:
        with pytest.raises(diag.StartupRefusal): diag.control_readonly(HEAD, diag.REMOTE, controller_child.digest, _OBSERVER, control_fd, ack_fd, controller_child.pins)
        assert "start" not in controller_child.calls
    finally: os.close(read_fd)


def test_postterminal_device_path_drift_is_negative_without_restart(root_controller, monkeypatch):
    original = diag._tty_check
    def checked(fd, value):
        if root_controller.started: raise diag.StartupRefusal("REFUSED: startup_observer")
        return original(fd, value)
    monkeypatch.setattr(diag, "_tty_check", checked)
    with pytest.raises(diag.StartupRefusal): diag.observe_readonly(HEAD, diag.REMOTE)
    assert root_controller.actions.count("initial_start") == 1 and len(root_controller.held) == 1
    assert not any("-k" in str(action) or "debug" == action for action in root_controller.actions)


def test_endpoint_drift_in_last_prestart_query_prevents_the_initial_start(controller_child, monkeypatch):
    original_run, queries, changed = diag.subprocess.run, [], []
    def run(args, **kwargs):
        result = original_run(args, **kwargs)
        if args == diag._launch_argv("query"):
            queries.append(True)
            if len(queries) == 3: changed.append(True)
        return result
    def checked(fd, value):
        if changed: raise diag.StartupRefusal("REFUSED: startup_observer")
        return tuple(value["terminal"])
    monkeypatch.setattr(diag.subprocess, "run", run); monkeypatch.setattr(diag, "_tty_check", checked)
    read_fd, control_fd = os.pipe(); ack_fd, ack_write = os.pipe(); os.write(ack_write, b"12"); os.close(ack_write)
    try:
        with pytest.raises(diag.StartupRefusal): diag.control_readonly(HEAD, diag.REMOTE, controller_child.digest, _OBSERVER, control_fd, ack_fd, controller_child.pins)
        assert changed == [True] and "start" not in controller_child.calls
    finally: os.close(read_fd)


_NATIVE_CHILD_HELD = []
_NATIVE_SESSION_CHILD = '''import json, sys
from scripts import diagnose_short_interest_native_supervisor_startup as d
observer = json.loads(sys.argv[1])
d._control_session(observer)
if sys.argv[2] == "legacy_ctty":
    import fcntl, termios
    fcntl.ioctl(2, termios.TIOCSCTTY, 0)
'''


@pytest.mark.skipif(sys.platform != "darwin", reason="Actual macOS devfs session-leader revocation regression")
@pytest.mark.parametrize("mode", ["legacy_ctty", "explicit_fds"])
def test_native_session_child_keeps_explicit_endpoints_without_controlling_ownership(mode):
    master, slave = os.openpty(); os.set_blocking(master, False)
    observer = {"nonce": "3" * 32, "terminal": list(diag._tty_pin(slave)), "slave_path": os.ttyname(slave)}
    process = None; held = False; raw_private = b""
    try:
        process = ORIGINAL_POPEN([diag.worker.PYTHON, "-B", "-c", _NATIVE_SESSION_CHILD, canonical_json(observer), mode],
            cwd=diag.ROOT, env=diag.worker._environment(), stdin=slave, stdout=slave, stderr=slave,
            start_new_session=True, close_fds=True, shell=False)
        try: actual_exit = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            held = True; _NATIVE_CHILD_HELD.append((process, master, slave))
            pytest.fail("source-free test child termination unknown; original handle and endpoints retained")
        assert actual_exit == 0
        try:
            for unused in range(4):
                block = os.read(master, 4096)
                if not block: break
                raw_private += block
        except (BlockingIOError, OSError): pass
        if mode == "legacy_ctty":
            with pytest.raises(OSError) as failed: os.fstat(slave)
            assert failed.value.errno == errno.EBADF
            with pytest.raises(OSError) as failed: os.ttyname(slave)
            assert failed.value.errno == errno.EBADF and os.isatty(slave) is False
        else:
            assert diag._tty_check(slave, observer) == tuple(observer["terminal"])
            assert os.isatty(slave) and os.ttyname(slave) == observer["slave_path"]
            assert os.fstat(slave).st_ino == observer["terminal"][1]
    finally:
        # No raw startup text is emitted or included in an assertion. A genuinely
        # unknown test child keeps all originals rather than being killed/lost.
        if not held:
            os.close(slave); os.close(master)


def test_v7_wrapper_transport_is_fixed_policy_bound_and_job_remains_bounded(fabricated):
    import ast, base64, zlib
    wrapper = diag._import_wrapper(); body = diag._import_body()
    encoded = next(node.args[0].value for node in ast.walk(ast.parse(wrapper))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "b64decode")
    assert zlib.decompress(base64.b64decode(encoded)).decode() == body
    descriptor = diag.policy()["import_wrapper"]
    assert descriptor["body_sha256"] == hash_bytes(body.encode()) and descriptor["inline_sha256"] == hash_bytes(wrapper.encode())
    digest = prepare(); job = diag.build_launchd_plist(HEAD, diag.REMOTE, digest, _OBSERVER)
    assert len(plistlib.dumps(job, sort_keys=True)) <= diag.MAX_CONFIG == 4096
    assert job["ProgramArguments"][:4] == [diag.worker.PYTHON, "-B", "-c", wrapper]
    assert job["ProgramArguments"][4:] == ["run-readonly", "--head", HEAD, "--remote", diag.REMOTE,
        "--spec-sha256", digest, "--observer", canonical_json(_OBSERVER)]
    assert "__import__('scripts.diagnose_short_interest_native_supervisor_startup',fromlist=['main'])" in body


def test_v7_wire_authority_hash_is_exact_no_alternate_or_default_authority_form():
    value = {"schema": "si-startup-PTY-observation-v7", "nonce": _OBSERVER["nonce"], "spec_sha256": "c" * 64,
        "pid": 456, "status": "readonly_predicates_passed_observation_only", "failure": None, "authority": diag.authority()}
    wire = diag._wire_encode(value); parsed = json.loads(wire)
    assert "authority" not in parsed and parsed["authority_sha256"] == hash_payload(diag.authority())
    assert diag.filter_observer(wire, _OBSERVER, "c" * 64, 456)["authority"] == diag.authority()
    for altered in ({**parsed, "authority_sha256": "0" * 64}, {k: v for k, v in parsed.items() if k != "authority_sha256"}, value):
        result = diag.filter_observer(canonical_json(altered).encode() + b"\n", _OBSERVER, "c" * 64, 456)
        assert result["status"] == "observer_unavailable"


def test_finite_wire_bound_covers_every_fixed_failure_family_and_stamp_domain():
    longest = lambda values: max(values, key=len)
    detail = {"stage": longest(diag._STAGES), "stage_scope": "entered_phase_including_callbacks_not_forensic_cause",
        "category": "local_contract_refusal", "contract_code": longest(diag._CODES),
        "upstream_contract_code": longest(diag.proof._CODES | diag.worker._CODES | diag.proof.native._CODES),
        "errno_name": longest(set(diag._ERRNOS.values()) | set(diag.proof._ERRNOS.values()) | set(diag.worker._ERRNOS.values()) | set(diag.proof.native._ERRNOS.values())),
        "mismatching_fields": [longest(diag.proof._STAMP_NAMES)] * 9,
        "original_Git": {"role": "actual_matching_ref", "code_ordinal": 6, "returncode": -32768},
        "original_query": {"returncode": -32768}}
    value = {"schema": "si-startup-PTY-observation-v7", "nonce": "f" * 32, "spec_sha256": "f" * 64,
        "pid": 2147483647, "status": "readonly_predicates_passed_observation_only", "failure": detail, "authority": diag.authority()}
    worst = len(diag._wire_encode(value))
    assert worst == diag._wire_bound() <= diag.MAX_WIRE == 1024 < diag.MAX_STATUS == 2048
    for code in diag._CODES:
        detail["contract_code"] = code
        assert len(diag._wire_encode(value)) <= worst


_WRAPPER_CHILD = '''import sys,os,json,builtins,errno,types
wrapper,mode,encoded=sys.argv[1:]
args=json.loads(encoded)
original=builtins.__import__
def intercepted(name,*a,**k):
 if name=='scripts.diagnose_short_interest_native_supervisor_startup':
  if mode in ('import_oserror','partial_write'):raise OSError(errno.EACCES,'PRIVATE_IMPORT_PATH_AND_TEXT')
  if mode=='import_unknown':raise RuntimeError('PRIVATE_DYNAMIC_EXCEPTION')
  def main(actual):
   if mode=='handoff_error':raise RuntimeError('PRIVATE_LATER_MAIN')
   return 0 if actual==args else 2
  return types.SimpleNamespace(main=main)
 if mode=='decoder_error' and name=='zlib':raise RuntimeError('PRIVATE_DECODER')
 return original(name,*a,**k)
builtins.__import__=intercepted
if mode=='partial_write':
 original_write=os.write
 def partial(fd,body):
  if fd==2:return original_write(fd,body[:10])
  return original_write(fd,body)
 os.write=partial
sys.argv=['-c',*args]
exec(wrapper)
'''


def _private_wrapper_child(mode, *, bad_channel=False):
    master, slave = os.openpty(); os.set_blocking(master, False)
    settings = termios.tcgetattr(slave); settings[1] &= ~termios.ONLCR; settings[3] &= ~termios.ECHO
    termios.tcsetattr(slave, termios.TCSANOW, settings)
    observer = {"nonce": "4" * 32, "terminal": list(diag._tty_pin(slave)), "slave_path": os.ttyname(slave)}
    if bad_channel: observer["terminal"][1] += 1
    args = ["run-readonly", "--head", HEAD, "--remote", diag.REMOTE, "--spec-sha256", "c" * 64, "--observer", canonical_json(observer)]
    process = None; held = False; private = b""
    try:
        process = ORIGINAL_POPEN([diag.worker.PYTHON, "-B", "-c", _WRAPPER_CHILD, diag._import_wrapper(), mode, canonical_json(args)],
            cwd=diag.ROOT, env=diag.worker._environment(), stdin=slave, stdout=slave, stderr=slave,
            start_new_session=True, close_fds=True, shell=False)
        try: actual_exit = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            held = True; _NATIVE_CHILD_HELD.append((process, master, slave)); pytest.fail("fixed wrapper test child unknown; originals retained")
        for unused in range(4):
            try: block = os.read(master, 4096)
            except BlockingIOError: break
            if not block: break
            private += block
        return actual_exit, process.pid, observer, private
    finally:
        if not held: os.close(slave); os.close(master)


@pytest.mark.parametrize("mode,expected_errno", [("import_oserror", "EACCES"), ("import_unknown", None)])
def test_preimport_wrapper_emits_one_authenticated_fixed_import_failure(mode, expected_errno):
    actual_exit, pid, observer, private = _private_wrapper_child(mode)
    assert actual_exit == 2
    result = diag.filter_observer(private, observer, "c" * 64, pid)
    assert result["status"] == "refused" and result["failure"]["stage"] == "startup_import"
    assert result["failure"]["contract_code"] == "startup_import_failed" and result["failure"]["errno_name"] == expected_errno
    assert result["failure"]["original_query"] == {"returncode": None}
    safe = b"PRIVATE" not in private
    assert safe and len(private) <= 1024 and private.count(b"\n") == 1


@pytest.mark.parametrize("mode,expected_exit", [("success", 0), ("decoder_error", 2), ("handoff_error", 2)])
def test_wrapper_success_or_nonimport_failure_has_no_prelude_or_relabelled_import_line(mode, expected_exit):
    actual_exit, unused_pid, unused_observer, private = _private_wrapper_child(mode)
    assert actual_exit == expected_exit
    empty = private == b""
    assert empty


def test_wrapper_invalid_destination_never_writes_or_imports_target():
    actual_exit, unused_pid, unused_observer, private = _private_wrapper_child("import_oserror", bad_channel=True)
    assert actual_exit == 2
    empty = private == b""
    assert empty


@pytest.mark.parametrize("hazard,code", [("target", "startup_kernel_target"), ("path", "startup_kernel_path"),
    ("runs", "startup_kernel_runs_field"), ("state_field", "startup_kernel_state_field"),
    ("active", "startup_kernel_active_field"), ("pid", "startup_kernel_pid_field"),
    ("exit_duplicate", "startup_kernel_exit_field"), ("exit_format", "startup_kernel_exit_format"),
    ("annotation", "startup_kernel_exit_annotation"), ("state_catalogue", "startup_kernel_state_catalogue"),
    ("never", "startup_kernel_never_exited"), ("bounds", "startup_kernel_bounds")])
def test_kernel_refusal_families_distinguish_unchanged_rejected_predicates(fabricated, hazard, code):
    raw = kernel_bytes()
    if hazard == "target": raw = raw.replace(diag._target().encode(), b"PRIVATE_FOREIGN_TARGET", 1)
    elif hazard == "path": raw = raw.replace(str(diag.ROOT / diag.PARENT / diag.BOOTSTRAP / "job.plist").encode(), b"PRIVATE_FOREIGN_PATH")
    elif hazard == "runs": raw += b"\truns = 0\n"
    elif hazard == "state_field": raw = raw.replace(b"\tstate = not running", b"\tstate = PRIVATE_UNRECOGNIZED_STATE")
    elif hazard == "active": raw += b"\tactive count = 0\n"
    elif hazard == "pid": raw += b"\tpid = PRIVATE_INVALID\n"
    elif hazard == "exit_duplicate": raw += b"\tlast exit code = 0\n"
    elif hazard == "exit_format": raw = raw.replace(b"(never exited)", b"PRIVATE_UNKNOWN_EXIT")
    elif hazard == "annotation": raw = kernel_bytes(1, exit_code=78).replace(b"78\n", b"78: EX_USAGE\n")
    elif hazard == "state_catalogue": raw = raw.replace(b"\tstate = not running", b"\tstate = spawn scheduled")
    elif hazard == "never": raw = raw.replace(b"\truns = 0", b"\truns = 1")
    else: raw = kernel_bytes(2, exit_code=0)
    with pytest.raises(diag.StartupRefusal) as error: diag._kernel(raw)
    detail = diag.failure_summary(error.value, HEAD)
    assert detail["contract_code"] == code and "PRIVATE" not in canonical_json(detail)


def test_query_returncode_projection_requires_genuine_original_frame(controller_child, monkeypatch):
    original = diag.subprocess.run
    def run(args, **kwargs):
        if args == diag._launch_argv("query"): return subprocess.CompletedProcess(args, 124, stdout=b"PRIVATE_RETURN_BODY")
        return original(args, **kwargs)
    monkeypatch.setattr(diag.subprocess, "run", run)
    with pytest.raises(diag.StartupRefusal) as error: diag._query(HEAD)
    detail = diag.failure_summary(error.value, HEAD)
    assert detail["contract_code"] == "startup_query_return" and detail["original_query"] == {"returncode": 124}
    def fake_query(head):
        result = subprocess.CompletedProcess(diag._launch_argv("query"), 0, stdout=b"")
        raise diag.StartupRefusal("REFUSED: startup_query_return")
    with pytest.raises(diag.StartupRefusal) as forged: fake_query(HEAD)
    assert diag.failure_summary(forged.value, HEAD)["original_query"] == {"returncode": None}


def test_actual_query_zero_return_with_refused_body_is_not_invented_success(controller_child, monkeypatch):
    original = diag.subprocess.run
    def run(args, **kwargs):
        if args == diag._launch_argv("query"): return subprocess.CompletedProcess(args, 0, stdout=b"PRIVATE_INVALID_BODY")
        return original(args, **kwargs)
    monkeypatch.setattr(diag.subprocess, "run", run)
    with pytest.raises(diag.StartupRefusal) as error: diag._query(HEAD)
    detail = diag.failure_summary(error.value, HEAD)
    assert detail["contract_code"] == "startup_kernel_target" and detail["original_query"] == {"returncode": 0}


def test_failed_poststart_query_clears_prestart_kernel_row_in_control_receipt(controller_child):
    controller_child.query_states[-1] = kernel_bytes(1).replace(b"\tstate = not running", b"\tstate = spawn scheduled")
    read_fd, control_fd = os.pipe(); ack_fd, ack_write = os.pipe(); os.write(ack_write, b"12"); os.close(ack_write)
    try:
        with pytest.raises(diag.StartupRefusal): diag.control_readonly(HEAD, diag.REMOTE, controller_child.digest, _OBSERVER, control_fd, ack_fd, controller_child.pins)
        receipt = json.loads(os.read(read_fd, diag.MAX_RAW).splitlines()[-1])
        assert receipt["target_pid"] == 456 and receipt["kernel"] is None
        assert receipt["failure"]["contract_code"] == "startup_kernel_state_catalogue"
        assert receipt["failure"]["original_query"] == {"returncode": 0}
    finally: os.close(read_fd)


def test_postquery_pid_binding_failure_has_distinct_code_and_no_borrowed_query_frame(controller_child):
    controller_child.query_states[-1] = kernel_bytes(1, running=True, pid=457)
    read_fd, control_fd = os.pipe(); ack_fd, ack_write = os.pipe(); os.write(ack_write, b"12"); os.close(ack_write)
    try:
        with pytest.raises(diag.StartupRefusal): diag.control_readonly(HEAD, diag.REMOTE, controller_child.digest, _OBSERVER, control_fd, ack_fd, controller_child.pins)
        receipt = json.loads(os.read(read_fd, diag.MAX_RAW).splitlines()[-1])
        assert receipt["failure"]["contract_code"] == "startup_kernel_pid_binding"
        assert receipt["failure"]["original_query"] == {"returncode": None}
    finally: os.close(read_fd)


def test_fixed_bootstrap_body_checks_the_single_actual_write_count():
    import ast
    body = ast.parse(diag._import_body())
    writes = [node for node in ast.walk(body) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr == "write"]
    assert len(writes) == 1
    assignments = [node for node in ast.walk(body) if isinstance(node, ast.Assign) and node.value is writes[0]]
    assert len(assignments) == 1 and isinstance(assignments[0].targets[0], ast.Name)
    count = assignments[0].targets[0].id
    guards = [node for node in ast.walk(body) if isinstance(node, ast.If) and isinstance(node.test, ast.BoolOp)
        and ast.unparse(node.test) == "type(" + count + ") is not int or " + count + " != len(B)"]
    assert len(guards) == 1 and any(isinstance(node, ast.Raise) for node in guards[0].body)


def test_bootstrap_partial_write_is_one_attempt_and_never_a_complete_observation():
    actual_exit, pid, observer, private = _private_wrapper_child("partial_write")
    assert actual_exit == 2 and len(private) == 10
    assert diag.filter_observer(private, observer, "c" * 64, pid)["status"] == "observer_unavailable"
