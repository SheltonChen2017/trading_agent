"""Inert preparation for four cloud-only, identity-field historical queries.

No local SDK, credential or real artifact access. A separately activated cell
requires the completed original consumer's existing kernel context. It never
repeats CIK discovery or old receipt reads, requests prices, or assigns PIT/
listing/canonical authority. Returned values and derived counts/hashes remain
in cloud; the public acknowledgement contains only own execution controls.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import sys

from research import insider_buying_qc_cik_candidate_consumer as consumer


SELF_PATH="research/insider_buying_qc_historical_reference_cell.py"
TEST_PATH="tests/test_insider_buying_qc_historical_reference_cell.py"
SCHEMA="insider-qc-historical-reference-v1"
AUDIT_ID="ib-qc-first64-historical-reference-20261025-once"
NOTEBOOK="ib_qc_cik_consumer_20261025.ipynb"
ARTIFACT_PARTS=("artifacts","insider_buying","qc_historical_reference_v1")
EMPTY_CACHE_PREFIX="/var/empty/insider-qc-historical-reference-no-bytecode"
LOCK_BYTES=b"INSETF-QC-four-historical-reference-fields-permanent-intent-v1\n"
PROJECT_ID=consumer.PROJECT_ID
LANE_ROOT,LANE_BRANCH=consumer.LANE_ROOT,consumer.LANE_BRANCH
MAX_CONTROL_BYTES,MAX_CELL_BYTES=256*1024,64*1024
SELECTORS=("CompanyReference.CIK","SecurityReference.SecurityType","SecurityReference.ShareClassStatus","SecurityReference.IsPrimaryShare")
CONSUMER_NONCE="452aa9b2606e7fc982bf7a517fca91ed7a565ae4eb1b3d1a1a4c322f2efc372f"
CONSUMER_HEAD="5553afed958734aa61a532d40f88c51e3688fcd9"
CONSUMER_SOURCE_SHA256="487c1ff07870844d90ef8e5654db6cc03094afc6c257da02b3d404b3e94c3716"
CONSUMER_TEST_SHA256="ca600c82d7d987c029cf7c880f6777e60694d65ada3275ea554300d3a7ac2676"
CONSUMER_OBSERVATION={
    "basis":"trusted-main-observed-own-controls; not reopened by this preparer",
    "execution_head":CONSUMER_HEAD,"source_inventory_sha256":"8fd87b48a94d0d06f8e4cb546adb17ea4ca205a81aac97fa313331307bfbb149",
    "source_path":consumer.SELF_PATH,"source_sha256":CONSUMER_SOURCE_SHA256,"test_path":consumer.TEST_PATH,"test_sha256":CONSUMER_TEST_SHA256,
    "nonce":CONSUMER_NONCE,"core_sha256":"66b555b70dc13435d2a6d063b2a65a74e296be83de853564e7ed7a3cf5de7421",
    "cell_sha256":"d7f69f3f80be17fd6a8b3be75a58bfb915d0509b62d92a96e3a5cc00292d42ab",
    "registration_sha256":"2f24b8542efd6bbf6378b2c5e7f090c040e54427c16ef287733edb7945bc4eae",
    "intent_sha256":"4b7a8d17b2df66b149e0853e2357cd6f7be4e996a168bde8da18448717ddf9ea",
    "ready_sha256":"36856495e222fb63f569782afa7d18e36b639523d54bac6a2503c32a5b86920f",
    "acknowledgement_sha256":"2ab7ad36d56d66353d2c95c4f00a34289457055c60c7dc02671294c20ca78df5",
    "acknowledgement_bytes":1077,"own_receipt_reads":104,"resolver_calls":0,"cloud_saves_deletes":0,
    "existing_chain_consistent_observed":True,"independent_persistence_or_platform_origin_established":False}
producer=consumer.producer
publication,sources=consumer.publication,consumer.sources
_raw,_sha,_decode=consumer._raw,consumer._sha,consumer._decode


class HistoricalReferenceError(ValueError):
    """Finite own-control refusal codes only."""


def _need(value,code):
    if not value:raise HistoricalReferenceError(code)


def _provenance(fixture):
    producer_provenance=consumer._producer_provenance(fixture)
    previous=_decode(_raw(CONSUMER_OBSERVATION))
    if fixture:
        previous={**previous,"basis":"invented own controls; no actual consumer observation","execution_head":"a"*40,
            "existing_chain_consistent_observed":False,"nonce":"e"*64}
    return {"producer":producer_provenance,"consumer":previous}


CORE_SOURCE='''def _ib_historical_reference_run(_factory,_text,_registration_sha,_expected_core_sha):
    import contextlib
    import hashlib
    import json
    import math
    from datetime import datetime
    class _Stop(Exception): pass
    class _Discard:
        def write(self,text): return len(text)
        def flush(self): return None
    def raw(value): return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)
    def sha(value): return hashlib.sha256(raw(value).encode()).hexdigest()
    def require(value):
        if not value: raise _Stop()
    def decode(text):
        require(type(text) is str and 0<len(text.encode())<=2097152)
        def pairs(items):
            result={}
            for key,value in items:
                require(key not in result);result[key]=value
            return result
        value=json.loads(text,object_pairs_hook=pairs,parse_constant=lambda _:require(False))
        require(type(value) is dict and raw(value)==text);return value
    authority={"reference_corroboration_only":True,"historical_absence_proven":False,"point_in_time_verified":False,
        "listing_verified":False,"share_class_verified":False,"publication_or_original_availability_verified":False,
        "vendor_backfill_excluded":False,"canonical_admitted":False,"rights_verified":False,"backtesting_ready":False}
    ack={"schema":"insider-qc-historical-reference-v1/acknowledgement","disposition":"registration_refused"}
    stage="registration";store=None;fresh_all=False;attempted=[];results=[];read_bytes=[0]
    try:
        r=decode(_text);require(hashlib.sha256(_text.encode()).hexdigest()==_registration_sha)
        require(set(r)=={"schema","audit_id","project_id","execution_notebook","execution_cell_index","nonce","prefix","fixture_only","core_sha256","source_provenance","preparation_source","scope"})
        require(r["schema"]=="insider-qc-historical-reference-v1/registration" and r["audit_id"]=="ib-qc-first64-historical-reference-20261025-once")
        require(type(r["project_id"]) is int and r["project_id"]==37465795 and r["execution_notebook"]=="ib_qc_cik_consumer_20261025.ipynb")
        require(type(r["execution_cell_index"]) is int and r["execution_cell_index"]==1 and r["fixture_only"] is __FIXTURE__)
        require(type(r["nonce"]) is str and len(r["nonce"])==64 and all(c in "0123456789abcdef" for c in r["nonce"]))
        require(r["prefix"]=="37465795/ib-qc-first64-historical-reference-20261025-once/"+r["nonce"] and r["core_sha256"]==_expected_core_sha)
        require(raw(r["source_provenance"])==raw(__PROVENANCE__) and raw(r["scope"])==raw(__SCOPE__))
        p=r["preparation_source"]
        require(type(p) is dict and set(p)=={"head","source_path","source_sha256","source_inventory_sha256"} and p["source_path"]=="research/insider_buying_qc_historical_reference_cell.py")
        for name,length in (("head",40),("source_sha256",64),("source_inventory_sha256",64)):
            require(type(p[name]) is str and len(p[name])==length and all(c in "0123456789abcdef" for c in p[name]))
        ack={"schema":"insider-qc-historical-reference-v1/acknowledgement","audit_id":r["audit_id"],"project_id":37465795,
            "execution_notebook":r["execution_notebook"],"execution_cell_index":1,"registration_sha256":_registration_sha,
            "core_sha256":r["core_sha256"],"prefix":r["prefix"],"fixture_only":r["fixture_only"],"disposition":"refused_no_retry",
            "stop_stage":None,"own_final_receipt_acknowledged":False,"own_error_receipt_acknowledged":False,
            "platform_values_counts_or_digests_exported":False,"backtesting_ready":False}
        stage="kernel_claim";marker="_ib_historical_reference_"+r["nonce"]
        require(marker not in globals());globals()[marker]=True
        stage="retained_context"
        previous=r["source_provenance"];old=__PRODUCER_REGISTRATION__
        original_nonce=previous["producer"]["nonce"];consumer_nonce=previous["consumer"]["nonce"]
        require(globals().get("_ib_cik_consume_"+original_nonce) is True and globals().get("_ib_cik_new_consumer_"+consumer_nonce) is True)
        rows=globals().get("_ib_cik_retained_"+original_nonce)
        require(type(rows) is list and len(rows)==51)
        old_authority={"candidate_only":True,"historical_absence_proven":False,"historical_cik_association_proven":False,
            "share_class_verified":False,"listing_verified":False,"point_in_time_verified":False,"canonical_admitted":False,"backtesting_ready":False}
        old_start={"schema":"insider-qc-cik-candidates-v1/start","registration_sha256":sha(old),"core_sha256":old["core_sha256"],
            "ciks_sha256":old["ciks_sha256"],"source_provenance":old["source_provenance"],"lookup_date":"2021-03-31","authority":old_authority}
        sid_values={};edges=[]
        for ordinal,(row,cik) in enumerate(zip(rows,old["ciks"]),1):
            require(type(row) is dict and set(row)=={"schema","ordinal","raw_cik","lookup_started_sha256","candidates","duplicate_sids","resolver_returned_zero","authority"})
            begun={"schema":"insider-qc-cik-candidates-v1/lookup-started","ordinal":ordinal,"raw_cik":cik,
                "parameter_cik":int(cik),"lookup_date":"2021-03-31","start_sha256":sha(old_start),"maximum_attempts":1}
            candidates=row["candidates"];require(type(candidates) is list and len(candidates)<=16)
            ids=[]
            for position,candidate in enumerate(candidates,1):
                require(type(candidate) is dict and set(candidate)=={"sid","symbol_value","security_type"} and candidate["security_type"]=="Equity")
                for name,limit in (("sid",512),("symbol_value",128)):
                    value=candidate[name];require(type(value) is str and 0<len(value)<=limit and all(32<=ord(c)<=126 for c in value))
                sid,value=candidate["sid"],candidate["symbol_value"];ids.append(sid)
                require(sid not in sid_values or sid_values[sid]==value)
                sid_values[sid]=value;edges.append({"cik_ordinal":ordinal,"candidate_ordinal":position,"raw_cik":cik,"sid":sid,"saved_symbol_value":value})
            expected={"schema":"insider-qc-cik-candidates-v1/lookup-result","ordinal":ordinal,"raw_cik":cik,"lookup_started_sha256":sha(begun),
                "candidates":candidates,"duplicate_sids":sorted({sid for sid in ids if ids.count(sid)>1}),"resolver_returned_zero":not candidates,"authority":old_authority}
            require(raw(row)==raw(expected) and len(edges)<=512)
        require(1<=len(sid_values)<=512)
        input_rows_sha=sha(rows);ordered_sids=sorted(sid_values)
        # Coherent mutation after the prior consumer cannot be ruled out by
        # ordinary globals; this is internal replay, not authenticated origin.
        def check_context():
            nonlocal stage
            stage="context_recheck"
            require(globals().get("_ib_cik_retained_"+original_nonce) is rows and sha(rows)==input_rows_sha
                and globals().get("_ib_cik_consume_"+original_nonce) is True
                and globals().get("_ib_cik_new_consumer_"+consumer_nonce) is True)
        stage="construct"
        with contextlib.redirect_stdout(_Discard()),contextlib.redirect_stderr(_Discard()):
            qb,SID,Symbol,equity,DataFrame,Timestamp,np,missing_values=_factory()
            stage="project";require(type(qb.project_id) is int and qb.project_id==37465795)
            stage="symbol_reconstruction";symbols=[]
            for sid in ordered_sids:
                identifier=SID.parse(sid);require(str(identifier)==sid and identifier.security_type==equity)
                symbol=Symbol(identifier,sid_values[sid]);require(isinstance(symbol,Symbol) and str(symbol.id)==sid and symbol.value==sid_values[sid] and symbol.security_type==equity)
                symbols.append(symbol)
            store=qb.object_store
            keys=[r["prefix"]+"/start.json"]
            for ordinal in range(1,5):keys.extend([r["prefix"]+"/%02d-started.json"%ordinal,r["prefix"]+"/%02d-result.json"%ordinal])
            keys.append(r["prefix"]+"/final.json");error_key=r["prefix"]+"/error.json"
            for key in keys+[error_key]:
                stage="key_precheck";require(store.contains_key(key) is False)
            fresh_all=True
            def save_read(key,value,phase):
                nonlocal stage
                stage=phase+"_save";text=raw(value);require(len(text.encode())<=2097152)
                require(store.save(key,text) is True);stage=phase+"_readback"
                retained=store.read(key);require(type(retained) is str)
                read_bytes[0]+=len(retained.encode());require(read_bytes[0]<=8388608)
                require(raw(decode(retained))==text)
            start={"schema":"insider-qc-historical-reference-v1/start","registration_sha256":_registration_sha,"core_sha256":r["core_sha256"],
                "source_provenance":previous,"retained_rows_sha256":input_rows_sha,"ordered_sids":ordered_sids,"candidate_edges":edges,
                "scope":r["scope"],"authority":authority}
            save_read(keys[0],start,"start");start_sha=sha(start)
            def value_metadata(value,selector):
                if value is None or value is np.nan or any(value is missing for missing in missing_values):return {"state":"missing_value"}
                if type(value) in (float,np.float64,np.float32) and math.isnan(float(value)):return {"state":"missing_value"}
                if selector=="SecurityReference.IsPrimaryShare":
                    require(type(value) in (bool,np.bool_));return {"state":"declared_value","kind":"boolean","value":bool(value)}
                if selector=="CompanyReference.CIK" and type(value) in (int,np.int64,np.int32,np.uint64,np.uint32):
                    require(0<=int(value)<=9999999999);return {"state":"declared_value","kind":"integer","value":int(value)}
                require(type(value) in (str,np.str_) and len(value)<=64 and all(32<=ord(c)<=126 for c in value))
                return {"state":"declared_value","kind":"text","value":str(value)}
            for ordinal,selector in enumerate(r["scope"]["selectors"],1):
                check_context()
                begun={"schema":"insider-qc-historical-reference-v1/query-started","ordinal":ordinal,"selector":selector,
                    "start_sha256":start_sha,"date_start_inclusive":"2021-03-31","date_end_inclusive":"2021-03-31",
                    "ordered_sids_sha256":sha(ordered_sids),"maximum_attempts":1}
                save_read(keys[2*ordinal-1],begun,"query_start")
                check_context()
                stage="reference_query";attempted.append(selector)
                frame=qb.get_fundamental(symbols,selector,datetime(2021,3,31),datetime(2021,3,31))
                check_context()
                stage="reference_shape";require(type(frame) is DataFrame and len(frame.index)<=1 and len(frame.columns)<=len(ordered_sids))
                columns=list(frame.columns);require(all(type(sid) is str and sid in sid_values for sid in columns) and len(columns)==len(set(columns)))
                stamps=[]
                for stamp in frame.index:
                    require(type(stamp) in (datetime,Timestamp) and not isinstance(stamp,np.datetime64)
                        and stamp.strftime("%Y-%m-%d") in r["scope"]["allowlisted_returned_index_dates"]
                        and (stamp.hour,stamp.minute,stamp.second,stamp.microsecond)==(0,0,0,0)
                        and getattr(stamp,"nanosecond",0)==0)
                    stamps.append({"returned_index_isoformat":stamp.isoformat(),"timezone_label":"naive-unqualified" if stamp.tzinfo is None else str(stamp.tzinfo),
                        "index_semantics":"date label or documented current-public-source EndTime=T+1; never availability",
                        "record_Time_or_EndTime_not_exposed_by_dataframe":True,"availability_before_entry_verified":False})
                observations=[]
                for sid in ordered_sids:
                    if not stamps:meta={"state":"no_record_returned"}
                    elif sid not in columns:meta={"state":"column_not_returned"}
                    else:meta=value_metadata(frame.iloc[0,columns.index(sid)],selector)
                    observations.append({"sid":sid,"reference":meta})
                result={"schema":"insider-qc-historical-reference-v1/query-result","ordinal":ordinal,"selector":selector,"query_started_sha256":sha(begun),
                    "returned_index":stamps,"observations":observations,"raw_missing_ambiguous_or_default_values_not_repaired":True,"authority":authority}
                save_read(keys[2*ordinal],result,"query_result");results.append(result)
                check_context()
            check_context()
            final={"schema":"insider-qc-historical-reference-v1/final","registration_sha256":_registration_sha,"start_sha256":start_sha,
                "query_result_sha256":[sha(result) for result in results],"candidate_edges_sha256":sha(edges),
                "all_four_fixed_queries_completed":True,"source_context_boundary_checks_match":True,"authority":authority}
            save_read(keys[-1],final,"final")
            globals()["_ib_historical_reference_retained_"+r["nonce"]]={"start":start,"results":results,"final":final}
            ack["own_final_receipt_acknowledged"]=True;ack["disposition"]="historical_reference_receipts_completed"
    except BaseException:
        if ack["disposition"]!="registration_refused":
            ack["stop_stage"]=stage
            if fresh_all and store is not None:
                error={"schema":"insider-qc-historical-reference-v1/error","registration_sha256":_registration_sha,"stop_stage":stage,
                    "attempted_selectors":attempted,"completed_selectors":[result["selector"] for result in results],
                    "unattempted_selectors":r["scope"]["selectors"][len(attempted):],"no_retry_or_resume":True,"authority":authority}
                try:
                    with contextlib.redirect_stdout(_Discard()),contextlib.redirect_stderr(_Discard()):
                        text=raw(error);require(len(text.encode())<=2097152);require(store.save(error_key,text) is True)
                        retained=store.read(error_key);require(type(retained) is str)
                        read_bytes[0]+=len(retained.encode());require(read_bytes[0]<=8388608 and raw(decode(retained))==text)
                        ack["own_error_receipt_acknowledged"]=True
                except BaseException:pass
    print(raw(ack))
'''


def _scope():
    return {"snapshot_date":"2021-03-31","date_start_inclusive":"2021-03-31","date_end_inclusive":"2021-03-31",
        "allowlisted_returned_index_dates":["2021-03-31","2021-04-01"],"returned_index_midnight_required":True,
        "EndTime_Tplus1_is_not_publication_or_availability":True,
        "selectors":list(SELECTORS),"maximum_batch_queries":4,"maximum_symbols":512,"maximum_candidate_edges":512,
        "maximum_rows_per_query":1,"maximum_receipt_bytes":2097152,"maximum_total_read_bytes":8388608,
        "fresh_own_keys":11,"old_receipt_reads":0,"resolver_calls":0,"prices_History_subscriptions_jobs_backtests":0,
        "retry_resume_kernel_reset_fallback":False,"platform_values_counts_or_digests_exported":False,
        "current_master_not_exact_runtime_attestation":True,"historical_feed_backfill_or_migration_excluded":False,
        "atomic_create_or_immutability_guaranteed":False}


def _core(fixture):
    return CORE_SOURCE.replace("__FIXTURE__",repr(fixture)).replace("__PROVENANCE__",repr(_provenance(fixture))).replace(
        "__SCOPE__",repr(_scope())).replace("__PRODUCER_REGISTRATION__",repr(producer._registration(consumer.PRODUCER_NONCE,fixture)))


def _registration(nonce,fixture,identity):
    _need(type(nonce) is str and producer.control._SHA.fullmatch(nonce) and type(fixture) is bool,"reference_nonce_or_mode_refused")
    _source_identity(identity,Path(identity["root"]))
    return {"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,"project_id":PROJECT_ID,"execution_notebook":NOTEBOOK,"execution_cell_index":1,
        "nonce":nonce,"prefix":f"{PROJECT_ID}/{AUDIT_ID}/{nonce}","fixture_only":fixture,"core_sha256":_sha(_core(fixture).encode()),
        "source_provenance":_provenance(fixture),"preparation_source":{"head":identity["head"],"source_path":SELF_PATH,
            "source_sha256":identity["source_sha256"][SELF_PATH],"source_inventory_sha256":identity["source_inventory_sha256"]},"scope":_scope()}


def _cell(nonce,fixture,identity):
    registration_raw=_raw(_registration(nonce,fixture,identity))
    wrapper=("\ndef _ib_historical_reference_factory():\n    from QuantConnect.Research import QuantBook\n    from QuantConnect import SecurityIdentifier,Symbol,SecurityType\n    from pandas import DataFrame,Timestamp,NA,NaT\n    import numpy as np\n    return QuantBook(),SecurityIdentifier,Symbol,SecurityType.EQUITY,DataFrame,Timestamp,np,(NA,NaT)\n"
        +"_ib_historical_reference_run(_ib_historical_reference_factory,"+repr(registration_raw.decode())+","+repr(_sha(registration_raw))+","+repr(_sha(_core(fixture).encode()))+")\n")
    cell_raw=(_core(fixture)+wrapper).encode();_need(0<len(cell_raw)<=MAX_CELL_BYTES,"reference_cell_bound_refused")
    compile(cell_raw,"<fixed-qc-historical-reference>","exec");return registration_raw,cell_raw


def _invented_identity(root):
    inventory={SELF_PATH:"a"*64,TEST_PATH:"b"*64,**{f"data/invented_{i:03}.py":"c"*64 for i in range(108)}}
    return {"root":str(root),"branch":LANE_BRANCH,"head":"a"*40,"clean":True,"source_sha256":inventory,"source_inventory_sha256":_sha(_raw(inventory))}


def build_invented_cell(nonce,*,root=Path("/invented-historical-reference")):
    return _cell(nonce,True,_invented_identity(root))


def _source_identity(value,root):
    _need(type(value) is dict and set(value)=={"root","branch","head","clean","source_sha256","source_inventory_sha256"}
        and value["root"]==str(root) and value["branch"]==LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and producer.control._HEAD.fullmatch(value["head"])
        and type(value["source_sha256"]) is dict and 2<=len(value["source_sha256"])<=2048 and {SELF_PATH,TEST_PATH}<=set(value["source_sha256"])
        and all(type(name) is str and len(name)<=512 and producer.control._SOURCE.fullmatch(name) and Path(name).as_posix()==name
            and ".." not in Path(name).parts and type(digest) is str and producer.control._SHA.fullmatch(digest) for name,digest in value["source_sha256"].items())
        and value["source_inventory_sha256"]==_sha(_raw(value["source_sha256"])),"reference_source_identity_refused")
    return value


def _current(identity):
    _source_identity(identity,LANE_ROOT)
    _need(set(sources.custody._internal_source_paths(LANE_ROOT))<=set(identity["source_sha256"]),"reference_loaded_closure_missing")
    _need(sources.custody._source_bytes(LANE_ROOT,tuple(identity["source_sha256"]))==identity["source_sha256"]
        and sources.custody._source_bytes(LANE_ROOT,tuple(sources.FROZEN))==sources.FROZEN,"reference_current_or_frozen_source_changed")
    _need(all(identity["source_sha256"].get(name)==digest for name,digest in ((consumer.SELF_PATH,CONSUMER_SOURCE_SHA256),
        (consumer.TEST_PATH,CONSUMER_TEST_SHA256),(producer.SELF_PATH,consumer.PRODUCER_SOURCE_SHA256),(producer.TEST_PATH,consumer.PRODUCER_TEST_SHA256))),"reference_original_source_changed")


def _identity(head):
    _need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"fixed_reference_source_required")
    value=sources.custody._identity(head)
    names=(SELF_PATH,TEST_PATH,consumer.SELF_PATH,consumer.TEST_PATH,producer.SELF_PATH,producer.TEST_PATH)
    own=sources.custody._source_bytes(LANE_ROOT,names)
    for name,digest in own.items():_need(_sha(sources.custody._git(LANE_ROOT,"show",head+":"+name))==digest,"reference_uncommitted_source")
    for old_head,items in ((CONSUMER_HEAD,((consumer.SELF_PATH,CONSUMER_SOURCE_SHA256),(consumer.TEST_PATH,CONSUMER_TEST_SHA256))),
        (consumer.PRODUCER_HEAD,((producer.SELF_PATH,consumer.PRODUCER_SOURCE_SHA256),(producer.TEST_PATH,consumer.PRODUCER_TEST_SHA256)))):
        for name,digest in items:_need(_sha(sources.custody._git(LANE_ROOT,"show",old_head+":"+name))==digest,"reference_original_Git_source_changed")
    inventory={**value["source_sha256"],**own};value=_source_identity({**value,"source_sha256":inventory,"source_inventory_sha256":_sha(_raw(inventory))},LANE_ROOT)
    _current(value);return value


def _isolated():
    _need(sys.flags.isolated==sys.flags.no_site==sys.flags.no_user_site==sys.flags.dont_write_bytecode==1
        and sys.pycache_prefix==EMPTY_CACHE_PREFIX,"reference_initial_isolation_required")


def _proof(identity,fixture):
    return {"schema":SCHEMA+"/source-preflight","fixture_only":fixture,"source_inventory_sha256":identity["source_inventory_sha256"],
        "source_count":len(identity["source_sha256"]),"native_network_fork_allwrite_securityexec_denial":not fixture,
        "current_frozen_loaded_and_original_sources_verified":not fixture,"SDK_artifact_credential_or_QC_accesses":0}


def _intent(identity,r,cell,proof,fixture):
    registration=_decode(r)
    return {"schema":SCHEMA+"/permanent-local-intent","audit_id":AUDIT_ID,"fixture_only":fixture,"execution_identity":identity,
        "registration_sha256":_sha(r),"core_sha256":registration["core_sha256"],"cell_sha256":_sha(cell),"cell_bytes":len(cell),
        "project_id":PROJECT_ID,"execution_notebook":NOTEBOOK,"execution_cell_index":1,"prefix":registration["prefix"],
        "source_provenance":registration["source_provenance"],"source_preflight":proof,"local_scope_permanently_consumed":True,
        "maximum_selected_cell_executions":1,"no_retry_even_after_kernel_reset":True,"old_scope_reset_or_recovered":False,
        "cloud_execution_observed":False,"SDK_artifact_credential_or_QC_accesses_by_preparer":0,"backtesting_ready":False}


def _capacity(identity,fixture):
    r,cell=_cell("0"*64,fixture,identity)
    for value in (identity,_decode(r),_intent(identity,r,cell,_proof(identity,fixture),fixture)):
        raw=_raw(value);_need(0<len(raw)<=MAX_CONTROL_BYTES and _raw(_decode(raw))==raw,"reference_control_capacity_refused")


def _worker(identity):
    _isolated();sources._prove_isolation();_current(identity);_capacity(identity,False);_current(identity);return _proof(identity,False)


def _source_preflight(identity):
    code=("import sys;sys.path.insert(0,"+repr(str(LANE_ROOT))+");import json;from research import insider_buying_qc_historical_reference_cell as m;identity=json.loads("+repr(_raw(identity).decode())+");"
        "\ntry: result=m._worker(identity)\nexcept BaseException: print('{\"disposition\":\"reference_source_preflight_refused\"}');sys.exit(2)\nprint(m._raw(result).decode())")
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    command=("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","LANG=C","LC_ALL=C","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)
    child=sources.launcher.run_child(command,cwd=LANE_ROOT,env=None,timeout=60,cap=8192)
    _need(child.returncode==0 and child.stderr==b"" and child.stdout==_raw(_proof(identity,False))+b"\n","reference_source_preflight_refused")
    return _proof(identity,False)


def _prepare(root,identity,*,fixture,guard,preflight,nonce_factory):
    _need(type(fixture) is bool and callable(guard) and callable(preflight) and callable(nonce_factory),"reference_preparation_mode_refused")
    if fixture:
        publication._fixture_root(root);publication._native_fixture_denial()
        _need(preflight is not _source_preflight and nonce_factory is not secrets.token_hex,"invented_reference_callbacks_required")
    else:_need(root==LANE_ROOT and preflight is _source_preflight and nonce_factory is secrets.token_hex,"fixed_reference_preparer_required")
    _source_identity(identity,root);_capacity(identity,fixture);guard();proof=preflight(identity)
    _need(_raw(proof)==_raw(_proof(identity,fixture)),"reference_native_preflight_refused");guard();chain=folder=None
    try:
        chain=sources.custody._Chain(root,ARTIFACT_PARTS,create=True,exclusive_last=True)
        folder=publication._NewDirectory(root.joinpath(*ARTIFACT_PARTS));expected=set()
        def check():
            guard();chain.recheck();folder.check();_need(set(os.listdir(folder.fd))==expected,"reference_output_inventory_changed")
        def publish(name,raw,cap=MAX_CONTROL_BYTES):
            check();digest=folder.publish(name,raw,cap=cap);expected.add(name);check();return digest
        publish("scope.lock",LOCK_BYTES);r,cell=_cell(nonce_factory(32),fixture,identity)
        registration_sha=publish("registration.json",r);cell_sha=publish("cell.py",cell,MAX_CELL_BYTES)
        intent_sha=publish("intent.json",_raw(_intent(identity,r,cell,proof,fixture)));registration=_decode(r)
        ready={"schema":SCHEMA+"/prepared-not-executed","audit_id":AUDIT_ID,"fixture_only":fixture,"registration_sha256":registration_sha,
            "cell_sha256":cell_sha,"cell_bytes":len(cell),"intent_sha256":intent_sha,"core_sha256":registration["core_sha256"],
            "project_id":PROJECT_ID,"execution_notebook":NOTEBOOK,"execution_cell_index":1,"prefix":registration["prefix"],
            "local_scope_permanently_consumed":True,"cloud_execution_observed":False,"SDK_artifact_credential_or_QC_accesses":0,"backtesting_ready":False}
        ready_sha=publish("ready.json",_raw(ready));check()
        return {**ready,"ready_sha256":ready_sha,"cell_source":cell.decode(),"cell_path":str(folder.path/"cell.py"),"intent_path":str(folder.path/"intent.json")}
    finally:publication._close_all((folder,chain),None,None,False)


def prepare_actual_cell(expected_head):
    _isolated();before=_identity(expected_head)
    def guard():_need(_identity(expected_head)==before,"reference_committed_source_changed")
    return _prepare(LANE_ROOT,before,fixture=False,guard=guard,preflight=_source_preflight,nonce_factory=secrets.token_hex)


def prepare_invented_cell(root,*,nonce="a"*64,guard=lambda:None,preflight=None):
    root=Path(root);identity=_invented_identity(root)
    return _prepare(root,identity,fixture=True,guard=guard,preflight=(lambda i:_proof(i,True)) if preflight is None else preflight,
        nonce_factory=lambda count:nonce if count==32 else _need(False,"reference_nonce_length"))


def validate_acknowledgement(raw,*,registration_raw):
    _need(type(raw) is bytes and 0<len(raw)<=8192,"reference_ack_bound")
    r=_decode(registration_raw)
    _need(set(r)=={"schema","audit_id","project_id","execution_notebook","execution_cell_index","nonce","prefix","fixture_only","core_sha256","source_provenance","preparation_source","scope"}
        and r["schema"]==SCHEMA+"/registration" and r["audit_id"]==AUDIT_ID and type(r["project_id"]) is int and r["project_id"]==PROJECT_ID
        and r["execution_notebook"]==NOTEBOOK and type(r["execution_cell_index"]) is int and r["execution_cell_index"]==1 and type(r["fixture_only"]) is bool
        and type(r["nonce"]) is str and producer.control._SHA.fullmatch(r["nonce"]) and r["prefix"]==f"{PROJECT_ID}/{AUDIT_ID}/{r['nonce']}"
        and r["core_sha256"]==_sha(_core(r["fixture_only"]).encode()) and _raw(r["source_provenance"])==_raw(_provenance(r["fixture_only"]))
        and _raw(r["scope"])==_raw(_scope()),"reference_registration_refused")
    p=r["preparation_source"]
    _need(type(p) is dict and set(p)=={"head","source_path","source_sha256","source_inventory_sha256"} and p["source_path"]==SELF_PATH
        and type(p["head"]) is str and producer.control._HEAD.fullmatch(p["head"])
        and all(type(p[name]) is str and producer.control._SHA.fullmatch(p[name]) for name in ("source_sha256","source_inventory_sha256")),"reference_registration_source_refused")
    fixed={"schema":SCHEMA+"/acknowledgement","audit_id":AUDIT_ID,"project_id":PROJECT_ID,"execution_notebook":NOTEBOOK,"execution_cell_index":1,
        "registration_sha256":_sha(registration_raw),"core_sha256":r["core_sha256"],"prefix":r["prefix"],"fixture_only":r["fixture_only"],
        "platform_values_counts_or_digests_exported":False,"backtesting_ready":False}
    value=_decode(raw.removesuffix(b"\n"));dynamic={"disposition","stop_stage","own_final_receipt_acknowledged","own_error_receipt_acknowledged"}
    _need(type(value) is dict and set(value)==set(fixed)|dynamic and _raw({key:value[key] for key in fixed})==_raw(fixed)
        and type(value["own_final_receipt_acknowledged"]) is bool and type(value["own_error_receipt_acknowledged"]) is bool,"reference_ack_schema_refused")
    if value["own_final_receipt_acknowledged"]:
        _need(value["disposition"]=="historical_reference_receipts_completed" and value["stop_stage"] is None and value["own_error_receipt_acknowledged"] is False,"reference_ack_false_completion")
    else:
        stages={"kernel_claim","retained_context","construct","project","symbol_reconstruction","key_precheck","start_save","start_readback",
            "query_start_save","query_start_readback","reference_query","reference_shape","query_result_save","query_result_readback","context_recheck","final_save","final_readback"}
        _need(value["disposition"]=="refused_no_retry" and type(value["stop_stage"]) is str and value["stop_stage"] in stages and (not value["own_error_receipt_acknowledged"]
            or value["stop_stage"] not in {"kernel_claim","retained_context","construct","project","symbol_reconstruction","key_precheck"}),"reference_ack_refusal_state")
    return value


class _ArgumentParser(argparse.ArgumentParser):
    def error(self,message):self.exit(2,"reference_argument_refused\n")


def main(argv=None):
    parser=_ArgumentParser(description=__doc__);parser.add_argument("--expected-head",required=True);args=parser.parse_args(argv)
    try:result=prepare_actual_cell(args.expected_head)
    except BaseException:print('{"disposition":"reference_local_preparation_refused"}');return 2
    print(_raw({key:value for key,value in result.items() if key!="cell_source"}).decode());return 0


if __name__=="__main__":raise SystemExit(main())
