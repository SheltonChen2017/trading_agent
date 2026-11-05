"""Provisional success-storage descriptors; never attest future process exit.

Only Main's original LIVE typed facts may create the fixed chunk/round roots.
Original metadata FDs/pins stay process-owned for a separate finite readonly
post-context audit. Later pure bindings never consult expired source leases.
Known actual EXIT0 and independent Main authentication remain indispensable.
"""
import fcntl
import json
import math
import os
from pathlib import Path
import resource
import stat
import sys
import time
from types import FunctionType

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_body_receipt_custody as primitive
from scripts import short_interest_count_response_volume as storage
from scripts import short_interest_count_durable_transport as transport

CHECKPOINT_POLICY_SHA256 = "965fa077fc16141468822ff083756d7f236f52b99b3ecc322844e2278cf2dd67"
MAXIMUM_CHUNKS, MAXIMUM_BYTES, MAXIMUM_RECEIPT_BYTES = 133, 2097152, 1024
MAXIMUM_AUDIT_SECONDS, MAXIMUM_TRANSIENT_FDS = 1800, 100
# Keep the serial 16-FD allowance and add seven concurrent workers at twelve
# FDs each: OwnedOutput2 + two (reader1 + HeldFiles2) + pair duplicates2 +
# explicit inventory FD1 + CPython listdir(fd)'s internal duplicate1.
# This is conservative constructor-based preclaim headroom, not a claim about
# all descriptors any process/library/system might ever allocate.
# Per chunk: independent mount + checkpoint dir + child dir + two file FDs.
# The single round index shares the last mount/checkpoint dir, adding three.
MAXIMUM_OWNED_FDS = 5 * MAXIMUM_CHUNKS + 3
ROOT_NAME, CHUNK_NAME, ROUND_NAME = "checkpoint", "chunk", "round"
_OPERATION_CLASS = transport.CountCaptureOperation
_ROOTS, _ISSUED, _KEEPERS, _ATTEMPTED, _CHUNKS = {}, {}, {}, set(), {}
_KEEPER_PINS, _DIRECTORY_PINS = {}, {}
_ROUND = None
_FAILED, _FAILED_NONCES = set(), set()
_AUTHORITY = (("source_admitted", False), ("count_source_qualified", False),
    ("denominator_admitted", False), ("actual_input_execution_admitted", False),
    ("ready_for_backtest", False), ("budget_release_authority", False),
    ("dispatch_authority", False), ("actual_process_EXIT0_attested", False),
    ("future_requalification_authority", False), ("perpetual_filesystem_custody_claimed", False),
    ("outcome_looks", 0), ("qc_attempts", 0))
_CODES = frozenset("""checkpoint_registration_pending checkpoint_factory_required
checkpoint_original_facts_required checkpoint_original_operation_changed checkpoint_original_volume_changed
checkpoint_source_not_live checkpoint_role_spent checkpoint_capacity_exhausted checkpoint_bounds_refused
checkpoint_directory_changed checkpoint_membership_changed checkpoint_original_seal_changed
checkpoint_original_bytes_changed checkpoint_binding_changed checkpoint_latched_failure
checkpoint_code_changed checkpoint_fd_headroom checkpoint_fd_close_failed checkpoint_clock_refused
checkpoint_audit_deadline checkpoint_round_incomplete""".split())


class CountCheckpointRefusal(ValueError): pass


def require(value, code):
    if not value: raise CountCheckpointRefusal("REFUSED: " + code)


def authority(): return dict(_AUTHORITY)


def policy():
    constants = (MAXIMUM_CHUNKS, MAXIMUM_BYTES, MAXIMUM_RECEIPT_BYTES,
        MAXIMUM_AUDIT_SECONDS, MAXIMUM_TRANSIENT_FDS, MAXIMUM_OWNED_FDS)
    require(all(type(a) is int and a == b for a, b in zip(constants, (133, 2097152, 1024, 1800, 100, 668)))
        and (ROOT_NAME, CHUNK_NAME, ROUND_NAME) == ("checkpoint", "chunk", "round"),
        "checkpoint_registration_pending")
    return {"schema": "si-count-success-checkpoint-policy-v1", "maximum_chunks": MAXIMUM_CHUNKS,
        "maximum_descriptor_bytes": MAXIMUM_BYTES, "maximum_receipt_bytes": MAXIMUM_RECEIPT_BYTES,
        "maximum_owned_FDs": MAXIMUM_OWNED_FDS, "maximum_transient_FDs": MAXIMUM_TRANSIENT_FDS,
        "transient_FD_derivation": {"serial_allowance": 16, "additional_workers": 7,
            "per_additional_worker_constructor_peak": 12, "includes_internal_listdir_duplicate": True,
            "scope": "conservative_constructor_based_preclaim_margin_not_universal_process_FD_maximum"},
        "independent_metadata_audit_seconds": MAXIMUM_AUDIT_SECONDS,
        "paths": [ROOT_NAME + "/" + CHUNK_NAME, ROOT_NAME + "/" + ROUND_NAME],
        "files": [primitive.BODY_NAME, primitive.RECEIPT_NAME],
        "primitive_policy_sha256": hash_payload(primitive.policy()),
        "volume_policy_sha256": hash_payload(storage.policy()),
        "facts": "fixed_Main_original_live_typed_facts10_no_caller_JSON_callbacks_or_status",
        "failure_latch": "original_plain_object_nonce_identity_scan_never_hash_changed_public_capability",
        "phase": "PROVISIONAL_STORAGE_FACTS", "selfhash_or_future_completion_claim": False,
        "provider_response_charge_bytes": 0,
        "metadata_classification": "checkpoint_storage_overhead_not_provider_response_or_budget_release",
        "postcontext": "own_original_readonly_FDs_native_epoch_directory_file9_and_bytes_not_expired_SourceLease",
        "terminal_clock": "same_original_pinned_monotonic_after_final_metadata_pass_no_source_callback",
        "terminal_authentication": "known_actual_process_EXIT0_and_Main_independent_original_root_pin_match_required",
        "authority": authority()}


def _registered():
    require(hash_payload(policy()) == CHECKPOINT_POLICY_SHA256, "checkpoint_registration_pending")


def failure_summary(error):
    if type(error) is not CountCheckpointRefusal: return primitive.failure_summary(error)
    args = BaseException.args.__get__(error, BaseException)
    code = (next((item for item in _CODES if args[0] == "REFUSED: " + item), None)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str else None)
    return {"category": "local_contract_refusal", "contract_code": code, "errno_name": None}


def _outer():
    from scripts import capture_short_interest_durable_counts
    return capture_short_interest_durable_counts


def _identity(cls):
    return type(cls) is type and cls.__hash__ is object.__hash__ and cls.__eq__ is object.__eq__


def _op(operation):
    require(transport.CountCaptureOperation is _OPERATION_CLASS and type(operation) is _OPERATION_CLASS
        and _identity(_OPERATION_CLASS), "checkpoint_original_operation_changed")
    original = transport.active_operation_binding(operation)
    require(type(original) is tuple and len(original) == 14 and original[0] is operation,
        "checkpoint_original_operation_changed")
    return original


def _live(op, volume, origin):
    with op[11]:
        require(_op(op[0]) is op, "checkpoint_original_operation_changed")
        transport._source_check(op[12])
        require(transport.volume_for_operation(op[0]) is volume
            and storage.preservation_volume_origin(volume, op[0]) is origin,
            "checkpoint_original_volume_changed")


def _dir(info):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
        "checkpoint_directory_changed")
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)


def _close_all(fds):
    failed = False
    for fd in tuple(fds):
        try: os.close(fd)
        except OSError: failed = True
    fds.clear(); require(not failed, "checkpoint_fd_close_failed")


def _code_pins():
    pins = []
    own = sys.modules[__name__]
    for name, function in tuple(vars(own).items()):
        if type(function) is FunctionType: pins.append((own, name, function, function.__code__))
    for module, names in ((storage, ("_native_statfs", "_mount_identity", "_node_pin", "_device_node_stat", "_platform")),
            (primitive.immutable, ("_stamp", "_flags")),
            (os, ("open", "close", "read", "fstat", "stat", "getuid", "getgid", "listdir", "lseek",
                "dup", "mkdir", "fchmod", "fsync")),
            (time, ("monotonic", "sleep")),
            (fcntl, ("fcntl",)), (storage.ctypes, ("CDLL",))):
        for name in names:
            function = getattr(module, name)
            pins.append((module, name, function, function.__code__ if type(function) is FunctionType else None))
    return tuple(pins)


def _check_code(pins):
    for owner, name, function, code in pins:
        require(vars(owner).get(name) is function and (code is None or function.__code__ is code),
            "checkpoint_code_changed")


def preflight_checkpoint_resources(operation, volume):
    """Before any claim: reserve finite FD headroom without changing limits."""
    _registered(); op = _op(operation)
    origin = storage.preservation_volume_origin(volume, operation); _live(op, volume, origin)
    soft, unused_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    current = len(os.listdir("/dev/fd"))
    held = sum(2 for unused in _ROOTS.values()) + sum(3 for unused in _KEEPERS.values())
    require(type(soft) is int and (soft == resource.RLIM_INFINITY
        or soft - current >= MAXIMUM_OWNED_FDS - held + MAXIMUM_TRANSIENT_FDS), "checkpoint_fd_headroom")


def _root(operation, volume, op, origin):
    existing = _ROOTS.get(operation)
    if existing is not None:
        require(existing[0] is op and existing[1] is volume and existing[2] is origin,
            "checkpoint_binding_changed")
        return existing
    _live(op, volume, origin)
    mount_fd = os.dup(origin[3]); fds = [mount_fd]
    try:
        require(fcntl.fcntl(mount_fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
            "checkpoint_original_volume_changed")
        try: os.stat(ROOT_NAME, dir_fd=mount_fd, follow_symlinks=False)
        except FileNotFoundError: pass
        else: raise CountCheckpointRefusal("REFUSED: checkpoint_role_spent")
        os.mkdir(ROOT_NAME, 0o700, dir_fd=mount_fd)
        fd = os.open(ROOT_NAME, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=mount_fd); fds.append(fd)
        os.fchmod(fd, 0o700); os.fsync(fd)
        path = origin[2] / ROOT_NAME; pin = _dir(os.fstat(fd))
        require(_dir(path.lstat()) == pin and pin[0] == origin[4][0] and not os.listdir(fd),
            "checkpoint_directory_changed")
        record = op, volume, origin, mount_fd, fd, path, pin, _code_pins()
        _ROOTS[operation] = record; fds.clear(); return record
    finally: _close_all(fds)


def _facts(operation, candidate, role, roots):
    outer = _outer()
    cap = (outer.checkpoint_facts(operation, candidate) if role == "chunk"
        else outer.checkpoint_round_facts(operation, candidate, roots))
    require(_identity(outer.CountCheckpointFacts) and type(cap) is outer.CountCheckpointFacts,
        "checkpoint_original_facts_required")
    facts = outer.checkpoint_facts_binding(cap)
    require(type(facts) is tuple and len(facts) == 10 and facts[0] is cap
        and facts[1] is operation and facts[2] is candidate
        and type(facts[5]) is bytes and 0 < len(facts[5]) <= MAXIMUM_BYTES
        and hash_bytes(facts[5]) == facts[6] and type(facts[9]) is object,
        "checkpoint_original_facts_required")
    parsed = json.loads(facts[5])
    require(type(parsed) is dict and canonical_json(parsed).encode() == facts[5]
        and parsed.get("schema") == ("si-count-checkpoint-descriptor-v1" if role == "chunk" else "si-count-checkpoint-round-v1")
        and parsed.get("phase") == "PROVISIONAL_STORAGE_FACTS", "checkpoint_original_facts_required")
    return facts


class ProvisionalCountCheckpoint:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise CountCheckpointRefusal("REFUSED: checkpoint_factory_required")
    def __repr__(self): return "<ProvisionalCountCheckpoint metadata-only>"
    def public_summary(self):
        original = checkpoint_binding(self)
        return {"schema": "si-count-checkpoint-root-v1", "phase": "PROVISIONAL_STORAGE_FACTS",
            "role": original[3], "body_sha256": original[6], "body_original9_sha256": hash_payload(original[7]),
            "receipt_sha256": original[8], "receipt_original9_sha256": hash_payload(original[9]), "authority": authority()}


_CHECKPOINT_CLASS = ProvisionalCountCheckpoint


def _fail(value):
    # A caller-visible class may have lost its default hash/equality. Find
    # the finite original record with `is`, then latch its plain object nonce.
    # Unknown/copy capabilities cannot manufacture a nonce or invoke methods.
    for original in tuple(_ISSUED.values()):
        if type(original) is tuple and len(original) == 12 and original[0] is value and type(original[11]) is object:
            _FAILED_NONCES.add(original[11])
            if type(value) is _CHECKPOINT_CLASS and _identity(_CHECKPOINT_CLASS): _FAILED.add(value)
            return


def checkpoint_binding(value):
    """Pure original12, deliberately no filesystem or expired source callback."""
    try:
        require(ProvisionalCountCheckpoint is _CHECKPOINT_CLASS and type(value) is _CHECKPOINT_CLASS
            and _identity(_CHECKPOINT_CLASS), "checkpoint_binding_changed")
        original = _ISSUED.get(value)
        require(type(original) is tuple and len(original) == 12 and original[0] is value
            and original is value._anchor is value._identity and value not in _FAILED
            and original[3] in ("chunk", "round") and type(original[11]) is object
            and original[11] not in _FAILED_NONCES
            and original[10] == ROOT_NAME + "/" + original[3] and value in _KEEPERS
            and _KEEPERS[value] is _KEEPER_PINS.get(value),
            "checkpoint_binding_changed")
        return original
    except BaseException: _fail(value); raise


def checkpoint_directory_pins(value):
    """Original checkpoint/child directory pins; no new stat baseline."""
    checkpoint_binding(value)
    try:
        original = _DIRECTORY_PINS.get(value)
        require(type(original) is tuple and len(original) == 2 and original is _KEEPER_PINS[value][6],
            "checkpoint_binding_changed")
        return original
    except BaseException: _fail(value); raise


def _publish(operation, candidate, role):
    global _ROUND
    _registered(); op = _op(operation)
    require(type(role) is str and role in ("chunk", "round"), "checkpoint_original_facts_required")
    require((operation, role) not in _ATTEMPTED and len(_ISSUED) < MAXIMUM_CHUNKS + 1,
        "checkpoint_role_spent")
    if role == "chunk": require(op[4] not in _CHUNKS, "checkpoint_role_spent")
    volume = transport.volume_for_operation(operation)
    origin = storage.preservation_volume_origin(volume, operation)
    roots = tuple(_CHUNKS[number] for number in sorted(_CHUNKS))
    if role == "round":
        require(_ROUND is None and len(roots) == len(op[2]._parts[3]) and op[4] == len(roots)
            and all(checkpoint_binding(cap)[4][3][2] is op[2] for cap in roots), "checkpoint_round_incomplete")
    facts = _facts(operation, candidate, role, roots)
    require(facts[3] is op, "checkpoint_original_facts_required")
    _ATTEMPTED.add((operation, role))
    root = _root(operation, volume, op, origin); fd = None; keepers = []
    try:
        _live(op, volume, origin)
        require(_dir(os.fstat(root[4])) == _dir(root[5].lstat()) == root[6], "checkpoint_directory_changed")
        os.mkdir(role, 0o700, dir_fd=root[4])
        fd = os.open(role, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root[4]); keepers.append(fd)
        os.fchmod(fd, 0o700); path = root[5] / role; directory_pin = _dir(os.fstat(fd))
        require(_dir(path.lstat()) == directory_pin and not os.listdir(fd), "checkpoint_directory_changed")
        def boundary(): _live(op, volume, origin)
        binding = primitive.freeze_body_receipt_binding(request_sha256=hash_payload(("checkpoint", role, op[10], op[4])),
            attempt_sha256=facts[6], reservation_sha256=hash_payload(("metadata_only_provider_charge_zero", op[10])),
            protocol_sha256=CHECKPOINT_POLICY_SHA256)
        with primitive._OwnedOutput(path, boundary) as owned:
            with primitive.prepare_owned_body_receipt(owned, facts[5], binding=binding, boundary=boundary,
                    monotonic=time.monotonic, sleep=time.sleep) as pair:
                pair.check(); seals, raws = [], []
                for file_cap in pair._anchor[3]:
                    file_origin = primitive._file_anchor(file_cap)
                    keepers.append(os.dup(file_origin[7])); seals.append(primitive._CHOICES[file_cap]); raws.append(file_origin[4])
            pair.closed_summary()
        require(_facts(operation, candidate, role, roots) is facts, "checkpoint_original_facts_required")
        _live(op, volume, origin)
        value = object.__new__(ProvisionalCountCheckpoint)
        original = (value, operation, candidate, role, facts, origin, hash_bytes(raws[0]), seals[0],
            hash_bytes(raws[1]), seals[1], ROOT_NAME + "/" + role, object())
        value._anchor = value._identity = original
        directory_pins = ((root[5], root[6]), (path, directory_pin))
        keeper = (root, path, directory_pin, tuple(keepers), tuple(raws), pair, directory_pins)
        _KEEPERS[value] = _KEEPER_PINS[value] = keeper
        _DIRECTORY_PINS[value] = directory_pins
        _ISSUED[value] = original; keepers.clear()
        _audit_one(value, lambda: None)
        if role == "chunk":
            require(op[4] not in _CHUNKS, "checkpoint_role_spent"); _CHUNKS[op[4]] = value
        else: _ROUND = value
        return value
    except BaseException:
        if "value" in locals(): _fail(value)
        raise
    finally: _close_all(keepers)


def publish_provisional_chunk_checkpoint(operation, candidate): return _publish(operation, candidate, "chunk")
def publish_provisional_round_checkpoint(operation, candidate): return _publish(operation, candidate, "round")


def _audit_pins(value):
    """Original endpoint/name/native/full9/catalogue sweep, no callbacks."""
    original = checkpoint_binding(value); root, path, pin, fds, unused_raws, unused_pair, unused_dirs = _KEEPERS[value]
    origin = original[5]
    require(all(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
        for fd in (root[3], root[4], fds[0])), "checkpoint_directory_changed")
    for info in (os.fstat(root[3]), origin[2].lstat()):
        require((info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)) == origin[4]
            and (info.st_dev, info.st_ino, info.st_uid, info.st_gid) == origin[5], "checkpoint_original_volume_changed")
    require(storage._mount_identity(storage._native_statfs(root[3])) == origin[6]
        and storage._node_pin(origin[6][-1], origin[4][0]) == origin[7], "checkpoint_original_volume_changed")
    require(_dir(os.fstat(root[4])) == _dir(root[5].lstat()) == root[6]
        and _dir(os.fstat(fds[0])) == _dir(path.lstat()) == pin, "checkpoint_directory_changed")
    expected_children = tuple(sorted(keeper[1].name for keeper in _KEEPER_PINS.values() if keeper[0] is root))
    require(tuple(sorted(os.listdir(root[4]))) == expected_children, "checkpoint_membership_changed")
    require(tuple(sorted(os.listdir(fds[0]))) == tuple(sorted((primitive.BODY_NAME, primitive.RECEIPT_NAME))),
        "checkpoint_membership_changed")
    for name, fd, seal in zip((primitive.BODY_NAME, primitive.RECEIPT_NAME), fds[1:], (original[7], original[9])):
        require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
            and primitive.immutable._stamp(os.fstat(fd)) == primitive.immutable._stamp(
                os.stat(name, dir_fd=fds[0], follow_symlinks=False)) == seal, "checkpoint_original_seal_changed")


def _audit_one(value, boundary):
    original = checkpoint_binding(value); root, path, pin, fds, raws, unused_pair, unused_dirs = _KEEPERS[value]
    own = next(item for item in root[7] if item[0] is sys.modules[__name__] and item[1] == "_check_code")
    require(own[2].__code__ is own[3], "checkpoint_code_changed")
    own[2](root[7]); _audit_pins(value)
    for name, fd, raw, seal in zip((primitive.BODY_NAME, primitive.RECEIPT_NAME), fds[1:], raws, (original[7], original[9])):
        require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY, "checkpoint_original_seal_changed")
        def check():
            boundary()
            require(primitive.immutable._stamp(os.fstat(fd)) == primitive.immutable._stamp(
                os.stat(name, dir_fd=fds[0], follow_symlinks=False)) == seal, "checkpoint_original_seal_changed")
        check(); os.lseek(fd, 0, os.SEEK_SET); offset = 0
        while offset < len(raw):
            check(); part = os.read(fd, min(65536, len(raw) - offset))
            require(type(part) is bytes and bool(part) and part == raw[offset:offset + len(part)], "checkpoint_original_bytes_changed")
            offset += len(part)
        require(os.read(fd, 1) == b"", "checkpoint_original_bytes_changed"); check()
    own[2](root[7])
    boundary(); own[2](root[7]); _audit_pins(value); own[2](root[7])


def audit_original_checkpoint_roots():
    """Own finite readonly metadata audit; no old source deadline is extended."""
    _registered(); original_clock = time.monotonic
    began = original_clock(); previous = [began]
    def boundary():
        now = original_clock()
        require(type(now) in (int, float) and math.isfinite(now) and 0 <= began <= previous[0] <= now,
            "checkpoint_clock_refused")
        require(now - began < MAXIMUM_AUDIT_SECONDS, "checkpoint_audit_deadline"); previous[0] = now
    originals = tuple(_ISSUED)
    for value in originals:
        try: boundary(); _audit_one(value, boundary)
        except BaseException: _fail(value); raise
    # A later root's byte sweep/clock boundary may affect an earlier root.
    # The final clock precedes one complete original-pin/catalogue sweep of
    # every root; there is no later caller callback or expired source guard.
    boundary()
    for value in originals:
        try:
            root = _KEEPER_PINS[value][0]
            own = next(item for item in root[7] if item[0] is sys.modules[__name__] and item[1] == "_check_code")
            require(own[2].__code__ is own[3], "checkpoint_code_changed")
            own[2](root[7]); _audit_pins(value); own[2](root[7])
            clock_pin = next(item for item in root[7] if item[0] is time and item[1] == "monotonic")
            require(clock_pin[2] is original_clock is time.monotonic, "checkpoint_code_changed")
        except BaseException: _fail(value); raise
    try:
        # This exact clock was bound by every original root above. Read only
        # elapsed time after the complete metadata pass: no source/lane guard
        # or caller callback is reintroduced beyond those final observations.
        ended = original_clock()
        require(type(ended) in (int, float) and math.isfinite(ended)
            and 0 <= began <= previous[0] <= ended, "checkpoint_clock_refused")
        require(ended - began < MAXIMUM_AUDIT_SECONDS, "checkpoint_audit_deadline")
        require(time.monotonic is original_clock, "checkpoint_code_changed")
    except BaseException:
        for value in originals: _fail(value)
        raise
    return {"schema": "si-count-checkpoint-metadata-audit-v1", "original_roots_checked": len(_ISSUED),
        "audit_context_closed": True, "authority": authority()}


def final_checkpoint_roots():
    require(_ROUND is not None, "checkpoint_round_incomplete")
    audit_original_checkpoint_roots(); original = checkpoint_binding(_ROUND)
    last = checkpoint_binding(_CHUNKS[max(_CHUNKS)])
    producer = json.loads(last[4][5])["producer"]
    producer_fields = ("head", "code_identity_sha256", "source_authority_sha256",
        "operator_protocol_sha256", "run_protocol_sha256", "negative_policy_sha256")
    require(all(type(producer.get(key)) is str and len(producer[key]) == (40 if key == "head" else 64)
        and all(char in "0123456789abcdef" for char in producer[key]) for key in producer_fields),
        "checkpoint_original_facts_required")
    return {"schema": "si-count-checkpoint-terminal-root-v1", "phase": "PROVISIONAL_STORAGE_FACTS",
        "index_raw_sha256": original[6], "index_body_original9_sha256": hash_payload(original[7]),
        "index_receipt_raw_sha256": original[8],
        "index_receipt_original9_sha256": hash_payload(original[9]),
        "directory_pins_sha256": hash_payload([{"path": path.relative_to(original[5][2]).as_posix(),
            "pin5": list(pin)} for path, pin in checkpoint_directory_pins(_ROUND)]),
        "producer_facts_sha256": original[4][6], "checkpoint_policy_sha256": CHECKPOINT_POLICY_SHA256,
        "producer": {key: producer[key] for key in producer_fields},
        "authority": authority()}
