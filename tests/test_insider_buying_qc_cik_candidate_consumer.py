"""Invented cloud receipts only; no real artifact, SDK, credentials or account."""
import ast
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import types

import pytest

pytest.importorskip("fcntl",reason="macOS/POSIX custody")
pytest.importorskip("termios",reason="macOS/POSIX custody")
from research import insider_buying_qc_cik_candidate_consumer as m


NONCE, PRIVATE = "d"*64, "invented-private-SDK-message"


class Symbol:
    def __init__(self,sid,value="INVENTED"):
        self.id,self.value,self.security_type=sid,value,"Equity"


class Store:
    def __init__(self):self.values,self.events,self.fail={},[],None
    def contains_key(self,key):
        self.events.append(("contains",key));return key in self.values
    def save(self,key,text):
        self.events.append(("save",key));self.values[key]=text;return True
    def read(self,key):
        self.events.append(("read",key));print(PRIVATE);print(PRIVATE,file=sys.stderr)
        if self.fail=="exception":raise RuntimeError(PRIVATE)
        if self.fail=="nontext":return b"private bytes"
        return self.values[key]
    def __getattr__(self,name):raise AssertionError("forbidden SDK member "+name)


def receipts():
    """Create all104 receipts through unchanged genuine producer core, in RAM."""
    store=Store();namespace={};exec(m.producer.CORE_SOURCE,namespace)
    qb=types.SimpleNamespace(project_id=m.PROJECT_ID,object_store=store)
    calls=[]
    def cik(value,*,trading_date):
        calls.append(value)
        return [] if len(calls)==1 else [Symbol("CLOUD-ONLY-SID"),Symbol("CLOUD-ONLY-SID")]
    qb.cik=cik;registration=m.producer._registration(m.PRODUCER_NONCE,True)
    text=m._raw(registration).decode()
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        namespace["_ib_cik_run"](lambda:(qb,Symbol,"Equity"),text,m._sha(text.encode()))
    assert len(calls)==51 and len(store.values)==104
    store.events.clear();return store


def execute(monkeypatch,*,store=None,project=m.PROJECT_ID,namespace=None,cell=None,fail_factory=False):
    store=receipts() if store is None else store
    class QB:
        project_id=project
        @property
        def object_store(self):return store
        def __getattr__(self,name):raise AssertionError("forbidden SDK member "+name)
    package,research=types.ModuleType("QuantConnect"),types.ModuleType("QuantConnect.Research")
    package.__path__=[]
    def factory():
        print(PRIVATE);print(PRIVATE,file=sys.stderr)
        if fail_factory:raise RuntimeError(PRIVATE)
        return QB()
    research.QuantBook=factory;package.Research=research
    monkeypatch.setitem(sys.modules,"QuantConnect",package);monkeypatch.setitem(sys.modules,"QuantConnect.Research",research)
    registration,generated=m.build_invented_cell(NONCE)
    namespace={} if namespace is None else namespace;out,err=io.StringIO(),io.StringIO()
    with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):exec(generated if cell is None else cell,namespace)
    raw=out.getvalue().encode()
    assert len(raw.splitlines())==1 and not err.getvalue() and PRIVATE.encode() not in raw and b"CLOUD-ONLY-SID" not in raw
    return m.validate_acknowledgement(raw,registration_raw=registration),raw,store,namespace


def test_true_generated_consumer_rederives_all_old_receipts_without_sdk_lookup_or_write(monkeypatch):
    ack,raw,store,namespace=execute(monkeypatch)
    assert ack["disposition"]=="existing_cloud_receipts_consistent_no_lookup"
    assert ack["own_receipt_reads"]==104 and len(store.events)==104
    assert all(event[0]=="read" for event in store.events)
    assert ack["resolver_calls_attempted"]==ack["cloud_saves_deletes"]==0
    assert ack["execution_notebook"]==m.NOTEBOOK!=ack["producer_notebook"]
    assert ack["producer_notebook"]==m.producer.NOTEBOOK and ack["execution_cell_index"]==0
    retained=namespace["_ib_cik_retained_"+m.PRODUCER_NONCE]
    assert len(retained)==51 and retained[0]["resolver_returned_zero"] is True
    assert retained[1]["duplicate_sids"]==["CLOUD-ONLY-SID"]
    for field in ("candidates","shared_sid_groups","candidate_rows","zero_result_rows","result_sha256"):
        assert ('"'+field+'":').encode() not in raw


@pytest.mark.parametrize("leaf",("start.json","001-started.json","001-result.json","051-result.json","final.json"))
@pytest.mark.parametrize("fault",("missing","empty-object","extra-private-field"))
def test_missing_or_coherently_altered_receipt_never_reconstructs_or_repeats(monkeypatch,leaf,fault):
    store=receipts();key=f"{m.PROJECT_ID}/{m.producer.AUDIT_ID}/{m.PRODUCER_NONCE}/{leaf}"
    if fault=="missing":del store.values[key]
    elif fault=="empty-object":store.values[key]='{}'
    else:
        changed=json.loads(store.values[key]);changed["private"]="CLOUD-ONLY-SID";store.values[key]=m._raw(changed).decode()
    before=dict(store.values);ack,_,_,namespace=execute(monkeypatch,store=store)
    assert ack["cloud_receipt_chain_consistent"] is False and ack["stop_stage"]=="inherited_refusal"
    assert ack["inherited_stop_stage"]=="consume_readback" and 1<=ack["own_receipt_reads"]<=104
    assert all(event[0]=="read" for event in store.events) and store.values==before
    assert "_ib_cik_retained_"+m.PRODUCER_NONCE not in namespace


@pytest.mark.parametrize("fault",("exception","nontext"))
def test_foreign_read_failures_emit_only_finite_own_status(monkeypatch,fault):
    store=receipts();store.fail=fault
    ack,raw,_,_=execute(monkeypatch,store=store)
    assert ack["own_receipt_reads"]==1 and ack["inherited_stop_stage"]=="consume_readback"
    assert PRIVATE.encode() not in raw and len(store.events)==1


@pytest.mark.parametrize("project",(True,37465795.0,"37465795",37465796,None))
def test_wrong_project_has_zero_reads_and_no_recovery(monkeypatch,project):
    ack,_,store,_=execute(monkeypatch,project=project)
    assert ack["inherited_stop_stage"]=="project" and ack["own_receipt_reads"]==0 and store.events==[]


def test_factory_failure_has_zero_reads_and_sanitized_refusal(monkeypatch):
    ack,_,store,_=execute(monkeypatch,fail_factory=True)
    assert ack["inherited_stop_stage"]=="construct" and store.events==[]


def test_ack_cannot_claim_consume_readback_failure_without_one_read(monkeypatch):
    ack,_,_,_=execute(monkeypatch,project=None)
    assert ack["own_receipt_reads"]==0 and ack["inherited_stop_stage"]=="project"
    ack["inherited_stop_stage"]="consume_readback"
    registration,_=m.build_invented_cell(NONCE)
    with pytest.raises(m.CandidateConsumerError):m.validate_acknowledgement(m._raw(ack),registration_raw=registration)


def test_same_selected_cell_or_fresh_nonce_does_not_reset_old_consume_marker(monkeypatch):
    _,_,store,namespace=execute(monkeypatch);store.events.clear()
    ack,_,_,_=execute(monkeypatch,store=store,namespace=namespace)
    assert ack["stop_stage"]=="kernel_claim" and store.events==[]
    _,fresh=m.build_invented_cell("e"*64)
    # A separately generated fixture nonce cannot erase the existing old-core
    # claim. No actual local intent or selected cell is prepared or executed.
    out=io.StringIO()
    with contextlib.redirect_stdout(out):exec(fresh,namespace)
    observed=json.loads(out.getvalue())
    assert observed["stop_stage"]=="inherited_refusal" and observed["inherited_stop_stage"]=="kernel_claim"
    assert observed["own_receipt_reads"]==0 and store.events==[]


@pytest.mark.parametrize("field,bad",(("fixture_only",False),("project_id",True),("execution_notebook","research.ipynb"),
    ("execution_cell_index",True),("consumer_core_sha256","a"*64),("scope",{}),("producer_provenance",{}),("producer_registration",{})))
def test_coherently_rehashed_wrong_registration_refuses_before_factory(field,bad):
    registration,_=m.build_invented_cell(NONCE);r=json.loads(registration);r[field]=bad;text=m._raw(r).decode()
    namespace={};exec(m.producer.CORE_SOURCE+m._consumer_core(True),namespace);out=io.StringIO()
    def forbidden():pytest.fail("registration must refuse before SDK construction")
    with contextlib.redirect_stdout(out):namespace["_ib_cik_consumer_run"](forbidden,text,m._sha(text.encode()),m._sha(m._consumer_core(True).encode()))
    assert json.loads(out.getvalue())=={"schema":m.SCHEMA+"/acknowledgement","disposition":"registration_refused"}


@pytest.mark.parametrize("field,bad",(("execution_notebook",m.producer.NOTEBOOK),("producer_notebook",m.NOTEBOOK),
    ("own_receipt_reads",True),("own_receipt_reads",103),("resolver_calls_attempted",1),("cloud_saves_deletes",1),
    ("cloud_receipt_chain_consistent",1),("platform_values_counts_or_digests_exported",True),("inherited_stop_stage","raw-private-exception")))
def test_external_ack_cannot_relabel_execution_or_launder_counts(monkeypatch,field,bad):
    ack,_,_,_=execute(monkeypatch);ack[field]=bad;registration,_=m.build_invented_cell(NONCE)
    with pytest.raises(m.CandidateConsumerError):m.validate_acknowledgement(m._raw(ack),registration_raw=registration)


def test_production_original_control_pins_are_rederived_without_reading_artifacts():
    provenance=m._producer_provenance(False)
    assert provenance==m.OBSERVED_PRODUCER and provenance["capture_selected_cell_executions_observed"]==1
    registration,cell=m.producer._cell(m.PRODUCER_NONCE,False)
    assert m._sha(registration)==provenance["registration_sha256"] and m._sha(cell)==provenance["cell_sha256"]
    assert m.producer.CORE_SHA256==m.PRODUCER_CORE_SHA256


def test_original_core_mutation_is_refused_before_production_source_preparation(monkeypatch):
    monkeypatch.setattr(m.producer,"CORE_SHA256","f"*64)
    with pytest.raises(m.CandidateConsumerError):m._producer_provenance(False)


def test_full_private_permanent_intent_precedes_returned_cell_and_never_rearms(tmp_path):
    path=tmp_path.joinpath(*m.ARTIFACT_PARTS);events=[]
    def preflight(identity):
        assert not path.exists();events.append("proof");return m._proof(identity,True)
    result=m.prepare_invented_cell(tmp_path,nonce=NONCE,preflight=preflight)
    assert events==["proof"] and result["cloud_execution_observed"] is False
    assert {p.name for p in path.iterdir()}=={"scope.lock","registration.json","cell.py","intent.json","ready.json"}
    intent=json.loads((path/"intent.json").read_bytes());registration=json.loads((path/"registration.json").read_bytes())
    assert len(intent["execution_identity"]["source_sha256"])==108
    assert intent["execution_notebook"]==m.NOTEBOOK and intent["old_scope_reset_or_recovered"] is False
    assert registration["producer_registration"]["notebook"]==m.producer.NOTEBOOK
    assert intent["cell_sha256"]==m._sha(result["cell_source"].encode())
    assert intent["producer_registration_sha256"]==m._sha(m._raw(registration["producer_registration"]))
    assert path.stat().st_mode&0o777==0o700 and all(p.stat().st_mode&0o777==0o600 for p in path.iterdir())
    with pytest.raises((ValueError,OSError)):m.prepare_invented_cell(tmp_path,nonce="e"*64)


def test_native_preflight_refusal_creates_no_namespace_or_random_nonce(tmp_path,monkeypatch):
    real=m._cell;observed=[]
    def cell(nonce,*args):observed.append(nonce);return real(nonce,*args)
    monkeypatch.setattr(m,"_cell",cell)
    def refusal(identity):raise m.CandidateConsumerError("invented-native-refusal")
    with pytest.raises(m.CandidateConsumerError):m.prepare_invented_cell(tmp_path,preflight=refusal)
    assert observed==["0"*64] and not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_bad_nonce_and_intent_publication_failure_both_permanently_preserve_scope(tmp_path,monkeypatch):
    (tmp_path/"bad").mkdir();(tmp_path/"failure").mkdir()
    with pytest.raises(m.CandidateConsumerError):m.prepare_invented_cell(tmp_path/"bad",nonce="bad")
    assert {p.name for p in (tmp_path/"bad").joinpath(*m.ARTIFACT_PARTS).iterdir()}=={"scope.lock"}
    publish=m.publication._NewDirectory.publish
    def failure(self,name,raw,**kwargs):
        if name=="intent.json":raise m.CandidateConsumerError("invented-write-refusal")
        return publish(self,name,raw,**kwargs)
    monkeypatch.setattr(m.publication._NewDirectory,"publish",failure)
    with pytest.raises(m.CandidateConsumerError):m.prepare_invented_cell(tmp_path/"failure")
    assert {p.name for p in (tmp_path/"failure").joinpath(*m.ARTIFACT_PARTS).iterdir()}=={"scope.lock","registration.json","cell.py"}


def test_local_output_mutation_stops_before_ready(tmp_path,monkeypatch):
    publish=m.publication._NewDirectory.publish
    def mutation(self,name,raw,**kwargs):
        result=publish(self,name,raw,**kwargs)
        if name=="intent.json":
            path=self.path/"cell.py";before=path.stat();body=path.read_bytes();path.write_bytes(b"#"+body[1:]);os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
        return result
    monkeypatch.setattr(m.publication._NewDirectory,"publish",mutation)
    with pytest.raises(ValueError):m.prepare_invented_cell(tmp_path)
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS,"ready.json").exists()


def identity(root):
    bodies={m.SELF_PATH:b"source",m.TEST_PATH:b"tests",m.producer.SELF_PATH:b"producer",m.producer.TEST_PATH:b"producer-tests",
        "data/hashing.py":b"hashing","ml/immutable_io.py":b"immutable"}
    inventory={name:m._sha(body) for name,body in bodies.items()}
    return {"root":str(root),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,"source_sha256":inventory,"source_inventory_sha256":m._sha(m._raw(inventory))},bodies


def test_genuine_internal_root_roster_git_and_original_source_front(monkeypatch):
    value,bodies=identity(m.LANE_ROOT)
    monkeypatch.setattr(m,"PRODUCER_SOURCE_SHA256",value["source_sha256"][m.producer.SELF_PATH]);monkeypatch.setattr(m,"PRODUCER_TEST_SHA256",value["source_sha256"][m.producer.TEST_PATH])
    monkeypatch.setattr(m.sources.custody,"_identity",lambda head:copy.deepcopy(value))
    monkeypatch.setattr(m.sources.custody,"_internal_source_paths",lambda root:tuple(bodies))
    monkeypatch.setattr(m.sources.custody,"_source_bytes",lambda root,names:m.sources.FROZEN if tuple(names)==tuple(m.sources.FROZEN) else {name:value["source_sha256"][name] for name in names})
    calls=[]
    def git(root,op,target):calls.append(target);return bodies[target.split(":",1)[1]]
    monkeypatch.setattr(m.sources.custody,"_git",git)
    assert m._identity("a"*40)==value and any(target.startswith(m.PRODUCER_HEAD+":") for target in calls)
    monkeypatch.setattr(m.sources.custody,"_git",lambda *args:b"wrong")
    with pytest.raises(m.CandidateConsumerError):m._identity("a"*40)


def test_loaded_roster_original_image_and_frozen_bytes_are_all_required(monkeypatch):
    value,bodies=identity(m.LANE_ROOT)
    monkeypatch.setattr(m.sources.custody,"_internal_source_paths",lambda root:("data/missing.py",))
    with pytest.raises(m.CandidateConsumerError,match="loaded_closure"):m._current(value)
    monkeypatch.setattr(m.sources.custody,"_internal_source_paths",lambda root:tuple(bodies))
    monkeypatch.setattr(m.sources.custody,"_source_bytes",lambda root,names:m.sources.FROZEN if tuple(names)==tuple(m.sources.FROZEN) else value["source_sha256"])
    with pytest.raises(m.CandidateConsumerError,match="original_source_image"):m._current(value)


def test_initial_isolation_and_native_source_proof_precede_capacity(monkeypatch):
    events=[];value,_=identity(m.LANE_ROOT)
    monkeypatch.setattr(m,"_isolated",lambda:events.append("flags"));monkeypatch.setattr(m.sources,"_prove_isolation",lambda:events.append("native"))
    monkeypatch.setattr(m,"_current",lambda identity:events.append("source"));monkeypatch.setattr(m,"_capacity",lambda identity,fixture:events.append("capacity"))
    assert m._worker(value)==m._proof(value,False) and events==["flags","native","source","capacity","source"]


def test_actual_front_refuses_nonisolated_before_git_or_artifacts(monkeypatch):
    monkeypatch.setattr(m.sys,"pycache_prefix","wrong")
    monkeypatch.setattr(m,"_identity",lambda *args:pytest.fail("before source/Git/own namespace"))
    with pytest.raises(m.CandidateConsumerError):m.prepare_actual_cell("a"*40)


@pytest.mark.parametrize("bad",(None,"exit","stderr","typed-proof"))
def test_native_command_and_exact_proof_controls(monkeypatch,bad):
    value,_=identity(m.LANE_ROOT);proof=m._proof(value,False);seen=[]
    if bad=="typed-proof":proof["source_count"]=True
    def launch(command,**kwargs):
        seen.append((command,kwargs));return types.SimpleNamespace(returncode=2 if bad=="exit" else 0,stderr=b"invented" if bad=="stderr" else b"",stdout=m._raw(proof)+b"\n")
    monkeypatch.setattr(m.sources.launcher,"run_child",launch)
    if bad is None:assert m._source_preflight(value)==m._proof(value,False)
    else:
        with pytest.raises(m.CandidateConsumerError):m._source_preflight(value)
    command,kwargs=seen[0];policy=command[command.index("-p")+1]
    assert command[:2]==("/usr/bin/env","-i") and all(flag in command for flag in ("-I","-S","-B"))
    assert all(token in policy for token in ("(deny network*)","(deny process-fork)","(deny file-write*)","/usr/bin/security"))
    assert "insider_buying_qc_cik_candidate_consumer" in command[-1] and "_git(" not in command[-1]
    assert kwargs=={"cwd":m.LANE_ROOT,"env":None,"timeout":60,"cap":8192}


def test_generated_outer_consumer_has_no_lookup_or_write_and_original_core_is_unchanged():
    core=m._consumer_core(True);tree=ast.parse(core)
    forbidden={"cik","save","delete","contains_key","history","add_equity","add_security","fundamentals","download","create_compile","create_backtest"}
    assert not {node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}&forbidden
    _,cell=m.build_invented_cell(NONCE)
    assert cell.startswith(m.producer.CORE_SOURCE.encode()) and b"sha(raw(old)),True)" in cell
    assert b"return QuantBook(),None,None" in cell


def test_cli_never_echoes_private_mistaken_argument(capsys):
    with pytest.raises(SystemExit):m.main(["--expected-head","a"*40,"--secret",PRIVATE])
    output=capsys.readouterr();assert output.err=="consumer_argument_refused\n" and PRIVATE not in output.out+output.err
