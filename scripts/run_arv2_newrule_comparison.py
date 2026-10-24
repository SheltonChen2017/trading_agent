"""Fixed six-cell research preparation/lifecycle entry point; never deployment.

Each operation needs its separately committed exact source/run decision. Pins
are source bindings, not authorization flags. Importing this module does not
read private inputs, credentials, QC state or start any operation.
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
from scripts import build_arv2_october_comparison_inputs as prepared_input

helpers = prepared_input.helpers
BRANCH, PYTHON = prepared_input.BRANCH, prepared_input.PYTHON
SOURCE = ROOT / "scripts/run_arv2_newrule_comparison.py"
INPUT_ROOT = ROOT / "artifacts/analyst_revisions_v2/massive_ratings_delta/R297-20261013-D5/package"
PACKAGE_SHA256 = "411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad"
LINEAGE_SHA256 = "e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9"
PACKAGE = INPUT_ROOT / "arv2-preliminary-qc-package-411c2734da61c7d4172c4cb3"
LINEAGE = INPUT_ROOT / ("arv2-october-lineage-" + LINEAGE_SHA256) / "lineage.json"
SCHEMA = "arv2-newrule-comparison-operation-v1"
MAX_OUTPUT_BYTES = 24 * 1024
# The already-frozen D5 import dependencies retain their original literal pins.
# Added pins describe this separately versioned consumer, not a source refresh.
SOURCE_PINS = MappingProxyType({**dict(prepared_input.SOURCE_PINS),
    "scripts/build_arv2_october_comparison_inputs.py": "8ac19a46ba6c8394aaed5b9e3767df882ef5d78340ca8337a8416e6a0549d269",
    "research/quantconnect.py": "7a12fdb68194ee10f6e8c3d7c0fc49c08b34166d056bd5ea2a72937dd03be373",
    "research/analyst_revisions_v2_qc/formal_qc_transport.py": "b8c332eda827aeaee23f0dbbddcc96dbd269c82c996812a8a31fe2a4fec62ac4",
    "research/analyst_revisions_v2_qc/six_universe_coverage_submission.py": "e511e04eeadb5a667b7ecee361dcac3de31d6323a0d64b1ea0b42f2879aab62b",
    "research/analyst_revisions_v2_qc/accepted_risk_preliminary_rating_policy.py": "7d45e0c294d03b5775ca6bd911043ea1e9b819e448eb7107fcbf0a2f162e36bd",
    "research/analyst_revisions_v2_qc/accepted_risk_preliminary_rating_evaluator.py": "2fb9bc8a8f74e37b57acb97f4d20b5820be04b9ee470fc2f34b3a8ea2c804910",
    "research/analyst_revisions_v2_qc/accepted_risk_order_level_core.py": "063ed8fb7024c879a640780c07723c7edfb95665acc711d02fc8be0d964e965f",
    "research/analyst_revisions_v2_qc/accepted_risk_order_level_forced_exit.py": "21ef6978d7c26b833b0ec553298584c360f03d602f3c244f2fc8645bd113ec3f",
    "research/analyst_revisions_v2_qc/accepted_risk_order_level_input_runtime.py": "a08098648d98a95736471113d48a3e1183f04969d2c2561b1a4f5d6bfc80d7ee",
    "research/analyst_revisions_v2_qc/accepted_risk_preliminary_qc_figi.py": "4ee85d92126e31d3bde9acaffb992a54cf44b02efa876157597b876086da7ca9",
    "research/analyst_revisions_v2_qc/accepted_risk_six_universe_order_qc_runtime.py": "84e4d69135ff13f592e071574d22b30255088f4df22bd11f33943c652d81a46a",
    "research/analyst_revisions_v2_qc/accepted_risk_six_universe_order_qc_projection.py": "5037fdc1153c9ac927a540201fa92cb45db463e8313e0c88e04ddc9f0eb301f6",
    "research/analyst_revisions_v2_qc/accepted_risk_preopen_rating_score.py": "67f86ffc696c036c7fbfef64ee00fb1ad1a8599727f5ef36762e329df85a023a",
    "research/analyst_revisions_v2_qc/newrule_comparison_targets.py": "30ed05cbc02bb0076d09c82467a32ad840ead87561f3e2a1ae1cc5a9ee65f29d",
    "research/analyst_revisions_v2_qc/newrule_comparison_qc_runtime.py": "674415b3179836a613afc6f7bdea23a966db21ab67221472fc5d87b4a742049d",
    "research/analyst_revisions_v2_qc/newrule_comparison_projection.py": "4f51d1a9a50293f4fa39be297666c1e6144462abaa82e69e342845580a1a4076",
    "research/analyst_revisions_v2_qc/newrule_comparison_submission.py": "cfd2456f2835bb1a4d2c04d6bb60a633b537a2af276a478ad3bfa5f2bc348d4f",
})
NEW_SOURCE_PINS = MappingProxyType({
    "accepted_risk_october_order_package.py": "655eec765a8b99d489881f7de7ddc339ab6b2c0bb0470feb814c6ef005d03c0a",
    "accepted_risk_preopen_rating_score.py": "67f86ffc696c036c7fbfef64ee00fb1ad1a8599727f5ef36762e329df85a023a",
    "newrule_comparison_targets.py": "30ed05cbc02bb0076d09c82467a32ad840ead87561f3e2a1ae1cc5a9ee65f29d",
    "newrule_comparison_qc_runtime.py": "674415b3179836a613afc6f7bdea23a966db21ab67221472fc5d87b4a742049d",
    "newrule_comparison_projection.py": "4f51d1a9a50293f4fa39be297666c1e6144462abaa82e69e342845580a1a4076",
})
DEADLINES = MappingProxyType({"prepare": 120, "organization": 60,
    "upload": 300, "capacity": 60, "begin": 300, "compile": 60,
    "launch": 90, "status": 60, "read": 90, "summarize": 120})
CANDIDATES = tuple(f"R{number}" for number in range(298, 304))


class OperationRefusal(ValueError):
    pass


def require(value):
    if not value:
        raise OperationRefusal("operation_refused")


def profile_record():
    return {"schema": SCHEMA, "root": str(ROOT), "branch": BRANCH,
        "python": str(PYTHON), "package_path": str(PACKAGE),
        "lineage_path": str(LINEAGE), "package_sha256": PACKAGE_SHA256,
        "lineage_sha256": LINEAGE_SHA256, "source_pins": dict(SOURCE_PINS),
        "new_source_pins": dict(NEW_SOURCE_PINS), "deadlines": dict(DEADLINES),
        "candidate_ids": list(CANDIDATES), "maximum_attempts": 3,
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "native_network_denial_for_offline_operations": True,
        "financial_scope": "six_fixed_order_based_backtests_only",
        "point_in_time_proven": False, "formal_forward_ready": False,
        "paper_or_live_ready": False}


def profile_sha256():
    return hashlib.sha256(helpers.canonical_json_bytes(profile_record())).hexdigest()


def _preflight(args, deadline):
    require(sys.platform == "darwin" and os.name == "posix" and sys.version_info[:2] == (3, 13)
        and Path(sys.executable) == PYTHON and Path.cwd() == ROOT and ROOT.resolve() == ROOT
        and Path(__file__).absolute() == SOURCE)
    require(type(args.expected_head) is str and re.fullmatch(r"[0-9a-f]{40}", args.expected_head) is not None)
    helpers.require_sha256(args.caller_sha256, "caller")
    require(type(args.operation) is str and args.operation in DEADLINES
        and len(SOURCE_PINS) >= 20 and len(NEW_SOURCE_PINS) == 5)
    require(args.candidate is None or args.candidate in CANDIDATES)
    if args.operation in ("begin", "compile", "launch", "status", "read"):
        require(args.candidate in CANDIDATES and type(args.attempt) is int and 1 <= args.attempt <= 3)
    else:
        require(args.candidate is None and args.attempt is None)
    if args.operation == "prepare":
        require(args.family_sha256 is None)
    else:
        helpers.require_sha256(args.family_sha256, "family")
    require((args.prior_failure_sha256 is None) == (args.justification_sha256 is None))
    if args.prior_failure_sha256 is not None:
        require(args.operation == "begin" and args.attempt in (2, 3))
        helpers.require_sha256(args.prior_failure_sha256, "prior failure")
        helpers.require_sha256(args.justification_sha256, "justification")
    elif args.operation == "begin":
        require(args.attempt == 1)
    for command, expected in ((["rev-parse", "--show-toplevel"], str(ROOT)),
        (["branch", "--show-current"], BRANCH), (["rev-parse", "HEAD"], args.expected_head),
        (["status", "--porcelain"], "")):
        result = subprocess.run(["git", *command], cwd=ROOT, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=min(3, helpers._remaining(deadline)), check=False)
        require(result.returncode == 0 and not result.stderr
            and result.stdout.decode("ascii").strip() == expected)
    for relative, expected in SOURCE_PINS.items():
        helpers.require_sha256(expected, "source pin")
        require(helpers._source_digest(ROOT / relative) == expected)
    require(helpers._source_digest(SOURCE) == args.caller_sha256)
    helpers._remaining(deadline)


def _operation(args, deadline):
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
    value = prepared_input.october.load_october_order_input_package(PACKAGE,
        expected_package_sha256=PACKAGE_SHA256, lineage_path=LINEAGE,
        expected_lineage_sha256=LINEAGE_SHA256)
    helpers._remaining(deadline)
    pins = {name: SOURCE_PINS[name] for name in submission.HOST_SOURCE_NAMES}
    bindings = dict(expected_new_source_pins=dict(NEW_SOURCE_PINS), expected_host_source_pins=pins)
    if args.operation == "prepare":
        plan = submission.prepare_family(value, **bindings)
        record = submission.require_family(plan, plan.family_sha256)
        return {"family_sha256": plan.family_sha256,
            "submission_profile_sha256": submission.PROFILE_SHA256,
            "package_sha256": PACKAGE_SHA256, "lineage_sha256": LINEAGE_SHA256,
            "cells": [{key: row[key] for key in ("candidate_id", "projection_sha256", "profile_sha256")}
                      for row in record["cells"]],
            "upload_inventory_sha256": record["upload_inventory_sha256"],
            "qc_contact": False, "result_cell_count": 0}
    plan = submission.load_family(value, expected_family_sha256=args.family_sha256, **bindings)
    helpers._remaining(deadline)
    common = dict(expected_family_sha256=args.family_sha256)
    if args.operation == "organization":
        return submission.discover_organization(plan, **common)
    if args.operation == "upload":
        return submission.upload_inputs(plan, **common)
    if args.operation == "capacity":
        return submission.capacity_once(plan, **common)
    if args.operation == "summarize":
        return submission.summarize_family(plan, **common)
    if args.operation == "begin":
        return submission.begin_attempt(plan, args.candidate, args.attempt, **common,
            prior_failure_sha256=args.prior_failure_sha256,
            retry_justification_sha256=args.justification_sha256)
    if args.operation == "compile":
        return submission.poll_compile_once(plan, args.candidate, args.attempt, **common)
    if args.operation == "launch":
        return submission.launch_compiled(plan, args.candidate, args.attempt, **common)
    if args.operation == "status":
        return submission.poll_status_once(plan, args.candidate, args.attempt, **common)
    if args.operation == "read":
        result = submission.read_result_once(plan, args.candidate, args.attempt, **common)
        meta = result["statistics"]["meta"]
        return {**{key: result[key] for key in ("family_sha256", "candidate_id", "attempt_id",
            "project_id", "backtest_id", "status", "cell_completed", "family_comparable", "result_cell")},
            "statistics_sha256": hashlib.sha256(helpers.canonical_json_bytes(result["statistics"])).hexdigest(),
            "account_aggregates": meta["account_aggregates"],
            "common_source_path_sha256": meta["common_source_path_sha256"],
            "decision_count": meta["decision_count"], "evaluation_session_count": meta["evaluation_session_count"],
            "order_count": meta["order_count"], "fill_count": meta["fill_count"],
            "coverage_fallback_counts": meta["coverage_fallback_counts"]}
    raise OperationRefusal("operation_refused")


def _failure(exc, submission=None):
    # Exact types, finite labels only. Never render/hash opaque runtime errors.
    # Never import or execute a module on the failure path after pin refusal.
    if submission is not None and type(exc) is submission.NewruleSubmissionError:
        return submission.finite_failure(exc)
    for expected, label in ((OperationRefusal, "operation_refused"),
        (helpers.Deadline, "deadline"), (KeyboardInterrupt, "cancelled"),
        (SystemExit, "cancelled"), (FileNotFoundError, "file_missing"),
        (PermissionError, "permission_error"), (OSError, "os_error"),
        (ValueError, "value_error"), (TypeError, "type_error"),
        (MemoryError, "memory_error")):
        if type(exc) is expected:
            return label
    return "unknown_exception"


def run(args):
    started = helpers._utc_now()
    stage = "preflight"
    submission = None
    deadline = time.monotonic() + DEADLINES.get(args.operation, 1)
    try:
        with helpers._alarm(deadline):
            _preflight(args, deadline)
            from research.analyst_revisions_v2_qc import newrule_comparison_submission as submission
            stage = args.operation
            result = _operation(args, deadline)
            helpers._remaining(deadline)
            envelope = {"schema": SCHEMA, "operation": args.operation,
                "expected_head": args.expected_head, "caller_sha256": args.caller_sha256,
                "profile_sha256": profile_sha256(), "started_at": started,
                "finished_at": helpers._utc_now(), "operation_completed": True,
                "result": result, "formal_forward_ready": False,
                "point_in_time_proven": False, "paper_or_live_ready": False}
            payload = helpers.canonical_json_bytes(envelope)
            require(len(payload) <= MAX_OUTPUT_BYTES)
            print(payload.decode("ascii"))
            return 0
    except BaseException as exc:
        print(helpers.canonical_json_bytes({"schema": SCHEMA,
            "operation": args.operation if args.operation in DEADLINES else "unknown",
            "operation_completed": False, "stage": stage,
            "failure_code": _failure(exc, submission), "attempt_consumption": "consult_exact_claim_no_automatic_retry",
            "formal_forward_ready": False, "point_in_time_proven": False,
            "paper_or_live_ready": False}).decode("ascii"))
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=tuple(DEADLINES))
    parser.add_argument("--candidate", choices=CANDIDATES)
    parser.add_argument("--attempt", type=int)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--caller-sha256", required=True)
    parser.add_argument("--family-sha256")
    parser.add_argument("--prior-failure-sha256")
    parser.add_argument("--justification-sha256")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
