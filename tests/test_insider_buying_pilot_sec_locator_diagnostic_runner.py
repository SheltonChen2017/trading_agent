"""Invented metadata/control IPC only; no actual source tree or transport."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_pilot_sec_locator_diagnostic_runner as m


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    spec=importlib.util.spec_from_file_location("invented_locator_runner_helper",
        Path(__file__).with_name("test_insider_buying_pilot_sec_locator_diagnostic.py"))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    return helper,helper.corpus.__wrapped__(tmp_path_factory)


@pytest.fixture
def sample(corpus,monkeypatch):
    helper,data=corpus
    case=helper._case(data,monkeypatch)
    first=helper._run(case).to_payload()
    periods=["2020Q1",*m.base.roster.PILOT_PERIODS[:11]]
    reports=[]
    for index,period in enumerate(periods):
        row=deepcopy(first);source=row["source_record"];year=int(period[:4]);quarter=int(period[-1])
        source.update(period=period,source_record_ordinal=3,filing_date=f"{year}-{(quarter-1)*3+1:02d}-01",
            accession_number=f"0000000001-{year%100:02d}-{100000+index:06d}")
        source["raw_filing_date"]=source["filing_date"]
        source["accession_key_sha256"]=m._sha(source["accession_number"].encode())
        source["filing_metadata_sha256"]=m._sha(m._raw({k:v for k,v in source.items() if k!="filing_metadata_sha256"}))
        row["quarantine_row"]["source"]=deepcopy(source)
        row["quarantine_row"]["source_record_sha256"]=source["filing_metadata_sha256"]
        row.update(fixture_only=False,quarantine_index=index,source_record_sha256=source["filing_metadata_sha256"],
            quarantine_sha256=m._sha(m._raw(row["quarantine_row"])),
            prior_selection_complete_sha256=m.SELECTION_PINS["complete.json"][0],prior_selection_sha256=m.SELECTION_SHA256)
        row["master"].update(period=period,decoded_sha256=m._sha(period.encode()),parsed_receipt_sha256=m._sha((period+"receipt").encode()))
        m.pure.validate_locator_diagnostic_payload(row);reports.append(row)
    lines=b"".join(m._raw(r)+b"\n" for r in reports)
    qlines=b"".join(m._raw(r["quarantine_row"])+b"\n" for r in reports)
    batch={"schema":m.pure.SCHEMA+"/batch","scope":"all_pinned_selector_quarantines","fixture_only":False,
        "prior_selection_complete_sha256":m.SELECTION_PINS["complete.json"][0],"prior_selection_sha256":m.SELECTION_SHA256,
        "prior_quarantine_jsonl_sha256":m._sha(qlines),"quarantine_count":12,"pilot_quarantine_count":11,
        "affected_periods":periods,"master_scan_count":12,"reports":reports,"reports_jsonl_sha256":m._sha(lines),
        "reports_jsonl_bytes":len(lines),**dict.fromkeys(m.pure._FALSE_REPORT,False),**dict.fromkeys(m.pure._ZERO_REPORT,0),
        "authority":dict(m.pure.audit._AUTHORITY)}
    m.pure.validate_locator_diagnostic_batch_payload(batch)
    all_periods=[f"{y}Q{q}" for y in range(2006,2027) for q in range(1,5) if (y,q)<=(2026,2)]
    master_rows=[]
    for period in all_periods:
        summary=next((r["master"] for r in reports if r["master"]["period"]==period),None) or first["master"]
        digest=m._sha((period+"inventedgzip").encode())
        master_rows.append({"period":period,"status":"acquired_noncanonical","source_url":f"https://www.sec.gov/Archives/edgar/full-index/{period[:4]}/QTR{period[-1]}/master.gz",
            "raw_object":{"sha256":digest,"relative_path":"objects/"+digest+".bin","size_bytes":17},
            "receipt":{"decoded_sha256":summary["decoded_sha256"],"decoded_size_bytes":summary["decoded_size_bytes"],
                "parser_version":m.pure.master.MASTER_INDEX_PARSER_VERSION,"master_receipt_sha256":summary["parsed_receipt_sha256"],
                "all_filing_row_count":summary["all_filing_row_count"],"form4_or_4a_path_rows":summary["form4_or_4a_path_rows"]}})
    master_report=m._raw({"kind":"INSETF-SEC-MASTER82-RESUMABLE-v1","master_indexes":master_rows,
        "complete_82_master_indexes_acquired":True,"halted_reason":None})
    commit=m._raw({"kind":"sec-master82-commit","report_name":"report.json","report_sha256":m._sha(master_report)})
    monkeypatch.setattr(m.base.bootstrap,"MASTER_COMMIT_SHA256",m._sha(commit))
    monkeypatch.setattr(m.base.bootstrap,"MASTER_REPORT_SHA256",m._sha(master_report))
    witness={"commit_hex":commit.hex(),"report_hex":master_report.hex()}
    descriptors=m._master_witness(witness)
    identity={"root":str(m.LANE_ROOT),"branch":m.base.LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":{m.SELF_PATH:"a"*64,m.PURE_PATH:"b"*64}}
    identity["source_inventory_sha256"]=m._sha(m._raw(identity["source_sha256"]))
    original={"locator_quarantines":[r["quarantine_row"] for r in reports],"locator_quarantine_jsonl_sha256":m._sha(qlines)}
    row_pins=tuple(r["quarantine_sha256"] for r in reports)
    # Only the absent on-disk three-control loader is stubbed; complete-control
    # validation has separate exact-byte/schema tests below and pure helper tests.
    monkeypatch.setattr(m,"_selection_controls",lambda controls:(None,original,row_pins))
    result={"schema":m.SCHEMA,"audit_id":m.AUDIT_ID,"registration":deepcopy(m.REGISTRATION),
        "registration_sha256":m._sha(m._raw(m.REGISTRATION)),"execution_identity":identity,
        "selection_control_pins":m.REGISTRATION["selection_control_pins"],"selection_controls":dict.fromkeys(m.SELECTION_PINS,{}),
        "master_descriptors":descriptors,"master_descriptors_sha256":m._sha(m._raw(descriptors)),
        "master_control_witness":witness,"diagnostic":batch,"diagnostic_sha256":m._sha(m._raw(batch)),
        "native_network_fork_allwrite_securityexec_denial":True,"all25_compressed_master_objects_hash_rechecked":True,
        "unaffected_master_decoded_or_reparsed":False,"actual_source_body_decoded":False,
        "new_provider_requests":0,"credential_reads":0,"qc_accesses":0,"outcome_looks":0,"backtests":0,
        "source_authenticated_here":False,"canonical_admitted":False,"backtesting_ready":False}
    assert m._validate(result,identity) is result
    return SimpleNamespace(result=result,identity=identity,original=original,witness=witness)


def _reframe(result):
    batch=result["diagnostic"]
    lines=b"".join(m._raw(row)+b"\n" for row in batch["reports"])
    batch.update(reports_jsonl_sha256=m._sha(lines),reports_jsonl_bytes=len(lines))
    result["diagnostic_sha256"]=m._sha(m._raw(batch))
    result["master_descriptors_sha256"]=m._sha(m._raw(result["master_descriptors"]))


@pytest.mark.parametrize("fault",["unknown","ready","typed_zero","no_native","fixture","count","dropped","periods",
    "source_identity","source_inventory","master_witness","master_descriptor","master_crosslink","row_membership","selector_witness"])
def test_parent_result_strict_external_control_membership_and_no_authority_laundering(sample,fault):
    result=deepcopy(sample.result);identity=sample.identity
    if fault=="unknown":result["unexpected"]=True
    if fault=="ready":result["backtesting_ready"]=True
    if fault=="typed_zero":result["credential_reads"]=False
    if fault=="no_native":result["native_network_fork_allwrite_securityexec_denial"]=False
    if fault=="fixture":result["diagnostic"]["fixture_only"]=True
    if fault=="count":result["diagnostic"]["quarantine_count"]=11
    if fault=="dropped":result["diagnostic"]["reports"].pop()
    if fault=="periods":result["master_descriptors"].reverse()
    if fault=="source_identity":result["execution_identity"]["head"]="b"*40
    if fault=="source_inventory":result["execution_identity"]["source_inventory_sha256"]="f"*64
    if fault=="master_witness":result["master_control_witness"]["report_hex"]="00"
    if fault=="master_descriptor":result["master_descriptors"][0]["raw_object"]["sha256"]="f"*64
    if fault=="master_crosslink":result["diagnostic"]["reports"][0]["master"]["decoded_sha256"]="f"*64
    if fault=="row_membership":
        row=result["diagnostic"]["reports"][0];source=row["source_record"]
        source["raw_symbol_label"]="DIFFERENT INVENTED LABEL"
        source["filing_metadata_sha256"]=m._sha(m._raw({k:v for k,v in source.items() if k!="filing_metadata_sha256"}))
        row["source_record_sha256"]=source["filing_metadata_sha256"]
        row["quarantine_row"]["source"]=deepcopy(source);row["quarantine_row"]["source_record_sha256"]=source["filing_metadata_sha256"]
        row["quarantine_sha256"]=m._sha(m._raw(row["quarantine_row"]))
        result["diagnostic"]["prior_quarantine_jsonl_sha256"]=m._sha(b"".join(m._raw(r["quarantine_row"])+b"\n" for r in result["diagnostic"]["reports"]))
    if fault=="selector_witness":result["selection_controls"]={}
    _reframe(result)
    with pytest.raises((m.LocatorRunnerError,m.pure.PilotSecLocatorDiagnosticError)):m._validate(result,identity)


def test_master_control_witness_bytes_external_pins_and_exact25_roster(sample,monkeypatch):
    assert len(m._master_witness(sample.witness))==25
    with pytest.raises(m.LocatorRunnerError):m._master_witness(dict(sample.witness,report_hex=sample.witness["report_hex"].upper()))
    report=m.base.bootstrap._json(bytes.fromhex(sample.witness["report_hex"]))
    report["master_indexes"].pop()
    raw=m._raw(report);commit=m._raw({"kind":"sec-master82-commit","report_name":"report.json","report_sha256":m._sha(raw)})
    monkeypatch.setattr(m.base.bootstrap,"MASTER_REPORT_SHA256",m._sha(raw));monkeypatch.setattr(m.base.bootstrap,"MASTER_COMMIT_SHA256",m._sha(commit))
    with pytest.raises(m.LocatorRunnerError,match="complete_inventory"):m._master_witness({"commit_hex":commit.hex(),"report_hex":raw.hex()})


def test_production_selection_loader_rejects_even_hash_bound_invented_fixture(corpus,monkeypatch):
    helper,data=corpus;case=helper._case(data,monkeypatch)
    # It cannot become a production12-row control merely by rebinding external
    # test hashes. The real pure validator/factory is not stubbed in this test.
    raw=m._raw(case.complete)
    controls={"complete.json":raw,"reservation.json":b"{}","terminal.json":b"{}"}
    monkeypatch.setattr(m,"SELECTION_PINS",{name:(m._sha(value),len(value)) for name,value in controls.items()})
    with pytest.raises(m.LocatorRunnerError):m._selection_controls(controls)


@pytest.mark.parametrize("fault",["empty","dirty","missing_source","bad_digest","path","inventory","branch"])
def test_execution_identity_is_exact_current_lane_clean_source_closure(sample,fault):
    identity=deepcopy(sample.identity)
    if fault=="empty":identity["source_sha256"]={}
    if fault=="dirty":identity["clean"]=False
    if fault=="missing_source":del identity["source_sha256"][m.SELF_PATH]
    if fault=="bad_digest":identity["source_sha256"][m.SELF_PATH]="notdigest"
    if fault=="path":identity["source_sha256"]["../bad"]="a"*64
    if fault=="inventory":identity["source_inventory_sha256"]="f"*64
    if fault=="branch":identity["branch"]="main"
    with pytest.raises((m.LocatorRunnerError,m.pure.PilotSecLocatorDiagnosticError)):m._identity(identity)


def test_exact_initial_native_child_command_no_site_minimal_env_and_no_outputs(sample):
    command=m._command(sample.identity)
    assert command[:5]==("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p")
    policy=command[5]
    assert all(s in policy for s in ("(deny network*)","(deny process-fork)","(deny file-write*)",'/usr/bin/security'))
    assert command[7:12]==("-I","-S","-B","-X","pycache_prefix="+m.base.EMPTY_CACHE_PREFIX)
    assert command[-2]=="-c" and "m._worker(identity)" in command[-1]
    assert m.REGISTRATION["persistent_result_published"] is False
    guard=m._Guard(sample.identity["head"],command)
    with pytest.raises(m.LocatorRunnerError,match="all_writes_refused"):guard._write(Path("/private/tmp/invented"))


@pytest.mark.parametrize("fault",["not_isolated","site","user_site","bytecode","cache"])
def test_worker_rejects_bad_native_flags_before_input_loader(monkeypatch,sample,fault):
    flags=SimpleNamespace(isolated=1,no_site=1,no_user_site=1,dont_write_bytecode=1)
    if fault=="not_isolated":flags.isolated=0
    if fault=="site":flags.no_site=0
    if fault=="user_site":flags.no_user_site=0
    if fault=="bytecode":flags.dont_write_bytecode=0
    monkeypatch.setattr(m.sys,"flags",flags)
    monkeypatch.setattr(m.sys,"pycache_prefix","/wrong" if fault=="cache" else m.base.EMPTY_CACHE_PREFIX)
    monkeypatch.setattr(m,"_SelectionHold",lambda:pytest.fail("input loader reached before isolation validation"))
    with pytest.raises(m.LocatorRunnerError,match="worker_flags"):m._worker(sample.identity)


def test_native_denial_probe_precedes_any_input_and_git_never_runs_in_worker(monkeypatch,sample):
    monkeypatch.setattr(m.sys,"flags",SimpleNamespace(isolated=1,no_site=1,no_user_site=1,dont_write_bytecode=1))
    monkeypatch.setattr(m.sys,"pycache_prefix",m.base.EMPTY_CACHE_PREFIX)
    monkeypatch.setattr(m.base,"_prove_isolation",lambda:(_ for _ in ()).throw(m.LocatorRunnerError("invented_native_denial_missing")))
    monkeypatch.setattr(m,"_SelectionHold",lambda:pytest.fail("input loader reached"))
    monkeypatch.setattr(m.base.custody,"_identity",lambda *a:pytest.fail("Git must remain outside denied worker"))
    with pytest.raises(m.LocatorRunnerError,match="native_denial_missing"):m._worker(sample.identity)


def test_parent_single_exact_worker_validates_witnesses_then_strips_without_rehash_label(monkeypatch,sample):
    calls=[]
    monkeypatch.setattr(m.base.custody,"_identity",lambda head:(calls.append(head) or sample.identity))
    monkeypatch.setattr(m.sys,"addaudithook",lambda hook:None)
    raw=m._raw(sample.result)+b"\n"
    def launch(command,**kwargs):
        assert command==m._command(sample.identity) and kwargs==dict(cwd=m.LANE_ROOT,env=None,timeout=m.CONTROL_TIMEOUT,cap=m.MAX_REPORT)
        calls.append("child");return SimpleNamespace(returncode=0,stdout=raw,stderr=b"")
    monkeypatch.setattr(m.base.launcher,"run_child",launch)
    returned=m.run_actual(sample.identity["head"])
    assert calls==[sample.identity["head"],"child",sample.identity["head"]]
    assert "selection_controls" not in returned and "master_control_witness" not in returned
    assert returned["selection_control_witness_validated_and_omitted"] is True
    assert returned["master_control_witness_validated_and_omitted"] is True
    assert returned["observed_worker_stdout_sha256"]==m._sha(raw) and returned["observed_worker_stdout_bytes"]==len(raw)
    assert returned["observed_worker_stdout_sha256"]!=m._sha(m._raw(returned))


@pytest.mark.parametrize("fault",["exit","stderr","empty","overlimit","final_identity","bad_json"])
def test_parent_refuses_child_or_final_source_drift(monkeypatch,sample,fault):
    calls=[]
    def identity(head):
        calls.append(head)
        if fault=="final_identity" and len(calls)==2:return dict(sample.identity,head="b"*40)
        return sample.identity
    monkeypatch.setattr(m.base.custody,"_identity",identity);monkeypatch.setattr(m.sys,"addaudithook",lambda hook:None)
    stdout=m._raw(sample.result)+b"\n";stderr=b"";exit_code=0
    if fault=="exit":exit_code=2
    if fault=="stderr":stderr=b"PRIVATE INVENTED ERROR"
    if fault=="empty":stdout=b""
    if fault=="overlimit":monkeypatch.setattr(m,"MAX_REPORT",1)
    if fault=="bad_json":stdout=b"PRIVATE INVENTED BAD JSON"
    monkeypatch.setattr(m.base.launcher,"run_child",lambda *a,**k:SimpleNamespace(returncode=exit_code,stdout=stdout,stderr=stderr))
    with pytest.raises(Exception):m.run_actual(sample.identity["head"])


def test_cli_refusal_is_sanitized_exit2_not_success(monkeypatch,capsys):
    monkeypatch.setattr(m,"run_actual",lambda head:(_ for _ in ()).throw(ValueError("PRIVATE INVENTED LOCATOR BODY")))
    assert m.main(["--expected-head","a"*40])==2
    assert capsys.readouterr().out=='{"disposition":"pilot_locator_diagnostic_refused"}\n'


def test_derive_hash_holds_all25_but_only_decodes_affected_masters_and_requires_genuine_result(monkeypatch,sample):
    body=deepcopy(sample.result["diagnostic"]);descriptors=deepcopy(sample.result["master_descriptors"])
    decoded=b"INVENTED METADATA ONLY NOT ACTUAL MASTER";compressed=b"x"*17
    for item in descriptors:
        item["producer_receipt"].update(decoded_sha256=m._sha(decoded),decoded_size_bytes=len(decoded))
    for report in body["reports"]:
        report["master"].update(decoded_sha256=m._sha(decoded),decoded_size_bytes=len(decoded))
    lines=b"".join(m._raw(row)+b"\n" for row in body["reports"])
    body.update(reports_jsonl_sha256=m._sha(lines),reports_jsonl_bytes=len(lines))
    m.pure.validate_locator_diagnostic_batch_payload(body)
    reads=[];decodes=[];calls=[]
    class Tree:
        def read(self,parts,name,*,cap,expected):
            reads.append((parts,name,cap,expected));return compressed
    held=SimpleNamespace(worker=sample.original,controls={"complete.json":b"INVENTED CONTROL"},
        row_pins=tuple(r["quarantine_sha256"] for r in body["reports"]))
    monkeypatch.setattr(m,"_master_descriptors",lambda tree:(descriptors,sample.witness))
    monkeypatch.setattr(m.base.bootstrap,"_decompress_master",lambda raw:(decodes.append(raw) or decoded))
    def assess(**kwargs):
        calls.append(kwargs);return m.pure._seal(body)
    monkeypatch.setattr(m.pure,"assess_pilot_sec_locator_quarantines",assess)
    returned,observed,witness=m._derive(held,Tree())
    assert returned==body and observed==descriptors and witness==sample.witness
    assert len(reads)==25 and len(decodes)==12 and len(calls)==1
    assert [item["period"] for item in calls[0]["master_inputs"]]==body["affected_periods"]
    assert calls[0]["expected_quarantine_sha256s"]==held.row_pins
    monkeypatch.setattr(m.pure,"assess_pilot_sec_locator_quarantines",lambda **kwargs:SimpleNamespace(to_payload=lambda:body))
    with pytest.raises(m.pure.PilotSecLocatorDiagnosticError,match="exact_locator"):m._derive(held,Tree())


def test_worker_positive_orchestration_rechecks_inputs_sources_and_drains_holds(monkeypatch,sample):
    events=[]
    monkeypatch.setattr(m.sys,"flags",SimpleNamespace(isolated=1,no_site=1,no_user_site=1,dont_write_bytecode=1))
    monkeypatch.setattr(m.sys,"pycache_prefix",m.base.EMPTY_CACHE_PREFIX)
    monkeypatch.setattr(m.base,"_prove_isolation",lambda:events.append("prove_native_before_read"))
    def source_bytes(root,paths):
        events.append("source_hashes");return m.base.FROZEN if set(paths)==set(m.base.FROZEN) else sample.identity["source_sha256"]
    monkeypatch.setattr(m.base.custody,"_source_bytes",source_bytes)
    class Held:
        controls=dict.fromkeys(m.SELECTION_PINS,b"{}")
        def __init__(self):events.append("open_selection")
        def recheck(self):events.append("selection_recheck")
        def close(self):events.append("selection_close")
    class Tree:
        def __init__(self,spec):self.spec=spec;self.locks=[];self.directories={};events.append("open_master")
        def recheck(self):events.append("master_recheck")
    monkeypatch.setattr(m,"_SelectionHold",Held);monkeypatch.setattr(m.base.bootstrap,"_Tree",Tree)
    monkeypatch.setattr(m,"_derive",lambda held,tree:(sample.result["diagnostic"],sample.result["master_descriptors"],sample.witness))
    result=m._worker(sample.identity)
    assert result["backtesting_ready"] is False
    assert events.index("prove_native_before_read")<events.index("open_selection")<events.index("open_master")
    assert "selection_recheck" in events and "master_recheck" in events and events[-1]=="selection_close"
    assert events.count("source_hashes")==4


def test_selection_cleanup_drains_and_preserves_primary():
    events=[]
    class Bad:
        def close(self):events.append("bad");raise OSError("INVENTED PRIVATE")
    class Good:
        def close(self):events.append("good")
    held=object.__new__(m._SelectionHold)
    held.tree=SimpleNamespace(handles=[("good",Good(),None,None),("bad",Bad(),None,None)],chain=Good())
    with pytest.raises(m.LocatorRunnerError,match="cleanup_refused"):held.close()
    assert events==["bad","good","good"]
    events.clear()
    try:
        raise RuntimeError("ORIGINAL")
    except RuntimeError:
        held.close()
    assert events==["bad","good","good"]
