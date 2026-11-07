"""Prospective kernel-immutable custody for this invocation's NEW metadata only.

Never unlocks a file, adopts existing evidence, resets a seal, or grants source
admission. The original creator and HeldFiles implementation remain untouched.
"""
from contextlib import contextmanager
import ctypes
import errno
import fcntl
import os
import stat
import sys
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_new_metadata_custody as creator

LIBRARY = "/usr/lib/libSystem.B.dylib"
IMMUTABLE_FLAG = 2
TRACKED_FLAG = 64
_MINTED = {}  # One finite operational object; retain original identities until process exit.
_SEALED = {}
_ISSUED = {}  # Populated only by successful terminal factory exit, never caller state.
_FAILED = set()
_ERRNOS = {getattr(errno, name): name for name in (
    "EACCES", "EPERM", "EBADF", "EINVAL", "EIO", "ENOSYS", "ENOTSUP", "EOPNOTSUPP")
    if hasattr(errno, name)}
_CODES = frozenset("""immutable_platform_refused immutable_kernel_unavailable
immutable_kernel_set_refused immutable_kernel_result_changed immutable_flags_changed
immutable_initial_flags_not_zero immutable_factory_required immutable_binding_changed
immutable_initial_flags_refused
immutable_latched_failure immutable_not_live immutable_not_sealed immutable_stamp_changed
immutable_seal_changed immutable_original_bytes_changed immutable_not_closed
immutable_read_bound_refused""".split())


class ImmutableMetadataRefusal(ValueError):
    def __init__(self, code, errno_value=None):
        code = code if type(code) is str and code in _CODES else "immutable_binding_changed"
        self._errno_name = _ERRNOS.get(errno_value) if type(errno_value) is int else None
        super().__init__("REFUSED: " + code)


def require(value, code):
    if not value: raise ImmutableMetadataRefusal(code)


def failure_summary(error):
    if type(error) is not ImmutableMetadataRefusal: return creator.failure_summary(error)
    args = BaseException.args.__get__(error, BaseException)
    code = next((item for item in _CODES if type(args) is tuple and len(args) == 1
        and type(args[0]) is str and args[0] == "REFUSED: " + item), None)
    try: name = object.__getattribute__(error, "_errno_name")
    except AttributeError: name = None
    return {"category": "local_contract_refusal", "contract_code": code,
        "errno_name": name if type(name) is str and name in _ERRNOS.values() else None}


def _platform():
    require(sys.platform == "darwin" and getattr(stat, "UF_IMMUTABLE", None) == IMMUTABLE_FLAG
        and getattr(stat, "UF_TRACKED", None) == TRACKED_FLAG and TRACKED_FLAG == 64
        and IMMUTABLE_FLAG == 2 and LIBRARY == "/usr/lib/libSystem.B.dylib", "immutable_platform_refused")


def _native_set(fd, initial_flags=0):
    """Darwin's fixed int fchflags(int, unsigned int); never path-based chflags."""
    _platform()
    require(type(initial_flags) is int and initial_flags in (0, TRACKED_FLAG), "immutable_initial_flags_refused")
    try:
        library = ctypes.CDLL(LIBRARY, use_errno=True)
        operation = library.fchflags
        operation.argtypes, operation.restype = (ctypes.c_int, ctypes.c_uint), ctypes.c_int
        ctypes.set_errno(0)
        result = operation(fd, initial_flags | IMMUTABLE_FLAG)
        number = ctypes.get_errno()
    except (OSError, AttributeError):
        raise ImmutableMetadataRefusal("immutable_kernel_unavailable") from None
    require(type(result) is int and result in (0, -1), "immutable_kernel_result_changed")
    if result != 0: raise ImmutableMetadataRefusal("immutable_kernel_set_refused", number)


def _flags(info):
    try: flags = info.st_flags
    except AttributeError: raise ImmutableMetadataRefusal("immutable_platform_refused") from None
    require(type(flags) is int and 0 <= flags <= 0xffffffff, "immutable_flags_changed")
    return flags


def _stamp(info): return (*creator._stamp(info), _flags(info))


def authority():
    return {"new_metadata_only": True, "is_capture_claim": False, "provider_HTTP": 0,
        "credential_reads": 0, "source_START_debits": 0, "source_charged_bytes": 0,
        "historical_repair_established": False, "source_admitted": False,
        "ready_for_backtest": False, "outcome_looks": 0, "qc_attempts": 0, "trading_authority": False}


class ImmutableMetadataCustody:
    __slots__ = ("_anchor", "_identity")

    def __init__(self): raise ImmutableMetadataRefusal("immutable_factory_required")
    def __repr__(self): return "<ImmutableMetadataCustody redacted>"

    def _latch(self):
        record = _MINTED.get(id(self))
        if type(record) is tuple and record[0] is self:
            _FAILED.add(id(self)); record[2]["failed"] = True

    def _binding(self, *, failed=False):
        try:
            anchor, identity = object.__getattribute__(self, "_anchor"), object.__getattribute__(self, "_identity")
        except AttributeError: raise ImmutableMetadataRefusal("immutable_binding_changed") from None
        record = _MINTED.get(id(self))
        require(type(self) is ImmutableMetadataCustody and type(record) is tuple and record[0] is self
            and record[1] is anchor is identity, "immutable_binding_changed")
        state = record[2]
        require(type(state) is dict and set(state) == {"failed", "closed", "seal", "held", "closed_raw"}
            and type(state["failed"]) is bool and type(state["closed"]) is bool
            and state["failed"] is (id(self) in _FAILED), "immutable_binding_changed")
        require(failed or id(self) not in _FAILED, "immutable_latched_failure")
        sealed = _SEALED.get(id(self))
        require((state["seal"] is not None) is (sealed is not None), "immutable_seal_changed")
        if sealed is not None:
            require(type(sealed) is tuple and len(sealed) == 4 and sealed[0] is self and sealed[1] is anchor
                and state["seal"] is sealed[2] and state["held"] is sealed[3], "immutable_seal_changed")
        issued = _ISSUED.get(id(self))
        require(state["closed"] is (issued is not None), "immutable_not_closed")
        if issued is not None:
            require(type(issued) is tuple and len(issued) == 5 and issued[0] is self and issued[1] is anchor
                and state["closed_raw"] is issued[2] and type(issued[2]) is bytes
                and state["seal"] is issued[3] and issued[4] == anchor[5], "immutable_binding_changed")
        cap, original, original_state, unused_fd, unused_boundary, policy_sha, initial, target = anchor
        require(policy_sha == hash_payload(policy()), "immutable_binding_changed")
        require(type(initial) is int and initial in (0, TRACKED_FLAG)
            and type(target) is int and target == (initial | IMMUTABLE_FLAG), "immutable_binding_changed")
        require(type(cap) is creator.NewMetadataCustody and cap._anchor is cap._identity is original
            and cap._state is cap._state_identity is original_state, "immutable_binding_changed")
        cap._guard()
        if state["seal"] is not None:
            require(cap._state_identity["seal_stamp"] == state["seal"][:8], "immutable_seal_changed")
        if state["held"] is not None:
            require(cap._held_identity is original_state["held"] is state["held"], "immutable_binding_changed")
        return anchor, state

    def _audit(self):
        anchor, state = self._binding()
        cap, original, unused_state, fd, boundary, unused_policy, unused_initial, target = anchor
        cap._owned(); boundary()
        require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
            "immutable_binding_changed")
        def pair():
            observations = os.fstat(fd), os.stat(original[2], dir_fd=original[6], follow_symlinks=False)
            for info in observations:
                creator._protected(info, original[8])
                require(creator._stamp(info)[5:7] == original[8][5:7], "immutable_stamp_changed")
                require(_flags(info) == target, "immutable_flags_changed")
                if state["seal"] is not None:
                    require(_stamp(info) == state["seal"], "immutable_stamp_changed")
            return observations
        pair(); creator._read_expected(fd, original[3]); pair(); boundary(); cap._owned()

    def seal_once(self):
        try:
            anchor, state = self._binding()
            require(not state["closed"] and state["seal"] is None, "immutable_not_live")
            self._audit(); cap = anchor[0]; cap.seal_once()
            chosen = cap._state_identity["seal_stamp"]
            require(type(chosen) is tuple and len(chosen) == 8, "immutable_seal_changed")
            state["seal"], state["held"] = (*chosen, anchor[7]), cap._held_identity
            _SEALED[id(self)] = self, anchor, state["seal"], state["held"]
            self.check(); return self
        except BaseException: self._latch(); raise

    def check(self):
        try:
            anchor, state = self._binding()
            require(not state["closed"] and state["seal"] is not None, "immutable_not_sealed")
            require(anchor[0]._state_identity["seal_stamp"] == state["seal"][:8], "immutable_seal_changed")
            self._audit(); anchor[0].check(); self._audit()
        except BaseException: self._latch(); raise

    def read(self, maximum=1024):
        try:
            anchor, unused = self._binding()
            require(type(maximum) is int and len(anchor[1][3]) <= maximum <= 1024, "immutable_read_bound_refused")
            self.check(); return anchor[0].read(maximum)
        except BaseException: self._latch(); raise

    def observation(self):
        try:
            anchor, state = self._binding(failed=True)
            return {"schema": "si-new-kernel-immutable-metadata-v1",
                "phase": "REFUSED" if state["failed"] else "CLOSED" if state["closed"] else "SEALED" if state["seal"] else "UNSEALED",
                "expected_raw_sha256": hash_bytes(anchor[1][3]), "bytes": len(anchor[1][3]),
                "immutable_flag": IMMUTABLE_FLAG,
                "initial_flags": anchor[6], "expected_flags": anchor[7],
                "seal_stamp_sha256": None if state["seal"] is None else hash_payload(list(state["seal"])),
                "policy_sha256": anchor[5], "original_creator_observation": anchor[0].observation(),
                "authority": authority()}
        except BaseException: self._latch(); raise

    def closed_summary(self):
        try:
            unused, state = self._binding()
            require(state["closed"] and type(state["closed_raw"]) is bytes, "immutable_not_closed")
            import json
            return json.loads(state["closed_raw"])
        except BaseException: self._latch(); raise


@contextmanager
def prepare_owned_immutable_metadata(owned, name, raw, *, parent=True, boundary,
                                     monotonic=time.monotonic, sleep=time.sleep):
    """One fresh creator invocation; no old-file or caller-capability input."""
    _platform()
    fd, value, flagged, original, target = None, None, False, None, None
    state = {"failed": False, "closed": False, "seal": None, "held": None, "closed_raw": None}
    try:
        def guarded_boundary():
            boundary()
            if flagged:
                for info in (os.fstat(fd), os.stat(original[2], dir_fd=original[6], follow_symlinks=False)):
                    require(_flags(info) == target, "immutable_flags_changed")
        with creator.prepare_owned_metadata(owned, name, raw, parent=parent, boundary=guarded_boundary,
                monotonic=monotonic, sleep=sleep) as cap:
            original, original_state = cap._anchor, cap._state_identity
            require(original_state["phase"] == "UNSEALED" and not original_state["attempted"], "immutable_binding_changed")
            fd = os.dup(original[7])
            require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY, "immutable_binding_changed")
            observed = os.fstat(fd), os.stat(original[2], dir_fd=original[6], follow_symlinks=False)
            for info in observed:
                creator._protected(info, original[8])
            initial_flags = tuple(_flags(info) for info in observed)
            require(type(initial_flags[0]) is int and type(initial_flags[1]) is int
                and initial_flags[0] == initial_flags[1] and initial_flags[0] in (0, TRACKED_FLAG),
                "immutable_initial_flags_refused")
            initial, target = initial_flags[0], initial_flags[0] | IMMUTABLE_FLAG
            _native_set(fd, initial_flags=initial)
            flagged = True
            value = object.__new__(ImmutableMetadataCustody)
            anchor = cap, original, original_state, fd, guarded_boundary, hash_payload(policy()), initial, target
            value._anchor = value._identity = anchor
            _MINTED[id(value)] = value, anchor, state
            value._audit()
            yield value
            value.check()  # No swallowed caller error or silently repaired state.
        # Inner creator has closed its ORIGINAL HeldFiles and readonly FD.
        value._audit()
        require(cap._state_identity["closed"] and cap._state_identity["phase"] == "CLOSED", "immutable_not_closed")
        closing, fd = fd, None
        os.close(closing); flagged = False
        boundary(); owned.check()
        require(_stamp(os.stat(original[2], dir_fd=original[6], follow_symlinks=False)) == state["seal"],
            "immutable_stamp_changed")
        summary = {**value.observation(), "phase": "CLOSED", "status": "closed_kernel_immutable_new_metadata_only"}
        closed_raw = canonical_json(summary).encode()
        _ISSUED[id(value)] = value, value._anchor, closed_raw, state["seal"], value._anchor[5]
        state["closed_raw"] = closed_raw; state["closed"] = True
    except BaseException:
        if value is not None: value._latch()
        raise
    finally:
        if fd is not None:
            closing, fd = fd, None
            try: os.close(closing)
            except BaseException:
                if value is not None: value._latch()
                raise


def policy():
    return {"schema": "si-new-kernel-immutable-metadata-policy-v2", "library": LIBRARY,
        "symbol": "fchflags", "ABI": "int(int,unsigned_int)", "flag": IMMUTABLE_FLAG,
        "maximum_bytes": 1024, "initial_flags_allowed": [0, TRACKED_FLAG],
        "tracked_flag": TRACKED_FLAG, "target_flags": "observed_initial_flags_OR_UF_IMMUTABLE",
        "scope": "THIS_invocation_original_creator_O_EXCL_inode_only",
        "seal": "UF_IMMUTABLE_before_one_original_eight_field_seal_plus_strict_flags_nine_field_seal",
        "closure": "original_context_exit_then_original_retained_readonly_dup_bytes_and_same_nine_field_stamp",
        "unlock_rebaseline_adoption_allowed": False, "authority": authority()}
