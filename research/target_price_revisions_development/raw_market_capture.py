"""One reserved empirical acquisition; native prices/payoffs remain private.

CAPTURED is not a completed backtest. The ordinary raw_run executor cannot
rearm this look: both use the same candidate.spent.json reservation. Imports
perform no I/O. Local owner custody is cooperative, not protected antirollback.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import http.client
import io
import os
from pathlib import Path
import re
import ssl
import stat
from urllib.parse import urlencode

from . import raw_run
from . import raw_sharadar_source as source

CAPTURE_ID = "TPR-RAWREV-MARKET-20261007-001"
CANDIDATE_ID = raw_run.CANDIDATE_ID
PRODUCTION_ROOT = raw_run.PRODUCTION_ROOT
CODE_FILES = ("raw_revision.py", "raw_backtest.py", "raw_candidate.py", "raw_run.py",
    "raw_market_capture.py", "raw_source_prepare.py", "raw_market_inputs.py")
LIMITS = {"requests": 10, "pages_per_dataset": 5, "rows_per_page": 10000,
    "bytes_per_page": 4 * 1024 * 1024, "total_bytes": 32 * 1024 * 1024,
    "tickers": 200, "request_seconds": 30, "redirects": 0, "retries": 0}
FIELDS = {"stocks": ("ticker", "date", "open", "close", "closeunadj", "volume"),
    "actions": ("ticker", "date", "action", "value", "contraticker")}
_production_credential = source._FIXED_RESOLVER
_FIXED_RESOLVER = _production_credential


class MarketCaptureError(ValueError):
    """Sanitized refusals, never native values, secret URLs or provider errors."""


def _tickers(values):
    if (type(values) is not tuple or not 1 <= len(values) <= LIMITS["tickers"]
            or any(type(v) is not str or re.fullmatch(r"[A-Z][A-Z0-9.\-/]{0,31}", v) is None for v in values)
            or tuple(sorted(set(values))) != values):
        raise MarketCaptureError("invalid exact ticker inventory")
    return values


@dataclass(frozen=True)
class CapturePlan:
    payload: bytes
    sha256: str

    def body(self):
        try:
            if type(self.payload) is not bytes or not 0 < len(self.payload) <= 65536 or source._digest(self.payload) != self.sha256:
                raise MarketCaptureError("invalid market plan identity")
            body = raw_run._decode(self.payload, 65536)
            expected = freeze_capture_plan(structure_sha256=body["structure_sha256"], waiver_sha256=body["waiver_sha256"],
                tickers=tuple(body["tickers"]), code_hashes=body["code_hashes"], candidate_policy_sha256=body["candidate_policy_sha256"],
                git_sha=body["git_sha"], owner_instruction_sha256=body["owner_instruction_sha256"],
                created_utc=body["created_utc"], expires_utc=body["expires_utc"], mode=body["mode"])
            if expected.payload != self.payload:
                raise MarketCaptureError("market plan differs from fixed policy")
            return body
        except (KeyError, TypeError, ValueError):
            raise MarketCaptureError("invalid market plan policy") from None


def freeze_capture_plan(*, structure_sha256: str, waiver_sha256: str, tickers: tuple,
                        code_hashes: dict, candidate_policy_sha256: str, git_sha: str,
                        owner_instruction_sha256: str, created_utc: str, expires_utc: str,
                        mode: str = "production") -> CapturePlan:
    for value in (structure_sha256, waiver_sha256, candidate_policy_sha256, owner_instruction_sha256):
        source._hash(value)
    source._hash(git_sha, 40)
    _tickers(tickers)
    if type(code_hashes) is not dict or any(type(k) is not str for k in code_hashes) or set(code_hashes) != set(CODE_FILES):
        raise MarketCaptureError("invalid complete market code inventory")
    for value in code_hashes.values():
        source._hash(value)
    if type(mode) is not str or mode not in ("production", "offline-fixture"):
        raise MarketCaptureError("invalid market mode")
    if owner_instruction_sha256 != raw_run.OWNER_WAIVER_INSTRUCTION_SHA256:
        raise MarketCaptureError("market owner scope mismatch")
    created, expires = source._clock(created_utc), source._clock(expires_utc)
    if not created < expires <= created + timedelta(hours=48):
        raise MarketCaptureError("invalid market expiry")
    payload = source._canonical({"schema": "tpr-raw-market-plan-v1", "capture_id": CAPTURE_ID,
        "candidate_id": CANDIDATE_ID, "mode": mode, "structure_sha256": structure_sha256,
        "waiver_sha256": waiver_sha256, "tickers": list(tickers), "code_hashes": dict(code_hashes),
        "candidate_policy_sha256": candidate_policy_sha256, "git_sha": git_sha,
        "owner_instruction_sha256": owner_instruction_sha256, "created_utc": created.isoformat(),
        "expires_utc": expires.isoformat(), "lane_root": str(raw_run.LANE_ROOT), "lane_branch": raw_run.LANE_BRANCH,
        "private_root": str(PRODUCTION_ROOT), "helper_sha256": source.HELPER_SHA256,
        "transport_parent_sha256": "7487a0990c4d3f80d4230c7f0bc03a471579620a3bc6ea25be7951d7c47dcb03",
        "input_files": ["rights.json", "structure.json"], "reservation_file": CANDIDATE_ID + ".spent.json",
        "price_dates": {"from": "2024-12-31", "to": "2025-03-31"},
        "action_dates": {"from": "2025-01-02", "to": "2025-03-31"}, "fields": {k: list(v) for k, v in FIELDS.items()},
        "limits": dict(LIMITS), "empirical_looks": 1, "action_cash_or_terminal_payoff_fields": True,
        "order_based": True, "personal_only": True, "rights_verified": False,
        "canonical_admission": False, "quantconnect": False, "trading": False,
        "outcome_read_before_reservation": False, "immutable_vintage_proven": False})
    return CapturePlan(payload, source._digest(payload))


def public_plan_summary(plan: CapturePlan) -> bytes:
    body = plan.body()
    return source._canonical({"schema": "tpr-raw-market-plan-summary-v1", "capture_id": CAPTURE_ID,
        "candidate_id": CANDIDATE_ID, "market_plan_sha256": plan.sha256, "mode": body["mode"],
        "structure_sha256": body["structure_sha256"], "waiver_sha256": body["waiver_sha256"],
        "candidate_policy_sha256": body["candidate_policy_sha256"], "code_hashes": body["code_hashes"],
        "git_sha": body["git_sha"], "owner_instruction_sha256": body["owner_instruction_sha256"],
        "created_utc": body["created_utc"], "expires_utc": body["expires_utc"], "ticker_count": len(body["tickers"]),
        "price_dates": body["price_dates"], "action_dates": body["action_dates"], "limits": body["limits"],
        "empirical_looks": 1, "rights_verified": False, "canonical_admission": False,
        "quantconnect": False, "trading": False, "native_ticker_list_published": False})


def _decimal(value, *, positive):
    if (type(value) is not str or not 1 <= len(value) <= 96
            or re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value) is None):
        raise MarketCaptureError("invalid native decimal field")
    try:
        parsed = Decimal(value)
        if (not parsed.is_finite() or parsed < 0 or positive and parsed <= 0
                or parsed > Decimal("1e24") or not -32 <= parsed.as_tuple().exponent <= 32):
            raise ValueError
        return format(parsed, "f")
    except (ValueError, InvalidOperation):
        raise MarketCaptureError("invalid native decimal field") from None


def parse_source_csv(payload: bytes, dataset: str, tickers: tuple) -> list[dict]:
    _tickers(tickers)
    if type(dataset) is not str or dataset not in FIELDS or type(payload) is not bytes or not 0 < len(payload) <= LIMITS["bytes_per_page"]:
        raise MarketCaptureError("invalid market CSV framing")
    try:
        text = payload.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        required = set(FIELDS[dataset])
        allowed = (required, required - {"contraticker"}) if dataset == "actions" else (required,)
        if len(header) != len(set(header)) or set(header) not in allowed:
            raise ValueError
        rows = []
        for cells in reader:
            if len(cells) != len(header) or len(rows) >= LIMITS["rows_per_page"]:
                raise ValueError
            if any(len(v) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in v) for v in cells):
                raise ValueError
            row = dict(zip(header, cells))
            if row["ticker"] not in tickers or re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date"]) is None:
                raise ValueError
            date.fromisoformat(row["date"])
            lower = "2024-12-31" if dataset == "stocks" else "2025-01-02"
            if not lower <= row["date"] <= "2025-03-31":
                raise ValueError
            if dataset == "stocks":
                for field in ("open", "close", "closeunadj"):
                    row[field] = _decimal(row[field], positive=True)
                row["volume"] = _decimal(row["volume"], positive=False)
            else:
                row.setdefault("contraticker", None)
                if not row["action"] or row["contraticker"] and re.fullmatch(r"[A-Z][A-Z0-9.\-/]{0,31}", row["contraticker"]) is None:
                    raise ValueError
                if row["value"]:
                    row["value"] = _decimal(row["value"], positive=False)
                elif row["action"] in ("dividend", "split", "spinoff"):
                    raise ValueError
            rows.append(row)
        return rows
    except (UnicodeError, ValueError, csv.Error, StopIteration, OverflowError):
        raise MarketCaptureError("market CSV schema or semantic refusal") from None


def request_query(dataset: str, page: int, tickers: tuple):
    _tickers(tickers)
    if type(dataset) is not str or dataset not in FIELDS or type(page) is not int or not 0 <= page < 5:
        raise MarketCaptureError("invalid fixed market request")
    return (("format", "csv"), ("ticker", ",".join(tickers)),
        ("from", "2024-12-31" if dataset == "stocks" else "2025-01-02"), ("to", "2025-03-31"),
        ("fields", ",".join(FIELDS[dataset])), ("limit", "10000"), ("skip", str(page * 10000)), ("sort", "date.asc"))


def _https_get(dataset, page, tickers, credential, budget):
    query = request_query(dataset, page, tickers)
    if not source._valid_credential(credential) or type(budget) is not int or not 0 < budget <= LIMITS["bytes_per_page"]:
        raise MarketCaptureError("invalid market transport")
    connection = None
    try:
        with source._deadline():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname, context.verify_mode, context.keylog_filename = True, ssl.CERT_REQUIRED, None
            context.load_default_certs()
            connection = http.client.HTTPSConnection("api.sharadar.com", 443, timeout=30, context=context)
            connection.set_debuglevel(0)
            connection.request("GET", "/v1.0/data/" + dataset + "?" + urlencode(query + (("api_key", credential),)),
                headers={"Accept": "text/csv", "Accept-Encoding": "identity", "Connection": "close", "User-Agent": "TPR-private-market/1"})
            response = connection.getresponse()
            headers = tuple((key.lower(), value) for key, value in response.getheaders()
                if key.lower() in ("content-type", "content-encoding", "content-length"))
            meta = dict(headers)
            if (response.status != 200 or len(headers) != len(meta) or meta.get("content-encoding", "").strip().lower() not in ("", "identity")
                    or meta.get("content-type", "").split(";", 1)[0].strip().lower() not in ("text/csv", "text/plain", "application/csv", "application/octet-stream")):
                return source.CaptureResponse(response.status, headers, b"", False)
            length = meta.get("content-length")
            if length is not None and (re.fullmatch(r"[0-9]{1,9}", length) is None or int(length) > budget):
                return source.CaptureResponse(response.status, headers, b"", False)
            payload = response.read(budget)
            return source.CaptureResponse(response.status, headers, payload, len(payload) < budget or response.isclosed())
    except (OSError, http.client.HTTPException, source._Deadline):
        raise MarketCaptureError("market transport failed") from None
    finally:
        if connection is not None:
            connection.close()


_FIXED_TRANSPORT = _https_get


def _prepare_source(directory_fd, body):
    try:
        _prepare_source_checked(directory_fd, body)
    except Exception:
        raise MarketCaptureError("market source preparation refused") from None


def _prepare_source_checked(directory_fd, body):
    waiver = raw_run._decode(raw_run._read_file(directory_fd, "rights.json", 65536, body["waiver_sha256"]), 65536)
    if raw_run._source_admission(waiver)["basis"] != "explicit-owner-waiver":
        raise MarketCaptureError("market requires the exact owner waiver")
    structure = raw_run._decode(raw_run._read_file(directory_fd, "structure.json", raw_run.MAX_INPUT_BYTES, body["structure_sha256"]), raw_run.MAX_INPUT_BYTES)
    if source._clock(structure["capture_utc"]) > source._clock(body["created_utc"]):
        raise MarketCaptureError("source capture postdates frozen market plan")
    from .raw_candidate import plan_target_frames
    prepared = plan_target_frames(structure)
    if source._digest(source._canonical(prepared["policy"])) != body["candidate_policy_sha256"]:
        raise MarketCaptureError("candidate policy changed before look")
    ids = prepared["proposed_security_ids"]
    mapping = {row["security_id"]: row["ticker"] for row in structure["identities"]}
    if not ids or tuple(sorted({mapping[sid] for sid in ids})) != tuple(body["tickers"]):
        raise MarketCaptureError("planned ticker inventory differs from source targets")


def _verify_code(body):
    for filename, identity in body["code_hashes"].items():
        source._verify_code(raw_run.LANE_ROOT / "research/target_price_revisions_development" / filename, identity)
    source._verify_code(raw_run.LANE_ROOT / "research/target_price_revisions_development/source_audit.py", source.HELPER_SHA256)
    source._verify_code(raw_run.LANE_ROOT / "research/target_price_revisions_development/raw_sharadar_source.py", body["transport_parent_sha256"])


def _now():
    return datetime.now(timezone.utc)


def _before_expiry(body, fixture_now):
    current = _now() if fixture_now is None else fixture_now
    if type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise MarketCaptureError("invalid market clock")
    if not source._clock(body["created_utc"]) <= current < source._clock(body["expires_utc"]):
        raise MarketCaptureError("market plan expired")
    return current


class _ClaimFailure(MarketCaptureError):
    def __init__(self, interrupted):
        super().__init__("market reservation incomplete; candidate remains spent")
        self.interrupted = interrupted


def _reserve(directory_fd, plan, current):
    body = plan.body()
    try:
        descriptor = os.open(CANDIDATE_ID + ".spent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    except FileExistsError:
        raise MarketCaptureError("candidate already spent") from None
    except OSError:
        raise MarketCaptureError("market reservation unavailable") from None
    try:
        source._write_fd(descriptor, source._canonical({"schema": "tpr-raw-market-look-reservation-v1",
            "candidate_id": CANDIDATE_ID, "capture_id": CAPTURE_ID, "market_plan_sha256": plan.sha256,
            "started_utc": current.isoformat(), "mode": body["mode"], "structure_sha256": body["structure_sha256"],
            "waiver_sha256": body["waiver_sha256"], "code_hashes": body["code_hashes"],
            "candidate_policy_sha256": body["candidate_policy_sha256"],
            "development_look_reserved": 1 if body["mode"] == "production" else 0,
            "fixture_runs": 1 if body["mode"] == "offline-fixture" else 0}))
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
    projection_path: Path | None
    aggregate_path: Path
    terminal_path: Path


def execute_capture(plan: CapturePlan, private_root: Path = PRODUCTION_ROOT) -> CaptureResult:
    if type(plan) is not CapturePlan or plan.body()["mode"] != "production":
        raise MarketCaptureError("public market executor is production-only")
    return _execute_capture(plan, private_root)


def _execute_fixture_capture(plan, private_root, *, now=None, credential_resolver=None, transport=None):
    if type(plan) is not CapturePlan or plan.body()["mode"] != "offline-fixture":
        raise MarketCaptureError("fixture executor requires offline-fixture mode")
    return _execute_capture(plan, private_root, now=now, credential_resolver=credential_resolver, transport=transport)


def _execute_capture(plan, private_root, *, now=None, credential_resolver=None, transport=None):
    body, mode = plan.body(), plan.body()["mode"]
    if mode == "production":
        if now is not None or credential_resolver is not None or transport is not None or private_root != PRODUCTION_ROOT:
            raise MarketCaptureError("production market adapters or root cannot change")
        raw_run._verify_lane()
        source._verify_identity({"git_sha": body["git_sha"], "code_sha256": body["transport_parent_sha256"]})
    elif (private_root == PRODUCTION_ROOT or credential_resolver is None or transport is None
            or credential_resolver in (_FIXED_RESOLVER, _production_credential) or transport in (_FIXED_TRANSPORT, _https_get)):
        raise MarketCaptureError("fixture market acquisition requires synthetic adapters")
    current = _before_expiry(body, now)
    directory_fd = raw_run._open_root(private_root, mode)
    try:
        if mode == "production":
            _verify_code(body)
        _prepare_source(directory_fd, body)
        claim_failure = None
        try:
            _reserve(directory_fd, plan, current)
        except _ClaimFailure as failure:
            claim_failure = failure
        rows, pages = {dataset: [] for dataset in FIELDS}, {dataset: [] for dataset in FIELDS}
        raw_counts, duplicates = {dataset: 0 for dataset in FIELDS}, {dataset: 0 for dataset in FIELDS}
        stage, status, failure, interrupted = "reservation" if claim_failure else "expiry", "FAILED", None, False
        attempts, total_bytes, last_http_status, projection_sha256, projection_path = 0, 0, None, None, None
        try:
            if claim_failure:
                if claim_failure.interrupted:
                    raise KeyboardInterrupt
                raise claim_failure
            _before_expiry(body, now)
            stage = "credential"
            resolver = _production_credential if mode == "production" else credential_resolver
            fetch = _https_get if mode == "production" else transport
            credential = resolver("sharadar")
            if not source._valid_credential(credential) or mode == "offline-fixture" and not credential.startswith("SYNTHETIC_"):
                raise MarketCaptureError("market credential unavailable")
            for dataset in FIELDS:
                keys, hashes = {}, set()
                for page in range(5):
                    stage = "expiry"
                    _before_expiry(body, now)
                    budget = min(LIMITS["bytes_per_page"], LIMITS["total_bytes"] - total_bytes)
                    if budget <= 0:
                        raise MarketCaptureError("market byte budget exhausted")
                    stage = "transport"
                    attempts += 1
                    response = fetch(dataset, page, tuple(body["tickers"]), credential, budget)
                    last_http_status = response.status if type(response) is source.CaptureResponse and type(response.status) is int and 100 <= response.status <= 599 else None
                    stage = "response"
                    payload = source._validate_response(response, credential, budget)
                    total_bytes += len(payload)
                    filename = CAPTURE_ID + "." + dataset + "." + str(page).zfill(3) + ".csv"
                    stage = "publication"
                    source._publish(directory_fd, filename, payload)
                    stage = "csv_schema"
                    parsed = parse_source_csv(payload, dataset, tuple(body["tickers"]))
                    identity = source._digest(payload)
                    stage = "pagination"
                    if parsed and identity in hashes:
                        raise MarketCaptureError("repeated market page refused")
                    hashes.add(identity)
                    raw_counts[dataset] += len(parsed)
                    for row in parsed:
                        key = (row["ticker"], row["date"]) if dataset == "stocks" else (row["ticker"], row["date"], row["action"], row["contraticker"])
                        if key in keys:
                            if keys[key] != row:
                                raise MarketCaptureError("conflicting native market key")
                            duplicates[dataset] += 1
                        else:
                            keys[key] = row
                            rows[dataset].append(row)
                    pages[dataset].append({"file": filename, "sha256": identity, "bytes": len(payload), "source_rows": len(parsed)})
                    if len(parsed) < LIMITS["rows_per_page"]:
                        break
                else:
                    raise MarketCaptureError("market page budget exhausted")
            if mode == "production":
                _verify_code(body)
            captured = _now() if now is None else now
            projection = source._canonical({"schema": "tpr-raw-market-projection-v1", "candidate_id": CANDIDATE_ID,
                "capture_id": CAPTURE_ID, "market_plan_sha256": plan.sha256, "mode": mode,
                "capture_utc": captured.isoformat(), "structure_sha256": body["structure_sha256"], "waiver_sha256": body["waiver_sha256"],
                "code_hashes": body["code_hashes"], "prices": rows["stocks"], "actions": rows["actions"],
                "pages": pages, "native_source_rows": raw_counts, "exact_duplicate_rows": duplicates,
                "transactional_snapshot": False, "point_in_time_data": False, "canonical_admission": False})
            if len(projection) > LIMITS["total_bytes"]:
                raise MarketCaptureError("market projection budget exhausted")
            projection_sha256 = source._digest(projection)
            filename = CAPTURE_ID + "." + projection_sha256 + ".projection.json"
            stage = "publication"
            source._publish(directory_fd, filename, projection)
            projection_path, status, stage = private_root / filename, "CAPTURED", "captured"
        except KeyboardInterrupt:
            status, failure, interrupted = "INTERRUPTED", "market_interrupted", True
        except Exception:
            failure = "market_capture_failed"
        report = {"schema": "tpr-raw-market-capture-report-v1", "capture_id": CAPTURE_ID, "candidate_id": CANDIDATE_ID,
            "market_plan_sha256": plan.sha256, "mode": mode, "status": status, "failure": failure,
            "failure_stage": stage if status != "CAPTURED" else None, "last_http_status": last_http_status,
            "native_source_row_counts": raw_counts, "unique_row_counts": {k: len(v) for k, v in rows.items()},
            "exact_duplicate_rows": duplicates, "page_counts": {k: len(v) for k, v in pages.items()},
            "response_bytes": total_bytes, "projection_sha256": projection_sha256,
            "provider_requests": attempts if mode == "production" else 0, "fixture_transport_calls": attempts if mode == "offline-fixture" else 0,
            "development_look_spent": 1 if mode == "production" else 0, "fixture_runs": 1 if mode == "offline-fixture" else 0,
            "backtest_completed": False, "real_backtest_ready": False, "outcome_access_before_reservation": False,
            "rights_verified": False, "transactional_snapshot": False, "canonical_admission": False,
            "quantconnect_attempts": 0, "trading": False}
        payload = source._canonical(report)
        aggregate_name, terminal_name = CAPTURE_ID + "." + source._digest(payload) + ".aggregate.json", CAPTURE_ID + ".terminal.json"
        source._publish(directory_fd, aggregate_name, payload)
        source._publish(directory_fd, terminal_name, source._canonical({"schema": "tpr-raw-market-capture-terminal-v1",
            "capture_id": CAPTURE_ID, "candidate_id": CANDIDATE_ID, "market_plan_sha256": plan.sha256,
            "status": status, "aggregate_sha256": source._digest(payload), "projection_sha256": projection_sha256,
            "development_look_spent": report["development_look_spent"], "fixture_runs": report["fixture_runs"],
            "backtest_completed": False, "quantconnect_attempts": 0, "canonical_admission": False, "trading": False}))
        if interrupted:
            raise KeyboardInterrupt("market acquisition interrupted; look remains spent") from None
        return CaptureResult(payload, source._digest(payload), projection_path, private_root / aggregate_name, private_root / terminal_name)
    finally:
        os.close(directory_fd)


@dataclass(frozen=True)
class SimulationResult:
    payload: bytes
    sha256: str
    report_path: Path | None
    aggregate_path: Path
    terminal_path: Path


def _read_reservation(directory_fd, body, plan):
    descriptor = None
    try:
        descriptor = os.open(CANDIDATE_ID + ".spent.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_nlink != 1 or not 0 < before.st_size <= 65536):
            raise MarketCaptureError("market reservation custody refused")
        parts, remaining = [], before.st_size
        while remaining:
            piece = os.read(descriptor, min(remaining, 65536))
            if not piece:
                raise MarketCaptureError("market reservation changed")
            parts.append(piece)
            remaining -= len(piece)
        after = os.fstat(descriptor)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise MarketCaptureError("market reservation changed")
        observed = raw_run._decode(b"".join(parts), 65536)
        started = source._clock(observed["started_utc"])
        if not source._clock(body["created_utc"]) <= started < source._clock(body["expires_utc"]):
            raise MarketCaptureError("market reservation clock mismatch")
        expected = {"schema": "tpr-raw-market-look-reservation-v1", "candidate_id": CANDIDATE_ID,
            "capture_id": CAPTURE_ID, "market_plan_sha256": plan.sha256, "started_utc": observed["started_utc"],
            "mode": body["mode"], "structure_sha256": body["structure_sha256"], "waiver_sha256": body["waiver_sha256"],
            "code_hashes": body["code_hashes"], "candidate_policy_sha256": body["candidate_policy_sha256"],
            "development_look_reserved": 1 if body["mode"] == "production" else 0,
            "fixture_runs": 1 if body["mode"] == "offline-fixture" else 0}
        if source._canonical(observed) != source._canonical(expected):
            raise MarketCaptureError("market reservation does not bind this plan")
    except (OSError, KeyError, ValueError):
        raise MarketCaptureError("market reservation unavailable or inapplicable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _captured_report(directory_fd, plan, identity):
    source._hash(identity)
    report = raw_run._decode(raw_run._read_file(directory_fd, CAPTURE_ID + "." + identity + ".aggregate.json", 65536, identity), 65536)
    required = {"schema", "capture_id", "candidate_id", "market_plan_sha256", "mode", "status", "failure", "failure_stage",
        "last_http_status", "native_source_row_counts", "unique_row_counts", "exact_duplicate_rows", "page_counts",
        "response_bytes", "projection_sha256", "provider_requests", "fixture_transport_calls", "development_look_spent",
        "fixture_runs", "backtest_completed", "real_backtest_ready", "outcome_access_before_reservation", "rights_verified",
        "transactional_snapshot", "canonical_admission", "quantconnect_attempts", "trading"}
    body = plan.body()
    if (set(report) != required or report["schema"] != "tpr-raw-market-capture-report-v1"
            or report["capture_id"] != CAPTURE_ID or report["candidate_id"] != CANDIDATE_ID
            or report["market_plan_sha256"] != plan.sha256 or report["mode"] != body["mode"]
            or report["status"] != "CAPTURED" or report["failure"] is not None or report["failure_stage"] is not None
            or any(report[key] is not False for key in ("backtest_completed", "real_backtest_ready", "outcome_access_before_reservation",
                "rights_verified", "transactional_snapshot", "canonical_admission", "trading"))
            or type(report["quantconnect_attempts"]) is not int or report["quantconnect_attempts"] != 0
            or type(report["development_look_spent"]) is not int
            or report["development_look_spent"] != (1 if body["mode"] == "production" else 0)
            or type(report["fixture_runs"]) is not int or report["fixture_runs"] != (1 if body["mode"] == "offline-fixture" else 0)):
        raise MarketCaptureError("captured report is not applicable to one reserved look")
    source._hash(report["projection_sha256"])
    return report


def _reserve_simulation(directory_fd, plan, capture_identity, projection_identity, current):
    try:
        descriptor = os.open(CANDIDATE_ID + ".simulation.spent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory_fd)
    except FileExistsError:
        raise MarketCaptureError("candidate simulation already spent") from None
    except OSError:
        raise MarketCaptureError("simulation reservation unavailable") from None
    try:
        source._write_fd(descriptor, source._canonical({"schema": "tpr-raw-simulation-reservation-v1", "candidate_id": CANDIDATE_ID,
            "capture_id": CAPTURE_ID, "market_plan_sha256": plan.sha256, "capture_report_sha256": capture_identity,
            "projection_sha256": projection_identity, "code_hashes": plan.body()["code_hashes"],
            "started_utc": current.isoformat(), "mode": plan.body()["mode"], "additional_development_looks": 0}))
        os.fsync(directory_fd)
    except KeyboardInterrupt:
        raise _ClaimFailure(True) from None
    except OSError:
        raise _ClaimFailure(False) from None
    finally:
        os.close(descriptor)


def _round8(value):
    number = Fraction(value)
    scaled = number * 100000000
    whole, remainder = divmod(scaled.numerator, scaled.denominator)
    if remainder * 2 > scaled.denominator or remainder * 2 == scaled.denominator and whole % 2:
        whole += 1
    text = str(abs(whole)).zfill(9)
    return ("-" if whole < 0 else "") + text[:-8] + "." + text[-8:]


def _result_summary(result):
    backtest = result["backtest"]
    sessions, orders, fills = backtest["sessions"], backtest["orders"], backtest["fills"]
    if (type(sessions) is not list or type(orders) is not list or type(fills) is not list
            or type(backtest["complete"]) is not bool or type(backtest["corporate_action_accounting_complete"]) is not bool):
        raise MarketCaptureError("invalid private backtest result framing")
    dates = [session["session_id"] for session in sessions]
    window_complete = (len(dates) == 60 and dates[0] == "2025-01-02" and dates[-1] == "2025-03-31" and dates == sorted(set(dates)))
    valuation = window_complete and all(session["close_equity"] is not None for session in sessions)
    cash, receivable = backtest["final_cash"], backtest["final_dividend_receivable"]
    final_nav = sessions[-1]["close_equity"] if sessions else None
    returned, drawdown = None, None
    if valuation:
        initial = Fraction(backtest["initial_cash"])
        if initial <= 0:
            raise MarketCaptureError("invalid initial private NAV")
        navs = [Fraction(session["close_equity"]) for session in sessions]
        peak, deepest = initial, Fraction()
        for nav in navs:
            peak = max(peak, nav)
            deepest = max(deepest, (peak - nav) / peak)
        returned, drawdown = _round8((navs[-1] / initial - 1) * 100), _round8(deepest * 100)
    if any(type(order["pending_quantity"]) is not int or order["pending_quantity"] < 0 for order in orders):
        raise MarketCaptureError("invalid private pending quantity")
    return {"valuation_complete": valuation, "frozen_window_complete": window_complete,
        "corporate_action_accounting_complete": backtest["corporate_action_accounting_complete"], "engine_complete": backtest["complete"],
        "study_sessions": len(sessions), "expected_study_sessions": 60, "window_start": "2025-01-02", "window_end": "2025-03-31",
        "orders": len(orders), "fills": len(fills), "pending_order_count": sum(order["pending_quantity"] > 0 for order in orders),
        "pending_quantity": sum(order["pending_quantity"] for order in orders),
        "pending_quantity_scope": "sum-of-day-only-unfilled-quantities-not-live-orders",
        "final_cash": _round8(cash), "final_dividend_receivable": _round8(receivable),
        "final_nav": None if final_nav is None else _round8(final_nav),
        "total_commissions": _round8(backtest["total_commission"]), "total_slippage": _round8(backtest["total_slippage"]),
        "return_pct": returned, "max_drawdown_pct": drawdown, "summary_rounding": "exact-rational-8-decimal-half-even",
        "dividend_cash_policy": "exdate-receivable-never-spendable-no-assumed-payment-date",
        "costs_calibrated": False, "point_in_time_data": False, "canonical_admission": False,
        "market_edge_proven": False, "confirmatory_alpha": "0", "quantconnect_attempts": 0, "trading": False}


def _compute(structure, projection):
    from .raw_market_inputs import convert
    from .raw_candidate import run_accounted_raw_candidate
    return run_accounted_raw_candidate(structure, convert(structure, projection["prices"], projection["actions"]))


def execute_backtest(plan: CapturePlan, capture_report_sha256: str) -> SimulationResult:
    if type(plan) is not CapturePlan or plan.body()["mode"] != "production":
        raise MarketCaptureError("public simulation executor is production-only")
    return _execute_backtest(plan, capture_report_sha256, PRODUCTION_ROOT)


def _execute_fixture_backtest(plan, capture_report_sha256, private_root, *, now=None):
    if type(plan) is not CapturePlan or plan.body()["mode"] != "offline-fixture" or private_root == PRODUCTION_ROOT:
        raise MarketCaptureError("fixture simulation requires a synthetic root and mode")
    return _execute_backtest(plan, capture_report_sha256, private_root, now=now)


def _execute_backtest(plan, capture_report_sha256, private_root, *, now=None):
    body = plan.body()
    current = _before_expiry(body, now)
    if body["mode"] == "production":
        if now is not None or private_root != PRODUCTION_ROOT:
            raise MarketCaptureError("production simulation context cannot change")
        raw_run._verify_lane()
        source._verify_identity({"git_sha": body["git_sha"], "code_sha256": body["transport_parent_sha256"]})
        _verify_code(body)
    directory_fd = raw_run._open_root(private_root, body["mode"])
    try:
        _prepare_source(directory_fd, body)
        _read_reservation(directory_fd, body, plan)
        captured = _captured_report(directory_fd, plan, capture_report_sha256)
        projection_identity = captured["projection_sha256"]
        claim_failure = None
        try:
            _reserve_simulation(directory_fd, plan, capture_report_sha256, projection_identity, current)
        except _ClaimFailure as failure:
            claim_failure = failure
        status, stage, failure, interrupted, report_path, report_sha256, summary = "FAILED", "reservation" if claim_failure else "projection", None, False, None, None, None
        try:
            if claim_failure:
                if claim_failure.interrupted:
                    raise KeyboardInterrupt
                raise claim_failure
            _before_expiry(body, now)
            filename = CAPTURE_ID + "." + projection_identity + ".projection.json"
            projection = raw_run._decode(raw_run._read_file(directory_fd, filename, LIMITS["total_bytes"], projection_identity), LIMITS["total_bytes"])
            required = {"schema", "candidate_id", "capture_id", "market_plan_sha256", "mode", "capture_utc", "structure_sha256",
                "waiver_sha256", "code_hashes", "prices", "actions", "pages", "native_source_rows", "exact_duplicate_rows",
                "transactional_snapshot", "point_in_time_data", "canonical_admission"}
            if (set(projection) != required or projection["schema"] != "tpr-raw-market-projection-v1"
                    or projection["candidate_id"] != CANDIDATE_ID or projection["capture_id"] != CAPTURE_ID
                    or projection["market_plan_sha256"] != plan.sha256 or projection["mode"] != body["mode"]
                    or projection["structure_sha256"] != body["structure_sha256"] or projection["waiver_sha256"] != body["waiver_sha256"]
                    or source._canonical(projection["code_hashes"]) != source._canonical(body["code_hashes"])
                    or any(projection[k] is not False for k in ("transactional_snapshot", "point_in_time_data", "canonical_admission"))
                    or source._clock(projection["capture_utc"]) > current):
                raise MarketCaptureError("projection does not bind the reserved market plan")
            stage = "structure"
            structure = raw_run._decode(raw_run._read_file(directory_fd, "structure.json", raw_run.MAX_INPUT_BYTES, body["structure_sha256"]), raw_run.MAX_INPUT_BYTES)
            stage = "simulation"
            result = _compute(structure, projection)
            if body["mode"] == "production":
                _verify_code(body)
            stage = "summary"
            summary = _result_summary(result)
            payload = source._canonical({"schema": "tpr-raw-private-simulation-result-v1", "candidate_id": CANDIDATE_ID,
                "market_plan_sha256": plan.sha256, "capture_report_sha256": capture_report_sha256,
                "projection_sha256": projection_identity, "code_hashes": body["code_hashes"], "result": result, "summary": summary})
            if len(payload) > LIMITS["total_bytes"]:
                raise MarketCaptureError("private simulation report budget exceeded")
            report_sha256 = source._digest(payload)
            filename = CAPTURE_ID + "." + report_sha256 + ".backtest.json"
            stage = "publication"
            source._publish(directory_fd, filename, payload)
            report_path, status, stage = private_root / filename, "SIMULATED", "simulated"
        except KeyboardInterrupt:
            status, failure, interrupted = "INTERRUPTED", "simulation_interrupted", True
        except Exception:
            failure = "simulation_failed"
        aggregate = {"schema": "tpr-raw-simulation-report-v1", "candidate_id": CANDIDATE_ID,
            "capture_id": CAPTURE_ID, "market_plan_sha256": plan.sha256, "capture_report_sha256": capture_report_sha256,
            "projection_sha256": projection_identity, "private_report_sha256": report_sha256,
            "status": status, "failure": failure, "failure_stage": stage if status != "SIMULATED" else None, "mode": body["mode"],
            "summary": summary, "development_look_spent": 1 if body["mode"] == "production" else 0,
            "additional_development_looks": 0, "simulation_runs": 1,
            "canonical_admission": False, "quantconnect_attempts": 0, "trading": False}
        payload = source._canonical(aggregate)
        identity = source._digest(payload)
        aggregate_name, terminal_name = CAPTURE_ID + "." + identity + ".simulation.aggregate.json", CAPTURE_ID + ".simulation.terminal.json"
        source._publish(directory_fd, aggregate_name, payload)
        source._publish(directory_fd, terminal_name, source._canonical({"schema": "tpr-raw-simulation-terminal-v1",
            "candidate_id": CANDIDATE_ID, "market_plan_sha256": plan.sha256, "status": status,
            "aggregate_sha256": identity, "private_report_sha256": report_sha256,
            "development_look_spent": aggregate["development_look_spent"], "additional_development_looks": 0,
            "simulation_runs": 1, "canonical_admission": False, "quantconnect_attempts": 0, "trading": False}))
        if interrupted:
            raise KeyboardInterrupt("simulation interrupted; simulation remains spent") from None
        return SimulationResult(payload, identity, report_path, private_root / aggregate_name, private_root / terminal_name)
    finally:
        os.close(directory_fd)
