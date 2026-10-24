"""One fresh own-OFF-project metadata discovery; no source/result or launch.

The documented list API has no date or page inputs. One bounded response is
sorted chronologically, including failures; unfamiliar jobs are not selected
as winners or authenticated as Mia. Body-free receipts cannot establish source,
full-window accounting, performance or economics. Spent scopes never renew.
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

from . import extended_mia_capture as capture

e, ops, files = capture.e, capture.ops, capture.files
LANE, BRANCH, PRIVATE_ROOT = capture.LANE, capture.BRANCH, capture.PRIVATE_ROOT
PROJECT, CANDIDATE = capture.PROJECT, capture.CANDIDATE
MODULE = capture.PREFIX + "extended_owner_mia_discovery.py"
LOOK = capture.PREFIX + "extended_mia_recovery_look20.json"
LOOK_SHA256 = "afe5e0994e140f127ac0bd92521448e0126e296c37fe11318f89f24e7c7334a0"
CONFIG_SHA256 = "19a9842cfceb695d1f8256f429745247387c89bb725ee2b8be44fe98a726322a"
CONFIG_MODULE_SHA256 = "5790ca63661f0f54a7734565342d141cbaba7797eb8c7b1e488c7ad573b01bd0"
SOURCE_PATHS = (*capture.SOURCE_PATHS, MODULE, LOOK)
ENDPOINT = "backtests/list"
PAYLOAD = {"projectId": PROJECT, "includeStatistics": False}
MAX_RESPONSE, MAX_ROWS, MAX_SECONDS = 1024 * 1024, 128, 30
MAX_RECEIPT, MAX_PRIVATE_ARTIFACT = 256 * 1024, 8 * 1024 * 1024
PRIOR_JOBS = frozenset(("34e0636f373c5ed9ee97387335b52454", "f79d3ff02644ec81f20da5cc6ca7440a",
                       "d7c76b7c4936c814f125a2b9a8cc2896"))
STATUS = frozenset(("Completed", "Completed.", "Runtime Error", "Error", "Stopped", "Cancelled",
                    "In Queue...", "In Progress...", "Running"))
OUTCOME_FIELDS = frozenset(("statistics", "runtimeStatistics", "totalPerformance", "rollingWindow", "parameterSet", "parameters",
    "sharpeRatio", "alpha", "beta", "compoundingAnnualReturn", "drawdown", "lossRate", "netProfit", "psr", "sortinoRatio",
    "trades", "treynorRatio", "winRate"))
ARGS = ("operation_id", "git_head", "source_hashes", "owner_instruction_sha256", "created_utc", "expires_utc", "mode")
Refusal = e.EvidenceError


def _fail():
    raise Refusal("bounded own-OFF metadata discovery refused; no automatic retry")


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _guard(head):
    capture._guard(head)
    if Path(__file__) != LANE / MODULE or Path(__file__).resolve() != LANE / MODULE: _fail()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE,
            capture_output=True, timeout=5).returncode: _fail()


def _sources(head):
    result = capture._sources(head)
    for relative in (MODULE, LOOK):
        _guard(head)
        committed = subprocess.run(["git", "show", head + ":" + relative], cwd=LANE,
            capture_output=True, timeout=5, check=True).stdout
        directory = files._directory((LANE / relative).parent, private=False)
        try:
            _guard(head)
            result[relative] = files._read(directory, Path(relative).name, expected_size=len(committed),
                expected_sha256=_sha(committed), remaining=capture.MAX_RESPONSE, private=False)
        finally: os.close(directory)
    _frozen(result); _guard(head)
    return result


def _frozen(sources):
    if (type(sources) is not dict or set(sources) != set(SOURCE_PATHS)
            or _sha(sources[capture.BUNDLE]) != capture.BUNDLE_SHA256
            or _sha(sources[capture.PREFIX + "extended_study_freeze.json"]) != e.FREEZE_SHA256
            or _sha(sources[capture.PREFIX + "extended_calendar.json"]) != ops.CALENDAR_SHA256
            or _sha(sources[LOOK]) != LOOK_SHA256): _fail()
    candidates = [row for row in e.parse_json(sources[capture.BUNDLE])["candidates"] if row["candidate_id"] == CANDIDATE]
    if (len(candidates) != 1 or _sha(candidates[0]["config_raw"].encode()) != CONFIG_SHA256
            or _sha(candidates[0]["files"]["extended_config.py"].encode()) != CONFIG_MODULE_SHA256): _fail()
    config = e.parse_json(candidates[0]["config_raw"].encode())
    if (config.get("arm") != "tpr_off" or config.get("candidate_id") != CANDIDATE
            or config.get("study_id") != e.STUDY_ID or config.get("freeze_sha256") != e.FREEZE_SHA256
            or config.get("input_hashes", {}).get("calendar.json") != ops.CALENDAR_SHA256): _fail()
    look = e.parse_json(sources[LOOK])
    if (look.get("schema") != "tpr-ext26-genuine-mia-look-v1" or look.get("candidate_id") != CANDIDATE
            or capture._integer(look.get("project_id"), 2**31 - 1) != PROJECT
            or capture._integer(look.get("look_ordinal"), 20) != 20
            or capture._integer(look.get("codex_attempts_consumed"), 3) != 3): _fail()
    return PRIOR_JOBS | {e._id(look["fresh_backtest_id"])}


def _plan(*, operation_id, git_head, source_hashes, owner_instruction_sha256, created_utc, expires_utc, mode="production"):
    if (type(operation_id) is not str or re.fullmatch(r"TPR-EXT26-OWNER-MIA-DISCOVERY-[A-Za-z0-9-]{1,50}", operation_id) is None
            or mode not in {"production", "offline-fixture"}): _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS): _fail()
    for identity in source_hashes.values(): e._hash(identity)
    if (source_hashes[capture.BUNDLE] != capture.BUNDLE_SHA256 or source_hashes[LOOK] != LOOK_SHA256
            or source_hashes[capture.PREFIX + "extended_study_freeze.json"] != e.FREEZE_SHA256
            or source_hashes[capture.PREFIX + "extended_calendar.json"] != ops.CALENDAR_SHA256): _fail()
    if not timedelta(0) < capture._clock(expires_utc) - capture._clock(created_utc) <= timedelta(hours=1): _fail()
    return {"schema": "tpr-ext26-owner-mia-discovery-plan-v1", "operation_id": operation_id,
        "project_id": PROJECT, "candidate_id": CANDIDATE, "study_id": e.STUDY_ID, "config_sha256": CONFIG_SHA256,
        "config_module_sha256": CONFIG_MODULE_SHA256,
        "freeze_sha256": e.FREEZE_SHA256, "calendar_sha256": ops.CALENDAR_SHA256,
        "git_head": git_head, "source_hashes": dict(source_hashes), "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created_utc, "expires_utc": expires_utc, "mode": mode,
        "endpoint": ENDPOINT, "payload": dict(PAYLOAD), "max_requests": 1, "max_response_bytes": MAX_RESPONSE,
        "max_received_bytes": MAX_RESPONSE + 1, "max_rows": MAX_ROWS, "max_seconds": MAX_SECONDS,
        "max_private_artifact_bytes": MAX_PRIVATE_ARTIFACT, "server_recent_filter_available": False,
        "new_codex_attempts": 0, "new_jobs_launched": 0, "attempt_reset": False, "automatic_retry": False,
        "source_read": False, "outcome_read_requested": False, "statistics_requested": False,
        "mia_message_or_job": False, "strategy_accepted": False, "canonical_admission": False}


def prepare_plan(**arguments):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    plan = _plan(git_head=head, source_hashes={name: _sha(raw) for name, raw in sources.items()}, **arguments)
    raw = e.canonical(plan)
    return {"plan": plan, "plan_json": raw.decode(), "plan_sha256": _sha(raw)}


def _contextual_redact(value):
    """Known profile channels only; never replace digits in job/numeric values."""
    pii = {"userId", "user_id", "ownerId", "publicId", "profileImage", "bio", "email", "firstName", "lastName", "apiToken", "api_token"}
    containers = {"user", "account", "profile", "owner", "metadata", "collaborators"}
    def walk(item, profile=False):
        if type(item) is dict:
            return {key: "[redacted]" if key in pii or profile and key in {"uid", "name", "id"}
                else walk(child, profile or key in containers) for key, child in item.items()}
        if type(item) is list: return [walk(child, profile) for child in item]
        return item
    return walk(value)


def _projection(raw, credential):
    projected = e.project_wire(raw, credential=credential)
    value = _contextual_redact(projected["projection"])
    if type(value) is not dict: _fail()
    # Retain no parameters/statistics/free text/source fields, even if the
    # server returns them despite includeStatistics=false. Original wire has
    # a hash/size only; this is intentionally a distinct metadata projection.
    response = {key: value[key] for key in ("success", "count", "projectId") if key in value}
    rows = value.get("backtests")
    unexpected = bool(set(value) & OUTCOME_FIELDS)
    if type(rows) is list:
        if len(rows) > MAX_ROWS: _fail()
        response["backtests"] = []
        for row in rows:
            if type(row) is not dict: _fail()
            unexpected = unexpected or bool(set(row) & OUTCOME_FIELDS)
            selected = {key: row[key] for key in ("backtestId", "created", "status", "progress", "snapshotId", "projectId") if key in row}
            if "name" in row:
                if type(row["name"]) is not str or len(row["name"].encode()) > 1024: _fail()
                selected.update(name_sha256=_sha(row["name"].encode()), name_bytes=len(row["name"].encode()))
            response["backtests"].append(selected)
    errors = value.get("errors")
    if errors is not None:
        if type(errors) is not list or len(errors) > MAX_ROWS or any(type(row) is not str for row in errors): _fail()
        response["error_count"] = len(errors)
        response["errors_sha256"] = _sha(e.canonical(errors))
    return {**projected, "redaction_policy": "tpr-ext26-owner-discovery-contextual-metadata-v1",
        "projection": response, "projection_sha256": _sha(e.canonical(response)),
        "unexpected_outcome_or_parameter_fields_present": unexpected,
        "raw_wire_retained": False, "outcome_parameter_source_fields_retained": False}


def _metadata(value, known):
    if value.get("success") is not True: _fail()
    rows, count = value.get("backtests"), capture._integer(value.get("count"), MAX_ROWS)
    if type(rows) is not list or len(rows) != count: _fail()
    if "projectId" in value and capture._integer(value["projectId"], 2**31 - 1) != PROJECT: _fail()
    result, seen, observed_projects = [], set(), int("projectId" in value)
    for row in rows:
        if type(row) is not dict: _fail()
        identity = e._id(row.get("backtestId"))
        if identity in seen: _fail()
        seen.add(identity)
        if "projectId" in row:
            if capture._integer(row["projectId"], 2**31 - 1) != PROJECT: _fail()
            observed_projects += 1
        created = row.get("created")
        if type(created) is not str or len(created) > 64: _fail()
        try:
            instant = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if instant.utcoffset() is None: _fail()
        except (ValueError, OverflowError): _fail()
        progress, status = row.get("progress"), row.get("status")
        if (type(progress) is not e.JsonNumber or not 0 <= progress.fraction() <= 1
                or type(status) is not str or not 0 < len(status.encode()) <= 80): _fail()
        snapshot = row.get("snapshotId")
        if snapshot is not None: capture._integer(snapshot, 2**63 - 1)
        entry = {"backtest_id": identity, "created": created, "status": status if status in STATUS else "unrecognized_status",
            "progress": progress, "snapshot_id_observed": snapshot, "known_historical_job": identity in known,
            "owner_reported_mia_attribution_verified": False, "compiled_source_proven": False,
            "name_sha256": row.get("name_sha256"), "name_bytes": row.get("name_bytes")}
        result.append((instant, identity, entry))
    result.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in result], observed_projects


def _native_request(plan, seconds, claim):
    rebuilt = _plan(**{key: plan[key] for key in ARGS})
    if (plan.get("mode") != "production" or e.canonical(plan) != e.canonical(rebuilt)
            or type(seconds) not in (int, float) or not 0 < seconds <= MAX_SECONDS): _fail()
    header = e.canonical(rebuilt)
    request = e.canonical({"endpoint": ENDPOINT, "payload": PAYLOAD, "plan_sha256": _sha(header)})
    if claim != {"bytes": len(request), "sha256": _sha(request)}: _fail()
    _guard(plan["git_head"])
    if not capture._clock(plan["created_utc"]) <= _production_clock() < capture._clock(plan["expires_utc"]): _fail()
    directory = files._directory(PRIVATE_ROOT, private=True)
    try:
        for name, raw in ((plan["operation_id"] + ".claim.spent.json", header),
                (plan["operation_id"] + ".access.json", _access(plan)),
                (plan["operation_id"] + ".read001.request.spent.json", request)):
            files._read(directory, name, expected_size=len(raw), expected_sha256=_sha(raw), remaining=MAX_RECEIPT, private=True)
    finally: os.close(directory)
    _guard(plan["git_head"])
    if not capture._clock(plan["created_utc"]) <= _production_clock() < capture._clock(plan["expires_utc"]): _fail()
    connection = None
    with ops.wall_deadline(seconds):
        user, token = ops.credential(); stamp = str(int(time.time()))
        authorization = base64.b64encode((user + ":" + _sha((token + ":" + stamp).encode())).encode()).decode()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); context.keylog_filename = None
        context.check_hostname, context.verify_mode = True, ssl.CERT_REQUIRED; context.load_default_certs()
        try:
            connection = http.client.HTTPSConnection("www.quantconnect.com", timeout=seconds, context=context)
            connection.request("POST", "/api/v2/" + ENDPOINT, body=e.canonical(PAYLOAD), headers={
                "Authorization": "Basic " + authorization, "Timestamp": stamp, "Content-Type": "application/json"})
            response = connection.getresponse()
            return response.read(MAX_RESPONSE + 1), response.status, token
        finally:
            if connection is not None: connection.close()


def _access(plan):
    return e.canonical({"plan_sha256": _sha(e.canonical(plan)), "created_utc": plan["created_utc"],
        "expires_utc": plan["expires_utc"], "endpoint": ENDPOINT, "payload": PAYLOAD, "read_only": True})


def _execute(plan, sources, root, *, guard, clock, monotonic, transport):
    if type(plan) is not dict: _fail()
    rebuilt = _plan(**{key: plan[key] for key in ARGS})
    if e.canonical(plan) != e.canonical(rebuilt): _fail()
    plan = rebuilt
    if (plan["mode"] == "production" and (root != PRIVATE_ROOT or guard is not _guard or clock is not _production_clock
            or monotonic is not time.monotonic or transport is not _native_request)
            or plan["mode"] == "offline-fixture" and (root == PRIVATE_ROOT or root.is_relative_to(LANE) or transport is _native_request)): _fail()
    known = _frozen(sources)
    started = monotonic()
    def check():
        guard(plan["git_head"]); current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0)
                or not capture._clock(plan["created_utc"]) <= current < capture._clock(plan["expires_utc"])
                or not 0 <= monotonic() - started < MAX_SECONDS
                or {name: _sha(raw) for name, raw in sources.items()} != plan["source_hashes"]): _fail()
    check(); directory = files._directory(root, private=True); lock = None
    operation = plan["operation_id"]
    report = {"schema": "tpr-ext26-owner-mia-discovery-receipt-v1", "operation_id": operation,
        "project_id": PROJECT, "candidate_id": CANDIDATE, "study_id": e.STUDY_ID, "config_sha256": CONFIG_SHA256,
        "config_module_sha256": CONFIG_MODULE_SHA256,
        "freeze_sha256": e.FREEZE_SHA256, "calendar_sha256": ops.CALENDAR_SHA256,
        "git_head": plan["git_head"], "source_hashes": plan["source_hashes"], "plan_sha256": _sha(e.canonical(plan)),
        "owner_instruction_sha256": plan["owner_instruction_sha256"], "status": "FAILED_OR_UNCERTAIN", "scope_spent": True,
        "request_attempts": 0, "received_bytes": 0, "failed_response_bytes_unknown": False,
        "request": None, "jobs": None, "unknown_job_ids": None, "observed_returned_project_fields": None,
        "unexpected_outcome_or_parameter_fields_present": None,
        "request_bound_to_fixed_project": True, "provider_authenticity_attested": False,
        "origin_attribution": "owner-reported-mia-only-not-authenticated-by-list", "compiled_source_proven": False,
        "new_codex_attempts": 0, "codex_off_attempts_consumed": 3, "new_jobs_launched": 0, "attempt_reset": False,
        "previously_recorded_looks": 20, "look_registry_updates_performed": 0,
        "newly_discovered_jobs_require_separate_attribution_and_retained_look_accounting": True,
        "winner_selected": False, "statistics_values_returned": False, "parameter_values_returned": False,
        "raw_text_returned": False, "source_read": False, "mia_message_or_job": False, "automatic_retry": False,
        "accepted_metrics": None, "economics_accepted": False, "canonical_admission": False, "trading": False}
    try:
        check(); capture._publish(directory, operation + ".claim.spent.json", e.canonical(plan))
        try:
            check(); lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600: _fail()
            check(); capture._publish(directory, operation + ".access.json", _access(plan))
            request_raw = e.canonical({"endpoint": ENDPOINT, "payload": PAYLOAD, "plan_sha256": report["plan_sha256"]})
            claim = {"bytes": len(request_raw), "sha256": _sha(request_raw)}
            check(); capture._publish(directory, operation + ".read001.request.spent.json", request_raw)
            report["request_attempts"] = 1; report["failed_response_bytes_unknown"] = True
            report["request"] = {"endpoint": ENDPOINT, "status": "failed_or_unknown", "http_status": None,
                "wire_bytes": None, "wire_sha256": None, "projection": None}
            check(); seconds = min(MAX_SECONDS, MAX_SECONDS - (monotonic() - started))
            if not 0 < seconds <= MAX_SECONDS: _fail()
            raw, status, token = transport(plan, seconds, claim)
            if type(raw) is not bytes: _fail()
            report["received_bytes"] = len(raw); report["failed_response_bytes_unknown"] = False
            report["request"]["wire_bytes"] = len(raw)
            if not 0 < len(raw) <= MAX_RESPONSE or type(status) is not int or not 100 <= status <= 599: _fail()
            report["request"]["http_status"] = status; check()
            projected = _projection(raw, token)
            report["request"]["wire_sha256"] = projected["original_wire_sha256"]
            report["unexpected_outcome_or_parameter_fields_present"] = projected["unexpected_outcome_or_parameter_fields_present"]
            private = e.canonical(projected)
            if len(private) > MAX_PRIVATE_ARTIFACT: _fail()
            check(); report["request"]["projection"] = capture._publish(directory, operation + ".read001.projection.json", private)
            if status != 200: _fail()
            jobs, observed = _metadata(projected["projection"], known)
            report.update(jobs=jobs, unknown_job_ids=[row["backtest_id"] for row in jobs if not row["known_historical_job"]],
                observed_returned_project_fields=observed)
            check(); report["request"]["status"] = "succeeded"; report["status"] = "COMPLETED_METADATA"
        except (Exception, KeyboardInterrupt): report["status"] = "FAILED_OR_UNCERTAIN"
        report["ended_utc"] = clock().isoformat(); raw_report = e.canonical(report)
        if len(raw_report) > MAX_RECEIPT: _fail()
        capture._publish(directory, operation + ".result.json", raw_report)
        return raw_report
    finally:
        if lock is not None:
            try:
                named, owned = os.stat("controller.lock", dir_fd=directory, follow_symlinks=False), os.fstat(lock)
                if (named.st_dev, named.st_ino) == (owned.st_dev, owned.st_ino): os.unlink("controller.lock", dir_fd=directory)
            except FileNotFoundError: pass
            finally: os.close(lock)
        os.close(directory)


def _production_clock(): return datetime.now(timezone.utc)


def execute_plan(plan):
    if type(plan) is not dict or plan.get("mode") != "production": _fail()
    return _execute(plan, _sources(plan["git_head"]), PRIVATE_ROOT, guard=_guard, clock=_production_clock,
        monotonic=time.monotonic, transport=_native_request)


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
        result = execute_plan(e.parse_json(raw)); print(result.decode(), end="")
        return 0 if e.parse_json(result)["status"] == "COMPLETED_METADATA" else 1
    except (Exception, KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","automatic_retry":false,"raw_text_returned":false}')
        return 1


if __name__ == "__main__": raise SystemExit(main())
