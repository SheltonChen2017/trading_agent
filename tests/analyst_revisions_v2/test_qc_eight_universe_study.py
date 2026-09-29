"""Offline R268--R276 freeze, count gate, parser, and comparator checks."""

import copy
import dataclasses
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import eight_universe_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from tests.analyst_revisions_v2.test_qc_matched_study_submission import diagnostic_fixture
from tests.analyst_revisions_v2.test_qc_relaxed_submission import ORG, Fake, canonical


def _eight_report(arm, total_return="0"):
    report = diagnostic_fixture("ar_off", 0, total_return)
    report["schema"] = "arv2-eight-matched-historical-diagnostics-v2-closing-minute"
    report["arm"] = arm
    report["eight_etf_panel_row_count"] = report.pop("six_etf_panel_row_count") + 2510
    report.update(closing_minute_reference_repair_count=0,
                  closing_minute_reference_repair_session_count=0,
                  closing_minute_reference_repair_path_sha256=adapter._sha([]))
    for year in range(2021, 2026):
        for ticker in ("XLI", "XLF"):
            report["year_universe_rows"].append(
                [str(year), ticker, 53 if year == 2024 else 52, 0, 0, 0, "0"])
    report["year_universe_rows"].sort(key=lambda item: item[:2])
    return report


def _counts():
    years = [2021, 2022, 2023, 2024, 2025]
    counts = [1, 1, 1, 1, 22]
    return {"meta": {"decision_count": 261, "sleeve_decision_count": 2088},
            "sleeves": {ticker: {
                "universe_id": ticker,
                "totals": {"relaxed_joint_pass_10_verified3_count": 26},
                "years": [{"year": year, "relaxed_joint_pass_10_verified3_count": value}
                          for year, value in zip(years, counts)],
            } for ticker in study.renderer.UNIVERSES},
            "overlap": {}}


def test_frozen_nine_arm_order_protocol_and_exact_parent_inventory():
    manifest = adapter._eight_universe_manifest()
    assert study.validate_manifest(manifest) is manifest
    assert list(study.CANDIDATE_ARMS) == [f"R{number}" for number in range(268, 277)]
    assert list(study.CANDIDATE_ARMS.values()) == ["ar_off", "ar_on80", "ar_on100",
        "ar_on120", "ar_on140", "ar_on160", "ar_on180", "ar_on200", "eight_etf_basket"]
    assert manifest["protocol"]["input_candidate_manifest_sha256"] == study.input_adapter._MANIFEST_SHA256
    assert manifest["protocol"]["physical_orders"] is True
    assert manifest["protocol"]["maximum_attempts_per_candidate"] == 3
    assert manifest["protocol"]["basket_control_optional"] is True
    assert all(row["source_file_count"] == 17 and row["kind"] == "order"
               for row in manifest["candidates"])
    assert manifest["candidates"][0]["coverage_policy_id"] == study.renderer.OFF_POLICY_ID
    assert manifest["candidates"][-1]["coverage_policy_id"] == study.renderer.OFF_POLICY_ID
    assert manifest["candidates"][0]["minimum_positive_score_count"] == 0
    assert manifest["candidates"][-1]["minimum_positive_score_count"] == 0
    assert all(row["minimum_positive_score_count"] == 1
               for row in manifest["candidates"][1:-1])
    assert all(row["coverage_policy_id"] == study.renderer.NEW_POLICY_ID
               for row in manifest["candidates"][1:-1])


@pytest.mark.parametrize("defect", ["extra_candidate", "wrong_arm", "wrong_parent",
    "wrong_source_hash", "wrong_policy", "wrong_floor", "wrong_schema", "not_order",
    "changed_input_gate", "wrong_source_count", "duplicate_source"])
def test_manifest_rejects_changed_prospective_identity(defect):
    manifest = copy.deepcopy(adapter._eight_universe_manifest())
    row = manifest["candidates"][0]
    if defect == "extra_candidate":
        manifest["candidates"].append(copy.deepcopy(row))
    elif defect == "wrong_arm":
        row["arm"] = "ar_on80"
    elif defect == "wrong_parent":
        row["source_candidate_id"] = "R260"
    elif defect == "wrong_source_hash":
        row["source_projection_sha256"] = "f" * 64
    elif defect == "wrong_policy":
        row["coverage_policy_id"] = study.renderer.NEW_POLICY_ID
    elif defect == "wrong_floor":
        row["minimum_positive_score_count"] = 3
    elif defect == "wrong_schema":
        row["summary_schema"] += "-altered"
    elif defect == "not_order":
        row["kind"] = "coverage"
    elif defect == "changed_input_gate":
        manifest["protocol"]["input_required_new_sleeve_joint_pass_total_at_least"] = 25
    elif defect == "wrong_source_count":
        row["source_file_count"] = 16
    else:
        manifest["candidates"][1]["source_files_sha256"] = row["source_files_sha256"]
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study.validate_manifest(manifest)


@pytest.mark.parametrize("defect", ["total", "annual", "year", "census", "missing"])
def test_preregistered_r267_gate_is_counts_only_and_fail_closed(defect):
    values = _counts()
    assert study._r267_admits(values) is True
    sleeve = values["sleeves"]["XLI"]
    if defect == "total":
        sleeve["totals"]["relaxed_joint_pass_10_verified3_count"] = 25
    elif defect == "annual":
        sleeve["years"][0]["relaxed_joint_pass_10_verified3_count"] = 0
        sleeve["years"][-1]["relaxed_joint_pass_10_verified3_count"] = 23
    elif defect == "year":
        sleeve["years"][0]["year"] = 2020
    elif defect == "census":
        values["meta"]["decision_count"] = 260
    else:
        del values["sleeves"]["XLF"]
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study._r267_admits(values)


def test_baseline_and_ladder_launch_prerequisites_fail_before_qc(tmp_path, monkeypatch):
    fake = Fake()
    monkeypatch.setattr(adapter, "preview", lambda plan, projection: {})
    baseline = adapter.build_plan("R268", ORG, tmp_path / "control", family=study.FAMILY)
    def unavailable(plan):
        raise adapter.RelaxedQcSubmissionError("R267 proof unavailable")
    monkeypatch.setattr(study, "require_input_readiness", unavailable)
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="R267 proof"):
        adapter.launch(baseline, object(), fake)
    assert fake.calls == []
    monkeypatch.setattr(study, "require_input_readiness", lambda plan: True)
    for candidate in ("R269", "R276"):
        plan = dataclasses.replace(baseline, candidate_id=candidate)
        with pytest.raises(adapter.RelaxedQcSubmissionError, match="valid R268"):
            adapter.launch(plan, object(), fake)
        assert fake.calls == []
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="bound"):
        adapter.build_plan("R268", ORG, tmp_path / "control", 4, family=study.FAMILY)


@pytest.mark.parametrize("arm", ["ar_off", "ar_on100", "eight_etf_basket"])
def test_eight_diagnostic_geometry_and_comparator_arm(arm):
    report = _eight_report(arm)
    assert study._validate_eight_diagnostics(report, arm) is True
    changed = copy.deepcopy(report)
    changed["eight_etf_panel_row_count"] = 7530
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study._validate_eight_diagnostics(changed, arm)
    changed = copy.deepcopy(report)
    changed["year_universe_rows"].pop()
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study._validate_eight_diagnostics(changed, arm)


def test_eight_order_parser_binds_diagnostic_digest_and_policy(monkeypatch):
    row = adapter._eight_universe_manifest()["candidates"][0]
    plan = adapter.RelaxedQcPlan("R268", ORG, Path("/unused"), family=study.FAMILY)
    report = _eight_report("ar_off")
    parsed = {"run_valid": True,
              "meta": {"matched_diagnostics_sha256": adapter._sha(report)},
              "aggregates": {"comparison_arm": "ar_off",
                  "analyst_revision_economic_usage": study._usage("ar_off"),
                  "coverage_policy_id": study.renderer.OFF_POLICY_ID,
                  "account": {"cumulative_return": "0"}}}
    monkeypatch.setattr(adapter, "_candidate", lambda plan: row)
    def common(plan, statistics, **kwargs):
        assert kwargs["decision_count"] == 261
        assert kwargs["eight_universe"] is True
        assert kwargs["expected_geometry"] is None
        return copy.deepcopy(parsed)
    monkeypatch.setattr(adapter, "_parse_order_common", common)
    stats = {name: canonical(report if name == study.DIAGNOSTIC_NAME else {}).decode("ascii")
             for name in study.STATISTIC_NAMES}
    assert study.parse_order(plan, stats)["diagnostics"] == report
    parsed["aggregates"]["coverage_policy_id"] = study.renderer.NEW_POLICY_ID
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="coverage"):
        study.parse_order(plan, stats)


def _comparison_results():
    baseline = adapter._eight_r268_a3_manifest()
    corrected = adapter._eight_ar_on_split_manifest()
    source_rows = {
        "R268": (adapter.FROZEN_EIGHT_R268_A3_MANIFEST_SHA256,
                 baseline["candidates"][0], baseline),
        **{row["candidate_id"]: (adapter.FROZEN_EIGHT_AR_ON_SPLIT_MANIFEST_SHA256,
                                  row, corrected)
           for row in corrected["candidates"]},
    }
    results = {}
    for index, (candidate, arm) in enumerate(study.CORE_CANDIDATES.items()):
        value = "0.20" if candidate == "R268" else f"0.{24 + index}"
        manifest_sha, row, manifest = source_rows[candidate]
        results[candidate] = {"candidate_id": candidate,
            "attempt": 3 if candidate == "R268" else 1,
            "manifest_sha256": manifest_sha,
            "projection_sha256": row["projection_sha256"],
            "meta": {"profile_id": row["profile_id"],
                "profile_sha256": row["profile_sha256"],
                "package_sha256": manifest["package_sha256"],
                "activation_manifest_sha256": manifest["activation_manifest_sha256"]},
            "run_valid": True, "diagnostics": _eight_report(arm, value),
            "aggregates": {"comparison_arm": arm,
                "profile_id": row["profile_id"],
                "profile_sha256": row["profile_sha256"],
                "matched_baseline_profile_sha256": row["matched_baseline_profile_sha256"],
                "analyst_revision_economic_usage": study._usage(arm),
                "coverage_policy_id": study._coverage_policy(arm),
                "target_gross_exposure": "0.98", "admission_leverage": "2",
                "account": {"starting_equity": "100000", "cumulative_return": value,
                    "first_observation_session": "2021-01-04",
                    "last_observation_session": "2025-12-31", "observation_count": 1255},
                "execution": {"submitted_rebalance_count": 261,
                    "completed_rebalance_count": 261}}}
    return results


def test_eight_core_run_comparator_requires_corrected_source_lineage():
    results = _comparison_results()
    comparison = study.compare_results(results)
    assert comparison["comparison_valid"] is True
    assert comparison["baseline_candidate_id"] == "R268"
    assert comparison["basket_control_present"] is False
    assert [item["tilt_percent"] for item in comparison["ladder"]] == [80, 100, 120, 140, 160, 180, 200]
    assert comparison["confirmation"] is False
    results["R276"] = {"run_valid": True}
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="R276 is not corrected"):
        study.compare_results(results)
    del results["R276"]
    results["R270"]["run_valid"] = False
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="valid"):
        study.compare_results(results)
    results["R270"]["run_valid"] = True
    results["R270"]["diagnostics"]["etf_daily_panel_sha256"] = "c" * 64
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="vintage"):
        study.compare_results(results)


@pytest.mark.parametrize("candidate,field", [
    ("R268", "attempt"),
    ("R268", "manifest_sha256"),
    ("R270", "manifest_sha256"),
    ("R270", "projection_sha256"),
    ("R270", "meta_profile_sha256"),
    ("R270", "aggregate_profile_sha256"),
    ("R270", "matched_baseline_profile_sha256"),
    ("R270", "meta_package_sha256"),
])
def test_comparator_refuses_original_or_mixed_source_identity(candidate, field):
    results = _comparison_results()
    target = results[candidate]
    old_rows = {row["candidate_id"]: row
                for row in adapter._eight_universe_manifest()["candidates"]}
    if field == "attempt":
        target[field] = 1
    elif field == "meta_profile_sha256":
        target["meta"]["profile_sha256"] = old_rows[candidate]["profile_sha256"]
    elif field == "aggregate_profile_sha256":
        target["aggregates"]["profile_sha256"] = old_rows[candidate]["profile_sha256"]
    elif field == "matched_baseline_profile_sha256":
        target["aggregates"][field] = old_rows[candidate][field]
    elif field == "meta_package_sha256":
        target["meta"]["package_sha256"] = "a" * 64
    elif field == "manifest_sha256":
        target[field] = adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256
    elif field == "projection_sha256":
        target[field] = old_rows[candidate]["projection_sha256"]
    else:
        target[field] = "a" * 64
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="corrected source lineage"):
        study.compare_results(results)


@pytest.mark.parametrize("field", ["split_rule", "baseline_a3_manifest_sha256"])
def test_comparator_refuses_manifest_split_policy_mismatch(monkeypatch, field):
    results = _comparison_results()
    corrected = copy.deepcopy(adapter._eight_ar_on_split_manifest())
    corrected[field] = "a" * 64
    monkeypatch.setattr(adapter, "_eight_ar_on_split_manifest", lambda: corrected)
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="split-policy ancestry"):
        study.compare_results(results)


@pytest.mark.parametrize("candidate", ["R268", "R270", "R276"])
def test_rebuilt_exact_seventeen_file_source_previews_offline(candidate, tmp_path):
    from scripts import run_arv2_eight_universe as script
    projected, profile = script.projected(candidate)
    plan = adapter.build_plan(candidate, ORG, tmp_path / "control", family=study.FAMILY)
    identity = adapter.preview(plan, projected)
    expected_manifest = (adapter.FROZEN_EIGHT_AR_ON_SPLIT_MANIFEST_SHA256
                         if candidate == "R270" else
                         adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256)
    assert identity["manifest_sha256"] == expected_manifest
    assert identity["profile_sha256"] == profile["profile_sha256"]
    assert len(identity["source_files"]) == 17
    assert projected.total_source_byte_count + 32_768 <= 448 * 1024


def test_original_family_freeze_does_not_pull_corrected_candidate_sources(monkeypatch):
    from scripts import run_arv2_eight_universe as script

    def corrected_source_is_not_the_original_inventory(*_args, **_kwargs):
        raise AssertionError("original family freeze traversed corrected routing")

    monkeypatch.setattr(script, "projected", corrected_source_is_not_the_original_inventory)
    assert script.freeze() == adapter._eight_universe_manifest()
