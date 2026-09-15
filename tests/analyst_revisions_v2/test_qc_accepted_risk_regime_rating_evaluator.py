import hashlib
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from data.exchange_calendar import trading_sessions

from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as r055,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_regime_rating_evaluator as subject,
)


PROFILE_ID = "arv2-stock-ic-2023-2025"
SECURITY_IDS = tuple(f"perm-security-{index:02d}" for index in range(21))


def _sessions():
    return tuple(
        session.isoformat()
        for session in trading_sessions(date(2013, 1, 2), date(2026, 4, 30))
    )


def _lineage():
    return {
        name: hashlib.sha256(name.encode("ascii")).hexdigest()
        for name in (
            "accepted_risk_input_pair_sha256",
            "security_master_admission_sha256",
            "firm_ontology_admission_sha256",
            "global_rating_map_sha256",
            "pre_normalized_contribution_source_sha256",
        )
    }


def _loaded_input(*, ended_security_id=None):
    sessions = _sessions()
    session_rows = tuple(
        {
            "schema": r055.SESSION_SCHEMA,
            "session_index": index,
            "session": session,
        }
        for index, session in enumerate(sessions)
    )
    decision = sessions.index("2023-01-03")
    memberships = tuple(
        r055.build_membership_record(
            security_id=security_id,
            first_session_index=0,
            last_session_index_exclusive=(
                decision + 1
                if security_id == ended_security_id
                else len(sessions)
            ),
            sector_id="sector-technology",
        )
        for security_id in SECURITY_IDS
    )
    eligible = sessions.index("2019-12-30")
    contributions = []
    for view in r055.SOURCE_VIEW_IDS:
        for index, security_id in enumerate(SECURITY_IDS[:12]):
            if index < 6:
                action = "downgrades"
                delta = Fraction(-(6 - index), 6)
            else:
                action = "upgrades"
                delta = Fraction(index - 5, 6)
            contributions.append(
                r055.build_contribution_record(
                    source_view_id=view,
                    security_id=security_id,
                    eligible_session_index=eligible,
                    institution_id=f"firm-{index:02d}",
                    common_event_id=f"event-{index:02d}",
                    rating_action=action,
                    firm_delta=delta,
                    global_delta=delta / 2,
                    source_row_sha256=hashlib.sha256(
                        f"source-{index}".encode("ascii")
                    ).hexdigest(),
                )
            )
    contribution_rows = tuple(contributions)
    manifest = r055.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=session_rows,
        membership_records=memberships,
        contribution_records=contribution_rows,
        source_lineage_sha256s=_lineage(),
        history_batch_security_count=64,
        scoring_sessions_per_callback=5,
        signal_seed_contributions_per_callback=24,
    )
    return r055.load_preliminary_rating_input(
        manifest, session_rows, memberships, contribution_rows
    )


def _observation(security_id, session, price):
    return r055.TotalReturnOpenObservation(
        r055.HISTORY_OBSERVATION_SCHEMA,
        security_id,
        session,
        Decimal(price),
    )


def _single_date_cell(
    *,
    named_refusals=(),
    omit=(),
    ended_security_id=None,
):
    value = _loaded_input(ended_security_id=ended_security_id)
    runtime = subject.RegimeRatingEvaluationRuntime(
        value,
        profile_id=PROFILE_ID,
        named_figi_resolution_refusals=named_refusals,
    )
    decision_position = value.session_axis.index("2023-01-03")
    exit_position = decision_position + 1
    decision_session = value.session_axis[decision_position]
    exit_session = value.session_axis[exit_position]
    request = runtime._history_request(0)
    observations = []
    for security_id in request.security_ids:
        index = (
            0
            if security_id == value.benchmark_security_id
            else SECURITY_IDS.index(security_id) + 1
        )
        for session, price in (
            (decision_session, "100"),
            (exit_session, str(100 + index)),
        ):
            if (security_id, session) not in omit:
                observations.append(_observation(security_id, session, price))
    runtime._accept_history(request, tuple(observations))
    for contribution_index in runtime._prestart_indices:
        runtime._apply_contribution(value.contributions[contribution_index])
    runtime._score_session(decision_position)
    cell = runtime._cells[(r055.SOURCE_VIEW_IDS[0], "firm_specific", 1)]
    result = runtime._cell_record(
        r055.SOURCE_VIEW_IDS[0], "firm_specific", 1, cell
    )
    runtime.abort()
    return result, decision_session, exit_session


def _complete_runtime(profile_id=PROFILE_ID):
    value = _loaded_input()
    runtime = subject.RegimeRatingEvaluationRuntime(
        value,
        profile_id=profile_id,
        named_figi_resolution_refusals=(),
    )
    positions = {session: index for index, session in enumerate(value.session_axis)}

    def loader(request):
        rows = []
        start = positions[request.start_session]
        end = positions[request.end_session]
        for security_id in request.security_ids:
            security_index = (
                0
                if security_id == value.benchmark_security_id
                else SECURITY_IDS.index(security_id) + 1
            )
            for offset, session in enumerate(value.session_axis[start : end + 1]):
                rows.append(
                    _observation(
                        security_id,
                        session,
                        100_000 + offset * security_index,
                    )
                )
        return tuple(rows)

    while runtime.phase is not subject.RuntimePhase.COMPLETED:
        runtime.run_callback(loader)
    return runtime


def test_only_three_exact_fixed_profiles_are_supported():
    assert subject.REGIME_PROFILE_IDS == (
        "arv2-stock-ic-2019-2023",
        "arv2-stock-ic-2023-2025",
        "arv2-stock-ic-2013-2019",
    )
    assert tuple(
        (
            subject.require_regime_profile(profile_id)["start_session"],
            subject.require_regime_profile(profile_id)["end_session"],
            subject.require_regime_profile(profile_id)["expected_session_count"],
        )
        for profile_id in subject.REGIME_PROFILE_IDS
    ) == (
        ("2019-01-02", "2023-12-29", 1_258),
        ("2023-01-03", "2025-12-31", 752),
        ("2013-01-02", "2019-12-31", 1_762),
    )
    for bad in (
        None,
        "2019-01-02..2023-12-29",
        "arv2-stock-ic-2019-2024",
    ):
        with pytest.raises(
            subject.RegimeRatingEvaluationError,
            match="one exact fixed profile id",
        ):
            subject.require_regime_profile(bad)
    with pytest.raises(
        subject.RegimeRatingEvaluationError,
        match="one exact fixed profile id",
    ):
        subject.RegimeRatingEvaluationRuntime(
            _loaded_input(),
            profile_id="arv2-stock-ic-2019-2024",
            named_figi_resolution_refusals=(),
        )


def test_profile_records_are_content_derived_and_returned_by_value():
    profile = subject.require_regime_profile(PROFILE_ID)
    semantic = {key: value for key, value in profile.items() if key != "profile_sha256"}
    assert profile["schema"] == subject.REGIME_PROFILE_SCHEMA
    assert profile["profile_sha256"] == r055._sha256(semantic)
    profile["start_session"] = "2024-01-02"
    assert subject.require_regime_profile(PROFILE_ID)["start_session"] == "2023-01-03"


def test_each_profile_evaluates_every_and_only_its_fixed_session():
    value = _loaded_input()
    for profile_id in subject.REGIME_PROFILE_IDS:
        profile = subject.require_regime_profile(profile_id)
        runtime = subject.RegimeRatingEvaluationRuntime(
            value,
            profile_id=profile_id,
            named_figi_resolution_refusals=(),
        )
        positions = runtime._evaluation_positions
        assert positions[0] == value.session_axis.index(profile["start_session"])
        assert positions[-1] == value.session_axis.index(profile["end_session"])
        assert positions == tuple(range(positions[0], positions[-1] + 1))
        assert len(positions) == profile["expected_session_count"]
        runtime.abort()


@pytest.mark.parametrize(
    ("case", "expected_field", "expected_count"),
    (
        (
            "benchmark_endpoint",
            "benchmark_endpoint_unavailable_pair_count",
            len(SECURITY_IDS),
        ),
        (
            "named_figi_refusal",
            "named_figi_resolution_refusal_pair_count",
            1,
        ),
        ("security_entry", "security_entry_unavailable_pair_count", 1),
        (
            "membership_ended_exit",
            "membership_ended_by_exit_with_exit_unavailable_pair_count",
            1,
        ),
        (
            "within_membership_exit",
            "within_membership_exit_unavailable_pair_count",
            1,
        ),
    ),
)
def test_each_missing_pair_category_is_isolated_and_reconciles(
    case, expected_field, expected_count
):
    probe = _loaded_input()
    decision = "2023-01-03"
    exit_session = probe.session_axis[probe.session_axis.index(decision) + 1]
    benchmark = probe.benchmark_security_id
    named_refusals = ()
    ended_security_id = None
    if case == "benchmark_endpoint":
        omit = ((benchmark, exit_session),)
    elif case == "named_figi_refusal":
        named_refusals = (SECURITY_IDS[0],)
        omit = ()
    elif case == "security_entry":
        omit = ((SECURITY_IDS[0], decision),)
    else:
        omit = ((SECURITY_IDS[0], exit_session),)
        if case == "membership_ended_exit":
            ended_security_id = SECURITY_IDS[0]
    cell, _decision, _exit = _single_date_cell(
        named_refusals=named_refusals,
        omit=omit,
        ended_security_id=ended_security_id,
    )
    counter_fields = (
        "benchmark_endpoint_unavailable_pair_count",
        "named_figi_resolution_refusal_pair_count",
        "security_entry_unavailable_pair_count",
        "membership_ended_by_exit_with_exit_unavailable_pair_count",
        "within_membership_exit_unavailable_pair_count",
    )
    assert cell[expected_field] == expected_count
    assert {
        field: cell[field] for field in counter_fields if field != expected_field
    } == {field: 0 for field in counter_fields if field != expected_field}
    assert sum(cell[field] for field in counter_fields) == cell[
        "missing_outcome_pair_count"
    ]
    assert cell["accepted_outcome_pair_count"] + cell[
        "missing_outcome_pair_count"
    ] == cell["eligible_score_row_count"]
    assert cell["missing_pair_counter_sum_matches_total"] is True


@pytest.mark.parametrize(
    ("higher_priority", "lower_priority", "expected_field"),
    (
        (
            "benchmark",
            "named",
            "benchmark_endpoint_unavailable_pair_count",
        ),
        (
            "named",
            "entry",
            "named_figi_resolution_refusal_pair_count",
        ),
        (
            "entry",
            "exit",
            "security_entry_unavailable_pair_count",
        ),
    ),
)
def test_overlapping_missing_conditions_follow_the_disclosed_precedence(
    higher_priority, lower_priority, expected_field
):
    value = _loaded_input()
    decision = "2023-01-03"
    exit_session = value.session_axis[value.session_axis.index(decision) + 1]
    security = SECURITY_IDS[0]
    named_refusals = (security,) if "named" in (higher_priority, lower_priority) else ()
    omit = []
    if "benchmark" in (higher_priority, lower_priority):
        omit.append((value.benchmark_security_id, exit_session))
    if "entry" in (higher_priority, lower_priority):
        omit.append((security, decision))
    if "exit" in (higher_priority, lower_priority):
        omit.append((security, exit_session))
    cell, _decision, _exit = _single_date_cell(
        named_refusals=named_refusals,
        omit=tuple(omit),
    )

    assert cell[expected_field] >= 1
    if higher_priority == "benchmark":
        assert cell[expected_field] == len(SECURITY_IDS)
        assert cell["named_figi_resolution_refusal_pair_count"] == 0
    elif higher_priority == "named":
        assert cell["security_entry_unavailable_pair_count"] == 0
    else:
        assert cell["within_membership_exit_unavailable_pair_count"] == 0


def test_named_figi_refusal_inventory_is_exact_and_not_requested_from_history():
    value = _loaded_input()
    for bad in (
        [SECURITY_IDS[0]],
        (SECURITY_IDS[1], SECURITY_IDS[0]),
        (SECURITY_IDS[0], SECURITY_IDS[0]),
        ("not-an-input-security",),
    ):
        with pytest.raises(subject.RegimeRatingEvaluationError, match="FIGI"):
            subject.RegimeRatingEvaluationRuntime(
                value,
                profile_id=PROFILE_ID,
                named_figi_resolution_refusals=bad,
            )
    runtime = subject.RegimeRatingEvaluationRuntime(
        value,
        profile_id=PROFILE_ID,
        named_figi_resolution_refusals=(SECURITY_IDS[0],),
    )
    assert all(
        SECURITY_IDS[0] not in request
        for request in runtime._history_batches
    )
    runtime.abort()


def test_regime_runtime_uses_the_exact_r055_cross_section_signal_path():
    value = _loaded_input()
    base = r055.PreliminaryRatingEvaluationRuntime(value)
    regime = subject.RegimeRatingEvaluationRuntime(
        value,
        profile_id=PROFILE_ID,
        named_figi_resolution_refusals=(),
    )
    assert (
        subject.RegimeRatingEvaluationRuntime._score_cross_section
        is r055.PreliminaryRatingEvaluationRuntime._score_cross_section
    )
    for runtime in (base, regime):
        for contribution_index in runtime._prestart_indices:
            runtime._apply_contribution(value.contributions[contribution_index])
    position = value.session_axis.index("2023-01-03")
    assert base._score_cross_section(position) == regime._score_cross_section(position)
    base.abort()
    regime.abort()


def test_completed_summary_has_exact_sixteen_cells_and_discloses_conditioning():
    runtime = _complete_runtime()
    summary = runtime.aggregate_summary()
    assert summary["schema"] == subject.REGIME_SUMMARY_SCHEMA
    assert summary["contract_id"] == subject.REGIME_CONTRACT_ID
    assert summary["input_contract_id"] == r055.CONTRACT_ID
    assert summary["status"] == "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_REGIME_ONLY"
    assert summary["r055_signal_rule_changed"] is False
    assert summary["terminal_payoff_applied"] is False
    assert summary["economic_portfolio_evaluation"] is False
    assert set(summary) == {
        "schema",
        "contract_id",
        "input_contract_id",
        "manifest_id",
        "manifest_sha256",
        "status",
        "source_lineage_sha256s",
        "profile",
        "source_view_ids",
        "score_arms",
        "horizons",
        "outcome_definition",
        "history_normalization_mode",
        "history_value_field",
        "decay_state_method",
        "benchmark_role",
        "q_data_policy_id",
        "input_security_count",
        "input_contribution_count",
        "named_figi_resolution_refusal_count",
        "completed_callback_count",
        "r055_signal_rule_changed",
        "outcome_availability_disclosures",
        "accepted_risk_disclosures",
        "raw_provider_rows_in_summary",
        "raw_security_outcome_rows_in_summary",
        "raw_price_rows_in_summary",
        "terminal_payoff_applied",
        "economic_portfolio_evaluation",
        "formal_result",
        "alpha_claim_authorized",
        "cells",
        "summary_id",
        "summary_sha256",
    }
    assert len(summary["cells"]) == 16
    assert {
        (
            cell["source_view_id"],
            cell["score_arm"],
            cell["horizon_sessions"],
        )
        for cell in summary["cells"]
    } == {
        (view, arm, horizon)
        for view in r055.SOURCE_VIEW_IDS
        for arm in r055.SCORE_ARMS
        for horizon in r055.HORIZONS
    }
    disclosures = summary["outcome_availability_disclosures"]
    assert disclosures == dict(subject.OUTCOME_AVAILABILITY_DISCLOSURES)
    assert disclosures[
        "endpoint_price_conditioning"
    ] == "security_and_benchmark_entry_and_exit_prices_required"
    assert disclosures["endpoint_price_conditioning_direction"] == "unknown"
    assert disclosures["membership_ended_by_exit_is_confirmed_terminal"] is False
    assert disclosures[
        "membership_ended_by_exit_interpretation"
    ] == "membership_end_is_not_a_confirmed_terminal_or_terminal_payoff"
    assert disclosures["terminal_payoff_policy_applied"] is False
    for cell in summary["cells"]:
        assert set(cell) == {
            "schema",
            "source_view_id",
            "score_arm",
            "horizon_sessions",
            "profile_id",
            "window_start_session",
            "window_end_session",
            "status",
            "eligible_score_row_count",
            "accepted_outcome_pair_count",
            "missing_outcome_pair_count",
            "benchmark_endpoint_unavailable_pair_count",
            "named_figi_resolution_refusal_pair_count",
            "security_entry_unavailable_pair_count",
            "membership_ended_by_exit_with_exit_unavailable_pair_count",
            "within_membership_exit_unavailable_pair_count",
            "missing_pair_counter_sum_matches_total",
            "sector_refused_row_count",
            "valid_ic_date_count",
            "invalid_ic_date_count",
            "mean_daily_spearman_ic",
            "median_daily_spearman_ic",
            "positive_ic_date_share",
            "mean_of_daily_cross_section_mean_excess_returns",
            "median_of_daily_cross_section_mean_excess_returns",
            "outcome_definition",
            "endpoint_price_conditioning",
            "membership_ended_by_exit_interpretation",
            "formal_accept_reject_disposition",
        }
        assert cell["schema"] == subject.REGIME_CELL_SCHEMA
        assert cell["profile_id"] == PROFILE_ID
        assert cell["endpoint_price_conditioning"] == disclosures[
            "endpoint_price_conditioning"
        ]
        assert cell["membership_ended_by_exit_interpretation"] == disclosures[
            "membership_ended_by_exit_interpretation"
        ]
        assert cell["valid_ic_date_count"] > 50
        assert cell["mean_daily_spearman_ic"] is not None

    statistics = runtime.custom_summary_statistics()
    assert len(statistics) == 17
    assert tuple(statistics) == subject.expected_custom_summary_statistic_names(
        PROFILE_ID
    )
    assert max(map(len, statistics)) <= 64
    assert max(map(len, statistics.values())) <= 4_096
    assert not any("perm-security" in value for value in statistics.values())


def test_all_profile_history_requests_use_only_their_exact_fixed_window():
    value = _loaded_input()
    for profile_id in subject.REGIME_PROFILE_IDS:
        profile = subject.require_regime_profile(profile_id)
        runtime = subject.RegimeRatingEvaluationRuntime(
            value,
            profile_id=profile_id,
            named_figi_resolution_refusals=(),
        )
        request = runtime._history_request(0)
        assert request.start_session == profile["start_session"]
        expected_end = value.session_axis[
            value.session_axis.index(profile["end_session"]) + max(r055.HORIZONS)
        ]
        assert request.end_session == expected_end
        runtime.abort()


def test_new_projected_module_is_small_and_has_no_action_surface():
    path = Path(subject.__file__)
    source = path.read_text(encoding="utf-8")
    assert path.stat().st_size < 60_000
    for forbidden in (
        "set_holdings",
        "market_order",
        "limit_order",
        "liquidate",
        "set_summary_statistic",
        "object_store",
    ):
        assert forbidden not in source.lower()
