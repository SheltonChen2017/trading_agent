"""Total AR mode pins, production-source replication and comparison scope."""

import copy

import pytest

from scripts import run_arv2_full_ar_ablation as script
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from tests.analyst_revisions_v2 import test_qc_recent_coverage_projection as inputs
from tests.analyst_revisions_v2 import test_qc_relaxed_submission as fixtures

prior_package = inputs.prior_package
actual_package = inputs.actual_package


def test_real_frozen_family_reproduces_r222_on_and_scope_is_disjoint(
        prior_package, actual_package, monkeypatch, tmp_path):
    monkeypatch.setattr(script, "packages", lambda: (prior_package, actual_package))
    frozen = script.freeze()
    assert frozen == adapter._full_ar_ablation_manifest()
    reference = adapter._coverage25_manifest()["candidates"][0]
    on = frozen["candidates"][1]
    for key in ("projection_sha256", "profile_sha256", "source_files_sha256",
                "matched_baseline_profile_sha256", "total_source_bytes"):
        assert on[key] == reference[key]
    for candidate, enabled in script.CANDIDATES.items():
        plan = adapter.build_plan(candidate, "a" * 32, tmp_path / "control", family="full_ar_ablation")
        row = adapter._candidate(plan)
        assert row["analyst_revision_enabled"] is enabled
        adapter.preview(plan, script.projected(candidate)[0])
    assert frozen["candidates"][0]["matched_baseline_profile_sha256"] != on["matched_baseline_profile_sha256"]


@pytest.fixture
def comparison(monkeypatch):
    aggregate, _, _ = fixtures.order_fixture()
    off = {"run_valid": True, "aggregates": copy.deepcopy(aggregate)}
    on = {"run_valid": True, "aggregates": copy.deepcopy(aggregate)}
    off["aggregates"]["account"]["cumulative_return"] = "0.55"
    on["aggregates"]["account"]["cumulative_return"] = "0.50"
    # Full ablation deliberately changes these: they are not weight-only.
    on["aggregates"]["matched_baseline_target_path_sha256"] = "b" * 64
    on["aggregates"]["matched_baseline_profile_sha256"] = "c" * 64
    on["aggregates"]["sleeve_diagnostics"]["rows"][0][5] += 1
    arms = {"R223": off, "R224": on}
    calls = []
    def read(candidate, control, family):
        calls.append((candidate, control, family))
        return arms[candidate]
    monkeypatch.setattr(script, "authenticated_cached_result", read)
    monkeypatch.setattr(adapter, "_full_ar_ablation_manifest", lambda: {"protocol": dict(script.PROTOCOL)})
    return arms, calls


def test_total_ar_comparison_allows_selection_changes_but_calls_authenticated_reader(comparison):
    arms, calls = comparison
    result = script.compare_cached()
    assert result["net_return_spread_percentage_points"] == "-5.00"
    assert result["total_analyst_revision_ablation"] is True
    assert result["weight_tilt_only"] is False and result["formal_alpha"] is False
    assert result["arms"]["R223"]["analyst_revision_enabled"] is False
    assert calls == [(candidate, script.CONTROL, "full_ar_ablation") for candidate in script.CANDIDATES]


@pytest.mark.parametrize("defect", ("invalid", "gross", "admission", "geometry", "start"))
def test_total_ar_comparison_refuses_invalid_or_unmatched_geometry(comparison, defect):
    arms, _ = comparison
    on = arms["R224"]
    if defect == "invalid":
        on["run_valid"] = False
    elif defect == "gross":
        on["aggregates"]["target_gross_exposure"] = "1.00"
    elif defect == "admission":
        on["aggregates"]["admission_leverage"] = "3"
    elif defect == "geometry":
        on["aggregates"]["account"]["observation_count"] = 289
    else:
        on["aggregates"]["account"]["starting_equity"] = "2000000"
    with pytest.raises(ValueError):
        script.compare_cached()


def test_total_ar_comparison_refuses_changed_prospective_protocol(comparison, monkeypatch):
    monkeypatch.setattr(adapter, "_full_ar_ablation_manifest", lambda: {"protocol": {**script.PROTOCOL,
        "cost_bps_per_side": "0"}})
    with pytest.raises(ValueError, match="protocol"):
        script.compare_cached()
