"""Fresh, bounded source-only capture for the owner's raw-revision diagnostic.

No import opens data or credentials. The constant spent ID precedes credential
resolution and cannot be renewed by a different plan hash. Only the nine native
feature fields persist privately; raw bodies, opaque cursors and credentials
never persist. Complete means pagination terminated, not a transactionally
complete historical inventory. The aggregate is not source rights, pristine
PIT or outcome admission. This does not renew D0 or any earlier source audit.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import http.client
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import threading
from urllib.parse import parse_qsl, urlencode, urlsplit

from .source_audit import (AuditResponse, LANE_ROOT, LANE_BRANCH, SourceAuditError,
    _canonical, _clock, _digest, _hash, _production_credential, _publish,
    _source_object, _valid_credential, _verify_execution_identity, _write_fd)

CANDIDATE_ID = "TPR-DEV-RAWREV-v1"
CAPTURE_ID = "TPR-RAWREV-SOURCE-20261007-001"
PRIVATE_ROOT = LANE_ROOT / "artifacts" / "target_price_raw_revision" / CANDIDATE_ID / "source_capture"
AUDITOR_SHA256 = "9f2674a47d0d62bb09e2dd5ba1ce7f37eed3c68dce254e40e0d11d1218f46960"
FIELDS = ("benzinga_id", "benzinga_firm_id", "ticker", "date", "last_updated", "currency",
          "price_target_action", "price_target", "previous_price_target")
QUERY = (("date.gte", "2024-08-01"), ("date.lte", "2025-03-31"), ("limit", "1000"), ("sort", "date.asc"))
HOST, ENDPOINT = "api.massive.com", "/benzinga/v1/ratings"
MAX_PAGES, MAX_ROWS = 100, 100000
MAX_PAGE_BYTES, MAX_TOTAL_BYTES = 4 * 1024 * 1024, 64 * 1024 * 1024
LATEST_CUTOFF = "2025-03-28T22:00:00+00:00"
_FIXED_CREDENTIAL = _production_credential


class SourceCaptureError(ValueError):
    """Sanitized capture refusal; never contains source or credential values."""


@dataclass(frozen=True)
class CapturePlan:
    payload: bytes
    sha256: str

    def body(self):
        try:
            if type(self.payload) is not bytes or len(self.payload) > 16384 or _digest(self.payload) != self.sha256:
                raise SourceCaptureError("invalid capture plan identity")
            body = _source_object(self.payload)
            expected = freeze_capture_plan(code_sha256=body["code_sha256"], git_sha=body["git_sha"],
                owner_instruction_sha256=body["owner_instruction_sha256"], created_utc=body["created_utc"],
                expires_utc=body["expires_utc"], mode=body["mode"])
            if self.payload != expected.payload:
                raise SourceCaptureError("invalid fixed capture policy")
            return body
        except (SourceAuditError, KeyError, TypeError, ValueError):
            raise SourceCaptureError("invalid capture plan") from None


def freeze_capture_plan(*, code_sha256, git_sha, owner_instruction_sha256, created_utc,
                        expires_utc, mode="production"):
    try:
        for value, length in ((code_sha256, 64), (git_sha, 40), (owner_instruction_sha256, 64)):
            _hash(value, length)
        created, expires = _clock(created_utc), _clock(expires_utc)
        if type(mode) is not str or mode not in ("production", "offline-fixture") or not created < expires <= created + timedelta(hours=48):
            raise SourceCaptureError("invalid capture mode or expiry")
        payload = _canonical({"schema": "tpr-raw-source-capture-plan-v1", "capture_id": CAPTURE_ID,
            "candidate_id": CANDIDATE_ID, "mode": mode, "code_sha256": code_sha256,
            "helper_sha256": AUDITOR_SHA256, "git_sha": git_sha, "owner_instruction_sha256": owner_instruction_sha256,
            "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
            "lane_root": str(LANE_ROOT), "lane_branch": LANE_BRANCH, "destination": str(PRIVATE_ROOT),
            "host": HOST, "endpoint": ENDPOINT, "query": dict(QUERY), "fields": list(FIELDS),
            "limits": {"pages": MAX_PAGES, "rows": MAX_ROWS, "total_bytes": MAX_TOTAL_BYTES,
                "page_bytes": MAX_PAGE_BYTES, "request_seconds": 30, "redirects": 0, "retries": 0},
            "latest_cutoff_utc": LATEST_CUTOFF, "rights_verified": False, "point_in_time_data": False,
            "outcome_access": False, "quantconnect": False, "trading": False, "d0_renewed": False})
        return CapturePlan(payload, _digest(payload))
    except SourceAuditError:
        raise SourceCaptureError("invalid capture plan fields") from None


def _verify_identity(body):
    try:
        _verify_execution_identity({"git_sha": body["git_sha"], "code_sha256": AUDITOR_SHA256})
        source = Path(__file__)
        if source.resolve() != LANE_ROOT / "research" / "target_price_revisions_development" / "raw_source_capture.py":
            raise SourceCaptureError("capture code custody mismatch")
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= 262144:
                raise SourceCaptureError("capture code identity mismatch")
            payload = os.read(fd, 262144)
            if len(payload) != metadata.st_size or _digest(payload) != body["code_sha256"]:
                raise SourceCaptureError("capture code identity mismatch")
        finally:
            os.close(fd)
    except (OSError, SourceAuditError):
        raise SourceCaptureError("capture execution identity unavailable") from None


def _private_root(root):
    fd = None
    try:
        if type(root) is not type(LANE_ROOT) or not root.is_absolute() or root.resolve() != root:
            raise SourceCaptureError("invalid private capture root")
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        for part in root.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        metadata = os.fstat(fd)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise SourceCaptureError("capture root requires owner-only custody")
        result, fd = fd, None
        return result
    except OSError:
        raise SourceCaptureError("private capture root unavailable") from None
    finally:
        if fd is not None:
            os.close(fd)


@contextmanager
def _deadline():
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise SourceCaptureError("capture deadline unavailable")
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_args):
        raise SourceCaptureError("capture transport deadline")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 30)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _https_get(query, credential, byte_limit):
    connection = None
    try:
        if type(byte_limit) is not int or not 0 < byte_limit <= MAX_PAGE_BYTES:
            raise SourceCaptureError("capture byte allowance unavailable")
        with _deadline():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname, context.verify_mode, context.keylog_filename = True, ssl.CERT_REQUIRED, None
            context.load_default_certs()
            connection = http.client.HTTPSConnection(HOST, 443, timeout=30, context=context)
            connection.set_debuglevel(0)
            connection.request("GET", ENDPOINT + "?" + urlencode(query), headers={"Authorization": "Bearer " + credential,
                "Accept": "application/json", "Accept-Encoding": "identity", "Connection": "close",
                "User-Agent": "TPR-raw-revision-source-capture/1"})
            response = connection.getresponse()
            headers = tuple((name.lower(), value) for name, value in response.getheaders()
                if name.lower() in ("content-length", "content-type", "content-encoding"))
            if response.status != 200:
                return AuditResponse(response.status, headers, b"")
            recognized = dict(headers)
            length = recognized.get("content-length")
            if (len(recognized) != len(headers) or recognized.get("content-encoding", "identity").lower() != "identity"
                    or recognized.get("content-type", "application/json").split(";", 1)[0].lower().strip() != "application/json"
                    or length is not None and (re.fullmatch(r"[0-9]{1,9}", length) is None or int(length) > byte_limit)):
                raise SourceCaptureError("capture response headers refused")
            payload = response.read(byte_limit)
            if len(payload) == byte_limit and not response.isclosed() or length is not None and len(payload) != int(length):
                raise SourceCaptureError("capture response completeness refused")
            return AuditResponse(response.status, headers, payload)
    except (OSError, http.client.HTTPException):
        raise SourceCaptureError("capture transport refused") from None
    finally:
        if connection is not None:
            connection.close()


_FIXED_TRANSPORT = _https_get


def _next_query(value):
    if type(value) is not str or len(value) > 16384:
        raise SourceCaptureError("invalid opaque capture cursor")
    try:
        url = urlsplit(value)
        pairs = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True)
        query = dict(pairs)
        if (url.scheme != "https" or url.netloc != HOST or url.path != ENDPOINT or url.fragment
                or len(query) != len(pairs) or "cursor" not in query
                or any(key not in dict(QUERY) and key != "cursor" for key in query)
                or any(key != "cursor" and query[key] != dict(QUERY)[key] for key in query)):
            raise SourceCaptureError("capture cursor left fixed scope")
        cursor = query["cursor"]
        if not 0 < len(cursor) <= 8192 or any(not 0x21 <= ord(char) <= 0x7e for char in cursor):
            raise SourceCaptureError("invalid opaque capture cursor")
        return QUERY + (("cursor", cursor),)
    except ValueError:
        raise SourceCaptureError("invalid opaque capture cursor") from None


def _echo(value, credential):
    if type(value) is str:
        return credential in value
    if type(value) is dict:
        return any(_echo(key, credential) or _echo(child, credential) for key, child in value.items())
    if type(value) is list:
        return any(_echo(child, credential) for child in value)
    return False


def _target(value):
    if value is None:
        return None, None, False
    try:
        if type(value) not in (int, Decimal, str) or type(value) is str and len(value) > 96:
            raise ValueError
        number = Decimal(value)
        if not number.is_finite() or len(number.as_tuple().digits) > 64 or not -32 <= number.as_tuple().exponent <= 32:
            raise ValueError
        return format(number, "f"), number, False
    except (ValueError, InvalidOperation):
        return value if type(value) is str and len(value) <= 96 else None, None, True


def _project(row):
    projected = {field: row.get(field) if type(row) is dict else None for field in FIELDS}
    malformed = type(row) is not dict
    for name in FIELDS[:-2]:
        value = projected[name]
        if name in ("benzinga_id", "benzinga_firm_id"):
            valid = type(value) is int and 0 < value < 10**30 or type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:\-]{0,127}", value) is not None
        else:
            valid = type(value) is str and 0 < len(value) <= 256
        if not valid:
            projected[name], malformed = None, True
    try:
        issued = projected["date"]
        if type(issued) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", issued) is None or not "2024-08-01" <= issued <= "2025-03-31":
            raise ValueError
        datetime.strptime(issued, "%Y-%m-%d")
        touched = _clock(projected["last_updated"])
    except (ValueError, SourceAuditError):
        touched, malformed = None, True
    projected["price_target"], new, bad = _target(projected["price_target"])
    malformed |= bad
    projected["previous_price_target"], previous, bad = _target(projected["previous_price_target"])
    malformed |= bad
    positive = new is not None and previous is not None and new > 0 and previous > 0
    cutoff = bool(positive and not malformed and touched is not None and touched <= _clock(LATEST_CUTOFF))
    return projected, malformed, positive, cutoff


@dataclass(frozen=True)
class CaptureResult:
    payload: bytes
    sha256: str
    aggregate_path: Path
    projection_path: Path | None
    terminal_path: Path


def execute_capture(plan, private_root=PRIVATE_ROOT):
    """Production-only; no injected clocks, credentials or transports."""
    if type(plan) is not CapturePlan or plan.body()["mode"] != "production" or private_root != PRIVATE_ROOT:
        raise SourceCaptureError("production capture requires exact plan and fixed root")
    _verify_identity(plan.body())
    return _execute(plan, private_root, datetime.now(timezone.utc), _production_credential, _https_get,
        lambda: datetime.now(timezone.utc))


def _execute_fixture_capture(plan, private_root, *, now, credential_resolver, transport):
    if (type(plan) is not CapturePlan or plan.body()["mode"] != "offline-fixture" or private_root == PRIVATE_ROOT
            or credential_resolver in (_FIXED_CREDENTIAL, _production_credential)
            or transport in (_FIXED_TRANSPORT, _https_get)):
        raise SourceCaptureError("fixture capture requires synthetic adapters and custody")
    return _execute(plan, private_root, now, credential_resolver, transport, lambda: now)


def _execute(plan, private_root, current, resolver, fetch, clock):
    body = plan.body()
    if type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0) or not _clock(body["created_utc"]) <= current < _clock(body["expires_utc"]):
        raise SourceCaptureError("capture clock outside frozen permit")
    fd = _private_root(private_root)
    try:
        try:
            claim = os.open(CAPTURE_ID + ".spent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise SourceCaptureError("fresh capture already spent") from None
        except OSError:
            raise SourceCaptureError("capture claim unavailable") from None
        rows, dispositions, pages, total_bytes, malformed, positive, cutoff = [], [], 0, 0, 0, 0, 0
        complete, interrupted, failure, projection_path = False, False, None, None
        try:
            try:
                _write_fd(claim, _canonical({"capture_id": CAPTURE_ID, "plan_sha256": plan.sha256,
                    "started_utc": current.isoformat(), "mode": body["mode"]}))
                os.fsync(fd)
            finally:
                os.close(claim)
            _publish(fd, CAPTURE_ID + ".plan.json", plan.payload)
            credential = resolver("massive")
            if not _valid_credential(credential) or body["mode"] == "offline-fixture" and not credential.startswith("SYNTHETIC_"):
                raise SourceCaptureError("capture credential unavailable")
            query, seen, event_ids = QUERY, set(), set()
            while True:
                if pages >= MAX_PAGES or total_bytes >= MAX_TOTAL_BYTES or clock() >= _clock(body["expires_utc"]):
                    raise SourceCaptureError("capture page budget exhausted")
                allowance = min(MAX_PAGE_BYTES, MAX_TOTAL_BYTES - total_bytes)
                pages += 1
                response = fetch(query, credential, allowance)
                if type(response) is not AuditResponse or type(response.status) is not int or response.status != 200 or type(response.body) is not bytes or response.refusal is not None:
                    raise SourceCaptureError("capture response refused")
                total_bytes += len(response.body)
                if not 0 < len(response.body) <= allowance or total_bytes > MAX_TOTAL_BYTES or credential.encode() in response.body:
                    raise SourceCaptureError("capture byte or privacy limit refused")
                source = _source_object(response.body)
                if _echo(source, credential) or source.get("status") != "OK" or type(source.get("results")) is not list or len(source["results"]) > 1000:
                    raise SourceCaptureError("capture source schema or privacy refused")
                if len(rows) + len(source["results"]) > MAX_ROWS:
                    raise SourceCaptureError("capture row budget exhausted")
                for row in source["results"]:
                    projected, bad, pair, eligible = _project(row)
                    event_id = projected["benzinga_id"]
                    if event_id is not None:
                        if str(event_id) in event_ids:
                            raise SourceCaptureError("capture native event overlap")
                        event_ids.add(str(event_id))
                    rows.append(projected)
                    dispositions.append("malformed_native_fields" if bad else "positive_raw_pair" if pair else "nonpositive_or_missing_raw_pair")
                    malformed += int(bad); positive += int(pair); cutoff += int(eligible)
                next_url = source.get("next_url")
                if next_url is None:
                    complete = True
                    break
                query = _next_query(next_url)
                cursor = dict(query)["cursor"]
                if cursor in seen or credential in cursor:
                    raise SourceCaptureError("capture cursor replay")
                seen.add(cursor)
            projection_name = CAPTURE_ID + ".projection.json"
            projection = _canonical({"schema": "tpr-raw-source-projection-v1", "candidate_id": CANDIDATE_ID,
                "capture_id": CAPTURE_ID, "capture_utc": clock().isoformat(), "started_utc": current.isoformat(),
                "plan_sha256": plan.sha256, "ratings": rows, "dispositions": dispositions,
                "complete": True, "transactional_inventory": False, "point_in_time_data": False})
            if len(projection) > MAX_TOTAL_BYTES:
                raise SourceCaptureError("capture projection byte limit")
            _publish(fd, projection_name, projection)
            projection_path = private_root / projection_name
        except KeyboardInterrupt:
            interrupted, failure, complete = True, "capture_interrupted", False
        except Exception:
            failure, complete = "capture_refused", False
        aggregate = {"schema": "tpr-raw-source-feasibility-v1", "candidate_id": CANDIDATE_ID, "capture_id": CAPTURE_ID,
            "plan_sha256": plan.sha256, "complete": complete, "pages": pages, "rows": len(rows),
            "response_bytes": total_bytes, "malformed": malformed, "positive_raw_pairs": positive,
            "positive_pairs_touch_by_latest_cutoff": cutoff, "latest_cutoff_utc": LATEST_CUTOFF,
            "source_blocker": not complete or cutoff == 0, "failure": failure,
            "transactional_inventory": False, "rights_verified": False, "point_in_time_data": False, "outcome_access": False,
            "quantconnect_attempts": 0, "trading": False, "d0_renewed": False}
        payload = _canonical(aggregate)
        aggregate_name, terminal_name = CAPTURE_ID + ".aggregate.json", CAPTURE_ID + ".terminal.json"
        _publish(fd, aggregate_name, payload)
        _publish(fd, terminal_name, _canonical({"schema": "tpr-raw-source-terminal-v1", "capture_id": CAPTURE_ID,
            "plan_sha256": plan.sha256, "status": "INTERRUPTED" if interrupted else "COMPLETED" if complete else "FAILED",
            "failure": failure, "aggregate_sha256": _digest(payload), "scope_spent": True,
            "outcome_looks": 0, "quantconnect_attempts": 0}))
        if interrupted:
            raise KeyboardInterrupt("capture interrupted; fresh scope remains spent") from None
        return CaptureResult(payload, _digest(payload), private_root / aggregate_name, projection_path, private_root / terminal_name)
    except SourceAuditError:
        raise SourceCaptureError("capture publication refused; fresh scope remains spent") from None
    finally:
        os.close(fd)
