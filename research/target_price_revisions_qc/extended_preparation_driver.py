"""Committed one-shot invoker for the explicit composite-v2 private preparation.

No resume, directory override, row arguments, credentials, provider adapter or
QC launch. A declaration hash records scoped owner authority, not attestation.
The fixed source closure must already be committed before the new private leaf
is created. CLI output contains only the closed count/hash result.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import stat
import subprocess
from types import FunctionType

from research.target_price_revisions_qc import extended_preparation as preparation

LANE_ROOT, LANE_BRANCH = preparation.LANE_ROOT, preparation.LANE_BRANCH
SOURCE_RELATIVE = preparation.DRIVER_RELATIVE


class DriverError(ValueError):
    """Closed invoker refusal; no licensed rows or private exceptions escape."""


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
        _fail("preparation driver requires exact physical lane")
    try:
        commands = (["git", "rev-parse", "--show-toplevel"], ["git", "branch", "--show-current"],
                    ["git", "rev-parse", "HEAD"], ["git", "status", "--short"])
        observed = [subprocess.run(command, cwd=LANE_ROOT, capture_output=True, timeout=5,
                    check=True).stdout.decode("utf-8").strip() for command in commands]
        if observed[:2] != [str(LANE_ROOT), LANE_BRANCH]:
            _fail("preparation driver Git lane mismatch")
        return preparation._hash(observed[2], 40)
    except (OSError, UnicodeError, subprocess.SubprocessError, ValueError):
        _fail("preparation driver Git custody unavailable")


def _verify_imports():
    if (Path(__file__) != LANE_ROOT / SOURCE_RELATIVE or preparation.LANE_ROOT != LANE_ROOT
            or preparation.LANE_BRANCH != LANE_BRANCH
            or preparation.PRIVATE_ROOT != LANE_ROOT / "artifacts" / "target_price_extended" / preparation.STUDY_ID / "inputs"
            or Path(preparation.__file__) != LANE_ROOT / preparation.SOURCE_RELATIVE):
        _fail("preparation driver imported module identity refused")
    for function in (preparation.freeze_preparation_plan, preparation.execute_preparation,
                     preparation._verify_execution_identity):
        if type(function) is not FunctionType or Path(function.__code__.co_filename) != LANE_ROOT / preparation.SOURCE_RELATIVE:
            _fail("preparation driver imported function identity refused")
    preparation._verify_imports()


def _bound_inventory(git_sha):
    hashes = {}
    try:
        for relative in preparation.SOURCE_PATHS:
            if _git_head() != git_sha:
                _fail("preparation driver HEAD advanced during source verification")
            payload = preparation.capture._read_source(relative)
            observed = preparation._sha(payload)
            committed = subprocess.run(["git", "show", git_sha + ":" + relative], cwd=LANE_ROOT,
                capture_output=True, timeout=5, check=True).stdout
            if type(committed) is not bytes or len(committed) > 262144 or preparation._sha(committed) != observed:
                _fail("preparation driver source not exact committed closure")
            hashes[relative] = observed
        if any(hashes[key] != value for key, value in preparation.repair.PUBLIC_HASHES.items()):
            _fail("preparation driver public freeze/probe/calendar refused")
        if _git_head() != git_sha:
            _fail("preparation driver HEAD advanced after source verification")
        return hashes
    except (OSError, subprocess.SubprocessError, ValueError):
        _fail("preparation driver source custody unavailable")


def _create_private_directory():
    descriptor = None
    try:
        descriptor = preparation.capture._open_directory(LANE_ROOT)
        for component in ("artifacts", "target_price_extended", preparation.STUDY_ID):
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            metadata = os.fstat(child)
            if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or component != "artifacts" and stat.S_IMODE(metadata.st_mode) != 0o700):
                os.close(child)
                _fail("preparation driver private parent custody refused")
            os.close(descriptor)
            descriptor = child
        try:
            os.mkdir("inputs", 0o700, dir_fd=descriptor)
        except FileExistsError:
            _fail("preparation driver refuses any previously prepared leaf")
        child = os.open("inputs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
        metadata = os.fstat(child)
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700):
            os.close(child)
            _fail("preparation driver private leaf custody refused")
        return child
    except (OSError, ValueError):
        _fail("preparation driver preparation unavailable; preserve partial root")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _safe_result(result):
    if (type(result) is not preparation.PreparationResult or type(result.payload) is not bytes
            or not 0 < len(result.payload) <= 32768 or preparation._sha(result.payload) != result.sha256):
        _fail("preparation driver result identity refused")
    report = preparation._object(result.payload)
    if (set(report) != preparation.PUBLIC_KEYS or report["schema"] != "tpr-ext26-preparation-result-v1"
            or report["study_id"] != preparation.STUDY_ID or report["operation_id"] != preparation.OPERATION_ID
            or report["status"] not in ("COMPLETED", "FAILED", "INTERRUPTED") or report["scope_spent"] is not True):
        _fail("preparation driver result schema refused")
    for key, maximum in (("payload_count", 256), ("payload_bytes", preparation.LIMITS["max_payload_bytes"]),
            ("identity_count", 100000), ("decision_count", 301), ("monthly_shards", 74),
            ("source_rows", preparation.LIMITS["max_source_rows"])):
        if type(report[key]) is not int or not 0 <= report[key] <= maximum:
            _fail("preparation driver result counts refused")
    for key in ("point_in_time_data", "rights_verified", "canonical_admission", "trading"):
        if report[key] is not False:
            _fail("preparation driver result authority refused")
    for key in ("outcome_reads", "development_looks", "quantconnect_attempts"):
        if type(report[key]) is not int or report[key] != 0:
            _fail("preparation driver result empirical scope refused")
    census = report["source_refusal_census"]
    if type(census) is not dict or set(census) != {"massive", "sharadar"}:
        _fail("preparation driver source-refusal providers refused")
    for categories in census.values():
        if categories is not None and (type(categories) is not dict or set(categories) != preparation.SEMANTIC_KEYS
                or any(type(value) is not int or not 0 <= value <= preparation.LIMITS["max_source_rows"]
                       for value in categories.values())):
            _fail("preparation driver source-refusal closed counts refused")
    if report["status"] == "COMPLETED":
        preparation._hash(report["preparation_sha256"])
        preparation._hash(report["manifest_sha256"])
        if (report["source_input_prepared"] is not True or report["decision_count"] != 301
                or any(value is None for value in census.values())
                or report["identity_count"] < 1 or report["monthly_shards"] != 70
                or report["payload_count"] != report["monthly_shards"] + 2 or report["payload_bytes"] <= 0):
            _fail("preparation driver completed result coherence refused")
    elif (report["source_input_prepared"] is not False or report["preparation_sha256"] is not None
            or report["manifest_sha256"] is not None):
        _fail("preparation driver failed result coherence refused")
    return report


def run_preparation(*, owner_instruction_sha256, created_utc, expires_utc,
                    capture_index_sha256, capture_plan_sha256, capture_report_sha256,
                    capture_git_sha, repair_index_sha256, repair_plan_sha256, repair_report_sha256,
                    repair_git_sha):
    _verify_imports()
    git_sha = _git_head()
    inventory = _bound_inventory(git_sha)
    plan = preparation.freeze_preparation_plan(source_hashes=inventory, git_sha=git_sha,
        owner_instruction_sha256=owner_instruction_sha256, created_utc=created_utc, expires_utc=expires_utc,
        capture_index_sha256=capture_index_sha256, capture_plan_sha256=capture_plan_sha256,
        capture_report_sha256=capture_report_sha256, capture_git_sha=capture_git_sha,
        repair_index_sha256=repair_index_sha256, repair_plan_sha256=repair_plan_sha256,
        repair_report_sha256=repair_report_sha256, repair_git_sha=repair_git_sha)
    body, current = plan.body(), _now()
    if (type(current) is not datetime or current.tzinfo is None or current.utcoffset() != timedelta(0)
            or not preparation._clock(body["created_utc"]) <= current < preparation._clock(body["expires_utc"])):
        _fail("preparation driver outside frozen clock")
    preparation._verify_execution_identity(body)
    if _git_head() != git_sha:
        _fail("preparation driver HEAD advanced before private preparation")
    directory = _create_private_directory()
    try:
        preparation.capture.helper._publish(directory, preparation.OPERATION_ID + ".driver-plan.json", plan.payload)
        preparation.capture._publish(directory, preparation.OPERATION_ID + ".driver-preparation.json", {
            "schema": "tpr-ext26-preparation-driver-v2", "operation_id": preparation.OPERATION_ID,
            "study_id": preparation.STUDY_ID, "plan_sha256": plan.sha256, "git_sha": git_sha,
            "source_hashes": inventory, "owner_instruction_sha256": owner_instruction_sha256,
            "prepared_utc": current.isoformat(), "status": "not_yet_invoked_by_driver"})
    finally:
        os.close(directory)
    if _git_head() != git_sha:
        _fail("preparation driver HEAD advanced before processing access")
    return _safe_result(preparation.execute_preparation(plan))


def _unknown_status(status):
    return {**preparation._report(status), "scope_spent": None}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Exact fresh single-use private TPR extended preparation")
    for option in ("owner-instruction-sha256", "created-utc", "expires-utc", "capture-index-sha256",
                   "capture-plan-sha256", "capture-report-sha256", "capture-git-sha",
                   "repair-index-sha256", "repair-plan-sha256", "repair-report-sha256", "repair-git-sha"):
        parser.add_argument("--" + option, required=True)
    arguments = parser.parse_args(argv)
    try:
        report = run_preparation(**vars(arguments))
    except KeyboardInterrupt:
        report = _unknown_status("INTERRUPTED_UNKNOWN")
    except Exception:
        report = _unknown_status("REFUSED_OR_FAILED_UNKNOWN")
    print(preparation._canonical(report).decode("ascii"), end="")
    return 0 if report["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
