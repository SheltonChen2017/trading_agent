"""Only synthetic memory, keys and responses; production seams stay forbidden."""
import base64
import copy
import hashlib
import io
import json
import socket
import time
from types import SimpleNamespace
import urllib.error
import urllib.parse
import urllib.request

import pytest

from scripts import diagnose_arv2_newrule_storage_error as d
from scripts import diagnose_arv2_newrule_upload as family
from scripts import diagnose_arv2_newrule_object_metadata as organization
from research.analyst_revisions_v2_qc import newrule_comparison_submission as old

HEAD, SHA, ORG = "a" * 40, "b" * 64, "synthetic-organization-private"
REAL_DIRECTORY, REAL_CLIENT, REAL_PREFLIGHT = old._Directory, old.QuantConnectClient, d._preflight
SECRETS = ("private-user", "private-token", ORG, "private-prefix/private-key")


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    violations = []
    def forbidden(*_args, **_kwargs):
        violations.append("boundary")
        pytest.fail("operational access forbidden")
    monkeypatch.setattr(REAL_DIRECTORY, "__init__", forbidden)
    monkeypatch.setattr(REAL_CLIENT, "__init__", forbidden)
    for owner, names in (
        (old, ("_Directory", "_client", "_input", "load_family", "prepare_family", "upload_inputs", "capacity_once", "begin_attempt", "_session")),
        (old.coverage, ("production_client",)), (old.october, ("load_october_order_input_package",)),
        (old.compact, ("load_accepted_risk_preliminary_package",)),
        (family, ("run", "_run", "_census")), (organization, ("run", "_run", "_transport")),
        (d.frozen, ("run", "_operation")), (urllib.request.OpenerDirector, ("open",)),
        (socket, ("create_connection", "getaddrinfo")), (socket.socket, ("connect", "connect_ex")),
        (old.http.client.HTTPConnection, ("request", "connect")), (old.http.client.HTTPSConnection, ("connect",)),
    ):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    yield violations
    assert violations == [], "swallowed operational boundary"


class Directory:
    def __init__(self): self.data, self.events, self.closed = {}, [], False
    def write(self, name, value):
        assert name.startswith("storage-error-diagnostic-v1-")
        self.events.append(("write", name))
        if name in self.data: raise FileExistsError()
        self.data[name] = copy.deepcopy(value)
    def read(self, name):
        self.events.append(("read", name))
        return copy.deepcopy(self.data[name])
    def verify(self): self.events.append(("verify", None))
    def __exit__(self, *_): self.closed = True


class Response:
    def __init__(self, raw, status=200): self.raw, self.code, self.closed, self.reads = raw, status, False, []
    def geturl(self): return old.API_BASE + "/object/properties"
    def read(self, size): self.reads.append(size); return self.raw
    def close(self): self.closed = True


def fixture(monkeypatch):
    directory, calls, events = Directory(), [], []
    row = [SECRETS[3], "c" * 64, 20, False]
    response = Response(json.dumps({"success": False, "errors": [
        "Organization does not have derivative export enabled", "Object private-key not found"]}).encode())
    monkeypatch.setattr(d, "_preflight", lambda *_: events.append("preflight"))
    monkeypatch.setattr(d, "_dependencies", lambda: (family, organization, old))
    monkeypatch.setattr(old, "_Directory", lambda: directory)
    def retained(*_):
        assert d.CLAIM in directory.data
        events.append("retained")
        return row, ORG
    monkeypatch.setattr(d, "_retained", retained)
    body = d.helpers.canonical_json_bytes({"organizationId": ORG, "key": row[0]})
    monkeypatch.setattr(d, "REQUEST_SHA256", hashlib.sha256(body).hexdigest())
    def client():
        assert d.CLAIM in directory.data and d.START in directory.data
        events.append("credentials")
        return SimpleNamespace(_credentials=SimpleNamespace(user_id=SECRETS[0], api_token=SECRETS[1]), _clock=lambda: 100)
    monkeypatch.setattr(old, "_client", client)
    monkeypatch.setattr(old, "_safe_environment", lambda: None)
    monkeypatch.setattr(old, "build_auth_headers", lambda *_: {"Authorization": "private-authorization", "Timestamp": "1234567890"})
    class Opener:
        def open(self, request, timeout):
            assert d.CLAIM in directory.data and d.START in directory.data
            assert directory.data[d.START]["request_sha256"] == hashlib.sha256(request.data).hexdigest()
            calls.append((request, timeout))
            return response
    monkeypatch.setattr(d, "_opener", lambda: Opener())
    return SimpleNamespace(directory=directory, calls=calls, events=events, row=row, response=response)


def execute(): return d._run(HEAD, SHA, time.monotonic() + 90)


def test_one_fixed_request_claim_order_safe_reason_and_no_admission(monkeypatch):
    f = fixture(monkeypatch); result, code = execute(); report = result["report"]
    assert code == 0 and report["terminal"] == "storage_response_observed"
    assert report["attempted_request_count"] == 1 and report["http_status"] == 200
    assert f.events == ["preflight", "retained", "credentials", "retained", "preflight"]
    assert f.directory.closed and set(f.directory.data) == {d.CLAIM, d.START, d.REPORT}
    request, timeout = f.calls[0]
    assert len(f.calls) == 1 and 0 < timeout <= 30 and request.get_method() == "POST"
    assert request.full_url == old.API_BASE + "/object/properties"
    assert json.loads(request.data) == {"organizationId": ORG, "key": f.row[0]}
    reasons = report["observation"]["redacted_provider_reasons"]
    assert reasons == ["organization does not have derivative export enabled", "object [redacted] not found"]
    assert report["observation"]["redacted_span_counts"] == [0, 1]
    assert all(report[key] is value for key, value in d.FLAGS.items())
    output = json.dumps(result)
    assert all(secret not in output for secret in SECRETS)
    raw = d.helpers.canonical_json_bytes(report)
    assert result["report_bytes"] == len(raw) and result["report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert f.response.closed and f.response.reads == [d.MAX_RESPONSE_BYTES + 1]


@pytest.mark.parametrize("status", [200, 301, 401, 403, 404, 429, 500, 503])
def test_non2xx_body_is_prospectively_observed_once_not_followed(monkeypatch, status):
    f = fixture(monkeypatch); f.response.code = status
    result, code = execute()
    assert code == 0 and len(f.calls) == 1 and result["report"]["http_status"] == status
    assert f.response.reads == [d.MAX_RESPONSE_BYTES + 1] and f.response.closed
    assert result["report"]["absence_established"] is False


def test_http_error_response_body_is_bounded_and_closed(monkeypatch):
    f = fixture(monkeypatch)
    body = io.BytesIO(b'{"success":false,"errors":["Storage read permission required"]}')
    error = urllib.error.HTTPError(old.API_BASE + "/object/properties", 403, "private-error", {}, body)
    def open(request, timeout): f.calls.append((request, timeout)); raise error
    monkeypatch.setattr(d, "_opener", lambda: SimpleNamespace(open=open))
    result, code = execute()
    assert code == 0 and body.closed and len(f.calls) == 1
    assert result["report"]["observation"]["redacted_provider_reasons"] == ["storage read permission required"]


@pytest.mark.parametrize("case", ["top", "extra", "success_int", "errors_null", "errors_dict", "error_number", "too_many", "too_long",
    "duplicate", "nonfinite", "exponent", "trailing", "encoding", "html", "oversize", "nonbytes", "url", "status_bool", "status_range"])
def test_malformed_or_ambiguous_response_finite_terminal(monkeypatch, case):
    f = fixture(monkeypatch)
    values = {"top": [], "extra": {"PRIVATE": True}, "success_int": {"success": 1}, "errors_null": {"errors": None},
        "errors_dict": {"errors": {}}, "error_number": {"errors": [1]}, "too_many": {"errors": ["quota"] * 9},
        "too_long": {"errors": ["q" * 513]}}
    raw = {"duplicate": b'{"success":false,"success":true}', "nonfinite": b'{"metadata":NaN}',
        "exponent": b'{"metadata":1e999}', "trailing": b'{}{}', "encoding": b'\xff', "html": b'<html>PRIVATE</html>',
        "oversize": b'x' * (d.MAX_RESPONSE_BYTES + 1), "nonbytes": "PRIVATE"}
    if case in values: f.response.raw = json.dumps(values[case]).encode()
    elif case in raw: f.response.raw = raw[case]
    elif case == "url": f.response.geturl = lambda: old.API_BASE + "/object/set"
    elif case == "status_bool": f.response.code = True
    elif case == "status_range": f.response.code = 999
    result, code = execute()
    assert code == 2 and len(f.calls) == 1 and result["report"]["observation"] is None
    assert f.response.closed and "PRIVATE" not in json.dumps(result)
    if case in {"url", "status_bool", "status_range"}: assert f.response.reads == []


@pytest.mark.parametrize("value", [{}, {"success": True}, {"success": True, "errors": ["quota exceeded"]},
    {"success": False, "metadata": {"preview": "PRIVATE-PREVIEW"}}])
def test_valid_response_shapes_are_diagnostic_only(monkeypatch, value):
    f = fixture(monkeypatch); f.response.raw = json.dumps(value).encode()
    result, code = execute()
    assert code == 0 and result["report"]["terminal"] == "storage_response_observed"
    assert "PRIVATE" not in json.dumps(result) and result["report"]["fix_established"] is False


@pytest.mark.parametrize("error", [TimeoutError("PRIVATE"), urllib.error.URLError("PRIVATE"), KeyboardInterrupt("PRIVATE"), SystemExit("PRIVATE")])
def test_transport_error_or_cancellation_never_retries(monkeypatch, error):
    f = fixture(monkeypatch)
    def open(request, timeout): f.calls.append((request, timeout)); raise error
    monkeypatch.setattr(d, "_opener", lambda: SimpleNamespace(open=open))
    result, code = execute()
    assert code == 2 and len(f.calls) == 1 and result["report"]["attempted_request_count"] == 1
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("stage", ["preflight", "claim", "retained", "request_pin", "credentials", "environment", "intent", "post_source", "post_head", "report", "readback", "verify", "close", "response_close"])
def test_failure_order_and_late_failure_suppress_normal_envelope(monkeypatch, stage, capsys):
    f = fixture(monkeypatch)
    def refused(*_): raise d.DiagnosticRefusal("publication_ambiguous")
    if stage == "preflight": monkeypatch.setattr(d, "_preflight", refused)
    elif stage == "claim": f.directory.data[d.CLAIM] = {}
    elif stage == "retained": monkeypatch.setattr(d, "_retained", refused)
    elif stage == "request_pin": monkeypatch.setattr(d, "REQUEST_SHA256", "0" * 64)
    elif stage == "credentials": monkeypatch.setattr(old, "_client", refused)
    elif stage == "environment": monkeypatch.setattr(old, "_safe_environment", refused)
    elif stage in {"intent", "report"}: f.directory.data[d.START if stage == "intent" else d.REPORT] = {}
    elif stage == "post_source":
        calls = []
        def retained(*_):
            calls.append(1)
            return f.row, ORG if len(calls) == 1 else "different"
        monkeypatch.setattr(d, "_retained", retained)
    elif stage == "post_head":
        def preflight(*_):
            if f.calls: refused()
        monkeypatch.setattr(d, "_preflight", preflight)
    elif stage == "readback":
        original = f.directory.read
        def read(name):
            value = original(name)
            if name == d.REPORT: value["diagnostic_only"] = 1
            return value
        f.directory.read = read
    elif stage == "response_close": f.response.close = refused
    else: setattr(f.directory, "verify" if stage == "verify" else "__exit__", refused)
    assert d.run(SimpleNamespace(expected_head=HEAD, caller_sha256=SHA)) == 2
    value = json.loads(capsys.readouterr().out)
    assert "PRIVATE" not in json.dumps(value)
    if stage in {"report", "readback", "verify", "close"}: assert "report_sha256" not in value
    if stage in {"preflight", "claim", "retained", "request_pin", "credentials", "environment", "intent"}: assert f.calls == []


def test_real_pytest_preflight_is_mandatory_before_directory(monkeypatch):
    monkeypatch.setattr(d, "_dependencies", lambda: pytest.fail("dependencies forbidden before gate"))
    result, code = execute()
    assert code == 2 and result["report"]["failure_code"] == "operational_test_context"
    assert not result["report_published"] and result["report"]["attempted_request_count"] == 0


@pytest.mark.parametrize("name", ["directory", "client", "socket", "old_run"])
def test_captured_live_seams_cannot_escape_alias_guards(isolation, name):
    calls = {"directory": lambda: REAL_DIRECTORY(), "client": lambda: REAL_CLIENT(),
        "socket": lambda: socket.create_connection(("unused.invalid", 443)), "old_run": lambda: family._run(None, None, 0)}
    with pytest.raises(pytest.fail.Exception): calls[name]()
    assert isolation == ["boundary"]; isolation.clear()


def test_proxy_redirect_handlers_are_explicit(monkeypatch):
    captured = []
    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: captured.extend(args))
    d._opener()
    assert captured[0].proxies == {}
    assert captured[1].redirect_request(None, None, 302, "PRIVATE", {}, "https://unused.invalid") is None


@pytest.mark.parametrize("encoding", ["raw", "url", "url2", "base64", "json"])
def test_known_secrets_never_survive_reason_projection(encoding):
    secret = "access"
    encoded = {"raw": secret, "url": urllib.parse.quote(secret), "url2": urllib.parse.quote(urllib.parse.quote(secret)),
        "base64": base64.b64encode(secret.encode()).decode(), "json": json.dumps(secret)[1:-1]}[encoding]
    result = d._sanitize_error("permission " + encoded + " not found", d._secret_variants((secret, *SECRETS[:3])))
    assert result == "permission [redacted] not found"


def test_nested_three_level_percent_encoded_known_word_is_redacted_after_final_decode():
    value = "".join("%%%02x" % ord(c) for c in "access")
    value = urllib.parse.quote(urllib.parse.quote(value, safe=""), safe="")
    result = d._sanitize_error("permission " + value + " required", d._secret_variants(("access", *SECRETS[:3])))
    assert result == "permission [redacted] required"


@pytest.mark.parametrize("span", ["https://private.invalid/access", "www.private.invalid", "name@example.com", "/Users/private/access", "C:\\private\\access",
    "private/access", "deadbeef1234", "12345", "a123-access", "üaccess", "secretword", "123e4567-e89b-12d3-a456-426614174000"])
def test_generic_private_spans_do_not_turn_into_vocabulary(span):
    result = d._sanitize_error("object " + span + " does not exist", d._secret_variants(SECRETS))
    assert result == "object [redacted] does not exist"


def test_useful_public_terms_and_negation_preserved_not_semantic_authority():
    result = d._sanitize_error("Object/key does not exist; Storage/Create permission required; quota maximum bytes files size; researcher customdata derivative export disabled", d._secret_variants(SECRETS))
    assert "storage create permission required" in result and "does not exist" in result
    assert "derivative export disabled" in result and "quota maximum bytes files size" in result
    assert all(word in d.VOCABULARY or word == d.REDACTED for word in result.split())


def test_no_render_or_lookup_of_hostile_exception_values():
    class HostileString(str):
        def __hash__(self): raise AssertionError("no hashing")
        def __eq__(self, other): raise AssertionError("no equality")
    class Meta(type):
        def __eq__(self, other): raise AssertionError("no equality")
    class Hostile(Exception, metaclass=Meta):
        def __str__(self): raise AssertionError("no str")
        def __repr__(self): raise AssertionError("no repr")
    assert d._failure(Hostile("PRIVATE"), (family, organization, old)) == "unknown_exception"
    assert d._failure(d.DiagnosticRefusal(HostileString("source_binding"))) == "unknown_exception"
    assert d._failure(d.DiagnosticRefusal("x" * 10000)) == "unknown_exception"


def preflight_fixture(monkeypatch):
    raw = b"synthetic committed source\n"; caller = hashlib.sha256(raw).hexdigest(); seen = []
    pins = {d.ROOT / name: sha for name, sha in d.PINS.items()}; pins[d.SOURCE] = caller
    monkeypatch.setattr(d, "sys", SimpleNamespace(modules={}))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(d.frozen, "_preflight", lambda args, deadline: seen.append(args))
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: pins[path])
    def git(args, deadline, limit=65536):
        if args[:2] == ["cat-file", "-s"]: return (str(len(raw)) + "\n").encode()
        if args[:2] == ["cat-file", "blob"]: assert limit == len(raw); return raw
        if args == ["rev-parse", "HEAD"]: return (HEAD + "\n").encode()
        assert args == ["status", "--porcelain"]; return b""
    monkeypatch.setattr(d, "_git", git)
    return SimpleNamespace(caller=caller, seen=seen, pins=pins, git=git)


def test_preflight_delegates_host_and_clean_source_but_never_operation(monkeypatch):
    f = preflight_fixture(monkeypatch); REAL_PREFLIGHT(HEAD, f.caller, time.monotonic() + 90)
    assert len(f.seen) == 1 and f.seen[0].operation == "summarize"
    assert f.seen[0].caller_sha256 == d.FROZEN_CALLER_SHA256 and f.seen[0].family_sha256 == d.FAMILY_SHA256


@pytest.mark.parametrize("mutation", ["self", "dependency", "blob", "size", "head", "dirty", "path", "deadline", "expired", "frozen"])
def test_preflight_source_binding_and_old_host_gate_fail_closed(monkeypatch, mutation):
    f = preflight_fixture(monkeypatch)
    if mutation == "self": f.pins[d.SOURCE] = "0" * 64
    elif mutation == "dependency": f.pins[d.ROOT / next(iter(d.PINS))] = "0" * 64
    elif mutation == "path": monkeypatch.setattr(d, "SOURCE", d.SOURCE.with_name("other.py"))
    elif mutation == "frozen":
        def refused(*_): raise d.frozen.OperationRefusal("PRIVATE")
        monkeypatch.setattr(d.frozen, "_preflight", refused)
    elif mutation not in {"deadline", "expired"}:
        def git(args, deadline, limit=65536):
            value = f.git(args, deadline, limit)
            if mutation == "blob" and args[:2] == ["cat-file", "blob"]: return b"x" * len(value)
            if mutation == "size" and args[:2] == ["cat-file", "-s"]: return b"0\n"
            if mutation == "head" and args == ["rev-parse", "HEAD"]: return b"c" * 40 + b"\n"
            if mutation == "dirty" and args == ["status", "--porcelain"]: return b" M file\n"
            return value
        monkeypatch.setattr(d, "_git", git)
    with pytest.raises((d.DiagnosticRefusal, d.frozen.OperationRefusal)):
        REAL_PREFLIGHT(HEAD, f.caller, time.monotonic() + (91 if mutation == "deadline" else -1 if mutation == "expired" else 90))


def test_retained_authentication_reads_only_bound_family_and_org(monkeypatch):
    rows = [["private-key-" + str(i), "a" * 64, 1, i == 5] for i in range(6)]
    calls = []
    monkeypatch.setattr(family, "_family_binding", lambda *_: calls.append("family") or {"upload_inventory": rows})
    monkeypatch.setattr(organization, "_organization", lambda *_: calls.append("organization") or ORG)
    monkeypatch.setattr(d, "INVENTORY_SHA256", hashlib.sha256(d.helpers.canonical_json_bytes(rows)).hexdigest())
    assert d._retained(Directory(), (family, organization, old), time.monotonic() + 90) == (rows[0], ORG)
    assert calls == ["family", "organization"]
    rows[0][2] = True
    with pytest.raises(d.DiagnosticRefusal, match="inventory_binding"):
        d._retained(Directory(), (family, organization, old), time.monotonic() + 90)


def test_import_closure_excludes_dispatch_fence():
    import sys
    assert "assistant.dispatch_fence" not in sys.modules
