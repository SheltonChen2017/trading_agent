"""Finite sys.monitoring observations of unchanged ORIGINAL metadata code.

This diagnostic owns only tool 4, its global mask, exact original target-local
masks and fixed known callback slots. Unknown-code local masks cannot be
enumerated by this API and are neither adopted nor changed. No setter, check,
writer, source, flag or original custody deadline is replaced.
"""
from contextlib import AbstractContextManager
import json
import os
import stat
import sys
import threading
import types

from data.hashing import canonical_json, hash_payload
from scripts import short_interest_immutable_transition_diagnostics as previous

immutable = previous.immutable
NAME = previous.NAME
MAXIMUM_REFUSALS, MAXIMUM_EVENTS = 16, 32768
TOOL_ID, TOOL_NAME = 4, "si-offline-targeted-immutable-v1"
BACKEND = "sys.monitoring_local_original_code_events"
SCOPE = "global_exact_target_local_known_callback_slots_and_tool4_ownership_only"
_NATIVE, _NATIVE_CODE, _FACTORY_CODE = previous._NATIVE, previous._NATIVE_CODE, previous._FACTORY_CODE
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
_MINTED, _FAILED, _ISSUED, _COUNTS = {}, {}, {}, {}
_CODES = frozenset("""targeted_factory_required targeted_arguments_refused targeted_binding_changed
targeted_monitor_busy targeted_monitor_changed targeted_monitor_cleanup_failed targeted_trace_occupied
targeted_original_code_changed targeted_already_entered targeted_not_closed targeted_wrong_thread
targeted_observer_error targeted_observer_overflow targeted_multiple_native_calls
targeted_original_factory_changed targeted_missing_native_observation targeted_frame_changed""".split())


class TargetedMonitorRefusal(ValueError):
    pass


def require(value, code):
    if not value:
        raise TargetedMonitorRefusal("REFUSED: " + code)


def authority():
    return previous.authority()


def policy():
    return {"schema": "si-targeted-immutable-monitoring-policy-v1", "name": NAME,
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
        "maximum_native_calls": 1, "maximum_controlled_refusals": MAXIMUM_REFUSALS,
        "maximum_meaningful_events": MAXIMUM_EVENTS, "bytes": 186,
        "origin_frame": "registered_callback_sys_getframe_1_exact_original_code_identity",
        "exceptional_return": "native_and_guard_callback_PY_UNWIND_retain_original_return_observations",
        "registry_keys": "retained_original_objects_and_original_plain_object_nonces",
        "report_issuance": "original_context_exit_after_resource_cleanup_only",
        "old_evidence_opened": False, "authority": authority()}


def failure_summary(error):
    controlled = previous._controlled(error, [(TargetedMonitorRefusal, _CODES, "monitor")])
    if controlled is None:
        return previous.failure_summary(error)
    return {"category": "local_contract_refusal", "contract_code": controlled[1], "errno_name": None}


def _call(name, *args):
    return _API[_API_NAMES.index(name)](*args)


def _identity_methods(value):
    return (type(value) is TargetedImmutableMonitor
        and TargetedImmutableMonitor.__hash__ is object.__hash__
        and TargetedImmutableMonitor.__eq__ is object.__eq__)


def _retained(value):
    for record in _MINTED.values():
        if type(record) is tuple and len(record) == 5 and record[0] is value:
            return record
    return None


def _fixed(value):
    return value if type(value) is str and value in _CODES else "targeted_observer_error"


def _phases(binding):
    phases = previous._phase_codes()
    catalogues = [(immutable.ImmutableMetadataRefusal, immutable._CODES, "immutable"),
        (immutable.creator.NewMetadataRefusal, immutable.creator._CODES, "creator")]
    previous._proof_binding(binding, phases, catalogues)
    return phases, catalogues


def _original_code(state):
    if (immutable._native_set is not _NATIVE or immutable._native_set.__code__ is not _NATIVE_CODE
            or previous._code(immutable.prepare_owned_immutable_metadata) is not _FACTORY_CODE):
        return False
    current, unused = _phases(state["proof_binding"])
    original = state["phase_pairs"]
    return len(current) == len(original) and all(code is old and phase == label
        for (code, phase), (old, label) in zip(current.items(), original))


class TargetedImmutableMonitor(AbstractContextManager):
    __slots__ = ("_identity",)

    def __init__(self):
        raise TargetedMonitorRefusal("REFUSED: targeted_factory_required")

    def _state(self, *, allow_failed=False):
        record = _MINTED.get(self) if _identity_methods(self) else None
        try:
            identity = object.__getattribute__(self, "_identity")
        except AttributeError:
            identity = None
        if type(record) is not tuple or len(record) != 5 or record[0] is not self or record[1] is not identity:
            TargetedImmutableMonitor._fail(self, "targeted_binding_changed")
            raise TargetedMonitorRefusal("REFUSED: targeted_binding_changed")
        state = record[2]
        try:
            good = (state["bindings"] is record[4][0] and state["phase_pairs"] is record[4][1]
                and state["callbacks"] is record[4][2] and type(state["directory_fd"]) is int
                and state["directory_fd"] == record[4][3]
                and state["proof_binding"] is record[4][4] and type(state["events"]) is int
                and (state["thread"] is None or type(state["thread"]) is int)
                and state["thread"] == record[3]["owner_thread"]
                and type(state["native_calls"]) is int
                and (state["events"], state["native_calls"]) == _COUNTS[record[1]])
        except BaseException:
            good = False
        if not good:
            TargetedImmutableMonitor._fail(self, "targeted_binding_changed")
            raise TargetedMonitorRefusal("REFUSED: targeted_binding_changed")
        latched = _FAILED.get(record[1])
        if not allow_failed and latched is not None:
            raise TargetedMonitorRefusal("REFUSED: " + _fixed(latched[2]))
        return state

    def _fail(self, code):
        record = _retained(self)
        if record is not None:
            prior = _FAILED.get(record[1])
            if prior is None:
                _FAILED[record[1]] = self, record[1], _fixed(code)
            elif not (type(prior) is tuple and len(prior) == 3 and prior[0] is self
                    and prior[1] is record[1] and type(prior[2]) is str and prior[2] in _CODES):
                _FAILED[record[1]] = self, record[1], "targeted_observer_error"

    def _event(self, state):
        record = _retained(self)
        require((state["events"], state["native_calls"]) == _COUNTS[record[1]], "targeted_binding_changed")
        state["events"] += 1
        _COUNTS[record[1]] = state["events"], state["native_calls"]
        require(state["events"] <= MAXIMUM_EVENTS, "targeted_observer_overflow")

    def _sample(self, state, fd):
        # Exactly the original read-only FD/name/protection/flag observations.
        return previous.ImmutableTransitionDiagnostic._sample(self, state, fd)

    def _callback(self, name, bindings):
        def callback(code, offset, *arguments):
            if type(code) is not types.CodeType:
                if name in _EXCEPTION_NAMES:
                    return None
                TargetedImmutableMonitor._fail(self, "targeted_original_code_changed")
                raise TargetedMonitorRefusal("REFUSED: targeted_original_code_changed")
            # Filter global exception propagation using the ORIGINAL immutable
            # code map before touching state or inspecting any unrelated frame.
            pair = bindings.get(code)
            if pair is None and name in _EXCEPTION_NAMES:
                return None
            try:
                state = self._state()
                require(pair is not None and pair[0] is code, "targeted_original_code_changed")
                require(threading.get_ident() == state["thread"], "targeted_wrong_thread")
                resource = _retained(self)[3]
                require(state["entered"] is True and resource["owned"] is True
                    and _MONITOR is sys.monitoring and all(getattr(_MONITOR, key) is function
                        for key, function in zip(_API_NAMES, _API))
                    and _call("get_tool", TOOL_ID) == TOOL_NAME
                    and _call("get_events", TOOL_ID) == _GLOBAL_MASK
                    and _call("get_local_events", TOOL_ID, code) == _LOCAL_MASK
                    and state["callbacks"][name] is callback, "targeted_monitor_changed")
                # This MUST be in the registered callback, before dispatch.
                frame = sys._getframe(1)
                require(frame.f_code is code, "targeted_frame_changed")
                self._observe(state, pair[1], name, code, frame, arguments)
            except BaseException as error:
                controlled = previous._controlled(error, [(TargetedMonitorRefusal, _CODES, "monitor")])
                fixed = controlled[1] if controlled is not None else "targeted_observer_error"
                TargetedImmutableMonitor._fail(self, fixed)
                raise TargetedMonitorRefusal("REFUSED: " + fixed) from None
            return None
        return callback

    def _observe(self, state, phase, event, code, frame, arguments):
        require(threading.get_ident() == state["thread"], "targeted_wrong_thread")
        if event == "PY_START" and code is _NATIVE_CODE:
            self._event(state)
            state["native_calls"] += 1
            record = _retained(self)
            _COUNTS[record[1]] = state["events"], state["native_calls"]
            require(state["native_calls"] == 1, "targeted_multiple_native_calls")
            parent = frame.f_back
            require(parent is not None and parent.f_code is _FACTORY_CODE, "targeted_original_factory_changed")
            original, cap = parent.f_locals.get("original"), parent.f_locals.get("cap")
            require(type(original) is tuple and len(original) == 15 and original[2] == NAME
                and original[6] == state["directory_fd"] and type(original[3]) is bytes and len(original[3]) == 186
                and type(cap) is immutable.creator.NewMetadataCustody and cap._anchor is original,
                "targeted_original_factory_changed")
            fd = frame.f_locals.get("fd")
            require(type(fd) is int, "targeted_observer_error")
            state["native_fd"] = fd
            state["before_native"] = self._sample(state, fd)
        if event in ("PY_RETURN", "PY_UNWIND") and code is _NATIVE_CODE:
            self._event(state)
            result, number = frame.f_locals.get("result"), frame.f_locals.get("number")
            state["native_result"] = result if type(result) is int and result in (0, -1) else "unavailable_or_invalid"
            state["native_errno_name"] = previous._ERRNOS.get(number) if type(number) is int else None
            state["immediate_after_native"] = self._sample(state, state["native_fd"])
        if event in ("PY_RETURN", "PY_UNWIND") and phase == "immutable_guard_callback" and state["immediate_after_native"] is not None:
            self._event(state)
            sample = self._sample(state, state["native_fd"])
            if sample not in state["after_callbacks"]:
                require(len(state["after_callbacks"]) < MAXIMUM_REFUSALS, "targeted_observer_overflow")
                state["after_callbacks"].append(sample)
        if event in _EXCEPTION_NAMES:
            require(len(arguments) == 1 and isinstance(arguments[0], BaseException), "targeted_observer_error")
            error = arguments[0]
            controlled = previous._controlled(error, state["catalogues"])
            if controlled is not None and not any(error is item for item in state["seen_errors"]):
                self._event(state)
                actual_phase = phase
                if phase in {"immutable_require", "creator_require", "proof_require"} and frame.f_back is not None:
                    origin = state["bindings"].get(frame.f_back.f_code)
                    if origin is not None and origin[0] is frame.f_back.f_code:
                        actual_phase = origin[1]
                require(len(state["refusals"]) < MAXIMUM_REFUSALS, "targeted_observer_overflow")
                state["seen_errors"].append(error)
                state["refusals"].append({"role": controlled[0], "phase": actual_phase, "contract_code": controlled[1]})

    def __enter__(self):
        state = self._state()
        require(not state["entered"], "targeted_already_entered")
        require(sys.gettrace() is None, "targeted_trace_occupied")
        require(_original_code(state), "targeted_original_code_changed")
        require(_MONITOR is sys.monitoring and all(getattr(_MONITOR, name) is function
            for name, function in zip(_API_NAMES, _API)), "targeted_monitor_changed")
        resource = _retained(self)[3]
        state["thread"] = threading.get_ident()
        resource["owner_thread"] = state["thread"]
        require(_call("get_tool", TOOL_ID) is None and _call("get_events", TOOL_ID) == 0
            and all(_call("get_local_events", TOOL_ID, code) == 0 for code, unused in state["phase_pairs"]),
            "targeted_monitor_busy")
        resource["prior_tool_unused"] = resource["original_global_mask_zero"] = resource["original_target_local_masks_zero"] = True
        try:
            _call("use_tool_id", TOOL_ID, TOOL_NAME)
            resource["owned"] = True
            for name, event in _EVENTS:
                old = _call("register_callback", TOOL_ID, event, None)
                # Mutation succeeds BEFORE the old callback is returned.
                resource["prior_callbacks"].append((event, old))
                resource["expected_callbacks"][event] = None
                require(old is None, "targeted_monitor_busy")
            resource["original_known_callbacks_absent"] = True
            for name in (*_LOCAL_NAMES, *_EXCEPTION_NAMES):
                event = dict(_EVENTS)[name]
                callback = state["callbacks"][name]
                old = _call("register_callback", TOOL_ID, event, callback)
                resource["expected_callbacks"][event] = callback
                require(old is None, "targeted_monitor_changed")
            for code, unused in state["phase_pairs"]:
                _call("set_local_events", TOOL_ID, code, _LOCAL_MASK)
                resource["active_codes"].append(code)
            _call("set_events", TOOL_ID, _GLOBAL_MASK)
            resource["global_active"] = True
            state["entered"] = True
            return self
        except BaseException as error:
            controlled = previous._controlled(error, [(TargetedMonitorRefusal, _CODES, "monitor")])
            fixed = controlled[1] if controlled is not None else "targeted_observer_error"
            self._fail(fixed)
            self._cleanup()
            raise TargetedMonitorRefusal("REFUSED: " + fixed) from None

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
            self._fail("targeted_monitor_changed")
            return False
        def still_owned():
            try:
                owner = _call("get_tool", TOOL_ID)
            except BaseException:
                TargetedImmutableMonitor._fail(self, "targeted_monitor_cleanup_failed")
                return False
            if owner == TOOL_NAME:
                return True
            resource["foreign_ownership_preserved"] = True
            TargetedImmutableMonitor._fail(self, "targeted_monitor_changed")
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
            self._fail("targeted_monitor_changed")
        if (resource["global_mask_restored"] and resource["target_local_masks_restored"]
                and resource["known_callback_slots_restored"]):
            try:
                if not still_owned(): return False
                _call("free_tool_id", TOOL_ID)
                resource["owned_tool_released"] = _call("get_tool", TOOL_ID) is None
            except BaseException:
                self._fail("targeted_monitor_cleanup_failed")
        closed = (resource["owned_tool_released"] and resource["global_mask_restored"]
            and resource["target_local_masks_restored"] and resource["known_callback_slots_restored"])
        if not closed:
            self._fail("targeted_monitor_cleanup_failed")
        return closed

    def __exit__(self, kind, error, traceback):
        record = None
        try:
            record = _retained(self)
            require(record is not None, "targeted_binding_changed")
            state = self._state(allow_failed=True)
            require(threading.get_ident() == state["thread"], "targeted_wrong_thread")
            require(sys.gettrace() is None, "targeted_trace_occupied")
            require(_original_code(state), "targeted_original_code_changed")
            require(_MONITOR is sys.monitoring and all(getattr(_MONITOR, name) is function
                for name, function in zip(_API_NAMES, _API)), "targeted_monitor_changed")
            require(state["native_calls"] == 1 and state["immediate_after_native"] is not None,
                "targeted_missing_native_observation")
        except BaseException as observed_error:
            controlled = previous._controlled(observed_error, [(TargetedMonitorRefusal, _CODES, "monitor")])
            TargetedImmutableMonitor._fail(self, controlled[1] if controlled is not None else "targeted_observer_error")
        finally:
            try:
                closed = TargetedImmutableMonitor._cleanup(self)
            except BaseException:
                closed = False
                TargetedImmutableMonitor._fail(self, "targeted_monitor_cleanup_failed")
        if record is None:
            raise TargetedMonitorRefusal("REFUSED: targeted_binding_changed")
        state, resource = record[2], record[3]
        try:
            latched = _FAILED.get(record[1])
            raw_failure = latched[2] if latched is not None else state["observer_failure"]
            failure = None if raw_failure is None else _fixed(raw_failure)
            if failure is not None:
                self._fail(failure)
            require(closed, "targeted_monitor_cleanup_failed")
            state["observer_failure"] = failure
            immediate = state["immediate_after_native"]
            classification = "no_complete_native_observation"
            if immediate is not None:
                target = 2 if state["before_native"]["fd_flags"] == 0 else 66
                if immediate["fd_flags"] != immediate["name_flags"]:
                    classification = "immediate_original_fd_name_flags_disagree"
                elif immediate["fd_flags"] != target:
                    classification = "required_flags_absent_at_immediate_observation"
                elif any(row["fd_flags"] != target or row["name_flags"] != target for row in state["after_callbacks"]):
                    classification = "required_flags_observed_then_lost"
                else:
                    classification = "required_flags_observed_without_recorded_loss"
            restoration = {name: resource[name] for name in ("prior_tool_unused", "original_global_mask_zero",
                "original_target_local_masks_zero", "original_known_callbacks_absent", "owned_tool_released",
                "global_mask_restored", "target_local_masks_restored", "known_callback_slots_restored",
                "foreign_ownership_preserved")}
            restoration.update(tool_id=TOOL_ID, scope=SCOPE)
            report = {"schema": "si-targeted-immutable-monitoring-diagnostic-v1", "backend": BACKEND,
                "monitoring_context_closed": True, "resource_restoration": restoration,
                "observer_complete": failure is None, "observer_failure": failure,
                "native_call_count": state["native_calls"], "native_result": state["native_result"],
                "native_errno_name": state["native_errno_name"], "before_native": state["before_native"],
                "immediate_after_native": immediate, "after_callbacks": state["after_callbacks"],
                "classification": classification, "first_controlled_refusal": state["refusals"][0] if state["refusals"] else None,
                "controlled_refusals": state["refusals"], "policy_sha256": hash_payload(policy()), "authority": authority()}
            raw = canonical_json(report)
            state["closed"] = True
            state["report_raw"] = raw
            _ISSUED[record[1]] = self, record[1], raw
        except BaseException as observed_error:
            controlled = previous._controlled(observed_error, [(TargetedMonitorRefusal, _CODES, "monitor")])
            fixed = controlled[1] if controlled is not None else "targeted_observer_error"
            self._fail(fixed)
            raise TargetedMonitorRefusal("REFUSED: " + fixed) from None
        if failure is not None:
            raise TargetedMonitorRefusal("REFUSED: " + failure) from None
        return False

    def report(self):
        state = self._state(allow_failed=True)
        record = _retained(self)
        issued = _ISSUED.get(record[1])
        require(type(issued) is tuple and issued[0] is self and issued[1] is record[1]
            and state["closed"] is True and state["report_raw"] is issued[2], "targeted_not_closed")
        value = json.loads(issued[2])
        latched = _FAILED.get(record[1])
        require(latched is None or (value["observer_complete"] is False and value["observer_failure"] == latched[2]),
            "targeted_not_closed")
        return {"diagnostic": value, "diagnostic_sha256": hash_payload(value)}


def observe_original_transition(*, directory_fd, name, proof_binding=None):
    require(TargetedImmutableMonitor.__hash__ is object.__hash__
        and TargetedImmutableMonitor.__eq__ is object.__eq__, "targeted_binding_changed")
    require(type(directory_fd) is int and type(name) is str and name == NAME, "targeted_arguments_refused")
    info = os.fstat(directory_fd)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
        "targeted_arguments_refused")
    try:
        os.stat(NAME, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise TargetedMonitorRefusal("REFUSED: targeted_arguments_refused")
    phases, catalogues = _phases(proof_binding)
    value = object.__new__(TargetedImmutableMonitor)
    value._identity = object()
    bindings = types.MappingProxyType({code: (code, phase) for code, phase in phases.items()})
    state = {"directory_fd": directory_fd, "proof_binding": proof_binding, "phase_pairs": tuple(phases.items()),
        "bindings": bindings, "catalogues": catalogues, "callbacks": {}, "entered": False, "closed": False,
        "thread": None, "events": 0, "native_calls": 0, "native_fd": None, "original": None,
        "before_native": None, "immediate_after_native": None, "after_callbacks": [],
        "native_result": "unavailable_or_invalid", "native_errno_name": None, "refusals": [],
        "seen_errors": [], "observer_failure": None, "report_raw": None}
    resource = {"owned": False, "owner_thread": None, "prior_callbacks": [], "expected_callbacks": {}, "active_codes": [],
        "global_active": False, "prior_tool_unused": False, "original_global_mask_zero": False,
        "original_target_local_masks_zero": False, "original_known_callbacks_absent": False,
        "owned_tool_released": False, "global_mask_restored": False, "target_local_masks_restored": False,
        "known_callback_slots_restored": False, "foreign_ownership_preserved": False}
    state["callbacks"] = types.MappingProxyType({event: value._callback(event, bindings)
        for event in (*_LOCAL_NAMES, *_EXCEPTION_NAMES)})
    pins = bindings, state["phase_pairs"], state["callbacks"], directory_fd, proof_binding
    _MINTED[value] = value, value._identity, state, resource, pins
    _COUNTS[value._identity] = 0, 0
    return value
