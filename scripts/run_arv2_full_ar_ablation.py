"""Order-based total AR ablation: entry, stock count and weight tilt together.

Same all-six 25% coverage, verified identities, inputs, dates and execution
economics. The AR-on arm reproduces R222 exactly; this is exploratory, not
an ETF-outperformance or formal-alpha test.
"""

import argparse
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_arv2_relaxed_research import packages
from scripts.run_arv2_weight_ablation import authenticated_cached_result
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as projection
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common

CONTROL = ROOT / "artifacts/analyst_revisions_v2/six_full_ar_ablation_qc_control_20260926"
CANDIDATES = {"R223": False, "R224": True}
PROTOCOL = {
    "first_session": "2025-08-01", "last_session": "2026-09-25",
    "observation_count": 290, "decision_count": 61,
    "target_gross_exposure": "0.98", "direct_name_cap": "0.098",
    "admission_leverage": "2", "cost_bps_per_side": "10",
    "stock_baseline": "verified_cap_desc_sid_top10_equal_slots",
    "unresolved_budget": "ALL_SIX_verified_weight_partial_budget_residual_own_ETF",
    "comparison": "total_AR_entry_count_and_weight_not_weight_only",
}


def projected(candidate):
    prior, current = packages()
    return projection.build_full_ar_ablation_projection(prior, current, CANDIDATES[candidate])


def freeze():
    predecessor = adapter._coverage25_manifest()
    rows = []
    for index, (candidate, enabled) in enumerate(CANDIDATES.items(), 145):
        value, profile = projected(candidate)
        sources = {item.project_path: item.source_bytes.decode("ascii") for item in value.source_files}
        with projection._cloud_loader(sources) as (load, _):
            runtime = load(projection._TILT_RUNTIME_PATH[:-3])
            meta_schema, summary_schema = runtime.TILT_META_SCHEMA, runtime.TILT_SUMMARY_SCHEMA
        files = [[item.project_path, item.content_sha256, item.byte_count] for item in value.source_files]
        label = "ON100" if enabled else "OFF"
        rows.append(dict(candidate_id=candidate,
            project_name=f"{index} ARV2 SIX FULL AR {label} {candidate} 202508 NOW",
            backtest_name=f"ARV2 {candidate} full AR {label} recent", kind="order", role=value.role,
            analyst_revision_enabled=enabled,
            projection_schema=value.schema, projection_sha256=value.projection_sha256,
            profile_id=value.profile_id, profile_sha256=value.profile_sha256,
            source_files_sha256=hashlib.sha256(common._canonical(files)).hexdigest(),
            source_file_count=len(files), total_source_bytes=value.total_source_byte_count,
            statistic_names=["ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES"],
            meta_schema=meta_schema, summary_schema=summary_schema,
            tilt_fraction=profile["maximum_stock_weight_change_fraction"],
            matched_baseline_profile_sha256=profile["matched_baseline_profile_sha256"]))
    return dict(schema="arv2-six-full-ar-ablation-family-v1",
        package_sha256=predecessor["package_sha256"],
        activation_manifest_sha256=predecessor["activation_manifest_sha256"],
        input_control_directory=predecessor["input_control_directory"],
        coverage_policy=predecessor["coverage_policy"], protocol=PROTOCOL,
        candidates=rows, predecessor_manifest_sha256=adapter.FROZEN_COVERAGE25_MANIFEST_SHA256)


def compare_cached():
    family = adapter._full_ar_ablation_manifest()
    if family.get("protocol") != PROTOCOL:
        raise ValueError("full AR comparison protocol changed")
    results = {candidate: authenticated_cached_result(candidate, CONTROL, "full_ar_ablation")
               for candidate in CANDIDATES}
    off, on = (results[candidate] for candidate in CANDIDATES)
    for result in results.values():
        if result.get("run_valid") is not True:
            raise ValueError("full AR comparison requires two valid order results")
        aggregates = result["aggregates"]
        for key in ("target_gross_exposure", "admission_leverage"):
            if aggregates.get(key) != PROTOCOL[key]:
                raise ValueError("full AR comparison execution geometry changed")
    for key in ("observation_count", "first_observation_session", "last_observation_session", "starting_equity"):
        if off["aggregates"]["account"][key] != on["aggregates"]["account"][key]:
            raise ValueError("full AR comparison account observations differ")
    common_census = ("pit_callback_source_row_count", "reference_history_call_count",
        "fundamental_snapshot_unavailable_decision_count", "constituent_collection_unavailable_decision_count",
        "constituent_collection_unavailable_universe_counts")
    if any(off["aggregates"][key] != on["aggregates"][key] for key in common_census):
        raise ValueError("full AR comparison non-AR source census differs")
    off_rows = off["aggregates"]["sleeve_diagnostics"]["rows"]
    on_rows = on["aggregates"]["sleeve_diagnostics"]["rows"]
    if any(left[:5] != right[:5] or left[10] != right[10] for left, right in zip(off_rows, on_rows)):
        raise ValueError("full AR comparison non-AR coverage differs")
    # Entry/count removal intentionally changes stock targets, fallback counts,
    # baseline profiles and paths. Equality there is not required for ablation.
    with localcontext() as context:
        context.prec = 96
        spread = (Decimal(on["aggregates"]["account"]["cumulative_return"])
                  - Decimal(off["aggregates"]["account"]["cumulative_return"])) * 100
    return {"comparison_valid": True, "weight_tilt_only": False,
        "total_analyst_revision_ablation": True, "formal_alpha": False,
        "net_return_spread_percentage_points": str(spread),
        "arms": {candidate: {"analyst_revision_enabled": CANDIDATES[candidate],
            "account": result["aggregates"]["account"],
            "execution": result["aggregates"]["execution"],
            "sleeve_diagnostics": result["aggregates"]["sleeve_diagnostics"]}
            for candidate, result in results.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "preview", "launch", "status", "read", "compare"))
    parser.add_argument("candidate", nargs="?", choices=tuple(CANDIDATES), default="R223")
    parser.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("operation requires the designated lane worktree")
    if args.operation in ("freeze", "compare"):
        print(json.dumps(freeze() if args.operation == "freeze" else compare_cached(), sort_keys=True, indent=2))
        return
    api = credentials.production_client()
    organization = common._post(api, "projects/read", {"projectId": 36998897})["projects"][0]["organizationId"]
    plan = adapter.build_plan(args.candidate, organization, CONTROL, args.attempt, family="full_ar_ablation")
    if args.operation == "preview":
        value = adapter.preview(plan, projected(args.candidate)[0])
        print(json.dumps({key: value[key] for key in ("candidate_id", "attempt", "projection_sha256", "profile_sha256")}, sort_keys=True))
    elif args.operation == "launch":
        value = adapter.launch(plan, projected(args.candidate)[0], api)
        print(json.dumps({key: value[key] for key in ("candidate_id", "attempt", "project_id", "backtest_id")}, sort_keys=True))
    else:
        receipt = common._read(adapter._path(plan, "launch"))
        if args.operation == "status":
            print(adapter.poll_status(plan, receipt, api))
        else:
            print(json.dumps(adapter.read_result_once(plan, receipt, api), sort_keys=True))


if __name__ == "__main__":
    main()
