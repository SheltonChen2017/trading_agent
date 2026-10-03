"""Focused, offline proofs for R277's fixed R268 holdings and AR weights."""

import ast
import dataclasses
from decimal import Decimal
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_relaxed_qc_projection as cloud,
    eight_universe_cap_holdings_weight_only_projection as subject,
    eight_universe_r268_a3_split_rounding as baseline,
)
from tests.analyst_revisions_v2.test_qc_matched_historical_projection import package
from tests.analyst_revisions_v2.test_qc_relaxed_selection_source import _rows, _snapshots


def _sources(projection):
    return {item.project_path: item.source_bytes.decode("ascii")
            for item in projection.source_files}


@pytest.fixture(scope="module")
def projected(package):
    parent, parent_profile = baseline.build_projection(package)
    candidate, profile = subject.build_projection(package)
    return parent, parent_profile, candidate, profile


def test_r277_changes_only_five_source_files_and_preserves_cap_selection(projected):
    parent, parent_profile, candidate, profile = projected
    original, changed = _sources(parent), _sources(candidate)
    assert candidate.schema == subject.SCHEMA
    assert len(candidate.source_files) == len(parent.source_files) == 17
    assert {path for path in changed if changed[path] != original[path]} == subject.CHANGED_SOURCE_PATHS
    assert changed["accepted_risk_six_universe_gate.py"] == original["accepted_risk_six_universe_gate.py"]
    assert changed["accepted_risk_six_universe_order_targets.py"] == original["accepted_risk_six_universe_order_targets.py"]
    assert candidate.package_sha256 == parent.package_sha256
    assert candidate.activation_manifest_sha256 == parent.activation_manifest_sha256
    assert profile["matched_baseline_profile_sha256"] == parent_profile["matched_baseline_profile_sha256"]
    assert profile["reference_baseline_target_path_sha256"] == subject.R268_BASELINE_TARGET_PATH_SHA256
    assert profile["comparison_arm"] == subject.ARM
    assert profile["analyst_revision_economic_usage"] == subject.ECONOMIC_USAGE
    assert profile["coverage_policy_id"] == parent_profile["coverage_policy_id"]
    assert profile["maximum_stock_weight_change_fraction"] == "1.00"
    for key in ("target_gross_exposure", "modeled_fee_bps_per_side", "slippage_bps",
                "admission_leverage", "reference_price_rule", "engine_fee_basis"):
        assert profile[key] == parent_profile[key]
    assert candidate.total_source_byte_count + 32_768 <= 448 * 1024


def test_r277_authenticates_profile_and_refuses_changed_baseline_path(projected):
    _, _, candidate, profile = projected
    sources = _sources(candidate)
    with cloud._cloud_loader(sources) as (load, _):
        runtime = load(subject._RUNTIME[:-3])
        gate = load("accepted_risk_six_universe_gate")
        tilt = load(subject._TILT[:-3])
        assert runtime.require_tilt_profile() == profile
        assert tilt.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == Decimal("1.00")
        assert tilt.TILT_RANK_RULE_ID == "scored_tied_midrank_centered_v1"
        assert gate.SLEEVE_BUDGETS == (Decimal("0.1225"),) * 8
        assert gate.DIRECT_STOCK_WEIGHT_CAP == Decimal("0.098")
        assert gate.UNIVERSE_IDS == subject.eight.UNIVERSES
        assert runtime._require_reference_baseline_target_path(
            subject.R268_BASELINE_TARGET_PATH_SHA256) is None
        for wrong in (None, 1, "0" * 64):
            with pytest.raises(runtime.AcceptedRiskSixUniverseOrderTiltQcRuntimeError,
                               match="baseline holdings/weights differ"):
                runtime._require_reference_baseline_target_path(wrong)
        aggregate = next(node for node in ast.walk(ast.parse(sources[subject._RUNTIME]))
                         if isinstance(node, ast.FunctionDef) and node.name == "_aggregate")
        calls = [ast.unparse(node.value) for node in aggregate.body if isinstance(node, ast.Expr)]
        assert calls.count("_require_reference_baseline_target_path(path.baseline_target_path_sha256)") == 1
        assert calls.index("path.to_record()") < calls.index(
            "_require_reference_baseline_target_path(path.baseline_target_path_sha256)")


def test_r277_aggregate_actually_refuses_a_valid_but_wrong_baseline_path(projected, monkeypatch):
    _, _, candidate, _ = projected
    with cloud._cloud_loader(_sources(candidate)) as (load, _):
        runtime = load(subject._RUNTIME[:-3])
        tilt = load(subject._TILT[:-3])
        path = tilt.TiltTargetPath(
            role=tilt.TILT_ROLE,
            gate_profile_id="gate",
            gate_profile_sha256="0" * 64,
            evaluation_profile_id="evaluation",
            evaluation_profile_sha256="1" * 64,
            construction_path_sha256="2" * 64,
            baseline_target_path_sha256="3" * 64,
            decisions=(),
            target_path_sha256="4" * 64,
        )
        path = dataclasses.replace(path, target_path_sha256=tilt._sha(path._semantic()))
        path.to_record()  # Isolates R277's baseline check from the path's own digest check.
        driver_type = runtime.AcceptedRiskSixUniverseOrderTiltQcDriver
        monkeypatch.setattr(driver_type, "_require_initialized", lambda self: True)
        driver = object.__new__(driver_type)
        driver._target_builder = SimpleNamespace(complete_path=lambda: path)
        with pytest.raises(runtime.AcceptedRiskSixUniverseOrderTiltQcRuntimeError,
                           match="baseline holdings/weights differ"):
            driver._aggregate()


def test_r277_weights_only_same_cap_selected_ids_and_preserves_budget(projected):
    parent, _, candidate, _ = projected
    with cloud._cloud_loader(_sources(candidate)) as (load, _):
        gate = load("accepted_risk_six_universe_gate")
        tilt = load(subject._TILT[:-3])
        rows = list(_rows(gate, "SPY", positives=0))
        for index, score in enumerate((1, 1, 2, 2)):
            rows[index] = dataclasses.replace(rows[index], firm_specific_score=Decimal(score))
        snapshots = _snapshots(gate, {"SPY": tuple(rows)})
        construction = gate.build_six_universe_construction(
            snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        weights = tilt.tilt_matched_weights(construction, snapshots)
        before = {item.security_id: item.weight for item in construction.matched_weights}
        after = {item.security_id: item.weight for item in weights}
        assert set(after) == set(before)
        assert any(after[security_id] != before[security_id]
                   for security_id in (row.security_id for row in rows[:4]))
        assert all(after[security_id] == before[security_id]
                   for security_id in (row.security_id for row in rows[4:10]))
        assert all(item.weight > 0 for item in weights)
        assert sum(item.weight for item in weights) == Decimal("0.98")
        assert all(item.weight <= Decimal("0.098") for item in weights if item.asset_kind == "stock")
        assert tuple(sleeve.matched_security_ids for sleeve in construction.sleeves) == tuple(
            tuple(f"sid-{sleeve.universe_id}-{index:02d}" for index in range(10))
            for sleeve in construction.sleeves)


def test_r277_renderer_refuses_altered_score_or_100pct_transfer_anchor(projected):
    parent, _, candidate, _ = projected
    original = _sources(parent)
    target = original[subject._TILT]
    assert "firm_specific_score=None" in target
    with pytest.raises(subject.EightCapHoldingsWeightOnlyProjectionError,
                       match="score enrichment anchor changed"):
        subject._render_tilt_targets(target.replace("firm_specific_score=None",
                                                   "firm_specific_score=Decimal(0)", 1),
                                     _sources(candidate)[subject._TILT])
    with pytest.raises(subject.EightCapHoldingsWeightOnlyProjectionError,
                       match="exact literal anchor changed"):
        subject._render_tilt_targets(target.replace("Decimal('0.00')",
                                                   "Decimal('0.10')", 1),
                                     _sources(candidate)[subject._TILT])


def test_r277_refuses_nonexact_parent_projection_before_source_use(package, monkeypatch):
    real = baseline.build_projection

    def changed(inputs):
        projection, profile = real(inputs)
        return dataclasses.replace(projection, projection_sha256="0" * 64), profile

    monkeypatch.setattr(baseline, "build_projection", changed)
    with pytest.raises(subject.EightCapHoldingsWeightOnlyProjectionError,
                       match="exact R268 A3 or R270 source ancestry changed"):
        subject.build_projection(package)
