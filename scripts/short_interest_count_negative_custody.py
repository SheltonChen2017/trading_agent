"""Permanent negative-only quarantine of ORIGINAL already-received bytes.

Never starts/retries HTTP, reads a key/source, resets a failed guard, refunds a
START/page, or issues any qualified count capability. The original mount FD
and opaque observations stay strongly alive on every blocker. The owner of
the process MUST keep it alive while `requires_process_hold` is true; this
module intentionally offers no release/retry/adoption or success-lane cast.
Production registration is pending an explicit Main code/policy freeze.
"""
import _thread
import fcntl
import json
import os
from pathlib import Path
import stat
import sys
import time
from types import FunctionType

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_body_receipt_custody as primitive
from scripts import short_interest_count_durable_budget as accounting
from scripts import short_interest_count_durable_transport as transport
from scripts import short_interest_count_response_volume as storage
from scripts import short_interest_count_control_custody as controls
from scripts import short_interest_count_response_custody as responses

immutable, creator = primitive.immutable, primitive.creator
PRESERVATION_POLICY_SHA256 = "PENDING"
MAXIMUM_ATTEMPTS, MAXIMUM_LEASES = 528, 133
MAXIMUM_BODY_BYTES, MAXIMUM_METADATA_BYTES = 2097152, 1024
ROOT_NAME, PAIR_NAME, METADATA_NAME = "quarantine", "pair", "metadata"
RECEIPT_NAME = "unqualified.receipt.private.json"
CLOSURE_NAME = "closure"
_LEASES, _STATES, _STATE_PINS, _ROOTS, _STORED = {}, {}, {}, {}, {}
_SOURCES, _SOURCE_PINS, _FINAL_ISSUED, _FINAL_PINS, _FINAL_MINTS = {}, {}, {}, {}, {}
_AUTHORITY_PINS = {}
_FINAL_ATTEMPTED = set()
_USED_OPERATIONS, _ATTEMPTED, _CORRUPT, _BLOCKED, _HOLDS = set(), set(), set(), set(), {}
_CODES = frozenset("""negative_registration_pending negative_lease_factory_required negative_lease_changed
negative_lease_spent negative_lease_capacity negative_original_volume_changed negative_original_code_changed
negative_failed_operation_required negative_observation_required negative_ticket_changed
negative_attempt_spent negative_attempt_capacity negative_body_limit negative_wire_blocker_pending
negative_wire_partial_unproven negative_owned_directory_changed negative_membership_changed
negative_file_changed negative_metadata_bound negative_process_hold_required
negative_final_spent negative_final_not_drained negative_source_registry_changed
negative_source_member_changed negative_source_catalogue_changed negative_final_manifest_changed""".split())


class NegativePreservationRefusal(ValueError): pass


def require(value, code):
    if not value: raise NegativePreservationRefusal("REFUSED: " + code)


def failure_summary(error):
    if type(error) is not NegativePreservationRefusal:
        for module, name in ((storage, "CountResponseVolumeRefusal"), (transport, "CountTransportRefusal"),
                (accounting, "DurableCountBudgetRefusal")):
            if type(error) is getattr(module, name): return module.failure_summary(error)
        return primitive.failure_summary(error)
    args = BaseException.args.__get__(error, BaseException)
    code = (next((name for name in _CODES if args[0] == "REFUSED: " + name), None)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str else None)
    return {"category": "local_contract_refusal", "errno_name": None, "contract_code": code}


def authority():
    return {"negative_preservation_only": True, "qualification_reset_authority": False,
        "new_claim_authority": False, "new_START_authority": False, "HTTP_authority": False,
        "credential_authority": False, "retry_authority": False, "budget_release_authority": False,
        "source_admitted": False, "actual_input_execution_admitted": False,
        "ready_for_backtest": False, "outcome_looks": 0, "qc_attempts": 0}


def policy():
    return {"schema": "si-count-negative-custody-v1", "maximum_attempts": MAXIMUM_ATTEMPTS,
        "maximum_leases": MAXIMUM_LEASES, "maximum_body_bytes": MAXIMUM_BODY_BYTES,
        "maximum_metadata_bytes": MAXIMUM_METADATA_BYTES, "root": ROOT_NAME,
        "ordinal_width": 6, "pair_component": PAIR_NAME, "metadata_component": METADATA_NAME,
        "receipt_name": RECEIPT_NAME, "closure_component": CLOSURE_NAME,
        "body_primitive_policy_sha256": hash_payload(primitive.policy()),
        "small_primitive_policy_sha256": hash_payload(immutable.policy()),
        "native_volume_policy_sha256": hash_payload(storage.policy()),
        "operator_policy_sha256": hash_payload(transport.policy()),
        "accounting_policy_sha256": hash_payload(accounting.policy()),
        "control_policy_sha256": hash_payload(controls.policy()),
        "response_policy_sha256": hash_payload(responses.policy()),
        "final_manifest": "one_quarantine_closure_pair_max2MiB_all_reserved_full_pages_original_settlements_no_source_or_process_closure",
        "prior_settlements": "original_account7_retained_privately_compact_counts_sums_ordered_digests_and_original_closureSHA_only",
        "source_catalogue": "fixed_capture_subtree_external_claim_only_metadata_first_unknown_partial_never_read_or_adopted",
        "source_budget": "all_STARTs_and_full_2MiB_negative_charges_unchanged_no_settlement",
        "issuance": "LIVE_original_op_volume_before_claim_key_independent_dup_RO_mount_FD",
        "failure_validation": "FAILED_original_registries_inmemory_code_native_FD_pins_only_no_source_guard_reset",
        "publication": "fixed_fresh_quarantine_ordinal_once_no_clone_reseal_adoption_namespace_retry",
        "blocker": "strong_original_observation_bytes_and_mount_FD_process_must_stay_alive",
        "authority": authority()}


def _registered():
    require(all(type(value) is int for value in (MAXIMUM_ATTEMPTS, MAXIMUM_LEASES, MAXIMUM_BODY_BYTES, MAXIMUM_METADATA_BYTES))
        and (MAXIMUM_ATTEMPTS, MAXIMUM_LEASES, MAXIMUM_BODY_BYTES, MAXIMUM_METADATA_BYTES) == (528, 133, 2097152, 1024)
        and all(type(value) is str for value in (ROOT_NAME, PAIR_NAME, METADATA_NAME, RECEIPT_NAME, CLOSURE_NAME))
        and (ROOT_NAME, PAIR_NAME, METADATA_NAME, RECEIPT_NAME, CLOSURE_NAME)
            == ("quarantine", "pair", "metadata", "unqualified.receipt.private.json", "closure")
        and PRESERVATION_POLICY_SHA256 == hash_payload(policy()), "negative_registration_pending")


def _code_pins():
    """Original in-memory functions/defaults, never a post-failure disk read."""
    pins = []
    modules = (sys.modules[__name__], primitive, immutable, creator, primitive.cache, storage, transport, accounting,
        controls, responses)
    for module in modules:
        for name, value in tuple(vars(module).items()):
            owners = [(module, name, value)]
            if type(value) is type and value.__module__ == module.__name__:
                pins.append((module, name, value, "CLASS", None, tuple(vars(value).items())))
                owners.extend((value, key, item) for key, item in tuple(vars(value).items()))
            for owner, key, function in owners:
                if type(function) is property: function = function.fget
                elif type(function) in (staticmethod, classmethod): function = function.__func__
                if type(function) is FunctionType:
                    pins.append((owner, key, function, function.__code__, function.__defaults__,
                        None if function.__kwdefaults__ is None else tuple(function.__kwdefaults__.items())))
    for name, function in tuple(vars(primitive._OwnedOutput).items()):
        if type(function) is staticmethod: function = function.__func__
        if type(function) is FunctionType:
            pins.append((primitive._OwnedOutput, name, function, function.__code__, function.__defaults__,
                None if function.__kwdefaults__ is None else tuple(function.__kwdefaults__.items())))
    for owner, names in ((os, ("open", "close", "read", "write", "fstat", "stat", "mkdir", "fsync", "fchmod", "dup", "getuid", "getgid", "listdir", "lseek")),
            (fcntl, ("fcntl",)), (storage.ctypes, ("CDLL",))):
        for name in names: pins.append((owner, name, getattr(owner, name), None, None, None))
    for owner, names in ((storage, ("_StatFS64",)), (storage.ctypes, ("c_int", "c_uint", "c_void_p", "POINTER",
            "byref", "sizeof", "set_errno", "get_errno"))):
        for name in names: pins.append((owner, name, getattr(owner, name), None, None, None))
    return tuple(pins)


def _check_code(pins):
    for owner, name, function, code, defaults, keywords in pins:
        current = vars(owner).get(name)
        if type(code) is str and code == "CLASS":
            actual = tuple(vars(current).items()) if current is function else ()
            require(current is function and len(actual) == len(keywords)
                and all(key is old_key and value is old_value for (key, value), (old_key, old_value)
                    in zip(actual, keywords)), "negative_original_code_changed")
            continue
        if type(current) is property: current = current.fget
        elif type(current) in (staticmethod, classmethod): current = current.__func__
        current_keywords = None if code is None or function.__kwdefaults__ is None else tuple(function.__kwdefaults__.items())
        keyword_match = current_keywords is keywords if keywords is None else (
            type(current_keywords) is tuple and len(current_keywords) == len(keywords)
            and all(key is old_key and value is old_value for (key, value), (old_key, old_value)
                in zip(current_keywords, keywords)))
        require(current is function and (code is None or (function.__code__ is code
            and function.__defaults__ is defaults and keyword_match)), "negative_original_code_changed")


def _directory(info):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
        "negative_owned_directory_changed")
    return info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)


def _original_anchor(lease):
    require(_identity_class(OriginalPreservationLease), "negative_lease_changed")
    record = _LEASES.get(lease) if type(lease) is OriginalPreservationLease else None
    require(type(record) is tuple and len(record) == 11 and record[0] is lease, "negative_lease_changed")
    return record


def _identity_class(cls):
    return type(cls) is type and cls.__hash__ is object.__hash__ and cls.__eq__ is object.__eq__


def _lease_record(lease):
    record = _original_anchor(lease)
    require(lease._anchor is lease._identity is record and _STATES.get(lease) is _STATE_PINS.get(lease),
        "negative_lease_changed")
    return record


def _update_state(lease, state):
    require(_STATES.get(lease) is _STATE_PINS.get(lease), "negative_lease_changed")
    _STATES[lease] = _STATE_PINS[lease] = state


def _check_lease(lease):
    anchor = _lease_record(lease)
    try:
        require(lease not in _CORRUPT, "negative_lease_changed")
        checker = next(pin for pin in anchor[6] if pin[0] is sys.modules[__name__] and pin[1] == "_check_code")
        require(checker[2].__code__ is checker[3], "negative_original_code_changed")
        checker[2](anchor[6]); require(hash_payload(policy()) == anchor[7], "negative_original_code_changed")
        origin, fd = anchor[4], anchor[5]
        require(anchor[1]._anchor is anchor[1]._identity is anchor[2]
            and anchor[3]._anchor is anchor[3]._identity is origin[8], "negative_original_volume_changed")
        require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY, "negative_original_volume_changed")
        for info in (os.fstat(fd), origin[2].lstat()):
            require(_directory(info) == origin[4] and (info.st_dev, info.st_ino, info.st_uid, info.st_gid) == origin[5],
                "negative_original_volume_changed")
        native = storage._native_statfs(fd)
        require(storage._mount_identity(native) == origin[6] and storage._node_pin(origin[6][-1], origin[4][0]) == origin[7],
            "negative_original_volume_changed")
        for path, pin in _ROOTS.get(lease, (None, None, ()))[2]:
            require(_directory(path.lstat()) == pin, "negative_owned_directory_changed")
        return anchor
    except BaseException:
        _CORRUPT.add(lease); raise


class OriginalPreservationLease:
    __slots__ = ("_anchor", "_identity")
    def __init__(self): raise NegativePreservationRefusal("REFUSED: negative_lease_factory_required")
    def __repr__(self): return "<OriginalPreservationLease negative-only; private bytes retained>"


def _prepare_original_preservation_lease(operation, volume, *, monotonic, sleep):
    _registered()
    require(type(getattr(transport, "unqualified_preservation_blocker", None)) is FunctionType,
        "negative_wire_blocker_pending")
    op = transport.active_operation_binding(operation)
    require(type(volume) is storage.CountResponseVolume and operation not in _USED_OPERATIONS,
        "negative_lease_spent")
    require(len(_LEASES) < MAXIMUM_LEASES, "negative_lease_capacity")
    with op[11]:
        origin = storage.preservation_volume_origin(volume, operation)
        require(type(origin) is tuple and len(origin) == 10 and origin[0] is volume and origin[1] is operation
            and type(origin[9]) is object, "negative_original_volume_changed")
        _USED_OPERATIONS.add(operation)
        fd = os.dup(origin[3])
        try:
            lease = object.__new__(OriginalPreservationLease)
            anchor = lease, operation, op, volume, origin, fd, _code_pins(), hash_payload(policy()), monotonic, sleep, _thread.RLock()
            lease._anchor = lease._identity = anchor; _LEASES[lease] = anchor
            _AUTHORITY_PINS[lease] = tuple(authority().items())
            _STATES[lease] = _STATE_PINS[lease] = (), (), ()  # original observations, durable records, blockers
            # This original dictionary is populated by Main's OWN directory
            # factory later. No failed SourceLease/Git callback is needed.
            from scripts import capture_short_interest_durable_counts as coordinator
            source = (anchor, coordinator, coordinator._DIRECTORIES, accounting._BUDGETS,
                accounting._TICKETS, controls._CAPS, controls._ISSUED, controls._CHOICES,
                responses._PAIRS, responses._PAIR_ISSUED, responses._FILE_ISSUED,
                responses._CHOICES, responses._BINDINGS, operation._anchor[1]._anchor)
            _SOURCES[lease] = _SOURCE_PINS[lease] = source
            require(storage.preservation_volume_origin(volume, operation) is origin, "negative_original_volume_changed")
            _check_lease(lease)
            return lease
        except BaseException:
            # No claims/keys/observations exist at this LIVE setup boundary.
            # Every returned lease instead retains its original FD permanently.
            os.close(fd); raise


def prepare_original_preservation_lease(operation, volume):
    return _prepare_original_preservation_lease(operation, volume, monotonic=time.monotonic, sleep=time.sleep)


def _failed_observation(lease, observation):
    anchor = _lease_record(lease); operation, op = anchor[1:3]
    record = transport._OPERATIONS.get(operation)
    require(type(record) is tuple and len(record) == 2 and record[0] is op
        and operation._anchor is operation._identity is op and operation in transport._FAILED,
        "negative_failed_operation_required")
    observed = transport.drained_http_observation_binding(observation)
    require(type(observed) is tuple and len(observed) == 16 and observed[1] is operation,
        "negative_observation_required")
    ticket = observed[2]; original = accounting._TICKETS.get(ticket) if type(ticket) is accounting.CountAttemptTicket else None
    require(type(original) is tuple and len(original) == 14 and original[0] is ticket
        and ticket._anchor is ticket._identity is original and original[1] is op[1] and original[2] is op[2]
        and original[3] == op[4] and original[12] is op[3] and original[11] == MAXIMUM_BODY_BYTES
        and type(original[4]) is int and 1 <= original[4] <= 70013
        and any(item is ticket for item in record[1][1]) and observed[5] == original[8], "negative_ticket_changed")
    return observed, original


def _new_directory(lease, parent_fd, parent, name):
    anchor = _check_lease(lease)
    expected = anchor[4][4] if parent == anchor[4][2] else dict(_ROOTS.get(lease, (None, None, ()))[2]).get(parent)
    require(expected is not None and fcntl.fcntl(parent_fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
        and _directory(os.fstat(parent_fd)) == _directory(parent.lstat()) == expected,
        "negative_owned_directory_changed")
    os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        os.fchmod(fd, 0o700); pin = _directory(os.fstat(fd)); path = parent / name
        require(_directory(path.lstat()) == pin and _directory(os.fstat(parent_fd)) == expected,
            "negative_owned_directory_changed")
        return fd, path, pin
    except BaseException: os.close(fd); raise


def _publication_directory(lease, ordinal, has_body):
    anchor = _check_lease(lease); mount = anchor[4][2]
    if lease not in _ROOTS:
        fd, path, pin = _new_directory(lease, anchor[5], mount, ROOT_NAME)
        _ROOTS[lease] = fd, path, ((path, pin),)
    qfd, root, pins = _ROOTS[lease]
    parent_fd, parent, pin = _new_directory(lease, qfd, root, f"{ordinal:06d}")
    _ROOTS[lease] = qfd, root, (*pins, (parent, pin))
    try:
        fd, path, child_pin = _new_directory(lease, parent_fd, parent, PAIR_NAME if has_body else METADATA_NAME)
        os.close(fd)
        _ROOTS[lease] = qfd, root, (*pins, (parent, pin), (path, child_pin))
        return path
    finally: os.close(parent_fd)


def _no_body_receipt(observed, original):
    raw = observed[10]
    encoded = canonical_json({"schema": "si-negative-count-receipt-v1", "observation_sha256": observed[14],
        "request_sha256": observed[5], "START_sha256": observed[6], "reservation_sha256": original[9],
        "operator_protocol_sha256": observed[7], "ordinal": original[4], "http_status": observed[9],
        "body_state": "unobserved" if raw is None else "observed_empty", "negative_full_page_charge_unchanged": MAXIMUM_BODY_BYTES,
        "source_admitted": False, "budget_release_authority": False}).encode()
    require(0 < len(encoded) <= MAXIMUM_METADATA_BYTES, "negative_metadata_bound")
    return encoded


def _audit_files(lease, files):
    _check_lease(lease)
    for path, expected, raw in files:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            require(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
                and immutable._stamp(os.fstat(fd)) == immutable._stamp(path.lstat()) == expected,
                "negative_file_changed")
            # The original SMALL metadata reader is permanently capped1024.
            # This fixed private-file reader separately audits up to2MiB.
            require(type(raw) is bytes and 0 < len(raw) <= MAXIMUM_BODY_BYTES, "negative_file_changed")
            os.lseek(fd, 0, os.SEEK_SET); offset = 0
            while offset < len(raw):
                require(immutable._stamp(os.fstat(fd)) == immutable._stamp(path.lstat()) == expected,
                    "negative_file_changed")
                part = os.read(fd, min(65536, len(raw) - offset))
                require(type(part) is bytes and bool(part) and part == raw[offset:offset + len(part)], "negative_file_changed")
                offset += len(part)
            require(offset == len(raw) and os.read(fd, 1) == b"", "negative_file_changed")
            require(immutable._stamp(os.fstat(fd)) == immutable._stamp(path.lstat()) == expected,
                "negative_file_changed")
        finally: os.close(fd)
        require(immutable._stamp(path.lstat()) == expected, "negative_file_changed")
    require(tuple(sorted(os.listdir(files[0][0].parent))) == tuple(sorted(path.name for path, unused, raw in files)),
        "negative_membership_changed")
    _check_lease(lease)


def preserve_failed_observation(lease, observation):
    """One quarantine attempt. Every failure returns a non-exiting blocker.

    The caller MUST inspect requires_process_hold. The global strong hold is
    deliberate; neither raw/opaque references nor the lease FD are released.
    """
    anchor = _original_anchor(lease)
    with anchor[10]:
        retained = _HOLDS.get(lease, ())
        opaque = transport._DRAINED.get(observation) if type(observation) is transport.UnqualifiedHttpObservation else None
        if type(opaque) is tuple and len(opaque) == 16 and opaque[0] is observation and opaque[1] is anchor[1]:
            if not any(item is observation for item in retained) and len(retained) < MAXIMUM_ATTEMPTS:
                _HOLDS[lease] = (*retained, observation)
        try:
            _check_lease(lease)  # Authenticate frozen functions BEFORE invoking any negative issuer callback.
            observed, original = _failed_observation(lease, observation)
            key = lease, original[0]
            require(key not in _ATTEMPTED, "negative_attempt_spent")
            require(sum(item[0] is lease for item in _ATTEMPTED) < MAXIMUM_ATTEMPTS, "negative_attempt_capacity")
            _ATTEMPTED.add(key)
            blocker = getattr(transport, "unqualified_preservation_blocker", None)
            require(type(blocker) is FunctionType, "negative_wire_blocker_pending")
            require(blocker(observation) is None, "negative_wire_partial_unproven")
            _check_lease(lease); raw = observed[10]
            require(raw is None or (type(raw) is bytes and len(raw) <= MAXIMUM_BODY_BYTES), "negative_body_limit")
            path = _publication_directory(lease, original[4], bool(raw)); files = []
            with primitive._OwnedOutput(path, lambda: _check_lease(lease)) as owned:
                if raw:
                    binding = primitive.freeze_body_receipt_binding(request_sha256=observed[5], attempt_sha256=observed[14],
                        reservation_sha256=original[9], protocol_sha256=anchor[7])
                    with primitive.prepare_owned_body_receipt(owned, raw, binding=binding, boundary=lambda: _check_lease(lease),
                            monotonic=anchor[8], sleep=anchor[9]) as cap: cap.check()
                    cap.closed_summary()
                    for file_cap in cap._anchor[3]:
                        origin = primitive._file_anchor(file_cap)
                        files.append((path / origin[3], primitive._CHOICES[file_cap], origin[4]))
                else:
                    metadata = _no_body_receipt(observed, original)
                    with immutable.prepare_owned_immutable_metadata(owned, RECEIPT_NAME, metadata, parent=False,
                            boundary=lambda: _check_lease(lease), monotonic=anchor[8], sleep=anchor[9]) as cap:
                        cap.seal_once(); cap.check()
                    issued = immutable._ISSUED[id(cap)]
                    require(issued[0] is cap and issued[1] is cap._anchor, "negative_file_changed")
                    files.append((path / RECEIPT_NAME, issued[3], metadata))
            _audit_files(lease, tuple(files))
            record = observation, original[0], cap, tuple(files)
            _STORED[key] = record
            old = _STATES[lease]; _update_state(lease, (_HOLDS.get(lease, ()), (*old[1], record), old[2]))
            return preservation_binding(lease)
        except BaseException as error:
            _BLOCKED.add(lease)
            old = _STATE_PINS[lease]
            failure = failure_summary(error)
            blockers = old[2] if failure in old[2] else (*old[2], failure)
            _STATES[lease] = _STATE_PINS[lease] = _HOLDS.get(lease, ()), old[1], blockers
            return _report(lease)


def preservation_binding(lease):
    anchor = _original_anchor(lease)
    with anchor[10]:
        try:
            _check_lease(lease)
            for record in _STATES[lease][1]: _audit_files(lease, record[3])
            if lease in _FINAL_ISSUED: _audit_final(lease)
        except BaseException as error:
            _BLOCKED.add(lease); old = _STATE_PINS[lease]
            failure = failure_summary(error)
            blockers = old[2] if failure in old[2] else (*old[2], failure)
            _STATES[lease] = _STATE_PINS[lease] = old[0], old[1], blockers
        return _report(lease)


def _source_record(lease):
    anchor = _check_lease(lease); source = _SOURCES.get(lease)
    require(type(source) is tuple and len(source) == 14 and source is _SOURCE_PINS.get(lease)
        and source[0] is anchor and source[2] is source[1]._DIRECTORIES
        and source[3] is accounting._BUDGETS and source[4] is accounting._TICKETS
        and source[5] is controls._CAPS and source[6] is controls._ISSUED and source[7] is controls._CHOICES
        and source[8] is responses._PAIRS and source[9] is responses._PAIR_ISSUED
        and source[10] is responses._FILE_ISSUED and source[11] is responses._CHOICES
        and source[12] is responses._BINDINGS, "negative_source_registry_changed")
    operation, op = anchor[1:3]; current = transport._OPERATIONS.get(operation)
    require(type(current) is tuple and len(current) == 2 and current[0] is op
        and operation._anchor is operation._identity is op and operation in transport._FAILED
        and type(current[1]) is tuple and len(current[1]) == 6, "negative_failed_operation_required")
    return anchor, source, current[1]


def _negative_accounting(lease):
    anchor, source, state = _source_record(lease); op = anchor[2]; budget = op[1]
    # This pure original journal survives FAILED and expired chunk readers.
    with source[13][4]:
        settled = accounting.settled_chunk_accounting(budget)
        original = source[3].get(budget)
        require(type(original) is tuple and len(original) == 3 and original[0] is budget
            and original[1] is source[13] is budget._anchor is budget._identity
            and original[2] is budget._state and settled[0] is budget and settled[1] is op[3]
            and settled[2] is op[2], "negative_source_registry_changed")
        budget_state = original[2]; tickets = budget_state[2]
        require(type(tickets) is tuple and len(tickets) <= MAXIMUM_ATTEMPTS
            and type(budget_state[0]) is int and budget_state[0] == op[4], "negative_ticket_changed")
        parts = []
        for ticket in tickets:
            value = source[4].get(ticket) if type(ticket) is accounting.CountAttemptTicket else None
            require(type(value) is tuple and len(value) == 14 and value[0] is ticket
                and ticket._anchor is ticket._identity is value and value[1] is budget
                and value[2] is op[2] and value[3] == op[4] and value[12] is op[3]
                and type(value[4]) is int and 1 <= value[4] <= 70013
                and value[11] == MAXIMUM_BODY_BYTES, "negative_ticket_changed")
            parts.append(value)
        require(len({value[4] for value in parts}) == len(parts), "negative_ticket_changed")
        return settled, budget_state, tuple(parts)


def _catalogue(parts):
    """Build the finite admissible set BEFORE examining any source file."""
    files = {"claim/claim.spent.json"}
    for role, name in (("inventory", "inventory.private.json"), ("provisional", "provisional.json"),
            ("closed", "closed.json"), ("manifest", "manifest.private.json")):
        files.add("capture/final_" + role + "/" + name)
    for value in parts:
        ordinal = format(value[4], "06d")
        files.update((f"capture/starts/{ordinal}/START.spent.json",
            f"capture/received/{ordinal}/received.private.json",
            f"capture/responses/{ordinal}/response.raw",
            f"capture/responses/{ordinal}/response.receipt.private.json"))
    directories = {"capture", "claim"}
    for name in files:
        parent = Path(name).parent
        while parent != Path("."):
            directories.add(parent.as_posix()); parent = parent.parent
    return tuple(sorted(files)), frozenset(directories)


def _scan_source(lease, parts):
    anchor, source, unused = _source_record(lease); mount = anchor[4][2]
    files, directories = _catalogue(parts); allowed = frozenset(files)
    original_pins = source[2].get(anchor[1], ())
    require(type(original_pins) is tuple, "negative_source_registry_changed")
    pins = {}
    for row in original_pins:
        require(type(row) is tuple and len(row) == 2 and type(row[0]) is type(mount), "negative_source_registry_changed")
        relative = row[0].relative_to(mount).as_posix()
        require(relative in directories and relative not in pins, "negative_source_catalogue_changed")
        pins[relative] = row[1]
    found_files, found_dirs = {}, {}
    def walk(parent_fd, name, relative):
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        require(relative in directories, "negative_source_catalogue_changed")
        pin = _directory(info)
        require(relative not in pins or pin == pins[relative], "negative_source_member_changed")
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            require(_directory(os.fstat(fd)) == pin, "negative_source_member_changed")
            names = tuple(sorted(os.listdir(fd)))
            found_dirs[relative] = pin, "ORIGINAL_DIRECTORY_PIN" if relative in pins else "UNKNOWN_PARTIAL_DIRECTORY"
            for child in names:
                rel = relative + "/" + child
                # No raw read occurs in this pass, including known filenames.
                require(rel in allowed or rel in directories, "negative_source_catalogue_changed")
                item = os.stat(child, dir_fd=fd, follow_symlinks=False)
                if rel in directories:
                    walk(fd, child, rel)
                else:
                    require(stat.S_ISREG(item.st_mode) and item.st_uid == os.getuid()
                        and stat.S_IMODE(item.st_mode) == 0o600 and item.st_nlink == 1,
                        "negative_source_member_changed")
                    found_files[rel] = immutable._stamp(item)
            require(tuple(sorted(os.listdir(fd))) == names and _directory(os.fstat(fd)) == pin
                and _directory(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)) == pin,
                "negative_source_member_changed")
        finally: os.close(fd)
    for name in ("capture", "claim"):
        try: os.stat(name, dir_fd=anchor[5], follow_symlinks=False)
        except FileNotFoundError: continue
        walk(anchor[5], name, name)
    return files, tuple(sorted(found_files.items())), tuple(sorted(found_dirs.items()))


def _closed_source_files(lease, parts):
    """Only original CLOSED issuer records, never failed public callbacks."""
    anchor, source, unused = _source_record(lease); operation = anchor[1]; mount = anchor[4][2]
    catalogue = frozenset(_catalogue(parts)[0]); known = {}
    def add(origin, seal):
        require(type(origin) is tuple and len(origin) == 15 and type(seal) is tuple and len(seal) == 9
            and origin[0]._anchor is origin[1] and type(origin[4]) is bytes
            and 0 < len(origin[4]) <= MAXIMUM_BODY_BYTES and hash_bytes(origin[4]) == origin[5]
            and all(type(value) is int for value in seal) and seal[:5] == origin[8][:5]
            and seal[2:6] == (os.getuid(), 0o600, 1, len(origin[4]))
            and seal[8] == origin[10] and seal[8] in (2, 66),
            "negative_source_member_changed")
        path = origin[1][0] / origin[3]; relative = path.relative_to(mount).as_posix()
        require(relative in catalogue and relative not in known, "negative_source_catalogue_changed")
        known[relative] = path, seal, origin[4]
    for cap, original in tuple(source[5].items()):
        if type(original) is not tuple or len(original) != 9 or original[1] is not operation: continue
        require(type(cap) in (controls.CountClaim, controls.CountStart, controls.CountReceived, controls.CountFinalControl)
            and cap._anchor is cap._identity is original[0], "negative_source_registry_changed")
        if source[6].get(cap) is original:
            add(original[0], source[7].get(cap))
    for cap, saved in tuple(source[8].items()):
        if type(saved) is not tuple or len(saved) != 2: continue
        origin = saved[0]
        if type(origin) is not tuple or len(origin) != 8: continue
        binding = source[12].get(origin[2])
        if type(binding) is not tuple or len(binding) != 9 or binding[3] is not anchor[2]: continue
        require(type(cap) is responses.CountResponseCustody and cap._anchor is cap._identity is origin
            and origin[2]._parts is origin[2]._identity is binding, "negative_source_registry_changed")
        issued = source[9].get(cap)
        if issued is None: continue
        require(type(issued) is tuple and issued[0] is origin and type(origin[3]) is tuple and len(origin[3]) == 2,
            "negative_source_registry_changed")
        for file_cap in origin[3]:
            file_issued = source[10].get(file_cap)
            require(type(file_cap) is responses.CountResponseFileCustody and type(file_issued) is tuple
                and len(file_issued) == 2 and file_issued[0] is file_cap._anchor is file_cap._identity
                and file_issued[1] is source[11].get(file_cap), "negative_source_registry_changed")
            add(file_issued[0], file_issued[1])
    return known


def _source_snapshot(lease, parts):
    before = _scan_source(lease, parts); known = _closed_source_files(lease, parts)
    observed = dict(before[1]); rows = []
    for relative in before[0]:
        if relative in known:
            path, seal, raw = known[relative]
            require(observed.get(relative) == seal, "negative_source_member_changed")
            # The catalogue pass completed before ANY file bytes are read.
            siblings = tuple(value for name, value in known.items() if value[0].parent == path.parent)
            _audit_files(lease, siblings)
            rows.append({"name": relative, "state": "ORIGINAL_CLOSED_SEAL_AUDITED",
                "bytes": len(raw), "sha256": hash_bytes(raw)})
        elif relative in observed:
            rows.append({"name": relative, "state": "UNKNOWN_UNSEALED_OR_PARTIAL",
                "observed_bytes": observed[relative][5], "charge_release_authority": False})
        else: rows.append({"name": relative, "state": "ABSENT_NOT_A_START_REFUND"})
    require(_scan_source(lease, parts) == before, "negative_source_member_changed")
    return before, tuple(rows)


def _final_directory(lease):
    anchor = _check_lease(lease)
    if lease not in _ROOTS:
        fd, path, pin = _new_directory(lease, anchor[5], anchor[4][2], ROOT_NAME)
        _ROOTS[lease] = fd, path, ((path, pin),)
    qfd, root, pins = _ROOTS[lease]
    fd, path, pin = _new_directory(lease, qfd, root, CLOSURE_NAME)
    _ROOTS[lease] = qfd, root, (*pins, (path, pin))
    os.close(fd); return path


def _quarantine_membership(lease):
    if lease not in _ROOTS: return
    unused_fd, root, pins = _ROOTS[lease]; paths = {path for path, unused in pins}
    for path in paths:
        expected_dirs = {child.name for child in paths if child.parent == path}
        expected_files = set()
        for record in _STATES[lease][1]:
            expected_files.update(item[0].name for item in record[3] if item[0].parent == path)
        if path == root / CLOSURE_NAME and lease in _FINAL_ISSUED:
            expected_files.update(item[0].name for item in _FINAL_ISSUED[lease][6])
        require(set(os.listdir(path)) == expected_dirs | expected_files, "negative_membership_changed")


def _audit_final(lease):
    anchor = _check_lease(lease); issued = _FINAL_ISSUED.get(lease)
    require(type(issued) is tuple and len(issued) == 8 and issued is _FINAL_PINS.get(lease)
        and issued[0] is anchor and lease in _FINAL_ATTEMPTED, "negative_final_manifest_changed")
    require(type(issued[7]) is object and _FINAL_MINTS.get(issued[7]) is issued,
        "negative_final_manifest_changed")
    pair = issued[4]; pair_origin = primitive._PAIRS.get(pair)
    pair_issue = primitive._PAIR_ISSUED.get(pair)
    require(type(pair) is primitive.BodyReceiptCustody and type(pair_origin) is tuple
        and type(pair_issue) is tuple and pair_issue[0] is pair_origin[0]
        is pair._anchor is pair._identity and pair._anchor[3][0]._anchor[4] is issued[5],
        "negative_final_manifest_changed")
    settled, state, parts = _negative_accounting(lease)
    require(settled is issued[1] and state is issued[2] and _source_snapshot(lease, parts) == issued[3],
        "negative_final_manifest_changed")
    _audit_files(lease, issued[6]); _quarantine_membership(lease)


def _settlement_rows(settled):
    """Bounded private projection; these hashes can grant no accounting.

    The full ORIGINAL account7 tuple remains in the issued marker's private
    witness. Re-authentication must reconstruct the original per-chunk roots;
    this compact JSON is never a replacement witness or a release grant.
    """
    return [{"chunk": account[2], "START_reservations": len(account[3]),
        "charged_bytes": sum(account[4]), "terminal_transport_covered_count": len(account[5]),
        "ordered_reservation_roster_sha256": hash_payload(tuple(accounting._TICKETS[ticket][9] for ticket in account[3])),
        "ordered_charges_sha256": hash_payload(account[4]), "covered_positions_sha256": hash_payload(account[5]),
        "original_closure_sha256": account[6]} for account in settled[3]]


def finalize_failed_chunk(lease):
    """Seal ONE dominating negative manifest; this closes no source/process.

    A not-yet-drained wire roster is a transient hold, not a spent namespace.
    Every publication/contract failure is permanent and retains original RAM
    and independent FDs. Only the original issued fact permits exit2.
    """
    anchor = _original_anchor(lease)
    with anchor[10], anchor[2][11]:
        try:
            _check_lease(lease); unused, unused_source, operation_state = _source_record(lease)
            if _report(lease)["pending_already_started_attempts"] or operation_state[2]: return _report(lease)
            require(lease not in _BLOCKED, "negative_process_hold_required")
            require(lease not in _FINAL_ATTEMPTED, "negative_final_spent")
            _FINAL_ATTEMPTED.add(lease)
            settled, state, parts = _negative_accounting(lease)
            source_snapshot = _source_snapshot(lease, parts)
            for record in _STATES[lease][1]: _audit_files(lease, record[3])
            _quarantine_membership(lease)
            op = anchor[2]
            journal = _settlement_rows(settled)
            payload = {"schema": "si-failed-count-chunk-preservation-manifest-v1",
                "status": "preservation_manifest_sealed_only", "source_contexts_closed": False,
                "process_closed": False, "chunk": op[4], "operator_protocol_sha256": op[5],
                "registration_sha256": op[6], "runtime_HEAD": op[8], "matching_remote": op[9],
                "plan_sha256": op[10], "preservation_policy_sha256": anchor[7],
                "historical_START_debits": accounting.research_budget.PRIOR_STARTS,
                "historical_charged_bytes": accounting.research_budget.PRIOR_CHARGED_BYTES,
                "original_irreversible_settlements": journal,
                "all_current_reserved_tickets": [{"ordinal": value[4], "position": value[5],
                    "lifetime_try": value[7], "request_sha256": value[8], "reservation_sha256": value[9],
                    "negative_full_page_charge_unchanged": MAXIMUM_BODY_BYTES} for value in parts],
                "current_full_page_reservations": len(parts) * MAXIMUM_BODY_BYTES,
                "source_members": list(source_snapshot[1]),
                "negative_observation_sha256s": [transport._DRAINED[record[0]][14] for record in _STATES[lease][1]],
                "positive_intent_has_no_authority": True, "authority": authority()}
            raw = canonical_json(payload).encode()
            require(0 < len(raw) <= MAXIMUM_BODY_BYTES, "negative_metadata_bound")
            path = _final_directory(lease)
            binding = primitive.freeze_body_receipt_binding(request_sha256=hash_payload({"negative_chunk": op[4], "plan": op[10]}),
                attempt_sha256=hash_payload(payload), reservation_sha256=hash_payload({"full_page_bytes": len(parts) * MAXIMUM_BODY_BYTES}),
                protocol_sha256=anchor[7])
            with primitive._OwnedOutput(path, lambda: _check_lease(lease)) as owned:
                with primitive.prepare_owned_body_receipt(owned, raw, binding=binding, boundary=lambda: _check_lease(lease),
                        monotonic=anchor[8], sleep=anchor[9]) as cap: cap.check()
                cap.closed_summary()
                files = tuple((path / primitive._file_anchor(file_cap)[3], primitive._CHOICES[file_cap],
                    primitive._file_anchor(file_cap)[4]) for file_cap in cap._anchor[3])
            _audit_files(lease, files)
            final_account = _negative_accounting(lease)
            require(final_account[0] is settled and final_account[1] is state
                and _source_snapshot(lease, parts) == source_snapshot, "negative_final_manifest_changed")
            # Independent original issued identity, never a caller completion
            # flag/raw payload or a mutable lease phase.
            issued = anchor, settled, state, source_snapshot, cap, raw, files, object()
            _FINAL_ISSUED[lease] = _FINAL_PINS[lease] = issued
            _FINAL_MINTS[issued[7]] = issued
            _audit_final(lease)
            return _report(lease)
        except BaseException as error:
            _BLOCKED.add(lease); old = _STATE_PINS[lease]; failure = failure_summary(error)
            blockers = old[2] if failure in old[2] else (*old[2], failure)
            _STATES[lease] = _STATE_PINS[lease] = old[0], old[1], blockers
            return _report(lease)


def _report(lease):
    state = _STATE_PINS[lease]; blocked = lease in _BLOCKED
    anchor = _original_anchor(lease)
    operation_identity = _identity_class(transport.CountCaptureOperation)
    operation = transport._OPERATIONS.get(anchor[1]) if operation_identity else None
    good_operation = (type(operation) is tuple and len(operation) == 2 and operation[0] is anchor[2]
        and type(operation[1]) is tuple and len(operation[1]) == 6 and type(operation[1][1]) is tuple)
    # Inflight bookkeeping can drain before its final observation is appended.
    # The ORIGINAL accepted-dispatch roster never removes that ticket, so it
    # remains pending until its exact negative bytes/metadata are persisted.
    dispatched = operation[1][1] if good_operation else ()
    stored_tickets = tuple(record[1] for record in state[1])
    pending = sum(not any(ticket is stored for stored in stored_tickets) for ticket in dispatched)
    if not good_operation:
        _BLOCKED.add(lease); blocked = True
    original_fstat = next(function for owner, name, function, unused_code, unused_defaults, unused_kw in anchor[6]
        if owner is os and name == "fstat")
    try:
        info = original_fstat(anchor[5])
        fd_open = (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)) == anchor[4][4]
    except OSError: fd_open = False
    final = lease in _FINAL_ISSUED and _FINAL_ISSUED.get(lease) is _FINAL_PINS.get(lease) and not blocked
    return {"schema": "si-negative-preservation-observation-v1",
        "status": "blocked_private_bytes_and_FDs_must_remain_alive" if blocked else
            "negative_quarantine_incomplete_process_must_remain_alive" if pending or not final else "preservation_manifest_sealed_only",
        "requires_process_hold": blocked or bool(pending) or not final, "pending_already_started_attempts": pending,
        "final_negative_manifest_issued": final,
        "retained_opaque_observations": len(_HOLDS.get(lease, ())),
        "originally_closed_negative_attempts": len(state[1]), "verified_durable_negative_attempts": 0 if blocked else len(state[1]),
        "blockers": [dict(item) for item in state[2]],
        "original_mount_FD_retained": fd_open, "original_operation_failed": operation_identity and anchor[1] in transport._FAILED,
        # Even a detected authority-function substitution cannot make a
        # BLOCKED public report echo changed authority flags.
        "budget_changes_performed": False, "authority": dict(_AUTHORITY_PINS[lease])}
