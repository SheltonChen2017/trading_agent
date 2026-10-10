"""One-shot, outcome-free source-access probe; stores closed aggregates only.

Importing this module does nothing. Production execution has exactly two
predeclared HTTPS operations and a spent claim before credential resolution.
Successful access is not contractual entitlement or point-in-time evidence.
The separately bound offline-fixture mode never resolves real credentials.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import pwd
import re
import signal
import ssl
import stat
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode


class SourceAuditError(ValueError):
    """A fixed source-audit refusal, never containing provider/secret details."""


AUDIT_ID = "TPR-SOURCE-AUDIT-20261006-001"
LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions")
LANE_BRANCH = "codex/strategy-target-price-revisions"
PRIVATE_ROOT = LANE_ROOT / "artifacts" / "target_price_source_audit"
MODES = ("production", "offline-fixture")
LIMITS = {
    "requests": 2, "response_bytes": 65536, "aggregate_response_bytes": 131072,
    "request_timeout_seconds": 10, "max_elapsed_seconds": 30,
    "redirects": 0, "retries": 0, "pages_followed": 0, "max_massive_rows": 1,
    "max_report_bytes": 32768,
}
FIELD_PRESENCE = (
    "price_target", "previous_price_target", "adjusted_price_target", "previous_adjusted_price_target",
    "currency", "date", "time", "last_updated", "benzinga_id", "firm_id", "analyst_id",
    "price_target_horizon", "previous_price_target_horizon", "published_at", "public_available_at",
    "version_available_at", "adjustment_vintage", "previous_adjustment_vintage",
)
AUTHORITY = {
    "canonical_admission": False, "point_in_time_data": False, "retained_capture_access": False,
    "auxiliary_joins": False, "outcomes": False, "quantconnect": False, "broker": False,
    "operator_database": False, "paper_live_deployment": False, "capital_orders_trading": False,
}


@dataclass(frozen=True)
class AuditRequest:
    provider: str
    host: str
    path: str
    query: tuple[tuple[str, str], ...]
    credential: str
    authorization: str

    def body(self) -> dict:
        return {"provider": self.provider, "method": "GET", "host": self.host, "port": 443,
                "path": self.path, "query": dict(self.query), "credential": self.credential,
                "authorization": self.authorization}


REQUESTS = (
    AuditRequest("massive", "api.massive.com", "/benzinga/v1/ratings",
                 (("date", "2025-01-02"), ("limit", "1"), ("sort", "date.asc")),
                 "env:MASSIVE_API_KEY", "Bearer"),
    AuditRequest("sharadar", "api.sharadar.com", "/v1.0/data/tickers", (("status", "True"),),
                 "env:SHARADAR_API_KEY-or-macos-keychain:SHARADAR_API_KEY-current-user", "query:api_key"),
)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(body: dict) -> bytes:
    return (json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                       allow_nan=False) + "\n").encode("ascii")


def _hash(value: object, length: int) -> str:
    if type(value) is not str or re.fullmatch("[0-9a-f]{" + str(length) + "}", value) is None:
        raise SourceAuditError("invalid audit identity")
    return value


def _clock(value: object) -> datetime:
    if type(value) is not str or len(value) > 64:
        raise SourceAuditError("invalid audit UTC clock")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise SourceAuditError("invalid audit UTC clock")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise SourceAuditError("invalid audit UTC clock") from None


def _unique(pairs: list) -> dict:
    body = {}
    for key, value in pairs:
        if key in body:
            raise SourceAuditError("duplicate source JSON key")
        body[key] = value
    return body


def _no_constant(_value: str) -> None:
    raise SourceAuditError("invalid source JSON constant")


@dataclass(frozen=True)
class AuditPlan:
    payload: bytes
    sha256: str

    def body(self) -> dict:
        return _check_plan(self)


def freeze_audit_plan(*, code_sha256: str, git_sha: str, owner_instruction_sha256: str,
                      created_utc: str, expires_utc: str, mode: str = "production") -> AuditPlan:
    """Freeze exact operations and budgets; this is scope, not vendor rights."""
    _hash(code_sha256, 64)
    _hash(git_sha, 40)
    _hash(owner_instruction_sha256, 64)
    if type(mode) is not str or mode not in MODES:
        raise SourceAuditError("invalid audit mode")
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not created < expires <= created + timedelta(hours=48):
        raise SourceAuditError("invalid audit expiry duration")
    body = {
        "schema": "tpr-outcome-free-source-audit-plan-v1", "audit_id": AUDIT_ID, "mode": mode,
        "code_sha256": code_sha256, "git_sha": git_sha,
        "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "lane_root": str(LANE_ROOT), "lane_branch": LANE_BRANCH,
        "private_destination": "artifacts/target_price_source_audit",
        "requests": [r.body() for r in REQUESTS], "limits": dict(LIMITS),
        "authority": dict(AUTHORITY), "field_presence": list(FIELD_PRESENCE),
        "working_assumption": "owner-authorized-outcome-free-access-not-vendor-attestation",
        "raw_retention": False, "d0_renewed": False,
        "license_entitlement": "unestablished", "point_in_time_facts": "unestablished",
    }
    payload = _canonical(body)
    return AuditPlan(payload, _digest(payload))


def _check_plan(plan: AuditPlan) -> dict:
    if type(plan) is not AuditPlan or type(plan.payload) is not bytes or len(plan.payload) > 16384:
        raise SourceAuditError("invalid audit plan frame")
    _hash(plan.sha256, 64)
    if _digest(plan.payload) != plan.sha256:
        raise SourceAuditError("audit plan digest mismatch")
    try:
        body = json.loads(plan.payload.decode("ascii"), object_pairs_hook=_unique, parse_constant=_no_constant,
                          parse_float=_no_constant)
        if type(body) is not dict:
            raise SourceAuditError("invalid audit plan body")
        expected = freeze_audit_plan(code_sha256=body["code_sha256"], git_sha=body["git_sha"],
                                    owner_instruction_sha256=body["owner_instruction_sha256"],
                                    created_utc=body["created_utc"], expires_utc=body["expires_utc"],
                                    mode=body["mode"])
        # Byte-exact comparison refuses unknown keys and bool/int aliases too.
        if expected.payload != plan.payload:
            raise SourceAuditError("audit plan differs from the fixed approved policy")
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise SourceAuditError("invalid audit plan policy") from None
    return body


@dataclass(frozen=True)
class AuditResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    refusal: str | None = None
    consumed_bytes: int | None = None


@dataclass(frozen=True)
class SourceAuditResult:
    payload: bytes
    sha256: str
    aggregate_path: Path
    terminal_path: Path


def _valid_credential(value: object) -> bool:
    # Prevent header injection and ambiguous echo encodings. Actual keys never
    # enter a serialized object or a diagnostic, including credential hashes.
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9._~\-]{8,256}", value) is not None


def _production_credential(provider: str) -> str | None:
    variable = "MASSIVE_API_KEY" if provider == "massive" else "SHARADAR_API_KEY"
    value = os.environ.get(variable)
    if value is None and provider == "sharadar":
        try:
            account = pwd.getpwuid(os.getuid()).pw_name
            response = subprocess.run(["/usr/bin/security", "find-generic-password", "-a", account,
                                       "-s", "SHARADAR_API_KEY", "-w"],
                                      capture_output=True, timeout=5, check=False)
            if response.returncode == 0 and len(response.stdout) <= 257:
                value = response.stdout.decode("ascii").rstrip("\n")
        except (OSError, UnicodeError, subprocess.SubprocessError):
            return None
    return value if _valid_credential(value) else None


def _verify_execution_identity(body: dict) -> None:
    """Bind actual source and this physical lane before consuming permission."""
    try:
        if Path.cwd() != LANE_ROOT or Path.cwd().resolve() != LANE_ROOT:
            raise SourceAuditError("source audit requires the designated physical lane")
        checks = ("--show-toplevel", "--abbrev-ref", "HEAD")
        commands = (["git", "rev-parse", checks[0]], ["git", "rev-parse", checks[1], "HEAD"],
                    ["git", "rev-parse", checks[2]])
        observed = [subprocess.run(cmd, cwd=LANE_ROOT, capture_output=True, check=True,
                                   timeout=5).stdout.decode("ascii").strip() for cmd in commands]
        if observed != [str(LANE_ROOT), LANE_BRANCH, body["git_sha"]]:
            raise SourceAuditError("source audit lane identity mismatch")
        source = Path(__file__)
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 262144:
                raise SourceAuditError("source audit code identity mismatch")
            payload = os.read(descriptor, 262144)
            if len(payload) != metadata.st_size or _digest(payload) != body["code_sha256"]:
                raise SourceAuditError("source audit code identity mismatch")
        finally:
            os.close(descriptor)
    except SourceAuditError:
        raise
    except (OSError, UnicodeError, subprocess.SubprocessError):
        raise SourceAuditError("source audit execution identity unavailable") from None


def _private_directory(root: Path, mode: str) -> int:
    descriptor = None
    try:
        if type(root) is not type(LANE_ROOT) or not root.is_absolute():
            raise SourceAuditError("invalid private audit directory")
        if mode == "production" and root != PRIVATE_ROOT:
            raise SourceAuditError("production requires the fixed lane audit root")
        # Do not resolve through a symlink to make an unsafe spelling acceptable.
        if root.resolve() != root or any(p.is_symlink() for p in (root, *root.parents)):
            raise SourceAuditError("invalid private audit directory")
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700):
            raise SourceAuditError("invalid private audit directory")
        owned = descriptor
        descriptor = None
        return owned
    except SourceAuditError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise SourceAuditError("private audit directory unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _write_fd(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("incomplete immutable write")
        remaining = remaining[written:]
    os.fsync(descriptor)


def _claim(directory_fd: int, plan: AuditPlan, started: datetime, mode: str) -> None:
    # Constant audit ID, not a plan hash: changed code/policy cannot renew it.
    payload = _canonical({"schema": "tpr-source-audit-spent-claim-v1", "audit_id": AUDIT_ID,
                          "plan_sha256": plan.sha256, "started_utc": started.isoformat(), "mode": mode})
    try:
        descriptor = os.open(AUDIT_ID + ".spent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory_fd)
    except FileExistsError:
        raise SourceAuditError("source audit already spent") from None
    except OSError:
        raise SourceAuditError("source audit claim unavailable") from None
    try:
        _write_fd(descriptor, payload)
        os.fsync(directory_fd)
    except OSError:
        raise SourceAuditError("source audit claim failed; one-shot scope remains spent") from None
    finally:
        os.close(descriptor)


def _publish(directory_fd: int, name: str, payload: bytes) -> None:
    temporary = ".pending-" + uuid.uuid4().hex
    descriptor = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory_fd)
        _write_fd(descriptor, payload)
        os.close(descriptor)
        descriptor = None
        # Hard-link publication is atomic and never replaces an existing path.
        os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
    except OSError:
        raise SourceAuditError("source audit publication failed; one-shot scope remains spent") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        except OSError:
            # No secret or raw data ever goes to the temporary aggregate.
            pass


class _RequestDeadline(Exception):
    pass


@contextmanager
def _request_deadline():
    """A POSIX main-thread timer caps the whole request, not each socket read."""
    if (threading.current_thread() is not threading.main_thread()
            or not hasattr(signal, "setitimer") or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0)):
        raise SourceAuditError("source audit request deadline unavailable")
    previous = signal.getsignal(signal.SIGALRM)
    def expired(_signal, _frame):
        raise _RequestDeadline()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, LIMITS["request_timeout_seconds"])
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _response_header_refusal(status: int, headers: tuple) -> str | None:
    if 300 <= status <= 399:
        return "redirect_refused"
    recognized = {}
    for name, value in headers:
        if name in recognized:
            return "body_schema_refused"
        recognized[name] = value
    encoding = recognized.get("content-encoding", "").strip().lower()
    if encoding not in ("", "identity"):
        return "encoding_refused"
    media = recognized.get("content-type", "").split(";", 1)[0].strip().lower()
    if media not in ("", "application/json"):
        return "content_type_refused"
    length = recognized.get("content-length")
    if length is not None:
        if re.fullmatch(r"[0-9]{1,9}", length) is None:
            return "body_schema_refused"
        if int(length) > LIMITS["response_bytes"]:
            return "response_byte_limit_refused"
    return None


def _https_get(request: AuditRequest, credential: str) -> AuditResponse:
    """Private fixed-host transport; no redirect, proxy, retry or page following."""
    if (type(request) is not AuditRequest
            or any(type(value) is not str for value in
                   (request.provider, request.host, request.path, request.credential, request.authorization))
            or type(request.query) is not tuple
            or any(type(pair) is not tuple or len(pair) != 2 or any(type(v) is not str for v in pair)
                   for pair in request.query)
            or request not in REQUESTS or not _valid_credential(credential)):
        raise SourceAuditError("invalid fixed source request")
    connection = None
    try:
        with _request_deadline():
            # The convenience factory honors SSLKEYLOGFILE. An explicit context
            # never enables environmental keylogging or persists TLS secrets.
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            context.keylog_filename = None
            context.load_default_certs()
            connection = http.client.HTTPSConnection(request.host, 443, timeout=10, context=context)
            connection.set_debuglevel(0)
            query = list(request.query)
            headers = {"Accept": "application/json", "Accept-Encoding": "identity", "Connection": "close",
                       "User-Agent": "TPR-outcome-free-source-audit/1"}
            if request.provider == "massive":
                headers["Authorization"] = "Bearer " + credential
            else:
                query.append(("api_key", credential))
            connection.request("GET", request.path + "?" + urlencode(query), headers=headers)
            response = connection.getresponse()
            if type(response.status) is not int or not 100 <= response.status <= 599:
                raise SourceAuditError("source audit transport failed")
            selected = tuple((name.lower(), value) for name, value in response.getheaders()
                             if name.lower() in ("content-type", "content-encoding", "content-length"))
            refusal = _response_header_refusal(response.status, selected)
            if refusal:
                return AuditResponse(response.status, selected, b"", refusal)
            payload = response.read(LIMITS["response_bytes"])
            # Never read even a sentinel byte beyond the selected response cap.
            # At an unclosed full boundary completeness is unproven: refuse.
            if len(payload) == LIMITS["response_bytes"] and not response.isclosed():
                return AuditResponse(response.status, selected, payload, "response_byte_limit_refused", len(payload))
            declared = dict(selected).get("content-length")
            if declared is not None and len(payload) != int(declared):
                return AuditResponse(response.status, selected, payload, "body_schema_refused", len(payload))
            return AuditResponse(response.status, selected, payload)
    except (OSError, http.client.HTTPException, _RequestDeadline):
        raise SourceAuditError("source audit transport failed") from None
    finally:
        if connection is not None:
            connection.close()


def _source_object(payload: bytes) -> dict:
    try:
        body = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique,
                          parse_float=Decimal, parse_constant=_no_constant)
        if type(body) is not dict:
            raise SourceAuditError("invalid source body")
        # Bounded bytes and depth keep unsolicited complex bodies from becoming
        # an unbounded parsing/semantic operation. Unknown fields are not output.
        def check(item: object, depth: int = 0) -> None:
            if depth > 24:
                raise SourceAuditError("invalid source body")
            if type(item) is dict:
                for child in item.values():
                    check(child, depth + 1)
            elif type(item) is list:
                for child in item:
                    check(child, depth + 1)
            elif type(item) not in (str, int, bool, type(None), Decimal):
                raise SourceAuditError("invalid source body")
        check(body)
        return body
    except (SourceAuditError, UnicodeError, ValueError, RecursionError, OverflowError, InvalidOperation):
        raise SourceAuditError("invalid source body") from None


def _empty_provider(provider: str, disposition: str = "not_attempted") -> dict:
    body = {"provider": provider, "http_status": None, "disposition": disposition,
            "authenticated_access_observed": False, "response_bytes": 0,
            "response_bytes_complete": True, "response_sha256": None}
    if provider == "massive":
        body.update(rows_observed=0, field_presence=dict.fromkeys(FIELD_PRESENCE, 0))
    else:
        body["metadata"] = {"metadata_shape_observed": False, "size_bytes": None, "snapshot_utc": None}
    return body


def _reduce_response(request: AuditRequest, response: AuditResponse, credentials: tuple[str, ...],
                     *, actual: bool) -> dict:
    result = _empty_provider(request.provider)
    if (type(response) is not AuditResponse or type(response.status) is not int
            or not 100 <= response.status <= 599 or type(response.body) is not bytes
            or type(response.headers) is not tuple
            or any(type(pair) is not tuple or len(pair) != 2
                   or any(type(v) is not str for v in pair) for pair in response.headers)):
        result["disposition"] = "body_schema_refused"
        return result
    result["http_status"] = response.status
    if len(response.body) > LIMITS["response_bytes"]:
        result["disposition"] = "response_byte_limit_refused"
        result["response_bytes_complete"] = False
        return result
    consumed = len(response.body) if response.consumed_bytes is None else response.consumed_bytes
    if type(consumed) is not int or not len(response.body) <= consumed <= LIMITS["response_bytes"]:
        result["disposition"] = "body_schema_refused"
        return result
    result["response_bytes"] = consumed
    # This check MUST precede every raw-payload digest, including error bodies.
    if any(key.encode("ascii") in response.body for key in credentials):
        result["disposition"] = "credential_echo_refused"
        return result
    recognized = tuple((name.lower(), value) for name, value in response.headers
                       if name.lower() in ("content-type", "content-encoding", "content-length"))
    refusal = _response_header_refusal(response.status, recognized)
    if response.refusal is not None:
        if type(response.refusal) is not str or response.refusal not in {
                "redirect_refused", "encoding_refused", "content_type_refused",
                "response_byte_limit_refused", "body_schema_refused"}:
            result["disposition"] = "body_schema_refused"
            return result
        refusal = response.refusal
    if refusal:
        result["disposition"] = refusal
        return result
    try:
        body = _source_object(response.body)
    except SourceAuditError:
        # Unparseable bytes might contain an escaped/partial credential; no raw
        # content identity is admitted for such a body, including HTTP errors.
        result["disposition"] = "http_access_refused" if response.status != 200 else "body_schema_refused"
        return result
    def echoed(item: object) -> bool:
        if type(item) is str:
            return any(key in item for key in credentials)
        if type(item) is dict:
            return any(echoed(key) or echoed(value) for key, value in item.items())
        if type(item) is list:
            return any(echoed(value) for value in item)
        return False
    if echoed(body):
        result["disposition"] = "credential_echo_refused"
        return result
    result["response_sha256"] = _digest(response.body)
    if response.status != 200:
        result["disposition"] = "http_access_refused"
        return result
    try:
        if request.provider == "massive":
            if set(body) - {"results", "status", "request_id", "next_url", "count"}:
                raise SourceAuditError("invalid source body")
            if type(body.get("status")) is not str or body["status"] != "OK":
                result["disposition"] = "api_access_refused"
                return result
            rows = body.get("results")
            if type(rows) is not list or any(type(row) is not dict for row in rows):
                raise SourceAuditError("invalid source body")
            if len(rows) > LIMITS["max_massive_rows"]:
                result["disposition"] = "row_limit_refused"
                return result
            if "count" in body and (type(body["count"]) is not int or body["count"] != len(rows)):
                raise SourceAuditError("invalid source body")
            result["rows_observed"] = len(rows)
            result["field_presence"] = {key: sum(key in row for row in rows) for key in FIELD_PRESENCE}
            result["disposition"] = "field_presence_observed" if rows else "empty_sample"
            result["authenticated_access_observed"] = bool(actual and rows)
        else:
            metadata = _sharadar_metadata(body)
            result["metadata"] = metadata
            result["disposition"] = "metadata_observed"
            result["authenticated_access_observed"] = actual
    except SourceAuditError:
        result["disposition"] = "body_schema_refused"
    return result


def _sharadar_metadata(body: dict) -> dict:
    """Status metadata only; no advertised download URL is ever followed."""
    if (set(body) != {"table", "name", "size", "sizeLabel", "modified"}
            or type(body["table"]) is not str or body["table"] != "tickers"
            or type(body["name"]) is not str or not 1 <= len(body["name"]) <= 256
            or type(body["sizeLabel"]) is not str or not 1 <= len(body["sizeLabel"]) <= 128):
        raise SourceAuditError("invalid source body")
    size = body["size"]
    if type(size) is not int or not 0 <= size <= 10**15:
        raise SourceAuditError("invalid source body")
    snapshot = _clock(body["modified"]).isoformat()
    return {"metadata_shape_observed": True, "size_bytes": size, "snapshot_utc": snapshot}


def execute_source_audit(plan: AuditPlan, private_root: Path, *, now: datetime | None = None,
                         credential_resolver: Callable | None = None,
                         transport: Callable | None = None,
                         monotonic: Callable | None = None) -> SourceAuditResult:
    """Spend one exact audit and return/persist ONLY sanitized aggregate bytes.

    Injections, custom clocks and arbitrary private directories require the
    plan's explicit offline-fixture mode; that mode never claims real access.
    A failed, interrupted or partially attempted audit remains spent forever.
    """
    body = _check_plan(plan)
    mode = body["mode"]
    if type(private_root) is not type(LANE_ROOT):
        raise SourceAuditError("invalid private audit directory")
    if mode == "production":
        if credential_resolver is not None or transport is not None or monotonic is not None:
            raise SourceAuditError("source audit injections require offline fixture mode")
        if private_root != PRIVATE_ROOT:
            raise SourceAuditError("production requires the fixed lane audit root")
        if now is not None:
            raise SourceAuditError("source audit clock injection requires offline fixture mode")
        _verify_execution_identity(body)
    else:
        if private_root == PRIVATE_ROOT:
            raise SourceAuditError("offline fixture directory cannot consume the production audit")
        if (credential_resolver is None or transport is None
                or credential_resolver is _production_credential or transport is _https_get):
            raise SourceAuditError("offline fixture mode requires synthetic fixtures, not production adapters")
    current = datetime.now(timezone.utc) if now is None else now
    if type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise SourceAuditError("invalid audit UTC clock")
    current = current.astimezone(timezone.utc)
    if not _clock(body["created_utc"]) <= current < _clock(body["expires_utc"]):
        raise SourceAuditError("audit plan is not currently valid")
    clock = time.monotonic if monotonic is None else monotonic
    directory_fd = _private_directory(private_root, mode)
    try:
        _claim(directory_fd, plan, current, mode)
        started = clock()
        resolver = _production_credential if mode == "production" else credential_resolver
        fetch = _https_get if mode == "production" else transport
        credentials: dict[str, str | None] = {}
        providers = [_empty_provider(request.provider) for request in REQUESTS]
        attempts, status, interrupted, active_index = 0, "COMPLETED", False, None
        try:
            # Resolve both tokens first so either token echoed by either source
            # is detected before a response-content hash is admitted.
            for request in REQUESTS:
                value = resolver(request.provider)
                valid = _valid_credential(value) and (mode == "production" or value.startswith("SYNTHETIC_"))
                credentials[request.provider] = value if valid else None
            secrets = tuple(value for value in credentials.values() if value is not None)
            response_bytes = 0
            for index, request in enumerate(REQUESTS):
                if clock() - started >= LIMITS["max_elapsed_seconds"]:
                    providers[index]["disposition"] = "elapsed_budget_refused"
                    status = "FAILED"
                    break
                credential = credentials[request.provider]
                if credential is None:
                    providers[index]["disposition"] = "credential_unavailable"
                    continue
                attempts += 1
                active_index = index
                try:
                    response = fetch(request, credential)
                except Exception:
                    # Unexpected exceptions are explicit failure, not a plausible
                    # access result. Do not let a URL/key in exception text escape.
                    providers[index]["disposition"] = "transport_failed"
                    providers[index]["response_bytes_complete"] = False
                    status = "FAILED"
                    for later in providers[index + 1:]:
                        later["disposition"] = "not_attempted_after_failure"
                    break
                providers[index] = _reduce_response(request, response, secrets, actual=mode == "production")
                active_index = None
                response_bytes += providers[index]["response_bytes"]
                if response_bytes > LIMITS["aggregate_response_bytes"]:
                    raise SourceAuditError("source audit aggregate byte budget refused")
                if clock() - started >= LIMITS["max_elapsed_seconds"]:
                    status = "FAILED"
                    for later in providers[index + 1:]:
                        later["disposition"] = "elapsed_budget_refused"
                    break
        except KeyboardInterrupt:
            interrupted, status = True, "INTERRUPTED"
            if active_index is not None:
                providers[active_index]["disposition"] = "transport_interrupted"
                providers[active_index]["response_bytes_complete"] = False
            for provider in providers:
                if provider["disposition"] == "not_attempted":
                    provider["disposition"] = "not_attempted_after_interruption"
        except Exception:
            status = "FAILED"
            for provider in providers:
                if provider["disposition"] == "not_attempted":
                    provider["disposition"] = "not_attempted_after_failure"
        report = {
            "schema": "tpr-outcome-free-source-audit-report-v1", "audit_id": AUDIT_ID, "mode": mode,
            "status": status, "started_utc": current.isoformat(), "plan_sha256": plan.sha256,
            "code_sha256": body["code_sha256"], "git_sha": body["git_sha"],
            "owner_instruction_sha256": body["owner_instruction_sha256"], "providers": providers,
            "provider_requests": attempts if mode == "production" else 0,
            "fixture_transport_calls": attempts if mode == "offline-fixture" else 0,
            "response_bytes": sum(item["response_bytes"] for item in providers),
            "response_bytes_complete": all(item["response_bytes_complete"] for item in providers),
            "authority": dict(AUTHORITY), "license_entitlement": "unestablished",
            "point_in_time_facts": "unestablished",
            "working_assumption": body["working_assumption"], "real_development_backtest_ready": False,
            "canonical_admission": False, "d0_renewed": False, "outcome_reads": 0,
            "qc_attempts": 0, "development_looks": 0,
        }
        payload = _canonical(report)
        if len(payload) > LIMITS["max_report_bytes"]:
            raise SourceAuditError("source audit aggregate report exceeds budget")
        identity = _digest(payload)
        aggregate_name = AUDIT_ID + "." + identity + ".aggregate.json"
        terminal_name = AUDIT_ID + ".terminal.json"
        _publish(directory_fd, aggregate_name, payload)
        _publish(directory_fd, terminal_name, _canonical({
            "schema": "tpr-source-audit-terminal-v1", "audit_id": AUDIT_ID,
            "plan_sha256": plan.sha256, "aggregate_sha256": identity, "status": status, "mode": mode}))
        if interrupted:
            raise KeyboardInterrupt("source audit interrupted; one-shot scope remains spent") from None
        return SourceAuditResult(payload, identity, private_root / aggregate_name, private_root / terminal_name)
    finally:
        os.close(directory_fd)
