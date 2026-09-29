"""Prospective eight-sleeve, QCOM-admitted order sensitivity.

R267 is an input-only prerequisite.  R268 is the AR-independent market-cap
baseline; R269--R275 transfer 80--200% of the bounded analyst revision tilt;
R276 is the actual eight-ETF basket control.  All nine are distinct exploratory
historical looks, not confirmation or trading authority.
"""

import dataclasses
from decimal import Decimal, localcontext
import os
from pathlib import Path
import stat

from . import accepted_risk_matched_diagnostics as diagnostics
from . import eight_universe_input_submission as input_adapter
from . import eight_universe_qcom_admitted_projection as renderer
from . import six_universe_relaxed_submission as adapter


FAMILY = "eight_universe"
MANIFEST_SCHEMA = "arv2-eight-universe-qcom-admitted-order-study-v1"
CANDIDATE_ARMS = {
    "R268": "ar_off",
    **{f"R{269 + index}": f"ar_on{percent}"
       for index, percent in enumerate(renderer.floor1.TILT_PERCENTS)},
    "R276": "eight_etf_basket",
}
BASELINE = "R268"
ETF_BASKET = "R276"
CORE_CANDIDATES = {candidate: arm for candidate, arm in CANDIDATE_ARMS.items()
                   if candidate != ETF_BASKET}
DIAGNOSTIC_NAME = "ARV2_EIGHT_GATE_ORDER_DIAGNOSTICS"
STATISTIC_NAMES = [
    "ARV2_EIGHT_GATE_ORDER_META",
    "ARV2_EIGHT_GATE_ORDER_AGGREGATES",
    DIAGNOSTIC_NAME,
]
PROTOCOL = {
    "candidate_ids": list(CANDIDATE_ARMS),
    "arms": list(CANDIDATE_ARMS.values()),
    "historical_order_window": ["2021-01-04", "2025-12-31"],
    "decision_count": 261,
    "observation_count": 1255,
    "universe_ids": list(renderer.UNIVERSES),
    "new_universe_ids": ["XLI", "XLF"],
    "coverage_policy_ids": {
        "ar_off_and_basket": renderer.OFF_POLICY_ID,
        "ar_on_ladder": renderer.NEW_POLICY_ID,
    },
    "minimum_verified_name_count": 3,
    "minimum_positive_score_counts": {"ar_off_and_basket": 0, "ar_on_ladder": 1},
    "target_gross_exposure": "0.98",
    "sleeve_budget": "0.1225",
    "direct_stock_weight_cap": "0.098",
    "modeled_fee_bps_per_side": "10",
    "slippage_bps": 0,
    "admission_leverage": "2",
    "baseline_candidate_id": BASELINE,
    "baseline_stock_rule": "coverage_valid_top_ten_market_cap_independent_of_analyst_scores",
    "baseline_is_count_matched_to_AR_on": False,
    "basket_candidate_id": ETF_BASKET,
    "basket_control_optional": True,
    "basket_rule": "fixed_eight_actual_ETF_sleeve_budgets_no_direct_stocks",
    "input_candidate_id": "R267",
    "input_candidate_manifest_sha256": input_adapter._MANIFEST_SHA256,
    "input_required_new_sleeve_joint_pass_total_at_least": 26,
    "input_required_new_sleeve_joint_pass_each_year_at_least": 1,
    "maximum_attempts_per_candidate": 3,
    "physical_orders": True,
    "sensitivity_only": True,
    "confirmation": False,
    "formal_alpha": False,
    "paper_live_trading": False,
}
_ROW_FIELDS = frozenset({
    "candidate_id", "arm", "source_candidate_id", "source_family",
    "source_manifest_sha256", "source_projection_sha256",
    "source_profile_sha256", "project_name", "backtest_name", "kind",
    "slippage_bps", "tilt_fraction", "coverage_policy_id",
    "minimum_verified_name_count", "minimum_positive_score_count",
    "analyst_revision_economic_usage", "reference_repair_enabled",
    "role", "projection_schema", "projection_sha256", "profile_id",
    "profile_sha256", "matched_baseline_profile_sha256",
    "source_files_sha256", "source_file_count", "total_source_bytes",
    "statistic_names", "meta_schema", "summary_schema",
})
_HEX = adapter.cap._HEX


def _fail(message):
    adapter._fail(message)


def _source_rows():
    floor = adapter._qcom_score_floor1_manifest()["candidates"]
    restored = adapter._qcom_restored_manifest()["candidates"]
    return ({row["candidate_id"]: row for row in floor},
            {row["candidate_id"]: row for row in restored})


def _usage(arm):
    return ("entry_count_and_weight" if arm.startswith("ar_on")
            else "none_authenticated_score_clock_only")


def _coverage_policy(arm):
    return renderer.NEW_POLICY_ID if arm.startswith("ar_on") else renderer.OFF_POLICY_ID


def _score_floor(arm):
    # The inherited AR-off module constant is dead for this rendered role:
    # _selected_ids selects cap-ranked names and reports zero positive counts.
    return 1 if arm.startswith("ar_on") else 0


def validate_manifest(value):
    """Reject altered arms, source ancestry, economics, or result inventory."""
    rows = value.get("candidates") if type(value) is dict else None
    if (type(value) is not dict
            or set(value) != {"schema", "protocol", "package_sha256",
                              "activation_manifest_sha256", "candidates"}
            or value["schema"] != MANIFEST_SCHEMA
            or value["protocol"] != PROTOCOL
            or type(rows) is not list or len(rows) != len(CANDIDATE_ARMS)):
        _fail("eight-universe protocol or candidate census changed")
    from . import accepted_risk_delta_order_package as delta
    from . import six_universe_matched_study as historical
    if (value["package_sha256"] != delta.EXPECTED_DELTA_PACKAGE_SHA256
            or value["activation_manifest_sha256"] != historical.HISTORICAL_ACTIVATION_SHA256):
        _fail("eight-universe historical input lineage changed")
    floor, restored = _source_rows()
    projects, backtests, projections, profiles, sources = set(), set(), set(), set(), set()
    for row, (candidate, arm) in zip(rows, CANDIDATE_ARMS.items()):
        source_id, parent_id, parent_projection = renderer.PARENT_IDS[arm]
        family = "qcom_score_floor1" if arm.startswith("ar_on") else "qcom_restored"
        source_manifest = (adapter.FROZEN_QCOM_SCORE_FLOOR1_MANIFEST_SHA256
                           if arm.startswith("ar_on") else adapter.FROZEN_QCOM_RESTORED_MANIFEST_SHA256)
        parent = (floor if arm.startswith("ar_on") else restored)[parent_id]
        fraction = (f"{int(arm[5:]) // 100}.{int(arm[5:]) % 100:02d}"
                    if arm.startswith("ar_on") else "0.00")
        slug = candidate.lower()
        expected_role = (f"matched_qcom_admitted_{slug}_eight_score_floor1_three_name_{arm}_s0"
                         if arm.startswith("ar_on") else
                         f"matched_qcom_admitted_{slug}_eight_three_name_ar_off_s0")
        expected_profile = (f"arv2-eight-matched-qcom-admitted-{slug}-eight-score-floor1-"
                            f"three-name-{arm}-s0-profile-v1" if arm.startswith("ar_on") else
                            f"arv2-eight-matched-qcom-admitted-{slug}-eight-three-name-ar_off-s0-profile-v1")
        writer_stem = (f"arv2-eight-matched-qcom-admitted-{slug}-eight-score-floor1-three-name-{arm}"
                       if arm.startswith("ar_on") else
                       f"arv2-eight-matched-qcom-admitted-{slug}-eight-three-name-ar_off")
        if (type(row) is not dict or set(row) != _ROW_FIELDS
                or row["candidate_id"] != candidate or row["arm"] != arm
                or row["source_candidate_id"] != parent_id
                or row["source_family"] != family
                or row["source_manifest_sha256"] != source_manifest
                or row["source_projection_sha256"] != parent_projection
                or row["source_projection_sha256"] != parent["projection_sha256"]
                or row["source_profile_sha256"] != parent["profile_sha256"]
                or row["project_name"] != f"ARV2 EIGHT QCOM {candidate} {arm.upper()} 2021 2025"
                or row["backtest_name"] != f"ARV2 {candidate} eight QCOM {arm} 2021 2025"
                or row["kind"] != "order" or type(row["slippage_bps"]) is not int
                or row["slippage_bps"] != 0 or row["tilt_fraction"] != fraction
                or row["coverage_policy_id"] != _coverage_policy(arm)
                or type(row["minimum_verified_name_count"]) is not int
                or row["minimum_verified_name_count"] != 3
                or type(row["minimum_positive_score_count"]) is not int
                or row["minimum_positive_score_count"] != _score_floor(arm)
                or row["analyst_revision_economic_usage"] != _usage(arm)
                or row["reference_repair_enabled"] is not True
                or row["role"] != expected_role
                or row["profile_id"] != expected_profile
                or row["projection_schema"] != f"arv2-eight-qcom-admitted-{slug}-projection-v1"
                or row["meta_schema"] != f"{writer_stem}-meta-v1"
                or row["summary_schema"] != f"{writer_stem}-summary-v1"
                or row["statistic_names"] != STATISTIC_NAMES
                or type(row["source_file_count"]) is not int or row["source_file_count"] != 17
                or type(row["total_source_bytes"]) is not int
                or not 0 < row["total_source_bytes"] + 32_768 <= 448 * 1024
                or any(type(row[key]) is not str or _HEX.fullmatch(row[key]) is None
                       for key in ("projection_sha256", "profile_sha256",
                                   "matched_baseline_profile_sha256", "source_files_sha256"))
                or row["project_name"] in projects or row["backtest_name"] in backtests
                or row["projection_sha256"] in projections or row["profile_sha256"] in profiles
                or row["source_files_sha256"] in sources):
            _fail(f"eight-universe candidate, parent, or source identity changed: {candidate}")
        projects.add(row["project_name"])
        backtests.add(row["backtest_name"])
        projections.add(row["projection_sha256"])
        profiles.add(row["profile_sha256"])
        sources.add(row["source_files_sha256"])
    return value


def _validate_eight_diagnostics(report, arm):
    """Authenticate eight-sleeve geometry using the frozen six-sleeve validator."""
    if type(report) is not dict:
        _fail("eight-universe diagnostic is not a record")
    six_key = "six_etf_panel_row_count"
    eight_key = "eight_etf_panel_row_count"
    expected = ({"schema", "arm", "slippage_bps_per_side", "overall_cumulative_return",
                 "annual_account_fields", "annual_account_rows", "membership_cap_path_sha256",
                 "source_snapshot_count", "diagnostic_history_call_count", "etf_daily_panel_sha256",
                 eight_key, "year_universe_fields", "year_universe_rows",
                 "universe_realized_profit_attributed", "all_stock_price_equality_proved",
                 "minute_execution_price_equality_proved", "daily_price_normalization", "fill_forward"}
                | diagnostics.REFERENCE_REPAIR_FIELDS)
    if (set(report) != expected
            or report["schema"] != "arv2-eight-matched-historical-diagnostics-v2-closing-minute"
            or report["arm"] != arm or report[eight_key] != 10040
            or type(report["year_universe_rows"]) is not list
            or len(report["year_universe_rows"]) != 40):
        _fail("eight-universe diagnostic schema or panel census changed")
    rows = report["year_universe_rows"]
    if (any(type(item) is not list or len(item) != 7 for item in rows)
            or [(item[0], item[1]) for item in rows]
            != sorted((str(year), universe) for year in range(2021, 2026)
                      for universe in renderer.UNIVERSES)):
        _fail("eight-universe year/sleeve diagnostic census changed")
    for item in rows:
        if (any(type(item[position]) is not int or item[position] < 0
                for position in range(2, 6))
                or item[3] > item[2] or item[4] > item[2] * 10
                or item[5] > item[4] or type(item[6]) is not str):
            _fail("eight-universe year/sleeve diagnostic bound changed")
        weight = diagnostics._base._decimal(
            item[6], "eight-universe fallback target weight", nonnegative=True)
        if weight > Decimal(item[2]):
            _fail("eight-universe year/sleeve fallback target bound changed")
    if any(sum(item[2] for item in rows if item[1] == universe) != 261
           for universe in renderer.UNIVERSES):
        _fail("eight-universe sleeve decision count changed")
    old_arm = ("ar_on100" if arm.startswith("ar_on") else
               "six_etf_basket" if arm == "eight_etf_basket" else "ar_off")
    six_report = {**report,
                  "schema": diagnostics.REFERENCE_REPAIR_SCHEMA,
                  "arm": old_arm,
                  six_key: 7530,
                  "year_universe_rows": [item for item in rows if item[1] in renderer.UNIVERSES[:6]]}
    del six_report[eight_key]
    diagnostics.validate_report(six_report, old_arm, 0,
                                reference_repair_enabled=True)
    return True


def parse_order(plan, statistics):
    """Read only the three bounded, digest-bound order statistics."""
    row = adapter._candidate(plan)
    if (plan.family != FAMILY or row["candidate_id"] not in CANDIDATE_ARMS
            or set(statistics) != set(STATISTIC_NAMES)):
        _fail("eight-universe result family or statistic inventory changed")
    parsed = adapter._parse_order_common(
        plan, statistics, expected_geometry=None,
        decision_count=PROTOCOL["decision_count"],
        extra_meta_fields=frozenset({"matched_diagnostics_sha256"}),
        extra_aggregate_fields=frozenset({
            "comparison_arm", "analyst_revision_economic_usage", "coverage_policy_id",
        }),
        result_transport="three_bounded_custom_summary_statistics",
        eight_universe=True,
    )
    aggregate = parsed["aggregates"]
    if (aggregate.get("comparison_arm") != row["arm"]
            or aggregate.get("analyst_revision_economic_usage") != _usage(row["arm"])
            or aggregate.get("coverage_policy_id") != _coverage_policy(row["arm"])
            or any(field in aggregate or field in parsed["meta"] for field in (
                "stock_exclusion_policy_id", "excluded_logical_security_sha256",
                "stock_exclusion_scope"))):
        _fail("eight-universe arm, coverage, or QCOM admission changed")
    report = adapter._statistic(statistics[DIAGNOSTIC_NAME])
    if parsed["meta"].get("matched_diagnostics_sha256") != adapter._sha(report):
        _fail("eight-universe diagnostic digest changed")
    _validate_eight_diagnostics(report, row["arm"])
    if report["overall_cumulative_return"] != aggregate["account"]["cumulative_return"]:
        _fail("eight-universe diagnostic and account return differ")
    return {**parsed, "diagnostics": report}


def compare_results(results):
    """Compare eight core order arms, plus R276 only when separately present.

    The eight-ETF basket is a separate reference, never a substituted
    AR-off stock baseline. Matching source digests do not prove stock-minute
    execution-price equality or create an independent confirmation sample.
    """
    core = list(CORE_CANDIDATES)
    if type(results) is not dict or list(results) not in (core, core + [ETF_BASKET]):
        _fail("eight-universe comparison needs the eight ordered core arms and optional R276")
    basket_present = ETF_BASKET in results
    reference = results[BASELINE]
    for candidate in results:
        arm = CANDIDATE_ARMS[candidate]
        result = results[candidate]
        if type(result) is not dict or result.get("run_valid") is not True:
            _fail("eight-universe comparison requires every supplied order run to be valid")
        report = result.get("diagnostics")
        _validate_eight_diagnostics(report, arm)
        aggregate = result.get("aggregates")
        if type(aggregate) is not dict:
            _fail("eight-universe comparison aggregate is absent")
        account = aggregate.get("account")
        execution = aggregate.get("execution")
        if (type(account) is not dict or type(execution) is not dict
                or aggregate.get("comparison_arm") != arm
                or aggregate.get("analyst_revision_economic_usage") != _usage(arm)
                or aggregate.get("coverage_policy_id") != _coverage_policy(arm)
                or aggregate.get("target_gross_exposure") != "0.98"
                or aggregate.get("admission_leverage") != "2"
                or account.get("first_observation_session") != "2021-01-04"
                or account.get("last_observation_session") != "2025-12-31"
                or type(account.get("observation_count")) is not int
                or account["observation_count"] != 1255
                or type(execution.get("submitted_rebalance_count")) is not int
                or execution["submitted_rebalance_count"] != 261
                or type(execution.get("completed_rebalance_count")) is not int
                or execution["completed_rebalance_count"] != 261
                or not adapter.cap._finite_decimal(account.get("starting_equity"))
                or Decimal(account["starting_equity"]) <= 0
                or not adapter.cap._finite_decimal(account.get("cumulative_return"))
                or account["cumulative_return"] != report["overall_cumulative_return"]):
            _fail("eight-universe comparison economics or order census changed")
        if candidate == BASELINE:
            continue
        old = reference["aggregates"]
        if account["starting_equity"] != old["account"]["starting_equity"]:
            _fail("eight-universe comparison starting capital differs")
        for key in ("membership_cap_path_sha256", "etf_daily_panel_sha256"):
            if report[key] != reference["diagnostics"][key]:
                _fail("eight-universe comparison reference-data vintage differs")
        for key in ("pit_callback_source_row_count",
                    "fundamental_snapshot_unavailable_decision_count",
                    "constituent_collection_unavailable_decision_count",
                    "constituent_collection_unavailable_universe_counts"):
            if aggregate.get(key) != old.get(key):
                _fail("eight-universe comparison non-AR source census differs")
    with localcontext() as context:
        context.prec = 96
        off = Decimal(reference["aggregates"]["account"]["cumulative_return"])
        basket = (Decimal(results[ETF_BASKET]["aggregates"]["account"]["cumulative_return"])
                  if basket_present else None)
        ladder = []
        for candidate, arm in CORE_CANDIDATES.items():
            if not arm.startswith("ar_on"):
                continue
            current = Decimal(results[candidate]["aggregates"]["account"]["cumulative_return"])
            row = {"candidate_id": candidate, "tilt_percent": int(arm[5:]),
                   "AR_on_minus_R268_AR_off_percentage_points": str((current - off) * 100)}
            if basket_present:
                row["AR_on_minus_R276_eight_ETF_percentage_points"] = str((current - basket) * 100)
            ladder.append(row)
        off_vs_basket = str((off - basket) * 100) if basket_present else None
    comparison = {"comparison_valid": True, "sensitivity_only": True,
            "confirmation": False, "formal_alpha": False,
            "baseline_candidate_id": BASELINE, "basket_control_present": basket_present,
            "ladder": ladder,
            "reference_data_scope": "common_membership_caps_and_eight_ETF_RAW_daily_panel_not_full_stock_minute_fill_tape"}
    if basket_present:
        comparison["basket_candidate_id"] = ETF_BASKET
        comparison["R268_AR_off_minus_R276_eight_ETF_percentage_points"] = off_vs_basket
    return comparison


_R267_CONTROL = (Path(__file__).resolve().parents[2] /
    "artifacts/analyst_revisions_v2/eight_universe_input_r267_qc_control_20260929")


def _r267_path(attempt, suffix):
    if type(attempt) is not int or attempt not in (1, 2, 3):
        _fail("R267 attempt is outside the frozen three-slot budget")
    try:
        info = _R267_CONTROL.stat(follow_symlinks=False)
    except OSError:
        _fail("R267 input result is unavailable")
    if (not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.getuid()):
        _fail("R267 input control directory is not private")
    return _R267_CONTROL / f"R267-A{attempt}-{suffix}.json"


def _r267_admits(counts):
    """The preregistered 10%/three-name count gate; never inspect outcomes."""
    if (type(counts) is not dict or set(counts) != {"meta", "sleeves", "overlap"}
            or type(counts["meta"]) is not dict
            or counts["meta"].get("decision_count") != 261
            or counts["meta"].get("sleeve_decision_count") != 8 * 261
            or type(counts["sleeves"]) is not dict
            or set(counts["sleeves"]) != set(renderer.UNIVERSES)):
        _fail("R267 input decision or eight-sleeve census changed")
    metric = "relaxed_joint_pass_10_verified3_count"
    for ticker in ("XLI", "XLF"):
        sleeve = counts["sleeves"][ticker]
        if (type(sleeve) is not dict or sleeve.get("universe_id") != ticker
                or type(sleeve.get("totals")) is not dict
                or type(sleeve.get("years")) is not list
                or len(sleeve["years"]) != 5):
            _fail("R267 new-sleeve count inventory changed")
        total = sleeve["totals"].get(metric)
        annual = sleeve["years"]
        counts_by_year = [item.get(metric) if type(item) is dict else None
                          for item in annual]
        if (type(total) is not int or total < 26
                or [item.get("year") if type(item) is dict else None for item in annual]
                   != [2021, 2022, 2023, 2024, 2025]
                or any(type(item) is not int or item < 1 for item in counts_by_year)
                or sum(counts_by_year) != total):
            _fail("R267 XLI/XLF preregistered input-readiness count gate did not pass")
    return True


def require_input_readiness(plan):
    """Reparse one completed R267 read and enforce its count-only gate."""
    if type(plan) is not adapter.RelaxedQcPlan or plan.family != FAMILY:
        _fail("eight-universe input prerequisite plan changed")
    from . import accepted_risk_eight_universe_input_qc_runtime as input_runtime
    found = 0
    for attempt in (1, 2, 3):
        result_path = _r267_path(attempt, "result")
        if not result_path.exists():
            continue
        found += 1
        input_plan = input_adapter.build_plan(plan.organization_id, _R267_CONTROL, attempt)
        claim = input_adapter.common._read_control(_r267_path(attempt, "claim"))
        receipt = input_adapter.common._read_control(_r267_path(attempt, "launch"))
        terminal = input_adapter.common._read_control(_r267_path(attempt, "terminal"))
        read_claim = input_adapter.common._read_control(_r267_path(attempt, "result-read-claim"))
        raw = input_adapter.common._read_control(_r267_path(attempt, "raw-custom"))
        saved = input_adapter.common._read_control(result_path)
        project = input_adapter.common._read_control(_r267_path(1, "project"))
        if (claim != {
                "candidate_id": "R267", "attempt": attempt,
                "project_name": input_plan.project_name,
                "projection_sha256": input_plan.projection_sha256,
                "profile_sha256": input_plan.profile_sha256,
            } or receipt.get("candidate_id") != "R267"
            or receipt.get("attempt") != attempt
            or receipt.get("project_id") != project.get("project_id")
            or receipt.get("project_name") != input_plan.project_name
            or receipt.get("backtest_name") != input_plan.backtest_name
            or receipt.get("projection_sha256") != input_plan.projection_sha256
            or receipt.get("profile_sha256") != input_plan.profile_sha256
            or project != {
                "candidate_id": "R267", "project_id": receipt.get("project_id"),
                "project_name": input_plan.project_name,
                "projection_sha256": input_plan.projection_sha256,
            } or terminal != {
                "candidate_id": "R267", "attempt": attempt,
                "project_id": receipt.get("project_id"),
                "backtest_id": receipt.get("backtest_id"), "status": "Completed.",
            } or read_claim != {
                "candidate_id": "R267", "attempt": attempt,
                "project_id": receipt.get("project_id"),
                "backtest_id": receipt.get("backtest_id"),
            } or type(raw) is not dict or set(raw) != {
                "candidate_id", "attempt", "project_id", "backtest_id",
                "backtest_name", "projection_sha256", "profile_sha256",
                "statistics",
            } or any(raw.get(key) != receipt.get(key) for key in (
                "candidate_id", "attempt", "project_id", "backtest_id",
                "backtest_name", "projection_sha256", "profile_sha256"))
            or type(raw["statistics"]) is not dict
            or set(raw["statistics"]) != set(input_runtime.expected_custom_summary_statistic_names())):
            _fail("R267 input claim, result, or source lineage changed")
        response = {"backtest": {
            "projectId": receipt["project_id"], "backtestId": receipt["backtest_id"],
            "name": receipt["backtest_name"], "status": "Completed.",
            "statistics": raw["statistics"],
        }}
        reparsed = input_adapter.parse_counts_response(response, input_plan, receipt)
        if reparsed != saved:
            _fail("R267 retained input statistics and result disagree")
        _r267_admits(saved)
    if found != 1:
        _fail("exactly one authenticated R267 input result is required")
    return True


def require_completed_baseline(plan):
    """Permit nonbaseline launches only after an authenticated valid R268 run."""
    if type(plan) is not adapter.RelaxedQcPlan or plan.family != FAMILY:
        _fail("eight-universe baseline prerequisite plan changed")
    if plan.candidate_id == BASELINE:
        return True
    for attempt in (1, 2, 3):
        baseline = dataclasses.replace(plan, candidate_id=BASELINE, attempt=attempt)
        result_path = adapter._path(baseline, "result")
        if not result_path.exists():
            continue
        launch = adapter.common._read(adapter._path(baseline, "launch"))
        adapter._receipt(baseline, launch)
        expected = {
            "candidate_id": BASELINE, "attempt": attempt,
            "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"], "status": "Completed.",
        }
        if (adapter.common._read(adapter._path(baseline, "terminal")) != expected
                or adapter.common._read(adapter._path(baseline, "read-claim")) != expected):
            _fail("eight-universe baseline completion lineage changed")
        retained = adapter._read_artifact(adapter._path(baseline, "raw-custom"))
        if (type(retained) is not dict or set(retained) != set(expected) | {"statistics"}
                or any(retained.get(key) != value for key, value in expected.items())
                or type(retained["statistics"]) is not dict
                or set(retained["statistics"]) != set(STATISTIC_NAMES)):
            _fail("eight-universe baseline custom-statistic lineage changed")
        parsed = parse_order(baseline, retained["statistics"])
        saved = adapter._read_artifact(result_path)
        if saved != {
            **expected, **parsed,
            "manifest_sha256": adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256,
            "projection_sha256": adapter._candidate(baseline)["projection_sha256"],
        }:
            _fail("eight-universe saved baseline differs from retained statistics")
        if parsed["run_valid"] is True:
            return True
    _fail("valid R268 AR-independent market-cap baseline result is unavailable")
