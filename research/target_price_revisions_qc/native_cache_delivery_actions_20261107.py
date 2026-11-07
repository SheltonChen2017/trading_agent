"""Fixed OFF-only delivery-census actions; pure preparation, no import effects.

This successor never dispatches the retired generic mutation executor. It
regenerates one pinned nonfinancial main, preserves every other cloud file,
checks fresh ownership and absence of active jobs, and verifies the retained
compile chain before a single diagnostic launch. The genuine owner-bound TLS
transport is fixed in production. Nothing here grants financial acceptance.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from . import comparison_20261029_project_api as api
from . import comparison_20261103_project_custody as custody
from . import native_cache_delivery_probe_20261107 as builder

projects, ops, evidence = api.projects, api.ops, api.e
MODULE = "research/target_price_revisions_qc/native_cache_delivery_actions_20261107.py"
REQUIRED_SOURCES = api.REQUIRED_SOURCES | builder.REQUIRED_SOURCES | frozenset((MODULE, custody.MODULE))
PINS = {api.MODULE: "680f31f17447e240f919435ee1d56a9a48526f5197e37ac97332b4b70ee42b87",
    api.PROJECTS_MODULE: "6dc87f33105de9d80e7a267a6cc737bb4262f47e49c43b65247592927a5788d7",
    custody.MODULE: "702d31144a7e62b59a53d374af695078f150809b19f0992415e690d07fa418a4",
    builder.MODULE: "2b6f1225c1e7296f79db831d464a1fbabaa4bfccf80eaaf5267dd35eba3cc6d8",
    **builder.PINNED}
OWNER_SHA256 = "1d0fad9452169f520b28be16f0e0f6ddd2c356dab28a7d127806e85f1f132daa"
MIA_PUBLIC_ID_SHA256 = "790fd84f9177e87e0c5bc385f8bef44e107330b3d2ff329d9b59f26298704ee1"
MIA_PRIVACY_BASIS = "owner_and_authorized_mia_component"
CREATION_OWNER_SHA256 = custody.CREATION_OWNER_SHA256
REGISTRY_SHA256 = custody.REGISTRY_SHA256
PRIVATE_ROOT = api.PRIVATE_ROOT.parent / "native-cache-delivery-actions-20261107"
PROOF_KEYS = ("compile_plan", "compile_result", "source_before", "compile_response",
    "source_after", "build_plan", "build_result", "build_response")
MAX_PROOF_BYTES, MAX_OUTPUT_BYTES = 12*1024*1024, 24*1024*1024
MAX_CONTROL_BYTES, SECONDS = 131072, 20
TERMINAL = frozenset(("Completed", "Completed.", "Runtime Error", "RuntimeError", "Error", "Stopped", "Cancelled"))
ACTION_KEYS = frozenset(("schema", "phase", "parent_probe_config_json", "helper_source_utf8", "probe_operation_id",
    "diagnostic_attempt", "attempt_id", "diagnostic_look_id", "latest_owner_instruction_sha256",
    "api_plan", "before_inventory", "source_inventory", "compile_id", "compile_evidence"))


class ActionRefusal(ValueError):
    pass


class ActionCancelled(KeyboardInterrupt):
    def __init__(self, report):
        self.report = api._clone(report)
        super().__init__("cache diagnostic cancelled; no automatic retry")


class ActionFatal(BaseException):
    def __init__(self, report):
        self.report = api._clone(report)
        super().__init__("cache diagnostic stopped; no automatic retry")


def _fail():
    raise ActionRefusal("fixed cache diagnostic action refused") from None


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()


def _native_integer(value):
    try:
        if type(value) is evidence.JsonNumber and re.fullmatch(r"[0-9]+", value.lexeme) is None:
            _fail()
        return projects._integer(value)
    except Exception:
        _fail()


def _parse(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 2*1024*1024:
        _fail()
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail()
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: _fail())
    except Exception:
        _fail()


def _descriptor(value):
    _closed(value, ("name", "bytes", "sha256"))
    if (type(value["name"]) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", value["name"]) is None
            or type(value["bytes"]) is not int or not 0 < value["bytes"] <= 2*1024*1024):
        _fail()
    api._hash(value["sha256"])
    return api._clone(value)


def _inventory(value):
    if type(value) is not dict or not 1 <= len(value) <= 25 or "main.py" not in value:
        _fail()
    for name, row in value.items():
        if type(name) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", name) is None:
            _fail()
        _closed(row, ("bytes", "sha256"))
        if type(row["bytes"]) is not int or not 0 < row["bytes"] <= 1024*1024:
            _fail()
        api._hash(row["sha256"])
    return api._clone(value)


def _request(identity, endpoint, payload, inventory=None):
    request = {"id": identity, "endpoint": endpoint, "payload": payload, "payload_file": None,
        "payload_sha256": api._sha(api._canonical(payload)),
        "max_response_bytes": 2*1024*1024 if endpoint in ("files/read", "backtests/list") else MAX_CONTROL_BYTES,
        "seconds": SECONDS}
    if inventory is not None:
        request["source_inventory_sha256"] = api._sha(api._canonical(inventory))
    return request


def _prepare(*, phase, parent_probe_config_json, helper_source, project_bindings_raw, expected_project_bindings_sha256,
        source_hashes, operation_id, probe_operation_id, git_head, latest_owner_instruction_sha256,
        created_utc, expires_utc, diagnostic_attempt, attempt_id, diagnostic_look_id,
        source_inventory, compile_id=None, compile_evidence=None, fixture=False):
    if (phase not in ("upload", "compile", "build", "launch") or type(source_hashes) is not dict
            or set(source_hashes) != REQUIRED_SOURCES or len(source_hashes) > 48
            or type(operation_id) is not str or re.fullmatch(r"TPR-CMP29-API-CACHE-[A-Z0-9-]{1,60}", operation_id) is None
            or latest_owner_instruction_sha256 != OWNER_SHA256
            or type(diagnostic_attempt) is not int or not 1 <= diagnostic_attempt <= 2**31-1):
        _fail()
    for identity, pattern in ((attempt_id, r"TPR-CACHE-ATTEMPT-[A-Z0-9-]{1,70}"),
            (diagnostic_look_id, r"TPR-CACHE-LOOK-[A-Z0-9-]{1,70}")):
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
    if (type(helper_source) is not bytes or _sha(helper_source) != builder.HELPER_SHA256
            or source_hashes[builder.reader.MODULE] != _sha(helper_source)):
        _fail()
    raw, report_raw = (builder._build_fixture(helper_source=helper_source, operation_id=probe_operation_id, git_head=git_head) if fixture else
        builder.build_cache_probe(parent_probe_config_json=parent_probe_config_json, helper_source=helper_source,
            operation_id=probe_operation_id, git_head=git_head))
    if fixture:
        parent_probe_config_json = builder._wire(builder._fixture_parent()[0]).decode("ascii")
    report, before = _parse(report_raw), _inventory(source_inventory)
    main = {"bytes": len(raw), "sha256": _sha(raw)}
    inventory = {**before, "main.py": main}
    if phase != "upload" and before != inventory:
        _fail()
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
                "backtestName": "TPR-DELIVERY-20261107-OFF-D" + str(diagnostic_attempt)}),
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
    action = {"schema": "tpr-fixed-cache-delivery-action-v1", "phase": phase,
        "parent_probe_config_json": parent_probe_config_json, "helper_source_utf8": helper_source.decode("utf-8"),
        "probe_operation_id": probe_operation_id, "diagnostic_attempt": diagnostic_attempt,
        "attempt_id": attempt_id, "diagnostic_look_id": diagnostic_look_id,
        "latest_owner_instruction_sha256": latest_owner_instruction_sha256, "api_plan": plan,
        "before_inventory": before if phase == "upload" else None, "source_inventory": inventory,
        "compile_id": compile_id, "compile_evidence": evidence_inputs}
    if SECONDS*len(_requests(action)) > (api._clock(expires_utc)-api._clock(created_utc)).total_seconds():
        _fail()
    return api._clone(action)


def prepare_action(*, phase, parent_probe_config_json, helper_source, project_bindings_raw, expected_project_bindings_sha256,
        source_hashes, operation_id, probe_operation_id, git_head, latest_owner_instruction_sha256,
        created_utc, expires_utc, diagnostic_attempt, attempt_id, diagnostic_look_id,
        source_inventory, compile_id=None, compile_evidence=None):
    """Pure preparation; supplied private input must already have a fresh claim."""
    try:
        return _prepare(**locals())
    except Exception:
        _fail()


def _prepare_fixture(**kwargs):
    try:
        if "parent_probe_config_json" in kwargs or "target_sid_text" in kwargs or "fixture" in kwargs:
            _fail()
        return _prepare(**kwargs, parent_probe_config_json="", fixture=True)
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
    fixture = plan["mode"] == "offline-fixture"
    kwargs = {key: action[key] for key in ("phase", "parent_probe_config_json", "probe_operation_id",
        "diagnostic_attempt", "attempt_id", "diagnostic_look_id", "latest_owner_instruction_sha256", "compile_id")}
    if type(action["helper_source_utf8"]) is not str:
        _fail()
    kwargs.update(helper_source=action["helper_source_utf8"].encode("utf-8"),
        project_bindings_raw=plan["project_bindings_json"].encode("ascii"),
        expected_project_bindings_sha256=plan["project_bindings_sha256"], source_hashes=plan["source_hashes"],
        operation_id=plan["operation_id"], git_head=plan["git_head"], created_utc=plan["created_utc"],
        expires_utc=plan["expires_utc"], source_inventory=action["before_inventory"] if action["phase"] == "upload" else action["source_inventory"],
        compile_evidence=action["compile_evidence"] or None, fixture=fixture)
    expected = _prepare(**kwargs)
    if _wire(action) != _wire(expected):
        _fail()
    return expected


def _file_inventory(body):
    if type(body.get("files")) is not list or not 1 <= len(body["files"]) <= 25:
        _fail()
    result = {}
    for row in body["files"]:
        if (type(row) is not dict or type(row.get("name")) is not str or row["name"] in result
                or type(row.get("content")) is not str or "projectId" in row and _native_integer(row["projectId"]) != builder.PROJECT_ID):
            _fail()
        raw = row["content"].encode("utf-8")
        result[row["name"]] = {"bytes": len(raw), "sha256": _sha(raw)}
    return _inventory(result)


def _component_context(context, registry):
    # Check present documented context fields; absence is not invented evidence.
    for key, expected in (("projectId", builder.PROJECT_ID), ("ownerId", registry["owner_id"])):
        if key in context and _native_integer(context[key]) != expected:
            _fail()
    if "organizationId" in context and context["organizationId"] != registry["organization_id"]:
        _fail()
    for key, private_value in (("isPublic", False), ("public", False),
            ("isPrivate", True), ("private", True), ("shared", False)):
        if key in context and context[key] is not private_value:
            _fail()


def _component_collaborators(rows, registry, latest_owner_instruction_sha256):
    """This OFF component uses owner direction plus an exact instance hash.

    Nullable UID or a display name alone proves nothing. This recognition is
    deliberately not independent platform/agent identity attestation, and it
    changes no permission or live authority. Unknown and duplicate actors fail.
    """
    if (latest_owner_instruction_sha256 != OWNER_SHA256 or type(rows) is not list or len(rows) > 2
            or registry["projects"]["OFF"]["project_id"] != builder.PROJECT_ID
            or type(registry["organization_id"]) is not str
            or re.fullmatch("[a-f0-9]{32}", registry["organization_id"]) is None):
        _fail()
    owner, owners, safe, mia = _native_integer(registry["owner_id"]), [], [], 0
    for row in rows:
        if type(row) is not dict or not {"uid", "owner", "permission", "liveControl"} <= set(row):
            _fail()
        if row["uid"] is None:
            public_id = row.get("publicId")
            if (mia or row["owner"] is not False or row.get("name") != "Mia"
                    or row["permission"] != "write" or row["liveControl"] is not True
                    or type(public_id) is not str or re.fullmatch("A-[a-f0-9]{32}", public_id) is None
                    or _sha(public_id.encode("ascii")) != MIA_PUBLIC_ID_SHA256):
                _fail()
            mia = 1
            safe.append({"role": "owner_authorized_mia", "public_id_sha256": MIA_PUBLIC_ID_SHA256,
                "uid_is_null": True, "owner": False, "permission": "write", "liveControl": True})
        else:
            if (owners or _native_integer(row["uid"]) != owner or row["owner"] is not True
                    or row["permission"] not in ("read", "write") or type(row["liveControl"]) is not bool
                    or type(row.get("publicId")) is str and row["publicId"].startswith("A-")):
                _fail()
            owners.append(row)
            safe.append({"role": "owner", "uid": owner, "owner": True,
                "permission": row["permission"], "liveControl": row["liveControl"]})
    stats = {"collaborator_count": len(rows), "nonowner_collaborator_count": mia,
        "recognized_mia_count": mia, "unknown_other_count": 0, "owner_only": mia == 0,
        "collaborators_sha256": _sha(_wire(sorted(safe, key=lambda row: row["role"]))),
        "privacy_basis": MIA_PRIVACY_BASIS if mia else custody.PRIVACY_BASIS,
        "independent_agent_identity_attested": False}
    return stats, owners


def _projection(body, request, registry, *, latest_owner_instruction_sha256):
    if type(body) is not dict or body.get("success") is not True:
        _fail()
    if "projectId" in body and _native_integer(body["projectId"]) != builder.PROJECT_ID:
        _fail()
    identity, payload = request["id"], request["payload"]
    if identity in ("metadata", "collaborators"):
        if body.get("errors") not in (None, []):
            _fail()
        _component_context(body, registry)
        if identity == "metadata":
            rows = body.get("projects")
            if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict or _native_integer(rows[0].get("projectId")) != builder.PROJECT_ID:
                _fail()
            _component_context(rows[0], registry)
            stats, owner_rows = _component_collaborators(rows[0].get("collaborators"), registry, latest_owner_instruction_sha256)
            # Legacy core validation sees owner rows only. Its owner-only counts
            # are replaced below with the UNFILTERED, fully classified actors.
            core_body = {**body, "projects": [{**rows[0], "collaborators": owner_rows}]}
            core = custody._projection(core_body, {"project_id": builder.PROJECT_ID, "phase": identity, "arm": "cap_off"}, registry)
            core_hash = core.pop("normalized_metadata_sha256")
            return {**core, **stats, "owner_core_metadata_sha256": core_hash,
                "normalized_metadata_sha256": _sha(_wire({"owner_core": core_hash, "actual_collaborators": stats}))}
        if body.get("userPermissions") != "write":
            _fail()
        stats, _ = _component_collaborators(body.get("collaborators"), registry, latest_owner_instruction_sha256)
        return {"phase": "collaborators", "project_id": builder.PROJECT_ID, "user_permissions": "write",
            "independent_native_origin_attested": False, **stats}
    if identity == "jobs":
        jobs, count = body.get("backtests"), body.get("count")
        # TPR-CR35-006: a list that disagrees with its own count cannot prove no active job.
        if (type(jobs) is not list or len(jobs) > 1000 or type(count) is evidence.JsonNumber
                and re.fullmatch(r"[0-9]+", count.lexeme) is None or projects._integer(count, 0, 1000) != len(jobs)):
            _fail()
        for row in jobs:
            if (type(row) is not dict or type(row.get("completed")) is not bool or row["completed"] is not True
                    or row.get("status") not in TERMINAL or type(row.get("backtestId")) is not str
                    or re.fullmatch("[a-f0-9]{32}", row["backtestId"]) is None
                    or "projectId" in row and _native_integer(row["projectId"]) != builder.PROJECT_ID):
                _fail()
        if len({row["backtestId"] for row in jobs}) != len(jobs):
            _fail()
        return {"terminal_jobs_observed": len(jobs), "nonterminal_jobs_observed": 0}
    if request["endpoint"] == "files/read":
        inventory = _file_inventory(body)
        digest = api._sha(api._canonical(inventory))
        if digest != request["source_inventory_sha256"]:
            _fail()
        return {"source_inventory": inventory, "source_inventory_sha256": digest}
    if identity in ("compile", "build"):
        compile_id, state = body.get("compileId"), body.get("state")
        api._identity(compile_id)
        if (type(state) is not str or re.fullmatch("[A-Za-z ]{1,40}", state) is None
                or identity == "build" and (compile_id != payload["compileId"] or state != "BuildSuccess")):
            _fail()
        return {"compile_id": compile_id, "compile_state": state}
    if identity == "launch":
        job = body.get("backtest")
        if (type(job) is not dict or type(job.get("backtestId")) is not str
                or re.fullmatch("[a-f0-9]{32}", job["backtestId"]) is None
                or "projectId" in job and _native_integer(job["projectId"]) != builder.PROJECT_ID):
            _fail()
        return {"backtest_id": job["backtestId"]}
    if identity == "write":
        return {"generated_main_acknowledged": True}
    _fail()


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
        for key in ("parent_probe_config_json", "helper_source_utf8", "probe_operation_id", "diagnostic_attempt", "attempt_id", "diagnostic_look_id",
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
        if (result.get("schema") != "tpr-fixed-cache-delivery-action-result-v1" or result.get("status") != "completed"
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


def _read_proof(root, descriptor):
    """Anchored nonblocking regular-file read; no legacy special-file open."""
    directory = leaf = None
    def stamp(value):
        return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    try:
        with ops.wall_deadline(SECONDS):
            directory = os.open(root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            parent = os.fstat(directory)
            ops._custody(parent, True)
            leaf = os.open(descriptor["name"], os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=directory)
            before = os.fstat(leaf)
            ops._custody(before)
            if not stat.S_ISREG(before.st_mode) or before.st_size != descriptor["bytes"] or before.st_nlink != 1:
                _fail()
            if stamp(os.stat(descriptor["name"], dir_fd=directory, follow_symlinks=False)) != stamp(before):
                _fail()
            chunks, remaining = [], descriptor["bytes"]
            while remaining:
                part = os.read(leaf, min(remaining, 131072))
                if not part:
                    _fail()
                chunks.append(part)
                remaining -= len(part)
            raw = b"".join(chunks)
            named_root = os.stat(root, follow_symlinks=False)
            if ((named_root.st_dev, named_root.st_ino) != (parent.st_dev, parent.st_ino)
                    or stamp(os.fstat(leaf)) != stamp(before)
                    or stamp(os.stat(descriptor["name"], dir_fd=directory, follow_symlinks=False)) != stamp(before)
                    or _sha(raw) != descriptor["sha256"]):
                _fail()
            return raw
    finally:
        if leaf is not None: os.close(leaf)
        if directory is not None: os.close(directory)


def _reservation_names(action):
    candidate = _wire({"project_id": builder.PROJECT_ID, "probe_operation_id": action["probe_operation_id"],
        "diagnostic_attempt": action["diagnostic_attempt"]})
    return ["attempt-"+_sha(action["attempt_id"].encode("ascii"))+".launch.spent.json",
        "look-"+_sha(action["diagnostic_look_id"].encode("ascii"))+".launch.spent.json",
        "candidate-"+_sha(candidate)+".launch.spent.json"]


def _guard(plan):
    api._guard(plan)
    if (Path(__file__) != api.LANE/MODULE or Path(builder.__file__) != api.LANE/builder.MODULE
            or Path(builder.prior.__file__) != api.LANE/builder.prior.MODULE
            or Path(builder.base.__file__) != api.LANE/builder.base.MODULE
            or Path(builder.reader.__file__) != api.LANE/builder.reader.MODULE
            or Path(custody.__file__) != api.LANE/custody.MODULE
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
    result = {"schema": "tpr-fixed-cache-delivery-action-result-v1", "phase": action["phase"],
        "operation_id": operation, "action_sha256": _sha(frozen), "git_head": plan["git_head"],
        "project_id": builder.PROJECT_ID, "candidate_config_sha256": plan["candidate_config_sha256"],
        "status": "failed_or_uncertain", "requests": [], "transport_calls_attempted": 0,
        "compile_requests_attempted": 0, "actual_new_diagnostic_jobs": 0, "observed_job_ids": [],
        "private_reads_attempted": 0, "private_bytes_read": 0, "dependency_claims": [], "launch_reservations": [],
        "action_claim_published": None,
        "response_bytes": 0, "receipt_published": False, "lock_cleanup_complete": False,
        "automatic_retry": False, "financial_attempts_created": 0, "financial_outcome_looks": 0,
        "input_canary_only": True, **{key: False for key in builder.FLAGS}}
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
            # TPR-CR35-004: retain the response before any further source/clock check. A
            # check here would lose a launched job's identity; the next check still stops.
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
            # TPR-CR35-005: an unpublished receipt never reports completed.
            result["status"] = "cancelled" if isinstance(stop, KeyboardInterrupt) else "failed_or_uncertain"
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
