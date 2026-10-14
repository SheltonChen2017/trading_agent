"""Three exact purchased Earnings metadata requests under private custody.

Production requires the fixed research path, a clean committed lane and
preregistration; private drafts cannot run the actual route.
The three months corroborate missing post-2010 metadata, not January 2006.
Scheduled/confirmed dates are not authenticated actual-release events. Values
of financial numeric tokens are never computed or projected. Raw successful
bytes remain private; this runner has no prices, QC jobs, outcomes or orders.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
from datetime import date
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import socket
import stat
import subprocess
import sys
import time
from typing import Callable
from urllib import error, request
from urllib.parse import parse_qsl, urlsplit

from research import insider_buying_benzinga_earnings_access as previous
from research import insider_buying_earnings_archive_assessment_runner as custody
from research import insider_buying_sec_2006q1_parent_bootstrap as custody_tree
from research.insider_buying_eodhd_earnings_demo import (
    FALSE_FLAGS, _git, _read_leaf, _sha, _version,
)
from research.insider_buying_provider_metadata_audit import _exclusive_json, _now
from research.insider_buying_provider_metadata_transport import ProviderMetadataResponse, _DenyRedirect

LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
LANE_BRANCH = "codex/strategy-insider-buying"
SELF_PATH = "research/insider_buying_benzinga_earnings_gap_capture_v1.py"
ARTIFACT_PARTS = ("artifacts", "insider_buying", "benzinga_earnings_gap_capture_v1")
SCHEMA = "insider-benzinga-three-missing-months-custody-v1"
OWNER_DIRECTION = "owner:2026-10-13:purchased-earnings-continuous-build"
WINDOWS = (("2018-08-01", "2018-08-31"), ("2019-02-01", "2019-02-28"),
           ("2020-02-01", "2020-02-29"))
MAX_ROWS = 50_000
MAX_BODY_BYTES = 16 * 1024**2
MAX_METADATA_BYTES = 256 * 1024**2
MAX_CONTROL_BYTES = 1024**2
MIN_FREE_BYTES = 4 * 1024**3
TIMEOUT_SECONDS = 20
COOLDOWN_SECONDS = 1.0
SOURCE_FILES = ("research/__init__.py", SELF_PATH,
    "research/insider_buying_benzinga_earnings_access.py",
    "research/insider_buying_eodhd_earnings_demo.py",
    "research/insider_buying_provider_metadata_audit.py",
    "research/insider_buying_provider_metadata_transport.py", "research/quantconnect.py",
    "research/insider_buying_earnings_archive_assessment_runner.py",
    "research/insider_buying_sec_2006q1_parent_bootstrap.py")
PREVIOUS_ID = "ib-earnings-access-20261007-owner-confirmed-once"
PREVIOUS_HASHES = {
    "reservation.json": "63eeced18e64a0b684c091eefa5cacb1778609bc431f307e836502b978681f76",
    "started.json": "a2979484c870e452c937235414afb2ade15deb275a45aa8ca0b650ec7e7af726",
    "successful-response.json": "11032221048364fd88e1b35d1a92790274719503f91c4a028827da9cdb50e945",
    "complete.json": "81bd2401ff26251428fb1ed278960a174d626f9ed8446902509464122de910ba",
}
_FINANCIAL = previous._FINANCIAL_FIELDS
_ROW_FIELDS = previous._ROW_FIELDS
_NUMBER = object()
_NUMERIC = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
_TRANSPORT_CODES = previous._TRANSPORT_FAILURES
_SCHEMA_CODES = frozenset({"credential_echo_refused", "source_json_refused", "duplicate_json_key",
    "nonfinite_number_refused", "number_lexeme_refused", "envelope_refused", "row_count_refused",
    "source_count_refused", "request_id_refused", "pagination_url_refused", "row_schema_refused",
    "source_field_refused", "window_date_refused", "schedule_time_refused", "date_status_refused",
    "updated_timestamp_refused", "metadata_byte_bound_exceeded"})


class EarningsGapError(ValueError):
    """A fixed sanitized code, never provider text, caller values or secrets."""


_CAPTURE_PHASES = frozenset({"preflight", "guard_current_identity", "guard_previous_access", "guard_current_journal"})


def _capture_diagnostic(exc):
    supplied = getattr(exc, "_earnings_capture_failure_diagnostic", None)
    allowed_categories = {"earnings_gap_error", "os_error", "value_error", "type_error", "key_error", "unclassified_error"}
    if (type(supplied) is dict and set(supplied) == {"phase", "exception_category", "recognized_os_errno"}
        and type(supplied["phase"]) is str and supplied["phase"] in _CAPTURE_PHASES
        and type(supplied["exception_category"]) is str and supplied["exception_category"] in allowed_categories
        and (supplied["recognized_os_errno"] is None or type(supplied["recognized_os_errno"]) is int
             and supplied["recognized_os_errno"] in {1, 2, 5, 9, 13, 17, 20, 24, 28, 30, 35})):
        return dict(supplied)
    phase = getattr(exc, "_earnings_capture_failure_phase", None)
    if type(phase) is not str or phase not in _CAPTURE_PHASES:
        phase = "preflight"
    categories = ((EarningsGapError, "earnings_gap_error"), (OSError, "os_error"),
                  (ValueError, "value_error"), (TypeError, "type_error"), (KeyError, "key_error"))
    category = next((name for kind, name in categories if isinstance(exc, kind)), "unclassified_error")
    number = exc.errno if isinstance(exc, OSError) else None
    if type(number) is not int or number not in {1, 2, 5, 9, 13, 17, 20, 24, 28, 30, 35}:
        number = None
    return {"phase": phase, "exception_category": category, "recognized_os_errno": number}


def _capture_at_phase(phase, function, *args, **kwargs):
    _require(type(phase) is str and phase in _CAPTURE_PHASES, "internal_capture_phase_refused")
    try:
        return function(*args, **kwargs)
    except Exception as exc:
        exc._earnings_capture_failure_phase = phase
        raise


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EarningsGapError(code)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _json(raw: bytes) -> dict:
    try:
        result = json.loads(raw, object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise EarningsGapError("control_json_refused") from None
    _require(type(result) is dict and _canonical(result) == raw, "control_json_refused")
    return result


def _url(window: tuple[str, str]) -> str:
    _require(type(window) is tuple and window in WINDOWS, "fixed_window_refused")
    return ("https://api.massive.com/benzinga/v1/earnings?date.gte=" + window[0] +
            "&date.lte=" + window[1] + "&limit=50000&sort=date.asc")


URLS = tuple(_url(window) for window in WINDOWS)


@dataclass(frozen=True, slots=True)
class EarningsGapRequest:
    url: str
    headers: tuple[tuple[str, str], ...] = field(repr=False)
    method: str = "GET"
    timeout_seconds: int = TIMEOUT_SECONDS

    def __repr__(self) -> str:
        return "EarningsGapRequest(<fixed month; credential redacted>)"


def _validate_request(item: EarningsGapRequest) -> None:
    _require(type(item) is EarningsGapRequest and type(item.url) is str and item.url in URLS and
        type(item.method) is str and item.method == "GET" and type(item.timeout_seconds) is int and
        item.timeout_seconds == TIMEOUT_SECONDS and type(item.headers) is tuple and
        all(type(pair) is tuple and len(pair) == 2 and all(type(v) is str for v in pair)
            for pair in item.headers), "fixed_request_refused")
    headers = dict(item.headers)
    _require(len(headers) == len(item.headers) and set(headers) == {"Accept", "Accept-Encoding", "Authorization"}
        and headers["Accept"] == "application/json" and headers["Accept-Encoding"] == "identity" and
        re.fullmatch(r"Bearer [!-~]{1,4096}", headers["Authorization"]) is not None,
        "fixed_request_refused")


def _read_bounded(stream, status: int) -> ProviderMetadataResponse:
    """One bounded read, including strict observed HTTP framing."""
    pieces, count, declared = [], 0, None
    try:
        if not callable(getattr(stream.headers, "get_all", None)):
            return ProviderMetadataResponse(status, b"", False, "partial-read")
        encoding = stream.headers.get_all("Content-Encoding", [])
        lengths = stream.headers.get_all("Content-Length", [])
        transfers = stream.headers.get_all("Transfer-Encoding", [])
        if not all(type(values) is list and all(type(v) is str for v in values)
                   for values in (encoding, lengths, transfers)):
            return ProviderMetadataResponse(status, b"", False, "partial-read")
        if len(encoding) > 1 or encoding and encoding[0].strip().lower() != "identity":
            return ProviderMetadataResponse(status, b"", False, "unsupported-content-encoding")
        if len(lengths) > 1:
            return ProviderMetadataResponse(status, b"", False, "invalid-content-length")
        if len(transfers) > 1 or transfers and (lengths or transfers[0].strip().lower() != "chunked"):
            return ProviderMetadataResponse(status, b"", False, "partial-read")
        if lengths:
            if re.fullmatch(r"[0-9]{1,20}", lengths[0]) is None:
                return ProviderMetadataResponse(status, b"", False, "invalid-content-length")
            declared = int(lengths[0])
            if declared > MAX_BODY_BYTES:
                return ProviderMetadataResponse(status, b"", False, "oversized-response")
        while count <= MAX_BODY_BYTES:
            requested = min(65536, MAX_BODY_BYTES + 1 - count)
            chunk = stream.read(requested)
            if type(chunk) is not bytes or len(chunk) > requested:
                return ProviderMetadataResponse(status, b"", False, "partial-read")
            if not chunk:
                raw = b"".join(pieces)
                if declared is not None and declared != count:
                    return ProviderMetadataResponse(status, raw, False, "truncated-response")
                return ProviderMetadataResponse(status, raw)
            pieces.append(chunk)
            count += len(chunk)
        return ProviderMetadataResponse(status, b"", False, "oversized-response")
    except Exception:
        return ProviderMetadataResponse(status, b"", False, "partial-read")


def _default_transport(item: EarningsGapRequest) -> ProviderMetadataResponse:
    _validate_request(item)
    stream = None
    try:
        opener = request.build_opener(request.ProxyHandler({}), _DenyRedirect(),
            request.HTTPSHandler(context=ssl.create_default_context()))
        try:
            stream = opener.open(request.Request(item.url, headers=dict(item.headers), method="GET"),
                                 timeout=TIMEOUT_SECONDS)
        except error.HTTPError as exc:
            stream = exc
        status = stream.getcode()
        if type(status) is not int or not 100 <= status <= 599:
            return ProviderMetadataResponse(None, b"", False, "invalid-http-status")
        if stream.geturl() != item.url:
            return ProviderMetadataResponse(status, b"", False, "response-origin-mismatch")
        observed = _read_bounded(stream, status)
        if 300 <= status < 400:
            return ProviderMetadataResponse(status, b"", False, "redirect-refused")
        return observed
    except TimeoutError:
        return ProviderMetadataResponse(None, b"", False, "transport-timeout")
    except error.URLError as exc:
        code = "transport-timeout" if isinstance(exc.reason, TimeoutError) else "transport-error"
        return ProviderMetadataResponse(None, b"", False, code)
    except Exception:
        return ProviderMetadataResponse(None, b"", False, "transport-error")
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate_json_key")
        # This hook runs on every nested object. It MUST NOT interpret any
        # number, including a nested key named count inside an invalid row.
        result[key] = value
    return result


@dataclass(frozen=True, slots=True, repr=False)
class _LexicalNumber:
    lexeme: str


def _number(text: str) -> _LexicalNumber:
    _require(type(text) is str and len(text) <= 128 and _NUMERIC.fullmatch(text) is not None,
             "number_lexeme_refused")
    # Bounds limit both significand and exponent length without evaluating it.
    exponent = re.split("[eE]", text)
    _require(len(exponent) == 1 or len(exponent[1].lstrip("+-")) <= 4,
             "number_lexeme_refused")
    return _LexicalNumber(text)


def _constant(_text):
    raise EarningsGapError("nonfinite_number_refused")


def _screen_echo(body: object, credential: str | None) -> None:
    if credential is None:
        return
    pending = [body]
    while pending:
        value = pending.pop()
        if type(value) is str:
            _require(credential not in value, "credential_echo_refused")
        elif type(value) is dict:
            pending.extend(value.keys())
            pending.extend(value.values())
        elif type(value) is list:
            pending.extend(value)


def _private_json(raw: bytes, *, credential: str | None) -> object:
    """Separate framing/privacy-safe raw custody from metadata qualification."""
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY_BYTES,
             "source_json_refused")
    if credential is not None:
        _require(credential.encode("ascii") not in raw, "credential_echo_refused")
    try:
        body = json.loads(raw, object_pairs_hook=_unique, parse_int=_number, parse_float=_number,
                          parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise EarningsGapError("source_json_refused") from None
    _screen_echo(body, credential)
    return body


def _project(raw: bytes, window: tuple[str, str], *, credential: str | None) -> dict:
    _require(type(window) is tuple and window in WINDOWS, "window_date_refused")
    body = _private_json(raw, credential=credential)
    _require(type(body) is dict and {"status", "results"} <= set(body) and
        set(body) <= {"status", "results", "count", "request_id", "next_url"} and
        type(body["status"]) is str and body["status"] == "OK", "envelope_refused")
    results = body["results"]
    _require(type(results) is list and len(results) <= MAX_ROWS, "row_count_refused")
    if "count" in body:
        token = body["count"]
        _require(type(token) is _LexicalNumber and re.fullmatch(r"0|[1-9][0-9]{0,4}", token.lexeme) is not None,
                 "source_count_refused")
        # Only this explicit top-level nonfinancial count is interpreted.
        _require(int(token.lexeme) == len(results), "source_count_refused")
    if "request_id" in body:
        _require(type(body["request_id"]) is _LexicalNumber or (type(body["request_id"]) is str and
                 re.fullmatch(r"[A-Za-z0-9._-]{1,128}", body["request_id"]) is not None), "request_id_refused")
    pagination = "next_url" in body
    if pagination:
        value = body["next_url"]
        _require(type(value) is str and len(value) <= 8192, "pagination_url_refused")
        parts = urlsplit(value)
        query = parse_qsl(parts.query, keep_blank_values=True)
        _require(parts.scheme == "https" and parts.netloc == "api.massive.com" and
            parts.path == "/benzinga/v1/earnings" and not parts.fragment and
            len(query) == 1 and query[0][0] == "cursor" and 0 < len(query[0][1]) <= 4096,
            "pagination_url_refused")
    rows, accepted = [], 0
    for ordinal, row in enumerate(results):
        _require(type(row) is dict and row and set(row) <= _ROW_FIELDS, "row_schema_refused")
        row = {name: _NUMBER if type(value) is _LexicalNumber else value for name, value in row.items()}
        for name, value in row.items():
            if name in _FINANCIAL | {"fiscal_year", "importance"}:
                _require(value is _NUMBER or value is None, "source_field_refused")
            else:
                _require(value is None or (type(value) is str and len(value) <= 16384 and
                    not any(ord(char) < 32 for char in value)), "source_field_refused")
        day, schedule_time, status, updated = (row.get(name) for name in
                                                ("date", "time", "date_status", "last_updated"))
        if day is not None:
            _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) is not None, "window_date_refused")
            try:
                parsed = date.fromisoformat(day)
            except ValueError:
                raise EarningsGapError("window_date_refused") from None
            _require(window[0] <= parsed.isoformat() <= window[1], "window_date_refused")
        if schedule_time is not None:
            _require(re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]", schedule_time) is not None,
                     "schedule_time_refused")
        if status is not None:
            _require(status in {"projected", "confirmed"}, "date_status_refused")
        if updated is not None:
            try:
                updated = previous._utc(updated)
            except previous.EarningsAccessAuditError:
                raise EarningsGapError("updated_timestamp_refused") from None
        metadata_usable = day is not None and all(type(row.get(name)) is str and
            0 < len(row[name].strip()) <= 128 for name in ("ticker", "benzinga_id"))
        accepted += int(metadata_usable)
        rows.append({"source_ordinal": ordinal, "source_columns": sorted(row),
            "benzinga_id": row.get("benzinga_id"), "ticker": row.get("ticker"),
            "company_name": row.get("company_name"), "date": day, "time": schedule_time,
            "date_status": status, "last_updated_utc": updated,
            "financial_fields_present": sorted(_FINANCIAL & set(row)),
            "financial_fields_null": sorted(name for name in _FINANCIAL & set(row) if row[name] is None),
            "actual_value_fields_nonnull": sorted(name for name in ("actual_eps", "actual_revenue")
                if name in row and row[name] is not None),
            "metadata_disposition": "candidate-date-id-ticker" if metadata_usable else "quarantined-missing-date-id-ticker",
            "actual_release_proven": False, "identity_pit_rights_ready": False})
    result = {"schema": "insider-benzinga-schedule-metadata-only-v1", "window": list(window),
        "source_rows": len(rows), "metadata_candidate_rows": accepted,
        "quarantined_rows": len(rows) - accepted, "rows": rows,
        "pagination_present_not_followed": pagination, "row_limit_reached": len(rows) == MAX_ROWS,
        "source_page_underfill_refused": pagination or len(rows) == MAX_ROWS,
        "empty_page_is_complete_archive": False,
        "source_time_timezone_interpretation": "UNMEASURED-documents-say-EST",
        "financial_numbers_evaluated": False, "January2006_coverage_supplied": False,
        **{flag: False for flag in FALSE_FLAGS}}
    _require(len(_canonical(result)) <= MAX_METADATA_BYTES, "metadata_byte_bound_exceeded")
    return result


def replay_supplied_metadata(raw: bytes, expected_sha256: str, window: tuple[str, str]) -> dict:
    """Pure byte-bound replay, not authenticated source or complete coverage."""
    _require(type(expected_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None
        and _sha(raw) == expected_sha256, "external_body_pin_refused")
    return _project(raw, window, credential=None)


def _same_or_overlapping(path: Path, protected: Path) -> bool:
    try:
        if path == protected or path.resolve() == protected.resolve():
            return True
        if path.exists() and protected.exists() and path.samefile(protected):
            return True
        for ancestor in path.parents:
            if ancestor.exists() and protected.exists() and ancestor.samefile(protected):
                return True
        for ancestor in protected.parents:
            if path.exists() and ancestor.exists() and path.samefile(ancestor):
                return True
        return False
    except OSError:
        raise EarningsGapError("fixture_root_refused") from None


def _fixture_root(root: Path) -> None:
    _require(isinstance(root, Path) and root.is_absolute() and root.resolve() == root,
             "fixture_root_refused")
    _require(not _same_or_overlapping(root, LANE_ROOT), "fixture_root_refused")


def _identity(expected_head: str) -> dict:
    _require(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head) is not None,
             "expected_head_refused")
    _require(Path(__file__) == LANE_ROOT / SELF_PATH and Path.cwd() == LANE_ROOT and
        LANE_ROOT.resolve() == LANE_ROOT, "inactive_or_other_worktree_refused")
    try:
        _require(_git(LANE_ROOT, "rev-parse", "--show-toplevel").decode().strip() == str(LANE_ROOT) and
            _git(LANE_ROOT, "branch", "--show-current").decode().strip() == LANE_BRANCH and
            _git(LANE_ROOT, "rev-parse", "HEAD").decode().strip() == expected_head and
            _git(LANE_ROOT, "status", "--porcelain=v1", "--untracked-files=all") == b"",
            "clean_committed_lane_required")
        inventory = {}
        for name in _current_source_paths(LANE_ROOT):
            path = LANE_ROOT / name
            parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                raw = _read_leaf(parent, path.name, limit=MAX_BODY_BYTES, private=False)
            finally:
                os.close(parent)
            _require(raw == _git(LANE_ROOT, "show", expected_head + ":" + name), "source_image_changed")
            inventory[name] = _sha(raw)
        _require(_git(LANE_ROOT, "rev-parse", "HEAD").decode().strip() == expected_head and
            _git(LANE_ROOT, "branch", "--show-current").decode().strip() == LANE_BRANCH and
            _git(LANE_ROOT, "status", "--porcelain=v1", "--untracked-files=all") == b"", "source_image_changed")
        return {"root": str(LANE_ROOT), "branch": LANE_BRANCH, "head": expected_head,
            "clean": True, "source_sha256": inventory, "source_inventory_sha256": _sha(_canonical(inventory))}
    except EarningsGapError:
        raise
    except Exception:
        raise EarningsGapError("source_identity_unavailable") from None


def _keychain_credential() -> str:
    """Exact owner-configured item; stdout stays private in process memory."""
    try:
        result = subprocess.run(("/usr/bin/security", "find-generic-password", "-s", "trading-agent-massive",
            "-a", "massive", "-w"), capture_output=True, check=False, timeout=15,
            env={"PATH": "/usr/bin:/bin"})
        _require(result.returncode == 0 and 0 < len(result.stdout) <= 4097, "credential_unavailable")
        value = result.stdout.decode("ascii").removesuffix("\n")
        _require(re.fullmatch(r"[!-~]{1,4096}", value) is not None and value.casefold() != "test-api-key",
                 "credential_unavailable")
        return value
    except EarningsGapError:
        raise
    except Exception:
        raise EarningsGapError("credential_unavailable") from None


def _directory(parent: int, name: str, *, create: bool, private: bool = True) -> int:
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        info = os.fstat(fd)
        _require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and
            stat.S_IMODE(info.st_mode) & 0o022 == 0 and
            (not private or stat.S_IMODE(info.st_mode) == 0o700),
                 "private_directory_refused")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _parent(root: Path, *, create: bool) -> int:
    _require(root.is_absolute() and root.resolve() == root, "journal_root_refused")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for i, name in enumerate(ARTIFACT_PARTS):
            child = _directory(fd, name, create=create, private=i == len(ARTIFACT_PARTS) - 1)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _write(parent: int, name: str, raw: bytes, *, limit: int) -> str:
    _require(type(raw) is bytes and 0 < len(raw) <= limit, "publication_size_refused")
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.fsync(parent)
    return _sha(raw)


def _same_directory(parent: int, name: str, held: int) -> None:
    named, opened = os.stat(name, dir_fd=parent, follow_symlinks=False), os.fstat(held)
    _require(stat.S_ISDIR(named.st_mode) and stat.S_IMODE(named.st_mode) == 0o700 and
        named.st_uid == os.geteuid() and (named.st_dev, named.st_ino) == (opened.st_dev, opened.st_ino),
        "named_directory_detached")


def _private_read(parent: int, name: str, *, limit: int) -> bytes:
    before = os.stat(name, dir_fd=parent, follow_symlinks=False)
    _require(before.st_uid == os.geteuid(), "private_leaf_owner_refused")
    raw = _read_leaf(parent, name, limit=limit)
    _require(_version(before) == _version(os.stat(name, dir_fd=parent, follow_symlinks=False)),
             "journal_leaf_changed")
    return raw


def _disk(directory: int, remaining: int) -> dict:
    info = os.fstatvfs(directory)
    _require(type(remaining) is int and 0 <= remaining <= len(WINDOWS) and
        type(info.f_bavail) is int and info.f_bavail >= 0 and
        type(info.f_frsize) is int and info.f_frsize > 0, "disk_observation_refused")
    available = info.f_bavail * info.f_frsize
    required = MIN_FREE_BYTES + remaining * (MAX_BODY_BYTES + MAX_METADATA_BYTES + 2 * MAX_CONTROL_BYTES)
    required += 2 * MAX_CONTROL_BYTES
    _require(available >= required, "disk_reserve_refused")
    return {"available_bytes": available, "required_bytes": required, "remaining_windows": remaining}


class _PreviousAccess:
    """Hold and reattach the exact old access record without repeating it."""
    def __init__(self, root: Path):
        self.root = root
        self.fd = previous._parent(root, create=False)
        try:
            self.folder = _directory(self.fd, PREVIOUS_ID, create=False)
        except BaseException:
            os.close(self.fd)
            raise
        try:
            self.check()
        except BaseException:
            os.close(self.folder)
            os.close(self.fd)
            raise

    def check(self) -> None:
        reopened = previous._parent(self.root, create=False)
        try:
            _require((os.fstat(reopened).st_dev, os.fstat(reopened).st_ino) ==
                (os.fstat(self.fd).st_dev, os.fstat(self.fd).st_ino), "previous_root_detached")
            _same_directory(reopened, PREVIOUS_ID, self.folder)
            _require(set(os.listdir(self.folder)) == set(PREVIOUS_HASHES), "previous_leaf_inventory_refused")
            for name, digest in PREVIOUS_HASHES.items():
                _require(_sha(_private_read(self.folder, name, limit=MAX_CONTROL_BYTES)) == digest,
                         "previous_access_pin_refused")
            _same_directory(reopened, PREVIOUS_ID, self.folder)
        finally:
            os.close(reopened)

    def close(self) -> None:
        os.close(self.folder)
        os.close(self.fd)


def _journal(root: Path, parent: int, claims: int, runs: int, folder: int,
             run_id: str, lock: int, published: dict, claimed: dict, *,
             known_runs: frozenset[str], lock_version: tuple, old_runs: dict) -> None:
    def attached():
        reopened = _parent(root, create=False)
        try:
            _require((os.fstat(reopened).st_dev, os.fstat(reopened).st_ino) ==
                (os.fstat(parent).st_dev, os.fstat(parent).st_ino) and
                set(os.listdir(reopened)) == {"claims", "runs", "capture.lock"}, "journal_root_detached")
            _same_directory(reopened, "claims", claims)
            _same_directory(reopened, "runs", runs)
            _require(frozenset(os.listdir(runs)) == known_runs, "run_inventory_changed")
            _same_directory(runs, run_id, folder)
            _require(set(os.listdir(folder)) == set(published) and set(os.listdir(claims)) == set(claimed),
                     "journal_inventory_changed")
            named, held = os.stat("capture.lock", dir_fd=reopened, follow_symlinks=False), os.fstat(lock)
            _require(stat.S_ISREG(named.st_mode) and stat.S_IMODE(named.st_mode) == 0o600 and
                named.st_nlink == 1 and named.st_size == 0 and named.st_uid == os.geteuid() and
                _version(named) == _version(held) == lock_version, "journal_lock_detached")
        finally:
            os.close(reopened)
    attached()
    for name, digest in published.items():
        cap = MAX_BODY_BYTES if name.endswith("-raw.json") else (
            MAX_METADATA_BYTES if name.endswith("-metadata.json") else MAX_CONTROL_BYTES)
        _require(_sha(_private_read(folder, name, limit=cap)) == digest, "journal_hash_changed")
    for name, digest in claimed.items():
        _require(_sha(_private_read(claims, name, limit=MAX_CONTROL_BYTES)) == digest, "claim_hash_changed")
    for name, old in old_runs.items():
        _same_directory(runs, name, old["fd"])
        _require(_version(os.fstat(old["fd"])) == old["version"] and set(os.listdir(old["fd"])) == set(old["leaves"]),
                 "older_run_custody_changed")
        for leaf, digest in old["leaves"].items():
            _require(_sha(_private_read(old["fd"], leaf, limit=MAX_METADATA_BYTES)) == digest,
                     "older_run_custody_changed")
        _same_directory(runs, name, old["fd"])
        _require(_version(os.fstat(old["fd"])) == old["version"], "older_run_custody_changed")
    attached()


def _old_claims(claims: int) -> dict:
    result = {}
    for name in os.listdir(claims):
        _require(re.fullmatch(r"[0-9a-f]{64}\.json", name) is not None, "claim_registry_refused")
        raw = _private_read(claims, name, limit=MAX_CONTROL_BYTES)
        value = _json(raw)
        _require(set(value) == {"schema", "run_id", "window", "url", "claimed_at_utc", "maximum_attempts"} and
            value["schema"] == SCHEMA and type(value["maximum_attempts"]) is int and
            value["maximum_attempts"] == 1 and type(value["window"]) is list and
            tuple(value["window"]) in WINDOWS and value["url"] == _url(tuple(value["window"])) and
            type(value["run_id"]) is str and re.fullmatch(r"ib-benzinga-gap-[a-z0-9-]{1,80}", value["run_id"]) is not None and
            name == _sha(value["url"].encode()) + ".json", "claim_registry_refused")
        previous._utc(value["claimed_at_utc"])
        result[name] = _sha(raw)
    return result


def _response(response: object, window: tuple[str, str], credential: str) -> tuple[dict, bytes | None, dict | None]:
    base = {"window": list(window), "url": _url(window), "http_status": None,
        "body_complete": False, "body_bytes": None, "body_sha256": None, "retained_raw": False,
        "metadata_source_rows": None, "metadata_candidate_rows": None, "quarantined_rows": None,
        "pagination_followed": False, "financial_numbers_evaluated": False, "qualification_code": None,
        **{flag: False for flag in FALSE_FLAGS}}
    if (type(response) is not ProviderMetadataResponse or type(response.body) is not bytes or
        type(response.body_complete) is not bool or (response.status is not None and
        (type(response.status) is not int or not 100 <= response.status <= 599)) or
        not (response.disposition is None or type(response.disposition) is str and response.disposition in _TRANSPORT_CODES)):
        return {**base, "disposition": "transport_result_refused"}, None, None
    base.update(http_status=response.status, body_complete=response.body_complete)
    if len(response.body) > MAX_BODY_BYTES:
        return {**base, "disposition": "oversized-response"}, None, None
    if response.disposition is not None or response.status is None or not response.body_complete:
        return {**base, "disposition": response.disposition or "partial-read"}, None, None
    if response.status != 200:
        code = "product_access_refused" if response.status in {401, 403} else (
            "rate_limited_no_retry" if response.status == 429 else "http_refused_no_retry")
        return {**base, "disposition": code}, None, None
    try:
        _private_json(response.body, credential=credential)
    except EarningsGapError as exc:
        code = exc.args[0] if len(exc.args) == 1 and exc.args[0] in _SCHEMA_CODES else "source_schema_refused"
        return {**base, "disposition": code}, None, None
    except Exception:
        return {**base, "disposition": "source_schema_refused"}, None, None
    base.update(body_bytes=len(response.body), body_sha256=_sha(response.body), retained_raw=True,
        metadata_source_rows=None, metadata_candidate_rows=None, quarantined_rows=None)
    try:
        metadata = _project(response.body, window, credential=credential)
    except EarningsGapError as exc:
        code = exc.args[0] if len(exc.args) == 1 and type(exc.args[0]) is str and exc.args[0] in _SCHEMA_CODES else "source_schema_refused"
        return {**base, "disposition": "source_metadata_quarantined", "qualification_code": code}, response.body, None
    except Exception:
        return {**base, "disposition": "source_metadata_quarantined", "qualification_code": "source_schema_refused"}, response.body, None
    base.update(metadata_source_rows=metadata["source_rows"], metadata_candidate_rows=metadata["metadata_candidate_rows"],
        quarantined_rows=metadata["quarantined_rows"])
    disposition = "partial_page_refused_no_pagination" if metadata["source_page_underfill_refused"] else "candidate_metadata_observed"
    return {**base, "disposition": disposition}, response.body, metadata


def _run(run_id: str, expected_head: str, *, root: Path, identity: Callable,
         credential_loader: Callable, transport: Callable, previous_guard: Callable,
         fixture_only: bool, clock: Callable = _now, monotonic: Callable = time.monotonic,
         sleep: Callable = time.sleep) -> dict:
    _require(type(run_id) is str and re.fullmatch(r"ib-benzinga-gap-[a-z0-9-]{1,80}", run_id) is not None and
        type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head) is not None,
        "run_identity_refused")
    if fixture_only:
        _fixture_root(root)
    else:
        _require(root == LANE_ROOT and identity is _identity and credential_loader is _keychain_credential and
            transport is _default_transport, "actual_fixed_route_refused")
    baseline = identity(expected_head)
    previous_guard()
    parent = claims = runs = folder = lock = None
    published, claimed, results, old_runs = {}, {}, [], {}
    try:
        parent = _parent(root, create=True)
        claims = _directory(parent, "claims", create=True)
        runs = _directory(parent, "runs", create=True)
        lock = os.open("capture.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
        lock_info = os.fstat(lock)
        _require(stat.S_ISREG(lock_info.st_mode) and stat.S_IMODE(lock_info.st_mode) == 0o600 and
            lock_info.st_nlink == 1 and lock_info.st_size == 0 and lock_info.st_uid == os.geteuid(),
            "journal_lock_detached")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        claimed = _old_claims(claims)
        _require(not any(_sha(url.encode()) + ".json" in claimed for url in URLS),
                 "completed_or_ambiguous_window_already_claimed")
        for name in os.listdir(runs):
            _require(re.fullmatch(r"ib-benzinga-gap-[a-z0-9-]{1,80}", name) is not None, "older_run_inventory_refused")
            old_fd = _directory(runs, name, create=False)
            old_runs[name] = {"fd": old_fd, "version": _version(os.fstat(old_fd)), "leaves": {}}
            for leaf in os.listdir(old_fd):
                _require(re.fullmatch(r"(?:manifest|complete|[0-2][0-9]-(?:started|raw|metadata|complete))\.json", leaf) is not None,
                         "older_run_inventory_refused")
                old_runs[name]["leaves"][leaf] = _sha(_private_read(old_fd, leaf, limit=MAX_METADATA_BYTES))
            _require(_version(os.fstat(old_fd)) == old_runs[name]["version"], "older_run_custody_changed")
        try:
            os.mkdir(run_id, 0o700, dir_fd=runs)
        except FileExistsError:
            raise EarningsGapError("existing_run_refused") from None
        os.fsync(runs)
        folder = _directory(runs, run_id, create=False)
        known_runs, lock_version = frozenset(os.listdir(runs)), _version(os.fstat(lock))
        resource = _disk(folder, len(WINDOWS))
        manifest = {"schema": SCHEMA, "run_id": run_id, "registered_at_utc": previous._utc(clock()),
            "owner_direction": OWNER_DIRECTION, "identity": baseline, "windows": [list(w) for w in WINDOWS],
            "urls": list(URLS), "maximum_transport_attempts": 3, "attempts_per_claim": 1,
            "prior_access_leaf_sha256": dict(PREVIOUS_HASHES), "fixture_only": fixture_only,
            "resource": resource, "pagination_retry_resume_redirect_permitted": False,
            "source_date_semantics": "scheduled-or-reported-not-authenticated-release",
            "January2006_coverage_supplied": False, **{flag: False for flag in FALSE_FLAGS}}
        published["manifest.json"] = _write(folder, "manifest.json", _canonical(manifest), limit=MAX_CONTROL_BYTES)
        def guard():
            _capture_at_phase("guard_current_identity", lambda: _require(identity(expected_head) == baseline, "current_source_changed"))
            _capture_at_phase("guard_previous_access", previous_guard)
            _capture_at_phase("guard_current_journal", _journal, root, parent, claims, runs, folder, run_id, lock, published, claimed,
                known_runs=known_runs, lock_version=lock_version, old_runs=old_runs)
        guard()
        for index, window in enumerate(WINDOWS):
            guard()
            resource = _disk(folder, len(WINDOWS) - index)
            url = _url(window)
            claim_name = _sha(url.encode()) + ".json"
            claim = {"schema": SCHEMA, "run_id": run_id, "window": list(window), "url": url,
                "claimed_at_utc": previous._utc(clock()), "maximum_attempts": 1}
            claimed[claim_name] = _write(claims, claim_name, _canonical(claim), limit=MAX_CONTROL_BYTES)
            prefix = f"{index:02d}"
            started = {"schema": SCHEMA, "run_id": run_id, "window": list(window), "url": url,
                "started_at_utc": previous._utc(clock()), "claim_sha256": claimed[claim_name],
                "manifest_sha256": published["manifest.json"], "resource": resource, "maximum_attempts": 1}
            published[prefix + "-started.json"] = _write(folder, prefix + "-started.json", _canonical(started), limit=MAX_CONTROL_BYTES)
            guard()
            try:
                credential = credential_loader()
                _require(type(credential) is str and re.fullmatch(r"[!-~]{1,4096}", credential) is not None and
                    credential.casefold() != "test-api-key", "credential_unavailable")
            except Exception:
                receipt = {"window": list(window), "url": url, "http_status": None, "body_complete": False,
                    "body_bytes": None, "body_sha256": None, "retained_raw": False,
                    "metadata_source_rows": None, "metadata_candidate_rows": None, "quarantined_rows": None,
                    "disposition": "credential_unavailable", "pagination_followed": False,
                    "financial_numbers_evaluated": False, "qualification_code": None, **{flag: False for flag in FALSE_FLAGS}}
                raw = metadata = None
            else:
                guard()
                item = EarningsGapRequest(url, (("Accept", "application/json"), ("Accept-Encoding", "identity"),
                                               ("Authorization", "Bearer " + credential)))
                _validate_request(item)
                try:
                    response = transport(item)
                except Exception:
                    response = ProviderMetadataResponse(None, b"", False, "transport-error")
                receipt, raw, metadata = _response(response, window, credential)
                credential = None
            # No speculative retry; post-response guards precede any retention.
            guard()
            if raw is not None:
                published[prefix + "-raw.json"] = _write(folder, prefix + "-raw.json", raw, limit=MAX_BODY_BYTES)
                guard()
                if metadata is not None:
                    published[prefix + "-metadata.json"] = _write(folder, prefix + "-metadata.json", _canonical(metadata), limit=MAX_METADATA_BYTES)
                    guard()
            sealed = {"schema": SCHEMA, "run_id": run_id, "ordinal": index,
                "completed_at_utc": previous._utc(clock()), "started_sha256": published[prefix + "-started.json"],
                "claim_sha256": claimed[claim_name], "receipt": receipt,
                "raw_sha256": published.get(prefix + "-raw.json"),
                "metadata_sha256": published.get(prefix + "-metadata.json")}
            published[prefix + "-complete.json"] = _write(folder, prefix + "-complete.json", _canonical(sealed), limit=MAX_CONTROL_BYTES)
            results.append(sealed)
            guard()
            if receipt["disposition"] != "candidate_metadata_observed":
                break
            if index + 1 < len(WINDOWS):
                completed = monotonic()
                _require(type(completed) in {int, float} and completed >= 0, "monotonic_clock_refused")
                # Spacing starts after all response processing and custody checks.
                sleep(COOLDOWN_SECONDS)
                after = monotonic()
                _require(type(after) in {int, float} and after - completed >= COOLDOWN_SECONDS,
                         "post_completion_cooldown_refused")
        guard()
        count = len(results)
        complete = {"schema": SCHEMA, "run_id": run_id, "completed_at_utc": previous._utc(clock()),
            "identity": baseline, "manifest_sha256": published["manifest.json"], "fixture_only": fixture_only,
            "planned_windows": len(WINDOWS), "claimed_started_windows": count, "terminal_windows": count,
            "candidate_metadata_windows": sum(r["receipt"]["disposition"] == "candidate_metadata_observed" for r in results),
            "refused_windows": sum(r["receipt"]["disposition"] != "candidate_metadata_observed" for r in results),
            "originally_unattempted_windows": [list(w) for w in WINDOWS[count:]], "results": results,
            "current_journal_sha256": dict(published), "claim_sha256": dict(claimed),
            "looks_jobs_backtests": [0, 0, 0], "January2006_coverage_supplied": False,
            **{flag: False for flag in FALSE_FLAGS}}
        published["complete.json"] = _write(folder, "complete.json", _canonical(complete), limit=MAX_CONTROL_BYTES)
        guard()
        unknown = sum(r["receipt"]["disposition"] == "source_metadata_quarantined" for r in results)
        known_rows = sum(r["receipt"]["metadata_source_rows"] or 0 for r in results)
        return {"run_id": run_id, "complete_sha256": published["complete.json"], "claimed_started_windows": count,
            "candidate_metadata_windows": complete["candidate_metadata_windows"],
            "refused_windows": complete["refused_windows"], "originally_unattempted_windows": complete["originally_unattempted_windows"],
            "source_rows": None if unknown else known_rows, "known_metadata_source_rows": known_rows,
            "unknown_metadata_windows": unknown,
            "retained_raw_bytes": sum(r["receipt"]["body_bytes"] or 0 for r in results),
            "fixture_only": fixture_only, "looks_jobs_backtests": [0, 0, 0], **{flag: False for flag in FALSE_FLAGS}}
    except EarningsGapError:
        raise
    except Exception as exc:
        # Keep the existing refusal type/semantics; carry only independently
        # sanitized diagnostic categories, never the original message/args.
        converted = EarningsGapError("capture_refused_claims_preserved")
        converted._earnings_capture_failure_diagnostic = _capture_diagnostic(exc)
        raise converted from None
    finally:
        for old in old_runs.values():
            os.close(old["fd"])
        for fd in (folder, runs, claims, lock, parent):
            if fd is not None:
                os.close(fd)


def run_fixture(run_id: str, expected_head: str, *, root: Path, identity: Callable,
                credential_loader: Callable, transport: Callable, previous_guard: Callable = lambda: None,
                clock: Callable = _now, monotonic: Callable = time.monotonic,
                sleep: Callable = time.sleep) -> dict:
    # Fence before any callback/source/output/credential operation.
    _fixture_root(root)
    _require(transport is not _default_transport and credential_loader is not _keychain_credential and
             identity is not _identity, "fixture_real_callback_refused")
    return _run(run_id, expected_head, root=root, identity=identity, credential_loader=credential_loader,
        transport=transport, previous_guard=previous_guard, fixture_only=True, clock=clock,
        monotonic=monotonic, sleep=sleep)


def run_capture(run_id: str, expected_head: str, *, expected_previous_complete_sha256: str) -> dict:
    _require(type(expected_previous_complete_sha256) is str and
        expected_previous_complete_sha256 == PREVIOUS_HASHES["complete.json"], "previous_external_pin_refused")
    _identity(expected_head)  # fixed-path inactive fence before previous root I/O
    old = _PreviousAccess(LANE_ROOT)
    try:
        return _run(run_id, expected_head, root=LANE_ROOT, identity=_identity,
            credential_loader=_keychain_credential, transport=_default_transport,
            previous_guard=old.check, fixture_only=False)
    finally:
        old.close()


_RECEIPT_KEYS = frozenset({"window", "url", "http_status", "body_complete", "body_bytes", "body_sha256",
    "retained_raw", "metadata_source_rows", "metadata_candidate_rows", "quarantined_rows", "pagination_followed",
    "financial_numbers_evaluated", "disposition", "qualification_code", *FALSE_FLAGS})
_REFUSALS = frozenset({"transport_result_refused", "credential_unavailable", "product_access_refused",
    "rate_limited_no_retry", "http_refused_no_retry", "source_schema_refused", *_TRANSPORT_CODES, *_SCHEMA_CODES})


def _verify_resource(value: object, remaining: int) -> None:
    required = MIN_FREE_BYTES + remaining * (MAX_BODY_BYTES + MAX_METADATA_BYTES + 2 * MAX_CONTROL_BYTES) + 2 * MAX_CONTROL_BYTES
    _require(type(value) is dict and set(value) == {"available_bytes", "required_bytes", "remaining_windows"} and
        all(type(value[key]) is int for key in value) and value["remaining_windows"] == remaining and
        value["required_bytes"] == required and value["available_bytes"] >= required, "terminal_resource_refused")


def _verify_identity_record(value: object, *, fixture_only: bool) -> None:
    _require(type(value) is dict and set(value) == {"root", "branch", "head", "clean", "source_sha256", "source_inventory_sha256"} and
        type(value["root"]) is str and (fixture_only or value["root"] == str(LANE_ROOT)) and
        value["branch"] == LANE_BRANCH and type(value["head"]) is str and
        re.fullmatch(r"[0-9a-f]{40}", value["head"]) is not None and value["clean"] is True and
        type(value["source_sha256"]) is dict and value["source_sha256"] and
        all(type(name) is str and type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
            for name, digest in value["source_sha256"].items()) and
        (fixture_only or set(SOURCE_FILES) <= set(value["source_sha256"])) and
        value["source_inventory_sha256"] == _sha(_canonical(value["source_sha256"])), "terminal_source_identity_refused")


def _verify_terminal(complete: dict, leaves: dict[str, bytes], claims: dict[str, bytes], *, fixture_only: bool) -> dict:
    """Independently replay all retained rows/requests, not just receipt literals."""
    _require(set(complete) == {"schema", "run_id", "completed_at_utc", "identity", "manifest_sha256", "fixture_only",
        "planned_windows", "claimed_started_windows", "terminal_windows", "candidate_metadata_windows", "refused_windows",
        "originally_unattempted_windows", "results", "current_journal_sha256", "claim_sha256", "looks_jobs_backtests",
        "January2006_coverage_supplied", *FALSE_FLAGS}, "terminal_schema_refused")
    run_id = complete["run_id"]
    _require(type(run_id) is str and re.fullmatch(r"ib-benzinga-gap-[a-z0-9-]{1,80}", run_id) is not None and
        complete["schema"] == SCHEMA and complete["fixture_only"] is fixture_only and
        type(complete["planned_windows"]) is int and complete["planned_windows"] == len(WINDOWS) and
        complete["looks_jobs_backtests"] == [0, 0, 0] and
        all(type(v) is int for v in complete["looks_jobs_backtests"]) and
        complete["January2006_coverage_supplied"] is False and
        all(complete[flag] is False for flag in FALSE_FLAGS), "terminal_authority_refused")
    previous._utc(complete["completed_at_utc"])
    _verify_identity_record(complete["identity"], fixture_only=fixture_only)
    results = complete["results"]
    _require(type(results) is list and 1 <= len(results) <= len(WINDOWS), "terminal_counts_refused")
    count = len(results)
    for name in ("claimed_started_windows", "terminal_windows"):
        _require(type(complete[name]) is int and complete[name] == count, "terminal_counts_refused")
    _require(complete["originally_unattempted_windows"] == [list(w) for w in WINDOWS[count:]],
             "terminal_unattempted_refused")
    expected_names = {"manifest.json", "complete.json"}
    expected_claim_names, accepted, refused, rows, retained_bytes, unknown = set(), 0, 0, 0, 0, 0
    manifest = _json(leaves["manifest.json"])
    _require(set(manifest) == {"schema", "run_id", "registered_at_utc", "owner_direction", "identity", "windows",
        "urls", "maximum_transport_attempts", "attempts_per_claim", "prior_access_leaf_sha256", "fixture_only", "resource",
        "pagination_retry_resume_redirect_permitted", "source_date_semantics", "January2006_coverage_supplied", *FALSE_FLAGS} and
        manifest["schema"] == SCHEMA and manifest["run_id"] == run_id and manifest["owner_direction"] == OWNER_DIRECTION and
        manifest["windows"] == [list(w) for w in WINDOWS] and manifest["urls"] == list(URLS) and
        type(manifest["maximum_transport_attempts"]) is int and manifest["maximum_transport_attempts"] == 3 and
        type(manifest["attempts_per_claim"]) is int and manifest["attempts_per_claim"] == 1 and
        manifest["prior_access_leaf_sha256"] == PREVIOUS_HASHES and manifest["fixture_only"] is fixture_only and
        manifest["pagination_retry_resume_redirect_permitted"] is False and
        manifest["source_date_semantics"] == "scheduled-or-reported-not-authenticated-release" and
        manifest["January2006_coverage_supplied"] is False and all(manifest[flag] is False for flag in FALSE_FLAGS) and
        manifest["identity"] == complete["identity"], "manifest_profile_refused")
    _require(complete["manifest_sha256"] == _sha(leaves["manifest.json"]), "manifest_pin_refused")
    previous._utc(manifest["registered_at_utc"])
    _verify_resource(manifest["resource"], len(WINDOWS))
    for index, terminal in enumerate(results):
        prefix, window, url = f"{index:02d}", WINDOWS[index], URLS[index]
        claim_name = _sha(url.encode()) + ".json"
        expected_claim_names.add(claim_name)
        expected_names.update({prefix + "-started.json", prefix + "-complete.json"})
        _require(type(terminal) is dict and set(terminal) == {"schema", "run_id", "ordinal", "completed_at_utc",
            "started_sha256", "claim_sha256", "receipt", "raw_sha256", "metadata_sha256"} and
            terminal["schema"] == SCHEMA and terminal["run_id"] == run_id and
            type(terminal["ordinal"]) is int and terminal["ordinal"] == index and
            _json(leaves[prefix + "-complete.json"]) == terminal, "terminal_window_refused")
        previous._utc(terminal["completed_at_utc"])
        start = _json(leaves[prefix + "-started.json"])
        claim = _json(claims[claim_name])
        _require(set(start) == {"schema", "run_id", "window", "url", "started_at_utc", "claim_sha256",
            "manifest_sha256", "resource", "maximum_attempts"} and set(claim) == {"schema", "run_id", "window", "url",
            "claimed_at_utc", "maximum_attempts"} and start["schema"] == claim["schema"] == SCHEMA and
            start["run_id"] == claim["run_id"] == run_id and start["window"] == claim["window"] == list(window) and
            start["url"] == claim["url"] == url and type(start["maximum_attempts"]) is int and
            type(claim["maximum_attempts"]) is int and start["maximum_attempts"] == claim["maximum_attempts"] == 1 and
            start["manifest_sha256"] == complete["manifest_sha256"] and
            start["claim_sha256"] == terminal["claim_sha256"] == _sha(claims[claim_name]) and
            terminal["started_sha256"] == _sha(leaves[prefix + "-started.json"]), "started_claim_binding_refused")
        previous._utc(start["started_at_utc"])
        previous._utc(claim["claimed_at_utc"])
        _verify_resource(start["resource"], len(WINDOWS) - index)
        receipt = terminal["receipt"]
        _require(type(receipt) is dict and set(receipt) == _RECEIPT_KEYS and receipt["window"] == list(window) and
            receipt["url"] == url and (receipt["http_status"] is None or type(receipt["http_status"]) is int and
            100 <= receipt["http_status"] <= 599) and type(receipt["body_complete"]) is bool and
            type(receipt["retained_raw"]) is bool and receipt["pagination_followed"] is False and
            receipt["financial_numbers_evaluated"] is False and all(receipt[flag] is False for flag in FALSE_FLAGS),
            "terminal_receipt_refused")
        disposition = receipt["disposition"]
        _require(type(disposition) is str, "terminal_receipt_refused")
        if receipt["retained_raw"]:
            expected_names.add(prefix + "-raw.json")
            raw = leaves[prefix + "-raw.json"]
            _private_json(raw, credential=None)
            _require(receipt["http_status"] == 200 and
                receipt["body_complete"] is True and type(receipt["body_bytes"]) is int and
                receipt["body_bytes"] == len(raw) and receipt["body_sha256"] == terminal["raw_sha256"] == _sha(raw) and
                receipt["retained_raw"] is True, "retained_body_replay_refused")
            if disposition == "source_metadata_quarantined":
                _require(type(receipt["qualification_code"]) is str and receipt["qualification_code"] in
                    _SCHEMA_CODES | {"source_schema_refused"} and terminal["metadata_sha256"] is None and
                    all(receipt[name] is None for name in ("metadata_source_rows", "metadata_candidate_rows", "quarantined_rows")),
                    "quarantined_raw_refusal_refused")
                try:
                    _project(raw, window, credential=None)
                except EarningsGapError as exc:
                    code = exc.args[0] if len(exc.args) == 1 and type(exc.args[0]) is str and exc.args[0] in _SCHEMA_CODES else "source_schema_refused"
                    _require(code == receipt["qualification_code"], "quarantined_raw_refusal_refused")
                else:
                    raise EarningsGapError("quarantined_raw_refusal_refused")
                unknown += 1
            else:
                expected_names.add(prefix + "-metadata.json")
                metadata_raw = leaves[prefix + "-metadata.json"]
                metadata = _project(raw, window, credential=None)
                _require(_canonical(metadata) == metadata_raw and terminal["metadata_sha256"] == _sha(metadata_raw) and
                    receipt["qualification_code"] is None, "retained_body_replay_refused")
                for name, value in (("metadata_source_rows", metadata["source_rows"]),
                    ("metadata_candidate_rows", metadata["metadata_candidate_rows"]), ("quarantined_rows", metadata["quarantined_rows"])):
                    _require(type(receipt[name]) is int and receipt[name] == value, "terminal_row_accounting_refused")
                expected = "partial_page_refused_no_pagination" if metadata["source_page_underfill_refused"] else "candidate_metadata_observed"
                _require(disposition == expected, "terminal_underfill_refused")
                rows += metadata["source_rows"]
            retained_bytes += len(raw)
        else:
            _require(disposition in _REFUSALS and terminal["raw_sha256"] is None and terminal["metadata_sha256"] is None and
                receipt["body_bytes"] is None and receipt["body_sha256"] is None and receipt["metadata_source_rows"] is None and
                receipt["metadata_candidate_rows"] is None and receipt["quarantined_rows"] is None and
                receipt["qualification_code"] is None, "terminal_refusal_refused")
        if disposition == "candidate_metadata_observed":
            accepted += 1
        else:
            refused += 1
            _require(index == count - 1, "requests_after_refusal_refused")
    _require(set(leaves) == expected_names and set(claims) == expected_claim_names, "terminal_leaf_inventory_refused")
    _require(type(complete["candidate_metadata_windows"]) is int and complete["candidate_metadata_windows"] == accepted and
        type(complete["refused_windows"]) is int and complete["refused_windows"] == refused and
        (count == len(WINDOWS) or refused == 1), "terminal_counts_refused")
    _require(complete["current_journal_sha256"] == {name: _sha(raw) for name, raw in leaves.items() if name != "complete.json"} and
        complete["claim_sha256"] == {name: _sha(raw) for name, raw in claims.items()}, "terminal_inventory_pins_refused")
    return {"run_id": run_id, "claimed_started_windows": count, "candidate_metadata_windows": accepted,
        "refused_windows": refused, "source_rows": None if unknown else rows,
        "known_metadata_source_rows": rows, "unknown_metadata_windows": unknown, "retained_raw_bytes": retained_bytes,
        "fixture_only": fixture_only, "January2006_coverage_supplied": False, **{flag: False for flag in FALSE_FLAGS}}


def verify_supplied_terminal(complete_raw: bytes, expected_complete_sha256: str,
                             leaves: dict[str, bytes], claims: dict[str, bytes], *, fixture_only: bool) -> dict:
    """Pure supplied byte replay; authenticity/current custody are not asserted."""
    _require(type(complete_raw) is bytes and 0 < len(complete_raw) <= MAX_CONTROL_BYTES and
        type(expected_complete_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", expected_complete_sha256) is not None and
        _sha(complete_raw) == expected_complete_sha256 and type(fixture_only) is bool and
        type(leaves) is dict and type(claims) is dict and leaves.get("complete.json") == complete_raw,
        "terminal_external_pin_refused")
    try:
        return _verify_terminal(_json(complete_raw), leaves, claims, fixture_only=fixture_only)
    except EarningsGapError:
        raise
    except Exception:
        raise EarningsGapError("terminal_replay_refused") from None


VERIFICATION_POLICY = '(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)'
MAX_VERIFIER_OUTPUT_BYTES = 256 * 1024
MAX_KNOWN_RUNS = 64
MAX_SOURCE_FILES = 512
_VERIFICATION_PHASES = frozenset({"fixed_preflight", "current_identity", "input_snapshot", "producer_git_inventory",
    "isolated_worker", "after_worker_identity", "after_worker_custody", "worker_protocol", "worker_isolation",
    "worker_current_sources", "worker_input_snapshot", "worker_terminal_replay", "worker_final_sources"})
_VERIFICATION_FAILURES = frozenset({"inactive_or_other_worktree_refused", "clean_committed_lane_required",
    "verification_external_pin_refused", "verification_root_inventory_refused", "verification_run_inventory_refused",
    "verification_claim_inventory_refused", "verification_directory_kind_refused", "verification_leaf_name_refused",
    "verification_lock_refused", "verification_metadata_cap_refused", "producer_source_inventory_refused",
    "producer_static_closure_refused", "source_identity_unavailable", "source_image_changed", "current_source_changed",
    "verification_worker_refused", "verification_worker_reply_refused", "worker_protocol_refused",
    "worker_current_inventory_refused", "worker_original_inventory_refused", "worker_isolation_refused",
    "worker_observation_differs", "terminal_replay_refused", "terminal_receipt_refused", "terminal_counts_refused",
    "terminal_resource_refused", "terminal_source_identity_refused", "verification_input_custody_refused"})


def _failure_fields(exc: BaseException, phase: str) -> dict:
    # Never str/repr an exception or disclose arbitrary args, filename or text.
    categories = {EarningsGapError: "earnings_gap_error", OSError: "os_error", ValueError: "value_error",
        TypeError: "type_error", KeyError: "key_error", json.JSONDecodeError: "json_error",
        subprocess.TimeoutExpired: "subprocess_timeout", subprocess.CalledProcessError: "subprocess_error"}
    code = exc.args[0] if len(exc.args) == 1 and type(exc.args[0]) is str else None
    return {"phase": phase if phase in _VERIFICATION_PHASES else "fixed_preflight",
        "exception_category": categories.get(type(exc), "os_error" if isinstance(exc, OSError) else "unclassified_error"),
        "fixed_code": code if code in _VERIFICATION_FAILURES else "unclassified_failure",
        "recognized_os_errno": exc.errno if isinstance(exc, OSError) and type(exc.errno) is int and
            exc.errno in {1, 2, 5, 9, 13, 17, 20, 24, 28, 30, 35} else None}


def _safe_failure_fields(exc: BaseException) -> dict:
    fallback = _failure_fields(exc, "fixed_preflight")
    supplied = getattr(exc, "failure_fields", None)
    categories = {"earnings_gap_error", "os_error", "value_error", "type_error", "key_error", "json_error",
        "subprocess_timeout", "subprocess_error", "unclassified_error"}
    if (type(supplied) is dict and set(supplied) == set(fallback) and
        type(supplied["phase"]) is str and supplied["phase"] in _VERIFICATION_PHASES and
        type(supplied["exception_category"]) is str and supplied["exception_category"] in categories and
        type(supplied["fixed_code"]) is str and supplied["fixed_code"] in _VERIFICATION_FAILURES | {"unclassified_failure"} and
        (supplied["recognized_os_errno"] is None or type(supplied["recognized_os_errno"]) is int and
         supplied["recognized_os_errno"] in {1, 2, 5, 9, 13, 17, 20, 24, 28, 30, 35})):
        return dict(supplied)
    return fallback


def _source_name(name: object) -> str:
    _require(type(name) is str and len(name) <= 512 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_/]*\.py", name) is not None and
        not Path(name).is_absolute() and ".." not in Path(name).parts, "producer_source_inventory_refused")
    return name


def _import_candidates(raw: bytes, name: str) -> set[str]:
    tree = ast.parse(raw, filename=name)
    modules, result = [], set()
    package = Path(name).parent.parts
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = ".".join(package[:len(package) + 1 - node.level]) if node.level else ""
            module = ".".join(part for part in (prefix, node.module) if part)
            modules.append(module)
            modules.extend(module + "." + item.name for item in node.names if item.name != "*")
    for module in modules:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", module):
            continue
        parts = module.split(".")
        result.update({str(Path(*parts).with_suffix(".py")), str(Path(*parts) / "__init__.py")})
        result.update(str(Path(*parts[:count]) / "__init__.py") for count in range(1, len(parts)))
    return result


def _source_current_bytes(root: Path, names) -> dict[str, str]:
    result = {}
    for name in names:
        _source_name(name)
        chain = custody._Chain(root, tuple(Path(name).parts[:-1]))
        try:
            raw = _read_leaf(chain.fd, Path(name).name, limit=4 * 1024**2, private=False)
            chain.recheck()
            result[name] = _sha(raw)
        finally:
            chain.close()
    return result


def _current_source_paths(root: Path) -> tuple[str, ...]:
    """Conservative static closure plus actually loaded internal modules.

    Inventory includes dependencies, not a claim every branch was executed.
    Private draft files are never eligible to become production source roots.
    """
    pending, found = list(SOURCE_FILES), set()
    for module in tuple(sys.modules.values()):
        name = getattr(module, "__file__", None)
        if type(name) is str:
            path = Path(name)
            if path.suffix == ".py" and path.is_relative_to(root) and path.relative_to(root).parts[0] == "research":
                pending.append(str(path.relative_to(root)))
    while pending:
        name = _source_name(pending.pop())
        if name in found:
            continue
        _require(len(found) < MAX_SOURCE_FILES, "producer_static_closure_refused")
        found.add(name)
        chain = custody._Chain(root, tuple(Path(name).parts[:-1]))
        try:
            raw = _read_leaf(chain.fd, Path(name).name, limit=4 * 1024**2, private=False)
            chain.recheck()
        finally:
            chain.close()
        for candidate in _import_candidates(raw, name):
            if (root / candidate).is_file():
                pending.append(candidate)
    return tuple(sorted(found))


def _producer_git_inventory(identity: dict) -> dict:
    """Check original commit bytes and its import closure, not current HEAD.

    This does not execute the complete historical environment. The current
    verifier executes while these original module bytes are independently bound.
    """
    _verify_identity_record(identity, fixture_only=False)
    head, expected = identity["head"], identity["source_sha256"]
    originals = {}
    for name in sorted(expected):
        _source_name(name)
        raw = _git(LANE_ROOT, "show", head + ":" + name)
        _require(type(raw) is bytes and 0 <= len(raw) <= 4 * 1024**2 and _sha(raw) == expected[name],
                 "producer_source_inventory_refused")
        originals[name] = raw
    _require(len(originals) <= MAX_SOURCE_FILES and set(SOURCE_FILES) <= set(originals), "producer_static_closure_refused")
    candidates = set()
    for name, raw in originals.items():
        candidates.update(_import_candidates(raw, name))
    # Use one verified Git tree listing, not a missing-object/error return
    # code that could accidentally treat an inaccessible module as absent.
    tree_raw = _git(LANE_ROOT, "ls-tree", "-r", "--name-only", head)
    _require(type(tree_raw) is bytes and len(tree_raw) <= 16 * 1024**2, "producer_static_closure_refused")
    tracked = set(tree_raw.decode("utf-8").splitlines())
    _require(candidates & tracked <= set(originals), "producer_static_closure_refused")
    return {"head": head, "source_sha256": expected,
        "source_inventory_sha256": _sha(_canonical(expected)), "original_committed_bytes_verified": True,
        "whole_historical_environment_executed": False}


def _tree_leaf_cap(name: str) -> int:
    if name.endswith("-raw.json"):
        return MAX_BODY_BYTES
    if name.endswith("-metadata.json"):
        return MAX_METADATA_BYTES
    return MAX_CONTROL_BYTES


class _VerificationTree:
    """Held full absolute ancestry, all known directories/leaves and lock."""
    def __init__(self, root: Path, run_id: str, expected_complete_sha256: str, *, fixture_only: bool):
        if fixture_only:
            _fixture_root(root)
        else:
            _require(root == LANE_ROOT, "inactive_or_other_worktree_refused")
        _require(type(run_id) is str and re.fullmatch(r"ib-benzinga-gap-[a-z0-9-]{1,80}", run_id) is not None and
            type(expected_complete_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", expected_complete_sha256) is not None,
            "verification_external_pin_refused")
        self.tree = custody_tree._Tree(custody_tree.RootSpec("benzinga-gap-global-custody", root.joinpath(*ARTIFACT_PARTS), "metadata-custody"))
        self.root, self.run_id, self.expected = root, run_id, expected_complete_sha256
        self.leaves, self.claims, self.observed = {}, {}, {}
        try:
            self._read_all()
            self.tree.recheck()
        except BaseException:
            self.close()
            raise

    def _read(self, parts: tuple, name: str, *, limit: int, expected=None) -> bytes:
        _require(name not in {"", ".", ".."} and "/" not in name, "verification_leaf_name_refused")
        raw = self.tree.read(parts, name, cap=limit, expected=expected)
        key = "/".join((*parts, name))
        entry = self.tree.leaves[key]
        self.observed[key] = {"sha256": _sha(raw), "bytes": len(raw), "version": list(entry[3]),
            "owner_uid": os.geteuid(), "private_mode": 0o600, "single_link": True}
        return raw

    def _read_all(self) -> None:
        _require(set(self.tree.names()) == {"claims", "runs", "capture.lock"}, "verification_root_inventory_refused")
        locked = self._read((), "capture.lock", limit=0)
        _require(locked == b"" and len(self.tree.locks) == 1, "verification_lock_refused")
        known_runs = self.tree.names(("runs",))
        _require(self.run_id in known_runs and len(known_runs) <= MAX_KNOWN_RUNS and
            all(re.fullmatch(r"ib-benzinga-gap-[a-z0-9-]{1,80}", name) is not None for name in known_runs),
            "verification_run_inventory_refused")
        for name in self.tree.names(("claims",)):
            _require(re.fullmatch(r"[0-9a-f]{64}\.json", name) is not None, "verification_claim_inventory_refused")
            self.claims[name] = self._read(("claims",), name, limit=MAX_CONTROL_BYTES)
        for name in known_runs:
            for leaf in self.tree.names(("runs", name)):
                _require(re.fullmatch(r"(?:manifest|complete|0[0-2]-(?:started|raw|metadata|complete))\.json", leaf) is not None,
                         "verification_leaf_name_refused")
                raw = self._read(("runs", name), leaf, limit=_tree_leaf_cap(leaf),
                    expected=self.expected if name == self.run_id and leaf == "complete.json" else None)
                if name == self.run_id:
                    self.leaves[leaf] = raw
        _require("complete.json" in self.leaves and _sha(self.leaves["complete.json"]) == self.expected,
                 "verification_external_pin_refused")

    def observation(self) -> dict:
        return {"namespace_parts": list(ARTIFACT_PARTS), "run_id": self.run_id,
            "directories": {"/".join(parts): list(names) for parts, (_, names) in sorted(self.tree.directories.items())},
            "leaf_inventory": self.observed, "complete_sha256": self.expected}

    def recheck(self) -> None:
        self.tree.recheck()

    def close(self) -> None:
        self.tree.close()


def _verify_isolation() -> dict:
    """Observe deny behavior, not only a caller-supplied policy label."""
    source_mode = os.stat(__file__, follow_symlinks=False)
    _require(stat.S_ISREG(source_mode.st_mode) and source_mode.st_uid == os.geteuid() and
        stat.S_IMODE(source_mode.st_mode) & stat.S_IWUSR != 0, "worker_isolation_refused")
    denied = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.5)
        try:
            sock.connect(("127.0.0.1", 1))
        except OSError as exc:
            denied["network_denied"] = exc.errno in {1, 13}
        else:
            denied["network_denied"] = False
    finally:
        sock.close()
    try:
        pid = os.fork()
    except OSError as exc:
        denied["fork_denied"] = exc.errno in {1, 13}
    else:
        if pid == 0:
            os._exit(99)
        os.waitpid(pid, 0)
        denied["fork_denied"] = False
    # Existing owner-writable source opened WITHOUT truncation/writing. An
    # ineffective sandbox causes refusal without creating or altering a file.
    try:
        fd = os.open(__file__, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        denied["all_write_denied"] = exc.errno in {1, 13}
    else:
        os.close(fd)
        denied["all_write_denied"] = False
    _require(set(denied) == {"network_denied", "fork_denied", "all_write_denied"} and
        all(value is True for value in denied.values()), "worker_isolation_refused")
    return denied


def _verify_worker(payload: dict, *, root: Path, fixture_only: bool) -> dict:
    phase = "worker_protocol"
    tree = None
    try:
        _require(type(payload) is dict and set(payload) == {"run_id", "expected_complete_sha256", "current_identity",
            "producer_inventory", "parent_observation", "fixture_only"} and payload["fixture_only"] is fixture_only,
            "worker_protocol_refused")
        if fixture_only:
            _fixture_root(root)
        else:
            _require(root == LANE_ROOT and Path.cwd() == LANE_ROOT and Path(__file__) == LANE_ROOT / SELF_PATH,
                     "inactive_or_other_worktree_refused")
        phase = "worker_isolation"
        isolation = _verify_isolation()
        current = payload["current_identity"]
        _verify_identity_record(current, fixture_only=fixture_only)
        phase = "worker_current_sources"
        _require(_source_current_bytes(root, current["source_sha256"]) == current["source_sha256"],
                 "worker_current_inventory_refused")
        phase = "worker_input_snapshot"
        tree = _VerificationTree(root, payload["run_id"], payload["expected_complete_sha256"], fixture_only=fixture_only)
        _require(tree.observation() == payload["parent_observation"], "worker_observation_differs")
        producer = payload["producer_inventory"]
        complete = _json(tree.leaves["complete.json"])
        _require(type(producer) is dict and set(producer) == {"head", "source_sha256", "source_inventory_sha256",
            "original_committed_bytes_verified", "whole_historical_environment_executed"} and
            producer["head"] == complete["identity"]["head"] and producer["source_sha256"] == complete["identity"]["source_sha256"] and
            producer["source_inventory_sha256"] == complete["identity"]["source_inventory_sha256"] and
            producer["original_committed_bytes_verified"] is (not fixture_only) and
            producer["whole_historical_environment_executed"] is False, "worker_original_inventory_refused")
        phase = "worker_terminal_replay"
        result = verify_supplied_terminal(tree.leaves["complete.json"], payload["expected_complete_sha256"],
            tree.leaves, tree.claims, fixture_only=fixture_only)
        tree.recheck()
        phase = "worker_final_sources"
        _require(_source_current_bytes(root, current["source_sha256"]) == current["source_sha256"],
                 "worker_current_inventory_refused")
        tree.recheck()
        return {"schema": "insider-benzinga-observed-custody-verification-v1", "run_id": payload["run_id"],
            "complete_sha256": payload["expected_complete_sha256"], "current_verifier_identity": current,
            "original_producer_inventory": producer, "observation_sha256": _sha(_canonical(tree.observation())),
            "leaf_count": len(tree.observed), "fixture_only": fixture_only, "isolation": isolation,
            "private_source_custody_rechecked": True, "terminal_replay": result,
            "historical_environment_executed": False, **{flag: False for flag in FALSE_FLAGS}}
    except Exception as exc:
        result = EarningsGapError("verification_worker_refused")
        result.failure_fields = _failure_fields(exc, phase)
        raise result from None
    finally:
        if tree is not None:
            tree.close()


def _launch_verify_worker(payload: dict, *, root: Path) -> dict:
    command = ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin:/usr/sbin:/sbin", "/usr/bin/sandbox-exec", "-p",
        VERIFICATION_POLICY, sys.executable, "-B", "-m", "research.insider_buying_benzinga_earnings_gap_capture_v1",
        "--verification-worker", "--run-id", payload["run_id"], "--expected-head", payload["current_identity"]["head"],
        "--expected-complete-sha256", payload["expected_complete_sha256"])
    launched = subprocess.run(command, cwd=root, input=_canonical(payload), capture_output=True, check=False,
        timeout=180, env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
    _require(launched.returncode == 0 and not launched.stderr and type(launched.stdout) is bytes and
        0 < len(launched.stdout) <= MAX_VERIFIER_OUTPUT_BYTES, "verification_worker_refused")
    # The production worker CLI uses print, adding exactly one framing LF.
    # Removing arbitrary whitespace would admit rehashed noncanonical wire.
    return _json(launched.stdout.removesuffix(b"\n"))


def _verification_round(run_id: str, expected_head: str, expected_complete_sha256: str, *, root: Path,
                        fixture_only: bool, identity: Callable, producer_inventory: Callable,
                        launch_worker: Callable) -> dict:
    phase, tree = "fixed_preflight", None
    try:
        if fixture_only:
            _fixture_root(root)
            _require(identity is not _identity and producer_inventory is not _producer_git_inventory and
                launch_worker is not _launch_verify_worker, "fixture_real_callback_refused")
        else:
            _require(root == LANE_ROOT and identity is _identity and producer_inventory is _producer_git_inventory and
                launch_worker is _launch_verify_worker, "inactive_or_other_worktree_refused")
        _require(type(expected_complete_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", expected_complete_sha256) is not None,
                 "verification_external_pin_refused")
        phase = "current_identity"
        current = identity(expected_head)
        phase = "input_snapshot"
        tree = _VerificationTree(root, run_id, expected_complete_sha256, fixture_only=fixture_only)
        complete = _json(tree.leaves["complete.json"])
        _verify_identity_record(complete["identity"], fixture_only=fixture_only)
        phase = "producer_git_inventory"
        producer = producer_inventory(complete["identity"])
        tree.recheck()
        _require(identity(expected_head) == current, "current_source_changed")
        payload = {"run_id": run_id, "expected_complete_sha256": expected_complete_sha256,
            "current_identity": current, "producer_inventory": producer,
            "parent_observation": tree.observation(), "fixture_only": fixture_only}
        phase = "isolated_worker"
        result = launch_worker(payload, root=root)
        phase = "after_worker_identity"
        _require(identity(expected_head) == current, "current_source_changed")
        phase = "after_worker_custody"
        tree.recheck()
        _require(type(result) is dict and set(result) == {"schema", "run_id", "complete_sha256", "current_verifier_identity",
            "original_producer_inventory", "observation_sha256", "leaf_count", "fixture_only", "isolation",
            "private_source_custody_rechecked", "terminal_replay", "historical_environment_executed", *FALSE_FLAGS} and
            result["schema"] == "insider-benzinga-observed-custody-verification-v1" and result["run_id"] == run_id and
            result["complete_sha256"] == expected_complete_sha256 and result["current_verifier_identity"] == current and
            result["original_producer_inventory"] == producer and result["fixture_only"] is fixture_only and
            result["observation_sha256"] == _sha(_canonical(tree.observation())) and
            type(result["leaf_count"]) is int and result["leaf_count"] == len(tree.observed) and
            result["private_source_custody_rechecked"] is True and result["historical_environment_executed"] is False and
            result["isolation"] == {"network_denied": True, "fork_denied": True, "all_write_denied": True} and
            all(type(value) is bool for value in result["isolation"].values()) and
            result["terminal_replay"] == verify_supplied_terminal(tree.leaves["complete.json"], expected_complete_sha256,
                tree.leaves, tree.claims, fixture_only=fixture_only) and all(result[flag] is False for flag in FALSE_FLAGS),
            "verification_worker_reply_refused")
        tree.recheck()
        _require(identity(expected_head) == current, "current_source_changed")
        return result
    except Exception as exc:
        result = EarningsGapError("verification_input_custody_refused")
        result.failure_fields = _failure_fields(exc, phase)
        raise result from None
    finally:
        if tree is not None:
            tree.close()


def verify_actual_capture(run_id: str, expected_head: str, expected_complete_sha256: str) -> dict:
    """No credential/provider access: fixed clean current source, original Git
    modules, held actual custody and a separately isolated pure replay worker."""
    return _verification_round(run_id, expected_head, expected_complete_sha256, root=LANE_ROOT, fixture_only=False,
        identity=_identity, producer_inventory=_producer_git_inventory, launch_worker=_launch_verify_worker)


def verify_fixture_capture(run_id: str, expected_head: str, expected_complete_sha256: str, *, root: Path,
                           identity: Callable, producer_inventory: Callable, launch_worker: Callable) -> dict:
    _fixture_root(root)  # before callbacks, source or custody constructors
    return _verification_round(run_id, expected_head, expected_complete_sha256, root=root, fixture_only=True,
        identity=identity, producer_inventory=producer_inventory, launch_worker=launch_worker)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-previous-complete-sha256")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--verification-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--expected-complete-sha256")
    args = parser.parse_args(argv)
    try:
        if args.verification_worker:
            payload_raw = sys.stdin.buffer.read(MAX_CONTROL_BYTES + 1)
            _require(0 < len(payload_raw) <= MAX_CONTROL_BYTES, "worker_protocol_refused")
            payload = _json(payload_raw)
            _require(payload.get("run_id") == args.run_id and payload.get("expected_complete_sha256") == args.expected_complete_sha256 and
                payload.get("current_identity", {}).get("head") == args.expected_head, "worker_protocol_refused")
            result = _verify_worker(payload, root=LANE_ROOT, fixture_only=False)
        elif args.verify_only:
            result = verify_actual_capture(args.run_id, args.expected_head, args.expected_complete_sha256)
        else:
            result = run_capture(args.run_id, args.expected_head,
                expected_previous_complete_sha256=args.expected_previous_complete_sha256)
    except Exception as exc:
        refused = {"disposition": "bounded_earnings_capture_refused_claims_preserved"}
        if args.verify_only or args.verification_worker:
            refused["verification_failure"] = _safe_failure_fields(exc)
        else:
            refused["capture_failure"] = _capture_diagnostic(exc)
        print(_canonical(refused).decode())
        return 2
    print(_canonical(result).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

