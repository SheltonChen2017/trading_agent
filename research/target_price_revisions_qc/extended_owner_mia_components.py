"""Bounded read-only components of explicitly discovered own-OFF jobs.

No launch, source edit, Object Store export, accepted metric or old-attempt
manifest is produced. An external job's retrospective look identity is separate
from the exhausted parent Codex attempt. Current-project files are not compiled
job source. Invalid compact messages remain diagnostic without suppressing
independently captured chart/order/index evidence. No automatic scope renewal.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import time

from . import extended_owner_mia_discovery as discovery

capture, e = discovery.capture, discovery.e
ops, files = capture.ops, capture.files
LANE, PRIVATE_ROOT, PROJECT = capture.LANE, capture.PRIVATE_ROOT, capture.PROJECT
CANDIDATE = capture.CANDIDATE
MODULE = capture.PREFIX + "extended_owner_mia_components.py"
LEDGER = capture.PREFIX + "extended_owner_recovery_observations30.json"
LEDGER_SHA256 = "0d42011a1a7e2c94fe9a5df948d5fa21b9a0546e7f69b8036f2532ac7073d8ef"
SOURCE_PATHS = (*discovery.SOURCE_PATHS, LEDGER, MODULE)
DIAG_OPERATION = "TPR-EXT26-OWNER-MIA-META-INSPECT-20261013-001"
PROJECTION_NAME = "TPR-EXT26-OWNER-MIA-DISCOVERY-20261013-001.read001.projection.json"
MAX_JOBS, MAX_PAGES, PAGE_SIZE = 8, 128, 99
MAX_SECONDS, REQUEST_SECONDS = 600, 30
MAX_TOTAL, MAX_PRIVATE_TOTAL = 64 * 1024 * 1024, 128 * 1024 * 1024
MAX_RECEIPT = 2 * 1024 * 1024
READ_LIMITS = {"backtests/read": 4 * 1024 * 1024, "backtests/chart/read": 2 * 1024 * 1024,
               "backtests/orders/read": 1024 * 1024, "backtests/read/log": 1024 * 1024}
MAX_REQUESTS = MAX_JOBS * (5 + MAX_PAGES)
ARGS = ("operation_id", "git_head", "source_hashes", "owner_instruction_sha256", "created_utc",
        "expires_utc", "discovery_reference", "batch_start", "jobs", "mode")
DOCS_BASE = "https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/backtest-management/read-backtest/"
PRIMARY_DOCS = tuple(DOCS_BASE + name for name in ("backtest-statistics", "charts", "orders", "logs"))
Refusal = e.EvidenceError


def _fail():
    raise Refusal("bounded own-job component capture refused; no automatic retry")


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _guard(head):
    discovery._guard(head)
    if Path(__file__) != LANE / MODULE or Path(__file__).resolve() != LANE / MODULE: _fail()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE,
            capture_output=True, timeout=5).returncode: _fail()


def _sources(head):
    result = discovery._sources(head)
    for relative in (LEDGER, MODULE):
        _guard(head)
        recorded = subprocess.run(["git", "show", head + ":" + relative], cwd=LANE,
            capture_output=True, timeout=5, check=True).stdout
        directory = files._directory((LANE / relative).parent, private=False)
        try:
            result[relative] = files._read(directory, Path(relative).name, expected_size=len(recorded),
                expected_sha256=_sha(recorded), remaining=capture.MAX_RESPONSE, private=False)
        finally: os.close(directory)
    _guard(head); return result


def _plan(*, operation_id, git_head, source_hashes, owner_instruction_sha256, created_utc,
          expires_utc, discovery_reference, batch_start, jobs, mode="production"):
    if (type(operation_id) is not str or re.fullmatch(r"TPR-EXT26-OWNER-MIA-COMPONENTS-[A-Za-z0-9-]{1,50}", operation_id) is None
            or mode not in {"production", "offline-fixture"}): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS): _fail()
    for value in source_hashes.values(): e._hash(value)
    if mode == "production" and source_hashes[LEDGER] != LEDGER_SHA256: _fail()
    for name, identity in ((capture.BUNDLE, capture.BUNDLE_SHA256), (discovery.LOOK, discovery.LOOK_SHA256),
            (capture.PREFIX + "extended_study_freeze.json", e.FREEZE_SHA256),
            (capture.PREFIX + "extended_calendar.json", ops.CALENDAR_SHA256)):
        if source_hashes[name] != identity: _fail()
    if not timedelta(0) < capture._clock(expires_utc) - capture._clock(created_utc) <= timedelta(hours=1): _fail()
    e._closed(discovery_reference, {"operation_id", "receipt_bytes", "receipt_sha256", "projection_name", "projection_bytes", "projection_sha256"})
    ref = dict(discovery_reference)
    if ref["operation_id"] != DIAG_OPERATION or ref["projection_name"] != PROJECTION_NAME: _fail()
    ref["receipt_bytes"] = capture._integer(ref["receipt_bytes"], discovery.MAX_RECEIPT)
    ref["projection_bytes"] = capture._integer(ref["projection_bytes"], discovery.MAX_RESPONSE)
    if not ref["receipt_bytes"] or not ref["projection_bytes"]: _fail()
    e._hash(ref["receipt_sha256"]); e._hash(ref["projection_sha256"])
    batch_start = capture._integer(batch_start, discovery.MAX_ROWS - 1)
    if batch_start % MAX_JOBS: _fail()
    if type(jobs) is not list or not 1 <= len(jobs) <= MAX_JOBS: _fail()
    admitted, seen = [], set()
    for offset, job in enumerate(jobs):
        e._closed(job, {"backtest_id", "retrospective_owner_look_ordinal"})
        identity = e._id(job["backtest_id"])
        ordinal = capture._integer(job["retrospective_owner_look_ordinal"], 20 + discovery.MAX_ROWS)
        if identity in seen or identity in discovery.PRIOR_JOBS or ordinal != 21 + batch_start + offset: _fail()
        seen.add(identity); admitted.append({"backtest_id": identity, "retrospective_owner_look_ordinal": ordinal})
    return {"schema": "tpr-ext26-owner-mia-components-plan-v1", "operation_id": operation_id,
        "project_id": PROJECT, "declared_candidate_id": CANDIDATE, "study_id": e.STUDY_ID,
        "config_sha256": discovery.CONFIG_SHA256, "config_module_sha256": discovery.CONFIG_MODULE_SHA256,
        "freeze_sha256": e.FREEZE_SHA256, "calendar_sha256": ops.CALENDAR_SHA256,
        "git_head": git_head, "source_hashes": dict(source_hashes), "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created_utc, "expires_utc": expires_utc, "discovery_reference": ref,
        "batch_start": batch_start, "jobs": admitted, "mode": mode, "parent_codex_attempt": 3,
        "codex_off_attempts_consumed": 3, "read_endpoints": dict(READ_LIMITS), "max_jobs": MAX_JOBS,
        "max_order_pages_per_job": MAX_PAGES, "max_requests": MAX_REQUESTS, "max_received_bytes": MAX_TOTAL,
        "max_private_artifact_bytes_total": MAX_PRIVATE_TOTAL, "max_seconds": MAX_SECONDS,
        "request_seconds": REQUEST_SECONDS, "new_codex_attempts": 0, "new_jobs_launched": 0,
        "automatic_retry": False, "source_read": False, "object_export": False,
        "compiled_source_proven": False, "economics_accepted": False, "canonical_admission": False}


def prepare_plan(**arguments):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    plan = _plan(git_head=head, source_hashes={name: _sha(raw) for name, raw in sources.items()}, **arguments)
    raw = e.canonical(plan)
    return {"plan": plan, "plan_json": raw.decode(), "plan_sha256": _sha(raw)}


def _ledger(sources, mode):
    if mode == "production" and _sha(sources[LEDGER]) != LEDGER_SHA256: _fail()
    ledger = e.parse_json(sources[LEDGER])
    if (ledger.get("schema") != "tpr-ext26-retrospective-owner-job-observations-v1"
            or ledger.get("project_id") != e.JsonNumber(str(PROJECT)) or ledger.get("candidate_id") != CANDIDATE
            or ledger.get("study_id") != e.STUDY_ID or ledger.get("freeze_sha256") != e.FREEZE_SHA256
            or ledger.get("calendar_sha256") != ops.CALENDAR_SHA256 or ledger.get("config_sha256") != discovery.CONFIG_SHA256
            or ledger.get("attempt_reset") is not False or ledger.get("new_codex_launches") != e.JsonNumber("0")
            or ledger.get("parent_codex_off_attempts_consumed") != e.JsonNumber("3")): _fail()
    return ledger


def _discovered(raw, projection_raw, plan, sources):
    """Verify the exact diagnostic AND its captured metadata, without inventing UTC.

    The original discovery remains FAILED_OR_UNCERTAIN. This is a distinct
    bounded read of its projection plus a successfully identified diagnosis,
    not a retry, repair of old evidence, or acceptance of external strategy.
    """
    ledger, row, outer = _ledger(sources, plan["mode"]), e.parse_json(raw), e.parse_json(projection_raw)
    ref = plan["discovery_reference"]
    if (ledger.get("owner_instruction_sha256") != plan["owner_instruction_sha256"]
            or ledger.get("diagnostic") != {"name": DIAG_OPERATION + ".result.json", "bytes": e.JsonNumber(str(ref["receipt_bytes"])), "sha256": ref["receipt_sha256"]}
            or ledger.get("projection") != {"name": PROJECTION_NAME, "bytes": e.JsonNumber(str(ref["projection_bytes"])), "sha256": ref["projection_sha256"]}
            or row.get("schema") != "tpr-ext26-owner-mia-metadata-inspect-receipt-v1" or row.get("operation_id") != DIAG_OPERATION
            or row.get("status") != "COMPLETED_DIAGNOSTIC_INSPECTION" or row.get("scope_spent") is not True
            or row.get("api_requests") != e.JsonNumber("0") or row.get("new_jobs") != e.JsonNumber("0")): _fail()
    e._closed(outer, {"schema", "redaction_policy", "original_wire_sha256", "original_wire_bytes", "projection_sha256", "projection",
        "unexpected_outcome_or_parameter_fields_present", "raw_wire_retained", "outcome_parameter_source_fields_retained"})
    if (outer["schema"] != "tpr-ext26-wire-projection-v1" or outer["redaction_policy"] != "tpr-ext26-owner-discovery-contextual-metadata-v1"
            or outer["raw_wire_retained"] is not False or outer["outcome_parameter_source_fields_retained"] is not False
            or type(outer["unexpected_outcome_or_parameter_fields_present"]) is not bool): _fail()
    value, diagnostic = outer["projection"], row.get("diagnostic")
    if type(value) is not dict or type(diagnostic) is not dict or value.get("success") is not True: _fail()
    if _sha(e.canonical(value)) != e._hash(outer["projection_sha256"]): _fail()
    e._hash(outer["original_wire_sha256"])
    capture._integer(outer["original_wire_bytes"], discovery.MAX_RESPONSE)
    native_rows = value.get("backtests")
    if (type(native_rows) is not list or not 1 <= len(native_rows) <= discovery.MAX_ROWS
            or capture._integer(value.get("count"), discovery.MAX_ROWS) != len(native_rows)
            or diagnostic.get("success") is not True or diagnostic.get("count") != value["count"]
            or diagnostic.get("returned_rows") != e.JsonNumber(str(len(native_rows)))
            or diagnostic.get("projection_sha256") != outer["projection_sha256"]
            or diagnostic.get("wire_sha256") != outer["original_wire_sha256"]
            or diagnostic.get("wire_bytes") != outer["original_wire_bytes"]): _fail()
    if "projectId" in value and capture._integer(value["projectId"], 2**31 - 1) != PROJECT: _fail()
    known = discovery._frozen({name: sources[name] for name in discovery.SOURCE_PATHS})
    if set(ledger.get("known_historical_jobs", [])) != set(known): _fail()
    selected_rows, seen, all_rows = [], set(), []
    for native in native_rows:
        if type(native) is not dict: _fail()
        identity, created = e._id(native.get("backtestId")), native.get("created")
        if identity in seen or capture._integer(native.get("projectId"), 2**31 - 1) != PROJECT: _fail()
        seen.add(identity)
        if type(created) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", created) is None: _fail()
        try: datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
        except ValueError: _fail()
        progress = native.get("progress")
        if type(progress) is not e.JsonNumber or not 0 <= progress.fraction() <= 1: _fail()
        all_rows.append(native)
        if identity not in known: selected_rows.append(native)
    diagnostics = diagnostic.get("jobs")
    if type(diagnostics) is not list or len(diagnostics) != len(native_rows): _fail()
    for native, parsed in zip(all_rows, diagnostics):
        if (type(parsed) is not dict or parsed.get("created_is_timezone_aware") is not False
                or any(parsed.get(key) != native.get(key) for key in ("backtestId", "created", "status", "progress", "snapshotId", "projectId"))): _fail()
    selected_rows.sort(key=lambda item: (item["created"], item["backtestId"]))
    unknown = [native["backtestId"] for native in selected_rows]
    expected_jobs = ledger.get("jobs")
    if (type(expected_jobs) is not list or len(expected_jobs) != len(unknown)
            or ledger.get("newly_observed_jobs") != e.JsonNumber(str(len(unknown)))): _fail()
    for offset, (native, observed) in enumerate(zip(selected_rows, expected_jobs)):
        if (observed.get("backtest_id") != native["backtestId"] or observed.get("created_server_string") != native["created"]
                or observed.get("status") != native["status"] or observed.get("snapshot_id") != native.get("snapshotId")
                or observed.get("look_ordinal") != e.JsonNumber(str(21 + offset))
                or observed.get("creation_timezone_known") is not False or observed.get("retrospective") is not True
                or observed.get("origin_authenticated_as_mia") is not False or observed.get("compiled_source_proven") is not False
                or observed.get("accepted_metrics") is not None or observed.get("economics_accepted") is not False): _fail()
    start = plan["batch_start"]
    if start >= len(unknown) or [job["backtest_id"] for job in plan["jobs"]] != unknown[start:start + MAX_JOBS]: _fail()
    return {"unfamiliar_jobs_total": len(unknown), "all_unfamiliar_job_ids": unknown,
        "batch_start": start, "batch_end": start + len(plan["jobs"]), "server_string_order_verified": True,
        "creation_timezone_known": False, "utc_chronology_attested": False,
        "chronology_basis": "uniform unzoned server creation strings; relative order only",
        "unfamiliar_jobs_omitted_from_this_batch": len(unknown) - len(plan["jobs"]),
        "owner_mia_origin_authenticated": False, "compiled_source_proven": False}


def _request_allowed(plan, endpoint, payload):
    if endpoint not in READ_LIMITS or type(payload) is not dict: _fail()
    identity = payload.get("backtestId")
    if identity not in {job["backtest_id"] for job in plan["jobs"]}: _fail()
    base = {"projectId": PROJECT, "backtestId": identity}
    if endpoint == "backtests/read": expected = base
    elif endpoint == "backtests/chart/read":
        if payload.get("name") not in ops.CHARTS: _fail()
        expected = {**base, "name": payload["name"], "start": ops.CHART_START, "end": ops.CHART_END, "count": ops.CHART_COUNT}
    elif endpoint == "backtests/read/log":
        if payload.get("query") not in {"EXT26_SUMMARY", "EXT26_EVIDENCE_INDEX"}: _fail()
        expected = {**base, "start": 0, "end": 100, "query": payload["query"]}
    else:
        start = payload.get("start")
        if type(start) is not int or not 0 <= start < MAX_PAGES * PAGE_SIZE or start % PAGE_SIZE: _fail()
        expected = {**base, "start": start, "end": start + PAGE_SIZE}
    if payload != expected: _fail()


def _access(plan):
    return e.canonical({"plan_sha256": _sha(e.canonical(plan)), "created_utc": plan["created_utc"],
        "expires_utc": plan["expires_utc"], "project_id": PROJECT, "read_only": True,
        "discovery_reference": plan["discovery_reference"], "jobs": plan["jobs"]})


def _native_request(plan, endpoint, payload, seconds, claim):
    _request_allowed(plan, endpoint, payload)
    rebuilt = _plan(**{key: plan[key] for key in ARGS})
    if (plan.get("mode") != "production" or e.canonical(plan) != e.canonical(rebuilt)
            or type(seconds) not in (int, float) or not 0 < seconds <= REQUEST_SECONDS): _fail()
    header = e.canonical(rebuilt); raw_request = e.canonical({"endpoint": endpoint, "payload": payload, "plan_sha256": _sha(header)})
    if claim != {"bytes": len(raw_request), "sha256": _sha(raw_request)}: _fail()
    _guard(plan["git_head"])
    if not capture._clock(plan["created_utc"]) <= _now() < capture._clock(plan["expires_utc"]): _fail()
    directory = files._directory(PRIVATE_ROOT, private=True)
    try:
        for name, raw in ((plan["operation_id"] + ".claim.spent.json", header),
                (plan["operation_id"] + ".access.json", _access(plan)),
                (plan["operation_id"] + ".request." + _sha(raw_request) + ".spent.json", raw_request)):
            files._read(directory, name, expected_size=len(raw), expected_sha256=_sha(raw), remaining=discovery.MAX_RECEIPT, private=True)
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
            connection.request("POST", "/api/v2/" + endpoint, body=e.canonical(payload), headers={
                "Authorization": "Basic " + authorization, "Timestamp": stamp, "Content-Type": "application/json"})
            response = connection.getresponse()
            return response.read(READ_LIMITS[endpoint] + 1), response.status, token
        finally:
            if connection is not None: connection.close()


def _terminal(response, identity):
    row = response.get("backtest")
    if type(row) is not dict or row.get("backtestId") != identity or type(row.get("completed")) is not bool: _fail()
    status, error, progress = row.get("status"), row.get("error"), row.get("progress")
    if ("error" not in row or error is not None and (type(error) is not str or not error)
            or type(progress) is not e.JsonNumber or not 0 <= progress.fraction() <= 1): _fail()
    terminal = row["completed"] and status in {"Completed", "Completed.", "Runtime Error", "Error", "Stopped", "Cancelled"}
    if (status in {"Completed", "Completed."} and (not terminal or error is not None or progress.fraction() != 1)
            or status in {"Runtime Error", "Error"} and (not terminal or error is None)): _fail()
    return {"terminal": terminal, "status": status if status in discovery.STATUS else "unrecognized_status",
        "completed_flag": row["completed"], "progress": progress, "error_bytes": len(error.encode()) if error else 0,
        "error_sha256": _sha(error.encode()) if error else None,
        "compile_id_observed": row.get("compileId") if type(row.get("compileId")) is str and len(row["compileId"]) <= 200 else None,
        "compiled_source_proven": False, "full_window_accounting_proven": False}


def _logs(response, marker, identity, sources):
    result = {"observed_matching_log_count": None, "compact_validated": False, "classification": "diagnostic_native_log_shape_refused",
        "aggregate_sha256": None, "journal_legacy_parent_attempt": 3, "private_journal_replay_verified": False}
    try:
        rows = response.get("logs"); count = capture._integer(response.get("length"), 100000)
        if type(rows) is not list or len(rows) != min(count, 100) or any(type(row) is not str for row in rows): _fail()
    except (e.EvidenceError, ValueError): return result
    result.update(observed_matching_log_count=count, classification="diagnostic_missing_aggregate")
    if count != 1:
        if count: result["classification"] = "diagnostic_ambiguous_aggregate_count"
        return result
    frozen = next(row for row in e.parse_json(sources[capture.BUNDLE])["candidates"] if row["candidate_id"] == CANDIDATE)
    manifest = {"candidate_id": CANDIDATE, "project_id": PROJECT, "arm": "tpr_off",
        "config_sha256": discovery.CONFIG_SHA256, "input_hashes": frozen["input_hashes"]}
    try:
        aggregate = ops.compact_aggregate(rows[0], marker, manifest, 3, identity)
    except (e.EvidenceError, ops.Refusal, ValueError):
        result["classification"] = "diagnostic_compact_message_refused"
        return result
    result.update(compact_validated=True, classification="validated_compact_shape_only",
        aggregate_sha256=_sha(e.canonical(aggregate)))
    return result


def _now(): return datetime.now(timezone.utc)


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
    _ledger(sources, plan["mode"])
    started, directory, lock = monotonic(), None, None
    def check():
        guard(plan["git_head"]); current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0)
                or not capture._clock(plan["created_utc"]) <= current < capture._clock(plan["expires_utc"])
                or not 0 <= monotonic() - started < MAX_SECONDS
                or {name: _sha(raw) for name, raw in sources.items()} != plan["source_hashes"]): _fail()
    check(); directory = files._directory(root, private=True); operation = plan["operation_id"]
    report = {"schema": "tpr-ext26-owner-mia-components-receipt-v1", "operation_id": operation,
        "project_id": PROJECT, "declared_candidate_id": CANDIDATE, "study_id": e.STUDY_ID,
        "git_head": plan["git_head"], "source_hashes": plan["source_hashes"], "plan_sha256": _sha(e.canonical(plan)),
        "owner_instruction_sha256": plan["owner_instruction_sha256"], "discovery_reference": plan["discovery_reference"],
        "status": "FAILED_OR_UNCERTAIN", "scope_spent": True, "discovery_body_bytes": 0, "discovery": None,
        "request_attempts": 0, "received_bytes": 0, "private_artifact_bytes": 0,
        "private_artifact_bytes_semantics": "retained bytes before final receipt", "failed_response_bytes_unknown": False,
        "requests": [], "jobs": [], "parent_codex_attempt": 3, "codex_off_attempts_consumed": 3,
        "new_codex_attempts": 0, "new_jobs_launched": 0, "new_looks": 0, "look_registry_updates_performed": 0,
        "actor_attribution": "owner-reported-mia-unverified", "winner_selected": False,
        "compiled_source_proven": False, "source_current_is_job_source": False, "accepted_metrics": None,
        "economics_accepted": False, "strategy_accepted": False, "canonical_admission": False,
        "object_export": False, "private_journal_replay_verified": False, "automatic_retry": False, "trading": False}
    def publish(name, raw, *, final=False):
        reserve = 0 if final else MAX_RECEIPT
        if len(raw) > (MAX_RECEIPT if final else capture.MAX_ARCHIVE) or len(raw) + reserve > MAX_PRIVATE_TOTAL - report["private_artifact_bytes"]: _fail()
        result = capture._publish(directory, name, raw); report["private_artifact_bytes"] += len(raw); return result
    try:
        check(); publish(operation + ".claim.spent.json", e.canonical(plan))
        try:
            check(); lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600: _fail()
            check(); publish(operation + ".access.json", _access(plan))
            ref = plan["discovery_reference"]
            check(); raw = files._read(directory, ref["operation_id"] + ".result.json", expected_size=ref["receipt_bytes"],
                expected_sha256=ref["receipt_sha256"], remaining=discovery.MAX_RECEIPT, private=True)
            report["discovery_body_bytes"] += len(raw)
            check(); projection_raw = files._read(directory, ref["projection_name"], expected_size=ref["projection_bytes"],
                expected_sha256=ref["projection_sha256"], remaining=discovery.MAX_RESPONSE, private=True)
            report["discovery_body_bytes"] += len(projection_raw)
            report["discovery"] = _discovered(raw, projection_raw, plan, sources)
            def request(endpoint, payload):
                check(); _request_allowed(plan, endpoint, payload)
                if (report["request_attempts"] >= MAX_REQUESTS
                        or READ_LIMITS[endpoint] + 1 > MAX_TOTAL - report["received_bytes"]): _fail()
                claim_raw = e.canonical({"endpoint": endpoint, "payload": payload, "plan_sha256": report["plan_sha256"]})
                claim = {"bytes": len(claim_raw), "sha256": _sha(claim_raw)}
                publish(operation + ".request." + claim["sha256"] + ".spent.json", claim_raw)
                stage = operation + ".read" + f'{report["request_attempts"] + 1:04d}'
                item = {"endpoint": endpoint, "backtest_id": payload["backtestId"], "status": "failed_or_unknown",
                    "wire_bytes": None, "wire_sha256": None, "http_status": None, "envelope": None,
                    "native_success_accepted": False}
                report["requests"].append(item); report["request_attempts"] += 1; report["failed_response_bytes_unknown"] = True
                check(); seconds = min(REQUEST_SECONDS, MAX_SECONDS - (monotonic() - started))
                wire, status, token = transport(plan, endpoint, payload, seconds, claim)
                if type(wire) is not bytes: _fail()
                report["received_bytes"] += len(wire); report["failed_response_bytes_unknown"] = False
                item["wire_bytes"] = len(wire)
                if not 0 < len(wire) <= READ_LIMITS[endpoint] or type(status) is not int or not 100 <= status <= 599: _fail()
                check(); projected = e.project_wire(wire, credential=token)
                response = discovery._contextual_redact(projected["projection"])
                item["wire_sha256"] = projected["original_wire_sha256"]; item["http_status"] = status
                # Explicit foreign identities/credential echoes refuse body
                # retention. Otherwise failed/loading replies are evidence,
                # not successful component acceptance or a reason to retry.
                checks = ops._returned_identity(response, PROJECT, payload["backtestId"]) if type(response) is dict else None
                envelope = e.canonical({"schema": "tpr-ext26-native-read-envelope-v1", "endpoint": endpoint,
                    "request": payload, "response": response, "returned_identity_checks": checks})
                check(); item["envelope"] = publish(stage + ".envelope.json", envelope)
                if status != 200:
                    item["status"] = "retained_http_failure"; _fail()
                if type(response) is not dict or response.get("success") is not True:
                    item["status"] = "retained_native_shape_or_success_refusal"; _fail()
                item["status"] = "succeeded"; item["native_success_accepted"] = True
                return response, item["envelope"]
            for selected in plan["jobs"]:
                check(); identity = selected["backtest_id"]; base = {"projectId": PROJECT, "backtestId": identity}
                result = {**selected, "origin_authenticated": False, "compiled_source_proven": False,
                    "terminal": None, "charts": {}, "orders": None, "logs": {}, "accepted_metrics": None,
                    "economics_accepted": False, "full_window_accounting_proven": False}
                report["jobs"].append(result)
                response, _ = request("backtests/read", base)
                try: result["terminal"] = _terminal(response, identity)
                except (e.EvidenceError, ValueError):
                    result["classification"] = "diagnostic_native_terminal_shape_refused"; continue
                if not result["terminal"]["terminal"]:
                    result["classification"] = "diagnostic_job_not_terminal"; continue
                frozen = next(row for row in e.parse_json(sources[capture.BUNDLE])["candidates"] if row["candidate_id"] == CANDIDATE)
                sessions = ops._bundle_calendar(frozen)
                for name in ops.CHARTS:
                    response, _ = request("backtests/chart/read", {**base, "name": name, "start": ops.CHART_START,
                        "end": ops.CHART_END, "count": ops.CHART_COUNT})
                    if name == "EXT26 Account NAV":
                        census, _ = ops._account_nav_chart(response, sessions); result["charts"][name] = census
                    else:
                        chart = response.get("chart")
                        result["charts"][name] = {"classification": "diagnostic_loading_chart" if response.get("status") in {"loading", "Loading"}
                            else "diagnostic_default_equity_control" if type(chart) is dict and chart.get("name") == name
                            else "diagnostic_missing_chart", "accepted_metrics": None}
                pages, total, ids = [], None, set()
                for number in range(MAX_PAGES):
                    start = number * PAGE_SIZE
                    response, descriptor = request("backtests/orders/read", {**base, "start": start, "end": start + PAGE_SIZE})
                    if response.get("status") in {"loading", "Loading"}:
                        result["orders"] = {"classification": "diagnostic_loading_orders", "pages_retained": len(pages),
                            "order_count": None, "fees": None, "fills": None}; break
                    count = capture._integer(response.get("length"), MAX_PAGES * PAGE_SIZE); rows = response.get("orders")
                    if total is not None and total != count or type(rows) is not list or len(rows) != min(PAGE_SIZE, count - start): _fail()
                    total = count
                    for row in rows:
                        order = e._integer(row.get("id")) if type(row) is dict else None
                        if order is None or order in ids: _fail()
                        ids.add(order)
                    pages.append(descriptor)
                    result["orders"] = {"classification": "diagnostic_partial_order_pages", "pages_retained": len(pages),
                        "order_count": len(ids), "reported_total": total, "fees": None, "fills": None,
                        "normalized_fill_or_fee_observations_proven": False}
                    if (number + 1) * PAGE_SIZE >= total:
                        if len(ids) != total: _fail()
                        result["orders"]["classification"] = "complete_order_page_census_only"
                        break
                for marker in ("EXT26_SUMMARY", "EXT26_EVIDENCE_INDEX"):
                    response, _ = request("backtests/read/log", {**base, "start": 0, "end": 100, "query": marker})
                    result["logs"][marker] = _logs(response, marker, identity, sources)
                result["classification"] = "diagnostic_native_components_captured"
            check(); report["status"] = "COMPLETED_CAPTURE"
        except (Exception, KeyboardInterrupt): report["status"] = "FAILED_OR_UNCERTAIN"
        report["ended_utc"] = clock().isoformat()
        raw_report = e.canonical(report)
        publish(operation + ".result.json", raw_report, final=True); return raw_report
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
    return _execute(plan, _sources(plan["git_head"]), PRIVATE_ROOT, guard=_guard, clock=_now,
        monotonic=time.monotonic, transport=_native_request)


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
        result = e.parse_json(execute_plan(e.parse_json(raw)))
        # No response bodies, source, performance, order rows or error text.
        print(e.canonical({"operation_id": result["operation_id"], "status": result["status"],
            "receipt_sha256": _sha(e.canonical(result)), "request_attempts": result["request_attempts"],
            "accepted_metrics": None, "automatic_retry": False}).decode(), end="")
        return 0 if result["status"] == "COMPLETED_CAPTURE" else 1
    except (Exception, KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","accepted_metrics":null,"automatic_retry":false}')
        return 1


if __name__ == "__main__": raise SystemExit(main())
