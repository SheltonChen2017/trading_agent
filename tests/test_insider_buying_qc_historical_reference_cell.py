"""Invented SDK/DataFrames only; no real QC, credential or artifact access."""
import ast
import contextlib
import copy
from datetime import datetime
import io
import json
import os
import sys
import types

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("fcntl",reason="macOS/POSIX custody")
pytest.importorskip("termios",reason="macOS/POSIX custody")
from research import insider_buying_qc_historical_reference_cell as m


NONCE,PRIVATE="d"*64,"invented-SDK-private-message"


class SID:
    def __init__(self,value):self.value,self.security_type=value,"Equity"
    def __str__(self):return self.value
    @staticmethod
    def parse(value):return SID(value)


class Symbol:
    def __init__(self,sid,value="INVENTED"):
        self.id,self.value,self.security_type=(SID(sid) if type(sid) is str else sid),value,"Equity"


class Store:
    def __init__(self):self.values,self.events,self.fail={},[],None
    def contains_key(self,key):
        self.events.append(("contains",key));return self.fail=="existing" or key in self.values
    def save(self,key,text):
        self.events.append(("save",key));print(PRIVATE)
        if self.fail=="save_false":return False
        if self.fail=="save_nonbool":return 1
        if self.fail=="save_exception":raise RuntimeError(PRIVATE)
        self.values[key]=text;return True
    def read(self,key):
        self.events.append(("read",key));print(PRIVATE,file=sys.stderr)
        if self.fail=="read_exception":raise RuntimeError(PRIVATE)
        if self.fail=="read_mismatch":return '{}'
        return self.values[key]
    def __getattr__(self,name):raise AssertionError("forbidden SDK member "+name)


def install(monkeypatch,qb,*,fail_factory=False):
    package,research=types.ModuleType("QuantConnect"),types.ModuleType("QuantConnect.Research")
    package.__path__=[];package.Symbol=Symbol;package.SecurityIdentifier=SID;package.SecurityType=types.SimpleNamespace(EQUITY="Equity")
    def factory():
        print(PRIVATE);print(PRIVATE,file=sys.stderr)
        if fail_factory:raise RuntimeError(PRIVATE)
        return qb
    research.QuantBook=factory;package.Research=research
    monkeypatch.setitem(sys.modules,"QuantConnect",package);monkeypatch.setitem(sys.modules,"QuantConnect.Research",research)


def context(monkeypatch,*,resolve=None):
    """Run genuine old capture+new consumer against invented in-memory SDK."""
    namespace={};store=Store();qb=types.SimpleNamespace(project_id=m.PROJECT_ID,object_store=store);called=[]
    def cik(value,*,trading_date):
        called.append(value)
        return [Symbol("CLOUD-SID-"+str(value))] if resolve is None else resolve(value,len(called))
    qb.cik=cik;install(monkeypatch,qb)
    exec(m.producer.CORE_SOURCE,namespace)
    r=m.producer._registration(m.consumer.PRODUCER_NONCE,True);text=m._raw(r).decode()
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        namespace["_ib_cik_run"](lambda:(qb,Symbol,"Equity"),text,m._sha(text.encode()))
        _,cell=m.consumer.build_invented_cell("e"*64);exec(cell,namespace)
    assert len(called)==51 and "_ib_cik_retained_"+m.consumer.PRODUCER_NONCE in namespace
    store.events.clear();return namespace,store


def execute(monkeypatch,*,namespace=None,store=None,resolve=None,frame=None,project=m.PROJECT_ID,fail_factory=False,cell=None):
    if namespace is None:namespace,store=context(monkeypatch,resolve=resolve)
    store=Store() if store is None else store
    calls=[]
    class QB:
        project_id=project
        object_store=store
        def get_fundamental(self,symbols,selector,start,end):
            print(PRIVATE);print(PRIVATE,file=sys.stderr);calls.append((symbols,selector,start,end));store.events.append(("query",selector))
            assert start==end==datetime(2021,3,31) and selector==m.SELECTORS[len(calls)-1]
            prefix=f"{m.PROJECT_ID}/{m.AUDIT_ID}/{NONCE}/{len(calls):02d}-started.json"
            assert store.events[-3:-1]==[("save",prefix),("read",prefix)]
            if frame is not None:return frame(symbols,selector,len(calls))
            value=False if selector==m.SELECTORS[3] else "ACTIVE" if selector!=m.SELECTORS[0] else "0000006281"
            return pd.DataFrame({str(symbol.id):[value] for symbol in symbols},index=[pd.Timestamp("2021-03-31")])
        def __getattr__(self,name):raise AssertionError("forbidden SDK member "+name)
    install(monkeypatch,QB(),fail_factory=fail_factory)
    registration,generated=m.build_invented_cell(NONCE);out,err=io.StringIO(),io.StringIO()
    with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):exec(generated if cell is None else cell,namespace)
    raw=out.getvalue().encode()
    assert not err.getvalue() and len(raw.splitlines())==1 and PRIVATE.encode() not in raw and b"CLOUD-SID" not in raw
    return m.validate_acknowledgement(raw,registration_raw=registration),raw,store,calls,namespace


def test_true_generated_four_batch_calls_only_exact_SID_columns_and_date(monkeypatch):
    ack,raw,store,calls,namespace=execute(monkeypatch)
    assert ack["disposition"]=="historical_reference_receipts_completed" and ack["own_final_receipt_acknowledged"] is True
    assert len(calls)==4 and all(len(call[0])==51 for call in calls)
    assert [call[1] for call in calls]==list(m.SELECTORS)
    assert all(event[0]=="contains" for event in store.events[:11])
    own=[event for event in store.events if event[0] in {"contains","save","read"}]
    assert all(f"/{m.AUDIT_ID}/{NONCE}/" in event[1] for event in own)
    assert sum(event[0]=="save" for event in own)==sum(event[0]=="read" for event in own)==10
    retained=namespace["_ib_historical_reference_retained_"+NONCE]
    primary=retained["results"][3]["observations"]
    assert all(row["reference"]=={"state":"declared_value","kind":"boolean","value":False} for row in primary)
    assert len(retained["start"]["candidate_edges"])==51 and retained["final"]["authority"]["point_in_time_verified"] is False
    stamp=retained["results"][0]["returned_index"][0]
    assert stamp["timezone_label"]=="naive-unqualified" and stamp["record_Time_or_EndTime_not_exposed_by_dataframe"] is True
    for field in ("candidate_edges","ordered_sids","observations","reference","query_result_sha256","attempted_selectors"):
        assert ('"'+field+'":').encode() not in raw


def test_current_public_getter_endtime_Tplus1_is_preserved_not_rewritten_as_availability(monkeypatch):
    def frame(symbols,selector,index):
        return pd.DataFrame({str(symbol.id):[False if index==4 else "declared"] for symbol in symbols},index=[pd.Timestamp("2021-04-01")])
    ack,_,_,calls,namespace=execute(monkeypatch,frame=frame)
    assert len(calls)==4 and ack["own_final_receipt_acknowledged"] is True
    retained=namespace["_ib_historical_reference_retained_"+NONCE]
    assert all(result["returned_index"][0]["returned_index_isoformat"]=="2021-04-01T00:00:00" for result in retained["results"])
    assert all(result["returned_index"][0]["availability_before_entry_verified"] is False for result in retained["results"])
    assert all(result["authority"]["point_in_time_verified"] is False for result in retained["results"])


def test_submicrosecond_timestamp_is_not_midnight_and_stops_first_query(monkeypatch):
    def frame(symbols,selector,index):
        return pd.DataFrame({str(symbol.id):[False if index==4 else "declared"] for symbol in symbols},index=[pd.Timestamp("2021-04-01T00:00:00.000000001")])
    ack,_,_,calls,_=execute(monkeypatch,frame=frame)
    assert len(calls)==1 and ack["stop_stage"]=="reference_shape" and ack["own_final_receipt_acknowledged"] is False


def test_duplicate_many_to_many_and_zero_source_rows_preserved_not_primary_filtered(monkeypatch):
    def resolve(value,index):
        return [] if index==1 else [Symbol("SHARED"),Symbol("SHARED")] if index==2 else [Symbol("SHARED")]
    ack,_,_,calls,namespace=execute(monkeypatch,resolve=resolve)
    assert ack["own_final_receipt_acknowledged"] and all(len(call[0])==1 for call in calls)
    retained=namespace["_ib_historical_reference_retained_"+NONCE]
    assert len(retained["start"]["candidate_edges"])==51
    assert len(namespace["_ib_cik_retained_"+m.consumer.PRODUCER_NONCE])==51


@pytest.mark.parametrize("fault",("missing_rows","missing_consumer","missing_old_marker","row_order","row_extra","row_hash","too_many","value_alias","all_zero"))
def test_missing_reset_or_unqualified_context_has_zero_queries_and_zero_cloud_operations(monkeypatch,fault):
    namespace,store=context(monkeypatch,resolve=(lambda value,index:[]) if fault=="all_zero" else None)
    key="_ib_cik_retained_"+m.consumer.PRODUCER_NONCE
    if fault=="missing_rows":namespace.pop(key)
    elif fault=="missing_consumer":namespace.pop("_ib_cik_new_consumer_"+"e"*64)
    elif fault=="missing_old_marker":namespace.pop("_ib_cik_consume_"+m.consumer.PRODUCER_NONCE)
    elif fault=="row_order":namespace[key][0],namespace[key][1]=namespace[key][1],namespace[key][0]
    elif fault=="row_extra":namespace[key][0]["private"]="not forwarded"
    elif fault=="row_hash":namespace[key][0]["lookup_started_sha256"]="f"*64
    elif fault=="too_many":namespace[key][0]["candidates"]*=17
    elif fault=="value_alias":
        namespace[key][1]["candidates"][0]["sid"]=namespace[key][0]["candidates"][0]["sid"]
        namespace[key][1]["candidates"][0]["symbol_value"]="CONFLICTING-ALIAS"
    ack,_,_,calls,_=execute(monkeypatch,namespace=namespace,store=store)
    assert ack["stop_stage"]=="retained_context" and calls==store.events==[]
    assert ack["own_error_receipt_acknowledged"] is False


@pytest.mark.parametrize("project",(True,37465795.0,"37465795",37465796,None))
def test_wrong_project_has_no_queries_or_cloud_keys(monkeypatch,project):
    ack,_,store,calls,_=execute(monkeypatch,project=project)
    assert ack["stop_stage"]=="project" and calls==store.events==[]


def test_factory_failure_is_sanitized_before_any_cloud_action(monkeypatch):
    ack,_,store,calls,_=execute(monkeypatch,fail_factory=True)
    assert ack["stop_stage"]=="construct" and calls==store.events==[]


@pytest.mark.parametrize("fault",("parse_exception","sid_roundtrip","security_type","symbol_value"))
def test_original_saved_sid_reconstruction_must_roundtrip_before_cloud_start(monkeypatch,fault):
    namespace,store=context(monkeypatch)
    if fault=="parse_exception":monkeypatch.setattr(SID,"parse",lambda _:(_ for _ in ()).throw(ValueError(PRIVATE)))
    elif fault=="sid_roundtrip":monkeypatch.setattr(SID,"parse",lambda value:SID("changed"))
    elif fault=="security_type":
        def parse(value):result=SID(value);result.security_type="Option";return result
        monkeypatch.setattr(SID,"parse",parse)
    else:
        old=Symbol.__init__
        def init(self,*args):old(self,*args);self.value="today's replacement"
        monkeypatch.setattr(Symbol,"__init__",init)
    ack,_,_,calls,_=execute(monkeypatch,namespace=namespace,store=store)
    assert ack["stop_stage"]=="symbol_reconstruction" and calls==store.events==[]


@pytest.mark.parametrize("fault",("existing","save_false","save_nonbool","save_exception","read_exception","read_mismatch"))
def test_store_refusal_never_queries_or_reconstructs_old_receipts(monkeypatch,fault):
    namespace,store=context(monkeypatch);store.fail=fault
    ack,_,_,calls,_=execute(monkeypatch,namespace=namespace,store=store)
    assert calls==[] and ack["own_final_receipt_acknowledged"] is False
    assert ack["stop_stage"]==("key_precheck" if fault=="existing" else "start_readback" if fault.startswith("read") else "start_save")


@pytest.mark.parametrize("fault",("ticker_columns","native_symbol_column","duplicate_columns","two_dates","next_date","nonframe","unknown_value","nonbool_primary","exception"))
def test_bad_historical_shape_stops_one_attempt_without_fallback_or_next_selector(monkeypatch,fault):
    def frame(symbols,selector,index):
        ids=[str(symbol.id) for symbol in symbols]
        if fault=="exception":raise RuntimeError(PRIVATE)
        if fault=="nonframe":return {"private":"not a dataframe"}
        if fault=="ticker_columns":return pd.DataFrame({"INVENTED":["value"]},index=[pd.Timestamp("2021-03-31")])
        if fault=="native_symbol_column":return pd.DataFrame({symbols[0]:["value"]},index=[pd.Timestamp("2021-03-31")])
        if fault=="duplicate_columns":return pd.DataFrame([["a","b"]],columns=[ids[0],ids[0]],index=[pd.Timestamp("2021-03-31")])
        if fault=="two_dates":return pd.DataFrame({ids[0]:["a","b"]},index=[pd.Timestamp("2021-03-31")]*2)
        if fault=="next_date":return pd.DataFrame({ids[0]:["a"]},index=[pd.Timestamp("2021-04-02")])
        value=object() if fault=="unknown_value" else (1 if selector==m.SELECTORS[3] else "value")
        return pd.DataFrame({sid:[value] for sid in ids},index=[pd.Timestamp("2021-03-31")])
    ack,_,store,calls,_=execute(monkeypatch,frame=frame)
    assert len(calls)==(4 if fault=="nonbool_primary" else 1) and ack["own_final_receipt_acknowledged"] is False
    assert ack["stop_stage"]==("reference_query" if fault=="exception" else "reference_shape")
    assert ack["own_error_receipt_acknowledged"] is True
    error=json.loads(store.values[f"{m.PROJECT_ID}/{m.AUDIT_ID}/{NONCE}/error.json"])
    assert error["unattempted_selectors"]==list(m.SELECTORS[len(calls):])


def test_empty_missing_and_nullable_reference_values_are_preserved_without_absence_claim(monkeypatch):
    def frame(symbols,selector,index):
        ids=[str(symbol.id) for symbol in symbols]
        if index==1:return pd.DataFrame(columns=ids)
        if index==2:return pd.DataFrame({ids[0]:[None]},index=[pd.Timestamp("2021-03-31",tz="UTC")])
        return pd.DataFrame({sid:[pd.NA if index==3 else pd.NaT] for sid in ids},index=[pd.Timestamp("2021-03-31")])
    ack,_,_,_,namespace=execute(monkeypatch,frame=frame)
    assert ack["own_final_receipt_acknowledged"] is True
    results=namespace["_ib_historical_reference_retained_"+NONCE]["results"]
    assert {v["reference"]["state"] for v in results[0]["observations"]}=={"no_record_returned"}
    assert results[1]["observations"][0]["reference"]["state"]=="missing_value"
    assert results[1]["observations"][1]["reference"]["state"]=="column_not_returned"
    assert results[1]["returned_index"][0]["returned_index_isoformat"].endswith("+00:00")
    assert all(result["authority"]["historical_absence_proven"] is False for result in results)


def test_maximum_512_edges_and_escaped_metadata_fit_registered_bounds(monkeypatch):
    def resolve(value,index):
        if index>32:return []
        return [Symbol((f"SID-{index:02d}-{n:02d}-"+'\\"'*512)[:512],value='\\"'*64) for n in range(16)]
    def frame(symbols,selector,index):
        return pd.DataFrame({str(symbol.id):[False if index==4 else '\\"'*32] for symbol in symbols},index=[pd.Timestamp("2021-03-31")])
    ack,_,store,calls,namespace=execute(monkeypatch,resolve=resolve,frame=frame)
    assert ack["own_final_receipt_acknowledged"] and len(calls)==4 and len(calls[0][0])==512
    own=[text.encode() for key,text in store.values.items() if f"/{m.AUDIT_ID}/" in key]
    assert len(own)==10 and max(map(len,own))<=2097152 and sum(map(len,own))<=8388608
    assert len(namespace["_ib_historical_reference_retained_"+NONCE]["start"]["candidate_edges"])==512


def test_source_context_mutation_during_query_cannot_complete(monkeypatch):
    namespace,store=context(monkeypatch)
    def frame(symbols,selector,index):
        if index==4:namespace["_ib_cik_retained_"+m.consumer.PRODUCER_NONCE][0]["candidates"][0]["symbol_value"]="mutated"
        return pd.DataFrame({str(symbol.id):[False if index==4 else "value"] for symbol in symbols},index=[pd.Timestamp("2021-03-31")])
    ack,_,_,calls,_=execute(monkeypatch,namespace=namespace,store=store,frame=frame)
    assert len(calls)==4 and ack["stop_stage"]=="context_recheck" and not ack["own_final_receipt_acknowledged"]


@pytest.mark.parametrize("fault",("rows","consumer_marker","old_marker"))
def test_early_context_mutation_stops_after_first_call_before_any_next_query(monkeypatch,fault):
    namespace,store=context(monkeypatch)
    def frame(symbols,selector,index):
        if index==1:
            if fault=="rows":namespace["_ib_cik_retained_"+m.consumer.PRODUCER_NONCE][0]["candidates"][0]["symbol_value"]="mutated"
            elif fault=="consumer_marker":namespace["_ib_cik_new_consumer_"+"e"*64]=False
            else:namespace["_ib_cik_consume_"+m.consumer.PRODUCER_NONCE]=False
        return pd.DataFrame({str(symbol.id):[False if index==4 else "declared"] for symbol in symbols},index=[pd.Timestamp("2021-04-01")])
    ack,_,_,calls,_=execute(monkeypatch,namespace=namespace,store=store,frame=frame)
    assert len(calls)==1 and ack["stop_stage"]=="context_recheck" and ack["own_final_receipt_acknowledged"] is False


def test_second_execution_never_repeats_any_cloud_action(monkeypatch):
    _,_,store,_,namespace=execute(monkeypatch);store.events.clear()
    ack,_,_,calls,_=execute(monkeypatch,namespace=namespace,store=store)
    assert ack["stop_stage"]=="kernel_claim" and calls==store.events==[]


@pytest.mark.parametrize("field,bad",(("fixture_only",False),("project_id",True),("execution_notebook","research.ipynb"),("execution_cell_index",0),
    ("core_sha256","a"*64),("source_provenance",{}),("scope",{})))
def test_coherent_bad_registration_refuses_before_context_or_factory(field,bad):
    registration,_=m.build_invented_cell(NONCE);r=json.loads(registration);r[field]=bad;text=m._raw(r).decode()
    namespace={};exec(m._core(True),namespace);out=io.StringIO()
    with contextlib.redirect_stdout(out):namespace["_ib_historical_reference_run"](lambda:pytest.fail("no SDK"),text,m._sha(text.encode()),m._sha(m._core(True).encode()))
    assert json.loads(out.getvalue())=={"schema":m.SCHEMA+"/acknowledgement","disposition":"registration_refused"}


@pytest.mark.parametrize("field,bad",(("execution_notebook",m.producer.NOTEBOOK),("execution_cell_index",0),("own_final_receipt_acknowledged",1),
    ("own_error_receipt_acknowledged",True),("platform_values_counts_or_digests_exported",True),("stop_stage","private exception")))
def test_external_ack_has_no_dynamic_platform_counts_or_false_completion(monkeypatch,field,bad):
    ack,_,_,_,_=execute(monkeypatch);ack[field]=bad;registration,_=m.build_invented_cell(NONCE)
    with pytest.raises(m.HistoricalReferenceError):m.validate_acknowledgement(m._raw(ack),registration_raw=registration)


@pytest.mark.parametrize("bad_stage",([],{}))
def test_generated_refusal_ack_unhashable_stage_has_finite_classification(monkeypatch,bad_stage):
    def frame(symbols,selector,index):
        return pd.DataFrame({str(symbols[0].id):[object()]},index=[pd.Timestamp("2021-03-31")])
    ack,_,_,calls,_=execute(monkeypatch,frame=frame)
    assert len(calls)==1 and ack["disposition"]=="refused_no_retry"
    assert ack["stop_stage"]=="reference_shape" and ack["own_error_receipt_acknowledged"] is True
    registration,_=m.build_invented_cell(NONCE);ack["stop_stage"]=bad_stage
    with pytest.raises(m.HistoricalReferenceError,match="reference_ack_refusal_state"):
        m.validate_acknowledgement(m._raw(ack),registration_raw=registration)


def test_private_fresh_intent_and_full_roster_precede_returned_cell(tmp_path):
    path=tmp_path.joinpath(*m.ARTIFACT_PARTS);called=[]
    def proof(identity):assert not path.exists();called.append(1);return m._proof(identity,True)
    result=m.prepare_invented_cell(tmp_path,preflight=proof);assert called==[1]
    assert {p.name for p in path.iterdir()}=={"scope.lock","registration.json","cell.py","intent.json","ready.json"}
    intent=json.loads((path/"intent.json").read_bytes());assert len(intent["execution_identity"]["source_sha256"])==110
    assert intent["cell_sha256"]==m._sha(result["cell_source"].encode()) and intent["no_retry_even_after_kernel_reset"] is True
    assert all(p.stat().st_mode&0o777==0o600 for p in path.iterdir())
    with pytest.raises((OSError,ValueError)):m.prepare_invented_cell(tmp_path)


def test_new_scope_targets_only_fresh_cell1_of_existing_consumer_notebook(tmp_path):
    result=m.prepare_invented_cell(tmp_path);path=tmp_path.joinpath(*m.ARTIFACT_PARTS)
    registration=json.loads((path/"registration.json").read_bytes());intent=json.loads((path/"intent.json").read_bytes())
    assert m.NOTEBOOK==m.consumer.NOTEBOOK=="ib_qc_cik_consumer_20261025.ipynb"
    assert all(value["execution_cell_index"]==1 and value["execution_notebook"]==m.consumer.NOTEBOOK for value in (registration,intent,result))
    assert m.consumer.NOTEBOOK!=m.producer.NOTEBOOK


def test_preflight_failure_creates_no_nonce_or_namespace(tmp_path,monkeypatch):
    original=m._cell;seen=[]
    def cell(nonce,*args):seen.append(nonce);return original(nonce,*args)
    monkeypatch.setattr(m,"_cell",cell)
    with pytest.raises(m.HistoricalReferenceError):m.prepare_invented_cell(tmp_path,preflight=lambda _:(_ for _ in ()).throw(m.HistoricalReferenceError("invented")))
    assert seen==["0"*64] and not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_failed_intent_write_preserves_permanent_namespace(tmp_path,monkeypatch):
    original=m.publication._NewDirectory.publish
    def publish(self,name,raw,**kwargs):
        if name=="intent.json":raise m.HistoricalReferenceError("invented")
        return original(self,name,raw,**kwargs)
    monkeypatch.setattr(m.publication._NewDirectory,"publish",publish)
    with pytest.raises(m.HistoricalReferenceError):m.prepare_invented_cell(tmp_path)
    assert {p.name for p in tmp_path.joinpath(*m.ARTIFACT_PARTS).iterdir()}=={"scope.lock","registration.json","cell.py"}


def test_actual_front_requires_initial_isolation_before_source_or_input(monkeypatch):
    monkeypatch.setattr(m.sys,"pycache_prefix","wrong");monkeypatch.setattr(m,"_identity",lambda _:pytest.fail("no actual reads"))
    with pytest.raises(m.HistoricalReferenceError):m.prepare_actual_cell("a"*40)


def test_native_worker_order_and_strict_native_result(monkeypatch):
    identity=m._invented_identity(m.LANE_ROOT);events=[]
    monkeypatch.setattr(m,"_isolated",lambda:events.append("flags"));monkeypatch.setattr(m.sources,"_prove_isolation",lambda:events.append("native"))
    monkeypatch.setattr(m,"_current",lambda _:events.append("source"));monkeypatch.setattr(m,"_capacity",lambda *args:events.append("capacity"))
    assert m._worker(identity)==m._proof(identity,False) and events==["flags","native","source","capacity","source"]
    def launch(command,**kwargs):
        policy=command[command.index("-p")+1]
        assert all(rule in policy for rule in ("deny network*","deny process-fork","deny file-write*","/usr/bin/security"))
        assert command[:2]==("/usr/bin/env","-i") and all(flag in command for flag in ("-I","-S","-B"))
        assert "_git(" not in command[-1]
        return types.SimpleNamespace(returncode=0,stderr=b"",stdout=m._raw(m._proof(identity,False))+b"\n")
    monkeypatch.setattr(m.sources.launcher,"run_child",launch);m._source_preflight(identity)
    monkeypatch.setattr(m.sources.launcher,"run_child",lambda *a,**k:types.SimpleNamespace(returncode=0,stderr=b"foreign",stdout=b"{}\n"))
    with pytest.raises(m.HistoricalReferenceError):m._source_preflight(identity)


def test_genuine_shaped_source_roster_requires_current_Git_and_old_image_proofs(monkeypatch):
    names=(m.SELF_PATH,m.TEST_PATH,m.consumer.SELF_PATH,m.consumer.TEST_PATH,m.producer.SELF_PATH,m.producer.TEST_PATH,"data/hashing.py","ml/immutable_io.py")
    bodies={name:(m.LANE_ROOT/name).read_bytes() for name in names};hashes={name:m._sha(raw) for name,raw in bodies.items()}
    value={"root":str(m.LANE_ROOT),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,"source_sha256":hashes,"source_inventory_sha256":m._sha(m._raw(hashes))}
    monkeypatch.setattr(m.sources.custody,"_identity",lambda _:copy.deepcopy(value));monkeypatch.setattr(m.sources.custody,"_internal_source_paths",lambda _:names)
    monkeypatch.setattr(m.sources.custody,"_source_bytes",lambda root,requested:m.sources.FROZEN if tuple(requested)==tuple(m.sources.FROZEN) else {name:hashes[name] for name in requested})
    seen=[]
    def git(root,op,target):seen.append(target);return bodies[target.split(":",1)[1]]
    monkeypatch.setattr(m.sources.custody,"_git",git);assert m._identity("a"*40)==value
    assert any(name.startswith(m.CONSUMER_HEAD+":") for name in seen) and any(name.startswith(m.consumer.PRODUCER_HEAD+":") for name in seen)
    monkeypatch.setattr(m.sources.custody,"_git",lambda *a:b"changed")
    with pytest.raises(m.HistoricalReferenceError):m._identity("a"*40)


def test_scope_and_AST_exclude_every_outcome_and_repeated_resolver_path():
    _,cell=m.build_invented_cell(NONCE);tree=ast.parse(cell)
    forbidden={"cik","history","add_equity","add_security","fundamentals","download","delete","create_backtest","create_compile","keys","get_fundamental_universe"}
    calls={node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
    assert not calls&forbidden and "get_fundamental" in calls
    assert m._scope()["old_receipt_reads"]==m._scope()["resolver_calls"]==0 and len(m.SELECTORS)==4


def test_CLI_never_echoes_unknown_private_argument(capsys):
    with pytest.raises(SystemExit):m.main(["--expected-head","a"*40,"--private",PRIVATE])
    output=capsys.readouterr();assert output.err=="reference_argument_refused\n" and PRIVATE not in output.out+output.err
