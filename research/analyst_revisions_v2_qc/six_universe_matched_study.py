"""One prospective historical comparison; no capacity search or I/O on import.

Reuse the reviewed submission/receipt engine. The three arms remove all AR,
enable its entry/count plus 100% transfers, or hold the six underlying ETFs.
Two fixed cost conditions distinguish signal contribution from cost fragility.
"""

from decimal import Decimal, localcontext

from . import six_universe_relaxed_submission as adapter
from . import six_universe_settlement_submission as common
from . import accepted_risk_delta_order_package as delta


HISTORICAL_ACTIVATION_SHA256 = "69b663c35b245e965b2d4e1f8402b3b14432d6d713f387eacb888f6756e78a41"
CANDIDATES = {
    "R225": ("ar_off", 0), "R226": ("ar_on100", 0), "R227": ("six_etf_basket", 0),
    "R228": ("ar_off", 5), "R229": ("ar_on100", 5), "R230": ("six_etf_basket", 5),
}
PROTOCOL = {
    "first_session": "2021-01-04", "last_session": "2025-12-31",
    "observation_count": 1255, "decision_count": 261,
    "target_gross_exposure": "0.98", "admission_leverage": "2",
    "cost_bps_per_side": "10", "slippage_bps": [0, 5],
    "cadence": "weekly_prior_session_decision_next_open_MOO",
    "selection_policy": "all_six_25pct_verified_subset_top10_equal_slots_residual_own_ETF",
    "comparison": "total_AR_entry_count_and_weights_not_weight_only",
    "confirmation": False, "capacity_search": False,
}
DIAGNOSTIC_NAME = "ARV2_SIX_GATE_ORDER_DIAGNOSTICS"


def validate_manifest(value):
    rows = value.get("candidates") if type(value) is dict else None
    if (type(rows) is not list or len(rows) != len(CANDIDATES)
            or value.get("schema") != "arv2-six-matched-historical-study-v1"
            or adapter._sha(value.get("protocol")) != adapter._sha(PROTOCOL)
            or value.get("package_sha256") != delta.EXPECTED_DELTA_PACKAGE_SHA256
            or value.get("activation_manifest_sha256") != HISTORICAL_ACTIVATION_SHA256
            or [row.get("candidate_id") for row in rows if type(row) is dict] != list(CANDIDATES)):
        adapter._fail("matched study protocol or candidate census changed")
    for row, (arm, slippage) in zip(rows, CANDIDATES.values()):
        if (row.get("kind") != "order" or row.get("arm") != arm
                or type(row.get("slippage_bps")) is not int or row["slippage_bps"] != slippage
                or row.get("tilt_fraction") != ("1.00" if arm == "ar_on100" else "0.00")
                or row.get("statistic_names") != ["ARV2_SIX_GATE_ORDER_META",
                    "ARV2_SIX_GATE_ORDER_AGGREGATES", DIAGNOSTIC_NAME]):
            adapter._fail("matched study AR mode or cost condition changed")
    return value


def parse_order(plan, statistics):
    row = adapter._candidate(plan)
    if set(statistics) != set(row["statistic_names"]):
        adapter._fail("matched study statistic inventory changed")
    parsed = adapter._parse_order_common(plan, statistics, expected_geometry=None,
        decision_count=PROTOCOL["decision_count"],
        extra_meta_fields=frozenset({"matched_diagnostics_sha256"}),
        extra_aggregate_fields=frozenset({"comparison_arm", "analyst_revision_economic_usage"}),
        result_transport="three_bounded_custom_summary_statistics")
    if (parsed["aggregates"].get("comparison_arm") != row["arm"]
            or parsed["aggregates"].get("analyst_revision_economic_usage") != (
                "entry_count_and_weight" if row["arm"] == "ar_on100"
                else "none_authenticated_score_clock_only")):
        adapter._fail("matched study economic AR mode changed")
    diagnostic = adapter._statistic(statistics[DIAGNOSTIC_NAME])
    if parsed["meta"].get("matched_diagnostics_sha256") != adapter._sha(diagnostic):
        adapter._fail("matched study diagnostic digest changed")
    from . import accepted_risk_matched_diagnostics as diagnostics
    diagnostics.validate_report(diagnostic, row["arm"], row["slippage_bps"])
    if diagnostic["overall_cumulative_return"] != parsed["aggregates"]["account"]["cumulative_return"]:
        adapter._fail("matched study diagnostic/account return differs")
    return {**parsed, "diagnostics": diagnostic}


def compare_results(results):
    """Compare only the frozen six valid arms with common reference provenance.

Same ETF panel/membership digests do not certify every stock-minute fill.
AR-on/off target paths deliberately differ: equality there is not a gate.
"""
    if type(results) is not dict or list(results) != list(CANDIDATES):
        raise ValueError("matched study needs the exact six prospective arms")
    from . import accepted_risk_matched_diagnostics as diagnostics
    for candidate, result in results.items():
        if result.get("run_valid") is not True:
            raise ValueError("matched study requires six valid order results")
        aggregate = result["aggregates"]
        account = aggregate["account"]
        diagnostics.validate_report(result["diagnostics"], *CANDIDATES[candidate])
        if (not adapter.cap._finite_decimal(account.get("cumulative_return"))
                or not adapter.cap._finite_decimal(account.get("starting_equity"))
                or Decimal(account["starting_equity"]) <= 0
                or account["cumulative_return"] != result["diagnostics"]["overall_cumulative_return"]):
            raise ValueError("matched study finite account/diagnostic return differs")
        for key in ("target_gross_exposure", "admission_leverage"):
            if aggregate.get(key) != PROTOCOL[key]:
                raise ValueError("matched study exposure/admission differs")
        if (type(account["observation_count"]) is not int
                or account["observation_count"] != PROTOCOL["observation_count"]
                or account["first_observation_session"] != PROTOCOL["first_session"]
                or account["last_observation_session"] != PROTOCOL["last_session"]):
            raise ValueError("matched study observation window differs")
        if (type(aggregate["execution"].get("decision_count")) is not int
                or aggregate["execution"]["decision_count"] != PROTOCOL["decision_count"]):
            raise ValueError("matched study decision census differs")
        for key in ("membership_cap_path_sha256", "etf_daily_panel_sha256"):
            digest = result["diagnostics"].get(key)
            if type(digest) is not str or not adapter.cap._HEX.fullmatch(digest):
                raise ValueError("matched study reference digest shape differs")
    reference = results["R225"]
    for result in results.values():
        if result["aggregates"]["account"]["starting_equity"] != reference["aggregates"]["account"]["starting_equity"]:
            raise ValueError("matched study starting capital differs")
        for key in ("membership_cap_path_sha256", "etf_daily_panel_sha256"):
            if result["diagnostics"][key] != reference["diagnostics"][key]:
                raise ValueError("matched study reference-data vintage differs")
        for key in ("pit_callback_source_row_count", "fundamental_snapshot_unavailable_decision_count",
                    "constituent_collection_unavailable_decision_count",
                    "constituent_collection_unavailable_universe_counts"):
            if result["aggregates"].get(key) != reference["aggregates"].get(key):
                raise ValueError("matched study non-AR source census differs")
    comparisons = []
    with localcontext() as context:
        context.prec = 96
        for slippage, ids in ((0, ("R225", "R226", "R227")), (5, ("R228", "R229", "R230"))):
            off, on, etf = [Decimal(results[key]["aggregates"]["account"]["cumulative_return"]) for key in ids]
            comparisons.append({"slippage_bps": slippage,
                "AR_on_minus_fully_off_percentage_points": str((on - off) * 100),
                "AR_on_minus_six_ETF_percentage_points": str((on - etf) * 100),
                "AR_off_minus_six_ETF_percentage_points": str((off - etf) * 100)})
    return {"comparison_valid": True, "total_AR_ablation": True,
        "formal_alpha": False, "confirmation": False, "comparisons": comparisons,
        "reference_data_scope": "common_membership_caps_and_six_ETF_RAW_daily_panel_not_full_stock_minute_fill_tape",
        "arms": {candidate: {"arm": CANDIDATES[candidate][0],
            "slippage_bps": CANDIDATES[candidate][1], "account": result["aggregates"]["account"],
            "execution": result["aggregates"]["execution"], "diagnostics": result["diagnostics"]}
            for candidate, result in results.items()}}
