from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_tilt as tilt,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_evaluator as legacy_portfolio,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as r055,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_sequential_r055_score as subject,
)


SECURITY_IDS = tuple(f"security-{index:02d}" for index in range(20))


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


def _loaded_input():
    sessions = tuple(
        session.isoformat()
        for session in trading_sessions(
            date(2013, 1, 2), date(2026, 4, 30)
        )
    )
    session_rows = tuple(
        {
            "schema": r055.SESSION_SCHEMA,
            "session_index": index,
            "session": session,
        }
        for index, session in enumerate(sessions)
    )
    memberships = tuple(
        r055.build_membership_record(
            security_id=security_id,
            first_session_index=0,
            last_session_index_exclusive=len(sessions),
            sector_id="sector-technology",
        )
        for security_id in SECURITY_IDS
    )
    start = sessions.index("2025-01-02")
    contribution_rows = []
    for view_index, view in enumerate(r055.SOURCE_VIEW_IDS):
        for index, security_id in enumerate(SECURITY_IDS[:12]):
            signed = index - 6 if index < 6 else index - 5
            firm_delta = Fraction(signed, 6 + view_index)
            contribution_rows.append(
                r055.build_contribution_record(
                    source_view_id=view,
                    security_id=security_id,
                    eligible_session_index=start - 4,
                    institution_id=f"institution-{index:02d}",
                    common_event_id=f"event-{view_index}-{index:02d}",
                    rating_action=(
                        "upgrades" if firm_delta > 0 else "downgrades"
                    ),
                    firm_delta=firm_delta,
                    global_delta=firm_delta / 2,
                    source_row_sha256=hashlib.sha256(
                        f"base-{view}-{index}".encode("ascii")
                    ).hexdigest(),
                )
            )
        for offset, security_id, signed in (
            (0, SECURITY_IDS[12], 1),
            (2, SECURITY_IDS[13], -1),
        ):
            firm_delta = Fraction(signed, 3 + view_index)
            contribution_rows.append(
                r055.build_contribution_record(
                    source_view_id=view,
                    security_id=security_id,
                    eligible_session_index=start + offset,
                    institution_id=f"institution-future-{offset}",
                    common_event_id=f"event-future-{view_index}-{offset}",
                    rating_action=(
                        "upgrades" if firm_delta > 0 else "downgrades"
                    ),
                    firm_delta=firm_delta,
                    global_delta=firm_delta / 2,
                    source_row_sha256=hashlib.sha256(
                        f"future-{view}-{offset}".encode("ascii")
                    ).hexdigest(),
                )
            )
    contribution_rows.sort(
        key=lambda row: (
            r055.SOURCE_VIEW_IDS.index(row["source_view_id"]),
            row["eligible_session_index"],
            row["security_id"],
            row["institution_id"],
            row["contribution_id"],
        )
    )
    contributions = tuple(contribution_rows)
    manifest = r055.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=session_rows,
        membership_records=memberships,
        contribution_records=contributions,
        source_lineage_sha256s=_lineage(),
    )
    return r055.load_preliminary_rating_input(
        manifest, session_rows, memberships, contributions
    )


def _legacy_cross_sections(value, positions):
    runtime = r055.PreliminaryRatingEvaluationRuntime(value)
    for index in runtime._prestart_indices:
        runtime._apply_contribution(value.contributions[index])
    wanted = set(positions)
    result = {}
    for position in runtime._evaluation_positions:
        cross_section = runtime._score_cross_section(position)
        if position in wanted:
            result[position] = cross_section
        if position >= max(wanted):
            break
    runtime.abort()
    return result


def test_runtime_inherits_exact_r055_methods_without_outcome_initialization():
    value = _loaded_input()
    start = value.session_axis.index("2025-01-02")
    runtime = subject.SequentialR055ScoreRuntime(
        value, start_position=start
    )

    assert (
        subject.SequentialR055ScoreRuntime._apply_contribution
        is r055.PreliminaryRatingEvaluationRuntime._apply_contribution
    )
    assert (
        subject.SequentialR055ScoreRuntime._score_cross_section
        is r055.PreliminaryRatingEvaluationRuntime._score_cross_section
    )
    assert not hasattr(runtime, "_history_prices")
    assert not hasattr(runtime, "_cells")
    assert not hasattr(runtime, "_phase")
    assert runtime.last_position is None


def test_first_snapshot_matches_legacy_r055_and_feeds_bounded_tilt():
    value = _loaded_input()
    start = value.session_axis.index("2025-01-02")
    expected_memberships, expected_scores, expected_refusals = (
        _legacy_cross_sections(value, (start,))[start]
    )
    runtime = subject.SequentialR055ScoreRuntime(
        value, start_position=start
    )

    snapshot = runtime.score(start)
    assert subject.PRIMARY_SOURCE_VIEW_ID == (
        legacy_portfolio.PRIMARY_SOURCE_VIEW_ID
    )
    assert subject.PRIMARY_SOURCE_VIEW_ID == r055.SOURCE_VIEW_IDS[1]
    axis = (
        subject.PRIMARY_SOURCE_VIEW_ID,
        subject.FIRM_SPECIFIC_SCORE_ARM,
    )
    assert snapshot.position == start
    assert snapshot.session == "2025-01-02"
    assert snapshot.memberships == expected_memberships
    assert (
        snapshot.primary_view_firm_specific_scores
        == expected_scores[axis]
    )
    assert snapshot.primary_view_firm_specific_sector_refused_count == (
        expected_refusals[axis]
    )
    assert snapshot.sector_by_security_id == {
        security_id: "sector-technology" for security_id in SECURITY_IDS
    }
    assert type(snapshot.primary_view_firm_specific_scores) is dict
    assert type(snapshot.sector_by_security_id) is dict

    construction = tilt.build_benchmark_tilt(
        {security_id: Decimal(100 + index) for index, security_id in enumerate(SECURITY_IDS)},
        snapshot.primary_view_firm_specific_scores,
        snapshot.sector_by_security_id,
    )
    assert construction.status == tilt.TILT_UNDERFILLED


def test_skipped_positions_apply_due_rows_but_never_future_rows():
    value = _loaded_input()
    start = value.session_axis.index("2025-01-02")
    runtime = subject.SequentialR055ScoreRuntime(
        value, start_position=start
    )

    first = runtime.score(start)
    current = subject.PRIMARY_SOURCE_VIEW_ID
    assert first.primary_view_firm_specific_scores[SECURITY_IDS[13]] == 0
    assert SECURITY_IDS[13] not in runtime._states[current]

    later_position = start + 2
    expected_memberships, expected_scores, expected_refusals = (
        _legacy_cross_sections(value, (later_position,))[later_position]
    )
    later = runtime.score(later_position)
    axis = (current, subject.FIRM_SPECIFIC_SCORE_ARM)
    assert SECURITY_IDS[13] in runtime._states[current]
    assert later.primary_view_firm_specific_scores[SECURITY_IDS[13]] != 0
    assert later.memberships == expected_memberships
    assert later.primary_view_firm_specific_scores == expected_scores[axis]
    assert later.primary_view_firm_specific_sector_refused_count == (
        expected_refusals[axis]
    )
    assert runtime.last_position == later_position


def test_positions_must_increase_strictly_and_stay_within_start_axis():
    value = _loaded_input()
    start = value.session_axis.index("2025-01-02")
    runtime = subject.SequentialR055ScoreRuntime(
        value, start_position=start
    )
    runtime.score(start)

    with pytest.raises(
        subject.SequentialR055ScoreError,
        match="score positions must increase strictly",
    ):
        runtime.score(start)
    with pytest.raises(
        subject.SequentialR055ScoreError,
        match="score position escaped the permitted axis",
    ):
        runtime.score(start - 1)
    with pytest.raises(
        subject.SequentialR055ScoreError,
        match="score position must be an exact int",
    ):
        runtime.score(True)
    with pytest.raises(
        subject.SequentialR055ScoreError,
        match="score position escaped the permitted axis",
    ):
        runtime.score(len(value.session_axis))


def test_session_entrypoint_and_returned_maps_are_detached():
    value = _loaded_input()
    start = value.session_axis.index("2025-01-02")
    runtime = subject.SequentialR055ScoreRuntime(
        value, start_position=start
    )
    first = runtime.score_session("2025-01-02")
    first.primary_view_firm_specific_scores[SECURITY_IDS[0]] = Decimal(999)
    first.sector_by_security_id[SECURITY_IDS[0]] = "hostile-sector"

    second = runtime.score_session(value.session_axis[start + 1])
    assert second.primary_view_firm_specific_scores[SECURITY_IDS[0]] != 999
    assert second.sector_by_security_id[SECURITY_IDS[0]] == "sector-technology"
    with pytest.raises(
        subject.SequentialR055ScoreError,
        match="session escaped the session axis",
    ):
        runtime.score_session("2025-01-01")


def test_constructor_requires_exact_input_and_exact_bounded_start():
    value = _loaded_input()
    for wrong in (None, object()):
        with pytest.raises(
            subject.SequentialR055ScoreError,
            match="requires exact preliminary input",
        ):
            subject.SequentialR055ScoreRuntime(wrong, start_position=0)
    for wrong in (True, Decimal(1)):
        with pytest.raises(
            subject.SequentialR055ScoreError,
            match="start position must be an exact int",
        ):
            subject.SequentialR055ScoreRuntime(value, start_position=wrong)
    for wrong in (-1, len(value.session_axis)):
        with pytest.raises(
            subject.SequentialR055ScoreError,
            match="start position escaped the session axis",
        ):
            subject.SequentialR055ScoreRuntime(value, start_position=wrong)
