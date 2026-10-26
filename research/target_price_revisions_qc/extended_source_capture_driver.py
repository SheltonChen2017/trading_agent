"""Committed one-shot invoker for the exact fresh extended source capture.

No resume, alternate directories, credential arguments or transport adapters.
The owner digest binds a declaration; contextual authority is in the lane record.
Preparation failures leave any partial directory untouched and do not prove that
scope is spent or that no request occurred. CLI output is closed count metadata.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import stat
import subprocess
from types import FunctionType

from research.target_price_revisions_qc import extended_source_capture as capture

LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions")
LANE_BRANCH = "codex/strategy-target-price-revisions"
SOURCE_RELATIVE = "research/target_price_revisions_qc/extended_source_capture_driver.py"
DRIVER_PLAN_NAME = capture.OPERATION_ID + ".driver-plan.json"
DRIVER_RECEIPT_NAME = capture.OPERATION_ID + ".driver-preparation.json"
PUBLIC_KEYS = capture.PUBLIC_KEYS | {"preparation_may_exist"}


class DriverError(ValueError):
    """Closed invoker refusal, never provider/row/credential content."""


def _fail(message):
    raise DriverError(message)


def _now():
    return datetime.now(timezone.utc)


def _execution_paths():
    current = Path.cwd()
    return current, current.resolve()


def _git_head():
    current, physical = _execution_paths()
    if current != LANE_ROOT or physical != LANE_ROOT:
        _fail("capture driver requires exact physical lane")
    try:
        commands = (["git", "rev-parse", "--show-toplevel"], ["git", "branch", "--show-current"],
                    ["git", "rev-parse", "HEAD"], ["git", "status", "--short"])
        observed = [subprocess.run(command, cwd=LANE_ROOT, capture_output=True, timeout=5,
                    check=True).stdout.decode("utf-8").strip() for command in commands]
        if observed[:2] != [str(LANE_ROOT), LANE_BRANCH]:
            _fail("capture driver Git lane mismatch")
        capture.probe._hash(observed[2], 40)
        return observed[2]
    except (OSError, UnicodeError, subprocess.SubprocessError, capture.probe.ProbeError):
        _fail("capture driver Git custody unavailable")


def _verify_imports():
    if (Path(__file__) != LANE_ROOT / SOURCE_RELATIVE or capture.LANE_ROOT != LANE_ROOT
            or capture.LANE_BRANCH != LANE_BRANCH
            or capture.PRIVATE_ROOT != LANE_ROOT / "artifacts" / "target_price_extended" / capture.STUDY_ID / "source_capture"
            or Path(capture.__file__) != LANE_ROOT / capture.SOURCE_RELATIVE):
        _fail("capture driver imported module identity refused")
    for function in (capture.freeze_capture_plan, capture.execute_capture, capture._verify_execution_identity):
        if type(function) is not FunctionType or Path(function.__code__.co_filename) != LANE_ROOT / capture.SOURCE_RELATIVE:
            _fail("capture driver imported function identity refused")
    capture._verify_imports()


def _bound_inventory(git_sha):
    hashes = {}
    try:
        for relative in capture.SOURCE_PATHS:
            if _git_head() != git_sha:
                _fail("capture driver HEAD advanced during source verification")
            payload = capture._read_source(relative)
            observed = capture.probe._digest(payload)
            committed = subprocess.run(["git", "show", git_sha + ":" + relative],
                cwd=LANE_ROOT, capture_output=True, timeout=5, check=True).stdout
            if type(committed) is not bytes or len(committed) > 262144 or capture.probe._digest(committed) != observed:
                _fail("capture driver source is not exact committed closure")
            hashes[relative] = observed
        if any(hashes[key] != value for key, value in capture.PUBLIC_HASHES.items()):
            _fail("capture driver public freeze identity refused")
        if _git_head() != git_sha:
            _fail("capture driver HEAD advanced during source verification")
        return hashes
    except (OSError, subprocess.SubprocessError, capture.probe.ProbeError):
        _fail("capture driver committed source custody unavailable")


def _create_private_directory():
    descriptor = None
    try:
        descriptor = capture._open_directory(LANE_ROOT)
        for component in ("artifacts", "target_price_extended", capture.STUDY_ID):
            try:
                os.mkdir(component, 0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            metadata = os.fstat(child)
            if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or component != "artifacts" and stat.S_IMODE(metadata.st_mode) != 0o700):
                os.close(child)
                _fail("capture driver private parent custody refused")
            os.close(descriptor)
            descriptor = child
        try:
            os.mkdir("source_capture", 0o700, dir_fd=descriptor)
        except FileExistsError:
            _fail("capture driver refuses any previously prepared leaf")
        child = os.open("source_capture", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
        metadata = os.fstat(child)
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700):
            os.close(child)
            _fail("capture driver private leaf custody refused")
        os.close(descriptor)
        descriptor = None
        return child
    except (OSError, capture.probe.ProbeError):
        _fail("capture driver preparation unavailable; preserve partial root")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _safe_result(result):
    if (type(result) is not capture.CaptureResult or type(result.payload) is not bytes
            or not 0 < len(result.payload) <= 32768
            or capture.probe._digest(result.payload) != result.sha256
            or result.index_path != capture.PRIVATE_ROOT / capture.INDEX_NAME):
        _fail("capture driver result identity refused")
    report = capture.helper._source_object(result.payload)
    if (set(report) != capture.PUBLIC_KEYS or report.get("schema") != "tpr-extended-source-capture-report-v1"
            or report.get("operation_id") != capture.OPERATION_ID or report.get("study_id") != capture.STUDY_ID
            or report.get("status") not in ("COMPLETED", "FAILED", "INTERRUPTED")
            or report.get("scope_spent") is not True):
        _fail("capture driver result schema refused")
    maxima = {"reserved_requests": 2240, "attempted_requests": 2240, "successful_requests": 2240,
              "response_bytes": 4 * 1024**3, "source_rows": 3968000,
              "row_refusals": 3968000, "identical_duplicate_rows": 3968000,
              "conflicting_duplicate_rows": 3968000, "terminated_massive_windows": 74,
              "terminated_sharadar_datasets": 2}
    for key, maximum in maxima.items():
        if type(report[key]) is not int or not 0 <= report[key] <= maximum:
            _fail("capture driver result counts refused")
    if not report["successful_requests"] <= report["attempted_requests"] <= report["reserved_requests"]:
        _fail("capture driver result request coherence refused")
    complete = report["status"] == "COMPLETED" and report["terminated_massive_windows"] == 74 and report["terminated_sharadar_datasets"] == 2
    if type(report["capture_complete"]) is not bool or report["capture_complete"] != complete:
        _fail("capture driver result completeness refused")
    for key in ("source_input_admitted", "point_in_time_data", "rights_verified", "canonical_admission", "trading"):
        if report[key] is not False:
            _fail("capture driver result authority refused")
    for key in ("outcome_reads", "development_looks", "quantconnect_attempts"):
        if type(report[key]) is not int or report[key] != 0:
            _fail("capture driver result authority refused")
    return {**report, "preparation_may_exist": True}


def run_capture(*, owner_instruction_sha256, created_utc, expires_utc):
    _verify_imports()
    git_sha = _git_head()
    source_hashes = _bound_inventory(git_sha)
    plan = capture.freeze_capture_plan(source_hashes=source_hashes, git_sha=git_sha,
        owner_instruction_sha256=owner_instruction_sha256, created_utc=created_utc, expires_utc=expires_utc)
    body, now = plan.body(), _now()
    if (type(now) is not datetime or now.tzinfo is None or now.utcoffset() != timedelta(0)
            or not capture.probe._clock(body["created_utc"]) <= now < capture.probe._clock(body["expires_utc"])):
        _fail("capture driver outside frozen clock")
    capture._verify_execution_identity(body)
    if _git_head() != git_sha:
        _fail("capture driver HEAD advanced before private preparation")
    directory = _create_private_directory()
    try:
        capture._publish(directory, DRIVER_PLAN_NAME, body)
        capture._publish(directory, DRIVER_RECEIPT_NAME,
            {"schema": "tpr-extended-capture-driver-preparation-v1", "operation_id": capture.OPERATION_ID,
             "study_id": capture.STUDY_ID, "git_sha": git_sha, "plan_sha256": plan.sha256,
             "owner_instruction_sha256": owner_instruction_sha256, "source_hashes": source_hashes,
             "status": "not_yet_invoked_by_driver", "prepared_utc": now.isoformat()})
    finally:
        os.close(directory)
    if _git_head() != git_sha:
        _fail("capture driver HEAD advanced before access")
    return _safe_result(capture.execute_capture(plan))


def _unknown_status(status):
    report = {key: None for key in capture.PUBLIC_KEYS}
    report.update(schema="tpr-extended-source-capture-report-v1", operation_id=capture.OPERATION_ID,
        study_id=capture.STUDY_ID, status=status, capture_complete=False, source_input_admitted=False,
        point_in_time_data=False, rights_verified=False, outcome_reads=0, development_looks=0,
        quantconnect_attempts=0, canonical_admission=False, trading=False)
    return {**report, "preparation_may_exist": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Exact fresh one-shot private TPR extended source capture")
    parser.add_argument("--owner-instruction-sha256", required=True)
    parser.add_argument("--created-utc", required=True)
    parser.add_argument("--expires-utc", required=True)
    args = parser.parse_args(argv)
    try:
        report = run_capture(owner_instruction_sha256=args.owner_instruction_sha256,
                             created_utc=args.created_utc, expires_utc=args.expires_utc)
    except KeyboardInterrupt:
        report = _unknown_status("INTERRUPTED_UNKNOWN")
    except Exception:
        report = _unknown_status("REFUSED_OR_FAILED_UNKNOWN")
    if set(report) != PUBLIC_KEYS:
        report = _unknown_status("REFUSED_OR_FAILED_UNKNOWN")
    print(capture._canonical(report).decode("ascii"), end="")
    return 0 if report["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
