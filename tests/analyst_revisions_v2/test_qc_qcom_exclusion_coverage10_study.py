"""Offline 10% QCOM-excluded manifest, source, transport, and comparison gates."""

import ast
import copy
import hashlib
import json

import pytest

from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_coverage10_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from scripts import run_arv2_qcom_exclusion_coverage10 as script
from tests.analyst_revisions_v2.test_qc_matched_study_submission import order_statistics
from tests.analyst_revisions_v2.test_qc_qcom_exclusion_study import result_fixture as predecessor_results
from tests.analyst_revisions_v2.test_qc_relaxed_submission import Fake, ORG, canonical


def manifest():
    return json.loads(adapter.QCOM_EXCLUSION_COVERAGE10_MANIFEST_PATH.read_bytes())


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
    original = predecessor_results()["R231"]
    rows = manifest()["candidates"]
    results = {}
    for index, row in enumerate(rows):
        candidate, arm = row["candidate_id"], row["arm"]
        result = copy.deepcopy(original)
        value = ("0.20", "0.24", "0.27", "0.31")[index]
        result.update(candidate_id=candidate, attempt=1, status="Completed.",
            manifest_sha256=adapter.FROZEN_QCOM_EXCLUSION_COVERAGE10_MANIFEST_SHA256,
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


def context_fixture():
    row231 = adapter._qcom_exclusion_manifest()["candidates"][0]
    tilt_rows = adapter._qcom_exclusion_tilt_manifest()["candidates"]
    rows = [row231, *tilt_rows]
    original = predecessor_results()["R231"]
    results = {}
    for index, row in enumerate(rows):
        candidate = row["candidate_id"]
        arm = "ar_off" if index == 0 else f"ar_on{(80, 120, 200)[index - 1]}"
        value = ("0.21", "0.23", "0.25", "0.28")[index]
        result = copy.deepcopy(original)
        result.update(candidate_id=candidate, attempt=1, status="Completed.",
            manifest_sha256=(adapter.FROZEN_QCOM_EXCLUSION_MANIFEST_SHA256 if index == 0
                else adapter.FROZEN_QCOM_EXCLUSION_TILT_MANIFEST_SHA256),
            projection_sha256=row["projection_sha256"])
        aggregate = result["aggregates"]
        aggregate.update(comparison_arm=arm,
            analyst_revision_economic_usage=("none_authenticated_score_clock_only"
                if index == 0 else "entry_count_and_weight"),
            maximum_stock_weight_change_fraction=row["tilt_fraction"],
            matched_baseline_profile_sha256=row["matched_baseline_profile_sha256"])
        aggregate["account"]["cumulative_return"] = value
        report = result["diagnostics"]
        report["arm"] = "ar_off" if index == 0 else "ar_on100"
        report["overall_cumulative_return"] = value
        report["annual_account_rows"][-1][5] = value
        results[candidate] = result
    return results


def test_manifest_is_separate_byte_pinned_four_arm_protocol():
    raw = adapter.QCOM_EXCLUSION_COVERAGE10_MANIFEST_PATH.read_bytes()
    value = adapter._qcom_exclusion_coverage10_manifest()
    assert hashlib.sha256(raw).hexdigest() == adapter.FROZEN_QCOM_EXCLUSION_COVERAGE10_MANIFEST_SHA256
    assert raw == (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("ascii")
    assert study.validate_manifest(value) is value
    assert list(study.CANDIDATES) == ["R238", "R239", "R240", "R241"]
    assert set(study.CANDIDATES).isdisjoint(study.predecessor.CANDIDATES)
    assert value["protocol"]["cost_bps_per_side"] == "10"
    assert value["protocol"]["target_gross_exposure"] == "0.98"
    assert value["protocol"]["admission_leverage"] == "2"
    assert value["protocol"]["minimum_verified_name_count"] == 5
    assert all(value["protocol"][key] == "0.10" for key in (
        "minimum_name_mapping_coverage", "minimum_market_cap_weight_coverage",
        "minimum_total_reported_weight"))
    assert value["protocol"]["confirmation"] is False


@pytest.mark.parametrize("defect", ("reordered", "old_candidate", "wrong_floor",
    "wrong_verified_names", "wrong_coverage_id", "wrong_baseline", "wrong_projection",
    "wrong_profile", "wrong_fee", "wrong_slippage", "wrong_role", "wrong_schema",
    "duplicate_source", "extra_field", "false_confirmation"))
def test_manifest_refuses_changed_identity_or_economics(defect):
    value = manifest()
    row = value["candidates"][0]
    if defect == "reordered": value["candidates"].reverse()
    elif defect == "old_candidate": row["candidate_id"] = "R231"
    elif defect == "wrong_floor": value["protocol"]["minimum_name_mapping_coverage"] = "0.25"
    elif defect == "wrong_verified_names": value["protocol"]["minimum_verified_name_count"] = 4
    elif defect == "wrong_coverage_id": row["coverage_policy_id"] = "old"
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


def test_real_projection_matches_manifest_and_previews_without_cloud(exact_projections, tmp_path):
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
    assert script.CONTROL != script.R231_CONTROL != script.TILT_CONTROL


def test_generated_meta_emitter_uses_the_manifest_schema(exact_projections):
    """Pin the actual shared emitter, which caught an older tilt-family gap."""
    for row in manifest()["candidates"]:
        projected = exact_projections[row["candidate_id"]][0]
        sources = {item.project_path: item.source_bytes.decode("ascii")
                   for item in projected.source_files}
        base = ast.parse(sources["accepted_risk_six_universe_order_qc_runtime.py"])
        assignments = [node for node in base.body if isinstance(node, ast.Assign)
                       and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                       and node.targets[0].id == "META_SCHEMA"]
        assert len(assignments) == 1
        assert ast.literal_eval(assignments[0].value) == row["meta_schema"]
        endings = [node for node in ast.walk(base) if isinstance(node, ast.FunctionDef)
                   and node.name == "on_end_of_algorithm"]
        assert len(endings) == 1
        emitted = [node.value for node in ast.walk(endings[0])
                   if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                       and target.id == "meta" for target in node.targets)]
        assert len(emitted) == 1 and isinstance(emitted[0], ast.Dict)
        schema = [value for key, value in zip(emitted[0].keys, emitted[0].values)
                  if isinstance(key, ast.Constant) and key.value == "schema"]
        assert len(schema) == 1 and isinstance(schema[0], ast.Name)
        assert schema[0].id == "META_SCHEMA"


@pytest.mark.parametrize("candidate", tuple(study.CANDIDATES))
def test_fake_cloud_preview_launch_and_single_bounded_read(candidate, exact_projections,
                                                           tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda api: None)
    fake = Fake()
    monkeypatch.setattr(adapter.common, "_post", fake.post)
    control = tmp_path / "controls"
    plan = adapter.build_plan(candidate, ORG, control, family=study.FAMILY)
    projection = exact_projections[candidate][0]
    identity = adapter.preview(plan, projection)
    assert identity["manifest_sha256"] == adapter.FROZEN_QCOM_EXCLUSION_COVERAGE10_MANIFEST_SHA256
    receipt = adapter.launch(plan, projection, fake)
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


def test_parse_refuses_missing_or_changed_coverage_policy(tmp_path):
    row = manifest()["candidates"][0]
    plan = adapter.build_plan("R238", ORG, tmp_path / "controls", family=study.FAMILY)
    statistics = statistics_fixture(row)
    for changed in (None, "old_policy"):
        mutated = copy.deepcopy(statistics)
        aggregate = json.loads(mutated["ARV2_SIX_GATE_ORDER_AGGREGATES"])
        if changed is None: del aggregate["coverage_policy_id"]
        else: aggregate["coverage_policy_id"] = changed
        raw = canonical(aggregate).decode("ascii")
        mutated["ARV2_SIX_GATE_ORDER_AGGREGATES"] = raw
        meta = json.loads(mutated["ARV2_SIX_GATE_ORDER_META"])
        meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
        mutated["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
        with pytest.raises(adapter.RelaxedQcSubmissionError):
            study.parse_order(plan, mutated)


def test_three_failed_compiles_spend_only_three_coverage10_slots(exact_projections,
                                                              tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda api: None)
    fake = Fake()
    fake.compile_state = "BuildError"
    monkeypatch.setattr(adapter.common, "_post", fake.post)
    control = tmp_path / "controls"
    for attempt in (1, 2, 3):
        plan = adapter.build_plan("R238", ORG, control, attempt, family=study.FAMILY)
        with pytest.raises(adapter.RelaxedQcSubmissionError, match="compile failed"):
            adapter.launch(plan, exact_projections["R238"][0], fake)
        assert adapter._path(plan, "claim").exists()
        assert adapter._path(plan, "terminal").exists()
    assert sum(endpoint == "projects/create" for endpoint, _ in fake.calls) == 1
    assert not any(endpoint == "backtests/create" for endpoint, _ in fake.calls)
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="bound"):
        adapter.build_plan("R238", ORG, control, 4, family=study.FAMILY)


def test_four_arm_comparison_and_25pct_context_allow_changed_membership_digest():
    results, context = result_fixture(), context_fixture()
    assert study.compare_results(results)["comparisons"][0][
        "AR_on_minus_coverage10_AR_off_percentage_points"] == "4.00"
    for result in context.values():
        result["diagnostics"]["membership_cap_path_sha256"] = "f" * 64
    compared = study.compare_results(results, context)
    assert compared["context_25pct"]["compatible"] is True
    assert compared["context_25pct"]["membership_digest_equality_required"] is False
    assert compared["context_25pct"]["comparisons"][0][
        "coverage10_minus_coverage25_percentage_points"] == "-1.00"
    context["R236"]["aggregates"]["pit_callback_source_row_count"] += 1
    with pytest.raises(ValueError, match="source census|source panel"):
        study.compare_results(results, context)


def test_comparison_refuses_wrong_identity_and_unsupported_fourth_attempt():
    results = result_fixture()
    results["R240"]["manifest_sha256"] = adapter.FROZEN_QCOM_EXCLUSION_TILT_MANIFEST_SHA256
    with pytest.raises(ValueError, match="authenticated"):
        study.compare_results(results)
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="bound"):
        adapter.build_plan("R238", ORG, script.CONTROL, 4, family=study.FAMILY)
