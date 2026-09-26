"""All-six 25% coverage is prospective, partial-budget and unknown-ID safe."""

import dataclasses
from decimal import Decimal, localcontext
import hashlib
from pathlib import Path
import sys
import types

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as subject
from research.analyst_revisions_v2_qc import six_universe_relaxed_selection_source as selection
from tests.analyst_revisions_v2 import test_qc_recent_coverage_projection as inputs
from tests.analyst_revisions_v2 import test_qc_relaxed_selection_source as fixtures

prior_package = inputs.prior_package
actual_package = inputs.actual_package
ROOT = Path(selection.__file__).parent


@pytest.fixture
def gate(monkeypatch):
    name = "accepted_risk_six_universe_gate"
    module = types.ModuleType(name)
    monkeypatch.setitem(sys.modules, name, module)
    source = selection.render_all25_gate_source((ROOT / (name + ".py")).read_text())
    exec(compile(source, name + ".py", "exec"), module.__dict__)
    return module


@pytest.fixture(scope="module")
def projection(prior_package, actual_package):
    return subject.build_all25_order_projection(prior_package, actual_package, 100)


@pytest.mark.parametrize("universe", selection.ALL25_UNIVERSES)
def test_exact25_boundary_scales_all_six_sleeves_and_excludes_unknowns(gate, universe):
    rows = fixtures._rows(gate, universe, count=20, known=5, positives=5, weight="0.0125")
    item = fixtures._sleeve(fixtures._construction(gate, {universe: rows}), universe)
    assert item.coverage.valid
    assert item.coverage.mapping_ratio == item.coverage.cap_weight_coverage_ratio == Decimal("0.25")
    assert item.coverage.total_reported_weight == Decimal("0.25")
    assert item.matched_security_ids == tuple(row.security_id for row in rows[:5])
    assert len(item.matched_stock_weights) == 5
    with localcontext() as context:
        context.prec = 96
        stock_weight = sum((weight for _, weight in item.matched_stock_weights), Decimal(0))
        # Half the ten slots are filled; the deliverable known-cap weight is
        # 0.25 * 0.25 = 6.25% of the sleeve, NOT a full-sleeve redistribution.
        assert 0 < stock_weight <= item.budget * Decimal("0.03125")
        assert item.matched_etf_fallback_weight == item.budget - stock_weight
        assert item.matched_etf_fallback_weight > item.budget * Decimal("0.96")


@pytest.mark.parametrize("universe", selection.ALL25_UNIVERSES)
@pytest.mark.parametrize("dimension", ("mapping", "cap", "total", "known_count", "upper_total"))
def test_each_coverage_dimension_refuses_below25_or_above_unchanged_upper(gate, universe, dimension):
    rows = fixtures._rows(gate, universe, positives=20)
    if dimension == "mapping":
        rows = fixtures._rows(gate, universe, known=4, positives=20)
        expected = "SID_NAME_MAPPING_BELOW_MINIMUM"
    elif dimension == "cap":
        rows = list(rows)
        for index in range(5, 20):
            rows[index] = dataclasses.replace(rows[index], pit_market_cap=None)
        rows[0] = dataclasses.replace(rows[0], reported_weight=Decimal("0.049999"))
        rows = tuple(rows)
        expected = "MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM"
    elif dimension == "total":
        rows = fixtures._rows(gate, universe, weight="0.012499")
        expected = "TOTAL_REPORTED_WEIGHT_OUT_OF_RANGE"
    elif dimension == "known_count":
        rows = fixtures._rows(gate, universe, count=4, positives=4, weight="0.25")
        expected = "KNOWN_MARKET_CAP_NAME_COUNT_BELOW_MINIMUM"
    else:
        rows = fixtures._rows(gate, universe, weight="0.052501")
        expected = "TOTAL_REPORTED_WEIGHT_OUT_OF_RANGE"
    item = fixtures._sleeve(fixtures._construction(gate, {universe: rows}), universe)
    assert expected in item.coverage.refusal_reasons
    assert not item.coverage.valid and not item.matched_stock_weights
    assert item.matched_etf_fallback_weight == item.budget


@pytest.mark.parametrize("universe", selection.ALL25_UNIVERSES[:-1])
def test_relaxation_does_not_disable_non_xle_analyst_entry(gate, universe):
    rows = fixtures._rows(gate, universe, known=5, positives=4, weight="0.0125")
    item = fixtures._sleeve(fixtures._construction(gate, {universe: rows}), universe)
    assert item.coverage.valid and item.positive_score_count == 4
    assert not item.matched_stock_weights and item.matched_etf_fallback_weight == item.budget


def test_xle_keeps_independent_cap_selection_at25_and_unknown_score_cannot_become_identity(gate):
    rows = fixtures._rows(gate, "XLE", known=5, positives=0, weight="0.0125")
    rows = rows[:5] + tuple(dataclasses.replace(row, firm_specific_score=Decimal("999999"))
                           for row in rows[5:])
    item = fixtures._sleeve(fixtures._construction(gate, {"XLE": rows}), "XLE")
    assert item.coverage.valid and item.positive_score_count == 0
    assert item.matched_security_ids == tuple(row.security_id for row in rows[:5])


@pytest.mark.parametrize("policy", ((), list(selection.ALL25_COVERAGE_POLICY),
    selection.ALL25_COVERAGE_POLICY[::-1],
    (("SPY", "0.24", "0.25", "0.25", 5), *selection.ALL25_COVERAGE_POLICY[1:]),
    (("SPY", "0.25", "0.25", "0.25", True), *selection.ALL25_COVERAGE_POLICY[1:])))
def test_public_all25_renderer_refuses_scope_expansion(policy):
    with pytest.raises(selection.RelaxedSelectionSourceError, match="exact six-universe"):
        selection.render_all25_gate_source((ROOT / "accepted_risk_six_universe_gate.py").read_text(), policy)


@pytest.mark.parametrize("percent", (0, 20, 120, True, "100"))
def test_projection_is_exactly100_before_any_input_load(percent):
    with pytest.raises(subject.RelaxedOrderProjectionError, match="exactly 100"):
        subject.build_all25_order_projection(object(), object(), percent)


def test_actual16file_closure_rebinds_all_profile_layers_and_versions_results(
        projection, prior_package, actual_package):
    value, profile = projection
    sources = {item.project_path: item.source_bytes.decode("ascii") for item in value.source_files}
    assert len(sources) == 16
    assert value.schema == "arv2-six-universe-all25-tilt100-qc-projection-v1"
    assert value.role == "matched_revision_tilt100_all25_recent"
    assert value.variant == "cap90_matched_revision_tilt100_all25_recent_v1"
    assert value.total_source_byte_count + 32768 <= 448 * 1024
    assert profile["maximum_stock_weight_change_fraction"] == "1.00"
    assert profile["target_gross_exposure"] == "0.98"
    old_policy = (("QQQ", "0.70", "0.80", "0.95", 5),
                  ("SOXX", "0.70", "0.80", "0.95", 5),
                  ("REMX", "0.50", "0.50", "0.25", 5))
    old, old_profile = subject.build_relaxed_order_projection(prior_package, actual_package, 100, old_policy)
    assert value.projection_sha256 != old.projection_sha256
    for key in ("gate_profile_sha256", "evaluation_profile_sha256", "cap90_predecessor_profile_sha256",
                "matched_baseline_profile_sha256", "profile_sha256"):
        assert profile[key] != old_profile[key]
    with subject._cloud_loader(sources) as (load, modules):
        for name in sorted(modules):
            load(name)
        gate = modules["accepted_risk_six_universe_gate"]
        targets = modules["accepted_risk_six_universe_order_targets"]
        tilt = modules["accepted_risk_six_universe_order_tilt_targets"]
        bridge = modules["accepted_risk_six_universe_order_bridge_qc_runtime"]
        runtime = modules["accepted_risk_six_universe_order_tilt_qc_runtime"]
        evaluation = modules["accepted_risk_six_universe_gate_evaluator"]
        assert gate.RELAXED_COVERAGE_POLICY == selection.ALL25_COVERAGE_POLICY
        assert "all25" in gate.PROFILE_SCHEMA and "all25" in gate.CONSTRUCTION_SCHEMA
        assert "ALL_SIX" in gate.TOP10_CAP90_EXPLORATORY_PROFILE.to_record()["unresolved_coverage_stock_budget_rule"]
        assert "all25" in targets.SLEEVE_DIAGNOSTIC_SCHEMA
        assert runtime.TILT_SUMMARY_SCHEMA == subject.ALL25_SUMMARY_SCHEMA
        assert runtime.TILT_META_SCHEMA == subject.ALL25_META_SCHEMA
        assert runtime.require_tilt_profile() == profile
        assert bridge.require_bridge_profile("matched")["profile_sha256"] == profile["matched_baseline_profile_sha256"]
        assert gate.TOP10_CAP90_EXPLORATORY_PROFILE.profile_sha256 == profile["gate_profile_sha256"]
        assert evaluation.TOP10_CAP90_EXPLORATORY_PROFILE.profile_sha256 == profile["evaluation_profile_sha256"]
        snapshots = fixtures._snapshots(gate, {name: fixtures._rows(gate, name, known=5,
            positives=0 if name == "XLE" else 5, weight="0.0125") for name in gate.UNIVERSE_IDS})
        construction = gate.build_six_universe_construction(snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        weights = tilt.tilt_matched_weights(construction, snapshots)
        assert weights != construction.matched_weights
        assert {row.security_id for row in weights} == {row.security_id for row in construction.matched_weights}
        assert {row.security_id: row.weight for row in weights if row.asset_kind == "etf"} == {
            row.security_id: row.weight for row in construction.matched_weights if row.asset_kind == "etf"}
        with localcontext() as context:
            context.prec = 96
            assert sum((row.weight for row in weights), Decimal(0)) == Decimal("0.98")
        assert all(row.weight <= Decimal("0.098") for row in weights if row.asset_kind == "stock")
        for sleeve in construction.sleeves:
            diagnostic = targets._sleeve_diagnostic(sleeve, targets.ROLE_MATCHED, construction.profile)
            assert diagnostic.selection_status == "PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK"
    for item in value.source_files:
        assert hashlib.sha256(item.source_bytes).hexdigest() == item.content_sha256
        compile("from AlgorithmImports import *\n" + item.source_bytes.decode("ascii"), item.project_path, "exec")
