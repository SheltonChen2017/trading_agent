"""Invented read-only observation controls; never actual artifacts or accounts."""
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zlib

import pytest

from research import insider_buying_sec_feed_prefix_nc_observe_v1 as m

CONTACT="invented@unit.test"


def _identity(root):
    sources={name:"a"*64 for name in (m.SELF_PATH,m.TEST_PATH,m.inherited.SELF_PATH,m.inherited.TEST_PATH)}
    return {"root":str(root),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}


def _old(tmp_path,body=None):
    root=tmp_path/"original";root.mkdir(mode=0o700)
    writer=zlib.compressobj(level=0,wbits=31)
    raw=(writer.compress((b"opaque invented observations" if body is None else body)+bytes(range(256))*500)+writer.flush())[:65536]
    response=m.capture.PrefixHttpResult(status=206,headers=(("Content-Length","65536"),("Content-Range","bytes 0-65535/1000000")),
        body=raw,body_read_attempted=True,refusal=None,declared_total=1000000)
    result=m.capture._invented(root=root,transport=lambda *_:response)
    run=root.joinpath(*m.capture.ARTIFACT_PARTS,"runs",m.capture.AUDIT_ID)
    pins={name:m._sha((run/name).read_bytes()) for name in m.inherited.ORIGINAL_PINS if name not in {"claim","prefix.bin"}}
    pins["complete.json"]=result["complete_sha256"];pins["prefix.bin"]=result["result"]["prefix_sha256"]
    pins["claim"]=m._sha(root.joinpath(*m.capture.ARTIFACT_PARTS,"claims",m.capture._claim_name()).read_bytes())
    return root,raw,pins


def _fixture(tmp_path):
    root,raw,pins=_old(tmp_path);held=m.inherited._HeldPrefix(root,fixture=True,pins=pins)
    identity=_identity(root)
    try:return root,raw,pins,copy.deepcopy(held.metadata),m._analyse(identity,CONTACT,held,fixture=True),identity
    finally:held.close()


def test_registration_readonly_old_lineage_and_detached_copy():
    value=m.registration()
    assert value["original_producer_head"]==m.inherited.ORIGINAL_HEAD
    assert value["original_prefix_pins"]==m.inherited.ORIGINAL_PINS
    assert value["original_source_count"]==138
    assert value["historical_shape_provenance"]["observed_source_count"]==144
    assert value["historical_shape_provenance"]["old_shape_output_replayed_here"] is False
    assert value["metadata_preflight_reads_or_hashes_raw_prefix"] is False
    assert value["authority"]["new_namespace_created"] is False and value["authority"]["files_written"]==0
    value["original_prefix_pins"]["prefix.bin"]="0"*64;value["authority"]["backtesting_ready"]=True
    assert m.registration()["original_prefix_pins"]==m.inherited.ORIGINAL_PINS
    assert m.registration()["authority"]["backtesting_ready"] is False


def test_real_fixture_observation_and_no_new_output(tmp_path):
    root,raw,pins,metadata,value,identity=_fixture(tmp_path)
    before={str(path.relative_to(root)) for path in root.rglob("*")}
    assert m._witness_valid(value,identity,metadata,True)==value
    assert value["original_prefix_sha256"]==pins["prefix.bin"]
    assert value["current_contact_prefix_rescreened"] is True
    assert value["original_contact_screen_replayed"] is value["original_current_contact_equality_attested"] is False
    assert value["observation"]["authority"]["canonical_admitted"] is False
    text=m._raw(value)
    assert CONTACT.encode() not in text and b"opaque invented observations" not in text and raw not in text
    assert {str(path.relative_to(root)) for path in root.rglob("*")}==before


def test_metadata_preflight_held_reader_never_reads_body(tmp_path,monkeypatch):
    root,raw,pins=_old(tmp_path);original=m.privacy._Directory.read
    def read(self,name,*args,**kwargs):
        assert name!="prefix.bin","metadata read forbidden"
        return original(self,name,*args,**kwargs)
    monkeypatch.setattr(m.privacy._Directory,"read",read)
    held=m.inherited._HeldPrefix(root,fixture=True,pins=pins)
    try:
        identity=_identity(root);plan=m._plan_valid(m._plan(identity,held.metadata),identity)
        assert plan["raw_prefix_read_or_hashed"] is False and plan["contact_reads"]==0
        held.check()
    finally:held.close()


@pytest.mark.parametrize("change",["extra","authority","fixture","identity","registration","input","prefix","complete","equality","original_screen","rescreen"])
def test_parent_rejects_dirty_outer_witness(tmp_path,change):
    _,_,_,metadata,value,identity=_fixture(tmp_path);value=copy.deepcopy(value)
    if change=="extra":value["extra"]="not allowed"
    elif change=="authority":value["authority"]["backtesting_ready"]=True
    elif change=="fixture":value["fixture_only"]=False
    elif change=="identity":value["execution_identity"]["head"]="b"*40
    elif change=="registration":value["registration_sha256"]="b"*64
    elif change=="input":value["input_metadata_sha256"]="b"*64
    elif change=="prefix":value["original_prefix_sha256"]="b"*64
    elif change=="complete":value["original_complete_sha256"]="b"*64
    elif change=="equality":value["original_current_contact_equality_attested"]=True
    elif change=="original_screen":value["original_contact_screen_replayed"]=True
    else:value["current_contact_prefix_rescreened"]=False
    with pytest.raises(m.PrefixNcObserveError):m._witness_valid(value,identity,metadata,True)


@pytest.mark.parametrize("change",["extra","bool_size","read_body","controls","claim","original_plan"])
def test_metadata_witness_rejects_changed_custody_or_plan(tmp_path,change):
    _,_,_,metadata,_,identity=_fixture(tmp_path)
    if change=="extra":metadata["unknown"]="opaque"
    elif change=="bool_size":metadata["prefix_bytes_statted"]=True
    elif change=="read_body":metadata["raw_prefix_read_by_metadata_preflight"]=True
    elif change=="controls":metadata["control_sha256"]["input-preflight.json"]="b"*64
    elif change=="claim":metadata["external_pins"]["claim"]="b"*64
    else:metadata["original_input_plan"]["inputs"]["fixture_only"]=False
    with pytest.raises(ValueError):m._plan_valid(m._plan(identity,metadata),identity)


@pytest.mark.parametrize("change",["extra","source_values","authority"])
def test_parent_rejects_dirty_nested_pure_witness(tmp_path,change):
    _,_,_,metadata,value,identity=_fixture(tmp_path);value=copy.deepcopy(value)
    if change=="extra":value["observation"]["not_registered"]="private value"
    elif change=="source_values":value["observation"]["authority"]["source_values_names_routes_or_their_hashes_returned"]=True
    else:value["observation"]["authority"]["canonical_admitted"]=True
    with pytest.raises(ValueError):m._witness_valid(value,identity,metadata,True)


def test_nested_observation_prefix_extent_must_match_held_range_unit(tmp_path):
    _,_,_,metadata,value,identity=_fixture(tmp_path)
    value["observation"]["prefix_bytes"]=1
    # The pure component permits smaller supplied prefixes. THIS front is
    # bound to the independently held exact65,536-byte historical Range unit.
    m.pure.validate_prefix_nc_observation(value["observation"],fixture_only=True)
    with pytest.raises(m.PrefixNcObserveError,match="analysis_refused"):
        m._witness_valid(value,identity,metadata,True)


@pytest.mark.parametrize("failure",["old_replay","new_observer"])
def test_local_prefix_hash_waits_for_both_privacy_runs(tmp_path,monkeypatch,failure):
    root,raw,pins=_old(tmp_path);held=m.inherited._HeldPrefix(root,fixture=True,pins=pins);original=m._sha
    def digest(value):
        assert value!=raw,"hash before both finite rescreens"
        return original(value)
    def refuse(*args,**kwargs):raise ValueError("foreign private detail")
    monkeypatch.setattr(m,"_sha",digest)
    if failure=="old_replay":monkeypatch.setattr(m.capture,"_verify_files",refuse)
    else:monkeypatch.setattr(m.pure,"qualify_prefix_nc_structure",refuse)
    try:
        with pytest.raises(ValueError,match="foreign private detail"):m._analyse(_identity(root),CONTACT,held,fixture=True)
    finally:held.close()


@pytest.mark.parametrize("change",["extra","raw","contact_alias","authority","registration","identity"])
def test_preflight_schema_closed(tmp_path,change):
    _,_,_,metadata,_,identity=_fixture(tmp_path);plan=m._plan(identity,metadata)
    if change=="extra":plan["unknown"]=0
    elif change=="raw":plan["raw_prefix_read_or_hashed"]=True
    elif change=="contact_alias":plan["contact_reads"]=False
    elif change=="authority":plan["authority"]["files_written"]=1
    elif change=="registration":plan["registration_sha256"]="b"*64
    else:plan["execution_identity"]=dict(identity,head="b"*40)
    with pytest.raises(m.PrefixNcObserveError):m._plan_valid(plan,identity)


def test_preflight_proves_git_and_rechecks_before_return(tmp_path,monkeypatch):
    _,_,_,inputs,_,identity=_fixture(tmp_path);events=[]
    monkeypatch.setattr(m,"_identity",lambda head:(events.append("identity") or identity))
    monkeypatch.setattr(m,"_child",lambda role,identity:(events.append(role) or m._plan(identity,inputs)))
    monkeypatch.setattr(m.inherited,"_parent_proofs",lambda value:events.append("proofs"))
    result=m.preflight_actual(expected_head="a"*40)
    assert events==["identity","preflight","proofs","identity"] and result["plan"]["raw_prefix_read_or_hashed"] is False


def test_actual_front_held_context_mismatch_stops_before_contact(tmp_path,monkeypatch):
    identity=_identity(tmp_path);plan=m._plan(identity,{"schema":m.inherited.SCHEMA+"/original-input"});events=[]
    class Held:
        metadata={"different":"metadata"}
        def close(self):events.append("closed")
    monkeypatch.setattr(m,"_preflight",lambda head:(identity,plan));monkeypatch.setattr(m.inherited,"_HeldPrefix",lambda root:Held())
    monkeypatch.setattr(m.contact_io,"_stdin_contact",lambda:pytest.fail("contact read"))
    with pytest.raises(m.PrefixNcObserveError,match="inputs_changed"):m.observe_actual(expected_head="a"*40)
    assert events==["closed"]


def test_actual_front_final_drift_refuses_after_child_not_replay(tmp_path,monkeypatch):
    _,_,_,metadata,witness,identity=_fixture(tmp_path);events=[];identities=iter([identity,dict(identity,head="b"*40)])
    plan=m._plan(identity,metadata);witness["fixture_only"]=False
    class Held:
        def __init__(self):self.metadata=metadata
        def check(self):events.append("held")
        def close(self):events.append("closed")
    monkeypatch.setattr(m,"_preflight",lambda head:(identity,plan));monkeypatch.setattr(m.inherited,"_HeldPrefix",lambda root:Held())
    monkeypatch.setattr(m,"_identity",lambda head:next(identities));monkeypatch.setattr(m,"_current",lambda value:events.append("current"))
    monkeypatch.setattr(m.contact_io,"_stdin_contact",lambda:CONTACT)
    monkeypatch.setattr(m.privacy,"_contact",lambda value,**kw:value)  # Invented front ordering only, never actual contact.
    monkeypatch.setattr(m,"_child",lambda *args:(events.append("child") or witness))
    monkeypatch.setattr(m,"_witness_valid",lambda *args:None)
    with pytest.raises(m.PrefixNcObserveError,match="source_changed"):m.observe_actual(expected_head="a"*40)
    assert events.count("child")==1 and events[-1]=="closed"


@pytest.mark.parametrize("wire",[{"ok":1},{"ok":True,"value":{},"extra":0},{"ok":False,"refusal":{"phase":[],"code":"metadata_refused"}},
    {"ok":False,"refusal":{"phase":"analysis","code":"private foreign exception"}}, {"ok":False,"refusal":{"phase":"analysis","code":"analysis_refused","extra":0}}])
def test_native_wire_refusals_are_finite_and_closed(tmp_path,monkeypatch,wire):
    monkeypatch.setattr(m.inherited.old,"_run_child",lambda *a,**k:wire)
    with pytest.raises(m.PrefixNcObserveError):m._child("preflight",_identity(tmp_path))


@pytest.mark.parametrize("phase,code",[("privacy","finite_prefix_screen_refused"),("capacity","aggregate_payload_bound"),("replay","immutable_third_pass_counts_differ")])
def test_known_pure_error_stage_survives_native_wire_without_values(tmp_path,monkeypatch,phase,code):
    error=m.pure.NCStructureError(phase,code)
    assert m._safe(error,"analysis")=={"phase":phase,"code":code}
    monkeypatch.setattr(m.inherited.old,"_run_child",lambda *a,**k:{"ok":False,"refusal":m._safe(error,"analysis")})
    with pytest.raises(m.pure.NCStructureError) as observed:m._child("observe",_identity(tmp_path))
    assert observed.value.phase==phase and observed.value.code==code


@pytest.mark.parametrize("change",["phase_list","code_list","unknown","subclass","deleted"])
def test_unknown_or_malformed_pure_error_cannot_echo_or_break_sanitizer(change):
    error=m.pure.NCStructureError("privacy","finite_prefix_screen_refused")
    if change=="phase_list":error.phase=[]
    elif change=="code_list":error.code=[]
    elif change=="unknown":error.code=CONTACT
    elif change=="subclass":
        class Foreign(m.pure.NCStructureError):pass
        error=Foreign("privacy","finite_prefix_screen_refused")
    else:del error.phase
    assert m._safe(error,"analysis")=={"phase":"analysis","code":"analysis_refused"}


def test_command_initially_strong_native_and_no_secret_env(tmp_path):
    value=m._command("observe",_identity(tmp_path));text=" ".join(value)
    assert value[:2]==("/usr/bin/env","-i") and "-I" in value and "-S" in value and "-B" in value
    assert "(deny network*)" in text and "(deny process-fork)" in text and "(deny file-write*)" in text
    assert '"/usr/bin/security"' in text and "pycache_prefix="+m.EMPTY_CACHE_PREFIX in text
    assert CONTACT not in text and "API_TOKEN" not in text


def test_worker_isolation_and_compile_precede_input(tmp_path,monkeypatch):
    _,_,_,metadata,_,identity=_fixture(tmp_path);events=[]
    monkeypatch.setattr(m.previous,"_isolated",lambda:events.append("flags"))
    monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:events.append("isolation"))
    class Memory:
        def __init__(self):events.append("memory")
        def check(self):events.append("sample")
        def close(self):events.append("memory_closed")
    class Held:
        def __init__(self,root):self.metadata=metadata;events.append("held")
        def check(self):events.append("held_check")
        def close(self):events.append("held_closed")
    monkeypatch.setattr(m.previous,"_WorkerMemoryGuard",Memory);monkeypatch.setattr(m.inherited,"_HeldPrefix",Held)
    monkeypatch.setattr(m,"_current",lambda identity:events.append("current"))
    monkeypatch.setattr(m.capture,"_compile_sources",lambda identity:events.append("compile"))
    result=m._worker("preflight",identity)
    assert result["ok"] is True and events.index("isolation")<events.index("compile")<events.index("held")
    assert events[-2:]==["memory_closed","held_closed"] or events[-2:]==["held_closed","memory_closed"]
    assert result["value"]["raw_prefix_read_or_hashed"] is False


def test_worker_compile_refusal_precedes_held_or_stdin(tmp_path,monkeypatch):
    monkeypatch.setattr(m.previous,"_isolated",lambda:None);monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:None)
    monkeypatch.setattr(m.previous,"_WorkerMemoryGuard",lambda:SimpleNamespace(check=lambda:None,close=lambda:None))
    monkeypatch.setattr(m,"_current",lambda identity:None)
    monkeypatch.setattr(m.capture,"_compile_sources",lambda identity:(_ for _ in ()).throw(ValueError("foreign private error")))
    monkeypatch.setattr(m.inherited,"_HeldPrefix",lambda root:pytest.fail("held inputs before compile"))
    result=m._worker("observe",_identity(tmp_path))
    assert result=={"ok":False,"refusal":{"phase":"source","code":"metadata_refused"}}


def test_worker_current_source_refusal_precedes_compilation_and_inputs(tmp_path,monkeypatch):
    monkeypatch.setattr(m.previous,"_isolated",lambda:None);monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:None)
    monkeypatch.setattr(m.previous,"_WorkerMemoryGuard",lambda:SimpleNamespace(check=lambda:None,close=lambda:None))
    def changed(identity):raise m.PrefixNcObserveError("source_changed")
    monkeypatch.setattr(m,"_current",changed)
    monkeypatch.setattr(m.capture,"_compile_sources",lambda identity:pytest.fail("compile before source check"))
    monkeypatch.setattr(m.inherited,"_HeldPrefix",lambda root:pytest.fail("input before source check"))
    assert m._worker("observe",_identity(tmp_path))=={"ok":False,"refusal":{"phase":"source","code":"source_changed"}}


def test_identity_real_loaded_closure_and_canonical_internal_paths(monkeypatch):
    # Source-only component assembly, NOT a clean-Git/actual-front proof. Only
    # inherited Git acquisition is supplied; all NEW current/path validators
    # operate on genuine source bytes and the real loaded internal closure.
    sources=m.custody._source_bytes(m.LANE_ROOT,tuple(set(m._paths())|set(m.custody._internal_source_paths(m.LANE_ROOT))))
    identity={"root":str(m.LANE_ROOT),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}
    monkeypatch.setattr(m.previous,"_isolated",lambda:None)
    monkeypatch.setattr(m.inherited,"_identity",lambda head:identity)
    def source_git(root,*args):
        assert root==m.LANE_ROOT and args[0]=="show" and args[1].startswith("a"*40+":")
        return (root/args[1].split(":",1)[1]).read_bytes()
    monkeypatch.setattr(m.custody,"_git",source_git)
    value=m._identity("a"*40)
    assert set(m._paths())<=set(value["source_sha256"])
    assert {"data/__init__.py","data/hashing.py","ml/immutable_io.py"}<=set(value["source_sha256"])
    monkeypatch.setattr(m.custody,"_git",lambda *a:b"wrong committed source image")
    with pytest.raises(m.PrefixNcObserveError,match="source_changed"):m._identity("a"*40)


def test_worker_memory_guard_covers_stdout_write_flush_and_final_sample(tmp_path,monkeypatch):
    _,_,_,metadata,_,identity=_fixture(tmp_path);events=[];state={"live":False};output=io.BytesIO()
    monkeypatch.setattr(m.previous,"_isolated",lambda:None);monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:None)
    monkeypatch.setattr(m,"_current",lambda value:None);monkeypatch.setattr(m.capture,"_compile_sources",lambda value:None)
    class Memory:
        def __init__(self):state["live"]=True
        def check(self):assert state["live"];events.append("sample")
        def close(self):state["live"]=False;events.append("closed")
    class Held:
        def __init__(self,root):self.metadata=metadata
        def check(self):pass
        def close(self):pass
    class Buffer:
        def write(self,raw):assert state["live"];events.append("write");output.write(raw)
        def flush(self):assert state["live"];events.append("flush")
    monkeypatch.setattr(m.previous,"_WorkerMemoryGuard",Memory);monkeypatch.setattr(m.inherited,"_HeldPrefix",Held)
    monkeypatch.setattr(m.sys,"stdout",SimpleNamespace(buffer=Buffer()))
    assert m._worker("preflight",identity,publish=True) is None
    assert json.loads(output.getvalue())["ok"] is True
    assert events[-4:]==["write","flush","sample","closed"]


def test_cli_unknown_arg_never_echoes_value_and_restores_echo(monkeypatch,capsys):
    events=[];monkeypatch.setattr(m.contact_io,"_protect_stdin_echo",lambda:(events.append("protect") or "saved"))
    monkeypatch.setattr(m.contact_io,"_restore_stdin_echo",lambda saved:events.append(saved))
    assert m.main(["--expected-head","a"*40,"--unknown-private",CONTACT])==2
    captured=capsys.readouterr();assert CONTACT not in captured.out+captured.err and captured.err==""
    assert json.loads(captured.out)["code"]=="private_arguments_refused" and events==["protect","saved"]


def test_cli_preflight_does_not_require_or_read_contact(monkeypatch,capsys):
    monkeypatch.setattr(m,"preflight_actual",lambda **kw:{"own_ready":True})
    monkeypatch.setattr(m.contact_io,"_stdin_contact",lambda:pytest.fail("preflight contact"))
    assert m.main(["--expected-head","a"*40,"--preflight-only"])==0
    assert json.loads(capsys.readouterr().out)=={"own_ready":True}
