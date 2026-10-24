"""One fixed captured metadata projection; never API, source or outcome access."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import time

from . import extended_mia_capture as capture

e, files = capture.e, capture.files
LANE, PRIVATE_ROOT = capture.LANE, capture.PRIVATE_ROOT
MODULE = capture.PREFIX + "extended_owner_mia_metadata_inspect.py"
SOURCE_PATHS = (*capture.SOURCE_PATHS, MODULE)
OPERATION = "TPR-EXT26-OWNER-MIA-META-INSPECT-20261013-001"
NAME = "TPR-EXT26-OWNER-MIA-DISCOVERY-20261013-001.read001.projection.json"
BYTES = 4138
SHA256 = "8cfb978f0145186d18ae71fdb347da0b45d876475c72cd9046e3aa47260c3239"
MAX_SECONDS = 30
ARGS = ("git_head", "source_hashes", "owner_instruction_sha256", "created_utc", "expires_utc", "mode", "fixture_descriptor")
OUTER = frozenset(("schema", "redaction_policy", "original_wire_sha256", "original_wire_bytes", "projection_sha256", "projection",
    "unexpected_outcome_or_parameter_fields_present", "raw_wire_retained", "outcome_parameter_source_fields_retained"))
TOP = frozenset(("success", "count", "projectId", "backtests", "error_count", "errors_sha256"))
ROW = frozenset(("backtestId", "created", "status", "progress", "snapshotId", "projectId", "name_sha256", "name_bytes"))
STATUSES = frozenset(("Completed", "Completed.", "Runtime Error", "Error", "Stopped", "Cancelled", "In Queue...", "In Progress...", "Running"))


def _fail():
    raise e.EvidenceError("fixed owner-Mia metadata inspection refused; no retry")


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _guard(head):
    capture._guard(head)
    if Path(__file__) != LANE / MODULE or Path(__file__).resolve() != LANE / MODULE: _fail()
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS], cwd=LANE,
            capture_output=True, timeout=5).returncode: _fail()


def _sources(head):
    result = capture._sources(head); _guard(head)
    committed = subprocess.run(["git", "show", head + ":" + MODULE], cwd=LANE, capture_output=True, timeout=5, check=True).stdout
    directory = files._directory((LANE / MODULE).parent, private=False)
    try:
        _guard(head)
        result[MODULE] = files._read(directory, Path(MODULE).name, expected_size=len(committed),
            expected_sha256=_sha(committed), remaining=capture.MAX_RESPONSE, private=False)
    finally: os.close(directory)
    _guard(head)
    return result


def _plan(*, git_head, source_hashes, owner_instruction_sha256, created_utc, expires_utc, mode="production", fixture_descriptor=None):
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    if mode not in {"production", "offline-fixture"} or type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS): _fail()
    for identity in source_hashes.values(): e._hash(identity)
    if (source_hashes[capture.BUNDLE] != capture.BUNDLE_SHA256
            or source_hashes[capture.PREFIX + "extended_study_freeze.json"] != e.FREEZE_SHA256
            or source_hashes[capture.PREFIX + "extended_calendar.json"] != capture.ops.CALENDAR_SHA256): _fail()
    if not timedelta(0) < capture._clock(expires_utc) - capture._clock(created_utc) <= timedelta(minutes=15): _fail()
    descriptor = {"bytes": BYTES, "sha256": SHA256}
    if mode == "production":
        if fixture_descriptor is not None: _fail()
    else:
        e._closed(fixture_descriptor, {"bytes", "sha256"})
        size = capture._integer(fixture_descriptor["bytes"], BYTES)
        if not size: _fail()
        descriptor = {"bytes": size, "sha256": e._hash(fixture_descriptor["sha256"])}
        fixture_descriptor = descriptor
    return {"schema": "tpr-ext26-owner-mia-metadata-inspect-plan-v1", "operation_id": OPERATION,
        "git_head": git_head, "source_hashes": dict(source_hashes), "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created_utc, "expires_utc": expires_utc, "mode": mode, "fixture_descriptor": fixture_descriptor,
        "name": NAME, "descriptor": descriptor, "max_reads": 1, "max_seconds": MAX_SECONDS,
        "api_requests": 0, "new_jobs": 0, "new_codex_attempts": 0, "automatic_retry": False}


def prepare_plan(**arguments):
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE: _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    plan = _plan(git_head=head, source_hashes={name: _sha(raw) for name, raw in sources.items()}, **arguments)
    raw = e.canonical(plan)
    return {"plan": plan, "plan_json": raw.decode(), "plan_sha256": _sha(raw)}


def _kind(value):
    return "number" if type(value) is e.JsonNumber else {bool: "boolean", str: "string", list: "list", dict: "object", type(None): "null"}.get(type(value), "unsupported")


def _number(value, maximum):
    if type(value) is e.JsonNumber and value.fraction().denominator == 1 and 0 <= value.fraction() <= maximum: return value
    return None


def _inspect(raw):
    outer = e.parse_json(raw); e._closed(outer, OUTER)
    if (outer["schema"] != "tpr-ext26-wire-projection-v1"
            or outer["redaction_policy"] != "tpr-ext26-owner-discovery-contextual-metadata-v1"
            or outer["raw_wire_retained"] is not False or outer["outcome_parameter_source_fields_retained"] is not False
            or type(outer["unexpected_outcome_or_parameter_fields_present"]) is not bool): _fail()
    wire_hash = e._hash(outer["original_wire_sha256"])
    wire_bytes = capture._integer(outer["original_wire_bytes"], 1024 * 1024)
    value = outer["projection"]
    if type(value) is not dict or not set(value) <= TOP or _sha(e.canonical(value)) != e._hash(outer["projection_sha256"]): _fail()
    rows = value.get("backtests")
    if type(rows) is not list or len(rows) > 128: _fail()
    if "projectId" in value and capture._integer(value["projectId"], 2**31 - 1) != capture.PROJECT: _fail()
    jobs = []
    for row in rows:
        if type(row) is not dict or not set(row) <= ROW: _fail()
        if "projectId" in row and capture._integer(row["projectId"], 2**31 - 1) != capture.PROJECT: _fail()
        identity = e._id(row.get("backtestId"))
        created = row.get("created"); instant = None
        if type(created) is str:
            if len(created.encode()) > 64: _fail()
            try: instant = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except (ValueError, OverflowError): pass
        status = row.get("status")
        progress = row.get("progress")
        numeric_progress = type(progress) is e.JsonNumber
        if "name_sha256" in row: e._hash(row["name_sha256"])
        if "name_bytes" in row: capture._integer(row["name_bytes"], 1024)
        jobs.append({"backtestId": identity, "created": created if instant is not None else None,
            "created_field_type": _kind(created), "created_parseable": instant is not None,
            "created_sha256": _sha(created.encode()) if type(created) is str else None,
            "created_bytes": len(created.encode()) if type(created) is str else None,
            "created_is_timezone_aware": instant.utcoffset() is not None if instant is not None else False,
            "status": status if type(status) is str and status in STATUSES else "unrecognized_status",
            "progress": progress if numeric_progress else None, "progress_field_type": _kind(progress),
            "progress_within_unit_bounds": numeric_progress and 0 <= progress.fraction() <= 1,
            "snapshotId": _number(row.get("snapshotId"), 2**63 - 1), "projectId": row.get("projectId"),
            "name_sha256": row.get("name_sha256"), "name_bytes": row.get("name_bytes")})
    return {"wire_sha256": wire_hash, "wire_bytes": wire_bytes, "raw_wire_independently_reopened": False,
        "projection_sha256": outer["projection_sha256"], "success": value.get("success") is True,
        "count": value.get("count") if type(value.get("count")) is e.JsonNumber else None,
        "count_within_whole_row_bounds": _number(value.get("count"), 128) is not None,
        "count_field_type": _kind(value.get("count")),
        "count_field_present": "count" in value, "projectId": value.get("projectId"), "jobs": jobs,
        "returned_rows": len(jobs), "unexpected_outcome_or_parameter_fields_present": outer["unexpected_outcome_or_parameter_fields_present"],
        "discovery_metadata_accepted": False, "mia_attribution_verified": False, "compiled_source_proven": False,
        "accepted_metrics": None, "attempt_reset": False, "canonical_admission": False, "trading": False}


def _execute(plan, sources, root, *, guard, clock, monotonic):
    if type(plan) is not dict: _fail()
    rebuilt = _plan(**{key: plan[key] for key in ARGS})
    if e.canonical(plan) != e.canonical(rebuilt): _fail()
    plan = rebuilt
    if (plan["mode"] == "production" and (root != PRIVATE_ROOT or guard is not _guard or clock is not _now or monotonic is not time.monotonic)
            or plan["mode"] == "offline-fixture" and (root == PRIVATE_ROOT or root.is_relative_to(LANE))): _fail()
    started = monotonic()
    def check():
        guard(plan["git_head"]); now = clock()
        if (type(now) is not datetime or now.utcoffset() != timedelta(0)
                or not capture._clock(plan["created_utc"]) <= now < capture._clock(plan["expires_utc"])
                or not 0 <= monotonic() - started < MAX_SECONDS
                or {name: _sha(raw) for name, raw in sources.items()} != plan["source_hashes"]): _fail()
    check(); directory = files._directory(root, private=True); lock = None
    report = {"schema": "tpr-ext26-owner-mia-metadata-inspect-receipt-v1", "operation_id": OPERATION,
        "git_head": plan["git_head"], "plan_sha256": _sha(e.canonical(plan)), "status": "FAILED_OR_UNCERTAIN",
        "scope_spent": True, "private_read_attempts": 0, "private_read_bytes": 0, "diagnostic": None,
        "api_requests": 0, "new_jobs": 0, "new_codex_attempts": 0, "automatic_retry": False,
        "accepted_metrics": None, "mia_attribution_verified": False, "canonical_admission": False, "trading": False}
    try:
        check(); capture._publish(directory, OPERATION + ".claim.spent.json", e.canonical(plan))
        try:
            check(); lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            info = os.fstat(lock)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600: _fail()
            check(); capture._publish(directory, OPERATION + ".access.json", e.canonical({"plan_sha256": report["plan_sha256"],
                "created_utc": plan["created_utc"], "expires_utc": plan["expires_utc"], "name": NAME,
                "descriptor": plan["descriptor"], "max_reads": 1, "read_only": True}))
            check(); report["private_read_attempts"] = 1
            descriptor = plan["descriptor"]
            raw = files._read(directory, NAME, expected_size=descriptor["bytes"], expected_sha256=descriptor["sha256"],
                remaining=descriptor["bytes"], private=True)
            report["private_read_bytes"] = len(raw); check()
            report["diagnostic"] = _inspect(raw); check(); report["status"] = "COMPLETED_DIAGNOSTIC_INSPECTION"
        except (Exception, KeyboardInterrupt): report["status"] = "FAILED_OR_UNCERTAIN"
        report["ended_utc"] = clock().isoformat(); raw = e.canonical(report)
        if len(raw) > 256 * 1024: _fail()
        capture._publish(directory, OPERATION + ".result.json", raw)
        return raw
    finally:
        if lock is not None:
            try:
                named, owned = os.stat("controller.lock", dir_fd=directory, follow_symlinks=False), os.fstat(lock)
                if (named.st_dev, named.st_ino) == (owned.st_dev, owned.st_ino): os.unlink("controller.lock", dir_fd=directory)
            except FileNotFoundError: pass
            finally: os.close(lock)
        os.close(directory)


def _now(): return datetime.now(timezone.utc)


def execute_plan(plan):
    if type(plan) is not dict or plan.get("mode") != "production": _fail()
    return _execute(plan, _sources(plan["git_head"]), PRIVATE_ROOT, guard=_guard, clock=_now, monotonic=time.monotonic)


def execute_fixture(plan, sources, root, *, clock, guard=lambda _: None, monotonic=lambda: 0.0):
    if type(plan) is not dict or plan.get("mode") != "offline-fixture": _fail()
    return _execute(plan, sources, root, guard=guard, clock=clock, monotonic=monotonic)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", required=True); parser.add_argument("--plan-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        raw = args.plan_json.encode()
        if _sha(raw) != e._hash(args.plan_sha256): _fail()
        result = execute_plan(e.parse_json(raw)); print(result.decode(), end="")
        return 0 if e.parse_json(result)["status"] == "COMPLETED_DIAGNOSTIC_INSPECTION" else 1
    except (Exception, KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","automatic_retry":false,"raw_text_returned":false}')
        return 1


if __name__ == "__main__": raise SystemExit(main())
