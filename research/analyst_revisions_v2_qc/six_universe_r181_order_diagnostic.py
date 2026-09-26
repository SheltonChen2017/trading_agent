"""One-use, redacted rejection diagnosis for the exact R181 A2 QC backtest.

This host-only reader has no action on import. It reads only the order pages of
the already completed, execution-invalid A2 run. The owner must explicitly
authorize the broader read; a private O_EXCL claim is spent before contact.
No raw order, security, timestamp, price, or message is persisted or returned.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from .six_universe_coverage_submission import production_client


class R181OrderDiagnosticError(ValueError):
    """The exact A2 authority or bounded diagnostic response was refused."""


_PROJECT_ID = 36_891_750
_BACKTEST_ID = "a74626d4d6ce7360ae95d2e1d7930910"
_PROJECT_NAME = "104 ARV2 SIX CAP90 SIGNAL R181 2021 2025"
_PROJECTION_SHA256 = "b68661ec2f90f98eb47e09242b8b9d4cd8ed21101667f355afba0a4a48461c29"
_PROFILE_SHA256 = "d27c558b71d20694e803a244e89f3feb79ba5084971c8d6d8eefa7cf8ecf09f0"
_BACKTEST_NAME = "ARV2 R181A2 six cap90 signal 2021 2025 b68661ec"
_AGGREGATE_SHA256 = "1376e1096b63e2189b0c44eccd54935391cf0e830ae736fd13b9fa20f604cc78"
_EXPECTED_ORDER_COUNT = 6_289
_EXPECTED_FILLED_COUNT = 6_267
_EXPECTED_INVALID_COUNT = 22
_PAGE_SPAN = 99  # QC requires end-start < 100.
_MAXIMUM_PAGE_COUNT = 64
_CONTROL_LIMIT = 16 * 1024
_CLAIM_NAME = "R181-A2-invalid-order-diagnostic-claim.json"
_RESULT_NAME = "R181-A2-invalid-order-diagnostic-result.json"
_SCHEMA_PROBE_CLAIM_NAME = "R181-A2-order-schema-probe-v2-claim.json"
_SCHEMA_PROBE_RESULT_NAME = "R181-A2-order-schema-probe-v2-result.json"
_SHAPE_TREE_CLAIM_NAME = "R181-A2-order-shape-tree-v3-claim.json"
_SHAPE_TREE_RESULT_NAME = "R181-A2-order-shape-tree-v3-result.json"
_RECOVERY_CLAIM_NAME = "R181-A2-invalid-order-diagnostic-v4-claim.json"
_RECOVERY_RESULT_NAME = "R181-A2-invalid-order-diagnostic-v4-result.json"
_TIMING_CLAIM_NAME = "R181-A2-buying-power-timing-v5-claim.json"
_TIMING_RESULT_NAME = "R181-A2-buying-power-timing-v5-result.json"
_RECEIPT_NAMES = (
    "R181-A2-claim.json", "R181-A2-launch.json",
    "R181-A2-terminal.json", "R181-A2-result-read-claim.json",
)
_REASONS = (
    "INSUFFICIENT_BUYING_POWER",
    "SECURITY_UNTRADABLE_OR_DELISTED",
    "ORDER_TYPE_OR_TIMING_UNSUPPORTED",
    "INVALID_QUANTITY",
    "PRICE_OR_MARGIN_BAND",
    "OTHER_REDACTED",
    "MULTIPLE_REASONS",
)
_REASON_PATTERNS = (
    ("INSUFFICIENT_BUYING_POWER", re.compile(r"buying power|insufficient cash|insufficient margin", re.I)),
    ("SECURITY_UNTRADABLE_OR_DELISTED", re.compile(r"not tradable|not tradeable|delist|security is not active|security has not been added", re.I)),
    ("ORDER_TYPE_OR_TIMING_UNSUPPORTED", re.compile(r"unsupported order|order type is not supported|market.on.open.*(?:only|cannot|not allowed)|cannot.*market.on.open", re.I)),
    ("INVALID_QUANTITY", re.compile(r"invalid quantity|zero quantity|quantity must|fractional shares|lot size", re.I)),
    ("PRICE_OR_MARGIN_BAND", re.compile(r"price band|price is (?:too|below|above)|minimum price|maximum price|margin requirement", re.I)),
)


def _refuse() -> None:
    # Never interpolate a QC response or an order message into an exception.
    # Suppress an exception's implicit context as well: QC request failures
    # may contain raw order text that would otherwise appear in tracebacks.
    raise R181OrderDiagnosticError(
        "R181 A2 order diagnosis refused; the one-use claim remains spent if present"
    ) from None


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _open_private_directory(path: Path) -> int:
    if not isinstance(path, Path) or not path.is_absolute():
        _refuse()
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(fd)
    except OSError:
        _refuse()
    if (
        not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
        or (hasattr(os, "getuid") and info.st_uid != os.getuid())
    ):
        os.close(fd)
        _refuse()
    return fd


def _read_private_record(directory_fd: int, name: str) -> tuple[dict, str]:
    try:
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        try:
            info = os.fstat(fd)
            raw = os.read(fd, _CONTROL_LIMIT + 1)
        finally:
            os.close(fd)
        if (
            not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or not 0 < len(raw) <= _CONTROL_LIMIT or info.st_size != len(raw)
            or (hasattr(os, "getuid") and info.st_uid != os.getuid())
        ):
            _refuse()
        value = json.loads(raw.decode("ascii"))
        if type(value) is not dict or _canonical(value) != raw:
            _refuse()
        return value, hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError, UnicodeError, TypeError, RecursionError):
        _refuse()


def _write_once(directory_fd: int, name: str, value: dict) -> None:
    raw = _canonical(value)
    if not 0 < len(raw) <= _CONTROL_LIMIT:
        _refuse()
    try:
        fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600, dir_fd=directory_fd,
        )
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(fd)
        os.fsync(directory_fd)
    except OSError:
        _refuse()


def _verify_a2_receipts(directory_fd: int) -> dict[str, str]:
    records = {}
    digests = {}
    for name in _RECEIPT_NAMES:
        records[name], digests[name] = _read_private_record(directory_fd, name)
    claim, launch, terminal, spent = (records[name] for name in _RECEIPT_NAMES)
    if (
        claim.get("candidate_id") != "R181" or claim.get("attempt") != 2
        or claim.get("role") != "signal" or claim.get("project_id") != _PROJECT_ID
        or claim.get("projection_sha256") != _PROJECTION_SHA256
        or claim.get("profile_sha256") != _PROFILE_SHA256
        or type(claim.get("source_files")) is not list or len(claim["source_files"]) != 13
        or launch.get("candidate_id") != "R181" or launch.get("attempt") != 2
        or launch.get("role") != "signal" or launch.get("project_id") != _PROJECT_ID
        or launch.get("project_name") != _PROJECT_NAME
        or launch.get("backtest_id") != _BACKTEST_ID
        or launch.get("backtest_name") != _BACKTEST_NAME
        or launch.get("projection_sha256") != _PROJECTION_SHA256
        or launch.get("profile_sha256") != _PROFILE_SHA256
        or terminal != {
            "candidate_id": "R181", "status": "Completed.",
            "project_id": _PROJECT_ID, "backtest_id": _BACKTEST_ID,
        }
        or spent != {
            "candidate_id": "R181", "project_id": _PROJECT_ID,
            "backtest_id": _BACKTEST_ID,
        }
        or claim.get("profile_id") != launch.get("profile_id")
    ):
        _refuse()
    # An A2 valid receipt would contradict the recorded execution-invalid run.
    try:
        os.stat("R181-A2-result-valid.json", dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except OSError:
        _refuse()
    else:
        _refuse()
    return digests


def _status(value: object) -> str:
    if type(value) is int:
        return {3: "Filled", 7: "Invalid"}.get(value, "")
    if type(value) is str and value in {"Filled", "Invalid", "filled", "invalid"}:
        return value.title()
    return ""


def _category(message: str) -> str:
    matches = [name for name, pattern in _REASON_PATTERNS if pattern.search(message)]
    if len(matches) > 1:
        return "MULTIPLE_REASONS"
    return matches[0] if matches else "OTHER_REDACTED"


def _invalid_reason(row: dict) -> str:
    events = row.get("events")
    if type(events) is not list or not 0 < len(events) <= 128:
        _refuse()
    categories = set()
    for event in events:
        if type(event) is not dict:
            _refuse()
        if _status(event.get("status")) != "Invalid":
            continue
        message = event.get("message")
        if type(message) is not str or not 0 < len(message) <= 4096:
            _refuse()
        categories.add(_category(message))
    if not categories:
        _refuse()
    return categories.pop() if len(categories) == 1 else "MULTIPLE_REASONS"


def _direction(value: object) -> str | None:
    if type(value) is int:
        return {0: "BUY", 1: "SELL"}.get(value)
    if type(value) is str:
        return {"buy": "BUY", "sell": "SELL"}.get(value.lower())
    return None


def _time_bin(value: object) -> str:
    """Classify an exact UTC event time; never retain the timestamp."""
    try:
        if type(value) in (int, float):
            numeric = Decimal(str(value))
            if not numeric.is_finite():
                return "UNKNOWN"
            epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
            if Decimal("1600000000") <= numeric <= Decimal("1800000000"):
                seconds = numeric
            elif Decimal("1600000000000") <= numeric <= Decimal("1800000000000"):
                seconds = numeric / Decimal(1000)
            else:
                return "UNKNOWN"
            whole_seconds = int(seconds)
            microseconds = int((seconds - whole_seconds) * 1_000_000)
            utc = epoch + timedelta(
                seconds=whole_seconds, microseconds=microseconds,
            )
        elif (
            type(value) is str and len(value) <= 40
            and re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z",
                value,
            )
        ):
            utc = datetime.fromisoformat(value[:-1] + "+00:00")
        else:
            return "UNKNOWN"
        local = utc.astimezone(ZoneInfo("America/New_York"))
    except (OverflowError, ValueError, OSError):
        return "UNKNOWN"
    if not date(2021, 1, 4) <= local.date() <= date(2025, 12, 31):
        return "UNKNOWN"
    return "PRE_OPEN" if (local.hour, local.minute) < (9, 30) else "AT_OR_AFTER_OPEN"


def _invalid_direction_and_time(row: dict) -> tuple[str, str]:
    row_direction = _direction(row.get("direction"))
    event_directions = set()
    event_bins = set()
    for event in row["events"]:
        if _status(event.get("status")) == "Invalid":
            event_direction = _direction(event.get("direction"))
            if event_direction is not None:
                event_directions.add(event_direction)
            event_bins.add(_time_bin(event.get("time")))
    if len(event_directions) > 1 or (
        row_direction is not None and event_directions
        and row_direction not in event_directions
    ):
        _refuse()
    direction = row_direction or (
        next(iter(event_directions)) if event_directions else "UNKNOWN"
    )
    time_bin = next(iter(event_bins)) if len(event_bins) == 1 else "UNKNOWN"
    return direction, time_bin


def _read_redacted_pages(
    client: object, *, recover_transient_shape: bool = False,
    classify_timing: bool = False,
) -> dict[str, object]:
    observed: dict[int, tuple[str, str | None]] = {}
    timing_census: list[tuple[str, str]] = []
    start = 0
    inclusive_end: bool | None = None
    shape_retries = 0
    endpoint_calls = 0
    length_mode: str | None = None
    for _ in range(_MAXIMUM_PAGE_COUNT):
        if len(observed) == _EXPECTED_ORDER_COUNT:
            break
        end = min(
            start + _PAGE_SPAN,
            _EXPECTED_ORDER_COUNT - (1 if inclusive_end else 0),
        )
        while True:
            endpoint_calls += 1
            if endpoint_calls > _MAXIMUM_PAGE_COUNT + (2 if recover_transient_shape else 0):
                _refuse()
            try:
                response = client.request("backtests/orders/read", {
                    "projectId": _PROJECT_ID, "backtestId": _BACKTEST_ID,
                    "start": start, "end": end,
                })
            except Exception:
                _refuse()
            if type(response) is not dict or response.get("success") is not True:
                _refuse()
            rows = response.get("orders")
            reported_length = response.get("length")
            if type(rows) is list and type(reported_length) is int:
                break
            if (
                not recover_transient_shape
                or rows is not None or reported_length is not None
                or shape_retries >= 2
            ):
                _refuse()
            shape_retries += 1
        if not 0 < len(rows) <= 100:
            _refuse()
        mode = (
            "page" if reported_length == len(rows)
            else "total" if recover_transient_shape and reported_length == _EXPECTED_ORDER_COUNT
            else None
        )
        if mode is None or (length_mode is not None and mode != length_mode):
            _refuse()
        length_mode = mode
        if inclusive_end is None:
            if len(rows) not in (_PAGE_SPAN, _PAGE_SPAN + 1):
                _refuse()
            inclusive_end = len(rows) == _PAGE_SPAN + 1
        expected_rows = end - start + int(inclusive_end)
        if len(rows) != expected_rows or start + len(rows) > _EXPECTED_ORDER_COUNT:
            _refuse()
        for row in rows:
            if type(row) is not dict or type(row.get("id")) is not int or row["id"] < 0:
                _refuse()
            status = _status(row.get("status"))
            if not status:
                _refuse()
            value = (status, _invalid_reason(row) if status == "Invalid" else None)
            if classify_timing and status == "Invalid":
                timing_census.append(_invalid_direction_and_time(row))
            if row["id"] in observed:
                _refuse()
            observed[row["id"]] = value
        start += len(rows)
    else:
        if len(observed) != _EXPECTED_ORDER_COUNT:
            _refuse()
    if len(observed) != _EXPECTED_ORDER_COUNT:
        _refuse()
    filled = sum(status == "Filled" for status, _ in observed.values())
    invalid = sum(status == "Invalid" for status, _ in observed.values())
    if filled != _EXPECTED_FILLED_COUNT or invalid != _EXPECTED_INVALID_COUNT:
        _refuse()
    reasons = {name: 0 for name in _REASONS}
    for status, reason in observed.values():
        if status == "Invalid":
            if reason not in reasons:
                _refuse()
            reasons[reason] += 1
    if sum(reasons.values()) != _EXPECTED_INVALID_COUNT:
        _refuse()
    result = {
        "schema": "arv2-r181-a2-redacted-order-reasons-v1",
        "filled_order_count": filled, "invalid_order_count": invalid,
        "reason_counts": reasons,
    }
    if recover_transient_shape:
        result.update({
            "schema": "arv2-r181-a2-redacted-order-reasons-v4",
            "transient_shape_retry_count": shape_retries,
            "length_mode": length_mode,
            "endpoint_call_count": endpoint_calls,
        })
    if classify_timing:
        if (
            not recover_transient_shape
            or reasons["INSUFFICIENT_BUYING_POWER"] != _EXPECTED_INVALID_COUNT
            or len(timing_census) != _EXPECTED_INVALID_COUNT
        ):
            _refuse()
        result["schema"] = "arv2-r181-a2-buying-power-timing-v5"
        result.pop("reason_counts")
        result["direction_counts"] = {
            name: sum(side == name for side, _ in timing_census)
            for name in ("BUY", "SELL", "UNKNOWN")
        }
        result["time_bin_counts"] = {
            name: sum(time_bin == name for _, time_bin in timing_census)
            for name in ("PRE_OPEN", "AT_OR_AFTER_OPEN", "UNKNOWN")
        }
    return result


def diagnose_r181_a2_rejections(*, owner_authorized: bool, control_directory: Path) -> dict[str, object]:
    """Spend one diagnostic read and return only fixed category counts.

    The caller must supply explicit owner authorization for reading individual
    QC orders; the earlier aggregate-only result claim does not authorize it.
    Any failure leaves the O_EXCL claim spent so no silent retry is possible.
    """
    if owner_authorized is not True:
        _refuse()
    directory_fd = _open_private_directory(control_directory)
    try:
        receipt_digests = _verify_a2_receipts(directory_fd)
        _write_once(directory_fd, _CLAIM_NAME, {
            "schema": "arv2-r181-a2-order-diagnostic-claim-v1",
            "candidate_id": "R181", "attempt": 2,
            "project_id": _PROJECT_ID, "backtest_id": _BACKTEST_ID,
            "projection_sha256": _PROJECTION_SHA256,
            "profile_sha256": _PROFILE_SHA256,
            "aggregate_sha256": _AGGREGATE_SHA256,
            "owner_authorized_individual_order_read": True,
            "expected_order_count": _EXPECTED_ORDER_COUNT,
            "expected_invalid_count": _EXPECTED_INVALID_COUNT,
            "maximum_endpoint_calls": _MAXIMUM_PAGE_COUNT,
            "receipt_sha256": receipt_digests,
        })
        try:
            result = _read_redacted_pages(production_client())
        except R181OrderDiagnosticError:
            raise
        except Exception:
            _refuse()
        _write_once(directory_fd, _RESULT_NAME, result)
        return result
    finally:
        os.close(directory_fd)


def probe_r181_a2_order_page_schema(*, owner_authorized: bool, control_directory: Path) -> dict[str, object]:
    """One newly claimed page read after the v1 reader refused its first page.

    Return only container types and counts, never order values or raw fields.
    This does not retry the spent v1 classification claim or launch a backtest.
    """
    if owner_authorized is not True:
        _refuse()
    directory_fd = _open_private_directory(control_directory)
    try:
        receipt_digests = _verify_a2_receipts(directory_fd)
        prior_claim, prior_claim_sha256 = _read_private_record(directory_fd, _CLAIM_NAME)
        if (
            prior_claim.get("schema") != "arv2-r181-a2-order-diagnostic-claim-v1"
            or prior_claim.get("project_id") != _PROJECT_ID
            or prior_claim.get("backtest_id") != _BACKTEST_ID
            or prior_claim.get("receipt_sha256") != receipt_digests
        ):
            _refuse()
        try:
            os.stat(_RESULT_NAME, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError:
            _refuse()
        else:
            _refuse()
        _write_once(directory_fd, _SCHEMA_PROBE_CLAIM_NAME, {
            "schema": "arv2-r181-a2-order-schema-probe-v2-claim-v1",
            "project_id": _PROJECT_ID,
            "backtest_id": _BACKTEST_ID,
            "prior_failed_claim_sha256": prior_claim_sha256,
            "receipt_sha256": receipt_digests,
            "maximum_endpoint_calls": 1,
            "raw_order_values_retained": False,
        })
        try:
            response = production_client().request("backtests/orders/read", {
                "projectId": _PROJECT_ID, "backtestId": _BACKTEST_ID,
                "start": 0, "end": _PAGE_SPAN,
            })
        except Exception:
            _refuse()
        if type(response) is not dict or response.get("success") is not True:
            _refuse()
        rows = response.get("orders")
        length = response.get("length")
        if type(rows) is list:
            container = "list"
            item = rows[0] if rows else None
        elif type(rows) is dict:
            container = "dict"
            item = next(iter(rows.values())) if rows else None
        elif rows is None:
            container = "missing_or_null"
            item = None
        else:
            container = "other"
            item = None
        result = {
            "schema": "arv2-r181-a2-order-page-shape-v2",
            "orders_container": container,
            "orders_count": len(rows) if container in ("list", "dict") else None,
            "first_order_value_is_object": type(item) is dict,
            "length_is_integer": type(length) is int,
            "length_value": length if type(length) is int and 0 <= length <= 100_000 else None,
        }
        _write_once(directory_fd, _SCHEMA_PROBE_RESULT_NAME, result)
        return result
    finally:
        os.close(directory_fd)


def _shape_tree(value: object, depth: int = 0) -> dict[str, object]:
    """Bounded JSON shape with digested keys; no value or raw key survives."""
    if type(value) is dict:
        items = sorted(
            (
                hashlib.sha256(key.encode("utf-8")).hexdigest(), child
            )
            for key, child in value.items()
            if type(key) is str
        )
        if len(items) != len(value):
            _refuse()
        return {
            "type": "object", "count": len(items),
            "members": [
                {"key_sha256": key_hash, "shape": _shape_tree(child, depth + 1)}
                for key_hash, child in items[:32]
            ] if depth < 2 else [],
        }
    if type(value) is list:
        return {
            "type": "array", "count": len(value),
            "first_shape": _shape_tree(value[0], depth + 1)
            if value and depth < 2 else None,
        }
    if value is None:
        kind = "null"
    elif type(value) is bool:
        kind = "boolean"
    elif type(value) is int:
        kind = "integer"
    elif type(value) is float:
        kind = "number"
    elif type(value) is str:
        kind = "string"
    else:
        _refuse()
    return {"type": kind}


def probe_r181_a2_order_shape_tree(*, owner_authorized: bool, control_directory: Path) -> dict[str, object]:
    """Final one-page shape probe after v2 revealed no top-level orders field."""
    if owner_authorized is not True:
        _refuse()
    directory_fd = _open_private_directory(control_directory)
    try:
        receipt_digests = _verify_a2_receipts(directory_fd)
        previous, previous_sha256 = _read_private_record(
            directory_fd, _SCHEMA_PROBE_RESULT_NAME,
        )
        if (
            previous.get("schema") != "arv2-r181-a2-order-page-shape-v2"
            or previous.get("orders_container") != "missing_or_null"
        ):
            _refuse()
        _write_once(directory_fd, _SHAPE_TREE_CLAIM_NAME, {
            "schema": "arv2-r181-a2-order-shape-tree-v3-claim-v1",
            "project_id": _PROJECT_ID, "backtest_id": _BACKTEST_ID,
            "previous_probe_result_sha256": previous_sha256,
            "receipt_sha256": receipt_digests,
            "maximum_endpoint_calls": 1,
            "raw_keys_or_values_retained": False,
        })
        try:
            response = production_client().request("backtests/orders/read", {
                "projectId": _PROJECT_ID, "backtestId": _BACKTEST_ID,
                "start": 0, "end": _PAGE_SPAN,
            })
        except Exception:
            _refuse()
        if type(response) is not dict or response.get("success") is not True:
            _refuse()
        result = {
            "schema": "arv2-r181-a2-order-shape-tree-v3",
            "response_shape": _shape_tree(response),
        }
        _write_once(directory_fd, _SHAPE_TREE_RESULT_NAME, result)
        return result
    finally:
        os.close(directory_fd)


def diagnose_r181_a2_rejections_v4(*, owner_authorized: bool, control_directory: Path) -> dict[str, object]:
    """One final bounded recovery after the observed intermittent page shape.

    At most two missing-shape page responses may be retried. All usable rows
    must still reconcile exactly to the pinned 6,289/6,267/22 census.
    """
    if owner_authorized is not True:
        _refuse()
    directory_fd = _open_private_directory(control_directory)
    try:
        receipt_digests = _verify_a2_receipts(directory_fd)
        shape, shape_sha256 = _read_private_record(
            directory_fd, _SHAPE_TREE_RESULT_NAME,
        )
        expected_members = {
            hashlib.sha256(name.encode("ascii")).hexdigest(): kind
            for name, kind in (("orders", "array"), ("length", "integer"), ("success", "boolean"))
        }
        members = shape.get("response_shape", {}).get("members")
        if (
            shape.get("schema") != "arv2-r181-a2-order-shape-tree-v3"
            or type(members) is not list or len(members) != 3
            or {
                item.get("key_sha256"): item.get("shape", {}).get("type")
                for item in members if type(item) is dict
            } != expected_members
        ):
            _refuse()
        _write_once(directory_fd, _RECOVERY_CLAIM_NAME, {
            "schema": "arv2-r181-a2-redacted-order-recovery-v4-claim-v1",
            "project_id": _PROJECT_ID, "backtest_id": _BACKTEST_ID,
            "profile_sha256": _PROFILE_SHA256,
            "aggregate_sha256": _AGGREGATE_SHA256,
            "previous_shape_sha256": shape_sha256,
            "receipt_sha256": receipt_digests,
            "maximum_endpoint_calls": _MAXIMUM_PAGE_COUNT + 2,
            "maximum_missing_shape_retries": 2,
            "raw_order_values_retained": False,
        })
        try:
            result = _read_redacted_pages(
                production_client(), recover_transient_shape=True,
            )
        except R181OrderDiagnosticError:
            raise
        except Exception:
            _refuse()
        _write_once(directory_fd, _RECOVERY_RESULT_NAME, result)
        return result
    finally:
        os.close(directory_fd)


def _verify_successful_v4(
    directory_fd: int, receipt_digests: dict[str, str],
) -> tuple[str, str]:
    shape, shape_sha256 = _read_private_record(
        directory_fd, _SHAPE_TREE_RESULT_NAME,
    )
    claim, claim_sha256 = _read_private_record(
        directory_fd, _RECOVERY_CLAIM_NAME,
    )
    result, result_sha256 = _read_private_record(
        directory_fd, _RECOVERY_RESULT_NAME,
    )
    if (
        shape.get("schema") != "arv2-r181-a2-order-shape-tree-v3"
        or claim.get("schema") != "arv2-r181-a2-redacted-order-recovery-v4-claim-v1"
        or claim.get("project_id") != _PROJECT_ID
        or claim.get("backtest_id") != _BACKTEST_ID
        or claim.get("profile_sha256") != _PROFILE_SHA256
        or claim.get("aggregate_sha256") != _AGGREGATE_SHA256
        or claim.get("previous_shape_sha256") != shape_sha256
        or claim.get("receipt_sha256") != receipt_digests
        or claim.get("maximum_endpoint_calls") != _MAXIMUM_PAGE_COUNT + 2
        or claim.get("maximum_missing_shape_retries") != 2
        or claim.get("raw_order_values_retained") is not False
        or set(result) != {
            "schema", "filled_order_count", "invalid_order_count",
            "reason_counts", "transient_shape_retry_count", "length_mode",
            "endpoint_call_count",
        }
        or result.get("schema") != "arv2-r181-a2-redacted-order-reasons-v4"
        or result.get("filled_order_count") != _EXPECTED_FILLED_COUNT
        or result.get("invalid_order_count") != _EXPECTED_INVALID_COUNT
        or result.get("reason_counts") != {
            name: _EXPECTED_INVALID_COUNT if name == "INSUFFICIENT_BUYING_POWER" else 0
            for name in _REASONS
        }
        or type(result.get("transient_shape_retry_count")) is not int
        or not 0 <= result["transient_shape_retry_count"] <= 2
        or type(result.get("length_mode")) is not str
        or result.get("length_mode") not in {"page", "total"}
        or type(result.get("endpoint_call_count")) is not int
        or not 63 <= result["endpoint_call_count"] <= _MAXIMUM_PAGE_COUNT + 2
    ):
        _refuse()
    return claim_sha256, result_sha256


def diagnose_r181_a2_buying_power_timing_v5(
    *, owner_authorized: bool, control_directory: Path,
) -> dict[str, object]:
    """One new claim for order side and NY pre-/post-open counts only.

    The v4 aggregate proves all 22 previous rejections were buying-power
    failures. No free-form deficit is parsed: QC's message has no pinned
    numeric-shortfall schema. This read leaves v4 unchanged and cannot retry.
    """
    if owner_authorized is not True:
        _refuse()
    directory_fd = _open_private_directory(control_directory)
    try:
        receipt_digests = _verify_a2_receipts(directory_fd)
        prior_claim_sha256, prior_result_sha256 = _verify_successful_v4(
            directory_fd, receipt_digests,
        )
        _write_once(directory_fd, _TIMING_CLAIM_NAME, {
            "schema": "arv2-r181-a2-buying-power-timing-v5-claim-v1",
            "project_id": _PROJECT_ID, "backtest_id": _BACKTEST_ID,
            "profile_sha256": _PROFILE_SHA256,
            "aggregate_sha256": _AGGREGATE_SHA256,
            "receipt_sha256": receipt_digests,
            "v4_claim_sha256": prior_claim_sha256,
            "v4_result_sha256": prior_result_sha256,
            "owner_authorized_individual_order_read": True,
            "maximum_pages": _MAXIMUM_PAGE_COUNT,
            "maximum_endpoint_calls": _MAXIMUM_PAGE_COUNT + 2,
            "raw_order_values_retained": False,
            "numeric_shortfall_parsed": False,
        })
        try:
            result = _read_redacted_pages(
                production_client(), recover_transient_shape=True,
                classify_timing=True,
            )
        except R181OrderDiagnosticError:
            raise
        except Exception:
            _refuse()
        _write_once(directory_fd, _TIMING_RESULT_NAME, result)
        return result
    finally:
        os.close(directory_fd)


__all__ = (
    "R181OrderDiagnosticError", "diagnose_r181_a2_rejections",
    "diagnose_r181_a2_rejections_v4",
    "diagnose_r181_a2_buying_power_timing_v5",
    "probe_r181_a2_order_page_schema",
    "probe_r181_a2_order_shape_tree",
)
