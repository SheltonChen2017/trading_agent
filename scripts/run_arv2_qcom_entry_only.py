"""Frozen R246 historical order diagnostic: AR entry/count, zero weight tilt.

The new arm shares R231/R232's QCOM-excluded source and order economics.
``freeze``/``preview`` are offline; each QC launch consumes one of three
attempts. ``compare`` reparses retained single-read statistics, never QC logs.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2_qc import six_universe_qcom_entry_only_projection as projection
from research.analyst_revisions_v2_qc import six_universe_qcom_entry_only_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from scripts.run_arv2_qcom_exclusion import CONTROL as PREDECESSOR_CONTROL, package
from scripts.run_arv2_weight_ablation import authenticated_cached_result


CONTROL = ROOT / "artifacts/analyst_revisions_v2/six_qcom_entry_only_qc_control_20260927"


def projected(inputs=None):
    return projection.build_qcom_entry_only_projection(package() if inputs is None else inputs)


def freeze():
    inputs = package()
    value, profile = projected(inputs)
    files = [[item.project_path, item.content_sha256, item.byte_count]
             for item in value.source_files]
    row = dict(candidate_id=study.CANDIDATE, arm="ar_on0", slippage_bps=0,
        project_name="ARV2 R246 QCOM ENTRY COUNT ZERO WEIGHT 2021 2025",
        backtest_name="ARV2 R246 QCOM entry count zero weight 2021 2025",
        kind="order", role=value.role, projection_schema=value.schema,
        projection_sha256=value.projection_sha256, profile_id=value.profile_id,
        profile_sha256=value.profile_sha256,
        source_files_sha256=hashlib.sha256(common._canonical(files)).hexdigest(),
        source_file_count=len(files), total_source_bytes=value.total_source_byte_count,
        statistic_names=study.STATISTIC_NAMES,
        meta_schema=projection.prior.QCOM_EXCLUSION_META_SCHEMA,
        summary_schema="arv2-six-matched-qcom-excluded-tilt0-summary-v1",
        tilt_fraction=profile["maximum_stock_weight_change_fraction"],
        matched_baseline_profile_sha256=profile["matched_baseline_profile_sha256"],
        excluded_stock_security_id_sha256=study.control.EXCLUDED_STOCK_SECURITY_ID_SHA256,
        reference_repair_enabled=True)
    return study.validate_manifest(dict(schema=study.MANIFEST_SCHEMA,
        protocol=study.PROTOCOL, package_sha256=inputs.package.package_sha256,
        activation_manifest_sha256=study.control.HISTORICAL_ACTIVATION_SHA256,
        candidates=[row]))


def compare_cached():
    adapter._qcom_exclusion_manifest()
    adapter._qcom_entry_only_manifest()
    results = {
        "R231": authenticated_cached_result("R231", PREDECESSOR_CONTROL, "qcom_exclusion"),
        study.CANDIDATE: authenticated_cached_result(study.CANDIDATE, CONTROL, study.FAMILY),
        "R232": authenticated_cached_result("R232", PREDECESSOR_CONTROL, "qcom_exclusion"),
    }
    return study.compare_results(results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "preview", "launch", "status", "read", "compare"))
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--organization", help="Owned QC organization ID for a cloud operation")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("operation requires the designated lane worktree")
    if args.operation == "freeze":
        result = freeze()
    elif args.operation == "compare":
        result = compare_cached()
    else:
        plan = adapter.build_plan(study.CANDIDATE,
            "a" * 32 if args.operation == "preview" else args.organization,
            CONTROL, args.attempt, family=study.FAMILY)
        if args.operation == "preview":
            identity = adapter.preview(plan, projected()[0])
            result = {key: identity[key] for key in (
                "candidate_id", "attempt", "manifest_sha256",
                "projection_sha256", "profile_sha256")}
        else:
            api = credentials.production_client()
            if args.operation == "launch":
                receipt = adapter.launch(plan, projected()[0], api)
                result = {key: receipt[key] for key in (
                    "candidate_id", "attempt", "project_id", "backtest_id")}
            else:
                receipt = common._read(adapter._path(plan, "launch"))
                result = (adapter.poll_status(plan, receipt, api)
                          if args.operation == "status"
                          else adapter.read_result_once(plan, receipt, api))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
