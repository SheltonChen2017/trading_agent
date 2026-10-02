"""One historical, order-based AR entry/count ablation with zero weight tilt.

R246 is paired with the existing authenticated R231 AR-off and R232 AR-on100
results. The three arms share the QCOM-excluded 25%/five-name construction;
this is exploratory decomposition, not held-out confirmation.
"""

from decimal import Decimal, localcontext

from . import accepted_risk_delta_order_package as delta
from . import accepted_risk_matched_diagnostics as diagnostics
from . import six_universe_qcom_exclusion_study as control
from . import six_universe_relaxed_submission as adapter
from . import six_universe_qcom_entry_only_projection as projection


FAMILY = "qcom_entry_only"
CANDIDATE = "R246"
MANIFEST_SCHEMA = "arv2-six-qcom-excluded-entry-only-historical-study-v1"
PROTOCOL = {**control.PROTOCOL,
    "slippage_bps": [0],
    "comparison": "R231_AR_off_vs_R246_AR_entry_count_zero_weight_vs_R232_full_AR_on100",
    "control_manifest_sha256": adapter.FROZEN_QCOM_EXCLUSION_MANIFEST_SHA256,
    "control_candidate_ids": ["R231", "R232"],
}
STATISTIC_NAMES = ["ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES",
                   control.DIAGNOSTIC_NAME]
EXPECTED_PROJECTION_SHA256 = "711bf00ec5dbefd45fda2e07c603800ec98e134d9e392582547f6f9186c43eff"
EXPECTED_PROFILE_SHA256 = "86cde0605e404f0d0249ab8530921b6cff02aba55e2918aa7f01126000ac96ca"
EXPECTED_BASELINE_PROFILE_SHA256 = projection.PREDECESSOR_BASELINE_PROFILE_SHA256
_SOURCE_CENSUS = ("pit_callback_source_row_count",
    "fundamental_snapshot_unavailable_decision_count",
    "constituent_collection_unavailable_decision_count",
    "constituent_collection_unavailable_universe_counts")


def validate_manifest(value):
    """Pin one fresh source and no alias of either spent control."""
    rows = value.get("candidates") if type(value) is dict else None
    if (type(value) is not dict
            or set(value) != {"schema", "protocol", "package_sha256",
                              "activation_manifest_sha256", "candidates"}
            or value["schema"] != MANIFEST_SCHEMA or value["protocol"] != PROTOCOL
            or value["package_sha256"] != delta.EXPECTED_DELTA_PACKAGE_SHA256
            or value["activation_manifest_sha256"] != control.HISTORICAL_ACTIVATION_SHA256
            or type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict):
        adapter._fail("entry-only historical protocol or source package changed")
    row = rows[0]
    if (set(row) != control._ROW_FIELDS
            or row["candidate_id"] != CANDIDATE or row["arm"] != "ar_on0"
            or type(row["slippage_bps"]) is not int or row["slippage_bps"] != 0
            or row["kind"] != "order" or row["tilt_fraction"] != "0.00"
            or row["role"] != "matched_qcom_excluded_ar_on0_s0"
            or row["profile_id"] != "arv2-six-matched-qcom-excluded-ar_on0-s0-profile-v1"
            or row["projection_schema"]
                != "arv2-six-matched-qcom-excluded-entry-only-projection-v1"
            or row["projection_sha256"] != EXPECTED_PROJECTION_SHA256
            or row["profile_sha256"] != EXPECTED_PROFILE_SHA256
            or row["matched_baseline_profile_sha256"] != EXPECTED_BASELINE_PROFILE_SHA256
            or row["meta_schema"] != projection.prior.QCOM_EXCLUSION_META_SCHEMA
            or row["summary_schema"] != "arv2-six-matched-qcom-excluded-tilt0-summary-v1"
            or row["statistic_names"] != STATISTIC_NAMES
            or row["excluded_stock_security_id_sha256"]
                != control.EXCLUDED_STOCK_SECURITY_ID_SHA256
            or row["reference_repair_enabled"] is not True
            or type(row["source_file_count"]) is not int or row["source_file_count"] != 17
            or type(row["total_source_bytes"]) is not int
            or not 0 < row["total_source_bytes"] < 448 * 1024
            or any(not control._digest(row[key]) for key in (
                "profile_sha256", "projection_sha256", "source_files_sha256",
                "matched_baseline_profile_sha256"))
            or any(type(row[key]) is not str or CANDIDATE not in row[key]
                   for key in ("project_name", "backtest_name"))):
        adapter._fail("entry-only candidate, closure, or physical-order disclosure changed")
    return value


def parse_order(plan, statistics):
    row = adapter._candidate(plan)
    if (plan.family != FAMILY or row["candidate_id"] != CANDIDATE
            or set(statistics) != set(STATISTIC_NAMES)):
        adapter._fail("entry-only result family or custom-statistic inventory changed")
    parsed = adapter._parse_order_common(plan, statistics, expected_geometry=None,
        decision_count=PROTOCOL["decision_count"],
        extra_meta_fields=frozenset({"matched_diagnostics_sha256"}),
        extra_aggregate_fields=frozenset({"comparison_arm", "analyst_revision_economic_usage",
            "stock_exclusion_policy_id", "excluded_logical_security_sha256"}),
        result_transport="three_bounded_custom_summary_statistics")
    aggregate = parsed["aggregates"]
    if (aggregate.get("comparison_arm") != "ar_on0"
            or aggregate.get("analyst_revision_economic_usage") != projection.ECONOMIC_USAGE
            or aggregate.get("stock_exclusion_policy_id") != control.EXCLUSION_RULE
            or aggregate.get("excluded_logical_security_sha256")
                != control.EXCLUDED_STOCK_SECURITY_ID_SHA256):
        adapter._fail("entry-only AR economic mode or exclusion changed")
    report = adapter._statistic(statistics[control.DIAGNOSTIC_NAME])
    if parsed["meta"].get("matched_diagnostics_sha256") != adapter._sha(report):
        adapter._fail("entry-only diagnostic digest changed")
    diagnostics.validate_report(report, "ar_on100", 0, reference_repair_enabled=True)
    if report["overall_cumulative_return"] != aggregate["account"]["cumulative_return"]:
        adapter._fail("entry-only diagnostic/account return differs")
    return {**parsed, "diagnostics": report}


def compare_results(results):
    """Report total entry/count and conditional weight effects, separately."""
    ids = ("R231", CANDIDATE, "R232")
    if type(results) is not dict or tuple(results) != ids:
        raise ValueError("entry-only comparison requires R231, R246, R232 in order")
    old = adapter._qcom_exclusion_manifest()
    new = adapter._qcom_entry_only_manifest()
    if (old["package_sha256"] != new["package_sha256"]
            or old["activation_manifest_sha256"] != new["activation_manifest_sha256"]
            or old["protocol"]["selection_policy"] != new["protocol"]["selection_policy"]
            or old["protocol"]["exclusion_rule"] != new["protocol"]["exclusion_rule"]
            or old["candidates"][1]["matched_baseline_profile_sha256"]
                != EXPECTED_BASELINE_PROFILE_SHA256):
        raise ValueError("entry-only controls do not share the frozen construction")
    rows = {row["candidate_id"]: row for row in (*old["candidates"][:2], *new["candidates"])}
    for candidate in ids:
        result, row = results[candidate], rows[candidate]
        aggregate = result.get("aggregates") if type(result) is dict else None
        report = result.get("diagnostics") if type(result) is dict else None
        if (type(result) is not dict or result.get("candidate_id") != candidate
                or result.get("run_valid") is not True or result.get("status") != "Completed."
                or type(result.get("attempt")) is not int or not 1 <= result["attempt"] <= 3
                or result.get("manifest_sha256") != (
                    adapter.FROZEN_QCOM_ENTRY_ONLY_MANIFEST_SHA256 if candidate == CANDIDATE
                    else adapter.FROZEN_QCOM_EXCLUSION_MANIFEST_SHA256)
                or result.get("projection_sha256") != row["projection_sha256"]
                or type(aggregate) is not dict or type(report) is not dict
                or aggregate.get("comparison_arm") != row["arm"]
                or aggregate.get("matched_baseline_profile_sha256")
                    != row["matched_baseline_profile_sha256"]
                or aggregate.get("maximum_stock_weight_change_fraction") != row["tilt_fraction"]
                or aggregate.get("target_gross_exposure") != PROTOCOL["target_gross_exposure"]
                or aggregate.get("admission_leverage") != PROTOCOL["admission_leverage"]
                or aggregate.get("stock_exclusion_policy_id") != control.EXCLUSION_RULE
                or aggregate.get("excluded_logical_security_sha256")
                    != control.EXCLUDED_STOCK_SECURITY_ID_SHA256
                or type(aggregate.get("account")) is not dict
                or aggregate["account"].get("observation_count") != PROTOCOL["observation_count"]
                or aggregate["account"].get("first_observation_session") != PROTOCOL["first_session"]
                or aggregate["account"].get("last_observation_session") != PROTOCOL["last_session"]
                or type(aggregate.get("execution")) is not dict
                or aggregate["execution"].get("submitted_rebalance_count") != PROTOCOL["decision_count"]
                or aggregate["execution"].get("completed_rebalance_count") != PROTOCOL["decision_count"]):
            raise ValueError("entry-only arm identity or execution geometry differs")
        diagnostics.validate_report(report, "ar_on100" if candidate != "R231" else "ar_off",
                                    0, reference_repair_enabled=True)
    off, entry, full = (results[candidate]["aggregates"] for candidate in ids)
    for candidate in ids[1:]:
        other = results[candidate]["aggregates"]
        other_report = results[candidate]["diagnostics"]
        if (other["account"]["starting_equity"] != off["account"]["starting_equity"]
                or any(other_report[key] != results["R231"]["diagnostics"][key]
                       for key in ("membership_cap_path_sha256", "etf_daily_panel_sha256"))
                or any(other.get(key) != off.get(key) for key in _SOURCE_CENSUS)):
            raise ValueError("entry-only family source or capital differs")
    for key in ("matched_baseline_target_path_sha256", "sleeve_diagnostics"):
        if entry.get(key) != full.get(key):
            raise ValueError("entry-only and full-AR baseline holdings differ")
    for key in ("account", "execution"):
        if type(entry.get(key)) is not dict or type(full.get(key)) is not dict:
            raise ValueError("entry-only or full-AR result body changed")
    with localcontext() as context:
        context.prec = 96
        off_return = Decimal(off["account"]["cumulative_return"])
        entry_return = Decimal(entry["account"]["cumulative_return"])
        full_return = Decimal(full["account"]["cumulative_return"])
        spreads = {
            "AR_entry_count_vs_off_percentage_points": str((entry_return - off_return) * 100),
            "AR_weight_given_same_entry_percentage_points": str((full_return - entry_return) * 100),
            "AR_total_vs_off_percentage_points": str((full_return - off_return) * 100),
        }
    return {"comparison_valid": True, "formal_alpha": False, "confirmation": False,
        "sensitivity_only": True, "same_AR_on_baseline_path_required": True,
        "reference_data_scope": "common_membership_caps_and_six_ETF_RAW_daily_panel_not_full_stock_minute_fill_tape",
        "spreads": spreads, "accounts": {candidate: results[candidate]["aggregates"]["account"]
            for candidate in ids}}
