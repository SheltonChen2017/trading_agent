"""Authenticate real production pins and reject unmatched comparison fixtures."""

import copy

import pytest

from scripts import run_arv2_weight_ablation as script
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from tests.analyst_revisions_v2 import test_qc_recent_coverage_projection as inputs

prior_package = inputs.prior_package
actual_package = inputs.actual_package


def test_actual_production_ablation_freeze_and_successful_predecessor_are_exact(prior_package, actual_package, monkeypatch, tmp_path):
    monkeypatch.setattr(script, "packages", lambda: (prior_package, actual_package))
    assert script.freeze() == adapter._ablation_manifest()
    predecessor = next(row for row in adapter._manifest()["candidates"] if row["candidate_id"] == "R214")
    on = adapter._ablation_manifest()["candidates"][1]
    for key in ("projection_sha256", "profile_sha256", "source_files_sha256", "matched_baseline_profile_sha256"):
        assert on[key] == predecessor[key]
    for candidate in script.PAIR:
        plan = adapter.build_plan(candidate, "a" * 32, tmp_path / "control", family="weight_ablation")
        adapter.preview(plan, script.projected(candidate)[0])


def test_actual_all25_manifest_source_and_exclusive_family_match(prior_package, actual_package, monkeypatch, tmp_path):
    monkeypatch.setattr(script, "packages", lambda: (prior_package, actual_package))
    assert script.freeze(all25=True) == adapter._coverage25_manifest()
    plan = adapter.build_plan("R222", "a" * 32, tmp_path / "control", family="coverage25")
    adapter.preview(plan, script.projected("R222")[0])
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="not frozen"):
        adapter.build_plan("R222", "a" * 32, tmp_path / "control", family="weight_ablation")


@pytest.mark.parametrize("defect", (None, "invalid", "path", "sleeves", "geometry", "baseline"))
def test_cached_comparison_requires_two_valid_identical_baselines(tmp_path, monkeypatch, defect):
    aggregate = {"account": {"cumulative_return": "0.50", "starting_equity": "1000000",
        "observation_count": 290, "first_observation_session": "2025-08-01", "last_observation_session": "2026-09-25"},
        "matched_baseline_target_path_sha256": "a" * 64, "matched_baseline_profile_sha256": "b" * 64,
        "sleeve_diagnostics": {"rows": []}, "admission_leverage": "2", "target_gross_exposure": "0.98", "execution": {}}
    off = {"run_valid": True, "aggregates": aggregate}
    on = copy.deepcopy(off)
    on["aggregates"]["account"]["cumulative_return"] = "0.55"
    if defect == "invalid":
        on["run_valid"] = False
    elif defect == "path":
        on["aggregates"]["matched_baseline_target_path_sha256"] = "c" * 64
    elif defect == "baseline":
        on["aggregates"]["matched_baseline_profile_sha256"] = "c" * 64
    elif defect == "sleeves":
        on["aggregates"]["sleeve_diagnostics"]["rows"].append([1])
    elif defect == "geometry":
        on["aggregates"]["account"]["observation_count"] = 289
    monkeypatch.setattr(script, "CONTROL", tmp_path)
    for candidate, value in zip(script.PAIR, (off, on)):
        adapter._write_artifact(tmp_path / f"{candidate}-A1-result.json", value)
    if defect:
        with pytest.raises(ValueError, match="valid|matched|geometry"):
            script.compare_cached()
    else:
        result = script.compare_cached()
        assert result["net_return_spread_percentage_points"] == "5.00"
        assert result["analyst_entry_and_count_gates_retained"] is True
        assert result["weight_tilt_only"] is True
