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

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_count_native_supervisor as proof

worker = proof.worker
ROOT, PARENT = proof.ROOT, proof.PARENT
MODULE = "scripts.diagnose_short_interest_native_supervisor_startup"
DRIVER = "scripts/diagnose_short_interest_native_supervisor_startup.py"
BOOTSTRAP = "count-native-supervisor-startup-diagnostic-v1"
STATUS = "count-native-supervisor-startup-diagnostic-v1.jsonl"
LABEL = "com.openai.codex.short-interest-native-startup-diagnostic-v1"
POLICY_SHA256 = "0fbb3142c3269f6d38c41be469ebb1c2b50307ea1f36e56f09e6ac83899f02d8"
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
_ORIGINAL_GIT, _GIT_CODE = worker._git, worker._git.__code__
_ORIGINAL_GUARD, _ORIGINAL_CODE, _ORIGINAL_READ = worker._guard, proof._Code, proof._read_bootstrap
_STAGE, _USED = "registration", False
_STAGES = frozenset("registration config_auth status_bind live_guard current_code historical_config terminal_code original_audit cleanup named_audit status_publication".split())
_CODES = frozenset("startup_unregistered startup_arguments startup_config startup_status startup_code startup_stamp startup_deadline startup_clock startup_forbidden startup_git_budget startup_already_used startup_write startup_membership".split())
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
    return {"schema": "si-native-startup-diagnostic-policy-v1", "root": str(ROOT), "parent": str(PARENT),
        "bootstrap": BOOTSTRAP, "status": STATUS, "label": LABEL, "code_files": list(CODE_FILES),
        "target_head": TARGET_HEAD, "target_remote": REMOTE, "target_spec_sha256": TARGET_SPEC,
        "target_manifest": TARGET_MANIFEST, "maximum_config_bytes": MAX_CONFIG, "maximum_status_bytes": MAX_STATUS,
        "maximum_elapsed_acceptance_seconds": MAX_SECONDS, "maximum_Git_calls": MAX_GIT, "Git_per_call_seconds": 30,
        "deadline": "elapsed_acceptance_at_phase_and_terminal_boundaries_not_hard_wall_kill",
        "preauth": "externally_pinned_canonical_config_only_live_root_branch_HEAD_status_unknown_until_original_guard",
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


def _payload(head, remote, manifest, pin):
    return {"schema": "si-native-startup-bootstrap-v1", "policy_sha256": POLICY_SHA256,
        "runtime_head": head, "actual_remote": remote, "code_manifest": manifest,
        "target_head": TARGET_HEAD, "target_remote": REMOTE, "target_spec_sha256": TARGET_SPEC,
        "target_manifest": TARGET_MANIFEST, "status_name": STATUS, "status_original_identity": list(proof._status_pin(pin)),
        "config_role": "input_only_live_branch_HEAD_status_unknown_until_original_guard", "authority": authority()}


def build_launchd_plist(head, remote, digest):
    require(_hash(head, 40) and remote == REMOTE and _hash(digest), "startup_arguments")
    return {"Label": LABEL, "ProgramArguments": [worker.PYTHON, "-B", "-m", MODULE, "run-readonly", "--head", head, "--remote", remote, "--spec-sha256", digest],
        "WorkingDirectory": str(ROOT), "EnvironmentVariables": worker._environment(), "RunAtLoad": True,
        "KeepAlive": False, "Debug": True, "StandardOutPath": "/dev/null", "StandardErrorPath": "/dev/null"}


def _protected(info, maximum=MAX_CONFIG):
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
        and info.st_nlink == 1 and 0 < info.st_size <= maximum, "startup_config")
    return proof._stamp(info)


class _Inputs:
    """Two original canonical config inputs; full9 every read and held epoch."""
    def __init__(self, directory): self.directory, self.rows, self.fds = directory, [], []
    def read(self, name):
        require(name in ("launch.spec.json", "job.plist"), "startup_config"); self.directory.check()
        before = _protected(os.stat(name, dir_fd=self.directory.fd, follow_symlinks=False))
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory.fd); self.fds.append(fd)
        proof._same(proof._stamp(os.fstat(fd)), before); raw = os.read(fd, MAX_CONFIG + 1)
        require(len(raw) == before[6], "startup_config"); proof._same(proof._stamp(os.fstat(fd)), before)
        proof._same(proof._stamp(os.stat(name, dir_fd=self.directory.fd, follow_symlinks=False)), before)
        self.rows.append((name, fd, before, raw)); return raw
    def audit(self, named=False):
        self.directory.named() if named else self.directory.check()
        require(set(os.listdir(self.directory.path if named else self.directory.fd)) == {"launch.spec.json", "job.plist"}, "startup_membership")
        for name, fd, stamp, raw in self.rows:
            proof._same(proof._stamp((self.directory.path / name).lstat()), stamp)
            if not named:
                proof._same(proof._stamp(os.fstat(fd)), stamp); os.lseek(fd, 0, os.SEEK_SET)
                require(os.read(fd, len(raw) + 1) == raw, "startup_config"); proof._same(proof._stamp(os.fstat(fd)), stamp)
    def close(self): proof._drain(self.fds)


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
            raw = canonical_json({"schema": "si-native-startup-observation-v1", "status": "refused" if detail is not None else "readonly_predicates_passed_observation_only",
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


def prepare_readonly(head, remote):
    registered(); require(_hash(head, 40) and remote == REMOTE, "startup_arguments")
    with _fence(head): return _prepare_readonly(head, remote)


def _prepare_readonly(head, remote):
    clock = _Clock()
    directory = code = own = inputs = None; failure = None
    try:
        _phase("live_guard", clock); worker._guard(head, remote)
        _phase("current_code", clock); code = proof._Code(head, remote, clock); own = _OwnCode(head, remote, clock)
        require(code.manifest == TARGET_MANIFEST, "startup_code")
        manifest = {**code.manifest, DRIVER: own.digest}
        _phase("config_auth", clock); directory = proof._Directory(BOOTSTRAP, create=True); pin = _prepare_status(directory)
        raw = canonical_json(_payload(head, remote, manifest, pin)).encode(); digest = hash_bytes(raw)
        job_raw = plistlib.dumps(build_launchd_plist(head, remote, digest), sort_keys=True)
        _config_write(directory, "launch.spec.json", raw); _config_write(directory, "job.plist", job_raw)
        inputs = _Inputs(directory); require(inputs.read("launch.spec.json") == raw, "startup_config")
        require(inputs.read("job.plist") == job_raw, "startup_config")
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
    return {"status": "prepared_readonly_not_submitted", "spec_sha256": digest, "authority": authority()}


def run_readonly(head, remote, digest):
    global _USED
    registered(); require(not _USED and _hash(head, 40) and remote == REMOTE and _hash(digest), "startup_arguments"); _USED = True
    with _fence(head, readonly=True): return _run_readonly(head, remote, digest)


def _run_readonly(head, remote, digest):
    clock = _Clock(); directory = inputs = status = code = own = target = None; target_fds = []; failure = None
    try:
        # No Git or code command precedes these fixed original config inputs.
        _phase("config_auth", clock); directory = proof._Directory(BOOTSTRAP, create=False); inputs = _Inputs(directory)
        raw = inputs.read("launch.spec.json"); require(hash_bytes(raw) == digest, "startup_config")
        payload = json.loads(raw); require(type(payload) is dict, "startup_config")
        manifest = payload.get("code_manifest"); pin = payload.get("status_original_identity")
        require(type(manifest) is dict and set(manifest) == set(CODE_FILES) and all(_hash(v) for v in manifest.values())
            and {k: manifest[k] for k in proof.CODE_FILES} == TARGET_MANIFEST, "startup_config")
        require(raw == canonical_json(_payload(head, remote, manifest, pin)).encode(), "startup_config")
        require(inputs.read("job.plist") == plistlib.dumps(build_launchd_plist(head, remote, digest), sort_keys=True), "startup_config"); inputs.audit()
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


def main(argv=None):
    parser = argparse.ArgumentParser(description="One registered read-only background startup diagnostic")
    parser.add_argument("command", choices=("prepare-readonly", "run-readonly")); parser.add_argument("--head"); parser.add_argument("--remote"); parser.add_argument("--spec-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare-readonly": print(canonical_json(prepare_readonly(args.head, args.remote)))
        else: run_readonly(args.head, args.remote, args.spec_sha256)
        return 0
    except BaseException as error:
        if args.command == "prepare-readonly": print(canonical_json({"status": "refused", "failure": failure_summary(error, args.head), "authority": authority()}))
        return 2


if __name__ == "__main__": raise SystemExit(main())
