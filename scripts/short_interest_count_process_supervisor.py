"""One fixed source-free process-lifetime proof; capture remains refused.

An independently launched launchd job may own this supervisor and its child.
This module never submits a launchd job, imports a source/credential/operator
module or launches a capture. Preparing files is not proof of independence.
Actual launch, clean code registration and a finite observation are separate
Main decisions. A parent-observed OS-child exit is NOT a Codex exec-session
receipt, original count closure or checkpoint-loader v1 admission.
"""
import argparse
import errno
import json
import math
import os
from pathlib import Path
import plistlib
import re
import selectors
import stat
import subprocess
import sys
import time

from data.hashing import canonical_json, hash_bytes, hash_payload

ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest")
BRANCH, REF = "codex/strategy-short-interest", "refs/heads/codex/strategy-short-interest"
PYTHON = "/Users/sheltonchen/.venvs/trading_agent-py313/bin/python"
MODULE = "scripts.short_interest_count_process_supervisor"
NAMESPACE = ROOT / "artifacts/short_interest/count-process-supervisor-proof-v2"
LABEL = "com.openai.codex.short-interest-process-proof-v2"
PROOF_POLICY_SHA256 = "c83bb95c7912d20d12b88cf145ccb3ea35a22d66ba2cfb2539108361ffc8f217"
WORKER_SECONDS, MAXIMUM_SECONDS, MAXIMUM_LOG_BYTES = 2, 5, 4096
MAXIMUM_TERMINAL_BYTES = 2048
FILES = ("job.plist", "launch.spec.json", "result.json", "stdout.jsonl", "run.refused.json", "supervisor.jsonl")
CODE_FILES = ("data/__init__.py", "data/hashing.py", "scripts/short_interest_count_process_supervisor.py")
_CHILDREN, _WAITS, _EXITS, _HELD = {}, {}, {}, []
_FAILURES, _FIELDS, _REFUSALS = {}, {}, {}
_CLI_CHANNEL = None
_STAGE = "registration"
_STAGES = frozenset("registration lane_guard current_code namespace_open launch_spec channel_binding child_launch child_observation terminal_code result_publication stdout_audit context_cleanup post_context_audit reporter_cleanup public_summary terminal_cli preparation".split())
_STAMP_FIELDS = ("dev", "ino", "uid", "gid", "mode", "nlink", "size", "mtime_ns", "ctime_ns")
_ERRNOS = {getattr(errno, name): name for name in ("EACCES", "EPERM", "EIO", "EBADF", "ENOSPC", "EFBIG", "EROFS", "EMFILE", "ENFILE", "EINTR", "EAGAIN", "ENOENT", "EEXIST")}
_CODES = frozenset("""supervisor_proof_unregistered supervisor_source_mode_unregistered
supervisor_arguments_refused supervisor_lane_changed supervisor_Git_refused
supervisor_code_changed supervisor_namespace_changed supervisor_file_changed
supervisor_write_refused supervisor_spec_changed supervisor_child_changed
supervisor_stdout_refused supervisor_clock_refused supervisor_deadline
supervisor_result_unavailable supervisor_exit_factory_required supervisor_exit_changed
supervisor_channel_changed supervisor_terminal_refused""".split())


class ProcessSupervisorRefusal(ValueError): pass


def require(value, code):
    if not value: raise ProcessSupervisorRefusal("REFUSED: " + code)


def _stage(name):
    global _STAGE
    require(type(name) is str and name in _STAGES, "supervisor_terminal_refused")
    _STAGE = name


def _same_stamp(actual, original, code="supervisor_file_changed"):
    """Project names only from this exact original-comparison failure."""
    if actual != original:
        error = ProcessSupervisorRefusal("REFUSED: " + code)
        if (type(actual) is tuple and type(original) is tuple and len(actual) == len(original) == len(_STAMP_FIELDS)
                and all(type(v) is int for v in (*actual, *original))):
            _FIELDS[id(error)] = error, tuple(name for name, a, b in zip(_STAMP_FIELDS, actual, original) if a != b)
        raise error


def _remember(error):
    old = _FAILURES.get(id(error))
    if type(old) is tuple and old[0] is error:
        result = dict(old[1]); result["mismatching_fields"] = list(result["mismatching_fields"])
        return result
    code = None
    if type(error) is ProcessSupervisorRefusal:
        arguments = BaseException.args.__get__(error, BaseException)
        if type(arguments) is tuple and len(arguments) == 1 and type(arguments[0]) is str:
            code = next((v for v in _CODES if arguments[0] == "REFUSED: " + v), None)
    number = OSError.errno.__get__(error, OSError) if isinstance(error, OSError) else None
    number = number if type(number) is int else None
    fields = _FIELDS.get(id(error))
    detail = {"stage": _STAGE if _STAGE in _STAGES else "registration",
        "category": "local_contract_refusal" if code else "local_os_error" if number in _ERRNOS else "unknown_local_error",
        "contract_code": code, "errno_name": _ERRNOS.get(number),
        "mismatching_fields": fields[1] if type(fields) is tuple and fields[0] is error else ()}
    _FAILURES[id(error)] = error, tuple(detail.items())
    detail["mismatching_fields"] = list(detail["mismatching_fields"])
    return detail


def failure_summary(error): return _remember(error)


def _close_fd(fd, primary_error=None):
    """One close attempt; a secondary cleanup error cannot replace a primary."""
    try: os.close(fd)
    except BaseException:
        if primary_error is None: raise


def authority():
    return {"source_free_lifetime_proof_only": True, "provider_HTTP": 0, "credential_reads": 0,
        "new_capture_claims": 0, "new_STARTs": 0, "new_charged_bytes": 0, "source_admitted": False,
        "checkpoint_v1_receipt_issued": False, "source_dispatch_authority": False,
        "budget_release_authority": False, "ready_for_backtest": False, "qc_attempts": 0}


def policy():
    return {"schema": "si-count-process-supervisor-proof-policy-v2", "root": str(ROOT),
        "branch": BRANCH, "ref": REF, "module": MODULE, "python": PYTHON, "namespace": str(NAMESPACE),
        "files": list(FILES), "code_paths": list(CODE_FILES), "worker_seconds": WORKER_SECONDS,
        "maximum_observation_seconds": MAXIMUM_SECONDS, "maximum_stdout_bytes": MAXIMUM_LOG_BYTES,
        "launch": "one_launchd_owned_RunAtLoad_job_no_keepalive_interval_or_automatic_relaunch",
        "dispatch_claim": "original_exclusive_stdout_file_before_one_child_Popen_no_retry",
        "exit": "original_parent_child_handle_wait_only_never_PID_absence_or_JSON_completion",
        "unknown": "retain_original_process_handle_FDs_no_kill_restart_or_positive_exit_claim",
        "negative": "exclusive_dominating_run_refused_from_original_live_anchors_and_one_original_dup_pair_through_terminal_audits_no_reopen_after_cleanup",
        "final_membership": "exact_five_positive_roles_no_negative_entry_after_final_original_reporter_cleanup_before_witness",
        "cleanup": "drain_both_original_namespace_anchors_preserve_first_function_local_actual_exception_never_ambient_caller_exception_attempt_each_original_FD_close_once_clean_close_failure_refuses",
        "terminal_channel": "precreated0600_singlelink_zero_byte_original_full_stamp_in_spec_launchd_FD1_original_spec_identity_first6_and_size0_required_for_diagnostics_full_stamp_and_named_binding_required_for_child_or_success_one_fixed_bounded_line_Root_independent_postexit_revalidation",
        "maximum_terminal_bytes": MAXIMUM_TERMINAL_BYTES,
        "diagnostics": "fixed_entered_phase_category_allowlisted_contract_errno_and_exact_original_comparison_field_names_only_never_exception_formatting",
        "capture": "unregistered_and_unconditionally_refused", "authority": authority()}


def _registered_proof():
    require(type(PROOF_POLICY_SHA256) is str and re.fullmatch(r"[0-9a-f]{64}", PROOF_POLICY_SHA256)
        and hash_payload(policy()) == PROOF_POLICY_SHA256, "supervisor_proof_unregistered")


def _capture_refused():
    raise ProcessSupervisorRefusal("REFUSED: supervisor_source_mode_unregistered")


def _hash(value): return type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def _physical():
    require(ROOT.is_absolute() and ROOT.resolve() == ROOT and Path.cwd().resolve() == ROOT,
        "supervisor_lane_changed")


def _git(arguments):
    _physical()
    result = subprocess.run(["git", *arguments], cwd=ROOT, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=_environment(), check=False, timeout=30)
    _physical()
    require(result.returncode == 0 and type(result.stdout) is bytes and len(result.stdout) <= 262144,
        "supervisor_Git_refused")
    return result.stdout


def _snapshot(head):
    require(_hash(head), "supervisor_arguments_refused")
    require(_git(["rev-parse", "--show-toplevel"]) == (str(ROOT) + "\n").encode(), "supervisor_lane_changed")
    raw = _git(["status", "--porcelain=v2", "--branch", "--no-ahead-behind", "--untracked-files=all"])
    headers = {}
    for row in raw.decode("utf-8").splitlines():
        require(row.startswith("# "), "supervisor_lane_changed")
        key, separator, value = row[2:].partition(" ")
        require(separator and key in {"branch.oid", "branch.head", "branch.upstream", "branch.ab"}
            and key not in headers, "supervisor_lane_changed")
        headers[key] = value
    require(headers.get("branch.oid") == head and headers.get("branch.head") == BRANCH
        and headers.get("branch.upstream", "origin/" + BRANCH) == "origin/" + BRANCH
        and headers.get("branch.ab", "+? -?") in {"+? -?", "+0 -0"}, "supervisor_lane_changed")


def _guard(head, remote):
    require(_hash(head) and _hash(remote), "supervisor_arguments_refused")
    _snapshot(head)
    require(_git(["rev-parse", "refs/remotes/origin/" + BRANCH]) == (remote + "\n").encode(),
        "supervisor_lane_changed")
    require(_git(["ls-remote", "--refs", "origin", REF]) == (remote + "\t" + REF + "\n").encode(),
        "supervisor_lane_changed")
    _snapshot(head)


def _code_manifest(head, remote):
    result = {}
    for name in CODE_FILES:
        _guard(head, remote)
        committed = _git(["show", head + ":" + name])
        path = ROOT / name
        require(path.resolve() == path and not path.is_symlink(), "supervisor_code_changed")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        primary = None
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_size <= 262144, "supervisor_code_changed")
            raw = os.read(fd, 262145)
            require(_stamp(before) == _stamp(os.fstat(fd)) == _stamp(path.lstat())
                and raw == committed, "supervisor_code_changed")
        except BaseException as error:
            primary = error; raise
        finally: _close_fd(fd, primary)
        result[name] = hash_bytes(raw)
    _guard(head, remote)
    return result


def _environment():
    return {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode),
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory(info, *, owner_only):
    mode = stat.S_IMODE(info.st_mode)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
        and (mode == 0o700 if owner_only else not mode & 0o022), "supervisor_namespace_changed")
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, mode


class _Namespace:
    """Proof metadata only; never an existing count-image custody adapter."""
    def __init__(self, *, create):
        require(NAMESPACE.resolve() == NAMESPACE and NAMESPACE.parent.resolve() == NAMESPACE.parent,
            "supervisor_namespace_changed")
        self.parent = os.open(NAMESPACE.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.fd = None
        try:
            self.parent_pin = _directory(os.fstat(self.parent), owner_only=False)
            require(self.parent_pin == _directory(NAMESPACE.parent.lstat(), owner_only=False), "supervisor_namespace_changed")
            if create:
                os.mkdir(NAMESPACE.name, 0o700, dir_fd=self.parent)
                os.fsync(self.parent)
            self.fd = os.open(NAMESPACE.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.parent)
            self.pin = _directory(os.fstat(self.fd), owner_only=True)
            self.check()
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def check(self):
        require(NAMESPACE.resolve() == NAMESPACE and NAMESPACE.parent.resolve() == NAMESPACE.parent
            and _directory(os.fstat(self.parent), owner_only=False) == self.parent_pin
            == _directory(NAMESPACE.parent.lstat(), owner_only=False)
            and _directory(os.fstat(self.fd), owner_only=True) == self.pin
            == _directory(os.stat(NAMESPACE.name, dir_fd=self.parent, follow_symlinks=False), owner_only=True)
            == _directory(NAMESPACE.lstat(), owner_only=True), "supervisor_namespace_changed")
        require(set(os.listdir(self.fd)) <= set(FILES), "supervisor_namespace_changed")
    def close(self):
        first = None
        for name in ("fd", "parent"):
            fd = getattr(self, name, None)
            if fd is not None:
                try: os.close(fd)
                except BaseException as error:
                    if first is None: first = error
                finally: setattr(self, name, None)
        if first is not None: raise first
    def duplicate_original(self):
        """Two bounded original dup anchors; no path is opened or adopted."""
        self.check()
        other = object.__new__(_Namespace)
        other.parent = other.fd = None
        other.parent_pin, other.pin = self.parent_pin, self.pin
        try:
            other.parent = os.dup(self.parent); other.fd = os.dup(self.fd)
            other.check(); return other
        except BaseException:
            try: other.close()
            except BaseException: pass
            raise
    def create(self, name):
        self.check(); require(name in FILES, "supervisor_file_changed")
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            os.fchmod(fd, 0o600); self.validate(fd, name, 0)
        except BaseException as error:
            _close_fd(fd, error); raise
        return fd
    def validate(self, fd, name, size):
        self.check()
        left, right = os.fstat(fd), os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        require(_stamp(left) == _stamp(right) and stat.S_ISREG(left.st_mode) and left.st_uid == os.getuid()
            and stat.S_IMODE(left.st_mode) == 0o600 and left.st_nlink == 1 and left.st_size == size,
            "supervisor_file_changed")
    def write(self, name, raw):
        require(type(raw) is bytes and 0 < len(raw) <= MAXIMUM_LOG_BYTES, "supervisor_write_refused")
        fd = self.create(name)
        primary = None
        try:
            _write(fd, raw); self.validate(fd, name, len(raw)); os.fsync(fd); os.fsync(self.fd); os.fsync(self.parent)
            seal = _stamp(os.fstat(fd)); os.lseek(fd, 0, os.SEEK_SET)
            require(os.read(fd, len(raw) + 1) == raw, "supervisor_file_changed")
            self.validate(fd, name, len(raw)); require(_stamp(os.fstat(fd)) == seal, "supervisor_file_changed")
        except BaseException as error:
            primary = error; raise
        finally: _close_fd(fd, primary)
        self.check()
        require(_stamp(os.stat(name, dir_fd=self.fd, follow_symlinks=False)) == seal, "supervisor_file_changed")
    def read(self, name):
        self.check()
        require(type(name) is str and name in FILES, "supervisor_file_changed")
        named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        require(stat.S_ISREG(named.st_mode) and named.st_uid == os.getuid()
            and stat.S_IMODE(named.st_mode) == 0o600 and named.st_nlink == 1
            and type(named.st_size) is int and 0 < named.st_size <= MAXIMUM_LOG_BYTES,
            "supervisor_file_changed")
        before, size = _stamp(named), named.st_size
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        primary = None
        try:
            require(_stamp(os.fstat(fd)) == before, "supervisor_file_changed")
            self.validate(fd, name, size); raw = os.read(fd, size + 1)
            self.validate(fd, name, size); require(_stamp(os.fstat(fd)) == before and len(raw) == size,
                "supervisor_file_changed")
        except BaseException as error:
            primary = error; raise
        finally: _close_fd(fd, primary)
        self.check()
        require(_stamp(os.stat(name, dir_fd=self.fd, follow_symlinks=False)) == before,
            "supervisor_file_changed")
        return raw


def _write(fd, raw):
    offset = 0
    while offset < len(raw):
        count = os.write(fd, memoryview(raw)[offset:])
        require(type(count) is int and 0 < count <= len(raw) - offset, "supervisor_write_refused")
        offset += count


def _terminal_fd(): return 1


class _TerminalChannel:
    """Already-open launchd diagnostic FD, never a reopened namespace."""
    def __init__(self):
        self.fd, self.attempted = _terminal_fd(), False
        self.diagnostic_authorized, self.bound = False, False
        info = os.fstat(self.fd)
        self.original = _stamp(info)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1 and info.st_size == 0,
            "supervisor_channel_changed")

    def bind(self, ns, original):
        # The fixed spec has already been authenticated. Diagnostic-only
        # authority requires its ORIGINAL inode/protection, never a new FD's
        # self-captured stamp. Full original seals below still gate dispatch.
        require(self.original[:7] == original[:7], "supervisor_channel_changed")
        self.diagnostic_authorized = True
        _same_stamp(self.original, original, "supervisor_channel_changed")
        _same_stamp(_stamp(os.fstat(self.fd)), original, "supervisor_channel_changed")
        _same_stamp(_stamp(os.stat("supervisor.jsonl", dir_fd=ns.fd, follow_symlinks=False)),
            original, "supervisor_channel_changed")
        ns.validate(self.fd, "supervisor.jsonl", 0)
        self.bound = True

    def emit(self, status, *, failure=None, refusal_record="not_applicable", child_exit=None):
        require(not self.attempted, "supervisor_terminal_refused")
        self.attempted = True  # Partial output can never be retried/appended as another terminal line.
        require(self.diagnostic_authorized is True, "supervisor_channel_changed")
        require(type(status) is str and status in ("proof_supervisor_contexts_closed", "refused")
            and type(refusal_record) is str and refusal_record in ("not_applicable", "published", "unavailable", "original_anchors_closed")
            and (child_exit is None or type(child_exit) is int and -255 <= child_exit <= 255),
            "supervisor_terminal_refused")
        if failure is not None:
            require(type(failure) is dict and set(failure) == {"stage", "category", "contract_code", "errno_name", "mismatching_fields"}
                and type(failure["stage"]) is str and failure["stage"] in _STAGES
                and type(failure["category"]) is str and failure["category"] in ("local_contract_refusal", "local_os_error", "unknown_local_error")
                and (failure["contract_code"] is None or type(failure["contract_code"]) is str and failure["contract_code"] in _CODES)
                and (failure["errno_name"] is None or type(failure["errno_name"]) is str and failure["errno_name"] in _ERRNOS.values())
                and type(failure["mismatching_fields"]) is list
                and all(type(v) is str and v in _STAMP_FIELDS for v in failure["mismatching_fields"])
                and len(failure["mismatching_fields"]) <= len(_STAMP_FIELDS), "supervisor_terminal_refused")
        require((status == "refused") == (failure is not None), "supervisor_terminal_refused")
        require((status != "proof_supervisor_contexts_closed" or self.bound is True and child_exit == 0 and refusal_record == "not_applicable")
            and (status != "refused" or refusal_record != "not_applicable"), "supervisor_terminal_refused")
        payload = {"schema": "si-count-process-proof-terminal-v2", "status": status,
            "failure": failure, "refusal_record": refusal_record, "actual_child_exit": child_exit,
            "supervisor_process_exit_attested": False, "launcher_independence_verified": False,
            "authority": authority()}
        raw = canonical_json(payload).encode() + b"\n"
        require(0 < len(raw) <= MAXIMUM_TERMINAL_BYTES and raw.count(b"\n") == 1,
            "supervisor_terminal_refused")
        _same_stamp(_stamp(os.fstat(self.fd)), self.original, "supervisor_channel_changed")
        _write(self.fd, raw); os.fsync(self.fd)
        after = os.fstat(self.fd)
        require(_stamp(after)[:6] == self.original[:6] and stat.S_ISREG(after.st_mode)
            and after.st_size == len(raw), "supervisor_channel_changed")


def _channel_stamp(value):
    require(type(value) in (tuple, list) and len(value) == len(_STAMP_FIELDS)
        and all(type(v) is int and 0 <= v <= 2 ** 64 for v in value)
        and value[2] == os.getuid() and tuple(value[4:7]) == (0o600, 1, 0), "supervisor_channel_changed")
    return tuple(value)


def _spec(head, remote, manifest, channel_stamp):
    original = _channel_stamp(channel_stamp)
    return {"schema": "si-count-process-proof-launch-v2", "runtime_head": head, "actual_remote": remote,
        "proof_policy_sha256": PROOF_POLICY_SHA256, "code_manifest": manifest,
        "supervisor_stdout_initial_stamp": list(original),
        "worker_arguments": [PYTHON, "-B", "-m", MODULE, "proof-worker", "--head", head, "--remote", remote],
        "authority": authority()}


def build_launchd_plist(head, remote, spec_sha256):
    """Pure fixed job definition; no bootstrap, install or recurring monitor."""
    require(_hash(head) and _hash(remote) and type(spec_sha256) is str
        and re.fullmatch(r"[0-9a-f]{64}", spec_sha256), "supervisor_arguments_refused")
    return {"Label": LABEL, "ProgramArguments": [PYTHON, "-B", "-m", MODULE, "supervise-proof",
        "--head", head, "--remote", remote, "--spec-sha256", spec_sha256], "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": _environment(), "RunAtLoad": True, "KeepAlive": False,
        "StandardOutPath": str(NAMESPACE / "supervisor.jsonl"), "StandardErrorPath": "/dev/null"}


def prepare_proof(head, remote):
    _stage("preparation")
    _registered_proof(); _guard(head, remote); manifest = _code_manifest(head, remote)
    ns = _Namespace(create=True)
    primary = None
    try:
        fd = ns.create("supervisor.jsonl")
        channel_primary = None
        try:
            os.fsync(fd); os.fsync(ns.fd); os.fsync(ns.parent)
            ns.validate(fd, "supervisor.jsonl", 0); channel_stamp = _stamp(os.fstat(fd))
        except BaseException as error:
            channel_primary = error; raise
        finally: _close_fd(fd, channel_primary)
        _same_stamp(_stamp(os.stat("supervisor.jsonl", dir_fd=ns.fd, follow_symlinks=False)), channel_stamp)
        raw = canonical_json(_spec(head, remote, manifest, channel_stamp)).encode()
        spec_sha = hash_bytes(raw)
        ns.write("launch.spec.json", raw)
        ns.write("job.plist", plistlib.dumps(build_launchd_plist(head, remote, spec_sha), sort_keys=True))
        _guard(head, remote); ns.check()
        return {"schema": "si-count-process-proof-prepared-v1", "launch_spec_sha256": spec_sha,
            "job_label": LABEL, "job_submitted": False, "authority": authority()}
    except BaseException as error:
        primary = error; raise
    finally:
        try: ns.close()
        except BaseException:
            if primary is None: raise


def _worker_line(stage, pid, parent_pid):
    return {"schema": "si-count-process-proof-worker-v1", "stage": stage, "process_id": pid,
        "parent_process_id": parent_pid, "proof_policy_sha256": PROOF_POLICY_SHA256, "authority": authority()}


def proof_worker(head, remote):
    _registered_proof(); require(_hash(remote), "supervisor_arguments_refused"); _snapshot(head)
    print(canonical_json(_worker_line("entered", os.getpid(), os.getppid())), flush=True)
    time.sleep(WORKER_SECONDS)
    print(canonical_json(_worker_line("completed", os.getpid(), os.getppid())), flush=True)
    return 0


def _now():
    value = time.monotonic()
    require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 2 ** 53,
        "supervisor_clock_refused")
    return value


def _collect(process, ns, log_fd, began):
    pending = b""; output = b""; stages = ["entered", "completed"]
    selector = selectors.DefaultSelector()
    primary = None
    try:
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        eof = False
        while not eof:
            require(0 <= _now() - began <= MAXIMUM_SECONDS, "supervisor_deadline")
            for key, unused in selector.select(0.1):
                block = os.read(key.fd, 1024)
                if not block: eof = True; break
                pending += block
                require(len(pending) + len(output) <= MAXIMUM_LOG_BYTES, "supervisor_stdout_refused")
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    require(stages and len(line) <= 1024, "supervisor_stdout_refused")
                    expected = canonical_json(_worker_line(stages.pop(0), process.pid, os.getpid())).encode()
                    require(line == expected, "supervisor_stdout_refused")
                    _write(log_fd, line + b"\n"); output += line + b"\n"
                    ns.validate(log_fd, "stdout.jsonl", len(output)); os.fsync(log_fd)
        remaining = MAXIMUM_SECONDS - (_now() - began)
        require(remaining > 0, "supervisor_deadline")
        original = _CHILDREN.get(process)
        require(type(original) is tuple and original[0] is process and process not in _WAITS,
            "supervisor_child_changed")
        status = process.wait(timeout=remaining)
        require(type(status) is int and _CHILDREN.get(process) is original, "supervisor_child_changed")
        _WAITS[process] = original, status, object()
        require(type(status) is int and status == 0 and 0 <= _now() - began <= MAXIMUM_SECONDS,
            "supervisor_child_changed")
        require(not pending and not stages, "supervisor_stdout_refused")
        ns.validate(log_fd, "stdout.jsonl", len(output)); os.fsync(log_fd); os.fsync(ns.fd); os.fsync(ns.parent)
        seal = _stamp(os.fstat(log_fd))
        os.lseek(log_fd, 0, os.SEEK_SET)
        require(os.read(log_fd, MAXIMUM_LOG_BYTES + 1) == output and _stamp(os.fstat(log_fd)) == seal,
            "supervisor_file_changed")
        return status, hash_bytes(output), seal
    except BaseException as error:
        primary = error; raise
    finally:
        try: selector.close()
        except BaseException:
            if primary is None: raise


class ParentObservedProofExit:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise ProcessSupervisorRefusal("REFUSED: supervisor_exit_factory_required")
    def public_summary(self):
        original = _EXITS.get(self) if type(self) is ParentObservedProofExit else None
        require(type(original) is tuple and original is self._anchor is self._identity,
            "supervisor_exit_changed")
        return json.loads(original[2])


def _hold_unknown(process, ns, log_fd):
    _HELD.append((process, ns, log_fd))
    try:
        ns.write("result.json", canonical_json({"schema": "si-count-process-proof-unverified-v1",
            "status": "child_termination_unverified", "requires_process_hold": True,
            "child_process_id": process.pid, "actual_process_exit": None,
            "authority": authority()}).encode())
    except BaseException:
        pass  # Reporting failure cannot authorize discarding the original live handle.
    while True: time.sleep(30)  # No kill, retry, restart, source operation or invented terminal result.


def _known_exit(process):
    original = _WAITS.get(process) if process is not None else None
    return (original[1] if type(original) is tuple and len(original) == 3
        and original[0] is _CHILDREN.get(process) and type(original[1]) is int else None)


def _record_refusal(error, ns, process):
    detail = _remember(error)
    previous = _REFUSALS.get(id(error))
    if type(previous) is tuple and previous[0] is error: return previous[1]
    state = "original_anchors_closed"
    if ns is not None and ns.fd is not None and ns.parent is not None:
        state = "unavailable"
        try:
            ns.write("run.refused.json", canonical_json({
                "schema": "si-count-process-proof-refusal-v2", "status": "proof_supervisor_refused",
                "failure": detail, "actual_child_exit": _known_exit(process),
                "proof_policy_sha256": PROOF_POLICY_SHA256, "authority": authority()}).encode())
            state = "published"
        except BaseException:
            pass  # Retain the first actual failure, not a failed diagnostic-write replacement.
    _REFUSALS[id(error)] = error, state
    return state


def supervise_proof(head, remote, spec_sha256):
    _stage("registration")
    ns = reporter = log_fd = process = completed = None
    failure = None
    try:
        try:
            _registered_proof(); _stage("lane_guard"); _guard(head, remote)
            _stage("current_code"); manifest = _code_manifest(head, remote)
            _stage("namespace_open"); ns = _Namespace(create=False)
            reporter = ns.duplicate_original()
            _stage("launch_spec"); raw_spec = ns.read("launch.spec.json")
            require(type(spec_sha256) is str and hash_bytes(raw_spec) == spec_sha256, "supervisor_spec_changed")
            parsed = json.loads(raw_spec)
            require(type(parsed) is dict, "supervisor_spec_changed")
            original_channel = _channel_stamp(parsed.get("supervisor_stdout_initial_stamp"))
            wanted = canonical_json(_spec(head, remote, manifest, original_channel)).encode()
            require(raw_spec == wanted and set(os.listdir(ns.fd)) == {"launch.spec.json", "job.plist", "supervisor.jsonl"}
                and ns.read("job.plist") == plistlib.dumps(build_launchd_plist(head, remote, spec_sha256), sort_keys=True),
                "supervisor_spec_changed")
            _stage("channel_binding")
            channel = _CLI_CHANNEL if type(_CLI_CHANNEL) is _TerminalChannel else _TerminalChannel()
            channel.bind(ns, original_channel)
            log_fd = ns.create("stdout.jsonl")  # Exclusive irreversible one-launch claim.
            os.fsync(log_fd); os.fsync(ns.fd); os.fsync(ns.parent)
            _stage("child_launch"); _guard(head, remote); began = _now()
            process = subprocess.Popen(_spec(head, remote, manifest, original_channel)["worker_arguments"], cwd=ROOT,
                env=_environment(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                shell=False, close_fds=True, start_new_session=True)
            require(type(process.pid) is int and process.pid > 0 and process.stdout is not None, "supervisor_child_changed")
            _CHILDREN[process] = process, spec_sha256, manifest, object()
            _stage("child_observation"); status, stdout_sha, log_seal = _collect(process, ns, log_fd, began)
            _stage("terminal_code"); _guard(head, remote)
            require(_code_manifest(head, remote) == manifest and _CHILDREN.get(process)[0] is process,
                "supervisor_code_changed")
            result = {"schema": "si-parent-observed-proof-process-exit-v2", "status": "proof_child_exit_observed",
                "parent_process_id": os.getpid(), "child_process_id": process.pid, "actual_process_exit": status,
                "supervisor_parent_process_id": os.getppid(),
                "runtime_head": head, "actual_remote": remote, "launch_spec_sha256": spec_sha256,
                "stdout_sha256": stdout_sha, "launcher_independence_verified": False,
                "supervisor_process_exit_attested": False, "known_Codex_exec_session": None, "authority": authority()}
            _stage("result_publication"); raw = canonical_json(result).encode(); ns.write("result.json", raw)
            _stage("stdout_audit"); ns.validate(log_fd, "stdout.jsonl", log_seal[6]); os.lseek(log_fd, 0, os.SEEK_SET)
            _same_stamp(_stamp(os.fstat(log_fd)), log_seal)
            require(hash_bytes(os.read(log_fd, MAXIMUM_LOG_BYTES + 1)) == stdout_sha, "supervisor_file_changed")
            _same_stamp(_stamp(os.fstat(log_fd)), log_seal)
            result_seal = _stamp(os.stat("result.json", dir_fd=ns.fd, follow_symlinks=False))
            completed = process, _CHILDREN[process], raw.decode(), object()
        except BaseException as error:
            failure = error; _record_refusal(error, reporter if reporter is not None else ns, process)
            if process is not None and _known_exit(process) is None:
                if type(_CLI_CHANNEL) is _TerminalChannel:
                    try: _CLI_CHANNEL.emit("refused", failure=_remember(error), refusal_record=_REFUSALS[id(error)][1])
                    except BaseException: pass
                _hold_unknown(process, ns, log_fd)
        finally:
            if not any(item[0] is process and item[1] is ns for item in _HELD):
                _stage("context_cleanup")
                close_actions = []
                if process is not None and process.stdout is not None: close_actions.append(process.stdout.close)
                if log_fd is not None: close_actions.append(lambda: os.close(log_fd))
                if ns is not None: close_actions.append(ns.close)
                for close in close_actions:
                    try: close()
                    except BaseException as error:
                        if failure is None:
                            failure = error; _record_refusal(error, reporter if reporter is not None else ns, process)
                if failure is not None: raise failure
        _stage("post_context_audit")
        require(completed is not None and _directory(NAMESPACE.parent.lstat(), owner_only=False) == ns.parent_pin
            and _directory(NAMESPACE.lstat(), owner_only=True) == ns.pin
            and NAMESPACE.resolve() == NAMESPACE, "supervisor_file_changed")
        _same_stamp(_stamp((NAMESPACE / "stdout.jsonl").lstat()), log_seal)
        _same_stamp(_stamp((NAMESPACE / "result.json").lstat()), result_seal)
        require(set(os.listdir(NAMESPACE)) == {"launch.spec.json", "job.plist", "supervisor.jsonl", "stdout.jsonl", "result.json"},
            "supervisor_file_changed")
        reporter.check(); _stage("reporter_cleanup"); reporter.close(); reporter = None
        # Final reporter cleanup cannot mint a witness before these original
        # named seals are checked again. No reporter is reopened on failure.
        _stage("post_context_audit")
        require(_directory(NAMESPACE.parent.lstat(), owner_only=False) == ns.parent_pin
            and _directory(NAMESPACE.lstat(), owner_only=True) == ns.pin
            and NAMESPACE.resolve() == NAMESPACE, "supervisor_file_changed")
        _same_stamp(_stamp((NAMESPACE / "stdout.jsonl").lstat()), log_seal)
        _same_stamp(_stamp((NAMESPACE / "result.json").lstat()), result_seal)
        require(set(os.listdir(NAMESPACE)) == {"launch.spec.json", "job.plist", "supervisor.jsonl", "stdout.jsonl", "result.json"},
            "supervisor_file_changed")
        witness = object.__new__(ParentObservedProofExit)
        witness._anchor = witness._identity = completed; _EXITS[witness] = completed
        return witness
    except BaseException as error:
        if failure is None: failure = error
        _record_refusal(error, reporter if reporter is not None else ns, process)
        raise
    finally:
        if reporter is not None:
            try: reporter.close()
            except BaseException as error:
                if failure is None:
                    _remember(error)
                    raise


def main(argv=None):
    global _CLI_CHANNEL
    parser = argparse.ArgumentParser(description="Registered one-shot source-free process-lifetime proof")
    parser.add_argument("mode", choices=("prepare-proof", "supervise-proof", "proof-worker", "capture"))
    parser.add_argument("--head"); parser.add_argument("--remote"); parser.add_argument("--spec-sha256")
    args = parser.parse_args(argv)
    channel = None
    try:
        _stage("registration")
        if args.mode == "capture": _capture_refused()
        if args.mode == "prepare-proof":
            result = prepare_proof(args.head, args.remote)
            print(canonical_json(result)); return 0
        if args.mode == "proof-worker": return proof_worker(args.head, args.remote)
        _stage("channel_binding"); channel = _TerminalChannel(); _CLI_CHANNEL = channel
        witness = supervise_proof(args.head, args.remote, args.spec_sha256)
        _stage("public_summary")
        result = witness.public_summary()
        _stage("terminal_cli")
        channel.emit("proof_supervisor_contexts_closed", child_exit=result["actual_process_exit"])
        return 0
    except BaseException as error:
        detail = _remember(error)
        if channel is not None:
            state = _REFUSALS.get(id(error))
            try:
                channel.emit("refused", failure=detail,
                    refusal_record=state[1] if type(state) is tuple and state[0] is error else "original_anchors_closed")
            except BaseException: pass  # Partial output is never retried or replaced.
        elif args.mode != "supervise-proof":
            print(canonical_json({"status": "refused", "failure": detail, "authority": authority()}))
        return 2
    finally:
        _CLI_CHANNEL = None


if __name__ == "__main__":
    raise SystemExit(main())
