"""Fresh fixed OFF metadata list, preserving server-unzoned creation clocks.

The original executed discovery is immutable. Relative chronology is defined
within an explicit-offset or server-unzoned clock group, never across groups.
No source/results fetch, Mia attribution, winner selection or launch follows.
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

from . import extended_owner_mia_discovery as original

capture, e, ops, files = original.capture, original.e, original.ops, original.files
LANE, PRIVATE_ROOT = original.LANE, original.PRIVATE_ROOT
PROJECT, CANDIDATE = original.PROJECT, original.CANDIDATE
MODULE = capture.PREFIX + "extended_owner_mia_discovery_successor.py"
LEDGER = capture.PREFIX + "extended_owner_recovery_observations30.json"
ORIGINAL_SHA256 = "93b45e421a6fe15a52411a7bcd1ca74ce3877bec038de7f662d7e91bb664403c"
LEDGER_SHA256 = "0d42011a1a7e2c94fe9a5df948d5fa21b9a0546e7f69b8036f2532ac7073d8ef"
SOURCE_PATHS = (*original.SOURCE_PATHS, LEDGER, MODULE)
ENDPOINT, PAYLOAD = original.ENDPOINT, original.PAYLOAD
MAX_RESPONSE, MAX_ROWS, MAX_SECONDS = original.MAX_RESPONSE, original.MAX_ROWS, original.MAX_SECONDS
MAX_RECEIPT, MAX_PRIVATE_ARTIFACT = original.MAX_RECEIPT, original.MAX_PRIVATE_ARTIFACT
ARGS = original.ARGS
_projection = original._projection
_contextual_redact = original._contextual_redact


def _fail(): raise e.EvidenceError("fresh bounded own-OFF metadata successor refused; no retry")


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _guard(head):
    original._guard(head)
    if Path(__file__) != LANE / MODULE or Path(__file__).resolve() != LANE / MODULE: _fail()
    if Path(original.__file__) != LANE / original.MODULE or Path(original.__file__).resolve() != LANE / original.MODULE: _fail()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE,
            capture_output=True, timeout=5).returncode: _fail()


def _sources(head):
    result = original._sources(head)
    for relative in (LEDGER, MODULE):
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
    if type(sources) is not dict or set(sources) != set(SOURCE_PATHS): _fail()
    if _sha(sources[original.MODULE]) != ORIGINAL_SHA256 or _sha(sources[LEDGER]) != LEDGER_SHA256: _fail()
    prior = original._frozen({name: sources[name] for name in original.SOURCE_PATHS})
    ledger = e.parse_json(sources[LEDGER])
    if (ledger.get("schema") != "tpr-ext26-retrospective-owner-job-observations-v1" or ledger.get("study_id") != e.STUDY_ID
            or ledger.get("candidate_id") != CANDIDATE or capture._integer(ledger.get("project_id"), 2**31 - 1) != PROJECT
            or ledger.get("freeze_sha256") != e.FREEZE_SHA256 or ledger.get("calendar_sha256") != ops.CALENDAR_SHA256
            or ledger.get("config_sha256") != original.CONFIG_SHA256 or capture._integer(ledger.get("retained_looks_before"), 30) != 20
            or capture._integer(ledger.get("retained_looks_after"), 30) != 30 or ledger.get("attempt_reset") is not False): _fail()
    rows, historical = ledger.get("jobs"), ledger.get("known_historical_jobs")
    if type(rows) is not list or len(rows) != 10 or type(historical) is not list or len(historical) != 4 or set(historical) != prior: _fail()
    known = set(prior)
    for ordinal, row in enumerate(rows, 21):
        if type(row) is not dict or capture._integer(row.get("look_ordinal"), 30) != ordinal: _fail()
        identity = e._id(row.get("backtest_id"))
        if identity in known or row.get("compiled_source_proven") is not False or row.get("economics_accepted") is not False or row.get("accepted_metrics") is not None: _fail()
        known.add(identity)
    if len(known) != 14: _fail()
    return frozenset(known)


def _plan(*, operation_id, git_head, source_hashes, owner_instruction_sha256, created_utc, expires_utc, mode="production"):
    if (type(operation_id) is not str or re.fullmatch(r"TPR-EXT26-OWNER-MIA-DISCOVERY-SUCCESSOR-[A-Za-z0-9-]{1,50}", operation_id) is None
            or mode not in {"production", "offline-fixture"}): _fail()
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS): _fail()
    for digest in source_hashes.values(): e._hash(digest)
    if source_hashes[original.MODULE] != ORIGINAL_SHA256 or source_hashes[LEDGER] != LEDGER_SHA256: _fail()
    if not timedelta(0) < capture._clock(expires_utc) - capture._clock(created_utc) <= timedelta(minutes=15): _fail()
    prior = original._plan(operation_id="TPR-EXT26-OWNER-MIA-DISCOVERY-SUCCESSOR-BASE", git_head=git_head,
        source_hashes={name:source_hashes[name] for name in original.SOURCE_PATHS}, owner_instruction_sha256=owner_instruction_sha256,
        created_utc=created_utc, expires_utc=expires_utc, mode=mode)
    return {**prior, "schema":"tpr-ext26-owner-mia-discovery-successor-plan-v1", "operation_id":operation_id,
        "source_hashes":dict(source_hashes), "public_job_ledger_sha256":LEDGER_SHA256, "known_job_count":14,
        "previously_recorded_looks":30, "created_timezone_assumption":None,
        "creation_order_policy":"relative-within-clock-groups-only", "cross_clock_group_chronology_proven":False,
        "parameters_error_source_native_performance_read_requested":False}


def prepare_plan(**arguments):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    plan = _plan(git_head=head, source_hashes={name:_sha(raw) for name,raw in sources.items()}, **arguments)
    raw = e.canonical(plan)
    return {"plan":plan, "plan_json":raw.decode(), "plan_sha256":_sha(raw)}


def _created(value):
    if type(value) is not str or len(value.encode()) > 64: _fail()
    match = re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.(\d{1,9}))?(?:Z|[+-]\d{2}:\d{2})?", value)
    if match is None: _fail()
    try: instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError): _fail()
    fraction = e.JsonNumber("0." + (match[1] or "0")).fraction()
    aware = instant.utcoffset() is not None
    # Explicit offsets allow instant ordering. No timezone is assigned to
    # server-unzoned values; fractional precision is not truncated for order.
    ordered = instant.replace(microsecond=0)
    if aware: ordered = ordered.astimezone(timezone.utc)
    return ("explicit_offset" if aware else "server_unzoned"), (ordered, fraction), aware


def _metadata(value, known):
    if value.get("success") is not True: _fail()
    rows, count = value.get("backtests"), capture._integer(value.get("count"), MAX_ROWS)
    if type(rows) is not list or len(rows) != count: _fail()
    if "projectId" in value and capture._integer(value["projectId"], 2**31 - 1) != PROJECT: _fail()
    groups, seen, observed = {"explicit_offset":[], "server_unzoned":[]}, set(), int("projectId" in value)
    for row in rows:
        if type(row) is not dict: _fail()
        identity = e._id(row.get("backtestId"))
        if identity in seen: _fail()
        seen.add(identity)
        if "projectId" in row:
            if capture._integer(row["projectId"], 2**31 - 1) != PROJECT: _fail()
            observed += 1
        group, order, aware = _created(row.get("created"))
        progress, status = row.get("progress"), row.get("status")
        if (type(progress) is not e.JsonNumber or not 0 <= progress.fraction() <= 1
                or type(status) is not str or not 0 < len(status.encode()) <= 80): _fail()
        snapshot = row.get("snapshotId")
        if snapshot is not None: capture._integer(snapshot, 2**63 - 1)
        if "name_sha256" in row: e._hash(row["name_sha256"])
        if "name_bytes" in row: capture._integer(row["name_bytes"], 1024)
        entry = {"backtest_id":identity, "created":row["created"], "created_is_timezone_aware":aware,
            "created_clock_basis":group, "created_timezone_assumption":None,
            "status":status if status in original.STATUS else "unrecognized_status", "progress":progress,
            "snapshot_id_observed":snapshot, "known_historical_job":identity in known,
            "owner_reported_mia_attribution_verified":False, "compiled_source_proven":False,
            "name_sha256":row.get("name_sha256"), "name_bytes":row.get("name_bytes")}
        groups[group].append((order, identity, entry))
    result = []
    # Presentation group order is not a chronology between clock groups.
    for group in ("explicit_offset", "server_unzoned"):
        for rank, (_, _, entry) in enumerate(sorted(groups[group], key=lambda item:(item[0],item[1])), 1):
            result.append({**entry, "relative_creation_rank_in_clock_group":rank})
    return result, observed


def _access(plan):
    return e.canonical({"plan_sha256":_sha(e.canonical(plan)), "created_utc":plan["created_utc"],
        "expires_utc":plan["expires_utc"], "endpoint":ENDPOINT, "payload":PAYLOAD, "read_only":True,
        "public_job_ledger_sha256":LEDGER_SHA256, "metadata_only":True})


def _native_request(plan, seconds, claim):
    rebuilt = _plan(**{key:plan[key] for key in ARGS})
    if (plan.get("mode") != "production" or e.canonical(plan) != e.canonical(rebuilt)
            or type(seconds) not in (int,float) or not 0 < seconds <= MAX_SECONDS): _fail()
    header = e.canonical(rebuilt)
    request = e.canonical({"endpoint":ENDPOINT, "payload":PAYLOAD, "plan_sha256":_sha(header)})
    if claim != {"bytes":len(request), "sha256":_sha(request)}: _fail()
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
                "Authorization":"Basic " + authorization, "Timestamp":stamp, "Content-Type":"application/json"})
            response = connection.getresponse()
            return response.read(MAX_RESPONSE + 1), response.status, token
        finally:
            if connection is not None: connection.close()


def _execute(plan, sources, root, *, guard, clock, monotonic, transport):
    if type(plan) is not dict: _fail()
    rebuilt = _plan(**{key:plan[key] for key in ARGS})
    if e.canonical(plan) != e.canonical(rebuilt): _fail()
    plan = rebuilt
    if (plan["mode"] == "production" and (root != PRIVATE_ROOT or guard is not _guard or clock is not _production_clock
            or monotonic is not time.monotonic or transport is not _native_request)
            or plan["mode"] == "offline-fixture" and (root == PRIVATE_ROOT or root.is_relative_to(LANE) or transport is _native_request)): _fail()
    known = _frozen(sources); started = monotonic()
    def check():
        guard(plan["git_head"]); current = clock()
        if (type(current) is not datetime or current.utcoffset() != timedelta(0)
                or not capture._clock(plan["created_utc"]) <= current < capture._clock(plan["expires_utc"])
                or not 0 <= monotonic() - started < MAX_SECONDS
                or {name:_sha(raw) for name,raw in sources.items()} != plan["source_hashes"]): _fail()
    check(); directory = files._directory(root, private=True); lock = None; operation = plan["operation_id"]
    report = {"schema":"tpr-ext26-owner-mia-discovery-successor-receipt-v1", "operation_id":operation,
        "project_id":PROJECT, "candidate_id":CANDIDATE, "study_id":e.STUDY_ID, "config_sha256":original.CONFIG_SHA256,
        "freeze_sha256":e.FREEZE_SHA256, "calendar_sha256":ops.CALENDAR_SHA256, "git_head":plan["git_head"],
        "source_hashes":plan["source_hashes"], "plan_sha256":_sha(e.canonical(plan)), "owner_instruction_sha256":plan["owner_instruction_sha256"],
        "status":"FAILED_OR_UNCERTAIN", "scope_spent":True, "request_attempts":0, "received_bytes":0,
        "failed_response_bytes_unknown":False, "request":None, "jobs":None, "unknown_job_ids":None,
        "observed_returned_project_fields":None, "unexpected_outcome_or_parameter_fields_present":None,
        "known_job_ids":sorted(known), "previously_recorded_looks":30, "public_job_ledger_sha256":LEDGER_SHA256,
        "creation_order_policy":"relative-within-clock-groups-only", "cross_clock_group_chronology_proven":False,
        "created_timezone_assumption":None, "creation_clock_groups_observed":None,
        "request_bound_to_fixed_project":True, "provider_authenticity_attested":False,
        "origin_attribution":"owner-reported-mia-only-not-authenticated-by-list", "compiled_source_proven":False,
        "new_codex_attempts":0, "codex_off_attempts_consumed":3, "new_jobs_launched":0, "attempt_reset":False,
        "look_registry_updates_performed":0, "newly_discovered_jobs_require_separate_attribution_and_retained_look_accounting":True,
        "winner_selected":False, "statistics_values_returned":False, "parameter_values_returned":False,
        "error_source_native_performance_bodies_returned":False, "raw_text_returned":False, "source_read":False,
        "mia_message_or_job":False, "automatic_retry":False, "accepted_metrics":None,
        "economics_accepted":False, "canonical_admission":False, "trading":False}
    try:
        check(); capture._publish(directory, operation + ".claim.spent.json", e.canonical(plan))
        try:
            check(); lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600: _fail()
            check(); capture._publish(directory, operation + ".access.json", _access(plan))
            request_raw = e.canonical({"endpoint":ENDPOINT, "payload":PAYLOAD, "plan_sha256":report["plan_sha256"]})
            claim = {"bytes":len(request_raw), "sha256":_sha(request_raw)}
            check(); capture._publish(directory, operation + ".read001.request.spent.json", request_raw)
            report["request_attempts"] = 1; report["failed_response_bytes_unknown"] = True
            report["request"] = {"endpoint":ENDPOINT, "status":"failed_or_unknown", "http_status":None,
                "wire_bytes":None, "wire_sha256":None, "projection":None}
            check(); seconds = min(MAX_SECONDS, MAX_SECONDS - (monotonic() - started))
            if not 0 < seconds <= MAX_SECONDS: _fail()
            raw, status, token = transport(plan, seconds, claim)
            if type(raw) is not bytes: _fail()
            report["received_bytes"] = len(raw); report["failed_response_bytes_unknown"] = False
            report["request"]["wire_bytes"] = len(raw)
            if not 0 < len(raw) <= MAX_RESPONSE or type(status) is not int or not 100 <= status <= 599: _fail()
            report["request"]["http_status"] = status; check(); projected = _projection(raw, token)
            report["request"]["wire_sha256"] = projected["original_wire_sha256"]
            report["unexpected_outcome_or_parameter_fields_present"] = projected["unexpected_outcome_or_parameter_fields_present"]
            private = e.canonical(projected)
            if len(private) > MAX_PRIVATE_ARTIFACT: _fail()
            check(); report["request"]["projection"] = capture._publish(directory, operation + ".read001.projection.json", private)
            if status != 200: _fail()
            jobs, observed = _metadata(projected["projection"], known)
            report.update(jobs=jobs, unknown_job_ids=[row["backtest_id"] for row in jobs if not row["known_historical_job"]],
                observed_returned_project_fields=observed, creation_clock_groups_observed=sorted({row["created_clock_basis"] for row in jobs}))
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
                if (named.st_dev,named.st_ino) == (owned.st_dev,owned.st_ino): os.unlink("controller.lock", dir_fd=directory)
            except FileNotFoundError: pass
            finally: os.close(lock)
        os.close(directory)


def _production_clock(): return datetime.now(timezone.utc)


def execute_plan(plan):
    if type(plan) is not dict or plan.get("mode") != "production": _fail()
    return _execute(plan, _sources(plan["git_head"]), PRIVATE_ROOT, guard=_guard, clock=_production_clock,
        monotonic=time.monotonic, transport=_native_request)


def execute_fixture(plan, sources, root, *, clock, transport, guard=lambda _:None, monotonic=lambda:0.0):
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
    except (Exception,KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","automatic_retry":false,"raw_text_returned":false}')
        return 1


if __name__ == "__main__": raise SystemExit(main())
