"""Zero transfers isolate weighting, while AR-dependent entry stays fixed."""

import dataclasses
from decimal import Decimal

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as sut
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from tests.analyst_revisions_v2 import test_qc_recent_coverage_projection as inputs
from tests.analyst_revisions_v2 import test_qc_relaxed_selection_source as fixtures

prior_package = inputs.prior_package
actual_package = inputs.actual_package


@pytest.fixture(scope="module")
def pair(prior_package, actual_package):
    policy = tuple(tuple(item) for item in adapter._manifest()["coverage_policy"])
    return {percent: sut.build_weight_ablation_projection(prior_package, actual_package, percent, policy)
            for percent in (0, 100)}


def sources(value):
    return {item.project_path: item.source_bytes.decode("ascii") for item in value.source_files}


def test_only_tilt_sources_change_and_all_baseline_profile_pins_match(pair):
    zero, on = sources(pair[0][0]), sources(pair[100][0])
    assert set(zero) == set(on) and len(zero) == 16
    assert {name for name in zero if zero[name] != on[name]} == {
        "accepted_risk_six_universe_order_tilt_targets.py",
        "accepted_risk_six_universe_order_tilt_qc_runtime.py", "main.py"}
    for key in ("gate_profile_sha256", "evaluation_profile_sha256", "matched_baseline_profile_sha256",
                "evaluation_start_session", "evaluation_end_session", "decision_count"):
        assert pair[0][1][key] == pair[100][1][key]
    assert pair[0][1]["maximum_stock_weight_change_fraction"] == "0.00"
    assert pair[100][1]["maximum_stock_weight_change_fraction"] == "1.00"
    assert pair[0][0].projection_sha256 != pair[100][0].projection_sha256


@pytest.mark.parametrize("case", ("distinct", "ties", "missing", "duplicate", "partial", "xle"))
def test_zero_is_exact_baseline_for_scored_and_partial_constructions(pair, case):
    records = {}
    for percent in (0, 100):
        with sut._cloud_loader(sources(pair[percent][0])) as (load, _):
            tilt = load("accepted_risk_six_universe_order_tilt_targets")
            gate = tilt._gate
            overrides = {}
            if case == "ties":
                overrides = {name: tuple(dataclasses.replace(row, firm_specific_score=Decimal(1))
                    for row in fixtures._rows(gate, name)) for name in gate.UNIVERSE_IDS}
            elif case == "missing":
                rows = list(fixtures._rows(gate, "SPY"))
                rows[0] = dataclasses.replace(rows[0], firm_specific_score=None)
                rows[1] = dataclasses.replace(rows[1], firm_specific_score=Decimal(0))
                overrides["SPY"] = tuple(rows)
            elif case == "duplicate":
                for name in gate.UNIVERSE_IDS:
                    rows = list(fixtures._rows(gate, name))
                    rows[0] = dataclasses.replace(rows[0], security_id="shared")
                    overrides[name] = tuple(rows)
            elif case == "partial":
                overrides["QQQ"] = fixtures._rows(gate, "QQQ", known=16)
            elif case == "xle":
                overrides["XLE"] = fixtures._rows(gate, "XLE", positives=0)
            snapshots = fixtures._snapshots(gate, overrides)
            construction = gate.build_six_universe_construction(snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
            result = tilt.tilt_matched_weights(construction, snapshots)
            assert {item.security_id for item in result} == {item.security_id for item in construction.matched_weights}
            assert {item.security_id: item.weight for item in result if item.asset_kind == "etf"} == {
                item.security_id: item.weight for item in construction.matched_weights if item.asset_kind == "etf"}
            if percent == 0 or case == "ties":
                assert result == construction.matched_weights
            elif case == "distinct":
                assert result != construction.matched_weights
            records[percent] = construction.to_record()
    assert records[0] == records[100]


def test_zero_still_refuses_four_positive_scores_outside_xle(pair):
    with sut._cloud_loader(sources(pair[0][0])) as (load, _):
        tilt = load("accepted_risk_six_universe_order_tilt_targets")
        gate = tilt._gate
        snapshots = fixtures._snapshots(gate, {"SPY": fixtures._rows(gate, "SPY", positives=4)})
        construction = gate.build_six_universe_construction(snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        assert not fixtures._sleeve(construction, "SPY").matched_stock_weights
        assert tilt.tilt_matched_weights(construction, snapshots) == construction.matched_weights


@pytest.mark.parametrize("percent", (True, "100", -1, 20, 200))
def test_ablation_scope_refuses_other_strengths_before_packages(percent):
    with pytest.raises(sut.RelaxedOrderProjectionError, match="exactly zero or 100"):
        sut.build_weight_ablation_projection(object(), object(), percent, ())


def test_historical_ladder_still_refuses_zero():
    with pytest.raises(sut.RelaxedOrderProjectionError, match="20 through 200"):
        sut.build_relaxed_order_projection(object(), object(), 0, ())
