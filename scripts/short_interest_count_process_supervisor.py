"""One fixed source-free process-lifetime proof; capture remains refused.

An independently launched launchd job may own this supervisor and its child.
This module never submits a launchd job, imports a source/credential/operator
module or launches a capture. Preparing files is not proof of independence.
Actual launch, clean code registration and a finite observation are separate
Main decisions. A parent-observed OS-child exit is NOT a Codex exec-session
receipt, original count closure or checkpoint-loader v1 admission.
"""
import argparse
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
NAMESPACE = ROOT / "artifacts/short_interest/count-process-supervisor-proof-v1"
LABEL = "com.openai.codex.short-interest-process-proof-v1"
PROOF_POLICY_SHA256 = "8071caa437d7d07dfbf5c8f70c6f9577ddc03cef03aa5e98d6bc8e4104b370a9"
WORKER_SECONDS, MAXIMUM_SECONDS, MAXIMUM_LOG_BYTES = 2, 5, 4096
FILES = ("job.plist", "launch.spec.json", "result.json", "stdout.jsonl")
CODE_FILES = ("data/__init__.py", "data/hashing.py", "scripts/short_interest_count_process_supervisor.py")
_CHILDREN, _WAITS, _EXITS, _HELD = {}, {}, {}, []
_CODES = frozenset("""supervisor_proof_unregistered supervisor_source_mode_unregistered
supervisor_arguments_refused supervisor_lane_changed supervisor_Git_refused
supervisor_code_changed supervisor_namespace_changed supervisor_file_changed
supervisor_write_refused supervisor_spec_changed supervisor_child_changed
supervisor_stdout_refused supervisor_clock_refused supervisor_deadline
supervisor_result_unavailable supervisor_exit_factory_required supervisor_exit_changed""".split())


class ProcessSupervisorRefusal(ValueError): pass


def require(value, code):
    if not value: raise ProcessSupervisorRefusal("REFUSED: " + code)


def authority():
    return {"source_free_lifetime_proof_only": True, "provider_HTTP": 0, "credential_reads": 0,
        "new_capture_claims": 0, "new_STARTs": 0, "new_charged_bytes": 0, "source_admitted": False,
        "checkpoint_v1_receipt_issued": False, "source_dispatch_authority": False,
        "budget_release_authority": False, "ready_for_backtest": False, "qc_attempts": 0}


def policy():
    return {"schema": "si-count-process-supervisor-proof-policy-v1", "root": str(ROOT),
        "branch": BRANCH, "ref": REF, "module": MODULE, "python": PYTHON, "namespace": str(NAMESPACE),
        "files": list(FILES), "code_paths": list(CODE_FILES), "worker_seconds": WORKER_SECONDS,
        "maximum_observation_seconds": MAXIMUM_SECONDS, "maximum_stdout_bytes": MAXIMUM_LOG_BYTES,
        "launch": "one_launchd_owned_RunAtLoad_job_no_keepalive_interval_or_automatic_relaunch",
        "dispatch_claim": "original_exclusive_stdout_file_before_one_child_Popen_no_retry",
        "exit": "original_parent_child_handle_wait_only_never_PID_absence_or_JSON_completion",
        "unknown": "retain_original_process_handle_FDs_no_kill_restart_or_positive_exit_claim",
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
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_size <= 262144, "supervisor_code_changed")
            raw = os.read(fd, 262145)
            require(_stamp(before) == _stamp(os.fstat(fd)) == _stamp(path.lstat())
                and raw == committed, "supervisor_code_changed")
        finally: os.close(fd)
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
            self.close(); raise
    def check(self):
        require(NAMESPACE.resolve() == NAMESPACE and NAMESPACE.parent.resolve() == NAMESPACE.parent
            and _directory(os.fstat(self.parent), owner_only=False) == self.parent_pin
            == _directory(NAMESPACE.parent.lstat(), owner_only=False)
            and _directory(os.fstat(self.fd), owner_only=True) == self.pin
            == _directory(os.stat(NAMESPACE.name, dir_fd=self.parent, follow_symlinks=False), owner_only=True)
            == _directory(NAMESPACE.lstat(), owner_only=True), "supervisor_namespace_changed")
        require(set(os.listdir(self.fd)) <= set(FILES), "supervisor_namespace_changed")
    def close(self):
        failures = []
        for name in ("fd", "parent"):
            fd = getattr(self, name, None)
            if fd is not None:
                try: os.close(fd)
                except OSError: failures.append(True)
                finally: setattr(self, name, None)
        require(not failures, "supervisor_file_changed")
    def create(self, name):
        self.check(); require(name in FILES, "supervisor_file_changed")
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            os.fchmod(fd, 0o600); self.validate(fd, name, 0)
        except BaseException:
            os.close(fd); raise
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
        try:
            _write(fd, raw); self.validate(fd, name, len(raw)); os.fsync(fd); os.fsync(self.fd); os.fsync(self.parent)
            seal = _stamp(os.fstat(fd)); os.lseek(fd, 0, os.SEEK_SET)
            require(os.read(fd, len(raw) + 1) == raw, "supervisor_file_changed")
            self.validate(fd, name, len(raw)); require(_stamp(os.fstat(fd)) == seal, "supervisor_file_changed")
        finally: os.close(fd)
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
        try:
            require(_stamp(os.fstat(fd)) == before, "supervisor_file_changed")
            self.validate(fd, name, size); raw = os.read(fd, size + 1)
            self.validate(fd, name, size); require(_stamp(os.fstat(fd)) == before and len(raw) == size,
                "supervisor_file_changed")
        finally: os.close(fd)
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


def _spec(head, remote, manifest):
    return {"schema": "si-count-process-proof-launch-v1", "runtime_head": head, "actual_remote": remote,
        "proof_policy_sha256": PROOF_POLICY_SHA256, "code_manifest": manifest,
        "worker_arguments": [PYTHON, "-B", "-m", MODULE, "proof-worker", "--head", head, "--remote", remote],
        "authority": authority()}


def build_launchd_plist(head, remote, spec_sha256):
    """Pure fixed job definition; no bootstrap, install or recurring monitor."""
    require(_hash(head) and _hash(remote) and type(spec_sha256) is str
        and re.fullmatch(r"[0-9a-f]{64}", spec_sha256), "supervisor_arguments_refused")
    return {"Label": LABEL, "ProgramArguments": [PYTHON, "-B", "-m", MODULE, "supervise-proof",
        "--head", head, "--remote", remote, "--spec-sha256", spec_sha256], "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": _environment(), "RunAtLoad": True, "KeepAlive": False,
        "StandardOutPath": "/dev/null", "StandardErrorPath": "/dev/null"}


def prepare_proof(head, remote):
    _registered_proof(); _guard(head, remote); manifest = _code_manifest(head, remote)
    raw = canonical_json(_spec(head, remote, manifest)).encode()
    spec_sha = hash_bytes(raw); ns = _Namespace(create=True)
    try:
        ns.write("launch.spec.json", raw)
        ns.write("job.plist", plistlib.dumps(build_launchd_plist(head, remote, spec_sha), sort_keys=True))
        _guard(head, remote); ns.check()
        return {"schema": "si-count-process-proof-prepared-v1", "launch_spec_sha256": spec_sha,
            "job_label": LABEL, "job_submitted": False, "authority": authority()}
    finally: ns.close()


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
    finally: selector.close()


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


def supervise_proof(head, remote, spec_sha256):
    _registered_proof(); _guard(head, remote); manifest = _code_manifest(head, remote)
    wanted = canonical_json(_spec(head, remote, manifest)).encode()
    require(type(spec_sha256) is str and hash_bytes(wanted) == spec_sha256, "supervisor_spec_changed")
    ns = _Namespace(create=False); log_fd = process = completed = None
    try:
        require(ns.read("launch.spec.json") == wanted and set(os.listdir(ns.fd)) == {"launch.spec.json", "job.plist"}
            and ns.read("job.plist") == plistlib.dumps(build_launchd_plist(head, remote, spec_sha256), sort_keys=True),
            "supervisor_spec_changed")
        log_fd = ns.create("stdout.jsonl")  # The irreversible one-launch claim, before Popen.
        os.fsync(log_fd); os.fsync(ns.fd); os.fsync(ns.parent)
        _guard(head, remote); began = _now()
        process = subprocess.Popen(_spec(head, remote, manifest)["worker_arguments"], cwd=ROOT,
            env=_environment(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            shell=False, close_fds=True, start_new_session=True)
        require(type(process.pid) is int and process.pid > 0 and process.stdout is not None,
            "supervisor_child_changed")
        _CHILDREN[process] = process, spec_sha256, manifest, object()
        status, stdout_sha, log_seal = _collect(process, ns, log_fd, began)
        _guard(head, remote)
        require(_code_manifest(head, remote) == manifest and _CHILDREN.get(process)[0] is process,
            "supervisor_code_changed")
        result = {"schema": "si-parent-observed-proof-process-exit-v1", "status": "proof_child_exit_observed",
            "parent_process_id": os.getpid(), "child_process_id": process.pid, "actual_process_exit": status,
            "supervisor_parent_process_id": os.getppid(),
            "runtime_head": head, "actual_remote": remote, "launch_spec_sha256": spec_sha256,
            "stdout_sha256": stdout_sha, "launcher_independence_verified": False,
            "supervisor_process_exit_attested": False, "known_Codex_exec_session": None, "authority": authority()}
        raw = canonical_json(result).encode(); ns.write("result.json", raw)
        ns.validate(log_fd, "stdout.jsonl", log_seal[6]); os.lseek(log_fd, 0, os.SEEK_SET)
        require(_stamp(os.fstat(log_fd)) == log_seal
            and hash_bytes(os.read(log_fd, MAXIMUM_LOG_BYTES + 1)) == stdout_sha
            and _stamp(os.fstat(log_fd)) == log_seal, "supervisor_file_changed")
        result_seal = _stamp(os.stat("result.json", dir_fd=ns.fd, follow_symlinks=False))
        completed = process, _CHILDREN[process], raw.decode(), object()
    except BaseException:
        if process is not None:
            waited = _WAITS.get(process)
            if (type(waited) is tuple and len(waited) == 3 and waited[0] is _CHILDREN.get(process)
                    and type(waited[1]) is int):
                try:
                    ns.write("result.json", canonical_json({"schema": "si-count-process-proof-rejected-v1",
                        "status": "proof_rejected_after_known_child_exit", "actual_process_exit": waited[1],
                        "child_process_id": process.pid, "authority": authority()}).encode())
                except BaseException: pass
            else: _hold_unknown(process, ns, log_fd)
        raise
    finally:
        if not any(item[0] is process and item[1] is ns for item in _HELD):
            failures = []
            for close in ((process.stdout.close,) if process is not None and process.stdout is not None else ()):
                try: close()
                except BaseException: failures.append(True)
            if log_fd is not None:
                try: os.close(log_fd)
                except BaseException: failures.append(True)
            try: ns.close()
            except BaseException: failures.append(True)
            require(not failures, "supervisor_file_changed")
    require(completed is not None and _directory(NAMESPACE.parent.lstat(), owner_only=False) == ns.parent_pin
        and _directory(NAMESPACE.lstat(), owner_only=True) == ns.pin
        and NAMESPACE.resolve() == NAMESPACE and _stamp((NAMESPACE / "stdout.jsonl").lstat()) == log_seal
        and _stamp((NAMESPACE / "result.json").lstat()) == result_seal, "supervisor_file_changed")
    witness = object.__new__(ParentObservedProofExit)
    witness._anchor = witness._identity = completed; _EXITS[witness] = completed
    return witness


def main(argv=None):
    parser = argparse.ArgumentParser(description="Registered one-shot source-free process-lifetime proof")
    parser.add_argument("mode", choices=("prepare-proof", "supervise-proof", "proof-worker", "capture"))
    parser.add_argument("--head"); parser.add_argument("--remote"); parser.add_argument("--spec-sha256")
    args = parser.parse_args(argv)
    try:
        if args.mode == "capture": _capture_refused()
        if args.mode == "prepare-proof": result = prepare_proof(args.head, args.remote)
        elif args.mode == "supervise-proof": result = supervise_proof(args.head, args.remote, args.spec_sha256).public_summary()
        else: return proof_worker(args.head, args.remote)
        print(canonical_json(result)); return 0
    except BaseException as error:
        arguments = BaseException.args.__get__(error, BaseException) if type(error) is ProcessSupervisorRefusal else ()
        code = next((value for value in _CODES if type(arguments) is tuple and len(arguments) == 1
            and type(arguments[0]) is str and arguments[0] == "REFUSED: " + value), None)
        print(canonical_json({"status": "refused", "contract_code": code, "authority": authority()})); return 2


if __name__ == "__main__":
    raise SystemExit(main())
