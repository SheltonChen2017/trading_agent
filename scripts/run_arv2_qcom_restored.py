"""Prospective QCOM-restored physical-order analogues R248--R259.

``freeze`` and ``preview`` are local. Owner-authorized exploratory cloud
actions remain subject to the lane's exact source, claim, project, attempt,
and one-use result gates; each candidate has at most three attempts.
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2_qc import six_universe_qcom_restored_projection as renderer
from research.analyst_revisions_v2_qc import six_universe_qcom_restored_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from scripts.run_arv2_qcom_exclusion import package


CONTROL = ROOT / "artifacts/analyst_revisions_v2/six_qcom_restored_qc_control_20260928"


def projected(candidate, inputs=None):
    predecessor = study.CANDIDATES[candidate]
    return renderer.build_qcom_admitted_projection(
        package() if inputs is None else inputs, predecessor, candidate,
    )


def _literal(source_files, path, name):
    rows = [item for item in source_files if item.project_path == path]
    if len(rows) != 1:
        raise ValueError("QCOM-restored writer source is absent")
    tree = ast.parse(rows[0].source_bytes.decode("ascii"))
    values = [node.value.value for node in tree.body
              if isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Name)
              and node.targets[0].id == name
              and isinstance(node.value, ast.Constant)
              and type(node.value.value) is str]
    if len(values) != 1:
        raise ValueError("QCOM-restored writer schema is not one literal")
    return values[0]


def freeze():
    """Recompute all exact source, profile, and writer pins without QC I/O."""
    inputs = package()
    rows = []
    for candidate, predecessor in study.CANDIDATES.items():
        value, profile = projected(candidate, inputs)
        family, predecessor_pin, parent = study._parent(predecessor)
        files = [[item.project_path, item.content_sha256, item.byte_count]
                 for item in value.source_files]
        rows.append({
            "candidate_id": candidate,
            "predecessor_candidate_id": predecessor,
            "predecessor_family": family,
            "predecessor_manifest_sha256": predecessor_pin,
            "predecessor_projection_sha256": parent["projection_sha256"],
            "predecessor_profile_sha256": parent["profile_sha256"],
            "project_name": f"ARV2 SIX QCOM RESTORED {candidate} FROM {predecessor} 2021 2025",
            "backtest_name": f"ARV2 {candidate} QCOM restored from {predecessor} 2021 2025",
            "kind": "order", "arm": parent["arm"], "slippage_bps": 0,
            "tilt_fraction": profile["maximum_stock_weight_change_fraction"],
            "coverage_policy_id": profile.get("coverage_policy_id"),
            "analyst_revision_economic_usage": study._economic_usage(parent["arm"]),
            "reference_repair_enabled": True,
            "role": value.role, "projection_schema": value.schema,
            "projection_sha256": value.projection_sha256,
            "profile_id": value.profile_id, "profile_sha256": value.profile_sha256,
            "matched_baseline_profile_sha256": profile["matched_baseline_profile_sha256"],
            "source_files_sha256": hashlib.sha256(common._canonical(files)).hexdigest(),
            "source_file_count": len(files), "total_source_bytes": value.total_source_byte_count,
            "statistic_names": study.STATISTIC_NAMES,
            "meta_schema": _literal(value.source_files,
                "accepted_risk_six_universe_order_qc_runtime.py", "META_SCHEMA"),
            "summary_schema": _literal(value.source_files,
                "accepted_risk_six_universe_order_tilt_qc_runtime.py", "TILT_SUMMARY_SCHEMA"),
        })
    return study.validate_manifest({
        "schema": study.MANIFEST_SCHEMA, "protocol": study.PROTOCOL,
        "package_sha256": inputs.package.package_sha256,
        "activation_manifest_sha256": study.excluded.HISTORICAL_ACTIVATION_SHA256,
        "candidates": rows,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "preview", "launch", "status", "read"))
    parser.add_argument("candidate", nargs="?", choices=tuple(study.CANDIDATES), default="R248")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--organization", help="Owned QC organization ID for a cloud operation")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("operation requires the designated lane worktree")
    if args.operation == "freeze":
        result = freeze()
    else:
        plan = adapter.build_plan(
            args.candidate, "a" * 32 if args.operation == "preview" else args.organization,
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
