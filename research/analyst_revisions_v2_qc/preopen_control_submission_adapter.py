"""One-use, outcome-free QC transport for the ARV2 pre-open control stage.

The production entry points remain closed until an external owner/reviewer
trust root exists.  Tests exercise the exact request choreography through the
credential-isolated ``FormalQcTransport`` injection seam.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import importlib
import json
import os
import re
import stat
import sys
import threading
import time
import weakref
from datetime import datetime, timezone
from pathlib import Path

from research.analyst_revisions_v2 import preopen_control_acquisition as preopen_core
from research.analyst_revisions_v2.preopen_control_acquisition import (
    CONTRACT_ID,
    CONTRACT_SHA256,
    PreopenControlAcquisitionReceipt,
    acquisition_output_shard_descriptor_records,
    require_reviewed_preopen_control_acquisition_receipt,
)
from . import formal_submission_adapter as formal
from . import preopen_control_acquisition_io as preopen_io
from .formal_qc_transport import FormalQcTransport
from .formal_streaming_input import (
    FormalStreamingCapacityBinding,
    PhysicalPreopenTerminalArchive,
    load_physical_preopen_terminal_archive,
    require_formal_streaming_capacity_binding,
)
from .owner_signature_authority import (
    OwnerSignatureAuthority,
    OwnerSignatureAuthorityError,
    require_preopen_execution_owner_signature,
)
from .preopen_control_stage import (
    ENTRY_PATH,
    QUALITY_WORKER_PATH,
    RUNTIME_PATH,
    TERMINAL_PACKAGE_SCHEMA,
    WORKER_PATH,
    PreopenControlQcProjection,
    PreopenControlRunAuthority,
    PreopenInputShard,
    build_preopen_control_qc_projection,
    canonical_json_bytes,
)


class PreopenQcSubmissionError(ValueError):
    """A pre-open plan, permit, response, or output binding is invalid."""


class PreopenQcSubmissionLocked(RuntimeError):
    """The one-use permit was spent and the external state is ambiguous."""

    def __init__(self, phase: str, permit_id: str, detail: str) -> None:
        super().__init__(f"{phase}: {detail}; one-use pre-open permit remains consumed")
        self.phase = phase
        self.permit_id = permit_id


PLAN_SCHEMA = "arv2-preopen-qc-submission-plan-v1"
PHYSICAL_PLAN_SCHEMA = "arv2-physical-preopen-qc-submission-plan-v1"
PERMIT_SCHEMA = "arv2-preopen-qc-one-use-permit-v1"
LAUNCH_SCHEMA = "arv2-preopen-qc-launch-receipt-v1"
TERMINAL_SCHEMA = "arv2-preopen-qc-terminal-status-v1"
OUTPUT_RECEIPT_SCHEMA = "arv2-preopen-qc-terminal-package-receipt-v1"
EXECUTION_AUTHORITY_SCHEMA = "arv2-preopen-qc-execution-authority-v1"
PHYSICAL_EXECUTION_AUTHORITY_SCHEMA = (
    "arv2-physical-preopen-qc-execution-authority-v1"
)
OWNER_REVIEW_WAIVER_ID = "arv2-owner-review-waiver-section-72-v1"
OWNER_REVIEW_WAIVER_SCOPE = "SECTION_72_THROUGH_FIRST_FORMAL_BACKTEST"
OWNER_REVIEW_WAIVER_BASIS = "OWNER_EXPLICIT_REVIEW_WAIVER"
OWNER_REVIEW_WAIVER_DISPOSITION = "NOT_PERFORMED_OWNER_WAIVED"
PHYSICAL_INPUT_UPLOAD_DISPOSITION = (
    "REUSE_PROCESS_AUTHENTICATED_PHYSICAL_PREOPEN_UPLOAD"
)
QC_DEFAULT_RESEARCH_NOTEBOOK_PATH = "research.ipynb"
PERMIT_FILENAME = "arv2-preopen-qc-one-use-permit-v1.json"
OUTPUT_ARCHIVE_DIRECTORY_NAME = "preopen-control-terminal-archive"
OUTPUT_ARCHIVE_MANIFEST_NAME = "output-manifest.json"
OUTPUT_ARCHIVE_SHARD_DIRECTORY = "terminal-shards"
MAX_PACKAGE_BYTES = 64 * 1024
MAX_OUTPUT_MANIFEST_BYTES = 8 * 1024 * 1024
# FormalQcTransport caps the complete JSON response at 16 MiB.  The raw object
# is base64 encoded inside that response, so keep each accepted object at or
# below 10 MiB and refuse a larger runtime descriptor before reading it.
MAX_OUTPUT_SHARD_READ_BYTES = 10 * 1024 * 1024
MAX_OUTPUT_SHARD_READS = 20_000
MAX_COMPILE_POLLS = 120
MAX_STATUS_POLLS = 240
COMPILE_POLL_SECONDS = 2
STATUS_POLL_SECONDS = 30
SOURCE_PATHS = (ENTRY_PATH, WORKER_PATH, QUALITY_WORKER_PATH, RUNTIME_PATH)
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/ -]{0,511}\Z")
PREOPEN_EXECUTION_ACTIONS = (
    "authenticate",
    "projects/read_exact_name_inventory",
    "projects/create_private_exact_name_once",
    "object/set_exact_input",
    "object/properties_verify_exact_input",
    "files/read_exact_inventory",
    "files/create_exact_projection",
    "compile/create_once",
    "compile/read_state_only_with_bounded_wait",
    "backtests/create_once",
    "backtests/list_identity_status_includeStatistics_false",
    "object/read_exact_named_terminal_package_once",
    "object/read_exact_output_manifest_then_content_addressed_terminal_shards_once",
    "write_owner_only_terminal_archive_manifest_last",
    "load_authenticated_physical_preopen_terminal_archive",
)
PHYSICAL_PREOPEN_EXECUTION_ACTIONS = (
    "authenticate",
    "projects/read_exact_name_inventory",
    "projects/create_private_exact_name_once",
    "object/properties_verify_process_authenticated_preuploaded_input",
    "files/read_exact_inventory",
    "files/delete_exact_new_project_default_research_notebook_once",
    "files/create_exact_projection",
    "compile/create_once",
    "compile/read_state_only_with_bounded_wait",
    "backtests/create_once",
    "backtests/list_identity_status_includeStatistics_false",
    "object/read_exact_named_terminal_package_once",
    "object/read_exact_pre_review_manifest_then_content_addressed_terminal_shards_once",
    "write_owner_only_inert_pre_review_capture_manifest_last",
)
PREOPEN_REQUIRED_HOST_CODE_PATHS = tuple(dict.fromkeys((
    *formal.REQUIRED_HOST_CODE_PATHS,
    "research/analyst_revisions_v2/canonical.py",
    "research/analyst_revisions_v2/stock_evaluation_contract.py",
    "research/analyst_revisions_v2/preopen_control_acquisition.py",
    "research/analyst_revisions_v2_qc/preopen_control_acquisition_io.py",
    "research/analyst_revisions_v2_qc/preopen_control_stage.py",
    "research/analyst_revisions_v2_qc/preopen_control_submission_adapter.py",
)))
PHYSICAL_PREOPEN_REQUIRED_HOST_CODE_PATHS = tuple(dict.fromkeys((
    *PREOPEN_REQUIRED_HOST_CODE_PATHS,
    "research/analyst_revisions_v2_qc/historical_preopen_input_adapter.py",
    "research/analyst_revisions_v2_qc/physical_preopen_submission_adapter.py",
    "research/analyst_revisions_v2_qc/preopen_control_prereview_downloader.py",
)))


def _make_preopen_action_global_binding_guard():
    """Pin the complete in-process namespace used by pre-open QC actions."""

    expected_names: tuple[str, ...] = ()
    expected_globals: tuple[tuple[str, object, object], ...] = ()
    expected_external: tuple[tuple[object, str, object], ...] = ()
    expected_json_classes: tuple[object, ...] = ()
    expected_dependency_functions: tuple[object, ...] = ()
    expected_dependency_classes: tuple[object, ...] = ()
    expected_dependency_module_attributes: tuple[object, ...] = ()
    getpid = os.getpid
    error_type = PreopenQcSubmissionError
    authority_pid = getpid()
    module_globals = globals()
    exact_type = type
    exact_tuple = tuple
    any_true = any
    read_attribute = getattr
    read_vars = vars
    mapping_get = dict.get
    dict_type = dict
    list_type = list
    function_type = exact_type(lambda: None)
    code_type = exact_type((lambda: None).__code__)
    module_type = exact_type(sys)
    class_type = type
    static_method_type = staticmethod
    class_method_type = classmethod
    property_type = property
    length = len
    zip_strict = zip
    string_type = str
    missing = object()
    path_type = exact_type(Path())
    guarded_json_classes = (json.JSONDecoder, json.JSONEncoder)
    dependency_global_namespaces = (
        read_vars(preopen_io),
        read_vars(preopen_core),
        load_physical_preopen_terminal_archive.__globals__,
    )
    excluded = (
        "_make_preopen_action_global_binding_guard",
        "_seal_preopen_action_global_bindings",
        "_require_preopen_action_global_bindings",
        "_bind_transport_capability_consumers",
        "_transport_capability_minter",
        "_seal_transport_capability_callers",
        "_execute_preopen_qc_submission_once_impl",
        "_execute_preuploaded_preopen_qc_submission_once_impl",
        "_inspect_preopen_qc_terminal_status_impl",
        "_retrieve_preopen_qc_terminal_package_impl",
        "_download_and_load_preopen_qc_terminal_archive_impl",
        "_process_receipt_frame_provenance",
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
                "_compile_id",
                "_compile_state",
                "COMPILE_TERMINAL_STATES",
                "_created_backtest",
                "parse_statistics_free_backtest_list",
                "BACKTEST_TERMINAL_STATUSES",
            ),
        ),
        (preopen_core, ("_validate_manifest",)),
        (preopen_io, ("_validated_batch_major_output_payloads",)),
        (hashlib, ("md5", "sha256")),
        (base64, ("b64decode", "b64encode")),
        (json, ("loads",)),
        (
            os,
            (
                "O_CLOEXEC",
                "O_CREAT",
                "O_DIRECTORY",
                "O_EXCL",
                "O_NOFOLLOW",
                "O_RDONLY",
                "O_WRONLY",
                "close",
                "fstat",
                "fsync",
                "getpid",
                "getuid",
                "mkdir",
                "open",
                "read",
                "write",
            ),
        ),
        (stat, ("S_IMODE", "S_ISDIR", "S_ISLNK", "S_ISREG")),
        (time, ("sleep",)),
        (sys, ("_getframe", "modules")),
        (os.path, ("realpath",)),
        (
            Path,
            (
                "is_absolute",
                "is_dir",
                "is_symlink",
                "iterdir",
                "lstat",
                "read_bytes",
                "relative_to",
                "resolve",
                "stat",
            ),
        ),
        (
            path_type,
            (
                "is_absolute",
                "is_dir",
                "is_symlink",
                "iterdir",
                "lstat",
                "read_bytes",
                "relative_to",
                "resolve",
                "stat",
            ),
        ),
    )

    def non_dunder_names() -> tuple[str, ...]:
        keys = exact_tuple(module_globals)
        if any_true(exact_type(name) is not string_type for name in keys):
            raise error_type("pre-open action global census changed")
        return exact_tuple(
            name
            for name in keys
            if not name.startswith("__") and name not in excluded
        )

    def is_dependency_namespace(namespace) -> bool:
        return any_true(
            namespace is expected
            for expected in dependency_global_namespaces
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

    def dependency_snapshot(roots):
        """Capture the bounded pre-open parser/manifest call graph."""

        pending = list_type(roots)
        pending_classes = list_type()
        seen: tuple[object, ...] = ()
        seen_classes: tuple[object, ...] = ()
        functions = list_type()
        classes = list_type()
        module_attributes = list_type()
        while pending or pending_classes:
            if not pending:
                value_class = pending_classes.pop()
                if any_true(value_class is item for item in seen_classes):
                    continue
                seen_classes = (*seen_classes, value_class)
                namespace = read_vars(value_class)
                names = exact_tuple(namespace)
                bindings = exact_tuple(
                    (name, namespace[name]) for name in names
                )
                classes.append((value_class, names, bindings))
                for _name, attribute in bindings:
                    candidate = (
                        attribute
                        if exact_type(attribute) is function_type
                        else attribute.__func__
                        if exact_type(attribute)
                        in (static_method_type, class_method_type)
                        else None
                    )
                    if (
                        exact_type(candidate) is function_type
                        and is_dependency_namespace(candidate.__globals__)
                    ):
                        pending.append(candidate)
                    if exact_type(attribute) is property_type:
                        for candidate in (
                            attribute.fget,
                            attribute.fset,
                            attribute.fdel,
                        ):
                            if (
                                exact_type(candidate) is function_type
                                and is_dependency_namespace(
                                    candidate.__globals__
                                )
                            ):
                                pending.append(candidate)
                continue
            function = pending.pop()
            if (
                exact_type(function) is not function_type
                or not is_dependency_namespace(function.__globals__)
                or any_true(function is item for item in seen)
            ):
                continue
            seen = (*seen, function)
            code = function.__code__
            namespace = function.__globals__
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
                (name, mapping_get(namespace, name, missing))
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
                namespace,
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
                    and is_dependency_namespace(value.__globals__)
                ):
                    pending.append(value)
                elif exact_type(value) is class_type:
                    pending_classes.append(value)
                elif exact_type(value) is module_type:
                    module_namespace = read_vars(value)
                    for name in names:
                        if name not in module_namespace:
                            continue
                        attribute = module_namespace[name]
                        module_attributes.append((
                            value,
                            module_namespace,
                            name,
                            attribute,
                        ))
                        if exact_type(attribute) is class_type:
                            pending_classes.append(attribute)
                        elif (
                            exact_type(attribute) is function_type
                            and is_dependency_namespace(
                                attribute.__globals__
                            )
                        ):
                            pending.append(attribute)
            for value in closure_values:
                if (
                    exact_type(value) is function_type
                    and is_dependency_namespace(value.__globals__)
                ):
                    pending.append(value)
                elif exact_type(value) is class_type:
                    pending_classes.append(value)
        return (
            exact_tuple(functions),
            exact_tuple(classes),
            exact_tuple(module_attributes),
        )

    def dependencies_are_current() -> bool:
        for (
            function,
            code,
            namespace,
            names,
            freevars,
            closure_values,
            builtin_namespace,
            builtin_mapping,
            global_bindings,
            builtin_bindings,
        ) in expected_dependency_functions:
            closure = function.__closure__ or ()
            current_closure_values = exact_tuple(
                cell.cell_contents for cell in closure
            )
            if (
                function.__code__ is not code
                or function.__globals__ is not namespace
                or transitive_code_names(function.__code__) != names
                or exact_tuple(function.__code__.co_freevars) != freevars
                or length(current_closure_values) != length(closure_values)
                or any_true(
                    current is not expected
                    for current, expected in zip_strict(
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
                    mapping_get(namespace, name, missing) is not expected
                    for name, expected in global_bindings
                )
                or any_true(
                    mapping_get(builtin_mapping, name, missing) is not expected
                    for name, expected in builtin_bindings
                )
            ):
                return False
        for value_class, names, bindings in expected_dependency_classes:
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
            in expected_dependency_module_attributes
        )

    def seal() -> None:
        nonlocal expected_names, expected_globals, expected_external
        nonlocal expected_json_classes
        nonlocal expected_dependency_functions, expected_dependency_classes
        nonlocal expected_dependency_module_attributes
        if expected_globals or expected_external:
            raise error_type("pre-open action globals were already sealed")
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
        expected_json_classes = exact_tuple(
            (
                value_class,
                exact_tuple(read_vars(value_class)),
                exact_tuple(
                    (name, read_vars(value_class)[name])
                    for name in read_vars(value_class)
                ),
            )
            for value_class in guarded_json_classes
        )
        (
            expected_dependency_functions,
            expected_dependency_classes,
            expected_dependency_module_attributes,
        ) = dependency_snapshot((
            preopen_io._validated_batch_major_output_payloads,
            preopen_core._validate_manifest,
            load_physical_preopen_terminal_archive,
            require_formal_streaming_capacity_binding,
        ))

    def require(kind: str) -> None:
        if getpid() != authority_pid or not expected_globals:
            raise error_type(
                f"pre-open {kind} action global authority changed"
            )
        if non_dunder_names() != expected_names or any_true(
            exact_type(module_globals.get(name, missing)) is not expected_type
            or module_globals.get(name, missing) is not expected
            for name, expected_type, expected in expected_globals
        ):
            raise error_type(
                f"pre-open {kind} action global authority changed"
            )
        if not dependencies_are_current() or any_true(
            exact_tuple(read_vars(value_class)) != names
            or any_true(
                read_vars(value_class)[name] is not expected
                for name, expected in bindings
            )
            for value_class, names, bindings in expected_json_classes
        ) or any_true(
            read_attribute(namespace, name, missing) is not value
            for namespace, name, value in expected_external
        ):
            raise error_type(
                f"pre-open {kind} action dependency authority changed"
            )

    return seal, require


(
    _seal_preopen_action_global_bindings,
    _require_preopen_action_global_bindings,
) = _make_preopen_action_global_binding_guard()


# These dictionaries are observable cleanup/accounting mirrors only.  Exact
# process-return authority additionally lives in the tuple-backed lexical
# vault below, so reflected insertion or replacement in a mirror cannot mint a
# launch, terminal-status, or output-read receipt.
_LAUNCH_RECEIPT_AUTHORITIES: dict[int, tuple[object, ...]] = {}
_TERMINAL_RECEIPT_AUTHORITIES: dict[int, tuple[object, ...]] = {}
_OUTPUT_RECEIPT_AUTHORITIES: dict[int, tuple[object, ...]] = {}
_PROCESS_RECEIPT_AUTHORITY_LOCK = threading.RLock()


def _make_process_receipt_authority_vault(
    receipt_types: tuple[tuple[str, type], ...],
):
    if (
        type(receipt_types) is not tuple
        or tuple(item[0] for item in receipt_types)
        != ("launch", "terminal", "output")
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not type
            for item in receipt_types
        )
    ):
        raise PreopenQcSubmissionError(
            "pre-open process receipt type census changed"
        )
    private_registries: tuple[
        tuple[str, tuple[tuple[int, tuple[object, ...]], ...]], ...
    ] = (("launch", ()), ("terminal", ()), ("output", ()))
    register_provenance: tuple[
        tuple[
            str,
            tuple[
                tuple[
                    object,
                    str,
                    str,
                    object,
                    tuple[tuple[str, object], ...],
                ],
                ...,
            ],
        ],
        ...,
    ] = ()
    getpid = os.getpid
    getframe = sys._getframe
    system_module = sys
    module_registry = system_module.modules
    module_name = __name__
    registered_module = module_registry.get(module_name)
    module_globals = globals()
    read_vars = vars
    exact_tuple = tuple
    any_true = any
    exact_type = type
    identity = id
    next_item = next
    weak_reference = weakref.ref
    error_type = PreopenQcSubmissionError
    hex_pattern = _HEX
    launch_public_registry = _LAUNCH_RECEIPT_AUTHORITIES
    terminal_public_registry = _TERMINAL_RECEIPT_AUTHORITIES
    output_public_registry = _OUTPUT_RECEIPT_AUTHORITIES
    process_lock = _PROCESS_RECEIPT_AUTHORITY_LOCK
    rlock_factory = threading.RLock
    authority_pid = getpid()

    def public_registry(kind: str) -> dict[int, tuple[object, ...]]:
        if kind == "launch":
            return launch_public_registry
        if kind == "terminal":
            return terminal_public_registry
        if kind == "output":
            return output_public_registry
        raise error_type("unknown pre-open process receipt kind")

    def private_registry(
        kind: str,
    ) -> tuple[tuple[int, tuple[object, ...]], ...]:
        return next_item(
            (records for name, records in private_registries if name == kind),
            (),
        )

    def replace_private_registry(
        kind: str,
        records: tuple[tuple[int, tuple[object, ...]], ...],
    ) -> None:
        nonlocal private_registries

        private_registries = exact_tuple(
            (name, records if name == kind else current)
            for name, current in private_registries
        )

    def private_entry(
        kind: str, identity: int,
    ) -> tuple[object, ...] | None:
        return next_item(
            (
                entry
                for key, entry in private_registry(kind)
                if key == identity
            ),
            None,
        )

    def caller_is_exact(kind: str) -> bool:
        chain = next_item(
            (
                value
                for name, value in register_provenance
                if name == kind
            ),
            (),
        )
        if not chain:
            return False
        frame = getframe(2)
        for (
            expected_code,
            expected_name,
            expected_filename,
            expected_globals,
            freevar_bindings,
        ) in chain:
            if (
                system_module.modules is not module_registry
                or module_registry.get(module_name) is not registered_module
                or registered_module is None
                or read_vars(registered_module) is not module_globals
                or frame is None
                or frame.f_code is not expected_code
                or frame.f_code.co_name != expected_name
                or frame.f_code.co_filename != expected_filename
                or frame.f_globals is not expected_globals
                or frame.f_globals is not module_globals
                or frame.f_globals.get("__name__") != module_name
                or exact_tuple(expected_code.co_freevars)
                != exact_tuple(name for name, _value in freevar_bindings)
                or any_true(
                    frame.f_locals.get(name) is not expected_value
                    for name, expected_value in freevar_bindings
                )
            ):
                return False
            frame = frame.f_back
        return True

    def forget(kind: str, identity: int, reference: object) -> None:
        public = public_registry(kind)
        with process_lock:
            current = private_entry(kind, identity)
            if current is not None and current[0] is reference:
                replace_private_registry(
                    kind,
                    exact_tuple(
                        item
                        for item in private_registry(kind)
                        if item[0] != identity
                    ),
                )
            if public.get(identity) is current:
                public.pop(identity, None)

    def reset_after_fork() -> None:
        nonlocal private_registries
        nonlocal launch_public_registry
        nonlocal terminal_public_registry
        nonlocal output_public_registry
        nonlocal process_lock
        global _LAUNCH_RECEIPT_AUTHORITIES
        global _TERMINAL_RECEIPT_AUTHORITIES
        global _OUTPUT_RECEIPT_AUTHORITIES
        global _PROCESS_RECEIPT_AUTHORITY_LOCK

        launch_public_registry = {}
        terminal_public_registry = {}
        output_public_registry = {}
        process_lock = rlock_factory()
        _LAUNCH_RECEIPT_AUTHORITIES = launch_public_registry
        _TERMINAL_RECEIPT_AUTHORITIES = terminal_public_registry
        _OUTPUT_RECEIPT_AUTHORITIES = output_public_registry
        _PROCESS_RECEIPT_AUTHORITY_LOCK = process_lock
        private_registries = (
            ("launch", ()), ("terminal", ()), ("output", ())
        )

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)

    def register(kind: str, value: object) -> object:
        public = public_registry(kind)
        if getpid() != authority_pid or not caller_is_exact(kind):
            raise PreopenQcSubmissionError(
                f"pre-open {kind} receipt register caller changed"
            )
        expected_type = next_item(
            (value_type for name, value_type in receipt_types if name == kind),
            None,
        )
        if exact_type(value) is not expected_type:
            raise PreopenQcSubmissionError(
                f"pre-open {kind} receipt register type changed"
            )
        receipt_sha256 = value.receipt_sha256
        if (
            exact_type(receipt_sha256) is not str
            or hex_pattern.fullmatch(receipt_sha256) is None
        ):
            raise PreopenQcSubmissionError(
                f"pre-open {kind} receipt register identity changed"
            )
        value_identity = identity(value)
        reference = weak_reference(
            value,
            lambda ref, receipt_kind=kind, key=value_identity: forget(
                receipt_kind, key, ref
            ),
        )
        entry = (reference, receipt_sha256, getpid())
        with process_lock:
            if (
                private_entry(kind, value_identity) is not None
                or value_identity in public
            ):
                raise PreopenQcSubmissionError(
                    f"pre-open {kind} receipt authority identity was reused"
                )
            replace_private_registry(
                kind,
                (*private_registry(kind), (value_identity, entry)),
            )
            public[value_identity] = entry
        return value

    def current(kind: str, value: object) -> tuple[object, ...] | None:
        public = public_registry(kind)
        value_identity = identity(value)
        with process_lock:
            private = private_entry(kind, value_identity)
            mirrored = public.get(value_identity)
            if (
                private is None
                or mirrored is not private
                or private[0]() is not value
                or private[-1] != getpid()
            ):
                replace_private_registry(
                    kind,
                    exact_tuple(
                        item
                        for item in private_registry(kind)
                        if item[0] != value_identity
                    ),
                )
                public.pop(value_identity, None)
                return None
            return private

    def seal_provenance(
        value: tuple[
            tuple[
                str,
                tuple[
                    tuple[
                        object,
                        str,
                        str,
                        object,
                        tuple[tuple[str, object], ...],
                    ],
                    ...,
                ],
            ],
            ...,
        ],
    ) -> None:
        nonlocal register_provenance

        if (
            register_provenance
            or type(value) is not tuple
            or tuple(item[0] for item in value)
            != ("launch", "terminal", "output")
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[1]) is not tuple
                or len(item[1]) != 3
                or any(
                    type(frame) is not tuple
                    or len(frame) != 5
                    or type(frame[1]) is not str
                    or type(frame[2]) is not str
                    or frame[3] is not module_globals
                    or type(frame[4]) is not tuple
                    or any(
                        type(binding) is not tuple
                        or len(binding) != 2
                        or type(binding[0]) is not str
                        for binding in frame[4]
                    )
                    for frame in item[1]
                )
                for item in value
            )
        ):
            raise PreopenQcSubmissionError(
                "pre-open process receipt provenance changed"
            )
        register_provenance = value

    return register, current, seal_provenance


@dataclasses.dataclass(frozen=True, slots=True)
class PreopenQcHostSourceBinding:
    path: str
    content_sha256: str
    byte_count: int

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class PreopenQcHostClosureBinding:
    closure_id: str
    closure_sha256: str
    sources: tuple[PreopenQcHostSourceBinding, ...]


def _read_preopen_host_sources(
    _sealed_root: Path = Path(__file__).resolve().parents[2],
    _sealed_paths: tuple[str, ...] = PREOPEN_REQUIRED_HOST_CODE_PATHS,
) -> tuple[PreopenQcHostSourceBinding, ...]:
    result = []
    for relative in _sealed_paths:
        path = (_sealed_root / relative).resolve(strict=True)
        try:
            path.relative_to(_sealed_root)
            payload = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise PreopenQcSubmissionError(
                "pre-open host source closure is unavailable"
            ) from exc
        if not payload or b"\r" in payload or not payload.endswith(b"\n"):
            raise PreopenQcSubmissionError(
                f"pre-open host source is not canonical LF: {relative}"
            )
        result.append(PreopenQcHostSourceBinding(
            path=relative,
            content_sha256=hashlib.sha256(payload).hexdigest(),
            byte_count=len(payload),
        ))
    return tuple(result)


def build_preopen_qc_host_closure_binding() -> PreopenQcHostClosureBinding:
    sources = _read_preopen_host_sources()
    seed = {
        "schema": "arv2-preopen-qc-host-closure-v1",
        "closure_id": None,
        "closure_sha256": None,
        "sources": [item.to_record() for item in sources],
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    return PreopenQcHostClosureBinding(
        closure_id="arv2-preopen-qc-host-closure-" + digest[:24],
        closure_sha256=digest,
        sources=sources,
    )


def verify_preopen_qc_host_closure_live(
    value: PreopenQcHostClosureBinding,
) -> None:
    if (
        type(value) is not PreopenQcHostClosureBinding
        or tuple(item.path for item in value.sources)
        != PREOPEN_REQUIRED_HOST_CODE_PATHS
        or any(
            type(item) is not PreopenQcHostSourceBinding
            or _HEX.fullmatch(item.content_sha256) is None
            or type(item.byte_count) is not int
            or item.byte_count < 1
            for item in value.sources
        )
    ):
        raise PreopenQcSubmissionError("pre-open host source closure changed")
    seed = {
        "schema": "arv2-preopen-qc-host-closure-v1",
        "closure_id": None,
        "closure_sha256": None,
        "sources": [item.to_record() for item in value.sources],
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        value.closure_sha256 != digest
        or value.closure_id != "arv2-preopen-qc-host-closure-" + digest[:24]
        or _read_preopen_host_sources() != value.sources
    ):
        raise PreopenQcSubmissionError("live pre-open host source closure changed")


def _read_physical_preopen_host_sources(
    _sealed_root: Path = Path(__file__).resolve().parents[2],
    _sealed_paths: tuple[str, ...] = PHYSICAL_PREOPEN_REQUIRED_HOST_CODE_PATHS,
) -> tuple[PreopenQcHostSourceBinding, ...]:
    result = []
    for relative in _sealed_paths:
        try:
            path = (_sealed_root / relative).resolve(strict=True)
            path.relative_to(_sealed_root)
            payload = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise PreopenQcSubmissionError(
                "physical pre-open host source closure is unavailable"
            ) from exc
        if not payload or b"\r" in payload or not payload.endswith(b"\n"):
            raise PreopenQcSubmissionError(
                f"physical pre-open host source is not canonical LF: {relative}"
            )
        result.append(PreopenQcHostSourceBinding(
            path=relative,
            content_sha256=hashlib.sha256(payload).hexdigest(),
            byte_count=len(payload),
        ))
    return tuple(result)


def build_physical_preopen_qc_host_closure_binding(
) -> PreopenQcHostClosureBinding:
    sources = _read_physical_preopen_host_sources()
    seed = {
        "schema": "arv2-physical-preopen-qc-host-closure-v1",
        "closure_id": None,
        "closure_sha256": None,
        "sources": [item.to_record() for item in sources],
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    return PreopenQcHostClosureBinding(
        closure_id="arv2-physical-preopen-qc-host-closure-" + digest[:24],
        closure_sha256=digest,
        sources=sources,
    )


def verify_physical_preopen_qc_host_closure_live(
    value: PreopenQcHostClosureBinding,
) -> None:
    if (
        type(value) is not PreopenQcHostClosureBinding
        or tuple(item.path for item in value.sources)
        != PHYSICAL_PREOPEN_REQUIRED_HOST_CODE_PATHS
        or any(
            type(item) is not PreopenQcHostSourceBinding
            or _HEX.fullmatch(item.content_sha256) is None
            or type(item.byte_count) is not int
            or item.byte_count < 1
            for item in value.sources
        )
    ):
        raise PreopenQcSubmissionError(
            "physical pre-open host source closure changed"
        )
    seed = {
        "schema": "arv2-physical-preopen-qc-host-closure-v1",
        "closure_id": None,
        "closure_sha256": None,
        "sources": [item.to_record() for item in value.sources],
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        value.closure_sha256 != digest
        or value.closure_id
        != "arv2-physical-preopen-qc-host-closure-" + digest[:24]
        or _read_physical_preopen_host_sources() != value.sources
    ):
        raise PreopenQcSubmissionError(
            "live physical pre-open host source closure changed"
        )


def _preopen_transport_call(
    closure: PreopenQcHostClosureBinding,
    client: FormalQcTransport,
    capability,
    method: str,
    *args,
    **kwargs,
) -> object:
    if (
        type(closure) is PreopenQcHostClosureBinding
        and tuple(item.path for item in closure.sources)
        == PHYSICAL_PREOPEN_REQUIRED_HOST_CODE_PATHS
    ):
        verify_physical_preopen_qc_host_closure_live(closure)
    else:
        verify_preopen_qc_host_closure_live(closure)
    return formal._transport_call(client, capability, method, *args, **kwargs)


def _require_external_execution_trust_root(
    value: OwnerSignatureAuthority | None, authority_payload: bytes,
) -> None:
    try:
        require_preopen_execution_owner_signature(
            value, authority_payload=authority_payload
        )
    except OwnerSignatureAuthorityError as exc:
        raise PreopenQcSubmissionError(
            "non-self-mintable owner/reviewer pre-open execution trust root is unavailable"
        ) from exc


def _canonical(value: object) -> bytes:
    try:
        return canonical_json_bytes(value)
    except (TypeError, ValueError, RecursionError) as exc:
        raise PreopenQcSubmissionError("pre-open submission value is not canonical") from exc


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise PreopenQcSubmissionError(f"{name} is not SHA-256")
    return value


def _safe(value: object, name: str) -> str:
    if type(value) is not str or _SAFE.fullmatch(value) is None:
        raise PreopenQcSubmissionError(f"{name} is not a safe identifier")
    return value


def _utc(value: object, name: str) -> str:
    if type(value) is not str or not value.endswith("Z"):
        raise PreopenQcSubmissionError(f"{name} is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PreopenQcSubmissionError(f"{name} is not canonical UTC") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise PreopenQcSubmissionError(f"{name} is not canonical UTC")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class PreopenQcUploadEntry:
    role: str
    object_store_key: str
    content_sha256: str
    content_md5: str
    byte_count: int
    payload: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            "role": self.role, "object_store_key": self.object_store_key,
            "content_sha256": self.content_sha256,
            "content_md5": self.content_md5, "byte_count": self.byte_count,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class PreopenQcSubmissionPlan:
    plan_id: str
    plan_sha256: str
    organization_id: str
    project_name: str
    backtest_name: str
    projection_id: str
    projection_sha256: str
    input_manifest_sha256: str
    project_source_set_sha256: str
    run_authority_id: str
    run_authority_sha256: str
    terminal_package_key: str
    upload_entries: tuple[PreopenQcUploadEntry, ...]
    source_files: tuple[object, ...]
    compile_poll_limit: int
    status_poll_limit: int
    maximum_backtest_submissions: int
    maximum_output_manifest_bytes: int
    maximum_output_shard_reads: int
    maximum_output_shard_read_bytes: int
    output_archive_root: Path | None
    input_manifest_bytes: bytes = dataclasses.field(repr=False)
    input_shards: tuple[PreopenInputShard, ...] = dataclasses.field(repr=False)
    projection: PreopenControlQcProjection = dataclasses.field(repr=False)
    run_authority: PreopenControlRunAuthority = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PhysicalPreopenQcSubmissionPlan:
    """Payload-free QC plan backed by one authenticated physical upload."""

    plan_id: str
    plan_sha256: str
    organization_id: str
    project_name: str
    backtest_name: str
    projection_id: str
    projection_sha256: str
    input_manifest_sha256: str
    project_source_set_sha256: str
    run_authority_id: str
    run_authority_sha256: str
    terminal_package_key: str
    physical_upload_receipt_id: str
    physical_upload_receipt_sha256: str
    physical_upload_plan_id: str
    physical_upload_plan_sha256: str
    physical_upload_permit_id: str
    physical_upload_permit_sha256: str
    physical_stream_id: str
    physical_stream_sha256: str
    input_source_inventory_sha256: str
    preuploaded_object_inventory_sha256: str
    preuploaded_input_shard_count: int
    preuploaded_object_count: int
    preuploaded_byte_count: int
    input_upload_disposition: str
    review_disposition: str
    independent_review_complete: bool
    authorization_basis: str
    owner_review_waiver_id: str
    owner_review_waiver_scope: str
    post_first_formal_backtest_independent_review_required: bool
    source_files: tuple[object, ...]
    compile_poll_limit: int
    status_poll_limit: int
    maximum_backtest_submissions: int
    maximum_output_manifest_bytes: int
    maximum_output_shard_reads: int
    maximum_output_shard_read_bytes: int
    output_archive_root: Path | None
    outcome_result_statistics_log_order_access_authorized: bool
    deployment_order_trading_authorized: bool
    _preuploaded_objects: tuple[object, ...] = dataclasses.field(repr=False)
    _input_manifest_bytes: bytes = dataclasses.field(repr=False)
    projection: PreopenControlQcProjection = dataclasses.field(repr=False)
    run_authority: PreopenControlRunAuthority = dataclasses.field(repr=False)
    _physical_upload_receipt: object = dataclasses.field(repr=False)
    _physical_receipt_requirer: object = dataclasses.field(repr=False)


_PHYSICAL_PLAN_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType[PhysicalPreopenQcSubmissionPlan], str, int]
] = {}
_PHYSICAL_PLAN_AUTHORITY_LOCK = threading.RLock()
_PHYSICAL_PLAN_AUTHORITY_PID = os.getpid()


def _entry(role: str, key: str, payload: bytes) -> PreopenQcUploadEntry:
    if type(payload) is not bytes or not payload:
        raise PreopenQcSubmissionError("upload entry is empty")
    return PreopenQcUploadEntry(
        role=role, object_store_key=key,
        content_sha256=hashlib.sha256(payload).hexdigest(),
        content_md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        byte_count=len(payload), payload=payload,
    )


def _rebuild_projection(
    projection: PreopenControlQcProjection, input_manifest_bytes: bytes,
    authority: PreopenControlRunAuthority,
) -> PreopenControlQcProjection:
    if (
        type(projection) is not PreopenControlQcProjection
        or tuple(item.project_path for item in projection.source_files) != SOURCE_PATHS
    ):
        raise PreopenQcSubmissionError("pre-open source projection changed")
    by_path = {item.project_path: item for item in projection.source_files}
    worker_source = by_path[WORKER_PATH].content
    if worker_source.count(CONTRACT_SHA256.encode("ascii")) != 1:
        raise PreopenQcSubmissionError("projected worker contract binding changed")
    worker_template = worker_source.replace(
        CONTRACT_SHA256.encode("ascii"),
        b"__ARV2_PREOPEN_CONTROL_CONTRACT_SHA256__",
    )
    rebuilt = build_preopen_control_qc_projection(
        input_manifest_bytes=input_manifest_bytes,
        worker_source_bytes=worker_template,
        quality_worker_source_bytes=by_path[QUALITY_WORKER_PATH].content,
        runtime_source_bytes=by_path[RUNTIME_PATH].content,
        run_authority=authority,
    )
    if rebuilt != projection or projection.enabled_runtime_source is not True:
        raise PreopenQcSubmissionError("pre-open source projection is not activated and exact")
    return projection


def build_preopen_qc_submission_plan(
    *, projection: PreopenControlQcProjection,
    input_manifest_bytes: bytes, input_shards: tuple[PreopenInputShard, ...],
    run_authority: PreopenControlRunAuthority, organization_id: str,
    output_archive_root: Path | None = None,
) -> PreopenQcSubmissionPlan:
    _safe(organization_id, "organization_id")
    _rebuild_projection(projection, input_manifest_bytes, run_authority)
    if (
        type(input_shards) is not tuple
        or not input_shards
        or any(type(item) is not PreopenInputShard for item in input_shards)
    ):
        raise PreopenQcSubmissionError("pre-open input shard inventory changed")
    try:
        manifest = json.loads(input_manifest_bytes.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise PreopenQcSubmissionError("input manifest is not JSON") from exc
    if _canonical(manifest) != input_manifest_bytes:
        raise PreopenQcSubmissionError("input manifest is not canonical")
    resource_census = manifest.get("resource_census")
    maximum_output_shard_reads = (
        resource_census.get("projected_output_shard_count")
        if type(resource_census) is dict else None
    )
    if (
        type(maximum_output_shard_reads) is not int
        or not 1 <= maximum_output_shard_reads <= MAX_OUTPUT_SHARD_READS
    ):
        raise PreopenQcSubmissionError(
            "projected output shard read bound is missing or exceeds its ceiling"
        )
    if output_archive_root is not None:
        if (
            type(output_archive_root) is not type(Path())
            or not output_archive_root.is_absolute()
            or ".." in output_archive_root.parts
            or output_archive_root.name != OUTPUT_ARCHIVE_DIRECTORY_NAME
        ):
            raise PreopenQcSubmissionError(
                "output archive must be the exact absolute archive child"
            )
        try:
            parent = output_archive_root.parent.resolve(strict=True)
            parent_stat = parent.stat(follow_symlinks=False)
            if output_archive_root.parent != parent:
                raise PreopenQcSubmissionError(
                    "output archive parent must be its canonical absolute path"
                )
            try:
                leaf_stat = output_archive_root.lstat()
            except FileNotFoundError:
                leaf_stat = None
        except OSError as exc:
            raise PreopenQcSubmissionError(
                "output archive parent is unavailable"
            ) from exc
        if (
            not stat.S_ISDIR(parent_stat.st_mode)
            or stat.S_IMODE(parent_stat.st_mode) != 0o700
            or (hasattr(os, "getuid") and parent_stat.st_uid != os.getuid())
            or (
                leaf_stat is not None
                and (
                    stat.S_ISLNK(leaf_stat.st_mode)
                    or not stat.S_ISDIR(leaf_stat.st_mode)
                    or stat.S_IMODE(leaf_stat.st_mode) != 0o700
                    or (
                        hasattr(os, "getuid")
                        and leaf_stat.st_uid != os.getuid()
                    )
                )
            )
        ):
            raise PreopenQcSubmissionError(
                "output archive parent or existing leaf is not owner-only"
            )
        output_archive_root = parent / OUTPUT_ARCHIVE_DIRECTORY_NAME
    descriptors = [item.descriptor() for item in input_shards]
    if (
        manifest.get("shards") != descriptors
        or hashlib.sha256(input_manifest_bytes).hexdigest()
        != projection.input_manifest_sha256
        or len(input_manifest_bytes) != projection.input_manifest_byte_count
    ):
        raise PreopenQcSubmissionError("input bytes differ from source projection")
    entries = (
        _entry("input_manifest", projection.input_manifest_key, input_manifest_bytes),
        *(
            _entry("input_" + item.role, item.object_store_key, item.payload)
            for item in input_shards
        ),
    )
    if tuple(item.role.removeprefix("input_") for item in entries[1:]) != tuple(
        item.role for item in input_shards
    ):
        raise PreopenQcSubmissionError("upload entry role projection changed")
    record = {
        "schema": PLAN_SCHEMA, "plan_id": None, "plan_sha256": None,
        "organization_id_sha256": hashlib.sha256(organization_id.encode()).hexdigest(),
        "project_name": projection.project_name,
        "backtest_name": projection.backtest_name,
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "input_manifest_sha256": projection.input_manifest_sha256,
        "project_source_set_sha256": projection.project_source_set_sha256,
        "run_authority_id": run_authority.pin_id,
        "run_authority_sha256": run_authority.pin_sha256,
        "terminal_package_key": projection.terminal_package_key,
        "upload_entries": [item.to_record() for item in entries],
        "source_files": [item.to_record() for item in projection.source_files],
        "compile_poll_limit": MAX_COMPILE_POLLS,
        "status_poll_limit": MAX_STATUS_POLLS,
        "maximum_backtest_submissions": 1,
        "maximum_output_manifest_bytes": MAX_OUTPUT_MANIFEST_BYTES,
        "maximum_output_shard_reads": maximum_output_shard_reads,
        "maximum_output_shard_read_bytes": MAX_OUTPUT_SHARD_READ_BYTES,
        "output_archive_root": (
            None if output_archive_root is None else str(output_archive_root)
        ),
        "outcome_result_statistics_log_order_access": False,
    }
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    record["plan_id"] = "arv2-preopen-qc-plan-" + digest[:24]
    record["plan_sha256"] = digest
    return PreopenQcSubmissionPlan(
        plan_id=record["plan_id"], plan_sha256=digest,
        organization_id=organization_id, project_name=projection.project_name,
        backtest_name=projection.backtest_name,
        projection_id=projection.projection_id,
        projection_sha256=projection.projection_sha256,
        input_manifest_sha256=projection.input_manifest_sha256,
        project_source_set_sha256=projection.project_source_set_sha256,
        run_authority_id=run_authority.pin_id,
        run_authority_sha256=run_authority.pin_sha256,
        terminal_package_key=projection.terminal_package_key,
        upload_entries=entries, source_files=projection.source_files,
        compile_poll_limit=MAX_COMPILE_POLLS,
        status_poll_limit=MAX_STATUS_POLLS, maximum_backtest_submissions=1,
        maximum_output_manifest_bytes=MAX_OUTPUT_MANIFEST_BYTES,
        maximum_output_shard_reads=maximum_output_shard_reads,
        maximum_output_shard_read_bytes=MAX_OUTPUT_SHARD_READ_BYTES,
        output_archive_root=output_archive_root,
        input_manifest_bytes=input_manifest_bytes, input_shards=input_shards,
        projection=projection, run_authority=run_authority,
    )


def _physical_plan_record(
    *, upload_receipt, upload_plan, preuploaded_objects: tuple[object, ...],
    projection: PreopenControlQcProjection,
    run_authority: PreopenControlRunAuthority,
    maximum_output_shard_reads: int,
    output_archive_root: Path | None,
) -> dict[str, object]:
    return {
        "schema": PHYSICAL_PLAN_SCHEMA,
        "plan_id": None,
        "plan_sha256": None,
        "organization_id_sha256": hashlib.sha256(
            upload_plan.organization_id.encode("utf-8")
        ).hexdigest(),
        "project_name": projection.project_name,
        "backtest_name": projection.backtest_name,
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "input_manifest_sha256": projection.input_manifest_sha256,
        "project_source_set_sha256": projection.project_source_set_sha256,
        "run_authority_id": run_authority.pin_id,
        "run_authority_sha256": run_authority.pin_sha256,
        "terminal_package_key": projection.terminal_package_key,
        "physical_upload_receipt_id": upload_receipt.receipt_id,
        "physical_upload_receipt_sha256": upload_receipt.receipt_sha256,
        "physical_upload_plan_id": upload_receipt.plan_id,
        "physical_upload_plan_sha256": upload_receipt.plan_sha256,
        "physical_upload_permit_id": upload_receipt.permit_id,
        "physical_upload_permit_sha256": upload_receipt.permit_sha256,
        "physical_stream_id": upload_receipt.stream_id,
        "physical_stream_sha256": upload_receipt.stream_sha256,
        "input_source_inventory_sha256": (
            upload_receipt.input_source_inventory_sha256
        ),
        "preuploaded_object_inventory_sha256": hashlib.sha256(
            _canonical([item.to_record() for item in preuploaded_objects])
        ).hexdigest(),
        "preuploaded_input_shard_count": (
            upload_receipt.uploaded_input_shard_count
        ),
        "preuploaded_object_count": upload_receipt.uploaded_object_count,
        "preuploaded_byte_count": upload_receipt.uploaded_byte_count,
        "input_upload_disposition": PHYSICAL_INPUT_UPLOAD_DISPOSITION,
        "review_authorization": {
            "review_disposition": OWNER_REVIEW_WAIVER_DISPOSITION,
            "independent_review_complete": False,
            "authorization_basis": OWNER_REVIEW_WAIVER_BASIS,
            "owner_review_waiver_id": OWNER_REVIEW_WAIVER_ID,
            "owner_review_waiver_scope": OWNER_REVIEW_WAIVER_SCOPE,
            "post_first_formal_backtest_independent_review_required": True,
        },
        "source_files": [item.to_record() for item in projection.source_files],
        "qc_default_research_notebook_path": (
            QC_DEFAULT_RESEARCH_NOTEBOOK_PATH
        ),
        "maximum_default_notebook_deletions": 1,
        "compile_poll_limit": MAX_COMPILE_POLLS,
        "status_poll_limit": MAX_STATUS_POLLS,
        "maximum_backtest_submissions": 1,
        "maximum_output_manifest_bytes": MAX_OUTPUT_MANIFEST_BYTES,
        "maximum_output_shard_reads": maximum_output_shard_reads,
        "maximum_output_shard_read_bytes": MAX_OUTPUT_SHARD_READ_BYTES,
        "output_archive_root": (
            None if output_archive_root is None else str(output_archive_root)
        ),
        "preuploaded_payloads_retained": False,
        "input_objects_reuploaded": False,
        "outcome_result_statistics_log_order_access_authorized": False,
        "deployment_order_trading_authorized": False,
    }


def _physical_plan_fingerprint(value: PhysicalPreopenQcSubmissionPlan) -> str:
    public = {
        field.name: (
            None
            if field.name == "output_archive_root"
            and value.output_archive_root is None
            else str(value.output_archive_root)
            if field.name == "output_archive_root"
            else getattr(value, field.name)
        )
        for field in dataclasses.fields(value)
        if not field.name.startswith("_")
        and field.name not in {"source_files", "projection", "run_authority"}
    }
    return hashlib.sha256(_canonical({
        "public": public,
        "source_files_tuple_identity": id(value.source_files),
        "source_file_identities": [
            id(item) for item in value.source_files
        ],
        "preuploaded_objects_tuple_identity": id(
            value._preuploaded_objects
        ),
        "preuploaded_object_identities": [
            id(item) for item in value._preuploaded_objects
        ],
        "projection_identity": id(value.projection),
        "run_authority_identity": id(value.run_authority),
        "upload_receipt_identity": id(value._physical_upload_receipt),
        "receipt_requirer_identity": id(value._physical_receipt_requirer),
    })).hexdigest()


def _physical_output_archive_root(
    output_archive_root: Path | None,
) -> Path | None:
    if output_archive_root is None:
        return None
    if (
        type(output_archive_root) is not type(Path())
        or not output_archive_root.is_absolute()
        or ".." in output_archive_root.parts
        or output_archive_root.name != OUTPUT_ARCHIVE_DIRECTORY_NAME
    ):
        raise PreopenQcSubmissionError(
            "physical pre-open output archive must be the exact absolute archive child"
        )
    try:
        parent = output_archive_root.parent.resolve(strict=True)
        parent_stat = parent.stat(follow_symlinks=False)
        if output_archive_root.parent != parent:
            raise PreopenQcSubmissionError(
                "physical pre-open output archive parent is not canonical"
            )
        try:
            leaf_stat = output_archive_root.lstat()
        except FileNotFoundError:
            leaf_stat = None
    except OSError as exc:
        raise PreopenQcSubmissionError(
            "physical pre-open output archive parent is unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(parent_stat.st_mode)
        or stat.S_IMODE(parent_stat.st_mode) != 0o700
        or (hasattr(os, "getuid") and parent_stat.st_uid != os.getuid())
        or (
            leaf_stat is not None
            and (
                stat.S_ISLNK(leaf_stat.st_mode)
                or not stat.S_ISDIR(leaf_stat.st_mode)
                or stat.S_IMODE(leaf_stat.st_mode) != 0o700
                or (
                    hasattr(os, "getuid")
                    and leaf_stat.st_uid != os.getuid()
                )
            )
        )
    ):
        raise PreopenQcSubmissionError(
            "physical pre-open output archive parent or leaf is not owner-only"
        )
    return parent / OUTPUT_ARCHIVE_DIRECTORY_NAME


def build_preopen_qc_submission_plan_from_physical_upload(
    *, physical_upload_receipt: object,
    output_archive_root: Path | None = None,
) -> PhysicalPreopenQcSubmissionPlan:
    """Bind a process-authenticated completed upload without retaining shards."""

    try:
        physical = importlib.import_module(
            "research.analyst_revisions_v2_qc.physical_preopen_submission_adapter"
        )
        receipt_requirer = physical.require_physical_preopen_upload_receipt
        upload_receipt = receipt_requirer(physical_upload_receipt)
    except Exception as exc:
        raise PreopenQcSubmissionError(
            "physical pre-open upload receipt is not process-authenticated"
        ) from exc
    upload_plan = upload_receipt._plan
    projection = upload_plan._projection
    run_authority = upload_plan._run_authority
    input_manifest_bytes = upload_plan._input_manifest_bytes
    _safe(upload_plan.organization_id, "organization_id")
    _rebuild_projection(projection, input_manifest_bytes, run_authority)
    output_archive_root = _physical_output_archive_root(output_archive_root)
    try:
        manifest = json.loads(input_manifest_bytes.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise PreopenQcSubmissionError(
            "physical pre-open activated input manifest is not JSON"
        ) from exc
    resource_census = manifest.get("resource_census")
    maximum_output_shard_reads = (
        resource_census.get("projected_output_shard_count")
        if type(resource_census) is dict
        else None
    )
    if (
        _canonical(manifest) != input_manifest_bytes
        or type(maximum_output_shard_reads) is not int
        or not 1 <= maximum_output_shard_reads <= MAX_OUTPUT_SHARD_READS
    ):
        raise PreopenQcSubmissionError(
            "physical pre-open activated manifest or output census changed"
        )
    descriptors = manifest.get("shards")
    preuploaded_objects = upload_plan.upload_objects
    if (
        type(descriptors) is not list
        or type(preuploaded_objects) is not tuple
        or len(preuploaded_objects) != len(descriptors) + 1
        or upload_receipt.uploaded_input_shard_count != len(descriptors)
        or upload_receipt.uploaded_object_count != len(preuploaded_objects)
        or upload_receipt.uploaded_byte_count
        != sum(item.byte_count for item in preuploaded_objects)
        or upload_receipt.input_manifest_sha256
        != projection.input_manifest_sha256
        or upload_receipt.input_source_inventory_sha256
        != manifest.get("input_source_inventory_sha256")
        or upload_receipt.activated_manifest_published_last is not True
        or upload_receipt.maximum_backtest_submissions != 0
        or upload_receipt.outcome_result_statistics_log_order_accessed is not False
        or upload_receipt.deployment_order_trading_authorized is not False
    ):
        raise PreopenQcSubmissionError(
            "physical pre-open upload receipt census or gates changed"
        )
    for ordinal, (descriptor, uploaded) in enumerate(
        zip(descriptors, preuploaded_objects[:-1], strict=True)
    ):
        if (
            type(descriptor) is not dict
            or uploaded.role != "input_" + str(descriptor.get("role"))
            or uploaded.object_store_key != descriptor.get("object_store_key")
            or uploaded.content_sha256 != descriptor.get("compressed_sha256")
            or uploaded.byte_count != descriptor.get("compressed_byte_count")
        ):
            raise PreopenQcSubmissionError(
                f"physical pre-open preuploaded shard {ordinal} lineage changed"
            )
    activated = preuploaded_objects[-1]
    if (
        activated.role != "input_manifest"
        or activated.object_store_key != projection.input_manifest_key
        or activated.content_sha256 != projection.input_manifest_sha256
        or activated.byte_count != projection.input_manifest_byte_count
    ):
        raise PreopenQcSubmissionError(
            "physical pre-open preuploaded manifest lineage changed"
        )
    record = _physical_plan_record(
        upload_receipt=upload_receipt,
        upload_plan=upload_plan,
        preuploaded_objects=preuploaded_objects,
        projection=projection,
        run_authority=run_authority,
        maximum_output_shard_reads=maximum_output_shard_reads,
        output_archive_root=output_archive_root,
    )
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    record["plan_id"] = "arv2-physical-preopen-qc-plan-" + digest[:24]
    record["plan_sha256"] = digest
    value = PhysicalPreopenQcSubmissionPlan(
        plan_id=record["plan_id"],
        plan_sha256=digest,
        organization_id=upload_plan.organization_id,
        project_name=projection.project_name,
        backtest_name=projection.backtest_name,
        projection_id=projection.projection_id,
        projection_sha256=projection.projection_sha256,
        input_manifest_sha256=projection.input_manifest_sha256,
        project_source_set_sha256=projection.project_source_set_sha256,
        run_authority_id=run_authority.pin_id,
        run_authority_sha256=run_authority.pin_sha256,
        terminal_package_key=projection.terminal_package_key,
        physical_upload_receipt_id=upload_receipt.receipt_id,
        physical_upload_receipt_sha256=upload_receipt.receipt_sha256,
        physical_upload_plan_id=upload_receipt.plan_id,
        physical_upload_plan_sha256=upload_receipt.plan_sha256,
        physical_upload_permit_id=upload_receipt.permit_id,
        physical_upload_permit_sha256=upload_receipt.permit_sha256,
        physical_stream_id=upload_receipt.stream_id,
        physical_stream_sha256=upload_receipt.stream_sha256,
        input_source_inventory_sha256=(
            upload_receipt.input_source_inventory_sha256
        ),
        preuploaded_object_inventory_sha256=record[
            "preuploaded_object_inventory_sha256"
        ],
        preuploaded_input_shard_count=(
            upload_receipt.uploaded_input_shard_count
        ),
        preuploaded_object_count=upload_receipt.uploaded_object_count,
        preuploaded_byte_count=upload_receipt.uploaded_byte_count,
        input_upload_disposition=PHYSICAL_INPUT_UPLOAD_DISPOSITION,
        review_disposition=OWNER_REVIEW_WAIVER_DISPOSITION,
        independent_review_complete=False,
        authorization_basis=OWNER_REVIEW_WAIVER_BASIS,
        owner_review_waiver_id=OWNER_REVIEW_WAIVER_ID,
        owner_review_waiver_scope=OWNER_REVIEW_WAIVER_SCOPE,
        post_first_formal_backtest_independent_review_required=True,
        source_files=projection.source_files,
        compile_poll_limit=MAX_COMPILE_POLLS,
        status_poll_limit=MAX_STATUS_POLLS,
        maximum_backtest_submissions=1,
        maximum_output_manifest_bytes=MAX_OUTPUT_MANIFEST_BYTES,
        maximum_output_shard_reads=maximum_output_shard_reads,
        maximum_output_shard_read_bytes=MAX_OUTPUT_SHARD_READ_BYTES,
        output_archive_root=output_archive_root,
        outcome_result_statistics_log_order_access_authorized=False,
        deployment_order_trading_authorized=False,
        _preuploaded_objects=preuploaded_objects,
        _input_manifest_bytes=input_manifest_bytes,
        projection=projection,
        run_authority=run_authority,
        _physical_upload_receipt=upload_receipt,
        _physical_receipt_requirer=receipt_requirer,
    )
    reference = weakref.ref(
        value,
        lambda _reference, key=id(value): _PHYSICAL_PLAN_AUTHORITIES.pop(
            key, None
        ),
    )
    with _PHYSICAL_PLAN_AUTHORITY_LOCK:
        _PHYSICAL_PLAN_AUTHORITIES[id(value)] = (
            reference,
            _physical_plan_fingerprint(value),
            os.getpid(),
        )
    return value


def require_preopen_qc_physical_submission_plan(
    value: PhysicalPreopenQcSubmissionPlan,
) -> PhysicalPreopenQcSubmissionPlan:
    if type(value) is not PhysicalPreopenQcSubmissionPlan:
        raise PreopenQcSubmissionError(
            "physical pre-open QC submission plan type changed"
        )
    with _PHYSICAL_PLAN_AUTHORITY_LOCK:
        registered = _PHYSICAL_PLAN_AUTHORITIES.get(id(value))
    if (
        os.getpid() != _PHYSICAL_PLAN_AUTHORITY_PID
        or registered is None
        or registered[0]() is not value
        or registered[2] != os.getpid()
    ):
        raise PreopenQcSubmissionError(
            "physical pre-open QC submission plan lacks process authority"
        )
    if (
        type(value.source_files) is not tuple
        or type(value._preuploaded_objects) is not tuple
        or type(value._input_manifest_bytes) is not bytes
        or type(value.output_archive_root) not in (type(None), type(Path()))
    ):
        raise PreopenQcSubmissionError(
            "physical pre-open QC submission plan container types changed"
        )
    try:
        fingerprint = _physical_plan_fingerprint(value)
    except Exception as exc:
        raise PreopenQcSubmissionError(
            "physical pre-open QC submission plan scalar types changed"
        ) from exc
    if registered[1] != fingerprint:
        raise PreopenQcSubmissionError(
            "physical pre-open QC submission plan changed"
        )
    try:
        receipt = value._physical_receipt_requirer(
            value._physical_upload_receipt
        )
    except Exception as exc:
        raise PreopenQcSubmissionError(
            "physical pre-open upload receipt changed after plan construction"
        ) from exc
    upload_plan = receipt._plan
    projection = upload_plan._projection
    run_authority = upload_plan._run_authority
    input_manifest_bytes = upload_plan._input_manifest_bytes
    try:
        manifest = json.loads(input_manifest_bytes.decode("utf-8"))
        maximum_output_shard_reads = manifest["resource_census"][
            "projected_output_shard_count"
        ]
        expected_root = _physical_output_archive_root(
            value.output_archive_root
        )
        expected_record = _physical_plan_record(
            upload_receipt=receipt,
            upload_plan=upload_plan,
            preuploaded_objects=upload_plan.upload_objects,
            projection=projection,
            run_authority=run_authority,
            maximum_output_shard_reads=maximum_output_shard_reads,
            output_archive_root=expected_root,
        )
        expected_digest = hashlib.sha256(
            _canonical(expected_record)
        ).hexdigest()
    except Exception as exc:
        raise PreopenQcSubmissionError(
            "physical pre-open upload lineage changed after plan construction"
        ) from exc
    if (
        value.plan_id
        != "arv2-physical-preopen-qc-plan-" + expected_digest[:24]
        or value.plan_sha256 != expected_digest
        or value._preuploaded_objects is not upload_plan.upload_objects
        or value._input_manifest_bytes is not input_manifest_bytes
        or value.projection is not projection
        or value.run_authority is not run_authority
        or expected_root != value.output_archive_root
    ):
        raise PreopenQcSubmissionError(
            "physical pre-open QC submission plan changed"
        )
    return value


def require_preopen_qc_submission_plan(
    value: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
) -> PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan:
    if type(value) is PhysicalPreopenQcSubmissionPlan:
        return require_preopen_qc_physical_submission_plan(value)
    if type(value) is not PreopenQcSubmissionPlan:
        raise PreopenQcSubmissionError("pre-open submission plan type changed")
    rebuilt = build_preopen_qc_submission_plan(
        projection=value.projection,
        input_manifest_bytes=value.input_manifest_bytes,
        input_shards=value.input_shards, run_authority=value.run_authority,
        organization_id=value.organization_id,
        output_archive_root=value.output_archive_root,
    )
    if rebuilt != value:
        raise PreopenQcSubmissionError("pre-open submission plan changed")
    return value


def _render_preopen_qc_execution_authority_candidate(
    plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
    host_closure: PreopenQcHostClosureBinding,
) -> bytes:
    require_preopen_qc_submission_plan(plan)
    if type(plan) is PhysicalPreopenQcSubmissionPlan:
        verify_physical_preopen_qc_host_closure_live(host_closure)
        return _canonical({
            "schema": PHYSICAL_EXECUTION_AUTHORITY_SCHEMA,
            "plan_id": plan.plan_id,
            "plan_sha256": plan.plan_sha256,
            "review_authorization": {
                "review_disposition": plan.review_disposition,
                "independent_review_complete": plan.independent_review_complete,
                "authorization_basis": plan.authorization_basis,
                "owner_review_waiver_id": plan.owner_review_waiver_id,
                "owner_review_waiver_scope": plan.owner_review_waiver_scope,
                "post_first_formal_backtest_independent_review_required": (
                    plan.post_first_formal_backtest_independent_review_required
                ),
            },
            "physical_upload_receipt_id": plan.physical_upload_receipt_id,
            "physical_upload_receipt_sha256": (
                plan.physical_upload_receipt_sha256
            ),
            "physical_upload_plan_id": plan.physical_upload_plan_id,
            "physical_upload_plan_sha256": plan.physical_upload_plan_sha256,
            "physical_upload_permit_id": plan.physical_upload_permit_id,
            "physical_upload_permit_sha256": (
                plan.physical_upload_permit_sha256
            ),
            "physical_stream_id": plan.physical_stream_id,
            "physical_stream_sha256": plan.physical_stream_sha256,
            "input_source_inventory_sha256": (
                plan.input_source_inventory_sha256
            ),
            "preuploaded_object_inventory_sha256": (
                plan.preuploaded_object_inventory_sha256
            ),
            "preuploaded_input_shard_count": (
                plan.preuploaded_input_shard_count
            ),
            "preuploaded_object_count": plan.preuploaded_object_count,
            "preuploaded_byte_count": plan.preuploaded_byte_count,
            "input_upload_disposition": plan.input_upload_disposition,
            "projection_id": plan.projection_id,
            "projection_sha256": plan.projection_sha256,
            "input_manifest_sha256": plan.input_manifest_sha256,
            "project_source_set_sha256": plan.project_source_set_sha256,
            "run_authority_id": plan.run_authority_id,
            "run_authority_sha256": plan.run_authority_sha256,
            "organization_id_sha256": hashlib.sha256(
                plan.organization_id.encode("utf-8")
            ).hexdigest(),
            "project_name": plan.project_name,
            "backtest_name": plan.backtest_name,
            "terminal_package_key": plan.terminal_package_key,
            "qc_default_research_notebook_path": (
                QC_DEFAULT_RESEARCH_NOTEBOOK_PATH
            ),
            "maximum_default_notebook_deletions": 1,
            "output_archive_root": (
                None
                if plan.output_archive_root is None
                else str(plan.output_archive_root)
            ),
            "host_closure": {
                "closure_id": host_closure.closure_id,
                "closure_sha256": host_closure.closure_sha256,
                "sources": [
                    item.to_record() for item in host_closure.sources
                ],
            },
            "actions": list(PHYSICAL_PREOPEN_EXECUTION_ACTIONS),
            "object_store_key_allowlist": [
                item.object_store_key for item in plan._preuploaded_objects
            ],
            "maximum_backtest_submissions": 1,
            "maximum_output_manifest_bytes": (
                plan.maximum_output_manifest_bytes
            ),
            "maximum_output_shard_reads": plan.maximum_output_shard_reads,
            "maximum_output_shard_read_bytes": (
                plan.maximum_output_shard_read_bytes
            ),
            "preuploaded_payloads_retained": False,
            "input_objects_reuploaded": False,
            "outcome_result_statistics_log_order_access": False,
            "deployment_order_trading_authorized": False,
        })
    verify_preopen_qc_host_closure_live(host_closure)
    return _canonical({
        "schema": EXECUTION_AUTHORITY_SCHEMA,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "projection_id": plan.projection_id,
        "projection_sha256": plan.projection_sha256,
        "input_manifest_sha256": plan.input_manifest_sha256,
        "project_source_set_sha256": plan.project_source_set_sha256,
        "run_authority_id": plan.run_authority_id,
        "run_authority_sha256": plan.run_authority_sha256,
        "organization_id_sha256": hashlib.sha256(
            plan.organization_id.encode("utf-8")
        ).hexdigest(),
        "project_name": plan.project_name,
        "backtest_name": plan.backtest_name,
        "terminal_package_key": plan.terminal_package_key,
        "output_archive_root": (
            None if plan.output_archive_root is None
            else str(plan.output_archive_root)
        ),
        "host_closure": {
            "closure_id": host_closure.closure_id,
            "closure_sha256": host_closure.closure_sha256,
            "sources": [item.to_record() for item in host_closure.sources],
        },
        "actions": list(PREOPEN_EXECUTION_ACTIONS),
        "maximum_backtest_submissions": 1,
        "maximum_output_manifest_bytes": plan.maximum_output_manifest_bytes,
        "maximum_output_shard_reads": plan.maximum_output_shard_reads,
        "maximum_output_shard_read_bytes": plan.maximum_output_shard_read_bytes,
        "manifest_persisted_last": True,
        "outcome_result_statistics_log_order_access": False,
    })


def render_preopen_qc_execution_authority_candidate(
    plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
) -> bytes:
    """Render the exact bytes the owner must sign for this pre-open QC run."""

    closure = (
        build_physical_preopen_qc_host_closure_binding()
        if type(plan) is PhysicalPreopenQcSubmissionPlan
        else build_preopen_qc_host_closure_binding()
    )
    return _render_preopen_qc_execution_authority_candidate(plan, closure)


@dataclasses.dataclass(frozen=True, slots=True)
class PreopenQcSubmissionPermit:
    permit_id: str
    permit_sha256: str
    plan_id: str
    plan_sha256: str
    started_at_utc: str
    submission_attempt_count: int
    ambiguous_submission_consumes_permit: bool
    retry_authorized: bool
    permit_path: Path
    _permit_bytes: bytes = dataclasses.field(repr=False)


def _spend_permit(
    plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
    ledger_directory: Path, started_at_utc: str,
) -> PreopenQcSubmissionPermit:
    require_preopen_qc_submission_plan(plan)
    _utc(started_at_utc, "submission started_at")
    if type(ledger_directory) is not type(Path()) or not ledger_directory.is_absolute():
        raise PreopenQcSubmissionError("permit directory must be an absolute Path")
    directory = ledger_directory.resolve(strict=True)
    mode = stat.S_IMODE(directory.stat().st_mode)
    if not directory.is_dir() or mode & 0o077:
        raise PreopenQcSubmissionError("permit directory must be private")
    path = directory / PERMIT_FILENAME
    record = {
        "schema": PERMIT_SCHEMA, "permit_id": None, "permit_sha256": None,
        "plan_id": plan.plan_id, "plan_sha256": plan.plan_sha256,
        "started_at_utc": started_at_utc, "submission_attempt_count": 1,
        "ambiguous_submission_consumes_permit": True,
        "retry_authorized": False,
    }
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    record["permit_id"] = "arv2-preopen-qc-permit-" + digest[:24]
    record["permit_sha256"] = digest
    payload = _canonical(record)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise PreopenQcSubmissionLocked(
            "permit", str(record["permit_id"]), "permit already spent"
        ) from exc
    try:
        written = os.write(descriptor, payload)
        os.fsync(descriptor)
        if written != len(payload):
            raise PreopenQcSubmissionLocked(
                "permit", str(record["permit_id"]), "permit write was incomplete"
            )
    finally:
        os.close(descriptor)
    return PreopenQcSubmissionPermit(
        permit_id=str(record["permit_id"]), permit_sha256=digest,
        plan_id=plan.plan_id, plan_sha256=plan.plan_sha256,
        started_at_utc=started_at_utc, submission_attempt_count=1,
        ambiguous_submission_consumes_permit=True, retry_authorized=False,
        permit_path=path, _permit_bytes=payload,
    )


def require_preopen_qc_submission_permit(
    permit: PreopenQcSubmissionPermit,
    plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
) -> PreopenQcSubmissionPermit:
    require_preopen_qc_submission_plan(plan)
    if type(permit) is not PreopenQcSubmissionPermit:
        raise PreopenQcSubmissionError("pre-open submission permit type changed")
    try:
        payload = permit.permit_path.read_bytes()
    except OSError as exc:
        raise PreopenQcSubmissionError("pre-open permit is unavailable") from exc
    if (
        payload != permit._permit_bytes
        or stat.S_IMODE(permit.permit_path.stat().st_mode) & 0o077
        or permit.plan_id != plan.plan_id or permit.plan_sha256 != plan.plan_sha256
        or permit.submission_attempt_count != 1
        or permit.ambiguous_submission_consumes_permit is not True
        or permit.retry_authorized is not False
    ):
        raise PreopenQcSubmissionError("pre-open submission permit changed")
    raw = json.loads(payload)
    seed = dict(raw)
    seed["permit_id"] = None
    seed["permit_sha256"] = None
    if (
        _canonical(raw) != payload
        or raw.get("permit_id") != permit.permit_id
        or raw.get("permit_sha256") != permit.permit_sha256
        or hashlib.sha256(_canonical(seed)).hexdigest() != permit.permit_sha256
    ):
        raise PreopenQcSubmissionError("pre-open permit identity changed")
    return permit


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PreopenQcLaunchReceipt:
    receipt_id: str
    receipt_sha256: str
    permit_id: str
    permit_sha256: str
    plan_id: str
    plan_sha256: str
    project_id: int
    compile_id: str
    backtest_id: str
    backtest_name: str
    initial_status: str
    uploaded_object_count: int
    uploaded_source_count: int
    submission_count: int


def _identified(schema: str, prefix: str, record: dict[str, object]):
    digest = hashlib.sha256(_canonical({"schema": schema, **record})).hexdigest()
    return prefix + digest[:24], digest


def _launch(
    plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
    permit: PreopenQcSubmissionPermit,
    project_id: int, compile_id: str, backtest_id: str, status: str,
) -> PreopenQcLaunchReceipt:
    uploaded_object_count = (
        0
        if type(plan) is PhysicalPreopenQcSubmissionPlan
        else len(plan.upload_entries)
    )
    record = {
        "permit_id": permit.permit_id, "permit_sha256": permit.permit_sha256,
        "plan_id": plan.plan_id, "plan_sha256": plan.plan_sha256,
        "project_id": project_id, "compile_id": compile_id,
        "backtest_id": backtest_id, "backtest_name": plan.backtest_name,
        "initial_status": status,
        "uploaded_object_count": uploaded_object_count,
        "uploaded_source_count": len(plan.source_files),
        "submission_count": 1,
    }
    identity, digest = _identified(LAUNCH_SCHEMA, "arv2-preopen-qc-launch-", record)
    return PreopenQcLaunchReceipt(receipt_id=identity, receipt_sha256=digest, **record)


def _register_launch_process_return(
    launch: PreopenQcLaunchReceipt,
) -> PreopenQcLaunchReceipt:
    _process_receipt_authority_register("launch", launch)
    return launch


def _require_launch_receipt(
    launch: PreopenQcLaunchReceipt,
    plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
    permit: PreopenQcSubmissionPermit,
) -> PreopenQcLaunchReceipt:
    registered = _process_receipt_authority_current("launch", launch)
    if (
        type(launch) is not PreopenQcLaunchReceipt
        or registered is None
        or registered[1] != launch.receipt_sha256
        or type(launch.project_id) is not int
        or launch.project_id < 1
        or launch != _launch(
            plan, permit, launch.project_id, launch.compile_id,
            launch.backtest_id, launch.initial_status,
        )
    ):
        raise PreopenQcSubmissionError("launch receipt changed")
    return launch


def _wait(seconds: int) -> None:
    time.sleep(seconds)


def _execute_preopen_qc_submission_once_impl(
    *, plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
    client: FormalQcTransport,
    ledger_directory: Path, started_at_utc: str,
    owner_signature: OwnerSignatureAuthority | None,
    _transport_capability_minter, _execute_preuploaded_impl=None,
) -> tuple[PreopenQcSubmissionPermit, PreopenQcLaunchReceipt]:
    host_closure = (
        build_physical_preopen_qc_host_closure_binding()
        if type(plan) is PhysicalPreopenQcSubmissionPlan
        else build_preopen_qc_host_closure_binding()
    )
    _require_external_execution_trust_root(
        owner_signature,
        _render_preopen_qc_execution_authority_candidate(plan, host_closure),
    )
    if type(plan) is PhysicalPreopenQcSubmissionPlan:
        verify_physical_preopen_qc_host_closure_live(host_closure)
    else:
        verify_preopen_qc_host_closure_live(host_closure)
    require_preopen_qc_submission_plan(plan)
    formal._require_concrete_transport(client)
    if (
        type(plan) is PhysicalPreopenQcSubmissionPlan
        and type(_execute_preuploaded_impl) is not type(lambda: None)
    ):
        raise PreopenQcSubmissionError(
            "physical pre-open execution authority is unavailable"
        )
    permit = _spend_permit(plan, ledger_directory, started_at_utc)
    if type(plan) is PhysicalPreopenQcSubmissionPlan:
        capability = _transport_capability_minter(
            transport=client,
            scope="submission",
            binding_record={
                "schema": "arv2-physical-preopen-qc-submission-capability-v1",
                "plan_sha256": plan.plan_sha256,
                "permit_sha256": permit.permit_sha256,
                "physical_upload_receipt_sha256": (
                    plan.physical_upload_receipt_sha256
                ),
                "preuploaded_object_inventory_sha256": (
                    plan.preuploaded_object_inventory_sha256
                ),
                "review_disposition": plan.review_disposition,
                "independent_review_complete": (
                    plan.independent_review_complete
                ),
                "owner_review_waiver_scope": plan.owner_review_waiver_scope,
                "input_objects_reuploaded": False,
            },
            call_budget={
                "authenticate": 1,
                "object/properties": plan.preuploaded_object_count,
                "projects/read": 2,
                "projects/create": 1,
                "files/read": 2,
                "files/delete": 1,
                "files/create": len(plan.source_files),
                "compile/create": 1,
                "compile/read": plan.compile_poll_limit,
                "backtests/create": 1,
            },
        )
        try:
            launch = _execute_preuploaded_impl(
                plan=plan,
                client=client,
                host_closure=host_closure,
                permit=permit,
                capability=capability,
            )
            return permit, _register_launch_process_return(launch)
        except PreopenQcSubmissionLocked:
            raise
        except PreopenQcSubmissionError as exc:
            raise PreopenQcSubmissionLocked(
                "physical_submission", permit.permit_id, str(exc)
            ) from exc
        except Exception as exc:
            raise PreopenQcSubmissionLocked(
                "physical_submission", permit.permit_id, type(exc).__name__
            ) from exc
    capability = _transport_capability_minter(
        transport=client, scope="submission",
        binding_record={
            "schema": "arv2-preopen-qc-submission-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
        },
        call_budget={
            "authenticate": 1, "projects/read": 2, "projects/create": 1,
            "object/set": len(plan.upload_entries),
            "object/properties": len(plan.upload_entries),
            "files/read": 2, "files/create": len(plan.source_files),
            "compile/create": 1, "compile/read": plan.compile_poll_limit,
            "backtests/create": 1,
        },
    )
    try:
        _preopen_transport_call(
            host_closure, client, capability, "_request_json", "authenticate", {}
        )
        inventory = formal._read_project_inventory(_preopen_transport_call(
            host_closure, client, capability, "_request_json", "projects/read", {}
        ))
        if any(
            type(item) is dict and item.get("name") == plan.project_name
            for item in inventory
        ):
            raise PreopenQcSubmissionError("exact pre-open project already exists")
        project = formal._created_project(
            _preopen_transport_call(
                host_closure, client, capability, "_request_json", "projects/create",
                {"name": plan.project_name, "language": "Py"},
            ), name=plan.project_name, organization_id=plan.organization_id,
        )
        project_id = int(project["projectId"])
        exact = formal._read_project_inventory(_preopen_transport_call(
            host_closure, client, capability, "_request_json", "projects/read",
            {"projectId": project_id},
        ))
        if len(exact) != 1:
            raise PreopenQcSubmissionError("created project identity is ambiguous")
        formal._project_record(
            exact[0], name=plan.project_name,
            organization_id=plan.organization_id,
        )
        for entry in plan.upload_entries:
            _preopen_transport_call(
                host_closure, client, capability, "_set_object_multipart",
                plan.organization_id, entry.object_store_key, entry.payload,
            )
            formal._object_metadata_matches(
                _preopen_transport_call(
                    host_closure, client, capability, "_read_object_properties",
                    plan.organization_id, entry.object_store_key,
                ), entry,
            )
        existing = formal._read_files(
            _preopen_transport_call(
                host_closure, client, capability, "_request_json", "files/read",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        if existing:
            raise PreopenQcSubmissionError("new pre-open project is not empty")
        for source in plan.source_files:
            _preopen_transport_call(
                host_closure, client, capability, "_request_json", "files/create",
                {
                    "projectId": project_id, "name": source.project_path,
                    "content": source.content.decode("utf-8"),
                },
            )
        observed = formal._read_files(
            _preopen_transport_call(
                host_closure, client, capability, "_request_json", "files/read",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        if set(observed) != {item.project_path for item in plan.source_files}:
            raise PreopenQcSubmissionError("project source inventory changed")
        for source in plan.source_files:
            payload = observed[source.project_path].encode("utf-8")
            if (
                len(payload) != source.byte_count
                or hashlib.sha256(payload).hexdigest() != source.content_sha256
            ):
                raise PreopenQcSubmissionError("project source bytes changed")
        compile_id = formal._compile_id(_preopen_transport_call(
            host_closure, client, capability, "_request_json", "compile/create",
            {"projectId": project_id},
        ), expected_project_id=project_id)
        compile_state = ""
        for index in range(plan.compile_poll_limit):
            compile_state = formal._compile_state(
                _preopen_transport_call(
                    host_closure, client, capability, "_request_json", "compile/read",
                    {"projectId": project_id, "compileId": compile_id},
                ), compile_id,
            )
            if compile_state in formal.COMPILE_TERMINAL_STATES:
                break
            if index + 1 == plan.compile_poll_limit:
                raise PreopenQcSubmissionError("compile polling exhausted")
            _wait(COMPILE_POLL_SECONDS)
        if compile_state != "BuildSuccess":
            raise PreopenQcSubmissionError("pre-open project did not compile")
        backtest_id, status = formal._created_backtest(
            _preopen_transport_call(
                host_closure, client, capability, "_request_json", "backtests/create",
                {
                    "projectId": project_id, "compileId": compile_id,
                    "backtestName": plan.backtest_name,
                },
            ), project_id=project_id, name=plan.backtest_name,
        )
        return permit, _register_launch_process_return(
            _launch(
                plan, permit, project_id, compile_id, backtest_id, status
            )
        )
    except Exception as exc:
        raise PreopenQcSubmissionLocked(
            "submission", permit.permit_id, type(exc).__name__
        ) from exc


def _execute_preuploaded_preopen_qc_submission_once_impl(
    *, plan: PhysicalPreopenQcSubmissionPlan, client: FormalQcTransport,
    host_closure: PreopenQcHostClosureBinding,
    permit: PreopenQcSubmissionPermit,
    capability: object,
) -> PreopenQcLaunchReceipt:
    """Use metadata-only input checks, then create, compile, and launch."""

    try:
        _preopen_transport_call(
            host_closure,
            client,
            capability,
            "_request_json",
            "authenticate",
            {},
        )
        for ordinal, expected in enumerate(plan._preuploaded_objects):
            try:
                metadata = _preopen_transport_call(
                    host_closure,
                    client,
                    capability,
                    "_read_object_properties",
                    plan.organization_id,
                    expected.object_store_key,
                )
                formal._object_metadata_matches(metadata, expected)
            except Exception as exc:
                raise PreopenQcSubmissionError(
                    f"physical pre-open preuploaded object {ordinal} metadata changed"
                ) from exc
        inventory = formal._read_project_inventory(
            _preopen_transport_call(
                host_closure,
                client,
                capability,
                "_request_json",
                "projects/read",
                {},
            )
        )
        if any(
            type(item) is dict and item.get("name") == plan.project_name
            for item in inventory
        ):
            raise PreopenQcSubmissionError(
                "exact physical pre-open project already exists"
            )
        project = formal._created_project(
            _preopen_transport_call(
                host_closure,
                client,
                capability,
                "_request_json",
                "projects/create",
                {"name": plan.project_name, "language": "Py"},
            ),
            name=plan.project_name,
            organization_id=plan.organization_id,
        )
        project_id = int(project["projectId"])
        exact = formal._read_project_inventory(
            _preopen_transport_call(
                host_closure,
                client,
                capability,
                "_request_json",
                "projects/read",
                {"projectId": project_id},
            )
        )
        if len(exact) != 1:
            raise PreopenQcSubmissionError(
                "created physical pre-open project identity is ambiguous"
            )
        created_project = formal._project_record(
            exact[0],
            name=plan.project_name,
            organization_id=plan.organization_id,
        )
        if created_project["projectId"] != project_id:
            raise PreopenQcSubmissionError(
                "created physical pre-open project identifier changed"
            )
        existing = formal._read_files(
            _preopen_transport_call(
                host_closure,
                client,
                capability,
                "_request_json",
                "files/read",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        if set(existing) - {QC_DEFAULT_RESEARCH_NOTEBOOK_PATH}:
            raise PreopenQcSubmissionError(
                "new physical pre-open project contains an unprojected source"
            )
        if QC_DEFAULT_RESEARCH_NOTEBOOK_PATH in existing:
            formal._success(
                _preopen_transport_call(
                    host_closure,
                    client,
                    capability,
                    "_request_json",
                    "files/delete",
                    {
                        "projectId": project_id,
                        "name": QC_DEFAULT_RESEARCH_NOTEBOOK_PATH,
                    },
                ),
                frozenset({"success", "errors", "messages"}),
                "files/delete",
            )
        for source in plan.source_files:
            formal._success(
                _preopen_transport_call(
                    host_closure,
                    client,
                    capability,
                    "_request_json",
                    "files/create",
                    {
                        "projectId": project_id,
                        "name": source.project_path,
                        "content": source.content.decode("utf-8"),
                    },
                ),
                frozenset({"success", "errors", "messages"}),
                "files/create",
            )
        observed = formal._read_files(
            _preopen_transport_call(
                host_closure,
                client,
                capability,
                "_request_json",
                "files/read",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        if set(observed) != {
            item.project_path for item in plan.source_files
        }:
            raise PreopenQcSubmissionError(
                "physical pre-open project source inventory changed"
            )
        for source in plan.source_files:
            payload = observed[source.project_path].encode("utf-8")
            if (
                len(payload) != source.byte_count
                or hashlib.sha256(payload).hexdigest()
                != source.content_sha256
            ):
                raise PreopenQcSubmissionError(
                    "physical pre-open project source bytes changed"
                )
        compile_id = formal._compile_id(
            _preopen_transport_call(
                host_closure,
                client,
                capability,
                "_request_json",
                "compile/create",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        compile_state = ""
        for index in range(plan.compile_poll_limit):
            compile_state = formal._compile_state(
                _preopen_transport_call(
                    host_closure,
                    client,
                    capability,
                    "_request_json",
                    "compile/read",
                    {"projectId": project_id, "compileId": compile_id},
                ),
                compile_id,
            )
            if compile_state in formal.COMPILE_TERMINAL_STATES:
                break
            if index + 1 == plan.compile_poll_limit:
                raise PreopenQcSubmissionError(
                    "physical pre-open compile polling exhausted"
                )
            _wait(COMPILE_POLL_SECONDS)
        if compile_state != "BuildSuccess":
            raise PreopenQcSubmissionError(
                "physical pre-open project did not compile"
            )
        backtest_id, status = formal._created_backtest(
            _preopen_transport_call(
                host_closure,
                client,
                capability,
                "_request_json",
                "backtests/create",
                {
                    "projectId": project_id,
                    "compileId": compile_id,
                    "backtestName": plan.backtest_name,
                },
            ),
            project_id=project_id,
            name=plan.backtest_name,
        )
        return _launch(
            plan,
            permit,
            project_id,
            compile_id,
            backtest_id,
            status,
        )
    except PreopenQcSubmissionError:
        raise
    except Exception as exc:
        raise PreopenQcSubmissionLocked(
            "physical_submission", permit.permit_id, type(exc).__name__
        ) from exc


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PreopenQcTerminalStatusReceipt:
    receipt_id: str
    receipt_sha256: str
    permit_sha256: str
    launch_receipt_sha256: str
    plan_sha256: str
    project_id: int
    backtest_id: str
    terminal_status: str
    status_poll_count: int
    statistics_requested: bool
    result_log_order_accessed: bool


def _terminal_receipt(
    *, plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
    permit: PreopenQcSubmissionPermit,
    launch: PreopenQcLaunchReceipt, status: str, count: int,
) -> PreopenQcTerminalStatusReceipt:
    record = {
        "permit_sha256": permit.permit_sha256,
        "launch_receipt_sha256": launch.receipt_sha256,
        "plan_sha256": plan.plan_sha256,
        "project_id": launch.project_id,
        "backtest_id": launch.backtest_id,
        "terminal_status": status,
        "status_poll_count": count,
        "statistics_requested": False,
        "result_log_order_accessed": False,
    }
    identity, digest = _identified(
        TERMINAL_SCHEMA, "arv2-preopen-qc-terminal-", record
    )
    return PreopenQcTerminalStatusReceipt(
        receipt_id=identity, receipt_sha256=digest, **record
    )


def _register_terminal_process_return(
    terminal: PreopenQcTerminalStatusReceipt,
) -> PreopenQcTerminalStatusReceipt:
    _process_receipt_authority_register("terminal", terminal)
    return terminal


def _inspect_preopen_qc_terminal_status_impl(
    *, plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
    permit: PreopenQcSubmissionPermit,
    launch: PreopenQcLaunchReceipt, client: FormalQcTransport,
    owner_signature: OwnerSignatureAuthority | None,
    _transport_capability_minter,
) -> PreopenQcTerminalStatusReceipt:
    host_closure = (
        build_physical_preopen_qc_host_closure_binding()
        if type(plan) is PhysicalPreopenQcSubmissionPlan
        else build_preopen_qc_host_closure_binding()
    )
    _require_external_execution_trust_root(
        owner_signature,
        _render_preopen_qc_execution_authority_candidate(plan, host_closure),
    )
    if type(plan) is PhysicalPreopenQcSubmissionPlan:
        verify_physical_preopen_qc_host_closure_live(host_closure)
    else:
        verify_preopen_qc_host_closure_live(host_closure)
    require_preopen_qc_submission_permit(permit, plan)
    _require_launch_receipt(launch, plan, permit)
    capability = _transport_capability_minter(
        transport=client, scope="status",
        binding_record={
            "schema": "arv2-preopen-qc-status-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "launch_receipt_sha256": launch.receipt_sha256,
        }, call_budget={"backtests/list": plan.status_poll_limit},
    )
    for index in range(plan.status_poll_limit):
        try:
            status = formal.parse_statistics_free_backtest_list(
                _preopen_transport_call(
                    host_closure, client, capability, "_request_json", "backtests/list",
                    {"projectId": launch.project_id, "includeStatistics": False},
                ), expected_project_id=launch.project_id,
                expected_backtest_id=launch.backtest_id,
                expected_backtest_name=launch.backtest_name,
            )
        except Exception as exc:
            raise PreopenQcSubmissionLocked(
                "terminal_status", permit.permit_id, type(exc).__name__
            ) from exc
        if status.status in formal.BACKTEST_TERMINAL_STATUSES:
            return _register_terminal_process_return(
                _terminal_receipt(
                    plan=plan,
                    permit=permit,
                    launch=launch,
                    status=status.status,
                    count=index + 1,
                )
            )
        if index + 1 == plan.status_poll_limit:
            raise PreopenQcSubmissionLocked(
                "terminal_status", permit.permit_id, "poll limit exhausted"
            )
        _wait(STATUS_POLL_SECONDS)
    raise AssertionError("unreachable pre-open status loop")


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PreopenQcOutputPackageReceipt:
    receipt_id: str
    receipt_sha256: str
    permit_sha256: str
    launch_receipt_sha256: str
    terminal_receipt_sha256: str
    project_id: int
    compile_id: str
    backtest_id: str
    package_key: str
    package_sha256: str
    package_byte_count: int
    output_manifest_id: str
    output_manifest_sha256: str
    output_manifest_byte_count: int
    output_manifest_key: str
    output_shard_inventory_sha256: str
    universe_terminal_projection_sha256: str
    control_terminal_projection_sha256: str
    q_data_measurement_projection_sha256: str
    terminal_count: int
    accepted_count: int
    refusal_count: int
    object_read_count: int
    outcome_statistics_log_order_accessed: bool
    package_bytes: bytes = dataclasses.field(repr=False)


(
    _process_receipt_authority_register,
    _process_receipt_authority_current,
    _seal_process_receipt_authority_provenance,
) = _make_process_receipt_authority_vault(
    (
        ("launch", PreopenQcLaunchReceipt),
        ("terminal", PreopenQcTerminalStatusReceipt),
        ("output", PreopenQcOutputPackageReceipt),
    )
)


def _require_terminal_receipt(
    terminal: PreopenQcTerminalStatusReceipt,
    plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
    permit: PreopenQcSubmissionPermit, launch: PreopenQcLaunchReceipt,
) -> PreopenQcTerminalStatusReceipt:
    _require_launch_receipt(launch, plan, permit)
    registered = _process_receipt_authority_current("terminal", terminal)
    if (
        type(terminal) is not PreopenQcTerminalStatusReceipt
        or registered is None
        or registered[1] != terminal.receipt_sha256
        or type(terminal.status_poll_count) is not int
        or not 1 <= terminal.status_poll_count <= plan.status_poll_limit
    ):
        raise PreopenQcSubmissionError("terminal status receipt changed")
    expected = _terminal_receipt(
        plan=plan,
        permit=permit,
        launch=launch,
        status=terminal.terminal_status,
        count=terminal.status_poll_count,
    )
    if terminal != expected:
        raise PreopenQcSubmissionError("terminal status receipt changed")
    return terminal


def _object_payload(
    response: object, *, key: str, maximum: int, name: str
) -> bytes:
    if type(response) is not dict or not set(response).issubset(
        {"success", "errors", "messages", "object"}
    ):
        raise PreopenQcSubmissionError(f"{name} Object Store envelope changed")
    item = response.get("object")
    if (
        response.get("success") is not True
        or type(item) is not dict
        or set(item) != {"key", "objectData"}
        or item.get("key") != key
        or type(item.get("objectData")) is not str
    ):
        raise PreopenQcSubmissionError(f"{name} object envelope changed")
    try:
        payload = base64.b64decode(item["objectData"], validate=True)
    except (ValueError, TypeError) as exc:
        raise PreopenQcSubmissionError(f"{name} is not canonical base64") from exc
    if (
        not 0 < len(payload) <= maximum
        or base64.b64encode(payload).decode("ascii") != item["objectData"]
    ):
        raise PreopenQcSubmissionError(f"{name} exceeds its byte bound")
    return payload


def _build_output_package_receipt(
    *, plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
    permit: PreopenQcSubmissionPermit,
    launch: PreopenQcLaunchReceipt, terminal: PreopenQcTerminalStatusReceipt,
    package_bytes: bytes,
) -> PreopenQcOutputPackageReceipt:
    require_preopen_qc_submission_permit(permit, plan)
    _require_terminal_receipt(terminal, plan, permit, launch)
    if terminal.terminal_status != "Completed.":
        raise PreopenQcSubmissionError("completed status receipt is required")
    if type(package_bytes) is not bytes or not 0 < len(package_bytes) <= MAX_PACKAGE_BYTES:
        raise PreopenQcSubmissionError("terminal package exceeds its bound")
    try:
        package = json.loads(package_bytes.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise PreopenQcSubmissionError("terminal package is not JSON") from exc
    expected_fields = {
        "schema", "contract_id", "contract_sha256", "input_manifest",
        "project_source_set_sha256", "output_manifest",
        "output_shard_inventory_sha256",
        "universe_terminal_projection_sha256",
        "control_terminal_projection_sha256",
        "q_data_measurement_projection_sha256", "census",
        "outcome_statistics_log_order_accessed",
    }
    input_manifest = package.get("input_manifest") if type(package) is dict else None
    output = package.get("output_manifest") if type(package) is dict else None
    census = package.get("census") if type(package) is dict else None
    if (
        type(package) is not dict
        or set(package) != expected_fields
        or _canonical(package) != package_bytes
        or package["schema"] != TERMINAL_PACKAGE_SCHEMA
        or package["contract_id"] != CONTRACT_ID
        or package["contract_sha256"] != CONTRACT_SHA256
        or type(input_manifest) is not dict
        or set(input_manifest) != {
            "artifact_id", "content_sha256", "artifact_sha256", "byte_count",
        }
        or input_manifest != {
            "artifact_id": plan.projection.input_manifest_id,
            "content_sha256": plan.input_manifest_sha256,
            "artifact_sha256": plan.input_manifest_sha256,
            "byte_count": plan.projection.input_manifest_byte_count,
        }
        or package["project_source_set_sha256"] != plan.project_source_set_sha256
        or package["outcome_statistics_log_order_accessed"] is not False
        or type(output) is not dict
        or set(output) != {
            "artifact_id", "content_sha256", "artifact_sha256", "byte_count",
            "object_store_key",
        }
        or output["content_sha256"] != output["artifact_sha256"]
        or type(output["byte_count"]) is not int
        or not 0 < output["byte_count"] <= plan.maximum_output_manifest_bytes
        or type(census) is not dict
        or set(census) != {
            "universe_terminal_count", "control_accepted_count",
            "control_refusal_count", "control_terminal_count",
        }
        or any(type(value) is not int or value < 0 for value in census.values())
        or census["universe_terminal_count"] != census["control_terminal_count"]
        or census["control_accepted_count"] + census["control_refusal_count"]
        != census["control_terminal_count"]
    ):
        raise PreopenQcSubmissionError("terminal package binding changed")
    for name in (
        "output_shard_inventory_sha256", "universe_terminal_projection_sha256",
        "control_terminal_projection_sha256",
        "q_data_measurement_projection_sha256",
    ):
        _sha(package[name], name)
    _safe(output["artifact_id"], "output manifest artifact_id")
    _sha(output["content_sha256"], "output manifest sha256")
    _safe(output["object_store_key"], "output manifest key")
    if (
        output["artifact_id"]
        != "arv2-preopen-control-output-" + output["content_sha256"][:24]
        or output["object_store_key"]
        != "arv2/preopen/output/manifests/"
        + output["content_sha256"] + ".json"
    ):
        raise PreopenQcSubmissionError("output manifest identity changed")
    record = {
        "permit_sha256": permit.permit_sha256,
        "launch_receipt_sha256": launch.receipt_sha256,
        "terminal_receipt_sha256": terminal.receipt_sha256,
        "project_id": launch.project_id,
        "compile_id": launch.compile_id,
        "backtest_id": launch.backtest_id,
        "package_key": plan.terminal_package_key,
        "package_sha256": hashlib.sha256(package_bytes).hexdigest(),
        "package_byte_count": len(package_bytes),
        "output_manifest_id": output["artifact_id"],
        "output_manifest_sha256": output["content_sha256"],
        "output_manifest_byte_count": output["byte_count"],
        "output_manifest_key": output["object_store_key"],
        "output_shard_inventory_sha256": package["output_shard_inventory_sha256"],
        "universe_terminal_projection_sha256": package[
            "universe_terminal_projection_sha256"
        ],
        "control_terminal_projection_sha256": package[
            "control_terminal_projection_sha256"
        ],
        "q_data_measurement_projection_sha256": package[
            "q_data_measurement_projection_sha256"
        ],
        "terminal_count": census["control_terminal_count"],
        "accepted_count": census["control_accepted_count"],
        "refusal_count": census["control_refusal_count"],
        "object_read_count": 1,
        "outcome_statistics_log_order_accessed": False,
    }
    identity, digest = _identified(
        OUTPUT_RECEIPT_SCHEMA, "arv2-preopen-qc-output-", record
    )
    return PreopenQcOutputPackageReceipt(
        receipt_id=identity,
        receipt_sha256=digest,
        package_bytes=package_bytes,
        **record,
    )


def _register_output_process_return(
    output: PreopenQcOutputPackageReceipt,
) -> PreopenQcOutputPackageReceipt:
    _process_receipt_authority_register("output", output)
    return output


def require_preopen_qc_output_package_receipt(
    value: PreopenQcOutputPackageReceipt, *,
    plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
    permit: PreopenQcSubmissionPermit, launch: PreopenQcLaunchReceipt,
    terminal: PreopenQcTerminalStatusReceipt,
) -> PreopenQcOutputPackageReceipt:
    registered = _process_receipt_authority_current("output", value)
    if (
        type(value) is not PreopenQcOutputPackageReceipt
        or registered is None
        or registered[1] != value.receipt_sha256
    ):
        raise PreopenQcSubmissionError(
            "terminal package receipt type or process-return authority changed"
        )
    rebuilt = _build_output_package_receipt(
        plan=plan, permit=permit, launch=launch, terminal=terminal,
        package_bytes=value.package_bytes,
    )
    if rebuilt != value:
        raise PreopenQcSubmissionError("terminal package receipt changed")
    return value


def _retrieve_preopen_qc_terminal_package_impl(
    *, plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
    permit: PreopenQcSubmissionPermit,
    launch: PreopenQcLaunchReceipt,
    terminal: PreopenQcTerminalStatusReceipt, client: FormalQcTransport,
    owner_signature: OwnerSignatureAuthority | None,
    _transport_capability_minter,
) -> PreopenQcOutputPackageReceipt:
    host_closure = (
        build_physical_preopen_qc_host_closure_binding()
        if type(plan) is PhysicalPreopenQcSubmissionPlan
        else build_preopen_qc_host_closure_binding()
    )
    _require_external_execution_trust_root(
        owner_signature,
        _render_preopen_qc_execution_authority_candidate(plan, host_closure),
    )
    if type(plan) is PhysicalPreopenQcSubmissionPlan:
        verify_physical_preopen_qc_host_closure_live(host_closure)
    else:
        verify_preopen_qc_host_closure_live(host_closure)
    require_preopen_qc_submission_permit(permit, plan)
    _require_terminal_receipt(terminal, plan, permit, launch)
    if (
        terminal.terminal_status != "Completed."
    ):
        raise PreopenQcSubmissionError("completed status receipt is required")
    capability = _transport_capability_minter(
        transport=client, scope="preopen_output_read",
        binding_record={
            "schema": "arv2-preopen-qc-output-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "launch_receipt_sha256": launch.receipt_sha256,
            "terminal_receipt_sha256": terminal.receipt_sha256,
            "package_key": plan.terminal_package_key,
        }, call_budget={"object/read": 1},
    )
    try:
        response = _preopen_transport_call(
            host_closure, client, capability, "_read_object_bounded",
            plan.organization_id, plan.terminal_package_key,
        )
    except Exception as exc:
        raise PreopenQcSubmissionLocked(
            "terminal_package", permit.permit_id, type(exc).__name__
        ) from exc
    package_bytes = _object_payload(
        response,
        key=plan.terminal_package_key,
        maximum=MAX_PACKAGE_BYTES,
        name="terminal package",
    )
    try:
        package = json.loads(package_bytes.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise PreopenQcSubmissionError("terminal package is not JSON") from exc
    expected_fields = {
        "schema", "contract_id", "contract_sha256", "input_manifest",
        "project_source_set_sha256", "output_manifest",
        "output_shard_inventory_sha256",
        "universe_terminal_projection_sha256",
        "control_terminal_projection_sha256",
        "q_data_measurement_projection_sha256", "census",
        "outcome_statistics_log_order_accessed",
    }
    input_manifest = package.get("input_manifest") if type(package) is dict else None
    output = package.get("output_manifest") if type(package) is dict else None
    census = package.get("census") if type(package) is dict else None
    if (
        type(package) is not dict or set(package) != expected_fields
        or _canonical(package) != package_bytes
        or package["schema"] != TERMINAL_PACKAGE_SCHEMA
        or package["contract_id"] != CONTRACT_ID
        or package["contract_sha256"] != CONTRACT_SHA256
        or type(input_manifest) is not dict
        or set(input_manifest) != {
            "artifact_id", "content_sha256", "artifact_sha256", "byte_count",
        }
        or input_manifest != {
            "artifact_id": plan.projection.input_manifest_id,
            "content_sha256": plan.input_manifest_sha256,
            "artifact_sha256": plan.input_manifest_sha256,
            "byte_count": plan.projection.input_manifest_byte_count,
        }
        or package["project_source_set_sha256"]
        != plan.project_source_set_sha256
        or package["outcome_statistics_log_order_accessed"] is not False
        or type(output) is not dict
        or set(output) != {
            "artifact_id", "content_sha256", "artifact_sha256", "byte_count",
            "object_store_key",
        }
        or output["content_sha256"] != output["artifact_sha256"]
        or type(output["byte_count"]) is not int or output["byte_count"] < 1
        or type(census) is not dict
        or set(census) != {
            "universe_terminal_count", "control_accepted_count",
            "control_refusal_count", "control_terminal_count",
        }
        or any(type(value) is not int or value < 0 for value in census.values())
        or census["universe_terminal_count"] != census["control_terminal_count"]
        or census["control_accepted_count"] + census["control_refusal_count"]
        != census["control_terminal_count"]
    ):
        raise PreopenQcSubmissionError("terminal package binding changed")
    for name in (
        "output_shard_inventory_sha256", "universe_terminal_projection_sha256",
        "control_terminal_projection_sha256",
        "q_data_measurement_projection_sha256",
    ):
        _sha(package[name], name)
    _safe(output["artifact_id"], "output manifest artifact_id")
    _sha(output["content_sha256"], "output manifest sha256")
    _safe(output["object_store_key"], "output manifest key")
    if (
        output["artifact_id"]
        != "arv2-preopen-control-output-" + output["content_sha256"][:24]
        or output["object_store_key"]
        != "arv2/preopen/output/manifests/"
        + output["content_sha256"] + ".json"
    ):
        raise PreopenQcSubmissionError("output manifest identity changed")
    record = {
        "permit_sha256": permit.permit_sha256,
        "launch_receipt_sha256": launch.receipt_sha256,
        "terminal_receipt_sha256": terminal.receipt_sha256,
        "project_id": launch.project_id, "compile_id": launch.compile_id,
        "backtest_id": launch.backtest_id,
        "package_key": plan.terminal_package_key,
        "package_sha256": hashlib.sha256(package_bytes).hexdigest(),
        "package_byte_count": len(package_bytes),
        "output_manifest_id": output["artifact_id"],
        "output_manifest_sha256": output["content_sha256"],
        "output_manifest_byte_count": output["byte_count"],
        "output_manifest_key": output["object_store_key"],
        "output_shard_inventory_sha256": package["output_shard_inventory_sha256"],
        "universe_terminal_projection_sha256": package[
            "universe_terminal_projection_sha256"
        ],
        "control_terminal_projection_sha256": package[
            "control_terminal_projection_sha256"
        ],
        "q_data_measurement_projection_sha256": package[
            "q_data_measurement_projection_sha256"
        ],
        "terminal_count": census["control_terminal_count"],
        "accepted_count": census["control_accepted_count"],
        "refusal_count": census["control_refusal_count"],
        "object_read_count": 1,
        "outcome_statistics_log_order_accessed": False,
    }
    identity, digest = _identified(
        OUTPUT_RECEIPT_SCHEMA, "arv2-preopen-qc-output-", record
    )
    value = _register_output_process_return(
        PreopenQcOutputPackageReceipt(
            receipt_id=identity,
            receipt_sha256=digest,
            package_bytes=package_bytes,
            **record,
        )
    )
    return require_preopen_qc_output_package_receipt(
        value, plan=plan, permit=permit, launch=launch, terminal=terminal
    )


def _fsync_private_directory(path: Path, name: str) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            observed = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(observed.st_mode)
                or stat.S_IMODE(observed.st_mode) != 0o700
                or (hasattr(os, "getuid") and observed.st_uid != os.getuid())
            ):
                raise PreopenQcSubmissionError(f"{name} is not owner-only")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise PreopenQcSubmissionError(f"{name} could not be authenticated") from exc


def _write_private_archive_file(path: Path, payload: bytes, name: str) -> None:
    if type(payload) is not bytes or not payload:
        raise PreopenQcSubmissionError(f"{name} is empty")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            view = memoryview(payload)
            while view:
                count = os.write(descriptor, view)
                if count <= 0:
                    raise OSError("short private archive write")
                view = view[count:]
            os.fsync(descriptor)
            observed = os.fstat(descriptor)
            if (
                not stat.S_ISREG(observed.st_mode)
                or observed.st_nlink != 1
                or observed.st_size != len(payload)
                or stat.S_IMODE(observed.st_mode) != 0o600
                or (hasattr(os, "getuid") and observed.st_uid != os.getuid())
            ):
                raise PreopenQcSubmissionError(f"{name} is not owner-only and exact")
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise PreopenQcSubmissionError(f"{name} could not be created exactly once") from exc


def _read_private_archive_file(
    path: Path, *, expected_sha256: str, expected_byte_count: int, maximum: int,
    name: str,
) -> bytes:
    if (
        type(path) is not type(Path())
        or not path.is_absolute()
        or path.is_symlink()
        or type(expected_byte_count) is not int
        or not 0 < expected_byte_count <= maximum
    ):
        raise PreopenQcSubmissionError(f"{name} path or byte bound changed")
    _sha(expected_sha256, name + " SHA-256")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_size != expected_byte_count
                or stat.S_IMODE(before.st_mode) != 0o600
                or (hasattr(os, "getuid") and before.st_uid != os.getuid())
            ):
                raise PreopenQcSubmissionError(f"{name} is not an exact private file")
            chunks = []
            remaining = expected_byte_count + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise PreopenQcSubmissionError(f"{name} could not be read") from exc
    identity_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if (
        len(payload) != expected_byte_count
        or hashlib.sha256(payload).hexdigest() != expected_sha256
        or tuple(getattr(before, field) for field in identity_fields)
        != tuple(getattr(after, field) for field in identity_fields)
    ):
        raise PreopenQcSubmissionError(f"{name} changed while read")
    return payload


def _prepare_output_archive(
    plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
    *, permit_id: str,
) -> tuple[Path, Path]:
    root = plan.output_archive_root
    if root is None:
        raise PreopenQcSubmissionError(
            "owner-signed output archive root is required before output reads"
        )
    try:
        parent = root.parent.resolve(strict=True)
        parent_stat = parent.stat(follow_symlinks=False)
    except OSError as exc:
        raise PreopenQcSubmissionError("output archive parent is unavailable") from exc
    if (
        root.name != OUTPUT_ARCHIVE_DIRECTORY_NAME
        or not stat.S_ISDIR(parent_stat.st_mode)
        or stat.S_IMODE(parent_stat.st_mode) != 0o700
        or (hasattr(os, "getuid") and parent_stat.st_uid != os.getuid())
    ):
        raise PreopenQcSubmissionError("output archive parent changed")
    try:
        os.mkdir(root, 0o700)
        shard_directory = root / OUTPUT_ARCHIVE_SHARD_DIRECTORY
        os.mkdir(shard_directory, 0o700)
        _fsync_private_directory(
            shard_directory, "output archive shard directory"
        )
        _fsync_private_directory(root, "output archive root")
        _fsync_private_directory(parent, "output archive parent")
    except Exception as exc:
        raise PreopenQcSubmissionLocked(
            "output_archive", permit_id, "archive already exists or is unavailable"
        ) from exc
    return root, shard_directory


def _require_output_archive_lineage(
    *, plan: PreopenQcSubmissionPlan, package: PreopenQcOutputPackageReceipt,
    preopen: PreopenControlAcquisitionReceipt,
    capacity: FormalStreamingCapacityBinding,
) -> tuple[PreopenControlAcquisitionReceipt, FormalStreamingCapacityBinding,
           tuple[dict[str, object], ...]]:
    preopen = require_reviewed_preopen_control_acquisition_receipt(preopen)
    capacity = require_formal_streaming_capacity_binding(capacity)
    if capacity.preopen_acquisition_receipt is not preopen:
        raise PreopenQcSubmissionError(
            "physical archive capacity and pre-open acquisition parents differ"
        )
    descriptors = acquisition_output_shard_descriptor_records(preopen)
    if (
        preopen.artifact_id != package.output_manifest_id
        or preopen.artifact_sha256 != package.output_manifest_sha256
        or preopen.content_sha256 != package.output_manifest_sha256
        or preopen.byte_count != package.output_manifest_byte_count
        or preopen.input_manifest_sha256 != plan.input_manifest_sha256
        or preopen.project_source_set_sha256 != plan.project_source_set_sha256
        or preopen.output_shard_inventory_sha256
        != package.output_shard_inventory_sha256
        or preopen.universe_terminal_projection_sha256
        != package.universe_terminal_projection_sha256
        or preopen.control_terminal_projection_sha256
        != package.control_terminal_projection_sha256
        or preopen.q_data_measurement_projection_sha256
        != package.q_data_measurement_projection_sha256
        or preopen.control_terminal_count != package.terminal_count
        or preopen.control_accepted_count != package.accepted_count
        or preopen.control_refusal_count != package.refusal_count
        or not 1 <= len(descriptors) <= plan.maximum_output_shard_reads
    ):
        raise PreopenQcSubmissionError(
            "terminal package, reviewed acquisition, and signed output bounds differ"
        )
    return preopen, capacity, descriptors


def _download_and_load_preopen_qc_terminal_archive_impl(
    *, plan: PreopenQcSubmissionPlan, permit: PreopenQcSubmissionPermit,
    launch: PreopenQcLaunchReceipt, terminal: PreopenQcTerminalStatusReceipt,
    package: PreopenQcOutputPackageReceipt,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    capacity: FormalStreamingCapacityBinding, client: FormalQcTransport,
    owner_signature: OwnerSignatureAuthority | None,
    _transport_capability_minter,
) -> PhysicalPreopenTerminalArchive:
    """Persist exact QC outputs once, manifest last, then mint the disk archive."""

    host_closure = build_preopen_qc_host_closure_binding()
    _require_external_execution_trust_root(
        owner_signature,
        _render_preopen_qc_execution_authority_candidate(plan, host_closure),
    )
    verify_preopen_qc_host_closure_live(host_closure)
    require_preopen_qc_submission_plan(plan)
    require_preopen_qc_submission_permit(permit, plan)
    _require_terminal_receipt(terminal, plan, permit, launch)
    package = require_preopen_qc_output_package_receipt(
        package, plan=plan, permit=permit, launch=launch, terminal=terminal
    )
    preopen, capacity, descriptors = _require_output_archive_lineage(
        plan=plan, package=package, preopen=preopen_acquisition_receipt,
        capacity=capacity,
    )
    if plan.output_archive_root is None:
        raise PreopenQcSubmissionError("signed output archive root is absent")
    formal._require_concrete_transport(client)
    root, shard_directory = _prepare_output_archive(
        plan, permit_id=permit.permit_id
    )
    capability = _transport_capability_minter(
        transport=client,
        scope="preopen_output_read",
        binding_record={
            "schema": "arv2-preopen-qc-physical-output-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "launch_receipt_sha256": launch.receipt_sha256,
            "terminal_receipt_sha256": terminal.receipt_sha256,
            "package_receipt_sha256": package.receipt_sha256,
            "output_manifest_sha256": package.output_manifest_sha256,
            "output_shard_inventory_sha256": package.output_shard_inventory_sha256,
            "output_archive_root": str(root),
            "manifest_persisted_last": True,
        },
        call_budget={"object/read": 1 + plan.maximum_output_shard_reads},
    )
    shard_paths: list[Path] = []
    try:
        manifest_response = _preopen_transport_call(
            host_closure, client, capability, "_read_object_bounded",
            plan.organization_id, package.output_manifest_key,
        )
        manifest_payload = _object_payload(
            manifest_response,
            key=package.output_manifest_key,
            maximum=plan.maximum_output_manifest_bytes,
            name="pre-open output manifest",
        )
        if (
            len(manifest_payload) != package.output_manifest_byte_count
            or hashlib.sha256(manifest_payload).hexdigest()
            != package.output_manifest_sha256
            or manifest_payload != preopen.output_manifest_bytes
        ):
            raise PreopenQcSubmissionError("output manifest bytes changed")
        manifest, _, _ = preopen_core._validate_manifest(manifest_payload)
        if (
            tuple(manifest["output_shards"]) != descriptors
            or hashlib.sha256(_canonical(list(descriptors))).hexdigest()
            != package.output_shard_inventory_sha256
        ):
            raise PreopenQcSubmissionError("output shard inventory changed")
        for ordinal, descriptor in enumerate(descriptors):
            expected_size = descriptor["compressed_byte_count"]
            if (
                type(expected_size) is not int
                or not 0 < expected_size <= plan.maximum_output_shard_read_bytes
            ):
                raise PreopenQcSubmissionError(
                    "output shard exceeds the signed transport-safe read bound"
                )
            response = _preopen_transport_call(
                host_closure, client, capability, "_read_object_bounded",
                plan.organization_id, descriptor["object_store_key"],
            )
            payload = _object_payload(
                response,
                key=descriptor["object_store_key"],
                maximum=plan.maximum_output_shard_read_bytes,
                name=f"pre-open terminal shard {ordinal}",
            )
            if (
                len(payload) != expected_size
                or hashlib.sha256(payload).hexdigest()
                != descriptor["compressed_sha256"]
            ):
                raise PreopenQcSubmissionError(
                    "pre-open terminal shard content changed"
                )
            path = shard_directory / (
                f'{ordinal:04d}-{descriptor["compressed_sha256"]}.jsonl.gz'
            )
            _write_private_archive_file(
                path, payload, f"pre-open terminal shard {ordinal}"
            )
            shard_paths.append(path)
            del payload

        def iter_local_payloads():
            for ordinal, (path, descriptor) in enumerate(
                zip(shard_paths, descriptors, strict=True)
            ):
                yield _read_private_archive_file(
                    path,
                    expected_sha256=descriptor["compressed_sha256"],
                    expected_byte_count=descriptor["compressed_byte_count"],
                    maximum=plan.maximum_output_shard_read_bytes,
                    name=f"archived pre-open terminal shard {ordinal}",
                )

        projection, totals = preopen_io._validated_batch_major_output_payloads(
            manifest, iter_local_payloads()
        )
        if (
            projection != preopen.output_shard_payload_projection_sha256
            or totals != {
                "terminal_count": package.terminal_count,
                "accepted_count": package.accepted_count,
                "refusal_count": package.refusal_count,
            }
        ):
            raise PreopenQcSubmissionError(
                "complete logical batch-major output projection changed"
            )
        _write_private_archive_file(
            root / OUTPUT_ARCHIVE_MANIFEST_NAME,
            manifest_payload,
            "pre-open output manifest",
        )
        _fsync_private_directory(shard_directory, "output archive shard directory")
        _fsync_private_directory(root, "output archive root")
        expected_shards = {path.name for path in shard_paths}
        if (
            {path.name for path in root.iterdir()}
            != {OUTPUT_ARCHIVE_MANIFEST_NAME, OUTPUT_ARCHIVE_SHARD_DIRECTORY}
            or {path.name for path in shard_directory.iterdir()} != expected_shards
        ):
            raise PreopenQcSubmissionError("output archive inventory changed")
        return load_physical_preopen_terminal_archive(
            preopen_acquisition_receipt=preopen,
            capacity=capacity,
            shard_paths=tuple(shard_paths),
        )
    except PreopenQcSubmissionLocked:
        raise
    except Exception as exc:
        raise PreopenQcSubmissionLocked(
            "output_archive", permit.permit_id, type(exc).__name__
        ) from exc


def _bind_transport_capability_consumers(
    minter, execute_impl, execute_preuploaded_impl, inspect_impl,
    retrieve_impl, download_impl, binding_guard,
):
    """Keep the restricted production minter lexical to reviewed actions."""

    execute_preuploaded_code = execute_preuploaded_impl.__code__
    execute_preuploaded_globals = execute_preuploaded_impl.__globals__
    execute_preuploaded_defaults = execute_preuploaded_impl.__defaults__
    execute_preuploaded_kwdefaults = execute_preuploaded_impl.__kwdefaults__

    def execute_preopen_qc_submission_once(
        *, plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
        client: FormalQcTransport,
        ledger_directory: Path, started_at_utc: str,
        owner_signature: OwnerSignatureAuthority | None,
    ) -> tuple[PreopenQcSubmissionPermit, PreopenQcLaunchReceipt]:
        if type(plan) is PhysicalPreopenQcSubmissionPlan and (
            type(execute_preuploaded_impl) is not type(lambda: None)
            or execute_preuploaded_impl.__code__ is not execute_preuploaded_code
            or execute_preuploaded_impl.__globals__ is not execute_preuploaded_globals
            or execute_preuploaded_impl.__defaults__ is not execute_preuploaded_defaults
            or execute_preuploaded_impl.__kwdefaults__
            is not execute_preuploaded_kwdefaults
            or execute_preuploaded_impl.__closure__ is not None
        ):
            raise PreopenQcSubmissionError(
                "physical pre-open execution dependency changed"
            )
        binding_guard("submission")
        return execute_impl(
            plan=plan,
            client=client,
            ledger_directory=ledger_directory,
            started_at_utc=started_at_utc,
            owner_signature=owner_signature,
            _transport_capability_minter=minter,
            _execute_preuploaded_impl=execute_preuploaded_impl,
        )

    def inspect_preopen_qc_terminal_status(
        *, plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
        permit: PreopenQcSubmissionPermit,
        launch: PreopenQcLaunchReceipt, client: FormalQcTransport,
        owner_signature: OwnerSignatureAuthority | None,
    ) -> PreopenQcTerminalStatusReceipt:
        binding_guard("terminal status")
        return inspect_impl(
            plan=plan,
            permit=permit,
            launch=launch,
            client=client,
            owner_signature=owner_signature,
            _transport_capability_minter=minter,
        )

    def retrieve_preopen_qc_terminal_package(
        *, plan: PreopenQcSubmissionPlan | PhysicalPreopenQcSubmissionPlan,
        permit: PreopenQcSubmissionPermit,
        launch: PreopenQcLaunchReceipt,
        terminal: PreopenQcTerminalStatusReceipt, client: FormalQcTransport,
        owner_signature: OwnerSignatureAuthority | None,
    ) -> PreopenQcOutputPackageReceipt:
        binding_guard("output package")
        return retrieve_impl(
            plan=plan,
            permit=permit,
            launch=launch,
            terminal=terminal,
            client=client,
            owner_signature=owner_signature,
            _transport_capability_minter=minter,
        )

    def download_and_load_preopen_qc_terminal_archive(
        *, plan: PreopenQcSubmissionPlan, permit: PreopenQcSubmissionPermit,
        launch: PreopenQcLaunchReceipt,
        terminal: PreopenQcTerminalStatusReceipt,
        package: PreopenQcOutputPackageReceipt,
        preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
        capacity: FormalStreamingCapacityBinding, client: FormalQcTransport,
        owner_signature: OwnerSignatureAuthority | None,
    ) -> PhysicalPreopenTerminalArchive:
        binding_guard("output archive")
        return download_impl(
            plan=plan,
            permit=permit,
            launch=launch,
            terminal=terminal,
            package=package,
            preopen_acquisition_receipt=preopen_acquisition_receipt,
            capacity=capacity,
            client=client,
            owner_signature=owner_signature,
            _transport_capability_minter=minter,
        )

    return (
        execute_preopen_qc_submission_once,
        inspect_preopen_qc_terminal_status,
        retrieve_preopen_qc_terminal_package,
        download_and_load_preopen_qc_terminal_archive,
    )


(
    _transport_capability_minter,
    _seal_transport_capability_callers,
) = (
    formal._claim_preopen_transport_capability_minter()
)


(
    execute_preopen_qc_submission_once,
    inspect_preopen_qc_terminal_status,
    retrieve_preopen_qc_terminal_package,
    download_and_load_preopen_qc_terminal_archive,
) = _bind_transport_capability_consumers(
    _transport_capability_minter,
    _execute_preopen_qc_submission_once_impl,
    _execute_preuploaded_preopen_qc_submission_once_impl,
    _inspect_preopen_qc_terminal_status_impl,
    _retrieve_preopen_qc_terminal_package_impl,
    _download_and_load_preopen_qc_terminal_archive_impl,
    _require_preopen_action_global_bindings,
)


def _process_receipt_frame_provenance(function: object) -> tuple[object, ...]:
    """Capture code plus the exact lexical dependencies used by one frame."""

    if type(function) is not type(lambda: None):
        raise PreopenQcSubmissionError(
            "pre-open process receipt producer type changed"
        )
    closure = function.__closure__ or ()
    if len(closure) != len(function.__code__.co_freevars):
        raise PreopenQcSubmissionError(
            "pre-open process receipt producer closure changed"
        )
    return (
        function.__code__,
        function.__code__.co_name,
        function.__code__.co_filename,
        function.__globals__,
        tuple(
            (name, cell.cell_contents)
            for name, cell in zip(
                function.__code__.co_freevars,
                closure,
                strict=True,
            )
        ),
    )


_seal_process_receipt_authority_provenance(
    (
        (
            "launch",
            (
                _process_receipt_frame_provenance(
                    _register_launch_process_return
                ),
                _process_receipt_frame_provenance(
                    _execute_preopen_qc_submission_once_impl
                ),
                _process_receipt_frame_provenance(
                    execute_preopen_qc_submission_once
                ),
            ),
        ),
        (
            "terminal",
            (
                _process_receipt_frame_provenance(
                    _register_terminal_process_return
                ),
                _process_receipt_frame_provenance(
                    _inspect_preopen_qc_terminal_status_impl
                ),
                _process_receipt_frame_provenance(
                    inspect_preopen_qc_terminal_status
                ),
            ),
        ),
        (
            "output",
            (
                _process_receipt_frame_provenance(
                    _register_output_process_return
                ),
                _process_receipt_frame_provenance(
                    _retrieve_preopen_qc_terminal_package_impl
                ),
                _process_receipt_frame_provenance(
                    retrieve_preopen_qc_terminal_package
                ),
            ),
        ),
    )
)

_seal_transport_capability_callers(
    (
        (
            "submission",
            ((
                _execute_preopen_qc_submission_once_impl,
                execute_preopen_qc_submission_once,
            ),),
        ),
        (
            "status",
            ((
                _inspect_preopen_qc_terminal_status_impl,
                inspect_preopen_qc_terminal_status,
            ),),
        ),
        (
            "preopen_output_read",
            (
                (
                    _retrieve_preopen_qc_terminal_package_impl,
                    retrieve_preopen_qc_terminal_package,
                ),
                (
                    _download_and_load_preopen_qc_terminal_archive_impl,
                    download_and_load_preopen_qc_terminal_archive,
                ),
            ),
        ),
    )
)

del _process_receipt_frame_provenance

del _transport_capability_minter
del _seal_transport_capability_callers
del _execute_preopen_qc_submission_once_impl
del _execute_preuploaded_preopen_qc_submission_once_impl
del _inspect_preopen_qc_terminal_status_impl
del _retrieve_preopen_qc_terminal_package_impl
del _download_and_load_preopen_qc_terminal_archive_impl
del _bind_transport_capability_consumers

_seal_preopen_action_global_bindings()
del _make_preopen_action_global_binding_guard
del _seal_preopen_action_global_bindings
del _require_preopen_action_global_bindings


__all__ = (
    "EXECUTION_AUTHORITY_SCHEMA", "PHYSICAL_EXECUTION_AUTHORITY_SCHEMA",
    "PREOPEN_EXECUTION_ACTIONS", "PHYSICAL_PREOPEN_EXECUTION_ACTIONS",
    "OWNER_REVIEW_WAIVER_ID", "OWNER_REVIEW_WAIVER_SCOPE",
    "OWNER_REVIEW_WAIVER_BASIS", "OWNER_REVIEW_WAIVER_DISPOSITION",
    "PHYSICAL_INPUT_UPLOAD_DISPOSITION", "PHYSICAL_PLAN_SCHEMA",
    "QC_DEFAULT_RESEARCH_NOTEBOOK_PATH",
    "MAX_OUTPUT_MANIFEST_BYTES", "MAX_OUTPUT_SHARD_READ_BYTES",
    "MAX_OUTPUT_SHARD_READS", "OUTPUT_ARCHIVE_DIRECTORY_NAME",
    "OUTPUT_ARCHIVE_MANIFEST_NAME", "OUTPUT_ARCHIVE_SHARD_DIRECTORY",
    "PREOPEN_REQUIRED_HOST_CODE_PATHS",
    "PHYSICAL_PREOPEN_REQUIRED_HOST_CODE_PATHS",
    "PreopenQcHostClosureBinding",
    "PreopenQcHostSourceBinding",
    "PhysicalPreopenQcSubmissionPlan", "PreopenQcLaunchReceipt",
    "PreopenQcOutputPackageReceipt",
    "PreopenQcSubmissionError", "PreopenQcSubmissionLocked",
    "PreopenQcSubmissionPermit", "PreopenQcSubmissionPlan",
    "PreopenQcTerminalStatusReceipt",
    "build_physical_preopen_qc_host_closure_binding",
    "build_preopen_qc_host_closure_binding",
    "build_preopen_qc_submission_plan",
    "build_preopen_qc_submission_plan_from_physical_upload",
    "download_and_load_preopen_qc_terminal_archive",
    "execute_preopen_qc_submission_once",
    "inspect_preopen_qc_terminal_status",
    "require_preopen_qc_output_package_receipt",
    "require_preopen_qc_physical_submission_plan",
    "require_preopen_qc_submission_permit", "require_preopen_qc_submission_plan",
    "render_preopen_qc_execution_authority_candidate",
    "retrieve_preopen_qc_terminal_package",
    "verify_physical_preopen_qc_host_closure_live",
    "verify_preopen_qc_host_closure_live",
)
