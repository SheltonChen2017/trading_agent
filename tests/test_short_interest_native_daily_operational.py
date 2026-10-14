"""Fabricated request slots/files only; no source/key/provider/QC reads."""
from pathlib import Path
import threading
import urllib.request
import pytest
from data.hashing import hash_bytes,hash_payload,canonical_json
from scripts import short_interest_lane_batch_guard as lane
from scripts import continue_short_interest_native_identity as custody
from research.short_interest_etf import native_daily_active_reference as daily
from scripts import capture_short_interest_native_daily_operational as m
from data.exchange_calendar import trading_sessions
from datetime import date

def plan():
    return daily.freeze_daily_active_plan(tuple(at.isoformat() for at in trading_sessions(date(2022,1,3),date(2026,8,31))),calendar_sha256="a"*64)
def control():
    trace=[]; advanced=[False]
    def runner(root,command):
        trace.append(command[1])
        if command[1]=="rev-parse": return (str(lane.ROOT)+"\n").encode()
        if command[1]=="status": return ("# branch.oid "+"a"*40+"\n# branch.head "+lane.BRANCH+"\n").encode()
        return (("c"*40 if advanced[0] else "b"*40)+"\t"+lane.REF+"\n").encode()
    guard=lane.LaneGuard(lane.ROOT,expected_head="a"*40,expected_remote="b"*40,runner=runner,physical=lambda root:None)
    return m.DailyHTTPBatchGate(guard,plan(),lambda:None),trace,advanced
def start(gate,attempt,day):
    url=daily.first_url(gate.plan,day)
    value={"attempt":attempt,"day_ordinal":day,"page_ordinal":1,"query_date":gate.plan.sessions()[day-1],
        "plan_sha256":gate.plan.sha256,"request":{"url":url},"request_sha256":daily.page_request_sha256(url),
        "whole_page_bytes_reserved":daily.MAXIMUM_RESPONSE_BYTES,"whole_page_rows_reserved":1000}
    gate.register_start(f"day-{day:04d}-page-01.started.json",value)
    return value,urllib.request.Request(url,method="GET")
def close(gate,value):
    gate.record_closed_receipt(value)

def manifest(sha="c"*64):
    fallback=(str(Path(m.__file__).absolute()),str(lane.ROOT/"scripts/capture_short_interest_native_daily_active.py"),
        str(lane.ROOT/"data/exchange_calendar.py"),str(lane.ROOT/"scripts/short_interest_keychain.py"))
    paths=m.required_code_paths() if hasattr(m,"required_code_paths") else fallback
    return {path:sha for path in paths}

def test_only_eight_HTTP_starts_between_actual_remote_boundaries_no_timed_cache():
    gate,trace,_=control(); gate.initial()
    for number in range(1,10):
        value,request=start(gate,number,number)
        gate.authorize_HTTP(request,daily.MAXIMUM_RESPONSE_BYTES); close(gate,value)
    assert trace.count("ls-remote")==3  # initial, first slot, ninth slot
    assert trace.count("status")>=18

def test_remote_advance_halts_new_HTTP_but_already_started_slot_drains_locally():
    gate,trace,advanced=control(); gate.initial()
    for number in range(1,9):
        value,request=start(gate,number,number); gate.authorize_HTTP(request,daily.MAXIMUM_RESPONSE_BYTES); close(gate,value)
    value,request=start(gate,9,9); advanced[0]=True
    with pytest.raises(m.OperationalRefusal,match="stop_and_drain"):
        gate.authorize_HTTP(request,daily.MAXIMUM_RESPONSE_BYTES)
    remotes=trace.count("ls-remote"); close(gate,value)
    assert trace.count("ls-remote")==remotes and gate._slots=={}
    with pytest.raises(m.OperationalRefusal): start(gate,10,10)
    with pytest.raises(m.OperationalRefusal): gate.permit_success()

def test_wrong_request_or_repeat_attempt_cannot_acquire_another_slot():
    gate,_,_=control(); value,request=start(gate,1,1)
    with pytest.raises(m.OperationalRefusal): gate.authorize_HTTP(urllib.request.Request("https://outside.invalid"),daily.MAXIMUM_RESPONSE_BYTES)
    close(gate,value)
    with pytest.raises(m.OperationalRefusal): start(gate,1,2)

def test_caller_completion_flag_cannot_replace_typed_report_coverage():
    gate,_,_=control()
    with pytest.raises(m.OperationalRefusal): gate.complete_day(1)
    with pytest.raises(m.OperationalRefusal): gate.final({"complete_frozen_sequence":True,"planned_days":1169,"days_returned":1169,"http_invocations":0})
    with pytest.raises(m.OperationalRefusal): gate.observe_qualified({"complete":True})

def test_pending_literal_blocks_live_action(monkeypatch):
    monkeypatch.setattr(m,"SOURCE_ARCHIVE_SHA256","PENDING")
    with pytest.raises(m.OperationalRefusal,match="pending"): m.run_pending()

def test_owned_source_read_once_then_no_rehash_or_reader_per_check(tmp_path):
    tmp_path.chmod(0o700); file=tmp_path/"source.bin"; file.write_bytes(b"synthetic-only"); file.chmod(0o600)
    calls=[]; held=m.HeldPinnedFile(file,hash_bytes(b"synthetic-only"),100,boundary=lambda:calls.append("local"))
    try:
        original=held.bytes()
        for _ in range(10): assert held.bytes() is original
        assert len(calls)==2
        file.write_bytes(b"mutated")
        with pytest.raises(m.OperationalRefusal): held.check()
    finally: held.close()

@pytest.mark.parametrize("fault",["symlink","mode","hardlink"])
def test_source_protection_failures_before_any_read(tmp_path,fault):
    tmp_path.chmod(0o700); file=tmp_path/"source.bin"; file.write_bytes(b"synthetic-only"); file.chmod(0o600)
    if fault=="symlink":
        other=tmp_path/"alias"; other.symlink_to(file); file=other
    elif fault=="mode": file.chmod(0o644)
    else:
        import os; os.link(file,tmp_path/"alias")
    with pytest.raises(m.OperationalRefusal): m.HeldPinnedFile(file,hash_bytes(b"synthetic-only"),100)

def test_scoped_owned_output_no_unregistered_name_overwrite_or_success(tmp_path):
    tmp_path.chmod(0o700); directory=tmp_path/"output"; directory.mkdir(mode=0o700)
    gate,_,_=control()
    with custody._OwnedOutput(directory,lambda:None) as owned:
        publisher=m.ScopedPublisher(owned,gate,directory)
        with pytest.raises(m.OperationalRefusal): publisher.bytes(directory,"foreign.raw",b"synthetic")
        with pytest.raises(m.OperationalRefusal): publisher.bytes(directory,"day-0001-page-01.raw",b"unstarted")
        assert not (directory/"day-0001-page-01.raw").exists()
        with pytest.raises(m.OperationalRefusal): publisher.json(directory,"day-0001-page-01.received.json",{"day_ordinal":2,"page_ordinal":1})
        assert not (directory/"day-0001-page-01.received.json").exists()
        publisher.json(directory,"run.refused.json",{"complete":False})
        with pytest.raises(FileExistsError): publisher.json(directory,"run.refused.json",{"complete":False})
        with pytest.raises(m.OperationalRefusal): publisher.bytes(directory,"day-0001.qualified.private.json",b"{}")
        assert not (directory/"day-0001.qualified.private.json").exists()

def test_external_commit_and_complete_code_manifest_do_not_reset_stable_source_budget():
    before=hash_payload(m.protocol())
    first=m.RuntimeRegistration(head="a"*40,remote="b"*40,code_manifest=manifest())
    changed=m.RuntimeRegistration(head="d"*40,remote="b"*40,code_manifest=manifest("e"*64))
    assert first.marker()!=changed.marker() and hash_payload(m.protocol())==before
    assert "registered_head" not in m.protocol() and "code_pins" not in m.protocol()
    assert first.payload()["complete_current_code_manifest"]==manifest()

def test_controller_and_registration_reflection_cannot_rebind_source_or_lane():
    gate,_,_=control()
    gate.source_check=lambda:None
    with pytest.raises(m.OperationalRefusal,match="binding_changed"): gate.local_check()
    registration=m.RuntimeRegistration(head="a"*40,remote="b"*40,code_manifest=manifest())
    object.__setattr__(registration,"_anchor",("d"*40,"b"*40,(),"c"*64))
    with pytest.raises(m.OperationalRefusal,match="registration_changed"): registration.binding()

def test_rejected_remote_gate_has_zero_HTTP_callback_and_zero_wire(monkeypatch):
    gate,trace,advanced=control(); value,request=start(gate,1,1); advanced[0]=True
    callbacks=[]; wires=[]
    monkeypatch.setattr(m,"_http",lambda *args:wires.append(args))
    with pytest.raises(m.OperationalRefusal,match="stop_and_drain"):
        gate.transport(None,request,daily.MAXIMUM_RESPONSE_BYTES,on_http_start=lambda:callbacks.append(True))
    assert callbacks==wires==[] and gate._invocations==0
    value["http_invoked"]=False; close(gate,value)
    assert not gate._slots

def test_literal_eight_inflight_transport_starts_share_one_remote_boundary(monkeypatch):
    gate,trace,_=control(); gate.initial()
    barrier=threading.Barrier(8); callbacks=[]; errors=[]
    def wire(*args):
        barrier.wait(timeout=5)
        return b"{\"status\":\"OK\",\"results\":[]}","application/json",200
    monkeypatch.setattr(m,"_http",wire)
    def worker(number):
        try:
            value,request=start(gate,number,number)
            gate.transport(None,request,daily.MAXIMUM_RESPONSE_BYTES,on_http_start=lambda:callbacks.append(number))
            value["http_invoked"]=True; close(gate,value)
        except BaseException as error: errors.append(error)
    workers=[threading.Thread(target=worker,args=(number,)) for number in range(1,9)]
    for worker_thread in workers: worker_thread.start()
    for worker_thread in workers: worker_thread.join(timeout=10)
    assert not errors and not any(worker_thread.is_alive() for worker_thread in workers)
    assert sorted(callbacks)==list(range(1,9)) and gate._invocations==8 and gate._slots=={}
    assert trace.count("ls-remote")==2  # initial + one boundary for eight starts

def test_source_hash_and_read_operations_are_once_not_per_slot_or_64KiB_check(tmp_path,monkeypatch):
    tmp_path.chmod(0o700); path=tmp_path/"source"; raw=b"synthetic"*(20*1024)
    path.write_bytes(raw); path.chmod(0o600); sha=hash_bytes(raw)
    hashes=[]; reads=[]; oldhash=m.hash_bytes; oldread=m.os.read
    monkeypatch.setattr(m,"hash_bytes",lambda value:(hashes.append(len(value)),oldhash(value))[1])
    monkeypatch.setattr(m.os,"read",lambda fd,n:(reads.append(n),oldread(fd,n))[1])
    held=m.HeldPinnedFile(path,sha,len(raw))
    try:
        assert len(reads)==3 and hashes==[len(raw)]
        for _ in range(100): held.check(); assert held.bytes() is held._raw
        assert len(reads)==3 and hashes==[len(raw)]
    finally: held.close()

def test_exact_typed_daily_qualification_requires_owned_raw_and_original_index(tmp_path,monkeypatch):
    import io,zipfile
    from research.short_interest_etf import sharadar_securities_master as master
    output=io.BytesIO()
    with zipfile.ZipFile(output,"w",zipfile.ZIP_STORED) as zipped:
        zipped.writestr("tickers.csv","table,permaticker,ticker,exchange,isdelisted,category,figi\n"
            "stocks,1,SYN,XNYS,N,Domestic Common Stock Primary Class,BBG000000001\n")
    index=daily.identity.build_composite_native_index(master.CapturedSharadarMasterArchive(
        "tickers",output.getvalue(),master.request_sha256("download-tickers")))
    gate,_,_=control(); gate=m.DailyHTTPBatchGate(gate.guard,gate.plan,gate.source_check,index)
    raw=canonical_json({"status":"OK","results":[]}).encode()
    monkeypatch.setattr(m,"_http",lambda *args:(raw,"application/json",200))
    tmp_path.chmod(0o700); directory=tmp_path/"output"; directory.mkdir(mode=0o700)
    with custody._OwnedOutput(directory,lambda:None) as owned:
        publisher=m.ScopedPublisher(owned,gate,directory)
        value,request=start(gate,1,1)
        gate.transport(None,request,daily.MAXIMUM_RESPONSE_BYTES,on_http_start=lambda:None)
        publisher.bytes(directory,"day-0001-page-01.raw",raw)
        received=dict(value,http_invoked=True,raw_path="day-0001-page-01.raw",raw_sha256=hash_bytes(raw),raw_bytes=len(raw))
        publisher.json(directory,"day-0001-page-01.received.json",received)
        page=daily.CapturedDailyActiveReferencePage(gate.plan.sessions()[0],1,request.full_url,raw,
            "2026-10-14T00:00:00Z","2026-10-14T00:00:01Z",200,"application/json")
        qualified=daily.qualify_daily_active_reference(gate.plan,1,(page,),index,
            started_at="2026-10-14T00:00:00Z",retrieved_at="2026-10-14T00:00:01Z")
        gate.observe_qualified(qualified)
        publisher.bytes(directory,"day-0001.qualified.private.json",qualified.to_bytes())
        publisher.json(directory,"day-0001.completed.json",{"day_ordinal":1})
        assert gate._closed_days=={1} and gate._raw_receipts[(1,1)][0]==hash_bytes(raw)

def test_receipt_cannot_claim_unpublished_raw_or_wrong_request():
    gate,_,_=control(); value,_=start(gate,1,1)
    with pytest.raises(m.OperationalRefusal,match="only_started_slot"):
        close(gate,dict(value,request_sha256="f"*64))
    with pytest.raises(m.OperationalRefusal,match="raw_receipt"):
        close(gate,dict(value,raw_path="day-0001-page-01.raw",raw_sha256="f"*64,raw_bytes=2))

def test_private_parent_permission_change_is_detected_by_retained_slot_guard(tmp_path):
    tmp_path.chmod(0o700); path=tmp_path/"source"; path.write_bytes(b"synthetic"); path.chmod(0o600)
    held=m.HeldPinnedFile(path,hash_bytes(b"synthetic"),100)
    try:
        tmp_path.chmod(0o755)
        with pytest.raises(m.OperationalRefusal,match="parent"): held.check()
    finally: held.close(); tmp_path.chmod(0o700)

def test_private_parent_replacement_does_not_rebind_a_retained_source(tmp_path):
    parent=tmp_path/"parent"; parent.mkdir(mode=0o700); path=parent/"source"
    path.write_bytes(b"synthetic"); path.chmod(0o600)
    held=m.HeldPinnedFile(path,hash_bytes(b"synthetic"),100)
    try:
        old=tmp_path/"old-parent"; parent.rename(old); parent.mkdir(mode=0o700)
        (old/"source").rename(parent/"source")
        with pytest.raises(m.OperationalRefusal,match="parent"): held.check()
    finally: held.close()

@pytest.mark.parametrize("missing",["data/exchange_calendar.py","scripts/short_interest_keychain.py"])
def test_current_registration_cannot_omit_local_execution_dependency(missing):
    pins=manifest(); del pins[str(lane.ROOT/missing)]
    with pytest.raises(m.OperationalRefusal,match="complete.*manifest|manifest.*complete"):
        m.RuntimeRegistration(head="a"*40,remote="b"*40,code_manifest=pins)

def test_negative_inventory_retains_fresh_final_remote_observation_even_on_drift(tmp_path):
    import json
    tmp_path.chmod(0o700); directory=tmp_path/"output"; directory.mkdir(mode=0o700)
    gate,trace,advanced=control(); gate.initial(); before=trace.count("ls-remote"); advanced[0]=True
    with custody._OwnedOutput(directory,lambda:None) as owned:
        publisher=m.ScopedPublisher(owned,gate,directory)
        publisher.json(directory,"inventory.private.json",{"complete_frozen_sequence":False,
            "http_invocations":0,"retrieved_at":"2026-10-14T00:00:00Z"})
    assert trace.count("ls-remote")==before+1
    retained=json.loads((directory/"inventory.private.json").read_bytes())
    assert retained["final_remote_observation"]["matching_remote_equal"] is False
    assert retained["complete_frozen_sequence"] is False

def test_extra_unregistered_code_path_is_not_part_of_complete_manifest():
    pins=manifest(); pins[str(lane.ROOT/"synthetic-extra.py")]="d"*64
    with pytest.raises(m.OperationalRefusal,match="complete.*manifest"):
        m.RuntimeRegistration(head="a"*40,remote="b"*40,code_manifest=pins)

def test_current_registration_cannot_omit_transitive_immutable_allocator():
    pins=manifest(); pins.pop(str(lane.ROOT/"ml/immutable_io.py"),None)
    with pytest.raises(m.OperationalRefusal,match="complete.*manifest"):
        m.RuntimeRegistration(head="a"*40,remote="b"*40,code_manifest=pins)

def test_negative_remote_exception_is_retained_without_exception_detail(tmp_path,monkeypatch):
    import json
    tmp_path.chmod(0o700); directory=tmp_path/"output"; directory.mkdir(mode=0o700)
    gate,_,_=control()
    def unavailable(guard): raise OSError("FABRICATED-PRIVATE-DETAIL-DO-NOT-RETAIN")
    monkeypatch.setattr(lane.LaneGuard,"refresh",unavailable)
    with custody._OwnedOutput(directory,lambda:None) as owned:
        publisher=m.ScopedPublisher(owned,gate,directory)
        value=publisher.finish_round({"complete_frozen_sequence":False,"http_invocations":0})
    raw=(directory/"round.closed.json").read_bytes(); payload=json.loads(raw)
    assert b"PRIVATE-DETAIL" not in raw and value["complete_frozen_sequence"] is False
    assert payload["round_closure_status"]=="refused"
    assert payload["final_remote_observation"]["remote_status"]=="refused_or_unavailable"

def test_naked_complete_closed_record_cannot_replace_fresh_audit(tmp_path):
    tmp_path.chmod(0o700); directory=tmp_path/"output"; directory.mkdir(mode=0o700)
    gate,_,_=control()
    with custody._OwnedOutput(directory,lambda:None) as owned:
        publisher=m.ScopedPublisher(owned,gate,directory)
        with pytest.raises(m.OperationalRefusal,match="fresh_owned"):
            publisher.json(directory,"round.closed.json",{"complete_frozen_sequence":True})
    assert not (directory/"round.closed.json").exists()

def whole_typed_gate(monkeypatch):
    from test_short_interest_native_daily_runtime_seams import existing_fictional_helpers
    index=existing_fictional_helpers().native_index()
    prior,trace,advanced=control()
    gate=m.DailyHTTPBatchGate(prior.guard,prior.plan,prior.source_check,index)
    raw=b'{"status":"OK","results":[]}'
    monkeypatch.setattr(m,"_http",lambda *args:(raw,"application/json",200))
    for day in range(1,1170):
        value,request=start(gate,day,day)
        gate.transport(None,request,daily.MAXIMUM_RESPONSE_BYTES,on_http_start=lambda:None)
        name=f"day-{day:04d}-page-01.raw"
        gate.record_published_raw(name,raw)
        close(gate,dict(value,http_invoked=True,raw_path=name,raw_sha256=hash_bytes(raw),raw_bytes=len(raw)))
        page=daily.CapturedDailyActiveReferencePage(gate.plan.sessions()[day-1],1,request.full_url,raw,
            "2026-10-14T00:00:00Z","2026-10-14T00:00:01Z",200,"application/json")
        report=daily.qualify_daily_active_reference(gate.plan,day,(page,),index,
            started_at="2026-10-14T00:00:00Z",retrieved_at="2026-10-14T00:00:01Z")
        gate.observe_qualified(report); gate.complete_day(day)
    return gate,trace,advanced

def test_advance_after_provisional_positive_inventory_is_refused_at_authoritative_close(tmp_path,monkeypatch):
    import json
    gate,trace,advanced=whole_typed_gate(monkeypatch)
    value={"complete_frozen_sequence":True,"planned_days":1169,"days_returned":1169,"http_invocations":1169}
    tmp_path.chmod(0o700); directory=tmp_path/"output"; directory.mkdir(mode=0o700)
    with custody._OwnedOutput(directory,lambda:None) as owned:
        publisher=m.ScopedPublisher(owned,gate,directory)
        publisher.json(directory,"inventory.private.json",value)
        provisional=json.loads((directory/"inventory.private.json").read_bytes())
        assert provisional["complete_frozen_sequence"] is True
        assert provisional["round_closure_status"].startswith("provisional")
        before=trace.count("ls-remote"); advanced[0]=True
        closed=publisher.finish_round(value)
    assert trace.count("ls-remote")==before+1
    assert closed["complete_frozen_sequence"] is False
    assert closed["round_closure"]["round_closure_status"]=="refused"
    assert closed["round_closure"]["final_remote_observation"]["matching_remote_equal"] is False
    retained=json.loads((directory/"round.closed.json").read_bytes())
    assert retained["complete_frozen_sequence"] is False

def test_missing_typed_coverage_never_completes_on_matching_final_remote(tmp_path):
    gate,_,_=control()
    tmp_path.chmod(0o700); directory=tmp_path/"output"; directory.mkdir(mode=0o700)
    with custody._OwnedOutput(directory,lambda:None) as owned:
        publisher=m.ScopedPublisher(owned,gate,directory)
        closed=publisher.finish_round({"complete_frozen_sequence":True,"planned_days":1169,
            "days_returned":1169,"http_invocations":0})
    assert closed["complete_frozen_sequence"] is False
    assert closed["round_closure"]["final_remote_observation"]["matching_remote_equal"] is True
    assert closed["round_closure"]["final_remote_observation"]["all1169_typed_qualification_and_raw_receipts"] is False
