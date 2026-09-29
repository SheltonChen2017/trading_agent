"""R267 private, input-only QC diagnostic for XLI/XLF admission readiness.

This is a non-order exception because it measures historical callback and
identifier availability only. It cannot evaluate a strategy or returns.
"""

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_eight_universe_input_qc_projection as projection
from research.analyst_revisions_v2_qc import eight_universe_input_submission as submission
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials


PACKAGE_PATH = ROOT / (
    "artifacts/analyst_revisions_v2/"
    "accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)
CONTROL_DIRECTORY = ROOT / "artifacts/analyst_revisions_v2/eight_universe_input_r267_qc_control_20260929"


def projected():
    package = delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )
    return projection.build_eight_universe_input_qc_projection(package)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "preview", "launch", "status", "read"))
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--organization", help="Owned QC organization ID for a cloud operation")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("R267 operation requires the designated Analyst Revisions worktree")
    value = projected()
    if args.operation == "freeze":
        result = {
            "candidate_id": projection.CANDIDATE_ID,
            "projection_sha256": value.projection_sha256,
            "profile_sha256": value.profile_sha256,
            "source_file_count": len(value.source_files),
            "total_source_byte_count": value.total_source_byte_count,
            "statistic_names": list(value.statistic_names),
            "quantconnect_io_performed": False,
        }
    else:
        plan = submission.build_plan(
            "a" * 32 if args.operation == "preview" else args.organization,
            CONTROL_DIRECTORY, args.attempt,
        )
        if args.operation == "preview":
            result = submission.preview(plan, value)
        else:
            api = credentials.production_client()
            if args.operation == "launch":
                receipt = submission.launch(plan, value, api)
                result = {key: receipt[key] for key in (
                    "candidate_id", "attempt", "project_id", "backtest_id",
                    "projection_sha256", "profile_sha256",
                )}
            else:
                receipt = credentials._read_control(submission._path(plan, "launch"))
                if args.operation == "status":
                    result = {"candidate_id": plan.candidate_id, "attempt": plan.attempt,
                              "status": submission.poll_status(plan, receipt, api)}
                else:
                    counts = submission.read_counts_once(plan, receipt, api)
                    result = {
                        "candidate_id": plan.candidate_id, "attempt": plan.attempt,
                        "decision_count": counts["meta"]["decision_count"],
                        "sleeves": {
                            ticker: {
                                key: row["totals"][key] for key in (
                                    "decision_count", "measurable_count",
                                    "constituent_missing_count", "constituent_stale_count",
                                    "no_positive_weight_count", "mapped_member_count_sum",
                                    "mapped_pit_cap_missing_member_count_sum",
                                    "joint_pass_95_count", "joint_pass_99_count",
                                )
                            } for ticker, row in counts["sleeves"].items()
                        },
                        "overlap": counts["overlap"]["totals"],
                    }
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
