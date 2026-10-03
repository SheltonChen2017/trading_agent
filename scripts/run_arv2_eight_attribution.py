"""Run the preregistered fixed-100% eight-universe attribution diagnostic.

R277 and R278 are distinct order-based QC looks. This runner never creates a
new attempt implicitly: the requested slot is claimed once, and retries stay
within that candidate's three-slot budget and same private project.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2_qc import eight_universe_attribution_study as study
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from scripts.run_arv2_qcom_restored import package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "preview", "launch", "status", "read", "compare"))
    parser.add_argument("candidate", nargs="?", choices=tuple(study.CANDIDATE_ARMS), default="R277")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--organization", help="Owned private QuantConnect organization ID")
    args = parser.parse_args()
    if (Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2"):
        raise ValueError("operation requires the designated Analyst Revisions lane worktree")
    if args.operation == "freeze":
        current = study.freeze_manifest(package())
        if current != study.frozen_manifest():
            raise ValueError("attribution manifest differs from the frozen source")
        result = {"manifest_sha256": hashlib.sha256(study.MANIFEST_PATH.read_bytes()).hexdigest(),
                  "candidates": [(row["candidate_id"], row["projection_sha256"],
                                  row["profile_sha256"]) for row in current["candidates"]]}
    elif args.operation == "compare":
        result = study.compare_from_saved(args.organization)
    else:
        plan = adapter.build_plan(args.candidate,
            "a" * 32 if args.operation == "preview" else args.organization,
            study.CONTROL, args.attempt, family=study.FAMILY)
        if args.operation == "preview":
            projection, _ = study.build_projection(package(), args.candidate)
            identity = adapter.preview(plan, projection)
            result = {key: identity[key] for key in (
                "candidate_id", "attempt", "manifest_sha256", "projection_sha256",
                "profile_sha256")}
        else:
            api = credentials.production_client()
            if args.operation == "launch":
                projection, _ = study.build_projection(package(), args.candidate)
                receipt = adapter.launch(plan, projection, api)
                result = {key: receipt[key] for key in (
                    "candidate_id", "attempt", "project_id", "backtest_id")}
            else:
                receipt = common._read(adapter._path(plan, "launch"))
                response = (adapter.poll_status(plan, receipt, api) if args.operation == "status"
                            else adapter.read_result_once(plan, receipt, api))
                if args.operation == "read":
                    account = response["aggregates"]["account"]
                    execution = response["aggregates"]["execution"]
                    result = {"candidate_id": args.candidate, "attempt": args.attempt,
                              "run_valid": response["run_valid"],
                              "cumulative_return": account["cumulative_return"],
                              "maximum_drawdown": account["maximum_drawdown"],
                              "matched_baseline_target_path_sha256": response["aggregates"][
                                  "matched_baseline_target_path_sha256"],
                              "completed_rebalance_count": execution["completed_rebalance_count"],
                              "invalid_order_count_sum": execution["invalid_order_count_sum"],
                              "canceled_order_count_sum": execution["canceled_order_count_sum"]}
                else:
                    result = response
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
