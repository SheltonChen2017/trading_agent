"""Finite sys.monitoring observations of unchanged ORIGINAL metadata code.

This diagnostic owns only tool 4, its global mask, exact original target-local
masks and fixed known callback slots. Unknown-code local masks cannot be
enumerated by this API and are neither adopted nor changed. No setter, check,
writer, source, flag or original custody deadline is replaced.
"""
from contextlib import AbstractContextManager
import json
import fcntl
import os
import stat
import sys
import threading
import types

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_immutable_transition_diagnostics as previous
from scripts import short_interest_body_receipt_custody as body_custody

immutable = previous.immutable
BODY_NAME, RECEIPT_NAME = "attempt-body.raw", "attempt-receipt.private.json"
ROLES = ("body", "receipt")
MAXIMUM_REFUSALS, MAXIMUM_EVENTS = 16, 32768
TOOL_ID, TOOL_NAME = 4, "si-offline-body-receipt-v1"
BACKEND = "sys.monitoring_local_original_code_events"
SCOPE = "global_exact_target_local_known_callback_slots_and_tool4_ownership_only"
_NATIVE, _NATIVE_CODE = previous._NATIVE, previous._NATIVE_CODE
_FACTORY_CODE = previous._code(body_custody._prepare_original_file)
_MONITOR = sys.monitoring
_API_NAMES = ("get_tool", "use_tool_id", "free_tool_id", "get_events", "set_events",
    "get_local_events", "set_local_events", "register_callback")
_API = tuple(getattr(_MONITOR, name) for name in _API_NAMES)
_LOCAL_NAMES = ("PY_START", "PY_RESUME", "PY_RETURN", "PY_YIELD")
_EXCEPTION_NAMES = ("RAISE", "RERAISE", "PY_UNWIND", "PY_THROW")
_ALL_NAMES = ("PY_START", "PY_RESUME", "PY_RETURN", "PY_YIELD", "CALL", "LINE",
    "INSTRUCTION", "JUMP", "BRANCH", "STOP_ITERATION", "C_RAISE", "C_RETURN",
    "PY_THROW", "PY_UNWIND", "RAISE", "RERAISE", "EXCEPTION_HANDLED")
_EVENTS = tuple((name, getattr(_MONITOR.events, name)) for name in _ALL_NAMES)
_LOCAL_MASK = sum(dict(_EVENTS)[name] for name in _LOCAL_NAMES)
_GLOBAL_MASK = sum(dict(_EVENTS)[name] for name in _EXCEPTION_NAMES)
_MINTED, _FAILED, _ISSUED, _COUNTS, _ROLE_COUNTS, _FILE_ORIGINS = {}, {}, {}, {}, {}, {}
_CODES = frozenset("""body_monitor_factory_required body_monitor_arguments_refused body_monitor_binding_changed
body_monitor_monitor_busy body_monitor_monitor_changed body_monitor_monitor_cleanup_failed body_monitor_trace_occupied
body_monitor_original_code_changed body_monitor_already_entered body_monitor_not_closed body_monitor_wrong_thread
body_monitor_observer_error body_monitor_observer_overflow body_monitor_multiple_native_calls
body_monitor_original_factory_changed body_monitor_missing_native_observation body_monitor_frame_changed
body_monitor_before_native_changed""".split())


class BodyReceiptMonitorRefusal(ValueError):
    pass


def require(value, code):
    if not value:
        raise BodyReceiptMonitorRefusal("REFUSED: " + code)


def authority():
    return {**previous.authority(), "synthetic_body_receipt_diagnostic_only": True,
        "body_receipt_store_admitted": False, "source_budget_released": False}


def policy():
    return {"schema": "si-body-receipt-immutable-monitoring-policy-v1",
        "fixed_roles": list(ROLES), "fixed_names": [BODY_NAME, RECEIPT_NAME],
        "backend": BACKEND, "tool_id": TOOL_ID, "tool_name": TOOL_NAME,
        "local_events": list(_LOCAL_NAMES), "global_filtered_events": list(_EXCEPTION_NAMES),
        "callback_slots": list(_ALL_NAMES), "resource_scope": SCOPE,
        "unknown_code_local_masks": "unobservable_and_untouched_not_universally_empty",
        "foreign_ownership": "permanent_refusal_leave_foreign_resources_unchanged",
        "ownership_observation": "check_before_each_cleanup_mutation_no_atomic_compare_and_swap_claim",
        "unexpected_callback": "restore_exact_displaced_replacement_refuse_and_hold_failed_lease",
        "original_native_and_checks_replaced": False, "global_trace_installed": False,
        "original_trace_required": "None_and_never_changed_by_this_diagnostic",
        "callback_checks": "original_nonce_state_thread_immutable_phase_map_and_owned_resource_masks_every_selected_event",
        "code_audits": "fresh_complete_catalogue_and_native_function_at_entry_and_terminal_exact_code_frame_on_selected_events",
        "unmatched_normal_functions": "not_observed_no_global_trace_equivalence_claim",
        "maximum_native_calls": 2, "exact_native_calls_per_role": 1,
        "maximum_controlled_refusals": MAXIMUM_REFUSALS,
        "maximum_meaningful_events": MAXIMUM_EVENTS,
        "actual_lengths_and_hashes": "genuine_original_new_file_anchor_raw_bytes_not_caller_length",
        "file_origin": "exact_registered_new_creator_frame_and_new_class_anchor_registry_body_then_receipt_disjoint_inodes",
        "native_precondition": "observed_original_inode_protections_size_mtime_readonly_and_initial_flags_before_setter_body_no_atomicity_claim",
        "origin_frame": "registered_callback_sys_getframe_1_exact_original_code_identity",
        "exceptional_return": "native_and_guard_callback_PY_UNWIND_retain_original_return_observations",
        "registry_keys": "retained_original_objects_and_original_plain_object_nonces",
        "report_issuance": "original_context_exit_after_resource_cleanup_only",
        "old_evidence_opened": False, "authority": authority()}


def failure_summary(error):
    controlled = previous._controlled(error, [(BodyReceiptMonitorRefusal, _CODES, "monitor")])
    if controlled is None:
        if type(error) is body_custody.BodyReceiptRefusal:
            return body_custody.failure_summary(error)
        return previous.failure_summary(error)
    return {"category": "local_contract_refusal", "contract_code": controlled[1], "errno_name": None}


def _call(name, *args):
    return _API[_API_NAMES.index(name)](*args)


def _identity_methods(value):
    return (type(value) is BodyReceiptImmutableMonitor
        and BodyReceiptImmutableMonitor.__hash__ is object.__hash__
        and BodyReceiptImmutableMonitor.__eq__ is object.__eq__)


def _retained(value):
    for record in _MINTED.values():
        if type(record) is tuple and len(record) == 5 and record[0] is value:
            return record
    return None


def _fixed(value):
    return value if type(value) is str and value in _CODES else "body_monitor_observer_error"


def _phases():
    catalogue = body_custody.monitor_phase_codes()
    require(type(catalogue) is dict and all(type(label) is str and type(code) is types.CodeType
        for label, code in catalogue.items()), "body_monitor_original_code_changed")
    phases = {code: label for label, code in catalogue.items()}
    previous._nested(_NATIVE_CODE, "immutable__native_set", phases)
    previous._nested(previous._code(immutable.require), "immutable_require", phases)
    catalogues = [(immutable.ImmutableMetadataRefusal, immutable._CODES, "immutable"),
        (body_custody.BodyReceiptRefusal, body_custody._CODES, "body_receipt")]
    module = sys.modules.get("scripts.diagnose_short_interest_body_receipt_custody")
    if module is not None:
        require(type(module) is types.ModuleType and type(module.require) is types.FunctionType
            and type(module._CODES) is frozenset and all(type(item) is str for item in module._CODES),
            "body_monitor_arguments_refused")
        for name in ("require", "run_registered", "_challenge", "_original", "_after_all_closes", "_code"):
            function = getattr(module, name, None)
            if type(function) is types.FunctionType:
                previous._nested(function.__code__, "proof_" + name, phases)
        catalogues.append((module.BodyReceiptProofRefusal, module._CODES, "proof"))
    return phases, catalogues


def _original_code(state):
    if (immutable._native_set is not _NATIVE or immutable._native_set.__code__ is not _NATIVE_CODE
            or previous._code(body_custody._prepare_original_file) is not _FACTORY_CODE):
        return False
    if body_custody._binding_anchor(state["binding"]) is not state["binding_anchor"]:
        return False
    current, unused = _phases()
    original = state["phase_pairs"]
    return len(current) == len(original) and all(code is old and phase == label
        for (code, phase), (old, label) in zip(current.items(), original))


class BodyReceiptImmutableMonitor(AbstractContextManager):
    __slots__ = ("_identity",)

    def __init__(self):
        raise BodyReceiptMonitorRefusal("REFUSED: body_monitor_factory_required")

    def _state(self, *, allow_failed=False):
        record = _MINTED.get(self) if _identity_methods(self) else None
        try:
            identity = object.__getattribute__(self, "_identity")
        except AttributeError:
            identity = None
        if type(record) is not tuple or len(record) != 5 or record[0] is not self or record[1] is not identity:
            BodyReceiptImmutableMonitor._fail(self, "body_monitor_binding_changed")
            raise BodyReceiptMonitorRefusal("REFUSED: body_monitor_binding_changed")
        state = record[2]
        try:
            good = (state["bindings"] is record[4][0] and state["phase_pairs"] is record[4][1]
                and state["callbacks"] is record[4][2] and type(state["directory_fd"]) is int
                and state["directory_fd"] == record[4][3]
                and state["binding"] is record[4][4] and state["binding_anchor"] is record[4][5]
                and type(state["events"]) is int
                and (state["thread"] is None or type(state["thread"]) is int)
                and state["thread"] == record[3]["owner_thread"]
                and type(state["native_calls"]) is int
                and (state["events"], state["native_calls"]) == _COUNTS[record[1]]
                and all(type(state["files"][role]["native_call_count"]) is int for role in ROLES)
                and tuple(state["files"][role]["native_call_count"] for role in ROLES) == _ROLE_COUNTS[record[1]])
            for index, role in enumerate(ROLES):
                file, origin = state["files"][role], _FILE_ORIGINS[record[1]][index]
                good = good and file["origin"] is origin
                if origin is not None:
                    good = good and (type(file["bytes"]) is int and file["bytes"] == len(origin[4])
                        and type(file["name"]) is str and file["name"] == origin[3]
                        and type(file["raw_sha256"]) is str and file["raw_sha256"] == origin[5]
                        and type(file["fd"]) is int and file["fd"] == origin[7]
                        and file["original"] is origin[8])
        except BaseException:
            good = False
        if not good:
            BodyReceiptImmutableMonitor._fail(self, "body_monitor_binding_changed")
            raise BodyReceiptMonitorRefusal("REFUSED: body_monitor_binding_changed")
        latched = _FAILED.get(record[1])
        if not allow_failed and latched is not None:
            raise BodyReceiptMonitorRefusal("REFUSED: " + _fixed(latched[2]))
        return state

    def _fail(self, code):
        record = _retained(self)
        if record is not None:
            prior = _FAILED.get(record[1])
            if prior is None:
                _FAILED[record[1]] = self, record[1], _fixed(code)
            elif not (type(prior) is tuple and len(prior) == 3 and prior[0] is self
                    and prior[1] is record[1] and type(prior[2]) is str and prior[2] in _CODES):
                _FAILED[record[1]] = self, record[1], "body_monitor_observer_error"

    def _event(self, state):
        record = _retained(self)
        require((state["events"], state["native_calls"]) == _COUNTS[record[1]], "body_monitor_binding_changed")
        state["events"] += 1
        _COUNTS[record[1]] = state["events"], state["native_calls"]
        require(state["events"] <= MAXIMUM_EVENTS, "body_monitor_observer_overflow")

    def _sample(self, state, file):
        observed = os.fstat(file["fd"]), os.stat(file["name"], dir_fd=state["directory_fd"], follow_symlinks=False)
        stamps = tuple(immutable.creator._stamp(info) for info in observed)
        if file["original"] is None:
            file["original"] = file["origin"][8]
        require(file["original"] is file["origin"][8], "body_monitor_original_factory_changed")
        original = file["original"]
        return {"fd_flags": previous._flag_class(observed[0]), "name_flags": previous._flag_class(observed[1]),
            "same_original_inode": all(row[:2] == original[:2] for row in stamps),
            "protections_match": all(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1 and info.st_size == file["bytes"]
                for info in observed),
            "size_and_mtime_unchanged": all(row[5:7] == original[5:7] for row in stamps),
            "retained_fd_readonly": fcntl.fcntl(file["fd"], fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY}

    def _callback(self, name, bindings):
        def callback(code, offset, *arguments):
            if type(code) is not types.CodeType:
                if name in _EXCEPTION_NAMES:
                    return None
                BodyReceiptImmutableMonitor._fail(self, "body_monitor_original_code_changed")
                raise BodyReceiptMonitorRefusal("REFUSED: body_monitor_original_code_changed")
            # Filter global exception propagation using the ORIGINAL immutable
            # code map before touching state or inspecting any unrelated frame.
            pair = bindings.get(code)
            if pair is None and name in _EXCEPTION_NAMES:
                return None
            try:
                state = self._state()
                require(pair is not None and pair[0] is code, "body_monitor_original_code_changed")
                require(threading.get_ident() == state["thread"], "body_monitor_wrong_thread")
                resource = _retained(self)[3]
                require(state["entered"] is True and resource["owned"] is True
                    and _MONITOR is sys.monitoring and all(getattr(_MONITOR, key) is function
                        for key, function in zip(_API_NAMES, _API))
                    and _call("get_tool", TOOL_ID) == TOOL_NAME
                    and _call("get_events", TOOL_ID) == _GLOBAL_MASK
                    and _call("get_local_events", TOOL_ID, code) == _LOCAL_MASK
                    and state["callbacks"][name] is callback, "body_monitor_monitor_changed")
                # This MUST be in the registered callback, before dispatch.
                frame = sys._getframe(1)
                require(frame.f_code is code, "body_monitor_frame_changed")
                self._observe(state, pair[1], name, code, frame, arguments)
            except BaseException as error:
                controlled = previous._controlled(error, [(BodyReceiptMonitorRefusal, _CODES, "monitor")])
                fixed = controlled[1] if controlled is not None else "body_monitor_observer_error"
                BodyReceiptImmutableMonitor._fail(self, fixed)
                raise BodyReceiptMonitorRefusal("REFUSED: " + fixed) from None
            return None
        return callback

    def _observe(self, state, phase, event, code, frame, arguments):
        require(threading.get_ident() == state["thread"], "body_monitor_wrong_thread")
        if event == "PY_START" and code is _NATIVE_CODE:
            self._event(state)
            state["native_calls"] += 1
            record = _retained(self)
            _COUNTS[record[1]] = state["events"], state["native_calls"]
            require(state["native_calls"] <= 2, "body_monitor_multiple_native_calls")
            parent = frame.f_back
            require(parent is not None and parent.f_code is _FACTORY_CODE, "body_monitor_original_factory_changed")
            origin, cap = parent.f_locals.get("origin"), parent.f_locals.get("file_cap")
            require(type(origin) is tuple and len(origin) == 15
                and type(cap) is body_custody.BodyReceiptFileCustody and cap._anchor is origin
                and body_custody._file_anchor(cap) is origin and parent.f_locals.get("binding") is state["binding"],
                "body_monitor_original_factory_changed")
            role = origin[2]
            require(type(role) is str and role in ROLES and role == ROLES[state["native_calls"] - 1],
                "body_monitor_original_factory_changed")
            file = state["files"][role]
            require(origin[3] == file["name"] and type(origin[4]) is bytes and 0 < len(origin[4]) <= 2 * 1024 ** 2
                and type(origin[5]) is str and hash_bytes(origin[4]) == origin[5]
                and origin[6] == state["directory_fd"], "body_monitor_original_factory_changed")
            fd = frame.f_locals.get("fd")
            require(type(fd) is int and fd == origin[7] == parent.f_locals.get("reader"), "body_monitor_observer_error")
            file["native_call_count"] += 1
            _ROLE_COUNTS[record[1]] = tuple(state["files"][item]["native_call_count"] for item in ROLES)
            require(file["native_call_count"] == 1, "body_monitor_multiple_native_calls")
            origins = list(_FILE_ORIGINS[record[1]])
            require(origins[ROLES.index(role)] is None, "body_monitor_multiple_native_calls")
            origins[ROLES.index(role)] = origin
            _FILE_ORIGINS[record[1]] = tuple(origins)
            file.update(origin=origin, cap=cap, fd=fd, bytes=len(origin[4]), raw_sha256=origin[5])
            file["before_native"] = self._sample(state, file)
            before = file["before_native"]
            require(before["fd_flags"] == before["name_flags"] == origin[9]
                and all(before[name] is True for name in ("same_original_inode", "protections_match",
                    "size_and_mtime_unchanged", "retained_fd_readonly")), "body_monitor_before_native_changed")
            if role == "receipt":
                body = state["files"]["body"]
                require(body["origin"] is not origin and body["cap"] is not cap and body["fd"] != fd
                    and body["original"][:2] != file["original"][:2], "body_monitor_original_factory_changed")
        if event in ("PY_RETURN", "PY_UNWIND") and code is _NATIVE_CODE:
            self._event(state)
            parent = frame.f_back
            require(parent is not None and parent.f_code is _FACTORY_CODE, "body_monitor_original_factory_changed")
            origin = parent.f_locals.get("origin")
            require(type(origin) is tuple and len(origin) == 15 and origin[2] in ROLES, "body_monitor_original_factory_changed")
            file = state["files"][origin[2]]
            require(origin is file["origin"] and parent.f_locals.get("file_cap") is file["cap"],
                "body_monitor_original_factory_changed")
            result, number = frame.f_locals.get("result"), frame.f_locals.get("number")
            file["native_result"] = result if type(result) is int and result in (0, -1) else "unavailable_or_invalid"
            file["native_errno_name"] = previous._ERRNOS.get(number) if type(number) is int else None
            file["immediate_after_native"] = self._sample(state, file)
        if event in ("PY_RETURN", "PY_UNWIND") and phase in {"immutable_guard_callback", "body_receipt_guard_callback"}:
            origin, cap = frame.f_locals.get("origin"), frame.f_locals.get("file_cap")
            if origin is not None or cap is not None:
                require(type(origin) is tuple and len(origin) == 15 and origin[2] in ROLES
                    and type(cap) is body_custody.BodyReceiptFileCustody and cap._anchor is origin
                    and body_custody.BodyReceiptFileCustody._binding(cap, failed=True)[0] is origin,
                    "body_monitor_original_factory_changed")
                file = state["files"][origin[2]]
                if file["immediate_after_native"] is not None:
                    require(origin is file["origin"] and cap is file["cap"], "body_monitor_original_factory_changed")
                    self._event(state)
                    sample = self._sample(state, file)
                    if sample not in file["after_callbacks"]:
                        require(len(file["after_callbacks"]) < MAXIMUM_REFUSALS, "body_monitor_observer_overflow")
                        file["after_callbacks"].append(sample)
        if event in _EXCEPTION_NAMES:
            require(len(arguments) == 1 and isinstance(arguments[0], BaseException), "body_monitor_observer_error")
            error = arguments[0]
            controlled = previous._controlled(error, state["catalogues"])
            if controlled is not None and not any(error is item for item in state["seen_errors"]):
                self._event(state)
                actual_phase = phase
                if frame.f_code.co_name == "require" and frame.f_back is not None:
                    origin = state["bindings"].get(frame.f_back.f_code)
                    if origin is not None and origin[0] is frame.f_back.f_code:
                        actual_phase = origin[1]
                require(len(state["refusals"]) < MAXIMUM_REFUSALS, "body_monitor_observer_overflow")
                state["seen_errors"].append(error)
                state["refusals"].append({"role": controlled[0], "phase": actual_phase, "contract_code": controlled[1]})

    def __enter__(self):
        state = self._state()
        require(not state["entered"], "body_monitor_already_entered")
        require(sys.gettrace() is None, "body_monitor_trace_occupied")
        require(_original_code(state), "body_monitor_original_code_changed")
        require(_MONITOR is sys.monitoring and all(getattr(_MONITOR, name) is function
            for name, function in zip(_API_NAMES, _API)), "body_monitor_monitor_changed")
        resource = _retained(self)[3]
        state["thread"] = threading.get_ident()
        resource["owner_thread"] = state["thread"]
        require(_call("get_tool", TOOL_ID) is None and _call("get_events", TOOL_ID) == 0
            and all(_call("get_local_events", TOOL_ID, code) == 0 for code, unused in state["phase_pairs"]),
            "body_monitor_monitor_busy")
        resource["prior_tool_unused"] = resource["original_global_mask_zero"] = resource["original_target_local_masks_zero"] = True
        try:
            _call("use_tool_id", TOOL_ID, TOOL_NAME)
            resource["owned"] = True
            for name, event in _EVENTS:
                old = _call("register_callback", TOOL_ID, event, None)
                # Mutation succeeds BEFORE the old callback is returned.
                resource["prior_callbacks"].append((event, old))
                resource["expected_callbacks"][event] = None
                require(old is None, "body_monitor_monitor_busy")
            resource["original_known_callbacks_absent"] = True
            for name in (*_LOCAL_NAMES, *_EXCEPTION_NAMES):
                event = dict(_EVENTS)[name]
                callback = state["callbacks"][name]
                old = _call("register_callback", TOOL_ID, event, callback)
                resource["expected_callbacks"][event] = callback
                require(old is None, "body_monitor_monitor_changed")
            for code, unused in state["phase_pairs"]:
                _call("set_local_events", TOOL_ID, code, _LOCAL_MASK)
                resource["active_codes"].append(code)
            _call("set_events", TOOL_ID, _GLOBAL_MASK)
            resource["global_active"] = True
            state["entered"] = True
            return self
        except BaseException as error:
            controlled = previous._controlled(error, [(BodyReceiptMonitorRefusal, _CODES, "monitor")])
            fixed = controlled[1] if controlled is not None else "body_monitor_observer_error"
            self._fail(fixed)
            self._cleanup()
            raise BodyReceiptMonitorRefusal("REFUSED: " + fixed) from None

    def _cleanup(self):
        record = _retained(self)
        if record is None:
            return False
        state, resource = record[2], record[3]
        phase_pairs = record[4][1]
        if not resource["owned"]:
            return False
        if _call("get_tool", TOOL_ID) != TOOL_NAME:
            resource["foreign_ownership_preserved"] = True
            self._fail("body_monitor_monitor_changed")
            return False
        def still_owned():
            try:
                owner = _call("get_tool", TOOL_ID)
            except BaseException:
                BodyReceiptImmutableMonitor._fail(self, "body_monitor_monitor_cleanup_failed")
                return False
            if owner == TOOL_NAME:
                return True
            resource["foreign_ownership_preserved"] = True
            BodyReceiptImmutableMonitor._fail(self, "body_monitor_monitor_changed")
            return False
        good = True
        try:
            expected = _GLOBAL_MASK if resource["global_active"] else 0
            if _call("get_events", TOOL_ID) != expected:
                good = False
            if not still_owned(): return False
            _call("set_events", TOOL_ID, 0)
            resource["global_mask_restored"] = _call("get_events", TOOL_ID) == 0
        except BaseException:
            good = False
        for code, unused in phase_pairs:
            try:
                expected = _LOCAL_MASK if any(code is item for item in resource["active_codes"]) else 0
                if _call("get_local_events", TOOL_ID, code) != expected:
                    good = False
                if not still_owned(): return False
                _call("set_local_events", TOOL_ID, code, 0)
            except BaseException:
                good = False
        try:
            resource["target_local_masks_restored"] = all(_call("get_local_events", TOOL_ID, code) == 0
                for code, unused in phase_pairs)
        except BaseException:
            good = False
        callbacks_good = True
        for event, prior in resource["prior_callbacks"]:
            try:
                if not still_owned(): return False
                actual = _call("register_callback", TOOL_ID, event, prior)
                if not still_owned(): return False
                if actual is not resource["expected_callbacks"][event]:
                    good = False
                    callbacks_good = False
                    # A replacement is somebody else's object, even while our
                    # lease name remains. Preserve it; do not silently erase it
                    # or release a slot with a known residual callback.
                    if not still_owned(): return False
                    displaced = _call("register_callback", TOOL_ID, event, actual)
                    if displaced is not prior:
                        good = False
                # Return proves that our expected original callback was removed.
            except BaseException:
                callbacks_good = False
                good = False
        resource["known_callback_slots_restored"] = callbacks_good
        if not good:
            self._fail("body_monitor_monitor_changed")
        if (resource["global_mask_restored"] and resource["target_local_masks_restored"]
                and resource["known_callback_slots_restored"]):
            try:
                if not still_owned(): return False
                _call("free_tool_id", TOOL_ID)
                resource["owned_tool_released"] = _call("get_tool", TOOL_ID) is None
            except BaseException:
                self._fail("body_monitor_monitor_cleanup_failed")
        closed = (resource["owned_tool_released"] and resource["global_mask_restored"]
            and resource["target_local_masks_restored"] and resource["known_callback_slots_restored"])
        if not closed:
            self._fail("body_monitor_monitor_cleanup_failed")
        return closed

    def __exit__(self, kind, error, traceback):
        record = None
        try:
            record = _retained(self)
            require(record is not None, "body_monitor_binding_changed")
            state = self._state(allow_failed=True)
            require(threading.get_ident() == state["thread"], "body_monitor_wrong_thread")
            require(sys.gettrace() is None, "body_monitor_trace_occupied")
            require(_original_code(state), "body_monitor_original_code_changed")
            require(_MONITOR is sys.monitoring and all(getattr(_MONITOR, name) is function
                for name, function in zip(_API_NAMES, _API)), "body_monitor_monitor_changed")
            require(state["native_calls"] == 2
                and all(state["files"][role]["native_call_count"] == 1
                    and state["files"][role]["immediate_after_native"] is not None for role in ROLES)
                and state["files"]["body"]["origin"] is not state["files"]["receipt"]["origin"]
                and state["files"]["body"]["original"][:2] != state["files"]["receipt"]["original"][:2],
                "body_monitor_missing_native_observation")
        except BaseException as observed_error:
            controlled = previous._controlled(observed_error, [(BodyReceiptMonitorRefusal, _CODES, "monitor")])
            BodyReceiptImmutableMonitor._fail(self, controlled[1] if controlled is not None else "body_monitor_observer_error")
        finally:
            try:
                closed = BodyReceiptImmutableMonitor._cleanup(self)
            except BaseException:
                closed = False
                BodyReceiptImmutableMonitor._fail(self, "body_monitor_monitor_cleanup_failed")
        if record is None:
            raise BodyReceiptMonitorRefusal("REFUSED: body_monitor_binding_changed")
        state, resource = record[2], record[3]
        try:
            latched = _FAILED.get(record[1])
            raw_failure = latched[2] if latched is not None else state["observer_failure"]
            failure = None if raw_failure is None else _fixed(raw_failure)
            if failure is not None:
                self._fail(failure)
            require(closed, "body_monitor_monitor_cleanup_failed")
            state["observer_failure"] = failure
            files = []
            for role in ROLES:
                file = state["files"][role]
                immediate = file["immediate_after_native"]
                classification = "no_complete_native_observation"
                if immediate is not None:
                    target = 2 if file["before_native"]["fd_flags"] == 0 else 66
                    if immediate["fd_flags"] != immediate["name_flags"]:
                        classification = "immediate_original_fd_name_flags_disagree"
                    elif immediate["fd_flags"] != target:
                        classification = "required_flags_absent_at_immediate_observation"
                    elif any(row["fd_flags"] != target or row["name_flags"] != target for row in file["after_callbacks"]):
                        classification = "required_flags_observed_then_lost"
                    else:
                        classification = "required_flags_observed_without_recorded_loss"
                row = {name: file[name] for name in ("name", "bytes", "raw_sha256", "native_call_count",
                    "native_result", "native_errno_name", "before_native", "immediate_after_native", "after_callbacks")}
                row.update(role=role, classification=classification)
                files.append(row)
            restoration = {name: resource[name] for name in ("prior_tool_unused", "original_global_mask_zero",
                "original_target_local_masks_zero", "original_known_callbacks_absent", "owned_tool_released",
                "global_mask_restored", "target_local_masks_restored", "known_callback_slots_restored",
                "foreign_ownership_preserved")}
            restoration.update(tool_id=TOOL_ID, scope=SCOPE)
            report = {"schema": "si-body-receipt-immutable-monitoring-diagnostic-v1", "backend": BACKEND,
                "monitoring_context_closed": True, "resource_restoration": restoration,
                "observer_complete": failure is None, "observer_failure": failure,
                "native_call_count": state["native_calls"], "files": files,
                "distinct_original_inodes": all(state["files"][role]["original"] is not None for role in ROLES)
                    and state["files"]["body"]["original"][:2] != state["files"]["receipt"]["original"][:2],
                "first_controlled_refusal": state["refusals"][0] if state["refusals"] else None,
                "controlled_refusals": state["refusals"], "policy_sha256": hash_payload(policy()), "authority": authority()}
            raw = canonical_json(report)
            state["closed"] = True
            state["report_raw"] = raw
            _ISSUED[record[1]] = self, record[1], raw
        except BaseException as observed_error:
            controlled = previous._controlled(observed_error, [(BodyReceiptMonitorRefusal, _CODES, "monitor")])
            fixed = controlled[1] if controlled is not None else "body_monitor_observer_error"
            self._fail(fixed)
            raise BodyReceiptMonitorRefusal("REFUSED: " + fixed) from None
        if failure is not None:
            raise BodyReceiptMonitorRefusal("REFUSED: " + failure) from None
        return False

    def report(self):
        state = self._state(allow_failed=True)
        record = _retained(self)
        issued = _ISSUED.get(record[1])
        require(type(issued) is tuple and issued[0] is self and issued[1] is record[1]
            and state["closed"] is True and state["report_raw"] is issued[2], "body_monitor_not_closed")
        value = json.loads(issued[2])
        latched = _FAILED.get(record[1])
        require(latched is None or (value["observer_complete"] is False and value["observer_failure"] == latched[2]),
            "body_monitor_not_closed")
        return {"diagnostic": value, "diagnostic_sha256": hash_payload(value)}


def observe_original_transition(*, directory_fd, binding):
    require(BodyReceiptImmutableMonitor.__hash__ is object.__hash__
        and BodyReceiptImmutableMonitor.__eq__ is object.__eq__, "body_monitor_binding_changed")
    require(type(directory_fd) is int and type(binding) is body_custody.BodyReceiptBinding
        and body_custody.BODY_NAME == BODY_NAME and body_custody.RECEIPT_NAME == RECEIPT_NAME,
        "body_monitor_arguments_refused")
    binding_anchor = body_custody._binding_anchor(binding)
    info = os.fstat(directory_fd)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
        "body_monitor_arguments_refused")
    for name in (BODY_NAME, RECEIPT_NAME):
        try:
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise BodyReceiptMonitorRefusal("REFUSED: body_monitor_arguments_refused")
    phases, catalogues = _phases()
    value = object.__new__(BodyReceiptImmutableMonitor)
    value._identity = object()
    bindings = types.MappingProxyType({code: (code, phase) for code, phase in phases.items()})
    files = {role: {"name": name, "bytes": 0, "raw_sha256": None, "native_call_count": 0,
        "origin": None, "cap": None, "fd": None, "original": None,
        "native_result": "unavailable_or_invalid", "native_errno_name": None,
        "before_native": None, "immediate_after_native": None, "after_callbacks": []}
        for role, name in zip(ROLES, (BODY_NAME, RECEIPT_NAME))}
    state = {"directory_fd": directory_fd, "binding": binding, "binding_anchor": binding_anchor,
        "phase_pairs": tuple(phases.items()), "files": files,
        "bindings": bindings, "catalogues": catalogues, "callbacks": {}, "entered": False, "closed": False,
        "thread": None, "events": 0, "native_calls": 0, "refusals": [],
        "seen_errors": [], "observer_failure": None, "report_raw": None}
    resource = {"owned": False, "owner_thread": None, "prior_callbacks": [], "expected_callbacks": {}, "active_codes": [],
        "global_active": False, "prior_tool_unused": False, "original_global_mask_zero": False,
        "original_target_local_masks_zero": False, "original_known_callbacks_absent": False,
        "owned_tool_released": False, "global_mask_restored": False, "target_local_masks_restored": False,
        "known_callback_slots_restored": False, "foreign_ownership_preserved": False}
    state["callbacks"] = types.MappingProxyType({event: value._callback(event, bindings)
        for event in (*_LOCAL_NAMES, *_EXCEPTION_NAMES)})
    pins = bindings, state["phase_pairs"], state["callbacks"], directory_fd, binding, binding_anchor
    _MINTED[value] = value, value._identity, state, resource, pins
    _COUNTS[value._identity] = 0, 0
    _ROLE_COUNTS[value._identity] = 0, 0
    _FILE_ORIGINS[value._identity] = None, None
    return value
