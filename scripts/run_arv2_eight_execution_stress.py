"""Run the frozen R280–R283 5-bps physical-order execution diagnostic.

One candidate is one private QC project with at most three accounted attempts.
The 20-session ADV capacity leg is unavailable, not a passing observation.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2_qc import eight_universe_execution_stress_study as study
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from scripts.run_arv2_qcom_restored import package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "preview", "launch", "status", "read"))
    parser.add_argument("candidate", nargs="?", choices=tuple(study.PARENT_BY_CANDIDATE), default="R280")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--organization", help="Owned private QuantConnect organization ID")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("operation requires the designated Analyst Revisions lane worktree")
    if args.operation == "freeze":
        frozen = study.frozen_manifest()
        if study.freeze_manifest(package()) != frozen:
            raise ValueError("execution-stress source differs from the frozen manifest")
        result = {"manifest_sha256": hashlib.sha256(study.MANIFEST_PATH.read_bytes()).hexdigest(),
                  "candidates": [(row["candidate_id"], row["projection_sha256"],
                                  row["profile_sha256"]) for row in frozen["candidates"]],
                  "liquidity_capacity_diagnostic": study.ADV_UNAVAILABLE}
    else:
        plan = adapter.build_plan(args.candidate,
            "a" * 32 if args.operation == "preview" else args.organization,
            study.CONTROL, args.attempt, family=study.FAMILY)
        if args.operation == "preview":
            projected, _ = study.build_projection(package(), args.candidate)
            identity = adapter.preview(plan, projected)
            result = {key: identity[key] for key in (
                "candidate_id", "attempt", "manifest_sha256", "projection_sha256",
                "profile_sha256")}
        else:
            api = credentials.production_client()
            if args.operation == "launch":
                projected, _ = study.build_projection(package(), args.candidate)
                receipt = adapter.launch(plan, projected, api)
                result = {key: receipt[key] for key in (
                    "candidate_id", "attempt", "project_id", "backtest_id")}
            else:
                receipt = common._read(adapter._path(plan, "launch"))
                response = (adapter.poll_status(plan, receipt, api) if args.operation == "status"
                            else adapter.read_result_once(plan, receipt, api))
                if args.operation == "read":
                    account = response["aggregates"]["account"]
                    execution = response["aggregates"]["execution"]
                    result = {
                        "candidate_id": args.candidate, "attempt": args.attempt,
                        "run_valid": response["run_valid"],
                        "cumulative_return": account["cumulative_return"],
                        "maximum_drawdown": account["maximum_drawdown"],
                        "completed_rebalance_count": execution["completed_rebalance_count"],
                        "invalid_order_count_sum": execution["invalid_order_count_sum"],
                        "canceled_order_count_sum": execution["canceled_order_count_sum"],
                        "actual_engine_fee_amount": execution["actual_engine_fee_amount"],
                        "modeled_fee_amount": execution["modeled_fee_amount"],
                        "execution_stress_fill_audit":
                            response["aggregates"]["execution_stress_fill_audit"],
                        "liquidity_capacity_diagnostic": study.ADV_UNAVAILABLE,
                    }
                else:
                    result = response
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
