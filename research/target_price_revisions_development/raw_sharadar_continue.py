"""Fresh bounded continuation; the executed parent collector is immutable.

The first native page is authenticated and reused, never refetched. Missing
FIGI is null, not a fabricated identifier; permaticker is only a current
source identity, not proof of historical cross-provider symbol continuity.
All source rows/CSV/refusals stay private. Imports perform no I/O.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import io
import os
from pathlib import Path
import re
import stat

from . import raw_sharadar_source as parent

CAPTURE_ID = "TPR-SHARADAR-CONTINUE-20261007-001"
PRIVATE_ROOT = parent.LANE_ROOT / "artifacts" / "target_price_raw_revision_source" / CAPTURE_ID
PARENT_SHA256 = "7487a0990c4d3f80d4230c7f0bc03a471579620a3bc6ea25be7951d7c47dcb03"
FIRST_PAGE_SHA256 = "8efa0c24558feebd4f17ba636c231622e177c53ea1d7389c5f37472158d38372"
FIRST_PAGE_BYTES = 451759
OWNER_SHA256 = parent._digest(b"other lanes have been using those data. skip the rights part. start backtesting immediately")
LIMITS = {"remaining_requests": 19, "total_response_bytes_including_parent": 32 * 1024 * 1024,
    "bytes_per_page": 4 * 1024 * 1024, "rows_per_page": 10000,
    "tickers_remaining_pages": 9, "actions_pages": 10, "request_timeout_seconds": 30,
    "rows_per_dataset": 100000, "retries": 0, "redirects": 0, "first_page_refetches": 0}
_FIXED_RESOLVER = parent._FIXED_RESOLVER
_FIXED_TRANSPORT = parent._FIXED_TRANSPORT
_production_credential = _FIXED_RESOLVER
_https_get = _FIXED_TRANSPORT


class ContinueError(parent.SharadarSourceError):
    """Closed diagnostics never echo native records or provider exceptions."""


@dataclass(frozen=True)
class ParsedCSV:
    rows: tuple[dict, ...]
    source_rows: int
    refusals: tuple[dict, ...]
    missing_optional_column: bool


def parse_source_csv(payload: bytes, dataset: str) -> ParsedCSV:
    """Exact native column families; semantic bad rows retain named refusals."""
    if type(dataset) is not str or dataset not in parent.FIELDS or type(payload) is not bytes or not 0 < len(payload) <= LIMITS["bytes_per_page"]:
        raise ContinueError("invalid continuation CSV framing")
    optional = "figi" if dataset == "tickers" else "contraticker"
    full_columns = set(parent.FIELDS[dataset])
    try:
        text = payload.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        if len(header) != len(set(header)) or set(header) not in (full_columns, full_columns - {optional}):
            raise ValueError
        missing = optional not in header
        accepted, refusals, total = [], [], 0
        for cells in reader:
            if len(cells) != len(header) or total >= LIMITS["rows_per_page"]:
                raise ValueError
            total += 1
            row = dict(zip(header, cells))
            if missing:
                row[optional] = None
            reason = None
            if any(len(value) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in value) for value in cells):
                reason = "invalid_native_cell"
            elif re.fullmatch(r"[A-Z][A-Z0-9.\-/]{0,31}", row["ticker"]) is None:
                reason = "invalid_native_ticker"
            elif dataset == "tickers":
                if re.fullmatch(r"[1-9][0-9]{0,19}", row["permaticker"]) is None:
                    reason = "invalid_native_permaticker"
                elif row["isdelisted"] not in ("Y", "N"):
                    reason = "unknown_native_delisting_status"
                elif row["figi"] and re.fullmatch(r"[A-Z0-9]{12}", row["figi"]) is None:
                    reason = "invalid_native_figi"
            else:
                try:
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date"]) is None:
                        raise ValueError
                    date.fromisoformat(row["date"])
                    if not "2024-08-01" <= row["date"] <= "2025-03-31":
                        reason = "outside_frozen_source_dates"
                except ValueError:
                    reason = "invalid_native_date"
                if reason is None and not row["action"]:
                    reason = "missing_native_action"
                if reason is None and row["contraticker"] and re.fullmatch(r"[A-Z][A-Z0-9.\-/]{0,31}", row["contraticker"]) is None:
                    reason = "invalid_native_counterparty"
            if reason:
                refusals.append({"row_number": total, "reason": reason})
            else:
                accepted.append(row)
        return ParsedCSV(tuple(accepted), total, tuple(refusals), missing)
    except (UnicodeError, ValueError, csv.Error, StopIteration, OverflowError):
        raise ContinueError("continuation CSV structural schema refused") from None


@dataclass(frozen=True)
class CapturePlan:
    payload: bytes
    sha256: str

    def body(self) -> dict:
        if type(self.payload) is not bytes or not 0 < len(self.payload) <= 16384 or parent._digest(self.payload) != self.sha256:
            raise ContinueError("invalid continuation plan identity")
        try:
            body = parent._source_object(self.payload)
            expected = freeze_capture_plan(code_sha256=body["code_sha256"], git_sha=body["git_sha"],
                owner_instruction_sha256=body["owner_instruction_sha256"], created_utc=body["created_utc"],
                expires_utc=body["expires_utc"], mode=body["mode"],
                first_page_sha256=body["first_page_sha256"], first_page_bytes=body["first_page_bytes"])
            if self.payload != expected.payload:
                raise ContinueError("continuation plan policy mismatch")
            return body
        except (TypeError, ValueError, KeyError):
            raise ContinueError("invalid continuation plan policy") from None


def freeze_capture_plan(*, code_sha256: str, git_sha: str, owner_instruction_sha256: str,
                        created_utc: str, expires_utc: str, mode: str = "production",
                        first_page_sha256: str = FIRST_PAGE_SHA256,
                        first_page_bytes: int = FIRST_PAGE_BYTES) -> CapturePlan:
    parent._hash(code_sha256)
    parent._hash(git_sha, 40)
    parent._hash(owner_instruction_sha256)
    parent._hash(first_page_sha256)
    if type(mode) is not str or mode not in ("production", "offline-fixture"):
        raise ContinueError("invalid continuation mode")
    if type(first_page_bytes) is not int or not 0 < first_page_bytes <= LIMITS["bytes_per_page"]:
        raise ContinueError("invalid first page size")
    if mode == "production" and (first_page_sha256 != FIRST_PAGE_SHA256 or first_page_bytes != FIRST_PAGE_BYTES
            or owner_instruction_sha256 != OWNER_SHA256):
        raise ContinueError("continuation parent or owner binding mismatch")
    created, expires = parent._clock(created_utc), parent._clock(expires_utc)
    if not created < expires <= created + timedelta(hours=48):
        raise ContinueError("invalid continuation expiry")
    payload = parent._canonical({"schema": "tpr-sharadar-continuation-plan-v1", "capture_id": CAPTURE_ID,
        "code_sha256": code_sha256, "parent_code_sha256": PARENT_SHA256, "helper_sha256": parent.HELPER_SHA256,
        "git_sha": git_sha, "owner_instruction_sha256": owner_instruction_sha256, "mode": mode,
        "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "lane_root": str(parent.LANE_ROOT), "lane_branch": parent.LANE_BRANCH,
        "private_root": str(PRIVATE_ROOT), "first_page_root": str(parent.PRIVATE_ROOT),
        "first_page_file": "tickers.000.csv", "first_page_sha256": first_page_sha256,
        "first_page_bytes": first_page_bytes, "limits": dict(LIMITS),
        "queries": {"tickers": dict(parent.request_query("tickers", 1)), "actions": dict(parent.request_query("actions", 0))},
        "optional_native_columns": {"tickers": "figi", "actions": "contraticker"},
        "missing_optional_value": None, "identity_policy": "current-unique-native-permaticker-not-historical-cross-provider-proof",
        "rights": "owner-assumed-personal-local-not-vendor-attested", "outcomes": False,
        "action_cash_or_terminal_payoff_fields": False, "quantconnect": False,
        "canonical_admission": False, "trading": False, "d0_renewed": False,
        "parent_capture_renewed": False, "point_in_time_identity": False})
    return CapturePlan(payload, parent._digest(payload))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _before_expiry(body: dict, fixture_now: datetime | None) -> datetime:
    current = _now() if fixture_now is None else fixture_now
    if type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise ContinueError("invalid continuation clock")
    if not parent._clock(body["created_utc"]) <= current < parent._clock(body["expires_utc"]):
        raise ContinueError("continuation expired")
    return current


def _verify_identity(body: dict) -> None:
    parent._verify_identity({"git_sha": body["git_sha"], "code_sha256": PARENT_SHA256})
    parent._verify_code(parent.LANE_ROOT / "research/target_price_revisions_development/raw_sharadar_continue.py", body["code_sha256"])


def _read_first(root: Path, body: dict) -> bytes:
    directory_fd = parent._open_root(root, "production" if body["mode"] == "production" else "offline-fixture")
    descriptor = None
    try:
        descriptor = os.open("tickers.000.csv", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_nlink != 1 or before.st_size != body["first_page_bytes"]):
            raise ContinueError("first page custody refused")
        parts, remaining = [], before.st_size
        while remaining:
            piece = os.read(descriptor, min(remaining, 65536))
            if not piece:
                raise ContinueError("first page changed")
            parts.append(piece)
            remaining -= len(piece)
        after = os.fstat(descriptor)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ContinueError("first page changed")
        payload = b"".join(parts)
        if parent._digest(payload) != body["first_page_sha256"]:
            raise ContinueError("first page identity mismatch")
        return payload
    except OSError:
        raise ContinueError("authenticated first page unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_fd)


class _ClaimFailure(ContinueError):
    def __init__(self, interrupted: bool):
        super().__init__("continuation claim incomplete; scope remains spent")
        self.interrupted = interrupted


def _claim(directory_fd: int, plan: CapturePlan, current: datetime) -> None:
    try:
        descriptor = os.open(CAPTURE_ID + ".spent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory_fd)
    except FileExistsError:
        raise ContinueError("continuation already spent") from None
    except OSError:
        raise ContinueError("continuation claim unavailable") from None
    try:
        parent._write_fd(descriptor, parent._canonical({"schema": "tpr-sharadar-continuation-spent-v1",
            "capture_id": CAPTURE_ID, "plan_sha256": plan.sha256, "mode": plan.body()["mode"],
            "started_utc": current.isoformat()}))
        os.fsync(directory_fd)
    except KeyboardInterrupt:
        raise _ClaimFailure(True) from None
    except OSError:
        raise _ClaimFailure(False) from None
    finally:
        os.close(descriptor)


def execute_capture(plan: CapturePlan, private_root: Path, *, first_page_root: Path | None = None,
                    now: datetime | None = None, credential_resolver=None, transport=None) -> parent.CaptureResult:
    if type(plan) is not CapturePlan:
        raise ContinueError("invalid continuation plan frame")
    body = plan.body()
    mode = body["mode"]
    if mode == "production":
        if now is not None or first_page_root is not None or credential_resolver is not None or transport is not None:
            raise ContinueError("production continuation adapters cannot be injected")
        if private_root != PRIVATE_ROOT:
            raise ContinueError("continuation requires fixed private root")
        _verify_identity(body)
        first_page_root = parent.PRIVATE_ROOT
    elif (first_page_root is None or first_page_root == parent.PRIVATE_ROOT or private_root in (PRIVATE_ROOT, parent.PRIVATE_ROOT)
            or credential_resolver is None or transport is None
            or credential_resolver in (_FIXED_RESOLVER, _production_credential)
            or transport in (_FIXED_TRANSPORT, _https_get)):
        raise ContinueError("offline continuation requires synthetic roots and adapters")
    current = _before_expiry(body, now)
    directory_fd = parent._open_root(private_root, "offline-fixture")
    try:
        claim_failure = None
        try:
            _claim(directory_fd, plan, current)
        except _ClaimFailure as failure:
            claim_failure = failure
        stage, status, failure, interrupted = "claim" if claim_failure else "parent_source", "FAILED", None, False
        rows = {dataset: [] for dataset in parent.FIELDS}
        pages = {dataset: [] for dataset in parent.FIELDS}
        counts = {dataset: 0 for dataset in parent.FIELDS}
        refusal_counts, refusals = {}, {dataset: [] for dataset in parent.FIELDS}
        absent_optional = {dataset: 0 for dataset in parent.FIELDS}
        attempts, total_bytes, last_http_status = 0, 0, None
        source_path, source_sha256 = None, None
        try:
            if claim_failure:
                if claim_failure.interrupted:
                    raise KeyboardInterrupt
                raise claim_failure
            first = _read_first(first_page_root, body)
            parsed = parse_source_csv(first, "tickers")
            if parsed.source_rows != LIMITS["rows_per_page"]:
                raise ContinueError("first page is not the frozen full source page")
            parent._publish(directory_fd, "tickers.000.csv", first)
            total_bytes = len(first)
            first_hash = parent._digest(first)
            def retain(dataset, page, payload, parsed):
                if counts[dataset] + parsed.source_rows > LIMITS["rows_per_dataset"]:
                    raise ContinueError("continuation row budget exhausted")
                filename = dataset + "." + str(page).zfill(3) + ".csv"
                pages[dataset].append({"file": filename, "sha256": parent._digest(payload),
                    "bytes": len(payload), "source_rows": parsed.source_rows,
                    "admitted_rows": len(parsed.rows), "missing_optional_column": parsed.missing_optional_column})
                rows[dataset].extend(parsed.rows)
                counts[dataset] += parsed.source_rows
                absent_optional[dataset] += parsed.missing_optional_column
                for refusal in parsed.refusals:
                    reason = refusal["reason"]
                    refusal_counts[reason] = refusal_counts.get(reason, 0) + 1
                    refusals[dataset].append(dict(refusal, page=page))
            retain("tickers", 0, first, parsed)
            stage = "expiry"
            _before_expiry(body, now)
            stage = "credential"
            resolver = _production_credential if mode == "production" else credential_resolver
            fetch = _https_get if mode == "production" else transport
            credential = resolver("sharadar")
            if not parent._valid_credential(credential) or mode == "offline-fixture" and not credential.startswith("SYNTHETIC_"):
                raise ContinueError("credential unavailable")
            for dataset, start in (("tickers", 1), ("actions", 0)):
                seen = {first_hash} if dataset == "tickers" else set()
                for page in range(start, 10):
                    stage = "expiry"
                    _before_expiry(body, now)
                    budget = min(LIMITS["bytes_per_page"], LIMITS["total_response_bytes_including_parent"] - total_bytes)
                    if budget <= 0:
                        raise ContinueError("continuation byte budget exhausted")
                    stage = "transport"
                    attempts += 1
                    response = fetch(dataset, page, credential, budget)
                    last_http_status = (response.status if type(response) is parent.CaptureResponse
                        and type(response.status) is int and 100 <= response.status <= 599 else None)
                    stage = "response"
                    payload = parent._validate_response(response, credential, budget)
                    total_bytes += len(payload)
                    stage = "publication"
                    parent._publish(directory_fd, dataset + "." + str(page).zfill(3) + ".csv", payload)
                    stage = "csv_schema"
                    parsed = parse_source_csv(payload, dataset)
                    stage = "pagination"
                    identity = parent._digest(payload)
                    if parsed.source_rows and identity in seen:
                        raise ContinueError("repeated continuation page refused")
                    seen.add(identity)
                    retain(dataset, page, payload, parsed)
                    if parsed.source_rows < LIMITS["rows_per_page"]:
                        break
                else:
                    raise ContinueError("continuation page budget exhausted")
            captured = _now() if now is None else now
            source_body = {"schema": "tpr-sharadar-native-source-v1", "capture_id": CAPTURE_ID,
                "plan_sha256": plan.sha256, "mode": mode, "capture_utc": captured.isoformat(),
                "parent_capture_id": parent.CAPTURE_ID, "first_page_sha256": body["first_page_sha256"],
                "tickers": rows["tickers"], "actions": rows["actions"], "pages": pages, "refusals": refusals,
                "source_rows": counts, "missing_optional_column_pages": absent_optional,
                "pagination_terminated": True, "transactional_snapshot": False, "point_in_time_identity": False,
                "historical_cross_provider_identity_proven": False, "history_versions_complete": False,
                "caveats": parent._row_caveats(rows), "source_window": {"from": "2024-08-01", "to": "2025-03-31"}}
            payload = parent._canonical(source_body)
            source_sha256 = parent._digest(payload)
            filename = CAPTURE_ID + "." + source_sha256 + ".source.json"
            stage = "publication"
            parent._publish(directory_fd, filename, payload)
            source_path, status, stage = private_root / filename, "COMPLETED", "completed"
        except KeyboardInterrupt:
            status, failure, interrupted = "INTERRUPTED", "continuation_interrupted", True
        except Exception:
            failure = "continuation_failed"
        action_counts = {kind: 0 for kind in parent.ACTION_KINDS + ("other",)}
        in_window = dict(action_counts)
        for row in rows["actions"]:
            kind = row["action"] if row["action"] in parent.ACTION_KINDS else "other"
            action_counts[kind] += 1
            if "2025-01-02" <= row["date"] <= "2025-03-31":
                in_window[kind] += 1
        report = {"schema": "tpr-sharadar-continuation-report-v1", "capture_id": CAPTURE_ID, "mode": mode,
            "plan_sha256": plan.sha256, "status": status, "failure": failure,
            "failure_stage": stage if status != "COMPLETED" else None, "last_http_status": last_http_status,
            "first_page_reused": bool(pages["tickers"]), "first_page_refetches": 0,
            "source_sha256": source_sha256, "source_row_counts": counts,
            "admitted_row_counts": {dataset: len(rows[dataset]) for dataset in rows},
            "row_refusal_counts": refusal_counts, "missing_optional_column_pages": absent_optional,
            "page_counts": {dataset: len(pages[dataset]) for dataset in pages},
            "response_bytes_including_parent": total_bytes, "action_kind_counts": action_counts,
            "in_window_action_kind_counts": in_window, "pagination_terminated": status == "COMPLETED",
            "source_caveats": parent._row_caveats(rows), "rights": "owner-assumed-personal-local-not-vendor-attested",
            "canonical_admission": False, "real_backtest_ready": False,
            "historical_cross_provider_identity_proven": False, "outcome_reads": 0,
            "development_looks": 0, "quantconnect_attempts": 0, "trading": False,
            "provider_requests": attempts if mode == "production" else 0,
            "fixture_transport_calls": attempts if mode == "offline-fixture" else 0}
        payload = parent._canonical(report)
        identity = parent._digest(payload)
        aggregate_name = CAPTURE_ID + "." + identity + ".aggregate.json"
        terminal_name = CAPTURE_ID + ".terminal.json"
        parent._publish(directory_fd, aggregate_name, payload)
        parent._publish(directory_fd, terminal_name, parent._canonical({"schema": "tpr-sharadar-continuation-terminal-v1",
            "capture_id": CAPTURE_ID, "plan_sha256": plan.sha256, "status": status,
            "aggregate_sha256": identity, "source_sha256": source_sha256,
            "outcome_reads": 0, "development_looks": 0, "quantconnect_attempts": 0}))
        if interrupted:
            raise KeyboardInterrupt("continuation interrupted; scope remains spent") from None
        return parent.CaptureResult(payload, identity, source_path, private_root / aggregate_name, private_root / terminal_name)
    finally:
        os.close(directory_fd)
