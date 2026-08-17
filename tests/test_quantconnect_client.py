"""QC-1: the QuantConnect research client.

Every test here runs offline. The transport and clock are injected, so the
documented auth algorithm is verified against fixed vectors rather than
against a live account -- which also means this suite stays green on a
machine with no QuantConnect credentials at all.
"""
from __future__ import annotations

import base64
import hashlib
import json

import pytest

from research.quantconnect import (
    API_TOKEN_ENV_VAR,
    USER_ID_ENV_VAR,
    QuantConnectClient,
    QuantConnectCredentials,
    QuantConnectError,
    QuantConnectNotConfigured,
    build_auth_headers,
    is_configured,
)

_CREDS = QuantConnectCredentials(user_id="12345", api_token="tok-abc")


def _fake_transport(status=200, body=None, capture=None):
    payload = {"success": True} if body is None else body

    def transport(url, data, headers, timeout):
        if capture is not None:
            capture.append(
                {"url": url, "data": data, "headers": dict(headers), "timeout": timeout}
            )
        return status, json.dumps(payload).encode("utf-8")

    return transport


def test_auth_header_matches_the_documented_algorithm_exactly():
    """Recomputed independently here rather than by calling the function
    under test, so a change to the implementation cannot silently redefine
    'correct'."""
    timestamp = 1_700_000_000
    headers = build_auth_headers(_CREDS, timestamp)

    expected_hash = hashlib.sha256(f"tok-abc:{timestamp}".encode("utf-8")).hexdigest()
    expected = base64.b64encode(f"12345:{expected_hash}".encode("utf-8")).decode("ascii")

    assert headers["Authorization"] == f"Basic {expected}"
    assert headers["Timestamp"] == str(timestamp)


def test_the_api_token_is_never_transmitted_in_the_clear():
    """The point of the scheme: only a time-bound hash goes over the wire."""
    headers = build_auth_headers(_CREDS, 1_700_000_000)
    joined = " ".join(headers.values())
    assert "tok-abc" not in joined
    decoded = base64.b64decode(headers["Authorization"].split()[1]).decode("utf-8")
    assert "tok-abc" not in decoded


def test_the_timestamp_acts_as_a_nonce():
    """Two calls a second apart must not produce the same signature, or the
    header could be replayed."""
    first = build_auth_headers(_CREDS, 1_700_000_000)
    second = build_auth_headers(_CREDS, 1_700_000_001)
    assert first["Authorization"] != second["Authorization"]


@pytest.mark.parametrize("bad", [0, -1, "1700000000", 1.5, True])
def test_invalid_timestamps_refuse(bad):
    with pytest.raises(QuantConnectError):
        build_auth_headers(_CREDS, bad)


def test_credentials_never_appear_in_repr():
    """A traceback, a log line, or a debugger dump must not leak the token."""
    assert "tok-abc" not in repr(_CREDS)
    assert "redacted" in repr(_CREDS)


@pytest.mark.parametrize(
    "env",
    [
        {},
        {USER_ID_ENV_VAR: "12345"},
        {API_TOKEN_ENV_VAR: "tok"},
        {USER_ID_ENV_VAR: "  ", API_TOKEN_ENV_VAR: "tok"},
    ],
)
def test_missing_or_blank_credentials_refuse_rather_than_default(env):
    assert is_configured(env) is False
    with pytest.raises(QuantConnectNotConfigured):
        QuantConnectCredentials.from_env(env)


def test_credentials_load_from_the_environment():
    env = {USER_ID_ENV_VAR: "999", API_TOKEN_ENV_VAR: "secret"}
    assert is_configured(env) is True
    creds = QuantConnectCredentials.from_env(env)
    assert creds.user_id == "999"


# --- the licence boundary -------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "data/read",
        "data/links/read",
        "/data/prices",
        "live/read",
        "object/store/read",
        "authenticateX",
        "backtests/../data/read",
        "projects/../../data/read",
        "files\\read",
        "https://evil.example/data/read",
        "backtests//evil",
        "",
        "   ",
    ],
)
def test_market_data_and_unlisted_endpoints_are_unreachable(path):
    """QuantConnect's terms forbid exporting raw data, and download licences
    are 'for the licensed organization's internal LEAN use only and cannot
    be redistributed or converted in any format'.

    Converting their data into this project's {ticker: DataFrame} pipeline
    would breach that. The allowlist makes the boundary structural rather
    than a matter of remembering -- a new market-data endpoint added by
    QuantConnect does not become reachable merely because nobody forbade it.

    Prefix matching alone is not enough: ``backtests/../data/read`` must
    also refuse, or URL normalization would bypass the licence boundary.
    """
    client = QuantConnectClient(_CREDS, transport=_fake_transport(), clock=lambda: 1)
    with pytest.raises(QuantConnectError, match="allowlist|non-empty"):
        client.request(path)


@pytest.mark.parametrize(
    "path", ["authenticate", "projects/read", "backtests/read", "optimizations/list"]
)
def test_results_endpoints_are_reachable(path):
    """Guards against 'fixing' the above by blocking everything."""
    client = QuantConnectClient(_CREDS, transport=_fake_transport(), clock=lambda: 1)
    assert client.request(path)["success"] is True


# --- failure handling -----------------------------------------------------

def test_in_band_failure_is_not_treated_as_success():
    """QuantConnect returns HTTP 200 with success:false. Trusting the status
    code alone would turn a rejected request into an empty result."""
    transport = _fake_transport(
        status=200, body={"success": False, "errors": ["Hash doesn't match."]}
    )
    client = QuantConnectClient(_CREDS, transport=transport, clock=lambda: 1)
    with pytest.raises(QuantConnectError, match="Hash doesn't match"):
        client.authenticate()


def test_missing_success_field_is_not_treated_as_success():
    """Fail closed: a 200 body without success:true is not evidence of OK."""
    transport = _fake_transport(status=200, body={"backtests": []})
    client = QuantConnectClient(_CREDS, transport=transport, clock=lambda: 1)
    with pytest.raises(QuantConnectError, match="no reason given"):
        client.list_backtests(1)


def test_http_error_status_refuses():
    transport = _fake_transport(status=401, body={"errors": ["unauthorized"]})
    client = QuantConnectClient(_CREDS, transport=transport, clock=lambda: 1)
    with pytest.raises(QuantConnectError, match="401"):
        client.authenticate()


def test_non_json_body_refuses_rather_than_returning_empty():
    def transport(url, data, headers, timeout):
        return 200, b"<html>maintenance</html>"

    client = QuantConnectClient(_CREDS, transport=transport, clock=lambda: 1)
    with pytest.raises(QuantConnectError, match="non-JSON"):
        client.authenticate()


def test_request_sends_auth_headers_and_the_expected_url():
    capture: list[dict] = []
    client = QuantConnectClient(
        _CREDS,
        base_url="https://example.test/api/v2",
        transport=_fake_transport(capture=capture),
        clock=lambda: 1_700_000_000,
    )
    client.read_backtest(project_id=7, backtest_id="bt-1")

    sent = capture[0]
    assert sent["url"] == "https://example.test/api/v2/backtests/read"
    assert sent["headers"]["Timestamp"] == "1700000000"
    assert sent["headers"]["Authorization"].startswith("Basic ")
    assert sent["headers"]["Content-Type"] == "application/json"
    assert json.loads(sent["data"]) == {"projectId": 7, "backtestId": "bt-1"}


@pytest.mark.parametrize(
    ("call", "path", "payload"),
    [
        (lambda client: client.create_project(" demo "), "projects/create",
         {"name": "demo", "language": "Py"}),
        (lambda client: client.create_file(7, " main.py ", "x=1"), "files/create",
         {"projectId": 7, "name": "main.py", "content": "x=1"}),
        (lambda client: client.update_file(7, " main.py ", "x=2"), "files/update",
         {"projectId": 7, "name": "main.py", "content": "x=2"}),
        (lambda client: client.compile_project(7), "compile/create", {"projectId": 7}),
        (lambda client: client.read_compile(7, " c-1 "), "compile/read",
         {"projectId": 7, "compileId": "c-1"}),
        (lambda client: client.create_backtest(7, " c-1 ", " run "), "backtests/create",
         {"projectId": 7, "compileId": "c-1", "backtestName": "run"}),
    ],
)
def test_cloud_mutation_helpers_send_the_exact_endpoint_contract(call, path, payload):
    capture: list[dict] = []
    client = QuantConnectClient(
        _CREDS, transport=_fake_transport(capture=capture), clock=lambda: 1
    )
    call(client)
    assert capture[0]["url"].endswith("/" + path)
    assert json.loads(capture[0]["data"]) == payload


def test_authenticate_posts_empty_json_object():
    """QuantConnect documents every call as POST, including authenticate.

    urllib.Request with data=None is GET. The first live authenticate() would
    have failed against the documented contract.
    """
    capture: list[dict] = []
    client = QuantConnectClient(
        _CREDS, transport=_fake_transport(capture=capture), clock=lambda: 1
    )
    client.authenticate()
    assert json.loads(capture[0]["data"]) == {}
    assert capture[0]["headers"]["Content-Type"] == "application/json"


def test_default_transport_uses_post_even_without_payload():
    """Pin the urllib Request method, not only the injected fake transport."""
    import research.quantconnect as qc

    seen: list[object] = []

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def getcode(self):
            return 200

        def read(self):
            return b'{"success": true}'

    def fake_urlopen(req, timeout=None):
        seen.append(req)
        return _FakeResponse()

    monkey_request = qc.request
    original = monkey_request.urlopen
    monkey_request.urlopen = fake_urlopen
    try:
        status, raw = qc._default_transport(
            "https://example.test/api/v2/authenticate",
            None,
            {"Authorization": "Basic x", "Timestamp": "1"},
            5.0,
        )
    finally:
        monkey_request.urlopen = original

    assert status == 200
    assert json.loads(raw)["success"] is True
    assert seen[0].get_method() == "POST"
    assert seen[0].data == b"{}"


@pytest.mark.parametrize("bad", [True, "7", 7.5, None, 0, -1])
def test_read_backtest_rejects_non_int_project_id(bad):
    client = QuantConnectClient(_CREDS, transport=_fake_transport(), clock=lambda: 1)
    with pytest.raises(QuantConnectError, match="project_id"):
        client.read_backtest(project_id=bad, backtest_id="bt-1")


@pytest.mark.parametrize("bad", ["", "  ", None, 12])
def test_read_backtest_rejects_blank_backtest_id(bad):
    client = QuantConnectClient(_CREDS, transport=_fake_transport(), clock=lambda: 1)
    with pytest.raises(QuantConnectError, match="backtest_id"):
        client.read_backtest(project_id=1, backtest_id=bad)


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), True, "30"])
def test_invalid_timeout_refuses(bad):
    with pytest.raises(QuantConnectError, match="timeout"):
        QuantConnectClient(_CREDS, transport=_fake_transport(), clock=lambda: 1, timeout=bad)


# --- architectural boundary ----------------------------------------------

def test_client_cannot_reach_execution_authority():
    """Research-only, the same contract backtest.interactive carries. A
    QuantConnect result must never be able to reach an order path.

    Source-level: the invariant is about the import graph, which no single
    runtime call can observe.
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "research" / "quantconnect.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden = ("assistant", "execution", "risk", "ml", "signals", "strategies")
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in forbidden:
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in forbidden:
                offenders.append(node.module)

    assert not offenders, (
        "the QuantConnect research client must not reach execution, "
        f"proposal, risk, or ML code: {offenders}"
    )


def test_the_unverified_success_assumption_is_documented_where_it_will_bite():
    """CQC-001. The `success is True` requirement is fail-closed and correct,
    but no live call has ever been made from this project, so whether every
    endpoint sets that field is an assumption rather than a verified
    contract.

    An undocumented assumption of this kind costs a debugging session: a
    valid response refused as "no reason given" reads as a credential
    problem. Pinned in three places because three different readers hit it —
    whoever debugs the failure (the code), whoever sets it up (the README),
    and whoever inherits the project (the durable facts).
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for relative in (
        "research/quantconnect.py",
        "README.md",
        "docs/operations/OPERATIONAL_FACTS.md",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert "CQC-001" in text, f"{relative} must record the open assumption"
        assert "no reason given" in text, (
            f"{relative} must name the symptom, so the failure is recognizable"
        )


# --------------------------------------------------------------------------
# FCS-003: percent-encoded traversal must not bypass the licence boundary.
#
# QCREV-002 hardened this against a literal `backtests/../data/read` on
# 2026-08-07. The encoded twin `backtests/%2e%2e/data/read` still passed:
# urllib does not normalize what we hand it, but servers and CDNs routinely
# decode-then-route, so the request would have reached a market-data endpoint.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "backtests/../data/read",
        "backtests/%2e%2e/data/read",
        "backtests/%2E%2E/data/read",
        "backtests/.%2e/data/read",
        "backtests/%252e%252e/data/read",  # double-encoded
        "backtests/%2f../data/read",
        "backtests/%5c../data/read",       # encoded backslash
        "data/read",
        "data/%2e%2e/backtests/read",
    ],
)
def test_encoded_traversal_cannot_reach_a_market_data_endpoint(path):
    from research.quantconnect import QuantConnectError, _assert_allowed

    with pytest.raises(QuantConnectError):
        _assert_allowed(path)


@pytest.mark.parametrize(
    "path",
    [
        "authenticate",
        "backtests/read",
        "backtests/list",
        "projects/create",
        "files/read",
        "compile/create",
        "optimizations/read",
    ],
)
def test_the_hardening_still_permits_every_allowlisted_endpoint(path):
    from research.quantconnect import _assert_allowed

    _assert_allowed(path)  # must not raise


def test_a_percent_sign_in_a_path_is_refused_outright():
    """Parameters travel in the JSON body; no allowlisted path needs an escape.

    Refusing '%' is what makes this robust against encodings nobody has
    thought of yet, rather than against the two that were reported.
    """
    from research.quantconnect import QuantConnectError, _assert_allowed

    with pytest.raises(QuantConnectError):
        _assert_allowed("backtests/read%20now")
