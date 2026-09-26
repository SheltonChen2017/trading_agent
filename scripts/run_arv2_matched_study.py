"""Frozen AR-off/on100/six-ETF historical order study, with 0/5bps slippage.

Freeze/preview/compare are offline. Launch is explicit, research-only and
bounded by the existing same-project three-attempt receipt engine.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import six_universe_matched_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from scripts.run_arv2_weight_ablation import authenticated_cached_result

CONTROL = ROOT / "artifacts/analyst_revisions_v2/six_matched_study_qc_control_20260926"


def package():
    location = ROOT / "artifacts/analyst_revisions_v2/accepted_risk_delta_order_package_20260918_01"
    return delta.load_accepted_risk_delta_order_package(location / delta.EXPECTED_DELTA_PACKAGE_ID,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256)


def projected(candidate, inputs=None):
    from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as projection
    arm, slippage = study.CANDIDATES[candidate]
    return projection.build_matched_historical_projection(package() if inputs is None else inputs, arm, slippage)


def freeze():
    from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as projection
    inputs = package()
    rows = []
    for index, (candidate, (arm, slippage)) in enumerate(study.CANDIDATES.items(), 147):
        value, profile = projected(candidate, inputs)
        files = [[item.project_path, item.content_sha256, item.byte_count] for item in value.source_files]
        rows.append(dict(candidate_id=candidate, arm=arm, slippage_bps=slippage,
            project_name=f"{index} ARV2 SIX MATCHED {arm.upper()} S{slippage} {candidate} 2021 2025",
            backtest_name=f"ARV2 {candidate} matched {arm} slippage{slippage} 2021 2025",
            kind="order", role=value.role, projection_schema=value.schema,
            projection_sha256=value.projection_sha256, profile_id=value.profile_id,
            profile_sha256=value.profile_sha256,
            source_files_sha256=hashlib.sha256(common._canonical(files)).hexdigest(),
            source_file_count=len(files), total_source_bytes=value.total_source_byte_count,
            statistic_names=["ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES", study.DIAGNOSTIC_NAME],
            meta_schema=projection.META_SCHEMA, summary_schema=projection.SUMMARY_SCHEMA,
            tilt_fraction=profile["maximum_stock_weight_change_fraction"],
            matched_baseline_profile_sha256=profile["matched_baseline_profile_sha256"]))
    value = dict(schema="arv2-six-matched-historical-study-v1", protocol=study.PROTOCOL,
        package_sha256=value.package_sha256,
        activation_manifest_sha256=study.HISTORICAL_ACTIVATION_SHA256,
        candidates=rows)
    return study.validate_manifest(value)


def compare_cached():
    adapter._matched_study_manifest()
    results = {candidate: authenticated_cached_result(candidate, CONTROL, "matched_study")
               for candidate in study.CANDIDATES}
    return study.compare_results(results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "preview", "launch", "status", "read", "compare"))
    parser.add_argument("candidate", nargs="?", choices=tuple(study.CANDIDATES), default="R225")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--organization", help="Owned QC organization ID; required only for cloud operations")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("operation requires the designated lane worktree")
    if args.operation in ("freeze", "compare"):
        result = freeze() if args.operation == "freeze" else compare_cached()
    else:
        plan = adapter.build_plan(args.candidate,
            "a" * 32 if args.operation == "preview" else args.organization,
            CONTROL, args.attempt, family="matched_study")
        if args.operation == "preview":
            identity = adapter.preview(plan, projected(args.candidate)[0])
            result = {key: identity[key] for key in ("candidate_id", "attempt",
                "manifest_sha256", "projection_sha256", "profile_sha256")}
        else:
            api = credentials.production_client()
            if args.operation == "launch":
                receipt = adapter.launch(plan, projected(args.candidate)[0], api)
                result = {key: receipt[key] for key in ("candidate_id", "attempt", "project_id", "backtest_id")}
            else:
                receipt = common._read(adapter._path(plan, "launch"))
                result = (adapter.poll_status(plan, receipt, api) if args.operation == "status"
                          else adapter.read_result_once(plan, receipt, api))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
