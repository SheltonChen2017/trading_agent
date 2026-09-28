"""A full AR-off control removes entry/count/weight effects, not just tilt."""

import dataclasses
from datetime import date
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_relaxed_qc_projection as subject
from research.analyst_revisions_v2_qc import six_universe_relaxed_selection_source as selection
from tests.analyst_revisions_v2 import test_qc_recent_coverage_projection as inputs
from tests.analyst_revisions_v2 import test_qc_relaxed_selection_source as fixtures
from tests.analyst_revisions_v2 import test_qc_accepted_risk_market_cap_stock_portfolio as input_fixtures

prior_package = inputs.prior_package
actual_package = inputs.actual_package


@pytest.fixture(scope="module")
def pair(prior_package, actual_package):
    return {mode: subject.build_full_ar_ablation_projection(prior_package, actual_package, mode)
            for mode in (False, True)}


def _sources(value):
    return {item.project_path: item.source_bytes.decode("ascii") for item in value.source_files}


@pytest.mark.parametrize("mode", (0, 1, None, "False", Decimal(0), (), object()))
def test_full_ar_mode_requires_exact_bool_before_any_inputs(mode):
    with pytest.raises(subject.RelaxedOrderProjectionError, match="exact boolean"):
        subject.build_full_ar_ablation_projection(object(), object(), mode)


def test_on_is_exact_successful_r222_reference_and_off_rebinds_identity(
        pair, prior_package, actual_package):
    reference, reference_profile = subject.build_all25_order_projection(prior_package, actual_package)
    on, on_profile = pair[True]
    off, off_profile = pair[False]
    row = json.loads((Path(subject.__file__).parent / "six_universe_coverage25_candidates.json")
                     .read_text())["candidates"][0]
    assert on.to_record() == reference.to_record()
    assert on.source_files == reference.source_files
    assert on_profile == reference_profile
    assert on.projection_sha256 == row["projection_sha256"]
    assert on_profile["profile_sha256"] == row["profile_sha256"]
    assert off.schema == "arv2-six-universe-aroff-tilt0-qc-projection-v1"
    assert off.role == "matched_revision_tilt0_aroff_recent"
    assert off_profile["maximum_stock_weight_change_fraction"] == "0.00"
    assert off_profile["tilt_rank_rule_id"] == "disabled_full_AR_off_v1"
    for key in ("gate_profile_sha256", "evaluation_profile_sha256", "matched_baseline_profile_sha256",
                "profile_sha256"):
        assert off_profile[key] != on_profile[key]
    for key in ("target_gross_exposure", "decision_count",
                "evaluation_start_session", "evaluation_end_session", "modeled_fee_bps_per_side",
                "admission_leverage", "daily_cash_minimum", "slippage_bps", "execution"):
        assert off_profile[key] == on_profile[key]
    assert len(off.source_files) == len(on.source_files) == 16
    assert off.total_source_byte_count + 32768 <= 448 * 1024
    for item in off.source_files:
        assert hashlib.sha256(item.source_bytes).hexdigest() == item.content_sha256
        compile("from AlgorithmImports import *\n" + item.source_bytes.decode("ascii"), item.project_path, "exec")
    with subject._cloud_loader(_sources(off)) as (load, modules):
        for name in sorted(modules):
            load(name)
        runtime = modules["accepted_risk_six_universe_order_tilt_qc_runtime"]
        assert runtime.require_tilt_profile() == off_profile
        assert runtime.TILT_SUMMARY_SCHEMA == subject.FULL_AR_OFF_SUMMARY_SCHEMA
        assert runtime.TILT_META_SCHEMA == subject.FULL_AR_OFF_META_SCHEMA
        gate = modules["accepted_risk_six_universe_gate"]
        record = gate.TOP10_CAP90_EXPLORATORY_PROFILE.to_record()
        assert record["minimum_positive_score_count"] == 0
        assert "disabled_for_stock_entry_stock_count_and_weights" in record["analyst_revision_usage"]
        assert record["positive_score_count_diagnostic"] == "zero_not_used_no_positive_entry_floor"
        assert gate.RELAXED_COVERAGE_POLICY == selection.ALL25_COVERAGE_POLICY
        assert gate.DIRECT_STOCK_WEIGHT_CAP == Decimal("0.098")


@pytest.mark.parametrize("universe", selection.ALL25_UNIVERSES)
@pytest.mark.parametrize("positives", (0, 4, 5, 7, 20))
def test_off_admits_top_ten_cap_names_regardless_of_ar_entry_or_count(pair, universe, positives):
    with subject._cloud_loader(_sources(pair[False][0])) as (load, _):
        tilt = load("accepted_risk_six_universe_order_tilt_targets")
        gate = tilt._gate
        rows = fixtures._rows(gate, universe, positives=positives)
        construction = fixtures._construction(gate, {universe: rows})
        sleeve = fixtures._sleeve(construction, universe)
        assert sleeve.coverage.valid
        assert sleeve.matched_security_ids == tuple(row.security_id for row in rows[:10])
        assert sleeve.signal_security_ids == sleeve.matched_security_ids
        assert sleeve.positive_score_count == 0
        assert len(sleeve.matched_stock_weights) == 10
        diagnostic = tilt._matched._sleeve_diagnostic(sleeve, tilt._matched.ROLE_MATCHED,
                                                     construction.profile)
        assert diagnostic.selection_status == "FULL_STOCK_SLOTS"
        assert diagnostic.positive_score_count == 0


@pytest.mark.parametrize("case", ("missing", "zero", "negative", "reverse", "huge_unknown", "duplicate"))
def test_off_entire_construction_and_targets_are_invariant_to_scores(pair, case):
    with subject._cloud_loader(_sources(pair[False][0])) as (load, _):
        tilt = load("accepted_risk_six_universe_order_tilt_targets")
        gate = tilt._gate
        overrides = {}
        for universe in gate.UNIVERSE_IDS:
            rows = fixtures._rows(gate, universe, known=16)
            if case == "duplicate":
                rows = (dataclasses.replace(rows[0], security_id="shared"), *rows[1:])
            overrides[universe] = rows
        original = fixtures._snapshots(gate, overrides)
        changed = tuple(dataclasses.replace(snapshot, constituents=tuple(
            dataclasses.replace(row, firm_specific_score=(
                None if case == "missing" else Decimal(0) if case == "zero"
                else Decimal(-1) if case == "negative" else Decimal(index)
                if case in ("reverse", "duplicate") else Decimal("999999999")))
            for index, row in enumerate(snapshot.constituents))) for snapshot in original)
        before = gate.build_six_universe_construction(original, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        after = gate.build_six_universe_construction(changed, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        assert before.to_record() == after.to_record()
        assert tilt.tilt_matched_weights(before, original) == before.matched_weights
        assert tilt.tilt_matched_weights(before, changed) == before.matched_weights
        assert all(item.weight <= Decimal("0.098") for item in after.matched_weights
                   if item.asset_kind == "stock")
        with localcontext() as context:
            context.prec = 96
            assert sum((item.weight for item in after.matched_weights), Decimal(0)) == Decimal("0.98")


@pytest.mark.parametrize("universe", selection.ALL25_UNIVERSES)
def test_off_retains_five_verified_floor_and_scaled_partial_budget(pair, universe):
    with subject._cloud_loader(_sources(pair[False][0])) as (load, _):
        tilt = load("accepted_risk_six_universe_order_tilt_targets")
        gate = tilt._gate
        rows = fixtures._rows(gate, universe, known=5, positives=0, weight="0.0125")
        construction = fixtures._construction(gate, {universe: rows})
        sleeve = fixtures._sleeve(construction, universe)
        assert sleeve.coverage.valid and len(sleeve.matched_stock_weights) == 5
        assert sleeve.matched_security_ids == tuple(row.security_id for row in rows[:5])
        with localcontext() as context:
            context.prec = 96
            stocks = sum((weight for _, weight in sleeve.matched_stock_weights), Decimal(0))
            assert 0 < stocks <= sleeve.budget * Decimal("0.03125")
            assert sleeve.matched_etf_fallback_weight == sleeve.budget - stocks
        diagnostic = tilt._matched._sleeve_diagnostic(sleeve, tilt._matched.ROLE_MATCHED,
                                                     construction.profile)
        assert diagnostic.selection_status == "PARTIAL_STOCK_EXPOSURE_WITH_ETF_FALLBACK"
        invalid = fixtures._sleeve(fixtures._construction(gate, {universe:
            fixtures._rows(gate, universe, count=4, known=4, positives=0, weight="0.25")}), universe)
        assert not invalid.coverage.valid and not invalid.matched_stock_weights
        assert invalid.matched_etf_fallback_weight == invalid.budget


@pytest.fixture(scope="module")
def synthetic_input():
    # Synthetic fixtures prove software invariance only, never investment edge.
    value = input_fixtures._input(20)
    axis = tuple(day.isoformat() for day in trading_sessions(date(2013, 1, 2), date(2026, 9, 25)))
    return dataclasses.replace(value, session_axis=axis, memberships=tuple(
        dataclasses.replace(row, last_session_index_exclusive=len(axis)) for row in value.memberships))


def test_actual_projected_builder_cannot_enrich_or_tilt_from_score_changes(pair, synthetic_input):
    with subject._cloud_loader(_sources(pair[False][0])) as (load, _):
        tilt = load("accepted_risk_six_universe_order_tilt_targets")
        base = tilt._score._r055
        record = {field.name: getattr(synthetic_input, field.name)
                  for field in dataclasses.fields(synthetic_input)}
        record["memberships"] = tuple(base.SecurityMembership(**dataclasses.asdict(row))
                                      for row in synthetic_input.memberships)
        record["contributions"] = tuple(base.RatingContribution(**dataclasses.asdict(row))
                                        for row in synthetic_input.contributions)
        value = base.PreliminaryRatingInput(**record)
        gate, evaluation = tilt._gate, tilt._evaluation
        session = evaluation.decision_sessions_for_input(value)[0]
        ids = tuple(row.security_id for row in value.memberships)
        snapshots = tuple(gate.UniverseSnapshot(spec.universe_id, spec.etf_ticker, "etf-" + spec.universe_id,
            tuple(gate.UniverseConstituent(Decimal("0.05"), security_id, security_id,
                  Decimal(20 - index), None) for index, security_id in enumerate(ids)))
            for spec in gate.UNIVERSE_SPECS)
        pit = evaluation.PitDecisionSnapshot(session=session, universes=snapshots)
        records = []
        for mode in ("missing", "positive", "negative", "reverse"):
            builder = tilt.MatchedRevisionTiltTargetBuilder(value)
            original = builder._capture._scorer.score_session
            def controlled(current, *, mode=mode):
                result = original(current)
                scores = {} if mode == "missing" else {security_id:
                    Decimal(index + 1) if mode == "positive" else Decimal(-index - 1)
                    if mode == "negative" else Decimal(20 - index)
                    for index, security_id in enumerate(ids)}
                return dataclasses.replace(result, primary_view_firm_specific_scores=scores)
            builder._capture._scorer.score_session = controlled
            decision = builder.build(session, pit)
            assert builder._capture.call_count == 1 and builder._capture.latest is None
            assert all(len(item.selected_security_ids) == 10 for item in decision.sleeves)
            assert all(item.positive_score_count == 0 for item in decision.sleeves)
            records.append(decision.to_record())
        assert all(record == records[0] for record in records[1:])
