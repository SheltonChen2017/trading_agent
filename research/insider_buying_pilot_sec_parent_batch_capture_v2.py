"""Additive bounded parent batches; original first64/archives are immutable.

Production requires externally observed planner pins, its Git lineage, a new
native full-source rederivation, continuously held inputs and one controller.
No QC/outcomes, retry, source promotion or backtest is implemented here.
"""
from __future__ import annotations

import argparse
import fcntl
import http.client
import json
import os
from pathlib import Path
import signal
import stat
import sys
import threading
import time
import weakref

from research import insider_buying_pilot_sec_parent_campaign_v2 as campaign
from research import insider_buying_sec_feed_archive_sample_v2 as fast_privacy

first,archive,base=campaign.first,campaign.archive,campaign.base
SCHEMA="insider-pilot-sec-parent-batch-capture-v2"
SELF_PATH=campaign.CAPTURE_SOURCE_PATH
TEST_PATH=campaign.CAPTURE_TEST_PATH
LANE_ROOT=campaign.LANE_ROOT
ARTIFACT_PARTS=campaign.CAPTURE_PARTS
MAX_PARENT_BYTES=8*1024*1024
MIN_FREE_BYTES=8*1024**3
SPACING_NS=500000000
TRANSPORT_SECONDS=30
LOCK_BYTES=b"INSETF-pilot-parent-batch-v2-private-single-attempt\n"
_raw,_sha,_decode=campaign._raw,campaign._sha,campaign._decode
AUTHORITY=dict(campaign.AUTHORITY)
_TOKEN=object();_DISPATCH=weakref.WeakKeyDictionary();_AUTHORIZATIONS=weakref.WeakKeyDictionary()
STAGES={"transport","HTTP_framing","header_privacy","body_privacy","header_identity","native_inspection","publication","complete"}
CODES={"transport_ambiguous","transport_deadline","HTTP_non200","HTTP_framing_refused","finite_privacy_refused",
    "header_identity_unbound","native_inspection_refused","native_inspection_deadline","none"}


class BatchCaptureError(ValueError):pass
class _Deadline(Exception):pass


def _need(value,code):
    if not value:raise BatchCaptureError(code)


def _stamp(clock):return first.custody._stamp(clock)


def _inspect_response(raw,headers,contact,request):
    """Pure opaque-parent privacy/header check; no financial-number parsing."""
    stage="HTTP_framing"
    try:
        _need(type(raw) is bytes and 0<len(raw)<=MAX_PARENT_BYTES,"HTTP_framing_refused")
        response=first.SecHttpResult(200,headers,raw)
        first._strict_selected_response(response,max_bytes=MAX_PARENT_BYTES)
        stage="header_privacy"
        for pair in headers:
            for value in pair:first.custody._screen_contact_echo(value,contact)
        stage="body_privacy"
        screen=fast_privacy._TextScreen(contact)
        for offset in range(0,len(raw),65536):screen.feed(raw[offset:offset+65536])
        screen.feed(b"",final=True)
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
        return {"schema":SCHEMA+"/inspection","accepted":False,"stage":stage,
            "code":"HTTP_framing_refused" if stage=="HTTP_framing" else "finite_privacy_refused",
            "body_sha256":None,"body_bytes":None,"headers_sha256":None,"header_bound":False}
    try:first.old._envelope_and_header(raw,request)
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):bound=False
    else:bound=True
    return {"schema":SCHEMA+"/inspection","accepted":True,"stage":"complete" if bound else "header_identity",
        "code":"none" if bound else "header_identity_unbound","body_sha256":_sha(raw),"body_bytes":len(raw),
        "headers_sha256":_sha(_raw(headers)),"header_bound":bound}


def _validate_inspection(value,raw,headers):
    _need(type(value) is dict and set(value)=={"schema","accepted","stage","code","body_sha256","body_bytes","headers_sha256","header_bound"}
        and value["schema"]==SCHEMA+"/inspection" and type(value["accepted"]) is bool and type(value["header_bound"]) is bool
        and value["stage"] in STAGES and value["code"] in CODES,"batch_inspection_schema")
    if value["accepted"]:
        _need(type(value["body_bytes"]) is int and value["body_bytes"]==len(raw)<=MAX_PARENT_BYTES
            and value["body_sha256"]==_sha(raw) and value["headers_sha256"]==_sha(_raw(headers))
            and (value["stage"],value["code"])==(("complete","none") if value["header_bound"] else ("header_identity","header_identity_unbound")),"batch_inspection_body_link")
    else:
        _need(value["header_bound"] is False and all(value[k] is None for k in ("body_sha256","body_bytes","headers_sha256"))
            and value["stage"] in {"HTTP_framing","header_privacy","body_privacy"},"batch_unretained_inspection")
    return value


def _inspection_worker(identity):
    campaign._isolated();campaign._current(identity)
    line=sys.stdin.buffer.readline(1024*1024+1)
    _need(line.endswith(b"\n") and len(line)<=1024*1024,"batch_private_stdin_header")
    value=_decode(line[:-1]);_need(set(value)=={"contact","request","headers","bytes"} and type(value["bytes"]) is int
        and 0<value["bytes"]<=MAX_PARENT_BYTES,"batch_private_stdin_schema")
    contact=first.custody._contact(value["contact"],observed=True);request=campaign._request(value["request"])
    headers=tuple(tuple(pair) for pair in value["headers"])
    raw=sys.stdin.buffer.read(value["bytes"]+1);_need(len(raw)==value["bytes"],"batch_private_stdin_body")
    result=_inspect_response(raw,headers,contact,request);campaign._current(identity);return result


def _command(identity,role,arguments=None):
    _need(role in {"inspect","readback"},"batch_worker_role")
    call="m._inspection_worker(identity)" if role=="inspect" else "m._readback_actual(identity,**"+repr(arguments)+")"
    code="import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_pilot_sec_parent_batch_capture_v2 as m;identity=json.loads("+repr(_raw(identity).decode())+");\ntry:r="+call+"\nexcept Exception:print(m.campaign._raw({'schema':m.campaign.SCHEMA+'/worker-refusal','phase':'source_identity','code':'native_or_control_refused'}).decode());sys.exit(2)\nprint(m._raw(r).decode())"
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+campaign.EMPTY_CACHE_PREFIX,"-c",code)


class _Authorization:
    def __init__(self,token,planhold,identity,guard):
        _need(token is _TOKEN,"batch_private_authorization_constructor")
        self.planhold,self.identity,self.guard=planhold,identity,guard
        self.plan_sha256=_sha(_raw(planhold.plan));self.number=planhold.plan["batch_number"];self.attempted=set()
        self.request_bytes=tuple(_raw(row["request"]) for row in planhold.plan["requests"])


def _authorized(value):
    _need(type(value) is _Authorization and _AUTHORIZATIONS.get(value)==(id(value.planhold),id(value.identity),id(value.guard),value.plan_sha256,value.number)
        and value.planhold.plan["batch_number"]==value.number,"batch_genuine_capture_authorization")
    return value


class _Context:
    def __init__(self,token,request,headers,guard,prove_start,*,authorization=None,ordinal=None):
        _need(token is _TOKEN,"batch_genuine_context")
        self.request,self.headers,self.guard,self.prove_start=request,headers,guard,prove_start;self.invoked=False
        self.authorization,self.ordinal=authorization,ordinal
        # Constructors never register dispatch or acquisition authority.


def _lane_boundary(identity):
    """Trusted-parent metadata only; no AST/all-source/Git-show per request."""
    _need(Path.cwd()==LANE_ROOT and LANE_ROOT.resolve()==LANE_ROOT
        and base.custody._git(LANE_ROOT,"rev-parse","--show-toplevel").decode().strip()==str(LANE_ROOT)
        and base.custody._git(LANE_ROOT,"branch","--show-current").decode().strip()==campaign.LANE_BRANCH
        and base.custody._git(LANE_ROOT,"rev-parse","HEAD").decode().strip()==identity["head"]
        and base.custody._git(LANE_ROOT,"status","--porcelain=v1","--untracked-files=all")==b"","batch_exact_clean_lane_before_dispatch")


def _production_transport(context):
    _need(type(context) is _Context and not context.invoked,"batch_genuine_dispatch")
    authorization=_authorized(context.authorization)
    _need(type(context.ordinal) is int and 0<=context.ordinal<len(authorization.planhold.plan["requests"])
        and context.ordinal not in authorization.attempted
        and context.request==authorization.planhold.plan["requests"][context.ordinal]["request"]
        and _raw(context.request)==authorization.request_bytes[context.ordinal]
        and _DISPATCH.get(context)==(id(authorization),context.ordinal,id(context.request),id(context.headers),id(context.guard),id(context.prove_start)),"batch_genuine_dispatch")
    request=campaign._request(context.request);context.guard();context.prove_start();_lane_boundary(authorization.identity)
    _need(threading.current_thread() is threading.main_thread() and signal.getitimer(signal.ITIMER_REAL)==(0.,0.),"batch_deadline_unavailable")
    previous=signal.getsignal(signal.SIGALRM);connection=None;started=time.monotonic()
    def expired(*a):raise _Deadline()
    signal.signal(signal.SIGALRM,expired)
    try:
        signal.setitimer(signal.ITIMER_REAL,TRANSPORT_SECONDS);context.invoked=True;authorization.attempted.add(context.ordinal)
        connection=http.client.HTTPSConnection("www.sec.gov",timeout=15)
        connection.request("GET",request["url"].removeprefix("https://www.sec.gov"),headers=context.headers)
        response=connection.getresponse();_need(type(response.status) is int,"batch_HTTP_status")
        pairs=tuple(response.getheaders())
        if response.status!=200:return first.SecHttpResult(response.status,pairs,b"")
        mode,size=archive._framing(pairs,MAX_PARENT_BYTES)
        _need(mode!="chunked" or response.chunked is True,"batch_chunk_framing")
        raw=response.read(size if mode=="length" else MAX_PARENT_BYTES+1)
        _need(mode!="chunked" or response.read(1)==b"" and response.isclosed(),"batch_chunk_terminal")
        result=first.SecHttpResult(200,pairs,raw);first._strict_selected_response(result,max_bytes=MAX_PARENT_BYTES)
        _need(time.monotonic()-started<=TRANSPORT_SECONDS,"batch_transport_deadline");return result
    except _Deadline:raise BatchCaptureError("batch_transport_deadline") from None
    finally:
        primary=sys.exc_info()[0] is not None;failed=False
        for cleanup in (lambda:signal.setitimer(signal.ITIMER_REAL,0),lambda:signal.signal(signal.SIGALRM,previous),*((connection.close,) if connection else ())):
            try:cleanup()
            except BaseException:failed=True
        if failed and not primary:raise BatchCaptureError("batch_transport_cleanup")


def _capture(*,root,plan,planner_receipt,identity,fixture,transport,contact,guard,inspector,clock,monotonic_ns,sleep,free_bytes,authorization=None):
    campaign.validate_batch_plan(plan);number=plan["batch_number"];name=campaign._batch(number)
    if fixture:
        first._fixture_root(root);first._native_fixture_denial()
        _need(plan["fixture_only"] is True and callable(transport) and transport is not _production_transport
            and contact not in {first.old._stdin_contact,first.old._getpass_contact},"batch_fixture_callbacks_only")
    else:
        _need(root==LANE_ROOT and plan["fixture_only"] is False and transport is _production_transport
            and contact is first.old._stdin_contact and inspector is None,"batch_fixed_actual_callbacks")
        _authorized(authorization)
        _need(authorization.identity is identity and authorization.guard is guard and authorization.plan_sha256==_sha(_raw(plan)),"batch_actual_authorization_binding")
    rows=plan["requests"];_need(0<len(rows)<=plan["limit"],"batch_empty_plan_no_contact")
    reservation={"schema":SCHEMA+"/reservation","batch_number":number,"fixture_only":fixture,"execution_identity":identity,
        "planner_receipt":planner_receipt,"plan_sha256":_sha(_raw(plan)),"planned_requests":len(rows),"policy":campaign.POLICY,"authority":dict(AUTHORITY)}
    _need(_decode(_raw(reservation))==reservation,"batch_production_control_roundtrip")
    folders=[];lock=None;guard()
    try:
        top=archive._Output(root.joinpath(*ARTIFACT_PARTS),create=True);folders.append(top)
        batches=archive._Output(top.path/"batches",create=True);folders.append(batches)
        _need(set(os.listdir(top.fd))=={"batches"} and set(os.listdir(batches.fd))=={campaign._batch(n) for n in range(1,number)},"batch_capture_namespace_consumed_or_gap")
        run=archive._Output(batches.path/name,create=True);folders.append(run)
        claims=archive._Output(run.path/"claims",create=True);objects=archive._Output(run.path/"objects",create=True);folders.extend((claims,objects))
        run.publish("scope.lock",LOCK_BYTES);lock=os.open("scope.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=run.fd)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);lockversion=archive._version(os.fstat(lock))
        expected={"scope.lock","claims","objects"};claim_names=set();object_names=set()
        def check():
            guard()
            for held in folders:held.check()
            _need(set(os.listdir(top.fd))=={"batches"} and set(os.listdir(batches.fd))=={campaign._batch(n) for n in range(1,number+1)}
                and set(os.listdir(run.fd))==expected and set(os.listdir(claims.fd))==claim_names and set(os.listdir(objects.fd))==object_names
                and archive._version(os.fstat(lock))==lockversion==archive._version(os.stat("scope.lock",dir_fd=run.fd,follow_symlinks=False)),"batch_output_inventory_or_lock_changed")
        def publish(leaf,value):
            digest=run.publish(leaf,_raw(value),cap=campaign.MAX_CONTROL);expected.add(leaf);check();return digest
        initial_capacity=free_bytes() if free_bytes else os.fstatvfs(run.fd).f_bavail*os.fstatvfs(run.fd).f_frsize
        _need(type(initial_capacity) is int and initial_capacity>=MIN_FREE_BYTES+len(rows)*MAX_PARENT_BYTES,"batch_initial_full_disk_reserve")
        rsha=publish("reservation.json",reservation)
        publish("plan.json",plan)
        private=first.custody._contact(contact(),observed=not fixture);archive._contact_needles(private)
        publish("contact-validated.json",{"schema":SCHEMA+"/contact","reservation_sha256":rsha,"contact_present":True,"contact_value_stored_or_hashed":False})
        results=[];consumed=set(plan["consumed_accessions"]);retained=bound=0;previous_finish=monotonic_ns()
        _need(type(previous_finish) is int and previous_finish>=0,"batch_initial_clock")
        publish("rate-origin.json",{"schema":SCHEMA+"/rate-origin","reservation_sha256":rsha,"origin_monotonic_ns":previous_finish})
        for ordinal,row in enumerate(rows):
            check();request=row["request"];accession=request["accession_number"]
            _need(accession not in consumed,"batch_permanent_accession_consumed")
            capacity=free_bytes() if free_bytes else os.fstatvfs(run.fd).f_bavail*os.fstatvfs(run.fd).f_frsize
            _need(type(capacity) is int and capacity>=MIN_FREE_BYTES+(len(rows)-ordinal)*MAX_PARENT_BYTES,"batch_remaining_disk_reserve")
            claim={"schema":SCHEMA+"/claim","batch_number":number,"reservation_sha256":rsha,"request_sha256":row["request_sha256"],"request":request,"claimed_at_utc":_stamp(clock)}
            cname=_sha(accession.encode())+".json";csha=claims.publish(cname,_raw(claim),cap=campaign.MAX_CONTROL);claim_names.add(cname);consumed.add(accession);check()
            now=monotonic_ns();_need(type(now) is int and now>=previous_finish,"batch_monotonic_clock")
            if now-previous_finish<SPACING_NS:sleep((SPACING_NS-now+previous_finish)/1e9)
            started=monotonic_ns();_need(type(started) is int and started-previous_finish>=SPACING_NS,"batch_cross_boundary_spacing")
            sname=f"request-{ordinal:04d}-start.json"
            start={"schema":SCHEMA+"/start","ordinal":ordinal,"attempt":1,"claim_sha256":csha,"request_sha256":row["request_sha256"],"started_utc":_stamp(clock),"started_monotonic_ns":started}
            ssha=publish(sname,start)
            def prove_start():
                check();_need(run.read(sname)==_raw(start) and claims.read(cname)==_raw(claim),"batch_durable_start_claim")
            headers={"User-Agent":"InsiderBuyingResearch-PilotCampaign/2.0 ("+private+")","Accept":"*/*","Accept-Encoding":"identity","Connection":"close"}
            response=None;context=None;invoked=0;stage="transport";code="transport_ambiguous"
            try:
                if fixture:prove_start();invoked=1;response=transport(request["url"],headers,MAX_PARENT_BYTES)
                else:
                    _authorized(authorization);prove_start()
                    context=_Context(_TOKEN,request,headers,check,prove_start,authorization=authorization,ordinal=ordinal)
                    _DISPATCH[context]=(id(authorization),ordinal,id(request),id(headers),id(check),id(prove_start))
                    response=_production_transport(context);invoked=int(context.invoked)
            except Exception as error:
                if context:invoked=int(context.invoked)
                if type(error) is BatchCaptureError and str(error)=="batch_transport_deadline":code="transport_deadline"
            check();status=None;inspection=None;body_sha=body_size=header_sha=None
            if response is not None:
                _need(type(response) is first.SecHttpResult and type(response.status) is int and 100<=response.status<=599,"batch_response_type")
                status=response.status;stage="HTTP_framing";code="HTTP_non200"
                if status!=200:_need(response.body==b"","batch_non200_body_unread")
                else:
                    try:
                        if fixture:inspection=inspector(response.body,response.headers,private,request)
                        else:
                            payload=_raw({"contact":private,"request":request,"headers":response.headers,"bytes":len(response.body)})+b"\n"+response.body
                            inspection=campaign._run_child(_command(identity,"inspect"),payload,timeout=90)
                        _validate_inspection(inspection,response.body,response.headers);stage,code=inspection["stage"],inspection["code"]
                    except Exception as error:
                        inspection=None;stage="native_inspection";code="native_inspection_deadline" if type(error) is campaign.CampaignError and str(error)=="campaign_native_worker_deadline" else "native_inspection_refused"
                    if inspection is not None and inspection["accepted"]:
                        body_sha,body_size,header_sha=inspection["body_sha256"],inspection["body_bytes"],inspection["headers_sha256"]
                        oname=body_sha+".bin"
                        if oname in object_names:_need(objects.read(oname,MAX_PARENT_BYTES)==response.body,"batch_same_object_changed")
                        else:objects.publish(oname,response.body,cap=MAX_PARENT_BYTES);object_names.add(oname)
                        publish(f"request-{ordinal:04d}-headers.json",{"headers":response.headers})
                        retained+=1;bound+=int(inspection["header_bound"]);check()
            finished=monotonic_ns();_need(type(finished) is int and finished>=started,"batch_finish_clock");previous_finish=finished
            terminal={"schema":SCHEMA+"/result","ordinal":ordinal,"attempt":1,"request_sha256":row["request_sha256"],"start_sha256":ssha,
                "raw_transport_invocations":invoked,"remote_request_count_measured":False,"http_status":status,"failure_stage":stage,"failure_code":code,
                "body_retained":body_sha is not None,"body_sha256":body_sha,"body_bytes":body_size,"headers_sha256":header_sha,
                "header_bound":bool(inspection and inspection["accepted"] and inspection["header_bound"]),"finished_utc":_stamp(clock),"finished_monotonic_ns":finished}
            _validate_terminal(terminal,row,ordinal,ssha)
            leaf=f"request-{ordinal:04d}-result.json";tsha=publish(leaf,terminal)
            results.append({"accession_number":accession,"claim_name":cname,"claim_sha256":csha,"start_name":sname,"start_sha256":ssha,"result_name":leaf,"result_sha256":tsha})
            if not terminal["header_bound"]:break
        index={"schema":campaign.SCHEMA+"/consumed-index","generation":number,"accessions":sorted(consumed),"plan_sha256":_sha(_raw(plan)),
            "predecessor_index_sha256":plan["predecessor"]["index_sha256"] if plan["predecessor"] else None,
            "base_consumption":plan["base_consumption"],"archive_exposures":list(campaign.ARCHIVE_EXPOSURES),"archive_membership_known":False,"authority":dict(AUTHORITY)}
        isha=publish("consumed-index.json",index)
        complete={"schema":SCHEMA+"/complete","batch_number":number,"fixture_only":fixture,"execution_identity":identity,"planner_receipt":planner_receipt,
            "reservation_sha256":rsha,"plan_sha256":_sha(_raw(plan)),"index_sha256":isha,"planned_requests":len(rows),"started_requests":len(results),
            "retained_bodies":retained,"header_bound_bodies":bound,"planned_unclaimed_unattempted":len(rows)-len(results),
            "capture_completed_without_refusal":len(results)==retained==bound==len(rows),"last_finished_utc":terminal["finished_utc"],
            "first64_predecessor_complete_sha256":plan["predecessor"]["first64_success_sha256"] if plan["predecessor"] else None,
            "results":results,"authority":dict(AUTHORITY)}
        csha=publish("complete.json",complete);check()
        return {"schema":SCHEMA+"/public","batch_number":number,"complete_sha256":csha,"index_sha256":isha,"plan_sha256":complete["plan_sha256"],
            **{k:complete[k] for k in ("planned_requests","started_requests","retained_bodies","header_bound_bodies","planned_unclaimed_unattempted","capture_completed_without_refusal")},"authority":dict(AUTHORITY)}
    finally:base.selector._close_all((archive.SimpleCloseFD(lock),*reversed(folders)),phase="batch_capture_cleanup")


def _run_invented_batch(plan,*,root,transport,contact="invented@unit.test",guard=lambda:None,clock=first.custody._utc,
    monotonic_ns=time.monotonic_ns,sleep=time.sleep,free_bytes=None):
    if type(plan) is campaign.CampaignBatch:plan=plan.to_payload()
    root=Path(root);identity={"fixture_only":True};pins={"fixture_only":True}
    reader=contact if callable(contact) else lambda:contact
    return _capture(root=root,plan=plan,planner_receipt=pins,identity=identity,fixture=True,transport=transport,contact=reader,guard=guard,
        inspector=_inspect_response,clock=clock,monotonic_ns=monotonic_ns,sleep=sleep,free_bytes=free_bytes)


def _tree_versions(tree):
    """No large journal rehash per dispatch; strict held identities still bind."""
    for _parts,(chain,names) in tree.directories.items():
        chain.recheck();info=os.fstat(chain.fd)
        _need(info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o700 and tuple(sorted(os.listdir(chain.fd)))==names,"batch_old_directory_changed")
    for parts,name,_digest,version,_cap in tree.leaves.values():
        _need(first.exposure.bootstrap.custody._version(os.stat(name,dir_fd=tree.directories[parts][0].fd,follow_symlinks=False))==version,"batch_old_leaf_changed")
    for chain,name,fd,version in tree.locks:
        _need(first.exposure.bootstrap.custody._version(os.fstat(fd))==version==first.exposure.bootstrap.custody._version(os.stat(name,dir_fd=chain.fd,follow_symlinks=False)),"batch_old_lock_changed")


class SourceHold:
    def __init__(self,identity):
        self.identity,self.rows=identity,[]
        try:
            campaign._current(identity)
            for name,digest in identity["source_sha256"].items():
                path=Path(name);chain=base.custody._Chain(LANE_ROOT,path.parts[:-1]);self.rows.append((chain,path.name,None,digest))
                before=base.custody._version(os.stat(path.name,dir_fd=chain.fd,follow_symlinks=False))
                raw=base.custody._read_leaf(chain.fd,path.name,limit=4*1024*1024,private=False)
                _need(_sha(raw)==digest and base.custody._version(os.stat(path.name,dir_fd=chain.fd,follow_symlinks=False))==before,"batch_source_initial_bytes")
                self.rows[-1]=(chain,path.name,before,digest)
            self.recheck()
        except BaseException:self.close();raise
    def recheck(self,*,full=False):
        for chain,name,version,digest in self.rows:
            chain.recheck();_need(base.custody._version(os.stat(name,dir_fd=chain.fd,follow_symlinks=False))==version,"batch_held_source_changed")
            if full:_need(_sha(base.custody._read_leaf(chain.fd,name,limit=4*1024*1024,private=False))==digest,"batch_held_source_bytes_changed")
        if full:campaign._current(self.identity)
    def close(self):
        base.selector._close_all(tuple(row[0] for row in self.rows),phase="batch_source_close");self.rows=[]


class BatchInputs:
    """Old inputs held throughout capture; source bodies are never decoded."""
    def __init__(self,plan):
        self.prior=self.intake=self.latest=None
        try:
            self.prior=first._PriorRoots({"exposure_inventory_sha256":plan["base_consumption"]["old_exposure_inventory_sha256"]})
            self.intake=base.selector._HeldIntake()
            bootstrap=first.exposure.bootstrap
            self.latest=bootstrap._Tree(bootstrap.RootSpec("campaign-prior-new64",LANE_ROOT.joinpath(*first.ARTIFACT_PARTS),"global-claims"))
            parts=("runs",first.CAPTURE_ID)
            report_raw=self.latest.read(parts,"complete.json",expected=archive.original.CAPTURE_REPORT_SHA256)
            reservation=self.latest.read(parts,"reservation.json")
            identity,report,selection=archive.original._original_controls(report_raw,reservation)
            _need(identity["head"]==archive.original.CAPTURE_HEAD,"batch_new64_execution_head")
            accessions=[]
            for ordinal,(row,descriptor) in enumerate(zip(selection["requests"],report["results"],strict=True)):
                start=self.latest.read(parts,f"request-{ordinal:03d}-start.json")
                result=self.latest.read(parts,f"request-{ordinal:03d}-result.json",expected=descriptor["result_sha256"])
                accession=row["request"]["accession_number"];claim=self.latest.read(("claims",),_sha(accession.encode())+".json")
                parsed=first._decode(start)
                _need(parsed["claim_sha256"]==_sha(claim) and first._decode(result)["start_sha256"]==_sha(start),"batch_new64_durable_controls")
                accessions.append(accession)
            _need(len(accessions)==64 and set(accessions)|self.prior.exposed_accessions<=set(plan["consumed_accessions"]),"batch_consumed_base_index")
            self.recheck(full=True)
        except BaseException:self.close();raise
    def recheck(self,*,full=False):
        for tree in self.prior.trees:_tree_versions(tree)
        _tree_versions(self.latest);self.intake.tree.check()
        if full:
            self.prior.recheck();self.latest.recheck();self.intake.recheck()
    def close(self):
        base.selector._close_all((self.intake,self.latest,self.prior),phase="batch_input_close")
        self.prior=self.intake=self.latest=None


def run_actual_batch(expected_head,*,batch_number,expected_plan_sha256,expected_complete_sha256,expected_producer_head):
    """CLI must protect queued stdin before this precontact work begins."""
    identity=campaign._identity(expected_head);controller=planhold=inputs=sources=authorization=None
    try:
        controller=campaign.Controller(LANE_ROOT)
        _need(controller.expected_batches=={campaign._batch(n) for n in range(1,batch_number+1)},"batch_planner_prefix_required")
        planhold=campaign.HeldBatchPlan(LANE_ROOT,batch_number,expected_plan_sha256=expected_plan_sha256,
            expected_complete_sha256=expected_complete_sha256,expected_producer_head=expected_producer_head)
        campaign.verify_plan_producer(planhold.receipt)
        predecessor=planhold.plan["predecessor"]
        priorpins={k:predecessor[k] for k in ("complete_sha256","plan_sha256","index_sha256")} if predecessor else None
        observed=campaign._run_child(campaign._command(identity,batch_number,priorpins),timeout=900)
        fresh=campaign._validate_worker(observed,identity,batch_number)
        _need(_raw(fresh)==_raw(planhold.plan),"batch_native_current_source_rederivation")
        inputs=BatchInputs(planhold.plan);sources=SourceHold(identity)
        def guard():controller.check();planhold.recheck();inputs.recheck();sources.recheck()
        guard();planhold.recheck(full=True)
        authorization=_Authorization(_TOKEN,planhold,identity,guard)
        # This is the sole registration point, after genuine fixed-root pins,
        # producer Git, native rederivation, held source/input proofs above.
        _AUTHORIZATIONS[authorization]=(id(planhold),id(identity),id(guard),authorization.plan_sha256,authorization.number)
        result=_capture(root=LANE_ROOT,plan=planhold.plan,planner_receipt=planhold.receipt,identity=identity,fixture=False,
            transport=_production_transport,contact=first.old._stdin_contact,guard=guard,inspector=None,
            clock=first.custody._utc,monotonic_ns=time.monotonic_ns,sleep=time.sleep,free_bytes=None,authorization=authorization)
        guard();planhold.recheck(full=True);inputs.recheck(full=True);sources.recheck(full=True)
        _need(campaign._identity(expected_head)==identity,"batch_parent_final_source_identity");return result
    finally:
        if authorization:_AUTHORIZATIONS.pop(authorization,None)
        base.selector._close_all((sources,inputs,planhold,controller),phase="batch_actual_cleanup")


class _Snapshot:
    """OLD private capture inputs: strict ctime before first byte and at end."""
    def __init__(self,root,number):
        self.folders=[];self.pins=[];self.lock=None
        try:
            self.top=self.open(root.joinpath(*ARTIFACT_PARTS));self.batches=self.open(self.top.path/"batches")
            self.run=self.open(self.batches.path/campaign._batch(number));self.claims=self.open(self.run.path/"claims");self.objects=self.open(self.run.path/"objects")
            self.lock=os.open("scope.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.run.fd)
            self.lockversion=base.custody._version(os.fstat(self.lock));fcntl.flock(self.lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
            _need(self.read(self.run,"scope.lock",1024)==LOCK_BYTES,"batch_readback_lock")
        except BaseException:self.close();raise
    def open(self,path):
        held=archive._Output(path);self.folders.append((held,base.custody._version(os.fstat(held.fd)),set(os.listdir(held.fd))));return held
    def read(self,folder,name,cap=campaign.MAX_CONTROL):
        version=base.custody._version(os.stat(name,dir_fd=folder.fd,follow_symlinks=False));raw=folder.read(name,cap)
        _need(base.custody._version(os.stat(name,dir_fd=folder.fd,follow_symlinks=False))==version,"batch_old_first_read_changed")
        self.pins.append((folder,name,version));return raw
    def recheck(self):
        for folder,version,names in self.folders:
            folder.check();_need(base.custody._version(os.fstat(folder.fd))==version and set(os.listdir(folder.fd))==names,"batch_old_directory_changed")
        _need(all(base.custody._version(os.stat(n,dir_fd=f.fd,follow_symlinks=False))==v for f,n,v in self.pins),"batch_old_leaf_changed")
        _need(base.custody._version(os.fstat(self.lock))==self.lockversion==base.custody._version(os.stat("scope.lock",dir_fd=self.run.fd,follow_symlinks=False)),"batch_old_lock_changed")
    def close(self):
        base.selector._close_all((archive.SimpleCloseFD(self.lock),*(r[0] for r in reversed(self.folders))),phase="batch_snapshot_close")
        self.folders=[];self.lock=None


def _validate_terminal(value,row,ordinal,start_sha):
    keys={"schema","ordinal","attempt","request_sha256","start_sha256","raw_transport_invocations","remote_request_count_measured","http_status",
        "failure_stage","failure_code","body_retained","body_sha256","body_bytes","headers_sha256","header_bound","finished_utc","finished_monotonic_ns"}
    _need(type(value) is dict and set(value)==keys and value["schema"]==SCHEMA+"/result" and type(value["ordinal"]) is int
        and value["ordinal"]==ordinal and type(value["attempt"]) is int and value["attempt"]==1 and value["request_sha256"]==row["request_sha256"]
        and value["start_sha256"]==start_sha and type(value["raw_transport_invocations"]) is int and value["raw_transport_invocations"] in {0,1}
        and value["remote_request_count_measured"] is False and type(value["body_retained"]) is type(value["header_bound"]) is bool
        and type(value["finished_monotonic_ns"]) is int and value["finished_monotonic_ns"]>=0
        and value["failure_stage"] in STAGES and value["failure_code"] in CODES,"batch_result_schema")
    _need(value["http_status"] is None or type(value["http_status"]) is int and 100<=value["http_status"]<=599,"batch_result_status")
    _stamp(lambda:value["finished_utc"])
    if value["body_retained"]:
        _need(value["http_status"]==200 and value["raw_transport_invocations"]==1 and type(value["body_bytes"]) is int and 0<value["body_bytes"]<=MAX_PARENT_BYTES,"batch_retained_result")
        for key in ("body_sha256","headers_sha256"):campaign._digest(value[key])
        _need((value["failure_stage"],value["failure_code"])==(("complete","none") if value["header_bound"] else ("header_identity","header_identity_unbound")),"batch_result_header_status")
    else:
        _need(value["header_bound"] is False and all(value[k] is None for k in ("body_sha256","body_bytes","headers_sha256")),"batch_unretained_result_measurements")
        pair=(value["failure_stage"],value["failure_code"])
        if value["http_status"] is None:allowed={("transport","transport_ambiguous"),("transport","transport_deadline")}
        elif value["http_status"]!=200:allowed={("HTTP_framing","HTTP_non200")}
        else:allowed={("HTTP_framing","HTTP_framing_refused"),("header_privacy","finite_privacy_refused"),("body_privacy","finite_privacy_refused"),
            ("native_inspection","native_inspection_refused"),("native_inspection","native_inspection_deadline")}
        _need(pair in allowed and (value["http_status"] is None or value["raw_transport_invocations"]==1),"batch_unretained_failure_stage")
    return value


def _verify(root,number,*,expected_complete_sha256,expected_plan_sha256,expected_index_sha256,fixture,hash_bodies=True):
    if fixture:first._fixture_root(root);first._native_fixture_denial()
    else:_need(root==LANE_ROOT,"batch_readback_fixed_root");campaign._isolated()
    for pin in (expected_complete_sha256,expected_plan_sha256,expected_index_sha256):campaign._digest(pin)
    snap=None
    try:
        snap=_Snapshot(root,number)
        complete_raw=snap.read(snap.run,"complete.json");plan_raw=snap.read(snap.run,"plan.json");index_raw=snap.read(snap.run,"consumed-index.json")
        _need((_sha(complete_raw),_sha(plan_raw),_sha(index_raw))==(expected_complete_sha256,expected_plan_sha256,expected_index_sha256),"batch_external_readback_pins")
        complete,plan,index=map(_decode,(complete_raw,plan_raw,index_raw));campaign.validate_batch_plan(plan)
        _need(complete["schema"]==SCHEMA+"/complete" and complete["fixture_only"] is fixture and plan["fixture_only"] is fixture
            and type(complete["batch_number"]) is int and complete["batch_number"]==plan["batch_number"]==number,"batch_readback_schema")
        if not fixture:first._source_identity(complete["execution_identity"],required_paths=(SELF_PATH,TEST_PATH,campaign.SELF_PATH,campaign.TEST_PATH))
        reservation_raw=snap.read(snap.run,"reservation.json");reservation=_decode(reservation_raw)
        _need(_raw(reservation)==_raw({"schema":SCHEMA+"/reservation","batch_number":number,"fixture_only":fixture,"execution_identity":complete["execution_identity"],
            "planner_receipt":complete["planner_receipt"],"plan_sha256":expected_plan_sha256,"planned_requests":len(plan["requests"]),"policy":campaign.POLICY,"authority":AUTHORITY}),"batch_reservation_crosslinks")
        rsha=_sha(reservation_raw)
        contact=_decode(snap.read(snap.run,"contact-validated.json"))
        _need(_raw(contact)==_raw({"schema":SCHEMA+"/contact","reservation_sha256":rsha,"contact_present":True,"contact_value_stored_or_hashed":False}),"batch_contact_receipt")
        origin=_decode(snap.read(snap.run,"rate-origin.json"))
        _need(set(origin)=={"schema","reservation_sha256","origin_monotonic_ns"} and origin["schema"]==SCHEMA+"/rate-origin" and origin["reservation_sha256"]==rsha
            and type(origin["origin_monotonic_ns"]) is int and origin["origin_monotonic_ns"]>=0,"batch_rate_origin")
        previous=origin["origin_monotonic_ns"];consumed=set(plan["consumed_accessions"]);claims=set();objects=set();retained=bound=0
        names={"claims","objects","scope.lock","reservation.json","plan.json","contact-validated.json","rate-origin.json","consumed-index.json","complete.json"}
        results=complete["results"];_need(type(results) is list and 0<len(results)<=len(plan["requests"]),"batch_result_count")
        last=None
        for ordinal,entry in enumerate(results):
            row=plan["requests"][ordinal];request=row["request"];accession=request["accession_number"]
            cname=_sha(accession.encode())+".json";sname=f"request-{ordinal:04d}-start.json";tname=f"request-{ordinal:04d}-result.json"
            _need(type(entry) is dict and set(entry)=={"accession_number","claim_name","claim_sha256","start_name","start_sha256","result_name","result_sha256"}
                and (entry["accession_number"],entry["claim_name"],entry["start_name"],entry["result_name"])==(accession,cname,sname,tname) and accession not in consumed,"batch_result_descriptor")
            craw=snap.read(snap.claims,cname);sraw=snap.read(snap.run,sname);traw=snap.read(snap.run,tname)
            _need((_sha(craw),_sha(sraw),_sha(traw))==(entry["claim_sha256"],entry["start_sha256"],entry["result_sha256"]),"batch_journal_hash_links")
            claim,start,terminal=map(_decode,(craw,sraw,traw))
            _stamp(lambda:claim["claimed_at_utc"])
            _need(_raw(claim)==_raw({"schema":SCHEMA+"/claim","batch_number":number,"reservation_sha256":rsha,"request_sha256":row["request_sha256"],"request":request,"claimed_at_utc":claim["claimed_at_utc"]}),"batch_claim_request_link")
            _need(set(start)=={"schema","ordinal","attempt","claim_sha256","request_sha256","started_utc","started_monotonic_ns"}
                and start["schema"]==SCHEMA+"/start" and type(start["ordinal"]) is int and start["ordinal"]==ordinal
                and type(start["attempt"]) is int and start["attempt"]==1 and start["claim_sha256"]==entry["claim_sha256"]
                and start["request_sha256"]==row["request_sha256"] and type(start["started_monotonic_ns"]) is int
                and start["started_monotonic_ns"]-previous>=SPACING_NS,"batch_durable_start_rate")
            _stamp(lambda:start["started_utc"]);_validate_terminal(terminal,row,ordinal,entry["start_sha256"])
            _need(terminal["finished_monotonic_ns"]>=start["started_monotonic_ns"],"batch_finish_order")
            previous=terminal["finished_monotonic_ns"];consumed.add(accession);claims.add(cname);names|={sname,tname}
            if terminal["body_retained"]:
                oname=terminal["body_sha256"]+".bin";objects.add(oname);hname=f"request-{ordinal:04d}-headers.json";names.add(hname)
                headers=_decode(snap.read(snap.run,hname));_need(set(headers)=={"headers"} and type(headers["headers"]) is list,"batch_header_inventory")
                pairs=tuple(tuple(pair) for pair in headers["headers"])
                _need(_sha(_raw(pairs))==terminal["headers_sha256"],"batch_headers_hash")
                if hash_bodies:
                    raw=snap.read(snap.objects,oname,MAX_PARENT_BYTES)
                    _need(len(raw)==terminal["body_bytes"] and _sha(raw)==terminal["body_sha256"],"batch_retained_body_hash")
                    first._strict_selected_response(first.SecHttpResult(200,pairs,raw),max_bytes=MAX_PARENT_BYTES)
                    try:first.old._envelope_and_header(raw,request)
                    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):observed_bound=False
                    else:observed_bound=True
                    _need(observed_bound is terminal["header_bound"],"batch_readback_header_identity")
                retained+=1;bound+=int(terminal["header_bound"])
            _need(terminal["header_bound"] or ordinal==len(results)-1,"batch_continued_after_fatal_refusal");last=terminal
        # Claude review section 330: as the first64 verifier does, a short result
        # list must end in its stopping refusal, not a header-bound prefix.
        _need(len(results)==len(plan["requests"]) or not last["header_bound"],"batch_readback_unexplained_early_stop")
        expected_index={"schema":campaign.SCHEMA+"/consumed-index","generation":number,"accessions":sorted(consumed),"plan_sha256":expected_plan_sha256,
            "predecessor_index_sha256":plan["predecessor"]["index_sha256"] if plan["predecessor"] else None,"base_consumption":plan["base_consumption"],
            "archive_exposures":list(campaign.ARCHIVE_EXPOSURES),"archive_membership_known":False,"authority":AUTHORITY}
        _need(_raw(index)==_raw(expected_index),"batch_consumed_index_conservation")
        expected_complete={"schema":SCHEMA+"/complete","batch_number":number,"fixture_only":fixture,"execution_identity":complete["execution_identity"],
            "planner_receipt":complete["planner_receipt"],"reservation_sha256":rsha,"plan_sha256":expected_plan_sha256,"index_sha256":expected_index_sha256,
            "planned_requests":len(plan["requests"]),"started_requests":len(results),"retained_bodies":retained,"header_bound_bodies":bound,
            "planned_unclaimed_unattempted":len(plan["requests"])-len(results),"capture_completed_without_refusal":len(results)==retained==bound==len(plan["requests"]),
            "last_finished_utc":last["finished_utc"],"first64_predecessor_complete_sha256":plan["predecessor"]["first64_success_sha256"] if plan["predecessor"] else None,
            "results":results,"authority":AUTHORITY}
        _need(_raw(complete)==_raw(expected_complete) and set(os.listdir(snap.run.fd))==names and set(os.listdir(snap.claims.fd))==claims
            and set(os.listdir(snap.objects.fd))==objects,"batch_complete_counts_inventory")
        snap.recheck()
        return {"schema":SCHEMA+"/readback","batch_number":number,"complete_sha256":expected_complete_sha256,"plan_sha256":expected_plan_sha256,
            "index_sha256":expected_index_sha256,"complete":complete,"index":index,"plan":plan,
            "body_bytes_rehashed_here":hash_bodies,"private_contact_screen_not_replayed_without_contact":True,"authority":dict(AUTHORITY)}
    finally:
        if snap:snap.close()


def verify_invented_batch(root,number,*,expected_complete_sha256,expected_plan_sha256,expected_index_sha256):
    return _verify(Path(root),number,expected_complete_sha256=expected_complete_sha256,expected_plan_sha256=expected_plan_sha256,
        expected_index_sha256=expected_index_sha256,fixture=True)


def _bind_planner_receipt(receipt,number,expected_plan_sha256,*,root=LANE_ROOT,fixture=False):
    """Section 342 (Claude review): the copied planner receipt must equal the
    planner's own held namespace and name the batch's external plan pin."""
    _need(type(receipt) is dict and set(receipt)=={"plan_sha256","complete_sha256","execution_identity"}
        and receipt["plan_sha256"]==expected_plan_sha256 and type(receipt["execution_identity"]) is dict,"batch_planner_receipt_binding")
    held=campaign.HeldBatchPlan(root,number,expected_plan_sha256=receipt["plan_sha256"],expected_complete_sha256=receipt["complete_sha256"],
        expected_producer_head=receipt["execution_identity"].get("head"),fixture=fixture)
    try:_need(_raw(held.receipt)==_raw(receipt),"batch_planner_receipt_binding")
    finally:held.close()


def _readback_actual(identity,**arguments):
    campaign._isolated();campaign._current(identity)
    number=arguments.pop("number")
    value=_verify(LANE_ROOT,number,fixture=False,**arguments)
    _bind_planner_receipt(value["complete"]["planner_receipt"],number,arguments["expected_plan_sha256"])
    campaign._current(identity);return value


def verify_actual_batch(expected_head,number,*,expected_complete_sha256,expected_plan_sha256,expected_index_sha256):
    identity=campaign._identity(expected_head)
    args={"number":number,"expected_complete_sha256":expected_complete_sha256,"expected_plan_sha256":expected_plan_sha256,"expected_index_sha256":expected_index_sha256}
    value=campaign._run_child(_command(identity,"readback",args),timeout=900)
    _need(value["complete_sha256"]==expected_complete_sha256 and value["plan_sha256"]==expected_plan_sha256 and value["index_sha256"]==expected_index_sha256,"batch_native_readback_external_pins")
    producer=value["complete"]["execution_identity"]
    first._source_identity(producer,required_paths=(SELF_PATH,TEST_PATH,campaign.SELF_PATH,campaign.TEST_PATH))
    for name,digest in producer["source_sha256"].items():
        _need(_sha(base.custody._git(LANE_ROOT,"show",producer["head"]+":"+name))==digest,"batch_original_capture_Git_proof")
    campaign.verify_plan_producer(value["complete"]["planner_receipt"])
    _need(campaign._identity(expected_head)==identity,"batch_readback_parent_source_changed")
    return {"schema":SCHEMA+"/readback-public","batch_number":number,"complete_sha256":expected_complete_sha256,"plan_sha256":expected_plan_sha256,
        "index_sha256":expected_index_sha256,"capture_completed_without_refusal":value["complete"]["capture_completed_without_refusal"],
        "started_requests":value["complete"]["started_requests"],"retained_bodies":value["complete"]["retained_bodies"],
        "body_bytes_rehashed_here":True,"private_contact_screen_not_replayed_without_contact":True,"authority":dict(AUTHORITY)}


def _validate_predecessor_link(higher,lower):
    """Cross-generation semantics, in addition to each root's external pins."""
    generation=lower["batch_number"];complete=lower["complete"]
    first64=lower["complete_sha256"] if generation==1 else complete["first64_predecessor_complete_sha256"]
    expected={"batch_number":generation,"complete_sha256":lower["complete_sha256"],"plan_sha256":lower["plan_sha256"],"index_sha256":lower["index_sha256"],
        "capture_execution_identity":complete["execution_identity"],"first64_success_sha256":first64,
        "last_finished_utc":complete["last_finished_utc"],"capture_completed_without_refusal":True}
    _need(higher["batch_number"]==generation+1 and higher["plan"]["batch_number"]==generation+1
        and _raw(higher["plan"]["predecessor"])==_raw(expected)
        and _raw(higher["plan"]["consumed_accessions"])==_raw(lower["index"]["accessions"])
        and higher["index"]["predecessor_index_sha256"]==lower["index_sha256"],"batch_exact_predecessor_semantics")


def read_actual_predecessor(number,*,expected_complete_sha256,expected_plan_sha256,expected_index_sha256,execution_identity):
    """Externally anchored complete chain/index, metadata only, no body replay."""
    campaign._isolated();campaign._current(execution_identity);campaign._batch(number)
    pins={"expected_complete_sha256":expected_complete_sha256,"expected_plan_sha256":expected_plan_sha256,"expected_index_sha256":expected_index_sha256}
    latest=None;following=None;first64=None;originalbase=None;originalsource=None;higher=None
    for generation in range(number,0,-1):
        value=_verify(LANE_ROOT,generation,fixture=False,hash_bodies=False,**pins)
        complete,plan,index=value["complete"],value["plan"],value["index"]
        if higher is not None:_validate_predecessor_link(higher,value)
        _need(complete["capture_completed_without_refusal"] is True,"batch_fatal_predecessor_requires_disposition")
        if latest is None:
            latest=value;following=index["accessions"];originalbase=plan["base_consumption"]
            originalsource=(plan["source_roster_sha256"],plan["parent_audit_sha256"])
        _need(plan["base_consumption"]==originalbase and (plan["source_roster_sha256"],plan["parent_audit_sha256"])==originalsource,"batch_predecessor_population_changed")
        if generation==1:
            _need(plan["limit"]==campaign.FIRST_LIMIT and complete["started_requests"]==campaign.FIRST_LIMIT,"batch_first64_success_required")
            first64=value["complete_sha256"]
        else:
            previous=plan["predecessor"]
            _need(type(previous) is dict and previous["batch_number"]==generation-1 and previous["capture_completed_without_refusal"] is True,"batch_predecessor_generation")
            pins={"expected_complete_sha256":previous["complete_sha256"],"expected_plan_sha256":previous["plan_sha256"],"expected_index_sha256":previous["index_sha256"]}
        higher=value
    _need(number==1 or latest["complete"]["first64_predecessor_complete_sha256"]==first64,"batch_first64_chain_anchor")
    complete=latest["complete"]
    proof={"batch_number":number,"complete_sha256":expected_complete_sha256,"plan_sha256":expected_plan_sha256,"index_sha256":expected_index_sha256,
        "capture_execution_identity":complete["execution_identity"],"first64_success_sha256":first64,
        "last_finished_utc":complete["last_finished_utc"],"capture_completed_without_refusal":True}
    campaign._current(execution_identity);return proof,following


class _Parser(argparse.ArgumentParser):
    def error(self,message):raise BatchCaptureError("batch_private_CLI_arguments")


def main(argv=None):
    saved=None
    try:
        saved=first.old._protect_stdin_echo()
        try:
            parser=_Parser(description=__doc__);parser.add_argument("--expected-head",required=True);parser.add_argument("--batch",type=int,required=True)
            parser.add_argument("--plan-sha",required=True);parser.add_argument("--plan-complete-sha");parser.add_argument("--plan-head")
            parser.add_argument("--verify-complete");parser.add_argument("--verify-index")
            args=parser.parse_args(argv)
            if args.verify_complete:
                result=verify_actual_batch(args.expected_head,args.batch,expected_complete_sha256=args.verify_complete,expected_plan_sha256=args.plan_sha,expected_index_sha256=args.verify_index)
            else:
                result=run_actual_batch(args.expected_head,batch_number=args.batch,expected_plan_sha256=args.plan_sha,
                    expected_complete_sha256=args.plan_complete_sha,expected_producer_head=args.plan_head)
        finally:first.old._restore_stdin_echo(saved)
    except campaign.NativeWorkerRefused as error:
        print(_raw({"disposition":"batch_capture_refused","failure_stage":error.phase,"failure_code":error.code}).decode());return 2
    except Exception:print('{"disposition":"batch_capture_refused"}');return 2
    print(_raw(result).decode());return 0 if result["capture_completed_without_refusal"] else 2


if __name__=="__main__":raise SystemExit(main())
