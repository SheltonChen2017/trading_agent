"""Exact exploratory-family operations; only bounded research summaries print."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_latest_order_package as latest
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt_recent_qc_projection as recent
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_recent_coverage_projection as coverage_projection
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as coverage
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common

CONTROL = ROOT / "artifacts/analyst_revisions_v2/six_relaxed_qc_control_20260926"


def packages():
    prior = delta.load_accepted_risk_delta_order_package(
        ROOT / "artifacts/analyst_revisions_v2/accepted_risk_delta_order_package_20260918_01" / delta.EXPECTED_DELTA_PACKAGE_ID,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256)
    location = ROOT / "artifacts/analyst_revisions_v2/accepted_risk_latest_order_package_20260925_01"
    current = latest.load_latest_order_input_package(
        location / recent.PINNED_PACKAGE_ID, expected_package_sha256=recent.PINNED_PACKAGE_SHA256,
        lineage_path=location / ("arv2-latest-lineage-" + recent.PINNED_LINEAGE_SHA256) / "lineage.json",
        expected_lineage_sha256=recent.PINNED_LINEAGE_SHA256).package
    return prior, current


def projection(candidate):
    prior, current = packages()
    if candidate == "R209":
        return coverage_projection.build_recent_coverage_projection(prior, current)
    from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
    policy = tuple(tuple(item) for item in adapter._manifest()["coverage_policy"])
    return relaxed.build_relaxed_order_projection(prior, current, (int(candidate[1:]) - 209) * 20, policy)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("diagnostic-manifest", "order-manifest", "preview", "launch", "status", "read", "recover-counts"))
    parser.add_argument("candidate", nargs="?", default="R209")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--policy", help="Prospective canonical three-universe policy JSON")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("operation requires the designated lane worktree")
    if args.operation == "diagnostic-manifest":
        value = projection("R209")
        files = [[item.project_path, item.content_sha256, item.byte_count] for item in value.source_files]
        row = dict(candidate_id="R209", project_name="131 ARV2 SIX RECENT COVERAGE R209 202508 202609",
                   backtest_name="ARV2 R209 recent coverage counts", kind="coverage", role="coverage",
                   projection_schema=value.schema, projection_sha256=value.projection_sha256,
                   profile_id=value.profile_id, profile_sha256=value.profile_sha256,
                   source_files_sha256=hashlib.sha256(common._canonical(files)).hexdigest(),
                   source_file_count=len(files), total_source_bytes=value.total_source_byte_count,
                   statistic_names=list(value.statistic_names), meta_schema=coverage_projection.META_SCHEMA,
                   summary_schema=coverage_projection.SLEEVE_SCHEMA, sleeve_schema=coverage_projection.SLEEVE_SCHEMA)
        print(json.dumps(dict(schema="arv2-relaxed-family-freeze-v1", package_sha256=value.package_sha256,
            activation_manifest_sha256=value.activation_manifest_sha256,
            input_control_directory=str(ROOT / "artifacts/analyst_revisions_v2/six_cap90_qc_control_20260923"),
            candidates=[row]), sort_keys=True, indent=2))
        return
    if args.operation == "order-manifest":
        from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
        policy = tuple(tuple(item) for item in json.loads(args.policy))
        family = adapter._manifest()
        if len(family["candidates"]) != 1:
            raise ValueError("order freeze requires the exact diagnostic-only predecessor")
        prior, current = packages()
        rows = list(family["candidates"])
        for offset, percent in enumerate(relaxed.TILT_PERCENTS, 210):
            value, profile = relaxed.build_relaxed_order_projection(prior, current, percent, policy)
            files = [[item.project_path, item.content_sha256, item.byte_count] for item in value.source_files]
            rows.append(dict(candidate_id=f"R{offset}", project_name=f"{offset - 78} ARV2 SIX RELAXED TILT{percent} R{offset} 202508 NOW",
                backtest_name=f"ARV2 R{offset} relaxed tilt{percent} recent", kind="order", role=value.role,
                projection_schema=value.schema, projection_sha256=value.projection_sha256,
                profile_id=value.profile_id, profile_sha256=value.profile_sha256,
                source_files_sha256=hashlib.sha256(common._canonical(files)).hexdigest(),
                source_file_count=len(files), total_source_bytes=value.total_source_byte_count,
                statistic_names=["ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES"],
                meta_schema=relaxed.META_SCHEMA, summary_schema=relaxed.SUMMARY_SCHEMAS[percent],
                tilt_fraction=profile["maximum_stock_weight_change_fraction"],
                matched_baseline_profile_sha256=profile["matched_baseline_profile_sha256"]))
        print(json.dumps({**family, "coverage_policy": [list(item) for item in policy],
            "candidates": rows}, sort_keys=True, indent=2))
        return
    api = coverage.production_client()
    organization = common._post(api, "projects/read", {"projectId": 36978919})["projects"][0]["organizationId"]
    plan = adapter.build_plan(args.candidate, organization, CONTROL, args.attempt)
    if args.operation == "preview":
        value = adapter.preview(plan, projection(args.candidate))
        print(json.dumps({key: value[key] for key in ("candidate_id", "attempt", "projection_sha256", "profile_sha256")}, sort_keys=True))
    elif args.operation == "launch":
        receipt = adapter.launch(plan, projection(args.candidate), api)
        print(json.dumps({key: receipt[key] for key in ("candidate_id", "attempt", "project_id", "backtest_id")}, sort_keys=True))
    else:
        receipt = common._read(adapter._path(plan, "launch"))
        if args.operation == "status":
            print(adapter.poll_status(plan, receipt, api))
        else:
            result = adapter.read_result_once(plan, receipt, api,
                recover_r209_transport=args.operation == "recover-counts")
            if args.candidate == "R209":
                report = {"run_valid": result["run_valid"],
                    "resolver_counts": result["meta"]["resolver_counts"],
                    "resolver_refusal_reasons": result["meta"]["resolver_refusal_reasons"],
                    "sleeves": {ticker: value["totals"] for ticker, value in result["sleeves"].items()}}
            else:
                report = result
            print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
