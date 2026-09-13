"""Concrete, allowlisted QuantConnect transport for the ARV2 formal run.

The submission adapter owns authorization and one-look accounting.  This
module owns only HTTP mechanics: the documented JSON endpoints, multipart
``/object/set``, and metadata verification.  Credentials are acquired through
the repository's redacting ``QuantConnectCredentials.from_env`` boundary; no
credential value is accepted by a public string argument, serialized, logged,
or included in an exception.

Constructing the transport performs no I/O and does not retain production
credentials.  Tests inject ``http_transport`` and ``clock`` so every path is
deterministic, credential-isolated, and offline.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import ssl
import sys
import threading
import time
from typing import Callable, Mapping
from urllib import error, request

from research.quantconnect import (
    API_BASE,
    QuantConnectCredentials,
)


class FormalQcTransportError(RuntimeError):
    """The reviewed transport refused a request or response."""


TRANSPORT_SCHEMA = "arv2-formal-qc-concrete-transport-v1"
REQUEST_METHOD_NAMES = (
    "_request_json",
    "_set_object_multipart",
    "_read_object_properties",
    "_read_object_bounded",
    "_read_power_calibration_object_bounded",
    "_read_formal_result_family_object_bounded",
    "_read_backtest_result",
)
_JSON_ENDPOINTS = frozenset(
    {
        "authenticate",
        "projects/create",
        "projects/read",
        "files/read",
        "files/create",
        "files/update",
        "compile/create",
        "compile/read",
        "backtests/create",
        "backtests/list",
        "object/properties",
        "object/read",
    }
)
_POST_ENDPOINTS = _JSON_ENDPOINTS | frozenset({"object/set", "backtests/read"})
_SAFE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,1023}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,511}\Z")
_SECRET_KEYS = frozenset(
    {"authorization", "api_token", "apitoken", "token", "password", "secret"}
)
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_OBJECT_BYTES = 48 * 1024 * 1024
FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT = 26
MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES = 4_200_000
MAX_FORMAL_RESULT_FAMILY_TOTAL_BYTES = (
    FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT
    * MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES
)
RESULT_FAMILY_READ_CAPABILITY_SCHEMA = (
    "arv2-formal-qc-result-family-read-transport-capability-v1"
)
PRODUCTION_TIMEOUT_SECONDS = 30.0
_OFFLINE_TEST_CREDENTIALS = QuantConnectCredentials(
    user_id="offline-test-user", api_token="offline-test-token-not-a-secret"
)


def _make_lane_local_production_primitives():
    """Close production clock and HTTP calls over their exact primitives."""

    request_constructor = request.Request
    open_url = request.urlopen
    make_tls_context = ssl.create_default_context
    http_error = error.HTTPError
    exact_dict = dict
    exact_int = int
    base_exception = Exception
    response_limit = MAX_RESPONSE_BYTES
    transport_error = FormalQcTransportError
    time_source = time.time

    def prepare_production_http_transport():
        # Creating the verified TLS context can read system trust files.  Do it
        # request-locally, before credential acquisition, never at import.
        tls_context = make_tls_context()

        def prepared_http_transport(
            url: str,
            body: bytes,
            headers: Mapping[str, str],
            timeout: float,
        ) -> tuple[int, bytes]:
            req = request_constructor(
                url,
                data=body,
                headers=exact_dict(headers),
                method="POST",
            )
            try:
                with open_url(
                    req,
                    timeout=timeout,
                    context=tls_context,
                ) as response:
                    raw = response.read(response_limit + 1)
                    return response.getcode(), raw
            except http_error as exc:
                return exc.code, exc.read(response_limit + 1)
            except base_exception:
                # Do not interpolate the request, headers, body, or underlying
                # exception: transports and TLS stacks can echo authentication
                # material.
                raise transport_error(
                    "QuantConnect network request failed"
                ) from None

        return prepared_http_transport

    def default_http_transport(
        url: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, bytes]:
        return prepare_production_http_transport()(
            url, body, headers, timeout
        )

    def production_clock() -> int:
        return exact_int(time_source())

    return (
        default_http_transport,
        production_clock,
        prepare_production_http_transport,
    )


(
    _default_http_transport,
    _production_clock,
    _prepare_production_http_transport,
) = (
    _make_lane_local_production_primitives()
)
del _make_lane_local_production_primitives


def _build_transport_capability_authority():
    """Keep capability construction and mutable authority state private."""

    sentinel = object()
    states: tuple[
        tuple[
            int,
            tuple[
                object, object, tuple[tuple[str, int], ...], int, int
            ],
        ], ...
    ] = ()
    authority_lock = threading.RLock()
    adapter_minter_claimed = False
    production_mint_provenance: tuple[object, ...] = ()
    offline_mint_code: object = None
    offline_mint_closure: tuple[tuple[str, object], ...] = ()
    formal_caller_provenance: tuple[
        tuple[str, tuple[tuple[tuple[object, ...], ...], ...]], ...
    ] = ()
    delegated_minter_provenance: tuple[
        tuple[str, tuple[object, ...]], ...
    ] = ()
    authority_pid = os.getpid()
    expected_adapter_path = os.path.realpath(
        os.path.join(os.path.dirname(__file__), "formal_submission_adapter.py")
    )
    function_type = type(_build_transport_capability_authority)
    missing_closure_value = object()
    expected_module_names: tuple[str, ...] = ()
    expected_module_globals: tuple[tuple[str, object], ...] = ()
    expected_external: tuple[tuple[object, str, object], ...] = ()
    expected_class_namespaces: tuple[
        tuple[object, tuple[str, ...], tuple[tuple[str, object], ...]], ...
    ] = ()
    request_dependencies: tuple[object, ...] = ()
    get_module_globals = globals
    get_pid = os.getpid
    get_frame = sys._getframe
    real_path = os.path.realpath
    get_attribute = getattr
    module_vars = vars
    exact_type = type
    exact_tuple = tuple
    any_true = any
    sort_values = sorted
    error_type = FormalQcTransportError
    module_name = __name__
    module_registry = sys.modules
    authority_module = module_registry.get(module_name)
    excluded_module_names = (
        "_claim_adapter_capability_minter",
        "_require_transport_authority_global_bindings",
        "_seal_transport_authority_global_bindings",
    )
    external_specs = (
        (base64, ("b64decode", "b64encode")),
        (hashlib, ("sha256",)),
        (
            json,
            ("dumps", "loads", "JSONDecoder", "_default_decoder"),
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
        (os, ("getpid",)),
        (os.path, ("realpath",)),
        (
            request,
            (
                "Request", "urlopen", "HTTPSHandler", "build_opener",
                "_opener",
            ),
        ),
        (request.Request, ("__new__", "__init__")),
        (
            request.HTTPSHandler,
            ("__new__", "__init__", "https_open"),
        ),
        (
            request.urlopen,
            ("__code__", "__globals__", "__defaults__", "__closure__"),
        ),
        (error, ("HTTPError",)),
        (ssl, ("create_default_context",)),
        (sys, ("_getframe", "modules")),
        (threading, ("RLock",)),
        (time, ("time",)),
    )
    credential_environment = os.environ
    environment_getitem = credential_environment.__getitem__
    missing_environment_key = KeyError
    strip_text = str.strip
    exact_str = str
    exact_int = int
    auth_sha256 = hashlib.sha256
    auth_b64encode = base64.b64encode
    user_id_environment_name = "QC_USER_ID"
    api_token_environment_name = "QC_API_TOKEN"
    class_namespaces = (
        json.JSONDecoder,
        json.JSONEncoder,
        request.Request,
        request.HTTPSHandler,
    )

    def load_production_credential_material() -> tuple[str, str]:
        """Read only the captured environment through lexical primitives."""

        try:
            user_id = environment_getitem(user_id_environment_name)
        except missing_environment_key:
            user_id = ""
        try:
            api_token = environment_getitem(api_token_environment_name)
        except missing_environment_key:
            api_token = ""
        if exact_type(user_id) is not exact_str:
            user_id = ""
        else:
            user_id = strip_text(user_id)
        if exact_type(api_token) is not exact_str:
            api_token = ""
        else:
            api_token = strip_text(api_token)
        if not user_id or not api_token:
            raise error_type("QuantConnect credentials are not configured")
        return user_id, api_token

    def build_lane_local_auth_headers(
        credential_material: tuple[str, str], timestamp: int,
    ) -> dict[str, str]:
        """Build authentication without consulting shared-module globals."""

        if (
            exact_type(credential_material) is not exact_tuple
            or len(credential_material) != 2
            or exact_type(credential_material[0]) is not exact_str
            or exact_type(credential_material[1]) is not exact_str
            or not credential_material[0]
            or not credential_material[1]
            or exact_type(timestamp) is not exact_int
            or timestamp <= 0
        ):
            raise error_type("QuantConnect credentials boundary changed")
        user_id, api_token = credential_material
        stamped = f"{api_token}:{timestamp}".encode("utf-8")
        hashed = auth_sha256(stamped).hexdigest()
        encoded = auth_b64encode(
            f"{user_id}:{hashed}".encode("utf-8")
        ).decode("ascii")
        return {
            "Authorization": f"Basic {encoded}",
            "Timestamp": str(timestamp),
        }

    def seal_module_bindings() -> None:
        nonlocal expected_module_names, expected_module_globals
        nonlocal expected_external, expected_class_namespaces
        nonlocal request_dependencies

        if (
            expected_module_names
            or expected_module_globals
            or expected_external
            or expected_class_namespaces
            or request_dependencies
            or authority_module is None
            or module_registry.get(module_name) is not authority_module
            or module_vars(authority_module) is not get_module_globals()
        ):
            raise error_type(
                "transport authority globals were already sealed"
            )
        current = get_module_globals()
        expected_module_names = exact_tuple(sort_values(
            name for name in current
            if not name.startswith("__")
            and name not in excluded_module_names
        ))
        expected_module_globals = exact_tuple(
            (name, current[name]) for name in expected_module_names
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
                exact_tuple(
                    (name, value)
                    for name, value in module_vars(class_type).items()
                ),
            )
            for class_type in class_namespaces
        )
        transport_type = current.get("FormalQcTransport", missing_closure_value)
        request_names = current.get("REQUEST_METHOD_NAMES")
        if (
            exact_type(transport_type) is not exact_type
            or exact_type(request_names) is not exact_tuple
        ):
            raise error_type("transport request surface changed")
        expected_external += exact_tuple(
            (transport_type, name, get_attribute(transport_type, name))
            for name in (
                "__init__", "_require_production_configuration", "_post",
                *request_names,
            )
        )
        request_dependencies = (
            current["_default_http_transport"],
            current["_production_clock"],
            current["_prepare_production_http_transport"],
            load_production_credential_material,
            build_lane_local_auth_headers,
            get_attribute(json, "loads"),
            current["_strict_response_object"],
            current["_reject_nonstandard_json_constant"],
        )

    def require_module_bindings() -> None:
        if (
            get_pid() != authority_pid
            or not expected_module_names
            or not request_dependencies
            or authority_module is None
            or module_registry.get(module_name) is not authority_module
        ):
            raise error_type("transport capability authority changed")
        current = get_module_globals()
        current_names = exact_tuple(sort_values(
            name for name in current
            if not name.startswith("__")
            and name not in excluded_module_names
        ))
        if (
            module_vars(authority_module) is not current
            or current_names != expected_module_names
            or any_true(
                current.get(name, missing_closure_value) is not expected
                for name, expected in expected_module_globals
            )
            or any_true(
                get_attribute(namespace, name, missing_closure_value)
                is not expected
                for namespace, name, expected in expected_external
            )
            or any_true(
                exact_tuple(sort_values(module_vars(class_type)))
                != expected_names
                or any_true(
                    module_vars(class_type).get(name, missing_closure_value)
                    is not expected
                    for name, expected in expected_bindings
                )
                for (
                    class_type,
                    expected_names,
                    expected_bindings,
                ) in expected_class_namespaces
            )
        ):
            raise error_type("transport capability authority changed")

    def capture_function(function: object) -> tuple[object, ...]:
        module = (
            module_registry.get(function.__module__)
            if type(function) is function_type
            else None
        )
        if type(function) is not function_type:
            raise FormalQcTransportError(
                "transport capability caller function changed"
            )
        if module is None or vars(module) is not function.__globals__:
            raise FormalQcTransportError(
                "transport capability caller module changed"
            )
        closure = function.__closure__ or ()
        if len(closure) != len(function.__code__.co_freevars):
            raise FormalQcTransportError(
                "transport capability caller closure changed"
            )
        return (
            function,
            function.__code__,
            function.__name__,
            function.__module__,
            module,
            real_path(function.__code__.co_filename),
            id(function.__globals__),
            tuple(
                (
                    name,
                    function.__globals__.get(name, missing_closure_value),
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

    def frame_matches(
        frame: object,
        provenance: tuple[object, ...],
        *,
        public_binding: bool,
    ) -> bool:
        (
            expected_function,
            expected_code,
            expected_name,
            expected_module_name,
            expected_module,
            expected_path,
            expected_globals_id,
            expected_global_bindings,
            expected_closure,
        ) = provenance
        try:
            return (
                frame is not None
                and frame.f_code is expected_code
                and frame.f_code.co_name == expected_name
                and frame.f_globals.get("__name__") == expected_module_name
                and id(frame.f_globals) == expected_globals_id
                and module_registry.get(expected_module_name)
                is expected_module
                and vars(expected_module) is frame.f_globals
                and real_path(frame.f_code.co_filename) == expected_path
                and expected_function.__code__ is expected_code
                and expected_function.__globals__ is frame.f_globals
                and expected_function.__name__ == expected_name
                and all(
                    expected_function.__globals__.get(
                        name, missing_closure_value
                    ) is expected
                    and frame.f_globals.get(name, missing_closure_value)
                    is expected
                    for name, expected in expected_global_bindings
                )
                and tuple(expected_function.__code__.co_freevars)
                == tuple(item[0] for item in expected_closure)
                and len(expected_function.__closure__ or ())
                == len(expected_closure)
                and all(
                    cell.cell_contents is expected
                    for cell, (_name, expected) in zip(
                        expected_function.__closure__ or (),
                        expected_closure,
                        strict=True,
                    )
                )
                and all(
                    frame.f_locals.get(name, missing_closure_value)
                    is expected
                    for name, expected in expected_closure
                )
                and (
                    not public_binding
                    or frame.f_globals.get(expected_name)
                    is expected_function
                )
            )
        except (AttributeError, KeyError, OSError, TypeError, ValueError):
            return False

    def frame_chain_matches(
        frame: object,
        chain: tuple[tuple[object, ...], ...],
    ) -> bool:
        current = frame
        for position, provenance in enumerate(chain):
            if not frame_matches(
                current,
                provenance,
                public_binding=position == len(chain) - 1,
            ):
                return False
            current = current.f_back
        return True

    class Capability:
        __slots__ = (
            "scope", "binding_sha256", "call_budget", "transport_identity",
            "production_transport", "result_family_route",
            "capability_sha256", "_sentinel",
        )

        def __init__(
            self, scope: str, binding_sha256: str,
            call_budget: tuple[tuple[str, int], ...], transport_identity: int,
            production_transport: bool,
            result_family_route: tuple[int, str, tuple[str, ...]] | None,
            construction_sentinel: object,
        ) -> None:
            if construction_sentinel is not sentinel:
                raise FormalQcTransportError(
                    "transport capability construction is private"
                )
            self.scope = scope
            self.binding_sha256 = binding_sha256
            self.call_budget = call_budget
            self.transport_identity = transport_identity
            self.production_transport = production_transport
            self.result_family_route = result_family_route
            encoded = json.dumps(
                [
                    scope, binding_sha256, list(call_budget),
                    transport_identity, production_transport,
                    result_family_route,
                ],
                separators=(",", ":"), sort_keys=False,
            ).encode("ascii")
            self.capability_sha256 = hashlib.sha256(encoded).hexdigest()
            self._sentinel = sentinel

    def result_family_route_material(
        binding_record: Mapping[str, object],
    ) -> tuple[int, str, tuple[str, ...]]:
        project_id = binding_record.get("project_id")
        organization_id = binding_record.get("organization_id")
        descriptor_root_sha256 = binding_record.get(
            "descriptor_root_sha256"
        )
        raw_keys = binding_record.get("object_store_keys")
        if (
            binding_record.get("schema")
            != RESULT_FAMILY_READ_CAPABILITY_SCHEMA
            or type(project_id) is not int
            or project_id <= 0
            or type(descriptor_root_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", descriptor_root_sha256) is None
            or type(raw_keys) is not list
            or len(raw_keys) != FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT
        ):
            raise FormalQcTransportError(
                "formal result-family capability binding changed"
            )
        organization = _safe_id(organization_id, "organization_id")
        keys = tuple(_safe_key(item) for item in raw_keys)
        if len(set(keys)) != FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT:
            raise FormalQcTransportError(
                "formal result-family Object Store key inventory changed"
            )
        return project_id, organization, keys

    def capability_material(
        *, scope: str, binding_record: Mapping[str, object],
        call_budget: Mapping[str, int],
    ) -> tuple[
        str,
        tuple[tuple[str, int], ...],
        tuple[int, str, tuple[str, ...]] | None,
    ]:
        if scope not in {
            "submission", "status", "preopen_output_read",
            "power_calibration_output_read", "result_read",
            "result_family_read",
        }:
            raise FormalQcTransportError("transport capability scope changed")
        if (
            type(binding_record) is not dict
            or not _exact_json_tree(binding_record)
        ):
            raise FormalQcTransportError("transport capability binding changed")
        binding_sha256 = hashlib.sha256(_json_bytes(binding_record)).hexdigest()
        if type(call_budget) is not dict or not call_budget:
            raise FormalQcTransportError(
                "transport capability call budget changed"
            )
        expected_scope = {
            "submission": _POST_ENDPOINTS - {
                "backtests/list", "backtests/read", "object/read"
            },
            "status": frozenset({"backtests/list"}),
            "preopen_output_read": frozenset({"object/read"}),
            "power_calibration_output_read": frozenset({"object/read"}),
            "result_read": frozenset({"backtests/read"}),
            "result_family_read": frozenset({"object/read"}),
        }[scope]
        if any(
            path not in expected_scope or type(count) is not int or count < 1
            for path, count in call_budget.items()
        ):
            raise FormalQcTransportError(
                "transport capability path budget changed"
            )
        if scope == "result_family_read":
            if call_budget != {
                "object/read": FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT
            }:
                raise FormalQcTransportError(
                    "formal result-family call budget changed"
                )
            result_family_route = result_family_route_material(binding_record)
        else:
            result_family_route = None
        return (
            binding_sha256,
            tuple(sorted(call_budget.items())),
            result_family_route,
        )

    def register(
        capability: Capability, transport: object,
        budget: tuple[tuple[str, int], ...],
    ) -> None:
        nonlocal states

        caller = get_frame(1)
        if capability.production_transport is True:
            caller_matches = bool(production_mint_provenance) and frame_matches(
                caller, production_mint_provenance, public_binding=False
            )
        else:
            caller_matches = (
                caller.f_code is offline_mint_code
                and caller.f_globals.get("__name__") == __name__
                and tuple(caller.f_code.co_freevars)
                == tuple(item[0] for item in offline_mint_closure)
                and all(
                    caller.f_locals.get(name, missing_closure_value)
                    is expected
                    for name, expected in offline_mint_closure
                )
            )
        if not caller_matches:
            raise FormalQcTransportError(
                "transport capability register caller changed"
            )
        with authority_lock:
            if any(key == id(capability) for key, _entry in states):
                raise FormalQcTransportError(
                    "transport capability identity is already registered"
                )
            credentials = transport._credentials
            if capability.production_transport is True:
                credential_material = None
            elif exact_type(credentials) is QuantConnectCredentials:
                credential_material = (
                    credentials.user_id,
                    credentials.api_token,
                )
            else:
                raise FormalQcTransportError(
                    "offline transport credentials changed"
                )
            states = (*states, (
                id(capability),
                (
                    capability,
                    transport,
                    budget,
                    get_pid(),
                    0,
                    capability.scope,
                    capability.binding_sha256,
                    capability.call_budget,
                    capability.transport_identity,
                    capability.production_transport,
                    capability.result_family_route,
                    capability.capability_sha256,
                    transport._production_ready,
                    transport._http,
                    transport._base_url,
                    transport._clock,
                    transport._timeout,
                    credentials,
                    credential_material,
                ),
            ))

    def claim_adapter_minter() -> tuple[
        Callable[..., object], Callable[..., None], Callable[..., None],
    ]:
        """Issue the one production minter only to the exact adapter import."""

        nonlocal adapter_minter_claimed, production_mint_provenance
        nonlocal formal_caller_provenance
        nonlocal delegated_minter_provenance
        try:
            caller = get_frame(1)
            caller_name = caller.f_globals.get("__name__")
            caller_globals = caller.f_globals
            caller_path = real_path(caller.f_code.co_filename)
            caller_code_name = caller.f_code.co_name
            registered_adapter = module_registry.get(
                "research.analyst_revisions_v2_qc.formal_submission_adapter"
            )
        except (AttributeError, OSError, TypeError):
            caller = None
            caller_name = None
            caller_globals = None
            caller_path = ""
            caller_code_name = ""
            registered_adapter = None
        if (
            get_pid() != authority_pid
            or caller_name
            != "research.analyst_revisions_v2_qc.formal_submission_adapter"
            or registered_adapter is None
            or vars(registered_adapter) is not caller_globals
            or caller_path != expected_adapter_path
            or caller_code_name != "<module>"
        ):
            raise FormalQcTransportError(
                "production capability minter claim is adapter-private"
            )
        if adapter_minter_claimed:
            raise FormalQcTransportError(
                "production capability minter is already claimed"
            )
        expected_formal_adapter_module = registered_adapter
        action_names = (
            (
                "submission",
                (
                    "_execute_formal_qc_submission_once_impl",
                    "_execute_streamed_formal_qc_submission_once_impl",
                ),
            ),
            (
                "status",
                (
                    "_inspect_statistics_free_terminal_status_impl",
                    "_inspect_streamed_statistics_free_terminal_status_impl",
                ),
            ),
            (
                "result_read",
                (
                    "_read_formal_qc_summary_result_once_impl",
                    "_read_streamed_formal_qc_summary_result_once_impl",
                ),
            ),
            (
                "result_family_read",
                ("_read_streamed_formal_result_family_objects",),
            ),
        )
        try:
            allowed_caller_codes = tuple(
                (
                    scope,
                    tuple(caller_globals[name].__code__ for name in names),
                )
                for scope, names in action_names
            )
            downstream_factory_code = caller_globals[
                "_make_downstream_transport_minter_claims"
            ].__code__
            code_type = type(downstream_factory_code)

            def nested_codes(code):
                return tuple(
                    item
                    for constant in code.co_consts
                    if type(constant) is code_type
                    for item in (constant, *nested_codes(constant))
                )

            downstream_mint_codes = tuple(
                code for code in nested_codes(downstream_factory_code)
                if code.co_name == "mint"
            )
            downstream_claim_codes = tuple(
                code for code in nested_codes(downstream_factory_code)
                if code.co_name == "claim"
            )
        except (AttributeError, KeyError, TypeError):
            allowed_caller_codes = ()
            downstream_mint_codes = ()
            downstream_claim_codes = ()
        if (
            tuple(item[0] for item in allowed_caller_codes)
            != ("submission", "status", "result_read", "result_family_read")
            or any(not item[1] for item in allowed_caller_codes)
            or len(downstream_mint_codes) != 1
            or len(downstream_claim_codes) != 1
        ):
            raise FormalQcTransportError(
                "production capability minter caller provenance is incomplete"
            )
        allowed_caller_codes = tuple(
            (
                scope,
                codes + (
                    downstream_mint_codes
                    if scope in {
                        "submission",
                        "status",
                        "preopen_output_read",
                        "power_calibration_output_read",
                    }
                    else ()
                ),
            )
            for scope, codes in (
                *allowed_caller_codes,
                ("preopen_output_read", ()),
                ("power_calibration_output_read", ()),
            )
        )
        adapter_minter_claimed = True
        minter_pid = get_pid()

        def caller_is_authorized(frame: object, scope: str) -> bool:
            alternatives = next(
                (
                    chains
                    for expected_scope, chains in formal_caller_provenance
                    if expected_scope == scope
                ),
                (),
            )
            if any(
                frame_chain_matches(frame, chain)
                for chain in alternatives
            ):
                return True
            return any(
                frame_matches(frame, provenance, public_binding=False)
                for _adapter_key, provenance in delegated_minter_provenance
            )

        def mint(
            *, transport: "FormalQcTransport", scope: str,
            binding_record: Mapping[str, object],
            call_budget: Mapping[str, int],
        ) -> object:
            require_module_bindings()
            caller = get_frame(1)
            if (
                get_pid() != minter_pid
                or not caller_is_authorized(caller, scope)
            ):
                raise FormalQcTransportError(
                    "transport capability minter caller changed"
                )
            if type(transport) is not FormalQcTransport:
                raise FormalQcTransportError(
                    "exact production transport is required"
                )
            transport._require_production_configuration()
            binding_sha256, budget, result_family_route = capability_material(
                scope=scope,
                binding_record=binding_record,
                call_budget=call_budget,
            )
            capability = Capability(
                scope, binding_sha256, budget, id(transport), True,
                result_family_route, sentinel,
            )
            register(capability, transport, budget)
            return capability

        if production_mint_provenance:
            raise FormalQcTransportError(
                "production capability mint provenance was already sealed"
            )
        production_mint_provenance = capture_function(mint)

        def seal_formal_callers(
            value: tuple[
                tuple[str, tuple[tuple[object, ...], ...]], ...
            ],
        ) -> None:
            nonlocal formal_caller_provenance

            require_module_bindings()
            if (
                formal_caller_provenance
                or type(value) is not tuple
                or tuple(item[0] for item in value)
                != (
                    "submission",
                    "status",
                    "result_read",
                    "result_family_read",
                )
                or any(
                    type(item) is not tuple
                    or len(item) != 2
                    or type(item[1]) is not tuple
                    or not item[1]
                    or any(
                        type(chain) is not tuple
                        or len(chain) < 2
                        for chain in item[1]
                    )
                    for item in value
                )
            ):
                raise FormalQcTransportError(
                    "formal transport caller provenance changed"
                )
            try:
                captured = tuple(
                    (
                        scope,
                        tuple(
                            tuple(capture_function(function) for function in chain)
                            for chain in alternatives
                        ),
                    )
                    for scope, alternatives in value
                )
            except (AttributeError, OSError, TypeError, ValueError) as exc:
                raise FormalQcTransportError(
                    "formal transport caller provenance changed"
                ) from exc
            for scope, alternatives in captured:
                allowed = next(
                    codes
                    for expected_scope, codes in allowed_caller_codes
                    if expected_scope == scope
                )
                if any(chain[0][1] not in allowed for chain in alternatives):
                    raise FormalQcTransportError(
                        "formal transport caller provenance changed"
                    )
            formal_caller_provenance = captured

        def register_delegated_minter(
            adapter_key: str, function: object,
        ) -> None:
            nonlocal delegated_minter_provenance

            require_module_bindings()
            caller_frame = get_frame(1)
            if (
                adapter_key not in {"fundamental", "preopen", "power"}
                or any(
                    key == adapter_key
                    for key, _provenance in delegated_minter_provenance
                )
                or caller_frame.f_code is not downstream_claim_codes[0]
                or caller_frame.f_globals.get("__name__")
                != "research.analyst_revisions_v2_qc.formal_submission_adapter"
                or module_registry.get(
                    "research.analyst_revisions_v2_qc.formal_submission_adapter"
                ) is not expected_formal_adapter_module
                or vars(expected_formal_adapter_module)
                is not caller_frame.f_globals
                or real_path(caller_frame.f_code.co_filename)
                != expected_adapter_path
            ):
                raise FormalQcTransportError(
                    "delegated transport minter registration changed"
                )
            delegated_minter_provenance = (
                *delegated_minter_provenance,
                (adapter_key, capture_function(function)),
            )

        # The import statement already holds the function locally.  Remove the
        # transient claim handle from both modules before returning the sole
        # minter to the adapter.
        module_globals = globals()
        module_globals.pop("_claim_adapter_capability_minter", None)
        if caller is not None:
            caller.f_globals.pop("_claim_adapter_capability_minter", None)
        del caller
        return mint, seal_formal_callers, register_delegated_minter

    def mint_offline_test_capability(
        transport: "FormalQcTransport", *, scope: str,
        call_budget: Mapping[str, int],
        binding_record: Mapping[str, object] | None = None,
    ) -> object:
        """Mint only against a credential-isolated injected test transport."""

        require_module_bindings()
        if (
            type(transport) is not FormalQcTransport
            or transport._production_ready is not False
            or transport._credentials != _OFFLINE_TEST_CREDENTIALS
        ):
            raise FormalQcTransportError(
                "offline capability requires the credential-isolated test "
                "transport"
            )
        if binding_record is None:
            binding_record = {
                "schema": "arv2-formal-qc-offline-test-capability-v1",
                "scope": scope,
            }
        binding_sha256, budget, result_family_route = capability_material(
            scope=scope,
            binding_record=binding_record,
            call_budget=call_budget,
        )
        capability = Capability(
            scope, binding_sha256, budget, id(transport), False,
            result_family_route, sentinel,
        )
        register(capability, transport, budget)
        return capability

    event_type = type(threading.Event())

    def hold_offline_test_authority_lock(
        transport: "FormalQcTransport",
        entered: threading.Event,
        release: threading.Event,
    ) -> None:
        """Hold the private lock only for the POSIX fork-reset regression."""

        if (
            type(transport) is not FormalQcTransport
            or transport._production_ready is not False
            or transport._credentials != _OFFLINE_TEST_CREDENTIALS
            or type(entered) is not event_type
            or type(release) is not event_type
        ):
            raise FormalQcTransportError(
                "authority-lock test seam requires an offline transport"
            )
        with authority_lock:
            entered.set()
            if not release.wait(15):
                raise FormalQcTransportError(
                    "authority-lock test seam timed out"
                )

    def require_capability(
        value: object, *, transport: "FormalQcTransport", scope: str,
        path: str | None = None, consume: bool = False,
        result_family_route: tuple[int, str, str] | None = None,
    ) -> object:
        nonlocal states

        require_module_bindings()
        if type(value) is not Capability:
            raise FormalQcTransportError(
                "adapter-minted transport capability is required"
            )
        with authority_lock:
            state_index = next(
                (
                    index for index, (key, _entry) in enumerate(states)
                    if key == id(value)
                ),
                None,
            )
            state = (
                None if state_index is None else states[state_index][1]
            )
            if (
                state is None
                or len(state) != 19
                or state[0] is not value
                or state[1] is not transport
                or state[3] != get_pid()
                or value._sentinel is not sentinel
                or value.scope is not state[5]
                or value.binding_sha256 is not state[6]
                or value.call_budget is not state[7]
                or value.transport_identity is not state[8]
                or value.production_transport is not state[9]
                or value.result_family_route is not state[10]
                or value.capability_sha256 is not state[11]
                or state[9] is not state[12]
                or value.scope != scope
                or value.transport_identity != id(transport)
                or transport._production_ready is not state[12]
                or transport._http is not state[13]
                or transport._base_url is not state[14]
                or transport._clock is not state[15]
                or transport._timeout is not state[16]
                or transport._credentials is not state[17]
                or (
                    state[18] is not None
                    and (
                        exact_type(state[18]) is not exact_tuple
                        or len(state[18]) != 2
                        or get_attribute(
                            transport._credentials,
                            "user_id",
                            missing_closure_value,
                        ) is not state[18][0]
                        or get_attribute(
                            transport._credentials,
                            "api_token",
                            missing_closure_value,
                        ) is not state[18][1]
                    )
                )
            ):
                raise FormalQcTransportError(
                    "transport capability state changed"
                )
            encoded = json.dumps(
                [
                    value.scope, value.binding_sha256,
                    list(value.call_budget), value.transport_identity,
                    value.production_transport, value.result_family_route,
                ],
                separators=(",", ":"), sort_keys=False,
            ).encode("ascii")
            if (
                hashlib.sha256(encoded).hexdigest()
                != value.capability_sha256
            ):
                raise FormalQcTransportError(
                    "adapter-minted transport capability is required"
                )
        if path is not None:
            with authority_lock:
                current_state = next(
                    (
                        entry for key, entry in states
                        if key == id(value)
                    ),
                    None,
                )
                if current_state is not state:
                    raise FormalQcTransportError(
                        "transport capability state changed"
                    )
                remaining = dict(state[2])
                next_result_family_key = state[4]
                if scope == "result_family_read":
                    bound_route = value.result_family_route
                    if (
                        path != "object/read"
                        or type(result_family_route) is not tuple
                        or len(result_family_route) != 3
                        or bound_route is None
                        or result_family_route[0] != bound_route[0]
                        or result_family_route[1] != bound_route[1]
                        or next_result_family_key >= len(bound_route[2])
                        or result_family_route[2]
                        != bound_route[2][next_result_family_key]
                    ):
                        raise FormalQcTransportError(
                            "formal result-family route changed"
                        )
                elif result_family_route is not None:
                    raise FormalQcTransportError(
                        "formal result-family route escaped its capability"
                    )
                if path not in remaining or remaining[path] < 1:
                    raise FormalQcTransportError(
                        "transport capability call budget exhausted"
                    )
                if consume:
                    updated = dict(remaining)
                    updated[path] -= 1
                    assert state_index is not None
                    replacement = (
                        state[0], state[1], tuple(sorted(updated.items())),
                        state[3], next_result_family_key + (
                            1 if scope == "result_family_read" else 0
                        ),
                        *state[5:],
                    )
                    states = (
                        *states[:state_index],
                        (id(value), replacement),
                        *states[state_index + 1:],
                    )
        return value

    def consume_capability_for_path(
        value: object, *, transport: "FormalQcTransport", path: str,
        result_family_route: tuple[int, str, str] | None = None,
    ) -> object:
        """Authenticate and spend one exact route without exposing a checker."""

        require_module_bindings()
        if type(value) is not Capability:
            raise FormalQcTransportError(
                "adapter-minted transport capability is required"
            )
        if path == "backtests/list":
            expected_scope = "status"
        elif path == "backtests/read":
            expected_scope = "result_read"
        elif path == "object/read" and value.scope in {
            "preopen_output_read",
            "power_calibration_output_read",
            "result_family_read",
        }:
            expected_scope = value.scope
        else:
            expected_scope = "submission"
        require_capability(
            value,
            transport=transport,
            scope=expected_scope,
            path=path,
            consume=True,
            result_family_route=result_family_route,
        )
        state = next(
            entry for key, entry in states if key == id(value)
        )
        return (
            state[9], state[13], state[14], state[15], state[16], state[17],
            state[18],
            *request_dependencies,
        )

    def require_request_module_bindings(value: object) -> None:
        """Refuse a mutated production namespace before request parsing."""

        del value
        require_module_bindings()

    def reset_after_fork() -> None:
        nonlocal states, authority_lock
        states = ()
        authority_lock = threading.RLock()

    offline_mint_code = mint_offline_test_capability.__code__
    offline_mint_closure = tuple(
        (name, cell.cell_contents)
        for name, cell in zip(
            mint_offline_test_capability.__code__.co_freevars,
            mint_offline_test_capability.__closure__ or (),
            strict=True,
        )
    )

    return (
        claim_adapter_minter,
        mint_offline_test_capability,
        hold_offline_test_authority_lock,
        consume_capability_for_path,
        reset_after_fork,
        seal_module_bindings,
        require_request_module_bindings,
    )


(
    _claim_adapter_capability_minter,
    _mint_offline_test_capability,
    _hold_offline_test_capability_authority_lock,
    _consume_capability_for_path,
    _reset_transport_capability_state_after_fork,
    _seal_transport_authority_global_bindings,
    _require_transport_authority_global_bindings,
) = _build_transport_capability_authority()
del _build_transport_capability_authority

if hasattr(os, "register_at_fork"):
    os.register_at_fork(
        after_in_child=_reset_transport_capability_state_after_fork
    )
del _reset_transport_capability_state_after_fork


def _strict_response_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _reject_nonstandard_json_constant(_value: str) -> object:
    raise ValueError("non-standard JSON numeric constant")


def _safe_id(value: object, name: str) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        raise FormalQcTransportError(f"{name} is not a safe identifier")
    return value


def _safe_key(value: object) -> str:
    if (
        type(value) is not str
        or _SAFE_KEY.fullmatch(value) is None
        or value.startswith("/")
        or "//" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise FormalQcTransportError("Object Store key is not safe")
    return value


def _exact_json_tree(value: object, depth: int = 0) -> bool:
    if depth > 16:
        return False
    if value is None or type(value) in (str, bool, int):
        return not (type(value) is int and abs(value) > 10**18)
    if type(value) is list:
        return all(_exact_json_tree(item, depth + 1) for item in value)
    if type(value) is dict:
        return all(
            type(key) is str
            and key.casefold().replace("_", "") not in _SECRET_KEYS
            and _exact_json_tree(item, depth + 1)
            for key, item in value.items()
        )
    return False


def _json_bytes(value: dict[str, object]) -> bytes:
    if type(value) is not dict or not _exact_json_tree(value):
        raise FormalQcTransportError("JSON request contains an unsupported value")
    try:
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise FormalQcTransportError("JSON request is not serializable") from exc
    if len(payload) > MAX_REQUEST_BYTES:
        raise FormalQcTransportError("JSON request exceeds the transport bound")
    return payload


def _multipart_boundary(exact_bytes: bytes) -> str:
    """Return the deterministic boundary; the caller must check collision."""

    return "ARV2" + hashlib.sha256(exact_bytes).hexdigest()


class FormalQcTransport:
    """Exact endpoint implementation injected into the one-shot adapter."""

    def __init__(
        self,
        *,
        base_url: str = API_BASE,
        http_transport: Callable[
            [str, bytes, Mapping[str, str], float], tuple[int, bytes]
        ] | None = None,
        clock: Callable[[], int] | None = None,
        timeout: float = PRODUCTION_TIMEOUT_SECONDS,
    ) -> None:
        if (
            type(base_url) is not str
            or base_url.rstrip("/") != API_BASE.rstrip("/")
        ):
            raise FormalQcTransportError("QuantConnect API base URL changed")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise FormalQcTransportError("transport timeout must be positive and finite")
        injected_test_seam = http_transport is not None or clock is not None
        if injected_test_seam:
            # Never load the user's environment credentials into an injected
            # callback.  The submission adapter rejects this offline seam.
            self._credentials = _OFFLINE_TEST_CREDENTIALS
        else:
            # Production credentials are acquired into a request-local value
            # only after the adapter has durably spent the one-use permit.
            self._credentials = None
        self._base_url = base_url.rstrip("/")
        self._http = http_transport or _default_http_transport
        if clock is None:
            self._clock = _production_clock
        else:
            self._clock = clock
        self._timeout = float(timeout)
        self._production_ready = (
            not injected_test_seam
            and self._http is _default_http_transport
            and self._timeout == PRODUCTION_TIMEOUT_SECONDS
        )

    def _require_production_configuration(self) -> None:
        if (
            self._production_ready is not True
            or self._http is not _default_http_transport
            or self._base_url != API_BASE.rstrip("/")
            or self._timeout != PRODUCTION_TIMEOUT_SECONDS
            or self._clock is not _production_clock
            or self._credentials is not None
        ):
            raise FormalQcTransportError(
                "injected/offline transport is forbidden for formal submission"
            )

    def _post(
        self, capability: object,
        *, path: str, body: bytes, content_type: str,
        _result_family_route: tuple[int, str, str] | None = None,
        _sealed_capability_consumer: object = None,
        _sealed_binding_guard: object = None,
    ) -> dict[str, object]:
        if path not in _POST_ENDPOINTS:
            raise FormalQcTransportError("QuantConnect endpoint is not allowlisted")
        if not callable(_sealed_capability_consumer):
            raise FormalQcTransportError(
                "transport capability authority is not sealed"
            )
        request_context = _sealed_capability_consumer(
            capability,
            transport=self,
            path=path,
            result_family_route=_result_family_route,
        )
        if (
            type(request_context) is not tuple
            or len(request_context) != 15
            or not callable(_sealed_binding_guard)
        ):
            raise FormalQcTransportError(
                "transport request authority changed"
            )
        (
            production_transport,
            http_transport,
            base_url,
            clock,
            timeout,
            credential_boundary,
            offline_credential_material,
            production_http_transport,
            production_clock,
            production_http_preparer,
            credential_loader,
            auth_header_builder,
            json_loader,
            strict_response_object,
            reject_json_constant,
        ) = request_context
        if (
            (path == "object/set" and re.fullmatch(
                r"multipart/form-data; boundary=ARV2[0-9a-f]{64}", content_type
            ) is None)
            or (path != "object/set" and content_type != "application/json")
            or type(body) is not bytes
            or len(body) > MAX_OBJECT_BYTES + 4096
        ):
            raise FormalQcTransportError("QuantConnect request envelope changed")
        if (
            self._production_ready is not production_transport
            or self._http is not http_transport
            or self._base_url is not base_url
            or self._clock is not clock
            or self._timeout is not timeout
            or self._credentials is not credential_boundary
        ):
            raise FormalQcTransportError(
                "transport configuration changed after capability mint"
            )
        prepared_http_transport = (
            production_http_preparer()
            if production_transport is True
            else http_transport
        )
        timestamp = clock()
        _sealed_binding_guard(capability)
        if type(timestamp) is not int or timestamp <= 0:
            raise FormalQcTransportError("transport clock returned an invalid timestamp")
        if (
            self._production_ready is not production_transport
            or self._http is not http_transport
            or self._base_url is not base_url
            or self._clock is not clock
            or self._timeout is not timeout
            or self._credentials is not credential_boundary
        ):
            raise FormalQcTransportError(
                "transport configuration changed during request"
            )
        if production_transport is True:
            if (
                http_transport is not production_http_transport
                or clock is not production_clock
                or credential_boundary is not None
                or offline_credential_material is not None
                or not callable(prepared_http_transport)
            ):
                raise FormalQcTransportError(
                    "production transport authority changed"
                )
            credential_material = credential_loader()
        else:
            credential_material = offline_credential_material
        if (
            type(credential_material) is not tuple
            or len(credential_material) != 2
        ):
            raise FormalQcTransportError("QuantConnect credentials boundary changed")
        headers = auth_header_builder(credential_material, timestamp)
        headers["Content-Type"] = content_type
        status, raw = prepared_http_transport(
            base_url + "/" + path,
            body,
            headers,
            timeout,
        )
        if type(status) is not int or type(raw) is not bytes or len(raw) > MAX_RESPONSE_BYTES:
            raise FormalQcTransportError("QuantConnect response envelope exceeded its bound")
        try:
            value = json_loader(
                raw.decode("utf-8"),
                object_pairs_hook=strict_response_object,
                parse_constant=reject_json_constant,
            )
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise FormalQcTransportError("QuantConnect response is not UTF-8 JSON") from exc
        if type(value) is not dict or value.get("success") is not True or status >= 400:
            # Values are intentionally not copied into this exception.
            raise FormalQcTransportError(f"QuantConnect {path} request was refused")
        return value

    def _request_json(
        self, capability: object,
        path: str, payload: dict[str, object] | None = None,
        *, _result_family_route: tuple[int, str, str] | None = None,
    ) -> dict[str, object]:
        if type(path) is not str or path not in _JSON_ENDPOINTS:
            raise FormalQcTransportError("QuantConnect endpoint is not allowlisted")
        return self._post(
            capability,
            path=path,
            body=_json_bytes({} if payload is None else payload),
            content_type="application/json",
            _result_family_route=_result_family_route,
        )

    def _set_object_multipart(
        self, capability: object,
        organization_id: str, key: str, exact_bytes: bytes
    ) -> dict[str, object]:
        organization = _safe_id(organization_id, "organization_id")
        object_key = _safe_key(key)
        if type(exact_bytes) is not bytes or not exact_bytes or len(exact_bytes) > MAX_OBJECT_BYTES:
            raise FormalQcTransportError("Object Store payload exceeds its exact bound")
        boundary = _multipart_boundary(exact_bytes)
        if type(boundary) is not str or re.fullmatch(r"ARV2[0-9a-f]{64}", boundary) is None:
            raise FormalQcTransportError("Object Store multipart boundary changed")
        if ("\r\n--" + boundary).encode("ascii") in exact_bytes:
            raise FormalQcTransportError("Object Store multipart boundary collides with payload")
        parts = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"organizationId\"\r\n\r\n{organization}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"key\"\r\n\r\n{object_key}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"objectData\"; filename=\"object.bin\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
        body = parts + exact_bytes + f"\r\n--{boundary}--\r\n".encode("ascii")
        return self._post(
            capability,
            path="object/set",
            body=body,
            content_type="multipart/form-data; boundary=" + boundary,
        )

    def _read_object_properties(
        self, capability: object,
        organization_id: str, key: str
    ) -> dict[str, object]:
        return self._request_json(
            capability, "object/properties",
            {"organizationId": _safe_id(organization_id, "organization_id"), "key": _safe_key(key)},
        )

    def _read_object_bounded(
        self, capability: object,
        organization_id: str, key: str
    ) -> dict[str, object]:
        """Read one adapter-named Object Store object through the JSON API."""

        return self._request_json(
            capability, "object/read",
            {
                "organizationId": _safe_id(
                    organization_id, "organization_id"
                ),
                "key": _safe_key(key),
            },
        )

    def _read_power_calibration_object_bounded(
        self, capability: object,
        organization_id: str, key: str
    ) -> dict[str, object]:
        """Read one calibration output under its distinct result-free scope."""

        return self._request_json(
            capability, "object/read",
            {
                "organizationId": _safe_id(
                    organization_id, "organization_id"
                ),
                "key": _safe_key(key),
            },
        )

    def _read_formal_result_family_object_bounded(
        self, capability: object,
        project_id: int, organization_id: str, key: str,
    ) -> dict[str, object]:
        """Read one exact ordered formal-result family object.

        The capability binds the completed run's project, organization, and
        complete ordered 26-key inventory.  The decoded byte check here keeps
        the base64 JSON response comfortably beneath the transport's existing
        16 MiB response ceiling; semantic gzip and descriptor reauthentication
        remain the result adapter's responsibility.
        """

        if type(project_id) is not int or project_id <= 0:
            raise FormalQcTransportError(
                "project_id is not a positive exact integer"
            )
        organization = _safe_id(organization_id, "organization_id")
        object_key = _safe_key(key)
        response = self._request_json(
            capability,
            "object/read",
            {"organizationId": organization, "key": object_key},
            _result_family_route=(project_id, organization, object_key),
        )
        if not set(response).issubset(
            {"success", "errors", "messages", "object"}
        ):
            raise FormalQcTransportError(
                "formal result-family Object Store envelope changed"
            )
        item = response.get("object")
        if (
            type(item) is not dict
            or set(item) != {"key", "objectData"}
            or item.get("key") != object_key
            or type(item.get("objectData")) is not str
        ):
            raise FormalQcTransportError(
                "formal result-family object envelope changed"
            )
        encoded = item["objectData"]
        maximum_encoded_characters = 4 * (
            (MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES + 2) // 3
        )
        if not encoded or len(encoded) > maximum_encoded_characters:
            raise FormalQcTransportError(
                "formal result-family object exceeds its byte bound"
            )
        try:
            payload = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeError, ValueError) as exc:
            raise FormalQcTransportError(
                "formal result-family object is not canonical base64"
            ) from exc
        if (
            not 0 < len(payload) <= MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES
            or base64.b64encode(payload).decode("ascii") != encoded
        ):
            raise FormalQcTransportError(
                "formal result-family object exceeds its byte bound"
            )
        return response

    def _read_backtest_result(
        self, capability: object,
        project_id: int, backtest_id: str
    ) -> dict[str, object]:
        if type(project_id) is not int or project_id <= 0:
            raise FormalQcTransportError("project_id is not a positive exact integer")
        return self._post(
            capability,
            path="backtests/read",
            body=_json_bytes(
                {"projectId": project_id,
                 "backtestId": _safe_id(backtest_id, "backtest_id")}
            ),
            content_type="application/json",
        )


def _seal_transport_request_authority(
    implementation: Callable[..., dict[str, object]],
    capability_consumer: Callable[..., object],
    binding_guard: Callable[[object], None],
) -> Callable[..., dict[str, object]]:
    """Closure-bind the sole capability consumer into the HTTP boundary."""

    def sealed_post(
        self: FormalQcTransport,
        capability: object,
        *,
        path: str,
        body: bytes,
        content_type: str,
        _result_family_route: tuple[int, str, str] | None = None,
    ) -> dict[str, object]:
        binding_guard(capability)
        return implementation(
            self,
            capability,
            path=path,
            body=body,
            content_type=content_type,
            _result_family_route=_result_family_route,
            _sealed_capability_consumer=capability_consumer,
            _sealed_binding_guard=binding_guard,
        )

    sealed_post.__name__ = implementation.__name__
    sealed_post.__qualname__ = implementation.__qualname__
    sealed_post.__doc__ = implementation.__doc__
    return sealed_post


FormalQcTransport._post = _seal_transport_request_authority(
    FormalQcTransport._post,
    _consume_capability_for_path,
    _require_transport_authority_global_bindings,
)
del _consume_capability_for_path
del _seal_transport_request_authority


def _seal_transport_request_method_authority(
    implementation: Callable[..., object],
    binding_guard: Callable[[object], None],
) -> Callable[..., object]:
    """Run the namespace guard before a request method parses arguments."""

    missing = object()

    def sealed_method(self, *args, **kwargs):
        capability = args[0] if args else kwargs.get("capability", missing)
        binding_guard(capability)
        return implementation(self, *args, **kwargs)

    sealed_method.__name__ = implementation.__name__
    sealed_method.__qualname__ = implementation.__qualname__
    sealed_method.__doc__ = implementation.__doc__
    return sealed_method


for _request_method_name in REQUEST_METHOD_NAMES:
    setattr(
        FormalQcTransport,
        _request_method_name,
        _seal_transport_request_method_authority(
            getattr(FormalQcTransport, _request_method_name),
            _require_transport_authority_global_bindings,
        ),
    )
del _request_method_name
del _require_transport_authority_global_bindings
del _seal_transport_request_method_authority


__all__ = (
    "FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT",
    "FormalQcTransport", "FormalQcTransportError",
    "MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES",
    "MAX_FORMAL_RESULT_FAMILY_TOTAL_BYTES", "MAX_OBJECT_BYTES",
    "MAX_REQUEST_BYTES", "MAX_RESPONSE_BYTES",
    "RESULT_FAMILY_READ_CAPABILITY_SCHEMA", "TRANSPORT_SCHEMA",
)


_seal_transport_authority_global_bindings()
del _seal_transport_authority_global_bindings
