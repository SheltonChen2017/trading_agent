"""One-use four-provider Keychain connection check, never source admission.

Requires a separately committed exact run decision. Seven fixed requests,
no retries/redirects/pagination; successful bodies are bounded in memory and
only finite schema/count observations are retained. No licensed rows persist.
The once-only --read-output mode requires external native network denial.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import MappingProxyType
from urllib.parse import quote, quote_plus, urlencode

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import arv2_keychain_connections as credentials
from scripts import run_arv2_massive_oct12_diagnostic as helpers

capture = helpers.capture
canonical_json_bytes = helpers.canonical_json_bytes
BRANCH = "codex/strategy-analyst-revisions-v2"
PYTHON = Path("/Users/sheltonchen/.venvs/trading_agent-py313/bin/python")
SOURCE = ROOT / "scripts/run_arv2_keychain_connection_check.py"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/provider_connections/R296-20261013-A"
SCHEMA = "arv2-keychain-provider-connection-check-v1"
OUTPUT_SCHEMA = "arv2-keychain-provider-connection-output-v1"
DEADLINE_SECONDS = 180
READER_SECONDS = 30
REQUEST_SECONDS = 15
REQUESTS_VERSION = "2.34.2"
MAX_BYTES = 16 * 1024
MAX_BODY_BYTES = 1024 * 1024
SOURCE_PINS = MappingProxyType({**helpers.SOURCE_PINS,
    "scripts/run_arv2_massive_oct12_diagnostic.py":
        "137743f30acd78aafb768114446f2b20cecec0bbac12fdc995233accf2911860",
    "scripts/arv2_keychain_connections.py":
        "bd9c0863c484810b8cf7a02e46551ed63f99ecec7bb4f322b91270fad7a28227",
})


@dataclass(frozen=True)
class Endpoint:
    provider: str
    role: str
    origin: str
    path: str
    query: tuple[tuple[str, str], ...]
    auth_query: str | None
    fields: tuple[str, ...]


ENDPOINTS = (
    Endpoint("fmp", "rating_changes", "https://financialmodelingprep.com", "/stable/grades",
        (("symbol", "AAPL"),), "apikey",
        ("symbol", "date", "gradingCompany", "previousGrade", "newGrade", "action")),
    Endpoint("massive", "analyst_ratings", "https://api.massive.com", "/benzinga/v1/ratings",
        (("ticker", "AAPL"), ("limit", "1")), None,
        ("ticker", "date", "time", "last_updated", "benzinga_id", "benzinga_firm_id",
         "firm", "previous_rating", "rating", "rating_action")),
    Endpoint("massive", "earnings", "https://api.massive.com", "/benzinga/v1/earnings",
        (("ticker", "AAPL"), ("limit", "1")), None,
        ("ticker", "date", "time", "last_updated", "benzinga_id", "actual_eps", "estimated_eps")),
    Endpoint("massive", "corporate_guidance", "https://api.massive.com", "/benzinga/v1/guidance",
        (("ticker", "AAPL"), ("limit", "1")), None,
        ("ticker", "date", "time", "last_updated", "benzinga_id", "min_eps_guidance",
         "max_eps_guidance", "min_revenue_guidance", "max_revenue_guidance")),
    Endpoint("eodhd", "daily_prices", "https://eodhd.com", "/api/eod/AAPL.US",
        (("from", "2026-10-12"), ("to", "2026-10-12"), ("fmt", "json")), "api_token",
        ("date", "open", "high", "low", "close", "adjusted_close", "volume")),
    Endpoint("eodhd", "earnings_calendar", "https://eodhd.com", "/api/calendar/earnings",
        (("symbols", "AAPL.US"), ("from", "2026-07-01"), ("to", "2026-09-30"),
         ("fmt", "json")), "api_token",
        ("code", "report_date", "date", "actual", "estimate", "difference", "percent")),
    Endpoint("sharadar", "ticker_identity", "https://api.sharadar.com", "/v1.0/data/tickers",
        (("ticker", "AAPL"), ("table", "stocks"), ("fields", "ticker,permaticker"),
         ("limit", "1"), ("format", "csv")), "api_key", ("ticker", "permaticker")),
)
PROFILE = canonical_json_bytes({
    "schema": SCHEMA, "purpose": "one_time_keychain_connection_and_schema_observation",
    "root": str(ROOT), "branch": BRANCH, "python": str(PYTHON),
    "host": "darwin-posix-python3.13", "control": str(CONTROL),
    "keychain": credentials.KEYCHAIN,
    "services": {key: list(pair) for key, pair in credentials.SERVICES.items()},
    "endpoints": [{"provider": e.provider, "role": e.role, "origin": e.origin,
        "path": e.path, "query": dict(e.query), "auth_query": e.auth_query,
        "fields": list(e.fields)} for e in ENDPOINTS],
    "maximum_send_intents": 7, "credential_reads_per_provider": 1,
    "transport": "owned_requests_httpadapter_send_no_session", "requests_version": REQUESTS_VERSION,
    "ssl_key_log_environment": "refuse_if_present", "stream": True,
    "unsafe_transport_logging": "refuse_handlers_debug_levels_never_change_settings",
    "tls_verify": True, "proxies": {}, "retries": 0, "redirects": False,
    "non200_body_unread": True, "retain_response_bodies": False,
    "fields_available_semantics": "all_rows_non_null_presence_not_usability",
    "independent_endpoint_failures_continue": True, "control_ambiguity_stops": True,
    "parent_deadline_seconds": DEADLINE_SECONDS, "keychain_timeout_seconds": 20,
    "request_timeout_seconds": REQUEST_SECONDS, "reader_deadline_seconds": READER_SECONDS,
    "maximum_output_bytes": MAX_BYTES, "maximum_response_bytes": MAX_BODY_BYTES,
    "source_pins": dict(SOURCE_PINS), "provider_request_count": None,
    "capture_accepted": False, "point_in_time_proven": False, "backtest_ready": False,
    "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0,
    "separate_run_freeze_required": True,
})
PROFILE_SHA256 = hashlib.sha256(PROFILE).hexdigest()
_SUCCESS = frozenset({"valid_nonempty", "valid_empty"})
_ROW_TERMINALS = frozenset({"not_attempted", "credentials_unavailable", "request_preparation_refused",
    "send_intent_ambiguous", "transport_failure", "response_binding_refused", "invalid_status",
    "http_status", "body_refused", "schema_refused", "credential_echo_refused", "close_refused",
    "deadline_timeout", "cancelled", "control_refused"}) | _SUCCESS
_TERMINALS = frozenset({"all_connections_responded", "completed_with_failures",
    "control_refused", "deadline_timeout", "cancelled", "send_intent_ambiguous", "close_refused"})
_CLAIM_KEYS = {"schema", "profile_sha256", "expected_head", "caller_sha256", "claimed_at",
    "parent_pid", "attempt_consumed"}
_REPORT_KEYS = {"schema", "profile_sha256", "expected_head", "caller_sha256",
    "parent_started_at", "parent_observed_terminal_at", "terminal", "attempt_consumed",
    "observations", "send_attempt_count", "provider_request_count", "capture_accepted",
    "point_in_time_proven", "backtest_ready", "paper_look_committed", "qc_calls", "outcome_reads"}
_ROW_KEYS = {"provider", "role", "endpoint_path", "status_code", "send_intent_recorded",
    "terminal", "row_count", "fields_available"}


class Refusal(ValueError):
    pass


def _require(condition: bool) -> None:
    if not condition:
        raise Refusal("control_refused")


def _preflight(expected_head: str, caller_sha256: str, deadline: float) -> None:
    _require("SSLKEYLOGFILE" not in os.environ)
    _require(sys.platform == "darwin" and os.name == "posix"
        and sys.version_info[:2] == (3, 13) and Path(sys.executable) == PYTHON
        and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE)
    _require(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head) is not None)
    helpers.require_sha256(caller_sha256, "caller hash")
    for args, expected in ((["rev-parse", "--show-toplevel"], str(ROOT)),
            (["branch", "--show-current"], BRANCH), (["rev-parse", "HEAD"], expected_head),
            (["status", "--porcelain"], "")):
        result = subprocess.run(["git", *args], cwd=ROOT, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=min(3, helpers._remaining(deadline)), check=False)
        _require(result.returncode == 0 and not result.stderr
            and result.stdout.decode("utf-8").strip() == expected)
    for relative, digest in SOURCE_PINS.items():
        _require(helpers._source_digest(ROOT / relative) == digest)
    _require(helpers._source_digest(SOURCE) == caller_sha256)
    capture._require_dirfd_support()
    helpers._remaining(deadline)


def _write_held(directory: int, name: str, value: dict) -> tuple[int, bytes, tuple]:
    payload = canonical_json_bytes(value)
    _require(0 < len(payload) <= MAX_BYTES)
    fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        os.fchmod(fd, 0o600)
        capture._write_all(fd, payload, "connection observation")
        os.fsync(fd)
        os.fsync(directory)
        identity = helpers._identity(helpers._file_metadata(fd))
        helpers._named_file(directory, name, fd)
        _require(os.pread(fd, MAX_BYTES + 1, 0) == payload)
        _require(helpers._identity(helpers._file_metadata(fd)) == identity)
        helpers._named_file(directory, name, fd)
        return fd, payload, identity
    except BaseException:
        os.close(fd)
        raise


def _check_held(directory: int, name: str, fd: int, identity: tuple) -> None:
    _require(helpers._identity(helpers._file_metadata(fd)) == identity)
    helpers._named_file(directory, name, fd)
    capture._require_reopened_artifact_identity(CONTROL, directory)


def _claim(expected_head: str, caller_sha256: str) -> tuple[int, int, tuple]:
    capture._require_operational_artifact_scope(CONTROL)
    _, parent = capture._open_directory_path(CONTROL.parent, create=True, name="connection parent")
    directory = claim = None
    try:
        os.mkdir(CONTROL.name, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = capture._open_private_child_directory(parent, CONTROL.name, "connection claim")
        claim, _, identity = _write_held(directory, "claim.json", {
            "schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "expected_head": expected_head,
            "caller_sha256": caller_sha256, "claimed_at": helpers._utc_now(),
            "parent_pid": os.getpid(), "attempt_consumed": True})
        capture._require_pinned_child_identity(parent, CONTROL.name, directory, "connection claim")
        return directory, claim, identity
    except BaseException:
        for fd in (claim, directory):
            if fd is not None:
                os.close(fd)
        raise
    finally:
        os.close(parent)


def _new_adapter():
    # Presence is checked again immediately before the only Requests import.
    _require("SSLKEYLOGFILE" not in os.environ)
    import requests
    _require(requests.__version__ == REQUESTS_VERSION)
    _check_transport_logging()
    return requests.adapters.HTTPAdapter(max_retries=0)


def _check_transport_logging() -> None:
    """Refuse configurations that could print query keys, never change them."""
    import http.client
    import urllib3.connection
    loggers = [logging.getLogger()]
    for name, logger in tuple(logging.Logger.manager.loggerDict.items()):
        if name in {"requests", "urllib3"} or name.startswith(("requests.", "urllib3.")):
            if isinstance(logger, logging.Logger):
                loggers.append(logger)
    for logger in loggers:
        _require(logger.getEffectiveLevel() >= logging.WARNING
            and all(type(handler) is logging.NullHandler for handler in logger.handlers))
    for connection in (http.client.HTTPConnection, http.client.HTTPSConnection,
            urllib3.connection.HTTPConnection, urllib3.connection.HTTPSConnection):
        _require(type(connection.debuglevel) is int and connection.debuglevel == 0)


def _prepare(endpoint: Endpoint, key: str):
    import requests
    _check_transport_logging()
    query = list(endpoint.query)
    if endpoint.auth_query is not None:
        query.append((endpoint.auth_query, key))
    url = endpoint.origin + endpoint.path + "?" + urlencode(query)
    headers = {} if endpoint.auth_query else {"Authorization": "Bearer " + key}
    request = requests.Request("GET", url, headers=headers).prepare()
    _validate_request(request, endpoint, key, url)
    return request, url


def _validate_request(request, endpoint: Endpoint, key: str, url: str) -> None:
    query = list(endpoint.query)
    if endpoint.auth_query is not None:
        query.append((endpoint.auth_query, key))
    _require(url == endpoint.origin + endpoint.path + "?" + urlencode(query))
    _require(request.url == url and request.method == "GET" and request.body is None)
    _require(dict(request.headers) == ({} if endpoint.auth_query else {"Authorization": "Bearer " + key}))
    _require(request.hooks == {"response": []})


def _body_bytes(response, endpoint: Endpoint, deadline: float) -> bytes:
    # No transparent decompression, HTML, or response convenience APIs.
    encoding = response.headers.get("Content-Encoding", "")
    media = response.headers.get("Content-Type", "")
    _require(type(encoding) is str and encoding.lower().strip() in {"", "identity"})
    accepted_media = {"text/csv", "application/csv", "text/plain"} if endpoint.provider == "sharadar" else {"application/json", "text/json"}
    _require(type(media) is str and media.split(";", 1)[0].lower().strip() in accepted_media)
    length = response.headers.get("Content-Length")
    if length is not None:
        _require(type(length) is str and re.fullmatch(r"[0-9]{1,8}", length) is not None
            and 0 < int(length) <= MAX_BODY_BYTES)
    chunks = []
    count = 0
    for chunk in response.raw.stream(amt=16384, decode_content=False):
        helpers._remaining(deadline)
        _require(type(chunk) is bytes)
        count += len(chunk)
        _require(count <= MAX_BODY_BYTES)
        chunks.append(chunk)
    _require(count > 0 and (length is None or count == int(length)))
    helpers._remaining(deadline)
    return b"".join(chunks)


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value)
        value[key] = item
    return value


def _constant(_value):
    raise Refusal("schema_refused")


def _echo_in(value: str, key: str) -> bool:
    if key in value:
        return True
    # Percent escapes are case-insensitive. Variants are bounded by the key
    # shape, and JSON escaping is decoded before the recursive pass below.
    lowered = value.lower()
    return any(variant != key and variant.lower() in lowered
               for variant in (quote(key, safe=""), quote_plus(key, safe="")))


def _no_echo(value, key: str, depth: int = 0) -> None:
    _require(depth <= 24)
    if type(value) is str:
        if _echo_in(value, key):
            raise Refusal("credential_echo_refused")
    elif type(value) is dict:
        for name, item in value.items():
            _no_echo(name, key, depth + 1)
            _no_echo(item, key, depth + 1)
    elif type(value) is list:
        for item in value:
            _no_echo(item, key, depth + 1)


def _date(value: object) -> bool:
    if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _number(value: object) -> bool:
    return type(value) is int or type(value) is Decimal and value.is_finite()


def _schema(endpoint: Endpoint, payload: bytes, key: str) -> tuple[int, dict]:
    _require(type(payload) is bytes and 0 < len(payload) <= MAX_BODY_BYTES)
    text = payload.decode("utf-8-sig" if endpoint.provider == "sharadar" else "utf-8", errors="strict")
    if _echo_in(text, key):
        raise Refusal("credential_echo_refused")
    if endpoint.provider == "sharadar":
        records = list(csv.reader(io.StringIO(text, newline=""), strict=True))
        _require(1 <= len(records) <= 2 and records[0] == ["ticker", "permaticker"])
        for row in records[1:]:
            _require(len(row) == 2 and row[0] == "AAPL" and 1 <= len(row[1]) <= 128
                and all(33 <= ord(char) <= 126 for char in row[1]))
        return len(records) - 1, {name: len(records) == 2 for name in endpoint.fields}
    value = json.loads(text, object_pairs_hook=_pairs, parse_float=Decimal, parse_constant=_constant)
    _no_echo(value, key)
    if endpoint.provider == "massive":
        _require(type(value) is dict and value.get("status") == "OK" and "results" in value
            and not any(name.lower() in {"error", "errors", "message"} for name in value))
        rows = value["results"]
    elif endpoint.role == "earnings_calendar":
        _require(type(value) is dict and value.get("type") == "Earnings"
            and value.get("symbols") == "AAPL.US" and "earnings" in value
            and not any(name.lower() in {"error", "errors", "message"} for name in value))
        rows = value["earnings"]
    else:
        rows = value
    _require(type(rows) is list and len(rows) <= 10000)
    if endpoint.provider == "massive" or endpoint.role == "daily_prices":
        _require(len(rows) <= 1)
    for row in rows:
        _require(type(row) is dict and not any(name.lower() in {"error", "errors", "message"} for name in row))
        if endpoint.provider == "fmp":
            _require(row["symbol"] == "AAPL" and _date(row["date"]))
            _require(all(row.get(name) is None or type(row[name]) is str and len(row[name]) <= 256
                for name in ("gradingCompany", "previousGrade", "newGrade", "action")))
        elif endpoint.provider == "massive":
            _require(row["ticker"] == "AAPL" and _date(row["date"]))
            _require(all(row.get(name) is None or type(row[name]) is str and len(row[name]) <= 256
                or _number(row[name]) for name in endpoint.fields))
        elif endpoint.role == "daily_prices":
            _require(row["date"] == "2026-10-12"
                and all(_number(row[name]) and row[name] > 0
                    for name in ("open", "high", "low", "close", "adjusted_close"))
                and _number(row["volume"]) and row["volume"] >= 0)
        elif endpoint.role == "earnings_calendar":
            _require(row["code"] == "AAPL.US" and _date(row["report_date"])
                and "2026-07-01" <= row["report_date"] <= "2026-09-30" and _date(row["date"]))
            _require(all(row.get(name) is None or _number(row[name])
                for name in ("actual", "estimate", "difference", "percent")))
    return len(rows), {name: bool(rows) and all(row.get(name) is not None for row in rows)
                       for name in endpoint.fields}


def _row(endpoint: Endpoint) -> dict:
    return {"provider": endpoint.provider, "role": endpoint.role, "endpoint_path": endpoint.path,
        "status_code": None, "send_intent_recorded": False, "terminal": "not_attempted",
        "row_count": None, "fields_available": {name: False for name in endpoint.fields}}


def _row_limit(endpoint: Endpoint) -> int:
    return 1 if endpoint.provider in {"massive", "sharadar"} or endpoint.role == "daily_prices" else 10000


def _required_fields(endpoint: Endpoint) -> tuple[str, ...]:
    if endpoint.provider == "fmp":
        return ("symbol", "date")
    if endpoint.provider == "massive":
        return ("ticker", "date")
    if endpoint.role == "earnings_calendar":
        return ("code", "report_date", "date")
    return endpoint.fields


def _observe(directory: int, claim: int, identity: tuple, deadline: float, result: dict) -> None:
    _check_held(directory, "claim.json", claim, identity)
    marker, _, _ = _write_held(directory, "observation-started.json",
        {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256})
    os.close(marker)
    adapter = None
    key = None
    current_provider = None
    try:
        adapter = _new_adapter()
        for index, endpoint in enumerate(ENDPOINTS):
            row = result["observations"][index]
            response = None
            try:
                helpers._remaining(deadline)
                _check_held(directory, "claim.json", claim, identity)
                row["terminal"] = "control_refused"
                _check_transport_logging()
                if endpoint.provider != current_provider:
                    current_provider = endpoint.provider
                    key = None
                    row["terminal"] = "credentials_unavailable"
                    try:
                        key = credentials.load_key(endpoint.provider,
                            timeout_seconds=min(20, helpers._remaining(deadline)))
                    except credentials.KeychainUnavailable:
                        pass
                if key is None:
                    row["terminal"] = "credentials_unavailable"
                    continue
                row["terminal"] = "request_preparation_refused"
                request, url = _prepare(endpoint, key)
                row["terminal"] = "control_refused"
                _check_held(directory, "claim.json", claim, identity)
                row["terminal"] = result["terminal"] = "send_intent_ambiguous"
                marker, _, _ = _write_held(directory, f"send-{index + 1}-started.json",
                    {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
                     "provider": endpoint.provider, "role": endpoint.role, "endpoint_path": endpoint.path})
                os.close(marker)
                row["send_intent_recorded"] = True
                result["send_attempt_count"] += 1
                row["terminal"] = "control_refused"
                _check_transport_logging()
                row["terminal"] = "transport_failure"
                response = adapter.send(request, stream=True, verify=True, cert=None, proxies={},
                    timeout=min(REQUEST_SECONDS, helpers._remaining(deadline)))
                row["terminal"] = "response_binding_refused"
                _require(response.request is request and response.url == url)
                _validate_request(request, endpoint, key, url)
                row["terminal"] = "invalid_status"
                status = response.status_code
                _require(type(status) is int and 100 <= status <= 599)
                row["status_code"] = status
                if status != 200:
                    row["terminal"] = "http_status"
                else:
                    row["terminal"] = "body_refused"
                    payload = _body_bytes(response, endpoint, deadline)
                    row["terminal"] = "schema_refused"
                    try:
                        row_count, fields = _schema(endpoint, payload, key)
                    except Refusal as error:
                        if error.args == ("credential_echo_refused",):
                            row["terminal"] = "credential_echo_refused"
                        raise
                    finally:
                        payload = None
                    row["row_count"], row["fields_available"] = row_count, fields
                    row["terminal"] = "valid_nonempty" if row_count else "valid_empty"
            except helpers.Deadline:
                row["terminal"] = result["terminal"] = "deadline_timeout"
                return
            except (KeyboardInterrupt, SystemExit):
                row["terminal"] = result["terminal"] = "cancelled"
                return
            except BaseException:
                # Finite stage only; never format any exception or request URL.
                if row["terminal"] in {"not_attempted", "control_refused", "send_intent_ambiguous"}:
                    result["terminal"] = "send_intent_ambiguous" if row["terminal"] == "send_intent_ambiguous" else "control_refused"
                    return
            finally:
                if response is not None:
                    try:
                        response.close()
                    except helpers.Deadline:
                        row["terminal"] = result["terminal"] = "deadline_timeout"
                    except (KeyboardInterrupt, SystemExit):
                        row["terminal"] = result["terminal"] = "cancelled"
                    except BaseException:
                        row["terminal"] = result["terminal"] = "close_refused"
            if result["terminal"] in {"deadline_timeout", "cancelled", "close_refused"}:
                return
        result["terminal"] = "all_connections_responded" if all(
            row["terminal"] in _SUCCESS for row in result["observations"]) else "completed_with_failures"
    finally:
        key = None
        if adapter is not None:
            try:
                adapter.close()
            except helpers.Deadline:
                result["terminal"] = "deadline_timeout"
            except (KeyboardInterrupt, SystemExit):
                result["terminal"] = "cancelled"
            except BaseException:
                result["terminal"] = "close_refused"


def _validate(claim: dict, result: dict, expected_head: str, caller_sha256: str, actual_exit: int) -> dict:
    helpers._exact(claim, _CLAIM_KEYS)
    helpers._exact(result, _REPORT_KEYS)
    _require(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head) is not None)
    helpers.require_sha256(caller_sha256, "caller hash")
    _require(type(actual_exit) is int and actual_exit in (0, 2))
    for value in (claim, result):
        _require(value["schema"] == SCHEMA and value["profile_sha256"] == PROFILE_SHA256
            and value["expected_head"] == expected_head and value["caller_sha256"] == caller_sha256
            and value["attempt_consumed"] is True)
    _require(type(claim["parent_pid"]) is int and claim["parent_pid"] > 0)
    _require(helpers.parse_utc_timestamp(result["parent_started_at"], "start")
        <= helpers.parse_utc_timestamp(claim["claimed_at"], "claim")
        <= helpers.parse_utc_timestamp(result["parent_observed_terminal_at"], "end"))
    _require(result["provider_request_count"] is None)
    for name in ("capture_accepted", "point_in_time_proven", "backtest_ready", "paper_look_committed"):
        _require(result[name] is False)
    for name in ("qc_calls", "outcome_reads"):
        _require(type(result[name]) is int and result[name] == 0)
    terminal = result["terminal"]
    _require(type(terminal) is str and terminal in _TERMINALS)
    rows = result["observations"]
    _require(type(rows) is list and len(rows) == len(ENDPOINTS))
    _require(type(result["send_attempt_count"]) is int and 0 <= result["send_attempt_count"] <= 7)
    intents = 0
    unfinished = False
    for row, endpoint in zip(rows, ENDPOINTS, strict=True):
        helpers._exact(row, _ROW_KEYS)
        _require((row["provider"], row["role"], row["endpoint_path"])
            == (endpoint.provider, endpoint.role, endpoint.path))
        _require(type(row["send_intent_recorded"]) is bool)
        _require(type(row["terminal"]) is str and row["terminal"] in _ROW_TERMINALS)
        status = row["status_code"]
        _require(status is None or type(status) is int and 100 <= status <= 599)
        helpers._exact(row["fields_available"], set(endpoint.fields))
        _require(all(type(value) is bool for value in row["fields_available"].values()))
        if unfinished:
            _require(row["terminal"] == "not_attempted")
        if row["terminal"] == "not_attempted":
            unfinished = True
        if status is not None:
            _require(row["send_intent_recorded"])
        if row["terminal"] in _SUCCESS:
            _require(status == 200 and type(row["row_count"]) is int and 0 <= row["row_count"] <= _row_limit(endpoint))
            _require((row["row_count"] > 0) == (row["terminal"] == "valid_nonempty"))
            if row["row_count"] == 0:
                _require(not any(row["fields_available"].values()))
        else:
            # A close failure can occur after validated data; retain its count
            # only as diagnostic metadata, never a successful connection.
            _require(row["row_count"] is None or row["terminal"] in {"close_refused", "deadline_timeout", "cancelled"}
                and status == 200 and type(row["row_count"]) is int and 0 <= row["row_count"] <= _row_limit(endpoint))
            if row["row_count"] is None:
                _require(not any(row["fields_available"].values()))
        if row["row_count"] is not None and row["row_count"] > 0:
            _require(all(row["fields_available"][name] is True for name in _required_fields(endpoint)))
        if row["terminal"] in {"not_attempted", "credentials_unavailable", "request_preparation_refused", "send_intent_ambiguous"}:
            _require(status is None and not row["send_intent_recorded"])
        if row["terminal"] in {"transport_failure", "response_binding_refused", "invalid_status"}:
            _require(status is None and row["send_intent_recorded"])
        if row["terminal"] in {"body_refused", "schema_refused", "credential_echo_refused"}:
            _require(status == 200)
        if row["terminal"] == "http_status":
            _require(type(status) is int and status != 200)
        intents += int(row["send_intent_recorded"])
    _require(intents == result["send_attempt_count"])
    all_ok = all(row["terminal"] in _SUCCESS for row in rows)
    if terminal == "all_connections_responded":
        _require(all_ok)
    if terminal == "completed_with_failures":
        _require(not all_ok and not unfinished)
    complete = terminal == "all_connections_responded" and actual_exit == 0
    _require(actual_exit != 0 or complete)
    return {"schema": OUTPUT_SCHEMA, "output_authenticated": True, "connections_responded": complete,
        "actual_parent_exit": actual_exit, "terminal": terminal, "attempt_consumed": True,
        "observations": rows, "send_attempt_count": intents, "provider_request_count": None,
        "profile_sha256": PROFILE_SHA256, "capture_accepted": False, "point_in_time_proven": False,
        "backtest_ready": False, "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0}


def _run(expected_head: str, caller_sha256: str, deadline: float) -> int:
    directory = claim = report_fd = None
    consumption = False
    result = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
        "expected_head": expected_head, "caller_sha256": caller_sha256,
        "parent_started_at": helpers._utc_now(), "parent_observed_terminal_at": None,
        "terminal": "control_refused", "attempt_consumed": True,
        "observations": [_row(endpoint) for endpoint in ENDPOINTS],
        "send_attempt_count": 0, "provider_request_count": None, "capture_accepted": False,
        "point_in_time_proven": False, "backtest_ready": False, "paper_look_committed": False,
        "qc_calls": 0, "outcome_reads": 0}
    try:
        _preflight(expected_head, caller_sha256, deadline)
        consumption = None
        directory, claim, identity = _claim(expected_head, caller_sha256)
        consumption = True
        _observe(directory, claim, identity, deadline, result)
    except (helpers.Deadline, subprocess.TimeoutExpired):
        result["terminal"] = "deadline_timeout"
    except (KeyboardInterrupt, SystemExit):
        result["terminal"] = "cancelled"
    except BaseException:
        pass
    try:
        helpers._remaining(deadline)
        if directory is None:
            print(canonical_json_bytes({"terminal": "claim_ambiguous" if consumption is None else "preclaim_refusal",
                "attempt_consumed": consumption, "provider_request_count": None}).decode())
            return 2
        _check_held(directory, "claim.json", claim, identity)
        result["parent_observed_terminal_at"] = helpers._utc_now()
        exit_code = 0 if result["terminal"] == "all_connections_responded" else 2
        _validate(helpers._read_channel(claim), result, expected_head, caller_sha256, exit_code)
        report_fd, payload, report_identity = _write_held(directory, "report.json", result)
        _check_held(directory, "report.json", report_fd, report_identity)
        _check_held(directory, "claim.json", claim, identity)
        helpers._remaining(deadline)
        print(canonical_json_bytes({"terminal": result["terminal"], "profile_sha256": PROFILE_SHA256,
            "report_sha256": hashlib.sha256(payload).hexdigest(), "report_bytes": len(payload),
            "send_attempt_count": result["send_attempt_count"], "provider_request_count": None}).decode())
        return exit_code
    except BaseException:
        print('{"terminal":"publication_ambiguous","provider_request_count":null}')
        return 2
    finally:
        for fd in (report_fd, claim, directory):
            if fd is not None:
                os.close(fd)


def run(expected_head: str, caller_sha256: str) -> int:
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            return _run(expected_head, caller_sha256, deadline)
    except BaseException:
        print('{"terminal":"parent_ambiguous","provider_request_count":null}')
        return 2


def _read_leaf(directory: int, name: str, stack: ExitStack) -> tuple[bytes, int, tuple]:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    stack.callback(os.close, fd)
    identity = helpers._identity(helpers._file_metadata(fd))
    helpers._named_file(directory, name, fd)
    payload = os.pread(fd, MAX_BYTES + 1, 0)
    _require(len(payload) == identity[6] and 0 < len(payload) <= MAX_BYTES)
    _check_held(directory, name, fd, identity)
    return payload, fd, identity


def read_output(expected_head: str, caller_sha256: str, report_sha256: str,
                report_bytes: int, actual_exit: int) -> dict:
    deadline = time.monotonic() + READER_SECONDS
    with helpers._alarm(deadline):
        _require(type(report_bytes) is int and 0 < report_bytes <= MAX_BYTES)
        _require(type(actual_exit) is int and actual_exit in (0, 2))
        helpers.require_sha256(report_sha256, "external report hash")
        _preflight(expected_head, caller_sha256, deadline)
        with ExitStack() as stack:
            _, directory = capture._open_directory_path(CONTROL, create=False, name="connection output")
            stack.callback(os.close, directory)
            payload, report_fd, report_identity = _read_leaf(directory, "report.json", stack)
            _require(len(payload) == report_bytes and hashlib.sha256(payload).hexdigest() == report_sha256)
            claim_payload, claim_fd, claim_identity = _read_leaf(directory, "claim.json", stack)
            summary = _validate(helpers._decode(claim_payload), helpers._decode(payload),
                expected_head, caller_sha256, actual_exit)
            _check_held(directory, "report.json", report_fd, report_identity)
            _check_held(directory, "claim.json", claim_fd, claim_identity)
            summary.update(report_sha256=report_sha256, report_bytes=report_bytes,
                claim_sha256=hashlib.sha256(claim_payload).hexdigest(), claim_bytes=len(claim_payload))
            helpers._remaining(deadline)
            return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--caller-sha256", required=True)
    parser.add_argument("--read-output", action="store_true")
    parser.add_argument("--report-sha256")
    parser.add_argument("--report-bytes", type=int)
    parser.add_argument("--actual-parent-exit", type=int)
    args = parser.parse_args(argv)
    if args.read_output:
        try:
            value = read_output(args.expected_head, args.caller_sha256, args.report_sha256,
                args.report_bytes, args.actual_parent_exit)
            print(canonical_json_bytes(value).decode())
            return 0 if value["connections_responded"] else 2
        except BaseException:
            print('{"terminal":"output_refused","output_authenticated":false}')
            return 2
    if any(value is not None for value in (args.report_sha256, args.report_bytes, args.actual_parent_exit)):
        print('{"terminal":"arguments_refused","provider_request_count":null}')
        return 2
    return run(args.expected_head, args.caller_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
