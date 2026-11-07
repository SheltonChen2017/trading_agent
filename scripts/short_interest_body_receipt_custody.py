"""NEW synthetic body/receipt custody; neither capture nor budget settlement.

The old 1024-byte creators remain unchanged. Only this factory's two exclusive
inodes receive bytes. Original seals, failures and terminal witnesses cannot
be reconstructed from caller fields. Caller OwnedOutput lifetime is external.
"""
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
import re
import stat
from types import CodeType
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_immutable_metadata as immutable

creator, cache, _OwnedOutput = immutable.creator, immutable.creator.cache, immutable.creator._OwnedOutput
BODY_NAME, RECEIPT_NAME = "attempt-body.raw", "attempt-receipt.private.json"
MAXIMUM_BODY_BYTES, MAXIMUM_RECEIPT_BYTES = 2 * 1024 ** 2, 1024
MAXIMUM_SECONDS, MAXIMUM_SAMPLES, SAMPLE_SECONDS, QUIET_SECONDS = 8.0, 16, .25, 1.0
_BINDINGS, _FILES, _CHOICES, _SEALS, _FILE_ISSUED, _PAIRS, _PAIR_ISSUED = {}, {}, {}, {}, {}, {}, {}
_FILE_STATES, _PAIR_PHASES = {}, {}
_FAILED, _ATTEMPTED = set(), set()
_OS_TYPES = (OSError, FileExistsError, FileNotFoundError, PermissionError, IsADirectoryError,
    NotADirectoryError, BlockingIOError, InterruptedError, TimeoutError)
_OS_ERRNOS = {getattr(errno, name): name for name in ("ENOSPC", "EIO", "EACCES", "EPERM",
    "EEXIST", "ENOENT", "EBADF", "EINVAL", "ENOTSUP", "EMFILE", "ENFILE")}
_CODES = frozenset("""body_receipt_policy_changed body_receipt_factory_required
body_receipt_binding_changed body_receipt_latched_failure body_receipt_bounds_refused
body_receipt_owned_changed body_receipt_inode_changed body_receipt_size_or_mtime_changed
body_receipt_flags_changed body_receipt_bytes_changed body_receipt_stamp_changed
body_receipt_clock_refused body_receipt_window_exhausted body_receipt_samples_exhausted
body_receipt_seal_once_required body_receipt_not_live body_receipt_not_closed
body_receipt_write_progress_changed body_receipt_readonly_required body_receipt_initial_flags_refused
body_receipt_membership_changed body_receipt_receipt_changed body_receipt_role_changed
body_receipt_held_choice_changed""".split())


class BodyReceiptRefusal(ValueError):
    pass


def require(value, code):
    if not value: raise BodyReceiptRefusal("REFUSED: " + code)


def failure_summary(error):
    if type(error) in _OS_TYPES:
        number = OSError.errno.__get__(error, OSError)
        return {"category": "local_os_error", "errno_name": _OS_ERRNOS.get(number) if type(number) is int else None,
            "contract_code": None}
    if type(error) is not BodyReceiptRefusal: return immutable.failure_summary(error)
    args = BaseException.args.__get__(error, BaseException)
    code = next((name for name in _CODES if type(args) is tuple and len(args) == 1
        and type(args[0]) is str and args[0] == "REFUSED: " + name), None)
    return {"category": "local_contract_refusal", "errno_name": None, "contract_code": code}


def authority():
    return {"custody_only": True, "synthetic_only": True, "source_admitted": False,
        "budget_release_authority": False, "dispatch_authority": False, "provider_HTTP": 0,
        "credential_reads": 0, "source_START_debits": 0, "source_charged_bytes": 0,
        "ready_for_backtest": False, "outcome_looks": 0, "qc_attempts": 0}


def policy():
    return {"schema": "si-new-body-receipt-custody-policy-v1", "body_name": BODY_NAME,
        "receipt_name": RECEIPT_NAME, "maximum_body_bytes": MAXIMUM_BODY_BYTES,
        "maximum_receipt_bytes": MAXIMUM_RECEIPT_BYTES, "per_file_seconds": MAXIMUM_SECONDS,
        "per_file_samples": MAXIMUM_SAMPLES, "sample_seconds": SAMPLE_SECONDS,
        "quiet_seconds": QUIET_SECONDS, "initial_flags": [0, 64], "target_flags": [2, 66],
        "kernel_policy_sha256": hash_payload(immutable.policy()),
        "seal": "one_original_HeldFiles_per_file_original8_plus_exact_flags9_never_rebaseline",
        "closure": "both_original_file_contexts_then_original_dup_bytes_stamps_close_and_named_stamps",
        "caller_context_closure_required_separately": True, "authority": authority()}


def _check_policy():
    current = (BODY_NAME, RECEIPT_NAME, MAXIMUM_BODY_BYTES, MAXIMUM_RECEIPT_BYTES,
        MAXIMUM_SECONDS, MAXIMUM_SAMPLES, SAMPLE_SECONDS, QUIET_SECONDS)
    expected = ("attempt-body.raw", "attempt-receipt.private.json", 2097152, 1024, 8.0, 16, .25, 1.0)
    require(all(type(value) is type(wanted) and value == wanted for value, wanted in zip(current, expected))
        and hash_payload(policy()) == _POLICY_SHA,
        "body_receipt_policy_changed")
    immutable._platform()


class BodyReceiptBinding:
    __slots__ = ("_parts", "_identity")
    def __init__(self): raise BodyReceiptRefusal("REFUSED: body_receipt_factory_required")
    def __repr__(self): return "<BodyReceiptBinding redacted>"
    @property
    def sha256(self): return _binding_anchor(self)[2]
    def to_payload(self): return json.loads(_binding_anchor(self)[1])


def _binding_anchor(binding):
    _check_policy()
    saved = _BINDINGS.get(binding) if type(binding) is BodyReceiptBinding else None
    try: parts, identity = binding._parts, binding._identity
    except AttributeError: parts, identity = None, None
    require(type(saved) is tuple and saved is parts is identity and saved[0] is binding,
        "body_receipt_binding_changed")
    return saved


def freeze_body_receipt_binding(*, request_sha256, attempt_sha256, reservation_sha256, protocol_sha256):
    _check_policy()
    values = dict(request_sha256=request_sha256, attempt_sha256=attempt_sha256,
        reservation_sha256=reservation_sha256, protocol_sha256=protocol_sha256)
    require(all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) for value in values.values()),
        "body_receipt_binding_changed")
    raw = canonical_json(values).encode(); value = object.__new__(BodyReceiptBinding)
    value._parts = value._identity = value, raw, hash_bytes(raw)
    _BINDINGS[value] = value._parts; return value


def _utc_now(): return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _clock(raw):
    try: return cache.parallel.clock(raw)
    except Exception: raise BodyReceiptRefusal("REFUSED: body_receipt_clock_refused") from None


def _receipt(binding, body, started, built):
    require(_clock(started) <= _clock(built), "body_receipt_clock_refused")
    raw = canonical_json({"schema": "si-new-body-receipt-v1", "roles": ["body", "receipt"],
        "binding_sha256": binding.sha256, "binding": binding.to_payload(), "body_name": BODY_NAME,
        "body_sha256": hash_bytes(body), "body_bytes": len(body),
        "creation_started_at": started, "receipt_built_at": built,
        "source_admitted": False, "budget_release_authority": False}).encode()
    require(0 < len(raw) <= MAXIMUM_RECEIPT_BYTES, "body_receipt_bounds_refused")
    return raw


def _latch(value):
    if type(value) in (BodyReceiptFileCustody, BodyReceiptCustody): _FAILED.add(value)


def _file_anchor(file_cap): return file_cap._binding()[0]


def _file_state(cap, state):
    saved = _FILE_STATES.get(cap)
    require(type(state) is dict and type(saved) is tuple and tuple(state) == tuple(name for name, unused in saved)
        and all(state[name] is original for name, original in saved), "body_receipt_binding_changed")


def _update_file(cap, **changes):
    state = _FILES[cap][1]; _file_state(cap, state)
    state.update(changes); _FILE_STATES[cap] = tuple(state.items())


def _close_all(descriptors):
    first = None
    while descriptors:
        fd = descriptors.pop()
        try: os.close(fd)
        except BaseException as error:
            if first is None: first = error
    if first is not None: raise first


def _pair(origin, expected=None):
    info = os.fstat(origin[7]), os.stat(origin[3], dir_fd=origin[6], follow_symlinks=False)
    for item in info:
        require(stat.S_ISREG(item.st_mode) and creator._stamp(item)[:5] == origin[8][:5]
            and item.st_uid == os.getuid() and stat.S_IMODE(item.st_mode) == 0o600 and item.st_nlink == 1,
            "body_receipt_inode_changed")
        require(creator._stamp(item)[5:7] == origin[8][5:7], "body_receipt_size_or_mtime_changed")
        require(immutable._flags(item) == origin[10], "body_receipt_flags_changed")
        if expected is not None: require(immutable._stamp(item) == expected, "body_receipt_stamp_changed")
    return tuple(immutable._stamp(item) for item in info)


def _read_original(origin, fd, expected, *, named=True, allow_ctime=False, creation_tick=None):
    require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY, "body_receipt_readonly_required")
    def check():
        if creation_tick is not None: creation_tick()
        for info in ((os.fstat(fd), os.stat(origin[3], dir_fd=origin[6], follow_symlinks=False))
                if named else (os.fstat(fd),)):
            observed = immutable._stamp(info)
            require((observed[:7] + observed[8:] == expected[:7] + expected[8:] if allow_ctime
                else observed == expected) and stat.S_ISREG(info.st_mode), "body_receipt_stamp_changed")
    check(); os.lseek(fd, 0, os.SEEK_SET); length, digest = 0, hashlib.sha256()
    while True:
        check(); part = os.read(fd, min(65536, len(origin[4]) + 1 - length))
        require(type(part) is bytes, "body_receipt_bytes_changed")
        if not part: break
        require(part == origin[4][length:length + len(part)], "body_receipt_bytes_changed")
        digest.update(part); length += len(part)
        require(length <= len(origin[4]), "body_receipt_bytes_changed")
    check(); require(length == len(origin[4]) and digest.hexdigest() == origin[5], "body_receipt_bytes_changed")
    require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY, "body_receipt_readonly_required")


class BodyReceiptFileCustody:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise BodyReceiptRefusal("REFUSED: body_receipt_factory_required")
    def __repr__(self): return "<BodyReceiptFileCustody redacted>"
    def _binding(self, *, failed=False):
        saved = _FILES.get(self) if type(self) is BodyReceiptFileCustody else None
        try: origin, identity = self._anchor, self._identity
        except AttributeError: origin, identity = None, None
        require(type(saved) is tuple and len(saved) == 4 and saved[0] is origin is identity,
            "body_receipt_binding_changed")
        require(failed or self not in _FAILED, "body_receipt_latched_failure")
        state, binding, scope = saved[1:]; _file_state(self, state); _binding_anchor(binding)
        require(type(state) is dict and state["phase"] in {"UNSEALED", "SEALING", "SEALED", "CLOSED"}
            and (state["phase"] == "CLOSED") is (self in _FILE_ISSUED), "body_receipt_binding_changed")
        choice, sealed = _CHOICES.get(self), _SEALS.get(self)
        require(state["choice"] is choice and (sealed is None or state["held"] is sealed[1]), "body_receipt_binding_changed")
        require(scope == _POLICY_SHA and origin[0]._anchor is origin[1], "body_receipt_binding_changed")
        return origin, state
    def _tick(self):
        origin, state = self._binding(); now = origin[13]()
        require(creator._valid_tick(now) and now >= state["last_tick"], "body_receipt_clock_refused")
        require(now - origin[12] <= MAXIMUM_SECONDS, "body_receipt_window_exhausted")
        _update_file(self, last_tick=now); return now
    def _boundary(self):
        origin, state = self._binding()
        require(type(origin[0]) is _OwnedOutput and origin[0]._anchor is origin[1], "body_receipt_owned_changed")
        for check in (origin[0].check, origin[11], origin[0].check):
            check()
            if state["phase"] in {"UNSEALED", "SEALING"}: self._tick()
    def _strict(self):
        origin, state = self._binding(); self._boundary()
        require(state["choice"] is not None, "body_receipt_not_live")
        _pair(origin, state["choice"]); _read_original(origin, origin[7], state["choice"]); _pair(origin, state["choice"])
    def seal_once(self):
        try:
            origin, state = self._binding(); _check_policy()
            require(self not in _ATTEMPTED and state["phase"] == "UNSEALED", "body_receipt_seal_once_required")
            _ATTEMPTED.add(self); prior, quiet_at = None, None
            for number in range(1, MAXIMUM_SAMPLES + 1):
                if number > 1: origin[14](SAMPLE_SECONDS); self._tick()
                self._boundary(); before = _pair(origin)
                _read_original(origin, origin[7], before[0], allow_ctime=True, creation_tick=self._tick); after = _pair(origin)
                now = self._tick(); candidate = after[-1]
                stable = all(item == candidate for item in (*before, *after))
                if not stable or candidate != prior: quiet_at = now if stable else None
                quiet = 0 if quiet_at is None else now - quiet_at
                _update_file(self, samples=(*state["samples"], (number, stable, min(8000, int(quiet * 1000)))))
                prior = candidate
                if stable and quiet >= QUIET_SECONDS:
                    _CHOICES[self] = candidate; _update_file(self, choice=candidate, phase="SEALING")
                    held = cache.HeldFiles((origin[1][0] / origin[3],), protected=True, boundary=self._strict)
                    _SEALS[self] = candidate, held; _update_file(self, held=held)
                    require(held._anchor[1][0][3] == (candidate[0], candidate[1], candidate[5], candidate[6], candidate[7])
                        and held._anchor[1][0][4:6] == candidate[2:4], "body_receipt_held_choice_changed")
                    _update_file(self, phase="SEALED"); self.check(); self._tick(); return self
            raise BodyReceiptRefusal("REFUSED: body_receipt_samples_exhausted")
        except BaseException: _latch(self); raise
    def check(self):
        try:
            origin, state = self._binding(); _check_policy()
            require(state["phase"] == "SEALED" and self in _SEALS, "body_receipt_not_live")
            self._strict(); state["held"].check()
            require(state["held"].read(origin[1][0] / origin[3], len(origin[4])) == origin[4], "body_receipt_bytes_changed")
            self._strict()
        except BaseException: _latch(self); raise


@contextmanager
def _prepare_original_file(owned, role, raw, *, binding, boundary, monotonic, sleep):
    """The ONLY native caller. Its exact origin/frame is monitor-authenticated."""
    _binding_anchor(binding); _check_policy()
    require(type(role) is str and role in ("body", "receipt"), "body_receipt_role_changed")
    name = BODY_NAME if role == "body" else RECEIPT_NAME
    maximum = MAXIMUM_BODY_BYTES if role == "body" else MAXIMUM_RECEIPT_BYTES
    require(role in ("body", "receipt") and type(raw) is bytes and 0 < len(raw) <= maximum,
        "body_receipt_bounds_refused")
    began, last = monotonic(), [None]
    require(creator._valid_tick(began), "body_receipt_clock_refused")
    def tick():
        now = monotonic()
        require(creator._valid_tick(now) and began <= now and (last[0] is None or last[0] <= now), "body_receipt_clock_refused")
        require(now - began <= MAXIMUM_SECONDS, "body_receipt_window_exhausted"); last[0] = now
    file_cap, origin, writer, reader, held = None, None, None, None, None
    def guarded_boundary():
        boundary()
        if file_cap is not None:
            require(_file_anchor(file_cap) is origin, "body_receipt_binding_changed")
            state = _FILES[file_cap][1]
            if state["flag_set"]: _pair(origin, state["choice"])
        if file_cap is None or _FILES[file_cap][1]["phase"] in {"UNSEALED", "SEALING"}: tick()
    try:
        require(type(owned) is _OwnedOutput, "body_receipt_owned_changed")
        owned.check(); guarded_boundary(); original_owned = owned._anchor; dirfd = original_owned[2]
        writer = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dirfd)
        os.fchmod(writer, 0o600); tick(); created = creator._stamp(os.fstat(writer)); offset = 0
        while offset < len(raw):
            owned.check(); guarded_boundary()
            for info in (os.fstat(writer), os.stat(name, dir_fd=dirfd, follow_symlinks=False)):
                creator._protected(info, created); require(info.st_size == offset, "body_receipt_write_progress_changed")
            amount = os.write(writer, memoryview(raw)[offset:]); tick()
            require(type(amount) is int and 0 < amount <= len(raw) - offset, "body_receipt_write_progress_changed"); offset += amount
        os.fsync(writer); os.fsync(dirfd); tick(); creation = creator._stamp(os.fstat(writer))
        reader = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dirfd)
        require(fcntl.fcntl(reader, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY, "body_receipt_readonly_required")
        for info in (os.fstat(reader), os.stat(name, dir_fd=dirfd, follow_symlinks=False)):
            creator._protected(info, creation); require(creator._stamp(info)[5:7] == creation[5:7], "body_receipt_size_or_mtime_changed")
        os.close(writer); writer = None; tick()
        initial = immutable._flags(os.fstat(reader)), immutable._flags(os.stat(name, dir_fd=dirfd, follow_symlinks=False))
        require(initial[0] == initial[1] and initial[0] in (0, 64), "body_receipt_initial_flags_refused")
        initial_flags, target = initial[0], initial[0] | 2
        file_cap = object.__new__(BodyReceiptFileCustody)
        origin = (owned, original_owned, role, name, raw, hash_bytes(raw), dirfd, reader, creation,
            initial_flags, target, guarded_boundary, began, monotonic, sleep)
        file_cap._anchor = file_cap._identity = origin
        state = {"phase": "UNSEALED", "choice": None, "held": None, "samples": (), "last_tick": last[0], "flag_set": False}
        _FILES[file_cap] = origin, state, binding, _POLICY_SHA
        _FILE_STATES[file_cap] = tuple(state.items())
        # No byte/clock/field adoption: verify original raw before the sole setter.
        _read_original(origin, reader, (*creation, initial_flags), allow_ctime=True, creation_tick=file_cap._tick)
        file_cap._tick()
        for info in (os.fstat(reader), os.stat(name, dir_fd=dirfd, follow_symlinks=False)):
            require(creator._stamp(info)[:7] == creation[:7] and immutable._flags(info) == initial_flags,
                "body_receipt_initial_flags_refused")
        immutable._native_set(reader, initial_flags=initial_flags)
        _update_file(file_cap, flag_set=True); file_cap.seal_once(); held = state["held"]
        yield file_cap
        file_cap.check(); held.close(); held = None
        closing, reader = reader, None; os.close(closing)
        owned.check(); boundary()
        require(immutable._stamp(os.stat(name, dir_fd=dirfd, follow_symlinks=False)) == _CHOICES[file_cap], "body_receipt_stamp_changed")
        _FILE_ISSUED[file_cap] = origin, _CHOICES[file_cap]; _update_file(file_cap, phase="CLOSED")
    except BaseException:
        if file_cap is not None: _latch(file_cap)
        raise
    finally:
        try:
            if held is None and file_cap in _SEALS and _FILES[file_cap][1]["phase"] != "CLOSED": held = _SEALS[file_cap][1]
            if held is not None: held.close()
        finally:
            try: _close_all([fd for fd in (writer, reader) if fd is not None])
            except BaseException:
                if file_cap is not None: _latch(file_cap)
                raise


def _file_summary(file_cap):
    origin, state = file_cap._binding(failed=True)
    return {"role": origin[2], "name": origin[3], "bytes": len(origin[4]), "raw_sha256": origin[5],
        "seal_stamp_sha256": None if state["choice"] is None else hash_payload(state["choice"]),
        "initial_flags": origin[9], "expected_flags": origin[10], "original_context_closed": file_cap in _FILE_ISSUED}


class BodyReceiptCustody:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise BodyReceiptRefusal("REFUSED: body_receipt_factory_required")
    def __repr__(self): return "<BodyReceiptCustody redacted>"
    def _binding(self, *, failed=False):
        record = _PAIRS.get(self) if type(self) is BodyReceiptCustody else None
        try: origin, identity = self._anchor, self._identity
        except AttributeError: origin, identity = None, None
        require(type(record) is tuple and record[0] is origin is identity, "body_receipt_binding_changed")
        require(failed or self not in _FAILED, "body_receipt_latched_failure")
        state = record[1]
        require(type(state) is dict and tuple(state) == ("phase",) and state["phase"] is _PAIR_PHASES.get(self), "body_receipt_binding_changed")
        require((state["phase"] == "CLOSED") is (self in _PAIR_ISSUED), "body_receipt_not_closed")
        _binding_anchor(origin[2])
        for cap in origin[3]: _file_anchor(cap)
        return origin, state
    def check(self):
        try:
            origin, state = self._binding(); require(state["phase"] == "LIVE", "body_receipt_not_live")
            for cap in (*origin[3], origin[3][0]): cap.check()
            _audit_pair(origin)
        except BaseException: _latch(self); raise
    def read_body(self, maximum=MAXIMUM_BODY_BYTES):
        try:
            origin, unused = self._binding(); require(type(maximum) is int and len(origin[3][0]._anchor[4]) <= maximum <= MAXIMUM_BODY_BYTES, "body_receipt_bounds_refused")
            self.check(); return origin[3][0]._anchor[4]
        except BaseException: _latch(self); raise
    def read_receipt(self):
        self.check(); return self._binding()[0][3][1]._anchor[4]
    def observation(self):
        try:
            origin, state = self._binding(failed=True)
            return {"schema": "si-body-receipt-custody-observation-v1", "status": "refused" if self in _FAILED else
                "closed_paired_custody" if state["phase"] == "CLOSED" else "live_paired_custody",
                "binding_sha256": origin[2].sha256, "policy_sha256": _POLICY_SHA,
                "files": [_file_summary(cap) for cap in origin[3]], "authority": authority()}
        except BaseException: _latch(self); raise
    def check_after_close(self):
        try:
            origin, state = self._binding(); require(state["phase"] == "CLOSED" and self in _PAIR_ISSUED, "body_receipt_not_closed")
            _audit_closed_paths(origin)
        except BaseException: _latch(self); raise
    def closed_summary(self):
        try:
            origin, state = self._binding(); issued = _PAIR_ISSUED.get(self)
            require(state["phase"] == "CLOSED" and type(issued) is tuple and issued[0] is origin,
                "body_receipt_not_closed")
            self.check_after_close(); return json.loads(issued[1])
        except BaseException: _latch(self); raise


def _audit_pair(origin):
    owned, anchor, unused_binding, caps, fds, unused_started, unused_built, boundary = origin
    require(owned._anchor is anchor, "body_receipt_owned_changed"); owned.check(); boundary()
    require(set(cache._inventory_names(anchor[2], boundary=owned.check)) == {BODY_NAME, RECEIPT_NAME}, "body_receipt_membership_changed")
    for cap, fd in zip(caps, fds): _read_original(_file_anchor(cap), fd, _CHOICES[cap])
    for cap in caps: require(immutable._stamp(os.stat(cap._anchor[3], dir_fd=anchor[2], follow_symlinks=False)) == _CHOICES[cap], "body_receipt_stamp_changed")
    owned.check(); boundary()
    require(set(cache._inventory_names(anchor[2], boundary=lambda: None)) == {BODY_NAME, RECEIPT_NAME}, "body_receipt_membership_changed")


def _audit_closed_paths(origin):
    unused_owned, anchor, unused_binding, caps, unused_fds, unused_started, unused_built, unused_boundary = origin
    directory, parent = anchor[:2]; descriptors = []
    try:
        require(directory.resolve() == directory and parent.resolve() == parent, "body_receipt_owned_changed")
        require(_OwnedOutput._stamp(parent.lstat()) == anchor[5] and _OwnedOutput._stamp(directory.lstat()) == anchor[4], "body_receipt_owned_changed")
        pfd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); descriptors.append(pfd)
        require(_OwnedOutput._stamp(os.fstat(pfd)) == anchor[5], "body_receipt_owned_changed")
        dfd = os.open(directory.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=pfd); descriptors.append(dfd)
        require(_OwnedOutput._stamp(os.fstat(dfd)) == anchor[4] and set(cache._inventory_names(dfd, boundary=lambda: None)) == {BODY_NAME, RECEIPT_NAME}, "body_receipt_membership_changed")
        for cap in caps:
            original = _file_anchor(cap); fd = os.open(original[3], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
            try:
                replacement = (*original[:6], dfd, *original[7:])
                _read_original(replacement, fd, _CHOICES[cap])
            finally: os.close(fd)
        for cap in caps: require(immutable._stamp(os.stat(cap._anchor[3], dir_fd=dfd, follow_symlinks=False)) == _CHOICES[cap], "body_receipt_stamp_changed")
        require(set(cache._inventory_names(dfd, boundary=lambda: None)) == {BODY_NAME, RECEIPT_NAME}, "body_receipt_membership_changed")
    finally:
        _close_all(descriptors)
    require(_OwnedOutput._stamp(parent.lstat()) == anchor[5] and _OwnedOutput._stamp(directory.lstat()) == anchor[4], "body_receipt_owned_changed")
    for cap in caps: require(immutable._stamp((directory / cap._anchor[3]).lstat()) == _CHOICES[cap], "body_receipt_stamp_changed")
    require(set(os.listdir(directory)) == {BODY_NAME, RECEIPT_NAME}, "body_receipt_membership_changed")
    require(_OwnedOutput._stamp(parent.lstat()) == anchor[5] and _OwnedOutput._stamp(directory.lstat()) == anchor[4], "body_receipt_owned_changed")


@contextmanager
def prepare_owned_body_receipt(owned, body, *, binding, boundary, monotonic=time.monotonic, sleep=time.sleep):
    _check_policy(); _binding_anchor(binding)
    require(type(owned) is _OwnedOutput and type(body) is bytes and 0 < len(body) <= MAXIMUM_BODY_BYTES,
        "body_receipt_bounds_refused")
    owned.check(); require(not cache._inventory_names(owned._anchor[2], boundary=owned.check), "body_receipt_membership_changed")
    started = _utc_now(); _clock(started); pair, fds = None, []
    try:
        with ExitStack() as files:
            body_cap = files.enter_context(_prepare_original_file(owned, "body", body, binding=binding,
                boundary=boundary, monotonic=monotonic, sleep=sleep))
            body_cap.check(); built = _utc_now(); receipt = _receipt(binding, body, started, built)
            receipt_cap = files.enter_context(_prepare_original_file(owned, "receipt", receipt, binding=binding,
                boundary=boundary, monotonic=monotonic, sleep=sleep))
            body_cap.check(); caps = body_cap, receipt_cap
            require(caps[0]._anchor[8][:2] != caps[1]._anchor[8][:2], "body_receipt_inode_changed")
            for cap in caps: fds.append(os.dup(cap._anchor[7]))
            pair = object.__new__(BodyReceiptCustody)
            origin = owned, owned._anchor, binding, caps, tuple(fds), started, built, boundary
            pair._anchor = pair._identity = origin; state = {"phase": "LIVE"}; _PAIRS[pair] = origin, state; _PAIR_PHASES[pair] = state["phase"]
            pair.check(); yield pair; pair.check()
        require(all(cap in _FILE_ISSUED for cap in caps), "body_receipt_not_closed")
        _audit_pair(origin)
        _close_all(fds)
        owned.check(); boundary()
        for cap in caps: require(immutable._stamp(os.stat(cap._anchor[3], dir_fd=owned._anchor[2], follow_symlinks=False)) == _CHOICES[cap], "body_receipt_stamp_changed")
        closed_at = _utc_now(); require(_clock(built) <= _clock(closed_at), "body_receipt_clock_refused")
        summary = {**pair.observation(), "status": "closed_body_receipt_custody_only", "closed_at": closed_at}
        _PAIR_ISSUED[pair] = origin, canonical_json(summary).encode(); state["phase"] = "CLOSED"; _PAIR_PHASES[pair] = state["phase"]
    except BaseException:
        if pair is not None: _latch(pair)
        raise
    finally:
        try: _close_all(fds)
        except BaseException:
            if pair is not None: _latch(pair)
            raise


def monitor_phase_codes():
    nested = next(code for code in _prepare_original_file.__wrapped__.__code__.co_consts
        if type(code) is CodeType and code.co_name == "guarded_boundary")
    return {"body_receipt_guard_callback": nested, "body_receipt_native_creator": _prepare_original_file.__wrapped__.__code__,
        "body_receipt_require": require.__code__, "body_receipt_file_binding": BodyReceiptFileCustody._binding.__code__,
        "body_receipt_file_tick": BodyReceiptFileCustody._tick.__code__,
        "body_receipt_file_boundary": BodyReceiptFileCustody._boundary.__code__,
        "body_receipt_file_strict": BodyReceiptFileCustody._strict.__code__,
        "body_receipt_file_seal": BodyReceiptFileCustody.seal_once.__code__, "body_receipt_file_check": BodyReceiptFileCustody.check.__code__,
        "body_receipt_read": _read_original.__code__, "body_receipt_pair_check": BodyReceiptCustody.check.__code__,
        "body_receipt_pair_binding": BodyReceiptCustody._binding.__code__,
        "body_receipt_pair_body_read": BodyReceiptCustody.read_body.__code__,
        "body_receipt_pair_receipt_read": BodyReceiptCustody.read_receipt.__code__,
        "body_receipt_pair_observation": BodyReceiptCustody.observation.__code__,
        "body_receipt_pair_closed_summary": BodyReceiptCustody.closed_summary.__code__,
        "body_receipt_pair_closed_audit": _audit_closed_paths.__code__,
        "body_receipt_pair_audit": _audit_pair.__code__, "body_receipt_close": _close_all.__code__,
        "body_receipt_pair_factory": prepare_owned_body_receipt.__wrapped__.__code__}


_POLICY_SHA = hash_payload(policy())
