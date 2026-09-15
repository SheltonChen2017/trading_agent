import base64
import hashlib
import importlib.util
import io
import json
import os
import sys
import threading
import zipfile

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
    + "-json.gz"
    for ordinal in range(transport.FORMAL_RESULT_FAMILY_OBJECT_READ_COUNT)
)
OBJECT_GET_JOB_ID = "2585354eb2e23cbbc4ba714332884650"
SIGNED_DOWNLOAD_URL = (
    "https://object-download.quantconnect.com/arv2-object.zip?signature=fixture"
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


def _object_get_response(*, job_id=OBJECT_GET_JOB_ID, url=SIGNED_DOWNLOAD_URL, **extra):
    return json.dumps(
        {
            "jobId": job_id,
            "url": url,
            "success": True,
            "errors": [],
            **extra,
        },
        separators=(",", ":"),
    ).encode("ascii")


def _object_archive(
    key, payload=b"formal-family-gzip-placeholder", *, member_name=None,
):
    return _object_archive_members(
        ((key if member_name is None else member_name, payload),)
    )


def _object_archive_members(members):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members:
            archive.writestr(name, payload)
    return output.getvalue()


def _ready_object_http(calls, *, payload=b"formal-family-gzip-placeholder"):
    state = {}

    def http(url, body, headers, timeout):
        calls.append((url, body, dict(headers), timeout))
        if url.endswith("/object/get"):
            request = json.loads(body)
            assert request == {
                "organizationId": ORGANIZATION_ID,
                "keys": [request["keys"][0]],
            }
            state["key"] = request["keys"][0]
            return 200, _object_get_response()
        assert url == SIGNED_DOWNLOAD_URL
        assert body == b""
        assert headers == {}
        return 200, _object_archive(state.pop("key"), payload)

    return http


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
        return 200, b'{"success":true}'

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


def test_files_delete_requires_exact_submission_scope_and_one_call_budget():
    calls = []

    def http(url, body, _headers, _timeout):
        calls.append((url, json.loads(body)))
        return 200, b'{"success":true}'

    client = _client(http)
    capability = transport._mint_offline_test_capability(
        client,
        scope="submission",
        call_budget={"files/delete": 1},
    )
    payload = {"projectId": PROJECT_ID, "name": "research.ipynb"}
    assert client._request_json(capability, "files/delete", payload) == {
        "success": True
    }
    assert calls == [
        (
            "https://www.quantconnect.com/api/v2/files/delete",
            payload,
        )
    ]

    with pytest.raises(transport.FormalQcTransportError, match="budget"):
        client._request_json(capability, "files/delete", payload)
    unbudgeted = transport._mint_offline_test_capability(
        client,
        scope="submission",
        call_budget={"authenticate": 1},
    )
    with pytest.raises(transport.FormalQcTransportError, match="budget"):
        client._request_json(unbudgeted, "files/delete", payload)
    for scope in (
        "status",
        "preopen_output_read",
        "power_calibration_output_read",
        "result_read",
        "result_family_read",
    ):
        with pytest.raises(
            transport.FormalQcTransportError,
            match="path budget changed",
        ):
            transport._mint_offline_test_capability(
                client,
                scope=scope,
                call_budget={"files/delete": 1},
            )
    assert len(calls) == 1


def test_result_family_read_enforces_project_organization_and_ordered_keys():
    calls = []
    client = _client(_ready_object_http(calls))
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
    assert [json.loads(body) for url, body, _headers, _timeout in calls
            if url.endswith("/object/get")] == [
        {"organizationId": ORGANIZATION_ID, "keys": [OBJECT_KEYS[0]]},
        {"organizationId": ORGANIZATION_ID, "keys": [OBJECT_KEYS[1]]},
    ]
    assert len(calls) == 4


def test_result_family_capability_permits_exactly_26_ordered_reads():
    calls = []
    client = _client(_ready_object_http(calls))
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
    assert [
        json.loads(body)["keys"][0]
        for url, body, _headers, _timeout in calls
        if url.endswith("/object/get")
    ] == list(OBJECT_KEYS)
    assert len(calls) == 2 * len(OBJECT_KEYS)


def test_object_get_nullable_url_polls_same_org_and_job_then_synthesizes_envelope():
    calls = []

    def http(url, body, headers, timeout):
        calls.append((url, body, dict(headers), timeout))
        if len(calls) == 1:
            return 200, _object_get_response(url=None)
        if len(calls) == 2:
            # The official response model makes jobId optional.  The request
            # remains bound to the original job even when QC omits the echo.
            return 200, _object_get_response(job_id=None)
        return 200, _object_archive(OBJECT_KEYS[0], b"exact-object")

    client = _client(http)
    response = client._read_formal_result_family_object_bounded(
        _capability(client), PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
    )
    assert response == {
        "success": True,
        "object": {
            "key": OBJECT_KEYS[0],
            "objectData": base64.b64encode(b"exact-object").decode("ascii"),
        },
    }
    assert json.loads(calls[0][1]) == {
        "organizationId": ORGANIZATION_ID,
        "keys": [OBJECT_KEYS[0]],
    }
    assert json.loads(calls[1][1]) == {
        "organizationId": ORGANIZATION_ID,
        "jobId": OBJECT_GET_JOB_ID,
    }
    assert calls[0][0].endswith("/object/get")
    assert calls[1][0].endswith("/object/get")
    assert calls[2][0] == SIGNED_DOWNLOAD_URL
    assert calls[2][1] == b""
    assert calls[2][2] == {}
    assert "Authorization" in calls[0][2]
    assert "Timestamp" in calls[0][2]


def test_object_get_immediate_url_accepts_documented_nullable_job_id():
    calls = []

    def http(url, body, headers, timeout):
        calls.append((url, body, dict(headers), timeout))
        if url.endswith("/object/get"):
            return 200, _object_get_response(job_id=None)
        return 200, _object_archive(OBJECT_KEYS[0], b"ready")

    client = _client(http)
    response = client._read_formal_result_family_object_bounded(
        _capability(client), PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
    )
    assert base64.b64decode(response["object"]["objectData"]) == b"ready"
    assert len(calls) == 2


def test_object_get_poll_rejects_changed_job_identity_before_download():
    calls = []

    def http(url, body, headers, timeout):
        calls.append((url, body, dict(headers), timeout))
        if len(calls) == 1:
            return 200, _object_get_response(url=None)
        return 200, _object_get_response(job_id="different-job")

    client = _client(http)
    with pytest.raises(
        transport.FormalQcTransportError, match="job identity"
    ):
        client._read_formal_result_family_object_bounded(
            _capability(client), PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
        )
    assert len(calls) == 2
    assert json.loads(calls[1][1]) == {
        "organizationId": ORGANIZATION_ID,
        "jobId": OBJECT_GET_JOB_ID,
    }


def test_object_get_poll_budget_is_finite_and_spends_one_logical_read():
    calls = []

    def http(url, body, headers, timeout):
        calls.append((url, body, dict(headers), timeout))
        return 200, _object_get_response(url=None)

    client = _client(http)
    capability = transport._mint_offline_test_capability(
        client,
        scope="preopen_output_read",
        call_budget={"object/read": 1},
    )
    with pytest.raises(
        transport.FormalQcTransportError, match="poll budget exhausted"
    ):
        client._read_object_bounded(
            capability, ORGANIZATION_ID, OBJECT_KEYS[0]
        )
    assert len(calls) == transport.OBJECT_GET_MAX_API_CALLS
    assert json.loads(calls[0][1]) == {
        "organizationId": ORGANIZATION_ID,
        "keys": [OBJECT_KEYS[0]],
    }
    assert all(
        json.loads(body) == {
            "organizationId": ORGANIZATION_ID,
            "jobId": OBJECT_GET_JOB_ID,
        }
        for _url, body, _headers, _timeout in calls[1:]
    )
    with pytest.raises(transport.FormalQcTransportError, match="budget"):
        client._read_object_bounded(
            capability, ORGANIZATION_ID, OBJECT_KEYS[0]
        )
    assert len(calls) == transport.OBJECT_GET_MAX_API_CALLS


def test_generic_bounded_reader_accepts_compressed_object_above_json_response_cap():
    payload = b"x" * (transport.MAX_RESPONSE_BYTES + 1)
    calls = []
    client = _client(_ready_object_http(calls, payload=payload))
    capability = transport._mint_offline_test_capability(
        client,
        scope="preopen_output_read",
        call_budget={"object/read": 1},
    )
    response = client._read_object_bounded(
        capability, ORGANIZATION_ID, OBJECT_KEYS[0]
    )
    assert base64.b64decode(response["object"]["objectData"]) == payload
    assert len(calls) == 2


@pytest.mark.parametrize(
    "url",
    (
        "http://object-download.quantconnect.com/object.zip?signature=x",
        "https://evil.example/object.zip?signature=x",
        "https://127.0.0.1/object.zip?signature=x",
        "https://user@object-download.quantconnect.com/object.zip?signature=x",
        "https://object-download.quantconnect.com:444/object.zip?signature=x",
        "https://object-download.quantconnect.com/object.zip#fragment",
    ),
)
def test_signed_download_rejects_unsafe_scheme_host_authority_and_fragment(url):
    calls = []

    def http(*args):
        calls.append(args)
        return 200, _object_get_response(url=url)

    client = _client(http)
    with pytest.raises(transport.FormalQcTransportError, match="URL is not safe"):
        client._read_formal_result_family_object_bounded(
            _capability(client), PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
        )
    assert len(calls) == 1


def test_signed_download_redirect_is_refused_without_forwarding_credentials():
    calls = []

    def http(url, body, headers, timeout):
        calls.append((url, body, dict(headers), timeout))
        if url.endswith("/object/get"):
            return 200, _object_get_response()
        return 302, b"redirect body"

    client = _client(http)
    with pytest.raises(transport.FormalQcTransportError, match="download was refused"):
        client._read_formal_result_family_object_bounded(
            _capability(client), PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
        )
    assert len(calls) == 2
    assert calls[1][0] == SIGNED_DOWNLOAD_URL
    assert calls[1][1] == b""
    assert calls[1][2] == {}


def test_signed_download_archive_and_member_bounds_are_enforced_before_decode():
    calls = []
    maximum_archive = (
        transport.MAX_FORMAL_RESULT_FAMILY_OBJECT_BYTES
        + transport.MAX_OBJECT_GET_ARCHIVE_OVERHEAD_BYTES
    )

    def http(url, body, headers, timeout):
        calls.append((url, body, dict(headers), timeout))
        if url.endswith("/object/get"):
            return 200, _object_get_response()
        return 200, b"x" * (maximum_archive + 1)

    client = _client(http)
    with pytest.raises(transport.FormalQcTransportError, match="byte bound"):
        client._read_formal_result_family_object_bounded(
            _capability(client), PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
        )
    assert len(calls) == 2


@pytest.mark.parametrize(
    "archive_bytes",
    (
        _object_archive(OBJECT_KEYS[0], member_name="wrong-key"),
        _object_archive_members(
            ((OBJECT_KEYS[0], b"one"), (OBJECT_KEYS[1], b"two"))
        ),
    ),
)
def test_object_get_archive_rejects_wrong_or_malformed_inventory(archive_bytes):
    calls = []

    def http(url, body, headers, timeout):
        calls.append((url, body, dict(headers), timeout))
        if url.endswith("/object/get"):
            return 200, _object_get_response()
        return 200, archive_bytes

    client = _client(http)
    with pytest.raises(transport.FormalQcTransportError):
        client._read_formal_result_family_object_bounded(
            _capability(client), PROJECT_ID, ORGANIZATION_ID, OBJECT_KEYS[0]
        )
    assert len(calls) == 2


@pytest.mark.parametrize(
    "response",
    (
        _object_get_response(unexpected=True),
        _object_get_response(job_id=True),
        _object_get_response(url=True),
        _object_get_response(url=""),
        b'{"jobId":"fixture","url":null,"success":true,"errors":"wrong"}',
    ),
)
def test_result_family_read_rejects_hostile_object_get_envelopes(response):
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
    calls = []
    client = _client(_ready_object_http(calls, payload=oversized))
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
    client = _client(_ready_object_http(calls))
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
    client = _client(_ready_object_http(calls))
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
    assert len(calls) == 2


@pytest.mark.skipif(
    not hasattr(os, "fork") or not hasattr(os, "register_at_fork"),
    reason="requires POSIX fork reset semantics",
)
def test_child_resets_inherited_held_private_authority_lock():
    calls = []
    client = _client(_ready_object_http(calls))
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
    assert len(calls) == 2


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
        def do_GET(self):
            self._redirect()

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self._redirect()

        def _redirect(self):
            seen["first"] = {name.lower(): value for name, value in self.headers.items()}
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


@pytest.mark.parametrize("redirect_code", (301, 302, 303, 307, 308))
def test_production_signed_download_refuses_redirect_without_auth(redirect_code):
    first, second, seen = _loopback_servers(redirect_code)
    workers = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (first, second)
    ]
    for worker in workers:
        worker.start()
    try:
        status, raw = transport._prepare_production_download_transport()(
            f"http://127.0.0.1:{first.server_port}/signed-object",
            5.0,
            1024,
        )
    finally:
        for server in (first, second):
            server.shutdown()
            server.server_close()

    assert "authorization" not in seen["first"]
    assert "timestamp" not in seen["first"]
    assert seen["second"] is None
    assert status == redirect_code
    assert raw == b""


def test_production_signed_download_caps_chunked_body_with_one_sentinel_byte():
    import http.server

    seen = {}

    class Chunked(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.update(
                {name.lower(): value for name, value in self.headers.items()}
            )
            payload = b"x" * 2048
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(f"{len(payload):x}\r\n".encode("ascii"))
            self.wfile.write(payload + b"\r\n0\r\n\r\n")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Chunked)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        status, raw = transport._prepare_production_download_transport()(
            f"http://127.0.0.1:{server.server_port}/chunked-object",
            5.0,
            1024,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == 200
    assert len(raw) == 1025
    assert "authorization" not in seen
    assert "timestamp" not in seen


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
