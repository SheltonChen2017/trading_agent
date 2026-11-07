"""One-shot readonly full-log recovery; synthetic source/custody/transport only."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import html
import inspect
import json
from pathlib import Path
import sys
from urllib.parse import quote

import pytest

from research.target_price_revisions_qc import native_cache_delivery_log_export_20261107 as m

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 7, 20, tzinfo=timezone.utc)
HEAD, ORG, OWNER = "a"*40, "a"*32, 123
TOKEN = 'SYNTH/"LOG\\TOKEN'


def wire(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def report(**changes):
    body = {"schema": "tpr-native-delivery-plain-cache-observations-v1",
        "source_epoch": "TPR-NATIVE-PARENT-DELIVERY-PLAIN-20261107-v1",
        "operation_id": m.PROBE_OPERATION_ID, "root_head": m.NATIVE_SOURCE_HEAD,
        "actual_job_id": m.BACKTEST_ID,
        "delivery": {"not_projected": "unaccepted diagnostic metadata"}}
    body.update(changes)
    return body


def logs(body=None, *, before="2021-02-08 ordinary diagnostic line\n", after="\n2021-02-12 done\n"):
    value = report() if body is None else body
    return before.encode("utf-8") + m.TAG.encode("ascii") + wire(value) + after.encode("utf-8")


def project(raw):
    return m.validate_export(raw, credential=TOKEN)


@pytest.fixture(autouse=True)
def deny_real_effects(monkeypatch):
    def deny(*_, **__):
        raise AssertionError("real credential/network/subprocess forbidden")
    monkeypatch.setattr(m.api.ops, "credential", deny)
    monkeypatch.setattr(m.projects.http.client, "HTTPSConnection", deny)
    monkeypatch.setattr(m.api.subprocess, "run", deny)
    if sys.platform != "darwin":
        def custody(*_, **__):
            pytest.skip("POSIX Mac custody fixture is not Windows custody proof")
        monkeypatch.setattr(m.api.ops, "_custody", custody)


def test_exact_export_metadata_never_projects_counts_or_promotes_completed_job():
    raw = logs()
    result = project(raw)
    serialized = wire(result)
    assert result["entire_wire_validated"] is True
    assert result["credential_echo_refused_before_retention"] is True
    assert result["original_wire_bytes"] == len(raw)
    assert result["original_wire_sha256"] == sha(raw)
    assert b"not_projected" not in serialized and b"unaccepted diagnostic metadata" not in serialized
    assert "delivery" not in result and "report" not in result
    for key in ("financial_acceptance", "delivery_counts_accepted", "native_origin_independently_attested",
            "import_origin_attested", "source_import_atomicity_attested", "full_log_completeness_attested"):
        assert result[key] is False


@pytest.mark.parametrize("field,value", [
    ("schema", "old"), ("source_epoch", "old"), ("operation_id", "wrong"),
    ("root_head", "b"*40), ("actual_job_id", "b"*32),
    ("root_head", True), ("actual_job_id", 1),
])
def test_tagged_header_has_exact_immutable_native_job_and_source_binding(field, value):
    with pytest.raises(m.ExportRefusal):
        project(logs(report(**{field: value})))


@pytest.mark.parametrize("field", ["schema", "source_epoch", "operation_id", "root_head", "actual_job_id"])
def test_required_native_report_header_is_not_invented_or_optional(field):
    body = report()
    body.pop(field)
    with pytest.raises(m.ExportRefusal):
        project(logs(body))


@pytest.mark.parametrize("field,value", [
    ("project_id", 38609836), ("project_id", True), ("config_sha256", "f"*64),
    ("financial_acceptance", True), ("coverage_accepted", 0), ("backtesting_ready", True),
])
def test_optional_provenance_and_acceptance_fields_cannot_contradict_fixed_recovery(field, value):
    with pytest.raises(m.ExportRefusal):
        project(logs(report(**{field: value})))


@pytest.mark.parametrize("raw", [
    b"", b"\xef\xbb\xbfplain", b"bad\xff", b"plain\x00text",
    b'{"success":false,"errors":["private error"]}', b'{"success":true,"url":"https://example.invalid/log"}',
    b"<!doctype html><html>login</html>", b"https://example.invalid/log",
    b"no diagnostic tag\n",
])
def test_nonplaintext_error_url_and_missing_tag_are_refused_without_error_echo(raw):
    with pytest.raises(m.ExportRefusal) as caught:
        project(raw)
    assert "private error" not in str(caught.value)


@pytest.mark.parametrize("tail", [
    b"", b"x", b" trailing", b"}",
])
def test_truncated_or_trailing_tag_json_is_not_repaired(tail):
    raw = m.TAG.encode() + wire(report())[:-3] + tail
    with pytest.raises(m.ExportRefusal):
        project(raw)


def test_duplicate_tag_and_duplicate_decoded_json_keys_are_refused():
    tag = m.TAG.encode()
    valid = tag + wire(report())
    for raw in (valid+b"\n"+valid, valid.replace(b'"root_head":', b'"root_head":"x","root_head":'),
            valid.replace(b'"root_head":', b'"root\\u005fhead":"x","root_head":')):
        with pytest.raises(m.ExportRefusal):
            project(raw)


@pytest.mark.parametrize("replacement", [
    b"NaN", b"Infinity", b"-Infinity", b"[1,]", b'{"x":0,"x":1}', b'{"x":0,"\\u0078":1}',
    b'"bad\\q"', b'"bad\x01"', b"01",
])
def test_entire_tag_discarded_subtree_is_strict_json(replacement):
    raw = m.TAG.encode()+wire(report(extra="SENTINEL"))
    raw = raw.replace(b'"SENTINEL"', replacement)
    with pytest.raises(m.ExportRefusal):
        project(raw)


def test_tag_byte_depth_and_node_caps_are_independent_and_load_bearing():
    assert m.MAX_BYTES == 262144 and m.SECONDS == 20 and m.PHASE_SECONDS == 240
    assert m.MAX_TAG_BYTES == 16384 and m.MAX_DEPTH == 16 and m.MAX_NODES == 4096
    with pytest.raises(m.ExportRefusal):
        project(b"x"*(m.MAX_BYTES+1))
    with pytest.raises(m.ExportRefusal):
        project(logs(report(extra="x"*16384)))
    raw = m.TAG.encode()+wire(report(extra="SENTINEL"))
    assert project(raw.replace(b'"SENTINEL"', b"["*15+b"0"+b"]"*15))["entire_wire_validated"]
    with pytest.raises(m.ExportRefusal):
        project(raw.replace(b'"SENTINEL"', b"["*16+b"0"+b"]"*16))
    assert project(logs(report(extra=[0]*4000)))["entire_wire_validated"]
    with pytest.raises(m.ExportRefusal):
        project(logs(report(extra=[0]*4097)))


def test_exact_whole_wire_byte_bound_can_capture_a_complete_safe_tag():
    tagged = logs(before="", after="")
    raw = b"x"*(m.MAX_BYTES-len(tagged)-1)+b"\n"+tagged
    assert len(raw) == m.MAX_BYTES
    assert project(raw)["original_wire_bytes"] == m.MAX_BYTES


@pytest.mark.parametrize("credential", [None, b"bytes", "", "x"*257, "line\nfeed", "é"])
def test_credential_context_must_be_bounded_printable_ascii(credential):
    with pytest.raises(m.ExportRefusal):
        m.validate_export(logs(), credential=credential)


def secret_variants():
    simple = json.dumps(TOKEN)[1:-1].replace("/", "\\/")
    unicode = "".join("\\u%04x" % ord(c) for c in TOKEN)
    hexcoded = "".join("\\x%02x" % ord(c) for c in TOKEN)
    percent = "".join("%%%02X" % ord(c) for c in TOKEN)
    entities = "".join("&#x%x;" % ord(c) for c in TOKEN)
    mixed = "".join((c, "\\u%04x"%ord(c), "%%%02X"%ord(c), "&#x%x;"%ord(c))[i%4]
        if c not in {'"', "\\", "/"} else json.dumps(c)[1:-1].replace("/", "\\/")
        for i, c in enumerate(TOKEN))
    return [TOKEN, simple, unicode, hexcoded, percent, entities, mixed,
        quote(entities, safe=""), html.escape(unicode), quote(simple, safe="")]


@pytest.mark.parametrize("encoded", secret_variants(), ids=range(10))
@pytest.mark.parametrize("location", ["before", "after", "discarded", "key", "control"])
def test_entire_text_secret_scan_includes_every_line_key_and_control_envelope(encoded, location):
    if location == "before": raw = logs(before=encoded+"\n")
    elif location == "after": raw = logs(after="\n"+encoded)
    elif location == "control": raw = ('{"success":false,"error":"'+encoded+'"}').encode()
    elif location == "key": raw = logs(report(**{encoded: "discarded"}))
    else: raw = logs(report(extra=encoded))
    with pytest.raises(m.ExportRefusal):
        project(raw)


def source_hashes():
    return {name: sha((ROOT/name).read_bytes()) for name in m.REQUIRED_SOURCES}


def registry(sources):
    return {"schema": "tpr-cmp28-five-project-bindings-v1", "round_id": m.projects.ROUND_ID,
        "owner_instruction_sha256": "ea2dd7037a0f33ab78771a2f6deb3016da34b164ab04f5b2c69f30c4ae31157f",
        "git_head": "b"*40, "adapter_source_sha256": sources[m.api.PROJECTS_MODULE],
        "organization_id": ORG, "owner_id": OWNER, "baseline_receipt_sha256": "d"*64,
        "privacy_basis": "documented_private_default_and_observed_collaborators",
        "explicit_privacy_flag_observed": False, "independent_native_origin_attested": False,
        "projects": {key: {"project_id": project, "name": m.projects.RESERVED_NAMES[key],
            "organization_id": ORG, "owner_id": OWNER, "language": "Py",
            "create_receipt_sha256": sha(("create-"+key).encode()),
            "read_receipt_sha256": sha(("read-"+key).encode()),
            "collaboration_receipt_sha256": sha(("collaborators-"+key).encode()),
            "collaborator_count": 1, "nonowner_collaborator_count": 0,
            "collaborators_sha256": "9"*64} for key, project in m.api.REGISTERED_PROJECTS.items()}}


def arguments(**changes):
    sources = source_hashes()
    raw = wire(registry(sources))
    args = dict(project_bindings_raw=raw, expected_project_bindings_sha256=sha(raw),
        operation_id="TPR-CMP29-API-LOGEXPORT-SYNTHETIC-001", git_head=HEAD,
        source_hashes=sources, latest_owner_instruction_sha256=m.OWNER_SHA256,
        created_utc=(NOW-timedelta(seconds=1)).isoformat(),
        expires_utc=(NOW+timedelta(seconds=239)).isoformat())
    args.update(changes)
    return args


def plan(**changes):
    return m._prepare_fixture(**arguments(**changes))


def run(tmp_path, *, raw=None, status=200, credential=TOKEN, transport=None, clock=lambda: NOW,
        guard=lambda _: None, monotonic=lambda: 0.0):
    calls = []
    def native(endpoint, payload, seconds, maximum, expected_owner):
        calls.append((endpoint, json.loads(payload), seconds, maximum, expected_owner))
        return logs() if raw is None else raw, status, credential, OWNER
    result = m._execute_fixture(plan(), tmp_path/"native",
        transport=native if transport is None else transport, clock=clock, guard=guard, monotonic=monotonic)
    return result, calls


def test_closed_plan_pins_existing_native_job_provenance_distinct_from_current_reader_head():
    args = arguments()
    prepared = m._prepare_fixture(**args)
    assert prepared["git_head"] == HEAD != prepared["native_source_head"] == m.NATIVE_SOURCE_HEAD
    assert m.NATIVE_SOURCE_HEAD == "e805d413bcbc00f1221275d8db28a1dc3cf8a89a"
    assert m.PROJECT_ID == 38609822 and m.BACKTEST_ID == "fb506cb363a915439998cf53ce419560"
    assert m.CONFIG_SHA256 == "88517aa2505f74601ff8190de0ba6e294c3719f12ac542334248b453cb01fad4"
    assert m.INVENTORY_SHA256 == "d309d29377b8d68c6841d2e56d0e8a77be90a0ab0bdf2abddb78cbec125b6826"
    request = prepared["request"]
    assert request == {"id": "logs", "endpoint": "backtests/export/logs",
        "payload": {"projectId": m.PROJECT_ID, "backtestId": m.BACKTEST_ID},
        "payload_sha256": sha(m.api._canonical({"projectId": m.PROJECT_ID, "backtestId": m.BACKTEST_ID})),
        "seconds": 20, "max_response_bytes": 262144}
    args["source_hashes"][m.MODULE] = "f"*64
    assert prepared["source_hashes"][m.MODULE] != "f"*64
    assert set(inspect.signature(m.prepare_plan).parameters) == {
        "project_bindings_raw", "expected_project_bindings_sha256", "operation_id", "git_head",
        "source_hashes", "latest_owner_instruction_sha256", "created_utc", "expires_utc"}
    assert all(sha((ROOT/name).read_bytes()) == digest for name, digest in m.PINS.items())


def test_fixture_registry_cannot_be_promoted_to_production_and_closure_is_exact():
    with pytest.raises(m.ExportRefusal):
        m.prepare_plan(**arguments())
    args = arguments();args["source_hashes"].pop(m.MODULE)
    with pytest.raises(m.ExportRefusal):
        m._prepare_fixture(**args)
    args = arguments();args["source_hashes"]["research/target_price_revisions_qc/unknown.py"] = "f"*64
    with pytest.raises(m.ExportRefusal):
        m._prepare_fixture(**args)


@pytest.mark.parametrize("changes", [
    {"operation_id": "TPR-CMP29-API-CACHE-OTHER"},
    {"git_head": "A"*40}, {"latest_owner_instruction_sha256": "f"*64},
    {"created_utc": "2026-11-07T20:00:00"},
    {"expires_utc": (NOW+timedelta(seconds=241)).isoformat()},
    {"expires_utc": (NOW-timedelta(seconds=2)).isoformat()},
])
def test_plan_lineage_authority_and_clock_are_closed(changes):
    with pytest.raises(m.ExportRefusal):
        plan(**changes)


@pytest.mark.parametrize("location", ["endpoint", "payload", "bound_source", "source_hashes", "extra"])
def test_mutated_or_extended_plan_cannot_select_another_request(tmp_path, location):
    prepared = plan()
    if location == "endpoint": prepared["request"]["endpoint"] = "backtests/read"
    elif location == "payload": prepared["request"]["payload"]["backtestId"] = "b"*32
    elif location == "bound_source": prepared["native_source_head"] = HEAD
    elif location == "source_hashes": prepared["source_hashes"][m.api.MODULE] = "f"*64
    else: prepared["parser"] = "unreviewed"
    calls = []
    with pytest.raises(m.ExportRefusal):
        m._execute_fixture(prepared, tmp_path/"native", transport=lambda *args: calls.append(args), clock=lambda: NOW)
    assert calls == []


def test_one_native_export_is_claimed_before_credentials_transport_and_retained_privately(tmp_path):
    prepared = plan()
    calls = []
    root = tmp_path/"native"
    def native(endpoint, payload, seconds, maximum, expected_owner):
        assert len(list(root.glob("*.operation.spent.json"))) == 1
        assert len(list(root.glob("*.request.spent.json"))) == 1
        assert not list(root.glob("*.response.raw"))
        calls.append((endpoint, json.loads(payload), seconds, maximum, expected_owner))
        return logs(), 200, TOKEN, OWNER
    result = m._execute_fixture(prepared, root, transport=native, clock=lambda: NOW)
    assert result["status"] == "completed"
    assert calls == [("backtests/export/logs", {"projectId": m.PROJECT_ID, "backtestId": m.BACKTEST_ID},
        20, 262144, OWNER)]
    assert result["receipt_published"] is result["lock_cleanup_complete"] is True
    assert (root/result["raw_response"]["name"]).read_bytes() == logs()
    assert result["metadata"]["tagged_report_binding_verified"] is True
    assert result["actual_new_backtests"] == 0
    assert result["financial_outcome_looks"] == 0
    assert TOKEN.encode() not in wire(result)


@pytest.mark.parametrize("encoded", secret_variants(), ids=range(10))
def test_echo_refusal_precedes_any_raw_retention_even_in_untagged_line(tmp_path, encoded):
    result, calls = run(tmp_path, raw=logs(before=encoded+"\n"))
    assert result["status"] == "failed_or_uncertain" and len(calls) == 1
    assert result["raw_response"] is result["metadata"] is None
    assert not list((tmp_path/"native").glob("*.response.raw"))
    assert TOKEN.encode() not in wire(result)


@pytest.mark.parametrize("raw,status", [
    (b'{"success":false,"errors":["private failure"]}', 200),
    (b"<html>login</html>", 200), (b"https://example.invalid/log", 200),
    (b"no tag", 200), (m.TAG.encode()+wire(report())[:-1], 200), (logs(), 503),
])
def test_safe_failed_wire_is_retained_but_does_not_admit_metadata(tmp_path, raw, status):
    result, calls = run(tmp_path, raw=raw, status=status)
    assert result["status"] == "failed_or_uncertain" and len(calls) == 1
    assert result["metadata"] is None
    assert result["raw_response"] is not None
    assert (tmp_path/"native"/result["raw_response"]["name"]).read_bytes() == raw


def test_spent_operation_prevents_repeat_even_after_native_uncertainty(tmp_path):
    def uncertain(*_):
        raise TimeoutError(TOKEN)
    first, _ = run(tmp_path, transport=uncertain)
    assert first["status"] == "failed_or_uncertain"
    assert first["request_claim"] is not None
    with pytest.raises(m.ExportRefusal):
        run(tmp_path)
    assert len(list((tmp_path/"native").glob("*.request.spent.json"))) == 1


def test_native_request_owner_mismatch_refuses_without_publishing_unverified_wire(tmp_path):
    result, _ = run(tmp_path, transport=lambda *_: (logs(), 200, TOKEN, OWNER+1))
    assert result["status"] == "failed_or_uncertain" and result["metadata"] is None
    assert result["raw_response"] is None


@pytest.mark.parametrize("change", ["deadline", "source"])
def test_fresh_guard_and_deadline_after_request_claim_prevent_native_effect(tmp_path, monkeypatch, change):
    changed = [False]
    clock = [NOW]
    original = m.api._publish
    def publish(root, name, raw):
        result = original(root, name, raw)
        if name.endswith(".request.spent.json"):
            changed[0] = True
            if change == "deadline": clock[0] = NOW+timedelta(seconds=300)
        return result
    def guard(_):
        if changed[0] and change == "source":
            raise m.ExportRefusal("synthetic source refusal")
    monkeypatch.setattr(m.api, "_publish", publish)
    result, calls = run(tmp_path, clock=lambda: clock[0], guard=guard)
    assert result["status"] == "failed_or_uncertain" and calls == []
    assert result["request_claim"] is not None


def test_monotonic_timeout_never_promotes_late_response(tmp_path):
    tick = [0.0]
    def transport(*_):
        tick[0] = 241.0
        return logs(), 200, TOKEN, OWNER
    result, _ = run(tmp_path, transport=transport, monotonic=lambda: tick[0])
    assert result["status"] == "failed_or_uncertain"
    assert result["metadata"] is None or all(result["metadata"][key] is False for key in m.FALSE_FLAGS)


@pytest.mark.parametrize("fatal", [KeyboardInterrupt, SystemExit])
def test_cancel_and_fatal_publish_body_free_receipts_and_preserve_spent_claims(tmp_path, fatal):
    def transport(*_):
        raise fatal(TOKEN)
    expected = m.ExportCancelled if fatal is KeyboardInterrupt else m.ExportFatal
    with pytest.raises(expected) as caught:
        run(tmp_path, transport=transport)
    result = caught.value.report
    assert result["receipt_published"] and result["lock_cleanup_complete"]
    assert result["request_claim"] is not None
    assert TOKEN not in str(caught.value) and TOKEN.encode() not in wire(result)


def test_result_receipt_failure_is_honest_body_free_and_never_retries(tmp_path, monkeypatch):
    original = m.api._publish
    def publish(root, name, raw):
        if name.endswith(".result.json"): raise OSError(TOKEN)
        return original(root, name, raw)
    monkeypatch.setattr(m.api, "_publish", publish)
    result, calls = run(tmp_path)
    assert len(calls) == 1 and result["status"] == "failed_or_uncertain"
    assert result["receipt_published"] is False
    assert TOKEN.encode() not in wire(result)


@pytest.mark.parametrize("fatal", [KeyboardInterrupt, SystemExit])
def test_preclaim_interruption_never_claims_request_or_published_receipt(tmp_path, monkeypatch, fatal):
    original = m.api._publish
    def publish(root, name, raw):
        if name.endswith(".operation.spent.json"): raise fatal(TOKEN)
        return original(root, name, raw)
    monkeypatch.setattr(m.api, "_publish", publish)
    expected = m.ExportCancelled if fatal is KeyboardInterrupt else m.ExportFatal
    with pytest.raises(expected) as caught:
        run(tmp_path)
    assert caught.value.report["receipt_published"] is False
    assert caught.value.report["operation_claim_published"] is None
    assert not list((tmp_path/"native").glob("*.request.spent.json"))
    assert not list((tmp_path/"native").glob("*.result.json"))


def test_partial_initial_claim_failure_is_preserved_without_effect_lock_or_receipt(tmp_path, monkeypatch):
    original = m.api._publish
    def publish(root, name, raw):
        if name.endswith(".operation.spent.json"):
            (root/name).write_bytes(raw[:17])
            raise OSError(TOKEN)
        return original(root, name, raw)
    monkeypatch.setattr(m.api, "_publish", publish)
    with pytest.raises(m.ExportRefusal) as caught:
        run(tmp_path)
    root = tmp_path/"native"
    partial = list(root.glob("*.operation.spent.json"))
    assert len(partial) == 1 and partial[0].stat().st_size == 17
    assert not list(root.glob("*.request.spent.json"))
    assert not list(root.glob("*.result.json")) and not (root/"comparison-api.lock").exists()
    assert TOKEN not in str(caught.value)


def test_existing_claim_and_receipt_are_never_overwritten_on_replay(tmp_path):
    root = tmp_path/"native"
    root.mkdir(mode=0o700)
    operation = plan()["operation_id"]
    claim, receipt = root/(operation+".operation.spent.json"), root/(operation+".result.json")
    claim.write_bytes(b"retained claim")
    receipt.write_bytes(b"retained receipt")
    with pytest.raises(m.ExportRefusal):
        run(tmp_path)
    assert claim.read_bytes() == b"retained claim" and receipt.read_bytes() == b"retained receipt"


def test_partial_response_publication_remains_spent_without_admitting_wire(tmp_path, monkeypatch):
    original = m.api._publish
    def publish(root, name, raw):
        if name.endswith(".response.raw"):
            (root/name).write_bytes(raw[:17])
            raise OSError(TOKEN)
        return original(root, name, raw)
    monkeypatch.setattr(m.api, "_publish", publish)
    result, calls = run(tmp_path)
    assert len(calls) == 1 and result["status"] == "failed_or_uncertain"
    assert result["raw_response"] is result["metadata"] is None
    partial = list((tmp_path/"native").glob("*.response.raw"))
    assert len(partial) == 1 and partial[0].read_bytes() == logs()[:17]
    with pytest.raises(m.ExportRefusal):
        run(tmp_path)


def test_fixture_cannot_select_production_transport_or_lane_private_root(tmp_path):
    with pytest.raises(m.ExportRefusal):
        m._execute_fixture(plan(), tmp_path/"native", transport=m.projects._native_request, clock=lambda: NOW)
    with pytest.raises(m.ExportRefusal):
        m._execute_fixture(plan(), m.api.LANE/"artifacts"/"fixture", transport=lambda *_: None, clock=lambda: NOW)
    with pytest.raises(m.ExportRefusal):
        m.execute_plan(plan())


def test_shared_lock_contention_never_cancels_or_overwrites_other_controller(tmp_path):
    root = tmp_path/"native"
    root.mkdir(mode=0o700)
    lock = root/"comparison-api.lock"
    lock.write_bytes(b"other owner lock")
    calls = []
    result = m._execute_fixture(plan(), root, transport=lambda *args: calls.append(args), clock=lambda: NOW)
    assert result["status"] == "failed_or_uncertain" and result["request_claim"] is None
    assert calls == [] and lock.read_bytes() == b"other owner lock"


def test_nonregular_operation_claim_is_not_followed_or_replaced(tmp_path):
    prepared = plan()
    root = tmp_path/"native"
    root.mkdir(mode=0o700)
    outside = tmp_path/"outside"
    outside.write_bytes(b"retained owner state")
    claim = root/(prepared["operation_id"]+".operation.spent.json")
    claim.symlink_to(outside)
    calls = []
    try:
        result = m._execute_fixture(prepared, root, transport=lambda *args: calls.append(args), clock=lambda: NOW)
    except m.ExportRefusal:
        pass
    else:
        assert result["status"] == "failed_or_uncertain" and result["request_claim"] is None
    assert calls == [] and outside.read_bytes() == b"retained owner state"


def test_actual_guard_refuses_uncommitted_reader_head_without_running_git(monkeypatch):
    from types import SimpleNamespace
    import subprocess
    prepared = plan()
    commands = []
    def git(command, **_):
        commands.append(command)
        args = command[1:]
        if args == ["rev-parse", "--show-toplevel"]: output = str(m.api.LANE).encode()
        elif args == ["branch", "--show-current"]: output = m.api.BRANCH.encode()
        elif args == ["rev-parse", "HEAD"]: output = prepared["git_head"].encode()
        elif args[0] == "show":
            name = args[1].split(":", 1)[1]
            if name == m.MODULE: raise subprocess.CalledProcessError(128, command)
            output = (ROOT/name).read_bytes()
        else: output = b""
        return SimpleNamespace(stdout=output, returncode=0)
    monkeypatch.setattr(m.api.subprocess, "run", git)
    with pytest.raises((m.ExportRefusal, subprocess.CalledProcessError)):
        m._guard(prepared)
    assert ["git", "show", prepared["git_head"]+":"+m.MODULE] in commands

# Printable credentials may contain literal backslash+n/f/b/r/t. A composed
# decoder can momentarily expose such a credential and then consume it as a
# control escape. Every intermediate decoded form must be checked first.
INTERMEDIATE_TOKENS = (
    r"SYNTH\nTOKEN", r"SYNTH\fTOKEN", r"SYNTH\bTOKEN", r"SYNTH\rTOKEN", r"SYNTH\tTOKEN",
    r'SYNTH\"QUOTE/TOKEN', r"SYNTH\/SLASH/TOKEN", r'SYNTH\n\f\b\"\/COMBINED',
)


def intermediate_echo(token, form):
    encoded = "".join(("\\u%04x"%ord(char), char, "%%%02X"%ord(char),
        "&#x%x;"%ord(char))[index%4] for index, char in enumerate(token))
    if form == "double_json":
        encoded = "".join("\\u%04x"%ord(char) for char in token)
        return json.dumps(json.dumps(encoded))[1:-1]
    return encoded


def echo_wire(encoded, location):
    if location == "before": return logs(before=encoded+"\n")
    if location == "after": return logs(after="\n"+encoded)
    if location == "key": return logs(report(**{encoded: "discarded"}))
    if location == "value": return logs(report(extra=encoded))
    if location == "control_key": return wire({"success": False, encoded: "discarded"})
    return wire({"success": False, "error": encoded})


@pytest.mark.parametrize("token", INTERMEDIATE_TOKENS, ids=range(8))
@pytest.mark.parametrize("form", ["mixed", "double_json"])
@pytest.mark.parametrize("location", ["before", "after", "key", "value", "control_key", "control_value"])
def test_intermediate_literal_backslash_credential_is_checked_before_further_decoding(token, form, location):
    raw = echo_wire(intermediate_echo(token, form), location)
    with pytest.raises(m.ExportRefusal):
        m.validate_export(raw, credential=token)


@pytest.mark.parametrize("token", INTERMEDIATE_TOKENS, ids=range(8))
@pytest.mark.parametrize("location", ["before", "after", "key", "value", "control_key", "control_value"])
def test_intermediate_echo_refusal_precedes_raw_hash_or_publication(tmp_path, monkeypatch, token, location):
    raw = echo_wire(intermediate_echo(token, "double_json"), location)
    hashed, published = [], []
    original_sha, original_publish = m.api._sha, m.api._publish
    def digest(value):
        if value == raw: hashed.append(True)
        return original_sha(value)
    def publish(root, name, value):
        if name.endswith(".response.raw") or value == raw: published.append(name)
        return original_publish(root, name, value)
    monkeypatch.setattr(m.api, "_sha", digest)
    monkeypatch.setattr(m.api, "_publish", publish)
    result, calls = run(tmp_path, raw=raw, credential=token)
    assert len(calls) == 1 and result["status"] == "failed_or_uncertain"
    assert result["raw_response"] is result["metadata"] is None
    assert not hashed and not published
    assert not list((tmp_path/"native").glob("*.response.raw"))
    assert token.encode() not in wire(result)
