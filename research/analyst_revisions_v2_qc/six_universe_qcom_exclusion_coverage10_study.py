"""Separate 2021--2025 QCOM-excluded, all-six 10% coverage sensitivity.

Four physical-order arms share the historical package, modeled fees, and
zero-slippage execution. The 25% arms may be shown only as construction
context after their own result authentication and a matched source-panel
census; a changed membership path is expected when admission is eased.
"""

from decimal import Decimal, localcontext

from . import accepted_risk_delta_order_package as delta
from . import accepted_risk_matched_diagnostics as diagnostics
from . import six_universe_qcom_exclusion_study as predecessor
from . import six_universe_qcom_exclusion_tilt_study as tilt
from . import six_universe_relaxed_submission as adapter


FAMILY = "qcom_exclusion_coverage10"
MANIFEST_SCHEMA = "arv2-six-qcom-excluded-coverage10-historical-study-v1"
COVERAGE_POLICY_ID = "all_six_minimum_mapping_cap_total_10pct_verified_names_5_v1"
CANDIDATES = {"R238": "ar_off", "R239": "ar_on80", "R240": "ar_on120",
              "R241": "ar_on200"}
CONTEXT_25PCT = {"R238": "R231", "R239": "R235", "R240": "R236",
                 "R241": "R237"}
TILT_FRACTIONS = {"ar_off": "0.00", "ar_on80": "0.80",
                  "ar_on120": "1.20", "ar_on200": "2.00"}
EXPECTED_PROJECTION_SHA256 = {
    "ar_off": "26e4680967e6f4a6bc66b0fe7c3e4198cdab1db2f1a7357878f01952560fd654",
    "ar_on80": "b3037679192d13cd931f22dd27ff7443ea328d17a7bed5d294bed3754f97dc9d",
    "ar_on120": "bf62a1fcf62bee8d63a739d88220a8d8764a30b889baaa1bca0ef025a7264f4f",
    "ar_on200": "ddaf84b437d347f43f789377b9629f90120d8418edfed3e7c596cfecf7e33f18",
}
EXPECTED_PROFILE_SHA256 = {
    "ar_off": "347b5fc991e49873af17242d02e3f10c3ad96305b9ad19dab0665b9a13bd145d",
    "ar_on80": "ba0992f1b35b184b9ba87b49f5f2cb0622e8aaf03bab81b9ba11ac58fb9690af",
    "ar_on120": "118e83a0aa53a792e169aea2dad7af007f56dbefa496ff9e6f150e510c68b0bf",
    "ar_on200": "af27b27e22f565a1ded18ad55b0e29705f87b803753a4fb3d9dc1433281689c7",
}
EXPECTED_BASELINE_PROFILE_SHA256 = {
    "ar_off": "bcbd6763067e14e29b53293e8cfd5a649f09153ebbfe4613158de0c4c7319a70",
    "ar_on80": "63600ecfca20e318f3bc65eb0dac0ad94ecc8a00f2559c27b35d21f8d8530949",
    "ar_on120": "63600ecfca20e318f3bc65eb0dac0ad94ecc8a00f2559c27b35d21f8d8530949",
    "ar_on200": "63600ecfca20e318f3bc65eb0dac0ad94ecc8a00f2559c27b35d21f8d8530949",
}
STATISTIC_NAMES = ["ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES",
                   predecessor.DIAGNOSTIC_NAME]
PROTOCOL = {**predecessor.PROTOCOL,
    "slippage_bps": [0],
    "selection_policy": "all_six_10pct_verified_subset_top10_equal_slots_residual_own_ETF",
    "coverage_policy_id": COVERAGE_POLICY_ID,
    "minimum_name_mapping_coverage": "0.10",
    "minimum_market_cap_weight_coverage": "0.10",
    "minimum_total_reported_weight": "0.10",
    "minimum_verified_name_count": 5,
    "comparison": "QCOM_excluded_coverage10_AR_off_vs_on80_on120_on200_with_25pct_context",
    "context_25pct_candidates": CONTEXT_25PCT,
}
_ROW_FIELDS = predecessor._ROW_FIELDS | {"coverage_policy_id"}
_COMMON_SOURCE_CENSUS = tilt._COMMON_SOURCE_CENSUS


def _digest(value):
    return type(value) is str and adapter.cap._HEX.fullmatch(value) is not None


def validate_manifest(value):
    """Refuse old-family aliases, changed economics, or incomplete disclosures."""
    if (type(value) is not dict
            or set(value) != {"schema", "protocol", "package_sha256",
                              "activation_manifest_sha256", "candidates"}
            or value["schema"] != MANIFEST_SCHEMA
            or type(value["protocol"]) is not dict or value["protocol"] != PROTOCOL
            or value["protocol"].get("confirmation") is not False
            or value["protocol"].get("capacity_search") is not False
            or value["protocol"].get("sensitivity_only") is not True
            or value["package_sha256"] != delta.EXPECTED_DELTA_PACKAGE_SHA256
            or value["activation_manifest_sha256"] != predecessor.HISTORICAL_ACTIVATION_SHA256
            or type(value["candidates"]) is not list
            or len(value["candidates"]) != len(CANDIDATES)):
        adapter._fail("QCOM-excluded coverage10 protocol or historical input changed")
    projects, backtests, projections, profiles, sources = set(), set(), set(), set(), set()
    for row, (candidate, arm) in zip(value["candidates"], CANDIDATES.items()):
        stem = f"arv2-six-matched-qcom-excluded-coverage10-{arm}"
        if (type(row) is not dict or set(row) != _ROW_FIELDS
                or row["candidate_id"] != candidate or row["arm"] != arm
                or type(row["slippage_bps"]) is not int or row["slippage_bps"] != 0
                or row["kind"] != "order" or row["tilt_fraction"] != TILT_FRACTIONS[arm]
                or row["coverage_policy_id"] != COVERAGE_POLICY_ID
                or row["role"] != f"matched_qcom_excluded_coverage10_{arm}_s0"
                or row["profile_id"] != stem + "-s0-profile-v1"
                or row["projection_schema"] != stem + "-projection-v1"
                or row["meta_schema"] != stem + "-meta-v1"
                or row["summary_schema"] != stem + "-summary-v1"
                or row["projection_sha256"] != EXPECTED_PROJECTION_SHA256[arm]
                or row["profile_sha256"] != EXPECTED_PROFILE_SHA256[arm]
                or row["matched_baseline_profile_sha256"]
                    != EXPECTED_BASELINE_PROFILE_SHA256[arm]
                or row["reference_repair_enabled"] is not True
                or row["excluded_stock_security_id_sha256"]
                    != predecessor.EXCLUDED_STOCK_SECURITY_ID_SHA256
                or row["statistic_names"] != STATISTIC_NAMES
                or type(row["source_file_count"]) is not int
                or row["source_file_count"] != 17
                or type(row["total_source_bytes"]) is not int
                or not 0 < row["total_source_bytes"] < 448 * 1024
                or any(not _digest(row[key]) for key in (
                    "profile_sha256", "projection_sha256", "source_files_sha256",
                    "matched_baseline_profile_sha256"))
                or type(row["project_name"]) is not str or not row["project_name"]
                or type(row["backtest_name"]) is not str or not row["backtest_name"]
                or candidate not in row["project_name"] or candidate not in row["backtest_name"]
                or row["project_name"] in projects or row["backtest_name"] in backtests
                or row["projection_sha256"] in projections
                or row["profile_sha256"] in profiles
                or row["source_files_sha256"] in sources):
            adapter._fail("QCOM-excluded coverage10 candidate or source disclosure changed")
        projects.add(row["project_name"])
        backtests.add(row["backtest_name"])
        projections.add(row["projection_sha256"])
        profiles.add(row["profile_sha256"])
        sources.add(row["source_files_sha256"])
    return value


def parse_order(plan, statistics):
    """Bind the new coverage policy and QCOM exclusion to one-use results."""
    row = adapter._candidate(plan)
    if (plan.family != FAMILY or row["candidate_id"] not in CANDIDATES
            or set(statistics) != set(STATISTIC_NAMES)):
        adapter._fail("QCOM-excluded coverage10 result family or inventory changed")
    parsed = adapter._parse_order_common(plan, statistics, expected_geometry=None,
        decision_count=PROTOCOL["decision_count"],
        extra_meta_fields=frozenset({"matched_diagnostics_sha256"}),
        extra_aggregate_fields=frozenset({"comparison_arm", "analyst_revision_economic_usage",
            "stock_exclusion_policy_id", "excluded_logical_security_sha256",
            "coverage_policy_id"}),
        result_transport="three_bounded_custom_summary_statistics")
    aggregate = parsed["aggregates"]
    if (aggregate.get("comparison_arm") != row["arm"]
            or aggregate.get("analyst_revision_economic_usage") != (
                "none_authenticated_score_clock_only" if row["arm"] == "ar_off"
                else "entry_count_and_weight")
            or aggregate.get("stock_exclusion_policy_id") != predecessor.EXCLUSION_RULE
            or aggregate.get("excluded_logical_security_sha256")
                != predecessor.EXCLUDED_STOCK_SECURITY_ID_SHA256
            or aggregate.get("coverage_policy_id") != COVERAGE_POLICY_ID):
        adapter._fail("QCOM-excluded coverage10 economics or policy identity changed")
    report = adapter._statistic(statistics[predecessor.DIAGNOSTIC_NAME])
    if parsed["meta"].get("matched_diagnostics_sha256") != adapter._sha(report):
        adapter._fail("QCOM-excluded coverage10 diagnostic digest changed")
    diagnostics.validate_report(report, "ar_off" if row["arm"] == "ar_off" else "ar_on100",
                                0, reference_repair_enabled=True)
    if report["overall_cumulative_return"] != aggregate["account"]["cumulative_return"]:
        adapter._fail("QCOM-excluded coverage10 diagnostic/account return differs")
    return {**parsed, "diagnostics": report}


def _validated_new_results(results):
    if type(results) is not dict or list(results) != list(CANDIDATES):
        raise ValueError("coverage10 comparison requires exactly four new stock arms")
    manifest = adapter._qcom_exclusion_coverage10_manifest()
    for row in manifest["candidates"]:
        candidate, arm = row["candidate_id"], row["arm"]
        result = results[candidate]
        if (type(result) is not dict or result.get("run_valid") is not True
                or result.get("candidate_id") != candidate
                or type(result.get("attempt")) is not int or not 1 <= result["attempt"] <= 3
                or result.get("status") != "Completed."
                or result.get("manifest_sha256")
                    != adapter.FROZEN_QCOM_EXCLUSION_COVERAGE10_MANIFEST_SHA256
                or result.get("projection_sha256") != row["projection_sha256"]):
            raise ValueError("coverage10 comparison requires authenticated completed arms")
        aggregate, report = result.get("aggregates"), result.get("diagnostics")
        if type(aggregate) is not dict or type(report) is not dict:
            raise ValueError("coverage10 aggregate or diagnostics missing")
        diagnostics.validate_report(report, "ar_off" if arm == "ar_off" else "ar_on100",
                                    0, reference_repair_enabled=True)
        account, execution = aggregate.get("account"), aggregate.get("execution")
        if (type(account) is not dict or type(execution) is not dict
                or aggregate.get("comparison_arm") != arm
                or aggregate.get("analyst_revision_economic_usage") != (
                    "none_authenticated_score_clock_only" if arm == "ar_off"
                    else "entry_count_and_weight")
                or aggregate.get("coverage_policy_id") != COVERAGE_POLICY_ID
                or aggregate.get("stock_exclusion_policy_id") != predecessor.EXCLUSION_RULE
                or aggregate.get("excluded_logical_security_sha256")
                    != predecessor.EXCLUDED_STOCK_SECURITY_ID_SHA256
                or aggregate.get("maximum_stock_weight_change_fraction") != row["tilt_fraction"]
                or aggregate.get("matched_baseline_profile_sha256")
                    != row["matched_baseline_profile_sha256"]
                or aggregate.get("target_gross_exposure") != PROTOCOL["target_gross_exposure"]
                or aggregate.get("admission_leverage") != PROTOCOL["admission_leverage"]
                or type(execution.get("submitted_rebalance_count")) is not int
                or execution["submitted_rebalance_count"] != PROTOCOL["decision_count"]
                or type(execution.get("completed_rebalance_count")) is not int
                or execution["completed_rebalance_count"] != PROTOCOL["decision_count"]
                or type(account.get("observation_count")) is not int
                or account["observation_count"] != PROTOCOL["observation_count"]
                or account.get("first_observation_session") != PROTOCOL["first_session"]
                or account.get("last_observation_session") != PROTOCOL["last_session"]
                or not adapter.cap._finite_decimal(account.get("starting_equity"))
                or Decimal(account["starting_equity"]) <= 0
                or not adapter.cap._finite_decimal(account.get("cumulative_return"))
                or account["cumulative_return"] != report["overall_cumulative_return"]
                or any(not _digest(report.get(key)) for key in (
                    "membership_cap_path_sha256", "etf_daily_panel_sha256"))):
            raise ValueError("coverage10 arm economics, source, or geometry differs")
    reference = results["R238"]
    for result in results.values():
        if result["aggregates"]["account"]["starting_equity"] != reference["aggregates"]["account"]["starting_equity"]:
            raise ValueError("coverage10 starting capital differs")
        for key in ("membership_cap_path_sha256", "etf_daily_panel_sha256"):
            if result["diagnostics"][key] != reference["diagnostics"][key]:
                raise ValueError("coverage10 source vintage differs within the four-arm family")
        for key in _COMMON_SOURCE_CENSUS:
            if result["aggregates"].get(key) != reference["aggregates"].get(key):
                raise ValueError("coverage10 non-AR source census differs")


def compare_results(results, context_25pct=None):
    """Compute descriptive net spreads; check old-arm context separately."""
    _validated_new_results(results)
    off = Decimal(results["R238"]["aggregates"]["account"]["cumulative_return"])
    with localcontext() as context:
        context.prec = 96
        comparisons = [{"candidate_id": candidate, "arm": arm,
            "AR_on_minus_coverage10_AR_off_percentage_points": str((Decimal(
                results[candidate]["aggregates"]["account"]["cumulative_return"]) - off) * 100)}
            for candidate, arm in CANDIDATES.items() if candidate != "R238"]
    output = {"comparison_valid": True, "formal_alpha": False, "confirmation": False,
        "sensitivity_only": True, "coverage_policy_id": COVERAGE_POLICY_ID,
        "excluded_stock_security_id_sha256": predecessor.EXCLUDED_STOCK_SECURITY_ID_SHA256,
        "reference_data_scope": "common_membership_caps_and_six_ETF_RAW_daily_panel_not_full_stock_minute_fill_tape",
        "comparisons": comparisons,
        "arms": {candidate: {"arm": arm, "account": results[candidate]["aggregates"]["account"],
            "execution": results[candidate]["aggregates"]["execution"],
            "diagnostics": results[candidate]["diagnostics"]}
            for candidate, arm in CANDIDATES.items()},
        "context_25pct": None}
    if context_25pct is None:
        return output
    if type(context_25pct) is not dict or list(context_25pct) != list(CONTEXT_25PCT.values()):
        raise ValueError("coverage10 context requires exactly four ordered 25% counterparts")
    # The old ladder authenticates its own manifest, economic mode, panel and
    # source census. Do not equate the 10% and 25% membership/cap path digests.
    tilt.compare_results(context_25pct)
    for new_id, old_id in CONTEXT_25PCT.items():
        new, old = results[new_id], context_25pct[old_id]
        if (new["diagnostics"]["etf_daily_panel_sha256"]
                != old["diagnostics"]["etf_daily_panel_sha256"]
                or new["aggregates"]["account"]["starting_equity"]
                    != old["aggregates"]["account"]["starting_equity"]
                or any(new["aggregates"].get(key) != old["aggregates"].get(key)
                       for key in _COMMON_SOURCE_CENSUS)):
            raise ValueError("coverage10 and 25% context lack a matched source panel or census")
    with localcontext() as context:
        context.prec = 96
        output["context_25pct"] = {"compatible": True,
            "membership_digest_equality_required": False,
            "construction_difference": "six minimum coverage floors 25% to 10%",
            "comparisons": [{"coverage10_candidate_id": new_id,
                "coverage25_candidate_id": old_id, "arm": CANDIDATES[new_id],
                "coverage10_minus_coverage25_percentage_points": str((Decimal(
                    results[new_id]["aggregates"]["account"]["cumulative_return"]) - Decimal(
                    context_25pct[old_id]["aggregates"]["account"]["cumulative_return"])) * 100)}
                for new_id, old_id in CONTEXT_25PCT.items()]}
    return output
