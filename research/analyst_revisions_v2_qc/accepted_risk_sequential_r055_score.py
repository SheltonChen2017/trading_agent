"""Pure sequential access to the unchanged R055 cross-sectional score.

The preliminary evaluator couples the score to outcome-history collection and
cell accumulation.  An order-level *backtest* needs only the already-reviewed
score state as simulated time advances.  This wrapper therefore initializes
just that state, inherits the exact R055 contribution and cross-section
methods, and exposes a detached score/sector snapshot.  It performs no QC,
provider, price, outcome, broker, network, or order I/O.
"""

import dataclasses
from collections import defaultdict
from decimal import Decimal

try:
    import accepted_risk_preliminary_rating_evaluator as _r055
except ImportError:
    from research.analyst_revisions_v2_qc import (
        accepted_risk_preliminary_rating_evaluator as _r055,
    )


class SequentialR055ScoreError(_r055.PreliminaryRatingEvaluationError):
    """The sequential score input or simulated-time progression was refused."""


PRIMARY_SOURCE_VIEW_ID = _r055.SOURCE_VIEW_IDS[1]
FIRM_SPECIFIC_SCORE_ARM = "firm_specific"


@dataclasses.dataclass(frozen=True, slots=True)
class SequentialR055ScoreSnapshot:
    """Detached primary-view, firm-specific R055 state for one session."""

    position: int
    session: str
    memberships: tuple[_r055.SecurityMembership, ...]
    primary_view_firm_specific_scores: dict[str, Decimal]
    sector_by_security_id: dict[str, str]
    primary_view_firm_specific_sector_refused_count: int


class SequentialR055ScoreRuntime(_r055.PreliminaryRatingEvaluationRuntime):
    """Advance the exact R055 state monotonically without outcome machinery."""

    def __init__(
        self,
        value: _r055.PreliminaryRatingInput,
        *,
        start_position: int,
    ) -> None:
        # Deliberately do not call the base initializer: it allocates outcome
        # history matrices and cell accumulators that this score-only boundary
        # must neither need nor expose.
        if type(value) is not _r055.PreliminaryRatingInput:
            raise SequentialR055ScoreError(
                "sequential R055 runtime requires exact preliminary input"
            )
        if type(start_position) is not int:
            raise SequentialR055ScoreError(
                "sequential R055 start position must be an exact int"
            )
        if start_position < 0 or start_position >= len(value.session_axis):
            raise SequentialR055ScoreError(
                "sequential R055 start position escaped the session axis"
            )

        self._input = value
        self._states: dict[str, dict[str, _r055._SignalState]] = {
            view: {} for view in _r055.SOURCE_VIEW_IDS
        }
        pending: dict[int, list[int]] = defaultdict(list)
        for index, contribution in enumerate(value.contributions):
            if contribution.eligible_session_index < start_position:
                self._apply_contribution(contribution)
            else:
                pending[contribution.eligible_session_index].append(index)
        self._live_contribution_indices = {
            position: tuple(indices)
            for position, indices in pending.items()
        }
        self._start_position = start_position
        self._last_position = start_position - 1
        self._failed = False
        self._session_positions = {
            session: position
            for position, session in enumerate(value.session_axis)
        }

    @property
    def last_position(self) -> int | None:
        """Return the last scored position, or ``None`` before the first score."""

        if self._last_position < self._start_position:
            return None
        return self._last_position

    def score_session(self, session: str) -> SequentialR055ScoreSnapshot:
        """Score an exact session name while preserving position monotonicity."""

        if type(session) is not str or session not in self._session_positions:
            raise SequentialR055ScoreError(
                "sequential R055 session escaped the session axis"
            )
        return self.score(self._session_positions[session])

    def score(self, position: int) -> SequentialR055ScoreSnapshot:
        """Advance through ``position`` and return a detached R055 snapshot.

        Skipped positions are permitted, but their newly eligible
        contributions are applied in order before the requested position.
        Contributions after ``position`` are never touched.
        """

        if self._failed:
            raise SequentialR055ScoreError(
                "sequential R055 runtime is closed after a failed advance"
            )
        if type(position) is not int:
            raise SequentialR055ScoreError(
                "sequential R055 score position must be an exact int"
            )
        if position < self._start_position or position >= len(
            self._input.session_axis
        ):
            raise SequentialR055ScoreError(
                "sequential R055 score position escaped the permitted axis"
            )
        if position <= self._last_position:
            raise SequentialR055ScoreError(
                "sequential R055 score positions must increase strictly"
            )

        try:
            for skipped in range(self._last_position + 1, position):
                for index in self._live_contribution_indices.get(skipped, ()):
                    self._apply_contribution(self._input.contributions[index])
            memberships, scores, sector_refused = self._score_cross_section(
                position
            )
        except Exception:
            # An advance mutates the cumulative signal state.  Refuse reuse
            # after an exception rather than risk applying any row twice.
            self._failed = True
            raise

        self._last_position = position
        sector_by_security_id = {
            membership.security_id: membership.sector_id
            for membership in memberships
        }
        if len(sector_by_security_id) != len(memberships):
            self._failed = True
            raise SequentialR055ScoreError(
                "sequential R055 active membership identity is ambiguous"
            )
        axis = (PRIMARY_SOURCE_VIEW_ID, FIRM_SPECIFIC_SCORE_ARM)
        return SequentialR055ScoreSnapshot(
            position=position,
            session=self._input.session_axis[position],
            memberships=memberships,
            primary_view_firm_specific_scores=dict(scores[axis]),
            sector_by_security_id=sector_by_security_id,
            primary_view_firm_specific_sector_refused_count=(
                sector_refused[axis]
            ),
        )


__all__ = (
    "FIRM_SPECIFIC_SCORE_ARM",
    "PRIMARY_SOURCE_VIEW_ID",
    "SequentialR055ScoreError",
    "SequentialR055ScoreRuntime",
    "SequentialR055ScoreSnapshot",
)
