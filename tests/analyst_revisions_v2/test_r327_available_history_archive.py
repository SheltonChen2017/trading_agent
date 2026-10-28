"""Synthetic local archive protocol, no retained DATA or operation."""
import copy
import os
from pathlib import Path
import stat
import time
from types import SimpleNamespace as NS

import pytest
from scripts import prepare_arv2_r327_available_history_archive as m


def args():
    return NS(expected_head="a"*40,caller_sha256="b"*64,profile_sha256="c"*64)


def refused(code,call):
    with pytest.raises(m.Refused) as caught:call()
    assert m.finite(caught.value)==code


def ready():
    p=m.payload
    return {"schema":p.SCHEMA+"-READY","archive_pin":{"byte_count":m.ARCHIVE_BYTES,"sha256":"a"*64},
        "header_pin":{"byte_count":len(p._header_bytes()),"sha256":m.sha(p._header_bytes())},
        "source_receipt":{"schema":p.SCHEMA+"-source-receipt","data_plan_sha256":p.PLAN_SHA256,
            "whole_hashes_checked":73,"copied_ranges":73,"source_endpoint_sha256":"b"*64,
            "requires_normal_return_before_READY":True,**p.FALSE_FLAGS},
        "source_guard_normal_return":True,"range_count":73,"data_plan_sha256":p.PLAN_SHA256,
        "archive_metadata_sha256":"c"*64,**p.FALSE_FLAGS}


def result():
    value=ready()
    return {"schema":m.SCHEMA,"input_binding":m.source_context()["input_binding"],
        "period_sha256":m.PERIOD_SHA256,"ready_receipt":value,"archive_pin":value["archive_pin"],
        "archive_security_sha256":"d"*64,"genuine_input_checks_complete":True,
        "genuine_input_postchecks_complete":True,"own_output_postchecks_complete":True,
        "source_context_sha256":m.sha(m.canonical(m.source_context())),**m.FALSE_FLAGS}


def packet():
    value=result();return m.canonical({"binding":m.binding(args()),"outcome":{"result":value,
        "report":m.pin(m.canonical({**m.binding(args()),"result":value}))}})+b"\n"


def failure_packet():
    return m.canonical({"binding":m.binding(args()),"outcome":{"failure":m.failure(args(),m.Refused("genuine"),
        claim_state="consumed")}})+b"\n"


def test_source_plan_is_exact_project_independent_73_data_not_QC_or_old_controls():
    context=m.source_context();plan=m.payload.data_plan()
    assert len(plan)==73 and set(plan)==set(m.payload.ROLES)
    assert sum(row["byte_count"] for row in plan.values())==148531396
    assert context["archive_byte_count"]==148543046
    assert context["input_binding"]["binding_contract"]["binding_count"]==6151
    assert all("/R326-20261027-AR/" in row["relative_path"] for row in plan.values())
    assert all(name not in str(plan) for name in ("claim.json","report.json","b149c9c"))
    assert context["input_binding"]["ordered_session_values_sha256"]==m.period.FULL_AXIS_SHA256


def test_native_policies_deny_contact_and_restrict_validator_to_new_archive_and_marker():
    producer,verifier=(m.native_profile(mode) for mode in ("produce","validate"))
    for value in (producer,verifier):
        assert "(deny network*)" in value
        assert '"/usr/bin/security"' in value and "/Library/Keychains" in value
        assert "www.quantconnect.com" not in value
    assert str(m.CONTROL/m.ARCHIVE_NAME) in verifier and str(m.CONTROL/m.VERIFY_NAME) in verifier
    for row in m.payload.data_plan().values():assert str(m.ROOT/row["relative_path"]) not in verifier
    assert str(m.worker.previous.PACKAGE) not in verifier and str(m.worker.previous.LINEAGE) not in verifier
    assert str(m.worker.previous.PACKAGE) in producer
    assert str(m.CONTROL/"claim.json") not in verifier and str(m.CONTROL/"report.json") not in verifier


@pytest.mark.parametrize("exit_code",(0,False,True,None,-1,1,2,71))
def test_success_packet_requires_exact_actual_zero(exit_code):
    if type(exit_code) is int and exit_code==0:
        assert m.validate_output(packet(),exit_code,args())["outcome"]["result"]["archive_pin"]["byte_count"]==148543046
    else:refused("output",lambda:m.validate_output(packet(),exit_code,args()))


@pytest.mark.parametrize("exit_code",(0,False,True,None,-1,1,2,71))
def test_failure_packet_requires_exact_actual_two_and_grants_no_archive_read(exit_code,monkeypatch):
    monkeypatch.setattr(m,"DirectoryGuard",lambda **_:pytest.fail("archive read on producer failure"))
    if type(exit_code) is int and exit_code==2:
        m.verify_output_archive(failure_packet(),exit_code,args(),time.monotonic()+100)
    else:refused("output",lambda:m.validate_output(failure_packet(),exit_code,args()))


@pytest.mark.parametrize("issue",("trailing","double_LF","wrong_binding","report_pin","archive_pin",
    "source_normal","source_73","formal","period","extra"))
def test_closed_result_and_pin_relationships_refuse(issue):
    raw=packet()
    if issue=="trailing":raw+=b"EXTRA"
    elif issue=="double_LF":raw+=b"\n"
    else:
        value=m.parse(raw[:-1]);out=value["outcome"];r=out["result"]
        if issue=="wrong_binding":value["binding"]["expected_head"]="d"*40
        elif issue=="report_pin":out["report"]["sha256"]="0"*64
        elif issue=="archive_pin":r["archive_pin"]=dict(r["archive_pin"],byte_count=1)
        elif issue=="source_normal":r["ready_receipt"]["source_guard_normal_return"]=False
        elif issue=="source_73":r["ready_receipt"]["source_receipt"]["whole_hashes_checked"]=72
        elif issue=="formal":r["formal_forward_ready"]=True
        elif issue=="period":r["period_sha256"]="0"*64
        else:r["raw_prices"]=["NEVER"]
        raw=m.canonical(value)+b"\n"
    with pytest.raises((m.Refused,m.payload.Refused)):m.validate_output(raw,0,args())


def test_known_payload_and_worker_failures_are_finite_without_rendering():
    assert m.finite(m.payload.Refused("byte_pin"))=="payload_byte_pin"
    assert m.finite(m.worker.previous.Refused("catalog"))=="worker_catalog"
    class Hostile:
        def __eq__(self,_):pytest.fail("hostile equality")
        def __str__(self):pytest.fail("hostile text")
        def __repr__(self):pytest.fail("hostile repr")
    assert m.finite(m.Refused(Hostile()))=="unknown"


@pytest.mark.parametrize("field,delta",((5,2),(5,-1),(0,1),(1,1),(2,1),(3,1),(4,1),(9,1)))
def test_own_EXCL_directory_refresh_never_ignores_extra_links_identity_owner_mode_or_flags(monkeypatch,field,delta):
    old=(1,2,stat.S_IFDIR|0o700,100,100,4,64,1000,1000,0)
    fresh=list(old);fresh[5]+=1;fresh[6:9]=[96,2000,2000]
    if field==5:fresh[5]=old[5]+delta
    else:fresh[field]=old[field]+delta
    guard=object.__new__(m.DirectoryGuard);guard._policy=lambda _:None
    monkeypatch.setattr(m,"metadata",lambda _:tuple(fresh))
    refused("output_changed",lambda:guard.refresh({"fd":99,"metadata":old},created_file=True))


def test_own_EXCL_refresh_requires_exact_verified_APFS_plus_one_not_generic_nlink_omission(monkeypatch):
    old=(1,2,stat.S_IFDIR|0o700,100,100,4,64,1000,1000,0)
    fresh=(*old[:5],old[5]+1,96,2000,2000,old[9])
    guard=object.__new__(m.DirectoryGuard);guard._policy=lambda _:None
    monkeypatch.setattr(m,"metadata",lambda _:fresh)
    row={"fd":99,"metadata":old};guard.refresh(row,created_file=True)
    assert row["metadata"]==fresh
    monkeypatch.setattr(m,"metadata",lambda _:old)
    refused("output_changed",lambda:guard.refresh({"fd":99,"metadata":old},created_file=True))


@pytest.fixture
def local(tmp_path,monkeypatch):
    root=tmp_path/"lane";root.mkdir(mode=0o755)
    first=root/"artifacts";first.mkdir(mode=0o700)
    second=first/"analyst_revisions_v2";second.mkdir(mode=0o700)
    monkeypatch.setattr(m,"ROOT",root)
    monkeypatch.setattr(m,"CONTROL",second/"new_archive"/"K")
    return root


def test_original_directory_FDs_and_exclusive_claim_prevent_reuse(local):
    with m.Store() as store:
        store.write("claim.json",b"fixed",time.monotonic()+100)
        assert stat.S_IMODE(os.fstat(store.files["claim.json"]["fd"]).st_mode)==0o600
        assert len(store.guard.rows)>3
    refused("claim_spent",m.Store)
    assert (m.CONTROL/"claim.json").read_bytes()==b"fixed"


def test_failed_partial_archive_is_retained_without_fabricated_normal_output(local):
    with m.Store() as store:
        store.write("claim.json",b"fixed",time.monotonic()+100)
        fd=store.create(m.ARCHIVE_NAME);os.write(fd,b"partial");store.failed=True
    assert (m.CONTROL/m.ARCHIVE_NAME).read_bytes()==b"partial"
    assert not (m.CONTROL/"report.json").exists()


def test_unaccounted_filesystem_entry_increment_is_never_refreshed_or_waived(local):
    store=m.Store()
    try:
        store.write("claim.json",b"fixed",time.monotonic()+100)
        old=store.guard.rows[-1]["metadata"]
        foreign=m.CONTROL/"not-created-through-owned-protocol"
        foreign.write_bytes(b"foreign");foreign.chmod(0o600)
        assert m.metadata(store.fd)[5]==old[5]+1
        refused("output_changed",store.verify)
        assert store.guard.rows[-1]["metadata"]==old
    finally:store.failed=True;store.__exit__(None)


@pytest.mark.parametrize("issue",("leaf_replace","ancestor_change"))
def test_store_named_and_full_ancestor_metadata_drift_refuses(local,issue):
    store=m.Store()
    try:
        store.write("claim.json",b"fixed",time.monotonic()+100)
        if issue=="leaf_replace":
            alternate=m.CONTROL/"other";alternate.write_bytes(b"fixed");alternate.chmod(0o600)
            os.replace(alternate,m.CONTROL/"claim.json")
        else:
            old=os.stat(m.CONTROL.parent);os.utime(m.CONTROL.parent,ns=(old.st_atime_ns,old.st_mtime_ns+1))
        refused("output_changed",store.verify)
    finally:store.failed=True;store.__exit__(None)


@pytest.fixture
def synthetic_run(monkeypatch):
    events=[];fresh=(1,2,stat.S_IFREG|0o600,os.getuid(),os.getgid(),1,m.ARCHIVE_BYTES,1,1,0)
    r=ready();r["archive_metadata_sha256"]=m.sha(m.canonical(list(fresh)))
    class Store:
        def __init__(self):self.files={};self.failed=False
        def __enter__(self):return self
        def __exit__(self,*_):events.append("close-failed" if self.failed else "close-normal")
        def write(self,name,raw,deadline):events.append(name);return m.pin(raw)
        def create(self,name):
            events.append("archive-create");self.files[name]={"fd":99,"metadata":(1,2,stat.S_IFREG|0o600,os.getuid(),os.getgid(),1,0,1,1,0),"security":{}}
            return 99
        def finish(self,*_):events.append("own-finish");return fresh
        def verify(self):events.append("own-verify")
    monkeypatch.setattr(m,"Store",Store)
    def genuine(_):
        events.append("genuine");return object(),{}, {}, {},m.source_context()["input_binding"]
    monkeypatch.setattr(m,"_genuine",genuine)
    def prepare(*_a,**_k):events.extend(("authenticate73","copy73","source-normal"));return copy.deepcopy(r)
    monkeypatch.setattr(m.payload,"prepare_archive_fd",prepare)
    monkeypatch.setattr(m.worker,"_catalog_unchanged",lambda *_:events.append("genuine-post"))
    monkeypatch.setattr(m,"preflight",lambda *_:events.append("preflight-post"))
    monkeypatch.setattr(m.ar,"_credential_free",lambda:None)
    monkeypatch.setattr(m.environment,"require_safe_environment",lambda:None)
    return events


def test_claim_then_genuine_then_all_hashes_copy_normal_guard_postchecks_report(synthetic_run):
    outcome=m.run(args(),time.monotonic()+100);m.validate_result(outcome["result"])
    order=synthetic_run
    assert order.index("claim.json")<order.index("genuine")<order.index("archive-create")
    assert order.index("authenticate73")<order.index("copy73")<order.index("source-normal")
    assert order.index("source-normal")<order.index("genuine-post")<order.index("report.json")<order.index("close-normal")


def test_partial_copy_failure_preserves_finite_cause_and_never_report(synthetic_run,monkeypatch):
    def broken(*_a,**_k):raise m.payload.Refused("byte_pin")
    monkeypatch.setattr(m.payload,"prepare_archive_fd",broken)
    outcome=m.run(args(),time.monotonic()+100)
    assert outcome["failure"]["failure_code"]=="payload_byte_pin"
    assert "report.json" not in synthetic_run and synthetic_run[-1]=="close-failed"


@pytest.fixture
def verifier(local,monkeypatch):
    raw=b"synthetic-private-archive";fresh=None;security=None
    with m.Store() as store:
        store.write("claim.json",b"claim",time.monotonic()+100)
        fd=store.create(m.ARCHIVE_NAME);old=store.files[m.ARCHIVE_NAME]["metadata"]
        m._write(fd,raw,time.monotonic()+100);fresh=store.finish(m.ARCHIVE_NAME,old)
        security=store.files[m.ARCHIVE_NAME]["security"]
        store.write("report.json",b"report",time.monotonic()+100)
    result={"ready_receipt":{"archive_metadata_sha256":m.sha(m.canonical(list(fresh))),
        "header_pin":{"byte_count":1,"sha256":"b"*64},"data_plan_sha256":m.payload.PLAN_SHA256},
        "archive_pin":m.pin(raw),"archive_security_sha256":m.sha(m.canonical(security))}
    monkeypatch.setattr(m,"validate_output",lambda *_:{"outcome":{"result":result}})
    monkeypatch.setattr(m.payload,"validate_receipt",lambda value,**_:value)
    calls=[]
    def verify(fd,*,expected_metadata,deadline):
        assert (m.CONTROL/m.VERIFY_NAME).is_file()
        assert expected_metadata==fresh and os.pread(fd,len(raw)+1,0)==raw
        calls.append(fd)
        return {"archive_pin":m.pin(raw),"header_pin":result["ready_receipt"]["header_pin"],
            "data_plan_sha256":m.payload.PLAN_SHA256}
    monkeypatch.setattr(m.payload,"verify_archive_fd",verify)
    monkeypatch.setattr(m,"preflight",lambda *_:None)
    monkeypatch.setattr(m.ar,"_credential_free",lambda:None)
    monkeypatch.setattr(m.environment,"require_safe_environment",lambda:None)
    return NS(raw=raw,metadata=fresh,result=result,calls=calls,verify=verify)


def test_independent_verifier_marks_before_read_and_can_never_be_replayed(verifier):
    m.verify_output_archive(b"frame",0,args(),time.monotonic()+100)
    assert len(verifier.calls)==1
    refused("verification_spent",lambda:m.verify_output_archive(b"frame",0,args(),time.monotonic()+100))
    assert len(verifier.calls)==1


@pytest.mark.parametrize("issue",("archive_replace","marker_replace","ancestor_drift","wrong_whole_hash"))
def test_independent_verifier_rejects_late_named_or_metadata_or_hash_drift(verifier,monkeypatch,issue):
    def changed(fd,**kwargs):
        value=verifier.verify(fd,**kwargs)
        if issue=="wrong_whole_hash":return dict(value,archive_pin=dict(value["archive_pin"],sha256="0"*64))
        if issue=="ancestor_drift":
            old=os.stat(m.CONTROL.parent);os.utime(m.CONTROL.parent,ns=(old.st_atime_ns,old.st_mtime_ns+1))
        else:
            target=m.ARCHIVE_NAME if issue=="archive_replace" else m.VERIFY_NAME
            alternate=m.CONTROL/"alternate";alternate.write_bytes(b"substitute");alternate.chmod(0o600)
            os.replace(alternate,m.CONTROL/target)
        return value
    monkeypatch.setattr(m.payload,"verify_archive_fd",changed)
    with pytest.raises(m.Refused):m.verify_output_archive(b"frame",0,args(),time.monotonic()+100)
    assert (m.CONTROL/m.VERIFY_NAME).exists()


def test_unknown_entry_before_verify_consumes_no_data_read(verifier):
    (m.CONTROL/"unexpected").write_bytes(b"unexpected")
    refused("verification_spent",lambda:m.verify_output_archive(b"frame",0,args(),time.monotonic()+100))
    assert not verifier.calls
