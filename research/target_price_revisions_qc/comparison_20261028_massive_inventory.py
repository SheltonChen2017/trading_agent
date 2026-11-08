"""Pure projection of ONE exact retained FAILED001 source-index metadata file.

No file/credential/provider/QC/private-row opener or active claim exists here.
Caller must publish a fresh source/HEAD/time/access claim BEFORE reading the
one fixed index. A second fresh scope must bind the resulting exact inventory
before opening only its386 Massive projection pages across74 monthly windows.
The old scope stays spent/FAILED. This is not provider completeness, input
admission, historical identity/basis proof, native acceptance or trading authority.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timezone
import hashlib
import json
import re

STUDY = "TPR-SIX-UNIVERSE-FIVE-ARM-20261028-v1"
OLD_STUDY = "TPR-CAP-TILT-EXT26-20261010-v1"
CAPTURE = "TPR-EXT26-SOURCE-CAPTURE-20261010-001"
CAPTURE_GIT = "aab3a91f2d9ecadb01b949a17a83d2f7f96f249b"
CAPTURE_PLAN = "df363a61e77abaadbe566c8a8ce474e21e05a67a805f566ff6b868d7d8b4f57c"
INDEX_NAME = CAPTURE + ".source-index.json"
INDEX_BYTES = 224765
INDEX_SHA256 = "701ab0f2e9e61d1db1f53b7d274bf70429f84b565a9fff8c56d1ced13b73e82c"
AGGREGATE_NAME = CAPTURE + ".aggregate.json"
AGGREGATE_BYTES = 669
AGGREGATE_SHA256 = "21bf77f95ca6cced97084f0520d1119cc872e6867ba13f188cae25002b70edc6"
INPUT_ROOT = "/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions/artifacts/target_price_extended/" + OLD_STUDY + "/source_capture"
MAX_PROJECTION_PAGE_BYTES = 128 * 1024**2
MAX_PROJECTION_TOTAL_BYTES = 4 * 1024**3
WINDOWS = tuple((f"{year:04}-{month:02}-01", "2026-10-09" if (year, month) == (2026, 10)
    else f"{year:04}-{month:02}-{calendar.monthrange(year, month)[1]:02}")
    for year in range(2020, 2027) for month in range(1, 13) if (2020, 9) <= (year, month) <= (2026, 10))
PUBLIC_PINS = {
    "research/target_price_revisions_qc/extended_source_capture_freeze.json": "23beda591abf29af63e0bad1fad4b94f7e8f49e6d64ca4d36d4c85b8ded87a2d",
    "research/target_price_revisions_qc/extended_source_probe_aggregate.json": "8fc3b1d2264ed8feb6e63e1e6f1e603abcffc2a9ff8757155639791ad48111a0",
    "research/target_price_revisions_qc/extended_study_freeze.json": "90bdec5520b29bd932a3ec730f7c4c40c544ea7582731ad6680ef34ea8cf4067",
    "research/target_price_revisions_qc/extended_calendar.json": "3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d"}
SOURCE_PATHS = (
    "research/target_price_revisions_qc/extended_source_capture.py",
    "research/target_price_revisions_qc/extended_source_capture_driver.py",
    "research/target_price_revisions_qc/extended_source_probe.py", "research/__init__.py",
    "research/target_price_revisions_qc/__init__.py", "research/target_price_revisions_development/__init__.py",
    "research/target_price_revisions_development/source_audit.py", *PUBLIC_PINS)
_INDEX_KEYS = frozenset("schema operation_id study_id plan_sha256 git_sha source_hashes started_utc ended_utc pages census failure report point_in_time_data action_history_no_lower_bound current_vintage_identity count_semantics terminated_pagination_not_transaction_snapshot".split())
_PAGE_KEYS = frozenset("request_index provider dataset window page http_status wire_file wire_sha256 wire_bytes received_bytes projection_file projection_sha256 projection_bytes response_complete disposition fetch_utc".split())
_COUNT_SEMANTICS = {
    "response_bytes": "observed bounded wire bytes including unpersisted refusals",
    "source_rows": "parsed retained native projections, not unknown refused bodies",
    "successful_requests": "complete HTTP200 wires, not signal admission"}


class InventoryRefusal(ValueError):
    """Body-free metadata refusal; actual read accounting belongs to the caller."""


def _fail():
    raise InventoryRefusal("fixed retained Massive metadata refused") from None


def canonical(body):
    try:
        return (json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                           allow_nan=False) + "\n").encode("ascii")
    except (TypeError, ValueError, OverflowError, RecursionError):
        _fail()


def _closed(body, keys):
    if type(body) is not dict or set(body) != keys:
        _fail()


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _fail()
    return value


def _count(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        _fail()
    return value


def _clock(value):
    try:
        if type(value) is not str or not 0 < len(value) <= 40:
            _fail()
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(result):
            _fail()
        return result
    except (ValueError, TypeError, OverflowError):
        _fail()


def aggregate_bytes():
    """Reconstruct public closed669-byte receipt; this does not read that file."""
    return canonical({"schema": "tpr-extended-source-capture-report-v1", "operation_id": CAPTURE,
        "study_id": OLD_STUDY, "status": "FAILED", "scope_spent": True,
        "reserved_requests": 387, "attempted_requests": 387, "successful_requests": 387,
        "response_bytes": 255582135, "source_rows": 349018, "row_refusals": 54,
        "identical_duplicate_rows": 0, "conflicting_duplicate_rows": 0,
        "terminated_massive_windows": 74, "terminated_sharadar_datasets": 0,
        "capture_complete": False, "source_input_admitted": False, "point_in_time_data": False,
        "rights_verified": False, "outcome_reads": 0, "development_looks": 0,
        "quantconnect_attempts": 0, "canonical_admission": False, "trading": False})


def _object(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail()
            result[key] = value
        return result
    def refuse(_):
        _fail()
    try:
        body = json.loads(raw, object_pairs_hook=pairs, parse_float=refuse, parse_constant=refuse)
        if type(body) is not dict:
            _fail()
        return body
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _fail()


def _inventory(body):
    """Pure schema validation only; fixed raw-byte admission is project_index."""
    _closed(body, _INDEX_KEYS)
    if (body["schema"] != "tpr-extended-source-index-v1" or body["operation_id"] != CAPTURE
            or body["study_id"] != OLD_STUDY or body["plan_sha256"] != CAPTURE_PLAN
            or body["git_sha"] != CAPTURE_GIT or body["failure"] != "refused_or_bound_hit_no_retry"
            or body["point_in_time_data"] is not False
            or any(body[key] is not True for key in ("action_history_no_lower_bound", "current_vintage_identity",
                                                     "terminated_pagination_not_transaction_snapshot"))
            or body["count_semantics"] != _COUNT_SEMANTICS
            or canonical(body["report"]) != aggregate_bytes()):
        _fail()
    _closed(body["source_hashes"], frozenset(SOURCE_PATHS))
    for key, value in body["source_hashes"].items():
        _hash(value)
        if key in PUBLIC_PINS and value != PUBLIC_PINS[key]:
            _fail()
    started, ended = _clock(body["started_utc"]), _clock(body["ended_utc"])
    if started > ended:
        _fail()
    pages, census = body["pages"], body["census"]
    if type(pages) is not list or len(pages) != 387 or type(census) is not list or len(census) != 76:
        _fail()
    groups, page_cursor, total_rows, wire_bytes, projection_bytes = [], 0, 0, 0, 0
    previous_clock = started
    names = set()
    for window, scope in zip(WINDOWS, census[:74]):
        _closed(scope, frozenset("provider dataset window pages source_rows terminated".split()))
        if (scope["provider"] != "massive" or scope["dataset"] != "ratings"
                or scope["window"] != list(window) or scope["terminated"] is not True
                or not 1 <= _count(scope["pages"], 64)
                or _count(scope["source_rows"], 64000) > scope["pages"] * 1000):
            _fail()
        descriptors = []
        for page in range(scope["pages"]):
            if page_cursor >= 386:
                _fail()
            entry = pages[page_cursor]
            _closed(entry, _PAGE_KEYS)
            number, prefix = page_cursor + 1, f"request.{page_cursor + 1:04}"
            if (type(entry["request_index"]) is not int or entry["request_index"] != number
                    or entry["provider"] != "massive" or entry["dataset"] != "ratings"
                    or entry["window"] != list(window) or type(entry["page"]) is not int or entry["page"] != page
                    or type(entry["http_status"]) is not int or entry["http_status"] != 200
                    or entry["response_complete"] is not True or entry["disposition"] != "projected"
                    or entry["wire_file"] != prefix + ".wire.json"
                    or entry["projection_file"] != prefix + ".projection.json"
                    or not 0 < _count(entry["wire_bytes"], 2 * 1024**2)
                    or type(entry["received_bytes"]) is not int or entry["received_bytes"] != entry["wire_bytes"]
                    or not 0 < _count(entry["projection_bytes"], MAX_PROJECTION_PAGE_BYTES)):
                _fail()
            _hash(entry["wire_sha256"])
            projection_hash = _hash(entry["projection_sha256"])
            observed = _clock(entry["fetch_utc"])
            if not previous_clock <= observed <= ended or entry["projection_file"] in names:
                _fail()
            previous_clock = observed
            names.add(entry["projection_file"])
            descriptors.append({"request_index": number, "page": page,
                "name": entry["projection_file"], "bytes": entry["projection_bytes"],
                "sha256": projection_hash, "fetch_utc": entry["fetch_utc"], "row_count": None})
            wire_bytes += entry["wire_bytes"]
            projection_bytes += entry["projection_bytes"]
            page_cursor += 1
        groups.append({"window": list(window), "source_rows": scope["source_rows"],
            "retained_scope_terminated": True, "projections": descriptors})
        total_rows += scope["source_rows"]
    if (page_cursor != 386 or total_rows != 349018 or wire_bytes != 255130379
            or not 0 < projection_bytes <= MAX_PROJECTION_TOTAL_BYTES):
        _fail()
    ignored = pages[-1]
    _closed(ignored, _PAGE_KEYS)
    expected = {"request_index": 387, "provider": "sharadar", "dataset": "tickers", "window": None,
        "page": 0, "http_status": 200, "wire_file": "request.0387.wire.csv",
        "wire_sha256": "10e4412848bf6c917b2f22657a3203e204bf77925c2f422f50c4d4a983ecf45a",
        "wire_bytes": 451756, "received_bytes": 451756, "projection_file": None,
        "projection_sha256": None, "projection_bytes": 0, "response_complete": True, "disposition": "wire_accepted",
        "fetch_utc": ignored["fetch_utc"]}
    if canonical(ignored) != canonical(expected) or not previous_clock <= _clock(ignored["fetch_utc"]) <= ended:
        _fail()
    for dataset, scope in zip(("tickers", "actions"), census[74:]):
        expected_scope = {"provider": "sharadar", "dataset": dataset, "window": None, "pages": 0,
            "source_rows": 0, "response_bytes": 451756 if dataset == "tickers" else 0, "terminated": False}
        if canonical(scope) != canonical(expected_scope):
            _fail()
    return {"schema": "tpr-comparison-20261028-massive-inventory-v1", "study_id": STUDY,
        "capture_operation": CAPTURE, "original_capture_status": "FAILED", "original_scope_remains_spent": True,
        "input_root": INPUT_ROOT, "index_name": INDEX_NAME, "index_bytes": INDEX_BYTES,
        "index_sha256": INDEX_SHA256, "original_plan_sha256": CAPTURE_PLAN, "capture_git_sha": CAPTURE_GIT,
        "windows": groups, "window_count": 74, "projection_count": 386, "source_rows": total_rows,
        "massive_wire_bytes_in_old_index": wire_bytes, "projection_bytes": projection_bytes,
        "next_stage_exact_file_count": 386, "next_stage_max_bytes": projection_bytes,
        "read_raw_wire": False, "read_sharadar": False, "read_old_d0": False,
        "fresh_claim_before_caller_index_read_required": True, "fresh_claim_before_page_read_required": True,
        "provider_completeness_proven": False, "historical_identity_proven": False,
        "point_in_time_data": False, "rights_verified": False, "source_inputs_admitted": False,
        "native_acceptance": False, "canonical_admission": False, "accepted_performance": None}


def project_index(raw):
    """Pure fixed-index projection; caller owns the fresh one-file read claim."""
    if type(raw) is not bytes or len(raw) != INDEX_BYTES or hashlib.sha256(raw).hexdigest() != INDEX_SHA256:
        _fail()
    return _inventory(_object(raw))


def inventory_bytes(raw):
    """Return closed canonical metadata, never licensed rows or an active claim."""
    return canonical(project_index(raw))
