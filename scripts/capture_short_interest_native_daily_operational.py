"""Prospective fixed daily source controller; no active source/key invocation.

Root must pin code/archive/spent-proof/calendar/output paths and commit the
registration before composition. This module never monkeypatches producer
globals or hides actualremote advancement in a time-based cache.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import stat
import threading
import subprocess
import inspect
from data.hashing import canonical_json,hash_bytes,hash_payload
from scripts import short_interest_lane_batch_guard as lane
from scripts import continue_short_interest_native_identity as custody
from scripts.short_interest_keychain import read_named_keychain
from scripts.qualify_sharadar_companion import _http,_utc_now
from scripts.capture_short_interest_native_grouped_market import shared_calendar_source
from research.short_interest_etf import sharadar_securities_master as master
from research.short_interest_etf import native_daily_active_reference as daily

OUTPUT_DIRECTORY="/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest/artifacts/short_interest/private/native_daily_active/daily-029173c8-v1"
SOURCE_ARCHIVE_PATH="/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest/artifacts/short_interest/sharadar_securities_master/sharadar-master-20261012T055800Z/attempt-08.raw"
SOURCE_ARCHIVE_SHA256="da2204eab9c20bd9c5203d52238c2ad75878cb63733c78a4febca11e6299e572"
SOURCE_ANCESTOR="a5ac4c22499e13f04776a8fa145fd3dba72bc383"
CALENDAR_SHA256="a22344dd29a80869f8c816e71dd5526f9872754d2a6f595131e93a3565228c6e"
SPENT_SOURCE_PINS={"/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest/artifacts/short_interest/sharadar_securities_master/sharadar-master-20261012T055800Z/protocol.json":"531654b15daff36d65856c52142f0fc94e3d0cea6e0e18ea444cd8525c9e1c55","/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest/artifacts/short_interest/sharadar_securities_master/sharadar-master-20261012T055800Z/started.json":"4e96385d84c5e45ed6afeb250804b5821611145d0c05063011a7c737c911cb6c","/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest/artifacts/short_interest/sharadar_securities_master/sharadar-master-20261012T055800Z/refused.json":"0b91937d40d1f932d02e25e821a5d37f8590bf3d6e6663a2790d48bedbaf1089","/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest/artifacts/short_interest/sharadar_securities_master/sharadar-master-20261012T055800Z/attempt-08.received.json":"bebb6bb6921dea43124d3b2f2186a55de434c596e225e4271ec38a13b27476bf","/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest/artifacts/short_interest/sharadar_securities_master/budget-a14e6d22c9fd9b1e5edbd3dae8b41f2380648b8b00710bf8ca2865a4884bc44c.json":"76170777b03b8a1e553777494ffa564c817975f5f4f0b15fffea0651066dcdbd"}
GLOBAL_CLAIM_NAME="daily-active-029173c8-v1.budget.json"
PROTOCOL_SHA256="d9bfd50ae4f9ad44c939832482066683b98304c160893b1b914bfcb138156126"

# Closed local import graph, including the dynamic shared-calendar import.
# Paths, not hashes or a future committed HEAD. Root independently checks this
# finite closure before calculating its external complete-current manifest.
REQUIRED_CODE_PATHS=(
    "data/__init__.py","data/exchange_calendar.py","data/financial_primitives.py","data/hashing.py",
    "ml/__init__.py","ml/immutable_io.py",
    "research/__init__.py","research/short_interest_etf/__init__.py",
    "research/short_interest_etf/availability.py","research/short_interest_etf/contracts.py",
    "research/short_interest_etf/finra_source_qualification.py","research/short_interest_etf/massive_action_supplement.py",
    "research/short_interest_etf/massive_class_denominator.py","research/short_interest_etf/native_daily_active_reference.py",
    "research/short_interest_etf/native_daily_recovery.py",
    "research/short_interest_etf/native_dated_class_reference.py","research/short_interest_etf/native_dated_identity.py",
    "research/short_interest_etf/native_grouped_market_source.py","research/short_interest_etf/native_listed_venue_namespace.py",
    "research/short_interest_etf/native_parallel_count_contract.py","research/short_interest_etf/native_population_class_matrix.py",
    "research/short_interest_etf/preregistration.py","research/short_interest_etf/sharadar_actual_input_binding.py",
    "research/short_interest_etf/sharadar_companion_qualification.py","research/short_interest_etf/sharadar_master_segments.py",
    "research/short_interest_etf/sharadar_native_master_index.py","research/short_interest_etf/sharadar_native_observations.py",
    "research/short_interest_etf/sharadar_securities_master.py","scripts/build_short_interest_native_master_offline.py",
    "scripts/capture_short_interest_native_daily_active.py","scripts/capture_short_interest_native_grouped_market.py",
    "scripts/capture_short_interest_native_identity.py","scripts/capture_short_interest_native_population.py",
    "scripts/capture_short_interest_securities_master.py","scripts/continue_short_interest_native_identity.py",
    "scripts/finalize_short_interest_master_offline.py","scripts/load_short_interest_native_class_matrix.py",
    "scripts/qualify_finra_short_interest.py","scripts/qualify_sharadar_companion.py",
    "scripts/qualify_short_interest_action_supplement.py","scripts/short_interest_keychain.py",
    "scripts/short_interest_lane_batch_guard.py")

def required_code_paths():
    return tuple(sorted((*[str(lane.ROOT/path) for path in REQUIRED_CODE_PATHS],str(Path(__file__).absolute()))))

class OperationalRefusal(ValueError):
    pass
def require(value,reason):
    if not value:
        raise OperationalRefusal(reason)

def protocol():
    return {"schema":"si-daily-active-operational-proposal-v1","output":OUTPUT_DIRECTORY,
        "global_claim":GLOBAL_CLAIM_NAME,"source_archive":SOURCE_ARCHIVE_PATH,"source_archive_sha256":SOURCE_ARCHIVE_SHA256,
        "source_ancestor":SOURCE_ANCESTOR,"spent_source_pins":SPENT_SOURCE_PINS,"calendar_sha256":CALENDAR_SHA256,
        # The exclusive budget is stable across code/head/time registrations.
        # Current complete code pins include this controller externally; no
        # self-SHA or future-HEAD literal is part of its own frozen bytes.
        "runtime_registration":"external_exact_HEAD_remote_complete_code_manifest",
        "code_manifest_policy":"closed_transitive_local_paths_and_controller_v1_not_self_SHA",
        "maximum_requests":daily.MAXIMUM_REQUESTS,"maximum_total_bytes":daily.MAXIMUM_TOTAL_BYTES,
        "maximum_day_chains":8,"maximum_HTTP_starts_per_remote_batch":8,
        "remote":"initial_each_8_started_HTTP_boundary_final_not_timed_or_each_chunk",
        "local":"fresh_two_Git_physical_root_branch_HEAD_status_before_every_START_and_publication",
        "sources":"original_owned_no_link_FDs_and_SHA_read_once_then_inode_stamp_per_slot_no_recapture",
        "publication":"registered_day_page_prefix_create_exclusive_private_0700_0600",
        "remote_drift":"stop_new_HTTP_retain_started_raw_closed_negative_receipts_local_FD_only_no_success",
        "round_close":"inventory_provisional_until_post_publication_drained_fresh_remote_closed_receipt",
        "key":"existing_named_massive_login_Keychain_only_no_inferred_environment_fallback",
        "automatic_retries":0,"source_only":True,"outcome_looks":0,"qc_attempts":0}

class RuntimeRegistration:
    """Root-supplied current code manifest; never a source-admission factory."""
    __slots__=("_anchor","_identity")
    def __init__(self,*,head,remote,code_manifest):
        require(all(type(value) is str and re.fullmatch(r"[0-9a-f]{40}",value)
            for value in (head,remote)) and type(code_manifest) is dict and bool(code_manifest),"exact_runtime_registration_required")
        pins=[]
        for path,sha in sorted(code_manifest.items()):
            require(type(path) is str and Path(path).is_absolute() and Path(path).is_relative_to(lane.ROOT)
                and type(sha) is str and re.fullmatch(r"[0-9a-f]{64}",sha),"exact_current_code_manifest_required")
            pins.append((path,sha))
        manifest=tuple(pins)
        require(tuple(path for path,_ in manifest)==required_code_paths(),"exact_complete_current_code_manifest_membership")
        self._anchor=self._identity=(head,remote,manifest,hash_payload(dict(manifest)))
    def binding(self):
        require(type(self) is RuntimeRegistration and self._anchor is self._identity
            and type(self._anchor) is tuple and len(self._anchor)==4,"runtime_registration_changed")
        require(tuple(path for path,_ in self._anchor[2])==required_code_paths(),"exact_complete_current_code_manifest_membership")
        return self._anchor
    def marker(self):
        head,remote,_,sha=self.binding()
        return {"registered_head":head,"registered_remote":remote,"complete_current_code_manifest_sha256":sha}
    def payload(self):
        value=self.marker(); value["complete_current_code_manifest"]=dict(self.binding()[2]); return value

class HeldPinnedFile:
    """One immutable file read; cheap retained FD/named-inode guards afterward."""
    __slots__=("_path","_fd","_stamp","_raw","_sha","_parent_fd","_parent_stamp","_private","_anchor","_identity")
    @staticmethod
    def _state(info):
        return info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns
    @staticmethod
    def _parent_state(info):
        return info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink
    def __init__(self,path,sha,maximum,*,private=True,boundary=lambda:None):
        boundary()
        require(type(path) is Path or isinstance(path,Path),"exact_pinned_path")
        require(path.is_absolute() and path.resolve()==path and type(sha) is str
            and re.fullmatch(r"[0-9a-f]{64}",sha) and type(maximum) is int and maximum>0,"registered_pin_required")
        require(type(private) is bool,"source_protection_mode_type")
        parent_fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        fd=None
        try:
            parent=os.fstat(parent_fd); named_parent=path.parent.lstat()
            require(stat.S_ISDIR(parent.st_mode) and parent.st_uid==os.getuid() and parent.st_nlink>=1
                and (not private or stat.S_IMODE(parent.st_mode)==0o700)
                and self._parent_state(parent)==self._parent_state(named_parent),"source_parent_protection")
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            info=os.fstat(fd); named=path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
                and stat.S_IMODE(info.st_mode)==(0o600 if private else 0o644)
                and self._state(info)==self._state(named) and info.st_size<=maximum,"source_file_protection")
            chunks=[]; size=0
            while size<info.st_size:
                require(self._parent_state(os.fstat(parent_fd))==self._parent_state(path.parent.lstat())==self._parent_state(parent),
                        "source_parent_changed_during_read")
                require(self._state(os.fstat(fd))==self._state(path.lstat())==self._state(info),"source_changed_during_read")
                part=os.read(fd,min(64*1024,info.st_size-size)); require(bool(part),"source_short_read")
                chunks.append(part); size+=len(part)
            raw=b"".join(chunks)
            require(hash_bytes(raw)==sha,"registered_source_bytes_changed")
            boundary()
            values=(path,fd,self._state(info),raw,sha,parent_fd,self._parent_state(parent),private)
            for name,value in zip(("_path","_fd","_stamp","_raw","_sha","_parent_fd","_parent_stamp","_private"),values): setattr(self,name,value)
            self._anchor=self._identity=values
            self.check()
        except BaseException:
            if fd is not None: os.close(fd)
            os.close(parent_fd); raise
    def check(self):
        require(self._anchor is self._identity and type(self._anchor) is tuple and len(self._anchor)==8
            and all(getattr(self,name) is value for name,value in zip(
                ("_path","_fd","_stamp","_raw","_sha","_parent_fd","_parent_stamp","_private"),self._anchor)),"source_handle_changed")
        parent=os.fstat(self._parent_fd); named_parent=self._path.parent.lstat()
        require(stat.S_ISDIR(parent.st_mode) and parent.st_uid==os.getuid() and parent.st_nlink>=1
            and (not self._private or stat.S_IMODE(parent.st_mode)==0o700)
            and self._path.parent.resolve()==self._path.parent
            and self._parent_state(parent)==self._parent_state(named_parent)==self._parent_stamp,"source_owned_parent_changed")
        require(self._path.resolve()==self._path and self._state(os.fstat(self._fd))==self._state(self._path.lstat())==self._stamp,
                "source_owned_inode_changed")
    def bytes(self): self.check(); return self._raw
    def close(self):
        try: os.close(self._fd)
        finally: os.close(self._parent_fd)

class DailyHTTPBatchGate:
    """Exact per-thread source attempt slots; remote proof lasts <=8 starts."""
    __slots__=("guard","plan","source_check","index","registration","_anchor","_identity","_lock","_slots","_authorizations","_invocations","_halted","_closed_days","_known_days","_attempts","_qualified","_raw_receipts","_published_raw")
    def __init__(self,guard,plan,source_check,index=None,registration=None):
        require(type(guard) is lane.LaneGuard and type(plan) is daily.DailyActiveReferencePlan,"exact_daily_lane_plan_required")
        self.guard,self.plan,self.source_check=guard,plan,source_check
        self.index=index
        require(registration is None or type(registration) is RuntimeRegistration,"exact_registration_type")
        if registration is not None:
            require(guard.binding()[1:3]==registration.binding()[:2],"registration_lane_guard_mismatch")
        self.registration=registration
        self._anchor=self._identity=(guard,plan,source_check,index,registration)
        self._lock=threading.RLock(); self._slots={}; self._authorizations=0; self._invocations=0; self._halted=False
        self._closed_days=set(); self._known_days=set()
        self._attempts=set(); self._qualified={}; self._raw_receipts={}; self._published_raw={}
    def local_check(self,*unused):
        require(self._anchor is self._identity and all(getattr(self,name) is value for name,value in zip(
            ("guard","plan","source_check","index","registration"),self._anchor)),"daily_controller_binding_changed")
        if self.registration is not None: self.registration.binding()
        self.guard.check(); self.plan._guard(); self.source_check()
    def initial(self):
        self.local_check()
        try: self.guard.refresh()
        except (lane.LaneBatchRefusal,OSError):
            self._halted=True; raise OperationalRefusal("matching_remote_advanced_or_ambiguous") from None
    def register_start(self,name,value):
        with self._lock:
            self.local_check()
            require(not self._halted,"halted_no_new_started_slots")
            match=re.fullmatch(r"day-([0-9]{4})-page-([0-9]{2})\.started\.json",name)
            require(match is not None and type(value) is dict,"exact_started_prefix_required")
            day,page=map(int,match.groups()); url=value.get("request",{}).get("url")
            require(type(value.get("attempt")) is int and 1<=value["attempt"]<=daily.MAXIMUM_REQUESTS
                and value.get("day_ordinal")==day and value.get("page_ordinal")==page
                and 1<=day<=len(self.plan.sessions()) and 1<=page<=daily.MAXIMUM_PAGES_PER_DAY
                and value.get("query_date")==self.plan.sessions()[day-1]
                and value.get("plan_sha256")==self.plan.sha256
                and value.get("request_sha256")==daily.page_request_sha256(url)
                and value.get("whole_page_bytes_reserved")==daily.MAXIMUM_RESPONSE_BYTES
                and value.get("whole_page_rows_reserved")==daily.MAXIMUM_PAGE_ROWS,"bound_start_receipt_required")
            require(url==daily.first_url(self.plan,day) if page==1 else daily.next_url(url,self.plan.sessions()[day-1])==url,
                    "same_date_active_request_required")
            thread=threading.get_ident()
            require(thread not in self._slots and value["attempt"] not in self._attempts,"one_pending_slot_per_day_chain_thread")
            if self.registration is not None:
                require(value.get("code_head")==self.registration.binding()[0],"started_receipt_registered_code_HEAD")
            self._attempts.add(value["attempt"])
            self._slots[thread]={"attempt":value["attempt"],"day":day,"page":page,"url":url,"authorized":False,"invoked":False}
    def authorize_HTTP(self,request,maximum):
        with self._lock:
            self.local_check(); require(not self._halted,"halted_no_new_HTTP")
            slot=self._slots.get(threading.get_ident())
            require(slot is not None and not slot["authorized"] and type(request.full_url) is str
                and request.full_url==slot["url"] and request.get_method()=="GET"
                and maximum==daily.MAXIMUM_RESPONSE_BYTES,"exact_started_HTTP_slot_required")
            if self._authorizations%8==0:
                try: self.guard.refresh()
                except (lane.LaneBatchRefusal,OSError):
                    self._halted=True; raise OperationalRefusal("matching_remote_advanced_stop_and_drain") from None
            self.local_check(); slot["authorized"]=True; self._authorizations+=1
    def transport(self,opener,request,maximum,*,on_http_start):
        self.authorize_HTTP(request,maximum)
        # Producer accounting is called only after exact registered guards,
        # immediately before the fixed transport. No descriptor/boolean can
        # declare an HTTP start or relax the source gate.
        on_http_start()
        with self._lock:
            self._slots[threading.get_ident()]["invoked"]=True; self._invocations+=1
        return _http(opener,request,maximum)
    def record_published_raw(self,name,raw):
        with self._lock:
            slot=self._slots.get(threading.get_ident())
            require(slot is not None and slot["invoked"] and name==f"day-{slot['day']:04d}-page-{slot['page']:02d}.raw"
                and type(raw) is bytes and len(raw)<=daily.MAXIMUM_RESPONSE_BYTES,"raw_exact_invoked_slot_required")
            key=(slot["day"],slot["page"])
            require(key not in self._published_raw,"one_owned_raw_per_page")
            self._published_raw[key]=(hash_bytes(raw),len(raw),daily.page_request_sha256(slot["url"]))
    def record_closed_receipt(self,value):
        with self._lock:
            self.local_check()
            slot=self._slots.get(threading.get_ident())
            require(slot is not None and value.get("attempt")==slot["attempt"]
                and value.get("day_ordinal")==slot["day"] and value.get("page_ordinal")==slot["page"]
                and value.get("request_sha256")==daily.page_request_sha256(slot["url"]),"only_started_slot_receipt_can_drain")
            require(value.get("http_invoked",False) is slot["invoked"],"exact_transport_invocation_receipt")
            if value.get("raw_path") is not None:
                key=(slot["day"],slot["page"])
                require(value["raw_path"]==f"day-{slot['day']:04d}-page-{slot['page']:02d}.raw"
                    and self._published_raw.get(key)==(value.get("raw_sha256"),value.get("raw_bytes"),value["request_sha256"]),"observed_raw_receipt_binding_required")
                self._raw_receipts[key]=self._published_raw[key]
            del self._slots[threading.get_ident()]
    def permit_success(self):
        self.local_check(); require(not self._halted,"remote_halted_no_success")
    def complete_day(self,day):
        with self._lock:
            self.permit_success(); require(1<=day<=len(self.plan.sessions()) and day not in self._closed_days
                and day in self._qualified,"one_typed_success_per_registered_day")
            self._closed_days.add(day)
    def observe_qualified(self,report):
        with self._lock:
            self.permit_success()
            require(type(report) is daily.DailyActiveReferenceQualification and report._plan is self.plan,"exact_singleton_daily_qualification_required")
            require(self.index is not None and report._index is self.index,"same_held_original_native_index_required")
            value=report.to_payload(); day=value["day_ordinal"]
            require(day not in self._qualified and value["query_date"]==self.plan.sessions()[day-1],"one_bound_daily_qualification")
            for origin in value["page_origins"]:
                require(self._raw_receipts.get((day,origin["ordinal"]))==(origin["raw_sha256"],origin["raw_bytes"],origin["request_sha256"]),
                        "every_qualified_page_has_closed_raw_receipt")
            self._qualified[day]=report.sha256
    def final(self,inventory):
        with self._lock:
            self.permit_success(); require(not self._slots and self._closed_days==set(range(1,1170))
                and inventory.get("complete_frozen_sequence") is True
                and inventory.get("planned_days")==1169 and inventory.get("days_returned")==1169
                and inventory.get("http_invocations")==self._invocations,"all_actual_daily_reports_and_drains_required")
            observation=self.audit_closure(inventory)
            require(observation["round_complete"] is True,"final_remote_or_typed_coverage_refused_no_success")
            return observation
    def audit_closure(self,inventory):
        """Every final audit is fresh; drift never blocks safe negative evidence."""
        with self._lock:
            self.local_check()
            began=_utc_now()
            matching=True
            try:
                self.guard.refresh()
            except (lane.LaneBatchRefusal,OSError):
                self._halted=True; matching=False
            ended=_utc_now()
            require(daily._clock(began)<=daily._clock(ended),"final_remote_audit_clock_backdated")
            coverage=(not self._slots and self._closed_days==set(range(1,1170))
                and set(self._qualified)==self._closed_days and inventory.get("planned_days")==1169
                and inventory.get("days_returned")==1169 and inventory.get("http_invocations")==self._invocations)
            complete=(inventory.get("complete_frozen_sequence") is True and coverage and matching and not self._halted)
            return {"schema":"si-daily-active-fresh-remote-closure-v1","audit_started_at":began,"audit_received_at":ended,
                "matching_remote_equal":matching,"remote_ref":lane.REF,"remote_status":"matching" if matching else "refused_or_unavailable",
                "pending_receipt_slots":len(self._slots),"all1169_typed_qualification_and_raw_receipts":coverage,
                "actual_HTTP_invocations":self._invocations,"round_complete":complete,"source_admitted":False,
                "outcome_looks":0,"qc_attempts":0}

class ScopedPublisher:
    """No unregistered names/overwrites; cheap owned FD checks per byte write."""
    def __init__(self,owned,gate,directory):
        require(type(owned) is custody._OwnedOutput and type(gate) is DailyHTTPBatchGate,"exact_owned_daily_publisher_required")
        self.owned,self.gate,self.directory=owned,gate,directory
        self._pending_closed=None
    def publish(self,directory,name,value,*,json_value=False):
        require(directory==self.directory and type(name) is str,"fixed_output_directory")
        self.gate.local_check(); self.owned.check()
        page=re.fullmatch(r"day-([0-9]{4})-page-([0-9]{2})\.(started\.json|received\.json|refused\.json|raw)",name)
        day=re.fullmatch(r"day-([0-9]{4})\.(started\.json|qualified\.private\.json|completed\.json|refused\.json)",name)
        require(page is not None or day is not None or name in {"inventory.private.json","run.refused.json","round.closed.json"},"unregistered_publication_prefix")
        if page:
            require(1<=int(page[1])<=1169 and 1<=int(page[2])<=daily.MAXIMUM_PAGES_PER_DAY,"registered_page_prefix_range")
        if day: require(1<=int(day[1])<=1169,"registered_day_prefix_range")
        if name=="round.closed.json":
            require(self._pending_closed is not None and value is self._pending_closed[0]
                and canonical_json(value)==self._pending_closed[1],"fresh_owned_authoritative_closure_required")
        if page and page[3]=="raw":
            slot=self.gate._slots.get(threading.get_ident())
            require(slot is not None and slot["invoked"] and (int(page[1]),int(page[2]))==(slot["day"],slot["page"])
                and type(value) is bytes and len(value)<=daily.MAXIMUM_RESPONSE_BYTES,"raw_slot_scope_before_publication")
        if page and page[3] in {"received.json","refused.json"}:
            require(type(value) is dict and (value.get("day_ordinal"),value.get("page_ordinal"))==(int(page[1]),int(page[2])),
                    "receipt_prefix_binding_before_publication")
        if page and page[3]=="started.json": self.gate.register_start(name,value)
        if day and day[2]=="started.json": self.gate.permit_success()
        if day and day[2] in {"qualified.private.json","completed.json"}:
            self.gate.permit_success()
            require(int(day[1]) in self.gate._qualified,"typed_qualification_before_publication")
            if day[2]=="qualified.private.json": require(hash_bytes(value)==self.gate._qualified[int(day[1])],"exact_qualified_bytes_required")
        if name in {"inventory.private.json","run.refused.json"}:
            observation=self.gate.audit_closure(value)
            value=dict(value,source_sequence_reported_complete=value.get("complete_frozen_sequence") is True,
                complete_frozen_sequence=observation["round_complete"],final_remote_observation=observation,
                round_closure_status="provisional_pending_post_publication_audit")
        if json_value and self.gate.registration is not None:
            value=dict(value,runtime_registration=self.gate.registration.marker(),stable_budget_protocol_sha256=PROTOCOL_SHA256)
        raw=(canonical_json(value)+"\n").encode() if json_value else value
        require(type(raw) is bytes,"exact_private_publication_bytes")
        self.owned.publish(name,raw)
        if page and page[3]=="raw": self.gate.record_published_raw(name,raw)
        if page and page[3] in {"received.json","refused.json"}:
            # A later refusal following an already received raw page is not a
            # second transport drain; only the first closed receipt consumes it.
            if threading.get_ident() in self.gate._slots: self.gate.record_closed_receipt(value)
        if day and day[2]=="completed.json": self.gate.complete_day(int(day[1]))
    def bytes(self,directory,name,value): self.publish(directory,name,value)
    def json(self,directory,name,value): self.publish(directory,name,value,json_value=True)
    def finish_round(self,inventory):
        # This is deliberately AFTER the provisional inventory publication.
        # A remote advance in that window yields a retained refused closure,
        # not an accepted Completed status from the earlier inventory.
        observation=self.gate.audit_closure(inventory)
        closed={"schema":"si-daily-active-authoritative-round-close-v1","plan_sha256":self.gate.plan.sha256,
            "final_remote_observation":observation,"complete_frozen_sequence":observation["round_complete"],
            "round_closure_status":"completed" if observation["round_complete"] else "refused",
            "source_admitted":False,"outcome_looks":0,"qc_attempts":0}
        self._pending_closed=(closed,canonical_json(closed))
        try: self.json(self.directory,"round.closed.json",closed)
        finally: self._pending_closed=None
        return dict(inventory,complete_frozen_sequence=observation["round_complete"],round_closure=closed)

def require_live_registration(registration=None):
    require(type(SOURCE_ANCESTOR) is str and re.fullmatch(r"[0-9a-f]{40}",SOURCE_ANCESTOR)
        and all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}",value)
        for value in (SOURCE_ARCHIVE_SHA256,CALENDAR_SHA256,PROTOCOL_SHA256))
        and hash_payload(protocol())==PROTOCOL_SHA256
        and type(SPENT_SOURCE_PINS) is dict and bool(SPENT_SOURCE_PINS)
        and type(OUTPUT_DIRECTORY) is str and OUTPUT_DIRECTORY.startswith(str(lane.ROOT)+"/artifacts/short_interest/private/")
        and re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,100}",GLOBAL_CLAIM_NAME),"prospective_operational_pins_pending")
    require(type(registration) is RuntimeRegistration,"external_current_runtime_registration_required")
    registration.binding()

def run_pending():
    require_live_registration()
    raise OperationalRefusal("root_source_loader_and_global_claim_composition_required_before_live_use")

class LoadedSourceBundle:
    """Read previously replayed spent proof/archive bytes once, never reset."""
    def __init__(self,guard,registration):
        require_live_registration(registration)
        self.guard=guard; self.registration=registration; self.handles=[]; self._closed=False
        guard.refresh()
        result=subprocess.run(["git","merge-base","--is-ancestor",SOURCE_ANCESTOR,registration.binding()[0]],
            cwd=lane.ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        require(result.returncode==0,"original_source_not_registered_lane_ancestor")
        guard.check()
        try:
            require(str(Path(__file__).absolute()) in dict(registration.binding()[2]),"controller_in_complete_manifest_required")
            for path,sha in registration.binding()[2]:
                code_path=Path(path)
                require(code_path.is_relative_to(lane.ROOT),"code_pin_outside_designated_lane")
                self.handles.append(HeldPinnedFile(code_path,sha,2*1024*1024,private=False,boundary=guard.check))
            proofs=[]
            for path,sha in SPENT_SOURCE_PINS.items():
                source_path=Path(path)
                require(source_path.is_relative_to(lane.ROOT/"artifacts/short_interest"),"spent_pin_outside_designated_lane")
                held=HeldPinnedFile(source_path,sha,2*1024*1024,boundary=guard.check)
                self.handles.append(held); proofs.append((str(source_path),held.bytes()))
            self.spent_proofs=tuple(proofs)
            # Pins identify the previous independently replayed original
            # source/budget receipts, not credential or download authority.
            archive_path=Path(SOURCE_ARCHIVE_PATH)
            require(archive_path.is_relative_to(lane.ROOT/"artifacts/short_interest"),"archive_pin_outside_designated_lane")
            archive=HeldPinnedFile(archive_path,SOURCE_ARCHIVE_SHA256,512*1024*1024,boundary=guard.check)
            self.handles.append(archive)
            captured=master.CapturedSharadarMasterArchive("tickers",archive.bytes(),master.request_sha256("download-tickers"))
            self.index=daily.identity.build_composite_native_index(captured)
            require(self.index.metadata()["archive_sha256"]==SOURCE_ARCHIVE_SHA256,"original_archive_index_binding")
            calendar=shared_calendar_source()
            require(hash_bytes(calendar)==CALENDAR_SHA256,"registered_calendar_bytes_changed")
            import json
            self.plan=daily.freeze_daily_active_plan(tuple(row["session"] for row in json.loads(calendar)["sessions"]),calendar_sha256=CALENDAR_SHA256)
            self.handles=tuple(self.handles)
            self._anchor=self._identity=(guard,registration,self.handles,self.plan,self.index)
            guard.check(); self.check()
        except BaseException:
            self.close(); raise
    def check(self):
        require(not self._closed and self._anchor is self._identity and all(getattr(self,name) is value for name,value in zip(
            ("guard","registration","handles","plan","index"),self._anchor)),"held_source_bundle_changed_or_closed")
        require_live_registration(self.registration)
        for held in self.handles: held.check()
        self.plan._guard(); self.index._guard()
    def close(self):
        for held in self.handles: held.close()
        self.handles=[]; self._closed=True

def run_registered(*,producer,started_at,registration):
    """Root must pin canonical producer code and apply the approved seams."""
    require_live_registration(registration)
    producer_path=Path(producer.__file__).absolute()
    require(str(producer_path) in dict(registration.binding()[2]) and {"lane_guard","transport","on_qualified_day"}
        <=set(inspect.signature(producer.capture_with_seams).parameters),"registered_canonical_producer_seams_required")
    head,remote=registration.binding()[:2]
    guard=lane.LaneGuard(lane.ROOT,expected_head=head,expected_remote=remote)
    bundle=LoadedSourceBundle(guard,registration)
    directory=Path(OUTPUT_DIRECTORY)
    try:
        require(directory.is_absolute() and directory.resolve()==directory,"fixed_output_path_required")
        parent=directory.parent.lstat()
        require(stat.S_ISDIR(parent.st_mode) and parent.st_uid==os.getuid() and stat.S_IMODE(parent.st_mode)==0o700,
                "fixed_output_parent_protection")
        directory.mkdir(mode=0o700)
        gate=DailyHTTPBatchGate(guard,bundle.plan,bundle.check,bundle.index,registration); gate.initial()
        with custody._OwnedOutput(directory,lambda:None) as owned:
            publisher=ScopedPublisher(owned,gate,directory)
            def claim(value):
                gate.local_check()
                require(value.get("maximum_attempts")==daily.MAXIMUM_REQUESTS and value.get("maximum_total_bytes")==daily.MAXIMUM_TOTAL_BYTES
                    and value.get("maximum_total_rows")==daily.MAXIMUM_ROWS and value.get("maximum_pages_per_day")==daily.MAXIMUM_PAGES_PER_DAY
                    and value.get("maximum_day_chains")==8 and value.get("plan_sha256")==bundle.plan.sha256
                    and value.get("code_head")==head and value.get("remote_head")==remote
                    and value.get("restart_or_resumption_allowed") is False,"exact_daily_global_budget_required")
                retained=dict(value,runtime_registration=registration.payload(),stable_budget_protocol_sha256=PROTOCOL_SHA256)
                owned.publish(GLOBAL_CLAIM_NAME,(canonical_json(retained)+"\n").encode(),parent=True)
            try:
                value=producer.capture_with_seams(lane.ROOT,directory,bundle.plan,bundle.index,
                    head=head,remote=remote,started_at=started_at,
                    verify_sources=lambda plan,index:bundle.check(),verify_code=lambda plan:bundle.check(),
                    claim_budget=claim,publish=publisher.bytes,publish_json=publisher.json,
                    read_secret=read_named_keychain,lane_guard=gate.local_check,transport=gate.transport,
                    on_qualified_day=gate.observe_qualified)
            except (daily.DailyActiveReferenceError,lane.LaneBatchRefusal,OperationalRefusal,OSError):
                publisher.finish_round({"complete_frozen_sequence":False,"http_invocations":gate._invocations,
                    "code":"registered_producer_refused_after_fixed_claim","outcome_looks":0,"qc_attempts":0})
                raise OperationalRefusal("registered_daily_round_refused_with_closure") from None
            return publisher.finish_round(value)
    finally:
        bundle.close()
