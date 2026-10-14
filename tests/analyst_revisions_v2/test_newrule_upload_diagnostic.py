"""Synthetic markers only: no private package, credentials or QC contacts."""
import builtins
import copy
import hashlib
import json
import sys
import time

import pytest

from tests.analyst_revisions_v2._dispatch_fence_closure import assert_lane_closure_excludes_dispatch_fence

from scripts import diagnose_arv2_newrule_upload as d
from research.analyst_revisions_v2_qc import newrule_comparison_submission as s

HEAD, SHA = "a" * 40, "b" * 64


import socket  # noqa: E402
import urllib.request  # noqa: E402

REAL_CREATE_CONNECTION, REAL_PRODUCTION_CLIENT = socket.create_connection, s.coverage.production_client


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    # Section 301 (ARV2R301-002): record every boundary hit, so a guard swallowed
    # by a broad product handler still fails at teardown (the 298.2 class).
    violations = []

    def forbidden(*_args, **_kwargs):
        violations.append("operational_boundary")
        pytest.fail("operational access forbidden")
    for name in ("run", "_operation"):
        monkeypatch.setattr(d.frozen, name, forbidden)
    for name in ("_client", "prepare_family", "discover_organization", "upload_inputs",
                 "capacity_once", "begin_attempt", "poll_compile_once", "launch_compiled",
                 "poll_status_once", "read_result_once", "summarize_family", "load_family", "_session"):
        monkeypatch.setattr(s, name, forbidden)
    monkeypatch.setattr(d.frozen.prepared_input.october, "load_october_order_input_package", forbidden)
    monkeypatch.setattr(s.QuantConnectClient, "__init__", forbidden)
    monkeypatch.setattr(s.coverage, "production_client", forbidden)
    monkeypatch.setattr(s.coverage, "_bounded_transport", forbidden)
    for owner, names in ((socket, ("create_connection", "getaddrinfo")),
                         (socket.socket, ("connect", "connect_ex")),
                         (urllib.request.OpenerDirector, ("open",))):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    yield violations
    assert violations == [], "swallowed operational boundary"


def test_isolation_records_swallowed_boundary_calls(isolation):
    # Fails if the fixture stops recording (the former version yielded nothing).
    assert s.coverage.production_client is not REAL_PRODUCTION_CLIENT
    assert socket.create_connection is not REAL_CREATE_CONNECTION
    try:
        s._client()
    except BaseException:
        pass  # a broad handler swallowing the guard, as product code might
    assert isolation == ["operational_boundary"]
    isolation.clear()


class MemoryDirectory:
    def __init__(self, data):
        self.data = copy.deepcopy(data)
        self.reads, self.writes = [], []
    def names(self):
        return tuple(self.data)
    def read(self, name):
        assert name not in {"organization.json", "upload-valid.json", "old-output.json"}
        self.reads.append(name)
        return copy.deepcopy(self.data[name])
    def write(self, name, value):
        assert name in {d.CLAIM, d.REPORT}
        if name in self.data:
            raise FileExistsError()
        self.writes.append(name)
        self.data[name] = copy.deepcopy(value)
    def __exit__(self, *_):
        pass


def fixtures(n=3, completed=0, pending=False, valid=False):
    inventory = [["PRIVATE-OBJECT-KEY-" + str(i), SHA, 10, i == n-1] for i in range(n)]
    record = {"upload_inventory": inventory,
        "upload_inventory_sha256": hashlib.sha256(d.helpers.canonical_json_bytes(inventory)).hexdigest()}
    data = {"upload-claim.json": {"family_sha256": d.FAMILY_SHA256},
            "organization.json": {"private": "PRIVATE-ORG-MUST-NOT-READ"}}
    slots = [(None, "authenticate", "upload-authenticate")]
    for index in range(n):
        slots.extend(((index, "object/set", f"upload-{index:03d}"),
                      (index, "object/properties", f"upload-{index:03d}-properties")))
    for position, (_, endpoint, stem) in enumerate(slots):
        if position < completed or position == completed and pending:
            data[stem + "-intent.json"] = {"family_sha256": d.FAMILY_SHA256,
                "endpoint": endpoint, "request_sha256": SHA, "epoch": 100 + position*2}
        if position < completed:
            data[stem + "-observed.json"] = {"family_sha256": d.FAMILY_SHA256,
                "response_sha256": SHA, "epoch": 101 + position*2}
    if valid:
        data["upload-valid.json"] = {"private": "MUST-NOT-READ"}
    return MemoryDirectory(data), record, slots


@pytest.mark.parametrize("completed,pending", [(0,False), (0,True), (1,False), (1,True),
    (2,False), (2,True), (3,True), (6,True), (7,False)])
def test_exact_sequential_prefix_and_no_private_values(completed, pending):
    directory, record, slots = fixtures(completed=completed, pending=pending)
    result = d._census(directory, record, time.monotonic()+10)
    assert result["inventory_count"] == 3
    assert result["retained_intent_count"] == completed + int(pending)
    assert result["observed_success_count"] == completed
    assert result["missing_observation_count"] == int(pending)
    last = completed if pending else completed-1
    assert result["last_retained_request_intent"] == (
        None if last < 0 else dict(endpoint=slots[last][1], index=slots[last][0]))
    assert result["actual_last_dispatch_unknown"] and result["request_count_unknown"]
    assert not result["successful_response_is_properties_validation"]
    assert not result["original_upload_valid_marker_content_read"]
    text = json.dumps(result)
    assert "PRIVATE" not in text and SHA not in text
    assert len(directory.reads) == 1 + completed*2 + int(pending)


def test_observed_sets_and_properties_census_exact():
    directory, record, _ = fixtures(completed=4, pending=True)
    result = d._census(directory, record, time.monotonic()+10)
    assert result["authenticate"] == dict(intent_present=True, observed_success_present=True, missing_observation=False)
    assert result["endpoint_census"]["object/set"] == dict(
        intent_indices=[0,1], observed_success_indices=[0,1], missing_observation_indices=[])
    assert result["endpoint_census"]["object/properties"] == dict(
        intent_indices=[0,1], observed_success_indices=[0], missing_observation_indices=[1])


@pytest.mark.parametrize("valid", [False, True])
def test_valid_presence_is_not_content_or_acceptance(valid):
    directory, record, _ = fixtures(completed=7, valid=valid)
    result = d._census(directory, record, time.monotonic()+10)
    assert result["original_upload_valid_marker_present"] is valid
    assert "upload-valid.json" not in directory.reads


@pytest.mark.parametrize("mutation", ["family", "endpoint", "hash", "bool_epoch", "negative_epoch",
    "large_epoch", "reversed_epoch", "extra_field", "missing_field", "orphan_observed",
    "gap", "unexpected_index", "unknown_upload", "early_valid", "claim_extra", "claim_family",
    "inventory_hash", "inventory_empty", "inventory_overflow", "inventory_type"])
def test_hostile_or_inconsistent_markers_refuse(mutation):
    directory, record, _ = fixtures(completed=1, pending=True)
    intent = directory.data["upload-000-intent.json"]
    if mutation == "family": intent["family_sha256"] = "c"*64
    elif mutation == "endpoint": intent["endpoint"] = "object/properties"
    elif mutation == "hash": intent["request_sha256"] = "PRIVATE"
    elif mutation == "bool_epoch": intent["epoch"] = True
    elif mutation == "negative_epoch": intent["epoch"] = -1
    elif mutation == "large_epoch": intent["epoch"] = 10**11
    elif mutation == "reversed_epoch": intent["epoch"] = 1
    elif mutation == "extra_field": intent["private"] = "do-not-output"
    elif mutation == "missing_field": del intent["epoch"]
    elif mutation == "orphan_observed": del directory.data["upload-authenticate-intent.json"]
    elif mutation == "gap": del directory.data["upload-authenticate-observed.json"]
    elif mutation == "unexpected_index": directory.data["upload-003-intent.json"] = intent
    elif mutation == "unknown_upload": directory.data["upload-private.json"] = {}
    elif mutation == "early_valid": directory.data["upload-valid.json"] = {}
    elif mutation == "claim_extra": directory.data["upload-claim.json"]["private"] = 1
    elif mutation == "claim_family": directory.data["upload-claim.json"]["family_sha256"] = SHA
    elif mutation == "inventory_hash": record["upload_inventory_sha256"] = SHA
    elif mutation == "inventory_empty": record["upload_inventory"] = []
    elif mutation == "inventory_overflow": record["upload_inventory"] *= 43
    elif mutation == "inventory_type": record["upload_inventory"] = tuple(record["upload_inventory"])
    with pytest.raises(d.DiagnosticRefusal):
        d._census(directory, record, time.monotonic()+10)


def test_full_128_inventory_is_bounded():
    directory, record, _ = fixtures(n=128, completed=257, valid=True)
    result = d._census(directory, record, time.monotonic()+10)
    assert result["observed_success_count"] == 257
    report = d._report(HEAD,SHA,"synthetic","marker_census",True,result,None)
    assert len(d.helpers.canonical_json_bytes(report)) < d.MAX_OUTPUT_BYTES - 512


def test_changed_census_names_refuse():
    directory, record, _ = fixtures()
    original, calls = directory.names, []
    def names():
        calls.append(1)
        return original() + (("new-concurrent.json",) if len(calls) > 1 else ())
    directory.names = names
    with pytest.raises(d.DiagnosticRefusal):
        d._census(directory, record, time.monotonic()+10)


def test_deadline_refuses_census():
    directory, record, _ = fixtures()
    with pytest.raises(d.helpers.Deadline):
        d._census(directory, record, time.monotonic()-1)


def run_fixtures(monkeypatch):
    directory, record, _ = fixtures(completed=1, pending=True)
    monkeypatch.setattr(d, "_preflight", lambda *_: None)
    monkeypatch.setattr(s, "_Directory", lambda: directory)
    loaded = []
    def load(actual, *_):
        assert actual is directory
        assert d.CLAIM in directory.data and d.REPORT not in directory.data
        loaded.append(True)
        return record
    monkeypatch.setattr(d, "_family_binding", load)
    return directory, record, loaded


def test_claim_precedes_authentication_and_report_is_pinned(monkeypatch, capsys):
    directory, _, loaded = run_fixtures(monkeypatch)
    original = copy.deepcopy(directory.data)
    assert d.run(HEAD, SHA) == 0 and loaded == [True]
    envelope = json.loads(capsys.readouterr().out)
    report = envelope["report"]
    assert directory.writes == [d.CLAIM, d.REPORT]
    assert all(directory.data[key] == value for key, value in original.items())
    assert report["terminal"] == "marker_census_completed" and report["attempt_consumed"] is True
    for key in ("original_upload_accepted", "changes_original_exit", "qc_contact_authorized",
                "point_in_time_proven", "formal_forward_ready", "paper_or_live_ready"):
        assert report[key] is False
    raw = d.helpers.canonical_json_bytes(directory.data[d.REPORT])
    assert envelope["report_bytes"] == len(raw)
    assert envelope["report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert envelope["report_published"] is True
    assert "PRIVATE" not in json.dumps(envelope)
    assert_lane_closure_excludes_dispatch_fence()


def test_repeated_diagnostic_refuses_before_source_read_or_report_overwrite(monkeypatch, capsys):
    directory, _, loaded = run_fixtures(monkeypatch)
    assert d.run(HEAD, SHA) == 0
    capsys.readouterr()
    retained = copy.deepcopy(directory.data)
    assert d.run(HEAD, SHA) == 2
    report = json.loads(capsys.readouterr().out)["report"]
    assert report["attempt_consumed"] is None and report["failure_code"] == "claim_or_report_exists"
    assert loaded == [True] and directory.data == retained


@pytest.mark.parametrize("stage", ["preflight", "claim", "family", "census", "report", "report_readback"])
def test_failures_never_accept_original_or_emit_raw_exception(monkeypatch, capsys, stage):
    directory, _, loaded = run_fixtures(monkeypatch)
    def fail(*_): raise RuntimeError("PRIVATE-EXCEPTION")
    if stage == "preflight": monkeypatch.setattr(d, "_preflight", fail)
    elif stage == "family": monkeypatch.setattr(d, "_family_binding", fail)
    elif stage == "census": monkeypatch.setattr(d, "_census", fail)
    elif stage in ("claim", "report"):
        original = directory.write
        def write(name,value):
            if name == (d.CLAIM if stage == "claim" else d.REPORT): fail()
            original(name,value)
        directory.write = write
    else:
        original = directory.read
        directory.read = lambda name: fail() if name == d.REPORT else original(name)
    assert d.run(HEAD,SHA) == 2
    output = capsys.readouterr().out
    assert "PRIVATE" not in output and '"original_upload_accepted":false' in output
    if stage in ("preflight", "claim"):
        assert loaded == [] and d.REPORT not in directory.data


def test_deadline_after_census_no_positive_publication(monkeypatch, capsys):
    directory, _, _ = run_fixtures(monkeypatch)
    original = d._census
    clock = time.monotonic
    def census(*args):
        value = original(*args)
        monkeypatch.setattr(time, "monotonic", lambda: clock()+1000)
        return value
    monkeypatch.setattr(d, "_census", census)
    assert d.run(HEAD,SHA) == 2
    assert d.REPORT not in directory.data
    assert "marker_census_completed" not in capsys.readouterr().out


def test_oversized_report_never_publishes(monkeypatch, capsys):
    directory, _, _ = run_fixtures(monkeypatch)
    monkeypatch.setattr(d, "_census", lambda *_: {"oversized": "x"*d.MAX_OUTPUT_BYTES})
    assert d.run(HEAD,SHA) == 2
    assert d.REPORT not in directory.data and "oversized" not in capsys.readouterr().out


def test_stateless_frozen_preflight_exact_source_arguments(monkeypatch):
    seen=[]
    def preflight(args, deadline):
        assert vars(args) == dict(operation="summarize", expected_head=HEAD,
            caller_sha256=d.FROZEN_CALLER_SHA256, candidate=None, attempt=None,
            family_sha256=d.FAMILY_SHA256, prior_failure_sha256=None, justification_sha256=None)
        seen.append(True)
    monkeypatch.setattr(d.frozen, "_preflight", preflight)
    monkeypatch.setattr(d.helpers, "_source_digest", lambda path: SHA if path == d.SOURCE else pytest.fail("unknown source"))
    d._preflight(HEAD,SHA,time.monotonic()+10)
    assert seen == [True]


def test_self_source_pin_refuses(monkeypatch):
    monkeypatch.setattr(d.frozen, "_preflight", lambda *_: None)
    monkeypatch.setattr(d.helpers, "_source_digest", lambda _: "c"*64)
    with pytest.raises(d.DiagnosticRefusal): d._preflight(HEAD,SHA,time.monotonic()+10)


def pinned_family(monkeypatch):
    record = {"schema": s.SCHEMA, "submission_profile_sha256": s.PROFILE_SHA256,
        "package_sha256": d.frozen.PACKAGE_SHA256, "lineage_sha256": d.frozen.LINEAGE_SHA256,
        "formal_forward_ready": False, "paper_or_live_ready": False,
        "upload_inventory": [["PRIVATE-DATA-KEY", SHA, s.UPLOAD_BYTES-s.ACTIVATION_BYTES,False],
            [s.ACTIVATION_KEY,s.ACTIVATION_SHA256,s.ACTIVATION_BYTES,True]]}
    digest = hashlib.sha256(d.helpers.canonical_json_bytes(record)).hexdigest()
    monkeypatch.setattr(d,"FAMILY_SHA256",digest)
    directory = MemoryDirectory({"family.json": record,
        "preparation-claim.json": {"schema":s.SCHEMA,"family_sha256":digest}})
    return directory,record


def test_exact_family_binding_only_two_fixed_reads(monkeypatch):
    directory,record = pinned_family(monkeypatch)
    assert d._family_binding(directory,s,time.monotonic()+10) == record
    assert directory.reads == ["family.json","preparation-claim.json"]


def test_external_family_pin_before_field_access(monkeypatch):
    directory,_ = pinned_family(monkeypatch)
    directory.data["family.json"]["upload_inventory"] = "PRIVATE-MISMATCH"
    with pytest.raises(d.DiagnosticRefusal):
        d._family_binding(directory,s,time.monotonic()+10)
    assert directory.reads == ["family.json"]


@pytest.mark.parametrize("mutation", ["preparation","package","lineage","schema","profile",
    "formal","paper","row_type","row_length","key","duplicate_key","digest","size_bool",
    "size_zero","size_large","activation_bool","activation_order","activation_pin","total_bytes"])
def test_pinned_family_still_needs_exact_finite_descriptor_types(monkeypatch,mutation):
    directory,record = pinned_family(monkeypatch)
    record = directory.data["family.json"]
    row=record["upload_inventory"][0]
    if mutation == "preparation": directory.data["preparation-claim.json"]["extra"] = True
    elif mutation in ("package","lineage","schema","profile"):
        record[{"package":"package_sha256","lineage":"lineage_sha256","schema":"schema",
                "profile":"submission_profile_sha256"}[mutation]] = "private"
    elif mutation == "formal": record["formal_forward_ready"] = 0
    elif mutation == "paper": record["paper_or_live_ready"] = 0
    elif mutation == "row_type": record["upload_inventory"][0] = tuple(row)
    elif mutation == "row_length": row.append(1)
    elif mutation == "key": row[0] = "x"*513
    elif mutation == "duplicate_key": row[0] = s.ACTIVATION_KEY
    elif mutation == "digest": row[1] = "x"
    elif mutation == "size_bool": row[2] = True
    elif mutation == "size_zero": row[2] = 0
    elif mutation == "size_large": row[2] = s.compact.MAX_UPLOAD_OBJECT_BYTES+1
    elif mutation == "activation_bool": row[3] = 0
    elif mutation == "activation_order": row[3] = True
    elif mutation == "activation_pin": record["upload_inventory"][-1][1] = SHA
    elif mutation == "total_bytes": row[2] -= 1
    digest = hashlib.sha256(d.helpers.canonical_json_bytes(record)).hexdigest()
    monkeypatch.setattr(d,"FAMILY_SHA256",digest)
    directory.data["preparation-claim.json"]["family_sha256"] = digest
    with pytest.raises(d.DiagnosticRefusal):
        d._family_binding(directory,s,time.monotonic()+10)


def test_unknown_opaque_exception_never_rendered_or_hashed():
    class Meta(type):
        def __hash__(self): pytest.fail("exception type hashed")
    class Error(Exception, metaclass=Meta): pass
    class Opaque:
        def __repr__(self): pytest.fail("repr")
        def __str__(self): pytest.fail("str")
    assert d._failure(Error(Opaque())) == "unknown_exception"


@pytest.mark.parametrize("exc,label", [(d.DiagnosticRefusal(),"diagnostic_refused"),
    (d.frozen.OperationRefusal(),"preflight_refused"), (d.helpers.Deadline(),"deadline"),
    (FileExistsError(),"claim_or_report_exists"), (FileNotFoundError(),"file_missing"),
    (PermissionError(),"permission_error"), (OSError(),"os_error"),
    (KeyboardInterrupt(),"cancelled"), (SystemExit(),"cancelled"),
    (ValueError(),"value_error"), (TypeError(),"type_error"),
    (KeyError(),"key_error"), (MemoryError(),"memory_error")])
def test_finite_exact_failure_labels(exc,label):
    assert d._failure(exc) == label


def test_no_failure_path_module_import():
    assert d._failure(RuntimeError("private")) == "unknown_exception"
    assert d._failure(s.NewruleSubmissionError("control_changed"),s) == "control_changed"
    assert d._failure(s.NewruleSubmissionError("PRIVATE"),s) == "operation_refused"


def test_source_refusal_never_imports_claims_or_loads(monkeypatch, capsys):
    def refuse(*_): raise d.DiagnosticRefusal()
    monkeypatch.setattr(d, "_preflight", refuse)
    monkeypatch.setattr(s, "_Directory", lambda: pytest.fail("claim after source refusal"))
    monkeypatch.setattr(d, "_family_binding", lambda *_: pytest.fail("source read after refusal"))
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert name != "research.analyst_revisions_v2_qc", "submission import after refusal"
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    assert d.run(HEAD,SHA) == 2
    report = json.loads(capsys.readouterr().out)["report"]
    assert report["attempt_consumed"] is False and report["stage"] == "preflight"


@pytest.mark.parametrize("which", ["claim", "report"])
def test_bool_integer_aliases_cannot_pass_new_control_readback(monkeypatch, capsys, which):
    directory, _, _ = run_fixtures(monkeypatch)
    original = directory.read
    def read(name):
        value = original(name)
        if name == (d.CLAIM if which == "claim" else d.REPORT):
            value["attempt_consumed"] = 1
        return value
    directory.read = read
    assert d.run(HEAD,SHA) == 2
    assert "marker_census_completed" not in capsys.readouterr().out


@pytest.mark.parametrize("raw", [
    b'{"family_sha256":"a","family_sha256":"b"}',
    b'{"epoch":NaN}', b'{"epoch":Infinity}', b'{"epoch":-Infinity}',
    b'{"epoch":1} trailing', b'{ "epoch": 1 }'])
def test_frozen_directory_parser_is_strict_on_retained_control_bytes(raw):
    with pytest.raises(s.NewruleSubmissionError):
        s._parse(raw)


def test_existing_claim_causes_no_private_marker_reads(monkeypatch, capsys):
    directory, _, loaded = run_fixtures(monkeypatch)
    directory.data[d.CLAIM] = {"previous": True}
    assert d.run(HEAD,SHA) == 2
    assert directory.reads == [] and loaded == [] and directory.writes == []
    assert json.loads(capsys.readouterr().out)["report"]["attempt_consumed"] is None
