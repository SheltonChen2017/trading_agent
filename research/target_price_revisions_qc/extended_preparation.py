"""Single-use private preparation of the registered extended signal inputs.

No credential, provider, QC, operator-state or outcome opener exists here.
Production binds immutable FAILED001's74 completed Massive scopes separately
from a fresh completed Sharadar-only repair. No synthetic Complete capture is
constructed; the failed original CSV wire stays audit-only. A fresh spent
processing claim precedes every read from either fixed leaf. Payloads stay private;
receipt contains only closed counts, hashes, provenance and limitations.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal as alarm
import stat
import subprocess
import threading
import time
from types import FunctionType

from research.target_price_revisions_qc import extended_signal as scorer
from research.target_price_revisions_qc import extended_source_capture as capture
from research.target_price_revisions_qc import extended_sharadar_repair as repair

LANE_ROOT, LANE_BRANCH = capture.LANE_ROOT, capture.LANE_BRANCH
STUDY_ID, FREEZE_SHA256, CALENDAR_SHA256 = scorer.STUDY_ID, scorer.FREEZE_SHA256, scorer.CALENDAR_SHA256
OPERATION_ID = "TPR-EXT26-PREPARATION-20261010-001"
PRIVATE_ROOT = LANE_ROOT / "artifacts" / "target_price_extended" / STUDY_ID / "inputs"
SOURCE_RELATIVE = "research/target_price_revisions_qc/extended_preparation.py"
DRIVER_RELATIVE = "research/target_price_revisions_qc/extended_preparation_driver.py"
SCORER_RELATIVE = "research/target_price_revisions_qc/extended_signal.py"
RAW_RELATIVE = "research/target_price_revisions_development/raw_revision.py"
CALENDAR_RELATIVE = "research/target_price_revisions_qc/extended_calendar.json"
SOURCE_PATHS = tuple(dict.fromkeys((SOURCE_RELATIVE, DRIVER_RELATIVE, SCORER_RELATIVE,
                                  RAW_RELATIVE, *repair.SOURCE_PATHS)))
ORIGINAL_CAPTURE = {"index_sha256": "701ab0f2e9e61d1db1f53b7d274bf70429f84b565a9fff8c56d1ced13b73e82c",
    "plan_sha256": "df363a61e77abaadbe566c8a8ce474e21e05a67a805f566ff6b868d7d8b4f57c",
    "report_sha256": "21bf77f95ca6cced97084f0520d1119cc872e6867ba13f188cae25002b70edc6",
    "git_sha": "aab3a91f2d9ecadb01b949a17a83d2f7f96f249b"}
LIMITS = {"max_elapsed_seconds": 5400, "max_wire_bytes": 4 * 1024**3,
          "max_projection_bytes": 4 * 1024**3, "max_projection_page_bytes": 128 * 1024**2,
          "max_source_rows": 3968000, "max_identity_bytes": 16 * 1024**2,
          "max_monthly_bytes": 32 * 1024**2, "max_payload_bytes": 512 * 1024**2,
          "max_manifest_bytes": 128 * 1024, "max_index_bytes": 8 * 1024**2}
LIMITATIONS = [
    "Current-vintage native identities and capture clocks do not prove historical availability.",
    "Terminated pagination is not a transaction-consistent provider snapshot or entitlement attestation.",
    "All source refusals, duplicate/conflicting native rows and unmatched counts are retained, never zero signals.",
    "Signal ACTIONS exclusions begin 2020-09-01 and are cumulative; earlier actions are audit-only.",
    "Private constituent packets are stock-proxy development inputs, not complete canonical ETF strategy admission.",
    "Private preparation reads no market outcomes and grants no trading or deployment authority.",
]
_BUILD_FRAMES = scorer.build_frames
_MASSIVE_PROJECTION, _CSV_PROJECTION = capture._massive_projection, repair.csv_projection
SEMANTIC_KEYS = frozenset(("invalid_native_id", "invalid_event_id", "invalid_firm_id", "invalid_native_ticker",
    "invalid_native_touch_order", "invalid_native_touch_clock", "conflicting_native_event_id",
    "invalid_native_cell", "invalid_native_permaticker", "unknown_native_delisting", "invalid_native_figi",
    "action_after_frozen_end", "invalid_native_action_date", "missing_native_action", "invalid_native_contraticker",
    "conflicting_native_identity"))
PUBLIC_KEYS = {"schema", "operation_id", "study_id", "status", "scope_spent",
               "preparation_sha256", "manifest_sha256", "payload_count", "payload_bytes",
               "identity_count", "decision_count", "monthly_shards", "source_rows",
               "source_input_prepared", "point_in_time_data", "rights_verified", "outcome_reads",
               "development_looks", "quantconnect_attempts", "canonical_admission", "trading", "source_refusal_census"}


class PreparationError(ValueError):
    """Closed refusal; no source rows, identifiers or private errors escape."""


def _fail(message="extended preparation refused"):
    raise PreparationError(message)


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _hash(value, length=64):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is None:
        _fail("preparation identity refused")
    return value


def _canonical(body):
    try:
        return scorer.canonical(body)
    except ValueError:
        _fail("preparation serialization refused")


def _object(payload):
    try:
        return capture.helper._source_object(payload)
    except ValueError:
        _fail("preparation JSON refused")


def _clock(value):
    try:
        return capture.probe._clock(value)
    except ValueError:
        _fail("preparation clock refused")


@dataclass(frozen=True)
class PreparationPlan:
    payload: bytes
    sha256: str

    def body(self):
        if (type(self.payload) is not bytes or not 0 < len(self.payload) <= 32768
                or _sha(self.payload) != _hash(self.sha256)):
            _fail("preparation plan identity refused")
        try:
            body = _object(self.payload)
            expected = freeze_preparation_plan(**{key: body[key] for key in (
                "source_hashes", "git_sha", "owner_instruction_sha256", "created_utc", "expires_utc",
                "capture_index_sha256", "capture_plan_sha256", "capture_report_sha256",
                "capture_git_sha", "repair_index_sha256", "repair_plan_sha256", "repair_report_sha256",
                "repair_git_sha", "mode")})
            if expected.payload != self.payload:
                _fail("preparation plan differs from fixed scope")
            return body
        except (KeyError, TypeError, ValueError):
            _fail("preparation plan policy refused")


def freeze_preparation_plan(*, source_hashes, git_sha, owner_instruction_sha256,
                            created_utc, expires_utc, capture_index_sha256,
                            capture_plan_sha256, capture_report_sha256, capture_git_sha,
                            repair_index_sha256, repair_plan_sha256, repair_report_sha256, repair_git_sha,
                            mode="production"):
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS):
        _fail("preparation reachable source inventory refused")
    for value in source_hashes.values():
        _hash(value)
    if any(source_hashes[key] != value for key, value in repair.PUBLIC_HASHES.items()):
        _fail("preparation freeze/probe/calendar binding refused")
    for value, length in ((git_sha, 40), (capture_git_sha, 40), (repair_git_sha, 40), (owner_instruction_sha256, 64),
            (capture_index_sha256, 64), (capture_plan_sha256, 64), (capture_report_sha256, 64),
            (repair_index_sha256, 64), (repair_plan_sha256, 64), (repair_report_sha256, 64)):
        _hash(value, length)
    created, expires = _clock(created_utc), _clock(expires_utc)
    if type(mode) is not str or mode not in ("production", "offline-fixture") or not created < expires <= created + timedelta(hours=48):
        _fail("preparation expiry/mode refused")
    if mode == "production" and any(value != ORIGINAL_CAPTURE[key] for key, value in (
            ("index_sha256", capture_index_sha256), ("plan_sha256", capture_plan_sha256),
            ("report_sha256", capture_report_sha256), ("git_sha", capture_git_sha))):
        _fail("preparation requires exact immutable FAILED001 source")
    body = {"schema": "tpr-ext26-preparation-plan-v2", "operation_id": OPERATION_ID,
        "study_id": STUDY_ID, "mode": mode, "source_hashes": dict(source_hashes), "git_sha": git_sha,
        "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "capture_operation_id": capture.OPERATION_ID, "capture_index_sha256": capture_index_sha256,
        "capture_plan_sha256": capture_plan_sha256, "capture_report_sha256": capture_report_sha256,
        "capture_git_sha": capture_git_sha, "capture_private_root": str(capture.PRIVATE_ROOT),
        "capture_status": "FAILED", "capture_failure": "refused_or_bound_hit_no_retry",
        "repair_operation_id": repair.OPERATION_ID, "repair_freeze_sha256": repair.FREEZE_SHA256,
        "repair_index_sha256": repair_index_sha256, "repair_plan_sha256": repair_plan_sha256,
        "repair_report_sha256": repair_report_sha256, "repair_git_sha": repair_git_sha,
        "repair_private_root": str(repair.PRIVATE_ROOT), "source_composition": "FAILED001-Massive74-plus-completed-Sharadar-repair2",
        "lane_root": str(LANE_ROOT), "lane_branch": LANE_BRANCH, "private_root": str(PRIVATE_ROOT),
        "freeze_sha256": FREEZE_SHA256, "calendar_sha256": CALENDAR_SHA256, "limits": dict(LIMITS),
        "working_authorization": "owner-scoped-private-development-not-provider-attestation",
        "old_receipts_renewed": False, "outcome_access": False, "quantconnect": False,
        "point_in_time_data": False, "rights_verified": False, "canonical_admission": False, "trading": False}
    payload = _canonical(body)
    return PreparationPlan(payload, _sha(payload))


def _verify_imports():
    modules = ((scorer, SCORER_RELATIVE), (scorer.raw, RAW_RELATIVE), (capture, capture.SOURCE_RELATIVE),
               (repair, repair.SOURCE_RELATIVE))
    if Path(__file__) != LANE_ROOT / SOURCE_RELATIVE or any(Path(module.__file__) != LANE_ROOT / relative for module, relative in modules):
        _fail("preparation imported module identity refused")
    for function, module, relative in ((_BUILD_FRAMES, scorer, SCORER_RELATIVE),
            (_MASSIVE_PROJECTION, capture, capture.SOURCE_RELATIVE), (_CSV_PROJECTION, repair, repair.SOURCE_RELATIVE)):
        if type(function) is not FunctionType or Path(function.__code__.co_filename) != LANE_ROOT / relative:
            _fail("preparation imported function identity refused")
    if (scorer.build_frames is not _BUILD_FRAMES or capture._massive_projection is not _MASSIVE_PROJECTION
            or repair.csv_projection is not _CSV_PROJECTION):
        _fail("preparation imported binding changed")
    capture._verify_imports()


def _verify_execution_identity(body):
    _verify_imports()
    try:
        for relative, expected in body["source_hashes"].items():
            capture.probe._git_identity(body)
            if _sha(capture._read_source(relative)) != expected:
                _fail("preparation current source hash refused")
            committed = subprocess.run(["git", "show", body["git_sha"] + ":" + relative],
                cwd=LANE_ROOT, capture_output=True, timeout=5, check=True).stdout
            if type(committed) is not bytes or len(committed) > 262144 or _sha(committed) != expected:
                _fail("preparation exact committed source closure refused")
            capture.probe._git_identity(body)
    except (OSError, UnicodeError, subprocess.SubprocessError, ValueError):
        _fail("preparation committed custody unavailable")


def _private_directory(path, mode, *, capture_leaf=False, repair_leaf=False):
    expected = repair.PRIVATE_ROOT if repair_leaf else capture.PRIVATE_ROOT if capture_leaf else PRIVATE_ROOT
    if (mode == "production" and path != expected or mode == "offline-fixture"
            and (path == expected or path.is_relative_to(LANE_ROOT))):
        _fail("preparation private-root policy refused")
    descriptor = capture._open_directory(path)
    metadata = os.fstat(descriptor)
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700):
        os.close(descriptor)
        _fail("preparation private owner/mode refused")
    return descriptor


def _read_private(directory, name, maximum, expected_sha=None, expected_bytes=None):
    if type(name) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", name) is None:
        _fail("preparation private basename refused")
    descriptor = None
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or not 0 < before.st_size <= maximum
                or expected_bytes is not None and (type(expected_bytes) is not int or before.st_size != expected_bytes)):
            _fail("preparation private file custody refused")
        pieces, remaining = [], before.st_size
        while remaining:
            part = os.read(descriptor, min(1024**2, remaining))
            if not part:
                _fail("preparation private file truncated")
            pieces.append(part)
            remaining -= len(part)
        payload, after = b"".join(pieces), os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink", "st_mode", "st_uid")
        if (any(getattr(before, key) != getattr(after, key) for key in fields)
                or expected_sha is not None and _sha(payload) != _hash(expected_sha)):
            _fail("preparation private file changed/hash refused")
        return payload
    except OSError:
        _fail("preparation private read unavailable")
    finally:
        if descriptor is not None:
            os.close(descriptor)


@contextmanager
def _deadline():
    if threading.current_thread() is not threading.main_thread() or alarm.getitimer(alarm.ITIMER_REAL) != (0.0, 0.0):
        _fail("preparation requires exclusive bounded main-thread execution")
    previous = alarm.getsignal(alarm.SIGALRM)
    def timeout(_signum, _frame):
        _fail("preparation elapsed bound hit")
    alarm.signal(alarm.SIGALRM, timeout)
    alarm.setitimer(alarm.ITIMER_REAL, LIMITS["max_elapsed_seconds"])
    try:
        yield
    finally:
        alarm.setitimer(alarm.ITIMER_REAL, 0)
        alarm.signal(alarm.SIGALRM, previous)


def _report(status, **changes):
    result = {"schema": "tpr-ext26-preparation-result-v1", "operation_id": OPERATION_ID,
        "study_id": STUDY_ID, "status": status, "scope_spent": True,
        "preparation_sha256": None, "manifest_sha256": None, "payload_count": 0,
        "payload_bytes": 0, "identity_count": 0, "decision_count": 0, "monthly_shards": 0,
        "source_rows": 0, "source_input_prepared": False, "point_in_time_data": False,
        "rights_verified": False, "outcome_reads": 0, "development_looks": 0,
        "quantconnect_attempts": 0, "canonical_admission": False, "trading": False,
        "source_refusal_census": {"massive": None, "sharadar": None}}
    result.update(changes)
    if set(result) != PUBLIC_KEYS:
        _fail("preparation public result schema refused")
    return result


def _capture_index(directory, body, check):
    check()
    payload = _read_private(directory, capture.INDEX_NAME, LIMITS["max_index_bytes"], body["capture_index_sha256"])
    index = _object(payload)
    expected_keys = {"schema", "operation_id", "study_id", "plan_sha256", "git_sha", "source_hashes",
        "started_utc", "ended_utc", "pages", "census", "failure", "report", "point_in_time_data",
        "action_history_no_lower_bound", "current_vintage_identity", "count_semantics",
        "terminated_pagination_not_transaction_snapshot"}
    if (set(index) != expected_keys or index["schema"] != "tpr-extended-source-index-v1"
            or index["operation_id"] != capture.OPERATION_ID or index["study_id"] != STUDY_ID
            or index["plan_sha256"] != body["capture_plan_sha256"] or index["git_sha"] != body["capture_git_sha"]
            or index["source_hashes"] != {key: body["source_hashes"][key] for key in capture.SOURCE_PATHS}
            or index["failure"] != body["capture_failure"] or index["point_in_time_data"] is not False
            or any(index[key] is not True for key in ("action_history_no_lower_bound", "current_vintage_identity",
                                                     "terminated_pagination_not_transaction_snapshot"))):
        _fail("preparation capture index binding refused")
    report = index["report"]
    if (type(report) is not dict or set(report) != capture.PUBLIC_KEYS
            or report["schema"] != "tpr-extended-source-capture-report-v1" or report["study_id"] != STUDY_ID
            or report["operation_id"] != capture.OPERATION_ID or report["status"] != "FAILED"
            or report["scope_spent"] is not True or report["capture_complete"] is not False
            or report["terminated_massive_windows"] != 74 or type(report["terminated_massive_windows"]) is not int
            or report["terminated_sharadar_datasets"] != 0 or type(report["terminated_sharadar_datasets"]) is not int):
        _fail("preparation original FAILED001 status refused")
    for key in ("source_input_admitted", "point_in_time_data", "rights_verified", "canonical_admission", "trading"):
        if report[key] is not False:
            _fail("preparation capture authority refused")
    for key in ("outcome_reads", "development_looks", "quantconnect_attempts"):
        if type(report[key]) is not int or report[key] != 0:
            _fail("preparation capture outcome/attempt scope refused")
    pages = index["pages"]
    if type(pages) is not list or not 75 <= len(pages) <= capture.LIMITS["max_requests"]:
        _fail("preparation capture page census refused")
    for key in ("reserved_requests", "attempted_requests", "successful_requests"):
        if type(report[key]) is not int or report[key] != len(pages):
            _fail("preparation capture request accounting refused")
    for key in ("source_rows", "row_refusals", "identical_duplicate_rows", "conflicting_duplicate_rows", "response_bytes"):
        maximum = LIMITS["max_wire_bytes"] if key == "response_bytes" else LIMITS["max_source_rows"]
        if type(report[key]) is not int or not 0 <= report[key] <= maximum:
            _fail("preparation capture source count bound refused")
    if body["mode"] == "production" and (len(pages) != 387 or report["source_rows"] != 349018
            or report["row_refusals"] != 54 or report["response_bytes"] != 255582135
            or report["identical_duplicate_rows"] != 0 or report["conflicting_duplicate_rows"] != 0):
        _fail("preparation exact original FAILED001 census refused")
    ignored = pages[-1]
    if (type(ignored) is not dict or ignored.get("provider") != "sharadar" or ignored.get("dataset") != "tickers"
            or ignored.get("page") != 0 or ignored.get("http_status") != 200 or ignored.get("response_complete") is not True
            or ignored.get("projection_file") is not None or ignored.get("projection_sha256") is not None
            or ignored.get("projection_bytes") != 0 or ignored.get("disposition") != "wire_accepted"
            or type(ignored.get("received_bytes")) is not int or ignored["received_bytes"] != ignored.get("wire_bytes")
            or ignored.get("wire_file") != f"request.{len(pages):04}.wire.csv"):
        _fail("preparation failed original Sharadar wire is audit-only")
    _hash(ignored["wire_sha256"])
    if body["mode"] == "production" and (ignored["wire_bytes"] != 451756
            or ignored["wire_sha256"] != "10e4412848bf6c917b2f22657a3203e204bf77925c2f422f50c4d4a983ecf45a"):
        _fail("preparation exact failed original wire metadata refused")
    for name, maximum, expected in ((capture.OPERATION_ID + ".plan.json", 32768, body["capture_plan_sha256"]),
            (capture.OPERATION_ID + ".aggregate.json", 32768, body["capture_report_sha256"])):
        check()
        selected = _read_private(directory, name, maximum, expected)
        if name.endswith(".plan.json"):
            plan = capture.CapturePlan(selected, expected).body()
            if plan["mode"] != body["mode"] or plan["git_sha"] != index["git_sha"] or plan["source_hashes"] != index["source_hashes"]:
                _fail("preparation original capture plan refused")
        elif _object(selected) != report:
            _fail("preparation original capture report refused")
    started, ended = _clock(index["started_utc"]), _clock(index["ended_utc"])
    if not _clock(plan["created_utc"]) <= started <= ended < _clock(plan["expires_utc"]):
        _fail("preparation capture clock closure refused")
    spent = _object(_read_private(directory, capture.OPERATION_ID + ".access.spent.json", 32768))
    if spent != {"schema": "tpr-extended-capture-access-spent-v1", "operation_id": capture.OPERATION_ID,
            "plan_sha256": body["capture_plan_sha256"], "mode": body["mode"], "started_utc": index["started_utc"]}:
        _fail("preparation capture access claim refused")
    terminal = _object(_read_private(directory, capture.OPERATION_ID + ".terminal.json", 32768))
    if terminal != {"schema": "tpr-extended-capture-terminal-v1", "operation_id": capture.OPERATION_ID,
            "plan_sha256": body["capture_plan_sha256"], "index_sha256": body["capture_index_sha256"],
            "status": "FAILED", "scope_spent": True, "outcome_reads": 0,
            "development_looks": 0, "quantconnect_attempts": 0}:
        _fail("preparation capture terminal binding refused")
    return index


def _repair_index(directory, body, check):
    check()
    index = _object(_read_private(directory, repair.INDEX_NAME, LIMITS["max_index_bytes"], body["repair_index_sha256"]))
    keys = {"schema", "operation_id", "study_id", "freeze_sha256", "plan_sha256", "git_sha", "source_hashes",
        "started_utc", "ended_utc", "pages", "census", "failure", "report", "original_capture_modified",
        "point_in_time_data", "current_vintage_identity", "action_history_no_lower_bound", "ticker_python_collation_asserted",
        "terminated_pagination_not_transaction_snapshot", "count_semantics"}
    if (set(index) != keys or index["schema"] != "tpr-ext26-sharadar-repair-index-v1"
            or index["operation_id"] != repair.OPERATION_ID or index["study_id"] != STUDY_ID
            or index["freeze_sha256"] != repair.FREEZE_SHA256 or index["plan_sha256"] != body["repair_plan_sha256"]
            or index["git_sha"] != body["repair_git_sha"] or index["failure"] is not None
            or index["source_hashes"] != {key: body["source_hashes"][key] for key in repair.SOURCE_PATHS}
            or any(index[key] is not False for key in ("original_capture_modified", "point_in_time_data", "ticker_python_collation_asserted"))
            or any(index[key] is not True for key in ("current_vintage_identity", "action_history_no_lower_bound",
                                                     "terminated_pagination_not_transaction_snapshot"))):
        _fail("preparation repair index binding refused")
    report, pages = index["report"], index["pages"]
    if (type(report) is not dict or set(report) != repair.PUBLIC_KEYS
            or report["schema"] != "tpr-ext26-sharadar-repair-report-v1" or report["operation_id"] != repair.OPERATION_ID
            or report["study_id"] != STUDY_ID or report["freeze_sha256"] != repair.FREEZE_SHA256
            or report["status"] != "COMPLETED" or report["scope_spent"] is not True or report["capture_complete"] is not True
            or type(report["terminated_sharadar_datasets"]) is not int or report["terminated_sharadar_datasets"] != 2
            or type(pages) is not list or not 2 <= len(pages) <= repair.LIMITS["max_requests"]):
        _fail("preparation complete repair required")
    for key in ("source_input_admitted", "point_in_time_data", "rights_verified", "canonical_admission", "trading"):
        if report[key] is not False: _fail("preparation repair authority refused")
    for key in ("outcome_reads", "development_looks", "quantconnect_attempts"):
        if type(report[key]) is not int or report[key] != 0: _fail("preparation repair empirical scope refused")
    for key in ("reserved_requests", "attempted_requests", "successful_requests"):
        if type(report[key]) is not int or report[key] != len(pages): _fail("preparation repair request accounting refused")
    for key in ("source_rows", "row_refusals", "identical_duplicate_rows", "conflicting_duplicate_rows", "response_bytes", "ticker_python_lexical_descents"):
        maximum = repair.LIMITS["max_response_bytes"] if key == "response_bytes" else LIMITS["max_source_rows"]
        if type(report[key]) is not int or not 0 <= report[key] <= maximum: _fail("preparation repair count bound refused")
    for name, expected in ((repair.OPERATION_ID + ".plan.json", body["repair_plan_sha256"]),
                           (repair.OPERATION_ID + ".aggregate.json", body["repair_report_sha256"])):
        check()
        selected = _read_private(directory, name, 32768, expected)
        if name.endswith(".plan.json"):
            plan = repair.RepairPlan(selected, expected).body()
            if plan["mode"] != body["mode"] or plan["git_sha"] != index["git_sha"] or plan["source_hashes"] != index["source_hashes"]:
                _fail("preparation repair original plan refused")
        elif _object(selected) != report: _fail("preparation repair original report refused")
    if not _clock(plan["created_utc"]) <= _clock(index["started_utc"]) <= _clock(index["ended_utc"]) < _clock(plan["expires_utc"]):
        _fail("preparation repair clock closure refused")
    expected_spent = {"schema": "tpr-ext26-sharadar-repair-access-spent-v1", "operation_id": repair.OPERATION_ID,
        "study_id": STUDY_ID, "plan_sha256": body["repair_plan_sha256"], "mode": body["mode"], "started_utc": index["started_utc"]}
    if _object(_read_private(directory, repair.OPERATION_ID + ".access.spent.json", 32768)) != expected_spent:
        _fail("preparation repair access claim refused")
    expected_terminal = {"schema": "tpr-ext26-sharadar-repair-terminal-v1", "operation_id": repair.OPERATION_ID,
        "plan_sha256": body["repair_plan_sha256"], "index_sha256": body["repair_index_sha256"], "status": "COMPLETED",
        "scope_spent": True, "outcome_reads": 0, "development_looks": 0, "quantconnect_attempts": 0}
    if _object(_read_private(directory, repair.OPERATION_ID + ".terminal.json", 32768)) != expected_terminal:
        _fail("preparation repair terminal binding refused")
    return index


def _replay_capture(directory, body, check, *, repaired=False):
    module, source_key = (repair, "repair") if repaired else (capture, "capture")
    index = _repair_index(directory, body, check) if repaired else _capture_index(directory, body, check)
    scopes = ([("sharadar", dataset, None) for dataset in ("tickers", "actions")] if repaired
              else [("massive", "ratings", list(window)) for window in capture.WINDOWS])
    census = index["census"]
    if type(census) is not list or len(census) != (2 if repaired else 76):
        _fail("preparation separately bound source census refused")
    if not repaired and any(row != {"provider": "sharadar", "dataset": dataset, "window": None,
            "pages": 0, "source_rows": 0, "response_bytes": index["pages"][-1]["wire_bytes"] if dataset == "tickers" else 0,
            "terminated": False} for dataset, row in zip(("tickers", "actions"), census[74:])):
        _fail("preparation failed original CSV census is audit-only")
    replay_counts, semantic = Counter(), dict.fromkeys(sorted(SEMANTIC_KEYS), 0)
    rows = {"ratings": [], "tickers": [], "actions": []}
    page_cursor, seen_events = 0, {}
    page_keys = {"request_index", "provider", "dataset", "window", "page", "http_status", "wire_file",
        "wire_sha256", "wire_bytes", "received_bytes", "projection_file", "projection_sha256",
        "projection_bytes", "response_complete", "disposition", "fetch_utc"}
    if repaired: page_keys.remove("window")
    for scope_index, (provider, dataset, window) in enumerate(scopes):
        check()
        row = census[scope_index]
        keys = {"provider", "dataset", "window", "pages", "source_rows", "terminated"}
        if provider == "sharadar": keys.add("response_bytes")
        if repaired: keys.remove("window")
        if (type(row) is not dict or set(row) != keys or (row["provider"], row["dataset"], row.get("window")) != (provider, dataset, window)
                or row["terminated"] is not True or type(row["pages"]) is not int or row["pages"] < 1):
            _fail("preparation source scope identity refused")
        maximum_pages = capture.WINDOW_PAGES if provider == "massive" else capture.DATASET_LIMITS[dataset]["pages"]
        if row["pages"] > maximum_pages:
            _fail("preparation source scope page bound refused")
        scope_rows, scope_wire, seen_rows, hashes, cursors, last_sort = 0, 0, {}, set(), set(), None
        for local_page in range(row["pages"]):
            check()
            if page_cursor >= len(index["pages"]):
                _fail("preparation missing source page refused")
            entry = index["pages"][page_cursor]
            request_index, prefix = page_cursor + 1, f"request.{page_cursor + 1:04}"
            if (type(entry) is not dict or set(entry) != page_keys or entry["request_index"] != request_index
                    or type(entry["request_index"]) is not int
                    or (entry["provider"], entry["dataset"], entry.get("window"), entry["page"]) != (provider, dataset, window, local_page)
                    or type(entry["page"]) is not int or entry["http_status"] != 200 or type(entry["http_status"]) is not int
                    or entry["response_complete"] is not True or entry["disposition"] != "projected"
                    or entry["wire_file"] != prefix + (".wire.json" if provider == "massive" else ".wire.csv")
                    or entry["projection_file"] != prefix + ".projection.json"):
                _fail("preparation page identity/terminal refused")
            wire_max = capture.MASSIVE_PAGE_BYTES if provider == "massive" else capture.CSV_PAGE_BYTES
            wire = _read_private(directory, entry["wire_file"], wire_max, entry["wire_sha256"], entry["wire_bytes"])
            if type(entry["received_bytes"]) is not int or entry["received_bytes"] != len(wire) or entry["wire_sha256"] in hashes:
                _fail("preparation repeated page/byte accounting refused")
            hashes.add(entry["wire_sha256"])
            replay_counts["response_bytes"] += len(wire)
            scope_wire += len(wire)
            fetched = _clock(entry["fetch_utc"])
            if not _clock(index["started_utc"]) <= fetched <= _clock(index["ended_utc"]):
                _fail("preparation source page clock refused")
            terminal = _object(_read_private(directory, prefix + ".terminal.json", 32768))
            expected_terminal = {**entry, "projection_file": None, "projection_sha256": None,
                                 "projection_bytes": 0, "disposition": "wire_accepted"}
            if terminal != expected_terminal:
                _fail("preparation original page terminal refused")
            request = _object(_read_private(directory, prefix + ".spent.json", 32768))
            request_keys = {"schema", "operation_id", "plan_sha256", "request_index", "provider", "dataset", "host",
                "endpoint", "window", "page", "offset", "cursor_present", "started_utc"}
            shared = ("request_index", "provider", "dataset", "page")
            if repaired: request_keys -= {"window", "cursor_present"}
            else: shared += ("window",)
            if (set(request) != request_keys or request["schema"] != ("tpr-ext26-sharadar-repair-request-spent-v1" if repaired else "tpr-extended-capture-request-spent-v1")
                    or request["operation_id"] != module.OPERATION_ID or request["plan_sha256"] != body[source_key + "_plan_sha256"]
                    or any(request[key] != entry[key] for key in shared)
                    or request["host"] != ("api.massive.com" if provider == "massive" else "api.sharadar.com")
                    or request["endpoint"] != ("/benzinga/v1/ratings" if provider == "massive" else "/v1.0/data/" + dataset)
                    or request["offset"] != (local_page * 10000 if provider == "sharadar" else None)
                    or not repaired and request["cursor_present"] is not (provider == "massive" and local_page > 0)
                    or not _clock(index["started_utc"]) <= _clock(request["started_utc"]) <= fetched):
                _fail("preparation original request claim refused")
            check()
            projected_bytes = _read_private(directory, entry["projection_file"], LIMITS["max_projection_page_bytes"],
                                            entry["projection_sha256"], entry["projection_bytes"])
            replay_counts["projection_bytes"] += len(projected_bytes)
            if replay_counts["projection_bytes"] > LIMITS["max_projection_bytes"] or replay_counts["response_bytes"] > LIMITS["max_wire_bytes"]:
                _fail("preparation aggregate source byte bound hit")
            if provider == "massive":
                reconstructed, following = _MASSIVE_PROJECTION(wire, tuple(window), fetched, seen_events)
                terminated = following is None
                if not terminated:
                    cursor = dict(following)["cursor"]
                    if cursor in cursors: _fail("preparation repeated source cursor refused")
                    cursors.add(cursor)
            else:
                reconstructed = _CSV_PROJECTION(wire, dataset, seen_rows)
                terminated = reconstructed["source_rows"] < 10000
            if _canonical(reconstructed) != projected_bytes or terminated != (local_page == row["pages"] - 1):
                _fail("preparation wire/projection/termination parity refused")
            selected = [item["source"] for item in reconstructed["rows"]]
            for item in reconstructed["rows"]:
                reasons = item["refusals"]
                if set(reasons) - SEMANTIC_KEYS: _fail("preparation unregistered source refusal category")
                for reason in reasons: semantic[reason] += 1
                if provider == "massive":
                    semantic["invalid_event_id"] += not scorer.raw._native_id(item["source"]["benzinga_id"])
                    semantic["invalid_firm_id"] += not scorer.raw._native_id(item["source"]["benzinga_firm_id"])
            sort_key = "ticker" if dataset == "tickers" else "date"
            if selected:
                if last_sort is not None and selected[0][sort_key] < last_sort:
                    if dataset == "tickers": replay_counts["ticker_python_lexical_descents"] += 1
                    else: _fail("preparation cross-page source sorting refused")
                last_sort = selected[-1][sort_key]
            rows[dataset].extend(selected)  # Never filter refused or duplicate rows.
            scope_rows += reconstructed["source_rows"]
            for key in ("source_rows", "row_refusals", "identical_duplicate_rows", "conflicting_duplicate_rows"):
                replay_counts[key] += reconstructed[key]
            if repaired: replay_counts["ticker_python_lexical_descents"] += reconstructed["ticker_python_lexical_descents"]
            if dataset == "actions" and any(reason in ("action_after_frozen_end", "invalid_native_action_date")
                    for item in reconstructed["rows"] for reason in item["refusals"]):
                _fail("preparation ACTIONS endpoint date scope refused")
            if replay_counts["source_rows"] > LIMITS["max_source_rows"]:
                _fail("preparation aggregate row bound hit")
            page_cursor += 1
        if (type(row["source_rows"]) is not int or scope_rows != row["source_rows"]
                or provider == "sharadar" and (type(row["response_bytes"]) is not int or scope_wire != row["response_bytes"])
                or scope_rows > (capture.MASSIVE_ROWS if provider == "massive" else capture.DATASET_LIMITS[dataset]["rows"])):
            _fail("preparation per-scope source census parity refused")
    ignored_bytes = 0 if repaired else index["pages"][-1]["wire_bytes"]
    if page_cursor != len(index["pages"]) - (0 if repaired else 1) or any(
            replay_counts[key] != index["report"][key] - (ignored_bytes if key == "response_bytes" else 0)
            for key in ("response_bytes", "source_rows", "row_refusals", "identical_duplicate_rows", "conflicting_duplicate_rows")):
        _fail("preparation full capture accounting refused")
    if repaired and replay_counts["ticker_python_lexical_descents"] != index["report"]["ticker_python_lexical_descents"]:
        _fail("preparation retained provider-order descent census refused")
    if any(len(rows[key]) > bound for key, bound in (("ratings", scorer.MAX_RATINGS),
            ("tickers", scorer.MAX_IDENTITIES), ("actions", scorer.MAX_ACTIONS))):
        _fail("preparation dataset aggregate row bound hit")
    check()
    # Re-read the bound index after all projection reads; no silent replacement.
    _read_private(directory, module.INDEX_NAME, LIMITS["max_index_bytes"], body[source_key + "_index_sha256"])
    return index, rows, dict(replay_counts), semantic


def _packet_payloads(result, calendar, capture_utc, check):
    if type(result) is not dict or set(result) != {"identities", "frames", "normalization", "source_census",
            "point_in_time_data", "canonical_admission", "outcome_reads"}:
        _fail("preparation scorer result schema refused")
    decisions = [row["session"] for row in calendar["decisions"]]
    identities, frames = result["identities"], result["frames"]
    if (type(identities) is not list or not 0 < len(identities) <= 100000
            or type(frames) is not list or [row["session"] for row in frames] != decisions
            or len(decisions) != 301 or len(result["normalization"]) != 301
            or result["point_in_time_data"] is not False or result["canonical_admission"] is not False
            or result["outcome_reads"] != 0 or type(result["outcome_reads"]) is not int):
        _fail("preparation scorer complete frame census refused")
    ids = []
    for identity in identities:
        if (type(identity) is not dict or set(identity) != {"security_id", "ticker", "eligible", "reason"}
                or type(identity["security_id"]) is not str
                or re.fullmatch(r"SHARADAR:[1-9][0-9]{0,19}", identity["security_id"]) is None
                or type(identity["eligible"]) is not bool or type(identity["reason"]) is not str
                or re.fullmatch(r"[a-z_]{1,96}", identity["reason"]) is None
                or identity["ticker"] is None and (identity["eligible"] or identity["reason"] != "ambiguous_snapshot_identity")
                or identity["ticker"] is not None and not scorer.raw._ticker(identity["ticker"])):
            _fail("preparation private identity schema refused")
        ids.append(identity["security_id"])
    if len(set(ids)) != len(ids):
        _fail("preparation duplicate packet identity refused")
    source_keys = {"ratings", "native_event_groups", "duplicate_rows", "native_identity_rows", "unmatched_rating_ticker_count",
                   "all_captured_actions", "pre_warmup_actions_audit_only", "signal_window_actions", "ambiguous_alias_identity_count"}
    if (type(result["source_census"]) is not dict or set(result["source_census"]) != source_keys
            or any(type(value) is not int or not 0 <= value <= LIMITS["max_source_rows"] for value in result["source_census"].values())):
        _fail("preparation public source census schema refused")
    for row, session in zip(result["normalization"], decisions):
        if (type(row) is not dict or set(row) != {"session", "accepted_distinct_events", "refusal_counts",
                "cumulative_excluded_ticker_count", "cumulative_nonshare_counts", "scored_identity_count"}
                or row["session"] != session
                or any(type(row[key]) is not int or not 0 <= row[key] <= LIMITS["max_source_rows"] for key in (
                    "accepted_distinct_events", "cumulative_excluded_ticker_count", "scored_identity_count"))):
            _fail("preparation normalization census schema refused")
        for key in ("refusal_counts", "cumulative_nonshare_counts"):
            if (type(row[key]) is not dict or any(type(reason) is not str or re.fullmatch(r"[a-z_]{1,96}", reason) is None
                    or type(count) is not int or not 0 <= count <= LIMITS["max_source_rows"] for reason, count in row[key].items())):
                _fail("preparation public reason/count schema refused")
    identity_body = {"schema": "tpr-ext26-identities-v1", "study_id": STUDY_ID,
        "freeze_sha256": FREEZE_SHA256, "calendar_sha256": CALENDAR_SHA256,
        "asof_utc": capture_utc, "limitations": list(LIMITATIONS), "identities": identities}
    encoded = _canonical(identity_body)
    if len(encoded) > LIMITS["max_identity_bytes"]:
        _fail("preparation identity payload byte bound hit")
    identity_sha = _sha(encoded)
    payloads = [("identities", identity_sha, encoded, [])]
    months = defaultdict(list)
    for frame, decision in zip(frames, calendar["decisions"]):
        if (type(frame) is not dict or set(frame) != {"session", "cutoff_utc", "states"}
                or frame["cutoff_utc"] != scorer.raw._utc(decision["cutoff"]).isoformat()
                or type(frame["states"]) is not list or [row.get("security_id") for row in frame["states"]] != ids):
            _fail("preparation frame clock/state completeness refused")
        for state in frame["states"]:
            if (type(state) is not dict or set(state) != {"security_id", "state", "score", "reasons"}
                    or state["state"] not in ("scored", "identity_ineligible", "unknown_input", "no_admissible_event")
                    or type(state["reasons"]) is not list or len(set(state["reasons"])) != len(state["reasons"])
                    or any(type(reason) is not str or re.fullmatch(r"[a-z_]{1,96}", reason) is None for reason in state["reasons"])):
                _fail("preparation frame state schema refused")
            if state["state"] == "scored":
                try:
                    if type(state["score"]) is not str or len(state["score"]) > 256 or not Decimal(state["score"]).is_finite():
                        _fail("preparation score decimal refused")
                except InvalidOperation:
                    _fail("preparation score decimal refused")
            elif state["score"] is not None:
                _fail("preparation missing state cannot become zero score")
        months[frame["session"][:7]].append(frame)
    total = len(encoded)
    for month, selected in sorted(months.items()):
        check()
        sessions = [frame["session"] for frame in selected]
        packet = {"schema": "tpr-ext26-signal-shard-v1", "study_id": STUDY_ID,
            "freeze_sha256": FREEZE_SHA256, "calendar_sha256": CALENDAR_SHA256,
            "identity_sha256": identity_sha, "sessions": sessions, "frames": selected}
        wire = _canonical(packet)
        total += len(wire)
        if len(wire) > LIMITS["max_monthly_bytes"] or total > LIMITS["max_payload_bytes"]:
            _fail("preparation monthly/aggregate payload byte bound hit")
        payloads.append(("signal-month", _sha(wire), wire, sessions))
    if [session for _kind, _digest, _wire, sessions in payloads for session in sessions] != decisions:
        _fail("preparation monthly complete decision partition refused")
    return payloads


@dataclass(frozen=True)
class PreparationResult:
    payload: bytes
    sha256: str


def execute_preparation(plan):
    if type(plan) is not PreparationPlan or plan.body()["mode"] != "production":
        _fail("production preparation requires exact production plan")
    body = plan.body()
    _verify_execution_identity(body)
    calendar_payload = capture._read_source(CALENDAR_RELATIVE)
    with _deadline():
        return _execute(plan, capture.PRIVATE_ROOT, repair.PRIVATE_ROOT, PRIVATE_ROOT, calendar_payload,
                        lambda: datetime.now(timezone.utc), time.monotonic)


def _execute_fixture_preparation(plan, capture_root, private_root, *, repair_root, calendar_payload, now,
                                 monotonic=lambda: 0.0):
    if (type(plan) is not PreparationPlan or plan.body()["mode"] != "offline-fixture"
            or any(path.is_relative_to(LANE_ROOT) for path in (capture_root, repair_root, private_root))
            or len({capture_root, repair_root, private_root}) != 3
            or not callable(monotonic)):
        _fail("fixture preparation requires synthetic external leaves")
    return _execute(plan, capture_root, repair_root, private_root, calendar_payload, lambda: now, monotonic)


def _execute(plan, capture_root, repair_root, private_root, calendar_payload, clock, monotonic):
    body, started = plan.body(), clock()
    if (type(started) is not datetime or started.tzinfo is None or started.utcoffset() != timedelta(0)
            or not _clock(body["created_utc"]) <= started < _clock(body["expires_utc"])
            or type(calendar_payload) is not bytes or _sha(calendar_payload) != CALENDAR_SHA256):
        _fail("preparation clock/calendar refused before claim")
    start_tick = monotonic()
    if type(start_tick) not in (int, float) or not math.isfinite(start_tick):
        _fail("preparation monotonic clock refused before claim")
    last_tick, last_clock = start_tick, started
    output = _private_directory(private_root, body["mode"])
    source = repaired_source = None
    def check():
        nonlocal last_tick, last_clock
        current = clock()
        tick = monotonic()
        if (type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0)
                or not last_clock <= current < _clock(body["expires_utc"])
                or type(tick) not in (int, float) or not math.isfinite(tick) or tick < last_tick
                or tick - start_tick >= LIMITS["max_elapsed_seconds"]):
            _fail("preparation elapsed/expiry bound hit")
        last_tick, last_clock = tick, current
    try:
        capture._claim(output, OPERATION_ID + ".access.spent.json", {
            "schema": "tpr-ext26-preparation-access-spent-v1", "operation_id": OPERATION_ID,
            "study_id": STUDY_ID, "plan_sha256": plan.sha256, "started_utc": started.isoformat(),
            "capture_index_sha256": body["capture_index_sha256"], "repair_index_sha256": body["repair_index_sha256"],
            "source_composition": body["source_composition"], "mode": body["mode"]})
        capture.helper._publish(output, OPERATION_ID + ".plan.json", plan.payload)
        source_refusals = {"massive": None, "sharadar": None}
        status, report = "FAILED", _report("FAILED")
        try:
            check()
            source = _private_directory(capture_root, body["mode"], capture_leaf=True)
            index, rows, replay, source_refusals["massive"] = _replay_capture(source, body, check)
            check()
            repaired_source = _private_directory(repair_root, body["mode"], repair_leaf=True)
            repair_index, repaired_rows, repair_replay, source_refusals["sharadar"] = _replay_capture(repaired_source, body, check, repaired=True)
            capture_utc = max((_clock(index["ended_utc"]), _clock(repair_index["ended_utc"]))).isoformat()
            if _clock(capture_utc) > started:
                _fail("preparation cannot precede either source completion")
            for key in rows: rows[key].extend(repaired_rows[key])
            repaired_rows.clear()
            combined_counts = {key: replay.get(key, 0) + repair_replay.get(key, 0)
                               for key in sorted(set(replay) | set(repair_replay))}
            if (combined_counts["source_rows"] > LIMITS["max_source_rows"]
                    or combined_counts["response_bytes"] > LIMITS["max_wire_bytes"]
                    or combined_counts["projection_bytes"] > LIMITS["max_projection_bytes"]):
                _fail("preparation joint composite source bound hit")
            check()
            capture._publish(output, OPERATION_ID + ".source-refusal-census.json", {
                "schema": "tpr-ext26-composite-source-refusals-v1", "operation_id": OPERATION_ID,
                "study_id": STUDY_ID, "plan_sha256": plan.sha256,
                "capture_index_sha256": body["capture_index_sha256"], "repair_index_sha256": body["repair_index_sha256"],
                "source_refusal_census": source_refusals,
                "semantics": "per-category occurrences; ID refinements overlap native-ID category; no row sum inference",
                "outcome_reads": 0, "quantconnect_attempts": 0})
            result = _BUILD_FRAMES(rows["ratings"], rows["tickers"], rows["actions"],
                calendar_payload=calendar_payload, capture_utc=capture_utc)
            rows.clear()
            check()
            payloads = _packet_payloads(result, _object(calendar_payload), capture_utc, check)
            refusal_occurrences = Counter()
            for row in result["normalization"]:
                refusal_occurrences.update(row["refusal_counts"])
            receipt = {"schema": "tpr-ext26-preparation-v2", "operation_id": OPERATION_ID,
                "study_id": STUDY_ID, "status": "COMPLETED", "plan_sha256": plan.sha256,
                "git_sha": body["git_sha"], "source_hashes": body["source_hashes"],
                "owner_instruction_sha256": body["owner_instruction_sha256"],
                "freeze_sha256": FREEZE_SHA256, "calendar_sha256": CALENDAR_SHA256,
                "capture_operation_id": capture.OPERATION_ID, "capture_index_sha256": body["capture_index_sha256"],
                "capture_plan_sha256": body["capture_plan_sha256"], "capture_report_sha256": body["capture_report_sha256"],
                "capture_git_sha": body["capture_git_sha"], "capture_utc": capture_utc,
                "source_composition": body["source_composition"], "capture_status": "FAILED",
                "capture_failure": index["failure"], "capture_ended_utc": index["ended_utc"],
                "original_failed_sharadar_wire_used_for_inputs": False,
                "repair_operation_id": repair.OPERATION_ID, "repair_freeze_sha256": repair.FREEZE_SHA256,
                "repair_index_sha256": body["repair_index_sha256"], "repair_plan_sha256": body["repair_plan_sha256"],
                "repair_report_sha256": body["repair_report_sha256"], "repair_git_sha": body["repair_git_sha"],
                "repair_ended_utc": repair_index["ended_utc"], "repair_status": "COMPLETED",
                "started_utc": started.isoformat(), "ended_utc": clock().isoformat(),
                "capture_census": index["report"], "repair_census": repair_index["report"],
                "source_refusal_census": source_refusals,
                "replayed_counts": dict(combined_counts), "capture_replayed_counts": replay,
                "repair_replayed_counts": repair_replay,
                "signal_source_census": result["source_census"],
                "normalization_refusal_occurrences_across_decisions": dict(sorted(refusal_occurrences.items())),
                "identity_count": len(result["identities"]),
                "eligible_identity_count": sum(row["eligible"] for row in result["identities"]),
                "decision_count": 301, "monthly_shards": len(payloads) - 1,
                "payloads": [{"kind": kind, "sha256": digest, "bytes": len(wire), "sessions": sessions}
                             for kind, digest, wire, sessions in payloads],
                "manifest_policy": "manifest is deterministically derived after receipt hash; not a circular receipt input",
                "limits": dict(LIMITS), "limitations": list(LIMITATIONS),
                "point_in_time_data": False, "rights_verified": False, "source_input_prepared": True,
                "outcome_reads": 0, "development_looks": 0, "quantconnect_attempts": 0,
                "canonical_admission": False, "trading": False}
            receipt_payload = _canonical(receipt)
            if len(receipt_payload) > 262144:
                _fail("preparation public receipt bound hit")
            receipt_sha = _sha(receipt_payload)
            prefix = "tpr-ext26/inputs/" + STUDY_ID + "/" + receipt_sha + "/"
            manifest = {"schema": "tpr-ext26-signal-manifest-v1", "study_id": STUDY_ID,
                "freeze_sha256": FREEZE_SHA256, "calendar_sha256": CALENDAR_SHA256,
                "identity_sha256": payloads[0][1], "identity_key": prefix + payloads[0][1] + ".json",
                "shards": [{"sha256": digest, "key": prefix + digest + ".json", "sessions": sessions}
                           for _kind, digest, _wire, sessions in payloads[1:]]}
            manifest_payload = _canonical(manifest)
            if len(manifest_payload) > LIMITS["max_manifest_bytes"] or sum(len(wire) for _, _, wire, _ in payloads) + len(manifest_payload) > LIMITS["max_payload_bytes"]:
                _fail("preparation manifest/aggregate bound hit")
            manifest_sha = _sha(manifest_payload)
            for _kind, digest, wire, _sessions in payloads:
                check()
                capture.helper._publish(output, digest + ".json", wire)
                _read_private(output, digest + ".json", len(wire), digest, len(wire))
            capture.helper._publish(output, manifest_sha + ".json", manifest_payload)
            _read_private(output, manifest_sha + ".json", LIMITS["max_manifest_bytes"], manifest_sha)
            check()
            capture.helper._publish(output, "preparation.json", receipt_payload)
            _read_private(output, "preparation.json", 262144, receipt_sha)
            check()
            status = "COMPLETED"
            report = _report(status, preparation_sha256=receipt_sha, manifest_sha256=manifest_sha,
                payload_count=len(payloads) + 1, payload_bytes=sum(len(wire) for _, _, wire, _ in payloads) + len(manifest_payload),
                identity_count=receipt["identity_count"], decision_count=301, monthly_shards=len(payloads) - 1,
                source_rows=combined_counts["source_rows"], source_input_prepared=True, source_refusal_census=source_refusals)
        except KeyboardInterrupt:
            status, report = "INTERRUPTED", _report("INTERRUPTED", source_refusal_census=source_refusals)
        except Exception:
            status, report = "FAILED", _report("FAILED", source_refusal_census=source_refusals)
        capture.helper._publish(output, OPERATION_ID + ".terminal.json", _canonical({
            "schema": "tpr-ext26-preparation-terminal-v1", "operation_id": OPERATION_ID,
            "plan_sha256": plan.sha256, "report": report, "ended_utc": clock().isoformat()}))
        encoded = _canonical(report)
        return PreparationResult(encoded, _sha(encoded))
    finally:
        if source is not None: os.close(source)
        if repaired_source is not None: os.close(repaired_source)
        os.close(output)
