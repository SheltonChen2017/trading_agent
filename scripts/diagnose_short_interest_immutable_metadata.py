"""One offline NEW-inode immutable-flag proof; no source/key/capture dispatch.

Old failed files and source claims are not reopened. This proves a prospective
publication primitive, not the actor behind an old timestamp change or inputs.
"""
from contextlib import ExitStack
import ctypes
import errno
import os
from pathlib import Path
import stat
import time

from data.hashing import hash_bytes, hash_payload
from scripts import diagnose_short_interest_new_metadata_custody as previous
from scripts import short_interest_immutable_metadata as immutable

DRIVER = "scripts/diagnose_short_interest_immutable_metadata.py"
HELPER = "scripts/short_interest_immutable_metadata.py"
NAMESPACE = "kernel-immutable-metadata-20261025-v2"
OUTPUT = previous.OUTPUT.parent / NAMESPACE
NAME = "one-safe-nonclaim.private.json"
MAXIMUM_SECONDS, HOLD_SECONDS = 120, 5
PROTOCOL_SHA256 = "131d639a9feb274e095c7d4970df00efd5841837b7c2506980954f30ea718e80"
_CODES = frozenset("""
immutable_proof_registration_changed immutable_proof_driver_changed
immutable_proof_manifest_changed immutable_proof_code_changed immutable_proof_deadline
immutable_proof_challenge_not_denied immutable_proof_challenge_errno
immutable_proof_original_stamp_changed immutable_proof_original_bytes_changed
immutable_proof_result_missing immutable_proof_code_context_changed
immutable_proof_output_not_ignored
""".split())


class ImmutableProofRefusal(ValueError):
    pass


def require(value, code):
    if not value:
        raise ImmutableProofRefusal("REFUSED: " + code)


def failure_summary(error):
    if type(error) is ImmutableProofRefusal:
        args = BaseException.args.__get__(error, BaseException)
        code = next((name for name in _CODES if type(args) is tuple and len(args) == 1
            and type(args[0]) is str and args[0] == "REFUSED: " + name), None)
        return {"category": "local_contract_refusal", "errno_name": None, "contract_code": code}
    return immutable.failure_summary(error)


def authority():
    return {"offline_new_inode_only": True, "historical_actor": "UNKNOWN",
        "historical_repair_established": False, "provider_HTTP": 0, "credential_reads": 0,
        "new_source_claims": 0, "source_STARTs": 0, "source_bytes": 0,
        "source_admitted": False, "ready_for_backtest": False, "outcome_looks": 0,
        "qc_attempts": 0, "trading_authority": False}


def code_paths():
    return tuple(sorted((*previous.code_paths(), HELPER, DRIVER)))


def protocol():
    return {"schema": "si-kernel-immutable-metadata-proof-policy-v2",
        "decision": "SI-DEC-20261025-07", "authority_id": "SI-AUTH-20261025-01",
        "driver": DRIVER, "helper": HELPER, "output": str(OUTPUT), "name": NAME,
        "immutable_helper_policy_sha256": hash_payload(immutable.policy()),
        "raw_sha256": hash_bytes(previous.metadata_bytes()), "bytes": 186,
        "maximum_seconds": MAXIMUM_SECONDS, "minimum_hold_seconds": HOLD_SECONDS,
        "new_inodes": 1, "retries": 0,
        "flag": "FD_preserve_original_UF_TRACKED_add_UF_IMMUTABLE_before_first_seal_never_clear",
        "initial_flags_allowed": [0, 64], "original_failed_v1_reopened": False,
        "challenge": ["write_open", "same_mode_fchmod", "fixed_fsetxattr"],
        "required_errno": "EPERM", "old_evidence_reopened": False,
        "closure": "all_original_code_and_metadata_context_exits_then_fresh_committed_code_and_original_nine_field_byte_audit",
        "code_paths": list(code_paths()), "authority": authority()}


def _registered():
    require(hash_payload(protocol()) == PROTOCOL_SHA256 and len(code_paths()) == 60
        and (MAXIMUM_SECONDS, HOLD_SECONDS) == (120, 5), "immutable_proof_registration_changed")


def _stamp(info):
    return immutable._stamp(info)


def _original(fd, owned, expected, raw):
    owned.check()
    for info in (os.fstat(fd), os.stat(NAME, dir_fd=owned._anchor[2], follow_symlinks=False)):
        require(stat.S_ISREG(info.st_mode) and hash_payload(list(_stamp(info))) == expected
            and immutable._flags(info) in (stat.UF_IMMUTABLE, stat.UF_IMMUTABLE | stat.UF_TRACKED),
            "immutable_proof_original_stamp_changed")
    os.lseek(fd, 0, os.SEEK_SET)
    require(os.read(fd, 1025) == raw, "immutable_proof_original_bytes_changed")
    require(hash_payload(list(_stamp(os.fstat(fd)))) == expected,
        "immutable_proof_original_stamp_changed")


def _after_all_closes(target, expected_directory, expected_parent, expected, raw, guard):
    """Reopen only against ORIGINAL inode/stamp pins, never choose a new seal."""
    guard.check()
    require(target.resolve() == target and target.parent.resolve() == target.parent,
        "immutable_proof_original_stamp_changed")
    stamp_directory = previous.prior._OwnedOutput._stamp
    require(stamp_directory(target.lstat()) == expected_directory
        and stamp_directory(target.parent.lstat()) == expected_parent,
        "immutable_proof_original_stamp_changed")
    parent_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directory_fd = None
    try:
        require(stamp_directory(os.fstat(parent_fd)) == expected_parent,
            "immutable_proof_original_stamp_changed")
        directory_fd = os.open(target.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        require(stamp_directory(os.fstat(directory_fd)) == expected_directory,
            "immutable_proof_original_stamp_changed")
        fd = os.open(NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        try:
            for info in (os.fstat(fd), os.stat(NAME, dir_fd=directory_fd, follow_symlinks=False)):
                require(stat.S_ISREG(info.st_mode) and hash_payload(list(_stamp(info))) == expected,
                    "immutable_proof_original_stamp_changed")
            require(os.read(fd, 1025) == raw, "immutable_proof_original_bytes_changed")
        finally:
            os.close(fd)
        require(hash_payload(list(_stamp(os.stat(NAME, dir_fd=directory_fd, follow_symlinks=False)))) == expected,
            "immutable_proof_original_stamp_changed")
    finally:
        if directory_fd is not None: os.close(directory_fd)
        os.close(parent_fd)
    require(stamp_directory(target.lstat()) == expected_directory
        and stamp_directory(target.parent.lstat()) == expected_parent
        and hash_payload(list(_stamp((target / NAME).lstat()))) == expected,
        "immutable_proof_original_stamp_changed")
    guard.check()


def _challenge(fd, owned):
    def write_open():
        opened = os.open(NAME, os.O_WRONLY | os.O_NOFOLLOW, dir_fd=owned._anchor[2])
        os.close(opened)
    def same_mode():
        os.fchmod(fd, 0o600)
    def fixed_attribute():
        # Darwin's local setxattr(2) ABI; never a pathname or arbitrary symbol.
        library = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        call = library.fsetxattr
        call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
        call.restype = ctypes.c_int
        value = ctypes.create_string_buffer(b"1")
        ctypes.set_errno(0)
        result = call(fd, b"org.codex.short-interest.offline-proof", value, 1, 0, 2)
        number = ctypes.get_errno()
        require(type(result) is int and result in (0, -1) and type(number) is int,
            "immutable_proof_challenge_not_denied")
        if result == -1:
            raise OSError(number, "fixed_offline_challenge")
    results = []
    for name, operation in (("write_open", write_open), ("same_mode_fchmod", same_mode),
                            ("fixed_fsetxattr", fixed_attribute)):
        try:
            operation()
        except OSError as error:
            require(error.errno == errno.EPERM, "immutable_proof_challenge_errno")
            results.append({"challenge": name, "result": "denied", "errno_name": "EPERM"})
        else:
            raise ImmutableProofRefusal("REFUSED: immutable_proof_challenge_not_denied")
    return results


def _code(root, guard, mapping, held):
    require(type(mapping) is dict and set(mapping) == set(code_paths()),
        "immutable_proof_manifest_changed")
    rows, identity = previous.count.old.cache._code_manifest(root, guard.binding()[1], code_paths(), held, guard)
    require({row["path"]: row["sha256"] for row in rows} == mapping,
        "immutable_proof_code_changed")
    held.check()
    return identity


def run_registered(root, *, runtime_head, actual_remote, complete_code_manifest):
    began, last_tick = time.monotonic(), [None]
    started = previous.prior._utc_now()
    started_clock = previous.count.old.parallel.clock(started)
    def window():
        now = time.monotonic()
        require(type(now) in (int, float) and type(began) in (int, float)
            and 0 <= began <= now <= 2 ** 53 and (last_tick[0] is None or last_tick[0] <= now)
            and now - began < MAXIMUM_SECONDS,
            "immutable_proof_deadline")
        last_tick[0] = now
        return now
    _registered()
    require(root == previous.lane.ROOT and Path(__file__).absolute() == root / DRIVER,
        "immutable_proof_driver_changed")
    guard = previous.lane.LaneGuard(root, expected_head=runtime_head, expected_remote=actual_remote)
    guard.refresh(); window()
    raw, held_live, identity, fd, result = previous.metadata_bytes(), [True], None, None, None
    target = root / OUTPUT
    # prepare_capture_directory refuses ANY old run; no existing evidence adopted.
    with ExitStack() as code_stack:
        held = code_stack.enter_context(previous.count.old.cache.HeldFiles(
            tuple(root / name for name in code_paths()), protected=False, boundary=guard.check))
        identity = _code(root, guard, complete_code_manifest, held); window()
        require(previous.count.old.cache._git(root, ["check-ignore", str(target)], guard).strip()
            == str(target).encode(), "immutable_proof_output_not_ignored")
        with previous.prior._OwnedOutput(previous.prior._prepare_capture_directory(target), guard.check) as owned:
            directory_stamp, parent_stamp = owned._anchor[4:6]
            def boundary():
                guard.check(); window()
                if held_live[0]: held.check()
            try:
                with immutable.prepare_owned_immutable_metadata(owned, NAME, raw, parent=False,
                        boundary=boundary) as capability:
                    capability.seal_once(); capability.check()
                    observation = capability.observation()
                    expected = observation["seal_stamp_sha256"]
                    fd = os.open(NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=owned._anchor[2])
                    _original(fd, owned, expected, raw)
                    challenges = _challenge(fd, owned)
                    until = window() + HOLD_SECONDS
                    while window() < until:
                        time.sleep(.25); capability.check(); _original(fd, owned, expected, raw); window()
                    _code(root, guard, complete_code_manifest, held); window()
                    code_stack.close()  # Success before switching the stable callback.
                    held_live[0] = False
                    capability.check(); guard.refresh(); window()
                closed = capability.closed_summary()
                _original(fd, owned, expected, raw); guard.refresh(); window()
                result = {"schema": "si-kernel-immutable-metadata-proof-closed-v2",
                    "status": "closed_offline_new_inode_only", "runtime_head": runtime_head,
                    "actual_remote": actual_remote, "code_identity_sha256": identity,
                    "code_manifest_sha256": hash_payload(complete_code_manifest),
                    "protocol_sha256": PROTOCOL_SHA256, "started_at": started,
                    "metadata_raw_sha256": hash_bytes(raw),
                    "seal_stamp_sha256": expected, "helper_closed_summary_sha256": hash_payload(closed),
                    "challenges": challenges, "original_code_and_metadata_contexts_closed": True,
                    "authority": authority()}
            finally:
                if fd is not None: os.close(fd)
    guard.refresh(); window()
    # This fresh audit is AFTER original code, metadata, retained reader and
    # output context exits; its own close must also succeed before emission.
    with previous.count.old.cache.HeldFiles(tuple(root / name for name in code_paths()),
            protected=False, boundary=guard.check) as final:
        require(_code(root, guard, complete_code_manifest, final) == identity,
            "immutable_proof_code_changed")
    window()
    _after_all_closes(target, directory_stamp, parent_stamp, expected, raw, guard); window()
    require(type(result) is dict, "immutable_proof_result_missing")
    closed_at = previous.prior._utc_now()
    require(previous.count.old.parallel.clock(closed_at) >= started_clock,
        "immutable_proof_deadline")
    result["closed_at"] = closed_at
    return result
