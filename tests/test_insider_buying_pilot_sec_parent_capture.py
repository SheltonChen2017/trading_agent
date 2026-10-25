"""Invented pilot sources under external native network/Keychain denial."""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
from urllib.parse import quote

import pytest

pytest.importorskip("fcntl",reason="macOS/POSIX pilot custody")
pytest.importorskip("termios",reason="macOS/POSIX private contact")

from research import insider_buying_pilot_sec_parent_capture as m

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_insider_buying_sec_complete_submission import _complete, _legacy_header
from test_insider_buying_pilot_sec_parent_readback import invented_report


CONTACT = "invented@unit.test"


def _request(index):
    accession = f"0000000123-21-{index:06d}"
    path = f"edgar/data/987654/{accession}.txt"
    return {"period":"2021Q1","accession_number":accession,"form_type":"4","filing_date":"2021-01-04",
        "issuer_cik":"123456","archive_path":path,"url":"https://www.sec.gov/Archives/"+path,
        "source_record_ordinal":index,
        **{key:"a"*64 for key in ("filing_metadata_sha256","quarterly_zip_sha256","submission_member_sha256",
            "submission_header_line_sha256","schema_profile_sha256","master_decoded_sha256","master_receipt_sha256")}}


def _selection(count=2):
    return m._invented_selection([_request(index) for index in range(1,count+1)])


def _body(request):
    return _complete(header=_legacy_header()).replace(b"0000999999-22-000001",
        request["accession_number"].encode()).replace(b"20221107",b"20210104")


def _response(raw):
    return m.SecHttpResult(200,(("Content-Length",str(len(raw))),),raw)


class Timer:
    def __init__(self):self.now=0;self.sleeps=[]
    def __call__(self):return self.now
    def sleep(self,seconds):self.sleeps.append(seconds);self.now+=round(seconds*1_000_000_000)


def _base(root):return root.joinpath(*m.ARTIFACT_PARTS)
def _run_path(root):return _base(root)/"runs"/m.CAPTURE_ID
def _json(path):return json.loads(path.read_bytes())


def _wire(selection,calls=None,response=None,on_call=None):
    requests={item["request"]["url"]:item["request"] for item in selection.to_payload()["requests"]}
    def wire(url,headers,maximum):
        if calls is not None:calls.append((url,dict(headers),maximum))
        if on_call is not None:on_call(url,headers,maximum)
        return response if response is not None else _response(_body(requests[url]))
    return wire


def _run(root,*,selection=None,transport=None,calls=None,response=None,timer=None,**kwargs):
    selection=_selection() if selection is None else selection
    timer=Timer() if timer is None else timer
    options={"clock":lambda:"2026-10-25T12:00:00+00:00","monotonic_ns":timer,
        "sleep":timer.sleep,"free_bytes":lambda:m.MIN_FREE_BYTES+64*m.MAX_PARENT_BYTES}
    options.update(kwargs)
    return m._run_invented_capture(selection,root=root,
        transport=_wire(selection,calls,response) if transport is None else transport,**options)


def test_all64_success_preserves_raw_request_jit_claims_cadence_and_false_authority(tmp_path):
    selection=_selection(64);calls=[];timer=Timer()
    def inspect_start(url,headers,maximum):
        index=len(calls)-1;run=_run_path(tmp_path)
        assert (run/"reservation.json").is_file() and (run/"contact-validated.json").is_file()
        claim=_base(tmp_path)/"claims"/(m._sha(selection.to_payload()["requests"][index]["request"]["accession_number"].encode())+".json")
        assert claim.is_file() and (run/f"request-{index:03d}-start.json").is_file()
        assert _json(claim)["request"]["request"]["issuer_cik"]=="123456"
        assert CONTACT in headers["User-Agent"] and maximum==m.MAX_PARENT_BYTES
    result=_run(tmp_path,selection=selection,calls=calls,timer=timer,
        transport=_wire(selection,calls,on_call=inspect_start))
    assert len(calls)==result["started_requests"]==result["raw_bodies_retained"]==result["header_bound_bodies"]==64
    assert result["capture_completed_without_refusal"] is True and result["fixture_only"] is True
    assert result["planned_unclaimed_unattempted"]==0
    assert len(timer.sleeps)==63 and all(value==0.5 for value in timer.sleeps)
    report=_json(_run_path(tmp_path)/"complete.json")
    assert report["full_xml_projection_attempts"]==0 and report["old_roots_written"] is False
    assert report["permanent_claims_created"]==64
    for value in report["authority"].values():assert value is False or type(value) is int and value==0
    for path in _base(tmp_path).rglob("*"):
        assert stat.S_IMODE(path.stat().st_mode)==(0o700 if path.is_dir() else 0o600)
        if path.is_file() and path.suffix!=".bin":assert CONTACT.encode() not in path.read_bytes()
    assert result["report_sha256"]==m._sha((_run_path(tmp_path)/"complete.json").read_bytes())


@pytest.mark.parametrize("status",(301,403,404,429,500))
def test_non200_stops_once_without_body_read_hash_or_retention(tmp_path,status):
    calls=[];result=_run(tmp_path,calls=calls,response=m.SecHttpResult(status,(),b""))
    assert len(calls)==result["started_requests"]==1 and result["raw_bodies_retained"]==0
    assert result["planned_unclaimed_unattempted"]==1 and not result["capture_completed_without_refusal"]
    row=_json(_run_path(tmp_path)/"request-000-result.json")
    assert row["status"]==status and row["body_sha256"] is None and row["body_size_bytes"] is None
    assert row["disposition"]=="http_refused_no_retry"
    assert len(list((_base(tmp_path)/"claims").iterdir()))==1
    assert not list((_run_path(tmp_path)/"objects").iterdir())


def test_transport_exception_is_ambiguous_permanent_and_never_retried(tmp_path):
    calls=[]
    def wire(*args):
        calls.append(args);raise OSError("PRIVATE ERROR NEVER PRINT")
    result=_run(tmp_path,transport=wire)
    assert len(calls)==result["started_requests"]==1 and result["raw_bodies_retained"]==0
    row=_json(_run_path(tmp_path)/"request-000-result.json")
    assert row["disposition"]=="ambiguous_transport_failure_no_retry" and row["status"] is None
    with pytest.raises(ValueError):_run(tmp_path)
    assert b"PRIVATE ERROR" not in (_run_path(tmp_path)/"complete.json").read_bytes()


def test_header_identity_refusal_retains_original_once_but_never_admits_or_continues(tmp_path):
    raw=b"<SEC-DOCUMENT>invented malformed source\n</SEC-DOCUMENT>\n"
    calls=[];result=_run(tmp_path,calls=calls,response=_response(raw))
    assert len(calls)==1 and result["raw_bodies_retained"]==1 and result["header_bound_bodies"]==0
    assert not result["capture_completed_without_refusal"]
    row=_json(_run_path(tmp_path)/"request-000-result.json")
    assert row["body_retained"] is True and row["header_identity_bound"] is False
    assert row["disposition"]=="complete_raw_parent_retained_header_quarantined_no_retry"
    assert (_run_path(tmp_path)/"objects"/(m._sha(raw)+".bin")).read_bytes()==raw


@pytest.mark.parametrize("encode",(lambda v:v,lambda v:quote(v,safe=""),lambda v:quote(quote(v,safe=""),safe=""),
    lambda v:"".join("\\u%04x"%ord(char) for char in v),lambda v:v.replace("@","&#64;")))
@pytest.mark.parametrize("where",("body","headers"))
def test_contact_echo_encodings_refuse_before_private_response_hash_and_storage(tmp_path,encode,where):
    contact=encode(CONTACT);raw=_body(_request(1))
    headers=(("Content-Length",str(len(raw))),)
    if where=="body":raw+=contact.encode();headers=(("Content-Length",str(len(raw))),)
    else:headers=(*headers,("X-Invented-Echo",contact))
    result=_run(tmp_path,response=m.SecHttpResult(200,headers,raw))
    assert result["started_requests"]==1 and result["raw_bodies_retained"]==0
    row=_json(_run_path(tmp_path)/"request-000-result.json")
    assert row["body_sha256"] is None and row["body_size_bytes"] is None
    if where=="headers":assert row["response_headers_sha256"] is None
    assert not list((_run_path(tmp_path)/"objects").iterdir())
    assert not any(contact.encode() in path.read_bytes() for path in _run_path(tmp_path).glob("*.json"))


@pytest.mark.parametrize("bad",("",None,[],[_request(i) for i in range(1,66)]))
def test_selection_bounds_and_types_refuse_before_io(bad):
    with pytest.raises(ValueError):m._invented_selection(bad)


@pytest.mark.parametrize("field,value",(("period","2006Q1"),("period","2021Q2"),("issuer_cik","0"),
    ("form_type","3"),("source_record_ordinal",True),("source_record_ordinal",0),
    ("filing_date","2021-04-01"),("master_decoded_sha256","notahash"),
    ("url","https://invalid.example/source"),("archive_path","edgar/data/1/different.txt")))
def test_selection_request_contract_is_exact_pilot_only(field,value):
    request=_request(1);request[field]=value
    with pytest.raises(ValueError):m._invented_selection([request])


def test_selection_duplicate_unknown_fields_copy_and_factory_seal():
    with pytest.raises(ValueError):m._invented_selection([_request(1),_request(1)])
    row=_request(1);row["unexpected"]=True
    with pytest.raises(ValueError):m._invented_selection([row])
    row=_request(1);selection=m._invented_selection([row])
    row["issuer_cik"]="999"
    assert selection.to_payload()["requests"][0]["request"]["issuer_cik"]=="123456"
    with pytest.raises(ValueError):replace(selection).to_payload()
    object.__setattr__(selection,"_bytes",m._raw({"unsafe":True}))
    with pytest.raises(ValueError):selection.to_payload()


def test_prior_consumption_blocks_before_contact_or_claim(tmp_path):
    class Prior(m._FixturePrior):
        def __init__(self):self.exposed_accessions={_request(1)["accession_number"]}
    contacts=[];calls=[]
    with pytest.raises(ValueError,match="already_consumed"):
        _run(tmp_path,prior_open=Prior,contact=lambda:contacts.append(1) or CONTACT,calls=calls)
    assert not contacts and not calls and not _base(tmp_path).exists()


@pytest.mark.parametrize("root",("lane","parent","relative"))
def test_fixture_root_cannot_alias_actual_roots_or_their_ancestors(tmp_path,root):
    selected={"lane":m.LANE_ROOT,"parent":m.LANE_ROOT.parent,"relative":Path("relative")}[root]
    with pytest.raises(ValueError):_run(selected,transport=lambda *args:pytest.fail("must not dispatch"))


def test_explicitly_unset_production_pins_refuse_before_any_identity_contact_or_source_loader(monkeypatch):
    def tripwire(*args,**kwargs):pytest.fail("production preactivation must not reach external helper")
    monkeypatch.setattr(m,"_identity",tripwire);monkeypatch.setattr(m,"_load_actual_selection",tripwire)
    monkeypatch.setattr(m.old,"_stdin_contact",tripwire);monkeypatch.setattr(m.old,"_getpass_contact",tripwire)
    monkeypatch.setattr(m,"ACTUAL_SELECTION_PINS",{})
    with pytest.raises(m.PilotParentCaptureError,match="not_activated"):
        m.run_actual_capture(expected_head="a"*40)


@pytest.mark.parametrize("which",("raw","wrapper"))
def test_fixture_cannot_select_production_transport_callback(tmp_path,monkeypatch,which):
    def tripwire(*args,**kwargs):pytest.fail("real transport must not be called")
    # Explicit tripwire is installed before referring to either production
    # transport object; native network denial remains the actual safety layer.
    monkeypatch.setattr(m,"_RAW_TRANSPORT",tripwire)
    callback=m._RAW_TRANSPORT if which=="raw" else m._production_transport
    with pytest.raises(ValueError,match="invented_transport_only"):_run(tmp_path,transport=callback)


def test_disk_reserve_exact_boundary_and_underfill_are_not_silent(tmp_path):
    calls=[]
    with pytest.raises(ValueError,match="disk_reserve"):
        _run(tmp_path,calls=calls,free_bytes=lambda:m.MIN_FREE_BYTES+2*m.MAX_PARENT_BYTES-1)
    assert calls==[]
    other=tmp_path/"enough";other.mkdir()
    assert _run(other,free_bytes=lambda:m.MIN_FREE_BYTES+2*m.MAX_PARENT_BYTES)["raw_bodies_retained"]==2


def test_postcompletion_disk_underfill_leaves_next_request_unclaimed(tmp_path):
    capacities=iter((m.MIN_FREE_BYTES+2*m.MAX_PARENT_BYTES, m.MIN_FREE_BYTES+2*m.MAX_PARENT_BYTES,m.MIN_FREE_BYTES-1))
    calls=[]
    with pytest.raises(ValueError,match="remaining_disk_reserve"):_run(tmp_path,calls=calls,free_bytes=lambda:next(capacities))
    assert len(calls)==1 and len(list((_base(tmp_path)/"claims").iterdir()))==1
    assert (_run_path(tmp_path)/"request-000-result.json").is_file()
    assert not (_run_path(tmp_path)/"request-001-start.json").exists()


def test_source_or_prior_guard_change_after_start_cannot_continue_or_rerun(tmp_path):
    changed=False;calls=[]
    def guard():
        if changed:raise ValueError("invented_changed_source")
    def wire(*args):
        nonlocal changed
        calls.append(args);changed=True;return _response(_body(_request(1)))
    with pytest.raises(ValueError,match="changed_source"):_run(tmp_path,guard=guard,transport=wire)
    assert len(calls)==1 and len(list((_base(tmp_path)/"claims").iterdir()))==1
    assert (_run_path(tmp_path)/"request-000-start.json").is_file()
    assert not (_run_path(tmp_path)/"complete.json").exists()


@pytest.mark.parametrize("change",("content","inode","mode","mtime","extra","symlink","hardlink"))
def test_output_custody_changes_during_request_refuse_even_same_size_restored_mtime(tmp_path,change):
    calls=[]
    def mutate(*args):
        calls.append(args);path=_run_path(tmp_path)/"reservation.json";old=path.stat();raw=path.read_bytes()
        if change=="content":
            path.write_bytes(raw.replace(b"2021Q1",b"2021Q2",1));os.utime(path,ns=(old.st_atime_ns,old.st_mtime_ns))
        elif change=="inode":
            path.unlink();path.write_bytes(raw);path.chmod(0o600);os.utime(path,ns=(old.st_atime_ns,old.st_mtime_ns))
        elif change=="mode":path.chmod(0o644)
        elif change=="mtime":os.utime(path,ns=(old.st_atime_ns,old.st_mtime_ns+1))
        elif change=="extra":(_run_path(tmp_path)/"unexpected.json").write_bytes(b"{}")
        elif change=="symlink":
            other=tmp_path/"samebytes";other.write_bytes(raw);path.unlink();path.symlink_to(other)
        else:os.link(path,tmp_path/"same-hardlink")
        return _response(_body(_request(1)))
    with pytest.raises(ValueError):_run(tmp_path,transport=mutate)
    assert len(calls)==1 and not (_run_path(tmp_path)/"complete.json").exists()


def test_benign_new_output_ctime_only_change_preserves_all_other_bytes_and_identity(tmp_path):
    def metadata_touch(*args):
        path=_run_path(tmp_path)/"reservation.json";before=path.stat()
        # fchmod to the unchanged mode may advance ctime; no source intake
        # ctime policy is touched by the new-output settlement contract.
        path.chmod(0o600)
        after=path.stat()
        assert m._version(before)==m._version(after)
        return _response(_body(_request(1 if not (_run_path(tmp_path)/"request-000-result.json").exists() else 2)))
    assert _run(tmp_path,transport=metadata_touch)["raw_bodies_retained"]==2


def test_cleanup_drains_all_preserves_primary_and_sanitizes_standalone_failures(monkeypatch):
    events=[]
    class Folder:
        def __init__(self,name):self.name=name
        def close(self):events.append(self.name);raise OSError("PRIVATE CLOSE")
    class Prior:
        def close(self):events.append("prior");raise OSError("PRIVATE PRIOR")
    with pytest.raises(RuntimeError,match="primary"):
        try:raise RuntimeError("primary")
        finally:m._close_all([Folder("a"),Folder("b")],Prior(),None,False)
    assert events==["b","a","prior"]
    events.clear()
    with pytest.raises(m.PilotParentCaptureError,match="capture_cleanup_refused"):
        m._close_all([Folder("a"),Folder("b")],Prior(),None,False)
    assert events==["b","a","prior"]


def test_independent_verifier_recounts_exact_original_custody_without_projection(tmp_path):
    result=_run(tmp_path)
    verified=m.verify_invented_capture(tmp_path,result["report_sha256"])
    assert verified["started_requests"]==verified["raw_bodies_retained"]==verified["header_bound_bodies"]==2
    assert verified["full_xml_projection_attempts"]==0 and verified["capture_completed_without_refusal"] is True


@pytest.mark.parametrize("response",(m.SecHttpResult(403,(),b""),_response(b"malformed header but retained")))
def test_verifier_preserves_stopped_http_or_header_quarantine_accounting(tmp_path,response):
    result=_run(tmp_path,response=response)
    verified=m.verify_invented_capture(tmp_path,result["report_sha256"])
    assert verified["started_requests"]==1 and verified["planned_unclaimed_unattempted"]==1
    assert verified["capture_completed_without_refusal"] is False


@pytest.mark.parametrize("fault",("report_hash","bool_count","overstated_count","result_order","claim","start",
    "body","body_mode","extra","missing_body","authority","spacing"))
def test_verifier_cannot_launder_changed_report_or_source_body_by_rehashing_report(tmp_path,fault):
    result=_run(tmp_path);run=_run_path(tmp_path);report=_json(run/"complete.json")
    if fault=="report_hash":
        with pytest.raises(ValueError):m.verify_invented_capture(tmp_path,"f"*64)
        return
    if fault=="bool_count":report["started_requests"]=True
    elif fault=="overstated_count":report["raw_bodies_retained"]+=1
    elif fault=="result_order":report["results"].reverse()
    elif fault=="claim":
        claim=next((_base(tmp_path)/"claims").iterdir());body=_json(claim);body["selection_sha256"]="f"*64;claim.write_bytes(m._raw(body))
    elif fault in {"start","spacing"}:
        index=0 if fault=="start" else 1;path=run/f"request-{index:03d}-start.json";body=_json(path)
        if fault=="start":body["request_sha256"]="f"*64
        else:body["started_monotonic_ns"]=0
        raw=m._raw(body);path.write_bytes(raw)
        output=run/f"request-{index:03d}-result.json";record=_json(output);record["start_sha256"]=m._sha(raw)
        raw=m._raw(record);output.write_bytes(raw);report["results"][index]["result_sha256"]=m._sha(raw)
    elif fault in {"body","body_mode","missing_body"}:
        path=next((run/"objects").iterdir())
        if fault=="body":path.write_bytes(path.read_bytes().replace(b"Invented",b"Altered!",1))
        elif fault=="body_mode":path.chmod(0o644)
        else:path.unlink()
    elif fault=="extra":(run/"unknown.json").write_bytes(b"{}")
    else:report["authority"]["backtest_authorized"]=True
    raw=m._raw(report);(run/"complete.json").write_bytes(raw)
    with pytest.raises((ValueError,OSError)):m.verify_invented_capture(tmp_path,m._sha(raw))


def test_actual_context_wrapper_rejects_forged_fixture_context_before_raw_transport(monkeypatch):
    def tripwire(*args,**kwargs):pytest.fail("unsealed context must not reach real transport")
    monkeypatch.setattr(m,"_RAW_TRANSPORT",tripwire)
    with pytest.raises(ValueError):m._production_transport(object(),0,_request(1)["url"],{},m.MAX_PARENT_BYTES)


def test_local_object_publication_failure_stays_local_refusal_not_privacy_disposition(tmp_path,monkeypatch):
    original=m._NewDirectory.publish
    def publish(self,name,raw,**kwargs):
        if name.endswith(".bin"):raise ValueError("invented_local_publication_failure")
        return original(self,name,raw,**kwargs)
    monkeypatch.setattr(m._NewDirectory,"publish",publish)
    with pytest.raises(ValueError,match="publication"):_run(tmp_path)
    assert (_run_path(tmp_path)/"request-000-start.json").is_file()
    assert len(list((_base(tmp_path)/"claims").iterdir()))==1
    assert not (_run_path(tmp_path)/"complete.json").exists()


def _invented_observer_selection():
    """Typed synthetic IPC with registered counts, not observed market data."""
    report=invented_report();source=report["source_roster"];parent=report["parent_audit"];records=[]
    for index in range(1,65):
        request=_request(index)
        row={"period":"2021Q1","source_record_ordinal":index,"accession_number":request["accession_number"],
            "form_type":"4","raw_filing_date":request["filing_date"],"filing_date":request["filing_date"],
            "raw_issuer_cik":request["issuer_cik"],"issuer_comparison_key":request["issuer_cik"].zfill(10),
            "short_cik":True,"accession_year_mismatch":False,"raw_symbol_label":"INVENTED",
            "accession_key_sha256":m._sha(request["accession_number"].encode()),
            **{key:request[key] for key in ("quarterly_zip_sha256","submission_member_sha256",
                "submission_header_line_sha256","schema_profile_sha256")}}
        row["filing_metadata_sha256"]=m._sha(m._raw(row));request["filing_metadata_sha256"]=row["filing_metadata_sha256"]
        target={key:request[key] for key in ("period","accession_number","form_type","filing_date","issuer_cik")}
        target.update(quarterly_index_sha256=request["master_decoded_sha256"],complete_submission_url=request["url"])
        records.append({"selection_ordinal":index,"source":row,"source_record_sha256":row["filing_metadata_sha256"],
            "request":request,"request_sha256":m._sha(m._raw(request)),"pre_normalization_target":target,
            "selected_locator":{key:request[key] for key in ("accession_number","form_type","filing_date","archive_path")},
            "compiler_disposition_sha256":"f"*64,"dispatch_authorized":False,"canonical_admitted":False})
    period=next(row["counts"] for row in parent["quarters"] if row["period"]=="2021Q1")
    payload={"schema":m.fresh.SCHEMA,"fixture_only":False,"selection_period":"2021Q1","selection_limit":64,"selected_count":64,
        "selection_policy":m.fresh.POLICY,"requests":records,"source_roster_sha256":m._sha(m._raw(source)),
        "parent_audit_sha256":m._sha(m._raw(parent)),"exposure_inventory_sha256":report["exposure_inventory_sha256"],
        "retained_candidate_inventory_sha256":report["retained_body_inventory_sha256"],"source_roster_counts":source["counts"],
        "parent_context_counts":parent["context_counts"],"parent_pilot_counts":parent["pilot_counts"],
        "quarter_bindings":parent["quarters"],
        "selection_period_observed_fresh_count":period["fresh_locatable_candidate_requests"],
        "selection_period_suppressed_late_repeat_count":0,
        "selection_period_eligible_after_global_suppression_count":period["fresh_locatable_candidate_requests"],
        "global_consumed_accessions":0,"global_repeat_accessions_observed":0,"all_25_quarters_finished":True,
        "complete_source_population_is_not_complete_parent_corpus":True,"no_earlier_or_later_quarter_substitution":True,
        "separate_diagnostic_does_not_resolve_original_ambiguous_start":True,"authority":dict(m.audit._AUTHORITY),
        "dispatch_authorized":False,"canonical_admitted":False,"backtesting_ready":False,
        **dict.fromkeys(("new_provider_requests","credential_reads","qc_jobs","outcome_looks","backtests"),0)}
    for stem in ("source_row","disposition","fresh_request"):
        for suffix in ("sha256","bytes"):payload["full_"+stem+"_jsonl_"+suffix]=parent[stem+"_jsonl_"+suffix]
    for stem,rows in (("selected_request",[row["request"] for row in records]),("selected_metadata",records)):
        raw=b"".join(m._raw(row)+b"\n" for row in rows)
        payload[stem+"_jsonl_sha256"]=m._sha(raw);payload[stem+"_jsonl_bytes"]=len(raw)
    assert m.fresh.validate_selection_payload(payload)==payload
    return payload,report


def _selection_controls(tmp_path,monkeypatch,change=None):
    from research import insider_buying_pilot_sec_fresh_selection_runner as observer
    payload,report=_invented_observer_selection()
    sources={observer.SELF_PATH:"e"*64}
    identity={"root":str(tmp_path),"branch":"codex/strategy-insider-buying","head":"a"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}
    worker={"schema":observer.SCHEMA,"audit_id":observer.AUDIT_ID,"registration":observer.REGISTRATION,
        "registration_sha256":m._sha(m._raw(observer.REGISTRATION)),"execution_identity":identity,
        "prior_audit_complete_sha256":observer.retained.PINS["complete.json"][0],
        "exposure_inventory_sha256":report["exposure_inventory_sha256"],
        "exposure_snapshot_sha256":report["exposure_snapshot_sha256"],
        "retained_body_inventory_sha256":report["retained_body_inventory_sha256"],"selection":payload,
        "selection_sha256":m._sha(m._raw(payload)),"source_roster":report["source_roster"],"parent_audit":report["parent_audit"],
        "locator_quarantines":[],"locator_quarantine_jsonl_sha256":m._sha(b""),"locator_quarantine_jsonl_bytes":0,
        "native_network_fork_allwrite_securityexec_denial":True,"new_provider_requests":0,"credential_reads":0,
        "qc_accesses":0,"outcome_looks":0,"backtests":0,"dispatch_authorized":False,"canonical_admitted":False,"backtesting_ready":False}
    reservation={"schema":observer.SCHEMA+"/reservation","registration":observer.REGISTRATION,
        "execution_identity":json.loads(m._raw(identity))}
    terminal={"schema":observer.SCHEMA+"/terminal","reservation_sha256":m._sha(m._raw(reservation)),
        "elapsed_seconds":12.375,"exit_code":0,"stdout_bytes":len(m._raw(worker))+1,
        "stdout_sha256":m._sha(m._raw(worker)+b"\n"),"stderr_bytes":0,"stderr_sha256":m._sha(b"")}
    complete={"schema":observer.SCHEMA+"/complete","audit_id":observer.AUDIT_ID,
        "reservation_sha256":m._sha(m._raw(reservation)),"terminal_sha256":m._sha(m._raw(terminal)),"worker_result":worker}
    if change is not None:change(reservation,terminal,complete)
    controls={"reservation.json":m._raw(reservation),"terminal.json":m._raw(terminal),"complete.json":m._raw(complete)}
    path=tmp_path.joinpath(*m.SELECTION_PARTS,m.SELECTION_AUDIT_ID);path.mkdir(parents=True)
    for parent in (path,*path.parents):
        if parent==tmp_path.parent:break
        parent.chmod(0o700)
    for name,raw in controls.items():
        leaf=path/name;leaf.write_bytes(raw);leaf.chmod(0o600)
    monkeypatch.setattr(m,"LANE_ROOT",tmp_path)
    monkeypatch.setattr(m,"ACTUAL_SELECTION_PINS",{name:(m._sha(raw),len(raw)) for name,raw in controls.items()})
    monkeypatch.setattr(m,"ACTUAL_SELECTION_SHA256",m._sha(m._raw(payload)))
    monkeypatch.setattr(m,"ACTUAL_SELECTION_HEAD","a"*40)
    return payload


def test_bound_selection_loader_accepts_real_outer_worker_wrapper_and_float_elapsed(tmp_path,monkeypatch):
    expected=_selection_controls(tmp_path,monkeypatch)
    value,hold=m._load_actual_selection()
    try:
        assert value.to_payload()==expected and value.sha256==m._sha(m._raw(expected))
        assert type(value) is m._PinnedActualSelection
    finally:hold.close()


@pytest.mark.parametrize("fault",("terminal_float_nan","terminal_exit_bool","terminal_stdout_sha","terminal_stdout_bytes",
    "terminal_reservation","complete_reservation","complete_terminal","worker_head","worker_selection_sha",
    "reservation_head","old_top_schema"))
def test_selection_control_loader_rejects_tampered_execution_lineage_and_ipc_hashes(tmp_path,monkeypatch,fault):
    def change(reservation,terminal,complete):
        if fault=="terminal_float_nan":terminal["elapsed_seconds"]="not-a-finite-number"
        elif fault=="terminal_exit_bool":terminal["exit_code"]=False
        elif fault=="terminal_stdout_sha":terminal["stdout_sha256"]="f"*64
        elif fault=="terminal_stdout_bytes":terminal["stdout_bytes"]+=1
        elif fault=="terminal_reservation":terminal["reservation_sha256"]="f"*64
        elif fault=="complete_reservation":complete["reservation_sha256"]="f"*64
        elif fault=="complete_terminal":complete["terminal_sha256"]="f"*64
        elif fault=="worker_head":complete["worker_result"]["execution_identity"]["head"]="b"*40
        elif fault=="worker_selection_sha":complete["worker_result"]["selection_sha256"]="f"*64
        elif fault=="reservation_head":
            reservation["execution_identity"]["head"]="b"*40
            terminal["reservation_sha256"]=m._sha(m._raw(reservation))
            complete["reservation_sha256"]=m._sha(m._raw(reservation))
        else:complete["selection"]=complete.pop("worker_result")["selection"]
        if fault in {"worker_head","worker_selection_sha"}:
            worker=complete["worker_result"]
            terminal["stdout_bytes"]=len(m._raw(worker))+1
            terminal["stdout_sha256"]=m._sha(m._raw(worker)+b"\n")
        if fault not in {"complete_reservation","complete_terminal"}:
            complete["terminal_sha256"]=m._sha(m._raw(terminal))
    _selection_controls(tmp_path,monkeypatch,change)
    with pytest.raises(ValueError):m._load_actual_selection()


def _invented_activation(monkeypatch):
    monkeypatch.setattr(m,"ACTUAL_SELECTION_PINS",{name:("a"*64,1)
        for name in ("reservation.json","terminal.json","complete.json")})
    monkeypatch.setattr(m,"ACTUAL_SELECTION_SHA256","b"*64)
    monkeypatch.setattr(m,"ACTUAL_SELECTION_HEAD","a"*40)


def test_committed_observed_activation_configuration_is_typed_without_loading_actual_inputs():
    # The default configuration may be activated after its separate selector
    # completes. This checks only committed constants, never private controls.
    m._activation_ready()
    assert set(m.ACTUAL_SELECTION_PINS)=={"reservation.json","terminal.json","complete.json"}
    assert all(type(size) is int and 0<size<=m.MAX_CONTROL_BYTES
        for digest,size in m.ACTUAL_SELECTION_PINS.values())


@pytest.mark.parametrize("fault",("missing","extra","bool_size","bad_digest","list_pin","selection_sha","head"))
def test_activation_rejects_malformed_observed_pins_before_any_actual_loader(monkeypatch,fault):
    _invented_activation(monkeypatch)
    pins=dict(m.ACTUAL_SELECTION_PINS)
    if fault=="missing":pins.pop("terminal.json")
    elif fault=="extra":pins["extra.json"]=("a"*64,1)
    elif fault=="bool_size":pins["complete.json"]=("a"*64,True)
    elif fault=="bad_digest":pins["complete.json"]=("not-a-sha",1)
    elif fault=="list_pin":pins["complete.json"]=["a"*64,1]
    elif fault=="selection_sha":monkeypatch.setattr(m,"ACTUAL_SELECTION_SHA256","invalid")
    else:monkeypatch.setattr(m,"ACTUAL_SELECTION_HEAD","invalid")
    monkeypatch.setattr(m,"ACTUAL_SELECTION_PINS",pins)
    monkeypatch.setattr(m,"_identity",lambda *a:pytest.fail("invalid activation must precede identity"))
    monkeypatch.setattr(m,"_load_actual_selection",lambda:pytest.fail("invalid activation must precede actual controls"))
    with pytest.raises(m.PilotParentCaptureError,match="not_activated"):
        m.run_actual_capture(expected_head="a"*40)


def test_actual_verifier_missing_isolation_flags_stops_before_any_replay(monkeypatch):
    _invented_activation(monkeypatch)
    def tripwire(*args,**kwargs):pytest.fail("missing native front must not inspect source or inputs")
    monkeypatch.setattr(m,"_verify_capture",tripwire)
    monkeypatch.setattr(m.source_runner,"_prove_isolation",tripwire)
    monkeypatch.setattr(m.exposure.bootstrap.custody,"_source_bytes",tripwire)
    monkeypatch.setattr(m,"sys",SimpleNamespace(flags=SimpleNamespace(isolated=1,no_site=0,dont_write_bytecode=1),
        pycache_prefix=m.source_runner.EMPTY_CACHE_PREFIX))
    with pytest.raises(ValueError,match="isolated_capture_verifier_required"):
        m.verify_actual_capture(expected_report_sha256="c"*64,execution_identity={})


def test_actual_verifier_changed_source_refuses_before_input_replay_with_fixture_cutpoints(monkeypatch):
    _invented_activation(monkeypatch);calls=[]
    monkeypatch.setattr(m,"sys",SimpleNamespace(flags=SimpleNamespace(isolated=1,no_site=1,dont_write_bytecode=1),
        pycache_prefix=m.source_runner.EMPTY_CACHE_PREFIX))
    monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:None)
    sources={m.SELF_PATH:"a"*64,m.TEST_PATH:"b"*64}
    identity={"root":str(m.LANE_ROOT),"branch":m.source_runner.LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}
    def changed(root,names):calls.append(tuple(names));return {}
    monkeypatch.setattr(m.exposure.bootstrap.custody,"_source_bytes",changed)
    monkeypatch.setattr(m,"_verify_capture",lambda **kwargs:pytest.fail("source mismatch must precede actual artifact replay"))
    with pytest.raises(ValueError,match="current_or_frozen_source_changed"):
        m.verify_actual_capture(expected_report_sha256="c"*64,execution_identity=identity)
    assert calls==[tuple(sources)]


def test_actual_input_preflight_missing_isolation_refuses_before_source_or_selection(monkeypatch):
    _invented_activation(monkeypatch)
    def tripwire(*args,**kwargs):pytest.fail("missing native preflight must precede every source/input read")
    monkeypatch.setattr(m,"_load_actual_selection",tripwire)
    monkeypatch.setattr(m,"_CaptureInputs",tripwire)
    monkeypatch.setattr(m.source_runner,"_prove_isolation",tripwire)
    monkeypatch.setattr(m.exposure.bootstrap.custody,"_source_bytes",tripwire)
    monkeypatch.setattr(m,"sys",SimpleNamespace(flags=SimpleNamespace(isolated=1,no_site=0,dont_write_bytecode=1),
        pycache_prefix=m.source_runner.EMPTY_CACHE_PREFIX))
    with pytest.raises(ValueError,match="isolated_capture_preflight_required"):
        m.preflight_actual_capture_inputs(execution_identity={})


def _preflight_cutpoints(monkeypatch,*,fault=None):
    """Invented metadata only; all actual source/input/contact cutpoints sealed."""
    payload,_=_invented_observer_selection();selection=m._seal(payload,observed=True)
    controls={name:BytesIO(("invented-"+name).encode())
        for name in ("reservation.json","terminal.json","complete.json")}
    monkeypatch.setattr(m,"ACTUAL_SELECTION_PINS",{name:(m._sha(stream.getvalue()),len(stream.getvalue()))
        for name,stream in controls.items()})
    monkeypatch.setattr(m,"ACTUAL_SELECTION_SHA256",selection.sha256)
    monkeypatch.setattr(m,"ACTUAL_SELECTION_HEAD","a"*40)
    monkeypatch.setattr(m,"sys",SimpleNamespace(flags=SimpleNamespace(isolated=1,no_site=1,dont_write_bytecode=1),
        pycache_prefix=m.source_runner.EMPTY_CACHE_PREFIX,exc_info=sys.exc_info))
    events=[];source_reads=[]
    sources={m.SELF_PATH:"a"*64,m.TEST_PATH:"b"*64}
    identity={"root":str(m.LANE_ROOT),"branch":m.source_runner.LANE_BRANCH,"head":"b"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":m._sha(m._raw(sources))}
    def source_bytes(root,names):
        source_reads.append(tuple(names));events.append("source")
        current=tuple(names)==tuple(sources)
        phase="early" if len(source_reads)<=2 else "late"
        if fault==phase+("_current" if current else "_frozen"):return {}
        return sources if current else m.source_runner.FROZEN
    class Hold:
        handles=[(name,stream,None,len(stream.getvalue())) for name,stream in controls.items()]
        def check(self):events.append("control_check")
        def close(self):
            events.append("control_close")
            if fault=="cleanup":raise OSError("PRIVATE CONTROL CLOSE")
    class Inputs:
        intake=SimpleNamespace(context={"leaf_count":84})
        exposed_accessions={_request(1)["accession_number"]} if fault=="consumed" else set()
        def __init__(self,value):
            assert value==payload;events.append("inputs")
        def recheck(self):
            events.append("input_check")
            if fault in {"input_change","cleanup"}:raise ValueError("invented_input_changed")
            if fault=="control_change":
                stream=controls["terminal.json"];stream.seek(0);stream.write(b"changed-")
        def final_recheck(self):events.append("input_final")
        def close(self):
            events.append("input_close")
            if fault=="cleanup":raise OSError("PRIVATE INPUT CLOSE")
    def load():events.append("selection");return selection,Hold()
    monkeypatch.setattr(m.source_runner,"_prove_isolation",lambda:events.append("native"))
    monkeypatch.setattr(m.exposure.bootstrap.custody,"_source_bytes",source_bytes)
    monkeypatch.setattr(m,"_load_actual_selection",load)
    monkeypatch.setattr(m,"_CaptureInputs",Inputs)
    def tripwire(*args,**kwargs):pytest.fail("preflight cannot create a namespace, read a contact, or dispatch")
    monkeypatch.setattr(m,"_NewDirectory",tripwire)
    monkeypatch.setattr(m,"_RAW_TRANSPORT",tripwire)
    monkeypatch.setattr(m.old,"_stdin_contact",tripwire);monkeypatch.setattr(m.old,"_getpass_contact",tripwire)
    return identity,events,source_reads


def test_actual_preflight_synthetic_holds_rechecks_source_controls_and_all84_without_namespace(monkeypatch):
    identity,events,source_reads=_preflight_cutpoints(monkeypatch)
    result=m.preflight_actual_capture_inputs(execution_identity=identity)
    assert result["schema"]==m.SCHEMA+"/input-preflight"
    assert result["selection_sha256"]==m.ACTUAL_SELECTION_SHA256
    assert result["selection_execution_head"]=="a"*40 and result["capture_execution_head"]=="b"*40
    assert result["source_inventory_sha256"]==identity["source_inventory_sha256"]
    assert result["selection_control_pins"]=={name:{"sha256":sha,"bytes":size}
        for name,(sha,size) in m.ACTUAL_SELECTION_PINS.items()}
    assert result["selected_count"]==64 and result["selected_prior_consumed_count"]==0
    assert result["held_intake_leaves"]==84 and result["current_master_period"]=="2021Q1"
    assert result["native_network_fork_allwrite_securityexec_denial"] is True
    assert result["output_namespace_created"] is False
    assert all(type(result[key]) is int and result[key]==0 for key in
        ("contact_reads","new_provider_requests","credential_reads","qc_accesses","outcome_looks","backtests"))
    assert result["authority"]==m.audit._AUTHORITY
    assert events[0]=="native" and events[-2:]==["control_close","input_close"]
    assert events.count("input_final")==1 and len(source_reads)==8


@pytest.mark.parametrize("fault",("early_current","early_frozen","late_current","late_frozen","consumed",
    "control_change","input_change","cleanup"))
def test_actual_preflight_changes_or_consumption_refuse_and_drain_invented_holds(monkeypatch,fault):
    identity,events,_=_preflight_cutpoints(monkeypatch,fault=fault)
    with pytest.raises(ValueError):m.preflight_actual_capture_inputs(execution_identity=identity)
    assert events[0]=="native"
    if fault.startswith("early_"):
        assert "selection" not in events and "inputs" not in events
    else:
        assert "control_close" in events
        if "inputs" in events:assert events[-2:]==["control_close","input_close"]
