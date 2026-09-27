"""Prospective QCOM-excluded stock sensitivity, separate from R225--R230.

All four arms use the reviewed historical package and physical MOO orders.
QCOM stays in the authenticated source and coverage denominators, but cannot
enter a direct-stock target. This is a sensitivity test, not a repair of R225.
No cloud call or outcome read occurs on import.
"""

from decimal import Decimal, localcontext

from . import accepted_risk_delta_order_package as delta
from . import accepted_risk_matched_diagnostics as diagnostics
from . import six_universe_matched_study as original
from . import six_universe_relaxed_submission as adapter


MANIFEST_SCHEMA = "arv2-six-qcom-excluded-historical-study-v1"
HISTORICAL_ACTIVATION_SHA256 = original.HISTORICAL_ACTIVATION_SHA256
EXCLUDED_STOCK_SECURITY_ID_SHA256 = (
    "12e2fb85270ad4370a284866d825f3a6cf121a92c997c3557861e6d08a7a6a1f"
)
EXCLUSION_RULE = "qcom_stock_eligibility_after_coverage_v1"
CANDIDATES = {
    "R231": ("ar_off", 0), "R232": ("ar_on100", 0),
    "R233": ("ar_off", 5), "R234": ("ar_on100", 5),
}
PROTOCOL = {
    "first_session": "2021-01-04", "last_session": "2025-12-31",
    "observation_count": 1255, "decision_count": 261,
    "target_gross_exposure": "0.98", "admission_leverage": "2",
    "cost_bps_per_side": "10", "slippage_bps": [0, 5],
    "cadence": "weekly_prior_session_decision_next_open_MOO",
    "selection_policy": "all_six_25pct_verified_subset_top10_equal_slots_residual_own_ETF",
    "comparison": "QCOM_excluded_total_AR_entry_count_and_weights",
    "exclusion_rule": EXCLUSION_RULE,
    "excluded_stock_security_id_sha256": EXCLUDED_STOCK_SECURITY_ID_SHA256,
    "confirmation": False, "capacity_search": False, "sensitivity_only": True,
}
DIAGNOSTIC_NAME = original.DIAGNOSTIC_NAME
_ROW_FIELDS = frozenset({
    "arm", "backtest_name", "candidate_id", "excluded_stock_security_id_sha256",
    "kind", "matched_baseline_profile_sha256", "meta_schema", "profile_id",
    "profile_sha256", "project_name", "projection_schema", "projection_sha256",
    "reference_repair_enabled", "role", "slippage_bps", "source_file_count",
    "source_files_sha256", "statistic_names", "summary_schema",
    "tilt_fraction", "total_source_bytes",
})


def _digest(value):
    return type(value) is str and adapter.cap._HEX.fullmatch(value) is not None


def validate_manifest(value):
    """Reject a changed arm, source identity, exclusion or old-family alias."""
    if (type(value) is not dict
            or set(value) != {"schema", "protocol", "package_sha256",
                              "activation_manifest_sha256", "candidates"}
            or value["schema"] != MANIFEST_SCHEMA
            or type(value["protocol"]) is not dict or value["protocol"] != PROTOCOL
            or value["protocol"].get("confirmation") is not False
            or value["protocol"].get("capacity_search") is not False
            or value["protocol"].get("sensitivity_only") is not True
            or value["package_sha256"] != delta.EXPECTED_DELTA_PACKAGE_SHA256
            or value["activation_manifest_sha256"] != HISTORICAL_ACTIVATION_SHA256
            or type(value["candidates"]) is not list
            or len(value["candidates"]) != len(CANDIDATES)):
        adapter._fail("QCOM-excluded protocol or historical input changed")
    projects, backtests = set(), set()
    for row, (candidate, (arm, slippage)) in zip(value["candidates"], CANDIDATES.items()):
        if (type(row) is not dict or set(row) != _ROW_FIELDS
                or row["candidate_id"] != candidate or row["arm"] != arm
                or type(row["slippage_bps"]) is not int or row["slippage_bps"] != slippage
                or row["kind"] != "order"
                or row["tilt_fraction"] != ("1.00" if arm == "ar_on100" else "0.00")
                or row["reference_repair_enabled"] is not True
                or row["excluded_stock_security_id_sha256"] != EXCLUDED_STOCK_SECURITY_ID_SHA256
                or row["statistic_names"] != ["ARV2_SIX_GATE_ORDER_META",
                    "ARV2_SIX_GATE_ORDER_AGGREGATES", DIAGNOSTIC_NAME]
                or type(row["source_file_count"]) is not int or row["source_file_count"] != 17
                or type(row["total_source_bytes"]) is not int
                or not 0 < row["total_source_bytes"] < 448 * 1024
                or any(not _digest(row[field]) for field in (
                    "profile_sha256", "projection_sha256", "source_files_sha256",
                    "matched_baseline_profile_sha256"))
                or any(type(row[field]) is not str or not row[field] for field in (
                    "project_name", "backtest_name", "role", "profile_id",
                    "projection_schema", "meta_schema", "summary_schema"))
                or candidate not in row["project_name"] or candidate not in row["backtest_name"]
                or row["project_name"] in projects or row["backtest_name"] in backtests):
            adapter._fail("QCOM-excluded candidate census or source disclosure changed")
        projects.add(row["project_name"])
        backtests.add(row["backtest_name"])
    return value


def parse_order(plan, statistics):
    """Bind the new exclusion fields to the same three-statistic transport."""
    row = adapter._candidate(plan)
    if (plan.family != "qcom_exclusion"
            or row["excluded_stock_security_id_sha256"] != EXCLUDED_STOCK_SECURITY_ID_SHA256
            or set(statistics) != set(row["statistic_names"])):
        adapter._fail("QCOM-excluded result family or identity changed")
    parsed = adapter._parse_order_common(plan, statistics, expected_geometry=None,
        decision_count=PROTOCOL["decision_count"],
        extra_meta_fields=frozenset({"matched_diagnostics_sha256"}),
        extra_aggregate_fields=frozenset({"comparison_arm", "analyst_revision_economic_usage",
            "stock_exclusion_policy_id", "excluded_logical_security_sha256"}),
        result_transport="three_bounded_custom_summary_statistics")
    aggregate = parsed["aggregates"]
    if (aggregate.get("comparison_arm") != row["arm"]
            or aggregate.get("analyst_revision_economic_usage") != (
                "entry_count_and_weight" if row["arm"] == "ar_on100"
                else "none_authenticated_score_clock_only")
            or aggregate.get("stock_exclusion_policy_id") != EXCLUSION_RULE
            or aggregate.get("excluded_logical_security_sha256") != EXCLUDED_STOCK_SECURITY_ID_SHA256):
        adapter._fail("QCOM-excluded economic mode or security identity changed")
    report = adapter._statistic(statistics[DIAGNOSTIC_NAME])
    if parsed["meta"].get("matched_diagnostics_sha256") != adapter._sha(report):
        adapter._fail("QCOM-excluded diagnostic digest changed")
    diagnostics.validate_report(report, row["arm"], row["slippage_bps"],
        reference_repair_enabled=True)
    if report["overall_cumulative_return"] != aggregate["account"]["cumulative_return"]:
        adapter._fail("QCOM-excluded diagnostic/account return differs")
    return {**parsed, "diagnostics": report}


def compare_results(results):
    """Compare only the four new stock arms; legacy ETFs are context, not peers.

    Same source/panel digests do not prove equality of every stock minute fill.
    Different AR modes may deliberately have different holdings/target paths.
    """
    if type(results) is not dict or list(results) != list(CANDIDATES):
        raise ValueError("QCOM-excluded comparison requires exactly four new stock arms")
    for candidate, result in results.items():
        arm, slippage = CANDIDATES[candidate]
        if type(result) is not dict or result.get("run_valid") is not True:
            raise ValueError("QCOM-excluded comparison requires four valid order results")
        aggregate = result["aggregates"]
        account = aggregate["account"]
        report = result["diagnostics"]
        diagnostics.validate_report(report, arm, slippage, reference_repair_enabled=True)
        if (aggregate.get("comparison_arm") != arm
                or aggregate.get("analyst_revision_economic_usage") != (
                    "entry_count_and_weight" if arm == "ar_on100"
                    else "none_authenticated_score_clock_only")
                or aggregate.get("stock_exclusion_policy_id") != EXCLUSION_RULE
                or aggregate.get("excluded_logical_security_sha256") != EXCLUDED_STOCK_SECURITY_ID_SHA256
                or aggregate.get("target_gross_exposure") != PROTOCOL["target_gross_exposure"]
                or aggregate.get("admission_leverage") != PROTOCOL["admission_leverage"]
                or type(aggregate.get("execution")) is not dict
                or type(aggregate["execution"].get("decision_count")) is not int
                or aggregate["execution"]["decision_count"] != PROTOCOL["decision_count"]
                or type(account) is not dict
                or type(account.get("observation_count")) is not int
                or account["observation_count"] != PROTOCOL["observation_count"]
                or account.get("first_observation_session") != PROTOCOL["first_session"]
                or account.get("last_observation_session") != PROTOCOL["last_session"]
                or not adapter.cap._finite_decimal(account.get("starting_equity"))
                or Decimal(account["starting_equity"]) <= 0
                or not adapter.cap._finite_decimal(account.get("cumulative_return"))
                or account["cumulative_return"] != report["overall_cumulative_return"]):
            raise ValueError("QCOM-excluded arm economics or account geometry differs")
        for key in ("membership_cap_path_sha256", "etf_daily_panel_sha256"):
            if not _digest(report.get(key)):
                raise ValueError("QCOM-excluded source digest shape differs")
    reference = results["R231"]
    for result in results.values():
        if result["aggregates"]["account"]["starting_equity"] != reference["aggregates"]["account"]["starting_equity"]:
            raise ValueError("QCOM-excluded starting capital differs")
        for key in ("membership_cap_path_sha256", "etf_daily_panel_sha256"):
            if result["diagnostics"][key] != reference["diagnostics"][key]:
                raise ValueError("QCOM-excluded source vintage differs")
        for key in ("pit_callback_source_row_count", "fundamental_snapshot_unavailable_decision_count",
                    "constituent_collection_unavailable_decision_count",
                    "constituent_collection_unavailable_universe_counts"):
            if result["aggregates"].get(key) != reference["aggregates"].get(key):
                raise ValueError("QCOM-excluded non-AR source census differs")
    comparisons = []
    with localcontext() as context:
        context.prec = 96
        for slippage, off_id, on_id in ((0, "R231", "R232"), (5, "R233", "R234")):
            off = Decimal(results[off_id]["aggregates"]["account"]["cumulative_return"])
            on = Decimal(results[on_id]["aggregates"]["account"]["cumulative_return"])
            comparisons.append({"slippage_bps": slippage,
                "AR_on_minus_fully_off_percentage_points": str((on - off) * 100)})
    return {"comparison_valid": True, "formal_alpha": False, "confirmation": False,
        "sensitivity_only": True, "excluded_stock_security_id_sha256": EXCLUDED_STOCK_SECURITY_ID_SHA256,
        "legacy_R227_R230_ETF_controls_matched": False,
        "reference_data_scope": "common_membership_caps_and_six_ETF_RAW_daily_panel_not_full_stock_minute_fill_tape",
        "comparisons": comparisons,
        "arms": {candidate: {"arm": CANDIDATES[candidate][0],
            "slippage_bps": CANDIDATES[candidate][1], "account": result["aggregates"]["account"],
            "execution": result["aggregates"]["execution"], "diagnostics": result["diagnostics"]}
            for candidate, result in results.items()}}
