"""Conservative publication-to-next-open availability for SI snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from data.exchange_calendar import (
    ExchangeCalendarError,
    next_session_open_strictly_after,
    resolve_nth_session_after,
    session_open_instant,
)
from research.short_interest_etf.contracts import (
    ReleaseCalendarEntry,
    ReleasePrecision,
    ShortInterestContractError,
    ShortInterestSnapshot,
    format_utc_timestamp,
    parse_utc_timestamp,
)


@dataclass(frozen=True)
class ExecutionCohort:
    session: str
    opens_at: str


def _next_open_after(instant: datetime) -> ExecutionCohort:
    try:
        session, opens_at = next_session_open_strictly_after(instant)
    except ExchangeCalendarError as exc:
        raise ShortInterestContractError(
            f"cannot resolve next-open execution cohort: {exc}"
        ) from exc
    return ExecutionCohort(session, format_utc_timestamp(opens_at))


def release_execution_cohort(release: ReleaseCalendarEntry) -> ExecutionCohort:
    """First open usable after a documented release, never settlement date."""
    if not isinstance(release, ReleaseCalendarEntry):
        raise ShortInterestContractError("release must be a ReleaseCalendarEntry")
    try:
        if release.precision is ReleasePrecision.DATE_ONLY:
            session = resolve_nth_session_after(release.public_release_date, 1)
            cohort = ExecutionCohort(
                session=session,
                opens_at=format_utc_timestamp(session_open_instant(session)),
            )
        else:
            cohort = _next_open_after(
                parse_utc_timestamp(release.public_release_at, "public_release_at")
            )
        if cohort.session <= release.settlement_date:
            session = resolve_nth_session_after(release.settlement_date, 1)
            return ExecutionCohort(
                session=session,
                opens_at=format_utc_timestamp(session_open_instant(session)),
            )
        return cohort
    except ExchangeCalendarError as exc:
        raise ShortInterestContractError(
            f"cannot resolve release execution cohort: {exc}"
        ) from exc


def snapshot_execution_cohort(
    snapshot: ShortInterestSnapshot,
    release: ReleaseCalendarEntry,
) -> ExecutionCohort:
    """First open after release and every exact input-availability instant."""
    if type(snapshot) is not ShortInterestSnapshot:
        raise ShortInterestContractError(
            "snapshot must be a ShortInterestSnapshot; daily volume is forbidden"
        )
    if not isinstance(release, ReleaseCalendarEntry):
        raise ShortInterestContractError("release must be a ReleaseCalendarEntry")
    if snapshot.release_calendar_key != release.key:
        raise ShortInterestContractError(
            "snapshot release_calendar_key does not match release entry"
        )
    if snapshot.settlement_date != release.settlement_date:
        raise ShortInterestContractError(
            "snapshot settlement_date does not match release entry"
        )

    cohorts = [
        release_execution_cohort(release),
        _next_open_after(
            parse_utc_timestamp(
                snapshot.revision_published_at, "revision_published_at"
            )
        ),
        _next_open_after(
            parse_utc_timestamp(
                snapshot.volume_basis.available_at, "volume_basis.available_at"
            )
        ),
        _next_open_after(
            parse_utc_timestamp(
                snapshot.denominator.available_at, "denominator.available_at"
            )
        ),
    ]
    return max(cohorts, key=lambda cohort: cohort.opens_at)
