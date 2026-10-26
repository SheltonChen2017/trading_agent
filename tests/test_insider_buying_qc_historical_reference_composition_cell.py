"""Genuine generated predecessor chains, invented SDK only; zero new SDK calls."""
import ast
import contextlib
import copy
from datetime import datetime
import io
import json
import sys
import types

import pandas as pd
import pytest

pytest.importorskip("fcntl",reason="macOS/POSIX custody")
pytest.importorskip("termios",reason="macOS/POSIX custody")
from research import insider_buying_qc_historical_reference_composition_cell as m
import test_insider_buying_qc_historical_reference_cell as inherited


NONCE="b"*64


def _context(monkeypatch,*,resolve=None,frame=None):
    monkeypatch.setattr(inherited,"NONCE",m.REFERENCE_NONCE)
    ack,_,store,_,namespace=inherited.execute(monkeypatch,resolve=resolve,frame=frame)
    assert ack["own_final_receipt_acknowledged"] is True
    store.events.clear()
    return namespace,store


def _execute(monkeypatch,*,namespace=None,store=None,resolve=None,frame=None):
    if namespace is None:namespace,store=_context(monkeypatch,resolve=resolve,frame=frame)
    registration,cell=m.build_invented_cell(NONCE);out,err=io.StringIO(),io.StringIO()
    # Any accidental SDK factory/store reuse must fail, not merely be ignored.
    def forbidden(*args,**kwargs):raise AssertionError("forbidden fresh SDK/store operation")
    if store is not None:
        monkeypatch.setattr(store,"contains_key",forbidden);monkeypatch.setattr(store,"save",forbidden);monkeypatch.setattr(store,"read",forbidden)
    monkeypatch.setattr(sys.modules["QuantConnect.Research"],"QuantBook",forbidden)
    with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):exec(cell,namespace)
    raw=out.getvalue().encode();assert err.getvalue()=="" and len(raw.splitlines())==1
    assert b"CLOUD-SID" not in raw and inherited.PRIVATE.encode() not in raw
    ack=m.validate_acknowledgement(raw,registration_raw=registration)
    if store is not None:assert store.events==[]
    return ack,raw,namespace


def _private(namespace):return namespace["_ib_reference_composed_"+NONCE]


def _matching_frame(symbols,selector,index):
    values={str(symbol.id):[str(symbol.id).rsplit("-",1)[1].zfill(10) if index==1 else False if index==4 else "DECLARED"] for symbol in symbols}
    return pd.DataFrame(values,index=[pd.Timestamp("2021-04-01")])


def test_generated_chain_composes_all_rows_edges_fields_and_labels_without_SDK(monkeypatch):
    ack,raw,namespace=_execute(monkeypatch,frame=_matching_frame)
    assert ack["disposition"]=="retained_reference_composition_completed" and ack["own_composition_published"] is True
    value=_private(namespace);old=namespace["_ib_historical_reference_retained_"+m.REFERENCE_NONCE]
    assert len(value["original_candidate_rows"])==len(value["edge_assessments"])==51
    assert value["original_historical_reference"]==old
    assert all(edge["declared_cik_comparison"]=="declared_cik_matches_expected" for edge in value["edge_assessments"])
    assert all(set(edge["raw_reference_fields"])==set(m.previous.SELECTORS) for edge in value["edge_assessments"])
    assert all(edge["raw_reference_fields"][m.previous.SELECTORS[3]]["value"] is False for edge in value["edge_assessments"])
    assert value["original_historical_reference"]["results"][0]["returned_index"][0]["returned_index_isoformat"]=="2021-04-01T00:00:00"
    assert value["authority"]["point_in_time_verified"] is value["authority"]["canonical_admitted"] is False
    for forbidden in ("candidate_edges","edge_assessments","source_rows_sha256","reference_context_sha256","canonical_declared_cik","observations","count"):
        assert ('"'+forbidden+'":').encode() not in raw


@pytest.mark.parametrize("declared,expected",[("0000006281","declared_cik_matches_expected"),("6281","declared_cik_matches_expected"),
    (6281,"declared_cik_matches_expected"),("0000019612","declared_cik_differs"),(0,"declared_cik_malformed_or_zero"),
    ("0000000000","declared_cik_malformed_or_zero"),("6281.0","declared_cik_malformed_or_zero"),
    (" 6281","declared_cik_malformed_or_zero"),("","declared_cik_malformed_or_zero")])
def test_CIK_comparison_preserves_lexeme_without_ticker_or_primary_selection(monkeypatch,declared,expected):
    def frame(symbols,selector,index):
        return pd.DataFrame({str(symbol.id):[declared if index==1 else False if index==4 else "UNKNOWN-RAW-CODE"] for symbol in symbols},index=[pd.Timestamp("2021-03-31")])
    ack,_,namespace=_execute(monkeypatch,frame=frame);assert ack["own_composition_published"]
    edges=_private(namespace)["edge_assessments"]
    assert edges[0]["declared_cik_comparison"]==expected and len(edges)==51
    assert edges[0]["raw_reference_fields"][m.previous.SELECTORS[0]]["value"]==declared
    assert edges[0]["raw_reference_fields"][m.previous.SELECTORS[1]]["value"]=="UNKNOWN-RAW-CODE"


def test_zero_duplicate_and_cross_CIK_edges_are_all_preserved(monkeypatch):
    def resolve(value,index):return [] if index==1 else [inherited.Symbol("SHARED"),inherited.Symbol("SHARED")] if index==2 else [inherited.Symbol("SHARED")]
    ack,_,namespace=_execute(monkeypatch,resolve=resolve);assert ack["own_composition_published"]
    value=_private(namespace);rows=value["original_candidate_rows"]
    assert len(rows)==51 and rows[0]["resolver_returned_zero"] is True and rows[1]["duplicate_sids"]==["SHARED"]
    assert len(value["edge_assessments"])==51 and len({edge["sid"] for edge in value["edge_assessments"]})==1
    assert value["no_candidates_silently_selected_or_dropped"] is True


def test_empty_missing_and_missing_columns_remain_distinct_not_absence(monkeypatch):
    def frame(symbols,selector,index):
        ids=[str(symbol.id) for symbol in symbols]
        if index==1:return pd.DataFrame(columns=ids)
        return pd.DataFrame({ids[0]:[None if index<4 else False]},index=[pd.Timestamp("2021-03-31")])
    ack,_,namespace=_execute(monkeypatch,frame=frame);assert ack["own_composition_published"]
    value=_private(namespace);edges=value["edge_assessments"]
    # Query scheduling sorts/deduplicates SID strings, not original CIK order.
    first_sid=value["original_historical_reference"]["start"]["ordered_sids"][0]
    first=next(edge for edge in edges if edge["sid"]==first_sid)
    second=next(edge for edge in edges if edge["sid"]!=first_sid)
    assert first["declared_cik_comparison"]=="reference_missing_or_unreturned"
    assert first["raw_reference_fields"][m.previous.SELECTORS[0]]=={"state":"no_record_returned"}
    assert first["raw_reference_fields"][m.previous.SELECTORS[1]]=={"state":"missing_value"}
    assert second["raw_reference_fields"][m.previous.SELECTORS[1]]=={"state":"column_not_returned"}
    assert value["authority"]["historical_absence_proven"] is False


@pytest.mark.parametrize("fault",("rows_missing","reference_missing","reference_marker","old_marker","consumer_marker","row_order","row_hash",
    "start_root","result_order","result_bool_ordinal","result_observation","primary_type","future_index","submicrosecond_index","final_root"))
def test_missing_or_mutated_context_refuses_without_SDK_or_store(monkeypatch,fault):
    namespace,store=_context(monkeypatch);rows=namespace["_ib_cik_retained_"+m.previous.consumer.PRODUCER_NONCE]
    reference=namespace["_ib_historical_reference_retained_"+m.REFERENCE_NONCE]
    if fault=="rows_missing":namespace.pop("_ib_cik_retained_"+m.previous.consumer.PRODUCER_NONCE)
    elif fault=="reference_missing":namespace.pop("_ib_historical_reference_retained_"+m.REFERENCE_NONCE)
    elif fault=="reference_marker":namespace["_ib_historical_reference_"+m.REFERENCE_NONCE]=False
    elif fault=="old_marker":namespace["_ib_cik_consume_"+m.previous.consumer.PRODUCER_NONCE]=False
    elif fault=="consumer_marker":namespace["_ib_cik_new_consumer_"+"e"*64]=False
    elif fault=="row_order":rows[0],rows[1]=rows[1],rows[0]
    elif fault=="row_hash":rows[0]["lookup_started_sha256"]="f"*64
    elif fault=="start_root":reference["start"]["registration_sha256"]="f"*64
    elif fault=="result_order":reference["results"][0],reference["results"][1]=reference["results"][1],reference["results"][0]
    elif fault=="result_bool_ordinal":reference["results"][0]["ordinal"]=True
    elif fault=="result_observation":reference["results"][0]["observations"][0]["sid"]="not-the-retained-SID"
    elif fault=="primary_type":reference["results"][3]["observations"][0]["reference"]["value"]=0
    elif fault=="future_index":reference["results"][0]["returned_index"][0]["returned_index_isoformat"]="2021-04-02T00:00:00"
    elif fault=="submicrosecond_index":reference["results"][0]["returned_index"][0]["returned_index_isoformat"]="2021-04-01T00:00:00.000000001"
    else:reference["final"]["query_result_sha256"][0]="f"*64
    ack,_,namespace=_execute(monkeypatch,namespace=namespace,store=store)
    assert ack["disposition"]=="refused_no_retry" and ack["own_composition_published"] is False
    assert ack["stop_stage"] in {"retained_context","context_shape"} and "_ib_reference_composed_"+NONCE not in namespace


@pytest.mark.parametrize("fault",("source","output"))
def test_publication_boundary_mutation_cannot_acknowledge_completion(monkeypatch,fault):
    old,store=_context(monkeypatch)
    class ObservedNamespace(dict):
        def __setitem__(self,key,value):
            super().__setitem__(key,value)
            if key=="_ib_reference_composed_"+NONCE:
                if fault=="source":self["_ib_cik_retained_"+m.previous.consumer.PRODUCER_NONCE][0]["candidates"][0]["symbol_value"]="mutated"
                else:value["edge_assessments"][0]["declared_cik_comparison"]="tampered"
    ack,_,namespace=_execute(monkeypatch,namespace=ObservedNamespace(old),store=store)
    assert ack["own_composition_published"] is False and ack["stop_stage"]==("source_recheck" if fault=="source" else "publication_recheck")
    assert "_ib_reference_composed_"+NONCE in namespace  # volatile failed candidate remains; no fabricated completion


def test_second_execution_claim_never_recomposes_or_reuses_SDK(monkeypatch):
    ack,_,namespace=_execute(monkeypatch);value=_private(namespace)
    again,_,namespace=_execute(monkeypatch,namespace=namespace)
    assert ack["own_composition_published"] is True and again["own_composition_published"] is False
    assert again["stop_stage"]=="kernel_claim" and _private(namespace) is value


def test_maximum_512_escaped_edges_retain_complete_graph_inside_capacity(monkeypatch):
    def resolve(value,index):
        if index>32:return []
        return [inherited.Symbol((f"SID-{index:02d}-{n:02d}-"+'\\"'*512)[:512],value='\\"'*64) for n in range(16)]
    def frame(symbols,selector,index):return pd.DataFrame({str(symbol.id):[False if index==4 else '\\"'*32] for symbol in symbols},index=[pd.Timestamp("2021-03-31")])
    ack,_,namespace=_execute(monkeypatch,resolve=resolve,frame=frame)
    assert ack["own_composition_published"] and len(_private(namespace)["edge_assessments"])==512
    assert len(m._raw(_private(namespace)))<=m._scope()["maximum_composition_bytes"]


@pytest.mark.parametrize("field,bad",(("execution_cell_index",1),("project_id",True),("execution_notebook","new-notebook.ipynb"),
    ("fixture_only",False),("source_provenance",{}),("scope",{}),("core_sha256","f"*64)))
def test_coherent_bad_registration_never_claims_or_touches_context(field,bad):
    registration,_=m.build_invented_cell(NONCE);value=json.loads(registration);value[field]=bad;text=m._raw(value).decode()
    namespace={};exec(m._core(True),namespace);out=io.StringIO()
    with contextlib.redirect_stdout(out):namespace["_ib_reference_compose"](text,m._sha(text.encode()),m._sha(m._core(True).encode()))
    assert json.loads(out.getvalue())=={"schema":m.SCHEMA+"/acknowledgement","disposition":"registration_refused"}
    assert "_ib_reference_composition_"+NONCE not in namespace


@pytest.mark.parametrize("field,bad",(("own_composition_published",1),("execution_cell_index",True),("SDK_or_store_calls",True),
    ("platform_values_counts_comparisons_or_digests_exported",True),("stop_stage",[]),("stop_stage",{})))
def test_external_ACK_rejects_types_and_unbounded_or_platform_fields(monkeypatch,field,bad):
    ack,_,_=_execute(monkeypatch);ack[field]=bad;registration,_=m.build_invented_cell(NONCE)
    with pytest.raises(m.ReferenceCompositionError):m.validate_acknowledgement(m._raw(ack),registration_raw=registration)


def test_scope_AST_has_no_SDK_import_or_query_store_surface():
    _,cell=m.build_invented_cell(NONCE);tree=ast.parse(cell)
    imported={node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)}
    assert imported=={"datetime"}
    calls={node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
    assert not calls&{"cik","get_fundamental","history","save","read","contains_key","delete","add_equity","download","create_backtest"}
    assert m._scope()["SDK_calls"]==m._scope()["ObjectStore_reads_saves_deletes"]==0
    assert m._sha(m._raw(m._reference_registration(False)))==m.REFERENCE_OBSERVATION["registration_sha256"]


def test_fresh_private_intent_after_native_preflight_is_one_shot(tmp_path):
    folder=tmp_path.joinpath(*m.ARTIFACT_PARTS);events=[]
    def preflight(identity):assert not folder.exists();events.append("preflight");return m._proof(identity,True)
    result=m.prepare_invented_cell(tmp_path,preflight=preflight)
    assert events==["preflight"] and {path.name for path in folder.iterdir()}=={"scope.lock","registration.json","cell.py","intent.json","ready.json"}
    intent=json.loads((folder/"intent.json").read_bytes())
    assert intent["maximum_selected_cell_executions"]==1 and intent["no_retry_even_after_kernel_reset"] is True
    assert result["execution_cell_index"]==2 and result["execution_notebook"]==m.previous.NOTEBOOK
    assert all(path.stat().st_mode&0o777==0o600 for path in folder.iterdir())
    with pytest.raises((OSError,ValueError)):m.prepare_invented_cell(tmp_path)


def test_preflight_failure_creates_no_scope_or_live_nonce(tmp_path):
    with pytest.raises(m.ReferenceCompositionError):m.prepare_invented_cell(tmp_path,preflight=lambda _:(_ for _ in ()).throw(m.ReferenceCompositionError("invented")))
    assert not tmp_path.joinpath(*m.ARTIFACT_PARTS).exists()


def test_actual_front_requires_initial_isolation_before_any_identity(monkeypatch):
    monkeypatch.setattr(m.sys,"pycache_prefix","wrong");monkeypatch.setattr(m,"_identity",lambda _:pytest.fail("no actual identity reads"))
    with pytest.raises(m.ReferenceCompositionError):m.prepare_actual_cell("a"*40)


def test_native_preflight_source_order_and_exact_child_result(monkeypatch):
    identity=m._invented_identity(m.LANE_ROOT);events=[]
    monkeypatch.setattr(m,"_isolated",lambda:events.append("flags"));monkeypatch.setattr(m.sources,"_prove_isolation",lambda:events.append("native"))
    monkeypatch.setattr(m,"_current",lambda _:events.append("source"));monkeypatch.setattr(m,"_capacity",lambda *a:events.append("capacity"))
    assert m._worker(identity)==m._proof(identity,False) and events==["flags","native","source","capacity","source"]
    def launch(command,**kwargs):
        assert command[:2]==("/usr/bin/env","-i") and all(flag in command for flag in ("-I","-S","-B"))
        policy=command[command.index("-p")+1]
        assert all(rule in policy for rule in ("deny network*","deny process-fork","deny file-write*","/usr/bin/security"))
        assert "_git(" not in command[-1]
        return types.SimpleNamespace(returncode=0,stderr=b"",stdout=m._raw(m._proof(identity,False))+b"\n")
    monkeypatch.setattr(m.sources.launcher,"run_child",launch);m._source_preflight(identity)
    monkeypatch.setattr(m.sources.launcher,"run_child",lambda *a,**k:types.SimpleNamespace(returncode=71,stderr=b"sandbox_apply",stdout=b""))
    with pytest.raises(m.ReferenceCompositionError):m._source_preflight(identity)


def test_source_identity_requires_new_and_exact_old_Git_images(monkeypatch):
    names=(m.SELF_PATH,m.TEST_PATH,m.previous.SELF_PATH,m.previous.TEST_PATH)
    bodies={name:(m.LANE_ROOT/name).read_bytes() for name in names};hashes={name:m._sha(body) for name,body in bodies.items()}
    value={"root":str(m.LANE_ROOT),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,"source_sha256":hashes,"source_inventory_sha256":m._sha(m._raw(hashes))}
    monkeypatch.setattr(m.previous,"_identity",lambda _:copy.deepcopy(value))
    monkeypatch.setattr(m.sources.custody,"_source_bytes",lambda root,requested:{name:hashes[name] for name in requested})
    seen=[]
    def git(root,op,target):seen.append(target);return bodies[target.split(":",1)[1]]
    monkeypatch.setattr(m.sources.custody,"_git",git);monkeypatch.setattr(m,"_current",lambda _:None)
    assert m._identity("a"*40)==value and any(target.startswith(m.REFERENCE_HEAD+":") for target in seen)
    monkeypatch.setattr(m.sources.custody,"_git",lambda *a:b"changed")
    with pytest.raises(m.ReferenceCompositionError):m._identity("a"*40)


def test_CLI_private_argument_never_echoes(capsys):
    with pytest.raises(SystemExit):m.main(["--expected-head","a"*40,"--private","invented-private"])
    captured=capsys.readouterr();assert captured.err=="composition_argument_refused\n" and "invented-private" not in captured.out+captured.err
