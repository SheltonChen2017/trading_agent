"""Behavioral proofs for the isolated prospective gate and its diagnostics."""

import ast
import dataclasses
from decimal import Decimal, localcontext
from pathlib import Path
import sys
import types

import pytest

from research.analyst_revisions_v2_qc import six_universe_relaxed_selection_source as subject


ROOT = Path(subject.__file__).parent
POLICY = tuple((name, "0.5", "0.5", "0.5", 5) for name in subject.RELAXED_UNIVERSES)


def _module(source, name, monkeypatch):
    module = types.ModuleType(name)
    monkeypatch.setitem(sys.modules, name, module)
    exec(compile(source, name + ".py", "exec"), module.__dict__)
    return module


@pytest.fixture
def gate(monkeypatch):
    return _module(subject.render_gate_source(
        (ROOT / "accepted_risk_six_universe_gate.py").read_text(), POLICY),
        "accepted_risk_six_universe_gate", monkeypatch)


def _rows(gate, universe, *, count=20, positives=12, weight="0.05", known=None):
    if known is None:
        known = count
    return tuple(gate.UniverseConstituent(
        reported_weight=Decimal(weight),
        security_id=f"sid-{universe}-{index:02d}" if index < known else None,
        security_name=f"name-{universe}-{index:02d}" if index < known else None,
        pit_market_cap=Decimal(count - index) if index < known else None,
        firm_specific_score=Decimal(positives - index) if index < positives else Decimal(0),
    ) for index in range(count))


def _snapshots(gate, overrides=None):
    overrides = overrides or {}
    return tuple(gate.UniverseSnapshot(
        spec.universe_id, spec.etf_ticker, "etf-" + spec.universe_id,
        overrides.get(spec.universe_id, _rows(gate, spec.universe_id)),
    ) for spec in gate.UNIVERSE_SPECS)


def _construction(gate, overrides=None, *, unavailable=()):
    return gate.build_six_universe_construction(
        _snapshots(gate, overrides), gate.TOP10_CAP90_EXPLORATORY_PROFILE,
        unavailable_universe_ids=unavailable)


def _sleeve(result, universe):
    return next(item for item in result.sleeves if item.universe_id == universe)


def _targets(gate, monkeypatch):
    for name in ("accepted_risk_preliminary_rating_evaluator", "accepted_risk_sequential_r055_score"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    evaluation = types.ModuleType("accepted_risk_six_universe_gate_evaluator")
    evaluation.TOP10_PRIMARY_PROFILE = types.SimpleNamespace(gate_score_quantum=Decimal("1e-48"))
    evaluation.TOP10_CAP90_EXPLORATORY_PROFILE = types.SimpleNamespace(gate_score_quantum=Decimal("1e-48"))
    monkeypatch.setitem(sys.modules, evaluation.__name__, evaluation)
    return _module(subject.render_targets_source(
        (ROOT / "accepted_risk_six_universe_order_targets.py").read_text()),
        "accepted_risk_six_universe_order_targets", monkeypatch)


@pytest.mark.parametrize("score", [None, Decimal(0), Decimal(-1)])
def test_xle_entry_uses_ten_cap_names_without_positive_analyst_signals(gate, score):
    rows = tuple(dataclasses.replace(row, firm_specific_score=score)
                 for row in _rows(gate, "XLE"))
    xle = _sleeve(_construction(gate, {"XLE": rows}), "XLE")
    assert xle.coverage.valid and xle.positive_score_count == 0
    assert xle.matched_security_ids == tuple(row.security_id for row in rows[:10])
    assert xle.signal_security_ids == xle.matched_security_ids
    assert len(xle.matched_stock_weights) == 10
    assert xle.matched_etf_fallback_weight == 0


def test_xle_two_positive_scores_do_not_limit_stock_count_or_override_cap_order(gate):
    rows = list(_rows(gate, "XLE", positives=2))
    rows[-1] = dataclasses.replace(rows[-1], firm_specific_score=Decimal("9999"))
    xle = _sleeve(_construction(gate, {"XLE": tuple(rows)}), "XLE")
    assert xle.positive_score_count == 3
    assert xle.matched_security_ids == tuple(row.security_id for row in rows[:10])
    assert rows[-1].security_id not in xle.matched_security_ids


def test_xle_fewer_verified_names_preserve_unfilled_slots_in_etf(gate):
    rows = _rows(gate, "XLE", count=7, positives=0, weight="0.14")
    xle = _sleeve(_construction(gate, {"XLE": rows}), "XLE")
    assert xle.coverage.valid and len(xle.matched_stock_weights) == 7
    with localcontext() as context:
        context.prec = 96
        assert xle.matched_etf_fallback_weight == xle.budget * Decimal("0.3")


def test_xle_unknown_identity_names_caps_are_never_selected(gate):
    rows = list(_rows(gate, "XLE", positives=0))
    rows[0] = dataclasses.replace(rows[0], security_id=None)
    rows[1] = dataclasses.replace(rows[1], security_name=None)
    rows[2] = dataclasses.replace(rows[2], pit_market_cap=None)
    # Two identity failures pass the unchanged90% identity floor, while
    # three unknown cap weights fail XLE's unchanged90% cap-coverage floor.
    xle = _sleeve(_construction(gate, {"XLE": tuple(rows)}), "XLE")
    assert not xle.coverage.valid and xle.matched_security_ids == ()
    rows[2] = _rows(gate, "XLE", positives=0)[2]
    xle = _sleeve(_construction(gate, {"XLE": tuple(rows)}), "XLE")
    assert xle.coverage.valid
    assert set(xle.matched_security_ids).isdisjoint({"sid-XLE-00", "sid-XLE-01"})


def test_xle_unavailable_or_invalid_coverage_retains_full_own_etf(gate):
    unavailable = _sleeve(_construction(gate, {"XLE": ()}, unavailable=("XLE",)), "XLE")
    invalid = _sleeve(_construction(gate, {"XLE": _rows(gate, "XLE", weight="0.04")}), "XLE")
    for xle in (unavailable, invalid):
        assert not xle.coverage.valid and not xle.matched_security_ids
        assert xle.matched_etf_fallback_weight == xle.budget


@pytest.mark.parametrize("universe", ["SPY", "XLV", "QQQ", "SOXX", "REMX"])
def test_other_universes_keep_positive_score_entry_requirement(gate, universe):
    item = _sleeve(_construction(gate, {universe: _rows(gate, universe, positives=4)}), universe)
    assert item.coverage.valid and item.positive_score_count == 4
    assert not item.matched_stock_weights and item.matched_etf_fallback_weight == item.budget


@pytest.mark.parametrize("universe", subject.RELAXED_UNIVERSES)
def test_relaxed_coverage_boundary_keeps_unknown_denominator_and_residual_etf(gate, universe):
    rows = _rows(gate, universe, known=10)
    item = _sleeve(_construction(gate, {universe: rows}), universe)
    assert item.coverage.valid
    assert item.coverage.member_count == 20 and item.coverage.mapped_member_count == 10
    assert item.coverage.mapping_ratio == item.coverage.cap_weight_coverage_ratio == Decimal("0.5")
    assert len(item.matched_stock_weights) == 10
    assert set(item.matched_security_ids) == {row.security_id for row in rows[:10]}
    with localcontext() as context:
        context.prec = 96
        selected = sum((weight for _, weight in item.matched_stock_weights), Decimal(0))
        assert selected <= item.budget * Decimal("0.5")
        assert item.matched_etf_fallback_weight == item.budget - selected


@pytest.mark.parametrize("universe", subject.RELAXED_UNIVERSES)
def test_coverage_immediately_below_mapping_and_cap_thresholds_refuses(gate, universe):
    item = _sleeve(_construction(gate, {universe: _rows(gate, universe, known=9)}), universe)
    assert not item.coverage.valid
    assert item.coverage.refusal_reasons == (
        "SID_NAME_MAPPING_BELOW_MINIMUM", "MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM")
    assert item.matched_etf_fallback_weight == item.budget


def test_low_reported_total_scales_invested_stock_budget_instead_of_normalizing_up(gate):
    item = _sleeve(_construction(gate, {"QQQ": _rows(gate, "QQQ", weight="0.025")}), "QQQ")
    assert item.coverage.valid and item.coverage.total_reported_weight == Decimal("0.5")
    assert item.coverage.cap_weight_coverage_ratio == 1
    with localcontext() as context:
        context.prec = 96
        assert sum((weight for _, weight in item.matched_stock_weights), Decimal(0)) <= item.budget / 2
    below = _sleeve(_construction(gate, {"QQQ": _rows(gate, "QQQ", weight="0.0249")}), "QQQ")
    assert "TOTAL_REPORTED_WEIGHT_OUT_OF_RANGE" in below.coverage.refusal_reasons
    above = _sleeve(_construction(gate, {"QQQ": _rows(gate, "QQQ", weight="0.0526")}), "QQQ")
    assert "TOTAL_REPORTED_WEIGHT_OUT_OF_RANGE" in above.coverage.refusal_reasons


def test_known_cap_name_floor_cannot_be_bypassed_by_large_weight_few_names(gate):
    rows = _rows(gate, "QQQ", count=4, positives=4, weight="0.25")
    item = _sleeve(_construction(gate, {"QQQ": rows}), "QQQ")
    assert item.coverage.mapping_ratio == item.coverage.cap_weight_coverage_ratio == 1
    assert item.coverage.refusal_reasons == ("KNOWN_MARKET_CAP_NAME_COUNT_BELOW_MINIMUM",)
    assert item.matched_etf_fallback_weight == item.budget


def test_exact_known_name_floor_five_passes_with_partial_stock_slots(gate):
    rows = _rows(gate, "SOXX", count=5, positives=5, weight="0.2")
    item = _sleeve(_construction(gate, {"SOXX": rows}), "SOXX")
    assert item.coverage.valid and len(item.matched_security_ids) == 5
    with localcontext() as context:
        context.prec = 96
        assert item.matched_etf_fallback_weight == item.budget / 2


def test_full_coverage_keeps_original_slot_weights_without_false_partial_status(gate, monkeypatch):
    targets = _targets(gate, monkeypatch)
    result = _construction(gate)
    for universe in subject.RELAXED_UNIVERSES:
        item = _sleeve(result, universe)
        assert item.matched_etf_fallback_weight == 0
        diagnostic = targets._sleeve_diagnostic(item, targets.ROLE_MATCHED, result.profile)
        assert diagnostic.selection_status == "FULL_STOCK_SLOTS"


def test_unrelaxed_spy_xlv_keep_original_coverage_bounds(gate):
    for universe in ("SPY", "XLV"):
        item = _sleeve(_construction(gate, {universe: _rows(gate, universe, known=10)}), universe)
        assert not item.coverage.valid
        assert item.coverage.refusal_reasons == (
            "SID_NAME_MAPPING_BELOW_MINIMUM", "MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM")


def test_diagnostics_distinguish_unresolved_exposure_from_duplicate_cap(gate, monkeypatch):
    targets = _targets(gate, monkeypatch)
    result = _construction(gate, {"QQQ": _rows(gate, "QQQ", known=10),
        "XLE": _rows(gate, "XLE", positives=0)})
    qqq = targets._sleeve_diagnostic(_sleeve(result, "QQQ"), targets.ROLE_MATCHED, result.profile)
    xle = targets._sleeve_diagnostic(_sleeve(result, "XLE"), targets.ROLE_MATCHED, result.profile)
    assert qqq.selection_status == "PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK"
    assert qqq.duplicate_cap_excess_weight == 0
    assert xle.selection_status == "FULL_STOCK_SLOTS" and xle.positive_score_count == 0
    assert xle.duplicate_cap_excess_weight == 0


def test_aggregate_shared_stock_cap_and_exact_gross_are_preserved(gate):
    overrides = {}
    for universe in gate.UNIVERSE_IDS:
        rows = list(_rows(gate, universe, positives=0 if universe == "XLE" else 12))
        rows[0] = dataclasses.replace(rows[0], security_id="shared")
        overrides[universe] = tuple(rows)
    result = _construction(gate, overrides)
    shared = next(item for item in result.matched_weights if item.security_id == "shared")
    assert shared.weight <= gate.DIRECT_STOCK_WEIGHT_CAP
    with localcontext() as context:
        context.prec = 96
        assert sum((item.weight for item in result.matched_weights), Decimal(0)) == Decimal("0.98")


def test_new_policy_is_bound_into_profiles_and_old_sources_stay_unchanged(gate):
    record = gate.TOP10_CAP90_EXPLORATORY_PROFILE.to_record()
    assert record["relaxed_universe_coverage_policy"] == [list(item) for item in POLICY]
    assert record["xle_stock_entry_rule"].endswith("independent_of_analyst_scores")
    assert "1e-24" in record["unresolved_coverage_stock_budget_rule"]
    changed = tuple((name, "0.6", "0.5", "0.5", 5) for name in subject.RELAXED_UNIVERSES)
    other_source = subject.render_gate_source((ROOT / "accepted_risk_six_universe_gate.py").read_text(), changed)
    namespace = {"__name__": gate.__name__}
    exec(compile(other_source, "other.py", "exec"), namespace)
    assert namespace["TOP10_CAP90_EXPLORATORY_PROFILE"].profile_sha256 != record["profile_sha256"]
    assert "RELAXED_COVERAGE_POLICY" not in (ROOT / "accepted_risk_six_universe_gate.py").read_text()


@pytest.mark.parametrize("value", [None, (), list(POLICY), POLICY[::-1],
    (("QQQ", "NaN", "0.5", "0.5", 5), *POLICY[1:]),
    (("QQQ", "0", "0.5", "0.5", 5), *POLICY[1:]),
    (("QQQ", "0.91", "0.5", "0.5", 5), *POLICY[1:]),
    (("QQQ", "0.5", "0.5", "0.96", 5), *POLICY[1:]),
    (("QQQ", "0.5", "0.5", "0.5", True), *POLICY[1:])])
def test_policy_refuses_noncanonical_or_unbounded_inputs(value):
    with pytest.raises(subject.RelaxedSelectionSourceError):
        subject.render_gate_source((ROOT / "accepted_risk_six_universe_gate.py").read_text(), value)


def test_missing_or_duplicate_source_anchors_refuse():
    original = (ROOT / "accepted_risk_six_universe_gate.py").read_text()
    for broken in (original.replace('SOURCE_VIEW_ID = ', 'CHANGED_SOURCE_VIEW_ID = '),
                   original + '\nSOURCE_VIEW_ID = "duplicate"\n'):
        with pytest.raises(subject.RelaxedSelectionSourceError, match="anchor"):
            subject.render_gate_source(broken, POLICY)
    with pytest.raises(subject.RelaxedSelectionSourceError, match="anchor"):
        subject.render_targets_source("pass\n")


def test_normalization_proves_ast_identity_and_recovers_source_budget():
    original = (ROOT / "accepted_risk_six_universe_gate.py").read_text()
    normalized = subject._normalize(original)
    assert ast.dump(ast.parse(original), include_attributes=False) == ast.dump(ast.parse(normalized), include_attributes=False)
    assert len(normalized) < len(original)
    rendered = subject.render_gate_source(original, POLICY)
    compile("from AlgorithmImports import *\n" + rendered, "qc.py", "exec")


def test_normalization_rejects_executable_changes_and_non_ascii_source(monkeypatch):
    monkeypatch.setattr(subject.ast, "unparse", lambda tree: "pass")
    with pytest.raises(subject.RelaxedSelectionSourceError, match="executable AST"):
        subject._normalize("x = 1\n")
    with pytest.raises(subject.RelaxedSelectionSourceError, match="ASCII"):
        subject._normalize("x = 'é'\n")
