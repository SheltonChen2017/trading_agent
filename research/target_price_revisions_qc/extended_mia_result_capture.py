"""Fresh, read-only EXT26 OFF Mia source inspection and native evidence.

Never reserves, compiles, writes cloud source, launches, or exports ObjectStore.
An externally recorded GUI ledger is declared Mia provenance, not authenticated
compiled-source proof. Exact API requests prove their own scope only. Every
scope/request is spent before private bodies or credentials; failures survive.
"""
from __future__ import annotations

import argparse
import ast
import base64
from datetime import datetime, timedelta, timezone
import difflib
import hashlib
import http.client
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import time

from . import extended_mia_capture as capture
from . import extended_native as native

e, ops, files = capture.e, capture.ops, capture.files
LANE, BRANCH, PRIVATE_ROOT = capture.LANE, capture.BRANCH, capture.PRIVATE_ROOT
PROJECT, CANDIDATE = capture.PROJECT, capture.CANDIDATE
MODULE = capture.PREFIX + "extended_mia_result_capture.py"
SOURCE_PATHS = (*capture.SOURCE_PATHS, MODULE, capture.PREFIX + "extended_native.py",
                capture.PREFIX + "extended_metrics.py")
MAX_PRIVATE, MAX_RECEIPT, MAX_HELPER = 32 * 1024 * 1024, 64 * 1024, 16384
MAX_TOTAL, MAX_SECONDS, REQUEST_SECONDS = 64 * 1024 * 1024, 600, 30
MAX_PAGES, PAGE_SIZE = 128, 99
PRIOR_JOBS = frozenset(("34e0636f373c5ed9ee97387335b52454", "f79d3ff02644ec81f20da5cc6ca7440a", "d7c76b7c4936c814f125a2b9a8cc2896"))
REPAIR = "audit_key_recovery.py"
NOTEBOOK_SHA256 = "af27200522531d426185f4daa25d23610c164134e3ab7fdf38919616d0d5b344"
ACTOR = "quantconnect-built-in-mia"
READ_LIMITS = {"backtests/read": 2 * 1024 * 1024, "backtests/read/log": 1024 * 1024,
               "backtests/chart/read": 2 * 1024 * 1024, "backtests/orders/read": 1024 * 1024}
POST_KEYS = frozenset(("operation_id", "receipt_bytes", "receipt_sha256", "sources_bytes", "sources_sha256",
                       "diff_bytes", "diff_sha256"))
MIA_KEYS = frozenset(("actor", "operation_id", "compile_id", "backtest_id", "source_hashes", "source_post_operation",
    "source_post_receipt_sha256", "baseline_operation", "baseline_receipt_sha256", "legacy_attempt",
    "codex_attempts_consumed", "observed_looks_before", "look_ordinal", "mia_look_sha256"))
ARGS = ("action", "operation_id", "git_head", "source_hashes", "owner_instruction_sha256", "created_utc",
        "expires_utc", "post_reference", "mia", "ui_ledger", "mode")
Refusal = e.EvidenceError


def _fail():
    raise Refusal("bounded EXT26 Mia read-only evidence refused; no automatic retry")


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _guard(head):
    capture._guard(head)
    for actual, relative in ((Path(__file__), MODULE), (Path(native.__file__), capture.PREFIX + "extended_native.py"),
            (Path(native.metrics.__file__), capture.PREFIX + "extended_metrics.py")):
        if actual != LANE / relative or actual.resolve() != actual: _fail()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE,
            capture_output=True, timeout=5).returncode: _fail()


def _sources(head):
    result = capture._sources(head)
    for name in SOURCE_PATHS[len(capture.SOURCE_PATHS):]:
        _guard(head)
        raw = subprocess.run(["git", "show", head + ":" + name], cwd=LANE,
            capture_output=True, timeout=5, check=True).stdout
        directory = files._directory((LANE / name).parent, private=False)
        try:
            _guard(head)
            result[name] = files._read(directory, Path(name).name, expected_size=len(raw), expected_sha256=_sha(raw),
                remaining=capture.MAX_RESPONSE, private=False)
        finally: os.close(directory)
    _guard(head)
    return result


def _operation(value):
    if type(value) is not str or re.fullmatch(r"TPR-EXT26-MIA-RESULT-[A-Za-z0-9-]{1,50}", value) is None: _fail()
    return value


def _descriptor(value, maximum):
    e._closed(value, {"bytes", "sha256"})
    size = capture._integer(value["bytes"], maximum)
    if not size: _fail()
    return {"bytes": size, "sha256": e._hash(value["sha256"])}


def _post(value):
    e._closed(value, POST_KEYS)
    capture._operation(value["operation_id"], "post-mia-source")
    result = dict(value)
    for role, maximum in (("receipt", MAX_RECEIPT), ("sources", capture.MAX_ARCHIVE), ("diff", capture.MAX_ARCHIVE)):
        bound = _descriptor({"bytes": value[role + "_bytes"], "sha256": value[role + "_sha256"]}, maximum)
        result[role + "_bytes"] = bound["bytes"]
    if sum(result[key + "_bytes"] for key in ("receipt", "sources", "diff")) > MAX_PRIVATE: _fail()
    return result


def _mia(value, post):
    e._closed(value, MIA_KEYS)
    if (value["actor"] != ACTOR or type(value["operation_id"]) is not str
            or re.fullmatch(r"TPR-EXT26-MIA-RECOVERY-[A-Za-z0-9-]{1,50}", value["operation_id"]) is None
            or value["source_post_operation"] != post["operation_id"]
            or value["source_post_receipt_sha256"] != post["receipt_sha256"]): _fail()
    for key, expected in (("legacy_attempt", 3), ("codex_attempts_consumed", 3), ("observed_looks_before", 19), ("look_ordinal", 20)):
        if type(value[key]) is not int or value[key] != expected: _fail()
    e._id(value["compile_id"]); e._id(value["backtest_id"])
    if value["backtest_id"] in PRIOR_JOBS: _fail()
    capture._operation(value["baseline_operation"], "baseline-source")
    for key in ("baseline_receipt_sha256", "mia_look_sha256"): e._hash(value[key])
    hashes = value["source_hashes"]
    if type(hashes) is not dict or not capture.EXPECTED_FILES | {REPAIR} <= set(hashes) or not len(hashes) <= capture.MAX_FILES: _fail()
    for name, identity in hashes.items():
        if type(name) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", name) is None: _fail()
        e._hash(identity)
    return {**value, "source_hashes": dict(hashes)}


def _plan(*, action, operation_id, git_head, source_hashes, owner_instruction_sha256, created_utc, expires_utc,
          post_reference, mia=None, ui_ledger=None, mode="production"):
    if action not in {"source-inspect", "status", "collect-native"} or mode not in {"production", "offline-fixture"}: _fail()
    _operation(operation_id); e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS): _fail()
    for identity in source_hashes.values(): e._hash(identity)
    if (source_hashes[capture.BUNDLE] != capture.BUNDLE_SHA256
            or source_hashes[capture.PREFIX + "extended_study_freeze.json"] != e.FREEZE_SHA256
            or source_hashes[capture.PREFIX + "extended_calendar.json"] != ops.CALENDAR_SHA256): _fail()
    duration = capture._clock(expires_utc) - capture._clock(created_utc)
    if not timedelta(0) < duration <= timedelta(hours=4): _fail()
    post = _post(post_reference)
    if action == "source-inspect":
        if mia is not None or ui_ledger is not None: _fail()
        limit, binding, ledger = 30, None, None
    else:
        binding, ledger, limit = _mia(mia, post), _descriptor(ui_ledger, MAX_RECEIPT), MAX_SECONDS
    return {"schema": "tpr-ext26-mia-result-plan-v1", "action": action, "operation_id": operation_id,
        "project_id": PROJECT, "candidate_id": CANDIDATE, "git_head": git_head, "source_hashes": dict(source_hashes),
        "owner_instruction_sha256": owner_instruction_sha256, "created_utc": created_utc, "expires_utc": expires_utc,
        "post_reference": post, "mia": binding, "ui_ledger": ledger, "mode": mode, "max_seconds": limit,
        "max_received_bytes": MAX_TOTAL, "request_seconds": REQUEST_SECONDS, "max_order_pages": MAX_PAGES,
        "read_endpoints": sorted(READ_LIMITS), "new_codex_attempts": 0, "new_looks": 0, "automatic_retry": False,
        "object_export": False, "compiled_source_proven": False, "strategy_accepted": False, "canonical_admission": False}


def prepare_plan(**arguments):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    return _plan(git_head=head, source_hashes={name: _sha(raw) for name, raw in sources.items()}, **arguments)


def _repair_source(text):
    """Narrow source disclosure grammar, not economic acceptance or secret proof."""
    if type(text) is not str or not 0 < len(text.encode()) <= MAX_HELPER: _fail()
    try: tree = ast.parse(text)
    except (SyntaxError, RecursionError): _fail()
    nodes = list(ast.walk(tree))
    if len(nodes) > 1500: _fail()
    permitted_imports = {"CompressedAuditStore", "canonical", "encode_gzip", "decode_gzip", "sha256", "MAX_METADATA", "_fail", "_keys", "_hash", "_positive"}
    classes, bases, exports, constants = [], [], [], set()
    def constant(node):
        if isinstance(node, ast.Call):
            if (not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name)
                    or (node.func.value.id, node.func.attr) != ("re", "compile") or not 1 <= len(node.args) <= 2
                    or node.keywords or not isinstance(node.args[0], ast.Constant)
                    or type(node.args[0].value) is not str or len(node.args[0].value.encode()) > 512): _fail()
            if len(node.args) == 2 and (not isinstance(node.args[1], ast.Attribute) or not isinstance(node.args[1].value, ast.Name)
                    or node.args[1].value.id != "re" or node.args[1].attr not in {"ASCII", "IGNORECASE"}): _fail()
            return
        try: value = ast.literal_eval(node)
        except (ValueError, TypeError, SyntaxError, RecursionError): _fail()
        def bounded(item, depth=0):
            if depth > 4: _fail()
            if type(item) is str:
                if len(item.encode()) > 512: _fail()
            elif type(item) is int:
                if not 0 <= item <= MAX_TOTAL: _fail()
            elif type(item) is bool: pass
            elif type(item) is tuple and len(item) <= 16:
                for child in item: bounded(child, depth + 1)
            else: _fail()
        bounded(value)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and type(node.value.value) is str: continue
        if (isinstance(node, ast.ImportFrom) and node.module == "__future__" and node.level == 0
                and [(alias.name, alias.asname) for alias in node.names] == [("annotations", None)]): continue
        if isinstance(node, ast.ImportFrom) and node.module == "extended_compressed_store" and node.level == 0:
            for alias in node.names:
                if alias.name not in permitted_imports: _fail()
                if alias.name == "CompressedAuditStore":
                    if alias.asname is not None and re.fullmatch(r"_?[A-Za-z][A-Za-z0-9_]{0,60}", alias.asname) is None: _fail()
                    bases.append(alias.asname or alias.name)
                elif alias.asname is not None: _fail()
        elif isinstance(node, ast.Import) and [(alias.name, alias.asname) for alias in node.names] == [("re", None)]: pass
        elif isinstance(node, ast.ClassDef): classes.append(node)
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "CompressedAuditStore" and isinstance(node.value, ast.Name)
                and node.value.id == "AuditKeyRecoveryStore"): exports.append(node)
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and re.fullmatch(r"_?[A-Z][A-Z0-9_]{0,60}", node.targets[0].id) is not None):
            if node.targets[0].id in constants or len(constants) >= 16: _fail()
            # These obvious disclosure channels refuse; this name check is NOT
            # proof that an innocently named literal contains no covert data.
            if any(word in node.targets[0].id for word in ("SECRET", "TOKEN", "PASSWORD", "API_KEY", "CREDENTIAL", "AUTHORIZATION", "LICENSED")): _fail()
            constant(node.value); constants.add(node.targets[0].id)
        else: _fail()
    if len(classes) != 1 or len(bases) != 1 or len(exports) > 1: _fail()
    cls = classes[0]
    if (cls.name not in {"AuditKeyRecoveryStore", "CompressedAuditStore"} or len(cls.bases) != 1 or not isinstance(cls.bases[0], ast.Name)
            or cls.bases[0].id != bases[0] or cls.decorator_list or cls.keywords
            or exports and (cls.name != "AuditKeyRecoveryStore" or tree.body.index(exports[0]) < tree.body.index(cls))): _fail()
    methods = []
    physical_helpers = {"_physical", "_validate_write_key", "_validate_full_key", "_sidecar_empty",
                        "_build_physical_mapping", "_collision_sweep", "_sweep_keys"}
    permitted_methods = {"__init__", "_key", "contains_key", "_sidecar"} | physical_helpers
    for node in cls.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and type(node.value.value) is str: continue
        if not isinstance(node, ast.FunctionDef) or node.name not in permitted_methods: _fail()
        if any(not isinstance(decorator, ast.Name) or decorator.id != "staticmethod" or node.name not in physical_helpers
                for decorator in node.decorator_list): _fail()
        if any(not isinstance(default, ast.Constant) for default in node.args.defaults + [value for value in node.args.kw_defaults if value is not None]): _fail()
        methods.append(node.name)
    if len(methods) != len(set(methods)) or not {"_key", "_sidecar"} <= set(methods): _fail()
    forbidden = (ast.Import, ast.ImportFrom, ast.AsyncFunctionDef, ast.Lambda, ast.Global, ast.Nonlocal,
                 ast.With, ast.AsyncWith, ast.Await, ast.Yield, ast.YieldFrom, ast.Delete)
    denied_names = {"eval", "exec", "open", "compile", "getattr", "setattr", "__import__", "globals", "locals", "input", "print"}
    permitted_calls = {"fullmatch", "contains_key", "save_bytes", "read_bytes", "_fail", "_key", "_physical",
        "_validate_write_key", "_sidecar_empty", "canonical", "encode_gzip", "decode_gzip", "sha256",
        "len", "type", "ValueError", "str", "bool", "super", "__init__", "replace", "startswith", "endswith",
        "int", "count", "group", "match", "isinstance", "dict", "_keys", "_hash", "_positive",
        "_validate_full_key", "_build_physical_mapping", "_collision_sweep", "_sweep_keys",
        "get", "values", "items", "keys", "set", "range", "any", "all", "sorted", "tuple"}
    for node in ast.walk(cls):
        if isinstance(node, forbidden): _fail()
        if isinstance(node, ast.Name) and (node.id in denied_names or node.id.startswith("__") and node.id != "__init__"): _fail()
        if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr != "__init__": _fail()
        if isinstance(node, ast.Constant) and type(node.value) is str and len(node.value.encode()) > 512: _fail()
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
            if name not in permitted_calls: _fail()
            if (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Attribute)
                    and isinstance(node.func.value.value, ast.Name) and node.func.value.value.id == "self"
                    and node.func.value.attr == "native" and name not in {"contains_key", "read_bytes", "save_bytes"}): _fail()
    return text


def _source_inspect(plan, sources, directory, check, report):
    ref = plan["post_reference"]; operation = ref["operation_id"]
    data = {}
    for role, suffix in (("receipt", ".result.json"), ("sources", ".read2.sources.json"), ("diff", ".diff.json")):
        check(); report["private_read_attempts"] += 1
        raw = files._read(directory, operation + suffix, expected_size=ref[role + "_bytes"],
            expected_sha256=ref[role + "_sha256"], remaining=MAX_PRIVATE - report["private_read_bytes"], private=True)
        report["private_read_bytes"] += len(raw); data[role] = e.parse_json(raw)
    receipt, archive, delta = data["receipt"], data["sources"], data["diff"]
    if (receipt.get("schema") != "tpr-ext26-mia-source-receipt-v1" or receipt.get("operation_id") != operation
            or receipt.get("action") != "post-mia-source" or receipt.get("status") != "COMPLETED"
            or receipt.get("stable_source_inventory") is not True or receipt.get("scope_spent") is not True
            or capture._integer(receipt.get("project_id"), 2**31 - 1) != PROJECT or receipt.get("candidate_id") != CANDIDATE
            or receipt.get("source_hashes") != {name: _sha(sources[name]) for name in capture.SOURCE_PATHS}
            or receipt.get("complete_private_diff") != {"name": operation + ".diff.json", "bytes": e.JsonNumber(str(ref["diff_bytes"])), "sha256": ref["diff_sha256"]}): _fail()
    ended = capture._clock(receipt["ended_utc"])
    if not capture._clock(plan["created_utc"]) - timedelta(hours=4) <= ended <= capture._clock(plan["created_utc"]): _fail()
    e._closed(archive, {"schema", "operation_id", "project_id", "request_index", "files"})
    if (archive["schema"] != "tpr-ext26-mia-all-source-v1" or archive["operation_id"] != operation
            or capture._integer(archive["project_id"], 2**31 - 1) != PROJECT
            or capture._integer(archive["request_index"], 2) != 2): _fail()
    current = archive["files"]; inventory = capture._inventory(current)
    if e.canonical(capture._public_inventory(inventory)) != e.canonical(receipt["inventory"]): _fail()
    archives = receipt.get("source_archives")
    if type(archives) is not list or len(archives) != 2 or archives[-1] != {
            "name": operation + ".read2.sources.json", "bytes": e.JsonNumber(str(ref["sources_bytes"])), "sha256": ref["sources_sha256"]}: _fail()
    e._closed(delta, {"schema", "changes", "all_changed_file_bytes_retained", "diff_format", "source_executed", "economics_accepted"})
    if (delta["schema"] != "tpr-ext26-mia-complete-source-diff-v1" or delta["all_changed_file_bytes_retained"] is not True
            or delta["diff_format"] != "complete-whole-file-before-after-v1" or delta["source_executed"] is not False
            or delta["economics_accepted"] is not False or type(delta["changes"]) is not list or len(delta["changes"]) != 2): _fail()
    before = dict(current)
    seen = set()
    for row in delta["changes"]:
        e._closed(row, {"name", "kind", "before", "after", "before_identity", "after_identity"})
        name = row["name"]
        if name in seen or name not in {"main.py", REPAIR} or name not in current or current[name] != row["after"]: _fail()
        seen.add(name)
        if e.canonical(row["after_identity"]) != e.canonical(inventory[name]): _fail()
        if name == REPAIR:
            if row["kind"] != "added" or row["before"] is not None or row["before_identity"] is not None: _fail()
            before.pop(name)
        else:
            if row["kind"] != "changed" or type(row["before"]) is not str: _fail()
            if e.canonical(row["before_identity"]) != e.canonical(capture._inventory({name: row["before"]})[name]): _fail()
            before[name] = row["before"]
    if seen != {"main.py", REPAIR}: _fail()
    changes, expected_diff = capture._diff(before, current)
    if e.canonical(delta) != expected_diff or e.canonical(changes) != e.canonical(receipt["changes"]): _fail()
    frozen = next(row["files"] for row in e.parse_json(sources[capture.BUNDLE])["candidates"] if row["candidate_id"] == CANDIDATE)
    if (set(before) != capture.EXPECTED_FILES | {"research.ipynb"}
            or any(before[name] != frozen[name] for name in capture.EXPECTED_FILES)
            or _sha(before["research.ipynb"].encode()) != NOTEBOOK_SHA256
            or set(current) != set(before) | {REPAIR}): _fail()
    old_import = "from extended_compressed_store import CompressedInputStore, CompressedAuditStore"
    candidates = (
        "from extended_compressed_store import CompressedInputStore\nfrom audit_key_recovery import AuditKeyRecoveryStore as CompressedAuditStore",
        "from extended_compressed_store import CompressedInputStore\nfrom audit_key_recovery import CompressedAuditStore")
    old = before["main.py"]
    matched = [replacement for replacement in candidates if current["main.py"] == old.replace(old_import, replacement, 1)]
    if old.count(old_import) != 1 or len(matched) != 1: _fail()
    new_import = matched[0]
    code = _repair_source(current[REPAIR])
    repair_tree = ast.parse(code)
    exported = {node.name for node in repair_tree.body if isinstance(node, ast.ClassDef)}
    if any(isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "CompressedAuditStore" and isinstance(node.value, ast.Name)
            and node.value.id == "AuditKeyRecoveryStore" for node in repair_tree.body): exported.add("CompressedAuditStore")
    imported = "AuditKeyRecoveryStore" if "AuditKeyRecoveryStore as" in new_import else "CompressedAuditStore"
    if imported not in exported: _fail()
    report.update(source_inspection={"all_file_inventory_verified": True, "complete_before_after_diff_verified": True,
        "original_writer_preserved": True, "other_modules_and_notebook_unchanged": True, "helper_sha256": _sha(code.encode()),
        "helper_bytes": len(code.encode()), "captured_helper_descriptor_verified": True,
        "main_import_only_diff": "\n".join(difflib.unified_diff([old_import], new_import.splitlines(), fromfile="main.py.before", tofile="main.py.after", lineterm="")),
        "permitted_repair_source": code, "source_read_only": True, "source_executed": False,
        "economics_accepted": False, "general_secret_or_covert_data_absence_proven": False})


def _request_allowed(plan, endpoint, payload):
    if plan.get("action") not in {"status", "collect-native"} or endpoint not in READ_LIMITS or type(payload) is not dict: _fail()
    base = {"projectId": PROJECT, "backtestId": plan["mia"]["backtest_id"]}
    if endpoint == "backtests/read": expected = base
    elif endpoint == "backtests/read/log":
        if payload.get("query") not in {"EXT26_SUMMARY", "EXT26_EVIDENCE_INDEX"}: _fail()
        expected = {**base, "start": 0, "end": 100, "query": payload["query"]}
    elif endpoint == "backtests/chart/read":
        if payload.get("name") not in ops.CHARTS: _fail()
        expected = {**base, "name": payload["name"], "count": ops.CHART_COUNT, "start": ops.CHART_START, "end": ops.CHART_END}
    else:
        start = payload.get("start")
        if type(start) is not int or not 0 <= start < MAX_PAGES * PAGE_SIZE or start % PAGE_SIZE: _fail()
        expected = {**base, "start": start, "end": start + PAGE_SIZE}
    if payload != expected or plan["action"] == "status" and endpoint != "backtests/read": _fail()


def _native_request(plan, endpoint, payload, seconds, claim):
    _request_allowed(plan, endpoint, payload)
    if type(seconds) not in (int, float) or not 0 < seconds <= REQUEST_SECONDS: _fail()
    # The native signer independently checks freshly durable own claims before
    # reading credentials. Fixture transports never enter this production path.
    if plan.get("mode") != "production" or e.canonical(plan) != e.canonical(_plan(**{key: plan[key] for key in ARGS})): _fail()
    bound = _descriptor(claim, MAX_RECEIPT) if type(claim) is dict and set(claim) == {"bytes", "sha256"} else None
    if bound is None: _fail()
    _guard(plan["git_head"])
    current = _now()
    if not capture._clock(plan["created_utc"]) <= current < capture._clock(plan["expires_utc"]): _fail()
    directory = files._directory(PRIVATE_ROOT, private=True)
    try:
        header = e.canonical(plan)
        files._read(directory, plan["operation_id"] + ".claim.spent.json", expected_size=len(header),
            expected_sha256=_sha(header), remaining=MAX_RECEIPT, private=True)
        request = e.canonical({"endpoint": endpoint, "payload": payload, "plan_sha256": _sha(header)})
        if bound != {"bytes": len(request), "sha256": _sha(request)}: _fail()
        # Fixed endpoint/payload, not a caller-supplied path: request identity
        # determines its immutable name, irrespective of the controller index.
        files._read(directory, plan["operation_id"] + ".request." + _sha(request) + ".spent.json",
            expected_size=bound["bytes"], expected_sha256=bound["sha256"], remaining=MAX_RECEIPT, private=True)
    finally: os.close(directory)
    connection = None
    with ops.wall_deadline(seconds):
        user, token = ops.credential(); stamp = str(int(time.time()))
        signed = _sha((token + ":" + stamp).encode())
        authorization = base64.b64encode((user + ":" + signed).encode()).decode()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); context.keylog_filename = None
        context.check_hostname, context.verify_mode = True, ssl.CERT_REQUIRED; context.load_default_certs()
        try:
            connection = http.client.HTTPSConnection("www.quantconnect.com", timeout=seconds, context=context)
            connection.request("POST", "/api/v2/" + endpoint, body=e.canonical(payload), headers={
                "Authorization": "Basic " + authorization, "Timestamp": stamp, "Content-Type": "application/json"})
            response = connection.getresponse()
            return response.read(READ_LIMITS[endpoint] + 1), response.status, token
        finally:
            if connection is not None: connection.close()


def _terminal(response, mia):
    if response.get("success") is not True or type(response.get("backtest")) is not dict: _fail()
    row = response["backtest"]
    if row.get("backtestId") != mia["backtest_id"]: _fail()
    ops._returned_identity(response, PROJECT, mia["backtest_id"])
    if "compileId" in row and row["compileId"] != mia["compile_id"]: _fail()
    error = row.get("error")
    if error is not None and (type(error) is not str or not error): _fail()
    status = row.get("status")
    if type(status) is not str or len(status) > 80: _fail()
    terminal = row.get("completed") is True and status in {"Completed", "Completed.", "Runtime Error", "Error", "Stopped", "Cancelled"}
    if terminal:
        if "error" not in row: _fail()
        if status in {"Runtime Error", "Error"} and error is None: _fail()
        if status in {"Completed", "Completed."} and (error is not None or type(row.get("progress")) is not e.JsonNumber or row["progress"].fraction() != 1): _fail()
    return {"terminal": terminal, "completed_flag": row.get("completed") is True,
        "status": status if status in {"Completed", "Completed.", "Runtime Error", "Error", "Stopped", "Cancelled", "In Progress...", "Running"} else "unrecognized_nonterminal",
        "error_present": error is not None, "error_bytes": len(error.encode()) if error else 0,
        "error_sha256": _sha(error.encode()) if error else None, "compile_id_returned_and_matching": "compileId" in row}


def _execute(plan, sources, root, *, guard, clock, monotonic, transport):
    if type(plan) is not dict or e.canonical(plan) != e.canonical(_plan(**{key: plan[key] for key in ARGS})): _fail()
    if (plan["mode"] == "production" and (root != PRIVATE_ROOT or guard is not _guard or clock is not _now
            or monotonic is not time.monotonic or transport is not _native_request)
            or plan["mode"] == "offline-fixture" and (root == PRIVATE_ROOT or root.is_relative_to(LANE) or transport is _native_request)): _fail()
    started = monotonic()
    def check():
        guard(plan["git_head"]); current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0)
                or not capture._clock(plan["created_utc"]) <= current < capture._clock(plan["expires_utc"])
                or not 0 <= monotonic() - started < plan["max_seconds"]
                or {name: _sha(raw) for name, raw in sources.items()} != plan["source_hashes"]): _fail()
    check(); directory = files._directory(root, private=True); lock = None
    operation = plan["operation_id"]
    try:
        check(); capture._publish(directory, operation + ".claim.spent.json", e.canonical(plan))
        report = {"schema": "tpr-ext26-mia-result-receipt-v1", "operation_id": operation, "action": plan["action"],
            "project_id": PROJECT, "candidate_id": CANDIDATE, "git_head": plan["git_head"], "source_hashes": plan["source_hashes"],
            "plan_sha256": _sha(e.canonical(plan)), "owner_instruction_sha256": plan["owner_instruction_sha256"],
            "status": "FAILED_OR_UNCERTAIN", "scope_spent": True, "private_read_attempts": 0, "private_read_bytes": 0,
            "request_attempts": 0, "received_bytes": 0, "failed_response_bytes_unknown": False, "requests": [],
            "source_inspection": None, "terminal": None, "native_census": None,
            "declared_gui_mia_provenance_verified": False, "authenticated_api_request_scope": False,
            "compiled_source_proven": False, "new_codex_attempts": 0, "codex_attempts_consumed": 3,
            "new_looks": 0, "mia_look_counted_externally": 20 if plan["mia"] else None, "automatic_retry": False,
            "object_export": False, "private_journal_replay_verified": False, "accepted_metrics": None,
            "strategy_accepted": False, "canonical_admission": False, "trading": False}
        try:
            check(); lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600: _fail()
            check(); capture._publish(directory, operation + ".access.json", e.canonical({"plan_sha256": report["plan_sha256"],
                "created_utc": plan["created_utc"], "expires_utc": plan["expires_utc"], "read_only": True}))
            if plan["action"] == "source-inspect":
                _source_inspect(plan, sources, directory, check, report)
            else:
                bound = plan["ui_ledger"]; check(); report["private_read_attempts"] += 1
                raw = files._read(directory, plan["mia"]["operation_id"] + ".ui-ledger.json", expected_size=bound["bytes"],
                    expected_sha256=bound["sha256"], remaining=MAX_RECEIPT, private=True)
                report["private_read_bytes"] += len(raw)
                expected = {"schema": "tpr-ext26-mia-ui-ledger-v1", "project_id": PROJECT, "candidate_id": CANDIDATE,
                    "mia": plan["mia"], "launch_via_mia": True, "compiled_source_proven": False}
                if e.canonical(e.parse_json(raw)) != e.canonical(expected): _fail()
                report["declared_gui_mia_provenance_verified"] = True
                def request(endpoint, payload):
                    check(); _request_allowed(plan, endpoint, payload)
                    if len(e.canonical(payload)) > 1024 or report["request_attempts"] >= 5 + MAX_PAGES: _fail()
                    # Native read uses one excess byte to detect oversized
                    # replies; reserve that refusal byte too, before transport.
                    if READ_LIMITS[endpoint] + 1 > plan["max_received_bytes"] - report["received_bytes"]: _fail()
                    stage = operation + ".read" + f'{report["request_attempts"] + 1:03d}'
                    request_raw = e.canonical({"endpoint": endpoint, "payload": payload, "plan_sha256": report["plan_sha256"]})
                    claim = {"bytes": len(request_raw), "sha256": _sha(request_raw)}
                    capture._publish(directory, stage + ".request.spent.json", request_raw)
                    capture._publish(directory, operation + ".request." + claim["sha256"] + ".spent.json", request_raw)
                    record = {"endpoint": endpoint, "status": "failed_or_unknown", "http_status": None, "bytes": None, "envelope": None}
                    report["requests"].append(record); report["request_attempts"] += 1; report["failed_response_bytes_unknown"] = True
                    check(); seconds = min(REQUEST_SECONDS, plan["max_seconds"] - (monotonic() - started))
                    wire, status, token = transport(plan, endpoint, payload, seconds, claim)
                    if type(wire) is not bytes or not 0 < len(wire) <= READ_LIMITS[endpoint] or report["received_bytes"] + len(wire) > MAX_TOTAL: _fail()
                    report["received_bytes"] += len(wire); report["failed_response_bytes_unknown"] = False
                    if type(status) is not int or not 100 <= status <= 599: _fail()
                    record.update(http_status=status, bytes=len(wire)); check()
                    projection = e.project_wire(wire, credential=token)
                    capture._publish(directory, stage + ".projection.json", e.canonical(projection))
                    if status != 200: _fail()
                    response = projection["projection"]
                    if response.get("success") is not True: _fail()
                    checks = ops._returned_identity(response, PROJECT, plan["mia"]["backtest_id"])
                    envelope = e.canonical({"schema": "tpr-ext26-native-read-envelope-v1", "endpoint": endpoint,
                        "request": payload, "response": response, "returned_identity_checks": checks})
                    record["envelope"] = capture._publish(directory, stage + ".envelope.json", envelope)
                    record["status"] = "succeeded"; report["authenticated_api_request_scope"] = plan["mode"] == "production"
                    capture._publish(directory, stage + ".terminal.json", e.canonical(record))
                    return response, envelope
                base = {"projectId": PROJECT, "backtestId": plan["mia"]["backtest_id"]}
                response, _ = request("backtests/read", base); report["terminal"] = _terminal(response, plan["mia"])
                if plan["action"] == "collect-native" and report["terminal"]["terminal"]:
                    _collect(plan, sources, directory, check, report, request, base)
                elif plan["action"] == "collect-native": report["status"] = "NOT_TERMINAL"
            check()
            if report["status"] != "NOT_TERMINAL": report["status"] = "COMPLETED_CAPTURE"
        except (Exception, KeyboardInterrupt):
            if report["requests"] and report["requests"][-1]["status"] != "succeeded":
                capture._publish(directory, operation + ".read" + f'{report["request_attempts"]:03d}' + ".terminal.json", e.canonical(report["requests"][-1]))
        report["ended_utc"] = clock().isoformat(); raw = e.canonical(report)
        if len(raw) > MAX_RECEIPT: _fail()
        capture._publish(directory, operation + ".result.json", raw)
        return raw
    finally:
        if lock is not None:
            try:
                named, owned = os.stat("controller.lock", dir_fd=directory, follow_symlinks=False), os.fstat(lock)
                if (named.st_dev, named.st_ino) == (owned.st_dev, owned.st_ino): os.unlink("controller.lock", dir_fd=directory)
            except FileNotFoundError: pass
            finally: os.close(lock)
        os.close(directory)


def _collect(plan, sources, directory, check, report, request, base):
    frozen = next(row for row in e.parse_json(sources[capture.BUNDLE])["candidates"] if row["candidate_id"] == CANDIDATE)
    manifest = {"candidate_id": CANDIDATE, "project_id": PROJECT, "arm": "tpr_off",
                "config_sha256": _sha(frozen["config_raw"].encode()), "input_hashes": frozen["input_hashes"]}
    census = {"summary_count": None, "index_count": None, "validated_compact_aggregates": False,
        "account_nav": None, "order_count": None, "order_pages": 0, "orders_missing_fill_observations": None,
        "orders_missing_fee_observations": None, "cost_values": None, "full_journal_exported": False}
    report["native_census"] = census
    counts = []
    for marker in ("EXT26_SUMMARY", "EXT26_EVIDENCE_INDEX"):
        response, _ = request("backtests/read/log", {**base, "start": 0, "end": 100, "query": marker})
        rows = response.get("logs"); count = capture._integer(response.get("length"), 100)
        if type(rows) is not list or len(rows) != count or count > 1: _fail()
        census["summary_count" if marker == "EXT26_SUMMARY" else "index_count"] = count; counts.append(count)
        if count:
            aggregate = ops.compact_aggregate(rows[0], marker, manifest, 3, base["backtestId"])
            check(); capture._publish(directory, plan["operation_id"] + "." + marker + ".aggregate.json", e.canonical(aggregate))
    census["validated_compact_aggregates"] = counts == [1, 1]
    sessions = ops._bundle_calendar(frozen)
    for name in ops.CHARTS:
        response, _ = request("backtests/chart/read", {**base, "name": name, "count": ops.CHART_COUNT, "start": ops.CHART_START, "end": ops.CHART_END})
        if name == "EXT26 Account NAV":
            observed, raw = ops._account_nav_chart(response, sessions); census["account_nav"] = observed
            if raw is not None:
                check(); capture._publish(directory, plan["operation_id"] + ".normalized-nav.json", raw)
    pages, descriptors, total, ids = [], [], None, set()
    for number in range(MAX_PAGES):
        start = number * PAGE_SIZE
        response, envelope = request("backtests/orders/read", {**base, "start": start, "end": start + PAGE_SIZE})
        count = capture._integer(response.get("length"), MAX_PAGES * PAGE_SIZE); rows = response.get("orders")
        if total is not None and count != total or type(rows) is not list or len(rows) != min(PAGE_SIZE, count - start): _fail()
        total = count
        for row in rows:
            identity = e._integer(row.get("id")) if type(row) is dict else None
            if identity is None or identity in ids: _fail()
            ids.add(identity)
        pages.append(envelope); parsed = e.parse_json(envelope)
        descriptors.append({"start": start, "end": start + PAGE_SIZE, "response_projection_sha256": _sha(e.canonical(response)),
            "request_response_envelope_sha256": _sha(envelope), "returned_identity_checks": parsed["returned_identity_checks"]})
        census.update(order_count=len(ids), order_pages=len(pages))
        if (number + 1) * PAGE_SIZE >= total: break
    if len(ids) != total: _fail()
    collection = e.canonical({"schema": "tpr-ext26-order-collection-v1", "candidate_id": CANDIDATE, "attempt": 3,
        "backtest_id": base["backtestId"], "order_count": total, "pages": descriptors, "strategy_accepted": False, "new_looks": 0})
    check(); capture._publish(directory, plan["operation_id"] + ".orders.completed.json", collection)
    normalized = native.normalize_orders(pages, collection, sources[capture.PREFIX + "extended_calendar.json"],
        expected_collection_sha256=_sha(collection), candidate_id=CANDIDATE, project_id=PROJECT, backtest_id=base["backtestId"], attempt=3)
    for number, (rows, observations) in enumerate(zip(normalized.pages, normalized.observations)):
        for kind, raw in (("normalized-orders", rows), ("observed-orders", observations)):
            check(); capture._publish(directory, plan["operation_id"] + "." + kind + f".{number:03d}.json", raw)
    public = e.parse_json(normalized.public)
    for key in ("orders_missing_fill_observations", "orders_missing_fee_observations"): census[key] = public[key]


def _now(): return datetime.now(timezone.utc)


def execute_plan(plan):
    if type(plan) is not dict or plan.get("mode") != "production": _fail()
    sources = _sources(plan["git_head"])
    return _execute(plan, sources, PRIVATE_ROOT, guard=_guard, clock=_now, monotonic=time.monotonic, transport=_native_request)


def execute_fixture(plan, sources, root, *, clock, transport, guard=lambda _: None, monotonic=lambda: 0.0):
    if type(plan) is not dict or plan.get("mode") != "offline-fixture": _fail()
    return _execute(plan, sources, root, guard=guard, clock=clock, monotonic=monotonic, transport=transport)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", required=True); parser.add_argument("--plan-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        raw = args.plan_json.encode()
        if _sha(raw) != e._hash(args.plan_sha256): _fail()
        plan = e.parse_json(raw)
        for key in ("legacy_attempt", "codex_attempts_consumed", "observed_looks_before", "look_ordinal"):
            if plan.get("mia"): plan["mia"][key] = capture._integer(plan["mia"][key], 20)
        for key in ("max_seconds", "max_received_bytes", "request_seconds", "max_order_pages", "new_codex_attempts", "new_looks"):
            plan[key] = capture._integer(plan[key], MAX_TOTAL)
        result = execute_plan(plan); print(result.decode(), end="")
        return 0 if e.parse_json(result)["status"] == "COMPLETED_CAPTURE" else 1
    except (Exception, KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","automatic_retry":false,"raw_text_returned":false}')
        return 1


if __name__ == "__main__": raise SystemExit(main())
