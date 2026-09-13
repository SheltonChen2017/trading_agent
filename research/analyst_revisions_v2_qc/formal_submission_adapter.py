"""One-use ARV2 formal QC submission, status, and separate result-read gates.

The adapter is intentionally narrow.  It accepts the reviewed concrete
``FormalQcTransport`` only, authenticates the full live host/source closure,
creates the durable one-use permit immediately before authentication, uploads
exact compact input objects with multipart + metadata verification, uploads
the exact projected source set, compiles, and launches at most one backtest.

Status polling never enters a result/statistics payload.  A completed status
only creates a disabled result-gate candidate.  A distinct owner-pinned result
authority is required before one logical result transaction may read the
allowlisted ARV2 summary root and its exact root-authenticated 26-object report
family inventory.  No standard statistic, chart, log, order, trade, or raw
security-event/market row is selected, retained, returned, or logged.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import re
import stat
import sys
import threading
import time
import weakref
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Mapping

from .owner_signature_authority import (
    OwnerSignatureAuthority,
    OwnerSignatureAuthorityError,
    reviewed_owner_signature_registry_status,
    require_formal_execution_owner_signature,
    require_formal_result_read_owner_signature,
)
from .formal_qc_transport import (
    FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT,
    MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES,
    MAX_FORMAL_RESULT_FAMILY_TOTAL_BYTES,
    REQUEST_METHOD_NAMES,
    RESULT_FAMILY_READ_CAPABILITY_SCHEMA,
    TRANSPORT_SCHEMA,
    FormalQcTransport,
    FormalQcTransportError,
    _claim_adapter_capability_minter,
)
from .formal_run_protocol import (
    FormalLookClaim,
    FormalRunCandidate,
    FormalSubmissionPermit,
    ReviewedFormalRunAuthority,
    begin_formal_submission_once,
    require_formal_look_claim,
    require_formal_run_candidate,
    require_formal_submission_permit,
    require_reviewed_formal_run_authority,
)
from .formal_runtime_projection import (
    ABSOLUTE_MAX_SUMMARY_CHUNKS,
    AGGREGATE_RESULT_SCHEMA,
    EVALUATION_ID,
    FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA,
    FORMAL_INPUT_PREFIX,
    FORMAL_RESULT_FAMILY_OBJECT_COUNT,
    INPUT_MANIFEST_SCHEMA,
    MAX_FORMAL_RESULT_FAMILY_OBJECT_COMPRESSED_BYTES,
    MAX_FORMAL_RESULT_FAMILY_OBJECT_UNCOMPRESSED_BYTES,
    MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES,
    MAX_FORMAL_RESULT_TOTAL_UNCOMPRESSED_BYTES,
    REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX,
    REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA,
    SUMMARY_CHUNK_PREFIX,
    SUMMARY_CHUNK_NAME_WIDTH,
    SUMMARY_META_NAME,
    SUMMARY_RECEIPT_SCHEMA,
    UPSTREAM_MATERIALIZATION_CAPACITY_SCHEMA,
    FormalQcCompressedShard,
    FormalQcRuntimeProjection,
    QcObjectPayloadBinding,
    canonical_json_bytes,
    require_formal_qc_compressed_shard,
    require_formal_qc_runtime_projection,
    validate_formal_qc_runtime_resource_candidate,
    require_projection_bound_to_candidate,
    require_qc_object_payload_binding,
)
from .formal_economic_execution_definition import (
    FormalEconomicExecutionBinding,
    FormalEconomicExecutionDefinitionError,
    require_formal_economic_execution_binding,
)
from .formal_report_contract import (
    FormalReportContract,
    FormalReportContractError,
    require_formal_report_contract,
)
from .formal_runtime_projection import (
    ABSOLUTE_MAX_SUMMARY_CHUNK_CHARACTERS,
    ABSOLUTE_MAX_SUMMARY_PAYLOAD_BYTES,
)
from .runtime_shard_projection import (
    SyntheticQcRuntimeShardProjection,
    require_synthetic_qc_runtime_shard_projection,
)

if TYPE_CHECKING:
    from .formal_streaming_bridge import (
        StreamedFormalRuntimeBridge,
        StreamedFormalUploadEntry,
    )
    from .power_calibration_bridge import AuthenticatedPowerFloorBinding


class FormalQcSubmissionError(ValueError):
    """A local binding, response envelope, or result receipt is invalid."""


class FormalQcSubmissionLocked(RuntimeError):
    """The formal look is spent and an external action became ambiguous."""

    def __init__(
        self,
        phase: str,
        permit_id: str,
        message: str,
        *,
        outcome_class: str = "refused",
    ) -> None:
        if outcome_class not in {
            "refused", "envelope", "network_ambiguous"
        }:
            raise ValueError("formal submission lock outcome class is invalid")
        super().__init__(f"{phase}: {message}; formal look remains consumed")
        self.phase = phase
        self.permit_id = permit_id
        self.outcome_class = outcome_class


def _failure_outcome_class(exc: BaseException) -> str:
    """Classify a spent action without retaining exception or response values."""

    if type(exc) is FormalQcTransportError:
        message = str(exc)
        if message == "QuantConnect network request failed":
            return "network_ambiguous"
        if message.startswith("QuantConnect ") and message.endswith(
            " request was refused"
        ):
            return "refused"
        return "envelope"
    if type(exc) is FormalQcSubmissionError:
        return "envelope"
    return "network_ambiguous"


def _make_formal_action_global_binding_guard():
    """Pin the complete action namespace before any one-use state is spent."""

    expected_names: tuple[str, ...] = ()
    expected_globals: tuple[tuple[str, object], ...] = ()
    expected_external: tuple[tuple[object, str, object], ...] = ()
    expected_class_namespaces: tuple[
        tuple[object, tuple[str, ...], tuple[tuple[str, object], ...]], ...
    ] = ()
    get_module_globals = globals
    get_pid = os.getpid
    get_attribute = getattr
    module_vars = vars
    exact_tuple = tuple
    any_true = any
    sort_values = sorted
    error_type = FormalQcSubmissionError
    authority_pid = get_pid()
    module_name = __name__
    module_registry = sys.modules
    authority_module = module_registry.get(module_name)
    missing = object()
    excluded = (
        "_make_formal_action_global_binding_guard",
        "_seal_formal_action_global_bindings",
        "_require_formal_action_global_bindings",
        "_claim_fundamental_discovery_transport_capability_minter",
        "_claim_preopen_transport_capability_minter",
        "_claim_power_calibration_transport_capability_minter",
    )
    os_external_names = (
        "close", "fstat", "fsync", "getpid", "open", "read",
        "register_at_fork", "stat", "write", "O_CREAT", "O_EXCL",
        "O_RDONLY", "O_WRONLY",
    ) + (("O_NOFOLLOW",) if hasattr(os, "O_NOFOLLOW") else ())
    concrete_path_type = type(Path())
    path_method_names = (
        "__fspath__", "__init__", "__new__", "__str__", "__truediv__",
        "is_absolute", "is_symlink", "name", "parent", "read_bytes",
        "relative_to", "resolve", "stat",
    )
    external_specs = (
        (base64, ("b64decode", "b64encode", "urlsafe_b64encode")),
        (dataclasses, ("asdict", "dataclass", "field", "fields")),
        (hashlib, ("md5", "sha256")),
        (
            json,
            (
                "dumps", "loads", "JSONDecoder", "JSONEncoder",
                "_default_decoder", "_default_encoder",
            ),
        ),
        (
            json.loads,
            (
                "__code__", "__globals__", "__defaults__",
                "__kwdefaults__", "__closure__",
            ),
        ),
        (
            json.dumps,
            (
                "__code__", "__globals__", "__defaults__",
                "__kwdefaults__", "__closure__",
            ),
        ),
        (os, os_external_names),
        (os.path, ("dirname", "join", "realpath")),
        (Path, path_method_names),
        (concrete_path_type, path_method_names),
        (re, ("compile", "fullmatch")),
        (stat, ("S_ISDIR", "S_ISLNK", "S_ISREG", "S_IMODE")),
        (sys, ("_getframe", "modules")),
        (threading, ("RLock",)),
        (time, ("sleep",)),
        (timezone, ("utc",)),
        (weakref, ("ref",)),
        (zlib, ("MAX_WBITS", "decompress", "decompressobj", "error")),
    )
    class_namespaces = (
        datetime,
        json.JSONDecoder,
        json.JSONEncoder,
    )

    def seal() -> None:
        nonlocal expected_names, expected_globals, expected_external
        nonlocal expected_class_namespaces

        if (
            expected_names
            or expected_globals
            or expected_external
            or expected_class_namespaces
            or authority_module is None
            or module_registry.get(module_name) is not authority_module
            or module_vars(authority_module) is not get_module_globals()
        ):
            raise error_type("formal action globals were already sealed")
        current = get_module_globals()
        expected_names = exact_tuple(sort_values(
            name for name in current
            if not name.startswith("__") and name not in excluded
        ))
        expected_globals = exact_tuple(
            (name, current[name]) for name in expected_names
        )
        expected_external = exact_tuple(
            (namespace, name, get_attribute(namespace, name))
            for namespace, names in external_specs
            for name in names
        )
        expected_class_namespaces = exact_tuple(
            (
                class_type,
                exact_tuple(sort_values(module_vars(class_type))),
                exact_tuple(module_vars(class_type).items()),
            )
            for class_type in class_namespaces
        )

    def require(kind: str) -> None:
        if (
            get_pid() != authority_pid
            or not expected_names
            or authority_module is None
            or module_registry.get(module_name) is not authority_module
        ):
            raise error_type(f"formal {kind} action global authority changed")
        current = get_module_globals()
        current_names = exact_tuple(sort_values(
            name for name in current
            if not name.startswith("__") and name not in excluded
        ))
        if (
            module_vars(authority_module) is not current
            or current_names != expected_names
            or any_true(
                current.get(name, missing) is not expected
                for name, expected in expected_globals
            )
        ):
            raise error_type(f"formal {kind} action global authority changed")
        if any_true(
            get_attribute(namespace, name, missing) is not expected
            for namespace, name, expected in expected_external
        ):
            raise error_type(
                f"formal {kind} action dependency authority changed"
            )
        if any_true(
            exact_tuple(sort_values(module_vars(class_type))) != expected_names
            or any_true(
                module_vars(class_type).get(name, missing) is not expected
                for name, expected in expected_bindings
            )
            for class_type, expected_names, expected_bindings
            in expected_class_namespaces
        ):
            raise error_type(
                f"formal {kind} action dependency authority changed"
            )

    return seal, require


(
    _seal_formal_action_global_bindings,
    _require_formal_action_global_bindings,
) = _make_formal_action_global_binding_guard()


def _require_streamed_runtime_bridge(value: object):
    # Lazy by design: formal_streaming_input uses legacy composer helpers, and
    # that composer imports this adapter.  Keeping the successor edge lazy
    # preserves the established acyclic legacy import boundary.
    from .formal_streaming_bridge import (
        require_streamed_formal_runtime_bridge,
    )

    return require_streamed_formal_runtime_bridge(value)


def _iter_streamed_upload_entries(value: object):
    from .formal_streaming_bridge import iter_streamed_formal_qc_upload_entries

    return iter_streamed_formal_qc_upload_entries(value)


def _require_streamed_authenticated_power_floor(
    value: object,
    runtime_bridge: object,
):
    """Reauthenticate the sole observed-power authority for a formal launch."""

    from .power_calibration_bridge import (
        AcceptedRiskPowerCalibrationError,
        require_authenticated_power_floor_binding,
    )

    try:
        authenticated = require_authenticated_power_floor_binding(value)
    except AcceptedRiskPowerCalibrationError as exc:
        raise FormalQcSubmissionError(
            "streamed launch lacks an authenticated power-floor binding"
        ) from exc
    bridge = _require_streamed_runtime_bridge(runtime_bridge)
    streamed = bridge.resource_candidate.streamed_input
    if (
        authenticated.power_floor is not bridge.formal_run_candidate.power_floor
        or authenticated.power_floor is not streamed.power_floor
        or authenticated.formal_power is not streamed.formal_power
        or authenticated.scoring_artifact_id != streamed.scoring.artifact_id
        or authenticated.scoring_artifact_sha256
        != streamed.scoring.artifact_sha256
        or authenticated.formal_census.scoring_artifact
        is not streamed.scoring
    ):
        raise FormalQcSubmissionError(
            "authenticated power floor escaped the exact formal TEST scorer"
        )
    return authenticated


def _require_streamed_economic_execution(
    value: object,
    runtime_bridge: object,
) -> FormalEconomicExecutionBinding:
    """Reauthenticate the exact pre-outcome economic definition ancestry."""

    try:
        authenticated = require_formal_economic_execution_binding(value)
    except FormalEconomicExecutionDefinitionError as exc:
        raise FormalQcSubmissionError(
            "streamed economic execution binding did not authenticate"
        ) from exc
    bridge = _require_streamed_runtime_bridge(runtime_bridge)
    if (
        authenticated is not bridge.economic_execution
        or authenticated
        is not bridge.resource_candidate.streamed_input.economic_execution
    ):
        raise FormalQcSubmissionError(
            "economic execution binding escaped the exact streamed input"
        )
    return authenticated


def _require_streamed_report_contract(
    value: object,
    runtime_bridge: object,
) -> FormalReportContract:
    """Reauthenticate the sole operative report and bootstrap contract."""

    bridge = _require_streamed_runtime_bridge(runtime_bridge)
    economic = _require_streamed_economic_execution(
        bridge.economic_execution, bridge
    )
    try:
        authenticated = require_formal_report_contract(
            value,
            expected_economic_execution_definition_sha256=(
                economic.definition_sha256
            ),
        )
    except FormalReportContractError as exc:
        raise FormalQcSubmissionError(
            "streamed formal report contract did not authenticate"
        ) from exc
    if (
        authenticated is not bridge.report_contract
        or authenticated is not bridge.resource_candidate.streamed_input.report_contract
    ):
        raise FormalQcSubmissionError(
            "formal report contract escaped the exact streamed input"
        )
    return authenticated


SCHEMA = "arv2-formal-qc-submission-adapter-v2"
STATUS = (
    "offline_reviewable_signature_trust_root_present_no_reviewed_owner_key_"
    "all_external_actions_hard_disabled"
)
AUTHORITY = (
    "detached_ed25519_owner_reviewer_trust_root_registry_empty_no_network_"
    "result_deployment_order_or_trading_authority"
)
UPLOAD_BUNDLE_SCHEMA = "arv2-formal-qc-compact-upload-bundle-v2"
SUBMISSION_PLAN_SCHEMA = "arv2-formal-qc-submission-plan-v2"
LAUNCH_RECEIPT_SCHEMA = "arv2-formal-qc-launch-receipt-v2"
TERMINAL_STATUS_SCHEMA = "arv2-formal-qc-terminal-status-v3"
RESULT_GATE_CANDIDATE_SCHEMA = "arv2-formal-qc-result-gate-candidate-v4"
RESULT_READ_AUTHORITY_SCHEMA = "arv2-formal-qc-result-read-authority-v3"
RESULT_READ_EXTERNAL_PIN_SCHEMA = "arv2-formal-qc-result-read-external-pin-v3"
RESULT_READ_PERMIT_SCHEMA = "arv2-formal-qc-result-read-permit-v2"
RESULT_READ_RECEIPT_SCHEMA = "arv2-formal-qc-summary-result-read-receipt-v3"
EXECUTION_AUTHORITY_SCHEMA = "arv2-formal-qc-execution-authority-v2"
HOST_CLOSURE_SCHEMA = "arv2-formal-qc-host-closure-v2"
TRANSPORT_BINDING_SCHEMA = "arv2-formal-qc-transport-binding-v2"
STREAMED_EXECUTION_AUTHORITY_SCHEMA = (
    "arv2-streamed-formal-qc-execution-authority-v1"
)
STREAMED_SUBMISSION_PLAN_SCHEMA = "arv2-streamed-formal-qc-submission-plan-v1"
STREAMED_SUBMISSION_BRIDGE_SCHEMA = (
    "arv2-streamed-formal-qc-submission-adapter-bridge-v2"
)
RESULT_READ_EXTERNAL_PIN_FILENAME = "arv2-formal-qc-result-read-pin-v1.json"
RESULT_READ_LEDGER_FILENAME = "arv2-formal-qc-result-read-spend-v1.json"
MAX_RESULT_READ_CONTROL_BYTES = 65_536

# These three registries are process authorities, not content caches.  A
# launch, terminal observation, or result receipt becomes authentic only when
# the adapter records the exact object returned across its corresponding
# transport boundary.  Publicly recomputing an identical dataclass and hashes
# cannot reproduce that authority.
_LAUNCH_RECEIPT_AUTHORITIES_LOCK = threading.RLock()
_LAUNCH_RECEIPT_AUTHORITIES: dict[int, tuple[object, ...]] = {}
_TERMINAL_STATUS_RECEIPT_AUTHORITIES_LOCK = threading.RLock()
_TERMINAL_STATUS_RECEIPT_AUTHORITIES: dict[int, tuple[object, ...]] = {}
_SUMMARY_RESULT_RECEIPT_AUTHORITIES_LOCK = threading.RLock()
_SUMMARY_RESULT_RECEIPT_AUTHORITIES: dict[int, tuple[object, ...]] = {}


def _make_process_receipt_authority_vault():
    """Return private register/check operations for transport-return receipts."""

    private_registries: tuple[
        tuple[str, tuple[tuple[int, tuple[object, ...]], ...]], ...
    ] = (("launch", ()), ("terminal", ()), ("summary", ()))
    register_provenance: tuple[
        tuple[str, tuple[tuple[tuple[object, ...], ...], ...]], ...
    ] = ()
    missing_closure_value = object()
    function_type = type(_make_process_receipt_authority_vault)
    get_frame = sys._getframe
    get_pid = os.getpid
    module_registry = sys.modules
    module_vars = vars
    exact_tuple = tuple
    any_true = any
    module_name = __name__
    authority_module = module_registry.get(module_name)

    def private_registry(
        kind: str,
    ) -> tuple[tuple[int, tuple[object, ...]], ...]:
        return next(
            (records for name, records in private_registries if name == kind),
            (),
        )

    def replace_private_registry(
        kind: str,
        records: tuple[tuple[int, tuple[object, ...]], ...],
    ) -> None:
        nonlocal private_registries

        private_registries = tuple(
            (name, records if name == kind else current)
            for name, current in private_registries
        )

    def private_entry(
        kind: str, identity: int,
    ) -> tuple[object, ...] | None:
        return next(
            (entry for key, entry in private_registry(kind) if key == identity),
            None,
        )

    def caller_is_exact(kind: str) -> bool:
        alternatives = next(
            (
                value for name, value in register_provenance
                if name == kind
            ),
            (),
        )
        for expected_chain in alternatives:
            frame = get_frame(2)
            for position, provenance in enumerate(expected_chain):
                (
                    expected_function,
                    expected_code,
                    expected_name,
                    expected_global_bindings,
                    expected_closure,
                ) = provenance
                if (
                    frame is None
                    or frame.f_code is not expected_code
                    or frame.f_code.co_name != expected_name
                    or frame.f_globals.get("__name__") != module_name
                    or authority_module is None
                    or module_registry.get(module_name) is not authority_module
                    or module_vars(authority_module) is not frame.f_globals
                    or expected_function.__code__ is not expected_code
                    or expected_function.__globals__ is not frame.f_globals
                    or expected_function.__name__ != expected_name
                    or any_true(
                        expected_function.__globals__.get(
                            name, missing_closure_value
                        ) is not expected
                        or frame.f_globals.get(
                            name, missing_closure_value
                        ) is not expected
                        for name, expected in expected_global_bindings
                    )
                    or exact_tuple(expected_function.__code__.co_freevars)
                    != exact_tuple(item[0] for item in expected_closure)
                    or len(expected_function.__closure__ or ())
                    != len(expected_closure)
                    or any_true(
                        cell.cell_contents is not expected
                        for cell, (_name, expected) in zip(
                            expected_function.__closure__ or (),
                            expected_closure,
                            strict=True,
                        )
                    )
                    or any_true(
                        frame.f_locals.get(name, missing_closure_value)
                        is not expected
                        for name, expected in expected_closure
                    )
                    or (
                        position == len(expected_chain) - 1
                        and frame.f_globals.get(expected_name)
                        is not expected_function
                    )
                ):
                    break
                frame = frame.f_back
            else:
                return True
        return False

    def public_registry_and_lock(
        kind: str,
    ) -> tuple[dict[int, tuple[object, ...]], threading.RLock]:
        if kind == "launch":
            return _LAUNCH_RECEIPT_AUTHORITIES, _LAUNCH_RECEIPT_AUTHORITIES_LOCK
        if kind == "terminal":
            return (
                _TERMINAL_STATUS_RECEIPT_AUTHORITIES,
                _TERMINAL_STATUS_RECEIPT_AUTHORITIES_LOCK,
            )
        if kind == "summary":
            return (
                _SUMMARY_RESULT_RECEIPT_AUTHORITIES,
                _SUMMARY_RESULT_RECEIPT_AUTHORITIES_LOCK,
            )
        raise AssertionError("unknown process receipt authority kind")

    def forget(kind: str, identity: int, reference: object) -> None:
        public, lock = public_registry_and_lock(kind)
        with lock:
            current = private_entry(kind, identity)
            if current is not None and current[0] is reference:
                replace_private_registry(
                    kind,
                    tuple(
                        item for item in private_registry(kind)
                        if item[0] != identity
                    ),
                )
            if public.get(identity) is current:
                public.pop(identity, None)

    def reset_after_fork() -> None:
        nonlocal private_registries
        global _LAUNCH_RECEIPT_AUTHORITIES_LOCK
        global _LAUNCH_RECEIPT_AUTHORITIES
        global _TERMINAL_STATUS_RECEIPT_AUTHORITIES_LOCK
        global _TERMINAL_STATUS_RECEIPT_AUTHORITIES
        global _SUMMARY_RESULT_RECEIPT_AUTHORITIES_LOCK
        global _SUMMARY_RESULT_RECEIPT_AUTHORITIES

        _LAUNCH_RECEIPT_AUTHORITIES_LOCK = threading.RLock()
        _LAUNCH_RECEIPT_AUTHORITIES = {}
        _TERMINAL_STATUS_RECEIPT_AUTHORITIES_LOCK = threading.RLock()
        _TERMINAL_STATUS_RECEIPT_AUTHORITIES = {}
        _SUMMARY_RESULT_RECEIPT_AUTHORITIES_LOCK = threading.RLock()
        _SUMMARY_RESULT_RECEIPT_AUTHORITIES = {}
        private_registries = (
            ("launch", ()), ("terminal", ()), ("summary", ())
        )

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)

    def register(
        kind: str,
        value: object,
        entry_tail: tuple[object, ...],
    ) -> object:
        public, lock = public_registry_and_lock(kind)
        if get_pid() != authority_pid or not caller_is_exact(kind):
            raise FormalQcSubmissionError(
                f"{kind} receipt register caller changed"
            )
        identity = id(value)
        reference = weakref.ref(
            value,
            lambda ref, receipt_kind=kind, key=identity: forget(
                receipt_kind, key, ref
            ),
        )
        entry = (reference, *entry_tail, get_pid())
        with lock:
            if private_entry(kind, identity) is not None or identity in public:
                raise FormalQcSubmissionError(
                    f"{kind} receipt authority identity was reused"
                )
            replace_private_registry(
                kind,
                (*private_registry(kind), (identity, entry)),
            )
            # Public registries are accounting/cleanup mirrors only.  A
            # process authority also requires exact identity with this
            # independently retained lexical entry.
            public[identity] = entry
        return value

    def current(kind: str, value: object) -> tuple[object, ...] | None:
        public, lock = public_registry_and_lock(kind)
        identity = id(value)
        with lock:
            private = private_entry(kind, identity)
            public_entry = public.get(identity)
            if (
                private is None
                or public_entry is not private
                or private[0]() is not value
                or private[-1] != get_pid()
            ):
                replace_private_registry(
                    kind,
                    tuple(
                        item for item in private_registry(kind)
                        if item[0] != identity
                    ),
                )
                public.pop(identity, None)
                return None
            return private

    def register_launch(value: object, entry_tail: tuple[object, ...]) -> object:
        return register("launch", value, entry_tail)

    def current_launch(value: object) -> tuple[object, ...] | None:
        return current("launch", value)

    def register_terminal(value: object, entry_tail: tuple[object, ...]) -> object:
        return register("terminal", value, entry_tail)

    def current_terminal(value: object) -> tuple[object, ...] | None:
        return current("terminal", value)

    def register_summary(value: object, entry_tail: tuple[object, ...]) -> object:
        return register("summary", value, entry_tail)

    def current_summary(value: object) -> tuple[object, ...] | None:
        return current("summary", value)

    def seal_register_provenance(
        value: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...],
    ) -> None:
        nonlocal register_provenance

        if (
            register_provenance
            or type(value) is not tuple
            or tuple(item[0] for item in value)
            != ("launch", "terminal", "summary")
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[1]) is not tuple
                or not item[1]
                or any(
                    type(chain) is not tuple
                    or not chain
                    or any(
                        type(function) is not function_type
                        or authority_module is None
                        or function.__globals__ is not vars(authority_module)
                        or function.__module__ != __name__
                        for function in chain
                    )
                    for chain in item[1]
                )
                for item in value
            )
        ):
            raise FormalQcSubmissionError(
                "process receipt register provenance changed"
            )
        try:
            register_provenance = tuple(
                (
                    kind,
                    tuple(
                        tuple(
                            (
                                function,
                                function.__code__,
                                function.__name__,
                                tuple(
                                    (
                                        name,
                                        function.__globals__.get(
                                            name, missing_closure_value
                                        ),
                                    )
                                    for name in function.__code__.co_names
                                ),
                                tuple(
                                    (name, cell.cell_contents)
                                    for name, cell in zip(
                                        function.__code__.co_freevars,
                                        function.__closure__ or (),
                                        strict=True,
                                    )
                                ),
                            )
                            for function in chain
                        )
                        for chain in alternatives
                    ),
                )
                for kind, alternatives in value
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise FormalQcSubmissionError(
                "process receipt register provenance changed"
            ) from exc

    authority_pid = get_pid()
    return (
        register_launch,
        current_launch,
        register_terminal,
        current_terminal,
        register_summary,
        current_summary,
        seal_register_provenance,
    )


(
    _process_authority_register_launch,
    _process_authority_current_launch,
    _process_authority_register_terminal,
    _process_authority_current_terminal,
    _process_authority_register_summary,
    _process_authority_current_summary,
    _seal_process_receipt_authority_provenance,
) = _make_process_receipt_authority_vault()

REQUIRED_HOST_CODE_PATHS = (
    "research/analyst_revisions_v2/accepted_risk_input_pair.py",
    "research/analyst_revisions_v2/production_truth_gate.py",
    "research/analyst_revisions_v2/production_input_pipeline.py",
    "research/analyst_revisions_v2/production_scoring.py",
    "research/analyst_revisions_v2_qc/formal_input_bundle.py",
    "research/analyst_revisions_v2_qc/formal_input_composer.py",
    "research/analyst_revisions_v2_qc/formal_evaluation_bridge.py",
    "research/analyst_revisions_v2_qc/formal_evaluation.py",
    "research/analyst_revisions_v2_qc/formal_cloud_evaluator.py",
    "research/analyst_revisions_v2_qc/formal_run_protocol.py",
    "research/analyst_revisions_v2_qc/formal_runtime_projection.py",
    "research/analyst_revisions_v2_qc/formal_streaming_input.py",
    "research/analyst_revisions_v2_qc/formal_streaming_bridge.py",
    "research/analyst_revisions_v2_qc/formal_qc_transport.py",
    "research/analyst_revisions_v2_qc/owner_signature_authority.py",
    "research/analyst_revisions_v2_qc/formal_submission_adapter.py",
    "research/analyst_revisions_v2_qc/runtime_shard_projection.py",
    "research/quantconnect.py",
)
TRANSPORT_REQUEST_SURFACE = tuple(REQUEST_METHOD_NAMES)
_PINNED_TRANSPORT_METHODS = {
    name: getattr(FormalQcTransport, name) for name in TRANSPORT_REQUEST_SURFACE
}
_PINNED_PRODUCTION_TRANSPORT_CHECK = FormalQcTransport._require_production_configuration
OBJECT_STORE_WRITE_TRANSPORT = "quantconnect_object_set_multipart_objectData_v1"
OBJECT_STORE_VERIFICATION_TRANSPORT = "quantconnect_object_properties_size_md5_v1"
COMPILE_PENDING_STATES = frozenset({"InQueue", "Building"})
COMPILE_TERMINAL_STATES = frozenset({"BuildSuccess", "BuildError"})
BACKTEST_PENDING_STATUSES = frozenset({"In Queue...", "In Progress..."})
BACKTEST_TERMINAL_STATUSES = frozenset({"Completed.", "Runtime Error"})
MAX_COMPILE_POLLS = 120
MAX_STATUS_POLLS = 240
COMPILE_POLL_INTERVAL_SECONDS = 2
STATUS_POLL_INTERVAL_SECONDS = 30
FORMAL_RESULT_LOGICAL_READ_COUNT = 1
FORMAL_RESULT_SUMMARY_READ_COUNT = 1
FORMAL_RESULT_FAMILY_READ_COUNT = FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT
FORMAL_RESULT_TRANSPORT_CALL_COUNT = (
    FORMAL_RESULT_SUMMARY_READ_COUNT + FORMAL_RESULT_FAMILY_READ_COUNT
)
FORMAL_RESULT_ROOT_MAXIMUM_BYTE_COUNT = 4_194_304
FORMAL_RESULT_ROOT_MAXIMUM_COMPRESSED_BYTE_COUNT = 200_000
FORMAL_RESULT_FAMILY_MAXIMUM_UNCOMPRESSED_BYTE_COUNT = 4_194_304
FORMAL_RESULT_FAMILY_TOTAL_MAXIMUM_UNCOMPRESSED_BYTE_COUNT = 109_051_904
FORMAL_RESULT_FAMILY_KEY_FORMULA = (
    "{project_id}/arv2/formal/output/report-families/"
    "{input_manifest_sha256}/{ordinal:02d}-{compressed_sha256}.json.gz"
)
EXECUTION_ACTIONS = (
    "authenticate",
    "projects/read_exact_name_inventory",
    "projects/create_private_exact_name_once",
    "object/set_multipart_exact_content_addressed_input",
    "object/properties_verify_exact_key_size_md5",
    "files/read_exact_inventory",
    "files/create_or_update_exact_projection",
    "compile/create_once",
    "compile/read_state_only_with_bounded_wait",
    "backtests/create_once",
    "backtests/list_identity_status_includeStatistics_false",
)

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX_32 = re.compile(r"[0-9a-f]{32}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/ -]{0,511}\Z")
_SAFE_PATH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,1023}\Z")
_TOP_STATUS_KEYS = frozenset({"success", "errors", "messages", "backtests", "count"})
_BACKTEST_STATUS_KEYS = frozenset(
    {
        "backtestId",
        "name",
        "status",
        "projectId",
        "created",
        "completed",
        "progress",
        "note",
    }
)
# ``/backtests/list`` returns a summary object whose documented shape includes
# performance fields even when ``includeStatistics`` is false.  Status polling
# must tolerate those *keys* without ever indexing, traversing, comparing, or
# returning their values.  The non-result metadata keys below receive the same
# discard-only treatment because none is needed to authenticate identity or
# terminal status.  Unknown keys still fail closed.
_DISCARDED_BACKTEST_SUMMARY_KEYS = frozenset(
    {
        "analysis",
        "backtestEnd",
        "backtestStart",
        "capacity",
        "charts",
        "closedTrades",
        "debugging",
        "error",
        "estimatedStrategyCapacity",
        "hasInitializeError",
        "insights",
        "nodeName",
        "optimizationId",
        "orders",
        "orderEvents",
        "organizationId",
        "outOfSampleDays",
        "outOfSampleMaxEndDate",
        "performanceStatistics",
        "tradeableDates",
        "parameterSet",
        "portfolioStatistics",
        "profitLoss",
        "researchGuide",
        "result",
        "results",
        "rollingWindow",
        "runtimeStatistics",
        "serverStatistics",
        "snapshotId",
        "stacktrace",
        "statistics",
        "tags",
        "totalFees",
        "totalNetProfit",
        "totalPerformance",
        "tradeStatistics",
        "sharpeRatio",
        "alpha",
        "beta",
        "compoundingAnnualReturn",
        "drawdown",
        "lossRate",
        "netProfit",
        "parameters",
        "psr",
        "securityTypes",
        "sortinoRatio",
        "trades",
        "treynorRatio",
        "winRate",
    }
)

def _make_downstream_transport_minter_claims(
    root_minter, root_register_delegated_minter,
):
    """Issue least-authority minters only to three exact adapter imports."""

    get_pid = os.getpid
    get_frame = sys._getframe
    real_path = os.path.realpath
    module_registry = sys.modules
    module_vars = vars
    get_module_globals = globals
    exact_type = type
    exact_tuple = tuple
    exact_len = len
    any_true = any
    authority_pid = get_pid()
    claimed: tuple[str, ...] = ()
    specifications = (
        (
            "fundamental",
            "research.analyst_revisions_v2_qc."
            "fundamental_universe_discovery_submission_adapter",
            "fundamental_universe_discovery_submission_adapter.py",
            (
                (
                    "submission",
                    ("_execute_fundamental_discovery_submission_once_impl",),
                ),
                (
                    "status",
                    ("_inspect_fundamental_discovery_terminal_status_impl",),
                ),
                (
                    "preopen_output_read",
                    (
                        "_download_and_review_fundamental_discovery_archive_impl",
                    ),
                ),
            ),
            "_claim_fundamental_discovery_transport_capability_minter",
        ),
        (
            "preopen",
            "research.analyst_revisions_v2_qc."
            "preopen_control_submission_adapter",
            "preopen_control_submission_adapter.py",
            (
                ("submission", ("_execute_preopen_qc_submission_once_impl",)),
                ("status", ("_inspect_preopen_qc_terminal_status_impl",)),
                (
                    "preopen_output_read",
                    (
                        "_retrieve_preopen_qc_terminal_package_impl",
                        "_download_and_load_preopen_qc_terminal_archive_impl",
                    ),
                ),
            ),
            "_claim_preopen_transport_capability_minter",
        ),
        (
            "power",
            "research.analyst_revisions_v2_qc."
            "power_calibration_submission_adapter",
            "power_calibration_submission_adapter.py",
            (
                (
                    "submission",
                    ("_execute_power_calibration_submission_once_impl",),
                ),
                (
                    "status",
                    ("_inspect_power_calibration_terminal_status_impl",),
                ),
                (
                    "power_calibration_output_read",
                    ("_persist_power_calibration_output_impl",),
                ),
            ),
            "_claim_power_calibration_transport_capability_minter",
        ),
    )

    def make_claim(adapter_key: str):
        specification = next(
            (item for item in specifications if item[0] == adapter_key),
            None,
        )
        if specification is None:
            raise AssertionError("unknown downstream adapter key")
        (
            _key,
            expected_name,
            filename,
            allowed_caller_names,
            claim_name,
        ) = specification
        expected_path = real_path(
            os.path.join(os.path.dirname(__file__), filename)
        )
        caller_provenance: tuple[
            tuple[str, tuple[tuple[tuple[object, ...], ...], ...]], ...
        ] = ()
        missing_closure_value = object()
        function_type = exact_type(make_claim)

        def capture_function(function: object) -> tuple[object, ...]:
            expected_module = module_registry.get(expected_name)
            if (
                exact_type(function) is not function_type
                or function.__module__ != expected_name
                or expected_module is None
                or function.__globals__ is not module_vars(expected_module)
                or real_path(function.__code__.co_filename)
                != expected_path
            ):
                raise FormalQcSubmissionError(
                    "downstream transport minter provenance is incomplete"
                )
            closure = function.__closure__ or ()
            if exact_len(closure) != exact_len(function.__code__.co_freevars):
                raise FormalQcSubmissionError(
                    "downstream transport minter provenance is incomplete"
                )
            return (
                function,
                function.__code__,
                function.__name__,
                expected_module,
                tuple(
                    (
                        name,
                        function.__globals__.get(
                            name, missing_closure_value
                        ),
                    )
                    for name in function.__code__.co_names
                ),
                tuple(
                    (name, cell.cell_contents)
                    for name, cell in zip(
                        function.__code__.co_freevars,
                        closure,
                        strict=True,
                    )
                ),
            )

        def caller_is_exact(scope: str) -> bool:
            alternatives = next(
                (
                    chains
                    for expected_scope, chains in caller_provenance
                    if expected_scope == scope
                ),
                (),
            )
            registered = module_registry.get(expected_name)
            for chain in alternatives:
                frame = get_frame(2)
                for position, provenance in enumerate(chain):
                    (
                        expected_function,
                        expected_code,
                        expected_function_name,
                        expected_module,
                        expected_global_bindings,
                        expected_closure,
                    ) = provenance
                    if (
                        frame is None
                        or frame.f_code is not expected_code
                        or frame.f_code.co_name != expected_function_name
                        or frame.f_globals.get("__name__") != expected_name
                        or registered is not expected_module
                        or module_vars(expected_module) is not frame.f_globals
                        or real_path(frame.f_code.co_filename)
                        != expected_path
                        or expected_function.__code__ is not expected_code
                        or expected_function.__globals__ is not frame.f_globals
                        or expected_function.__name__
                        != expected_function_name
                        or any_true(
                            expected_function.__globals__.get(
                                name, missing_closure_value
                            ) is not expected
                            or frame.f_globals.get(
                                name, missing_closure_value
                            ) is not expected
                            for name, expected in expected_global_bindings
                        )
                        or exact_tuple(expected_function.__code__.co_freevars)
                        != exact_tuple(item[0] for item in expected_closure)
                        or exact_len(expected_function.__closure__ or ())
                        != exact_len(expected_closure)
                        or any_true(
                            cell.cell_contents is not expected
                            for cell, (_name, expected) in zip(
                                expected_function.__closure__ or (),
                                expected_closure,
                                strict=True,
                            )
                        )
                        or any_true(
                            frame.f_locals.get(
                                name, missing_closure_value
                            ) is not expected
                            for name, expected in expected_closure
                        )
                        or (
                        position == exact_len(chain) - 1
                            and frame.f_globals.get(expected_function_name)
                            is not expected_function
                        )
                    ):
                        break
                    frame = frame.f_back
                else:
                    return True
            return False

        def claim():
            nonlocal claimed

            try:
                caller = get_frame(1)
                caller_globals = caller.f_globals
                caller_name = caller_globals.get("__name__")
                caller_path = real_path(caller.f_code.co_filename)
                caller_code_name = caller.f_code.co_name
                registered = module_registry.get(expected_name)
            except (AttributeError, OSError, TypeError):
                caller = None
                caller_globals = None
                caller_name = None
                caller_path = ""
                caller_code_name = ""
                registered = None
            if (
                get_pid() != authority_pid
                or adapter_key in claimed
                or caller_name != expected_name
                or registered is None
                or module_vars(registered) is not caller_globals
                or caller_path != expected_path
                or caller_code_name != "<module>"
            ):
                raise FormalQcSubmissionError(
                    "downstream transport minter claim is adapter-private"
                )
            try:
                allowed_callers = exact_tuple(
                    (
                        scope,
                        exact_tuple(
                            caller_globals[name].__code__ for name in names
                        ),
                    )
                    for scope, names in allowed_caller_names
                )
            except (AttributeError, KeyError, TypeError) as exc:
                raise FormalQcSubmissionError(
                    "downstream transport minter provenance is incomplete"
                ) from exc
            if any_true(not codes for _scope, codes in allowed_callers):
                raise FormalQcSubmissionError(
                    "downstream transport minter provenance is incomplete"
                )
            claimed = (*claimed, adapter_key)
            minter_pid = get_pid()

            def mint(
                *, transport: FormalQcTransport, scope: str,
                binding_record: Mapping[str, object],
                call_budget: Mapping[str, int],
            ) -> object:
                if (
                    get_pid() != minter_pid
                    or not caller_is_exact(scope)
                ):
                    raise FormalQcSubmissionError(
                        "downstream transport capability caller changed"
                    )
                return root_minter(
                    transport=transport,
                    scope=scope,
                    binding_record=binding_record,
                    call_budget=call_budget,
                )

            root_register_delegated_minter(adapter_key, mint)

            def seal_callers(
                value: tuple[
                    tuple[str, tuple[tuple[object, ...], ...]], ...
                ],
            ) -> None:
                nonlocal caller_provenance

                if (
                    caller_provenance
                    or exact_type(value) is not exact_tuple
                    or exact_tuple(item[0] for item in value)
                    != exact_tuple(item[0] for item in allowed_caller_names)
                    or any_true(
                        exact_type(item) is not exact_tuple
                        or exact_len(item) != 2
                        or exact_type(item[1]) is not exact_tuple
                        or not item[1]
                        or any_true(
                            exact_type(chain) is not exact_tuple
                            or exact_len(chain) < 2
                            for chain in item[1]
                        )
                        for item in value
                    )
                ):
                    raise FormalQcSubmissionError(
                        "downstream transport caller provenance changed"
                    )
                try:
                    captured = exact_tuple(
                        (
                            scope,
                            exact_tuple(
                                exact_tuple(
                                    capture_function(function)
                                    for function in chain
                                )
                                for chain in alternatives
                            ),
                        )
                        for scope, alternatives in value
                    )
                except (AttributeError, OSError, TypeError, ValueError) as exc:
                    raise FormalQcSubmissionError(
                        "downstream transport caller provenance changed"
                    ) from exc
                for scope, alternatives in captured:
                    allowed_codes = next(
                        codes
                        for expected_scope, codes in allowed_callers
                        if expected_scope == scope
                    )
                    if any_true(
                        chain[0][1] not in allowed_codes
                        for chain in alternatives
                    ):
                        raise FormalQcSubmissionError(
                            "downstream transport caller provenance changed"
                        )
                caller_provenance = captured

            get_module_globals().pop(claim_name, None)
            if caller_globals is not None:
                caller_globals.pop(claim_name, None)
            del caller
            return mint, seal_callers

        return claim

    return (
        make_claim("fundamental"),
        make_claim("preopen"),
        make_claim("power"),
    )


def _require_non_self_mintable_execution_trust_root(
    value: OwnerSignatureAuthority | None, authority_payload: bytes,
) -> None:
    """Reauthenticate the detached owner signature over the exact authority."""

    try:
        require_formal_execution_owner_signature(
            value, authority_payload=authority_payload
        )
    except OwnerSignatureAuthorityError as exc:
        raise FormalQcSubmissionError(
            "non-self-mintable owner/reviewer execution trust root is unavailable"
        ) from exc


def _require_non_self_mintable_result_read_trust_root(
    value: OwnerSignatureAuthority | None, authority_payload: bytes,
) -> None:
    """Reauthenticate the separately scoped result-read owner signature."""

    try:
        require_formal_result_read_owner_signature(
            value, authority_payload=authority_payload
        )
    except OwnerSignatureAuthorityError as exc:
        raise FormalQcSubmissionError(
            "non-self-mintable owner/reviewer result-read trust root is unavailable"
        ) from exc


def _canonical(value: object) -> bytes:
    try:
        return canonical_json_bytes(value)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise FormalQcSubmissionError("submission value is not canonical JSON") from exc


def _json_object(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload:
        raise FormalQcSubmissionError(f"{name} must be nonempty exact bytes")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise FormalQcSubmissionError(f"{name} is not UTF-8 JSON") from exc
    if type(value) is not dict or _canonical(value) != payload:
        raise FormalQcSubmissionError(f"{name} is not one canonical JSON object")
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise FormalQcSubmissionError(f"{name} is not a lowercase SHA-256")
    return value


def _safe_id(value: object, name: str) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        raise FormalQcSubmissionError(f"{name} is not a safe identifier")
    return value


def _positive_int(value: object, name: str, *, zero: bool = False) -> int:
    if type(value) is not int or value < (0 if zero else 1):
        raise FormalQcSubmissionError(f"{name} is not an exact positive census")
    return value


def _require_concrete_transport(value: FormalQcTransport) -> FormalQcTransport:
    if type(value) is not FormalQcTransport or any(
        getattr(FormalQcTransport, name) is not implementation
        or name in vars(value)
        for name, implementation in _PINNED_TRANSPORT_METHODS.items()
    ):
        raise FormalQcSubmissionError("exact reviewed FormalQcTransport surface is required")
    try:
        _PINNED_PRODUCTION_TRANSPORT_CHECK(value)
    except Exception as exc:
        raise FormalQcSubmissionError(
            "exact production-only FormalQcTransport configuration is required"
        ) from exc
    return value


def _transport_call(
    client: FormalQcTransport, capability, method: str, *args, **kwargs
) -> object:
    _require_concrete_transport(client)
    return _PINNED_TRANSPORT_METHODS[method](
        client, capability, *args, **kwargs
    )


def _local_wait(seconds: int) -> None:
    """Wait between polls without invoking caller-controlled code."""

    if type(seconds) is not int or seconds not in {
        COMPILE_POLL_INTERVAL_SECONDS, STATUS_POLL_INTERVAL_SECONDS,
    }:
        raise FormalQcSubmissionError("poll wait interval changed")
    time.sleep(seconds)


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcUploadEntry:
    role: str
    object_store_key: str
    content_sha256: str
    content_md5: str
    byte_count: int
    payload: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            "role": self.role,
            "object_store_key": self.object_store_key,
            "content_sha256": self.content_sha256,
            "content_md5": self.content_md5,
            "byte_count": self.byte_count,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcUploadBundle:
    bundle_id: str
    bundle_sha256: str
    entries: tuple[FormalQcUploadEntry, ...]
    input_manifest: QcObjectPayloadBinding
    shards: tuple[FormalQcCompressedShard, ...]
    total_byte_count: int
    _canonical_document: bytes = dataclasses.field(repr=False)


def _upload_entry(role: str, key: str, payload: bytes) -> FormalQcUploadEntry:
    _safe_id(role, "upload role")
    if type(key) is not str or _SAFE_PATH.fullmatch(key) is None:
        raise FormalQcSubmissionError("upload Object Store key changed")
    if type(payload) is not bytes or not payload:
        raise FormalQcSubmissionError("upload payload must be exact nonempty bytes")
    return FormalQcUploadEntry(
        role=role,
        object_store_key=key,
        content_sha256=hashlib.sha256(payload).hexdigest(),
        content_md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        byte_count=len(payload),
        payload=bytes(payload),
    )


def build_formal_qc_upload_bundle(
    *,
    input_manifest: QcObjectPayloadBinding,
    manifest_payload: bytes,
    shards: tuple[FormalQcCompressedShard, ...],
) -> FormalQcUploadBundle:
    require_qc_object_payload_binding(input_manifest)
    if (
        input_manifest.role != "input_manifest"
        or input_manifest.schema != INPUT_MANIFEST_SCHEMA
        or input_manifest.object_store_key != FORMAL_INPUT_PREFIX + input_manifest.content_sha256 + ".json"
        or hashlib.sha256(manifest_payload).hexdigest() != input_manifest.content_sha256
        or len(manifest_payload) != input_manifest.byte_count
    ):
        raise FormalQcSubmissionError("input manifest upload binding changed")
    _json_object(manifest_payload, "input manifest")
    try:
        validate_formal_qc_runtime_resource_candidate(
            manifest_payload=manifest_payload,
            shards=shards,
        )
    except (TypeError, ValueError) as exc:
        raise FormalQcSubmissionError("compact input resource readiness changed") from exc
    entries = (
        *(
            _upload_entry(item.role, item.object_store_key, item.payload)
            for item in shards
        ),
        # Publish the content-addressed manifest only after every referenced
        # object; a partial upload is never discoverable as a complete input.
        _upload_entry("input_manifest", input_manifest.object_store_key, manifest_payload),
    )
    if len({item.object_store_key for item in entries}) != len(entries):
        raise FormalQcSubmissionError("upload bundle contains duplicate Object Store keys")
    seed = {
        "schema": UPLOAD_BUNDLE_SCHEMA,
        "bundle_id": None,
        "bundle_sha256": None,
        "entries": [item.to_record() for item in entries],
        "entry_count": len(entries),
        "total_byte_count": sum(item.byte_count for item in entries),
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["bundle_sha256"] = digest
    seed["bundle_id"] = "arv2-formal-qc-upload-" + digest[:24]
    return FormalQcUploadBundle(
        bundle_id=str(seed["bundle_id"]),
        bundle_sha256=digest,
        entries=entries,
        input_manifest=input_manifest,
        shards=shards,
        total_byte_count=sum(item.byte_count for item in entries),
        _canonical_document=_canonical(seed),
    )


def require_formal_qc_upload_bundle(value: FormalQcUploadBundle) -> FormalQcUploadBundle:
    if type(value) is not FormalQcUploadBundle:
        raise FormalQcSubmissionError("upload bundle type changed")
    manifest = next((item for item in value.entries if item.role == "input_manifest"), None)
    if manifest is None:
        raise FormalQcSubmissionError("upload bundle lost its input manifest")
    rebuilt = build_formal_qc_upload_bundle(
        input_manifest=value.input_manifest,
        manifest_payload=manifest.payload,
        shards=value.shards,
    )
    if any(
        getattr(value, field.name) != getattr(rebuilt, field.name)
        for field in dataclasses.fields(FormalQcUploadBundle)
    ):
        raise FormalQcSubmissionError("upload bundle changed")
    return value


def _require_upload_projection_capacity(
    upload_bundle: FormalQcUploadBundle,
    projection: FormalQcRuntimeProjection,
) -> None:
    require_formal_qc_upload_bundle(upload_bundle)
    require_formal_qc_runtime_projection(projection)
    manifest_entry = next(
        item for item in upload_bundle.entries if item.role == "input_manifest"
    )
    manifest = _json_object(manifest_entry.payload, "input manifest")
    _require_upstream_materialization_capacity(manifest)
    capacity = manifest.get("capacity_review")
    limits = capacity.get("limits") if type(capacity) is dict else None
    if (
        manifest.get("cloud_evaluator")
        != projection.evaluator_source_closure.to_record()
        or type(limits) is not dict
        or type(limits.get("max_object_store_total_input_byte_count")) is not int
        or upload_bundle.total_byte_count
        > limits["max_object_store_total_input_byte_count"]
        or type(limits.get("max_single_object_byte_count")) is not int
        or max(item.byte_count for item in upload_bundle.entries)
        > limits["max_single_object_byte_count"]
        or type(limits.get("max_project_file_count")) is not int
        or len(projection.source_files) > limits["max_project_file_count"]
        or type(limits.get("max_project_source_character_count")) is not int
        or sum(item.character_count for item in projection.source_files)
        > limits["max_project_source_character_count"]
    ):
        raise FormalQcSubmissionError(
            "input/evaluator/project/Object Store capacity binding changed"
        )


def _require_upstream_materialization_capacity(
    manifest: Mapping[str, object],
) -> None:
    """Keep launch closed until a distinct reviewed upstream artifact exists."""

    value = manifest.get("upstream_scoring_materialization_capacity")
    expected_fields = {
        "schema", "status", "artifact_binding", "distinct_from_runtime_capacity",
        "one_fold_streaming_projection_verified",
        "production_truth_materialization_capacity_verified",
        "representative_full_census_verified", "launch_authorized",
    }
    artifact = value.get("artifact_binding") if type(value) is dict else None
    if (
        type(value) is not dict
        or set(value) != expected_fields
        or value.get("schema") != UPSTREAM_MATERIALIZATION_CAPACITY_SCHEMA
        or value.get("status") != "reviewed_upstream_capacity_affirmative"
        or value.get("distinct_from_runtime_capacity") is not True
        or value.get("one_fold_streaming_projection_verified") is not True
        or value.get("production_truth_materialization_capacity_verified") is not True
        or value.get("representative_full_census_verified") is not True
        or value.get("launch_authorized") is not True
        or type(artifact) is not dict
        or set(artifact) != {
            "artifact_id", "content_sha256", "artifact_sha256", "byte_count",
        }
        or _SAFE_ID.fullmatch(str(artifact.get("artifact_id"))) is None
        or _HEX_64.fullmatch(str(artifact.get("content_sha256"))) is None
        or _HEX_64.fullmatch(str(artifact.get("artifact_sha256"))) is None
        or type(artifact.get("byte_count")) is not int
        or artifact["byte_count"] < 1
    ):
        raise FormalQcSubmissionError(
            "separate reviewed upstream scoring materialization capacity is absent"
        )


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcHostSourceBinding:
    path: str
    content_sha256: str
    byte_count: int

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcHostClosureBinding:
    closure_id: str
    closure_sha256: str
    worktree_root: str
    sources: tuple[FormalQcHostSourceBinding, ...]
    b5d_project_source_set_id: str
    b5d_project_source_set_sha256: str
    b5d_project_source_set_artifact_sha256: str
    _canonical_document: bytes = dataclasses.field(repr=False)


def _read_live_host_sources(worktree_root: Path) -> tuple[FormalQcHostSourceBinding, ...]:
    if not isinstance(worktree_root, Path) or not worktree_root.is_absolute():
        raise FormalQcSubmissionError("worktree root must be an exact absolute Path")
    root = worktree_root.resolve(strict=True)
    result = []
    for relative in REQUIRED_HOST_CODE_PATHS:
        path = (root / relative).resolve(strict=True)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise FormalQcSubmissionError("host source escaped the worktree") from exc
        payload = path.read_bytes()
        if not payload or b"\r" in payload or not payload.endswith(b"\n"):
            raise FormalQcSubmissionError(f"host source is not canonical LF: {relative}")
        result.append(
            FormalQcHostSourceBinding(
                path=relative,
                content_sha256=hashlib.sha256(payload).hexdigest(),
                byte_count=len(payload),
            )
        )
    return tuple(result)


def build_formal_qc_host_closure_binding(
    *, worktree_root: Path,
    b5d_project_source_set: SyntheticQcRuntimeShardProjection,
) -> FormalQcHostClosureBinding:
    try:
        require_synthetic_qc_runtime_shard_projection(b5d_project_source_set)
    except (TypeError, ValueError) as exc:
        raise FormalQcSubmissionError("B5D source-set ancestry binding changed") from exc
    root = worktree_root.resolve(strict=True)
    sources = _read_live_host_sources(root)
    seed = {
        "schema": HOST_CLOSURE_SCHEMA,
        "closure_id": None,
        "closure_sha256": None,
        "worktree_root": str(root),
        "sources": [item.to_record() for item in sources],
        "b5d_project_source_set": {
            "artifact_id": b5d_project_source_set.projection_id,
            "content_sha256": b5d_project_source_set.projection_sha256,
            "artifact_sha256": b5d_project_source_set.projection_artifact_sha256,
            "project_file_count": b5d_project_source_set.project_file_count,
            "total_projected_source_byte_count":
                b5d_project_source_set.total_projected_source_byte_count,
        },
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["closure_sha256"] = digest
    seed["closure_id"] = "arv2-formal-qc-host-closure-" + digest[:24]
    return FormalQcHostClosureBinding(
        closure_id=str(seed["closure_id"]),
        closure_sha256=digest,
        worktree_root=str(root),
        sources=sources,
        b5d_project_source_set_id=b5d_project_source_set.projection_id,
        b5d_project_source_set_sha256=b5d_project_source_set.projection_sha256,
        b5d_project_source_set_artifact_sha256=
            b5d_project_source_set.projection_artifact_sha256,
        _canonical_document=_canonical(seed),
    )


def require_formal_qc_host_closure_binding(
    value: FormalQcHostClosureBinding,
) -> FormalQcHostClosureBinding:
    if type(value) is not FormalQcHostClosureBinding:
        raise FormalQcSubmissionError("host closure type changed")
    if (
        type(value.sources) is not tuple
        or tuple(item.path for item in value.sources) != REQUIRED_HOST_CODE_PATHS
        or any(
            type(item) is not FormalQcHostSourceBinding
            or _HEX_64.fullmatch(item.content_sha256) is None
            or type(item.byte_count) is not int
            or item.byte_count < 1
            for item in value.sources
        )
    ):
        raise FormalQcSubmissionError("host closure source manifest changed")
    raw = _json_object(value._canonical_document, "host closure")
    if (
        raw.get("schema") != HOST_CLOSURE_SCHEMA
        or raw.get("closure_id") != value.closure_id
        or raw.get("closure_sha256") != value.closure_sha256
        or raw.get("worktree_root") != value.worktree_root
        or raw.get("sources") != [item.to_record() for item in value.sources]
    ):
        raise FormalQcSubmissionError("host closure changed")
    seed = dict(raw)
    seed["closure_id"] = None
    seed["closure_sha256"] = None
    if hashlib.sha256(_canonical(seed)).hexdigest() != value.closure_sha256:
        raise FormalQcSubmissionError("host closure identity changed")
    b5d = raw.get("b5d_project_source_set")
    if type(b5d) is not dict or (
        b5d.get("artifact_id") != value.b5d_project_source_set_id
        or b5d.get("content_sha256") != value.b5d_project_source_set_sha256
        or b5d.get("artifact_sha256") != value.b5d_project_source_set_artifact_sha256
    ):
        raise FormalQcSubmissionError("B5D source-set ancestry changed")
    return value


def verify_formal_qc_host_closure_live(value: FormalQcHostClosureBinding) -> None:
    require_formal_qc_host_closure_binding(value)
    observed = _read_live_host_sources(Path(value.worktree_root))
    if observed != value.sources:
        raise FormalQcSubmissionError("live host code closure changed")


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcTransportBinding:
    transport_id: str
    transport_sha256: str
    schema: str
    implementation_path: str
    implementation_sha256: str
    implementation_byte_count: int
    concrete_type: str
    request_surface: tuple[str, ...]
    object_store_write_transport: str
    object_store_verification_transport: str

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def build_formal_qc_transport_binding(
    *, host_code_closure: FormalQcHostClosureBinding
) -> FormalQcTransportBinding:
    require_formal_qc_host_closure_binding(host_code_closure)
    source = next(
        item for item in host_code_closure.sources
        if item.path == "research/analyst_revisions_v2_qc/formal_qc_transport.py"
    )
    seed = {
        "schema": TRANSPORT_BINDING_SCHEMA,
        "transport_id": None,
        "transport_sha256": None,
        "transport_schema": TRANSPORT_SCHEMA,
        "implementation_path": source.path,
        "implementation_sha256": source.content_sha256,
        "implementation_byte_count": source.byte_count,
        "concrete_type": "FormalQcTransport",
        "request_surface": list(TRANSPORT_REQUEST_SURFACE),
        "object_store_write_transport": OBJECT_STORE_WRITE_TRANSPORT,
        "object_store_verification_transport": OBJECT_STORE_VERIFICATION_TRANSPORT,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["transport_sha256"] = digest
    seed["transport_id"] = "arv2-formal-qc-transport-" + digest[:24]
    return FormalQcTransportBinding(
        transport_id=str(seed["transport_id"]),
        transport_sha256=digest,
        schema=TRANSPORT_SCHEMA,
        implementation_path=source.path,
        implementation_sha256=source.content_sha256,
        implementation_byte_count=source.byte_count,
        concrete_type="FormalQcTransport",
        request_surface=TRANSPORT_REQUEST_SURFACE,
        object_store_write_transport=OBJECT_STORE_WRITE_TRANSPORT,
        object_store_verification_transport=OBJECT_STORE_VERIFICATION_TRANSPORT,
    )


def require_formal_qc_transport_binding(
    value: FormalQcTransportBinding, host_code_closure: FormalQcHostClosureBinding
) -> FormalQcTransportBinding:
    if type(value) is not FormalQcTransportBinding or value != build_formal_qc_transport_binding(
        host_code_closure=host_code_closure
    ):
        raise FormalQcSubmissionError("concrete QC transport binding changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcExecutionAuthority:
    authority_id: str
    authority_sha256: str
    candidate_id: str
    candidate_sha256: str
    projection_id: str
    projection_sha256: str
    upload_bundle_id: str
    upload_bundle_sha256: str
    organization_id_sha256: str
    project_name: str
    backtest_name: str
    host_code_closure: FormalQcHostClosureBinding
    transport: FormalQcTransportBinding
    actions: tuple[str, ...]
    maximum_backtest_submissions: int
    compile_poll_limit: int
    compile_poll_interval_seconds: int
    status_poll_limit: int
    status_poll_interval_seconds: int
    qc_outcome_execution_authorized: bool
    status_only_access_authorized: bool
    result_read_authorized: bool
    log_access_authorized: bool
    deployment_orders_trading_authorized: bool
    owner_signature_authority_id: str | None
    owner_signature_authority_sha256: str | None
    owner_signature_public_key_blob_sha256: str | None
    owner_signature_sha256: str | None
    owner_signature_purpose: str | None
    owner_signed_payload_sha256: str | None
    _receipt_bytes: bytes = dataclasses.field(repr=False)
    _owner_signature: OwnerSignatureAuthority | None = dataclasses.field(repr=False)


def _execution_document(
    *,
    candidate: FormalRunCandidate,
    projection: FormalQcRuntimeProjection,
    upload_bundle: FormalQcUploadBundle,
    host_code_closure: FormalQcHostClosureBinding,
    transport: FormalQcTransportBinding,
    organization_id: str,
) -> dict[str, object]:
    seed = {
        "schema": EXECUTION_AUTHORITY_SCHEMA,
        "status": "requires_exact_owner_external_pin",
        "authority_id": None,
        "authority_sha256": None,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "project_source_set_sha256": projection.project_source_set_sha256,
        "evaluator_source_closure_sha256": projection.evaluator_source_closure_sha256,
        "upload_bundle_id": upload_bundle.bundle_id,
        "upload_bundle_sha256": upload_bundle.bundle_sha256,
        "input_manifest_sha256": upload_bundle.input_manifest.content_sha256,
        "organization_id_sha256": hashlib.sha256(organization_id.encode()).hexdigest(),
        "project_name": projection.project_name,
        "backtest_name": projection.backtest_name,
        "host_code_closure": {
            "closure_id": host_code_closure.closure_id,
            "closure_sha256": host_code_closure.closure_sha256,
        },
        "transport": transport.to_record(),
        "actions": list(EXECUTION_ACTIONS),
        "maximum_backtest_submissions": 1,
        "compile_poll_limit": MAX_COMPILE_POLLS,
        "compile_poll_interval_seconds": COMPILE_POLL_INTERVAL_SECONDS,
        "status_poll_limit": MAX_STATUS_POLLS,
        "status_poll_interval_seconds": STATUS_POLL_INTERVAL_SECONDS,
        "capacity_and_evaluator_receipts_bound_by_input_manifest": True,
        "qc_outcome_execution_authorized": True,
        "status_only_access_authorized": True,
        "result_read_authorized": False,
        "log_access_authorized": False,
        "deployment_orders_trading_authorized": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["authority_sha256"] = digest
    seed["authority_id"] = "arv2-owner-outcome-qc-authority-" + digest
    return seed


def render_formal_qc_execution_authority_candidate(
    *, candidate: FormalRunCandidate, projection: FormalQcRuntimeProjection,
    upload_bundle: FormalQcUploadBundle,
    host_code_closure: FormalQcHostClosureBinding,
    transport: FormalQcTransportBinding, organization_id: str,
) -> bytes:
    require_formal_run_candidate(candidate)
    require_projection_bound_to_candidate(candidate, projection)
    require_formal_qc_upload_bundle(upload_bundle)
    _require_upload_projection_capacity(upload_bundle, projection)
    require_formal_qc_host_closure_binding(host_code_closure)
    require_formal_qc_transport_binding(transport, host_code_closure)
    _safe_id(organization_id, "organization_id")
    if upload_bundle.input_manifest != projection.input_manifest:
        raise FormalQcSubmissionError("projection and upload input manifest differ")
    return _canonical(
        _execution_document(
            candidate=candidate, projection=projection, upload_bundle=upload_bundle,
            host_code_closure=host_code_closure, transport=transport,
            organization_id=organization_id,
        )
    )


def load_formal_qc_execution_authority(
    *, candidate: FormalRunCandidate, reviewed_authority: ReviewedFormalRunAuthority,
    projection: FormalQcRuntimeProjection, upload_bundle: FormalQcUploadBundle,
    host_code_closure: FormalQcHostClosureBinding,
    transport: FormalQcTransportBinding, organization_id: str,
    receipt_bytes: bytes,
    owner_signature: OwnerSignatureAuthority | None = None,
) -> FormalQcExecutionAuthority:
    require_reviewed_formal_run_authority(candidate, reviewed_authority)
    expected = render_formal_qc_execution_authority_candidate(
        candidate=candidate, projection=projection, upload_bundle=upload_bundle,
        host_code_closure=host_code_closure, transport=transport,
        organization_id=organization_id,
    )
    if type(receipt_bytes) is not bytes or receipt_bytes != expected:
        raise FormalQcSubmissionError("execution authority receipt bytes changed")
    _require_non_self_mintable_execution_trust_root(owner_signature, expected)
    raw = _json_object(receipt_bytes, "execution authority receipt")
    if reviewed_authority.owner_outcome_authority_receipt_id != raw["authority_id"]:
        raise FormalQcSubmissionError("owner review pin does not bind this exact execution authority")
    return FormalQcExecutionAuthority(
        authority_id=str(raw["authority_id"]),
        authority_sha256=str(raw["authority_sha256"]),
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        projection_id=projection.projection_id,
        projection_sha256=projection.projection_sha256,
        upload_bundle_id=upload_bundle.bundle_id,
        upload_bundle_sha256=upload_bundle.bundle_sha256,
        organization_id_sha256=str(raw["organization_id_sha256"]),
        project_name=projection.project_name,
        backtest_name=projection.backtest_name,
        host_code_closure=host_code_closure,
        transport=transport,
        actions=EXECUTION_ACTIONS,
        maximum_backtest_submissions=1,
        compile_poll_limit=MAX_COMPILE_POLLS,
        compile_poll_interval_seconds=COMPILE_POLL_INTERVAL_SECONDS,
        status_poll_limit=MAX_STATUS_POLLS,
        status_poll_interval_seconds=STATUS_POLL_INTERVAL_SECONDS,
        qc_outcome_execution_authorized=True,
        status_only_access_authorized=True,
        result_read_authorized=False,
        log_access_authorized=False,
        deployment_orders_trading_authorized=False,
        owner_signature_authority_id=(
            owner_signature.authority_id
            if type(owner_signature) is OwnerSignatureAuthority else None
        ),
        owner_signature_authority_sha256=(
            owner_signature.authority_sha256
            if type(owner_signature) is OwnerSignatureAuthority else None
        ),
        owner_signature_public_key_blob_sha256=(
            owner_signature.public_key_blob_sha256
            if type(owner_signature) is OwnerSignatureAuthority else None
        ),
        owner_signature_sha256=(
            owner_signature.signature_sha256
            if type(owner_signature) is OwnerSignatureAuthority else None
        ),
        owner_signature_purpose=(
            owner_signature.purpose
            if type(owner_signature) is OwnerSignatureAuthority else None
        ),
        owner_signed_payload_sha256=(
            owner_signature.authority_payload_sha256
            if type(owner_signature) is OwnerSignatureAuthority else None
        ),
        _receipt_bytes=bytes(receipt_bytes),
        _owner_signature=owner_signature,
    )


def require_formal_qc_execution_authority(
    *, value: FormalQcExecutionAuthority, candidate: FormalRunCandidate,
    reviewed_authority: ReviewedFormalRunAuthority,
    projection: FormalQcRuntimeProjection, upload_bundle: FormalQcUploadBundle,
    organization_id: str,
) -> FormalQcExecutionAuthority:
    if type(value) is not FormalQcExecutionAuthority:
        raise FormalQcSubmissionError("execution authority type changed")
    rebuilt = load_formal_qc_execution_authority(
        candidate=candidate, reviewed_authority=reviewed_authority,
        projection=projection, upload_bundle=upload_bundle,
        host_code_closure=value.host_code_closure, transport=value.transport,
        organization_id=organization_id, receipt_bytes=value._receipt_bytes,
        owner_signature=value._owner_signature,
    )
    if any(
        getattr(value, field.name) != getattr(rebuilt, field.name)
        for field in dataclasses.fields(FormalQcExecutionAuthority)
    ):
        raise FormalQcSubmissionError("execution authority changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcSubmissionPlan:
    plan_id: str
    plan_sha256: str
    organization_id: str
    candidate_id: str
    candidate_sha256: str
    authority_id: str
    execution_authority: FormalQcExecutionAuthority
    projection_id: str
    projection_sha256: str
    upload_bundle: FormalQcUploadBundle
    project_name: str
    backtest_name: str
    source_manifest: tuple[tuple[str, str, int], ...]
    maximum_backtest_submissions: int
    compile_poll_limit: int
    compile_poll_interval_seconds: int
    status_poll_limit: int
    status_poll_interval_seconds: int
    include_statistics: bool
    result_read_authorized: bool
    orders_authorized: bool
    _canonical_document: bytes = dataclasses.field(repr=False)


def build_formal_qc_submission_plan(
    *, candidate: FormalRunCandidate, authority: ReviewedFormalRunAuthority,
    execution_authority: FormalQcExecutionAuthority,
    projection: FormalQcRuntimeProjection, upload_bundle: FormalQcUploadBundle,
    organization_id: str,
) -> FormalQcSubmissionPlan:
    require_formal_qc_execution_authority(
        value=execution_authority, candidate=candidate,
        reviewed_authority=authority, projection=projection,
        upload_bundle=upload_bundle, organization_id=organization_id,
    )
    source_manifest = tuple(
        (item.project_path, item.content_sha256, item.byte_count)
        for item in projection.source_files
    )
    seed = {
        "schema": SUBMISSION_PLAN_SCHEMA,
        "plan_id": None,
        "plan_sha256": None,
        "organization_id": organization_id,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "authority_id": authority.authority_id,
        "execution_authority_id": execution_authority.authority_id,
        "execution_authority_sha256": execution_authority.authority_sha256,
        "owner_signature_authority_id": execution_authority.owner_signature_authority_id,
        "owner_signature_authority_sha256": execution_authority.owner_signature_authority_sha256,
        "owner_signature_public_key_blob_sha256": execution_authority.owner_signature_public_key_blob_sha256,
        "owner_signature_sha256": execution_authority.owner_signature_sha256,
        "owner_signature_purpose": execution_authority.owner_signature_purpose,
        "owner_signed_payload_sha256": execution_authority.owner_signed_payload_sha256,
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "upload_bundle_id": upload_bundle.bundle_id,
        "upload_bundle_sha256": upload_bundle.bundle_sha256,
        "project_name": projection.project_name,
        "backtest_name": projection.backtest_name,
        "source_manifest": [
            {"path": path, "sha256": digest, "byte_count": count}
            for path, digest, count in source_manifest
        ],
        "maximum_backtest_submissions": 1,
        "compile_poll_limit": MAX_COMPILE_POLLS,
        "compile_poll_interval_seconds": COMPILE_POLL_INTERVAL_SECONDS,
        "status_poll_limit": MAX_STATUS_POLLS,
        "status_poll_interval_seconds": STATUS_POLL_INTERVAL_SECONDS,
        "include_statistics": False,
        "result_read_authorized": False,
        "orders_authorized": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["plan_sha256"] = digest
    seed["plan_id"] = "arv2-formal-qc-plan-" + digest[:24]
    return FormalQcSubmissionPlan(
        plan_id=str(seed["plan_id"]), plan_sha256=digest,
        organization_id=organization_id, candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256, authority_id=authority.authority_id,
        execution_authority=execution_authority,
        projection_id=projection.projection_id, projection_sha256=projection.projection_sha256,
        upload_bundle=upload_bundle, project_name=projection.project_name,
        backtest_name=projection.backtest_name, source_manifest=source_manifest,
        maximum_backtest_submissions=1, compile_poll_limit=MAX_COMPILE_POLLS,
        compile_poll_interval_seconds=COMPILE_POLL_INTERVAL_SECONDS,
        status_poll_limit=MAX_STATUS_POLLS,
        status_poll_interval_seconds=STATUS_POLL_INTERVAL_SECONDS,
        include_statistics=False, result_read_authorized=False,
        orders_authorized=False, _canonical_document=_canonical(seed),
    )


def require_formal_qc_submission_plan(
    *, value: FormalQcSubmissionPlan, candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority, projection: FormalQcRuntimeProjection,
) -> FormalQcSubmissionPlan:
    if type(value) is not FormalQcSubmissionPlan:
        raise FormalQcSubmissionError("submission plan type changed")
    rebuilt = build_formal_qc_submission_plan(
        candidate=candidate, authority=authority,
        execution_authority=value.execution_authority,
        projection=projection, upload_bundle=value.upload_bundle,
        organization_id=value.organization_id,
    )
    if any(
        getattr(value, field.name) != getattr(rebuilt, field.name)
        for field in dataclasses.fields(FormalQcSubmissionPlan)
    ):
        raise FormalQcSubmissionError("submission plan changed")
    return value


def _require_streamed_upload_projection_capacity(
    bridge: StreamedFormalRuntimeBridge,
) -> None:
    """Reauthenticate the payload-free upload/resource projection."""

    bridge = _require_streamed_runtime_bridge(bridge)
    projection = bridge.runtime_projection
    require_formal_qc_runtime_projection(projection)
    manifest = _json_object(bridge.input_manifest_payload, "streamed input manifest")
    _require_upstream_materialization_capacity(manifest)
    capacity = manifest.get("capacity_review")
    limits = capacity.get("limits") if type(capacity) is dict else None
    descriptors = bridge.upload_descriptors
    if (
        projection is not bridge.runtime_projection
        or projection.input_manifest is not bridge.input_manifest
        or manifest.get("cloud_evaluator")
        != projection.evaluator_source_closure.to_record()
        or type(descriptors) is not tuple
        or not descriptors
        or descriptors[-1].role != "input_manifest"
        or descriptors[-1].content_sha256
        != bridge.input_manifest.content_sha256
        or len({item.object_store_key for item in descriptors}) != len(descriptors)
        or type(limits) is not dict
        or type(limits.get("max_object_store_total_input_byte_count")) is not int
        or bridge.upload_total_byte_count
        > limits["max_object_store_total_input_byte_count"]
        or type(limits.get("max_single_object_byte_count")) is not int
        or max(item.byte_count for item in descriptors)
        > limits["max_single_object_byte_count"]
        or type(limits.get("max_project_file_count")) is not int
        or len(projection.source_files) > limits["max_project_file_count"]
        or type(limits.get("max_project_source_character_count")) is not int
        or sum(item.character_count for item in projection.source_files)
        > limits["max_project_source_character_count"]
    ):
        raise FormalQcSubmissionError(
            "streamed input/evaluator/project/Object Store capacity binding changed"
        )


@dataclasses.dataclass(frozen=True, slots=True)
class StreamedFormalQcExecutionAuthority:
    authority_id: str
    authority_sha256: str
    candidate_id: str
    candidate_sha256: str
    runtime_bridge_id: str
    runtime_bridge_sha256: str
    economic_execution_binding_id: str
    economic_execution_binding_sha256: str
    economic_execution_definition_id: str
    economic_execution_definition_sha256: str
    formal_report_contract_id: str
    formal_report_contract_sha256: str
    formal_report_contract_artifact_sha256: str
    formal_report_contract_economic_execution_definition_sha256: str
    formal_report_contract_secondary_hypothesis_registry_sha256: str
    formal_report_contract_deflated_sharpe_trial_registry_sha256: str
    formal_report_contract_stock_bootstrap_seed_sha256: str
    formal_report_contract_report_family_count: int
    formal_report_contract_secondary_hypothesis_count: int
    formal_report_contract_strategy_trial_count: int
    projection_id: str
    projection_sha256: str
    upload_projection_sha256: str
    upload_entry_count: int
    upload_total_byte_count: int
    organization_id_sha256: str
    project_name: str
    backtest_name: str
    host_code_closure: FormalQcHostClosureBinding
    transport: FormalQcTransportBinding
    actions: tuple[str, ...]
    maximum_backtest_submissions: int
    compile_poll_limit: int
    compile_poll_interval_seconds: int
    status_poll_limit: int
    status_poll_interval_seconds: int
    sequential_reopen_rehash_upload_required: bool
    qc_outcome_execution_authorized: bool
    status_only_access_authorized: bool
    result_read_authorized: bool
    log_access_authorized: bool
    deployment_orders_trading_authorized: bool
    owner_signature_authority_id: str | None
    owner_signature_authority_sha256: str | None
    owner_signature_public_key_blob_sha256: str | None
    owner_signature_sha256: str | None
    owner_signature_purpose: str | None
    owner_signed_payload_sha256: str | None
    _receipt_bytes: bytes = dataclasses.field(repr=False)
    _owner_signature: OwnerSignatureAuthority | None = dataclasses.field(repr=False)


def _streamed_execution_document(
    *,
    bridge: StreamedFormalRuntimeBridge,
    host_code_closure: FormalQcHostClosureBinding,
    transport: FormalQcTransportBinding,
    organization_id: str,
) -> dict[str, object]:
    candidate = bridge.formal_run_candidate
    projection = bridge.runtime_projection
    seed = {
        "schema": STREAMED_EXECUTION_AUTHORITY_SCHEMA,
        "status": "requires_exact_owner_external_pin",
        "authority_id": None,
        "authority_sha256": None,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "runtime_bridge_id": bridge.bridge_id,
        "runtime_bridge_sha256": bridge.bridge_sha256,
        "economic_execution_binding_id": bridge.economic_execution.binding_id,
        "economic_execution_binding_sha256": (
            bridge.economic_execution.binding_sha256
        ),
        "economic_execution_definition_id": (
            bridge.economic_execution.definition_id
        ),
        "economic_execution_definition_sha256": (
            bridge.economic_execution.definition_sha256
        ),
        "formal_report_contract_id": bridge.report_contract.contract_id,
        "formal_report_contract_sha256": bridge.report_contract.contract_sha256,
        "formal_report_contract_artifact_sha256": (
            bridge.report_contract.artifact_sha256
        ),
        "formal_report_contract_economic_execution_definition_sha256": (
            bridge.report_contract.economic_execution_definition_sha256
        ),
        "formal_report_contract_secondary_hypothesis_registry_sha256": (
            bridge.report_contract.secondary_hypothesis_registry_sha256
        ),
        "formal_report_contract_deflated_sharpe_trial_registry_sha256": (
            bridge.report_contract.deflated_sharpe_trial_registry_sha256
        ),
        "formal_report_contract_stock_bootstrap_seed_sha256": (
            bridge.report_contract.stock_bootstrap_seed_sha256
        ),
        "formal_report_contract_report_family_count": (
            bridge.report_contract.report_family_count
        ),
        "formal_report_contract_secondary_hypothesis_count": (
            bridge.report_contract.secondary_hypothesis_count
        ),
        "formal_report_contract_strategy_trial_count": (
            bridge.report_contract.strategy_trial_count
        ),
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "project_source_set_sha256": projection.project_source_set_sha256,
        "evaluator_source_closure_sha256": (
            projection.evaluator_source_closure_sha256
        ),
        "upload_projection_sha256": bridge.upload_projection_sha256,
        "upload_entry_count": bridge.upload_entry_count,
        "upload_total_byte_count": bridge.upload_total_byte_count,
        "input_manifest_sha256": bridge.input_manifest.content_sha256,
        "organization_id_sha256": hashlib.sha256(
            organization_id.encode()
        ).hexdigest(),
        "project_name": projection.project_name,
        "backtest_name": projection.backtest_name,
        "host_code_closure": {
            "closure_id": host_code_closure.closure_id,
            "closure_sha256": host_code_closure.closure_sha256,
        },
        "transport": transport.to_record(),
        "actions": list(EXECUTION_ACTIONS),
        "maximum_backtest_submissions": 1,
        "compile_poll_limit": MAX_COMPILE_POLLS,
        "compile_poll_interval_seconds": COMPILE_POLL_INTERVAL_SECONDS,
        "status_poll_limit": MAX_STATUS_POLLS,
        "status_poll_interval_seconds": STATUS_POLL_INTERVAL_SECONDS,
        "capacity_and_evaluator_receipts_bound_by_input_manifest": True,
        "sequential_reopen_rehash_upload_required": True,
        "manifest_published_last": True,
        "full_payload_tuple_materialized": False,
        "qc_outcome_execution_authorized": True,
        "status_only_access_authorized": True,
        "result_read_authorized": False,
        "log_access_authorized": False,
        "deployment_orders_trading_authorized": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["authority_sha256"] = digest
    seed["authority_id"] = "arv2-owner-streamed-outcome-qc-authority-" + digest
    return seed


def render_streamed_formal_qc_execution_authority_candidate(
    *,
    runtime_bridge: StreamedFormalRuntimeBridge,
    host_code_closure: FormalQcHostClosureBinding,
    transport: FormalQcTransportBinding,
    organization_id: str,
) -> bytes:
    bridge = _require_streamed_runtime_bridge(runtime_bridge)
    _require_streamed_upload_projection_capacity(bridge)
    require_formal_qc_host_closure_binding(host_code_closure)
    require_formal_qc_transport_binding(transport, host_code_closure)
    _safe_id(organization_id, "organization_id")
    return _canonical(
        _streamed_execution_document(
            bridge=bridge,
            host_code_closure=host_code_closure,
            transport=transport,
            organization_id=organization_id,
        )
    )


def load_streamed_formal_qc_execution_authority(
    *,
    runtime_bridge: StreamedFormalRuntimeBridge,
    reviewed_authority: ReviewedFormalRunAuthority,
    host_code_closure: FormalQcHostClosureBinding,
    transport: FormalQcTransportBinding,
    organization_id: str,
    receipt_bytes: bytes,
    owner_signature: OwnerSignatureAuthority | None = None,
) -> StreamedFormalQcExecutionAuthority:
    bridge = _require_streamed_runtime_bridge(runtime_bridge)
    candidate = bridge.formal_run_candidate
    require_reviewed_formal_run_authority(candidate, reviewed_authority)
    expected = render_streamed_formal_qc_execution_authority_candidate(
        runtime_bridge=bridge,
        host_code_closure=host_code_closure,
        transport=transport,
        organization_id=organization_id,
    )
    if type(receipt_bytes) is not bytes or receipt_bytes != expected:
        raise FormalQcSubmissionError(
            "streamed execution authority receipt bytes changed"
        )
    _require_non_self_mintable_execution_trust_root(owner_signature, expected)
    raw = _json_object(receipt_bytes, "streamed execution authority receipt")
    if reviewed_authority.owner_outcome_authority_receipt_id != raw["authority_id"]:
        raise FormalQcSubmissionError(
            "owner review pin does not bind this exact streamed execution authority"
        )
    projection = bridge.runtime_projection
    return StreamedFormalQcExecutionAuthority(
        authority_id=str(raw["authority_id"]),
        authority_sha256=str(raw["authority_sha256"]),
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        runtime_bridge_id=bridge.bridge_id,
        runtime_bridge_sha256=bridge.bridge_sha256,
        economic_execution_binding_id=bridge.economic_execution.binding_id,
        economic_execution_binding_sha256=(
            bridge.economic_execution.binding_sha256
        ),
        economic_execution_definition_id=bridge.economic_execution.definition_id,
        economic_execution_definition_sha256=(
            bridge.economic_execution.definition_sha256
        ),
        formal_report_contract_id=bridge.report_contract.contract_id,
        formal_report_contract_sha256=bridge.report_contract.contract_sha256,
        formal_report_contract_artifact_sha256=(
            bridge.report_contract.artifact_sha256
        ),
        formal_report_contract_economic_execution_definition_sha256=(
            bridge.report_contract.economic_execution_definition_sha256
        ),
        formal_report_contract_secondary_hypothesis_registry_sha256=(
            bridge.report_contract.secondary_hypothesis_registry_sha256
        ),
        formal_report_contract_deflated_sharpe_trial_registry_sha256=(
            bridge.report_contract.deflated_sharpe_trial_registry_sha256
        ),
        formal_report_contract_stock_bootstrap_seed_sha256=(
            bridge.report_contract.stock_bootstrap_seed_sha256
        ),
        formal_report_contract_report_family_count=(
            bridge.report_contract.report_family_count
        ),
        formal_report_contract_secondary_hypothesis_count=(
            bridge.report_contract.secondary_hypothesis_count
        ),
        formal_report_contract_strategy_trial_count=(
            bridge.report_contract.strategy_trial_count
        ),
        projection_id=projection.projection_id,
        projection_sha256=projection.projection_sha256,
        upload_projection_sha256=bridge.upload_projection_sha256,
        upload_entry_count=bridge.upload_entry_count,
        upload_total_byte_count=bridge.upload_total_byte_count,
        organization_id_sha256=str(raw["organization_id_sha256"]),
        project_name=projection.project_name,
        backtest_name=projection.backtest_name,
        host_code_closure=host_code_closure,
        transport=transport,
        actions=EXECUTION_ACTIONS,
        maximum_backtest_submissions=1,
        compile_poll_limit=MAX_COMPILE_POLLS,
        compile_poll_interval_seconds=COMPILE_POLL_INTERVAL_SECONDS,
        status_poll_limit=MAX_STATUS_POLLS,
        status_poll_interval_seconds=STATUS_POLL_INTERVAL_SECONDS,
        sequential_reopen_rehash_upload_required=True,
        qc_outcome_execution_authorized=True,
        status_only_access_authorized=True,
        result_read_authorized=False,
        log_access_authorized=False,
        deployment_orders_trading_authorized=False,
        owner_signature_authority_id=(
            owner_signature.authority_id
            if type(owner_signature) is OwnerSignatureAuthority
            else None
        ),
        owner_signature_authority_sha256=(
            owner_signature.authority_sha256
            if type(owner_signature) is OwnerSignatureAuthority
            else None
        ),
        owner_signature_public_key_blob_sha256=(
            owner_signature.public_key_blob_sha256
            if type(owner_signature) is OwnerSignatureAuthority
            else None
        ),
        owner_signature_sha256=(
            owner_signature.signature_sha256
            if type(owner_signature) is OwnerSignatureAuthority
            else None
        ),
        owner_signature_purpose=(
            owner_signature.purpose
            if type(owner_signature) is OwnerSignatureAuthority
            else None
        ),
        owner_signed_payload_sha256=(
            owner_signature.authority_payload_sha256
            if type(owner_signature) is OwnerSignatureAuthority
            else None
        ),
        _receipt_bytes=bytes(receipt_bytes),
        _owner_signature=owner_signature,
    )


def require_streamed_formal_qc_execution_authority(
    *,
    value: StreamedFormalQcExecutionAuthority,
    runtime_bridge: StreamedFormalRuntimeBridge,
    reviewed_authority: ReviewedFormalRunAuthority,
    organization_id: str,
) -> StreamedFormalQcExecutionAuthority:
    if type(value) is not StreamedFormalQcExecutionAuthority:
        raise FormalQcSubmissionError("streamed execution authority type changed")
    rebuilt = load_streamed_formal_qc_execution_authority(
        runtime_bridge=runtime_bridge,
        reviewed_authority=reviewed_authority,
        host_code_closure=value.host_code_closure,
        transport=value.transport,
        organization_id=organization_id,
        receipt_bytes=value._receipt_bytes,
        owner_signature=value._owner_signature,
    )
    if any(
        getattr(value, field.name) != getattr(rebuilt, field.name)
        for field in dataclasses.fields(StreamedFormalQcExecutionAuthority)
    ):
        raise FormalQcSubmissionError("streamed execution authority changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class StreamedFormalQcSubmissionPlan:
    plan_id: str
    plan_sha256: str
    organization_id: str
    candidate_id: str
    candidate_sha256: str
    reviewed_authority_id: str
    reviewed_authority_sha256: str
    execution_authority: StreamedFormalQcExecutionAuthority
    runtime_bridge: StreamedFormalRuntimeBridge
    economic_execution: FormalEconomicExecutionBinding
    report_contract: FormalReportContract
    projection_id: str
    projection_sha256: str
    upload_projection_sha256: str
    upload_entry_count: int
    upload_total_byte_count: int
    project_name: str
    backtest_name: str
    source_manifest: tuple[tuple[str, str, int], ...]
    maximum_backtest_submissions: int
    compile_poll_limit: int
    compile_poll_interval_seconds: int
    status_poll_limit: int
    status_poll_interval_seconds: int
    sequential_reopen_rehash_upload_required: bool
    manifest_published_last: bool
    full_payload_tuple_materialized: bool
    include_statistics: bool
    result_read_authorized: bool
    orders_authorized: bool
    _canonical_document: bytes = dataclasses.field(repr=False)


def build_streamed_formal_qc_submission_plan(
    *,
    runtime_bridge: StreamedFormalRuntimeBridge,
    authority: ReviewedFormalRunAuthority,
    execution_authority: StreamedFormalQcExecutionAuthority,
    organization_id: str,
) -> StreamedFormalQcSubmissionPlan:
    bridge = _require_streamed_runtime_bridge(runtime_bridge)
    candidate = bridge.formal_run_candidate
    projection = bridge.runtime_projection
    require_streamed_formal_qc_execution_authority(
        value=execution_authority,
        runtime_bridge=bridge,
        reviewed_authority=authority,
        organization_id=organization_id,
    )
    source_manifest = tuple(
        (item.project_path, item.content_sha256, item.byte_count)
        for item in projection.source_files
    )
    seed = {
        "schema": STREAMED_SUBMISSION_PLAN_SCHEMA,
        "plan_id": None,
        "plan_sha256": None,
        "organization_id": organization_id,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "reviewed_authority_id": authority.authority_id,
        "reviewed_authority_sha256": authority.authority_sha256,
        "execution_authority_id": execution_authority.authority_id,
        "execution_authority_sha256": execution_authority.authority_sha256,
        "owner_signature_authority_id": (
            execution_authority.owner_signature_authority_id
        ),
        "owner_signature_authority_sha256": (
            execution_authority.owner_signature_authority_sha256
        ),
        "owner_signature_public_key_blob_sha256": (
            execution_authority.owner_signature_public_key_blob_sha256
        ),
        "owner_signature_sha256": execution_authority.owner_signature_sha256,
        "owner_signature_purpose": execution_authority.owner_signature_purpose,
        "owner_signed_payload_sha256": (
            execution_authority.owner_signed_payload_sha256
        ),
        "runtime_bridge_id": bridge.bridge_id,
        "runtime_bridge_sha256": bridge.bridge_sha256,
        "economic_execution_binding_id": bridge.economic_execution.binding_id,
        "economic_execution_binding_sha256": (
            bridge.economic_execution.binding_sha256
        ),
        "economic_execution_definition_id": (
            bridge.economic_execution.definition_id
        ),
        "economic_execution_definition_sha256": (
            bridge.economic_execution.definition_sha256
        ),
        "formal_report_contract_id": bridge.report_contract.contract_id,
        "formal_report_contract_sha256": bridge.report_contract.contract_sha256,
        "formal_report_contract_artifact_sha256": (
            bridge.report_contract.artifact_sha256
        ),
        "formal_report_contract_economic_execution_definition_sha256": (
            bridge.report_contract.economic_execution_definition_sha256
        ),
        "formal_report_contract_secondary_hypothesis_registry_sha256": (
            bridge.report_contract.secondary_hypothesis_registry_sha256
        ),
        "formal_report_contract_deflated_sharpe_trial_registry_sha256": (
            bridge.report_contract.deflated_sharpe_trial_registry_sha256
        ),
        "formal_report_contract_stock_bootstrap_seed_sha256": (
            bridge.report_contract.stock_bootstrap_seed_sha256
        ),
        "formal_report_contract_report_family_count": (
            bridge.report_contract.report_family_count
        ),
        "formal_report_contract_secondary_hypothesis_count": (
            bridge.report_contract.secondary_hypothesis_count
        ),
        "formal_report_contract_strategy_trial_count": (
            bridge.report_contract.strategy_trial_count
        ),
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "upload_projection_sha256": bridge.upload_projection_sha256,
        "upload_entry_count": bridge.upload_entry_count,
        "upload_total_byte_count": bridge.upload_total_byte_count,
        "project_name": projection.project_name,
        "backtest_name": projection.backtest_name,
        "source_manifest": [
            {"path": path, "sha256": digest, "byte_count": count}
            for path, digest, count in source_manifest
        ],
        "maximum_backtest_submissions": 1,
        "compile_poll_limit": MAX_COMPILE_POLLS,
        "compile_poll_interval_seconds": COMPILE_POLL_INTERVAL_SECONDS,
        "status_poll_limit": MAX_STATUS_POLLS,
        "status_poll_interval_seconds": STATUS_POLL_INTERVAL_SECONDS,
        "sequential_reopen_rehash_upload_required": True,
        "manifest_published_last": True,
        "full_payload_tuple_materialized": False,
        "include_statistics": False,
        "result_read_authorized": False,
        "orders_authorized": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["plan_sha256"] = digest
    seed["plan_id"] = "arv2-streamed-formal-qc-plan-" + digest[:24]
    return StreamedFormalQcSubmissionPlan(
        plan_id=str(seed["plan_id"]),
        plan_sha256=digest,
        organization_id=organization_id,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        reviewed_authority_id=authority.authority_id,
        reviewed_authority_sha256=authority.authority_sha256,
        execution_authority=execution_authority,
        runtime_bridge=bridge,
        economic_execution=bridge.economic_execution,
        report_contract=bridge.report_contract,
        projection_id=projection.projection_id,
        projection_sha256=projection.projection_sha256,
        upload_projection_sha256=bridge.upload_projection_sha256,
        upload_entry_count=bridge.upload_entry_count,
        upload_total_byte_count=bridge.upload_total_byte_count,
        project_name=projection.project_name,
        backtest_name=projection.backtest_name,
        source_manifest=source_manifest,
        maximum_backtest_submissions=1,
        compile_poll_limit=MAX_COMPILE_POLLS,
        compile_poll_interval_seconds=COMPILE_POLL_INTERVAL_SECONDS,
        status_poll_limit=MAX_STATUS_POLLS,
        status_poll_interval_seconds=STATUS_POLL_INTERVAL_SECONDS,
        sequential_reopen_rehash_upload_required=True,
        manifest_published_last=True,
        full_payload_tuple_materialized=False,
        include_statistics=False,
        result_read_authorized=False,
        orders_authorized=False,
        _canonical_document=_canonical(seed),
    )


def require_streamed_formal_qc_submission_plan(
    *,
    value: StreamedFormalQcSubmissionPlan,
    authority: ReviewedFormalRunAuthority,
) -> StreamedFormalQcSubmissionPlan:
    if type(value) is not StreamedFormalQcSubmissionPlan:
        raise FormalQcSubmissionError("streamed submission plan type changed")
    rebuilt = build_streamed_formal_qc_submission_plan(
        runtime_bridge=value.runtime_bridge,
        authority=authority,
        execution_authority=value.execution_authority,
        organization_id=value.organization_id,
    )
    economic_execution = _require_streamed_economic_execution(
        value.economic_execution, value.runtime_bridge
    )
    report_contract = _require_streamed_report_contract(
        value.report_contract, value.runtime_bridge
    )
    if (
        value.economic_execution is not economic_execution
        or value.economic_execution is not value.runtime_bridge.economic_execution
        or rebuilt.economic_execution is not value.economic_execution
        or value.report_contract is not report_contract
        or value.report_contract is not value.runtime_bridge.report_contract
        or rebuilt.report_contract is not value.report_contract
        or any(
            getattr(value, field.name) != getattr(rebuilt, field.name)
            for field in dataclasses.fields(StreamedFormalQcSubmissionPlan)
        )
    ):
        raise FormalQcSubmissionError("streamed submission plan changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class StreamedFormalSubmissionAdapterBridge:
    bridge_id: str
    bridge_sha256: str
    schema: str
    runtime_bridge: StreamedFormalRuntimeBridge
    formal_run_candidate: FormalRunCandidate
    reviewed_authority: ReviewedFormalRunAuthority
    execution_authority: StreamedFormalQcExecutionAuthority
    authenticated_power_floor: AuthenticatedPowerFloorBinding
    economic_execution: FormalEconomicExecutionBinding
    report_contract: FormalReportContract
    plan: StreamedFormalQcSubmissionPlan
    sequential_upload_primitive_present: bool
    full_payload_tuple_materialized: bool
    external_action_performed: bool
    _canonical_document: bytes = dataclasses.field(repr=False)


def build_streamed_formal_submission_adapter_bridge(
    *,
    runtime_bridge: StreamedFormalRuntimeBridge,
    reviewed_authority: ReviewedFormalRunAuthority,
    execution_authority: StreamedFormalQcExecutionAuthority,
    authenticated_power_floor: AuthenticatedPowerFloorBinding,
    organization_id: str,
) -> StreamedFormalSubmissionAdapterBridge:
    bridge = _require_streamed_runtime_bridge(runtime_bridge)
    authenticated_power = _require_streamed_authenticated_power_floor(
        authenticated_power_floor, bridge
    )
    economic_execution = _require_streamed_economic_execution(
        bridge.economic_execution, bridge
    )
    report_contract = _require_streamed_report_contract(
        bridge.report_contract, bridge
    )
    plan = build_streamed_formal_qc_submission_plan(
        runtime_bridge=bridge,
        authority=reviewed_authority,
        execution_authority=execution_authority,
        organization_id=organization_id,
    )
    record = {
        "schema": STREAMED_SUBMISSION_BRIDGE_SCHEMA,
        "runtime_bridge_id": bridge.bridge_id,
        "runtime_bridge_sha256": bridge.bridge_sha256,
        "formal_run_candidate_id": bridge.formal_run_candidate.candidate_id,
        "formal_run_candidate_sha256": bridge.formal_run_candidate.candidate_sha256,
        "reviewed_authority_id": reviewed_authority.authority_id,
        "reviewed_authority_sha256": reviewed_authority.authority_sha256,
        "execution_authority_id": execution_authority.authority_id,
        "execution_authority_sha256": execution_authority.authority_sha256,
        "authenticated_power_floor_id": authenticated_power.binding_id,
        "authenticated_power_floor_sha256": authenticated_power.binding_sha256,
        "economic_execution_binding_id": economic_execution.binding_id,
        "economic_execution_binding_sha256": economic_execution.binding_sha256,
        "economic_execution_definition_id": economic_execution.definition_id,
        "economic_execution_definition_sha256": (
            economic_execution.definition_sha256
        ),
        "formal_report_contract_id": report_contract.contract_id,
        "formal_report_contract_sha256": report_contract.contract_sha256,
        "formal_report_contract_artifact_sha256": report_contract.artifact_sha256,
        "formal_report_contract_economic_execution_definition_sha256": (
            report_contract.economic_execution_definition_sha256
        ),
        "formal_report_contract_secondary_hypothesis_registry_sha256": (
            report_contract.secondary_hypothesis_registry_sha256
        ),
        "formal_report_contract_deflated_sharpe_trial_registry_sha256": (
            report_contract.deflated_sharpe_trial_registry_sha256
        ),
        "formal_report_contract_stock_bootstrap_seed_sha256": (
            report_contract.stock_bootstrap_seed_sha256
        ),
        "formal_report_contract_report_family_count": report_contract.report_family_count,
        "formal_report_contract_secondary_hypothesis_count": (
            report_contract.secondary_hypothesis_count
        ),
        "formal_report_contract_strategy_trial_count": (
            report_contract.strategy_trial_count
        ),
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "upload_projection_sha256": bridge.upload_projection_sha256,
        "upload_entry_count": bridge.upload_entry_count,
        "sequential_upload_primitive_present": True,
        "manifest_published_last": True,
        "full_payload_tuple_materialized": False,
        "external_action_performed": False,
    }
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    value = StreamedFormalSubmissionAdapterBridge(
        bridge_id=f"arv2-streamed-submission-adapter-{digest[:24]}",
        bridge_sha256=digest,
        schema=STREAMED_SUBMISSION_BRIDGE_SCHEMA,
        runtime_bridge=bridge,
        formal_run_candidate=bridge.formal_run_candidate,
        reviewed_authority=reviewed_authority,
        execution_authority=execution_authority,
        authenticated_power_floor=authenticated_power,
        economic_execution=economic_execution,
        report_contract=report_contract,
        plan=plan,
        sequential_upload_primitive_present=True,
        full_payload_tuple_materialized=False,
        external_action_performed=False,
        _canonical_document=_canonical(record),
    )
    return require_streamed_formal_submission_adapter_bridge(value)


def require_streamed_formal_submission_adapter_bridge(
    value: StreamedFormalSubmissionAdapterBridge,
) -> StreamedFormalSubmissionAdapterBridge:
    if type(value) is not StreamedFormalSubmissionAdapterBridge:
        raise FormalQcSubmissionError(
            "streamed submission adapter bridge type changed"
        )
    rebuilt = build_streamed_formal_qc_submission_plan(
        runtime_bridge=value.runtime_bridge,
        authority=value.reviewed_authority,
        execution_authority=value.execution_authority,
        organization_id=value.plan.organization_id,
    )
    authenticated_power = _require_streamed_authenticated_power_floor(
        value.authenticated_power_floor, value.runtime_bridge
    )
    economic_execution = _require_streamed_economic_execution(
        value.economic_execution, value.runtime_bridge
    )
    report_contract = _require_streamed_report_contract(
        value.report_contract, value.runtime_bridge
    )
    record = {
        "schema": STREAMED_SUBMISSION_BRIDGE_SCHEMA,
        "runtime_bridge_id": value.runtime_bridge.bridge_id,
        "runtime_bridge_sha256": value.runtime_bridge.bridge_sha256,
        "formal_run_candidate_id": value.formal_run_candidate.candidate_id,
        "formal_run_candidate_sha256": value.formal_run_candidate.candidate_sha256,
        "reviewed_authority_id": value.reviewed_authority.authority_id,
        "reviewed_authority_sha256": value.reviewed_authority.authority_sha256,
        "execution_authority_id": value.execution_authority.authority_id,
        "execution_authority_sha256": value.execution_authority.authority_sha256,
        "authenticated_power_floor_id": authenticated_power.binding_id,
        "authenticated_power_floor_sha256": authenticated_power.binding_sha256,
        "economic_execution_binding_id": economic_execution.binding_id,
        "economic_execution_binding_sha256": economic_execution.binding_sha256,
        "economic_execution_definition_id": economic_execution.definition_id,
        "economic_execution_definition_sha256": (
            economic_execution.definition_sha256
        ),
        "formal_report_contract_id": report_contract.contract_id,
        "formal_report_contract_sha256": report_contract.contract_sha256,
        "formal_report_contract_artifact_sha256": report_contract.artifact_sha256,
        "formal_report_contract_economic_execution_definition_sha256": (
            report_contract.economic_execution_definition_sha256
        ),
        "formal_report_contract_secondary_hypothesis_registry_sha256": (
            report_contract.secondary_hypothesis_registry_sha256
        ),
        "formal_report_contract_deflated_sharpe_trial_registry_sha256": (
            report_contract.deflated_sharpe_trial_registry_sha256
        ),
        "formal_report_contract_stock_bootstrap_seed_sha256": (
            report_contract.stock_bootstrap_seed_sha256
        ),
        "formal_report_contract_report_family_count": report_contract.report_family_count,
        "formal_report_contract_secondary_hypothesis_count": (
            report_contract.secondary_hypothesis_count
        ),
        "formal_report_contract_strategy_trial_count": (
            report_contract.strategy_trial_count
        ),
        "plan_id": value.plan.plan_id,
        "plan_sha256": value.plan.plan_sha256,
        "upload_projection_sha256": value.runtime_bridge.upload_projection_sha256,
        "upload_entry_count": value.runtime_bridge.upload_entry_count,
        "sequential_upload_primitive_present": True,
        "manifest_published_last": True,
        "full_payload_tuple_materialized": False,
        "external_action_performed": False,
    }
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    if (
        rebuilt != value.plan
        or value.schema != STREAMED_SUBMISSION_BRIDGE_SCHEMA
        or value.formal_run_candidate is not value.runtime_bridge.formal_run_candidate
        or value.plan.runtime_bridge is not value.runtime_bridge
        or value.plan.execution_authority is not value.execution_authority
        or value.plan.economic_execution is not economic_execution
        or value.authenticated_power_floor is not authenticated_power
        or value.economic_execution is not economic_execution
        or value.economic_execution is not value.runtime_bridge.economic_execution
        or value.report_contract is not report_contract
        or value.report_contract is not value.runtime_bridge.report_contract
        or value.plan.report_contract is not report_contract
        or value.bridge_id != f"arv2-streamed-submission-adapter-{digest[:24]}"
        or value.bridge_sha256 != digest
        or value._canonical_document != _canonical(record)
        or value.sequential_upload_primitive_present is not True
        or value.full_payload_tuple_materialized is not False
        or value.external_action_performed is not False
    ):
        raise FormalQcSubmissionError("streamed submission adapter bridge changed")
    return value


def _preflight_streamed_upload(
    bridge: StreamedFormalRuntimeBridge,
) -> None:
    expected = bridge.upload_descriptors
    count = 0
    total = 0
    for entry, descriptor in zip(
        _iter_streamed_upload_entries(bridge), expected, strict=True
    ):
        if entry.to_record() != descriptor.to_record():
            raise FormalQcSubmissionError(
                "streamed upload preflight descriptor changed"
            )
        count += 1
        total += entry.byte_count
        del entry
    if count != bridge.upload_entry_count or total != bridge.upload_total_byte_count:
        raise FormalQcSubmissionError("streamed upload preflight census changed")


def _exact_dict(value: object, allowed: frozenset[str], name: str) -> dict[str, object]:
    if type(value) is not dict or not set(value).issubset(allowed):
        raise FormalQcSubmissionError(f"{name} envelope changed")
    return value


def _success(value: object, allowed: frozenset[str], name: str) -> dict[str, object]:
    result = _exact_dict(value, allowed, name)
    if result.get("success") is not True:
        raise FormalQcSubmissionError(f"{name} was not successful")
    return result


def _project_record(value: object, *, name: str, organization_id: str) -> dict[str, object]:
    allowed = frozenset(
        {"projectId", "organizationId", "name", "language", "owner", "codeRunning", "collaborators", "libraries", "leanVersionId"}
    )
    record = _exact_dict(value, allowed, "project")
    if (
        type(record.get("projectId")) is not int
        or record["projectId"] <= 0
        or record.get("organizationId") != organization_id
        or record.get("name") != name
        or record.get("language") != "Py"
        or record.get("owner") is not True
        or record.get("codeRunning") is not False
        or type(record.get("collaborators")) is not list
        or len(record["collaborators"]) > 1
        or any(type(item) is not dict or item.get("owner") is not True for item in record["collaborators"])
    ):
        raise FormalQcSubmissionError("project is not the exact private owner project")
    return record


def _created_project(value: object, *, name: str, organization_id: str) -> dict[str, object]:
    raw = _success(value, frozenset({"success", "errors", "messages", "projects"}), "projects/create")
    projects = raw.get("projects")
    if type(projects) is not list or len(projects) != 1:
        raise FormalQcSubmissionError("projects/create did not return one project")
    record = projects[0]
    if (
        type(record) is not dict
        or type(record.get("projectId")) is not int
        or record["projectId"] <= 0
        or record.get("name") != name
        or record.get("language") != "Py"
        or ("organizationId" in record and record["organizationId"] != organization_id)
    ):
        raise FormalQcSubmissionError("projects/create identity changed")
    return record


def _read_project_inventory(value: object) -> list[dict[str, object]]:
    raw = _success(value, frozenset({"success", "errors", "messages", "projects"}), "projects/read")
    projects = raw.get("projects")
    if type(projects) is not list:
        raise FormalQcSubmissionError("projects/read omitted its project list")
    return projects


def _read_files(value: object) -> dict[str, str]:
    raw = _success(value, frozenset({"success", "errors", "messages", "files"}), "files/read")
    items = raw.get("files")
    if type(items) is not list:
        raise FormalQcSubmissionError("files/read omitted its file list")
    result: dict[str, str] = {}
    for item in items:
        if type(item) is not dict or not set(item).issubset({"name", "content"}):
            raise FormalQcSubmissionError("files/read item changed")
        name, content = item.get("name"), item.get("content")
        if type(name) is not str or type(content) is not str or name in result:
            raise FormalQcSubmissionError("files/read item identity changed")
        result[name] = content
    return result


def _object_metadata_matches(value: object, entry: FormalQcUploadEntry) -> None:
    raw = _success(value, frozenset({"success", "errors", "messages", "metadata"}), "object/properties")
    metadata = raw.get("metadata")
    if type(metadata) is not dict or not set(metadata).issubset(
        {"key", "modified", "created", "size", "md5", "mime", "preview"}
    ):
        raise FormalQcSubmissionError("Object Store metadata envelope changed")
    # Never access preview: it may contain licensed input bytes.
    if (
        metadata.get("key") != entry.object_store_key
        or metadata.get("size") != entry.byte_count
        or type(metadata.get("md5")) is not str
        or metadata["md5"].casefold() != entry.content_md5
    ):
        raise FormalQcSubmissionError("Object Store metadata does not authenticate uploaded bytes")


def _compile_id(value: object) -> str:
    raw = _success(value, frozenset({"success", "errors", "messages", "compileId"}), "compile/create")
    return _safe_id(raw.get("compileId"), "compile_id")


def _compile_state(value: object, compile_id: str) -> str:
    raw = _success(value, frozenset({"success", "errors", "messages", "compileId", "state"}), "compile/read")
    if raw.get("compileId") != compile_id or raw.get("state") not in COMPILE_PENDING_STATES | COMPILE_TERMINAL_STATES:
        raise FormalQcSubmissionError("compile/read state envelope changed")
    return str(raw["state"])


def _status_keys_without_values(
    value: object,
    *,
    allowed: frozenset[str],
    discard_only: frozenset[str],
    name: str,
) -> None:
    """Validate one status object by key only.

    In particular, do not obtain a reference to a discard-only value.  This is
    the response-envelope successor required by the locked B5C smoke: the API
    is allowed to serialize its documented summary fields, while this adapter
    consumes only the run identity and state.
    """

    if type(value) is not dict:
        raise FormalQcSubmissionError(f"{name} envelope changed")
    for key in value.keys():
        if type(key) is not str:
            raise FormalQcSubmissionError(f"{name} has a non-string key")
        if key not in allowed and key not in discard_only:
            raise FormalQcSubmissionError(f"{name} contains an unknown key")


@dataclasses.dataclass(frozen=True, slots=True)
class StatisticsFreeBacktestStatus:
    backtest_id: str
    backtest_name: str
    project_id: int
    status: str


def parse_statistics_free_backtest_list(
    value: object, *, expected_project_id: int,
    expected_backtest_id: str, expected_backtest_name: str,
) -> StatisticsFreeBacktestStatus:
    _positive_int(expected_project_id, "expected project id")
    _safe_id(expected_backtest_id, "expected backtest id")
    _safe_id(expected_backtest_name, "expected backtest name")
    _status_keys_without_values(
        value,
        allowed=_TOP_STATUS_KEYS,
        discard_only=frozenset(),
        name="backtests/list",
    )
    # Only allowlisted non-result fields are indexed from this point onward.
    raw = value
    if raw.get("success") is not True:
        raise FormalQcSubmissionError("backtests/list was not successful")
    for key in ("errors", "messages"):
        if key in raw and (
            type(raw[key]) is not list
            or any(type(item) is not str for item in raw[key])
        ):
            raise FormalQcSubmissionError("backtests/list message envelope changed")
    items = raw.get("backtests")
    if type(items) is not list:
        raise FormalQcSubmissionError("backtests/list omitted its list")
    if "count" in raw and (type(raw["count"]) is not int or raw["count"] != len(items)):
        raise FormalQcSubmissionError("backtests/list count changed")
    matches = []
    for item in items:
        _status_keys_without_values(
            item,
            allowed=_BACKTEST_STATUS_KEYS,
            discard_only=_DISCARDED_BACKTEST_SUMMARY_KEYS,
            name="backtests/list item",
        )
        row = item
        for key in ("backtestId", "name", "status"):
            if key in row and type(row[key]) is not str:
                raise FormalQcSubmissionError(
                    f"backtests/list {key} shape changed"
                )
        if "projectId" in row and type(row["projectId"]) is not int:
            raise FormalQcSubmissionError(
                "backtests/list projectId shape changed"
            )
        for key in ("created", "completed", "note"):
            if key in row and row[key] is not None and type(row[key]) is not str:
                raise FormalQcSubmissionError(
                    "backtests/list ignored field shape changed"
                )
        if (
            "progress" in row
            and row["progress"] is not None
            and type(row["progress"]) not in (str, int)
        ):
            raise FormalQcSubmissionError("backtests/list progress shape changed")
        if row.get("backtestId") == expected_backtest_id:
            matches.append(row)
    if len(matches) != 1:
        raise FormalQcSubmissionError("backtests/list did not contain one exact run")
    row = matches[0]
    if (
        row.get("name") != expected_backtest_name
        or (
            "projectId" in row
            and row.get("projectId") != expected_project_id
        )
        or row.get("status") not in BACKTEST_PENDING_STATUSES | BACKTEST_TERMINAL_STATUSES
    ):
        raise FormalQcSubmissionError("backtests/list run identity/status changed")
    return StatisticsFreeBacktestStatus(
        backtest_id=expected_backtest_id, backtest_name=expected_backtest_name,
        project_id=expected_project_id, status=row["status"],
    )


def _created_backtest(value: object, *, project_id: int, name: str) -> tuple[str, str]:
    raw = _success(value, frozenset({"success", "errors", "messages", "backtest"}), "backtests/create")
    row = raw.get("backtest")
    if type(row) is not dict or not set(row).issubset(_BACKTEST_STATUS_KEYS):
        raise FormalQcSubmissionError("backtests/create envelope changed")
    backtest_id = _safe_id(row.get("backtestId"), "backtest_id")
    if row.get("name") != name or row.get("projectId") != project_id or row.get("status") not in BACKTEST_PENDING_STATUSES:
        raise FormalQcSubmissionError("backtests/create identity changed")
    return backtest_id, str(row["status"])


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class FormalQcLaunchReceipt:
    receipt_id: str
    receipt_sha256: str
    permit_id: str
    permit_sha256: str
    plan_id: str
    plan_sha256: str
    projection_id: str
    projection_sha256: str
    economic_execution_binding_id: str | None
    economic_execution_binding_sha256: str | None
    economic_execution_definition_id: str | None
    economic_execution_definition_sha256: str | None
    host_closure_sha256: str
    project_id: int
    compile_id: str
    compile_state: str
    backtest_id: str
    backtest_name: str
    initial_status: str
    input_object_count: int
    source_file_count: int
    backtest_submission_count: int
    include_statistics: bool
    result_read_authorized: bool
    orders_authorized: bool


def _identified_receipt(prefix: str, schema: str, record: dict[str, object]) -> tuple[str, str]:
    digest = hashlib.sha256(_canonical({"schema": schema, **record})).hexdigest()
    return prefix + digest[:24], digest


def _launch_receipt_record(value: FormalQcLaunchReceipt) -> dict[str, object]:
    return {
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(value)
        if field.name not in {"receipt_id", "receipt_sha256"}
    }


def _register_launch_receipt_authority_impl(
    value: FormalQcLaunchReceipt,
    *,
    permit: FormalSubmissionPermit,
    plan: FormalQcSubmissionPlan | StreamedFormalQcSubmissionPlan,
    streamed: bool,
    _authority_register: Callable[..., object],
) -> FormalQcLaunchReceipt:
    return _authority_register(
        value,
        (
            permit,
            plan,
            streamed,
            _canonical(_launch_receipt_record(value)),
        ),
    )


def _require_launch_receipt_authority_impl(
    value: FormalQcLaunchReceipt,
    *,
    permit: FormalSubmissionPermit | None = None,
    plan: FormalQcSubmissionPlan | StreamedFormalQcSubmissionPlan | None = None,
    streamed: bool | None = None,
    _authority_current: Callable[[object], tuple[object, ...] | None],
) -> tuple[object, ...]:
    if type(value) is not FormalQcLaunchReceipt:
        raise FormalQcSubmissionError("launch receipt type changed")
    registered = _authority_current(value)
    if registered is None:
        raise FormalQcSubmissionError(
            "launch receipt changed or lacks process-return authority"
        )
    if (
        (permit is not None and registered[1] is not permit)
        or (plan is not None and registered[2] is not plan)
        or (streamed is not None and registered[3] is not streamed)
        or registered[4] != _canonical(_launch_receipt_record(value))
        or registered[5] != os.getpid()
    ):
        raise FormalQcSubmissionError("launch receipt authority changed")
    return registered


def _launch_receipt(
    *, permit: FormalSubmissionPermit, plan: FormalQcSubmissionPlan,
    project_id: int, compile_id: str, backtest_id: str,
    initial_status: str,
) -> FormalQcLaunchReceipt:
    record = {
        "permit_id": permit.permit_id, "permit_sha256": permit.permit_sha256,
        "plan_id": plan.plan_id, "plan_sha256": plan.plan_sha256,
        "projection_id": plan.projection_id, "projection_sha256": plan.projection_sha256,
        "economic_execution_binding_id": None,
        "economic_execution_binding_sha256": None,
        "economic_execution_definition_id": None,
        "economic_execution_definition_sha256": None,
        "host_closure_sha256": plan.execution_authority.host_code_closure.closure_sha256,
        "project_id": project_id, "compile_id": compile_id,
        "compile_state": "BuildSuccess", "backtest_id": backtest_id,
        "backtest_name": plan.backtest_name, "initial_status": initial_status,
        "input_object_count": len(plan.upload_bundle.entries),
        "source_file_count": len(plan.source_manifest),
        "backtest_submission_count": 1, "include_statistics": False,
        "result_read_authorized": False, "orders_authorized": False,
    }
    receipt_id, digest = _identified_receipt(
        "arv2-formal-qc-launch-", LAUNCH_RECEIPT_SCHEMA, record
    )
    return FormalQcLaunchReceipt(receipt_id=receipt_id, receipt_sha256=digest, **record)


def _external(
    closure: FormalQcHostClosureBinding, operation: Callable[[], object]
) -> object:
    verify_formal_qc_host_closure_live(closure)
    return operation()


def _streamed_launch_receipt(
    *,
    permit: FormalSubmissionPermit,
    plan: StreamedFormalQcSubmissionPlan,
    project_id: int,
    compile_id: str,
    backtest_id: str,
    initial_status: str,
) -> FormalQcLaunchReceipt:
    record = {
        "permit_id": permit.permit_id,
        "permit_sha256": permit.permit_sha256,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "projection_id": plan.projection_id,
        "projection_sha256": plan.projection_sha256,
        "economic_execution_binding_id": plan.economic_execution.binding_id,
        "economic_execution_binding_sha256": (
            plan.economic_execution.binding_sha256
        ),
        "economic_execution_definition_id": plan.economic_execution.definition_id,
        "economic_execution_definition_sha256": (
            plan.economic_execution.definition_sha256
        ),
        "host_closure_sha256": (
            plan.execution_authority.host_code_closure.closure_sha256
        ),
        "project_id": project_id,
        "compile_id": compile_id,
        "compile_state": "BuildSuccess",
        "backtest_id": backtest_id,
        "backtest_name": plan.backtest_name,
        "initial_status": initial_status,
        "input_object_count": plan.upload_entry_count,
        "source_file_count": len(plan.source_manifest),
        "backtest_submission_count": 1,
        "include_statistics": False,
        "result_read_authorized": False,
        "orders_authorized": False,
    }
    receipt_id, digest = _identified_receipt(
        "arv2-formal-qc-launch-", LAUNCH_RECEIPT_SCHEMA, record
    )
    return FormalQcLaunchReceipt(
        receipt_id=receipt_id, receipt_sha256=digest, **record
    )


def _execute_streamed_formal_qc_submission_once_impl(
    *,
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
    claim: FormalLookClaim,
    client: FormalQcTransport,
    submission_started_at_utc: str,
    _authority_register_launch: Callable[..., FormalQcLaunchReceipt],
    _transport_capability_minter: Callable[..., object],
) -> tuple[FormalSubmissionPermit, FormalQcLaunchReceipt]:
    """Execute the exact one-shot flow without retaining the input payload set."""

    submitted = require_streamed_formal_submission_adapter_bridge(
        submission_bridge
    )
    candidate = submitted.formal_run_candidate
    authority = submitted.reviewed_authority
    plan = submitted.plan
    projection = submitted.runtime_bridge.runtime_projection
    execution = submitted.execution_authority
    _require_non_self_mintable_execution_trust_root(
        execution._owner_signature, execution._receipt_bytes
    )
    require_streamed_formal_qc_submission_plan(
        value=plan, authority=authority
    )
    require_formal_look_claim(candidate, authority, claim)
    _require_concrete_transport(client)
    closure = execution.host_code_closure
    verify_formal_qc_host_closure_live(closure)

    # Re-open and authenticate the entire physical inventory before spending
    # the look.  This pass holds one payload at a time and performs no action.
    _preflight_streamed_upload(submitted.runtime_bridge)
    verify_formal_qc_host_closure_live(closure)
    _require_streamed_authenticated_power_floor(
        submitted.authenticated_power_floor, submitted.runtime_bridge
    )
    _require_streamed_economic_execution(
        submitted.economic_execution, submitted.runtime_bridge
    )
    _require_streamed_report_contract(
        submitted.report_contract, submitted.runtime_bridge
    )
    permit = begin_formal_submission_once(
        candidate=candidate,
        authority=authority,
        claim=claim,
        submission_started_at_utc=submission_started_at_utc,
    )
    transport_capability = _transport_capability_minter(
        transport=client,
        scope="submission",
        binding_record={
            "schema": "arv2-streamed-formal-qc-submission-transport-capability-v1",
            "candidate_sha256": candidate.candidate_sha256,
            "reviewed_authority_sha256": authority.authority_sha256,
            "runtime_bridge_sha256": submitted.runtime_bridge.bridge_sha256,
            "submission_adapter_bridge_sha256": submitted.bridge_sha256,
            "authenticated_power_floor_sha256": (
                submitted.authenticated_power_floor.binding_sha256
            ),
            "economic_execution_binding_sha256": (
                submitted.economic_execution.binding_sha256
            ),
            "economic_execution_definition_sha256": (
                submitted.economic_execution.definition_sha256
            ),
            "formal_report_contract_sha256": (
                submitted.report_contract.contract_sha256
            ),
            "formal_report_contract_artifact_sha256": (
                submitted.report_contract.artifact_sha256
            ),
            "formal_report_contract_stock_bootstrap_seed_sha256": (
                submitted.report_contract.stock_bootstrap_seed_sha256
            ),
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
        },
        call_budget={
            "authenticate": 1,
            "projects/read": 2,
            "projects/create": 1,
            "object/set": plan.upload_entry_count,
            "object/properties": plan.upload_entry_count,
            "files/read": 2,
            "files/create": len(projection.source_files),
            "files/update": len(projection.source_files),
            "compile/create": 1,
            "compile/read": plan.compile_poll_limit,
            "backtests/create": 1,
        },
    )
    try:
        _transport_call(
            client, transport_capability, "_request_json", "authenticate", {}
        )
        inventory = _read_project_inventory(
            _external(
                closure,
                lambda: _transport_call(
                    client,
                    transport_capability,
                    "_request_json",
                    "projects/read",
                    {},
                ),
            )
        )
        if any(
            type(item) is dict and item.get("name") == plan.project_name
            for item in inventory
        ):
            raise FormalQcSubmissionError("exact formal project already exists")
        project = _created_project(
            _external(
                closure,
                lambda: _transport_call(
                    client,
                    transport_capability,
                    "_request_json",
                    "projects/create",
                    {"name": plan.project_name, "language": "Py"},
                ),
            ),
            name=plan.project_name,
            organization_id=plan.organization_id,
        )
        project_id = int(project["projectId"])
        exact_inventory = _read_project_inventory(
            _external(
                closure,
                lambda: _transport_call(
                    client,
                    transport_capability,
                    "_request_json",
                    "projects/read",
                    {"projectId": project_id},
                ),
            )
        )
        if len(exact_inventory) != 1:
            raise FormalQcSubmissionError(
                "projects/read did not return the created project"
            )
        _project_record(
            exact_inventory[0],
            name=plan.project_name,
            organization_id=plan.organization_id,
        )

        uploaded = 0
        for entry in _iter_streamed_upload_entries(
            submitted.runtime_bridge
        ):
            _external(
                closure,
                lambda item=entry: _transport_call(
                    client,
                    transport_capability,
                    "_set_object_multipart",
                    plan.organization_id,
                    item.object_store_key,
                    item.payload,
                ),
            )
            metadata = _external(
                closure,
                lambda item=entry: _transport_call(
                    client,
                    transport_capability,
                    "_read_object_properties",
                    plan.organization_id,
                    item.object_store_key,
                ),
            )
            _object_metadata_matches(metadata, entry)
            uploaded += 1
            del entry
        if uploaded != plan.upload_entry_count:
            raise FormalQcSubmissionError("streamed upload omitted an input object")

        existing = _read_files(
            _external(
                closure,
                lambda: _transport_call(
                    client,
                    transport_capability,
                    "_request_json",
                    "files/read",
                    {"projectId": project_id},
                ),
            )
        )
        projected = {item.project_path: item for item in projection.source_files}
        if not set(existing).issubset({"main.py"}):
            raise FormalQcSubmissionError(
                "new project contains an unexpected source file"
            )
        for path, source in projected.items():
            endpoint = "files/update" if path in existing else "files/create"
            _success(
                _external(
                    closure,
                    lambda endpoint=endpoint, path=path, source=source: _transport_call(
                        client,
                        transport_capability,
                        "_request_json",
                        endpoint,
                        {
                            "projectId": project_id,
                            "name": path,
                            "content": source.content.decode("utf-8"),
                        },
                    ),
                ),
                frozenset({"success", "errors", "messages"}),
                endpoint,
            )
        observed = _read_files(
            _external(
                closure,
                lambda: _transport_call(
                    client,
                    transport_capability,
                    "_request_json",
                    "files/read",
                    {"projectId": project_id},
                ),
            )
        )
        if set(observed) != set(projected):
            raise FormalQcSubmissionError("QC project source inventory changed")
        for path, source in projected.items():
            payload = observed[path].encode("utf-8")
            if (
                len(payload) != source.byte_count
                or hashlib.sha256(payload).hexdigest() != source.content_sha256
            ):
                raise FormalQcSubmissionError("QC project source bytes changed")
        compile_id = _compile_id(
            _external(
                closure,
                lambda: _transport_call(
                    client,
                    transport_capability,
                    "_request_json",
                    "compile/create",
                    {"projectId": project_id},
                ),
            )
        )
        compile_state = ""
        for index in range(plan.compile_poll_limit):
            compile_state = _compile_state(
                _external(
                    closure,
                    lambda: _transport_call(
                        client,
                        transport_capability,
                        "_request_json",
                        "compile/read",
                        {"projectId": project_id, "compileId": compile_id},
                    ),
                ),
                compile_id,
            )
            if compile_state in COMPILE_TERMINAL_STATES:
                break
            if index + 1 == plan.compile_poll_limit:
                raise FormalQcSubmissionError("compile polling exhausted")
            _local_wait(plan.compile_poll_interval_seconds)
        if compile_state != "BuildSuccess":
            raise FormalQcSubmissionError(
                "formal source did not compile successfully"
            )
        backtest_id, initial_status = _created_backtest(
            _external(
                closure,
                lambda: _transport_call(
                    client,
                    transport_capability,
                    "_request_json",
                    "backtests/create",
                    {
                        "projectId": project_id,
                        "compileId": compile_id,
                        "backtestName": plan.backtest_name,
                    },
                ),
            ),
            project_id=project_id,
            name=plan.backtest_name,
        )
        return permit, _authority_register_launch(
            _streamed_launch_receipt(
                permit=permit,
                plan=plan,
                project_id=project_id,
                compile_id=compile_id,
                backtest_id=backtest_id,
                initial_status=initial_status,
            ),
            permit=permit,
            plan=plan,
            streamed=True,
        )
    except Exception as exc:
        if isinstance(exc, FormalQcSubmissionLocked):
            raise
        # Content objects uploaded before a failure remain content-addressed;
        # the manifest is ordered last, and every ambiguity consumes the look.
        raise FormalQcSubmissionLocked(
            "streamed_submission",
            permit.permit_id,
            type(exc).__name__,
            outcome_class=_failure_outcome_class(exc),
        ) from exc


def require_streamed_formal_qc_launch_receipt(
    *,
    value: FormalQcLaunchReceipt,
    permit: FormalSubmissionPermit,
    plan: StreamedFormalQcSubmissionPlan,
) -> FormalQcLaunchReceipt:
    if type(value) is not FormalQcLaunchReceipt:
        raise FormalQcSubmissionError("streamed launch receipt type changed")
    _require_launch_receipt_authority(
        value, permit=permit, plan=plan, streamed=True
    )
    expected = _streamed_launch_receipt(
        permit=permit,
        plan=plan,
        project_id=value.project_id,
        compile_id=value.compile_id,
        backtest_id=value.backtest_id,
        initial_status=value.initial_status,
    )
    if value != expected:
        raise FormalQcSubmissionError("streamed launch receipt changed")
    return value


def _require_legacy_materialized_submission_retired() -> None:
    """Permanently close the pre-streaming launch surface.

    A materialized ``FormalRunCandidate`` has no authenticated identity edge
    to the separately replayed formal TEST scorer.  It therefore cannot prove
    that its caller-supplied observed power counts came from that scorer.  The
    streamed adapter bridge is the sole launchable formal path.
    """

    raise FormalQcSubmissionError(
        "legacy materialized formal QC submission is retired; "
        "the authenticated streamed adapter bridge is required"
    )


def _execute_formal_qc_submission_once_impl(
    *, candidate: FormalRunCandidate, authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim, projection: FormalQcRuntimeProjection,
    plan: FormalQcSubmissionPlan, client: FormalQcTransport,
    submission_started_at_utc: str,
    _authority_register_launch: Callable[..., FormalQcLaunchReceipt],
    _transport_capability_minter: Callable[..., object],
) -> tuple[FormalSubmissionPermit, FormalQcLaunchReceipt]:
    _require_legacy_materialized_submission_retired()
    _require_non_self_mintable_execution_trust_root(
        plan.execution_authority._owner_signature,
        plan.execution_authority._receipt_bytes,
    )
    require_formal_qc_submission_plan(
        value=plan, candidate=candidate, authority=authority, projection=projection
    )
    require_formal_look_claim(candidate, authority, claim)
    _require_concrete_transport(client)
    closure = plan.execution_authority.host_code_closure
    verify_formal_qc_host_closure_live(closure)
    permit = begin_formal_submission_once(
        candidate=candidate, authority=authority, claim=claim,
        submission_started_at_utc=submission_started_at_utc,
    )
    transport_capability = _transport_capability_minter(
        transport=client,
        scope="submission",
        binding_record={
            "schema": "arv2-formal-qc-submission-transport-capability-v1",
            "candidate_sha256": candidate.candidate_sha256,
            "reviewed_authority_sha256": authority.authority_sha256,
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
        },
        call_budget={
            "authenticate": 1,
            "projects/read": 2,
            "projects/create": 1,
            "object/set": len(plan.upload_bundle.entries),
            "object/properties": len(plan.upload_bundle.entries),
            "files/read": 2,
            "files/create": len(projection.source_files),
            "files/update": len(projection.source_files),
            "compile/create": 1,
            "compile/read": plan.compile_poll_limit,
            "backtests/create": 1,
        },
    )
    try:
        # Permit creation is followed only by a pure private-capability mint,
        # then the first network method; every callback/file check happened above.
        _transport_call(
            client, transport_capability, "_request_json", "authenticate", {}
        )
        inventory = _read_project_inventory(_external(
            closure,
            lambda: _transport_call(
                client, transport_capability, "_request_json", "projects/read", {}
            ),
        ))
        if any(type(item) is dict and item.get("name") == plan.project_name for item in inventory):
            raise FormalQcSubmissionError("exact formal project already exists")
        project = _created_project(
            _external(
                closure,
                lambda: _transport_call(
                    client, transport_capability, "_request_json", "projects/create",
                    {"name": plan.project_name, "language": "Py"}
                ),
            ),
            name=plan.project_name,
            organization_id=plan.organization_id,
        )
        project_id = int(project["projectId"])
        exact_inventory = _read_project_inventory(_external(
            closure,
            lambda: _transport_call(
                client, transport_capability, "_request_json", "projects/read",
                {"projectId": project_id}
            ),
        ))
        if len(exact_inventory) != 1:
            raise FormalQcSubmissionError("projects/read did not return the created project")
        _project_record(
            exact_inventory[0], name=plan.project_name,
            organization_id=plan.organization_id,
        )
        for entry in plan.upload_bundle.entries:
            _external(
                closure,
                lambda item=entry: _transport_call(
                    client, transport_capability, "_set_object_multipart",
                    plan.organization_id,
                    item.object_store_key, item.payload),
            )
            metadata = _external(
                closure,
                lambda item=entry: _transport_call(
                    client, transport_capability, "_read_object_properties",
                    plan.organization_id,
                    item.object_store_key),
            )
            _object_metadata_matches(metadata, entry)
        existing = _read_files(_external(
            closure,
            lambda: _transport_call(
                client, transport_capability, "_request_json", "files/read",
                {"projectId": project_id}
            ),
        ))
        projected = {item.project_path: item for item in projection.source_files}
        if not set(existing).issubset({"main.py"}):
            raise FormalQcSubmissionError("new project contains an unexpected source file")
        for path, source in projected.items():
            endpoint = "files/update" if path in existing else "files/create"
            _success(
                _external(
                    closure,
                    lambda endpoint=endpoint, path=path, source=source: _transport_call(
                        client, transport_capability, "_request_json", endpoint,
                        {"projectId": project_id, "name": path, "content": source.content.decode("utf-8")},
                    ),
                ),
                frozenset({"success", "errors", "messages"}), endpoint,
            )
        observed = _read_files(_external(
            closure,
            lambda: _transport_call(
                client, transport_capability, "_request_json", "files/read",
                {"projectId": project_id}
            ),
        ))
        if set(observed) != set(projected):
            raise FormalQcSubmissionError("QC project source inventory changed")
        for path, source in projected.items():
            payload = observed[path].encode("utf-8")
            if len(payload) != source.byte_count or hashlib.sha256(payload).hexdigest() != source.content_sha256:
                raise FormalQcSubmissionError("QC project source bytes changed")
        compile_id = _compile_id(_external(
            closure,
            lambda: _transport_call(
                client, transport_capability, "_request_json", "compile/create",
                {"projectId": project_id}
            ),
        ))
        compile_state = ""
        for index in range(plan.compile_poll_limit):
            compile_state = _compile_state(
                _external(
                    closure,
                    lambda: _transport_call(
                        client, transport_capability, "_request_json", "compile/read",
                        {"projectId": project_id, "compileId": compile_id}
                    ),
                ),
                compile_id,
            )
            if compile_state in COMPILE_TERMINAL_STATES:
                break
            if index + 1 == plan.compile_poll_limit:
                raise FormalQcSubmissionError("compile polling exhausted")
            _local_wait(plan.compile_poll_interval_seconds)
        if compile_state != "BuildSuccess":
            raise FormalQcSubmissionError("formal source did not compile successfully")
        backtest_id, initial_status = _created_backtest(
            _external(
                closure,
                lambda: _transport_call(
                    client, transport_capability, "_request_json", "backtests/create",
                    {"projectId": project_id, "compileId": compile_id, "backtestName": plan.backtest_name},
                ),
            ),
            project_id=project_id,
            name=plan.backtest_name,
        )
        return permit, _authority_register_launch(
            _launch_receipt(
                permit=permit, plan=plan, project_id=project_id,
                compile_id=compile_id, backtest_id=backtest_id,
                initial_status=initial_status,
            ),
            permit=permit,
            plan=plan,
            streamed=False,
        )
    except Exception as exc:
        if isinstance(exc, FormalQcSubmissionLocked):
            raise
        raise FormalQcSubmissionLocked(
            "submission",
            permit.permit_id,
            type(exc).__name__,
            outcome_class=_failure_outcome_class(exc),
        ) from exc


def require_formal_qc_launch_receipt(
    *, value: FormalQcLaunchReceipt, permit: FormalSubmissionPermit,
    plan: FormalQcSubmissionPlan,
) -> FormalQcLaunchReceipt:
    if type(value) is not FormalQcLaunchReceipt:
        raise FormalQcSubmissionError("launch receipt type changed")
    _require_launch_receipt_authority(
        value, permit=permit, plan=plan, streamed=False
    )
    expected = _launch_receipt(
        permit=permit, plan=plan, project_id=value.project_id,
        compile_id=value.compile_id, backtest_id=value.backtest_id,
        initial_status=value.initial_status,
    )
    if value != expected:
        raise FormalQcSubmissionError("launch receipt changed")
    return value


def _require_launch_self_identity(
    value: FormalQcLaunchReceipt,
) -> FormalQcLaunchReceipt:
    _require_launch_receipt_authority(value)
    record = _launch_receipt_record(value)
    receipt_id, digest = _identified_receipt(
        "arv2-formal-qc-launch-", LAUNCH_RECEIPT_SCHEMA, record
    )
    if value.receipt_id != receipt_id or value.receipt_sha256 != digest:
        raise FormalQcSubmissionError("launch receipt content identity changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class FormalQcTerminalStatusReceipt:
    receipt_id: str
    receipt_sha256: str
    launch_receipt_id: str
    launch_receipt_sha256: str
    permit_id: str
    permit_sha256: str
    plan_id: str
    plan_sha256: str
    runtime_bridge_id: str | None
    runtime_bridge_sha256: str | None
    submission_adapter_bridge_id: str | None
    submission_adapter_bridge_sha256: str | None
    authenticated_power_floor_id: str | None
    authenticated_power_floor_sha256: str | None
    economic_execution_binding_id: str | None
    economic_execution_binding_sha256: str | None
    economic_execution_definition_id: str | None
    economic_execution_definition_sha256: str | None
    backtest_id: str
    terminal_status: str
    status_poll_count: int
    statistics_requested: bool
    full_status_envelope_received_and_json_parsed: bool
    statistics_or_result_values_selected_or_inspected: bool
    discarded_values_retained_in_receipt_or_exported: bool


def _terminal_receipt_record(
    value: FormalQcTerminalStatusReceipt,
) -> dict[str, object]:
    return {
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(value)
        if field.name not in {"receipt_id", "receipt_sha256"}
    }


def _register_terminal_status_receipt_authority_impl(
    value: FormalQcTerminalStatusReceipt,
    *,
    launch: FormalQcLaunchReceipt,
    permit: FormalSubmissionPermit,
    plan: FormalQcSubmissionPlan | StreamedFormalQcSubmissionPlan,
    streamed: bool,
    context: tuple[object, ...],
    _authority_register: Callable[..., object],
) -> FormalQcTerminalStatusReceipt:
    return _authority_register(
        value,
        (
            launch,
            permit,
            plan,
            streamed,
            context,
            _canonical(_terminal_receipt_record(value)),
        ),
    )


def _require_terminal_status_receipt_authority_impl(
    value: FormalQcTerminalStatusReceipt,
    *,
    launch: FormalQcLaunchReceipt | None = None,
    permit: FormalSubmissionPermit | None = None,
    plan: FormalQcSubmissionPlan | StreamedFormalQcSubmissionPlan | None = None,
    streamed: bool | None = None,
    context: tuple[object, ...] | None = None,
    _authority_current: Callable[[object], tuple[object, ...] | None],
) -> tuple[object, ...]:
    if type(value) is not FormalQcTerminalStatusReceipt:
        raise FormalQcSubmissionError("terminal receipt type changed")
    registered = _authority_current(value)
    if registered is None:
        raise FormalQcSubmissionError(
            "terminal receipt changed or lacks process-return authority"
        )
    if (
        (launch is not None and registered[1] is not launch)
        or (permit is not None and registered[2] is not permit)
        or (plan is not None and registered[3] is not plan)
        or (streamed is not None and registered[4] is not streamed)
        or (
            context is not None
            and (
                len(registered[5]) != len(context)
                or any(
                    left is not right
                    for left, right in zip(registered[5], context, strict=True)
                )
            )
        )
        or registered[6] != _canonical(_terminal_receipt_record(value))
        or registered[7] != os.getpid()
    ):
        raise FormalQcSubmissionError("terminal receipt authority changed")
    return registered


def _terminal_receipt(
    *, launch: FormalQcLaunchReceipt, permit: FormalSubmissionPermit,
    plan: FormalQcSubmissionPlan, terminal_status: str, status_poll_count: int,
) -> FormalQcTerminalStatusReceipt:
    if (
        type(terminal_status) is not str
        or terminal_status not in BACKTEST_TERMINAL_STATUSES
        or type(status_poll_count) is not int
        or not 1 <= status_poll_count <= plan.status_poll_limit
    ):
        raise FormalQcSubmissionError("terminal receipt status is not terminal")
    record = {
        "launch_receipt_id": launch.receipt_id,
        "launch_receipt_sha256": launch.receipt_sha256,
        "permit_id": permit.permit_id, "permit_sha256": permit.permit_sha256,
        "plan_id": plan.plan_id, "plan_sha256": plan.plan_sha256,
        "runtime_bridge_id": None,
        "runtime_bridge_sha256": None,
        "submission_adapter_bridge_id": None,
        "submission_adapter_bridge_sha256": None,
        "authenticated_power_floor_id": None,
        "authenticated_power_floor_sha256": None,
        "economic_execution_binding_id": None,
        "economic_execution_binding_sha256": None,
        "economic_execution_definition_id": None,
        "economic_execution_definition_sha256": None,
        "backtest_id": launch.backtest_id, "terminal_status": terminal_status,
        "status_poll_count": status_poll_count,
        "statistics_requested": False,
        "full_status_envelope_received_and_json_parsed": True,
        "statistics_or_result_values_selected_or_inspected": False,
        "discarded_values_retained_in_receipt_or_exported": False,
    }
    receipt_id, digest = _identified_receipt(
        "arv2-formal-qc-terminal-", TERMINAL_STATUS_SCHEMA, record
    )
    return FormalQcTerminalStatusReceipt(receipt_id=receipt_id, receipt_sha256=digest, **record)


def _inspect_statistics_free_terminal_status_impl(
    *, candidate: FormalRunCandidate, authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim, permit: FormalSubmissionPermit,
    plan: FormalQcSubmissionPlan, launch: FormalQcLaunchReceipt,
    client: FormalQcTransport,
    _authority_register_terminal: Callable[..., FormalQcTerminalStatusReceipt],
    _transport_capability_minter: Callable[..., object],
) -> FormalQcTerminalStatusReceipt:
    _require_legacy_materialized_submission_retired()
    _require_non_self_mintable_execution_trust_root(
        plan.execution_authority._owner_signature,
        plan.execution_authority._receipt_bytes,
    )
    require_formal_submission_permit(candidate, authority, claim, permit)
    require_formal_qc_launch_receipt(value=launch, permit=permit, plan=plan)
    _require_concrete_transport(client)
    closure = plan.execution_authority.host_code_closure
    transport_capability = _transport_capability_minter(
        transport=client,
        scope="status",
        binding_record={
            "schema": "arv2-formal-qc-status-transport-capability-v1",
            "candidate_sha256": candidate.candidate_sha256,
            "reviewed_authority_sha256": authority.authority_sha256,
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "launch_receipt_sha256": launch.receipt_sha256,
        },
        call_budget={"backtests/list": plan.status_poll_limit},
    )
    for index in range(plan.status_poll_limit):
        try:
            status = parse_statistics_free_backtest_list(
                _external(
                    closure,
                    lambda: _transport_call(
                        client, transport_capability, "_request_json", "backtests/list",
                        {"projectId": launch.project_id, "includeStatistics": False},
                    ),
                ),
                expected_project_id=launch.project_id,
                expected_backtest_id=launch.backtest_id,
                expected_backtest_name=launch.backtest_name,
            )
        except Exception as exc:
            raise FormalQcSubmissionLocked(
                "terminal_status",
                permit.permit_id,
                type(exc).__name__,
                outcome_class=_failure_outcome_class(exc),
            ) from exc
        if status.status in BACKTEST_TERMINAL_STATUSES:
            return _authority_register_terminal(
                _terminal_receipt(
                    launch=launch, permit=permit, plan=plan,
                    terminal_status=status.status, status_poll_count=index + 1,
                ),
                launch=launch,
                permit=permit,
                plan=plan,
                streamed=False,
                context=(candidate, authority, claim),
            )
        if index + 1 == plan.status_poll_limit:
            raise FormalQcSubmissionLocked("terminal_status", permit.permit_id, "poll limit exhausted")
        _local_wait(plan.status_poll_interval_seconds)
    raise AssertionError("unreachable bounded terminal-status loop")


def require_formal_qc_terminal_status_receipt(
    *, terminal: FormalQcTerminalStatusReceipt, launch: FormalQcLaunchReceipt,
    plan: FormalQcSubmissionPlan, permit: FormalSubmissionPermit,
    candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim,
) -> FormalQcTerminalStatusReceipt:
    if type(terminal) is not FormalQcTerminalStatusReceipt:
        raise FormalQcSubmissionError("terminal receipt type changed")
    _require_terminal_status_receipt_authority(
        terminal,
        launch=launch,
        permit=permit,
        plan=plan,
        streamed=False,
        context=(candidate, authority, claim),
    )
    require_formal_submission_permit(candidate, authority, claim, permit)
    expected = _terminal_receipt(
        launch=launch, permit=permit, plan=plan,
        terminal_status=terminal.terminal_status,
        status_poll_count=terminal.status_poll_count,
    )
    if terminal != expected:
        raise FormalQcSubmissionError("terminal receipt changed")
    return terminal


def _streamed_terminal_receipt(
    *,
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
    launch: FormalQcLaunchReceipt,
    permit: FormalSubmissionPermit,
    terminal_status: str,
    status_poll_count: int,
) -> FormalQcTerminalStatusReceipt:
    submitted = require_streamed_formal_submission_adapter_bridge(
        submission_bridge
    )
    if (
        type(terminal_status) is not str
        or terminal_status not in BACKTEST_TERMINAL_STATUSES
        or type(status_poll_count) is not int
        or not 1 <= status_poll_count <= submitted.plan.status_poll_limit
    ):
        raise FormalQcSubmissionError("terminal receipt status is not terminal")
    record = {
        "launch_receipt_id": launch.receipt_id,
        "launch_receipt_sha256": launch.receipt_sha256,
        "permit_id": permit.permit_id,
        "permit_sha256": permit.permit_sha256,
        "plan_id": submitted.plan.plan_id,
        "plan_sha256": submitted.plan.plan_sha256,
        "runtime_bridge_id": submitted.runtime_bridge.bridge_id,
        "runtime_bridge_sha256": submitted.runtime_bridge.bridge_sha256,
        "submission_adapter_bridge_id": submitted.bridge_id,
        "submission_adapter_bridge_sha256": submitted.bridge_sha256,
        "authenticated_power_floor_id": (
            submitted.authenticated_power_floor.binding_id
        ),
        "authenticated_power_floor_sha256": (
            submitted.authenticated_power_floor.binding_sha256
        ),
        "economic_execution_binding_id": submitted.economic_execution.binding_id,
        "economic_execution_binding_sha256": (
            submitted.economic_execution.binding_sha256
        ),
        "economic_execution_definition_id": (
            submitted.economic_execution.definition_id
        ),
        "economic_execution_definition_sha256": (
            submitted.economic_execution.definition_sha256
        ),
        "backtest_id": launch.backtest_id,
        "terminal_status": terminal_status,
        "status_poll_count": status_poll_count,
        "statistics_requested": False,
        "full_status_envelope_received_and_json_parsed": True,
        "statistics_or_result_values_selected_or_inspected": False,
        "discarded_values_retained_in_receipt_or_exported": False,
    }
    receipt_id, digest = _identified_receipt(
        "arv2-formal-qc-terminal-", TERMINAL_STATUS_SCHEMA, record
    )
    return FormalQcTerminalStatusReceipt(
        receipt_id=receipt_id, receipt_sha256=digest, **record
    )


def _inspect_streamed_statistics_free_terminal_status_impl(
    *,
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
    claim: FormalLookClaim,
    permit: FormalSubmissionPermit,
    launch: FormalQcLaunchReceipt,
    client: FormalQcTransport,
    _authority_register_terminal: Callable[..., FormalQcTerminalStatusReceipt],
    _transport_capability_minter: Callable[..., object],
) -> FormalQcTerminalStatusReceipt:
    """Poll only identity/status for the exact authenticated streamed run."""

    submitted = require_streamed_formal_submission_adapter_bridge(
        submission_bridge
    )
    candidate = submitted.formal_run_candidate
    authority = submitted.reviewed_authority
    plan = submitted.plan
    _require_non_self_mintable_execution_trust_root(
        submitted.execution_authority._owner_signature,
        submitted.execution_authority._receipt_bytes,
    )
    require_formal_submission_permit(candidate, authority, claim, permit)
    require_streamed_formal_qc_launch_receipt(
        value=launch, permit=permit, plan=plan
    )
    _require_streamed_authenticated_power_floor(
        submitted.authenticated_power_floor, submitted.runtime_bridge
    )
    _require_streamed_economic_execution(
        submitted.economic_execution, submitted.runtime_bridge
    )
    _require_streamed_report_contract(
        submitted.report_contract, submitted.runtime_bridge
    )
    _require_concrete_transport(client)
    closure = submitted.execution_authority.host_code_closure
    transport_capability = _transport_capability_minter(
        transport=client,
        scope="status",
        binding_record={
            "schema": "arv2-streamed-formal-qc-status-transport-capability-v1",
            "candidate_sha256": candidate.candidate_sha256,
            "reviewed_authority_sha256": authority.authority_sha256,
            "runtime_bridge_sha256": submitted.runtime_bridge.bridge_sha256,
            "submission_adapter_bridge_sha256": submitted.bridge_sha256,
            "authenticated_power_floor_sha256": (
                submitted.authenticated_power_floor.binding_sha256
            ),
            "economic_execution_binding_sha256": (
                submitted.economic_execution.binding_sha256
            ),
            "economic_execution_definition_sha256": (
                submitted.economic_execution.definition_sha256
            ),
            "formal_report_contract_sha256": (
                submitted.report_contract.contract_sha256
            ),
            "formal_report_contract_artifact_sha256": (
                submitted.report_contract.artifact_sha256
            ),
            "formal_report_contract_stock_bootstrap_seed_sha256": (
                submitted.report_contract.stock_bootstrap_seed_sha256
            ),
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "launch_receipt_sha256": launch.receipt_sha256,
        },
        call_budget={"backtests/list": plan.status_poll_limit},
    )
    for index in range(plan.status_poll_limit):
        try:
            status = parse_statistics_free_backtest_list(
                _external(
                    closure,
                    lambda: _transport_call(
                        client,
                        transport_capability,
                        "_request_json",
                        "backtests/list",
                        {
                            "projectId": launch.project_id,
                            "includeStatistics": False,
                        },
                    ),
                ),
                expected_project_id=launch.project_id,
                expected_backtest_id=launch.backtest_id,
                expected_backtest_name=launch.backtest_name,
            )
        except Exception as exc:
            raise FormalQcSubmissionLocked(
                "streamed_terminal_status",
                permit.permit_id,
                type(exc).__name__,
                outcome_class=_failure_outcome_class(exc),
            ) from exc
        if status.status in BACKTEST_TERMINAL_STATUSES:
            return _authority_register_terminal(
                _streamed_terminal_receipt(
                    submission_bridge=submitted,
                    launch=launch,
                    permit=permit,
                    terminal_status=status.status,
                    status_poll_count=index + 1,
                ),
                launch=launch,
                permit=permit,
                plan=plan,
                streamed=True,
                context=(submitted, claim),
            )
        if index + 1 == plan.status_poll_limit:
            raise FormalQcSubmissionLocked(
                "streamed_terminal_status",
                permit.permit_id,
                "poll limit exhausted",
            )
        _local_wait(plan.status_poll_interval_seconds)
    raise AssertionError("unreachable bounded streamed terminal-status loop")


def require_streamed_formal_qc_terminal_status_receipt(
    *,
    terminal: FormalQcTerminalStatusReceipt,
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
    claim: FormalLookClaim,
    permit: FormalSubmissionPermit,
    launch: FormalQcLaunchReceipt,
) -> FormalQcTerminalStatusReceipt:
    submitted = require_streamed_formal_submission_adapter_bridge(
        submission_bridge
    )
    if type(terminal) is not FormalQcTerminalStatusReceipt:
        raise FormalQcSubmissionError("streamed terminal receipt type changed")
    _require_terminal_status_receipt_authority(
        terminal,
        launch=launch,
        permit=permit,
        plan=submitted.plan,
        streamed=True,
        context=(submitted, claim),
    )
    require_formal_submission_permit(
        submitted.formal_run_candidate,
        submitted.reviewed_authority,
        claim,
        permit,
    )
    require_streamed_formal_qc_launch_receipt(
        value=launch, permit=permit, plan=submitted.plan
    )
    expected = _streamed_terminal_receipt(
        submission_bridge=submitted,
        launch=launch,
        permit=permit,
        terminal_status=terminal.terminal_status,
        status_poll_count=terminal.status_poll_count,
    )
    if terminal != expected:
        raise FormalQcSubmissionError("streamed terminal receipt changed")
    return terminal


def streamed_formal_post_launch_capability_record(
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
) -> dict[str, object]:
    """Authenticated pre-launch proof that the streamed run has a closed exit."""

    submitted = require_streamed_formal_submission_adapter_bridge(
        submission_bridge
    )
    return {
        "schema": "arv2-streamed-formal-post-launch-capability-v1",
        "runtime_bridge_id": submitted.runtime_bridge.bridge_id,
        "runtime_bridge_sha256": submitted.runtime_bridge.bridge_sha256,
        "submission_adapter_bridge_id": submitted.bridge_id,
        "submission_adapter_bridge_sha256": submitted.bridge_sha256,
        "authenticated_power_floor_id": (
            submitted.authenticated_power_floor.binding_id
        ),
        "authenticated_power_floor_sha256": (
            submitted.authenticated_power_floor.binding_sha256
        ),
        "economic_execution_binding_id": submitted.economic_execution.binding_id,
        "economic_execution_binding_sha256": (
            submitted.economic_execution.binding_sha256
        ),
        "economic_execution_definition_id": (
            submitted.economic_execution.definition_id
        ),
        "economic_execution_definition_sha256": (
            submitted.economic_execution.definition_sha256
        ),
        "formal_report_contract_id": submitted.report_contract.contract_id,
        "formal_report_contract_sha256": (
            submitted.report_contract.contract_sha256
        ),
        "formal_report_contract_artifact_sha256": (
            submitted.report_contract.artifact_sha256
        ),
        "identity_status_only_value_selection_with_include_statistics_false": True,
        "process_bound_power_authority": True,
        "separate_owner_signed_result_read_gate": True,
        "one_use_selected_summary_statistics_only_read": True,
        "root_authenticated_26_object_report_family_read": True,
        "builder_authenticated_summary_result_receipt": True,
        "formal_evaluation_bridge_receipt_compatible": True,
        "logs_charts_orders_trades_access": False,
    }


def _require_terminal_self_identity(
    value: FormalQcTerminalStatusReceipt,
) -> FormalQcTerminalStatusReceipt:
    _require_terminal_status_receipt_authority(value)
    record = _terminal_receipt_record(value)
    receipt_id, digest = _identified_receipt(
        "arv2-formal-qc-terminal-", TERMINAL_STATUS_SCHEMA, record
    )
    if value.receipt_id != receipt_id or value.receipt_sha256 != digest:
        raise FormalQcSubmissionError("terminal receipt content identity changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcResultGateCandidate:
    gate_id: str
    gate_sha256: str
    terminal_receipt_id: str
    terminal_receipt_sha256: str
    terminal_status: str
    launch_receipt_id: str
    launch_receipt_sha256: str
    plan_id: str
    plan_sha256: str
    projection_id: str
    projection_sha256: str
    runtime_bridge_id: str | None
    runtime_bridge_sha256: str | None
    submission_adapter_bridge_id: str | None
    submission_adapter_bridge_sha256: str | None
    authenticated_power_floor_id: str | None
    authenticated_power_floor_sha256: str | None
    economic_execution_binding_id: str | None
    economic_execution_binding_sha256: str | None
    economic_execution_definition_id: str | None
    economic_execution_definition_sha256: str | None
    expected_input_manifest_sha256: str
    expected_formal_report_contract_sha256: str | None
    formal_result_logical_read_count: int
    formal_result_summary_read_count: int
    formal_result_family_object_read_count: int
    formal_result_transport_call_count: int
    formal_result_root_maximum_byte_count: int
    formal_result_root_maximum_compressed_byte_count: int
    formal_result_family_maximum_uncompressed_byte_count: int
    formal_result_family_maximum_compressed_byte_count: int
    formal_result_family_total_maximum_uncompressed_byte_count: int
    formal_result_family_total_maximum_compressed_byte_count: int
    formal_result_family_key_formula: str
    formal_result_family_package_required: bool
    expected_summary_meta_name: str
    expected_summary_chunk_prefix: str
    result_read_authorized: bool
    owner_terminal_result_authority_receipt_id: None


def build_formal_qc_result_gate_candidate(
    *, terminal: FormalQcTerminalStatusReceipt, launch: FormalQcLaunchReceipt,
    plan: FormalQcSubmissionPlan, permit: FormalSubmissionPermit,
    candidate: FormalRunCandidate, authority: ReviewedFormalRunAuthority,
    claim: FormalLookClaim, projection: FormalQcRuntimeProjection,
) -> FormalQcResultGateCandidate:
    require_formal_qc_terminal_status_receipt(
        terminal=terminal, launch=launch, plan=plan, permit=permit,
        candidate=candidate, authority=authority, claim=claim,
    )
    require_projection_bound_to_candidate(candidate, projection)
    record = {
        "terminal_receipt_id": terminal.receipt_id,
        "terminal_receipt_sha256": terminal.receipt_sha256,
        "terminal_status": terminal.terminal_status,
        "launch_receipt_id": launch.receipt_id,
        "launch_receipt_sha256": launch.receipt_sha256,
        "plan_id": plan.plan_id, "plan_sha256": plan.plan_sha256,
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "runtime_bridge_id": None,
        "runtime_bridge_sha256": None,
        "submission_adapter_bridge_id": None,
        "submission_adapter_bridge_sha256": None,
        "authenticated_power_floor_id": None,
        "authenticated_power_floor_sha256": None,
        "economic_execution_binding_id": None,
        "economic_execution_binding_sha256": None,
        "economic_execution_definition_id": None,
        "economic_execution_definition_sha256": None,
        "expected_input_manifest_sha256": projection.input_manifest.content_sha256,
        "expected_formal_report_contract_sha256": None,
        "formal_result_logical_read_count": FORMAL_RESULT_LOGICAL_READ_COUNT,
        "formal_result_summary_read_count": FORMAL_RESULT_SUMMARY_READ_COUNT,
        "formal_result_family_object_read_count": FORMAL_RESULT_FAMILY_READ_COUNT,
        "formal_result_transport_call_count": FORMAL_RESULT_TRANSPORT_CALL_COUNT,
        "formal_result_root_maximum_byte_count": FORMAL_RESULT_ROOT_MAXIMUM_BYTE_COUNT,
        "formal_result_root_maximum_compressed_byte_count": (
            FORMAL_RESULT_ROOT_MAXIMUM_COMPRESSED_BYTE_COUNT
        ),
        "formal_result_family_maximum_uncompressed_byte_count": (
            FORMAL_RESULT_FAMILY_MAXIMUM_UNCOMPRESSED_BYTE_COUNT
        ),
        "formal_result_family_maximum_compressed_byte_count": (
            MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES
        ),
        "formal_result_family_total_maximum_uncompressed_byte_count": (
            FORMAL_RESULT_FAMILY_TOTAL_MAXIMUM_UNCOMPRESSED_BYTE_COUNT
        ),
        "formal_result_family_total_maximum_compressed_byte_count": (
            MAX_FORMAL_RESULT_FAMILY_TOTAL_BYTES
        ),
        "formal_result_family_key_formula": FORMAL_RESULT_FAMILY_KEY_FORMULA,
        "formal_result_family_package_required": False,
        "expected_summary_meta_name": SUMMARY_META_NAME,
        "expected_summary_chunk_prefix": SUMMARY_CHUNK_PREFIX,
        "result_read_authorized": False,
        "owner_terminal_result_authority_receipt_id": None,
    }
    gate_id, digest = _identified_receipt(
        "arv2-formal-qc-result-gate-", RESULT_GATE_CANDIDATE_SCHEMA, record
    )
    return FormalQcResultGateCandidate(gate_id=gate_id, gate_sha256=digest, **record)


def require_formal_qc_result_gate_candidate(
    *, value: FormalQcResultGateCandidate, terminal: FormalQcTerminalStatusReceipt,
    launch: FormalQcLaunchReceipt, plan: FormalQcSubmissionPlan,
    permit: FormalSubmissionPermit, candidate: FormalRunCandidate,
    authority: ReviewedFormalRunAuthority, claim: FormalLookClaim,
    projection: FormalQcRuntimeProjection,
) -> FormalQcResultGateCandidate:
    if type(value) is not FormalQcResultGateCandidate:
        raise FormalQcSubmissionError("result gate type changed")
    expected = build_formal_qc_result_gate_candidate(
        terminal=terminal, launch=launch, plan=plan, permit=permit,
        candidate=candidate, authority=authority, claim=claim,
        projection=projection,
    )
    if value != expected or value.result_read_authorized is not False:
        raise FormalQcSubmissionError("disabled result gate changed")
    return value


def build_streamed_formal_qc_result_gate_candidate(
    *,
    terminal: FormalQcTerminalStatusReceipt,
    launch: FormalQcLaunchReceipt,
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
    claim: FormalLookClaim,
    permit: FormalSubmissionPermit,
) -> FormalQcResultGateCandidate:
    submitted = require_streamed_formal_submission_adapter_bridge(
        submission_bridge
    )
    require_streamed_formal_qc_terminal_status_receipt(
        terminal=terminal,
        submission_bridge=submitted,
        claim=claim,
        permit=permit,
        launch=launch,
    )
    projection = submitted.runtime_bridge.runtime_projection
    record = {
        "terminal_receipt_id": terminal.receipt_id,
        "terminal_receipt_sha256": terminal.receipt_sha256,
        "terminal_status": terminal.terminal_status,
        "launch_receipt_id": launch.receipt_id,
        "launch_receipt_sha256": launch.receipt_sha256,
        "plan_id": submitted.plan.plan_id,
        "plan_sha256": submitted.plan.plan_sha256,
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "runtime_bridge_id": submitted.runtime_bridge.bridge_id,
        "runtime_bridge_sha256": submitted.runtime_bridge.bridge_sha256,
        "submission_adapter_bridge_id": submitted.bridge_id,
        "submission_adapter_bridge_sha256": submitted.bridge_sha256,
        "authenticated_power_floor_id": (
            submitted.authenticated_power_floor.binding_id
        ),
        "authenticated_power_floor_sha256": (
            submitted.authenticated_power_floor.binding_sha256
        ),
        "economic_execution_binding_id": submitted.economic_execution.binding_id,
        "economic_execution_binding_sha256": (
            submitted.economic_execution.binding_sha256
        ),
        "economic_execution_definition_id": (
            submitted.economic_execution.definition_id
        ),
        "economic_execution_definition_sha256": (
            submitted.economic_execution.definition_sha256
        ),
        "expected_input_manifest_sha256": projection.input_manifest.content_sha256,
        "expected_formal_report_contract_sha256": (
            submitted.report_contract.contract_sha256
        ),
        "formal_result_logical_read_count": FORMAL_RESULT_LOGICAL_READ_COUNT,
        "formal_result_summary_read_count": FORMAL_RESULT_SUMMARY_READ_COUNT,
        "formal_result_family_object_read_count": FORMAL_RESULT_FAMILY_READ_COUNT,
        "formal_result_transport_call_count": FORMAL_RESULT_TRANSPORT_CALL_COUNT,
        "formal_result_root_maximum_byte_count": FORMAL_RESULT_ROOT_MAXIMUM_BYTE_COUNT,
        "formal_result_root_maximum_compressed_byte_count": (
            FORMAL_RESULT_ROOT_MAXIMUM_COMPRESSED_BYTE_COUNT
        ),
        "formal_result_family_maximum_uncompressed_byte_count": (
            FORMAL_RESULT_FAMILY_MAXIMUM_UNCOMPRESSED_BYTE_COUNT
        ),
        "formal_result_family_maximum_compressed_byte_count": (
            MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES
        ),
        "formal_result_family_total_maximum_uncompressed_byte_count": (
            FORMAL_RESULT_FAMILY_TOTAL_MAXIMUM_UNCOMPRESSED_BYTE_COUNT
        ),
        "formal_result_family_total_maximum_compressed_byte_count": (
            MAX_FORMAL_RESULT_FAMILY_TOTAL_BYTES
        ),
        "formal_result_family_key_formula": FORMAL_RESULT_FAMILY_KEY_FORMULA,
        "formal_result_family_package_required": True,
        "expected_summary_meta_name": SUMMARY_META_NAME,
        "expected_summary_chunk_prefix": SUMMARY_CHUNK_PREFIX,
        "result_read_authorized": False,
        "owner_terminal_result_authority_receipt_id": None,
    }
    gate_id, digest = _identified_receipt(
        "arv2-formal-qc-result-gate-", RESULT_GATE_CANDIDATE_SCHEMA, record
    )
    return FormalQcResultGateCandidate(
        gate_id=gate_id, gate_sha256=digest, **record
    )


def require_streamed_formal_qc_result_gate_candidate(
    *,
    value: FormalQcResultGateCandidate,
    terminal: FormalQcTerminalStatusReceipt,
    launch: FormalQcLaunchReceipt,
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
    claim: FormalLookClaim,
    permit: FormalSubmissionPermit,
) -> FormalQcResultGateCandidate:
    if type(value) is not FormalQcResultGateCandidate:
        raise FormalQcSubmissionError("streamed result gate type changed")
    expected = build_streamed_formal_qc_result_gate_candidate(
        terminal=terminal,
        launch=launch,
        submission_bridge=submission_bridge,
        claim=claim,
        permit=permit,
    )
    if value != expected or value.result_read_authorized is not False:
        raise FormalQcSubmissionError("disabled streamed result gate changed")
    return value


def _require_result_gate_self_identity(
    value: FormalQcResultGateCandidate,
) -> FormalQcResultGateCandidate:
    if type(value) is not FormalQcResultGateCandidate:
        raise FormalQcSubmissionError("result gate type changed")
    record = {
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(value)
        if field.name not in {"gate_id", "gate_sha256"}
    }
    gate_id, digest = _identified_receipt(
        "arv2-formal-qc-result-gate-", RESULT_GATE_CANDIDATE_SCHEMA, record
    )
    if (
        value.gate_id != gate_id
        or value.gate_sha256 != digest
        or value.result_read_authorized is not False
        or value.owner_terminal_result_authority_receipt_id is not None
    ):
        raise FormalQcSubmissionError("disabled result gate content identity changed")
    return value


def _require_private_result_directory(path: Path) -> Path:
    if type(path) is not type(Path()) or not path.is_absolute() or path.is_symlink():
        raise FormalQcSubmissionError("result-read ledger directory changed")
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.stat(follow_symlinks=False).st_mode
    except OSError as exc:
        raise FormalQcSubmissionError("result-read ledger directory is unavailable") from exc
    if (
        resolved != path
        or not stat.S_ISDIR(mode)
        or stat.S_IMODE(mode) != 0o700
    ):
        raise FormalQcSubmissionError(
            "result-read ledger directory must be a real private mode-0700 directory"
        )
    return resolved


def _read_private_result_control(path: Path, name: str) -> bytes:
    if type(path) is not type(Path()) or path.is_symlink():
        raise FormalQcSubmissionError(f"{name} must be a nonsymlink Path")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FormalQcSubmissionError(f"{name} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size <= 0
            or before.st_size > MAX_RESULT_READ_CONTROL_BYTES
        ):
            raise FormalQcSubmissionError(
                f"{name} is not a bounded private mode-0600 regular file"
            )
        chunks: list[bytes] = []
        remaining = MAX_RESULT_READ_CONTROL_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(payload) > MAX_RESULT_READ_CONTROL_BYTES
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise FormalQcSubmissionError(f"{name} changed while read")
    finally:
        os.close(descriptor)
    return payload


def _exclusive_private_result_write(
    directory: Path, filename: str, payload: bytes
) -> Path:
    directory = _require_private_result_directory(directory)
    target = directory / filename
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise FormalQcSubmissionLocked(
            "result_read", filename, "result-read authority is already spent"
        ) from exc
    except OSError as exc:
        raise FormalQcSubmissionError(
            "result-read ledger entry could not be created"
        ) from exc
    try:
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise FormalQcSubmissionError("result-read ledger write stalled")
            offset += written
        os.fsync(descriptor)
    except BaseException as exc:
        os.close(descriptor)
        raise FormalQcSubmissionLocked(
            "result_read", filename, "result-read ledger write is ambiguous"
        ) from exc
    else:
        os.close(descriptor)
    try:
        directory_descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        raise FormalQcSubmissionLocked(
            "result_read", filename, "result-read ledger durability is ambiguous"
        ) from exc
    try:
        stored = _read_private_result_control(target, "result-read ledger entry")
    except Exception as exc:
        raise FormalQcSubmissionLocked(
            "result_read", filename, "result-read ledger reauthentication is ambiguous"
        ) from exc
    if stored != payload:
        raise FormalQcSubmissionLocked(
            "result_read", filename, "result-read ledger reauthentication failed"
        )
    return target


def _formal_result_transaction_contract(
    gate: FormalQcResultGateCandidate,
) -> dict[str, object]:
    _sha(gate.expected_input_manifest_sha256, "expected input manifest hash")
    if gate.formal_result_family_package_required is True:
        _sha(
            gate.expected_formal_report_contract_sha256,
            "expected formal report contract hash",
        )
    elif gate.expected_formal_report_contract_sha256 is not None:
        raise FormalQcSubmissionError(
            "legacy result gate gained a report-family contract"
        )
    if (
        gate.formal_result_logical_read_count != FORMAL_RESULT_LOGICAL_READ_COUNT
        or gate.formal_result_summary_read_count != FORMAL_RESULT_SUMMARY_READ_COUNT
        or gate.formal_result_family_object_read_count
        != FORMAL_RESULT_FAMILY_READ_COUNT
        or gate.formal_result_transport_call_count
        != FORMAL_RESULT_TRANSPORT_CALL_COUNT
        or gate.formal_result_root_maximum_byte_count
        != FORMAL_RESULT_ROOT_MAXIMUM_BYTE_COUNT
        or gate.formal_result_root_maximum_compressed_byte_count
        != FORMAL_RESULT_ROOT_MAXIMUM_COMPRESSED_BYTE_COUNT
        or gate.formal_result_family_maximum_uncompressed_byte_count
        != FORMAL_RESULT_FAMILY_MAXIMUM_UNCOMPRESSED_BYTE_COUNT
        or gate.formal_result_family_maximum_compressed_byte_count
        != MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES
        or gate.formal_result_family_total_maximum_uncompressed_byte_count
        != FORMAL_RESULT_FAMILY_TOTAL_MAXIMUM_UNCOMPRESSED_BYTE_COUNT
        or gate.formal_result_family_total_maximum_compressed_byte_count
        != MAX_FORMAL_RESULT_FAMILY_TOTAL_BYTES
        or gate.formal_result_family_key_formula
        != FORMAL_RESULT_FAMILY_KEY_FORMULA
        or type(gate.formal_result_family_package_required) is not bool
    ):
        raise FormalQcSubmissionError("formal result transaction contract changed")
    return {
        "expected_input_manifest_sha256": gate.expected_input_manifest_sha256,
        "expected_formal_report_contract_sha256": (
            gate.expected_formal_report_contract_sha256
        ),
        "formal_result_logical_read_count": gate.formal_result_logical_read_count,
        "formal_result_summary_read_count": gate.formal_result_summary_read_count,
        "formal_result_family_object_read_count": (
            gate.formal_result_family_object_read_count
        ),
        "formal_result_transport_call_count": gate.formal_result_transport_call_count,
        "formal_result_root_maximum_byte_count": (
            gate.formal_result_root_maximum_byte_count
        ),
        "formal_result_root_maximum_compressed_byte_count": (
            gate.formal_result_root_maximum_compressed_byte_count
        ),
        "formal_result_family_maximum_uncompressed_byte_count": (
            gate.formal_result_family_maximum_uncompressed_byte_count
        ),
        "formal_result_family_maximum_compressed_byte_count": (
            gate.formal_result_family_maximum_compressed_byte_count
        ),
        "formal_result_family_total_maximum_uncompressed_byte_count": (
            gate.formal_result_family_total_maximum_uncompressed_byte_count
        ),
        "formal_result_family_total_maximum_compressed_byte_count": (
            gate.formal_result_family_total_maximum_compressed_byte_count
        ),
        "formal_result_family_key_formula": gate.formal_result_family_key_formula,
        "formal_result_family_package_required": (
            gate.formal_result_family_package_required
        ),
    }


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcResultReadExternalPin:
    pin_id: str
    pin_sha256: str
    candidate_id: str
    candidate_sha256: str
    reviewed_authority_id: str
    reviewed_authority_sha256: str
    result_authority_id: str
    result_authority_sha256: str
    result_authority_receipt_sha256: str
    result_gate_id: str
    result_gate_sha256: str
    terminal_receipt_id: str
    terminal_receipt_sha256: str
    launch_receipt_id: str
    launch_receipt_sha256: str
    backtest_id: str
    pin_path: Path
    ledger_path: Path
    maximum_result_reads: int
    expected_input_manifest_sha256: str
    expected_formal_report_contract_sha256: str | None
    formal_result_logical_read_count: int
    formal_result_summary_read_count: int
    formal_result_family_object_read_count: int
    formal_result_transport_call_count: int
    formal_result_root_maximum_byte_count: int
    formal_result_root_maximum_compressed_byte_count: int
    formal_result_family_maximum_uncompressed_byte_count: int
    formal_result_family_maximum_compressed_byte_count: int
    formal_result_family_total_maximum_uncompressed_byte_count: int
    formal_result_family_total_maximum_compressed_byte_count: int
    formal_result_family_key_formula: str
    formal_result_family_package_required: bool
    selected_summary_statistics_only: bool
    bound_report_family_objects_only: bool
    raw_security_event_or_market_rows_selection_forbidden: bool
    logs_charts_orders_trades_value_selection_forbidden: bool
    retry_after_ambiguity: bool
    _pin_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcResultReadAuthority:
    authority_id: str
    authority_sha256: str
    result_gate_id: str
    result_gate_sha256: str
    terminal_receipt_id: str
    terminal_receipt_sha256: str
    terminal_status: str
    backtest_id: str
    expected_summary_meta_name: str
    expected_summary_chunk_prefix: str
    candidate_id: str
    candidate_sha256: str
    reviewed_authority_id: str
    reviewed_authority_sha256: str
    external_pin_id: str
    external_pin_sha256: str
    result_read_pin_path: Path
    result_read_ledger_path: Path
    maximum_result_reads: int
    expected_input_manifest_sha256: str
    expected_formal_report_contract_sha256: str | None
    formal_result_logical_read_count: int
    formal_result_summary_read_count: int
    formal_result_family_object_read_count: int
    formal_result_transport_call_count: int
    formal_result_root_maximum_byte_count: int
    formal_result_root_maximum_compressed_byte_count: int
    formal_result_family_maximum_uncompressed_byte_count: int
    formal_result_family_maximum_compressed_byte_count: int
    formal_result_family_total_maximum_uncompressed_byte_count: int
    formal_result_family_total_maximum_compressed_byte_count: int
    formal_result_family_key_formula: str
    formal_result_family_package_required: bool
    selected_summary_statistics_only: bool
    bound_report_family_objects_only: bool
    raw_security_event_or_market_rows_selection_forbidden: bool
    logs_charts_orders_trades_value_selection_forbidden: bool
    owner_signature_authority_id: str | None
    owner_signature_authority_sha256: str | None
    owner_signature_public_key_blob_sha256: str | None
    owner_signature_sha256: str | None
    owner_signature_purpose: str | None
    owner_signed_payload_sha256: str | None
    _receipt_bytes: bytes = dataclasses.field(repr=False)
    _external_pin: FormalQcResultReadExternalPin = dataclasses.field(repr=False)
    _owner_signature: OwnerSignatureAuthority | None = dataclasses.field(repr=False)


def render_formal_qc_result_read_authority_candidate(
    gate: FormalQcResultGateCandidate,
    launch: FormalQcLaunchReceipt,
    terminal: FormalQcTerminalStatusReceipt,
    *,
    candidate: FormalRunCandidate,
    reviewed_authority: ReviewedFormalRunAuthority,
) -> bytes:
    require_reviewed_formal_run_authority(candidate, reviewed_authority)
    _require_result_gate_self_identity(gate)
    _require_launch_self_identity(launch)
    _require_terminal_self_identity(terminal)
    if (
        gate.terminal_status != "Completed."
        or terminal.terminal_status != "Completed."
        or gate.terminal_receipt_id != terminal.receipt_id
        or gate.terminal_receipt_sha256 != terminal.receipt_sha256
        or gate.launch_receipt_id != launch.receipt_id
        or gate.launch_receipt_sha256 != launch.receipt_sha256
        or gate.plan_id == ""
    ):
        raise FormalQcSubmissionError("exact disabled result gate is required")
    directory = _require_private_result_directory(reviewed_authority.claim_directory)
    pin_path = directory / RESULT_READ_EXTERNAL_PIN_FILENAME
    ledger_path = directory / RESULT_READ_LEDGER_FILENAME
    seed = {
        "schema": RESULT_READ_AUTHORITY_SCHEMA,
        "authority_id": None, "authority_sha256": None,
        "result_gate_id": gate.gate_id, "result_gate_sha256": gate.gate_sha256,
        "terminal_receipt_id": gate.terminal_receipt_id,
        "terminal_receipt_sha256": gate.terminal_receipt_sha256,
        "terminal_status": gate.terminal_status,
        "backtest_id": launch.backtest_id,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "reviewed_authority_id": reviewed_authority.authority_id,
        "reviewed_authority_sha256": reviewed_authority.authority_sha256,
        "result_read_pin_path": str(pin_path),
        "result_read_ledger_path": str(ledger_path),
        "expected_summary_meta_name": SUMMARY_META_NAME,
        "expected_summary_chunk_prefix": SUMMARY_CHUNK_PREFIX,
        "maximum_result_reads": 1,
        **_formal_result_transaction_contract(gate),
        "selected_summary_statistics_only": True,
        "bound_report_family_objects_only": gate.formal_result_family_package_required,
        "raw_security_event_or_market_rows_selection_forbidden": True,
        "logs_charts_orders_trades_value_selection_forbidden": True,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["authority_sha256"] = digest
    seed["authority_id"] = "arv2-formal-qc-result-read-authority-" + digest
    return _canonical(seed)


def _result_read_external_pin_document(
    *,
    candidate: FormalRunCandidate,
    reviewed_authority: ReviewedFormalRunAuthority,
    gate: FormalQcResultGateCandidate,
    launch: FormalQcLaunchReceipt,
    terminal: FormalQcTerminalStatusReceipt,
    result_authority_receipt_bytes: bytes,
) -> dict[str, object]:
    expected_authority = render_formal_qc_result_read_authority_candidate(
        gate,
        launch,
        terminal,
        candidate=candidate,
        reviewed_authority=reviewed_authority,
    )
    if (
        type(result_authority_receipt_bytes) is not bytes
        or result_authority_receipt_bytes != expected_authority
    ):
        raise FormalQcSubmissionError(
            "result-read authority receipt does not match the owner pin candidate"
        )
    authority_record = _json_object(expected_authority, "result-read authority")
    directory = _require_private_result_directory(reviewed_authority.claim_directory)
    seed = {
        "schema": RESULT_READ_EXTERNAL_PIN_SCHEMA,
        "status": "owner_authorized_one_logical_multipart_result_read",
        "pin_id": None,
        "pin_sha256": None,
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "reviewed_authority_id": reviewed_authority.authority_id,
        "reviewed_authority_sha256": reviewed_authority.authority_sha256,
        "result_authority_id": authority_record["authority_id"],
        "result_authority_sha256": authority_record["authority_sha256"],
        "result_authority_receipt_sha256": hashlib.sha256(
            result_authority_receipt_bytes
        ).hexdigest(),
        "result_gate_id": gate.gate_id,
        "result_gate_sha256": gate.gate_sha256,
        "terminal_receipt_id": terminal.receipt_id,
        "terminal_receipt_sha256": terminal.receipt_sha256,
        "launch_receipt_id": launch.receipt_id,
        "launch_receipt_sha256": launch.receipt_sha256,
        "backtest_id": launch.backtest_id,
        "pin_path": str(directory / RESULT_READ_EXTERNAL_PIN_FILENAME),
        "ledger_path": str(directory / RESULT_READ_LEDGER_FILENAME),
        "maximum_result_reads": 1,
        **_formal_result_transaction_contract(gate),
        "selected_summary_statistics_only": True,
        "bound_report_family_objects_only": gate.formal_result_family_package_required,
        "raw_security_event_or_market_rows_selection_forbidden": True,
        "logs_charts_orders_trades_value_selection_forbidden": True,
        "retry_after_ambiguity": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["pin_sha256"] = digest
    seed["pin_id"] = "arv2-formal-qc-result-read-pin-" + digest[:24]
    return seed


def render_formal_qc_result_read_external_pin_candidate(
    *,
    candidate: FormalRunCandidate,
    reviewed_authority: ReviewedFormalRunAuthority,
    gate: FormalQcResultGateCandidate,
    launch: FormalQcLaunchReceipt,
    terminal: FormalQcTerminalStatusReceipt,
    result_authority_receipt_bytes: bytes,
) -> bytes:
    """Render a trust-root candidate; rendering alone grants no read access.

    The owner must place these exact bytes at ``pin_path`` as a private 0600
    regular file.  The adapter never creates or updates that authorization.
    """

    return _canonical(
        _result_read_external_pin_document(
            candidate=candidate,
            reviewed_authority=reviewed_authority,
            gate=gate,
            launch=launch,
            terminal=terminal,
            result_authority_receipt_bytes=result_authority_receipt_bytes,
        )
    )


def load_formal_qc_result_read_external_pin(
    *,
    candidate: FormalRunCandidate,
    reviewed_authority: ReviewedFormalRunAuthority,
    gate: FormalQcResultGateCandidate,
    launch: FormalQcLaunchReceipt,
    terminal: FormalQcTerminalStatusReceipt,
    result_authority_receipt_bytes: bytes,
) -> FormalQcResultReadExternalPin:
    expected = render_formal_qc_result_read_external_pin_candidate(
        candidate=candidate,
        reviewed_authority=reviewed_authority,
        gate=gate,
        launch=launch,
        terminal=terminal,
        result_authority_receipt_bytes=result_authority_receipt_bytes,
    )
    pin_path = reviewed_authority.claim_directory / RESULT_READ_EXTERNAL_PIN_FILENAME
    payload = _read_private_result_control(pin_path, "owner result-read external pin")
    if payload != expected:
        raise FormalQcSubmissionError("owner result-read external pin changed")
    raw = _json_object(payload, "owner result-read external pin")
    return FormalQcResultReadExternalPin(
        pin_id=str(raw["pin_id"]),
        pin_sha256=str(raw["pin_sha256"]),
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        reviewed_authority_id=reviewed_authority.authority_id,
        reviewed_authority_sha256=reviewed_authority.authority_sha256,
        result_authority_id=str(raw["result_authority_id"]),
        result_authority_sha256=str(raw["result_authority_sha256"]),
        result_authority_receipt_sha256=str(
            raw["result_authority_receipt_sha256"]
        ),
        result_gate_id=gate.gate_id,
        result_gate_sha256=gate.gate_sha256,
        terminal_receipt_id=terminal.receipt_id,
        terminal_receipt_sha256=terminal.receipt_sha256,
        launch_receipt_id=launch.receipt_id,
        launch_receipt_sha256=launch.receipt_sha256,
        backtest_id=launch.backtest_id,
        pin_path=pin_path,
        ledger_path=reviewed_authority.claim_directory / RESULT_READ_LEDGER_FILENAME,
        maximum_result_reads=1,
        **_formal_result_transaction_contract(gate),
        selected_summary_statistics_only=True,
        bound_report_family_objects_only=gate.formal_result_family_package_required,
        raw_security_event_or_market_rows_selection_forbidden=True,
        logs_charts_orders_trades_value_selection_forbidden=True,
        retry_after_ambiguity=False,
        _pin_bytes=payload,
    )


def require_formal_qc_result_read_external_pin(
    *,
    value: FormalQcResultReadExternalPin,
    candidate: FormalRunCandidate,
    reviewed_authority: ReviewedFormalRunAuthority,
    gate: FormalQcResultGateCandidate,
    launch: FormalQcLaunchReceipt,
    terminal: FormalQcTerminalStatusReceipt,
    result_authority_receipt_bytes: bytes,
) -> FormalQcResultReadExternalPin:
    if type(value) is not FormalQcResultReadExternalPin:
        raise FormalQcSubmissionError("owner result-read external pin type changed")
    loaded = load_formal_qc_result_read_external_pin(
        candidate=candidate,
        reviewed_authority=reviewed_authority,
        gate=gate,
        launch=launch,
        terminal=terminal,
        result_authority_receipt_bytes=result_authority_receipt_bytes,
    )
    if value != loaded:
        raise FormalQcSubmissionError("owner result-read external pin changed")
    return value


def load_formal_qc_result_read_authority(
    *, gate: FormalQcResultGateCandidate, launch: FormalQcLaunchReceipt,
    terminal: FormalQcTerminalStatusReceipt,
    candidate: FormalRunCandidate,
    reviewed_authority: ReviewedFormalRunAuthority,
    receipt_bytes: bytes,
    owner_signature: OwnerSignatureAuthority | None = None,
) -> FormalQcResultReadAuthority:
    expected = render_formal_qc_result_read_authority_candidate(
        gate,
        launch,
        terminal,
        candidate=candidate,
        reviewed_authority=reviewed_authority,
    )
    if type(receipt_bytes) is not bytes or receipt_bytes != expected:
        raise FormalQcSubmissionError("result-read authority receipt bytes changed")
    _require_non_self_mintable_result_read_trust_root(owner_signature, expected)
    raw = _json_object(receipt_bytes, "result-read authority")
    external_pin = load_formal_qc_result_read_external_pin(
        candidate=candidate,
        reviewed_authority=reviewed_authority,
        gate=gate,
        launch=launch,
        terminal=terminal,
        result_authority_receipt_bytes=receipt_bytes,
    )
    return FormalQcResultReadAuthority(
        authority_id=str(raw["authority_id"]), authority_sha256=str(raw["authority_sha256"]),
        result_gate_id=gate.gate_id, result_gate_sha256=gate.gate_sha256,
        terminal_receipt_id=gate.terminal_receipt_id,
        terminal_receipt_sha256=gate.terminal_receipt_sha256,
        terminal_status=gate.terminal_status,
        backtest_id=launch.backtest_id,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        reviewed_authority_id=reviewed_authority.authority_id,
        reviewed_authority_sha256=reviewed_authority.authority_sha256,
        external_pin_id=external_pin.pin_id,
        external_pin_sha256=external_pin.pin_sha256,
        result_read_pin_path=external_pin.pin_path,
        result_read_ledger_path=external_pin.ledger_path,
        expected_summary_meta_name=SUMMARY_META_NAME,
        expected_summary_chunk_prefix=SUMMARY_CHUNK_PREFIX,
        maximum_result_reads=1, selected_summary_statistics_only=True,
        **_formal_result_transaction_contract(gate),
        bound_report_family_objects_only=gate.formal_result_family_package_required,
        raw_security_event_or_market_rows_selection_forbidden=True,
        logs_charts_orders_trades_value_selection_forbidden=True,
        owner_signature_authority_id=(
            owner_signature.authority_id
            if type(owner_signature) is OwnerSignatureAuthority else None
        ),
        owner_signature_authority_sha256=(
            owner_signature.authority_sha256
            if type(owner_signature) is OwnerSignatureAuthority else None
        ),
        owner_signature_public_key_blob_sha256=(
            owner_signature.public_key_blob_sha256
            if type(owner_signature) is OwnerSignatureAuthority else None
        ),
        owner_signature_sha256=(
            owner_signature.signature_sha256
            if type(owner_signature) is OwnerSignatureAuthority else None
        ),
        owner_signature_purpose=(
            owner_signature.purpose
            if type(owner_signature) is OwnerSignatureAuthority else None
        ),
        owner_signed_payload_sha256=(
            owner_signature.authority_payload_sha256
            if type(owner_signature) is OwnerSignatureAuthority else None
        ),
        _receipt_bytes=bytes(receipt_bytes),
        _external_pin=external_pin,
        _owner_signature=owner_signature,
    )


def require_formal_qc_result_read_authority(
    *, value: FormalQcResultReadAuthority,
    gate: FormalQcResultGateCandidate,
    launch: FormalQcLaunchReceipt,
    terminal: FormalQcTerminalStatusReceipt,
    candidate: FormalRunCandidate,
    reviewed_authority: ReviewedFormalRunAuthority,
) -> FormalQcResultReadAuthority:
    if type(value) is not FormalQcResultReadAuthority:
        raise FormalQcSubmissionError("result-read authority type changed")
    rebuilt = load_formal_qc_result_read_authority(
        gate=gate,
        launch=launch,
        terminal=terminal,
        candidate=candidate,
        reviewed_authority=reviewed_authority,
        receipt_bytes=value._receipt_bytes,
        owner_signature=value._owner_signature,
    )
    if any(
        getattr(value, field.name) != getattr(rebuilt, field.name)
        for field in dataclasses.fields(FormalQcResultReadAuthority)
    ):
        raise FormalQcSubmissionError("result-read authority changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class FormalQcResultReadPermit:
    permit_id: str
    permit_sha256: str
    result_authority_id: str
    result_authority_sha256: str
    result_gate_id: str
    result_gate_sha256: str
    external_pin_id: str
    external_pin_sha256: str
    backtest_id: str
    result_read_started_at_utc: str
    maximum_result_reads: int
    expected_input_manifest_sha256: str
    expected_formal_report_contract_sha256: str | None
    formal_result_logical_read_count: int
    formal_result_summary_read_count: int
    formal_result_family_object_read_count: int
    formal_result_transport_call_count: int
    formal_result_root_maximum_byte_count: int
    formal_result_root_maximum_compressed_byte_count: int
    formal_result_family_maximum_uncompressed_byte_count: int
    formal_result_family_maximum_compressed_byte_count: int
    formal_result_family_total_maximum_uncompressed_byte_count: int
    formal_result_family_total_maximum_compressed_byte_count: int
    formal_result_family_key_formula: str
    formal_result_family_package_required: bool
    bound_report_family_objects_only: bool
    raw_security_event_or_market_rows_selection_forbidden: bool
    result_read_attempt_count: int
    ambiguous_result_read_consumes_authority: bool
    retry_authorized: bool
    ledger_path: Path
    _permit_bytes: bytes = dataclasses.field(repr=False)


def build_formal_qc_result_read_permit(
    *, result_authority: FormalQcResultReadAuthority,
    result_read_started_at_utc: str,
) -> FormalQcResultReadPermit:
    if type(result_authority) is not FormalQcResultReadAuthority:
        raise FormalQcSubmissionError("result-read authority type changed")
    if type(result_read_started_at_utc) is not str:
        raise FormalQcSubmissionError("result-read timestamp changed type")
    try:
        parsed = datetime.fromisoformat(
            result_read_started_at_utc[:-1] + "+00:00"
        ) if result_read_started_at_utc.endswith("Z") else None
    except ValueError as exc:
        raise FormalQcSubmissionError("result-read timestamp is not canonical UTC") from exc
    if (
        parsed is None
        or parsed.tzinfo != timezone.utc
        or parsed.microsecond != 0
        or parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
        != result_read_started_at_utc
    ):
        raise FormalQcSubmissionError("result-read timestamp is not canonical UTC")
    record = {
        "result_authority_id": result_authority.authority_id,
        "result_authority_sha256": result_authority.authority_sha256,
        "result_gate_id": result_authority.result_gate_id,
        "result_gate_sha256": result_authority.result_gate_sha256,
        "external_pin_id": result_authority.external_pin_id,
        "external_pin_sha256": result_authority.external_pin_sha256,
        "backtest_id": result_authority.backtest_id,
        "result_read_started_at_utc": result_read_started_at_utc,
        "maximum_result_reads": 1,
        "expected_input_manifest_sha256": (
            result_authority.expected_input_manifest_sha256
        ),
        "expected_formal_report_contract_sha256": (
            result_authority.expected_formal_report_contract_sha256
        ),
        "formal_result_logical_read_count": (
            result_authority.formal_result_logical_read_count
        ),
        "formal_result_summary_read_count": (
            result_authority.formal_result_summary_read_count
        ),
        "formal_result_family_object_read_count": (
            result_authority.formal_result_family_object_read_count
        ),
        "formal_result_transport_call_count": (
            result_authority.formal_result_transport_call_count
        ),
        "formal_result_root_maximum_byte_count": (
            result_authority.formal_result_root_maximum_byte_count
        ),
        "formal_result_root_maximum_compressed_byte_count": (
            result_authority.formal_result_root_maximum_compressed_byte_count
        ),
        "formal_result_family_maximum_uncompressed_byte_count": (
            result_authority.formal_result_family_maximum_uncompressed_byte_count
        ),
        "formal_result_family_maximum_compressed_byte_count": (
            result_authority.formal_result_family_maximum_compressed_byte_count
        ),
        "formal_result_family_total_maximum_uncompressed_byte_count": (
            result_authority.formal_result_family_total_maximum_uncompressed_byte_count
        ),
        "formal_result_family_total_maximum_compressed_byte_count": (
            result_authority.formal_result_family_total_maximum_compressed_byte_count
        ),
        "formal_result_family_key_formula": (
            result_authority.formal_result_family_key_formula
        ),
        "formal_result_family_package_required": (
            result_authority.formal_result_family_package_required
        ),
        "bound_report_family_objects_only": (
            result_authority.bound_report_family_objects_only
        ),
        "raw_security_event_or_market_rows_selection_forbidden": (
            result_authority.raw_security_event_or_market_rows_selection_forbidden
        ),
        "result_read_attempt_count": 1,
        "ambiguous_result_read_consumes_authority": True,
        "retry_authorized": False,
        "ledger_path": str(result_authority.result_read_ledger_path),
    }
    permit_id, digest = _identified_receipt(
        "arv2-formal-qc-result-read-permit-", RESULT_READ_PERMIT_SCHEMA, record
    )
    payload = _canonical({
        "schema": RESULT_READ_PERMIT_SCHEMA,
        "permit_id": permit_id,
        "permit_sha256": digest,
        **record,
    })
    return FormalQcResultReadPermit(
        permit_id=permit_id,
        permit_sha256=digest,
        result_authority_id=result_authority.authority_id,
        result_authority_sha256=result_authority.authority_sha256,
        result_gate_id=result_authority.result_gate_id,
        result_gate_sha256=result_authority.result_gate_sha256,
        external_pin_id=result_authority.external_pin_id,
        external_pin_sha256=result_authority.external_pin_sha256,
        backtest_id=result_authority.backtest_id,
        result_read_started_at_utc=result_read_started_at_utc,
        maximum_result_reads=1,
        expected_input_manifest_sha256=(
            result_authority.expected_input_manifest_sha256
        ),
        expected_formal_report_contract_sha256=(
            result_authority.expected_formal_report_contract_sha256
        ),
        formal_result_logical_read_count=(
            result_authority.formal_result_logical_read_count
        ),
        formal_result_summary_read_count=(
            result_authority.formal_result_summary_read_count
        ),
        formal_result_family_object_read_count=(
            result_authority.formal_result_family_object_read_count
        ),
        formal_result_transport_call_count=(
            result_authority.formal_result_transport_call_count
        ),
        formal_result_root_maximum_byte_count=(
            result_authority.formal_result_root_maximum_byte_count
        ),
        formal_result_root_maximum_compressed_byte_count=(
            result_authority.formal_result_root_maximum_compressed_byte_count
        ),
        formal_result_family_maximum_uncompressed_byte_count=(
            result_authority.formal_result_family_maximum_uncompressed_byte_count
        ),
        formal_result_family_maximum_compressed_byte_count=(
            result_authority.formal_result_family_maximum_compressed_byte_count
        ),
        formal_result_family_total_maximum_uncompressed_byte_count=(
            result_authority.formal_result_family_total_maximum_uncompressed_byte_count
        ),
        formal_result_family_total_maximum_compressed_byte_count=(
            result_authority.formal_result_family_total_maximum_compressed_byte_count
        ),
        formal_result_family_key_formula=(
            result_authority.formal_result_family_key_formula
        ),
        formal_result_family_package_required=(
            result_authority.formal_result_family_package_required
        ),
        bound_report_family_objects_only=(
            result_authority.bound_report_family_objects_only
        ),
        raw_security_event_or_market_rows_selection_forbidden=(
            result_authority.raw_security_event_or_market_rows_selection_forbidden
        ),
        result_read_attempt_count=1,
        ambiguous_result_read_consumes_authority=True,
        retry_authorized=False,
        ledger_path=result_authority.result_read_ledger_path,
        _permit_bytes=payload,
    )


def _begin_formal_qc_result_read_once(
    *,
    result_authority: FormalQcResultReadAuthority,
    result_read_started_at_utc: str,
) -> FormalQcResultReadPermit:
    """Durably consume the exact externally pinned result-read authority."""

    if type(result_authority) is not FormalQcResultReadAuthority:
        raise FormalQcSubmissionError("result-read authority type changed")
    if (
        result_authority.maximum_result_reads != 1
        or result_authority.result_read_ledger_path
        != result_authority._external_pin.ledger_path
        or result_authority.result_read_pin_path
        != result_authority._external_pin.pin_path
        or _read_private_result_control(
            result_authority.result_read_pin_path,
            "owner result-read external pin",
        )
        != result_authority._external_pin._pin_bytes
    ):
        raise FormalQcSubmissionError("owner result-read external pin changed")
    permit = build_formal_qc_result_read_permit(
        result_authority=result_authority,
        result_read_started_at_utc=result_read_started_at_utc,
    )
    target = _exclusive_private_result_write(
        result_authority.result_read_ledger_path.parent,
        result_authority.result_read_ledger_path.name,
        permit._permit_bytes,
    )
    if target != result_authority.result_read_ledger_path:
        raise FormalQcSubmissionLocked(
            "result_read", permit.permit_id, "result-read ledger path changed"
        )
    return permit


def require_formal_qc_result_read_permit(
    *, value: FormalQcResultReadPermit,
    result_authority: FormalQcResultReadAuthority,
) -> FormalQcResultReadPermit:
    if type(value) is not FormalQcResultReadPermit:
        raise FormalQcSubmissionError("result-read permit type changed")
    expected = build_formal_qc_result_read_permit(
        result_authority=result_authority,
        result_read_started_at_utc=value.result_read_started_at_utc,
    )
    if (
        value != expected
        or value.ledger_path != result_authority.result_read_ledger_path
        or _read_private_result_control(
            value.ledger_path, "result-read ledger entry"
        )
        != value._permit_bytes
    ):
        raise FormalQcSubmissionError("result-read permit changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class FormalQcSummaryResultReadReceipt:
    receipt_id: str
    receipt_sha256: str
    result_authority_id: str
    result_authority_sha256: str
    result_read_permit_id: str
    result_read_permit_sha256: str
    external_pin_id: str
    external_pin_sha256: str
    result_read_ledger_path: Path
    terminal_receipt_id: str
    terminal_receipt_sha256: str
    launch_receipt_id: str
    launch_receipt_sha256: str
    project_id: int
    backtest_id: str
    terminal_status: str
    summary_pairs: tuple[tuple[str, str], ...]
    summary_pairs_sha256: str
    result_read_count: int
    formal_result_root_manifest_sha256: str | None
    formal_result_root_manifest_byte_count: int
    streamed_preknown_bindings_sha256: str | None
    formal_result_input_manifest_sha256: str | None
    formal_result_report_contract_sha256: str | None
    formal_result_descriptor_inventory_sha256: str | None
    formal_result_root_descriptor_inventory_sha256: str | None
    formal_result_object_store_key_inventory_sha256: str | None
    formal_result_family_payload_inventory_sha256: str | None
    formal_result_family_object_count: int
    formal_result_total_uncompressed_byte_count: int
    formal_result_total_compressed_byte_count: int
    formal_result_summary_read_count: int
    formal_result_family_object_read_count: int
    formal_result_transport_call_count: int
    formal_result_all_family_objects_content_authenticated: bool
    process_authenticated_qc_read: bool
    full_result_envelope_received_and_json_parsed: bool
    standard_statistic_values_selected_or_inspected: bool
    logs_charts_orders_trades_values_selected_or_inspected: bool
    unrelated_values_retained_in_receipt_or_exported: bool
    _result_read_permit: FormalQcResultReadPermit = dataclasses.field(repr=False)
    _formal_result_root_manifest: bytes = dataclasses.field(repr=False)
    _formal_result_family_payloads: tuple[tuple[str, bytes], ...] = (
        dataclasses.field(repr=False)
    )
    _formal_result_bindings: object = dataclasses.field(repr=False)
    _formal_result_family_descriptors: tuple[object, ...] = dataclasses.field(
        repr=False
    )


def _summary_pairs_topology(
    value: tuple[tuple[str, str], ...],
) -> tuple[object, ...]:
    if type(value) is not tuple or any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or type(item[1]) is not str
        for item in value
    ):
        raise FormalQcSubmissionError("summary result pair topology changed")
    return (
        id(value),
        len(value),
        tuple(
            (id(item), len(item), id(item[0]), id(item[1]))
            for item in value
        ),
    )


def _formal_result_package_topology(
    root_manifest: bytes,
    family_payloads: tuple[tuple[str, bytes], ...],
    bindings: object,
    descriptors: tuple[object, ...],
) -> tuple[object, ...]:
    if (
        type(root_manifest) is not bytes
        or type(family_payloads) is not tuple
        or type(descriptors) is not tuple
    ):
        raise FormalQcSubmissionError("formal result package topology changed")
    if any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or type(item[1]) is not bytes
        for item in family_payloads
    ):
        raise FormalQcSubmissionError("formal result family topology changed")
    if bindings is None:
        binding_bytes = b""
    else:
        try:
            binding_record = bindings.to_record()
        except (AttributeError, TypeError, ValueError) as exc:
            raise FormalQcSubmissionError(
                "formal result binding topology changed"
            ) from exc
        binding_bytes = _canonical(binding_record)
    try:
        descriptor_bytes = _canonical(
            [descriptor.to_record() for descriptor in descriptors]
        )
    except (AttributeError, TypeError, ValueError) as exc:
        if descriptors:
            raise FormalQcSubmissionError(
                "formal result descriptor topology changed"
            ) from exc
        descriptor_bytes = b"[]\n"
    return (
        id(root_manifest), len(root_manifest), hashlib.sha256(root_manifest).hexdigest(),
        id(family_payloads), len(family_payloads),
        tuple(
            (
                id(item), id(item[0]), item[0], id(item[1]), len(item[1]),
                hashlib.sha256(item[1]).hexdigest(),
            )
            for item in family_payloads
        ),
        id(bindings), binding_bytes,
        id(descriptors), tuple(id(item) for item in descriptors), descriptor_bytes,
    )


def _formal_result_receipt_attestation(
    *, root_manifest: bytes,
    family_payloads: tuple[tuple[str, bytes], ...],
    bindings: object,
    descriptors: tuple[object, ...],
    project_id: int,
) -> dict[str, object]:
    if not root_manifest and not family_payloads and bindings is None and not descriptors:
        return {
            "formal_result_root_manifest_sha256": None,
            "formal_result_root_manifest_byte_count": 0,
            "streamed_preknown_bindings_sha256": None,
            "formal_result_input_manifest_sha256": None,
            "formal_result_report_contract_sha256": None,
            "formal_result_descriptor_inventory_sha256": None,
            "formal_result_root_descriptor_inventory_sha256": None,
            "formal_result_object_store_key_inventory_sha256": None,
            "formal_result_family_payload_inventory_sha256": None,
            "formal_result_family_object_count": 0,
            "formal_result_total_uncompressed_byte_count": 0,
            "formal_result_total_compressed_byte_count": 0,
            "formal_result_summary_read_count": FORMAL_RESULT_SUMMARY_READ_COUNT,
            "formal_result_family_object_read_count": 0,
            "formal_result_transport_call_count": FORMAL_RESULT_SUMMARY_READ_COUNT,
            "formal_result_all_family_objects_content_authenticated": False,
        }
    if (
        type(project_id) is not int
        or project_id <= 0
        or len(family_payloads) != FORMAL_RESULT_FAMILY_READ_COUNT
        or len(descriptors) != FORMAL_RESULT_FAMILY_READ_COUNT
        or bindings is None
    ):
        raise FormalQcSubmissionError("formal result package census changed")
    root = _json_object(root_manifest, "formal result root manifest")
    preknown = root.get("streamed_preknown_bindings")
    if type(preknown) is not dict:
        raise FormalQcSubmissionError(
            "formal result root omitted streamed preknown bindings"
        )
    descriptor_records = [descriptor.to_record() for descriptor in descriptors]
    suffixes = tuple(descriptor.object_store_key_suffix for descriptor in descriptors)
    if tuple(item[0] for item in family_payloads) != suffixes:
        raise FormalQcSubmissionError("formal result payload order changed")
    root_sha256 = hashlib.sha256(root_manifest).hexdigest()
    descriptor_inventory = hashlib.sha256(
        _canonical(descriptor_records)
    ).hexdigest()
    key_inventory = [f"{project_id}/{suffix}" for suffix in suffixes]
    payload_inventory = [
        {
            "object_store_key_suffix": suffix,
            "compressed_byte_count": len(payload),
            "compressed_sha256": hashlib.sha256(payload).hexdigest(),
        }
        for suffix, payload in family_payloads
    ]
    return {
        "formal_result_root_manifest_sha256": root_sha256,
        "formal_result_root_manifest_byte_count": len(root_manifest),
        "streamed_preknown_bindings_sha256": hashlib.sha256(
            _canonical(preknown)
        ).hexdigest(),
        "formal_result_input_manifest_sha256": bindings.input_manifest_sha256,
        "formal_result_report_contract_sha256": (
            bindings.formal_report_contract_sha256
        ),
        "formal_result_descriptor_inventory_sha256": descriptor_inventory,
        "formal_result_root_descriptor_inventory_sha256": hashlib.sha256(
            _canonical(
                {
                    "root_manifest_sha256": root_sha256,
                    "report_family_object_descriptors": descriptor_records,
                }
            )
        ).hexdigest(),
        "formal_result_object_store_key_inventory_sha256": hashlib.sha256(
            _canonical(key_inventory)
        ).hexdigest(),
        "formal_result_family_payload_inventory_sha256": hashlib.sha256(
            _canonical(payload_inventory)
        ).hexdigest(),
        "formal_result_family_object_count": len(family_payloads),
        "formal_result_total_uncompressed_byte_count": sum(
            descriptor.uncompressed_byte_count for descriptor in descriptors
        ),
        "formal_result_total_compressed_byte_count": sum(
            len(payload) for _suffix, payload in family_payloads
        ),
        "formal_result_summary_read_count": FORMAL_RESULT_SUMMARY_READ_COUNT,
        "formal_result_family_object_read_count": len(family_payloads),
        "formal_result_transport_call_count": (
            FORMAL_RESULT_SUMMARY_READ_COUNT + len(family_payloads)
        ),
        "formal_result_all_family_objects_content_authenticated": True,
    }


def _mint_summary_result_receipt_authority_impl(
    *,
    record: dict[str, object],
    pairs: tuple[tuple[str, str], ...],
    permit: FormalQcResultReadPermit,
    result_authority: FormalQcResultReadAuthority,
    result_gate: FormalQcResultGateCandidate,
    terminal: FormalQcTerminalStatusReceipt,
    launch: FormalQcLaunchReceipt,
    candidate: FormalRunCandidate,
    reviewed_authority: ReviewedFormalRunAuthority,
    root_manifest: bytes,
    family_payloads: tuple[tuple[str, bytes], ...],
    bindings: object,
    descriptors: tuple[object, ...],
    _authority_register: Callable[..., object],
) -> FormalQcSummaryResultReadReceipt:
    canonical_record = _canonical(record)
    receipt_id, digest = _identified_receipt(
        "arv2-formal-qc-result-read-", RESULT_READ_RECEIPT_SCHEMA, record
    )
    value = FormalQcSummaryResultReadReceipt(
        receipt_id=receipt_id,
        receipt_sha256=digest,
        summary_pairs=pairs,
        **{
            key: item
            for key, item in record.items()
            if key not in {"summary_pairs", "result_read_ledger_path"}
        },
        result_read_ledger_path=permit.ledger_path,
        _result_read_permit=permit,
        _formal_result_root_manifest=root_manifest,
        _formal_result_family_payloads=family_payloads,
        _formal_result_bindings=bindings,
        _formal_result_family_descriptors=descriptors,
    )
    return _authority_register(
        value,
        (
            pairs,
            _summary_pairs_topology(pairs),
            result_authority,
            result_gate,
            terminal,
            launch,
            permit,
            candidate,
            reviewed_authority,
            canonical_record,
            root_manifest,
            family_payloads,
            bindings,
            descriptors,
            _formal_result_package_topology(
                root_manifest, family_payloads, bindings, descriptors
            ),
        ),
    )


def _mint_completed_summary_read_receipt_impl(
    *,
    pairs: tuple[tuple[str, str], ...],
    permit: FormalQcResultReadPermit,
    result_authority: FormalQcResultReadAuthority,
    result_gate: FormalQcResultGateCandidate,
    terminal: FormalQcTerminalStatusReceipt,
    launch: FormalQcLaunchReceipt,
    candidate: FormalRunCandidate,
    reviewed_authority: ReviewedFormalRunAuthority,
    _authority_mint_summary: Callable[..., FormalQcSummaryResultReadReceipt],
    root_manifest: bytes = b"",
    family_payloads: tuple[tuple[str, bytes], ...] = (),
    bindings: object = None,
    descriptors: tuple[object, ...] = (),
) -> FormalQcSummaryResultReadReceipt:
    pairs_hash = hashlib.sha256(
        _canonical([list(item) for item in pairs])
    ).hexdigest()
    record = {
        "result_authority_id": result_authority.authority_id,
        "result_authority_sha256": result_authority.authority_sha256,
        "result_read_permit_id": permit.permit_id,
        "result_read_permit_sha256": permit.permit_sha256,
        "external_pin_id": result_authority.external_pin_id,
        "external_pin_sha256": result_authority.external_pin_sha256,
        "result_read_ledger_path": str(permit.ledger_path),
        "terminal_receipt_id": terminal.receipt_id,
        "terminal_receipt_sha256": terminal.receipt_sha256,
        "launch_receipt_id": launch.receipt_id,
        "launch_receipt_sha256": launch.receipt_sha256,
        "project_id": launch.project_id,
        "backtest_id": launch.backtest_id,
        "terminal_status": terminal.terminal_status,
        "summary_pairs": [list(item) for item in pairs],
        "summary_pairs_sha256": pairs_hash,
        "result_read_count": 1,
        "process_authenticated_qc_read": True,
        "full_result_envelope_received_and_json_parsed": True,
        "standard_statistic_values_selected_or_inspected": False,
        "logs_charts_orders_trades_values_selected_or_inspected": False,
        "unrelated_values_retained_in_receipt_or_exported": False,
        **_formal_result_receipt_attestation(
            root_manifest=root_manifest,
            family_payloads=family_payloads,
            bindings=bindings,
            descriptors=descriptors,
            project_id=launch.project_id,
        ),
    }
    return _authority_mint_summary(
        record=record,
        pairs=pairs,
        permit=permit,
        result_authority=result_authority,
        result_gate=result_gate,
        terminal=terminal,
        launch=launch,
        candidate=candidate,
        reviewed_authority=reviewed_authority,
        root_manifest=root_manifest,
        family_payloads=family_payloads,
        bindings=bindings,
        descriptors=descriptors,
    )


_SUMMARY_RESULT_CONTRACT_FIELDS = frozenset(
    {
        "aggregate_result_schema",
        "summary_receipt_schema",
        "cloud_evaluation_output_schema",
        "report_family_object_reference_schema",
        "meta_name",
        "chunk_prefix",
        "chunk_name_width",
        "max_payload_byte_count",
        "max_chunk_count",
        "max_chunk_characters",
        "fold_horizon_axis_count",
        "source_view_fold_horizon_axis_count",
        "raw_market_or_outcome_rows_in_summary_forbidden",
        "report_family_object_count",
        "report_family_object_key_suffix_prefix",
        "report_family_object_full_key_derivation",
        "report_family_object_uncompressed_byte_ceiling",
        "report_family_object_compressed_byte_ceiling",
        "report_family_object_total_uncompressed_byte_ceiling",
        "report_family_object_total_compressed_byte_ceiling",
        "object_store_write_once_existing_identical_bytes_only",
        "object_store_save_then_reopen_and_rehash_required",
        "root_summary_published_only_after_all_family_reopens",
        "family_objects_required_for_result_read",
    }
)
_SUMMARY_RESULT_META_FIELDS = frozenset(
    {
        "schema", "evaluation_id", "input_manifest_sha256",
        "cloud_evaluator_sha256", "root_manifest_schema",
        "root_manifest_sha256", "root_manifest_byte_count",
        "compressed_root_sha256", "compressed_root_byte_count", "encoding",
        "chunk_count", "chunks", "report_family_object_reference_schema",
        "report_family_object_count", "report_family_object_inventory_sha256",
        "report_family_object_total_uncompressed_byte_count",
        "report_family_object_total_compressed_byte_count",
        "report_family_object_full_key_prefix",
        "object_store_write_once_existing_identical_bytes_only",
        "object_store_save_then_reopen_and_rehash_complete",
        "object_store_reopened_object_count",
        "raw_report_family_rows_in_summary", "fold_horizon_axis_count",
        "source_view_fold_horizon_axis_count", "failed_arm_omission_count",
        "orders_placed",
    }
)
_SUMMARY_RESULT_CHUNK_FIELDS = frozenset(
    {"name", "ordinal", "character_count", "sha256"}
)
def _require_summary_result_contract(value: object) -> dict[str, int]:
    if type(value) is not dict or set(value) != _SUMMARY_RESULT_CONTRACT_FIELDS:
        raise FormalQcSubmissionError("summary result contract fields changed")
    if (
        value["aggregate_result_schema"] != AGGREGATE_RESULT_SCHEMA
        or value["summary_receipt_schema"] != SUMMARY_RECEIPT_SCHEMA
        or value["cloud_evaluation_output_schema"]
        != FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA
        or value["report_family_object_reference_schema"]
        != REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA
        or value["meta_name"] != SUMMARY_META_NAME
        or value["chunk_prefix"] != SUMMARY_CHUNK_PREFIX
        or value["chunk_name_width"] != SUMMARY_CHUNK_NAME_WIDTH
        or type(value["max_payload_byte_count"]) is not int
        or not 0
        < value["max_payload_byte_count"]
        <= ABSOLUTE_MAX_SUMMARY_PAYLOAD_BYTES
        or type(value["max_chunk_count"]) is not int
        or not 0 < value["max_chunk_count"] <= ABSOLUTE_MAX_SUMMARY_CHUNKS
        or type(value["max_chunk_characters"]) is not int
        or not 0
        < value["max_chunk_characters"]
        <= ABSOLUTE_MAX_SUMMARY_CHUNK_CHARACTERS
        or value["fold_horizon_axis_count"] != 24
        or value["source_view_fold_horizon_axis_count"] != 48
        or value["raw_market_or_outcome_rows_in_summary_forbidden"] is not True
        or value["report_family_object_count"]
        != FORMAL_RESULT_FAMILY_OBJECT_COUNT
        or value["report_family_object_key_suffix_prefix"]
        != REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX
        or value["report_family_object_full_key_derivation"]
        != "str(project_id)+'/'+authenticated_object_store_key_suffix"
        or value["report_family_object_uncompressed_byte_ceiling"]
        != MAX_FORMAL_RESULT_FAMILY_OBJECT_UNCOMPRESSED_BYTES
        or value["report_family_object_compressed_byte_ceiling"]
        != MAX_FORMAL_RESULT_FAMILY_OBJECT_COMPRESSED_BYTES
        or value["report_family_object_total_uncompressed_byte_ceiling"]
        != MAX_FORMAL_RESULT_TOTAL_UNCOMPRESSED_BYTES
        or value["report_family_object_total_compressed_byte_ceiling"]
        != MAX_FORMAL_RESULT_TOTAL_COMPRESSED_BYTES
        or value["object_store_write_once_existing_identical_bytes_only"] is not True
        or value["object_store_save_then_reopen_and_rehash_required"] is not True
        or value["root_summary_published_only_after_all_family_reopens"] is not True
        or value["family_objects_required_for_result_read"] is not True
    ):
        raise FormalQcSubmissionError("summary result contract changed")
    return {
        "chunk_name_width": value["chunk_name_width"],
        "max_payload_byte_count": value["max_payload_byte_count"],
        "max_chunk_count": value["max_chunk_count"],
        "max_chunk_characters": value["max_chunk_characters"],
    }


def _extract_arv2_summary_pairs(
    value: object, *, launch: FormalQcLaunchReceipt,
    maximum_chunk_count: int, maximum_chunk_characters: int,
    chunk_name_width: int = SUMMARY_CHUNK_NAME_WIDTH,
    maximum_payload_byte_count: int = ABSOLUTE_MAX_SUMMARY_PAYLOAD_BYTES,
) -> tuple[tuple[str, str], ...]:
    if type(value) is not dict or value.get("success") is not True:
        raise FormalQcSubmissionError("backtests/read response changed")
    backtest = value.get("backtest")
    if type(backtest) is not dict:
        raise FormalQcSubmissionError("backtests/read omitted its backtest")
    # The transport has decoded/materialized the bounded envelope.  From that
    # envelope this gate selects only run identity/status and named ARV2
    # summary values; it neither selects nor retains unrelated values.
    if (
        backtest.get("backtestId") != launch.backtest_id
        or backtest.get("projectId") != launch.project_id
        or backtest.get("name") != launch.backtest_name
        or backtest.get("status") != "Completed."
    ):
        raise FormalQcSubmissionError("backtests/read returned another run")
    statistics = backtest.get("statistics")
    if type(statistics) is not dict:
        raise FormalQcSubmissionError("backtests/read omitted summary statistics")
    names = tuple(
        sorted(
            key for key in statistics.keys()
            if type(key) is str
            and (key == SUMMARY_META_NAME or key.startswith(SUMMARY_CHUNK_PREFIX))
        )
    )
    if SUMMARY_META_NAME not in names:
        raise FormalQcSubmissionError("ARV2 summary metadata is absent")
    chunk_names = tuple(name for name in names if name != SUMMARY_META_NAME)
    expected_chunk_names = tuple(
        SUMMARY_CHUNK_PREFIX + str(index).zfill(chunk_name_width)
        for index in range(len(chunk_names))
    )
    if (
        chunk_names != expected_chunk_names
        or not chunk_names
        or len(chunk_names) > maximum_chunk_count
    ):
        raise FormalQcSubmissionError("ARV2 summary chunk inventory changed")
    pairs = []
    for name in names:
        value_at_name = statistics[name]
        if (
            type(value_at_name) is not str
            or not value_at_name
            or len(value_at_name) > maximum_chunk_characters
            or re.fullmatch(r"[A-Za-z0-9_=-]+", value_at_name) is None
        ):
            raise FormalQcSubmissionError("ARV2 summary statistic value changed")
        pairs.append((name, value_at_name))
    encoded = "".join(
        value_at_name for name, value_at_name in pairs
        if name.startswith(SUMMARY_CHUNK_PREFIX) and name != SUMMARY_META_NAME
    )
    # Reject by an exact pre-decode upper bound before allocating decoded
    # bytes, then validate the URL-safe base64 and its reviewed compressed
    # payload capacity.  The evaluator independently bounds decompression.
    if len(encoded) > 4 * ((maximum_payload_byte_count + 2) // 3):
        raise FormalQcSubmissionError(
            "ARV2 summary compressed payload exceeded reviewed capacity"
        )
    try:
        compressed = base64.b64decode(
            encoded.encode("ascii"), altchars=b"-_", validate=True
        )
    except (UnicodeError, ValueError) as exc:
        raise FormalQcSubmissionError(
            "ARV2 summary chunks are not canonical URL-safe base64"
        ) from exc
    if (
        not compressed
        or len(compressed) > maximum_payload_byte_count
        or base64.urlsafe_b64encode(compressed).decode("ascii") != encoded
    ):
        raise FormalQcSubmissionError(
            "ARV2 summary compressed payload changed or exceeded reviewed capacity"
        )
    return tuple(pairs)


def _exact_urlsafe_base64(value: object, name: str) -> bytes:
    if type(value) is not str or not value:
        raise FormalQcSubmissionError(f"{name} is not nonempty base64 text")
    try:
        payload = base64.b64decode(
            value.encode("ascii"), altchars=b"-_", validate=True
        )
    except (UnicodeError, ValueError) as exc:
        raise FormalQcSubmissionError(
            f"{name} is not canonical URL-safe base64"
        ) from exc
    if base64.urlsafe_b64encode(payload).decode("ascii") != value:
        raise FormalQcSubmissionError(
            f"{name} is not canonical URL-safe base64"
        )
    return payload


def _reconstruct_formal_result_root(
    pairs: tuple[tuple[str, str], ...], *,
    result_contract: Mapping[str, int],
) -> tuple[bytes, dict[str, object]]:
    """Reconstruct and authenticate the bounded summary root before 26 reads."""

    if type(pairs) is not tuple or type(result_contract) is not dict:
        raise FormalQcSubmissionError("formal result root input changed")
    selected = dict(pairs)
    if len(selected) != len(pairs) or SUMMARY_META_NAME not in selected:
        raise FormalQcSubmissionError("ARV2 summary inventory changed")
    meta = _json_object(
        _exact_urlsafe_base64(
            selected[SUMMARY_META_NAME], "ARV2 summary metadata"
        ),
        "ARV2 summary metadata",
    )
    chunks = meta.get("chunks")
    if (
        set(meta) != _SUMMARY_RESULT_META_FIELDS
        or meta.get("schema") != SUMMARY_RECEIPT_SCHEMA
        or meta.get("evaluation_id") != EVALUATION_ID
        or meta.get("root_manifest_schema") != AGGREGATE_RESULT_SCHEMA
        or meta.get("encoding")
        != "gzip-mtime-zero-os-255-plus-urlsafe-base64-no-linebreaks"
        or meta.get("report_family_object_reference_schema")
        != "arv2-formal-report-family-object-reference-v1"
        or meta.get("report_family_object_count")
        != FORMAL_RESULT_FAMILY_READ_COUNT
        or meta.get("object_store_write_once_existing_identical_bytes_only")
        is not True
        or meta.get("object_store_save_then_reopen_and_rehash_complete")
        is not True
        or meta.get("object_store_reopened_object_count")
        != FORMAL_RESULT_FAMILY_READ_COUNT
        or meta.get("raw_report_family_rows_in_summary") is not False
        or meta.get("fold_horizon_axis_count") != 24
        or meta.get("source_view_fold_horizon_axis_count") != 48
        or meta.get("failed_arm_omission_count") != 0
        or meta.get("orders_placed") != 0
        or type(chunks) is not list
        or type(meta.get("chunk_count")) is not int
        or meta["chunk_count"] != len(chunks)
        or not chunks
        or len(chunks) > result_contract["max_chunk_count"]
    ):
        raise FormalQcSubmissionError("ARV2 summary metadata changed")
    width = result_contract["chunk_name_width"]
    names = tuple(
        SUMMARY_CHUNK_PREFIX + str(index).zfill(width)
        for index in range(len(chunks))
    )
    if set(selected) != {SUMMARY_META_NAME, *names}:
        raise FormalQcSubmissionError("ARV2 summary chunk census changed")
    encoded_parts: list[str] = []
    for ordinal, raw in enumerate(chunks):
        name = names[ordinal]
        text = selected[name]
        if (
            type(raw) is not dict
            or set(raw) != _SUMMARY_RESULT_CHUNK_FIELDS
            or raw.get("name") != name
            or raw.get("ordinal") != ordinal
            or raw.get("character_count") != len(text)
            or raw.get("sha256")
            != hashlib.sha256(text.encode("ascii")).hexdigest()
        ):
            raise FormalQcSubmissionError("ARV2 summary chunk changed")
        encoded_parts.append(text)
    compressed = _exact_urlsafe_base64(
        "".join(encoded_parts), "ARV2 summary root"
    )
    expected_compressed_count = meta.get("compressed_root_byte_count")
    expected_root_count = meta.get("root_manifest_byte_count")
    if (
        type(expected_compressed_count) is not int
        or expected_compressed_count != len(compressed)
        or not 0 < len(compressed) <= result_contract["max_payload_byte_count"]
        or len(compressed) > FORMAL_RESULT_ROOT_MAXIMUM_COMPRESSED_BYTE_COUNT
        or _sha(meta.get("compressed_root_sha256"), "summary root hash")
        != hashlib.sha256(compressed).hexdigest()
        or type(expected_root_count) is not int
        or not 0 < expected_root_count <= FORMAL_RESULT_ROOT_MAXIMUM_BYTE_COUNT
        or type(meta.get("report_family_object_total_uncompressed_byte_count"))
        is not int
        or not 0
        < meta["report_family_object_total_uncompressed_byte_count"]
        <= FORMAL_RESULT_FAMILY_TOTAL_MAXIMUM_UNCOMPRESSED_BYTE_COUNT
        or type(meta.get("report_family_object_total_compressed_byte_count"))
        is not int
        or not 0
        < meta["report_family_object_total_compressed_byte_count"]
        <= MAX_FORMAL_RESULT_FAMILY_TOTAL_BYTES
        or type(meta.get("report_family_object_full_key_prefix")) is not str
        or not meta["report_family_object_full_key_prefix"]
        or _sha(
            meta.get("report_family_object_inventory_sha256"),
            "summary family inventory hash",
        )
        != meta["report_family_object_inventory_sha256"]
        or len(compressed) < 18
        or compressed[:4] != b"\x1f\x8b\x08\x00"
        or compressed[4:8] != b"\x00\x00\x00\x00"
        or compressed[8] != 2
        or compressed[9] != 255
    ):
        raise FormalQcSubmissionError("ARV2 summary root identity changed")
    try:
        decoder = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
        root_manifest = decoder.decompress(
            compressed, FORMAL_RESULT_ROOT_MAXIMUM_BYTE_COUNT + 1
        )
        if decoder.unconsumed_tail:
            raise FormalQcSubmissionError(
                "ARV2 summary root exceeded its decompression bound"
            )
        root_manifest += decoder.flush(
            FORMAL_RESULT_ROOT_MAXIMUM_BYTE_COUNT + 1 - len(root_manifest)
        )
    except (ValueError, zlib.error) as exc:
        raise FormalQcSubmissionError(
            "ARV2 summary root is not canonical bounded gzip"
        ) from exc
    if (
        len(root_manifest) != expected_root_count
        or decoder.eof is not True
        or decoder.unused_data
        or decoder.unconsumed_tail
        or _sha(meta.get("root_manifest_sha256"), "formal result root hash")
        != hashlib.sha256(root_manifest).hexdigest()
    ):
        raise FormalQcSubmissionError("ARV2 summary root content changed")
    return root_manifest, meta


def _formal_result_family_object_payload(
    response: object, *, object_store_key: str,
) -> bytes:
    if type(response) is not dict or not set(response).issubset(
        {"success", "errors", "messages", "object"}
    ):
        raise FormalQcSubmissionError(
            "formal result-family Object Store envelope changed"
        )
    item = response.get("object")
    if (
        response.get("success") is not True
        or type(item) is not dict
        or set(item) != {"key", "objectData"}
        or item.get("key") != object_store_key
        or type(item.get("objectData")) is not str
    ):
        raise FormalQcSubmissionError(
            "formal result-family object envelope changed"
        )
    encoded = item["objectData"]
    try:
        payload = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeError, ValueError) as exc:
        raise FormalQcSubmissionError(
            "formal result-family object is not canonical base64"
        ) from exc
    if (
        not 0 < len(payload) <= MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES
        or base64.b64encode(payload).decode("ascii") != encoded
    ):
        raise FormalQcSubmissionError(
            "formal result-family object exceeded its byte bound"
        )
    return payload


def _read_streamed_formal_result_family_objects(
    *, root_manifest: bytes, root_metadata: Mapping[str, object],
    submitted: StreamedFormalSubmissionAdapterBridge,
    launch: FormalQcLaunchReceipt, client: FormalQcTransport,
    transport_capability_minter: Callable[..., object],
) -> tuple[
    object, tuple[object, ...], tuple[tuple[str, bytes], ...]
]:
    """Validate the root, read exactly its 26 objects, then validate all."""

    from .formal_cloud_evaluator import (
        FormalCloudEvaluationError,
        REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX,
        REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA,
        derive_formal_cloud_evaluation_family_object_read_plan,
        derive_streamed_formal_evaluation_preknown_bindings_record,
        require_formal_cloud_evaluation_aggregate_bytes,
        require_formal_cloud_evaluation_family_object_payload,
    )

    manifest = _json_object(
        submitted.runtime_bridge.input_manifest_payload,
        "streamed input manifest",
    )
    try:
        preknown = derive_streamed_formal_evaluation_preknown_bindings_record(
            manifest
        )
        bindings, descriptors = (
            derive_formal_cloud_evaluation_family_object_read_plan(
                root_manifest, expected_preknown_bindings=preknown
            )
        )
    except (FormalCloudEvaluationError, TypeError, ValueError) as exc:
        raise FormalQcSubmissionError(
            "formal result root did not authenticate its exact submission"
        ) from exc
    descriptor_records = [descriptor.to_record() for descriptor in descriptors]
    descriptor_root = hashlib.sha256(
        _canonical(descriptor_records)
    ).hexdigest()
    total_uncompressed = sum(
        descriptor.uncompressed_byte_count for descriptor in descriptors
    )
    total_compressed = sum(
        descriptor.compressed_byte_count for descriptor in descriptors
    )
    if (
        len(descriptors) != FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT
        or root_metadata.get("input_manifest_sha256")
        != bindings.input_manifest_sha256
        or root_metadata.get("cloud_evaluator_sha256")
        != bindings.evaluator_source_closure_sha256
        or root_metadata.get("root_manifest_sha256")
        != hashlib.sha256(root_manifest).hexdigest()
        or root_metadata.get("root_manifest_byte_count") != len(root_manifest)
        or root_metadata.get("report_family_object_reference_schema")
        != REPORT_FAMILY_OBJECT_REFERENCE_SCHEMA
        or root_metadata.get("report_family_object_count")
        != FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT
        or root_metadata.get("report_family_object_inventory_sha256")
        != descriptor_root
        or root_metadata.get(
            "report_family_object_total_uncompressed_byte_count"
        )
        != total_uncompressed
        or root_metadata.get(
            "report_family_object_total_compressed_byte_count"
        )
        != total_compressed
        or root_metadata.get("report_family_object_full_key_prefix")
        != f"{launch.project_id}/{REPORT_FAMILY_OBJECT_KEY_SUFFIX_PREFIX}"
        or root_metadata.get(
            "object_store_write_once_existing_identical_bytes_only"
        )
        is not True
        or root_metadata.get(
            "object_store_save_then_reopen_and_rehash_complete"
        )
        is not True
        or root_metadata.get("object_store_reopened_object_count")
        != FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT
        or root_metadata.get("raw_report_family_rows_in_summary") is not False
    ):
        raise FormalQcSubmissionError(
            "formal result summary metadata escaped the authenticated root"
        )
    keys = tuple(
        f"{launch.project_id}/{descriptor.object_store_key_suffix}"
        for descriptor in descriptors
    )
    if any(
        key
        != FORMAL_RESULT_FAMILY_KEY_FORMULA.format(
            project_id=launch.project_id,
            input_manifest_sha256=bindings.input_manifest_sha256,
            ordinal=descriptor.ordinal,
            compressed_sha256=descriptor.compressed_sha256,
        )
        for descriptor, key in zip(descriptors, keys, strict=True)
    ):
        raise FormalQcSubmissionError(
            "formal result-family Object Store key formula changed"
        )
    capability = transport_capability_minter(
        transport=client,
        scope="result_family_read",
        binding_record={
            "schema": RESULT_FAMILY_READ_CAPABILITY_SCHEMA,
            "project_id": launch.project_id,
            "organization_id": submitted.plan.organization_id,
            "descriptor_root_sha256": descriptor_root,
            "object_store_keys": list(keys),
            "root_manifest_sha256": hashlib.sha256(root_manifest).hexdigest(),
            "result_read_receipt_pending": True,
            "result_disposition_authority": False,
            "deployment_authority": False,
            "orders_authority": False,
            "trading_authority": False,
        },
        call_budget={
            "object/read": FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT
        },
    )
    family_payloads: list[tuple[str, bytes]] = []
    total = 0
    for descriptor, key in zip(descriptors, keys, strict=True):
        raw = _transport_call(
            client,
            capability,
            "_read_formal_result_family_object_bounded",
            launch.project_id,
            submitted.plan.organization_id,
            key,
        )
        payload = _formal_result_family_object_payload(
            raw, object_store_key=key
        )
        total += len(payload)
        if total > MAX_FORMAL_RESULT_FAMILY_TOTAL_BYTES:
            raise FormalQcSubmissionError(
                "formal result-family total exceeded its byte bound"
            )
        try:
            require_formal_cloud_evaluation_family_object_payload(
                root_manifest,
                expected_bindings=bindings,
                descriptor=descriptor,
                payload=payload,
            )
        except (FormalCloudEvaluationError, TypeError, ValueError) as exc:
            raise FormalQcSubmissionError(
                "formal result-family object failed content authentication"
            ) from exc
        family_payloads.append((descriptor.object_store_key_suffix, payload))
    frozen_payloads = tuple(family_payloads)
    if (
        len(frozen_payloads) != FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT
        or total != sum(
            descriptor.compressed_byte_count for descriptor in descriptors
        )
    ):
        raise FormalQcSubmissionError(
            "formal result-family read census changed"
        )
    try:
        require_formal_cloud_evaluation_aggregate_bytes(
            root_manifest,
            expected_bindings=bindings,
            report_family_object_payloads=dict(frozen_payloads),
        )
    except (FormalCloudEvaluationError, TypeError, ValueError) as exc:
        raise FormalQcSubmissionError(
            "formal result-family aggregate failed final authentication"
        ) from exc
    return bindings, descriptors, frozen_payloads


def _read_formal_qc_summary_result_once_impl(
    *, result_authority: FormalQcResultReadAuthority,
    result_gate: FormalQcResultGateCandidate,
    candidate: FormalRunCandidate,
    reviewed_authority: ReviewedFormalRunAuthority,
    terminal: FormalQcTerminalStatusReceipt, launch: FormalQcLaunchReceipt,
    claim: FormalLookClaim, submission_permit: FormalSubmissionPermit,
    plan: FormalQcSubmissionPlan, client: FormalQcTransport,
    result_read_started_at_utc: str,
    _authority_mint_completed: Callable[
        ..., FormalQcSummaryResultReadReceipt
    ],
    _transport_capability_minter: Callable[..., object],
) -> FormalQcSummaryResultReadReceipt:
    _require_legacy_materialized_submission_retired()
    _require_non_self_mintable_result_read_trust_root(
        result_authority._owner_signature,
        result_authority._receipt_bytes,
    )
    require_formal_qc_result_read_authority(
        value=result_authority,
        gate=result_gate,
        launch=launch,
        terminal=terminal,
        candidate=candidate,
        reviewed_authority=reviewed_authority,
    )
    require_formal_qc_launch_receipt(
        value=launch, permit=submission_permit, plan=plan
    )
    require_formal_qc_terminal_status_receipt(
        terminal=terminal,
        launch=launch,
        plan=plan,
        permit=submission_permit,
        candidate=candidate,
        authority=reviewed_authority,
        claim=claim,
    )
    _require_concrete_transport(client)
    if (
        result_authority.backtest_id != launch.backtest_id
        or result_authority.terminal_receipt_id != terminal.receipt_id
        or terminal.terminal_status != "Completed."
        or result_authority.candidate_id != candidate.candidate_id
        or result_authority.reviewed_authority_id != reviewed_authority.authority_id
        or plan.candidate_id != candidate.candidate_id
        or plan.authority_id != reviewed_authority.authority_id
    ):
        raise FormalQcSubmissionError("separate exact result-read authority is required")
    manifest_entry = next(
        item for item in plan.upload_bundle.entries if item.role == "input_manifest"
    )
    result_contract = _require_summary_result_contract(
        _json_object(manifest_entry.payload, "input manifest").get(
            "summary_result_contract"
        )
    )
    # All validation and the final live-source check precede the durable
    # one-use transition.  Its return is immediately followed by the sole
    # network read; no callback or filesystem check is interposed.
    verify_formal_qc_host_closure_live(
        plan.execution_authority.host_code_closure
    )
    permit = _begin_formal_qc_result_read_once(
        result_authority=result_authority,
        result_read_started_at_utc=result_read_started_at_utc,
    )
    try:
        transport_capability = _transport_capability_minter(
            transport=client,
            scope="result_read",
            binding_record={
                "schema": "arv2-formal-qc-result-read-transport-capability-v1",
                "candidate_sha256": candidate.candidate_sha256,
                "reviewed_authority_sha256": reviewed_authority.authority_sha256,
                "result_authority_sha256": result_authority.authority_sha256,
                "result_read_permit_sha256": permit.permit_sha256,
                "launch_receipt_sha256": launch.receipt_sha256,
            },
            call_budget={"backtests/read": 1},
        )
        raw = _transport_call(
            client, transport_capability, "_read_backtest_result",
            launch.project_id, launch.backtest_id
        )
        pairs = _extract_arv2_summary_pairs(
            raw, launch=launch,
            maximum_chunk_count=result_contract["max_chunk_count"],
            maximum_chunk_characters=result_contract["max_chunk_characters"],
            chunk_name_width=result_contract["chunk_name_width"],
            maximum_payload_byte_count=result_contract[
                "max_payload_byte_count"
            ],
        )
        return _authority_mint_completed(
            pairs=pairs,
            permit=permit,
            result_authority=result_authority,
            result_gate=result_gate,
            terminal=terminal,
            launch=launch,
            candidate=candidate,
            reviewed_authority=reviewed_authority,
        )
    except Exception as exc:
        raise FormalQcSubmissionLocked(
            "result_read",
            permit.permit_id,
            type(exc).__name__,
            outcome_class=_failure_outcome_class(exc),
        ) from exc


def _streamed_summary_result_contract(
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
) -> dict[str, int]:
    submitted = require_streamed_formal_submission_adapter_bridge(
        submission_bridge
    )
    runtime_bridge = submitted.runtime_bridge
    payload = runtime_bridge.input_manifest_payload
    if (
        hashlib.sha256(payload).hexdigest()
        != runtime_bridge.input_manifest.content_sha256
        or len(payload) != runtime_bridge.input_manifest.byte_count
    ):
        raise FormalQcSubmissionError("streamed input manifest changed")
    manifest = _json_object(payload, "streamed input manifest")
    return _require_summary_result_contract(
        manifest.get("summary_result_contract")
    )


def _read_streamed_formal_qc_summary_result_once_impl(
    *,
    result_authority: FormalQcResultReadAuthority,
    result_gate: FormalQcResultGateCandidate,
    submission_bridge: StreamedFormalSubmissionAdapterBridge,
    terminal: FormalQcTerminalStatusReceipt,
    launch: FormalQcLaunchReceipt,
    claim: FormalLookClaim,
    submission_permit: FormalSubmissionPermit,
    client: FormalQcTransport,
    result_read_started_at_utc: str,
    _authority_mint_completed: Callable[
        ..., FormalQcSummaryResultReadReceipt
    ],
    _transport_capability_minter: Callable[..., object],
) -> FormalQcSummaryResultReadReceipt:
    """Perform the separately authorized selected-summary-only read."""

    submitted = require_streamed_formal_submission_adapter_bridge(
        submission_bridge
    )
    candidate = submitted.formal_run_candidate
    reviewed_authority = submitted.reviewed_authority
    _require_non_self_mintable_result_read_trust_root(
        result_authority._owner_signature,
        result_authority._receipt_bytes,
    )
    require_streamed_formal_qc_result_gate_candidate(
        value=result_gate,
        terminal=terminal,
        launch=launch,
        submission_bridge=submitted,
        claim=claim,
        permit=submission_permit,
    )
    require_formal_qc_result_read_authority(
        value=result_authority,
        gate=result_gate,
        launch=launch,
        terminal=terminal,
        candidate=candidate,
        reviewed_authority=reviewed_authority,
    )
    require_streamed_formal_qc_launch_receipt(
        value=launch, permit=submission_permit, plan=submitted.plan
    )
    require_streamed_formal_qc_terminal_status_receipt(
        terminal=terminal,
        submission_bridge=submitted,
        claim=claim,
        permit=submission_permit,
        launch=launch,
    )
    _require_concrete_transport(client)
    if (
        result_authority.backtest_id != launch.backtest_id
        or result_authority.terminal_receipt_id != terminal.receipt_id
        or terminal.terminal_status != "Completed."
        or result_authority.candidate_id != candidate.candidate_id
        or result_authority.reviewed_authority_id
        != reviewed_authority.authority_id
        or submitted.plan.candidate_id != candidate.candidate_id
        or submitted.plan.reviewed_authority_id
        != reviewed_authority.authority_id
        or result_gate.runtime_bridge_id != submitted.runtime_bridge.bridge_id
        or result_gate.runtime_bridge_sha256
        != submitted.runtime_bridge.bridge_sha256
        or result_gate.submission_adapter_bridge_id != submitted.bridge_id
        or result_gate.submission_adapter_bridge_sha256
        != submitted.bridge_sha256
        or result_gate.authenticated_power_floor_id
        != submitted.authenticated_power_floor.binding_id
        or result_gate.authenticated_power_floor_sha256
        != submitted.authenticated_power_floor.binding_sha256
        or result_gate.economic_execution_binding_id
        != submitted.economic_execution.binding_id
        or result_gate.economic_execution_binding_sha256
        != submitted.economic_execution.binding_sha256
        or result_gate.economic_execution_definition_id
        != submitted.economic_execution.definition_id
        or result_gate.economic_execution_definition_sha256
        != submitted.economic_execution.definition_sha256
    ):
        raise FormalQcSubmissionError(
            "separate exact streamed result-read authority is required"
        )
    result_contract = _streamed_summary_result_contract(submitted)
    verify_formal_qc_host_closure_live(
        submitted.execution_authority.host_code_closure
    )
    _require_streamed_authenticated_power_floor(
        submitted.authenticated_power_floor, submitted.runtime_bridge
    )
    _require_streamed_economic_execution(
        submitted.economic_execution, submitted.runtime_bridge
    )
    _require_streamed_report_contract(
        submitted.report_contract, submitted.runtime_bridge
    )
    permit = _begin_formal_qc_result_read_once(
        result_authority=result_authority,
        result_read_started_at_utc=result_read_started_at_utc,
    )
    try:
        transport_capability = _transport_capability_minter(
            transport=client,
            scope="result_read",
            binding_record={
                "schema": (
                    "arv2-streamed-formal-qc-result-read-transport-"
                    "capability-v1"
                ),
                "candidate_sha256": candidate.candidate_sha256,
                "reviewed_authority_sha256": (
                    reviewed_authority.authority_sha256
                ),
                "runtime_bridge_sha256": submitted.runtime_bridge.bridge_sha256,
                "submission_adapter_bridge_sha256": submitted.bridge_sha256,
                "authenticated_power_floor_sha256": (
                    submitted.authenticated_power_floor.binding_sha256
                ),
                "economic_execution_binding_sha256": (
                    submitted.economic_execution.binding_sha256
                ),
                "economic_execution_definition_sha256": (
                    submitted.economic_execution.definition_sha256
                ),
                "formal_report_contract_sha256": (
                    submitted.report_contract.contract_sha256
                ),
                "formal_report_contract_artifact_sha256": (
                    submitted.report_contract.artifact_sha256
                ),
                "formal_report_contract_stock_bootstrap_seed_sha256": (
                    submitted.report_contract.stock_bootstrap_seed_sha256
                ),
                "result_authority_sha256": result_authority.authority_sha256,
                "result_read_permit_sha256": permit.permit_sha256,
                "launch_receipt_sha256": launch.receipt_sha256,
            },
            call_budget={"backtests/read": 1},
        )
        raw = _transport_call(
            client,
            transport_capability,
            "_read_backtest_result",
            launch.project_id,
            launch.backtest_id,
        )
        pairs = _extract_arv2_summary_pairs(
            raw,
            launch=launch,
            maximum_chunk_count=result_contract["max_chunk_count"],
            maximum_chunk_characters=result_contract[
                "max_chunk_characters"
            ],
            chunk_name_width=result_contract["chunk_name_width"],
            maximum_payload_byte_count=result_contract[
                "max_payload_byte_count"
            ],
        )
        root_manifest, root_metadata = _reconstruct_formal_result_root(
            pairs, result_contract=result_contract
        )
        bindings, descriptors, family_payloads = (
            _read_streamed_formal_result_family_objects(
                root_manifest=root_manifest,
                root_metadata=root_metadata,
                submitted=submitted,
                launch=launch,
                client=client,
                transport_capability_minter=_transport_capability_minter,
            )
        )
        return _authority_mint_completed(
            pairs=pairs,
            permit=permit,
            result_authority=result_authority,
            result_gate=result_gate,
            terminal=terminal,
            launch=launch,
            candidate=candidate,
            reviewed_authority=reviewed_authority,
            root_manifest=root_manifest,
            family_payloads=family_payloads,
            bindings=bindings,
            descriptors=descriptors,
        )
    except Exception as exc:
        raise FormalQcSubmissionLocked(
            "streamed_result_read",
            permit.permit_id,
            type(exc).__name__,
            outcome_class=_failure_outcome_class(exc),
        ) from exc


def _require_formal_qc_summary_result_read_receipt_impl(
    value: FormalQcSummaryResultReadReceipt,
    *, result_authority: FormalQcResultReadAuthority,
    terminal: FormalQcTerminalStatusReceipt,
    launch: FormalQcLaunchReceipt,
    _authority_current: Callable[[object], tuple[object, ...] | None],
) -> FormalQcSummaryResultReadReceipt:
    if type(value) is not FormalQcSummaryResultReadReceipt:
        raise FormalQcSubmissionError("summary result-read receipt type changed")
    registered = _authority_current(value)
    if registered is None:
        raise FormalQcSubmissionError(
            "summary result-read receipt changed or lacks process-return authority"
        )
    if (
        registered[1] is not value.summary_pairs
        or registered[2] != _summary_pairs_topology(value.summary_pairs)
        or registered[3] is not result_authority
        or registered[5] is not terminal
        or registered[6] is not launch
        or registered[7] is not value._result_read_permit
        or registered[11] is not value._formal_result_root_manifest
        or registered[12] is not value._formal_result_family_payloads
        or registered[13] is not value._formal_result_bindings
        or registered[14] is not value._formal_result_family_descriptors
        or registered[15] != _formal_result_package_topology(
            value._formal_result_root_manifest,
            value._formal_result_family_payloads,
            value._formal_result_bindings,
            value._formal_result_family_descriptors,
        )
        or registered[16] != os.getpid()
    ):
        raise FormalQcSubmissionError(
            "summary result-read receipt authority or topology changed"
        )
    result_gate = registered[4]
    candidate = registered[8]
    reviewed_authority = registered[9]
    _require_launch_self_identity(launch)
    _require_terminal_self_identity(terminal)
    _require_result_gate_self_identity(result_gate)
    require_formal_qc_result_read_authority(
        value=result_authority,
        gate=result_gate,
        launch=launch,
        terminal=terminal,
        candidate=candidate,
        reviewed_authority=reviewed_authority,
    )
    record = {
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(value)
        if field.name not in {
            "receipt_id", "receipt_sha256", "_result_read_permit",
            "_formal_result_root_manifest", "_formal_result_family_payloads",
            "_formal_result_bindings", "_formal_result_family_descriptors",
        }
    }
    record["summary_pairs"] = [list(item) for item in value.summary_pairs]
    record["result_read_ledger_path"] = str(value.result_read_ledger_path)
    receipt_id, digest = _identified_receipt(
        "arv2-formal-qc-result-read-", RESULT_READ_RECEIPT_SCHEMA, record
    )
    attestation = _formal_result_receipt_attestation(
        root_manifest=value._formal_result_root_manifest,
        family_payloads=value._formal_result_family_payloads,
        bindings=value._formal_result_bindings,
        descriptors=value._formal_result_family_descriptors,
        project_id=value.project_id,
    )
    if (
        value.receipt_id != receipt_id
        or value.receipt_sha256 != digest
        or registered[10] != _canonical(record)
        or require_formal_qc_result_read_permit(
            value=value._result_read_permit,
            result_authority=result_authority,
        ) is not value._result_read_permit
        or value.result_read_permit_id != value._result_read_permit.permit_id
        or value.result_read_permit_sha256 != value._result_read_permit.permit_sha256
        or value.external_pin_id != result_authority.external_pin_id
        or value.external_pin_sha256 != result_authority.external_pin_sha256
        or value.result_read_ledger_path != result_authority.result_read_ledger_path
        or value.result_authority_id != result_authority.authority_id
        or value.result_authority_sha256 != result_authority.authority_sha256
        or value.terminal_receipt_id != terminal.receipt_id
        or value.terminal_receipt_sha256 != terminal.receipt_sha256
        or value.launch_receipt_id != launch.receipt_id
        or value.launch_receipt_sha256 != launch.receipt_sha256
        or value.backtest_id != launch.backtest_id
        or value.project_id != launch.project_id
        or value.terminal_status != terminal.terminal_status
        or value.result_read_count != 1
        or any(getattr(value, name) != expected for name, expected in attestation.items())
        or value.formal_result_family_object_count
        != result_authority.formal_result_family_object_read_count
        * int(result_authority.formal_result_family_package_required)
        or value.formal_result_summary_read_count
        != result_authority.formal_result_summary_read_count
        or value.formal_result_transport_call_count
        != (
            result_authority.formal_result_transport_call_count
            if result_authority.formal_result_family_package_required
            else FORMAL_RESULT_SUMMARY_READ_COUNT
        )
        or (
            result_authority.formal_result_family_package_required
            and value.formal_result_all_family_objects_content_authenticated
            is not True
        )
        or value.process_authenticated_qc_read is not True
        or value.full_result_envelope_received_and_json_parsed is not True
        or value.standard_statistic_values_selected_or_inspected is not False
        or value.logs_charts_orders_trades_values_selected_or_inspected is not False
        or value.unrelated_values_retained_in_receipt_or_exported is not False
        or hashlib.sha256(_canonical([list(item) for item in value.summary_pairs])).hexdigest()
        != value.summary_pairs_sha256
    ):
        raise FormalQcSubmissionError("summary result-read receipt changed")
    return value


def _bind_process_receipt_authorities(
    transport_capability_minter: Callable[..., object],
    binding_guard: Callable[[str], None],
    process_register_launch: Callable[..., object],
    process_current_launch: Callable[[object], tuple[object, ...] | None],
    process_register_terminal: Callable[..., object],
    process_current_terminal: Callable[[object], tuple[object, ...] | None],
    process_register_summary: Callable[..., object],
    process_current_summary: Callable[[object], tuple[object, ...] | None],
    launch_registration_implementation: Callable[..., FormalQcLaunchReceipt],
    launch_require_implementation: Callable[..., tuple[object, ...]],
    terminal_registration_implementation: Callable[
        ..., FormalQcTerminalStatusReceipt
    ],
    terminal_require_implementation: Callable[..., tuple[object, ...]],
    summary_mint_implementation: Callable[
        ..., FormalQcSummaryResultReadReceipt
    ],
    completed_mint_implementation: Callable[
        ..., FormalQcSummaryResultReadReceipt
    ],
    streamed_execute_implementation: Callable[
        ..., tuple[FormalSubmissionPermit, FormalQcLaunchReceipt]
    ],
    legacy_execute_implementation: Callable[
        ..., tuple[FormalSubmissionPermit, FormalQcLaunchReceipt]
    ],
    streamed_status_implementation: Callable[
        ..., FormalQcTerminalStatusReceipt
    ],
    legacy_status_implementation: Callable[..., FormalQcTerminalStatusReceipt],
    streamed_read_implementation: Callable[
        ..., FormalQcSummaryResultReadReceipt
    ],
    legacy_read_implementation: Callable[..., FormalQcSummaryResultReadReceipt],
    summary_require_implementation: Callable[
        ..., FormalQcSummaryResultReadReceipt
    ],
):
    """Bind minting only into the transport consumers that earned it."""

    def register_launch(
        value: FormalQcLaunchReceipt,
        *,
        permit: FormalSubmissionPermit,
        plan: FormalQcSubmissionPlan | StreamedFormalQcSubmissionPlan,
        streamed: bool,
    ) -> FormalQcLaunchReceipt:
        return launch_registration_implementation(
            value,
            permit=permit,
            plan=plan,
            streamed=streamed,
            _authority_register=process_register_launch,
        )

    def _require_launch_receipt_authority(
        value: FormalQcLaunchReceipt,
        *,
        permit: FormalSubmissionPermit | None = None,
        plan: FormalQcSubmissionPlan | StreamedFormalQcSubmissionPlan | None = None,
        streamed: bool | None = None,
    ) -> tuple[object, ...]:
        return launch_require_implementation(
            value,
            permit=permit,
            plan=plan,
            streamed=streamed,
            _authority_current=process_current_launch,
        )

    def register_terminal(
        value: FormalQcTerminalStatusReceipt,
        *,
        launch: FormalQcLaunchReceipt,
        permit: FormalSubmissionPermit,
        plan: FormalQcSubmissionPlan | StreamedFormalQcSubmissionPlan,
        streamed: bool,
        context: tuple[object, ...],
    ) -> FormalQcTerminalStatusReceipt:
        return terminal_registration_implementation(
            value,
            launch=launch,
            permit=permit,
            plan=plan,
            streamed=streamed,
            context=context,
            _authority_register=process_register_terminal,
        )

    def _require_terminal_status_receipt_authority(
        value: FormalQcTerminalStatusReceipt,
        *,
        launch: FormalQcLaunchReceipt | None = None,
        permit: FormalSubmissionPermit | None = None,
        plan: FormalQcSubmissionPlan | StreamedFormalQcSubmissionPlan | None = None,
        streamed: bool | None = None,
        context: tuple[object, ...] | None = None,
    ) -> tuple[object, ...]:
        return terminal_require_implementation(
            value,
            launch=launch,
            permit=permit,
            plan=plan,
            streamed=streamed,
            context=context,
            _authority_current=process_current_terminal,
        )

    def mint_summary(
        *,
        record: dict[str, object],
        pairs: tuple[tuple[str, str], ...],
        permit: FormalQcResultReadPermit,
        result_authority: FormalQcResultReadAuthority,
        result_gate: FormalQcResultGateCandidate,
        terminal: FormalQcTerminalStatusReceipt,
        launch: FormalQcLaunchReceipt,
        candidate: FormalRunCandidate,
        reviewed_authority: ReviewedFormalRunAuthority,
        root_manifest: bytes,
        family_payloads: tuple[tuple[str, bytes], ...],
        bindings: object,
        descriptors: tuple[object, ...],
    ) -> FormalQcSummaryResultReadReceipt:
        return summary_mint_implementation(
            record=record,
            pairs=pairs,
            permit=permit,
            result_authority=result_authority,
            result_gate=result_gate,
            terminal=terminal,
            launch=launch,
            candidate=candidate,
            reviewed_authority=reviewed_authority,
            root_manifest=root_manifest,
            family_payloads=family_payloads,
            bindings=bindings,
            descriptors=descriptors,
            _authority_register=process_register_summary,
        )

    def mint_completed(
        *,
        pairs: tuple[tuple[str, str], ...],
        permit: FormalQcResultReadPermit,
        result_authority: FormalQcResultReadAuthority,
        result_gate: FormalQcResultGateCandidate,
        terminal: FormalQcTerminalStatusReceipt,
        launch: FormalQcLaunchReceipt,
        candidate: FormalRunCandidate,
        reviewed_authority: ReviewedFormalRunAuthority,
        root_manifest: bytes = b"",
        family_payloads: tuple[tuple[str, bytes], ...] = (),
        bindings: object = None,
        descriptors: tuple[object, ...] = (),
    ) -> FormalQcSummaryResultReadReceipt:
        return completed_mint_implementation(
            pairs=pairs,
            permit=permit,
            result_authority=result_authority,
            result_gate=result_gate,
            terminal=terminal,
            launch=launch,
            candidate=candidate,
            reviewed_authority=reviewed_authority,
            _authority_mint_summary=mint_summary,
            root_manifest=root_manifest,
            family_payloads=family_payloads,
            bindings=bindings,
            descriptors=descriptors,
        )

    def execute_streamed_formal_qc_submission_once(
        *,
        submission_bridge: StreamedFormalSubmissionAdapterBridge,
        claim: FormalLookClaim,
        client: FormalQcTransport,
        submission_started_at_utc: str,
    ) -> tuple[FormalSubmissionPermit, FormalQcLaunchReceipt]:
        binding_guard("streamed submission")
        return streamed_execute_implementation(
            submission_bridge=submission_bridge,
            claim=claim,
            client=client,
            submission_started_at_utc=submission_started_at_utc,
            _authority_register_launch=register_launch,
            _transport_capability_minter=transport_capability_minter,
        )

    def execute_formal_qc_submission_once(
        *,
        candidate: FormalRunCandidate,
        authority: ReviewedFormalRunAuthority,
        claim: FormalLookClaim,
        projection: FormalQcRuntimeProjection,
        plan: FormalQcSubmissionPlan,
        client: FormalQcTransport,
        submission_started_at_utc: str,
    ) -> tuple[FormalSubmissionPermit, FormalQcLaunchReceipt]:
        binding_guard("legacy submission")
        return legacy_execute_implementation(
            candidate=candidate,
            authority=authority,
            claim=claim,
            projection=projection,
            plan=plan,
            client=client,
            submission_started_at_utc=submission_started_at_utc,
            _authority_register_launch=register_launch,
            _transport_capability_minter=transport_capability_minter,
        )

    def inspect_streamed_statistics_free_terminal_status(
        *,
        submission_bridge: StreamedFormalSubmissionAdapterBridge,
        claim: FormalLookClaim,
        permit: FormalSubmissionPermit,
        launch: FormalQcLaunchReceipt,
        client: FormalQcTransport,
    ) -> FormalQcTerminalStatusReceipt:
        binding_guard("streamed status")
        return streamed_status_implementation(
            submission_bridge=submission_bridge,
            claim=claim,
            permit=permit,
            launch=launch,
            client=client,
            _authority_register_terminal=register_terminal,
            _transport_capability_minter=transport_capability_minter,
        )

    def inspect_statistics_free_terminal_status(
        *,
        candidate: FormalRunCandidate,
        authority: ReviewedFormalRunAuthority,
        claim: FormalLookClaim,
        permit: FormalSubmissionPermit,
        plan: FormalQcSubmissionPlan,
        launch: FormalQcLaunchReceipt,
        client: FormalQcTransport,
    ) -> FormalQcTerminalStatusReceipt:
        binding_guard("legacy status")
        return legacy_status_implementation(
            candidate=candidate,
            authority=authority,
            claim=claim,
            permit=permit,
            plan=plan,
            launch=launch,
            client=client,
            _authority_register_terminal=register_terminal,
            _transport_capability_minter=transport_capability_minter,
        )

    def read_streamed_formal_qc_summary_result_once(
        *,
        result_authority: FormalQcResultReadAuthority,
        result_gate: FormalQcResultGateCandidate,
        submission_bridge: StreamedFormalSubmissionAdapterBridge,
        terminal: FormalQcTerminalStatusReceipt,
        launch: FormalQcLaunchReceipt,
        claim: FormalLookClaim,
        submission_permit: FormalSubmissionPermit,
        client: FormalQcTransport,
        result_read_started_at_utc: str,
    ) -> FormalQcSummaryResultReadReceipt:
        binding_guard("streamed result read")
        return streamed_read_implementation(
            result_authority=result_authority,
            result_gate=result_gate,
            submission_bridge=submission_bridge,
            terminal=terminal,
            launch=launch,
            claim=claim,
            submission_permit=submission_permit,
            client=client,
            result_read_started_at_utc=result_read_started_at_utc,
            _authority_mint_completed=mint_completed,
            _transport_capability_minter=transport_capability_minter,
        )

    def read_formal_qc_summary_result_once(
        *,
        result_authority: FormalQcResultReadAuthority,
        result_gate: FormalQcResultGateCandidate,
        candidate: FormalRunCandidate,
        reviewed_authority: ReviewedFormalRunAuthority,
        terminal: FormalQcTerminalStatusReceipt,
        launch: FormalQcLaunchReceipt,
        claim: FormalLookClaim,
        submission_permit: FormalSubmissionPermit,
        plan: FormalQcSubmissionPlan,
        client: FormalQcTransport,
        result_read_started_at_utc: str,
    ) -> FormalQcSummaryResultReadReceipt:
        binding_guard("legacy result read")
        return legacy_read_implementation(
            result_authority=result_authority,
            result_gate=result_gate,
            candidate=candidate,
            reviewed_authority=reviewed_authority,
            terminal=terminal,
            launch=launch,
            claim=claim,
            submission_permit=submission_permit,
            plan=plan,
            client=client,
            result_read_started_at_utc=result_read_started_at_utc,
            _authority_mint_completed=mint_completed,
            _transport_capability_minter=transport_capability_minter,
        )

    def require_formal_qc_summary_result_read_receipt(
        value: FormalQcSummaryResultReadReceipt,
        *,
        result_authority: FormalQcResultReadAuthority,
        terminal: FormalQcTerminalStatusReceipt,
        launch: FormalQcLaunchReceipt,
    ) -> FormalQcSummaryResultReadReceipt:
        return summary_require_implementation(
            value,
            result_authority=result_authority,
            terminal=terminal,
            launch=launch,
            _authority_current=process_current_summary,
        )

    return (
        _require_launch_receipt_authority,
        _require_terminal_status_receipt_authority,
        execute_streamed_formal_qc_submission_once,
        execute_formal_qc_submission_once,
        inspect_streamed_statistics_free_terminal_status,
        inspect_statistics_free_terminal_status,
        read_streamed_formal_qc_summary_result_once,
        read_formal_qc_summary_result_once,
        require_formal_qc_summary_result_read_receipt,
        (
            register_launch,
            register_terminal,
            mint_summary,
            mint_completed,
        ),
    )

def _seal_formal_pre_spend_io_authority(
    implementation: Callable[..., object],
    binding_guard: Callable[[str], None],
) -> Callable[..., object]:
    """Authenticate exact dependencies before any pre-spend host/file read."""

    def sealed(*args, **kwargs):
        binding_guard("result-control I/O")
        return implementation(*args, **kwargs)

    sealed.__name__ = implementation.__name__
    sealed.__qualname__ = implementation.__qualname__
    sealed.__doc__ = implementation.__doc__
    return sealed


for _formal_pre_spend_io_name in (
    "_require_private_result_directory",
    "_read_private_result_control",
    "_exclusive_private_result_write",
    "verify_formal_qc_host_closure_live",
):
    globals()[_formal_pre_spend_io_name] = _seal_formal_pre_spend_io_authority(
        globals()[_formal_pre_spend_io_name],
        _require_formal_action_global_bindings,
    )
del _formal_pre_spend_io_name
del _seal_formal_pre_spend_io_authority


# Claim the sole production transport minter only after all exact action
# implementations exist, so its caller provenance can be sealed to those
# code objects before any public action wrapper is exposed.
(
    _mint_transport_capability,
    _seal_formal_transport_capability_callers,
    _register_downstream_transport_capability_minter,
) = _claim_adapter_capability_minter()
globals().pop("_claim_adapter_capability_minter", None)
(
    _claim_fundamental_discovery_transport_capability_minter,
    _claim_preopen_transport_capability_minter,
    _claim_power_calibration_transport_capability_minter,
) = _make_downstream_transport_minter_claims(
    _mint_transport_capability,
    _register_downstream_transport_capability_minter,
)
del _make_downstream_transport_minter_claims
del _register_downstream_transport_capability_minter


(
    _require_launch_receipt_authority,
    _require_terminal_status_receipt_authority,
    execute_streamed_formal_qc_submission_once,
    execute_formal_qc_submission_once,
    inspect_streamed_statistics_free_terminal_status,
    inspect_statistics_free_terminal_status,
    read_streamed_formal_qc_summary_result_once,
    read_formal_qc_summary_result_once,
    require_formal_qc_summary_result_read_receipt,
    _process_receipt_binder_functions,
) = _bind_process_receipt_authorities(
    _mint_transport_capability,
    _require_formal_action_global_bindings,
    _process_authority_register_launch,
    _process_authority_current_launch,
    _process_authority_register_terminal,
    _process_authority_current_terminal,
    _process_authority_register_summary,
    _process_authority_current_summary,
    _register_launch_receipt_authority_impl,
    _require_launch_receipt_authority_impl,
    _register_terminal_status_receipt_authority_impl,
    _require_terminal_status_receipt_authority_impl,
    _mint_summary_result_receipt_authority_impl,
    _mint_completed_summary_read_receipt_impl,
    _execute_streamed_formal_qc_submission_once_impl,
    _execute_formal_qc_submission_once_impl,
    _inspect_streamed_statistics_free_terminal_status_impl,
    _inspect_statistics_free_terminal_status_impl,
    _read_streamed_formal_qc_summary_result_once_impl,
    _read_formal_qc_summary_result_once_impl,
    _require_formal_qc_summary_result_read_receipt_impl,
)
_seal_formal_transport_capability_callers((
    (
        "submission",
        (
            (
                _execute_streamed_formal_qc_submission_once_impl,
                execute_streamed_formal_qc_submission_once,
            ),
            (
                _execute_formal_qc_submission_once_impl,
                execute_formal_qc_submission_once,
            ),
        ),
    ),
    (
        "status",
        (
            (
                _inspect_streamed_statistics_free_terminal_status_impl,
                inspect_streamed_statistics_free_terminal_status,
            ),
            (
                _inspect_statistics_free_terminal_status_impl,
                inspect_statistics_free_terminal_status,
            ),
        ),
    ),
    (
        "result_read",
        (
            (
                _read_streamed_formal_qc_summary_result_once_impl,
                read_streamed_formal_qc_summary_result_once,
            ),
            (
                _read_formal_qc_summary_result_once_impl,
                read_formal_qc_summary_result_once,
            ),
        ),
    ),
    (
        "result_family_read",
        (
            (
                _read_streamed_formal_result_family_objects,
                _read_streamed_formal_qc_summary_result_once_impl,
                read_streamed_formal_qc_summary_result_once,
            ),
        ),
    ),
))
del _seal_formal_transport_capability_callers
_seal_process_receipt_authority_provenance((
    (
        "launch",
        tuple(
            (
                _process_authority_register_launch,
                _register_launch_receipt_authority_impl,
                _process_receipt_binder_functions[0],
                implementation,
                public,
            )
            for implementation, public in (
                (
                    _execute_streamed_formal_qc_submission_once_impl,
                    execute_streamed_formal_qc_submission_once,
                ),
                (
                    _execute_formal_qc_submission_once_impl,
                    execute_formal_qc_submission_once,
                ),
            )
        ),
    ),
    (
        "terminal",
        tuple(
            (
                _process_authority_register_terminal,
                _register_terminal_status_receipt_authority_impl,
                _process_receipt_binder_functions[1],
                implementation,
                public,
            )
            for implementation, public in (
                (
                    _inspect_streamed_statistics_free_terminal_status_impl,
                    inspect_streamed_statistics_free_terminal_status,
                ),
                (
                    _inspect_statistics_free_terminal_status_impl,
                    inspect_statistics_free_terminal_status,
                ),
            )
        ),
    ),
    (
        "summary",
        tuple(
            (
                _process_authority_register_summary,
                _mint_summary_result_receipt_authority_impl,
                _process_receipt_binder_functions[2],
                _mint_completed_summary_read_receipt_impl,
                _process_receipt_binder_functions[3],
                implementation,
                public,
            )
            for implementation, public in (
                (
                    _read_streamed_formal_qc_summary_result_once_impl,
                    read_streamed_formal_qc_summary_result_once,
                ),
                (
                    _read_formal_qc_summary_result_once_impl,
                    read_formal_qc_summary_result_once,
                ),
            )
        ),
    ),
))
del _bind_process_receipt_authorities
del _process_receipt_binder_functions
del _seal_process_receipt_authority_provenance
del _execute_formal_qc_submission_once_impl
del _execute_streamed_formal_qc_submission_once_impl
del _inspect_statistics_free_terminal_status_impl
del _inspect_streamed_statistics_free_terminal_status_impl
del _make_process_receipt_authority_vault
del _mint_completed_summary_read_receipt_impl
del _mint_summary_result_receipt_authority_impl
del _mint_transport_capability
del _process_authority_current_launch
del _process_authority_current_summary
del _process_authority_current_terminal
del _process_authority_register_launch
del _process_authority_register_summary
del _process_authority_register_terminal
del _read_formal_qc_summary_result_once_impl
del _read_streamed_formal_qc_summary_result_once_impl
del _register_launch_receipt_authority_impl
del _register_terminal_status_receipt_authority_impl
del _require_formal_qc_summary_result_read_receipt_impl
del _require_launch_receipt_authority_impl
del _require_terminal_status_receipt_authority_impl


def formal_qc_submission_adapter_record() -> dict[str, object]:
    signature_registry = reviewed_owner_signature_registry_status()
    gate_key_counts = signature_registry["gate_key_counts"]
    signature_keys_installed = (
        type(gate_key_counts) is dict
        and gate_key_counts.get("formal_qc_execution") == 1
        and gate_key_counts.get("formal_qc_result_read") == 1
    )
    return {
        "schema": SCHEMA, "status": STATUS, "authority": AUTHORITY,
        "concrete_transport_present": True,
        "non_self_mintable_execution_trust_root_implemented": True,
        "non_self_mintable_result_read_trust_root_implemented": True,
        "reviewed_owner_signature_key_count": signature_registry["reviewed_key_count"],
        "reviewed_owner_signature_key_installed": signature_keys_installed,
        "all_external_actions_hard_disabled": not signature_keys_installed,
        "capacity_receipt_is_external_authority": False,
        "injected_transport_allowed_for_formal_submission": False,
        "injected_callback_can_receive_environment_credentials": False,
        "same_process_hostile_python_sandbox_claimed": False,
        "security_boundary": "exact_live_reviewed_host_source_closure",
        "compact_multipart_input_present": True,
        "disk_backed_streamed_input_present": True,
        "sequential_reopen_rehash_upload_present": True,
        "streamed_manifest_published_last": True,
        "streamed_full_payload_tuple_materialized": False,
        "metadata_size_md5_verification_present": True,
        "live_host_closure_reverified_before_external_actions": True,
        "statistics_free_status_parser_present": True,
        "legacy_materialized_external_action_paths_retired": True,
        "streamed_statistics_free_terminal_path_present": True,
        "streamed_authenticated_power_floor_required": True,
        "streamed_selected_summary_only_result_path_present": True,
        "separate_result_read_gate_present": True,
        "external_private_result_read_pin_required": True,
        "durable_exclusive_result_read_ledger_present": True,
        "result_read_callback_injection_allowed": False,
        "summary_result_receipt_present": True,
        "summary_result_receipt_builder_authenticated": True,
        "raw_object_store_result_download_required": False,
        "deployment_orders_trading_authorized": False,
    }


__all__ = (
    "AUTHORITY", "BACKTEST_PENDING_STATUSES", "BACKTEST_TERMINAL_STATUSES",
    "COMPILE_POLL_INTERVAL_SECONDS", "EXECUTION_ACTIONS",
    "FormalQcExecutionAuthority", "FormalQcHostClosureBinding",
    "FormalQcHostSourceBinding", "FormalQcLaunchReceipt",
    "FormalQcResultGateCandidate", "FormalQcResultReadAuthority",
    "FormalQcResultReadExternalPin", "FormalQcResultReadPermit",
    "FormalQcSubmissionError", "FormalQcSubmissionLocked",
    "FormalQcSubmissionPlan", "FormalQcSummaryResultReadReceipt",
    "FormalQcTerminalStatusReceipt", "FormalQcTransportBinding",
    "FormalQcUploadBundle", "FormalQcUploadEntry", "MAX_COMPILE_POLLS",
    "StreamedFormalQcExecutionAuthority", "StreamedFormalQcSubmissionPlan",
    "StreamedFormalSubmissionAdapterBridge",
    "MAX_STATUS_POLLS", "REQUIRED_HOST_CODE_PATHS",
    "RESULT_READ_EXTERNAL_PIN_FILENAME", "RESULT_READ_LEDGER_FILENAME", "SCHEMA",
    "STATUS", "STATUS_POLL_INTERVAL_SECONDS", "TRANSPORT_REQUEST_SURFACE",
    "build_formal_qc_host_closure_binding", "build_formal_qc_result_gate_candidate",
    "build_streamed_formal_qc_result_gate_candidate",
    "build_formal_qc_result_read_permit",
    "build_formal_qc_submission_plan", "build_formal_qc_transport_binding",
    "build_formal_qc_upload_bundle", "execute_formal_qc_submission_once",
    "build_streamed_formal_qc_submission_plan",
    "build_streamed_formal_submission_adapter_bridge",
    "execute_streamed_formal_qc_submission_once",
    "formal_qc_submission_adapter_record", "inspect_statistics_free_terminal_status",
    "inspect_streamed_statistics_free_terminal_status",
    "load_formal_qc_execution_authority", "load_formal_qc_result_read_authority",
    "load_streamed_formal_qc_execution_authority",
    "load_formal_qc_result_read_external_pin",
    "parse_statistics_free_backtest_list", "read_formal_qc_summary_result_once",
    "read_streamed_formal_qc_summary_result_once",
    "render_formal_qc_execution_authority_candidate",
    "render_streamed_formal_qc_execution_authority_candidate",
    "render_formal_qc_result_read_external_pin_candidate",
    "render_formal_qc_result_read_authority_candidate",
    "require_formal_qc_execution_authority", "require_formal_qc_host_closure_binding",
    "require_formal_qc_launch_receipt", "require_formal_qc_result_gate_candidate",
    "require_formal_qc_result_read_external_pin",
    "require_formal_qc_result_read_authority", "require_formal_qc_result_read_permit",
    "require_formal_qc_submission_plan", "require_formal_qc_summary_result_read_receipt",
    "require_formal_qc_terminal_status_receipt", "require_formal_qc_transport_binding",
    "require_formal_qc_upload_bundle", "verify_formal_qc_host_closure_live",
    "require_streamed_formal_qc_execution_authority",
    "require_streamed_formal_qc_launch_receipt",
    "require_streamed_formal_qc_result_gate_candidate",
    "require_streamed_formal_qc_submission_plan",
    "require_streamed_formal_qc_terminal_status_receipt",
    "require_streamed_formal_submission_adapter_bridge",
    "streamed_formal_post_launch_capability_record",
)


_seal_formal_action_global_bindings()
del _make_formal_action_global_binding_guard
del _seal_formal_action_global_bindings
del _require_formal_action_global_bindings
