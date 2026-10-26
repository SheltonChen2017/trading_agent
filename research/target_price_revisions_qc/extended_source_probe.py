"""One-shot, outcome-free availability samples for the frozen extended study.

Seven fixed GETs are samples, not complete history, entitlement or PIT proof.
Import opens neither credentials nor files. Production permits no adapters;
its source custody and all seven spent claims precede credential resolution.
No raw response, provider identifier or target value is published or retained.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import http.client
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import subprocess
import threading
from urllib.parse import urlencode

from research.target_price_revisions_development import source_audit as helper

LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions")
LANE_BRANCH = "codex/strategy-target-price-revisions"
STUDY_ID = "TPR-CAP-TILT-EXT26-20261010-v1"
OPERATION_ID = "TPR-EXT26-SOURCE-PROBE-20261010-001"
PRIVATE_ROOT = LANE_ROOT / "artifacts" / "target_price_extended" / STUDY_ID / "source_probe"
SOURCE_RELATIVE = "research/target_price_revisions_qc/extended_source_probe.py"
FREEZE_RELATIVE = "research/target_price_revisions_qc/extended_study_freeze.json"
FREEZE_SHA256 = "90bdec5520b29bd932a3ec730f7c4c40c544ea7582731ad6680ef34ea8cf4067"
HELPER_PATHS = ("research/__init__.py", "research/target_price_revisions_qc/__init__.py",
                "research/target_price_revisions_development/__init__.py",
                "research/target_price_revisions_development/source_audit.py")
WINDOWS = (("2020-09-01", "2020-12-31"), ("2021-01-01", "2021-12-31"),
           ("2022-01-01", "2022-12-31"), ("2023-01-01", "2023-12-31"),
           ("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31"),
           ("2026-01-01", "2026-10-09"))
QUERIES = tuple((("date.gte", start), ("date.lte", end), ("limit", "1"),
                 ("sort", "date.asc")) for start, end in WINDOWS)
HOST, ENDPOINT = "api.massive.com", "/benzinga/v1/ratings"
MAX_BYTES = 65536
LIMITS = {"requests": 7, "response_bytes_each": MAX_BYTES,
          "aggregate_response_bytes": 7 * MAX_BYTES, "request_seconds": 30,
          "redirects": 0, "retries": 0, "pagination": 0, "rows_each": 1}
_FIXED_RESOLVER = helper._production_credential


class ProbeError(ValueError):
    """Closed refusal; provider values, errors and credentials never escape."""


def _fail(message):
    raise ProbeError(message)


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _hash(value, length=64):
    if type(value) is not str or re.fullmatch("[0-9a-f]{" + str(length) + "}", value) is None:
        _fail("invalid probe identity")
    return value


def _clock(value):
    try:
        return helper._clock(value)
    except helper.SourceAuditError:
        _fail("invalid probe clock")


def _canonical(body):
    try:
        return helper._canonical(body)
    except (ValueError, TypeError, OverflowError):
        _fail("probe serialization refused")


@dataclass(frozen=True)
class ProbePlan:
    payload: bytes
    sha256: str

    def body(self):
        if (type(self.payload) is not bytes or not 0 < len(self.payload) <= 16384
                or _digest(self.payload) != _hash(self.sha256)):
            _fail("probe plan identity refused")
        try:
            body = helper._source_object(self.payload)
            expected = freeze_probe_plan(code_sha256=body["code_sha256"],
                helper_hashes=body["helper_hashes"], git_sha=body["git_sha"],
                owner_instruction_sha256=body["owner_instruction_sha256"],
                created_utc=body["created_utc"], expires_utc=body["expires_utc"],
                mode=body["mode"])
            if expected.payload != self.payload:
                _fail("probe plan differs from fixed scope")
            return body
        except (helper.SourceAuditError, ValueError, TypeError, KeyError):
            _fail("probe plan policy refused")


def freeze_probe_plan(*, code_sha256, helper_hashes, git_sha,
                      owner_instruction_sha256, created_utc, expires_utc,
                      mode="production"):
    """Freeze scope only; this does not attest account access or provider rights."""
    for value, length in ((code_sha256, 64), (git_sha, 40),
                          (owner_instruction_sha256, 64)):
        _hash(value, length)
    if (type(helper_hashes) is not dict or set(helper_hashes) != set(HELPER_PATHS)
            or any(type(key) is not str for key in helper_hashes)):
        _fail("incomplete reachable helper inventory")
    for value in helper_hashes.values():
        _hash(value)
    if type(mode) is not str or mode not in ("production", "offline-fixture"):
        _fail("invalid probe mode")
    created, expires = _clock(created_utc), _clock(expires_utc)
    if not created < expires <= created + timedelta(hours=48):
        _fail("invalid probe expiry")
    body = {"schema": "tpr-extended-source-probe-plan-v1", "study_id": STUDY_ID,
        "operation_id": OPERATION_ID, "mode": mode, "code_sha256": code_sha256,
        "helper_hashes": dict(helper_hashes), "git_sha": git_sha,
        "owner_instruction_sha256": owner_instruction_sha256,
        "created_utc": created.isoformat(), "expires_utc": expires.isoformat(),
        "lane_root": str(LANE_ROOT), "lane_branch": LANE_BRANCH,
        "private_root": str(PRIVATE_ROOT), "freeze_sha256": FREEZE_SHA256,
        "host": HOST, "endpoint": ENDPOINT, "method": "GET",
        "credential_authority": "env:MASSIVE_API_KEY", "authorization": "Bearer",
        "queries": [dict(query) for query in QUERIES], "limits": dict(LIMITS),
        "working_authorization": "owner-scoped-private-development-not-provider-attestation",
        "samples_only": True, "complete_history": False, "point_in_time_data": False,
        "rights_verified": False, "outcome_access": False, "quantconnect": False,
        "canonical_admission": False, "trading": False, "old_receipts_renewed": False,
        "raw_response_retention": False}
    payload = _canonical(body)
    return ProbePlan(payload, _digest(payload))


def _open_directory(path):
    """Walk every path component without following a substituted parent link."""
    if type(path) is not type(LANE_ROOT) or not path.is_absolute():
        _fail("invalid private probe root")
    descriptor = None
    try:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for component in path.parts[1:]:
            if component in (".", ".."):
                _fail("invalid probe path component")
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        result, descriptor = descriptor, None
        return result
    except OSError:
        _fail("probe directory custody refused")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_source(relative):
    path = LANE_ROOT / relative
    directory = _open_directory(path.parent)
    descriptor = None
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or not 0 <= metadata.st_size <= 262144):
            _fail("probe source custody refused")
        payload = os.read(descriptor, 262145)
        after = os.fstat(descriptor)
        if (len(payload) != metadata.st_size
                or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                    after.st_ctime_ns) != (metadata.st_dev, metadata.st_ino,
                    metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)):
            _fail("probe source changed during verification")
        return payload
    except OSError:
        _fail("probe source verification unavailable")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


def _execution_paths():
    current = Path.cwd()
    return current, current.resolve()


def _git_identity(body):
    current, physical = _execution_paths()
    if current != LANE_ROOT or physical != LANE_ROOT:
        _fail("probe requires designated physical lane")
    commands = (["git", "rev-parse", "--show-toplevel"],
                ["git", "branch", "--show-current"],
                ["git", "rev-parse", "HEAD"], ["git", "status", "--short"])
    observed = [subprocess.run(command, cwd=LANE_ROOT, capture_output=True,
        timeout=5, check=True).stdout.decode("utf-8") for command in commands]
    if [value.strip() for value in observed[:3]] != [str(LANE_ROOT), LANE_BRANCH, body["git_sha"]]:
        _fail("probe Git identity mismatch")


def _verify_execution_identity(body):
    try:
        _git_identity(body)
        root_descriptor = _open_directory(LANE_ROOT)
        os.close(root_descriptor)
        if Path(__file__) != LANE_ROOT / SOURCE_RELATIVE:
            _fail("probe module path mismatch")
        inventory = {SOURCE_RELATIVE: body["code_sha256"],
                     FREEZE_RELATIVE: FREEZE_SHA256, **body["helper_hashes"]}
        for relative, expected in inventory.items():
            if _digest(_read_source(relative)) != expected:
                _fail("probe source hash mismatch")
            _git_identity(body)
            committed = subprocess.run(["git", "show", body["git_sha"] + ":" + relative],
                cwd=LANE_ROOT, capture_output=True, timeout=5, check=True).stdout
            if type(committed) is not bytes or len(committed) > 262144 or _digest(committed) != expected:
                _fail("probe committed source hash mismatch")
        _git_identity(body)
    except (OSError, UnicodeError, subprocess.SubprocessError):
        _fail("probe execution custody unavailable")


def _private_directory(path, mode):
    if mode == "production" and path != PRIVATE_ROOT or mode == "offline-fixture" and path == PRIVATE_ROOT:
        _fail("probe private-root policy refused")
    descriptor = _open_directory(path)
    metadata = os.fstat(descriptor)
    if (metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700
            or not stat.S_ISDIR(metadata.st_mode)):
        os.close(descriptor)
        _fail("probe root requires owner-only custody")
    return descriptor


def _claim(directory, name, body):
    descriptor = None
    try:
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        helper._write_fd(descriptor, _canonical(body))
        os.fsync(directory)
    except FileExistsError:
        _fail("probe scope already spent")
    except (OSError, helper.SourceAuditError):
        _fail("probe claim unavailable; scope remains spent")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _publish(directory, name, body):
    try:
        helper._publish(directory, name, _canonical(body))
    except (OSError, helper.SourceAuditError):
        _fail("probe publication refused; scope remains spent")


@contextmanager
def _deadline():
    if (threading.current_thread() is not threading.main_thread()
            or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0)):
        _fail("probe wall deadline unavailable")
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_args):
        _fail("probe transport deadline")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 30)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@dataclass(frozen=True)
class ProbeResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    complete: bool = True


def _https_get(query, credential):
    if query not in QUERIES or not helper._valid_credential(credential):
        _fail("probe transport scope refused")
    connection = None
    try:
        with _deadline():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname, context.verify_mode, context.keylog_filename = True, ssl.CERT_REQUIRED, None
            context.load_default_certs()
            connection = http.client.HTTPSConnection(HOST, 443, timeout=30, context=context)
            connection.set_debuglevel(0)
            connection.request("GET", ENDPOINT + "?" + urlencode(query),
                headers={"Authorization": "Bearer " + credential, "Accept": "application/json",
                         "Accept-Encoding": "identity", "Connection": "close",
                         "User-Agent": "TPR-extended-source-probe/1"})
            response = connection.getresponse()
            headers = tuple((name.lower(), value) for name, value in response.getheaders()
                            if name.lower() in ("content-length", "content-type", "content-encoding"))
            recognized = dict(headers)
            length = recognized.get("content-length")
            if (len(recognized) != len(headers)
                    or recognized.get("content-encoding", "identity").lower() != "identity"
                    or recognized.get("content-type", "application/json").split(";", 1)[0].lower().strip() != "application/json"
                    or length is not None and (re.fullmatch(r"[0-9]{1,9}", length) is None
                                              or int(length) > MAX_BYTES)):
                return ProbeResponse(response.status, headers, b"", False)
            # Never consume a byte beyond the frozen cap. An unfinished HTTP
            # response, or a short declared body, is retained as incomplete.
            payload = response.read(MAX_BYTES)
            complete = response.isclosed() and (length is None or len(payload) == int(length))
            return ProbeResponse(response.status, headers, payload, complete)
    except (OSError, http.client.HTTPException):
        _fail("probe transport refused")
    finally:
        if connection is not None:
            connection.close()


_FIXED_TRANSPORT = _https_get


def _echo(value, credential):
    if type(value) is str:
        return credential in value
    if type(value) is dict:
        return any(_echo(key, credential) or _echo(child, credential)
                   for key, child in value.items())
    if type(value) is list:
        return any(_echo(child, credential) for child in value)
    return False


def _native_id(value):
    return (type(value) is int and 0 < value < 10**30 or type(value) is str
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:\-]{0,127}", value) is not None)


def _positive_target(value):
    if type(value) not in (str, int, Decimal) or type(value) is str and len(value) > 96:
        return False
    try:
        number = Decimal(value)
        return (number.is_finite() and 0 < number <= Decimal(10**24)
                and len(number.as_tuple().digits) <= 64
                and -32 <= number.as_tuple().exponent <= 32)
    except (ValueError, InvalidOperation, OverflowError):
        return False


def _empty_projection():
    return {"sample_count": 0, "date_in_window_count": 0, "aware_touch_clock_count": 0,
        "touch_not_before_issue_count": 0, "touch_not_after_fetch_count": 0,
        "event_id_valid_count": 0, "event_id_integer_count": 0,
        "event_id_string_count": 0, "firm_id_valid_count": 0,
        "firm_id_integer_count": 0, "firm_id_string_count": 0,
        "positive_nominal_pair_count": 0, "usd_count": 0,
        "revision_action_count": 0, "pagination_present": False}


def _reduce_response(response, credential, window, fetched):
    """Closed count-only projection. Missing target on one sample is not denial."""
    projection = _empty_projection()
    if (type(response) is not ProbeResponse or type(response.status) is not int
            or not 100 <= response.status <= 599 or type(response.body) is not bytes
            or not 0 < len(response.body) <= MAX_BYTES or response.complete is not True):
        _fail("probe response framing refused")
    if type(response.headers) is not tuple:
        _fail("probe response headers refused")
    recognized = {}
    for row in response.headers:
        if (type(row) is not tuple or len(row) != 2 or any(type(value) is not str for value in row)
                or row[0] not in ("content-length", "content-type", "content-encoding")
                or row[0] in recognized):
            _fail("probe response headers refused")
        recognized[row[0]] = row[1]
    length = recognized.get("content-length")
    if (recognized.get("content-encoding", "identity").lower() != "identity"
            or recognized.get("content-type", "application/json").split(";", 1)[0].lower().strip() != "application/json"
            or length is not None and (re.fullmatch(r"[0-9]{1,9}", length) is None
                                      or int(length) != len(response.body))):
        _fail("probe response headers refused")
    if credential.encode("ascii") in response.body:
        _fail("probe credential echo refused")
    try:
        body = helper._source_object(response.body)
    except helper.SourceAuditError:
        _fail("probe source JSON refused")
    if _echo(body, credential):
        _fail("probe credential echo refused")
    if response.status != 200:
        return "http_refused", projection
    if body.get("status") != "OK" or type(body.get("results")) is not list:
        _fail("probe API schema or status refused")
    if len(body["results"]) > 1:
        _fail("probe source sample limit refused")
    projection["pagination_present"] = body.get("next_url") is not None
    if not body["results"]:
        return "sample_empty", projection
    row = body["results"][0]
    if type(row) is not dict:
        _fail("probe source row schema refused")
    issued = row.get("date")
    try:
        if (type(issued) is not str or date.fromisoformat(issued).isoformat() != issued
                or not window[0] <= issued <= window[1]):
            _fail("probe sample outside fixed window")
    except (ValueError, TypeError):
        _fail("probe sample outside fixed window")
    projection["sample_count"] = projection["date_in_window_count"] = 1
    for field, prefix in (("benzinga_id", "event_id"), ("benzinga_firm_id", "firm_id")):
        value = row.get(field)
        projection[prefix + "_valid_count"] = int(_native_id(value))
        projection[prefix + "_integer_count"] = int(type(value) is int)
        projection[prefix + "_string_count"] = int(type(value) is str)
    try:
        touched = _clock(row.get("last_updated"))
        projection["aware_touch_clock_count"] = 1
        projection["touch_not_before_issue_count"] = int(touched.date().isoformat() >= issued)
        projection["touch_not_after_fetch_count"] = int(touched <= fetched)
    except ProbeError:
        pass
    projection["positive_nominal_pair_count"] = int(_positive_target(row.get("price_target"))
                                                    and _positive_target(row.get("previous_price_target")))
    projection["usd_count"] = int(row.get("currency") == "USD")
    projection["revision_action_count"] = int(row.get("price_target_action") in ("raises", "lowers", "maintains"))
    return "sampled", projection


@dataclass(frozen=True)
class ProbeResult:
    payload: bytes
    sha256: str
    aggregate_path: Path
    terminal_path: Path


def execute_probe(plan):
    """Production-only; immutable exact custody precedes any spent operation."""
    if type(plan) is not ProbePlan or plan.body()["mode"] != "production":
        _fail("production probe requires exact production plan")
    body = plan.body()
    _verify_execution_identity(body)
    return _execute(plan, PRIVATE_ROOT, datetime.now(timezone.utc),
                    helper._production_credential, _https_get, lambda: datetime.now(timezone.utc))


def _execute_fixture_probe(plan, private_root, *, now, credential_resolver, transport):
    if (type(plan) is not ProbePlan or plan.body()["mode"] != "offline-fixture"
            or private_root == PRIVATE_ROOT
            or not callable(credential_resolver) or not callable(transport)
            or credential_resolver in (_FIXED_RESOLVER, helper._production_credential)
            or transport in (_FIXED_TRANSPORT, _https_get)):
        _fail("fixture probe requires synthetic isolated adapters")
    return _execute(plan, private_root, now, credential_resolver, transport, lambda: now)


def _execute(plan, private_root, now, resolver, transport, clock):
    body = plan.body()
    if (type(now) is not datetime or now.tzinfo is None or now.utcoffset() != timedelta(0)
            or not _clock(body["created_utc"]) <= now < _clock(body["expires_utc"])):
        _fail("probe outside frozen expiry")
    directory = _private_directory(private_root, body["mode"])
    try:
        _claim(directory, OPERATION_ID + ".access.spent.json",
            {"schema": "tpr-extended-probe-access-spent-v1", "operation_id": OPERATION_ID,
             "plan_sha256": plan.sha256, "started_utc": now.isoformat(), "mode": body["mode"]})
        _publish(directory, OPERATION_ID + ".plan.json", body)
        # Reserve all seven fixed requests before a credential is loaded. A
        # failure leaves the global claim and partial request claims spent.
        for index, query in enumerate(QUERIES):
            _claim(directory, f"{OPERATION_ID}.request.{index + 1}.spent.json",
                {"schema": "tpr-extended-probe-request-spent-v1", "operation_id": OPERATION_ID,
                 "plan_sha256": plan.sha256, "request_index": index + 1,
                 "query": dict(query), "started_utc": now.isoformat()})
        rows, attempted, total_bytes, interrupted = [], 0, 0, False
        credential = None
        try:
            credential = resolver("massive")
            if (not helper._valid_credential(credential)
                    or body["mode"] == "offline-fixture" and not credential.startswith("SYNTHETIC_")):
                _fail("probe credential unavailable")
        except KeyboardInterrupt:
            interrupted, credential = True, None
        except Exception:
            credential = None
        for index, (query, window) in enumerate(zip(QUERIES, WINDOWS)):
            projection, disposition = _empty_projection(), "credential_unavailable"
            status, wire_hash, wire_bytes, complete = None, None, 0, False
            if interrupted:
                disposition = "interrupted_unattempted"
            elif credential is not None and helper._valid_credential(credential):
                try:
                    fetched = clock()
                    if fetched >= _clock(body["expires_utc"]):
                        _fail("probe outside frozen expiry")
                    attempted += 1
                    disposition = "transport_refused_unknown"
                    response = transport(query, credential)
                    fetched = clock()
                    if (type(fetched) is not datetime or fetched.tzinfo is None
                            or fetched.utcoffset() != timedelta(0) or fetched < now
                            or fetched >= _clock(body["expires_utc"])):
                        _fail("probe response clock refused")
                    if type(response) is ProbeResponse:
                        status = response.status if type(response.status) is int and 100 <= response.status <= 599 else None
                        complete = response.complete is True
                        if type(response.body) is bytes and len(response.body) <= MAX_BYTES:
                            wire_bytes = len(response.body)
                            total_bytes += wire_bytes
                            # Do not derive a persisted credential hash through
                            # an echoed response, including escaped JSON echoes.
                            if credential.encode("ascii") in response.body:
                                _fail("probe credential echo refused")
                            parsed = helper._source_object(response.body)
                            if _echo(parsed, credential):
                                _fail("probe credential echo refused")
                            wire_hash = _digest(response.body)
                    disposition, projection = _reduce_response(response, credential, window, fetched)
                except KeyboardInterrupt:
                    interrupted, disposition = True, "interrupted_unknown"
                except Exception:
                    disposition = "response_refused_unknown"
            row = {"window_start": window[0], "window_end": window[1],
                   "request_index": index + 1, "http_status": status,
                   "disposition": disposition, "projection": projection}
            rows.append(row)
            _publish(directory, f"{OPERATION_ID}.request.{index + 1}.terminal.json",
                {"schema": "tpr-extended-probe-request-terminal-v1", "operation_id": OPERATION_ID,
                 "plan_sha256": plan.sha256, "fetch_utc": clock().isoformat(),
                 "response_sha256": wire_hash, "response_bytes": wire_bytes,
                 "response_complete": complete, "scope_spent": True, **row})
        successes = sum(row["disposition"] in ("sampled", "sample_empty") for row in rows)
        report = {"schema": "tpr-extended-source-probe-report-v1", "operation_id": OPERATION_ID,
            "study_id": STUDY_ID, "plan_sha256": plan.sha256,
            "windows": rows, "reserved_requests": 7, "attempted_requests": attempted,
            "successful_sample_responses": successes,
            "sampled_rows": sum(row["projection"]["sample_count"] for row in rows),
            "response_bytes": total_bytes, "all_requests_succeeded": successes == 7,
            "interrupted": interrupted, "scope_spent": True, "samples_only": True,
            "complete_history": False, "point_in_time_data": False, "rights_verified": False,
            "outcome_reads": 0, "development_looks": 0, "quantconnect_attempts": 0,
            "canonical_admission": False, "trading": False, "old_receipts_renewed": False,
            "full_capture_admitted": False}
        payload = _canonical(report)
        aggregate_name, terminal_name = OPERATION_ID + ".aggregate.json", OPERATION_ID + ".terminal.json"
        _publish(directory, aggregate_name, report)
        _publish(directory, terminal_name,
            {"schema": "tpr-extended-probe-terminal-v1", "operation_id": OPERATION_ID,
             "plan_sha256": plan.sha256, "aggregate_sha256": _digest(payload),
             "status": "INTERRUPTED" if interrupted else "COMPLETED" if successes == 7 else "FAILED",
             "scope_spent": True, "attempted_requests": attempted,
             "outcome_reads": 0, "development_looks": 0, "quantconnect_attempts": 0})
        if interrupted:
            raise KeyboardInterrupt("probe interrupted; fresh scope remains spent") from None
        return ProbeResult(payload, _digest(payload), private_root / aggregate_name, private_root / terminal_name)
    finally:
        os.close(directory)
