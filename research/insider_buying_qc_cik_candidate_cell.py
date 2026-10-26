"""Inert preparation for one cloud-only, non-PIT CIK candidate diagnostic.

No local helper imports the QC SDK, reads a dataset/identity artifact or a
credential, or executes cloud code. Own source/intent controls are read back.
Only the separately activated generated cell can call the resolver.
Returned candidates, cardinalities and their digests stay inside QC. Zero is
not historical absence; the resolver's last-ticker fallback is not listing/PIT
evidence. ObjectStore precheck/save is not atomic create or immutability.
"resolver_calls_completed" means fully iterated, shape-validated result rows;
neither that counter nor "attempted" is a measured backend HTTP request count.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import sys

from research import insider_buying_qc_cloud_control_cell as control


SELF_PATH = "research/insider_buying_qc_cik_candidate_cell.py"
TEST_PATH = "tests/test_insider_buying_qc_cik_candidate_cell.py"
SCHEMA = "insider-qc-cik-candidates-v1"
AUDIT_ID = "ib-qc-first64-cik-candidates-20261025-once"
PROJECT_ID = 37465795
NOTEBOOK = "ib_qc_cik_candidates_20261025.ipynb"
ARTIFACT_PARTS = ("artifacts", "insider_buying", "qc_cik_candidates_v1")
EMPTY_CACHE_PREFIX = "/var/empty/insider-qc-cik-candidates-no-bytecode"
LANE_ROOT, LANE_BRANCH = control.LANE_ROOT, control.LANE_BRANCH
MAX_CONTROL_BYTES, MAX_CELL_BYTES = 256 * 1024, 64 * 1024
LOCK_BYTES = b"INSETF-QC-first64-CIK-candidates-permanent-local-intent-v1\n"
CIKS = ("0000006281","0000019612","0000070318","0000072573","0000100885","0000716634",
    "0000737468","0000844856","0000861838","0000874866","0000877890","0000908255",
    "0000946673","0001015328","0001018840","0001058090","0001082923","0001084554",
    "0001124610","0001133818","0001136893","0001141391","0001171759","0001177394",
    "0001178253","0001287865","0001305323","0001309108","0001314152","0001320695",
    "0001379785","0001423689","0001438423","0001506293","0001533998","0001555280",
    "0001593034","0001640147","0001640455","0001671933","0001676479","0001682265",
    "0001709768","0001710072","0001740547","0001741231","0001773751","0001792580",
    "0001805284","0001831270","0001831617")
SOURCE_PROVENANCE = {
    "basis":"trusted-main-observed-assessment-metadata; not reopened by this preparer",
    "selected_parents":64,"assessment_execution_head":"7458c598b97f61a21d1c2023ef8451bf1afa6740",
    "assessment_sha256":"f0a2cac2773c6b79b2d82c4e82264009ec8ce52189c77d0dbd7d0e56cf2d842f",
    "ordered_rows_sha256":"91f7b1d5703cc5168c63d28f2260ad44199d953879b4018744bb05aadb604e11",
    "capture_head":"1bb03b8ee44088cad82872c12a6cd7f38e9ef961",
    "capture_report_sha256":"a407d79f06e8257a9a7344a8a64398547e0e51209eae169e4acaa58b92839749",
    "capture_source_inventory_sha256":"908600f5c405dcc4fe21c7a77c7c1bb58e9c3d98be8dd8fd02d3b3beefaa284a",
    "assessment_source_inventory_sha256":"709fa92cb2f30ddc485de553cf0b17cb8ab2e904ffb09902c80f78f435f8c910"}
publication, sources = control.publication, control.sources
_raw, _sha, _decode = control._raw, control._sha, control._decode
CIKS_SHA256 = _sha(_raw(list(CIKS)))


class CikCandidateError(ValueError):
    """Sanitized own-control codes only."""


def _need(value, code):
    if not value: raise CikCandidateError(code)


CORE_SOURCE = '''def _ib_cik_run(_factory, _registration_text, _registration_sha256, _consume=False):
    import contextlib
    import hashlib
    import json
    from datetime import datetime
    class _Discard:
        def write(self, value): return len(value)
        def flush(self): return None
    class _Stop(Exception): pass
    def raw(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    def sha(text): return hashlib.sha256(text.encode()).hexdigest()
    def require(value):
        if not value: raise _Stop()
    def decode(text):
        require(type(text) is str and 0 < len(text.encode()) <= 524288)
        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result); result[key] = value
            return result
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=lambda _: require(False))
        require(type(value) is dict and raw(value) == text)
        return value
    authority = {"candidate_only":True,"historical_absence_proven":False,"historical_cik_association_proven":False,
        "share_class_verified":False,"listing_verified":False,"point_in_time_verified":False,
        "canonical_admitted":False,"backtesting_ready":False}
    ack = {"schema":"insider-qc-cik-candidates-v1/acknowledgement","disposition":"registration_refused"}
    stage, store, fresh_all = ["registration"], None, False
    try:
        r = decode(_registration_text)
        require(sha(_registration_text) == _registration_sha256)
        require(set(r) == {"schema","audit_id","project_id","notebook","cell_index","nonce","prefix","fixture_only","core_sha256","ciks","ciks_sha256","source_provenance","scope"})
        require(r["schema"] == "insider-qc-cik-candidates-v1/registration" and r["audit_id"] == "ib-qc-first64-cik-candidates-20261025-once")
        require(type(r["project_id"]) is int and r["project_id"] == 37465795 and r["notebook"] == "ib_qc_cik_candidates_20261025.ipynb")
        require(type(r["cell_index"]) is int and r["cell_index"] == 0 and type(r["fixture_only"]) is bool)
        require(type(r["nonce"]) is str and len(r["nonce"]) == 64 and all(c in "0123456789abcdef" for c in r["nonce"]))
        require(type(r["core_sha256"]) is str and len(r["core_sha256"]) == 64 and all(c in "0123456789abcdef" for c in r["core_sha256"]))
        require(r["prefix"] == "37465795/ib-qc-first64-cik-candidates-20261025-once/" + r["nonce"])
        require(raw(r["ciks"]) == raw(__CIKS__) and r["ciks_sha256"] == sha(raw(r["ciks"])))
        require(raw(r["source_provenance"]) == raw(__PROVENANCE__))
        require(type(_consume) is bool)
        require(raw(r["scope"]) == raw({"lookup_date":"2021-03-31","maximum_resolver_calls":51,"maximum_candidates_per_cik":16,"maximum_candidates_total":512,"fresh_cloud_keys":105,"maximum_receipt_bytes":524288,"maximum_total_read_bytes":2097152,"history_subscriptions_jobs_backtests":0,"atomic_create_or_immutability_guaranteed":False}))
        keys = [r["prefix"] + "/start.json"]
        for index in range(1,52): keys.extend([r["prefix"] + "/%03d-started.json" % index, r["prefix"] + "/%03d-result.json" % index])
        keys.append(r["prefix"] + "/final.json")
        error_key = r["prefix"] + "/error.json"
        ack = {"schema":"insider-qc-cik-candidates-v1/acknowledgement","audit_id":r["audit_id"],"project_id":37465795,
            "notebook":r["notebook"],"cell_index":0,"prefix":r["prefix"],"registration_sha256":_registration_sha256,
            "core_sha256":r["core_sha256"],"fixture_only":r["fixture_only"],"mode":"consume" if _consume else "capture",
            "disposition":"refused_no_retry","resolver_calls_attempted":0,"resolver_calls_completed":0,
            "own_key_prechecks":0,"own_receipt_saves":0,"own_receipt_reads":0,"cloud_receipt_chain_complete":False,
            "stop_stage":None,"error_receipt_acknowledged":False,
            "platform_values_counts_or_digests_exported":False,"atomic_create_or_immutability_guaranteed":False,"backtesting_ready":False}
        marker = "_ib_cik_" + ("consume_" if _consume else "capture_") + r["nonce"]
        stage[0] = "kernel_claim";require(marker not in globals()); globals()[marker] = True
        start = {"schema":"insider-qc-cik-candidates-v1/start","registration_sha256":_registration_sha256,"core_sha256":r["core_sha256"],
            "ciks_sha256":r["ciks_sha256"],"source_provenance":r["source_provenance"],"lookup_date":"2021-03-31","authority":authority}
        start_sha = sha(raw(start))
        def begun(index, cik):
            return {"schema":"insider-qc-cik-candidates-v1/lookup-started","ordinal":index,"raw_cik":cik,
                "parameter_cik":int(cik),"lookup_date":"2021-03-31","start_sha256":start_sha,"maximum_attempts":1}
        def result(index, cik, candidates):
            require(type(candidates) is list and len(candidates) <= 16)
            for candidate in candidates:
                require(type(candidate) is dict and set(candidate) == {"sid","symbol_value","security_type"})
                require(candidate["security_type"] == "Equity")
                for name, limit in (("sid",512),("symbol_value",128)):
                    value = candidate[name]
                    require(type(value) is str and 0 < len(value) <= limit and all(32 <= ord(c) <= 126 for c in value))
            ids = [item["sid"] for item in candidates]
            return {"schema":"insider-qc-cik-candidates-v1/lookup-result","ordinal":index,"raw_cik":cik,
                "lookup_started_sha256":sha(raw(begun(index,cik))),"candidates":candidates,
                "duplicate_sids":sorted({sid for sid in ids if ids.count(sid) > 1}),
                "resolver_returned_zero":len(candidates)==0,"authority":authority}
        def final(rows):
            require(len(rows)==51 and sum(len(row["candidates"]) for row in rows)<=512)
            edges = {}
            for index, row in enumerate(rows,1):
                for sid in {item["sid"] for item in row["candidates"]}: edges.setdefault(sid,[]).append(index)
            return {"schema":"insider-qc-cik-candidates-v1/final","start_sha256":start_sha,"registration_sha256":_registration_sha256,
                "result_sha256":[sha(raw(row)) for row in rows],"shared_sid_groups":[{"sid":sid,"cik_ordinals":indices} for sid,indices in sorted(edges.items()) if len(indices)>1],
                "candidate_rows":sum(len(row["candidates"]) for row in rows),"zero_result_rows":sum(row["resolver_returned_zero"] for row in rows),
                "all_51_resolver_calls_completed":True,"authority":authority}
        with contextlib.redirect_stdout(_Discard()), contextlib.redirect_stderr(_Discard()):
            stage[0] = "construct"
            qb, symbol_type, equity_type = _factory()
            stage[0] = "project"
            require(type(qb.project_id) is int and qb.project_id == 37465795)
            store = qb.object_store
            read_bytes = [0]
            def read(key, phase="consume"):
                stage[0] = phase+"_readback"
                ack["own_receipt_reads"] += 1
                text = store.read(key);require(type(text) is str)
                read_bytes[0] += len(text.encode());require(read_bytes[0]<=2097152)
                return decode(text)
            def save_read(key, value, phase):
                stage[0] = phase+"_save"
                text = raw(value); require(len(text.encode())<=524288)
                ack["own_receipt_saves"] += 1
                require(store.save(key,text) is True)
                require(raw(read(key,phase)) == text)
            rows = []
            if _consume:
                require(raw(read(keys[0])) == raw(start))
                for index,cik in enumerate(r["ciks"],1):
                    require(raw(read(keys[2*index-1])) == raw(begun(index,cik)))
                    row = read(keys[2*index]); require(raw(row) == raw(result(index,cik,row.get("candidates"))))
                    rows.append(row); require(sum(len(row["candidates"]) for row in rows)<=512)
                require(raw(read(keys[-1])) == raw(final(rows)))
                # Retained mapping values remain in this cloud kernel only.
                globals()["_ib_cik_retained_"+r["nonce"]] = rows
            else:
                for key in keys+[error_key]:
                    stage[0] = "key_precheck"
                    ack["own_key_prechecks"] += 1
                    require(store.contains_key(key) is False)
                fresh_all = True
                save_read(keys[0],start,"start")
                total = 0
                for index,cik in enumerate(r["ciks"],1):
                    save_read(keys[2*index-1],begun(index,cik),"row_start")
                    stage[0] = "cik_call"
                    ack["resolver_calls_attempted"] += 1
                    resolved = qb.cik(int(cik),trading_date=datetime(2021,3,31))
                    candidates = []
                    for symbol in resolved:
                        stage[0] = "native_symbol_shape"
                        require(isinstance(symbol,symbol_type) and symbol.security_type == equity_type)
                        require(len(candidates)<16 and total<512)
                        candidates.append({"sid":str(symbol.id),"symbol_value":symbol.value,"security_type":"Equity"});total += 1
                    row = result(index,cik,candidates)
                    ack["resolver_calls_completed"] += 1
                    save_read(keys[2*index],row,"row_result");rows.append(row)
                save_read(keys[-1],final(rows),"final")
            ack["cloud_receipt_chain_complete"] = True
            ack["disposition"] = "retained_receipts_consistent_no_lookup" if _consume else "candidate_receipts_completed"
    except BaseException:
        # One distinct, fresh own error key may record control-only failure.
        # Never repeat a lookup/write or reconstruct a missing data receipt.
        if ack["disposition"] != "registration_refused":
            ack["stop_stage"] = stage[0]
            if not _consume and fresh_all and store is not None:
                error = {"schema":"insider-qc-cik-candidates-v1/error","registration_sha256":_registration_sha256,
                    "stop_stage":stage[0],"resolver_calls_attempted":ack["resolver_calls_attempted"],
                    "resolver_calls_completed":ack["resolver_calls_completed"],
                    "unattempted_ciks":r["ciks"][ack["resolver_calls_attempted"]:],"no_retry_or_resume":True,"authority":authority}
                try:
                    with contextlib.redirect_stdout(_Discard()),contextlib.redirect_stderr(_Discard()):
                        text = raw(error);ack["own_receipt_saves"] += 1
                        require(store.save(error_key,text) is True)
                        ack["own_receipt_reads"] += 1
                        retained = store.read(error_key);require(type(retained) is str)
                        read_bytes[0] += len(retained.encode());require(read_bytes[0]<=2097152)
                        require(raw(decode(retained)) == text)
                        ack["error_receipt_acknowledged"] = True
                except BaseException: pass
    print(raw(ack))
'''.replace("__CIKS__", repr(list(CIKS))).replace("__PROVENANCE__", repr(SOURCE_PROVENANCE))
CORE_SHA256 = _sha(CORE_SOURCE.encode())


def _registration(nonce, fixture):
    _need(type(nonce) is str and control._SHA.fullmatch(nonce) and type(fixture) is bool, "candidate_nonce_or_mode_refused")
    return {"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,"project_id":PROJECT_ID,"notebook":NOTEBOOK,"cell_index":0,
        "nonce":nonce,"prefix":f"{PROJECT_ID}/{AUDIT_ID}/{nonce}","fixture_only":fixture,"core_sha256":CORE_SHA256,
        "ciks":list(CIKS),"ciks_sha256":CIKS_SHA256,"source_provenance":_decode(_raw(SOURCE_PROVENANCE)),
        "scope":{"lookup_date":"2021-03-31","maximum_resolver_calls":51,"maximum_candidates_per_cik":16,
            "maximum_candidates_total":512,"fresh_cloud_keys":105,"maximum_receipt_bytes":524288,
            "maximum_total_read_bytes":2097152,"history_subscriptions_jobs_backtests":0,
            "atomic_create_or_immutability_guaranteed":False}}


def _cell(nonce, fixture, *, consume=False):
    _need(type(consume) is bool,"candidate_mode_refused")
    registration_raw = _raw(_registration(nonce,fixture))
    wrapper = ("\ndef _ib_cik_factory():\n    from QuantConnect.Research import QuantBook\n    from QuantConnect import Symbol, SecurityType\n    return QuantBook(), Symbol, SecurityType.EQUITY\n"
        + "_ib_cik_run(_ib_cik_factory,"+repr(registration_raw.decode())+","+repr(_sha(registration_raw))+","+repr(consume)+")\n")
    cell_raw = (CORE_SOURCE+wrapper).encode();_need(0<len(cell_raw)<=MAX_CELL_BYTES,"candidate_cell_bound_refused")
    compile(cell_raw,"<fixed-qc-cik-candidates>","exec")
    return registration_raw,cell_raw


def build_invented_cell(nonce, *, consume=False):
    """Inert fixture-only full-cell image; consumer NEVER calls qb.cik."""
    return _cell(nonce,True,consume=consume)


def _source_identity(value,root):
    _need(type(value) is dict and set(value)=={"root","branch","head","clean","source_sha256","source_inventory_sha256"}
        and value["root"]==str(root) and value["branch"]==LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and control._HEAD.fullmatch(value["head"])
        and type(value["source_sha256"]) is dict and 2<=len(value["source_sha256"])<=2048
        and {SELF_PATH,TEST_PATH}<=set(value["source_sha256"])
        and all(type(name) is str and len(name)<=512 and control._SOURCE.fullmatch(name) and Path(name).as_posix()==name
            and ".." not in Path(name).parts and type(digest) is str and control._SHA.fullmatch(digest)
            for name,digest in value["source_sha256"].items())
        and value["source_inventory_sha256"]==_sha(_raw(value["source_sha256"])),"candidate_source_identity_refused")
    return value


def _current(identity):
    _source_identity(identity,LANE_ROOT)
    _need(set(sources.custody._internal_source_paths(LANE_ROOT))<=set(identity["source_sha256"]),"candidate_loaded_closure_missing")
    _need(sources.custody._source_bytes(LANE_ROOT,tuple(identity["source_sha256"]))==identity["source_sha256"]
        and sources.custody._source_bytes(LANE_ROOT,tuple(sources.FROZEN))==sources.FROZEN,"candidate_current_or_frozen_source_changed")


def _identity(head):
    _need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"fixed_candidate_source_required")
    identity=sources.custody._identity(head);own=sources.custody._source_bytes(LANE_ROOT,(SELF_PATH,TEST_PATH))
    for name,digest in own.items():_need(_sha(sources.custody._git(LANE_ROOT,"show",head+":"+name))==digest,"candidate_uncommitted_source")
    inventory={**identity["source_sha256"],**own};identity=_source_identity({**identity,"source_sha256":inventory,
        "source_inventory_sha256":_sha(_raw(inventory))},LANE_ROOT);_current(identity);return identity


def _isolated():
    _need(sys.flags.isolated==sys.flags.no_site==sys.flags.no_user_site==sys.flags.dont_write_bytecode==1
        and sys.pycache_prefix==EMPTY_CACHE_PREFIX,"candidate_initial_isolation_required")


def _proof(identity,fixture):
    return {"schema":SCHEMA+"/source-preflight","fixture_only":fixture,"source_inventory_sha256":identity["source_inventory_sha256"],
        "source_count":len(identity["source_sha256"]),"native_network_fork_allwrite_securityexec_denial":not fixture,
        "current_frozen_and_loaded_sources_verified":not fixture,"qc_or_credential_accesses":0}


def _intent(identity,registration_raw,cell_raw,proof,fixture):
    r=_decode(registration_raw)
    return {"schema":SCHEMA+"/permanent-local-intent","audit_id":AUDIT_ID,"fixture_only":fixture,"execution_identity":identity,
        "registration_sha256":_sha(registration_raw),"core_sha256":CORE_SHA256,"cell_sha256":_sha(cell_raw),"cell_bytes":len(cell_raw),
        "project_id":PROJECT_ID,"notebook":NOTEBOOK,"cell_index":0,"prefix":r["prefix"],"source_preflight":proof,
        "local_scope_permanently_consumed":True,"maximum_selected_cell_executions":1,"no_retry_even_after_kernel_reset":True,
        "cloud_execution_observed":False,"qc_or_credential_accesses_by_preparer":0,"backtesting_ready":False}


def _capacity(identity,fixture):
    _source_identity(identity,Path(identity["root"]));r,cell=_cell("0"*64,fixture)
    for value in (identity,_decode(r),_intent(identity,r,cell,_proof(identity,fixture),fixture)):
        raw=_raw(value);_need(0<len(raw)<=MAX_CONTROL_BYTES and _raw(_decode(raw))==raw,"candidate_control_capacity_refused")


def _worker(identity):
    _isolated();sources._prove_isolation();_current(identity);_capacity(identity,False);_current(identity);return _proof(identity,False)


def _source_preflight(identity):
    code=("import sys;sys.path.insert(0,"+repr(str(LANE_ROOT))+");import json;from research import insider_buying_qc_cik_candidate_cell as m;identity=json.loads("+repr(_raw(identity).decode())+");"
        "\ntry: result=m._worker(identity)\nexcept BaseException: print('{\"disposition\":\"candidate_source_preflight_refused\"}');sys.exit(2)\nprint(m._raw(result).decode())")
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    command=("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","LANG=C","LC_ALL=C","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)
    child=sources.launcher.run_child(command,cwd=LANE_ROOT,env=None,timeout=60,cap=8192)
    _need(child.returncode==0 and child.stderr==b"" and child.stdout==_raw(_proof(identity,False))+b"\n","candidate_source_preflight_refused")
    return _proof(identity,False)


def _prepare(root,identity,*,fixture,guard,preflight,nonce_factory):
    _need(type(fixture) is bool and callable(guard) and callable(preflight) and callable(nonce_factory),"candidate_preparation_mode_refused")
    if fixture:
        publication._fixture_root(root);publication._native_fixture_denial()
        _need(preflight is not _source_preflight and nonce_factory is not secrets.token_hex,"invented_candidate_callbacks_required")
    else:_need(root==LANE_ROOT and preflight is _source_preflight and nonce_factory is secrets.token_hex,"fixed_candidate_preparer_required")
    _source_identity(identity,root);_capacity(identity,fixture);guard();proof=preflight(identity)
    _need(_raw(proof)==_raw(_proof(identity,fixture)),"candidate_native_preflight_refused");guard()
    chain=folder=None
    try:
        chain=sources.custody._Chain(root,ARTIFACT_PARTS,create=True,exclusive_last=True);folder=publication._NewDirectory(root.joinpath(*ARTIFACT_PARTS));expected=set()
        def check():
            guard();chain.recheck();folder.check();_need(set(os.listdir(folder.fd))==expected,"candidate_output_inventory_changed")
        def publish(name,raw,cap=MAX_CONTROL_BYTES):
            check();digest=folder.publish(name,raw,cap=cap);expected.add(name);check();return digest
        publish("scope.lock",LOCK_BYTES);registration_raw,cell_raw=_cell(nonce_factory(32),fixture)
        registration_sha=publish("registration.json",registration_raw);cell_sha=publish("cell.py",cell_raw,MAX_CELL_BYTES)
        intent_sha=publish("intent.json",_raw(_intent(identity,registration_raw,cell_raw,proof,fixture)))
        ready={"schema":SCHEMA+"/prepared-not-executed","audit_id":AUDIT_ID,"fixture_only":fixture,
            "registration_sha256":registration_sha,"cell_sha256":cell_sha,"cell_bytes":len(cell_raw),"intent_sha256":intent_sha,
            "core_sha256":CORE_SHA256,"prefix":_decode(registration_raw)["prefix"],"project_id":PROJECT_ID,"notebook":NOTEBOOK,"cell_index":0,
            "local_scope_permanently_consumed":True,"cloud_execution_observed":False,"qc_or_credential_accesses":0,"backtesting_ready":False}
        ready_sha=publish("ready.json",_raw(ready));check()
        return {**ready,"ready_sha256":ready_sha,"cell_source":cell_raw.decode(),"cell_path":str(folder.path/"cell.py"),"intent_path":str(folder.path/"intent.json")}
    finally:publication._close_all((folder,chain),None,None,False)


def prepare_actual_cell(expected_head):
    _isolated();before=_identity(expected_head)
    def guard():_need(_identity(expected_head)==before,"candidate_committed_source_changed")
    return _prepare(LANE_ROOT,before,fixture=False,guard=guard,preflight=_source_preflight,nonce_factory=secrets.token_hex)


def prepare_invented_cell(root,*,nonce="a"*64,guard=lambda:None,preflight=None):
    inventory={SELF_PATH:"a"*64,TEST_PATH:"b"*64,**{f"data/invented_{i:03}.py":"c"*64 for i in range(106)}}
    identity={"root":str(root),"branch":LANE_BRANCH,"head":"a"*40,"clean":True,"source_sha256":inventory,"source_inventory_sha256":_sha(_raw(inventory))}
    return _prepare(root,identity,fixture=True,guard=guard,preflight=(lambda i:_proof(i,True)) if preflight is None else preflight,
        nonce_factory=lambda count:nonce if count==32 else _need(False,"candidate_nonce_length"))


def validate_acknowledgement(raw,*,registration_raw,consume=False):
    _need(type(raw) is bytes and 0<len(raw)<=8192 and type(consume) is bool,"candidate_ack_bound")
    r=_decode(registration_raw);_need(_raw(r)==_raw(_registration(r.get("nonce"),r.get("fixture_only"))),"candidate_registration_refused")
    value=_decode(raw.removesuffix(b"\n"));fixed={"schema":SCHEMA+"/acknowledgement","audit_id":AUDIT_ID,"project_id":PROJECT_ID,
        "notebook":NOTEBOOK,"cell_index":0,"prefix":r["prefix"],"registration_sha256":_sha(registration_raw),"core_sha256":CORE_SHA256,
        "fixture_only":r["fixture_only"],"mode":"consume" if consume else "capture","platform_values_counts_or_digests_exported":False,
        "atomic_create_or_immutability_guaranteed":False,"backtesting_ready":False}
    dynamic={"disposition","resolver_calls_attempted","resolver_calls_completed","own_key_prechecks","own_receipt_saves","own_receipt_reads","cloud_receipt_chain_complete","stop_stage","error_receipt_acknowledged"}
    _need(type(value) is dict and set(value)==set(fixed)|dynamic and _raw({k:value[k] for k in fixed})==_raw(fixed),"candidate_ack_schema_refused")
    counts={k:value[k] for k in dynamic if k not in {"disposition","cloud_receipt_chain_complete","stop_stage","error_receipt_acknowledged"}}
    _need(all(type(n) is int and n>=0 for n in counts.values()) and type(value["cloud_receipt_chain_complete"]) is bool
        and type(value["error_receipt_acknowledged"]) is bool,"candidate_ack_count_types")
    attempted,completed,prechecks,saves,reads=(value[k] for k in ("resolver_calls_attempted","resolver_calls_completed","own_key_prechecks","own_receipt_saves","own_receipt_reads"))
    _need(0<=completed<=attempted<=51 and 0<=prechecks<=105 and 0<=reads<=saves<=105 if not consume else attempted==completed==prechecks==saves==0 and 0<=reads<=104,"candidate_ack_count_bounds")
    if value["error_receipt_acknowledged"]:
        _need(not consume and prechecks==105 and saves>=1 and reads>=1
            and value["stop_stage"] not in {"kernel_claim","construct","project","key_precheck"},"candidate_ack_unperformed_error_receipt")
    if value["cloud_receipt_chain_complete"]:
        _need(value["disposition"]==("retained_receipts_consistent_no_lookup" if consume else "candidate_receipts_completed")
            and (reads==104 if consume else attempted==completed==51 and prechecks==105 and saves==reads==104)
            and value["stop_stage"] is None and value["error_receipt_acknowledged"] is False,"candidate_ack_false_completion")
    else:_need(value["disposition"]=="refused_no_retry" and value["stop_stage"] in {"kernel_claim","construct","project","key_precheck","start_save","start_readback","row_start_save","row_start_readback","cik_call","native_symbol_shape","row_result_save","row_result_readback","final_save","final_readback","consume_readback"},"candidate_ack_refusal_state")
    return value


class _ArgumentParser(argparse.ArgumentParser):
    def error(self,message):self.exit(2,"candidate_argument_refused\n")


def main(argv=None):
    parser=_ArgumentParser(description=__doc__);parser.add_argument("--expected-head",required=True);args=parser.parse_args(argv)
    try:result=prepare_actual_cell(args.expected_head)
    except BaseException:print('{"disposition":"candidate_local_preparation_refused"}');return 2
    print(_raw({k:v for k,v in result.items() if k!="cell_source"}).decode());return 0


if __name__=="__main__":raise SystemExit(main())
