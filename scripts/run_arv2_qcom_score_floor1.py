"""Frozen QCOM-admitted positive-score-floor-one order sensitivity R260--R266.

``freeze`` and ``preview`` are local and outcome-free. R261/on100 must run
first; a bounded, authenticated increase in direct-stock selections is a
hard prerequisite to launching any other ladder arm. Cloud operations retain
one private project, at most three attempts and one result read per arm.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2_qc import six_universe_qcom_restored_score_floor1_projection as renderer
from research.analyst_revisions_v2_qc import six_universe_qcom_score_floor1_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from scripts.run_arv2_qcom_restored import _literal, package


CONTROL = ROOT / "artifacts/analyst_revisions_v2/six_qcom_score_floor1_qc_control_20260929"


def projected(candidate, inputs=None):
    """Build a new versioned source from the exact frozen QCOM-admitted base."""
    return renderer.build_qcom_admitted_score_floor1_projection(
        package() if inputs is None else inputs,
        study.CANDIDATE_PERCENTS[candidate], candidate,
    )


def freeze():
    """Recompute every source, profile and writer pin without QC I/O."""
    inputs = package()
    original = adapter._qcom_restored_manifest()
    sources = {row["candidate_id"]: row for row in original["candidates"]}
    rows = []
    for candidate, percent in study.CANDIDATE_PERCENTS.items():
        source_id = study.SOURCE_CANDIDATES[candidate]
        parent = sources[source_id]
        value, profile = projected(candidate, inputs)
        files = [[item.project_path, item.content_sha256, item.byte_count]
                 for item in value.source_files]
        rows.append({
            "candidate_id": candidate,
            "source_candidate_id": source_id,
            "source_manifest_sha256": adapter.FROZEN_QCOM_RESTORED_MANIFEST_SHA256,
            "source_projection_sha256": parent["projection_sha256"],
            "source_profile_sha256": parent["profile_sha256"],
            "project_name": f"ARV2 SIX QCOM FLOOR1 {candidate} AR{percent} 2021 2025",
            "backtest_name": f"ARV2 {candidate} QCOM score floor1 AR{percent} 2021 2025",
            "kind": "order", "arm": f"ar_on{percent}", "slippage_bps": 0,
            "tilt_fraction": profile["maximum_stock_weight_change_fraction"],
            "coverage_policy_id": profile["coverage_policy_id"],
            "minimum_verified_name_count": 3,
            "minimum_positive_score_count": 1,
            "analyst_revision_economic_usage": "entry_count_and_weight",
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
        "activation_manifest_sha256": study.excluded.HISTORICAL_ACTIVATION_SHA256,
        "candidates": rows,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "preview", "launch", "status", "read"))
    parser.add_argument("candidate", nargs="?", choices=tuple(study.CANDIDATE_PERCENTS),
                        default=study.PILOT)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--organization", help="Owned QC organization ID for a cloud operation")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("operation requires the designated lane worktree")
    if args.operation == "freeze":
        result = freeze()
    else:
        plan = adapter.build_plan(
            args.candidate,
            "a" * 32 if args.operation == "preview" else args.organization,
            CONTROL, args.attempt, family=study.FAMILY,
        )
        if args.operation == "preview":
            identity = adapter.preview(plan, projected(args.candidate)[0])
            result = {key: identity[key] for key in (
                "candidate_id", "attempt", "manifest_sha256",
                "projection_sha256", "profile_sha256",
            )}
        else:
            api = credentials.production_client()
            if args.operation == "launch":
                receipt = adapter.launch(plan, projected(args.candidate)[0], api)
                result = {key: receipt[key] for key in (
                    "candidate_id", "attempt", "project_id", "backtest_id",
                )}
            else:
                receipt = common._read(adapter._path(plan, "launch"))
                result = (adapter.poll_status(plan, receipt, api)
                          if args.operation == "status"
                          else adapter.read_result_once(plan, receipt, api))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
