"""ONE separately registered Oct7 archive: full raw custody, never admission.

The frozen pure recognizer is not an acquisition front. This new front binds
the observed Q4 listing and cumulative consumed-index, initially native-denied
source/control health, one fresh namespace, private stdin and one durable GET.
Only a fully screened/integrity-checked immutable response may be retained.
Opaque physical TAR profiles can be retained but never extracted or admitted.
Neither unretained June failure is retried or diagnosed here.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
import fcntl
import http.client
import os
from pathlib import Path
import re
import resource
import signal
import sys
import threading
import time
import weakref

from research import insider_buying_sec_feed_format_v3 as engine
from research import insider_buying_sec_feed_directory_q4_v2 as directory
from research import insider_buying_sec_feed_archive_sample_v2 as old
from research import insider_buying_pilot_sec_parent_batch_capture_v2 as batch

publication,custody,privacy,source_runner=directory.publication,directory.custody,directory.privacy,directory.source_runner
contact_io=directory.contact_io
_raw,_sha,_control=old._raw,old._sha,old._control
SCHEMA="insider-sec-feed-archive-format-v3"
SELF_PATH="research/insider_buying_sec_feed_archive_format_v3.py"
TEST_PATH="tests/test_insider_buying_sec_feed_archive_format_v3.py"
LANE_ROOT,LANE_BRANCH=directory.LANE_ROOT,directory.LANE_BRANCH
EMPTY_CACHE_PREFIX=batch.campaign.EMPTY_CACHE_PREFIX
ARTIFACT_PARTS=("artifacts","insider_buying","sec_feed_archive_format_v3")
AUDIT_ID="ib-sec-feed-archive-20201007-format-v3-20261025-once"
URL="https://www.sec.gov/Archives/edgar/Feed/2020/QTR4/20201007.nc.tar.gz"
LOCK_BYTES=b"INSETF-single-unused-20201007-archive-format-v3\n"
MAX_COMPRESSED=512*1024**2
MAX_CONTROL=64*1024**2
TRANSPORT_SECONDS,IDLE_SECONDS,WORKER_SECONDS=600,15,1800
WORKER_VM_GROWTH_BYTES=4*1024**3
WORKER_PEAK_RSS_FUSE_BYTES=4*1024**3
RSS_FUSE_POLL_SECONDS=0.05
MIN_FREE_BYTES=8*1024**3
DIRECTORY_HEAD="a3b84a1dfb7a4fbe958ac162fae88a74f882e706"
DIRECTORY_SOURCE_INVENTORY="df5d0dabd4c6f3732fccdc59a0ce46b1492ddc8eda304ed0f34c72e2098420e4"
DIRECTORY_REPORT="6081e7b6d92e7a7916e38735f7020a4c417e93f309dd1fe2225f8bf0bd54952f"
DIRECTORY_BODY="d53ecb1d60e139ff2a132bebffcce7d97bf3130964175c6a550ac86d80ef17d9"
DIRECTORY_INVENTORY="a670a31dadf0521abbb458e3e057042abde5cc3b35c13cef871ff6cd2452a37f"
CONSUMED_PINS={"complete.json":"6233fc9b49c6a10c59904179199514b7d1e7df979df1c26d5d0ee2853bc04339",
    "plan.json":"3e54de6b0c5e9355ed83610f447fa86ad461f990ac36d41ed35ab5ee9640a555",
    "consumed-index.json":"d501e30d5ce1e9b90cd8738251036fa5f0dbf0a16bba65d6c5d66fa83af4f664"}
FROZEN={"research/insider_buying_sec_feed_format_v3.py":"acfd242f083809a67510d96ab8129dc8da02bdbe17f930f475f7da40c58cd675",
    "tests/test_insider_buying_sec_feed_format_v3.py":"4057b4764abdaae73bbe822aa5ec992d1db2922b4fce294b308f57743bfebb45",
    directory.SELF_PATH:"eb26edea5e854834bcfa25b61b312dd7aaee2c91635d00b21d943041c6807c5b",
    directory.TEST_PATH:"13d344dcdfab2f95aa3500aa03f3a7d4a8f6d88aa3ef7dbc2d0deb72f9fb13f5",
    engine.PRIVACY_SOURCE_PATH:engine.PRIVACY_SOURCE_SHA256}
_TOKEN=object();_ACTIVATIONS=weakref.WeakKeyDictionary();_DISPATCH=weakref.WeakKeyDictionary()
_PHASES=frozenset({"arguments","source","native_preflight","inputs","namespace","capacity","reservation","contact",
    "claim","start","transport","inspection","publication","complete","final","readback","cleanup"})


class ArchiveFormatError(ValueError):
    """Finite own phase/code, never foreign/private exception text."""


class _AbsoluteDeadline(Exception):pass


def _need(value,code):
    if not value:raise ArchiveFormatError(code)


def _classified(phase,error):
    # Only explicitly raised own static codes are public. Foreign text is not.
    code=error.args[0] if type(error) is ArchiveFormatError and len(error.args)==1 else None
    public={"private_arguments_refused","private_contact_mode_refused","fixed_actual_front_required","source_changed",
        "native_worker_refused","native_source_preflight_refused","fresh_namespace_already_exists","disk_reserve_refused",
        "inputs_changed","trusted_activation_required","dispatch_context_refused","transport_front_refused",
        "absolute_transport_deadline","transport_cleanup_refused","output_inventory_changed","output_lock_changed",
        "readback_pin_refused","readback_crosslinks_refused","readback_engine_differs","local_operation_refused"}
    return {"phase":phase if phase in _PHASES else "source","code":code if code in public else "local_operation_refused"}


def _at(phase,error):
    value=_classified(getattr(error,"phase",phase),error)
    result=ArchiveFormatError(value["code"]);result.phase=value["phase"];return result


def _authority():
    return {**directory._authority(),"bounded_named_archive_acquisition":False,"full_raw_retention_scope_only":False,
        "primary_ownership_XML":False,"acceptance_verified":False,"point_in_time":False,"canonical_admitted":False,"backtesting_ready":False}


def registration():
    return {"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,"method":"GET","url":URL,
        "directory_head":DIRECTORY_HEAD,"directory_report_sha256":DIRECTORY_REPORT,"directory_body_sha256":DIRECTORY_BODY,
        "directory_inventory_sha256":DIRECTORY_INVENTORY,"source_ordinal":5,"listed_name":"20201007.nc.tar.gz",
        "advertised_size_text":"390877 KB","advertisement_is_priority_cue_not_measured_bytes":True,
        "advertised_KB_base_or_rounding_qualified":False,"maximum_GETs":1,"maximum_compressed_bytes":MAX_COMPRESSED,
        "transport_absolute_seconds":TRANSPORT_SECONDS,"transport_idle_seconds":IDLE_SECONDS,"native_worker_wall_seconds":WORKER_SECONDS,
        "native_worker_memory_policy":_memory_policy(),"minimum_free_reserve_bytes":MIN_FREE_BYTES,
        "capacity_includes_worst_case_response_and_controls":True,"redirects":False,"proxies":False,"retries":False,
        "HEAD_Range_alias_requests":False,"full_raw_retention_not_compact_discard":True,
        "privacy_integrity_before_body_header_SHA_or_retention":True,"known_consumed_accessions":20044,
        "unknown_June_archive_memberships_remain_unknown":True,"individual_parent_dispatches":0,
        "member_XML_financial_extraction":False,"readback_current_private_contact_reload_registered":True,
        "original_current_contact_equality_attested":False,"earlier_URLs_retried_or_rediagnosed":False,"authority":_authority()}


def _isolated():
    _need(sys.flags.isolated==sys.flags.no_site==sys.flags.no_user_site==sys.flags.dont_write_bytecode==1
        and sys.pycache_prefix==EMPTY_CACHE_PREFIX,"initial_isolated_flags_required")


def _memory_policy():
    return {"platform":"darwin","VM_baseline":"libproc self PROC_PIDTASKINFO virtual bytes, not resident bytes",
        "maximum_new_VM_growth_bytes":WORKER_VM_GROWTH_BYTES,"existing_stricter_soft_and_hard_limits_preserved":True,
        "kernel_limit_install_and_readback_required_before_inputs":True,"peak_RSS_sample_source":"getrusage RUSAGE_SELF Darwin bytes",
        "sampled_peak_RSS_fuse_bytes":WORKER_PEAK_RSS_FUSE_BYTES,"requested_RSS_poll_interval_ms":50,
        "sample_failure_or_overshoot_terminates_worker":True,"instantaneous_or_hard_RSS_bound_claimed":False,
        "sampling_can_overshoot_between_observations":True,"final_sample_and_monitor_liveness_required":True,
        "production_publish_true_monitor_scope":"source/input/inspection/replay plus JSON serialization and stdout write/flush/final sample",
        "direct_publish_false_caller_serialization_sampled":False,
        "volatile_observed_metrics_in_deterministic_plan":False}


def _self_memory():
    """Darwin's exact 96-byte public task-info structure, THIS process only."""
    _need(sys.platform=="darwin","macOS_native_memory_policy_required")
    library=ctypes.CDLL("/usr/lib/libproc.dylib",use_errno=True)
    call=library.proc_pidinfo
    call.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_int];call.restype=ctypes.c_int
    buffer=ctypes.create_string_buffer(96)
    _need(call(os.getpid(),4,0,buffer,96)==96,"self_memory_metric_refused")
    virtual=int.from_bytes(buffer.raw[:8],sys.byteorder);resident=int.from_bytes(buffer.raw[8:16],sys.byteorder)
    _need(0<resident<=virtual<(1<<63)-WORKER_VM_GROWTH_BYTES,"self_memory_metric_refused")
    return virtual,resident


def _rss_sample():
    _need(sys.platform=="darwin","macOS_native_memory_policy_required")
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    _need(type(peak) is int and 0<peak<=WORKER_PEAK_RSS_FUSE_BYTES,"sampled_peak_RSS_fuse_refused")


def _rss_fuse_once():
    try:_rss_sample()
    except BaseException:
        os._exit(2)
        return False  # Only reachable in an invented terminating-call seam.
    return True


class _WorkerMemoryGuard:
    def __init__(self):
        _need(sys.platform=="darwin","macOS_native_memory_policy_required")
        baseline,_=_self_memory();soft,hard=resource.getrlimit(resource.RLIMIT_AS)
        _need(type(soft) is type(hard) is int and 0<soft<=hard,"existing_VM_limit_refused")
        limit=min(baseline+WORKER_VM_GROWTH_BYTES,soft,hard)
        _need(limit>baseline,"existing_VM_limit_leaves_no_growth")
        # macOS already maps a very large shared virtual region. An absolute
        # 4GiB address-space limit is invalid; this bounds NEW VM growth and
        # does not pretend that committing existing mappings is hard-RSS bound.
        resource.setrlimit(resource.RLIMIT_AS,(limit,hard))
        _need(resource.getrlimit(resource.RLIMIT_AS)==(limit,hard),"VM_limit_readback_refused")
        _rss_sample();self.stop=threading.Event();self.thread=threading.Thread(target=self._watch,name="ib-archive-v3-rss-fuse",daemon=True)
        self.thread.start()
        try:self.check()
        except BaseException:
            self.stop.set();self.thread.join(timeout=0.25);raise

    def _watch(self):
        while not self.stop.wait(RSS_FUSE_POLL_SECONDS):
            if not _rss_fuse_once():return

    def check(self):
        _need(not self.stop.is_set() and self.thread.is_alive(),"RSS_monitor_not_live")
        _rss_sample()

    def close(self):
        try:self.check()
        finally:self.stop.set();self.thread.join(timeout=0.25)
        _need(not self.thread.is_alive(),"RSS_monitor_join_refused")


def _identity(head):
    _isolated();_need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"fixed_actual_front_required")
    # The cumulative predecessor verifier requires additional test paths named
    # by strings, not imports. Inherit its COMPLETE qualified identity builder;
    # a generic loaded/static closure alone cannot discover those contracts.
    value=batch.campaign._identity(head)
    own=custody._source_bytes(LANE_ROOT,(SELF_PATH,TEST_PATH,*FROZEN,batch.SELF_PATH,batch.TEST_PATH,batch.campaign.SELF_PATH,batch.campaign.TEST_PATH))
    for name,pin in own.items():_need(_sha(custody._git(LANE_ROOT,"show",head+":"+name))==pin,"source_changed")
    sources={**value["source_sha256"],**own};value={**value,"source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))}
    _current(value);return value


def _current(identity):
    publication._source_identity(identity,required_paths=(SELF_PATH,TEST_PATH,*FROZEN,batch.SELF_PATH,batch.TEST_PATH,batch.campaign.SELF_PATH,batch.campaign.TEST_PATH))
    _need(custody._source_bytes(LANE_ROOT,tuple(identity["source_sha256"]))==identity["source_sha256"]
        and custody._source_bytes(LANE_ROOT,tuple(FROZEN))==FROZEN
        and custody._source_bytes(LANE_ROOT,tuple(source_runner.FROZEN))==source_runner.FROZEN
        and set(custody._internal_source_paths(LANE_ROOT))<=set(identity["source_sha256"]),"source_changed")


def _source_git(identity):
    publication._source_identity(identity)
    for name,pin in identity["source_sha256"].items():
        _need(_sha(custody._git(LANE_ROOT,"show",identity["head"]+":"+name))==pin,"source_changed")


def _check_identity(value,root):
    _need(type(value) is dict and set(value)=={"root","branch","head","clean","source_sha256","source_inventory_sha256"}
        and value["root"]==str(root) and value["branch"]==LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and re.fullmatch(r"[0-9a-f]{40}",value["head"])
        and type(value["source_sha256"]) is dict and {SELF_PATH,TEST_PATH}<=set(value["source_sha256"])
        and 1<=len(value["source_sha256"])<=4096 and all(type(n) is str and len(n)<=512
            and re.fullmatch(r"[A-Za-z0-9_./-]+\.py",n) and not n.startswith("/")
            and all(p not in {"",".",".."} for p in n.split("/")) and type(d) is str and re.fullmatch(r"[0-9a-f]{64}",d)
            for n,d in value["source_sha256"].items())
        and value["source_inventory_sha256"]==_sha(_raw(value["source_sha256"])),"source_identity_refused")
    return value


class _Inputs:
    """Strict, continuously held OLD listing and cumulative metadata; no bodies."""
    def __init__(self,root,*,fixture=False):
        self.root,self.fixture,self.folders,self.lock,self.snap=root,fixture,[],None,None
        try:
            top=self.open(root.joinpath(*directory.ARTIFACT_PARTS));claims=self.open(top.path/"claims")
            runs=self.open(top.path/"runs");run=self.open(runs.path/directory.AUDIT_ID)
            self.lock=os.open("scope.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd)
            self.lockversion=privacy._file_version(os.fstat(self.lock));fcntl.flock(self.lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
            _need(top.read("scope.lock")==directory.LOCK_BYTES and set(os.listdir(top.fd))=={"scope.lock","claims","runs"}
                and set(os.listdir(runs.fd))=={directory.AUDIT_ID} and set(os.listdir(claims.fd))=={directory._claim_name()},"directory_scope_refused")
            names={"reservation.json","contact-validated.json","request-start.json","request-result.json","complete.json","response.bin","response-headers.json","inventory.json"}
            _need(set(os.listdir(run.fd))==names,"directory_run_inventory_refused")
            values={name:run.read(name,cap=directory.MAX_RESPONSE_BYTES) for name in sorted(names)}
            claim=claims.read(directory._claim_name());self.directory_summary=_directory_summary(values,claim,root,fixture)
            self.snap=batch._Snapshot(root,1)
            # Bind EVERY old metadata/claim/header leaf, not old business bodies.
            for folder in (self.snap.run,self.snap.claims):
                for name in sorted(os.listdir(folder.fd)):
                    if name not in {"claims","objects"}:self.snap.read(folder,name)
            complete=_control(self.snap.read(self.snap.run,"complete.json"));plan=_control(self.snap.read(self.snap.run,"plan.json"))
            index=_control(self.snap.read(self.snap.run,"consumed-index.json"))
            for name,pin in CONSUMED_PINS.items():
                _need(fixture or _sha(self.snap.read(self.snap.run,name))==pin,"consumed_external_pin_refused")
            prior=index.get("accessions");_prior(prior)
            _need(fixture or len(prior)==20044,"consumed_count_refused")
            self.prior=prior;self.complete,self.plan=complete,plan
            self.metadata={"directory":self.directory_summary,"prior_accessions":prior,"prior_accessions_sha256":_sha(_raw(prior)),
                "consumed_pins":{n:_sha(self.snap.read(self.snap.run,n)) for n in CONSUMED_PINS},
                "capture_execution_identity":complete["execution_identity"],"planner_receipt":complete["planner_receipt"],
                "metadata_pins":{str(f.path.relative_to(root)):{n:{"sha256":p[0],"bytes":p[1]} for n,p in sorted(f.pins.items())}
                    for f in (*self.folders,*(row[0] for row in self.snap.folders))},
                "old_original_body_bytes_read":0,"unknown_June_archive_memberships_known":False}
            self.check()
        except BaseException:
            self.close();raise

    def open(self,path):
        value=directory._ReadbackDirectory(path);self.folders.append(value);return value

    def check(self):
        for folder in self.folders:folder.check()
        if self.snap:self.snap.recheck()
        if self.lock is not None:
            top=self.folders[0]
            _need(self.lockversion==privacy._file_version(os.fstat(self.lock))==privacy._file_version(
                os.stat("scope.lock",dir_fd=top.fd,follow_symlinks=False)),"inputs_changed")

    def close(self):
        publication._close_all([*self.folders,*([self.snap] if self.snap else [])],None,self.lock,self.lock is not None)
        self.folders=[];self.snap=None;self.lock=None


def _directory_summary(raws,claim,root,fixture):
    values={n:_control(raw) for n,raw in raws.items() if n!="response.bin"}
    reservation=values["reservation.json"];identity=reservation.get("execution_identity")
    directory._source_identity(identity,root=root)
    result=values["request-result.json"];rsha=_sha(raws["reservation.json"])
    _need(raws["reservation.json"]==_raw(directory._reservation(identity,fixture))
        and claim==_raw({"schema":directory.SCHEMA+"/url-claim","method":"GET","url":directory.URL,
            "scope_sha256":_sha(_raw(directory._scope())),"reservation_sha256":rsha})
        and raws["request-start.json"]==_raw({"schema":directory.SCHEMA+"/start","scope_sha256":_sha(_raw(directory._scope())),
            "reservation_sha256":rsha,"claim_sha256":_sha(claim),"attempt":1})
        and raws["contact-validated.json"]==_raw({"schema":directory.SCHEMA+"/contact","reservation_sha256":rsha,
            "contact_present":True,"contact_value_stored_or_hashed":False}),"directory_control_crosslinks_refused")
    inventory=directory.parse_directory_inventory(raws["response.bin"])
    _need(raws["inventory.json"]==_raw(inventory) and result["response_sha256"]==_sha(raws["response.bin"])
        and result["response_bytes"]==len(raws["response.bin"]) and result["inventory_sha256"]==_sha(raws["inventory.json"])
        and result["response_retained"] is result["inventory_qualified"] is True and result["http_status"]==200
        and type(result["transport_invocations"]) is int and result["transport_invocations"]==1
        and result["reservation_sha256"]==rsha and result["claim_sha256"]==_sha(claim)
        and result["start_sha256"]==_sha(raws["request-start.json"])
        and raws["complete.json"]==_raw(directory._complete_control(identity,fixture,rsha,result,_sha(raws["request-result.json"]),True)),"directory_complete_crosslinks_refused")
    headers=values["response-headers.json"]
    _need(type(headers) is dict and set(headers)=={"headers"},"directory_header_control_schema_refused")
    pairs=_headers(headers["headers"])
    _need(raws["response-headers.json"]==_raw({"headers":pairs}),"directory_header_control_schema_refused")
    directory._strict_selected_response(directory.SecHttpResult(200,pairs,raws["response.bin"]),max_bytes=directory.MAX_RESPONSE_BYTES)
    _need(result["response_headers_sha256"]==_sha(_raw(pairs)),"directory_headers_refused")
    if not fixture:
        _need(_sha(raws["complete.json"])==DIRECTORY_REPORT and len(raws["response.bin"])==8274
            and _sha(raws["response.bin"])==DIRECTORY_BODY and _sha(raws["inventory.json"])==DIRECTORY_INVENTORY
            and identity["head"]==DIRECTORY_HEAD and identity["source_inventory_sha256"]==DIRECTORY_SOURCE_INVENTORY
            and len(identity["source_sha256"])==108,"directory_actual_pins_refused")
    matches=[r for r in inventory["entries"] if r["qualified_archive_url"]==URL]
    _need(len(matches)==1 and matches[0]["source_ordinal"]==5 and matches[0]["listed_name"]=="20201007.nc.tar.gz"
        and matches[0]["advertised_size_text"]=="390877 KB","selected_fixed_row_refused")
    return {"complete_sha256":_sha(raws["complete.json"]),"body_sha256":_sha(raws["response.bin"]),
        "inventory_sha256":_sha(raws["inventory.json"]),"original_execution_identity":identity,"selected_row":matches[0]}


def _prior(prior):
    _need(type(prior) is list and len(prior)<=100000 and prior==sorted(set(prior))
        and all(type(v) is str and re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}",v) for v in prior),"prior_accessions_refused")


def _preflight_worker(identity):
    _isolated();source_runner._prove_isolation();_current(identity)
    forms=_forms(identity,False,{"capacity_template_only":True})
    hold=None
    try:
        hold=_Inputs(LANE_ROOT)
        proof,prior=batch.read_actual_predecessor(1,expected_complete_sha256=CONSUMED_PINS["complete.json"],
            expected_plan_sha256=CONSUMED_PINS["plan.json"],expected_index_sha256=CONSUMED_PINS["consumed-index.json"],execution_identity=identity)
        _need(prior==hold.prior and proof["capture_execution_identity"]==hold.complete["execution_identity"],"consumed_metadata_proof_refused")
        hold.check();_current(identity)
        value={"schema":SCHEMA+"/input-preflight","execution_identity":identity,"inputs":hold.metadata,
            "prior_proof":proof,"source_control_capacity_roundtrip":True,"new_requests":0,"contact_reads":0,"namespace_created":False}
        _forms(identity,False,value);value["capacity_proof"]=_capacity_proof(identity,value)
        _forms(identity,False,value);return value
    finally:
        if hold:hold.close()


def _overlap(prior):
    """A complete dispatch ledger is NOT an observed archive membership scan."""
    _prior(prior)
    return {"known_consumed_dispatch_index_count":len(prior),"known_consumed_index_sha256":_sha(_raw(prior)),
        "archive_vs_known_accession_membership":"UNDETERMINED","observed_overlap_count":None,
        "unknown_June_archive_memberships_known":False,"absence_of_membership_evidence_is_not_zero_overlap":True,
        "ALL_members_quarantined_unextracted_unadmitted":True,"later_typed_admission_requires_membership_resolution":True,
        "individual_parent_redispatches":0}


def _inspect(raw,headers,contact,prior,*,fixture):
    _prior(prior)
    private=privacy._contact(contact,observed=not fixture)
    screen=old._TextScreen(private);screen.feed(_raw(headers));screen.feed(b"",final=True)
    descriptor=engine.inspect_gzip_tar_format(raw,privacy_contact=private,fixture_only=fixture)
    # All source/header/body SHA here follows complete finite screening/integrity.
    return {"schema":SCHEMA+"/inspection","format":descriptor,"headers_sha256":_sha(_raw(headers)),
        "overlap":_overlap(prior),"current_contact_finite_screened":True,
        "original_current_contact_equality_attested":False,"authority":_authority()}


def _engine_refusal(error):
    # The exact pinned engine's own phase/code are finite source literals.
    allowed={"gzip-header":{"truncated_fixed_header","invalid_magic","trailing_nonmember_bytes","unsupported_compression_method",
        "reserved_flags_set","truncated_extra_length","truncated_extra_field","header_bytes_bound","optional_text_field_bound_or_truncation",
        "truncated_or_bounded_header_crc","header_crc_mismatch","member_count_bound"},
        "gzip-deflate":{"truncated_stream","invalid_deflate_stream","no_progress","decoded_byte_bound","total_expansion_ratio_bound"},
        "gzip-trailer":{"truncated_trailer","crc32_mismatch","isize_mod32_mismatch","member_expansion_ratio_bound"},
        "privacy":{"explicit_contact_required","contact_or_profile_refused","finite_screen_refused"},
        "metadata":{"descriptor_quota_exceeded","final_descriptor_quota_exceeded"}}
    if type(error) is engine.FeedFormatError and error.phase in allowed and error.code in allowed[error.phase]:
        return {"phase":error.phase,"code":error.code}
    return {"phase":"inspection","code":"finite_privacy_or_format_refused"}


def _worker(role,identity,*,publish=False):
    _isolated();source_runner._prove_isolation()
    memory=_WorkerMemoryGuard()
    try:
        value=_guarded_worker(role,identity,memory)
        if not publish:return value
        # The native worker's fuse remains live during potentially large JSON
        # serialization AND blocked anonymous stdout drain, not just input IO.
        raw=_raw(value);_need(0<len(raw)<MAX_CONTROL,"native_stdout_bound")
        memory.check();sys.stdout.buffer.write(raw+b"\n");sys.stdout.buffer.flush();memory.check()
    finally:memory.close()


def _guarded_worker(role,identity,memory):
    memory.check();_current(identity)
    if role=="preflight":return {"ok":True,"value":_preflight_worker(identity)}
    line=sys.stdin.buffer.readline(MAX_CONTROL+1)
    _need(line.endswith(b"\n") and len(line)<=MAX_CONTROL,"private_stdin_header_bound")
    args=_control(line[:-1]);private=privacy._contact(args.get("contact"),observed=True)
    if role=="readback":
        _need(set(args)=={"contact","report_sha256"},"readback_stdin_schema")
        result=_verify_files(LANE_ROOT,args["report_sha256"],private,fixture=False,current_identity=identity)
        _current(identity);return {"ok":True,"value":result}
    _need(role=="inspect" and set(args)=={"contact","headers","prior","bytes"} and type(args["bytes"]) is int
        and 0<args["bytes"]<=MAX_COMPRESSED,"inspect_stdin_schema")
    raw=sys.stdin.buffer.read(args["bytes"]+1);_need(len(raw)==args["bytes"],"private_stdin_body_bound")
    headers=_headers(args["headers"])
    try:value=_inspect(raw,headers,private,args["prior"],fixture=False)
    except (engine.FeedFormatError,old.ArchiveSampleError,ArchiveFormatError) as error:
        _current(identity);return {"ok":False,"refusal":_engine_refusal(error)}
    _current(identity);return {"ok":True,"value":value}


def _command(role,identity):
    _need(role in {"preflight","inspect","readback"},"fixed_worker_role_required")
    code="import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_sec_feed_archive_format_v3 as m;identity=json.loads("+repr(_raw(identity).decode())+");\ntry:m._worker("+repr(role)+",identity,publish=True)\nexcept Exception:print('{\"ok\":false,\"refusal\":{\"phase\":\"source\",\"code\":\"native_worker_refused\"}}');sys.exit(2)"
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    return ("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)


def _child(role,identity,payload=b""):
    value=old._run_child(_command(role,identity),payload,timeout=WORKER_SECONDS)
    _need(type(value) is dict and type(value.get("ok")) is bool and set(value)==({"ok","value"} if value["ok"] else {"ok","refusal"}),"native_worker_refused")
    return value


def _headers(value):
    _need(type(value) in {list,tuple} and len(value)<=64 and all(type(p) in {list,tuple} and len(p)==2
        and all(type(v) is str for v in p) for p in value) and len(_raw(value))<=16384,"header_bound_refused")
    return tuple(tuple(p) for p in value)


def _claim_name():return _sha(b"GET\0"+URL.encode())+".json"


def _capacity(fd):
    space=os.fstatvfs(fd)
    _need(space.f_bavail*space.f_frsize>=MIN_FREE_BYTES+MAX_COMPRESSED+4*MAX_CONTROL,"disk_reserve_refused")


def _preoutput_capacity(root):
    # No creation: use the deepest existing held no-follow ancestor, then
    # repeat on the final output FD before private contact. A later mount or
    # capacity change is not silently treated as the earlier observation.
    for count in range(len(ARTIFACT_PARTS)-1,-1,-1):
        held=None
        try:held=custody._Chain(root,ARTIFACT_PARTS[:count]);_capacity(held.fd);held.recheck();return
        except FileNotFoundError:continue
        finally:
            if held:held.close()
    raise ArchiveFormatError("disk_reserve_refused")


def _forms(identity,fixture,plan):
    _check_identity(identity,Path(identity["root"]))
    reservation={"schema":SCHEMA+"/reservation","audit_id":AUDIT_ID,"fixture_only":fixture,"registration":registration(),
        "registration_sha256":_sha(_raw(registration())),"execution_identity":identity,"input_preflight_sha256":_sha(_raw(plan))}
    rsha=_sha(_raw(reservation));claim={"schema":SCHEMA+"/URL-claim","method":"GET","url":URL,"reservation_sha256":rsha}
    start={"schema":SCHEMA+"/start","attempt":1,"reservation_sha256":rsha,"claim_sha256":_sha(_raw(claim))}
    forms={"reservation.json":reservation,"input-preflight.json":plan,"claim.json":claim,"request-start.json":start}
    for value in forms.values():_need(_control(_raw(value))==value,"control_capacity_roundtrip_refused")
    # Real identity, exact constructors, worst supported result/descriptor envelope.
    result={"schema":SCHEMA+"/result","reservation_sha256":rsha,"claim_sha256":_sha(_raw(claim)),"start_sha256":_sha(_raw(start)),
        "raw_transport_invocations":1,"remote_request_count_measured":False,"http_status":200,
        "disposition":"whole_archive_retained_format_only_noncanonical","response_retained":True,"compressed_sha256":"0"*64,
        "compressed_bytes":MAX_COMPRESSED,"response_headers_sha256":"0"*64,"inspection_sha256":"0"*64,"inspection_refusal":None,
        "transport_refusal":None,"individual_parent_requests":0,"contact_value_stored_or_hashed":False,
        "format_status":"refused-physical-profile","authority":_authority()}
    _validate_result(result,rsha,_sha(_raw(claim)),_sha(_raw(start)))
    template=_complete(identity,fixture,plan,rsha,result,_sha(_raw(result)))
    _need(_control(_raw(template))==template and len(_raw(template))+engine.FeedFormatLimits().metadata_bytes+4*1024**2<=MAX_CONTROL,"control_capacity_roundtrip_refused")
    return forms


def _capacity_proof(identity,plan):
    """UNPUBLISHED capacity-only schema envelopes, never an archive result.

    Real engine-produced row/gzip layouts are repeated only up to its 32MiB
    total descriptor ceiling, not an impossible 100k fully populated layout.
    The exact 64MiB/3M-node archive codec used by inherited bounded IPC decodes
    the full envelope, in addition to real current roster/provenance controls.
    This proves structural capacity, not semantic source/member observations.
    """
    payload=b"<SUBMISSION>"+b"x"*244+b"<SEC-DOCUMENT></SEC-DOCUMENT>"
    header=bytearray(512);header[:8]=b"probe.nc";header[100:108]=b"0000600\0";header[108:116]=header[116:124]=b"0000000\0"
    header[124:136]=format(len(payload),"011o").encode()+b"\0";header[136:148]=b"00000000000\0";header[148:156]=b"        "
    header[156:157]=b"0";header[257:265]=b"ustar\0"+b"00";header[148:156]=format(sum(header),"06o").encode()+b"\0 "
    raw=engine.zlib.compress(bytes(header)+payload+bytes((-len(payload))%512)+bytes(1024),wbits=31)
    form=engine.inspect_gzip_tar_format(raw,privacy_contact=None,fixture_only=True)
    row=copy.deepcopy(form["tar"]["members"][0]);part=copy.deepcopy(form["gzip_members"][0])
    fixed=copy.deepcopy(form);fixed["tar"]["members"]=[];fixed["gzip_members"]=[]
    unit=len(_raw(row))+len(_raw(part))+24
    count=min(100000,(engine.FeedFormatLimits().metadata_bytes-len(_raw(fixed))-4096)//unit)
    form["tar"]["members"]=[{**row,"ordinal":i+1} for i in range(count)]
    form["gzip_members"]=[{**part,"ordinal":i+1} for i in range(count)]
    form["tar"]["observed_member_count"]=count
    size=len(_raw(form));_need(31*1024**2<=size<=engine.FeedFormatLimits().metadata_bytes,"format_capacity_template_bound")
    inspection={"schema":SCHEMA+"/inspection","format":form,"headers_sha256":"0"*64,
        "overlap":_overlap(plan["inputs"]["prior_accessions"]),"current_contact_finite_screened":True,
        "original_current_contact_equality_attested":False,"authority":_authority()}
    envelope={"ok":True,"value":inspection};wire=_raw(envelope)
    _need(len(wire)<=MAX_CONTROL and _control(wire)==envelope,"descriptor_IPC_capacity_refused")
    forms=_forms(identity,False,plan)
    return {"schema":SCHEMA+"/unpublished-capacity-proof","capacity_only_not_source_observation":True,
        "format_descriptor_bytes":size,"format_member_layout_count":count,"format_gzip_layout_count":count,
        "own_IPC_envelope_bytes":len(wire),"exact_64MiB_3M_node_archive_codec_roundtrip":True,
        "actual_control_sizes":{name:len(_raw(value)) for name,value in forms.items()},"template_published_or_retained":False}


class _Activation:
    def __init__(self,identity,guard):self.identity,self.guard=identity,guard


def _activated(value,identity):
    _need(type(value) is _Activation and _ACTIVATIONS.get(value)==(_raw(identity),id(value.guard))
        and _raw(value.identity)==_raw(identity),"trusted_activation_required")
    value.guard()


class _Dispatch:
    def __init__(self,token,activation,identity,guard,prove,headers):
        _need(token is _TOKEN,"dispatch_context_refused")
        self.activation,self.identity,self.guard,self.prove,self.headers=activation,identity,guard,prove,headers
        self.attempted=False;_DISPATCH[self]=(id(activation),_raw(identity),id(guard),id(prove),_raw(headers))


def _transport(context):
    _need(type(context) is _Dispatch and _DISPATCH.get(context)==(id(context.activation),_raw(context.identity),id(context.guard),id(context.prove),_raw(context.headers))
        and not context.attempted,"dispatch_context_refused")
    _activated(context.activation,context.identity);context.guard();context.prove()
    _need(threading.current_thread() is threading.main_thread() and signal.getitimer(signal.ITIMER_REAL)==(0.,0.),"transport_front_refused")
    previous=signal.getsignal(signal.SIGALRM);connection=None;begun=time.monotonic()
    def expired(*_):raise _AbsoluteDeadline()
    signal.signal(signal.SIGALRM,expired)
    try:
        signal.setitimer(signal.ITIMER_REAL,TRANSPORT_SECONDS);context.attempted=True
        connection=http.client.HTTPSConnection("www.sec.gov",timeout=IDLE_SECONDS)
        connection.request("GET",URL.removeprefix("https://www.sec.gov"),headers=context.headers)
        response=connection.getresponse();pairs=tuple(response.getheaders())
        _need(type(response.status) is int,"http_status_refused")
        if response.status!=200:return directory.SecHttpResult(response.status,pairs,b"")
        mode,size=old._framing(pairs,MAX_COMPRESSED)
        _need(mode!="chunked" or response.chunked is True,"http_chunk_decoder_refused")
        raw=response.read(size if mode=="length" else MAX_COMPRESSED+1)
        _need(mode!="chunked" or response.read(1)==b"" and response.isclosed(),"http_chunk_terminal_refused")
        result=directory.SecHttpResult(200,pairs,raw);old._strict_response(result)
        _need(time.monotonic()-begun<=TRANSPORT_SECONDS,"absolute_transport_deadline");return result
    except _AbsoluteDeadline:raise ArchiveFormatError("absolute_transport_deadline") from None
    finally:
        active=sys.exc_info()[0] is not None;failed=False
        for cleanup in (lambda:signal.setitimer(signal.ITIMER_REAL,0),lambda:signal.signal(signal.SIGALRM,previous),*((connection.close,) if connection else ())):
            try:cleanup()
            except BaseException:failed=True
        if failed and not active:raise ArchiveFormatError("transport_cleanup_refused")


def _complete(identity,fixture,plan,rsha,result,result_sha):
    return {"schema":SCHEMA+"/complete","audit_id":AUDIT_ID,"fixture_only":fixture,"execution_identity":identity,
        "registration_sha256":_sha(_raw(registration())),"input_preflight_sha256":_sha(_raw(plan)),"reservation_sha256":rsha,
        "result_sha256":result_sha,"result":result,"authority":_authority()}


def _validate_result(value,rsha,csha,ssha):
    keys={"schema","reservation_sha256","claim_sha256","start_sha256","raw_transport_invocations","remote_request_count_measured",
        "http_status","disposition","response_retained","compressed_sha256","compressed_bytes","response_headers_sha256",
        "inspection_sha256","inspection_refusal","transport_refusal","individual_parent_requests","contact_value_stored_or_hashed","format_status","authority"}
    _need(type(value) is dict and set(value)==keys and value["schema"]==SCHEMA+"/result"
        and (value["reservation_sha256"],value["claim_sha256"],value["start_sha256"])==(rsha,csha,ssha)
        and type(value["raw_transport_invocations"]) is int and value["raw_transport_invocations"]==1
        and type(value["response_retained"]) is bool and value["remote_request_count_measured"] is False
        and value["contact_value_stored_or_hashed"] is False and type(value["individual_parent_requests"]) is int
        and value["individual_parent_requests"]==0 and value["authority"]==_authority(),"result_schema_refused")
    _need(value["http_status"] is None or type(value["http_status"]) is int and 100<=value["http_status"]<=599,"result_status_refused")
    if value["response_retained"]:
        _need(value["http_status"]==200 and type(value["compressed_bytes"]) is int and 0<value["compressed_bytes"]<=MAX_COMPRESSED
            and all(type(value[k]) is str and re.fullmatch(r"[0-9a-f]{64}",value[k]) for k in ("compressed_sha256","response_headers_sha256","inspection_sha256"))
            and value["inspection_refusal"] is value["transport_refusal"] is None
            and value["disposition"]=="whole_archive_retained_format_only_noncanonical"
            and value["format_status"] in {"physical-framing-complete","refused-physical-profile"},"result_retained_refused")
    else:
        _need(all(value[k] is None for k in ("compressed_sha256","compressed_bytes","response_headers_sha256","inspection_sha256","format_status")),"result_unretained_refused")
        if value["http_status"] is None:
            _need(value["disposition"]=="ambiguous_transport_failure_no_retry" and value["inspection_refusal"] is None
                and type(value["transport_refusal"]) is dict and value["transport_refusal"] in
                    ({"phase":"transport","code":c} for c in ("absolute_transport_deadline","idle_timeout","ambiguous_transport")),"result_transport_refused")
        elif value["http_status"]!=200:
            _need(value["disposition"]=="non200_body_unread_no_retry" and value["inspection_refusal"] is value["transport_refusal"] is None,"result_non200_refused")
        else:
            refusal=value["inspection_refusal"]
            _need(value["disposition"]=="privacy_integrity_or_descriptor_refused_no_retention_no_retry" and value["transport_refusal"] is None
                and type(refusal) is dict and set(refusal)=={"phase","code"}
                and (refusal=={"phase":"inspection","code":"finite_privacy_or_format_refused"} or
                    _engine_refusal(engine.FeedFormatError(refusal["phase"],refusal["code"]))==refusal),"result_inspection_refused")
    return value


def _validate_inspection(value,body,headers,prior,*,fixture):
    _need(type(value) is dict and set(value)=={"schema","format","headers_sha256","overlap","current_contact_finite_screened","original_current_contact_equality_attested","authority"}
        and value["schema"]==SCHEMA+"/inspection" and value["current_contact_finite_screened"] is True
        and value["original_current_contact_equality_attested"] is False and value["headers_sha256"]==_sha(_raw(headers))
        and value["authority"]==_authority(),"inspection_schema_refused")
    form=value["format"]
    _need(type(form) is dict and form.get("schema")==engine.SCHEMA and form.get("finite_privacy_screened") is True
        and form.get("fixture_only") is fixture and form.get("compressed_bytes")==len(body)
        and form.get("compressed_sha256")==_sha(body) and form.get("canonical_admitted") is False
        and form.get("backtesting_ready") is False and form.get("files_read_written_or_extracted")==0
        and form.get("privacy_source_sha256")==engine.PRIVACY_SOURCE_SHA256 and form.get("all_compressed_bytes_accounted") is True
        and form.get("gzip_concatenation_supported") is True and form.get("source_authenticated") is False
        and form.get("XML_or_financial_fields_parsed") is False and form.get("acceptance_or_PIT_verified") is False,"inspection_body_binding_refused")
    _need(value["overlap"]==_overlap(prior),"inspection_overlap_refused")
    _control(_raw(value));return value


def _run(*,root,identity,plan,contact,transport,fixture,guard,activation=None,inspector=None,hold=None):
    if fixture:
        publication._fixture_root(root);publication._native_fixture_denial()
        _need(callable(transport) and transport is not _transport and contact not in {contact_io._stdin_contact,contact_io._getpass_contact},"invented_callbacks_required")
    else:
        _need(root==LANE_ROOT and transport is _transport and contact is contact_io._stdin_contact and inspector is None and type(hold) is _Inputs,"fixed_actual_front_required")
        _activated(activation,identity)
    _prior(plan["inputs"]["prior_accessions"]);forms=_forms(identity,fixture,plan);guard()
    if hold:hold.check();_need(hold.metadata==plan["inputs"],"inputs_changed")
    phase="capacity";folders=[];lock=None;locked=False;fresh=None
    try:
        _preoutput_capacity(root);phase="namespace"
        try:fresh=custody._Chain(root,ARTIFACT_PARTS,create=True,exclusive_last=True)
        except custody.ArchiveAssessmentRunnerError as exc:
            if exc.args==("output_cannot_resume_or_overwrite",):raise ArchiveFormatError("fresh_namespace_already_exists") from None
            raise
        top=old._Output(root.joinpath(*ARTIFACT_PARTS));folders.append(top)
        claims=old._Output(top.path/"claims",create=True);folders.append(claims)
        runs=old._Output(top.path/"runs",create=True);folders.append(runs)
        top.publish("scope.lock",LOCK_BYTES);lock=os.open("scope.lock",os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True;version=old._version(os.fstat(lock))
        phase="capacity";_capacity(top.fd)
        os.mkdir(AUDIT_ID,0o700,dir_fd=runs.fd);os.fsync(runs.fd);run=old._Output(runs.path/AUDIT_ID);folders.append(run)
        names=set();claimnames=set()
        def check():
            guard();fresh.recheck()
            if hold:hold.check();_need(hold.metadata==plan["inputs"],"inputs_changed")
            for folder in folders:folder.check()
            _need(version==old._version(os.fstat(lock))==old._version(os.stat("scope.lock",dir_fd=top.fd,follow_symlinks=False)),"output_lock_changed")
            _need(set(os.listdir(top.fd))=={"scope.lock","claims","runs"} and set(os.listdir(runs.fd))=={AUDIT_ID}
                and set(os.listdir(run.fd))==names and set(os.listdir(claims.fd))==claimnames,"output_inventory_changed")
        def publish(name,value):
            pin=run.publish(name,_raw(value));names.add(name);check();return pin
        phase="reservation";rsha=publish("reservation.json",forms["reservation.json"]);publish("input-preflight.json",plan)
        phase="contact";private=privacy._contact(contact(),observed=not fixture);old._contact_needles(private)
        publish("contact-validated.json",{"schema":SCHEMA+"/contact","reservation_sha256":rsha,"contact_present":True,"contact_value_stored_or_hashed":False})
        phase="claim";csha=claims.publish(_claim_name(),_raw(forms["claim.json"]));claimnames.add(_claim_name());check()
        phase="start";ssha=publish("request-start.json",forms["request-start.json"])
        def prove():
            check();_need(claims.read(_claim_name())==_raw(forms["claim.json"]) and run.read("request-start.json")==_raw(forms["request-start.json"]),"dispatch_context_refused")
        headers={"User-Agent":"InsiderBuyingResearch-FeedArchiveFormat/3.0 ("+private+")","Accept":"application/gzip","Accept-Encoding":"identity","Connection":"close"}
        phase="transport";response=None;context=None;invocations=0;transport_refusal=None
        try:
            if fixture:prove();invocations=1;response=transport(URL,headers,MAX_COMPRESSED)
            else:context=_Dispatch(_TOKEN,activation,identity,guard,prove,headers);response=_transport(context);invocations=int(context.attempted)
        except Exception as error:
            if not fixture:_need(context is not None and context.attempted,"transport_front_refused");invocations=1
            code="absolute_transport_deadline" if type(error) is ArchiveFormatError and error.args==("absolute_transport_deadline",) else "idle_timeout" if isinstance(error,TimeoutError) else "ambiguous_transport"
            transport_refusal={"phase":"transport","code":code}
        check();status=None;inspection=None;retained=False;refusal=None;bodysha=bodybytes=hsha=isha=None
        disposition="ambiguous_transport_failure_no_retry"
        if response is not None:
            _need(type(response) is directory.SecHttpResult and type(response.status) is int and 100<=response.status<=599,"response_metadata_refused")
            status=response.status;disposition="non200_body_unread_no_retry"
            if status==200:
                phase="inspection"
                try:
                    body=old._strict_response(response);pairs=_headers(response.headers)
                    if fixture:inspection=(inspector or _inspect)(body,pairs,private,plan["inputs"]["prior_accessions"],fixture=True)
                    else:
                        envelope=_raw({"contact":private,"headers":pairs,"prior":plan["inputs"]["prior_accessions"],"bytes":len(body)})+b"\n"
                        reply=_child("inspect",identity,envelope+body)
                        if not reply["ok"]:refusal=reply["refusal"];raise ArchiveFormatError("native_inspection_refused")
                        inspection=reply["value"]
                    _validate_inspection(inspection,body,pairs,plan["inputs"]["prior_accessions"],fixture=fixture)
                except Exception as error:
                    refusal=refusal or _engine_refusal(error);disposition="privacy_integrity_or_descriptor_refused_no_retention_no_retry"
                else:
                    phase="publication";bodysha=run.publish("response.gz",body,cap=MAX_COMPRESSED);names.add("response.gz");check()
                    bodybytes=len(body);hsha=_sha(_raw(pairs));publish("response-headers.json",{"headers":pairs});isha=publish("inspection.json",inspection);retained=True
                    disposition="whole_archive_retained_format_only_noncanonical"
        result={"schema":SCHEMA+"/result","reservation_sha256":rsha,"claim_sha256":csha,"start_sha256":ssha,
            "raw_transport_invocations":invocations,"remote_request_count_measured":False,"http_status":status,"disposition":disposition,
            "response_retained":retained,"compressed_sha256":bodysha,"compressed_bytes":bodybytes,"response_headers_sha256":hsha,
            "inspection_sha256":isha,"inspection_refusal":refusal,"transport_refusal":transport_refusal,
            "individual_parent_requests":0,"contact_value_stored_or_hashed":False,
            "format_status":inspection["format"]["tar"]["status"] if retained else None,"authority":_authority()}
        phase="complete";_validate_result(result,rsha,csha,ssha);resultsha=publish("request-result.json",result);complete=_complete(identity,fixture,plan,rsha,result,resultsha)
        report=publish("complete.json",complete);phase="final";check()
        return {"schema":SCHEMA+"/public","audit_id":AUDIT_ID,"complete_sha256":report,"result":result,"authority":_authority()}
    except Exception as error:
        classified=_classified(phase,error);value=ArchiveFormatError(classified["code"]);value.phase=classified["phase"];raise value from None
    finally:
        primary=sys.exc_info()[0] is not None
        try:publication._close_all(folders,fresh,lock,locked)
        except Exception as error:
            if not primary:raise _at("cleanup",error) from None


def _invented(*,root,transport,contact=lambda:"invented@unit.test",prior=(),guard=lambda:None,inspector=None):
    sources={SELF_PATH:"a"*64,TEST_PATH:"b"*64};identity={"root":str(root),"branch":LANE_BRANCH,"head":"a"*40,"clean":True,
        "source_sha256":sources,"source_inventory_sha256":_sha(_raw(sources))}
    plan={"schema":SCHEMA+"/input-preflight","execution_identity":identity,"inputs":{"prior_accessions":sorted(set(prior)),"fixture_only":True}}
    return _run(root=Path(root),identity=identity,plan=plan,contact=contact,transport=transport,fixture=True,guard=guard,inspector=inspector)


def _verify_files(root,pin,private,*,fixture,current_identity=None):
    if fixture:publication._fixture_root(root);publication._native_fixture_denial()
    else:_isolated();source_runner._prove_isolation();_current(current_identity);_need(root==LANE_ROOT,"fixed_actual_front_required")
    _need(type(pin) is str and re.fullmatch(r"[0-9a-f]{64}",pin),"readback_pin_refused")
    folders=[];lock=None;inputs=None
    try:
        if not fixture:inputs=_Inputs(root)
        def opened(path):
            value=directory._ReadbackDirectory(path);folders.append(value);return value
        top=opened(root.joinpath(*ARTIFACT_PARTS));claims=opened(top.path/"claims");runs=opened(top.path/"runs");run=opened(runs.path/AUDIT_ID)
        lock=os.open("scope.lock",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=top.fd);version=privacy._file_version(os.fstat(lock))
        fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        _need(top.read("scope.lock")==LOCK_BYTES and set(os.listdir(top.fd))=={"scope.lock","claims","runs"}
            and set(os.listdir(runs.fd))=={AUDIT_ID} and set(os.listdir(claims.fd))=={_claim_name()},"readback_crosslinks_refused")
        complete_raw=run.read("complete.json",cap=MAX_CONTROL);_need(_sha(complete_raw)==pin,"readback_pin_refused")
        complete=_control(complete_raw);identity=complete["execution_identity"];plan=_control(run.read("input-preflight.json",cap=MAX_CONTROL))
        if inputs:_need(inputs.metadata==plan["inputs"],"inputs_changed")
        _check_identity(identity,root)
        forms=_forms(identity,fixture,plan);rsha=_sha(_raw(forms["reservation.json"]));result_raw=run.read("request-result.json",cap=MAX_CONTROL);result=_control(result_raw)
        _validate_result(result,rsha,_sha(_raw(forms["claim.json"])),_sha(_raw(forms["request-start.json"])))
        _need(plan["execution_identity"]==identity and run.read("reservation.json",cap=MAX_CONTROL)==_raw(forms["reservation.json"])
            and claims.read(_claim_name())==_raw(forms["claim.json"]) and run.read("request-start.json")==_raw(forms["request-start.json"])
            and run.read("contact-validated.json")==_raw({"schema":SCHEMA+"/contact","reservation_sha256":rsha,"contact_present":True,"contact_value_stored_or_hashed":False})
            and complete_raw==_raw(_complete(identity,fixture,plan,rsha,result,_sha(result_raw)))
            and result["reservation_sha256"]==rsha and result["claim_sha256"]==_sha(_raw(forms["claim.json"]))
            and result["start_sha256"]==_sha(_raw(forms["request-start.json"])) and type(result["raw_transport_invocations"]) is int
            and result["raw_transport_invocations"]==1 and result["authority"]==_authority(),"readback_crosslinks_refused")
        names={"reservation.json","input-preflight.json","request-start.json","request-result.json","contact-validated.json","complete.json"}
        if result["response_retained"] is True:
            names|={"response.gz","response-headers.json","inspection.json"}
            # Strict versions before first bytes; defer RAW body/header hashes
            # until fresh-current-contact rescreening and engine replay succeed.
            run._versions();body=run.tree.read("response.gz",cap=MAX_COMPRESSED);hraw=run.tree.read("response-headers.json",cap=MAX_CONTROL);run._versions()
            header_control=_control(hraw)
            _need(set(header_control)=={"headers"},"readback_crosslinks_refused")
            headers=_headers(header_control["headers"])
            _need(hraw==_raw({"headers":headers}),"readback_crosslinks_refused")
            old._strict_response(directory.SecHttpResult(200,headers,body))
            observed=_inspect(body,headers,private,plan["inputs"]["prior_accessions"],fixture=fixture)
            expected=run.read("inspection.json",cap=MAX_CONTROL)
            _need(_raw(observed)==expected and _sha(expected)==result["inspection_sha256"] and observed["format"]["compressed_sha256"]==result["compressed_sha256"]
                and len(body)==result["compressed_bytes"] and observed["headers_sha256"]==result["response_headers_sha256"]
                and result["http_status"]==200 and result["disposition"]=="whole_archive_retained_format_only_noncanonical"
                and result["inspection_refusal"] is None and result["format_status"]==observed["format"]["tar"]["status"],"readback_engine_differs")
            _need(run.read("response.gz",cap=MAX_COMPRESSED)==body and run.read("response-headers.json",cap=MAX_CONTROL)==hraw,"readback_engine_differs")
        else:
            _need(result["response_retained"] is False and all(result[k] is None for k in ("compressed_sha256","compressed_bytes","response_headers_sha256","inspection_sha256","format_status")),"readback_crosslinks_refused")
        _need(set(os.listdir(run.fd))==names,"readback_crosslinks_refused")
        for folder in folders:folder.check()
        if inputs:inputs.check();_need(inputs.metadata==plan["inputs"],"inputs_changed")
        _need(version==privacy._file_version(os.fstat(lock))==privacy._file_version(os.stat("scope.lock",dir_fd=top.fd,follow_symlinks=False)),"inputs_changed")
        return {"schema":SCHEMA+"/readback","complete_sha256":pin,"result":result,"producer_execution_identity":identity,
            "original_input_plan":plan,"current_contact_rescreen_and_engine_replay":result["response_retained"],
            "original_current_contact_equality_attested":False,"original_contact_screen_replayed":False,"new_provider_requests":0,"authority":_authority()}
    finally:publication._close_all([*folders,*([inputs] if inputs else [])],None,lock,lock is not None)


def _parent_plan_proofs(plan):
    inputs=plan["inputs"];_source_git(inputs["directory"]["original_execution_identity"])
    _source_git(inputs["capture_execution_identity"]);batch.campaign.verify_plan_producer(inputs["planner_receipt"])


def run_actual(expected_head):
    phase="source";hold=None;activation=None
    try:
        identity=_identity(expected_head);phase="native_preflight"
        reply=_child("preflight",identity);_need(reply["ok"],"native_source_preflight_refused");plan=reply["value"]
        phase="inputs";_parent_plan_proofs(plan)
        def guard():_need(_identity(expected_head)==identity,"source_changed")
        guard()
        hold=_Inputs(LANE_ROOT);_need(hold.metadata==plan["inputs"],"inputs_changed")
        activation=_Activation(identity,guard);_ACTIVATIONS[activation]=(_raw(identity),id(guard))
        return _run(root=LANE_ROOT,identity=identity,plan=plan,contact=contact_io._stdin_contact,transport=_transport,
            fixture=False,guard=guard,activation=activation,hold=hold)
    except Exception as error:raise _at(phase,error) from None
    finally:
        primary=sys.exc_info()[0] is not None
        if activation:_ACTIVATIONS.pop(activation,None)
        if hold:
            try:hold.close()
            except Exception as error:
                if not primary:raise _at("cleanup",error) from None


def verify_actual(expected_head,pin):
    phase="source"
    try:
        identity=_identity(expected_head);phase="native_preflight"
        preflight=_child("preflight",identity);_need(preflight["ok"],"native_source_preflight_refused")
        phase="inputs";_parent_plan_proofs(preflight["value"])
        phase="contact";private=privacy._contact(contact_io._stdin_contact(),observed=True)
        phase="readback";reply=_child("readback",identity,_raw({"contact":private,"report_sha256":pin})+b"\n");_need(reply["ok"],"native_worker_refused")
        value=reply["value"];_source_git(value["producer_execution_identity"]);_parent_plan_proofs(value["original_input_plan"])
        _need({**value["original_input_plan"],"execution_identity":identity}==preflight["value"],"inputs_changed")
        phase="final";_need(_identity(expected_head)==identity,"source_changed")
        return {k:v for k,v in value.items() if k not in {"producer_execution_identity","original_input_plan"}}
    except Exception as error:raise _at(phase,error) from None


class _Parser(argparse.ArgumentParser):
    def error(self,message):raise ArchiveFormatError("private_arguments_refused")


def main(argv=None):
    saved=contact_io._protect_stdin_echo()
    try:
        parser=_Parser();parser.add_argument("--expected-head",required=True);parser.add_argument("--verify-complete")
        args=parser.parse_args(argv)
        value=verify_actual(args.expected_head,args.verify_complete) if args.verify_complete else run_actual(args.expected_head)
        print(_raw(value).decode());return 0 if value["result"]["response_retained"] else 2
    except Exception as error:
        code=_classified(getattr(error,"phase","arguments"),error)
        print(_raw({"schema":SCHEMA+"/refusal",**code,"preserve_claims_and_namespace":True}).decode());return 2
    finally:contact_io._restore_stdin_echo(saved)


if __name__=="__main__":raise SystemExit(main())
