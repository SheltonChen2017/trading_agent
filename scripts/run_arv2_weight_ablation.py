"""Exact order-based 0/100 weight ablation; AR entry gates remain in both arms."""

import argparse
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_arv2_relaxed_research import packages
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as projection
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from research.analyst_revisions_v2_qc import six_universe_coverage_submission as credentials
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as common

CONTROL = ROOT / "artifacts/analyst_revisions_v2/six_weight_ablation_qc_control_20260926"
PAIR = {"R220": 0, "R221": 100}
CANDIDATES = {**PAIR, "R222": 100}


def projected(candidate):
    prior, current = packages()
    if candidate == "R222":
        return projection.build_all25_order_projection(prior, current, 100)
    policy = tuple(tuple(item) for item in adapter._manifest()["coverage_policy"])
    return projection.build_weight_ablation_projection(prior, current, CANDIDATES[candidate], policy)


def freeze(*, all25=False):
    predecessor = adapter._manifest()
    rows = []
    for candidate, percent in ({"R222": 100} if all25 else PAIR).items():
        value, profile = projected(candidate)
        files = [[item.project_path, item.content_sha256, item.byte_count] for item in value.source_files]
        rows.append(dict(candidate_id=candidate,
            project_name=(f"144 ARV2 SIX COVERAGE25 TILT100 R222 202508 NOW" if all25 else
                f"{int(candidate[1:]) - 78} ARV2 SIX WEIGHT ABLATION TILT{percent} {candidate} 202508 NOW"),
            backtest_name=("ARV2 R222 all-six coverage25 tilt100 recent" if all25 else
                f"ARV2 {candidate} weight ablation tilt{percent} recent"), kind="order", role=value.role,
            projection_schema=value.schema, projection_sha256=value.projection_sha256,
            profile_id=value.profile_id, profile_sha256=value.profile_sha256,
            source_files_sha256=hashlib.sha256(common._canonical(files)).hexdigest(),
            source_file_count=len(files), total_source_bytes=value.total_source_byte_count,
            statistic_names=["ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES"],
            meta_schema=(projection.ALL25_META_SCHEMA if all25 else projection.META_SCHEMA),
            summary_schema=(projection.ALL25_SUMMARY_SCHEMA if all25 else
                f"arv2-six-universe-order-tilt{percent}-recent-summary-v1-relaxed-v1"),
            tilt_fraction=profile["maximum_stock_weight_change_fraction"],
            matched_baseline_profile_sha256=profile["matched_baseline_profile_sha256"]))
    return dict(schema=("arv2-six-coverage25-family-v1" if all25 else "arv2-six-weight-ablation-family-v1"),
        package_sha256=predecessor["package_sha256"],
        activation_manifest_sha256=predecessor["activation_manifest_sha256"],
        input_control_directory=predecessor["input_control_directory"],
        coverage_policy=([list(item) for item in projection._selection.ALL25_COVERAGE_POLICY]
            if all25 else predecessor["coverage_policy"]), candidates=rows,
        comparison=("all_six_25pct_coverage_100pct_tilt_selection_change_not_AR_ablation" if all25 else
            "same_selection_weight_tilt_only_AR_entry_and_count_retained"),
        predecessor_manifest_sha256=adapter.FROZEN_MANIFEST_SHA256)


def compare_cached():
    results = {}
    for candidate in PAIR:
        for attempt in range(3, 0, -1):
            path = CONTROL / f"{candidate}-A{attempt}-result.json"
            if path.is_file():
                plan = adapter.build_plan(candidate, "a" * 32, CONTROL, attempt,
                    family="weight_ablation")
                launch = common._read(adapter._path(plan, "launch"))
                identity = adapter._receipt(plan, launch)
                expected = {"candidate_id": candidate, "attempt": attempt,
                    "project_id": launch["project_id"], "backtest_id": launch["backtest_id"],
                    "status": "Completed."}
                if (common._read(adapter._path(plan, "terminal")) != expected
                        or common._read(adapter._path(plan, "read-claim")) != expected):
                    raise ValueError("comparison cached terminal or result-read claim changed")
                raw = adapter._read_artifact(adapter._path(plan, "raw-custom"))
                row = adapter._candidate(plan)
                if (set(raw) != set(expected) | {"statistics"}
                        or any(raw.get(key) != value for key, value in expected.items())
                        or type(raw.get("statistics")) is not dict
                        or set(raw["statistics"]) != set(row["statistic_names"])):
                    raise ValueError("comparison cached raw-statistic identity changed")
                parsed = adapter._parse_order(plan, raw["statistics"])
                result = adapter._read_artifact(path)
                if result != {**expected, **parsed,
                        "manifest_sha256": identity["manifest_sha256"],
                        "projection_sha256": row["projection_sha256"]}:
                    raise ValueError("comparison cached arm differs from authenticated statistics")
                results[candidate] = result
                break
        else:
            raise ValueError("comparison lacks a completed result")
    off, on = (results[candidate] for candidate in PAIR)
    for result in results.values():
        if result.get("run_valid") is not True:
            raise ValueError("comparison requires two valid order results")
    fields = ("matched_baseline_profile_sha256", "matched_baseline_target_path_sha256", "sleeve_diagnostics",
              "target_gross_exposure", "admission_leverage")
    if any(off["aggregates"].get(key) != on["aggregates"].get(key) for key in fields):
        raise ValueError("same-selection weight comparison is not matched")
    for key in ("observation_count", "first_observation_session", "last_observation_session", "starting_equity"):
        if off["aggregates"]["account"][key] != on["aggregates"]["account"][key]:
            raise ValueError("same-selection observation or account geometry differs")
    with localcontext() as context:
        context.prec = 96
        spread = (Decimal(on["aggregates"]["account"]["cumulative_return"])
                  - Decimal(off["aggregates"]["account"]["cumulative_return"])) * 100
    return {"comparison_valid": True, "weight_tilt_only": True,
            "analyst_entry_and_count_gates_retained": True, "net_return_spread_percentage_points": str(spread),
            "matched_baseline_target_path_sha256": off["aggregates"]["matched_baseline_target_path_sha256"],
            "arms": {candidate: {"tilt_percent": CANDIDATES[candidate],
                "account": result["aggregates"]["account"], "execution": result["aggregates"]["execution"]}
                for candidate, result in results.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "freeze25", "preview", "launch", "status", "read", "compare"))
    parser.add_argument("candidate", nargs="?", choices=tuple(CANDIDATES), default="R220")
    parser.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT or ROOT.name != "trading_agent__analyst_revisions_v2":
        raise ValueError("operation requires the designated lane worktree")
    if args.operation in ("freeze", "freeze25", "compare"):
        print(json.dumps(compare_cached() if args.operation == "compare" else
            freeze(all25=args.operation == "freeze25"), sort_keys=True, indent=2))
        return
    api = credentials.production_client()
    organization = common._post(api, "projects/read", {"projectId": 36983178})["projects"][0]["organizationId"]
    plan = adapter.build_plan(args.candidate, organization, CONTROL, args.attempt,
        family="coverage25" if args.candidate == "R222" else "weight_ablation")
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
