"""One-use, offline R297 retained-byte diagnosis; never capture acceptance.

The separately frozen invocation must be launched under native network denial.
This calls only the unchanged offline authenticator after an exclusive new
claim. A returned authority is discarded without inspection or serialization.
Neither a diagnostic return nor its report replaces the original parent exit.
"""
from __future__ import annotations

import argparse
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
from scripts import capture_arv2_massive_ratings_delta as original

helpers, capture, delta = original.helpers, original.capture, original.delta
BRANCH, PYTHON = original.BRANCH, original.PYTHON
SOURCE = ROOT / "scripts/diagnose_arv2_r297_authentication.py"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/massive_ratings_delta/R297-20261013-D3"
CAPTURE_PATH = ROOT / "artifacts/analyst_revisions_v2/massive_ratings_delta/R297-20261013-A/capture"
MANIFEST_SHA256 = "2594cf2379c4a88c6ee53dc0ab3791235a01a4069f77505b7f98d560d8e9da00"
MANIFEST_BYTES, DEADLINE_SECONDS = 2628, 30
SCHEMA = "arv2-r297-retained-authentication-diagnostic-v1"
SOURCE_PINS = MappingProxyType({**original.SOURCE_PINS,
    "scripts/capture_arv2_massive_ratings_delta.py":
        "14936a7a1b493b28554eae0a9dbddfa07363d61fa9ce5d461580ae1b009ce818"})
KNOWN_CODES = frozenset("""
ancestor_changed artifact_inventory artifact_path authentication_failed
authority_changed authority_container authority_field_type authority_scalar
authority_type authority_unavailable capture_chronology clock_type clock_value
cursor_chain cursor_replay digest_type digest_value directory_final_changed
directory_preopen_changed duplicate_rating_provider_id extraction_mismatch
leaf_final_changed leaf_preopen_changed leaf_read_changed leaf_size leaf_size_changed
manifest_binding manifest_canonical manifest_digest_marker manifest_external_pin
manifest_inventory manifest_size manifest_totals normalization_context normalization_invalid
normalization_page normalization_row normalized_count operational_path page_binding
page_bytes page_chronology page_count page_external_pin page_inventory page_semantics
pages_type private_directory private_leaf readiness_flag response_replay
row_page_binding row_type terminal_chain terminal_flag page_number row_offset
page_limit attempted_count row_count raw_total rows_total page_order http_status
page_rows page_raw_bytes page_rows_bytes leaf_expected_size
""".split())
PROFILE = helpers.canonical_json_bytes({
    "schema": SCHEMA, "root": str(ROOT), "branch": BRANCH, "python": str(PYTHON),
    "control": str(CONTROL), "capture": str(CAPTURE_PATH),
    "manifest_sha256": MANIFEST_SHA256, "manifest_bytes": MANIFEST_BYTES,
    "source_pins": dict(SOURCE_PINS), "deadline_seconds": DEADLINE_SECONDS,
    "known_refusal_codes": sorted(KNOWN_CODES), "offline_authentication_calls": 1,
    "native_network_denial": "required_external_sandbox-exec_deny_network",
    "diagnostic_only": True, "original_capture_accepted": False,
    "changes_original_exit": False, "provider_contact_authorized": False,
    "point_in_time_proven": False, "backtest_ready": False, "paper_or_live_ready": False,
})
PROFILE_SHA256 = hashlib.sha256(PROFILE).hexdigest()


class DiagnosticRefusal(ValueError):
    pass


def _require(condition):
    if not condition:
        raise DiagnosticRefusal("diagnostic_refused")


def _preflight(head, caller, deadline):
    _require(sys.platform == "darwin" and os.name == "posix" and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE)
    _require(type(head) is str and re.fullmatch(r"[0-9a-f]{40}", head) is not None)
    helpers.require_sha256(caller, "caller")
    for args, expected in ((["rev-parse", "--show-toplevel"], str(ROOT)),
            (["branch", "--show-current"], BRANCH), (["rev-parse", "HEAD"], head),
            (["status", "--porcelain"], "")):
        result = subprocess.run(["git", *args], cwd=ROOT, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=min(3, helpers._remaining(deadline)), check=False)
        _require(result.returncode == 0 and not result.stderr and result.stdout.decode().strip() == expected)
    for relative, expected in SOURCE_PINS.items():
        helpers.require_sha256(expected, "source pin")
        _require(helpers._source_digest(ROOT / relative) == expected)
    _require(helpers._source_digest(SOURCE) == caller)
    capture._require_dirfd_support()
    helpers._remaining(deadline)


def _check(directory, name, fd, identity):
    _require(helpers._identity(helpers._file_metadata(fd)) == identity)
    helpers._named_file(directory, name, fd)
    capture._require_reopened_artifact_identity(CONTROL, directory)


def _claim(head, caller):
    capture._require_operational_artifact_scope(CONTROL)
    _, parent = capture._open_directory_path(CONTROL.parent, create=True, name="diagnostic parent")
    directory = claim = None
    try:
        os.mkdir(CONTROL.name, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = capture._open_private_child_directory(parent, CONTROL.name, "diagnostic control")
        claim, _, identity = original.transport._write_held(directory, "claim.json", {
            "schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "expected_head": head,
            "caller_sha256": caller, "claimed_at": helpers._utc_now(), "attempt_consumed": True})
        capture._require_pinned_child_identity(parent, CONTROL.name, directory, "diagnostic control")
        return directory, claim, identity
    except BaseException:
        for fd in (claim, directory):
            if fd is not None:
                os.close(fd)
        raise
    finally:
        os.close(parent)


def _failure(exc):
    """Use exact types and a finite literal inventory, never exception rendering."""
    kind = type(exc)
    if kind is delta.RatingsDeltaError:
        args = exc.args
        code = args[0] if type(args) is tuple and len(args) == 1 and type(args[0]) is str else None
        return "ratings_delta_error", code if code in KNOWN_CODES else "unknown"
    labels = {
        delta._input.AcceptedRiskInputError: "accepted_risk_input_error",
        delta.CanonicalEvidenceError: "canonical_evidence_error",
        DiagnosticRefusal: "diagnostic_refusal", helpers.Deadline: "deadline",
        KeyboardInterrupt: "cancelled", SystemExit: "cancelled",
        OSError: "os_error", FileNotFoundError: "file_missing", PermissionError: "permission_error",
        ValueError: "value_error", TypeError: "type_error", KeyError: "key_error",
        UnicodeDecodeError: "unicode_error", UnicodeEncodeError: "unicode_error",
        RecursionError: "recursion_error", OverflowError: "overflow_error", MemoryError: "memory_error",
    }
    for expected, label in labels.items():
        if kind is expected:
            return label, "unknown"
    return "unknown_exception", "unknown"


def _run(head, caller, deadline):
    directory = claim = report_fd = None
    consumed, stage = False, "preflight"
    terminal, exception_type, refusal_code = "diagnostic_refused", None, None
    started = helpers._utc_now()
    try:
        _preflight(head, caller, deadline)
        stage, consumed = "claim", None
        directory, claim, identity = _claim(head, caller)
        consumed, stage = True, "source_authentication"
        _check(directory, "claim.json", claim, identity)
        helpers._remaining(deadline)
        # Do not inspect, print, convert, persist or return the opaque authority.
        delta.authenticate_capture(CAPTURE_PATH, expected_manifest_sha256=MANIFEST_SHA256,
            expected_manifest_byte_count=MANIFEST_BYTES)
        terminal = "retained_authentication_returned"
    except BaseException as exc:
        exception_type, refusal_code = _failure(exc)
        terminal = "diagnostic_refused"
    try:
        helpers._remaining(deadline)
        if directory is None:
            print(helpers.canonical_json_bytes({"schema": SCHEMA, "terminal": terminal,
                "stage": stage, "attempt_consumed": consumed, "exception_type": exception_type,
                "refusal_code": refusal_code, "diagnostic_only": True,
                "original_capture_accepted": False}).decode())
            return 2
        _check(directory, "claim.json", claim, identity)
        report = {"schema": SCHEMA, "profile_sha256": PROFILE_SHA256, "expected_head": head,
            "caller_sha256": caller, "started_at": started, "finished_at": helpers._utc_now(),
            "terminal": terminal, "stage": stage, "exception_type": exception_type,
            "refusal_code": refusal_code, "attempt_consumed": True, "diagnostic_only": True,
            "original_capture_accepted": False, "changes_original_exit": False,
            "provider_contact_authorized": False, "provider_request_count": None,
            "point_in_time_proven": False, "backtest_ready": False, "paper_or_live_ready": False,
            "qc_calls": 0, "outcome_reads": 0}
        report_fd, payload, report_identity = original.transport._write_held(directory, "report.json", report)
        _check(directory, "claim.json", claim, identity)
        _check(directory, "report.json", report_fd, report_identity)
        helpers._remaining(deadline)
        print(helpers.canonical_json_bytes({"report": report,
            "report_sha256": hashlib.sha256(payload).hexdigest(), "report_bytes": len(payload)}).decode())
        return 0 if terminal == "retained_authentication_returned" else 2
    except BaseException:
        print('{"terminal":"diagnostic_publication_ambiguous","original_capture_accepted":false}')
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
        print('{"terminal":"diagnostic_parent_ambiguous","original_capture_accepted":false}')
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--caller-sha256", required=True)
    args = parser.parse_args(argv)
    return run(args.expected_head, args.caller_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
