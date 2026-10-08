"""Bounded private TICKERS/ACTIONS capture for an owner-assumed local study.

Imports are inert. This is source discovery, not an outcome look, historical
identity proof, corporate-action payoff engine or vendor rights attestation.
The raw CSV and projected native rows stay in the fixed owner-only directory.
"""
from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import http.client
import html
import io
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import subprocess
import threading
from urllib.parse import unquote, urlencode

from .source_audit import (LANE_BRANCH, LANE_ROOT, SourceAuditError, _canonical,
    _clock, _digest, _production_credential, _publish, _source_object,
    _valid_credential, _write_fd)

CAPTURE_ID = "TPR-SHARADAR-SOURCE-20261007-001"
PRIVATE_ROOT = LANE_ROOT / "artifacts" / "target_price_raw_revision_source" / CAPTURE_ID
HELPER_SHA256 = "9f2674a47d0d62bb09e2dd5ba1ce7f37eed3c68dce254e40e0d11d1218f46960"
LIMITS = {"pages_per_dataset": 10, "rows_per_page": 10000,
    "bytes_per_page": 4 * 1024 * 1024, "total_response_bytes": 32 * 1024 * 1024,
    "request_timeout_seconds": 30, "requests": 20, "redirects": 0, "retries": 0}
FIELDS = {"tickers": ("ticker", "permaticker", "figi", "category", "exchange", "isdelisted"),
    "actions": ("ticker", "date", "action", "contraticker")}
ACTION_KINDS = ("dividend", "split", "spinoff", "tickerchange", "listed", "delisted", "acquisition", "relation")
_FIXED_RESOLVER = _production_credential


class SharadarSourceError(SourceAuditError):
    """Closed refusals contain no native rows, credential or provider errors."""


class _ClaimFailure(SharadarSourceError):
    def __init__(self, interrupted: bool):
        super().__init__("capture claim incomplete; scope remains spent")
        self.interrupted = interrupted


def _hash(value: object, length: int = 64) -> str:
    if type(value) is not str or re.fullmatch("[0-9a-f]{" + str(length) + "}", value) is None:
        raise SharadarSourceError("invalid capture identity")
    return value


def request_query(dataset: str, page: int) -> tuple[tuple[str, str], ...]:
    if type(dataset) is not str or dataset not in FIELDS or type(page) is not int or not 0 <= page < 10:
        raise SharadarSourceError("invalid fixed source page")
    scope = (("table", "stocks"),) if dataset == "tickers" else (("from", "2024-08-01"), ("to", "2025-03-31"))
    return (("format", "csv"),) + scope + (("fields", ",".join(FIELDS[dataset])),
        ("limit", "10000"), ("skip", str(page * 10000)),
        ("sort", "ticker.asc" if dataset == "tickers" else "date.asc"))


@dataclass(frozen=True)
class CapturePlan:
    payload: bytes
    sha256: str

    def body(self) -> dict:
        if type(self.payload) is not bytes or not 0 < len(self.payload) <= 16384 or _digest(self.payload) != self.sha256:
            raise SharadarSourceError("invalid capture plan identity")
        try:
            body = _source_object(self.payload)
            expected = freeze_capture_plan(code_sha256=body["code_sha256"], git_sha=body["git_sha"],
                owner_instruction_sha256=body["owner_instruction_sha256"], created_utc=body["created_utc"],
                expires_utc=body["expires_utc"], mode=body["mode"])
            if expected.payload != self.payload:
                raise SharadarSourceError("capture plan policy mismatch")
            return body
        except (TypeError, ValueError, KeyError):
            raise SharadarSourceError("invalid capture plan policy") from None


def freeze_capture_plan(*, code_sha256: str, git_sha: str, owner_instruction_sha256: str,
                        created_utc: str, expires_utc: str, mode: str = "production") -> CapturePlan:
    _hash(code_sha256)
    _hash(git_sha, 40)
    _hash(owner_instruction_sha256)
    if type(mode) is not str or mode not in ("production", "offline-fixture"):
        raise SharadarSourceError("invalid capture mode")
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not created < expires <= created + timedelta(hours=48):
        raise SharadarSourceError("invalid capture expiry")
    body = {"schema": "tpr-sharadar-source-plan-v1", "capture_id": CAPTURE_ID,
        "code_sha256": code_sha256, "helper_sha256": HELPER_SHA256, "git_sha": git_sha,
        "owner_instruction_sha256": owner_instruction_sha256, "mode": mode,
        "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "lane_root": str(LANE_ROOT), "lane_branch": LANE_BRANCH, "private_root": str(PRIVATE_ROOT),
        "queries": {dataset: dict(request_query(dataset, 0)) for dataset in FIELDS},
        "limits": dict(LIMITS), "rights": "owner-assumed-personal-local-not-vendor-attested",
        "raw_retention": "private-only", "outcomes": False, "quantconnect": False,
        "canonical_admission": False, "trading": False, "point_in_time_identity": False,
        "historical_versions_complete": False, "d0_renewed": False}
    body["action_cash_or_terminal_payoff_fields"] = False
    payload = _canonical(body)
    return CapturePlan(payload, _digest(payload))


def parse_source_csv(payload: bytes, dataset: str) -> list[dict[str, str]]:
    """Project requested native columns without inventing IDs or fact labels."""
    if type(dataset) is not str or dataset not in FIELDS or type(payload) is not bytes or not 0 < len(payload) <= LIMITS["bytes_per_page"]:
        raise SharadarSourceError("invalid source CSV framing")
    try:
        text = payload.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        if len(header) != len(set(header)) or set(header) != set(FIELDS[dataset]):
            raise ValueError
        rows = []
        for cells in reader:
            if len(cells) != len(header) or len(rows) >= LIMITS["rows_per_page"]:
                raise ValueError
            if any(len(value) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in value) for value in cells):
                raise ValueError
            row = dict(zip(header, cells))
            if not re.fullmatch(r"[A-Z][A-Z0-9.\-/]{0,31}", row["ticker"]):
                raise ValueError
            if dataset == "tickers":
                if (not re.fullmatch(r"[1-9][0-9]{0,19}", row["permaticker"])
                        or row["isdelisted"] not in ("Y", "N")
                        or row["figi"] and re.fullmatch(r"[A-Z0-9]{12}", row["figi"]) is None):
                    raise ValueError
            else:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date"]):
                    raise ValueError
                date.fromisoformat(row["date"])
                if not "2024-08-01" <= row["date"] <= "2025-03-31" or not row["action"]:
                    raise ValueError
                if row["contraticker"] and not re.fullmatch(r"[A-Z][A-Z0-9.\-/]{0,31}", row["contraticker"]):
                    raise ValueError
            rows.append(row)
        return rows
    except (UnicodeError, ValueError, csv.Error, StopIteration, OverflowError):
        raise SharadarSourceError("source CSV schema refused") from None


@dataclass(frozen=True)
class CaptureResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    complete: bool = True


class _Deadline(Exception):
    pass


@contextmanager
def _deadline():
    if (threading.current_thread() is not threading.main_thread() or not hasattr(signal, "setitimer")
            or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0)):
        raise SharadarSourceError("request deadline unavailable")
    previous = signal.getsignal(signal.SIGALRM)
    def expired(_signum, _frame):
        raise _Deadline()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 30)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _credential_echo(payload: bytes, credential: str) -> bool:
    text = payload.decode("utf-8", errors="replace")
    # Source retention is permitted, credential retention is not. Decode the
    # common literal/form/HTML/Unicode echo spellings before persisting CSV.
    for _ in range(3):
        if credential in text:
            return True
        text = html.unescape(unquote(text))
        text = re.sub(r"\\u([0-9A-Fa-f]{4})", lambda match: chr(int(match[1], 16)), text)
    return credential in text


def _validate_response(response: CaptureResponse, credential: str, budget: int) -> bytes:
    if (type(response) is not CaptureResponse or type(response.status) is not int or response.status != 200
            or type(response.headers) is not tuple or type(response.body) is not bytes
            or response.complete is not True or not 0 < len(response.body) <= budget):
        raise SharadarSourceError("source response refused")
    headers = {}
    for pair in response.headers:
        if type(pair) is not tuple or len(pair) != 2 or any(type(v) is not str for v in pair):
            raise SharadarSourceError("source headers refused")
        key, value = pair[0].lower(), pair[1]
        if key in headers:
            raise SharadarSourceError("source headers refused")
        headers[key] = value
    if (headers.get("content-encoding", "").strip().lower() not in ("", "identity")
            or headers.get("content-type", "").split(";", 1)[0].strip().lower()
                not in ("text/csv", "application/csv", "application/octet-stream", "text/plain")):
        raise SharadarSourceError("source media refused")
    length = headers.get("content-length")
    if length is not None and (re.fullmatch(r"[0-9]{1,9}", length) is None or int(length) != len(response.body)):
        raise SharadarSourceError("source length refused")
    if _credential_echo(response.body, credential):
        raise SharadarSourceError("credential echo refused")
    return response.body


def _https_get(dataset: str, page: int, credential: str, budget: int) -> CaptureResponse:
    query = request_query(dataset, page)
    if not _valid_credential(credential) or type(budget) is not int or not 0 < budget <= LIMITS["bytes_per_page"]:
        raise SharadarSourceError("invalid fixed source request")
    connection = None
    try:
        with _deadline():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            context.keylog_filename = None
            context.load_default_certs()
            connection = http.client.HTTPSConnection("api.sharadar.com", 443, timeout=30, context=context)
            connection.set_debuglevel(0)
            path = "/v1.0/data/" + dataset + "?" + urlencode(query + (("api_key", credential),))
            connection.request("GET", path, headers={"Accept": "text/csv", "Accept-Encoding": "identity",
                "Connection": "close", "User-Agent": "TPR-private-source/1"})
            response = connection.getresponse()
            headers = tuple((key.lower(), value) for key, value in response.getheaders()
                if key.lower() in ("content-type", "content-encoding", "content-length"))
            # Refuse non-200/redirect/encoded responses before reading any body.
            if response.status != 200 or dict(headers).get("content-encoding", "").strip().lower() not in ("", "identity"):
                return CaptureResponse(response.status, headers, b"", False)
            if (len(headers) != len(dict(headers)) or dict(headers).get("content-type", "").split(";", 1)[0].strip().lower()
                    not in ("text/csv", "application/csv", "application/octet-stream", "text/plain")):
                return CaptureResponse(response.status, headers, b"", False)
            length = dict(headers).get("content-length")
            if length is not None and (re.fullmatch(r"[0-9]{1,9}", length) is None or int(length) > budget):
                return CaptureResponse(response.status, headers, b"", False)
            payload = response.read(budget)
            result = CaptureResponse(response.status, headers, payload,
                len(payload) < budget or response.isclosed())
            return result
    except (OSError, http.client.HTTPException, _Deadline):
        raise SharadarSourceError("source transport failed") from None
    finally:
        if connection is not None:
            connection.close()


_FIXED_TRANSPORT = _https_get


def _verify_code(path: Path, expected: str) -> None:
    descriptor = None
    try:
        if path.resolve() != path:
            raise SharadarSourceError("capture code custody refused")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= 262144:
            raise SharadarSourceError("capture code refused")
        payload = os.read(descriptor, metadata.st_size)
        if len(payload) != metadata.st_size or _digest(payload) != expected:
            raise SharadarSourceError("capture code identity mismatch")
    except OSError:
        raise SharadarSourceError("capture code unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _verify_identity(body: dict) -> None:
    try:
        if Path.cwd() != LANE_ROOT or Path.cwd().resolve() != LANE_ROOT:
            raise SharadarSourceError("capture requires designated physical lane")
        observed = [subprocess.run(cmd, cwd=LANE_ROOT, capture_output=True, check=True, timeout=5).stdout.decode("ascii").strip()
            for cmd in (["git", "rev-parse", "--show-toplevel"], ["git", "branch", "--show-current"], ["git", "rev-parse", "HEAD"])]
        if observed != [str(LANE_ROOT), LANE_BRANCH, body["git_sha"]]:
            raise SharadarSourceError("capture lane identity mismatch")
        _verify_code(LANE_ROOT / "research/target_price_revisions_development/raw_sharadar_source.py", body["code_sha256"])
        _verify_code(LANE_ROOT / "research/target_price_revisions_development/source_audit.py", HELPER_SHA256)
    except (OSError, UnicodeError, subprocess.SubprocessError):
        raise SharadarSourceError("capture lane identity unavailable") from None


def _open_root(root: Path, mode: str) -> int:
    descriptor = None
    try:
        if (type(root) is not type(LANE_ROOT) or not root.is_absolute() or root.resolve() != root
                or mode == "production" and root != PRIVATE_ROOT or mode == "offline-fixture" and root == PRIVATE_ROOT):
            raise SharadarSourceError("invalid capture root")
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        for component in root.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise SharadarSourceError("capture root custody refused")
        result, descriptor = descriptor, None
        return result
    except OSError:
        raise SharadarSourceError("private capture root unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _claim(directory_fd: int, plan: CapturePlan, now: datetime) -> None:
    try:
        descriptor = os.open(CAPTURE_ID + ".spent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory_fd)
    except FileExistsError:
        raise SharadarSourceError("capture already spent") from None
    except OSError:
        raise SharadarSourceError("capture claim unavailable") from None
    try:
        _write_fd(descriptor, _canonical({"schema": "tpr-sharadar-source-spent-v1", "capture_id": CAPTURE_ID,
            "plan_sha256": plan.sha256, "started_utc": now.isoformat(), "mode": plan.body()["mode"]}))
        os.fsync(directory_fd)
    except KeyboardInterrupt:
        raise _ClaimFailure(True) from None
    except OSError:
        raise _ClaimFailure(False) from None
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class CaptureResult:
    payload: bytes
    sha256: str
    source_path: Path | None
    aggregate_path: Path
    terminal_path: Path


def _row_caveats(rows: dict) -> dict:
    duplicate_counts, conflicting_counts = {}, {}
    for dataset in FIELDS:
        observed, native_keys = set(), {}
        duplicates, conflicts = 0, 0
        for row in rows[dataset]:
            exact = tuple(row[field] for field in FIELDS[dataset])
            duplicates += exact in observed
            observed.add(exact)
            key_fields = ("ticker", "permaticker") if dataset == "tickers" else ("ticker", "date", "action", "contraticker")
            key = tuple(row[field] for field in key_fields)
            variants = native_keys.setdefault(key, set())
            conflicts += bool(variants) and exact not in variants
            variants.add(exact)
        duplicate_counts[dataset], conflicting_counts[dataset] = duplicates, conflicts
    return {"duplicate_projected_rows": duplicate_counts, "conflicting_projected_keys": conflicting_counts,
        "missing_identity_fields": {field: sum(not row[field] for row in rows["tickers"])
            for field in ("figi", "category", "exchange")},
        "rows_deduplicated": False, "native_action_key_unique_proven": False,
        "offset_pagination_stability_proven": False, "global_source_completeness_proven": False}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _current_before_expiry(body: dict, fixture_now: datetime | None) -> datetime:
    current = _now() if fixture_now is None else fixture_now
    if type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise SharadarSourceError("invalid capture clock")
    if not _clock(body["created_utc"]) <= current < _clock(body["expires_utc"]):
        raise SharadarSourceError("capture plan expired")
    return current


def execute_capture(plan: CapturePlan, private_root: Path, *, now: datetime | None = None,
                    credential_resolver=None, transport=None) -> CaptureResult:
    """One fresh capture, with immutable claim before credential resolution."""
    if type(plan) is not CapturePlan:
        raise SharadarSourceError("invalid capture plan frame")
    body = plan.body()
    mode = body["mode"]
    if mode == "production":
        if now is not None or credential_resolver is not None or transport is not None:
            raise SharadarSourceError("production adapters cannot be injected")
        _verify_identity(body)
    elif (credential_resolver is None or transport is None
            or credential_resolver in (_FIXED_RESOLVER, _production_credential)
            or transport in (_FIXED_TRANSPORT, _https_get)):
        raise SharadarSourceError("offline capture requires synthetic adapters")
    current = _current_before_expiry(body, now)
    directory_fd = _open_root(private_root, mode)
    try:
        claim_failure = None
        try:
            _claim(directory_fd, plan, current)
        except _ClaimFailure as failure:
            claim_failure = failure
        status, failure, interrupted = "FAILED", "source_incomplete", False
        rows = {dataset: [] for dataset in FIELDS}
        pages, counts, attempts, total_bytes = {}, {dataset: 0 for dataset in FIELDS}, 0, 0
        source_path, source_sha256 = None, None
        stage, last_http_status, csv_failures = "claim" if claim_failure else "credential", None, 0
        try:
            if claim_failure:
                if claim_failure.interrupted:
                    raise KeyboardInterrupt
                raise claim_failure
            stage = "expiry"
            _current_before_expiry(body, now)
            stage = "credential"
            resolver = _production_credential if mode == "production" else credential_resolver
            fetch = _https_get if mode == "production" else transport
            credential = resolver("sharadar")
            if not _valid_credential(credential) or mode == "offline-fixture" and not credential.startswith("SYNTHETIC_"):
                raise SharadarSourceError("credential unavailable")
            for dataset in FIELDS:
                pages[dataset] = []
                seen = set()
                for page in range(LIMITS["pages_per_dataset"]):
                    stage = "expiry"
                    _current_before_expiry(body, now)
                    budget = min(LIMITS["bytes_per_page"], LIMITS["total_response_bytes"] - total_bytes)
                    if budget <= 0:
                        raise SharadarSourceError("source aggregate budget refused")
                    stage = "transport"
                    attempts += 1
                    response = fetch(dataset, page, credential, budget)
                    last_http_status = (response.status if type(response) is CaptureResponse
                        and type(response.status) is int and 100 <= response.status <= 599 else None)
                    stage = "response"
                    payload = _validate_response(response, credential, budget)
                    total_bytes += len(payload)
                    identity = _digest(payload)
                    filename = dataset + "." + str(page).zfill(3) + ".csv"
                    # Preserve authorized opaque native evidence before schema
                    # assumptions, so a parser repair needs no new provider pull.
                    stage = "publication"
                    _publish(directory_fd, filename, payload)
                    pages[dataset].append({"file": filename, "sha256": identity, "bytes": len(payload), "rows": None})
                    stage = "csv_schema"
                    parsed = parse_source_csv(payload, dataset)
                    pages[dataset][-1]["rows"] = len(parsed)
                    stage = "pagination"
                    if parsed and identity in seen:
                        raise SharadarSourceError("repeated source page refused")
                    seen.add(identity)
                    rows[dataset].extend(parsed)
                    counts[dataset] += len(parsed)
                    if len(parsed) < LIMITS["rows_per_page"]:
                        break
                else:
                    raise SharadarSourceError("source page budget exhausted; completeness unproven")
            captured = _now() if now is None else now
            source = {"schema": "tpr-sharadar-native-source-v1", "capture_id": CAPTURE_ID,
                "plan_sha256": plan.sha256, "capture_utc": captured.isoformat(), "mode": mode,
                "tickers": rows["tickers"], "actions": rows["actions"], "pages": pages,
                "pagination_terminated": True, "transactional_snapshot": False,
                "point_in_time_identity": False, "history_versions_complete": False,
                "source_window": {"from": "2024-08-01", "to": "2025-03-31"},
                "caveats": _row_caveats(rows)}
            source_payload = _canonical(source)
            source_sha256 = _digest(source_payload)
            filename = CAPTURE_ID + "." + source_sha256 + ".source.json"
            stage = "publication"
            _publish(directory_fd, filename, source_payload)
            source_path, status, failure = private_root / filename, "COMPLETED", None
            stage = "completed"
        except KeyboardInterrupt:
            status, failure, interrupted = "INTERRUPTED", "capture_interrupted", True
        except Exception:
            # Exceptions can contain query credentials or native record values.
            failure = "claim_failed" if stage == "claim" else "capture_failed"
            csv_failures = 1 if stage == "csv_schema" else 0
        action_counts = {kind: 0 for kind in ACTION_KINDS + ("other",)}
        in_window = {kind: 0 for kind in ACTION_KINDS + ("other",)}
        for row in rows["actions"]:
            kind = row["action"] if row["action"] in ACTION_KINDS else "other"
            action_counts[kind] += 1
            if "2025-01-02" <= row["date"] <= "2025-03-31":
                in_window[kind] += 1
        report = {"schema": "tpr-sharadar-source-report-v1", "capture_id": CAPTURE_ID,
            "status": status, "failure": failure, "mode": mode, "plan_sha256": plan.sha256,
            "failure_stage": stage if status != "COMPLETED" else None,
            "last_http_status": last_http_status, "csv_schema_failures": csv_failures,
            "source_sha256": source_sha256, "row_counts": counts,
            "page_counts": {dataset: len(pages.get(dataset, [])) for dataset in FIELDS},
            "response_bytes": total_bytes, "action_kind_counts": action_counts,
            "in_window_action_kind_counts": in_window,
            "pagination_terminated": status == "COMPLETED", "transactional_snapshot": False,
            "personal_rights": "owner-assumed-not-vendor-attested", "point_in_time_identity": False,
            "history_versions_complete": False, "canonical_admission": False,
            "real_backtest_ready": False, "outcome_reads": 0, "development_looks": 0,
            "quantconnect_attempts": 0, "trading": False,
            "provider_requests": attempts if mode == "production" else 0,
            "fixture_transport_calls": attempts if mode == "offline-fixture" else 0,
            "source_caveats": _row_caveats(rows)}
        payload = _canonical(report)
        identity = _digest(payload)
        aggregate_name = CAPTURE_ID + "." + identity + ".aggregate.json"
        terminal_name = CAPTURE_ID + ".terminal.json"
        _publish(directory_fd, aggregate_name, payload)
        _publish(directory_fd, terminal_name, _canonical({"schema": "tpr-sharadar-source-terminal-v1",
            "capture_id": CAPTURE_ID, "plan_sha256": plan.sha256, "status": status,
            "aggregate_sha256": identity, "source_sha256": source_sha256, "outcome_reads": 0,
            "development_looks": 0, "quantconnect_attempts": 0}))
        if interrupted:
            raise KeyboardInterrupt("source capture interrupted; scope remains spent") from None
        return CaptureResult(payload, identity, source_path, private_root / aggregate_name, private_root / terminal_name)
    finally:
        os.close(directory_fd)
