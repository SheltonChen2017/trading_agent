"""Named, bounded OFF2/OFF3 frontier diagnosis; no candidate mutation or launch.

Two separately claimed scopes read the exact retained terminal envelopes or
fetch only unfiltered native logs for the two fixed, failed OFF jobs. Private
wires remain owner-only. Public outputs are closed dates/counts/frames/enums,
never statistics values, raw logs, licensed identities or a causal conclusion.
Cooperative POSIX custody is not Windows ACL/protected-parent proof.
"""
from __future__ import annotations

import argparse
import base64
from datetime import date, datetime, timedelta, timezone
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

from . import extended_evidence as e, extended_operations as ops

LANE, BRANCH, PRIVATE_ROOT = ops.LANE, ops.BRANCH, ops.PRIVATE_ROOT
PREFIX = "research/target_price_revisions_qc/"
SOURCE_RELATIVE = PREFIX + "extended_frontier_diagnostic.py"
SOURCE_PATHS = (SOURCE_RELATIVE, PREFIX + "extended_evidence.py",
    PREFIX + "extended_operations.py", "research/__init__.py", PREFIX + "__init__.py",
    PREFIX + "extended_study_freeze.json", PREFIX + "extended_calendar.json")
FREEZE_SHA256 = e.FREEZE_SHA256
CALENDAR_SHA256 = ops.CALENDAR_SHA256
BASELINE = "ad5af50612b80afb5e20e928f0b44adbbecc117f"
PROJECT = 37650980
CANDIDATE = "TPR-CAP-TILT-EXT26-OFF-BASE-v1"
TERMINALS = (
    (2, "f79d3ff02644ec81f20da5cc6ca7440a", 1299525,
     "11d6db1fbdf381653897c317d80a083527d9e925a57ba591486c673dc2697173"),
    (3, "d7c76b7c4936c814f125a2b9a8cc2896", 1301513,
     "b5f7788177d117dd4dc95ae53c84cf6b60a15fc7410f5877b332743e618e7417"))
MAX_RESPONSE = 1024 * 1024
MAX_PAGES, PAGE_LINES, MAX_REQUESTS = 20, 200, 40
MAX_TERMINAL_BYTES = sum(row[2] for row in TERMINALS)
MAX_LOG_BYTES = MAX_REQUESTS * MAX_RESPONSE
STATISTICS = ("Start Equity", "End Equity", "Total Orders", "Total Fees",
    "Drawdown", "Net Profit", "Total Trades")
ERROR_TYPES = frozenset(("AttributeError", "TypeError", "NameError", "ImportError",
    "ModuleNotFoundError", "KeyError", "ValueError", "RuntimeError", "SyntaxError",
    "MemoryError", "TimeoutError", "NotSupportedException", "InvalidOperationException"))
FRAME_FILES = ("main.py", "extended_core.py", "extended_loader.py",
    "extended_compressed_store.py", "extended_runtime_successor.py",
    "extended_completion_successor.py")
MARKERS = {
    "data_exhaustion": r"end of data|data feed.{0,60}exhaust|no more data|all subscriptions.{0,60}finished",
    "stop_or_cancel": r"\bquit\b|algorithm.{0,60}stopp|\bcancel(?:led|ed|ing)\b",
    "runtime_error": r"runtime error|\bexception\b|traceback",
    "time_limit": r"time limit|\btimeout\b|maximum.{0,60}runtime|exceeded.{0,60}time",
    "audit_export": r"save_bytes|object\s*store|compressed.{0,60}audit|chunk.{0,60}(?:write|save)",
    "evidence_bound": r"private evidence run bound|subscription bound|history bound",
    "memory": r"out of memory|\bMemoryError\b"}
_FIELDS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink", "st_mode", "st_uid")
_ARGS = ("action", "operation_id", "source_hashes", "git_head", "owner_instruction_sha256",
    "created_utc", "expires_utc", "mode")
Refusal = e.EvidenceError


def _fail():
    raise Refusal("bounded fixed-job frontier diagnosis refused; no automatic retry")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _clock(value):
    if type(value) is not str or len(value) > 64:
        _fail()
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail()
    if result.utcoffset() != timedelta(0):
        _fail()
    return result


def _integer(value, maximum=2**31 - 1):
    if type(value) is e.JsonNumber and value.fraction().denominator == 1:
        value = int(value.fraction())
    if type(value) is not int or not 0 <= value <= maximum:
        _fail()
    return value


def _guard(head):
    e._hash(head, 40)
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE:
        _fail()
    def git(*args):
        return subprocess.run(["git", *args], cwd=LANE, capture_output=True,
            text=True, timeout=5, check=True).stdout.strip()
    physical = Path.cwd().resolve()
    top, branch, actual = git("rev-parse", "--show-toplevel"), git("branch", "--show-current"), git("rev-parse", "HEAD")
    git("status", "--short")  # Inspect, preserve and do not silently consume concurrent work.
    if physical != LANE or top != str(LANE) or branch != BRANCH or actual != head:
        _fail()
    if subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE, head],
            cwd=LANE, capture_output=True, timeout=5).returncode:
        _fail()
    if subprocess.run(["git", "check-ignore", "-q", str(PRIVATE_ROOT)],
            cwd=LANE, capture_output=True, timeout=5).returncode:
        _fail()


def _directory(path, *, private):
    if not isinstance(path, Path) or path.resolve() != path:
        _fail()
    fd = None
    try:
        # Open every component without following a swapped/symlinked parent.
        fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        accumulated = Path(path.anchor)
        for component in path.parts[1:]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = next_fd
            accumulated /= component
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode):
                _fail()
            if private and (accumulated == ops.PRIVATE_PARENT or accumulated.is_relative_to(ops.PRIVATE_PARENT)):
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    _fail()
        if private:
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                _fail()
        return fd
    except Exception:
        if fd is not None:
            os.close(fd)
        _fail()


def _read(directory, name, *, expected_size, expected_sha256, remaining, private):
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,220}", name) is None or expected_size > remaining:
        _fail()
    fd = None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid()
                or before.st_size != expected_size or before.st_size > remaining
                or private and stat.S_IMODE(before.st_mode) != 0o600
                or any(getattr(before, field) != getattr(named, field) for field in _FIELDS)):
            _fail()
        pieces, left = [], expected_size
        while left:
            part = os.read(fd, min(65536, left))
            if not part or len(part) > left:
                _fail()
            pieces.append(part); left -= len(part)
        if os.read(fd, 1):
            _fail()
        after, named_after = os.fstat(fd), os.stat(name, dir_fd=directory, follow_symlinks=False)
        if any(getattr(before, field) != getattr(after, field) or getattr(before, field) != getattr(named_after, field) for field in _FIELDS):
            _fail()
        raw = b"".join(pieces)
        if _sha(raw) != expected_sha256:
            _fail()
        return raw
    finally:
        if fd is not None:
            os.close(fd)


def _publish(directory, name, raw):
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,220}", name) is None or type(raw) is not bytes or len(raw) > 2 * MAX_RESPONSE:
        _fail()
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            _fail()
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:])
            if not count:
                _fail()
            offset += count
        os.fsync(fd)
    finally:
        os.close(fd)


def _sources(head):
    _guard(head)
    if Path(__file__) != LANE / SOURCE_RELATIVE or Path(e.__file__) != LANE / (PREFIX + "extended_evidence.py") or Path(ops.__file__) != LANE / (PREFIX + "extended_operations.py"):
        _fail()
    sources = {}
    for name in SOURCE_PATHS:
        _guard(head)
        committed = subprocess.run(["git", "show", head + ":" + name], cwd=LANE,
            capture_output=True, timeout=5, check=True).stdout
        if not 0 <= len(committed) <= MAX_RESPONSE:
            _fail()
        directory = _directory((LANE / name).parent, private=False)
        try:
            _guard(head)
            sources[name] = _read(directory, Path(name).name, expected_size=len(committed),
                expected_sha256=_sha(committed), remaining=MAX_RESPONSE, private=False)
        finally:
            os.close(directory)
    if (_sha(sources[PREFIX + "extended_study_freeze.json"]) != FREEZE_SHA256
            or _sha(sources[PREFIX + "extended_calendar.json"]) != CALENDAR_SHA256):
        _fail()
    _guard(head)
    return sources


def _plan(*, action, operation_id, source_hashes, git_head, owner_instruction_sha256,
          created_utc, expires_utc, mode="production"):
    prefix = "TPR-EXT26-FRONTIER-" if action == "terminals" else "TPR-EXT26-ENGINE-LOG-" if action == "logs" else None
    if (prefix is None or type(operation_id) is not str
            or re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9-]{1,64}", operation_id) is None
            or mode not in {"production", "offline-fixture"} or type(source_hashes) is not dict
            or set(source_hashes) != set(SOURCE_PATHS)):
        _fail()
    for identity in source_hashes.values():
        e._hash(identity)
    if (source_hashes[PREFIX + "extended_study_freeze.json"] != FREEZE_SHA256
            or source_hashes[PREFIX + "extended_calendar.json"] != CALENDAR_SHA256):
        _fail()
    e._hash(git_head, 40); e._hash(owner_instruction_sha256)
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not created < expires <= created + timedelta(hours=4):
        _fail()
    return {"schema": "tpr-ext26-frontier-diagnostic-plan-v1", "action": action,
        "operation_id": operation_id, "source_hashes": dict(source_hashes), "git_head": git_head,
        "owner_instruction_sha256": owner_instruction_sha256, "created_utc": created_utc,
        "expires_utc": expires_utc, "mode": mode, "study_id": e.STUDY_ID,
        "freeze_sha256": FREEZE_SHA256, "calendar_sha256": CALENDAR_SHA256,
        "project_id": PROJECT, "candidate_id": CANDIDATE,
        "terminals": [{"attempt": attempt, "job_id": job, "bytes": size, "sha256": digest,
            "name": CANDIDATE + ".attempt." + str(attempt) + ".terminal.json"}
            for attempt, job, size, digest in TERMINALS],
        "endpoint": "backtests/read/log" if action == "logs" else None,
        "query": "", "page_lines": PAGE_LINES, "max_pages_per_job": MAX_PAGES,
        "max_requests": MAX_REQUESTS if action == "logs" else 0,
        "max_response_bytes": MAX_RESPONSE, "max_body_bytes": MAX_LOG_BYTES if action == "logs" else MAX_TERMINAL_BYTES,
        "max_seconds": 1500 if action == "logs" else 30, "request_seconds": 30,
        "statistic_equality_fields": list(STATISTICS), "new_looks": 0, "quantconnect_attempts": 0,
        "automatic_retry": False, "old_claims_renewed": False, "cause_proved": False,
        "canonical_admission": False, "trading": False}


def prepare_plan(**arguments):
    """Public committed bytes only; does not read a terminal, log or credential."""
    if Path.cwd() != LANE or Path.cwd().resolve() != LANE:
        _fail()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=LANE, capture_output=True,
        text=True, timeout=5, check=True).stdout.strip()
    sources = _sources(head)
    return _plan(source_hashes={name: _sha(raw) for name, raw in sources.items()},
        git_head=head, mode="production", **arguments)


def _identity(value, job):
    if type(value) is not dict:
        _fail()
    present = {"project": False, "job": False}
    for row in (value, value.get("backtest")):
        if row is None:
            continue
        if type(row) is not dict:
            _fail()
        for name in ("projectId", "project_id"):
            if name in row:
                if _integer(row[name]) != PROJECT:
                    _fail()
                present["project"] = True
        for name in ("backtestId", "backtest_id"):
            if name in row:
                if type(row[name]) is not str or row[name] != job:
                    _fail()
                present["job"] = True
    return {"request_bound_to_fixed_job": True, "returned_project_present_and_matching": present["project"],
        "returned_job_present_and_matching": present["job"], "provider_authenticity_attested": False}


def _text_diagnostic(strings):
    dates, errors, frames = set(), set(), set()
    markers = {name: 0 for name in MARKERS}
    for text in strings:
        if type(text) is not str or len(text.encode("utf-8")) > MAX_RESPONSE:
            _fail()
        for token in re.findall(r"\b20[0-9]{2}-[0-9]{2}-[0-9]{2}\b", text):
            try:
                date.fromisoformat(token)
            except ValueError:
                continue
            dates.add(token)
        errors.update(name for name in ERROR_TYPES if re.search(r"\b" + name + r"\b", text))
        for file, line in re.findall(r"\b(" + "|".join(map(re.escape, FRAME_FILES)) + r")\b[^\n]{0,40}?\b(?:line\s+|:)([1-9][0-9]{0,5})\b", text):
            frames.add((file, int(line)))
        for name, pattern in MARKERS.items():
            markers[name] += bool(re.search(pattern, text, re.I))
    ordered = sorted(dates)
    return {"date_token_census": {"distinct_count": len(ordered), "first": ordered[0] if ordered else None,
        "last": ordered[-1] if ordered else None, "tokens": ordered[:128], "tokens_complete": len(ordered) <= 128},
        "known_error_types": sorted(errors), "code_frames": [{"file": file, "line": line} for file, line in sorted(frames)[:64]],
        "code_frames_complete": len(frames) <= 64, "keyword_line_counts": markers,
        "cause_proved": False, "raw_text_returned": False}


def _terminal(raw, expected, calendar):
    request, response = e._envelope(raw, {"projectId", "backtestId"}, "backtests/read")
    if _integer(request["projectId"]) != PROJECT or request["backtestId"] != expected["job_id"]:
        _fail()
    identity = _identity(response, expected["job_id"])
    if response.get("success") is not True or type(response.get("backtest")) is not dict:
        _fail()
    backtest = response["backtest"]
    if (backtest.get("backtestId") != expected["job_id"] or backtest.get("completed") is not True
            or backtest.get("status") != "Runtime Error" or type(backtest.get("error")) is not str or not backtest["error"]):
        _fail()
    rolling = backtest.get("rollingWindow")
    if type(rolling) is not dict or len(rolling) > 4096:
        _fail()
    frontier_dates, unrecognized = set(), 0
    for key in rolling:
        match = re.fullmatch(r"M[1-9][0-9]?_(20[0-9]{6})", key)
        if match is None:
            unrecognized += 1
            continue
        try:
            frontier_dates.add(datetime.strptime(match.group(1), "%Y%m%d").date().isoformat())
        except ValueError:
            _fail()
    frontier = max(frontier_dates) if frontier_dates else None
    statistics = backtest.get("statistics")
    if type(statistics) is not dict:
        _fail()
    selected = {}
    for field in STATISTICS:
        if field in statistics:
            value = statistics[field]
            if type(value) not in (str, e.JsonNumber) or type(value) is str and (not value or len(value) > 256):
                _fail()
            selected[field] = value
    valuations = calendar["valuation_sessions"]
    observed = {"attempt": expected["attempt"], "job_id": expected["job_id"],
        "exact_terminal_sha256_verified": True, "schema_and_stage_match": True,
        "request_response_identity": identity,
        "runtime_error_terminal": True, "private_error_bytes": len(backtest["error"].encode("utf-8")),
        "private_error_sha256": _sha(backtest["error"].encode("utf-8")),
        "error_diagnostic": _text_diagnostic([backtest["error"]]),
        "rolling_key_census": {"total": len(rolling), "recognized": len(rolling) - unrecognized,
            "unrecognized": unrecognized, "last_date_token": frontier,
            "frozen_valuation_sessions_through_frontier": sum(day <= frontier for day in valuations) if frontier else None,
            "frozen_valuation_sessions": len(valuations), "frontier_proves_engine_end_or_cause": False},
        "tradeable_dates": _integer(backtest["tradeableDates"]) if "tradeableDates" in backtest else None,
        "statistic_values_returned": False, "performance_accepted": False}
    return observed, selected


def _secret_free(raw, user, token):
    projected = e.project_wire(raw, credential=token)
    value = projected["projection"]
    def scrub(item):
        if type(item) is str:
            if user and user in item:
                _fail()
            return re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[redacted-email]", item)
        if type(item) is dict:
            if user and any(user in key for key in item):
                _fail()
            return {key: "[redacted]" if key in {"userId", "user_id", "uid", "ownerId", "publicId", "profileImage", "bio"}
                else scrub(child) for key, child in item.items()}
        if type(item) is list:
            return [scrub(child) for child in item]
        return item
    redacted = scrub(value)
    return {**projected, "projection": redacted, "projection_sha256": _sha(e.canonical(redacted)),
        "additional_log_redaction": "known-profile-fields-email-and-user-text-refusal-v1"}


def _native_request(payload):
    raw = e.canonical(payload)
    connection = None
    with ops.wall_deadline(30):
        user, token = ops.credential()
        stamp = str(int(time.time()))
        signed = hashlib.sha256((token + ":" + stamp).encode()).hexdigest()
        authorization = base64.b64encode((user + ":" + signed).encode()).decode()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.keylog_filename = None
        context.check_hostname, context.verify_mode = True, ssl.CERT_REQUIRED
        context.load_default_certs()
        try:
            connection = http.client.HTTPSConnection("www.quantconnect.com", timeout=30, context=context)
            connection.request("POST", "/api/v2/backtests/read/log", body=raw, headers={
                "Authorization": "Basic " + authorization, "Timestamp": stamp, "Content-Type": "application/json"})
            response = connection.getresponse()
            body = response.read(MAX_RESPONSE + 1)
            return body, response.status, user, token
        finally:
            if connection is not None:
                connection.close()


def _execute(plan, sources, root, *, guard, clock, monotonic, transport):
    expected = _plan(**{name: plan[name] for name in _ARGS})
    if e.canonical(expected) != e.canonical(plan):
        _fail()
    if (plan["mode"] == "production" and (root != PRIVATE_ROOT or transport is not _native_request)
            or plan["mode"] == "offline-fixture" and (root == PRIVATE_ROOT or root.is_relative_to(LANE) or transport is _native_request)):
        _fail()
    started = monotonic()
    def check():
        guard(plan["git_head"])
        if (not _clock(plan["created_utc"]) <= clock() < _clock(plan["expires_utc"])
                or monotonic() - started >= plan["max_seconds"]
                or {name: _sha(raw) for name, raw in sources.items()} != plan["source_hashes"]):
            _fail()
    check()
    calendar = json.loads(sources[PREFIX + "extended_calendar.json"])
    if _sha(sources[PREFIX + "extended_calendar.json"]) != CALENDAR_SHA256:
        _fail()
    directory = _directory(root, private=True)
    lock = None
    operation, report = plan["operation_id"], None
    try:
        check(); _publish(directory, operation + ".claim.spent.json", e.canonical(plan))
        report = {"schema": "tpr-ext26-frontier-diagnostic-receipt-v1", "operation_id": operation,
            "action": plan["action"], "plan_sha256": _sha(e.canonical(plan)), "git_head": plan["git_head"],
            "source_hashes": plan["source_hashes"], "owner_instruction_sha256": plan["owner_instruction_sha256"],
            "status": "FAILED_OR_UNCERTAIN", "scope_spent": True, "read_bytes": 0, "read_attempts": 0,
            "failed_read_body_bytes_unknown": False, "requests": [], "jobs": [], "statistic_equality": None,
            "all_log_pages_observed": False, "new_looks": 0, "quantconnect_attempts": 0,
            "licensed_input_reads": 0, "object_export": False, "candidate_changed": False,
            "automatic_retry": False, "old_claims_renewed": False, "cause_proved": False,
            "raw_text_returned": False, "statistic_values_returned": False, "performance_accepted": False,
            "canonical_admission": False, "trading": False}
        try:
            check()
            lock = os.open("controller.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            lock_info = os.fstat(lock)
            if lock_info.st_nlink != 1 or lock_info.st_uid != os.getuid() or stat.S_IMODE(lock_info.st_mode) != 0o600:
                _fail()
            if plan["action"] == "terminals":
                statistics = []
                for terminal in plan["terminals"]:
                    check(); _publish(directory, operation + ".terminal" + str(terminal["attempt"]) + ".read.spent.json", e.canonical({
                        "plan_sha256": report["plan_sha256"], "name": terminal["name"], "bytes": terminal["bytes"], "sha256": terminal["sha256"]}))
                    report["read_attempts"] += 1; report["failed_read_body_bytes_unknown"] = True
                    check(); raw = _read(directory, terminal["name"], expected_size=terminal["bytes"], expected_sha256=terminal["sha256"],
                        remaining=MAX_TERMINAL_BYTES - report["read_bytes"], private=True)
                    report["read_bytes"] += len(raw); report["failed_read_body_bytes_unknown"] = False
                    check(); observed, selected = _terminal(raw, terminal, calendar)
                    report["jobs"].append(observed); statistics.append(selected)
                report["statistic_equality"] = {field: {"present_in_both": all(field in row for row in statistics),
                    "equal": e.canonical(statistics[0][field]) == e.canonical(statistics[1][field]) if all(field in row for row in statistics) else None}
                    for field in STATISTICS}
            else:
                for terminal in plan["terminals"]:
                    job = terminal["job_id"]
                    observed = {"attempt": terminal["attempt"], "job_id": job, "total_matching_lines": None,
                        "observed_lines": 0, "pages": 0, "coverage_complete": False, "bounded_incomplete": False,
                        "request_response_identity": [], "diagnostics": []}
                    report["jobs"].append(observed)
                    for page in range(MAX_PAGES):
                        payload = {"projectId": PROJECT, "backtestId": job, "start": page * PAGE_LINES,
                            "end": (page + 1) * PAGE_LINES, "query": ""}
                        check()
                        if len(report["requests"]) >= MAX_REQUESTS:
                            _fail()
                        stage = operation + ".attempt" + str(terminal["attempt"]) + ".page" + f"{page:02d}"
                        claim = {"endpoint": "backtests/read/log", "payload": payload,
                            "payload_sha256": _sha(e.canonical(payload)), "plan_sha256": report["plan_sha256"]}
                        _publish(directory, stage + ".request.spent.json", e.canonical(claim))
                        request = {"attempt": terminal["attempt"], "page": page, "status": "failed_or_unknown",
                            "response_bytes": None, "projection_sha256": None}
                        report["requests"].append(request)
                        report["read_attempts"] += 1; report["failed_read_body_bytes_unknown"] = True
                        check(); raw, http_status, user, token = transport(payload)
                        if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE or report["read_bytes"] + len(raw) > MAX_LOG_BYTES:
                            _fail()
                        report["read_bytes"] += len(raw); report["failed_read_body_bytes_unknown"] = False
                        check(); projected = _secret_free(raw, user, token)
                        _publish(directory, stage + ".projection.json", e.canonical(projected))
                        request.update(response_bytes=len(raw), projection_sha256=projected["projection_sha256"])
                        value = projected["projection"]
                        if http_status != 200 or type(value) is not dict or value.get("success") is not True:
                            _fail()
                        identity = _identity(value, job)
                        total, logs = _integer(value.get("length")), value.get("logs")
                        if observed["total_matching_lines"] is None:
                            observed["total_matching_lines"] = total
                        if (total != observed["total_matching_lines"] or type(logs) is not list
                                or len(logs) != min(PAGE_LINES, max(0, total - payload["start"]))
                                or any(type(line) is not str for line in logs)):
                            _fail()
                        diagnostic = _text_diagnostic(logs)
                        observed["pages"] += 1; observed["observed_lines"] += len(logs)
                        observed["request_response_identity"].append(identity)
                        observed["diagnostics"].append(diagnostic)
                        request["status"] = "succeeded"
                        check(); _publish(directory, stage + ".terminal.json", e.canonical(request))
                        if observed["observed_lines"] == total:
                            observed["coverage_complete"] = True
                            break
                    observed["bounded_incomplete"] = not observed["coverage_complete"]
                report["all_log_pages_observed"] = all(row["coverage_complete"] for row in report["jobs"])
            check(); report["status"] = "COMPLETED" if plan["action"] == "terminals" or report["all_log_pages_observed"] else "BOUNDED_INCOMPLETE"
        except (Exception, KeyboardInterrupt):
            report["status"] = "FAILED_OR_UNCERTAIN"
            # Keep a durable failure for a claimed request even before auth/body.
            if report["requests"] and report["requests"][-1]["status"] == "failed_or_unknown":
                last = report["requests"][-1]
                stage = operation + ".attempt" + str(last["attempt"]) + ".page" + f"{last['page']:02d}"
                # Metadata-only closure after a spent read/time refusal never
                # renews permission to read a body or make another request.
                guard(plan["git_head"]); _publish(directory, stage + ".terminal.json", e.canonical(last))
        report["ended_utc"] = clock().isoformat()
        guard(plan["git_head"]); raw = e.canonical(report)
        _publish(directory, operation + ".result.json", raw)
        return raw
    finally:
        if lock is not None:
            # Never remove another process's replacement lock.
            try:
                current = os.stat("controller.lock", dir_fd=directory, follow_symlinks=False)
                owned = os.fstat(lock)
                if current.st_dev == owned.st_dev and current.st_ino == owned.st_ino:
                    os.unlink("controller.lock", dir_fd=directory)
            except FileNotFoundError:
                pass
            finally:
                os.close(lock)
        os.close(directory)


def execute_plan(plan):
    """Production has no alternate path, transport, clock or credential seam."""
    if type(plan) is not dict or plan.get("mode") != "production":
        _fail()
    sources = _sources(plan["git_head"])
    return _execute(plan, sources, PRIVATE_ROOT, guard=_guard,
        clock=lambda: datetime.now(timezone.utc), monotonic=time.monotonic, transport=_native_request)


def _execute_fixture(plan, sources, root, *, clock, transport, guard=lambda _: None, monotonic=lambda: 0.0):
    if (type(plan) is not dict or plan.get("mode") != "offline-fixture" or root.is_relative_to(LANE)
            or transport is _native_request):
        _fail()
    return _execute(plan, sources, root, guard=guard, clock=clock, monotonic=monotonic, transport=transport)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fixed failed-OFF terminal or unfiltered-log diagnosis; no launch")
    parser.add_argument("action", choices=("terminals", "logs"))
    for name in ("operation-id", "owner-instruction-sha256", "created-utc", "expires-utc"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        plan = prepare_plan(action=args.action, operation_id=args.operation_id,
            owner_instruction_sha256=args.owner_instruction_sha256,
            created_utc=args.created_utc, expires_utc=args.expires_utc)
        print(execute_plan(plan).decode("ascii"), end="")
        return 0
    except (Exception, KeyboardInterrupt):
        print('{"status":"REFUSED_OR_UNCERTAIN","raw_text_returned":false,"automatic_retry":false}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
