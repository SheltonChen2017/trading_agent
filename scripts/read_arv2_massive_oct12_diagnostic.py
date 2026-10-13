"""Bounded offline reader of the sole R293 claim/report, never capture pages.

An actual parent exit supplied by the operator is an external observed fact,
not authenticated by this report. Exit zero AND validated accepted output are
required. A valid failure report provides finite evidence, not acceptance or
retry authority. Invoke only under the separately committed one-shot decision.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_arv2_massive_oct12_diagnostic as caller

CONTROL = caller.CONTROL
CALLER_SHA256 = "137743f30acd78aafb768114446f2b20cecec0bbac12fdc995233accf2911860"
PROFILE_SHA256 = "0d5d703f4696fae42d69ed3457c83e94d719d1a87155390b6cec278d80176ad1"
SCHEMA = "arv2-massive-oct12-diagnostic-output-v1"
_REPORT_KEYS = frozenset({
    "schema", "profile_sha256", "terminal", "attempt_consumed", "capture_observation",
    "binding", "parent_started_at", "parent_observed_terminal_at", "authentication",
    "provider_request_count", "point_in_time_proven", "paper_look_committed", "qc_calls", "outcome_reads",
})


def _require(condition: bool) -> None:
    if not condition:
        raise caller.Refusal("output_refused")


def _source_pins(expected_head: str, deadline: float) -> None:
    _require(caller.PROFILE_SHA256 == PROFILE_SHA256)
    # Pure local host/Git/public-source checks; this never dispatches a worker.
    caller._preflight(expected_head, CALLER_SHA256, deadline)


def _read_leaf(directory: int, name: str, stack: ExitStack) -> tuple[bytes, int, tuple]:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    stack.callback(os.close, fd)
    before = caller._identity(caller._file_metadata(fd))
    caller._named_file(directory, name, fd)
    payload, _ = caller.capture._read_and_pin_private_regular_at(
        directory, name, maximum_bytes=caller.MAX_CHANNEL, name="diagnostic output",
    )
    _require(len(payload) == before[6])
    _require(caller._identity(caller._file_metadata(fd)) == before)
    caller._named_file(directory, name, fd)
    return payload, fd, before


def _validate(claim: dict, report: dict, expected_head: str, actual_exit: int) -> dict:
    caller._exact(claim, {"schema", "profile_sha256", "expected_head", "caller_sha256",
                          "parent_pid", "deadline_monotonic_ns", "claimed_at", "attempt_consumed"})
    caller._exact(report, _REPORT_KEYS)
    _require(type(expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", expected_head) is not None)
    _require(type(actual_exit) is int and actual_exit in (0, 2))
    _require(claim["expected_head"] == expected_head and claim["caller_sha256"] == CALLER_SHA256)
    for value in (claim, report):
        _require(value["schema"] == caller.SCHEMA and value["profile_sha256"] == PROFILE_SHA256)
        _require(value["attempt_consumed"] is True)
    for key in ("parent_pid", "deadline_monotonic_ns"):
        _require(type(claim[key]) is int and claim[key] > 0)
    _require(report["provider_request_count"] is None)
    for key in ("point_in_time_proven", "paper_look_committed"):
        _require(report[key] is False)
    for key in ("qc_calls", "outcome_reads"):
        _require(type(report[key]) is int and report[key] == 0)
    started = caller.parse_utc_timestamp(report["parent_started_at"], "parent start")
    claimed = caller.parse_utc_timestamp(claim["claimed_at"], "claim")
    ended = caller.parse_utc_timestamp(report["parent_observed_terminal_at"], "terminal")
    _require(started <= claimed <= ended)
    terminal = report["terminal"]
    _require(type(terminal) is str and terminal in caller._TERMINALS and terminal != "claim_ambiguous")
    observed, binding, authenticated = (report[k] for k in ("capture_observation", "binding", "authentication"))
    if observed is not None:
        caller._exact(observed, {"capture_invoked", "producer_return_received", "terminal_state",
                                 "failure_code", "provider_request_count"})
        _require(observed["provider_request_count"] is None)
        observation = caller.CaptureObservation(**{k: v for k, v in observed.items() if k != "provider_request_count"})
        _require(observation.capture_invoked)
    if binding is not None:
        caller._require_binding(binding)
        _require(observed is not None and observed["producer_return_received"] is True)
        _require(claimed <= caller.parse_utc_timestamp(binding["capture_started_at"], "capture start")
                 <= caller.parse_utc_timestamp(binding["capture_completed_at"], "capture end") <= ended)
    if authenticated is not None:
        _require(binding is not None)
        caller._require_authentication(authenticated, binding)
        _require(terminal in {"accepted", "worker_timeout"})
    if terminal == "accepted":
        _require(authenticated is not None)
    elif terminal == "producer_raised":
        _require(observed is not None and observed["terminal_state"] == "producer_raised")
        _require(binding is None and authenticated is None)
    elif terminal == "authentication_refused":
        _require(binding is not None and authenticated is None)
    elif terminal == "invalid_producer_return":
        _require(observed is not None and observed["producer_return_received"] is True)
        _require(binding is None and authenticated is None)
    accepted = terminal == "accepted" and actual_exit == 0
    _require(actual_exit != 0 or accepted)
    summary = {"schema": SCHEMA, "output_authenticated": True, "accepted": accepted,
               "terminal": terminal, "actual_parent_exit": actual_exit, "attempt_consumed": True,
               "failure_code": None if observed is None else observed["failure_code"],
               "provider_request_count": None, "point_in_time_proven": False,
               "paper_look_committed": False, "qc_calls": 0, "outcome_reads": 0,
               "profile_sha256": PROFILE_SHA256}
    if accepted:
        summary.update(first_event_date=caller.EVENT_DATE, last_event_date=caller.EVENT_DATE,
                       capture_sha256=binding["capture_sha256"], manifest_sha256=binding["manifest_sha256"],
                       receipt_sha256=authenticated["receipt_sha256"],
                       source_row_count=binding["total_row_count"], page_count=binding["total_page_count"],
                       capture_started_at=binding["capture_started_at"], capture_completed_at=binding["capture_completed_at"],
                       role_row_counts=binding["role_row_counts"])
    return summary


def _read_output(expected_head: str, report_sha256: str, report_bytes: int, actual_exit: int, deadline: float) -> dict:
    """Only fixed claim/report leaf bytes are read; never allocate or repair."""
    _require(Path.cwd() == ROOT and ROOT.resolve() == ROOT)
    _require(type(report_bytes) is int and 0 < report_bytes <= caller.MAX_CHANNEL)
    caller.require_sha256(report_sha256, "external report pin")
    _source_pins(expected_head, deadline)
    with ExitStack() as stack:
        _, directory = caller.capture._open_directory_path(CONTROL, create=False, name="diagnostic output")
        stack.callback(os.close, directory)
        payload, report_fd, report_identity = _read_leaf(directory, "report.json", stack)
        _require(len(payload) == report_bytes and hashlib.sha256(payload).hexdigest() == report_sha256)
        claim_payload, claim_fd, claim_identity = _read_leaf(directory, "claim.json", stack)
        summary = _validate(caller._decode(claim_payload), caller._decode(payload), expected_head, actual_exit)
        for name, fd, identity in (("report.json", report_fd, report_identity), ("claim.json", claim_fd, claim_identity)):
            _require(caller._identity(caller._file_metadata(fd)) == identity)
            caller._named_file(directory, name, fd)
        caller.capture._require_reopened_artifact_identity(CONTROL, directory)
        summary.update(report_sha256=report_sha256, report_bytes=report_bytes,
                       claim_sha256=hashlib.sha256(claim_payload).hexdigest(), claim_bytes=len(claim_payload))
        return summary


def read_output(expected_head: str, report_sha256: str, report_bytes: int, actual_exit: int) -> dict:
    # Cooperative alarm cannot bound uninterruptible I/O or host suspension.
    deadline = time.monotonic() + 30
    with caller._alarm(deadline):
        result = _read_output(expected_head, report_sha256, report_bytes, actual_exit, deadline)
        caller._remaining(deadline)
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--report-bytes", required=True, type=int)
    parser.add_argument("--actual-parent-exit", required=True, type=int, choices=(0, 2))
    parsed = parser.parse_args(argv)
    try:
        summary = read_output(parsed.expected_head, parsed.report_sha256, parsed.report_bytes, parsed.actual_parent_exit)
        print(caller.canonical_json_bytes(summary).decode("utf-8"), end="")
        return 0 if summary["accepted"] else 2
    except BaseException:
        print('{"schema":"arv2-massive-oct12-diagnostic-output-v1","output_authenticated":false,"accepted":false,"terminal":"output_refused","provider_request_count":null}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
