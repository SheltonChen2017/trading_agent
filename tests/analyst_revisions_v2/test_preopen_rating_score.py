"""Synthetic-only tests for the separately versioned 09:20 score clock."""

import dataclasses
import hashlib
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import accepted_risk_preliminary_rating_evaluator as r055
from research.analyst_revisions_v2_qc import accepted_risk_preopen_rating_score as subject
from tests.analyst_revisions_v2.test_qc_accepted_risk_sequential_r055_score import (
    SECURITY_IDS, _loaded_input,
)


@pytest.fixture(scope="module")
def value():
    return _loaded_input()


def _start(value):
    return value.session_axis.index("2025-01-02")


def _ordered(rows):
    return tuple(sorted(rows, key=lambda item: (
        r055.SOURCE_VIEW_IDS.index(item.source_view_id), item.eligible_session_index,
        item.security_id, item.institution_id, item.contribution_id,
    )))


def _contribution(view, security, position, *, firm=Fraction(1), global_value=Fraction(1), label="synthetic"):
    row = r055.build_contribution_record(
        source_view_id=view, security_id=security, eligible_session_index=position,
        institution_id=label, common_event_id=label + "-event",
        rating_action="upgrades" if firm > 0 else "downgrades",
        firm_delta=firm, global_delta=global_value,
        source_row_sha256=hashlib.sha256(label.encode()).hexdigest(),
    )
    return r055.RatingContribution(
        view, row["contribution_id"], security, position, label, label + "-event",
        row["rating_action"], firm, global_value,
        row["source_row_sha256"], row["row_sha256"],
    )


def _memberships(value, specs):
    rows = tuple(sorted((r055.build_membership_record(
        security_id=security, first_session_index=first,
        last_session_index_exclusive=last, sector_id=sector,
    ) for security, first, last, sector in specs), key=lambda row: (
        row["security_id"], row["first_session_index"], row["last_session_index_exclusive"], row["sector_id"],
    )))
    return r055._parse_memberships(rows, len(value.session_axis))


def _reference(value, position, *, include_same=False):
    # Independently select the admissible rows before invoking the unchanged
    # pure R055 arithmetic; do not run its outcome/history initializer.
    runtime = object.__new__(r055.PreliminaryRatingEvaluationRuntime)
    runtime._input = value
    runtime._states = {view: {} for view in r055.SOURCE_VIEW_IDS}
    runtime._live_contribution_indices = {}
    for row in value.contributions:
        if row.eligible_session_index < position or (include_same and row.eligible_session_index == position):
            runtime._apply_contribution(row)
    return runtime._score_cross_section(position)


def _assert_reference(snapshot, value, position):
    members, scores, refused = _reference(value, position)
    assert snapshot.position == position
    assert snapshot.session == value.session_axis[position]
    assert snapshot.memberships == members
    assert snapshot.scores_by_axis == scores
    assert snapshot.sector_refused_counts == {axis: refused[axis] for axis in subject._AXES}


def test_inherits_unchanged_numeric_methods_without_outcome_initializer(value):
    runtime = subject.PreopenRatingScoreRuntime(value, start_position=_start(value))
    for name in ("_apply_contribution", "_score_cross_section", "_reliability"):
        assert getattr(subject.PreopenRatingScoreRuntime, name) is getattr(r055.PreliminaryRatingEvaluationRuntime, name)
    assert not hasattr(runtime, "_history_prices")
    assert not hasattr(runtime, "_cells")
    assert not hasattr(runtime, "_phase")
    assert runtime.last_position is None
    assert runtime._live_contribution_indices == {}
    assert subject.CONTRACT_ID != r055.CONTRACT_ID
    assert subject.DECISION_TIME_NEW_YORK == "09:20:00"
    assert subject.FROZEN_ELIGIBILITY_TIME_NEW_YORK == "09:30:00"


def test_same_session_and_future_0930_are_excluded_until_next_session(value):
    p = _start(value)
    runtime = subject.PreopenRatingScoreRuntime(value, start_position=p)
    first = runtime.score(p)
    for view in r055.SOURCE_VIEW_IDS:
        assert SECURITY_IDS[12] not in runtime._states[view]
        assert SECURITY_IDS[13] not in runtime._states[view]
        assert first.scores_by_axis[(view, "firm_specific")][SECURITY_IDS[12]] == 0
    assert first.scores_by_axis != _reference(value, p, include_same=True)[1]
    second = runtime.score(p + 1)
    _assert_reference(second, value, p + 1)
    assert SECURITY_IDS[12] in runtime._states[subject.PRIMARY_SOURCE_VIEW_ID]
    at_future_open = runtime.score(p + 2)
    assert SECURITY_IDS[13] not in runtime._states[subject.PRIMARY_SOURCE_VIEW_ID]
    _assert_reference(at_future_open, value, p + 2)
    following = runtime.score(p + 3)
    assert SECURITY_IDS[13] in runtime._states[subject.PRIMARY_SOURCE_VIEW_ID]
    _assert_reference(following, value, p + 3)


@pytest.mark.parametrize("offset", [0, 1, 2, 3, 4, 20, 40])
@pytest.mark.parametrize("seed_at_decision", [False, True])
def test_both_views_and_arms_equal_frozen_arithmetic_with_strict_row_subset(value, offset, seed_at_decision):
    p = _start(value)
    runtime = subject.PreopenRatingScoreRuntime(value, start_position=p + offset if seed_at_decision else 0)
    snapshot = runtime.score(p + offset)
    _assert_reference(snapshot, value, p + offset)
    assert set(snapshot.scores_by_axis) == set(subject._AXES)
    assert snapshot.primary_view_firm_specific_scores == snapshot.scores_by_axis[(r055.SOURCE_VIEW_IDS[1], "firm_specific")]


def test_skipped_progression_equals_each_session_and_applies_every_row_once(value):
    p = _start(value)
    dense = subject.PreopenRatingScoreRuntime(value, start_position=p)
    sparse = subject.PreopenRatingScoreRuntime(value, start_position=p)
    for offset in range(6):
        expected = dense.score(p + offset)
        if offset in (0, 2, 5):
            actual = sparse.score(p + offset)
            assert actual.scores_by_axis == expected.scores_by_axis
            assert actual.sector_refused_counts == expected.sector_refused_counts
    assert sparse._states == dense._states


def test_original_full2013_seed_and_original_indices_not_shifted(value):
    p = _start(value)
    ancient = tuple(_contribution(view, SECURITY_IDS[0], 0, label="2013-seed") for view in r055.SOURCE_VIEW_IDS)
    seeded = dataclasses.replace(value, contributions=_ordered(value.contributions + ancient))
    runtime = subject.PreopenRatingScoreRuntime(seeded, start_position=p)
    assert runtime._input.session_axis[0] == "2013-01-02"
    assert runtime._input.contributions == seeded.contributions
    for view in r055.SOURCE_VIEW_IDS:
        assert "2013-seed" in runtime._states[view][SECURITY_IDS[0]].firm_institution_mass
    _assert_reference(runtime.score(p), seeded, p)
    probe = value.contributions[0]
    state = subject.PreopenRatingScoreRuntime(value, start_position=p)._states[probe.source_view_id][probe.security_id]
    with localcontext(r055._context()):
        expected = +(r055._fraction_decimal(probe.firm_delta) / r055._decay(probe.eligible_session_index))
    assert state.raw_firm_unscaled == expected


def test_current_membership_and_normalization_not_yesterdays_cross_section(value):
    p = _start(value)
    specs = [(security, 0, len(value.session_axis), "sector-technology") for security in SECURITY_IDS[1:]]
    specs += [(SECURITY_IDS[0], 0, p, "sector-technology"),
              ("security-20", p, len(value.session_axis), "sector-technology")]
    changed = dataclasses.replace(value, memberships=_memberships(value, specs))
    actual = subject.PreopenRatingScoreRuntime(changed, start_position=p).score(p)
    _assert_reference(actual, changed, p)
    assert SECURITY_IDS[0] not in actual.sector_by_security_id
    assert actual.primary_view_firm_specific_scores["security-20"] == 0
    assert "security-20" not in _reference(changed, p - 1)[1][subject._AXES[0]]


def test_october_axis_excludes_oct12_and_oct13_eligible_rows_at_oct12_preopen(value):
    sessions = tuple(session.isoformat() for session in trading_sessions(date(2013, 1, 2), date(2026, 10, 13)))
    p = sessions.index("2026-10-12")
    extended = dataclasses.replace(value, session_axis=sessions)
    extended = dataclasses.replace(extended, memberships=_memberships(extended, [
        (security, 0, len(sessions), "sector-technology") for security in SECURITY_IDS
    ]))
    additions = tuple(_contribution(view, SECURITY_IDS[14 + offset], p + offset,
                                    label=f"october-{offset}")
                      for view in r055.SOURCE_VIEW_IDS for offset in (0, 1))
    extended = dataclasses.replace(extended, contributions=_ordered(value.contributions + additions))
    runtime = subject.PreopenRatingScoreRuntime(extended, start_position=p)
    _assert_reference(runtime.score(p), extended, p)
    for view in r055.SOURCE_VIEW_IDS:
        assert SECURITY_IDS[14] not in runtime._states[view]
        assert SECURITY_IDS[15] not in runtime._states[view]
    runtime.score_session("2026-10-13")
    for view in r055.SOURCE_VIEW_IDS:
        assert SECURITY_IDS[14] in runtime._states[view]
        assert SECURITY_IDS[15] not in runtime._states[view]


@pytest.mark.parametrize("mode", ["no-active", "four-active", "nineteen-members", "all-equal"])
def test_null_underfilled_and_zero_cross_sections_retain_frozen_semantics(value, mode):
    p = _start(value)
    count = 20 if mode == "all-equal" else 4 if mode == "four-active" else 1
    position = p if mode == "no-active" else p - 1
    rows = tuple(_contribution(view, security, position, label=f"flat-{i}")
                 for view in r055.SOURCE_VIEW_IDS for i, security in enumerate(SECURITY_IDS[:count]))
    modified = dataclasses.replace(value, contributions=_ordered(rows))
    if mode == "nineteen-members":
        modified = dataclasses.replace(modified, memberships=value.memberships[:-1])
    snap = subject.PreopenRatingScoreRuntime(modified, start_position=p).score(p)
    _assert_reference(snap, modified, p)
    for axis in subject._AXES:
        if mode == "all-equal":
            # Preserve even the frozen evaluator's fractional-decay rounding:
            # a rounded even median can create a tiny nonzero MAD here.
            assert len(set(snap.scores_by_axis[axis].values())) == 1
            assert snap.sector_refused_counts[axis] == 0
        else:
            assert snap.scores_by_axis[axis] == {}
            assert snap.sector_refused_counts[axis] == len(modified.memberships)


def test_uniform_exact_power_decay_zero_is_not_replaced_by_missing(value):
    p = 20
    rows = tuple(_contribution(view, security, 0, label=f"exact-flat-{i}")
                 for view in r055.SOURCE_VIEW_IDS for i, security in enumerate(SECURITY_IDS))
    modified = dataclasses.replace(value, contributions=_ordered(rows))
    snap = subject.PreopenRatingScoreRuntime(modified, start_position=p).score(p)
    _assert_reference(snap, modified, p)
    for axis in subject._AXES:
        assert len(snap.scores_by_axis[axis]) == 20
        assert set(snap.scores_by_axis[axis].values()) == {Decimal(0)}
        assert snap.sector_refused_counts[axis] == 0


def test_returned_and_input_records_are_detached_no_authority_minted(value):
    p = _start(value)
    local_value = dataclasses.replace(value, contributions=tuple(dataclasses.replace(row) for row in value.contributions))
    runtime = subject.PreopenRatingScoreRuntime(local_value, start_position=p)
    assert runtime._input is not local_value
    assert runtime._input.contributions[0] is not local_value.contributions[0]
    first = runtime.score(p)
    first.scores_by_axis[subject._AXES[0]][SECURITY_IDS[0]] = Decimal(999)
    first.sector_refused_counts[subject._AXES[0]] = 999
    first.sector_by_security_id[SECURITY_IDS[0]] = "changed"
    object.__setattr__(first.memberships[0], "sector_id", "changed")
    object.__setattr__(local_value.contributions[-1], "eligible_session_index", 0)
    _assert_reference(runtime.score(p + 1), value, p + 1)
    assert first.formal_source_admitted is False
    assert first.pristine_point_in_time is False
    assert first.deployment_authorized is False


@pytest.mark.parametrize("position", [True, 1.0, Decimal(1), None, -1, 99999])
def test_invalid_start_positions_refuse(value, position):
    with pytest.raises(subject.PreopenRatingScoreError):
        subject.PreopenRatingScoreRuntime(value, start_position=position)


@pytest.mark.parametrize("position", [True, 1.0, Decimal(1), None, -1, 99999])
def test_invalid_score_positions_do_not_consume_advancement(value, position):
    runtime = subject.PreopenRatingScoreRuntime(value, start_position=_start(value))
    with pytest.raises(subject.PreopenRatingScoreError):
        runtime.score(position)
    assert runtime.last_position is None
    _assert_reference(runtime.score(_start(value)), value, _start(value))


def test_monotonicity_and_exact_session_entrypoint(value):
    p = _start(value)
    runtime = subject.PreopenRatingScoreRuntime(value, start_position=p)
    for bad in (None, 20250102, "2025-01-01"):
        with pytest.raises(subject.PreopenRatingScoreError):
            runtime.score_session(bad)
    runtime.score_session("2025-01-02")
    for repeated in (p, p - 1):
        with pytest.raises(subject.PreopenRatingScoreError):
            runtime.score(repeated)
    assert runtime.last_position == p


@pytest.mark.parametrize("failure_site", ["contribution", "cross-section", "snapshot", "legacy-injection"])
def test_partial_advance_failure_permanently_closes_runtime(value, monkeypatch, failure_site):
    p = _start(value)
    runtime = subject.PreopenRatingScoreRuntime(value, start_position=p)
    runtime.score(p)
    def fail(*_args, **_kwargs):
        raise ValueError("synthetic failure")
    if failure_site == "contribution":
        monkeypatch.setattr(runtime, "_apply_contribution", fail)
    elif failure_site == "cross-section":
        monkeypatch.setattr(runtime, "_score_cross_section", fail)
    elif failure_site == "snapshot":
        monkeypatch.setattr(subject, "PreopenRatingScoreSnapshot", fail)
    else:
        runtime._live_contribution_indices[p + 1] = (0,)
    with pytest.raises(ValueError):
        runtime.score(p + 1)
    assert runtime.last_position == p
    with pytest.raises(subject.PreopenRatingScoreError, match="closed"):
        runtime.score(p + 2)


@pytest.mark.parametrize("field, replacement", [
    ("session_axis", []), ("memberships", []), ("contributions", []),
    ("source_lineage_sha256s", []), ("manifest_sha256", "bad"),
    ("history_batch_security_count", True), ("benchmark_security_id", SECURITY_IDS[0]),
])
def test_malformed_top_level_values_refuse(value, field, replacement):
    with pytest.raises(subject.PreopenRatingScoreError):
        subject.PreopenRatingScoreRuntime(dataclasses.replace(value, **{field: replacement}), start_position=_start(value))


@pytest.mark.parametrize("field, replacement", [
    ("source_view_id", "other"), ("eligible_session_index", True),
    ("eligible_session_index", -1), ("eligible_session_index", 99999),
    ("firm_delta", 1), ("global_delta", 0), ("row_sha256", "0" * 64),
    ("contribution_id", "bad"), ("rating_action", "hold"),
    ("security_id", "missing"),
])
def test_malformed_contribution_values_refuse(value, field, replacement):
    row = dataclasses.replace(value.contributions[0], **{field: replacement})
    modified = dataclasses.replace(value, contributions=(row,) + value.contributions[1:])
    with pytest.raises(subject.PreopenRatingScoreError):
        subject.PreopenRatingScoreRuntime(modified, start_position=_start(value))


@pytest.mark.parametrize("mode", ["duplicate", "reordered", "one-view", "bad-quality", "bad-membership-hash", "overlap", "truncated-seed"])
def test_shape_collision_membership_and_seed_refusals(value, mode):
    changed = value
    if mode == "duplicate":
        changed = dataclasses.replace(value, contributions=(value.contributions[0],) + value.contributions)
    elif mode == "reordered":
        changed = dataclasses.replace(value, contributions=value.contributions[::-1])
    elif mode == "one-view":
        changed = dataclasses.replace(value, contributions=tuple(row for row in value.contributions if row.source_view_id == r055.SOURCE_VIEW_IDS[0]))
    elif mode in ("bad-quality", "bad-membership-hash"):
        field, item = ("q_data", Decimal(2)) if mode == "bad-quality" else ("row_sha256", "0" * 64)
        changed = dataclasses.replace(value, memberships=(dataclasses.replace(value.memberships[0], **{field: item}),) + value.memberships[1:])
    elif mode == "overlap":
        changed = dataclasses.replace(value, memberships=(value.memberships[0],) + value.memberships)
    else:
        changed = dataclasses.replace(value, session_axis=value.session_axis[1:])
    with pytest.raises(subject.PreopenRatingScoreError):
        subject.PreopenRatingScoreRuntime(changed, start_position=_start(value))


def test_plain_shape_checks_do_not_claim_source_or_manifest_authentication(value):
    # Hash-shaped forged metadata remains only a value: upstream authentication
    # is required.  This scorer must not pretend these structural checks mint it.
    changed = dataclasses.replace(value, manifest_sha256="f" * 64, manifest_id="synthetic-unverified-value")
    snapshot = subject.PreopenRatingScoreRuntime(changed, start_position=_start(value)).score(_start(value))
    assert snapshot.formal_source_admitted is False


def test_exact_input_and_nested_dataclass_types_are_required(value):
    class DerivedInput(r055.PreliminaryRatingInput):
        pass
    class DerivedContribution(r055.RatingContribution):
        pass
    derived = DerivedInput(**{field.name: getattr(value, field.name) for field in dataclasses.fields(value)})
    row = value.contributions[0]
    nested = DerivedContribution(**{field.name: getattr(row, field.name) for field in dataclasses.fields(row)})
    for changed in (None, derived, dataclasses.replace(value, contributions=(nested,) + value.contributions[1:])):
        with pytest.raises(subject.PreopenRatingScoreError):
            subject.PreopenRatingScoreRuntime(changed, start_position=0)
