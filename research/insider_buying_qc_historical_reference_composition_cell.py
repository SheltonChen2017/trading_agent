"""Prepare a zero-SDK, cloud-only join of the completed reference contexts.

This successor neither repeats a query nor reads an Object Store receipt. It
validates the retained CIK/reference chains and preserves every candidate edge,
zero, duplicate, raw field state and returned index label. A numeric CIK match
is only a comparison of retained declared identifiers, never a title/SID/PIT,
listing, availability, rights or readiness admission. All comparisons, values,
cardinalities and derived digests stay in the kernel. Only own execution-control
metadata may leave it. Ordinary globals are not authenticated immutable storage.

Run the trusted local parent directly, not inside another Seatbelt profile:
its source-only child applies the strong native policy before source checks.
No local helper imports the SDK or reads actual business/credential artifacts.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import sys

from research import insider_buying_qc_historical_reference_cell as previous


SELF_PATH="research/insider_buying_qc_historical_reference_composition_cell.py"
TEST_PATH="tests/test_insider_buying_qc_historical_reference_composition_cell.py"
SCHEMA="insider-qc-historical-reference-composition-v1"
AUDIT_ID="ib-qc-first64-historical-reference-composition-20261025-once"
NOTEBOOK=previous.NOTEBOOK
PROJECT_ID=previous.PROJECT_ID
CELL_INDEX=2
ARTIFACT_PARTS=("artifacts","insider_buying","qc_historical_reference_composition_v1")
EMPTY_CACHE_PREFIX="/var/empty/insider-qc-historical-reference-composition-no-bytecode"
LOCK_BYTES=b"INSETF-QC-retained-reference-composition-permanent-intent-v1\n"
MAX_CONTROL_BYTES,MAX_CELL_BYTES=256*1024,64*1024
LANE_ROOT,LANE_BRANCH=previous.LANE_ROOT,previous.LANE_BRANCH
publication,sources=previous.publication,previous.sources
_raw,_sha,_decode=previous._raw,previous._sha,previous._decode
REFERENCE_NONCE="80d684adcb9788f78af2622f4097c383eba2718ddb80066b41f750e9bec22769"
REFERENCE_HEAD="586d3ef38700f4a963488d70b29736e03f0b4a85"
REFERENCE_SOURCE_SHA256="3f2ad607b75e5f8e1d774898e96a1c79141b08666990d1421b1204d01e52350f"
REFERENCE_TEST_SHA256="08d02b62a4b480ae0f2cecf9e2473ee38c716389ed4d4f8d68a9782730846d54"
REFERENCE_OBSERVATION={
    "basis":"trusted-main-observed-own-controls-record276; not reopened by this preparer",
    "execution_head":REFERENCE_HEAD,"source_path":previous.SELF_PATH,"source_sha256":REFERENCE_SOURCE_SHA256,
    "test_path":previous.TEST_PATH,"test_sha256":REFERENCE_TEST_SHA256,"nonce":REFERENCE_NONCE,
    "source_inventory_sha256":"8e635a57ef61e45f73036f7482476be1b2c6f13cf09d3eb01ae5e7396d82898e",
    "core_sha256":"54cda8175ceafc5bec6c3f6f90c31c43bcd0daad991262a42d13415736760fd2",
    "cell_sha256":"0a55a8c95927849da9353a821de14e834fbc750fb1110b94a82b82410ff9a2cb",
    "registration_sha256":"36f256d2afc9403ddba3a49d1b204add18fbccdece7b9bde7c5a1f531708bba1",
    "intent_sha256":"cd286d5c237aa849854b49b82cdee49037f35c36b6a98cde3cd1674cbacd0517",
    "ready_sha256":"76d5d2bd7ef3d69badcb25597c8b48edf89a9f85528f66d2bfb618fee47e450e",
    "acknowledgement_sha256":"633d9096557f492eaba7d5e3c12125960d5d45f501ba68d6fa40f97b3dcf2168",
    "acknowledgement_bytes":782,"own_final_receipt_acknowledged":True,"own_error_receipt_acknowledged":False,
    "stop_stage":None,"independent_persistence_or_platform_origin_established":False}


class ReferenceCompositionError(ValueError):
    """Finite own-control classifications, never supplied/private exception text."""


def _need(value,code):
    if not value:raise ReferenceCompositionError(code)


def _reference_registration(fixture):
    if fixture:
        return _decode(previous.build_invented_cell(REFERENCE_NONCE)[0])
    value={"schema":previous.SCHEMA+"/registration","audit_id":previous.AUDIT_ID,"project_id":PROJECT_ID,
        "execution_notebook":NOTEBOOK,"execution_cell_index":1,"nonce":REFERENCE_NONCE,
        "prefix":f"{PROJECT_ID}/{previous.AUDIT_ID}/{REFERENCE_NONCE}","fixture_only":False,
        "core_sha256":REFERENCE_OBSERVATION["core_sha256"],"source_provenance":previous._provenance(False),
        "preparation_source":{"head":REFERENCE_HEAD,"source_path":previous.SELF_PATH,
            "source_sha256":REFERENCE_SOURCE_SHA256,"source_inventory_sha256":REFERENCE_OBSERVATION["source_inventory_sha256"]},
        "scope":previous._scope()}
    _need(_sha(_raw(value))==REFERENCE_OBSERVATION["registration_sha256"]
        and _sha(previous._core(False).encode())==value["core_sha256"],"composition_original_registration_changed")
    return value


def _provenance(fixture):
    observed=_decode(_raw(REFERENCE_OBSERVATION))
    if fixture:observed={**observed,"basis":"invented own controls; no actual reference observation","execution_head":"a"*40}
    return {"reference":observed,"reference_registration":_reference_registration(fixture)}


def _scope():
    return {"source_cik_rows":51,"maximum_candidate_edges":512,"maximum_candidates_per_cik":16,
        "selectors":list(previous.SELECTORS),"reference_date":"2021-03-31","maximum_reference_context_bytes":8388608,
        "maximum_composition_bytes":16777216,"SDK_calls":0,"ObjectStore_reads_saves_deletes":0,
        "resolver_fundamental_history_price_outcome_calls":0,"original_cells_reexecuted":0,
        "retry_resume_reset_fallback":False,"all_values_counts_comparisons_and_digests_stay_cloud":True,
        "CIK_comparison":"positive ASCII digit text of 1..10 digits or exact integer; canonical ten-digit comparison; preserve original",
        "no_security_title_mapping_or_PIT_admission":True,"boundary_checks_not_continuous_immutability":True,
        "kernel_graph_storage":"volatile_existing_namespace_not_durable_or_independent_persistence"}


CORE_SOURCE='''def _ib_reference_compose(_text,_registration_sha,_expected_core_sha):
    import hashlib
    import json
    from datetime import datetime
    class _Stop(Exception): pass
    def require(value):
        if not value:raise _Stop()
    def raw(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)
    def sha(value):return hashlib.sha256(raw(value).encode()).hexdigest()
    def copy(value):return json.loads(raw(value))
    def text(value,limit):return type(value) is str and len(value)<=limit and all(32<=ord(c)<=126 for c in value)
    def same(left,right):require(raw(left)==raw(right))
    def decode(value):
        require(type(value) is str and 0<len(value.encode())<=262144)
        def pairs(items):
            result={}
            for key,item in items:require(key not in result);result[key]=item
            return result
        result=json.loads(value,object_pairs_hook=pairs,parse_constant=lambda _:require(False))
        require(type(result) is dict and raw(result)==value);return result
    authority={"retained_declared_identifier_comparison_only":True,"historical_cik_association_proven":False,
        "security_title_or_class_mapping_admitted":False,"first_listing_verified":False,"historical_absence_proven":False,
        "point_in_time_verified":False,"publication_or_original_availability_verified":False,"vendor_backfill_excluded":False,
        "canonical_admitted":False,"rights_verified":False,"backtesting_ready":False}
    ack={"schema":"insider-qc-historical-reference-composition-v1/acknowledgement","disposition":"registration_refused"}
    stage="registration"
    try:
        r=decode(_text);require(hashlib.sha256(_text.encode()).hexdigest()==_registration_sha)
        require(set(r)=={"schema","audit_id","project_id","execution_notebook","execution_cell_index","nonce","prefix","fixture_only","core_sha256","source_provenance","preparation_source","scope"})
        require(r["schema"]=="insider-qc-historical-reference-composition-v1/registration" and r["audit_id"]=="ib-qc-first64-historical-reference-composition-20261025-once")
        require(type(r["project_id"]) is int and r["project_id"]==37465795 and r["execution_notebook"]=="ib_qc_cik_consumer_20261025.ipynb")
        require(type(r["execution_cell_index"]) is int and r["execution_cell_index"]==2 and r["fixture_only"] is __FIXTURE__)
        require(type(r["nonce"]) is str and len(r["nonce"])==64 and all(c in "0123456789abcdef" for c in r["nonce"]))
        require(r["prefix"]=="37465795/ib-qc-first64-historical-reference-composition-20261025-once/"+r["nonce"] and r["core_sha256"]==_expected_core_sha)
        same(r["source_provenance"],__PROVENANCE__);same(r["scope"],__SCOPE__)
        p=r["preparation_source"]
        require(type(p) is dict and set(p)=={"head","source_path","source_sha256","source_inventory_sha256"} and p["source_path"]=="research/insider_buying_qc_historical_reference_composition_cell.py")
        for name,length in (("head",40),("source_sha256",64),("source_inventory_sha256",64)):
            require(type(p[name]) is str and len(p[name])==length and all(c in "0123456789abcdef" for c in p[name]))
        ack={"schema":"insider-qc-historical-reference-composition-v1/acknowledgement","audit_id":r["audit_id"],"project_id":37465795,
            "execution_notebook":r["execution_notebook"],"execution_cell_index":2,"registration_sha256":_registration_sha,
            "core_sha256":r["core_sha256"],"prefix":r["prefix"],"fixture_only":r["fixture_only"],
            "disposition":"refused_no_retry","stop_stage":None,"own_composition_published":False,
            "SDK_or_store_calls":0,"platform_values_counts_comparisons_or_digests_exported":False,"backtesting_ready":False}
        stage="kernel_claim";marker="_ib_reference_composition_"+r["nonce"]
        require(marker not in globals());globals()[marker]=True
        stage="retained_context"
        old_ref=r["source_provenance"]["reference_registration"];old=__PRODUCER_REGISTRATION__
        original_nonce=old_ref["source_provenance"]["producer"]["nonce"]
        consumer_nonce=old_ref["source_provenance"]["consumer"]["nonce"]
        reference_nonce=old_ref["nonce"]
        keys=["_ib_cik_consume_"+original_nonce,"_ib_cik_new_consumer_"+consumer_nonce,"_ib_historical_reference_"+reference_nonce]
        require(all(globals().get(key) is True for key in keys))
        rows=globals().get("_ib_cik_retained_"+original_nonce)
        retained=globals().get("_ib_historical_reference_retained_"+reference_nonce)
        require(type(rows) is list and len(rows)==51 and type(retained) is dict and set(retained)=={"start","results","final"})
        stage="context_shape"
        old_authority={"candidate_only":True,"historical_absence_proven":False,"historical_cik_association_proven":False,
            "share_class_verified":False,"listing_verified":False,"point_in_time_verified":False,"canonical_admitted":False,"backtesting_ready":False}
        old_start={"schema":"insider-qc-cik-candidates-v1/start","registration_sha256":sha(old),"core_sha256":old["core_sha256"],
            "ciks_sha256":old["ciks_sha256"],"source_provenance":old["source_provenance"],"lookup_date":"2021-03-31","authority":old_authority}
        sid_values={};edges=[]
        for ordinal,(row,cik) in enumerate(zip(rows,old["ciks"]),1):
            require(type(row) is dict and set(row)=={"schema","ordinal","raw_cik","lookup_started_sha256","candidates","duplicate_sids","resolver_returned_zero","authority"})
            begun={"schema":"insider-qc-cik-candidates-v1/lookup-started","ordinal":ordinal,"raw_cik":cik,"parameter_cik":int(cik),
                "lookup_date":"2021-03-31","start_sha256":sha(old_start),"maximum_attempts":1}
            candidates=row["candidates"];require(type(candidates) is list and len(candidates)<=16);ids=[]
            for position,candidate in enumerate(candidates,1):
                require(type(candidate) is dict and set(candidate)=={"sid","symbol_value","security_type"} and candidate["security_type"]=="Equity")
                require(text(candidate["sid"],512) and candidate["sid"] and text(candidate["symbol_value"],128) and candidate["symbol_value"])
                sid,value=candidate["sid"],candidate["symbol_value"];ids.append(sid)
                require(sid not in sid_values or sid_values[sid]==value);sid_values[sid]=value
                edges.append({"cik_ordinal":ordinal,"candidate_ordinal":position,"raw_cik":cik,"sid":sid,"saved_symbol_value":value})
            same(row,{"schema":"insider-qc-cik-candidates-v1/lookup-result","ordinal":ordinal,"raw_cik":cik,
                "lookup_started_sha256":sha(begun),"candidates":candidates,"duplicate_sids":sorted({sid for sid in ids if ids.count(sid)>1}),
                "resolver_returned_zero":not candidates,"authority":old_authority})
            require(len(edges)<=512)
        require(1<=len(sid_values)<=512);ordered_sids=sorted(sid_values)
        ref_authority={"reference_corroboration_only":True,"historical_absence_proven":False,"point_in_time_verified":False,
            "listing_verified":False,"share_class_verified":False,"publication_or_original_availability_verified":False,
            "vendor_backfill_excluded":False,"canonical_admitted":False,"rights_verified":False,"backtesting_ready":False}
        expected_start={"schema":"insider-qc-historical-reference-v1/start","registration_sha256":sha(old_ref),"core_sha256":old_ref["core_sha256"],
            "source_provenance":old_ref["source_provenance"],"retained_rows_sha256":sha(rows),"ordered_sids":ordered_sids,
            "candidate_edges":edges,"scope":old_ref["scope"],"authority":ref_authority}
        same(retained["start"],expected_start);start_sha=sha(expected_start)
        results=retained["results"];require(type(results) is list and len(results)==4)
        for ordinal,(result,selector) in enumerate(zip(results,r["scope"]["selectors"]),1):
            require(type(result) is dict and set(result)=={"schema","ordinal","selector","query_started_sha256","returned_index","observations","raw_missing_ambiguous_or_default_values_not_repaired","authority"})
            begun={"schema":"insider-qc-historical-reference-v1/query-started","ordinal":ordinal,"selector":selector,"start_sha256":start_sha,
                "date_start_inclusive":"2021-03-31","date_end_inclusive":"2021-03-31","ordered_sids_sha256":sha(ordered_sids),"maximum_attempts":1}
            require(result["schema"]=="insider-qc-historical-reference-v1/query-result" and type(result["ordinal"]) is int
                and result["ordinal"]==ordinal and result["selector"]==selector and result["query_started_sha256"]==sha(begun)
                and result["raw_missing_ambiguous_or_default_values_not_repaired"] is True)
            same(result["authority"],ref_authority)
            stamps=result["returned_index"];require(type(stamps) is list and len(stamps)<=1)
            for stamp in stamps:
                require(type(stamp) is dict and set(stamp)=={"returned_index_isoformat","timezone_label","index_semantics","record_Time_or_EndTime_not_exposed_by_dataframe","availability_before_entry_verified"})
                value=stamp["returned_index_isoformat"];require(text(value,128) and value)
                instant=datetime.fromisoformat(value);require(instant.date().isoformat() in old_ref["scope"]["allowlisted_returned_index_dates"]
                    and (instant.hour,instant.minute,instant.second,instant.microsecond)==(0,0,0,0) and instant.isoformat()==value)
                require(text(stamp["timezone_label"],128) and stamp["timezone_label"]
                    and stamp["record_Time_or_EndTime_not_exposed_by_dataframe"] is True and stamp["availability_before_entry_verified"] is False)
                require(stamp["index_semantics"]=="date label or documented current-public-source EndTime=T+1; never availability")
            observations=result["observations"];require(type(observations) is list and len(observations)==len(ordered_sids))
            for observation,sid in zip(observations,ordered_sids):
                require(type(observation) is dict and set(observation)=={"sid","reference"} and observation["sid"]==sid)
                value=observation["reference"];require(type(value) is dict and type(value.get("state")) is str)
                state=value["state"]
                if state in {"no_record_returned","column_not_returned","missing_value"}:
                    require(set(value)=={"state"} and (state=="no_record_returned")== (not stamps))
                else:
                    require(stamps and set(value)=={"state","kind","value"} and state=="declared_value")
                    kind,item=value["kind"],value["value"]
                    if kind=="boolean":require(selector=="SecurityReference.IsPrimaryShare" and type(item) is bool)
                    elif kind=="integer":require(selector=="CompanyReference.CIK" and type(item) is int and 0<=item<=9999999999)
                    else:require(kind=="text" and text(item,64) and selector!="SecurityReference.IsPrimaryShare")
        same(retained["final"],{"schema":"insider-qc-historical-reference-v1/final","registration_sha256":sha(old_ref),"start_sha256":start_sha,
            "query_result_sha256":[sha(result) for result in results],"candidate_edges_sha256":sha(edges),
            "all_four_fixed_queries_completed":True,"source_context_boundary_checks_match":True,"authority":ref_authority})
        require(len(raw(retained).encode())<=8388608)
        row_hash,reference_hash=sha(rows),sha(retained)
        def check_context():
            nonlocal stage
            stage="source_recheck"
            require(globals().get("_ib_cik_retained_"+original_nonce) is rows and sha(rows)==row_hash
                and globals().get("_ib_historical_reference_retained_"+reference_nonce) is retained and sha(retained)==reference_hash
                and all(globals().get(key) is True for key in keys))
        check_context();stage="comparison"
        fields={result["selector"]:{item["sid"]:item["reference"] for item in result["observations"]} for result in results}
        compared=[]
        for edge in edges:
            value=fields["CompanyReference.CIK"][edge["sid"]];normalized=None
            if value["state"]!="declared_value":disposition="reference_missing_or_unreturned"
            else:
                item=value["value"]
                if value["kind"]=="integer":normalized=str(item).zfill(10) if item>0 else None
                elif value["kind"]=="text" and 1<=len(item)<=10 and all("0"<=c<="9" for c in item) and int(item)>0:
                    normalized=item.zfill(10)
                disposition=("declared_cik_matches_expected" if normalized==edge["raw_cik"] else "declared_cik_differs" if normalized else "declared_cik_malformed_or_zero")
            compared.append({**edge,"declared_cik_comparison":disposition,"canonical_declared_cik":normalized,
                "raw_reference_fields":{selector:copy(values[edge["sid"]]) for selector,values in fields.items()}})
        output={"schema":"insider-qc-historical-reference-composition-v1/private-composition","registration_sha256":_registration_sha,
            "original_candidate_rows":copy(rows),"original_historical_reference":copy(retained),"edge_assessments":compared,
            "source_rows_sha256":row_hash,"reference_context_sha256":reference_hash,"edge_assessments_sha256":sha(compared),
            "zero_candidate_rows_preserved":True,"duplicates_and_cross_cik_edges_preserved":True,"no_candidates_silently_selected_or_dropped":True,
            "all_four_raw_states_and_returned_index_labels_preserved":True,"boundary_checks_not_continuous_immutability":True,
            "kernel_graph_storage":"volatile_existing_namespace_not_durable_or_independent_persistence","authority":authority}
        require(len(raw(output).encode())<=16777216);output_hash=sha(output)
        check_context();stage="publication";result_key="_ib_reference_composed_"+r["nonce"]
        require(result_key not in globals());globals()[result_key]=output
        check_context();stage="publication_recheck"
        require(globals().get(result_key) is output and sha(output)==output_hash)
        ack["own_composition_published"]=True;ack["disposition"]="retained_reference_composition_completed"
    except BaseException:
        if ack["disposition"]!="registration_refused":ack["stop_stage"]=stage
    print(raw(ack))
'''


def _core(fixture):
    return CORE_SOURCE.replace("__FIXTURE__",repr(fixture)).replace("__PROVENANCE__",repr(_provenance(fixture))).replace(
        "__SCOPE__",repr(_scope())).replace("__PRODUCER_REGISTRATION__",repr(previous.producer._registration(previous.consumer.PRODUCER_NONCE,fixture)))


def _source_identity(value,root):
    _need(type(value) is dict and set(value)=={"root","branch","head","clean","source_sha256","source_inventory_sha256"}
        and value["root"]==str(root) and value["branch"]==LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and previous.producer.control._HEAD.fullmatch(value["head"])
        and type(value["source_sha256"]) is dict and 2<=len(value["source_sha256"])<=2048 and {SELF_PATH,TEST_PATH}<=set(value["source_sha256"])
        and all(type(name) is str and len(name)<=512 and previous.producer.control._SOURCE.fullmatch(name) and Path(name).as_posix()==name
            and ".." not in Path(name).parts and type(digest) is str and previous.producer.control._SHA.fullmatch(digest) for name,digest in value["source_sha256"].items())
        and value["source_inventory_sha256"]==_sha(_raw(value["source_sha256"])),"composition_source_identity_refused")
    return value


def _registration(nonce,fixture,identity):
    _need(type(nonce) is str and previous.producer.control._SHA.fullmatch(nonce) and type(fixture) is bool,"composition_nonce_or_mode_refused")
    _source_identity(identity,Path(identity["root"]))
    return {"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,"project_id":PROJECT_ID,"execution_notebook":NOTEBOOK,"execution_cell_index":CELL_INDEX,
        "nonce":nonce,"prefix":f"{PROJECT_ID}/{AUDIT_ID}/{nonce}","fixture_only":fixture,"core_sha256":_sha(_core(fixture).encode()),
        "source_provenance":_provenance(fixture),"preparation_source":{"head":identity["head"],"source_path":SELF_PATH,
            "source_sha256":identity["source_sha256"][SELF_PATH],"source_inventory_sha256":identity["source_inventory_sha256"]},"scope":_scope()}


def _cell(nonce,fixture,identity):
    registration=_raw(_registration(nonce,fixture,identity))
    cell=(_core(fixture)+"\n_ib_reference_compose("+repr(registration.decode())+","+repr(_sha(registration))+","+repr(_sha(_core(fixture).encode()))+")\n").encode()
    _need(0<len(cell)<=MAX_CELL_BYTES,"composition_cell_capacity_refused");compile(cell,"<fixed-retained-reference-composition>","exec")
    return registration,cell


def _invented_identity(root):
    inventory={SELF_PATH:"a"*64,TEST_PATH:"b"*64,**{f"data/invented_{i:03}.py":"c"*64 for i in range(108)}}
    return {"root":str(root),"branch":LANE_BRANCH,"head":"a"*40,"clean":True,"source_sha256":inventory,"source_inventory_sha256":_sha(_raw(inventory))}


def build_invented_cell(nonce,*,root=Path("/invented-reference-composition")):
    return _cell(nonce,True,_invented_identity(root))


def _current(identity):
    _source_identity(identity,LANE_ROOT);previous._current(identity)
    _need(identity["source_sha256"].get(previous.SELF_PATH)==REFERENCE_SOURCE_SHA256
        and identity["source_sha256"].get(previous.TEST_PATH)==REFERENCE_TEST_SHA256,"composition_original_source_changed")


def _identity(head):
    _need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"fixed_composition_source_required")
    value=previous._identity(head);own=sources.custody._source_bytes(LANE_ROOT,(SELF_PATH,TEST_PATH))
    for name,digest in own.items():_need(_sha(sources.custody._git(LANE_ROOT,"show",head+":"+name))==digest,"composition_uncommitted_source")
    for name,digest in ((previous.SELF_PATH,REFERENCE_SOURCE_SHA256),(previous.TEST_PATH,REFERENCE_TEST_SHA256)):
        _need(_sha(sources.custody._git(LANE_ROOT,"show",REFERENCE_HEAD+":"+name))==digest,"composition_original_Git_source_changed")
    inventory={**value["source_sha256"],**own};value=_source_identity({**value,"source_sha256":inventory,"source_inventory_sha256":_sha(_raw(inventory))},LANE_ROOT)
    _current(value);return value


def _isolated():
    _need(sys.flags.isolated==sys.flags.no_site==sys.flags.no_user_site==sys.flags.dont_write_bytecode==1
        and sys.pycache_prefix==EMPTY_CACHE_PREFIX,"composition_initial_isolation_required")


def _proof(identity,fixture):
    return {"schema":SCHEMA+"/source-preflight","fixture_only":fixture,"source_inventory_sha256":identity["source_inventory_sha256"],
        "source_count":len(identity["source_sha256"]),"native_network_fork_allwrite_securityexec_denial":not fixture,
        "current_frozen_loaded_and_original_sources_verified":not fixture,"SDK_artifact_credential_or_QC_accesses":0}


def _intent(identity,r,cell,proof,fixture):
    registration=_decode(r)
    return {"schema":SCHEMA+"/permanent-local-intent","audit_id":AUDIT_ID,"fixture_only":fixture,"execution_identity":identity,
        "registration_sha256":_sha(r),"core_sha256":registration["core_sha256"],"cell_sha256":_sha(cell),"cell_bytes":len(cell),
        "project_id":PROJECT_ID,"execution_notebook":NOTEBOOK,"execution_cell_index":CELL_INDEX,"prefix":registration["prefix"],
        "source_provenance":registration["source_provenance"],"source_preflight":proof,"local_scope_permanently_consumed":True,
        "maximum_selected_cell_executions":1,"no_retry_even_after_kernel_reset":True,"old_scope_reset_or_recovered":False,
        "cloud_execution_observed":False,"SDK_artifact_credential_or_QC_accesses_by_preparer":0,"backtesting_ready":False}


def _capacity(identity,fixture):
    r,cell=_cell("0"*64,fixture,identity)
    for value in (identity,_decode(r),_intent(identity,r,cell,_proof(identity,fixture),fixture)):
        raw=_raw(value);_need(0<len(raw)<=MAX_CONTROL_BYTES and _raw(_decode(raw))==raw,"composition_control_capacity_refused")


def _worker(identity):
    _isolated();sources._prove_isolation();_current(identity);_capacity(identity,False);_current(identity);return _proof(identity,False)


def _source_preflight(identity):
    code=("import sys;sys.path.insert(0,"+repr(str(LANE_ROOT))+");import json;from research import insider_buying_qc_historical_reference_composition_cell as m;identity=json.loads("+repr(_raw(identity).decode())+");"
        "\ntry: result=m._worker(identity)\nexcept BaseException: print('{\"disposition\":\"composition_source_preflight_refused\"}');sys.exit(2)\nprint(m._raw(result).decode())")
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    command=("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","LANG=C","LC_ALL=C","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)
    child=sources.launcher.run_child(command,cwd=LANE_ROOT,env=None,timeout=60,cap=8192)
    _need(child.returncode==0 and child.stderr==b"" and child.stdout==_raw(_proof(identity,False))+b"\n","composition_source_preflight_refused")
    return _proof(identity,False)


def _prepare(root,identity,*,fixture,guard,preflight,nonce_factory):
    _need(type(fixture) is bool and callable(guard) and callable(preflight) and callable(nonce_factory),"composition_preparation_mode_refused")
    if fixture:
        publication._fixture_root(root);publication._native_fixture_denial()
        _need(preflight is not _source_preflight and nonce_factory is not secrets.token_hex,"invented_composition_callbacks_required")
    else:_need(root==LANE_ROOT and preflight is _source_preflight and nonce_factory is secrets.token_hex,"fixed_composition_preparer_required")
    _source_identity(identity,root);_capacity(identity,fixture);guard();proof=preflight(identity)
    _need(_raw(proof)==_raw(_proof(identity,fixture)),"composition_native_preflight_refused");guard();chain=folder=None
    try:
        chain=sources.custody._Chain(root,ARTIFACT_PARTS,create=True,exclusive_last=True)
        folder=publication._NewDirectory(root.joinpath(*ARTIFACT_PARTS));expected=set()
        def check():
            guard();chain.recheck();folder.check();_need(set(os.listdir(folder.fd))==expected,"composition_output_inventory_changed")
        def publish(name,raw,cap=MAX_CONTROL_BYTES):
            check();digest=folder.publish(name,raw,cap=cap);expected.add(name);check();return digest
        publish("scope.lock",LOCK_BYTES);r,cell=_cell(nonce_factory(32),fixture,identity)
        registration_sha=publish("registration.json",r);cell_sha=publish("cell.py",cell,MAX_CELL_BYTES)
        intent_sha=publish("intent.json",_raw(_intent(identity,r,cell,proof,fixture)));registration=_decode(r)
        ready={"schema":SCHEMA+"/prepared-not-executed","audit_id":AUDIT_ID,"fixture_only":fixture,"registration_sha256":registration_sha,
            "cell_sha256":cell_sha,"cell_bytes":len(cell),"intent_sha256":intent_sha,"core_sha256":registration["core_sha256"],
            "project_id":PROJECT_ID,"execution_notebook":NOTEBOOK,"execution_cell_index":CELL_INDEX,"prefix":registration["prefix"],
            "local_scope_permanently_consumed":True,"cloud_execution_observed":False,"SDK_artifact_credential_or_QC_accesses":0,"backtesting_ready":False}
        ready_sha=publish("ready.json",_raw(ready));check()
        return {**ready,"ready_sha256":ready_sha,"cell_source":cell.decode(),"cell_path":str(folder.path/"cell.py"),"intent_path":str(folder.path/"intent.json")}
    finally:publication._close_all((folder,chain),None,None,False)


def prepare_actual_cell(expected_head):
    _isolated();before=_identity(expected_head)
    def guard():_need(_identity(expected_head)==before,"composition_committed_source_changed")
    return _prepare(LANE_ROOT,before,fixture=False,guard=guard,preflight=_source_preflight,nonce_factory=secrets.token_hex)


def prepare_invented_cell(root,*,nonce="a"*64,guard=lambda:None,preflight=None):
    root=Path(root);identity=_invented_identity(root)
    return _prepare(root,identity,fixture=True,guard=guard,preflight=(lambda i:_proof(i,True)) if preflight is None else preflight,
        nonce_factory=lambda count:nonce if count==32 else _need(False,"composition_nonce_length"))


def validate_acknowledgement(raw,*,registration_raw):
    _need(type(raw) is bytes and 0<len(raw)<=8192,"composition_ack_bound")
    r=_decode(registration_raw);_need(type(r) is dict,"composition_registration_refused")
    # Regenerate the exact own image, not a caller-defined weaker scope.
    p=r.get("preparation_source");_need(type(p) is dict and set(p)=={"head","source_path","source_sha256","source_inventory_sha256"},"composition_registration_source_refused")
    _need(p["source_path"]==SELF_PATH and type(p["head"]) is str and previous.producer.control._HEAD.fullmatch(p["head"])
        and all(type(p[name]) is str and previous.producer.control._SHA.fullmatch(p[name]) for name in ("source_sha256","source_inventory_sha256")),"composition_registration_source_refused")
    fixed_registration={"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,"project_id":PROJECT_ID,"execution_notebook":NOTEBOOK,
        "execution_cell_index":CELL_INDEX,"nonce":r.get("nonce"),"prefix":f"{PROJECT_ID}/{AUDIT_ID}/{r.get('nonce')}","fixture_only":r.get("fixture_only"),
        "core_sha256":_sha(_core(r.get("fixture_only")).encode()),"source_provenance":_provenance(r.get("fixture_only")),"preparation_source":p,"scope":_scope()}
    _need(type(r.get("nonce")) is str and previous.producer.control._SHA.fullmatch(r["nonce"]) and type(r.get("fixture_only")) is bool
        and _raw(r)==_raw(fixed_registration),"composition_registration_refused")
    fixed={"schema":SCHEMA+"/acknowledgement","audit_id":AUDIT_ID,"project_id":PROJECT_ID,"execution_notebook":NOTEBOOK,"execution_cell_index":CELL_INDEX,
        "registration_sha256":_sha(registration_raw),"core_sha256":r["core_sha256"],"prefix":r["prefix"],"fixture_only":r["fixture_only"],
        "SDK_or_store_calls":0,"platform_values_counts_comparisons_or_digests_exported":False,"backtesting_ready":False}
    value=_decode(raw.removesuffix(b"\n"));dynamic={"disposition","stop_stage","own_composition_published"}
    _need(type(value) is dict and set(value)==set(fixed)|dynamic and _raw({key:value[key] for key in fixed})==_raw(fixed)
        and type(value["own_composition_published"]) is bool,"composition_ack_schema_refused")
    if value["own_composition_published"]:
        _need(value["disposition"]=="retained_reference_composition_completed" and value["stop_stage"] is None,"composition_ack_false_completion")
    else:_need(value["disposition"]=="refused_no_retry" and type(value["stop_stage"]) is str
        and value["stop_stage"] in {"kernel_claim","retained_context","context_shape","source_recheck","comparison","publication","publication_recheck"},"composition_ack_refusal_state")
    return value


class _ArgumentParser(argparse.ArgumentParser):
    def error(self,message):self.exit(2,"composition_argument_refused\n")


def main(argv=None):
    parser=_ArgumentParser(description=__doc__);parser.add_argument("--expected-head",required=True);args=parser.parse_args(argv)
    try:result=prepare_actual_cell(args.expected_head)
    except BaseException:print('{"disposition":"composition_local_preparation_refused"}');return 2
    print(_raw({key:value for key,value in result.items() if key!="cell_source"}).decode());return 0


if __name__=="__main__":raise SystemExit(main())
