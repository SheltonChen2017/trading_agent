"""Finite readonly requalification of known successful count storage roots.

This module never reconstructs an old process capability or resumes a source
operation. Provisional producer files alone are insufficient: an independently
authenticated Main receipt for a KNOWN exit0 and exact original roots must be
frozen before entry. The new corpus describes transport custody only.
"""
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
from datetime import timedelta
from types import FunctionType, BuiltinFunctionType

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import load_short_interest_count_epoch_ledger as old_archive
from scripts import short_interest_count_response_volume as storage
from scripts import short_interest_lane_batch_guard as lane
from scripts import capture_short_interest_durable_counts as producer
from research.short_interest_etf import native_count_recovery_budget as plans
from research.short_interest_etf import native_dated_class_reference as references

ROOT = lane.ROOT
DRIVER = "scripts/load_short_interest_count_checkpoints.py"
PROTOCOL_SHA256 = "PENDING"
EXPECTED_PRODUCER_HEAD = EXPECTED_PRODUCER_PROTOCOL = "PENDING"
EXPECTED_PRODUCER_CODE_MANIFEST = ()
EXPECTED_RECEIPT_PATH = EXPECTED_RECEIPT_SHA256 = EXPECTED_RECEIPT_SEAL9_SHA256 = "PENDING"
EXPECTED_ROUND_MOUNT = EXPECTED_ROUND_BODY_SHA256 = EXPECTED_ROUND_BODY_SEAL9_SHA256 = "PENDING"
EXPECTED_ROUND_RECEIPT_SHA256 = EXPECTED_ROUND_RECEIPT_SEAL9_SHA256 = "PENDING"
EXPECTED_ROUND_DIRECTORY_PINS_SHA256 = "PENDING"
MAXIMUM_SECONDS, MAXIMUM_CHUNKS, MAXIMUM_BYTES = 1800, 133, 2 * 1024 ** 2
# Exact original public-code/ancestry producers exercised by timing-v2.
HISTORICAL_HEADS = (
    "ab169b34f8763af7bd529ba98dbe151b5aa46e6c", "f67bbf2fc5ab4c7ce822c7e52b57b560cd670682",
    "91f4158b6c9a9b4bf0099e60e5a50d2d9727587b", "3784f4f8779b4a8a14aed109b6a9cb8354126dd7",
    "f61a40bf497747cffdda367d2a20c393383c8232", "a5ac4c22499e13f04776a8fa145fd3dba72bc383",
    "11d6b300b6737ead079a3a0532b5bfdd693600c5", "64f372ea8bfbcc542e87356a5e3e58fe07da1c27",
    "71f0a62de1ecfa07e1c1f91bd34ec94361eb207a", "99417837467f98b0ed02a3272b0980f4efa2d243",
    "e9771c52824edc3fb123d586230ffca36bcfdd8f", "2d11d1f5b73a04e0701c65bdeb81152766535f89")
_ISSUED, _FAILED, _CLOSED, _PRIVATE = {}, set(), {}, {}
_DEADLINES, _DEADLINE_LAST, _PRODUCERS, _PRODUCER_PINS = {}, {}, {}, {}
_MONOTONIC = time.monotonic
_CODES = frozenset("""checkpoint_loader_registration_pending checkpoint_loader_root_changed
checkpoint_loader_json_changed checkpoint_loader_shape_changed checkpoint_loader_seal_changed
checkpoint_loader_file_changed checkpoint_loader_directory_changed checkpoint_loader_native_changed
checkpoint_loader_catalogue_changed checkpoint_loader_negative checkpoint_loader_producer_changed
checkpoint_loader_receipt_required checkpoint_loader_index_changed checkpoint_loader_accounting_changed
checkpoint_loader_baseline_changed checkpoint_loader_code_changed checkpoint_loader_clock_changed
checkpoint_loader_window_exhausted checkpoint_loader_factory_required checkpoint_loader_binding_changed
checkpoint_loader_not_closed checkpoint_loader_readonly_required checkpoint_loader_close_failed""".split())


class CountCheckpointLoaderRefusal(ValueError): pass


def require(value, code):
    if not value: raise CountCheckpointLoaderRefusal("REFUSED: " + code)


def failure_summary(error):
    code = None
    if type(error) is CountCheckpointLoaderRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((item for item in _CODES if args[0] == "REFUSED: " + item), None)
    return {"category": "local_contract_refusal" if code is not None else "unknown_local_error",
        "contract_code": code, "errno_name": None}


def authority():
    return {"requalified_transport_custody_only": True, "source_admitted": False,
        "count_source_qualified": False, "denominator_admitted": False, "historical_PIT_admitted": False,
        "actual_input_execution_admitted": False, "ready_for_backtest": False, "source_resume_authority": False,
        "budget_release_authority": False, "provider_HTTP": 0, "credential_reads": 0,
        "new_claims": 0, "new_STARTs": 0, "new_charged_bytes": 0, "outcome_looks": 0, "qc_attempts": 0}


def _digest(value): return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None
def _head(value): return type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def code_paths():
    # Storage has fixed lazy transport/outer/checkpoint validators. Bind that
    # complete executable closure, including the explicitly retained original
    # wrappers, rather than only this module's eager import statements.
    return tuple(sorted(set((*producer.code_paths(), DRIVER))))


def protocol():
    return {"schema": "si-count-checkpoint-loader-policy-v1", "maximum_seconds": MAXIMUM_SECONDS,
        "maximum_chunks": MAXIMUM_CHUNKS, "maximum_file_bytes": MAXIMUM_BYTES,
        "producer_head": EXPECTED_PRODUCER_HEAD, "producer_protocol": EXPECTED_PRODUCER_PROTOCOL,
        "producer_code_manifest": [list(row) for row in EXPECTED_PRODUCER_CODE_MANIFEST],
        "receipt": [EXPECTED_RECEIPT_PATH, EXPECTED_RECEIPT_SHA256, EXPECTED_RECEIPT_SEAL9_SHA256],
        "round": [EXPECTED_ROUND_MOUNT, EXPECTED_ROUND_BODY_SHA256, EXPECTED_ROUND_BODY_SEAL9_SHA256,
            EXPECTED_ROUND_RECEIPT_SHA256, EXPECTED_ROUND_RECEIPT_SEAL9_SHA256, EXPECTED_ROUND_DIRECTORY_PINS_SHA256],
        "root": str(ROOT), "same_original_mounted_epoch_only": True, "reattach": False,
        "Git_historical_heads": list(HISTORICAL_HEADS),
        "Git_routes": "exact_current_producer_historical_show_paths_exact_ancestry_and_only_matching_origin_REF",
        "producer_files": "PROVISIONAL_STORAGE_FACTS_never_actual_process_closure",
        "repository_brackets": "full_exact_snapshots_before_after_each_descriptor_inner_original_seals_bytes_native_and_pinned_clock",
        "producer_code": "original_private_invariant_witness_initial_and_terminal_guarded_Git_audits_registration_recomputed_per_chunk",
        "terminal_clock": "same_original_pinned_pure_monotonic_through_last_metadata_check_no_source_callback",
        "root_of_trust": "frozen_Main_independently_authenticated_KNOWN_actual_exit0_receipt_and_original_full9_pins",
        "closure": "all_source_sweeps_and_code_context_exits_then_fresh_committed_code_and_original_terminal_witness",
        "code_paths": list(code_paths()), "authority": authority()}


def registered():
    require(_head(EXPECTED_PRODUCER_HEAD) and all(_digest(value) for value in (
        PROTOCOL_SHA256, EXPECTED_PRODUCER_PROTOCOL, EXPECTED_RECEIPT_SHA256, EXPECTED_RECEIPT_SEAL9_SHA256,
        EXPECTED_ROUND_BODY_SHA256, EXPECTED_ROUND_BODY_SEAL9_SHA256,
        EXPECTED_ROUND_RECEIPT_SHA256, EXPECTED_ROUND_RECEIPT_SEAL9_SHA256, EXPECTED_ROUND_DIRECTORY_PINS_SHA256))
        and type(EXPECTED_PRODUCER_CODE_MANIFEST) is tuple and EXPECTED_PRODUCER_CODE_MANIFEST
        and tuple(sorted(set(EXPECTED_PRODUCER_CODE_MANIFEST))) == EXPECTED_PRODUCER_CODE_MANIFEST
        and all(type(row) is tuple and len(row) == 2 and type(row[0]) is str and _digest(row[1])
            for row in EXPECTED_PRODUCER_CODE_MANIFEST)
        and type(EXPECTED_RECEIPT_PATH) is str and Path(EXPECTED_RECEIPT_PATH).is_absolute()
        and type(EXPECTED_ROUND_MOUNT) is str and Path(EXPECTED_ROUND_MOUNT).is_absolute()
        and (MAXIMUM_SECONDS, MAXIMUM_CHUNKS, MAXIMUM_BYTES) == (1800, 133, 2097152)
        and hash_payload(protocol()) == PROTOCOL_SHA256, "checkpoint_loader_registration_pending")


def _parse(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAXIMUM_BYTES, "checkpoint_loader_json_changed")
    def pairs(items):
        result = {}
        for key, value in items:
            require(type(key) is str and key not in result, "checkpoint_loader_json_changed")
            result[key] = value
        return result
    try: value = json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda unused: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError): raise CountCheckpointLoaderRefusal("REFUSED: checkpoint_loader_json_changed") from None
    require(canonical_json(value).encode() == raw, "checkpoint_loader_json_changed")
    return value


def _keys(value, expected):
    require(type(value) is dict and set(value) == set(expected), "checkpoint_loader_shape_changed")


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode), info.st_nlink,
        info.st_size, info.st_mtime_ns, info.st_ctime_ns, getattr(info, "st_flags", None))


def _seal(value):
    require(type(value) is list and len(value) == 9 and all(type(item) is int and item >= 0 for item in value)
        and value[2] == os.getuid() and value[3] == 0o600 and value[4] == 1
        and 0 < value[5] <= MAXIMUM_BYTES and value[8] & 2 == 2, "checkpoint_loader_seal_changed")
    return tuple(value)


def _relative(name):
    require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", name)
        and not any(part in (".", "..") for part in name.split("/")), "checkpoint_loader_catalogue_changed")
    return name


def _close(fds):
    failed = False
    while fds:
        try: os.close(fds.pop())
        except BaseException: failed = True
    require(not failed, "checkpoint_loader_close_failed")


class _PinnedDeadline:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise CountCheckpointLoaderRefusal("REFUSED: checkpoint_loader_factory_required")


def _new_deadline(monotonic=_MONOTONIC):
    """Production uses the ORIGINAL builtin; explicit Python clocks are tests."""
    require(type(monotonic) in (FunctionType, BuiltinFunctionType)
        and type(MAXIMUM_SECONDS) is int and MAXIMUM_SECONDS == 1800, "checkpoint_loader_clock_changed")
    began = monotonic()
    require(type(began) in (int, float) and math.isfinite(began) and 0 <= began <= 2 ** 53,
        "checkpoint_loader_clock_changed")
    value = object.__new__(_PinnedDeadline)
    original = (value, monotonic, monotonic.__code__ if type(monotonic) is FunctionType else None,
        monotonic.__defaults__ if type(monotonic) is FunctionType else None, began, MAXIMUM_SECONDS, object())
    value._anchor = value._identity = original
    _DEADLINES[id(value)] = original; _DEADLINE_LAST[id(value)] = original, began
    return value


def _tick(deadline):
    original = _DEADLINES.get(id(deadline)) if type(deadline) is _PinnedDeadline else None
    require(type(original) is tuple and len(original) == 7 and original[0] is deadline
        and deadline._anchor is deadline._identity is original
        and _DEADLINE_LAST.get(id(deadline), (None,))[0] is original,
        "checkpoint_loader_clock_changed")
    clock = original[1]
    require((original[2] is None or (clock.__code__ is original[2] and clock.__defaults__ is original[3]))
        and type(MAXIMUM_SECONDS) is int and MAXIMUM_SECONDS == original[5], "checkpoint_loader_clock_changed")
    now = clock()
    require(type(now) in (int, float) and math.isfinite(now)
        and original[4] <= _DEADLINE_LAST[id(deadline)][1] <= now <= 2 ** 53, "checkpoint_loader_clock_changed")
    require(now - original[4] < original[5], "checkpoint_loader_window_exhausted")
    _DEADLINE_LAST[id(deadline)] = original, now


@contextmanager
def _repository_unit(guard, deadline):
    """A fixed readonly unit, never timed evidence or a caller complete flag."""
    _tick(deadline); guard.check(); _tick(deadline)
    try: yield
    finally: _tick(deadline); guard.check(); _tick(deadline)


def _read_original(path, digest, seal9, boundary, *, seal_hash=None):
    boundary(); require(path.is_absolute() and path.resolve() == path and _digest(digest), "checkpoint_loader_file_changed")
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), "checkpoint_loader_file_changed")
    require(seal9 is not None or _digest(seal_hash), "checkpoint_loader_seal_changed")
    expected = _stamp(before) if seal9 is None else _seal(seal9)
    require(expected[8] is not None and _stamp(before) == expected
        and (seal_hash is None or hash_payload(expected) == seal_hash), "checkpoint_loader_seal_changed")
    # A registered hash of an ORIGINAL full9 may bootstrap its exact tuple;
    # this is never accepted without that separately frozen trusted hash.
    if seal9 is None: _seal(list(expected))
    fds = []
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK); fds.append(fd)
        require(_stamp(os.fstat(fd)) == expected, "checkpoint_loader_seal_changed")
        pieces, remaining = [], expected[5]
        while remaining:
            boundary(); piece = os.read(fd, min(65536, remaining))
            require(type(piece) is bytes and piece, "checkpoint_loader_file_changed")
            pieces.append(piece); remaining -= len(piece)
        require(os.read(fd, 1) == b"", "checkpoint_loader_file_changed")
        raw = b"".join(pieces)
        require(hash_bytes(raw) == digest and _stamp(os.fstat(fd)) == _stamp(path.lstat()) == expected,
            "checkpoint_loader_file_changed")
    finally: _close(fds)
    boundary(); require(_stamp(path.lstat()) == expected, "checkpoint_loader_seal_changed")
    return raw, expected


def _directory5(path, pin):
    require(type(pin) is list and len(pin) == 5 and all(type(item) is int for item in pin),
        "checkpoint_loader_directory_changed")
    def stamp(info): return info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)
    require(path.resolve() == path and stat.S_ISDIR(path.lstat().st_mode)
        and pin[2:3] == [os.getuid()] and pin[4] == 0o700 and stamp(path.lstat()) == tuple(pin),
        "checkpoint_loader_directory_changed")
    fds = []
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); fds.append(fd)
        require(stamp(os.fstat(fd)) == stamp(path.lstat()) == tuple(pin), "checkpoint_loader_directory_changed")
    finally: _close(fds)


def _pair(mount, relative_root, body_sha, body_seal, receipt_sha, receipt_seal, boundary, *, hashes=False,
        directory_pins=None, final_mount=False):
    require(relative_root in ("checkpoint/chunk", "checkpoint/round"), "checkpoint_loader_index_changed")
    base = mount / relative_root
    require(type(directory_pins) is list and len(directory_pins) == 2, "checkpoint_loader_directory_changed")
    for row, expected in zip(directory_pins, ("checkpoint", relative_root)):
        _keys(row, ("path", "pin5")); require(row["path"] == expected, "checkpoint_loader_directory_changed")
        _directory5(mount / expected, row["pin5"])
    expected_children = {"chunk", "round"} if relative_root == "checkpoint/round" or final_mount else {"chunk"}
    require(set(os.listdir(mount / "checkpoint")) == expected_children, "checkpoint_loader_negative")
    require(base.resolve() == base and set(os.listdir(base)) == {"attempt-body.raw", "attempt-receipt.private.json"},
        "checkpoint_loader_catalogue_changed")
    body, body9 = _read_original(base / "attempt-body.raw", body_sha, None if hashes else body_seal,
        boundary, seal_hash=body_seal if hashes else None)
    receipt, receipt9 = _read_original(base / "attempt-receipt.private.json", receipt_sha,
        None if hashes else receipt_seal, boundary, seal_hash=receipt_seal if hashes else None)
    value = _parse(receipt)
    require(value.get("body_sha256") == body_sha and type(value.get("body_bytes")) is int
        and value["body_bytes"] == len(body) and value.get("source_admitted") is False
        and value.get("budget_release_authority") is False, "checkpoint_loader_index_changed")
    for row in directory_pins: _directory5(mount / row["path"], row["pin5"])
    require(set(os.listdir(mount / "checkpoint")) == expected_children, "checkpoint_loader_negative")
    require(set(os.listdir(base)) == {"attempt-body.raw", "attempt-receipt.private.json"},
        "checkpoint_loader_negative")
    for row in directory_pins: _directory5(mount / row["path"], row["pin5"])
    return body, body9, receipt9


def _receipt(boundary):
    raw, seal = _read_original(Path(EXPECTED_RECEIPT_PATH), EXPECTED_RECEIPT_SHA256, None,
        boundary, seal_hash=EXPECTED_RECEIPT_SEAL9_SHA256)
    value = _parse(raw)
    _keys(value, ("schema", "known_exec_session", "process_exit", "producer_head", "producer_protocol",
        "round_index_body_sha256", "round_index_body_seal9_sha256", "round_index_receipt_sha256",
        "round_index_receipt_seal9_sha256", "expected_union_binding_sha256", "actual_union_sha256"))
    require(value["schema"] == "si-count-actual-exit0-receipt-v1"
        and type(value["known_exec_session"]) is int and value["known_exec_session"] > 0
        and type(value["process_exit"]) is int and value["process_exit"] == 0
        and value["producer_head"] == EXPECTED_PRODUCER_HEAD and value["producer_protocol"] == EXPECTED_PRODUCER_PROTOCOL
        and value["round_index_body_sha256"] == EXPECTED_ROUND_BODY_SHA256
        and value["round_index_body_seal9_sha256"] == EXPECTED_ROUND_BODY_SEAL9_SHA256
        and value["round_index_receipt_sha256"] == EXPECTED_ROUND_RECEIPT_SHA256
        and value["round_index_receipt_seal9_sha256"] == EXPECTED_ROUND_RECEIPT_SEAL9_SHA256
        and _digest(value["expected_union_binding_sha256"]) and _digest(value["actual_union_sha256"]),
        "checkpoint_loader_receipt_required")
    return value, (Path(EXPECTED_RECEIPT_PATH), EXPECTED_RECEIPT_SHA256, list(seal))


def _round_directories():
    rows = []
    for name in ("checkpoint", "checkpoint/round"):
        info = (Path(EXPECTED_ROUND_MOUNT) / name).lstat()
        rows.append({"path": name, "pin5": [info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)]})
    require(hash_payload(rows) == EXPECTED_ROUND_DIRECTORY_PINS_SHA256, "checkpoint_loader_directory_changed")
    return rows


def _directory(path, pin):
    require(type(pin) is list and len(pin) == 4 and all(type(item) is int for item in pin)
        and path.resolve() == path and storage._directory(path.lstat()) == tuple(pin),
        "checkpoint_loader_directory_changed")
    fds = []
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); fds.append(fd)
        require(storage._directory(os.fstat(fd)) == tuple(pin), "checkpoint_loader_directory_changed")
    finally: _close(fds)


def _native(volume, plan_sha, chunk, boundary):
    _keys(volume, ("mount", "namespace", "backing_pin", "root_pin", "root_identity", "native_identity",
        "device", "block_node_pin", "parent_directories", "system_entries"))
    mount, namespace = Path(volume["mount"]), Path(volume["namespace"])
    expected = ROOT / storage.PARENT / f"{storage.NAMESPACE_PREFIX}-{plan_sha}-chunk{chunk:03d}"
    require(namespace == expected and mount == expected / storage.MOUNT_NAME and mount.resolve() == mount,
        "checkpoint_loader_native_changed")
    for row in volume["parent_directories"]:
        _keys(row, ("path", "pin4")); _directory(Path(row["path"]), row["pin4"])
    require(set(os.listdir(namespace)) == {storage.IMAGE_NAME, storage.MOUNT_NAME}, "checkpoint_loader_native_changed")
    fds = []
    try:
        fd = os.open(namespace / storage.IMAGE_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK); fds.append(fd)
        require(storage._backing(os.fstat(fd)) == storage._backing((namespace / storage.IMAGE_NAME).lstat())
            == tuple(volume["backing_pin"]), "checkpoint_loader_native_changed")
        fd = os.open(mount, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW); fds.append(fd)
        info = os.fstat(fd); native = storage._native_statfs(fd)
        require(storage._directory(info) == storage._directory(mount.lstat()) == tuple(volume["root_pin"])
            and list(storage._fresh_root_identity(info)) == volume["root_identity"]
            and json.loads(canonical_json(storage._mount_identity(native))) == volume["native_identity"]
            and storage._node_pin(volume["device"], info.st_dev) == tuple(volume["block_node_pin"]),
            "checkpoint_loader_native_changed")
    finally: _close(fds)
    _root_membership(mount, volume["system_entries"], boundary)
    boundary(); return mount


def _producer_profile(value):
    _keys(value, ("head", "remote", "code_manifest", "code_identity_sha256", "source_authority_sha256",
        "operator_protocol_sha256", "run_protocol_sha256", "negative_policy_sha256", "registration_sha256"))
    require(value["head"] == EXPECTED_PRODUCER_HEAD and value["run_protocol_sha256"] == EXPECTED_PRODUCER_PROTOCOL
        and value["code_manifest"] == [list(row) for row in EXPECTED_PRODUCER_CODE_MANIFEST]
        and _head(value["remote"]) and all(_digest(value[key]) for key in (
            "code_identity_sha256", "source_authority_sha256", "operator_protocol_sha256", "negative_policy_sha256", "registration_sha256")),
        "checkpoint_loader_producer_changed")
    require(hash_payload({"git_commit": value["head"], "files": [
        {"path": name, "sha256": digest} for name, digest in EXPECTED_PRODUCER_CODE_MANIFEST]})
        == value["code_identity_sha256"], "checkpoint_loader_producer_changed")
    return canonical_json({key: item for key, item in value.items() if key != "registration_sha256"}).encode()


class _ProducerCodeWitness:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise CountCheckpointLoaderRefusal("REFUSED: checkpoint_loader_factory_required")


def _producer_origin(witness):
    original = _PRODUCERS.get(id(witness)) if type(witness) is _ProducerCodeWitness else None
    require(type(original) is tuple and len(original) == 7 and original[0] is witness
        and witness._anchor is witness._identity is original and original is _PRODUCER_PINS.get(id(witness))
        and hash_bytes(original[1]) == original[2] and hash_payload(protocol()) == original[4],
        "checkpoint_loader_producer_changed")
    return original


def _audit_producer_code(witness, guard, deadline):
    original = _producer_origin(witness)
    for name, digest in original[3]:
        _tick(deadline)
        # Every REAL Git invocation keeps its original complete guards.
        committed = old_archive.count.old.cache._git(ROOT, ["show", original[5] + ":" + name], guard)
        require(hash_bytes(committed) == digest, "checkpoint_loader_producer_changed")
        _tick(deadline)
    require(_producer_origin(witness) is original, "checkpoint_loader_producer_changed")


def _new_producer_witness(value, guard, deadline):
    raw = _producer_profile(value); manifest, head, scope = EXPECTED_PRODUCER_CODE_MANIFEST, EXPECTED_PRODUCER_HEAD, hash_payload(protocol())
    for name, digest in manifest:
        _tick(deadline)
        committed = old_archive.count.old.cache._git(ROOT, ["show", head + ":" + name], guard)
        require(hash_bytes(committed) == digest, "checkpoint_loader_producer_changed"); _tick(deadline)
    require(manifest is EXPECTED_PRODUCER_CODE_MANIFEST and head is EXPECTED_PRODUCER_HEAD
        and scope == hash_payload(protocol()) and _producer_profile(value) == raw, "checkpoint_loader_producer_changed")
    # Nothing can authenticate a provisional witness while code is still
    # being read: mint only after the complete original guarded verification.
    witness = object.__new__(_ProducerCodeWitness)
    original = witness, raw, hash_bytes(raw), manifest, scope, head, object()
    witness._anchor = witness._identity = original
    _PRODUCERS[id(witness)] = _PRODUCER_PINS[id(witness)] = original
    return witness


def _match_producer(value, witness, plan_sha256, chunk):
    original = _producer_origin(witness)
    require(_producer_profile(value) == original[1] and _digest(plan_sha256)
        and type(chunk) is int and 1 <= chunk <= MAXIMUM_CHUNKS, "checkpoint_loader_producer_changed")
    # Registration binds the chunk, so unlike the invariant producer profile
    # it MUST differ across chunks. This is the exact original operator hash.
    expected = hash_payload({"plan_sha256": plan_sha256, "chunk": chunk,
        "protocol_sha256": value["operator_protocol_sha256"], "head": value["head"], "remote": value["remote"],
        "code_identity_sha256": value["code_identity_sha256"],
        "code_manifest_sha256": hash_payload(dict(original[3]))})
    require(value["registration_sha256"] == expected, "checkpoint_loader_producer_changed")


def _root_membership(mount, system_entries, boundary):
    require(type(system_entries) in (list, tuple), "checkpoint_loader_catalogue_changed")
    names = []
    for row in system_entries:
        _keys(row, ("name", "pin5")); name, pin = row["name"], row["pin5"]
        allowed = getattr(storage, "SYSTEM_ENTRY_NAMES", frozenset())
        require(type(allowed) is frozenset and type(name) is str and name in allowed
            and type(pin) is list and len(pin) == 5 and all(type(item) is int for item in pin),
            "checkpoint_loader_catalogue_changed")
        path = mount / name; info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode) == tuple(pin)
            and path.resolve() == path, "checkpoint_loader_directory_changed")
        names.append(name)
    require(names == sorted(set(names)) and set(os.listdir(mount)) == {"capture", "claim", "checkpoint", *names},
        "checkpoint_loader_negative")
    boundary()


def _catalogue(mount, files, directories, boundary, *, system_entries=()):
    require(type(files) is list and 0 < len(files) <= 4 * 528 + 5 and type(directories) is list,
        "checkpoint_loader_catalogue_changed")
    names, private = [], {}
    # The native root is never an open-ended side channel for a negative or
    # foreign member. System entries are checked separately against ORIGINAL
    # pre-source volume pins by _root_membership, before this byte sweep.
    _root_membership(mount, system_entries, boundary)
    for row in files:
        _keys(row, ("path", "bytes", "sha256", "seal9")); name = _relative(row["path"])
        seal = _seal(row["seal9"])
        require(type(row["bytes"]) is int and row["bytes"] == seal[5] and _digest(row["sha256"])
            and (name.startswith("capture/") or name == "claim/claim.spent.json")
            and not any(word in name.lower() for word in ("refused", "quarantine", "negative")),
            "checkpoint_loader_negative")
        raw, unused = _read_original(mount / name, row["sha256"], row["seal9"], boundary)
        names.append(name); private[name] = raw
    require(names == sorted(set(names)), "checkpoint_loader_catalogue_changed")
    expected_dirs = {"."}
    for name in names:
        parent = Path(name).parent
        while parent != Path("."):
            expected_dirs.add(parent.as_posix()); parent = parent.parent
    observed = []
    for row in directories:
        _keys(row, ("path", "pin4")); name = row["path"]
        require(name == "." or _relative(name), "checkpoint_loader_catalogue_changed")
        _directory(mount / name, row["pin4"]); observed.append(name)
        allowed = {Path(item).parts[len(Path(name).parts) if name != "." else 0]
            for item in names if name == "." or item.startswith(name + "/")}
        if name == ".": allowed = {"capture", "claim", "checkpoint"}  # APFS system entries separately native-owned.
        else: require(set(os.listdir(mount / name)) == allowed, "checkpoint_loader_catalogue_changed")
    require(observed == sorted(set(observed)) and set(observed) == expected_dirs, "checkpoint_loader_catalogue_changed")
    _root_membership(mount, system_entries, lambda: None)
    return private


def _file_metadata(path, seal9):
    """Original full9 only; the complete bytes were authenticated earlier."""
    expected = _seal(list(seal9))
    require(path.resolve() == path and stat.S_ISREG(path.lstat().st_mode)
        and _stamp(path.lstat()) == expected, "checkpoint_loader_seal_changed")
    fds = []
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK); fds.append(fd)
        require(_stamp(os.fstat(fd)) == _stamp(path.lstat()) == expected, "checkpoint_loader_seal_changed")
    finally: _close(fds)
    require(_stamp(path.lstat()) == expected, "checkpoint_loader_seal_changed")


def _checkpoint_metadata(mount, relative_root, body9, receipt9, directories, *, final_mount):
    base = mount / relative_root
    for row in directories: _directory5(mount / row["path"], row["pin5"])
    _file_metadata(base / "attempt-body.raw", body9)
    _file_metadata(base / "attempt-receipt.private.json", receipt9)
    expected = {"chunk", "round"} if final_mount else {"chunk"}
    require(set(os.listdir(mount / "checkpoint")) == expected
        and set(os.listdir(base)) == {"attempt-body.raw", "attempt-receipt.private.json"},
        "checkpoint_loader_negative")
    for row in directories: _directory5(mount / row["path"], row["pin5"])


def _terminal_metadata(index, descriptors, round_directories, round_body9, round_receipt9, receipt_pin, deadline):
    """One finite no-callback original metadata pass after final code/clocks.

    No body reread, expired lease, new baseline, or perpetual/atomic stability
    assertion is made here. Each original native/name/FD pin is observed once.
    """
    _tick(deadline)
    for number, (entry, descriptor) in enumerate(zip(index["chunks"], descriptors), 1):
        _tick(deadline)
        mount = _native(descriptor["volume"], index["plan_sha256"], number, lambda: None)
        _tick(deadline)
        files = descriptor["files"]; names = [row["path"] for row in files]
        expected_dirs = {"."}
        for name in names:
            parent = Path(name).parent
            while parent != Path("."):
                expected_dirs.add(parent.as_posix()); parent = parent.parent
        observed = []
        for row in descriptor["directories"]:
            _tick(deadline)
            name = row["path"]; _directory(mount / name, row["pin4"]); observed.append(name)
            if name != ".":
                allowed = {Path(item).parts[len(Path(name).parts)] for item in names if item.startswith(name + "/")}
                require(set(os.listdir(mount / name)) == allowed, "checkpoint_loader_catalogue_changed")
        require(observed == sorted(set(observed)) and set(observed) == expected_dirs,
            "checkpoint_loader_catalogue_changed")
        for row in files:
            _tick(deadline); _file_metadata(mount / row["path"], row["seal9"]); _tick(deadline)
        _checkpoint_metadata(mount, "checkpoint/chunk", entry["body_seal9"], entry["receipt_seal9"],
            entry["directory_pins"], final_mount=number == len(descriptors))
        _root_membership(mount, descriptor["volume"]["system_entries"], lambda: None)
        _tick(deadline)
    _checkpoint_metadata(Path(EXPECTED_ROUND_MOUNT), "checkpoint/round", round_body9, round_receipt9,
        round_directories, final_mount=True)
    _file_metadata(receipt_pin[0], receipt_pin[2])
    # Direct original pinned clock, not an arbitrary source/repository callback
    # after the last original file/native/membership audit.
    _tick(deadline)


def _attempts(descriptor, private, plan, lifetime, *, ordinal_offset=0):
    attempts = descriptor["attempts"]; chunk = descriptor["plan"]["chunk"]
    require(type(attempts) is list and 0 < len(attempts) <= len(plan.chunk_positions(chunk)) + 16,
        "checkpoint_loader_accounting_changed")
    charges, reservations, covered, chains, epoch_tries = [], [], set(), {}, {}
    claim = _parse(private[descriptor["external_claim_path"]])
    require(claim.get("schema") == "si-count-spent-claim-v1" and claim.get("spent") is True
        and claim.get("chunk") == chunk and claim.get("plan_sha256") == plan.sha256,
        "checkpoint_loader_accounting_changed")
    def clock(value):
        try: return old_archive.count.old.cache.parallel.clock(value)
        except Exception: raise CountCheckpointLoaderRefusal("REFUSED: checkpoint_loader_accounting_changed") from None
    require(type(ordinal_offset) is int and ordinal_offset >= 0, "checkpoint_loader_accounting_changed")
    for local_number, attempt in enumerate(attempts, 1):
        number = ordinal_offset + local_number
        _keys(attempt, ("reservation", "reservation_sha256", "observation_sha256", "http_invoked", "http_status",
            "received_at", "fixed_diagnostic", "START_path", "received_path", "body_path", "receipt_path", "charged_bytes"))
        reservation = attempt["reservation"]
        _keys(reservation, ("schema", "plan_sha256", "chunk_number", "reservation_ordinal", "source_position",
            "matrix_query_ordinal", "lifetime_try", "request_sha256", "accounting_policy_sha256", "bytes_reserved", "dispatch_authority"))
        position = reservation["source_position"]
        require(type(position) is int and position in plan.chunk_positions(chunk)
            and reservation["schema"] == "si-count-attempt-reservation-v1" and reservation["plan_sha256"] == plan.sha256
            and type(reservation["chunk_number"]) is int and reservation["chunk_number"] == chunk
            and type(reservation["reservation_ordinal"]) is int and reservation["reservation_ordinal"] == number
            and type(reservation["lifetime_try"]) is int and reservation["lifetime_try"] == lifetime[position - 1] + 1 <= 3
            and type(reservation["bytes_reserved"]) is int and reservation["bytes_reserved"] == MAXIMUM_BYTES
            and reservation["dispatch_authority"] is False and _digest(reservation["request_sha256"])
            and hash_payload(reservation) == attempt["reservation_sha256"], "checkpoint_loader_accounting_changed")
        ordinal = plan.chunk_positions(chunk).index(position)
        require(reservation["matrix_query_ordinal"] == plan.chunk_matrix_ordinals(chunk)[ordinal],
            "checkpoint_loader_accounting_changed")
        query_plan = plan._parts[1]._parts[1].query_plan
        selected = references.freeze_native_class_query_plan(query_plan._matrix,
            mode="explicit_anchors", selected_query_ordinals=(reservation["matrix_query_ordinal"],))
        require(next(selected.iter_queries()).to_payload()["request_sha256"] == reservation["request_sha256"]
            and type(attempt["http_invoked"]) is bool and (attempt["http_status"] is None
                or type(attempt["http_status"]) is int), "checkpoint_loader_accounting_changed")
        if position in chains:
            previous = chains[position]
            detail = previous["fixed_diagnostic"]
            require(previous["http_status"] is None and type(detail) is dict and detail.get("retryable") is True
                and detail.get("code") == "network_failure" and detail.get("http_status") is None
                and detail.get("phase") == "open" and detail.get("failure_class") in (
                    "timeout", "dns_temporary", "connection_reset", "connection_refused", "connection_aborted")
                and previous["reservation"]["request_sha256"] == reservation["request_sha256"],
                "checkpoint_loader_accounting_changed")
        lifetime[position - 1] += 1; chains[position] = attempt
        started = _parse(private[attempt["START_path"]]); received = _parse(private[attempt["received_path"]])
        require(attempt["START_path"] == f"capture/starts/{number:06d}/START.spent.json"
            and attempt["received_path"] == f"capture/received/{number:06d}/received.private.json",
            "checkpoint_loader_accounting_changed")
        require(started.get("reservation_sha256") == attempt["reservation_sha256"]
            and started.get("request_sha256") == reservation["request_sha256"] and started.get("spent") is True
            and type(started.get("ordinal")) is int and started["ordinal"] == number
            and type(started.get("lifetime_try")) is int and started["lifetime_try"] == reservation["lifetime_try"]
            and started.get("claim_sha256") == hash_bytes(private[descriptor["external_claim_path"]])
            and received.get("observation_sha256") == attempt["observation_sha256"]
            and received.get("START_sha256") == hash_bytes(private[attempt["START_path"]])
            and received.get("http_invoked") is attempt["http_invoked"]
            and type(received.get("http_status")) is type(attempt["http_status"])
            and received.get("http_status") == attempt["http_status"], "checkpoint_loader_accounting_changed")
        require(clock(started.get("started_at")) <= clock(attempt["received_at"]), "checkpoint_loader_accounting_changed")
        if position in epoch_tries:
            require(clock(started["started_at"]) >= epoch_tries[position][1]
                + timedelta(seconds=2 if epoch_tries[position][0] == 1 else 10), "checkpoint_loader_accounting_changed")
        epoch_tries[position] = (epoch_tries.get(position, (0, None))[0] + 1, clock(attempt["received_at"]))
        if attempt["http_invoked"] is True and type(attempt["http_status"]) is int and attempt["http_status"] == 200:
            require(type(attempt["body_path"]) is str and attempt["body_path"] == f"capture/responses/{number:06d}/response.raw"
                and type(attempt["receipt_path"]) is str
                and attempt["receipt_path"] == f"capture/responses/{number:06d}/response.receipt.private.json",
                "checkpoint_loader_accounting_changed")
            raw = private[attempt["body_path"]]; receipt = _parse(private[attempt["receipt_path"]])
            require(raw and receipt.get("body_sha256") == received.get("body_sha256") == hash_bytes(raw)
                and type(receipt.get("body_bytes")) is int and receipt["body_bytes"] == len(raw)
                and receipt.get("http_observation_sha256") == attempt["observation_sha256"]
                and receipt.get("source_admitted") is False and receipt.get("budget_release_authority") is False,
                "checkpoint_loader_accounting_changed")
            charge = len(raw); covered.add(position)
        else:
            require(attempt["body_path"] is attempt["receipt_path"] is None,
                "checkpoint_loader_accounting_changed"); charge = MAXIMUM_BYTES
        require(type(attempt["charged_bytes"]) is int and attempt["charged_bytes"] == charge,
            "checkpoint_loader_accounting_changed")
        charges.append(charge); reservations.append(attempt["reservation_sha256"])
    account = {"chunk": chunk, "reservation_sha256s": reservations, "charges": charges,
        "covered_positions": sorted(covered), "manifest_sha256": descriptor["final_manifest_sha256"]}
    require(account == descriptor["account"] and sorted(covered) == list(plan.chunk_positions(chunk)),
        "checkpoint_loader_accounting_changed")
    return account


def _account_root(account):
    return {"chunk": account["chunk"], "STARTs": len(account["charges"]),
        "charged_bytes": sum(account["charges"]), "reservation_roster_sha256": hash_payload(account["reservation_sha256s"]),
        "charges_sha256": hash_payload(account["charges"]), "covered_positions": len(account["covered_positions"]),
        "covered_positions_sha256": hash_payload(account["covered_positions"]), "manifest_sha256": account["manifest_sha256"]}


class RequalifiedCountTransportCorpus:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise CountCheckpointLoaderRefusal("REFUSED: checkpoint_loader_factory_required")
    def __repr__(self): return "<RequalifiedCountTransportCorpus source-only; redacted>"
    def closed_summary(self):
        try:
            original = _corpus_origin(self)
            issued = _CLOSED.get(self)
            require(type(issued) is tuple and len(issued) == 3 and issued[0] is original
                and type(issued[1]) is bytes and hash_bytes(issued[1]) == issued[2], "checkpoint_loader_not_closed")
            return json.loads(issued[1])
        except BaseException:
            if type(self) is RequalifiedCountTransportCorpus: _FAILED.add(id(self))
            raise


def _corpus_origin(value, expected=None):
    require(type(value) is RequalifiedCountTransportCorpus
        and RequalifiedCountTransportCorpus.__hash__ is object.__hash__
        and RequalifiedCountTransportCorpus.__eq__ is object.__eq__, "checkpoint_loader_binding_changed")
    original = _ISSUED.get(value)
    require(type(original) is tuple and len(original) == 3 and original[0] is value
        and value._anchor is value._identity is original and id(value) not in _FAILED
        and _PRIVATE.get(value) is original[2] and (expected is None or original is expected),
        "checkpoint_loader_binding_changed")
    return original


def _git_allowed(executable, command, cwd, runtime_head):
    if not (type(executable) is str and executable == "git" and type(command) in (list, tuple)
        and command and all(type(item) is str for item in command) and str(cwd) == str(ROOT)):
        return False
    command = tuple(command)
    if len(command) == 3 and command[:2] == ("git", "show"):
        revision, separator, name = command[2].partition(":")
        return separator == ":" and revision in (*HISTORICAL_HEADS, runtime_head, EXPECTED_PRODUCER_HEAD) and name in code_paths()
    if len(command) == 5 and command[:3] == ("git", "merge-base", "--is-ancestor"):
        return command[3] in (*HISTORICAL_HEADS, EXPECTED_PRODUCER_HEAD) and command[4] == runtime_head
    return command in {
        ("git", "ls-remote", "origin", lane.REF), ("git", "ls-remote", "--exit-code", "origin", lane.REF),
        ("git", "rev-parse", "--show-toplevel"), ("git", "rev-parse", "HEAD"),
        ("git", "branch", "--show-current"), ("git", "status", "--porcelain"),
        ("git", "status", "--porcelain=v2", "--branch", "--no-ahead-behind", "--untracked-files=all")}


@contextmanager
def _readonly_seams(runtime_head):
    state = [True]
    def hook(event, args):
        if not state[0]: return
        if event.startswith("socket.") or event in ("os.chflags", "os.chmod", "os.mkdir", "os.remove", "os.rename", "os.rmdir"):
            raise CountCheckpointLoaderRefusal("REFUSED: checkpoint_loader_readonly_required")
        if event == "open":
            flags = args[2]
            require(type(flags) is int and not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND),
                "checkpoint_loader_readonly_required")
        if event == "subprocess.Popen":
            require(_git_allowed(args[0], args[1], args[2], runtime_head),
                "checkpoint_loader_readonly_required")
    sys.addaudithook(hook)
    try: yield
    finally: state[0] = False


@contextmanager
def load_registered_count_checkpoints(root, *, runtime_head, actual_remote,
        complete_code_manifest, archive_code_manifest):
    registered()  # Before any receipt, source, native or code reads.
    require(root == ROOT and root.resolve() == root and Path.cwd().resolve() == root,
        "checkpoint_loader_root_changed")
    require(type(complete_code_manifest) is dict and tuple(sorted(complete_code_manifest)) == code_paths()
        and all(_digest(item) for item in complete_code_manifest.values()), "checkpoint_loader_code_changed")
    deadline, value, producer_witness = _new_deadline(), None, None
    guard = lane.LaneGuard(root, expected_head=runtime_head, expected_remote=actual_remote)
    def clock_boundary(): _tick(deadline)
    def boundary():
        _tick(deadline); guard.check(); _tick(deadline)
    def audit_code(held):
        guard.refresh()
        for name, digest in sorted(complete_code_manifest.items()):
            raw = held.read(root / name, 8 * 1024 ** 2)
            committed = old_archive.count.old.cache._git(root, ["show", runtime_head + ":" + name], guard)
            require(hash_bytes(raw) == hash_bytes(committed) == digest, "checkpoint_loader_code_changed")
        held.check(); boundary()
    try:
        with _readonly_seams(runtime_head):
            boundary()
            with old_archive.load_registered_count_epoch_ledger(root, runtime_head=runtime_head,
                    actual_remote=actual_remote, complete_code_manifest=archive_code_manifest) as archive: pass
            closed_old = archive.closed_summary(); baseline = archive._anchor[0]
            require(closed_old["model_ledger_sha256"] == baseline.sha256 == plans.BASELINE_LEDGER_SHA256,
                "checkpoint_loader_baseline_changed")
            plan = plans.freeze_count_recovery_plan(baseline)
            with old_archive.count.old.cache.HeldFiles(tuple(root / name for name in code_paths()),
                    protected=False, boundary=boundary) as code:
                audit_code(code)
                with _repository_unit(guard, deadline): main_receipt, receipt_pin = _receipt(clock_boundary)
                round_directories = _round_directories()
                def audit_round():
                    with _repository_unit(guard, deadline):
                        return _pair(Path(EXPECTED_ROUND_MOUNT), "checkpoint/round", EXPECTED_ROUND_BODY_SHA256,
                            EXPECTED_ROUND_BODY_SEAL9_SHA256, EXPECTED_ROUND_RECEIPT_SHA256,
                            EXPECTED_ROUND_RECEIPT_SEAL9_SHA256, clock_boundary, hashes=True, directory_pins=round_directories)
                index_raw, round_body9, round_receipt9 = audit_round()
                index = _parse(index_raw)
                _keys(index, ("schema", "phase", "baseline_sha256", "plan_sha256", "chunks",
                    "expected_union_binding_sha256", "expected_accounting", "authority"))
                require(index["schema"] == "si-count-checkpoint-round-v1" and index["phase"] == "PROVISIONAL_STORAGE_FACTS"
                    and index["baseline_sha256"] == baseline.sha256 and index["plan_sha256"] == plan.sha256
                    and type(index["chunks"]) is list and len(index["chunks"]) == len(plan._parts[3]) <= MAXIMUM_CHUNKS
                    and hash_payload(index["expected_accounting"]) == index["expected_union_binding_sha256"]
                    == main_receipt["expected_union_binding_sha256"], "checkpoint_loader_index_changed")
                descriptors, accounts, lifetime = [], [], list(plan._parts[4][0])
                def sweep(root_entry, number, *, account=True):
                    with _repository_unit(guard, deadline): return sweep_files(root_entry, number, account=account)
                def sweep_files(root_entry, number, *, account=True):
                    nonlocal producer_witness
                    _keys(root_entry, ("chunk", "mount", "relative_root", "body_sha256", "body_seal9",
                        "receipt_sha256", "receipt_seal9", "descriptor_sha256", "directory_pins"))
                    require(type(root_entry["chunk"]) is int and root_entry["chunk"] == number
                        and root_entry["relative_root"] == "checkpoint/chunk", "checkpoint_loader_index_changed")
                    raw, unused3, unused4 = _pair(Path(root_entry["mount"]), "checkpoint/chunk", root_entry["body_sha256"],
                        root_entry["body_seal9"], root_entry["receipt_sha256"], root_entry["receipt_seal9"], clock_boundary,
                        directory_pins=root_entry["directory_pins"], final_mount=number == len(plan._parts[3]))
                    require(hash_bytes(raw) == root_entry["descriptor_sha256"], "checkpoint_loader_index_changed")
                    descriptor = _parse(raw)
                    _keys(descriptor, ("schema", "phase", "producer", "archive", "plan", "payload_base", "files",
                        "directories", "volume", "attempts", "external_claim_path", "final_manifest_sha256", "account", "authority"))
                    require(descriptor["schema"] == "si-count-checkpoint-descriptor-v1"
                        and descriptor["phase"] == "PROVISIONAL_STORAGE_FACTS" and descriptor["plan"] == {
                            "sha256": plan.sha256, "chunk": number, "positions": list(plan.chunk_positions(number)),
                            "total_chunks": len(plan._parts[3])} and descriptor["archive"]["baseline_sha256"] == baseline.sha256,
                        "checkpoint_loader_baseline_changed")
                    if producer_witness is None:
                        require(number == 1, "checkpoint_loader_producer_changed")
                        producer_witness = _new_producer_witness(descriptor["producer"], guard, deadline)
                    _match_producer(descriptor["producer"], producer_witness, plan.sha256, number)
                    mount = _native(descriptor["volume"], plan.sha256, number, clock_boundary)
                    require(str(mount) == root_entry["mount"], "checkpoint_loader_native_changed")
                    private = _catalogue(mount, descriptor["files"], descriptor["directories"], clock_boundary,
                        system_entries=descriptor["volume"]["system_entries"])
                    if account: accounts.append(_attempts(descriptor, private, plan, lifetime,
                        ordinal_offset=sum(len(item["charges"]) for item in accounts)))
                    manifest = _parse(private["capture/final_manifest/manifest.private.json"])
                    expected_members = [{"name": row["path"][8:], "bytes": row["bytes"], "sha256": row["sha256"]}
                        for row in descriptor["files"] if row["path"].startswith("capture/")
                        and row["path"] != "capture/final_manifest/manifest.private.json"]
                    require(manifest.get("payload") == {"members": expected_members}
                        and hash_bytes(private["capture/final_manifest/manifest.private.json"]) == descriptor["final_manifest_sha256"],
                        "checkpoint_loader_catalogue_changed")
                    return descriptor
                for number, root_entry in enumerate(index["chunks"], 1): descriptors.append(sweep(root_entry, number))
                expected = {"baseline_sha256": baseline.sha256, "plan_sha256": plan.sha256,
                    "accounts": [_account_root(account) for account in accounts]}
                starts = sum(len(account["charges"]) for account in accounts)
                charged = sum(sum(account["charges"]) for account in accounts)
                require(expected == index["expected_accounting"] and 13992 + starts <= 84005
                    and 23452681 + charged <= 4 * 1024 ** 3, "checkpoint_loader_accounting_changed")
                summary = {"schema": "si-requalified-count-transport-corpus-v1", "status": "contexts_open",
                    "chunks": len(descriptors), "new_retained_STARTs": starts, "new_retained_charged_bytes": charged,
                    "baseline_sha256": baseline.sha256, "plan_sha256": plan.sha256,
                    "Main_exit0_receipt_sha256": EXPECTED_RECEIPT_SHA256,
                    "round_index_sha256": EXPECTED_ROUND_BODY_SHA256,
                    "expected_union_binding_sha256": index["expected_union_binding_sha256"],
                    "producer_actual_union_sha256": main_receipt["actual_union_sha256"], "authority": authority()}
                value = object.__new__(RequalifiedCountTransportCorpus)
                private = (tuple(canonical_json(item).encode() for item in descriptors),
                    tuple(canonical_json(item).encode() for item in accounts), index_raw, object())
                original = value, canonical_json(summary).encode(), private
                value._anchor = value._identity = original; _ISSUED[value] = original; _PRIVATE[value] = private
                yield value
                _corpus_origin(value, original)
                for number, root_entry in enumerate(index["chunks"], 1):
                    require(sweep(root_entry, number, account=False) == descriptors[number - 1], "checkpoint_loader_file_changed")
                require(audit_round()[0] == index_raw, "checkpoint_loader_index_changed")
                with _repository_unit(guard, deadline): _read_original(*receipt_pin[:2], receipt_pin[2], clock_boundary)
                code.check(); audit_code(code)
            with old_archive.count.old.cache.HeldFiles(tuple(root / name for name in code_paths()),
                    protected=False, boundary=boundary) as final_code: audit_code(final_code)
            _audit_producer_code(producer_witness, guard, deadline)
            # Last original source audit follows the terminal code context exit.
            for number, root_entry in enumerate(index["chunks"], 1):
                require(sweep(root_entry, number, account=False) == descriptors[number - 1], "checkpoint_loader_file_changed")
            require(audit_round()[0] == index_raw, "checkpoint_loader_index_changed")
            with _repository_unit(guard, deadline): _read_original(*receipt_pin[:2], receipt_pin[2], clock_boundary)
            boundary()
            closed = dict(summary, status="closed_requalified_transport_custody_only")
            raw = canonical_json(closed).encode(); digest = hash_bytes(raw); boundary()
            _terminal_metadata(index, descriptors, round_directories, round_body9, round_receipt9, receipt_pin, deadline)
            _CLOSED[value] = original, raw, digest
    except BaseException:
        if value is not None:
            _FAILED.add(id(value))
            if (type(value) is RequalifiedCountTransportCorpus and RequalifiedCountTransportCorpus.__hash__ is object.__hash__
                and RequalifiedCountTransportCorpus.__eq__ is object.__eq__): _CLOSED.pop(value, None)
        raise
