"""One prospective, source-free metadata observation outside Documents.

This does not admit a source, a native-supervision receipt, production storage,
or a backtest. Original kernel waits belong to the independent controller.
The controller must retain raw lines: JavaScript numbers cannot carry full9
nanosecond integers. Existing proofs, flags, files and claims are never adopted.
"""
import argparse
import errno
import json
import math
import os
from pathlib import Path
import re
import select
import stat
import sys
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import prove_short_interest_native_supervision as p

ROOT = p.ROOT
BASE = Path("/Users/sheltonchen/Library/Application Support/CodexShortInterestCustody")
NAMESPACE = "local-metadata-20261103-v1"
DRIVER = "scripts/prove_short_interest_local_metadata.py"
CODE_FILES = (*p.CODE_FILES, DRIVER)
SDK_SHA256 = "e477f8921c71410c36aa8c4b23e9c76f46aa68286b62bf2991882832b7a73237"
POLICY_SHA256 = "43088ee5abc1327c21a78013f3371ddf9b9cae3084f8ffedfc7afd6ed51c2a87"
LITERAL_NAME = "literal.json"
LITERAL = b'FIXED_SOURCE_FREE_CUSTODY_ATTRIBUTION_V1\n'
MAXIMUM_SECONDS, TAIL_SECONDS, INTERVAL = 300, 40, 0.25
MAXIMUM_WIRE, MAXIMUM_CONTROL_BYTES = 4096, 65536
CONTROL_ROLES = ("registration.private.json", "producer.sealed.private.json", "producer.closed.private.json",
    "observer.open.private.json", "observer.closed.private.json", "process.waits.private.json", "run.closed.json",
    "run.refused.json", "producer.refused.private.json", "observer.refused.private.json",
    "producer.process-refused.private.json", "observer.process-refused.private.json")
SCHEMA = "si-local-metadata-observation-v1"
_STAMP_NAMES = ("dev", "ino", "uid", "gid", "mode", "nlink", "size", "mtime_ns", "ctime_ns")
_STAGES = frozenset(("registration", "code", "ancestry", "creation", "seal", "handshake", "observation", "close", "terminal", "final_read", "control"))
_CODES = frozenset(("local_arguments", "local_policy", "local_code", "local_path", "local_directory", "local_exists",
    "local_host", "local_membership", "local_clock", "local_deadline", "local_latched", "local_wire",
    "local_handshake", "local_exit", "local_original", "local_flags", "local_bytes", "local_readonly", "local_accounting"))
_ERRNOS = {getattr(errno, name): name for name in ("EACCES", "EPERM", "ENOENT", "EEXIST", "EIO", "ENOSPC", "EROFS", "EINTR", "EBADF", "ELOOP")}
_STAGE, _USED, _COMPARISONS = "registration", False, {}


class LocalMetadataRefusal(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise LocalMetadataRefusal("REFUSED: " + code)


def _phase(stage):
    global _STAGE
    require(stage in _STAGES, "local_arguments")
    _STAGE = stage


def authority():
    return {"location_metadata_observation_only": True, "source_admitted": False,
        "source_dispatch_authority": False, "native_supervision_admitted": False,
        "durable_Main_receipt": False, "production_storage_admitted": False,
        "input_admitted": False, "ready_for_backtest": False, "historical_repair": False,
        "provider_HTTP": 0, "credential_reads": 0, "new_source_claims": 0,
        "source_STARTs": 0, "source_bytes": 0, "QC_or_Safari": False, "qc_attempts": 0}


def policy():
    return {"schema": "si-local-metadata-policy-v1", "root": str(ROOT), "base": str(BASE),
        "namespace": NAMESPACE, "directories": ["data", "control"], "literal_name": LITERAL_NAME,
        "literal_sha256": hash_bytes(LITERAL), "literal_bytes": len(LITERAL),
        "SDK_sha256": SDK_SHA256, "code_files": list(CODE_FILES), "maximum_seconds": MAXIMUM_SECONDS,
        "tail_seconds_after_controller_exit0": TAIL_SECONDS, "sample_seconds": INTERVAL,
        "maximum_wire_bytes": MAXIMUM_WIRE, "maximum_control_bytes": MAXIMUM_CONTROL_BYTES,
        "postexit_control_roles": list(CONTROL_ROLES), "each_control_bytes": 4096,
        "producer_count": 1, "observer_count": 1, "retry_count": 0,
        "ancestry": "original_nofollow_dev_ino_uid_gid_mode_nlink_root_or_owner_not_group_world_writable_private_0700_new_base_only",
        "directories_contract": "APFS_all_entry_nlink_exact_own_additions_empty_control_until_both_processes_exit_no_rebaseline",
        "host": "local_writable_APFS_ownership_enabled_not_native_mounted_volume_admission",
        "publisher": "unchanged_exact_original_p_Files_creator_RO_handoff_UF2_full9_bytes",
        "handshake": "bounded_raw_FD_lines_python_exact_integers_observer_original_RO_open_before_producer_ACK_owned_controller_wait0_then_40s_tail",
        "closure": "original_data_seal_through_all_code_directory_and_file_closes_final_named_full9_flags_bytes_no_unknown_exit_admission",
        "controls": "controller_only_after_both_actual_exits_fixed_roles_total_64KiB_no_publisher_or_registration_inside_Documents",
        "authority": authority()}


def registered():
    require(type(POLICY_SHA256) is str and re.fullmatch(r"[0-9a-f]{64}", POLICY_SHA256)
        and hash_payload(policy()) == POLICY_SHA256, "local_policy")
    require(BASE == Path("/Users/sheltonchen/Library/Application Support/CodexShortInterestCustody")
        and NAMESPACE == "local-metadata-20261103-v1" and CODE_FILES == (*p.CODE_FILES, DRIVER)
        and len(CODE_FILES) == 8 and len(set(CODE_FILES)) == 8, "local_policy")
    p._require_immutable_platform()


def failure_summary(error):
    code = None
    if type(error) is LocalMetadataRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((value for value in _CODES if args[0] == "REFUSED: " + value), None)
    number = OSError.errno.__get__(error, OSError) if isinstance(error, OSError) else None
    upstream = p.failure_summary(error)
    fields = _COMPARISONS.get(id(error))
    fields = list(fields[1]) if fields is not None and fields[0] is error else upstream["mismatching_fields"]
    return {"stage": _STAGE, "category": "local_contract_refusal" if code or upstream["contract_code"] or upstream["upstream_contract_code"] else "local_error",
        "contract_code": code, "publisher_contract_code": upstream["contract_code"],
        "upstream_contract_code": upstream["upstream_contract_code"],
        "errno_name": _ERRNOS.get(number), "mismatching_fields": fields}


def _same(actual, original):
    if actual != original:
        error = LocalMetadataRefusal("REFUSED: local_original")
        _COMPARISONS[id(error)] = error, tuple(name for name, a, b in zip(_STAMP_NAMES, actual, original) if a != b)
        raise error


class _Clock:
    def __init__(self):
        self.failed = False
        self.begin = self.last = time.monotonic()
        self.check()

    def check(self):
        require(not self.failed, "local_latched")
        try:
            now = time.monotonic()
            require(type(now) in (int, float) and math.isfinite(now)
                and 0 <= self.begin <= self.last <= now, "local_clock")
            require(now - self.begin <= MAXIMUM_SECONDS, "local_deadline")
            self.last = now
            return MAXIMUM_SECONDS - (now - self.begin)
        except BaseException:
            self.failed = True
            raise


class _Latched:
    def __init__(self):
        self.failed = False

    def _run(self, operation):
        require(not self.failed, "local_latched")
        try:
            return operation()
        except BaseException:
            self.failed = True
            raise


class _Code8(_Latched):
    """The original seven-file holder plus this new committed driver."""
    def __init__(self, head, remote, clock):
        super().__init__()
        self.head, self.remote, self.clock, self.fd, self.original = head, remote, clock, None, None
        self.old = p._Code7(head, remote, clock)
        try:
            self.fd = os.open(ROOT / DRIVER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            self.original = p._stamp(os.fstat(self.fd))
            # _Code7's genuine constructor has ALREADY read all seven original
            # committed files. Keep its exact issued mapping and live stamps;
            # do not immediately repeat the same expensive remote-Git sweep.
            self.manifest = self._run(lambda: self._eighth(self.old.manifest, initial=True))
        except BaseException:
            self.close()
            raise

    def audit(self, initial=False):
        return self._run(lambda: self._eighth(self.old.audit(), initial=initial))

    def _eighth(self, issued_manifest, *, initial):
        p._guard(self.head, self.remote)
        self.clock.check()
        self.old.named()
        require(type(issued_manifest) is dict and set(issued_manifest) == set(p.CODE_FILES)
            and all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) for value in issued_manifest.values())
            and issued_manifest.get(p.DRIVER) == SDK_SHA256, "local_code")
        manifest = issued_manifest.copy()
        require((ROOT / DRIVER).resolve() == ROOT / DRIVER, "local_path")
        _same(p._stamp(os.fstat(self.fd)), self.original)
        _same(p._stamp((ROOT / DRIVER).lstat()), self.original)
        require(stat.S_ISREG(os.fstat(self.fd).st_mode) and 0 < self.original[6] <= 1048576, "local_code")
        os.lseek(self.fd, 0, os.SEEK_SET)
        raw = os.read(self.fd, 1048577)
        require(raw == p._git(["show", self.head + ":" + DRIVER]), "local_code")
        if not initial:
            require(raw == self.raw, "local_code")
        self.raw = raw
        _same(p._stamp(os.fstat(self.fd)), self.original)
        self.old.named()
        manifest[DRIVER] = hash_bytes(raw)
        self.clock.check()
        return manifest

    def close(self):
        first = None
        for close in (lambda: p._close(self.fd) if self.fd is not None else None, self.old.close):
            try:
                close()
            except BaseException as error:
                if first is None:
                    first = error
        self.fd = None
        if first is not None:
            self.failed = True
            raise first

    def named(self):
        def action():
            self.old.named()
            _same(p._stamp((ROOT / DRIVER).lstat()), self.original)
        return self._run(action)


def _directory_pin(info, private=False):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid in (0, os.getuid())
        and not stat.S_IMODE(info.st_mode) & 0o022, "local_directory")
    if private:
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, "local_directory")
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink)


def _host(fd):
    native = p._native_statfs(fd)
    require(native["fstype"] == "apfs" and type(native["flags"]) is int
        and native["flags"] & p.native.MNT_LOCAL
        and not native["flags"] & (p.native.MNT_RDONLY | p.native.MNT_IGNORE_OWNERSHIP), "local_host")
    return (native["fsid"], native["fstype"], native["flags"], native["mounted_on"], native["mounted_from"])


class _Scope(_Latched):
    """All directory originals; only exact owned additions derive nlink."""
    def __init__(self, clock, *, create, originals=None):
        super().__init__()
        self.clock, self.rows, self.fds, self.files, self.closed = clock, [], [], None, False
        self.controls, self.control_literal = None, None
        self.bound_to_originals = originals is not None
        self.creating = create
        self.path = BASE / NAMESPACE
        try:
            require(Path.cwd().resolve() == ROOT and ROOT.resolve() == ROOT and BASE.is_absolute(), "local_path")
            current = Path(BASE.anchor)
            fd = os.open(current, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self._add(current, fd, False)
            for part in BASE.parts[1:-1]:
                current /= part
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fds[-1])
                self._add(current, fd, current == BASE.parent)
            self.host = _host(self.fds[-1])
            self._child(BASE.name, create=create)
            self._child(NAMESPACE, create=create)
            self.namespace_fd = self.fds[-1]
            namespace_row = self.rows[-1]
            self._child("data", create=create)
            self.data_fd = self.fds[-1]
            self._child("control", create=create, parent=namespace_row)
            self.control_fd = self.fds[-1]
            self.initials = tuple(row[2] for row in self.rows)
            if originals is not None:
                require(type(originals) is list and len(originals) == len(self.rows), "local_original")
                for row, original in zip(self.rows, originals):
                    require(type(original) is list and len(original) == 6 and all(type(v) is int for v in original), "local_original")
                    require(row[2] == tuple(original), "local_original")
            self.check()
        except BaseException:
            self.failed = True
            self.close()
            raise

    def _add(self, path, fd, private):
        self.fds.append(fd)
        pin = _directory_pin(os.fstat(fd), private)
        require(path.resolve() == path and pin == _directory_pin(path.lstat(), private), "local_path")
        self.rows.append([path, fd, pin, private])

    def _child(self, name, *, create, parent=None):
        self.clock.check()
        parent = self.rows[-1] if parent is None else parent
        require(_directory_pin(os.fstat(parent[1]), parent[3]) == parent[2], "local_directory")
        if create:
            try:
                os.stat(name, dir_fd=parent[1], follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise LocalMetadataRefusal("REFUSED: local_exists")
            os.mkdir(name, 0o700, dir_fd=parent[1])
            os.fsync(parent[1])
            parent[2] = (*parent[2][:-1], parent[2][-1] + 1)
            require(_directory_pin(os.fstat(parent[1]), parent[3]) == parent[2], "local_directory")
        path = parent[0] / name
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent[1])
        self._add(path, fd, True)

    def _expected(self, row):
        pin = row[2]
        if row[0] == self.path / "data" and self.files is not None:
            require(type(self.files) is p._Files and self.files.path == row[0]
                and set(self.files.originals) <= {LITERAL_NAME}, "local_membership")
            return (*pin[:-1], pin[-1] + len(self.files.originals))
        if row[0] == self.path / "control" and self.controls is not None:
            require(type(self.controls) is p._Files and self.controls.path == row[0]
                and self.controls.fd == self.control_fd and self.controls.parent == self.namespace_fd
                and self.controls.roles == frozenset(CONTROL_ROLES)
                and set(self.controls.originals) <= set(CONTROL_ROLES), "local_membership")
            return (*pin[:-1], pin[-1] + len(self.controls.originals))
        return pin

    def attach_control_publisher(self, literal):
        """Explicit controller phase, AFTER its independent original waits.

        This is only an original metadata publisher. No caller-supplied exit
        claim grants admission. Producer, observer and final_read never call
        this method, and continue to demand EMPTY control through closure.
        """
        def action():
            _phase("control")
            require(self.bound_to_originals and not self.creating and self.controls is None
                and type(literal) is _OriginalLiteral and literal.scope is self
                and literal.fd is not None and not literal.failed, "local_arguments")
            self.check(); literal.audit()
            self.control_literal = literal
            self.controls = p._Files(self.control_fd, self.namespace_fd, self.path / "control",
                self._control_callback, CONTROL_ROLES)
            return self.controls
        return self._run(action)

    def _control_callback(self):
        def action():
            self.check()
            require(type(self.control_literal) is _OriginalLiteral and self.control_literal.scope is self,
                "local_arguments")
            self.control_literal.audit()
        return self._run(action)

    def _control_originals(self, named):
        total = 0
        if self.controls is None:
            return
        for name, (fd, unused, original, raw) in self.controls.originals.items():
            info = (self.path / "control" / name).lstat() if named else os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and 0 <= info.st_size <= 4096, "local_accounting")
            total += info.st_size
            require(total <= MAXIMUM_CONTROL_BYTES, "local_accounting")
            # An in-progress genuine O_EXCL publication has not minted a seal.
            # It contributes its one known entry/bytes, never an old baseline.
            if original is None:
                require(not named and not self.controls.closed, "local_original")
                continue
            require(type(raw) is bytes and len(raw) == info.st_size, "local_bytes")
            _same(p._stamp(info), original)
            p._check_frozen(self.controls.creators.get(name), info)
            other = os.stat(name, dir_fd=self.control_fd, follow_symlinks=False) if not named else info
            _same(p._stamp(other), original)
            if named:
                read_fd = os.open(self.path / "control" / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            else:
                read_fd = fd
            try:
                _same(p._stamp(os.fstat(read_fd)), original)
                os.lseek(read_fd, 0, os.SEEK_SET)
                require(os.read(read_fd, len(raw) + 1) == raw, "local_bytes")
                _same(p._stamp(os.fstat(read_fd)), original)
                p._check_frozen(self.controls.creators.get(name), os.fstat(read_fd))
            finally:
                if named:
                    p._close(read_fd)
            _same(p._stamp((self.path / "control" / name).lstat()), original)
            p._check_frozen(self.controls.creators.get(name), (self.path / "control" / name).lstat())

    def _check(self, named=False):
        self.clock.check()
        require(Path.cwd().resolve() == ROOT and ROOT.resolve() == ROOT, "local_path")
        require(named or not self.closed, "local_directory")
        for row in self.rows:
            path, fd, unused, private = row
            expected = self._expected(row)
            require(path.resolve() == path and _directory_pin(path.lstat(), private) == expected, "local_directory")
            if not named:
                require(_directory_pin(os.fstat(fd), private) == expected, "local_directory")
        require(set(os.listdir(BASE)) == {NAMESPACE} and set(os.listdir(self.path)) == {"data", "control"}, "local_membership")
        expected_controls = set(self.controls.originals) if self.controls is not None else set()
        require(set(os.listdir(self.path / "control")) == expected_controls, "local_membership")
        self._control_originals(named or self.controls is not None and self.controls.closed)
        expected = set(self.files.originals) if self.files is not None else (set() if self.creating else {LITERAL_NAME})
        require(set(os.listdir(self.path / "data")) == expected, "local_membership")
        if not named:
            require(_host(self.namespace_fd) == self.host, "local_host")
        else:
            # All original directory FDs are closed. A new read can only
            # compare with the ORIGINAL identity/protections; it cannot adopt
            # a remount or a new host baseline.
            original = next(self._expected(row) for row in self.rows if row[0] == self.path)
            fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                require(_directory_pin(os.fstat(fd), True) == original, "local_directory")
                require(_host(fd) == self.host, "local_host")
            finally:
                p._close(fd)
            require(_directory_pin(self.path.lstat(), True) == original, "local_directory")

    def check(self):
        return self._run(lambda: self._check())

    def named(self):
        return self._run(lambda: self._check(named=True))

    def wire_originals(self):
        self.check()
        return [list(self._expected(row)) for row in self.rows]

    def close(self):
        first = None
        try:
            if self.controls is not None and not self.controls.closed:
                self.controls.close()
        except BaseException as error:
            first = error
        try:
            p._drain(self.fds)
        except BaseException as error:
            if first is None:
                first = error
        finally:
            self.closed = True
        if first is not None:
            self.failed = True
            raise first


class _OriginalLiteral(_Latched):
    def __init__(self, scope, original, flags):
        super().__init__()
        require(type(original) in (tuple, list) and len(original) == 9
            and all(type(v) is int and v >= 0 for v in original), "local_original")
        require(type(flags) is int and 0 <= flags < 2 ** 32 and flags & p.UF_IMMUTABLE, "local_flags")
        self.scope, self.original, self.flags, self.fd = scope, tuple(original), flags, None
        try:
            self.fd = os.open(LITERAL_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=scope.data_fd)
            require(p._descriptor_access(self.fd) == os.O_RDONLY and os.get_inheritable(self.fd) is False, "local_readonly")
            self.audit()
        except BaseException:
            self.failed = True
            self.close()
            raise

    def _info(self, info):
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1, "local_original")
        _same(p._stamp(info), self.original)
        require(p._file_flags(info) == self.flags and self.flags & p.UF_IMMUTABLE, "local_flags")

    def audit(self):
        def action():
            self.scope.check()
            self._info(os.fstat(self.fd))
            self._info(os.stat(LITERAL_NAME, dir_fd=self.scope.data_fd, follow_symlinks=False))
            os.lseek(self.fd, 0, os.SEEK_SET)
            require(os.read(self.fd, len(LITERAL) + 1) == LITERAL, "local_bytes")
            self._info(os.fstat(self.fd))
            self.scope.check()
        return self._run(action)

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            try:
                p._close(fd)
            except BaseException:
                self.failed = True
                raise

    def named(self):
        def action():
            self.scope.named() if self.scope.closed else self.scope.check()
            path = self.scope.path / "data" / LITERAL_NAME
            self._info(path.lstat())
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                require(p._descriptor_access(fd) == os.O_RDONLY, "local_readonly")
                self._info(os.fstat(fd))
                require(os.read(fd, len(LITERAL) + 1) == LITERAL, "local_bytes")
                self._info(os.fstat(fd))
            finally:
                p._close(fd)
            self._info(path.lstat())
            self.scope.named() if self.scope.closed else self.scope.check()
        return self._run(action)


class _Lines(_Latched):
    """One raw descriptor and one bounded pending buffer; no TextIO buffering."""
    def __init__(self, fd, clock):
        super().__init__()
        self.fd, self.clock, self.pending, self.total = fd, clock, bytearray(), 0

    def read(self):
        def action():
            while True:
                self.clock.check()
                index = self.pending.find(b"\n")
                if index >= 0:
                    require(index + 1 <= MAXIMUM_WIRE, "local_wire")
                    raw = bytes(self.pending[:index + 1])
                    del self.pending[:index + 1]
                    return raw
                require(len(self.pending) < MAXIMUM_WIRE, "local_wire")
                ready, unused, unused2 = select.select([self.fd], [], [], min(1.0, self.clock.check()))
                if not ready:
                    continue
                block = os.read(self.fd, min(4096, MAXIMUM_WIRE - len(self.pending)))
                require(type(block) is bytes and block, "local_wire")
                self.total += len(block)
                require(self.total <= MAXIMUM_CONTROL_BYTES, "local_wire")
                self.pending.extend(block)
        return self._run(action)

    def finish(self):
        """The controller closes stdin after its last packet; extras refuse."""
        def action():
            require(not self.pending, "local_wire")
            while True:
                self.clock.check()
                ready, unused, unused2 = select.select([self.fd], [], [], min(1.0, self.clock.check()))
                if ready:
                    require(os.read(self.fd, 1) == b"", "local_wire")
                    return
        return self._run(action)


def _decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAXIMUM_WIRE and raw.endswith(b"\n") and raw.count(b"\n") == 1, "local_wire")
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, "local_wire")
            result[key] = value
        return result
    def number(unused):
        raise LocalMetadataRefusal("REFUSED: local_wire")
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=number)
    except (ValueError, UnicodeError):
        raise LocalMetadataRefusal("REFUSED: local_wire") from None
    require(type(value) is dict and (canonical_json(value) + "\n").encode() == raw, "local_wire")
    return value


def _emit(value, fd=1):
    raw = (canonical_json(value) + "\n").encode()
    require(len(raw) <= MAXIMUM_WIRE, "local_wire")
    p._write(fd, raw)
    return raw


def _binding(head, remote, operation):
    require(all(type(v) is str and re.fullmatch(r"[0-9a-f]{40}", v) for v in (head, remote))
        and type(operation) is str and re.fullmatch(r"[0-9a-f]{64}", operation), "local_arguments")
    return {"schema": SCHEMA, "operation": operation, "runtime_head": head,
        "actual_remote": remote, "policy_sha256": POLICY_SHA256, "authority": authority()}


def _exact(actual, expected):
    """JSON equality that never aliases booleans and numeric counters."""
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return set(actual) == set(expected) and all(type(key) is str
            and _exact(actual[key], expected[key]) for key in expected)
    if type(expected) in (list, tuple):
        return len(actual) == len(expected) and all(_exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _original_packet_fields(value):
    require(type(value.get("pid")) is int and value["pid"] > 0
        and type(value.get("original9")) is list and len(value["original9"]) == 9
        and all(type(item) is int and item >= 0 for item in value["original9"])
        and type(value.get("flags")) is int and 0 <= value["flags"] < 2 ** 32
        and value["flags"] & p.UF_IMMUTABLE, "local_handshake")
    if "literal_bytes" in value:
        require(type(value["literal_bytes"]) is int and value["literal_bytes"] == len(LITERAL), "local_handshake")


def _packet(raw, binding, event, extra):
    value = _decode(raw)
    require(set(value) == set(binding) | {"event", *extra}
        and all(_exact(value.get(k), v) for k, v in binding.items())
        and type(value["event"]) is str and value["event"] == event, "local_handshake")
    return value


def _start(head, remote, operation):
    global _USED
    require(not _USED, "local_latched")
    _USED = True
    _phase("registration")
    clock = _Clock()
    require(Path.cwd().resolve() == ROOT and ROOT.resolve() == ROOT, "local_path")
    binding = _binding(head, remote, operation)
    registered()
    p._guard(head, remote)
    clock.check()
    _phase("code")
    return binding, clock, _Code8(head, remote, clock)


def producer(head, remote, operation, *, input_fd=0, output_fd=1):
    binding, clock, code = _start(head, remote, operation)
    scope, files, original, flags = None, None, None, None
    published = None
    try:
        with p._source_denied():
            _phase("ancestry")
            scope = _Scope(clock, create=True)
            files = p._Files(scope.data_fd, scope.namespace_fd, scope.path / "data", scope.check, (LITERAL_NAME,))
            scope.files = files
            _phase("creation")
            published = 0
            try:
                files.write(LITERAL_NAME, LITERAL)
            except BaseException:
                # A partial create may precede the publisher's own bookkeeping.
                # Never infer a completed publication or a zero debit from it.
                published = None
                raise
            published = 1
            _phase("seal")
            files.audit()
            original = tuple(files.originals[LITERAL_NAME][2])
            flags = p._file_flags(os.fstat(files.originals[LITERAL_NAME][0]))
            code.audit()
            sealed = {**binding, "event": "producer_sealed", "pid": os.getpid(),
                "original9": list(original), "flags": flags, "literal_sha256": hash_bytes(LITERAL),
                "literal_bytes": len(LITERAL), "directory_pins": scope.wire_originals(), "code_manifest": code.manifest}
            raw = _emit(sealed, output_fd)
            _phase("handshake")
            reader = _Lines(input_fd, clock)
            opened = _packet(reader.read(), binding, "observer_open", ("pid", "producer_raw_sha256"))
            require(type(opened["pid"]) is int and opened["pid"] > 0 and opened["pid"] != os.getpid()
                and opened["producer_raw_sha256"] == hash_bytes(raw), "local_handshake")
            reader.finish()
            _phase("close")
            files.audit(); files.close(); files.named(); scope.check()
            code.audit(); code.close(); code.named(); files.named(); scope.check()
            scope.close(); scope.named(); files.named(); clock.check()
            _phase("terminal")
            _emit({**binding, "event": "producer_closed", "pid": os.getpid(),
                "producer_raw_sha256": hash_bytes(raw), "original9": list(original), "flags": flags,
                "code_manifest": code.manifest, "published": published,
                "closure": "all_original_publisher_code_and_directory_handles_closed_named_audited"}, output_fd)
    except BaseException as error:
        _emit({**binding, "event": "producer_refused", "diagnostic": failure_summary(error),
            "literal_publications": published, "creation_accounting": "unknown" if published is None else "observed",
            "success": False}, output_fd)
        raise
    finally:
        # Cleanup never changes files/flags/names. Any failed close remains a failure.
        if files is not None and not files.closed:
            files.close()
        if scope is not None and not scope.closed:
            scope.close()
        if code.fd is not None:
            code.close()


def observer(head, remote, operation, *, input_fd=0, output_fd=1):
    binding, clock, code = _start(head, remote, operation)
    scope, literal = None, None
    try:
        with p._source_denied():
            reader = _Lines(input_fd, clock)
            _phase("handshake")
            producer_raw = reader.read()
            sealed = _packet(producer_raw, binding, "producer_sealed",
                ("pid", "original9", "flags", "literal_sha256", "literal_bytes", "directory_pins", "code_manifest"))
            _original_packet_fields(sealed)
            require(sealed["pid"] != os.getpid()
                and sealed["literal_sha256"] == hash_bytes(LITERAL) and sealed["literal_bytes"] == len(LITERAL)
                and _exact(sealed["code_manifest"], code.manifest), "local_handshake")
            _phase("ancestry")
            scope = _Scope(clock, create=False, originals=sealed["directory_pins"])
            literal = _OriginalLiteral(scope, sealed["original9"], sealed["flags"])
            _emit({**binding, "event": "observer_open", "pid": os.getpid(), "producer_raw_sha256": hash_bytes(producer_raw)}, output_fd)
            _phase("handshake")
            closed_raw = reader.read()
            closed = _packet(closed_raw, binding, "producer_closed", ("pid", "producer_raw_sha256", "original9", "flags", "code_manifest", "published", "closure"))
            _original_packet_fields(closed)
            require(closed["pid"] == sealed["pid"] and closed["producer_raw_sha256"] == hash_bytes(producer_raw)
                and _exact(closed["original9"], sealed["original9"]) and _exact(closed["flags"], sealed["flags"])
                and _exact(closed["code_manifest"], code.manifest) and type(closed["published"]) is int and closed["published"] == 1
                and closed["closure"] == "all_original_publisher_code_and_directory_handles_closed_named_audited", "local_handshake")
            terminal = _packet(reader.read(), binding, "producer_exit", ("pid", "returncode"))
            require(type(terminal["pid"]) is int and terminal["pid"] == sealed["pid"]
                and type(terminal["returncode"]) is int and terminal["returncode"] == 0, "local_exit")
            reader.finish()
            _phase("observation")
            begin = time.monotonic()
            samples = 0
            while True:
                literal.audit(); samples += 1
                now = time.monotonic(); clock.check()
                require(now >= begin, "local_clock")
                if now - begin >= TAIL_SECONDS:
                    break
                time.sleep(min(INTERVAL, TAIL_SECONDS - (now - begin)))
            _phase("close")
            literal.audit(); literal.close(); literal.named(); scope.check()
            code.audit(); code.close(); code.named(); literal.named(); scope.check()
            scope.close(); scope.named(); literal.named(); clock.check()
            _phase("terminal")
            _emit({**binding, "event": "observer_closed", "pid": os.getpid(),
                "producer_pid": sealed["pid"], "producer_raw_sha256": hash_bytes(producer_raw),
                "producer_closed_raw_sha256": hash_bytes(closed_raw), "original9": list(literal.original),
                "flags": literal.flags, "code_manifest": code.manifest, "samples": samples,
                "tail_seconds": TAIL_SECONDS, "closure": "all_original_observer_code_and_directory_handles_closed_named_audited",
                "controller_exit0_is_an_observation_claim_until_owned_wait_correlated": True}, output_fd)
    except BaseException as error:
        _emit({**binding, "event": "observer_refused", "diagnostic": failure_summary(error), "success": False}, output_fd)
        raise
    finally:
        if literal is not None and literal.fd is not None:
            literal.close()
        if scope is not None and not scope.closed:
            scope.close()
        if code.fd is not None:
            code.close()


def final_read(head, remote, operation, producer_raw):
    """A fresh read of the ORIGINAL seal; caller bytes never grant authority.

    Call before controller writes any control file. The controller separately
    correlates both genuine process waits; this read cannot mint those waits.
    """
    with p._source_denied():
        return _final_read(head, remote, operation, producer_raw)


def _final_read(head, remote, operation, producer_raw):
    binding, clock, code = _start(head, remote, operation)
    scope, literal = None, None
    try:
        _phase("final_read")
        sealed = _packet(producer_raw, binding, "producer_sealed",
            ("pid", "original9", "flags", "literal_sha256", "literal_bytes", "directory_pins", "code_manifest"))
        _original_packet_fields(sealed)
        require(sealed["literal_sha256"] == hash_bytes(LITERAL) and sealed["literal_bytes"] == len(LITERAL)
            and _exact(sealed["code_manifest"], code.manifest), "local_handshake")
        scope = _Scope(clock, create=False, originals=sealed["directory_pins"])
        literal = _OriginalLiteral(scope, sealed["original9"], sealed["flags"])
        literal.audit(); literal.close(); literal.named(); code.audit(); code.close(); code.named()
        literal.named(); scope.close(); scope.named(); literal.named(); clock.check()
        return {**binding, "status": "original_local_literal_read_after_both_external_waits_still_required",
            "producer_raw_sha256": hash_bytes(producer_raw), "authority": authority()}
    finally:
        if literal is not None and literal.fd is not None:
            literal.close()
        if scope is not None and not scope.closed:
            scope.close()
        if code.fd is not None:
            code.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("producer", "observer"))
    parser.add_argument("--head", required=True)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--operation", required=True)
    args = parser.parse_args(argv)
    try:
        (producer if args.role == "producer" else observer)(args.head, args.remote, args.operation)
    except BaseException as error:
        _emit({"schema": SCHEMA, "event": "process_refused", "role": args.role,
            "diagnostic": failure_summary(error), "success": False, "authority": authority()})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
