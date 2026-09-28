"""QCOM-excluded AR-on 80/120/200 historical order sensitivity.

The source, manifest, and QC controls are separate from R231--R234.
``freeze`` and ``preview`` are local; ``launch`` consumes one of at most
three QC attempts for one candidate. ``read`` uses the sole bounded custom
statistic read, ``recover`` reparses an already retained read locally, and
``compare`` uses authenticated cached results only.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as projection
from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_tilt_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common
from scripts.run_arv2_qcom_exclusion import CONTROL as R231_CONTROL, package
from scripts.run_arv2_weight_ablation import authenticated_cached_result


CONTROL = ROOT / "artifacts/analyst_revisions_v2/six_qcom_exclusion_tilt_qc_control_20260927"


def projected(candidate, inputs=None):
    return projection.build_qcom_exclusion_tilt_projection(
        package() if inputs is None else inputs, study.CANDIDATES[candidate], 0)


def freeze():
    inputs = package()
    rows = []
    for index, (candidate, percent) in enumerate(study.CANDIDATES.items(), 157):
        value, profile = projected(candidate, inputs)
        files = [[item.project_path, item.content_sha256, item.byte_count]
                 for item in value.source_files]
        rows.append(dict(
            candidate_id=candidate, tilt_percent=percent, arm=f"ar_on{percent}",
            slippage_bps=0,
            project_name=f"{index} ARV2 SIX QCOM EXCLUSION AR_ON{percent} S0 {candidate} 2021 2025",
            backtest_name=f"ARV2 {candidate} QCOM exclusion ar_on{percent} slippage0 2021 2025",
            kind="order", role=value.role, projection_schema=value.schema,
            projection_sha256=value.projection_sha256, profile_id=value.profile_id,
            profile_sha256=value.profile_sha256,
            source_files_sha256=hashlib.sha256(common._canonical(files)).hexdigest(),
            source_file_count=len(files), total_source_bytes=value.total_source_byte_count,
            statistic_names=study.STATISTIC_NAMES,
            meta_schema=f"arv2-six-matched-qcom-excluded-tilt{percent}-meta-v1",
            summary_schema=f"arv2-six-matched-qcom-excluded-tilt{percent}-summary-v1",
            tilt_fraction=profile["maximum_stock_weight_change_fraction"],
            matched_baseline_profile_sha256=profile["matched_baseline_profile_sha256"],
            excluded_stock_security_id_sha256=study.control.EXCLUDED_STOCK_SECURITY_ID_SHA256,
            reference_repair_enabled=True,
        ))
    return study.validate_manifest(dict(
        schema=study.MANIFEST_SCHEMA, protocol=study.PROTOCOL,
        package_sha256=inputs.package.package_sha256,
        activation_manifest_sha256=study.control.HISTORICAL_ACTIVATION_SHA256,
        candidates=rows,
    ))


def compare_cached():
    adapter._qcom_exclusion_manifest()
    adapter._qcom_exclusion_tilt_manifest()
    results = {"R231": authenticated_cached_result("R231", R231_CONTROL, "qcom_exclusion")}
    results.update({
        candidate: authenticated_cached_result(candidate, CONTROL, study.FAMILY)
        for candidate in study.CANDIDATES
    })
    return study.compare_results(results)


def recover_retained_result(candidate, attempt=1, control=CONTROL):
    """Finish a spent read from its retained custom statistics, without QC I/O."""
    plan = adapter.build_plan(candidate, "a" * 32, control, attempt, family=study.FAMILY)
    result_path = adapter._path(plan, "result")
    if result_path.exists() or adapter._path(plan, "recovery-read-claim").exists():
        raise ValueError("QCOM-excluded tilt recovery result is already present or claim changed")
    launch = common._read(adapter._path(plan, "launch"))
    identity = adapter._receipt(plan, launch)
    expected = {"candidate_id": candidate, "attempt": attempt,
        "project_id": launch["project_id"], "backtest_id": launch["backtest_id"],
        "status": "Completed."}
    if (common._read(adapter._path(plan, "terminal")) != expected
            or common._read(adapter._path(plan, "read-claim")) != expected):
        raise ValueError("QCOM-excluded tilt recovery lacks exact completed read claim")
    raw = adapter._read_artifact(adapter._path(plan, "raw-custom"))
    row = adapter._candidate(plan)
    if (set(raw) != set(expected) | {"statistics"}
            or any(raw.get(key) != value for key, value in expected.items())
            or type(raw.get("statistics")) is not dict
            or set(raw["statistics"]) != set(row["statistic_names"])):
        raise ValueError("QCOM-excluded tilt recovery raw-statistic identity changed")
    parsed = adapter._parse_order(plan, raw["statistics"])
    adapter._write_artifact(result_path, {**expected, **parsed,
        "manifest_sha256": identity["manifest_sha256"],
        "projection_sha256": row["projection_sha256"]})
    return parsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "preview", "launch", "status", "read", "recover", "compare"))
    parser.add_argument("candidate", nargs="?", choices=tuple(study.CANDIDATES), default="R235")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--organization", help="Owned QC organization ID; required for cloud operations")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("operation requires the designated lane worktree")
    if args.operation in ("freeze", "compare"):
        result = freeze() if args.operation == "freeze" else compare_cached()
    elif args.operation == "recover":
        result = recover_retained_result(args.candidate, args.attempt, CONTROL)
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
                result = (
                    adapter.poll_status(plan, receipt, api)
                    if args.operation == "status"
                    else adapter.read_result_once(plan, receipt, api)
                )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
