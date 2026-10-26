"""Invented metadata/custody/native isolation tests; no actual retained inputs."""
from copy import deepcopy
import errno
import io
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="macOS/POSIX custody support")
LANE = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
sys.path.insert(0, str(LANE / "tests"))
from test_insider_buying_sec_2006q1_original_admission_v1 import supplied, _inputs
from research import insider_buying_sec_2006q1_original_admission_runner as module


def _assess(supplied,inputs=None):
    snapshot,census,_=supplied
    return module.pure.assess_original_admission(snapshot,census,_inputs(supplied) if inputs is None else inputs,
        expected_capture_report_sha256=module.CAPTURE_REPORT_SHA256,fixture_only=True)


def _evidence(body):
    context = {"parsed_snapshot_id":body["parsed_snapshot_id"], "parsed_lineage_sha256":body["parsed_lineage_hash"],
        "census_quarter_sha256":body["census_quarter_sha256"], **module.previous._source_identity_inventory(body["rows"])}
    keys = {"prefix_ordinal", "source_record_ordinal", "accession_number", "request_sha256", "result_sha256",
        "terminal_disposition", "body_sha256", "body_size_bytes", "header_identity_bound"}
    anchors = [{key:row[key] for key in keys} for row in body["parent_ledger"]]
    return {"frozen_original_baseline":{"preparation_context":context,"publication_pins":{
            "assessment.json":{"sha256":body["frozen_baseline_assessment_sha256"]}}},
        "frozen_baseline_accounting_sha256":body["frozen_baseline_accounting_sha256"],
        "selected_parent_anchors":anchors, "selected_parent_anchors_sha256":module._sha(module._raw(anchors)),
        "capture_execution_context":{"capture_id":module.original.CAPTURE_ID, "capture_execution_head":"a"*40,
            "capture_execution_source_inventory_sha256":"b"*64,"bootstrap_execution_head":"c"*40}}


def _repair(body):
    body["accounting_sha256"] = module.pure.hash_payload(body["rows"])
    body["parent_ledger_sha256"] = module._sha(module._raw(body["parent_ledger"]))


def test_parent_metadata_validator_accepts_only_real_typed_fixture_partitions(supplied):
    body = _assess(supplied,_inputs(supplied,2,issuer_first=True)).to_payload()
    assert module._validate_metadata(body,_evidence(body),fixture_only=True) is body
    with pytest.raises(module.OriginalAdmissionRunnerError):module._validate_metadata(body,_evidence(body))


@pytest.mark.parametrize("mutation", ["drop", "swap", "ordinal", "raw_cik", "form", "year_flag", "hash", "promote",
    "authority", "count", "context", "old_reason", "old_disposition", "corroboration", "row_extra", "top_extra"])
def test_rehashed_or_coherent_output_metadata_mutations_do_not_change_original_roster_or_authority(supplied,mutation):
    body = _assess(supplied).to_payload(); evidence = _evidence(body)
    if mutation == "drop":body["rows"].pop()
    elif mutation == "swap":body["rows"][0],body["rows"][1] = body["rows"][1],body["rows"][0]
    elif mutation == "ordinal":body["rows"][0]["source_record_ordinal"] = True
    elif mutation == "raw_cik":body["rows"][0]["raw_issuer_cik"] = "0123456"
    elif mutation == "form":body["rows"][0]["form_type"] = "4"
    elif mutation == "year_flag":body["rows"][2]["accession_year_mismatch"] = False
    elif mutation == "hash":body["rows"][0]["raw_submission_member_sha256"] = "b"*64
    elif mutation == "promote":body["whole_quarter_identity_sha256"] = "a"*64
    elif mutation == "authority":body["authority"]["backtesting_ready"] = True
    elif mutation == "count":body["counts"]["selected_parents"] = True
    elif mutation == "context":body["parsed_snapshot_id"] = "invented"
    elif mutation == "old_reason":body["rows"][2]["frozen_baseline_quarantine_reasons"] = []
    elif mutation == "old_disposition":body["rows"][2]["frozen_baseline_disposition"] = "accepted"
    elif mutation == "corroboration":body["rows"][0]["corroboration"] = {"forged":True}
    elif mutation == "row_extra":body["rows"][0]["unexpected"] = False
    else:body["unexpected"] = False
    _repair(body)
    with pytest.raises((module.OriginalAdmissionRunnerError,ValueError,KeyError)):
        module._validate_metadata(body,evidence,fixture_only=True)


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "old_header", "body", "request", "result", "projection_parent", "projection_result",
    "clock", "topology", "refusal", "row_evidence", "projection_extra", "size_bool", "bound_count"])
def test_rehashed_parent_ledger_cannot_diverge_from_authenticated_original_control_anchors(supplied,mutation):
    body = _assess(supplied,_inputs(supplied,2)).to_payload(); evidence = _evidence(body)
    row = body["parent_ledger"][0]
    if mutation == "drop":body["parent_ledger"].pop()
    elif mutation == "duplicate":body["parent_ledger"][1] = deepcopy(row)
    elif mutation == "old_header":row["header_identity_bound"] = True
    elif mutation == "body":row["body_sha256"] = "b"*64
    elif mutation == "request":row["request_sha256"] = "b"*64
    elif mutation == "result":row["result_sha256"] = "b"*64
    elif mutation == "projection_parent":row["original_projection"]["original_parent_sha256"] = "b"*64
    elif mutation == "projection_result":row["original_projection"]["capture_result_sha256"] = "b"*64
    elif mutation == "clock":row["original_projection"]["accepted_clock_verified"] = True
    elif mutation == "topology":row["original_projection"]["header_topology"] = "reordered"
    elif mutation == "refusal":row["original_projection_refusal"] = "ignored"
    elif mutation == "row_evidence":body["rows"][2]["original_parent_evidence"] = None
    elif mutation == "projection_extra":row["original_projection"]["unexpected"] = "opaque"
    elif mutation == "size_bool":row["body_size_bytes"] = True
    else:body["counts"]["structurally_bound_original_parents"] = 0
    _repair(body)
    with pytest.raises((module.OriginalAdmissionRunnerError,ValueError,KeyError)):
        module._validate_metadata(body,evidence,fixture_only=True)


def test_small_fixture_cannot_assert_actual64_profile_or_missing_header_quarantines(supplied):
    counts = _assess(supplied).to_payload()["counts"]
    module._strict_counts(counts,actual=False)
    with pytest.raises(module.OriginalAdmissionRunnerError):module._strict_counts(counts)
    counts = {**counts,"source_filings":83657,"target_filings":71679,"context_filings":11978,"selected_parents":64,
        "retained_parent_bodies":64,"structurally_bound_original_parents":64,"structurally_bound_noncanonical_filings":64,
        "parser_quarantined_parents":0,"unavailable_selected_parents":0,"quarantined_filings":83593,
        "target_original_binding_missing":71615,"preserved_capture_header_quarantines":63}
    with pytest.raises(module.OriginalAdmissionRunnerError,match="actual_full_quarter_original64_profile_refused"):
        module._strict_counts(counts)


def test_settled_output_custody_still_rehashes_held_bytes_and_detects_sametime_mutation(tmp_path):
    root = tmp_path / "private-output";root.mkdir(mode=0o700)
    output = module._Output(root)
    try:
        output.publish("reservation.json",b'{"safe":true}',cap=128)
        output.check()
        leaf = root/"reservation.json"; before = leaf.stat()
        leaf.write_bytes(b'{"safe":null}')
        os.utime(leaf,ns=(before.st_atime_ns,before.st_mtime_ns))
        with pytest.raises(module.OriginalAdmissionRunnerError,match="output_leaf_content_changed"):output.check()
    finally:output.close()


@pytest.mark.parametrize("mutation", ["inode", "mode", "hardlink", "extra", "truncate"])
def test_output_leaf_and_inventory_custody_is_not_weakened_with_ctime_settlement(tmp_path,mutation):
    root = tmp_path/"private-output";root.mkdir(mode=0o700);output=module._Output(root)
    try:
        output.publish("reservation.json",b"{}",cap=32);leaf=root/"reservation.json"
        if mutation == "inode":
            leaf.rename(root/"old.json");leaf.write_bytes(b"{}");leaf.chmod(0o600)
        elif mutation == "mode":leaf.chmod(0o644)
        elif mutation == "hardlink":os.link(leaf,tmp_path/"linked")
        elif mutation == "extra":(root/"foreign.json").write_bytes(b"{}")
        else:leaf.write_bytes(b"{")
        with pytest.raises((module.OriginalAdmissionRunnerError,ValueError)):output.check()
    finally:output.close()


def test_worker_policy_is_process_tree_network_fork_exec_denied_and_output_only(tmp_path):
    policy=module.original.isolation._worker_policy(tmp_path)
    assert "(deny network*)" in policy and "(deny process-fork)" in policy and "(deny process-exec)" in policy
    assert "(deny file-write*)" in policy and '(allow file-write* (subpath "'+str(tmp_path)+'"))' in policy
    assert "/usr/bin/security" not in policy
    # The test launcher itself must be under actual native network denial;
    # native full worker-control conformance is separately run without nesting
    # sandbox-exec (macOS refuses nesting sandbox_apply under an existing seatbelt).
    module.original.capture.bootstrap.custody._effective_denial(require_fork=False)


def test_bootstrap_refuses_malformed_envelope_without_importing_consumer_or_sources(monkeypatch,capsys):
    monkeypatch.setattr(module.sys,"stdin",SimpleNamespace(buffer=io.BytesIO(b"{}")))
    with pytest.raises(SystemExit) as stop:exec(compile(module.SOURCE_ONLY_BOOTSTRAP,"<invented-bootstrap>","exec"),{})
    assert stop.value.code == 2
    value=module.original.capture._json(capsys.readouterr().out.encode().removesuffix(b"\n"))
    assert module._strict_failure(value)["failure_phase"] == "worker_bootstrap_context"


def test_initial_output_control_read_allows_only_genuine_ctime_settlement(tmp_path,monkeypatch):
    root=tmp_path/"private-output";root.mkdir(mode=0o700)
    leaf=root/"reservation.json";leaf.write_bytes(b"{}");leaf.chmod(0o600)
    before=leaf.stat();real_read=module.os.read;changed=[]
    def read_with_settlement(fd,count):
        result=real_read(fd,count)
        if not changed:
            os.chmod(leaf,0o600);changed.append(leaf.stat())
        return result
    monkeypatch.setattr(module.os,"read",read_with_settlement)
    output=module._Output(root)
    try:
        assert output.read_control("reservation.json") == b"{}"
        assert changed and before.st_ctime_ns != changed[0].st_ctime_ns
        output.check()
    finally:output.close()


@pytest.mark.parametrize("mutation", ["mode","mtime","inode","content"])
def test_initial_control_read_rejects_non_ctime_changes(tmp_path,monkeypatch,mutation):
    root=tmp_path/"private-output";root.mkdir(mode=0o700)
    leaf=root/"reservation.json";leaf.write_bytes(b"{}");leaf.chmod(0o600)
    real_read=module.os.read;changed=[]
    def mutating(fd,count):
        result=real_read(fd,count)
        if not changed:
            changed.append(True)
            if mutation == "mode":leaf.chmod(0o644)
            elif mutation == "mtime":
                info=leaf.stat();os.utime(leaf,ns=(info.st_atime_ns,info.st_mtime_ns+1_000_000))
            elif mutation == "inode":
                leaf.rename(root/"removed");leaf.write_bytes(b"{}");leaf.chmod(0o600)
            else:leaf.write_bytes(b"[]")
        return result
    monkeypatch.setattr(module.os,"read",mutating)
    output=module._Output(root)
    try:
        with pytest.raises(module.OriginalAdmissionRunnerError):output.read_control("reservation.json",expected_sha256=module._sha(b"{}"))
    finally:output.close()


def _published(tmp_path,body,evidence,*,mutate=None):
    root=tmp_path/"readback-output";root.mkdir(mode=0o700);output=module._Output(root)
    rows=[{"path":name,"sha256":"a"*64} for name in sorted(module.SOURCE_SEEDS|{"research/insider_buying/sec_ib1c_identity_v2.py"})]
    identity={"source_sha256":{row["path"]:row["sha256"] for row in rows}}
    frozen={"invented-frozen-path":"b"*64}
    reservation=module._raw(module._reservation(identity,frozen,evidence))
    output.publish("reservation.json",reservation,cap=module.MAX_CONTROL_BYTES)
    assessment_raw=module._raw(body);ledger_raw=module._raw({key:value for key,value in body.items() if key!="rows"})
    assessment_sha=output.publish("assessment.json",assessment_raw,cap=module.MAX_ASSESSMENT_BYTES)
    ledger_sha=output.publish("parent-admission.json",ledger_raw,cap=module.MAX_LEDGER_BYTES)
    complete={"schema":module.SCHEMA+"/complete","audit_id":module.AUDIT_ID,"fixture_only":True,
        "current_execution_identity":identity,"frozen_sources":frozen,"reservation_sha256":module._sha(reservation),
        "pinned_metadata_evidence":evidence,**evidence["capture_execution_context"],"capture_report_sha256":module.CAPTURE_REPORT_SHA256,
        "original_preparation_producer_commit":module.original.downstream.PRODUCER_COMMIT,
        "original_preparation_completion_sha256":module.original.downstream.EXPECTED_COMPLETION_SHA256,
        "original_preparation_assessment_sha256":module.original.downstream.EXPECTED_ASSESSMENT_SHA256,
        "source_only_bootstrap_sha256":module._sha(module.SOURCE_ONLY_BOOTSTRAP.encode()),
        "assessment_sha256":assessment_sha,"assessment_bytes":len(assessment_raw),
        "parent_ledger_sha256":ledger_sha,"parent_ledger_bytes":len(ledger_raw),
        "source_execution":module._executed_sources(rows,identity),
        "effective_process_tree_network_denial":True,"effective_process_fork_denial":True,
        "effective_keychain_exec_denial":True,"writes_confined_to_fresh_output_by_launcher":True,
        "authority":module.pure.authority(),"whole_quarter_identity_sha256":None,
        **{key:body[key] for key in ("counts","form_counts","accounting_sha256","parsed_snapshot_id","parsed_lineage_hash",
            "census_quarter_sha256","frozen_baseline_assessment_sha256","frozen_baseline_accounting_sha256")}}
    if mutate:mutate(complete)
    complete_sha=output.publish("complete.json",module._raw(complete),cap=module.MAX_CONTROL_BYTES)
    output.close()
    summary={"audit_id":module.AUDIT_ID,"fixture_only":True,"complete_sha256":complete_sha,"assessment_sha256":assessment_sha,
        "parent_ledger_sha256":ledger_sha,"counts":body["counts"],"authority":module.pure.authority(),
        "capture_report_sha256":module.CAPTURE_REPORT_SHA256}
    return module._Output(root),summary,identity,frozen


def test_end_to_end_fresh_output_publication_and_parent_metadata_only_readback(supplied,tmp_path):
    body=_assess(supplied).to_payload();evidence=_evidence(body)
    output,summary,identity,frozen=_published(tmp_path,body,evidence)
    try:
        complete=module._verify_outputs(output,summary,identity,frozen,evidence,fixture_only=True)
        assert complete["counts"] == body["counts"]
        assert output.read_metadata("assessment.json") == body
        output.check(final=True)
    finally:output.close()


@pytest.mark.parametrize("mutation", ["source_only","source_count","source_hash","historical","census","baseline_accounting",
    "capture_head","capture_inventory","capture_bootstrap","keychain","isolation","bytes_bool","authority","source_extra"])
def test_coherent_rehashed_complete_metadata_does_not_bypass_parent_readback(supplied,tmp_path,mutation):
    body=_assess(supplied).to_payload();evidence=_evidence(body)
    def mutate(complete):
        if mutation == "source_only":complete["source_execution"]["source_only_lane_imports"]=False
        elif mutation == "source_count":complete["source_execution"]["executed_source_count"]+=1
        elif mutation == "source_hash":complete["source_execution"]["executed_source_inventory_sha256"]="b"*64
        elif mutation == "historical":complete["source_execution"]["full_historical_environment_reconstructed"]=True
        elif mutation == "census":complete["census_quarter_sha256"]="b"*64
        elif mutation == "baseline_accounting":complete["frozen_baseline_accounting_sha256"]="b"*64
        elif mutation == "capture_head":complete["capture_execution_head"]="b"*40
        elif mutation == "capture_inventory":complete["capture_execution_source_inventory_sha256"]="c"*64
        elif mutation == "capture_bootstrap":complete["bootstrap_execution_head"]="d"*40
        elif mutation == "keychain":complete["effective_keychain_exec_denial"]=False
        elif mutation == "isolation":complete["effective_process_tree_network_denial"]=False
        elif mutation == "bytes_bool":complete["assessment_bytes"]=True
        elif mutation == "authority":complete["authority"]["backtesting_ready"]=True
        else:complete["source_execution"]["unlisted_claim"]=True
    output,summary,identity,frozen=_published(tmp_path,body,evidence,mutate=mutate)
    try:
        with pytest.raises((module.OriginalAdmissionRunnerError,ValueError)):
            module._verify_outputs(output,summary,identity,frozen,evidence,fixture_only=True)
    finally:output.close()


def test_new_baseline_hash_labels_are_bound_to_old_external_pins(supplied):
    body=_assess(supplied).to_payload();evidence=_evidence(body)
    for key in ("frozen_baseline_assessment_sha256","frozen_baseline_accounting_sha256"):
        altered=deepcopy(body);altered[key]="b"*64
        with pytest.raises(module.OriginalAdmissionRunnerError,match="metadata_frozen_baseline_digest_differs"):
            module._validate_metadata(altered,evidence,fixture_only=True)


def test_keychain_probe_requires_native_errno_and_does_not_accept_a_success(monkeypatch,tmp_path):
    monkeypatch.setattr(module.original,"_prove_worker_isolation",lambda *_:None)
    for number in (errno.EPERM,errno.EACCES):
        def denied(*_a,**_k):raise OSError(number,"invented secret must not be output")
        monkeypatch.setattr(module.os,"execve",denied)
        module._prove_worker_isolation(tmp_path)
    monkeypatch.setattr(module.os,"execve",lambda *_a,**_k:None)
    with pytest.raises(module.OriginalAdmissionRunnerError,match="native_keychain_exec_denial_not_observed"):
        module._prove_worker_isolation(tmp_path)


def test_worker_denial_precedes_all_real_input_loaders(monkeypatch,tmp_path):
    root=tmp_path/"reserved";root.mkdir(mode=0o700);(root/"reservation.json").write_bytes(b"{}");(root/"reservation.json").chmod(0o600)
    identity={"source_sha256":{}};frozen={};metadata={};events=[]
    output=SimpleNamespace(path=root,fd=os.open(root,os.O_RDONLY),read_control=lambda *_a,**_k:module._raw(module._reservation(identity,frozen,metadata)),
        close=lambda:events.append("closed"))
    monkeypatch.setattr(module.original.capture.bootstrap,"_required_identity",lambda *_a:None)
    monkeypatch.setattr(module,"_current_bytes",lambda *_a:None)
    monkeypatch.setattr(module,"_output_directory",lambda *_a,**_k:output)
    monkeypatch.setattr(module,"_PinnedEvidence",lambda:pytest.fail("must not load evidence before denial"))
    monkeypatch.setattr(module.original,"_load_original_preparation",lambda:pytest.fail("must not open original preparation"))
    monkeypatch.setattr(module.original,"_load_sealed_capture",lambda *_a:pytest.fail("must not open original body"))
    def denied(*_a):events.append("native-probe");raise module.OriginalAdmissionRunnerError("invented_denial_refusal")
    monkeypatch.setattr(module,"_prove_worker_isolation",denied)
    try:
        with pytest.raises(module.OriginalAdmissionRunnerError,match="invented_denial_refusal"):
            module._worker(module.AUDIT_ID,expected_head="a"*40,parent_context={"identity":identity,"frozen_sources":frozen,
                "pinned_metadata_evidence":metadata},executed_sources=lambda:[])
        assert events == ["native-probe","closed"]
    finally:os.close(output.fd)


def test_all_resources_close_and_primary_failure_is_preserved():
    events=[]
    class Held:
        def __init__(self,name,fail=False):self.name,self.fail=name,fail
        def close(self):
            events.append(self.name)
            if self.fail:raise ValueError("cleanup")
    with pytest.raises(ValueError,match="cleanup"):module._close_all([Held("one",True),Held("two"),Held("three",True)])
    assert events == ["one","two","three"]
    events.clear()
    with pytest.raises(KeyError,match="primary"):
        try:raise KeyError("primary")
        finally:module._close_all([Held("one",True),Held("two")])
    assert events == ["one","two"]


@pytest.mark.parametrize("fallback", ["parent_preflight","worker_publication","private arbitrary secret"])
def test_failure_outputs_never_include_exception_or_private_path_strings(fallback):
    diagnostic=module._failure_diagnostic(OSError(errno.EPERM,"private api_key madeup /secret/path"),fallback)
    raw=module._raw(module._strict_failure(diagnostic))
    assert b"api_key" not in raw and b"madeup" not in raw and b"/secret/path" not in raw


def test_inactive_source_refuses_before_metadata_raw_inputs_or_namespace_claim(monkeypatch):
    monkeypatch.setattr(module,"__file__",str(LANE/"artifacts/ignored-inactive.py"))
    monkeypatch.setattr(module.original,"_fixed_source_identity",lambda *_a:pytest.fail("must not source-inventory from inactive code"))
    monkeypatch.setattr(module,"_PinnedEvidence",lambda:pytest.fail("must not read actual evidence"))
    monkeypatch.setattr(module,"_output_directory",lambda *_a,**_k:pytest.fail("must not create output"))
    with pytest.raises(module.OriginalAdmissionRunnerError,match="fixed_lane_runner_source_required"):
        module.run_observed_admission(expected_head="a"*40)


def test_no_nonfixed_audit_id_or_runtime_rebinding_parameters(monkeypatch):
    monkeypatch.setattr(module.original.capture.custody,"_Directory",lambda *_a,**_k:pytest.fail("must not touch actualnamespace"))
    with pytest.raises(module.OriginalAdmissionRunnerError):module._output_directory(module.AUDIT_ID+"-retry",create=True)
    with pytest.raises(SystemExit):module.main(["--expected-head","a"*40,"--audit-id","renamed-retry"])
