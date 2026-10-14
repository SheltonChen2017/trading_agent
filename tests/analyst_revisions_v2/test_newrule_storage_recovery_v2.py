"""Synthetic remote store only; never operational controls, credentials, or QC."""
import copy
import hashlib
import io
import json
import socket
import time
from types import SimpleNamespace
import urllib.error

import pytest

from scripts import arv2_newrule_storage_recovery_v2 as r

HEAD, SHA, ORG = "a"*40, "b"*64, "f"*32
REAL_RETAINED = r._retained
REAL_REQUIRE_FAMILY = r.old.require_family
REAL_DIRECTORY = r.old._Directory
REAL_CLIENT = r.old.QuantConnectClient
REAL_GATE = r._runtime_gate
REAL_INCIDENT = r._incident_binding


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    violations = []
    def forbidden(*_a, **_k):
        violations.append("operational_boundary")
        pytest.fail("operational access forbidden")
    # Guard the original class too: a stale import/module alias must not evade
    # the local synthetic _Directory replacement. These tests need no real
    # control filesystem at all, including the production control directory.
    monkeypatch.setattr(REAL_DIRECTORY, "__init__", forbidden)
    monkeypatch.setattr(REAL_CLIENT, "__init__", forbidden)
    monkeypatch.setattr(r.old.coverage, "production_client", forbidden)
    monkeypatch.setattr(r.old.october, "load_october_order_input_package", forbidden)
    monkeypatch.setattr(r.old.compact, "load_accepted_risk_preliminary_package", forbidden)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", forbidden)
    monkeypatch.setattr(r.old.http.client.HTTPConnection, "request", forbidden)
    monkeypatch.setattr(r.old.http.client.HTTPConnection, "connect", forbidden)
    monkeypatch.setattr(r.old.http.client.HTTPSConnection, "connect", forbidden)
    for obj, names in ((socket, ("create_connection", "getaddrinfo")),
                       (socket.socket, ("connect", "connect_ex"))):
        for name in names: monkeypatch.setattr(obj, name, forbidden)
    for obj, names in ((r.old, ("_client", "_Directory", "load_family", "prepare_family", "discover_organization",
        "upload_inputs", "capacity_once", "begin_attempt", "poll_compile_once", "launch_compiled",
        "poll_status_once", "read_result_once", "summarize_family", "_session")),
        (r.prior, ("run", "_run", "_opener")), (r.markers, ("run", "_run", "_census"))):
        for name in names: monkeypatch.setattr(obj, name, forbidden)
    yield violations
    # Product code intentionally catches BaseException for finite reporting.
    # A swallowed guard must therefore still fail the test during teardown.
    assert violations == [], "an operational boundary guard was reached"


class Directory:
    def __init__(self): self.data, self.events = {}, []
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def names(self): return tuple(self.data)
    def read(self, name):
        self.events.append(("read", name))
        return copy.deepcopy(self.data[name])
    def write(self, name, value):
        assert name.startswith("storage-recovery-v2-")
        self.events.append(("write", name))
        if name in self.data: raise FileExistsError()
        self.data[name] = copy.deepcopy(value)


class Response:
    def __init__(self, url, code=200, value=None, raw=None):
        self.url, self.code = url, code
        self.raw = json.dumps(value).encode() if raw is None else raw
        self.reads, self.closed = [], False
    def geturl(self): return self.url
    def read(self, size): self.reads.append(size); return self.raw
    def close(self): self.closed = True


def fixture(monkeypatch, existing=()):
    directory = Directory()
    monkeypatch.setattr(r, "_runtime_gate", lambda *_: None)
    monkeypatch.setattr(r, "_incident_binding", lambda *_: None)
    payloads = tuple(("PRIVATE-BYTES-" + str(i)).encode() for i in range(6))
    rows = [[r.PREFIX + "/file-" + str(i), hashlib.sha256(p).hexdigest(), len(p), i == 5]
            for i, p in enumerate(payloads)]
    descriptors = [SimpleNamespace(object_store_key=row[0], activation_manifest=row[3]) for row in rows]
    record = dict(upload_inventory=rows, upload_inventory_sha256=r._sha(rows))
    plan = SimpleNamespace(_input=object())
    monkeypatch.setattr(r.old, "_Directory", lambda: directory)
    monkeypatch.setattr(r.old, "require_family", lambda *_: copy.deepcopy(record))
    monkeypatch.setattr(r.old, "_bound", lambda *_: None)
    monkeypatch.setattr(r.old, "_input", lambda _: object())
    monkeypatch.setattr(r.old.compact, "iter_accepted_risk_preliminary_upload_objects", lambda _: iter(zip(descriptors, payloads)))
    monkeypatch.setattr(r.prior, "INVENTORY_SHA256", r._sha(rows))
    monkeypatch.setattr(r, "_retained", lambda *_: ORG)
    monkeypatch.setattr(r.prior, "_organization", lambda *_: ORG)
    monkeypatch.setattr(r.old, "_client", lambda: SimpleNamespace(_credentials=object(), _clock=lambda: 100))
    monkeypatch.setattr(r.old, "build_auth_headers", lambda *_: {"Authorization": "SYNTHETIC-PRIVATE"})
    calls, responses = [], []
    remote = {i: payloads[i] for i in existing}
    def listing():
        return {"success": True, "path": r.PREFIX, "objects": [
            dict(key=rows[i][0], name="file-"+str(i), modified="2026-10-14T00:00:00Z",
                 mime="application/octet-stream", folder=False, size=len(remote[i])) for i in sorted(remote)],
            "page": 0, "totalPages": int(bool(remote)), "objectStorageUsed": sum(map(len, remote.values()))}
    def properties(index):
        return dict(success=True, metadata=dict(key=rows[index][0], size=len(remote[index]),
            md5=hashlib.md5(remote[index], usedforsecurity=False).hexdigest(), preview="PRIVATE-PREVIEW"))
    class Opener:
        def open(self, request, timeout):
            endpoint = request.full_url.rsplit("/", 1)[-1]
            if endpoint == "list": index = None; value = listing()
            elif endpoint == "properties":
                body = json.loads(request.data)
                assert body["organizationId"] == ORG
                index = next(i for i, row in enumerate(rows) if row[0] == body["key"])
                value = properties(index)
            else:
                assert endpoint == "set"
                index = next(i for i, row in enumerate(rows) if row[0].encode() in request.data)
                assert payloads[index] in request.data and index not in remote
                remote[index] = payloads[index]
                value = {"success": True}
            calls.append((endpoint, index, request, timeout))
            response = Response(request.full_url, value=value)
            responses.append(response)
            return response
    monkeypatch.setattr(r.prior, "_opener", lambda: Opener())
    return SimpleNamespace(directory=directory, rows=rows, payloads=payloads, plan=plan,
        record=record, remote=remote, listing=listing, properties=properties, calls=calls, responses=responses)


def recover(f):
    r.claim(HEAD, SHA)
    return r.recover(f.plan, r.FAMILY_SHA256, HEAD, SHA, time.monotonic()+60)


@pytest.mark.parametrize("existing", [(), (0,), (0,1), (1,3), (0,1,2,3,4), tuple(range(6))])
def test_reconcile_existing_before_missing_then_activation_last(monkeypatch, existing):
    f = fixture(monkeypatch, existing)
    result = recover(f)
    assert result["complete"] is True and result["failure_code"] is None
    missing = [i for i in range(6) if i not in existing]
    expected = [("list", None)] + [("properties", i) for i in existing]
    expected += [(endpoint, i) for i in missing for endpoint in ("set", "properties")]
    assert [(e, i) for e, i, _, _ in f.calls] == expected
    assert result["attempted_request_count"] == len(f.calls) == 13-len(existing)
    assert result["requests"] == f.directory.data[r.REPORT]["requests"]
    assert "upload-valid.json" not in f.directory.data
    receipt = r.require_admission(f.directory, f.plan, f.record, result["receipt_sha256"])
    assert receipt["validated_indices"] == list(range(6)) and receipt["actual_exit_is_external"] is True
    assert receipt["legacy_upload_accepted"] is False
    assert "PRIVATE" not in json.dumps(result) and "PRIVATE" not in json.dumps(f.directory.data[r.REPORT])
    assert f.directory.events[0] == ("write", r.CLAIM)
    assert all(response.closed for response in f.responses)


@pytest.mark.parametrize("existing", [(5,), (0,5), (0,1,2,3,5)])
def test_activation_exists_without_all_data_never_writes(monkeypatch, existing):
    f = fixture(monkeypatch, existing)
    result = recover(f)
    assert not result["complete"] and result["failure_code"] == "activation_without_data"
    assert [(e, i) for e, i, _, _ in f.calls] == [("list", None)]
    assert r.ADMISSION not in f.directory.data


@pytest.mark.parametrize("mutation", ["extra", "path", "pagination", "bool_page", "float_total", "zero_nonempty",
    "objects_type", "folder", "duplicate", "unknown", "size", "float_size", "name", "missing_field", "negative_used"])
def test_listing_refusal_is_not_absence(monkeypatch, mutation):
    f = fixture(monkeypatch, (0,))
    value = f.listing()
    if mutation == "extra": value["unexpected"] = "PRIVATE"
    elif mutation == "path": value["path"] = r.PREFIX + "-other"
    elif mutation == "pagination": value["totalPages"] = 2
    elif mutation == "bool_page": value["page"] = False
    elif mutation == "float_total": value["totalPages"] = 1.0
    elif mutation == "zero_nonempty": value["totalPages"] = 0
    elif mutation == "objects_type": value["objects"] = {}
    elif mutation == "folder": value["objects"][0]["folder"] = True
    elif mutation == "duplicate": value["objects"] *= 2
    elif mutation == "unknown": value["objects"][0]["key"] += "-unknown"
    elif mutation == "size": value["objects"][0]["size"] += 1
    elif mutation == "float_size": value["objects"][0]["size"] = float(value["objects"][0]["size"])
    elif mutation == "name": value["objects"][0]["name"] = "other"
    elif mutation == "missing_field": del value["objects"][0]["folder"]
    elif mutation == "negative_used": value["objectStorageUsed"] = -1
    with pytest.raises(r.StorageRecoveryError): r._listing(value, f.rows)


@pytest.mark.parametrize("mutation", ["key", "size", "float_size", "md5", "md5_case", "preview", "unknown_field"])
def test_properties_use_exact_key_size_payload_md5(monkeypatch, mutation):
    f = fixture(monkeypatch, (0,))
    value = f.properties(0)
    if mutation == "key": value["metadata"]["key"] += "other"
    elif mutation == "size": value["metadata"]["size"] += 1
    elif mutation == "float_size": value["metadata"]["size"] = float(value["metadata"]["size"])
    elif mutation == "md5": value["metadata"]["md5"] = "0"*32
    elif mutation == "md5_case": value["metadata"]["md5"] = value["metadata"]["md5"].upper()
    elif mutation == "preview": value["metadata"]["preview"] = {"PRIVATE": ["LICENSED"]}
    elif mutation == "unknown_field": value["metadata"]["unknown"] = True
    if mutation in {"md5_case", "preview"}: r._properties(value, f.rows[0], f.payloads[0])
    else:
        with pytest.raises(r.StorageRecoveryError): r._properties(value, f.rows[0], f.payloads[0])


def test_known_existing_payload_mismatch_stops_before_any_put(monkeypatch):
    f = fixture(monkeypatch, (0,1))
    f.remote[1] = b"X"*len(f.payloads[1])
    result = recover(f)
    assert result["failure_code"] == "properties_mismatch"
    assert all(e != "set" for e, _, _, _ in f.calls) and r.ADMISSION not in f.directory.data


@pytest.mark.parametrize("which", [r.CLAIM, r.START])
def test_one_use_claim_start_collision_prevents_contact(monkeypatch, which):
    f = fixture(monkeypatch)
    if which == r.CLAIM:
        r.claim(HEAD, SHA)
        f.directory.events.clear()
        with pytest.raises(FileExistsError): r.claim(HEAD, SHA)
        assert f.directory.events == [("write", r.CLAIM)]
    else:
        r.claim(HEAD, SHA)
        f.directory.data[r.START] = {}
        with pytest.raises(FileExistsError): r.recover(f.plan, r.FAMILY_SHA256, HEAD, SHA, time.monotonic()+60)
    assert not f.calls


def test_unauthenticated_family_cannot_be_counterfeited():
    with pytest.raises(r.old.NewruleSubmissionError): REAL_REQUIRE_FAMILY(object(), r.FAMILY_SHA256)


@pytest.mark.parametrize("mutate", ["caller", "head", "profile", "attempt", "extra"])
def test_claim_exact_binding(monkeypatch, mutate):
    f = fixture(monkeypatch)
    r.claim(HEAD, SHA)
    if mutate == "caller": f.directory.data[r.CLAIM]["caller_sha256"] = "c"*64
    elif mutate == "head": f.directory.data[r.CLAIM]["expected_head"] = "c"*40
    elif mutate == "profile": f.directory.data[r.CLAIM]["profile_sha256"] = "c"*64
    elif mutate == "attempt": f.directory.data[r.CLAIM]["attempt_consumed"] = 1
    else: f.directory.data[r.CLAIM]["extra"] = True
    with pytest.raises(r.StorageRecoveryError): r.recover(f.plan, r.FAMILY_SHA256, HEAD, SHA, time.monotonic()+60)
    assert not f.calls


def fake_exchange(monkeypatch, response, throws=False):
    directory, calls = Directory(), []
    api = SimpleNamespace(_credentials=object(), _clock=lambda: 100)
    monkeypatch.setattr(r.old, "build_auth_headers", lambda *_: {"Authorization": "SYNTHETIC"})
    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            if throws: raise response
            return response
    monkeypatch.setattr(r.prior, "_opener", lambda: Opener())
    state = dict(requests=[], attempted_request_count=0)
    return directory, api, state, calls


@pytest.mark.parametrize("code", [301,401,403,404,429,500])
def test_http_refusal_retains_status_never_failed_body(monkeypatch, code):
    response = Response(r.old.API_BASE+"/object/list", code, raw=b"PRIVATE")
    directory, api, state, calls = fake_exchange(monkeypatch, response)
    with pytest.raises(r.StorageRecoveryError, match="http_status"):
        r._request(directory, api, "object/list", None, b'{}', "application/json", state, time.monotonic()+10)
    assert response.reads == [] and response.closed and len(calls) == 1
    assert state["attempted_request_count"] == 1 and state["requests"][0]["http_status"] == code


def test_http_error_preserves_numeric_status_without_read(monkeypatch):
    class Body(io.BytesIO):
        def read(self, *_): pytest.fail("failed body read")
    error = urllib.error.HTTPError(r.old.API_BASE+"/object/list", 403, "PRIVATE", {}, Body(b"PRIVATE"))
    directory, api, state, calls = fake_exchange(monkeypatch, error, True)
    with pytest.raises(r.StorageRecoveryError, match="http_status"):
        r._request(directory, api, "object/list", None, b'{}', "application/json", state, time.monotonic()+10)
    assert state["requests"][0]["http_status"] == 403 and len(calls) == 1


@pytest.mark.parametrize("raw,code", [(b'{"success":false,"errors":["quota exceeded"]}', "service_refused"),
    (b'{"success":true,"errors":["quota exceeded"]}', "response_contradiction"),
    (b'{"success":true,"success":false}', "diagnostic_refused"),
    (b'{"success":NaN}', "diagnostic_refused"), (b'[]', "response_schema"),
    (b'\xff', "response_encoding"), (b'{}junk', "response_json")])
def test_strict_response_and_contradictions_refuse_finite(monkeypatch, raw, code):
    response = Response(r.old.API_BASE+"/object/list", raw=raw)
    directory, api, state, calls = fake_exchange(monkeypatch, response)
    with pytest.raises(BaseException) as caught:
        r._request(directory, api, "object/list", None, b'{}', "application/json", state, time.monotonic()+10)
    assert r.finite_failure(caught.value) == code and len(calls) == 1 and response.closed
    assert state["requests"][0]["http_status"] == 200
    if b'quota' in raw: assert state["requests"][0]["error_category"] == "quota"


@pytest.mark.parametrize("mutation", ["overflow", "status_bool", "url", "timeout", "budget"])
def test_request_bounds_deadline_ambiguity_and_budget(monkeypatch, mutation):
    response = Response(r.old.API_BASE+"/object/list", value={"success": True})
    if mutation == "overflow": response.raw = b'x'*(r.MAX_RESPONSE_BYTES+1)
    elif mutation == "status_bool": response.code = True
    elif mutation == "url": response.url += "/other"
    elif mutation == "timeout": response = TimeoutError("PRIVATE")
    directory, api, state, calls = fake_exchange(monkeypatch, response, mutation == "timeout")
    if mutation == "budget": state["requests"] = [{}]*13
    with pytest.raises(BaseException):
        r._request(directory, api, "object/list", None, b'{}', "application/json", state, time.monotonic()+10)
    assert len(calls) == (0 if mutation == "budget" else 1)
    assert state["attempted_request_count"] == len(calls)


@pytest.mark.parametrize("when", ["existing", "set", "post_properties"])
def test_mid_recovery_refusal_has_no_retry_and_retains_safe_trace(monkeypatch, when):
    f = fixture(monkeypatch, (0,) if when == "existing" else ())
    original = r._request
    def request(directory, api, endpoint, index, body, content_type, state, deadline):
        if (when == "existing" and endpoint == "object/properties") or (
            when == "set" and endpoint == "object/set") or (when == "post_properties" and endpoint == "object/properties"):
            entry = dict(ordinal=len(state["requests"]), endpoint=endpoint, index=index, attempted=True,
                request_sha256=hashlib.sha256(body).hexdigest(),
                http_status=200, response_schema_valid=True, api_success=False, error_category="quota")
            state["requests"].append(entry); state["attempted_request_count"] += 1
            raise r.StorageRecoveryError("service_refused")
        return original(directory, api, endpoint, index, body, content_type, state, deadline)
    monkeypatch.setattr(r, "_request", request)
    result = recover(f)
    assert result["complete"] is False and result["failure_code"] == "service_refused"
    assert result["requests"][-1]["error_category"] == "quota"
    assert r.ADMISSION not in f.directory.data and "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("mutation", ["receipt_pin", "receipt_extra", "receipt_flag", "report_flag", "report_extra",
    "report_count_bool", "request_index_float", "request_missing", "order", "start", "intent", "intent_digest", "observed", "legacy"])
def test_admission_strict_external_pin_schema_and_census(monkeypatch, mutation):
    f = fixture(monkeypatch)
    result = recover(f)
    receipt, report = f.directory.data[r.ADMISSION], f.directory.data[r.REPORT]
    if mutation == "receipt_pin": result["receipt_sha256"] = "c"*64
    elif mutation == "receipt_extra": receipt["unknown"] = True
    elif mutation == "receipt_flag": receipt["formal_forward_ready"] = True
    elif mutation == "report_flag": report["legacy_upload_accepted"] = True
    elif mutation == "report_extra": report["private"] = "PRIVATE"
    elif mutation == "report_count_bool": report["attempted_request_count"] = True
    elif mutation == "request_index_float": report["requests"][1]["index"] = 0.0
    elif mutation == "request_missing": report["requests"].pop()
    elif mutation == "order": report["validated_indices"] = list(reversed(range(6)))
    elif mutation == "start": f.directory.data[r.START]["caller_sha256"] = "c"*64
    elif mutation == "intent": f.directory.data["storage-recovery-v2-request-00-intent.json"]["endpoint"] = "object/set"
    elif mutation == "intent_digest": f.directory.data["storage-recovery-v2-request-00-intent.json"]["request_sha256"] = "c"*64
    elif mutation == "observed": f.directory.data["storage-recovery-v2-request-00-observed.json"]["api_success"] = False
    elif mutation == "legacy": f.directory.data["upload-valid.json"] = {}
    if mutation != "receipt_pin":
        receipt["report_sha256"] = r._sha(report)
        result["receipt_sha256"] = r._sha(receipt)
    with pytest.raises(r.StorageRecoveryError): r.require_admission(f.directory, f.plan, f.record, result["receipt_sha256"])


@pytest.mark.parametrize("failure", ["post_source", "old_control", "report_collision", "admission_collision"])
def test_late_refusal_never_normal_admission(monkeypatch, failure):
    f = fixture(monkeypatch)
    calls = []
    def retained(*_):
        calls.append(None)
        if len(calls) == 2:
            if failure == "post_source": raise r.StorageRecoveryError("source_postcheck")
            if failure == "old_control": f.directory.data["other-lane.json"] = {}
        return ORG
    monkeypatch.setattr(r, "_retained", retained)
    if failure == "report_collision": f.directory.data[r.REPORT] = {}
    if failure == "admission_collision": f.directory.data[r.ADMISSION] = {}
    if "collision" in failure:
        with pytest.raises(r.StorageRecoveryError, match="publication_ambiguous"): recover(f)
    else:
        result = recover(f)
        assert not result["complete"] and r.ADMISSION not in f.directory.data


def test_finite_failure_does_not_render_unknown_or_hostile_types():
    class Meta(type):
        def __hash__(cls): pytest.fail("hash")
        def __eq__(cls, other): pytest.fail("equality")
    class Hostile(Exception, metaclass=Meta):
        def __str__(self): pytest.fail("str")
    assert r.finite_failure(Hostile("PRIVATE")) == "unknown_exception"
    assert r.finite_failure(r.StorageRecoveryError("PRIVATE")) == "unknown_exception"
    assert all(type(code) is str and len(code) <= 64 for code in r.FINITE_FAILURE_CODES)


def test_long_failure_label_refuses_before_inventory_lookup(monkeypatch):
    class Inventory:
        def __contains__(self, value): pytest.fail("long unknown text hashed/looked up")
    monkeypatch.setattr(r, "_CODES", Inventory())
    assert r.finite_failure(r.StorageRecoveryError("X"*65)) == "unknown_exception"


def test_multipart_exact_unchanged_frozen_geometry(monkeypatch):
    f = fixture(monkeypatch)
    body, content_type = r._multipart(ORG, f.rows[0][0], f.payloads[0])
    boundary = r.old.transport._multipart_boundary(f.payloads[0])
    expected = (f'--{boundary}\r\nContent-Disposition: form-data; name="organizationId"\r\n\r\n{ORG}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="key"\r\n\r\n{f.rows[0][0]}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="objectData"; filename="object.bin"\r\n'
        'Content-Type: application/octet-stream\r\n\r\n').encode() + f.payloads[0] + f'\r\n--{boundary}--\r\n'.encode()
    assert body == expected and content_type == "multipart/form-data; boundary="+boundary


@pytest.mark.parametrize("boundary", ["directory_alias", "client_alias", "opener", "socket", "input_loader"])
def test_independent_guards_block_stale_aliases_before_operational_access(isolate, boundary):
    calls = {
        "directory_alias": lambda: REAL_DIRECTORY(),
        "client_alias": lambda: REAL_CLIENT(),
        "opener": lambda: urllib.request.OpenerDirector().open("https://unused.invalid"),
        "socket": lambda: socket.create_connection(("unused.invalid", 443)),
        "input_loader": lambda: r.old.october.load_october_order_input_package("unused"),
    }
    with pytest.raises(pytest.fail.Exception, match="operational access forbidden"):
        calls[boundary]()
    assert isolate == ["operational_boundary"]
    isolate.clear()  # This test explicitly expected and verified the guard.


def retained_fixture(monkeypatch):
    f = fixture(monkeypatch)
    monkeypatch.setattr(r.helpers, "_source_digest", lambda path: r.D9_SHA256 if path == r.prior.SOURCE else r.prior.D8_SOURCE_SHA256)
    observed = []
    monkeypatch.setattr(r.prior, "_d8_binding", lambda *_: observed.append("d8_exact_external_binding"))
    value = {"schema": r.prior.SCHEMA, "profile_sha256": r.prior.PROFILE_SHA256,
        "expected_head": r.D9_HEAD, "caller_sha256": r.D9_SHA256, "family_sha256": r.FAMILY_SHA256,
        "started_at": "2026-10-14T00:00:00Z", "finished_at": "2026-10-14T00:00:01Z",
        "stage": "diagnostic_completed", "terminal": "metadata_observation_completed",
        "attempt_consumed": True, "failure_code": None, "attempted_request_count": 1,
        "http_status": 200, "observation": {"response_schema_valid": True, "api_success": False,
            "metadata_schema_valid": None, "key_matches": None, "size_matches": None,
            "md5_well_formed": None, "error_category": "unknown"},
        "diagnostic_only": True, "original_upload_accepted": False, "changes_original_exit": False,
        "historical_failure_cause_reconstructed": False, "measured_server_contact": False,
        "md5_content_authentication": False, "point_in_time_proven": False,
        "formal_forward_ready": False, "paper_or_live_ready": False}
    f.directory.data[r.prior.REPORT] = value
    raw = r.helpers.canonical_json_bytes(value)
    monkeypatch.setattr(r, "D9_REPORT_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(r, "D9_REPORT_BYTES", len(raw))
    return f, observed


def test_retained_binding_reuses_only_stateless_external_evidence_checks(monkeypatch):
    f, observed = retained_fixture(monkeypatch)
    assert REAL_RETAINED(f.directory, f.plan, f.record, time.monotonic()+30) == ORG
    assert observed == ["d8_exact_external_binding"]
    assert f.directory.events == [("read", r.prior.REPORT)] and not f.calls


@pytest.mark.parametrize("mutation", ["source_d8", "source_d9", "hash", "length", "head", "count_bool", "profile", "success", "legacy"])
def test_retained_d9_source_content_schema_and_legacy_refusal(monkeypatch, mutation):
    f, _ = retained_fixture(monkeypatch)
    value = f.directory.data[r.prior.REPORT]
    if mutation.startswith("source_"):
        bad = r.prior.D8_SOURCE if mutation == "source_d8" else r.prior.SOURCE
        monkeypatch.setattr(r.helpers, "_source_digest", lambda path: "c"*64 if path == bad else (
            r.D9_SHA256 if path == r.prior.SOURCE else r.prior.D8_SOURCE_SHA256))
    elif mutation == "hash": monkeypatch.setattr(r, "D9_REPORT_SHA256", "c"*64)
    elif mutation == "length": monkeypatch.setattr(r, "D9_REPORT_BYTES", r.D9_REPORT_BYTES+1)
    elif mutation == "head": value["expected_head"] = HEAD
    elif mutation == "count_bool": value["attempted_request_count"] = True
    elif mutation == "profile": value["profile_sha256"] = SHA
    elif mutation == "success": value["observation"]["api_success"] = True
    elif mutation == "legacy": f.directory.data["upload-valid.json"] = {}
    if mutation in {"head", "count_bool", "profile", "success"}:
        raw = r.helpers.canonical_json_bytes(value)
        monkeypatch.setattr(r, "D9_REPORT_SHA256", hashlib.sha256(raw).hexdigest())
        monkeypatch.setattr(r, "D9_REPORT_BYTES", len(raw))
    with pytest.raises(r.StorageRecoveryError): REAL_RETAINED(f.directory, f.plan, f.record, time.monotonic()+30)
    assert not f.calls


@pytest.mark.parametrize("mutation", ["payload", "type", "descriptor", "activation", "prefix"])
def test_payload_binding_preserves_immutable_inventory(monkeypatch, mutation):
    f = fixture(monkeypatch)
    payloads = list(f.payloads)
    descriptors = [SimpleNamespace(object_store_key=row[0], activation_manifest=row[3]) for row in f.rows]
    if mutation == "payload": payloads[0] += b'x'
    elif mutation == "type": payloads[0] = bytearray(payloads[0])
    elif mutation == "descriptor": descriptors[0].object_store_key += "-other"
    elif mutation == "activation": descriptors[0].activation_manifest = True
    elif mutation == "prefix":
        f.record["upload_inventory"][0][0] = "other-prefix/file-0"
        descriptors[0].object_store_key = "other-prefix/file-0"
        monkeypatch.setattr(r.prior, "INVENTORY_SHA256", r._sha(f.record["upload_inventory"]))
    monkeypatch.setattr(r.old.compact, "iter_accepted_risk_preliminary_upload_objects", lambda _: iter(zip(descriptors, payloads)))
    with pytest.raises(r.StorageRecoveryError): r._payloads(f.plan, f.record)


def gate_fixture(monkeypatch):
    """Public source/Git observations only, with no real subprocess or file read."""
    helper, caller = b"synthetic committed helper\n", b"synthetic committed caller\n"
    caller_sha = hashlib.sha256(caller).hexdigest()
    observed = []
    pins = {r.ROOT / path: digest for path, digest in
            (*r.prior.frozen.SOURCE_PINS.items(), *r.FROZEN_ADDITIONS.items())}
    pins.update({r.SOURCE: hashlib.sha256(helper).hexdigest(), r.CALLER_SOURCE: caller_sha})
    monkeypatch.setattr(r, "sys", SimpleNamespace(platform="darwin", version_info=(3,13,9),
        executable=str(r.prior.frozen.PYTHON)))
    monkeypatch.setattr(r, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(r, "_under_test", lambda: False)
    monkeypatch.setattr(r.helpers, "_source_digest", lambda path: pins[path])
    calls = []
    def git(arguments, deadline, limit=65536):
        calls.append(tuple(arguments))
        observed.append("git")
        if arguments == ["rev-parse", "--show-toplevel"]: return (str(r.ROOT)+"\n").encode()
        if arguments == ["branch", "--show-current"]: return (r.prior.frozen.BRANCH+"\n").encode()
        if arguments == ["rev-parse", "HEAD"]: return (HEAD+"\n").encode()
        if arguments == ["status", "--porcelain"]: return b""
        payload = helper if arguments[2].split(":", 1)[1] == r.SOURCE.relative_to(r.ROOT).as_posix() else caller
        if arguments[:2] == ["cat-file", "-s"]: return (str(len(payload))+"\n").encode()
        assert arguments[:2] == ["cat-file", "blob"] and limit == len(payload)
        return payload
    monkeypatch.setattr(r, "_git", git)
    return SimpleNamespace(caller=caller_sha, pins=pins, git=git, calls=calls, observed=observed)


def test_runtime_gate_requires_exact_clean_committed_source_bindings(monkeypatch):
    f = gate_fixture(monkeypatch)
    REAL_GATE(HEAD, f.caller, time.monotonic()+30)
    assert len(f.calls) == 10
    assert f.calls[-2:] == [("rev-parse", "HEAD"), ("status", "--porcelain")]
    assert [call[1] for call in f.calls if call[0] == "cat-file"] == ["-s", "blob", "-s", "blob"]


@pytest.mark.parametrize("mutation", [None, "returncode", "bool_returncode", "stderr", "stdout_type", "overflow"])
def test_git_observation_is_bounded_and_never_shell_dispatched(monkeypatch, mutation):
    seen = []
    result = SimpleNamespace(returncode=0, stdout=b"public\n", stderr=b"")
    if mutation == "returncode": result.returncode = 1
    elif mutation == "bool_returncode": result.returncode = False
    elif mutation == "stderr": result.stderr = b"warning"
    elif mutation == "stdout_type": result.stdout = "public\n"
    elif mutation == "overflow": result.stdout = b"x"*33
    def run(command, **kwargs):
        seen.append((command, kwargs))
        return result
    monkeypatch.setattr(r.subprocess, "run", run)
    if mutation is None: assert r._git(["status", "--porcelain"], time.monotonic()+30, 32) == b"public\n"
    else:
        with pytest.raises(r.StorageRecoveryError, match="helper_git_binding"):
            r._git(["status", "--porcelain"], time.monotonic()+30, 32)
    assert len(seen) == 1 and seen[0][0] == ["git", "status", "--porcelain"]
    assert seen[0][1] == dict(cwd=r.ROOT, stdin=r.subprocess.DEVNULL,
        capture_output=True, timeout=3, check=False)


@pytest.mark.parametrize("mutation", ["platform", "os", "python_version", "interpreter", "cwd",
    "root_realpath", "helper_path", "git_root", "branch", "head", "dirty", "late_head", "late_dirty",
    "old_pin", "frozen_pin", "caller_pin", "helper_blob", "caller_blob", "blob_size", "blob_huge",
    "source_inventory", "addition_inventory"])
def test_runtime_gate_refuses_each_host_commit_or_source_mismatch(monkeypatch, mutation):
    f = gate_fixture(monkeypatch)
    if mutation == "platform": r.sys.platform = "linux"
    elif mutation == "os": r.os.name = "nt"
    elif mutation == "python_version": r.sys.version_info = (3,12,1)
    elif mutation == "interpreter": r.sys.executable += "-other"
    elif mutation == "cwd": monkeypatch.setattr(r.Path, "cwd", classmethod(lambda cls: r.ROOT / "wrong"))
    elif mutation == "root_realpath": monkeypatch.setattr(r.Path, "resolve", lambda self: self / "wrong")
    elif mutation == "helper_path": monkeypatch.setattr(r, "SOURCE", r.SOURCE.with_name("other.py"))
    elif mutation == "old_pin": f.pins[r.ROOT / next(iter(r.prior.frozen.SOURCE_PINS))] = "c"*64
    elif mutation == "frozen_pin": f.pins[r.ROOT / next(iter(r.FROZEN_ADDITIONS))] = "c"*64
    elif mutation == "caller_pin": f.pins[r.CALLER_SOURCE] = "c"*64
    elif mutation == "source_inventory": monkeypatch.setattr(r.prior.frozen, "SOURCE_PINS", {})
    elif mutation == "addition_inventory": monkeypatch.setattr(r, "FROZEN_ADDITIONS", {})
    else:
        seen = {}
        def changed(arguments, deadline, limit=65536):
            key = tuple(arguments); seen[key] = seen.get(key, 0)+1
            value = f.git(arguments, deadline, limit)
            if mutation == "git_root" and arguments == ["rev-parse", "--show-toplevel"]: return b"wrong\n"
            if mutation == "branch" and arguments == ["branch", "--show-current"]: return b"wrong\n"
            if mutation in {"head", "late_head"} and arguments == ["rev-parse", "HEAD"] and (mutation == "head" or seen[key] == 2): return b"c"*40+b"\n"
            if mutation in {"dirty", "late_dirty"} and arguments == ["status", "--porcelain"] and (mutation == "dirty" or seen[key] == 2): return b" M tracked.py\n"
            if mutation == "helper_blob" and arguments[:2] == ["cat-file", "blob"] and arguments[2].split(":", 1)[1] == r.SOURCE.relative_to(r.ROOT).as_posix(): return b"X"*len(value)
            if mutation == "caller_blob" and arguments[:2] == ["cat-file", "blob"] and arguments[2].split(":", 1)[1] == r.CALLER_SOURCE.relative_to(r.ROOT).as_posix(): return b"X"*len(value)
            if mutation == "blob_size" and arguments[:2] == ["cat-file", "-s"]: return b"0\n"
            if mutation == "blob_huge" and arguments[:2] == ["cat-file", "-s"]: return b"2097153\n"
            return value
        monkeypatch.setattr(r, "_git", changed)
    with pytest.raises(r.StorageRecoveryError): REAL_GATE(HEAD, f.caller, time.monotonic()+30)


@pytest.mark.parametrize("operation", ["claim", "recover"])
def test_actual_pytest_context_refuses_before_any_directory(operation):
    with pytest.raises(r.StorageRecoveryError, match="operational_test_context"):
        if operation == "claim": r.claim(HEAD, SHA)
        else: r.recover(object(), r.FAMILY_SHA256, HEAD, SHA, time.monotonic()+30)


@pytest.mark.parametrize("operation", ["claim", "recover"])
def test_gate_is_mandatory_before_directory_even_with_valid_argument_shapes(monkeypatch, operation):
    f = fixture(monkeypatch)
    entered = []
    def gate(*_):
        entered.append("gate")
        raise r.StorageRecoveryError("helper_source_pin")
    monkeypatch.setattr(r, "_runtime_gate", gate)
    with pytest.raises(r.StorageRecoveryError, match="helper_source_pin"):
        if operation == "claim": r.claim(HEAD, SHA)
        else: r.recover(f.plan, r.FAMILY_SHA256, HEAD, SHA, time.monotonic()+30)
    assert entered == ["gate"] and f.directory.events == [] and f.calls == []


def incident_fixture():
    directory = Directory()
    binding = {"schema": "arv2-newrule-storage-recovery-v1", "profile_sha256": r.V1_PROFILE_SHA256,
        "family_sha256": r.FAMILY_SHA256, "expected_head": "a"*40, "caller_sha256": "b"*64}
    directory.data["storage-recovery-v1-claim.json"] = dict(binding, attempt_consumed=True)
    directory.data["storage-recovery-v1-start.json"] = dict(binding)
    directory.data["storage-recovery-v1-report.json"] = dict(binding,
        organization_sha256=r.ORGANIZATION_SHA256, inventory_sha256=r.prior.INVENTORY_SHA256,
        stage="retained_authentication", complete=False, attempt_consumed=True,
        failure_code="genuine_family_required", attempted_request_count=0, requests=[],
        existing_indices=[], published_indices=[], validated_indices=[], legacy_upload_accepted=False,
        atomic_absent_only_put=False, actual_exit_is_external=True, formal_forward_ready=False,
        point_in_time_proven=False, paper_or_live_ready=False)
    return directory


def test_exact_accidental_refusal_canonical_schema_matches_external_pin_without_private_read():
    directory = incident_fixture()
    raw = r.helpers.canonical_json_bytes(directory.data["storage-recovery-v1-report.json"])
    assert len(raw) == r.V1_REFUSAL_BYTES == 935
    assert hashlib.sha256(raw).hexdigest() == r.V1_REFUSAL_SHA256
    REAL_INCIDENT(directory)
    assert directory.events == [("read", "storage-recovery-v1-"+name+".json") for name in ("claim", "start", "report")]


@pytest.mark.parametrize("mutation", ["claim", "start", "pin", "length", "head", "caller", "complete",
    "count_bool", "requests", "failure", "extra", "profile", "legacy"])
def test_incident_binding_refuses_exact_pin_and_schema_drift(monkeypatch, mutation):
    directory = incident_fixture()
    report = directory.data["storage-recovery-v1-report.json"]
    if mutation in {"claim", "start"}: directory.data["storage-recovery-v1-"+mutation+".json"]["expected_head"] = "c"*40
    elif mutation == "pin": monkeypatch.setattr(r, "V1_REFUSAL_SHA256", "c"*64)
    elif mutation == "length": monkeypatch.setattr(r, "V1_REFUSAL_BYTES", 936)
    else:
        key, value = {"head": ("expected_head", "c"*40), "caller": ("caller_sha256", "c"*64),
            "complete": ("complete", True), "count_bool": ("attempted_request_count", False),
            "requests": ("requests", [{}]), "failure": ("failure_code", "unknown_exception"),
            "extra": ("unexpected", True), "profile": ("profile_sha256", "c"*64),
            "legacy": ("legacy_upload_accepted", True)}[mutation]
        report[key] = value
        raw = r.helpers.canonical_json_bytes(report)
        # Isolate schema validation beyond the independently tested byte pin.
        monkeypatch.setattr(r, "V1_REFUSAL_SHA256", hashlib.sha256(raw).hexdigest())
        monkeypatch.setattr(r, "V1_REFUSAL_BYTES", len(raw))
    with pytest.raises(r.StorageRecoveryError): REAL_INCIDENT(directory)


def test_claim_consumes_before_incident_and_authenticates_before_return(monkeypatch):
    directory = incident_fixture()
    gate_calls = []
    monkeypatch.setattr(r, "_runtime_gate", lambda *_: gate_calls.append("gate"))
    monkeypatch.setattr(r.old, "_Directory", lambda: directory)
    result = r.claim(HEAD, SHA)
    assert gate_calls == ["gate"] and result["attempt_consumed"] is True
    assert directory.events == [("write", r.CLAIM)] + [("read", "storage-recovery-v1-"+name+".json") for name in ("claim", "start", "report")]


def test_incident_mismatch_consumes_claim_but_never_returns_for_private_input_load(monkeypatch):
    directory = incident_fixture()
    directory.data["storage-recovery-v1-claim.json"]["expected_head"] = "c"*40
    monkeypatch.setattr(r, "_runtime_gate", lambda *_: None)
    monkeypatch.setattr(r.old, "_Directory", lambda: directory)
    with pytest.raises(r.StorageRecoveryError, match="prior_refusal_schema"): r.claim(HEAD, SHA)
    assert r.CLAIM in directory.data and r.START not in directory.data
    assert directory.events[0] == ("write", r.CLAIM)


def test_recovery_reauthenticates_incident_after_start_before_retained_or_credentials(monkeypatch):
    f = fixture(monkeypatch)
    r.claim(HEAD, SHA)
    checked = []
    def incident(directory):
        checked.append(r.START in directory.data)
        raise r.StorageRecoveryError("prior_refusal_pin")
    monkeypatch.setattr(r, "_incident_binding", incident)
    monkeypatch.setattr(r, "_retained", lambda *_: pytest.fail("retained reads forbidden after incident refusal"))
    result = r.recover(f.plan, r.FAMILY_SHA256, HEAD, SHA, time.monotonic()+30)
    assert checked == [True] and result["failure_code"] == "prior_refusal_pin"
    assert result["complete"] is False and result["attempted_request_count"] == 0
    assert result["requests"] == [] and f.calls == [] and r.ADMISSION not in f.directory.data
    assert f.directory.data[r.REPORT]["prior_v1_refusal_sha256"] == r.V1_REFUSAL_SHA256
