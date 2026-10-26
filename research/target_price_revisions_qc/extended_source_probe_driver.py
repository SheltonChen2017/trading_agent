"""Committed one-shot invoker for the exact extended-study source probe.

Invoke with ``python -m research.target_price_revisions_qc.extended_source_probe_driver``
and explicit owner-instruction SHA256 / UTC creation and expiry clocks. The
digest binds the caller's declaration; it does not itself prove ownership.
There is no resume, alternate root, credential argument or injected transport.
Partially prepared directories are preserved, never silently retried/deleted.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import stat
import subprocess
from types import FunctionType

from research.target_price_revisions_qc import extended_source_probe as probe

LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__target_price_revisions")
LANE_BRANCH = "codex/strategy-target-price-revisions"
SOURCE_RELATIVE = "research/target_price_revisions_qc/extended_source_probe_driver.py"
SOURCE_PATHS = (SOURCE_RELATIVE, probe.SOURCE_RELATIVE, probe.FREEZE_RELATIVE,
                *probe.HELPER_PATHS)
DRIVER_PLAN_NAME = probe.OPERATION_ID + ".driver-plan.json"
DRIVER_RECEIPT_NAME = probe.OPERATION_ID + ".driver-preparation.json"
PUBLIC_KEYS = frozenset({"schema", "operation_id", "study_id", "status", "reserved_requests",
    "attempted_requests", "successful_sample_responses", "sampled_rows", "response_bytes",
    "scope_spent", "samples_only", "complete_history", "point_in_time_data", "rights_verified",
    "full_capture_admitted", "outcome_reads", "development_looks", "quantconnect_attempts",
    "canonical_admission", "trading", "preparation_may_exist"})


class DriverError(ValueError):
    """Closed invoker refusal without local, provider or credential details."""


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
        _fail("probe driver requires exact physical lane")
    try:
        commands = (["git", "rev-parse", "--show-toplevel"],
                    ["git", "branch", "--show-current"], ["git", "rev-parse", "HEAD"],
                    ["git", "status", "--short"])
        observed = [subprocess.run(command, cwd=LANE_ROOT, capture_output=True,
            timeout=5, check=True).stdout.decode("utf-8").strip() for command in commands]
        if observed[:2] != [str(LANE_ROOT), LANE_BRANCH]:
            _fail("probe driver Git lane mismatch")
        probe._hash(observed[2], 40)
        return observed[2]
    except (OSError, UnicodeError, subprocess.SubprocessError, probe.ProbeError):
        _fail("probe driver Git custody unavailable")


def _verify_imports():
    if (Path(__file__) != LANE_ROOT / SOURCE_RELATIVE
            or probe.LANE_ROOT != LANE_ROOT or probe.LANE_BRANCH != LANE_BRANCH
            or probe.PRIVATE_ROOT != LANE_ROOT / "artifacts" / "target_price_extended"
                / probe.STUDY_ID / "source_probe"
            or Path(probe.__file__) != LANE_ROOT / probe.SOURCE_RELATIVE
            or Path(probe.helper.__file__) != LANE_ROOT / "research/target_price_revisions_development/source_audit.py"):
        _fail("probe driver imported module identity refused")
    for function, relative in ((probe.execute_probe, probe.SOURCE_RELATIVE),
        (probe.freeze_probe_plan, probe.SOURCE_RELATIVE),
        (probe._read_source, probe.SOURCE_RELATIVE),
        (probe.helper._production_credential, "research/target_price_revisions_development/source_audit.py")):
        if type(function) is not FunctionType or Path(function.__code__.co_filename) != LANE_ROOT / relative:
            _fail("probe driver imported function identity refused")


def _bound_inventory(git_sha):
    """Read only the fixed source closure, and prove exact committed parity."""
    hashes = {}
    try:
        for relative in SOURCE_PATHS:
            if _git_head() != git_sha:
                _fail("probe driver HEAD advanced during preparation")
            current = probe._read_source(relative)
            current_hash = probe._digest(current)
            committed = subprocess.run(["git", "show", git_sha + ":" + relative],
                cwd=LANE_ROOT, capture_output=True, timeout=5, check=True).stdout
            if (type(committed) is not bytes or len(committed) > 262144
                    or probe._digest(committed) != current_hash):
                _fail("probe driver requires exact committed sources")
            hashes[relative] = current_hash
        if hashes[probe.FREEZE_RELATIVE] != probe.FREEZE_SHA256:
            _fail("probe driver frozen study mismatch")
        if _git_head() != git_sha:
            _fail("probe driver HEAD advanced during preparation")
        return hashes
    except (OSError, subprocess.SubprocessError, probe.ProbeError):
        _fail("probe driver source verification unavailable")


def _create_private_directory():
    """Create only the fixed fresh leaf, walking every parent without links."""
    descriptor = None
    try:
        descriptor = probe._open_directory(LANE_ROOT)
        for component in ("artifacts", "target_price_extended", probe.STUDY_ID):
            try:
                os.mkdir(component, 0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            metadata = os.fstat(child)
            if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or component != "artifacts" and stat.S_IMODE(metadata.st_mode) != 0o700):
                os.close(child)
                _fail("probe driver private parent custody refused")
            os.close(descriptor)
            descriptor = child
        # ANY existing leaf is a prior preparation, not a resumable permit.
        try:
            os.mkdir("source_probe", 0o700, dir_fd=descriptor)
        except FileExistsError:
            _fail("probe driver fresh leaf already exists; do not retry")
        child = os.open("source_probe", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=descriptor)
        metadata = os.fstat(child)
        if (metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700
                or not stat.S_ISDIR(metadata.st_mode)):
            os.close(child)
            _fail("probe driver fresh leaf custody refused")
        os.close(descriptor)
        descriptor = None
        return child
    except (OSError, probe.ProbeError):
        _fail("probe driver preparation unavailable; preserve partial root")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _status(*, status, report=None):
    unknown = report is None
    result = {"schema": "tpr-extended-probe-driver-status-v1",
        "operation_id": probe.OPERATION_ID, "study_id": probe.STUDY_ID, "status": status,
        "reserved_requests": None if unknown else report["reserved_requests"],
        "attempted_requests": None if unknown else report["attempted_requests"],
        "successful_sample_responses": None if unknown else report["successful_sample_responses"],
        "sampled_rows": None if unknown else report["sampled_rows"],
        "response_bytes": None if unknown else report["response_bytes"],
        "scope_spent": None if unknown else True,
        "samples_only": True, "complete_history": False, "point_in_time_data": False,
        "rights_verified": False, "full_capture_admitted": False, "outcome_reads": 0,
        "development_looks": 0, "quantconnect_attempts": 0, "canonical_admission": False,
        "trading": False, "preparation_may_exist": True}
    if set(result) != PUBLIC_KEYS:
        _fail("probe driver public schema refused")
    return result


def _safe_result(result):
    if (type(result) is not probe.ProbeResult or type(result.payload) is not bytes
            or len(result.payload) > 32768 or probe._digest(result.payload) != result.sha256):
        _fail("probe driver result identity refused")
    try:
        report = probe.helper._source_object(result.payload)
        if (report.get("schema") != "tpr-extended-source-probe-report-v1"
                or report.get("operation_id") != probe.OPERATION_ID
                or report.get("study_id") != probe.STUDY_ID
                or report.get("scope_spent") is not True
                or report.get("reserved_requests") != 7
                or type(report.get("reserved_requests")) is not int
                or type(report.get("all_requests_succeeded")) is not bool
                or type(report.get("interrupted")) is not bool):
            _fail("probe driver result schema refused")
        for key, maximum in (("attempted_requests", 7), ("successful_sample_responses", 7),
                             ("sampled_rows", 7), ("response_bytes", 7 * probe.MAX_BYTES)):
            if type(report.get(key)) is not int or not 0 <= report[key] <= maximum:
                _fail("probe driver result count refused")
        for key in ("complete_history", "point_in_time_data", "rights_verified", "full_capture_admitted",
                    "canonical_admission", "trading"):
            if report.get(key) is not False:
                _fail("probe driver result authority refused")
        for key in ("outcome_reads", "development_looks", "quantconnect_attempts"):
            if type(report.get(key)) is not int or report[key] != 0:
                _fail("probe driver result authority refused")
        if (report.get("samples_only") is not True
                or report["sampled_rows"] > report["successful_sample_responses"]
                or report["successful_sample_responses"] > report["attempted_requests"]
                or report["all_requests_succeeded"] != (report["successful_sample_responses"] == 7)):
            _fail("probe driver result count coherence refused")
        status = "INTERRUPTED" if report["interrupted"] else "COMPLETED" if report["all_requests_succeeded"] else "FAILED"
        return _status(status=status, report=report)
    except probe.helper.SourceAuditError:
        _fail("probe driver result parsing refused")


@dataclass(frozen=True)
class DriverResult:
    payload: bytes
    sha256: str


def run_probe(*, owner_instruction_sha256, created_utc, expires_utc):
    """Prepare and execute once; no injected root, clocks, secrets or adapters."""
    _verify_imports()
    git_sha = _git_head()
    source_hashes = _bound_inventory(git_sha)
    plan = probe.freeze_probe_plan(code_sha256=source_hashes[probe.SOURCE_RELATIVE],
        helper_hashes={path: source_hashes[path] for path in probe.HELPER_PATHS},
        git_sha=git_sha, owner_instruction_sha256=owner_instruction_sha256,
        created_utc=created_utc, expires_utc=expires_utc)
    body = plan.body()
    now = _now()
    if (type(now) is not datetime or now.tzinfo is None or now.utcoffset() != timedelta(0)
            or not probe._clock(body["created_utc"]) <= now < probe._clock(body["expires_utc"])):
        _fail("probe driver plan outside allowed clock")
    # Complete probe custody is checked while the private leaf still does not
    # exist. This is not an access claim, nor evidence of a later HTTP result.
    probe._verify_execution_identity(body)
    if _git_head() != git_sha:
        _fail("probe driver HEAD advanced before preparation")
    directory = _create_private_directory()
    try:
        probe._publish(directory, DRIVER_PLAN_NAME, body)
        probe._publish(directory, DRIVER_RECEIPT_NAME,
            {"schema": "tpr-extended-probe-driver-preparation-v1",
             "operation_id": probe.OPERATION_ID, "study_id": probe.STUDY_ID,
             "git_sha": git_sha, "plan_sha256": plan.sha256,
             "owner_instruction_sha256": owner_instruction_sha256,
             "driver_sha256": source_hashes[SOURCE_RELATIVE],
             "source_hashes": source_hashes, "prepared_utc": now.isoformat(),
             "provider_operation_stage": "not_yet_invoked_by_driver",
             "preparation_is_access_claim": False,
             "partial_preparation_must_not_be_retried_by_implication": True})
    finally:
        os.close(directory)
    # The public probe repeats current/committed custody, spends all claims,
    # and only then resolves credentials. Failure leaves preparation intact.
    result = probe.execute_probe(plan)
    payload = probe._canonical(_safe_result(result))
    return DriverResult(payload, probe._digest(payload))


def main(argv=None):
    class ClosedParser(argparse.ArgumentParser):
        def error(self, message):
            _fail("probe driver explicit arguments refused")
    parser = ClosedParser(description="Execute the exact one-shot extended TPR availability probe.")
    parser.add_argument("--owner-instruction-sha256", required=True)
    parser.add_argument("--created-utc", required=True)
    parser.add_argument("--expires-utc", required=True)
    try:
        arguments = parser.parse_args(argv)
        result = run_probe(owner_instruction_sha256=arguments.owner_instruction_sha256,
                           created_utc=arguments.created_utc, expires_utc=arguments.expires_utc)
        print(result.payload.decode("ascii"), end="")
        status = probe.helper._source_object(result.payload)["status"]
        return 0 if status == "COMPLETED" else 1
    except KeyboardInterrupt:
        print(probe._canonical(_status(status="INTERRUPTED")).decode("ascii"), end="")
        return 130
    except (DriverError, probe.ProbeError):
        # A preparation refusal does not establish whether a prior caller
        # consumed this root or an interrupted launch reached HTTP.
        print(probe._canonical(_status(status="REFUSED")).decode("ascii"), end="")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
