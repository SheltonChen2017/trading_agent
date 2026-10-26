"""Synthetic-only D9 tests: no private artifacts, credentials, or QC contact."""
import copy
import hashlib
import io
import json
import time
from types import SimpleNamespace
import urllib.error

import pytest

from scripts import diagnose_arv2_newrule_object_metadata as d
from scripts import diagnose_arv2_newrule_upload as d8
from research.analyst_revisions_v2_qc import newrule_comparison_submission as s

HEAD, SHA = "a" * 40, "b" * 64
PREFLIGHT = d._preflight
OPENER = d._opener
CLIENT = s._client


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("operational access forbidden")
    for obj, names in ((d.frozen, ("run", "_operation")),
        (d8, ("run", "_run", "_census")),
        (s, ("_client", "load_family", "prepare_family", "discover_organization", "upload_inputs",
             "capacity_once", "begin_attempt", "poll_compile_once", "launch_compiled",
             "poll_status_once", "read_result_once", "summarize_family", "_session")),
        (d, ("_preflight", "_opener"))):
        for name in names:
            monkeypatch.setattr(obj, name, forbidden)


class MemoryDirectory:
    def __init__(self, data):
        self.data = copy.deepcopy(data)
        self.events = []
    def names(self):
        return tuple(self.data)
    def read(self, name):
        assert name not in {"upload-valid.json", "upload-000-intent.json", "upload-authenticate-observed.json"}
        self.events.append(("read", name))
        return copy.deepcopy(self.data[name])
    def write(self, name, value):
        assert name in {d.CLAIM, d.START, d.REPORT}
        self.events.append(("write", name))
        if name in self.data:
            raise FileExistsError()
        self.data[name] = copy.deepcopy(value)
    def __exit__(self, *_):
        self.events.append(("close", None))


def binding_fixture(monkeypatch):
    total = s.UPLOAD_BYTES - s.ACTIVATION_BYTES
    inventory = [[f"PRIVATE-KEY-{i}", SHA, total // 5 + (total % 5 if i == 0 else 0), False]
                 for i in range(5)]
    inventory.append([s.ACTIVATION_KEY, s.ACTIVATION_SHA256, s.ACTIVATION_BYTES, True])
    inventory_sha = hashlib.sha256(d.helpers.canonical_json_bytes(inventory)).hexdigest()
    monkeypatch.setattr(d, "INVENTORY_SHA256", inventory_sha)
    record = {"schema": s.SCHEMA, "package_sha256": d.frozen.PACKAGE_SHA256,
        "lineage_sha256": d.frozen.LINEAGE_SHA256, "submission_profile_sha256": s.PROFILE_SHA256,
        "formal_forward_ready": False, "paper_or_live_ready": False,
        "upload_inventory": inventory, "upload_inventory_sha256": inventory_sha}
    family = hashlib.sha256(d.helpers.canonical_json_bytes(record)).hexdigest()
    monkeypatch.setattr(d, "FAMILY_SHA256", family)
    monkeypatch.setattr(d8, "FAMILY_SHA256", family)
    census = {"inventory_count": 6, "upload_inventory_sha256": inventory_sha,
        "authenticate": dict(intent_present=True, observed_success_present=True, missing_observation=False),
        "endpoint_census": {"object/set": dict(intent_indices=[0], observed_success_indices=[], missing_observation_indices=[0]),
            "object/properties": dict(intent_indices=[], observed_success_indices=[], missing_observation_indices=[])},
        "retained_intent_count": 2, "observed_success_count": 1, "missing_observation_count": 1,
        "last_retained_request_intent": {"endpoint": "object/set", "index": 0},
        "actual_last_dispatch_unknown": True, "request_count_unknown": True,
        "successful_response_is_properties_validation": False,
        "original_upload_valid_marker_present": False, "original_upload_valid_marker_content_read": False}
    report = d8._report(d.D8_HEAD, d.D8_SOURCE_SHA256, "2026-10-14T00:00:00Z", "marker_census", True, census, None)
    raw = d.helpers.canonical_json_bytes(report)
    monkeypatch.setattr(d, "D8_REPORT_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(d, "D8_REPORT_BYTES", len(raw))
    org = "f" * 32
    monkeypatch.setattr(d, "ORGANIZATION_SHA256", hashlib.sha256(org.encode()).hexdigest())
    organization_claim = dict(family_sha256=family, reference_project_id=s.REFERENCE_PROJECT)
    directory = MemoryDirectory({"family.json": record,
        "preparation-claim.json": dict(schema=s.SCHEMA, family_sha256=family), d.D8_REPORT: report,
        "organization-claim.json": organization_claim,
        "organization.json": dict(organization_claim, organization_id=org, organization_sha256=d.ORGANIZATION_SHA256)})
    return directory, record, inventory[0], org


def harness(monkeypatch, response=None, status=200):
    directory, record, row, org = binding_fixture(monkeypatch)
    monkeypatch.setattr(d, "_preflight", lambda *_: None)
    monkeypatch.setattr(s, "_Directory", lambda: directory)
    def client():
        directory.events.append(("credentials", None))
        return object()
    monkeypatch.setattr(s, "_client", client)
    def transport(api, submission, body, state, deadline):
        directory.events.append(("request", None))
        assert json.loads(body) == {"organizationId": org, "key": row[0]}
        assert d.CLAIM in directory.data and d.START in directory.data
        assert state["attempted_request_count"] == 0
        state.update(attempted_request_count=1, http_status=status)
        return response if response is not None else (
            json.dumps({"success": True, "metadata": {"key": row[0], "size": row[2], "md5": "c"*32}}).encode()
            if 200 <= status < 300 else None)
    monkeypatch.setattr(d, "_transport", transport)
    return directory, record, row


def read_output(capsys):
    text = capsys.readouterr().out
    assert "PRIVATE" not in text and '"organization_id"' not in text
    return json.loads(text)


def test_complete_claim_before_retained_reads_credentials_one_request(monkeypatch, capsys):
    directory, _, _ = harness(monkeypatch)
    assert d._run(HEAD, SHA, time.monotonic()+10) == 0
    envelope = read_output(capsys)
    report = envelope["report"]
    assert directory.events[0] == ("write", d.CLAIM)
    assert directory.events.count(("request", None)) == 1
    assert directory.events.index(("write", d.START)) < directory.events.index(("credentials", None))
    assert report["attempted_request_count"] == 1 and report["http_status"] == 200
    assert report["observation"] == dict(response_schema_valid=True, api_success=True,
        metadata_schema_valid=True, key_matches=True, size_matches=True, md5_well_formed=True, error_category="unknown")
    for field in ("original_upload_accepted", "changes_original_exit", "historical_failure_cause_reconstructed",
                  "measured_server_contact", "md5_content_authentication", "point_in_time_proven",
                  "formal_forward_ready", "paper_or_live_ready"):
        assert report[field] is False
    raw = d.helpers.canonical_json_bytes(report)
    assert envelope["report_sha256"] == hashlib.sha256(raw).hexdigest() and envelope["report_bytes"] == len(raw)


@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500, 599])
def test_non_success_status_is_completed_diagnostic_not_upload(monkeypatch, capsys, status):
    harness(monkeypatch, status=status)
    assert d._run(HEAD, SHA, time.monotonic()+10) == 0
    report = read_output(capsys)["report"]
    assert report["http_status"] == status and report["observation"]["api_success"] is None
    assert report["observation"]["error_category"] == "unknown" and not report["original_upload_accepted"]


@pytest.mark.parametrize("error,category", [("Access denied", "permission"), ("object not found", "not_found"),
    ("quota exceeded", "quota"), ("subscription expired", "subscription"),
    ("PRIVATE-KEY permission denied here", "unknown"), ("", "unknown")])
def test_finite_error_categories_no_text(error, category):
    value = d._observation(json.dumps({"success": False, "errors": [error]}).encode(), ["PRIVATE", SHA, 3, False])
    assert value["error_category"] == category and value["api_success"] is False
    assert error not in json.dumps(value) if error and error not in {"", "unknown"} else True


@pytest.mark.parametrize("change", ["key", "size", "md5"])
def test_current_metadata_mismatch_is_finite_observation_not_content_authentication(change):
    metadata = {"key": "PRIVATE", "size": 3, "md5": "f"*32, "preview": "PRIVATE-LICENSED-ROWS"}
    metadata[change] = {"key": "OTHER", "size": 4, "md5": "not-an-md5"}[change]
    result = d._observation(json.dumps(dict(success=True, metadata=metadata)).encode(), ["PRIVATE", SHA, 3, False])
    assert result[{"key":"key_matches", "size":"size_matches", "md5":"md5_well_formed"}[change]] is False
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("raw", [b'{"success":true,"success":false}', b'{"success":NaN}',
    b'{"success":Infinity}', b'[]', b'null', b'{"success":1}', b'{"success":true}',
    b'{"success":false,"errors":"PRIVATE"}', b'{"success":false,"metadata":{}}',
    b'{"success":false,"extra":"PRIVATE"}', b'{} trailing', b'\xff',
    b'{"success":false,"errors":[1]}', b'{"success":true,"metadata":{"key":"p","size":true,"md5":"x"}}'])
def test_schema_ambiguity_refuses_without_rendering(raw):
    with pytest.raises((d.DiagnosticRefusal, ValueError)):
        d._observation(raw, ["PRIVATE", SHA, 3, False])


@pytest.mark.parametrize("errors", [["x"]*9, ["x"*513], [True], [None], ["quota exceeded", "not found"]])
def test_error_bounds_and_ambiguous_categories(errors):
    if errors == ["quota exceeded", "not found"]:
        assert d._error_category(errors) == "unknown"
    else:
        with pytest.raises(d.DiagnosticRefusal):
            d._error_category(errors)


@pytest.mark.parametrize("mutation", ["hash", "length", "head", "profile", "source", "success", "index",
    "extra", "bool_count", "float_index", "second_missing", "auth", "valid_present", "inventory"])
def test_d8_binding_refuses_changed_pin_schema_or_census(monkeypatch, mutation):
    directory, record, _, _ = binding_fixture(monkeypatch)
    value = directory.data[d.D8_REPORT]
    if mutation == "hash": monkeypatch.setattr(d, "D8_REPORT_SHA256", "c"*64)
    elif mutation == "length": monkeypatch.setattr(d, "D8_REPORT_BYTES", d.D8_REPORT_BYTES+1)
    elif mutation == "head": value["expected_head"] = HEAD
    elif mutation == "profile": value["profile_sha256"] = SHA
    elif mutation == "source": value["caller_sha256"] = SHA
    elif mutation == "success": value["terminal"] = "diagnostic_refused"
    elif mutation == "index": value["census"]["last_retained_request_intent"]["index"] = 1
    elif mutation == "extra": value["private"] = "SECRET"
    elif mutation == "bool_count": value["census"]["observed_success_count"] = True
    elif mutation == "float_index": value["census"]["endpoint_census"]["object/set"]["intent_indices"] = [0.0]
    elif mutation == "second_missing": value["census"]["missing_observation_count"] = 2
    elif mutation == "auth": value["census"]["authenticate"]["observed_success_present"] = False
    elif mutation == "valid_present": directory.data["upload-valid.json"] = {"PRIVATE": 1}
    elif mutation == "inventory": record["upload_inventory_sha256"] = SHA
    if mutation not in {"hash", "length"}:
        raw = d.helpers.canonical_json_bytes(value)
        monkeypatch.setattr(d, "D8_REPORT_SHA256", hashlib.sha256(raw).hexdigest())
        monkeypatch.setattr(d, "D8_REPORT_BYTES", len(raw))
    with pytest.raises(d.DiagnosticRefusal):
        d._d8_binding(directory, record, d8)


@pytest.mark.parametrize("mutation", ["org", "hash", "claim", "extra", "float_project"])
def test_organization_external_digest_and_exact_types(monkeypatch, mutation):
    directory, _, _, _ = binding_fixture(monkeypatch)
    value = directory.data["organization.json"]
    if mutation == "org": value["organization_id"] = "e"*32
    elif mutation == "hash": value["organization_sha256"] = SHA
    elif mutation == "claim": directory.data["organization-claim.json"]["family_sha256"] = SHA
    elif mutation == "extra": value["private"] = "PRIVATE"
    elif mutation == "float_project": value["reference_project_id"] = float(s.REFERENCE_PROJECT)
    with pytest.raises(d.DiagnosticRefusal):
        d._organization(directory, s)


@pytest.mark.parametrize("phase", ["preflight", "claim", "d8", "org", "start", "credentials", "transport", "schema", "publication"])
def test_refusals_do_not_retry_or_emit_private_detail(monkeypatch, capsys, phase):
    directory, _, _ = harness(monkeypatch)
    def fail(*_):
        raise RuntimeError("PRIVATE-ROW-OR-CREDENTIAL")
    if phase == "preflight": monkeypatch.setattr(d, "_preflight", fail)
    elif phase == "claim": directory.data[d.CLAIM] = {}
    elif phase == "d8": directory.data[d.D8_REPORT]["terminal"] = "changed"
    elif phase == "org": directory.data["organization.json"]["organization_id"] = "e"*32
    elif phase == "start": directory.data[d.START] = {}
    elif phase == "credentials": monkeypatch.setattr(s, "_client", fail)
    elif phase == "transport": monkeypatch.setattr(d, "_transport", fail)
    elif phase == "schema": monkeypatch.setattr(d, "_observation", fail)
    elif phase == "publication": directory.data[d.REPORT] = {}
    assert d._run(HEAD, SHA, time.monotonic()+10) == 2
    envelope = read_output(capsys)
    assert len([x for x in directory.events if x[0] == "request"]) <= 1
    if phase in {"preflight", "claim"}:
        assert not any(x[0] == "read" for x in directory.events)
    if phase in {"preflight", "claim", "d8", "org", "start"}:
        assert ("credentials", None) not in directory.events
    if "report" in envelope:
        assert envelope["report"]["observation"] is None


class Response:
    def __init__(self, code=200, raw=b'{}', url=None):
        self.code, self.raw = code, raw
        self.url = url or s.API_BASE + "/object/properties"
        self.reads, self.closed = [], False
    def geturl(self): return self.url
    def read(self, size):
        self.reads.append(size)
        return self.raw
    def close(self): self.closed = True


def fake_transport(monkeypatch, response, error=False):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            if error: raise response
            return response
    monkeypatch.setattr(d, "_opener", lambda: Opener())
    monkeypatch.setattr(s, "build_auth_headers", lambda *_: {"Authorization": "PRIVATE-TOKEN"})
    api = SimpleNamespace(_credentials=object(), _clock=lambda: 100)
    state = dict(attempted_request_count=0, http_status=None)
    return api, state, calls


@pytest.mark.parametrize("code", [200, 201, 204, 301, 401, 403, 404, 429, 500])
def test_one_bounded_fixed_endpoint_transport_no_failed_body(monkeypatch, code):
    response = Response(code)
    api, state, calls = fake_transport(monkeypatch, response)
    raw = d._transport(api, s, b'{}', state, time.monotonic()+10)
    assert state == dict(attempted_request_count=1, http_status=code)
    assert len(calls) == 1 and calls[0][0].full_url == s.API_BASE + "/object/properties"
    assert calls[0][0].get_method() == "POST" and 0 < calls[0][1] <= 10
    assert response.reads == ([d.MAX_RESPONSE_BYTES+1] if 200 <= code < 300 else [])
    assert raw == (b'{}' if 200 <= code < 300 else None) and response.closed


def test_http_error_numeric_status_retained_without_body(monkeypatch):
    class ForbiddenBody(io.BytesIO):
        def read(self, *_): pytest.fail("failed response body read")
    error = urllib.error.HTTPError(s.API_BASE + "/object/properties", 403, "PRIVATE", {}, ForbiddenBody(b"PRIVATE"))
    api, state, calls = fake_transport(monkeypatch, error, error=True)
    assert d._transport(api, s, b'{}', state, time.monotonic()+10) is None
    assert state["http_status"] == 403 and state["attempted_request_count"] == 1 and len(calls) == 1


@pytest.mark.parametrize("mutation", ["bool", "float", "low", "high", "url", "large", "str_body", "already_sent", "request_large"])
def test_transport_bounds_refuse_without_second_request(monkeypatch, mutation):
    response = Response()
    if mutation == "bool": response.code = True
    elif mutation == "float": response.code = 200.0
    elif mutation == "low": response.code = 99
    elif mutation == "high": response.code = 600
    elif mutation == "url": response.url = "https://untrusted.invalid/"
    elif mutation == "large": response.raw = b'x' * (d.MAX_RESPONSE_BYTES+1)
    elif mutation == "str_body": response.raw = "PRIVATE"
    api, state, calls = fake_transport(monkeypatch, response)
    if mutation == "already_sent": state["attempted_request_count"] = 1
    body = b'x'*(d.MAX_REQUEST_BYTES+1) if mutation == "request_large" else b'{}'
    with pytest.raises(d.DiagnosticRefusal):
        d._transport(api, s, body, state, time.monotonic()+10)
    assert len(calls) == (0 if mutation in {"already_sent", "request_large"} else 1)


def test_no_redirect_and_explicit_empty_proxy_handler(monkeypatch):
    captured = []
    monkeypatch.setattr(d.urllib.request, "build_opener", lambda *handlers: captured.extend(handlers))
    OPENER()  # Actual pure constructor, without any open call.
    assert captured[0].proxies == {}
    assert captured[1].redirect_request(None, None, 302, "PRIVATE", {}, "https://elsewhere.invalid") is None


def test_preflight_passes_original_caller_and_checks_d8_and_self(monkeypatch):
    seen = []
    monkeypatch.setattr(d.frozen, "_preflight", lambda args, deadline: seen.append(args))
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: d.D8_SOURCE_SHA256 if path == d.D8_SOURCE else SHA)
    PREFLIGHT(HEAD, SHA, time.monotonic()+10)
    assert seen[0].caller_sha256 == d.FROZEN_CALLER_SHA256 and seen[0].operation == "summarize"


@pytest.mark.parametrize("bad", ["d8", "self"])
def test_source_pin_refusal_precedes_any_private_access(monkeypatch, bad):
    monkeypatch.setattr(d.frozen, "_preflight", lambda *_: None)
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: "c"*64 if (
        path == d.D8_SOURCE if bad == "d8" else path == d.SOURCE) else (d.D8_SOURCE_SHA256 if path == d.D8_SOURCE else SHA))
    with pytest.raises(d.DiagnosticRefusal): PREFLIGHT(HEAD, SHA, time.monotonic()+10)


def test_unknown_exception_type_does_not_run_hostile_hooks():
    class Meta(type):
        def __hash__(cls): pytest.fail("metaclass hash")
        def __eq__(cls, other): pytest.fail("metaclass equality")
    class Hostile(Exception, metaclass=Meta):
        def __str__(self): pytest.fail("str")
        def __repr__(self): pytest.fail("repr")
    assert d._failure(Hostile("PRIVATE"), s) == "unknown_exception"


def test_bad_input_never_echoed_and_deadline_is_terminal(monkeypatch, capsys):
    harness(monkeypatch)
    assert d._run("PRIVATE-INPUT", "PRIVATE-TOKEN", time.monotonic()-1) == 2
    assert "PRIVATE" not in capsys.readouterr().out


def test_parent_alarm_covers_whole_operation(monkeypatch, capsys):
    seen = []
    class Alarm:
        def __enter__(self): seen.append("enter")
        def __exit__(self, *_): seen.append("exit")
    monkeypatch.setattr(d.helpers, "_alarm", lambda deadline: Alarm())
    monkeypatch.setattr(d, "_run", lambda *_: seen.append("run") or 0)
    assert d.run(HEAD, SHA) == 0 and seen == ["enter", "run", "exit"]


@pytest.mark.parametrize("error", [TimeoutError("PRIVATE"), urllib.error.URLError("PRIVATE"), OSError("PRIVATE")])
def test_transport_exception_spends_one_attempt_without_retry(monkeypatch, error):
    api, state, calls = fake_transport(monkeypatch, error, error=True)
    with pytest.raises(type(error)):
        d._transport(api, s, b'{}', state, time.monotonic()+10)
    assert state == dict(attempted_request_count=1, http_status=None) and len(calls) == 1


def test_deadline_after_response_read_closes_and_retains_status(monkeypatch):
    response = Response()
    api, state, calls = fake_transport(monkeypatch, response)
    remaining_calls = []
    def remaining(deadline):
        remaining_calls.append(None)
        if len(remaining_calls) == 3:
            raise d.helpers.Deadline()
        return 10
    monkeypatch.setattr(d.helpers, "_remaining", remaining)
    with pytest.raises(d.helpers.Deadline):
        d._transport(api, s, b'{}', state, time.monotonic()+10)
    assert response.closed and response.reads == [d.MAX_RESPONSE_BYTES+1]
    assert len(calls) == 1 and state == dict(attempted_request_count=1, http_status=200)


@pytest.mark.parametrize("phase", ["family", "d8", "organization", "claim", "report"])
def test_late_retained_or_report_change_prevents_normal_success(monkeypatch, capsys, phase):
    directory, _, _ = harness(monkeypatch)
    original_transport, original_read = d._transport, directory.read
    def transport(*args):
        raw = original_transport(*args)
        if phase == "family": directory.data["family.json"]["upload_inventory_sha256"] = SHA
        elif phase == "d8": directory.data[d.D8_REPORT]["census"]["missing_observation_count"] = 0
        elif phase == "organization": directory.data["organization.json"]["organization_id"] = "e"*32
        elif phase == "claim": directory.data[d.CLAIM]["profile_sha256"] = SHA
        return raw
    def read(name):
        value = original_read(name)
        if name == d.REPORT and phase == "report": value["attempted_request_count"] = 2
        return value
    monkeypatch.setattr(d, "_transport", transport)
    monkeypatch.setattr(directory, "read", read)
    assert d._run(HEAD, SHA, time.monotonic()+10) == 2
    envelope = read_output(capsys)
    if "report" in envelope:
        assert envelope["report"]["observation"] is None
    else:
        assert envelope["terminal"] == "diagnostic_publication_ambiguous"


@pytest.mark.parametrize("bad", ["d8", "self"])
def test_actual_source_preflight_failure_uses_no_private_constructor_or_credentials(monkeypatch, capsys, bad):
    monkeypatch.setattr(d, "_preflight", PREFLIGHT)
    monkeypatch.setattr(d.frozen, "_preflight", lambda *_: None)
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: "c"*64 if (
        path == d.D8_SOURCE if bad == "d8" else path == d.SOURCE) else (d.D8_SOURCE_SHA256 if path == d.D8_SOURCE else SHA))
    monkeypatch.setattr(s, "_Directory", lambda: pytest.fail("private constructor accessed"))
    assert d._run(HEAD, SHA, time.monotonic()+10) == 2
    report = read_output(capsys)["report"]
    assert report["stage"] == "preflight" and report["attempt_consumed"] is False
    assert report["attempted_request_count"] == 0


@pytest.mark.parametrize("unsafe", ["sslkeylog", "httpdebug", "httpsdebug"])
def test_inherited_client_environment_refuses_before_credentials(monkeypatch, unsafe):
    monkeypatch.setattr(s.coverage, "production_client", lambda: pytest.fail("credentials accessed"))
    if unsafe == "sslkeylog": monkeypatch.setenv("SSLKEYLOGFILE", "PRIVATE")
    elif unsafe == "httpdebug": monkeypatch.setattr(s.http.client.HTTPConnection, "debuglevel", 1)
    elif unsafe == "httpsdebug": monkeypatch.setattr(s.http.client.HTTPSConnection, "debuglevel", 1)
    with pytest.raises(s.NewruleSubmissionError): CLIENT()


def test_nonzero_and_schema_refusal_retain_observed_status_not_body(monkeypatch, capsys):
    harness(monkeypatch, response=b'{"success":true,"PRIVATE-EXTRA":"LICENSED"}')
    assert d._run(HEAD, SHA, time.monotonic()+10) == 2
    report = read_output(capsys)["report"]
    assert report["http_status"] == 200 and report["attempted_request_count"] == 1
    assert report["observation"] is None and not report["original_upload_accepted"]
