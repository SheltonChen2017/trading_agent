"""One-shot transport and manifest-last persistence for nuisance calibration.

The production path is deliberately closed until an independently reviewed
owner public key is pinned for ``power_calibration_qc_execution``.  Building a
plan or review candidate performs no network, credential, outcome, or QC I/O.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import sys
import threading
import time
import weakref
from datetime import datetime
from pathlib import Path

from . import formal_submission_adapter as formal
from . import power_calibration_bridge as _power_bridge
from .formal_qc_transport import FormalQcTransport
from .owner_signature_authority import (
    OwnerSignatureAuthority,
    OwnerSignatureAuthorityError,
    require_power_calibration_execution_owner_signature,
)
from .power_calibration_bridge import (
    MAX_MANIFEST_BYTES,
    MAX_OUTPUT_SHARD_BYTES,
    OUTPUT_MANIFEST_SCHEMA,
    AcceptedRiskPowerCalibrationInput,
    AcceptedRiskPowerCalibrationOutput,
    CalibrationShardDescriptor,
    _descriptor_from_record,
    _path_fingerprint,
    _read_private,
    _strict_object,
    _write_private,
    canonical_json_bytes,
    load_accepted_risk_power_calibration_output,
    require_accepted_risk_power_calibration_input,
)
from .power_calibration_runtime import (
    PowerCalibrationQcProjection,
    require_power_calibration_qc_projection,
)


class PowerCalibrationSubmissionError(ValueError):
    """A calibration plan, claim, response, or archive is invalid."""


class PowerCalibrationSubmissionLocked(RuntimeError):
    """The single permit was spent and external state is ambiguous."""


REVIEW_FILENAME = "arv2-power-calibration-review-claim-v1.json"
PERMIT_FILENAME = "arv2-power-calibration-one-use-permit-v1.json"
MAX_CONTROL_BYTES = 1024 * 1024
COMPILE_POLLS = 120
STATUS_POLLS = 240
COMPILE_WAIT_SECONDS = 2
STATUS_WAIT_SECONDS = 30
_LAUNCH_AUTHORITIES: dict[int, tuple[object, ...]] = {}
_TERMINAL_AUTHORITIES: dict[int, tuple[object, ...]] = {}
_LAUNCH_AUTHORITIES_LOCK = threading.RLock()
_TERMINAL_AUTHORITIES_LOCK = threading.RLock()


@dataclasses.dataclass(frozen=True, slots=True)
class PowerCalibrationUploadEntry:
    role: str
    object_store_key: str
    content_sha256: str
    content_md5: str
    byte_count: int
    path: Path | None
    payload: bytes | None = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            "role": self.role, "object_store_key": self.object_store_key,
            "content_sha256": self.content_sha256,
            "content_md5": self.content_md5, "byte_count": self.byte_count,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class PowerCalibrationSubmissionPlan:
    plan_id: str
    plan_sha256: str
    organization_id: str
    project_name: str
    backtest_name: str
    input_id: str
    input_sha256: str
    projection_id: str
    projection_sha256: str
    output_manifest_key: str
    uploads: tuple[PowerCalibrationUploadEntry, ...]
    source_files: tuple[object, ...]
    review_directory: Path
    archive_directory: Path
    compile_poll_limit: int
    status_poll_limit: int
    maximum_backtest_submissions: int
    include_statistics: bool
    formal_outcome_evaluation: bool
    calibration_input: AcceptedRiskPowerCalibrationInput = dataclasses.field(repr=False)
    projection: PowerCalibrationQcProjection = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class PowerCalibrationReviewClaim:
    claim_id: str
    claim_sha256: str
    plan_id: str
    plan_sha256: str
    pin_path: Path
    pin_sha256: str
    pin_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class PowerCalibrationSubmissionPermit:
    permit_id: str
    permit_sha256: str
    plan_sha256: str
    claim_sha256: str
    owner_signature_sha256: str
    started_at_utc: str
    permit_path: Path
    permit_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PowerCalibrationLaunchReceipt:
    receipt_id: str
    receipt_sha256: str
    plan_sha256: str
    permit_sha256: str
    project_id: int
    compile_id: str
    backtest_id: str
    backtest_name: str
    initial_status: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PowerCalibrationTerminalStatus:
    receipt_id: str
    receipt_sha256: str
    launch_sha256: str
    project_id: int
    backtest_id: str
    status: str
    poll_count: int
    include_statistics: bool
    full_status_envelope_received_and_json_parsed: bool
    statistics_or_result_values_selected_or_inspected: bool
    discarded_values_retained_in_receipt_or_exported: bool


def _make_power_action_global_binding_guard():
    """Pin the complete in-process action namespace before it can mint."""

    expected_names: tuple[str, ...] = ()
    expected_globals: tuple[tuple[str, object, object], ...] = ()
    expected_external: tuple[tuple[object, str, object], ...] = ()
    expected_bridge_functions: tuple[object, ...] = ()
    expected_bridge_classes: tuple[object, ...] = ()
    expected_bridge_module_attributes: tuple[object, ...] = ()
    getpid = os.getpid
    error_type = PowerCalibrationSubmissionError
    authority_pid = getpid()
    module_globals = globals()
    bridge_module_globals = vars(_power_bridge)
    exact_type = type
    exact_tuple = tuple
    any_true = any
    length = len
    zip_strict = zip
    read_attribute = getattr
    read_vars = vars
    mapping_get = dict.get
    dict_type = dict
    list_type = list
    function_type = exact_type(lambda: None)
    code_type = exact_type((lambda: None).__code__)
    module_type = exact_type(sys)
    string_type = str
    missing = object()
    path_type = exact_type(Path())
    bridge_path_type = exact_type(_power_bridge.Path())
    guarded_bridge_classes = (
        _power_bridge.json.JSONDecoder,
        _power_bridge.json.JSONEncoder,
    )

    def transitive_code_names(root_code) -> tuple[str, ...]:
        pending = list_type((root_code,))
        seen_codes: tuple[object, ...] = ()
        names = list_type()
        while pending:
            code = pending.pop()
            if any_true(code is item for item in seen_codes):
                continue
            seen_codes = (*seen_codes, code)
            for name in code.co_names:
                if name not in names:
                    names.append(name)
            pending.extend(
                value
                for value in code.co_consts
                if exact_type(value) is code_type
            )
        return exact_tuple(names)
    excluded = (
        "_make_power_action_global_binding_guard",
        "_seal_power_action_global_bindings",
        "_require_power_action_global_bindings",
        "_bind_submission_return_authority",
        "_bind_terminal_persistence",
        "_transport_capability_minter",
        "_power_terminal_minter",
        "_execute_power_calibration_submission_once_impl",
        "_inspect_power_calibration_terminal_status_impl",
        "_persist_power_calibration_output_impl",
        "_require_power_calibration_launch_receipt_impl",
        "_require_power_calibration_terminal_status_impl",
        "_return_authority_register_launch",
        "_return_authority_current_launch",
        "_return_authority_register_terminal",
        "_return_authority_current_terminal",
        "_seal_submission_return_builder_callers",
        "_make_submission_return_authority",
        "_power_bridge",
    )
    external_specs = (
        (
            formal,
            (
                "_require_concrete_transport",
                "_transport_call",
                "_read_project_inventory",
                "_created_project",
                "_project_record",
                "_object_metadata_matches",
                "_read_files",
                "_success",
                "_compile_id",
                "_compile_state",
                "COMPILE_TERMINAL_STATES",
                "_created_backtest",
                "parse_statistics_free_backtest_list",
                "BACKTEST_TERMINAL_STATUSES",
            ),
        ),
        (hashlib, ("sha256",)),
        (base64, ("b64decode",)),
        (os, ("getpid", "mkdir")),
        (time, ("sleep",)),
        (
            _power_bridge,
            (
                "Path",
                "_path_fingerprint",
                "_write_private",
                "getattr",
                "hasattr",
                "len",
                "memoryview",
                "os",
                "stat",
                "type",
            ),
        ),
        (
            _power_bridge.os,
            (
                "O_CLOEXEC",
                "O_CREAT",
                "O_EXCL",
                "O_NOFOLLOW",
                "O_WRONLY",
                "close",
                "fsync",
                "getuid",
                "lstat",
                "open",
                "write",
            ),
        ),
        (
            _power_bridge.stat,
            ("S_IMODE", "S_ISDIR", "S_ISLNK", "S_ISREG"),
        ),
        (
            _power_bridge.Path,
            ("is_absolute",),
        ),
        (
            bridge_path_type,
            ("is_absolute",),
        ),
        (Path, ("is_absolute",)),
        (path_type, ("is_absolute",)),
    )

    def bridge_dependency_snapshot(roots):
        """Capture the bounded bridge parser/persistence call graph."""

        pending = list_type(roots)
        seen: tuple[object, ...] = ()
        functions = list_type()
        module_attributes = list_type()
        while pending:
            function = pending.pop()
            if (
                exact_type(function) is not function_type
                or function.__globals__ is not bridge_module_globals
                or any_true(function is item for item in seen)
            ):
                continue
            seen = (*seen, function)
            code = function.__code__
            names = transitive_code_names(code)
            closure = function.__closure__ or ()
            closure_values = exact_tuple(
                cell.cell_contents for cell in closure
            )
            builtin_namespace = function.__builtins__
            builtin_mapping = (
                builtin_namespace
                if exact_type(builtin_namespace) is dict_type
                else read_vars(builtin_namespace)
            )
            global_bindings = exact_tuple(
                (
                    name,
                    mapping_get(bridge_module_globals, name, missing),
                )
                for name in names
            )
            builtin_bindings = exact_tuple(
                (name, mapping_get(builtin_mapping, name, missing))
                for name, value in global_bindings
                if value is missing
            )
            functions.append((
                function,
                code,
                names,
                exact_tuple(code.co_freevars),
                closure_values,
                builtin_namespace,
                builtin_mapping,
                global_bindings,
                builtin_bindings,
            ))
            for _name, value in global_bindings:
                if (
                    exact_type(value) is function_type
                    and value.__globals__ is bridge_module_globals
                ):
                    pending.append(value)
                elif exact_type(value) is module_type:
                    namespace = read_vars(value)
                    for name in names:
                        if name in namespace:
                            module_attributes.append(
                                (value, namespace, name, namespace[name])
                            )
            for value in closure_values:
                if (
                    exact_type(value) is function_type
                    and value.__globals__ is bridge_module_globals
                ):
                    pending.append(value)
        classes = list_type()
        for value_class in guarded_bridge_classes:
            namespace = read_vars(value_class)
            names = exact_tuple(namespace)
            classes.append((
                value_class,
                names,
                exact_tuple((name, namespace[name]) for name in names),
            ))
        return (
            exact_tuple(functions),
            exact_tuple(classes),
            exact_tuple(module_attributes),
        )

    def bridge_dependencies_are_current() -> bool:
        for (
            function,
            code,
            names,
            freevars,
            closure_values,
            builtin_namespace,
            builtin_mapping,
            global_bindings,
            builtin_bindings,
        ) in expected_bridge_functions:
            closure = function.__closure__ or ()
            current_closure_values = exact_tuple(
                cell.cell_contents for cell in closure
            )
            if (
                function.__code__ is not code
                or function.__globals__ is not bridge_module_globals
                or transitive_code_names(function.__code__) != names
                or exact_tuple(function.__code__.co_freevars) != freevars
                or length(current_closure_values) != length(closure_values)
                or any_true(
                    current is not expected
                    for current, expected
                    in zip_strict(
                        current_closure_values,
                        closure_values,
                        strict=True,
                    )
                )
                or function.__builtins__ is not builtin_namespace
                or (
                    builtin_namespace
                    if exact_type(builtin_namespace) is dict_type
                    else read_vars(builtin_namespace)
                )
                is not builtin_mapping
                or any_true(
                    mapping_get(bridge_module_globals, name, missing)
                    is not expected
                    for name, expected in global_bindings
                )
                or any_true(
                    mapping_get(builtin_mapping, name, missing)
                    is not expected
                    for name, expected in builtin_bindings
                )
            ):
                return False
        for value_class, names, bindings in expected_bridge_classes:
            namespace = read_vars(value_class)
            if exact_tuple(namespace) != names or any_true(
                namespace[name] is not expected
                for name, expected in bindings
            ):
                return False
        return not any_true(
            read_vars(namespace) is not namespace_vars
            or mapping_get(namespace_vars, name, missing) is not expected
            for namespace, namespace_vars, name, expected
            in expected_bridge_module_attributes
        )

    def non_dunder_names() -> tuple[str, ...]:
        keys = exact_tuple(module_globals)
        if any_true(exact_type(name) is not string_type for name in keys):
            raise error_type("calibration action global census changed")
        return exact_tuple(
            name
            for name in keys
            if not name.startswith("__") and name not in excluded
        )

    def seal() -> None:
        nonlocal expected_names, expected_globals, expected_external
        nonlocal expected_bridge_functions, expected_bridge_classes
        nonlocal expected_bridge_module_attributes
        if expected_globals or expected_external:
            raise error_type(
                "calibration action globals were already sealed"
            )
        expected_names = non_dunder_names()
        expected_globals = exact_tuple(
            (
                name,
                exact_type(module_globals[name]),
                module_globals[name],
            )
            for name in expected_names
        )
        expected_external = exact_tuple(
            (namespace, name, read_attribute(namespace, name, missing))
            for namespace, names in external_specs
            for name in names
        )
        (
            expected_bridge_functions,
            expected_bridge_classes,
            expected_bridge_module_attributes,
        ) = bridge_dependency_snapshot((
            _strict_object,
            _descriptor_from_record,
            _write_private,
            load_accepted_risk_power_calibration_output,
        ))

    def require(kind: str) -> None:
        if getpid() != authority_pid or not expected_globals:
            raise error_type(
                f"calibration {kind} action global authority changed"
            )
        if non_dunder_names() != expected_names or any_true(
            exact_type(module_globals.get(name, missing)) is not expected_type
            or module_globals.get(name, missing) is not expected
            for name, expected_type, expected in expected_globals
        ):
            raise error_type(
                f"calibration {kind} action global authority changed"
            )
        if not bridge_dependencies_are_current() or any_true(
            read_attribute(namespace, name, missing) is not value
            for namespace, name, value in expected_external
        ):
            raise error_type(
                f"calibration {kind} action dependency authority changed"
            )

    return seal, require


(
    _seal_power_action_global_bindings,
    _require_power_action_global_bindings,
) = _make_power_action_global_binding_guard()


def _make_submission_return_authority(binding_guard):
    """Create provenance-bound launch and terminal return authorities.

    The public dictionaries are bounded-state inspection surfaces only.  The
    authentic entries live in an immutable tuple replaced on every mutation,
    so ordinary closure reflection cannot inject or reseal authority.  The
    two registrar closures additionally accept calls only from the exact QC
    action implementations sealed below after those functions exist.
    """

    records: tuple[tuple[str, int, tuple[object, ...]], ...] = ()
    register_callers: tuple[
        tuple[
            str,
            tuple[
                tuple[object, int, str, tuple[tuple[str, object], ...]], ...
            ],
        ],
        ...,
    ] = ()
    rlock_factory = threading.RLock
    lock = rlock_factory()
    getpid = os.getpid
    realpath = os.path.realpath
    getframe = sys._getframe
    authority_pid = getpid()
    module_name = __name__
    module_path = realpath(__file__)
    function_type = type(lambda: None)

    def public_registry(kind: str) -> dict[int, tuple[object, ...]]:
        registry = (
            _LAUNCH_AUTHORITIES if kind == "launch"
            else _TERMINAL_AUTHORITIES if kind == "terminal"
            else None
        )
        if type(registry) is not dict:
            raise PowerCalibrationSubmissionError(
                "calibration return-authority public registry changed"
            )
        return registry

    def expected_caller(kind: str, frame: object) -> None:
        match = next(
            (item for item in register_callers if item[0] == kind),
            None,
        )
        chain = () if match is None else match[1]
        valid = bool(chain) and getpid() == authority_pid
        current_frame = frame
        for code, globals_id, path, bindings in chain:
            if (
                not valid
                or current_frame is None
                or current_frame.f_code is not code
                or id(current_frame.f_globals) != globals_id
                or realpath(current_frame.f_code.co_filename) != path
                or tuple(current_frame.f_code.co_freevars)
                != tuple(name for name, _value in bindings)
                or any(
                    current_frame.f_locals.get(name) is not value
                    for name, value in bindings
                )
            ):
                valid = False
                break
            current_frame = current_frame.f_back
        if not valid:
            raise PowerCalibrationSubmissionError(
                "calibration return-authority registration caller changed"
            )

    def forget(kind: str, identity: int, reference: object) -> None:
        nonlocal records
        with lock:
            matching = next(
                (
                    item for item in records
                    if item[0] == kind and item[1] == identity
                ),
                None,
            )
            if matching is not None and matching[2][0] is reference:
                records = tuple(item for item in records if item is not matching)
                public = public_registry(kind)
                if public.get(identity) is matching[2]:
                    public.pop(identity, None)

    def register(
        kind: str,
        caller_frame: object,
        value: object,
        *lineage: object,
    ) -> None:
        nonlocal records
        expected_caller(kind, caller_frame)
        identity = id(value)
        reference = weakref.ref(
            value,
            lambda ref, category=kind, key=identity: forget(category, key, ref),
        )
        entry = (reference, *lineage, getpid())
        with lock:
            public = public_registry(kind)
            if (
                any(item[0] == kind and item[1] == identity for item in records)
                or identity in public
            ):
                raise PowerCalibrationSubmissionError(
                    "calibration return-authority identity was reused"
                )
            records = (*records, (kind, identity, entry))
            public[identity] = entry

    def current(kind: str, value: object) -> tuple[object, ...] | None:
        nonlocal records
        identity = id(value)
        with lock:
            matching = next(
                (
                    item for item in records
                    if item[0] == kind and item[1] == identity
                ),
                None,
            )
            private = None if matching is None else matching[2]
            public_records = public_registry(kind)
            public = public_records.get(identity)
            if (
                private is None
                or public is not private
                or private[0]() is not value
                or private[-1] != getpid()
            ):
                if matching is not None:
                    records = tuple(item for item in records if item is not matching)
                public_records.pop(identity, None)
                return None
            return private

    def seal_builder_callers(
        *, execute_impl: object, inspect_impl: object,
        execute_public: object, inspect_public: object,
    ) -> None:
        nonlocal register_callers
        specifications = (
            (
                "launch",
                (
                    (execute_impl, "_execute_power_calibration_submission_once_impl"),
                    (
                        execute_public,
                        "execute_power_calibration_submission_once",
                    ),
                ),
            ),
            (
                "terminal",
                (
                    (inspect_impl, "_inspect_power_calibration_terminal_status_impl"),
                    (
                        inspect_public,
                        "inspect_power_calibration_terminal_status",
                    ),
                ),
            ),
        )
        if register_callers:
            raise PowerCalibrationSubmissionError(
                "calibration return-authority provenance was already sealed"
            )
        sealed = ()
        for kind, functions in specifications:
            chain = ()
            for function, expected_name in functions:
                if (
                    type(function) is not function_type
                    or function.__module__ != module_name
                    or function.__globals__ is not globals()
                    or function.__code__.co_name != expected_name
                    or realpath(function.__code__.co_filename) != module_path
                ):
                    raise PowerCalibrationSubmissionError(
                        "calibration return-authority provenance changed"
                    )
                closure = function.__closure__ or ()
                if len(closure) != len(function.__code__.co_freevars):
                    raise PowerCalibrationSubmissionError(
                        "calibration return-authority closure changed"
                    )
                chain = (*chain, (
                    function.__code__,
                    id(function.__globals__),
                    module_path,
                    tuple(
                        (name, cell.cell_contents)
                        for name, cell in zip(
                            function.__code__.co_freevars,
                            closure,
                            strict=True,
                        )
                    ),
                ))
            sealed = (*sealed, (kind, chain))
        register_callers = sealed

    def register_launch(
        value: PowerCalibrationLaunchReceipt,
        *, plan: PowerCalibrationSubmissionPlan,
        permit: PowerCalibrationSubmissionPermit,
        review_claim: PowerCalibrationReviewClaim,
        owner_signature: OwnerSignatureAuthority,
    ) -> None:
        binding_guard("launch registration")
        caller = getframe(1)
        expected_caller("launch", caller)
        register(
            "launch",
            caller,
            value,
            plan,
            permit,
            review_claim,
            owner_signature,
            canonical_json_bytes(_launch_record(value)),
        )

    def current_launch(value: PowerCalibrationLaunchReceipt):
        return current("launch", value)

    def register_terminal(
        value: PowerCalibrationTerminalStatus,
        *, plan: PowerCalibrationSubmissionPlan,
        launch: PowerCalibrationLaunchReceipt,
        permit: PowerCalibrationSubmissionPermit,
        review_claim: PowerCalibrationReviewClaim,
        owner_signature: OwnerSignatureAuthority,
    ) -> None:
        binding_guard("terminal registration")
        caller = getframe(1)
        expected_caller("terminal", caller)
        register(
            "terminal",
            caller,
            value,
            plan,
            launch,
            permit,
            review_claim,
            owner_signature,
            canonical_json_bytes(_terminal_record(value)),
        )

    def current_terminal(value: PowerCalibrationTerminalStatus):
        return current("terminal", value)

    def reset_private_after_fork() -> None:
        nonlocal lock, records
        records = ()
        lock = rlock_factory()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_private_after_fork)
    return (
        seal_builder_callers,
        register_launch,
        current_launch,
        register_terminal,
        current_terminal,
    )


def _reset_submission_authorities_after_fork() -> None:
    global _LAUNCH_AUTHORITIES, _TERMINAL_AUTHORITIES
    global _LAUNCH_AUTHORITIES_LOCK, _TERMINAL_AUTHORITIES_LOCK
    _LAUNCH_AUTHORITIES = {}
    _TERMINAL_AUTHORITIES = {}
    _LAUNCH_AUTHORITIES_LOCK = threading.RLock()
    _TERMINAL_AUTHORITIES_LOCK = threading.RLock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_submission_authorities_after_fork)


(
    _seal_submission_return_builder_callers,
    _return_authority_register_launch,
    _return_authority_current_launch,
    _return_authority_register_terminal,
    _return_authority_current_terminal,
) = _make_submission_return_authority(_require_power_action_global_bindings)


def _safe_text(value: object, name: str) -> str:
    if (
        type(value) is not str or not value or len(value) > 1024
        or "\x00" in value or ".." in value.split("/")
    ):
        raise PowerCalibrationSubmissionError(f"{name} is not safe text")
    return value


def _utc(value: object) -> str:
    if type(value) is not str or not value.endswith("Z"):
        raise PowerCalibrationSubmissionError("started_at_utc is not canonical")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PowerCalibrationSubmissionError("started_at_utc is not canonical") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise PowerCalibrationSubmissionError("started_at_utc is not canonical")
    return value


def _entry_payload(entry: PowerCalibrationUploadEntry) -> bytes:
    if entry.payload is not None:
        payload = entry.payload
    elif entry.path is not None:
        payload, _ = _read_private(entry.path, entry.byte_count)
    else:
        raise PowerCalibrationSubmissionError("upload entry has no source")
    if (
        len(payload) != entry.byte_count
        or hashlib.sha256(payload).hexdigest() != entry.content_sha256
        or hashlib.md5(payload, usedforsecurity=False).hexdigest() != entry.content_md5
    ):
        raise PowerCalibrationSubmissionError("upload entry changed")
    return payload


def _entry(role: str, key: str, payload: bytes | None, path: Path | None) -> PowerCalibrationUploadEntry:
    exact = payload
    if exact is None and path is not None:
        exact, _ = _read_private(path, MAX_OUTPUT_SHARD_BYTES * 8)
    if type(exact) is not bytes or not exact:
        raise PowerCalibrationSubmissionError("upload entry is empty")
    return PowerCalibrationUploadEntry(
        role=role, object_store_key=_safe_text(key, "Object Store key"),
        content_sha256=hashlib.sha256(exact).hexdigest(),
        content_md5=hashlib.md5(exact, usedforsecurity=False).hexdigest(),
        byte_count=len(exact), path=path, payload=payload,
    )


def _plan_record(value: PowerCalibrationSubmissionPlan) -> dict[str, object]:
    return {
        "schema": "arv2-power-calibration-submission-plan-v1",
        "organization_id_sha256": hashlib.sha256(
            value.organization_id.encode("utf-8")
        ).hexdigest(),
        "project_name": value.project_name, "backtest_name": value.backtest_name,
        "input_id": value.input_id, "input_sha256": value.input_sha256,
        "projection_id": value.projection_id,
        "projection_sha256": value.projection_sha256,
        "output_manifest_key": value.output_manifest_key,
        "uploads": [item.to_record() for item in value.uploads],
        "source_files": [item.to_record() for item in value.source_files],
        "review_directory": str(value.review_directory),
        "archive_directory": str(value.archive_directory),
        "compile_poll_limit": value.compile_poll_limit,
        "status_poll_limit": value.status_poll_limit,
        "maximum_backtest_submissions": value.maximum_backtest_submissions,
        "include_statistics": value.include_statistics,
        "formal_outcome_evaluation": value.formal_outcome_evaluation,
    }


def build_power_calibration_submission_plan(
    *, calibration_input: AcceptedRiskPowerCalibrationInput,
    projection: PowerCalibrationQcProjection, organization_id: str,
    review_directory: Path, archive_directory: Path,
) -> PowerCalibrationSubmissionPlan:
    calibration_input = require_accepted_risk_power_calibration_input(calibration_input)
    projection = require_power_calibration_qc_projection(projection)
    if (
        projection.input_id != calibration_input.input_id
        or projection.input_sha256 != calibration_input.input_sha256
    ):
        raise PowerCalibrationSubmissionError("projection and input differ")
    _safe_text(organization_id, "organization id")
    _path_fingerprint(review_directory, directory=True)
    if archive_directory.parent != review_directory or archive_directory.exists():
        raise PowerCalibrationSubmissionError("archive must be a new direct child of review directory")
    uploads = []
    for path, descriptor in zip(
        calibration_input.shard_paths, calibration_input.shard_descriptors,
        strict=True,
    ):
        uploads.append(_entry("input_shard", descriptor.object_store_key, None, path))
    # The manifest is the commit marker.  It is deliberately the last remote
    # write so a partial upload cannot advertise a usable input inventory.
    uploads.append(_entry(
        "input_manifest", projection.input_manifest_key,
        calibration_input.manifest_bytes, None,
    ))
    placeholder = object.__new__(PowerCalibrationSubmissionPlan)
    values = {
        "plan_id": "", "plan_sha256": "", "organization_id": organization_id,
        "project_name": projection.project_name,
        "backtest_name": projection.backtest_name,
        "input_id": calibration_input.input_id,
        "input_sha256": calibration_input.input_sha256,
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "output_manifest_key": projection.output_manifest_key,
        "uploads": tuple(uploads), "source_files": projection.sources,
        "review_directory": review_directory,
        "archive_directory": archive_directory,
        "compile_poll_limit": COMPILE_POLLS, "status_poll_limit": STATUS_POLLS,
        "maximum_backtest_submissions": 1, "include_statistics": False,
        "formal_outcome_evaluation": False,
        "calibration_input": calibration_input, "projection": projection,
    }
    for name, item in values.items():
        object.__setattr__(placeholder, name, item)
    digest = hashlib.sha256(canonical_json_bytes(_plan_record(placeholder))).hexdigest()
    object.__setattr__(placeholder, "plan_id", f"arv2-power-calibration-plan-{digest[:24]}")
    object.__setattr__(placeholder, "plan_sha256", digest)
    return require_power_calibration_submission_plan(placeholder)


def require_power_calibration_submission_plan(
    value: PowerCalibrationSubmissionPlan,
) -> PowerCalibrationSubmissionPlan:
    if type(value) is not PowerCalibrationSubmissionPlan:
        raise PowerCalibrationSubmissionError("calibration plan changed type")
    require_accepted_risk_power_calibration_input(value.calibration_input)
    require_power_calibration_qc_projection(value.projection)
    _path_fingerprint(value.review_directory, directory=True)
    seed = _plan_record(value)
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    if (
        value.plan_id != f"arv2-power-calibration-plan-{digest[:24]}"
        or value.plan_sha256 != digest or value.maximum_backtest_submissions != 1
        or value.include_statistics is not False
        or value.formal_outcome_evaluation is not False
        or value.projection.input_id != value.input_id
        or value.calibration_input.input_id != value.input_id
        or value.source_files is not value.projection.sources
        or not value.uploads
        or value.uploads[-1].role != "input_manifest"
        or any(item.role != "input_shard" for item in value.uploads[:-1])
    ):
        raise PowerCalibrationSubmissionError("calibration plan changed")
    for entry in value.uploads:
        _entry_payload(entry)
    return value


def _claim_document(plan: PowerCalibrationSubmissionPlan) -> dict[str, object]:
    require_power_calibration_submission_plan(plan)
    seed = {
        "schema": "arv2-power-calibration-review-claim-v1",
        "plan_id": plan.plan_id, "plan_sha256": plan.plan_sha256,
        "review_disposition": "GO", "independent_review_complete": True,
        "private_review_pin": True, "maximum_backtest_submissions": 1,
        "formal_outcome_evaluation": False, "result_read": False,
        "retry_after_ambiguity": False,
    }
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    return {
        **seed, "claim_id": f"arv2-power-calibration-review-{digest[:24]}",
        "claim_sha256": digest,
    }


def render_power_calibration_review_claim_candidate(
    plan: PowerCalibrationSubmissionPlan,
) -> bytes:
    return canonical_json_bytes(_claim_document(plan))


def load_power_calibration_review_claim(
    plan: PowerCalibrationSubmissionPlan,
) -> PowerCalibrationReviewClaim:
    expected = render_power_calibration_review_claim_candidate(plan)
    path = plan.review_directory / REVIEW_FILENAME
    payload, _ = _read_private(path, MAX_CONTROL_BYTES)
    if payload != expected:
        raise PowerCalibrationSubmissionError("calibration review claim changed")
    raw = _claim_document(plan)
    return PowerCalibrationReviewClaim(
        claim_id=raw["claim_id"], claim_sha256=raw["claim_sha256"],
        plan_id=plan.plan_id, plan_sha256=plan.plan_sha256,
        pin_path=path, pin_sha256=hashlib.sha256(payload).hexdigest(),
        pin_bytes=payload,
    )


def require_power_calibration_review_claim(value, plan):
    if type(value) is not PowerCalibrationReviewClaim:
        raise PowerCalibrationSubmissionError("exact calibration review claim required")
    if load_power_calibration_review_claim(plan) != value:
        raise PowerCalibrationSubmissionError("calibration review claim changed")
    return value


def render_power_calibration_execution_authority_candidate(plan, claim) -> bytes:
    require_power_calibration_submission_plan(plan)
    require_power_calibration_review_claim(claim, plan)
    return canonical_json_bytes({
        "schema": "arv2-power-calibration-execution-authority-v1",
        "plan_id": plan.plan_id, "plan_sha256": plan.plan_sha256,
        "claim_id": claim.claim_id, "claim_sha256": claim.claim_sha256,
        "review_pin_sha256": claim.pin_sha256,
        "project_name": plan.project_name, "backtest_name": plan.backtest_name,
        "input_id": plan.input_id, "input_sha256": plan.input_sha256,
        "projection_id": plan.projection_id,
        "projection_sha256": plan.projection_sha256,
        "output_manifest_key": plan.output_manifest_key,
        "actions": [
            "authenticate", "projects/read", "projects/create_once",
            "object/set_and_properties_exact_inputs", "files/create_exact_sources",
            "files/update_default_main_if_present",
            "compile/create_once", "backtests/create_once",
            "backtests/list_status_only", "object/read_calibration_outputs_only",
        ],
        "maximum_backtest_submissions": 1, "include_statistics": False,
        "formal_outcome_evaluation": False, "retry_after_ambiguity": False,
    })


def _preflight(plan, claim, owner_signature):
    payload = render_power_calibration_execution_authority_candidate(plan, claim)
    try:
        require_power_calibration_execution_owner_signature(
            owner_signature, authority_payload=payload
        )
    except OwnerSignatureAuthorityError as exc:
        raise PowerCalibrationSubmissionError(
            "distinct owner power-calibration signature is unavailable"
        ) from exc
    return payload


def _spend(plan, claim, owner_signature, started_at_utc):
    _utc(started_at_utc)
    seed = {
        "schema": "arv2-power-calibration-one-use-permit-v1",
        "plan_sha256": plan.plan_sha256, "claim_sha256": claim.claim_sha256,
        "owner_signature_sha256": owner_signature.authority_sha256,
        "started_at_utc": started_at_utc, "attempt_count": 1,
        "retry_authorized": False,
    }
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    raw = {
        **seed, "permit_id": f"arv2-power-calibration-permit-{digest[:24]}",
        "permit_sha256": digest,
    }
    payload = canonical_json_bytes(raw)
    path = plan.review_directory / PERMIT_FILENAME
    try:
        _write_private(path, payload)
    except Exception as exc:
        raise PowerCalibrationSubmissionLocked("calibration permit is already spent") from exc
    return PowerCalibrationSubmissionPermit(
        permit_id=raw["permit_id"], permit_sha256=digest,
        plan_sha256=plan.plan_sha256, claim_sha256=claim.claim_sha256,
        owner_signature_sha256=owner_signature.authority_sha256,
        started_at_utc=started_at_utc, permit_path=path, permit_bytes=payload,
    )


def require_power_calibration_submission_permit(
    value: PowerCalibrationSubmissionPermit,
    *, plan: PowerCalibrationSubmissionPlan,
    review_claim: PowerCalibrationReviewClaim,
    owner_signature: OwnerSignatureAuthority,
) -> PowerCalibrationSubmissionPermit:
    require_power_calibration_submission_plan(plan)
    require_power_calibration_review_claim(review_claim, plan)
    _preflight(plan, review_claim, owner_signature)
    if type(value) is not PowerCalibrationSubmissionPermit:
        raise PowerCalibrationSubmissionError("exact calibration permit required")
    _utc(value.started_at_utc)
    seed = {
        "schema": "arv2-power-calibration-one-use-permit-v1",
        "plan_sha256": plan.plan_sha256,
        "claim_sha256": review_claim.claim_sha256,
        "owner_signature_sha256": owner_signature.authority_sha256,
        "started_at_utc": value.started_at_utc,
        "attempt_count": 1,
        "retry_authorized": False,
    }
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    expected = canonical_json_bytes({
        **seed,
        "permit_id": f"arv2-power-calibration-permit-{digest[:24]}",
        "permit_sha256": digest,
    })
    payload, _ = _read_private(value.permit_path, MAX_CONTROL_BYTES)
    if (
        value.permit_path != plan.review_directory / PERMIT_FILENAME
        or value.permit_id != f"arv2-power-calibration-permit-{digest[:24]}"
        or value.permit_sha256 != digest
        or value.plan_sha256 != plan.plan_sha256
        or value.claim_sha256 != review_claim.claim_sha256
        or value.owner_signature_sha256 != owner_signature.authority_sha256
        or value.permit_bytes != expected
        or payload != expected
    ):
        raise PowerCalibrationSubmissionError("calibration permit changed")
    return value


def _launch_record(
    value: PowerCalibrationLaunchReceipt,
) -> dict[str, object]:
    return {
        "plan_sha256": value.plan_sha256,
        "permit_sha256": value.permit_sha256,
        "project_id": value.project_id,
        "compile_id": value.compile_id,
        "backtest_id": value.backtest_id,
        "backtest_name": value.backtest_name,
        "initial_status": value.initial_status,
    }


def _require_power_calibration_launch_receipt_impl(
    value: PowerCalibrationLaunchReceipt,
    *, plan: PowerCalibrationSubmissionPlan,
    permit: PowerCalibrationSubmissionPermit,
    review_claim: PowerCalibrationReviewClaim,
    owner_signature: OwnerSignatureAuthority,
    _authority_current: object,
) -> PowerCalibrationLaunchReceipt:
    require_power_calibration_submission_plan(plan)
    if type(value) is not PowerCalibrationLaunchReceipt:
        raise PowerCalibrationSubmissionError("exact calibration launch required")
    require_power_calibration_submission_permit(
        permit,
        plan=plan,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )
    registered = _authority_current(value)
    if (
        registered is None
        or registered[0]() is not value
        or registered[1] is not plan
        or registered[2] is not permit
        or registered[3] is not review_claim
        or registered[4] is not owner_signature
        or registered[6] != os.getpid()
    ):
        raise PowerCalibrationSubmissionError(
            "calibration launch lacks process-return authority"
        )
    seed = _launch_record(value)
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    if (
        type(value.project_id) is not int or value.project_id <= 0
        or value.plan_sha256 != plan.plan_sha256
        or value.permit_sha256 != permit.permit_sha256
        or value.backtest_name != plan.backtest_name
        or value.receipt_id != f"arv2-power-calibration-launch-{digest[:24]}"
        or value.receipt_sha256 != digest
        or registered[5] != canonical_json_bytes(seed)
    ):
        raise PowerCalibrationSubmissionError("calibration launch changed")
    _safe_text(value.compile_id, "compile id")
    _safe_text(value.backtest_id, "backtest id")
    _safe_text(value.initial_status, "initial status")
    return value


def _terminal_record(value: PowerCalibrationTerminalStatus) -> dict[str, object]:
    return {
        "launch_sha256": value.launch_sha256,
        "project_id": value.project_id,
        "backtest_id": value.backtest_id,
        "status": value.status,
        "poll_count": value.poll_count,
        "include_statistics": value.include_statistics,
        "full_status_envelope_received_and_json_parsed": (
            value.full_status_envelope_received_and_json_parsed
        ),
        "statistics_or_result_values_selected_or_inspected": (
            value.statistics_or_result_values_selected_or_inspected
        ),
        "discarded_values_retained_in_receipt_or_exported": (
            value.discarded_values_retained_in_receipt_or_exported
        ),
    }


def _require_power_calibration_terminal_status_impl(
    value: PowerCalibrationTerminalStatus,
    *, plan: PowerCalibrationSubmissionPlan,
    launch: PowerCalibrationLaunchReceipt,
    permit: PowerCalibrationSubmissionPermit,
    review_claim: PowerCalibrationReviewClaim,
    owner_signature: OwnerSignatureAuthority,
    _authority_current: object,
) -> PowerCalibrationTerminalStatus:
    require_power_calibration_submission_plan(plan)
    if type(value) is not PowerCalibrationTerminalStatus:
        raise PowerCalibrationSubmissionError("exact calibration status required")
    require_power_calibration_launch_receipt(
        launch,
        plan=plan,
        permit=permit,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )
    registered = _authority_current(value)
    if (
        registered is None
        or registered[0]() is not value
        or registered[1] is not plan
        or registered[2] is not launch
        or registered[3] is not permit
        or registered[4] is not review_claim
        or registered[5] is not owner_signature
        or registered[7] != os.getpid()
    ):
        raise PowerCalibrationSubmissionError(
            "calibration terminal status lacks process-return authority"
        )
    seed = _terminal_record(value)
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    if (
        value.launch_sha256 != launch.receipt_sha256
        or value.project_id != launch.project_id
        or value.backtest_id != launch.backtest_id
        or type(value.poll_count) is not int
        or not 1 <= value.poll_count <= plan.status_poll_limit
        or value.include_statistics is not False
        or value.full_status_envelope_received_and_json_parsed is not True
        or value.statistics_or_result_values_selected_or_inspected is not False
        or value.discarded_values_retained_in_receipt_or_exported is not False
        or value.receipt_id != f"arv2-power-calibration-status-{digest[:24]}"
        or value.receipt_sha256 != digest
        or registered[6] != canonical_json_bytes(seed)
    ):
        raise PowerCalibrationSubmissionError("calibration terminal status changed")
    _safe_text(value.status, "terminal status")
    return value


def _call(client, capability, method, *args):
    return formal._transport_call(client, capability, method, *args)


def _execute_power_calibration_submission_once_impl(
    *, plan: PowerCalibrationSubmissionPlan,
    review_claim: PowerCalibrationReviewClaim,
    owner_signature: OwnerSignatureAuthority | None,
    client: FormalQcTransport, started_at_utc: str,
    _authority_register: object,
    _transport_capability_minter: object,
) -> tuple[PowerCalibrationSubmissionPermit, PowerCalibrationLaunchReceipt]:
    require_power_calibration_submission_plan(plan)
    require_power_calibration_review_claim(review_claim, plan)
    _preflight(plan, review_claim, owner_signature)
    formal._require_concrete_transport(client)
    permit = _spend(plan, review_claim, owner_signature, started_at_utc)
    require_power_calibration_submission_permit(
        permit, plan=plan, review_claim=review_claim,
        owner_signature=owner_signature,
    )
    capability = _transport_capability_minter(
        transport=client, scope="submission",
        binding_record={
            "schema": "arv2-power-calibration-submission-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
        },
        call_budget={
            "authenticate": 1, "projects/read": 2, "projects/create": 1,
            "object/set": len(plan.uploads),
            "object/properties": len(plan.uploads), "files/read": 2,
            "files/create": len(plan.source_files), "compile/create": 1,
            "files/update": len(plan.source_files),
            "compile/read": plan.compile_poll_limit, "backtests/create": 1,
        },
    )
    try:
        _call(client, capability, "_request_json", "authenticate", {})
        inventory = formal._read_project_inventory(
            _call(client, capability, "_request_json", "projects/read", {})
        )
        if any(item.get("name") == plan.project_name for item in inventory):
            raise PowerCalibrationSubmissionError("exact calibration project already exists")
        created = formal._created_project(
            _call(client, capability, "_request_json", "projects/create", {
                "name": plan.project_name, "language": "Py",
            }), name=plan.project_name, organization_id=plan.organization_id,
        )
        project_id = int(created["projectId"])
        exact = formal._read_project_inventory(
            _call(client, capability, "_request_json", "projects/read", {
                "projectId": project_id,
            })
        )
        if len(exact) != 1:
            raise PowerCalibrationSubmissionError("created project is ambiguous")
        formal._project_record(
            exact[0], name=plan.project_name, organization_id=plan.organization_id
        )
        for entry in plan.uploads:
            payload = _entry_payload(entry)
            _call(
                client, capability, "_set_object_multipart",
                plan.organization_id, entry.object_store_key, payload,
            )
            formal._object_metadata_matches(
                _call(
                    client, capability, "_read_object_properties",
                    plan.organization_id, entry.object_store_key,
                ), entry,
            )
        existing = formal._read_files(
            _call(
                client, capability, "_request_json", "files/read",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        if not set(existing).issubset({"main.py"}):
            raise PowerCalibrationSubmissionError(
                "new calibration project contains an unexpected source"
            )
        for source in plan.source_files:
            endpoint = (
                "files/update"
                if source.project_path in existing else "files/create"
            )
            formal._success(_call(client, capability, "_request_json", endpoint, {
                "projectId": project_id, "name": source.project_path,
                "content": source.content.decode("utf-8"),
            }), frozenset({"success", "errors", "messages"}), endpoint)
        files = formal._read_files(
            _call(
                client, capability, "_request_json", "files/read",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        expected_sources = {
            item.project_path: item for item in plan.source_files
        }
        if set(files) != set(expected_sources):
            raise PowerCalibrationSubmissionError("calibration source inventory changed")
        for path, source in expected_sources.items():
            try:
                payload = files[path].encode("utf-8")
            except UnicodeError as exc:
                raise PowerCalibrationSubmissionError(
                    "calibration source readback is not UTF-8"
                ) from exc
            if (
                payload != source.content
                or len(payload) != source.byte_count
                or hashlib.sha256(payload).hexdigest() != source.content_sha256
            ):
                raise PowerCalibrationSubmissionError(
                    "calibration source readback changed"
                )
        compile_id = formal._compile_id(_call(
            client, capability, "_request_json", "compile/create", {"projectId": project_id}
        ), expected_project_id=project_id)
        compile_state = ""
        for index in range(plan.compile_poll_limit):
            compile_state = formal._compile_state(_call(
                client, capability, "_request_json", "compile/read", {
                    "projectId": project_id, "compileId": compile_id,
                }), compile_id)
            if compile_state in formal.COMPILE_TERMINAL_STATES:
                break
            if index + 1 == plan.compile_poll_limit:
                raise PowerCalibrationSubmissionError("compile polling exhausted")
            time.sleep(COMPILE_WAIT_SECONDS)
        if compile_state != "BuildSuccess":
            raise PowerCalibrationSubmissionError("calibration project did not compile")
        backtest_id, initial = formal._created_backtest(_call(
            client, capability, "_request_json", "backtests/create", {
                "projectId": project_id, "compileId": compile_id,
                "backtestName": plan.backtest_name,
            }), project_id=project_id, name=plan.backtest_name)
        seed = {
            "plan_sha256": plan.plan_sha256, "permit_sha256": permit.permit_sha256,
            "project_id": project_id, "compile_id": compile_id,
            "backtest_id": backtest_id, "backtest_name": plan.backtest_name,
            "initial_status": initial,
        }
        digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
        launch = PowerCalibrationLaunchReceipt(
            receipt_id=f"arv2-power-calibration-launch-{digest[:24]}",
            receipt_sha256=digest, **seed,
        )
        _authority_register(
            launch,
            plan=plan,
            permit=permit,
            review_claim=review_claim,
            owner_signature=owner_signature,
        )
        require_power_calibration_launch_receipt(
            launch,
            plan=plan,
            permit=permit,
            review_claim=review_claim,
            owner_signature=owner_signature,
        )
        return permit, launch
    except Exception as exc:
        raise PowerCalibrationSubmissionLocked(
            "calibration submission became ambiguous; permit remains consumed"
        ) from exc


def _inspect_power_calibration_terminal_status_impl(
    *, plan, review_claim, owner_signature, permit, launch, client,
    _authority_register,
    _transport_capability_minter,
) -> PowerCalibrationTerminalStatus:
    require_power_calibration_submission_permit(
        permit, plan=plan, review_claim=review_claim,
        owner_signature=owner_signature,
    )
    require_power_calibration_launch_receipt(
        launch,
        plan=plan,
        permit=permit,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )
    capability = _transport_capability_minter(
        transport=client, scope="status",
        binding_record={
            "schema": "arv2-power-calibration-status-capability-v1",
            "launch_sha256": launch.receipt_sha256,
            "permit_sha256": permit.permit_sha256,
        }, call_budget={"backtests/list": plan.status_poll_limit},
    )
    for index in range(plan.status_poll_limit):
        try:
            status = formal.parse_statistics_free_backtest_list(
                _call(client, capability, "_request_json", "backtests/list", {
                    "projectId": launch.project_id, "includeStatistics": False,
                }), expected_project_id=launch.project_id,
                expected_backtest_id=launch.backtest_id,
                expected_backtest_name=launch.backtest_name,
            )
        except Exception as exc:
            raise PowerCalibrationSubmissionLocked(
                "calibration terminal-status read became ambiguous"
            ) from exc
        if status.status in formal.BACKTEST_TERMINAL_STATUSES:
            seed = {
                "launch_sha256": launch.receipt_sha256,
                "project_id": launch.project_id,
                "backtest_id": launch.backtest_id, "status": status.status,
                "poll_count": index + 1, "include_statistics": False,
                "full_status_envelope_received_and_json_parsed": True,
                "statistics_or_result_values_selected_or_inspected": False,
                "discarded_values_retained_in_receipt_or_exported": False,
            }
            digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
            terminal = PowerCalibrationTerminalStatus(
                receipt_id=f"arv2-power-calibration-status-{digest[:24]}",
                receipt_sha256=digest, **seed,
            )
            _authority_register(
                terminal,
                plan=plan,
                launch=launch,
                permit=permit,
                review_claim=review_claim,
                owner_signature=owner_signature,
            )
            return require_power_calibration_terminal_status(
                terminal,
                plan=plan,
                launch=launch,
                permit=permit,
                review_claim=review_claim,
                owner_signature=owner_signature,
            )
        if index + 1 == plan.status_poll_limit:
            raise PowerCalibrationSubmissionLocked("status polling exhausted")
        time.sleep(STATUS_WAIT_SECONDS)
    raise AssertionError("unreachable status loop")


def _object_payload(response: object, key: str, maximum: int) -> bytes:
    if type(response) is not dict or response.get("success") is not True:
        raise PowerCalibrationSubmissionError("Object Store read failed")
    item = response.get("object")
    if type(item) is not dict or item.get("key") != key or type(item.get("objectData")) is not str:
        raise PowerCalibrationSubmissionError("Object Store envelope changed")
    try:
        payload = base64.b64decode(item["objectData"], validate=True)
    except (TypeError, ValueError) as exc:
        raise PowerCalibrationSubmissionError("Object Store payload is not base64") from exc
    if not 0 < len(payload) <= maximum:
        raise PowerCalibrationSubmissionError("Object Store payload exceeded capacity")
    return payload


def _persist_power_calibration_output_impl(
    *, plan, review_claim, owner_signature, permit, launch, terminal_status,
    client, _mint_terminal_receipt, _transport_capability_minter,
) -> AcceptedRiskPowerCalibrationOutput:
    require_power_calibration_submission_permit(
        permit, plan=plan, review_claim=review_claim,
        owner_signature=owner_signature,
    )
    require_power_calibration_launch_receipt(
        launch,
        plan=plan,
        permit=permit,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )
    require_power_calibration_terminal_status(
        terminal_status,
        plan=plan,
        launch=launch,
        permit=permit,
        review_claim=review_claim,
        owner_signature=owner_signature,
    )
    if terminal_status.status != "Completed.":
        raise PowerCalibrationSubmissionError("calibration did not complete")
    capability = _transport_capability_minter(
        transport=client, scope="power_calibration_output_read",
        binding_record={
            "schema": "arv2-power-calibration-output-read-capability-v1",
            "launch_sha256": launch.receipt_sha256,
            "terminal_sha256": terminal_status.receipt_sha256,
        }, call_budget={"object/read": 1 + 64},
    )
    try:
        os.mkdir(plan.archive_directory, 0o700)
        shard_directory = plan.archive_directory / "shards"
        os.mkdir(shard_directory, 0o700)
    except OSError as exc:
        raise PowerCalibrationSubmissionLocked("output archive already exists") from exc
    try:
        manifest_payload = _object_payload(_call(
            client, capability, "_read_power_calibration_object_bounded",
            plan.organization_id, plan.output_manifest_key,
        ), plan.output_manifest_key, MAX_MANIFEST_BYTES)
        manifest = _strict_object(manifest_payload, "calibration output manifest")
        if manifest.get("schema") != OUTPUT_MANIFEST_SCHEMA:
            raise PowerCalibrationSubmissionLocked("output manifest schema changed")
        raw_descriptors = manifest.get("shards")
        if type(raw_descriptors) is not list or not 0 < len(raw_descriptors) <= 64:
            raise PowerCalibrationSubmissionLocked("output shard inventory changed")
        descriptors = tuple(
            _descriptor_from_record(item, maximum_bytes=MAX_OUTPUT_SHARD_BYTES)
            for item in raw_descriptors
        )
        shard_paths = []
        for descriptor in descriptors:
            payload = _object_payload(_call(
                client, capability, "_read_power_calibration_object_bounded",
                plan.organization_id, descriptor.object_store_key,
            ), descriptor.object_store_key, MAX_OUTPUT_SHARD_BYTES)
            if hashlib.sha256(payload).hexdigest() != descriptor.compressed_sha256:
                raise PowerCalibrationSubmissionLocked("output shard changed")
            path = (
                shard_directory
                / f"{descriptor.ordinal:03d}-{descriptor.compressed_sha256}.jsonl.gz"
            )
            _write_private(path, payload)
            shard_paths.append(path)
        manifest_path = plan.archive_directory / "manifest.json"
        _write_private(manifest_path, manifest_payload)  # commit marker is last
        qc_terminal = _mint_terminal_receipt(
            plan_id=plan.plan_id, plan_sha256=plan.plan_sha256,
            calibration_input=plan.calibration_input,
            project_id=str(launch.project_id), backtest_id=launch.backtest_id,
            output_manifest_key=plan.output_manifest_key,
        )
        return load_accepted_risk_power_calibration_output(
            calibration_input=plan.calibration_input,
            terminal_receipt=qc_terminal, manifest_path=manifest_path,
            shard_paths=tuple(shard_paths),
        )
    except PowerCalibrationSubmissionLocked:
        raise
    except Exception as exc:
        raise PowerCalibrationSubmissionLocked(
            "calibration output read/persistence became ambiguous"
        ) from exc


def _bind_submission_return_authority(
    *, execute_impl: object, require_launch_impl: object,
    inspect_impl: object, require_terminal_impl: object,
    register_launch: object, current_launch: object,
    register_terminal: object, current_terminal: object,
    transport_capability_minter: object,
    binding_guard: object,
) -> tuple[object, object, object, object]:
    """Bind QC-return registration only to the exact external-call paths."""

    def execute_power_calibration_submission_once(
        *, plan: PowerCalibrationSubmissionPlan,
        review_claim: PowerCalibrationReviewClaim,
        owner_signature: OwnerSignatureAuthority | None,
        client: FormalQcTransport, started_at_utc: str,
    ) -> tuple[PowerCalibrationSubmissionPermit, PowerCalibrationLaunchReceipt]:
        binding_guard("submission")
        return execute_impl(
            plan=plan,
            review_claim=review_claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc=started_at_utc,
            _authority_register=register_launch,
            _transport_capability_minter=transport_capability_minter,
        )

    def require_launch(
        value: PowerCalibrationLaunchReceipt,
        *, plan: PowerCalibrationSubmissionPlan,
        permit: PowerCalibrationSubmissionPermit,
        review_claim: PowerCalibrationReviewClaim,
        owner_signature: OwnerSignatureAuthority,
    ) -> PowerCalibrationLaunchReceipt:
        binding_guard("launch require")
        return require_launch_impl(
            value,
            plan=plan,
            permit=permit,
            review_claim=review_claim,
            owner_signature=owner_signature,
            _authority_current=current_launch,
        )

    def inspect_power_calibration_terminal_status(
        *, plan, review_claim, owner_signature, permit, launch, client,
    ) -> PowerCalibrationTerminalStatus:
        binding_guard("terminal status")
        return inspect_impl(
            plan=plan,
            review_claim=review_claim,
            owner_signature=owner_signature,
            permit=permit,
            launch=launch,
            client=client,
            _authority_register=register_terminal,
            _transport_capability_minter=transport_capability_minter,
        )

    def require_terminal(
        value: PowerCalibrationTerminalStatus,
        *, plan: PowerCalibrationSubmissionPlan,
        launch: PowerCalibrationLaunchReceipt,
        permit: PowerCalibrationSubmissionPermit,
        review_claim: PowerCalibrationReviewClaim,
        owner_signature: OwnerSignatureAuthority,
    ) -> PowerCalibrationTerminalStatus:
        binding_guard("terminal require")
        return require_terminal_impl(
            value,
            plan=plan,
            launch=launch,
            permit=permit,
            review_claim=review_claim,
            owner_signature=owner_signature,
            _authority_current=current_terminal,
        )

    return (
        execute_power_calibration_submission_once,
        require_launch,
        inspect_power_calibration_terminal_status,
        require_terminal,
    )


# Both downstream minters perform an import-time one-shot claim and pin the
# exact three action implementations above.  Deferring these claims until all
# implementations exist is part of the authority handshake, not runtime I/O.
(
    _transport_capability_minter,
    _seal_transport_capability_callers,
) = (
    formal._claim_power_calibration_transport_capability_minter()
)
_power_terminal_minter = _power_bridge._claim_power_calibration_terminal_minter(
    _persist_power_calibration_output_impl
)


(
    execute_power_calibration_submission_once,
    require_power_calibration_launch_receipt,
    inspect_power_calibration_terminal_status,
    require_power_calibration_terminal_status,
) = _bind_submission_return_authority(
    execute_impl=_execute_power_calibration_submission_once_impl,
    require_launch_impl=_require_power_calibration_launch_receipt_impl,
    inspect_impl=_inspect_power_calibration_terminal_status_impl,
    require_terminal_impl=_require_power_calibration_terminal_status_impl,
    register_launch=_return_authority_register_launch,
    current_launch=_return_authority_current_launch,
    register_terminal=_return_authority_register_terminal,
    current_terminal=_return_authority_current_terminal,
    transport_capability_minter=_transport_capability_minter,
    binding_guard=_require_power_action_global_bindings,
)

_seal_submission_return_builder_callers(
    execute_impl=_execute_power_calibration_submission_once_impl,
    inspect_impl=_inspect_power_calibration_terminal_status_impl,
    execute_public=execute_power_calibration_submission_once,
    inspect_public=inspect_power_calibration_terminal_status,
)

del _bind_submission_return_authority
del _require_power_calibration_launch_receipt_impl
del _require_power_calibration_terminal_status_impl
del _return_authority_register_launch
del _return_authority_current_launch
del _return_authority_register_terminal
del _return_authority_current_terminal
del _seal_submission_return_builder_callers
del _make_submission_return_authority


def _bind_terminal_persistence(
    persistence_impl: object,
    terminal_minter: object,
    transport_capability_minter: object,
    binding_guard: object,
) -> object:
    """Keep the Completed-receipt minter lexical to authenticated persistence."""

    def persist_power_calibration_output(
        *, plan, review_claim, owner_signature, permit, launch,
        terminal_status, client,
    ) -> AcceptedRiskPowerCalibrationOutput:
        binding_guard("output persistence")
        return persistence_impl(
            plan=plan,
            review_claim=review_claim,
            owner_signature=owner_signature,
            permit=permit,
            launch=launch,
            terminal_status=terminal_status,
            client=client,
            _mint_terminal_receipt=terminal_minter,
            _transport_capability_minter=transport_capability_minter,
        )

    return persist_power_calibration_output


persist_power_calibration_output = _bind_terminal_persistence(
    _persist_power_calibration_output_impl,
    _power_terminal_minter,
    _transport_capability_minter,
    _require_power_action_global_bindings,
)

_power_bridge._seal_power_calibration_terminal_persistence(
    _persist_power_calibration_output_impl,
    persist_power_calibration_output,
)

_seal_transport_capability_callers(
    (
        (
            "submission",
            ((
                _execute_power_calibration_submission_once_impl,
                execute_power_calibration_submission_once,
            ),),
        ),
        (
            "status",
            ((
                _inspect_power_calibration_terminal_status_impl,
                inspect_power_calibration_terminal_status,
            ),),
        ),
        (
            "power_calibration_output_read",
            ((
                _persist_power_calibration_output_impl,
                persist_power_calibration_output,
            ),),
        ),
    )
)

del _bind_terminal_persistence
del _execute_power_calibration_submission_once_impl
del _inspect_power_calibration_terminal_status_impl
del _persist_power_calibration_output_impl
del _power_terminal_minter
del _transport_capability_minter
del _seal_transport_capability_callers
del _power_bridge

_seal_power_action_global_bindings()
del _make_power_action_global_binding_guard
del _seal_power_action_global_bindings
del _require_power_action_global_bindings


__all__ = [
    "PowerCalibrationLaunchReceipt", "PowerCalibrationReviewClaim",
    "PowerCalibrationSubmissionError", "PowerCalibrationSubmissionLocked",
    "PowerCalibrationSubmissionPermit", "PowerCalibrationSubmissionPlan",
    "PowerCalibrationTerminalStatus", "build_power_calibration_submission_plan",
    "execute_power_calibration_submission_once",
    "inspect_power_calibration_terminal_status",
    "load_power_calibration_review_claim", "persist_power_calibration_output",
    "render_power_calibration_execution_authority_candidate",
    "render_power_calibration_review_claim_candidate",
    "require_power_calibration_review_claim",
    "require_power_calibration_launch_receipt",
    "require_power_calibration_submission_plan",
    "require_power_calibration_submission_permit",
    "require_power_calibration_terminal_status",
]
