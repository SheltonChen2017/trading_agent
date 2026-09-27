"""Prospective QCOM-direct-stock exclusion sensitivity, not an R225 retry.

The four historical order arms retain the original input package and window.
Only the explicitly versioned stock-eligibility exclusion differs. ``freeze``
and ``preview`` are local; ``launch`` is a one-attempt QC mutation, and ``read``
uses the receipt-bound one-use aggregate reader.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as projection
from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from scripts.run_arv2_weight_ablation import authenticated_cached_result

CONTROL = ROOT / "artifacts/analyst_revisions_v2/six_qcom_exclusion_qc_control_20260927"
PACKAGE = ROOT / "artifacts/analyst_revisions_v2/accepted_risk_delta_order_package_20260918_01"


def package():
    return delta.load_accepted_risk_delta_order_package(
        PACKAGE / delta.EXPECTED_DELTA_PACKAGE_ID,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )


def projected(candidate, inputs=None):
    arm, slippage = study.CANDIDATES[candidate]
    return projection.build_qcom_exclusion_projection(
        package() if inputs is None else inputs, arm, slippage
    )


def freeze():
    inputs = package()
    rows = []
    for index, (candidate, (arm, slippage)) in enumerate(study.CANDIDATES.items(), 153):
        value, profile = projected(candidate, inputs)
        files = [
            [item.project_path, item.content_sha256, item.byte_count]
            for item in value.source_files
        ]
        rows.append(dict(
            candidate_id=candidate, arm=arm, slippage_bps=slippage,
            project_name=f"{index} ARV2 SIX QCOM EXCLUSION {arm.upper()} S{slippage} {candidate} 2021 2025",
            backtest_name=f"ARV2 {candidate} QCOM exclusion {arm} slippage{slippage} 2021 2025",
            kind="order", role=value.role,
            projection_schema=value.schema,
            projection_sha256=value.projection_sha256,
            profile_id=value.profile_id,
            profile_sha256=value.profile_sha256,
            source_files_sha256=hashlib.sha256(common._canonical(files)).hexdigest(),
            source_file_count=len(files),
            total_source_bytes=value.total_source_byte_count,
            statistic_names=[
                "ARV2_SIX_GATE_ORDER_META",
                "ARV2_SIX_GATE_ORDER_AGGREGATES",
                study.DIAGNOSTIC_NAME,
            ],
            meta_schema=projection.QCOM_EXCLUSION_META_SCHEMA,
            summary_schema=projection.QCOM_EXCLUSION_SUMMARY_SCHEMA,
            tilt_fraction=profile["maximum_stock_weight_change_fraction"],
            matched_baseline_profile_sha256=profile["matched_baseline_profile_sha256"],
            excluded_stock_security_id_sha256=study.EXCLUDED_STOCK_SECURITY_ID_SHA256,
            reference_repair_enabled=True,
        ))
    value = dict(
        schema=study.MANIFEST_SCHEMA,
        protocol=study.PROTOCOL,
        package_sha256=inputs.package.package_sha256,
        activation_manifest_sha256=study.HISTORICAL_ACTIVATION_SHA256,
        candidates=rows,
    )
    return study.validate_manifest(value)


def compare_cached():
    adapter._qcom_exclusion_manifest()
    results = {
        candidate: authenticated_cached_result(candidate, CONTROL, "qcom_exclusion")
        for candidate in study.CANDIDATES
    }
    return study.compare_results(results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "preview", "launch", "status", "read", "compare"))
    parser.add_argument("candidate", nargs="?", choices=tuple(study.CANDIDATES), default="R231")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--organization", help="Owned QC organization ID; required for cloud operations")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("operation requires the designated lane worktree")
    if args.operation in ("freeze", "compare"):
        result = freeze() if args.operation == "freeze" else compare_cached()
    else:
        plan = adapter.build_plan(
            args.candidate,
            "a" * 32 if args.operation == "preview" else args.organization,
            CONTROL,
            args.attempt,
            family="qcom_exclusion",
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
                result = (
                    adapter.poll_status(plan, receipt, api)
                    if args.operation == "status"
                    else adapter.read_result_once(plan, receipt, api)
                )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
