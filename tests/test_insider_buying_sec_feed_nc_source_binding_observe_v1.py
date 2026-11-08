"""Invented source/prefix controls only; no actual retained files or accounts."""
import copy
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import zlib

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
from research import insider_buying_sec_feed_nc_source_binding_observe_v1 as m

CONTACT="invented-binder@unit.test"


def _helper(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


@pytest.fixture(scope="module")
def source_corpus(tmp_path_factory):
    helper=_helper("invented_NC_observe_binder","test_insider_buying_sec_feed_nc_source_binding_v1.py")
    return helper,helper.corpus.__wrapped__(tmp_path_factory)


def _intake(tmp_path,corpus):
    helper,(fixture_helper,supplied,_,_)=corpus;manifest,images,selected=supplied
    root=tmp_path/"intake";root.mkdir(mode=0o700)
    (root/m.selector.pure.census._MANIFEST_NAME).write_bytes(manifest)
    auxiliary=b"invented opaque source-control";(root/m.selector._AUX_NAME).write_bytes(auxiliary)
    for image in images:(root/(image.period.lower()+"_form345.zip")).write_bytes(image.raw_bytes)
    for path in root.iterdir():path.chmod(0o600)
    pins={"root":root,"manifest_pin":(m._sha(manifest),len(manifest)),"auxiliary_pin":(m._sha(auxiliary),len(auxiliary))}
    return pins,{**pins,"fixture_only":True,"census_pin":selected["census_sha256"],"header_pin":selected["header_preflight_sha256"]}


def _header(name,size,kind=b"0"):
    raw=bytearray(512);raw[:len(name)]=name
    for at,width,text in ((100,8,b"0000600\0"),(108,8,b"0000000\0"),(116,8,b"0000000\0"),
            (124,12,format(size,"011o").encode()+b"\0"),(136,12,b"00000000000\0")):
        raw[at:at+width]=text
    raw[156:157]=kind;raw[257:265]=b"ustar  \0";raw[148:156]=b"        "
    raw[148:156]=format(sum(raw),"06o").encode()+b"\0 ";return bytes(raw)


def _member(payload,name=b"opaque-file.nc"):
    return _header(name,len(payload))+payload+bytes((-len(payload))%512)


def _prefix(corpus,*,private=b""):
    helper,supplied=corpus;row=helper._row(supplied,"2020Q4")
    payloads=(helper._payload(row),helper._payload(helper._row(supplied)),helper._payload(row,accession="9999999999-20-000099",extra=b"<PAPER>Y\n"))
    decoded=_header(b"directory/",0,b"5")+b"".join(_member(raw) for raw in payloads)
    decoded+=_member(private+b"x"*150000,name=b"partial.nc")
    writer=zlib.compressobj(level=0,wbits=31);raw=(writer.compress(decoded)+writer.flush())[:65536]
    assert len(raw)==65536;return raw,payloads


def _identity(root):
    sources={name:"a"*64 for name in (m.SELF_PATH,m.TEST_PATH,m.inherited.inherited.SELF_PATH,m.inherited.inherited.TEST_PATH)}
    return {"root":str(root),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}


@pytest.fixture
def observation(tmp_path,source_corpus,monkeypatch):
    pins,genuine_args=_intake(tmp_path,source_corpus);metadata=m._IntakeMetadata(fixture=True,**pins)
    raw,_=_prefix(source_corpus);identity=_identity(tmp_path)
    helper,supplied=source_corpus;summary=supplied[2].to_payload();selection=helper._args(supplied)["selection_raw"]
    prefix=SimpleNamespace(root=tmp_path,pins={"complete.json":"b"*64,"prefix.bin":m._sha(raw)},
        metadata={"original_execution_identity":identity,"external_pins":{"complete.json":"b"*64,"prefix.bin":m._sha(raw)}},read_body=lambda:raw,check=lambda:None)
    source=SimpleNamespace(consumed=frozenset(),selection=selection,intake=metadata,metadata={"retained_source_roster":summary,"consumed_count":0},check=metadata.check)
    monkeypatch.setattr(m.capture,"_verify_files",lambda *a,**kw:{"producer_execution_identity":identity,"current_contact_prefix_rescreened":True})
    monkeypatch.setattr(m,"_analysis_intake",lambda:m.selector._HeldIntake(**genuine_args))
    plan=m._plan(identity,prefix.metadata,source.metadata)
    try:yield identity,prefix,source,plan,m._analyse(identity,CONTACT,prefix,source,plan,fixture=True)
    finally:metadata.close()


def test_registration_is_new_readonly_question_and_explicit_deferred_body_proof():
    value=m.registration();assert value["preflight_prefix_and_ZIP_body_bytes_read"]==0
    assert value["analysis_opaque_intake_ZIPs_hashed"]==82 and value["analysis_SUBMISSION_quarters_rederived"]==25
    assert value["required_parent_source_window"]=="2020Q4..2025Q4"
    assert value["maximum_control_or_IPC_bytes"]==2*1024**2 and value["native_worker_seconds"]==900
    assert value["authority"]["files_written"]==value["authority"]["new_requests"]==0
    value["original_prefix_pins"]["prefix.bin"]="0"*64
    assert m.registration()["original_prefix_pins"]["prefix.bin"]!=value["original_prefix_pins"]["prefix.bin"]


def test_intake_metadata_never_reads_or_hashes_ZIP_body(tmp_path,source_corpus,monkeypatch):
    pins,_=_intake(tmp_path,source_corpus);original=m.selector.held_io._HeldCapture.open;opened=[]
    class NeverRead:
        def __init__(self,stream):self.stream=stream
        def read(self,*a,**kw):pytest.fail("ZIPbody read by metadata preflight")
        def __getattr__(self,key):return getattr(self.stream,key)
    def guarded(self,name,cap):
        value=original(self,name,cap);opened.append(name)
        return NeverRead(value) if name.endswith(".zip") else value
    monkeypatch.setattr(m.selector.held_io._HeldCapture,"open",guarded)
    held=m._IntakeMetadata(fixture=True,**pins)
    try:
        held.check();assert len(opened)==84 and len([name for name in opened if name.endswith(".zip")])==82
    finally:held.close()


def test_metadata_hold_matches_genuine_intake_and_detects_later_source_change(tmp_path,source_corpus):
    pins,args=_intake(tmp_path,source_corpus);held=m._IntakeMetadata(fixture=True,**pins);actual=None
    try:
        actual=m.selector._HeldIntake(**args);held.match_genuine(actual)
        leaf=next(pins["root"].glob("*.zip"));leaf.write_bytes(leaf.read_bytes()+b"changed")
        with pytest.raises(ValueError):held.check()
        with pytest.raises(ValueError):held.match_genuine(actual)
    finally:m.selector._close_all((actual,held),phase="invented_test_cleanup")


def test_frozen_geometry_collects_paper_and_complete_NC_but_accounts_partial_and_directory(source_corpus):
    raw,payloads=_prefix(source_corpus);collected,geometry=m._collect(raw,CONTACT,True)
    assert collected==payloads and geometry["examined_physical_ordinals"]==[2,3,4]
    assert geometry["physical_headers_observed"]==5 and geometry["unexamined_physical_members"]==2
    assert geometry["member_dispositions"]==["nonregular_or_extension_not_examined",*["collected_complete_observed_NC_payload"]*3,"partial_physical_payload_not_examined"]
    assert geometry["route_payload_bytes_examined"]==sum(map(len,payloads))
    m._geometry_valid(geometry)
    assert CONTACT.encode() not in m._raw(geometry) and b"PRIVATE" not in m._raw(geometry)


def test_genuine_full25_binder_observation_preserves_all_counts_without_exporting_rows(observation):
    identity,prefix,source,plan,value=observation;m._witness_valid(value,identity,plan,True)
    bound=value["source17_binding"]
    assert bound["source_population_counts"]["context_submission_rows"]==150
    assert bound["private_source17_candidate_count"]==2 and bound["route_batch"]["members"]==3
    assert bound["route_batch"]["disposition_counts"]["unqualified_documented_status"]==1
    assert value["source_rederivation_matches_retained_roster"] is True
    assert value["analysis_SUBMISSION_quarters_rederived"]==25 and value["analysis_opaque_intake_ZIPs_hashed"]==82
    wire=m._raw(value)
    for needle in (CONTACT.encode(),b"PRIVATE BODY",b"9999999999-20-000099",b"0000000001-20-400003",b'"source_rows":',b"raw_issuer_cik"):
        assert needle not in wire
    assert len(wire)<m.MAX_CONTROL and value["authority"]["backtesting_ready"] is False


def test_privacy_in_unselected_partial_payload_stops_before_source_intake(source_corpus,monkeypatch):
    raw,_=_prefix(source_corpus,private=CONTACT.encode());opened=[]
    monkeypatch.setattr(m,"_analysis_intake",lambda:opened.append(True))
    prefix=SimpleNamespace(root=Path("/private/tmp/invented"),pins={"complete.json":"a"*64,"prefix.bin":m._sha(raw)},
        metadata={"original_execution_identity":{}},read_body=lambda:raw,check=lambda:None)
    monkeypatch.setattr(m.capture,"_verify_files",lambda *a,**kw:{"producer_execution_identity":{},"current_contact_prefix_rescreened":True})
    with pytest.raises(ValueError):m._analyse({},CONTACT,prefix,SimpleNamespace(),{},fixture=True)
    assert opened==[]


def test_no_complete_payloads_are_finite_refusal_before_source_body_inputs(monkeypatch):
    writer=zlib.compressobj(level=0,wbits=31);raw=(writer.compress(_member(b"x"*150000))+writer.flush())[:65536]
    prefix=SimpleNamespace(root=Path("/private/tmp/invented"),pins={"complete.json":"a"*64,"prefix.bin":m._sha(raw)},
        metadata={"original_execution_identity":{}},read_body=lambda:raw,check=lambda:None)
    monkeypatch.setattr(m.capture,"_verify_files",lambda *a,**kw:{"producer_execution_identity":{},"current_contact_prefix_rescreened":True})
    monkeypatch.setattr(m,"_analysis_intake",lambda:pytest.fail("no-payload source open"))
    with pytest.raises(m.NCBindingObserveError,match="no_complete_NC_payloads_for_route_batch"):
        m._analyse({},CONTACT,prefix,SimpleNamespace(),{},fixture=True)


@pytest.mark.parametrize("change",["extra","fixture","identity","plan","prefix","complete","authority","rescreen","roster_match","ZIP_count","quarter_count","source_values"])
def test_parent_rejects_outer_witness_laundering(observation,change):
    identity,prefix,source,plan,value=observation;value=copy.deepcopy(value)
    if change=="extra":value["private_unknown"]="NO"
    elif change=="fixture":value["fixture_only"]=False
    elif change=="identity":value["execution_identity"]["head"]="c"*40
    elif change=="plan":value["input_plan_sha256"]="c"*64
    elif change=="prefix":value["original_prefix_sha256"]="c"*64
    elif change=="complete":value["original_prefix_complete_sha256"]="c"*64
    elif change=="authority":value["authority"]["backtesting_ready"]=True
    elif change=="rescreen":value["current_contact_prefix_rescreened"]=False
    elif change=="roster_match":value["source_rederivation_matches_retained_roster"]=False
    elif change=="ZIP_count":value["analysis_opaque_intake_ZIPs_hashed"]=True
    elif change=="quarter_count":value["analysis_SUBMISSION_quarters_rederived"]=24
    else:value["private_claims_rows_and_payloads_not_returned"]=False
    with pytest.raises(ValueError):m._witness_valid(value,identity,plan,True)


@pytest.mark.parametrize("change",["extra","source_count","row_bytes","consumed","eligible","authority","codepins","source_values","rows_partition","route_count"])
def test_parent_rejects_nested_binding_laundering(observation,change):
    identity,_,_,plan,value=observation;value=copy.deepcopy(value);bound=value["source17_binding"]
    if change=="extra":bound["raw_CIK"]="NOT ALLOWED"
    elif change=="source_count":bound["source_population_counts"]["context_submission_rows"]=149
    elif change=="row_bytes":bound["source_accounting"]["source_row_bytes_accounted"]+=1
    elif change=="consumed":bound["source_accounting"]["caller_consumed_accessions"]+=1
    elif change=="eligible":bound["eligible_join_count"]=True
    elif change=="authority":bound["authority"]["canonical_admitted"]=True
    elif change=="codepins":bound["code_dependency_pins"]={}
    elif change=="source_values":bound["source_values_or_value_hashes_exported"]=True
    elif change=="rows_partition":bound["source_accounting"]["rows_without_eligible_route_accessions"]-=1
    else:bound["route_batch"]["members"]+=1
    with pytest.raises(ValueError):m._witness_valid(value,identity,plan,True)


@pytest.mark.parametrize("change",["extra","prefix_size","bool_count","ordinal","unexamined","member_reason","payload_bytes"])
def test_parent_rejects_geometry_accounting_laundering(observation,change):
    identity,_,_,plan,value=observation;value=copy.deepcopy(value);geometry=value["geometry"]
    if change=="extra":geometry["name"]="PRIVATE"
    elif change=="prefix_size":geometry["prefix_bytes"]=1
    elif change=="bool_count":geometry["physical_headers_observed"]=True
    elif change=="ordinal":geometry["examined_physical_ordinals"][0]=True
    elif change=="unexamined":geometry["unexamined_physical_members"]+=1
    elif change=="member_reason":geometry["member_dispositions"][0]="invented_reason"
    else:geometry["route_payload_bytes_examined"]-=1
    with pytest.raises(ValueError):m._witness_valid(value,identity,plan,True)


def test_strict_control_size_canonical_and_duplicate_keys():
    assert m._control(m._raw({"own":1}))=={"own":1}
    for raw in (b'{"x":1,"x":1}',b'{"x":1 }',b"x"*(m.MAX_CONTROL+1)):
        with pytest.raises(ValueError):m._control(raw)


def test_cli_echo_guard_precedes_arguments_and_restores_without_private_text(monkeypatch,capsys):
    seen=[];monkeypatch.setattr(m.contact_io,"_protect_stdin_echo",lambda:seen.append("protected") or "saved")
    monkeypatch.setattr(m.contact_io,"_restore_stdin_echo",lambda saved:seen.append(("restored",saved)))
    assert m.main(["--unexpected","PRIVATE CLI ARGUMENT"])==2
    assert seen==["protected",("restored","saved")] and "PRIVATE" not in capsys.readouterr().out


@pytest.mark.parametrize("preflight",[True,False])
def test_cli_calls_only_selected_front_and_reports_success_status(monkeypatch,capsys,preflight):
    monkeypatch.setattr(m.contact_io,"_protect_stdin_echo",lambda:None);monkeypatch.setattr(m.contact_io,"_restore_stdin_echo",lambda _:None)
    monkeypatch.setattr(m,"preflight_actual",lambda **kw:{"only":"preflight"})
    monkeypatch.setattr(m,"observe_actual",lambda **kw:{"only":"observe"})
    assert m.main(["--expected-head","a"*40,"--preflight-only" if preflight else "--contact-stdin"])==0
    assert ("preflight" if preflight else "observe") in capsys.readouterr().out


def _worker_seams(monkeypatch):
    events=[]
    class Hold:
        metadata={}
        def check(self):events.append("hold_check")
        def close(self):events.append("hold_close")
    class Memory:
        def __init__(self):events.append("memory")
        def check(self):events.append("memory_check")
        def close(self):events.append("memory_close")
    monkeypatch.setattr(m.previous,"_isolated",lambda:events.append("flags"))
    monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:events.append("native"))
    monkeypatch.setattr(m.previous,"_WorkerMemoryGuard",Memory)
    monkeypatch.setattr(m,"_current",lambda _:events.append("current"))
    monkeypatch.setattr(m.capture,"_compile_sources",lambda _:events.append("compile"))
    monkeypatch.setattr(m.inherited.inherited,"_HeldPrefix",lambda _:events.append("prefix") or Hold())
    monkeypatch.setattr(m,"_SourceInputs",lambda _:events.append("source_inputs") or Hold())
    monkeypatch.setattr(m,"_plan_valid",lambda value,identity:value)
    return events


def test_worker_proves_initial_native_compiles_checks_before_any_input(monkeypatch):
    events=_worker_seams(monkeypatch);result=m._worker("preflight",{})
    assert result["ok"] is True
    assert events[:9]==["flags","native","memory","current","compile","current","memory_check","prefix","source_inputs"]
    assert events[-3:]==["hold_close","hold_close","memory_close"]
    assert events[-5:-3]==["current","memory_check"]


@pytest.mark.parametrize("cut",["native","current","compile"])
def test_worker_early_control_refusal_never_opens_private_inputs(monkeypatch,cut):
    events=_worker_seams(monkeypatch)
    def refused(*args):events.append("refused");raise m.NCBindingObserveError("source_changed")
    if cut=="native":monkeypatch.setattr(m.source_runner,"_prove_isolation",refused)
    elif cut=="current":monkeypatch.setattr(m,"_current",refused)
    else:monkeypatch.setattr(m.capture,"_compile_sources",refused)
    if cut=="native":
        with pytest.raises(m.NCBindingObserveError):m._worker("preflight",{})
    else:assert m._worker("preflight",{})["ok"] is False
    assert "prefix" not in events and "source_inputs" not in events


def test_live_memory_guard_spans_stdout_write_flush_final_sample_and_cleanup(monkeypatch):
    events=_worker_seams(monkeypatch)
    class Sink:
        def write(self,raw):events.append("stdout_write");assert raw.endswith(b"\n")
        def flush(self):events.append("stdout_flush")
    monkeypatch.setattr(m.sys,"stdout",SimpleNamespace(buffer=Sink()))
    assert m._worker("preflight",{},publish=True) is None
    index=events.index("stdout_write")
    assert events[index-1:index+4]==["memory_check","stdout_write","stdout_flush","memory_check","hold_close"]
    assert events[-3:]==["hold_close","hold_close","memory_close"]


def test_worker_final_current_source_change_refuses_after_analysis(monkeypatch):
    events=_worker_seams(monkeypatch);calls=[]
    def current(_):
        calls.append(True)
        if len(calls)==3:raise m.NCBindingObserveError("source_changed","final")
    monkeypatch.setattr(m,"_current",current)
    result=m._worker("preflight",{})
    assert result=={"ok":False,"refusal":{"phase":"final","code":"source_changed"}}
    assert events[-3:]==["hold_close","hold_close","memory_close"]


def test_worker_cleanup_drains_every_hold_even_if_one_close_fails(monkeypatch):
    events=_worker_seams(monkeypatch)
    class Bad:
        metadata={}
        def check(self):pass
        def close(self):events.append("bad_close");raise RuntimeError("private cleanup detail")
    monkeypatch.setattr(m,"_SourceInputs",lambda _:Bad())
    with pytest.raises(ValueError):m._worker("preflight",{})
    assert events[-3:]==["bad_close","hold_close","memory_close"]


def test_parent_preflight_rechecks_identity_after_native_and_original_proofs(monkeypatch):
    calls=[];identity={"head":"a"*40}
    def current(_):calls.append("identity");return identity if calls.count("identity")==1 else {"head":"b"*40}
    monkeypatch.setattr(m,"_identity",current);monkeypatch.setattr(m,"_child",lambda *a: calls.append("child") or {})
    monkeypatch.setattr(m,"_plan_valid",lambda value,identity:value);monkeypatch.setattr(m,"_parent_proofs",lambda _:calls.append("producer_Git"))
    with pytest.raises(m.NCBindingObserveError,match="source_changed"):m._preflight("a"*40)
    assert calls==["identity","child","producer_Git","identity"]


def test_child_command_is_initially_native_and_finite_no_credentials_or_actual_calls():
    command=m._command("preflight",{});joined=" ".join(command)
    for needle in ("deny network*","deny process-fork","deny file-write*",'deny process-exec (literal "/usr/bin/security")',"-I","-S","-B"):
        assert needle in joined
    assert "env" in command[0] and "-i" in command


@pytest.mark.parametrize("phase",["PRIVATE phase",["PRIVATE phase"]])
def test_malformed_typed_error_phase_is_not_exported(phase):
    error=m.NCBindingObserveError("source_changed");error.phase=phase
    safe=m._safe(error,"source")
    assert safe=={"phase":"source","code":"metadata_refused"}


def test_only_whitelisted_static_binder_codes_survive_finite_error_boundary():
    assert m._safe(m.binder.NCSourceBindingError("complete_source_callback_accounting_refused"),"source17")=={
        "phase":"source17","code":"complete_source_callback_accounting_refused"}
    assert m._safe(m.binder.NCSourceBindingError("PRIVATE SOURCE DETAIL"),"source17")=={"phase":"source17","code":"source17_refused"}
