"""Genuine invented25-quarter plans; native-denied transport fixtures only."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
from urllib.parse import quote

import pytest

pytest.importorskip("fcntl",reason="macOS/POSIX capture custody")
pytest.importorskip("termios",reason="macOS/POSIX private contact")
from research import insider_buying_pilot_sec_parent_campaign_v2 as campaign
from research import insider_buying_pilot_sec_parent_capture as first
from research import insider_buying_pilot_sec_parent_batch_capture_v2 as m


CONTACT="invented@unit.test"


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    path=Path(__file__).with_name("test_insider_buying_pilot_sec_parent_campaign_v2.py")
    spec=importlib.util.spec_from_file_location("invented_batch_campaign_fixture",path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    return helper,helper.corpus.__wrapped__(tmp_path_factory)


@pytest.fixture(scope="module")
def plan(corpus):
    helper,values=corpus
    return helper._finish(helper._pipeline(values)).to_payload()


class Timer:
    def __init__(self):self.now,self.sleeps=0,[]
    def __call__(self):return self.now
    def sleep(self,seconds):self.sleeps.append(seconds);self.now+=round(seconds*1_000_000_000)


def _body(request):
    path=Path(__file__).with_name("test_insider_buying_sec_complete_submission.py")
    spec=importlib.util.spec_from_file_location("invented_batch_parent_fixture",path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    raw=helper._complete(header=helper._legacy_header())
    raw=raw.replace(b"0000999999-22-000001",request["accession_number"].encode()).replace(
        b"20221107",request["filing_date"].replace("-","").encode()).replace(b"0000123456",request["issuer_cik"].zfill(10).encode())
    if request["form_type"]=="4/A":
        raw=raw.replace(b"CONFORMED SUBMISSION TYPE:\t4\n",b"CONFORMED SUBMISSION TYPE:\t4/A\n").replace(
            b"FORM TYPE:\t4\n",b"FORM TYPE:\t4/A\n").replace(b"<TYPE>4\n",b"<TYPE>4/A\n").replace(b"<documentType>4</documentType>",b"<documentType>4/A</documentType>")
    return raw


def _response(raw,status=200):return first.SecHttpResult(status,(("Content-Length",str(len(raw))),),raw)
def _base(root):return root.joinpath(*campaign.CAPTURE_PARTS)
def _run_path(root,number=1):return _base(root)/"batches"/campaign._batch(number)
def _json(path):return json.loads(path.read_bytes())


def _wire(plan,calls,response=None,on_call=None,timer=None):
    requests={row["request"]["url"]:row["request"] for row in plan["requests"]}
    def wire(url,headers,maximum):
        calls.append((url,dict(headers),maximum,None if timer is None else timer.now))
        if on_call:on_call(url,headers,maximum)
        return _response(_body(requests[url])) if response is None else response
    return wire


def _run(root,plan,*,calls=None,timer=None,response=None,transport=None,contact=CONTACT,**kwargs):
    calls=[] if calls is None else calls;timer=Timer() if timer is None else timer
    options={"clock":lambda:"2026-10-25T12:00:00+00:00","monotonic_ns":timer,"sleep":timer.sleep,"free_bytes":lambda:1024**4}
    options.update(kwargs)
    return m._run_invented_batch(plan,root=root,transport=_wire(plan,calls,response,timer=timer) if transport is None else transport,
        contact=contact,**options)


def _verify(root,result,number=1):
    return m.verify_invented_batch(root,number,expected_complete_sha256=result["complete_sha256"],
        expected_plan_sha256=result["plan_sha256"],expected_index_sha256=result["index_sha256"])


def test_genuine64_source_requests_JIT_claims_cadence_private_custody_and_independent_readback(tmp_path,plan):
    calls=[];timer=Timer();selected=plan["requests"]
    def inspect(url,headers,maximum):
        index=len(calls)-1;request=selected[index]["request"]
        assert url==request["url"] and maximum==8*1024*1024
        assert CONTACT in headers["User-Agent"]
        run=_run_path(tmp_path)
        assert (run/"reservation.json").is_file()
        assert (run/"claims"/(campaign._sha(request["accession_number"].encode())+".json")).is_file()
        assert (run/f"request-{index:04d}-start.json").is_file()
    result=_run(tmp_path,plan,calls=calls,timer=timer,transport=_wire(plan,calls,on_call=inspect,timer=timer))
    assert len(calls)==64 and result["plan_sha256"]==campaign._sha(campaign._raw(plan))
    assert len(timer.sleeps)==64 and all(seconds==0.5 for seconds in timer.sleeps)
    assert all(after[3]-before[3]>=500000000 for before,after in zip(calls,calls[1:]))
    assert _verify(tmp_path,result)["complete_sha256"]==result["complete_sha256"]
    assert result["complete_sha256"]==campaign._sha((_run_path(tmp_path)/"complete.json").read_bytes())
    for path in _base(tmp_path).rglob("*"):
        assert stat.S_IMODE(path.stat().st_mode)==(0o700 if path.is_dir() else 0o600)
        if path.is_file() and path.suffix==".json":assert CONTACT.encode() not in path.read_bytes()
    with pytest.raises((ValueError,OSError)):_run(tmp_path,plan)


@pytest.mark.parametrize("status",(301,403,404,429,500))
def test_non200_is_once_only_no_body_hash_or_retention_and_claim_stays_consumed(tmp_path,plan,status):
    calls=[];result=_run(tmp_path,plan,calls=calls,response=first.SecHttpResult(status,(),b""))
    assert len(calls)==1 and len(list((_run_path(tmp_path)/"claims").iterdir()))==1
    assert not list((_run_path(tmp_path)/"objects").iterdir())
    assert _verify(tmp_path,result)["complete_sha256"]==result["complete_sha256"]
    with pytest.raises((ValueError,OSError)):_run(tmp_path,plan)


def test_transport_exception_is_ambiguous_permanent_not_retried_or_printed(tmp_path,plan):
    calls=[]
    def transport(*args):calls.append(args);raise OSError("PRIVATE-EXCEPTION-MUST-NOT-OUTPUT")
    result=_run(tmp_path,plan,transport=transport)
    assert len(calls)==1 and not list((_run_path(tmp_path)/"objects").iterdir())
    for path in _run_path(tmp_path).glob("*.json"):assert b"PRIVATE-EXCEPTION" not in path.read_bytes()
    assert _verify(tmp_path,result)["complete_sha256"]==result["complete_sha256"]


def test_header_identity_failure_keeps_original_quarantine_once_and_stops(tmp_path,plan):
    calls=[];raw=b"<SEC-DOCUMENT>invented ambiguous header\n</SEC-DOCUMENT>\n"
    result=_run(tmp_path,plan,calls=calls,response=_response(raw))
    assert len(calls)==1 and len(list((_run_path(tmp_path)/"objects").iterdir()))==1
    assert next((_run_path(tmp_path)/"objects").iterdir()).read_bytes()==raw
    assert _verify(tmp_path,result)["complete_sha256"]==result["complete_sha256"]


@pytest.mark.parametrize("encoding",("literal","percent","double-percent","unicode","html"))
@pytest.mark.parametrize("where",("body","headers"))
def test_contact_echo_refuses_before_any_response_hash_or_storage(tmp_path,plan,encoding,where):
    encoded={"literal":CONTACT,"percent":quote(CONTACT,safe=""),"double-percent":quote(quote(CONTACT,safe=""),safe=""),
        "unicode":"".join("\\u%04x"%ord(c) for c in CONTACT),"html":CONTACT.replace("@","&#64;")}[encoding]
    raw=_body(plan["requests"][0]["request"])
    if where=="body":raw+=encoded.encode()
    headers=(("Content-Length",str(len(raw))),)+((("X-Invented",encoded),) if where=="headers" else ())
    calls=[];result=_run(tmp_path,plan,calls=calls,response=first.SecHttpResult(200,headers,raw))
    assert len(calls)==1 and not list((_run_path(tmp_path)/"objects").iterdir())
    for path in _run_path(tmp_path).glob("*.json"):assert encoded.encode() not in path.read_bytes()
    assert _verify(tmp_path,result)["complete_sha256"]==result["complete_sha256"]


def test_declared_profile_does_not_mutate_frozen_original_parent_global():
    assert campaign.POLICY["transport_wall_seconds"]==30 and first.MAX_PARENT_BYTES==8*1024*1024


@pytest.mark.parametrize("fault",("fixture_false","selected_bool","source_hash","request_url","already_consumed"))
def test_bad_plan_refuses_before_contact_transport_or_namespace(tmp_path,plan,fault):
    changed=deepcopy(plan)
    if fault=="fixture_false":changed["fixture_only"]=False
    elif fault=="selected_bool":changed["selected_count"]=True
    elif fault=="source_hash":changed["requests"][0]["source_record_sha256"]="f"*64
    elif fault=="request_url":changed["requests"][0]["request"]["url"]="https://untrusted.invalid/parent.txt"
    else:
        changed["consumed_accessions"]=sorted([*changed["consumed_accessions"],changed["requests"][0]["request"]["accession_number"]])
        changed["consumed_index_sha256"]=campaign._sha(campaign._raw(changed["consumed_accessions"]))
    def forbidden(*args,**kwargs):pytest.fail("plan must refuse before callback")
    with pytest.raises(ValueError):_run(tmp_path,changed,transport=forbidden)
    assert not _base(tmp_path).exists()


def test_insufficient_disk_has_zero_transport_calls(tmp_path,plan):
    calls=[]
    with pytest.raises(ValueError):_run(tmp_path,plan,calls=calls,free_bytes=lambda:0)
    assert calls==[]


def test_initial_full_batch_disk_reserve_refuses_before_private_contact_read(tmp_path,plan):
    def contact():pytest.fail("private contact must not be read when full batch cannot fit")
    with pytest.raises(ValueError):_run(tmp_path,plan,free_bytes=lambda:0,contact=contact)


def test_source_guard_failure_before_publication_has_zero_transport(tmp_path,plan):
    calls=[]
    with pytest.raises(ValueError):_run(tmp_path,plan,calls=calls,guard=lambda:(_ for _ in ()).throw(ValueError("invented-source-drift")))
    assert calls==[]


@pytest.mark.parametrize("fault",("duplicate_length","conflicting_length","transfer_plus_length","encoded_body","over8MiB","wrong_length"))
def test_framing_failure_refuses_before_body_hash_even_with_valid_header(plan,monkeypatch,fault):
    raw=_body(plan["requests"][0]["request"]);headers=(("Content-Length",str(len(raw))),)
    if fault=="duplicate_length":headers*=2
    elif fault=="conflicting_length":headers+=(("Content-Length",str(len(raw)+1)),)
    elif fault=="transfer_plus_length":headers+=(("Transfer-Encoding","chunked"),)
    elif fault=="encoded_body":headers+=(("Content-Encoding","gzip"),)
    elif fault=="over8MiB":raw=b"x"*(8*1024*1024+1);headers=(("Content-Length",str(len(raw))),)
    else:headers=(("Content-Length",str(len(raw)+1)),)
    def forbidden(value):pytest.fail("unsafe bytes must not be hashed")
    monkeypatch.setattr(m,"_sha",forbidden)
    result=m._inspect_response(raw,headers,CONTACT,plan["requests"][0]["request"])
    assert result["accepted"] is False and result["body_sha256"] is result["body_bytes"] is result["headers_sha256"] is None


@pytest.mark.parametrize("where",("body","header-unicode","header-double-percent"))
def test_whole_contact_screen_precedes_any_response_cryptographic_hash(plan,monkeypatch,where):
    raw=_body(plan["requests"][0]["request"]);headers=(("Content-Length",str(len(raw))),)
    if where=="body":raw+=CONTACT.encode();headers=(("Content-Length",str(len(raw))),)
    else:
        encoded="".join("\\u%04x"%ord(c) for c in CONTACT) if where=="header-unicode" else quote(quote(CONTACT,safe=""),safe="")
        headers+=(("X-Invented",encoded),)
    monkeypatch.setattr(m,"_sha",lambda value:pytest.fail("contact-bearing response must not be hashed"))
    result=m._inspect_response(raw,headers,CONTACT,plan["requests"][0]["request"])
    assert result["accepted"] is False and result["body_sha256"] is result["headers_sha256"] is None


def _unit_dispatch(request,monkeypatch,*,guard=lambda:None,prove_start=lambda:None):
    """TEST-ONLY component simulation; never actual-front/authorization proof.

    Native process-tree denial + dummy HTTPS is required by these tests. The
    production registry is populated only after real held-source/native proof;
    no production fixture-authority API is added for this unit simulation.
    """
    monkeypatch.setattr(m,"_lane_boundary",lambda identity:None)
    held=SimpleNamespace(plan={"batch_number":1,"requests":[{"request":request}]})
    identity={"invented_component_simulation_only":True}
    auth=m._Authorization(m._TOKEN,held,identity,guard)
    m._AUTHORIZATIONS[auth]=(id(held),id(identity),id(guard),auth.plan_sha256,auth.number)
    context=m._Context(m._TOKEN,request,{},guard,prove_start,authorization=auth,ordinal=0)
    m._DISPATCH[context]=(id(auth),0,id(context.request),id(context.headers),id(context.guard),id(context.prove_start))
    return context


def test_default_transport_exactSEC_one_GET_non200_body_UNREAD_and_no_retry(plan,monkeypatch):
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**k:pytest.fail("initial opener tripwire"))
    calls=[]
    class Response:
        status=403
        def getheaders(self):return [("Location","https://untrusted.invalid/")]
        def read(self,*args):pytest.fail("non200 body must stay unread")
    class Connection:
        def __init__(self,host,*,timeout):calls.append(("connect",host,timeout))
        def request(self,method,path,headers):calls.append(("request",method,path,headers))
        def getresponse(self):return Response()
        def close(self):calls.append(("close",))
    monkeypatch.setattr(m.http.client,"HTTPSConnection",Connection)
    context=_unit_dispatch(plan["requests"][0]["request"],monkeypatch)
    response=m._production_transport(context)
    assert context.invoked is True and response.status==403 and response.body==b""
    assert calls[0]==("connect","www.sec.gov",15) and calls[1][1]=="GET"
    prior=list(calls)
    with pytest.raises(ValueError):m._production_transport(context)
    assert calls==prior and m.signal.getitimer(m.signal.ITIMER_REAL)==(0.,0.)


def test_direct_noop_context_cannot_authorize_production_transport(plan,monkeypatch):
    opened=[]
    class Response:
        status=403
        def getheaders(self):return []
        def read(self,*args):pytest.fail("non200 body must stay unread")
    class Connection:
        def __init__(self,*args,**kwargs):opened.append((args,kwargs))
        def request(self,*args,**kwargs):pass
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(m.http.client,"HTTPSConnection",Connection)
    context=m._Context(m._TOKEN,plan["requests"][0]["request"],{},lambda:None,lambda:None)
    with pytest.raises(ValueError):m._production_transport(context)
    assert opened==[] and context.invoked is False


def test_transport_source_refusal_and_unavailable_deadline_do_not_open_or_claim_invocation(plan,monkeypatch):
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**k:pytest.fail("no opener"))
    context=_unit_dispatch(plan["requests"][0]["request"],monkeypatch,guard=lambda:(_ for _ in ()).throw(ValueError("invented-source-drift")))
    with pytest.raises(ValueError):m._production_transport(context)
    assert context.invoked is False
    monkeypatch.setattr(m.signal,"getitimer",lambda _:(1.,0.))
    context=_unit_dispatch(plan["requests"][0]["request"],monkeypatch)
    with pytest.raises(ValueError):m._production_transport(context)
    assert context.invoked is False


def test_absolute_transport_deadline_is_restored_without_masking_primary(plan,monkeypatch):
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**k:pytest.fail("initial opener tripwire"))
    class Connection:
        def __init__(self,*args,**kwargs):pass
        def request(self,*args,**kwargs):raise m._Deadline()
        def close(self):raise OSError("PRIVATE cleanup")
    monkeypatch.setattr(m.http.client,"HTTPSConnection",Connection);previous=m.signal.getsignal(m.signal.SIGALRM)
    context=_unit_dispatch(plan["requests"][0]["request"],monkeypatch)
    with pytest.raises(m.BatchCaptureError,match="transport_deadline"):m._production_transport(context)
    assert context.invoked is True and m.signal.getsignal(m.signal.SIGALRM)==previous and m.signal.getitimer(m.signal.ITIMER_REAL)==(0.,0.)


def test_initial_worker_isolation_precedes_private_stdin_or_raw_body(monkeypatch):
    monkeypatch.setattr(m.sys,"stdin",None)
    monkeypatch.setattr(m.campaign,"_isolated",lambda:(_ for _ in ()).throw(ValueError("native-first")))
    with pytest.raises(ValueError,match="native-first"):m._inspection_worker({})


def test_native_inspection_command_uses_anonymous_stdin_not_contact_or_body(plan):
    command=m._command({"own_source_control_only":True},"inspect")
    assert CONTACT not in repr(command) and plan["requests"][0]["request"]["accession_number"] not in repr(command)
    assert command[:2]==("/usr/bin/env","-i") and all(flag in command for flag in ("-I","-S","-B"))
    policy=command[command.index("-p")+1]
    assert all(rule in policy for rule in ("deny network*","deny process-fork","deny file-write*","/usr/bin/security"))


def _replace_json(path,value):
    raw=campaign._raw(value);path.write_bytes(raw);return campaign._sha(raw)


def _repin_complete(root,result,complete):
    changed=dict(result);changed["complete_sha256"]=_replace_json(_run_path(root)/"complete.json",complete);return changed


@pytest.mark.parametrize("fault",("counts","authority","extra_file","index_missing_claim","index_claim_unstarted","claim_request","claim_bool_attempt","start_spacing","remote_measured","result_bool","result_digest","headers_digest","retained_content"))
def test_independent_readback_rejects_coherent_control_count_claim_and_body_mutations(tmp_path,plan,fault):
    result=_run(tmp_path,plan,response=_response(b"invented unbound header"));run=_run_path(tmp_path)
    complete=_json(run/"complete.json");entry=complete["results"][0]
    if fault=="counts":complete["header_bound_bodies"]=1
    elif fault=="authority":complete["authority"]["backtests"]=True
    elif fault=="extra_file":(run/"unexpected.json").write_bytes(b"{}")
    elif fault.startswith("index_"):
        index=_json(run/"consumed-index.json")
        if fault=="index_missing_claim":index["accessions"].remove(entry["accession_number"])
        else:index["accessions"]=sorted(set(index["accessions"])|{plan["requests"][1]["request"]["accession_number"]})
        result["index_sha256"]=_replace_json(run/"consumed-index.json",index);complete["index_sha256"]=result["index_sha256"]
    elif fault=="claim_request":
        claim=_json(run/"claims"/entry["claim_name"]);claim["request"]["issuer_cik"]="1"
        entry["claim_sha256"]=_replace_json(run/"claims"/entry["claim_name"],claim)
        start=_json(run/entry["start_name"]);start["claim_sha256"]=entry["claim_sha256"]
        entry["start_sha256"]=_replace_json(run/entry["start_name"],start)
        terminal=_json(run/entry["result_name"]);terminal["start_sha256"]=entry["start_sha256"]
        entry["result_sha256"]=_replace_json(run/entry["result_name"],terminal)
    elif fault in {"claim_bool_attempt","start_spacing"}:
        start=_json(run/entry["start_name"])
        if fault=="claim_bool_attempt":start["attempt"]=True
        else:start["started_monotonic_ns"]-=1
        entry["start_sha256"]=_replace_json(run/entry["start_name"],start)
        terminal=_json(run/entry["result_name"]);terminal["start_sha256"]=entry["start_sha256"]
        entry["result_sha256"]=_replace_json(run/entry["result_name"],terminal)
    elif fault in {"remote_measured","result_bool","result_digest","headers_digest"}:
        terminal=_json(run/entry["result_name"])
        if fault=="remote_measured":terminal["remote_request_count_measured"]=True
        elif fault=="result_bool":terminal["raw_transport_invocations"]=True
        elif fault=="result_digest":terminal["body_sha256"]="f"*64
        else:terminal["headers_sha256"]="e"*64
        entry["result_sha256"]=_replace_json(run/entry["result_name"],terminal)
    else:
        leaf=next((run/"objects").iterdir());raw=leaf.read_bytes();leaf.write_bytes(b"x"*len(raw))
    changed=_repin_complete(tmp_path,result,complete)
    with pytest.raises((ValueError,OSError)):_verify(tmp_path,changed)


@pytest.mark.parametrize("which",("complete","plan","index"))
def test_readback_external_pins_are_not_forged_from_own_current_controls(tmp_path,plan,which):
    result=_run(tmp_path,plan,response=first.SecHttpResult(403,(),b""));result[which+"_sha256"]="f"*64
    with pytest.raises(ValueError,match="external_readback_pins"):_verify(tmp_path,result)


def test_readback_samebyte_initial_ctime_change_is_not_new_output_settlement(tmp_path,plan,monkeypatch):
    result=_run(tmp_path,plan,response=first.SecHttpResult(403,(),b""));path=_run_path(tmp_path)/"complete.json"
    before=path.stat();original=m.os.read;changed=[]
    def read(fd,count):
        info=m.os.fstat(fd)
        if not changed and (info.st_dev,info.st_ino)==(before.st_dev,before.st_ino):
            changed.append(True);os.chmod(path,0o640);os.chmod(path,0o600)
        return original(fd,count)
    monkeypatch.setattr(m.os,"read",read)
    with pytest.raises(ValueError):_verify(tmp_path,result)
    assert changed and path.read_bytes()==campaign._raw(_json(path))


def test_readback_requires_shared_scope_lock_and_unchanged_file_inventory(tmp_path,plan):
    result=_run(tmp_path,plan,response=first.SecHttpResult(403,(),b""));fd=os.open(_run_path(tmp_path)/"scope.lock",os.O_RDONLY)
    try:
        m.fcntl.flock(fd,m.fcntl.LOCK_EX|m.fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):_verify(tmp_path,result)
    finally:os.close(fd)
    assert _verify(tmp_path,result)["complete_sha256"]==result["complete_sha256"]


def test_fixture_actual_alias_is_refused_before_namespace_transport_or_privatecontact(plan,monkeypatch):
    monkeypatch.setattr(m.archive,"_Output",lambda *args,**kwargs:pytest.fail("actual alias must refuse before namespace"))
    def forbidden(*args,**kwargs):pytest.fail("actual alias must refuse before callbacks")
    with pytest.raises(ValueError):_run(m.LANE_ROOT,plan,transport=forbidden,contact=forbidden)


def test_actual_front_rejects_source_before_controller_input_or_native_child(monkeypatch):
    monkeypatch.setattr(m.campaign,"_identity",lambda _:(_ for _ in ()).throw(ValueError("invented-source-refused")))
    for name in ("Controller","HeldBatchPlan"):
        monkeypatch.setattr(m.campaign,name,lambda *a,**k:pytest.fail("source failure before any namespace or plan"))
    monkeypatch.setattr(m.campaign,"_run_child",lambda *a,**k:pytest.fail("no native child after source failure"))
    monkeypatch.setattr(m,"BatchInputs",lambda *a,**k:pytest.fail("no actual input after source failure"))
    with pytest.raises(ValueError,match="invented-source-refused"):
        m.run_actual_batch("a"*40,batch_number=1,expected_plan_sha256="b"*64,expected_complete_sha256="c"*64,expected_producer_head="d"*40)


def test_private_CLI_arguments_and_precontact_stdin_echo_never_leak(monkeypatch,capsys):
    events=[]
    monkeypatch.setattr(m.first.old,"_protect_stdin_echo",lambda:events.append("protected") or "saved")
    monkeypatch.setattr(m.first.old,"_restore_stdin_echo",lambda saved:events.append(("restored",saved)))
    assert m.main(["--secret-contact",CONTACT])==2
    captured=capsys.readouterr()
    assert CONTACT not in captured.out+captured.err and captured.err==""
    assert json.loads(captured.out)=={"disposition":"batch_capture_refused"}
    assert events==["protected",("restored","saved")]


def test_two_genuine_batches_conserve_consumed_index_exact_parent_proof_and_finish_to_start_spacing(tmp_path,plan,corpus):
    timer=Timer();first_calls=[];one=_run(tmp_path,plan,calls=first_calls,timer=timer)
    lower=_verify(tmp_path,one);first_consumed=lower["index"]["accessions"]
    predecessor={"batch_number":1,"complete_sha256":one["complete_sha256"],"plan_sha256":one["plan_sha256"],
        "index_sha256":one["index_sha256"],"capture_execution_identity":lower["complete"]["execution_identity"],
        "first64_success_sha256":one["complete_sha256"],"last_finished_utc":lower["complete"]["last_finished_utc"],
        "capture_completed_without_refusal":True}
    helper,values=corpus;pipeline=helper._pipeline(values,consumed=first_consumed,number=2,limit=8)
    pipeline[0].predecessor=predecessor;second_plan=helper._finish(pipeline).to_payload()
    second_calls=[];two=_run(tmp_path,second_plan,calls=second_calls,timer=timer);higher=_verify(tmp_path,two,2)
    assert len(first_calls)==64 and len(second_calls)==8 and len(timer.sleeps)==72
    assert all(seconds==0.5 for seconds in timer.sleeps)
    assert second_calls[0][3]-first_calls[-1][3]>=500000000
    assert not {row[0] for row in first_calls}&{row[0] for row in second_calls}
    assert set(first_consumed)<set(higher["index"]["accessions"])
    assert higher["index"]["predecessor_index_sha256"]==one["index_sha256"]
    assert higher["complete"]["first64_predecessor_complete_sha256"]==one["complete_sha256"]
    m._validate_predecessor_link(higher,lower)
    assert _verify(tmp_path,one)["index_sha256"]==one["index_sha256"]


@pytest.mark.parametrize("fault",("authorization_unregistered","request","request_in_place","ordinal_bool","ordinal_outside","dispatch_notregistered","attempt_consumed"))
def test_unit_dispatch_registrations_cannot_change_request_ordinal_or_repeat_attempt(plan,monkeypatch,fault):
    context=_unit_dispatch(deepcopy(plan["requests"][0]["request"]),monkeypatch);opened=[]
    if fault=="authorization_unregistered":m._AUTHORIZATIONS.pop(context.authorization)
    elif fault=="request":context.request=plan["requests"][1]["request"]
    elif fault=="request_in_place":context.request["issuer_cik"]="1"
    elif fault=="ordinal_bool":context.ordinal=True
    elif fault=="ordinal_outside":context.ordinal=1
    elif fault=="dispatch_notregistered":m._DISPATCH.pop(context)
    else:context.authorization.attempted.add(0)
    class Response:
        status=403
        def getheaders(self):return []
    class Connection:
        def __init__(self,*args,**kwargs):opened.append((args,kwargs))
        def request(self,*args,**kwargs):pass
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(m.http.client,"HTTPSConnection",Connection)
    with pytest.raises(ValueError):m._production_transport(context)
    assert opened==[] and context.invoked is False


def test_authorization_constructor_alone_cannot_grant_capture(plan):
    held=SimpleNamespace(plan=plan);identity={"invented":True};guard=lambda:None
    value=m._Authorization(m._TOKEN,held,identity,guard)
    with pytest.raises(ValueError,match="genuine_capture_authorization"):m._authorized(value)


@pytest.mark.parametrize("fault",("none","root","branch","head","status"))
def test_cheap_lane_boundary_requires_exact_root_branch_HEAD_and_clean_status_without_source_Gitshow(monkeypatch,fault):
    calls=[];head="a"*40
    def git(root,*args):
        assert root==m.LANE_ROOT;calls.append(args)
        outputs={("rev-parse","--show-toplevel"):str(m.LANE_ROOT).encode(),("branch","--show-current"):campaign.LANE_BRANCH.encode(),
            ("rev-parse","HEAD"):head.encode(),("status","--porcelain=v1","--untracked-files=all"):b""}
        assert args in outputs,"metadata check must not traverseAST/Gitshowallsource"
        key={"root":("rev-parse","--show-toplevel"),"branch":("branch","--show-current"),"head":("rev-parse","HEAD"),"status":("status","--porcelain=v1","--untracked-files=all")}.get(fault)
        return b"unexpected" if args==key else outputs[args]
    monkeypatch.setattr(m.base.custody,"_git",git)
    if fault=="none":m._lane_boundary({"head":head});assert len(calls)==4
    else:
        with pytest.raises(ValueError,match="exact_clean_lane_before_dispatch"):m._lane_boundary({"head":head})


def test_HEAD_change_after_held_source_proof_stops_before_dummy_opener_and_attempt_latch(plan,monkeypatch):
    boundary=m._lane_boundary;events=[]
    context=_unit_dispatch(deepcopy(plan["requests"][0]["request"]),monkeypatch,
        guard=lambda:events.append("source_and_inputs_checked"),prove_start=lambda:events.append("durable_start_checked"))
    context.authorization.identity["head"]="a"*40
    monkeypatch.setattr(m,"_lane_boundary",boundary)
    def git(root,*args):
        if args==("rev-parse","--show-toplevel"):return str(m.LANE_ROOT).encode()
        if args==("branch","--show-current"):return campaign.LANE_BRANCH.encode()
        if args==("rev-parse","HEAD"):return b"b"*40
        pytest.fail("must stop at changedHEAD")
    monkeypatch.setattr(m.base.custody,"_git",git)
    monkeypatch.setattr(m.http.client,"HTTPSConnection",lambda *a,**k:pytest.fail("HEAD change must precede opener"))
    with pytest.raises(ValueError,match="exact_clean_lane_before_dispatch"):m._production_transport(context)
    assert events==["source_and_inputs_checked","durable_start_checked"]
    assert context.invoked is False and context.authorization.attempted==set()


# Claude review section 330: guards that in-memory mutants survived, and the
# readback's missing early-stop check. Each test fails if its guard is removed.

def test_readback_refuses_a_coherently_truncated_capture_without_a_final_refusal(tmp_path,plan):
    result=_run(tmp_path,plan);run=_run_path(tmp_path)
    complete=_json(run/"complete.json");keep=3
    for entry in complete["results"][keep:]:
        terminal=_json(run/entry["result_name"])
        for leaf in (run/"claims"/entry["claim_name"],run/entry["start_name"],run/entry["result_name"],
                     run/entry["result_name"].replace("-result.json","-headers.json"),run/"objects"/(terminal["body_sha256"]+".bin")):
            leaf.unlink()
    complete["results"]=complete["results"][:keep]
    index=_json(run/"consumed-index.json")
    index["accessions"]=sorted(set(plan["consumed_accessions"])|{entry["accession_number"] for entry in complete["results"]})
    result["index_sha256"]=complete["index_sha256"]=_replace_json(run/"consumed-index.json",index)
    complete.update(started_requests=keep,retained_bodies=keep,header_bound_bodies=keep,
        planned_unclaimed_unattempted=len(plan["requests"])-keep,capture_completed_without_refusal=False)
    with pytest.raises(m.BatchCaptureError,match="^batch_readback_unexplained_early_stop$"):
        _verify(tmp_path,_repin_complete(tmp_path,result,complete))


def test_non200_with_body_bytes_refuses_instead_of_recording_a_normal_stop(tmp_path,plan):
    with pytest.raises(m.BatchCaptureError,match="^batch_non200_body_unread$"):
        _run(tmp_path,plan,response=_response(b"unexpected",status=404))
    assert list((_run_path(tmp_path)/"objects").iterdir())==[]


def test_parent_binds_the_inspection_to_the_exact_body_it_retains(tmp_path,plan,monkeypatch):
    real=m._inspect_response
    monkeypatch.setattr(m,"_inspect_response",lambda *args:{**real(*args),"body_sha256":"f"*64})
    result=_run(tmp_path,plan);terminal=_json(_run_path(tmp_path)/"request-0000-result.json")
    assert terminal["failure_code"]=="native_inspection_refused" and terminal["body_retained"] is False
    assert list((_run_path(tmp_path)/"objects").iterdir())==[]
    assert result["started_requests"]==1 and result["retained_bodies"]==0


def test_empty_plan_refuses_before_namespace_or_private_contact(tmp_path,plan):
    empty=deepcopy(plan);empty["requests"]=[];empty["selected_count"]=0
    with pytest.raises(m.BatchCaptureError,match="^batch_empty_plan_no_contact$"):
        _run(tmp_path,empty,contact=lambda:pytest.fail("private contact read"))
    assert not _base(tmp_path).exists()
