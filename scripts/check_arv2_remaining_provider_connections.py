"""R296-C first dispatch of six products after authenticated Keychain access.

A/B are spent. Only pinned stateless A validators/transport/file primitives
are reused; this module owns a new exclusive lifecycle and output reader.
No command-line switch grants authority; a committed one-use freeze is needed.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import MappingProxyType

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_keychain_connection_check as contract

helpers = contract.helpers
capture = helpers.capture
canonical_json_bytes = helpers.canonical_json_bytes
credentials = contract.credentials
BRANCH = "codex/strategy-analyst-revisions-v2"
PYTHON = Path("/Users/sheltonchen/.venvs/trading_agent-py313/bin/python")
SOURCE = ROOT / "scripts/check_arv2_remaining_provider_connections.py"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/provider_connections/R296-20261013-C"
SCHEMA = "arv2-remaining-provider-connection-check-v1"
OUTPUT_SCHEMA = "arv2-remaining-provider-connection-output-v1"
ENDPOINTS = contract.ENDPOINTS[:6]
MAX_BYTES = 16384
DEADLINE_SECONDS = 180
READER_SECONDS = 30
SOURCE_PINS = MappingProxyType({**contract.SOURCE_PINS,
    "scripts/run_arv2_keychain_connection_check.py":
        "399d898d05f8696d4e5a1e6df25053d2449f96646fd870bf4dd2d75cd748af80",
    "scripts/diagnose_arv2_keychain_access.py":
        "6ce06af283a8445bcc68ef06d5868996c60ef507763e9834f01452e553b3fb5c"})
PROFILE = canonical_json_bytes({"schema": SCHEMA,
    "purpose": "first_six_product_dispatch_after_authenticated_keychain_access",
    "root": str(ROOT), "branch": BRANCH, "python": str(PYTHON),
    "host": "darwin-posix-python3.13", "control": str(CONTROL),
    "source_pins": dict(SOURCE_PINS), "stateless_contract_profile_sha256": contract.PROFILE_SHA256,
    "prior_access_evidence": {"report_sha256": "97ce208331cba6c531ebafc4f49c342e691d5b64cd0bedb692063373b2b98c0e",
        "report_bytes": 1070, "actual_exit": 0, "authenticated_all_valid_shape": True},
    "prior_evidence_is_external_not_reread": True, "provider_order": ["fmp", "massive", "eodhd"],
    "endpoints": [{"provider": e.provider, "role": e.role, "origin": e.origin,
        "path": e.path, "query": dict(e.query), "auth_query": e.auth_query,
        "fields": list(e.fields)} for e in ENDPOINTS],
    "maximum_send_intents": 6, "key_reads_per_provider": 1, "sharadar_excluded": True,
    "parent_deadline_seconds": DEADLINE_SECONDS, "keychain_timeout_seconds": 20,
    "request_timeout_seconds": 15, "reader_deadline_seconds": READER_SECONDS,
    "maximum_output_bytes": MAX_BYTES, "maximum_response_bytes": 1048576,
    "retain_response_bodies": False, "retries": 0, "redirects": False,
    "tls_verify": True, "stream": True, "proxies": {}, "provider_request_count": None,
    "capture_accepted": False, "backtest_ready": False, "point_in_time_proven": False,
    "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0,
    "separate_run_freeze_required": True})
PROFILE_SHA256 = hashlib.sha256(PROFILE).hexdigest()
_SUCCESS = frozenset({"valid_nonempty", "valid_empty"})
_ROW_TERMINALS = frozenset({"not_attempted", "credentials_unavailable", "request_preparation_refused",
    "send_intent_ambiguous", "transport_failure", "response_binding_refused", "invalid_status",
    "http_status", "body_refused", "schema_refused", "credential_echo_refused", "close_refused",
    "deadline_timeout", "cancelled", "control_refused"}) | _SUCCESS
_TERMINALS = frozenset({"all_connections_responded", "completed_with_failures", "control_refused",
    "deadline_timeout", "cancelled", "send_intent_ambiguous", "close_refused"})
_CLAIM_KEYS = {"schema", "profile_sha256", "expected_head", "caller_sha256", "claimed_at", "parent_pid", "attempt_consumed"}
_REPORT_KEYS = {"schema", "profile_sha256", "expected_head", "caller_sha256", "parent_started_at",
    "parent_observed_terminal_at", "terminal", "attempt_consumed", "observations", "send_attempt_count",
    "provider_request_count", "capture_accepted", "point_in_time_proven", "backtest_ready", "paper_look_committed", "qc_calls", "outcome_reads"}


class Refusal(ValueError):
    pass


def _require(condition):
    if not condition:
        raise Refusal("control_refused")


def _preflight(head: str, caller: str, deadline: float) -> None:
    _require("SSLKEYLOGFILE" not in os.environ)
    _require(sys.platform == "darwin" and os.name == "posix" and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE)
    _require(type(head) is str and re.fullmatch(r"[0-9a-f]{40}", head) is not None)
    helpers.require_sha256(caller, "caller hash")
    for args, expected in ((["rev-parse", "--show-toplevel"], str(ROOT)),
            (["branch", "--show-current"], BRANCH), (["rev-parse", "HEAD"], head),
            (["status", "--porcelain"], "")):
        result = subprocess.run(["git", *args], cwd=ROOT, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=min(3, helpers._remaining(deadline)), check=False)
        _require(result.returncode == 0 and not result.stderr and result.stdout.decode("utf-8").strip() == expected)
    for relative, digest in SOURCE_PINS.items():
        _require(helpers._source_digest(ROOT / relative) == digest)
    _require(helpers._source_digest(SOURCE) == caller)
    capture._require_dirfd_support()
    helpers._remaining(deadline)


# Stateless, caller-supplied dirfd/name/value only; no A control path is used.
_write_held = contract._write_held


def _check_held(directory, name, fd, identity):
    _require(helpers._identity(helpers._file_metadata(fd)) == identity)
    helpers._named_file(directory, name, fd)
    capture._require_reopened_artifact_identity(CONTROL, directory)


def _claim(head, caller):
    capture._require_operational_artifact_scope(CONTROL)
    _, parent = capture._open_directory_path(CONTROL.parent, create=True, name="remaining connection parent")
    directory = claim = None
    try:
        os.mkdir(CONTROL.name, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = capture._open_private_child_directory(parent, CONTROL.name, "remaining connection claim")
        claim, _, identity = _write_held(directory, "claim.json", {"schema": SCHEMA,
            "profile_sha256": PROFILE_SHA256, "expected_head": head, "caller_sha256": caller,
            "claimed_at": helpers._utc_now(), "parent_pid": os.getpid(), "attempt_consumed": True})
        capture._require_pinned_child_identity(parent, CONTROL.name, directory, "remaining connection claim")
        return directory, claim, identity
    except BaseException:
        for fd in (claim, directory):
            if fd is not None:
                os.close(fd)
        raise
    finally:
        os.close(parent)


def _observe(directory, claim, identity, deadline, result):
    _check_held(directory, "claim.json", claim, identity)
    marker, _, _ = _write_held(directory, "observation-started.json", {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256})
    os.close(marker)
    adapter = key = None
    provider = None
    try:
        adapter = contract._new_adapter()
        for index, endpoint in enumerate(ENDPOINTS):
            row = result["observations"][index]
            response = None
            try:
                helpers._remaining(deadline)
                row["terminal"] = "control_refused"
                _check_held(directory, "claim.json", claim, identity)
                contract._check_transport_logging()
                if provider != endpoint.provider:
                    provider, key = endpoint.provider, None
                    row["terminal"] = "credentials_unavailable"
                    try:
                        key = credentials.load_key(provider, timeout_seconds=min(20, helpers._remaining(deadline)))
                    except credentials.KeychainUnavailable:
                        pass
                if key is None:
                    row["terminal"] = "credentials_unavailable"
                    continue
                row["terminal"] = "request_preparation_refused"
                request, url = contract._prepare(endpoint, key)
                row["terminal"] = "control_refused"
                _check_held(directory, "claim.json", claim, identity)
                row["terminal"] = result["terminal"] = "send_intent_ambiguous"
                marker, _, _ = _write_held(directory, f"send-{index + 1}-started.json", {
                    "schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "provider": endpoint.provider,
                    "role": endpoint.role, "endpoint_path": endpoint.path})
                os.close(marker)
                row["send_intent_recorded"] = True
                result["send_attempt_count"] += 1
                row["terminal"] = "control_refused"
                contract._check_transport_logging()
                row["terminal"] = "transport_failure"
                response = adapter.send(request, stream=True, verify=True, cert=None, proxies={},
                    timeout=min(15, helpers._remaining(deadline)))
                row["terminal"] = "response_binding_refused"
                _require(response.request is request and response.url == url)
                contract._validate_request(request, endpoint, key, url)
                row["terminal"] = "invalid_status"
                code = response.status_code
                _require(type(code) is int and 100 <= code <= 599)
                row["status_code"] = code
                if code != 200:
                    row["terminal"] = "http_status"
                else:
                    row["terminal"] = "body_refused"
                    payload = contract._body_bytes(response, endpoint, deadline)
                    row["terminal"] = "schema_refused"
                    try:
                        count, fields = contract._schema(endpoint, payload, key)
                    except contract.Refusal as error:
                        if error.args == ("credential_echo_refused",):
                            row["terminal"] = "credential_echo_refused"
                        raise
                    finally:
                        payload = None
                    row.update(row_count=count, fields_available=fields,
                        terminal="valid_nonempty" if count else "valid_empty")
            except helpers.Deadline:
                row["terminal"] = result["terminal"] = "deadline_timeout"
                return
            except (KeyboardInterrupt, SystemExit):
                row["terminal"] = result["terminal"] = "cancelled"
                return
            except BaseException:
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
        result["terminal"] = "all_connections_responded" if all(row["terminal"] in _SUCCESS
            for row in result["observations"]) else "completed_with_failures"
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


def _validate(claim, result, head, caller, actual_exit):
    helpers._exact(claim, _CLAIM_KEYS)
    helpers._exact(result, _REPORT_KEYS)
    _require(type(head) is str and re.fullmatch(r"[0-9a-f]{40}", head) is not None)
    helpers.require_sha256(caller, "caller hash")
    _require(type(actual_exit) is int and actual_exit in (0, 2))
    for value in (claim, result):
        _require(value["schema"] == SCHEMA and value["profile_sha256"] == PROFILE_SHA256
            and value["expected_head"] == head and value["caller_sha256"] == caller and value["attempt_consumed"] is True)
    _require(type(claim["parent_pid"]) is int and claim["parent_pid"] > 0)
    _require(helpers.parse_utc_timestamp(result["parent_started_at"], "start")
        <= helpers.parse_utc_timestamp(claim["claimed_at"], "claim")
        <= helpers.parse_utc_timestamp(result["parent_observed_terminal_at"], "end"))
    for name in ("capture_accepted", "backtest_ready", "point_in_time_proven", "paper_look_committed"):
        _require(result[name] is False)
    for name in ("qc_calls", "outcome_reads"):
        _require(type(result[name]) is int and result[name] == 0)
    _require(result["provider_request_count"] is None)
    terminal, rows = result["terminal"], result["observations"]
    _require(type(terminal) is str and terminal in _TERMINALS)
    _require(type(rows) is list and len(rows) == 6)
    _require(type(result["send_attempt_count"]) is int and 0 <= result["send_attempt_count"] <= 6)
    intents = 0
    unfinished = False
    for row, endpoint in zip(rows, ENDPOINTS, strict=True):
        helpers._exact(row, {"provider", "role", "endpoint_path", "status_code", "send_intent_recorded",
            "terminal", "row_count", "fields_available"})
        _require((row["provider"], row["role"], row["endpoint_path"]) == (endpoint.provider, endpoint.role, endpoint.path))
        _require(type(row["send_intent_recorded"]) is bool and type(row["terminal"]) is str and row["terminal"] in _ROW_TERMINALS)
        status, count = row["status_code"], row["row_count"]
        _require(status is None or type(status) is int and 100 <= status <= 599)
        helpers._exact(row["fields_available"], set(endpoint.fields))
        _require(all(type(flag) is bool for flag in row["fields_available"].values()))
        if unfinished:
            _require(row["terminal"] == "not_attempted")
        if row["terminal"] == "not_attempted":
            unfinished = True
        if status is not None:
            _require(row["send_intent_recorded"])
        if row["terminal"] in _SUCCESS:
            _require(status == 200 and type(count) is int and 0 <= count <= contract._row_limit(endpoint))
            _require((count > 0) == (row["terminal"] == "valid_nonempty"))
        else:
            _require(count is None or row["terminal"] in {"close_refused", "deadline_timeout", "cancelled"}
                and status == 200 and type(count) is int and 0 <= count <= contract._row_limit(endpoint))
        if count is None or count == 0:
            _require(not any(row["fields_available"].values()))
        else:
            _require(all(row["fields_available"][field] is True for field in contract._required_fields(endpoint)))
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
    elif terminal == "completed_with_failures":
        _require(not all_ok and not unfinished)
    complete = terminal == "all_connections_responded" and actual_exit == 0
    _require(actual_exit != 0 or complete)
    return {"schema": OUTPUT_SCHEMA, "output_authenticated": True, "connections_responded": complete,
        "actual_parent_exit": actual_exit, "terminal": terminal, "attempt_consumed": True, "observations": rows,
        "send_attempt_count": intents, "provider_request_count": None, "profile_sha256": PROFILE_SHA256,
        "capture_accepted": False, "point_in_time_proven": False, "backtest_ready": False,
        "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0}


def _run(head, caller, deadline):
    directory = claim = report_fd = None
    consumption = False
    result = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "expected_head": head,
        "caller_sha256": caller, "parent_started_at": helpers._utc_now(), "parent_observed_terminal_at": None,
        "terminal": "control_refused", "attempt_consumed": True, "observations": [contract._row(e) for e in ENDPOINTS],
        "send_attempt_count": 0, "provider_request_count": None, "capture_accepted": False,
        "backtest_ready": False, "point_in_time_proven": False, "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0}
    try:
        _preflight(head, caller, deadline)
        consumption = None
        directory, claim, identity = _claim(head, caller)
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
        code = 0 if result["terminal"] == "all_connections_responded" else 2
        _validate(helpers._read_channel(claim), result, head, caller, code)
        report_fd, payload, report_identity = _write_held(directory, "report.json", result)
        _check_held(directory, "report.json", report_fd, report_identity)
        _check_held(directory, "claim.json", claim, identity)
        helpers._remaining(deadline)
        print(canonical_json_bytes({"terminal": result["terminal"], "profile_sha256": PROFILE_SHA256,
            "report_sha256": hashlib.sha256(payload).hexdigest(), "report_bytes": len(payload),
            "send_attempt_count": result["send_attempt_count"], "provider_request_count": None}).decode())
        return code
    except BaseException:
        print('{"terminal":"publication_ambiguous","provider_request_count":null}')
        return 2
    finally:
        for fd in (report_fd, claim, directory):
            if fd is not None:
                os.close(fd)


def run(head, caller):
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        with helpers._alarm(deadline):
            return _run(head, caller, deadline)
    except BaseException:
        print('{"terminal":"parent_ambiguous","provider_request_count":null}')
        return 2


def _read_leaf(directory, name, stack):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    stack.callback(os.close, fd)
    identity = helpers._identity(helpers._file_metadata(fd))
    helpers._named_file(directory, name, fd)
    payload = os.pread(fd, MAX_BYTES + 1, 0)
    _require(len(payload) == identity[6] and 0 < len(payload) <= MAX_BYTES)
    _check_held(directory, name, fd, identity)
    return payload, fd, identity


def read_output(head, caller, report_sha256, report_bytes, actual_exit):
    deadline = time.monotonic() + READER_SECONDS
    with helpers._alarm(deadline):
        _require(type(report_bytes) is int and 0 < report_bytes <= MAX_BYTES)
        _require(type(actual_exit) is int and actual_exit in (0, 2))
        helpers.require_sha256(report_sha256, "external report hash")
        _preflight(head, caller, deadline)
        with ExitStack() as stack:
            _, directory = capture._open_directory_path(CONTROL, create=False, name="remaining connection output")
            stack.callback(os.close, directory)
            payload, report_fd, report_identity = _read_leaf(directory, "report.json", stack)
            _require(len(payload) == report_bytes and hashlib.sha256(payload).hexdigest() == report_sha256)
            claim_payload, claim_fd, claim_identity = _read_leaf(directory, "claim.json", stack)
            summary = _validate(helpers._decode(claim_payload), helpers._decode(payload), head, caller, actual_exit)
            _check_held(directory, "report.json", report_fd, report_identity)
            _check_held(directory, "claim.json", claim_fd, claim_identity)
            summary.update(report_sha256=report_sha256, report_bytes=report_bytes,
                claim_sha256=hashlib.sha256(claim_payload).hexdigest(), claim_bytes=len(claim_payload))
            helpers._remaining(deadline)
            return summary


def main(argv=None):
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
