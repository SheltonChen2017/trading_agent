"""Purpose-specific, source-free Root export and independently owned Main wait.

Saved JSON never reconstructs ClosedNativeSupervision or a Popen wait. A new
durable observation can be loaded only against the separate committed anchor
written by Main after the *outer* process has actually closed successfully.
This module grants no provider, budget-release, strategy or QC authority.
"""
import argparse
from contextlib import contextmanager
import errno
import json
import math
import os
from pathlib import Path
import re
import select
import secrets
import stat
import subprocess
import sys
import time
from types import CodeType, FrameType, SimpleNamespace

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import prove_short_interest_native_supervision as p

ROOT = p.ROOT
DRIVER = "scripts/short_interest_native_main_receipt.py"
MODULE = "scripts.short_interest_native_main_receipt"
ANCHOR = Path("research/short_interest_etf/specs/native_main_receipt_anchor_20261103_v1.json")
PROTOCOL_SHA256 = "8e99009d217b81aa6720e8b313d495943831679cdb7948d21cf11be590ead4c0"
ROOT_PROJECTION = "root.projection.private.json"
MAIN_RECEIPT = "main.receipt.private.json"
MAXIMUM_SECONDS, MAXIMUM_FILE_BYTES, MAXIMUM_WIRE_BYTES, MAXIMUM_PIPE_BYTES = 300, 4096, 4096, 65536
STAMP_SCHEMA = "si-native-file-full9-v1-gid-permission-mode-flags-separate"
_STAGES = frozenset("registration code root_coordinate root_export root_handshake root_close main_spawn main_receive main_wait main_publish loader cleanup terminal".split())
_CODES = frozenset("main_arguments main_unregistered main_factory main_latched main_clock main_deadline main_wire main_shape main_binding main_file main_directory main_flags main_bytes main_original main_negative main_exit main_source_refused main_anchor_pending main_anchor_changed main_code main_closed main_unknown".split())
_ERRNOS = {getattr(errno, key): key for key in ("EACCES", "EPERM", "ENOENT", "EEXIST", "EIO", "ENOSPC", "EROFS", "EBADF", "ELOOP", "EPIPE", "EINTR")}
_STAGE, _USED = "registration", False
_CHILDREN, _WAITS, _OBSERVED, _AUTHENTICATED, _HELD = {}, {}, {}, {}, []
_OBSERVED_FAILED, _AUTHENTICATED_FAILED = set(), set()


class NativeMainReceiptRefusal(ValueError):
    pass


def require(value, code):
    if not value:
        raise NativeMainReceiptRefusal("REFUSED: " + code)


def _phase(stage):
    global _STAGE
    require(stage in _STAGES, "main_arguments")
    _STAGE = stage


def _profile():
    value = getattr(p, "LOCAL_MAIN_V1", None)
    require(value is not None and p._profile(value) is value, "main_unregistered")
    return value


def code_paths():
    return (*p.CODE_FILES, DRIVER)


def authority():
    return {"durable_custody_observation_only": True, "source_admitted": False,
        "source_dispatch_authority": False, "budget_release_authority": False,
        "accounting_resolution_admitted": False, "old_actuals_known": False,
        "count_source_qualified": False, "denominator_admitted": False,
        "actual_input_admitted": False, "ready_for_backtest": False,
        "provider_HTTP": 0, "credential_reads": 0, "new_source_claims": 0,
        "source_STARTs": 0, "source_bytes": 0, "outcome_looks": 0,
        "QC_or_Safari": False, "qc_attempts": 0}


def policy():
    profile = _profile()
    return {"schema": "si-native-main-receipt-policy-v1", "root": str(ROOT),
        "native_profile": p._profile_id(profile), "native_policy_sha256": p._policy_sha(profile),
        "code_files": list(code_paths()), "driver_module": MODULE,
        "root_projection": ROOT_PROJECTION, "main_receipt": MAIN_RECEIPT,
        "root_directory": "root-export", "main_directory": "main-receipt",
        "maximum_seconds": MAXIMUM_SECONDS, "maximum_file_bytes": MAXIMUM_FILE_BYTES,
        "maximum_wire_bytes": MAXIMUM_WIRE_BYTES, "maximum_pipe_bytes": MAXIMUM_PIPE_BYTES,
        "stamp_schema": STAMP_SCHEMA, "anchor": ANCHOR.as_posix(),
        "projection": "only_exact_live_Root_factory_original_marker_flags_manifest_native_config_context_clock_no_JSON_Root_reconstruction",
        "handoff": "Root_ready_original_publisher_held_Main_original_RO_open_ACK_then_Root_closed_same_seal_actual_own_Popen_wait0_EOF_no_stderr",
        "wait": "original_launch_frame_process_args_env_binding_and_original_controller_wait_never_caller_exit_flags",
        "directories": "original_empty_full9_before_first_owned_OEXCL_one_known_addition_then_one_new_postpublication_full9_seal_no_rebaseline",
        "publication": "unchanged_genuine_Files_creator_RO_handoff_UF2_original_full9_exact_bytes_all_contexts_and_postclose",
        "unknown": "retain_original_process_FDs_bytes_and_contexts_no_kill_retry_or_positive_recovery",
        "durable_reader": "committed_independent_anchor_original_body_and_stamp_digests_historical_code_current_reader_guard_held_until_close",
        "authority": authority()}


def registered():
    require(type(PROTOCOL_SHA256) is str and re.fullmatch(r"[0-9a-f]{64}", PROTOCOL_SHA256)
        and hash_payload(policy()) == PROTOCOL_SHA256, "main_unregistered")
    require(tuple(p.policy(_profile())["code_files"]) == code_paths()
        and len(code_paths()) == len(set(code_paths())) == 8, "main_code")
    p.registered(_profile())


def failure_summary(error):
    code = None
    if type(error) is NativeMainReceiptRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((item for item in _CODES if args[0] == "REFUSED: " + item), None)
    number = OSError.errno.__get__(error, OSError) if isinstance(error, OSError) else None
    upstream = p.failure_summary(error)
    return {"stage": _STAGE, "category": "local_contract_refusal" if code or upstream["contract_code"] or upstream["upstream_contract_code"] else "unknown_local_error",
        "contract_code": code, "native_contract_code": upstream["contract_code"],
        "upstream_contract_code": upstream["upstream_contract_code"],
        "errno_name": _ERRNOS.get(number) or upstream["errno_name"],
        "mismatching_fields": upstream["mismatching_fields"]}


def _exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return set(actual) == set(expected) and all(type(k) is str and _exact(actual[k], expected[k]) for k in expected)
    if type(expected) in (list, tuple):
        return len(actual) == len(expected) and all(_exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _head(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def _stamp(value):
    require(type(value) in (list, tuple) and len(value) == 9
        and all(type(item) is int and item >= 0 for item in value), "main_shape")
    return tuple(value)


def _flags(value):
    require(type(value) is int and 0 <= value < 2 ** 32 and value & p.UF_IMMUTABLE, "main_flags")
    return value


def _json(raw, *, wire=False):
    require(type(raw) is bytes and 0 < len(raw) <= (MAXIMUM_WIRE_BYTES if wire else MAXIMUM_FILE_BYTES), "main_wire")
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, "main_shape")
            result[key] = value
        return result
    def invalid(unused):
        raise NativeMainReceiptRefusal("REFUSED: main_shape")
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid)
    except (ValueError, UnicodeError):
        raise NativeMainReceiptRefusal("REFUSED: main_shape") from None
    require(type(value) is dict and (canonical_json(value) + ("\n" if wire else "")).encode() == raw, "main_shape")
    return value


def _wire(value, fd=1):
    raw = (canonical_json(value) + "\n").encode()
    require(len(raw) <= MAXIMUM_WIRE_BYTES, "main_wire")
    p._write(fd, raw)
    return raw


class _Latched:
    def __init__(self):
        self.failed = False
    def _run(self, operation):
        require(not self.failed, "main_latched")
        try:
            return operation()
        except BaseException:
            self.failed = True
            raise


class _Deadline(_Latched):
    def __init__(self):
        super().__init__()
        self.begin = self.last = time.monotonic()
        p._bind_profile(self, _profile())
        self.check()
    def check(self):
        def action():
            now = time.monotonic()
            require(type(now) in (int, float) and math.isfinite(now)
                and 0 <= self.begin <= self.last <= now, "main_clock")
            require(now - self.begin <= MAXIMUM_SECONDS, "main_deadline")
            self.last = now
            return MAXIMUM_SECONDS - (now - self.begin)
        return self._run(action)


class _RootDeadline:
    def __init__(self, clock, projection):
        self.clock, self.projection = clock, projection
        p._bind_profile(self, _profile())
    def check(self):
        return min(self.clock.check(), self.projection.remaining_seconds())


def _binding(head, remote, operation):
    require(_head(head) and _head(remote) and type(operation) is str
        and re.fullmatch(r"[0-9a-f]{32}", operation), "main_arguments")
    return {"schema": "si-native-main-bridge-wire-v1", "runtime_head": head,
        "actual_remote": remote, "operation": operation, "protocol_sha256": PROTOCOL_SHA256,
        "native_policy_sha256": p._policy_sha(_profile()), "authority": authority()}


def _packet(raw, binding, event, fields):
    value = _json(raw, wire=True)
    require(set(value) == set(binding) | {"event", *fields}
        and all(_exact(value.get(key), val) for key, val in binding.items())
        and type(value.get("event")) is str and value["event"] == event, "main_binding")
    return value


def _descriptor(value, name):
    require(type(value) is dict and set(value) == {"schema", "name", "bytes", "sha256", "native_full9", "original_flags", "directory_native_full9"}
        and value["schema"] == STAMP_SCHEMA and value["name"] == name
        and type(value["bytes"]) is int and 0 < value["bytes"] <= MAXIMUM_FILE_BYTES
        and _digest(value["sha256"]), "main_shape")
    require(_stamp(value["native_full9"])[6] == value["bytes"], "main_shape")
    _stamp(value["directory_native_full9"]); _flags(value["original_flags"])
    return value


def _projection(raw, head, remote):
    value = _json(raw)
    keys = {"schema", "storage_profile", "runtime_head", "actual_remote", "policy_sha256", "spec_sha256", "nonce", "producer_pid", "actual_kernel_exit", "actual_child_exit", "marker", "inventory", "code_manifest_sha256", "native_inventory_sha256", "config_identity7_sha256", "load_window9_sha256", "root_context_snapshot_sha256", "host_directory_originals", "authority"}
    require(set(value) == keys and value["schema"] == "si-native-root-closure-projection-v1"
        and value["storage_profile"] == p._profile_id(_profile())
        and value["runtime_head"] == head and value["actual_remote"] == remote
        and value["policy_sha256"] == p._policy_sha(_profile())
        and _exact(value["authority"], p.authority()), "main_binding")
    require(type(value["producer_pid"]) is int and 0 < value["producer_pid"] < 2 ** 31
        and type(value["actual_kernel_exit"]) is int and value["actual_kernel_exit"] == 0
        and type(value["actual_child_exit"]) is int and value["actual_child_exit"] == 0
        and type(value["nonce"]) is str and re.fullmatch(r"[0-9a-f]{32}", value["nonce"]), "main_shape")
    for key in ("spec_sha256", "code_manifest_sha256", "native_inventory_sha256", "config_identity7_sha256", "load_window9_sha256", "root_context_snapshot_sha256"):
        require(_digest(value[key]), "main_shape")
    for name, keys in (("marker", {"sha256", "native_full9", "original_flags"}), ("inventory", {"sha256", "native_full9", "original_flags", "bytes"})):
        row = value[name]
        require(type(row) is dict and set(row) == keys and _digest(row["sha256"]), "main_shape")
        _stamp(row["native_full9"]); _flags(row["original_flags"])
        if name == "inventory": require(type(row["bytes"]) is int and 0 < row["bytes"] <= p.MAXIMUM_NATIVE_BYTES and row["bytes"] == row["native_full9"][6], "main_shape")
    require(type(value["host_directory_originals"]) is dict and set(value["host_directory_originals"]) == {"root-export", "main-receipt"}, "main_shape")
    for row in value["host_directory_originals"].values(): _stamp(row)
    return value


class _Publication(_Latched):
    """Keep initial empty observation separate from one new publication seal."""
    def __init__(self, directory, initial, clock, name):
        super().__init__()
        require(type(directory) is p._Directory and p._profile_of(directory) is _profile()
            and name in {ROOT_PROJECTION, MAIN_RECEIPT}, "main_factory")
        self.directory, self.initial, self.clock, self.name = directory, _stamp(initial), clock, name
        self.files, self.directory_seal, self.closed = None, None, False
        self.check()
        self.files = p._Files(directory.fd, directory.parent, directory.path, self.check, (name,))
    def check(self):
        def action():
            self.clock.check(); self.directory.check()
            require(not self.closed, "main_closed")
            names = set(self.files.originals) if self.files is not None else set()
            require(names <= {self.name} and set(os.listdir(self.directory.fd)) == names, "main_directory")
            a = p._stamp(os.fstat(self.directory.fd)); b = p._stamp(self.directory.path.lstat())
            # This fixed profile requires the observed APFS all-entry nlink
            # contract. This is not a portable ordinary-directory adapter.
            require(a == b and a[:5] == self.initial[:5]
                and a[5] == self.initial[5] + len(names), "main_directory")
            if not names: require(a == self.initial, "main_original")
            if self.directory_seal is not None: require(a == self.directory_seal, "main_original")
        return self._run(action)
    def write(self, raw):
        def action():
            require(self.directory_seal is None and not self.files.originals, "main_factory")
            self.files.write(self.name, raw); self.files.audit(); self.check()
            self.directory_seal = p._stamp(os.fstat(self.directory.fd))
            self.check()
        return self._run(action)
    def descriptor(self):
        self.audit()
        row = self.files.originals[self.name]
        return {"schema": STAMP_SCHEMA, "name": self.name, "bytes": len(row[3]),
            "sha256": hash_bytes(row[3]), "native_full9": list(row[2]),
            "original_flags": p._creator(self.files.creators[self.name])["frozen_flags"],
            "directory_native_full9": list(self.directory_seal)}
    def audit(self):
        return self._run(lambda: (self.check(), self.files.audit()))
    def close(self):
        try:
            if self.files is not None and not self.files.closed: self.files.close()
        except BaseException:
            self.failed = True; raise
        finally: self.closed = True
    def named(self):
        def action():
            self.clock.check(); self.directory.named()
            require(self.closed and self.directory_seal is not None
                and p._stamp(self.directory.path.lstat()) == self.directory_seal, "main_original")
            self.files.named()
            require(p._stamp(self.directory.path.lstat()) == self.directory_seal, "main_original")
        return self._run(action)


class _HeldArtifact(_Latched):
    def __init__(self, directory, descriptor, name, clock):
        super().__init__()
        self.directory, self.clock = directory, clock
        self._descriptor_raw = canonical_json(_descriptor(descriptor, name))
        self._descriptor_value = json.loads(self._descriptor_raw)
        self.path, self.fd, self.raw, self.closed = directory.path / name, None, None, False
        try:
            directory.check()
            self.fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory.fd)
            require(p._descriptor_access(self.fd) == os.O_RDONLY and os.get_inheritable(self.fd) is False, "main_file")
            self.audit()
        except BaseException:
            self.failed = True; self.close(); raise
    @property
    def descriptor(self):
        return json.loads(self._descriptor_raw)
    def _info(self, info):
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
            and p._stamp(info) == tuple(self.descriptor["native_full9"])
            and p._file_flags(info) == self.descriptor["original_flags"], "main_original")
    def audit(self):
        def action():
            self.clock.check(); self.directory.check()
            require(not self.closed and set(os.listdir(self.directory.fd)) == {self.descriptor["name"]}
                and p._stamp(os.fstat(self.directory.fd)) == p._stamp(self.directory.path.lstat()) == tuple(self.descriptor["directory_native_full9"]), "main_directory")
            self._info(os.fstat(self.fd)); self._info(self.path.lstat())
            os.lseek(self.fd, 0, os.SEEK_SET); raw = os.read(self.fd, MAXIMUM_FILE_BYTES + 1)
            require(len(raw) == self.descriptor["bytes"] and hash_bytes(raw) == self.descriptor["sha256"]
                and (self.raw is None or self.raw == raw), "main_bytes")
            self.raw = raw; self._info(os.fstat(self.fd)); self._info(self.path.lstat())
        return self._run(action)
    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            try: p._close(fd)
            except BaseException: self.failed = True; raise
        self.closed = True
    def named(self):
        def action():
            self.clock.check(); self.directory.named()
            require(p._stamp(self.directory.path.lstat()) == tuple(self.descriptor["directory_native_full9"])
                and set(os.listdir(self.directory.path)) == {self.descriptor["name"]}, "main_directory")
            self._info(self.path.lstat())
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                self._info(os.fstat(fd)); raw = os.read(fd, MAXIMUM_FILE_BYTES + 1)
                require(raw == self.raw, "main_bytes"); self._info(os.fstat(fd))
            finally: p._close(fd)
            self._info(self.path.lstat())
            require(p._stamp(self.directory.path.lstat()) == tuple(self.descriptor["directory_native_full9"]), "main_directory")
        return self._run(action)


class _Lines(_Latched):
    def __init__(self, fd, clock):
        super().__init__(); self.fd, self.clock, self.pending, self.total = fd, clock, bytearray(), 0
    def read(self):
        def action():
            while True:
                self.clock.check(); index = self.pending.find(b"\n")
                if index >= 0:
                    require(index + 1 <= MAXIMUM_WIRE_BYTES, "main_wire")
                    raw = bytes(self.pending[:index + 1]); del self.pending[:index + 1]; return raw
                require(len(self.pending) < MAXIMUM_WIRE_BYTES, "main_wire")
                ready, unused, unused2 = select.select([self.fd], [], [], min(0.25, self.clock.check()))
                if ready:
                    block = os.read(self.fd, MAXIMUM_WIRE_BYTES - len(self.pending))
                    require(type(block) is bytes and bool(block), "main_wire")
                    self.pending.extend(block); self.total += len(block)
                    require(self.total <= MAXIMUM_PIPE_BYTES, "main_wire")
        return self._run(action)
    def finish(self):
        def action():
            require(not self.pending, "main_wire")
            while True:
                self.clock.check(); ready, unused, unused2 = select.select([self.fd], [], [], min(0.25, self.clock.check()))
                if ready: require(os.read(self.fd, 1) == b"", "main_wire"); return
        return self._run(action)


def _entry(head, remote, operation):
    global _USED
    require(not _USED, "main_latched"); _USED = True
    clock = _Deadline(); binding = _binding(head, remote, operation)
    registered(); p._guard(head, remote); code = p._Code7(head, remote, clock)
    require(set(code.manifest) == set(code_paths()), "main_code")
    return clock, binding, code


def _directory(kind):
    return p._Directory(kind, create=False, profile=_profile())


def _hold(state):
    """Unknown lifecycle/unpreserved original bytes are never released or killed."""
    _HELD.append(state)
    while True: time.sleep(1)


def root_export(head, remote, operation, *, input_fd=0, output_fd=1):
    _phase("registration"); clock, binding, code = _entry(head, remote, operation)
    directory = publication = projection = None; failure = None; held = False
    try:
        with p._source_denied():
            _phase("root_coordinate")
            root = p.coordinate_registered(head, remote, profile=_profile())
            projection = p.project_root_closure(root)
            raw = projection.canonical_bytes(); body = _projection(raw, head, remote)
            require(body["code_manifest_sha256"] == hash_payload(code.manifest), "main_code")
            coupled = _RootDeadline(clock, projection)
            _phase("root_export"); directory = _directory("root-export")
            publication = _Publication(directory, body["host_directory_originals"]["root-export"], coupled, ROOT_PROJECTION)
            publication.write(raw); descriptor = publication.descriptor(); code.audit(); publication.audit()
            ready = {**binding, "event": "projection_ready", "root_pid": os.getpid(), "projection": descriptor}
            _wire(ready, output_fd)
            _phase("root_handshake"); reader = _Lines(input_fd, coupled)
            ack = _packet(reader.read(), binding, "main_original_projection_open", ("root_pid", "main_pid", "projection_sha256"))
            require(type(ack["main_pid"]) is int and ack["main_pid"] == os.getppid()
                and type(ack["root_pid"]) is int and ack["root_pid"] == os.getpid()
                and ack["projection_sha256"] == descriptor["sha256"], "main_binding")
            reader.finish(); publication.audit(); code.audit(); publication.audit()
            _phase("root_close"); publication.close(); publication.named(); directory.check()
            code.close(); code.named(); publication.named(); directory.close(); directory.named(); publication.named(); coupled.check()
            _wire({**ready, "event": "projection_closed"}, output_fd)
    except BaseException as error:
        failure = error
        if publication is not None and (publication.failed or publication.files and publication.files.originals):
            held = True; _hold({"role": "root", "error": error, "code": code, "directory": directory, "publication": publication, "projection": projection})
        raise
    finally:
        if not held:
            first = failure
            for item in (publication, directory, code):
                if item is not None:
                    try: item.close()
                    except BaseException as error:
                        if first is None: first = error
            if failure is None and first is not None: raise first


def _command(head, remote, operation):
    return [p.worker.PYTHON, "-B", "-m", MODULE, "root-export", "--head", head, "--remote", remote, "--operation", operation]


def _launch_root(head, remote, operation):
    arguments = _command(head, remote, operation); environment = p.worker._environment()
    process = subprocess.Popen(arguments, cwd=ROOT, env=environment, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, close_fds=True)
    require(type(process) is subprocess.Popen and type(process.pid) is int and process.pid > 0
        and process.stdin is not None and process.stdout is not None and process.stderr is not None, "main_factory")
    row = process, tuple(arguments), hash_payload(environment), sys._getframe(), object()
    _CHILDREN[process] = row
    return process


def _origin(process):
    row = _CHILDREN.get(process)
    require(type(row) is tuple and len(row) == 5 and row[0] is process
        and type(process) is subprocess.Popen and type(process.args) is list
        and tuple(process.args) == row[1], "main_factory")
    frame = row[3]
    require(type(frame) is FrameType and frame.f_code is _launch_root.__code__ and frame.f_globals is globals()
        and frame.f_locals.get("process") is process
        and frame.f_locals.get("row") is row
        and tuple(frame.f_locals.get("arguments", ())) == row[1]
        and hash_payload(frame.f_locals.get("environment")) == row[2], "main_factory")
    return row


class _Pump(_Latched):
    def __init__(self, process, clock):
        super().__init__(); _origin(process)
        self.process, self.clock = process, clock
        self.stdout, self.stderr, self.pending, self.blocks = bytearray(), bytearray(), bytearray(), []
        self.open = {process.stdout.fileno(): "stdout", process.stderr.fileno(): "stderr"}
        for fd in self.open: os.set_blocking(fd, False)
    def _step(self):
        self.clock.check()
        ready, unused, unused2 = select.select(list(self.open), [], [], min(0.25, self.clock.check()))
        for fd in ready:
            try: block = os.read(fd, MAXIMUM_WIRE_BYTES)
            except BlockingIOError: continue
            if not block: del self.open[fd]; continue
            role = self.open[fd]; self.blocks.append((role, block))  # retain BEFORE any refusal
            target = self.stdout if role == "stdout" else self.stderr; target.extend(block)
            if role == "stdout": self.pending.extend(block)
            require(len(target) <= MAXIMUM_PIPE_BYTES and role != "stderr", "main_negative")
    def read(self):
        def action():
            while True:
                index = self.pending.find(b"\n")
                if index >= 0:
                    require(index + 1 <= MAXIMUM_WIRE_BYTES, "main_wire")
                    raw = bytes(self.pending[:index + 1]); del self.pending[:index + 1]; return raw
                require(len(self.pending) < MAXIMUM_WIRE_BYTES and self.process.stdout.fileno() in self.open, "main_wire")
                self._step()
        return self._run(action)
    def finish(self):
        def action():
            require(not self.pending, "main_wire")
            while self.open:
                self._step(); require(not self.pending, "main_wire")
            require(not self.stderr, "main_negative")
            status = self.process.wait(timeout=max(0.001, self.clock.check()))
            require(type(status) is int and status == 0, "main_exit")
            self.clock.check()
            origin = _origin(self.process)
            frame = sys._getframe()
            wait = origin, status, hash_bytes(bytes(self.stdout)), hash_bytes(bytes(self.stderr)), frame, object()
            require(self.process not in _WAITS, "main_factory"); _WAITS[self.process] = wait
            return wait
        return self._run(action)


def _wait(process, pump):
    row = _WAITS.get(process); origin = _origin(process)
    require(type(row) is tuple and len(row) == 6 and row[0] is origin and type(row[1]) is int and row[1] == 0
        and row[2] == hash_bytes(bytes(pump.stdout)) and row[3] == hash_bytes(bytes(pump.stderr))
        and not pump.open and not pump.pending and not pump.stderr, "main_factory")
    frame = row[4]
    require(type(frame) is FrameType and frame.f_code is _PUMP_WAIT_CODE and frame.f_globals is globals()
        and frame.f_locals.get("self") is pump and pump.process is process
        and frame.f_locals.get("wait") is row and frame.f_locals.get("origin") is origin
        and frame.f_locals.get("status") == 0, "main_factory")
    return row


def _close_all(items, primary=None):
    first = primary
    for item in items:
        if item is not None:
            try: item.close()
            except BaseException as error:
                if first is None: first = error
    if first is not None and primary is None: raise first


def _config(head, remote, body, code):
    directory = _directory("bootstrap"); inputs = p._Inputs(directory)
    try:
        raw = inputs.read("launch.spec.json")
        require(hash_bytes(raw) == body["spec_sha256"], "main_code")
        spec = _json(raw)
        require(raw == canonical_json(p._payload(head, remote, code.manifest, spec["observer"], profile=_profile())).encode(), "main_code")
        import plistlib
        require(inputs.read("job.plist") == plistlib.dumps(p.build_launchd_plist(head, remote, hash_bytes(raw), spec["observer"], profile=_profile()), sort_keys=True), "main_code")
        require(p.config_identity7_sha256(inputs) == body["config_identity7_sha256"], "main_original")
        return directory, inputs
    except BaseException:
        _close_all((inputs, directory)); raise


def _originals(head, remote, body, code, clock):
    marker = body["marker"]
    reader = p._OriginalRead(head, remote, body["spec_sha256"], {"nonce": body["nonce"]}, body["producer_pid"],
        {"sha256": marker["sha256"], "stamp": marker["native_full9"], "original_flags": marker["original_flags"]}, profile=_profile())
    try:
        require(hash_payload(reader.inventory["code_manifest"]) == body["code_manifest_sha256"]
            and _exact(reader.inventory["code_manifest"], code.manifest)
            and hash_payload(reader.native) == body["native_inventory_sha256"], "main_code")
        require(_exact(body["inventory"], {"sha256": reader.marker["inventory_sha256"],
            "native_full9": reader.marker["inventory_original_stamp"],
            "original_flags": reader.marker["inventory_original_flags"],
            "bytes": reader.marker["inventory_bytes"]}), "main_original")
        reader.current_association(clock); reader.audit()
        return reader
    except BaseException:
        reader.close(); raise


class MainReceiptObservation:
    __slots__ = ("_anchor",)
    def __init__(self): raise NativeMainReceiptRefusal("REFUSED: main_factory")
    def public_summary(self):
        try:
            require(id(self) not in _OBSERVED_FAILED, "main_latched")
            row = _OBSERVED.get(id(self))
            require(type(self) is MainReceiptObservation and type(row) is tuple and len(row) == 6
                and row[0] is self and self._anchor is row, "main_factory")
            frame = row[5]
            require(type(frame) is FrameType and frame.f_code is _COORDINATE_CODE and frame.f_globals is globals()
                and frame.f_locals.get("value") is self and frame.f_locals.get("row") is row
                and frame.f_locals.get("process") is row[2] and frame.f_locals.get("pump") is row[3]
                and frame.f_locals.get("clock") is row[4], "main_factory")
            _wait(row[2], row[3]); row[4].check()
            return json.loads(row[1])
        except BaseException:
            if type(self) is MainReceiptObservation and id(self) in _OBSERVED: _OBSERVED_FAILED.add(id(self))
            raise


def _public_packet(receipt, descriptor):
    projection = receipt["root_projection"]
    return {"schema": "si-native-main-observation-v1", "status": "closed_candidate_requires_outer_actual_exit_and_committed_anchor",
        "runtime_head": receipt["runtime_head"], "actual_remote": receipt["actual_remote"], "operation": receipt["operation"],
        "protocol_sha256": receipt["protocol_sha256"], "native_policy_sha256": receipt["native_policy_sha256"],
        "receipt_sha256": descriptor["sha256"], "receipt_native_full9_json": canonical_json(descriptor["native_full9"]),
        "receipt_native_full9_sha256": hash_payload(descriptor["native_full9"]),
        "receipt_directory_full9_json": canonical_json(descriptor["directory_native_full9"]),
        "receipt_directory_full9_sha256": hash_payload(descriptor["directory_native_full9"]),
        "receipt_original_flags": descriptor["original_flags"], "receipt_bytes": descriptor["bytes"],
        "projection_sha256": projection["sha256"], "projection_native_full9_sha256": hash_payload(projection["native_full9"]),
        "actual_root_exit": 0, "authority": authority()}


def coordinate_registered(head, remote, operation=None):
    operation = secrets.token_hex(16) if operation is None else operation
    _phase("registration"); clock, binding, code = _entry(head, remote, operation)
    process = pump = root_directory = root_file = reader = config_directory = config = main_directory = publication = None
    failure = None; held = False
    try:
        with p._source_denied():
            _phase("main_spawn"); process = _launch_root(head, remote, operation); pump = _Pump(process, clock)
            _phase("main_receive"); ready_raw = pump.read()
            ready = _packet(ready_raw, binding, "projection_ready", ("root_pid", "projection"))
            require(type(ready["root_pid"]) is int and ready["root_pid"] == process.pid, "main_binding")
            descriptor = _descriptor(ready["projection"], ROOT_PROJECTION)
            root_directory = _directory("root-export"); root_file = _HeldArtifact(root_directory, descriptor, ROOT_PROJECTION, clock)
            body = _projection(root_file.raw, head, remote)
            reader = _originals(head, remote, body, code, clock); config_directory, config = _config(head, remote, body, code)
            root_file.audit(); reader.audit(); config.audit(); clock.check()
            ack = {**binding, "event": "main_original_projection_open", "root_pid": process.pid,
                "main_pid": os.getpid(), "projection_sha256": descriptor["sha256"]}
            process.stdin.write((canonical_json(ack) + "\n").encode()); process.stdin.flush(); process.stdin.close()
            closed_raw = pump.read(); closed = _packet(closed_raw, binding, "projection_closed", ("root_pid", "projection"))
            require(_exact(closed, {**ready, "event": "projection_closed"}), "main_binding")
            _phase("main_wait"); pump.finish(); wait = _wait(process, pump)
            code.audit(); config.audit(); reader.current_association(clock); reader.audit(); root_file.audit(); clock.check()
            _phase("main_publish"); main_directory = _directory("main-receipt")
            publication = _Publication(main_directory, body["host_directory_originals"]["main-receipt"], clock, MAIN_RECEIPT)
            receipt = {"schema": "si-native-main-counter-receipt-v1", "runtime_head": head, "actual_remote": remote,
                "operation": operation, "protocol_sha256": PROTOCOL_SHA256, "native_policy_sha256": p._policy_sha(_profile()),
                "storage_profile": p._profile_id(_profile()), "root_projection": descriptor,
                "root_pid": process.pid, "actual_root_exit": wait[1], "root_stdout_sha256": wait[2],
                "root_stderr_sha256": wait[3], "root_ready_sha256": hash_bytes(ready_raw), "root_closed_sha256": hash_bytes(closed_raw),
                "command_sha256": hash_payload(list(_origin(process)[1])), "environment_sha256": _origin(process)[2],
                "code_manifest": code.manifest, "root_context_snapshot_sha256": body["root_context_snapshot_sha256"],
                "native_inventory_sha256": body["native_inventory_sha256"], "status": "candidate_requires_independent_outer_actual_exit_and_committed_anchor", "authority": authority()}
            receipt_raw = canonical_json(receipt).encode(); require(len(receipt_raw) <= MAXIMUM_FILE_BYTES, "main_shape")
            publication.write(receipt_raw); receipt_descriptor = publication.descriptor()
            code.audit(); config.audit(); reader.audit(); root_file.audit(); publication.audit(); _wait(process, pump); clock.check()
            # No subsequent Git/native callbacks may obscure the final original audit.
            publication.close(); publication.named(); reader.close(); reader.named(); config.close(); config.audit(named=True)
            code.close(); code.named(); root_file.close(); root_file.named()
            main_directory.close(); main_directory.named(); publication.named()
            root_directory.close(); root_directory.named(); root_file.named()
            config_directory.close(); config_directory.named(); config.audit(named=True)
            reader.named(); publication.named(); root_file.named(); clock.check()
            public = _public_packet(receipt, receipt_descriptor)
    except BaseException as error:
        failure = error
        # poll()/caller flags cannot establish the owned wait, drained EOF or
        # preservation of still unread pipe bytes. Retain every pre-wait error.
        if process is not None and (process not in _WAITS or pump is not None and (pump.failed or pump.stderr)):
            held = True; _hold({"role": "main", "process": process, "pump": pump, "code": code, "root_directory": root_directory,
                "root_file": root_file, "reader": reader, "config_directory": config_directory, "config": config,
                "main_directory": main_directory, "publication": publication, "error": error})
        raise
    finally:
        if not held:
            _close_all((publication, reader, config, root_file, main_directory, root_directory, config_directory, code), failure)
            if process is not None:
                _close_all((process.stdin, process.stdout, process.stderr), failure)
    clock.check(); _wait(process, pump)
    value = object.__new__(MainReceiptObservation)
    row = value, canonical_json(public), process, pump, clock, sys._getframe()
    value._anchor = row; _OBSERVED[id(value)] = row
    return value


class _Anchor(_Latched):
    def __init__(self, head):
        super().__init__(); self.path, self.fd, self.closed = ROOT / ANCHOR, None, False
        require(self.path.is_file() and not self.path.is_symlink() and self.path.resolve() == self.path, "main_anchor_pending")
        try:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            info = os.fstat(self.fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                and not stat.S_IMODE(info.st_mode) & 0o022 and 0 < info.st_size <= MAXIMUM_FILE_BYTES, "main_anchor_changed")
            self.original = p._stamp(info); self.raw = os.read(self.fd, MAXIMUM_FILE_BYTES + 1)
            require(len(self.raw) == info.st_size and self.raw == p._git(["show", head + ":" + ANCHOR.as_posix()]), "main_anchor_changed")
            self.audit()
        except BaseException:
            self.failed = True; self.close(); raise
    def audit(self):
        def action():
            require(not self.closed and self.path.resolve() == self.path
                and p._stamp(os.fstat(self.fd)) == p._stamp(self.path.lstat()) == self.original, "main_anchor_changed")
            os.lseek(self.fd, 0, os.SEEK_SET); require(os.read(self.fd, MAXIMUM_FILE_BYTES + 1) == self.raw, "main_anchor_changed")
            require(self.path.resolve() == self.path
                and p._stamp(os.fstat(self.fd)) == p._stamp(self.path.lstat()) == self.original, "main_anchor_changed")
        return self._run(action)
    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            try: p._close(fd)
            except BaseException: self.failed = True; raise
        self.closed = True
    def named(self):
        return self._run(lambda: require(self.path.resolve() == self.path
            and p._stamp(self.path.lstat()) == self.original, "main_anchor_changed"))


def _anchor_value(value, head):
    keys = {"schema", "runtime_head", "native_policy_sha256", "protocol_sha256", "receipt_sha256", "receipt_native_full9_sha256", "receipt_directory_full9_sha256", "receipt_original_flags", "projection_sha256", "projection_native_full9_sha256", "outer_stdout_sha256", "outer_actual_exit", "outer_stderr_bytes", "outer_elapsed_ns"}
    require(set(value) == keys and value["schema"] == "si-native-main-committed-anchor-v1"
        and _head(value["runtime_head"]) and value["native_policy_sha256"] == p._policy_sha(_profile())
        and value["protocol_sha256"] == PROTOCOL_SHA256
        and type(value["outer_actual_exit"]) is int and value["outer_actual_exit"] == 0
        and type(value["outer_stderr_bytes"]) is int and value["outer_stderr_bytes"] == 0
        and type(value["outer_elapsed_ns"]) is int and 0 <= value["outer_elapsed_ns"] <= MAXIMUM_SECONDS * 10 ** 9,
        "main_anchor_changed")
    for key in ("receipt_sha256", "receipt_native_full9_sha256", "receipt_directory_full9_sha256", "projection_sha256", "projection_native_full9_sha256", "outer_stdout_sha256"):
        require(_digest(value[key]), "main_anchor_changed")
    _flags(value["receipt_original_flags"])
    result = subprocess.run(["git", "merge-base", "--is-ancestor", value["runtime_head"], head], cwd=ROOT,
        env=p.worker._environment(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(type(result.returncode) is int and result.returncode == 0, "main_anchor_changed")
    return value


def _anchor(head):
    path = ROOT / ANCHOR
    require(path.is_file() and not path.is_symlink(), "main_anchor_pending")
    held = _Anchor(head)
    try:
        raw = held.raw
        value = _json(raw[:-1] if raw.endswith(b"\n") else raw)
        _anchor_value(value, head); held.audit()
        return value, held
    except BaseException:
        held.close(); raise


class AuthenticatedDurableMainReceipt:
    __slots__ = ("_anchor",)
    def __init__(self): raise NativeMainReceiptRefusal("REFUSED: main_factory")
    def validate(self):
        try:
            require(id(self) not in _AUTHENTICATED_FAILED, "main_latched")
            row = _AUTHENTICATED.get(id(self))
            require(type(self) is AuthenticatedDurableMainReceipt and type(row) is tuple and len(row) == 4
                and row[0] is self and self._anchor is row and type(row[2]) is _Loaded, "main_factory")
            frame = row[3]
            require(type(frame) is FrameType and frame.f_code is _LOAD_CODE and frame.f_globals is globals()
                and frame.f_locals.get("value") is self and frame.f_locals.get("row") is row
                and frame.f_locals.get("loaded") is row[2], "main_factory")
            return row[2].validate()
        except BaseException:
            if type(self) is AuthenticatedDurableMainReceipt and id(self) in _AUTHENTICATED: _AUTHENTICATED_FAILED.add(id(self))
            raise
    def public_summary(self):
        self.validate(); return json.loads(_AUTHENTICATED[id(self)][1])


class _Loaded(_Latched):
    def __init__(self, head, remote, clock, code, anchor, anchor_holder):
        super().__init__(); self.head, self.remote, self.clock, self.code = head, remote, clock, code
        self.anchor, self.anchor_holder, self.closed = anchor, anchor_holder, False
        self.main_directory = self.main_file = self.root_directory = self.root_file = self.reader = self.config_directory = self.config = None
        try:
            self.main_directory = _directory("main-receipt")
            info = os.stat(MAIN_RECEIPT, dir_fd=self.main_directory.fd, follow_symlinks=False)
            original = p._stamp(info); directory_original = p._stamp(os.fstat(self.main_directory.fd))
            # These are comparisons with INDEPENDENT committed original digests,
            # never a newly sampled stamp substituted for a missing seal.
            require(hash_payload(list(original)) == anchor["receipt_native_full9_sha256"]
                and hash_payload(list(directory_original)) == anchor["receipt_directory_full9_sha256"], "main_original")
            desc = {"schema": STAMP_SCHEMA, "name": MAIN_RECEIPT, "bytes": original[6], "sha256": anchor["receipt_sha256"],
                "native_full9": list(original), "original_flags": anchor["receipt_original_flags"], "directory_native_full9": list(directory_original)}
            self.main_file = _HeldArtifact(self.main_directory, desc, MAIN_RECEIPT, clock)
            self.receipt = _json(self.main_file.raw)
            self._receipt()
            self.root_directory = _directory("root-export")
            self.root_file = _HeldArtifact(self.root_directory, self.receipt["root_projection"], ROOT_PROJECTION, clock)
            body = _projection(self.root_file.raw, anchor["runtime_head"], self.receipt["actual_remote"])
            require(hash_bytes(self.root_file.raw) == anchor["projection_sha256"]
                and hash_payload(self.receipt["root_projection"]["native_full9"]) == anchor["projection_native_full9_sha256"], "main_original")
            historical = self.receipt["code_manifest"]
            require(set(historical) == set(code_paths()) and all(_digest(value) for value in historical.values())
                and hash_payload(historical) == body["code_manifest_sha256"], "main_code")
            for name, digest in historical.items():
                require(hash_bytes(p._git(["show", anchor["runtime_head"] + ":" + name])) == digest, "main_code")
            # OriginalReader consumes only the exported original seals. It does
            # not and cannot mint the vanished Root closure capability.
            historical_code = SimpleNamespace(manifest=historical)
            self.reader = _originals(anchor["runtime_head"], self.receipt["actual_remote"], body, historical_code, clock)
            self.config_directory, self.config = _config(anchor["runtime_head"], self.receipt["actual_remote"], body, historical_code)
            self.body = body
            public = _public_packet(self.receipt, self.main_file.descriptor)
            require(hash_bytes((canonical_json(public) + "\n").encode()) == anchor["outer_stdout_sha256"], "main_anchor_changed")
            self.validate()
        except BaseException:
            self.failed = True; self.close(); raise
    def _receipt(self):
        r = self.receipt
        keys = {"schema", "runtime_head", "actual_remote", "operation", "protocol_sha256", "native_policy_sha256", "storage_profile", "root_projection", "root_pid", "actual_root_exit", "root_stdout_sha256", "root_stderr_sha256", "root_ready_sha256", "root_closed_sha256", "command_sha256", "environment_sha256", "code_manifest", "root_context_snapshot_sha256", "native_inventory_sha256", "status", "authority"}
        require(set(r) == keys and r["schema"] == "si-native-main-counter-receipt-v1"
            and r["runtime_head"] == self.anchor["runtime_head"] and _head(r["actual_remote"])
            and r["protocol_sha256"] == PROTOCOL_SHA256 and r["native_policy_sha256"] == p._policy_sha(_profile())
            and r["storage_profile"] == p._profile_id(_profile()) and _exact(r["authority"], authority())
            and r["status"] == "candidate_requires_independent_outer_actual_exit_and_committed_anchor"
            and type(r["root_pid"]) is int and r["root_pid"] > 0
            and type(r["actual_root_exit"]) is int and r["actual_root_exit"] == 0
            and r["root_stderr_sha256"] == hash_bytes(b""), "main_shape")
        _descriptor(r["root_projection"], ROOT_PROJECTION)
        require(type(r["operation"]) is str and re.fullmatch(r"[0-9a-f]{32}", r["operation"]), "main_shape")
        for key in ("root_stdout_sha256", "root_stderr_sha256", "root_ready_sha256", "root_closed_sha256", "command_sha256", "environment_sha256", "root_context_snapshot_sha256", "native_inventory_sha256"):
            require(_digest(r[key]), "main_shape")
    def validate(self):
        def action():
            require(not self.closed, "main_closed"); self.clock.check(); self.code.audit()
            self.anchor_holder.audit()
            self.main_file.audit(); self.root_file.audit()
            self.reader.current_association(self.clock); self.reader.audit(); self.config.audit()
            require(self.receipt["root_context_snapshot_sha256"] == self.body["root_context_snapshot_sha256"]
                and self.receipt["native_inventory_sha256"] == self.body["native_inventory_sha256"], "main_binding")
            return True
        return self._run(action)
    def close(self):
        if self.closed: return
        first = None
        for item in (self.reader, self.config, self.main_file, self.root_file, self.main_directory, self.root_directory, self.config_directory, self.code, self.anchor_holder):
            if item is not None:
                try: item.close()
                except BaseException as error:
                    if first is None: first = error
        self.closed = True
        for item in (self.code, self.reader, self.config, self.main_file, self.root_file):
            if item is not None:
                try: item.audit(named=True) if type(item) is p._Inputs else item.named()
                except BaseException as error:
                    if first is None: first = error
        try: self.anchor_holder.named()
        except BaseException as error:
            if first is None: first = error
        try: self.clock.check()
        except BaseException as error:
            if first is None: first = error
        if first is not None: self.failed = True; raise first


@contextmanager
def load_registered(head, remote):
    """Held custody-only receipt; pending anchor refuses before private I/O."""
    _phase("loader"); clock = _Deadline(); registered(); p._guard(head, remote)
    anchor, anchor_holder = _anchor(head)
    code = loaded = None
    try:
        code = p._Code7(head, remote, clock)
        with p._source_denied():
            loaded = _Loaded(head, remote, clock, code, anchor, anchor_holder)
            value = object.__new__(AuthenticatedDurableMainReceipt)
            summary = {"status": "authenticated_durable_main_custody_observation", "runtime_head": anchor["runtime_head"],
                "receipt_sha256": anchor["receipt_sha256"], "projection_sha256": anchor["projection_sha256"], "authority": authority()}
            row = value, canonical_json(summary), loaded, sys._getframe()
            value._anchor = row; _AUTHENTICATED[id(value)] = row
            yield value
            loaded.validate()
    finally:
        if loaded is not None: loaded.close()
        else: _close_all((code, anchor_holder))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("root-export", "coordinate", "load"))
    parser.add_argument("--head", required=True); parser.add_argument("--remote", required=True)
    parser.add_argument("--operation")
    args = parser.parse_args(argv)
    try:
        if args.role == "root-export":
            root_export(args.head, args.remote, args.operation)
        elif args.role == "coordinate":
            print(canonical_json(coordinate_registered(args.head, args.remote, args.operation).public_summary()))
        else:
            with load_registered(args.head, args.remote) as receipt: print(canonical_json(receipt.public_summary()))
    except BaseException as error:
        _wire({"schema": "si-native-main-process-refusal-v1", "status": "refused", "role": args.role,
            "failure": failure_summary(error), "authority": authority()})
        return 2
    return 0


_PUMP_WAIT_CODE = next(item for item in _Pump.finish.__code__.co_consts if isinstance(item, CodeType) and item.co_name == "action")
_COORDINATE_CODE, _LOAD_CODE = coordinate_registered.__code__, load_registered.__wrapped__.__code__


if __name__ == "__main__":
    raise SystemExit(main())
