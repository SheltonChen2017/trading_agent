"""Invented old-prefix custody + offline runner fixtures; no real artifacts."""
import copy

import pytest

pytest.importorskip("fcntl", reason="IBWIN-CR01: POSIX custody support; Windows custody port deferred")
import fcntl
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import zlib


from research import insider_buying_sec_feed_prefix_shape_runner_v1 as m

CONTACT="invented@unit.test"


def _raw_prefix(decoded=None):
    # The old fixture requires an exact64KiB Range unit. A level0 member leaves
    # its final gzip trailer outside the retained bytes, just as a real prefix.
    decoded=(b"opaque invented prefix"+bytes(range(256))*300) if decoded is None else decoded
    writer=zlib.compressobj(level=0,wbits=31)
    return (writer.compress(decoded)+writer.flush())[:65536]


def _old(root,raw=None):
    raw=_raw_prefix() if raw is None else raw
    response=m.capture.PrefixHttpResult(status=206,headers=(("Content-Length","65536"),("Content-Range","bytes 0-65535/1000000")),
        body=raw,body_read_attempted=True,refusal=None,declared_total=1000000)
    result=m.capture._invented(root=root,transport=lambda *_:response)
    assert result["result"]["prefix_retained"] is True
    return result["complete_sha256"]


def _pins(root,pin):
    run=root.joinpath(*m.capture.ARTIFACT_PARTS,"runs",m.capture.AUDIT_ID)
    value={name:hashlib.sha256((run/name).read_bytes()).hexdigest() for name in m.ORIGINAL_PINS if name not in {"claim","prefix.bin"}}
    value["complete.json"]=pin
    value["claim"]=hashlib.sha256(root.joinpath(*m.capture.ARTIFACT_PARTS,"claims",m.capture._claim_name()).read_bytes()).hexdigest()
    value["prefix.bin"]=json.loads((run/"request-result.json").read_bytes())["prefix_sha256"]
    return value


def _path(root):return root.joinpath(*m.ARTIFACT_PARTS,"runs",m.AUDIT_ID)


def _fixture(tmp_path,**kwargs):
    original=tmp_path/"original";original.mkdir(mode=0o700)
    target=tmp_path/"target";target.mkdir(mode=0o700);pin=_old(original)
    value=m._invented(root=target,original_root=original,original_complete_sha256=pin,**kwargs)
    return original,target,pin,value


def test_registration_is_offline_only_fresh_and_returns_independent_controls():
    value=m.registration()
    assert value["original_prefix_pins"]["prefix.bin"]==m.ORIGINAL_PINS["prefix.bin"]
    assert value["original_producer_head"]==m.ORIGINAL_HEAD and value["original_source_count"]==138
    assert value["new_HTTP_or_URL_claim_or_source_dispatch"] is False
    assert value["metadata_preflight_reads_raw_prefix"] is False
    assert value["maximum_control_or_IPC_bytes"]==1024**2
    value["original_prefix_pins"]["prefix.bin"]="0"*64;value["authority"]["backtesting_ready"]=True
    assert m.registration()["original_prefix_pins"]["prefix.bin"]!=value["original_prefix_pins"]["prefix.bin"]
    assert m.registration()["authority"]["backtesting_ready"] is False


def test_offline_fixture_retains_only_sanitized_shape_and_exact_independent_replay(tmp_path):
    original,target,pin,value=_fixture(tmp_path)
    assert value["result"]["report_retained"] is True and value["result"]["new_requests"]==0
    report=json.loads((_path(target)/"report.json").read_bytes())
    assert report["raw_prefix_reuse_only_no_new_HTTP"] is True
    assert report["shape"]["whole_carrier_CRC_ISIZE_EOF_or_privacy_verified"] is False
    assert report["original_current_contact_equality_attested"] is False
    replay=m._verify_files(target,value["complete_sha256"],"current@unit.test",fixture=True,
        original_root=original,original_pins=_pins(original,pin))
    assert replay["result"]==value["result"] and replay["current_contact_prefix_rescreened"] is True
    assert replay["authority"]["canonical_admitted"] is replay["authority"]["backtesting_ready"] is False
    assert not (_path(target)/"prefix.bin").exists()
    for file in target.rglob("*"):
        if file.is_file():assert CONTACT.encode() not in file.read_bytes() and b"opaque invented prefix" not in file.read_bytes()


def test_metadata_hold_never_reads_or_hashes_raw_prefix(tmp_path,monkeypatch):
    original=tmp_path/"original";original.mkdir(mode=0o700);pin=_old(original)
    real=m.privacy._Directory.read
    def no_body(self,name,*args,**kwargs):
        assert name!="prefix.bin","metadata front read raw body"
        return real(self,name,*args,**kwargs)
    monkeypatch.setattr(m.privacy._Directory,"read",no_body)
    held=m._HeldPrefix(original,fixture=True,pins=_pins(original,pin))
    try:
        assert held.metadata["raw_prefix_read_by_metadata_preflight"] is False
        held.check()
    finally:held.close()


def test_current_contact_late_raw_private_refusal_keeps_finite_failure_no_report(tmp_path):
    original=tmp_path/"original";original.mkdir(mode=0o700)
    target=tmp_path/"target";target.mkdir(mode=0o700)
    raw=_raw_prefix(b"other@unit.test"+bytes(range(256))*300);pin=_old(original,raw)
    value=m._invented(root=target,original_root=original,original_complete_sha256=pin,contact=lambda:"other@unit.test")
    assert value["result"]["report_retained"] is False
    assert value["result"]["report_sha256"] is None and not (_path(target)/"report.json").exists()
    assert value["result"]["refusal"]["code"] in {"local_operation_refused","finite_prefix_screen_refused"}
    replay=m._verify_files(target,value["complete_sha256"],CONTACT,fixture=True,original_root=original,original_pins=_pins(original,pin))
    assert replay["result"]==value["result"] and replay["current_contact_prefix_rescreened"] is False


def test_freshness_guard_precedes_contact_and_never_resumes(tmp_path):
    original,target,pin,value=_fixture(tmp_path);calls=[]
    with pytest.raises(m.PrefixShapeRunnerError,match="fresh_namespace_already_exists"):
        m._invented(root=target,original_root=original,original_complete_sha256=pin,contact=lambda:calls.append(1))
    assert calls==[] and m._verify_files(target,value["complete_sha256"],CONTACT,fixture=True,
        original_root=original,original_pins=_pins(original,pin))["result"]["report_retained"] is True


def test_low_disk_refuses_before_new_namespace_or_contact(tmp_path,monkeypatch):
    original=tmp_path/"original";original.mkdir(mode=0o700);pin=_old(original)
    target=tmp_path/"target";target.mkdir(mode=0o700);calls=[]
    monkeypatch.setattr(m.os,"fstatvfs",lambda _:SimpleNamespace(f_bavail=0,f_frsize=1))
    with pytest.raises(m.PrefixShapeRunnerError,match="disk_reserve_refused"):
        m._invented(root=target,original_root=original,original_complete_sha256=pin,contact=lambda:calls.append(1))
    assert calls==[] and not target.joinpath(*m.ARTIFACT_PARTS).exists()


@pytest.mark.parametrize("name",["complete.json","reservation.json","request-start.json","request-result.json","inspection.json","response-headers.json"])
def test_old_external_controls_cannot_be_substituted(tmp_path,name):
    original=tmp_path/"original";original.mkdir(mode=0o700);pin=_old(original);pins=_pins(original,pin)
    run=original.joinpath(*m.capture.ARTIFACT_PARTS,"runs",m.capture.AUDIT_ID)
    (run/name).write_bytes((run/name).read_bytes()+b" ")
    with pytest.raises(ValueError):m._HeldPrefix(original,fixture=True,pins=pins)


def test_old_header_unknown_key_refused_without_resealing_complete(tmp_path):
    original=tmp_path/"original";original.mkdir(mode=0o700);pin=_old(original);pins=_pins(original,pin)
    path=original.joinpath(*m.capture.ARTIFACT_PARTS,"runs",m.capture.AUDIT_ID,"response-headers.json")
    value=json.loads(path.read_bytes());value["unregistered_extra"]=True;path.write_bytes(m._raw(value))
    with pytest.raises(ValueError):m._HeldPrefix(original,fixture=True,pins=pins)


def test_old_scope_exclusive_writer_blocks_reader(tmp_path):
    original=tmp_path/"original";original.mkdir(mode=0o700);pin=_old(original);pins=_pins(original,pin)
    path=original.joinpath(*m.capture.ARTIFACT_PARTS,"scope.lock");fd=os.open(path,os.O_RDONLY)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):m._HeldPrefix(original,fixture=True,pins=pins)
    finally:os.close(fd)


def test_strict_old_version_hold_detects_mutation_even_restored_bytes(tmp_path):
    original=tmp_path/"original";original.mkdir(mode=0o700);pin=_old(original);pins=_pins(original,pin)
    held=m._HeldPrefix(original,fixture=True,pins=pins)
    try:
        path=original.joinpath(*m.capture.ARTIFACT_PARTS,"runs",m.capture.AUDIT_ID,"prefix.bin")
        raw=path.read_bytes();path.write_bytes(raw)
        with pytest.raises(ValueError):held.check()
    finally:held.close()


@pytest.mark.parametrize("name",["registration.json","reservation.json","input-preflight.json","contact-validated.json","analysis-start.json","analysis-result.json","report.json","complete.json"])
def test_new_control_exact_pin_inventory_and_versions_are_binding(tmp_path,name):
    original,target,pin,value=_fixture(tmp_path);path=_path(target)/name;path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError):m._verify_files(target,value["complete_sha256"],CONTACT,fixture=True,
        original_root=original,original_pins=_pins(original,pin))


@pytest.mark.parametrize("field,value",[("new_requests",True),("new_requests",1),("contact_reads",1),
    ("namespace_created",True),("schema","wrong"),("extra",True)])
def test_preflight_refuses_type_aliases_nonzero_actions_or_extra_fields(tmp_path,field,value):
    sources={m.SELF_PATH:"a"*64,m.TEST_PATH:"b"*64};identity={"root":str(tmp_path),"branch":m.LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}
    plan=m._plan(identity,{"schema":m.SCHEMA+"/original-input"});plan[field]=value
    with pytest.raises(m.PrefixShapeRunnerError,match="preflight_refused"):m._forms(identity,True,plan)


def test_native_command_initial_all_denials_isolation_and_no_private_values():
    command=m._command("analyse",{"source":"invented"});text=" ".join(command)
    assert "deny network*" in text and "deny process-fork" in text and "deny file-write*" in text
    assert 'deny process-exec (literal "/usr/bin/security")' in text
    assert "-I" in command and "-S" in command and "-B" in command
    assert "pycache_prefix="+m.EMPTY_CACHE_PREFIX in command
    assert CONTACT not in text and "http.client" not in text and "HTTPSConnection" not in text


def test_safe_foreign_exception_never_exposes_message():
    assert m._safe(ValueError(CONTACT),"analysis")=={"phase":"analysis","code":"local_operation_refused"}
    assert m._safe(m.shape.PrefixShapeError("privacy","finite_prefix_screen_refused"),"analysis")=={
        "phase":"privacy","code":"finite_prefix_screen_refused"}


def test_cli_protects_echo_before_argument_parser_and_restores_on_refusal(monkeypatch,capsys):
    calls=[];monkeypatch.setattr(m.contact_io,"_protect_stdin_echo",lambda:calls.append("protect") or "saved")
    monkeypatch.setattr(m.contact_io,"_restore_stdin_echo",lambda saved:calls.append(saved))
    assert m.main(["--private-key",CONTACT])==2
    assert calls==["protect","saved"] and CONTACT not in capsys.readouterr().out


def test_actual_readback_rechecks_exact_final_parent_identity(monkeypatch):
    identity={"head":"a"*40};changed={"head":"b"*40};calls=[]
    monkeypatch.setattr(m,"_identity",lambda _:calls.append(1) or (identity if len(calls)==1 else changed))
    plan={"execution_identity":identity,"inputs":{}}
    monkeypatch.setattr(m,"_child",lambda role,*a,**k:plan if role=="preflight" else {
        "producer_execution_identity":identity,"original_input_plan":plan})
    monkeypatch.setattr(m,"_forms",lambda *a:None);monkeypatch.setattr(m,"_parent_proofs",lambda *a:None)
    monkeypatch.setattr(m.previous,"_source_git",lambda *a:None);monkeypatch.setattr(m,"_current",lambda *a:None)
    monkeypatch.setattr(m.privacy,"_contact",lambda *a,**k:CONTACT);monkeypatch.setattr(m.contact_io,"_stdin_contact",lambda:CONTACT)
    with pytest.raises(m.PrefixShapeRunnerError,match="source_changed"):m.verify_actual(expected_head="a"*40,expected_report_sha256="b"*64)
    assert len(calls)==2


@pytest.mark.parametrize("wire",[{"ok":True,"value":{},"extra":True},{"ok":1,"value":{}},
    {"ok":False,"refusal":{"phase":[],"code":"native_boundary_refused"}},
    {"ok":False,"refusal":{"phase":"source","code":{},"extra":True}}])
def test_child_unknown_fields_and_untyped_refusals_are_finite(monkeypatch,wire):
    monkeypatch.setattr(m.old,"_run_child",lambda *a,**k:wire)
    with pytest.raises(m.PrefixShapeRunnerError):m._child("preflight",{})


def test_source_compilation_and_current_health_precede_first_old_input(monkeypatch):
    calls=[]
    class Memory:
        def __init__(self):calls.append("memory-install")
        def check(self):calls.append("memory-check")
        def close(self):calls.append("memory-close")
    class Held:
        def __init__(self,root):
            assert calls[:5]==["isolation","native-health","memory-install","current","compile"]
            calls.append("inputs");self.metadata={"schema":m.SCHEMA+"/original-input"}
        def check(self):calls.append("input-check")
        def close(self):calls.append("input-close")
    monkeypatch.setattr(m.previous,"_isolated",lambda:calls.append("isolation"))
    monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:calls.append("native-health"))
    monkeypatch.setattr(m.previous,"_WorkerMemoryGuard",Memory)
    monkeypatch.setattr(m,"_current",lambda _:calls.append("current"))
    monkeypatch.setattr(m.capture,"_compile_sources",lambda _:calls.append("compile"))
    monkeypatch.setattr(m,"_HeldPrefix",Held);monkeypatch.setattr(m,"_forms",lambda *a:None)
    value=m._worker("preflight",{},publish=False)
    assert value["ok"] is True and calls.index("compile")<calls.index("inputs")
    assert "input-close" in calls and calls[-1]=="memory-close"


def test_bad_source_stops_before_any_input_or_private_read(monkeypatch):
    calls=[]
    class Memory:
        def check(self):pass
        def close(self):calls.append("closed")
    monkeypatch.setattr(m.previous,"_isolated",lambda:None)
    monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:None)
    monkeypatch.setattr(m.previous,"_WorkerMemoryGuard",Memory)
    monkeypatch.setattr(m,"_current",lambda _:(_ for _ in ()).throw(m.PrefixShapeRunnerError("source_changed")))
    monkeypatch.setattr(m,"_HeldPrefix",lambda *a,**k:pytest.fail("source failure reached old input"))
    value=m._worker("analyse",{},publish=False)
    assert value=={"ok":False,"refusal":{"phase":"source","code":"source_changed"}} and calls==["closed"]


def test_old_hold_unlock_failure_still_drains_close_and_primary_error(monkeypatch):
    held=m._HeldPrefix.__new__(m._HeldPrefix);held.lock=123;calls=[]
    held.folders=[SimpleNamespace(close=lambda:calls.append("folder"))]
    monkeypatch.setattr(m.fcntl,"flock",lambda *a:(_ for _ in ()).throw(OSError("invented")))
    monkeypatch.setattr(m.os,"close",lambda fd:calls.append(fd))
    with pytest.raises(m.PrefixShapeRunnerError,match="cleanup_refused"):held.close()
    assert calls==[123,"folder"] and held.lock is None and held.folders==[]
    held.lock=124;held.folders=[SimpleNamespace(close=lambda:calls.append("folder2"))]
    try:raise RuntimeError("invented-primary")
    except RuntimeError:held.close()
    assert calls[-2:]==[124,"folder2"]


@pytest.mark.parametrize("field,value",[("fixture_only",False),("schema","wrong"),("original_prefix_sha256","0"*64)])
def test_coherently_resealed_report_controls_still_refuse_semantic_drift(tmp_path,field,value):
    original,target,pin,result=_fixture(tmp_path);path=_path(target)
    report=json.loads((path/"report.json").read_bytes());report[field]=value;(path/"report.json").write_bytes(m._raw(report))
    outcome=json.loads((path/"analysis-result.json").read_bytes());outcome["report_sha256"]=m._sha(m._raw(report))
    (path/"analysis-result.json").write_bytes(m._raw(outcome));complete=json.loads((path/"complete.json").read_bytes())
    complete["result"]=outcome;complete["result_sha256"]=m._sha(m._raw(outcome));(path/"complete.json").write_bytes(m._raw(complete))
    with pytest.raises(ValueError):m._verify_files(target,m._sha(m._raw(complete)),CONTACT,fixture=True,
        original_root=original,original_pins=_pins(original,pin))


@pytest.mark.parametrize("kind,magic",[(b"x",b"ustar\x0000"),(b"2",b"ustar\x0000"),(b"5",b"ustar\x0000"),(b"0",b"UNKNOWN!")])
def test_supported_observation_can_stop_before_marker_bearing_payload_without_false_refusal(tmp_path,kind,magic):
    header=bytearray(512);header[:11]=b"invented.nc";body=b"<SUBMISSION>opaque"
    header[124:136]=format(len(body),"011o").encode()+b"\0";header[156:157]=kind;header[257:265]=magic
    header[148:156]=b"        ";header[148:156]=format(sum(header),"06o").encode()+b"\0 "
    raw=_raw_prefix(bytes(header)+body+bytes((-len(body))%512)+bytes(range(256))*300)
    original=tmp_path/"original";original.mkdir(mode=0o700);target=tmp_path/"target";target.mkdir(mode=0o700);pin=_old(original,raw)
    value=m._invented(root=target,original_root=original,original_complete_sha256=pin)
    assert value["result"]["report_retained"] is True
    report=json.loads((_path(target)/"report.json").read_bytes())
    assert report["shape"]["physical_shape_observations"]["headers"][0]["payload_opening_markers"]==[]
    assert report["shape"]["prefix_format_descriptor"]["first_tar_header_observation"]["payload_opening_markers"]==[{"offset":0,"family":"SUBMISSION"}]
