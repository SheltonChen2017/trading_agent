"""Fresh, bounded Sharadar-only repair; original failed capture is immutable.

TICKERS' provider order is retained without an invented Python-collation gate.
ACTIONS dates, exact offset census, source refusals/duplicates and all original
private/auth/request fences remain. Import performs no I/O; production exposes
no adapters, resume or alternate roots. No Massive endpoint can be invoked.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import io
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from types import FunctionType

from research.target_price_revisions_qc import extended_source_capture as capture

LANE_ROOT, LANE_BRANCH, STUDY_ID = capture.LANE_ROOT, capture.LANE_BRANCH, capture.STUDY_ID
OPERATION_ID = "TPR-EXT26-SHARADAR-REPAIR-20261010-001"
PRIVATE_ROOT = LANE_ROOT / "artifacts" / "target_price_extended" / STUDY_ID / "sharadar_repair"
SOURCE_RELATIVE = "research/target_price_revisions_qc/extended_sharadar_repair.py"
DRIVER_RELATIVE = "research/target_price_revisions_qc/extended_sharadar_repair_driver.py"
FREEZE_RELATIVE = "research/target_price_revisions_qc/extended_sharadar_repair_freeze.json"
FREEZE_SHA256 = "0d0f67a6d02915ff7357018ef51108fdeb3e334cbcccc7e2fa65bbeb1f1d6097"
PUBLIC_HASHES = {**capture.PUBLIC_HASHES, FREEZE_RELATIVE: FREEZE_SHA256}
SOURCE_PATHS = tuple(dict.fromkeys((SOURCE_RELATIVE, DRIVER_RELATIVE, FREEZE_RELATIVE, *capture.SOURCE_PATHS)))
LIMITS = {"max_requests": 192, "max_response_bytes": 768 * 1024**2,
          "page_bytes": 4 * 1024**2, "max_elapsed_seconds": 5400,
          "request_seconds": 30, "redirects": 0, "retries": 0}
DATASET_LIMITS = {key: dict(value) for key, value in capture.DATASET_LIMITS.items()}
INDEX_NAME = OPERATION_ID + ".source-index.json"
_FIXED_TRANSPORT, _FIXED_RESOLVER = capture._https_get, capture.helper._production_credential
_FIXED_QUERY = capture._sharadar_query
PUBLIC_KEYS = frozenset({"schema", "operation_id", "study_id", "freeze_sha256", "status", "scope_spent",
    "reserved_requests", "attempted_requests", "successful_requests", "response_bytes", "source_rows",
    "row_refusals", "identical_duplicate_rows", "conflicting_duplicate_rows", "ticker_python_lexical_descents",
    "terminated_sharadar_datasets", "capture_complete", "source_input_admitted", "point_in_time_data",
    "rights_verified", "outcome_reads", "development_looks", "quantconnect_attempts", "canonical_admission", "trading"})


class RepairError(ValueError):
    """Closed refusal; never exposes provider, row or credential content."""


def _fail(message):
    raise RepairError(message)


def _canonical(body):
    try:
        return capture._canonical(body)
    except ValueError:
        _fail("repair serialization refused")


def _scope():
    return {"provider": "sharadar", "host": "api.sharadar.com", "method": "GET",
        "queries": {key: dict(value) for key, value in capture.CSV_QUERY.items()},
        "dataset_limits": {key: dict(value) for key, value in DATASET_LIMITS.items()}, "limits": dict(LIMITS),
        "ticker_python_collation_asserted": False, "actions_iso_order_and_end_required": True}


@dataclass(frozen=True)
class RepairPlan:
    payload: bytes
    sha256: str

    def body(self):
        if (type(self.payload) is not bytes or not 0 < len(self.payload) <= 32768
                or capture.probe._digest(self.payload) != capture.probe._hash(self.sha256)):
            _fail("repair plan identity refused")
        try:
            body = capture.helper._source_object(self.payload)
            expected = freeze_repair_plan(**{key: body[key] for key in ("source_hashes", "git_sha",
                "owner_instruction_sha256", "created_utc", "expires_utc", "mode")})
            if expected.payload != self.payload:
                _fail("repair plan differs from frozen scope")
            return body
        except (KeyError, TypeError, ValueError):
            _fail("repair plan policy refused")


def freeze_repair_plan(*, source_hashes, git_sha, owner_instruction_sha256,
                       created_utc, expires_utc, mode="production"):
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS):
        _fail("repair complete fixed source closure required")
    for value in source_hashes.values(): capture.probe._hash(value)
    if any(source_hashes[key] != value for key, value in PUBLIC_HASHES.items()):
        _fail("repair freeze/probe/calendar binding refused")
    capture.probe._hash(git_sha, 40)
    capture.probe._hash(owner_instruction_sha256)
    created, expires = capture.probe._clock(created_utc), capture.probe._clock(expires_utc)
    if mode not in ("production", "offline-fixture") or type(mode) is not str or not created < expires <= created + timedelta(hours=48):
        _fail("repair mode/expiry refused")
    body = {"schema": "tpr-ext26-sharadar-repair-plan-v1", "operation_id": OPERATION_ID,
        "study_id": STUDY_ID, "mode": mode, "source_hashes": dict(source_hashes), "git_sha": git_sha,
        "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "freeze_sha256": FREEZE_SHA256, "lane_root": str(LANE_ROOT), "lane_branch": LANE_BRANCH,
        "private_root": str(PRIVATE_ROOT), "scope": _scope(), "old_receipts_renewed": False,
        "original_capture_modified": False, "point_in_time_data": False, "rights_verified": False,
        "outcome_access": False, "quantconnect": False, "canonical_admission": False, "trading": False,
        "working_authorization": "owner-scoped-private-development-not-provider-attestation"}
    encoded = _canonical(body)
    return RepairPlan(encoded, capture.probe._digest(encoded))


def _verify_imports():
    if (Path(__file__) != LANE_ROOT / SOURCE_RELATIVE or Path(capture.__file__) != LANE_ROOT / capture.SOURCE_RELATIVE
            or capture.LANE_ROOT != LANE_ROOT or capture.LANE_BRANCH != LANE_BRANCH):
        _fail("repair imported module identity refused")
    for function, relative in ((_FIXED_TRANSPORT, capture.SOURCE_RELATIVE), (_FIXED_QUERY, capture.SOURCE_RELATIVE),
            (_FIXED_RESOLVER, "research/target_price_revisions_development/source_audit.py")):
        if type(function) is not FunctionType or Path(function.__code__.co_filename) != LANE_ROOT / relative:
            _fail("repair imported function identity refused")
    if (capture._https_get is not _FIXED_TRANSPORT or capture._sharadar_query is not _FIXED_QUERY
            or capture.helper._production_credential is not _FIXED_RESOLVER):
        _fail("repair production adapter substitution refused")
    capture._verify_imports()


def _verify_execution_identity(body):
    _verify_imports()
    try:
        for relative, expected in body["source_hashes"].items():
            capture.probe._git_identity(body)
            if capture.probe._digest(capture._read_source(relative)) != expected:
                _fail("repair current source hash refused")
            committed = subprocess.run(["git", "show", body["git_sha"] + ":" + relative],
                cwd=LANE_ROOT, capture_output=True, timeout=5, check=True).stdout
            if type(committed) is not bytes or len(committed) > 262144 or capture.probe._digest(committed) != expected:
                _fail("repair exact committed closure refused")
            capture.probe._git_identity(body)
    except (OSError, UnicodeError, subprocess.SubprocessError, ValueError):
        _fail("repair committed source custody unavailable")


def _private_directory(path, mode):
    if (mode == "production" and path != PRIVATE_ROOT or mode == "offline-fixture"
            and (path == PRIVATE_ROOT or path.is_relative_to(LANE_ROOT))):
        _fail("repair private-root policy refused")
    directory = capture._open_directory(path)
    metadata = os.fstat(directory)
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700):
        os.close(directory)
        _fail("repair requires owner-only private root")
    return directory


def csv_projection(payload, dataset, seen):
    """Original native fields/refusals, without a false TICKERS collation gate.

    Missing optional columns remain None. Present empty strings are preserved,
    not silently repaired. Duplicate/conflict rows and provider order are kept.
    The public API is pure and is also the composite adapter's replay oracle.
    """
    if (type(payload) is not bytes or not 0 < len(payload) <= LIMITS["page_bytes"]
            or type(dataset) is not str or dataset not in DATASET_LIMITS or type(seen) is not dict):
        _fail("repair projection scope refused")
    optional = "figi" if dataset == "tickers" else "contraticker"
    required = set(capture.CSV_FIELDS[dataset]) - {optional}
    try:
        text = payload.decode("utf-8-sig")
        if "\x00" in text: raise ValueError
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        if len(header) != len(set(header)) or not required <= set(header) or len(header) > 128:
            raise ValueError
        rows, refusals, duplicates, conflicts, descents, previous = [], 0, 0, 0, 0, None
        for cells in reader:
            if len(cells) != len(header) or len(rows) >= 10000: raise ValueError
            native = dict(zip(header, cells))
            row = {field: native.get(field) for field in capture.CSV_FIELDS[dataset]}
            reasons = []
            if any(len(value) > 8192 or any(ord(c) < 32 or ord(c) == 127 for c in value) for value in cells):
                reasons.append("invalid_native_cell")
            if re.fullmatch(r"[A-Z][A-Z0-9.\-/]{0,31}", row["ticker"]) is None:
                reasons.append("invalid_native_ticker")
            if dataset == "tickers":
                if re.fullmatch(r"[1-9][0-9]{0,19}", row["permaticker"]) is None:
                    reasons.append("invalid_native_permaticker")
                if row["isdelisted"] not in ("Y", "N"):
                    reasons.append("unknown_native_delisting")
                if row["figi"] and re.fullmatch(r"[A-Z0-9]{12}", row["figi"]) is None:
                    reasons.append("invalid_native_figi")
                sorting, identity = row["ticker"], row["ticker"]
            else:
                try:
                    if date.fromisoformat(row["date"]).isoformat() != row["date"] or row["date"] > "2026-10-09":
                        reasons.append("action_after_frozen_end")
                except ValueError:
                    reasons.append("invalid_native_action_date")
                if not row["action"]: reasons.append("missing_native_action")
                if row["contraticker"] and re.fullmatch(r"[A-Z][A-Z0-9.\-/]{0,31}", row["contraticker"]) is None:
                    reasons.append("invalid_native_contraticker")
                sorting = row["date"]
                identity = (row["ticker"], row["date"], row["action"], row["contraticker"])
            if previous is not None and sorting < previous:
                if dataset == "actions": _fail("repair ACTIONS chronological order refused")
                descents += 1  # Visible count, never a TICKERS admission rule.
            previous = sorting
            signature = capture.probe._digest(_canonical(row))
            if identity in seen:
                if seen[identity] == signature: duplicates += 1
                else:
                    conflicts += 1
                    reasons.append("conflicting_native_identity")
            else: seen[identity] = signature
            refusals += bool(reasons)
            rows.append({"source": row, "refusals": reasons})
        return {"schema": "tpr-ext26-sharadar-repair-page-v1", "dataset": dataset, "rows": rows,
            "source_rows": len(rows), "row_refusals": refusals, "identical_duplicate_rows": duplicates,
            "conflicting_duplicate_rows": conflicts, "ticker_python_lexical_descents": descents,
            "missing_optional_column": optional not in header, "current_vintage_not_point_in_time": True}
    except (UnicodeError, ValueError, TypeError, csv.Error, StopIteration):
        _fail("repair CSV structural schema refused")


@dataclass(frozen=True)
class RepairResult:
    payload: bytes
    sha256: str
    index_path: Path


def execute_repair(plan):
    if type(plan) is not RepairPlan or plan.body()["mode"] != "production":
        _fail("production repair requires exact production plan")
    _verify_execution_identity(plan.body())
    return _execute(plan, PRIVATE_ROOT, _FIXED_RESOLVER, _FIXED_TRANSPORT,
                    lambda: datetime.now(timezone.utc), time.monotonic)


def _execute_fixture_repair(plan, private_root, *, now, credential_resolver, transport, monotonic=lambda: 0.0):
    if (type(plan) is not RepairPlan or plan.body()["mode"] != "offline-fixture"
            or private_root.is_relative_to(LANE_ROOT) or not callable(credential_resolver) or not callable(transport)
            or not callable(monotonic) or credential_resolver in (_FIXED_RESOLVER, capture.helper._production_credential)
            or transport in (_FIXED_TRANSPORT, capture._https_get)):
        _fail("repair fixture requires synthetic external adapters")
    return _execute(plan, private_root, credential_resolver, transport, lambda: now, monotonic)


def _execute(plan, private_root, resolver, transport, clock, monotonic):
    body, started = plan.body(), clock()
    if (type(started) is not datetime or started.tzinfo is None or started.utcoffset() != timedelta(0)
            or not capture.probe._clock(body["created_utc"]) <= started < capture.probe._clock(body["expires_utc"])):
        _fail("repair outside frozen clock")
    start_tick = monotonic()
    if type(start_tick) not in (int, float) or not math.isfinite(start_tick):
        _fail("repair monotonic clock refused")
    previous_tick, previous_clock = start_tick, started
    directory = _private_directory(private_root, body["mode"])
    state = {"reserved_requests": 0, "attempted_requests": 0, "successful_requests": 0,
        "response_bytes": 0, "source_rows": 0, "row_refusals": 0, "identical_duplicate_rows": 0,
        "conflicting_duplicate_rows": 0, "ticker_python_lexical_descents": 0, "terminated_sharadar_datasets": 0}
    pages = []
    census = [{"provider": "sharadar", "dataset": dataset, "pages": 0, "source_rows": 0,
               "response_bytes": 0, "terminated": False} for dataset in ("tickers", "actions")]
    credential, interrupted = None, False
    def remaining():
        nonlocal previous_tick, previous_clock
        current, tick = clock(), monotonic()
        if (type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0)
                or current < previous_clock or type(tick) not in (int, float) or not math.isfinite(tick) or tick < previous_tick):
            _fail("repair clock rollback refused")
        previous_tick, previous_clock = tick, current
        available = min(LIMITS["max_elapsed_seconds"] - (tick - start_tick),
                        (capture.probe._clock(body["expires_utc"]) - current).total_seconds())
        if available <= 0: _fail("repair elapsed/expiry bound hit")
        return current, available
    try:
        capture._claim(directory, OPERATION_ID + ".access.spent.json", {
            "schema": "tpr-ext26-sharadar-repair-access-spent-v1", "operation_id": OPERATION_ID,
            "study_id": STUDY_ID, "plan_sha256": plan.sha256, "mode": body["mode"], "started_utc": started.isoformat()})
        capture.helper._publish(directory, OPERATION_ID + ".plan.json", plan.payload)
        status, failure = "FAILED", "uninvoked"
        def fetch(dataset, page):
            nonlocal credential
            current, budget = remaining()
            if (state["reserved_requests"] >= LIMITS["max_requests"]
                    or LIMITS["max_response_bytes"] - state["response_bytes"] < LIMITS["page_bytes"]):
                _fail("repair global request/byte bound hit")
            query = _FIXED_QUERY(dataset, page)
            index, prefix = state["reserved_requests"] + 1, f"request.{state['reserved_requests'] + 1:04}"
            capture._claim(directory, prefix + ".spent.json", {
                "schema": "tpr-ext26-sharadar-repair-request-spent-v1", "operation_id": OPERATION_ID,
                "plan_sha256": plan.sha256, "request_index": index, "provider": "sharadar", "dataset": dataset,
                "host": "api.sharadar.com", "endpoint": "/v1.0/data/" + dataset, "page": page,
                "offset": page * 10000, "started_utc": current.isoformat()})
            state["reserved_requests"] += 1
            entry = {"request_index": index, "provider": "sharadar", "dataset": dataset, "page": page,
                "http_status": None, "wire_file": None, "wire_sha256": None, "wire_bytes": 0,
                "received_bytes": None, "projection_file": None, "projection_sha256": None,
                "projection_bytes": 0, "response_complete": False, "disposition": "unknown_spent",
                "fetch_utc": current.isoformat()}
            pages.append(entry)
            try:
                if credential is None:
                    credential = resolver("sharadar")
                    if (not capture.helper._valid_credential(credential)
                            or body["mode"] == "offline-fixture" and not credential.startswith("SYNTHETIC_")):
                        _fail("repair credential unavailable")
                _current, budget = remaining()  # Resolver cannot extend wall/expiry budget.
                state["attempted_requests"] += 1
                response = transport("sharadar", dataset, query, credential, min(30, budget))
                entry["fetch_utc"] = clock().isoformat()
                if type(response) is capture.CaptureResponse:
                    if type(response.status) is int and 100 <= response.status <= 599: entry["http_status"] = response.status
                    if type(response.body) is bytes and len(response.body) <= LIMITS["page_bytes"]:
                        entry["received_bytes"] = len(response.body)
                        state["response_bytes"] += len(response.body)
                remaining()
                capture._framing(response, LIMITS["page_bytes"], "text/csv")
                entry["response_complete"] = response.complete is True
                capture._secret_guard(response.body, (credential,))
                capture.helper._publish(directory, prefix + ".wire.csv", response.body)
                entry.update(wire_file=prefix + ".wire.csv", wire_sha256=capture.probe._digest(response.body), wire_bytes=len(response.body))
                if response.status != 200 or response.complete is not True or not response.body:
                    _fail("repair HTTP/incomplete response refused")
                entry["disposition"] = "wire_accepted"
                state["successful_requests"] += 1
                return response.body, entry
            except KeyboardInterrupt:
                entry["disposition"] = "interrupted_unknown_spent"
                raise
            except Exception:
                entry["disposition"] = "refused_unknown_spent"
                _fail("repair request refused; no retry")
            finally:
                capture._publish(directory, prefix + ".terminal.json", entry)
        try:
            for dataset_index, dataset in enumerate(("tickers", "actions")):
                row = census[dataset_index]
                seen, hashes, last_date, last_ticker = {}, set(), None, None
                for page in range(DATASET_LIMITS[dataset]["pages"]):
                    if row["response_bytes"] + LIMITS["page_bytes"] > DATASET_LIMITS[dataset]["bytes"]:
                        _fail("repair dataset byte bound hit")
                    payload, entry = fetch(dataset, page)
                    row["response_bytes"] += len(payload)
                    if entry["wire_sha256"] in hashes: _fail("repair repeated page refused")
                    hashes.add(entry["wire_sha256"])
                    projection = csv_projection(payload, dataset, seen)
                    selected = projection["rows"]
                    if selected:
                        if dataset == "actions":
                            first, last = selected[0]["source"]["date"], selected[-1]["source"]["date"]
                            if last_date is not None and first < last_date:
                                _fail("repair ACTIONS cross-page chronological order refused")
                            last_date = last
                        else:
                            first, last = selected[0]["source"]["ticker"], selected[-1]["source"]["ticker"]
                            # Separate cross-page count, never a TICKERS sorting gate.
                            state["ticker_python_lexical_descents"] += int(last_ticker is not None and first < last_ticker)
                            last_ticker = last
                    encoded = _canonical(projection)
                    filename = f"request.{entry['request_index']:04}.projection.json"
                    capture.helper._publish(directory, filename, encoded)
                    entry.update(projection_file=filename, projection_sha256=capture.probe._digest(encoded),
                                 projection_bytes=len(encoded), disposition="projected")
                    for key in ("source_rows", "row_refusals", "identical_duplicate_rows", "conflicting_duplicate_rows", "ticker_python_lexical_descents"):
                        state[key] += projection[key]
                    row["pages"] += 1
                    row["source_rows"] += projection["source_rows"]
                    if row["source_rows"] > DATASET_LIMITS[dataset]["rows"]:
                        _fail("repair dataset row bound hit")
                    if dataset == "actions" and any(reason in ("action_after_frozen_end", "invalid_native_action_date")
                            for native in selected for reason in native["refusals"]):
                        _fail("repair ACTIONS endpoint date scope refused")
                    remaining()
                    if projection["source_rows"] < 10000:
                        row["terminated"] = True
                        state["terminated_sharadar_datasets"] += 1
                        break
                if not row["terminated"]: _fail("repair offset termination bound hit")
            remaining()
            status, failure = "COMPLETED", None
        except KeyboardInterrupt:
            status, failure, interrupted = "INTERRUPTED", "interrupted_unknown_spent", True
        except Exception:
            status, failure = "FAILED", "refused_or_bound_hit_no_retry"
        complete = status == "COMPLETED" and state["terminated_sharadar_datasets"] == 2
        report = {"schema": "tpr-ext26-sharadar-repair-report-v1", "operation_id": OPERATION_ID,
            "study_id": STUDY_ID, "freeze_sha256": FREEZE_SHA256, "status": status, "scope_spent": True,
            **state, "capture_complete": complete, "source_input_admitted": False,
            "point_in_time_data": False, "rights_verified": False, "outcome_reads": 0,
            "development_looks": 0, "quantconnect_attempts": 0, "canonical_admission": False, "trading": False}
        if set(report) != PUBLIC_KEYS: _fail("repair public report schema refused")
        index = {"schema": "tpr-ext26-sharadar-repair-index-v1", "operation_id": OPERATION_ID,
            "study_id": STUDY_ID, "freeze_sha256": FREEZE_SHA256, "plan_sha256": plan.sha256,
            "git_sha": body["git_sha"], "source_hashes": body["source_hashes"],
            "started_utc": started.isoformat(), "ended_utc": clock().isoformat(),
            "pages": pages, "census": census, "failure": failure, "report": report,
            "original_capture_modified": False, "point_in_time_data": False,
            "current_vintage_identity": True, "action_history_no_lower_bound": True,
            "ticker_python_collation_asserted": False, "terminated_pagination_not_transaction_snapshot": True,
            "count_semantics": {"response_bytes": "observed bounded wire bytes including unpersisted refusals",
                "source_rows": "parsed retained native projections, not unknown refused bodies",
                "successful_requests": "complete HTTP200 wires, not signal admission"}}
        capture._publish(directory, INDEX_NAME, index)
        capture._publish(directory, OPERATION_ID + ".aggregate.json", report)
        capture._publish(directory, OPERATION_ID + ".terminal.json", {
            "schema": "tpr-ext26-sharadar-repair-terminal-v1", "operation_id": OPERATION_ID,
            "plan_sha256": plan.sha256, "index_sha256": capture.probe._digest(_canonical(index)),
            "status": status, "scope_spent": True, "outcome_reads": 0, "development_looks": 0, "quantconnect_attempts": 0})
        if interrupted: raise KeyboardInterrupt("repair interrupted; preserve spent scope") from None
        encoded = _canonical(report)
        return RepairResult(encoded, capture.probe._digest(encoded), private_root / INDEX_NAME)
    finally:
        credential = None
        os.close(directory)
