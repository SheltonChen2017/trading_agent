"""Finite read-only tracing of the ORIGINAL new-metadata immutable transition.

Never replaces a setter/check, clears a flag, opens a writer, admits a source,
or repairs evidence. The caller must still require the original proof closure.
"""
from contextlib import AbstractContextManager
import errno
import fcntl
import json
import os
import stat
import sys
import threading
import types

from data.hashing import canonical_json, hash_payload
from scripts import short_interest_immutable_metadata as immutable

NAME = "one-safe-nonclaim.private.json"
MAXIMUM_REFUSALS = 16
MAXIMUM_EVENTS = 32768
_NATIVE = immutable._native_set
_NATIVE_CODE = _NATIVE.__code__
_MINTED = {}
_FAILED = {}  # Independent first observer fault; mutable state cannot reset it.
_ISSUED = {}  # Only the original context exit may issue canonical report bytes.
_ERRNOS = {getattr(errno, name): name for name in (
    "EACCES", "EPERM", "EBADF", "EINVAL", "EIO", "ENOSYS", "ENOTSUP", "EOPNOTSUPP")
    if hasattr(errno, name)}
_CODES = frozenset("""transition_factory_required transition_trace_occupied
transition_arguments_refused transition_original_code_changed transition_already_entered
transition_not_closed transition_observer_lost transition_observer_error
transition_observer_overflow transition_multiple_native_calls transition_wrong_thread
transition_binding_changed transition_missing_native_observation
transition_original_factory_changed""".split())


class TransitionDiagnosticRefusal(ValueError):
    pass


def require(value, code):
    if not value:
        raise TransitionDiagnosticRefusal("REFUSED: " + code)


def authority():
    return {"diagnostic_only": True, "provider_HTTP": 0, "credential_reads": 0,
        "source_STARTs": 0, "source_bytes": 0, "source_admitted": False,
        "historical_repair_established": False, "ready_for_backtest": False,
        "outcome_looks": 0, "qc_attempts": 0, "trading_authority": False}


def policy():
    return {"schema": "si-immutable-transition-diagnostic-policy-v1", "name": NAME,
        "maximum_native_calls": 1, "maximum_controlled_refusals": MAXIMUM_REFUSALS,
        "maximum_trace_events": MAXIMUM_EVENTS, "bytes": 186,
        "original_native_and_checks_replaced": False, "native_observation":
        "original_call_return_immediate_readonly_FD_and_fixed_name_before_callbacks",
        "trace_entry": "original_sys_gettrace_None", "trace_exit": "restore_original_None",
        "permanent_observer_failure_latch": True,
        "report_issuance": "original_context_exit_only_independent_canonical_bytes",
        "old_evidence_opened": False, "authority": authority()}


def failure_summary(error):
    controlled = _controlled(error, [(TransitionDiagnosticRefusal, _CODES, "observer")])
    if controlled is None:
        return immutable.failure_summary(error)
    return {"category": "local_contract_refusal", "contract_code": controlled[1], "errno_name": None}


def _code(function):
    # @contextmanager returns a SHARED contextlib wrapper. Observe the exact
    # original generator, not the decorator's helper or unrelated contexts.
    original = getattr(function, "__wrapped__", function)
    require(type(original) is types.FunctionType, "transition_original_code_changed")
    return original.__code__


def _nested(code, phase, result):
    result[code] = phase
    for child in code.co_consts:
        if type(child) is types.CodeType:
            _nested(child, "immutable_guard_callback" if child.co_name == "guarded_boundary" else phase, result)


def _phase_codes():
    result = {}
    for name in ("_native_set", "prepare_owned_immutable_metadata", "require"):
        _nested(_code(getattr(immutable, name)), "immutable_" + name, result)
    for name in ("_binding", "_audit", "seal_once", "check", "read", "closed_summary"):
        _nested(getattr(immutable.ImmutableMetadataCustody, name).__code__, "immutable_" + name, result)
    for name in ("prepare_owned_metadata", "require"):
        _nested(_code(getattr(immutable.creator, name)), "creator_" + name, result)
    for name in ("_guard", "_owned", "_pair", "_strict", "_tick", "seal_once", "check", "_close"):
        _nested(getattr(immutable.creator.NewMetadataCustody, name).__code__, "creator_" + name, result)
    return result


_PHASE_CODES = _phase_codes()
_FACTORY_CODE = _code(immutable.prepare_owned_immutable_metadata)


def _flag_class(info):
    value = immutable._flags(info)
    return value if type(value) is int and value in (0, 2, 64, 66) else "other"


def _controlled(error, catalogues):
    for cls, codes, role in catalogues:
        if type(error) is not cls:
            continue
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            for code in codes:
                if args[0] == "REFUSED: " + code:
                    return role, code
    return None


def _proof_binding(binding, phases, catalogues):
    if binding is None:
        return
    require(type(binding) is tuple and len(binding) == 3, "transition_arguments_refused")
    function, cls, codes = binding
    module = sys.modules.get("scripts.diagnose_short_interest_immutable_metadata")
    require(type(module) is types.ModuleType and function is getattr(module, "require", None)
        and cls is getattr(module, "ImmutableProofRefusal", None) and codes is getattr(module, "_CODES", None)
        and type(function) is types.FunctionType and type(codes) is frozenset
        and all(type(code) is str for code in codes), "transition_arguments_refused")
    for name in ("require", "run_registered", "_challenge", "_original", "_after_all_closes", "_code"):
        _nested(getattr(module, name).__code__, "proof_" + name, phases)
    catalogues.append((cls, codes, "proof"))


class ImmutableTransitionDiagnostic(AbstractContextManager):
    __slots__ = ("_identity",)

    def __init__(self):
        raise TransitionDiagnosticRefusal("REFUSED: transition_factory_required")

    def _state(self):
        record = _MINTED.get(id(self))
        require(type(self) is ImmutableTransitionDiagnostic and type(record) is tuple
            and record[0] is self and record[1] is self._identity, "transition_binding_changed")
        return record[2]

    def _fail(self, code):
        record = _MINTED.get(id(self))
        if type(record) is tuple and record[0] is self:
            _FAILED.setdefault(id(self), (self, record[1], code))

    def __enter__(self):
        state = self._state()
        require(not state["entered"], "transition_already_entered")
        require(sys.gettrace() is None, "transition_trace_occupied")
        require(immutable._native_set is _NATIVE and immutable._native_set.__code__ is _NATIVE_CODE,
            "transition_original_code_changed")
        state["thread"] = threading.get_ident()
        state["entered"] = True
        state["tracer"] = self._trace
        sys.settrace(state["tracer"])
        return self

    def _sample(self, state, fd):
        before = state["original"]
        observed = os.fstat(fd), os.stat(NAME, dir_fd=state["directory_fd"], follow_symlinks=False)
        stamps = tuple(immutable.creator._stamp(info) for info in observed)
        if before is None:
            state["original"] = stamps[0]
            before = stamps[0]
        return {"fd_flags": _flag_class(observed[0]), "name_flags": _flag_class(observed[1]),
            "same_original_inode": all(row[:2] == before[:2] for row in stamps),
            "protections_match": all(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1 and info.st_size == 186
                for info in observed),
            "size_and_mtime_unchanged": all(row[5:7] == before[5:7] for row in stamps),
            "retained_fd_readonly": fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY}

    def _trace(self, frame, event, argument):
        state = self._state()
        if frame.f_code not in state["phases"]:
            return None
        try:
            require(threading.get_ident() == state["thread"], "transition_wrong_thread")
            frame.f_trace_lines = False
            frame.f_trace_opcodes = False
            phase = state["phases"][frame.f_code]
            if event == "call" and frame.f_code is _NATIVE_CODE:
                self._event(state)
                state["native_calls"] += 1
                require(state["native_calls"] == 1, "transition_multiple_native_calls")
                parent = frame.f_back
                require(parent is not None and parent.f_code is _FACTORY_CODE,
                    "transition_original_factory_changed")
                original = parent.f_locals.get("original")
                cap = parent.f_locals.get("cap")
                require(type(original) is tuple and len(original) == 15
                    and original[2] == NAME and original[6] == state["directory_fd"]
                    and type(original[3]) is bytes and len(original[3]) == 186
                    and type(cap) is immutable.creator.NewMetadataCustody and cap._anchor is original,
                    "transition_original_factory_changed")
                fd = frame.f_locals.get("fd")
                require(type(fd) is int, "transition_observer_error")
                state["native_fd"] = fd
                state["before_native"] = self._sample(state, fd)
            if event == "return" and frame.f_code is _NATIVE_CODE:
                self._event(state)
                values = frame.f_locals
                result, number = values.get("result"), values.get("number")
                state["native_result"] = result if type(result) is int and result in (0, -1) else "unavailable_or_invalid"
                state["native_errno_name"] = _ERRNOS.get(number) if type(number) is int else None
                state["immediate_after_native"] = self._sample(state, state["native_fd"])
            if event == "return" and phase == "immutable_guard_callback" and state["immediate_after_native"] is not None:
                self._event(state)
                sample = self._sample(state, state["native_fd"])
                if sample not in state["after_callbacks"]:
                    require(len(state["after_callbacks"]) < MAXIMUM_REFUSALS, "transition_observer_overflow")
                    state["after_callbacks"].append(sample)
            if event == "exception":
                require(type(argument) is tuple and len(argument) == 3, "transition_observer_error")
                controlled = _controlled(argument[1], state["catalogues"])
                if controlled is not None and not any(error is argument[1] for error in state["seen_errors"]):
                    self._event(state)
                    origin = frame.f_back
                    actual_phase = phase
                    if phase in {"immutable_require", "creator_require", "proof_require"} and origin is not None:
                        actual_phase = state["phases"].get(origin.f_code, phase)
                    row = {"role": controlled[0], "phase": actual_phase, "contract_code": controlled[1]}
                    require(len(state["refusals"]) < MAXIMUM_REFUSALS, "transition_observer_overflow")
                    state["seen_errors"].append(argument[1])
                    state["refusals"].append(row)
            return state["tracer"]
        except BaseException as error:
            controlled = _controlled(error, [(TransitionDiagnosticRefusal, _CODES, "observer")])
            state["observer_failure"] = controlled[1] if controlled is not None else "transition_observer_error"
            self._fail(state["observer_failure"])
            raise TransitionDiagnosticRefusal("REFUSED: " + state["observer_failure"]) from None

    def _event(self, state):
        # Ordinary require/helper calls must remain traced to observe an
        # exception, but are NOT native/callback/refusal observations. Counting
        # every internal call would exhaust the cap during a normal code audit.
        state["events"] += 1
        require(state["events"] <= MAXIMUM_EVENTS, "transition_observer_overflow")

    def __exit__(self, kind, error, traceback):
        # Restore tracing even if the caller replaced the public identity slot.
        record = _MINTED.get(id(self))
        if type(record) is not tuple or record[0] is not self:
            sys.settrace(None)
            raise TransitionDiagnosticRefusal("REFUSED: transition_binding_changed")
        state = record[2]
        latched = _FAILED.get(id(self))
        failure = latched[2] if type(latched) is tuple and latched[0] is self and latched[1] is record[1] else state["observer_failure"]
        try:
            identity = object.__getattribute__(self, "_identity")
        except AttributeError:
            identity = None
        if identity is not record[1]:
            failure = failure or "transition_binding_changed"
        if sys.gettrace() is not state["tracer"]:
            failure = failure or "transition_observer_lost"
        if immutable._native_set is not _NATIVE or immutable._native_set.__code__ is not _NATIVE_CODE:
            failure = failure or "transition_original_code_changed"
        if threading.get_ident() != state["thread"]:
            failure = failure or "transition_wrong_thread"
        if state["native_calls"] != 1 or state["immediate_after_native"] is None:
            failure = failure or "transition_missing_native_observation"
        sys.settrace(None)
        if failure is not None:
            self._fail(failure)
        state["observer_failure"] = failure
        state["closed"] = True
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
        report = {"schema": "si-immutable-transition-diagnostic-v1", "observer_complete": failure is None,
            "observer_failure": failure, "native_call_count": state["native_calls"],
            "native_result": state["native_result"], "native_errno_name": state["native_errno_name"],
            "before_native": state["before_native"], "immediate_after_native": immediate,
            "after_callbacks": state["after_callbacks"], "classification": classification,
            "first_controlled_refusal": state["refusals"][0] if state["refusals"] else None,
            "controlled_refusals": state["refusals"], "policy_sha256": hash_payload(policy()),
            "authority": authority()}
        state["report_raw"] = canonical_json(report)
        _ISSUED[id(self)] = self, record[1], state["report_raw"]
        if failure is not None:
            raise TransitionDiagnosticRefusal("REFUSED: " + failure) from None
        return False

    def report(self):
        state = self._state()
        issued = _ISSUED.get(id(self))
        require(type(issued) is tuple and issued[0] is self and issued[1] is self._identity
            and state["closed"] is True and state["report_raw"] is issued[2]
            and type(issued[2]) is str, "transition_not_closed")
        report = json.loads(state["report_raw"])
        return {"diagnostic": report, "diagnostic_sha256": hash_payload(report)}


def observe_original_transition(*, directory_fd, name, proof_binding=None):
    require(type(directory_fd) is int and type(name) is str and name == NAME,
        "transition_arguments_refused")
    info = os.fstat(directory_fd)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o700, "transition_arguments_refused")
    try:
        os.stat(NAME, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise TransitionDiagnosticRefusal("REFUSED: transition_arguments_refused")
    phases = dict(_PHASE_CODES)
    catalogues = [(immutable.ImmutableMetadataRefusal, immutable._CODES, "immutable"),
        (immutable.creator.NewMetadataRefusal, immutable.creator._CODES, "creator")]
    _proof_binding(proof_binding, phases, catalogues)
    value = object.__new__(ImmutableTransitionDiagnostic)
    value._identity = object()
    state = {"directory_fd": directory_fd, "entered": False, "closed": False, "thread": None,
        "tracer": None, "phases": phases, "catalogues": catalogues, "events": 0,
        "native_calls": 0, "native_fd": None, "original": None, "before_native": None,
        "immediate_after_native": None, "after_callbacks": [], "native_result": "unavailable_or_invalid",
        "native_errno_name": None, "refusals": [], "seen_errors": [],
        "observer_failure": None, "report_raw": None}
    _MINTED[id(value)] = value, value._identity, state
    return value
