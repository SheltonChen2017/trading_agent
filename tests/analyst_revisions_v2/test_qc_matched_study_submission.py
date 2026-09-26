"""Matched-study host guards and fake-cloud integration, never research results."""

import copy
import dataclasses
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_matched_diagnostics as diagnostics
from research.analyst_revisions_v2_qc import six_universe_matched_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from tests.analyst_revisions_v2.test_qc_relaxed_submission import (
    Fake, ORG, Projection, canonical, order_fixture,
)
from tests.analyst_revisions_v2.test_qc_six_universe_tilt_ladder_floor_projection import (
    package as exact_delta_package,
)


def manifest_fixture():
    projection = Projection()
    projection.package_sha256 = study.delta.EXPECTED_DELTA_PACKAGE_SHA256
    projection.activation_manifest_sha256 = study.HISTORICAL_ACTIVATION_SHA256
    projection.role = "matched-test-role"
    projection.projection_sha256 = adapter._sha(projection.semantic())
    rows = []
    for candidate, (arm, slippage) in study.CANDIDATES.items():
        rows.append({"candidate_id": candidate, "project_name": "ARV2 MATCHED " + candidate,
            "backtest_name": "ARV2 " + candidate + " matched",
            "kind": "order", "role": projection.role, "arm": arm,
            "slippage_bps": slippage, "tilt_fraction": "1.00" if arm == "ar_on100" else "0.00",
            "projection_schema": projection.schema, "projection_sha256": projection.projection_sha256,
            "profile_id": projection.profile_id, "profile_sha256": projection.profile_sha256,
            "source_file_count": 1, "total_source_bytes": projection.total_source_byte_count,
            "source_files_sha256": adapter._sha(projection.semantic()["source_files"]),
            "statistic_names": ["ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES", study.DIAGNOSTIC_NAME],
            "matched_baseline_profile_sha256": "b" * 64,
            "meta_schema": "test-order-meta", "summary_schema": "relaxed-summary"})
    return {"schema": "arv2-six-matched-historical-study-v1",
        "protocol": copy.deepcopy(study.PROTOCOL), "package_sha256": projection.package_sha256,
        "activation_manifest_sha256": projection.activation_manifest_sha256,
        "candidates": rows}, projection


def diagnostic_fixture(arm="ar_off", slippage=0, total_return="0"):
    years = [str(year) for year in range(2021, 2026)]
    counts = [252, 251, 250, 252, 250]
    ends = ["2021-12-31", "2022-12-30", "2023-12-29", "2024-12-31", "2025-12-31"]
    return {"schema": diagnostics.SCHEMA, "arm": arm, "slippage_bps_per_side": slippage,
        "overall_cumulative_return": total_return,
        "annual_account_fields": list(diagnostics.ANNUAL_FIELDS),
        "annual_account_rows": [[year, counts[index], index > 0,
            "2021-01-04" if index == 0 else ends[index - 1], ends[index],
            total_return if index == 4 else "0", "0", "0", None]
            for index, year in enumerate(years)],
        "membership_cap_path_sha256": "a" * 64, "source_snapshot_count": 261,
        "diagnostic_history_call_count": 1, "etf_daily_panel_sha256": "b" * 64,
        "six_etf_panel_row_count": study.PROTOCOL["observation_count"] * 6,
        "year_universe_fields": list(diagnostics.UNIVERSE_FIELDS),
        "year_universe_rows": [[year, universe, 53 if year == "2024" else 52,
            0, 0, 0, "0"] for year in years for universe in diagnostics._base._gate.UNIVERSE_IDS],
        "universe_realized_profit_attributed": False, "all_stock_price_equality_proved": False,
        "minute_execution_price_equality_proved": False,
        "daily_price_normalization": "RAW", "fill_forward": False}


def results_fixture():
    results = {}
    for index, (candidate, (arm, slippage)) in enumerate(study.CANDIDATES.items()):
        value = ("0.20", "0.25", "0.22", "0.18", "0.22", "0.20")[index]
        aggregate, _, _ = order_fixture()
        aggregate.update(target_gross_exposure="0.98", admission_leverage="2",
            slippage_bps_per_side=slippage,
            matched_baseline_target_path_sha256=str(index) * 64)
        aggregate["account"].update(observation_count=study.PROTOCOL["observation_count"],
            first_observation_session="2021-01-04", last_observation_session="2025-12-31",
            starting_equity="100000", ending_equity=str(Decimal("100000") * (1 + Decimal(value))),
            cumulative_return=value)
        aggregate["execution"].update(decision_count=261, submitted_rebalance_count=261,
            completed_rebalance_count=261, submitted_order_count=261, filled_order_count_sum=261)
        results[candidate] = {"run_valid": True, "aggregates": aggregate,
            "diagnostics": diagnostic_fixture(arm, slippage, value)}
    return results


def order_statistics(row):
    aggregate, _, meta = order_fixture()
    aggregate.update(schema=row["summary_schema"], role=row["role"],
        profile_id=row["profile_id"], profile_sha256=row["profile_sha256"],
        maximum_stock_weight_change_fraction=row["tilt_fraction"],
        matched_baseline_profile_sha256=row["matched_baseline_profile_sha256"],
        comparison_arm=row["arm"], analyst_revision_economic_usage=(
            "entry_count_and_weight" if row["arm"] == "ar_on100"
            else "none_authenticated_score_clock_only"))
    aggregate["account"].update(first_observation_session="2021-01-04",
        last_observation_session="2025-12-31", observation_count=1255)
    aggregate["execution"].update(decision_count=261, submitted_rebalance_count=261,
        completed_rebalance_count=261, submitted_order_count=261, filled_order_count_sum=261)
    aggregate["fallback_counts"] = {"PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK": 1566}
    for sleeve in aggregate["sleeve_diagnostics"]["rows"]:
        sleeve[2] = 261
        sleeve[10] = {"KNOWN_MARKET_CAP_NAME_COUNT_BELOW_MINIMUM": 261}
        sleeve[11] = {"PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK": 261}
    report = diagnostic_fixture(row["arm"], row["slippage_bps"], aggregate["account"]["cumulative_return"])
    raw = canonical(aggregate).decode("ascii")
    meta.update(schema=row["meta_schema"], role=row["role"], profile_id=row["profile_id"],
        profile_sha256=row["profile_sha256"], package_sha256=study.delta.EXPECTED_DELTA_PACKAGE_SHA256,
        activation_manifest_sha256=study.HISTORICAL_ACTIVATION_SHA256,
        aggregate_schema=row["summary_schema"], aggregate_sha256=hashlib.sha256(raw.encode("ascii")).hexdigest(),
        matched_diagnostics_sha256=adapter._sha(report),
        result_transport="three_bounded_custom_summary_statistics")
    return {"ARV2_SIX_GATE_ORDER_META": canonical(meta).decode("ascii"),
        "ARV2_SIX_GATE_ORDER_AGGREGATES": raw, study.DIAGNOSTIC_NAME: canonical(report).decode("ascii")}


def test_protocol_has_exact_three_arms_and_two_prospective_cost_conditions():
    assert study.CANDIDATES == {"R225": ("ar_off", 0), "R226": ("ar_on100", 0),
        "R227": ("six_etf_basket", 0), "R228": ("ar_off", 5),
        "R229": ("ar_on100", 5), "R230": ("six_etf_basket", 5)}
    manifest, _ = manifest_fixture()
    assert study.validate_manifest(manifest) is manifest
    assert manifest["protocol"]["confirmation"] is False
    assert manifest["protocol"]["capacity_search"] is False


def test_real_source_freeze_reproduces_committed_manifest_and_all_previews(exact_delta_package, tmp_path, monkeypatch):
    from scripts import run_arv2_matched_study as script
    monkeypatch.setattr(script, "package", lambda: exact_delta_package)
    frozen = adapter._matched_study_manifest()
    assert script.freeze() == frozen
    assert "input_control_directory" not in frozen
    for candidate in study.CANDIDATES:
        plan = adapter.build_plan(candidate, ORG, tmp_path / "control", family="matched_study")
        projected, _ = script.projected(candidate)
        preview = adapter.preview(plan, projected)
        assert preview["candidate_id"] == candidate
        assert preview["projection_sha256"] == projected.projection_sha256
        assert preview["manifest_sha256"] == adapter.FROZEN_MATCHED_STUDY_MANIFEST_SHA256


@pytest.mark.parametrize("defect", ["missing", "duplicate", "reordered", "wrong_arm",
    "boolean_slippage", "wrong_slippage", "tilt", "missing_statistic", "extra_statistic",
    "wrong_package", "wrong_activation", "wrong_decisions", "boolean_confirmation"])
def test_manifest_refuses_semantic_census_and_protocol_changes(defect):
    value, _ = manifest_fixture()
    rows = value["candidates"]
    if defect == "missing":
        rows.pop()
    elif defect == "duplicate":
        rows[-1]["candidate_id"] = rows[0]["candidate_id"]
    elif defect == "reordered":
        rows.reverse()
    elif defect == "wrong_arm":
        rows[0]["arm"] = "ar_on100"
    elif defect == "boolean_slippage":
        rows[0]["slippage_bps"] = False
    elif defect == "wrong_slippage":
        rows[0]["slippage_bps"] = 5
    elif defect == "tilt":
        rows[0]["tilt_fraction"] = "0.40"
    elif defect == "missing_statistic":
        rows[0]["statistic_names"].pop()
    elif defect == "extra_statistic":
        rows[0]["statistic_names"].append("Net Profit")
    elif defect == "wrong_package":
        value["package_sha256"] = "f" * 64
    elif defect == "wrong_activation":
        value["activation_manifest_sha256"] = "f" * 64
    elif defect == "wrong_decisions":
        value["protocol"]["decision_count"] = 260
    elif defect == "boolean_confirmation":
        value["protocol"]["confirmation"] = 0
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study.validate_manifest(value)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    manifest, projection = manifest_fixture()
    path = tmp_path / "matched.json"
    path.write_bytes(canonical(manifest))
    monkeypatch.setattr(adapter, "MATCHED_STUDY_MANIFEST_PATH", path)
    monkeypatch.setattr(adapter, "FROZEN_MATCHED_STUDY_MANIFEST_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(adapter, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda api: None)
    fake = Fake()
    monkeypatch.setattr(adapter.common, "_post", fake.post)
    plan = adapter.build_plan("R225", ORG, tmp_path / "control", family="matched_study")
    return plan, projection, fake, manifest


def test_new_family_dispatch_keeps_claim_one_use_and_owner_research_waiver(frozen):
    plan, projection, fake, _ = frozen
    identity = adapter.preview(plan, projection)
    assert identity["authority"] == "owner_exploratory_signature_waiver"
    receipt = adapter.launch(plan, projection, fake)
    assert receipt["project_id"] == 123
    assert adapter._path(plan, "claim").exists()
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="consumed"):
        adapter.launch(plan, projection, fake)
    assert sum(endpoint == "backtests/create" for endpoint, _ in fake.calls) == 1


@pytest.mark.parametrize("attempt", [False, True, 0, 4, "1", 1.0])
def test_matched_family_cannot_change_three_attempt_bound(frozen, attempt):
    plan, _, fake, _ = frozen
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="bound"):
        adapter._candidate(dataclasses.replace(plan, attempt=attempt))
    assert fake.calls == []


def test_manifest_hash_refuses_shape_identical_unpinned_name_before_qc(frozen):
    plan, projection, fake, manifest = frozen
    manifest["candidates"][0]["project_name"] += " EDITED"
    adapter.MATCHED_STUDY_MANIFEST_PATH.write_bytes(canonical(manifest))
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="frozen manifest"):
        adapter.launch(plan, projection, fake)
    assert fake.calls == []


def test_compile_failure_consumes_slot_and_retries_same_project(frozen):
    plan, projection, fake, _ = frozen
    fake.compile_state = "BuildError"
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="compile failed"):
        adapter.launch(plan, projection, fake)
    fake.compile_state = "BuildSuccess"
    adapter.launch(dataclasses.replace(plan, attempt=2), projection, fake)
    assert sum(endpoint == "projects/create" for endpoint, _ in fake.calls) == 1


@pytest.mark.parametrize("candidate_id", list(study.CANDIDATES))
def test_completed_fake_cloud_real_three_statistic_parser_one_read(frozen, candidate_id):
    base_plan, projection, fake, manifest = frozen
    plan = dataclasses.replace(base_plan, candidate_id=candidate_id)
    row = next(row for row in manifest["candidates"] if row["candidate_id"] == candidate_id)
    receipt = adapter.launch(plan, projection, fake)
    fake.status = "Completed."
    assert adapter.poll_status(plan, receipt, fake) == "Completed."
    fake.statistics = {**order_statistics(row), "Net Profit": "DO NOT RETAIN"}
    result = adapter.read_result_once(plan, receipt, fake)
    assert result["run_valid"] is True
    assert result["diagnostics"]["arm"] == row["arm"]
    assert result["aggregates"]["account"]["observation_count"] == 1255
    assert "DO NOT RETAIN" not in str(result)
    assert "NOT RETAINED" not in str(result)
    with pytest.raises(adapter.common.SixUniverseSettlementSubmissionError):
        adapter.read_result_once(plan, receipt, fake)
    assert sum(endpoint == "backtests/read" for endpoint, _ in fake.calls) == 1


@pytest.mark.parametrize("defect", ["economic_mode", "comparison_arm", "statistic_inventory",
    "diagnostic_digest", "account_return"])
def test_real_parser_isolates_matched_mode_inventory_and_rebound_digest(frozen, defect):
    plan, _, _, manifest = frozen
    row = manifest["candidates"][0]
    statistics = order_statistics(row)
    aggregate = json.loads(statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"])
    meta = json.loads(statistics["ARV2_SIX_GATE_ORDER_META"])
    if defect == "economic_mode":
        aggregate["analyst_revision_economic_usage"] = "entry_count_and_weight"
    elif defect == "comparison_arm":
        aggregate["comparison_arm"] = "ar_on100"
    elif defect == "statistic_inventory":
        statistics["Net Profit"] = "0"
    elif defect == "diagnostic_digest":
        meta["matched_diagnostics_sha256"] = "c" * 64
    elif defect == "account_return":
        aggregate["account"].update(cumulative_return="0.2", ending_equity="1200000")
    raw = canonical(aggregate).decode("ascii")
    statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"] = raw
    meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    statistics["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        adapter._parse_order(plan, statistics)


def test_three_statistic_parser_validates_diagnostic_digest_and_arm(monkeypatch):
    manifest, _ = manifest_fixture()
    row = manifest["candidates"][0]
    plan = adapter.RelaxedQcPlan("R225", ORG, Path("/unused"), family="matched_study")
    report = diagnostic_fixture()
    parsed = {"run_valid": True, "meta": {"matched_diagnostics_sha256": adapter._sha(report)},
        "aggregates": {"account": {"cumulative_return": "0"}, "comparison_arm": "ar_off",
            "analyst_revision_economic_usage": "none_authenticated_score_clock_only"}}
    monkeypatch.setattr(adapter, "_candidate", lambda value: row)
    def common(value, statistics, **kwargs):
        assert kwargs["decision_count"] == 261
        assert kwargs["expected_geometry"] is None
        assert kwargs["extra_meta_fields"] == frozenset({"matched_diagnostics_sha256"})
        return copy.deepcopy(parsed)
    monkeypatch.setattr(adapter, "_parse_order_common", common)
    statistics = {name: canonical(report if name == study.DIAGNOSTIC_NAME else {}).decode("ascii")
        for name in row["statistic_names"]}
    assert adapter._parse_order(plan, statistics)["diagnostics"] == report
    parsed["meta"]["matched_diagnostics_sha256"] = "c" * 64
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="digest"):
        adapter._parse_order(plan, statistics)
    parsed["meta"]["matched_diagnostics_sha256"] = adapter._sha(report)
    report["arm"] = "ar_on100"
    parsed["meta"]["matched_diagnostics_sha256"] = adapter._sha(report)
    statistics[study.DIAGNOSTIC_NAME] = canonical(report).decode("ascii")
    with pytest.raises(diagnostics._base.AcceptedRiskSixUniverseOrderQcRuntimeError):
        adapter._parse_order(plan, statistics)


def test_comparison_accepts_deliberately_different_target_paths_and_computes_spreads():
    results = results_fixture()
    answer = study.compare_results(results)
    assert answer["comparison_valid"] is True
    assert answer["total_AR_ablation"] is True
    assert answer["formal_alpha"] is False
    assert Decimal(answer["comparisons"][0]["AR_on_minus_fully_off_percentage_points"]) == Decimal(5)
    assert Decimal(answer["comparisons"][1]["AR_on_minus_fully_off_percentage_points"]) == Decimal(4)
    assert "not_full_stock_minute_fill_tape" in answer["reference_data_scope"]


@pytest.mark.parametrize("defect", ["missing_arm", "invalid", "boolean_valid", "observations",
    "boolean_observations", "first_session", "last_session", "decisions", "capital",
    "gross", "admission", "membership_digest", "etf_digest", "malformed_common_digest",
    "wrong_diagnostic_arm", "wrong_slippage", "nonfinite_return", "return_mismatch",
    "zero_capital", "nonfinite_capital", "boolean_decisions", "non_ar_source_census"])
def test_comparison_refuses_nonmatched_or_invalid_evidence(defect):
    results = results_fixture()
    item = results["R229"]
    account = item["aggregates"]["account"]
    if defect == "missing_arm":
        results.pop("R230")
    elif defect == "invalid":
        item["run_valid"] = False
    elif defect == "boolean_valid":
        item["run_valid"] = 1
    elif defect == "observations":
        account["observation_count"] -= 1
    elif defect == "boolean_observations":
        account["observation_count"] = True
    elif defect in {"first_session", "last_session"}:
        account[defect.replace("_session", "_observation_session")] = "2025-08-01"
    elif defect == "decisions":
        item["aggregates"]["execution"]["decision_count"] = 260
    elif defect == "capital":
        account["starting_equity"] = "100001"
    elif defect == "gross":
        item["aggregates"]["target_gross_exposure"] = "1.0"
    elif defect == "admission":
        item["aggregates"]["admission_leverage"] = "3"
    elif defect in {"membership_digest", "etf_digest"}:
        item["diagnostics"]["membership_cap_path_sha256" if defect.startswith("membership") else "etf_daily_panel_sha256"] = "c" * 64
    elif defect == "malformed_common_digest":
        for result in results.values():
            result["diagnostics"]["etf_daily_panel_sha256"] = "not-a-digest"
    elif defect == "wrong_diagnostic_arm":
        item["diagnostics"]["arm"] = "ar_off"
    elif defect == "wrong_slippage":
        item["diagnostics"]["slippage_bps_per_side"] = 0
    elif defect == "nonfinite_return":
        account["cumulative_return"] = "NaN"
    elif defect == "return_mismatch":
        account["cumulative_return"] = "0.99"
    elif defect == "zero_capital":
        for result in results.values():
            result["aggregates"]["account"]["starting_equity"] = "0"
    elif defect == "nonfinite_capital":
        for result in results.values():
            result["aggregates"]["account"]["starting_equity"] = "Infinity"
    elif defect == "boolean_decisions":
        item["aggregates"]["execution"]["decision_count"] = True
    elif defect == "non_ar_source_census":
        item["aggregates"]["pit_callback_source_row_count"] += 1
    with pytest.raises((ValueError, diagnostics._base.AcceptedRiskSixUniverseOrderQcRuntimeError)):
        study.compare_results(results)
