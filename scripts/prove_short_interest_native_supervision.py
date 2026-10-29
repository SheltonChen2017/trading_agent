"""Fresh typed source-free native-supervision proof; no V1 result admission.

PTY bytes are observation only. A Root-closed in-memory result requires an
actual kernel0 receipt and independently authenticated original APFS controls.
A durable Main receipt/SourceAUTH bridge is deliberately unavailable here.
"""
import argparse
import base64
from contextlib import contextmanager
import errno
import json
import math
import os
from pathlib import Path
import plistlib
import re
import secrets
import socket
import stat
import subprocess
import time
import zlib

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_count_native_supervisor as old
from scripts import diagnose_short_interest_native_supervisor_startup as startup

worker, native = old.worker, old.native
ROOT, PARENT = old.ROOT, old.PARENT
MODULE = "scripts.prove_short_interest_native_supervision"
DRIVER = "scripts/prove_short_interest_native_supervision.py"
BOOTSTRAP = "si-native-supervision-v2-v1-bootstrap"
DOMAIN = "si-native-supervision-v2-v1-domain"
LABEL = "com.openai.codex.short-interest-native-supervision-v2-v1"
POLICY_SHA256 = "8e3ba4e2e3efb8d9724bc89485ab6017f830d22a0053455dd331b705698e0eb5"
CODE_FILES = (*old.CODE_FILES, startup.DRIVER, DRIVER)
MAXIMUM_SECONDS, COMMAND_SECONDS, VIRTUAL_BYTES = 300, 120, 8 * 1024 ** 3
MAXIMUM_NATIVE_BYTES, MAXIMUM_CONTROL_BYTES, MAX_CONFIG, MAX_WIRE = 4194304, 4096, 4096, 1024
RAW_ROLES = ("native.before.plist", "native.create.plist", "native.attach.plist", "native.initial.plist", "native.terminal.plist")
PRIVATE_ROLES = ()
INVENTORY_ROLE, MARKER_ROLE = "metadata.inventory.private.json", "run.completed.provisional.json"
CONTROL_ROLES = ("run.started.json", "stdout.jsonl", "child.exit.provisional.json", MARKER_ROLE, "run.refused.json")
ROLES = RAW_ROLES + CONTROL_ROLES + (INVENTORY_ROLE,)
POSITIVE_ROLES = set(ROLES) - {"run.refused.json"}
LAUNCHCTL = "/bin/launchctl"
_COLLECT, _COLLECT_CODE = worker._collect, worker._collect.__code__
_USED = False
_STAGE, _COMPONENT = "registration", "operation"
_STAGES = frozenset("registration startup_import bootstrap current_code native_creation output_creation child_launch child_observation terminal_code terminal_native inventory_publication original_audit cleanup named_audit root_load root_observation root_verification root_cleanup".split())
_COMPONENTS = old._COMPONENTS | frozenset(("operation", "main_directory", "root_receipt"))
_CODES = old._CODES | startup._CODES | frozenset("supervision_unregistered supervision_arguments supervision_code supervision_factory supervision_changed supervision_wait supervision_kernel supervision_negative supervision_original supervision_unknown supervision_marker supervision_source_refused".split())
_ERRNOS = {**old._ERRNOS, **startup._ERRNOS}
_PRODUCERS, _CLOSED, _PREPARED, _HELD, _FAILURES, _ADVISORIES, _KERNEL_ORIGINS = {}, {}, {}, [], {}, {}, {}
_stamp, _same, _dir, _drain, _write, _close = old._stamp, old._same, old._dir, old._drain, old._write, old._close


class SupervisionRefusal(ValueError): pass


def require(value, code):
    if not value: raise SupervisionRefusal("REFUSED: " + code)


def _phase(value):
    global _STAGE
    require(value in _STAGES, "supervision_arguments"); _STAGE = value


def _component(value, ordinal=0):
    global _COMPONENT
    require(value in _COMPONENTS and type(ordinal) is int and 0 <= ordinal <= 32, "supervision_arguments"); _COMPONENT = value


def authority():
    return {"source_free_native_supervision_only": True, "source_admitted": False, "source_dispatch_authority": False,
        "budget_release_authority": False, "old_V1_admitted": False, "durable_Main_receipt": False,
        "ready_for_backtest": False, "provider_HTTP": 0, "credential_reads": 0, "source_STARTs": 0,
        "source_bytes": 0, "new_source_claims": 0, "QC_or_Safari": False, "qc_attempts": 0}


def policy():
    return {"schema": "si-native-supervision-v2-policy-v1", "root": str(ROOT), "bootstrap": BOOTSTRAP,
        "domain": DOMAIN, "label": LABEL, "code_files": list(CODE_FILES), "roles": list(ROLES),
        "virtual_bytes": VIRTUAL_BYTES, "maximum_seconds": MAXIMUM_SECONDS, "native_command_seconds": COMMAND_SECONDS,
        "config_bytes": MAX_CONFIG, "control_bytes": MAXIMUM_CONTROL_BYTES, "native_bytes": MAXIMUM_NATIVE_BYTES, "inventory_bytes": MAXIMUM_NATIVE_BYTES,
        "worker_log_bytes": worker.MAXIMUM_LOG_BYTES, "private_buffer_bytes": 65536, "private_buffer_files": [], "wire_bytes": MAX_WIRE,
        "volume": "fresh_original_creator_APFS_local_nobrowse_owner_writable_global_unique_no_shadow_no_retry_detach_remount_adoption",
        "evidence": "original_OEXCL0600_singlelink_full9_and_readback_all_contexts_and_postclose_named_audits_no_negative",
        "worker": "unchanged_genuine_two_second_two_line_proof_worker_collect_original_wait0_within5seconds",
        "kernel": "Root_exact_loaded_job_one_initial_kickstart_p_no_k_pending_never_exited_never_zero_final_runs1_inactive_noPID_exit0",
        "result": "own_exact_factory_provenance_kernel0_childwait0_original_marker_inventory_native_and_code_conjunction_no_V1_cast",
        "Root_context_provenance": "exact_closed_original_reader_code_config_load_transaction_objects_immutable_private_snapshot_and_issuer_retained_by_RootReceipt_no_caller_flags_or_JSON",
        "kernel_provenance": "exact_issued_parsed_object_original_typed_CompletedProcess_exact_queryargv_returncode_boundedstdout_SHA_frozen_snapshot_issuer_retained_and_revalidated_by_Closed_getter_no_JSON_flags",
        "unknown": "hold_all_original_contexts_process_buffers_and_trace_indefinitely_while_alive_no_kill_restart_positive_recovery_start_attempt_latched_and_kernel_cleared_before_dispatch",
        "Root_final_native": "complete_original_native_and_control_sweep_after_last_callbacks_then_strict_nofollow_original_pin_verification_reads_postclose_no_rebaseline_new_hdiutil_or_creator_adoption",
        "Main_receipt": "fresh_parent_seeded_empty_pinned_APFS_main_directory_only_durable_writing_unavailable_SourceAUTH_blocked",
        "wrapper_body_sha256": hash_bytes(_wrapper_body().encode()), "wrapper_inline_sha256": hash_bytes(_wrapper().encode()),
        "authority": authority()}


def registered():
    require(type(POLICY_SHA256) is str and re.fullmatch(r"[0-9a-f]{64}", POLICY_SHA256)
        and hash_payload(policy()) == POLICY_SHA256 and _COLLECT is worker._collect and _COLLECT_CODE is worker._collect.__code__, "supervision_unregistered")
    require(CODE_FILES == (*old.CODE_FILES, startup.DRIVER, DRIVER), "supervision_code")


def failure_summary(error):
    previous = _FAILURES.get(id(error))
    if previous is not None and previous[0] is error: return json.loads(previous[1])
    code = None
    if type(error) is SupervisionRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((v for v in _CODES if args[0] == "REFUSED: " + v), None)
    upstream = old.failure_summary(error)
    number = OSError.errno.__get__(error, OSError) if isinstance(error, OSError) else None
    number = number if type(number) is int else None
    detail = {"stage": _STAGE, "component": _COMPONENT, "contract_code": code,
        "upstream_contract_code": upstream["contract_code"] or upstream["upstream_contract_code"],
        "errno_name": _ERRNOS.get(number) or upstream["errno_name"], "mismatching_fields": upstream["mismatching_fields"]}
    _FAILURES[id(error)] = error, canonical_json(detail); return detail


class _Clock:
    def __init__(self): self.clock = time.monotonic; self.begin = self.last = self.clock(); self.check()
    def check(self):
        now = self.clock(); require(type(now) in (int, float) and math.isfinite(now) and 0 <= self.begin <= self.last <= now, "native_proof_clock")
        require(now - self.begin <= MAXIMUM_SECONDS, "native_proof_deadline"); self.last = now; return MAXIMUM_SECONDS - (now - self.begin)


def _guard(head, remote): return worker._guard(head, remote)
def _git(arguments): return worker._git(arguments)
def _platform(): return native._platform()
def _native_statfs(fd): return native._native_statfs(fd)
def _device_node(device, mount_dev): return native._node_pin(device, mount_dev)
def _native_command(arguments, timeout):
    return subprocess.run(arguments, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=False, timeout=timeout, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
def _launch_worker(head, remote):
    return subprocess.Popen([worker.PYTHON, "-B", "-m", worker.MODULE, "proof-worker", "--head", head, "--remote", remote],
        cwd=ROOT, env=worker._environment(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        shell=False, close_fds=True, start_new_session=True)
def _new_domain(clock): return _DomainVolume(clock)


@contextmanager
def _source_denied():
    changed = []
    def denied(*args, **kwargs): raise SupervisionRefusal("REFUSED: supervision_source_refused")
    def replace(obj, name): changed.append((obj, name, getattr(obj, name))); setattr(obj, name, denied)
    try:
        for name in ("connect", "connect_ex"): replace(socket.socket, name)
        for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr"): replace(socket, name)
        yield
    finally:
        for obj, name, value in reversed(changed): setattr(obj, name, value)

class _Directory:
    """Original nofollow ancestry to one exclusively new or bootstrap directory."""
    def __init__(self, name, *, create):
        self.fds, self.nodes, self.closed = [], [], False
        self.path = ROOT / PARENT / name
        try:
            require(ROOT.resolve() == ROOT and Path.cwd().resolve() == ROOT, "native_proof_path")
            parent = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); self.fds.append(parent)
            self.nodes.append((ROOT, parent, _dir(os.fstat(parent))))
            path = ROOT
            for part in (*PARENT.parts, name):
                path /= part
                if path == self.path and create:
                    try: os.stat(part, dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError: pass
                    else: raise SupervisionRefusal("REFUSED: native_proof_exists")
                    os.mkdir(part, 0o700, dir_fd=parent); os.fsync(parent)
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                self.fds.append(fd); self.nodes.append((path, fd, _dir(os.fstat(fd), path == self.path)))
                parent = fd
            self.fd, self.parent = self.fds[-1], self.fds[-2]; self.check()
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def check(self):
        require(not self.closed and ROOT.resolve() == ROOT and Path.cwd().resolve() == ROOT, "native_proof_path")
        for path, fd, pin in self.nodes:
            require(path.resolve() == path and _dir(path.lstat(), path == self.path)
                == _dir(os.fstat(fd), path == self.path) == pin, "native_proof_path")
    def named(self):
        for path, unused, pin in self.nodes:
            require(path.resolve() == path and _dir(path.lstat(), path == self.path) == pin, "native_proof_path")
    def close(self):
        try: _drain(self.fds)
        finally: self.closed = True


class _Files:
    def __init__(self, fd, parent, path, check, roles):
        self.fd, self.parent, self.path, self.callback, self.roles = fd, parent, path, check, frozenset(roles)
        self.originals, self.fds, self.closed = {}, [], False
    def check(self):
        self.callback()
        require(not self.closed and set(os.listdir(self.fd)) <= self.roles, "native_proof_membership")
    def create(self, name):
        self.check(); require(name in self.roles and name not in self.originals, "native_proof_membership")
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        self.fds.append(fd); os.fchmod(fd, 0o600)
        info = os.fstat(fd); self.originals[name] = [fd, _stamp(info)[:6], None, None]
        self.validate(fd, name, 0); return fd
    def validate(self, fd, name, size):
        self.check(); row = self.originals.get(name)
        require(row is not None and row[0] == fd, "native_proof_protection")
        a, b = os.fstat(fd), os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        require(stat.S_ISREG(a.st_mode) and _stamp(a)[:6] == row[1]
            and a.st_uid == os.getuid() and stat.S_IMODE(a.st_mode) == 0o600 and a.st_nlink == 1
            and a.st_size == size, "native_proof_protection"); _same(_stamp(a), _stamp(b))
    def seal(self, name, fd, stamp, raw):
        self.validate(fd, name, len(raw)); _same(_stamp(os.fstat(fd)), stamp)
        os.lseek(fd, 0, os.SEEK_SET)
        require(os.read(fd, len(raw) + 1) == raw, "native_proof_stamp")
        _same(_stamp(os.fstat(fd)), stamp)
        require(self.originals[name][2] is None, "native_proof_stamp")
        self.originals[name][2:] = stamp, raw
    def write(self, name, raw):
        limit = MAXIMUM_NATIVE_BYTES if name in RAW_ROLES or name == INVENTORY_ROLE else 65536 if name in PRIVATE_ROLES else MAXIMUM_CONTROL_BYTES
        require(type(raw) is bytes and 0 < len(raw) <= limit, "native_proof_write")
        fd = self.create(name); _write(fd, raw); self.validate(fd, name, len(raw))
        os.fsync(fd); os.fsync(self.fd); os.fsync(self.parent)
        self.seal(name, fd, _stamp(os.fstat(fd)), raw)
    def audit(self):
        self.check(); require(set(os.listdir(self.fd)) == set(self.originals), "native_proof_membership")
        for name, (fd, unused, stamp, raw) in self.originals.items():
            require(stamp is not None and type(raw) is bytes, "native_proof_stamp")
            self.validate(fd, name, len(raw)); _same(_stamp(os.fstat(fd)), stamp)
            os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "native_proof_stamp")
            _same(_stamp(os.fstat(fd)), stamp)
    def named(self):
        require(self.path.resolve() == self.path and set(os.listdir(self.path)) == set(self.originals), "native_proof_membership")
        for name, (unused, unused_pin, stamp, unused_raw) in self.originals.items():
            require(stamp is not None, "native_proof_stamp"); _same(_stamp((self.path / name).lstat()), stamp)
    def inventory(self):
        self.audit()
        require(INVENTORY_ROLE not in self.originals and "run.completed.provisional.json" not in self.originals,
            "native_proof_membership")
        return [{"name": name, "sha256": hash_bytes(row[3]), "bytes": len(row[3]), "original_stamp": list(row[2])}
            for name, row in sorted(self.originals.items())]
    def close(self):
        try: _drain(self.fds)
        finally: self.closed = True


class _Code7:
    def __init__(self, head, remote, clock):
        self.head, self.remote, self.clock, self.rows, self.fds = head, remote, clock, {}, []
        try:
            for ordinal, name in enumerate(CODE_FILES, 1):
                _component("code_file", ordinal)
                path = ROOT / name; require(path.resolve() == path, "native_proof_path")
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK); self.fds.append(fd)
                info = os.fstat(fd)
                require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= 1024 ** 2, "native_proof_code")
                self.rows[name] = fd, _stamp(info), b""
            self.manifest = self.audit(initial=True)
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def audit(self, initial=False):
        result = {}
        for ordinal, (name, (fd, stamp, original)) in enumerate(self.rows.items(), 1):
            _component("code_file", ordinal)
            _guard(self.head, self.remote); self.clock.check()
            require((ROOT / name).resolve() == ROOT / name, "native_proof_path")
            _same(_stamp(os.fstat(fd)), stamp); _same(_stamp((ROOT / name).lstat()), stamp)
            os.lseek(fd, 0, os.SEEK_SET); raw = os.read(fd, 1024 ** 2 + 1)
            require(raw == _git(["show", self.head + ":" + name]), "native_proof_code")
            if not initial: require(raw == original, "native_proof_code")
            _same(_stamp(os.fstat(fd)), stamp); self.rows[name] = fd, stamp, raw; result[name] = hash_bytes(raw)
        self.clock.check(); return result
    def named(self):
        for ordinal, (name, (unused, stamp, unused_raw)) in enumerate(self.rows.items(), 1):
            _component("code_file", ordinal)
            require((ROOT / name).resolve() == ROOT / name, "native_proof_path")
            _same(_stamp((ROOT / name).lstat()), stamp)
    def close(self): _drain(self.fds)


def _protected(info, maximum=MAX_CONFIG):
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
        and info.st_nlink == 1 and 0 < info.st_size <= maximum, "startup_config")
    return _stamp(info)


class _Inputs:
    """Exact two-role configuration reauthentication, never an evidence seal.

    Original identity, protection, size and expected bytes never change. Each
    separate read has its own full9 FD/name barrier through its original close.
    Timestamps between operations are observations, not source custody evidence.
    """
    ROLES = ("launch.spec.json", "job.plist")
    def __init__(self, directory):
        require(type(directory) is _Directory and directory.path == ROOT / PARENT / BOOTSTRAP, "startup_config")
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
            _same(_stamp(os.fstat(fd)), before); _same(_stamp(path.lstat()), before)
            raw = os.read(fd, MAX_CONFIG + 1)
            require(len(raw) == pin[6] and (expected is None or raw == expected), "startup_config")
            _same(_stamp(os.fstat(fd)), before); _same(_stamp(path.lstat()), before)
        except BaseException as error: primary = error; raise
        finally: _close(fd, primary)
        require(_protected(path.lstat())[:7] == pin, "startup_config")
        _same(_stamp(path.lstat()), before)  # This reader's close remains inside its full9 barrier.
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
        os.fchmod(fd, 0o600); before = _stamp(os.fstat(fd))
        require(before[4:7] == (0o600, 1, 0), "startup_config"); _same(_stamp(os.stat(name, dir_fd=directory.fd, follow_symlinks=False)), before)
        _write(fd, raw); os.fsync(fd); os.fsync(directory.fd); os.fsync(directory.parent)
        stamp = _protected(os.fstat(fd)); _same(_stamp(os.stat(name, dir_fd=directory.fd, follow_symlinks=False)), stamp)
        os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "startup_config"); _same(_stamp(os.fstat(fd)), stamp)
        pin = stamp[:7]
    except BaseException as error: primary = error; raise
    finally: _close(fd, primary)
    # Configuration timestamps across separate operations confer no evidence cap.
    require(_protected(os.stat(name, dir_fd=directory.fd, follow_symlinks=False))[:7] == pin, "startup_config")
    return pin


class _DomainVolume:
    def __init__(self, clock):
        _component("native_platform", 1)
        _platform()
        clock.check()
        _component("native_parent", 2)
        self.clock, self.directory, self.fds, self.origins = clock, _Directory(DOMAIN, create=True), [], {}
        self.path = self.directory.path; self.image = self.path / "backing.sparseimage"; self.mount = self.path / "mount"
        self.mount_fd = None
        try:
            _component("native_host", 3)
            host = _native_statfs(self.directory.fd)
            require(host["flags"] & native.MNT_LOCAL and not host["flags"] & native.MNT_IGNORE_OWNERSHIP
                and host["bsize"] * host["bavail"] >= VIRTUAL_BYTES + 1024 ** 3, "native_proof_capacity")
            self.host_device = os.fstat(self.directory.fd).st_dev
            _component("native_before_info", 4)
            self.command("before", "info"); self._association(self.origins["before"], absent=True)
            _component("native_create", 5)
            self.command("create", "create")
            require(set(os.listdir(self.directory.fd)) == {"backing.sparseimage"}, "native_proof_membership")
            _component("native_backing", 6)
            fd = os.open("backing.sparseimage", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory.fd)
            self.fds.append(fd); self.backing_fd = fd
            require(stat.S_ISREG(os.fstat(fd).st_mode) and os.fstat(fd).st_uid == os.getuid() and os.fstat(fd).st_nlink == 1,
                "native_proof_backing"); os.fchmod(fd, 0o600); self.backing_pin = native._backing(os.fstat(fd))
            _component("native_under_mount", 7)
            os.mkdir("mount", 0o700, dir_fd=self.directory.fd)
            self.under_fd = os.open("mount", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.directory.fd)
            self.fds.append(self.under_fd); self.under_pin = _dir(os.fstat(self.under_fd), True)
            require(not os.listdir(self.under_fd), "native_proof_membership")
            _component("native_attach", 8)
            self.command("attach", "attach"); self.attach_entities = native._entities(plistlib.loads(self.origins["attach"]))
            _component("native_initial_info", 9)
            self.command("initial", "info"); self.device = self._association(self.origins["initial"])
            _component("native_mount_open", 11)
            self.mount_fd = os.open("mount", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.directory.fd)
            self.fds.append(self.mount_fd); info = os.fstat(self.mount_fd)
            self.creation = native._fresh_root_identity(info); current = _native_statfs(self.mount_fd)
            self.mount_native = native._mount_identity(current); self.node = _device_node(self.device, info.st_dev)
            self._native(current)
            _component("native_capacity", 13)
            require(type(current["bsize"]) is int and current["bsize"] > 0
                and type(current["blocks"]) is int and 4 * 1024 ** 3 <= current["blocks"] * current["bsize"] <= VIRTUAL_BYTES
                and type(current["bavail"]) is int and current["bavail"] * current["bsize"] >= 4 * 1024 ** 3,
                "native_proof_capacity")
            require(info.st_dev != self.host_device and self.creation == native._fresh_root_identity(self.mount.lstat()), "native_proof_mount")
            _component("native_root_mode", 14)
            os.fchmod(self.mount_fd, 0o700); os.fsync(self.mount_fd); self.mount_pin = _dir(os.fstat(self.mount_fd), True)
            require(native._fresh_root_identity(os.fstat(self.mount_fd)) == self.creation, "native_proof_mount")
            _component("native_system", 15)
            self.system = None
            require(set(os.listdir(self.mount_fd)) <= {".fseventsd"}, "native_proof_membership")
            if ".fseventsd" in os.listdir(self.mount_fd): self.system = self._system()
            _component("main_directory")
            os.mkdir("main", 0o700, dir_fd=self.mount_fd)
            self.main_fd = os.open("main", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.mount_fd); self.fds.append(self.main_fd)
            self.main_seal = _stamp(os.fstat(self.main_fd)); require(not os.listdir(self.main_fd), "native_proof_membership")
            _same(_stamp((self.mount / "main").lstat()), self.main_seal)
            _component("native_first_check", 16)
            self.check()
        except BaseException as error:
            failure_summary(error)
            try: self.close()
            except BaseException: pass
            raise
    def arguments(self, verb):
        if verb == "create": return [native.HDIUTIL, "create", "-type", "SPARSE", "-size", "8g", "-fs", "APFS", "-uid", str(os.getuid()), "-gid", str(os.getgid()), "-mode", "0700", "-volname", "SI_NATIVE_SUPERVISION_V2_V1", "-nospotlight", "-plist", str(self.image)]
        if verb == "attach": return [native.HDIUTIL, "attach", "-mountpoint", str(self.mount), "-mount", "required", "-nobrowse", "-owners", "on", "-noautoopen", "-noautoopenro", "-noautoopenrw", "-plist", str(self.image)]
        require(verb == "info", "native_proof_command"); return [native.HDIUTIL, "info", "-plist"]
    def command(self, role, verb):
        require(role not in self.origins and {"before": "info", "create": "create", "attach": "attach", "initial": "info", "terminal": "info"}.get(role) == verb,
            "native_proof_command")
        remaining = self.clock.check(); require(remaining > 0, "native_proof_deadline")
        self._pre_command(role)
        result = _native_command(self.arguments(verb), min(COMMAND_SECONDS, remaining))
        self.clock.check()
        require(type(result.returncode) is int and result.returncode == 0 and type(result.stdout) is bytes
            and 0 < len(result.stdout) <= MAXIMUM_NATIVE_BYTES, "native_proof_command")
        parsed = plistlib.loads(result.stdout)
        require((type(parsed) is list and parsed == [str(self.image)]) if verb == "create" else type(parsed) is dict,
            "native_proof_plist")
        self.origins[role] = result.stdout
    def _pre_command(self, role):
        self.directory.check()
        if role in ("before", "create"):
            require(not os.listdir(self.directory.fd), "native_proof_membership"); return
        require(set(os.listdir(self.directory.fd)) == {"backing.sparseimage", "mount"}, "native_proof_membership")
        require(native._backing(os.fstat(self.backing_fd))
            == native._backing(os.stat("backing.sparseimage", dir_fd=self.directory.fd, follow_symlinks=False))
            == native._backing(self.image.lstat()) == self.backing_pin, "native_proof_backing")
        require(_dir(os.fstat(self.under_fd), True) == self.under_pin and self.mount.resolve() == self.mount,
            "native_proof_path")
        if role == "attach":
            require(_dir(os.stat("mount", dir_fd=self.directory.fd, follow_symlinks=False), True)
                == _dir(self.mount.lstat(), True) == self.under_pin and not os.listdir(self.under_fd), "native_proof_path")
        elif role == "initial":
            mounted = [r for r in self.attach_entities if r[3] is not None]
            require(len(mounted) == 1 and mounted[0][3] == str(self.mount)
                and self.mount.lstat().st_dev != self.host_device, "native_proof_mount")
            native._fresh_root_identity(self.mount.lstat())
        else:
            require(role == "terminal", "native_proof_command"); self.check()
    def _association(self, raw, absent=False):
        _component("native_association", 10)
        parsed = plistlib.loads(raw); images = parsed.get("images")
        require(type(images) is list and len(images) <= 256 and all(type(r) is dict for r in images), "native_proof_association")
        matching = [r for r in images if r.get("image-path") == str(self.image)]
        require(len(matching) == (0 if absent else 1), "native_proof_association")
        if absent: return None
        selected = matching[0]; require(not any(k in selected for k in ("shadow-path", "shadow-file")), "native_proof_association")
        entities = native._entities(selected); mounted = [r for r in entities if r[3] is not None]
        attached = [r for r in self.attach_entities if r[3] is not None]
        require(len(mounted) == len(attached) == 1 and mounted[0][0] == attached[0][0]
            and mounted[0][3] == attached[0][3] == str(self.mount)
            and {r[0] for r in self.attach_entities} <= {r[0] for r in entities}, "native_proof_association")
        native._mounted_descriptor(mounted[0]); native._mounted_descriptor(attached[0])
        device = mounted[0][0]; own_devices = {r[0] for r in entities} | {r[0] for r in self.attach_entities}
        device_counts = {name: 0 for name in own_devices}; mounts = 0
        for image in images:
            rows = image.get("system-entities", [])
            require(type(rows) is list and len(rows) <= 64 and all(type(r) is dict for r in rows), "native_proof_association")
            for name in own_devices: device_counts[name] += sum(r.get("dev-entry") == name for r in rows)
            mounts += sum(r.get("mount-point") == str(self.mount) for r in rows)
        require(mounts == 1 and all(count == 1 for count in device_counts.values()), "native_proof_association"); return device
    def _native(self, current):
        _component("native_contract", 12)
        require(current["fstype"] == "apfs" and current["owner"] == os.getuid()
            and current["flags"] & native.MNT_LOCAL and current["flags"] & native.MNT_DONTBROWSE
            and not current["flags"] & (native.MNT_RDONLY | native.MNT_IGNORE_OWNERSHIP)
            and current["mounted_on"] == str(self.mount) and current["mounted_from"] == self.device
            and native._mount_identity(current) == self.mount_native, "native_proof_mount")
    def _system(self):
        _component("native_system", 15)
        info = os.stat(".fseventsd", dir_fd=self.mount_fd, follow_symlinks=False)
        require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == 0
            and info.st_gid == os.fstat(self.mount_fd).st_gid and info.st_dev == os.fstat(self.mount_fd).st_dev,
            "native_proof_protection")
        return _stamp(info)[:6]
    def check(self):
        _component("native_parent", 2)
        self.clock.check(); self.directory.check()
        require(set(os.listdir(self.directory.fd)) == {"backing.sparseimage", "mount"}, "native_proof_membership")
        _component("native_backing", 6)
        require(native._backing(os.fstat(self.backing_fd)) == native._backing(self.image.lstat()) == self.backing_pin,
            "native_proof_backing")
        _component("native_under_mount", 7)
        require(_dir(os.fstat(self.under_fd), True) == self.under_pin and self.mount.resolve() == self.mount
            and _dir(os.fstat(self.mount_fd), True) == _dir(self.mount.lstat(), True) == self.mount_pin, "native_proof_mount")
        self._native(_native_statfs(self.mount_fd))
        _component("native_mount_open", 11)
        require(_device_node(self.device, os.fstat(self.mount_fd).st_dev) == self.node, "native_proof_mount")
        _component("native_system", 15)
        expected = ({".fseventsd"} if self.system is not None else set()) | {"main"} | ({"proof"} if hasattr(self, "proof_pin") else set())
        require(set(os.listdir(self.mount_fd)) == expected, "native_proof_membership")
        if self.system is not None: require(self._system() == self.system, "native_proof_protection")
        _same(_stamp(os.fstat(self.main_fd)), self.main_seal); _same(_stamp((self.mount / "main").lstat()), self.main_seal)
        require(not os.listdir(self.main_fd), "native_proof_membership")
        if hasattr(self, "proof_pin"): require(_dir((self.mount / "proof").lstat(), True) == self.proof_pin, "native_proof_path")
    def outputs(self):
        self.check(); os.mkdir("proof", 0o700, dir_fd=self.mount_fd)
        fd = os.open("proof", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.mount_fd)
        self.fds.append(fd); self.proof_pin = _dir(os.fstat(fd), True); self.check()
        return _Files(fd, self.mount_fd, self.mount / "proof", self.check, ROLES)
    def terminal(self):
        self.command("terminal", "info"); require(self._association(self.origins["terminal"]) == self.device, "native_proof_association"); self.check()
    def inventory(self):
        self.check()
        return {"domain_original_identity": self.directory.nodes[-1][2], "main_original_seal": self.main_seal, "proof_original_identity": self.proof_pin, "backing_original_identity": self.backing_pin, "mount_original_identity": self.mount_pin,
            "native_original_identity": self.mount_native, "device_node_original_identity": self.node,
            "fresh_root_creation_identity": self.creation, "system_original_metadata": self.system,
            "attach_original_entities": self.attach_entities,
            "original_command_output_sha256s": {name: hash_bytes(raw) for name, raw in sorted(self.origins.items())}}
    def named(self):
        self.directory.named()
        require(set(os.listdir(self.path)) == {"backing.sparseimage", "mount"}
            and native._backing(self.image.lstat()) == self.backing_pin and _dir(self.mount.lstat(), True) == self.mount_pin,
            "native_proof_path")
        require(set(os.listdir(self.mount)) == ({".fseventsd"} if self.system is not None else set()) | {"proof", "main"}
            and _dir((self.mount / "proof").lstat(), True) == self.proof_pin, "native_proof_membership")
        if self.system is not None: require(_stamp((self.mount / ".fseventsd").lstat())[:6] == self.system, "native_proof_protection")
        _same(_stamp((self.mount / "main").lstat()), self.main_seal); require(not os.listdir(self.mount / "main"), "native_proof_membership")
    def close(self):
        first = None
        try: _drain(self.fds)
        except BaseException as error: first = error
        try: self.directory.close()
        except BaseException as error:
            if first is None: first = error
        if first is not None: raise first



def _payload(head, remote, manifest, observer):
    return {"schema": "si-native-supervision-bootstrap-v1", "runtime_head": head, "actual_remote": remote,
        "policy_sha256": POLICY_SHA256, "code_manifest": manifest, "observer": startup._observer_config(observer),
        "authority": authority()}


def _wrapper_body():
    body = startup._import_body().replace(startup.MODULE, MODULE).replace("run-readonly", "run-proof")
    body = body.replace("si-startup-PTY-observation-v7", "si-native-supervision-observation-v1")
    body = body.replace(hash_payload(startup.authority()), hash_payload(authority()))
    start = body.index("  F={"); end = body.index("\n  R={", start)
    body = body[:start] + "  F={'stage':'startup_import','component':'operation','contract_code':'startup_import_failed','upstream_contract_code':None,'errno_name':n,'mismatching_fields':[]}" + body[end:]
    return body.replace("'failure':F,'authority_sha256'", "'failure':F,'marker':None,'authority_sha256'")


def _wrapper():
    encoded = base64.b64encode(zlib.compress(_wrapper_body().encode(), 9)).decode("ascii")
    return "import os\ntry:\n import base64,zlib\n exec(zlib.decompress(base64.b64decode(" + repr(encoded) + ")))\nexcept BaseException:\n os._exit(2)\n"


def build_launchd_plist(head, remote, digest, observer):
    require(worker._hash(head) and worker._hash(remote) and re.fullmatch(r"[0-9a-f]{64}", digest), "supervision_arguments")
    observer = startup._observer_config(observer)
    return {"Label": LABEL, "ProgramArguments": [worker.PYTHON, "-B", "-c", _wrapper(), "run-proof", "--head", head,
        "--remote", remote, "--spec-sha256", digest, "--observer", canonical_json(observer)],
        "WorkingDirectory": str(ROOT), "EnvironmentVariables": worker._environment(), "RunAtLoad": False, "KeepAlive": False,
        "StandardOutPath": "/dev/null", "StandardErrorPath": observer["slave_path"]}


def prepare_bootstrap(head, remote, observer):
    registered(); observer = startup._observer_config(observer); clock = _Clock()
    code = directory = inputs = None; error = None
    try:
        _phase("current_code"); _guard(head, remote); code = _Code7(head, remote, clock)
        _phase("bootstrap"); directory = _Directory(BOOTSTRAP, create=True)
        raw = canonical_json(_payload(head, remote, code.manifest, observer)).encode(); digest = hash_bytes(raw)
        job = plistlib.dumps(build_launchd_plist(head, remote, digest, observer), sort_keys=True)
        pins = {"launch.spec.json": _config_write(directory, "launch.spec.json", raw), "job.plist": _config_write(directory, "job.plist", job)}
        inputs = _Inputs(directory)
        inputs.read("launch.spec.json", expected=raw, original_pin=pins["launch.spec.json"])
        inputs.read("job.plist", expected=job, original_pin=pins["job.plist"])
        code.audit(); _guard(head, remote); inputs.audit(); clock.check()
    except BaseException as failure: error = failure; failure_summary(failure); raise
    finally:
        first = error
        for obj in (inputs, directory, code):
            if obj is not None:
                try: obj.close()
                except BaseException as failure:
                    if first is None: first = failure; failure_summary(failure)
        if error is None and first is not None: raise first
    code.named(); inputs.audit(named=True); clock.check()
    _PREPARED[(head, remote, digest, observer["nonce"])] = tuple((name, *inputs.rows[name]) for name in inputs.ROLES)
    return {"status": "prepared_not_loaded", "spec_sha256": digest, "authority": authority()}


def _read_config(head, remote, digest, observer, manifest):
    directory = _Directory(BOOTSTRAP, create=False); inputs = _Inputs(directory)
    try:
        raw = inputs.read("launch.spec.json")
        require(hash_bytes(raw) == digest and raw == canonical_json(_payload(head, remote, manifest, observer)).encode(), "supervision_code")
        require(inputs.read("job.plist") == plistlib.dumps(build_launchd_plist(head, remote, digest, observer), sort_keys=True), "supervision_code")
        inputs.audit(); return directory, inputs
    except BaseException:
        try: inputs.close()
        finally: directory.close()
        raise


def _audit_local(outputs):
    """Final original control audit with no Git/native callback side effects."""
    require(outputs.path.resolve() == outputs.path and _dir(os.fstat(outputs.fd), True) == _dir(outputs.path.lstat(), True)
        and set(os.listdir(outputs.fd)) == set(outputs.originals), "native_proof_membership")
    for name, (fd, pin, stamp, raw) in outputs.originals.items():
        require(type(raw) is bytes and stamp is not None and _stamp(os.fstat(fd))[:6] == pin, "native_proof_stamp")
        _same(_stamp(os.fstat(fd)), stamp); _same(_stamp(os.stat(name, dir_fd=outputs.fd, follow_symlinks=False)), stamp)
        os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "native_proof_stamp")
        _same(_stamp(os.fstat(fd)), stamp)


class _NegativeReporter:
    def __init__(self, outputs, volume):
        self.path, self.mount, self.domain = outputs.path, volume.mount, volume.path
        self.pins = (_dir(os.fstat(outputs.fd), True), _dir(os.fstat(volume.mount_fd), True), _dir(os.fstat(volume.directory.fd), True))
        self.fds = []; self.used = False
        try:
            for fd in (outputs.fd, volume.mount_fd, volume.directory.fd): self.fds.append(os.dup(fd))
            self.check()
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def check(self):
        require(len(self.fds) == 3, "supervision_original")
        for fd, path, pin in zip(self.fds, (self.path, self.mount, self.domain), self.pins):
            require(path.resolve() == path and _dir(os.fstat(fd), True) == _dir(path.lstat(), True) == pin, "supervision_original")
    def refuse(self, error):
        require(not self.used, "supervision_negative"); self.used = True; self.check()
        raw = canonical_json({"schema": "si-native-supervision-refusal-v1", "failure": failure_summary(error), "authority": authority()}).encode()
        fd = os.open("run.refused.json", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fds[0]); primary = None
        try:
            os.fchmod(fd, 0o600); _write(fd, raw); os.fsync(fd); os.fsync(self.fds[0]); os.fsync(self.fds[1])
            before = _protected(os.fstat(fd)); _same(_stamp(os.stat("run.refused.json", dir_fd=self.fds[0], follow_symlinks=False)), before)
            os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "supervision_negative"); _same(_stamp(os.fstat(fd)), before)
        except BaseException as error: primary = error; raise
        finally: _close(fd, primary)
        self.check(); _same(_stamp((self.path / "run.refused.json").lstat()), before)
    def close(self): _drain(self.fds)


class ProducerObservation:
    __slots__ = ("_anchor",)
    def __init__(self): raise SupervisionRefusal("REFUSED: supervision_factory")
    def public_summary(self):
        row = _PRODUCERS.get(id(self)); require(type(row) is tuple and row[0] is self and self._anchor is row, "supervision_factory")
        require(row[2][0] is row[3] and row[2][1] == 0, "supervision_wait")
        return json.loads(row[1])


class ClosedNativeSupervision:
    __slots__ = ("_anchor",)
    def __init__(self): raise SupervisionRefusal("REFUSED: supervision_factory")
    def public_summary(self):
        row = _CLOSED.get(id(self)); require(type(row) is tuple and row[0] is self and self._anchor is row and row[2] in _ROOT_RECEIPTS, "supervision_factory")
        receipt = _ROOT_RECEIPTS[row[2]]
        require(type(receipt) is tuple and len(receipt) == 6 and receipt[0] is row[3] and receipt[1] == row[1]
            and _kernel_origin(receipt[2][0]) is receipt[2] and _terminal(receipt[2][0]) and receipt[2][0]["exit"] == 0
            and _root_context_snapshot(*receipt[3]) == receipt[4], "supervision_factory")
        return json.loads(row[1])


def _hold(state):
    _HELD.append(state)
    while True:
        if state.get("master") is not None:
            try: state["raw"], unused = _read_private(state["master"], state["raw"])
            except BaseException: pass
        time.sleep(0.1 if state.get("master") is not None else 30)


def run_registered(head, remote, digest, observer):
    global _USED
    registered(); require(not _USED, "native_proof_already_used"); _USED = True
    with _source_denied(): return _produce(head, remote, digest, startup._observer_config(observer))


def _produce(head, remote, digest, observer):
    clock = _Clock(); code = directory = config = volume = outputs = reporter = process = None
    error = None; held = False; entered = returned = False; origin = wait = marker = None
    try:
        _phase("current_code"); _guard(head, remote); code = _Code7(head, remote, clock)
        _phase("bootstrap"); directory, config = _read_config(head, remote, digest, observer, code.manifest)
        _phase("native_creation"); volume = _new_domain(clock)
        _phase("output_creation"); outputs = volume.outputs(); reporter = _NegativeReporter(outputs, volume)
        for role in ("before", "create", "attach", "initial"): outputs.write("native." + role + ".plist", volume.origins[role])
        started = {"schema": "si-native-supervision-started-v1", "runtime_head": head, "actual_remote": remote,
            "policy_sha256": POLICY_SHA256, "spec_sha256": digest, "nonce": observer["nonce"], "producer_pid": os.getpid(), "authority": authority()}
        outputs.write("run.started.json", canonical_json(started).encode())
        _guard(head, remote); code.audit(); config.audit(); volume.check(); outputs.audit()
        log_fd = outputs.create("stdout.jsonl"); os.fsync(log_fd); os.fsync(outputs.fd); os.fsync(outputs.parent)
        _phase("child_launch"); began = worker._now(); process = _launch_worker(head, remote)
        require(type(process.pid) is int and process.pid > 0 and process.stdout is not None, "supervision_wait")
        origin = (process, digest, code.manifest, object()); worker._CHILDREN[process] = origin
        _phase("child_observation"); entered = True
        status, stdout_sha, seal = _COLLECT(process, outputs, log_fd, began); returned = True
        wait = worker._WAITS.get(process)
        require(type(wait) is tuple and len(wait) == 3 and wait[0] is origin and worker._CHILDREN.get(process) is origin and wait[1] == status == 0, "supervision_wait")
        os.lseek(log_fd, 0, os.SEEK_SET); raw = os.read(log_fd, worker.MAXIMUM_LOG_BYTES + 1)
        require(hash_bytes(raw) == stdout_sha, "supervision_original"); outputs.seal("stdout.jsonl", log_fd, seal, raw)
        report = {**started, "schema": "si-native-supervision-child-v1", "child_pid": process.pid, "actual_child_exit": 0,
            "stdout_sha256": stdout_sha, "kernel_exit_attested": False, "status": "provisional_until_Root_kernel0"}
        outputs.write("child.exit.provisional.json", canonical_json(report).encode())
        _phase("terminal_code"); code.audit(); _guard(head, remote)
        _phase("terminal_native"); volume.terminal(); outputs.write("native.terminal.plist", volume.origins["terminal"])
        _phase("inventory_publication")
        inventory = {"schema": "si-native-supervision-inventory-v1", "controls": outputs.inventory(), "native": volume.inventory(),
            "code_manifest": code.manifest, "runtime_head": head, "policy_sha256": POLICY_SHA256, "nonce": observer["nonce"], "authority": authority()}
        inventory_raw = canonical_json(inventory).encode(); outputs.write(INVENTORY_ROLE, inventory_raw)
        inventory_stamp = outputs.originals[INVENTORY_ROLE][2]
        marker = {**report, "schema": "si-native-supervision-marker-v1", "inventory_sha256": hash_bytes(inventory_raw),
            "inventory_bytes": len(inventory_raw), "inventory_original_stamp": list(inventory_stamp), "code_manifest_sha256": hash_payload(code.manifest),
            "durable_Main_receipt": False}
        marker_raw = canonical_json(marker).encode(); outputs.write(MARKER_ROLE, marker_raw)
        marker_pin = tuple(outputs.originals[MARKER_ROLE][2]); marker_sha = hash_bytes(marker_raw)
        # Finish all Git/native callbacks before the final original-only audit.
        code.audit(); _guard(head, remote); volume.check(); config.audit(); code.close(); code.named()
        _phase("original_audit"); _audit_local(outputs); clock.check()
    except BaseException as failure:
        error = failure; failure_summary(failure)
        if reporter is not None:
            try: reporter.refuse(failure)
            except BaseException: pass
        actual_wait = worker._WAITS.get(process) if process is not None else None
        unknown = process is not None and not (type(actual_wait) is tuple and len(actual_wait) == 3 and actual_wait[0] is origin and type(actual_wait[1]) is int)
        if unknown or entered and not returned:
            held = True
            state = {"process": process, "code": code, "directory": directory, "config": config, "volume": volume,
                "outputs": outputs, "reporter": reporter, "origin": origin, "failure": failure, "trace": BaseException.__traceback__.__get__(failure, BaseException)}
            try: _hold(state)
            except BaseException: raise failure
        # Known-negative paths continue through original reporter cleanup.
    finally:
        if not held:
            first = error; _phase("cleanup")
            actions = []
            if process is not None and process.stdout is not None: actions.append(process.stdout.close)
            actions += [obj.close for obj in (outputs, volume, code, config, directory) if obj is not None]
            for close in actions:
                try: close()
                except BaseException as failure:
                    if first is None: first = failure; failure_summary(failure)
            if first is not None and reporter is not None:
                try: reporter.refuse(first)
                except BaseException: pass
            if error is None and first is not None: error = first
    if held: raise SupervisionRefusal("REFUSED: supervision_unknown")
    terminal_error = error
    if terminal_error is None:
        try:
            _phase("named_audit"); volume.named(); code.named(); config.audit(named=True); outputs.named(); clock.check()
            require(set(os.listdir(outputs.path)) == POSITIVE_ROLES, "supervision_negative")
        except BaseException as failure:
            terminal_error = failure; failure_summary(failure)
            if reporter is not None:
                try: reporter.refuse(failure)
                except BaseException: pass
    if reporter is not None:
        try: reporter.close()
        except BaseException as failure:
            if terminal_error is None: terminal_error = failure; failure_summary(failure)
    if terminal_error is not None: raise terminal_error
    # Last original named seals follow reporter cleanup; no reopen/rebaseline.
    volume.named(); code.named(); config.audit(named=True); outputs.named(); clock.check()
    require(set(os.listdir(outputs.path)) == POSITIVE_ROLES, "supervision_negative")
    public = {"status": "producer_checks_complete_provisional", "marker": {"sha256": marker_sha, "stamp": list(marker_pin)},
        "actual_child_exit": 0, "kernel_exit_attested": False, "durable_Main_receipt": False, "authority": authority()}
    value = object.__new__(ProducerObservation); row = (value, canonical_json(public), wait, origin, object())
    value._anchor = row; _PRODUCERS[id(value)] = row; return value


def _observer_fd(): return 2


class _Observer:
    def __init__(self, config, digest):
        self.config = startup._observer_config(config); require(re.fullmatch(r"[0-9a-f]{64}", digest), "supervision_arguments")
        self.digest, self.fd, self.attempted = digest, _observer_fd(), False; startup._tty_check(self.fd, self.config)
    def emit(self, result=None, error=None):
        require(not self.attempted and ((result is None) != (error is None)), "supervision_original"); self.attempted = True
        startup._tty_check(self.fd, self.config)
        if result is not None:
            require(type(result) is ProducerObservation, "supervision_factory"); marker = result.public_summary()["marker"]; detail = None
        else: marker = None; detail = _checked_failure(failure_summary(error))
        payload = {"schema": "si-native-supervision-observation-v1", "nonce": self.config["nonce"], "spec_sha256": self.digest,
            "pid": os.getpid(), "status": "producer_complete_provisional" if marker is not None else "refused",
            "marker": marker, "failure": detail, "authority_sha256": hash_payload(authority())}
        raw = canonical_json(payload).encode() + b"\n"; require(0 < len(raw) <= MAX_WIRE and raw.count(b"\n") == 1, "supervision_original")
        os.set_blocking(self.fd, False); count = os.write(self.fd, raw)
        require(type(count) is int and count == len(raw), "supervision_original")


def _checked_failure(detail):
    require(type(detail) is dict and set(detail) == {"stage", "component", "contract_code", "upstream_contract_code", "errno_name", "mismatching_fields"}
        and type(detail["stage"]) is str and detail["stage"] in _STAGES
        and type(detail["component"]) is str and detail["component"] in _COMPONENTS
        and (detail["contract_code"] is None or type(detail["contract_code"]) is str and detail["contract_code"] in _CODES)
        and (detail["upstream_contract_code"] is None or type(detail["upstream_contract_code"]) is str and detail["upstream_contract_code"] in old._CODES | worker._CODES | native._CODES)
        and (detail["errno_name"] is None or type(detail["errno_name"]) is str and detail["errno_name"] in set(_ERRNOS.values()) | set(native._ERRNOS.values()) | set(worker._ERRNOS.values()))
        and type(detail["mismatching_fields"]) is list and len(detail["mismatching_fields"]) <= 9
        and all(type(value) is str and value in old._STAMP_NAMES for value in detail["mismatching_fields"]), "supervision_original")
    return json.loads(canonical_json(detail))


def _validated_observation(raw, observer, digest, pid):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_WIRE and raw.count(b"\n") == 1, "supervision_original")
    value = json.loads(raw)
    require(type(value) is dict and set(value) == {"schema", "nonce", "spec_sha256", "pid", "status", "marker", "failure", "authority_sha256"}
        and raw == canonical_json(value).encode() + b"\n" and value["schema"] == "si-native-supervision-observation-v1"
        and value["nonce"] == observer["nonce"] and value["spec_sha256"] == digest
        and type(value["pid"]) is int and value["pid"] == pid and 0 < pid < 2 ** 31
        and value["authority_sha256"] == hash_payload(authority()), "supervision_original")
    if value["status"] == "refused":
        require(value["marker"] is None, "supervision_original"); _checked_failure(value["failure"]); return value
    require(value["status"] == "producer_complete_provisional" and value["failure"] is None, "supervision_original")
    marker = value["marker"]
    require(type(marker) is dict and set(marker) == {"sha256", "stamp"} and type(marker["sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", marker["sha256"]) and type(marker["stamp"]) is list and len(marker["stamp"]) == 9
        and all(type(v) is int and 0 <= v <= 2 ** 64 for v in marker["stamp"])
        and marker["stamp"][2] == os.getuid() and tuple(marker["stamp"][4:6]) == (0o600, 1)
        and 0 < marker["stamp"][6] <= MAXIMUM_CONTROL_BYTES, "supervision_marker")
    return value


def _filtered_observation(raw, observer, digest, pid):
    value = _validated_observation(raw, observer, digest, pid)
    require(value["status"] == "producer_complete_provisional" and value["failure"] is None, "supervision_negative")
    return value["marker"]


def advisory_summary(error):
    row = _ADVISORIES.get(id(error))
    return json.loads(row[1]) if type(row) is tuple and row[0] is error else None


class _LoadTransaction:
    def __init__(self, head, remote, digest, observer):
        key = (head, remote, digest, observer["nonce"]); require(key in _PREPARED, "supervision_original")
        self.directory = None; self.fds, self.rows, self.nodes = [], [], []
        try:
            self.directory = _Directory(BOOTSTRAP, create=False)
            self.nodes = [(path, fd, _stamp(os.fstat(fd))) for path, fd, unused in self.directory.nodes]
            for name, pin, raw, digest_value in _PREPARED[key]:
                require(hash_bytes(raw) == digest_value, "supervision_original")
                before = _protected(os.stat(name, dir_fd=self.directory.fd, follow_symlinks=False)); require(before[:7] == pin, "supervision_original")
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory.fd); self.fds.append(fd)
                self.rows.append((name, fd, before, raw))
            self.audit()
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def audit(self):
        self.directory.check(); require(set(os.listdir(self.directory.fd)) == set(_Inputs.ROLES), "supervision_original")
        for path, fd, stamp in self.nodes: _same(_stamp(os.fstat(fd)), stamp); _same(_stamp(path.lstat()), stamp)
        for name, fd, stamp, raw in self.rows:
            _same(_stamp(os.fstat(fd)), stamp); _same(_stamp(os.stat(name, dir_fd=self.directory.fd, follow_symlinks=False)), stamp)
            os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "supervision_original"); _same(_stamp(os.fstat(fd)), stamp)
    def named(self):
        self.directory.named()
        for path, unused, stamp in self.nodes: _same(_stamp(path.lstat()), stamp)
        for name, unused, stamp, unused_raw in self.rows: _same(_stamp((self.directory.path / name).lstat()), stamp)
    def close(self):
        first = None
        try: _drain(self.fds)
        except BaseException as error: first = error
        if self.directory is not None:
            try: self.directory.close()
            except BaseException as error:
                if first is None: first = error
            try: self.named()
            except BaseException as error:
                if first is None: first = error
        if first is not None: raise first


def _association(raw, image, mount, attach_entities, absent=False):
    _component("native_association", 10)
    parsed = plistlib.loads(raw); images = parsed.get("images")
    require(type(images) is list and len(images) <= 256 and all(type(r) is dict for r in images), "native_proof_association")
    matching = [r for r in images if r.get("image-path") == str(image)]
    require(len(matching) == (0 if absent else 1), "native_proof_association")
    if absent: return None
    selected = matching[0]; require(not any(k in selected for k in ("shadow-path", "shadow-file")), "native_proof_association")
    entities = native._entities(selected); mounted = [r for r in entities if r[3] is not None]
    attached = [r for r in attach_entities if r[3] is not None]
    require(len(mounted) == len(attached) == 1 and mounted[0][0] == attached[0][0]
        and mounted[0][3] == attached[0][3] == str(mount)
        and {r[0] for r in attach_entities} <= {r[0] for r in entities}, "native_proof_association")
    native._mounted_descriptor(mounted[0]); native._mounted_descriptor(attached[0])
    device = mounted[0][0]; own_devices = {r[0] for r in entities} | {r[0] for r in attach_entities}
    device_counts = {name: 0 for name in own_devices}; mounts = 0
    for image in images:
        rows = image.get("system-entities", [])
        require(type(rows) is list and len(rows) <= 64 and all(type(r) is dict for r in rows), "native_proof_association")
        for name in own_devices: device_counts[name] += sum(r.get("dev-entry") == name for r in rows)
        mounts += sum(r.get("mount-point") == str(mount) for r in rows)
    require(mounts == 1 and all(count == 1 for count in device_counts.values()), "native_proof_association"); return device


def _tuples(value):
    if type(value) is list: return tuple(_tuples(item) for item in value)
    return value


class _RootReceipt:
    __slots__ = ()
    def __init__(self): raise SupervisionRefusal("REFUSED: supervision_factory")


_ROOT_RECEIPTS = {}


class _OriginalRead:
    """Independent reads compare reported ORIGINAL seals, never a new baseline."""
    def __init__(self, head, remote, digest, observer, producer_pid, marker):
        self.head, self.remote, self.digest, self.observer, self.producer_pid = head, remote, digest, observer, producer_pid
        self.directory = None; self.fds, self.files, self.anchors = [], [], []
        try:
            self.directory = _Directory(DOMAIN, create=False); self.path = self.directory.path; self.mount = self.path / "mount"; self.image = self.path / "backing.sparseimage"
            self.mount_fd = os.open("mount", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.directory.fd); self.fds.append(self.mount_fd)
            self.proof_path = self.mount / "proof"
            self.proof_fd = os.open("proof", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.mount_fd); self.fds.append(self.proof_fd)
            marker_raw = self.read(MARKER_ROLE, marker["stamp"], marker["sha256"], MAXIMUM_CONTROL_BYTES)
            self.marker = json.loads(marker_raw); m = self.marker
            expected_keys = {"schema", "runtime_head", "actual_remote", "policy_sha256", "spec_sha256", "nonce", "producer_pid", "authority",
                "child_pid", "actual_child_exit", "stdout_sha256", "kernel_exit_attested", "status", "inventory_sha256", "inventory_bytes",
                "inventory_original_stamp", "code_manifest_sha256", "durable_Main_receipt"}
            require(type(m) is dict and set(m) == expected_keys and marker_raw == canonical_json(m).encode()
                and m["schema"] == "si-native-supervision-marker-v1" and m["runtime_head"] == head and m["actual_remote"] == remote
                and m["policy_sha256"] == POLICY_SHA256 and m["spec_sha256"] == digest and m["nonce"] == observer["nonce"]
                and type(m["producer_pid"]) is int and m["producer_pid"] == producer_pid
                and type(m["child_pid"]) is int and 0 < m["child_pid"] < 2 ** 31 and m["actual_child_exit"] == 0
                and type(m["actual_child_exit"]) is int and m["kernel_exit_attested"] is False and m["durable_Main_receipt"] is False
                and m["status"] == "provisional_until_Root_kernel0" and m["authority"] == authority(), "supervision_marker")
            raw = self.read(INVENTORY_ROLE, m["inventory_original_stamp"], m["inventory_sha256"], MAXIMUM_NATIVE_BYTES)
            require(len(raw) == m["inventory_bytes"], "supervision_original"); self.inventory = json.loads(raw); inv = self.inventory
            require(type(inv) is dict and set(inv) == {"schema", "controls", "native", "code_manifest", "runtime_head", "policy_sha256", "nonce", "authority"}
                and raw == canonical_json(inv).encode() and inv["schema"] == "si-native-supervision-inventory-v1"
                and inv["runtime_head"] == head and inv["policy_sha256"] == POLICY_SHA256 and inv["nonce"] == observer["nonce"]
                and inv["authority"] == authority() and type(inv["code_manifest"]) is dict and set(inv["code_manifest"]) == set(CODE_FILES)
                and all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) for value in inv["code_manifest"].values())
                and hash_payload(inv["code_manifest"]) == m["code_manifest_sha256"], "supervision_original")
            controls = inv["controls"]
            require(type(controls) is list and len(controls) == len(POSITIVE_ROLES) - 2, "supervision_original")
            names = set(); self.raw_controls = {}
            for row in controls:
                require(type(row) is dict and set(row) == {"name", "sha256", "bytes", "original_stamp"}
                    and row["name"] in POSITIVE_ROLES - {MARKER_ROLE, INVENTORY_ROLE} and row["name"] not in names, "supervision_original")
                names.add(row["name"]); limit = MAXIMUM_NATIVE_BYTES if row["name"] in RAW_ROLES else MAXIMUM_CONTROL_BYTES
                body = self.read(row["name"], row["original_stamp"], row["sha256"], limit)
                require(len(body) == row["bytes"], "supervision_original"); self.raw_controls[row["name"]] = body
            require(names == POSITIVE_ROLES - {MARKER_ROLE, INVENTORY_ROLE}, "supervision_original")
            expected_stdout = b"".join(canonical_json(worker._worker_line(stage, m["child_pid"], producer_pid)).encode() + b"\n" for stage in ("entered", "completed"))
            require(self.raw_controls["stdout.jsonl"] == expected_stdout and hash_bytes(expected_stdout) == m["stdout_sha256"], "supervision_wait")
            expected_started = {"schema": "si-native-supervision-started-v1", "runtime_head": head, "actual_remote": remote,
                "policy_sha256": POLICY_SHA256, "spec_sha256": digest, "nonce": observer["nonce"], "producer_pid": producer_pid, "authority": authority()}
            expected_child = {**expected_started, "schema": "si-native-supervision-child-v1", "child_pid": m["child_pid"], "actual_child_exit": 0,
                "stdout_sha256": m["stdout_sha256"], "kernel_exit_attested": False, "status": "provisional_until_Root_kernel0"}
            require(self.raw_controls["run.started.json"] == canonical_json(expected_started).encode()
                and self.raw_controls["child.exit.provisional.json"] == canonical_json(expected_child).encode(), "supervision_wait")
            child = json.loads(self.raw_controls["child.exit.provisional.json"])
            require(type(child["actual_child_exit"]) is int and child["actual_child_exit"] == 0, "supervision_wait")
            self.native = inv["native"]; n = self.native
            native_keys = {"domain_original_identity", "main_original_seal", "proof_original_identity", "backing_original_identity", "mount_original_identity",
                "native_original_identity", "device_node_original_identity", "fresh_root_creation_identity", "system_original_metadata", "attach_original_entities", "original_command_output_sha256s"}
            require(type(n) is dict and set(n) == native_keys, "supervision_original")
            require(n["original_command_output_sha256s"] == {role: hash_bytes(self.raw_controls["native." + role + ".plist"]) for role in ("before", "create", "attach", "initial", "terminal")}, "supervision_original")
            require(_dir(os.fstat(self.directory.fd), True) == _tuples(n["domain_original_identity"])
                and _dir(os.fstat(self.mount_fd), True) == _tuples(n["mount_original_identity"])
                and _dir(os.fstat(self.proof_fd), True) == _tuples(n["proof_original_identity"]), "supervision_original")
            self.backing_fd = os.open("backing.sparseimage", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory.fd); self.fds.append(self.backing_fd)
            self.main_fd = os.open("main", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.mount_fd); self.fds.append(self.main_fd)
            self.attach_entities = native._entities(plistlib.loads(self.raw_controls["native.attach.plist"]))
            require(_tuples(n["attach_original_entities"]) == _tuples(self.attach_entities), "supervision_original")
            self.device = _association(self.raw_controls["native.terminal.plist"], self.image, self.mount, self.attach_entities)
            self.anchors = [(self.path, self.directory.fd, _tuples(n["domain_original_identity"])),
                (self.mount, self.mount_fd, _tuples(n["mount_original_identity"])), (self.proof_path, self.proof_fd, _tuples(n["proof_original_identity"]))]
            self.audit()
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def read(self, name, seal, digest, maximum):
        require(name in POSITIVE_ROLES and type(seal) is list and len(seal) == 9 and all(type(v) is int and v >= 0 for v in seal)
            and type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest), "supervision_original")
        seal = tuple(seal); info = os.stat(name, dir_fd=self.proof_fd, follow_symlinks=False)
        _same(_protected(info, maximum), seal)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.proof_fd); self.fds.append(fd)
        _same(_stamp(os.fstat(fd)), seal); raw = os.read(fd, maximum + 1)
        require(len(raw) == seal[6] and hash_bytes(raw) == digest, "supervision_original")
        _same(_stamp(os.fstat(fd)), seal); _same(_stamp(os.stat(name, dir_fd=self.proof_fd, follow_symlinks=False)), seal)
        self.files.append((name, fd, seal, raw)); return raw
    def native_audit(self):
        self._native_originals(self.mount_fd, self.backing_fd, self.main_fd, self.directory.fd)
    def _native_originals(self, mount_fd, backing_fd, main_fd, domain_fd):
        n = self.native; current = _native_statfs(mount_fd)
        require(native._mount_identity(current) == _tuples(n["native_original_identity"])
            and current["fstype"] == "apfs" and current["owner"] == os.getuid()
            and current["flags"] & native.MNT_LOCAL and current["flags"] & native.MNT_DONTBROWSE
            and not current["flags"] & (native.MNT_RDONLY | native.MNT_IGNORE_OWNERSHIP)
            and current["mounted_on"] == str(self.mount) and current["mounted_from"] == self.device, "supervision_original")
        require(_device_node(self.device, os.fstat(mount_fd).st_dev) == _tuples(n["device_node_original_identity"]), "supervision_original")
        require(type(current["bsize"]) is int and current["bsize"] > 0 and type(current["blocks"]) is int
            and 4 * 1024 ** 3 <= current["blocks"] * current["bsize"] <= VIRTUAL_BYTES
            and type(current["bavail"]) is int and current["bavail"] * current["bsize"] >= 4 * 1024 ** 3, "supervision_original")
        require(native._backing(os.fstat(backing_fd)) == native._backing(self.image.lstat()) == _tuples(n["backing_original_identity"]), "supervision_original")
        require(_dir(os.fstat(main_fd), True) == _dir((self.mount / "main").lstat(), True), "supervision_original")
        require(native._fresh_root_identity(os.fstat(mount_fd)) == _tuples(n["fresh_root_creation_identity"])
            and os.fstat(mount_fd).st_dev != os.fstat(domain_fd).st_dev, "supervision_original")
        expected_names = {"proof", "main"} | ({".fseventsd"} if n["system_original_metadata"] is not None else set())
        require(set(os.listdir(domain_fd)) == {"backing.sparseimage", "mount"} and set(os.listdir(mount_fd)) == expected_names, "supervision_original")
        if n["system_original_metadata"] is not None:
            info = os.stat(".fseventsd", dir_fd=mount_fd, follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700
                and info.st_gid == os.fstat(mount_fd).st_gid and _stamp(info)[:6] == _tuples(n["system_original_metadata"]), "supervision_original")
        require(_stamp(os.fstat(main_fd)) == _stamp((self.mount / "main").lstat()) == _tuples(n["main_original_seal"])
            and not os.listdir(main_fd), "supervision_original")
    def current_association(self, clock):
        result = _native_command([native.HDIUTIL, "info", "-plist"], min(COMMAND_SECONDS, clock.check()))
        require(type(result.returncode) is int and result.returncode == 0 and type(result.stdout) is bytes and 0 < len(result.stdout) <= MAXIMUM_NATIVE_BYTES, "supervision_original")
        require(_association(result.stdout, self.image, self.mount, self.attach_entities) == self.device, "supervision_original")
        self.native_audit()
    def audit(self):
        self.directory.check(); self.native_audit(); self.audit_local()
    def audit_local(self):
        for path, fd, pin in self.anchors: require(path.resolve() == path and _dir(os.fstat(fd), True) == _dir(path.lstat(), True) == pin, "supervision_original")
        require(set(os.listdir(self.proof_fd)) == POSITIVE_ROLES, "supervision_negative")
        for name, fd, seal, raw in self.files:
            _same(_stamp(os.fstat(fd)), seal); _same(_stamp((self.proof_path / name).lstat()), seal)
            os.lseek(fd, 0, os.SEEK_SET); require(os.read(fd, len(raw) + 1) == raw, "supervision_original"); _same(_stamp(os.fstat(fd)), seal)
    def _named_originals(self):
        self.directory.named()
        for path, unused, pin in self.anchors: require(path.resolve() == path and _dir(path.lstat(), True) == pin, "supervision_original")
        n = self.native
        require(native._backing(self.image.lstat()) == _tuples(n["backing_original_identity"])
            and native._fresh_root_identity(self.mount.lstat()) == _tuples(n["fresh_root_creation_identity"]), "supervision_original")
        require(set(os.listdir(self.path)) == {"backing.sparseimage", "mount"}
            and set(os.listdir(self.mount)) == {"proof", "main"} | ({".fseventsd"} if n["system_original_metadata"] is not None else set()), "supervision_original")
        if n["system_original_metadata"] is not None:
            info = (self.mount / ".fseventsd").lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700
                and info.st_gid == self.mount.lstat().st_gid and info.st_dev == self.mount.lstat().st_dev
                and _stamp(info)[:6] == _tuples(n["system_original_metadata"]), "supervision_original")
        require(set(os.listdir(self.proof_path)) == POSITIVE_ROLES, "supervision_negative")
        for name, unused, seal, unused_raw in self.files: _same(_stamp((self.proof_path / name).lstat()), seal)
        _same(_stamp((self.mount / "main").lstat()), _tuples(n["main_original_seal"]))
        require(not os.listdir(self.mount / "main"), "supervision_original")
    def named(self):
        self._named_originals(); fds = []; primary = None
        try:
            # These strict independent verification reads compare ONLY original
            # producer pins; they issue no creator capability or new baseline.
            domain_fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); fds.append(domain_fd)
            require(_dir(os.fstat(domain_fd), True) == _tuples(self.native["domain_original_identity"]), "supervision_original")
            mount_fd = os.open("mount", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=domain_fd); fds.append(mount_fd)
            require(_dir(os.fstat(mount_fd), True) == _tuples(self.native["mount_original_identity"]), "supervision_original")
            backing_fd = os.open("backing.sparseimage", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=domain_fd); fds.append(backing_fd)
            main_fd = os.open("main", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=mount_fd); fds.append(main_fd)
            self._native_originals(mount_fd, backing_fd, main_fd, domain_fd)
            self._named_originals()
        except BaseException as error: primary = error; raise
        finally:
            try: _drain(fds)
            except BaseException:
                if primary is None: raise
        self._named_originals()
    def close(self):
        first = None
        try: _drain(self.fds)
        except BaseException as error: first = error
        if self.directory is not None:
            try: self.directory.close()
            except BaseException as error:
                if first is None: first = error
        if first is not None: raise first



def _root_context_snapshot(reader, code, config, load):
    """Finite exact original contexts retained after their successful closure."""
    require(type(reader) is _OriginalRead and type(code) is _Code7 and type(config) is _Inputs
        and type(load) is _LoadTransaction and not reader.fds and not code.fds and not load.fds
        and reader.directory.closed and config.directory.closed and load.directory.closed, "supervision_factory")
    return canonical_json({
        "reader": {"head": reader.head, "remote": reader.remote, "digest": reader.digest, "observer": reader.observer,
            "producer_pid": reader.producer_pid, "marker": reader.marker, "inventory": reader.inventory,
            "anchors": [[str(path), fd, pin] for path, fd, pin in reader.anchors],
            "files": [[name, fd, seal, hash_bytes(raw), len(raw)] for name, fd, seal, raw in reader.files],
            "native": reader.native, "device": reader.device, "attach_entities": reader.attach_entities},
        "code": {"head": code.head, "remote": code.remote, "manifest": code.manifest,
            "rows": {name: [fd, seal, hash_bytes(raw), len(raw)] for name, (fd, seal, raw) in code.rows.items()}},
        "config": {name: [pin, hash_bytes(raw), len(raw), digest] for name, (pin, raw, digest) in config.rows.items()},
        "load": {"rows": [[name, fd, seal, hash_bytes(raw), len(raw)] for name, fd, seal, raw in load.rows],
            "nodes": [[str(path), fd, seal] for path, fd, seal in load.nodes]}})


def _target(): return "gui/" + str(os.getuid()) + "/" + LABEL


def _service_arguments(role):
    arguments = {"query": [LAUNCHCTL, "print", _target()],
        "load": [LAUNCHCTL, "bootstrap", "gui/" + str(os.getuid()), str(ROOT / PARENT / BOOTSTRAP / "job.plist")],
        "start": [LAUNCHCTL, "kickstart", "-p", _target()]}
    require(type(role) is str and role in arguments, "supervision_arguments"); return arguments[role]


def _launch_service(role):
    return subprocess.run(_service_arguments(role), cwd=ROOT, env=worker._environment(), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, check=False, timeout=30)


def _kernel_metadata(raw):
    require(type(raw) is bytes and len(raw) <= 65536, "supervision_kernel")
    text = raw.decode("utf-8")
    require(text.splitlines()[:1] == [_target() + " = {"], "supervision_kernel")
    require(re.findall(r"(?m)^\tpath = ([^\r\n]+)$", text) == [str(ROOT / PARENT / BOOTSTRAP / "job.plist")], "supervision_kernel")
    values = {}
    for key, expression in (("state", r"[a-z ]+"), ("runs", r"[0-9]+"), ("active count", r"[0-9]+"), ("pid", r"[0-9]+")):
        rows = re.findall(r"(?m)^\t" + key + " = (" + expression + r")[ \t]*$", text)
        require(len(rows) <= 1 and len(rows) == len(re.findall(r"(?m)^\t" + key + " =", text)), "supervision_kernel")
        values[key] = rows[0] if rows else None
    require(all(values[key] is not None for key in ("state", "runs", "active count"))
        and values["state"] in {"running", "not running"}, "supervision_kernel")
    exits = re.findall(r"(?m)^\tlast exit code = ([^\r\n]+)$", text)
    require(len(exits) <= 1 and len(exits) == len(re.findall(r"(?m)^\tlast exit code =", text)), "supervision_kernel")
    code = None; never = exits == ["(never exited)"]
    if exits and not never:
        match = re.fullmatch(r"(-?[0-9]+)(?:: ([A-Z_]+))?[ \t]*", exits[0]); require(match is not None, "supervision_kernel")
        code = int(match[1]); require(not match[2] or startup._SYSEXITS.get(code) == match[2], "supervision_kernel")
    result = {"state": values["state"], "runs": int(values["runs"]), "active_count": int(values["active count"]),
        "pid": int(values["pid"]) if values["pid"] is not None else None, "exit": code, "pending": never or code is None}
    require(result["runs"] in (0, 1) and result["active_count"] in (0, 1)
        and (result["pid"] is None or 0 < result["pid"] < 2 ** 31)
        and (code is None or -32768 <= code <= 32767), "supervision_kernel")
    return result


def _query_service(head):
    _guard(head, startup.REMOTE)
    result = _launch_service("query")
    require(type(result) is subprocess.CompletedProcess and type(result.returncode) is int
        and type(result.args) is list and all(type(v) is str for v in result.args) and result.args == _service_arguments("query")
        and type(result.stdout) is bytes and len(result.stdout) <= 65536, "supervision_kernel")
    if result.returncode == 113: return None
    require(result.returncode == 0, "supervision_kernel"); value = _kernel_metadata(result.stdout)
    row = (value, result, tuple(result.args), result.returncode, result.stdout, hash_bytes(result.stdout), canonical_json(value), object())
    _KERNEL_ORIGINS[id(value)] = row; return value


def _kernel_origin(value):
    row = _KERNEL_ORIGINS.get(id(value))
    require(type(row) is tuple and len(row) == 8 and row[0] is value and type(value) is dict, "supervision_factory")
    result = row[1]
    require(type(result) is subprocess.CompletedProcess and type(result.args) is list and all(type(v) is str for v in result.args)
        and tuple(result.args) == row[2] == tuple(_service_arguments("query"))
        and type(result.returncode) is int and result.returncode == row[3] == 0
        and type(result.stdout) is bytes and result.stdout == row[4] and hash_bytes(result.stdout) == row[5]
        and canonical_json(value) == row[6] and _kernel_metadata(result.stdout) == value, "supervision_changed")
    return row


def _never_started(kernel):
    require(type(kernel) is dict and kernel["runs"] == 0 and kernel["state"] == "not running"
        and kernel["active_count"] == 0 and kernel["pid"] is None and kernel["exit"] is None, "supervision_kernel")


def _terminal(kernel):
    return type(kernel) is dict and kernel["runs"] == 1 and kernel["state"] == "not running" and kernel["active_count"] == 0 and kernel["pid"] is None and type(kernel["exit"]) is int and kernel["pending"] is False


def _read_private(fd, raw):
    try: block = os.read(fd, 4096)
    except BlockingIOError: return raw, False
    if not block: return raw, True
    return (raw + block)[:65536 + 4096], False


def _drain_private(fd, raw):
    for unused in range(32):
        raw, done = _read_private(fd, raw)
        if done: return raw
        try: block = os.read(fd, 4096)
        except BlockingIOError: return raw
        if not block: return raw
        raw = (raw + block)[:65536 + 4096]
    raise SupervisionRefusal("REFUSED: supervision_unknown")


def coordinate_registered(head, remote):
    registered()
    with _source_denied(): return _coordinate(head, remote)


def _coordinate(head, remote):
    clock = _Clock(); code = config_directory = config = transaction = root_read = load_witness = None
    master = slave = None; raw = b""; loaded = started = start_attempt = False; kernel = None; failure = None
    scope = object(); receipt = None; public = None
    try:
        _phase("current_code"); _guard(head, remote); code = _Code7(head, remote, clock)
        require(_query_service(head) is None, "supervision_kernel")
        master, slave = os.openpty(); os.set_blocking(master, False)
        settings = startup.termios.tcgetattr(slave); settings[1] &= ~startup.termios.ONLCR; settings[3] &= ~startup.termios.ECHO
        startup.termios.tcsetattr(slave, startup.termios.TCSANOW, settings)
        observer = {"nonce": secrets.token_hex(16), "terminal": list(startup._tty_pin(slave)), "slave_path": os.ttyname(slave)}
        startup._tty_check(slave, observer)
        digest = prepare_bootstrap(head, remote, observer)["spec_sha256"]
        _guard(head, remote); require(_query_service(head) is None, "supervision_kernel")
        _phase("root_load"); transaction = _LoadTransaction(head, remote, digest, observer)
        startup._tty_check(slave, observer); require(_launch_service("load").returncode == 0, "supervision_kernel"); loaded = True
        transaction.audit(); startup._tty_check(slave, observer); transaction.close(); load_witness = transaction; transaction = None
        kernel = _query_service(head); _never_started(kernel)
        raw = _drain_private(master, raw); _guard(head, remote)
        config_directory, config = _read_config(head, remote, digest, observer, code.manifest)
        kernel = _query_service(head); _never_started(kernel); raw = b""; startup._tty_check(slave, observer)
        start_attempt = True; kernel = None
        result = _launch_service("start"); require(result.returncode == 0 and re.fullmatch(rb"[1-9][0-9]{0,9}\n?", result.stdout), "supervision_kernel")
        producer_pid = int(result.stdout); require(producer_pid < 2 ** 31, "supervision_kernel"); started = True
        _phase("root_observation")
        for unused in range(300):
            raw, unused_eof = _read_private(master, raw)
            kernel = None; kernel = _query_service(head)
            require(kernel is not None and (kernel["pid"] is None or kernel["pid"] == producer_pid), "supervision_kernel")
            if _terminal(kernel): break
            clock.check(); time.sleep(1)
        require(_terminal(kernel), "supervision_unknown")
        raw = _drain_private(master, raw); startup._tty_check(slave, observer)
        try: observed = _validated_observation(raw, observer, digest, producer_pid)
        except BaseException: observed = {"status": "observer_unavailable", "failure": None}
        if kernel["exit"] != 0 or observed["status"] != "producer_complete_provisional":
            negative = SupervisionRefusal("REFUSED: supervision_negative")
            advisory = {"status": "negative_source_free_native_supervision", "target_pid": producer_pid, "actual_kernel_exit": kernel["exit"],
                "producer_observation": {"status": observed["status"], "failure": observed["failure"]}, "authority": authority()}
            _ADVISORIES[id(negative)] = negative, canonical_json(advisory); raise negative
        original_marker = _filtered_observation(raw, observer, digest, producer_pid)
        _phase("root_verification"); root_read = _OriginalRead(head, remote, digest, observer, producer_pid, original_marker)
        require(root_read.inventory["code_manifest"] == code.manifest, "supervision_code")
        root_read.current_association(clock); code.audit(); _guard(head, remote); config.audit()
        # No Git/native command after this last original-only audit.
        root_read.audit(); clock.check()
        public = {"status": "closed_source_free_native_supervision_in_memory_only", "runtime_head": head, "actual_remote": remote,
            "policy_sha256": POLICY_SHA256, "target_pid": producer_pid, "actual_kernel_exit": 0, "actual_child_exit": 0,
            "marker_sha256": original_marker["sha256"], "durable_Main_receipt": False, "sourceAUTH_blocked": True, "authority": authority()}
    except BaseException as error:
        failure = error; failure_summary(error)
        if start_attempt and not _terminal(kernel) or loaded and kernel is None:
            state = {"master": master, "slave": slave, "code": code, "config_directory": config_directory, "config": config,
                "transaction": transaction, "load_witness": load_witness, "root_read": root_read, "raw": raw, "failure": error,
                "start_attempted": start_attempt, "start_PID_validated": started, "kernel": kernel, "scope": scope}
            master = slave = None; code = config_directory = config = transaction = root_read = None
            try: _hold(state)
            except BaseException: raise error
    finally:
        first = failure; _phase("root_cleanup")
        for obj in (transaction, root_read, config, config_directory, code):
            if obj is not None:
                try: obj.close()
                except BaseException as error:
                    if first is None: first = error; failure_summary(error)
        for fd in (slave, master):
            if fd is not None:
                try: os.close(fd)
                except BaseException as error:
                    if first is None: first = error; failure_summary(error)
        failure = first
    if failure is not None: raise failure
    config.audit(named=True); root_read.named(); code.named(); clock.check()
    # Exact Root-issued registry witness exists only AFTER the full conjunction.
    original_kernel = _kernel_origin(kernel)
    require(_terminal(kernel) and kernel["exit"] == 0, "supervision_kernel")
    contexts = (root_read, code, config, load_witness); context_snapshot = _root_context_snapshot(*contexts)
    receipt = object.__new__(_RootReceipt); _ROOT_RECEIPTS[receipt] = (scope, canonical_json(public), original_kernel, contexts, context_snapshot, object())
    value = object.__new__(ClosedNativeSupervision); row = (value, canonical_json(public), receipt, scope)
    value._anchor = row; _CLOSED[id(value)] = row; return value


def main(argv=None):
    parser = argparse.ArgumentParser(description="One registered source-free typed native-supervision proof")
    parser.add_argument("command", choices=("prepare-proof", "run-proof", "coordinate-proof", "capture"))
    parser.add_argument("--head"); parser.add_argument("--remote"); parser.add_argument("--spec-sha256"); parser.add_argument("--observer")
    args = parser.parse_args(argv); observer = None
    try:
        if args.command == "capture": raise SupervisionRefusal("REFUSED: supervision_source_refused")
        if args.command == "run-proof":
            observer = _Observer(json.loads(args.observer), args.spec_sha256)
            result = run_registered(args.head, args.remote, args.spec_sha256, observer.config); observer.emit(result=result)
        elif args.command == "prepare-proof": print(canonical_json(prepare_bootstrap(args.head, args.remote, json.loads(args.observer))))
        else: print(canonical_json(coordinate_registered(args.head, args.remote).public_summary()))
        return 0
    except BaseException as error:
        if observer is not None:
            try: observer.emit(error=error)
            except BaseException: pass
        elif args.command != "run-proof": print(canonical_json({"status": "refused", "failure": failure_summary(error), "producer_diagnostic": advisory_summary(error), "authority": authority()}))
        return 2


if __name__ == "__main__": raise SystemExit(main())
