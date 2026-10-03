"""Offline three-name study identity, bounded transport, and comparison gates."""

import copy
import hashlib
import json

import pytest

from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_three_name_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from scripts import run_arv2_qcom_exclusion_three_name as script
from tests.analyst_revisions_v2.test_qc_matched_study_submission import order_statistics
from tests.analyst_revisions_v2.test_qc_qcom_exclusion_coverage10_study import (
    result_fixture as coverage10_results,
)
from tests.analyst_revisions_v2.test_qc_relaxed_submission import Fake, ORG, canonical


def manifest():
    return json.loads(adapter.QCOM_EXCLUSION_THREE_NAME_MANIFEST_PATH.read_bytes())


@pytest.fixture(scope="module")
def exact_projections():
    inputs = script.package()
    return {candidate: script.projected(candidate, inputs)
            for candidate in study.CANDIDATES}


def statistics_fixture(row):
    statistics = order_statistics(row)
    report = json.loads(statistics[study.predecessor.DIAGNOSTIC_NAME])
    report["arm"] = "ar_off" if row["arm"] == "ar_off" else "ar_on100"
    aggregate = json.loads(statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"])
    aggregate.update(
        analyst_revision_economic_usage=("none_authenticated_score_clock_only"
            if row["arm"] == "ar_off" else "entry_count_and_weight"),
        stock_exclusion_policy_id=study.predecessor.EXCLUSION_RULE,
        excluded_logical_security_sha256=study.predecessor.EXCLUDED_STOCK_SECURITY_ID_SHA256,
        coverage_policy_id=study.COVERAGE_POLICY_ID)
    raw = canonical(aggregate).decode("ascii")
    statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"] = raw
    statistics[study.predecessor.DIAGNOSTIC_NAME] = canonical(report).decode("ascii")
    meta = json.loads(statistics["ARV2_SIX_GATE_ORDER_META"])
    meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    meta["matched_diagnostics_sha256"] = adapter._sha(report)
    statistics["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
    return statistics


def result_fixture():
    original = coverage10_results()["R238"]
    results = {}
    for index, row in enumerate(manifest()["candidates"]):
        candidate, arm = row["candidate_id"], row["arm"]
        result = copy.deepcopy(original)
        value = ("0.20", "0.24", "0.27", "0.31")[index]
        result.update(candidate_id=candidate, attempt=1, status="Completed.",
            manifest_sha256=adapter.FROZEN_QCOM_EXCLUSION_THREE_NAME_MANIFEST_SHA256,
            projection_sha256=row["projection_sha256"])
        aggregate = result["aggregates"]
        aggregate.update(comparison_arm=arm,
            analyst_revision_economic_usage=("none_authenticated_score_clock_only"
                if arm == "ar_off" else "entry_count_and_weight"),
            maximum_stock_weight_change_fraction=row["tilt_fraction"],
            matched_baseline_profile_sha256=row["matched_baseline_profile_sha256"],
            stock_exclusion_policy_id=study.predecessor.EXCLUSION_RULE,
            excluded_logical_security_sha256=study.predecessor.EXCLUDED_STOCK_SECURITY_ID_SHA256,
            coverage_policy_id=study.COVERAGE_POLICY_ID)
        aggregate["account"]["cumulative_return"] = value
        report = result["diagnostics"]
        report["arm"] = "ar_off" if arm == "ar_off" else "ar_on100"
        report["overall_cumulative_return"] = value
        report["annual_account_rows"][-1][5] = value
        results[candidate] = result
    return results


def test_manifest_pins_three_name_policy_and_separate_four_arm_identity():
    raw = adapter.QCOM_EXCLUSION_THREE_NAME_MANIFEST_PATH.read_bytes()
    value = adapter._qcom_exclusion_three_name_manifest()
    assert hashlib.sha256(raw).hexdigest() == adapter.FROZEN_QCOM_EXCLUSION_THREE_NAME_MANIFEST_SHA256
    assert raw == (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("ascii")
    assert study.validate_manifest(value) is value
    assert list(study.CANDIDATES) == ["R242", "R243", "R244", "R245"]
    assert set(study.CANDIDATES).isdisjoint(study.coverage10.CANDIDATES)
    protocol = value["protocol"]
    assert protocol["cost_bps_per_side"] == "10"
    assert protocol["target_gross_exposure"] == "0.98"
    assert protocol["admission_leverage"] == "2"
    assert protocol["minimum_verified_name_count"] == 3
    assert protocol["minimum_non_xle_positive_ar_score_count"] == 3
    assert all(protocol[key] == "0.10" for key in (
        "minimum_name_mapping_coverage", "minimum_market_cap_weight_coverage",
        "minimum_total_reported_weight"))
    assert protocol["confirmation"] is False
    assert protocol["sensitivity_only"] is True


@pytest.mark.parametrize("defect", ("reordered", "old_candidate", "wrong_verified_names",
    "wrong_positive_scores", "wrong_coverage", "wrong_policy", "wrong_baseline",
    "wrong_projection", "wrong_profile", "wrong_fee", "wrong_slippage", "wrong_role",
    "wrong_schema", "duplicate_source", "extra_field", "false_confirmation"))
def test_manifest_refuses_changed_identity_or_economics(defect):
    value = manifest()
    row = value["candidates"][0]
    if defect == "reordered": value["candidates"].reverse()
    elif defect == "old_candidate": row["candidate_id"] = "R238"
    elif defect == "wrong_verified_names": value["protocol"]["minimum_verified_name_count"] = 5
    elif defect == "wrong_positive_scores": value["protocol"]["minimum_non_xle_positive_ar_score_count"] = 2
    elif defect == "wrong_coverage": value["protocol"]["minimum_total_reported_weight"] = "0.25"
    elif defect == "wrong_policy": row["coverage_policy_id"] = "old"
    elif defect == "wrong_baseline": row["matched_baseline_profile_sha256"] = "f" * 64
    elif defect == "wrong_projection": row["projection_sha256"] = "f" * 64
    elif defect == "wrong_profile": row["profile_sha256"] = "f" * 64
    elif defect == "wrong_fee": value["protocol"]["cost_bps_per_side"] = "5"
    elif defect == "wrong_slippage": row["slippage_bps"] = 5
    elif defect == "wrong_role": row["role"] = "matched_qcom_excluded_ar_off_s0"
    elif defect == "wrong_schema": row["meta_schema"] = "old"
    elif defect == "duplicate_source": value["candidates"][1]["source_files_sha256"] = row["source_files_sha256"]
    elif defect == "extra_field": row["extra"] = True
    elif defect == "false_confirmation": value["protocol"]["confirmation"] = 0
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study.validate_manifest(value)


def test_exact_projection_and_offline_preview(exact_projections, tmp_path):
    value = manifest()
    for row in value["candidates"]:
        projected, profile = exact_projections[row["candidate_id"]]
        files = [[item.project_path, item.content_sha256, item.byte_count]
                 for item in projected.source_files]
        assert projected.projection_sha256 == row["projection_sha256"]
        assert projected.profile_sha256 == profile["profile_sha256"] == row["profile_sha256"]
        assert projected.profile_id == row["profile_id"]
        assert projected.role == row["role"]
        assert profile["coverage_policy_id"] == row["coverage_policy_id"]
        assert profile["matched_baseline_profile_sha256"] == row["matched_baseline_profile_sha256"]
        assert hashlib.sha256(adapter.common._canonical(files)).hexdigest() == row["source_files_sha256"]
        plan = adapter.build_plan(row["candidate_id"], ORG, tmp_path / "controls", family=study.FAMILY)
        assert adapter.preview(plan, projected)["projection_sha256"] == row["projection_sha256"]
    assert script.freeze() == value
    assert script.CONTROL != script.CONTEXT_CONTROL


@pytest.mark.parametrize("candidate", tuple(study.CANDIDATES))
def test_fake_cloud_launch_and_one_bounded_read(candidate, exact_projections, tmp_path,
                                                monkeypatch):
    monkeypatch.setattr(adapter, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda api: None)
    fake = Fake()
    monkeypatch.setattr(adapter.common, "_post", fake.post)
    plan = adapter.build_plan(candidate, ORG, tmp_path / "controls", family=study.FAMILY)
    receipt = adapter.launch(plan, exact_projections[candidate][0], fake)
    fake.status = "Completed."
    assert adapter.poll_status(plan, receipt, fake) == "Completed."
    row = next(item for item in manifest()["candidates"] if item["candidate_id"] == candidate)
    fake.statistics = {**statistics_fixture(row), "Net Profit": "NOT RETAINED"}
    parsed = adapter.read_result_once(plan, receipt, fake)
    assert parsed["run_valid"] is True
    assert parsed["aggregates"]["coverage_policy_id"] == study.COVERAGE_POLICY_ID
    assert parsed["aggregates"]["comparison_arm"] == row["arm"]
    assert "NOT RETAINED" not in str(parsed)
    assert sum(endpoint == "backtests/read" for endpoint, _ in fake.calls) == 1
    with pytest.raises(adapter.common.SixUniverseSettlementSubmissionError):
        adapter.read_result_once(plan, receipt, fake)


def test_result_parser_refuses_changed_three_name_policy(tmp_path):
    row = manifest()["candidates"][0]
    plan = adapter.build_plan("R242", ORG, tmp_path / "controls", family=study.FAMILY)
    statistics = statistics_fixture(row)
    aggregate = json.loads(statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"])
    aggregate["coverage_policy_id"] = study.coverage10.COVERAGE_POLICY_ID
    raw = canonical(aggregate).decode("ascii")
    statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"] = raw
    meta = json.loads(statistics["ARV2_SIX_GATE_ORDER_META"])
    meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    statistics["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="policy identity"):
        study.parse_order(plan, statistics)


def test_comparison_authenticates_four_arms_and_separate_10pct_context():
    results = result_fixture()
    output = study.compare_results(results)
    assert output["comparisons"][0]["AR_on_minus_three_name_AR_off_percentage_points"] == "4.00"
    context = coverage10_results()
    output = study.compare_results(results, context)
    assert output["context_10pct"]["compatible"] is True
    changed_context = copy.deepcopy(context)
    for result in changed_context.values():
        result["diagnostics"]["membership_cap_path_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="membership|source"):
        study.compare_results(results, changed_context)
    assert output["context_10pct"]["membership_digest_equality_required"] is True
    context["R240"]["aggregates"]["pit_callback_source_row_count"] += 1
    with pytest.raises(ValueError, match="source panel|source census"):
        study.compare_results(results, context)
    results["R244"]["manifest_sha256"] = adapter.FROZEN_QCOM_EXCLUSION_COVERAGE10_MANIFEST_SHA256
    with pytest.raises(ValueError, match="authenticated"):
        study.compare_results(results)


@pytest.mark.parametrize("key", (
    "pit_callback_source_row_count",
    "fundamental_snapshot_unavailable_decision_count",
    "constituent_collection_unavailable_decision_count",
    "constituent_collection_unavailable_universe_counts",
))
def test_four_arm_comparison_refuses_each_non_ar_source_census_mismatch(key):
    assert study._COMMON_SOURCE_CENSUS == (
        "pit_callback_source_row_count",
        "fundamental_snapshot_unavailable_decision_count",
        "constituent_collection_unavailable_decision_count",
        "constituent_collection_unavailable_universe_counts",
    )
    results = result_fixture()
    assert study.compare_results(copy.deepcopy(results))["comparison_valid"] is True
    aggregate = results["R245"]["aggregates"]
    value = aggregate[key]
    if type(value) is dict:
        value[sorted(value)[0]] += 1
    else:
        aggregate[key] = value + 1
    with pytest.raises(ValueError, match="three-name non-AR source census differs"):
        study.compare_results(results)


@pytest.mark.parametrize("key", (
    "pit_callback_source_row_count",
    "fundamental_snapshot_unavailable_decision_count",
    "constituent_collection_unavailable_decision_count",
    "constituent_collection_unavailable_universe_counts",
))
def test_10pct_context_refuses_each_non_ar_source_census_mismatch(key):
    results, context = result_fixture(), coverage10_results()
    assert study.compare_results(copy.deepcopy(results), copy.deepcopy(context))[
        "context_10pct"]["compatible"] is True
    for result in results.values():
        aggregate = result["aggregates"]
        value = aggregate[key]
        if type(value) is dict:
            value[sorted(value)[0]] += 1
        else:
            aggregate[key] = value + 1
    assert study.compare_results(copy.deepcopy(results))["comparison_valid"] is True
    with pytest.raises(ValueError, match="source panel, or census"):
        study.compare_results(results, context)


def test_fourth_attempt_refused_without_qc(tmp_path):
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="bound"):
        adapter.build_plan("R242", ORG, tmp_path / "controls", 4, family=study.FAMILY)
