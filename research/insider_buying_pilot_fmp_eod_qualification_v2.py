"""Fresh stable-data epoch for existing-plan control qualification.

This module never resumes the three failed v1 claims. Source identity remains
the designated worktree; only private data journals use the fixed stable store.
No data or account result grants historical availability, PIT, rights or QC.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import ssl
import subprocess
import sys
import time
import weakref
from urllib import error, parse, request

from research import insider_buying_pilot_fmp_eod_qualification_v1 as legacy
from research import insider_buying_pilot_stable_custody_v2 as stable
from research.insider_buying_keychain_credentials import KeychainCredential, read_keychain_credential

SCHEMA = "insider-pilot-fmp-eod-stable-qualification-v2"
AUDIT_ID = "ib-fmp-eod-stable-qualification-v2-20261103-once"
PROBE_ID = "ib-local-custody-v2-20261103-once"
SELF_PATH = "research/insider_buying_pilot_fmp_eod_qualification_v2.py"
TEST_PATH = "tests/test_insider_buying_pilot_fmp_eod_qualification_v2.py"
OWN_PATHS = (SELF_PATH, TEST_PATH, "research/insider_buying_pilot_stable_custody_v2.py", "tests/test_insider_buying_pilot_stable_custody_v2.py")
LANE_ROOT, LANE_BRANCH = legacy.LANE_ROOT, legacy.LANE_BRANCH
MAX_BODY, MAX_CONTROL, MAX_INPUT_METADATA = legacy.MAX_BODY, legacy.MAX_CONTROL, legacy.MAX_INPUT_METADATA
SPACING_NS = legacy.SPACING_NS
PROBE_SECONDS, PROBE_FILES = 70, 8
_CODES = legacy._CODES | {"storage_unqualified", "source_bindings_required", "worker_payload_refused", "snapshot_refused", "scope_refused"}
_ARMED = weakref.WeakKeyDictionary()
_raw, _sha, _now, authority = legacy._raw, legacy._sha, legacy._now, legacy.authority
_case_list, build_requests, _validate_item = legacy._case_list, legacy.build_requests, legacy._validate_item
_credential, _Reply, _validate_projection = legacy._credential, legacy._Reply, legacy._validate_projection

class QualificationError(ValueError):
    def __init__(self, code, *, details=None):
        super().__init__(code)
        self.details = details

def _need(ok, code):
    if not ok:
        raise QualificationError(code)

def failure_info(exc, stage):
    allowed_stages = {"arguments", "identity", "health", "probe", "proof", "snapshot", "metadata", "bodies", "project",
        "storage-proof", "reservation", "failed-snapshot", "control-metadata", "control-bodies", "bindings", "providers", "final"}
    stage = stage if stage in allowed_stages else "arguments"
    if type(exc) is QualificationError and type(exc.details) is dict:
        value = dict(exc.details)
        if not _valid_failure(value):
            return {"code": "qualification_stopped", "artifact_role": "unknown", "changed_fields": [], "stage": stage}
        if stage != "arguments": value["stage"] = stage
        return value
    if type(exc) is stable.CustodyError:
        value = stable.safe_failure(exc)
        return {"code": value["code"], "artifact_role": value["role"], "changed_fields": value["changed_fields"], "stage": stage}
    code = str(exc) if type(exc) is QualificationError and str(exc) in _CODES else legacy.safe_failure(exc)
    return {"code": code, "artifact_role": "unknown", "changed_fields": [], "stage": stage}

def _valid_failure(value):
    stages = {"arguments", "identity", "health", "probe", "proof", "snapshot", "metadata", "bodies", "project",
        "storage-proof", "reservation", "failed-snapshot", "control-metadata", "control-bodies", "bindings", "providers", "final"}
    return type(value) is dict and set(value)=={"code","artifact_role","changed_fields","stage"} \
        and type(value["code"]) is str and value["code"] in (_CODES | stable._CODES) \
        and type(value["artifact_role"]) is str and value["artifact_role"] in (stable._ROLES | {"unknown"}) \
        and type(value["changed_fields"]) is list and len(value["changed_fields"])<=len(stable._DIFF_FIELDS) \
        and all(type(v) is str and v in stable._DIFF_FIELDS for v in value["changed_fields"]) \
        and len(set(value["changed_fields"]))==len(value["changed_fields"]) \
        and type(value["stage"]) is str and value["stage"] in stages

def _identity(head):
    value = legacy._identity(head)
    own = legacy.custody._source_bytes(LANE_ROOT, OWN_PATHS)
    for name, pin in own.items():
        _need(_sha(legacy.custody._git(LANE_ROOT, "show", head+":"+name)) == pin, "identity_refused")
    sources = {**value["source_sha256"], **own}
    value = {**value, "source_sha256": sources, "source_inventory_sha256": _sha(_raw(sources))}
    _current(value)
    return value

def _current(identity):
    legacy._current(identity)
    _need(set(OWN_PATHS) <= set(identity["source_sha256"]) and legacy.custody._source_bytes(LANE_ROOT, OWN_PATHS)
        == {p: identity["source_sha256"][p] for p in OWN_PATHS}, "identity_refused")

def registration(storage_receipt_sha256):
    _need(type(storage_receipt_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", storage_receipt_sha256), "storage_unqualified")
    return {"schema": SCHEMA+"/registration", "audit_id": AUDIT_ID, "purpose": "provider_control_qualification",
        "storage_receipt_sha256": storage_receipt_sha256, "storage_probe_id": PROBE_ID,
        "required_filing_window": ["2020-10-01", "2025-12-31"], "warmup_controls": 8, "recent_selected_positions": [0,5,8,14],
        "maximum_controls": 12, "maximum_unique_requests": 36, "maximum_attempts_per_request": 1,
        "credential_reads_per_provider": 1, "rows_per_request": 100, "maximum_response_bytes": MAX_BODY,
        "http_open_read_seconds": 15, "http_close_seconds": 1, "source_worker_seconds": 120, "projection_worker_seconds": 30,
        "prior_provider_use_must_be_zero": True, "fresh_operation_not_continuation": True,
        "redirect_retry_paging_fallback_or_resume_permitted": False, "raw_or_normalized_provider_rows_retained": False,
        "receipt_cannot_reparse_unretained_body": True, "authority": authority()}

def probe_registration():
    return {"schema": SCHEMA+"/storage-registration", "audit_id": PROBE_ID, "purpose": "storage_qualification",
        "synthetic_only": True, "minimum_observed_seconds": PROBE_SECONDS, "synthetic_files": PROBE_FILES,
        "minimum_post_publication_seconds": PROBE_SECONDS, "worker_wall_seconds": 240,
        "source_data_reads": 0, "credential_reads": 0, "provider_invocations": 0, "authority": authority()}

def _policy(role, paths=()):
    if role != "probe":
        if role == "snapshot":
            paths = (*paths, *(stable.LEGACY_ROOT/name for name in (stable.LEGACY_AUDIT, stable.LEGACY_SECOND, stable.LEGACY_THIRD)))
        policy = legacy._policy(paths)
        if role == "proof":
            allowed = '(require-any (literal '+json.dumps(str(stable.PRIVATE_CUSTODY_ROOT))+') (subpath '+json.dumps(str(stable.PRIVATE_CUSTODY_ROOT/PROBE_ID))+'))'
            return policy+'(deny file-read* (require-all (subpath '+json.dumps(str(stable.PRIVATE_CUSTODY_ROOT))+') (require-not '+allowed+')))'
        return policy+'(deny file-read* (subpath '+json.dumps(str(stable.PRIVATE_CUSTODY_ROOT))+'))'
    root = stable.PRIVATE_CUSTODY_ROOT
    allowed = '(require-any (literal '+json.dumps(str(root))+') (subpath '+json.dumps(str(root/PROBE_ID))+'))'
    write_allowed = '(require-any (literal "/dev/null") (literal '+json.dumps(str(root))+') (subpath '+json.dumps(str(root/PROBE_ID))+'))'
    policy = '(version 1)(allow default)(deny network*)(deny process-exec (literal "/usr/bin/security"))'
    policy += '(deny file-write* (require-not '+write_allowed+'))'
    policy += '(deny file-read* (require-all (subpath '+json.dumps(str(root))+') (require-not '+allowed+')))'
    # Git may stat tracked ZIP pointers; it cannot read their data here.
    policy += '(deny file-read-data (subpath '+json.dumps(str(LANE_ROOT/"artifacts"))+'))'
    for p in (legacy.RECENT_ROOT, Path("/Volumes"), Path("/Users/sheltonchen/Library/Keychains")):
        policy += '(deny file-read* (subpath '+json.dumps(str(p))+'))'
    return policy

def _probe(identity):
    context = stable.Epoch(identity, probe_registration())
    began = time.monotonic()
    try:
        for i in range(PROBE_FILES):
            context.publish(f"synthetic-{i:03d}.json", {"schema": SCHEMA+"/synthetic", "ordinal": i, "payload": "X"*20800})
        published = time.monotonic()
        checks = 0
        while time.monotonic()-published < PROBE_SECONDS:
            context.check(); checks += 1
            time.sleep(min(1.0, max(0.0, PROBE_SECONDS-(time.monotonic()-published))))
        context.check(); checks += 1
        elapsed = time.monotonic()-began
        receipt = {"schema": SCHEMA+"/storage-qualification", "audit_id": PROBE_ID, "purpose": "storage_qualification",
            "passed": True, "synthetic_only": True, "fixture_only": False, "execution_identity": identity,
            "storage_identity": context.storage_identity,
            "registration": probe_registration(), "observed_seconds": elapsed, "minimum_observed_seconds": PROBE_SECONDS,
            "post_publication_observed_seconds": time.monotonic()-published,
            "synthetic_file_count": PROBE_FILES, "repeated_strict_checks": checks,
            "native_network_denied": True, "live_memory_guard": True, "source_data_reads": 0, "credential_reads": 0,
            "provider_invocations": 0, "authority": authority(),
            "published_leaf_pins": {n: {"bytes": p["bytes"], "sha256": p["sha256"]} for n,p in context.pins.items()}}
        pin = context.publish("complete.json", receipt); context.check()
        return {"passed": True, "audit_id": PROBE_ID, "receipt_sha256": pin, "observed_seconds": elapsed,
            "post_publication_observed_seconds": receipt["post_publication_observed_seconds"],
            "source_inventory_sha256": identity["source_inventory_sha256"], "source_data_reads": 0, "credential_reads": 0,
            "provider_invocations": 0, "authority": authority()}
    finally:
        context.close()

def _proof(identity, supplied, guard):
    _need(type(supplied) is dict and set(supplied) == {"sha256"} and type(supplied["sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", supplied["sha256"]), "storage_unqualified")
    names = ["reservation.json", *(f"synthetic-{i:03d}.json" for i in range(PROBE_FILES)), "complete.json"]
    readback = stable.read_epoch_controls(PROBE_ID, names, {"complete.json": {"bytes": None, "sha256": supplied["sha256"]}}, memory=guard)
    controls = readback["controls"]; receipt = controls["complete.json"]
    keys={"schema","audit_id","purpose","passed","synthetic_only","fixture_only","execution_identity",
        "storage_identity","registration","observed_seconds","minimum_observed_seconds","post_publication_observed_seconds",
        "synthetic_file_count","repeated_strict_checks","native_network_denied","live_memory_guard","source_data_reads",
        "credential_reads","provider_invocations","authority","published_leaf_pins"}
    _need(type(receipt) is dict and set(receipt)==keys
        and receipt["schema"] == SCHEMA+"/storage-qualification" and receipt["passed"] is True
        and receipt["audit_id"]==PROBE_ID and receipt["purpose"]=="storage_qualification"
        and receipt["synthetic_only"] is True and receipt["fixture_only"] is False
        and receipt["execution_identity"] == identity and receipt["registration"] == probe_registration()
        and receipt["storage_identity"] == readback["storage_identity"]
        and type(receipt["observed_seconds"]) in {int,float} and math.isfinite(receipt["observed_seconds"])
        and PROBE_SECONDS <= receipt["observed_seconds"] <= 240
        and type(receipt["post_publication_observed_seconds"]) in {int,float} and math.isfinite(receipt["post_publication_observed_seconds"])
        and PROBE_SECONDS <= receipt["post_publication_observed_seconds"] <= receipt["observed_seconds"]
        and type(receipt["minimum_observed_seconds"]) is int and receipt["minimum_observed_seconds"] == PROBE_SECONDS
        and type(receipt["synthetic_file_count"]) is int and receipt["synthetic_file_count"] == PROBE_FILES
        and type(receipt["repeated_strict_checks"]) is int and 0 < receipt["repeated_strict_checks"] <= 240
        and receipt["native_network_denied"] is receipt["live_memory_guard"] is True
        and all(type(receipt[k]) is int and receipt[k]==0 for k in ("source_data_reads","credential_reads","provider_invocations"))
        and _raw(receipt["authority"]) == _raw(authority()), "storage_unqualified")
    for i in range(PROBE_FILES):
        _need(controls[f"synthetic-{i:03d}.json"] == {"schema": SCHEMA+"/synthetic", "ordinal": i, "payload": "X"*20800}, "storage_unqualified")
    _need(receipt["published_leaf_pins"] == {n:p for n,p in readback["pins"].items() if n!="complete.json"}, "storage_unqualified")
    return {"schema": SCHEMA+"/bound-storage-proof", "receipt_sha256": supplied["sha256"],
        "receipt_head": identity["head"], "source_inventory_sha256": identity["source_inventory_sha256"],
        "storage_identity": readback["storage_identity"],
        "observed_seconds": receipt["observed_seconds"], "passed": True, "fixture_only": False,
        "authority": authority()}

def _worker(role, identity):
    guard = None
    try:
        legacy.native._isolated()
        if role == "probe":
            legacy.custody._effective_denial(require_fork=False)
        else:
            legacy.native.batch.campaign.base._prove_isolation()
        guard = legacy.native._WorkerMemoryGuard(); _current(identity)
        raw = sys.stdin.buffer.read(legacy.ipc.MAX_IPC_INPUT+1)
        _need(len(raw)<=legacy.ipc.MAX_IPC_INPUT, "worker_payload_refused")
        supplied = json.loads(raw) if raw else {}
        if role == "health":
            _need(supplied == {}, "worker_payload_refused")
            data = {"passed": True, "source_only": True, "source_files_opened": False, "native_controls": True, "authority": authority()}
        elif role == "probe":
            _need(supplied == {}, "worker_payload_refused")
            data = _probe(identity)
        elif role == "proof":
            data = _proof(identity, supplied, guard)
        elif role == "snapshot":
            _need(supplied == {}, "worker_payload_refused")
            data = stable.snapshot_actual(memory=guard)
        elif role == "metadata":
            _need(supplied == {}, "worker_payload_refused")
            data = legacy.controls.metadata_actual(memory=guard)
        elif role == "bodies":
            data = legacy.controls.derive_actual(supplied, memory=guard); _case_list(data["cases"])
        elif role == "project":
            _need(type(supplied) is dict and set(supplied)=={"raw_base64","cases","item","credential"}, "worker_payload_refused")
            raw_body=base64.b64decode(supplied["raw_base64"],validate=True)
            _need(0 < len(raw_body) <= MAX_BODY, "worker_payload_refused")
            cred=supplied["credential"]
            _need(type(cred) is dict and set(cred)=={"provider","value"} and cred["provider"] in {"fmp","eodhd"}
                and type(cred["value"]) is str and re.fullmatch(r"[!-~]{1,4096}",cred["value"]), "worker_payload_refused")
            credential=KeychainCredential(cred["provider"],cred["value"])
            legacy._screen(raw_body,credential)
            data={"passed":True,"projection":legacy._project(raw_body,_case_list(supplied["cases"]),supplied["item"])}
        else:
            raise QualificationError("worker_payload_refused")
        _current(identity);guard.check(); wire={"passed":True,"data":data}
    except Exception as exc:
        wire={"passed":False,"failure":failure_info(exc,role)}
    try:
        if guard is not None:guard.check()
        payload=_raw({"ok":True,"value":wire});_need(len(payload)<=MAX_CONTROL,"worker_payload_refused")
        sys.stdout.buffer.write(payload+b"\n");sys.stdout.buffer.flush()
        if guard is not None:guard.check()
    finally:
        if guard is not None:guard.close()

def _child(role,identity,supplied=None,*,paths=()):
    _need(role in {"health","probe","proof","snapshot","metadata","bodies","project"}, "worker_refused")
    code="import sys,json;sys.path.insert(0,"+repr(str(LANE_ROOT))+");from research import insider_buying_pilot_fmp_eod_qualification_v2 as m;m._worker("+repr(role)+",json.loads("+repr(_raw(identity).decode())+"))"
    command=("/usr/bin/env","-i","PATH=/usr/bin:/bin:/usr/sbin:/sbin","/usr/bin/sandbox-exec","-p",_policy(role,paths),
        sys.executable,"-I","-S","-B","-X","pycache_prefix="+legacy.native.EMPTY_CACHE_PREFIX,"-c",code)
    payload=b"" if supplied is None else _raw(supplied)
    _need(len(payload)<=legacy.ipc.MAX_IPC_INPUT,"worker_payload_refused")
    value=legacy.ipc._launch(command,payload,timeout=240 if role=="probe" else 30 if role=="project" else 120)
    _need(type(value) is dict and type(value.get("passed")) is bool,"worker_refused")
    if value["passed"] is not True:
        info=value.get("failure")
        _need(_valid_failure(info), "worker_refused")
        raise QualificationError("worker_refused",details=info)
    _need(set(value)=={"passed","data"},"worker_refused")
    return value["data"]

def _bind_inputs(context,cases,identity,storage_receipt_sha256):
    _case_list(cases)
    value={"schema":SCHEMA+"/input-bindings","code_identity":identity,
        "storage_qualification_sha256":storage_receipt_sha256,
        "storage_receipt_copy_sha256":context.pins["storage-qualification.json"]["sha256"],
        "snapshot_sha256":context.pins["failed-predecessor-snapshot.json"]["sha256"],
        "control_evidence_sha256":context.pins["controls.json"]["sha256"],"control_sha256":_sha(_raw(cases)),
        "fixture_only":context.fixture}
    return context.publish("input-bindings.json",value)

def _validated_bindings(context,cases,identity):
    value=context.read("input-bindings.json")
    _need(_raw(value)==_raw({"schema":SCHEMA+"/input-bindings","code_identity":identity,
        "storage_qualification_sha256":context.registration["storage_receipt_sha256"],
        "storage_receipt_copy_sha256":context.pins["storage-qualification.json"]["sha256"],
        "snapshot_sha256":context.pins["failed-predecessor-snapshot.json"]["sha256"],
        "control_evidence_sha256":context.pins["controls.json"]["sha256"],"control_sha256":_sha(_raw(cases)),
        "fixture_only":context.fixture}), "source_bindings_required")
    _need(_raw(context.registration)==_raw(registration(value["storage_qualification_sha256"]))
        and context.read("controls.json")["cases"]==cases, "source_bindings_required")
    if not context.fixture:
        _need(context.storage_identity==context.read("storage-qualification.json")["storage_identity"], "storage_unqualified")
    return value

def _binding(context,item,credential):
    context.check();_validate_item(item)
    plan=context.read("request-plan.json");bound=context.read("controls.json");cases=_case_list(bound["cases"])
    bindings=_validated_bindings(context,cases,context.identity)
    binding_sha=context.pins["input-bindings.json"]["sha256"]
    _need(_raw(plan)==_raw({"schema":SCHEMA+"/plan","requests":build_requests(cases),"control_sha256":_sha(_raw(cases)),
        "fixture_only":context.fixture,"registration":registration(bindings["storage_qualification_sha256"]),
        "bindings_sha256":binding_sha}), "started_journal_required")
    _need(context.active is not None,"started_journal_required")
    started=context.read(context.active);idx=started["request_index"]
    _need(type(idx) is int and 0<=idx<len(plan["requests"]) and context.active==f"request-{idx:03d}-started.json"
        and plan["requests"][idx]==item and started["fingerprint"]==item["fingerprint"]
        and type(started["maximum_attempts"]) is int and started["maximum_attempts"]==1
        and started["request_plan_sha256"]==context.pins["request-plan.json"]["sha256"]
        and started["input_bindings_sha256"]==binding_sha, "started_journal_required")
    _credential(credential,item["provider"],fixture=context.fixture)
    _need(item["fingerprint"] not in context.dispatched,"started_journal_required")
    return bindings

def _transport(context,item,credential):
    _need(type(context) is stable.Epoch and context.is_actual() and context.fixture is False
        and context.root==LANE_ROOT and context.storage_root==stable.PRIVATE_CUSTODY_ROOT, "started_journal_required")
    _need("input-bindings.json" in context.pins and _ARMED.get(context)==context.pins["input-bindings.json"]["sha256"],"source_bindings_required")
    _binding(context,item,credential);context.dispatched.add(item["fingerprint"])
    url=legacy._live_url(item,credential);parsed=parse.urlsplit(url)
    _need(parsed.scheme=="https" and parsed.netloc in {"financialmodelingprep.com","eodhd.com"}
        and not parsed.fragment and not parsed.username and not parsed.password,"request_refused")
    opener=request.build_opener(request.ProxyHandler({}),legacy._DenyRedirect(),request.HTTPSHandler(context=ssl.create_default_context()))
    req=request.Request(url,headers={"Accept":"application/json","Accept-Encoding":"identity"},method="GET")
    stream=None
    try:
        with legacy._Deadline() as deadline:
            context.check();_need(req.full_url==legacy._live_url(item,credential),"request_refused")
            try:
                try:stream=opener.open(req,timeout=legacy.HTTP_SECONDS)
                except error.HTTPError as exc:stream=exc
                status=stream.getcode()
                _need(type(status) is int and 100<=status<=599 and stream.geturl()==url,"framing_refused")
                return legacy._read_response(stream,status)
            finally:
                if stream is not None:deadline.arm_cleanup();stream.close()
    except TimeoutError:return _Reply(None,b"","transport_timeout")
    except (QualificationError,legacy.ProviderQualificationError) as exc:return _Reply(None,b"",failure_info(exc,"providers")["code"])
    except Exception:return _Reply(None,b"","transport_error")


def _drive(context, cases, identity, *, fixture=False, credential_reader=None, transport=None, project=None):
    _need(context.fixture is fixture and (not fixture and all(v is None for v in (credential_reader, transport, project))
        or fixture and all(callable(v) for v in (credential_reader, transport, project))), "arguments_refused")
    bindings = _validated_bindings(context, cases, identity)
    binding_sha = context.pins["input-bindings.json"]["sha256"]
    if not fixture: _need(_ARMED.get(context) == binding_sha, "source_bindings_required")
    requests = build_requests(cases)
    plan_sha = context.publish("request-plan.json", {"schema": SCHEMA+"/plan", "requests": requests,
        "control_sha256": _sha(_raw(cases)), "fixture_only": fixture,
        "registration": registration(bindings["storage_qualification_sha256"]), "bindings_sha256": binding_sha})
    reader = credential_reader if fixture else read_keychain_credential
    credential_cache, stopped_providers, stopped_families, receipts = {}, set(), set(), []
    previous_finish = None
    for i, item in enumerate(requests):
        provider, family = item["provider"], item["family"]
        if provider in stopped_providers or family in stopped_families:
            receipts.append({"request_index": i, "family": family, "attempted": False, "code": "prior_provider_or_family_refusal"})
            continue
        if provider not in credential_cache:
            context.publish(provider+"-credential-started.json", {"provider": provider, "maximum_reads": 1, "plan_sha256": plan_sha})
            credential = None
            try: credential = _credential(reader(provider), provider, fixture=fixture)
            except Exception: pass
            context.publish(provider+"-credential-completed.json", {"provider": provider,
                "read_observed": credential is not None, "secret_stored_or_hashed": False})
            credential_cache[provider] = credential
            if credential is None:
                stopped_providers.add(provider)
                receipts.append({"request_index": i, "family": family, "attempted": False, "code": "credential_refused"})
                continue
        credential = credential_cache[provider]
        if previous_finish is not None:
            remaining = SPACING_NS - (time.monotonic_ns() - previous_finish)
            if remaining > 0: time.sleep(remaining / 1_000_000_000)
        name = f"request-{i:03d}-started.json"
        context.publish(name, {"schema": SCHEMA+"/request-started", "request_index": i,
            "fingerprint": item["fingerprint"], "maximum_attempts": 1,
            "request_plan_sha256": plan_sha, "input_bindings_sha256": binding_sha, "started_utc": _now()})
        context.active = name; context.check()
        response = transport(item, credential) if fixture else _transport(context, item, credential)
        previous_finish = time.monotonic_ns(); context.active = None; context.check()
        _need(type(response) is _Reply and (response.status is None or type(response.status) is int
            and 100 <= response.status <= 599) and type(response.body) is bytes
            and len(response.body) <= MAX_BODY and (response.code is None or response.code in _CODES), "request_refused")
        observed = None; code = response.code
        if response.status == 200 and code is None:
            relevant = [v for v in cases if v["case_id"] in item["case_ids"]]
            try:
                if fixture: observed = project(response.body, relevant, item, credential)
                else:
                    value = _child("project", identity, {"raw_base64": base64.b64encode(response.body).decode(),
                        "cases": relevant, "item": item, "credential": {"provider": provider, "value": credential.value}})
                    _need(value.get("passed") is True and type(value.get("projection")) is dict, "projection_refused")
                    observed = value["projection"]
                _validate_projection(observed, relevant)
                _need(len(_raw(observed)) <= MAX_INPUT_METADATA, "projection_refused")
                if observed["scoped"] is False: code = "provider_scope_refused"
            except Exception:
                code = "projection_refused"; observed = None
        else: code = code or "http_refused"
        if code is not None:
            if response.status in {401, 429} or response.status is None or (response.status is not None and response.status >= 500):
                stopped_providers.add(provider)
            else: stopped_families.add(family)
        record = {"schema": SCHEMA+"/request-completed", "request_index": i, "family": family,
            "attempted": True, "fingerprint": item["fingerprint"], "http_status": response.status,
            "code": code or "metadata_projected", "projection": observed, "raw_response_retained": False,
            "error_or_refused_body_hashed_or_retained": False, "finished_utc": _now()}
        context.publish(f"request-{i:03d}-completed.json", record); receipts.append(record)
    return {"schema": SCHEMA+"/complete", "fixture_only": fixture, "execution_head": identity["head"],
        "planned_requests": len(requests), "transport_invocation_count": sum(v["attempted"] for v in receipts),
        "unattempted_requests": sum(not v["attempted"] for v in receipts),
        "credential_reads_observed": sum(v is not None for v in credential_cache.values()),
        "credential_read_attempts": len(credential_cache),
        "projected_responses": sum(v.get("projection") is not None for v in receipts),
        "scoped_responses": sum(v.get("projection") is not None and v["projection"]["scoped"] for v in receipts),
        "clean_scoped_responses": sum(v.get("projection") is not None and v["projection"]["scoped"] and v["projection"]["metadata_clean"] for v in receipts),
        "receipts": receipts, "authority": authority(), "raw_response_retained": False,
        "remote_request_count_measured": False, "completed_utc": _now()}


def preflight_actual(head):
    identity=_identity(head);value=_child("health",identity);_current(identity)
    _need(value=={"passed":True,"source_only":True,"source_files_opened":False,"native_controls":True,"authority":authority()},"worker_refused")
    return {**value,"source_images":len(identity["source_sha256"]),"source_inventory_sha256":identity["source_inventory_sha256"]}

def run_storage_qualification(head):
    identity=_identity(head)
    stable.prepare_actual_root()
    value=_child("probe",identity);_current(identity)
    return value

def run_actual(head,storage_receipt_sha256):
    identity=_identity(head);context=None;stage="storage-proof"
    try:
        reg=registration(storage_receipt_sha256)
        proof=_child("proof",identity,{"sha256":storage_receipt_sha256})
        stage="reservation";context=stable.Epoch(identity,reg)
        _need(context.storage_identity==proof["storage_identity"], "storage_unqualified")
        context.publish("storage-qualification.json",proof)
        stage="failed-snapshot";context.publish("failed-snapshot-started.json",{"worker_invocations":1})
        snapshot=_child("snapshot",identity,paths=stable.snapshot_paths())
        stable.validate_snapshot(snapshot,fixture=False)
        context.publish("failed-predecessor-snapshot.json",snapshot)
        stage="control-metadata";context.publish("controls-metadata-started.json",{"worker_invocations":1})
        metadata=_child("metadata",identity,paths=legacy.controls.metadata_paths())
        _need(len(_raw(metadata))<=MAX_INPUT_METADATA,"controls_refused");context.publish("controls-metadata.json",metadata)
        stage="control-bodies";context.publish("controls-bodies-started.json",{"worker_invocations":1,"metadata_sha256":_sha(_raw(metadata))})
        bound=_child("bodies",identity,metadata,paths=legacy.controls.body_paths(metadata))
        cases=_case_list(bound["cases"]);_need(len(cases)==12 and bound["fixture_only"] is False
            and bound["warmup_full_readback_verified"] is True and bound["recent_selected_parent_count"]==4,"controls_refused")
        context.publish("controls.json",bound)
        stage="bindings";binding_sha=_bind_inputs(context,cases,identity,storage_receipt_sha256);_ARMED[context]=binding_sha
        stage="providers";result=_drive(context,cases,identity)
        result.update(storage_receipt_sha256=storage_receipt_sha256,scope_reservation_sha256=context.latch["sha256"],
            input_bindings_sha256=binding_sha,control_evidence_sha256=context.pins["controls.json"]["sha256"],
            failed_snapshot_sha256=context.pins["failed-predecessor-snapshot.json"]["sha256"],
            published_leaf_pins={n:{"bytes":p["bytes"],"sha256":p["sha256"]} for n,p in context.pins.items()})
        stage="final";receipt_sha=context.publish("complete.json",result);context.check()
        return {**public_summary(result), "complete_receipt_sha256":receipt_sha}
    except Exception as exc:
        raise QualificationError("qualification_stopped",details=failure_info(exc,stage)) from None
    finally:
        if context is not None:
            _ARMED.pop(context,None);context.close()

def public_summary(result):
    _need(type(result) is dict and result.get("schema")==SCHEMA+"/complete","arguments_refused")
    return {k:result[k] for k in ("schema","fixture_only","execution_head","planned_requests","transport_invocation_count",
        "unattempted_requests","credential_reads_observed","credential_read_attempts","projected_responses","scoped_responses",
        "clean_scoped_responses","authority","raw_response_retained","remote_request_count_measured")}

def main(argv=None):
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--expected-head",required=True)
    modes=cli.add_mutually_exclusive_group()
    modes.add_argument("--health",action="store_true")
    modes.add_argument("--storage-qualification",action="store_true")
    cli.add_argument("--storage-receipt-sha256")
    args=cli.parse_args(argv)
    try:
        _need(not ((args.health or args.storage_qualification) and args.storage_receipt_sha256),"arguments_refused")
        if args.health:value=preflight_actual(args.expected_head)
        elif args.storage_qualification:value=run_storage_qualification(args.expected_head)
        else:
            _need(args.storage_receipt_sha256 is not None,"storage_unqualified")
            value=run_actual(args.expected_head,args.storage_receipt_sha256)
    except Exception as exc:
        print(_raw({"refused":failure_info(exc,"arguments"),"authority":authority()}).decode());return 2
    print(_raw(value).decode())
    return 0 if args.health or args.storage_qualification or value["clean_scoped_responses"]==value["planned_requests"] else 2

if __name__=="__main__":
    raise SystemExit(main())
