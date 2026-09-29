"""Offline source and selection proofs for the prospective floor-one ladder."""

import ast
import dataclasses
from decimal import Decimal

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as matched
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as relaxed
from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_three_name_projection as three_name
from research.analyst_revisions_v2_qc import six_universe_qcom_restored_projection as restored
from research.analyst_revisions_v2_qc import six_universe_qcom_restored_score_floor1_projection as subject
from tests.analyst_revisions_v2.test_qc_matched_historical_projection import package
from tests.analyst_revisions_v2.test_qc_relaxed_selection_source import _rows, _snapshots


_LADDER = ((80, "R260"), (100, "R261"), (120, "R262"), (140, "R263"),
           (160, "R264"), (180, "R265"), (200, "R266"))


def _sources(projection):
    return {item.project_path: item.source_bytes.decode("ascii")
            for item in projection.source_files}


@pytest.fixture(scope="module")
def ladder(package):
    return {percent: subject.build_qcom_admitted_score_floor1_projection(
        package, percent, candidate_id) for percent, candidate_id in _LADDER}


def _sleeve(gate, universe, rows):
    construction = gate.build_six_universe_construction(
        _snapshots(gate, {universe: tuple(rows)}), gate.TOP10_CAP90_EXPLORATORY_PROFILE)
    return next(item for item in construction.sleeves if item.universe_id == universe)


def test_seven_arms_are_distinct_pinned_order_closures_with_original_economics(ladder):
    projections = []
    for percent, candidate_id in _LADDER:
        projection, profile = ladder[percent]
        projections.append(projection.projection_sha256)
        assert projection.schema == (
            f"arv2-six-qcom-admitted-{candidate_id.lower()}-score-floor1-projection-v1")
        assert projection.role == profile["role"] == (
            f"matched_qcom_admitted_{candidate_id.lower()}_score_floor1_"
            f"three_name_ar_on{percent}_s0")
        assert projection.profile_id == profile["profile_id"] == (
            f"arv2-six-matched-qcom-admitted-{candidate_id.lower()}-score-floor1-"
            f"three-name-ar_on{percent}-s0-profile-v1")
        assert profile["coverage_policy_id"] == subject.COVERAGE_POLICY_ID
        assert profile["maximum_stock_weight_change_fraction"] == (
            f"{percent // 100}.{percent % 100:02d}")
        assert profile["comparison_arm"] == f"ar_on{percent}"
        assert profile["analyst_revision_economic_usage"] == "entry_count_and_weight"
        assert profile["target_gross_exposure"] == "0.98"
        assert profile["modeled_fee_bps_per_side"] == "10"
        assert profile["slippage_bps"] == "0"
        assert profile["admission_leverage"] == "2"
        assert projection.total_source_byte_count < 500_000
        assert len(projection.source_files) == 17
        assert "stock_exclusion_policy_id" not in profile
        assert "excluded_logical_security_sha256" not in profile
        sources = _sources(projection)
        assert not any("EXCLUDED_QCOM_SECURITY_ID" in source or
                       "qcom_excluded" in source or "qcom-excluded" in source
                       for source in sources.values())
        with relaxed._cloud_loader(sources) as (load, _):
            gate = load(relaxed._GATE_PATH[:-3])
            runtime = load(relaxed._TILT_RUNTIME_PATH[:-3])
            order = load(subject._ORDER[:-3])
            assert gate.RELAXED_COVERAGE_POLICY == three_name.COVERAGE_POLICY
            assert gate.MINIMUM_POSITIVE_SCORE_COUNT == 1
            assert runtime.require_tilt_profile() == profile
            assert runtime.TILT_META_SCHEMA == (
                f"arv2-six-matched-qcom-admitted-{candidate_id.lower()}-score-floor1-"
                f"three-name-ar_on{percent}-meta-v1")
            assert runtime.TILT_SUMMARY_SCHEMA == (
                f"arv2-six-matched-qcom-admitted-{candidate_id.lower()}-score-floor1-"
                f"three-name-ar_on{percent}-summary-v1")
            assert order.META_SCHEMA == (
                f"arv2-six-matched-qcom-admitted-{candidate_id.lower()}-score-floor1-"
                f"three-name-ar_on{percent}-meta-v1")
    assert len(set(projections)) == len(_LADDER)


def test_floor_one_changes_non_xle_admission_without_lowering_three_verified_names(
        package, ladder):
    new, _ = ladder[100]
    predecessor, _ = restored.build_qcom_admitted_projection(package, "R243", "R256")
    with relaxed._cloud_loader(_sources(new)) as (load, _):
        gate = load(relaxed._GATE_PATH[:-3])
        one = _sleeve(gate, "REMX", _rows(gate, "REMX", positives=1))
        zero = _sleeve(gate, "REMX", _rows(gate, "REMX", positives=0))
        short = _sleeve(gate, "REMX", _rows(gate, "REMX", known=2, positives=1))
        xle = _sleeve(gate, "XLE", _rows(gate, "XLE", positives=0))
        assert one.coverage.valid and one.positive_score_count == 1
        assert len(one.matched_security_ids) == 1
        assert one.matched_etf_fallback_weight > 0
        assert zero.coverage.valid and zero.matched_security_ids == ()
        assert zero.matched_etf_fallback_weight == zero.budget
        assert not short.coverage.valid and short.matched_security_ids == ()
        assert short.matched_etf_fallback_weight == short.budget
        assert xle.coverage.valid and xle.positive_score_count == 0
        assert len(xle.matched_security_ids) == 10
        qcom = matched._authenticated_qcom_security_id(package)
        rows = list(_rows(gate, "REMX", positives=1))
        rows[0] = dataclasses.replace(rows[0], security_id=qcom,
            security_name="QCOM", firm_specific_score=Decimal("1000"))
        assert qcom in _sleeve(gate, "REMX", rows).matched_security_ids
    with relaxed._cloud_loader(_sources(predecessor)) as (load, _):
        gate = load(relaxed._GATE_PATH[:-3])
        old = _sleeve(gate, "REMX", _rows(gate, "REMX", positives=1))
        assert old.coverage.valid and old.matched_security_ids == ()
        assert old.matched_etf_fallback_weight == old.budget


def test_diagnostics_arm_is_actual_tilt_and_validation_accepts_it(ladder):
    for percent, _candidate_id in _LADDER:
        projection, _ = ladder[percent]
        sources = _sources(projection)
        main = ast.parse(sources["main.py"])
        calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == "install_matched_diagnostics"]
        assert len(calls) == 1
        assert isinstance(calls[0].args[1], ast.Constant)
        assert calls[0].args[1].value == f"ar_on{percent}"
        with relaxed._cloud_loader(sources) as (load, _):
            diagnostics = load("accepted_risk_matched_diagnostics")
            accepted = [f"ar_on{value}" for value in subject.TILT_PERCENTS]
            # Two exact validation sites are widened in the generated source;
            # no diagnostics or QC outcome is created by this inspection.
            tree = ast.parse(sources["accepted_risk_matched_diagnostics.py"])
            tuples = [tuple(item.value for item in node.elts)
                      for node in ast.walk(tree) if isinstance(node, ast.Tuple)
                      and all(isinstance(item, ast.Constant) for item in node.elts)]
            assert tuples.count(("ar_off", *accepted, "six_etf_basket")) == 2
            assert callable(diagnostics.install_matched_diagnostics)


@pytest.mark.parametrize("percent,new_id", (
    (0, "R900"), (60, "R900"), (220, "R900"), (True, "R900"),
    (80, "R259"), (80, "R256"), (80, "r900"), (80, "R0900"), (80, True)))
def test_invalid_tilt_or_identity_refuses_before_package_access(percent, new_id):
    with pytest.raises(subject.QcomRestoredScoreFloor1ProjectionError,
                       match="percent or fresh candidate identity"):
        subject.build_qcom_admitted_score_floor1_projection(object(), percent, new_id)


def test_changed_count_or_coverage_anchor_refuses(package):
    parent, _ = restored.build_qcom_admitted_projection(package, "R243", "R256")
    gate = _sources(parent)[relaxed._GATE_PATH]
    for altered in (gate.replace("MINIMUM_POSITIVE_SCORE_COUNT = 3",
                                 "MINIMUM_POSITIVE_SCORE_COUNT = 2", 1),
                    gate.replace("'0.10', '0.10', '0.10', 3",
                                 "'0.10', '0.10', '0.10', 2", 1)):
        with pytest.raises(subject.QcomRestoredScoreFloor1ProjectionError,
                           match="coverage anchor"):
            subject._render_source(relaxed._GATE_PATH, altered, old_id="R256",
                old_percent=80, percent=100, new_id="R900")


def test_changed_order_meta_schema_anchor_refuses(package):
    parent, _ = restored.build_qcom_admitted_projection(package, "R243", "R256")
    source = _sources(parent)[subject._ORDER]
    altered = source.replace("three-name-ar_on80-meta-v1",
                             "three-name-ar_on100-meta-v1", 1)
    with pytest.raises(subject.QcomRestoredScoreFloor1ProjectionError,
                       match="order META schema anchor changed"):
        subject._render_source(subject._ORDER, altered, old_id="R256",
            old_percent=80, percent=100, new_id="R900")
