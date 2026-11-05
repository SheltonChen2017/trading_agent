"""Fixed OFF control-only native configuration census; no import effects.

Only a deterministic SPY metadata census can be uploaded. The parent probe
and its guard remain unchanged. Shared pure custody and regular-file proof
helpers are pinned; this module owns the closed plans, proofs and fixed TLS
executor. No parent config, helper source or private security identity enters
this action contract. All research and operational acceptance remains false.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import time

from . import native_cache_actions_20261104 as fixed
from . import native_config_census_20261104 as builder

api, projects, ops, evidence = fixed.api, fixed.projects, fixed.ops, fixed.evidence
MODULE = "research/target_price_revisions_qc/native_config_census_actions_20261104.py"
REQUIRED_SOURCES = fixed.REQUIRED_SOURCES | builder.REQUIRED_SOURCES | frozenset((MODULE,))
PINS = {**fixed.PINS, **builder.PINNED, fixed.MODULE: "c2f4778240898d9fc4ae563a06e8df2c8ec93ae51e5c9aec7a98948e9cf012be",
    builder.MODULE: "75eeb1338fc0a7a418c07335122e33b40af86ee0e711127c5d16847e59a1d5ff"}
OWNER_SHA256, CREATION_OWNER_SHA256 = fixed.OWNER_SHA256, fixed.CREATION_OWNER_SHA256
REGISTRY_SHA256 = fixed.REGISTRY_SHA256
BASELINE_INVENTORY_SHA256 = "336251d676c9a176d113d3e8127202cb300562b590e9f24316cda3b1d79566fb"
PRIVATE_ROOT = api.PRIVATE_ROOT.parent / "native-config-census-actions-20261104"
PROOF_KEYS = fixed.PROOF_KEYS
MAX_PROOF_BYTES, MAX_OUTPUT_BYTES = fixed.MAX_PROOF_BYTES, fixed.MAX_OUTPUT_BYTES
SECONDS = fixed.SECONDS
ACTION_SCHEMA = "tpr-fixed-control-config-census-action-v1"
RESULT_SCHEMA = "tpr-fixed-control-config-census-action-result-v1"
ACTION_KEYS = frozenset(("schema", "phase", "probe_operation_id", "diagnostic_attempt",
    "attempt_id", "diagnostic_look_id", "latest_owner_instruction_sha256", "api_plan",
    "before_inventory", "source_inventory", "compile_id", "compile_evidence"))

ActionRefusal, ActionCancelled, ActionFatal = fixed.ActionRefusal, fixed.ActionCancelled, fixed.ActionFatal
_fail, _wire, _sha = fixed._fail, fixed._wire, fixed._sha
_closed, _parse, _descriptor = fixed._closed, fixed._parse, fixed._descriptor
_inventory, _request, _read_proof = fixed._inventory, fixed._request, fixed._read_proof
_projection, _native_integer = fixed._projection, fixed._native_integer
_reservation_names = fixed._reservation_names


def _prepare(*, phase, project_bindings_raw, expected_project_bindings_sha256,
        source_hashes, operation_id, probe_operation_id, git_head, latest_owner_instruction_sha256,
        created_utc, expires_utc, diagnostic_attempt, attempt_id, diagnostic_look_id,
        source_inventory, compile_id=None, compile_evidence=None, fixture=False):
    if (phase not in ("upload", "compile", "build", "launch") or type(source_hashes) is not dict
            or set(source_hashes) != REQUIRED_SOURCES or len(source_hashes) > 48
            or type(operation_id) is not str or re.fullmatch(r"TPR-CMP29-API-CENSUS-[A-Z0-9-]{1,59}", operation_id) is None
            or latest_owner_instruction_sha256 != OWNER_SHA256
            or type(diagnostic_attempt) is not int or not 1 <= diagnostic_attempt <= 2**31-1):
        _fail()
    for identity, pattern in ((attempt_id, r"TPR-CENSUS-ATTEMPT-[A-Z0-9-]{1,69}"),
            (diagnostic_look_id, r"TPR-CENSUS-LOOK-[A-Z0-9-]{1,69}")):
        if type(identity) is not str or re.fullmatch(pattern, identity) is None:
            _fail()
    for name, digest in source_hashes.items():
        api._hash(digest)
        if name in PINS and digest != PINS[name]:
            _fail()
    registry = projects.validate_bindings(project_bindings_raw, expected_sha256=expected_project_bindings_sha256)
    if ({name: row["project_id"] for name, row in registry["projects"].items()} != api.REGISTERED_PROJECTS
            or registry["adapter_source_sha256"] != source_hashes[api.PROJECTS_MODULE]
            or not fixture and (len(project_bindings_raw) != 3573 or expected_project_bindings_sha256 != REGISTRY_SHA256
                or registry["owner_instruction_sha256"] != CREATION_OWNER_SHA256)):
        _fail()
    raw, report_raw = builder.build_config_census(operation_id=probe_operation_id, git_head=git_head)
    report, before = _parse(report_raw), _inventory(source_inventory)
    # A single frozen baseline is retained in EVERY phase. Only main may differ.
    if not fixture and _sha(api._canonical(before)) != BASELINE_INVENTORY_SHA256:
        _fail()
    main = {"bytes": len(raw), "sha256": _sha(raw)}
    inventory = {**before, "main.py": main}
    evidence_inputs = {}
    if phase in ("build", "launch"):
        api._identity(compile_id)
    elif compile_id is not None:
        _fail()
    if phase == "launch":
        _closed(compile_evidence, PROOF_KEYS)
        evidence_inputs = {key: _descriptor(value) for key, value in compile_evidence.items()}
        if (len({row["name"] for row in evidence_inputs.values()}) != 8
                or sum(row["bytes"] for row in evidence_inputs.values()) > MAX_PROOF_BYTES):
            _fail()
    elif compile_evidence is not None:
        _fail()
    project = builder.PROJECT_ID
    if phase == "upload":
        requests = [_request("before", "files/read", {"projectId": project}, before),
            _request("write", "files/update", {"projectId": project, "name": "main.py", "content": raw.decode("ascii")}),
            _request("after", "files/read", {"projectId": project}, inventory)]
    elif phase == "compile":
        requests = [_request("before", "files/read", {"projectId": project}, inventory),
            _request("compile", "compile/create", {"projectId": project}),
            _request("after", "files/read", {"projectId": project}, inventory)]
    elif phase == "build":
        requests = [_request("build", "compile/read", {"projectId": project, "compileId": compile_id})]
    else:
        requests = [_request("before", "files/read", {"projectId": project}, inventory),
            _request("launch", "backtests/create", {"projectId": project, "compileId": compile_id,
                "backtestName": "TPR-CONFIG-CENSUS-20261104-OFF-D" + str(diagnostic_attempt)}),
            _request("after", "files/read", {"projectId": project}, inventory)]
    plan = api.prepare_plan(project_bindings_raw=project_bindings_raw,
        expected_project_bindings_sha256=expected_project_bindings_sha256, arm="cap_off",
        candidate_config_sha256=report["config_sha256"], candidate_attempt=diagnostic_attempt,
        operation_id=operation_id, git_head=git_head, source_hashes=source_hashes,
        owner_instruction_sha256=registry["owner_instruction_sha256"], created_utc=created_utc,
        expires_utc=expires_utc, requests=requests,
        allowed_source_hashes={"main.py": main["sha256"]} if phase == "upload" else {},
        attempt_id=None if phase == "build" else attempt_id,
        reserved_look_id=None if phase == "build" else diagnostic_look_id,
        mode="offline-fixture" if fixture else "production")
    action = {"schema": ACTION_SCHEMA, "phase": phase,
        "probe_operation_id": probe_operation_id, "diagnostic_attempt": diagnostic_attempt,
        "attempt_id": attempt_id, "diagnostic_look_id": diagnostic_look_id,
        "latest_owner_instruction_sha256": latest_owner_instruction_sha256, "api_plan": plan,
        "before_inventory": before, "source_inventory": inventory,
        "compile_id": compile_id, "compile_evidence": evidence_inputs}
    if SECONDS*len(_requests(action)) > (api._clock(expires_utc)-api._clock(created_utc)).total_seconds():
        _fail()
    return api._clone(action)


def prepare_action(*, phase, project_bindings_raw, expected_project_bindings_sha256,
        source_hashes, operation_id, probe_operation_id, git_head, latest_owner_instruction_sha256,
        created_utc, expires_utc, diagnostic_attempt, attempt_id, diagnostic_look_id,
        source_inventory, compile_id=None, compile_evidence=None):
    """Pure construction; caller must freshly claim the registry/baseline read."""
    try:
        return _prepare(**locals())
    except Exception:
        _fail()


def _prepare_fixture(**kwargs):
    # Private synthetic custody only. No runtime/source/input override exists.
    try:
        if "fixture" in kwargs:
            _fail()
        return _prepare(**kwargs, fixture=True)
    except Exception:
        _fail()


def _requests(action):
    prefix = [] if action["phase"] == "build" else [
        _request("metadata", "projects/read", {"projectId": builder.PROJECT_ID}),
        _request("collaborators", "projects/collaboration/read", {"projectId": builder.PROJECT_ID}),
        _request("jobs", "backtests/list", {"projectId": builder.PROJECT_ID})]
    return prefix + action["api_plan"]["requests"]

def _validated(action):
    _closed(action, ACTION_KEYS)
    plan = api._validated(action["api_plan"])
    kwargs = {key: action[key] for key in ("phase", "probe_operation_id", "diagnostic_attempt",
        "attempt_id", "diagnostic_look_id", "latest_owner_instruction_sha256", "compile_id")}
    kwargs.update(project_bindings_raw=plan["project_bindings_json"].encode("ascii"),
        expected_project_bindings_sha256=plan["project_bindings_sha256"], source_hashes=plan["source_hashes"],
        operation_id=plan["operation_id"], git_head=plan["git_head"], created_utc=plan["created_utc"],
        expires_utc=plan["expires_utc"], source_inventory=action["before_inventory"],
        compile_evidence=action["compile_evidence"] or None, fixture=plan["mode"] == "offline-fixture")
    expected = _prepare(**kwargs)
    if _wire(action) != _wire(expected):
        _fail()
    return expected


def _proof(action, raws):
    _closed(raws, PROOF_KEYS)
    for key, raw in raws.items():
        descriptor = action["compile_evidence"][key]
        if len(raw) != descriptor["bytes"] or _sha(raw) != descriptor["sha256"]:
            _fail()
    compiled, built = _validated(_parse(raws["compile_plan"])), _validated(_parse(raws["build_plan"]))
    if compiled["phase"] != "compile" or built["phase"] != "build":
        _fail()
    for other in (compiled, built):
        for key in ("before_inventory", "probe_operation_id", "diagnostic_attempt", "attempt_id", "diagnostic_look_id",
                "latest_owner_instruction_sha256", "source_inventory"):
            if other[key] != action[key]:
                _fail()
        for key in ("git_head", "source_hashes", "project_id", "candidate_config_sha256", "candidate_binding_sha256", "mode"):
            if other["api_plan"][key] != action["api_plan"][key]:
                _fail()
    ids = [item["api_plan"]["operation_id"] for item in (compiled, built, action)]
    if len(set(ids)) != 3 or built["compile_id"] != action["compile_id"]:
        _fail()
    if not (api._clock(compiled["api_plan"]["created_utc"]) <= api._clock(built["api_plan"]["created_utc"])
            <= api._clock(action["api_plan"]["created_utc"])):
        _fail()
    results = [_parse(raws[key]) for key in ("compile_result", "build_result")]
    for other, result in zip((compiled, built), results):
        if (result.get("schema") != RESULT_SCHEMA or result.get("status") != "completed"
                or result.get("action_sha256") != _sha(_wire(other)) or result.get("receipt_published") is not True
                or result.get("lock_cleanup_complete") is not True or result.get("automatic_retry") is not False
                or result.get("observed_job_ids") != []
                or any(result.get(key) is not False for key in builder.FLAGS)):
            _fail()
        expected = {"operation_id": other["api_plan"]["operation_id"], "phase": other["phase"],
            "git_head": other["api_plan"]["git_head"], "project_id": builder.PROJECT_ID,
            "candidate_config_sha256": other["api_plan"]["candidate_config_sha256"]}
        if any(type(result.get(key)) is not type(value) or result[key] != value for key, value in expected.items()):
            _fail()
        requests = _requests(other)
        counts = {"actual_new_diagnostic_jobs": 0, "financial_attempts_created": 0, "financial_outcome_looks": 0,
            "compile_requests_attempted": int(other["phase"] == "compile"), "transport_calls_attempted": len(requests)}
        if any(type(result.get(key)) is not int or result[key] != value for key, value in counts.items()):
            _fail()
        if type(result.get("requests")) is not list or len(result["requests"]) != len(requests):
            _fail()
        for row, request in zip(result["requests"], requests):
            if (row.get("id") != request["id"] or row.get("endpoint") != request["endpoint"]
                    or row.get("status") != "succeeded" or row.get("http_status") != 200):
                _fail()
    names = {"compile_plan": ids[0]+".action.spent.json", "compile_result": ids[0]+".result.json",
        "build_plan": ids[1]+".action.spent.json", "build_result": ids[1]+".result.json"}
    mapping = ((results[0], "before", "source_before", compiled), (results[0], "compile", "compile_response", compiled),
        (results[0], "after", "source_after", compiled), (results[1], "build", "build_response", built))
    registry = projects.validate_bindings(action["api_plan"]["project_bindings_json"].encode("ascii"),
        expected_sha256=action["api_plan"]["project_bindings_sha256"])
    for result, identity, key, other in mapping:
        row = next(item for item in result["requests"] if item["id"] == identity)
        request = next(item for item in _requests(other) if item["id"] == identity)
        names[key] = other["api_plan"]["operation_id"]+"."+identity+".response.raw"
        if row.get("raw_response") != action["compile_evidence"][key]:
            _fail()
        projected = _projection(_parse(raws[key]), request, registry,
            latest_owner_instruction_sha256=other["latest_owner_instruction_sha256"])
        if projected != row.get("projection"):
            _fail()
        if identity in ("compile", "build") and projected["compile_id"] != action["compile_id"]:
            _fail()
    if any(action["compile_evidence"][key]["name"] != name for key, name in names.items()):
        _fail()
    return True

def _guard(plan):
    fixed._guard(plan)
    if (Path(__file__) != api.LANE/MODULE or Path(fixed.__file__) != api.LANE/fixed.MODULE
            or Path(builder.__file__) != api.LANE/builder.MODULE
            or api.subprocess.run(["git", "check-ignore", "-q", str(PRIVATE_ROOT)], cwd=api.LANE,
                capture_output=True, timeout=10).returncode):
        _fail()


def _execute(action, root, lock_root, *, transport, guard, clock, monotonic, fixture):
    action = _validated(action)
    plan = action["api_plan"]
    if (not fixture and (root != PRIVATE_ROOT or lock_root != api.PRIVATE_ROOT or transport is not projects._native_request
            or guard is not _guard or clock is not api._utcnow or monotonic is not time.monotonic or plan["mode"] != "production")
            or fixture and (plan["mode"] != "offline-fixture" or root == PRIVATE_ROOT or root.is_relative_to(api.LANE)
                or lock_root != root or transport is projects._native_request)):
        _fail()
    frozen, started, previous_now, previous_tick = _wire(action), monotonic(), None, None
    registry = projects.validate_bindings(plan["project_bindings_json"].encode("ascii"), expected_sha256=plan["project_bindings_sha256"])
    def check(seconds=0):
        nonlocal previous_now, previous_tick
        guard(plan)
        now, tick = clock(), monotonic()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0)
                or not api._clock(plan["created_utc"]) <= now < api._clock(plan["expires_utc"])
                or type(tick) not in (int, float) or not 0 <= tick-started < 600
                or previous_now is not None and now < previous_now or previous_tick is not None and tick < previous_tick
                or api._clock(plan["expires_utc"])-now < timedelta(seconds=seconds) or 600-(tick-started) < seconds
                or _wire(action) != frozen):
            _fail()
        previous_now, previous_tick = now, tick
    check()
    if root.resolve() != root or lock_root.resolve() != lock_root:
        _fail()
    for path in ((ops.PRIVATE_PARENT, api.PRIVATE_ROOT.parent, api.PRIVATE_ROOT, root) if not fixture else (root,)):
        path.mkdir(mode=0o700, exist_ok=True)
        ops._custody(path.lstat(), True)
    operation, lock, stop, written = plan["operation_id"], None, None, 0
    result = {"schema": RESULT_SCHEMA, "phase": action["phase"],
        "operation_id": operation, "action_sha256": _sha(frozen), "git_head": plan["git_head"],
        "project_id": builder.PROJECT_ID, "candidate_config_sha256": plan["candidate_config_sha256"],
        "status": "failed_or_uncertain", "requests": [], "transport_calls_attempted": 0,
        "compile_requests_attempted": 0, "actual_new_diagnostic_jobs": 0, "observed_job_ids": [],
        "private_reads_attempted": 0, "private_bytes_read": 0, "dependency_claims": [], "launch_reservations": [],
        "action_claim_published": None,
        "response_bytes": 0, "receipt_published": False, "lock_cleanup_complete": False,
        "automatic_retry": False, "financial_attempts_created": 0, "financial_outcome_looks": 0,
        "configuration_census_only": True, **{key: False for key in builder.FLAGS}}
    def publish(name, raw):
        nonlocal written
        if type(raw) is not bytes or not 0 < len(raw) <= 2*1024*1024 or written+len(raw) > MAX_OUTPUT_BYTES:
            _fail()
        value = api._publish(root, name, raw)
        written += len(raw)
        return value
    try:
        publish(operation+".action.spent.json", frozen)
        result["action_claim_published"] = True
    except FileExistsError:
        _fail()  # Never touch a spent operation's historical result or claim.
    except BaseException as error:
        stop = error  # A partial/fsynced interrupted claim remains spent.
    lock_path = lock_root/"comparison-api.lock"
    try:
        if stop is not None:
            raise stop
        lock = os.open(lock_path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
        ops._custody(os.fstat(lock))
        wire = _wire({"operation_id": operation, "action_sha256": result["action_sha256"]})
        if os.write(lock, wire) != len(wire):
            _fail()
        os.fsync(lock)
        directory = os.open(lock_root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)
        raws = {}
        for key in PROOF_KEYS if action["phase"] == "launch" else ():
            check()
            descriptor = action["compile_evidence"][key]
            result["dependency_claims"].append(publish(operation+"."+key+".read.spent.json", _wire({
                "action_sha256": result["action_sha256"], "source_hashes": plan["source_hashes"],
                "git_head": plan["git_head"], "input": descriptor, "attempt_id": action["attempt_id"],
                "diagnostic_look_id": action["diagnostic_look_id"], "created_utc": plan["created_utc"], "expires_utc": plan["expires_utc"]})))
            check(SECONDS)
            result["private_reads_attempted"] += 1
            raw = _read_proof(root, descriptor)
            result["private_bytes_read"] += len(raw)
            if len(raw) != descriptor["bytes"] or _sha(raw) != descriptor["sha256"]:
                _fail()
            raws[key] = raw
        if action["phase"] == "launch":
            _proof(action, raws)
            reservation = _wire({"action_sha256": result["action_sha256"], "source_hashes": plan["source_hashes"],
                "git_head": plan["git_head"], "project_id": builder.PROJECT_ID,
                "candidate_config_sha256": plan["candidate_config_sha256"],
                "probe_operation_id": action["probe_operation_id"], "diagnostic_attempt": action["diagnostic_attempt"],
                "attempt_id": action["attempt_id"], "diagnostic_look_id": action["diagnostic_look_id"],
                "latest_owner_instruction_sha256": action["latest_owner_instruction_sha256"],
                "created_utc": plan["created_utc"], "expires_utc": plan["expires_utc"]})
            for name in _reservation_names(action):
                check()
                result["launch_reservations"].append(publish(name, reservation))
        for request in _requests(action):
            check()
            row = {"id": request["id"], "endpoint": request["endpoint"], "status": "failed_or_unknown",
                "http_status": None, "raw_response": None, "projection": None, "request_claim": None}
            result["requests"].append(row)
            row["request_claim"] = publish(operation+"."+request["id"]+".request.spent.json", _wire({
                "action_sha256": result["action_sha256"], "request": request, "git_head": plan["git_head"],
                "source_hashes": plan["source_hashes"], "created_utc": plan["created_utc"], "expires_utc": plan["expires_utc"],
                "latest_owner_instruction_sha256": action["latest_owner_instruction_sha256"],
                "registry_creation_owner_instruction_sha256": registry["owner_instruction_sha256"],
                "attempt_id": action["attempt_id"], "diagnostic_look_id": action["diagnostic_look_id"]}))
            check(request["seconds"])  # AFTER fsync/source checks, BEFORE Keychain/TLS.
            result["transport_calls_attempted"] += 1
            if request["id"] == "compile": result["compile_requests_attempted"] += 1
            if request["id"] == "launch": result["actual_new_diagnostic_jobs"] = None
            raw, status, credential, owner = transport(request["endpoint"], api._canonical(request["payload"]),
                request["seconds"], request["max_response_bytes"], registry["owner_id"])
            check()
            if (type(raw) is not bytes or not 0 < len(raw) <= request["max_response_bytes"]
                    or result["response_bytes"]+len(raw) > 8*1024*1024 or type(status) is not int
                    or _native_integer(owner) != registry["owner_id"] or type(credential) is not str
                    or re.fullmatch(r"[!-~]{1,256}", credential) is None):
                _fail()
            evidence.project_wire(raw, credential=credential)
            result["response_bytes"] += len(raw)
            row["http_status"] = status
            row["raw_response"] = publish(operation+"."+request["id"]+".response.raw", raw)
            if status != 200:
                _fail()
            row["projection"] = _projection(evidence.parse_json(raw), request, registry,
                latest_owner_instruction_sha256=action["latest_owner_instruction_sha256"])
            if request["id"] == "launch":
                result["observed_job_ids"].append(row["projection"]["backtest_id"])
                result["actual_new_diagnostic_jobs"] = 1
            row["status"] = "succeeded"
        check()
        result["status"] = "completed"
    except BaseException as error:
        stop = error
    finally:
        if lock is not None:
            try:
                current, owned = os.stat(lock_path, follow_symlinks=False), os.fstat(lock)
                if (current.st_dev, current.st_ino) != (owned.st_dev, owned.st_ino):
                    _fail()
                os.unlink(lock_path)
                os.close(lock)
                lock = None
                directory = os.open(lock_root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try: os.fsync(directory)
                finally: os.close(directory)
                result["lock_cleanup_complete"] = True
            except BaseException as error:
                stop = api._retain_stop(stop, error)
            finally:
                if lock is not None:
                    try: os.close(lock)
                    except BaseException as error: stop = api._retain_stop(stop, error)
        if stop is not None:
            result["status"] = "cancelled" if isinstance(stop, KeyboardInterrupt) else "failed_or_uncertain"
        result["receipt_published"] = True
        try:
            result["receipt"] = publish(operation+".result.json", _wire(result))
        except BaseException as error:
            result["receipt_published"] = False
            stop = api._retain_stop(stop, error)
    if isinstance(stop, KeyboardInterrupt):
        raise ActionCancelled(result) from None
    if stop is not None and not isinstance(stop, Exception):
        raise ActionFatal(result) from None
    return api._clone(result)

def execute_action(action):
    """Production: fixed owner-bound native TLS only, no callback/override."""
    try:
        if action["api_plan"]["mode"] != "production":
            _fail()
        return _execute(action, PRIVATE_ROOT, api.PRIVATE_ROOT, transport=projects._native_request,
            guard=_guard, clock=api._utcnow, monotonic=time.monotonic, fixture=False)
    except (ActionCancelled, ActionFatal):
        raise
    except Exception:
        _fail()

def _execute_fixture(action, root, *, transport, clock, guard=lambda _: None, monotonic=lambda: 0.0):
    try:
        return _execute(action, root, root, transport=transport, guard=guard, clock=clock, monotonic=monotonic, fixture=True)
    except (ActionCancelled, ActionFatal):
        raise
    except Exception:
        _fail()
