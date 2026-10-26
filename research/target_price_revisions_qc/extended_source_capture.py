"""Fresh, one-shot private source capture for the frozen extended TPR study.

Imports perform no I/O. Production has no adapters, alternate roots or resume.
The fixed global claim and each request claim precede credential resolution.
Raw wires/native projections remain private; public results contain counts only.
Terminated pagination is not PIT, contractual access or completeness attestation.
"""
from __future__ import annotations

import calendar
from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import html
import http.client
import io
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import subprocess
import threading
import time
from types import FunctionType
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

from research.target_price_revisions_qc import extended_source_probe as probe

helper = probe.helper
LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions")
LANE_BRANCH = "codex/strategy-target-price-revisions"
STUDY_ID = "TPR-CAP-TILT-EXT26-20261010-v1"
OPERATION_ID = "TPR-EXT26-SOURCE-CAPTURE-20261010-001"
PRIVATE_ROOT = LANE_ROOT / "artifacts" / "target_price_extended" / STUDY_ID / "source_capture"
SOURCE_RELATIVE = "research/target_price_revisions_qc/extended_source_capture.py"
DRIVER_RELATIVE = "research/target_price_revisions_qc/extended_source_capture_driver.py"
PUBLIC_HASHES = {
    "research/target_price_revisions_qc/extended_source_capture_freeze.json": "23beda591abf29af63e0bad1fad4b94f7e8f49e6d64ca4d36d4c85b8ded87a2d",
    "research/target_price_revisions_qc/extended_source_probe_aggregate.json": "8fc3b1d2264ed8feb6e63e1e6f1e603abcffc2a9ff8757155639791ad48111a0",
    "research/target_price_revisions_qc/extended_study_freeze.json": "90bdec5520b29bd932a3ec730f7c4c40c544ea7582731ad6680ef34ea8cf4067",
    "research/target_price_revisions_qc/extended_calendar.json": "3eccdf3cf9a2542ffd249983241d5747c2ecd4e21bc4a71f7f826c77ec1fe53d",
}
SOURCE_PATHS = (SOURCE_RELATIVE, DRIVER_RELATIVE, probe.SOURCE_RELATIVE,
                *probe.HELPER_PATHS, *PUBLIC_HASHES)
MASSIVE_FIELDS = ("benzinga_id", "benzinga_firm_id", "ticker", "date", "last_updated",
                  "currency", "price_target_action", "price_target", "previous_price_target")
CSV_FIELDS = {"tickers": ("ticker", "permaticker", "figi", "category", "exchange", "isdelisted"),
              "actions": ("ticker", "date", "action", "contraticker")}
CSV_QUERY = {
    "tickers": {"fields": ",".join(CSV_FIELDS["tickers"]), "format": "csv", "limit": "10000",
                "sort": "ticker.asc", "table": "stocks"},
    "actions": {"fields": ",".join(CSV_FIELDS["actions"]), "format": "csv", "limit": "10000",
                "sort": "date.asc", "to": "2026-10-09"},
}
LIMITS = {"max_elapsed_seconds": 5400, "max_requests": 2240,
          "max_response_bytes": 4 * 1024**3, "request_seconds": 30, "redirects": 0, "retries": 0}
DATASET_LIMITS = {"tickers": {"pages": 64, "rows": 640000, "bytes": 256 * 1024**2},
                  "actions": {"pages": 128, "rows": 1280000, "bytes": 512 * 1024**2}}
MASSIVE_PAGE_BYTES, CSV_PAGE_BYTES = 2 * 1024**2, 4 * 1024**2
MASSIVE_PAGES, MASSIVE_ROWS, WINDOW_PAGES = 2048, 2048000, 64
WINDOWS = tuple((f"{year:04}-{month:02}-01",
                 "2026-10-09" if (year, month) == (2026, 10)
                 else f"{year:04}-{month:02}-{calendar.monthrange(year, month)[1]:02}")
                for year in range(2020, 2027) for month in range(1, 13)
                if (2020, 9) <= (year, month) <= (2026, 10))
_open_directory = probe._open_directory
_read_source = probe._read_source
_FIXED_RESOLVER = helper._production_credential
_FIXED_OPEN = probe._open_directory
_FIXED_READ = probe._read_source
INDEX_NAME = OPERATION_ID + ".source-index.json"
PUBLIC_KEYS = frozenset({"schema", "operation_id", "study_id", "status", "scope_spent",
    "reserved_requests", "attempted_requests", "successful_requests", "response_bytes", "source_rows", "row_refusals",
    "identical_duplicate_rows", "conflicting_duplicate_rows", "terminated_massive_windows",
    "terminated_sharadar_datasets", "capture_complete", "source_input_admitted", "point_in_time_data",
    "rights_verified", "outcome_reads", "development_looks", "quantconnect_attempts",
    "canonical_admission", "trading"})


class CaptureError(ValueError):
    """Closed failure; never expose provider, row, cursor or credential values."""


def _fail(message):
    raise CaptureError(message)


def _canonical(body):
    try:
        return helper._canonical(body)
    except (ValueError, TypeError, OverflowError):
        _fail("capture serialization refused")


def _scope():
    return {"windows": [list(window) for window in WINDOWS], "limits": dict(LIMITS),
        "massive": {"host": "api.massive.com", "endpoint": "/benzinga/v1/ratings",
            "fields": list(MASSIVE_FIELDS), "page_bytes": MASSIVE_PAGE_BYTES,
            "max_pages": MASSIVE_PAGES, "max_rows": MASSIVE_ROWS,
            "pages_each_window": WINDOW_PAGES, "limit": "1000", "sort": "date.asc"},
        "sharadar": {"host": "api.sharadar.com", "page_bytes": CSV_PAGE_BYTES,
            "queries": {key: dict(value) for key, value in CSV_QUERY.items()},
            "limits": {key: dict(value) for key, value in DATASET_LIMITS.items()}}}


@dataclass(frozen=True)
class CapturePlan:
    payload: bytes
    sha256: str

    def body(self):
        if (type(self.payload) is not bytes or not 0 < len(self.payload) <= 32768
                or probe._digest(self.payload) != probe._hash(self.sha256)):
            _fail("capture plan identity refused")
        try:
            body = helper._source_object(self.payload)
            expected = freeze_capture_plan(source_hashes=body["source_hashes"],
                git_sha=body["git_sha"], owner_instruction_sha256=body["owner_instruction_sha256"],
                created_utc=body["created_utc"], expires_utc=body["expires_utc"], mode=body["mode"])
            if expected.payload != self.payload:
                _fail("capture plan differs from fixed scope")
            return body
        except (KeyError, TypeError, ValueError):
            _fail("capture plan policy refused")


def freeze_capture_plan(*, source_hashes, git_sha, owner_instruction_sha256,
                        created_utc, expires_utc, mode="production"):
    """Bind the complete local closure, not just this module or a driver hash."""
    if type(source_hashes) is not dict or set(source_hashes) != set(SOURCE_PATHS):
        _fail("capture requires complete fixed source inventory")
    for value in source_hashes.values():
        probe._hash(value)
    for path, expected in PUBLIC_HASHES.items():
        if source_hashes[path] != expected:
            _fail("capture public freeze identity refused")
    probe._hash(git_sha, 40)
    probe._hash(owner_instruction_sha256)
    if type(mode) is not str or mode not in ("production", "offline-fixture"):
        _fail("capture mode refused")
    created, expires = probe._clock(created_utc), probe._clock(expires_utc)
    if not created < expires <= created + timedelta(hours=48):
        _fail("capture expiry refused")
    body = {"schema": "tpr-extended-source-capture-plan-v1", "operation_id": OPERATION_ID,
        "study_id": STUDY_ID, "mode": mode, "source_hashes": dict(source_hashes),
        "git_sha": git_sha, "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "lane_root": str(LANE_ROOT), "lane_branch": LANE_BRANCH, "private_root": str(PRIVATE_ROOT),
        "scope": _scope(), "old_receipts_renewed": False, "point_in_time_data": False,
        "rights_verified": False, "outcome_access": False, "quantconnect": False,
        "canonical_admission": False, "trading": False, "original_wire_retention_private": True,
        "working_authorization": "owner-scoped-private-development-not-provider-attestation"}
    payload = _canonical(body)
    return CapturePlan(payload, probe._digest(payload))


def _verify_imports():
    if (Path(__file__) != LANE_ROOT / SOURCE_RELATIVE or probe.LANE_ROOT != LANE_ROOT
            or probe.LANE_BRANCH != LANE_BRANCH
            or Path(probe.__file__) != LANE_ROOT / probe.SOURCE_RELATIVE
            or Path(helper.__file__) != LANE_ROOT / "research/target_price_revisions_development/source_audit.py"):
        _fail("capture imported module identity refused")
    for function, relative in ((_open_directory, probe.SOURCE_RELATIVE),
        (_read_source, probe.SOURCE_RELATIVE),
        (helper._production_credential, "research/target_price_revisions_development/source_audit.py")):
        if type(function) is not FunctionType or Path(function.__code__.co_filename) != LANE_ROOT / relative:
            _fail("capture imported function identity refused")
    if (helper._production_credential is not _FIXED_RESOLVER or _read_source is not _FIXED_READ
            or _open_directory is not _FIXED_OPEN or _https_get is not _FIXED_TRANSPORT):
        _fail("capture production adapter substitution refused")


def _verify_execution_identity(body):
    _verify_imports()
    try:
        for relative, expected in body["source_hashes"].items():
            probe._git_identity(body)
            if probe._digest(_read_source(relative)) != expected:
                _fail("capture local source hash mismatch")
            probe._git_identity(body)
            committed = subprocess.run(["git", "show", body["git_sha"] + ":" + relative],
                cwd=LANE_ROOT, capture_output=True, timeout=5, check=True).stdout
            if type(committed) is not bytes or len(committed) > 262144 or probe._digest(committed) != expected:
                _fail("capture committed source hash mismatch")
        probe._git_identity(body)
    except (OSError, UnicodeError, subprocess.SubprocessError, probe.ProbeError):
        _fail("capture source custody unavailable")


def _private_directory(path, mode):
    if mode == "production" and path != PRIVATE_ROOT:
        _fail("capture private root refused")
    if mode == "offline-fixture" and (path == PRIVATE_ROOT or path.is_relative_to(LANE_ROOT)):
        _fail("capture fixture requires synthetic external root")
    descriptor = _open_directory(path)
    metadata = os.fstat(descriptor)
    if (metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700
            or not stat.S_ISDIR(metadata.st_mode)):
        os.close(descriptor)
        _fail("capture private custody refused")
    return descriptor


def _publish(directory, name, body):
    try:
        helper._publish(directory, name, _canonical(body))
    except (OSError, helper.SourceAuditError):
        _fail("capture publication unavailable; preserve spent scope")


def _claim(directory, name, body):
    try:
        probe._claim(directory, name, body)
    except probe.ProbeError:
        _fail("capture claim refused; scope remains spent")


@contextmanager
def _deadline(seconds):
    if (type(seconds) not in (int, float) or not 0 < seconds <= 30
            or threading.current_thread() is not threading.main_thread()
            or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0)):
        _fail("capture request deadline refused")
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_args):
        _fail("capture request deadline expired")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _massive_query(window, cursor=None):
    if window not in WINDOWS:
        _fail("capture window refused")
    body = {"date.gte": window[0], "date.lte": window[1], "limit": "1000", "sort": "date.asc"}
    if cursor is not None:
        if type(cursor) is not str or not 0 < len(cursor) <= 8192 or any(ord(c) < 33 or ord(c) > 126 for c in cursor):
            _fail("capture cursor refused")
        body["cursor"] = cursor
    return tuple(sorted(body.items()))


def _sharadar_query(dataset, page):
    if dataset not in CSV_QUERY or type(page) is not int or not 0 <= page < DATASET_LIMITS[dataset]["pages"]:
        _fail("capture CSV page refused")
    return tuple(sorted({**CSV_QUERY[dataset], "skip": str(page * 10000)}.items()))


def _transport_scope(provider, dataset, query):
    if type(query) is not tuple or any(type(pair) is not tuple or len(pair) != 2
        or any(type(value) is not str for value in pair) for pair in query):
        _fail("capture request query refused")
    body = dict(query)
    if len(body) != len(query):
        _fail("capture request query refused")
    if provider == "massive" and dataset == "ratings":
        window = (body.get("date.gte"), body.get("date.lte"))
        if query != _massive_query(window, body.get("cursor")):
            _fail("capture Massive scope refused")
        return "api.massive.com", "/benzinga/v1/ratings", MASSIVE_PAGE_BYTES, "application/json"
    if provider == "sharadar" and dataset in CSV_QUERY:
        skip = body.get("skip", "")
        if re.fullmatch(r"0|[1-9][0-9]{0,7}", skip) is None or int(skip) % 10000:
            _fail("capture CSV offset refused")
        if query != _sharadar_query(dataset, int(skip) // 10000):
            _fail("capture CSV scope refused")
        return "api.sharadar.com", "/v1.0/data/" + dataset, CSV_PAGE_BYTES, "text/csv"
    _fail("capture provider refused")


@dataclass(frozen=True)
class CaptureResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    complete: bool = True


def _framing(response, maximum, content_type):
    if (type(response) is not CaptureResponse or type(response.status) is not int
            or not 100 <= response.status <= 599 or type(response.headers) is not tuple
            or type(response.body) is not bytes or len(response.body) > maximum):
        _fail("capture response framing refused")
    recognized = {}
    for pair in response.headers:
        if (type(pair) is not tuple or len(pair) != 2 or any(type(value) is not str for value in pair)
                or pair[0] not in ("content-length", "content-type", "content-encoding")
                or pair[0] in recognized):
            _fail("capture response headers refused")
        recognized[pair[0]] = pair[1]
    length = recognized.get("content-length")
    media = recognized.get("content-type", content_type).split(";", 1)[0].lower().strip()
    permitted = ("text/csv", "application/csv", "text/plain", "application/octet-stream") if content_type == "text/csv" else ("application/json",)
    if (recognized.get("content-encoding", "identity").lower() != "identity" or media not in permitted
            or length is not None and (re.fullmatch(r"[0-9]{1,10}", length) is None
                                      or int(length) != len(response.body))):
        _fail("capture response headers refused")


def _https_get(provider, dataset, query, credential, seconds):
    host, endpoint, maximum, media = _transport_scope(provider, dataset, query)
    if not helper._valid_credential(credential):
        _fail("capture credential unavailable")
    connection = None
    try:
        with _deadline(seconds):
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname, context.verify_mode, context.keylog_filename = True, ssl.CERT_REQUIRED, None
            context.load_default_certs()
            connection = http.client.HTTPSConnection(host, 443, timeout=seconds, context=context)
            connection.set_debuglevel(0)
            query_items = query + (("api_key", credential),) if provider == "sharadar" else query
            headers = {"Accept": media, "Accept-Encoding": "identity", "Connection": "close",
                       "User-Agent": "TPR-extended-source-capture/1"}
            if provider == "massive":
                headers["Authorization"] = "Bearer " + credential
            connection.request("GET", endpoint + "?" + urlencode(query_items), headers=headers)
            response = connection.getresponse()
            kept = tuple((name.lower(), value) for name, value in response.getheaders()
                         if name.lower() in ("content-length", "content-type", "content-encoding"))
            values = dict(kept)
            declared = values.get("content-length")
            if (len(values) != len(kept) or declared is not None and
                    (re.fullmatch(r"[0-9]{1,10}", declared) is None or int(declared) > maximum)):
                return CaptureResponse(response.status, kept, b"", False)
            wire = response.read(maximum)
            complete = response.isclosed() and (declared is None or len(wire) == int(declared))
            return CaptureResponse(response.status, kept, wire, complete)
    except (OSError, http.client.HTTPException):
        _fail("capture HTTPS refused")
    finally:
        if connection is not None:
            connection.close()


_FIXED_TRANSPORT = _https_get


def _secret_guard(payload, credentials):
    """Refuse plain, JSON-escaped, URL-escaped and HTML-escaped echoes before hash/write."""
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeError:
        _fail("capture nontext response refused")
    current = text
    for _ in range(64):
        if any(credential in current for credential in credentials):
            _fail("capture credential echo refused")
        previous = current
        decoded = re.sub(r"\\(?:u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2}))",
            lambda match: chr(int(match.group(1) or match.group(2), 16)), previous)
        current = html.unescape(unquote(decoded))
        if current == previous:
            return text
    _fail("capture encoded response ambiguity refused")


def _next_query(body, window):
    value = body.get("next_url")
    if value is None:
        return None
    if type(value) is not str or not 0 < len(value) <= 16384:
        _fail("capture pagination type refused")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.netloc != "api.massive.com"
            or parsed.path != "/benzinga/v1/ratings" or parsed.fragment):
        _fail("capture pagination host refused")
    pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    values = dict(pairs)
    fixed = dict(_massive_query(window))
    if (len(values) != len(pairs) or set(values) - {"cursor", *fixed}
            or "cursor" not in values
            or any(values[key] != fixed[key] for key in fixed if key in values)):
        _fail("capture pagination filters refused")
    return _massive_query(window, values["cursor"])


def _scalar(value):
    if value is None or type(value) in (str, int, bool):
        if type(value) is str and (len(value) > 8192 or "\x00" in value):
            _fail("capture native scalar refused")
        return value
    if type(value) is Decimal:
        return str(value)
    _fail("capture native scalar refused")


def _massive_projection(payload, window, fetched, seen):
    try:
        body = helper._source_object(payload)
    except helper.SourceAuditError:
        _fail("capture Massive JSON refused")
    if body.get("status") != "OK" or type(body.get("results")) is not list or len(body["results"]) > 1000:
        _fail("capture Massive API schema refused")
    rows, refusals, duplicates, conflicts = [], 0, 0, 0
    previous_date = None
    for native in body["results"]:
        if type(native) is not dict:
            _fail("capture native revision row refused")
        row = {key: _scalar(native.get(key)) for key in MASSIVE_FIELDS}
        issued = row["date"]
        try:
            if type(issued) is not str or date.fromisoformat(issued).isoformat() != issued or not window[0] <= issued <= window[1]:
                _fail("capture revision date outside frozen month")
        except (ValueError, TypeError):
            _fail("capture revision date outside frozen month")
        if previous_date is not None and issued < previous_date:
            _fail("capture revision sorting refused")
        previous_date = issued
        reasons = []
        if not probe._native_id(row["benzinga_id"]) or not probe._native_id(row["benzinga_firm_id"]):
            reasons.append("invalid_native_id")
        if type(row["ticker"]) is not str or re.fullmatch(r"[A-Z][A-Z0-9.\-/]{0,31}", row["ticker"]) is None:
            reasons.append("invalid_native_ticker")
        try:
            touch = probe._clock(row["last_updated"])
            if touch.date().isoformat() < issued or touch > fetched:
                reasons.append("invalid_native_touch_order")
        except probe.ProbeError:
            reasons.append("invalid_native_touch_clock")
        nominal = probe._positive_target(row["price_target"]) and probe._positive_target(row["previous_price_target"])
        # Missing/nonpositive targets are visible source dispositions, not an
        # account-access denial or a zero-valued signal.
        disposition = "nominal_pair_present" if nominal else "nominal_pair_unavailable"
        if probe._native_id(row["benzinga_id"]):
            identity = (type(row["benzinga_id"]).__name__, row["benzinga_id"])
            signature = probe._digest(_canonical(row))
            if identity in seen:
                if seen[identity] == signature:
                    duplicates += 1
                else:
                    conflicts += 1
                    reasons.append("conflicting_native_event_id")
            else:
                seen[identity] = signature
        refusals += bool(reasons)
        rows.append({"source": row, "refusals": reasons, "nominal_disposition": disposition})
    return {"schema": "tpr-extended-massive-native-page-v1", "window": list(window),
            "rows": rows, "source_rows": len(rows), "row_refusals": refusals,
            "identical_duplicate_rows": duplicates, "conflicting_duplicate_rows": conflicts}, _next_query(body, window)


def _csv_projection(payload, dataset, seen):
    optional = "figi" if dataset == "tickers" else "contraticker"
    required = set(CSV_FIELDS[dataset]) - {optional}
    try:
        text = payload.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        # Native provider may ignore fields and add its other table columns.
        # Keep the exact original wire; project only frozen fields, never infer.
        if len(header) != len(set(header)) or not required <= set(header) or len(header) > 128:
            raise ValueError
        rows, refusals, duplicates, conflicts, previous = [], 0, 0, 0, None
        for cells in reader:
            if len(cells) != len(header) or len(rows) >= 10000:
                raise ValueError
            native = dict(zip(header, cells))
            row = {field: native.get(field) for field in CSV_FIELDS[dataset]}
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
                sorting = row["ticker"]
                identity = row["ticker"]
            else:
                try:
                    if date.fromisoformat(row["date"]).isoformat() != row["date"] or row["date"] > "2026-10-09":
                        reasons.append("action_after_frozen_end")
                except ValueError:
                    reasons.append("invalid_native_action_date")
                if not row["action"]:
                    reasons.append("missing_native_action")
                if row["contraticker"] and re.fullmatch(r"[A-Z][A-Z0-9.\-/]{0,31}", row["contraticker"]) is None:
                    reasons.append("invalid_native_contraticker")
                sorting = row["date"]
                identity = (row["ticker"], row["date"], row["action"], row["contraticker"])
            if previous is not None and sorting < previous:
                _fail("capture CSV sorting refused")
            previous = sorting
            signature = probe._digest(_canonical(row))
            if identity in seen:
                if seen[identity] == signature:
                    duplicates += 1
                else:
                    conflicts += 1
                    reasons.append("conflicting_native_identity")
            else:
                seen[identity] = signature
            refusals += bool(reasons)
            rows.append({"source": row, "refusals": reasons})
        return {"schema": "tpr-extended-sharadar-native-page-v1", "dataset": dataset,
            "rows": rows, "source_rows": len(rows), "row_refusals": refusals,
            "identical_duplicate_rows": duplicates, "conflicting_duplicate_rows": conflicts,
            "missing_optional_column": optional not in header,
            "current_vintage_not_point_in_time": True}
    except (UnicodeError, ValueError, TypeError, csv.Error, StopIteration):
        _fail("capture CSV structural schema refused")


@dataclass(frozen=True)
class CaptureResult:
    payload: bytes
    sha256: str
    index_path: Path


def execute_capture(plan):
    """Production-only. Exact committed closure verified before global claim."""
    if type(plan) is not CapturePlan or plan.body()["mode"] != "production":
        _fail("production capture requires exact production plan")
    _verify_execution_identity(plan.body())
    return _execute(plan, PRIVATE_ROOT, helper._production_credential, _https_get,
                    lambda: datetime.now(timezone.utc), time.monotonic)


def _execute_fixture_capture(plan, private_root, *, now, credential_resolver, transport, monotonic=lambda: 0.0):
    if (type(plan) is not CapturePlan or plan.body()["mode"] != "offline-fixture"
            or private_root.is_relative_to(LANE_ROOT) or not callable(credential_resolver)
            or not callable(transport) or not callable(monotonic)
            or credential_resolver in (_FIXED_RESOLVER, helper._production_credential)
            or transport in (_FIXED_TRANSPORT, _https_get)):
        _fail("fixture capture requires synthetic isolated adapters")
    return _execute(plan, private_root, credential_resolver, transport, lambda: now, monotonic)


def _execute(plan, private_root, resolver, transport, clock, monotonic):
    body = plan.body()
    started = clock()
    if (type(started) is not datetime or started.tzinfo is None or started.utcoffset() != timedelta(0)
            or not probe._clock(body["created_utc"]) <= started < probe._clock(body["expires_utc"])):
        _fail("capture outside frozen expiry")
    start_tick = monotonic()
    directory = _private_directory(private_root, body["mode"])
    state = {"reserved_requests": 0, "attempted_requests": 0, "successful_requests": 0, "response_bytes": 0,
        "source_rows": 0, "row_refusals": 0, "identical_duplicate_rows": 0,
        "conflicting_duplicate_rows": 0, "terminated_massive_windows": 0,
        "terminated_sharadar_datasets": 0}
    pages, credentials = [], {}
    census = [{"provider": "massive", "dataset": "ratings", "window": list(window),
               "pages": 0, "source_rows": 0, "terminated": False} for window in WINDOWS]
    census += [{"provider": "sharadar", "dataset": dataset, "window": None,
                "pages": 0, "source_rows": 0, "response_bytes": 0, "terminated": False}
               for dataset in ("tickers", "actions")]
    status = "FAILED"
    failure = "uninvoked"
    interrupted = False
    try:
        _claim(directory, OPERATION_ID + ".access.spent.json",
            {"schema": "tpr-extended-capture-access-spent-v1", "operation_id": OPERATION_ID,
             "plan_sha256": plan.sha256, "mode": body["mode"], "started_utc": started.isoformat()})
        _publish(directory, OPERATION_ID + ".plan.json", body)

        def fetch(provider, dataset, query, window=None, page=0):
            nonlocal failure
            current = clock()
            remaining = min(LIMITS["max_elapsed_seconds"] - (monotonic() - start_tick),
                            (probe._clock(body["expires_utc"]) - current).total_seconds())
            if (type(current) is not datetime or current.tzinfo is None or current < started
                    or remaining <= 0 or state["reserved_requests"] >= LIMITS["max_requests"]):
                _fail("capture elapsed or request bound hit")
            host, endpoint, maximum, media = _transport_scope(provider, dataset, query)
            remaining_bytes = LIMITS["max_response_bytes"] - state["response_bytes"]
            if remaining_bytes < maximum:
                _fail("capture aggregate byte bound hit")
            index = state["reserved_requests"] + 1
            prefix = f"request.{index:04}"
            # Never persist cursor values or query credentials in receipts.
            request = {"schema": "tpr-extended-capture-request-spent-v1", "operation_id": OPERATION_ID,
                "plan_sha256": plan.sha256, "request_index": index, "provider": provider,
                "dataset": dataset, "host": host, "endpoint": endpoint, "window": list(window) if window else None,
                "page": page, "offset": page * 10000 if provider == "sharadar" else None,
                "cursor_present": "cursor" in dict(query), "started_utc": current.isoformat()}
            _claim(directory, prefix + ".spent.json", request)
            state["reserved_requests"] += 1
            entry = {"request_index": index, "provider": provider, "dataset": dataset,
                "window": list(window) if window else None, "page": page, "http_status": None,
                "wire_file": None, "wire_sha256": None, "wire_bytes": 0,
                "received_bytes": None,
                "projection_file": None, "projection_sha256": None, "projection_bytes": 0,
                "response_complete": False, "disposition": "unknown_spent", "fetch_utc": current.isoformat()}
            pages.append(entry)
            try:
                if provider not in credentials:
                    credential = resolver(provider)
                    if (not helper._valid_credential(credential)
                            or body["mode"] == "offline-fixture" and not credential.startswith("SYNTHETIC_")):
                        _fail("capture credential unavailable")
                    credentials[provider] = credential
                # Credential resolution also consumes the same wall budget;
                # neither a late keychain response nor an expiry extends it.
                remaining = min(LIMITS["max_elapsed_seconds"] - (monotonic() - start_tick),
                    (probe._clock(body["expires_utc"]) - clock()).total_seconds())
                if remaining <= 0:
                    _fail("capture deadline hit before GET")
                state["attempted_requests"] += 1
                response = transport(provider, dataset, query, credentials[provider], min(30, remaining))
                entry["fetch_utc"] = clock().isoformat()
                if type(response) is CaptureResponse:
                    if type(response.status) is int and 100 <= response.status <= 599:
                        entry["http_status"] = response.status
                    if type(response.body) is bytes and len(response.body) <= maximum:
                        entry["received_bytes"] = len(response.body)
                        state["response_bytes"] += len(response.body)
                if clock() >= probe._clock(body["expires_utc"]) or monotonic() - start_tick >= LIMITS["max_elapsed_seconds"]:
                    _fail("capture operation deadline hit")
                _framing(response, maximum, media)
                entry["http_status"] = response.status
                entry["response_complete"] = response.complete is True
                _secret_guard(response.body, tuple(credentials.values()))
                if provider == "massive":
                    # A malformed JSON wire cannot be safely claimed decoded-
                    # secret-free; retain its refusal, never the malformed body.
                    parsed = helper._source_object(response.body)
                    if any(probe._echo(parsed, value) for value in credentials.values()):
                        _fail("capture credential echo refused")
                wire_name = prefix + (".wire.json" if provider == "massive" else ".wire.csv")
                helper._publish(directory, wire_name, response.body)
                entry.update(wire_file=wire_name, wire_sha256=probe._digest(response.body), wire_bytes=len(response.body))
                if response.status != 200 or response.complete is not True or not response.body:
                    _fail("capture HTTP or incomplete wire refused")
                entry["disposition"] = "wire_accepted"
                state["successful_requests"] += 1
                return response.body, entry
            except KeyboardInterrupt:
                entry["disposition"] = "interrupted_unknown_spent"
                raise
            except Exception:
                entry["disposition"] = "refused_unknown_spent"
                _fail("capture request refused; no retry")
            finally:
                _publish(directory, prefix + ".terminal.json", entry)

        def retain_projection(entry, projection):
            encoded = _canonical(projection)
            filename = f"request.{entry['request_index']:04}.projection.json"
            helper._publish(directory, filename, encoded)
            entry.update(projection_file=filename, projection_sha256=probe._digest(encoded),
                         projection_bytes=len(encoded), disposition="projected")
            for key in ("source_rows", "row_refusals", "identical_duplicate_rows", "conflicting_duplicate_rows"):
                state[key] += projection[key]

        try:
            massive_count, massive_rows, seen_events = 0, 0, {}
            for window_index, window in enumerate(WINDOWS):
                query, cursors, hashes, last_date = _massive_query(window), set(), set(), None
                window_row = census[window_index]
                for page in range(WINDOW_PAGES):
                    if massive_count >= MASSIVE_PAGES:
                        _fail("capture Massive page bound hit")
                    payload, entry = fetch("massive", "ratings", query, window, page)
                    massive_count += 1
                    if entry["wire_sha256"] in hashes:
                        _fail("capture repeated page refused")
                    hashes.add(entry["wire_sha256"])
                    projection, next_query = _massive_projection(payload, window, probe._clock(entry["fetch_utc"]), seen_events)
                    if projection["rows"]:
                        first = projection["rows"][0]["source"]["date"]
                        if last_date is not None and first < last_date:
                            _fail("capture Massive cross-page sorting refused")
                        last_date = projection["rows"][-1]["source"]["date"]
                    massive_rows += projection["source_rows"]
                    if massive_rows > MASSIVE_ROWS:
                        _fail("capture Massive row bound hit")
                    retain_projection(entry, projection)
                    window_row["pages"] += 1
                    window_row["source_rows"] += projection["source_rows"]
                    if next_query is None:
                        window_row["terminated"] = True
                        state["terminated_massive_windows"] += 1
                        break
                    cursor = dict(next_query)["cursor"]
                    if cursor in cursors:
                        _fail("capture repeated cursor refused")
                    cursors.add(cursor)
                    query = next_query
                if not window_row["terminated"]:
                    _fail("capture monthly pagination bound hit")
            for dataset_index, dataset in enumerate(("tickers", "actions")):
                dataset_row = census[74 + dataset_index]
                seen_rows, hashes, last_sort = {}, set(), None
                for page in range(DATASET_LIMITS[dataset]["pages"]):
                    if dataset_row["response_bytes"] + CSV_PAGE_BYTES > DATASET_LIMITS[dataset]["bytes"]:
                        _fail("capture CSV byte bound hit")
                    payload, entry = fetch("sharadar", dataset, _sharadar_query(dataset, page), page=page)
                    dataset_row["response_bytes"] += len(payload)
                    if entry["wire_sha256"] in hashes:
                        _fail("capture repeated CSV page refused")
                    hashes.add(entry["wire_sha256"])
                    projection = _csv_projection(payload, dataset, seen_rows)
                    sort_field = "ticker" if dataset == "tickers" else "date"
                    if projection["rows"]:
                        first = projection["rows"][0]["source"][sort_field]
                        if last_sort is not None and first < last_sort:
                            _fail("capture CSV cross-page sorting refused")
                        last_sort = projection["rows"][-1]["source"][sort_field]
                    dataset_row["source_rows"] += projection["source_rows"]
                    if dataset_row["source_rows"] > DATASET_LIMITS[dataset]["rows"]:
                        _fail("capture CSV row bound hit")
                    retain_projection(entry, projection)
                    dataset_row["pages"] += 1
                    if dataset == "actions" and any("action_after_frozen_end" in row["refusals"]
                                                    for row in projection["rows"]):
                        _fail("capture ACTIONS provider date scope refused")
                    if projection["source_rows"] < 10000:
                        dataset_row["terminated"] = True
                        state["terminated_sharadar_datasets"] += 1
                        break
                if not dataset_row["terminated"]:
                    _fail("capture CSV pagination bound hit")
            if clock() >= probe._clock(body["expires_utc"]) or monotonic() - start_tick >= LIMITS["max_elapsed_seconds"]:
                _fail("capture deadline hit after projection")
            status, failure = "COMPLETED", None
        except KeyboardInterrupt:
            status, failure, interrupted = "INTERRUPTED", "interrupted_unknown_spent", True
        except Exception:
            status, failure = "FAILED", "refused_or_bound_hit_no_retry"

        complete = status == "COMPLETED" and state["terminated_massive_windows"] == 74 and state["terminated_sharadar_datasets"] == 2
        report = {"schema": "tpr-extended-source-capture-report-v1", "operation_id": OPERATION_ID,
            "study_id": STUDY_ID, "status": status, "scope_spent": True, **state,
            "capture_complete": complete, "source_input_admitted": False,
            "point_in_time_data": False, "rights_verified": False, "outcome_reads": 0,
            "development_looks": 0, "quantconnect_attempts": 0, "canonical_admission": False, "trading": False}
        if set(report) != PUBLIC_KEYS:
            _fail("capture public report schema refused")
        index = {"schema": "tpr-extended-source-index-v1", "operation_id": OPERATION_ID,
            "study_id": STUDY_ID, "plan_sha256": plan.sha256, "git_sha": body["git_sha"],
            "source_hashes": body["source_hashes"], "started_utc": started.isoformat(),
            "ended_utc": clock().isoformat(), "pages": pages, "census": census,
            "failure": failure, "report": report, "point_in_time_data": False,
            "action_history_no_lower_bound": True, "current_vintage_identity": True,
            "count_semantics": {"response_bytes": "observed bounded wire bytes including unpersisted refusals",
                                "source_rows": "parsed retained native projections, not unknown refused bodies",
                                "successful_requests": "complete HTTP200 wires, not signal admission"},
            "terminated_pagination_not_transaction_snapshot": True}
        _publish(directory, INDEX_NAME, index)
        _publish(directory, OPERATION_ID + ".aggregate.json", report)
        _publish(directory, OPERATION_ID + ".terminal.json",
            {"schema": "tpr-extended-capture-terminal-v1", "operation_id": OPERATION_ID,
             "plan_sha256": plan.sha256, "index_sha256": probe._digest(_canonical(index)),
             "status": status, "scope_spent": True, "outcome_reads": 0,
             "development_looks": 0, "quantconnect_attempts": 0})
        if interrupted:
            raise KeyboardInterrupt("capture interrupted; preserve spent scope") from None
        payload = _canonical(report)
        return CaptureResult(payload, probe._digest(payload), private_root / INDEX_NAME)
    finally:
        credentials.clear()
        os.close(directory)
