"""Bounded read-only qualification of the owner's retained FirstRate USB data.

This is source quality and coverage, never source admission or a backtest.
Only fixed daily, corporate-action, listing and earnings inputs are selected.
No download URL, credential, price, EPS value or ticker is in public output.
Files remain on the USB; no archive is extracted and no supplied code executes.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import stat
import struct
import subprocess
import sys
import time
import weakref
import zipfile
import zlib

from research import insider_buying_sec_feed_archive_format_v3 as native
from research import insider_buying_pilot_2021_2025 as pilot
from research import insider_buying_pilot_massive_evidence_readback_v1 as ipc

SCHEMA = "insider-pilot-firstrate-usb-qualification-v1"
SELF_PATH = "research/insider_buying_pilot_firstrate_qualification_v1.py"
TEST_PATH = "tests/test_insider_buying_pilot_firstrate_qualification_v1.py"
USB_ROOT = Path("/Volumes/SANDISK/firstrate")
LANE_ROOT = native.LANE_ROOT
MANIFEST_BYTES = 327907
MANIFEST_SHA256 = "c681af584244d38e3f9dea2ff765cc2c991cb383107a3e542115a4338ee4cdf8"
ACTUAL_CALENDAR_SHA256 = "cf89f63750992981001461030434ee95776b1f4b387f95084514fb42e5958aae"
ACTUAL_PLAN_SHA256 = "f74310ade5bb09047b0b2edc3a25b3f40608289857bc9575e8b7310b9e349037"
MAX_MANIFEST = 1024 * 1024
MAX_FILE = 2 * 1024**3
MAX_COMPRESSED_TOTAL = 16 * 1024**3
MAX_MEMBER = 16 * 1024**2
MAX_ZIP_DECODED = 8 * 1024**3
MAX_TOTAL_DECODED = 32 * 1024**3
MAX_CENTRAL = 16 * 1024**2
MAX_MEMBERS = 50000
MAX_LINE = 65536
MAX_ROWS = 200000000
WORKER_SECONDS = 1800
MAX_IPC_INPUT = 256 * 1024
MAX_IPC_OUTPUT = 128 * 1024 * 1024
WINDOW_START, WINDOW_END = "2020-10-01", "2025-12-31"
MARKET_START, MARKET_END = "2019-10-01", "2026-06-30"
PILOT_START, PILOT_END = "2021-01-01", "2025-12-31"
STOCK = "market/Stocks_Complete_10_000+_Tickers"
ETF = "market/ETF-Complete_5000+_Tickers"
EARNINGS = "fundamentals/Earnings_Calendar_Estimates_Surprises"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MD5 = re.compile(r"[0-9a-f]{32}\Z")
_NAME = re.compile(r"[A-Za-z0-9^][A-Za-z0-9._+ ^-]{0,199}\Z")
_ZIP_COMPONENT = re.compile(r"[A-Za-z0-9^_][A-Za-z0-9._+ ^-]{0,199}\Z")
_NUMBER = re.compile(r"[+-]?[0-9]{1,24}(?:\.[0-9]{1,24})?(?:[eE][+-]?[0-9]{1,3})?\Z")
_TOKEN = object()
_SEALS = weakref.WeakKeyDictionary()
_WORKER_CODES = frozenset({"source_qualification_refused", "source_changed", "source_custody_refused",
    "source_cleanup_refused", "source_resource_refused", "manifest_external_pin_refused", "manifest_schema_refused",
    "selected_manifest_record_refused", "selected_path_refused", "selected_inventory_refused",
    "selected_file_integrity_refused", "source_scope_refused", "zip_magic_refused", "zip_structure_refused",
    "zip_member_refused", "zip_resource_refused", "decoded_resource_refused", "row_resource_refused",
    "row_encoding_refused", "row_csv_refused", "earnings_header_refused", "listing_header_refused",
    "calendar_refused", "native_refused", "worker_deadline_refused", "worker_ipc_refused", "worker_process_refused"})


class FirstRateQualificationError(ValueError):
    """Finite own codes only; supplied source and OS text remain private."""


def _need(ok, code):
    if not ok:
        raise FirstRateQualificationError(code)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _authority():
    return {"source_authenticated": False, "historical_identity_verified": False,
        "historical_public_known_by_verified": False, "point_in_time_data": False,
        "actual_earnings_status_verified": False, "rights_verified": False,
        "canonical_admitted": False, "full_population_complete": False,
        "backtesting_ready": False, "qc_jobs": 0, "outcome_looks": 0, "backtests": 0}


def safe_failure(error):
    return str(error) if type(error) is FirstRateQualificationError and str(error) in _WORKER_CODES else "native_refused"


def _ipc_result(stdout, stderr, returncode):
    _need(type(stdout) is bytes and len(stdout) <= MAX_IPC_OUTPUT + 1 and stdout.endswith(b"\n")
        and type(stderr) is bytes and len(stderr) <= 4096, "worker_ipc_refused")
    _need(returncode in {0, 2} and type(returncode) is int and not stderr, "worker_process_refused")
    def pairs(items):
        value = {}
        for key, child in items:
            _need(key not in value, "worker_ipc_refused"); value[key] = child
        return value
    try:
        value = json.loads(stdout[:-1], object_pairs_hook=pairs,
            parse_float=lambda _: _need(False, "worker_ipc_refused"),
            parse_constant=lambda _: _need(False, "worker_ipc_refused"))
        _need(type(value) is dict and _raw(value) + b"\n" == stdout and type(value.get("ok")) is bool,
            "worker_ipc_refused")
        if value["ok"] is False:
            _need(set(value) == {"ok", "code"} and type(value["code"]) is str
                and value["code"] in _WORKER_CODES, "worker_ipc_refused")
            raise FirstRateQualificationError(value["code"])
        _need(returncode == 0 and set(value) == {"ok", "value"} and type(value["value"]) is dict,
            "worker_ipc_refused")
        return value["value"]
    except FirstRateQualificationError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise FirstRateQualificationError("worker_ipc_refused") from None


def _launch(command, payload=b"", *, timeout=WORKER_SECONDS):
    """Trusted-parent bounded IPC only; this helper does NOT choose an input scope.

    Main supplies the independently qualified fixed native command. Reusing
    the existing bounded cleanup does not call any Massive source operation.
    """
    _need(type(payload) is bytes and len(payload) <= MAX_IPC_INPUT and type(timeout) is int
        and 1 <= timeout <= WORKER_SECONDS and isinstance(command, (tuple, list))
        and command and all(type(v) is str and len(v) <= 256 * 1024 for v in command), "worker_ipc_refused")
    process = poll = None; accepted = False
    try:
        process = subprocess.Popen(command, cwd=LANE_ROOT, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        poll = selectors.DefaultSelector()
        output, errors, offset = bytearray(), bytearray(), 0
        for stream in (process.stdin, process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
        if payload:
            poll.register(process.stdin, selectors.EVENT_WRITE, "input")
        else:
            process.stdin.close()
        poll.register(process.stdout, selectors.EVENT_READ, output)
        poll.register(process.stderr, selectors.EVENT_READ, errors)
        deadline = time.monotonic() + timeout
        while poll.get_map():
            remaining = deadline - time.monotonic()
            _need(remaining > 0, "worker_deadline_refused")
            for key, _ in poll.select(min(0.2, remaining)):
                if key.data == "input":
                    try: count = os.write(key.fileobj.fileno(), memoryview(payload)[offset:offset+65536])
                    except BlockingIOError: continue
                    _need(type(count) is int and count > 0, "worker_process_refused")
                    offset += count
                    if offset == len(payload):
                        poll.unregister(key.fileobj); key.fileobj.close()
                    continue
                cap = 4096 if key.data is errors else MAX_IPC_OUTPUT + 1
                try: chunk = os.read(key.fileobj.fileno(), min(65536, cap + 1 - len(key.data)))
                except BlockingIOError: continue
                if chunk:
                    key.data.extend(chunk)
                    _need(len(key.data) <= cap, "worker_ipc_refused")
                else:
                    poll.unregister(key.fileobj)
        _need(offset == len(payload), "worker_process_refused")
        remaining = deadline - time.monotonic()
        _need(remaining > 0, "worker_deadline_refused")
        result = _ipc_result(bytes(output), bytes(errors), process.wait(timeout=remaining))
        accepted = True
        return result
    except FirstRateQualificationError:
        raise
    except subprocess.TimeoutExpired:
        raise FirstRateQualificationError("worker_deadline_refused") from None
    except Exception:
        raise FirstRateQualificationError("worker_process_refused") from None
    finally:
        primary = sys.exc_info()[0] is not None
        stdin_closed = True
        if process is not None and process.stdin is not None:
            try: process.stdin.close()
            except Exception: stdin_closed = False
        clean = ipc._cleanup(process, poll, failed=not accepted)
        _need(primary or clean and stdin_closed, "worker_process_refused")


def _manifest(raw, expected, *, actual):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_MANIFEST and type(expected) is str
        and _SHA.fullmatch(expected) and _sha(raw) == expected, "manifest_external_pin_refused")
    if actual:
        _need(expected == MANIFEST_SHA256 and len(raw) == MANIFEST_BYTES, "manifest_external_pin_refused")
    def pairs(items):
        value = {}
        for key, child in items:
            _need(key not in value, "manifest_schema_refused")
            value[key] = child
        return value
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
            parse_constant=lambda _: _need(False, "manifest_schema_refused"))
        _need(type(value) is dict and 1 <= len(value) <= 2000, "manifest_schema_refused")
        if actual:
            _need(len(value) == 769, "manifest_schema_refused")
        return value
    except FirstRateQualificationError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise FirstRateQualificationError("manifest_schema_refused") from None


def _kind(key):
    """Exact scope, independent of attacker-supplied URL/path destinations."""
    for family, prefix in (("stock", STOCK), ("etf", ETF)):
        if key in {prefix + "/Read_Me_Documentation", prefix + "/Ticker_Listing"}:
            return family + ("_readme" if key.endswith("Documentation") else "_listing")
        if re.fullmatch(re.escape(prefix) + r"/Tickers_[A-Z]_Day_Unadjusted_Full_Dataset", key):
            return family + "_daily"
        if family == "stock" and re.fullmatch(re.escape(prefix) + r"/1-Day_Unadjusted_Archive_[1-5]", key):
            return "stock_daily"
        if family == "stock" and key == prefix + "/1-Day_Unadjusted_2025+_Delisted_tickers":
            return "stock_daily"
        if re.fullmatch(re.escape(prefix) + r"/(?:Stocks?|ETF)_Dividends", key):
            return family + "_dividends"
        if re.fullmatch(re.escape(prefix) + r"/(?:Stocks?|ETF)_Splits", key):
            return family + "_splits"
    if key == EARNINGS + "/Full_Dataset":
        return "earnings"
    if key == EARNINGS + "/Read_Me_Documentation":
        return "earnings_readme"
    return None


def selected_records(manifest, *, actual):
    selected, names = [], set()
    for key, record in manifest.items():
        _need(type(key) is str, "manifest_schema_refused")
        kind = _kind(key)
        if kind is None:
            continue
        _need(type(record) is dict and set(record) == {"bytes", "fetched", "md5", "ok", "path", "url"}
            and record["ok"] is True and type(record["bytes"]) is int and 0 < record["bytes"] <= MAX_FILE
            and type(record["md5"]) is str and _MD5.fullmatch(record["md5"]), "selected_manifest_record_refused")
        # URL/fetched are deliberately neither interpreted as instructions nor exported.
        _need(type(record["path"]) is str and len(record["path"]) <= 4096
            and type(record["url"]) is str and len(record["url"]) <= 16384
            and type(record["fetched"]) is str and len(record["fetched"]) <= 128,
            "selected_manifest_record_refused")
        supplied = record["path"].replace("\\", "/")
        positions = [supplied.find(stem) for stem in ("market/", "fundamentals/") if supplied.find(stem) >= 0]
        _need(bool(positions), "selected_path_refused")
        relative = supplied[min(positions):]
        path = PurePosixPath(relative)
        _need(not path.is_absolute() and path.as_posix() == relative and all(part not in {"", ".", ".."}
            and _NAME.fullmatch(part) for part in path.parts) and path.suffix.lower() in {".txt", ".zip"}
            and str(path.with_suffix("")) == key and relative not in names, "selected_path_refused")
        names.add(relative)
        selected.append({"relative": relative, "kind": kind, "bytes": record["bytes"], "md5": record["md5"]})
    counts = Counter(row["kind"] for row in selected)
    expected = {"stock_daily": 32, "etf_daily": 26, "stock_listing": 1, "etf_listing": 1,
        "stock_readme": 1, "etf_readme": 1, "stock_dividends": 1, "stock_splits": 1,
        "etf_dividends": 1, "etf_splits": 1, "earnings": 1, "earnings_readme": 1}
    _need(bool(selected) and (not actual or dict(counts) == expected), "selected_inventory_refused")
    _need(sum(row["bytes"] for row in selected) <= MAX_COMPRESSED_TOTAL, "source_resource_refused")
    return sorted(selected, key=lambda row: row["relative"])


def _version(info):
    # exFAT ownership/mode and ctime are not claimed as private immutable custody.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size, info.st_mtime_ns)


class _HeldSource:
    """No-follow ancestry and open selected regular files; never an output writer."""
    def __init__(self, root):
        self.root, self.fds, self.leaves = Path(root), [], {}
        try:
            _need(self.root.is_absolute() and ".." not in self.root.parts, "source_custody_refused")
            fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fds.append((fd, None, None, _version(os.fstat(fd))))
            for part in self.root.parts[1:]:
                parent = fd
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                self.fds.append((fd, parent, part, _version(os.fstat(fd))))
            self.rootfd = fd
        except BaseException:
            self.close()
            raise

    def open(self, relative, cap):
        parts = PurePosixPath(relative).parts
        _need(parts and not relative.startswith("/") and all(p not in {"", ".", ".."} for p in parts), "source_custody_refused")
        directory, parents, leaf_fd = self.rootfd, [], None
        try:
            for name in parts[:-1]:
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                parents.append((child, directory, name, _version(os.fstat(child))))
                directory = child
            info = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            _need(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= cap, "source_custody_refused")
            leaf_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            _need(_version(os.fstat(leaf_fd)) == _version(info), "source_custody_refused")
            value = {"fd": leaf_fd, "parent": directory, "name": parts[-1], "version": _version(info),
                "parents": parents, "sha256": None, "md5": None, "bytes": info.st_size}
            _need(relative not in self.leaves, "source_custody_refused")
            self.leaves[relative] = value
            leaf_fd = None
            return value
        except BaseException:
            if leaf_fd is not None:
                os.close(leaf_fd)
            for child, *_ in reversed(parents):
                os.close(child)
            raise

    def hash(self, value):
        os.lseek(value["fd"], 0, os.SEEK_SET)
        sha, md5, size = hashlib.sha256(), hashlib.md5(), 0
        while chunk := os.read(value["fd"], 1024 * 1024):
            size += len(chunk)
            _need(size <= value["bytes"], "source_changed")
            sha.update(chunk); md5.update(chunk)
        _need(size == value["bytes"], "source_changed")
        current = (sha.hexdigest(), md5.hexdigest())
        _need(value["sha256"] is None or current == (value["sha256"], value["md5"]), "source_changed")
        value["sha256"], value["md5"] = current
        self.check_versions()
        return current

    def check_versions(self):
        for fd, parent, name, version in self.fds:
            current = _version(os.fstat(fd))
            _need(current[:3] == version[:3], "source_changed")
            if parent is not None:
                _need(_version(os.stat(name, dir_fd=parent, follow_symlinks=False))[:3] == version[:3], "source_changed")
        for value in self.leaves.values():
            _need(_version(os.fstat(value["fd"])) == value["version"] == _version(os.stat(
                value["name"], dir_fd=value["parent"], follow_symlinks=False)), "source_changed")
            for fd, parent, name, version in value["parents"]:
                _need(_version(os.fstat(fd))[:3] == version[:3] == _version(os.stat(
                    name, dir_fd=parent, follow_symlinks=False))[:3], "source_changed")

    def close(self):
        primary, failed = sys.exc_info()[0] is not None, False
        handles = [v["fd"] for v in self.leaves.values()]
        handles += [item[0] for v in self.leaves.values() for item in reversed(v["parents"])]
        handles += [item[0] for item in reversed(self.fds)]
        for fd in handles:
            try: os.close(fd)
            except OSError: failed = True
        self.leaves, self.fds = {}, []
        if failed and not primary:
            raise FirstRateQualificationError("source_cleanup_refused")


def _zip_members(stream):
    """Bound central-directory allocation BEFORE ZipFile constructs its index."""
    stream.seek(0, os.SEEK_END); size = stream.tell()
    _need(22 <= size <= MAX_FILE, "zip_resource_refused")
    stream.seek(max(0, size - 65557)); tail = stream.read(65557)
    at = tail.rfind(bytes((80, 75, 5, 6)))
    _need(at >= 0 and len(tail) - at >= 22, "zip_structure_refused")
    fields = struct.unpack_from("<4s4H2LH", tail, at)
    _, disk, central_disk, on_disk, members, central_bytes, offset, comment = fields
    absolute = max(0, size - 65557) + at
    _need(disk == central_disk == 0 and on_disk == members and 0 < members < 65535
        and members <= MAX_MEMBERS and central_bytes <= MAX_CENTRAL and offset + central_bytes == absolute
        and comment <= 4096 and at + 22 + comment == len(tail)
        and offset != 0xffffffff and central_bytes != 0xffffffff, "zip_structure_refused")
    stream.seek(0)
    archive = zipfile.ZipFile(stream)
    try:
        rows = archive.infolist()
        _need(len(rows) == members, "zip_structure_refused")
        seen, decoded = set(), 0
        for item in rows:
            name = PurePosixPath(item.filename)
            _need(not name.is_absolute() and name.as_posix() == item.filename.rstrip("/")
                and 1 <= len(name.parts) <= 3 and all(p not in {"", ".", ".."} and _ZIP_COMPONENT.fullmatch(p) for p in name.parts)
                and item.filename not in seen and not stat.S_ISLNK(item.external_attr >> 16)
                and not item.flag_bits & 1 and item.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED},
                "zip_member_refused")
            seen.add(item.filename)
            _need(0 <= item.file_size <= MAX_MEMBER and 0 <= item.compress_size <= MAX_FILE
                and (item.file_size == 0 or item.compress_size > 0)
                and item.file_size <= max(1, item.compress_size) * 2000, "zip_resource_refused")
            decoded += item.file_size
        _need(decoded <= MAX_ZIP_DECODED, "zip_resource_refused")
        return archive, rows, decoded
    except BaseException:
        archive.close()
        raise


def _lines(stream, budget):
    while raw := stream.readline(MAX_LINE + 1):
        _need(len(raw) <= MAX_LINE, "row_resource_refused")
        budget[0] += len(raw)
        _need(budget[0] <= MAX_TOTAL_DECODED, "decoded_resource_refused")
        try: text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try: text = raw.decode("cp1252")
            except UnicodeDecodeError: raise FirstRateQualificationError("row_encoding_refused") from None
        try:
            row = next(csv.reader([text], strict=True))
            _need(len(row) <= 32 and all(len(v) <= 16384 for v in row), "row_resource_refused")
            yield row
        except (csv.Error, StopIteration):
            raise FirstRateQualificationError("row_csv_refused") from None


def _day(text):
    if type(text) is not str:
        return None
    try:
        if len(text) == 10 and date.fromisoformat(text).isoformat() == text:
            return text
        if len(text) == 19 and text.endswith(" 00:00:00"):
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            if parsed.strftime("%Y-%m-%d %H:%M:%S") == text:
                return text[:10]
    except ValueError:
        pass
    return None


def _number(text):
    if type(text) is not str or len(text) > 64 or not _NUMBER.fullmatch(text):
        return None
    try:
        value = Decimal(text)
        return value if value.is_finite() and abs(value.as_tuple().exponent) <= 100 else None
    except (InvalidOperation, ValueError):
        return None


def _label(name):
    stem = PurePosixPath(name).stem
    return re.sub(r"(?:_full_1day_UNADJUSTED|_earnings|_divs|_splits)$", "", stem)


def _daily(rows):
    result = {"rows": 0, "dated_rows": 0, "window_rows": 0, "pre_window_rows": 0, "post_window_rows": 0,
        "numeric_rows_examined": 0, "zero_volume_rows": 0, "first_date": None, "last_date": None,
        "pilot_rows": 0, "calendar_2020_rows": 0, "maturity_tail_rows": 0, "market_envelope_rows": 0,
        "post_market_envelope_rows": 0,
        "duplicate_dates": 0, "out_of_order_dates": 0, "quality_reasons": Counter(), "years": Counter(),
        "market_envelope_year_bitmaps": {}}
    seen, previous = set(), None
    for physical_ordinal, row in enumerate(rows):
        if physical_ordinal == 0 and [x.lower() for x in row] == ["timestamp", "open", "high", "low", "close", "volume"]:
            continue
        result["rows"] += 1
        _need(result["rows"] <= MAX_ROWS, "row_resource_refused")
        if len(row) != 6:
            result["quality_reasons"]["six_columns_required"] += 1
            continue
        day = _day(row[0])
        if day is None:
            result["quality_reasons"]["date_refused"] += 1
            continue
        result["dated_rows"] += 1; result["years"][day[:4]] += 1
        result["first_date"] = min(result["first_date"] or day, day)
        result["last_date"] = max(result["last_date"] or day, day)
        result["duplicate_dates"] += int(day in seen)
        result["out_of_order_dates"] += int(previous is not None and day < previous)
        seen.add(day); previous = day
        result["window_rows" if WINDOW_START <= day <= WINDOW_END else "pre_window_rows" if day < WINDOW_START else "post_window_rows"] += 1
        result["pilot_rows"] += int(PILOT_START <= day <= PILOT_END)
        result["calendar_2020_rows"] += int("2020-01-01" <= day <= "2020-12-31")
        result["maturity_tail_rows"] += int("2026-01-01" <= day <= "2026-03-30")
        result["post_market_envelope_rows"] += int(day > MARKET_END)
        if not MARKET_START <= day <= MARKET_END:
            continue  # Outside the frozen market envelope, numeric values stay opaque.
        result["market_envelope_rows"] += 1
        stamp = date.fromisoformat(day)
        offset = (stamp - date(stamp.year, 1, 1)).days
        bitmap = result["market_envelope_year_bitmaps"]
        bitmap[day[:4]] = bitmap.get(day[:4], 0) | (1 << offset)
        result["numeric_rows_examined"] += 1
        values = tuple(_number(v) for v in row[1:])
        if any(v is None for v in values):
            result["quality_reasons"]["numeric_refused"] += 1
            continue
        opening, high, low, close, volume = values
        if any(v <= 0 for v in values[:4]) or volume < 0:
            result["quality_reasons"]["nonpositive_price_or_negative_volume"] += 1
        elif not low <= opening <= high or not low <= close <= high:
            result["quality_reasons"]["OHLC_bounds_refused"] += 1
        result["zero_volume_rows"] += int(volume == 0)
    if result["rows"] == 0:
        result["quality_reasons"]["empty_price_member"] += 1
    result["quality_reasons"], result["years"] = dict(result["quality_reasons"]), dict(result["years"])
    result["market_envelope_year_bitmaps"] = {key: format(value, "x") for key, value in result["market_envelope_year_bitmaps"].items()}
    return result


def _earnings(rows, *, buffered_interval=None):
    _need(buffered_interval is None or type(buffered_interval) is tuple and len(buffered_interval) == 2
        and all(_day(value) is not None for value in buffered_interval)
        and buffered_interval[0] <= buffered_interval[1], "calendar_refused")
    head = next(rows, None)
    _need(head == ["date", "eps_estimate", "eps_reported", "release_time"], "earnings_header_refused")
    result = {"rows": 0, "window_rows": 0, "invalid_date_rows": 0, "invalid_width_rows": 0,
        "nonblank_reported_rows_in_window": 0, "release_time_counts_in_window": Counter(),
        "provider_reported_candidate_rows_in_window": 0, "malformed_reported_rows_in_window": 0,
        "buffered_rows": 0, "buffered_provider_reported_candidate_rows": 0, "buffered_unknown_reported_rows": 0,
        "buffered_malformed_reported_rows": 0, "buffered_release_time_counts": Counter(),
        "buffered_interval": list(buffered_interval) if buffered_interval is not None else None,
        "first_date": None, "last_date": None, "duplicate_dates": 0}
    seen = set()
    for row in rows:
        result["rows"] += 1
        _need(result["rows"] <= MAX_ROWS, "row_resource_refused")
        if len(row) != 4:
            result["invalid_width_rows"] += 1
            continue
        day = _day(row[0])
        if day is None:
            result["invalid_date_rows"] += 1
            continue
        result["duplicate_dates"] += int(day in seen); seen.add(day)
        result["first_date"] = min(result["first_date"] or day, day)
        result["last_date"] = max(result["last_date"] or day, day)
        in_window = WINDOW_START <= day <= WINDOW_END
        in_buffer = buffered_interval is not None and buffered_interval[0] <= day <= buffered_interval[1]
        release = row[3] if row[3] in {"before_open", "after_close", ""} else "other_uninterpreted"
        reported = _number(row[2]) if (in_window or in_buffer) and row[2] else None
        candidate, malformed = bool(row[2]) and reported is not None, bool(row[2]) and reported is None
        if in_window:
            result["window_rows"] += 1
            result["nonblank_reported_rows_in_window"] += int(bool(row[2]))
            result["provider_reported_candidate_rows_in_window"] += int(candidate)
            result["malformed_reported_rows_in_window"] += int(malformed)
            result["release_time_counts_in_window"][release or "unknown"] += 1
        if in_buffer:
            result["buffered_rows"] += 1
            result["buffered_provider_reported_candidate_rows"] += int(candidate)
            result["buffered_unknown_reported_rows"] += int(not row[2])
            result["buffered_malformed_reported_rows"] += int(malformed)
            result["buffered_release_time_counts"][release or "unknown"] += 1
    result["release_time_counts_in_window"] = dict(result["release_time_counts_in_window"])
    result["buffered_release_time_counts"] = dict(result["buffered_release_time_counts"])
    # Missing timing can use the existing whole-civil-date interval diagnostic;
    # it is not an automatic diagnostic failure or an inferred actual status.
    return result


def _listing(rows):
    _need(next(rows, None) == ["Ticker", "Name", "First Date", "Last Date"], "listing_header_refused")
    result = {"rows": 0, "invalid_width_rows": 0, "invalid_label_rows": 0,
        "invalid_date_rows": 0, "duplicate_labels": 0, "labels": {}}
    for row in rows:
        result["rows"] += 1
        _need(result["rows"] <= 100000, "row_resource_refused")
        if len(row) != 4:
            result["invalid_width_rows"] += 1
            continue
        label = row[0]
        if not re.fullmatch(r"[A-Za-z0-9^][A-Za-z0-9._+^\-]{0,99}", label):
            result["invalid_label_rows"] += 1
            continue
        first, last = _day(row[2]), _day(row[3])
        result["invalid_date_rows"] += int(first is None or last is None or first > last)
        records = result["labels"].setdefault(label, [])
        result["duplicate_labels"] += int(bool(records))
        records.append({"first_date": first, "last_date": last, "name_sha256": _sha(row[1].encode())})
    return result


def _actions(rows, *, split=False):
    """Headerless source date/value pairs; no return/adjustment calculation."""
    result = {"rows": 0, "invalid_width_rows": 0, "invalid_date_rows": 0,
        "numeric_rows_examined": 0, "invalid_numeric_rows": 0, "duplicate_dates": 0,
        "market_envelope_rows": 0, "first_date": None, "last_date": None}
    seen = set()
    for row in rows:
        result["rows"] += 1
        _need(result["rows"] <= MAX_ROWS, "row_resource_refused")
        if len(row) != 2:
            result["invalid_width_rows"] += 1
            continue
        day = _day(row[0])
        if day is None:
            result["invalid_date_rows"] += 1
            continue
        result["first_date"] = min(result["first_date"] or day, day)
        result["last_date"] = max(result["last_date"] or day, day)
        result["duplicate_dates"] += int(day in seen); seen.add(day)
        if MARKET_START <= day <= MARKET_END:
            result["market_envelope_rows"] += 1
            result["numeric_rows_examined"] += 1
            value = _number(row[1])
            result["invalid_numeric_rows"] += int(value is None or value < 0 or split and value == 0)
    return result


def _archive_coverage(leaf, kind, budget, memory, *, earnings_interval=None):
    _need(os.pread(leaf["fd"], 4, 0) == bytes((80, 75, 3, 4)), "zip_magic_refused")
    with os.fdopen(os.dup(leaf["fd"]), "rb") as stream:
        archive, members, declared = _zip_members(stream)
        try:
            _need(budget[1] + declared <= MAX_TOTAL_DECODED, "decoded_resource_refused")
            budget[1] += declared
            coverage = {}
            for item in members:
                memory.check()
                if item.is_dir():
                    continue
                _need(PurePosixPath(item.filename).suffix.lower() in {".txt", ".csv"}, "zip_member_refused")
                with archive.open(item) as member:
                    rows = _lines(member, budget)
                    value = _daily(rows) if kind.endswith("_daily") else _earnings(rows, buffered_interval=earnings_interval) if kind == "earnings" else _actions(rows, split=kind.endswith("_splits"))
                    _need(member.read(1) == b"", "zip_member_refused")
                # Keep duplicate source labels separately rather than deduplicate a universe.
                coverage[item.filename] = {"source_label": _label(item.filename), **value}
            memory.check()
            return coverage
        finally:
            archive.close()


def _aggregate(coverage):
    summary = {"files_by_kind": Counter(), "members_by_kind": Counter(), "rows_by_kind": Counter(),
        "price_quality_reasons": Counter(), "price_rows_in_market_envelope": 0,
        "price_numeric_rows_examined": 0, "price_rows_2020": 0, "price_rows_maturity_tail": 0,
        "price_rows_pilot": 0, "price_rows_after_envelope": 0, "zero_volume_price_rows": 0,
        "duplicate_price_dates": 0, "out_of_order_price_dates": 0,
        "earnings_rows_in_required_window": 0, "earnings_nonblank_reported_rows_in_required_window": 0,
        "earnings_provider_reported_candidate_rows_in_required_window": 0, "earnings_malformed_reported_rows_in_required_window": 0,
        "earnings_buffered_rows": 0, "earnings_buffered_provider_reported_candidate_rows": 0,
        "earnings_buffered_unknown_reported_rows": 0, "earnings_buffered_malformed_reported_rows": 0,
        "earnings_buffered_release_time_counts": Counter(),
        "earnings_release_time_counts_in_required_window": Counter(), "earnings_invalid_rows": 0,
        "action_invalid_rows": 0, "listing_quality_counts": Counter(), "membership_reconciliation": {}}
    labels = {"stock": Counter(), "etf": Counter()}
    listing_sets = {}
    for file in coverage.values():
        kind = file["kind"]; summary["files_by_kind"][kind] += 1
        if kind.endswith("_listing"):
            value = file["listing"]
            listing_sets[kind.split("_")[0]] = set(value["labels"])
            for key in ("rows", "invalid_width_rows", "invalid_label_rows", "invalid_date_rows", "duplicate_labels"):
                summary["listing_quality_counts"][kind + "/" + key] += value[key]
            continue
        members = file.get("members", {})
        summary["members_by_kind"][kind] += len(members)
        for value in members.values():
            summary["rows_by_kind"][kind] += value["rows"]
            if kind.endswith("_daily"):
                labels[kind.split("_")[0]][value["source_label"]] += 1
                summary["price_quality_reasons"].update(value["quality_reasons"])
                for source, target in (("market_envelope_rows", "price_rows_in_market_envelope"),
                    ("numeric_rows_examined", "price_numeric_rows_examined"), ("calendar_2020_rows", "price_rows_2020"),
                    ("maturity_tail_rows", "price_rows_maturity_tail"), ("pilot_rows", "price_rows_pilot"),
                    ("post_market_envelope_rows", "price_rows_after_envelope"), ("zero_volume_rows", "zero_volume_price_rows"),
                    ("duplicate_dates", "duplicate_price_dates"), ("out_of_order_dates", "out_of_order_price_dates")):
                    summary[target] += value[source]
            elif kind == "earnings":
                summary["earnings_rows_in_required_window"] += value["window_rows"]
                summary["earnings_nonblank_reported_rows_in_required_window"] += value["nonblank_reported_rows_in_window"]
                summary["earnings_provider_reported_candidate_rows_in_required_window"] += value["provider_reported_candidate_rows_in_window"]
                summary["earnings_malformed_reported_rows_in_required_window"] += value["malformed_reported_rows_in_window"]
                for key in ("buffered_rows", "buffered_provider_reported_candidate_rows", "buffered_unknown_reported_rows", "buffered_malformed_reported_rows"):
                    summary["earnings_" + key] += value[key]
                summary["earnings_buffered_release_time_counts"].update(value["buffered_release_time_counts"])
                summary["earnings_release_time_counts_in_required_window"].update(value["release_time_counts_in_window"])
                summary["earnings_invalid_rows"] += value["invalid_date_rows"] + value["invalid_width_rows"]
            elif kind.endswith(("_dividends", "_splits")):
                summary["action_invalid_rows"] += value["invalid_date_rows"] + value["invalid_width_rows"] + value["invalid_numeric_rows"]
    for family, body_labels in labels.items():
        listed = listing_sets.get(family, set())
        summary["membership_reconciliation"][family] = {"listed_unique_labels": len(listed),
            "daily_unique_labels": len(body_labels), "daily_duplicate_labels": sum(n - 1 for n in body_labels.values()),
            "listed_without_daily_label": len(listed - set(body_labels)),
            "daily_label_absent_from_listing": len(set(body_labels) - listed),
            "exact_labels_are_historical_identities": False}
    return {key: dict(value) if isinstance(value, Counter) else value for key, value in summary.items()}


def _calendar_plan(raw, *, actual):
    _need(type(raw) is bytes and 0 < len(raw) <= pilot.MAX_BYTES, "calendar_refused")
    digest = _sha(raw)
    if actual:
        _need(digest == ACTUAL_CALENDAR_SHA256, "calendar_refused")
    try:
        plan = pilot.freeze_pilot_2021_2025(calendar_raw=raw, expected_calendar_sha256=digest)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise FirstRateQualificationError("calendar_refused") from None
    if actual:
        _need(plan.sha256 == ACTUAL_PLAN_SHA256, "calendar_refused")
    return plan


def _date_masks(days):
    value = {}
    for day in days:
        stamp = date.fromisoformat(day)
        offset = (stamp - date(stamp.year, 1, 1)).days
        value[day[:4]] = value.get(day[:4], 0) | (1 << offset)
    return value


def _calendar_comparison(coverage, plan, *, actual):
    body = pilot._plan(plan)  # Genuine factory, never a caller dictionary/seal clone.
    if actual:
        _need(body["calendar_sha256"] == ACTUAL_CALENDAR_SHA256 and plan.sha256 == ACTUAL_PLAN_SHA256,
            "calendar_refused")
    dates = [row["session"] for row in body["calendar_sessions"]]
    entries = [i for i, day in enumerate(dates) if PILOT_START <= day <= PILOT_END]
    first, last = entries[0], entries[-1]
    groups = {"full_envelope": dates, "first_253_warmup": dates[first-253:first],
        "pilot": dates[first:last+1], "last_60_maturity": dates[last+1:last+61]}
    masks = {name: _date_masks(days) for name, days in groups.items()}
    total = {"pilot_plan_sha256": plan.sha256, "calendar_sha256": body["calendar_sha256"],
        "expected_date_counts": {name: len(days) for name, days in groups.items()},
        "members_examined": 0, "members_complete_date_presence_by_scope": Counter(),
        "missing_date_presence_cells_by_scope": Counter(), "extra_noncalendar_date_presence_cells": 0,
        "date_presence_is_not_valid_bar_admission": True, "historical_listing_seasoning_verified": False,
        "SEC_cohort_membership_or_identity_verified": False, "calendar_authenticity_verified_here": False,
        "missing_dates_reconstructible_from_fixed_calendar_and_observed_bitmaps": True}
    for file in coverage.values():
        if not file["kind"].endswith("_daily"):
            continue
        for value in file["members"].values():
            observed = {year: int(bits, 16) for year, bits in value["market_envelope_year_bitmaps"].items()}
            comparison = {}
            for name, expected in masks.items():
                missing = {year: bits & ~observed.get(year, 0) for year, bits in expected.items()}
                count = sum(bits.bit_count() for bits in missing.values())
                # Missing sets are exactly derivable from the fixed calendar
                # and already retained observed bitmaps; do not duplicate four
                # near-identical bitmap sets in the protected IPC catalogue.
                comparison[name] = {"missing_count": count}
                total["members_complete_date_presence_by_scope"][name] += int(count == 0)
                total["missing_date_presence_cells_by_scope"][name] += count
            extra = sum((bits & ~masks["full_envelope"].get(year, 0)).bit_count() for year, bits in observed.items())
            comparison["extra_noncalendar_date_count"] = extra
            value["pilot_calendar_date_comparison"] = comparison
            total["extra_noncalendar_date_presence_cells"] += extra
            total["members_examined"] += 1
    for key in ("members_complete_date_presence_by_scope", "missing_date_presence_cells_by_scope"):
        total[key] = dict(total[key])
    return total


def _qualify(root, manifest_sha256, *, actual, memory, plan=None):
    held = None
    try:
        _need(type(actual) is bool, "source_scope_refused")
        if actual:
            _need(Path(root) == USB_ROOT and manifest_sha256 == MANIFEST_SHA256
                and type(memory) is native._WorkerMemoryGuard, "native_refused")
            native._isolated(); native.batch.campaign.base._prove_isolation()
            body = pilot._plan(plan)
            _need(body["calendar_sha256"] == ACTUAL_CALENDAR_SHA256 and plan.sha256 == ACTUAL_PLAN_SHA256,
                "calendar_refused")
        memory.check()
        earnings_interval = None
        if plan is not None:
            context = pilot._plan(plan)["context"]
            earnings_interval = (context["required_earnings_first_civil_date"], context["required_earnings_last_civil_date"])
        held = _HeldSource(root)
        manifest = held.open("manifest.json", MAX_MANIFEST)
        held.hash(manifest)
        _need(manifest["sha256"] == manifest_sha256, "manifest_external_pin_refused")
        manifest_raw = os.pread(manifest["fd"], manifest["bytes"], 0)
        records = selected_records(_manifest(manifest_raw, manifest_sha256, actual=actual), actual=actual)
        coverage, pins, budget = {}, {}, [0, 0]
        for record in records:
            memory.check(); held.check_versions()
            leaf = held.open(record["relative"], MAX_FILE)
            digest, md5 = held.hash(leaf)
            _need(leaf["bytes"] == record["bytes"] and md5 == record["md5"], "selected_file_integrity_refused")
            kind = record["kind"]
            value = {"kind": kind}
            if kind.endswith("_readme"):
                _need(leaf["bytes"] <= MAX_LINE, "source_resource_refused")
                # Hash only: supplied prose is untrusted source data, never instructions.
                value["readme_text_interpreted"] = False
            elif kind.endswith("_listing"):
                with os.fdopen(os.dup(leaf["fd"]), "rb") as stream:
                    stream.seek(0); value["listing"] = _listing(_lines(stream, budget))
            else:
                value["members"] = _archive_coverage(leaf, kind, budget, memory, earnings_interval=earnings_interval)
            pins[record["relative"]] = {"sha256": digest, "bytes": leaf["bytes"], "manifest_md5_match": True}
            coverage[record["relative"]] = value
            held.hash(leaf); memory.check()
        # Final byte rehash of EVERY held input, not only metadata versions.
        for leaf in held.leaves.values():
            held.hash(leaf); memory.check()
        held.check_versions()
        comparison = _calendar_comparison(coverage, plan, actual=actual) if plan is not None else None
        payload = {"schema": SCHEMA, "fixture_only": not actual, "manifest_sha256": manifest_sha256,
            "selected_file_pins": pins, "selected_file_count": len(records), "audit_completed": True,
            "market_quality_interval": [MARKET_START, MARKET_END], "earnings_count_interval": [WINDOW_START, WINDOW_END],
            "earnings_diagnostic_buffered_interval": list(earnings_interval) if earnings_interval is not None else None,
            "decoded_bytes_streamed": budget[0], "zip_declared_decoded_bytes": budget[1],
            "summary": _aggregate(coverage), "calendar_date_comparison": comparison, "private_coverage": coverage,
            "exfat_private_modes_or_immutable_snapshot_claimed": False,
            "historical_version_archive_supplied": False, "earnings_actual_status_inferred_from_reported_presence": False,
            "blank_earnings_time_is_automatic_failure": False, "new_requests": 0, "credential_reads": 0,
            "financial_returns_or_signals_computed": False, "authority": _authority()}
        result = FirstRateQualification(_raw(payload), _TOKEN); _SEALS[result] = result._bytes
        memory.check()
        return result
    except FirstRateQualificationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, zipfile.BadZipFile, RuntimeError, zlib.error, EOFError):
        raise FirstRateQualificationError("source_qualification_refused") from None
    finally:
        if held is not None:
            held.close()


def qualify_invented(root, *, expected_manifest_sha256, memory, calendar_raw=None):
    """Caller fixtures remain fixtures even when supplied pins are coherent."""
    path = Path(root).absolute()
    resolved = path.resolve()
    _need(not resolved.is_relative_to(USB_ROOT) and not resolved.is_relative_to(LANE_ROOT), "fixture_root_refused")
    plan = _calendar_plan(calendar_raw, actual=False) if calendar_raw is not None else None
    return _qualify(path, expected_manifest_sha256, actual=False, memory=memory, plan=plan)


def qualify_actual(*, memory, calendar_raw):
    """Fixed USB scope inside the separately qualified initial native fence.

    Keep the real caller-owned guard live through serialization, stdout flush
    and a final sample. This function has no launcher, writer or fallback.
    """
    _need(Path(__file__).resolve() == LANE_ROOT / SELF_PATH and type(memory) is native._WorkerMemoryGuard,
        "native_refused")
    native._isolated(); native.batch.campaign.base._prove_isolation(); memory.check()
    plan = _calendar_plan(calendar_raw, actual=True)
    return _qualify(USB_ROOT, MANIFEST_SHA256, actual=True, memory=memory, plan=plan)


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class FirstRateQualification:
    _bytes: bytes = field(repr=False)
    _token: object = field(repr=False)

    def canonical_bytes(self):
        _need(type(self) is FirstRateQualification and self._token is _TOKEN
            and _SEALS.get(self) == self._bytes, "genuine_qualification_required")
        return self._bytes

    @property
    def sha256(self):
        return _sha(self.canonical_bytes())


def public_summary(result):
    _need(type(result) is FirstRateQualification, "genuine_qualification_required")
    payload = json.loads(result.canonical_bytes())
    coverage = payload.pop("private_coverage")
    return {**payload, "private_coverage_sha256": _sha(_raw(coverage)), "qualification_sha256": result.sha256}


def private_coverage(result):
    _need(type(result) is FirstRateQualification, "genuine_qualification_required")
    return json.loads(result.canonical_bytes())["private_coverage"]
