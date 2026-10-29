"""One source-free launchd parent creates and retains its own APFS proof domain.

Host files are bootstrap bytes, never transferred creation capabilities. This
separately registered experiment does not adopt any old image or proof. Every
producer record stays provisional until Main independently observes kernel
exit0, original child wait0 and all original controls without a negative.
"""
import argparse
import errno
import json
import math
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_count_process_supervisor as worker
from scripts import short_interest_isolated_custody_volume as native

ROOT = worker.ROOT
MODULE = "scripts.short_interest_count_native_supervisor"
DRIVER = "scripts/short_interest_count_native_supervisor.py"
PARENT = Path("artifacts/short_interest")
BOOTSTRAP = "count-process-supervisor-native-bootstrap-v1"
DOMAIN = "count-process-supervisor-native-domain-v1"
LABEL = "com.openai.codex.short-interest-native-process-proof-v1"
POLICY_SHA256 = "9df40f358d3f48b66e605b2fe768646e90e2f2b47892a05788453e36e9a25484"
CODE_FILES = ("data/__init__.py", "data/hashing.py", DRIVER,
    "scripts/short_interest_count_process_supervisor.py", "scripts/short_interest_isolated_custody_volume.py")
MAXIMUM_SECONDS, COMMAND_SECONDS, VIRTUAL_BYTES = 300, 120, 8 * 1024 ** 3
MAXIMUM_NATIVE_BYTES, MAXIMUM_CONTROL_BYTES = 4 * 1024 ** 2, 4096
RAW_ROLES = ("native.before.plist", "native.create.plist", "native.attach.plist", "native.initial.plist", "native.terminal.plist")
PRIVATE_ROLES = ("child.failure.buffers.private.json", "child.remaining.pipe.private.json")
INVENTORY_ROLE = "metadata.inventory.private.json"
CONTROL_ROLES = ("run.started.json", "stdout.jsonl", "child.exit.provisional.json", "run.completed.provisional.json", "run.refused.json", "child.late.exit.negative.json")
ROLES = RAW_ROLES + PRIVATE_ROLES + CONTROL_ROLES + (INVENTORY_ROLE,)
_COLLECT_FUNCTION, _COLLECT_CODE = worker._collect, worker._collect.__code__
_BUFFER_ORIGINS = {}
_PRESERVATION_ORIGINS = {}
_USED, _STAGE = False, "registration"
_HELD, _RESULTS, _FAILURES, _FIELDS = [], {}, {}, {}
_STAGES = frozenset("registration bootstrap current_code native_creation native_association output_creation child_launch child_observation terminal_code terminal_native provisional_publication original_audit cleanup named_audit".split())
_CODES = frozenset("native_proof_unregistered native_proof_source_refused native_proof_arguments native_proof_clock native_proof_deadline native_proof_path native_proof_protection native_proof_membership native_proof_exists native_proof_write native_proof_stamp native_proof_code native_proof_command native_proof_plist native_proof_association native_proof_mount native_proof_backing native_proof_capacity native_proof_already_used native_proof_wait native_proof_result_factory native_proof_result_changed".split())
_ERRNOS = {getattr(errno, n): n for n in ("EACCES", "EPERM", "ENOENT", "EEXIST", "ENOSPC", "EIO", "EBADF", "EMFILE", "ENFILE", "EROFS", "EINTR", "EAGAIN")}
_STAMP_NAMES = ("dev", "ino", "uid", "gid", "mode", "nlink", "size", "mtime_ns", "ctime_ns")


class NativeProofRefusal(ValueError): pass


def require(value, code):
    if not value: raise NativeProofRefusal("REFUSED: " + code)


def authority():
    return {"source_free_native_lifetime_proof_only": True, "provider_HTTP": 0, "credential_reads": 0,
        "source_STARTs": 0, "source_bytes": 0, "new_source_claims": 0, "source_dispatch_authority": False,
        "old_custody_repaired": False, "source_admitted": False, "budget_release_authority": False,
        "ready_for_backtest": False, "QC_or_Safari": False, "qc_attempts": 0}


def policy():
    return {"schema": "si-native-process-proof-policy-v1", "root": str(ROOT), "parent": str(PARENT),
        "bootstrap": BOOTSTRAP, "domain": DOMAIN, "label": LABEL, "code_files": list(CODE_FILES),
        "virtual_bytes": VIRTUAL_BYTES, "whole_seconds": MAXIMUM_SECONDS, "command_seconds": COMMAND_SECONDS,
        "native_output_bytes": MAXIMUM_NATIVE_BYTES, "control_bytes": MAXIMUM_CONTROL_BYTES,
        "inventory_bytes": MAXIMUM_NATIVE_BYTES, "private_failure_bytes": 65536,
        "native_output_limit_kind": "post_capture_acceptance_of_fixed_local_command_output_not_hard_capture_memory_bound",
        "roles": list(ROLES), "worker_policy_sha256": worker.PROOF_POLICY_SHA256,
        "worker": "unchanged_two_second_worker_original_collect_wait_within_five_seconds",
        "host": "bootstrap_spec_job_bytes_only_no_host_creation_stamp_admission_stdout_stderr_devnull",
        "native": "new_SPARSE_APFS_same_parent_creator_original_FDs_global_unique_image_device_mount_no_shadow_no_detach_remount_retry_or_cleanup",
        "inner": "original_O_EXCL0600_singlelink_full9_stamp_and_exact_readback_never_reseal_adopt_or_ctime_relax",
        "inventory": "original_sealed_preceding_controls_hash_bytes_full9_stamps_native_original_pins_code5_manifest_inventory_and_marker_excluded_from_roster_marker_binds_original_inventory_body_and_seal",
        "backing": "mutable_container_original_inode0600_singlelink_not_immutable_evidence_seal",
        "closure": "all_code_Git_native_callbacks_then_original_control_membership_clock_audits_all_FDs_closed_final_original_named_seals_no_reopen",
        "unknown": "retain_original_child_code_bootstrap_volume_output_FDs_no_kill_restart_or_positive_result",
        "late_negative": "exact_original_collect_failure_frame_all_present_pending_output_line_block_bytes_plus_remaining_pipe_and_partial_log_preserved_before_original_wait_late_exit_negative_only_otherwise_hold_all_contexts",
        "kernel_exit": "all_producer_records_provisional_until_Main_independent_actual_kernel_exit0_and_no_negative",
        "authority": authority()}


def registered():
    require(re.fullmatch(r"[0-9a-f]{64}", POLICY_SHA256) is not None and hash_payload(policy()) == POLICY_SHA256
        and (MAXIMUM_SECONDS, COMMAND_SECONDS, VIRTUAL_BYTES, MAXIMUM_NATIVE_BYTES, MAXIMUM_CONTROL_BYTES)
        == (300, 120, 8589934592, 4194304, 4096), "native_proof_unregistered")
    native._platform()  # Pure SDK/descriptor capability check before any effect.


def _phase(name):
    global _STAGE
    require(name in _STAGES, "native_proof_arguments"); _STAGE = name


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode),
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _same(actual, original):
    if actual != original:
        error = NativeProofRefusal("REFUSED: native_proof_stamp")
        if type(actual) is tuple and type(original) is tuple and len(actual) == len(original) == 9:
            _FIELDS[id(error)] = error, tuple(n for n, a, b in zip(_STAMP_NAMES, actual, original) if a != b)
        raise error


def failure_summary(error):
    previous = _FAILURES.get(id(error))
    if previous is not None and previous[0] is error: return json.loads(previous[1])
    code = None
    if type(error) is NativeProofRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((n for n in _CODES if args[0] == "REFUSED: " + n), None)
    upstream = worker.failure_summary(error) if type(error) is worker.ProcessSupervisorRefusal else native.failure_summary(error)
    number = OSError.errno.__get__(error, OSError) if isinstance(error, OSError) else None
    name = _ERRNOS.get(number) if type(number) is int else None
    fields = _FIELDS.get(id(error))
    detail = {"stage": _STAGE, "category": "local_contract_refusal" if code or upstream["contract_code"] else "local_os_error" if name else "unknown_local_error",
        "contract_code": code, "upstream_contract_code": upstream["contract_code"], "errno_name": name or upstream.get("errno_name"),
        "mismatching_fields": list(fields[1]) if fields is not None and fields[0] is error else []}
    _FAILURES[id(error)] = error, canonical_json(detail)
    return detail


def _close(fd, primary=None):
    try: os.close(fd)
    except BaseException:
        if primary is None: raise


def _drain(fds):
    first = None
    for fd in reversed(fds):
        try: os.close(fd)
        except BaseException as error:
            if first is None: first = error
    fds.clear()
    if first is not None: raise first


def _write(fd, raw):
    offset = 0
    while offset < len(raw):
        n = os.write(fd, memoryview(raw)[offset:])
        require(type(n) is int and 0 < n <= len(raw) - offset, "native_proof_write"); offset += n


def _dir(info, private=False):
    mode = stat.S_IMODE(info.st_mode)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
        and (mode == 0o700 if private else not mode & 0o022), "native_proof_protection")
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, mode


class _Clock:
    def __init__(self): self.clock = time.monotonic; self.begin = self.last = self.clock(); self.check()
    def check(self):
        now = self.clock()
        require(type(now) in (int, float) and math.isfinite(now) and 0 <= self.begin <= self.last <= now,
            "native_proof_clock")
        require(now - self.begin <= MAXIMUM_SECONDS, "native_proof_deadline"); self.last = now
        return MAXIMUM_SECONDS - (now - self.begin)


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
                    else: raise NativeProofRefusal("REFUSED: native_proof_exists")
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


class _Code:
    def __init__(self, head, remote, clock):
        self.head, self.remote, self.clock, self.rows, self.fds = head, remote, clock, {}, []
        try:
            for name in CODE_FILES:
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
        for name, (fd, stamp, original) in self.rows.items():
            worker._guard(self.head, self.remote); self.clock.check()
            require((ROOT / name).resolve() == ROOT / name, "native_proof_path")
            _same(_stamp(os.fstat(fd)), stamp); _same(_stamp((ROOT / name).lstat()), stamp)
            os.lseek(fd, 0, os.SEEK_SET); raw = os.read(fd, 1024 ** 2 + 1)
            require(raw == worker._git(["show", self.head + ":" + name]), "native_proof_code")
            if not initial: require(raw == original, "native_proof_code")
            _same(_stamp(os.fstat(fd)), stamp); self.rows[name] = fd, stamp, raw; result[name] = hash_bytes(raw)
        self.clock.check(); return result
    def named(self):
        for name, (unused, stamp, unused_raw) in self.rows.items():
            require((ROOT / name).resolve() == ROOT / name, "native_proof_path")
            _same(_stamp((ROOT / name).lstat()), stamp)
    def close(self): _drain(self.fds)


def _spec(head, remote, manifest):
    return {"schema": "si-native-process-bootstrap-v1", "runtime_head": head, "actual_remote": remote,
        "policy_sha256": POLICY_SHA256, "code_manifest": manifest, "domain": DOMAIN, "authority": authority()}


def build_launchd_plist(head, remote, digest):
    require(all(type(v) is str and re.fullmatch(r"[0-9a-f]{40}", v) for v in (head, remote))
        and type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest), "native_proof_arguments")
    return {"Label": LABEL, "ProgramArguments": [worker.PYTHON, "-B", "-m", MODULE, "run-proof",
        "--head", head, "--remote", remote, "--bootstrap-sha256", digest], "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": worker._environment(), "RunAtLoad": True, "KeepAlive": False,
        "StandardOutPath": "/dev/null", "StandardErrorPath": "/dev/null"}


def prepare_bootstrap(head, remote):
    registered(); clock = _Clock(); worker._guard(head, remote)
    code = directory = files = None; primary = None
    try:
        code = _Code(head, remote, clock); raw = canonical_json(_spec(head, remote, code.manifest)).encode(); digest = hash_bytes(raw)
        directory = _Directory(BOOTSTRAP, create=True)
        files = _Files(directory.fd, directory.parent, directory.path, directory.check, ("launch.spec.json", "job.plist"))
        files.write("launch.spec.json", raw); files.write("job.plist", plistlib.dumps(build_launchd_plist(head, remote, digest), sort_keys=True))
        code.audit(); worker._guard(head, remote); files.audit(); clock.check()
    except BaseException as error: primary = error; raise
    finally:
        first = primary
        for obj in (files, directory, code):
            if obj is not None:
                try: obj.close()
                except BaseException as error:
                    if first is None: first = error
        if primary is None and first is not None: raise first
    files.named(); directory.named(); code.named(); clock.check()
    return {"schema": "si-native-process-bootstrap-prepared-v1", "bootstrap_sha256": digest,
        "job_submitted": False, "native_created": False, "authority": authority()}


def _read_bootstrap(head, remote, manifest, digest):
    directory = _Directory(BOOTSTRAP, create=False); rows = []; primary = None
    directory.bootstrap_rows = []
    try:
        expected = {"launch.spec.json": canonical_json(_spec(head, remote, manifest)).encode(),
            "job.plist": plistlib.dumps(build_launchd_plist(head, remote, digest), sort_keys=True)}
        require(set(os.listdir(directory.fd)) == set(expected) and hash_bytes(expected["launch.spec.json"]) == digest,
            "native_proof_code")
        for name, raw in expected.items():
            info = os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_nlink == 1 and info.st_size == len(raw), "native_proof_protection")
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory.fd); rows.append(fd)
            before = _stamp(info); _same(_stamp(os.fstat(fd)), before)
            require(os.read(fd, len(raw) + 1) == raw, "native_proof_code")
            _same(_stamp(os.fstat(fd)), before)
            directory.bootstrap_rows.append((name, fd, before, raw))
        _bootstrap_audit(directory)
        return directory, rows
    except BaseException as error:
        primary = error
        try: _drain(rows)
        except BaseException: pass
        try: directory.close()
        except BaseException: pass
        raise primary


def _bootstrap_audit(directory, *, named=False):
    if named: directory.named()
    else: directory.check()
    require(set(os.listdir(directory.path if named else directory.fd)) == {"launch.spec.json", "job.plist"},
        "native_proof_membership")
    for name, fd, stamp, raw in directory.bootstrap_rows:
        _same(_stamp((directory.path / name).lstat()), stamp)
        if not named:
            _same(_stamp(os.fstat(fd)), stamp); os.lseek(fd, 0, os.SEEK_SET)
            require(os.read(fd, len(raw) + 1) == raw, "native_proof_code"); _same(_stamp(os.fstat(fd)), stamp)


class _Volume:
    def __init__(self, clock):
        native._platform()
        clock.check()
        self.clock, self.directory, self.fds, self.origins = clock, _Directory(DOMAIN, create=True), [], {}
        self.path = self.directory.path; self.image = self.path / "backing.sparseimage"; self.mount = self.path / "mount"
        self.mount_fd = None
        try:
            host = native._native_statfs(self.directory.fd)
            require(host["flags"] & native.MNT_LOCAL and not host["flags"] & native.MNT_IGNORE_OWNERSHIP
                and host["bsize"] * host["bavail"] >= VIRTUAL_BYTES + 1024 ** 3, "native_proof_capacity")
            self.host_device = os.fstat(self.directory.fd).st_dev
            self.command("before", "info"); self._association(self.origins["before"], absent=True)
            self.command("create", "create")
            require(set(os.listdir(self.directory.fd)) == {"backing.sparseimage"}, "native_proof_membership")
            fd = os.open("backing.sparseimage", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory.fd)
            self.fds.append(fd); self.backing_fd = fd
            require(stat.S_ISREG(os.fstat(fd).st_mode) and os.fstat(fd).st_uid == os.getuid() and os.fstat(fd).st_nlink == 1,
                "native_proof_backing"); os.fchmod(fd, 0o600); self.backing_pin = native._backing(os.fstat(fd))
            os.mkdir("mount", 0o700, dir_fd=self.directory.fd)
            self.under_fd = os.open("mount", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.directory.fd)
            self.fds.append(self.under_fd); self.under_pin = _dir(os.fstat(self.under_fd), True)
            require(not os.listdir(self.under_fd), "native_proof_membership")
            self.command("attach", "attach"); self.attach_entities = native._entities(plistlib.loads(self.origins["attach"]))
            self.command("initial", "info"); self.device = self._association(self.origins["initial"])
            self.mount_fd = os.open("mount", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.directory.fd)
            self.fds.append(self.mount_fd); info = os.fstat(self.mount_fd)
            self.creation = native._fresh_root_identity(info); current = native._native_statfs(self.mount_fd)
            self.mount_native = native._mount_identity(current); self.node = native._node_pin(self.device, info.st_dev)
            self._native(current)
            require(type(current["bsize"]) is int and current["bsize"] > 0
                and type(current["blocks"]) is int and 4 * 1024 ** 3 <= current["blocks"] * current["bsize"] <= VIRTUAL_BYTES
                and type(current["bavail"]) is int and current["bavail"] * current["bsize"] >= 4 * 1024 ** 3,
                "native_proof_capacity")
            require(info.st_dev != self.host_device and self.creation == native._fresh_root_identity(self.mount.lstat()), "native_proof_mount")
            os.fchmod(self.mount_fd, 0o700); os.fsync(self.mount_fd); self.mount_pin = _dir(os.fstat(self.mount_fd), True)
            require(native._fresh_root_identity(os.fstat(self.mount_fd)) == self.creation, "native_proof_mount")
            self.system = None
            require(set(os.listdir(self.mount_fd)) <= {".fseventsd"}, "native_proof_membership")
            if ".fseventsd" in os.listdir(self.mount_fd): self.system = self._system()
            self.check()
        except BaseException:
            try: self.close()
            except BaseException: pass
            raise
    def arguments(self, verb):
        if verb == "create": return [native.HDIUTIL, "create", "-type", "SPARSE", "-size", "8g", "-fs", "APFS", "-uid", str(os.getuid()), "-gid", str(os.getgid()), "-mode", "0700", "-volname", "SI_NATIVE_PROCESS_PROOF_V1", "-nospotlight", "-plist", str(self.image)]
        if verb == "attach": return [native.HDIUTIL, "attach", "-mountpoint", str(self.mount), "-mount", "required", "-nobrowse", "-owners", "on", "-noautoopen", "-noautoopenro", "-noautoopenrw", "-plist", str(self.image)]
        require(verb == "info", "native_proof_command"); return [native.HDIUTIL, "info", "-plist"]
    def command(self, role, verb):
        require(role not in self.origins and {"before": "info", "create": "create", "attach": "attach", "initial": "info", "terminal": "info"}.get(role) == verb,
            "native_proof_command")
        remaining = self.clock.check(); require(remaining > 0, "native_proof_deadline")
        self._pre_command(role)
        result = subprocess.run(self.arguments(verb), cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False, timeout=min(COMMAND_SECONDS, remaining), env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
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
        require(current["fstype"] == "apfs" and current["owner"] == os.getuid()
            and current["flags"] & native.MNT_LOCAL and current["flags"] & native.MNT_DONTBROWSE
            and not current["flags"] & (native.MNT_RDONLY | native.MNT_IGNORE_OWNERSHIP)
            and current["mounted_on"] == str(self.mount) and current["mounted_from"] == self.device
            and native._mount_identity(current) == self.mount_native, "native_proof_mount")
    def _system(self):
        info = os.stat(".fseventsd", dir_fd=self.mount_fd, follow_symlinks=False)
        require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == 0
            and info.st_gid == os.fstat(self.mount_fd).st_gid and info.st_dev == os.fstat(self.mount_fd).st_dev,
            "native_proof_protection")
        return _stamp(info)[:6]
    def check(self):
        self.clock.check(); self.directory.check()
        require(set(os.listdir(self.directory.fd)) == {"backing.sparseimage", "mount"}, "native_proof_membership")
        require(native._backing(os.fstat(self.backing_fd)) == native._backing(self.image.lstat()) == self.backing_pin,
            "native_proof_backing")
        require(_dir(os.fstat(self.under_fd), True) == self.under_pin and self.mount.resolve() == self.mount
            and _dir(os.fstat(self.mount_fd), True) == _dir(self.mount.lstat(), True) == self.mount_pin, "native_proof_mount")
        self._native(native._native_statfs(self.mount_fd))
        require(native._node_pin(self.device, os.fstat(self.mount_fd).st_dev) == self.node, "native_proof_mount")
        expected = ({".fseventsd"} if self.system is not None else set()) | ({"proof"} if hasattr(self, "proof_pin") else set())
        require(set(os.listdir(self.mount_fd)) == expected, "native_proof_membership")
        if self.system is not None: require(self._system() == self.system, "native_proof_protection")
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
        return {"backing_original_identity": self.backing_pin, "mount_original_identity": self.mount_pin,
            "native_original_identity": self.mount_native, "device_node_original_identity": self.node,
            "fresh_root_creation_identity": self.creation, "system_original_metadata": self.system,
            "attach_original_entities": self.attach_entities,
            "original_command_output_sha256s": {name: hash_bytes(raw) for name, raw in sorted(self.origins.items())}}
    def named(self):
        self.directory.named()
        require(set(os.listdir(self.path)) == {"backing.sparseimage", "mount"}
            and native._backing(self.image.lstat()) == self.backing_pin and _dir(self.mount.lstat(), True) == self.mount_pin,
            "native_proof_path")
        require(set(os.listdir(self.mount)) == ({".fseventsd"} if self.system is not None else set()) | {"proof"}
            and _dir((self.mount / "proof").lstat(), True) == self.proof_pin, "native_proof_membership")
        if self.system is not None: require(_stamp((self.mount / ".fseventsd").lstat())[:6] == self.system, "native_proof_protection")
    def close(self):
        first = None
        try: _drain(self.fds)
        except BaseException as error: first = error
        try: self.directory.close()
        except BaseException as error:
            if first is None: first = error
        if first is not None: raise first


class NativeProofResult:
    __slots__ = ("_anchor",)
    def __init__(self): raise NativeProofRefusal("REFUSED: native_proof_result_factory")
    def public_summary(self):
        row = _RESULTS.get(id(self))
        require(type(row) is tuple and row[0] is self and row is self._anchor, "native_proof_result_changed")
        return json.loads(row[1])


def _collect_buffers(error, process, outputs, log_fd):
    """Bounded exact original failure frame; values remain private, never formatted."""
    previous = _BUFFER_ORIGINS.get(id(error))
    if previous is not None and previous[0] is error:
        return previous if previous[1] is process and previous[2] is outputs and previous[3] == log_fd else None
    if worker._collect is not _COLLECT_FUNCTION or worker._collect.__code__ is not _COLLECT_CODE: return None
    trace = BaseException.__traceback__.__get__(error, BaseException)
    frame = None
    for unused in range(128):
        if trace is None: break
        if trace.tb_frame.f_code is _COLLECT_CODE and trace.tb_frame.f_globals is worker.__dict__:
            if frame is not None: return None
            frame = trace.tb_frame
        trace = trace.tb_next
    if trace is not None or frame is None: return None
    values = frame.f_locals
    if values.get("process") is not process or values.get("ns") is not outputs or values.get("log_fd") != log_fd: return None
    if not all(name in values for name in ("pending", "output")): return None
    buffers = tuple((name, values[name]) for name in ("pending", "output", "line", "block") if name in values)
    if not all(type(value) is bytes and len(value) <= worker.MAXIMUM_LOG_BYTES + 1024 for unused, value in buffers): return None
    raw = canonical_json({"schema": "si-native-original-collect-buffers-v1", "private_buffers_hex": {name: value.hex() for name, value in buffers},
        "all_present_original_fields_retained": True, "authority": authority()}).encode()
    row = error, process, outputs, log_fd, frame, buffers, raw, hash_bytes(raw), object()
    _BUFFER_ORIGINS[id(error)] = row
    return row


def _preserve_failed_collection(error, origin, process, outputs, volume, code, bootstrap, clock, log_fd):
    """Late completion is negative only; inability to authenticate retains all contexts."""
    buffers = _collect_buffers(error, process, outputs, log_fd)
    if buffers is None: return False
    if id(error) in _PRESERVATION_ORIGINS: return False
    state = {"remaining": b"", "block": b"", "blocks": (), "partial_log": None,
        "failure": None, "failure_frame": None}
    # Strong original issuance precedes every extra consumed pipe/log read.
    _PRESERVATION_ORIGINS[id(error)] = error, process, outputs, log_fd, origin, object(), state
    try:
        outputs.write("child.failure.buffers.private.json", buffers[6])
        require(_BUFFER_ORIGINS.get(id(error)) is buffers and buffers[0] is error and buffers[1] is process
            and buffers[2] is outputs and buffers[3] == log_fd
            and hash_bytes(buffers[6]) == buffers[7], "native_proof_wait")
        wait = worker._WAITS.get(process)
        if not (type(wait) is tuple and len(wait) == 3 and wait[0] is origin and type(wait[1]) is int):
            while True:
                require(worker._CHILDREN.get(process) is origin and origin[0] is process, "native_proof_wait")
                try: status = process.wait(timeout=30)
                except subprocess.TimeoutExpired: continue
                require(type(status) is int and worker._CHILDREN.get(process) is origin, "native_proof_wait")
                worker._WAITS[process] = origin, status, object(); wait = worker._WAITS[process]
                break
        require(wait[0] is origin and origin[0] is process and type(wait[1]) is int, "native_proof_wait")
        eof = False
        for unused in range(6):
            block = os.read(process.stdout.fileno(), min(1024, worker.MAXIMUM_LOG_BYTES - len(state["remaining"]) + 1))
            state["block"] = block; state["blocks"] = (*state["blocks"], block)
            require(type(block) is bytes, "native_proof_wait")
            state["remaining"] += block
            if not block: eof = True; break
            require(len(state["remaining"]) <= worker.MAXIMUM_LOG_BYTES, "native_proof_capacity")
        require(eof, "native_proof_wait")
        outputs.write("child.remaining.pipe.private.json", canonical_json({"schema": "si-native-remaining-pipe-v1", "private_bytes_hex": state["remaining"].hex(), "authority": authority()}).encode())
        row = outputs.originals.get("stdout.jsonl")
        require(row is not None and row[0] == log_fd and row[2] is None, "native_proof_wait")
        size = os.fstat(log_fd).st_size; require(0 <= size <= worker.MAXIMUM_LOG_BYTES, "native_proof_capacity")
        outputs.validate(log_fd, "stdout.jsonl", size); seal = _stamp(os.fstat(log_fd)); os.lseek(log_fd, 0, os.SEEK_SET)
        raw = os.read(log_fd, worker.MAXIMUM_LOG_BYTES + 1); state["partial_log"] = raw
        require(len(raw) == size, "native_proof_stamp")
        outputs.seal("stdout.jsonl", log_fd, seal, raw)
        outputs.write("child.late.exit.negative.json", canonical_json({"schema": "si-native-late-exit-negative-v1", "status": "permanent_negative_original_wait_observed",
            "actual_child_exit": wait[1], "original_failure": failure_summary(error), "authority": authority()}).encode())
        code.audit(); worker._guard(code.head, code.remote); volume.terminal()
        if "native.terminal.plist" not in outputs.originals: outputs.write("native.terminal.plist", volume.origins["terminal"])
        _bootstrap_audit(bootstrap); volume.check(); outputs.audit(); clock.check()
        return True
    except BaseException as secondary:
        state["failure"] = secondary
        trace = BaseException.__traceback__.__get__(secondary, BaseException)
        for unused in range(128):
            if trace is None: break
            if trace.tb_frame.f_code is _preserve_failed_collection.__code__ and trace.tb_frame.f_globals is globals():
                state["failure_frame"] = trace.tb_frame; break
            trace = trace.tb_next
        return False  # No retry/reseal/reset after a preservation failure.


def run_registered(head, remote, bootstrap_sha256):
    global _USED
    _phase("registration"); registered(); require(not _USED, "native_proof_already_used"); _USED = True
    clock = _Clock(); code = bootstrap = volume = outputs = process = None
    bootstrap_fds = []; failure = None; unknown = False; log_fd = origin = None
    collect_entered = collect_returned = False
    try:
        _phase("current_code"); worker._guard(head, remote); code = _Code(head, remote, clock)
        _phase("bootstrap"); bootstrap, bootstrap_fds = _read_bootstrap(head, remote, code.manifest, bootstrap_sha256)
        _phase("native_creation"); volume = _Volume(clock)
        _phase("output_creation"); outputs = volume.outputs()
        for role in ("before", "create", "attach", "initial"): outputs.write("native." + role + ".plist", volume.origins[role])
        outputs.write("run.started.json", canonical_json({"schema": "si-native-process-started-v1", "runtime_head": head,
            "actual_remote": remote, "bootstrap_sha256": bootstrap_sha256, "policy_sha256": POLICY_SHA256,
            "code_manifest_sha256": hash_payload(code.manifest), "authority": authority()}).encode())
        worker._guard(head, remote); code.audit(); _bootstrap_audit(bootstrap); volume.check(); outputs.audit()
        log_fd = outputs.create("stdout.jsonl"); os.fsync(log_fd); os.fsync(outputs.fd); os.fsync(outputs.parent)
        _phase("child_launch"); began = worker._now()
        process = subprocess.Popen([worker.PYTHON, "-B", "-m", worker.MODULE, "proof-worker", "--head", head, "--remote", remote],
            cwd=ROOT, env=worker._environment(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            shell=False, close_fds=True, start_new_session=True)
        require(type(process.pid) is int and process.pid > 0 and process.stdout is not None, "native_proof_wait")
        origin = process, bootstrap_sha256, code.manifest, object(); worker._CHILDREN[process] = origin
        _phase("child_observation"); collect_entered = True
        status, stdout_sha, seal = worker._collect(process, outputs, log_fd, began); collect_returned = True
        wait = worker._WAITS.get(process)
        require(type(wait) is tuple and len(wait) == 3 and wait[0] is worker._CHILDREN.get(process) and wait[1] == status == 0,
            "native_proof_wait")
        os.lseek(log_fd, 0, os.SEEK_SET); raw = os.read(log_fd, worker.MAXIMUM_LOG_BYTES + 1)
        require(hash_bytes(raw) == stdout_sha, "native_proof_stamp"); outputs.seal("stdout.jsonl", log_fd, seal, raw)
        report = {"schema": "si-native-process-observation-v1", "status": "provisional_source_free_child_wait0",
            "actual_child_exit": status, "parent_process_id": os.getpid(), "supervisor_parent_process_id": os.getppid(),
            "child_process_id": process.pid, "runtime_head": head, "actual_remote": remote, "policy_sha256": POLICY_SHA256,
            "bootstrap_sha256": bootstrap_sha256, "stdout_sha256": stdout_sha,
            "supervisor_process_exit_attested": False, "launcher_independence_verified": False,
            "known_Codex_exec_session": None, "authority": authority()}
        outputs.write("child.exit.provisional.json", canonical_json(report).encode())
        _phase("terminal_code"); code.audit(); worker._guard(head, remote)
        _phase("terminal_native"); volume.terminal(); outputs.write("native.terminal.plist", volume.origins["terminal"])
        _phase("provisional_publication")
        inventory = {"schema": "si-native-original-metadata-inventory-v1", "status": "provisional_until_Main_kernel_exit0",
            "controls": outputs.inventory(), "native": volume.inventory(), "code_manifest": code.manifest,
            "supervisor_process_exit_attested": False, "authority": authority()}
        inventory_raw = canonical_json(inventory).encode(); outputs.write(INVENTORY_ROLE, inventory_raw)
        inventory_stamp = outputs.originals[INVENTORY_ROLE][2]
        marker = {**report, "inventory_sha256": hash_bytes(inventory_raw), "inventory_bytes": len(inventory_raw),
            "inventory_original_stamp": list(inventory_stamp)}
        outputs.write("run.completed.provisional.json", canonical_json(marker).encode())
        report = {**report, "inventory_sha256": hash_bytes(inventory_raw)}
        code.close(); code.named()
        # No Git or native-command callback after this original evidence sweep.
        _phase("original_audit"); _bootstrap_audit(bootstrap); volume.check(); outputs.audit(); clock.check()
    except BaseException as error:
        failure = error; detail = failure_summary(error)
        if process is not None:
            row = worker._WAITS.get(process)
            unknown = not (type(row) is tuple and len(row) == 3 and row[0] is worker._CHILDREN.get(process) and type(row[1]) is int)
        if outputs is not None and not outputs.closed:
            try: outputs.write("run.refused.json", canonical_json({"schema": "si-native-process-refusal-v1", "failure": detail,
                "child_termination_unknown": unknown, "authority": authority()}).encode())
            except BaseException: pass
        collect_failure = collect_entered and not collect_returned
        if unknown or collect_failure:
            held = (process, code, bootstrap, tuple(bootstrap_fds), volume, outputs)
            _HELD.append(held); unknown = True
            if origin is not None and _preserve_failed_collection(error, origin, process, outputs, volume, code, bootstrap, clock, log_fd):
                require(_HELD[-1] is held, "native_proof_wait"); unknown = False; _HELD.pop()
            else:
                while True: time.sleep(30)  # No kill/restart/release of ANY original context.
        raise
    finally:
        if not unknown:
            _phase("cleanup"); first = failure
            actions = []
            if process is not None and process.stdout is not None: actions.append(process.stdout.close)
            for obj in (outputs, volume, code):
                if obj is not None: actions.append(obj.close)
            actions.append(lambda: _drain(bootstrap_fds))
            if bootstrap is not None: actions.append(bootstrap.close)
            for close in actions:
                try: close()
                except BaseException as error:
                    if first is None: first = error; failure_summary(error)
            if failure is None and first is not None: raise first
    _phase("named_audit"); volume.named(); _bootstrap_audit(bootstrap, named=True); code.named(); outputs.named(); clock.check()
    require("run.refused.json" not in os.listdir(outputs.path), "native_proof_membership")
    value = object.__new__(NativeProofResult); row = value, canonical_json(report), wait, object()
    value._anchor = row; _RESULTS[id(value)] = row
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description="One registered source-free native process proof")
    parser.add_argument("command", choices=("prepare-proof", "run-proof", "capture"))
    parser.add_argument("--head"); parser.add_argument("--remote"); parser.add_argument("--bootstrap-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "capture": raise NativeProofRefusal("REFUSED: native_proof_source_refused")
        if args.command == "prepare-proof": result = prepare_bootstrap(args.head, args.remote)
        else: result = run_registered(args.head, args.remote, args.bootstrap_sha256).public_summary()
        print(canonical_json(result)); return 0
    except BaseException as error:
        print(canonical_json({"status": "refused", "failure": failure_summary(error), "authority": authority()})); return 2


if __name__ == "__main__": raise SystemExit(main())
