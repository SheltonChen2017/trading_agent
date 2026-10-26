"""Invented SDK/control receipts only; never QC, credentials or actual artifacts."""
import ast
import contextlib
import copy
from datetime import datetime
import io
import json
import os
import sys
import types

import pytest

pytest.importorskip("fcntl", reason="macOS/POSIX custody")
pytest.importorskip("termios", reason="macOS/POSIX custody")
from research import insider_buying_qc_cik_candidate_cell as m


NONCE, PRIVATE = "a"*64, "invented-SDK-private-message-never-output"


class Symbol:
    def __init__(self, sid, value="INVENTED", security_type="Equity"):
        self.id, self.value, self.security_type = sid, value, security_type


class Store:
    def __init__(self, *, fail=None):
        self.values, self.events, self.fail = {}, [], fail
    def contains_key(self, key):
        self.events.append(("contains",key))
        return self.fail == "existing" or key in self.values
    def save(self, key, text):
        self.events.append(("save",key)); print(PRIVATE)
        if self.fail == "save_false": return False
        if self.fail == "save_nonbool": return 1
        if self.fail == "save_exception": raise RuntimeError(PRIVATE)
        self.values[key] = text
        return True
    def read(self, key):
        self.events.append(("read",key))
        if self.fail == "read_exception": raise RuntimeError(PRIVATE)
        if self.fail == "read_mismatch": return '{}'
        return self.values[key]
    def __getattr__(self,name):
        raise AssertionError("forbidden SDK member:"+name)


def execute(monkeypatch, *, store=None, resolve=None, consume=False, namespace=None,
            project=m.PROJECT_ID, fail_factory=False, cell=None):
    store = Store() if store is None else store
    qb = types.SimpleNamespace(project_id=project,object_store=store)
    calls=[]
    def cik(value, *, trading_date):
        calls.append((value,trading_date));store.events.append(("cik",value));print(PRIVATE,file=sys.stderr)
        assert trading_date == datetime(2021,3,31)
        assert value == int(m.CIKS[len(calls)-1])
        # Corresponding own started receipt must already be saved AND read.
        key=f"{m.PROJECT_ID}/{m.AUDIT_ID}/{NONCE}/{len(calls):03d}-started.json"
        assert store.events[-3:-1] == [("save",key),("read",key)]
        if consume: pytest.fail("retained receipt consumption MUST NOT repeat a resolver call")
        return [Symbol("PRIVATE-SID-"+str(value))] if resolve is None else resolve(value,len(calls))
    qb.cik=cik
    package,research=types.ModuleType("QuantConnect"),types.ModuleType("QuantConnect.Research")
    package.__path__=[];package.Symbol=Symbol;package.SecurityType=types.SimpleNamespace(EQUITY="Equity")
    def factory():
        print(PRIVATE);print(PRIVATE,file=sys.stderr)
        if fail_factory:raise RuntimeError(PRIVATE)
        return qb
    research.QuantBook=factory;package.Research=research
    monkeypatch.setitem(sys.modules,"QuantConnect",package);monkeypatch.setitem(sys.modules,"QuantConnect.Research",research)
    registration,generated=m.build_invented_cell(NONCE,consume=consume)
    namespace={} if namespace is None else namespace
    out,err=io.StringIO(),io.StringIO()
    with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
        exec(generated if cell is None else cell,namespace)
    raw=out.getvalue().encode()
    assert err.getvalue()=="" and PRIVATE.encode() not in raw and b"PRIVATE-SID" not in raw
    assert len(raw.splitlines())==1
    ack=m.validate_acknowledgement(raw,registration_raw=registration,consume=consume)
    return ack,raw,store,calls,namespace


def test_exact_full_source_inputs_and_true_generated_capture(monkeypatch):
    assert len(m.CIKS)==len(set(m.CIKS))==51 and tuple(sorted(m.CIKS))==m.CIKS
    assert all(len(c)==10 and c.isascii() and c.isdigit() and int(c)>0 for c in m.CIKS)
    assert m.SOURCE_PROVENANCE["assessment_sha256"]=="f0a2cac2773c6b79b2d82c4e82264009ec8ce52189c77d0dbd7d0e56cf2d842f"
    ack,raw,store,calls,_=execute(monkeypatch)
    assert len(calls)==51 and ack["resolver_calls_attempted"]==ack["resolver_calls_completed"]==51
    assert ack["own_key_prechecks"]==105 and ack["own_receipt_saves"]==ack["own_receipt_reads"]==104
    assert ack["cloud_receipt_chain_complete"] is True and ack["stop_stage"] is None
    assert ack["platform_values_counts_or_digests_exported"] is ack["backtesting_ready"] is False
    assert len(store.values)==104 and all("error.json" not in key for key in store.values)
    assert all(event[0]=="contains" for event in store.events[:105])
    final=json.loads(store.values[f"{m.PROJECT_ID}/{m.AUDIT_ID}/{NONCE}/final.json"])
    assert final["candidate_rows"]==51 and final["zero_result_rows"]==0
    assert final["authority"]["point_in_time_verified"] is False
    for name in ("candidate_rows","zero_result_rows","shared_sid_groups","result_sha256"):
        assert name.encode() not in raw


def test_cloud_only_zero_duplicate_and_many_to_one_do_not_become_identity_proof(monkeypatch):
    def resolve(value,index):
        if index==1:return []
        return [Symbol("SHARED-SID"),Symbol("SHARED-SID")] if index==2 else [Symbol("SHARED-SID")]
    ack,raw,store,_,_=execute(monkeypatch,resolve=resolve)
    prefix=f"{m.PROJECT_ID}/{m.AUDIT_ID}/{NONCE}"
    row1,row2=(json.loads(store.values[f"{prefix}/{n:03d}-result.json"]) for n in (1,2))
    final=json.loads(store.values[prefix+"/final.json"])
    assert row1["resolver_returned_zero"] is True and row1["authority"]["historical_absence_proven"] is False
    assert row2["duplicate_sids"]==["SHARED-SID"] and len(row2["candidates"])==2
    assert final["shared_sid_groups"]==[{"sid":"SHARED-SID","cik_ordinals":list(range(2,52))}]
    assert ack["cloud_receipt_chain_complete"] is True and b"SHARED-SID" not in raw


def test_maximum_legal_escaped_metadata_fits_explicit_receipt_capacity(monkeypatch):
    def resolve(value,index):
        if index>32:return []
        group=(index-1)//2
        return [Symbol((f"GROUP-{group:03d}-{n:02d}-"+'\\"'*512)[:512],value='\\"'*64) for n in range(16)]
    ack,_,store,calls,_=execute(monkeypatch,resolve=resolve)
    assert len(calls)==51 and ack["resolver_calls_completed"]==51
    assert ack["cloud_receipt_chain_complete"] is True
    prefix=f"{m.PROJECT_ID}/{m.AUDIT_ID}/{NONCE}"
    assert 256*1024<len(store.values[prefix+"/final.json"].encode())<=512*1024
    assert sum(len(raw.encode()) for raw in store.values.values())<2*1024*1024
    assert len([key for key in store.values if key.endswith("-result.json")])==51


def test_deliberately_injected_unsupported_final_payload_refuses_at_final_stage(monkeypatch):
    # Not a supported native shape: deliberately inject a >512KiB own fixture
    # field, keeping a separately hashed fixture-only source image. No actual
    # or foreign codec cap is changed and no production operation is run.
    anchor='"candidate_rows":sum(len(row["candidates"]) for row in rows),'
    assert m.CORE_SOURCE.count(anchor)==1
    altered=m.CORE_SOURCE.replace(anchor,'"unsupported_fixture_payload":"X"*600000,'+anchor,1)
    monkeypatch.setattr(m,"CORE_SOURCE",altered);monkeypatch.setattr(m,"CORE_SHA256",m._sha(altered.encode()))
    ack,_,store,calls,_=execute(monkeypatch)
    assert len(calls)==51 and ack["resolver_calls_completed"]==51
    assert ack["disposition"]=="refused_no_retry" and ack["stop_stage"]=="final_save"
    assert ack["error_receipt_acknowledged"] is True
    prefix=f"{m.PROJECT_ID}/{m.AUDIT_ID}/{NONCE}"
    assert prefix+"/final.json" not in store.values
    assert len([key for key in store.values if key.endswith("-result.json")])==51


@pytest.mark.parametrize("fault",("17-per-cik","513-total","not-symbol","non-equity","empty-id","long-value","resolver-exception"))
def test_invalid_or_excess_resolver_metadata_stops_without_retry_and_cloud_error(monkeypatch,fault):
    def resolve(value,index):
        if fault=="17-per-cik":return [Symbol(f"SID-{n}") for n in range(17)]
        if fault=="513-total":return [Symbol(f"SID-{index}-{n}") for n in range(16)]
        if fault=="not-symbol":return [object()]
        if fault=="non-equity":return [Symbol("SID",security_type="Option")]
        if fault=="empty-id":return [Symbol("")]
        if fault=="long-value":return [Symbol("SID",value="x"*129)]
        raise RuntimeError(PRIVATE)
    ack,_,store,calls,namespace=execute(monkeypatch,resolve=resolve)
    assert ack["disposition"]=="refused_no_retry" and ack["cloud_receipt_chain_complete"] is False
    assert len(calls)==(33 if fault=="513-total" else 1)
    assert ack["error_receipt_acknowledged"] is True
    error=json.loads(store.values[f"{m.PROJECT_ID}/{m.AUDIT_ID}/{NONCE}/error.json"])
    assert error["unattempted_ciks"]==list(m.CIKS[len(calls):]) and error["no_retry_or_resume"] is True
    prior=list(store.events)
    again,_,_,calls2,_=execute(monkeypatch,store=store,namespace=namespace)
    assert calls2==[] and store.events==prior and again["stop_stage"]=="kernel_claim"


@pytest.mark.parametrize("fault",("existing","save_false","save_nonbool","save_exception","read_exception","read_mismatch"))
def test_storage_failures_stop_before_resolver_and_never_resume(monkeypatch,fault):
    ack,_,store,calls,_=execute(monkeypatch,store=Store(fail=fault))
    assert calls==[] and ack["cloud_receipt_chain_complete"] is False
    assert ack["stop_stage"]==("key_precheck" if fault=="existing" else "start_readback" if fault.startswith("read") else "start_save")
    assert ack["own_receipt_saves"]<=(0 if fault=="existing" else 2)


@pytest.mark.parametrize("project",(True,37465795.0,"37465795",37465796,None))
def test_wrong_project_refuses_without_store_or_lookup(monkeypatch,project):
    ack,_,store,calls,_=execute(monkeypatch,project=project)
    assert calls==store.events==[] and ack["stop_stage"]=="project"


def test_factory_exception_is_fixed_and_no_cloud_operations(monkeypatch):
    ack,_,store,calls,_=execute(monkeypatch,fail_factory=True)
    assert ack["stop_stage"]=="construct" and store.events==calls==[]


@pytest.mark.parametrize("mode",("construct","existing","consume"))
def test_coherent_refusal_cannot_claim_an_unperformed_error_receipt(monkeypatch,mode):
    if mode=="construct":ack,_,_,_,_=execute(monkeypatch,fail_factory=True)
    elif mode=="existing":ack,_,_,_,_=execute(monkeypatch,store=Store(fail="existing"))
    else:ack,_,_,_,_=execute(monkeypatch,consume=True)
    assert ack["error_receipt_acknowledged"] is False
    ack["error_receipt_acknowledged"]=True
    registration,_=m.build_invented_cell(NONCE)
    with pytest.raises(m.CikCandidateError):
        m.validate_acknowledgement(m._raw(ack),registration_raw=registration,consume=mode=="consume")


def test_safe_cloud_consumer_rederives_all_receipts_without_any_lookup_or_write(monkeypatch):
    _,_,store,_,_=execute(monkeypatch)
    store.events.clear()
    ack,raw,_,calls,namespace=execute(monkeypatch,store=store,consume=True)
    assert calls==[] and all(event[0]=="read" for event in store.events) and len(store.events)==104
    assert ack["disposition"]=="retained_receipts_consistent_no_lookup" and ack["resolver_calls_attempted"]==0
    assert len(namespace["_ib_cik_retained_"+NONCE])==51 and b"PRIVATE-SID" not in raw


@pytest.mark.parametrize("leaf",("start.json","001-started.json","001-result.json","final.json"))
def test_consumer_missing_or_corrupt_cloud_receipts_cannot_reconstruct_or_repeat(monkeypatch,leaf):
    _,_,store,_,_=execute(monkeypatch)
    store.values[f"{m.PROJECT_ID}/{m.AUDIT_ID}/{NONCE}/{leaf}"]='{}';store.events.clear()
    ack,_,_,calls,_=execute(monkeypatch,store=store,consume=True)
    assert calls==[] and ack["cloud_receipt_chain_complete"] is False and ack["error_receipt_acknowledged"] is False
    assert all(event[0]=="read" for event in store.events)


@pytest.mark.parametrize("field,bad",(("maximum_resolver_calls",True),("fresh_cloud_keys",104),("history_subscriptions_jobs_backtests",False),("atomic_create_or_immutability_guaranteed",0)))
def test_coherent_bad_scope_registration_refuses_before_sdk(monkeypatch,field,bad):
    r=json.loads(m.build_invented_cell(NONCE)[0]);r["scope"][field]=bad
    namespace={};exec(m.CORE_SOURCE,namespace);out=io.StringIO()
    def forbidden():pytest.fail("registration must refuse before SDK")
    text=m._raw(r).decode()
    with contextlib.redirect_stdout(out):namespace["_ib_cik_run"](forbidden,text,m._sha(text.encode()))
    assert json.loads(out.getvalue())=={"schema":m.SCHEMA+"/acknowledgement","disposition":"registration_refused"}


@pytest.mark.parametrize("change",("cik-order","cik-duplicate","assessment-pin"))
def test_coherent_input_identity_changes_cannot_replace_supplied_51_source_members(change):
    r=json.loads(m.build_invented_cell(NONCE)[0])
    if change=="cik-order":r["ciks"][0],r["ciks"][1]=r["ciks"][1],r["ciks"][0]
    elif change=="cik-duplicate":r["ciks"][1]=r["ciks"][0]
    else:r["source_provenance"]["assessment_sha256"]="0"*64
    r["ciks_sha256"]=m._sha(m._raw(r["ciks"]))
    namespace={};exec(m.CORE_SOURCE,namespace);out=io.StringIO();text=m._raw(r).decode()
    with contextlib.redirect_stdout(out):namespace["_ib_cik_run"](lambda:pytest.fail("source substituted"),text,m._sha(text.encode()))
    assert json.loads(out.getvalue())["disposition"]=="registration_refused"


@pytest.mark.parametrize("field,bad",(("resolver_calls_attempted",True),("own_key_prechecks",104),("own_receipt_saves",103),("cloud_receipt_chain_complete",1),("platform_values_counts_or_digests_exported",True),("stop_stage","raw-private-exception")))
def test_external_ack_never_launders_types_counts_completion_or_private_fields(monkeypatch,field,bad):
    ack,_,_,_,_=execute(monkeypatch);ack[field]=bad
    r,_=m.build_invented_cell(NONCE)
    with pytest.raises(m.CikCandidateError):m.validate_acknowledgement(m._raw(ack),registration_raw=r)


def identity(root):
    inventory={m.SELF_PATH:m._sha(b"source"),m.TEST_PATH:m._sha(b"tests"),"data/hashing.py":m._sha(b"hashing"),"ml/immutable_io.py":m._sha(b"immutable")}
    return {"root":str(root),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,"source_sha256":inventory,"source_inventory_sha256":m._sha(m._raw(inventory))}


def test_permanent_private_local_intent_and_full_roster_precede_returned_source(tmp_path):
    path=tmp_path.joinpath(*m.ARTIFACT_PARTS);calls=[]
    def proof(value):
        assert not path.exists();calls.append(1);return m._proof(value,True)
    result=m.prepare_invented_cell(tmp_path,preflight=proof)
    assert calls==[1] and result["cloud_execution_observed"] is False
    assert set(p.name for p in path.iterdir())=={"scope.lock","registration.json","cell.py","intent.json","ready.json"}
    intent=json.loads((path/"intent.json").read_bytes())
    assert len(intent["execution_identity"]["source_sha256"])==108
    assert intent["cell_sha256"]==m._sha(result["cell_source"].encode()) and intent["no_retry_even_after_kernel_reset"] is True
    assert all(p.stat().st_mode&0o777==0o600 for p in path.iterdir()) and path.stat().st_mode&0o777==0o700
    with pytest.raises((ValueError,OSError)):m.prepare_invented_cell(tmp_path,nonce="b"*64)


def test_preflight_refusal_creates_no_namespace_or_selected_nonce(tmp_path,monkeypatch):
    original=m._cell
    def cell(nonce,fixture,**kwargs):
        assert nonce=="0"*64;return original(nonce,fixture,**kwargs)
    monkeypatch.setattr(m,"_cell",cell)
    def fail(value):raise m.CikCandidateError("invented-native-refusal")
    with pytest.raises(m.CikCandidateError):m.prepare_invented_cell(tmp_path,preflight=fail)
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_bad_nonce_after_local_claim_is_not_rearmed(tmp_path):
    with pytest.raises(m.CikCandidateError):m.prepare_invented_cell(tmp_path,nonce="bad")
    path=tmp_path.joinpath(*m.ARTIFACT_PARTS)
    assert set(p.name for p in path.iterdir())=={"scope.lock"}
    with pytest.raises((ValueError,OSError)):m.prepare_invented_cell(tmp_path)


def test_local_intent_publication_failure_preserves_existing_claim(tmp_path,monkeypatch):
    publish=m.publication._NewDirectory.publish
    def failure(self,name,raw,**kwargs):
        if name=="intent.json":raise m.CikCandidateError("invented-local-publication-refusal")
        return publish(self,name,raw,**kwargs)
    monkeypatch.setattr(m.publication._NewDirectory,"publish",failure)
    with pytest.raises(m.CikCandidateError):m.prepare_invented_cell(tmp_path)
    path=tmp_path.joinpath(*m.ARTIFACT_PARTS)
    assert set(p.name for p in path.iterdir())=={"scope.lock","registration.json","cell.py"}
    with pytest.raises((ValueError,OSError)):m.prepare_invented_cell(tmp_path)


def test_real_shaped_current_identity_checks_own_git_and_all_internal_roots(monkeypatch):
    value=identity(m.LANE_ROOT)
    monkeypatch.setattr(m.sources.custody,"_identity",lambda head:copy.deepcopy(value))
    monkeypatch.setattr(m.sources.custody,"_internal_source_paths",lambda root:tuple(value["source_sha256"]))
    monkeypatch.setattr(m.sources.custody,"_source_bytes",lambda root,names:m.sources.FROZEN if tuple(names)==tuple(m.sources.FROZEN) else {k:value["source_sha256"][k] for k in names})
    def git(root,op,target):return b"source" if target.endswith(":"+m.SELF_PATH) else b"tests"
    monkeypatch.setattr(m.sources.custody,"_git",git)
    assert m._identity("a"*40)==value
    monkeypatch.setattr(m.sources.custody,"_git",lambda *args:b"wrong")
    with pytest.raises(m.CikCandidateError):m._identity("a"*40)


def test_native_source_worker_denial_before_control_reads_and_actual_front(monkeypatch):
    events=[]
    monkeypatch.setattr(m,"_isolated",lambda:events.append("flags"))
    monkeypatch.setattr(m.sources,"_prove_isolation",lambda:events.append("native"))
    monkeypatch.setattr(m,"_current",lambda i:events.append("source"))
    monkeypatch.setattr(m,"_capacity",lambda i,f:events.append("capacity"))
    assert m._worker(identity(m.LANE_ROOT))==m._proof(identity(m.LANE_ROOT),False)
    assert events==["flags","native","source","capacity","source"]


def test_actual_front_nonisolated_refuses_before_identity(monkeypatch):
    monkeypatch.setattr(m.sys,"pycache_prefix","wrong")
    monkeypatch.setattr(m,"_identity",lambda *args:pytest.fail("before initial isolation"))
    with pytest.raises(m.CikCandidateError):m.prepare_actual_cell("a"*40)


def test_loaded_source_closure_is_not_reduced_to_owned_images(monkeypatch):
    value=identity(m.LANE_ROOT)
    monkeypatch.setattr(m.sources.custody,"_internal_source_paths",lambda root:("data/required.py",))
    monkeypatch.setattr(m.sources.custody,"_source_bytes",lambda *args:pytest.fail("incomplete source closure"))
    with pytest.raises(m.CikCandidateError,match="candidate_loaded_closure_missing"):m._current(value)


@pytest.mark.parametrize("bad",(None,"returncode","stderr","typed-proof"))
def test_native_preflight_exact_new_source_command_and_receipt(monkeypatch,bad):
    value=identity(m.LANE_ROOT);seen=[];proof=m._proof(value,False)
    if bad=="typed-proof":proof["source_count"]=True
    def launch(command,**kwargs):
        seen.append((command,kwargs));return types.SimpleNamespace(returncode=2 if bad=="returncode" else 0,
            stderr=b"invented" if bad=="stderr" else b"",stdout=m._raw(proof)+b"\n")
    monkeypatch.setattr(m.sources.launcher,"run_child",launch)
    if bad is None:assert m._source_preflight(value)==m._proof(value,False)
    else:
        with pytest.raises(m.CikCandidateError):m._source_preflight(value)
    assert len(seen)==1
    command,kwargs=seen[0];policy=command[command.index("-p")+1]
    assert all(token in policy for token in ("(deny network*)","(deny process-fork)","(deny file-write*)","/usr/bin/security"))
    assert command[:2]==("/usr/bin/env","-i") and all(flag in command for flag in ("-I","-S","-B"))
    assert "insider_buying_qc_cik_candidate_cell" in command[-1] and "_git(" not in command[-1]
    assert kwargs=={"cwd":m.LANE_ROOT,"env":None,"timeout":60,"cap":8192}


def test_generated_sdk_scope_has_no_history_subscription_job_or_platform_export():
    _,cell=m.build_invented_cell(NONCE);tree=ast.parse(cell)
    forbidden={"history","add_equity","add_security","fundamentals","download","delete","keys","create_backtest","create_compile","request"}
    assert not {node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}&forbidden
    assert b"store.read(" in cell and b"qb.cik(" in cell and b"trading_date=datetime(2021,3,31)" in cell


def test_cli_never_echoes_mistaken_private_argument(capsys):
    with pytest.raises(SystemExit):m.main(["--expected-head","a"*40,"--token","invented-private"])
    assert capsys.readouterr().err=="candidate_argument_refused\n"
