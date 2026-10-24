"""One fixed properties-first v4 reconciliation; no operation on import."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts import run_arv2_newrule_comparison as frozen

helpers = frozen.helpers
SOURCE = ROOT / "scripts/run_arv2_newrule_storage_recovery_v4.py"
HELPER_SOURCE = ROOT / "scripts/arv2_newrule_storage_recovery_v4.py"
HELPER_SHA256 = "c77e1e8ba3634f6edd03ec9e825da56eeca3ecac13b48face9b3c25ce9e46c8f"
FROZEN_CALLER_SHA256 = "533c1ebf520e9ebf836c78067b9b1480eccf49cfb01aaeb240e3a73b77087d05"
FAMILY_SHA256 = "8b8ee913dcfb5ad37f4748ea70db4fcbd6ff15580e52cd160bccf2b37e10a9e5"
SCHEMA = "arv2-newrule-storage-recovery-operation-v4"
DEADLINE_SECONDS, MAX_OUTPUT_BYTES = 300, 64 * 1024
# Verified before helper import; this complete closure cannot depend on that import.
ADDITIONS = {
    "scripts/arv2_newrule_storage_recovery_v3.py": "7f817962d49ac4d692351131e1a1af004efa2db7ee720eb0aaf29533757f8c4c",
    "scripts/run_arv2_newrule_storage_recovery_v3.py": "696e04425f6fdc71f0bafa50d17939ae2e7c67f6d9666e12ce1a1437e5c763c0",
    "scripts/diagnose_arv2_newrule_upload.py": "b8477fe9246b7355c9b10bec91a9ad6e6305fcd0a7e2d4f00f61da1c35ce9901",
    "scripts/diagnose_arv2_newrule_object_metadata.py": "0a566b6b049f160daf6cc1a1bb2a507e18dd645c64d948dea50136cebbbede23",
    "scripts/arv2_newrule_storage_recovery_v2.py": "02d40ea52084111cf6a04c6ffad629df0bb9008890133e16ef5b2a8f7b4406e9",
    "scripts/diagnose_arv2_newrule_properties_matrix.py": "47b8eec8296beb0433a1223adea38c471ba2034b26ac81cb20a2e4143431f363",
    "scripts/diagnose_arv2_newrule_storage_error.py": "090c0ad92811820cb87d37df7c13f8b63033d14b5d23f20cac770c729760a252",
}


class RecoveryOperationRefusal(ValueError): pass


def _require(value):
    if not value: raise RecoveryOperationRefusal("operation_refused")


def profile_record():
    return {"schema": SCHEMA, "root": str(ROOT), "branch": frozen.BRANCH, "python": str(frozen.PYTHON),
        "family_sha256": FAMILY_SHA256, "helper_sha256": HELPER_SHA256, "additional_pins": ADDITIONS,
        "frozen_caller_sha256": FROZEN_CALLER_SHA256, "source_pins": dict(frozen.SOURCE_PINS),
        "deadline_seconds": DEADLINE_SECONDS, "max_output_bytes": MAX_OUTPUT_BYTES,
        "actual_exit_required_for_admission": True, "original_upload_accepted": False,
        "strategy_launch": False, "formal_forward_ready": False, "paper_or_live_ready": False}


def profile_sha256(): return hashlib.sha256(helpers.canonical_json_bytes(profile_record())).hexdigest()


def _preflight(args, deadline):
    _require("PYTEST_CURRENT_TEST" not in os.environ and "pytest" not in sys.modules
        and not any(name == "_pytest" or name.startswith("_pytest.") for name in tuple(sys.modules)))
    _require(Path(__file__).absolute() == SOURCE)
    frozen._preflight(SimpleNamespace(operation="summarize", expected_head=args.expected_head,
        caller_sha256=FROZEN_CALLER_SHA256, candidate=None, attempt=None,
        family_sha256=FAMILY_SHA256, prior_failure_sha256=None, justification_sha256=None), deadline)
    helpers.require_sha256(args.caller_sha256, "caller")
    helpers.require_sha256(HELPER_SHA256, "helper")
    _require(helpers._source_digest(SOURCE) == args.caller_sha256
        and helpers._source_digest(HELPER_SOURCE) == HELPER_SHA256)
    for name, digest in ADDITIONS.items(): _require(helpers._source_digest(ROOT / name) == digest)
    helpers._remaining(deadline)


def _failure(error, recovery=None):
    if recovery is not None: return recovery.finite_failure(error)
    for kind, label in ((RecoveryOperationRefusal, "operation_refused"), (frozen.OperationRefusal, "preflight_refused"),
        (helpers.Deadline, "deadline"), (FileExistsError, "claim_collision"), (FileNotFoundError, "file_missing"),
        (PermissionError, "permission_error"), (KeyboardInterrupt, "cancelled"), (SystemExit, "cancelled"),
        (OSError, "os_error"), (ValueError, "value_error"), (TypeError, "type_error")):
        if type(error) is kind: return label
    return "unknown_exception"


def _safe_result(result, recovery):
    _require(type(result) is dict and type(result.get("complete")) is bool)
    fields = {"complete", "report_sha256", "report_bytes", "failure_code", "attempted_request_count", "requests"}
    if result["complete"]: fields |= {"receipt_sha256", "receipt_bytes"}
    _require(set(result) == fields)
    for prefix in ("report", "receipt") if result["complete"] else ("report",):
        helpers.require_sha256(result[prefix + "_sha256"], prefix)
        _require(type(result[prefix + "_bytes"]) is int and 0 < result[prefix + "_bytes"] <= recovery.MAX_REPORT_BYTES)
    _require(result["failure_code"] is None if result["complete"] else type(result["failure_code"]) is str
        and len(result["failure_code"]) <= 64 and result["failure_code"] in recovery.FINITE_FAILURE_CODES)
    count, trace = result["attempted_request_count"], result["requests"]
    _require(type(count) is int and 0 <= count <= 24 and type(trace) is list and len(trace) <= 24)
    for ordinal, entry in enumerate(trace):
        _require(type(entry) is dict and set(entry) == {"ordinal", "phase", "endpoint", "index", "request_sha256",
            "attempted", "http_status", "observation", "object_state", "absence_template_index", "failure_code", "error_shape"})
        helpers.require_sha256(entry["request_sha256"], "request")
        _require(type(entry["ordinal"]) is int and entry["ordinal"] == ordinal and type(entry["index"]) is int and 0 <= entry["index"] < 6
            and type(entry["phase"]) is str and entry["phase"] in {"initial", "recheck", "put", "verify"}
            and entry["endpoint"] == ("object/set" if entry["phase"] == "put" else "object/properties")
            and type(entry["attempted"]) is bool
            and (entry["http_status"] is None or type(entry["http_status"]) is int and 100 <= entry["http_status"] <= 599)
            and (entry["object_state"] is None or type(entry["object_state"]) is str and entry["object_state"] in {"present", "absent", "published"})
            and (entry["absence_template_index"] is None or type(entry["absence_template_index"]) is int and 0 <= entry["absence_template_index"] < len(recovery.ABSENCE_TEMPLATES))
            and (entry["failure_code"] is None or type(entry["failure_code"]) is str and len(entry["failure_code"]) <= 64
                 and entry["failure_code"] in recovery.FINITE_FAILURE_CODES))
        if entry["observation"] is not None: recovery._validate_observation(entry["observation"])
        recovery._validate_error_shape(entry["error_shape"])
    _require(count == sum(entry["attempted"] for entry in trace))
    return result


def run(args):
    recovery, stage = None, "preflight"
    deadline = time.monotonic() + DEADLINE_SECONDS
    started = helpers._utc_now()
    try:
        with helpers._alarm(deadline):
            _preflight(args, deadline)
            from scripts import arv2_newrule_storage_recovery_v4 as recovery
            stage = "reconciliation_claimed_or_ambiguous"
            result = _safe_result(recovery.recover(args.expected_head, args.caller_sha256, deadline), recovery)
            helpers._remaining(deadline)
            envelope = {"schema": SCHEMA, "profile_sha256": profile_sha256(), "expected_head": args.expected_head,
                "caller_sha256": args.caller_sha256, "started_at": started, "finished_at": helpers._utc_now(),
                "operation_completed": result["complete"], "result": result, "original_upload_accepted": False,
                "formal_forward_ready": False, "paper_or_live_ready": False}
            raw = helpers.canonical_json_bytes(envelope)
            _require(len(raw) <= MAX_OUTPUT_BYTES)
            print(raw.decode("ascii"))
            return 0 if result["complete"] else 2
    except BaseException as error:
        print(helpers.canonical_json_bytes({"schema": SCHEMA, "operation_completed": False,
            "stage": stage, "failure_code": _failure(error, recovery), "original_upload_accepted": False,
            "formal_forward_ready": False, "paper_or_live_ready": False}).decode("ascii"))
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--caller-sha256", required=True)
    return run(parser.parse_args(argv))


if __name__ == "__main__": raise SystemExit(main())
