"""Read-only retained SEC exposure and original-body candidates for the pilot.

Operational journals establish consumed requests, not canonical source admission.
Original text bodies may be stream-hashed but are NEVER parsed here. Auxiliary
XML/header/index/master records do not count as original complete submissions.
The old bootstrap and all stopped namespaces remain unchanged.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
import errno
import hashlib
import json
import os
import re
import stat
import sys
import uuid

from research import insider_buying_sec_2006q1_parent_bootstrap as bootstrap

SCHEMA = "insider-pilot-sec-retained-exposure-v1"
CANDIDATE_SCHEMA = SCHEMA+"/candidates"
MAX_INVENTORY_BYTES = 128*1024*1024
MAX_CANDIDATES = 100000
MAX_ORIGINAL_BYTES = 8*1024*1024
MAX_MASTER_BYTES = 64*1024*1024
MAX_STREAM_BYTES = 4*1024**3
_TARGET_KEYS = ("accession_number","period","filing_date","form_type","issuer_cik")
_REQUEST_KEYS = frozenset((*_TARGET_KEYS,"url","archive_path","master_source_sha256","parsed_lineage_hash",
    "submission_row_id","filing_date_raw","quarterly_zip_sha256","raw_lineage_sha256","raw_snapshot_id",
    "source_record_ordinal","accession_key_sha256","filing_metadata_sha256","submission_inventory_sha256",
    "submission_member_sha256","master_decoded_sha256","master_receipt_sha256"))
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_OBJECT = re.compile(r"(?:(?:runs/[a-z][a-z0-9-]{0,100}|shard-[0-9]{4})/)?objects/([0-9a-f]{64})\.bin\Z")
_CANDIDATE_KEYS = frozenset(("root_id","control_name","control_sha256","request_sha256","request","request_url",
    "retained_target","raw_object","body_currently_hash_verified","complete_parent_parsed_here"))
_MASTER_KEYS = frozenset(("root_id","control_name","control_sha256","period","source_url","raw_object",
    "producer_receipt","body_currently_hash_verified","master_decoded_here"))


class PilotSecExposureError(ValueError):
    """Fixed codes only: no retained response, contact, path or exception text."""


def _need(condition,code):
    if not condition:raise PilotSecExposureError(code)


def _raw(value):return bootstrap._canonical(value)
def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _digest(value):_need(type(value) is str and _SHA.fullmatch(value),"digest_refused");return value
def _json(raw):
    _need(type(raw) is bytes and 0<len(raw)<=MAX_INVENTORY_BYTES,"metadata_bytes_refused")
    return bootstrap._json(raw,newline=False)


def authority():
    return {"source_authenticated":False,"official_acceptance_verified":False,"publication_time_verified":False,
        "point_in_time_data":False,"rights_verified":False,"canonical_evidence":False,"complete_corpus":False,
        "direct_ib1c_ingest_authorized":False,"dispatch_enabled":False,"qc_authorized":False,"backtest_authorized":False,
        "execution_authorized":False,"sec_dispatches":0,"outcome_looks":0,"qc_jobs":0,"backtests":0}


def actual_roots():
    specs = list(bootstrap.actual_roots())
    path = bootstrap.custody.LANE_ROOT/"artifacts/insider_buying/sec_2006q1_parent_capture_v1"
    if all(spec.path != path for spec in specs):
        specs.append(bootstrap.RootSpec("sec-2006q1-global-claims",path,"global-claims"))
    _need(len({spec.root_id for spec in specs})==len(specs),"root_id_repeats")
    return tuple(specs)


def _native_read_only():
    bootstrap.custody._effective_denial(require_fork=True)
    try:os.execve("/usr/bin/security",["security","help"],{"PATH":"/usr/bin:/bin:/usr/sbin:/sbin"})
    except OSError as exc:_need(exc.errno in {errno.EPERM,errno.EACCES},"credential_exec_denial_required")
    else:raise PilotSecExposureError("credential_exec_denial_required")
    probe = "/private/tmp/insider-pilot-sec-readonly-"+uuid.uuid4().hex
    try:fd=os.open(probe,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except OSError as exc:_need(exc.errno in {errno.EPERM,errno.EACCES},"all_write_denial_required")
    else:os.close(fd);raise PilotSecExposureError("all_write_denial_required")


class ExposureHold:
    """Add opaque streaming-body pins without mutating the historical helper."""
    def __init__(self,tree):
        self.tree,self.spec,self.body_pins,self.streamed = tree,tree.spec,{},0
        self.candidate_inventory_sha256 = None

    def hash_body(self,relative,digest,size,*,master=False):
        _need(type(relative) is str and _OBJECT.fullmatch(relative) and _OBJECT.fullmatch(relative).group(1)==_digest(digest),
              "body_object_path_hash_refused")
        limit = MAX_MASTER_BYTES if master else MAX_ORIGINAL_BYTES
        _need(type(size) is int and 0<size<=limit,"body_size_refused")
        parts=tuple(Path(relative).parts);chain=self.tree.open(parts[:-1]);chain.recheck()
        before=os.stat(parts[-1],dir_fd=chain.fd,follow_symlinks=False)
        _need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==os.geteuid()
              and stat.S_IMODE(before.st_mode)==0o600 and before.st_size==size,"body_custody_refused")
        fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=chain.fd)
        try:
            _need(bootstrap.custody._version(os.fstat(fd))==bootstrap.custody._version(before),"body_substituted")
            value,count=hashlib.sha256(),0
            while chunk:=os.read(fd,65536):
                count+=len(chunk);self.streamed+=len(chunk)
                _need(count<=size and self.streamed<=MAX_STREAM_BYTES,"body_stream_bound_refused")
                value.update(chunk)
            version=bootstrap.custody._version(before)
            _need(count==size and value.hexdigest()==digest and version==bootstrap.custody._version(os.fstat(fd))
                  ==bootstrap.custody._version(os.stat(parts[-1],dir_fd=chain.fd,follow_symlinks=False)),"body_hash_or_version_changed")
        finally:os.close(fd)
        pin=(digest,size,master,version)
        _need(relative not in self.body_pins or self.body_pins[relative]==pin,"held_body_changed")
        self.body_pins[relative]=pin

    def recheck(self):
        self.tree.recheck()
        for relative,(digest,size,master,version) in tuple(self.body_pins.items()):
            parts=tuple(Path(relative).parts);chain=self.tree.open(parts[:-1])
            _need(bootstrap.custody._version(os.stat(parts[-1],dir_fd=chain.fd,follow_symlinks=False))==version,"held_body_version_changed")
            self.hash_body(relative,digest,size,master=master)

    def close(self):
        # bootstrap._Tree.close stops at its first exception; drain all handles
        # in the additive wrapper and preserve an already active primary.
        primary,failed=sys.exc_info()[0] is not None,False
        for _,_,fd,_ in self.tree.locks:
            try:os.close(fd)
            except BaseException:failed=True
        for chain,_ in reversed(tuple(self.tree.directories.values())):
            try:chain.close()
            except BaseException:failed=True
        self.tree.locks,self.tree.directories=[],{}
        if failed and not primary:raise PilotSecExposureError("source_cleanup_refused") from None


def close_holds(holds):
    primary,failed=sys.exc_info()[0] is not None,False
    for hold in reversed(holds):
        try:hold.close()
        except BaseException:failed=True
    if failed and not primary:raise PilotSecExposureError("source_cleanup_refused") from None


def _requests(controls):
    by_accession,by_hash=defaultdict(list),defaultdict(list)
    for name,raw in controls.items():
        if Path(name).name not in {"inventory.json","campaign-plan.json","plan.json","reservation.json"}:continue
        body=bootstrap._json(raw)
        if Path(name).name=="reservation.json":items=body.get("selection",{}).get("requests",[])
        else:items=body.get("requests",body.get("rows",body.get("candidates",[])))
        _need(type(items) is list,"request_inventory_refused")
        for item in items:
            _need(type(item) is dict,"request_refused")
            request=item.get("request",item);accession=request.get("accession_number")
            if accession is None:continue
            _need(type(accession) is str and _ACCESSION.fullmatch(accession),"request_accession_refused")
            if "url" in request:_need(bootstrap._accession_url(request["url"])==accession,"request_url_accession_differs")
            digest=_sha(_raw(request))
            if "request_sha256" in item:_need(item["request_sha256"]==digest,"request_hash_differs")
            if request not in by_accession[accession]:by_accession[accession].append(request)
            if request not in by_hash[digest]:by_hash[digest].append(request)
    return by_accession,by_hash


def _target(request):
    _need(type(request) is dict and all(type(request.get(key)) is str for key in _TARGET_KEYS),"complete_target_metadata_required")
    _need(set(request)<=_REQUEST_KEYS and len(_raw(request))<=16384
          and all(type(value) is str or key=="source_record_ordinal" and type(value) is int and value>=1
                  for key,value in request.items()),"private_or_unknown_request_field_refused")
    result={key:request[key] for key in _TARGET_KEYS}
    _need(_ACCESSION.fullmatch(result["accession_number"]) and re.fullmatch(r"20[0-9]{2}Q[1-4]",result["period"])
          and result["form_type"] in {"3","3/A","4","4/A","5","5/A"}
          and re.fullmatch(r"[0-9]{1,10}",result["issuer_cik"]) and int(result["issuer_cik"])>0
          and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",result["filing_date"]),"complete_target_metadata_refused")
    try:day=date.fromisoformat(result["filing_date"])
    except ValueError:raise PilotSecExposureError("complete_target_date_refused") from None
    _need(f"{day.year}Q{(day.month-1)//3+1}"==result["period"],"complete_target_period_differs")
    return result


def _object(value,*,prefix=""):
    _need(type(value) is dict and set(value)=={"relative_path","sha256","size_bytes"},"raw_descriptor_refused")
    result={**value,"relative_path":prefix+value["relative_path"]}
    _need(type(result["relative_path"]) is str and _OBJECT.fullmatch(result["relative_path"])
          and _OBJECT.fullmatch(result["relative_path"]).group(1)==_digest(result["sha256"])
          and type(result["size_bytes"]) is int and 0<result["size_bytes"]<=MAX_MASTER_BYTES,"raw_descriptor_refused")
    return result


def _candidate(root_id,control_name,control_sha,request,url,raw_object):
    target=_target(request)
    _need(bootstrap._PARENT_URL.fullmatch(url) and bootstrap._accession_url(url)==target["accession_number"],"original_parent_locator_required")
    if "url" in request:_need(request["url"]==url,"candidate_request_url_differs")
    value={"root_id":root_id,"control_name":control_name,"control_sha256":_digest(control_sha),
        "request_sha256":_sha(_raw(request)),"request":request,"request_url":url,"retained_target":target,
        "raw_object":_object(raw_object),"body_currently_hash_verified":False,"complete_parent_parsed_here":False}
    _need(value["raw_object"]["size_bytes"]<=MAX_ORIGINAL_BYTES,"original_body_bound_refused")
    return value


def _events(spec,controls,tree):
    if spec.profile=="simple-jsonl":
        raw=controls["attempts.jsonl"]
        return [(f"attempts.jsonl:line-{index:06d}",bootstrap._json(line+b"\n"),_sha(raw))
                for index,line in enumerate(raw.splitlines(),1)]
    if spec.profile=="event-chain":return bootstrap._event_chain(controls)
    if spec.profile=="sharded-events":
        return [item for part in sorted(name for name in tree.names() if re.fullmatch(r"shard-[0-9]{4}",name))
                for item in bootstrap._event_chain(controls,part)]
    return []


def _same_request(choices,accession,url):
    rows=[request for request in choices[accession] if request.get("url",url)==url]
    _need(rows,"candidate_request_missing")
    targets={_raw(_target(request)) for request in rows}
    _need(len(targets)==1,"candidate_request_target_conflicts")
    # Preserve the most complete retained producer request, never synthesize a
    # locator from the issuer. Different schema hashes remain in its lineage.
    return max(rows,key=lambda request:(len(request),_sha(_raw(request))))


def _collect_one(hold,controls,requests,global_hashes):
    spec=hold.spec;found=[];dispatch=[];masters=[]
    events=_events(spec,controls,hold.tree)
    active,valid,inventory_cache={},{},{}
    for name,event,digest in events:
        kind=event.get("kind");group=str(Path(name).parent)
        if kind in {"attempt-start","attempt-reserved"}:
            url=event.get("url",event.get("path"));accession=bootstrap._accession_url(url)
            active[(group,event["ordinal"])]=(accession,url,name,digest)
            if accession is not None:dispatch.append({"accession_number":accession,"root_id":spec.root_id,
                "control_name":name,"control_sha256":digest,"url":url,"state":"reserved" if kind=="attempt-reserved" else "started",
                "outcome":None})
        elif kind in {"attempt-finish","attempt-response","attempt-refused","attempt-network-error","attempt-framing-refusal","attempt-abandoned"}:
            key=(group,event["ordinal"]);_need(key in active,"terminal_without_start")
            accession,url,_,_=active.pop(key);outcome=event.get("outcome",kind)
            if accession is not None:
                state="response_observed" if outcome in {"valid_response","http_status"} and event.get("status")==200 else "consumed_refusal"
                dispatch.append({"accession_number":accession,"root_id":spec.root_id,"control_name":name,
                    "control_sha256":digest,"url":url,"state":state,"outcome":outcome})
                if outcome in {"valid_response","http_status"} and event.get("status")==200:
                    valid[(group,accession)]=(event.get("body_sha256"),event.get("body_size_bytes"),url)
        elif kind=="item-complete":
            accession=event["accession_number"]
            _need(event.get("source") in {"reused","acquired","new_acquired"},"item_source_refused")
            parent=str(Path(name).parent);prefix="" if parent=="." else parent+"/"
            if prefix not in inventory_cache:
                inventory=bootstrap._json(controls[prefix+"inventory.json"])
                request_rows=inventory.get("requests",inventory.get("rows",[]))
                request_map={item.get("request",item)["accession_number"]:item.get("request",item) for item in request_rows}
                reuse_rows=inventory.get("reuses",[]);reuse_map={row["accession_number"]:row for row in reuse_rows}
                _need(len(request_map)==len(request_rows) and len(reuse_map)==len(reuse_rows),"ordered_request_identity_repeats")
                inventory_cache[prefix]=(request_map,reuse_map)
            request_map,reuse_map=inventory_cache[prefix]
            _need(accession in request_map,"completed_request_identity_missing")
            request=request_map[accession];url=request["url"]
            if event["source"]=="reused":
                _need(accession in reuse_map and all(reuse_map[accession].get(key)==event.get(key) for key in
                    ("object_sha256","object_size_bytes","prior_report_sha256")),"reused_descriptor_binding_differs")
            else:
                _need(valid.pop((group,accession),None)==(event["object_sha256"],event["object_size_bytes"],url),
                      "completed_response_binding_differs")
            found.append(_candidate(spec.root_id,name,digest,request,url,
                {"relative_path":prefix+"objects/"+event["object_sha256"]+".bin","sha256":event["object_sha256"],"size_bytes":event["object_size_bytes"]}))
    # A later separate diagnostic never pops this original stream's active start.
    for accession,url,name,digest in active.values():
        if accession is not None:dispatch.append({"accession_number":accession,"root_id":spec.root_id,"control_name":name,
            "control_sha256":digest,"url":url,"state":"ambiguous","outcome":None})
    if spec.profile=="simple-jsonl":
        if "commit.json" not in controls:return found,dispatch,masters
        commit=bootstrap._json(controls["commit.json"]);report_name=commit.get("report_name",commit.get("report"))
        report=bootstrap._json(controls[report_name]);report_sha=_sha(controls[report_name])
        for row in report.get("filings",[]):
            if row.get("status")!="acquired_noncanonical":continue
            request=row["candidate"];url=row["source_url"];accession=request["accession_number"]
            matches=[value for (group,acc),value in valid.items() if acc==accession and value[2]==url]
            descriptor=_object(row["raw_object"])
            _need((descriptor["sha256"],descriptor["size_bytes"],url) in matches,"complete_report_response_binding_differs")
            found.append(_candidate(spec.root_id,report_name,report_sha,request,url,descriptor))
    elif spec.profile=="global-claims":
        for claim_name in sorted(name for name in controls if name.startswith("claims/")):
            claim_raw=controls[claim_name];claim=bootstrap._json(claim_raw);row=claim["request"];request=row["request"]
            accession=request["accession_number"];capture_id=claim["capture_id"]
            reservation=bootstrap._json(controls[f"runs/{capture_id}/reservation.json"])
            _need(reservation.get("selection_sha256")==_sha(_raw(reservation["selection"])),"global_selection_hash_differs")
            ordinal=reservation["selection"]["requests"].index(row);prefix=f"runs/{capture_id}/request-{ordinal:03d}"
            result_raw=controls.get(prefix+"-result.json")
            if result_raw is None:continue
            result=bootstrap._json(result_raw);disposition=result.get("disposition")
            good=result.get("body_retained") is True and type(result.get("status")) is int and result["status"]==200
            url=request["url"]
            dispatch.append({"accession_number":accession,"root_id":spec.root_id,"control_name":prefix+"-result.json",
                "control_sha256":_sha(result_raw),"url":url,"state":"response_observed" if good else "consumed_refusal","outcome":disposition})
            if good:
                complete_name=f"runs/{capture_id}/complete.json";complete_raw=controls.get(complete_name)
                if complete_raw is None:
                    dispatch[-1]["state"]="response_unsealed"
                    continue  # Consumed forever, but not a sealed body candidate.
                complete=bootstrap._json(complete_raw);result_name=f"request-{ordinal:03d}-result.json"
                reservation_raw=controls[f"runs/{capture_id}/reservation.json"]
                _need(complete.get("reservation_sha256")==_sha(reservation_raw)
                      and complete.get("selection_sha256")==reservation["selection_sha256"]
                      and {"result_name":result_name,"result_sha256":_sha(result_raw)} in complete.get("results",[]),
                      "candidate_result_completion_binding_differs")
                found.append(_candidate(spec.root_id,prefix+"-result.json",_sha(result_raw),request,url,
                    {"relative_path":f"runs/{capture_id}/objects/{result['body_sha256']}.bin",
                     "sha256":result["body_sha256"],"size_bytes":result["body_size_bytes"]}))
    elif spec.profile=="diagnostic":
        manifest=bootstrap._json(controls["manifest.json"])
        digest=manifest.get("refused_request_sha256",manifest.get("ambiguous_request_sha256"));choices=global_hashes[digest]
        _need(len(choices)==1,"diagnostic_request_missing")
        request=choices[0];url=request["url"];commit_raw=controls.get("commit.json")
        if commit_raw is not None:
            commit=bootstrap._json(commit_raw);report_name=commit["report_name"];report=bootstrap._json(controls[report_name])
            response_raw=controls.get("response.json");_need(response_raw is not None,"diagnostic_response_missing")
            response=bootstrap._json(response_raw)
            _need(report.get("body_sha256")==response.get("body_sha256") and report.get("body_size_bytes")==response.get("body_size_bytes")
                  and report.get("response_headers_sha256")==response.get("headers_sha256"),"diagnostic_response_report_differs")
            good=type(response.get("status")) is int and response["status"]==200 and report.get("transport_outcome")=="returned"
            if good:found.append(_candidate(spec.root_id,report_name,_sha(controls[report_name]),request,url,
                {"relative_path":"objects/"+response["body_sha256"]+".bin","sha256":response["body_sha256"],"size_bytes":response["body_size_bytes"]}))
            dispatch.append({"accession_number":request["accession_number"],"root_id":spec.root_id,
                "control_name":report_name,"control_sha256":_sha(controls[report_name]),"url":url,
                "state":"response_observed" if good and report.get("envelope_outcome")=="accepted" else "consumed_refusal",
                "outcome":report.get("envelope_outcome")})
    if spec.root_id=="masters-v3":
        commit=bootstrap._json(controls["commit.json"]);report_name=commit["report_name"];report=bootstrap._json(controls[report_name])
        rows=report.get("master_indexes")
        _need(type(rows) is list and len(rows)==82 and report.get("complete_82_master_indexes_acquired") is True,
              "complete_master_inventory_required")
        completed_events={event["period"]:event for _,event,_ in events if event.get("kind")=="quarter-complete"}
        expected_periods=[f"{year}Q{quarter}" for year in range(2006,2027) for quarter in range(1,5) if (year,quarter)<=(2026,2)]
        _need(len(completed_events)==82 and [row["period"] for row in rows]==expected_periods,
              "complete_master_terminal_inventory_required")
        for row in rows:
            _need(row.get("status")=="acquired_noncanonical","master_not_completed")
            event=completed_events.get(row["period"]);descriptor=_object(row["raw_object"])
            _need(event is not None and event.get("object_sha256")==descriptor["sha256"]
                  and event.get("object_size_bytes")==descriptor["size_bytes"] and event.get("summary")==row["receipt"],
                  "master_completed_event_descriptor_differs")
            receipt=row["receipt"]
            _need(type(receipt) is dict and set(receipt)=={"decoded_sha256","decoded_size_bytes","parser_version",
                "master_receipt_sha256","all_filing_row_count","form4_or_4a_path_rows"}
                and type(receipt["decoded_size_bytes"]) is int and 0<receipt["decoded_size_bytes"]<=MAX_MASTER_BYTES
                and type(receipt["all_filing_row_count"]) is int and receipt["all_filing_row_count"]>0
                and type(receipt["form4_or_4a_path_rows"]) is int and 0<=receipt["form4_or_4a_path_rows"]<=receipt["all_filing_row_count"]
                and receipt["parser_version"]=="insider-buying-sec-quarter-master-idx-v1","master_receipt_schema_refused")
            _digest(receipt["decoded_sha256"]);_digest(receipt["master_receipt_sha256"])
            if "2020Q1"<=row["period"]<="2026Q1":
                masters.append({"root_id":spec.root_id,"control_name":report_name,"control_sha256":_sha(controls[report_name]),
                    "period":row["period"],"source_url":row["source_url"],"raw_object":_object(row["raw_object"]),
                    "producer_receipt":row["receipt"],"body_currently_hash_verified":False,"master_decoded_here":False})
        _need(len(masters)==25,"exact_25_context_masters_required")
    return found,dispatch,masters


def observe_exposures(roots,*,fixture_only):
    """Return held roots, OLD exposure bytes, snapshot bytes, candidates bytes.

    Parent must call close_holds() in a finally block. The actual runner must
    bind committed source identity independently; this function does no Git.
    """
    _need(type(fixture_only) is bool and type(roots) is tuple and roots,"typed_exposure_scope_required")
    if fixture_only:
        paths=[str(spec.path) for spec in roots];common=Path(os.path.commonpath(paths))
        bootstrap._fixture_roots_only(common,roots,roots[0].path)
        bootstrap.custody._effective_denial(require_fork=False)
    else:
        _need(roots==actual_roots(),"fixed_actual_root_inventory_required")
        _native_read_only()
    trees,exposure_raw,old_snapshot=bootstrap.bootstrap_exposures(roots)
    holds=[ExposureHold(tree) for tree in trees]
    try:
        controls={hold.spec.root_id:bootstrap._controls(hold.tree) for hold in holds}
        lookups={};global_hashes=defaultdict(list)
        for root_id,items in controls.items():
            by_accession,by_hash=_requests(items);lookups[root_id]=by_accession
            for digest,requests in by_hash.items():
                for request in requests:
                    if request not in global_hashes[digest]:global_hashes[digest].append(request)
        candidates,dispatch,masters=[],[],[]
        for hold in holds:
            found,seen,reference=_collect_one(hold,controls[hold.spec.root_id],lookups[hold.spec.root_id],global_hashes)
            candidates.extend(found);dispatch.extend(seen);masters.extend(reference)
        _need(len(candidates)<=MAX_CANDIDATES,"candidate_count_bound_refused")
        grouped=defaultdict(list)
        for candidate in candidates:grouped[candidate["retained_target"]["accession_number"]].append(candidate)
        records=[{"accession_number":accession,"candidates":sorted(rows,key=lambda v:(v["root_id"],v["control_name"],v["raw_object"]["sha256"]))}
                 for accession,rows in sorted(grouped.items())]
        inventory={"schema":CANDIDATE_SCHEMA,"fixture_only":fixture_only,"records":records,
                   "masters":sorted(masters,key=lambda v:v["period"]),"authority":authority()}
        candidate_raw=_raw(inventory);_need(len(candidate_raw)<=MAX_INVENTORY_BYTES,"candidate_bytes_bound_refused")
        for hold in holds:hold.candidate_inventory_sha256=_sha(candidate_raw)
        snapshot={"schema":SCHEMA+"/snapshot","fixture_only":fixture_only,"bootstrap_snapshot_sha256":_sha(old_snapshot),
            "bootstrap_snapshot":bootstrap._json(old_snapshot,newline=False),"exposure_sha256":_sha(exposure_raw),
            "candidates_sha256":_sha(candidate_raw),"dispatch_records":dispatch,"authority":authority(),
            "body_files_opened_here":False,"source_admission_claimed":False}
        snapshot_raw=_raw(snapshot);_need(len(snapshot_raw)<=MAX_INVENTORY_BYTES,"snapshot_bytes_bound_refused")
        for hold in holds:hold.recheck()
        return holds,exposure_raw,snapshot_raw,candidate_raw
    except BaseException:
        close_holds(holds);raise


def hash_candidate_bodies(holds,candidates_raw,*,include_masters=True):
    """Opaque byte recheck, not complete-parent/XML/financial interpretation."""
    _need(type(holds) is list and all(type(hold) is ExposureHold for hold in holds)
          and type(include_masters) is bool,"held_roots_required")
    _need(holds and all(hold.candidate_inventory_sha256==_sha(candidates_raw) for hold in holds),"exact_observed_candidate_inventory_required")
    inventory=_json(candidates_raw)
    _need(set(inventory)=={"schema","fixture_only","records","masters","authority"} and inventory["schema"]==CANDIDATE_SCHEMA
          and type(inventory["fixture_only"]) is bool and inventory["authority"]==authority(),"candidate_schema_refused")
    by_root={hold.spec.root_id:hold for hold in holds};seen=set()
    for record in inventory["records"]:
        _need(type(record) is dict and set(record)=={"accession_number","candidates"} and _ACCESSION.fullmatch(record["accession_number"])
              and record["accession_number"] not in seen and type(record["candidates"]) is list and record["candidates"],"candidate_record_refused")
        seen.add(record["accession_number"])
        for row in record["candidates"]:
            _need(type(row) is dict and set(row)==_CANDIDATE_KEYS and row["root_id"] in by_root
                  and row["retained_target"]==_target(row["request"]) and row["retained_target"]["accession_number"]==record["accession_number"]
                  and row["request_sha256"]==_sha(_raw(row["request"])) and row["complete_parent_parsed_here"] is False
                  and type(row["body_currently_hash_verified"]) is bool,"candidate_request_binding_refused")
            _candidate(row["root_id"],row["control_name"],row["control_sha256"],row["request"],row["request_url"],row["raw_object"])
            hold=by_root[row["root_id"]];control=hold.tree.leaves.get(row["control_name"])
            _need(control is not None and control[2]==row["control_sha256"],"candidate_control_not_held")
            raw=_object(row["raw_object"]);hold.hash_body(raw["relative_path"],raw["sha256"],raw["size_bytes"])
            row["body_currently_hash_verified"]=True
    _need(type(inventory["masters"]) is list,"master_inventory_refused")
    for row in inventory["masters"]:
        _need(type(row) is dict and set(row)==_MASTER_KEYS and row["root_id"] in by_root
              and row["master_decoded_here"] is False and type(row["body_currently_hash_verified"]) is bool,"master_descriptor_refused")
        if include_masters:
            hold=by_root[row["root_id"]];control=hold.tree.leaves.get(row["control_name"])
            _need(control is not None and control[2]==row["control_sha256"],"master_control_not_held")
            raw=_object(row["raw_object"]);hold.hash_body(raw["relative_path"],raw["sha256"],raw["size_bytes"],master=True)
            row["body_currently_hash_verified"]=True
    for hold in holds:hold.recheck()
    encoded=_raw(inventory);_need(len(encoded)<=MAX_INVENTORY_BYTES,"candidate_bytes_bound_refused")
    for hold in holds:hold.candidate_inventory_sha256=_sha(encoded)
    return encoded
