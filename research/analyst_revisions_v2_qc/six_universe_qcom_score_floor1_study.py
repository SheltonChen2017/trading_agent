"""Prospective QCOM-admitted, three-name, one-positive-score tilt ladder.

These are exploratory historical order runs, not an independent confirmation
sample. R261/on100 is a stock-admission pilot: no other arm may launch unless
its authenticated result has at least one post-cap REMX direct-stock target.
Importing this module performs no provider, QC, or filesystem action.
"""

import dataclasses

from . import accepted_risk_delta_order_package as delta
from . import accepted_risk_matched_diagnostics as diagnostics
from . import six_universe_qcom_exclusion_study as excluded
from . import six_universe_relaxed_submission as adapter


FAMILY = "qcom_score_floor1"
MANIFEST_SCHEMA = "arv2-six-qcom-admitted-score-floor1-tilt-ladder-v1"
PILOT = "R261"
CANDIDATE_PERCENTS = {
    "R260": 80, "R261": 100, "R262": 120, "R263": 140,
    "R264": 160, "R265": 180, "R266": 200,
}
SOURCE_CANDIDATES = {
    "R260": "R256", "R261": "R256", "R262": "R257",
    "R263": "R256", "R264": "R256", "R265": "R256", "R266": "R258",
}
COVERAGE_POLICY_ID = (
    "all_six_minimum_mapping_cap_total_10pct_verified_names_3_positive_scores_1_v1"
)
STATISTIC_NAMES = [
    "ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES",
    excluded.DIAGNOSTIC_NAME,
]
PROTOCOL = {
    "candidate_ids": list(CANDIDATE_PERCENTS),
    "source_ids": list(SOURCE_CANDIDATES.values()),
    "one_change": "QCOM_admitted_three_name_positive_score_floor_3_to_1_and_versioned_tilt_ladder",
    "historical_order_window": ["2021-01-04", "2025-12-31"],
    "decision_count": excluded.PROTOCOL["decision_count"],
    "observation_count": excluded.PROTOCOL["observation_count"],
    "cost_bps_per_side": excluded.PROTOCOL["cost_bps_per_side"],
    "slippage_bps": 0,
    "target_gross_exposure": excluded.PROTOCOL["target_gross_exposure"],
    "admission_leverage": excluded.PROTOCOL["admission_leverage"],
    "minimum_verified_name_count": 3,
    "minimum_positive_score_count": 1,
    "pilot_candidate_id": PILOT,
    "pilot_required_remx_post_cap_stock_target_count_at_least": 1,
    "pilot_required_total_post_cap_stock_target_count_above": 12211,
    "floor3_reference_candidate_id": "R257",
    "floor3_reference_remx_post_cap_stock_target_count": 0,
    "floor3_reference_total_post_cap_stock_target_count": 12211,
    "maximum_attempts_per_candidate": 3,
    "physical_orders": True,
    "sensitivity_only": True,
    "confirmation": False,
    "formal_alpha": False,
    "paper_live_trading": False,
}
_ROW_FIELDS = frozenset({
    "candidate_id", "source_candidate_id", "source_manifest_sha256",
    "source_projection_sha256", "source_profile_sha256", "project_name",
    "backtest_name", "kind", "arm", "slippage_bps", "tilt_fraction",
    "coverage_policy_id", "minimum_verified_name_count",
    "minimum_positive_score_count", "analyst_revision_economic_usage",
    "reference_repair_enabled", "role", "projection_schema",
    "projection_sha256", "profile_id", "profile_sha256",
    "matched_baseline_profile_sha256", "source_files_sha256",
    "source_file_count", "total_source_bytes", "statistic_names",
    "meta_schema", "summary_schema",
})


def validate_manifest(value):
    """Reject changed candidates, economic rules, source provenance or pins."""
    rows = value.get("candidates") if type(value) is dict else None
    if (
        type(value) is not dict
        or set(value) != {"schema", "protocol", "package_sha256",
                          "activation_manifest_sha256", "candidates"}
        or value["schema"] != MANIFEST_SCHEMA
        or type(value["protocol"]) is not dict or value["protocol"] != PROTOCOL
        or value["package_sha256"] != delta.EXPECTED_DELTA_PACKAGE_SHA256
        or value["activation_manifest_sha256"] != excluded.HISTORICAL_ACTIVATION_SHA256
        or type(rows) is not list or len(rows) != len(CANDIDATE_PERCENTS)
    ):
        adapter._fail("score-floor1 protocol or historical inputs changed")
    # This family may consume only the already frozen QCOM-admitted three-name
    # source, never mutable project files or the old QCOM-excluded projection.
    source_manifest = adapter._qcom_restored_manifest()
    sources = {row["candidate_id"]: row for row in source_manifest["candidates"]}
    seen_projects, seen_backtests, seen_projections = set(), set(), set()
    seen_profiles, seen_sources = set(), set()
    for row, (candidate, percent) in zip(rows, CANDIDATE_PERCENTS.items()):
        source_id = SOURCE_CANDIDATES[candidate]
        parent = sources[source_id]
        digest_keys = (
            "projection_sha256", "profile_sha256",
            "matched_baseline_profile_sha256", "source_files_sha256",
        )
        if (
            type(row) is not dict or set(row) != _ROW_FIELDS
            or row["candidate_id"] != candidate
            or row["source_candidate_id"] != source_id
            or row["source_manifest_sha256"] != adapter.FROZEN_QCOM_RESTORED_MANIFEST_SHA256
            or row["source_projection_sha256"] != parent["projection_sha256"]
            or row["source_profile_sha256"] != parent["profile_sha256"]
            or row["project_name"] != f"ARV2 SIX QCOM FLOOR1 {candidate} AR{percent} 2021 2025"
            or row["backtest_name"] != f"ARV2 {candidate} QCOM score floor1 AR{percent} 2021 2025"
            or row["kind"] != "order" or row["arm"] != f"ar_on{percent}"
            or type(row["slippage_bps"]) is not int or row["slippage_bps"] != 0
            or row["tilt_fraction"] != f"{percent // 100}.{percent % 100:02d}"
            or row["coverage_policy_id"] != COVERAGE_POLICY_ID
            or type(row["minimum_verified_name_count"]) is not int
            or row["minimum_verified_name_count"] != 3
            or type(row["minimum_positive_score_count"]) is not int
            or row["minimum_positive_score_count"] != 1
            or row["analyst_revision_economic_usage"] != "entry_count_and_weight"
            or row["reference_repair_enabled"] is not True
            or row["projection_schema"] != (
                f"arv2-six-qcom-admitted-{candidate.lower()}-score-floor1-projection-v1")
            or not isinstance(row["role"], str)
            or row["role"] != (
                f"matched_qcom_admitted_{candidate.lower()}_score_floor1_three_name_ar_on{percent}_s0")
            or row["profile_id"] != (
                f"arv2-six-matched-qcom-admitted-{candidate.lower()}-score-floor1-"
                f"three-name-ar_on{percent}-s0-profile-v1")
            or row["meta_schema"] != (
                f"arv2-six-matched-qcom-admitted-{candidate.lower()}-score-floor1-"
                f"three-name-ar_on{percent}-meta-v1")
            or row["summary_schema"] != (
                f"arv2-six-matched-qcom-admitted-{candidate.lower()}-score-floor1-"
                f"three-name-ar_on{percent}-summary-v1")
            or row["statistic_names"] != STATISTIC_NAMES
            or type(row["source_file_count"]) is not int
            or row["source_file_count"] != 17
            or type(row["total_source_bytes"]) is not int
            or not 0 < row["total_source_bytes"] < 448 * 1024
            or any(type(row[key]) is not str or adapter.cap._HEX.fullmatch(row[key]) is None
                   for key in digest_keys)
            or row["project_name"] in seen_projects
            or row["backtest_name"] in seen_backtests
            or row["projection_sha256"] in seen_projections
            or row["profile_sha256"] in seen_profiles
            or row["source_files_sha256"] in seen_sources
        ):
            adapter._fail("score-floor1 candidate or source identity changed")
        seen_projects.add(row["project_name"])
        seen_backtests.add(row["backtest_name"])
        seen_projections.add(row["projection_sha256"])
        seen_profiles.add(row["profile_sha256"])
        seen_sources.add(row["source_files_sha256"])
    return value


def parse_order(plan, statistics):
    """Read only the three bounded statistics from an exact completed run."""
    row = adapter._candidate(plan)
    if (plan.family != FAMILY or row["candidate_id"] not in CANDIDATE_PERCENTS
            or set(statistics) != set(STATISTIC_NAMES)):
        adapter._fail("score-floor1 result family or statistic inventory changed")
    parsed = adapter._parse_order_common(
        plan, statistics, expected_geometry=None,
        decision_count=PROTOCOL["decision_count"],
        extra_meta_fields=frozenset({"matched_diagnostics_sha256"}),
        extra_aggregate_fields=frozenset({
            "comparison_arm", "analyst_revision_economic_usage", "coverage_policy_id",
        }),
        result_transport="three_bounded_custom_summary_statistics",
    )
    aggregate = parsed["aggregates"]
    if (
        aggregate.get("comparison_arm") != row["arm"]
        or aggregate.get("analyst_revision_economic_usage") != "entry_count_and_weight"
        or aggregate.get("coverage_policy_id") != COVERAGE_POLICY_ID
        or any(key in aggregate or key in parsed["meta"] for key in (
            "stock_exclusion_policy_id", "excluded_logical_security_sha256",
            "stock_exclusion_scope"))
    ):
        adapter._fail("score-floor1 arm, coverage or QCOM eligibility changed")
    report = adapter._statistic(statistics[excluded.DIAGNOSTIC_NAME])
    if parsed["meta"].get("matched_diagnostics_sha256") != adapter._sha(report):
        adapter._fail("score-floor1 diagnostic digest changed")
    # The new QC source emits the actual arm. The host's frozen legacy
    # validator accepts only the old ar_on100 label, so validate the exact
    # label first, then normalize only a private copy for its other geometry
    # and schema checks. The authenticated report itself stays unchanged.
    if report.get("arm") != row["arm"]:
        adapter._fail("score-floor1 diagnostic arm changed")
    diagnostics.validate_report(
        {**report, "arm": "ar_on100"}, "ar_on100", 0,
        reference_repair_enabled=True,
    )
    if report["overall_cumulative_return"] != aggregate["account"]["cumulative_return"]:
        adapter._fail("score-floor1 diagnostic and account return differ")
    return {**parsed, "diagnostics": report}


def pilot_post_cap_stock_target_counts(result):
    """Return bounded REMX and total direct-stock target counts, no names."""
    if type(result) is not dict or result.get("run_valid") is not True:
        adapter._fail("score-floor1 pilot is not a valid completed result")
    sleeve = result.get("aggregates", {}).get("sleeve_diagnostics", {})
    fields, rows = sleeve.get("fields"), sleeve.get("rows")
    if (type(fields) is not list or type(rows) is not list or len(rows) != 6
            or fields != [
                "universe_id", "etf_ticker", "decision_count", "coverage_valid_count",
                "coverage_invalid_count", "positive_score_count_sum",
                "selected_security_count_sum", "post_cap_stock_target_count_sum",
                "etf_target_weight_sum", "duplicate_cap_excess_weight_sum",
                "coverage_refusal_reason_counts", "selection_status_counts",
            ]):
        adapter._fail("score-floor1 pilot sleeve census changed")
    if (any(type(row) is not list or len(row) != 12
            or type(row[7]) is not int or not 0 <= row[7] <= 2610
            for row in rows)
            or {row[0] for row in rows} != {"SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE"}):
        adapter._fail("score-floor1 pilot direct-stock count census changed")
    remx = [row for row in rows if row[0] == "REMX" and row[1] == "REMX"]
    if len(remx) != 1:
        adapter._fail("score-floor1 pilot REMX stock count changed")
    return remx[0][7], sum(row[7] for row in rows)


def require_successful_pilot(plan):
    """Before any non-pilot launch, authenticate a spent positive R261 result."""
    if plan.candidate_id == PILOT:
        return
    if plan.family != FAMILY:
        adapter._fail("score-floor1 pilot family changed")
    for attempt in (1, 2, 3):
        pilot = dataclasses.replace(plan, candidate_id=PILOT, attempt=attempt)
        result_path = adapter._path(pilot, "result")
        if not result_path.exists():
            continue
        launch = adapter.common._read(adapter._path(pilot, "launch"))
        adapter._receipt(pilot, launch)
        terminal = adapter.common._read(adapter._path(pilot, "terminal"))
        read_claim = adapter.common._read(adapter._path(pilot, "read-claim"))
        expected = {
            "candidate_id": PILOT, "attempt": attempt,
            "project_id": launch["project_id"], "backtest_id": launch["backtest_id"],
            "status": "Completed.",
        }
        result = adapter._read_artifact(result_path)
        if (terminal != expected or read_claim != expected
                or any(result.get(key) != value for key, value in expected.items())
                or result.get("manifest_sha256") != adapter.FROZEN_QCOM_SCORE_FLOOR1_MANIFEST_SHA256
                or result.get("projection_sha256") != adapter._candidate(pilot)["projection_sha256"]):
            adapter._fail("score-floor1 pilot result lineage changed")
        # Re-parse the exact bounded custom statistics retained by the sole
        # QC read. A mutable local result JSON cannot invent stock counts to
        # unlock the other six launches. This performs no second QC call.
        retained = adapter._read_artifact(adapter._path(pilot, "raw-custom"))
        if (type(retained) is not dict
                or set(retained) != set(expected) | {"statistics"}
                or any(retained.get(key) != value for key, value in expected.items())
                or type(retained["statistics"]) is not dict
                or set(retained["statistics"]) != set(STATISTIC_NAMES)):
            adapter._fail("score-floor1 pilot retained statistic lineage changed")
        reparsed = parse_order(pilot, retained["statistics"])
        if result != {
            **expected, **reparsed,
            "manifest_sha256": adapter.FROZEN_QCOM_SCORE_FLOOR1_MANIFEST_SHA256,
            "projection_sha256": adapter._candidate(pilot)["projection_sha256"],
        }:
            adapter._fail("score-floor1 pilot saved result differs from retained statistics")
        if result.get("run_valid") is False:
            # A completed but invalid attempt is eligible for the next of
            # the same candidate's three slots; it cannot open the ladder.
            continue
        remx_count, total_count = pilot_post_cap_stock_target_counts(result)
        if remx_count < 1 or total_count <= 12211:
            adapter._fail("score-floor1 pilot did not increase direct-stock selections")
        return
    adapter._fail("score-floor1 pilot result is unavailable")
