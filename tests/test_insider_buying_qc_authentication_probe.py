"""Invented auth-status controls only; initial native network/Keychain denial."""
from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

pytest.importorskip("fcntl", reason="macOS/POSIX custody")
pytest.importorskip("termios", reason="macOS/POSIX custody")
from research import insider_buying_qc_authentication_probe as m


USER, TOKEN = "700019", "invented-secret-authentication-token-92837"


def credentials():
    return m.qc.QuantConnectCredentials(USER, TOKEN)


def response(body=b'{"success":true}', headers=None, status=200):
    return m.AuthenticationHttpResult(status, (("Content-Length", str(len(body))),) if headers is None else headers, body)


def folder(root):
    return root.joinpath(*m.ARTIFACT_PARTS)


def read(path):
    return json.loads(path.read_bytes())


def run(root, *, result=None, events=None, reader=None, on_call=None, **kwargs):
    def load():
        if events is not None:
            events.append("credentials")
        assert (folder(root) / "reservation.json").is_file()
        assert (folder(root) / "credential-read-intent.json").is_file()
        assert not (folder(root) / "request-start.json").exists()
        return credentials() if reader is None else reader()
    def transport(url, body, headers, cap):
        if events is not None:
            events.append("transport")
        assert url == m.URL and body == b"{}" and cap == 16 * 1024
        assert (folder(root) / "request-start.json").is_file()
        assert (folder(root) / "credential-read-complete.json").is_file()
        assert headers["Content-Type"] == "application/json" and "Authorization" in headers
        if on_call is not None:
            on_call(headers)
        return response() if result is None else result
    return m._run_invented_probe(root=root, credential_reader=load, transport=transport, **kwargs)


@pytest.mark.parametrize("raw,expected,optional", (
    (b'{"success":true}', True, []),
    (b' {"success": false} \n', False, []),
    (b'{"success":true,"errors":[]}', True, ["errors"]),
    (b'{"warnings":[],"errors":[],"success":true}', True, ["errors", "warnings"]),
))
def test_auth_parser_documented_boolean_and_only_empty_optional_collections(raw, expected, optional):
    result = m.parse_authentication_status(raw)
    assert result == {"schema": m.SCHEMA + "/status", "success": expected,
        "optional_empty_fields": optional, "authentication_is_not_entitlement": True}


@pytest.mark.parametrize("raw", (
    b'{}', b'[]', b'{"success":1}', b'{"success":"true"}', b'{"success":null}',
    b'{"success":true,"accountId":"private"}', b'{"success":true,"accountId":1e999999}',
    b'{"success":true,"errors":["not stored"]}', b'{"success":false,"warnings":["not stored"]}',
    b'{"success":true,"errors":null}', b'{"success":true,"warnings":{}}',
    b'{"success":true,"success":false}', b'{"success":true,"x":NaN}', b'not JSON',
    b'\xff{"success":true}', b'', b' ' * (m.MAX_BODY_BYTES + 1),
))
def test_unknown_account_fields_numbers_duplicates_messages_and_encoding_refuse(raw):
    with pytest.raises(m.AuthenticationProbeError):
        m.parse_authentication_status(raw)


def test_documented_auth_header_algorithm_is_pure_without_real_environment():
    headers, secrets = m._credential_headers(credentials(), 1700000000)
    expected_hash = m.qc.hashlib.sha256((TOKEN + ":1700000000").encode()).hexdigest()
    expected = "Basic " + base64.b64encode((USER + ":" + expected_hash).encode()).decode()
    assert headers["Authorization"] == expected and headers["Timestamp"] == "1700000000"
    assert set(headers) == {"Authorization", "Timestamp", "Content-Type", "Accept", "Accept-Encoding", "Connection"}
    assert USER in secrets and TOKEN in secrets and expected_hash in secrets and expected in secrets


def test_one_from_env_wrapper_invocation_is_not_a_configuration_search(monkeypatch):
    calls = []
    def fake(cls):
        calls.append(1)
        return credentials()
    monkeypatch.setattr(m.qc.QuantConnectCredentials, "from_env", classmethod(fake))
    assert m._read_credentials().user_id == USER
    assert calls == [1]


def test_positive_private_one_shot_and_independent_status_readback(tmp_path):
    events = []
    result = run(tmp_path, events=events)
    assert events == ["credentials", "transport"]
    assert result["authentication_success"] is True and result["auth_status_qualified"] is True
    assert result["credential_reads"] == result["raw_transport_invocations"] == 1
    verified = m.verify_invented_probe(tmp_path, result["report_sha256"])
    assert verified["authentication_success"] is True and verified["credential_reads"] == 0
    assert verified["raw_transport_invocations_in_original_operation"] == 1
    assert set(p.name for p in folder(tmp_path).iterdir()) == {"scope.lock", "reservation.json",
        "credential-read-intent.json", "credential-read-complete.json", "request-start.json", "result.json",
        "response.bin", "response-framing.json", "status.json", "complete.json"}
    for path in folder(tmp_path).iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
        raw = path.read_bytes()
        assert USER.encode() not in raw and TOKEN.encode() not in raw
    with pytest.raises(ValueError, match="already_consumed"):
        run(tmp_path, events=events)
    assert events == ["credentials", "transport"]


def test_qualified_false_authentication_is_not_success_or_retry(tmp_path):
    result = run(tmp_path, result=response(b'{"success":false,"errors":[]}'))
    assert result["authentication_success"] is False and result["auth_status_qualified"] is True
    assert m.verify_invented_probe(tmp_path, result["report_sha256"])["authentication_success"] is False
    with pytest.raises(ValueError):
        run(tmp_path)


@pytest.mark.parametrize("status", (301, 302, 401, 403, 429, 500))
def test_non200_status_has_no_body_or_header_fingerprint(tmp_path, status):
    result = run(tmp_path, result=response(b"PRIVATE not authorized", (("X-Account", "PRIVATE"),), status))
    assert result["http_status"] == status and result["authentication_success"] is None
    assert not result["auth_status_qualified"] and result["body_sha256"] is result["body_bytes"] is None
    assert not (folder(tmp_path) / "response.bin").exists()
    assert m.verify_invented_probe(tmp_path, result["report_sha256"])["http_status"] == status


@pytest.mark.parametrize("raw", (b'{"success":true,"accountId":"account"}', b'{"success":false,"errors":["message"]}',
    b'not JSON', b'{"success":1}', b'{"success":true,"unknown":1e99999}'))
def test_unknown_http200_never_hashed_or_retained(tmp_path, monkeypatch, raw):
    hashes = []
    old = m._sha
    def digest(value):
        if value == raw:
            hashes.append(value)
        return old(value)
    monkeypatch.setattr(m, "_sha", digest)
    result = run(tmp_path, result=response(raw))
    assert hashes == [] and result["body_sha256"] is None and not result["auth_status_qualified"]
    assert not (folder(tmp_path) / "response.bin").exists()
    assert m.verify_invented_probe(tmp_path, result["report_sha256"])["authentication_success"] is None


@pytest.mark.parametrize("which", ("user", "token", "authorization", "base64", "signature"))
@pytest.mark.parametrize("where", ("header", "body"))
@pytest.mark.parametrize("encoded", (False, True))
def test_all_transient_credential_forms_screened_before_any_response_hash(tmp_path, monkeypatch, which, where, encoded):
    headers, secrets = m._credential_headers(credentials(), 1700000000)
    needles = {"user": USER, "token": TOKEN, "authorization": headers["Authorization"],
        "base64": secrets[3], "signature": secrets[5]}
    secret = needles[which]
    if encoded:
        secret = "".join("\\u%04x" % ord(c) for c in quote(secret, safe=""))
    raw = b'{"success":true}' if where == "header" else ("{\"success\":true,\"echo\":\"" + secret + "\"}").encode()
    pairs = (("Content-Length", str(len(raw))),) + ((("X-Echo", secret),) if where == "header" else ())
    hashes, old = [], m._sha
    def digest(value):
        if value in (raw, m._raw(pairs)):
            hashes.append(value)
        return old(value)
    monkeypatch.setattr(m, "_sha", digest)
    result = run(tmp_path, result=response(raw, pairs))
    assert hashes == [] and result["body_sha256"] is None
    assert result["disposition"] == "authentication_privacy_framing_or_schema_refused_no_retry"
    assert not (folder(tmp_path) / "response.bin").exists()


@pytest.mark.parametrize("headers", ((("Content-Length", "16"), ("Content-Length", "16")),
    (("Transfer-Encoding", "chunked "),), (("Content-Encoding", "gzip"),), ()))
def test_ambiguous_response_framing_refuses(tmp_path, headers):
    result = run(tmp_path, result=response(headers=headers))
    assert result["body_sha256"] is None and not result["auth_status_qualified"]


def test_response_limit_and_safe_framing_projection_never_retains_arbitrary_headers(tmp_path):
    raw = b'{"success":true}' + b" " * (m.MAX_BODY_BYTES - 16)
    assert len(raw) == m.MAX_BODY_BYTES
    result = run(tmp_path, result=response(raw, (("Content-Length", str(len(raw))), ("Server", "invented-server"))))
    assert result["body_bytes"] == m.MAX_BODY_BYTES
    assert read(folder(tmp_path) / "response-framing.json") == {"headers": [["Content-Length", str(len(raw))]]}
    assert all(b"invented-server" not in p.read_bytes() for p in folder(tmp_path).iterdir())


def test_credential_reader_failure_preserves_reservation_and_intent_without_dispatch(tmp_path):
    events = []
    def bad():
        raise RuntimeError("SECRET not printed")
    with pytest.raises(m.AuthenticationProbeError, match="^configured_credentials_unavailable_or_invalid$"):
        run(tmp_path, events=events, reader=bad)
    assert events == ["credentials"] and (folder(tmp_path) / "credential-read-intent.json").exists()
    assert not (folder(tmp_path) / "request-start.json").exists()
    with pytest.raises(ValueError):
        run(tmp_path)


def test_transport_failure_is_once_sanitized_and_permanently_consumed(tmp_path):
    calls = []
    def wire(*args):
        calls.append(1)
        raise OSError("PRIVATE token exception")
    result = m._run_invented_probe(root=tmp_path, credential_reader=credentials, transport=wire)
    assert calls == [1] and result["http_status"] is None
    assert result["disposition"] == "ambiguous_authentication_transport_failure_no_retry"
    assert all(b"PRIVATE" not in p.read_bytes() for p in folder(tmp_path).iterdir())
    assert m.verify_invented_probe(tmp_path, result["report_sha256"])["raw_transport_invocations_in_original_operation"] == 1
    with pytest.raises(ValueError):
        m._run_invented_probe(root=tmp_path, credential_reader=credentials, transport=wire)
    assert calls == [1]


@pytest.mark.parametrize("count", (106, 256, 1024))
def test_unpublished_production_sized_complete_preflight_before_credentials(tmp_path, count):
    inventory = {m.SELF_PATH: "a" * 64, m.TEST_PATH: "b" * 64,
        **{f"research/invented_{i:04}.py": "c" * 64 for i in range(count - 2)}}
    identity = {"root": str(tmp_path), "branch": m.LANE_BRANCH, "head": "a" * 40, "clean": True,
        "source_sha256": inventory, "source_inventory_sha256": m._sha(m._raw(inventory))}
    forms = m._preflight(identity, False, tmp_path)
    assert set(forms) == {"identity", "reservation", "intent", "validated", "start", "capacity_result", "capacity_complete"}
    assert len(forms["capacity_complete"]["execution_identity"]["source_sha256"]) == count
    assert not folder(tmp_path).exists()


def test_preflight_failure_precedes_namespace_or_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_decode", lambda raw: (_ for _ in ()).throw(ValueError("invented_control_refusal")))
    monkeypatch.setattr(m.publication, "_NewDirectory", lambda *a, **k: pytest.fail("no namespace"))
    with pytest.raises(ValueError):
        m._run_invented_probe(root=tmp_path, credential_reader=lambda: pytest.fail("no credential read"),
            transport=lambda *a: pytest.fail("no transport"))
    assert not folder(tmp_path).exists()


@pytest.mark.parametrize("fixture", (True, False))
def test_internal_actual_fixture_callback_root_separation(tmp_path, monkeypatch, fixture):
    root = m.LANE_ROOT if fixture else tmp_path
    monkeypatch.setattr(m.publication, "_NewDirectory", lambda *a, **k: pytest.fail("no namespace"))
    with pytest.raises(ValueError):
        m._run(root=root, identity={}, guard=lambda: None, credential_reader=credentials,
            transport=lambda *a: pytest.fail("no live transport"), fixture=fixture, clock=lambda: 1)


@pytest.mark.parametrize("which", ("reader", "transport", "raw"))
def test_fixture_cannot_consume_production_reader_or_transport(tmp_path, which):
    reader = m._read_credentials if which == "reader" else credentials
    wire = m._production_transport if which == "transport" else m._https_authenticate if which == "raw" else lambda *a: response()
    with pytest.raises(ValueError):
        m._run_invented_probe(root=tmp_path, credential_reader=reader, transport=wire)
    assert not folder(tmp_path).exists()


@pytest.mark.parametrize("fault", ("credential_bool", "transport_bool", "fixture_integer", "authority_integer", "start_bool", "body", "status", "extra"))
def test_readback_rejects_coherently_rehashed_unsafe_or_untyped_controls(tmp_path, fault):
    run(tmp_path)
    target = folder(tmp_path); complete = read(target / "complete.json")
    if fault == "credential_bool":
        complete["credential_reads"] = True
    elif fault == "transport_bool":
        complete["raw_transport_invocations"] = True
    elif fault == "fixture_integer":
        complete["fixture_only"] = 1
    elif fault == "authority_integer":
        complete["authority"]["storage_entitlement_established"] = 0
    elif fault == "start_bool":
        start = read(target / "request-start.json"); start["attempt"] = True
        (target / "request-start.json").write_bytes(m._raw(start))
    elif fault == "body":
        (target / "response.bin").write_bytes(b'{"success":false}')
    elif fault == "status":
        status = read(target / "status.json"); status["success"] = 1
        raw = m._raw(status); (target / "status.json").write_bytes(raw)
        result = complete["result"]; result["status_sha256"] = m._sha(raw)
        raw = m._raw(result); (target / "result.json").write_bytes(raw)
        complete["result_sha256"] = m._sha(raw)
    else:
        (target / "unregistered.json").write_bytes(b"{}")
    raw = m._raw(complete); (target / "complete.json").write_bytes(raw)
    with pytest.raises(ValueError):
        m.verify_invented_probe(tmp_path, m._sha(raw))


def _timer_context(monkeypatch):
    events = []
    monkeypatch.setattr(m, "signal", SimpleNamespace(ITIMER_REAL=1, SIGALRM=2, getitimer=lambda _: (0.0, 0.0),
        getsignal=lambda _: "old", signal=lambda *args: events.append(("handler", *args)),
        setitimer=lambda *args: events.append(("timer", *args))))
    monkeypatch.setattr(m.time, "time", lambda: 1700000000)
    return m._Context(m._TOKEN, {}, lambda: None, None, "a" * 64, credentials()), events


def test_production_default_guard_precedes_timer_and_raw_latch(monkeypatch):
    context, events = _timer_context(monkeypatch)
    monkeypatch.setattr(m._Context, "check", lambda _: (_ for _ in ()).throw(ValueError("guard")))
    monkeypatch.setattr(m, "_https_authenticate", lambda *a: pytest.fail("no opener"))
    with pytest.raises(ValueError, match="guard"):
        m._production_transport(context)
    assert not context.attempted and not context.raw_transport_invoked and events == []


def test_production_absolute_deadline_stops_once_and_restores_alarm(monkeypatch):
    context, events = _timer_context(monkeypatch); calls = []
    monkeypatch.setattr(m._Context, "check", lambda _: None)
    def raw(headers):
        calls.append(headers)
        raise m._DeadlineExceeded()
    monkeypatch.setattr(m, "_https_authenticate", raw)
    with pytest.raises(m.AuthenticationProbeError, match="auth_transport_deadline_refused"):
        m._production_transport(context)
    assert len(calls) == 1 and calls[0]["Timestamp"] == "1700000000" and context.attempted and context.raw_transport_invoked
    assert [x for x in events if x[0] == "timer"] == [("timer", 1, 15), ("timer", 1, 0)]
    assert events[-1] == ("handler", 2, "old")


@pytest.mark.parametrize("status", (301, 401, 403, 429, 500))
def test_default_https_transport_exact_post_and_non200_never_reads_headers_or_body(monkeypatch, status):
    events = []
    class Reply:
        def __init__(self): self.status = status
        def getheaders(self): pytest.fail("non200 headers unread")
        def read(self, *args): pytest.fail("non200 body unread")
    class Connection:
        def __init__(self, host, timeout): events.append(("connect", host, timeout))
        def request(self, *args, **kwargs): events.append(("request", args, kwargs))
        def getresponse(self): return Reply()
        def close(self): events.append(("close",))
    monkeypatch.setattr(m.http.client, "HTTPSConnection", Connection)
    reply = m._https_authenticate({"invented": "headers"})
    assert reply.status == status and reply.headers == () and reply.body == b""
    assert events == [("connect", "www.quantconnect.com", 15),
        ("request", ("POST", "/api/v2/authenticate"), {"body": b"{}", "headers": {"invented": "headers"}}), ("close",)]


def test_actual_readback_native_front_refuses_before_source_or_artifacts(monkeypatch):
    monkeypatch.setattr(m, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=1, no_site=0,
        no_user_site=1, dont_write_bytecode=1), pycache_prefix=m.EMPTY_CACHE_PREFIX))
    monkeypatch.setattr(m.sources, "_prove_isolation", lambda: pytest.fail("flags first"))
    monkeypatch.setattr(m, "_verify", lambda *a: pytest.fail("no real source artifacts"))
    with pytest.raises(m.AuthenticationProbeError, match="isolated"):
        m.verify_actual_probe(expected_report_sha256="a" * 64, execution_identity={})


def test_cli_fixed_refusal_and_no_secret_arguments(monkeypatch, capsys):
    monkeypatch.setattr(m, "run_actual_probe", lambda *a: (_ for _ in ()).throw(RuntimeError("PRIVATE")))
    assert m.main(["--expected-head", "a" * 40]) == 2
    output = capsys.readouterr()
    assert "PRIVATE" not in output.out + output.err and output.err.startswith("REFUSED:")
    with pytest.raises(SystemExit):
        m.main(["--expected-head", "a" * 40, "--api-token", "invented-not-real"])
    output = capsys.readouterr()
    assert "invented-not-real" not in output.err + output.out


def test_actual_readback_cannot_omit_current_dependency_closure(monkeypatch):
    inventory = {m.SELF_PATH: "a" * 64, m.TEST_PATH: "b" * 64}
    identity = {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": "a" * 40, "clean": True,
        "source_sha256": inventory, "source_inventory_sha256": m._sha(m._raw(inventory))}
    monkeypatch.setattr(m, "_isolated", lambda: None)
    monkeypatch.setattr(m.sources, "_prove_isolation", lambda: None)
    monkeypatch.setattr(m.sources.custody, "_internal_source_paths", lambda root: (m.SELF_PATH, "research/quantconnect.py"))
    monkeypatch.setattr(m.sources.custody, "_source_bytes", lambda root, names:
        inventory if tuple(names) == tuple(inventory) else m.sources.FROZEN)
    monkeypatch.setattr(m, "_verify", lambda *args: pytest.fail("omitted closure must precede actual artifacts"))
    with pytest.raises(m.AuthenticationProbeError, match="auth_readback_source_closure_incomplete"):
        m.verify_actual_probe(expected_report_sha256="a" * 64, execution_identity=identity)


@pytest.mark.parametrize("fault", ("reservation_head", "intent_count", "validated_count", "start_bool"))
def test_genuine_transport_context_independently_replays_all_durable_controls(monkeypatch, fault):
    inventory = {m.SELF_PATH: "a" * 64, m.TEST_PATH: "b" * 64,
        **{f"research/invented_{i:03}.py": "c" * 64 for i in range(104)}}
    identity = {"root": str(m.LANE_ROOT), "branch": m.LANE_BRANCH, "head": "a" * 40, "clean": True,
        "source_sha256": inventory, "source_inventory_sha256": m._sha(m._raw(inventory))}
    forms = m._preflight(identity, False, m.LANE_ROOT)
    if fault == "reservation_head": forms["reservation"]["execution_identity"]["head"] = "b" * 40
    elif fault == "intent_count": forms["intent"]["maximum_from_env_invocations"] = True
    elif fault == "validated_count": forms["validated"]["from_env_invocations"] = True
    else: forms["start"]["attempt"] = True
    raw = {"reservation.json": m._raw(forms["reservation"]), "credential-read-intent.json": m._raw(forms["intent"]),
        "credential-read-complete.json": m._raw(forms["validated"]), "request-start.json": m._raw(forms["start"])}
    class Memory:
        def check(self): pass
        def read(self, name): return raw[name]
    monkeypatch.setattr(m, "_identity", lambda _: identity)
    context = m._Context(m._TOKEN, identity, lambda: None, Memory(), m._sha(raw["request-start.json"]), credentials())
    with pytest.raises(ValueError, match="durable_auth_start_refused"):
        context.check()
    assert not context.attempted and not context.raw_transport_invoked


def test_source_change_after_response_stops_before_response_publication(tmp_path):
    changed = False
    def guard():
        if changed: raise ValueError("invented source change")
    def wire(*args):
        nonlocal changed
        changed = True
        return response()
    with pytest.raises(ValueError, match="invented source change"):
        m._run_invented_probe(root=tmp_path, credential_reader=credentials, transport=wire, guard=guard)
    assert (folder(tmp_path) / "request-start.json").exists()
    assert not (folder(tmp_path) / "response.bin").exists() and not (folder(tmp_path) / "complete.json").exists()


def test_local_response_publication_failure_is_not_mislabeled_remote_refusal(tmp_path, monkeypatch):
    old = m.publication._NewDirectory.publish
    def publish(self, name, raw, **kwargs):
        if name == "response.bin": raise OSError("invented local publication failure")
        return old(self, name, raw, **kwargs)
    monkeypatch.setattr(m.publication._NewDirectory, "publish", publish)
    with pytest.raises(OSError, match="invented local publication failure"):
        run(tmp_path)
    assert (folder(tmp_path) / "request-start.json").exists()
    assert not (folder(tmp_path) / "result.json").exists() and not (folder(tmp_path) / "complete.json").exists()


@pytest.mark.parametrize("fault", ("valid_length", "valid_chunked", "short_length", "chunked_oversize", "chunked_incomplete", "chunked_decoder", "duplicate"))
def test_default_https_reader_complete_framing_and_caps(monkeypatch, fault):
    calls = []
    body = b'{"success":true}'
    class Reply:
        status = 200
        chunked = fault.startswith("chunked") or fault == "valid_chunked"
        def getheaders(self):
            if self.chunked: return [("Transfer-Encoding", "chunked")]
            if fault == "duplicate": return [("Content-Length", "16"), ("Content-Length", "16")]
            return [("Content-Length", "17" if fault == "short_length" else str(len(body)))]
        def read(self, n):
            calls.append(n)
            return (b"x" * (m.MAX_BODY_BYTES + 1) if fault == "chunked_oversize" else body) if len(calls) == 1 else b""
        def isclosed(self): return fault != "chunked_incomplete"
    reply = Reply()
    if fault == "chunked_decoder": reply.chunked = False
    # The decoder mismatch must keep a real chunked header while reporting a
    # contradictory http.client decoder flag.
    if fault == "chunked_decoder": reply.getheaders = lambda: [("Transfer-Encoding", "chunked")]
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return reply
        def close(self): pass
    monkeypatch.setattr(m.http.client, "HTTPSConnection", Connection)
    if fault in {"short_length", "chunked_oversize", "chunked_incomplete", "chunked_decoder"}:
        with pytest.raises(ValueError): m._https_authenticate({})
    else:
        result = m._https_authenticate({})
        assert result.body == (b"" if fault == "duplicate" else body)
        if fault == "duplicate": assert calls == []


def test_repeated_default_transport_context_cannot_invoke_again(monkeypatch):
    context, _ = _timer_context(monkeypatch); calls = []
    monkeypatch.setattr(m._Context, "check", lambda _: None)
    monkeypatch.setattr(m, "_https_authenticate", lambda headers: calls.append(1) or response())
    m._production_transport(context)
    with pytest.raises(ValueError, match="fixed_auth_transport_required"):
        m._production_transport(context)
    assert calls == [1]


def test_slow_source_checks_precede_fresh_nonce_without_another_credential_read(monkeypatch):
    context, events = _timer_context(monkeypatch); observed = []; now = [1700000000]
    monkeypatch.setattr(m.time, "time", lambda: now[0])
    def slow_checks(_):
        events.append(("slow-source-checks",))
        now[0] += 900
    monkeypatch.setattr(m._Context, "check", slow_checks)
    monkeypatch.setattr(m, "_read_credentials", lambda: pytest.fail("context must not reread credentials"))
    def wire(headers):
        observed.append(headers)
        return response()
    monkeypatch.setattr(m, "_https_authenticate", wire)
    m._production_transport(context)
    assert len(observed) == 1 and observed[0]["Timestamp"] == "1700000900"
    assert observed[0] == m._credential_headers(credentials(), 1700000900)[0]
    assert context.needles == m._credential_headers(credentials(), 1700000900)[1]
    assert events[0] == ("slow-source-checks",)
    assert [e for e in events if e[0] == "timer"] == [("timer", 1, 15), ("timer", 1, 0)]
