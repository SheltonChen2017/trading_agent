"""QCOM-excluded 10% admission-floor historical order study, R238--R241.

The four zero-slippage sources use the original 2021--2025 package. ``freeze``
and ``preview`` are local. ``launch`` spends one of three candidate attempts;
``read`` consumes the sole bounded aggregate read. ``compare`` uses only
authenticated cached results and includes the 25% arms when all are present.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_coverage10_projection as projection
from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_coverage10_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from scripts.run_arv2_qcom_exclusion import CONTROL as R231_CONTROL, package
from scripts.run_arv2_qcom_exclusion_tilt import CONTROL as TILT_CONTROL
from scripts.run_arv2_weight_ablation import authenticated_cached_result


CONTROL = ROOT / "artifacts/analyst_revisions_v2/six_qcom_exclusion_coverage10_qc_control_20260927"


def projected(candidate, inputs=None):
    return projection.build_qcom_exclusion_coverage10_projection(
        package() if inputs is None else inputs, study.CANDIDATES[candidate])


def freeze():
    inputs = package()
    rows = []
    for index, (candidate, arm) in enumerate(study.CANDIDATES.items(), 160):
        value, profile = projected(candidate, inputs)
        files = [[item.project_path, item.content_sha256, item.byte_count]
                 for item in value.source_files]
        rows.append(dict(
            candidate_id=candidate, arm=arm, slippage_bps=0,
            project_name=f"{index} ARV2 SIX QCOM EXCLUSION COVERAGE10 {arm.upper()} S0 {candidate} 2021 2025",
            backtest_name=f"ARV2 {candidate} QCOM exclusion coverage10 {arm} slippage0 2021 2025",
            kind="order", role=value.role, projection_schema=value.schema,
            projection_sha256=value.projection_sha256,
            profile_id=value.profile_id, profile_sha256=value.profile_sha256,
            source_files_sha256=hashlib.sha256(common._canonical(files)).hexdigest(),
            source_file_count=len(files), total_source_bytes=value.total_source_byte_count,
            statistic_names=study.STATISTIC_NAMES,
            meta_schema=f"arv2-six-matched-qcom-excluded-coverage10-{arm}-meta-v1",
            summary_schema=f"arv2-six-matched-qcom-excluded-coverage10-{arm}-summary-v1",
            tilt_fraction=profile["maximum_stock_weight_change_fraction"],
            matched_baseline_profile_sha256=profile["matched_baseline_profile_sha256"],
            coverage_policy_id=profile["coverage_policy_id"],
            excluded_stock_security_id_sha256=study.predecessor.EXCLUDED_STOCK_SECURITY_ID_SHA256,
            reference_repair_enabled=True,
        ))
    return study.validate_manifest(dict(
        schema=study.MANIFEST_SCHEMA, protocol=study.PROTOCOL,
        package_sha256=inputs.package.package_sha256,
        activation_manifest_sha256=study.predecessor.HISTORICAL_ACTIVATION_SHA256,
        candidates=rows,
    ))


def _has_cached_result(candidate, control):
    return any((control / f"{candidate}-A{attempt}-result.json").is_file()
               for attempt in (1, 2, 3))


def compare_cached():
    adapter._qcom_exclusion_coverage10_manifest()
    results = {candidate: authenticated_cached_result(candidate, CONTROL, study.FAMILY)
               for candidate in study.CANDIDATES}
    controls = {"R231": (R231_CONTROL, "qcom_exclusion"),
                "R235": (TILT_CONTROL, "qcom_exclusion_tilt"),
                "R236": (TILT_CONTROL, "qcom_exclusion_tilt"),
                "R237": (TILT_CONTROL, "qcom_exclusion_tilt")}
    present = {candidate: _has_cached_result(candidate, control)
               for candidate, (control, _) in controls.items()}
    if all(present.values()):
        context = {candidate: authenticated_cached_result(candidate, control, family)
                   for candidate, (control, family) in controls.items()}
        return study.compare_results(results, context)
    output = study.compare_results(results)
    output["context_25pct"] = {"compatible": False,
        "reason": "all four authenticated 25% counterpart results are required",
        "available_candidate_ids": [candidate for candidate, available in present.items() if available]}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "preview", "launch", "status", "read", "compare"))
    parser.add_argument("candidate", nargs="?", choices=tuple(study.CANDIDATES), default="R238")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--organization", help="Owned QC organization ID; required for cloud operations")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("operation requires the designated lane worktree")
    if args.operation in ("freeze", "compare"):
        result = freeze() if args.operation == "freeze" else compare_cached()
    else:
        plan = adapter.build_plan(args.candidate,
            "a" * 32 if args.operation == "preview" else args.organization,
            CONTROL, args.attempt, family=study.FAMILY)
        if args.operation == "preview":
            identity = adapter.preview(plan, projected(args.candidate)[0])
            result = {key: identity[key] for key in (
                "candidate_id", "attempt", "manifest_sha256",
                "projection_sha256", "profile_sha256")}
        else:
            api = credentials.production_client()
            if args.operation == "launch":
                receipt = adapter.launch(plan, projected(args.candidate)[0], api)
                result = {key: receipt[key] for key in (
                    "candidate_id", "attempt", "project_id", "backtest_id")}
            else:
                receipt = common._read(adapter._path(plan, "launch"))
                result = (adapter.poll_status(plan, receipt, api) if args.operation == "status"
                          else adapter.read_result_once(plan, receipt, api))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
