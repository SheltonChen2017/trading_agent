import hashlib
import json
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as base,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_stock_portfolio_evaluator as subject,
)


def _sessions():
    return tuple(
        session.isoformat()
        for session in trading_sessions(
            date(2013, 1, 2), date(2026, 4, 30)
        )
    )


def _input(
    *, membership_end=None, membership_end_security_index=19, security_count=20
):
    sessions = _sessions()
    id_width = max(2, len(str(security_count - 1)))
    session_rows = tuple(
        {
            "schema": base.SESSION_SCHEMA,
            "session_index": index,
            "session": session,
        }
        for index, session in enumerate(sessions)
    )
    last = (
        len(sessions)
        if membership_end is None
        else sessions.index(membership_end)
    )
    memberships = tuple(
        base.build_membership_record(
            security_id=f"perm-security-{index:0{id_width}d}",
            first_session_index=0,
            last_session_index_exclusive=(
                last if index == membership_end_security_index else len(sessions)
            ),
            sector_id="sector-technology",
        )
        for index in range(security_count)
    )
    eligible = sessions.index("2020-11-30")
    contributions = []
    for view in base.SOURCE_VIEW_IDS:
        for index in range(security_count):
            midpoint = security_count // 2
            delta = Fraction(
                index - midpoint if index < midpoint else index - midpoint + 1,
                10,
            )
            contributions.append(
                base.build_contribution_record(
                    source_view_id=view,
                    security_id=f"perm-security-{index:0{id_width}d}",
                    eligible_session_index=eligible,
                    institution_id=f"firm-{index:02d}",
                    common_event_id=f"event-{index:02d}",
                    rating_action=(
                        "downgrades" if index < midpoint else "upgrades"
                    ),
                    firm_delta=delta,
                    global_delta=delta / 2,
                    source_row_sha256=hashlib.sha256(
                        f"source-{view}-{index}".encode("ascii")
                    ).hexdigest(),
                )
            )
    lineage = {
        name: hashlib.sha256(name.encode("ascii")).hexdigest()
        for name in base._SOURCE_LINEAGE_FIELDS
    }
    manifest = base.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=session_rows,
        membership_records=memberships,
        contribution_records=tuple(contributions),
        source_lineage_sha256s=lineage,
        history_batch_security_count=64,
        scoring_sessions_per_callback=5,
        signal_seed_contributions_per_callback=20000,
    )
    return base.load_preliminary_rating_input(
        manifest, session_rows, memberships, tuple(contributions)
    )


def _history_loader(value, *, omissions=frozenset()):
    positions = {session: index for index, session in enumerate(value.session_axis)}

    def load(request):
        rows = []
        begin = positions[request.start_session]
        end = positions[request.end_session]
        for security_id in request.security_ids:
            if security_id == value.benchmark_security_id:
                growth = Decimal("1.0002")
            else:
                index = int(security_id.rsplit("-", 1)[1])
                growth = Decimal("1.001") if index >= 10 else Decimal("0.9995")
            price = Decimal(100)
            for offset, session in enumerate(value.session_axis[begin:end + 1]):
                if offset:
                    with localcontext(base._context()):
                        price = +(price * growth)
                if (security_id, session) not in omissions:
                    rows.append(
                        base.TotalReturnOpenObservation(
                            base.HISTORY_OBSERVATION_SCHEMA,
                            security_id,
                            session,
                            price,
                        )
                    )
        return tuple(rows)

    return load


def _complete(
    value,
    *,
    omissions=frozenset(),
    named_figi_resolution_refusals=(),
):
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=named_figi_resolution_refusals,
    )
    loader = _history_loader(value, omissions=omissions)
    while runtime.phase is not base.RuntimePhase.COMPLETED:
        runtime.run_callback(loader)
    return runtime


def test_profile_freezes_one_mathematically_consistent_stock_rule():
    profile = subject.require_stock_portfolio_profile(subject.PROFILE_ID)
    digest = profile.pop("profile_sha256")
    assert subject._sha(profile) == digest
    assert profile["selection"] == (
        "top_decile_of_resolvable_score_bearing_universe_capped_at_50_"
        "ordered_by_score_then_security_id_without_absolute_score_gate"
    )
    assert profile["maximum_holdings"] == 50
    assert profile["target_gross_exposure"] == "0.98"
    assert profile["stock_weight_cap"] == "0.0196"
    assert profile["exposure_underfill_disposition"] == (
        "retain_residual_cash_and_label_every_result_cell"
    )
    assert profile["cash_return"] == "0"
    assert profile["cost_bps_per_side"] == [10]
    assert profile["account_wide_stale_rebalance_deferral"] is False
    assert profile["stale_position_turnover"] == (
        "excluded_until_current_price_is_available"
    )
    assert profile["locked_position_gross_over_target"] == (
        "preserve_the_locked_weight_and_assign_zero_remaining_budget"
    )
    assert profile["absolute_positive_score_gate"] is False
    assert profile["named_figi_resolution_refusals_excluded_before_ranking"] is True
    assert profile["membership_end_missing_price"] == (
        "assume_zero_terminal_value_as_a_conservative_lower_bound"
    )
    assert profile["terminal_payoff_applied"] is False
    assert profile["leverage"] is False
    assert profile["expected_decision_session_count"] == 261
    assert profile["expected_return_session_count"] == 1254


def test_profile_refuses_implicit_or_unknown_selection():
    with pytest.raises(TypeError, match="profile_id"):
        subject.StockPortfolioEvaluationRuntime(
            _input(),
            package_id="arv2-test-package",
            package_sha256="a" * 64,
            named_figi_resolution_refusals=(),
        )
    with pytest.raises(subject.AcceptedRiskStockPortfolioError, match="exact frozen"):
        subject.StockPortfolioEvaluationRuntime(
            _input(),
            profile_id="arv2-stock-portfolio-unregistered",
            package_id="arv2-test-package",
            package_sha256="a" * 64,
            named_figi_resolution_refusals=(),
        )


def test_weekly_decisions_rank_negative_scores_without_an_absolute_gate():
    value = _input()
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    position = value.session_axis.index(subject.DECISION_START_SESSION)
    scores = {
        f"perm-security-{index:02d}": Decimal(index - 30)
        for index in range(20)
    }
    axis = (subject.PRIMARY_SOURCE_VIEW_ID, subject.PRIMARY_SCORE_ARM)
    runtime._after_score_cross_section(
        position,
        value.memberships,
        {axis: scores},
        {axis: 0},
    )
    selected, matched = runtime._decisions[subject.DECISION_START_SESSION]
    assert selected == ("perm-security-19", "perm-security-18")
    assert matched == tuple(sorted(scores))
    assert sum(
        runtime._targets(
            subject._Account("signal"), selected, position
        ).values(),
        Decimal(0),
    ) == Decimal(0)  # no authenticated history has been loaded yet


def test_top_fifty_slots_target_exactly_ninety_eight_percent():
    value = _input(security_count=500)
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    position = value.session_axis.index(subject.DECISION_START_SESSION)
    axis = (subject.PRIMARY_SOURCE_VIEW_ID, subject.PRIMARY_SCORE_ARM)
    scores = {
        f"perm-security-{index:03d}": Decimal(index)
        for index in range(500)
    }
    runtime._after_score_cross_section(
        position,
        value.memberships,
        {axis: scores},
        {axis: 0},
    )
    selected, _matched = runtime._decisions[subject.DECISION_START_SESSION]
    history_position = runtime._history_session_positions[
        subject.DECISION_START_SESSION
    ]
    for security_id in selected:
        runtime._history_prices[history_position][
            runtime._history_security_positions[security_id]
        ] = "100"

    account = subject._Account("signal")
    executed_gross = runtime._advance_account(
        account, position, selected
    )

    assert len(selected) == subject.MAXIMUM_HOLDINGS
    assert len(account.weights) == subject.MAXIMUM_HOLDINGS
    assert set(account.weights.values()) == {subject.STOCK_WEIGHT_CAP}
    assert sum(account.weights.values(), Decimal(0)) == subject.TARGET_GROSS_EXPOSURE
    assert executed_gross == subject.TARGET_GROSS_EXPOSURE
    assert account.full_target_execution_count == 1
    assert account.underfilled_target_execution_count == 0


def test_equal_score_boundary_uses_the_frozen_security_id_tiebreak():
    value = _input()
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    position = value.session_axis.index(subject.DECISION_START_SESSION)
    axis = (subject.PRIMARY_SOURCE_VIEW_ID, subject.PRIMARY_SCORE_ARM)
    scores = {
        f"perm-security-{index:02d}": Decimal(1)
        for index in range(20)
    }

    runtime._after_score_cross_section(
        position,
        value.memberships,
        {axis: scores},
        {axis: 0},
    )

    assert runtime._decisions[subject.DECISION_START_SESSION][0] == (
        "perm-security-00",
        "perm-security-01",
    )


def test_named_figi_refusal_is_excluded_before_ranking_and_matching():
    value = _input()
    refused = "perm-security-19"
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(refused,),
    )
    position = value.session_axis.index(subject.DECISION_START_SESSION)
    axis = (subject.PRIMARY_SOURCE_VIEW_ID, subject.PRIMARY_SCORE_ARM)
    scores = {
        f"perm-security-{index:02d}": Decimal(index)
        for index in range(20)
    }

    runtime._after_score_cross_section(
        position,
        value.memberships,
        {axis: scores},
        {axis: 0},
    )

    selected, matched = runtime._decisions[subject.DECISION_START_SESSION]
    assert refused not in selected
    assert refused not in matched
    assert selected == ("perm-security-18", "perm-security-17")


def test_one_refused_sector_is_excluded_without_forcing_every_other_sector_to_cash():
    value = _input()
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    position = value.session_axis.index(subject.DECISION_START_SESSION)
    axis = (subject.PRIMARY_SOURCE_VIEW_ID, subject.PRIMARY_SCORE_ARM)
    surviving_scores = {
        f"perm-security-{index:02d}": Decimal(index)
        for index in range(10, 20)
    }

    runtime._after_score_cross_section(
        position,
        value.memberships,
        {axis: surviving_scores},
        {axis: 10},
    )

    selected, matched = runtime._decisions[subject.DECISION_START_SESSION]
    assert selected == ("perm-security-19",)
    assert matched == tuple(sorted(surviving_scores))
    assert runtime._sector_refused_decision_count == 1


def test_completed_stock_portfolio_is_aggregate_only_and_primary_cost_only():
    runtime = _complete(_input())
    summary = runtime.aggregate_summary()
    statistics = runtime.custom_summary_statistics()

    assert summary["status"] == "PRELIMINARY_ACCEPTED_RISK_STOCK_PORTFOLIO"
    assert summary["decision_session_count"] > 250
    assert 200 < summary["signal_selected_decision_count"] <= summary["decision_session_count"]
    assert summary["sector_refused_decision_count"] == 0
    assert summary["invested_return_session_count"] > 1000
    assert summary["rebalance_execution_count"] == summary["decision_session_count"]
    assert summary["full_target_execution_count"] == 0
    assert summary["underfilled_target_execution_count"] == summary[
        "rebalance_execution_count"
    ]
    assert summary["matched_rebalance_execution_count"] == summary[
        "rebalance_execution_count"
    ]
    assert summary["matched_target_met_execution_count"] == summary[
        "matched_rebalance_execution_count"
    ]
    assert summary["matched_underfilled_target_execution_count"] == 0
    assert Decimal(summary["mean_executed_target_gross_exposure"]) == Decimal(
        "0.0392"
    )
    assert Decimal(
        summary["matched_mean_executed_target_gross_exposure"]
    ) == Decimal("0.0392")
    assert Decimal("1.5") < Decimal(summary["mean_selected_name_count"]) <= 2
    assert Decimal(summary["average_holding_count"]) > 0
    assert summary["terminal_payoff_applied"] is False
    assert summary["membership_end_liquidation_is_terminal_payoff"] is False
    assert summary["membership_end_zero_recovery_count"] == 0
    assert summary["partial_rebalance_decision_count"] == 0
    assert summary["stale_position_deferral_count"] == 0
    assert summary["mean_locked_gross_at_partial_decisions"] == "0"
    assert summary["locked_exposure_over_target_count"] == 0
    assert summary["matched_partial_rebalance_decision_count"] == 0
    assert summary["matched_stale_position_deferral_count"] == 0
    assert summary["matched_mean_locked_gross_at_partial_decisions"] == "0"
    assert summary["matched_locked_exposure_over_target_count"] == 0
    assert summary["named_figi_resolution_refusal_count"] == 0
    assert summary["economic_portfolio_evaluation"] is True
    assert summary["orders"] is False
    assert summary["trading"] is False
    assert tuple(sorted(statistics)) == (
        *subject.expected_custom_summary_statistic_names(),
    )
    cells = summary["portfolio_cells"]
    assert len(cells) == 1
    assert cells[0]["cost_bps_per_side"] == subject.PRIMARY_COST_BPS
    assert cells[0]["primary_cost_scenario"] is True
    assert Decimal(cells[0]["cumulative_return"]) > 0
    for cell in cells:
        with localcontext(base._context()):
            expected_matched_difference = +(
                Decimal(cell["cumulative_return"])
                - Decimal(cell["matched_eligible_stock_cumulative_return"])
            )
            expected_spy_difference = +(
                Decimal(cell["cumulative_return"])
                - Decimal(cell["spy_cumulative_return"])
            )
        assert Decimal(cell["cumulative_return_minus_matched"]) == (
            expected_matched_difference
        )
        assert Decimal(cell["cumulative_return_minus_spy"]) == (
            expected_spy_difference
        )
    with localcontext(base._context()):
        expected_wealth = Decimal(1)
        for _index in range(cells[0]["return_session_count"] - 1):
            expected_wealth = +(expected_wealth * Decimal("1.0002"))
        expected_spy = +(expected_wealth - Decimal(1))
    assert (
        abs(Decimal(cells[0]["spy_cumulative_return"]) - expected_spy)
        <= Decimal("1e-48")
    )
    assert all(
        cell["status"]
        == "PRELIMINARY_DESCRIPTIVE_AVAILABLE_WITH_EXPOSURE_UNDERFILL"
        and cell["exposure_underfill_present"] is True
        for cell in cells
    )
    assert all(
        cell["return_metric_conditioning"] == "no_price_proxy"
        and cell["risk_metrics_are_price_proxy_conditioned"] is False
        for cell in cells
    )
    assert abs(
        Decimal(cells[0]["average_cash_weight"])
        - Decimal(cells[0]["matched_average_cash_weight"])
    ) < Decimal("0.01")
    assert all(len(value) <= 4096 for value in statistics.values())
    assert len(statistics["ARV2_STOCK_PORTFOLIO_META"]) <= 3072
    metadata = json.loads(statistics["ARV2_STOCK_PORTFOLIO_META"])
    assert "profile" not in metadata
    assert metadata["profile_id"] == subject.PROFILE_ID
    assert metadata["profile_sha256"] == subject._PROFILE["profile_sha256"]


def test_matched_comparator_freezes_decision_weights_and_leaves_failed_entry_cash():
    value = _input()
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    position = value.session_axis.index(subject.DECISION_START_SESSION)
    history_position = runtime._history_session_positions[
        subject.DECISION_START_SESSION
    ]
    desired = tuple(
        f"perm-security-{index:02d}" for index in range(20)
    )
    for security_id in desired[:-1]:
        runtime._history_prices[history_position][
            runtime._history_security_positions[security_id]
        ] = "100"
    account = subject._Account("matched")

    targets = runtime._targets(account, desired, position)

    expected_weight = subject.TARGET_GROSS_EXPOSURE / Decimal(len(desired))
    assert len(targets) == len(desired) - 1
    assert set(targets.values()) == {expected_weight}
    assert sum(targets.values(), Decimal(0)) == Decimal("0.931")
    assert account.entry_price_refusal_count == 1


def test_matched_only_entry_failure_is_disclosed_as_exposure_underfill():
    value = _input(security_count=500)
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    position = value.session_axis.index(subject.DECISION_START_SESSION)
    history_position = runtime._history_session_positions[
        subject.DECISION_START_SESSION
    ]
    matched_desired = tuple(
        f"perm-security-{index:03d}" for index in range(500)
    )
    signal_desired = matched_desired[-subject.MAXIMUM_HOLDINGS:]
    missing_matched_only_name = matched_desired[0]
    for security_id in matched_desired[1:]:
        runtime._history_prices[history_position][
            runtime._history_security_positions[security_id]
        ] = "100"
    signal = subject._Account("signal")
    matched = subject._Account("matched")

    signal_gross = runtime._advance_account(
        signal, position, signal_desired
    )
    matched_gross = runtime._advance_account(
        matched,
        position,
        matched_desired,
        target_gross=signal_gross,
    )

    assert signal_gross == subject.TARGET_GROSS_EXPOSURE
    assert signal.full_target_execution_count == 1
    assert signal.underfilled_target_execution_count == 0
    assert matched.entry_price_refusal_count == 1
    assert matched.full_target_execution_count == 0
    assert matched.underfilled_target_execution_count == 1
    assert matched_gross < signal_gross
    assert missing_matched_only_name not in matched.weights
    assert sum(matched.weights.values(), Decimal(0)) == Decimal("0.97804")
    signal.invested_return_session_count = subject.MINIMUM_INVESTED_RETURN_SESSIONS
    assert runtime._cell_status(signal, matched, 1254) == (
        "PRELIMINARY_DESCRIPTIVE_AVAILABLE_WITH_EXPOSURE_UNDERFILL"
    )
    for account in (signal, matched):
        for accumulator in account.accumulators.values():
            accumulator.returns.append(Decimal(0))
    assert all(
        runtime._cell(cost, signal, matched, Decimal(1), 1254)[
            "exposure_underfill_present"
        ]
        is True
        for cost in subject.COST_BPS_SCENARIOS
    )


def test_matched_nondivisor_name_count_preserves_exact_requested_gross():
    value = _input()
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    position = value.session_axis.index(subject.DECISION_START_SESSION)
    history_position = runtime._history_session_positions[
        subject.DECISION_START_SESSION
    ]
    desired = tuple(f"perm-security-{index:02d}" for index in range(3))
    for security_id in desired:
        runtime._history_prices[history_position][
            runtime._history_security_positions[security_id]
        ] = "100"

    targets = runtime._targets(
        subject._Account("matched"),
        desired,
        position,
        target_gross=subject.TARGET_GROSS_EXPOSURE,
    )

    with localcontext(base._context()):
        assert +base._stable_sum(targets.values()) == subject.TARGET_GROSS_EXPOSURE
    assert max(targets.values()) - min(targets.values()) <= Decimal("1e-49")


def test_partial_rebalance_locks_exact_drifted_weight_and_trades_only_remainder():
    value = _input()
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    stale = "perm-security-18"
    tradable = "perm-security-19"
    newcomer = "perm-security-17"
    position = value.session_axis.index("2021-01-12")
    history_position = runtime._history_session_positions["2021-01-12"]
    runtime._history_prices[history_position][
        runtime._history_security_positions[tradable]
    ] = "110"
    runtime._history_prices[history_position][
        runtime._history_security_positions[newcomer]
    ] = "100"
    account = subject._Account(
        "matched",
        weights={stale: Decimal("0.4"), tradable: Decimal("0.4")},
        marks={stale: Decimal("100"), tradable: Decimal("100")},
    )

    executed_gross = runtime._advance_account(
        account,
        position,
        (stale, tradable, newcomer),
        target_gross=subject.TARGET_GROSS_EXPOSURE,
    )

    with localcontext(base._context()):
        gross_multiplier = Decimal("1.04")
        expected_locked = +(Decimal("0.4") / gross_multiplier)
        expected_tradable_pretrade = +(
            Decimal("0.4") * Decimal("1.1") / gross_multiplier
        )
        expected_unlocked = +(
            (subject.TARGET_GROSS_EXPOSURE - expected_locked) / Decimal(2)
        )
        expected_turnover = +(
            abs(expected_unlocked - expected_tradable_pretrade)
            + expected_unlocked
        )
        expected_net_return = +(
            Decimal("0.04")
            - Decimal("0.001") * expected_turnover
        )
    assert executed_gross == subject.TARGET_GROSS_EXPOSURE
    assert account.weights == {
        stale: expected_locked,
        tradable: expected_unlocked,
        newcomer: expected_unlocked,
    }
    assert account.marks == {
        stale: Decimal("100"),
        tradable: Decimal("110"),
        newcomer: Decimal("100"),
    }
    assert account.turnover_sum == expected_turnover
    assert account.accumulators[10].returns == [expected_net_return]
    assert account.partial_rebalance_decision_count == 1
    assert account.stale_position_deferral_count == 1
    assert account.locked_gross_sum_at_partial_decisions == expected_locked


def test_stale_position_recovery_books_cumulative_return_exactly_once():
    value = _input()
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    security_id = "perm-security-19"
    stale_position = value.session_axis.index("2021-01-12")
    recovery_position = value.session_axis.index("2021-01-13")
    unchanged_position = value.session_axis.index("2021-01-14")
    for position in (recovery_position, unchanged_position):
        session = value.session_axis[position]
        history_position = runtime._history_session_positions[session]
        runtime._history_prices[history_position][
            runtime._history_security_positions[security_id]
        ] = "120"
    account = subject._Account(
        "signal",
        weights={security_id: Decimal("0.4")},
        marks={security_id: Decimal("100")},
    )

    runtime._advance_account(account, stale_position, None)
    runtime._advance_account(account, recovery_position, None)
    recovered_weight = account.weights[security_id]
    runtime._advance_account(account, unchanged_position, None)
    with localcontext(base._context()):
        expected_recovered_weight = +(
            Decimal("0.4") * Decimal("1.2") / Decimal("1.08")
        )

    assert account.accumulators[10].returns == [
        Decimal(0),
        Decimal("0.08"),
        Decimal(0),
    ]
    assert recovered_weight == expected_recovered_weight
    assert account.weights[security_id] == recovered_weight
    assert account.marks[security_id] == Decimal("120")
    assert account.turnover_sum == 0
    assert account.stale_mark_session_count == 1


def test_locked_gross_above_target_is_preserved_without_new_trades():
    value = _input()
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    stale = "perm-security-18"
    newcomer = "perm-security-19"
    position = value.session_axis.index("2021-01-12")
    history_position = runtime._history_session_positions["2021-01-12"]
    runtime._history_prices[history_position][
        runtime._history_security_positions[newcomer]
    ] = "100"
    account = subject._Account(
        "matched",
        weights={stale: Decimal("0.99")},
        marks={stale: Decimal("100")},
    )

    executed_gross = runtime._advance_account(
        account,
        position,
        (newcomer,),
        target_gross=subject.TARGET_GROSS_EXPOSURE,
    )

    assert executed_gross == Decimal("0.99")
    assert account.weights == {stale: Decimal("0.99")}
    assert account.marks == {stale: Decimal("100")}
    assert account.turnover_sum == 0
    assert account.partial_rebalance_decision_count == 1
    assert account.stale_position_deferral_count == 1
    assert account.locked_exposure_over_target_count == 1
    assert account.full_target_execution_count == 0
    assert account.underfilled_target_execution_count == 0


def test_locked_nonselected_signal_name_consumes_one_holdings_slot():
    value = _input(security_count=64)
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    stale = "perm-security-00"
    desired = tuple(f"perm-security-{index:02d}" for index in range(14, 64))
    position = value.session_axis.index("2021-01-12")
    history_position = runtime._history_session_positions["2021-01-12"]
    for security_id in desired:
        runtime._history_prices[history_position][
            runtime._history_security_positions[security_id]
        ] = "100"
    account = subject._Account(
        "signal",
        weights={stale: subject.STOCK_WEIGHT_CAP},
        marks={stale: Decimal("100")},
    )

    runtime._advance_account(account, position, desired)

    assert len(account.weights) == subject.MAXIMUM_HOLDINGS
    assert stale in account.weights
    assert tuple(security_id for security_id in desired if security_id in account.weights) == (
        desired[: subject.MAXIMUM_HOLDINGS - 1]
    )
    assert desired[-1] not in account.weights
    assert sum(account.weights.values()) <= subject.TARGET_GROSS_EXPOSURE


def test_zero_signal_exposure_does_not_create_zero_weight_matched_holdings():
    value = _input()
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    position = value.session_axis.index(subject.DECISION_START_SESSION)
    history_position = runtime._history_session_positions[
        subject.DECISION_START_SESSION
    ]
    desired = tuple(
        f"perm-security-{index:02d}" for index in range(20)
    )
    for security_id in desired:
        runtime._history_prices[history_position][
            runtime._history_security_positions[security_id]
        ] = "100"
    account = subject._Account("matched")

    executed_gross = runtime._advance_account(
        account,
        position,
        desired,
        target_gross=Decimal(0),
    )

    assert executed_gross == 0
    assert account.weights == {}
    assert account.marks == {}
    assert account.holding_count_sum == 0
    assert account.selected_execution_count == 0
    assert account.full_target_execution_count == 1
    assert account.underfilled_target_execution_count == 0


def test_missing_held_mark_is_carried_while_tradable_positions_rebalance():
    value = _input()
    omission = ("perm-security-19", "2021-01-12")
    runtime = _complete(value, omissions=frozenset((omission,)))
    summary = runtime.aggregate_summary()

    assert summary["stale_mark_session_count"] == 1
    assert summary["deferred_rebalance_count"] == 0
    assert summary["rebalance_execution_count"] == 261
    assert summary["partial_rebalance_decision_count"] == 1
    assert summary["stale_position_deferral_count"] == 1
    assert Decimal(summary["mean_locked_gross_at_partial_decisions"]) > 0
    assert summary["membership_end_liquidation_count"] == 0
    assert all(
        cell["status"]
        == "PRELIMINARY_DESCRIPTIVE_AVAILABLE_WITH_STALE_MARK_PROXY"
        for cell in summary["portfolio_cells"]
    )
    assert all(
        cell["return_metric_conditioning"]
        == "conditioned_on_stale_mark_path"
        and cell["risk_metrics_are_price_proxy_conditioned"] is True
        for cell in summary["portfolio_cells"]
    )


def test_two_missing_held_marks_count_one_partial_decision_and_two_deferrals():
    value = _input()
    omissions = frozenset(
        (
            ("perm-security-18", "2021-01-12"),
            ("perm-security-19", "2021-01-12"),
        )
    )
    runtime = _complete(value, omissions=omissions)
    summary = runtime.aggregate_summary()

    assert summary["stale_mark_session_count"] == 1
    assert summary["matched_stale_mark_session_count"] == 1
    assert summary["deferred_rebalance_count"] == 0
    assert summary["matched_deferred_rebalance_count"] == 0
    assert summary["partial_rebalance_decision_count"] == 1
    assert summary["matched_partial_rebalance_decision_count"] == 1
    assert summary["stale_position_deferral_count"] == 2
    assert summary["matched_stale_position_deferral_count"] == 2


def test_matched_only_stale_name_partially_rebalances_only_the_comparator():
    value = _input()
    runtime = _complete(
        value,
        omissions=frozenset((("perm-security-00", "2021-01-12"),)),
    )
    summary = runtime.aggregate_summary()

    assert summary["stale_mark_session_count"] == 0
    assert summary["deferred_rebalance_count"] == 0
    assert summary["rebalance_execution_count"] == 261
    assert summary["matched_stale_mark_session_count"] == 1
    assert summary["matched_deferred_rebalance_count"] == 0
    assert summary["matched_rebalance_execution_count"] == 261
    assert summary["matched_partial_rebalance_decision_count"] == 1
    assert summary["matched_stale_position_deferral_count"] == 1
    assert Decimal(
        summary["matched_mean_locked_gross_at_partial_decisions"]
    ) > 0
    assert all(
        cell["status"]
        == "PRELIMINARY_DESCRIPTIVE_AVAILABLE_WITH_STALE_MARK_PROXY"
        and cell["risk_metrics_are_price_proxy_conditioned"] is True
        for cell in summary["portfolio_cells"]
    )


def test_membership_end_missing_open_uses_zero_recovery_lower_bound():
    value = _input(
        membership_end="2025-12-15", membership_end_security_index=0
    )
    omission = ("perm-security-00", "2025-12-15")
    runtime = _complete(value, omissions=frozenset((omission,)))
    summary = runtime.aggregate_summary()

    assert summary["membership_end_liquidation_count"] == 1
    assert summary["membership_end_zero_recovery_count"] == 1
    assert summary["stale_mark_session_count"] == 0
    assert summary["membership_end_liquidation_is_terminal_payoff"] is False
    assert summary["terminal_payoff_applied"] is False
    assert all(
        cell["status"]
        == "PRELIMINARY_DESCRIPTIVE_LOWER_BOUND_WITH_ZERO_RECOVERY"
        for cell in summary["portfolio_cells"]
    )
    assert all(
        cell["return_metric_conditioning"]
        == "conditioned_on_zero_recovery_lower_bound_and_possible_stale_mark_path"
        and cell["risk_metrics_are_price_proxy_conditioned"] is True
        for cell in summary["portfolio_cells"]
    )


def test_zero_recovery_lower_bound_books_the_held_weight_as_a_loss():
    value = _input(membership_end="2021-01-11")
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    security_id = "perm-security-19"
    position = value.session_axis.index("2021-01-11")
    account = subject._Account(
        "signal",
        weights={security_id: subject.STOCK_WEIGHT_CAP},
        marks={security_id: Decimal("100")},
    )

    runtime._advance_account(account, position, None)

    assert account.weights == {}
    assert account.accumulators[10].returns == [-subject.STOCK_WEIGHT_CAP]
    assert account.accumulators[10].wealth == Decimal(1) - subject.STOCK_WEIGHT_CAP
    assert account.membership_end_zero_recovery_count == 1


def test_membership_end_forces_liquidation_and_refuses_reentry_even_with_open():
    value = _input(membership_end="2021-01-11")
    runtime = subject.StockPortfolioEvaluationRuntime(
        value,
        profile_id=subject.PROFILE_ID,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
    )
    security_id = "perm-security-19"
    position = value.session_axis.index("2021-01-11")
    history_position = runtime._history_session_positions["2021-01-11"]
    runtime._history_prices[history_position][
        runtime._history_security_positions[security_id]
    ] = "101"
    account = subject._Account(
        "signal",
        weights={security_id: subject.STOCK_WEIGHT_CAP},
        marks={security_id: Decimal("100")},
    )

    runtime._advance_account(account, position, (security_id,))

    assert account.weights == {}
    assert account.marks == {}
    assert account.membership_end_liquidation_count == 1
    assert account.membership_end_zero_recovery_count == 0
    assert account.membership_end_entry_refusal_count == 1
    assert account.turnover_sum > 0
    with localcontext(base._context()):
        gross_return = +(subject.STOCK_WEIGHT_CAP * Decimal("0.01"))
        expected_net = +(
            gross_return
            - Decimal("0.001") * account.turnover_sum
        )
        expected_wealth = +(Decimal(1) + expected_net)
        gross_wealth = +(Decimal(1) + gross_return)
    assert account.accumulators[10].wealth == expected_wealth
    assert account.accumulators[10].wealth < gross_wealth


def test_base_runtime_hook_is_noop_and_preserves_existing_summary_shape():
    assert (
        base.PreliminaryRatingEvaluationRuntime._after_score_cross_section(
            object(), 0, (), {}, {}
        )
        is None
    )


def test_one_held_name_going_untradable_does_not_freeze_matched_comparator():
    """ARV2R85-001: one locked name must not freeze account-wide rebalancing."""
    value = _input()
    later = tuple(
        session
        for session in value.session_axis
        if "2021-02-01" <= session <= "2025-12-31"
    )
    # perm-security-00 is held by the matched comparator but never selected
    # into the signal sleeve, and it prices normally until 2021-02-01.
    runtime = _complete(
        value,
        omissions=frozenset(("perm-security-00", session) for session in later),
    )
    summary = runtime.aggregate_summary()

    # The signal sleeve is untouched: every weekly decision still executes.
    assert summary["rebalance_execution_count"] == 261
    assert summary["deferred_rebalance_count"] == 0
    assert summary["stale_mark_session_count"] == 0

    # The stale name remains locked, but all 261 comparator decisions execute.
    assert summary["matched_rebalance_execution_count"] == 261
    assert summary["matched_deferred_rebalance_count"] == 0
    assert summary["matched_partial_rebalance_decision_count"] == 257
    assert summary["matched_stale_position_deferral_count"] == 257
    assert summary["matched_stale_mark_session_count"] == 1236
    assert Decimal(
        summary["matched_mean_locked_gross_at_partial_decisions"]
    ) > 0

    # The stale position still makes the return proxy-conditioned, even though
    # it no longer stops the rest of the matched comparator from rebalancing.
    assert all(
        cell["risk_metrics_are_price_proxy_conditioned"] is True
        for cell in summary["portfolio_cells"]
    )
