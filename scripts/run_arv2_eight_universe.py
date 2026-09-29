"""Freeze and inspect R268--R276 eight-sleeve order candidates.

Local freeze/preview perform no QC I/O.  A cloud launch requires the
authenticated R267 input gate and a valid R268 market-cap baseline first.
Each candidate has one private project, at most three attempts, and a single
bounded result read per completed run.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2_qc import eight_universe_qcom_admitted_projection as renderer
from research.analyst_revisions_v2_qc import eight_universe_r268_a2_diagnostic as drift_a2
from research.analyst_revisions_v2_qc import eight_universe_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from scripts.run_arv2_qcom_restored import _literal, package


CONTROL = ROOT / "artifacts/analyst_revisions_v2/eight_universe_qc_control_20260929"


def projected(candidate, inputs=None, *, attempt=1):
    """Build one exact new 17-file order source without cloud or outcome I/O."""
    if candidate == study.BASELINE and attempt == 2:
        return drift_a2.build_projection(package() if inputs is None else inputs)
    if candidate == study.BASELINE and attempt != 1:
        raise ValueError("R268 A3 requires its own prospective source freeze")
    return renderer.build_eight_universe_projection(
        package() if inputs is None else inputs,
        study.CANDIDATE_ARMS[candidate], candidate,
    )


def freeze():
    """Recompute every new source, profile, and writer pin offline."""
    inputs = package()
    floor, restored = study._source_rows()
    rows = []
    for candidate, arm in study.CANDIDATE_ARMS.items():
        _, parent_id, parent_projection = renderer.PARENT_IDS[arm]
        on = arm.startswith("ar_on")
        parent = (floor if on else restored)[parent_id]
        value, profile = projected(candidate, inputs)
        files = [[item.project_path, item.content_sha256, item.byte_count]
                 for item in value.source_files]
        rows.append({
            "candidate_id": candidate,
            "arm": arm,
            "source_candidate_id": parent_id,
            "source_family": "qcom_score_floor1" if on else "qcom_restored",
            "source_manifest_sha256": (
                adapter.FROZEN_QCOM_SCORE_FLOOR1_MANIFEST_SHA256 if on else
                adapter.FROZEN_QCOM_RESTORED_MANIFEST_SHA256),
            "source_projection_sha256": parent_projection,
            "source_profile_sha256": parent["profile_sha256"],
            "project_name": f"ARV2 EIGHT QCOM {candidate} {arm.upper()} 2021 2025",
            "backtest_name": f"ARV2 {candidate} eight QCOM {arm} 2021 2025",
            "kind": "order", "slippage_bps": 0,
            "tilt_fraction": profile["maximum_stock_weight_change_fraction"],
            "coverage_policy_id": profile["coverage_policy_id"],
            "minimum_verified_name_count": 3,
            "minimum_positive_score_count": study._score_floor(arm),
            "analyst_revision_economic_usage": study._usage(arm),
            "reference_repair_enabled": True,
            "role": value.role,
            "projection_schema": value.schema,
            "projection_sha256": value.projection_sha256,
            "profile_id": value.profile_id,
            "profile_sha256": value.profile_sha256,
            "matched_baseline_profile_sha256": profile["matched_baseline_profile_sha256"],
            "source_files_sha256": hashlib.sha256(common._canonical(files)).hexdigest(),
            "source_file_count": len(files),
            "total_source_bytes": value.total_source_byte_count,
            "statistic_names": study.STATISTIC_NAMES,
            "meta_schema": _literal(value.source_files,
                "accepted_risk_six_universe_order_qc_runtime.py", "META_SCHEMA"),
            "summary_schema": _literal(value.source_files,
                "accepted_risk_six_universe_order_tilt_qc_runtime.py", "TILT_SUMMARY_SCHEMA"),
        })
    return study.validate_manifest({
        "schema": study.MANIFEST_SCHEMA,
        "protocol": study.PROTOCOL,
        "package_sha256": inputs.package.package_sha256,
        "activation_manifest_sha256": study.adapter._qcom_score_floor1_manifest()[
            "activation_manifest_sha256"],
        "candidates": rows,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "preview", "launch", "status", "read"))
    parser.add_argument("candidate", nargs="?", choices=tuple(study.CANDIDATE_ARMS),
                        default=study.BASELINE)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--organization", help="Owned QC organization ID for a cloud operation")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("operation requires the designated lane worktree")
    if args.operation == "freeze":
        if args.candidate == study.BASELINE and args.attempt == 3:
            raise ValueError("R268 A3 requires its own prospective source freeze")
        result = (drift_a2.freeze_manifest(package())
                  if args.candidate == study.BASELINE and args.attempt == 2
                  else freeze())
    else:
        plan = adapter.build_plan(
            args.candidate,
            "a" * 32 if args.operation == "preview" else args.organization,
            CONTROL, args.attempt, family=study.FAMILY,
        )
        if args.operation == "preview":
            identity = adapter.preview(plan, projected(args.candidate, attempt=args.attempt)[0])
            result = {key: identity[key] for key in (
                "candidate_id", "attempt", "manifest_sha256",
                "projection_sha256", "profile_sha256",
            )}
        else:
            api = credentials.production_client()
            if args.operation == "launch":
                receipt = adapter.launch(plan, projected(args.candidate, attempt=args.attempt)[0], api)
                result = {key: receipt[key] for key in (
                    "candidate_id", "attempt", "project_id", "backtest_id",
                )}
            else:
                receipt = common._read(adapter._path(plan, "launch"))
                result = (adapter.poll_status(plan, receipt, api)
                          if args.operation == "status"
                          else adapter.read_result_once(plan, receipt, api))
                if (args.operation == "read" and args.candidate == study.BASELINE
                        and args.attempt == 2):
                    diagnostic = result["drift_diagnostic"]
                    result = {key: diagnostic[key] for key in (
                        "holding_drift_skip_count", "rejections")}
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
