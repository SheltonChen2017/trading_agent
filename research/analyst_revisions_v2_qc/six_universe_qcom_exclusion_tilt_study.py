"""Separate, exploratory QCOM-excluded AR-on weight-tilt ladder.

R235--R237 retain the 2021--2025 physical-order package and the exact
post-coverage direct-stock QCOM exclusion. R231 is a contextual AR-off
zero-slippage control only when its authenticated source census matches.
No cloud call or outcome read occurs on import.
"""

from decimal import Decimal, localcontext

from . import accepted_risk_delta_order_package as delta
from . import accepted_risk_matched_diagnostics as diagnostics
from . import six_universe_qcom_exclusion_study as control
from . import six_universe_relaxed_submission as adapter


MANIFEST_SCHEMA = "arv2-six-qcom-excluded-ar-on-tilt-ladder-v1"
FAMILY = "qcom_exclusion_tilt"
CANDIDATES = {"R235": 80, "R236": 120, "R237": 200}
CONTROL_CANDIDATE = "R231"
CONTROL_AR_ON_BASELINE_PROFILE_SHA256 = (
    "f03e7f0f9669e3d5168511a9c05cf5e0b9c2c88801fc87433d990537c333615d"
)
TILT_FRACTIONS = {80: "0.80", 120: "1.20", 200: "2.00"}
STATISTIC_NAMES = ["ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES",
                   control.DIAGNOSTIC_NAME]
# The pinned plain order runtime emits META_SCHEMA below. The distinct tilt
# runtime emits TILT_META_SCHEMA, but that is not this custom META statistic.
# Admit the observed transport only for these exact frozen source closures.
SHARED_ORDER_META_SCHEMA = "arv2-six-matched-qcom-excluded-meta-v1"
_SHARED_META_SOURCE_PINS = {
    "R235": ("06842824c2fee60f447c4e920ee23634917958f94fa2332a9f21ea24eeed0aa1",
             "8e21a83db1a1ec62f3a57bc69b64626e9c72101a7437fc834d8a4ca8ea7c1a82"),
    "R236": ("cc18bcdda7dc17750c186a403c8ec74568c4a7f71c528bdd4b714c00ef63c17b",
             "6b4ab1c8109ef3deadf09c220ba9179c8156288cdae094807dc67051cac34812"),
    "R237": ("44b7e0dfcd31ecb1698e0b46196ebe4de80ca036d9273516b05f35dd65241f25",
             "c35d5a907d470f53425f25112956a70bc38b8e1d465cfaa1a6bedb36d979c675"),
}
_SHARED_META_MANIFEST_PIN = "3a5532ebcda49695fcf29e964af5ca7c79e7c29cec773f2814d17408af0ddbb4"
PROTOCOL = {**control.PROTOCOL,
    "slippage_bps": [0],
    "comparison": "QCOM_excluded_AR_on_weight_tilt_80_120_200_vs_R231_AR_off_context",
    "control_candidate_id": CONTROL_CANDIDATE,
    "control_manifest_sha256": adapter.FROZEN_QCOM_EXCLUSION_MANIFEST_SHA256,
}
_ROW_FIELDS = control._ROW_FIELDS | {"tilt_percent"}
_COMMON_SOURCE_CENSUS = (
    "pit_callback_source_row_count",
    "fundamental_snapshot_unavailable_decision_count",
    "constituent_collection_unavailable_decision_count",
    "constituent_collection_unavailable_universe_counts",
)


def _digest(value):
    return type(value) is str and adapter.cap._HEX.fullmatch(value) is not None


def validate_manifest(value):
    """Require three distinct zero-slippage candidates and the old control pin."""
    if (type(value) is not dict
            or set(value) != {"schema", "protocol", "package_sha256",
                              "activation_manifest_sha256", "candidates"}
            or value["schema"] != MANIFEST_SCHEMA
            or type(value["protocol"]) is not dict or value["protocol"] != PROTOCOL
            or value["protocol"].get("confirmation") is not False
            or value["protocol"].get("capacity_search") is not False
            or value["protocol"].get("sensitivity_only") is not True
            or type(value["protocol"].get("slippage_bps")) is not list
            or len(value["protocol"]["slippage_bps"]) != 1
            or type(value["protocol"]["slippage_bps"][0]) is not int
            or value["package_sha256"] != delta.EXPECTED_DELTA_PACKAGE_SHA256
            or value["activation_manifest_sha256"] != control.HISTORICAL_ACTIVATION_SHA256
            or type(value["candidates"]) is not list
            or len(value["candidates"]) != len(CANDIDATES)):
        adapter._fail("QCOM-excluded tilt protocol or historical input changed")
    projects, backtests, projections, profiles, sources = set(), set(), set(), set(), set()
    for row, (candidate, percent) in zip(value["candidates"], CANDIDATES.items()):
        arm = f"ar_on{percent}"
        if (type(row) is not dict or set(row) != _ROW_FIELDS
                or row["candidate_id"] != candidate
                or type(row["tilt_percent"]) is not int or row["tilt_percent"] != percent
                or row["arm"] != arm
                or type(row["slippage_bps"]) is not int or row["slippage_bps"] != 0
                or row["kind"] != "order"
                or row["tilt_fraction"] != TILT_FRACTIONS[percent]
                or row["role"] != f"matched_qcom_excluded_{arm}_s0"
                or row["profile_id"] != f"arv2-six-matched-qcom-excluded-{arm}-s0-profile-v1"
                or row["projection_schema"] != f"arv2-six-matched-qcom-excluded-tilt{percent}-projection-v1"
                or row["meta_schema"] != f"arv2-six-matched-qcom-excluded-tilt{percent}-meta-v1"
                or row["summary_schema"] != f"arv2-six-matched-qcom-excluded-tilt{percent}-summary-v1"
                or row["reference_repair_enabled"] is not True
                or row["excluded_stock_security_id_sha256"] != control.EXCLUDED_STOCK_SECURITY_ID_SHA256
                or row["matched_baseline_profile_sha256"] != CONTROL_AR_ON_BASELINE_PROFILE_SHA256
                or row["statistic_names"] != STATISTIC_NAMES
                or type(row["source_file_count"]) is not int or row["source_file_count"] != 17
                or type(row["total_source_bytes"]) is not int
                or not 0 < row["total_source_bytes"] < 448 * 1024
                or any(not _digest(row[key]) for key in (
                    "profile_sha256", "projection_sha256", "source_files_sha256"))
                or type(row["project_name"]) is not str or not row["project_name"]
                or type(row["backtest_name"]) is not str or not row["backtest_name"]
                or candidate not in row["project_name"] or candidate not in row["backtest_name"]
                or row["project_name"] in projects or row["backtest_name"] in backtests
                or row["projection_sha256"] in projections or row["profile_sha256"] in profiles
                or row["source_files_sha256"] in sources):
            adapter._fail("QCOM-excluded tilt candidate identity or source disclosure changed")
        projects.add(row["project_name"])
        backtests.add(row["backtest_name"])
        projections.add(row["projection_sha256"])
        profiles.add(row["profile_sha256"])
        sources.add(row["source_files_sha256"])
    return value


def parse_order(plan, statistics):
    """Bind the tilt's distinct aggregate arm to the shared AR-on diagnostics."""
    row = adapter._candidate(plan)
    if (plan.family != FAMILY or row["candidate_id"] not in CANDIDATES
            or row["tilt_percent"] != CANDIDATES[row["candidate_id"]]
            or set(statistics) != set(STATISTIC_NAMES)):
        adapter._fail("QCOM-excluded tilt result family or inventory changed")
    observed_meta_schema = adapter._statistic(statistics[STATISTIC_NAMES[0]]).get("schema")
    expected_meta_schema = row["meta_schema"]
    if observed_meta_schema == SHARED_ORDER_META_SCHEMA:
        if (adapter._plan_manifest_sha256(plan) != _SHARED_META_MANIFEST_PIN
                or (row["projection_sha256"], row["source_files_sha256"])
                    != _SHARED_META_SOURCE_PINS[row["candidate_id"]]):
            adapter._fail("QCOM-excluded tilt shared META source identity changed")
        expected_meta_schema = SHARED_ORDER_META_SCHEMA
    parsed = adapter._parse_order_common(plan, statistics, expected_geometry=None,
        decision_count=PROTOCOL["decision_count"],
        extra_meta_fields=frozenset({"matched_diagnostics_sha256"}),
        extra_aggregate_fields=frozenset({"comparison_arm", "analyst_revision_economic_usage",
            "stock_exclusion_policy_id", "excluded_logical_security_sha256"}),
        result_transport="three_bounded_custom_summary_statistics",
        expected_meta_schema=expected_meta_schema)
    aggregate = parsed["aggregates"]
    if (aggregate.get("comparison_arm") != row["arm"]
            or aggregate.get("analyst_revision_economic_usage") != "entry_count_and_weight"
            or aggregate.get("stock_exclusion_policy_id") != control.EXCLUSION_RULE
            or aggregate.get("excluded_logical_security_sha256") != control.EXCLUDED_STOCK_SECURITY_ID_SHA256):
        adapter._fail("QCOM-excluded tilt economic mode or security identity changed")
    report = adapter._statistic(statistics[control.DIAGNOSTIC_NAME])
    if parsed["meta"].get("matched_diagnostics_sha256") != adapter._sha(report):
        adapter._fail("QCOM-excluded tilt diagnostic digest changed")
    diagnostics.validate_report(report, "ar_on100", 0, reference_repair_enabled=True)
    if report["overall_cumulative_return"] != aggregate["account"]["cumulative_return"]:
        adapter._fail("QCOM-excluded tilt diagnostic/account return differs")
    return {**parsed, "diagnostics": report}


def compare_results(results):
    """Compare valid new arms to authenticated R231 only on common inputs.

    Equal membership/cap and ETF RAW-panel hashes do not prove equality of
    stock minute prices, execution fills, or a point-in-time Benzinga vintage.
    """
    ids = [CONTROL_CANDIDATE, *CANDIDATES]
    if type(results) is not dict or list(results) != ids:
        raise ValueError("QCOM-excluded tilt comparison requires R231 and exactly three new arms")
    control_manifest = adapter._qcom_exclusion_manifest()
    manifest = adapter._qcom_exclusion_tilt_manifest()
    control_row = control_manifest["candidates"][0]
    if (control_row["candidate_id"] != CONTROL_CANDIDATE
            or control_row["slippage_bps"] != 0
            or control_row["arm"] != "ar_off"
            or control_manifest["package_sha256"] != manifest["package_sha256"]
            or control_manifest["activation_manifest_sha256"] != manifest["activation_manifest_sha256"]
            or control_manifest["protocol"]["exclusion_rule"] != PROTOCOL["exclusion_rule"]
            or control_manifest["protocol"]["selection_policy"] != PROTOCOL["selection_policy"]
            or control_manifest["candidates"][1]["matched_baseline_profile_sha256"]
                != CONTROL_AR_ON_BASELINE_PROFILE_SHA256):
        raise ValueError("R231 is not the same QCOM-excluded historical control")
    rows = {CONTROL_CANDIDATE: control_row, **{
        row["candidate_id"]: row for row in manifest["candidates"]}}
    for candidate in ids:
        result, row = results[candidate], rows[candidate]
        if (type(result) is not dict or result.get("run_valid") is not True
                or result.get("candidate_id") != candidate
                or type(result.get("attempt")) is not int or not 1 <= result["attempt"] <= 3
                or result.get("status") != "Completed."
                or result.get("manifest_sha256") != (
                    adapter.FROZEN_QCOM_EXCLUSION_MANIFEST_SHA256 if candidate == CONTROL_CANDIDATE
                    else adapter.FROZEN_QCOM_EXCLUSION_TILT_MANIFEST_SHA256)
                or result.get("projection_sha256") != row["projection_sha256"]):
            raise ValueError("QCOM-excluded tilt comparison requires authenticated completed arms")
        aggregate = result.get("aggregates")
        report = result.get("diagnostics")
        if type(aggregate) is not dict or type(report) is not dict:
            raise ValueError("QCOM-excluded tilt aggregate or diagnostics missing")
        arm = "ar_off" if candidate == CONTROL_CANDIDATE else f"ar_on{CANDIDATES[candidate]}"
        diagnostics.validate_report(report, "ar_off" if candidate == CONTROL_CANDIDATE else "ar_on100",
                                    0, reference_repair_enabled=True)
        account, execution = aggregate.get("account"), aggregate.get("execution")
        if (type(account) is not dict or type(execution) is not dict
                or aggregate.get("comparison_arm") != arm
                or aggregate.get("analyst_revision_economic_usage") != (
                    "none_authenticated_score_clock_only" if candidate == CONTROL_CANDIDATE
                    else "entry_count_and_weight")
                or aggregate.get("maximum_stock_weight_change_fraction") != row["tilt_fraction"]
                or aggregate.get("matched_baseline_profile_sha256") != row["matched_baseline_profile_sha256"]
                or aggregate.get("stock_exclusion_policy_id") != control.EXCLUSION_RULE
                or aggregate.get("excluded_logical_security_sha256") != control.EXCLUDED_STOCK_SECURITY_ID_SHA256
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
                or account["cumulative_return"] != report["overall_cumulative_return"]):
            raise ValueError("QCOM-excluded tilt arm economics or account geometry differs")
        if any(not _digest(report.get(key)) for key in (
                "membership_cap_path_sha256", "etf_daily_panel_sha256")):
            raise ValueError("QCOM-excluded tilt source digest shape differs")
    reference = results[CONTROL_CANDIDATE]
    for result in results.values():
        if result["aggregates"]["account"]["starting_equity"] != reference["aggregates"]["account"]["starting_equity"]:
            raise ValueError("QCOM-excluded tilt starting capital differs")
        for key in ("membership_cap_path_sha256", "etf_daily_panel_sha256"):
            if result["diagnostics"][key] != reference["diagnostics"][key]:
                raise ValueError("QCOM-excluded tilt source vintage differs")
        for key in _COMMON_SOURCE_CENSUS:
            if result["aggregates"].get(key) != reference["aggregates"].get(key):
                raise ValueError("QCOM-excluded tilt non-AR source census differs")
    off = Decimal(reference["aggregates"]["account"]["cumulative_return"])
    with localcontext() as context:
        context.prec = 96
        comparisons = [{"candidate_id": candidate, "tilt_percent": percent,
            "AR_on_minus_R231_AR_off_percentage_points": str((Decimal(
                results[candidate]["aggregates"]["account"]["cumulative_return"]) - off) * 100)}
            for candidate, percent in CANDIDATES.items()]
    return {"comparison_valid": True, "formal_alpha": False, "confirmation": False,
        "sensitivity_only": True, "control_candidate_id": CONTROL_CANDIDATE,
        "excluded_stock_security_id_sha256": control.EXCLUDED_STOCK_SECURITY_ID_SHA256,
        "reference_data_scope": "common_membership_caps_and_six_ETF_RAW_daily_panel_not_full_stock_minute_fill_tape",
        "comparisons": comparisons,
        "arms": {candidate: {"arm": ("ar_off" if candidate == CONTROL_CANDIDATE
                                     else f"ar_on{CANDIDATES[candidate]}"),
            "slippage_bps": 0, "account": results[candidate]["aggregates"]["account"],
            "execution": results[candidate]["aggregates"]["execution"],
            "diagnostics": results[candidate]["diagnostics"]} for candidate in ids}}
