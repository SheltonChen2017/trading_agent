"""Separate QCOM-excluded, three-verified-name sensitivity, R242--R245.

This is an exploratory 2021--2025 physical-order comparison, not confirmation.
It retains the six 10% coverage floors and changes the verified-stock floor
from five to three; non-XLE stock entry also needs three positive AR scores.
The R238--R241 results are authenticated separately as construction context.
"""

from decimal import Decimal, localcontext

from . import accepted_risk_delta_order_package as delta
from . import accepted_risk_matched_diagnostics as diagnostics
from . import six_universe_qcom_exclusion_study as predecessor
from . import six_universe_qcom_exclusion_coverage10_study as coverage10
from . import six_universe_relaxed_submission as adapter


FAMILY = "qcom_exclusion_three_name"
MANIFEST_SCHEMA = "arv2-six-qcom-excluded-three-name-historical-study-v1"
COVERAGE_POLICY_ID = "all_six_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_3_v1"
CANDIDATES = {"R242": "ar_off", "R243": "ar_on80", "R244": "ar_on120",
              "R245": "ar_on200"}
CONTEXT_10PCT = {"R242": "R238", "R243": "R239", "R244": "R240",
                 "R245": "R241"}
TILT_FRACTIONS = coverage10.TILT_FRACTIONS
EXPECTED_PROJECTION_SHA256 = {
    "ar_off": "829c370e58ebd1d398cc62a0acd5aca29885487f0353a5ff0ab7157afeb58ced",
    "ar_on80": "ca4546db5e649d55da0fa266a8876760d487e7984559fc512d9c64bb0e42277d",
    "ar_on120": "f72bc3f00065d259af10480ce7c2a99f55826da8ab419b50aab6529c7194b10c",
    "ar_on200": "954aeea6c375659d7dfd6d8357cde1a70623287f4cdc7581f4e3a4070a650e35",
}
EXPECTED_PROFILE_SHA256 = {
    "ar_off": "df467b66aea1852f0863e5a8a30a5aac48e4d42eb6f693315805fa90a20cc88f",
    "ar_on80": "d658ca16667a09aa11b3e631a5bebc618b1b6dc6cec93ea9286471a8bfec7d18",
    "ar_on120": "d068b0d9795f0b636ba8c90a6cfbdcd657a6839b8830fbb3c83a80bd5eba3ea7",
    "ar_on200": "17674a77ce2fc2efd0bb7206abc0f85f05f4b9527b324466f4e03e1f686c33f0",
}
EXPECTED_BASELINE_PROFILE_SHA256 = {
    "ar_off": "a8a3c74b9558e462a61fb347c7ed1fb2f5e6b5b38dedaa925b50d800258de092",
    "ar_on80": "e656cab31548624aec270c9c7c3cad1bafbb55461a90efe42d29bb930cafe88e",
    "ar_on120": "e656cab31548624aec270c9c7c3cad1bafbb55461a90efe42d29bb930cafe88e",
    "ar_on200": "e656cab31548624aec270c9c7c3cad1bafbb55461a90efe42d29bb930cafe88e",
}
STATISTIC_NAMES = coverage10.STATISTIC_NAMES
PROTOCOL = {**coverage10.PROTOCOL,
    "selection_policy": "all_six_10pct_verified_three_top10_equal_slots_residual_own_ETF",
    "coverage_policy_id": COVERAGE_POLICY_ID,
    "minimum_verified_name_count": 3,
    "minimum_non_xle_positive_ar_score_count": 3,
    "comparison": "QCOM_excluded_three_name_AR_off_vs_on80_on120_on200_with_10pct_context",
    "context_10pct_candidates": CONTEXT_10PCT,
}
PROTOCOL.pop("context_25pct_candidates")
_ROW_FIELDS = coverage10._ROW_FIELDS
_COMMON_SOURCE_CENSUS = coverage10._COMMON_SOURCE_CENSUS


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
        adapter._fail("QCOM-excluded three-name protocol or historical input changed")
    projects, backtests, projections, profiles, sources = set(), set(), set(), set(), set()
    for row, (candidate, arm) in zip(value["candidates"], CANDIDATES.items()):
        stem = f"arv2-six-matched-qcom-excluded-three-name-{arm}"
        if (type(row) is not dict or set(row) != _ROW_FIELDS
                or row["candidate_id"] != candidate or row["arm"] != arm
                or type(row["slippage_bps"]) is not int or row["slippage_bps"] != 0
                or row["kind"] != "order" or row["tilt_fraction"] != TILT_FRACTIONS[arm]
                or row["coverage_policy_id"] != COVERAGE_POLICY_ID
                or row["role"] != f"matched_qcom_excluded_three_name_{arm}_s0"
                or row["profile_id"] != stem + "-s0-profile-v1"
                or row["projection_schema"] != stem + "-projection-v1"
                or row["meta_schema"] != stem + "-meta-v1"
                or row["summary_schema"] != stem + "-summary-v1"
                or row["projection_sha256"] != EXPECTED_PROJECTION_SHA256.get(arm)
                or row["profile_sha256"] != EXPECTED_PROFILE_SHA256.get(arm)
                or row["matched_baseline_profile_sha256"]
                    != EXPECTED_BASELINE_PROFILE_SHA256.get(arm)
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
            adapter._fail("QCOM-excluded three-name candidate or source disclosure changed")
        projects.add(row["project_name"])
        backtests.add(row["backtest_name"])
        projections.add(row["projection_sha256"])
        profiles.add(row["profile_sha256"])
        sources.add(row["source_files_sha256"])
    return value


def parse_order(plan, statistics):
    """Bind the three-name policy and QCOM exclusion to a one-use result."""
    row = adapter._candidate(plan)
    if (plan.family != FAMILY or row["candidate_id"] not in CANDIDATES
            or set(statistics) != set(STATISTIC_NAMES)):
        adapter._fail("QCOM-excluded three-name result family or inventory changed")
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
        adapter._fail("QCOM-excluded three-name economics or policy identity changed")
    report = adapter._statistic(statistics[predecessor.DIAGNOSTIC_NAME])
    if parsed["meta"].get("matched_diagnostics_sha256") != adapter._sha(report):
        adapter._fail("QCOM-excluded three-name diagnostic digest changed")
    diagnostics.validate_report(report, "ar_off" if row["arm"] == "ar_off" else "ar_on100",
                                0, reference_repair_enabled=True)
    if report["overall_cumulative_return"] != aggregate["account"]["cumulative_return"]:
        adapter._fail("QCOM-excluded three-name diagnostic/account return differs")
    return {**parsed, "diagnostics": report}


def _validated_results(results):
    if type(results) is not dict or list(results) != list(CANDIDATES):
        raise ValueError("three-name comparison requires exactly four new stock arms")
    manifest = adapter._qcom_exclusion_three_name_manifest()
    for row in manifest["candidates"]:
        candidate, arm = row["candidate_id"], row["arm"]
        result = results[candidate]
        if (type(result) is not dict or result.get("run_valid") is not True
                or result.get("candidate_id") != candidate
                or type(result.get("attempt")) is not int or not 1 <= result["attempt"] <= 3
                or result.get("status") != "Completed."
                or result.get("manifest_sha256")
                    != adapter.FROZEN_QCOM_EXCLUSION_THREE_NAME_MANIFEST_SHA256
                or result.get("projection_sha256") != row["projection_sha256"]):
            raise ValueError("three-name comparison requires authenticated completed arms")
        aggregate, report = result.get("aggregates"), result.get("diagnostics")
        if type(aggregate) is not dict or type(report) is not dict:
            raise ValueError("three-name aggregate or diagnostics missing")
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
            raise ValueError("three-name arm economics, source, or geometry differs")
    reference = results["R242"]
    for result in results.values():
        if result["aggregates"]["account"]["starting_equity"] != reference["aggregates"]["account"]["starting_equity"]:
            raise ValueError("three-name starting capital differs")
        for key in ("membership_cap_path_sha256", "etf_daily_panel_sha256"):
            if result["diagnostics"][key] != reference["diagnostics"][key]:
                raise ValueError("three-name source vintage differs within the four-arm family")
        for key in _COMMON_SOURCE_CENSUS:
            if result["aggregates"].get(key) != reference["aggregates"].get(key):
                raise ValueError("three-name non-AR source census differs")


def compare_results(results, context_10pct=None):
    """Compute descriptive net spreads with separately authenticated context."""
    _validated_results(results)
    off = Decimal(results["R242"]["aggregates"]["account"]["cumulative_return"])
    with localcontext() as context:
        context.prec = 96
        comparisons = [{"candidate_id": candidate, "arm": arm,
            "AR_on_minus_three_name_AR_off_percentage_points": str((Decimal(
                results[candidate]["aggregates"]["account"]["cumulative_return"]) - off) * 100)}
            for candidate, arm in CANDIDATES.items() if candidate != "R242"]
    output = {"comparison_valid": True, "formal_alpha": False, "confirmation": False,
        "sensitivity_only": True, "coverage_policy_id": COVERAGE_POLICY_ID,
        "excluded_stock_security_id_sha256": predecessor.EXCLUDED_STOCK_SECURITY_ID_SHA256,
        "reference_data_scope": "common_membership_caps_and_six_ETF_RAW_daily_panel_not_full_stock_minute_fill_tape",
        "comparisons": comparisons,
        "arms": {candidate: {"arm": arm, "account": results[candidate]["aggregates"]["account"],
            "execution": results[candidate]["aggregates"]["execution"],
            "diagnostics": results[candidate]["diagnostics"]}
            for candidate, arm in CANDIDATES.items()},
        "context_10pct": None}
    if context_10pct is None:
        return output
    if type(context_10pct) is not dict or list(context_10pct) != list(CONTEXT_10PCT.values()):
        raise ValueError("three-name context requires exactly four ordered 10% counterparts")
    coverage10.compare_results(context_10pct)
    for new_id, old_id in CONTEXT_10PCT.items():
        new, old = results[new_id], context_10pct[old_id]
        if (new["diagnostics"]["etf_daily_panel_sha256"]
                != old["diagnostics"]["etf_daily_panel_sha256"]
                or new["aggregates"]["account"]["starting_equity"]
                    != old["aggregates"]["account"]["starting_equity"]
                or any(new["aggregates"].get(key) != old["aggregates"].get(key)
                       for key in _COMMON_SOURCE_CENSUS)):
            raise ValueError("three-name and five-name context lack a matched source panel or census")
    with localcontext() as context:
        context.prec = 96
        output["context_10pct"] = {"compatible": True,
            "membership_digest_equality_required": False,
            "construction_difference": "verified-name floor five to three; non-XLE positive-score floor five to three",
            "comparisons": [{"three_name_candidate_id": new_id,
                "five_name_candidate_id": old_id, "arm": CANDIDATES[new_id],
                "three_name_minus_five_name_percentage_points": str((Decimal(
                    results[new_id]["aggregates"]["account"]["cumulative_return"]) - Decimal(
                    context_10pct[old_id]["aggregates"]["account"]["cumulative_return"])) * 100)}
                for new_id, old_id in CONTEXT_10PCT.items()]}
    return output
