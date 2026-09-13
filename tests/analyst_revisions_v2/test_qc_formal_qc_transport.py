import base64
import hashlib
import importlib.util
import json
import os
import sys
import threading

import pytest

from research.analyst_revisions_v2_qc import formal_qc_transport as transport
from research.analyst_revisions_v2_qc import formal_submission_adapter as adapter


PROJECT_ID = 24680
ORGANIZATION_ID = "arv2-test-org"
DESCRIPTOR_ROOT_SHA256 = "d" * 64
OBJECT_KEYS = tuple(
    "24680/arv2/formal/output/report-families/"
    + f"{ordinal:02d}-"
    + f"{ordinal:064x}"
    + ".json.gz"
    for ordinal in range(transport.FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT)
)


def _binding(
    *,
    project_id=PROJECT_ID,
    organization_id=ORGANIZATION_ID,
    descriptor_root_sha256=DESCRIPTOR_ROOT_SHA256,
    object_store_keys=OBJECT_KEYS,
):
    return {
        "schema": transport.RESULT_FAMILY_READ_CAPABILITY_SCHEMA,
        "project_id": project_id,
        "organization_id": organization_id,
        "descriptor_root_sha256": descriptor_root_sha256,
        "object_store_keys": list(object_store_keys),
        "result_authority_sha256": "a" * 64,
    }


def _response(key, payload=b"formal-family-gzip-placeholder"):
    return json.dumps(
        {
            "success": True,
            "object": {
                "key": key,
                "objectData": base64.b64encode(payload).decode("ascii"),
            },
        },
        separators=(",", ":"),
    ).encode("ascii")


def _client(http):
    return transport.FormalQcTransport(
        http_transport=http, clock=lambda: 1_789_000_000
    )


def _closure_value(function, name):
    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    return cells[name].cell_contents


def _capability(client, *, binding=None, budget=None):
    return transport._mint_offline_test_capability(
        client,
        scope="result_family_read",
        binding_record=_binding() if binding is None else binding,
        call_budget=(
            {"object/read": transport.FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT}
            if budget is None
            else budget
        ),
    )


def test_result_family_transport_surface_and_exact_capacity_constants():
    assert (
        "_read_formal_result_family_object_bounded"
        in transport.REQUEST_METHOD_NAMES
    )
    assert transport.FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT == 26
    assert transport.MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES == 4_200_000
    assert transport.MAX_FORMAL_RESULT_FAMILY_TOTAL_BYTES == 109_200_000
    assert (
        transport.MAX_FORMAL_RESULT_FAMILY_TOTAL_BYTES
        == transport.FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT
        * transport.MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES
    )


def test_transport_capability_raw_authority_names_are_absent_after_adapter_claim():
    assert adapter.__name__.endswith(".formal_submission_adapter")
    assert not any(
        hasattr(transport, name)
        for name in (
            "_CAPABILITY_SENTINEL",
            "_CAPABILITY_STATE",
            "_CAPABILITY_STATE_LOCK",
            "_FormalQcTransportCapability",
            "_ADAPTER_MINTER_CLAIMED",
            "_capability_material",
            "_result_family_route_material",
            "_require_capability",
            "_consume_capability_for_path",
            "_reset_transport_capability_state_after_fork",
            "_claim_adapter_capability_minter",
            "_build_transport_capability_authority",
            "_seal_transport_request_authority",
        )
    )


def test_transport_production_minter_cannot_be_preclaimed_by_an_importer():
    specification = importlib.util.spec_from_file_location(
        "arv2_isolated_formal_qc_transport", transport.__file__
    )
    assert specification is not None and specification.loader is not None
    isolated = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = isolated
    try:
        specification.loader.exec_module(isolated)
    finally:
        sys.modules.pop(specification.name, None)
    with pytest.raises(
        isolated.FormalQcTransportError, match="adapter-private"
    ):
        isolated._claim_adapter_capability_minter()
    spoofed_adapter_globals = {
        "__name__": adapter.__name__,
        "claim": isolated._claim_adapter_capability_minter,
    }
    spoofed_adapter_code = compile(
        "claim()", adapter.__file__, "exec"
    )
    with pytest.raises(
        isolated.FormalQcTransportError, match="adapter-private"
    ):
        exec(spoofed_adapter_code, spoofed_adapter_globals)
    assert hasattr(isolated, "_claim_adapter_capability_minter")


def test_reflected_transport_authority_cannot_inject_or_self_mint():
    """The former closure-dict exploit is inert before credential access."""

    client = transport.FormalQcTransport()
    consumer = _closure_value(
        transport.FormalQcTransport._post, "capability_consumer"
    )
    require_capability = _closure_value(consumer, "require_capability")
    capability_type = _closure_value(require_capability, "Capability")
    sentinel = _closure_value(require_capability, "sentinel")
    states = _closure_value(require_capability, "states")
    assert type(states) is tuple
    assert not hasattr(states, "__setitem__")

    forged = capability_type(
        "submission",
        "0" * 64,
        (("authenticate", 1),),
        id(client),
        True,
        None,
        sentinel,
    )
    with pytest.raises(
        transport.FormalQcTransportError, match="state changed"
    ):
        consumer(forged, transport=client, path="authenticate")

    production_minter = _closure_value(
        adapter.inspect_statistics_free_terminal_status,
        "transport_capability_minter",
    )
    register = _closure_value(production_minter, "register")
    with pytest.raises(
        transport.FormalQcTransportError, match="register caller changed"
    ):
        register(forged, client, (("authenticate", 1),))
    with pytest.raises(
        transport.FormalQcTransportError, match="minter caller changed"
    ):
        production_minter(
            transport=client,
            scope="submission",
            binding_record={"schema": "reflected-forge"},
            call_budget={"authenticate": 1},
        )


@pytest.mark.parametrize(
    "budget",
    (
        {"object/read": 25},
        {"object/read": 27},
        {"object/read": 26, "backtests/read": 1},
        {"backtests/read": 26},
    ),
)
def test_result_family_capability_requires_exact_26_read_budget(budget):
    client = _client(lambda *_args: (200, b'{"success":true}'))
    with pytest.raises(
        transport.FormalQcTransportError,
        match="budget|path",
    ):
        _capability(client, budget=budget)


@pytest.mark.parametrize(
    "binding",
    (
        _binding(project_id=True),
        _binding(project_id=0),
        _binding(organization_id="../hostile"),
        _binding(descriptor_root_sha256="D" * 64),
        _binding(object_store_keys=OBJECT_KEYS[:-1]),
        _binding(object_store_keys=OBJECT_KEYS[:-1] + (OBJECT_KEYS[0],)),
        _binding(
            object_store_keys=("/absolute/key",) + OBJECT_KEYS[1:]
        ),
        {**_binding(), "schema": "hostile-result-family-capability"},
    ),
)
def test_result_family_capability_rejects_hostile_route_binding(binding):
    client = _client(lambda *_args: (200, b'{"success":true}'))
    with pytest.raises(transport.FormalQcTransportError):
        _capability(client, binding=binding)


def test_result_family_scope_cannot_cross_result_or_object_routes():
    calls = []

    def http(*args):
        calls.append(args)
        return 200, _response(OBJECT_KEYS[0])

    client = _client(http)
    family = _capability(client)
    result = transport._mint_offline_test_capability(
        client, scope="result_read", call_budget={"backtests/read": 1}
    )
    with pytest.raises(transport.FormalQcTransportError, match="capability"):
        client._read_formal_result_family_object_bounded(
            result, PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
        )
    with pytest.raises(transport.FormalQcTransportError, match="capability"):
        client._read_backtest_result(family, PROJECT_ID, "backtest-id")
    with pytest.raises(transport.FormalQcTransportError, match="capability"):
        client._request_json(
            family,
            "object/properties",
            {"organizationId": ORGANIZATION_ID, "key": OBJECT_KEYS[0]},
        )
    with pytest.raises(
        transport.FormalQcTransportError, match="route"
    ):
        client._request_json(
            family,
            "object/read",
            {"organizationId": ORGANIZATION_ID, "key": OBJECT_KEYS[0]},
        )
    assert calls == []


def test_result_family_read_enforces_project_organization_and_ordered_keys():
    calls = []

    def http(url, body, headers, timeout):
        del url, headers, timeout
        request = json.loads(body)
        calls.append(request)
        return 200, _response(request["key"])

    client = _client(http)
    capability = _capability(client)
    hostile_routes = (
        (PROJECT_ID + 1, ORGANIZATION_ID, OBJECT_KEYS[0]),
        (PROJECT_ID, "another-org", OBJECT_KEYS[0]),
        (PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[1]),
    )
    for project_id, organization_id, key in hostile_routes:
        with pytest.raises(
            transport.FormalQcTransportError, match="route"
        ):
            client._read_formal_result_family_object_bounded(
                capability, project_id, organization_id, key
            )
    first = client._read_formal_result_family_object_bounded(
        capability, PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
    )
    assert first["object"]["key"] == OBJECT_KEYS[0]
    with pytest.raises(transport.FormalQcTransportError, match="route"):
        client._read_formal_result_family_object_bounded(
            capability, PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
        )
    second = client._read_formal_result_family_object_bounded(
        capability, PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[1]
    )
    assert second["object"]["key"] == OBJECT_KEYS[1]
    assert calls == [
        {"organizationId": ORGANIZATION_ID, "key": OBJECT_KEYS[0]},
        {"organizationId": ORGANIZATION_ID, "key": OBJECT_KEYS[1]},
    ]


def test_result_family_capability_permits_exactly_26_ordered_reads():
    calls = []

    def http(_url, body, _headers, _timeout):
        key = json.loads(body)["key"]
        calls.append(key)
        return 200, _response(key)

    client = _client(http)
    capability = _capability(client)
    for key in OBJECT_KEYS:
        client._read_formal_result_family_object_bounded(
            capability, PROJECT_ID, ORGANIZATION_ID, key
        )
    with pytest.raises(
        transport.FormalQcTransportError, match="route|budget"
    ):
        client._read_formal_result_family_object_bounded(
            capability, PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[-1]
        )
    assert calls == list(OBJECT_KEYS)


@pytest.mark.parametrize(
    "response",
    (
        b'{"success":true,"unexpected":true}',
        b'{"success":true,"object":{"key":"wrong","objectData":"YQ=="}}',
        (
            b'{"success":true,"object":{"key":"'
            + OBJECT_KEYS[0].encode("ascii")
            + b'","objectData":"YQ==","extra":false}}'
        ),
        (
            b'{"success":true,"object":{"key":"'
            + OBJECT_KEYS[0].encode("ascii")
            + b'","objectData":"not base64"}}'
        ),
        (
            b'{"success":true,"object":{"key":"'
            + OBJECT_KEYS[0].encode("ascii")
            + b'","objectData":""}}'
        ),
    ),
)
def test_result_family_read_rejects_hostile_object_envelopes(response):
    calls = []

    def http(*args):
        calls.append(args)
        return 200, response

    client = _client(http)
    with pytest.raises(transport.FormalQcTransportError):
        client._read_formal_result_family_object_bounded(
            _capability(client),
            PROJECT_ID,
            ORGANIZATION_ID,
            OBJECT_KEYS[0],
        )
    assert len(calls) == 1


def test_result_family_read_rejects_decoded_object_above_4_2_mb():
    oversized = b"x" * (transport.MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES + 1)

    def http(*_args):
        return 200, _response(OBJECT_KEYS[0], oversized)

    client = _client(http)
    with pytest.raises(
        transport.FormalQcTransportError, match="byte bound"
    ):
        client._read_formal_result_family_object_bounded(
            _capability(client),
            PROJECT_ID,
            ORGANIZATION_ID,
            OBJECT_KEYS[0],
        )


def test_result_family_read_rejects_transport_response_above_16_mib():
    response = (
        b'{"success":true,"padding":"'
        + b"x" * transport.MAX_RESPONSE_BYTES
        + b'"}'
    )

    def http(*_args):
        return 200, response

    client = _client(http)
    with pytest.raises(
        transport.FormalQcTransportError, match="response envelope"
    ):
        client._read_formal_result_family_object_bounded(
            _capability(client),
            PROJECT_ID,
            ORGANIZATION_ID,
            OBJECT_KEYS[0],
        )


def test_result_family_capability_mutation_revokes_before_http():
    calls = []

    def http(*args):
        calls.append(args)
        return 200, _response(OBJECT_KEYS[0])

    client = _client(http)
    capability = _capability(client)
    capability.result_family_route = (
        PROJECT_ID,
        ORGANIZATION_ID,
        tuple(reversed(OBJECT_KEYS)),
    )
    with pytest.raises(transport.FormalQcTransportError, match="capability"):
        client._read_formal_result_family_object_bounded(
            capability, PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
        )
    assert calls == []


def test_public_registry_and_sentinel_lookalikes_cannot_reseal_spent_authority(
    monkeypatch,
):
    calls = []

    def http(*args):
        calls.append(args)
        return 200, b'{"success":true}'

    client = _client(http)
    capability = transport._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1}
    )
    client._request_json(capability, "authenticate", {})
    monkeypatch.setattr(transport, "_CAPABILITY_SENTINEL", object(), raising=False)
    monkeypatch.setattr(
        transport,
        "_CAPABILITY_STATE",
        {
            id(capability): (
                capability,
                client,
                {"authenticate": 1},
                os.getpid(),
                0,
            )
        },
        raising=False,
    )
    monkeypatch.setattr(transport, "_CAPABILITY_STATE_LOCK", threading.RLock(), raising=False)
    monkeypatch.setattr(
        transport,
        "_require_capability",
        lambda *_args, **_kwargs: capability,
        raising=False,
    )
    with pytest.raises(
        transport.FormalQcTransportError,
        match="capability authority changed",
    ):
        client._request_json(capability, "authenticate", {})
    assert len(calls) == 1


def test_reflected_production_minter_refuses_injected_builtin_before_access(
    monkeypatch,
):
    calls = []

    def http(*args):
        calls.append(args)
        return 200, b'{"success":true}'

    client = _client(http)
    minter = _closure_value(
        adapter.inspect_statistics_free_terminal_status,
        "transport_capability_minter",
    )
    hostile_calls = []

    def hostile_any(values):
        hostile_calls.append(values)
        return True

    monkeypatch.setattr(transport, "any", hostile_any, raising=False)
    with pytest.raises(
        transport.FormalQcTransportError,
        match="capability authority changed",
    ):
        minter(
            transport=client,
            scope="submission",
            binding_record={"schema": "audit-direct-reflected"},
            call_budget={"authenticate": 1},
        )
    assert hostile_calls == []
    assert calls == []


def test_post_mint_namespace_injection_refuses_before_http(monkeypatch):
    calls = []

    def http(*args):
        calls.append(args)
        return 200, b'{"success":true}'

    client = _client(http)
    capability = transport._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1}
    )
    hostile_calls = []

    def hostile_type(value):
        hostile_calls.append(value)
        return type(value)

    monkeypatch.setattr(transport, "type", hostile_type, raising=False)
    with pytest.raises(
        transport.FormalQcTransportError,
        match="capability authority changed",
    ):
        client._request_json(capability, "authenticate", {})
    assert hostile_calls == []
    assert calls == []


def test_rebound_auth_base64_refuses_before_secret_or_http(monkeypatch):
    calls = []
    hostile_inputs = []

    def http(*args):
        calls.append(args)
        return 200, b'{"success":true}'

    client = _client(http)
    capability = transport._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1}
    )

    def hostile_b64encode(value):
        hostile_inputs.append(value)
        return base64.b64encode(value)

    monkeypatch.setattr(transport.base64, "b64encode", hostile_b64encode)
    with pytest.raises(
        transport.FormalQcTransportError,
        match="capability authority changed",
    ):
        client._request_json(capability, "authenticate", {})
    assert hostile_inputs == []
    assert calls == []


def test_rebound_request_constructor_refuses_before_headers_or_http(
    monkeypatch,
):
    calls = []
    hostile_inputs = []

    def http(*args):
        calls.append(args)
        return 200, b'{"success":true}'

    client = _client(http)
    capability = transport._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1}
    )
    original_init = transport.request.Request.__init__

    def hostile_init(self, *args, **kwargs):
        hostile_inputs.append((args, kwargs))
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(transport.request.Request, "__init__", hostile_init)
    with pytest.raises(
        transport.FormalQcTransportError,
        match="capability authority changed",
    ):
        client._request_json(capability, "authenticate", {})
    assert hostile_inputs == []
    assert calls == []


@pytest.mark.parametrize(
    ("class_name", "method_name"),
    (("JSONDecoder", "__init__"), ("JSONEncoder", "__init__")),
)
def test_rebound_json_codec_refuses_before_callback_or_http(
    monkeypatch, class_name, method_name,
):
    calls = []
    hostile_inputs = []

    def http(*args):
        calls.append(args)
        return 200, b'{"success":true}'

    client = _client(http)
    capability = transport._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1}
    )
    codec_type = getattr(transport.json, class_name)
    original = getattr(codec_type, method_name)

    def hostile_method(self, *args, **kwargs):
        hostile_inputs.append((args, kwargs))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(codec_type, method_name, hostile_method)
    with pytest.raises(
        transport.FormalQcTransportError,
        match="capability authority changed",
    ):
        client._request_json(capability, "authenticate", {})
    assert hostile_inputs == []
    assert calls == []


def test_clock_cannot_redirect_post_mint_request_with_capability_flag_pair():
    safe_calls = []
    hostile_calls = []
    state = {}

    def safe_http(*args):
        safe_calls.append(args)
        return 200, b'{"success":true}'

    def hostile_http(*args):
        hostile_calls.append(args)
        return 200, b'{"success":true}'

    def mutating_clock():
        state["capability"].production_transport = True
        state["client"]._http = hostile_http
        return 1_789_000_000

    client = transport.FormalQcTransport(
        http_transport=safe_http,
        clock=mutating_clock,
    )
    capability = transport._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1}
    )
    state.update(client=client, capability=capability)
    with pytest.raises(
        transport.FormalQcTransportError,
        match="configuration changed",
    ):
        client._request_json(capability, "authenticate", {})
    assert safe_calls == []
    assert hostile_calls == []


def test_isolated_transport_import_does_not_create_tls_context(monkeypatch):
    context_calls = []

    def hostile_context_factory(*args, **kwargs):
        context_calls.append((args, kwargs))
        raise AssertionError("TLS context creation is import-time I/O")

    monkeypatch.setattr(
        transport.ssl,
        "create_default_context",
        hostile_context_factory,
    )
    specification = importlib.util.spec_from_file_location(
        "arv2_isolated_formal_qc_transport_no_tls_io",
        transport.__file__,
    )
    assert specification is not None and specification.loader is not None
    isolated = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = isolated
    try:
        specification.loader.exec_module(isolated)
    finally:
        sys.modules.pop(specification.name, None)
    assert context_calls == []


def test_offline_capability_cannot_be_data_mutated_into_production():
    calls = []

    def http(*args):
        calls.append(args)
        return 200, b'{"success":true}'

    client = _client(http)
    capability = transport._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1}
    )
    client._production_ready = True
    client._http = transport._default_http_transport
    client._base_url = transport.API_BASE.rstrip("/")
    client._timeout = transport.PRODUCTION_TIMEOUT_SECONDS
    client._clock = transport._production_clock
    client._credentials = None
    capability.production_transport = True
    encoded = json.dumps(
        [
            capability.scope,
            capability.binding_sha256,
            list(capability.call_budget),
            capability.transport_identity,
            capability.production_transport,
            capability.result_family_route,
        ],
        separators=(",", ":"),
        sort_keys=False,
    ).encode("ascii")
    capability.capability_sha256 = hashlib.sha256(encoded).hexdigest()
    with pytest.raises(
        transport.FormalQcTransportError,
        match="capability state changed",
    ):
        client._post(
            capability,
            path="authenticate",
            body="not-bytes",
            content_type="application/json",
        )
    assert calls == []


def test_transport_authority_seals_exact_module_name_census():
    minter = _closure_value(
        adapter.inspect_statistics_free_terminal_status,
        "transport_capability_minter",
    )
    binding_guard = _closure_value(minter, "require_module_bindings")
    expected_names = _closure_value(binding_guard, "expected_module_names")
    excluded = _closure_value(binding_guard, "excluded_module_names")
    assert expected_names == tuple(sorted(
        name for name in vars(transport)
        if not name.startswith("__") and name not in excluded
    ))


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_result_family_capability_is_cleared_in_child_and_remains_live_in_parent():
    calls = []

    def http(*args):
        calls.append(args)
        return 200, _response(OBJECT_KEYS[0])

    client = _client(http)
    capability = _capability(client)
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - reported through the pipe
        os.close(read_descriptor)
        try:
            client._read_formal_result_family_object_bounded(
                capability, PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
            )
        except transport.FormalQcTransportError:
            outcome = b"refused"
        else:
            outcome = b"accepted"
        os.write(write_descriptor, outcome)
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    outcome = os.read(read_descriptor, 32)
    os.close(read_descriptor)
    _, status = os.waitpid(child, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert outcome == b"refused"
    assert calls == []
    client._read_formal_result_family_object_bounded(
        capability, PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
    )
    assert len(calls) == 1


@pytest.mark.skipif(
    not hasattr(os, "fork") or not hasattr(os, "register_at_fork"),
    reason="requires POSIX fork reset semantics",
)
def test_child_resets_inherited_held_private_authority_lock():
    calls = []

    def http(*args):
        calls.append(args)
        return 200, _response(OBJECT_KEYS[0])

    client = _client(http)
    capability = _capability(client)
    entered = threading.Event()
    release = threading.Event()
    holder = threading.Thread(
        target=transport._hold_offline_test_capability_authority_lock,
        args=(client, entered, release),
    )
    holder.start()
    assert entered.wait(5)
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - reported through the pipe
        os.close(read_descriptor)
        try:
            client._read_formal_result_family_object_bounded(
                capability, PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
            )
        except transport.FormalQcTransportError:
            outcome = b"refused"
        except BaseException as exc:
            outcome = (f"{type(exc).__name__}:{exc}").encode("utf-8")[:500]
        else:
            outcome = b"accepted"
        os.write(write_descriptor, outcome)
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    outcome = os.read(read_descriptor, 512)
    os.close(read_descriptor)
    _, status = os.waitpid(child, 0)
    release.set()
    holder.join(timeout=5)
    assert not holder.is_alive()
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert outcome == b"refused"
    assert calls == []
    client._read_formal_result_family_object_bounded(
        capability, PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
    )
    assert len(calls) == 1


def _loopback_servers(redirect_code):
    import http.server

    seen = {"first": None, "second": None}

    class Second(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self._answer()

        def do_POST(self):
            self._answer()

        def _answer(self):
            seen["second"] = {name.lower(): value for name, value in self.headers.items()}
            body = b'{"success":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    second = http.server.HTTPServer(("127.0.0.1", 0), Second)

    class First(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen["first"] = {name.lower(): value for name, value in self.headers.items()}
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(redirect_code)
            self.send_header(
                "Location", f"http://127.0.0.1:{second.server_port}/collect"
            )
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    first = http.server.HTTPServer(("127.0.0.1", 0), First)
    return first, second, seen


@pytest.mark.parametrize("redirect_code", (301, 302, 303, 307, 308))
def test_production_http_primitive_refuses_every_redirect(redirect_code):
    """A 3xx from the pinned host must never issue a second request."""

    first, second, seen = _loopback_servers(redirect_code)
    workers = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (first, second)
    ]
    for worker in workers:
        worker.start()
    try:
        status, raw = transport._prepare_production_http_transport()(
            f"http://127.0.0.1:{first.server_port}/authenticate",
            b"{}",
            {"Authorization": "Basic fixture-only", "Timestamp": "1"},
            5.0,
        )
    finally:
        for server in (first, second):
            server.shutdown()
            server.server_close()

    assert seen["first"]["authorization"] == "Basic fixture-only"
    assert seen["first"]["timestamp"] == "1"
    assert seen["second"] is None
    assert status == redirect_code
    assert raw == b""


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [
        (200, b'{"success":false,"errors":["fixture"]}', "request was refused"),
        (199, b'{"success":true}', "request was refused"),
        (301, b'{"success":true}', "request was refused"),
        (403, b'{"success":true}', "request was refused"),
        (200, b"not json", "not UTF-8 JSON"),
    ],
)
def test_request_json_refuses_failed_envelopes_and_error_statuses(
    status, body, message
):
    client = _client(lambda *args: (status, body))
    capability = transport._mint_offline_test_capability(
        client, scope="submission", call_budget={"authenticate": 1}
    )
    with pytest.raises(transport.FormalQcTransportError, match=message):
        client._request_json(capability, "authenticate", {})


def test_production_http_primitive_wraps_network_failure_without_detail():
    with pytest.raises(transport.FormalQcTransportError) as excinfo:
        transport._prepare_production_http_transport()(
            "http://127.0.0.1:1/authenticate",
            b"{}",
            {"Authorization": "Basic fixture-only"},
            2.0,
        )
    assert str(excinfo.value) == "QuantConnect network request failed"
    assert excinfo.value.__cause__ is None
