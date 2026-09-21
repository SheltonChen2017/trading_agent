import dataclasses
import json
from decimal import Decimal

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as base,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate as gate,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate_evaluator as subject,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_market_cap_stock_portfolio as fixtures,
)


def _snapshots(value, *, injected_score=False):
    decisions = subject.decision_sessions_for_input(value)
    security_ids = tuple(sorted(item.security_id for item in value.memberships))
    weight = Decimal(1) / Decimal(len(security_ids))
    return tuple(
        subject.PitDecisionSnapshot(
            session=session,
            universes=tuple(
                gate.UniverseSnapshot(
                    universe_id=spec.universe_id,
                    etf_ticker=spec.etf_ticker,
                    etf_security_id="etf-security-" + spec.etf_ticker,
                    constituents=tuple(
                        gate.UniverseConstituent(
                            reported_weight=weight,
                            security_id=security_id,
                            security_name=security_id,
                            pit_market_cap=Decimal(
                                len(security_ids) - index
                            ),
                            firm_specific_score=(
                                Decimal(1) if injected_score and index == 0 else None
                            ),
                        )
                        for index, security_id in enumerate(security_ids)
                    ),
                )
                for spec in gate.UNIVERSE_SPECS
            ),
        )
        for session in decisions
    )


def _runtime(value, *, profile=subject.TOP10_PRIMARY_PROFILE, snapshots=None):
    return subject.SixUniverseGateEvaluationRuntime(
        value,
        profile_id=profile.profile_id,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        symbol_resolution_id="arv2-test-resolution",
        symbol_resolution_sha256="b" * 64,
        decision_snapshots=(
            _snapshots(value) if snapshots is None else snapshots
        ),
        pit_history_call_count=77,
        pit_source_row_count=123_456,
    )


def _loader(value, *, omissions=frozenset(), overrides=None):
    overrides = {} if overrides is None else overrides
    positions = {session: index for index, session in enumerate(value.session_axis)}

    def load(request):
        rows = []
        begin = positions[request.start_session]
        end = positions[request.end_session]
        for security_id in request.security_ids:
            for session in value.session_axis[begin : end + 1]:
                if (security_id, session) in omissions:
                    continue
                rows.append(
                    base.TotalReturnOpenObservation(
                        base.HISTORY_OBSERVATION_SCHEMA,
                        security_id,
                        session,
                        overrides.get((security_id, session), Decimal(100)),
                    )
                )
        return tuple(rows)

    return load


def _complete(value, **kwargs):
    runtime = _runtime(value, **kwargs)
    loader = _loader(value)
    while runtime.phase is subject.EvaluationPhase.HISTORY:
        runtime.run_callback(loader)
    return runtime


def test_profiles_freeze_window_timing_cost_and_distinct_gate_profiles():
    assert subject.PROFILE_IDS == (
        subject.TOP10_PRIMARY_PROFILE.profile_id,
        subject.TOP5_SENSITIVITY_PROFILE.profile_id,
    )
    assert subject.TOP10_PRIMARY_PROFILE.gate_profile is gate.TOP10_PRIMARY_PROFILE
    assert subject.TOP5_SENSITIVITY_PROFILE.gate_profile is gate.TOP5_SENSITIVITY_PROFILE
    assert subject.TOP10_PRIMARY_PROFILE.profile_sha256 != (
        subject.TOP5_SENSITIVITY_PROFILE.profile_sha256
    )
    for profile in subject.PROFILES:
        record = profile.to_record()
        assert record["evaluation_start_session"] == "2021-01-04"
        assert record["evaluation_end_session"] == "2025-12-31"
        assert record["expected_decision_session_count"] == 261
        assert record["execution_timing"].startswith("next_authenticated")
        assert record["cost_bps_per_side"] == 10
        assert record["modeled_cost_rate_per_side"] == "0.001"
        assert record["annualization_sessions"] == "252"
        assert record["gate_score_quantum"] == "0.000000000000000000000000000000000000000000000001"
        assert record["minimum_invested_return_sessions_per_stock_account"] == 50
        assert record["etf_price_series_requirement"].startswith("all_six_ETFs")
        assert record["point_in_time_analyst_archive"] is False
        assert record["orders"] is False


def test_schedule_has_exact_weekly_geometry_and_next_open_inside_window():
    value = fixtures._input(20)
    decisions = subject.decision_sessions_for_input(value)
    assert len(decisions) == 261
    assert decisions[0] == "2021-01-04"
    assert decisions[-1] == "2025-12-29"
    end = value.session_axis.index(subject.EVALUATION_END_SESSION)
    assert all(value.session_axis.index(item) + 1 <= end for item in decisions)


def test_constant_prices_charge_exact_ten_bps_on_initial_two_sided_turnover():
    value = fixtures._input(20)
    runtime = _complete(value)
    summary = runtime.aggregate_summary()
    for role in ("signal", "matched", "six_etf_basket"):
        record = summary[role]
        assert record["cost_bps_per_side"] == 10
        assert record["cumulative_return"] == "-0.00098"
        assert record["rebalance_count"] == 261
        assert record["return_session_count"] == 1_254
    assert summary["meta"]["decision_session_count"] == 261
    assert summary["meta"]["pit_history_call_count"] == 77


def test_execution_uses_profile_bound_economics_after_module_constant_mutation(
    monkeypatch,
):
    value = fixtures._input(20)
    runtime = _runtime(value)
    old_id, new_id = runtime.history_security_ids[:2]
    position = value.session_axis.index("2021-01-05")
    session = value.session_axis[position]
    runtime._history_prices[(old_id, session)] = Decimal(100)
    runtime._history_prices[(new_id, session)] = Decimal(100)
    account = subject._Account(
        "signal",
        weights={old_id: Decimal("0.98")},
        marks={old_id: Decimal(100)},
    )
    monkeypatch.setattr(subject, "MODELED_COST_RATE_PER_SIDE", Decimal("1"))
    monkeypatch.setattr(subject, "ANNUALIZATION_SESSIONS", Decimal("1"))
    monkeypatch.setattr(subject, "GATE_SCORE_QUANTUM", Decimal("1"))

    runtime._advance_account(
        account,
        position,
        {new_id: Decimal("0.98")},
        frozenset((old_id, new_id)),
    )

    # The already-bound runtime cannot be re-priced by mutable module globals,
    # and later profile serialization fails closed before producing a receipt.
    assert account.accumulator.returns == [Decimal("-0.00196")]
    with pytest.raises(
        subject.SixUniverseGateEvaluationError,
        match="economic constants changed",
    ):
        runtime._profile.to_record()


def test_decision_session_jump_is_not_captured_before_next_open_execution():
    value = fixtures._input(20)
    runtime = _runtime(value)
    first_signal = next(
        item.security_id
        for item in runtime._decisions["2021-01-04"].construction.signal_weights
        if item.asset_kind == "stock"
    )
    overrides = {
        (first_signal, session): Decimal(200)
        for session in value.session_axis
        if "2021-01-05" <= session <= subject.EVALUATION_END_SESSION
    }
    loader = _loader(value, overrides=overrides)
    while runtime.phase is subject.EvaluationPhase.HISTORY:
        runtime.run_callback(loader)
    # The stock doubled between the decision and execution opens.  A same-day
    # implementation would capture it; next-open execution does not.
    assert runtime.aggregate_summary()["signal"]["cumulative_return"] == "-0.00098"


def test_one_stale_held_name_does_not_defer_the_whole_rebalance():
    value = fixtures._input(20)
    runtime = _runtime(value)
    first_signal = next(
        item.security_id
        for item in runtime._decisions["2021-01-04"].construction.signal_weights
        if item.asset_kind == "stock"
    )
    loader = _loader(
        value,
        omissions=frozenset({(first_signal, "2021-01-12")}),
    )
    while runtime.phase is subject.EvaluationPhase.HISTORY:
        runtime.run_callback(loader)
    signal = runtime.aggregate_summary()["signal"]
    assert signal["stale_mark_session_count"] == 1
    assert signal["stale_position_deferral_count"] == 1
    assert signal["rebalance_count"] == 261


def test_missing_ineligible_holding_takes_terminal_zero_recovery():
    value = fixtures._input(20)
    runtime = _runtime(value)
    security_id = next(
        item.security_id
        for item in runtime._decisions["2021-01-04"].construction.signal_weights
        if item.asset_kind == "stock"
    )
    account = subject._Account(
        "signal",
        weights={security_id: Decimal("0.5")},
        marks={security_id: Decimal(100)},
    )
    position = value.session_axis.index("2021-01-05")

    runtime._advance_account(account, position, None, frozenset())

    assert account.eligibility_exit_zero_recovery_count == 1
    assert account.weights == {}
    assert account.marks == {}
    assert account.accumulator.wealth == Decimal("0.5")


def test_full_rotation_charges_exact_two_sided_turnover_cost():
    value = fixtures._input(20)
    runtime = _runtime(value)
    old_id, new_id = runtime.history_security_ids[:2]
    position = value.session_axis.index("2021-01-05")
    session = value.session_axis[position]
    runtime._history_prices[(old_id, session)] = Decimal(100)
    runtime._history_prices[(new_id, session)] = Decimal(100)
    account = subject._Account(
        "signal",
        weights={old_id: Decimal("0.98")},
        marks={old_id: Decimal(100)},
    )

    runtime._advance_account(
        account,
        position,
        {new_id: Decimal("0.98")},
        frozenset((old_id, new_id)),
    )

    assert account.turnover_sum == Decimal("1.96")
    assert account.accumulator.returns == [Decimal("-0.00196")]
    assert account.accumulator.wealth == Decimal("0.99804")


def test_top10_and_top5_build_distinct_construction_paths_and_slot_counts():
    value = fixtures._input(20)
    top10 = _runtime(value, profile=subject.TOP10_PRIMARY_PROFILE)
    top5 = _runtime(value, profile=subject.TOP5_SENSITIVITY_PROFILE)
    assert top10._construction_path_sha256 != top5._construction_path_sha256
    top10_sleeve = top10._decisions["2021-01-04"].construction.sleeves[0]
    top5_sleeve = top5._decisions["2021-01-04"].construction.sleeves[0]
    assert len(top10_sleeve.signal_security_ids) == 10
    assert len(top5_sleeve.signal_security_ids) == 5


def test_snapshot_cannot_inject_a_score_or_change_its_session_census():
    value = fixtures._input(20)
    with pytest.raises(
        subject.SixUniverseGateEvaluationError,
        match="inject an R055 score",
    ):
        _runtime(value, snapshots=_snapshots(value, injected_score=True))
    with pytest.raises(
        subject.SixUniverseGateEvaluationError,
        match="snapshot census",
    ):
        _runtime(value, snapshots=_snapshots(value)[:-1])


def test_history_rows_are_typed_bounded_unique_and_within_request():
    value = fixtures._input(20)
    runtime = _runtime(value)
    request = runtime._history_request(0)
    row = base.TotalReturnOpenObservation(
        base.HISTORY_OBSERVATION_SCHEMA,
        request.security_ids[0],
        request.start_session,
        Decimal(100),
    )
    runtime._accept_history(request, (row,))
    with pytest.raises(subject.SixUniverseGateEvaluationError, match="identity"):
        runtime._accept_history(request, (row,))


def test_aggregate_transport_is_fixed_bounded_and_contains_no_raw_rows_or_ids():
    value = fixtures._input(20)
    runtime = _complete(value)
    statistics = runtime.custom_summary_statistics()
    assert tuple(statistics) == subject.expected_custom_summary_statistic_names(
        subject.TOP10_PRIMARY_PROFILE.profile_id
    )
    assert all(len(item.encode("ascii")) <= 4_096 for item in statistics.values())
    joined = "".join(statistics.values())
    assert "perm-security-" not in joined
    assert "adjusted_open" not in joined
    meta = json.loads(statistics[subject.META_STATISTIC_NAME])
    assert meta["aggregate_only"] is True
    assert meta["raw_rows_in_output"] is False
    assert meta["orders"] is False


def test_callback_failure_closes_runtime_and_summary_refuses_before_completion():
    value = fixtures._input(20)
    runtime = _runtime(value)
    with pytest.raises(subject.SixUniverseGateEvaluationError, match="before completion"):
        runtime.aggregate_summary()
    with pytest.raises(RuntimeError):
        runtime.run_callback(lambda _request: (_ for _ in ()).throw(RuntimeError("x")))
    assert runtime.phase is subject.EvaluationPhase.ABORTED
    with pytest.raises(subject.SixUniverseGateEvaluationError, match="closed"):
        runtime.run_callback(_loader(value))


def test_empty_history_refuses_named_incomplete_etf_series_before_completion():
    value = fixtures._input(20)
    runtime = _runtime(value)
    with pytest.raises(
        subject.SixUniverseGateEvaluationError,
        match="SPY ETF price series is incomplete",
    ):
        while runtime.phase is subject.EvaluationPhase.HISTORY:
            runtime.run_callback(lambda _request: ())
    assert runtime.phase is subject.EvaluationPhase.ABORTED


def test_complete_etfs_but_no_stock_entries_refuse_invested_session_floor():
    value = fixtures._input(20)
    runtime = _runtime(value)
    etf_ids = {item[1] for item in runtime._etf_id_by_universe}
    positions = {
        session: index for index, session in enumerate(value.session_axis)
    }

    def etf_only(request):
        rows = []
        begin = positions[request.start_session]
        end = positions[request.end_session]
        for security_id in request.security_ids:
            if security_id not in etf_ids:
                continue
            for session in value.session_axis[begin : end + 1]:
                rows.append(
                    base.TotalReturnOpenObservation(
                        base.HISTORY_OBSERVATION_SCHEMA,
                        security_id,
                        session,
                        Decimal(100),
                    )
                )
        return tuple(rows)

    with pytest.raises(
        subject.SixUniverseGateEvaluationError,
        match="signal invested-session evidence is underfilled",
    ):
        while runtime.phase is subject.EvaluationPhase.HISTORY:
            runtime.run_callback(etf_only)
    assert runtime.phase is subject.EvaluationPhase.ABORTED
