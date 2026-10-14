"""Pure 09:20 score view over the original-index accepted-risk rating input.

This separately versioned adapter excludes contributions whose frozen 09:30
eligibility is the decision session itself.  It neither shifts eligibility
indices nor evaluates yesterday's membership/cross-section.  All other numeric
operations are the unchanged preliminary evaluator's operations.

Exact typed input is a value, not source authority.  The defensive shape/hash
checks below do not authenticate its manifest, source lineage, calendar, or
package.  Those remain the new October package/projection's responsibility.
There is no outcome, provider, price, order, or deployment operation here.
"""

import dataclasses
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction

try:
    import accepted_risk_preliminary_rating_evaluator as _r055
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_rating_evaluator as _r055,
    )


CONTRACT_ID = "arv2-accepted-risk-preopen-rating-score-v1"
DECISION_TIME_NEW_YORK = "09:20:00"
FROZEN_ELIGIBILITY_TIME_NEW_YORK = "09:30:00"
PRIMARY_SOURCE_VIEW_ID = _r055.SOURCE_VIEW_IDS[1]
FIRM_SPECIFIC_SCORE_ARM = "firm_specific"
_AXES = tuple((view, arm) for view in _r055.SOURCE_VIEW_IDS for arm in _r055.SCORE_ARMS)


class PreopenRatingScoreError(_r055.PreliminaryRatingEvaluationError):
    """The pure score value or forward-only progression was refused."""


def _copy_input(value):
    """Validate bounded scalar structure and detach frozen nested records.

    Contribution records are checked one at a time to avoid retaining a second
    full canonical-dictionary corpus alongside the potentially large input.
    """
    if type(value) is not _r055.PreliminaryRatingInput:
        raise PreopenRatingScoreError("preopen score requires exact preliminary input")
    if type(value.session_axis) is not tuple or len(value.session_axis) > _r055.MAX_SESSION_COUNT:
        raise PreopenRatingScoreError("preopen session axis requires a bounded tuple")
    sessions = _r055._parse_sessions(tuple(
        {"schema": _r055.SESSION_SCHEMA, "session_index": i, "session": session}
        for i, session in enumerate(value.session_axis)
    ))
    if type(value.memberships) is not tuple or not 0 < len(value.memberships) <= _r055.MAX_SECURITY_COUNT:
        raise PreopenRatingScoreError("preopen memberships require a bounded tuple")
    membership_rows = []
    for item in value.memberships:
        if type(item) is not _r055.SecurityMembership or type(item.q_data) is not Decimal:
            raise PreopenRatingScoreError("preopen membership type changed")
        if not item.q_data.is_finite() or item.q_data != Decimal(1):
            raise PreopenRatingScoreError("preopen membership quality changed")
        row = _r055.build_membership_record(
            security_id=item.security_id,
            first_session_index=item.first_session_index,
            last_session_index_exclusive=item.last_session_index_exclusive,
            sector_id=item.sector_id,
        )
        if _r055._hash(item.row_sha256, "membership hash") != row["row_sha256"]:
            raise PreopenRatingScoreError("preopen membership content hash changed")
        membership_rows.append(row)
    memberships = _r055._parse_memberships(tuple(membership_rows), len(sessions))
    securities = {item.security_id for item in memberships}
    if type(value.contributions) is not tuple or len(value.contributions) > _r055.MAX_CONTRIBUTION_COUNT:
        raise PreopenRatingScoreError("preopen contributions require a bounded tuple")
    copied = []
    previous = None
    seen = set()
    views = set()
    for item in value.contributions:
        if type(item) is not _r055.RatingContribution:
            raise PreopenRatingScoreError("preopen contribution type changed")
        view = _r055._string(item.source_view_id, "source view")
        if view not in _r055.SOURCE_VIEW_IDS:
            raise PreopenRatingScoreError("preopen contribution view changed")
        security = _r055._string(item.security_id, "contribution security")
        if security not in securities:
            raise PreopenRatingScoreError("preopen contribution lacks membership")
        _r055._count(item.eligible_session_index, "eligible session", maximum=len(sessions) - 1)
        if type(item.firm_delta) is not Fraction or type(item.global_delta) is not Fraction:
            raise PreopenRatingScoreError("preopen contribution deltas changed type")
        # Check the action type before the frozen builder compares its value.
        _r055._string(item.rating_action, "rating action")
        row = _r055.build_contribution_record(
            source_view_id=view, security_id=security,
            eligible_session_index=item.eligible_session_index,
            institution_id=item.institution_id, common_event_id=item.common_event_id,
            rating_action=item.rating_action, firm_delta=item.firm_delta,
            global_delta=item.global_delta, source_row_sha256=item.source_row_sha256,
        )
        if (_r055._hash(item.row_sha256, "contribution hash") != row["row_sha256"]
                or _r055._string(item.contribution_id, "contribution id") != row["contribution_id"]):
            raise PreopenRatingScoreError("preopen contribution content identity changed")
        key = (view, item.eligible_session_index, security, item.institution_id)
        if key in seen:
            raise PreopenRatingScoreError("preopen institution/security/session duplicate")
        seen.add(key)
        order = (_r055.SOURCE_VIEW_IDS.index(view), item.eligible_session_index,
                 security, item.institution_id, item.contribution_id)
        if previous is not None and previous > order:
            raise PreopenRatingScoreError("preopen contributions are not canonically sorted")
        previous = order
        views.add(view)
        copied.append(dataclasses.replace(item))
    if views != set(_r055.SOURCE_VIEW_IDS):
        raise PreopenRatingScoreError("preopen input lacks a required source view")
    benchmark = _r055._string(value.benchmark_security_id, "benchmark security")
    if benchmark in securities:
        raise PreopenRatingScoreError("preopen benchmark is a scored security")
    _r055._hash(value.manifest_sha256, "manifest hash")
    _r055._string(value.manifest_id, "manifest id")
    if type(value.source_lineage_sha256s) is not tuple:
        raise PreopenRatingScoreError("preopen lineage must be an exact tuple")
    for pair in value.source_lineage_sha256s:
        if type(pair) is not tuple or len(pair) != 2:
            raise PreopenRatingScoreError("preopen lineage pair changed")
        _r055._string(pair[0], "lineage role")
        _r055._hash(pair[1], "lineage hash")
    if tuple(pair[0] for pair in value.source_lineage_sha256s) != _r055._SOURCE_LINEAGE_FIELDS:
        raise PreopenRatingScoreError("preopen lineage roles changed")
    for field, maximum in (
        ("history_batch_security_count", _r055.MAX_HISTORY_BATCH_SECURITY_COUNT),
        ("scoring_sessions_per_callback", _r055.MAX_SCORING_SESSIONS_PER_CALLBACK),
        ("signal_seed_contributions_per_callback", _r055.MAX_SIGNAL_SEED_CONTRIBUTIONS_PER_CALLBACK),
    ):
        _r055._positive_count(getattr(value, field), field, maximum=maximum)
    return dataclasses.replace(value, session_axis=sessions, memberships=memberships,
                               contributions=tuple(copied))


@dataclasses.dataclass(frozen=True, slots=True)
class PreopenRatingScoreSnapshot:
    """Detached current-membership maps for both views and both score arms."""

    position: int
    session: str
    memberships: tuple[_r055.SecurityMembership, ...]
    scores_by_axis: dict[tuple[str, str], dict[str, Decimal]]
    sector_by_security_id: dict[str, str]
    sector_refused_counts: dict[tuple[str, str], int]

    @property
    def primary_view_firm_specific_scores(self) -> dict[str, Decimal]:
        return dict(self.scores_by_axis[(PRIMARY_SOURCE_VIEW_ID, FIRM_SPECIFIC_SCORE_ARM)])

    @property
    def primary_view_firm_specific_sector_refused_count(self) -> int:
        return self.sector_refused_counts[(PRIMARY_SOURCE_VIEW_ID, FIRM_SPECIFIC_SCORE_ARM)]

    @property
    def formal_source_admitted(self) -> bool:
        return False

    @property
    def pristine_point_in_time(self) -> bool:
        return False

    @property
    def deployment_authorized(self) -> bool:
        return False


class PreopenRatingScoreRuntime(_r055.PreliminaryRatingEvaluationRuntime):
    """Original-index score arithmetic, strictly before the decision open."""

    def __init__(self, value: _r055.PreliminaryRatingInput, *, start_position: int):
        # Do not initialize the outcome/history runtime.
        try:
            self._input = _copy_input(value)
        except _r055.PreliminaryRatingEvaluationError as exc:
            raise PreopenRatingScoreError("preopen input structure refused") from exc
        if type(start_position) is not int or not 0 <= start_position < len(self._input.session_axis):
            raise PreopenRatingScoreError("preopen start position must be an exact in-axis int")
        self._states = {view: {} for view in _r055.SOURCE_VIEW_IDS}
        pending = defaultdict(list)
        for index, contribution in enumerate(self._input.contributions):
            if contribution.eligible_session_index < start_position:
                self._apply_contribution(contribution)
            else:
                pending[contribution.eligible_session_index].append(index)
        self._pending_indices = {position: tuple(indices) for position, indices in pending.items()}
        # The inherited cross-section may only normalize the state already
        # advanced below.  Its legacy 09:30 injection path must remain empty.
        self._live_contribution_indices = {}
        self._start_position = start_position
        self._last_position = start_position - 1
        self._failed = False
        self._session_positions = {session: i for i, session in enumerate(self._input.session_axis)}

    @property
    def last_position(self) -> int | None:
        return None if self._last_position < self._start_position else self._last_position

    def score_session(self, session: str) -> PreopenRatingScoreSnapshot:
        if type(session) is not str or session not in self._session_positions:
            raise PreopenRatingScoreError("preopen session escaped the axis")
        return self.score(self._session_positions[session])

    def score(self, position: int) -> PreopenRatingScoreSnapshot:
        if self._failed:
            raise PreopenRatingScoreError("preopen runtime is closed after a failed advance")
        if type(position) is not int or not self._start_position <= position < len(self._input.session_axis):
            raise PreopenRatingScoreError("preopen score position must be an exact permitted int")
        if position <= self._last_position:
            raise PreopenRatingScoreError("preopen score positions must increase strictly")
        try:
            if self._live_contribution_indices:
                raise PreopenRatingScoreError("preopen legacy same-session injection is not empty")
            for eligible in range(max(self._start_position, self._last_position), position):
                for index in self._pending_indices.get(eligible, ()):
                    self._apply_contribution(self._input.contributions[index])
            memberships, scores, refused = self._score_cross_section(position)
            sectors = {item.security_id: item.sector_id for item in memberships}
            if len(sectors) != len(memberships):
                raise PreopenRatingScoreError("preopen active membership identity is ambiguous")
            snapshot = PreopenRatingScoreSnapshot(
                position, self._input.session_axis[position],
                tuple(dataclasses.replace(item) for item in memberships),
                {axis: dict(scores[axis]) for axis in _AXES}, sectors,
                {axis: refused[axis] for axis in _AXES},
            )
        except BaseException:
            # Any partial mutation makes continued advancement inadmissible.
            self._failed = True
            raise
        self._last_position = position
        return snapshot


__all__ = (
    "CONTRACT_ID", "DECISION_TIME_NEW_YORK", "FROZEN_ELIGIBILITY_TIME_NEW_YORK",
    "PRIMARY_SOURCE_VIEW_ID", "FIRM_SPECIFIC_SCORE_ARM", "PreopenRatingScoreError",
    "PreopenRatingScoreSnapshot", "PreopenRatingScoreRuntime",
)
