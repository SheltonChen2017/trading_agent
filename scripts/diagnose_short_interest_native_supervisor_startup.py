"""One registered read-only background startup replay, never a native proof.

The externally pinned canonical configuration authenticates an observation
channel before Git. It grants no assertion about the live lane. All live
predicates still run through the unchanged original guard and code reader.
"""
import argparse
import builtins
import io
from contextlib import contextmanager
import errno
import secrets
import json
import math
import os
from pathlib import Path
import plistlib
import re
import socket
import stat
import subprocess
import time

try:
    import fcntl
    import termios
except ImportError:  # Metadata analysis/import remains available off POSIX.
    fcntl = termios = None

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_count_native_supervisor as proof

worker = proof.worker
ROOT, PARENT = proof.ROOT, proof.PARENT
MODULE = "scripts.diagnose_short_interest_native_supervisor_startup"
DRIVER = "scripts/diagnose_short_interest_native_supervisor_startup.py"
BOOTSTRAP = "count-native-supervisor-startup-diagnostic-v5"
STATUS = "count-native-supervisor-startup-diagnostic-v5.jsonl"
LABEL = "com.openai.codex.short-interest-native-startup-diagnostic-v5"
POLICY_SHA256 = "858d85488e9bc447070e63f1c9e7e0c234d3ee917d991f3bf6b857c3dbf0b000"
TARGET_HEAD = "b58f992ac73451f8e4ec1384061ad7030d8afffa"
REMOTE = "f27d836ab0c7422463ea19b2f6fa3bba86535c4c"
TARGET_SPEC = "28220a7af8aea2acc70da2a61fbceddd86cc831226cfc56c560ec13e0da2e8a6"
TARGET_MANIFEST = {
    "data/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "data/hashing.py": "f772a0567ce33248bde0b1b022e81c0ff675afbb67557a8588c158861c4a3f4c",
    "scripts/short_interest_count_native_supervisor.py": "66762c1f7a1531c395aa20e79d4eac99984259e81f691bbfe1f407b983288f5b",
    "scripts/short_interest_count_process_supervisor.py": "0b11afcc9a7026fe9727cca1131c5bf1ddea7d37cd716b1d1874ff636ff23565",
    "scripts/short_interest_isolated_custody_volume.py": "3baf4977794e30864cbc1a6d59869daccde5161140aee59684fd5fac6e6ba6b8"}
CODE_FILES = (*proof.CODE_FILES, DRIVER)
MAX_CONFIG, MAX_STATUS, MAX_SECONDS, MAX_GIT = 4096, 2048, 300, 128
LAUNCHCTL = "/bin/launchctl"
MAX_RAW, MAX_POLLS = 65536, 300
_SYSEXITS = dict(enumerate(("EX_USAGE", "EX_DATAERR", "EX_NOINPUT", "EX_NOUSER", "EX_NOHOST", "EX_UNAVAILABLE", "EX_SOFTWARE", "EX_OSERR", "EX_OSFILE", "EX_CANTCREAT", "EX_IOERR", "EX_TEMPFAIL", "EX_PROTOCOL", "EX_NOPERM", "EX_CONFIG"), 64))
_CONTROLLER_HELD, _PREPARED_INPUTS = [], {}
_ORIGINAL_GIT, _GIT_CODE = worker._git, worker._git.__code__
_ORIGINAL_GUARD, _ORIGINAL_CODE, _ORIGINAL_READ = worker._guard, proof._Code, proof._read_bootstrap
_STAGE, _USED = "registration", False
_STAGES = frozenset("registration config_auth status_bind live_guard current_code historical_config terminal_code original_audit cleanup named_audit status_publication observer_binding controller_load controller_prestart controller_barrier controller_initial_start controller_terminal".split())
_CODES = frozenset("startup_unregistered startup_arguments startup_config startup_status startup_code startup_stamp startup_deadline startup_clock startup_forbidden startup_git_budget startup_already_used startup_write startup_membership startup_observer startup_control startup_control_state startup_control_unknown".split())
_ERRNOS = {getattr(errno, n): n for n in ("EACCES", "EPERM", "ENOENT", "EEXIST", "ENOSPC", "EIO", "EBADF", "EMFILE", "ENFILE", "EROFS", "EINTR", "EAGAIN")}
_FAILURES = {}


class StartupRefusal(ValueError): pass


def require(value, code):
    if not value: raise StartupRefusal("REFUSED: " + code)


def authority():
    return {"startup_diagnostic_only": True, "source_dispatch_authority": False, "native_proof_authority": False,
        "old_proof_admitted": False, "live_lane_admitted": False, "source_admitted": False,
        "budget_release_authority": False, "supervisor_process_exit_attested": False,
        "launcher_independence_verified": False, "readback_claimed": False, "ready_for_backtest": False,
        "provider_HTTP": 0, "credential_reads": 0, "source_STARTs": 0, "source_bytes": 0,
        "new_source_claims": 0, "native_commands": 0, "QC_or_Safari": False, "qc_attempts": 0}


def policy():
    return {"schema": "si-native-startup-diagnostic-policy-v5", "root": str(ROOT), "parent": str(PARENT),
        "bootstrap": BOOTSTRAP, "status": STATUS, "label": LABEL, "code_files": list(CODE_FILES),
        "target_head": TARGET_HEAD, "target_remote": REMOTE, "target_spec_sha256": TARGET_SPEC,
        "target_manifest": TARGET_MANIFEST, "maximum_config_bytes": MAX_CONFIG, "maximum_status_bytes": MAX_STATUS,
        "maximum_elapsed_acceptance_seconds": MAX_SECONDS, "maximum_Git_calls": MAX_GIT, "Git_per_call_seconds": 30,
        "deadline": "elapsed_acceptance_at_phase_and_terminal_boundaries_not_hard_wall_kill",
        "preauth": "externally_pinned_canonical_config_only_live_root_branch_HEAD_status_unknown_until_original_guard",
        "configuration": "exact_spec_job_roles_original_first7_and_canonical_expected_bytes_SHA_across_phases_fresh_full9_FD_named_stability_each_read_including_close_no_evidence_capability_original_creator_pin_preserved_prepare_initial_Runtime_pin_configuration_only",
        "retired": "startup_diagnostic_v1_v2_v3_v4_namespaces_status_and_jobs_preserved_never_reused",
        "observer": "Root_CLI_original_TTY_dev_ino_rdev_UID_GID_mode_isatty_observation_only_before_registration_fence_clock_config_one2048_nonblocking_write_no_retry_fsync_readback_nonce_specDigest_PID_correlated_no_exclusive_writer_or_own_kernel_claim",
        "load_consumption": "same_process_original_prepare_first7_canonical_bytes_SHA_fresh_full9_held_FD_named_epoch_across_single_bootstrap_load_and_postcleanup_exact_loaded_target_canonicaljobpath_neverstarted0_child_original_config_reauth_before_prestart_and_initial_start_no_debug_no_SourceAuthority",
        "controller": "one_private_PTY_persistent_session_leader_controlchild_TIOCSCTTY_fixed_label_load_RunAtLoadFalse_KeepAliveFalse_runs0_canonical_original_slave_devfs_StandardErrorPath_no_debug_verify_runs0_private_prestart_drain_ack_barrier_initial_kickstart_p_no_k_Root_terminal_capture_ack_then_session_release_no_kill_restart",
        "kernel": "original_local_snapshot_before_every_query_top_level_one_tab_state_activecount_runs_exit_numeric_or_exact64_78_sysexit_pair_never_exited_None_only_runs0_notrunning_active0_noPID_no_PIDabsence_inference",
        "controller_unknown": "retain_original_PTY_pipes_child_handle_private_buffers_continue_draining_while_parent_lives_no_command_retry_restart_kill_or_proof_if_parent_interrupted_retention_unknown",
        "device_path": "exact_os_ttyname_original_slave_private_devfs_node_trusted_dev_ancestry_named_char_and_FD_dev_ino_rdev_UID_GID_mode_isatty_before_after_load_before_start_after_terminal_not_launchd_nofollow_or_nocreate_claim_no_exclusive_writer",
        "raw": "private_RAM_only_max65536_plus_one4096_read_no_raw_tool_chat_partial_unrelated_duplicate_or_bad_nonce_PID_unavailable",
        "status_role": "original_first7_empty0600_singlelink_nofollow_parentfd_WRONLY_NONBLOCK_no_CREATE_TRUNC_APPEND_full9_each_operation_one_bounded_line_no_evidence_capability",
        "runtime": "unchanged_original_guard_Code5_at_newruntimeHEAD_plus_own_Code6_then_original_historical_bootstrap_at_targetHEAD_no_global_mutation",
        "git_failure": "complete_trace_within128_unique_original_function_code_and_globals_frame_exact_arguments_CompletedProcess_returncode_only_no_output_stderr_paths_values_or_type",
        "operation": "read_only_fixed_Git_only_exact_devnull_O_RDWR_character_device_standard_channel_exception_no_source_write_native_provider_socket_DNS_capture_or_child_operation_no_retry",
        "authority": authority()}


def registered():
    require(type(POLICY_SHA256) is str and re.fullmatch("[0-9a-f]{64}", POLICY_SHA256)
        and hash_payload(policy()) == POLICY_SHA256, "startup_unregistered")
    require(worker._git is _ORIGINAL_GIT and worker._guard is _ORIGINAL_GUARD
        and proof._Code is _ORIGINAL_CODE and proof._read_bootstrap is _ORIGINAL_READ, "startup_code")


def _phase(value, clock):
    global _STAGE
    require(value in _STAGES, "startup_arguments"); _STAGE = value; clock.check()


class _Clock:
    def __init__(self): self.start = self.last = time.monotonic(); self.check()
    def check(self):
        now = time.monotonic()
        require(type(now) in (int, float) and math.isfinite(now) and 0 <= self.start <= self.last <= now, "startup_clock")
        require(now - self.start <= MAX_SECONDS, "startup_deadline"); self.last = now


def _hash(value, size=64): return type(value) is str and re.fullmatch("[0-9a-f]{" + str(size) + "}", value) is not None


def _git_role(arguments, head):
    if type(arguments) is not list or not all(type(v) is str for v in arguments): return None
    if arguments == ["rev-parse", "--show-toplevel"]: return "root", 0
    if arguments == ["status", "--porcelain=v2", "--branch", "--no-ahead-behind", "--untracked-files=all"]: return "status", 0
    if arguments == ["rev-parse", "refs/remotes/origin/" + worker.BRANCH]: return "tracking", 0
    if arguments == ["ls-remote", "--refs", "origin", worker.REF]: return "actual_matching_ref", 0
    for ordinal, name in enumerate(CODE_FILES, 1):
        if arguments == ["show", head + ":" + name]: return "code_file", ordinal
    return None


def _git_failure(error, head):
    trace = BaseException.__traceback__.__get__(error, BaseException); found = []
    for unused in range(128):
        if trace is None: break
        frame = trace.tb_frame
        if frame.f_code is _GIT_CODE and frame.f_globals is worker.__dict__: found.append(frame)
        trace = trace.tb_next
    if trace is not None or len(found) != 1: return {"role": None, "code_ordinal": None, "returncode": None}
    frame = found[0]; arguments = frame.f_locals.get("arguments"); role = _git_role(arguments, head)
    if role is None: return {"role": None, "code_ordinal": None, "returncode": None}
    result = frame.f_locals.get("result"); number = None
    if type(result) is subprocess.CompletedProcess and type(result.args) is list and all(type(v) is str for v in result.args) and result.args == ["git", *arguments]:
        if type(result.returncode) is int and -32768 <= result.returncode <= 32767: number = result.returncode
    return {"role": role[0], "code_ordinal": role[1], "returncode": number}


def failure_summary(error, head):
    previous = _FAILURES.get(id(error))
    if previous is not None and previous[0] is error: return json.loads(previous[1])
    code = None
    if type(error) is StartupRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((v for v in _CODES if args[0] == "REFUSED: " + v), None)
    upstream = proof.failure_summary(error)
    number = OSError.errno.__get__(error, OSError) if isinstance(error, OSError) else None
    detail = {"stage": _STAGE, "stage_scope": "entered_phase_including_callbacks_not_forensic_cause",
        "category": "local_contract_refusal" if code or upstream["contract_code"] or upstream["upstream_contract_code"] else "local_os_error" if number in _ERRNOS else "unknown_local_error",
        "contract_code": code, "upstream_contract_code": upstream["contract_code"] or upstream["upstream_contract_code"],
        "errno_name": _ERRNOS.get(number) or upstream["errno_name"], "mismatching_fields": upstream["mismatching_fields"],
        "original_Git": _git_failure(error, head)}
    _FAILURES[id(error)] = error, canonical_json(detail); return detail


@contextmanager
def _fence(head, *, readonly=False):
    """Only the original finite Git argv may cross the subprocess boundary."""
    changed = []; count = [0]
    def replace(obj, name, value): changed.append((obj, name, getattr(obj, name))); setattr(obj, name, value)
    def denied(*args, **kwargs): raise StartupRefusal("REFUSED: startup_forbidden")
    original_run, original_popen = subprocess.run, subprocess.Popen
    def command(args, kwargs):
        require(type(args) is list and args[:1] == ["git"] and _git_role(args[1:], head) is not None, "startup_forbidden")
        require(kwargs.get("cwd") == ROOT and kwargs.get("env") == worker._environment()
            and kwargs.get("stdin") == subprocess.DEVNULL and kwargs.get("stderr") == subprocess.DEVNULL
            and kwargs.get("stdout") == subprocess.PIPE, "startup_forbidden")
    def run(args, **kwargs):
        require(set(kwargs) == {"cwd", "stdin", "stdout", "stderr", "env", "check", "timeout"}, "startup_forbidden")
        command(args, kwargs); count[0] += 1
        require(count[0] <= MAX_GIT and kwargs.get("timeout") == 30 and kwargs.get("check") is False, "startup_git_budget")
        return original_run(args, **kwargs)
    def popen(args, **kwargs):
        require(set(kwargs) == {"cwd", "stdin", "stdout", "stderr", "env"}, "startup_forbidden")
        command(args, kwargs); return original_popen(args, **kwargs)
    try:
        replace(subprocess, "run", run); replace(subprocess, "Popen", popen)
        for name in ("call", "check_call", "check_output"): replace(subprocess, name, denied)
        for name in ("connect", "connect_ex"): replace(socket.socket, name, denied)
        for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr"): replace(socket, name, denied)
        replace(proof.native.ctypes, "CDLL", denied)
        replace(proof, "_Volume", denied)
        if readonly:
            original_open, original_builtin, original_io = os.open, builtins.open, io.open
            def opened(path, flags, *args, **kwargs):
                if type(path) is str and path == "/dev/null" and type(flags) is int and flags == os.O_RDWR and not args and not kwargs:
                    before = os.stat("/dev/null", follow_symlinks=False)
                    require(stat.S_ISCHR(before.st_mode), "startup_forbidden")
                    fd = original_open(path, flags); primary = None
                    try:
                        current = os.fstat(fd); named = os.stat("/dev/null", follow_symlinks=False)
                        require(stat.S_ISCHR(current.st_mode) and stat.S_ISCHR(named.st_mode)
                            and (before.st_dev, before.st_ino, before.st_rdev) == (current.st_dev, current.st_ino, current.st_rdev)
                            == (named.st_dev, named.st_ino, named.st_rdev), "startup_forbidden")
                        return fd
                    except BaseException as error:
                        primary = error
                        proof._close(fd, primary); raise
                if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                    require(path == STATUS and flags == os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                        and not args and set(kwargs) == {"dir_fd"}
                        and proof._dir(os.fstat(kwargs["dir_fd"])) == proof._dir((ROOT / PARENT).lstat()), "startup_forbidden")
                return original_open(path, flags, *args, **kwargs)
            def fileopen(original, path, mode="r", *args, **kwargs):
                require(type(mode) is str and not any(v in mode for v in "wax+"), "startup_forbidden")
                return original(path, mode, *args, **kwargs)
            replace(os, "open", opened)
            replace(builtins, "open", lambda path, mode="r", *a, **k: fileopen(original_builtin, path, mode, *a, **k))
            replace(io, "open", lambda path, mode="r", *a, **k: fileopen(original_io, path, mode, *a, **k))
            for name in ("mkdir", "makedirs", "unlink", "remove", "rename", "replace", "link", "symlink", "chmod", "fchmod", "truncate", "ftruncate"):
                replace(os, name, denied)
        yield
    finally:
        for obj, name, original in reversed(changed): setattr(obj, name, original)


class _OwnCode:
    def __init__(self, head, remote, clock):
        self.head, self.remote, self.clock = head, remote, clock; self.fd = None
        self.path = ROOT / DRIVER
        try:
            require(self.path.resolve() == self.path, "startup_code")
            self.fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            info = os.fstat(self.fd); require(stat.S_ISREG(info.st_mode) and info.st_size <= 1024 ** 2, "startup_code")
            self.stamp = proof._stamp(info); self.raw = None; self.digest = self.audit()
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def audit(self):
        worker._guard(self.head, self.remote); self.clock.check(); self.named()
        proof._same(proof._stamp(os.fstat(self.fd)), self.stamp); os.lseek(self.fd, 0, os.SEEK_SET)
        raw = os.read(self.fd, 1024 ** 2 + 1)
        require(raw == worker._git(["show", self.head + ":" + DRIVER]) and (self.raw is None or raw == self.raw), "startup_code")
        proof._same(proof._stamp(os.fstat(self.fd)), self.stamp); self.raw = raw; self.clock.check(); return hash_bytes(raw)
    def named(self):
        require(self.path.resolve() == self.path, "startup_code"); proof._same(proof._stamp(self.path.lstat()), self.stamp)
    def close(self):
        fd, self.fd = self.fd, None
        if fd is not None: os.close(fd)


def _payload(head, remote, manifest, pin, observer):
    return {"schema": "si-native-startup-bootstrap-v5", "policy_sha256": POLICY_SHA256,
        "runtime_head": head, "actual_remote": remote, "code_manifest": manifest,
        "target_head": TARGET_HEAD, "target_remote": REMOTE, "target_spec_sha256": TARGET_SPEC,
        "target_manifest": TARGET_MANIFEST, "status_name": STATUS, "status_original_identity": list(proof._status_pin(pin)),
        "config_role": "input_only_live_branch_HEAD_status_unknown_until_original_guard", "observer": _observer_config(observer), "authority": authority()}


def build_launchd_plist(head, remote, digest, observer):
    require(_hash(head, 40) and remote == REMOTE and _hash(digest), "startup_arguments")
    return {"Label": LABEL, "ProgramArguments": [worker.PYTHON, "-B", "-m", MODULE, "run-readonly", "--head", head, "--remote", remote, "--spec-sha256", digest, "--observer", canonical_json(_observer_config(observer))],
        "WorkingDirectory": str(ROOT), "EnvironmentVariables": worker._environment(), "RunAtLoad": False,
        "KeepAlive": False, "Debug": True, "StandardOutPath": "/dev/null", "StandardErrorPath": _observer_config(observer)["slave_path"]}


def _protected(info, maximum=MAX_CONFIG):
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
        and info.st_nlink == 1 and 0 < info.st_size <= maximum, "startup_config")
    return proof._stamp(info)


class _Inputs:
    """Exact two-role configuration reauthentication, never an evidence seal.

    Original identity, protection, size and expected bytes never change. Each
    separate read has its own full9 FD/name barrier through its original close.
    Timestamps between operations are observations, not source custody evidence.
    """
    ROLES = ("launch.spec.json", "job.plist")
    def __init__(self, directory):
        require(type(directory) is proof._Directory and directory.path == ROOT / PARENT / BOOTSTRAP, "startup_config")
        directory.check(); self.directory, self.rows = directory, {}
    def _membership(self, named=False):
        self.directory.named() if named else self.directory.check()
        require(set(os.listdir(self.directory.path if named else self.directory.fd)) == set(self.ROLES), "startup_membership")
    def read(self, name, *, expected=None, original_pin=None, named=False):
        require(type(name) is str and name in self.ROLES, "startup_config"); self._membership(named)
        existing = self.rows.get(name)
        require(existing is None or expected is original_pin is None, "startup_config")
        if existing is not None:
            pin, expected, digest = existing
            require(hash_bytes(expected) == digest, "startup_config")
        else:
            require(expected is None or type(expected) is bytes and 0 < len(expected) <= MAX_CONFIG, "startup_config")
            require(original_pin is None or type(original_pin) is tuple and len(original_pin) == 7
                and all(type(v) is int for v in original_pin), "startup_config")
            pin = original_pin
        path = self.directory.path / name
        info = path.lstat() if named else os.stat(name, dir_fd=self.directory.fd, follow_symlinks=False)
        before = _protected(info)
        require(pin is None or before[:7] == pin, "startup_config")
        pin = before[:7] if pin is None else pin
        fd = os.open(path if named else name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            **({} if named else {"dir_fd": self.directory.fd})); primary = None
        try:
            require(_protected(os.fstat(fd))[:7] == pin, "startup_config")
            proof._same(proof._stamp(os.fstat(fd)), before); proof._same(proof._stamp(path.lstat()), before)
            raw = os.read(fd, MAX_CONFIG + 1)
            require(len(raw) == pin[6] and (expected is None or raw == expected), "startup_config")
            proof._same(proof._stamp(os.fstat(fd)), before); proof._same(proof._stamp(path.lstat()), before)
        except BaseException as error: primary = error; raise
        finally: proof._close(fd, primary)
        require(_protected(path.lstat())[:7] == pin, "startup_config")
        proof._same(proof._stamp(path.lstat()), before)  # This reader's close remains inside its full9 barrier.
        self.directory.named() if named else self.directory.check()
        if existing is None: self.rows[name] = pin, raw, hash_bytes(raw)
        return raw
    def audit(self, named=False):
        require(set(self.rows) == set(self.ROLES), "startup_config")
        self._membership(named)
        for name in self.ROLES: self.read(name, named=named)
    def close(self):
        pass  # Each original read FD is closed exactly once by that operation.


def _config_write(directory, name, raw):
    require(name in ("launch.spec.json", "job.plist") and type(raw) is bytes and 0 < len(raw) <= MAX_CONFIG, "startup_config")
    directory.check(); fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory.fd); primary = None
    try:
        os.fchmod(fd, 0o600); before = proof._stamp(os.fstat(fd))
        require(before[4:7] == (0o600, 1, 0), "startup_config"); proof._same(proof._stamp(os.stat(name, dir_fd=directory.fd, follow_symlinks=False)), before)
        proof._write(fd, raw); os.fsync(fd); os.fsync(directory.fd); os.fsync(directory.parent)
        stamp = _protected(os.fstat(fd)); proof._same(proof._stamp(os.stat(name, dir_fd=directory.fd, follow_symlinks=False)), stamp)
        os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "startup_config"); proof._same(proof._stamp(os.fstat(fd)), stamp)
        pin = stamp[:7]
    except BaseException as error: primary = error; raise
    finally: proof._close(fd, primary)
    # Configuration timestamps across separate operations confer no evidence cap.
    require(_protected(os.stat(name, dir_fd=directory.fd, follow_symlinks=False))[:7] == pin, "startup_config")
    return pin


class _Status:
    def __init__(self): self.fd = self.parent = self.pin = self.parent_pin = None; self.failed = self.attempted = False
    def bind(self, directory, pin):
        require(self.fd is None and self.pin is None and not self.failed, "startup_status")
        try:
            self.pin = proof._status_pin(pin); directory.check(); self.parent_pin = proof._dir(os.fstat(directory.parent)); self.parent = os.dup(directory.parent)
            before = os.stat(STATUS, dir_fd=self.parent, follow_symlinks=False)
            require(proof._status_identity(before) == self.pin, "startup_status")
            stamp = proof._stamp(before); self.fd = os.open(STATUS, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.parent)
            proof._same(proof._stamp(os.fstat(self.fd)), stamp); self.check(0)
        except BaseException:
            self.failed = True
            try: self.close()
            except BaseException: pass
            raise
    def check(self, size):
        require(not self.failed and self.fd is not None and self.parent is not None, "startup_status")
        path = ROOT / PARENT; require(path.resolve() == path and proof._dir(path.lstat()) == proof._dir(os.fstat(self.parent)) == self.parent_pin, "startup_status")
        left, right = os.fstat(self.fd), os.stat(STATUS, dir_fd=self.parent, follow_symlinks=False)
        require(proof._status_identity(left, size)[:6] == self.pin[:6] == proof._status_identity(right, size)[:6], "startup_status")
        proof._same(proof._stamp(left), proof._stamp(right))
    def emit(self, detail):
        require(not self.attempted, "startup_status"); self.attempted = True
        if detail is not None:
            keys = {"stage", "stage_scope", "category", "contract_code", "upstream_contract_code", "errno_name", "mismatching_fields", "original_Git"}
            require(type(detail) is dict and all(type(v) is str for v in detail) and set(detail) == keys and type(detail["stage"]) is str and detail["stage"] in _STAGES
                and type(detail["stage_scope"]) is str and detail["stage_scope"] == "entered_phase_including_callbacks_not_forensic_cause"
                and type(detail["category"]) is str and detail["category"] in ("local_contract_refusal", "local_os_error", "unknown_local_error")
                and (detail["contract_code"] is None or type(detail["contract_code"]) is str and detail["contract_code"] in _CODES)
                and (detail["upstream_contract_code"] is None or type(detail["upstream_contract_code"]) is str and detail["upstream_contract_code"] in proof._CODES | worker._CODES | proof.native._CODES)
                and (detail["errno_name"] is None or type(detail["errno_name"]) is str and detail["errno_name"] in set(_ERRNOS.values()) | set(proof._ERRNOS.values()) | set(worker._ERRNOS.values()) | set(proof.native._ERRNOS.values()))
                and type(detail["mismatching_fields"]) is list and len(detail["mismatching_fields"]) <= 9
                and all(type(v) is str and v in proof._STAMP_NAMES for v in detail["mismatching_fields"]), "startup_status")
            git = detail["original_Git"]
            require(type(git) is dict and all(type(v) is str for v in git) and set(git) == {"role", "code_ordinal", "returncode"}
                and (git["role"] is None or type(git["role"]) is str and git["role"] in ("root", "status", "tracking", "actual_matching_ref", "code_file"))
                and (git["code_ordinal"] is None or type(git["code_ordinal"]) is int and 0 <= git["code_ordinal"] <= 6)
                and (git["returncode"] is None or type(git["returncode"]) is int and -32768 <= git["returncode"] <= 32767), "startup_status")
        try:
            self.check(0)
            raw = canonical_json({"schema": "si-native-startup-observation-v5", "status": "refused" if detail is not None else "readonly_predicates_passed_observation_only",
                "failure": detail, "authority": authority()}).encode() + b"\n"
            require(0 < len(raw) <= MAX_STATUS and raw.count(b"\n") == 1, "startup_status")
            proof._write(self.fd, raw); os.fsync(self.fd); self.check(len(raw))
        except BaseException: self.failed = True; raise
    def close(self):
        first = None; before = None
        if self.fd is not None and not self.failed:
            try:
                info = os.fstat(self.fd); self.check(info.st_size); before = proof._stamp(info)
            except BaseException as error: first = error
        fd, self.fd = self.fd, None
        if fd is not None:
            try: os.close(fd)
            except BaseException as error:
                if first is None: first = error
        if first is None and before is not None:
            try: proof._same(proof._stamp(os.stat(STATUS, dir_fd=self.parent, follow_symlinks=False)), before)
            except BaseException as error: first = error
        parent, self.parent = self.parent, None
        if parent is not None:
            try: os.close(parent)
            except BaseException as error:
                if first is None: first = error
        if first is not None: self.failed = True; raise first


def _prepare_status(directory):
    directory.check(); fd = os.open(STATUS, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory.parent); primary = None
    try:
        os.fchmod(fd, 0o600); pin = proof._status_identity(os.fstat(fd)); require(proof._status_identity(os.stat(STATUS, dir_fd=directory.parent, follow_symlinks=False)) == pin, "startup_status")
        os.fsync(fd); os.fsync(directory.parent)
    except BaseException as error: primary = error; raise
    finally: proof._close(fd, primary)
    require(proof._status_identity(os.stat(STATUS, dir_fd=directory.parent, follow_symlinks=False)) == pin, "startup_status"); return pin


def prepare_readonly(head, remote, observer):
    registered(); require(_hash(head, 40) and remote == REMOTE, "startup_arguments")
    with _fence(head): return _prepare_readonly(head, remote, _observer_config(observer))


def _prepare_readonly(head, remote, observer):
    clock = _Clock()
    directory = code = own = inputs = None; failure = None
    try:
        _phase("live_guard", clock); worker._guard(head, remote)
        _phase("current_code", clock); code = proof._Code(head, remote, clock); own = _OwnCode(head, remote, clock)
        require(code.manifest == TARGET_MANIFEST, "startup_code")
        manifest = {**code.manifest, DRIVER: own.digest}
        _phase("config_auth", clock); directory = proof._Directory(BOOTSTRAP, create=True); pin = _prepare_status(directory)
        raw = canonical_json(_payload(head, remote, manifest, pin, observer)).encode(); digest = hash_bytes(raw)
        job_raw = plistlib.dumps(build_launchd_plist(head, remote, digest, observer), sort_keys=True)
        spec_pin = _config_write(directory, "launch.spec.json", raw)
        job_pin = _config_write(directory, "job.plist", job_raw)
        inputs = _Inputs(directory)
        require(inputs.read("launch.spec.json", expected=raw, original_pin=spec_pin) == raw, "startup_config")
        require(inputs.read("job.plist", expected=job_raw, original_pin=job_pin) == job_raw, "startup_config")
        _phase("terminal_code", clock); code.audit(); own.audit(); worker._guard(head, remote)
        _phase("original_audit", clock); inputs.audit()
    except BaseException as error: failure = error; failure_summary(error, head); raise
    finally:
        first = failure
        try: _phase("cleanup", clock)
        except BaseException as error:
            if first is None: first = error; failure_summary(error, head)
        for obj in (inputs, directory, own, code):
            if obj is not None:
                try: obj.close()
                except BaseException as error:
                    if first is None: first = error; failure_summary(error, head)
        if failure is None and first is not None: raise first
    _phase("named_audit", clock); code.named(); own.named(); inputs.audit(named=True); clock.check()
    _PREPARED_INPUTS[(head, remote, digest, observer["nonce"])] = tuple((name, *inputs.rows[name]) for name in inputs.ROLES)
    return {"status": "prepared_readonly_not_submitted", "spec_sha256": digest, "authority": authority()}


def run_readonly(head, remote, digest, observer):
    global _USED
    registered(); require(not _USED and _hash(head, 40) and remote == REMOTE and _hash(digest), "startup_arguments"); _USED = True
    with _fence(head, readonly=True): return _run_readonly(head, remote, digest, _observer_config(observer))


def _run_readonly(head, remote, digest, observer):
    clock = _Clock(); directory = inputs = status = code = own = target = None; target_fds = []; failure = None
    try:
        # No Git or code command precedes these fixed original config inputs.
        _phase("config_auth", clock); directory = proof._Directory(BOOTSTRAP, create=False); inputs = _Inputs(directory)
        raw = inputs.read("launch.spec.json"); require(hash_bytes(raw) == digest, "startup_config")
        payload = json.loads(raw); require(type(payload) is dict, "startup_config")
        manifest = payload.get("code_manifest"); pin = payload.get("status_original_identity")
        require(type(manifest) is dict and set(manifest) == set(CODE_FILES) and all(_hash(v) for v in manifest.values())
            and {k: manifest[k] for k in proof.CODE_FILES} == TARGET_MANIFEST, "startup_config")
        require(raw == canonical_json(_payload(head, remote, manifest, pin, observer)).encode(), "startup_config")
        require(inputs.read("job.plist") == plistlib.dumps(build_launchd_plist(head, remote, digest, observer), sort_keys=True), "startup_config"); inputs.audit()
        _phase("status_bind", clock); status = _Status(); status.bind(directory, pin)
        _phase("live_guard", clock); worker._guard(head, remote)
        _phase("current_code", clock); code = proof._Code(head, remote, clock); own = _OwnCode(head, remote, clock)
        require({**code.manifest, DRIVER: own.digest} == manifest, "startup_code")
        _phase("historical_config", clock); target, target_fds = proof._read_bootstrap(TARGET_HEAD, REMOTE, TARGET_MANIFEST, TARGET_SPEC)
        _phase("terminal_code", clock); code.audit(); own.audit(); worker._guard(head, remote)
        _phase("original_audit", clock); proof._bootstrap_audit(target); inputs.audit(); status.check(0); clock.check()
    except BaseException as error: failure = error; failure_summary(error, head)
    finally:
        # Preserve the first original error; cleanup always attempts all originals.
        try: _phase("cleanup", clock)
        except BaseException as error:
            if failure is None: failure = error; failure_summary(error, head)
        for close in ([lambda: proof._drain(target_fds)] + [obj.close for obj in (target, own, code, inputs, directory) if obj is not None]):
            try: close()
            except BaseException as error:
                if failure is None: failure = error; failure_summary(error, head)
        if failure is None:
            try:
                _phase("named_audit", clock); code.named(); own.named(); proof._bootstrap_audit(target, named=True); inputs.audit(named=True); status.check(0); clock.check()
            except BaseException as error: failure = error; failure_summary(error, head)
        if status is not None:
            try:
                _phase("status_publication", clock); status.emit(failure_summary(failure, head) if failure is not None else None)
            except BaseException as error:
                if failure is None: failure = error; failure_summary(error, head)
            try: status.close()
            except BaseException as error:
                if failure is None: failure = error; failure_summary(error, head)
        try: clock.check()
        except BaseException as error:
            if failure is None: failure = error; failure_summary(error, head)
    if failure is not None: raise failure
    return {"status": "readonly_predicates_passed_observation_only", "authority": authority()}



def _observer_fd(): return 2


def _tty_pin(fd):
    info = os.fstat(fd)
    require(stat.S_ISCHR(info.st_mode) and os.isatty(fd), "startup_observer")
    return (info.st_dev, info.st_ino, info.st_rdev, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))



def _tty_check(fd, config):
    """Existing Root-owned slave endpoint; no creation or exclusive-writer claim."""
    expected = tuple(config["terminal"]); name = config["slave_path"]; path = Path(name)
    require(type(name) is str and name == os.ttyname(fd) and path.is_absolute()
        and ((path.parent == Path("/dev") and re.fullmatch(r"ttys[0-9A-Za-z]+", path.name) is not None)
            or (path.parent == Path("/dev/pts") and path.name.isdecimal())), "startup_observer")
    require(path.resolve() == path, "startup_observer")
    for parent in (Path("/dev"), *([path.parent] if path.parent != Path("/dev") else [])):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not stat.S_IMODE(info.st_mode) & 0o022, "startup_observer")
    require(_tty_pin(fd) == expected, "startup_observer")
    info = path.lstat()
    require(stat.S_ISCHR(info.st_mode)
        and (info.st_dev, info.st_ino, info.st_rdev, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == expected, "startup_observer")
    return expected

def _observer_config(value):
    require(type(value) is dict and set(value) == {"nonce", "terminal", "slave_path"}
        and type(value["slave_path"]) is str and 0 < len(value["slave_path"]) <= 128
        and _hash(value["nonce"], 32) and type(value["terminal"]) in (tuple, list) and len(value["terminal"]) == 6
        and all(type(v) is int and 0 <= v <= 2 ** 64 for v in value["terminal"]), "startup_observer")
    return {"nonce": value["nonce"], "terminal": list(value["terminal"]), "slave_path": value["slave_path"]}


class _Observer:
    """Root-argv endpoint observation, never an exclusive writer/source proof."""
    def __init__(self, config, digest):
        self.config = _observer_config(config); require(_hash(digest), "startup_observer")
        self.digest, self.fd, self.attempted = digest, _observer_fd(), False
        _tty_check(self.fd, self.config)
    def emit(self, detail):
        require(not self.attempted, "startup_observer"); self.attempted = True
        _tty_check(self.fd, self.config)
        if detail is not None: _validate_detail(detail)
        payload = {"schema": "si-startup-PTY-observation-v5", "nonce": self.config["nonce"],
            "spec_sha256": self.digest, "pid": os.getpid(),
            "status": "refused" if detail is not None else "readonly_predicates_passed_observation_only",
            "failure": detail, "authority": authority()}
        raw = canonical_json(payload).encode() + b"\n"
        require(0 < len(raw) <= MAX_STATUS and raw.count(b"\n") == 1, "startup_observer")
        # One nonblocking attempt, no deadline gate on a negative diagnostic.
        os.set_blocking(self.fd, False)
        written = os.write(self.fd, raw)
        require(type(written) is int and written == len(raw), "startup_observer")


def filter_observer(raw, config, digest, pid):
    """Raw startup/OS text stays private and cannot become a reported finding."""
    unavailable = {"status": "observer_unavailable", "authority": authority()}
    try:
        expected = _observer_config(config)
        if type(raw) is not bytes or len(raw) > MAX_RAW or raw.count(b"\n") != 1 or len(raw) > MAX_STATUS: return unavailable
        value = json.loads(raw)
        if type(value) is not dict or set(value) != {"schema", "nonce", "spec_sha256", "pid", "status", "failure", "authority"}: return unavailable
        if raw != canonical_json(value).encode() + b"\n" or value["schema"] != "si-startup-PTY-observation-v5" or value["nonce"] != expected["nonce"] or value["spec_sha256"] != digest: return unavailable
        if type(pid) is not int or pid <= 0 or type(value["pid"]) is not int or value["pid"] != pid or value["authority"] != authority(): return unavailable
        if value["status"] not in ("refused", "readonly_predicates_passed_observation_only"): return unavailable
        detail = value["failure"]
        if (value["status"] == "refused") != (type(detail) is dict): return unavailable
        if detail is not None:
            # Validate using the same exact fixed-domain projection as the subject
            # reporter, without constructing/opening an observation file.
            _validate_detail(detail)
        return value
    except BaseException: return unavailable


def _validate_detail(detail):
    keys = {"stage", "stage_scope", "category", "contract_code", "upstream_contract_code", "errno_name", "mismatching_fields", "original_Git"}
    require(type(detail) is dict and set(detail) == keys and all(type(k) is str for k in detail)
        and type(detail["stage"]) is str and detail["stage"] in _STAGES
        and detail["stage_scope"] == "entered_phase_including_callbacks_not_forensic_cause"
        and type(detail["category"]) is str and detail["category"] in ("local_contract_refusal", "local_os_error", "unknown_local_error")
        and (detail["contract_code"] is None or type(detail["contract_code"]) is str and detail["contract_code"] in _CODES)
        and (detail["upstream_contract_code"] is None or type(detail["upstream_contract_code"]) is str and detail["upstream_contract_code"] in proof._CODES | worker._CODES | proof.native._CODES)
        and (detail["errno_name"] is None or type(detail["errno_name"]) is str and detail["errno_name"] in set(_ERRNOS.values()) | set(proof._ERRNOS.values()) | set(worker._ERRNOS.values()) | set(proof.native._ERRNOS.values()))
        and type(detail["mismatching_fields"]) is list and len(detail["mismatching_fields"]) <= 9
        and all(type(k) is str and k in proof._STAMP_NAMES for k in detail["mismatching_fields"]), "startup_observer")
    git = detail["original_Git"]
    require(type(git) is dict and set(git) == {"role", "code_ordinal", "returncode"}
        and (git["role"] is None or type(git["role"]) is str and git["role"] in ("root", "status", "tracking", "actual_matching_ref", "code_file"))
        and (git["code_ordinal"] is None or type(git["code_ordinal"]) is int and 0 <= git["code_ordinal"] <= 6)
        and (git["returncode"] is None or type(git["returncode"]) is int and -32768 <= git["returncode"] <= 32767), "startup_observer")




@contextmanager
def _controller_scope():
    changed = []
    def denied(*args, **kwargs): raise StartupRefusal("REFUSED: startup_forbidden")
    def replace(obj, name): changed.append((obj, name, getattr(obj, name))); setattr(obj, name, denied)
    try:
        for name in ("connect", "connect_ex"): replace(socket.socket, name)
        for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr"): replace(socket, name)
        replace(proof.native.ctypes, "CDLL"); replace(proof, "_Volume")
        yield
    finally:
        for obj, name, value in reversed(changed): setattr(obj, name, value)

def _target(): return "gui/" + str(os.getuid()) + "/" + LABEL


def _launch_argv(role):
    values = {"query": ["print", _target()], "load": ["bootstrap", "gui/" + str(os.getuid()), str(ROOT / PARENT / BOOTSTRAP / "job.plist")],
        "start": ["kickstart", "-p", _target()]}
    require(type(role) is str and role in values, "startup_control"); return [LAUNCHCTL, *values[role]]


def _launch(role):
    """Finite exact argv only; raw native text is private and never formatted."""
    result = subprocess.run(_launch_argv(role), cwd=ROOT, env=worker._environment(),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30, shell=False)
    require(type(result) is subprocess.CompletedProcess and type(result.returncode) is int
        and -32768 <= result.returncode <= 32767 and result.args == _launch_argv(role), "startup_control")
    require(type(result.stdout) is bytes and len(result.stdout) <= MAX_RAW, "startup_control")
    return result


def _kernel(raw):
    require(type(raw) is bytes and len(raw) <= MAX_RAW, "startup_control_state")
    text = raw.decode("utf-8"); result = {}
    require(text.splitlines()[:1] == [_target() + " = {"], "startup_control_state")
    paths = re.findall(r"(?m)^\tpath = ([^\r\n]+)$", text)
    require(paths == [str(ROOT / PARENT / BOOTSTRAP / "job.plist")], "startup_control_state")
    for key, label, pattern in (("runs", "runs", r"(?m)^\truns = ([0-9]+)[ \t]*$"),
        ("state", "state", r"(?m)^\tstate = ([a-z ]+)[ \t]*$"),
        ("active_count", "active count", r"(?m)^\tactive count = ([0-9]+)[ \t]*$"),
        ("pid", "pid", r"(?m)^\tpid = ([0-9]+)[ \t]*$")):
        values = re.findall(pattern, text)
        require(len(values) <= 1 and len(re.findall(r"(?m)^\t" + label + r" =", text)) == len(values), "startup_control_state")
        result[key] = values[0] if values else None
    exits = re.findall(r"(?m)^\tlast exit code = ([^\r\n]+)$", text)
    require(len(exits) <= 1 and len(re.findall(r"(?m)^\tlast exit code =", text)) == len(exits), "startup_control_state")
    exit_code = None; never_exited = exits == ["(never exited)"]
    if exits and not never_exited:
        numeric = re.fullmatch(r"(-?[0-9]+)(?:: ([A-Z_]+))?[ \t]*", exits[0])
        require(numeric is not None, "startup_control_state")
        exit_code = int(numeric[1]); symbol = numeric[2]
        require(not symbol or _SYSEXITS.get(exit_code) == symbol, "startup_control_state")
    require(result["runs"] is not None and result["active_count"] is not None
        and result["state"] in ("running", "not running"), "startup_control_state")
    value = {"runs": int(result["runs"]), "running": result["state"] == "running", "active_count": int(result["active_count"]),
        "pid": int(result["pid"]) if result["pid"] is not None else None, "exit": exit_code}
    require(not never_exited or value["runs"] == 0 and value["running"] is False
        and value["active_count"] == 0 and value["pid"] is None, "startup_control_state")
    require(value["runs"] in (0, 1) and value["active_count"] in (0, 1)
        and (value["pid"] is None or 0 < value["pid"] < 2 ** 31)
        and (value["exit"] is None or -32768 <= value["exit"] <= 32767), "startup_control_state")
    return value


def _query_result(head):
    with _fence(head): worker._snapshot(head)
    return _launch("query")


def _query(head):
    result = _query_result(head); require(result.returncode == 0, "startup_control_state"); return _kernel(result.stdout)


def _never_started(value):
    require(value["runs"] == 0 and value["running"] is False and value["active_count"] == 0 and value["pid"] is None, "startup_control_state")


def _control_guard(head, remote):
    with _fence(head): worker._guard(head, remote)


def _control_message(fd, value):
    require(type(fd) is int and fd > 2 and stat.S_ISFIFO(os.fstat(fd).st_mode)
        and fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_WRONLY, "startup_control")
    raw = canonical_json(value).encode() + b"\n"
    require(0 < len(raw) <= MAX_CONFIG, "startup_control"); proof._write(fd, raw)


def control_readonly(head, remote, digest, observer, control_fd, ack_fd, config_pins):
    with _controller_scope(): return _control_readonly(head, remote, digest, observer, control_fd, ack_fd, config_pins)


def _control_readonly(head, remote, digest, observer, control_fd, ack_fd, config_pins):
    """One persistent child owns the controlling session through target exit."""
    require(os.name == "posix" and fcntl is not None and termios is not None, "startup_observer")
    observer = _observer_config(observer); clock = _Clock(); failure = None; pid = None; kernel = None
    code = own = None
    try:
        require(_tty_check(0, observer) == _tty_check(1, observer) == _tty_check(2, observer)
            and os.getsid(0) == os.getpid(), "startup_observer")
        fcntl.ioctl(2, termios.TIOCSCTTY, 0)
        registered(); require(_hash(head, 40) and remote == REMOTE and _hash(digest), "startup_arguments")
        with _fence(head):
            worker._guard(head, remote); code = proof._Code(head, remote, clock); own = _OwnCode(head, remote, clock)
            require(code.manifest == TARGET_MANIFEST, "startup_code")
        kernel = _query(head); _never_started(kernel); _control_guard(head, remote)
        _phase("controller_prestart", clock)
        _controller_config(head, remote, digest, observer, config_pins, {**code.manifest, DRIVER: own.digest}); _tty_check(2, observer)
        _never_started(_query(head)); _phase("controller_barrier", clock)
        _control_message(control_fd, {"schema": "si-startup-prestart-barrier-v5", "nonce": observer["nonce"],
            "spec_sha256": digest, "control_pid": os.getpid(), "status": "runs0_before_initial_start"})
        require(type(ack_fd) is int and ack_fd > 2 and stat.S_ISFIFO(os.fstat(ack_fd).st_mode)
            and fcntl.fcntl(ack_fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY, "startup_control")
        require(os.read(ack_fd, 1) == b"1", "startup_control")
        _control_guard(head, remote)
        _controller_config(head, remote, digest, observer, config_pins, {**code.manifest, DRIVER: own.digest})
        _never_started(_query(head))
        _phase("controller_initial_start", clock); _tty_check(2, observer)
        started = _launch("start"); require(started.returncode == 0 and re.fullmatch(rb"[1-9][0-9]{0,9}\n?", started.stdout) is not None, "startup_control")
        pid = int(started.stdout); require(pid < 2 ** 31, "startup_control")
        _phase("controller_terminal", clock)
        for unused in range(MAX_POLLS):
            kernel = _query(head)
            require(kernel["runs"] in (0, 1) and (kernel["pid"] is None or kernel["pid"] == pid), "startup_control_state")
            if kernel["runs"] == 1 and not kernel["running"] and kernel["active_count"] == 0 and kernel["exit"] is not None: break
            clock.check(); time.sleep(1)
        require(kernel is not None and kernel["runs"] == 1 and not kernel["running"] and kernel["active_count"] == 0 and kernel["exit"] is not None, "startup_control_unknown")
        with _fence(head): code.audit(); own.audit(); worker._guard(head, remote)
        _tty_check(2, observer); clock.check()
    except BaseException as error: failure = error; failure_summary(error, head)
    finally:
        for obj in (own, code):
            if obj is not None:
                try: obj.close()
                except BaseException as error:
                    if failure is None: failure = error; failure_summary(error, head)
        if failure is None:
            try: code.named(); own.named(); clock.check()
            except BaseException as error: failure = error; failure_summary(error, head)
        # Target may be unknown. Never kill/restart; parent retains original PTY
        # and child handle and independently queries the exact fresh service.
        message = {"schema": "si-startup-control-v5", "nonce": observer["nonce"], "spec_sha256": digest,
            "control_pid": os.getpid(), "target_pid": pid, "kernel": kernel,
            "status": "refused" if failure is not None else "terminal_observed", "failure": failure_summary(failure, head) if failure is not None else None,
            "authority": authority()}
        try:
            _control_message(control_fd, message)
            require(os.read(ack_fd, 1) == b"2", "startup_control")  # Root has captured independent terminal state and raw transport.
        except BaseException as error:
            if failure is None: failure = error; failure_summary(error, head)
        for fd in (ack_fd, control_fd):
            if fd is not None:
                try: os.close(fd)
                except BaseException as error:
                    if failure is None: failure = error; failure_summary(error, head)
    if failure is not None: raise failure
    return message


def _private_read(fd, buffer):
    try: block = os.read(fd, 4096)
    except BlockingIOError: return buffer, False
    if not block: return buffer, True
    return (buffer + block)[:MAX_RAW + 4096], False


def _hold_private_controller(state):
    _CONTROLLER_HELD.append(state)
    while True:
        # Preserve original endpoints and keep draining privately, including after
        # acceptance expires. This never retries a command or admits a result.
        for name, key in (("master", "raw"), ("read_fd", "control")):
            fd = state[name]
            if fd is not None:
                try: state[key], unused_eof = _private_read(fd, state[key])
                except BaseException: state["transport_unavailable"] = True
        time.sleep(0.1)


def observe_readonly(head, remote):
    with _controller_scope(): return _observe_readonly(head, remote)



class _LoadInputs:
    """One original canonical config consumption epoch, not source authority."""
    def __init__(self, head, remote, digest, observer):
        key = (head, remote, digest, observer["nonce"])
        require(key in _PREPARED_INPUTS, "startup_config")
        original = _PREPARED_INPUTS[key]
        require(type(original) is tuple and tuple(row[0] for row in original) == _Inputs.ROLES, "startup_config")
        self.directory = None; self.rows, self.fds, self.ancestry = [], [], []
        try:
            self.directory = proof._Directory(BOOTSTRAP, create=False)
            self.ancestry = [(path, fd, proof._stamp(os.fstat(fd))) for path, fd, unused_pin in self.directory.nodes]
            for name, pin, raw, digest_value in original:
                require(hash_bytes(raw) == digest_value, "startup_config")
                info = os.stat(name, dir_fd=self.directory.fd, follow_symlinks=False)
                stamp = _protected(info); require(stamp[:7] == pin, "startup_config")
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory.fd); self.fds.append(fd)
                proof._same(proof._stamp(os.fstat(fd)), stamp)
                require(os.read(fd, len(raw) + 1) == raw, "startup_config")
                proof._same(proof._stamp(os.fstat(fd)), stamp)
                self.rows.append((name, fd, stamp, raw))
            self.audit()
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def audit(self):
        self.directory.check(); require(set(os.listdir(self.directory.fd)) == set(_Inputs.ROLES), "startup_membership")
        for path, fd, stamp in self.ancestry:
            proof._same(proof._stamp(os.fstat(fd)), stamp); proof._same(proof._stamp(path.lstat()), stamp)
        for name, fd, stamp, raw in self.rows:
            proof._same(proof._stamp(os.stat(name, dir_fd=self.directory.fd, follow_symlinks=False)), stamp)
            proof._same(proof._stamp(os.fstat(fd)), stamp); os.lseek(fd, 0, os.SEEK_SET)
            require(os.read(fd, len(raw) + 1) == raw, "startup_config")
            proof._same(proof._stamp(os.fstat(fd)), stamp)
            proof._same(proof._stamp(os.stat(name, dir_fd=self.directory.fd, follow_symlinks=False)), stamp)
    def close(self):
        first = None
        try: proof._drain(self.fds)
        except BaseException as error: first = error
        if self.directory is not None:
            try:
                for name, unused, stamp, unused_raw in self.rows:
                    proof._same(proof._stamp((self.directory.path / name).lstat()), stamp)
            except BaseException as error:
                if first is None: first = error
            try: self.directory.close()
            except BaseException as error:
                if first is None: first = error
            try:
                self.directory.named()
                for path, unused, stamp in self.ancestry: proof._same(proof._stamp(path.lstat()), stamp)
                for name, unused, stamp, unused_raw in self.rows: proof._same(proof._stamp((self.directory.path / name).lstat()), stamp)
            except BaseException as error:
                if first is None: first = error
        if first is not None: raise first


def _creator_pins(head, remote, digest, observer):
    key = (head, remote, digest, observer["nonce"]); require(key in _PREPARED_INPUTS, "startup_config")
    return {name: list(pin) for name, pin, unused_raw, unused_hash in _PREPARED_INPUTS[key]}


def _controller_config(head, remote, digest, observer, pins, manifest):
    require(type(pins) is dict and set(pins) == set(_Inputs.ROLES), "startup_config")
    directory = inputs = None; primary = None
    try:
        directory = proof._Directory(BOOTSTRAP, create=False); inputs = _Inputs(directory)
        expected = {"job.plist": plistlib.dumps(build_launchd_plist(head, remote, digest, observer), sort_keys=True), "launch.spec.json": None}
        for name in _Inputs.ROLES:
            require(type(pins[name]) is list and len(pins[name]) == 7 and all(type(v) is int for v in pins[name]), "startup_config")
            raw = inputs.read(name, expected=expected[name], original_pin=tuple(pins[name]))
            if name == "launch.spec.json":
                require(hash_bytes(raw) == digest and raw == canonical_json(_payload(head, remote, manifest, proof._status_pin(json.loads(raw)["status_original_identity"]), observer)).encode(), "startup_config")
        inputs.audit()
    except BaseException as error: primary = error; raise
    finally:
        first = primary
        for obj in (inputs, directory):
            if obj is not None:
                try: obj.close()
                except BaseException as error:
                    if first is None: first = error
        if primary is None and first is not None: raise first
    inputs.audit(named=True)


def _control_receipt(value, observer, digest, pid):
    require(type(value) is dict and set(value) == {"schema", "nonce", "spec_sha256", "control_pid", "target_pid", "kernel", "status", "failure", "authority"}
        and value["schema"] == "si-startup-control-v5" and value["nonce"] == observer["nonce"]
        and value["spec_sha256"] == digest and type(value["control_pid"]) is int and value["control_pid"] == pid
        and value["authority"] == authority() and value["status"] in ("terminal_observed", "refused"), "startup_control")
    require(value["target_pid"] is None or type(value["target_pid"]) is int and 0 < value["target_pid"] < 2 ** 31, "startup_control")
    if value["status"] == "refused": _validate_detail(value["failure"])
    else: require(value["failure"] is None, "startup_control")
    kernel = value["kernel"]
    if kernel is not None:
        require(type(kernel) is dict and set(kernel) == {"runs", "running", "active_count", "pid", "exit"}
            and type(kernel["runs"]) is int and kernel["runs"] in (0, 1) and type(kernel["running"]) is bool
            and type(kernel["active_count"]) is int and kernel["active_count"] in (0, 1)
            and (kernel["pid"] is None or type(kernel["pid"]) is int and 0 < kernel["pid"] < 2 ** 31)
            and (kernel["exit"] is None or type(kernel["exit"]) is int and -32768 <= kernel["exit"] <= 32767), "startup_control")
    return value


def _drain_to_eagain(fd, raw):
    for unused in range(32):
        try: block = os.read(fd, 4096)
        except BlockingIOError: return raw
        if not block: return raw
        raw = (raw + block)[:MAX_RAW + 4096]
    raise StartupRefusal("REFUSED: startup_control_unknown")


def _observe_readonly(head, remote):
    """Root CLI owns one private PTY. No raw child output reaches its caller."""
    require(os.name == "posix" and fcntl is not None and termios is not None and hasattr(os, "openpty"), "startup_observer")
    registered(); require(_hash(head, 40) and remote == REMOTE, "startup_arguments")
    _control_guard(head, remote); clock = _Clock(); master = slave = read_fd = write_fd = ack_read = ack_write = None
    process = None; raw = control = b""; failure = None; kernel = None; child_exit = None; loaded = False; receipt = None
    try:
        require(_query_result(head).returncode == 113, "startup_control_state")
        master, slave = os.openpty(); os.set_blocking(master, False)
        settings = termios.tcgetattr(slave); settings[1] &= ~termios.ONLCR; settings[3] &= ~termios.ECHO
        termios.tcsetattr(slave, termios.TCSANOW, settings)
        observer = {"nonce": secrets.token_hex(16), "terminal": list(_tty_pin(slave)), "slave_path": os.ttyname(slave)}
        _tty_check(slave, observer)
        digest = prepare_readonly(head, remote, observer)["spec_sha256"]
        _control_guard(head, remote); require(_query_result(head).returncode == 113, "startup_control_state")
        _phase("controller_load", clock); consumption = _LoadInputs(head, remote, digest, observer); load_error = None
        try:
            _tty_check(slave, observer)
            require(_launch("load").returncode == 0, "startup_control"); loaded = True
            consumption.audit(); _tty_check(slave, observer)
        except BaseException as error: load_error = error; raise
        finally:
            try: consumption.close()
            except BaseException:
                if load_error is None: raise
        kernel = _query(head); _never_started(kernel); _control_guard(head, remote)
        read_fd, write_fd = os.pipe(); os.set_blocking(read_fd, False); ack_read, ack_write = os.pipe()
        process = subprocess.Popen([worker.PYTHON, "-B", "-m", MODULE, "control-readonly", "--head", head, "--remote", remote,
            "--spec-sha256", digest, "--observer", canonical_json(observer), "--control-fd", str(write_fd), "--ack-fd", str(ack_read),
            "--config-pins", canonical_json(_creator_pins(head, remote, digest, observer))],
            cwd=ROOT, env=worker._environment(), stdin=slave, stdout=slave, stderr=slave,
            close_fds=True, pass_fds=(write_fd, ack_read), start_new_session=True, shell=False)
        os.close(write_fd); write_fd = None; os.close(ack_read); ack_read = None
        acknowledged = terminal_acknowledged = False
        for unused in range(MAX_POLLS):
            raw, unused_eof = _private_read(master, raw); control, unused_eof = _private_read(read_fd, control)
            lines = control.splitlines(keepends=True)
            complete = [line for line in lines if line.endswith(b"\n")]
            if not acknowledged and not terminal_acknowledged and complete:
                first_value = json.loads(complete[0])
                require(complete[0] == canonical_json(first_value).encode() + b"\n", "startup_control")
                if type(first_value) is dict and first_value.get("schema") == "si-startup-prestart-barrier-v5":
                    require(first_value == {"schema": "si-startup-prestart-barrier-v5", "nonce": observer["nonce"],
                        "spec_sha256": digest, "control_pid": process.pid, "status": "runs0_before_initial_start"}, "startup_control")
                    kernel = _query(head); _never_started(kernel)
                    raw = _drain_to_eagain(master, raw)  # No initial start is possible before acknowledgment.
                    kernel = _query(head); _never_started(kernel); raw = b""; _tty_check(slave, observer)
                    require(os.write(ack_write, b"1") == 1, "startup_control"); acknowledged = True
                else:
                    receipt = _control_receipt(first_value, observer, digest, process.pid)
                    require(receipt["status"] == "refused" and receipt["target_pid"] is None, "startup_control")
                    kernel = _query(head); _never_started(kernel)
                    raw = _drain_to_eagain(master, raw)
                    require(os.write(ack_write, b"2") == 1, "startup_control")
                    os.close(ack_write); ack_write = None; terminal_acknowledged = True
            if acknowledged and not terminal_acknowledged and len(complete) == 2:
                value = json.loads(complete[1]); require(complete[1] == canonical_json(value).encode() + b"\n", "startup_control")
                receipt = _control_receipt(value, observer, digest, process.pid)
                kernel = _query(head)
                require(not kernel["running"] and kernel["active_count"] == 0 and kernel["runs"] in (0, 1), "startup_control_unknown")
                if receipt["target_pid"] is None: _never_started(kernel)
                else:
                    require(kernel["runs"] == 1 and kernel["exit"] is not None
                        and (kernel["pid"] is None or kernel["pid"] == receipt["target_pid"]), "startup_control_state")
                raw = _drain_to_eagain(master, raw)  # Target terminal; controller still owns the session.
                _tty_check(slave, observer)
                require(os.write(ack_write, b"2") == 1, "startup_control")
                os.close(ack_write); ack_write = None; terminal_acknowledged = True
            if process.poll() is not None:
                child_exit = process.wait(timeout=0); break
            clock.check(); time.sleep(1)
        if child_exit is None: raise StartupRefusal("REFUSED: startup_control_unknown")
        raw = _drain_to_eagain(master, raw); control = _drain_to_eagain(read_fd, control)
        require(receipt is not None and terminal_acknowledged and type(child_exit) is int, "startup_control")
        require(control.count(b"\n") == (2 if acknowledged else 1), "startup_control")
        kernel = _query(head)
        pid = receipt["target_pid"]
        if pid is None:
            _never_started(kernel); require(receipt["status"] == "refused" and child_exit != 0, "startup_control")
            result = {"status": "observer_unavailable", "authority": authority()}
        else:
            require(kernel["runs"] == 1 and not kernel["running"] and kernel["active_count"] == 0 and kernel["exit"] is not None
                and (kernel["pid"] is None or kernel["pid"] == pid), "startup_control_state")
            result = filter_observer(raw, observer, digest, pid)
        _control_guard(head, remote); _tty_check(slave, observer); clock.check()
        return {"status": "control_refused_before_initial_start" if pid is None else "terminal_observation_only",
            "target_started": pid is not None, "controller_exit": child_exit, "control_failure": receipt["failure"],
            "kernel": kernel, "observer": result, "authority": authority()}
    except BaseException as error:
        failure = error; failure_summary(error, head)
        if process is not None and child_exit is None or loaded and (kernel is None or kernel["running"]):
            state = {"master": master, "slave": slave, "read_fd": read_fd, "write_fd": write_fd,
                "ack_read": ack_read, "ack_write": ack_write, "process": process, "raw": raw, "control": control,
                "failure": failure, "transport_unavailable": False}
            master = slave = read_fd = write_fd = ack_read = ack_write = None
            try: _hold_private_controller(state)
            except BaseException: raise failure
        raise
    finally:
        first = failure
        for fd in (ack_write, ack_read, write_fd, read_fd, slave, master):
            if fd is not None:
                try: os.close(fd)
                except BaseException as error:
                    if first is None: first = error; failure_summary(error, head)
        if failure is None and first is not None: raise first


def main(argv=None):
    parser = argparse.ArgumentParser(description="One registered read-only background startup diagnostic")
    parser.add_argument("command", choices=("prepare-readonly", "run-readonly", "observe-readonly", "control-readonly"))
    parser.add_argument("--head"); parser.add_argument("--remote"); parser.add_argument("--spec-sha256"); parser.add_argument("--observer"); parser.add_argument("--control-fd", type=int); parser.add_argument("--ack-fd", type=int); parser.add_argument("--config-pins")
    args = parser.parse_args(argv); observer = None
    try:
        if args.command == "run-readonly":
            # Root CLI identity authenticates observation only before all subject
            # predicates, including registration, clock, config and live lane.
            observer = _Observer(json.loads(args.observer), args.spec_sha256)
            run_readonly(args.head, args.remote, args.spec_sha256, observer.config)
            observer.emit(None)
        elif args.command == "prepare-readonly": print(canonical_json(prepare_readonly(args.head, args.remote, json.loads(args.observer))))
        elif args.command == "observe-readonly": print(canonical_json(observe_readonly(args.head, args.remote)))
        else: control_readonly(args.head, args.remote, args.spec_sha256, json.loads(args.observer), args.control_fd, args.ack_fd, json.loads(args.config_pins))
        return 0
    except BaseException as error:
        detail = failure_summary(error, args.head)
        if args.command == "run-readonly":
            if observer is not None:
                try: observer.emit(detail)
                except BaseException: pass
        elif args.command != "control-readonly": print(canonical_json({"status": "refused", "failure": detail, "authority": authority()}))
        return 2


if __name__ == "__main__": raise SystemExit(main())
