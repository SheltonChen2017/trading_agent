"""One-use R295 HTTP-status observation, not capture or source admission.

Requires a separately committed exact run decision. Review waivers, when any,
are external owner decisions, never command-line authorization switches.
Only first-page response status is inspected; no body, pagination or retry.
``send_attempt_count`` counts acknowledged dispatch-intent boundaries, not
packets, confirmed requests, or a census of all persisted markers. A failed
marker write can leave evidence despite no acknowledgement or send; that is
``send_intent_ambiguous``. Interruption between acknowledgement/send is unknown.
The native-network-denied ``--read-output`` mode reads only this claim/report.
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
from types import MappingProxyType, SimpleNamespace
from urllib.parse import urlencode

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_massive_oct12_diagnostic as helpers

capture = helpers.capture
canonical_json_bytes = helpers.canonical_json_bytes
BRANCH = "codex/strategy-analyst-revisions-v2"
PYTHON = Path("/Users/sheltonchen/.venvs/trading_agent-py313/bin/python")
SOURCE = ROOT / "scripts/run_arv2_massive_http_status_diagnostic.py"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/massive_diagnostic/R295-20261013-A"
SCHEMA = "arv2-massive-http-status-diagnostic-v1"
OUTPUT_SCHEMA = "arv2-massive-http-status-output-v1"
EVENT_DATE = "2026-10-12"
DEADLINE_SECONDS = 60
READER_SECONDS = 30
REQUEST_SECONDS = 15
REQUESTS_VERSION = "2.34.2"
MAX_BYTES = 16 * 1024
SOURCE_PINS = MappingProxyType({**helpers.SOURCE_PINS,
    "scripts/run_arv2_massive_oct12_diagnostic.py":
        "137743f30acd78aafb768114446f2b20cecec0bbac12fdc995233accf2911860",
})
ROLE_PATHS = tuple((role.value, capture.ENDPOINT_PATHS[role]) for role in capture.ROLE_ORDER)
QUERY = MappingProxyType({"date.gte": EVENT_DATE, "date.lte": EVENT_DATE,
                         "limit": "1", "sort": "date.asc"})
PROFILE = canonical_json_bytes({
    "schema": SCHEMA, "purpose": "first_page_http_status_observation_not_acquisition",
    "root": str(ROOT), "branch": BRANCH, "python": str(PYTHON),
    "host": "darwin-posix-python3.13", "control": str(CONTROL),
    "role_paths": [list(row) for row in ROLE_PATHS], "query": dict(QUERY),
    "transport": "owned_requests_httpadapter_send_no_session",
    "requests_version": REQUESTS_VERSION, "ssl_key_log_environment": "refuse_if_present",
    "stream": True, "tls_verify": True, "proxies": {}, "retries": 0,
    "redirects": False, "maximum_send_intents": 3, "stop_first_non200": True,
    "parent_deadline_seconds": DEADLINE_SECONDS, "request_timeout_seconds": REQUEST_SECONDS,
    "reader_deadline_seconds": READER_SECONDS, "maximum_output_bytes": MAX_BYTES,
    "source_pins": dict(SOURCE_PINS), "provider_request_count": None,
    "point_in_time_proven": False, "capture_accepted": False,
    "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0,
    "separate_run_freeze_required": True, "independent_review_required": True,
})
PROFILE_SHA256 = hashlib.sha256(PROFILE).hexdigest()
_TERMINALS = frozenset({"all_statuses_200", "http_status", "invalid_status",
    "transport_failure", "response_binding_refused", "request_preparation_refused",
    "credentials_unavailable", "close_refused", "deadline_timeout", "control_refused",
    "send_intent_ambiguous"})
_ROW_TERMINALS = _TERMINALS - {"all_statuses_200", "credentials_unavailable"} | {"status_200"}
_CLAIM_KEYS = {"schema", "profile_sha256", "expected_head", "caller_sha256",
               "claimed_at", "parent_pid", "attempt_consumed"}
_REPORT_KEYS = {"schema", "profile_sha256", "expected_head", "caller_sha256",
    "parent_started_at", "parent_observed_terminal_at", "terminal", "attempt_consumed",
    "observations", "send_attempt_count", "provider_request_count", "capture_accepted",
    "point_in_time_proven", "paper_look_committed", "qc_calls", "outcome_reads"}


class Refusal(ValueError):
    pass


def _require(condition: bool) -> None:
    if not condition:
        raise Refusal("control_refused")


def _preflight(expected_head: str, caller_sha256: str, deadline: float) -> None:
    # Presence alone refuses: never display a credential-bearing TLS-log path
    # or silently change the operator's environment/security configuration.
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
        capture._write_all(fd, payload, "status diagnostic")
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
    _, parent = capture._open_directory_path(CONTROL.parent, create=True, name="status parent")
    directory = claim = None
    try:
        os.mkdir(CONTROL.name, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = capture._open_private_child_directory(parent, CONTROL.name, "status claim")
        value = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
            "expected_head": expected_head, "caller_sha256": caller_sha256,
            "claimed_at": helpers._utc_now(), "parent_pid": os.getpid(), "attempt_consumed": True}
        claim, _, identity = _write_held(directory, "claim.json", value)
        capture._require_pinned_child_identity(parent, CONTROL.name, directory, "status claim")
        return directory, claim, identity
    except BaseException:
        for fd in (claim, directory):
            if fd is not None:
                os.close(fd)
        raise
    finally:
        os.close(parent)


def _new_adapter():
    import requests
    # No Session: even allow_redirects=False Session.send can prefetch a
    # redirect body for Response.next. Direct HTTPAdapter never follows it.
    _require(requests.__version__ == REQUESTS_VERSION)
    return requests.adapters.HTTPAdapter(max_retries=0)


def _prepare(role, key: str):
    import requests
    url = capture.BASE_URL + capture.ENDPOINT_PATHS[role] + "?" + urlencode(QUERY)
    prepared = requests.Request("GET", url, headers={"Authorization": "Bearer " + key}).prepare()
    _validate_request(prepared, role, key, url)
    return prepared, url


def _validate_request(prepared, role, key: str, expected_url: str) -> None:
    _require(prepared.method == "GET" and prepared.body is None)
    _require(dict(prepared.headers) == {"Authorization": "Bearer " + key})
    _require(prepared.hooks == {"response": []})
    capture._validate_prepared_request(SimpleNamespace(request=prepared, url=prepared.url),
        expected_url=expected_url, source_role=role)


def _observe(directory: int, claim: int, identity: tuple, deadline: float, result: dict) -> None:
    _check_held(directory, "claim.json", claim, identity)
    # A direct duplicate dispatch cannot reuse the already claimed process.
    marker, _, _ = _write_held(directory, "observation-started.json",
        {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256})
    os.close(marker)
    result["terminal"] = "credentials_unavailable"
    helpers._remaining(deadline)
    key = capture._api_key()
    adapter = None
    try:
        result["terminal"] = "control_refused"
        adapter = _new_adapter()
        for index, role in enumerate(capture.ROLE_ORDER):
            row = {"role": role.value, "endpoint_path": capture.ENDPOINT_PATHS[role],
                   "status_code": None, "send_intent_recorded": False,
                   "terminal": "request_preparation_refused"}
            result["observations"].append(row)
            result["terminal"] = row["terminal"]
            response = None
            try:
                helpers._remaining(deadline)
                prepared, url = _prepare(role, key)
                _check_held(directory, "claim.json", claim, identity)
                row["terminal"] = result["terminal"] = "send_intent_ambiguous"
                intent, _, _ = _write_held(directory, f"send-{index + 1}-started.json",
                    {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
                     "role": role.value, "endpoint_path": capture.ENDPOINT_PATHS[role]})
                os.close(intent)
                # Acknowledged conservative dispatch boundary, not wire count
                # or a census of partially written markers.
                row["send_intent_recorded"] = True
                result["send_attempt_count"] += 1
                row["terminal"] = result["terminal"] = "transport_failure"
                response = adapter.send(prepared, stream=True, verify=True, cert=None,
                    proxies={}, timeout=min(REQUEST_SECONDS, helpers._remaining(deadline)))
                row["terminal"] = result["terminal"] = "response_binding_refused"
                _require(response.request is prepared)
                _validate_request(prepared, role, key, url)
                capture._validate_prepared_request(response, expected_url=url, source_role=role)
                row["terminal"] = result["terminal"] = "invalid_status"
                status = response.status_code
                _require(type(status) is int and 100 <= status <= 599)
                row["status_code"] = status
                row["terminal"] = "status_200" if status == 200 else "http_status"
                result["terminal"] = row["terminal"] if status != 200 else "control_refused"
            except helpers.Deadline:
                row["terminal"] = result["terminal"] = "deadline_timeout"
            except BaseException:
                # Keep only the finite stage already recorded, never exception args.
                result["terminal"] = row["terminal"]
            finally:
                if response is not None:
                    try:
                        response.close()  # Never content/text/json/raw/headers/history/next.
                    except helpers.Deadline:
                        row["terminal"] = result["terminal"] = "deadline_timeout"
                    except BaseException:
                        row["terminal"] = result["terminal"] = "close_refused"
            if row["terminal"] != "status_200":
                return
        result["terminal"] = "all_statuses_200"
    finally:
        key = None
        if adapter is not None:
            try:
                adapter.close()
            except helpers.Deadline:
                result["terminal"] = "deadline_timeout"
            except BaseException:
                result["terminal"] = "close_refused"


def _validate(claim: dict, result: dict, expected_head: str, caller_sha256: str, actual_exit: int) -> dict:
    helpers._exact(claim, _CLAIM_KEYS)
    helpers._exact(result, _REPORT_KEYS)
    _require(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head) is not None)
    helpers.require_sha256(caller_sha256, "caller hash")
    _require(type(actual_exit) is int and actual_exit in (0, 2))
    for record in (claim, result):
        _require(record["schema"] == SCHEMA and record["profile_sha256"] == PROFILE_SHA256
            and record["expected_head"] == expected_head and record["caller_sha256"] == caller_sha256
            and record["attempt_consumed"] is True)
    _require(type(claim["parent_pid"]) is int and claim["parent_pid"] > 0)
    _require(helpers.parse_utc_timestamp(result["parent_started_at"], "start")
        <= helpers.parse_utc_timestamp(claim["claimed_at"], "claim")
        <= helpers.parse_utc_timestamp(result["parent_observed_terminal_at"], "end"))
    _require(result["provider_request_count"] is None)
    for name in ("capture_accepted", "point_in_time_proven", "paper_look_committed"):
        _require(result[name] is False)
    for name in ("qc_calls", "outcome_reads"):
        _require(type(result[name]) is int and result[name] == 0)
    terminal = result["terminal"]
    _require(type(terminal) is str and terminal in _TERMINALS)
    rows = result["observations"]
    _require(type(rows) is list and len(rows) <= 3)
    _require(type(result["send_attempt_count"]) is int and 0 <= result["send_attempt_count"] <= 3)
    intents = 0
    for index, row in enumerate(rows):
        helpers._exact(row, {"role", "endpoint_path", "status_code", "send_intent_recorded", "terminal"})
        _require((row["role"], row["endpoint_path"]) == ROLE_PATHS[index])
        _require(type(row["send_intent_recorded"]) is bool)
        _require(type(row["terminal"]) is str and row["terminal"] in _ROW_TERMINALS)
        status = row["status_code"]
        _require(status is None or type(status) is int and 100 <= status <= 599)
        if status is not None:
            _require(row["send_intent_recorded"])
        if row["terminal"] in {"status_200", "http_status"}:
            _require(type(status) is int and (status == 200) == (row["terminal"] == "status_200"))
        if row["terminal"] in {"request_preparation_refused", "transport_failure", "response_binding_refused", "invalid_status"}:
            _require(status is None)
        if row["terminal"] in {"transport_failure", "response_binding_refused", "invalid_status"}:
            _require(row["send_intent_recorded"])
        if row["terminal"] == "request_preparation_refused":
            _require(not row["send_intent_recorded"])
        if row["terminal"] == "send_intent_ambiguous":
            _require(not row["send_intent_recorded"] and status is None)
        if index < len(rows) - 1:
            _require(row["terminal"] == "status_200")
        intents += int(row["send_intent_recorded"])
    _require(intents == result["send_attempt_count"])
    if terminal == "all_statuses_200":
        _require(len(rows) == 3 and all(row["terminal"] == "status_200" for row in rows))
    elif terminal == "credentials_unavailable":
        _require(not rows)
    elif terminal not in {"control_refused", "deadline_timeout", "close_refused"}:
        _require(bool(rows) and rows[-1]["terminal"] == terminal)
    complete = terminal == "all_statuses_200" and actual_exit == 0
    _require(actual_exit != 0 or complete)
    return {"schema": OUTPUT_SCHEMA, "output_authenticated": True,
        "diagnostic_complete": complete, "actual_parent_exit": actual_exit,
        "terminal": terminal, "attempt_consumed": True, "observations": rows,
        "send_attempt_count": intents, "provider_request_count": None,
        "profile_sha256": PROFILE_SHA256, "capture_accepted": False,
        "point_in_time_proven": False, "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0}


def _run(expected_head: str, caller_sha256: str, deadline: float) -> int:
    directory = claim = report_fd = None
    consumption = False
    result = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256,
        "expected_head": expected_head, "caller_sha256": caller_sha256,
        "parent_started_at": helpers._utc_now(), "parent_observed_terminal_at": None,
        "terminal": "control_refused", "attempt_consumed": True,
        "observations": [], "send_attempt_count": 0, "provider_request_count": None,
        "capture_accepted": False, "point_in_time_proven": False, "paper_look_committed": False,
        "qc_calls": 0, "outcome_reads": 0}
    try:
        _preflight(expected_head, caller_sha256, deadline)
        consumption = None
        directory, claim, identity = _claim(expected_head, caller_sha256)
        consumption = True
        _observe(directory, claim, identity, deadline, result)
    except (helpers.Deadline, subprocess.TimeoutExpired):
        result["terminal"] = "deadline_timeout"
    except BaseException:
        pass  # Finite current stage only, never raw exception output.
    try:
        helpers._remaining(deadline)
        if directory is None:
            print(canonical_json_bytes({"terminal": "claim_ambiguous" if consumption is None else "preclaim_refusal",
                "attempt_consumed": consumption, "provider_request_count": None}).decode())
            return 2
        _check_held(directory, "claim.json", claim, identity)
        result["parent_observed_terminal_at"] = helpers._utc_now()
        exit_code = 0 if result["terminal"] == "all_statuses_200" else 2
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
        # Covers preflight, credential, TLS/header observation, close and output;
        # cannot bound uninterruptible kernel I/O or host suspension.
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
    # Native network denial is externally required for this once-only mode.
    deadline = time.monotonic() + READER_SECONDS
    with helpers._alarm(deadline):
        _require(type(report_bytes) is int and 0 < report_bytes <= MAX_BYTES)
        _require(type(actual_exit) is int and actual_exit in (0, 2))
        helpers.require_sha256(report_sha256, "external report hash")
        _preflight(expected_head, caller_sha256, deadline)
        with ExitStack() as stack:
            _, directory = capture._open_directory_path(CONTROL, create=False, name="status output")
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
            return 0 if value["diagnostic_complete"] else 2
        except BaseException:
            print('{"terminal":"output_refused","output_authenticated":false}')
            return 2
    if any(value is not None for value in (args.report_sha256, args.report_bytes, args.actual_parent_exit)):
        print('{"terminal":"arguments_refused","provider_request_count":null}')
        return 2
    return run(args.expected_head, args.caller_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
