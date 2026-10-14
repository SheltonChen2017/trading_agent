"""Committed one-shot CLI for the exact fresh Sharadar-only repair.

No resume, alternate directory, credential arguments, provider adapter or
Massive route. Original failed source artifacts are never opened or changed.
Source custody is checked before private preparation and again before access.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import stat
import subprocess
from types import FunctionType

from research.target_price_revisions_qc import extended_sharadar_repair as repair

LANE_ROOT, LANE_BRANCH = repair.LANE_ROOT, repair.LANE_BRANCH
SOURCE_RELATIVE = repair.DRIVER_RELATIVE
PUBLIC_KEYS = repair.PUBLIC_KEYS | {"preparation_may_exist"}


class DriverError(ValueError):
    """Closed invoker refusal, without credentials, rows or native errors."""


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
        _fail("repair driver requires exact physical lane")
    try:
        commands = (["git", "rev-parse", "--show-toplevel"], ["git", "branch", "--show-current"],
                    ["git", "rev-parse", "HEAD"], ["git", "status", "--short"])
        observed = [subprocess.run(command, cwd=LANE_ROOT, capture_output=True, timeout=5,
                    check=True).stdout.decode("utf-8").strip() for command in commands]
        if observed[:2] != [str(LANE_ROOT), LANE_BRANCH]:
            _fail("repair driver Git lane mismatch")
        return repair.capture.probe._hash(observed[2], 40)
    except (OSError, UnicodeError, subprocess.SubprocessError, ValueError):
        _fail("repair driver Git custody unavailable")


def _verify_imports():
    if (Path(__file__) != LANE_ROOT / SOURCE_RELATIVE or repair.LANE_ROOT != LANE_ROOT
            or repair.LANE_BRANCH != LANE_BRANCH
            or repair.PRIVATE_ROOT != LANE_ROOT / "artifacts" / "target_price_extended" / repair.STUDY_ID / "sharadar_repair"
            or Path(repair.__file__) != LANE_ROOT / repair.SOURCE_RELATIVE):
        _fail("repair driver imported module identity refused")
    for function in (repair.freeze_repair_plan, repair.execute_repair, repair._verify_execution_identity):
        if type(function) is not FunctionType or Path(function.__code__.co_filename) != LANE_ROOT / repair.SOURCE_RELATIVE:
            _fail("repair driver imported function identity refused")
    repair._verify_imports()


def _bound_inventory(git_sha):
    hashes = {}
    try:
        for relative in repair.SOURCE_PATHS:
            if _git_head() != git_sha:
                _fail("repair driver HEAD advanced during source verification")
            payload = repair.capture._read_source(relative)
            digest = repair.capture.probe._digest(payload)
            committed = subprocess.run(["git", "show", git_sha + ":" + relative], cwd=LANE_ROOT,
                capture_output=True, timeout=5, check=True).stdout
            if type(committed) is not bytes or len(committed) > 262144 or repair.capture.probe._digest(committed) != digest:
                _fail("repair driver source not exact committed closure")
            hashes[relative] = digest
        if any(hashes[key] != value for key, value in repair.PUBLIC_HASHES.items()):
            _fail("repair driver public freeze/probe/calendar refused")
        if _git_head() != git_sha:
            _fail("repair driver HEAD advanced after source verification")
        return hashes
    except (OSError, subprocess.SubprocessError, ValueError):
        _fail("repair driver committed source custody unavailable")


def _create_private_directory():
    descriptor = None
    try:
        descriptor = repair.capture._open_directory(LANE_ROOT)
        for component in ("artifacts", "target_price_extended", repair.STUDY_ID):
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            metadata = os.fstat(child)
            if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or component != "artifacts" and stat.S_IMODE(metadata.st_mode) != 0o700):
                os.close(child)
                _fail("repair driver private parent custody refused")
            os.close(descriptor)
            descriptor = child
        try:
            os.mkdir("sharadar_repair", 0o700, dir_fd=descriptor)
        except FileExistsError:
            _fail("repair driver refuses any previously prepared leaf")
        child = os.open("sharadar_repair", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
        metadata = os.fstat(child)
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700):
            os.close(child)
            _fail("repair driver private leaf custody refused")
        return child
    except (OSError, ValueError):
        _fail("repair driver preparation unavailable; preserve partial root")
    finally:
        if descriptor is not None: os.close(descriptor)


def _safe_result(result):
    if (type(result) is not repair.RepairResult or type(result.payload) is not bytes
            or not 0 < len(result.payload) <= 32768 or repair.capture.probe._digest(result.payload) != result.sha256
            or result.index_path != repair.PRIVATE_ROOT / repair.INDEX_NAME):
        _fail("repair driver result identity refused")
    report = repair.capture.helper._source_object(result.payload)
    if (set(report) != repair.PUBLIC_KEYS or report["schema"] != "tpr-ext26-sharadar-repair-report-v1"
            or report["operation_id"] != repair.OPERATION_ID or report["study_id"] != repair.STUDY_ID
            or report["freeze_sha256"] != repair.FREEZE_SHA256
            or report["status"] not in ("COMPLETED", "FAILED", "INTERRUPTED") or report["scope_spent"] is not True):
        _fail("repair driver result schema refused")
    for key, maximum in (("reserved_requests", 192), ("attempted_requests", 192), ("successful_requests", 192),
            ("response_bytes", repair.LIMITS["max_response_bytes"]), ("source_rows", 1920000),
            ("row_refusals", 1920000), ("identical_duplicate_rows", 1920000), ("conflicting_duplicate_rows", 1920000),
            ("ticker_python_lexical_descents", 640000), ("terminated_sharadar_datasets", 2)):
        if type(report[key]) is not int or not 0 <= report[key] <= maximum:
            _fail("repair driver result count bound refused")
    if not report["successful_requests"] <= report["attempted_requests"] <= report["reserved_requests"]:
        _fail("repair driver request accounting refused")
    complete = report["status"] == "COMPLETED" and report["terminated_sharadar_datasets"] == 2
    if type(report["capture_complete"]) is not bool or report["capture_complete"] != complete:
        _fail("repair driver completed count coherence refused")
    for key in ("source_input_admitted", "point_in_time_data", "rights_verified", "canonical_admission", "trading"):
        if report[key] is not False:
            _fail("repair driver result authority refused")
    for key in ("outcome_reads", "development_looks", "quantconnect_attempts"):
        if type(report[key]) is not int or report[key] != 0:
            _fail("repair driver empirical scope refused")
    return {**report, "preparation_may_exist": True}


def run_repair(*, owner_instruction_sha256, created_utc, expires_utc):
    _verify_imports()
    git_sha = _git_head()
    inventory = _bound_inventory(git_sha)
    plan = repair.freeze_repair_plan(source_hashes=inventory, git_sha=git_sha,
        owner_instruction_sha256=owner_instruction_sha256, created_utc=created_utc, expires_utc=expires_utc)
    body, current = plan.body(), _now()
    if (type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0)
            or not repair.capture.probe._clock(body["created_utc"]) <= current < repair.capture.probe._clock(body["expires_utc"])):
        _fail("repair driver outside frozen clock")
    repair._verify_execution_identity(body)
    if _git_head() != git_sha:
        _fail("repair driver HEAD advanced before preparation")
    directory = _create_private_directory()
    try:
        repair.capture.helper._publish(directory, repair.OPERATION_ID + ".driver-plan.json", plan.payload)
        repair.capture._publish(directory, repair.OPERATION_ID + ".driver-preparation.json", {
            "schema": "tpr-ext26-sharadar-repair-driver-v1", "operation_id": repair.OPERATION_ID,
            "study_id": repair.STUDY_ID, "plan_sha256": plan.sha256, "git_sha": git_sha,
            "source_hashes": inventory, "owner_instruction_sha256": owner_instruction_sha256,
            "prepared_utc": current.isoformat(), "status": "not_yet_invoked_by_driver"})
    finally:
        os.close(directory)
    if _git_head() != git_sha:
        _fail("repair driver HEAD advanced before access")
    return _safe_result(repair.execute_repair(plan))


def _unknown_status(status):
    report = {key: None for key in repair.PUBLIC_KEYS}
    report.update(schema="tpr-ext26-sharadar-repair-report-v1", operation_id=repair.OPERATION_ID,
        study_id=repair.STUDY_ID, freeze_sha256=repair.FREEZE_SHA256, status=status,
        capture_complete=False, source_input_admitted=False, point_in_time_data=False, rights_verified=False,
        outcome_reads=0, development_looks=0, quantconnect_attempts=0, canonical_admission=False, trading=False)
    return {**report, "preparation_may_exist": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Exact one-shot fresh Sharadar-only TPR repair")
    parser.add_argument("--owner-instruction-sha256", required=True)
    parser.add_argument("--created-utc", required=True)
    parser.add_argument("--expires-utc", required=True)
    arguments = parser.parse_args(argv)
    try:
        report = run_repair(**vars(arguments))
    except KeyboardInterrupt:
        report = _unknown_status("INTERRUPTED_UNKNOWN")
    except Exception:
        report = _unknown_status("REFUSED_OR_FAILED_UNKNOWN")
    print(repair._canonical(report).decode("ascii"), end="")
    return 0 if report["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
