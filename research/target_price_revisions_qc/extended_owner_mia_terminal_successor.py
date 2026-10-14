"""Fresh look30-only terminal diagnosis and independent native components.

The executed original remains immutable. A selective parser validates every
terminal JSON token but retains no statistics, market rows or native error
text. Its larger, prospectively bounded node census diagnoses the original
100k-node boundary; it does not weaken that shared parser. No launch, new look,
attempt reset, source/economics acceptance or Object Store export occurs here.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import time

from . import extended_owner_mia_components as original

e, ops, files, capture, discovery = original.e, original.ops, original.files, original.capture, original.discovery
LANE, PRIVATE_ROOT, PROJECT, CANDIDATE = original.LANE, original.PRIVATE_ROOT, original.PROJECT, original.CANDIDATE
MODULE = capture.PREFIX + "extended_owner_mia_terminal_successor.py"
SOURCE_PATHS = (*original.SOURCE_PATHS, MODULE)
ORIGINAL_SHA256 = "4b1640a9cfdbadc30aa8a0b0e2e7da63170123227891e32d87af5e0f3de435db"
PARENT_NAME = "TPR-EXT26-OWNER-MIA-COMPONENTS-20261013-002.result.json"
PARENT_BYTES = 8851
PARENT_SHA256 = "245641d84e40a69b6320803e1563b6e4099eca09e1aabcbfcc83ecc022be773d"
JOB = "4936632376c0885358493a2694ed239b"
LOOK = 30
MAX_TERMINAL_NODES, MAX_PARSE_SECONDS = 400000, 10
MAX_SECONDS, MAX_REQUESTS = original.MAX_SECONDS, 1 + 2 + original.MAX_PAGES + 2
READ_LIMITS = dict(original.READ_LIMITS)
ARGS = ("operation_id", "git_head", "source_hashes", "owner_instruction_sha256", "created_utc",
        "expires_utc", "parent_reference", "mode")
SELECTED = frozenset(("backtestId", "projectId", "status", "completed", "error", "progress", "created", "snapshotId", "compileId"))
ERROR_MARKERS = {
    "initialization_marker": ("Initialize", "initialize", "initialization"),
    "data_callback_marker": ("OnData", "on_data"),
    "end_callback_marker": ("OnEndOfAlgorithm", "on_end_of_algorithm", "_ext_finish", "EXT26_SUMMARY"),
    "compressed_audit_store_marker": ("CompressedAuditStore", "save_bytes", "LocalObjectStore"),
}
Refusal = e.EvidenceError


def _fail(): raise Refusal("fresh fixed look30 diagnostic refused; no automatic retry")
def _sha(raw): return hashlib.sha256(raw).hexdigest()
def _now(): return datetime.now(timezone.utc)


class ParseRefusal(Refusal):
    """Only a closed enum, never exception text or a private token."""
    CODES = frozenset(("credential_echo_refused", "credential_format_refused", "utf8_refused",
        "syntax_refused", "duplicate_key_refused", "numeric_token_refused", "depth_bound_refused",
        "node_bound_refused", "terminal_shape_refused", "foreign_identity_refused", "unexpected_identity_container_refused"))
    def __init__(self, code):
        if code not in self.CODES: _fail()
        self.code = code
        super().__init__(code)


class SelectiveTerminalParser:
    """Validate all JSON, storing only fixed terminal fields.

    Ignored arrays are scanned rather than materialized. String keys and values
    undergo decoded echo checks, including ignored statistics and parameters.
    Original numeric spelling, depth32 and duplicate-key rules are retained.
    The complete response is never reserialized through the shared100k parser.
    """
    def __init__(self, raw, credential):
        if type(raw) is not bytes or not 0 < len(raw) <= READ_LIMITS["backtests/read"]: _fail()
        if type(credential) is not str or re.fullmatch(r"[!-~]{0,256}", credential) is None:
            raise ParseRefusal("credential_format_refused")
        if credential and credential.encode() in raw: raise ParseRefusal("credential_echo_refused")
        try: self.text = raw.decode("utf-8")
        except UnicodeError: raise ParseRefusal("utf8_refused") from None
        self.credential, self.position, self.nodes = credential, 0, 0
        self.selected, self.backtest_object, self.root_object = {}, False, False
        self.unselected_terminal_fields = 0
        self.composite_selected, self.unexpected_identity_containers = set(), set()

    def _space(self):
        while self.position < len(self.text) and self.text[self.position] in " \t\r\n": self.position += 1

    def _string(self):
        if self.position >= len(self.text) or self.text[self.position] != '"': raise ParseRefusal("syntax_refused")
        try: value, self.position = json.decoder.scanstring(self.text, self.position + 1, True)
        except (ValueError, UnicodeError): raise ParseRefusal("syntax_refused") from None
        if self.credential and self.credential in value: raise ParseRefusal("credential_echo_refused")
        return value

    def _primitive(self, path, value):
        if len(path) == 1 and path[0] in {"success", "projectId", "backtestId"}: self.selected[path[0]] = value
        elif len(path) == 2 and path[0] == "backtest" and path[1] in SELECTED:
            self.selected.setdefault("backtest", {})[path[1]] = value

    def _value(self, path=(), depth=0):
        self.nodes += 1
        if self.nodes > MAX_TERMINAL_NODES: raise ParseRefusal("node_bound_refused")
        if depth > e.MAX_DEPTH: raise ParseRefusal("depth_bound_refused")
        self._space()
        if self.position >= len(self.text): raise ParseRefusal("syntax_refused")
        character = self.text[self.position]
        if path in {("chart",), ("orders",)}: self.unexpected_identity_containers.add(path[0])
        if character in "{[" and (path in {("success",), ("projectId",), ("backtestId",)}
                or len(path) == 2 and path[0] == "backtest" and path[1] in SELECTED):
            self.composite_selected.add(path)
            self._primitive(path, None)
        if character == "{":
            if not path: self.root_object = True
            if path == ("backtest",): self.backtest_object = True; self.selected.setdefault("backtest", {})
            self.position += 1; self._space(); seen = set()
            if self.position < len(self.text) and self.text[self.position] == "}": self.position += 1; return
            while True:
                self._space(); key = self._string()
                if key in seen: raise ParseRefusal("duplicate_key_refused")
                seen.add(key); self._space()
                if self.position >= len(self.text) or self.text[self.position] != ":": raise ParseRefusal("syntax_refused")
                self.position += 1
                if path == ("backtest",) and key not in SELECTED: self.unselected_terminal_fields += 1
                self._value(path + (key,), depth + 1); self._space()
                if self.position < len(self.text) and self.text[self.position] == "}": self.position += 1; return
                if self.position >= len(self.text) or self.text[self.position] != ",": raise ParseRefusal("syntax_refused")
                self.position += 1
        elif character == "[":
            self.position += 1; self._space(); index = 0
            if self.position < len(self.text) and self.text[self.position] == "]": self.position += 1; return
            while True:
                self._value(path + (index,), depth + 1); index += 1; self._space()
                if self.position < len(self.text) and self.text[self.position] == "]": self.position += 1; return
                if self.position >= len(self.text) or self.text[self.position] != ",": raise ParseRefusal("syntax_refused")
                self.position += 1
        elif character == '"': self._primitive(path, self._string())
        else:
            for literal, value in (("true", True), ("false", False), ("null", None)):
                if self.text.startswith(literal, self.position):
                    self.position += len(literal); self._primitive(path, value); return
            match = e.NUMBER.match(self.text, self.position)
            if match is None: raise ParseRefusal("syntax_refused")
            try: value = e.JsonNumber(match.group())
            except e.EvidenceError: raise ParseRefusal("numeric_token_refused") from None
            self.position = match.end(); self._primitive(path, value)

    def parse(self):
        self._value(); self._space()
        if self.position != len(self.text): raise ParseRefusal("syntax_refused")
        if not self.root_object or not self.backtest_object: raise ParseRefusal("terminal_shape_refused")
        return self.selected


def terminal_projection(raw, *, credential):
    parser = SelectiveTerminalParser(raw, credential)
    value = parser.parse()
    if parser.unexpected_identity_containers: raise ParseRefusal("unexpected_identity_container_refused")
    if parser.composite_selected:
        if any(path[-1] in {"projectId", "backtestId"} for path in parser.composite_selected):
            raise ParseRefusal("foreign_identity_refused")
        raise ParseRefusal("terminal_shape_refused")
    if value.get("success") is not True: raise ParseRefusal("terminal_shape_refused")
    row = value.get("backtest")
    try: identity_checks = ops._returned_identity(value, PROJECT, JOB)
    except e.EvidenceError: raise ParseRefusal("foreign_identity_refused") from None
    if type(row) is not dict or row.get("backtestId") != JOB: raise ParseRefusal("terminal_shape_refused")
    native_status = row.get("status")
    if type(native_status) is not str or native_status not in discovery.STATUS | {"RuntimeError"}:
        raise ParseRefusal("terminal_shape_refused")
    if "compileId" in row:
        try: e._id(row["compileId"])
        except e.EvidenceError: raise ParseRefusal("terminal_shape_refused") from None
    if "snapshotId" in row:
        try: capture._integer(row["snapshotId"], 2**31 - 1)
        except e.EvidenceError: raise ParseRefusal("terminal_shape_refused") from None
    if "created" in row:
        if type(row["created"]) is not str or len(row["created"]) > 64:
            raise ParseRefusal("terminal_shape_refused")
        try: datetime.fromisoformat(row["created"].replace("Z", "+00:00"))
        except ValueError: raise ParseRefusal("terminal_shape_refused") from None
    normalized = {**row, "status": "Runtime Error" if native_status == "RuntimeError" else native_status}
    try: terminal = original._terminal({"backtest": normalized}, JOB)
    except (e.EvidenceError, ValueError): raise ParseRefusal("terminal_shape_refused") from None
    error = row.get("error")
    # No raw error, source, statistics, parameters or licensed market rows.
    metadata = {key: row[key] for key in SELECTED - {"error", "status"} if key in row}
    metadata.update(native_status=native_status, terminal=terminal,
        status_adapter="RuntimeError -> Runtime Error" if native_status == "RuntimeError" else None,
        error_present=error is not None,
        error_stage_marker_observations=[name for name, needles in ERROR_MARKERS.items()
            if type(error) is str and any(needle in error for needle in needles)],
        marker_observations_prove_accounting_or_exact_cause=False)
    projection = {"success": True, "backtest": metadata, "returned_identity_checks": identity_checks}
    return {"schema": "tpr-ext26-selective-terminal-projection-v1", "projection": projection,
        "original_wire_sha256": _sha(raw), "original_wire_bytes": len(raw),
        "projection_sha256": _sha(e.canonical(projection)), "json_value_nodes_scanned": parser.nodes,
        "current_response_exceeds_original_100k_node_bound": parser.nodes > e.MAX_NODES,
        "earlier_original_refusal_cause_proven": False,
        "max_selective_nodes": MAX_TERMINAL_NODES, "depth_limit_unchanged": e.MAX_DEPTH,
        "unselected_backtest_fields": parser.unselected_terminal_fields,
        "raw_wire_retained": False, "raw_error_retained": False,
        "statistics_parameters_market_rows_retained": False, "compiled_source_proven": False}


def _guard(head):
    original._guard(head)
    if Path(__file__) != LANE / MODULE or Path(__file__).resolve() != LANE / MODULE: _fail()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE,
            capture_output=True, timeout=5).returncode: _fail()


def _sources(head):
    result = original._sources(head); _guard(head)
    committed = subprocess.run(["git", "show", head + ":" + MODULE], cwd=LANE,
        capture_output=True, timeout=5, check=True).stdout
    directory = files._directory((LANE / MODULE).parent, private=False)
    try:
        result[MODULE] = files._read(directory, Path(MODULE).name, expected_size=len(committed),
            expected_sha256=_sha(committed), remaining=capture.MAX_RESPONSE, private=False)
    finally: os.close(directory)
    _guard(head); return result


def _plan(*, operation_id, git_head, source_hashes, owner_instruction_sha256, created_utc,
          expires_utc, parent_reference, mode="production"):
    if (type(operation_id) is not str or re.fullmatch(r"TPR-EXT26-OWNER-MIA-TERMINAL-[A-Za-z0-9-]{1,50}", operation_id) is None
            or mode not in {"production", "offline-fixture"}): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS): _fail()
    for identity in source_hashes.values(): e._hash(identity)
    if (source_hashes[original.MODULE] != ORIGINAL_SHA256
            or source_hashes[capture.BUNDLE] != capture.BUNDLE_SHA256
            or source_hashes[discovery.LOOK] != discovery.LOOK_SHA256
            or source_hashes[capture.PREFIX + "extended_study_freeze.json"] != e.FREEZE_SHA256
            or source_hashes[capture.PREFIX + "extended_calendar.json"] != ops.CALENDAR_SHA256
            or mode == "production" and source_hashes[original.LEDGER] != original.LEDGER_SHA256): _fail()
    if not timedelta(0) < capture._clock(expires_utc) - capture._clock(created_utc) <= timedelta(hours=1): _fail()
    e._closed(parent_reference, {"name", "bytes", "sha256"})
    ref = {**parent_reference, "bytes": capture._integer(parent_reference["bytes"], original.MAX_RECEIPT)}
    e._hash(ref["sha256"])
    if (ref["name"] != PARENT_NAME or not ref["bytes"]
            or mode == "production" and ref != {"name": PARENT_NAME, "bytes": PARENT_BYTES, "sha256": PARENT_SHA256}): _fail()
    return {"schema": "tpr-ext26-owner-mia-terminal-plan-v1", "operation_id": operation_id,
        "project_id": PROJECT, "declared_candidate_id": CANDIDATE, "study_id": e.STUDY_ID,
        "git_head": git_head, "source_hashes": dict(source_hashes), "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created_utc, "expires_utc": expires_utc, "parent_reference": ref, "mode": mode,
        "backtest_id": JOB, "retrospective_owner_look_ordinal": LOOK, "parent_codex_attempt": 3,
        "freeze_sha256": e.FREEZE_SHA256, "calendar_sha256": ops.CALENDAR_SHA256, "config_sha256": discovery.CONFIG_SHA256,
        "max_requests": MAX_REQUESTS, "read_endpoints": dict(READ_LIMITS), "max_received_bytes": original.MAX_TOTAL,
        "max_private_artifact_bytes": original.MAX_PRIVATE_TOTAL, "max_seconds": MAX_SECONDS,
        "max_selective_terminal_nodes": MAX_TERMINAL_NODES, "max_terminal_parse_seconds": MAX_PARSE_SECONDS,
        "original_collector_source_sha256": ORIGINAL_SHA256,
        "shared_parser_source_sha256": source_hashes[capture.PREFIX + "extended_evidence.py"],
        "original_shared_node_bound": e.MAX_NODES,
        "new_jobs_launched": 0, "new_codex_attempts": 0, "new_looks": 0,
        "retrospective_parent_look29_replayed": False, "scope_reason": "diagnose refused latest look30 terminal, not choose a winner",
        "automatic_retry": False, "object_export": False, "source_read": False,
        "economics_accepted": False, "compiled_source_proven": False, "canonical_admission": False}


def prepare_plan(**arguments):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    plan = _plan(git_head=head, source_hashes={name: _sha(raw) for name, raw in sources.items()}, **arguments)
    raw = e.canonical(plan)
    return {"plan": plan, "plan_json": raw.decode(), "plan_sha256": _sha(raw)}


def _request_allowed(endpoint, payload):
    original._request_allowed({"jobs": [{"backtest_id": JOB}]}, endpoint, payload)


def _access(plan):
    return e.canonical({"plan_sha256": _sha(e.canonical(plan)), "created_utc": plan["created_utc"],
        "expires_utc": plan["expires_utc"], "read_only": True, "project_id": PROJECT,
        "backtest_id": JOB, "look_ordinal": LOOK, "parent_reference": plan["parent_reference"]})


def _native_request(plan, endpoint, payload, seconds, claim):
    _request_allowed(endpoint, payload)
    rebuilt = _plan(**{key: plan[key] for key in ARGS})
    raw_request = e.canonical({"endpoint": endpoint, "payload": payload, "plan_sha256": _sha(e.canonical(plan))})
    if (plan.get("mode") != "production" or e.canonical(plan) != e.canonical(rebuilt)
            or type(seconds) not in (int, float) or not 0 < seconds <= original.REQUEST_SECONDS
            or claim != {"bytes": len(raw_request), "sha256": _sha(raw_request)}): _fail()
    _guard(plan["git_head"])
    if not capture._clock(plan["created_utc"]) <= _now() < capture._clock(plan["expires_utc"]): _fail()
    directory = files._directory(PRIVATE_ROOT, private=True)
    try:
        for name, raw in ((plan["operation_id"] + ".claim.spent.json", e.canonical(plan)),
                (plan["operation_id"] + ".access.json", _access(plan)),
                (plan["operation_id"] + ".request." + _sha(raw_request) + ".spent.json", raw_request)):
            files._read(directory, name, expected_size=len(raw), expected_sha256=_sha(raw),
                remaining=original.MAX_RECEIPT, private=True)
    finally: os.close(directory)
    _guard(plan["git_head"])
    if not capture._clock(plan["created_utc"]) <= _now() < capture._clock(plan["expires_utc"]): _fail()
    connection = None
    with ops.wall_deadline(seconds):
        user, token = ops.credential(); stamp = str(int(time.time()))
        authorization = base64.b64encode((user + ":" + _sha((token + ":" + stamp).encode())).encode()).decode()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); context.keylog_filename = None
        context.check_hostname, context.verify_mode = True, ssl.CERT_REQUIRED; context.load_default_certs()
        try:
            connection = http.client.HTTPSConnection("www.quantconnect.com", timeout=seconds, context=context)
            connection.request("POST", "/api/v2/" + endpoint, body=e.canonical(payload),
                headers={"Authorization": "Basic " + authorization, "Timestamp": stamp, "Content-Type": "application/json"})
            response = connection.getresponse()
            return response.read(READ_LIMITS[endpoint] + 1), response.status, token
        finally:
            if connection is not None: connection.close()


def _parent(raw, plan, sources):
    receipt = e.parse_json(raw); ledger = original._ledger({name: sources[name] for name in original.SOURCE_PATHS}, plan["mode"])
    if (receipt.get("schema") != "tpr-ext26-owner-mia-components-receipt-v1"
            or receipt.get("operation_id") + ".result.json" != PARENT_NAME or receipt.get("status") != "FAILED_OR_UNCERTAIN"
            or receipt.get("scope_spent") is not True or receipt.get("new_jobs_launched") != e.JsonNumber("0")
            or receipt.get("new_codex_attempts") != e.JsonNumber("0") or receipt.get("new_looks") != e.JsonNumber("0")
            or receipt.get("parent_codex_attempt") != e.JsonNumber("3") or receipt.get("project_id") != e.JsonNumber(str(PROJECT))
            or receipt.get("declared_candidate_id") != CANDIDATE or receipt.get("accepted_metrics") is not None
            or receipt.get("compiled_source_proven") is not False or receipt.get("economics_accepted") is not False
            or receipt.get("source_hashes", {}).get(original.MODULE) != ORIGINAL_SHA256
            or ledger.get("owner_instruction_sha256") != plan["owner_instruction_sha256"]): _fail()
    jobs = receipt.get("jobs")
    if (type(jobs) is not list or len(jobs) != 2
            or [capture._integer(row.get("retrospective_owner_look_ordinal"), LOOK) for row in jobs] != [29, 30]
            or jobs[-1].get("backtest_id") != JOB or jobs[-1].get("terminal") is not None): _fail()
    requests = receipt.get("requests")
    if (type(requests) is not list or len(requests) != 7
            or requests[-1].get("backtest_id") != JOB or requests[-1].get("endpoint") != "backtests/read"
            or requests[-1].get("status") != "failed_or_unknown" or requests[-1].get("envelope") is not None): _fail()
    ref = receipt.get("discovery_reference")
    if (type(ref) is not dict or ref.get("operation_id") != original.DIAG_OPERATION
            or ledger.get("diagnostic") != {"name": original.DIAG_OPERATION + ".result.json",
                "bytes": e.JsonNumber(str(capture._integer(ref["receipt_bytes"], discovery.MAX_RECEIPT))), "sha256": ref["receipt_sha256"]}
            or ledger.get("projection") != {"name": original.PROJECTION_NAME,
                "bytes": e.JsonNumber(str(capture._integer(ref["projection_bytes"], discovery.MAX_RESPONSE))), "sha256": ref["projection_sha256"]}): _fail()
    return receipt, ledger, {**ref,
        "receipt_bytes": capture._integer(ref["receipt_bytes"], discovery.MAX_RECEIPT),
        "projection_bytes": capture._integer(ref["projection_bytes"], discovery.MAX_RESPONSE)}


def _execute(plan, sources, root, *, guard, clock, monotonic, transport):
    if type(plan) is not dict: _fail()
    rebuilt = _plan(**{key: plan[key] for key in ARGS})
    if e.canonical(plan) != e.canonical(rebuilt): _fail()
    plan = rebuilt
    if (plan["mode"] == "production" and (root != PRIVATE_ROOT or guard is not _guard or clock is not _now
            or monotonic is not time.monotonic or transport is not _native_request)
            or plan["mode"] == "offline-fixture" and (root == PRIVATE_ROOT or root.is_relative_to(LANE) or transport is _native_request)): _fail()
    if type(sources) is not dict or set(sources) != set(SOURCE_PATHS): _fail()
    discovery._frozen({name: sources[name] for name in discovery.SOURCE_PATHS})
    original._ledger({name: sources[name] for name in original.SOURCE_PATHS}, plan["mode"])
    started, directory, lock = monotonic(), None, None
    def check():
        guard(plan["git_head"]); current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0)
                or not capture._clock(plan["created_utc"]) <= current < capture._clock(plan["expires_utc"])
                or not 0 <= monotonic() - started < MAX_SECONDS
                or {name: _sha(raw) for name, raw in sources.items()} != plan["source_hashes"]): _fail()
    check(); directory = files._directory(root, private=True); operation = plan["operation_id"]
    report = {"schema": "tpr-ext26-owner-mia-terminal-receipt-v1", "operation_id": operation,
        "project_id": PROJECT, "backtest_id": JOB, "retrospective_owner_look_ordinal": LOOK,
        "git_head": plan["git_head"], "source_hashes": plan["source_hashes"], "plan_sha256": _sha(e.canonical(plan)),
        "owner_instruction_sha256": plan["owner_instruction_sha256"], "parent_reference": plan["parent_reference"],
        "status": "FAILED_OR_UNCERTAIN", "scope_spent": True, "parent_body_bytes": 0, "discovery": None,
        "request_attempts": 0, "received_bytes": 0, "private_artifact_bytes": 0,
        "private_artifact_bytes_semantics": "retained bytes before final receipt", "requests": [],
        "terminal": None, "charts": {}, "orders": None, "logs": {}, "component_refusals": [],
        "parent_codex_attempt": 3, "codex_off_attempts_consumed": 3, "new_codex_attempts": 0,
        "new_jobs_launched": 0, "new_looks": 0, "retrospective_parent_look29_replayed": False,
        "actor_origin_authenticated": False, "compiled_source_proven": False, "economics_accepted": False,
        "accepted_metrics": None, "full_window_accounting_proven": False, "strategy_accepted": False,
        "canonical_admission": False, "object_export": False, "automatic_retry": False}
    def publish(name, raw, *, final=False):
        reserve = 0 if final else original.MAX_RECEIPT
        if (len(raw) > (original.MAX_RECEIPT if final else capture.MAX_ARCHIVE)
                or len(raw) + reserve > original.MAX_PRIVATE_TOTAL - report["private_artifact_bytes"]): _fail()
        result = capture._publish(directory, name, raw); report["private_artifact_bytes"] += len(raw); return result
    try:
        check(); publish(operation + ".claim.spent.json", e.canonical(plan))
        try:
            check(); lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600: _fail()
            check(); publish(operation + ".access.json", _access(plan))
            ref = plan["parent_reference"]
            check(); raw = files._read(directory, ref["name"], expected_size=ref["bytes"],
                expected_sha256=ref["sha256"], remaining=original.MAX_RECEIPT, private=True)
            report["parent_body_bytes"] += len(raw); parent, ledger, discovered_ref = _parent(raw, plan, sources)
            check(); diagnostic = files._read(directory, original.DIAG_OPERATION + ".result.json",
                expected_size=capture._integer(discovered_ref["receipt_bytes"], discovery.MAX_RECEIPT),
                expected_sha256=discovered_ref["receipt_sha256"], remaining=discovery.MAX_RECEIPT, private=True)
            report["parent_body_bytes"] += len(diagnostic)
            check(); projection = files._read(directory, original.PROJECTION_NAME,
                expected_size=capture._integer(discovered_ref["projection_bytes"], discovery.MAX_RESPONSE),
                expected_sha256=discovered_ref["projection_sha256"], remaining=discovery.MAX_RESPONSE, private=True)
            report["parent_body_bytes"] += len(projection)
            # Original chronological batch is checked intact. This successor
            # targets only its refused last component, never repeats look29.
            batch = {"mode": plan["mode"], "owner_instruction_sha256": plan["owner_instruction_sha256"],
                "discovery_reference": discovered_ref, "batch_start": 8,
                "jobs": [{"backtest_id": row["backtest_id"]} for row in parent["jobs"]]}
            report["discovery"] = original._discovered(diagnostic, projection, batch,
                {name: sources[name] for name in original.SOURCE_PATHS})
            if ledger["jobs"][-1]["backtest_id"] != JOB or ledger["jobs"][-1]["look_ordinal"] != e.JsonNumber(str(LOOK)): _fail()
            def request(endpoint, payload):
                check(); _request_allowed(endpoint, payload)
                if (report["request_attempts"] >= MAX_REQUESTS
                        or READ_LIMITS[endpoint] + 1 > original.MAX_TOTAL - report["received_bytes"]): _fail()
                claim_raw = e.canonical({"endpoint": endpoint, "payload": payload, "plan_sha256": report["plan_sha256"]})
                claim = {"bytes": len(claim_raw), "sha256": _sha(claim_raw)}
                publish(operation + ".request." + claim["sha256"] + ".spent.json", claim_raw)
                item = {"endpoint": endpoint, "backtest_id": JOB, "status": "failed_or_unknown",
                    "http_status": None, "wire_bytes": None, "wire_sha256": None, "envelope": None,
                    "pipeline_phase": "transport_not_returned", "refusal_classification": None}
                report["requests"].append(item); report["request_attempts"] += 1
                stage = operation + ".read" + f'{report["request_attempts"]:04d}'
                try:
                    check(); wire, http_status, token = transport(plan, endpoint, payload,
                        min(original.REQUEST_SECONDS, MAX_SECONDS - (monotonic() - started)), claim)
                    if type(http_status) is int and 100 <= http_status <= 599: item["http_status"] = http_status
                    if type(wire) is bytes: item["wire_bytes"] = len(wire); report["received_bytes"] += len(wire)
                    item["pipeline_phase"] = "transport_returned"
                    if type(wire) is not bytes or not 0 < len(wire) <= READ_LIMITS[endpoint] or item["http_status"] is None:
                        item["refusal_classification"] = "wire_or_http_bound_refused"; return None
                    item["pipeline_phase"] = "post_transport_source_time_guard"; check()
                    item["pipeline_phase"] = "terminal_selective_parse" if endpoint == "backtests/read" else "component_exact_projection"
                    if endpoint == "backtests/read":
                        with ops.wall_deadline(MAX_PARSE_SECONDS): projected = terminal_projection(wire, credential=token)
                        response = projected["projection"]
                        envelope = e.canonical({"schema": "tpr-ext26-selective-terminal-envelope-v1",
                            "endpoint": endpoint, "request": payload, **projected})
                    else:
                        projected = e.project_wire(wire, credential=token)
                        response = discovery._contextual_redact(projected["projection"])
                        checks = ops._returned_identity(response, PROJECT, JOB) if type(response) is dict else None
                        envelope = e.canonical({"schema": "tpr-ext26-native-read-envelope-v1",
                            "endpoint": endpoint, "request": payload, "response": response,
                            "returned_identity_checks": checks})
                    item["wire_sha256"] = projected["original_wire_sha256"]
                    item["pipeline_phase"] = "safe_private_envelope_publication"; check()
                    item["envelope"] = publish(stage + ".envelope.json", envelope)
                    if item["http_status"] != 200:
                        item["refusal_classification"] = "retained_http_failure"; return None
                    if type(response) is not dict or response.get("success") is not True:
                        item["refusal_classification"] = "retained_native_shape_or_success_refusal"; return None
                    item.update(status="succeeded", pipeline_phase="safe_envelope_retained")
                    return response
                except ParseRefusal as error:
                    item["refusal_classification"] = error.code; return None
                except Exception:
                    # A genuine interrupt propagates to the scope handler; it is
                    # not a per-request refusal that licenses further reads.
                    item["refusal_classification"] = "closed_pipeline_refusal_or_uncertainty"; return None
            base = {"projectId": PROJECT, "backtestId": JOB}
            response = request("backtests/read", base)
            if response is not None: report["terminal"] = response["backtest"]
            frozen = next(row for row in e.parse_json(sources[capture.BUNDLE])["candidates"] if row["candidate_id"] == CANDIDATE)
            sessions = ops._bundle_calendar(frozen)
            # Every component has its own safety checks. A parser refusal does
            # not establish stage and does not suppress independent reads.
            for name in ops.CHARTS:
                response = request("backtests/chart/read", {**base, "name": name, "start": ops.CHART_START,
                    "end": ops.CHART_END, "count": ops.CHART_COUNT})
                if response is None: report["charts"][name] = {"classification": "diagnostic_component_request_refused"}; continue
                if name == "EXT26 Account NAV":
                    report["charts"][name], _ = ops._account_nav_chart(response, sessions)
                else:
                    chart = response.get("chart")
                    report["charts"][name] = {"classification": "diagnostic_loading_chart" if response.get("status") in {"loading", "Loading"}
                        else "diagnostic_default_equity_control" if type(chart) is dict and chart.get("name") == name
                        else "diagnostic_missing_chart", "accepted_metrics": None}
            try:
                total, ids, pages = None, set(), 0
                for number in range(original.MAX_PAGES):
                    start = number * original.PAGE_SIZE
                    response = request("backtests/orders/read", {**base, "start": start, "end": start + original.PAGE_SIZE})
                    if response is None:
                        report["orders"] = {"classification": "diagnostic_order_request_refused", "pages_retained": pages}; break
                    if response.get("status") in {"loading", "Loading"}:
                        report["orders"] = {"classification": "diagnostic_loading_orders", "pages_retained": pages}; break
                    count = capture._integer(response.get("length"), original.MAX_PAGES * original.PAGE_SIZE); rows = response.get("orders")
                    if total is not None and total != count or type(rows) is not list or len(rows) != min(original.PAGE_SIZE, count - start): _fail()
                    total = count
                    for row in rows:
                        identity = e._integer(row.get("id")) if type(row) is dict else None
                        if identity is None or identity in ids: _fail()
                        ids.add(identity)
                    pages += 1
                    report["orders"] = {"classification": "diagnostic_partial_order_pages", "pages_retained": pages,
                        "order_count": len(ids), "reported_total": total, "fees": None, "fills": None}
                    if (number + 1) * original.PAGE_SIZE >= total:
                        if len(ids) != total: _fail()
                        report["orders"]["classification"] = "complete_order_page_census_only"; break
            except Exception:
                report["component_refusals"].append("order_census_shape_refused")
            for marker in ("EXT26_SUMMARY", "EXT26_EVIDENCE_INDEX"):
                response = request("backtests/read/log", {**base, "start": 0, "end": 100, "query": marker})
                report["logs"][marker] = original._logs(response, marker, JOB, sources) if response is not None else {
                    "classification": "diagnostic_component_request_refused", "compact_validated": False}
            check(); report["status"] = "COMPLETED_DIAGNOSTIC_CAPTURE"
        except (Exception, KeyboardInterrupt): report["status"] = "FAILED_OR_UNCERTAIN"
        report["ended_utc"] = clock().isoformat()
        raw_report = e.canonical(report); publish(operation + ".result.json", raw_report, final=True); return raw_report
    finally:
        if lock is not None:
            try:
                named, owned = os.stat("controller.lock", dir_fd=directory, follow_symlinks=False), os.fstat(lock)
                if (named.st_dev, named.st_ino) == (owned.st_dev, owned.st_ino): os.unlink("controller.lock", dir_fd=directory)
            except FileNotFoundError: pass
            finally: os.close(lock)
        if directory is not None: os.close(directory)


def execute_plan(plan):
    if type(plan) is not dict or plan.get("mode") != "production": _fail()
    return _execute(plan, _sources(plan["git_head"]), PRIVATE_ROOT,
        guard=_guard, clock=_now, monotonic=time.monotonic, transport=_native_request)


def execute_fixture(plan, sources, root, *, clock, transport, guard=lambda _: None, monotonic=lambda: 0.0):
    if type(plan) is not dict or plan.get("mode") != "offline-fixture": _fail()
    return _execute(plan, sources, root, guard=guard, clock=clock, monotonic=monotonic, transport=transport)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", required=True); parser.add_argument("--plan-sha256", required=True)
    arguments = parser.parse_args(argv)
    try:
        raw = arguments.plan_json.encode()
        if _sha(raw) != e._hash(arguments.plan_sha256): _fail()
        returned = execute_plan(e.parse_json(raw)); result = e.parse_json(returned)
        print(e.canonical({"operation_id": result["operation_id"], "status": result["status"],
            "receipt_sha256": _sha(returned), "request_attempts": result["request_attempts"],
            "accepted_metrics": None, "automatic_retry": False}).decode(), end="")
        return 0 if result["status"] == "COMPLETED_DIAGNOSTIC_CAPTURE" else 1
    except (Exception, KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","accepted_metrics":null,"automatic_retry":false}')
        return 1


if __name__ == "__main__": raise SystemExit(main())
