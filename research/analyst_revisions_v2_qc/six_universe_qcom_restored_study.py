"""Prospective QCOM-admitted analogues of historical R235--R246 orders.

This separate exploratory family changes only the exact direct-stock QCOM
exclusion in each frozen predecessor source. It has no confirmation, paper,
live, or trading authority. Importing this module performs no cloud action.
"""

from . import accepted_risk_delta_order_package as delta
from . import accepted_risk_matched_diagnostics as diagnostics
from . import six_universe_qcom_entry_only_projection as entry_only
from . import six_universe_qcom_exclusion_study as excluded
from . import six_universe_qcom_restored_projection as renderer
from . import six_universe_relaxed_submission as adapter


FAMILY = "qcom_restored"
MANIFEST_SCHEMA = "arv2-six-qcom-restored-historical-analogues-v1"
CANDIDATES = {f"R{new}": f"R{old}" for new, old in zip(range(248, 260), range(235, 247))}
STATISTIC_NAMES = [
    "ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES",
    excluded.DIAGNOSTIC_NAME,
]
PROTOCOL = {
    "candidate_ids": list(CANDIDATES),
    "predecessor_ids": list(CANDIDATES.values()),
    "one_change": "remove_exact_direct_stock_QCOM_exclusion_from_each_predecessor",
    "historical_order_window": ["2021-01-04", "2025-12-31"],
    "decision_count": excluded.PROTOCOL["decision_count"],
    "observation_count": excluded.PROTOCOL["observation_count"],
    "cost_bps_per_side": excluded.PROTOCOL["cost_bps_per_side"],
    "slippage_bps": 0,
    "target_gross_exposure": excluded.PROTOCOL["target_gross_exposure"],
    "admission_leverage": excluded.PROTOCOL["admission_leverage"],
    "maximum_attempts_per_candidate": 3,
    "physical_orders": True,
    "sensitivity_only": True,
    "confirmation": False,
    "formal_alpha": False,
    "paper_live_trading": False,
}
_FAMILY_BY_PREDECESSOR = {
    **{f"R{number}": "qcom_exclusion_tilt" for number in range(235, 238)},
    **{f"R{number}": "qcom_exclusion_coverage10" for number in range(238, 242)},
    **{f"R{number}": "qcom_exclusion_three_name" for number in range(242, 246)},
    "R246": "qcom_entry_only",
}
_ROW_FIELDS = frozenset({
    "candidate_id", "predecessor_candidate_id", "predecessor_family",
    "predecessor_manifest_sha256", "predecessor_projection_sha256",
    "predecessor_profile_sha256", "project_name", "backtest_name", "kind",
    "arm", "slippage_bps", "tilt_fraction", "coverage_policy_id",
    "analyst_revision_economic_usage", "reference_repair_enabled",
    "role", "projection_schema", "projection_sha256", "profile_id",
    "profile_sha256", "matched_baseline_profile_sha256", "source_files_sha256",
    "source_file_count", "total_source_bytes", "statistic_names",
    "meta_schema", "summary_schema",
})


def _parent(predecessor):
    family = _FAMILY_BY_PREDECESSOR[predecessor]
    methods = {
        "qcom_exclusion_tilt": (
            adapter._qcom_exclusion_tilt_manifest,
            adapter.FROZEN_QCOM_EXCLUSION_TILT_MANIFEST_SHA256),
        "qcom_exclusion_coverage10": (
            adapter._qcom_exclusion_coverage10_manifest,
            adapter.FROZEN_QCOM_EXCLUSION_COVERAGE10_MANIFEST_SHA256),
        "qcom_exclusion_three_name": (
            adapter._qcom_exclusion_three_name_manifest,
            adapter.FROZEN_QCOM_EXCLUSION_THREE_NAME_MANIFEST_SHA256),
        "qcom_entry_only": (
            adapter._qcom_entry_only_manifest,
            adapter.FROZEN_QCOM_ENTRY_ONLY_MANIFEST_SHA256),
    }
    manifest, pin = methods[family]
    rows = [row for row in manifest()["candidates"] if row["candidate_id"] == predecessor]
    if len(rows) != 1:
        adapter._fail("QCOM-restored predecessor census changed")
    return family, pin, rows[0]


def _economic_usage(arm):
    return (
        "none_authenticated_score_clock_only" if arm == "ar_off" else
        entry_only.ECONOMIC_USAGE if arm == "ar_on0" else
        "entry_count_and_weight"
    )


def _expected_meta_schema(candidate, predecessor, arm):
    stem = f"arv2-six-matched-qcom-admitted-{candidate.lower()}"
    if predecessor in {"R235", "R236", "R237", "R246"}:
        return stem + "-meta-v1"
    if predecessor in {"R238", "R239", "R240", "R241"}:
        return stem + f"-coverage10-{arm}-meta-v1"
    return stem + f"-three-name-{arm}-meta-v1"


def validate_manifest(value):
    """Refuse aliases of spent candidates and any changed source or economics."""
    rows = value.get("candidates") if type(value) is dict else None
    if (
        type(value) is not dict
        or set(value) != {"schema", "protocol", "package_sha256",
                          "activation_manifest_sha256", "candidates"}
        or value["schema"] != MANIFEST_SCHEMA
        or type(value["protocol"]) is not dict or value["protocol"] != PROTOCOL
        or value["package_sha256"] != delta.EXPECTED_DELTA_PACKAGE_SHA256
        or value["activation_manifest_sha256"] != excluded.HISTORICAL_ACTIVATION_SHA256
        or type(rows) is not list or len(rows) != 12
    ):
        adapter._fail("QCOM-restored protocol or historical inputs changed")
    projects, backtests, projections, profiles, sources = set(), set(), set(), set(), set()
    for row, (candidate, predecessor) in zip(rows, CANDIDATES.items()):
        family, parent_pin, parent = _parent(predecessor)
        slug = candidate.lower()
        identity = f"qcom_admitted_{slug}"
        old = "qcom_excluded"
        digest_keys = (
            "projection_sha256", "profile_sha256", "matched_baseline_profile_sha256",
            "source_files_sha256",
        )
        if (
            type(row) is not dict or set(row) != _ROW_FIELDS
            or row["candidate_id"] != candidate
            or row["predecessor_candidate_id"] != predecessor
            or row["predecessor_family"] != family
            or row["predecessor_manifest_sha256"] != parent_pin
            or row["predecessor_projection_sha256"] != parent["projection_sha256"]
            or row["predecessor_projection_sha256"] != renderer.PREDECESSOR_SHA256[predecessor]
            or row["predecessor_profile_sha256"] != parent["profile_sha256"]
            or row["project_name"] != (
                f"ARV2 SIX QCOM RESTORED {candidate} FROM {predecessor} 2021 2025")
            or row["backtest_name"] != (
                f"ARV2 {candidate} QCOM restored from {predecessor} 2021 2025")
            or row["kind"] != "order" or row["arm"] != parent["arm"]
            or type(row["slippage_bps"]) is not int or row["slippage_bps"] != 0
            or row["tilt_fraction"] != parent["tilt_fraction"]
            or row["coverage_policy_id"] != parent.get("coverage_policy_id")
            or row["analyst_revision_economic_usage"] != _economic_usage(row["arm"])
            or row["reference_repair_enabled"] is not True
            or row["role"] != parent["role"].replace(old, identity)
            or row["projection_schema"] != f"arv2-six-qcom-admitted-{slug}-projection-v1"
            or row["profile_id"] != parent["profile_id"].replace(
                "qcom-excluded", f"qcom-admitted-{slug}")
            or row["statistic_names"] != STATISTIC_NAMES
            or row["meta_schema"] != _expected_meta_schema(
                candidate, predecessor, row["arm"])
            or row["summary_schema"] != parent["summary_schema"].replace(
                "qcom-excluded", f"qcom-admitted-{slug}")
            or type(row["source_file_count"]) is not int
            or row["source_file_count"] != 17
            or type(row["total_source_bytes"]) is not int
            or not 0 < row["total_source_bytes"] < 448 * 1024
            or any(type(row[key]) is not str or adapter.cap._HEX.fullmatch(row[key]) is None
                   for key in digest_keys)
            or row["project_name"] in projects or row["backtest_name"] in backtests
            or row["projection_sha256"] in projections or row["profile_sha256"] in profiles
            or row["source_files_sha256"] in sources
        ):
            adapter._fail("QCOM-restored candidate or source identity changed")
        projects.add(row["project_name"])
        backtests.add(row["backtest_name"])
        projections.add(row["projection_sha256"])
        profiles.add(row["profile_sha256"])
        sources.add(row["source_files_sha256"])
    return value


def parse_order(plan, statistics):
    """Parse only three bounded custom statistics for a completed order run."""
    row = adapter._candidate(plan)
    if (plan.family != FAMILY or row["candidate_id"] not in CANDIDATES
            or set(statistics) != set(STATISTIC_NAMES)):
        adapter._fail("QCOM-restored result family or statistic inventory changed")
    extra = {"comparison_arm", "analyst_revision_economic_usage"}
    if row["coverage_policy_id"] is not None:
        extra.add("coverage_policy_id")
    parsed = adapter._parse_order_common(
        plan, statistics, expected_geometry=None,
        decision_count=PROTOCOL["decision_count"],
        extra_meta_fields=frozenset({"matched_diagnostics_sha256"}),
        extra_aggregate_fields=frozenset(extra),
        result_transport="three_bounded_custom_summary_statistics",
    )
    aggregate = parsed["aggregates"]
    if (
        aggregate.get("comparison_arm") != row["arm"]
        or aggregate.get("analyst_revision_economic_usage")
            != row["analyst_revision_economic_usage"]
        or (row["coverage_policy_id"] is not None
            and aggregate.get("coverage_policy_id") != row["coverage_policy_id"])
        or any(key in aggregate or key in parsed["meta"] for key in (
            "stock_exclusion_policy_id", "excluded_logical_security_sha256",
            "stock_exclusion_scope"))
    ):
        adapter._fail("QCOM-restored arm economics or coverage changed")
    report = adapter._statistic(statistics[excluded.DIAGNOSTIC_NAME])
    if parsed["meta"].get("matched_diagnostics_sha256") != adapter._sha(report):
        adapter._fail("QCOM-restored diagnostic digest changed")
    diagnostics.validate_report(
        report, "ar_off" if row["arm"] == "ar_off" else "ar_on100", 0,
        reference_repair_enabled=True,
    )
    if report["overall_cumulative_return"] != aggregate["account"]["cumulative_return"]:
        adapter._fail("QCOM-restored diagnostic and account return differ")
    return {**parsed, "diagnostics": report}
