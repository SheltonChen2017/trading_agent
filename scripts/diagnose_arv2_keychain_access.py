"""Once-only R296-B credential-stage observation; no provider calls.

Both operational modes require external native network denial and a separately
committed exact one-use decision. No old caller/reader/credential loader runs.
Only fixed categories and actual command return codes cross the boundary.
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
from scripts import arv2_keychain_connections as keymap
from scripts import run_arv2_massive_oct12_diagnostic as helpers

capture = helpers.capture
canonical_json_bytes = helpers.canonical_json_bytes
BRANCH = "codex/strategy-analyst-revisions-v2"
PYTHON = Path("/Users/sheltonchen/.venvs/trading_agent-py313/bin/python")
SOURCE = ROOT / "scripts/diagnose_arv2_keychain_access.py"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/provider_connections/R296-20261013-B"
SCHEMA = "arv2-keychain-access-diagnostic-v1"
OUTPUT_SCHEMA = "arv2-keychain-access-output-v1"
PROVIDERS = ("fmp", "massive", "eodhd")
DEADLINE_SECONDS = 200
KEY_SECONDS = 60
READER_SECONDS = 30
MAX_BYTES = 16384
SOURCE_PINS = MappingProxyType({**helpers.SOURCE_PINS,
    "scripts/run_arv2_massive_oct12_diagnostic.py":
        "137743f30acd78aafb768114446f2b20cecec0bbac12fdc995233accf2911860",
    "scripts/arv2_keychain_connections.py":
        "bd9c0863c484810b8cf7a02e46551ed63f99ecec7bb4f322b91270fad7a28227",
})
PROFILE = canonical_json_bytes({"schema": SCHEMA,
    "purpose": "credential_stage_cause_observation_after_owner_prompt_approval_no_provider",
    "root": str(ROOT), "branch": BRANCH, "python": str(PYTHON),
    "host": "darwin-posix-python3.13", "control": str(CONTROL),
    "keychain": keymap.KEYCHAIN,
    "services": {name: list(keymap.SERVICES[name]) for name in PROVIDERS},
    "provider_order": list(PROVIDERS), "security_command": "/usr/bin/security",
    "reads_per_provider": 1, "parent_deadline_seconds": DEADLINE_SECONDS,
    "keychain_timeout_seconds": KEY_SECONDS, "reader_deadline_seconds": READER_SECONDS,
    "maximum_output_bytes": MAX_BYTES, "accepted_key_shape_bytes": [8, 4096],
    "stdout_bound": "post_read_shape_only_not_pipe_memory_ceiling",
    "native_network_denial_required": True, "source_pins": dict(SOURCE_PINS),
    "provider_calls_dispatched": 0, "provider_request_count": None,
    "capture_accepted": False, "backtest_ready": False, "point_in_time_proven": False,
    "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0,
    "separate_run_freeze_required": True})
PROFILE_SHA256 = hashlib.sha256(PROFILE).hexdigest()
_OBSERVATIONS = frozenset({"not_attempted", "timed_out", "command_failed", "command_unavailable",
    "command_completed_valid_shape", "command_completed_invalid_shape", "control_refused",
    "read_intent_ambiguous", "deadline_timeout", "cancelled"})
_TERMINALS = frozenset({"all_credentials_valid_shape", "completed_with_failures", "control_refused",
    "read_intent_ambiguous", "deadline_timeout", "cancelled"})
_SHAPES = frozenset({"valid", "missing_final_lf", "short_or_long", "invalid_ascii", "invalid_output_type"})
_CLAIM_KEYS = {"schema", "profile_sha256", "expected_head", "caller_sha256", "claimed_at",
    "parent_pid", "attempt_consumed"}
_REPORT_KEYS = {"schema", "profile_sha256", "expected_head", "caller_sha256", "parent_started_at",
    "parent_observed_terminal_at", "terminal", "attempt_consumed", "observations", "read_attempt_count",
    "provider_calls_dispatched", "provider_request_count", "capture_accepted", "backtest_ready",
    "point_in_time_proven", "paper_look_committed", "qc_calls", "outcome_reads"}


class Refusal(ValueError):
    pass


def _require(condition: bool) -> None:
    if not condition:
        raise Refusal("control_refused")


def _preflight(expected_head: str, caller_sha256: str, deadline: float) -> None:
    _require(sys.platform == "darwin" and os.name == "posix" and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
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
        capture._write_all(fd, payload, "credential observation")
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
    _, parent = capture._open_directory_path(CONTROL.parent, create=True, name="keychain diagnostic parent")
    directory = claim = None
    try:
        os.mkdir(CONTROL.name, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = capture._open_private_child_directory(parent, CONTROL.name, "keychain diagnostic claim")
        claim, _, identity = _write_held(directory, "claim.json", {"schema": SCHEMA,
            "profile_sha256": PROFILE_SHA256, "expected_head": expected_head, "caller_sha256": caller_sha256,
            "claimed_at": helpers._utc_now(), "parent_pid": os.getpid(), "attempt_consumed": True})
        capture._require_pinned_child_identity(parent, CONTROL.name, directory, "keychain diagnostic claim")
        return directory, claim, identity
    except BaseException:
        for fd in (claim, directory):
            if fd is not None:
                os.close(fd)
        raise
    finally:
        os.close(parent)


def _shape(payload: object) -> str:
    if type(payload) is not bytes:
        return "invalid_output_type"
    if not payload.endswith(b"\n"):
        return "missing_final_lf"
    value = payload[:-1]
    if not 8 <= len(value) <= 4096:
        return "short_or_long"
    if any(item < 33 or item > 126 for item in value):
        return "invalid_ascii"
    return "valid"


def _observe_key(provider: str, deadline: float) -> tuple[str, int | None, str | None]:
    _require(provider in PROVIDERS)
    service, account = keymap.SERVICES[provider]
    completed = None
    try:
        completed = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", service,
            "-a", account, "-w", keymap.KEYCHAIN], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=min(KEY_SECONDS, helpers._remaining(deadline)), check=False)
        code = completed.returncode
        if type(code) is not int or not -255 <= code <= 255:
            return "command_unavailable", None, None
        if code != 0:
            return "command_failed", code, None
        shape = _shape(completed.stdout)
        return ("command_completed_valid_shape" if shape == "valid" else "command_completed_invalid_shape",
                0, shape)
    except subprocess.TimeoutExpired:
        # Timeout exception stdout may contain secrets; never format it.
        return "timed_out", None, None
    except (helpers.Deadline, KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        return "command_unavailable", None, None
    finally:
        completed = None  # Lifetime minimization, not a memory-erasure claim.


def _row(provider: str) -> dict:
    return {"provider": provider, "read_intent_recorded": False,
        "terminal": "not_attempted", "returncode": None, "shape_code": None}


def _observe(directory: int, claim: int, identity: tuple, deadline: float, result: dict) -> None:
    for index, provider in enumerate(PROVIDERS):
        row = result["observations"][index]
        try:
            helpers._remaining(deadline)
            row["terminal"] = "control_refused"
            _check_held(directory, "claim.json", claim, identity)
            row["terminal"] = result["terminal"] = "read_intent_ambiguous"
            marker, _, _ = _write_held(directory, f"read-{index + 1}-started.json", {
                "schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "provider": provider})
            os.close(marker)
            row["read_intent_recorded"] = True
            result["read_attempt_count"] += 1
            row["terminal"] = "command_unavailable"
            terminal, code, shape = _observe_key(provider, deadline)
            row.update(terminal=terminal, returncode=code, shape_code=shape)
        except helpers.Deadline:
            row["terminal"] = result["terminal"] = "deadline_timeout"
            return
        except (KeyboardInterrupt, SystemExit):
            row["terminal"] = result["terminal"] = "cancelled"
            return
        except BaseException:
            result["terminal"] = "read_intent_ambiguous" if row["terminal"] == "read_intent_ambiguous" else "control_refused"
            return
    result["terminal"] = "all_credentials_valid_shape" if all(row["terminal"] == "command_completed_valid_shape"
        for row in result["observations"]) else "completed_with_failures"


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
    for name in ("capture_accepted", "backtest_ready", "point_in_time_proven", "paper_look_committed"):
        _require(result[name] is False)
    for name in ("provider_calls_dispatched", "qc_calls", "outcome_reads"):
        _require(type(result[name]) is int and result[name] == 0)
    _require(result["provider_request_count"] is None)
    _require(type(result["terminal"]) is str and result["terminal"] in _TERMINALS)
    rows = result["observations"]
    _require(type(rows) is list and len(rows) == 3)
    _require(type(result["read_attempt_count"]) is int and 0 <= result["read_attempt_count"] <= 3)
    intents = 0
    stopped = False
    complete_states = {"timed_out", "command_failed", "command_unavailable",
        "command_completed_valid_shape", "command_completed_invalid_shape"}
    for provider, row in zip(PROVIDERS, rows, strict=True):
        helpers._exact(row, {"provider", "read_intent_recorded", "terminal", "returncode", "shape_code"})
        _require(row["provider"] == provider and type(row["read_intent_recorded"]) is bool)
        state = row["terminal"]
        _require(type(state) is str and state in _OBSERVATIONS)
        if stopped:
            _require(state == "not_attempted")
        if state not in complete_states:
            stopped = True
        code, shape = row["returncode"], row["shape_code"]
        _require(code is None or type(code) is int and -255 <= code <= 255)
        _require(shape is None or type(shape) is str and shape in _SHAPES)
        if state in complete_states:
            _require(row["read_intent_recorded"])
        if state in {"command_completed_valid_shape", "command_completed_invalid_shape"}:
            _require(code == 0 and type(code) is int and shape in _SHAPES
                and (shape == "valid") == (state == "command_completed_valid_shape"))
        elif state == "command_failed":
            _require(type(code) is int and code != 0 and shape is None)
        else:
            _require(code is None and shape is None)
        if state in {"not_attempted", "read_intent_ambiguous"}:
            _require(not row["read_intent_recorded"])
        intents += int(row["read_intent_recorded"])
    _require(intents == result["read_attempt_count"])
    all_valid = all(row["terminal"] == "command_completed_valid_shape" for row in rows)
    if result["terminal"] == "all_credentials_valid_shape":
        _require(all_valid)
    elif result["terminal"] == "completed_with_failures":
        _require(not all_valid and all(row["terminal"] in complete_states for row in rows))
    valid = result["terminal"] == "all_credentials_valid_shape" and actual_exit == 0
    _require(actual_exit != 0 or valid)
    return {"schema": OUTPUT_SCHEMA, "output_authenticated": True, "all_credentials_valid_shape": valid,
        "actual_parent_exit": actual_exit, "terminal": result["terminal"], "attempt_consumed": True,
        "observations": rows, "read_attempt_count": intents, "profile_sha256": PROFILE_SHA256,
        "provider_calls_dispatched": 0, "provider_request_count": None, "capture_accepted": False,
        "backtest_ready": False, "point_in_time_proven": False, "paper_look_committed": False,
        "qc_calls": 0, "outcome_reads": 0}


def _run(expected_head: str, caller_sha256: str, deadline: float) -> int:
    directory = claim = report_fd = None
    consumption = False
    result = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "expected_head": expected_head,
        "caller_sha256": caller_sha256, "parent_started_at": helpers._utc_now(),
        "parent_observed_terminal_at": None, "terminal": "control_refused", "attempt_consumed": True,
        "observations": [_row(provider) for provider in PROVIDERS], "read_attempt_count": 0,
        "provider_calls_dispatched": 0, "provider_request_count": None, "capture_accepted": False,
        "backtest_ready": False, "point_in_time_proven": False, "paper_look_committed": False,
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
                "attempt_consumed": consumption, "provider_calls_dispatched": 0}).decode())
            return 2
        _check_held(directory, "claim.json", claim, identity)
        result["parent_observed_terminal_at"] = helpers._utc_now()
        exit_code = 0 if result["terminal"] == "all_credentials_valid_shape" else 2
        _validate(helpers._read_channel(claim), result, expected_head, caller_sha256, exit_code)
        report_fd, payload, report_identity = _write_held(directory, "report.json", result)
        _check_held(directory, "report.json", report_fd, report_identity)
        _check_held(directory, "claim.json", claim, identity)
        helpers._remaining(deadline)
        print(canonical_json_bytes({"terminal": result["terminal"], "profile_sha256": PROFILE_SHA256,
            "report_sha256": hashlib.sha256(payload).hexdigest(), "report_bytes": len(payload),
            "read_attempt_count": result["read_attempt_count"], "provider_calls_dispatched": 0}).decode())
        return exit_code
    except BaseException:
        print('{"terminal":"publication_ambiguous","provider_calls_dispatched":0}')
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
        print('{"terminal":"parent_ambiguous","provider_calls_dispatched":0}')
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
            _, directory = capture._open_directory_path(CONTROL, create=False, name="keychain diagnostic output")
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
            return 0 if value["all_credentials_valid_shape"] else 2
        except BaseException:
            print('{"terminal":"output_refused","output_authenticated":false}')
            return 2
    if any(value is not None for value in (args.report_sha256, args.report_bytes, args.actual_parent_exit)):
        print('{"terminal":"arguments_refused","provider_calls_dispatched":0}')
        return 2
    return run(args.expected_head, args.caller_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
