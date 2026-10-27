"""Finite synthetic maximum-body and canonical-receipt custody proof.

No provider, source claim, budget settlement or source admission is performed.
All original per-file checks and deadlines remain enforced by the new helper.
"""
from contextlib import ExitStack
import ctypes
import errno
import os
from pathlib import Path
import stat
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import diagnose_short_interest_isolated_immutable_metadata as previous
from scripts import short_interest_body_receipt_custody as custody
from scripts import short_interest_body_receipt_volume as storage
from scripts import short_interest_body_receipt_monitor as monitor

base = previous.base
DRIVER = "scripts/diagnose_short_interest_body_receipt_custody.py"
HELPER = "scripts/short_interest_body_receipt_custody.py"
STORAGE = "scripts/short_interest_body_receipt_volume.py"
MONITOR = "scripts/short_interest_body_receipt_monitor.py"
WRAPPER = "scripts/run_short_interest_body_receipt_offline.py"
INNER_DIRECTORY = "proof"
MAXIMUM_SECONDS, HOLD_SECONDS = 420, 5
MAXIMUM_BODY_BYTES, MAXIMUM_RECEIPT_BYTES = 2 * 1024 ** 2, 1024
EXPECTED_CODE_PATHS = 70
BODY_SHA256 = "03359e9fa404fac2200a0e3e9fa0dcd8eb973358a76e24b805de7e7566a2fd4a"
PROTOCOL_SHA256 = "df8990fee21d8192cdbf76c4d934007101c189bd24b86a66f719d73d180564f9"
_LAST_TRANSITION = None
_LAST_STAGE = "not_entered"
_RUN_USED, _CLOSED_FAILED = False, False
_CLOSED_RECORD, _CLOSED_ORIGINAL = None, None
_STAGES = frozenset("""not_entered registration code_context_open storage_context_open
output_context_open body_receipt_context_open pair_checking file_challenges
pair_hold original_code_context_exit pair_context_exit output_context_exit
volume_context_exit terminal_original_audits closed""".split())
_CODES = frozenset("""body_receipt_proof_registration_changed body_receipt_proof_driver_changed
body_receipt_proof_manifest_changed body_receipt_proof_code_changed body_receipt_proof_deadline
body_receipt_proof_result_missing body_receipt_proof_output_not_ignored
body_receipt_proof_original_stamp_changed body_receipt_proof_original_bytes_changed
body_receipt_proof_challenge_not_denied body_receipt_proof_challenge_errno
body_receipt_proof_already_invoked body_receipt_proof_not_original_closed
body_receipt_proof_fd_close_failed""".split())


class BodyReceiptProofRefusal(ValueError):
    pass


def require(value, code):
    if not value: raise BodyReceiptProofRefusal("REFUSED: " + code)


def authority():
    return {**previous.authority(), "maximum_body_custody_proved": False,
        "synthetic_maximum_body_and_receipt_only": True, "budget_settlement_authority": False,
        "production_body_durability_admitted": False, "chunk_transport_admitted": False}


def synthetic_body():
    marker = b"SHORT_INTEREST_OFFLINE_SYNTHETIC_BODY_V1\n"
    copies, tail = divmod(MAXIMUM_BODY_BYTES, len(marker))
    return marker * copies + marker[:tail]


def binding():
    return custody.freeze_body_receipt_binding(
        request_sha256=hash_bytes(b"fixed_offline_synthetic_request_v1"),
        attempt_sha256=hash_bytes(b"fixed_offline_synthetic_NONCLAIM_attempt_v1"),
        reservation_sha256=hash_bytes(b"fixed_offline_synthetic_NO_BUDGET_RESERVATION_v1"),
        protocol_sha256=PROTOCOL_SHA256)


def code_paths():
    return tuple(sorted((*previous.code_paths(), HELPER, STORAGE, MONITOR, DRIVER, WRAPPER)))


def protocol():
    return {"schema": "si-body-receipt-custody-proof-policy-v1",
        "decision": "SI-DEC-20261027-06", "authority_id": "SI-AUTH-20261026-02",
        "driver": DRIVER, "helper": HELPER, "offline_harness": WRAPPER,
        "bound_antecedent_not_runtime_imported": [previous.WRAPPER],
        "storage_policy_sha256": hash_payload(storage.policy()),
        "custody_policy_sha256": hash_payload(custody.policy()),
        "monitor_policy_sha256": hash_payload(monitor.policy()),
        "inner_directory": INNER_DIRECTORY, "body_name": custody.BODY_NAME,
        "receipt_name": custody.RECEIPT_NAME, "body_bytes": MAXIMUM_BODY_BYTES,
        "body_sha256": BODY_SHA256, "maximum_receipt_bytes": MAXIMUM_RECEIPT_BYTES,
        "receipt": "internal_canonical_receipt_bound_to_exact_body_and_four_fixed_synthetic_hashes",
        "maximum_seconds": MAXIMUM_SECONDS, "minimum_hold_seconds": HOLD_SECONDS,
        "per_file_creation_seal_seconds": 8, "new_probe_inodes": 2, "native_set_calls": 2,
        "native_roles": ["body", "receipt"], "retries": 0,
        "challenge_per_role": ["write_open", "same_mode_fchmod", "fixed_fsetxattr"],
        "required_errno": "EPERM", "old_evidence_reopened": False,
        "original_seal_checks_unchanged": True,
        "metadata_boundary": "original_volume_check_with_two_fresh_pre_post_lane_and_full_code_callbacks",
        "failure_stage": "fixed_entered_stage_may_include_callback_or_cleanup_not_forensic_cause",
        "closure": "both_original_file_pair_output_code_exits_then_volume_exit_fresh_committed_code_original_pair_nine_field_byte_and_volume_audits",
        "no_budget_release": "pair_or_inner_closure_never_releases_full_page_or_START_reservations",
        "code_paths": list(code_paths()), "authority": authority()}


def entered_stage():
    return _LAST_STAGE if type(_LAST_STAGE) is str and _LAST_STAGE in _STAGES else "not_entered"


def failure_summary(error):
    if type(error) is BodyReceiptProofRefusal:
        args = BaseException.args.__get__(error, BaseException)
        code = next((name for name in _CODES if type(args) is tuple and len(args) == 1
            and type(args[0]) is str and args[0] == "REFUSED: " + name), None)
        result = {"category": "local_contract_refusal", "contract_code": code, "errno_name": None}
    elif type(error) is storage.IsolatedVolumeRefusal:
        result = storage.failure_summary(error)
    elif type(error) is monitor.BodyReceiptMonitorRefusal:
        result = monitor.failure_summary(error)
    elif type(error) is custody.BodyReceiptRefusal:
        result = custody.failure_summary(error)
    else:
        result = base._failure_summary(error)
    result["storage_association"] = storage.association_diagnostic()
    result["entered_stage"] = entered_stage()
    if _LAST_TRANSITION is not None:
        try: result["native_transition"] = _LAST_TRANSITION.report()
        except monitor.BodyReceiptMonitorRefusal:
            result["native_transition"] = {"status": "no_closed_observer_report"}
    return result


def _code(root, guard, mapping, held):
    require(type(mapping) is dict and set(mapping) == set(code_paths()), "body_receipt_proof_manifest_changed")
    rows, identity = base.previous.count.old.cache._code_manifest(
        root, guard.binding()[1], code_paths(), held, guard)
    require({row["path"]: row["sha256"] for row in rows} == mapping, "body_receipt_proof_code_changed")
    held.check()
    return identity


def _original(fd, directory_fd, name, expected, raw):
    """Audit only the original seal, full bytes and original readonly FD."""
    import fcntl
    require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
        "body_receipt_proof_original_stamp_changed")
    def pair():
        for info in (os.fstat(fd), os.stat(name, dir_fd=directory_fd, follow_symlinks=False)):
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and info.st_size == len(raw)
                and hash_payload(list(base.immutable._stamp(info))) == expected
                and base.immutable._flags(info) in (2, 66), "body_receipt_proof_original_stamp_changed")
    pair()
    os.lseek(fd, 0, os.SEEK_SET)
    parts, length = [], 0
    while length <= len(raw):
        part = os.read(fd, min(65536, len(raw) + 1 - length))
        if not part: break
        parts.append(part); length += len(part)
    require(b"".join(parts) == raw, "body_receipt_proof_original_bytes_changed")
    pair()


def _after_all_closes(target, expected_directory, expected_parent, files, guard):
    guard.check()
    stamp = base.previous.prior._OwnedOutput._stamp
    require(target.resolve() == target and target.parent.resolve() == target.parent
        and stamp(target.lstat()) == expected_directory and stamp(target.parent.lstat()) == expected_parent,
        "body_receipt_proof_original_stamp_changed")
    parent_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directory_fd = None
    try:
        require(stamp(os.fstat(parent_fd)) == expected_parent, "body_receipt_proof_original_stamp_changed")
        directory_fd = os.open(target.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        require(stamp(os.fstat(directory_fd)) == expected_directory, "body_receipt_proof_original_stamp_changed")
        require(set(os.listdir(directory_fd)) == {row["name"] for row in files}, "body_receipt_proof_original_stamp_changed")
        for row in files:
            fd = os.open(row["name"], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
            try: _original(fd, directory_fd, row["name"], row["seal_stamp_sha256"], row["raw"])
            finally: os.close(fd)
        for row in files:
            require(hash_payload(list(base.immutable._stamp(os.stat(row["name"], dir_fd=directory_fd,
                follow_symlinks=False)))) == row["seal_stamp_sha256"], "body_receipt_proof_original_stamp_changed")
        require(set(os.listdir(directory_fd)) == {row["name"] for row in files},
            "body_receipt_proof_original_stamp_changed")
    finally:
        if directory_fd is not None: os.close(directory_fd)
        os.close(parent_fd)
    require(stamp(target.lstat()) == expected_directory and stamp(target.parent.lstat()) == expected_parent
        and set(os.listdir(target)) == {row["name"] for row in files},
        "body_receipt_proof_original_stamp_changed")
    guard.check()


def _challenge(fd, directory_fd, name):
    def write_open():
        opened = os.open(name, os.O_WRONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        os.close(opened)
    def same_mode(): os.fchmod(fd, 0o600)
    def fixed_attribute():
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
            "body_receipt_proof_challenge_not_denied")
        if result == -1: raise OSError(number, "fixed_offline_challenge")
    rows = []
    for label, operation in (("write_open", write_open), ("same_mode_fchmod", same_mode), ("fixed_fsetxattr", fixed_attribute)):
        try: operation()
        except OSError as error:
            require(error.errno == errno.EPERM, "body_receipt_proof_challenge_errno")
            rows.append({"challenge": label, "result": "denied", "errno_name": "EPERM"})
        else: raise BodyReceiptProofRefusal("REFUSED: body_receipt_proof_challenge_not_denied")
    return rows


def _drain_fds(fds):
    failed = False
    while fds:
        try: os.close(fds.pop())
        except BaseException: failed = True
    require(not failed, "body_receipt_proof_fd_close_failed")


def run_registered(root, *, runtime_head, actual_remote, complete_code_manifest):
    global _LAST_TRANSITION, _LAST_STAGE, _RUN_USED, _CLOSED_RECORD, _CLOSED_ORIGINAL
    require(not _RUN_USED, "body_receipt_proof_already_invoked")
    _RUN_USED = True
    _LAST_TRANSITION, _LAST_STAGE = None, "registration"
    began, last_tick = time.monotonic(), [None]
    started = base.previous.prior._utc_now()
    started_clock = base.previous.count.old.parallel.clock(started)
    def window():
        now = time.monotonic()
        require(type(now) in (int, float) and type(began) in (int, float) and 0 <= began <= now <= 2 ** 53
            and (last_tick[0] is None or last_tick[0] <= now) and now - began < MAXIMUM_SECONDS,
            "body_receipt_proof_deadline")
        last_tick[0] = now
        return now
    require(hash_payload(protocol()) == PROTOCOL_SHA256 and len(code_paths()) == EXPECTED_CODE_PATHS
        and (MAXIMUM_SECONDS, HOLD_SECONDS, MAXIMUM_BODY_BYTES, MAXIMUM_RECEIPT_BYTES) == (420, 5, 2097152, 1024),
        "body_receipt_proof_registration_changed")
    require(root == base.previous.lane.ROOT and Path(__file__).absolute() == root / DRIVER,
        "body_receipt_proof_driver_changed")
    guard = base.previous.lane.LaneGuard(root, expected_head=runtime_head, expected_remote=actual_remote)
    guard.refresh(); window()
    raw, held_live, result, file_rows, fds = synthetic_body(), [True], None, None, []
    require(type(raw) is bytes and len(raw) == MAXIMUM_BODY_BYTES and hash_bytes(raw) == BODY_SHA256,
        "body_receipt_proof_registration_changed")
    with ExitStack() as code_stack:
        _LAST_STAGE = "code_context_open"
        held = code_stack.enter_context(base.previous.count.old.cache.HeldFiles(
            tuple(root / name for name in code_paths()), protected=False, boundary=guard.check))
        identity = _code(root, guard, complete_code_manifest, held); window()
        def storage_boundary():
            guard.check(); window()
            if held_live[0]: held.check()
        _LAST_STAGE = "storage_context_open"
        with storage.prepare_registered_volume(root, boundary=storage_boundary) as volume:
            target = volume.mountpoint / INNER_DIRECTORY
            require(base.previous.count.old.cache._git(root, ["check-ignore", str(target)], guard).strip()
                == str(target).encode(), "body_receipt_proof_output_not_ignored")
            _LAST_STAGE = "output_context_open"
            with base.previous.prior._OwnedOutput(
                    base.previous.prior._prepare_capture_directory(target), guard.check) as owned:
                directory_stamp, parent_stamp = owned._anchor[4:6]
                pair_binding = binding()
                def boundary(): volume.check()
                try:
                    with monitor.observe_original_transition(directory_fd=owned._anchor[2], binding=pair_binding) as diagnostic:
                        _LAST_TRANSITION = diagnostic
                        _LAST_STAGE = "body_receipt_context_open"
                        with custody.prepare_owned_body_receipt(owned, raw, binding=pair_binding, boundary=boundary) as pair:
                            _LAST_STAGE = "pair_checking"
                            pair.check()
                            receipt = pair.read_receipt()
                            observation = pair.observation()
                            file_rows = [{"role": role, "name": name, "raw": value,
                                "seal_stamp_sha256": observation["files"][index]["seal_stamp_sha256"]}
                                for index, (role, name, value) in enumerate((("body", custody.BODY_NAME, raw),
                                    ("receipt", custody.RECEIPT_NAME, receipt)))]
                            require(pair.read_body() == raw and 0 < len(receipt) <= MAXIMUM_RECEIPT_BYTES,
                                "body_receipt_proof_original_bytes_changed")
                            for row in file_rows:
                                fd = os.open(row["name"], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                    dir_fd=owned._anchor[2]); fds.append(fd)
                                _original(fd, owned._anchor[2], row["name"], row["seal_stamp_sha256"], row["raw"])
                            _LAST_STAGE = "file_challenges"
                            challenges = [{"role": row["role"], "name": row["name"],
                                "challenges": _challenge(fd, owned._anchor[2], row["name"])}
                                for fd, row in zip(fds, file_rows)]
                            _LAST_STAGE = "pair_hold"
                            until = window() + HOLD_SECONDS
                            while window() < until:
                                time.sleep(.25); pair.check()
                                for fd, row in zip(fds, file_rows):
                                    _original(fd, owned._anchor[2], row["name"], row["seal_stamp_sha256"], row["raw"])
                                window()
                            _code(root, guard, complete_code_manifest, held); window()
                            _LAST_STAGE = "original_code_context_exit"
                            code_stack.close(); held_live[0] = False
                            pair.check(); guard.refresh(); window()
                            _LAST_STAGE = "pair_context_exit"
                        closed = pair.closed_summary()
                        for fd, row in zip(fds, file_rows):
                            _original(fd, owned._anchor[2], row["name"], row["seal_stamp_sha256"], row["raw"])
                        boundary()
                    trace_report = diagnostic.report()
                    require(trace_report["diagnostic"]["observer_complete"] is True,
                        "body_receipt_proof_result_missing")
                    result = {"schema": "si-body-receipt-custody-proof-closed-v1",
                        "status": "closed_offline_synthetic_maximum_body_receipt_only", "runtime_head": runtime_head,
                        "actual_remote": actual_remote, "code_identity_sha256": identity,
                        "code_manifest_sha256": hash_payload(complete_code_manifest), "protocol_sha256": PROTOCOL_SHA256,
                        "started_at": started, "binding_sha256": pair_binding.sha256,
                        "files": [{key: (len(row["raw"]) if key == "bytes" else hash_bytes(row["raw"]) if key == "raw_sha256"
                            else row[key]) for key in ("role", "name", "bytes", "raw_sha256", "seal_stamp_sha256")}
                            for row in file_rows], "helper_closed_summary_sha256": hash_payload(closed),
                        "native_transition": trace_report, "challenges": challenges,
                        "original_code_and_pair_contexts_closed": True, "authority": authority()}
                finally:
                    _drain_fds(fds)
            _LAST_STAGE = "output_context_exit"
            guard.refresh(); window()
            with base.previous.count.old.cache.HeldFiles(tuple(root / name for name in code_paths()),
                    protected=False, boundary=guard.check) as final:
                require(_code(root, guard, complete_code_manifest, final) == identity, "body_receipt_proof_code_changed")
            _after_all_closes(target, directory_stamp, parent_stamp, file_rows, guard)
            pair.check_after_close(); volume.check(); window()
            _LAST_STAGE = "volume_context_exit"
        _LAST_STAGE = "terminal_original_audits"
        volume.check_after_close(); storage_summary = volume.closed_summary()
        with base.previous.count.old.cache.HeldFiles(tuple(root / name for name in code_paths()),
                protected=False, boundary=guard.check) as terminal:
            require(_code(root, guard, complete_code_manifest, terminal) == identity, "body_receipt_proof_code_changed")
        _after_all_closes(target, directory_stamp, parent_stamp, file_rows, guard)
        pair.check_after_close(); volume.check_after_close(); guard.refresh(); window()
    require(type(result) is dict, "body_receipt_proof_result_missing")
    closed_at = base.previous.prior._utc_now()
    require(base.previous.count.old.parallel.clock(closed_at) >= started_clock, "body_receipt_proof_deadline")
    result["closed_at"] = closed_at
    result["isolated_storage_closed_summary_sha256"] = hash_payload(storage_summary)
    window(); _LAST_STAGE = "closed"
    # A matching dictionary/hash is not an issued terminal proof. Keep the
    # ORIGINAL objects and original callback in this one finite invocation.
    def terminal_check():
        with base.previous.count.old.cache.HeldFiles(tuple(root / name for name in code_paths()),
                protected=False, boundary=guard.check) as verification:
            require(_code(root, guard, complete_code_manifest, verification) == identity,
                "body_receipt_proof_code_changed")
        _after_all_closes(target, directory_stamp, parent_stamp, file_rows, guard)
        pair.check_after_close(); volume.check_after_close(); guard.refresh(); window()
    raw_result = canonical_json(result).encode()
    window()
    require(_CLOSED_RECORD is None and _CLOSED_ORIGINAL is None, "body_receipt_proof_not_original_closed")
    _CLOSED_RECORD = _CLOSED_ORIGINAL = (result, raw_result, pair, volume, diagnostic, terminal_check, window, object())
    return result


def validate_closed_result(result):
    """Require this factory's one post-context result and ORIGINAL live pins."""
    global _CLOSED_FAILED
    try:
        record = _CLOSED_RECORD
        require(not _CLOSED_FAILED and type(record) is tuple and len(record) == 8
            and record is _CLOSED_ORIGINAL and type(record[7]) is object
            and result is record[0] and type(result) is dict
            and type(record[1]) is bytes and canonical_json(result).encode() == record[1],
            "body_receipt_proof_not_original_closed")
        require(hash_payload(record[2].closed_summary()) == result["helper_closed_summary_sha256"]
            and hash_payload(record[3].closed_summary()) == result["isolated_storage_closed_summary_sha256"]
            and record[4].report() == result["native_transition"], "body_receipt_proof_not_original_closed")
        record[5]()
        require(_CLOSED_RECORD is record is _CLOSED_ORIGINAL
            and canonical_json(result).encode() == record[1], "body_receipt_proof_not_original_closed")
        record[6]()
    except BaseException:
        _CLOSED_FAILED = True
        raise
    return True
