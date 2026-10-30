"""Protected, source-complete campaign batches; never an archive retry.

The immutable full-source accounting is rederived once per bounded batch, not
per request. A completed planner is not capture, canonical admission or a
backtest. Genuine production selection is available only through the initially
native-denied fixed-root worker. Existing first64 and stopped roots are inputs.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass,field
from datetime import date
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
import weakref

from research import insider_buying_pilot_sec_fresh_selection_runner as source
from research import insider_buying_pilot_sec_parent_capture as first
from research import insider_buying_sec_feed_archive_sample as archive

base,audit,roster,fresh=source.base,source.base.compiler,source.base.roster,source.selection
SCHEMA="insider-pilot-sec-parent-campaign-v2-launch2"
SELF_PATH="research/insider_buying_pilot_sec_parent_campaign_v2.py"
TEST_PATH="tests/test_insider_buying_pilot_sec_parent_campaign_v2.py"
CAPTURE_SOURCE_PATH="research/insider_buying_pilot_sec_parent_batch_capture_v2.py"
CAPTURE_TEST_PATH="tests/test_insider_buying_pilot_sec_parent_batch_capture_v2.py"
LANE_ROOT,LANE_BRANCH=base.LANE_ROOT,base.LANE_BRANCH
ARTIFACT_PARTS=("artifacts","insider_buying","pilot_sec_parent_campaign_v2_launch2")
CAPTURE_PARTS=("artifacts","insider_buying","pilot_sec_parent_batch_capture_v2")
FAILED_PARTS=("artifacts","insider_buying","pilot_sec_parent_campaign_v2")
FAILED_SCHEMA="insider-pilot-sec-parent-campaign-v2"
FAILED_HEAD="586d3ef38700f4a963488d70b29736e03f0b4a85"
FAILED_RESERVATION_SHA256="272ad69aacf9e4f3468138f0bceb32f1215102fe7df4b04d794f973367f1a6ac"
FAILED_RESERVATION_BYTES=16698
FAILED_INVENTORY_SHA256="cf67bf8fc534085003d8e2b89447ba4520c78e2e8561844960b3f252865dd438"
FIRST_LIMIT,MAX_LIMIT,MAX_BATCHES=64,1024,20000
MAX_CONTROL=128*1024*1024
MAX_CONSUMED=1500000
EMPTY_CACHE_PREFIX=base.EMPTY_CACHE_PREFIX
LOCK_BYTES=b"INSETF-pilot-parent-campaign-v2-launch2-one-controller\n"
FAILED_LOCK_BYTES=b"INSETF-pilot-parent-campaign-v2-one-controller\n"
_raw,_sha=audit._raw,audit._sha
_TOKEN=object();_SEALS=weakref.WeakKeyDictionary()
ARCHIVE_EXPOSURES=(
    {"url":archive.URL,"complete_sha256":"dad7ff80e46277409aaeaf92f000b3b0ca98e81b6c622caf22f84332c61b4242","http_status":200},
    {"url":"https://www.sec.gov/Archives/edgar/Feed/2021/QTR2/20210616.nc.tar.gz","complete_sha256":"8d12cf9a297899450b987c293acdcb479306a6f4512f859662ee34b8dd9e7693","http_status":200})
POLICY={"source_periods":list(audit.PERIODS),"pilot_periods":list(audit.PILOT_PERIODS),
    "order":"quarter_then_original_source_ordinal_not_returns","first_batch_requests":FIRST_LIMIT,
    "later_batch_maximum":MAX_LIMIT,"maximum_attempts_per_accession":1,
    "minimum_finish_to_next_start_ns":500000000,"maximum_parent_bytes":8*1024*1024,
    "transport_wall_seconds":30,"global_writer":"cooperative_lane_controller_EX_flock_held_through_capture_not_machinewide_rate_enforcement",
    "per_lane_request_ceiling_per_second":5,"SEC_user_aggregate_ceiling_per_second":10,"cross_machine_rate_enforcement_implemented":False,
    "completed_and_ambiguous_accessions_excluded":True,"old_scope_resumed":False,
    "archive_membership_unknown_is_not_zero_exposure_or_an_accession_claim":True,
    "new_archive_requests":0,"full_population_source_metadata_is_not_parent_completion":True}
AUTHORITY=dict(audit._AUTHORITY)
# Section 342 (Claude review): later one-shot capture namespaces whose consumed
# accessions this planner does not yet chain. While one exists, planning stops,
# so no successor batch can request one of its filings again.
UNCHAINED_LATER_CAPTURE_PARTS=(("artifacts","insider_buying","pilot_sec_required21_v1"),)


class CampaignError(ValueError):pass


class NativeWorkerRefused(CampaignError):
    def __init__(self,phase,code):
        self.phase,self.code=phase,code;super().__init__("campaign_native_worker_refused")


PHASES={"launcher_health","stopped_launch_custody","initial_isolation","source_identity","prior_custody","source_rederivation","final_input_recheck"}
FAILURE_CODES={"native_or_control_refused","prior_consumption_changed","source_population_changed","late_repeat_reconciliation_required"}


def _safe_failure(error):
    phase=getattr(error,"_campaign_phase","initial_isolation")
    if phase not in PHASES:phase="initial_isolation"
    codes={"campaign_old_exposure_changed":"prior_consumption_changed","campaign_original_full_audit_changed":"source_population_changed",
        "campaign_late_repeat_requires_reconciliation":"late_repeat_reconciliation_required",
        "campaign_unchained_later_capture_consumption":"prior_consumption_changed"}
    code=codes.get(str(error),"native_or_control_refused") if type(error) is CampaignError else "native_or_control_refused"
    return {"schema":SCHEMA+"/worker-refusal","phase":phase,"code":code}


def _need(value,code):
    if not value:raise CampaignError(code)


def _no_unchained_later_capture(root=LANE_ROOT):
    for parts in UNCHAINED_LATER_CAPTURE_PARTS:
        _need(not os.path.lexists(root.joinpath(*parts)),"campaign_unchained_later_capture_consumption")


def _copy(value):return json.loads(_raw(value))


def _digest(value):
    _need(type(value) is str and re.fullmatch(r"[0-9a-f]{64}",value),"campaign_digest_required")
    return value


def _decode(raw):
    _need(type(raw) is bytes and 0<len(raw)<=MAX_CONTROL,"campaign_control_bytes")
    def pairs(items):
        value={}
        for key,child in items:_need(key not in value,"campaign_duplicate_control_key");value[key]=child
        return value
    try:
        value=json.loads(raw,object_pairs_hook=pairs,parse_float=lambda _:_need(False,"campaign_float_refused"),parse_constant=lambda _:_need(False,"campaign_nonfinite_refused"))
        _need(type(value) is dict and _raw(value)==raw,"campaign_canonical_control")
        pending=[(value,0)];nodes=0
        while pending:
            child,depth=pending.pop();nodes+=1;_need(depth<=32 and nodes<=8000000,"campaign_control_resources")
            if type(child) is dict:
                _need(len(child)<=4096 and all(type(k) is str and len(k)<=512 for k in child),"campaign_control_dictionary")
                pending.extend((v,depth+1) for v in child.values())
            elif type(child) is list:
                _need(len(child)<=MAX_CONSUMED,"campaign_control_list");pending.extend((v,depth+1) for v in child)
            elif type(child) is str:_need(len(child)<=1024*1024,"campaign_control_string")
        return value
    except CampaignError:raise
    except (ValueError,TypeError,UnicodeError,RecursionError):raise CampaignError("campaign_JSON_refused") from None


def _batch(number):
    _need(type(number) is int and 1<=number<=MAX_BATCHES,"campaign_batch_number")
    return f"batch-{number:06d}"


def _accessions(values):
    _need(type(values) is list and len(values)<=MAX_CONSUMED and values==sorted(set(values))
        and all(type(v) is str and audit._ACCESSION.fullmatch(v) for v in values),"campaign_consumed_index")
    return values


def _request(value):
    _need(type(value) is dict and set(value)==fresh._REQUEST_KEYS,"campaign_exact_request")
    _need(all(type(v) is str and 0<len(v)<=2048 and not any(ord(c)<32 for c in v)
        for k,v in value.items() if k!="source_record_ordinal") and type(value["source_record_ordinal"]) is int
        and 1<=value["source_record_ordinal"]<=audit.MAX_QUARTER_ROWS,"campaign_request_types")
    _need(value["period"] in audit.PERIODS and value["form_type"] in {"4","4/A"}
        and audit._ACCESSION.fullmatch(value["accession_number"]) and audit._cik(value["issuer_cik"]),"campaign_request_scope")
    try:filed=date.fromisoformat(value["filing_date"])
    except ValueError:raise CampaignError("campaign_request_date") from None
    quarter=f"{filed.year}Q{(filed.month-1)//3+1}"
    match=audit._PATH.fullmatch(value["archive_path"])
    _need(quarter==value["period"] and filed.isoformat()==value["filing_date"] and match is not None
        and int(match.group(1))>0 and match.group(2)==value["accession_number"]
        and value["url"]=="https://www.sec.gov/Archives/"+value["archive_path"],"campaign_exact_parent_locator")
    for key,item in value.items():
        if key.endswith("sha256"):_digest(item)
    return value


def _record(value,ordinal):
    _need(type(value) is dict and set(value)==fresh._RECORD_KEYS and type(value["selection_ordinal"]) is int
        and value["selection_ordinal"]==ordinal and value["dispatch_authorized"] is value["canonical_admitted"] is False,
        "campaign_request_record")
    original,_=audit._source(value["source"]);request=_request(value["request"])
    mapping={"issuer_cik":"raw_issuer_cik",**{k:k for k in ("period","accession_number","form_type","filing_date",
        "source_record_ordinal","filing_metadata_sha256","quarterly_zip_sha256","submission_member_sha256","submission_header_line_sha256","schema_profile_sha256")}}
    _need(all(request[k]==original[v] for k,v in mapping.items()) and value["source_record_sha256"]==original["filing_metadata_sha256"]
        and value["request_sha256"]==_sha(_raw(request)),"campaign_request_source_crosslink")
    locator=fresh.SecMasterIndexRow(**value["selected_locator"]).to_payload()
    _need(all(request[k]==locator[k] for k in locator),"campaign_master_locator_crosslink")
    target={k:request[k] for k in ("period","accession_number","form_type","filing_date","issuer_cik")}
    target.update(quarterly_index_sha256=request["master_decoded_sha256"],complete_submission_url=request["url"])
    _need(value["pre_normalization_target"]==target,"campaign_original_target_crosslink")
    _digest(value["compiler_disposition_sha256"])
    return original


@dataclass(frozen=True,slots=True,weakref_slot=True,eq=False)
class CampaignBatch:
    _bytes:bytes=field(repr=False)
    _token:object=field(repr=False)
    def canonical_bytes(self):
        _need(type(self) is CampaignBatch and self._token is _TOKEN and _SEALS.get(self)==self._bytes,"genuine_campaign_factory")
        return self._bytes
    def to_payload(self):return _decode(self.canonical_bytes())
    @property
    def sha256(self):return _sha(self.canonical_bytes())


class CampaignBatchBuilder:
    """Full compiler stream before sealing; late repeats cannot slip a prefix."""
    def __init__(self,*,consumed,batch_number,predecessor,limit=None):
        self.consumed=set(_accessions(list(consumed)));self.number=batch_number;_batch(batch_number)
        self.limit=(FIRST_LIMIT if batch_number==1 else MAX_LIMIT) if limit is None else limit
        _need(type(self.limit) is int and (self.limit==FIRST_LIMIT if batch_number==1 else 1<=self.limit<=MAX_LIMIT),"campaign_batch_limit")
        _need(predecessor is None if batch_number==1 else type(predecessor) is dict,"campaign_predecessor_required")
        self.predecessor=_copy(predecessor);self.hashes={k:hashlib.sha256() for k in ("source_row","disposition","fresh_request")}
        self.sizes={k:0 for k in self.hashes};self.quarters={};self.eligible=[];self.blocked=set();self.closed=False;self.period=None
    def consume(self,row):
        _need(not self.closed and type(row) is dict and set(row)==fresh._DISPOSITION_KEYS and row["schema"]==audit.SCHEMA+"/filing","campaign_stream_row")
        self.closed=True  # Failure poisons this partially consumed builder.
        original,line=audit._source(row["source"]);period=original["period"]
        _need(self.period is None or period==self.period or audit.PERIODS.index(period)>audit.PERIODS.index(self.period),"campaign_quarter_rollback")
        self.period=period
        _need(row["source_record_sha256"]==original["filing_metadata_sha256"] and row["dispatch_authorized"] is row["canonical_admitted"] is False,"campaign_stream_hash_authority")
        quarter=self.quarters.setdefault(period,{"count":0,**{k:hashlib.sha256() for k in self.hashes},**{k+"_bytes":0 for k in self.hashes}})
        _need(list(self.quarters)==list(audit.PERIODS[:len(self.quarters)]) and original["source_record_ordinal"]==quarter["count"]+1,"campaign_source_order")
        quarter["count"]+=1
        for key in ("prior_consumed","historical_ambiguous_start_preserved","cross_quarter_accession_repeat","cross_quarter_source_identity_conflict","fresh_locatable_candidate"):
            _need(type(row[key]) is bool,"campaign_disposition_boolean")
        if any(row[k] for k in ("prior_consumed","historical_ambiguous_start_preserved","cross_quarter_accession_repeat","cross_quarter_source_identity_conflict")):
            self.blocked.add(original["accession_number"])
        lines={"source_row":line,"disposition":_raw(row)+b"\n","fresh_request":_raw(row["request"])+b"\n" if row["fresh_locatable_candidate"] else b""}
        for key,raw in lines.items():
            self.hashes[key].update(raw);self.sizes[key]+=len(raw);quarter[key].update(raw);quarter[key+"_bytes"]+=len(raw)
        if row["fresh_locatable_candidate"] and original["accession_number"] not in self.consumed and len(self.eligible)<self.limit:
            item={"selection_ordinal":len(self.eligible)+1,"source":original,"source_record_sha256":row["source_record_sha256"],
                **{k:row[k] for k in ("request","request_sha256","pre_normalization_target","selected_locator")},
                "compiler_disposition_sha256":_sha(lines["disposition"][:-1]),"dispatch_authorized":False,"canonical_admitted":False}
            _record(item,len(self.eligible)+1);self.eligible.append(_copy(item))
        self.closed=False
    def finish(self,*,source_roster,parent_audit,base_consumption,archive_exposures=ARCHIVE_EXPOSURES):
        _need(not self.closed,"campaign_builder_closed");self.closed=True
        genuine=roster.validate_pilot_sec_roster(source_roster);completed=audit.validate_pilot_sec_parent_audit(parent_audit)
        body=genuine.to_payload()
        _need(completed["source_roster_sha256"]==genuine.sha256 and completed["fixture_only"] is body["fixture_only"]
            and list(self.quarters)==list(audit.PERIODS),"campaign_full_genuine_factories")
        for stem in self.hashes:
            _need(completed[stem+"_jsonl_sha256"]==self.hashes[stem].hexdigest() and completed[stem+"_jsonl_bytes"]==self.sizes[stem],"campaign_complete_stream_binding")
        _need(body["source_row_jsonl_sha256"]==self.hashes["source_row"].hexdigest() and body["source_row_jsonl_bytes"]==self.sizes["source_row"],"campaign_roster_stream_binding")
        for expected in completed["quarters"]:
            quarter=self.quarters[expected["period"]]
            _need(quarter["count"]==expected["counts"]["source_filings"] and all(quarter[k].hexdigest()==expected[k+"_jsonl_sha256"]
                and quarter[k+"_bytes"]==expected[k+"_jsonl_bytes"] for k in self.hashes),"campaign_quarter_conservation")
        # A late repeat invalidates the candidate prefix; no first-occurrence
        # deduplication or silent refill across already consumed source rows.
        _need(not any(item["request"]["accession_number"] in self.blocked for item in self.eligible),"campaign_late_repeat_requires_reconciliation")
        selected=self.eligible
        _need(len({r["request"]["accession_number"] for r in selected})==len(selected),"campaign_selected_duplicate")
        value={"schema":SCHEMA+"/plan","fixture_only":body["fixture_only"],"batch_number":self.number,"batch_id":_batch(self.number),
            "limit":self.limit,"selected_count":len(selected),"requests":selected,"source_roster":body,"parent_audit":completed,
            "source_roster_sha256":genuine.sha256,"parent_audit_sha256":parent_audit.sha256,
            "consumed_accessions":sorted(self.consumed),"consumed_index_sha256":_sha(_raw(sorted(self.consumed))),
            "base_consumption":_copy(base_consumption),"predecessor":self.predecessor,"archive_exposures":_copy(list(archive_exposures)),
            "archive_membership_known":False,"policy":_copy(POLICY),"authority":dict(AUTHORITY)}
        validate_batch_plan(value);sealed=CampaignBatch(_raw(value),_TOKEN);_SEALS[sealed]=sealed._bytes;return sealed


def validate_batch_plan(value):
    try:
        keys={"schema","fixture_only","batch_number","batch_id","limit","selected_count","requests","source_roster","parent_audit",
            "source_roster_sha256","parent_audit_sha256","consumed_accessions","consumed_index_sha256","base_consumption","predecessor",
            "archive_exposures","archive_membership_known","policy","authority"}
        _need(type(value) is dict and set(value)==keys and value["schema"]==SCHEMA+"/plan" and type(value["fixture_only"]) is bool
            and value["batch_id"]==_batch(value["batch_number"]) and _raw(value["policy"])==_raw(POLICY) and value["archive_membership_known"] is False
            and _raw(value["authority"])==_raw(AUTHORITY),"campaign_plan_schema")
        number,limit=value["batch_number"],value["limit"]
        _need(type(limit) is int and (limit==FIRST_LIMIT if number==1 else 1<=limit<=MAX_LIMIT)
            and (value["predecessor"] is None if number==1 else type(value["predecessor"]) is dict),"campaign_plan_limit_predecessor")
        consumed=_accessions(value["consumed_accessions"])
        _need(value["consumed_index_sha256"]==_sha(_raw(consumed)) and value["archive_exposures"]==list(ARCHIVE_EXPOSURES),"campaign_index_archive_binding")
        proof=value["base_consumption"]
        _need(type(proof) is dict and set(proof)=={"old_exposure_inventory_sha256","old_exposure_snapshot_sha256","latest64_report_sha256",
            "latest64_capture_head","latest64_source_inventory_sha256","old_count","new64_count"}
            and type(proof["latest64_capture_head"]) is str and re.fullmatch(r"[0-9a-f]{40}",proof["latest64_capture_head"])
            and all(type(proof[k]) is int and 0<=proof[k]<=MAX_CONSUMED for k in ("old_count","new64_count")),"campaign_base_consumption_schema")
        for key,item in proof.items():
            if key.endswith("sha256"):_digest(item)
        _need(value["source_roster_sha256"]==_sha(_raw(value["source_roster"])) and value["parent_audit_sha256"]==_sha(_raw(value["parent_audit"]))
            and value["parent_audit"]["source_roster_sha256"]==value["source_roster_sha256"]
            and value["source_roster"]["fixture_only"] is value["parent_audit"]["fixture_only"] is value["fixture_only"],"campaign_completed_source_binding")
        _need([q["period"] for q in value["parent_audit"]["quarters"]]==list(audit.PERIODS),"campaign_all25_required")
        if value["fixture_only"] is False:
            _need(value["source_roster"]["counts"]=={"context_quarters":25,"pilot_quarters":20,"context_submission_rows":1281147,
                "context_form4_or_4a_rows":1163648,"pilot_submission_rows":1008318,"pilot_form4_or_4a_rows":921570},"campaign_recorded_population")
            _need(proof["latest64_report_sha256"]==archive.original.CAPTURE_REPORT_SHA256
                and proof["latest64_capture_head"]==archive.original.CAPTURE_HEAD and proof["new64_count"]==64
                and proof["latest64_source_inventory_sha256"]=="908600f5c405dcc4fe21c7a77c7c1bb58e9c3d98be8dd8fd02d3b3beefaa284a", "campaign_base_actual_pins")
        rows=value["requests"];_need(type(rows) is list and type(value["selected_count"]) is int and len(rows)==value["selected_count"]<=limit,"campaign_request_count")
        previous=(-1,0);seen=set()
        for ordinal,item in enumerate(rows,1):
            original=_record(item,ordinal);order=(audit.PERIODS.index(original["period"]),original["source_record_ordinal"])
            accession=original["accession_number"]
            _need(order>previous and accession not in seen and accession not in consumed,"campaign_request_order_freshness")
            previous=order;seen.add(accession)
        _decode(_raw(value));return _copy(value)
    except CampaignError:raise
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError):raise CampaignError("campaign_plan_refused") from None


def _identity(head):
    _need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"campaign_fixed_source")
    value=base.custody._identity(head)
    names={SELF_PATH,TEST_PATH,CAPTURE_SOURCE_PATH,CAPTURE_TEST_PATH,first.SELF_PATH,first.TEST_PATH,archive.SELF_PATH,archive.TEST_PATH,source.SELF_PATH,
        "research/insider_buying_sec_feed_archive_sample_v2.py","tests/test_insider_buying_sec_feed_archive_sample_v2.py",
        "tests/test_insider_buying_pilot_sec_fresh_selection_runner.py",base.SELF_PATH,
        "tests/test_insider_buying_pilot_sec_parent_audit_runner.py",source.retained.SELF_PATH,
        "tests/test_insider_buying_pilot_sec_parent_structure_runner.py"}
    own=base.custody._source_bytes(LANE_ROOT,tuple(sorted(names)))
    for name,digest in own.items():_need(_sha(base.custody._git(LANE_ROOT,"show",head+":"+name))==digest,"campaign_uncommitted_source")
    sources={**value["source_sha256"],**own};value={**value,"source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))}
    _current(value);return value


def _current(identity):
    first._source_identity(identity,required_paths=(SELF_PATH,TEST_PATH,CAPTURE_SOURCE_PATH,CAPTURE_TEST_PATH,first.SELF_PATH,first.TEST_PATH,archive.SELF_PATH,archive.TEST_PATH))
    _need(base.custody._source_bytes(LANE_ROOT,tuple(identity["source_sha256"]))==identity["source_sha256"]
        and base.custody._source_bytes(LANE_ROOT,tuple(base.FROZEN))==base.FROZEN,"campaign_current_source_changed")
    _need(set(base.custody._internal_source_paths(LANE_ROOT))<=set(identity["source_sha256"]),"campaign_loaded_source_closure_changed")
    _need(base.custody._source_bytes(LANE_ROOT,(first.SELF_PATH,first.TEST_PATH))=={
        first.SELF_PATH:archive.original.CAPTURE_SOURCE_SHA256,first.TEST_PATH:archive.original.CAPTURE_TEST_SHA256},"campaign_first64_frozen")


def _isolated():
    _need(sys.flags.isolated==sys.flags.no_site==sys.flags.no_user_site==sys.flags.dont_write_bytecode==1
        and sys.pycache_prefix==EMPTY_CACHE_PREFIX,"campaign_initial_native_flags")
    base._prove_isolation()


def _failed_reservation(raw,*,fixture=False,pin=None):
    expected=pin if fixture else {"sha256":FAILED_RESERVATION_SHA256,"bytes":FAILED_RESERVATION_BYTES,
        "head":FAILED_HEAD,"source_inventory_sha256":FAILED_INVENTORY_SHA256}
    _need(type(expected) is dict and set(expected)=={"sha256","bytes","head","source_inventory_sha256"}
        and type(expected["bytes"]) is int and len(raw)==expected["bytes"] and _sha(raw)==_digest(expected["sha256"]),"campaign_failed_reservation_pin")
    value=_decode(raw);identity=value.get("execution_identity")
    if fixture:
        _need(type(identity) is dict and type(identity.get("root")) is str,"campaign_failed_fixture_identity")
        first._fixture_root(Path(identity["root"]))
    first._source_identity({**identity,"root":str(LANE_ROOT)} if fixture else identity,
        required_paths=(SELF_PATH,TEST_PATH,CAPTURE_SOURCE_PATH,CAPTURE_TEST_PATH))
    _need(identity["head"]==expected["head"] and identity["source_inventory_sha256"]==expected["source_inventory_sha256"]
        and _raw(value)==_raw({"schema":FAILED_SCHEMA+"/reservation","batch_number":1,"execution_identity":identity,
            "policy":POLICY,"authority":AUTHORITY,"predecessor_pins":None}),"campaign_failed_reservation_crosslinks")
    return {"schema":SCHEMA+"/stopped-launch-lineage","failed_root_parts":list(FAILED_PARTS),"failed_execution_head":identity["head"],
        "reservation_sha256":_sha(raw),"reservation_bytes":len(raw),"source_inventory_sha256":identity["source_inventory_sha256"],
        "batch_inventory":["reservation.json"],"completed_predecessor":False,"historical_dispatch_count_measured":False},identity


def _launch_lineage():
    return {"schema":SCHEMA+"/stopped-launch-lineage","failed_root_parts":list(FAILED_PARTS),"failed_execution_head":FAILED_HEAD,
        "reservation_sha256":FAILED_RESERVATION_SHA256,"reservation_bytes":FAILED_RESERVATION_BYTES,"source_inventory_sha256":FAILED_INVENTORY_SHA256,
        "batch_inventory":["reservation.json"],"completed_predecessor":False,"historical_dispatch_count_measured":False}


class _FailedLaunchHold:
    """Strict old metadata only; never complete or resume the consumed launch."""
    def __init__(self,root,*,fixture=False,pin=None):
        if fixture:first._fixture_root(root);first._native_fixture_denial()
        else:_need(root==LANE_ROOT and pin is None,"campaign_failed_fixed_root")
        self.folders=[];self.lock=None;self.versions={};self.raws={}
        try:
            top=archive._Output(root.joinpath(*FAILED_PARTS));self.folders.append(top)
            batches=archive._Output(top.path/"batches");self.folders.append(batches)
            run=archive._Output(batches.path/_batch(1));self.folders.append(run)
            self.top,self.batches,self.run=top,batches,run
            self.directory_versions=[base.custody._version(os.fstat(folder.fd)) for folder in self.folders]
            _need(set(os.listdir(top.fd))=={"controller.lock","batches"} and set(os.listdir(batches.fd))=={_batch(1)}
                and set(os.listdir(run.fd))=={"reservation.json"},"campaign_failed_stopped_inventory")
            self.lock=os.open("controller.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd)
            fcntl.flock(self.lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
            self.lock_version=base.custody._version(os.fstat(self.lock))
            for folder,name,cap in ((top,"controller.lock",4096),(run,"reservation.json",MAX_CONTROL)):
                key=(folder.path,name);before=base.custody._version(os.stat(name,dir_fd=folder.fd,follow_symlinks=False))
                raw=folder.read(name,cap)
                _need(base.custody._version(os.stat(name,dir_fd=folder.fd,follow_symlinks=False))==before,"campaign_failed_old_control_changed")
                self.versions[key]=before;self.raws[key]=raw
            _need(self.raws[(top.path,"controller.lock")]==FAILED_LOCK_BYTES,"campaign_failed_lock_bytes")
            self.reservation_raw=self.raws[(run.path,"reservation.json")]
            self.summary,self.identity=_failed_reservation(self.reservation_raw,fixture=fixture,pin=pin)
            self.recheck()
        except BaseException:self.close();raise
    def recheck(self):
        _need(self.lock is not None,"campaign_failed_hold_closed")
        _need(set(os.listdir(self.top.fd))=={"controller.lock","batches"} and set(os.listdir(self.batches.fd))=={_batch(1)}
            and set(os.listdir(self.run.fd))=={"reservation.json"},"campaign_failed_stopped_inventory")
        _need(base.custody._version(os.fstat(self.lock))==self.lock_version
            ==base.custody._version(os.stat("controller.lock",dir_fd=self.top.fd,follow_symlinks=False)),"campaign_failed_lock_changed")
        for folder,version in zip(self.folders,self.directory_versions):
            folder.check();_need(base.custody._version(os.fstat(folder.fd))==version,"campaign_failed_directory_changed")
            for (path,name),before in self.versions.items():
                if path==folder.path:
                    _need(base.custody._version(os.stat(name,dir_fd=folder.fd,follow_symlinks=False))==before
                        and folder.read(name,MAX_CONTROL)==self.raws[(path,name)]
                        and base.custody._version(os.stat(name,dir_fd=folder.fd,follow_symlinks=False))==before,"campaign_failed_old_control_changed")
    def close(self):
        base.selector._close_all((archive.SimpleCloseFD(self.lock),*reversed(self.folders)),phase="campaign_failed_hold_cleanup")
        self.lock=None;self.folders=[]


def _launcher_health_worker(identity):
    _isolated();_current(identity)
    return {"schema":SCHEMA+"/launcher-health","execution_identity":identity,
        "native_network_fork_allwrite_securityexec_denial":True,"artifact_reads":0,"provider_requests":0,"credential_reads":0,"qc_accesses":0}


def _launcher_health(identity):
    """Exact worker launcher, source only, before claiming any new namespace."""
    try:
        result=_run_child(_command(identity,1,role="health"),timeout=30)
        expected={"schema":SCHEMA+"/launcher-health","execution_identity":identity,
            "native_network_fork_allwrite_securityexec_denial":True,"artifact_reads":0,"provider_requests":0,"credential_reads":0,"qc_accesses":0}
        _need(_raw(result)==_raw(expected),"campaign_launcher_health_witness")
    except Exception:raise NativeWorkerRefused("launcher_health","native_or_control_refused") from None


def _failed_launch_worker(identity):
    _isolated();_current(identity);held=None
    try:
        held=_FailedLaunchHold(LANE_ROOT);held.recheck();_current(identity)
        return {"schema":SCHEMA+"/stopped-launch-worker","execution_identity":identity,"lineage":held.summary,
            "reservation_witness":held.reservation_raw.decode(),"native_network_fork_allwrite_securityexec_denial":True}
    finally:base.selector._close_all((held,),phase="campaign_stopped_launch_cleanup")


def _stopped_launch_lineage(identity):
    result=_run_child(_command(identity,1,role="stopped"),timeout=60)
    _need(type(result) is dict and set(result)=={"schema","execution_identity","lineage","reservation_witness","native_network_fork_allwrite_securityexec_denial"}
        and result["schema"]==SCHEMA+"/stopped-launch-worker" and _raw(result["execution_identity"])==_raw(identity)
        and type(result["reservation_witness"]) is str and result["native_network_fork_allwrite_securityexec_denial"] is True,"campaign_stopped_launch_witness")
    summary,old_identity=_failed_reservation(result["reservation_witness"].encode())
    _need(_raw(summary)==_raw(result["lineage"]),"campaign_stopped_launch_crosslinks")
    verify_plan_producer({"execution_identity":old_identity})
    return summary


def _previous_pins(number,pins):
    _batch(number)
    if number==1:_need(pins is None,"campaign_first_batch_no_predecessor");return None
    _need(type(pins) is dict and set(pins)=={"complete_sha256","plan_sha256","index_sha256"},"campaign_external_predecessor_pins_required")
    for value in pins.values():_digest(value)
    return pins


def _next_consumption(number,pins,identity):
    if number==1:return None,None
    # Production successor verification lives in the additive collector, never
    # a fabricated receipt/dictionary or a reset of the original first64.
    from research import insider_buying_pilot_sec_parent_batch_capture_v2 as capture
    return capture.read_actual_predecessor(number-1,expected_complete_sha256=pins["complete_sha256"],
        expected_plan_sha256=pins["plan_sha256"],expected_index_sha256=pins["index_sha256"],execution_identity=identity)


def _plan_worker(identity,number,predecessor_pins=None):
    prior_hold=accepted=intake=failed=None;holds=[];phase="initial_isolation"
    try:
        _isolated();phase="source_identity";_current(identity);_previous_pins(number,predecessor_pins)
        _no_unchained_later_capture();phase="stopped_launch_custody"
        failed=_FailedLaunchHold(LANE_ROOT);phase="prior_custody"
        prior_hold=source.retained._PriorHold();prior=prior_hold.report()
        accepted=base.prior._Held(LANE_ROOT);base.prior._selector(accepted,base.prior.ACTUAL_ANCHORS)
        selected=accepted.leaf(base.prior.SELECTOR_PARTS,"selection.json",base.prior.MAX_CONTROL,base.prior.ACTUAL_ANCHORS.selection)
        holds,exposure_raw,snapshot,candidates=base.exposure.observe_exposures(base.exposure.actual_roots(),fixture_only=False)
        _need(_sha(exposure_raw)==prior["exposure_inventory_sha256"] and _sha(snapshot)==prior["exposure_snapshot_sha256"],"campaign_old_exposure_changed")
        candidates=base.exposure.hash_candidate_bodies(holds,candidates)
        _need(_sha(candidates)==prior["retained_body_inventory_sha256"],"campaign_old_candidates_changed")
        latest=archive._latest64_metadata();old=set(audit._exposures(base._decode(exposure_raw)))
        predecessor,following=_next_consumption(number,predecessor_pins,identity)
        consumed=sorted(old|set(latest["accessions"])|set(following or ()))
        proof={"old_exposure_inventory_sha256":_sha(exposure_raw),"old_exposure_snapshot_sha256":_sha(snapshot),
            "latest64_report_sha256":latest["report_sha256"],"latest64_capture_head":latest["capture_head"],
            "latest64_source_inventory_sha256":latest["source_inventory_sha256"],"old_count":len(old),"new64_count":len(latest["accessions"])}
        _need(latest["report_sha256"]==archive.original.CAPTURE_REPORT_SHA256 and latest["capture_head"]==archive.original.CAPTURE_HEAD
            and len(latest["accessions"])==64,"campaign_completed_first64_pins")
        builder=CampaignBatchBuilder(consumed=consumed,batch_number=number,predecessor=predecessor)
        phase="source_rederivation"
        masters=next(held for held in holds if held.spec.root_id=="masters-v3")
        compiler=audit.PilotSecParentAuditCompiler(exposure_raw=exposure_raw,expected_exposure_sha256=_sha(exposure_raw),
            candidates_raw=candidates,expected_candidates_sha256=_sha(candidates),master_for_period=lambda p:base._master(masters.tree,p),emit_row=builder.consume)
        intake=base.selector._HeldIntake()
        derived=roster.derive_pilot_sec_roster(intake_manifest_raw=intake.manifest_raw,expected_manifest_sha256=intake.context["manifest_sha256"],
            selection_raw=selected,expected_selection_sha256=base.prior.ACTUAL_ANCHORS.selection,
            quarter_inputs=roster.held_context_quarters(intake),consume_row=compiler.consume,fixture_only=False)
        compiled=compiler.finish(derived)
        _need(derived.to_payload()==prior["source_roster"] and compiled.to_payload()==prior["parent_audit"],"campaign_original_full_audit_changed")
        batch=builder.finish(source_roster=derived,parent_audit=compiled,base_consumption=proof)
        phase="final_input_recheck"
        intake.recheck();accepted.recheck();prior_hold.recheck();failed.recheck()
        for held in holds:held.recheck()
        _current(identity)
        return {"schema":SCHEMA+"/worker","execution_identity":identity,"plan":batch.to_payload(),"plan_sha256":batch.sha256,"stopped_launch_lineage":failed.summary,
            "native_network_fork_allwrite_securityexec_denial":True,"new_provider_requests":0,"credential_reads":0,"qc_accesses":0,"outcome_looks":0}
    except Exception as error:
        error._campaign_phase=phase;raise
    finally:base.selector._close_all((intake,accepted,prior_hold,failed,*reversed(holds)),phase="campaign_planner_cleanup")


def _command(identity,number,predecessor_pins=None,*,role="plan"):
    _previous_pins(number,predecessor_pins)
    _need(role in {"plan","health","stopped"},"campaign_fixed_worker_role")
    call={"plan":"m._plan_worker(identity,"+repr(number)+","+repr(predecessor_pins)+")","health":"m._launcher_health_worker(identity)","stopped":"m._failed_launch_worker(identity)"}[role]
    code="import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_pilot_sec_parent_campaign_v2 as m;identity=json.loads("+repr(_raw(identity).decode())+");\ntry:r="+call+"\nexcept Exception as e:print(m._raw(m._safe_failure(e)).decode());sys.exit(2)\nprint(m._raw(r).decode())"
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)


def _run_child(command,payload=b"",*,timeout=900):
    """Own bounded IPC codec: supports the full eventual consumed index.

    Do not inherit archive-v1's smaller100001-list profile for this new
    campaign. Private body/contact inputs are anonymous stdin, never argv.
    """
    _need(type(payload) is bytes and len(payload)<=16*1024*1024,"campaign_stdin_bound")
    process=subprocess.Popen(command,cwd=LANE_ROOT,env=None,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    poll=selectors.DefaultSelector();out=bytearray();errors=bytearray();offset=0;deadline=time.monotonic()+timeout
    try:
        for stream in (process.stdin,process.stdout,process.stderr):os.set_blocking(stream.fileno(),False)
        if payload:poll.register(process.stdin,selectors.EVENT_WRITE,"input")
        else:process.stdin.close()
        poll.register(process.stdout,selectors.EVENT_READ,out);poll.register(process.stderr,selectors.EVENT_READ,errors)
        while poll.get_map():
            remaining=deadline-time.monotonic();_need(remaining>0,"campaign_native_worker_deadline")
            for key,_ in poll.select(min(.2,remaining)):
                if key.data=="input":
                    try:count=os.write(key.fileobj.fileno(),memoryview(payload)[offset:offset+65536])
                    except BrokenPipeError:poll.unregister(key.fileobj);key.fileobj.close();continue
                    offset+=count
                    if offset==len(payload):poll.unregister(key.fileobj);key.fileobj.close()
                else:
                    cap=16384 if key.data is errors else MAX_CONTROL
                    chunk=os.read(key.fileobj.fileno(),min(65536,cap+1-len(key.data)))
                    if chunk:key.data.extend(chunk);_need(len(key.data)<=cap,"campaign_native_pipe_bound")
                    else:poll.unregister(key.fileobj)
        code=process.wait(timeout=max(.001,deadline-time.monotonic()))
        _need(not errors and out,"campaign_native_worker_refused")
        result=_decode(bytes(out).removesuffix(b"\n"))
        if code==2 and set(result)=={"schema","phase","code"} and result["schema"]==SCHEMA+"/worker-refusal" and result["phase"] in PHASES and result["code"] in FAILURE_CODES:
            raise NativeWorkerRefused(result["phase"],result["code"])
        _need(code==0,"campaign_native_worker_refused");return result
    except BaseException:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait();raise
    finally:base.selector._close_all((poll,process.stdin,process.stdout,process.stderr),phase="campaign_native_pipe_cleanup")


class Controller:
    """One cooperative writer; no root reset, unknown files or old batch resume."""
    def __init__(self,root,*,create=False,fixture=False):
        if fixture:first._fixture_root(root);first._native_fixture_denial()
        else:_need(root==LANE_ROOT,"campaign_fixed_root")
        self.root,self.folders,self.lock=Path(root),[],None
        try:
            self.top=archive._Output(self.root.joinpath(*ARTIFACT_PARTS),create=create);self.folders.append(self.top)
            self.batches=archive._Output(self.top.path/"batches",create=create);self.folders.append(self.batches)
            if create and not self.top.tree.exists("controller.lock"):self.top.publish("controller.lock",LOCK_BYTES)
            self.lock=os.open("controller.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.top.fd)
            self.version=base.custody._version(os.fstat(self.lock));fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            _need(self.top.read("controller.lock")==LOCK_BYTES and set(os.listdir(self.top.fd))=={"controller.lock","batches"},"campaign_controller_inventory")
            self.expected_batches=set(os.listdir(self.batches.fd))
        except BaseException:self.close();raise
    def check(self):
        for held in self.folders:held.check()
        _need(set(os.listdir(self.batches.fd))==self.expected_batches,"campaign_unexpected_batch_inventory")
        _need(base.custody._version(os.fstat(self.lock))==self.version==base.custody._version(os.stat("controller.lock",dir_fd=self.top.fd,follow_symlinks=False)),"campaign_controller_lock_changed")
    def fresh(self,number):
        name=_batch(number);self.check()
        _need(set(os.listdir(self.batches.fd))=={_batch(n) for n in range(1,number)},"campaign_batch_gap_or_consumed_namespace")
        run=archive._Output(self.batches.path/name,create=True);self.folders.append(run);self.expected_batches.add(name)
        _need(not os.listdir(run.fd),"campaign_no_batch_resume");return run
    def close(self):
        active=sys.exc_info()[0] is not None;failure=False
        for held in (archive.SimpleCloseFD(self.lock),*reversed(self.folders)):
            try:held.close()
            except BaseException:failure=True
        self.lock=None;self.folders=[]
        if failure and not active:raise CampaignError("campaign_controller_cleanup")


def _validate_worker(result,identity,number):
    _need(type(result) is dict and set(result)=={"schema","execution_identity","plan","plan_sha256","stopped_launch_lineage","native_network_fork_allwrite_securityexec_denial",
        "new_provider_requests","credential_reads","qc_accesses","outcome_looks"} and result["schema"]==SCHEMA+"/worker"
        and result["execution_identity"]==identity and result["native_network_fork_allwrite_securityexec_denial"] is True
        and _raw(result["stopped_launch_lineage"])==_raw(_launch_lineage())
        and all(type(result[k]) is int and result[k]==0 for k in ("new_provider_requests","credential_reads","qc_accesses","outcome_looks")),"campaign_worker_witness")
    plan=validate_batch_plan(result["plan"])
    _need(plan["fixture_only"] is False and plan["batch_number"]==number and result["plan_sha256"]==_sha(_raw(plan)),"campaign_worker_plan_crosslink")
    return plan


def prepare_actual_batch(expected_head,*,batch_number=1,predecessor_pins=None):
    identity=_identity(expected_head);_previous_pins(batch_number,predecessor_pins);controller=None
    _launcher_health(identity)
    lineage=_stopped_launch_lineage(identity)
    _need(_raw(lineage)==_raw(_launch_lineage()) and _identity(expected_head)==identity,"campaign_stopped_launch_lineage_changed")
    _no_unchained_later_capture()
    reservation={"schema":SCHEMA+"/reservation","batch_number":batch_number,"execution_identity":identity,"policy":_copy(POLICY),"authority":dict(AUTHORITY),"predecessor_pins":_copy(predecessor_pins),"stopped_launch_lineage":lineage}
    _need(_decode(_raw(reservation))==reservation,"campaign_production_reservation_roundtrip")
    try:
        controller=Controller(LANE_ROOT,create=True);run=controller.fresh(batch_number)
        rsha=run.publish("reservation.json",_raw(reservation),cap=MAX_CONTROL)
        result=_run_child(_command(identity,batch_number,predecessor_pins),timeout=900)
        plan=_validate_worker(result,identity,batch_number);_need(_identity(expected_head)==identity,"campaign_parent_source_changed")
        psha=run.publish("plan.json",_raw(plan),cap=MAX_CONTROL)
        complete={"schema":SCHEMA+"/complete","batch_number":batch_number,"execution_identity":identity,"reservation_sha256":rsha,
            "plan_sha256":psha,"stopped_launch_lineage":lineage,"native_network_fork_allwrite_securityexec_denial":True,"authority":dict(AUTHORITY)}
        csha=run.publish("complete.json",_raw(complete),cap=MAX_CONTROL);controller.check()
        return {"schema":SCHEMA+"/public","batch_number":batch_number,"plan_sha256":psha,"complete_sha256":csha,
            "selected_count":plan["selected_count"],"next_action":"capture_exact_qualified_batch_not_backtest","authority":dict(AUTHORITY)}
    finally:
        if controller:controller.close()


def _validate_plan_controls(raws,number,*,expected_plan_sha256,expected_complete_sha256,expected_producer_head,fixture=False):
    """Own receipt crosslinks; externally pinned origin is independently bound."""
    _need(type(raws) is dict and set(raws)=={"reservation.json","plan.json","complete.json"},"campaign_plan_control_inventory")
    _need(_sha(raws["plan.json"])==_digest(expected_plan_sha256) and _sha(raws["complete.json"])==_digest(expected_complete_sha256),
        "campaign_external_plan_complete_pins")
    reservation,plan,complete=(_decode(raws[n]) for n in ("reservation.json","plan.json","complete.json"))
    validate_batch_plan(plan)
    pins=reservation.get("predecessor_pins");_previous_pins(number,pins)
    _need(_raw(complete)==_raw({"schema":SCHEMA+"/complete","batch_number":number,"execution_identity":reservation["execution_identity"],
        "reservation_sha256":_sha(raws["reservation.json"]),"plan_sha256":_sha(raws["plan.json"]),
        "stopped_launch_lineage":_launch_lineage(),"native_network_fork_allwrite_securityexec_denial":True,"authority":dict(AUTHORITY)}) and plan["batch_number"]==number
        and plan["fixture_only"] is fixture and _raw(reservation)==_raw({"schema":SCHEMA+"/reservation","batch_number":number,
            "execution_identity":complete["execution_identity"],"policy":POLICY,"authority":dict(AUTHORITY),"predecessor_pins":pins,"stopped_launch_lineage":_launch_lineage()}),"campaign_plan_receipt_crosslinks")
    if number>1:_need(all(plan["predecessor"].get(k)==v for k,v in pins.items()),"campaign_external_predecessor_crosslink")
    identity=complete["execution_identity"]
    _need(type(expected_producer_head) is str and re.fullmatch(r"[0-9a-f]{40}",expected_producer_head)
        and type(identity) is dict and set(identity)=={"root","branch","head","clean","source_sha256","source_inventory_sha256"}
        and identity["head"]==expected_producer_head and identity["branch"]==LANE_BRANCH and identity["clean"] is True
        and type(identity["source_sha256"]) is dict and {SELF_PATH,TEST_PATH}<=set(identity["source_sha256"])
        and 1<=len(identity["source_sha256"])<=4096 and identity["source_inventory_sha256"]==_sha(_raw(identity["source_sha256"]))
        and all(type(n) is str and re.fullmatch(r"[A-Za-z0-9_./-]+\.py",n) and not n.startswith("/")
            and all(p not in {"",".",".."} for p in n.split("/")) and type(d) is str and audit._SHA.fullmatch(d)
            for n,d in identity["source_sha256"].items()),"campaign_external_producer_identity")
    if fixture:first._fixture_root(Path(identity["root"]))
    else:_need(identity["root"]==str(LANE_ROOT) and {CAPTURE_SOURCE_PATH,CAPTURE_TEST_PATH}<=set(identity["source_sha256"]),"campaign_producer_fixed_root_closure")
    return plan,{"plan_sha256":_sha(raws["plan.json"]),"complete_sha256":_sha(raws["complete.json"]),"execution_identity":complete["execution_identity"]}


class HeldBatchPlan:
    """Pinned metadata remains held through capture; never a raw-body reader.

    The trusted parent may hold this metadata while a separate native worker
    rederives source evidence. Native callers prove denial before construction.
    """
    def __init__(self,root,number,*,expected_plan_sha256,expected_complete_sha256,expected_producer_head,fixture=False):
        if fixture:first._fixture_root(root);first._native_fixture_denial()
        else:_need(root==LANE_ROOT,"campaign_fixed_plan_root")
        _digest(expected_plan_sha256);_digest(expected_complete_sha256);_batch(number)
        self.tree=None;self.raws={};self.versions={}
        try:
            self.tree=archive._Output(root.joinpath(*ARTIFACT_PARTS,"batches",_batch(number)))
            self.directory_version=base.custody._version(os.fstat(self.tree.fd))
            _need(set(os.listdir(self.tree.fd))=={"reservation.json","plan.json","complete.json"},"campaign_complete_plan_inventory")
            for name in ("reservation.json","plan.json","complete.json"):
                self.versions[name]=base.custody._version(os.stat(name,dir_fd=self.tree.fd,follow_symlinks=False))
                self.raws[name]=self.tree.read(name,MAX_CONTROL)
                _need(base.custody._version(os.stat(name,dir_fd=self.tree.fd,follow_symlinks=False))==self.versions[name],"campaign_old_plan_changed")
            self.plan,self.receipt=_validate_plan_controls(self.raws,number,expected_plan_sha256=expected_plan_sha256,
                expected_complete_sha256=expected_complete_sha256,expected_producer_head=expected_producer_head,fixture=fixture)
            self.recheck(full=True)
        except BaseException:self.close();raise
    def recheck(self,*,full=False):
        _need(self.tree is not None,"campaign_plan_hold_closed")
        self.tree.tree.check()  # Ancestry/descriptor checks, not large rehash.
        _need(set(os.listdir(self.tree.fd))==set(self.raws) and base.custody._version(os.fstat(self.tree.fd))==self.directory_version
            and all(base.custody._version(os.stat(n,dir_fd=self.tree.fd,follow_symlinks=False))==v
                for n,v in self.versions.items()),"campaign_old_plan_changed")
        if full:
            self.tree.check()
            _need(all(self.tree.read(n,MAX_CONTROL)==self.raws[n] for n in self.versions),"campaign_old_plan_bytes_changed")
    def close(self):
        if self.tree:self.tree.close();self.tree=None


def verify_plan_producer(receipt):
    """Trusted-parent Git proof; never call under the fork-denied worker."""
    identity=receipt["execution_identity"];first._source_identity(identity,required_paths=(SELF_PATH,TEST_PATH,CAPTURE_SOURCE_PATH,CAPTURE_TEST_PATH))
    for name,digest in identity["source_sha256"].items():
        _need(_sha(base.custody._git(LANE_ROOT,"show",identity["head"]+":"+name))==digest,"campaign_original_producer_Git_proof")


def read_actual_batch_plan(number,*,expected_plan_sha256,expected_complete_sha256,expected_producer_head):
    """Initially native-denied loader returns an OPEN hold; caller must close."""
    _isolated()
    return HeldBatchPlan(LANE_ROOT,number,expected_plan_sha256=expected_plan_sha256,
        expected_complete_sha256=expected_complete_sha256,expected_producer_head=expected_producer_head)


class _Parser(argparse.ArgumentParser):
    def error(self,message):raise CampaignError("campaign_CLI_arguments_refused")


def main(argv=None):
    try:
        parser=_Parser(description=__doc__);parser.add_argument("--expected-head",required=True);parser.add_argument("--batch",type=int,default=1)
        for field in ("complete","plan","index"):parser.add_argument("--previous-"+field)
        args=parser.parse_args(argv);provided=(args.previous_complete,args.previous_plan,args.previous_index)
        pins=None if not any(provided) else {"complete_sha256":provided[0],"plan_sha256":provided[1],"index_sha256":provided[2]}
        result=prepare_actual_batch(args.expected_head,batch_number=args.batch,predecessor_pins=pins)
    except NativeWorkerRefused as error:
        print(_raw({"disposition":"campaign_plan_refused","failure_stage":error.phase,"failure_code":error.code}).decode());return 2
    except Exception:print('{"disposition":"campaign_plan_refused"}');return 2
    print(_raw(result).decode());return 0


if __name__=="__main__":raise SystemExit(main())
