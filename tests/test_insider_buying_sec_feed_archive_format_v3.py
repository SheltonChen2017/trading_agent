"""Invented archive/controls only; external native network/Keychain denial."""
from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("fcntl",reason="macOS/POSIX custody")
pytest.importorskip("termios",reason="private stdin protection")
from research import insider_buying_sec_feed_archive_format_v3 as m

CONTACT="invented@unit.test"
PRIOR="0000000001-20-000001"


def _tar(body=b"<SUBMISSION>opaque</SUBMISSION>",*,name=b"invent.nc",kind=b"0"):
    header=bytearray(512);header[:len(name)]=name
    for at,size,value in ((100,8,b"0000600\0"),(108,8,b"0000000\0"),(116,8,b"0000000\0"),
        (124,12,format(len(body),"011o").encode()+b"\0"),(136,12,b"00000000000\0")):
        header[at:at+size]=value
    header[148:156]=b"        ";header[156:157]=kind;header[257:265]=b"ustar\0"+b"00"
    header[148:156]=format(sum(header),"06o").encode()+b"\0 "
    return bytes(header)+body+bytes((-len(body))%512)+bytes(1024)


def _response(body=None,headers=None,status=200):
    body=gzip.compress(_tar(),mtime=0) if body is None else body
    return m.directory.SecHttpResult(status,(("Content-Length",str(len(body))),) if headers is None else headers,body)


def _run(root,*,response=None,calls=None,hook=None,**kw):
    def wire(url,headers,cap):
        assert url==m.URL and cap==512*1024**2 and CONTACT in headers["User-Agent"]
        if calls is not None:calls.append((url,cap))
        if hook:hook()
        return _response() if response is None else response
    return m._invented(root=root,transport=wire,**kw)


def _base(root):return root.joinpath(*m.ARTIFACT_PARTS)
def _runpath(root):return _base(root)/"runs"/m.AUDIT_ID
def _read(path):return json.loads(path.read_bytes())


def test_fixed_unused_scope_literal_pins_no_alias_and_false_authority():
    reg=m.registration()
    assert m.URL=="https://www.sec.gov/Archives/edgar/Feed/2020/QTR4/20201007.nc.tar.gz"
    assert (reg["source_ordinal"],reg["listed_name"],reg["advertised_size_text"])==(5,"20201007.nc.tar.gz","390877 KB")
    assert reg["advertisement_is_priority_cue_not_measured_bytes"] is True
    assert reg["advertised_KB_base_or_rounding_qualified"] is False
    assert reg["maximum_GETs"]==1 and reg["transport_absolute_seconds"]==600 and reg["transport_idle_seconds"]==15
    assert reg["maximum_compressed_bytes"]==512*1024**2
    assert reg["native_worker_memory_policy"]["maximum_new_VM_growth_bytes"]==4*1024**3
    assert reg["native_worker_memory_policy"]["sampled_peak_RSS_fuse_bytes"]==4*1024**3
    assert reg["native_worker_memory_policy"]["instantaneous_or_hard_RSS_bound_claimed"] is False
    assert m.EMPTY_CACHE_PREFIX==m.batch.campaign.EMPTY_CACHE_PREFIX!=m.directory.EMPTY_CACHE_PREFIX
    reg["authority"]["backtesting_ready"]=True
    assert m.registration()["authority"]["backtesting_ready"] is False
    assert m.URL not in {m.old.URL,m.old.v1.URL}


def test_real_shaped_opaque_parent_is_not_admission_or_observed_membership(tmp_path):
    calls=[]
    def hook():
        run=_runpath(tmp_path)
        assert (run/"reservation.json").is_file() and (run/"request-start.json").is_file()
        assert (_base(tmp_path)/"claims"/m._claim_name()).is_file()
    result=_run(tmp_path,calls=calls,hook=hook,prior=[PRIOR])
    assert calls==[(m.URL,m.MAX_COMPRESSED)] and result["result"]["raw_transport_invocations"]==1
    run=_runpath(tmp_path);inspection=_read(run/"inspection.json")
    assert inspection["format"]["fixture_only"] is inspection["format"]["finite_privacy_screened"] is True
    assert inspection["overlap"]["known_consumed_dispatch_index_count"]==1
    assert inspection["overlap"]["archive_vs_known_accession_membership"]=="UNDETERMINED"
    assert inspection["overlap"]["observed_overlap_count"] is None
    assert inspection["overlap"]["ALL_members_quarantined_unextracted_unadmitted"] is True
    assert inspection["format"]["complete_submission_projection_created"] is inspection["format"]["backtesting_ready"] is False
    verified=m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)
    assert verified["current_contact_rescreen_and_engine_replay"] is True
    assert verified["original_current_contact_equality_attested"] is verified["original_contact_screen_replayed"] is False
    assert verified["result"]==result["result"]
    for path in _base(tmp_path).rglob("*"):
        if path.is_file():assert CONTACT.encode() not in path.read_bytes()


@pytest.mark.parametrize("raw",(gzip.compress(b"not a TAR",mtime=0),gzip.compress(_tar(name=b"../escape"),mtime=0),
    gzip.compress(_tar(kind=b"2"),mtime=0)))
def test_normal_engine_return_retains_full_raw_even_opaque_or_unsupported_profiles(tmp_path,raw):
    result=_run(tmp_path,response=_response(raw));assert result["result"]["response_retained"] is True
    inspection=_read(_runpath(tmp_path)/"inspection.json")
    assert inspection["format"]["tar"]["all_member_profiles_supported"] is False
    assert (_runpath(tmp_path)/"response.gz").read_bytes()==raw
    assert result["result"]["disposition"]=="whole_archive_retained_format_only_noncanonical"
    assert m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)["result"]==result["result"]


def test_multiple_gzip_segments_of_one_tar_are_preserved_unchanged(tmp_path):
    tar=_tar();raw=gzip.compress(tar[:511],mtime=0)+gzip.compress(tar[511:],mtime=0)
    result=_run(tmp_path,response=_response(raw));inspection=_read(_runpath(tmp_path)/"inspection.json")
    assert len(inspection["format"]["gzip_members"])==2
    assert result["result"]["compressed_sha256"]==hashlib.sha256(raw).hexdigest()
    assert (_runpath(tmp_path)/"response.gz").read_bytes()==raw


@pytest.mark.parametrize("fault",("crc","trailing","body_contact","header_contact","header_encoded_contact","length"))
def test_engine_or_header_privacy_failure_retains_no_response_or_header(tmp_path,fault):
    response=_response();raw=response.body;headers=response.headers
    if fault=="crc":raw=raw[:-8]+bytes([raw[-8]^1])+raw[-7:]
    elif fault=="trailing":raw+=b"garbage"
    elif fault=="body_contact":raw=gzip.compress(_tar(CONTACT.encode()),mtime=0)
    elif fault=="header_contact":headers=(("Content-Length",str(len(raw))),("X-Diagnostic",CONTACT))
    elif fault=="header_encoded_contact":headers=(("Content-Length",str(len(raw))),("X-Diagnostic","invented%40unit.test"))
    else:headers=(("Content-Length",str(len(raw)+1)),)
    if fault in {"crc","trailing","body_contact"}:headers=(("Content-Length",str(len(raw))),)
    result=_run(tmp_path,response=_response(raw,headers));run=_runpath(tmp_path)
    assert result["result"]["response_retained"] is False and result["result"]["inspection_refusal"]
    assert not (run/"response.gz").exists() and not (run/"response-headers.json").exists() and not (run/"inspection.json").exists()
    assert result["result"]["compressed_sha256"] is result["result"]["response_headers_sha256"] is None
    assert m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)["result"]==result["result"]


@pytest.mark.parametrize("status",(301,403,429,500))
def test_non200_has_no_body_retention_or_retry(tmp_path,status):
    calls=[];result=_run(tmp_path,response=_response(b"unread",status=status),calls=calls)
    assert len(calls)==1 and result["result"]["disposition"]=="non200_body_unread_no_retry"
    assert result["result"]["compressed_bytes"] is None and not (_runpath(tmp_path)/"response.gz").exists()


def test_ambiguous_transport_is_consumed_once_and_not_resumed(tmp_path):
    calls=[]
    def broken(*args):calls.append(1);raise RuntimeError(CONTACT)
    first=m._invented(root=tmp_path,transport=broken)
    assert first["result"]["disposition"]=="ambiguous_transport_failure_no_retry" and calls==[1]
    with pytest.raises(m.ArchiveFormatError,match="fresh_namespace_already_exists"):
        m._invented(root=tmp_path,transport=broken)
    assert calls==[1]


@pytest.mark.parametrize("suffix",((),("claims","runs")))
def test_existing_empty_final_namespace_refuses_before_contact_or_wire(tmp_path,suffix):
    base=_base(tmp_path);base.mkdir(parents=True)
    for name in suffix:(base/name).mkdir()
    before={str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")};calls=[]
    with pytest.raises(m.ArchiveFormatError,match="fresh_namespace_already_exists"):
        _run(tmp_path,contact=lambda:calls.append("contact"),calls=calls)
    assert calls==[] and before=={str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}


def test_capacity_refuses_before_private_contact_or_claim(tmp_path,monkeypatch):
    calls=[];monkeypatch.setattr(m.os,"fstatvfs",lambda _:SimpleNamespace(f_bavail=1,f_frsize=1))
    with pytest.raises(m.ArchiveFormatError,match="disk_reserve_refused"):_run(tmp_path,contact=lambda:calls.append("contact"),calls=calls)
    assert calls==[] and not (_runpath(tmp_path)/"reservation.json").exists()
    assert not _base(tmp_path).exists()


def test_source_guard_failure_is_before_new_output_and_contact(tmp_path):
    calls=[]
    def refused():raise ValueError(CONTACT)
    with pytest.raises(ValueError):_run(tmp_path,guard=refused,contact=lambda:calls.append(1),calls=calls)
    assert calls==[] and not _base(tmp_path).exists()


def test_held_input_mutation_after_start_blocks_transport(tmp_path):
    calls=[];count=[0]
    def guard():
        count[0]+=1
        if (_runpath(tmp_path)/"request-start.json").exists():raise ValueError(CONTACT)
    with pytest.raises(m.ArchiveFormatError):_run(tmp_path,guard=guard,calls=calls)
    assert calls==[] and count[0]>1


@pytest.mark.parametrize("phase,code",(("gzip-trailer","crc32_mismatch"),("gzip-header","reserved_flags_set"),("privacy","finite_screen_refused")))
def test_precise_frozen_engine_refusal_is_finite(phase,code):
    assert m._engine_refusal(m.engine.FeedFormatError(phase,code))=={"phase":phase,"code":code}
    assert CONTACT not in json.dumps(m._engine_refusal(RuntimeError(CONTACT)))


def test_invented_identity_and_noop_guard_cannot_register_real_dispatch(tmp_path,monkeypatch):
    calls=[];identity={"invented":True};activation=m._Activation(identity,lambda:None)
    context=m._Dispatch(m._TOKEN,activation,identity,lambda:None,lambda:None,{"User-Agent":CONTACT})
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**k:calls.append(1))
    with pytest.raises(m.ArchiveFormatError,match="trusted_activation_required"):m._transport(context)
    assert calls==[] and context.attempted is False
    with pytest.raises(m.ArchiveFormatError,match="dispatch_context_refused"):m._transport(object())


def test_native_command_initial_controls_no_private_payload_in_argv():
    command=m._command("inspect",{"invented_source_only":True});joined=" ".join(command)
    for text in ("-I","-S","-B","deny network*","deny process-fork","deny file-write*","/usr/bin/security",m.EMPTY_CACHE_PREFIX):assert text in joined
    assert CONTACT not in joined and m.URL not in joined
    assert "_worker('inspect'" in joined and "publish=True" in joined and "insider_buying_sec_feed_archive_format_v3" in joined


def test_actual_inspector_never_uses_fixture_mode(monkeypatch):
    raw=_response().body;headers=_response(raw).headers;seen=[];real=m.engine.inspect_gzip_tar_format;contact_calls=[]
    # Only the supplied contact validator is a fixture seam. Assert that BOTH
    # wrapper and engine ask for actual-mode validation; no real contact read.
    monkeypatch.setattr(m.privacy,"_contact",lambda value,*,observed:(contact_calls.append(observed),value)[1])
    monkeypatch.setattr(m.engine,"inspect_gzip_tar_format",lambda body,**kw:(seen.append(kw),real(body,**kw))[1])
    m._inspect(raw,headers,CONTACT,[PRIOR],fixture=False)
    assert seen==[{"privacy_contact":CONTACT,"fixture_only":False}]
    assert contact_calls==[True,True]


@pytest.mark.parametrize("leaf",("complete.json","reservation.json","request-start.json","request-result.json","inspection.json","response.gz","response-headers.json"))
def test_strict_independent_readback_refuses_changed_raw_or_controls(tmp_path,leaf):
    result=_run(tmp_path);path=_runpath(tmp_path)/leaf;raw=path.read_bytes();path.write_bytes(raw+b" ")
    with pytest.raises(ValueError):m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)


def test_readback_current_contact_different_is_not_original_contact_attestation(tmp_path):
    result=_run(tmp_path)
    value=m._verify_files(tmp_path,result["complete_sha256"],"different@unit.test",fixture=True)
    assert value["current_contact_rescreen_and_engine_replay"] is True
    assert value["original_current_contact_equality_attested"] is value["original_contact_screen_replayed"] is False


def test_readback_current_contact_echo_refuses_without_rewrite(tmp_path):
    response=_response(gzip.compress(_tar(b"different@unit.test"),mtime=0));result=_run(tmp_path,response=response)
    before={str(p):p.read_bytes() for p in _runpath(tmp_path).iterdir()}
    with pytest.raises(ValueError):m._verify_files(tmp_path,result["complete_sha256"],"different@unit.test",fixture=True)
    assert before=={str(p):p.read_bytes() for p in _runpath(tmp_path).iterdir()}


def test_unbound_header_control_extra_refuses_with_unchanged_external_complete_pin(tmp_path):
    result=_run(tmp_path);path=_runpath(tmp_path)/"response-headers.json"
    value=_read(path);value["unregistered_extra"]="invented_unbound_extra";path.write_bytes(m._raw(value))
    with pytest.raises(m.ArchiveFormatError):m._verify_files(tmp_path,result["complete_sha256"],CONTACT,fixture=True)


@pytest.mark.parametrize("arguments",(("--help",),("--invalid",),("--expected-head","private-invalid")))
def test_cli_echo_protection_before_parser_and_restoration(monkeypatch,arguments,capsys):
    calls=[];monkeypatch.setattr(m.contact_io,"_protect_stdin_echo",lambda:calls.append("protect") or "saved")
    monkeypatch.setattr(m.contact_io,"_restore_stdin_echo",lambda saved:calls.append(("restore",saved)))
    monkeypatch.setattr(m,"run_actual",lambda _:(_ for _ in ()).throw(RuntimeError(CONTACT)))
    try:m.main(list(arguments))
    except SystemExit:pass
    assert calls==["protect",("restore","saved")] and CONTACT not in capsys.readouterr().out


def test_foreign_private_exception_text_never_public(monkeypatch,capsys):
    monkeypatch.setattr(m.contact_io,"_protect_stdin_echo",lambda:None);monkeypatch.setattr(m.contact_io,"_restore_stdin_echo",lambda _:None)
    monkeypatch.setattr(m,"run_actual",lambda _:(_ for _ in ()).throw(RuntimeError(CONTACT)))
    assert m.main(["--expected-head","a"*40])==2
    out=capsys.readouterr().out;assert CONTACT not in out and "local_operation_refused" in out


@pytest.fixture(scope="module")
def genuine_plan(tmp_path_factory):
    path=Path(__file__).with_name("test_insider_buying_pilot_sec_parent_batch_capture_v2.py")
    spec=importlib.util.spec_from_file_location("invented_archive_v3_batch_fixture",path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    corpus=helper.corpus.__wrapped__(tmp_path_factory)
    return helper,helper.plan.__wrapped__(corpus)


def _directory_response():
    items=[]
    for day in ("01","02","05","06","07"):
        name="202010"+day+".nc.tar.gz"
        items.append({"name":name,"href":name,"type":"file","size":"390877 KB" if day=="07" else "500000 KB","last-modified":"opaque display"})
    body=m._raw({"directory":{"name":"opaque","parent-dir":"opaque","item":items}})
    return m.directory.SecHttpResult(200,(("Content-Length",str(len(body))),),body)


@pytest.fixture(scope="module")
def populated_inputs(tmp_path_factory,genuine_plan):
    root=tmp_path_factory.mktemp("invented_archive_v3_inputs")
    helper,plan=genuine_plan
    m.directory._run_invented_probe(root=root,transport=lambda *a:_directory_response())
    helper._run(root,plan)
    return root


def _populate_inputs(root,populated_inputs):
    # Recreate the tiny listing at this exact fixture root; do not relabel its
    # source identity by copying a different root's signed control chain.
    source=populated_inputs.joinpath(*m.batch.ARTIFACT_PARTS);target=root.joinpath(*m.batch.ARTIFACT_PARTS)
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,target)
    m.directory._run_invented_probe(root=root,transport=lambda *a:_directory_response())


def test_real_shaped_listing_and_complete_batch_metadata_hold_no_original_bodies(tmp_path,populated_inputs,monkeypatch):
    _populate_inputs(tmp_path,populated_inputs)
    seen=[];read=m.batch.archive._Output.read
    def only_metadata(self,name,*args,**kw):
        seen.append((str(self.path),name));assert not (self.path.name=="objects" and name.endswith(".bin"))
        return read(self,name,*args,**kw)
    monkeypatch.setattr(m.batch.archive._Output,"read",only_metadata)
    held=m._Inputs(tmp_path,fixture=True)
    try:
        summary=held.metadata
        assert summary["directory"]["selected_row"]["source_ordinal"]==5
        assert summary["directory"]["selected_row"]["advertised_size_text"]=="390877 KB"
        assert len(summary["prior_accessions"])>=64 and summary["old_original_body_bytes_read"]==0
        assert summary["unknown_June_archive_memberships_known"] is False
        assert any(name.endswith("-headers.json") for _,name in seen)
        assert any(name.endswith("-start.json") for _,name in seen)
        held.check()
    finally:held.close()


@pytest.mark.parametrize("kind",("listing","consumed","journal","headers","samebyte_ctime"))
def test_old_hold_rechecks_full_metadata_and_initial_ctimes(tmp_path,populated_inputs,kind):
    _populate_inputs(tmp_path,populated_inputs);held=m._Inputs(tmp_path,fixture=True)
    try:
        if kind=="listing":path=tmp_path.joinpath(*m.directory.ARTIFACT_PARTS,"runs",m.directory.AUDIT_ID,"response.bin")
        elif kind=="consumed":path=held.snap.run.path/"consumed-index.json"
        elif kind=="journal":path=held.snap.run.path/"request-0000-start.json"
        else:path=held.snap.run.path/"request-0000-headers.json"
        raw=path.read_bytes();path.write_bytes(raw if kind=="samebyte_ctime" else raw+b" ")
        with pytest.raises(ValueError):held.check()
    finally:held.close()


def test_old_consumed_scope_EX_lock_prevents_new_hold(tmp_path,populated_inputs):
    _populate_inputs(tmp_path,populated_inputs)
    path=tmp_path.joinpath(*m.batch.ARTIFACT_PARTS,"batches",m.batch.campaign._batch(1),"scope.lock")
    fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
    try:
        m.fcntl.flock(fd,m.fcntl.LOCK_EX|m.fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):m._Inputs(tmp_path,fixture=True)
    finally:os.close(fd)


def test_new_input_replay_does_not_omit_original_Q4_exact_header_control_schema(tmp_path,populated_inputs):
    _populate_inputs(tmp_path,populated_inputs)
    path=tmp_path.joinpath(*m.directory.ARTIFACT_PARTS,"runs",m.directory.AUDIT_ID,"response-headers.json")
    value=_read(path);value["unregistered_extra"]="invented_unbound_extra";path.write_bytes(m._raw(value))
    with pytest.raises(m.ArchiveFormatError,match="directory_header_control_schema_refused"):m._Inputs(tmp_path,fixture=True)


@pytest.mark.parametrize("front,phase",(("source","source"),("native","native_preflight")))
def test_actual_front_source_or_native_refusal_precedes_inputs_and_contact(monkeypatch,front,phase):
    seen=[]
    monkeypatch.setattr(m,"_identity",lambda _:(_ for _ in ()).throw(ValueError(CONTACT)) if front=="source" else {"invented":True})
    monkeypatch.setattr(m,"_child",lambda *a,**k:{"ok":False,"refusal":{}})
    monkeypatch.setattr(m,"_Inputs",lambda *a,**k:seen.append("inputs"))
    monkeypatch.setattr(m.contact_io,"_stdin_contact",lambda:seen.append("contact"))
    with pytest.raises(m.ArchiveFormatError) as caught:m.run_actual("a"*40)
    assert caught.value.phase==phase and seen==[] and CONTACT not in str(caught.value)


def test_native_initial_denial_precedes_first_private_stdin_or_input(monkeypatch):
    calls=[];monkeypatch.setattr(m,"_isolated",lambda:None)
    monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:(_ for _ in ()).throw(ValueError("denied fixture")))
    monkeypatch.setattr(m,"_current",lambda _:calls.append("source"))
    monkeypatch.setattr(m.sys,"stdin",SimpleNamespace(buffer=SimpleNamespace(readline=lambda _:calls.append("private"))))
    with pytest.raises(ValueError):m._worker("inspect",{})
    assert calls==[]


@pytest.mark.parametrize("fault",("bool_attempt","extra","parent_requests","contact_hash","measured","wrong_disposition"))
def test_coherently_resealed_non200_result_cannot_weaken_exact_contract(tmp_path,fault):
    result=_run(tmp_path,response=_response(b"",status=403));run=_runpath(tmp_path)
    value=_read(run/"request-result.json")
    if fault=="bool_attempt":value["raw_transport_invocations"]=True
    elif fault=="extra":value["unknown"]=True
    elif fault=="parent_requests":value["individual_parent_requests"]=1
    elif fault=="contact_hash":value["contact_value_stored_or_hashed"]=True
    elif fault=="measured":value["remote_request_count_measured"]=True
    else:value["disposition"]="whole_archive_retained_format_only_noncanonical"
    raw=m._raw(value);(run/"request-result.json").write_bytes(raw)
    complete=_read(run/"complete.json");complete["result"]=value;complete["result_sha256"]=m._sha(raw)
    raw=m._raw(complete);(run/"complete.json").write_bytes(raw)
    with pytest.raises(ValueError):m._verify_files(tmp_path,m._sha(raw),CONTACT,fixture=True)


def _unit_dispatch(monkeypatch,*,guard=lambda:None,prove=lambda:None):
    identity={"invented_source_only":True};activation=m._Activation(identity,guard)
    # A test-only registry seam, NEVER the public constructor's authority.
    m._ACTIVATIONS[activation]=(m._raw(identity),id(guard))
    context=m._Dispatch(m._TOKEN,activation,identity,guard,prove,{"User-Agent":"invented private agent","Accept-Encoding":"identity"})
    signals=[];monkeypatch.setattr(m.signal,"getitimer",lambda _:(0.,0.))
    monkeypatch.setattr(m.signal,"getsignal",lambda _:"prior handler")
    monkeypatch.setattr(m.signal,"signal",lambda *a:signals.append(("signal",a)))
    monkeypatch.setattr(m.signal,"setitimer",lambda *a:signals.append(("timer",a)))
    return context,signals


@pytest.mark.parametrize("status",(200,301,403,429))
def test_real_transport_logic_exact_one_GET_idle_wall_and_non200_unread(monkeypatch,status):
    calls=[];raw=_response().body;headers=(("Content-Length",str(len(raw))),)
    context,signals=_unit_dispatch(monkeypatch,guard=lambda:calls.append("guard"),prove=lambda:calls.append("prove"))
    class Response:
        chunked=False
        def __init__(self):self.status=status
        def getheaders(self):return headers
        def read(self,count):calls.append(("read",count));assert status==200;return raw
    class Connection:
        def __init__(self,host,*,timeout):calls.append(("open",host,timeout))
        def request(self,*args,**kw):calls.append(("request",args,kw))
        def getresponse(self):return Response()
        def close(self):calls.append("close")
    monkeypatch.setattr(m.http.client,"HTTPSConnection",Connection)
    result=m._transport(context)
    assert result.status==status and context.attempted is True
    assert calls.count(("open","www.sec.gov",15))==1
    request=next(c for c in calls if type(c)is tuple and c[0]=="request")
    assert request==("request",("GET","/Archives/edgar/Feed/2020/QTR4/20201007.nc.tar.gz"),{"headers":context.headers})
    assert calls.index("prove")<calls.index(("open","www.sec.gov",15)) and calls[-1]=="close"
    assert ("timer",(m.signal.ITIMER_REAL,600)) in signals and ("timer",(m.signal.ITIMER_REAL,0)) in signals
    assert signals[-1]==("signal",(m.signal.SIGALRM,"prior handler"))
    if status!=200:assert not any(type(c)is tuple and c[0]=="read" for c in calls) and result.body==b""
    with pytest.raises(m.ArchiveFormatError,match="dispatch_context_refused"):m._transport(context)


@pytest.mark.parametrize("fault",("guard","proof","headers","identity"))
def test_real_transport_refuses_changed_context_or_custody_before_socket(monkeypatch,fault):
    calls=[]
    def bad():raise ValueError(CONTACT)
    context,_=_unit_dispatch(monkeypatch,guard=bad if fault=="guard" else lambda:None,prove=bad if fault=="proof" else lambda:None)
    if fault=="headers":context.headers["Accept-Encoding"]="gzip"
    if fault=="identity":context.identity["changed"]=True
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**kw:calls.append("open"))
    with pytest.raises(ValueError):m._transport(context)
    assert calls==[] and context.attempted is False


@pytest.mark.parametrize("fault",("idle","wall","truncated","oversize","bad_chunk_terminal","drip_wall"))
def test_real_transport_failure_does_not_retry_and_restores_timer_connection(monkeypatch,fault):
    calls=[];raw=_response().body;context,signals=_unit_dispatch(monkeypatch)
    class Response:
        status=200;chunked=True
        def getheaders(self):return (("Transfer-Encoding","chunked"),) if fault=="bad_chunk_terminal" else (("Content-Length",str(m.MAX_COMPRESSED+1 if fault=="oversize" else len(raw))),)
        def read(self,count):
            calls.append(("read",count))
            if fault=="idle":raise TimeoutError("private idle"+CONTACT)
            if fault=="wall":raise m._AbsoluteDeadline()
            return raw[:-1] if fault=="truncated" else raw if len(calls)==2 else b"nonterminal"
        def isclosed(self):return False
    class Connection:
        def __init__(self,*a,**k):calls.append("open")
        def request(self,*a,**k):pass
        def getresponse(self):return Response()
        def close(self):calls.append("close")
    monkeypatch.setattr(m.http.client,"HTTPSConnection",Connection)
    if fault=="drip_wall":
        ticks=iter((0,601));monkeypatch.setattr(m.time,"monotonic",lambda:next(ticks))
    with pytest.raises((ValueError,TimeoutError)) as caught:m._transport(context)
    assert calls.count("open")==1 and calls[-1]=="close" and context.attempted is True
    assert ("timer",(m.signal.ITIMER_REAL,0)) in signals
    if fault in {"wall","drip_wall"}:assert caught.value.args==("absolute_transport_deadline",)


def test_real_transport_cleanup_failure_preserves_primary(monkeypatch):
    context,_=_unit_dispatch(monkeypatch)
    class Connection:
        def __init__(self,*a,**kw):pass
        def request(self,*a,**kw):raise RuntimeError("original private failure")
        def close(self):raise RuntimeError("cleanup private failure")
    monkeypatch.setattr(m.http.client,"HTTPSConnection",Connection)
    with pytest.raises(RuntimeError,match="original private failure"):m._transport(context)


def test_actual_hold_cleanup_preserves_primary_but_classifies_cleanup_only_failure(monkeypatch):
    identity={"invented":True};plan={"inputs":{}}
    monkeypatch.setattr(m,"_identity",lambda _:identity);monkeypatch.setattr(m,"_child",lambda *a:{"ok":True,"value":plan})
    monkeypatch.setattr(m,"_parent_plan_proofs",lambda _:None)
    class Hold:
        metadata={}
        def close(self):raise RuntimeError(CONTACT)
    monkeypatch.setattr(m,"_Inputs",lambda *a:Hold())
    def primary(**_):raise m._at("inspection",m.ArchiveFormatError("local_operation_refused"))
    monkeypatch.setattr(m,"_run",primary)
    with pytest.raises(m.ArchiveFormatError) as caught:m.run_actual("a"*40)
    assert caught.value.phase=="inspection"
    monkeypatch.setattr(m,"_run",lambda **_:"success")
    with pytest.raises(m.ArchiveFormatError) as caught:m.run_actual("a"*40)
    assert caught.value.phase=="cleanup" and CONTACT not in str(caught.value)


def test_outer_run_cleanup_preserves_primary_even_if_drain_helper_itself_fails(tmp_path,monkeypatch):
    real=m.publication._close_all
    def drain(*args,**kwargs):real(*args,**kwargs);raise RuntimeError(CONTACT)
    monkeypatch.setattr(m.publication,"_close_all",drain)
    def guard():
        if (_runpath(tmp_path)/"request-start.json").exists():raise ValueError("primary source refusal")
    with pytest.raises(m.ArchiveFormatError) as caught:_run(tmp_path,guard=guard)
    assert caught.value.phase=="start" and CONTACT not in str(caught.value)


def test_maximum_metadata_IPC_and_actual_full_roster_controls_capacity(tmp_path):
    sources={m.SELF_PATH:"a"*64,m.TEST_PATH:"b"*64,**{f"research/invented_capacity_{i:03d}.py":"c"*64 for i in range(140)}}
    identity={"root":str(tmp_path),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,"source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}
    prior=[f"{i:010d}-20-000001" for i in range(20044)]
    plan={"execution_identity":identity,"inputs":{"prior_accessions":prior,"provenance_capacity_only_not_observed":True,
        "capture_execution_identity":identity,"directory_original_identity":identity,"planner_identity":identity}}
    result=m._capacity_proof(identity,plan)
    assert 31*1024**2<=result["format_descriptor_bytes"]<=32*1024**2
    assert result["own_IPC_envelope_bytes"]>31*1024**2 and result["exact_64MiB_3M_node_archive_codec_roundtrip"] is True
    assert result["template_published_or_retained"] is False and result["capacity_only_not_source_observation"] is True
    assert 0<result["format_member_layout_count"]<=100000 and not list(tmp_path.iterdir())


def _memory_seam(monkeypatch,*,baseline=415*1024**3,soft=None,hard=None,readback_bad=False):
    infinity=m.resource.RLIM_INFINITY;soft=infinity if soft is None else soft;hard=infinity if hard is None else hard
    state={"limit":(soft,hard),"calls":[]}
    monkeypatch.setattr(m,"_self_memory",lambda:(baseline,20*1024**2))
    monkeypatch.setattr(m,"_rss_sample",lambda:None)
    monkeypatch.setattr(m.resource,"getrlimit",lambda _:(state["limit"][0]-1,state["limit"][1]) if readback_bad and state["calls"] else state["limit"])
    def set_limit(kind,value):state["calls"].append((kind,value));state["limit"]=value
    monkeypatch.setattr(m.resource,"setrlimit",set_limit)
    return state


@pytest.mark.parametrize("stricter",(False,True))
def test_memory_guard_measured_VM_growth_preserves_existing_hard_and_stricter_soft(monkeypatch,stricter):
    baseline=415*1024**3;soft=baseline+128*1024**2 if stricter else m.resource.RLIM_INFINITY
    state=_memory_seam(monkeypatch,baseline=baseline,soft=soft)
    guard=m._WorkerMemoryGuard()
    try:
        expected=min(baseline+4*1024**3,soft)
        assert state["calls"]==[(m.resource.RLIMIT_AS,(expected,m.resource.RLIM_INFINITY))]
        assert guard.thread.daemon and guard.thread.is_alive()
        guard.check()
    finally:guard.close()
    assert not guard.thread.is_alive() and guard.stop.is_set()


@pytest.mark.parametrize("fault",("soft_bool","soft_above_hard","no_growth","readback","install"))
def test_memory_limit_invalid_existing_or_install_refuses_before_thread_and_inputs(monkeypatch,fault):
    baseline=415*1024**3
    state=_memory_seam(monkeypatch,baseline=baseline,soft=True if fault=="soft_bool" else baseline if fault=="no_growth" else baseline+512*1024**2,
        hard=baseline+256*1024**2 if fault=="soft_above_hard" else None,readback_bad=fault=="readback")
    calls=[];monkeypatch.setattr(m.threading,"Thread",lambda *a,**k:calls.append("thread"))
    if fault=="install":monkeypatch.setattr(m.resource,"setrlimit",lambda *a:(_ for _ in ()).throw(ValueError("unsupported fixture")))
    with pytest.raises(ValueError):m._WorkerMemoryGuard()
    assert calls==[]


@pytest.mark.parametrize("fault",("short","zero_VM","zero_RSS","RSS_above_VM","overflow_VM"))
def test_fixed_self_libproc_exact_96_byte_metric_and_invalid_baseline(monkeypatch,fault):
    calls=[];virtual,resident=(415*1024**3,20*1024**2)
    if fault=="zero_VM":virtual=0
    elif fault=="zero_RSS":resident=0
    elif fault=="RSS_above_VM":resident=virtual+1
    elif fault=="overflow_VM":virtual=(1<<63)-1
    class Call:
        def __call__(self,pid,flavor,arg,buffer,size):
            calls.append((pid,flavor,arg,size))
            raw=virtual.to_bytes(8,sys.byteorder)+resident.to_bytes(8,sys.byteorder)+bytes(80)
            m.ctypes.memmove(buffer,raw,96);return 95 if fault=="short" else 96
    call=Call();monkeypatch.setattr(m.ctypes,"CDLL",lambda path,**kw:(calls.append((path,kw)),SimpleNamespace(proc_pidinfo=call))[1])
    with pytest.raises(m.ArchiveFormatError,match="self_memory_metric_refused"):m._self_memory()
    assert calls[0]==("/usr/lib/libproc.dylib",{"use_errno":True})
    assert calls[1]==(os.getpid(),4,0,96) and call.restype is m.ctypes.c_int


def test_fixed_self_libproc_bytes_not_KB_or_pages(monkeypatch):
    class Call:
        def __call__(self,pid,flavor,arg,buffer,size):
            m.ctypes.memmove(buffer,(415*1024**3).to_bytes(8,sys.byteorder)+(24*1024**2).to_bytes(8,sys.byteorder)+bytes(80),96);return 96
    monkeypatch.setattr(m.ctypes,"CDLL",lambda *a,**kw:SimpleNamespace(proc_pidinfo=Call()))
    assert m._self_memory()==(415*1024**3,24*1024**2)


@pytest.mark.parametrize("peak",(0,True,1.0,4*1024**3+1))
def test_sampled_Darwin_peak_RSS_fuse_rejects_invalid_or_overshoot(monkeypatch,peak):
    seen=[];monkeypatch.setattr(m.resource,"getrusage",lambda kind:(seen.append(kind),SimpleNamespace(ru_maxrss=peak))[1])
    with pytest.raises(m.ArchiveFormatError,match="sampled_peak_RSS_fuse_refused"):m._rss_sample()
    assert seen==[m.resource.RUSAGE_SELF]


@pytest.mark.parametrize("fails",(False,True))
def test_RSS_fuse_metric_failure_terminates_worker_only_with_finite_status(monkeypatch,fails):
    calls=[]
    def sample():
        if fails:raise RuntimeError(CONTACT)
    monkeypatch.setattr(m,"_rss_sample",sample);monkeypatch.setattr(m.os,"_exit",lambda status:calls.append(status))
    assert m._rss_fuse_once() is (not fails)
    assert calls==([2] if fails else [])


def test_RSS_daemon_requested_interval_and_monitor_liveness_are_mandatory(monkeypatch):
    guard=object.__new__(m._WorkerMemoryGuard);waits=[]
    guard.stop=SimpleNamespace(wait=lambda seconds:(waits.append(seconds),False)[1])
    monkeypatch.setattr(m,"_rss_fuse_once",lambda:False);guard._watch()
    assert waits==[0.05] and waits[0]<=0.1
    guard.stop=SimpleNamespace(is_set=lambda:False);guard.thread=SimpleNamespace(is_alive=lambda:False)
    with pytest.raises(m.ArchiveFormatError,match="RSS_monitor_not_live"):guard.check()


def test_RSS_final_sample_failure_still_stops_and_joins_monitor(monkeypatch):
    guard=object.__new__(m._WorkerMemoryGuard);calls=[]
    guard.stop=SimpleNamespace(is_set=lambda:False,set=lambda:calls.append("stop"))
    guard.thread=SimpleNamespace(is_alive=lambda:True,join=lambda **kw:calls.append(("join",kw)))
    monkeypatch.setattr(m,"_rss_sample",lambda:(_ for _ in ()).throw(m.ArchiveFormatError("sampled_peak_RSS_fuse_refused")))
    with pytest.raises(m.ArchiveFormatError,match="sampled_peak_RSS_fuse_refused"):guard.close()
    assert calls==["stop",("join",{"timeout":0.25})]


def test_memory_guard_install_failure_precedes_source_or_private_input(monkeypatch):
    calls=[];monkeypatch.setattr(m,"_isolated",lambda:calls.append("flags"))
    monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:calls.append("native"))
    def refused():calls.append("memory");raise ValueError("unsupported fixture")
    monkeypatch.setattr(m,"_WorkerMemoryGuard",refused);monkeypatch.setattr(m,"_current",lambda _:calls.append("source"))
    monkeypatch.setattr(m.sys,"stdin",SimpleNamespace(buffer=SimpleNamespace(readline=lambda _:calls.append("private"))))
    with pytest.raises(ValueError):m._worker("inspect",{})
    assert calls==["flags","native","memory"]


def test_memory_monitor_covers_serialization_stdout_drain_and_final_sample(monkeypatch):
    calls=[];monkeypatch.setattr(m,"_isolated",lambda:calls.append("flags"));monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:calls.append("native"))
    class Guard:
        def __init__(self):calls.append("install")
        def check(self):calls.append("sample")
        def close(self):calls.append("final_close_sample")
    monkeypatch.setattr(m,"_WorkerMemoryGuard",Guard)
    monkeypatch.setattr(m,"_guarded_worker",lambda *a:{"ok":True,"value":{"invented":True}})
    encode=m._raw
    monkeypatch.setattr(m,"_raw",lambda value:(calls.append("serialize"),encode(value))[1])
    output=[]
    class Pipe:
        def write(self,raw):calls.append("stdout_write");output.append(raw)
        def flush(self):calls.append("stdout_flush")
    monkeypatch.setattr(m.sys,"stdout",SimpleNamespace(buffer=Pipe()))
    assert m._worker("inspect",{},publish=True) is None
    assert calls==["flags","native","install","serialize","sample","stdout_write","stdout_flush","sample","final_close_sample"]
    assert output==[b'{"ok":true,"value":{"invented":true}}\n']


@pytest.mark.parametrize("ambient_legacy_test_paths",(False,True))
def test_actual_identity_inherits_complete_campaign_string_named_test_roster(monkeypatch,ambient_legacy_test_paths):
    # Source bytes only, no artifact/Git/process/network action. The invented
    # base identity is NOT proof of a clean committed production checkout.
    campaign=m.batch.campaign;calls=[]
    required={campaign.SELF_PATH,campaign.TEST_PATH,campaign.CAPTURE_SOURCE_PATH,campaign.CAPTURE_TEST_PATH,
        campaign.first.SELF_PATH,campaign.first.TEST_PATH,campaign.archive.SELF_PATH,campaign.archive.TEST_PATH,
        campaign.source.SELF_PATH,"research/insider_buying_sec_feed_archive_sample_v2.py",
        "tests/test_insider_buying_sec_feed_archive_sample_v2.py","tests/test_insider_buying_pilot_sec_fresh_selection_runner.py",
        campaign.base.SELF_PATH,"tests/test_insider_buying_pilot_sec_parent_audit_runner.py",campaign.source.retained.SELF_PATH,
        "tests/test_insider_buying_pilot_sec_parent_structure_runner.py"}
    static=set(m.custody._internal_source_paths(m.LANE_ROOT))
    omitted={campaign.first.TEST_PATH,campaign.archive.TEST_PATH}
    # Controlled source-only omission, independent of other pytest modules
    # already loaded by a larger focused/reviewer run. Test BOTH ambient cases.
    if ambient_legacy_test_paths:static.update(omitted)
    else:static.difference_update(omitted)
    def identity(names):
        sources=m.custody._source_bytes(m.LANE_ROOT,tuple(sorted(names)))
        return {"root":str(m.LANE_ROOT),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,
            "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}
    generic=identity(static-omitted);inherited=identity(static|required)
    monkeypatch.setattr(m,"_isolated",lambda:None)
    monkeypatch.setattr(m.custody,"_identity",lambda head:(calls.append("generic"),copy.deepcopy(generic))[1])
    monkeypatch.setattr(campaign,"_identity",lambda head:(calls.append("campaign"),copy.deepcopy(inherited))[1])
    def git(root,*args):
        assert root==m.LANE_ROOT and args[0]=="show" and args[1].startswith("a"*40+":")
        return (root/args[1].split(":",1)[1]).read_bytes()
    monkeypatch.setattr(m.custody,"_git",git)
    value=m._identity("a"*40)
    # Run the REAL unchanged legacy guard, not a reduced interpretation of it.
    campaign._current(value)
    assert {campaign.first.TEST_PATH,campaign.archive.TEST_PATH,*required,m.SELF_PATH,m.TEST_PATH,*m.FROZEN}<=set(value["source_sha256"])
    assert calls==["campaign"]
