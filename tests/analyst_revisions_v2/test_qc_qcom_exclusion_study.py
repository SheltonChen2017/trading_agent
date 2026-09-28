"""Offline QCOM-excluded sensitivity contracts; no QC or outcome access."""

import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from tests.analyst_revisions_v2.test_qc_matched_study_submission import (
    diagnostic_fixture, manifest_fixture as original_fixture, order_statistics,
    results_fixture,
)
from tests.analyst_revisions_v2.test_qc_relaxed_submission import Fake, ORG, canonical


def manifest_fixture():
    value, projection = original_fixture()
    extra = []
    for index in range(16):
        raw = f"value_{index:02d} = {index}\n".encode("ascii")
        extra.append(SimpleNamespace(project_path=f"part_{index:02d}.py", source_bytes=raw,
            byte_count=len(raw), content_sha256=hashlib.sha256(raw).hexdigest()))
    projection.source_files = tuple(sorted((*projection.source_files, *extra),
                                         key=lambda item: item.project_path))
    projection.total_source_byte_count = sum(item.byte_count for item in projection.source_files)
    projection.projection_sha256 = adapter._sha(projection.semantic())
    value["schema"] = study.MANIFEST_SCHEMA
    value["protocol"] = copy.deepcopy(study.PROTOCOL)
    value["candidates"] = value["candidates"][:4]
    for row, (candidate, (arm, slippage)) in zip(value["candidates"], study.CANDIDATES.items()):
        row.update(candidate_id=candidate, arm=arm, slippage_bps=slippage,
            project_name="QCOM excluded test " + candidate,
            backtest_name="QCOM excluded result " + candidate,
            tilt_fraction="1.00" if arm == "ar_on100" else "0.00",
            reference_repair_enabled=True,
            excluded_stock_security_id_sha256=study.EXCLUDED_STOCK_SECURITY_ID_SHA256,
            projection_sha256=projection.projection_sha256,
            source_file_count=len(projection.source_files),
            total_source_bytes=projection.total_source_byte_count,
            source_files_sha256=adapter._sha(projection.semantic()["source_files"]))
    return value, projection


def result_fixture():
    prior = results_fixture()
    rows = (prior["R225"], prior["R226"], prior["R228"], prior["R229"])
    results = {}
    for (candidate, (arm, slippage)), old in zip(study.CANDIDATES.items(), rows):
        result = copy.deepcopy(old)
        result["aggregates"].update(comparison_arm=arm,
            analyst_revision_economic_usage=("entry_count_and_weight" if arm == "ar_on100"
                else "none_authenticated_score_clock_only"),
            stock_exclusion_policy_id=study.EXCLUSION_RULE,
            excluded_logical_security_sha256=study.EXCLUDED_STOCK_SECURITY_ID_SHA256)
        # The physical order runtime emits submitted/completed rebalance counts,
        # not the synthetic decision_count supplied by the older test fixture.
        result["aggregates"]["execution"].pop("decision_count", None)
        report = result["diagnostics"]
        report.update(schema=study.diagnostics.REFERENCE_REPAIR_SCHEMA,
            closing_minute_reference_repair_count=0,
            closing_minute_reference_repair_session_count=0,
            closing_minute_reference_repair_path_sha256=adapter._sha([]))
        results[candidate] = result
    return results


def test_four_arm_protocol_is_prospective_qcom_excluded_stock_sensitivity():
    assert study.CANDIDATES == {"R231": ("ar_off", 0), "R232": ("ar_on100", 0),
        "R233": ("ar_off", 5), "R234": ("ar_on100", 5)}
    value, _ = manifest_fixture()
    assert study.validate_manifest(value) is value
    assert study.PROTOCOL["excluded_stock_security_id_sha256"] == study.EXCLUDED_STOCK_SECURITY_ID_SHA256
    assert study.PROTOCOL["confirmation"] is False
    assert study.PROTOCOL["sensitivity_only"] is True
    assert set(study.CANDIDATES).isdisjoint(study.original.CANDIDATES)


@pytest.mark.parametrize("defect", ("old_candidate", "reordered", "missing", "extra_row_field",
    "wrong_policy", "wrong_exclusion", "wrong_package", "wrong_activation", "wrong_slippage",
    "bool_slippage", "wrong_arm", "wrong_tilt", "repair_disabled", "false_confirmation",
    "missing_statistic", "duplicate_project", "bool_source_count", "wrong_source_digest"))
def test_manifest_refuses_old_family_alias_or_changed_economics(defect):
    value, _ = manifest_fixture()
    row = value["candidates"][0]
    if defect == "old_candidate":
        row["candidate_id"] = "R225"
    elif defect == "reordered":
        value["candidates"].reverse()
    elif defect == "missing":
        value["candidates"].pop()
    elif defect == "extra_row_field":
        row["extra"] = "unreviewed"
    elif defect == "wrong_policy":
        value["protocol"]["exclusion_rule"] = "skip_reference_only"
    elif defect == "wrong_exclusion":
        row["excluded_stock_security_id_sha256"] = "f" * 64
    elif defect == "wrong_package":
        value["package_sha256"] = "f" * 64
    elif defect == "wrong_activation":
        value["activation_manifest_sha256"] = "f" * 64
    elif defect == "wrong_slippage":
        row["slippage_bps"] = 5
    elif defect == "bool_slippage":
        row["slippage_bps"] = False
    elif defect == "wrong_arm":
        row["arm"] = "ar_on100"
    elif defect == "wrong_tilt":
        row["tilt_fraction"] = "1.00"
    elif defect == "repair_disabled":
        row["reference_repair_enabled"] = False
    elif defect == "false_confirmation":
        value["protocol"]["confirmation"] = 0
    elif defect == "missing_statistic":
        row["statistic_names"].pop()
    elif defect == "duplicate_project":
        value["candidates"][1]["project_name"] = row["project_name"]
    elif defect == "bool_source_count":
        row["source_file_count"] = True
    elif defect == "wrong_source_digest":
        row["source_files_sha256"] = "not a digest"
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study.validate_manifest(value)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    manifest, projection = manifest_fixture()
    path = tmp_path / "qcom-exclusion.json"
    raw = canonical(manifest)
    path.write_bytes(raw)
    monkeypatch.setattr(adapter, "QCOM_EXCLUSION_MANIFEST_PATH", path)
    monkeypatch.setattr(adapter, "FROZEN_QCOM_EXCLUSION_MANIFEST_SHA256",
                        hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(adapter, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda api: None)
    fake = Fake()
    monkeypatch.setattr(adapter.common, "_post", fake.post)
    plan = adapter.build_plan("R231", ORG, tmp_path / "control", family="qcom_exclusion")
    return plan, projection, fake, manifest


def test_new_family_preview_claim_and_attempt_bound_are_separate(frozen):
    plan, projection, fake, _ = frozen
    identity = adapter.preview(plan, projection)
    assert identity["manifest_sha256"] == adapter.FROZEN_QCOM_EXCLUSION_MANIFEST_SHA256
    assert identity["authority"] == "owner_exploratory_signature_waiver"
    receipt = adapter.launch(plan, projection, fake)
    assert receipt["candidate_id"] == "R231" and receipt["attempt"] == 1
    assert adapter._path(plan, "claim").exists()
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="consumed"):
        adapter.launch(plan, projection, fake)
    for invalid in (False, 0, 4, "2", 1.0):
        with pytest.raises(adapter.RelaxedQcSubmissionError, match="bound"):
            adapter.build_plan("R231", ORG, plan.control_directory, invalid,
                               family="qcom_exclusion")
    assert sum(endpoint == "backtests/create" for endpoint, _ in fake.calls) == 1


def test_changed_new_manifest_refuses_before_any_cloud_call(frozen):
    plan, projection, fake, value = frozen
    value["candidates"][0]["project_name"] += " changed"
    adapter.QCOM_EXCLUSION_MANIFEST_PATH.write_bytes(canonical(value))
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="frozen manifest"):
        adapter.launch(plan, projection, fake)
    assert fake.calls == []


@pytest.mark.parametrize("candidate", tuple(study.CANDIDATES))
def test_completed_fake_cloud_reads_all_three_linked_statistics_once(frozen, candidate):
    first_plan, projection, fake, manifest = frozen
    plan = dataclasses.replace(first_plan, candidate_id=candidate)
    row = next(item for item in manifest["candidates"] if item["candidate_id"] == candidate)
    receipt = adapter.launch(plan, projection, fake)
    fake.status = "Completed."
    assert adapter.poll_status(plan, receipt, fake) == "Completed."
    statistics = order_statistics(row)
    aggregate = json.loads(statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"])
    aggregate.update(stock_exclusion_policy_id=study.EXCLUSION_RULE,
        excluded_logical_security_sha256=study.EXCLUDED_STOCK_SECURITY_ID_SHA256)
    raw = canonical(aggregate).decode("ascii")
    statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"] = raw
    meta = json.loads(statistics["ARV2_SIX_GATE_ORDER_META"])
    meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    statistics["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
    fake.statistics = {**statistics, "Net Profit": "DO NOT RETAIN"}
    result = adapter.read_result_once(plan, receipt, fake)
    assert result["run_valid"] is True
    assert result["aggregates"]["stock_exclusion_policy_id"] == study.EXCLUSION_RULE
    assert result["aggregates"]["excluded_logical_security_sha256"] == study.EXCLUDED_STOCK_SECURITY_ID_SHA256
    assert "DO NOT RETAIN" not in str(result)
    assert sum(endpoint == "backtests/read" for endpoint, _ in fake.calls) == 1
    with pytest.raises(adapter.common.SixUniverseSettlementSubmissionError):
        adapter.read_result_once(plan, receipt, fake)


def test_new_family_parser_binds_exclusion_and_diagnostic_digest(monkeypatch):
    value, _ = manifest_fixture()
    row = value["candidates"][0]
    plan = adapter.RelaxedQcPlan("R231", ORG, Path("/unused"), family="qcom_exclusion")
    report = diagnostic_fixture("ar_off", 0, "0")
    report.update(schema=study.diagnostics.REFERENCE_REPAIR_SCHEMA,
        closing_minute_reference_repair_count=0,
        closing_minute_reference_repair_session_count=0,
        closing_minute_reference_repair_path_sha256=adapter._sha([]))
    parsed = {"run_valid": True, "meta": {"matched_diagnostics_sha256": adapter._sha(report)},
        "aggregates": {"comparison_arm": "ar_off",
            "analyst_revision_economic_usage": "none_authenticated_score_clock_only",
            "stock_exclusion_policy_id": study.EXCLUSION_RULE,
            "excluded_logical_security_sha256": study.EXCLUDED_STOCK_SECURITY_ID_SHA256,
            "account": {"cumulative_return": "0"}}}
    monkeypatch.setattr(adapter, "_candidate", lambda value: row)
    def common(value, statistics, **kwargs):
        assert kwargs["decision_count"] == 261
        assert kwargs["expected_geometry"] is None
        assert kwargs["extra_aggregate_fields"] == frozenset({
            "comparison_arm", "analyst_revision_economic_usage",
            "stock_exclusion_policy_id", "excluded_logical_security_sha256"})
        return copy.deepcopy(parsed)
    monkeypatch.setattr(adapter, "_parse_order_common", common)
    stats = {name: canonical(report if name == study.DIAGNOSTIC_NAME else {}).decode("ascii")
             for name in row["statistic_names"]}
    assert study.parse_order(plan, stats)["diagnostics"] == report
    parsed["aggregates"]["excluded_logical_security_sha256"] = "f" * 64
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="security identity"):
        study.parse_order(plan, stats)


def test_four_stock_arm_comparison_computes_only_matched_spreads():
    result = study.compare_results(result_fixture())
    assert result["comparison_valid"] is True
    assert result["sensitivity_only"] is True
    assert result["formal_alpha"] is False
    assert result["legacy_R227_R230_ETF_controls_matched"] is False
    assert [row["AR_on_minus_fully_off_percentage_points"] for row in result["comparisons"]] == ["5.00", "4.00"]


@pytest.mark.parametrize("defect", ("old_etf_arm", "missing", "invalid", "changed_source",
    "changed_etf", "changed_capital", "changed_arm", "changed_slippage", "changed_exclusion",
    "changed_decisions", "nonfinite_return"))
def test_four_stock_arm_comparison_refuses_unmatched_or_invalid_evidence(defect):
    results = result_fixture()
    item = results["R234"]
    if defect == "old_etf_arm":
        results["R227"] = results.pop("R234")
    elif defect == "missing":
        results.pop("R234")
    elif defect == "invalid":
        item["run_valid"] = False
    elif defect == "changed_source":
        item["diagnostics"]["membership_cap_path_sha256"] = "c" * 64
    elif defect == "changed_etf":
        item["diagnostics"]["etf_daily_panel_sha256"] = "c" * 64
    elif defect == "changed_capital":
        item["aggregates"]["account"]["starting_equity"] = "100001"
    elif defect == "changed_arm":
        item["aggregates"]["comparison_arm"] = "ar_off"
    elif defect == "changed_slippage":
        item["diagnostics"]["slippage_bps_per_side"] = 0
    elif defect == "changed_exclusion":
        item["aggregates"]["excluded_logical_security_sha256"] = "f" * 64
    elif defect == "changed_decisions":
        item["aggregates"]["execution"]["completed_rebalance_count"] = 260
    elif defect == "nonfinite_return":
        item["aggregates"]["account"]["cumulative_return"] = "NaN"
    with pytest.raises((ValueError, study.diagnostics._base.AcceptedRiskSixUniverseOrderQcRuntimeError)):
        study.compare_results(results)


@pytest.fixture(scope="module")
def actual_family():
    from scripts import run_arv2_qcom_exclusion as script
    inputs = script.package()
    projected = {candidate: script.projected(candidate, inputs)
                 for candidate in study.CANDIDATES}
    return script, inputs, projected


def test_real_freeze_preview_and_all_seventeen_cloud_files_are_pinned(actual_family, monkeypatch, tmp_path):
    script, _inputs, projected = actual_family
    pinned = adapter._qcom_exclusion_manifest()
    monkeypatch.setattr(script, "package", lambda: _inputs)
    monkeypatch.setattr(script, "projected", lambda candidate, inputs=None: projected[candidate])
    assert script.freeze() == pinned
    for row in pinned["candidates"]:
        candidate = row["candidate_id"]
        value, profile = projected[candidate]
        plan = adapter.build_plan(candidate, ORG, tmp_path / "control", family="qcom_exclusion")
        preview = adapter.preview(plan, value)
        assert preview["manifest_sha256"] == adapter.FROZEN_QCOM_EXCLUSION_MANIFEST_SHA256
        assert preview["projection_sha256"] == row["projection_sha256"]
        assert preview["profile_sha256"] == profile["profile_sha256"]
        assert profile["stock_exclusion_policy_id"] == study.EXCLUSION_RULE
        assert profile["excluded_logical_security_sha256"] == study.EXCLUDED_STOCK_SECURITY_ID_SHA256
        assert len(value.source_files) == 17
        for item in value.source_files:
            source = item.source_bytes.decode("ascii")
            compile(source, item.project_path, "exec")
            compile("from AlgorithmImports import *\n" + source, item.project_path, "exec")
            assert hashlib.sha256(item.source_bytes).hexdigest() == item.content_sha256


def test_prior_matched_family_manifest_and_all_six_projections_stay_unchanged(actual_family):
    script, inputs, _projected = actual_family
    from scripts import run_arv2_matched_study as old_script
    from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as source
    paths_and_hashes = (
        (adapter.MATCHED_STUDY_MANIFEST_PATH, adapter.FROZEN_MATCHED_STUDY_MANIFEST_SHA256),
        (adapter.MATCHED_STUDY_DIAGNOSTIC_MANIFEST_PATH, adapter.FROZEN_MATCHED_STUDY_DIAGNOSTIC_MANIFEST_SHA256),
        (adapter.MATCHED_STUDY_CLOSING_MINUTE_MANIFEST_PATH, adapter.FROZEN_MATCHED_STUDY_CLOSING_MINUTE_MANIFEST_SHA256),
        (adapter.MATCHED_STUDY_FEE_CALLBACK_MANIFEST_PATH, adapter.FROZEN_MATCHED_STUDY_FEE_CALLBACK_MANIFEST_SHA256),
    )
    for path, pinned in paths_and_hashes:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pinned
    original = adapter._matched_study_fee_callback_manifest()
    for row in original["candidates"]:
        value, profile = source.build_matched_historical_projection(
            inputs, row["arm"], row["slippage_bps"])
        assert value.projection_sha256 == row["projection_sha256"]
        assert value.profile_sha256 == profile["profile_sha256"] == row["profile_sha256"]
    assert script.CONTROL != old_script.CONTROL
