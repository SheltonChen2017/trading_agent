"""Synthetic six-object protocol; production artifacts and network stay denied."""
import copy
import ast
import hashlib
import io
import json
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest

from tests.analyst_revisions_v2._dispatch_fence_closure import assert_lane_closure_excludes_dispatch_fence

from scripts import run_arv2_newrule_comparison as frozen_baseline
BASELINE_SCRIPT_MODULES = frozenset(name for name in sys.modules if name.startswith("scripts."))
from scripts import arv2_newrule_storage_recovery_v4 as d
from scripts import run_arv2_newrule_storage_recovery_v4 as caller
INTRODUCED_SCRIPT_MODULES = frozenset(name for name in sys.modules if name.startswith("scripts.")) - BASELINE_SCRIPT_MODULES

old, HEAD, SHA, ORG = d.old, "a" * 40, "b" * 64, "f" * 32
REAL_DIRECTORY, REAL_CLIENT = old._Directory, old.QuantConnectClient
REAL_GATE, REAL_RECOVER, REAL_CALLER_PREFLIGHT = d._runtime_gate, d.recover, caller._preflight


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    violations = []
    def forbidden(*_args, **_kwargs):
        violations.append("operational_boundary")
        pytest.fail("operational boundary forbidden")
    monkeypatch.setattr(REAL_DIRECTORY, "__init__", forbidden)
    monkeypatch.setattr(REAL_CLIENT, "__init__", forbidden)
    for owner, names in (
        (old, ("_Directory", "_client", "_input", "load_family", "prepare_family", "upload_inputs", "capacity_once", "begin_attempt", "_session")),
        (old.coverage, ("production_client",)), (old.october, ("load_october_order_input_package",)),
        (old.compact, ("load_accepted_risk_preliminary_package",)),
        (d.primitives, ("claim", "recover", "require_admission", "_runtime_gate", "_retained", "_request")),
        (d.family, ("run", "_run", "_census")), (d.organization_reader, ("run", "_run", "_transport")),
        (d.payload_reader, ("run", "_run", "_transport", "_retained", "_listing_binding", "_dependencies")),
        (d.error_text, ("run", "_run", "_transport", "_preflight")), (d.frozen, ("run", "_operation")),
        (urllib.request.OpenerDirector, ("open",)), (socket, ("create_connection", "getaddrinfo")),
        (socket.socket, ("connect", "connect_ex")), (old.http.client.HTTPConnection, ("request", "connect")),
        (old.http.client.HTTPSConnection, ("connect",)),
    ):
        for name in names: monkeypatch.setattr(owner, name, forbidden)
    yield violations
    assert violations == [], "swallowed operational boundary"


class Directory:
    def __init__(self):
        self.data = {"family.json": {}, "organization.json": {}, "organization-claim.json": {}, "preparation-claim.json": {}}
        self.closed, self.events = False, []
    def names(self): return tuple(self.data)
    def read(self, name): self.events.append(("read", name)); return copy.deepcopy(self.data[name])
    def write(self, name, value):
        assert name.startswith(d.STEM)
        self.events.append(("write", name))
        if name in self.data: raise FileExistsError()
        self.data[name] = copy.deepcopy(value)
    def verify(self): self.events.append(("verify", None))
    def __exit__(self, *_): self.closed = True


class Response:
    def __init__(self, url, value, code=200):
        self.url, self.value, self.code, self.closed, self.reads = url, value, code, False, []
    def geturl(self): return self.url
    def read(self, size):
        self.reads.append(size)
        return self.value if type(self.value) is bytes else json.dumps(self.value).encode()
    def close(self): self.closed = True


def fixture(monkeypatch, present=()):
    directory, calls, responses, events, overrides = Directory(), [], [], [], {}
    payloads = tuple(("synthetic-payload-" + str(i)).encode() for i in range(6))
    rows = [["private-prefix/object-" + str(i), hashlib.sha256(payload).hexdigest(), len(payload), i == 5] for i, payload in enumerate(payloads)]
    record = {"upload_inventory": rows}; value = object(); plan = SimpleNamespace(_input=value)
    server = set(present)
    monkeypatch.setattr(d, "_runtime_gate", lambda *_: events.append("gate"))
    monkeypatch.setattr(caller, "_preflight", lambda *_: events.append("caller_gate"))
    monkeypatch.setattr(old, "_Directory", lambda: directory)
    def retained(*_):
        assert d.CLAIM in directory.data and d.START in directory.data
        events.append("retained")
        return record, ORG
    monkeypatch.setattr(d, "_retained", retained)
    def load(*_):
        assert d.CLAIM in directory.data
        events.append("package")
        return value, payloads
    monkeypatch.setattr(d.payload_reader, "_load_payloads", load)
    monkeypatch.setattr(d.payload_reader, "_package_payloads", lambda *_: payloads)
    monkeypatch.setattr(d.family, "_family_binding", lambda *_: record)
    monkeypatch.setattr(d.organization_reader, "_organization", lambda *_: ORG)
    monkeypatch.setattr(old, "require_family", lambda passed, pin: record if passed is plan and pin == d.FAMILY_SHA256 else None)
    monkeypatch.setattr(old, "_bound", lambda *_: None)
    def client():
        assert d.CLAIM in directory.data and "package" in events
        events.append("credentials")
        return SimpleNamespace(_credentials=SimpleNamespace(user_id="private-user", api_token="private-token"), _clock=lambda: 100)
    monkeypatch.setattr(old, "_client", client)
    monkeypatch.setattr(old, "_safe_environment", lambda: None)
    monkeypatch.setattr(old, "build_auth_headers", lambda *_: {"Authorization": "private-auth", "Timestamp": "1234567890"})
    def good(index):
        return {"success": True, "metadata": {"key": rows[index][0], "size": rows[index][2],
            "md5": hashlib.md5(payloads[index], usedforsecurity=False).hexdigest(), "preview": "PRIVATE-PREVIEW"}}
    def absent(index): return {"success": False, "errors": [d.ABSENCE_TEMPLATES[0].format(key=rows[index][0])]}
    class Opener:
        def open(self, request, timeout):
            ordinal = len(calls); intent = directory.data[d._stem(ordinal) + "-intent.json"]
            phase, index = intent["phase"], intent["index"]
            assert d.CLAIM in directory.data and d.START in directory.data
            assert intent["request_sha256"] == hashlib.sha256(request.data).hexdigest()
            assert intent["endpoint"] == request.full_url.rsplit("/api/v2/", 1)[-1]
            calls.append((phase, index, request, timeout))
            if phase == "put": server.add(index)
            response = overrides.get((phase, index), {"success": True} if phase == "put" else good(index) if index in server else absent(index))
            if isinstance(response, BaseException): raise response
            if not isinstance(response, Response): response = Response(request.full_url, response)
            responses.append(response)
            return response
    monkeypatch.setattr(d.error_text, "_opener", lambda: Opener())
    return SimpleNamespace(directory=directory, calls=calls, responses=responses, events=events, overrides=overrides,
        rows=rows, payloads=payloads, record=record, plan=plan, value=value, good=good, absent=absent)


def execute(): return d.recover(HEAD, SHA, time.monotonic() + 300)


@pytest.mark.parametrize("mask", range(64))
def test_all_64_initial_subsets_have_exact_trace_and_activation_last(monkeypatch, mask):
    present = [i for i in range(6) if mask & (1 << i)]
    missing = [i for i in range(6) if i not in present]
    f = fixture(monkeypatch, present); result = execute()
    assert f.directory.closed and f.events[:4] == ["gate", "retained", "package", "credentials"]
    expected = [("initial", i) for i in range(6)]
    refused = 5 in present and len(present) != 6
    if not refused: expected += [(phase, i) for i in missing for phase in ("recheck", "put", "verify")]
    assert [(phase, index) for phase, index, *_ in f.calls] == expected
    assert result["attempted_request_count"] == len(expected) <= 24
    assert result["complete"] is (not refused)
    assert all(0 < timeout <= 30 for *_, timeout in f.calls)
    assert all(response.closed and response.reads == [d.MAX_RESPONSE_BYTES + 1] for response in f.responses)
    assert "private-prefix" not in json.dumps(result) and "PRIVATE-PREVIEW" not in json.dumps(result)
    assert "upload-valid.json" not in f.directory.data
    if refused:
        assert result["failure_code"] == "activation_without_data" and d.ADMISSION not in f.directory.data
    else:
        receipt = d.require_admission(f.directory, f.plan, f.record, result["receipt_sha256"])
        assert receipt["validated_indices"] == list(range(6))
        assert caller._safe_result(result, d) == result
        assert len([1 for phase, *_ in f.calls if phase == "put"]) == len(missing)


@pytest.mark.parametrize("template", d.ABSENCE_TEMPLATES)
def test_only_exact_selected_full_key_templates_are_supported(monkeypatch, template):
    f = fixture(monkeypatch, range(6))
    value = {"success": False, "errors": [template.format(key=f.rows[0][0])]}
    assert d._properties_state(value, f.rows[0], f.payloads[0]) == ("absent", d.ABSENCE_TEMPLATES.index(template))


@pytest.mark.parametrize("case", ["wrong_key", "generic", "redacted", "org", "negation", "lowercase", "leading", "trailing", "encoded", "multiple", "null_metadata_data", "api_missing", "success_int"])
def test_unknown_or_ambiguous_absence_stops_before_all_sets(monkeypatch, case):
    f = fixture(monkeypatch)
    value = f.absent(0)
    messages = {"wrong_key": "File not found: private-prefix/other", "generic": "File not found", "redacted": "file not found [redacted]",
        "org": "Organization not found: " + ORG, "negation": "File not found: " + f.rows[0][0] + " is not the error",
        "lowercase": value["errors"][0].lower(), "leading": " " + value["errors"][0], "trailing": value["errors"][0] + ".",
        "encoded": "File not found: private-prefix%2Fobject-0"}
    if case in messages: value["errors"] = [messages[case]]
    elif case == "multiple": value["errors"] *= 2
    elif case == "null_metadata_data": value["metadata"] = {}
    elif case == "api_missing": del value["success"]
    elif case == "success_int": value["success"] = 0
    f.overrides[("initial", 0)] = value
    result = execute()
    assert result["complete"] is False and len(f.calls) == 1 and not any(phase == "put" for phase, *_ in f.calls)
    assert d.ADMISSION not in f.directory.data
    assert (result["requests"][0]["observation"] is None) is (case == "success_int")
    assert caller._safe_result(result, d) == result


@pytest.mark.parametrize("field", ["key", "size", "md5", "errors", "size_bool"])
def test_known_initial_mismatch_prevents_every_set(monkeypatch, field):
    f = fixture(monkeypatch, [4]); value = f.good(4)
    if field == "errors": value["errors"] = ["permission denied"]
    elif field == "size_bool": value["metadata"]["size"] = True
    else: value["metadata"][field] = {"key": "wrong-private-key", "size": 99, "md5": "0" * 32}[field]
    f.overrides[("initial", 4)] = value
    result = execute()
    assert not result["complete"] and len(f.calls) == 5 and all(phase == "initial" for phase, *_ in f.calls)


@pytest.mark.parametrize("state", ["present", "wrong_key", "permission", "http", "cancel"])
def test_immediate_recheck_change_always_stops_without_put(monkeypatch, state):
    f = fixture(monkeypatch)
    value = {"present": f.good(0), "wrong_key": {"success": False, "errors": ["File not found: other"]},
        "permission": {"success": False, "errors": ["Permission denied"]},
        "http": Response(old.API_BASE + "/object/properties", {"errors": ["Permission denied"]}, 403),
        "cancel": KeyboardInterrupt("PRIVATE")}[state]
    f.overrides[("recheck", 0)] = value
    result = execute()
    assert not result["complete"] and len(f.calls) == 7 and all(phase != "put" for phase, *_ in f.calls)
    assert caller._safe_result(result, d) == result


@pytest.mark.parametrize("phase", ["initial", "recheck", "put", "verify"])
def test_numeric_status_safe_redacted_refusal_survives_each_phase(monkeypatch, phase):
    f = fixture(monkeypatch)
    endpoint = "object/set" if phase == "put" else "object/properties"
    f.overrides[(phase, 0)] = Response(old.API_BASE + "/" + endpoint,
        {"errors": ["Permission denied for private-token organization " + ORG]}, 403)
    result = execute(); last = result["requests"][-1]
    assert not result["complete"] and result["failure_code"] == "http_status" and last["http_status"] == 403
    assert last["observation"]["api_success"] is None
    assert "permission denied" in last["observation"]["redacted_provider_reasons"][0]
    assert "private-token" not in json.dumps(result) and ORG not in json.dumps(result)
    assert caller._safe_result(result, d) == result


def test_unknown_error_shape_is_finite_and_never_absence(monkeypatch):
    f = fixture(monkeypatch); text = "File not found >>> " + f.rows[0][0] + " <<<"
    f.overrides[("initial", 0)] = {"success": False, "errors": [text]}
    result = execute(); shape = result["requests"][0]["error_shape"]
    assert shape == {"file_not_found_prefix": True, "requested_key_occurrences": 1, "prefix_characters": 19, "suffix_characters": 4}
    assert result["failure_code"] == "absence_unproven" and not result["complete"]


@pytest.mark.parametrize("case", ["oversize", "duplicate", "nonfinite", "encoding", "html", "redirect", "timeout", "close", "api_false_put", "absent_verify"])
def test_transport_and_terminal_refusals_do_not_continue(monkeypatch, case):
    f = fixture(monkeypatch)
    response = Response(old.API_BASE + "/object/properties", f.absent(0))
    raw = {"oversize": b"x" * (d.MAX_RESPONSE_BYTES + 1), "duplicate": b'{"success":false,"success":true}',
        "nonfinite": b'{"success":false,"metadata":NaN}', "encoding": b'\xff', "html": b'<html>PRIVATE</html>'}
    if case in raw: response.value = raw[case]
    elif case == "redirect": response.url = "https://unused.invalid"
    elif case == "timeout": response = TimeoutError("PRIVATE")
    elif case == "close":
        def fail(): raise OSError("PRIVATE")
        response.close = fail
    phase = "initial"
    if case == "api_false_put": phase, response = "put", {"success": False, "errors": ["quota exceeded"]}
    if case == "absent_verify": phase, response = "verify", f.absent(0)
    f.overrides[(phase, 0)] = response
    result = execute()
    assert not result["complete"] and d.ADMISSION not in f.directory.data
    assert "PRIVATE" not in json.dumps(result) and caller._safe_result(result, d) == result
    if phase == "initial": assert len(f.calls) == 1


@pytest.mark.parametrize("stage", ["gate", "claim", "start", "retained", "package", "credentials", "post_payload", "post_head", "old_names", "report", "receipt", "verify", "close"])
def test_claim_boundaries_and_late_failure_cannot_return_success(monkeypatch, stage, capsys):
    f = fixture(monkeypatch, range(6))
    def fail(*_): raise d.StorageRecoveryError("publication_ambiguous")
    if stage == "gate": monkeypatch.setattr(d, "_runtime_gate", fail)
    elif stage in {"claim", "start", "report", "receipt"}: f.directory.data[{"claim": d.CLAIM, "start": d.START, "report": d.REPORT, "receipt": d.ADMISSION}[stage]] = {}
    elif stage == "retained": monkeypatch.setattr(d, "_retained", fail)
    elif stage == "package": monkeypatch.setattr(d.payload_reader, "_load_payloads", fail)
    elif stage == "credentials": monkeypatch.setattr(old, "_client", fail)
    elif stage == "post_payload":
        seen = []
        def load(*_): seen.append(1); return f.value, f.payloads if len(seen) == 1 else (b"changed",)
        monkeypatch.setattr(d.payload_reader, "_load_payloads", load)
    elif stage == "post_head":
        def gate(*_):
            if f.calls: fail()
        monkeypatch.setattr(d, "_runtime_gate", gate)
    elif stage == "old_names":
        def gate(*_):
            if f.calls: f.directory.data["unexpected-old.json"] = {}
        monkeypatch.setattr(d, "_runtime_gate", gate)
    else: setattr(f.directory, "verify" if stage == "verify" else "__exit__", fail)
    assert caller.run(SimpleNamespace(expected_head=HEAD, caller_sha256=SHA)) == 2
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["operation_completed"] is False
    if stage in {"gate", "claim", "start", "retained", "package", "credentials"}: assert not f.calls
    # A retained receipt can precede a late directory/close failure. External
    # actual exit2 above makes it inadmissible, even if its bytes exist.
    if stage in {"verify", "close"}: assert d.ADMISSION in f.directory.data and "result" not in envelope


def test_dependency_refusal_keeps_finite_failure_and_report_pin(monkeypatch):
    fixture(monkeypatch)
    def fail(*_): raise d.family.DiagnosticRefusal("PRIVATE")
    monkeypatch.setattr(d, "_retained", fail)
    result = execute()
    assert result["failure_code"] == "dependency_validation_refused" and caller._safe_result(result, d) == result


def test_real_test_context_blocks_direct_helper_before_directory():
    with pytest.raises(d.StorageRecoveryError, match="operational_test_context"):
        REAL_RECOVER(HEAD, SHA, time.monotonic() + 300)


@pytest.mark.parametrize("which", ["directory", "client", "socket", "old_recover"])
def test_captured_seams_block_stale_aliases(isolation, which):
    methods = {"directory": lambda: REAL_DIRECTORY(), "client": lambda: REAL_CLIENT(),
        "socket": lambda: socket.create_connection(("unused.invalid", 443)), "old_recover": lambda: d.primitives.recover(None, None, None, None, 0)}
    with pytest.raises(pytest.fail.Exception): methods[which]()
    assert isolation == ["operational_boundary"]; isolation.clear()


def repin(f):
    report = f.directory.data[d.REPORT]
    receipt = d._receipt(HEAD, SHA, report)
    f.directory.data[d.ADMISSION] = receipt
    return d._sha(receipt)


@pytest.mark.parametrize("mutation", ["external", "report_pin", "receipt_flag", "claim", "start", "extra", "count_bool", "initial", "published", "validated",
    "phase", "index_bool", "digest", "attempted", "status_bool", "api", "template", "error_shape", "observation_words", "intent", "observed", "own_name", "legacy"])
def test_admission_rejects_changed_receipt_trace_markers_and_type_aliases(monkeypatch, mutation):
    f = fixture(monkeypatch); result = execute(); pin = result["receipt_sha256"]
    report, receipt = f.directory.data[d.REPORT], f.directory.data[d.ADMISSION]
    if mutation == "external": pin = "0" * 64
    elif mutation == "report_pin": report["stage"] = "changed"
    elif mutation == "receipt_flag": receipt["actual_exit_is_external"] = 1; pin = d._sha(receipt)
    elif mutation == "claim": f.directory.data[d.CLAIM]["attempt_consumed"] = 1
    elif mutation == "start": f.directory.data[d.START]["caller_sha256"] = "0" * 64
    elif mutation == "intent": f.directory.data[d._stem(0) + "-intent.json"]["index"] = False
    elif mutation == "observed": f.directory.data[d._stem(0) + "-observed.json"]["observation_record"]["attempted"] = 1
    elif mutation == "own_name": f.directory.data[d.STEM + "unexpected.json"] = {}
    elif mutation == "legacy": f.directory.data["upload-valid.json"] = {}
    else:
        if mutation == "extra": report["extra"] = True
        elif mutation == "count_bool": report["attempted_request_count"] = True
        elif mutation == "initial": report["initial_states"][0] = "present"
        elif mutation == "published": report["published_indices"] = [5, 0, 1, 2, 3, 4]
        elif mutation == "validated": report["validated_indices"] = [0]
        else:
            entry = report["requests"][0]
            key, value = {"phase": ("phase", "recheck"), "index_bool": ("index", False), "digest": ("request_sha256", "0" * 64),
                "attempted": ("attempted", False), "status_bool": ("http_status", True), "template": ("absence_template_index", True),
                "error_shape": ("error_shape", None)}.get(mutation, (None, None))
            if key: entry[key] = value
            elif mutation == "api": entry["observation"]["api_success"] = True
            else: entry["observation"]["redacted_provider_reasons"] = ["PRIVATE"]
        pin = repin(f)
    with pytest.raises(d.StorageRecoveryError): d.require_admission(f.directory, f.plan, f.record, pin)


def gate_fixture(monkeypatch):
    raw = {d.SOURCE: b"synthetic helper\n", d.CALLER_SOURCE: b"synthetic caller\n"}
    pins = {d.ROOT / name: pin for name, pin in {**dict(d.frozen.SOURCE_PINS), **d.ADDITIONS}.items()}
    pins.update({path: hashlib.sha256(value).hexdigest() for path, value in raw.items()})
    monkeypatch.setattr(d, "_under_test", lambda: False)
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: pins[path])
    def git(args, deadline, limit=65536):
        values = {("rev-parse", "--show-toplevel"): str(d.ROOT), ("branch", "--show-current"): d.frozen.BRANCH,
            ("rev-parse", "HEAD"): HEAD, ("status", "--porcelain"): ""}
        if tuple(args) in values: return values[tuple(args)].encode()
        path = d.ROOT / args[2].split(":", 1)[1]
        if args[:2] == ["cat-file", "-s"]: return str(len(raw[path])).encode()
        assert args[:2] == ["cat-file", "blob"] and limit == len(raw[path]); return raw[path]
    monkeypatch.setattr(d, "_git", git)
    return SimpleNamespace(raw=raw, pins=pins, git=git, caller=pins[d.CALLER_SOURCE])


def test_exact_runtime_gate_known_good_synthetic_git(monkeypatch):
    f = gate_fixture(monkeypatch); REAL_GATE(HEAD, f.caller, time.monotonic() + 300)


@pytest.mark.parametrize("mutation", ["root", "branch", "head", "dirty", "helper_source", "caller_source", "dependency", "blob", "size", "path", "deadline"])
def test_gate_checks_exact_host_and_committed_closure(monkeypatch, mutation):
    f = gate_fixture(monkeypatch)
    if mutation in {"helper_source", "caller_source"}: f.pins[d.SOURCE if mutation == "helper_source" else d.CALLER_SOURCE] = "0" * 64
    elif mutation == "dependency": f.pins[d.ROOT / next(iter(d.ADDITIONS))] = "0" * 64
    elif mutation == "path": monkeypatch.setattr(d, "SOURCE", d.SOURCE.with_name("other.py"))
    elif mutation != "deadline":
        def changed(args, deadline, limit=65536):
            value = f.git(args, deadline, limit)
            match = {"root": ["rev-parse", "--show-toplevel"], "branch": ["branch", "--show-current"], "head": ["rev-parse", "HEAD"], "dirty": ["status", "--porcelain"]}
            if args == match.get(mutation): return b"changed"
            if mutation == "size" and args[:2] == ["cat-file", "-s"]: return b"0"
            if mutation == "blob" and args[:2] == ["cat-file", "blob"]: return b"x" * len(value)
            return value
        monkeypatch.setattr(d, "_git", changed)
    with pytest.raises(d.StorageRecoveryError): REAL_GATE(HEAD, f.caller, time.monotonic() + (301 if mutation == "deadline" else 300))


def test_caller_refused_preflight_never_imports_or_calls_helper(monkeypatch, capsys):
    def refused(*_): raise caller.RecoveryOperationRefusal("operation_refused")
    monkeypatch.setattr(caller, "_preflight", refused)
    monkeypatch.setattr(d, "recover", lambda *_: pytest.fail("helper forbidden"))
    assert caller.run(SimpleNamespace(expected_head=HEAD, caller_sha256=SHA)) == 2
    assert json.loads(capsys.readouterr().out)["failure_code"] == "operation_refused"


def test_source_literals_and_selected_executed_import_closure():
    import sys
    assert caller.FROZEN_CALLER_SHA256 == d.error_text.FROZEN_CALLER_SHA256
    assert caller.HELPER_SHA256 == hashlib.sha256(d.SOURCE.read_bytes()).hexdigest()
    for name, pin in {**dict(d.frozen.SOURCE_PINS), **d.ADDITIONS}.items():
        assert hashlib.sha256((d.ROOT / name).read_bytes()).hexdigest() == pin
    assert_lane_closure_excludes_dispatch_fence()
    selected = set(d.frozen.SOURCE_PINS) | set(d.ADDITIONS)
    selected |= {d.SOURCE.relative_to(d.ROOT).as_posix(), caller.SOURCE.relative_to(d.ROOT).as_posix()}
    for name, module in tuple(sys.modules.items()):
        path = getattr(module, "__file__", None)
        if name in INTRODUCED_SCRIPT_MODULES and path and Path(path).suffix == ".py":
            relative = Path(path).relative_to(d.ROOT).as_posix()
            assert relative in selected, relative


@pytest.mark.parametrize("case", ["valid", "caller", "helper", "dependency", "host", "pending"])
def test_caller_preimport_gate_binds_selected_sources(monkeypatch, case):
    monkeypatch.setattr(caller, "sys", SimpleNamespace(modules={}))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    seen = []
    monkeypatch.setattr(caller.frozen, "_preflight", lambda args, deadline: seen.append(args))
    monkeypatch.setattr(caller, "HELPER_SHA256", "c" * 64)
    pins = {caller.ROOT / name: pin for name, pin in caller.ADDITIONS.items()}
    pins.update({caller.SOURCE: SHA, caller.HELPER_SOURCE: "c" * 64})
    monkeypatch.setattr(caller.helpers, "_source_digest", lambda path: pins[path])
    if case == "caller": pins[caller.SOURCE] = "0" * 64
    elif case == "helper": pins[caller.HELPER_SOURCE] = "0" * 64
    elif case == "dependency": pins[caller.ROOT / next(iter(caller.ADDITIONS))] = "0" * 64
    elif case == "host":
        def refused(*_): raise caller.frozen.OperationRefusal("PRIVATE")
        monkeypatch.setattr(caller.frozen, "_preflight", refused)
    elif case == "pending": monkeypatch.setattr(caller, "HELPER_SHA256", "PENDING")
    args = SimpleNamespace(expected_head=HEAD, caller_sha256=SHA)
    if case == "valid":
        REAL_CALLER_PREFLIGHT(args, time.monotonic() + 300)
        assert len(seen) == 1 and seen[0].caller_sha256 == d.error_text.FROZEN_CALLER_SHA256
    else:
        with pytest.raises(ValueError): REAL_CALLER_PREFLIGHT(args, time.monotonic() + 300)


@pytest.mark.parametrize("template_index,template", [(3, "File not found {key}"), (4, "File not found:{key}")], ids=["space", "colon"])
def test_new_exact_forms_complete_full_synthetic_protocol_and_admission(monkeypatch, template_index, template):
    f = fixture(monkeypatch)
    for phase in ("initial", "recheck"):
        for index in range(6):
            f.overrides[(phase, index)] = {"success": False, "errors": [template.format(key=f.rows[index][0])]}
    result = execute()
    assert result["complete"] is True and result["attempted_request_count"] == 24
    assert [(phase, index) for phase, index, *_ in f.calls] == [("initial", i) for i in range(6)] + [
        (phase, i) for i in range(6) for phase in ("recheck", "put", "verify")]
    assert all(entry["absence_template_index"] == template_index for entry in result["requests"] if entry["object_state"] == "absent")
    assert caller._safe_result(result, d) == result
    d.require_admission(f.directory, f.plan, f.record, result["receipt_sha256"])


@pytest.mark.parametrize("template_index", [3, 4])
@pytest.mark.parametrize("mutation", ["wrong_key", "trailing", "negated", "tab_separator", "newline_separator", "http404"])
def test_new_form_near_matches_never_authorize_any_write(monkeypatch, template_index, mutation):
    f = fixture(monkeypatch)
    text = d.ABSENCE_TEMPLATES[template_index].format(key=f.rows[0][0])
    if mutation == "wrong_key": text = text.replace(f.rows[0][0], "private-prefix/other")
    elif mutation == "trailing": text += "."
    elif mutation == "negated": text = "Not " + text
    elif mutation == "tab_separator": text = "File not found\t" + f.rows[0][0]
    elif mutation == "newline_separator": text = "File not found\n" + f.rows[0][0]
    response = {"success": False, "errors": [text]}
    if mutation == "http404": response = Response(old.API_BASE + "/object/properties", response, 404)
    f.overrides[("initial", 0)] = response
    result = execute()
    assert result["complete"] is False and result["attempted_request_count"] == 1
    assert [(phase, index) for phase, index, *_ in f.calls] == [("initial", 0)]
    assert d.ADMISSION not in f.directory.data
    assert result["failure_code"] == ("http_status" if mutation == "http404" else "absence_unproven")


def test_v4_only_changes_explicit_provenance_grammar_and_versioned_bindings():
    original = (d.ROOT / "scripts/arv2_newrule_storage_recovery_v3.py").read_text()
    transformed = original.replace("len(ADDITIONS) == 6", "len(ADDITIONS) == 8")
    transformed = transformed.replace("inventory_sha256=INVENTORY_SHA256, historical_d13_report_sha256_not_reread=D13_REPORT_SHA256,",
        "inventory_sha256=INVENTORY_SHA256, historical_d13_report_sha256_not_reread=D13_REPORT_SHA256,\n        historical_d14_report_sha256_not_reread=D14_REPORT_SHA256,")
    def functions(source):
        return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}
    assert functions(transformed) == functions(d.SOURCE.read_text())
    old_caller = (d.ROOT / "scripts/run_arv2_newrule_storage_recovery_v3.py").read_text()
    transformed_caller = old_caller.replace("storage_recovery_v3", "storage_recovery_v4").replace(
        '0 <= entry["absence_template_index"] < 3', '0 <= entry["absence_template_index"] < len(recovery.ABSENCE_TEMPLATES)')
    assert functions(transformed_caller) == functions(caller.SOURCE.read_text())
    assert d.ABSENCE_TEMPLATES == ("File not found: {key}", "File not found: '{key}'", 'File not found: "{key}"',
        "File not found {key}", "File not found:{key}")
    assert d.MAX_REQUESTS == 24 and d.MAX_SETS == 6 and d.DEADLINE_SECONDS == 300 and d.REQUEST_SECONDS == 30
    assert d.PROFILE["historical_d14_head_not_reread"] == "14d8c9a90eb0c477f7b1053465cece2001662e37"
    assert d.PROFILE["historical_d14_report_sha256_not_reread"] == "8435a8605495e91341eaa7f283faa54205f327588332419d114fd73f9579c7b6"
    assert d.PROFILE["historical_d14_report_bytes_not_reread"] == 1801
