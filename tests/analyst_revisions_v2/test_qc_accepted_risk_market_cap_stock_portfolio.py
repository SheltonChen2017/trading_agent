import hashlib
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_evaluator as subject,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as base,
)


def _sessions():
    return tuple(
        session.isoformat()
        for session in trading_sessions(
            date(2013, 1, 2), date(2026, 4, 30)
        )
    )


def _input():
    sessions = _sessions()
    session_rows = tuple(
        {
            "schema": base.SESSION_SCHEMA,
            "session_index": index,
            "session": session,
        }
        for index, session in enumerate(sessions)
    )
    memberships = tuple(
        base.build_membership_record(
            security_id=f"perm-security-{index:02d}",
            first_session_index=0,
            last_session_index_exclusive=len(sessions),
            sector_id="sector-technology",
        )
        for index in range(20)
    )
    contributions = []
    contribution_sessions = tuple(
        sessions.index(
            next(
                session
                for session in sessions
                if session.startswith(f"{year}-")
            )
        )
        for year in range(2018, 2026)
    )
    for view in base.SOURCE_VIEW_IDS:
        for contribution_session in contribution_sessions:
            for index in range(20):
                delta = Fraction(index - 10 if index < 10 else index - 9, 10)
                contributions.append(
                    base.build_contribution_record(
                        source_view_id=view,
                        security_id=f"perm-security-{index:02d}",
                        eligible_session_index=contribution_session,
                        institution_id=f"firm-{index:02d}",
                        common_event_id=(
                            f"event-{contribution_session}-{index:02d}"
                        ),
                        rating_action=(
                            "downgrades" if index < 10 else "upgrades"
                        ),
                        firm_delta=delta,
                        global_delta=delta / 2,
                        source_row_sha256=hashlib.sha256(
                            f"source-{view}-{contribution_session}-{index}".encode(
                                "ascii"
                            )
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
        signal_seed_contributions_per_callback=20_000,
    )
    return base.load_preliminary_rating_input(
        manifest,
        session_rows,
        memberships,
        tuple(contributions),
    )


def _caps(value, profile_id, security_ids=None):
    if security_ids is None:
        security_ids = tuple(
            sorted(item.security_id for item in value.memberships)
        )
    cap_by_security = {
        security_id: Decimal(index + 1)
        for index, security_id in enumerate(security_ids)
    }
    return {
        session: dict(cap_by_security)
        for session in subject.decision_sessions_for_input(value, profile_id)
    }


_DEFAULT_CAPS = object()


def _runtime(
    value,
    *,
    profile_id=subject.QQQ_2021_2025_PROFILE_ID,
    caps=_DEFAULT_CAPS,
):
    return subject.MarketCapStockPortfolioEvaluationRuntime(
        value,
        profile_id=profile_id,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
        eligibility_market_caps_by_decision_session=(
            _caps(value, profile_id) if caps is _DEFAULT_CAPS else caps
        ),
    )


def _history_loader(value, *, omissions=frozenset(), opening_jump=False):
    positions = {
        session: index for index, session in enumerate(value.session_axis)
    }

    def load(request):
        rows = []
        begin = positions[request.start_session]
        end = positions[request.end_session]
        for security_id in request.security_ids:
            for session in value.session_axis[begin : end + 1]:
                if (security_id, session) in omissions:
                    continue
                price = Decimal(100)
                if (
                    opening_jump
                    and security_id != value.benchmark_security_id
                    and session > "2021-01-04"
                ):
                    price = Decimal(200)
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
    profile_id=subject.QQQ_2021_2025_PROFILE_ID,
    caps=_DEFAULT_CAPS,
    omissions=frozenset(),
    opening_jump=False,
):
    runtime = _runtime(value, profile_id=profile_id, caps=caps)
    loader = _history_loader(
        value,
        omissions=omissions,
        opening_jump=opening_jump,
    )
    while runtime.phase is not base.RuntimePhase.COMPLETED:
        runtime.run_callback(loader)
    return runtime


def test_six_exact_profiles_cover_both_proxies_and_fixed_periods():
    assert subject.PROFILE_IDS == (
        subject.QQQ_2021_2025_PROFILE_ID,
        subject.SPY_2021_2025_PROFILE_ID,
        subject.QQQ_2019_2023_PROFILE_ID,
        subject.SPY_2019_2023_PROFILE_ID,
        subject.QQQ_2023_2025_PROFILE_ID,
        subject.SPY_2023_2025_PROFILE_ID,
    )
    assert subject.ALL_PROFILE_IDS == subject.PROFILE_IDS
    assert subject.QQQ_PROFILE_IDS == subject.PROFILE_IDS[::2]
    assert subject.SPY_PROFILE_IDS == subject.PROFILE_IDS[1::2]
    expected = {
        subject.QQQ_2021_2025_PROFILE_ID: ("QQQ", 1_255, 261),
        subject.SPY_2021_2025_PROFILE_ID: ("SPY", 1_255, 261),
        subject.QQQ_2019_2023_PROFILE_ID: ("QQQ", 1_258, 261),
        subject.SPY_2019_2023_PROFILE_ID: ("SPY", 1_258, 261),
        subject.QQQ_2023_2025_PROFILE_ID: ("QQQ", 752, 157),
        subject.SPY_2023_2025_PROFILE_ID: ("SPY", 752, 157),
    }
    for profile_id, (ticker, sessions, decisions) in expected.items():
        profile = subject.require_profile(profile_id)
        digest = profile.pop("profile_sha256")
        assert subject._sha(profile) == digest
        assert profile["expected_session_count"] == sessions
        assert profile["expected_decision_session_count"] == decisions
        assert profile["r055_score_rule"] == "exact_unchanged_R055_cross_section"
        assert profile["target_gross_exposure"] == "0.98"
        assert profile["execution_timing"] == "next_authenticated_session_open"
        assert profile["cost_bps_per_side"] == [0, 5, 10, 20]
        assert profile["leverage"] is False
        assert subject.constituent_etf_tickers_for_profile(profile_id) == (
            ticker,
        )


def test_profiles_are_detached_and_unknown_profile_refuses():
    profile = subject.require_profile(subject.QQQ_2021_2025_PROFILE_ID)
    profile["cost_bps_per_side"].append(99)
    assert subject.require_profile(subject.QQQ_2021_2025_PROFILE_ID)[
        "cost_bps_per_side"
    ] == [0, 5, 10, 20]
    with pytest.raises(
        subject.MarketCapStockPortfolioEvaluationError,
        match="exact fixed profile",
    ):
        subject.require_profile("unknown")


def test_decision_schedule_and_history_request_bind_each_fixed_window():
    value = _input()
    for profile_id in subject.PROFILE_IDS:
        profile = subject.require_profile(profile_id)
        decisions = subject.decision_sessions_for_input(value, profile_id)
        assert len(decisions) == profile["expected_decision_session_count"]
        runtime = _runtime(value, profile_id=profile_id)
        assert len(runtime._evaluation_positions) == profile["expected_session_count"]
        request = runtime._history_request(0)
        assert request.start_session == profile["evaluation_start_session"]
        expected_end = value.session_axis[
            value.session_axis.index(profile["evaluation_end_session"])
            + max(base.HORIZONS)
        ]
        assert request.end_session == expected_end


@pytest.mark.parametrize(
    ("replacement", "message"),
    (
        (None, "must be an exact dict"),
        (Decimal(0), "positive finite Decimal"),
        (Decimal("NaN"), "positive finite Decimal"),
        (Decimal("Infinity"), "positive finite Decimal"),
        (Decimal("1e1000"), "positive finite Decimal"),
        (1.0, "positive finite Decimal"),
    ),
)
def test_market_cap_map_refuses_wrong_container_or_value(replacement, message):
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    caps = _caps(value, profile_id)
    if replacement is None:
        caps = None
    else:
        first_session = min(caps)
        caps[first_session]["perm-security-00"] = replacement
    with pytest.raises(
        subject.MarketCapStockPortfolioEvaluationError,
        match=message,
    ):
        _runtime(value, profile_id=profile_id, caps=caps)


def test_market_cap_map_requires_every_decision_and_input_security_ids():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    caps = _caps(value, profile_id)
    caps.pop(min(caps))
    with pytest.raises(
        subject.MarketCapStockPortfolioEvaluationError,
        match="sessions are not exhaustive",
    ):
        _runtime(value, profile_id=profile_id, caps=caps)
    caps = _caps(value, profile_id)
    caps[min(caps)]["not-an-input-security"] = Decimal(1)
    with pytest.raises(
        subject.MarketCapStockPortfolioEvaluationError,
        match="escaped input securities",
    ):
        _runtime(value, profile_id=profile_id, caps=caps)


def test_exact_r055_intersection_precedes_ranking_and_caller_mutation():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    eligible = tuple(f"perm-security-{index:02d}" for index in range(9))
    caps = _caps(value, profile_id, eligible)
    runtime = _runtime(value, profile_id=profile_id, caps=caps)
    first = subject.decision_sessions_for_input(value, profile_id)[0]
    caps[first].clear()
    position = value.session_axis.index(first)
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
    decision = runtime._decisions[first]
    assert decision.eligible == eligible
    assert decision.selected == ("perm-security-08",)


def test_runtime_reuses_r055_state_scoring_without_overriding_it():
    assert issubclass(
        subject.MarketCapStockPortfolioEvaluationRuntime,
        base.PreliminaryRatingEvaluationRuntime,
    )
    assert (
        subject.MarketCapStockPortfolioEvaluationRuntime._score_cross_section
        is base.PreliminaryRatingEvaluationRuntime._score_cross_section
    )
    assert (
        subject.MarketCapStockPortfolioEvaluationRuntime._apply_contribution
        is base.PreliminaryRatingEvaluationRuntime._apply_contribution
    )
    assert subject.PRIMARY_SOURCE_VIEW_ID == base.SOURCE_VIEW_IDS[1]
    assert subject.PRIMARY_SCORE_ARM == "firm_specific"


def test_small_universe_selected_and_matched_books_each_reach_exact_98_percent():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    eligible = tuple(f"perm-security-{index:02d}" for index in range(9))
    runtime = _runtime(
        value,
        profile_id=profile_id,
        caps=_caps(value, profile_id, eligible),
    )
    first = subject.decision_sessions_for_input(value, profile_id)[0]
    position = value.session_axis.index(first)
    axis = (subject.PRIMARY_SOURCE_VIEW_ID, subject.PRIMARY_SCORE_ARM)
    scores = {
        security_id: Decimal(index)
        for index, security_id in enumerate(eligible)
    }
    runtime._after_score_cross_section(
        position,
        value.memberships,
        {axis: scores},
        {axis: 0},
    )
    decision = runtime._decisions[first]
    runtime._price = lambda _security_id, _position: Decimal(100)
    selected_account = subject._Account("selected")
    matched_account = subject._Account("matched")
    selected = runtime._targets(
        selected_account,
        decision,
        decision.selected,
        position + 1,
        {},
    )
    matched = runtime._targets(
        matched_account,
        decision,
        decision.eligible,
        position + 1,
        {},
    )
    assert selected == {"perm-security-08": Decimal("0.98")}
    assert base._stable_sum(matched.values()) == Decimal("0.98")
    assert matched["perm-security-08"] / matched["perm-security-00"] == 9


def test_missing_entry_is_counted_and_remaining_caps_renormalize_to_target():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    eligible = tuple(f"perm-security-{index:02d}" for index in range(20))
    runtime = _runtime(value, profile_id=profile_id)
    first = subject.decision_sessions_for_input(value, profile_id)[0]
    position = value.session_axis.index(first)
    axis = (subject.PRIMARY_SOURCE_VIEW_ID, subject.PRIMARY_SCORE_ARM)
    scores = {
        security_id: Decimal(index)
        for index, security_id in enumerate(eligible)
    }
    runtime._after_score_cross_section(
        position,
        value.memberships,
        {axis: scores},
        {axis: 0},
    )
    decision = runtime._decisions[first]
    runtime._price = lambda security_id, _position: (
        None if security_id == "perm-security-19" else Decimal(100)
    )
    account = subject._Account("selected")
    targets = runtime._targets(
        account,
        decision,
        decision.selected,
        position + 1,
        {},
    )
    assert targets == {"perm-security-18": Decimal("0.98")}
    assert account.entry_price_refusal_count == 1


def test_selected_and_matched_targets_are_market_cap_proportional():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    runtime = _runtime(value, profile_id=profile_id)
    first = subject.decision_sessions_for_input(value, profile_id)[0]
    position = value.session_axis.index(first)
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
    decision = runtime._decisions[first]
    runtime._price = lambda _security_id, _position: Decimal(100)
    selected = runtime._targets(
        subject._Account("selected"),
        decision,
        decision.selected,
        position + 1,
        {},
    )
    matched = runtime._targets(
        subject._Account("matched"),
        decision,
        decision.eligible,
        position + 1,
        {},
    )
    assert base._stable_sum(selected.values()) == Decimal("0.98")
    assert selected["perm-security-19"] / selected["perm-security-18"] == (
        Decimal(20) / Decimal(19)
    )
    assert matched["perm-security-19"] / matched["perm-security-00"] == 20


def test_stale_selected_holdings_preserve_the_fifty_name_cap():
    runtime = _runtime(_input())
    runtime._price = lambda _security_id, _position: Decimal(100)
    desired = tuple(f"candidate-{index:02d}" for index in range(50))
    decision = subject._Decision(
        selected=desired,
        eligible=desired,
        market_caps={security_id: Decimal(1) for security_id in desired},
    )
    targets = runtime._targets(
        subject._Account("selected"),
        decision,
        desired,
        0,
        {"stale-security": Decimal("0.01")},
    )
    assert len(targets) == subject.MAXIMUM_HOLDINGS
    assert "candidate-49" not in targets
    assert base._stable_sum(targets.values()) == Decimal("0.98")


def test_complete_result_has_four_costs_full_exposure_and_concentration_metrics():
    runtime = _complete(_input())
    summary = runtime.aggregate_summary()
    assert summary["r055_signal_rule_changed"] is False
    assert summary["decision_session_count"] == 261
    assert summary["portfolio_return_session_count"] == 1_254
    assert summary["mean_eligible_score_count"] == "20"
    assert summary["mean_selected_name_count"] == "2"
    for name in ("selected_aggregates", "matched_aggregates"):
        aggregate = summary[name]
        assert aggregate["rebalance_execution_count"] == 261
        assert aggregate["full_target_execution_count"] == 261
        assert aggregate["underfilled_target_execution_count"] == 0
        assert Decimal(aggregate["mean_executed_gross_exposure"]) == Decimal(
            "0.98"
        )
        assert Decimal(aggregate["minimum_executed_gross_exposure"]) == Decimal(
            "0.98"
        )
        assert Decimal(aggregate["maximum_executed_gross_exposure"]) == Decimal(
            "0.98"
        )
        assert Decimal(aggregate["mean_invested_weight_hhi"]) > 0
        assert Decimal(aggregate["mean_effective_holding_count"]) >= 1
    assert [
        cell["cost_bps_per_side"] for cell in summary["portfolio_cells"]
    ] == [0, 5, 10, 20]
    returns = [
        Decimal(cell["cumulative_return"])
        for cell in summary["portfolio_cells"]
    ]
    assert returns == [
        Decimal(0),
        Decimal("-0.00049"),
        Decimal("-0.00098"),
        Decimal("-0.00196"),
    ]
    statistics = runtime.custom_summary_statistics()
    assert tuple(statistics) == subject.expected_custom_summary_statistic_names(
        subject.QQQ_2021_2025_PROFILE_ID
    )
    assert all(len(value) <= 4096 for value in statistics.values())
    assert all(cell["leverage"] is False for cell in summary["portfolio_cells"])


def test_first_decision_executes_at_next_open_not_same_open():
    runtime = _complete(_input(), opening_jump=True)
    zero_cost = runtime.aggregate_summary()["portfolio_cells"][0]
    assert zero_cost["cost_bps_per_side"] == 0
    assert zero_cost["cumulative_return"] == "0"
    assert zero_cost["matched_eligible_stock_cumulative_return"] == "0"


def test_missing_eligibility_exit_uses_symmetric_zero_recovery():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    decisions = subject.decision_sessions_for_input(value, profile_id)
    caps = _caps(value, profile_id)
    for session in decisions[1:]:
        caps[session].pop("perm-security-19")
    exit_position = value.session_axis.index(decisions[1]) + 1
    exit_session = value.session_axis[exit_position]
    runtime = _complete(
        value,
        caps=caps,
        omissions=frozenset({("perm-security-19", exit_session)}),
    )
    summary = runtime.aggregate_summary()
    assert summary["selected_aggregates"][
        "eligibility_exit_zero_recovery_count"
    ] == 1
    assert summary["matched_aggregates"][
        "eligibility_exit_zero_recovery_count"
    ] == 1
    assert summary["portfolio_cells"][0]["status"] == (
        "PRELIMINARY_DESCRIPTIVE_ZERO_RECOVERY_SENSITIVITY"
    )


def test_missing_price_inside_eligibility_defers_only_stale_holding():
    value = _input()
    profile_id = subject.QQQ_2021_2025_PROFILE_ID
    decisions = subject.decision_sessions_for_input(value, profile_id)
    stale_position = value.session_axis.index(decisions[1]) + 1
    stale_session = value.session_axis[stale_position]
    runtime = _complete(
        value,
        omissions=frozenset({("perm-security-19", stale_session)}),
    )
    summary = runtime.aggregate_summary()
    for name in ("selected_aggregates", "matched_aggregates"):
        assert summary[name]["stale_mark_session_count"] == 1
        assert summary[name]["partial_rebalance_decision_count"] == 1
        assert summary[name]["eligibility_exit_zero_recovery_count"] == 0


def test_module_is_pure_and_does_not_import_old_giant_evaluator():
    source = open(subject.__file__, encoding="utf-8").read()
    assert "accepted_risk_stock_portfolio_evaluator" not in source
    for forbidden in (
        "requests",
        "urllib",
        "subprocess",
        "socket",
        "os.environ",
    ):
        assert forbidden not in source
