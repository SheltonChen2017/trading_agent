"""Prepare one fresh cell that consumes the completed CIK receipts in cloud.

The executed capture source and notebook are unchanged. This preparer reads
only own source/intent controls, never actual identity artifacts, credentials
or QC. The separately activated cell reads the exact old104 receipts without
repeating a resolver lookup or writing cloud data. Derived mappings stay in
the cloud kernel; only own execution acknowledgement metadata may leave it.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import sys

from research import insider_buying_qc_cik_candidate_cell as producer


SELF_PATH = "research/insider_buying_qc_cik_candidate_consumer.py"
TEST_PATH = "tests/test_insider_buying_qc_cik_candidate_consumer.py"
SCHEMA = "insider-qc-cik-candidate-consumer-v1"
AUDIT_ID = "ib-qc-first64-cik-receipt-consumer-20261025-once"
NOTEBOOK = "ib_qc_cik_consumer_20261025.ipynb"
PROJECT_ID = producer.PROJECT_ID
ARTIFACT_PARTS = ("artifacts", "insider_buying", "qc_cik_candidate_consumer_v1")
EMPTY_CACHE_PREFIX = "/var/empty/insider-qc-cik-candidate-consumer-no-bytecode"
LOCK_BYTES = b"INSETF-QC-CIK-receipt-consumer-permanent-local-intent-v1\n"
MAX_CONTROL_BYTES, MAX_CELL_BYTES = 256 * 1024, 64 * 1024
LANE_ROOT, LANE_BRANCH = producer.LANE_ROOT, producer.LANE_BRANCH
publication, sources = producer.publication, producer.sources
_raw, _sha, _decode = producer._raw, producer._sha, producer._decode
PRODUCER_NONCE = "4c9ef422128b91d6a043e543ada86fe10ec9d1f910d6697acb3cb0c6dab8dd13"
PRODUCER_HEAD = "c4311eab0b7a0540ac03e83b4eba22c96a1ac436"
PRODUCER_SOURCE_SHA256 = "4a192fef3feff0adbfe036c70fcb7b494bb29de2ad87d25bdc69c2010b00ca42"
PRODUCER_TEST_SHA256 = "6856a4e4bdec12cee31c692035792615d3f23f4c9a0e1725083c44eff4b614f1"
PRODUCER_CORE_SHA256 = "32027295c6b367ce19e558ea9548e77a0830e5ac5c7b3f5111682f70a11d0171"
OBSERVED_PRODUCER = {
    "basis":"trusted-main-observed-own-controls-record259; not reopened by this preparer",
    "execution_head":PRODUCER_HEAD,"source_path":producer.SELF_PATH,
    "source_sha256":PRODUCER_SOURCE_SHA256,"test_path":producer.TEST_PATH,
    "test_sha256":PRODUCER_TEST_SHA256,"core_sha256":PRODUCER_CORE_SHA256,
    "nonce":PRODUCER_NONCE,"registration_sha256":"00751670b4d83e9070b5a5c957d36834a72f5e2019b9405c9a7aaaaa470a317e",
    "cell_sha256":"e0c0ecab1892415c0e63e48bb4804407d2ee2f5b80ef0b31eaf77bb3be5f7129",
    "intent_sha256":"d5f5b5d92099e97eacc0e51ffc7cc1522b6411c1a0f00b47b37a7ce6d73e3334",
    "ready_sha256":"5e121b7fab9f1940b63272ab540cfe94729df0d65bbb761017305b5be285941d",
    "acknowledgement_sha256":"71492296649b4099dcb168be5caf30996c8813b0f1cc2c4faca3e875da933288",
    "capture_selected_cell_executions_observed":1,"resolver_calls_attempted":51,
    "resolver_rows_shape_validated":51,"own_receipt_saves":104,"own_receipt_reads":104,
    "cloud_receipt_chain_completed_observed":True,"backend_HTTP_request_count_measured":False}


class CandidateConsumerError(ValueError):
    """Finite own-control refusal codes only."""


def _need(value, code):
    if not value: raise CandidateConsumerError(code)


def _producer_provenance(fixture):
    registration_raw, capture_cell = producer._cell(PRODUCER_NONCE, fixture)
    if not fixture:
        _need(producer.CORE_SHA256 == PRODUCER_CORE_SHA256
            and _sha(registration_raw) == OBSERVED_PRODUCER["registration_sha256"]
            and _sha(capture_cell) == OBSERVED_PRODUCER["cell_sha256"], "consumer_original_capture_image_changed")
        return _decode(_raw(OBSERVED_PRODUCER))
    return {**_decode(_raw(OBSERVED_PRODUCER)), "basis":"invented own controls; no observed cloud operation",
        "execution_head":"a"*40,"registration_sha256":_sha(registration_raw),"cell_sha256":_sha(capture_cell),
        "intent_sha256":"a"*64,"ready_sha256":"b"*64,"acknowledgement_sha256":"c"*64,
        "capture_selected_cell_executions_observed":0,"cloud_receipt_chain_completed_observed":False}


CONSUMER_CORE_SOURCE = '''def _ib_cik_consumer_run(_factory, _text, _expected_sha, _expected_core_sha):
    import contextlib
    import hashlib
    import json
    class _Stop(Exception): pass
    class _Buffer:
        def __init__(self): self.text = ""
        def write(self, text):
            if type(text) is not str or len((self.text+text).encode()) > 8192: raise _Stop()
            self.text += text
            return len(text)
        def flush(self): return None
    class _Discard:
        def write(self, text): return len(text)
        def flush(self): return None
    def raw(value): return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)
    def sha(text): return hashlib.sha256(text.encode()).hexdigest()
    def require(value):
        if not value: raise _Stop()
    def decode(text):
        require(type(text) is str and 0 < len(text.encode()) <= 262144)
        def pairs(items):
            result = {}
            for key,value in items:
                require(key not in result);result[key] = value
            return result
        value = json.loads(text,object_pairs_hook=pairs,parse_constant=lambda _:require(False))
        require(type(value) is dict and raw(value) == text)
        return value
    ack = {"schema":"insider-qc-cik-candidate-consumer-v1/acknowledgement","disposition":"registration_refused"}
    stage = "registration"
    try:
        r = decode(_text)
        require(sha(_text) == _expected_sha)
        require(set(r) == {"schema","audit_id","project_id","execution_notebook","execution_cell_index","nonce","fixture_only","consumer_core_sha256","producer_registration","producer_provenance","preparation_source","scope"})
        require(r["schema"] == "insider-qc-cik-candidate-consumer-v1/registration" and r["audit_id"] == "ib-qc-first64-cik-receipt-consumer-20261025-once")
        require(type(r["project_id"]) is int and r["project_id"] == 37465795 and r["execution_notebook"] == "ib_qc_cik_consumer_20261025.ipynb")
        require(type(r["execution_cell_index"]) is int and r["execution_cell_index"] == 0 and r["fixture_only"] is __FIXTURE_MODE__)
        require(type(r["nonce"]) is str and len(r["nonce"]) == 64 and all(c in "0123456789abcdef" for c in r["nonce"]))
        require(type(r["consumer_core_sha256"]) is str and r["consumer_core_sha256"] == _expected_core_sha)
        require(raw(r["producer_registration"]) == raw(__PRODUCER_REGISTRATION__))
        require(raw(r["producer_provenance"]) == raw(__PRODUCER_PROVENANCE__))
        p = r["preparation_source"]
        require(type(p) is dict and set(p) == {"head","source_path","source_sha256","source_inventory_sha256"})
        require(p["source_path"] == "research/insider_buying_qc_cik_candidate_consumer.py")
        for name,length in (("head",40),("source_sha256",64),("source_inventory_sha256",64)):
            require(type(p[name]) is str and len(p[name]) == length and all(c in "0123456789abcdef" for c in p[name]))
        require(raw(r["scope"]) == raw({"mode":"consume-existing-receipts-only","maximum_selected_cell_executions":1,"maximum_own_receipt_reads":104,"resolver_calls":0,"own_key_prechecks":0,"cloud_saves_deletes":0,"history_subscriptions_jobs_backtests":0,"new_cloud_keys":0,"reset_resume_or_reconstruct_missing_receipt":False,"platform_values_counts_or_digests_exported":False}))
        old = r["producer_registration"]
        ack = {"schema":"insider-qc-cik-candidate-consumer-v1/acknowledgement","audit_id":r["audit_id"],"project_id":37465795,
            "execution_notebook":r["execution_notebook"],"execution_cell_index":0,"registration_sha256":_expected_sha,
            "consumer_core_sha256":r["consumer_core_sha256"],"fixture_only":r["fixture_only"],
            "producer_notebook":old["notebook"],"producer_registration_sha256":sha(raw(old)),
            "producer_cell_sha256":r["producer_provenance"]["cell_sha256"],
            "producer_acknowledgement_sha256":r["producer_provenance"]["acknowledgement_sha256"],
            "disposition":"refused_no_retry","resolver_calls_attempted":0,"own_receipt_reads":0,"cloud_saves_deletes":0,
            "cloud_receipt_chain_consistent":False,"stop_stage":None,"inherited_stop_stage":None,
            "platform_values_counts_or_digests_exported":False,"backtesting_ready":False}
        stage = "kernel_claim"
        marker = "_ib_cik_new_consumer_"+r["nonce"]
        require(marker not in globals());globals()[marker] = True
        stage = "inherited_core"
        buffer = _Buffer()
        with contextlib.redirect_stdout(buffer),contextlib.redirect_stderr(_Discard()):
            _ib_cik_run(_factory,raw(old),sha(raw(old)),True)
        stage = "inherited_ack"
        require(buffer.text.endswith("\\n") and buffer.text.count("\\n") == 1)
        inherited = decode(buffer.text[:-1])
        fixed = {"schema":"insider-qc-cik-candidates-v1/acknowledgement","audit_id":old["audit_id"],"project_id":37465795,
            "notebook":old["notebook"],"cell_index":0,"prefix":old["prefix"],"registration_sha256":sha(raw(old)),
            "core_sha256":old["core_sha256"],"fixture_only":old["fixture_only"],"mode":"consume",
            "platform_values_counts_or_digests_exported":False,"atomic_create_or_immutability_guaranteed":False,"backtesting_ready":False,
            "resolver_calls_attempted":0,"resolver_calls_completed":0,"own_key_prechecks":0,"own_receipt_saves":0,"error_receipt_acknowledged":False}
        require(set(inherited) == set(fixed)|{"disposition","own_receipt_reads","cloud_receipt_chain_complete","stop_stage"})
        require(raw({key:inherited[key] for key in fixed}) == raw(fixed))
        require(type(inherited["own_receipt_reads"]) is int and 0 <= inherited["own_receipt_reads"] <= 104)
        require(type(inherited["cloud_receipt_chain_complete"]) is bool)
        ack["own_receipt_reads"] = inherited["own_receipt_reads"]
        if inherited["cloud_receipt_chain_complete"]:
            require(inherited["own_receipt_reads"] == 104 and inherited["disposition"] == "retained_receipts_consistent_no_lookup" and inherited["stop_stage"] is None)
            ack["cloud_receipt_chain_consistent"] = True
            ack["disposition"] = "existing_cloud_receipts_consistent_no_lookup"
        else:
            require(inherited["disposition"] == "refused_no_retry" and inherited["stop_stage"] in {"kernel_claim","construct","project","consume_readback"})
            ack["stop_stage"] = "inherited_refusal";ack["inherited_stop_stage"] = inherited["stop_stage"]
    except BaseException:
        if ack["disposition"] != "registration_refused": ack["stop_stage"] = stage
    print(raw(ack))
'''


def _consumer_core(fixture):
    return CONSUMER_CORE_SOURCE.replace("__PRODUCER_REGISTRATION__", repr(producer._registration(PRODUCER_NONCE,fixture))).replace(
        "__PRODUCER_PROVENANCE__", repr(_producer_provenance(fixture))).replace("__FIXTURE_MODE__",repr(fixture))


def _scope():
    return {"mode":"consume-existing-receipts-only","maximum_selected_cell_executions":1,"maximum_own_receipt_reads":104,
        "resolver_calls":0,"own_key_prechecks":0,"cloud_saves_deletes":0,"history_subscriptions_jobs_backtests":0,"new_cloud_keys":0,
        "reset_resume_or_reconstruct_missing_receipt":False,"platform_values_counts_or_digests_exported":False}


def _registration(nonce, fixture, identity):
    _need(type(nonce) is str and producer.control._SHA.fullmatch(nonce) and type(fixture) is bool,"consumer_nonce_or_mode_refused")
    _source_identity(identity,Path(identity["root"]))
    return {"schema":SCHEMA+"/registration","audit_id":AUDIT_ID,"project_id":PROJECT_ID,
        "execution_notebook":NOTEBOOK,"execution_cell_index":0,"nonce":nonce,"fixture_only":fixture,
        "consumer_core_sha256":_sha(_consumer_core(fixture).encode()),"producer_registration":producer._registration(PRODUCER_NONCE,fixture),
        "producer_provenance":_producer_provenance(fixture),"preparation_source":{"head":identity["head"],"source_path":SELF_PATH,
            "source_sha256":identity["source_sha256"][SELF_PATH],"source_inventory_sha256":identity["source_inventory_sha256"]},"scope":_scope()}


def _cell(nonce, fixture, identity):
    registration_raw=_raw(_registration(nonce,fixture,identity))
    wrapper=("\ndef _ib_cik_readonly_factory():\n    from QuantConnect.Research import QuantBook\n    return QuantBook(),None,None\n"
        +"_ib_cik_consumer_run(_ib_cik_readonly_factory,"+repr(registration_raw.decode())+","+repr(_sha(registration_raw))+","+repr(_sha(_consumer_core(fixture).encode()))+")\n")
    cell_raw=(producer.CORE_SOURCE+_consumer_core(fixture)+wrapper).encode()
    _need(0<len(cell_raw)<=MAX_CELL_BYTES,"consumer_cell_bound_refused");compile(cell_raw,"<fixed-qc-cik-receipt-consumer>","exec")
    return registration_raw,cell_raw


def _invented_identity(root):
    inventory={SELF_PATH:"a"*64,TEST_PATH:"b"*64,**{f"data/invented_{i:03}.py":"c"*64 for i in range(106)}}
    return {"root":str(root),"branch":LANE_BRANCH,"head":"a"*40,"clean":True,"source_sha256":inventory,"source_inventory_sha256":_sha(_raw(inventory))}


def build_invented_cell(nonce, *, root=Path("/invented-qc-consumer")):
    """Inert fixture image only; no SDK imports or cloud operation here."""
    return _cell(nonce,True,_invented_identity(root))


def _source_identity(value, root):
    _need(type(value) is dict and set(value)=={"root","branch","head","clean","source_sha256","source_inventory_sha256"}
        and value["root"]==str(root) and value["branch"]==LANE_BRANCH and value["clean"] is True
        and type(value["head"]) is str and producer.control._HEAD.fullmatch(value["head"])
        and type(value["source_sha256"]) is dict and 2<=len(value["source_sha256"])<=2048
        and {SELF_PATH,TEST_PATH}<=set(value["source_sha256"])
        and all(type(name) is str and len(name)<=512 and producer.control._SOURCE.fullmatch(name) and Path(name).as_posix()==name
            and ".." not in Path(name).parts and type(digest) is str and producer.control._SHA.fullmatch(digest)
            for name,digest in value["source_sha256"].items())
        and value["source_inventory_sha256"]==_sha(_raw(value["source_sha256"])),"consumer_source_identity_refused")
    return value


def _current(identity):
    _source_identity(identity,LANE_ROOT)
    _need(set(sources.custody._internal_source_paths(LANE_ROOT))<=set(identity["source_sha256"]),"consumer_loaded_closure_missing")
    _need(sources.custody._source_bytes(LANE_ROOT,tuple(identity["source_sha256"]))==identity["source_sha256"]
        and sources.custody._source_bytes(LANE_ROOT,tuple(sources.FROZEN))==sources.FROZEN,"consumer_current_or_frozen_source_changed")
    _need(identity["source_sha256"].get(producer.SELF_PATH)==PRODUCER_SOURCE_SHA256
        and identity["source_sha256"].get(producer.TEST_PATH)==PRODUCER_TEST_SHA256
        and producer.CORE_SHA256==PRODUCER_CORE_SHA256,"consumer_original_source_image_changed")


def _identity(head):
    _need(Path(__file__).resolve()==LANE_ROOT/SELF_PATH,"fixed_consumer_source_required")
    identity=sources.custody._identity(head)
    own=sources.custody._source_bytes(LANE_ROOT,(SELF_PATH,TEST_PATH,producer.SELF_PATH,producer.TEST_PATH))
    for name,digest in own.items():_need(_sha(sources.custody._git(LANE_ROOT,"show",head+":"+name))==digest,"consumer_uncommitted_source")
    for name,digest in ((producer.SELF_PATH,PRODUCER_SOURCE_SHA256),(producer.TEST_PATH,PRODUCER_TEST_SHA256)):
        _need(_sha(sources.custody._git(LANE_ROOT,"show",PRODUCER_HEAD+":"+name))==digest,"consumer_original_Git_source_changed")
    inventory={**identity["source_sha256"],**own};value=_source_identity({**identity,"source_sha256":inventory,
        "source_inventory_sha256":_sha(_raw(inventory))},LANE_ROOT);_current(value);return value


def _isolated():
    _need(sys.flags.isolated==sys.flags.no_site==sys.flags.no_user_site==sys.flags.dont_write_bytecode==1
        and sys.pycache_prefix==EMPTY_CACHE_PREFIX,"consumer_initial_isolation_required")


def _proof(identity,fixture):
    return {"schema":SCHEMA+"/source-preflight","fixture_only":fixture,"source_inventory_sha256":identity["source_inventory_sha256"],
        "source_count":len(identity["source_sha256"]),"native_network_fork_allwrite_securityexec_denial":not fixture,
        "current_frozen_loaded_and_original_sources_verified":not fixture,"old_artifact_or_credential_or_QC_accesses":0}


def _intent(identity,registration_raw,cell_raw,proof,fixture):
    r=_decode(registration_raw)
    return {"schema":SCHEMA+"/permanent-local-intent","audit_id":AUDIT_ID,"fixture_only":fixture,"execution_identity":identity,
        "registration_sha256":_sha(registration_raw),"consumer_core_sha256":r["consumer_core_sha256"],"cell_sha256":_sha(cell_raw),"cell_bytes":len(cell_raw),
        "project_id":PROJECT_ID,"execution_notebook":NOTEBOOK,"execution_cell_index":0,"producer_provenance":r["producer_provenance"],
        "producer_registration_sha256":_sha(_raw(r["producer_registration"])),"source_preflight":proof,
        "local_scope_permanently_consumed":True,"maximum_selected_cell_executions":1,"no_retry_even_after_kernel_reset":True,
        "old_scope_reset_or_recovered":False,"cloud_execution_observed":False,"QC_or_credential_accesses_by_preparer":0,"backtesting_ready":False}


def _capacity(identity,fixture):
    r,cell=_cell("0"*64,fixture,identity)
    for value in (identity,_decode(r),_intent(identity,r,cell,_proof(identity,fixture),fixture)):
        raw=_raw(value);_need(0<len(raw)<=MAX_CONTROL_BYTES and _raw(_decode(raw))==raw,"consumer_control_capacity_refused")


def _worker(identity):
    _isolated();sources._prove_isolation();_current(identity);_capacity(identity,False);_current(identity);return _proof(identity,False)


def _source_preflight(identity):
    code=("import sys;sys.path.insert(0,"+repr(str(LANE_ROOT))+");import json;from research import insider_buying_qc_cik_candidate_consumer as m;identity=json.loads("+repr(_raw(identity).decode())+");"
        "\ntry: result=m._worker(identity)\nexcept BaseException: print('{\"disposition\":\"consumer_source_preflight_refused\"}');sys.exit(2)\nprint(m._raw(result).decode())")
    policy='(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)(deny process-exec (literal "/usr/bin/security"))'
    command=("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","LANG=C","LC_ALL=C","/usr/bin/sandbox-exec","-p",policy,
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+EMPTY_CACHE_PREFIX,"-c",code)
    child=sources.launcher.run_child(command,cwd=LANE_ROOT,env=None,timeout=60,cap=8192)
    _need(child.returncode==0 and child.stderr==b"" and child.stdout==_raw(_proof(identity,False))+b"\n","consumer_source_preflight_refused")
    return _proof(identity,False)


def _prepare(root,identity,*,fixture,guard,preflight,nonce_factory):
    _need(type(fixture) is bool and callable(guard) and callable(preflight) and callable(nonce_factory),"consumer_preparation_mode_refused")
    if fixture:
        publication._fixture_root(root);publication._native_fixture_denial()
        _need(preflight is not _source_preflight and nonce_factory is not secrets.token_hex,"invented_consumer_callbacks_required")
    else:_need(root==LANE_ROOT and preflight is _source_preflight and nonce_factory is secrets.token_hex,"fixed_consumer_preparer_required")
    _source_identity(identity,root);_capacity(identity,fixture);guard();proof=preflight(identity)
    _need(_raw(proof)==_raw(_proof(identity,fixture)),"consumer_native_preflight_refused");guard()
    chain=folder=None
    try:
        chain=sources.custody._Chain(root,ARTIFACT_PARTS,create=True,exclusive_last=True)
        folder=publication._NewDirectory(root.joinpath(*ARTIFACT_PARTS));expected=set()
        def check():
            guard();chain.recheck();folder.check();_need(set(os.listdir(folder.fd))==expected,"consumer_output_inventory_changed")
        def publish(name,raw,cap=MAX_CONTROL_BYTES):
            check();digest=folder.publish(name,raw,cap=cap);expected.add(name);check();return digest
        publish("scope.lock",LOCK_BYTES);registration_raw,cell_raw=_cell(nonce_factory(32),fixture,identity)
        registration_sha=publish("registration.json",registration_raw);cell_sha=publish("cell.py",cell_raw,MAX_CELL_BYTES)
        intent_sha=publish("intent.json",_raw(_intent(identity,registration_raw,cell_raw,proof,fixture)))
        r=_decode(registration_raw)
        ready={"schema":SCHEMA+"/prepared-not-executed","audit_id":AUDIT_ID,"fixture_only":fixture,"registration_sha256":registration_sha,
            "cell_sha256":cell_sha,"cell_bytes":len(cell_raw),"intent_sha256":intent_sha,"consumer_core_sha256":r["consumer_core_sha256"],
            "project_id":PROJECT_ID,"execution_notebook":NOTEBOOK,"execution_cell_index":0,"producer_registration_sha256":_sha(_raw(r["producer_registration"])),
            "local_scope_permanently_consumed":True,"cloud_execution_observed":False,"QC_or_credential_accesses":0,"backtesting_ready":False}
        ready_sha=publish("ready.json",_raw(ready));check()
        return {**ready,"ready_sha256":ready_sha,"cell_source":cell_raw.decode(),"cell_path":str(folder.path/"cell.py"),"intent_path":str(folder.path/"intent.json")}
    finally:publication._close_all((folder,chain),None,None,False)


def prepare_actual_cell(expected_head):
    _isolated();before=_identity(expected_head)
    def guard():_need(_identity(expected_head)==before,"consumer_committed_source_changed")
    return _prepare(LANE_ROOT,before,fixture=False,guard=guard,preflight=_source_preflight,nonce_factory=secrets.token_hex)


def prepare_invented_cell(root,*,nonce="a"*64,guard=lambda:None,preflight=None):
    root=Path(root);identity=_invented_identity(root)
    return _prepare(root,identity,fixture=True,guard=guard,preflight=(lambda i:_proof(i,True)) if preflight is None else preflight,
        nonce_factory=lambda count:nonce if count==32 else _need(False,"consumer_nonce_length"))


def validate_acknowledgement(raw,*,registration_raw):
    _need(type(raw) is bytes and 0<len(raw)<=8192,"consumer_ack_bound")
    r=_decode(registration_raw)
    # Reconstruct only the fixed registration semantics. The full preparation
    # inventory is authenticated externally by the durable intent, not invented.
    _need(set(r)=={"schema","audit_id","project_id","execution_notebook","execution_cell_index","nonce","fixture_only","consumer_core_sha256","producer_registration","producer_provenance","preparation_source","scope"}
        and r["schema"]==SCHEMA+"/registration" and r["audit_id"]==AUDIT_ID and type(r["project_id"]) is int and r["project_id"]==PROJECT_ID
        and r["execution_notebook"]==NOTEBOOK and type(r["execution_cell_index"]) is int and r["execution_cell_index"]==0
        and type(r["fixture_only"]) is bool and type(r["nonce"]) is str and producer.control._SHA.fullmatch(r["nonce"])
        and r["consumer_core_sha256"]==_sha(_consumer_core(r["fixture_only"]).encode())
        and _raw(r["producer_registration"])==_raw(producer._registration(PRODUCER_NONCE,r["fixture_only"]))
        and _raw(r["producer_provenance"])==_raw(_producer_provenance(r["fixture_only"])) and _raw(r["scope"])==_raw(_scope()),"consumer_registration_refused")
    p=r["preparation_source"]
    _need(type(p) is dict and set(p)=={"head","source_path","source_sha256","source_inventory_sha256"} and p["source_path"]==SELF_PATH
        and type(p["head"]) is str and producer.control._HEAD.fullmatch(p["head"])
        and all(type(p[name]) is str and producer.control._SHA.fullmatch(p[name]) for name in ("source_sha256","source_inventory_sha256")),"consumer_registration_source_refused")
    old=r["producer_registration"]
    fixed={"schema":SCHEMA+"/acknowledgement","audit_id":AUDIT_ID,"project_id":PROJECT_ID,"execution_notebook":NOTEBOOK,"execution_cell_index":0,
        "registration_sha256":_sha(registration_raw),"consumer_core_sha256":r["consumer_core_sha256"],"fixture_only":r["fixture_only"],
        "producer_notebook":old["notebook"],"producer_registration_sha256":_sha(_raw(old)),"producer_cell_sha256":r["producer_provenance"]["cell_sha256"],
        "producer_acknowledgement_sha256":r["producer_provenance"]["acknowledgement_sha256"],"resolver_calls_attempted":0,"cloud_saves_deletes":0,
        "platform_values_counts_or_digests_exported":False,"backtesting_ready":False}
    value=_decode(raw.removesuffix(b"\n"));dynamic={"disposition","own_receipt_reads","cloud_receipt_chain_consistent","stop_stage","inherited_stop_stage"}
    _need(type(value) is dict and set(value)==set(fixed)|dynamic and _raw({key:value[key] for key in fixed})==_raw(fixed)
        and type(value["own_receipt_reads"]) is int and 0<=value["own_receipt_reads"]<=104 and type(value["cloud_receipt_chain_consistent"]) is bool,"consumer_ack_schema_refused")
    if value["cloud_receipt_chain_consistent"]:
        _need(value["disposition"]=="existing_cloud_receipts_consistent_no_lookup" and value["own_receipt_reads"]==104
            and value["stop_stage"] is value["inherited_stop_stage"] is None,"consumer_ack_false_completion")
    else:
        _need(value["disposition"]=="refused_no_retry" and value["stop_stage"] in {"kernel_claim","inherited_core","inherited_ack","inherited_refusal"}
            and (value["inherited_stop_stage"] in {"kernel_claim","construct","project","consume_readback"} if value["stop_stage"]=="inherited_refusal" else value["inherited_stop_stage"] is None)
            and (value["own_receipt_reads"]==0 if value["stop_stage"]!="inherited_refusal" or value["inherited_stop_stage"]!="consume_readback" else value["own_receipt_reads"]>=1),"consumer_ack_refusal_state")
    return value


class _ArgumentParser(argparse.ArgumentParser):
    def error(self,message):self.exit(2,"consumer_argument_refused\n")


def main(argv=None):
    parser=_ArgumentParser(description=__doc__);parser.add_argument("--expected-head",required=True);args=parser.parse_args(argv)
    try:result=prepare_actual_cell(args.expected_head)
    except BaseException:print('{"disposition":"consumer_local_preparation_refused"}');return 2
    print(_raw({key:value for key,value in result.items() if key!="cell_source"}).decode());return 0


if __name__=="__main__":raise SystemExit(main())
