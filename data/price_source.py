"""GR-4: the production read path's data-honesty contracts.

Every number the app shows traces to one provider (yfinance) whose closes
are retroactively adjusted and whose outage mode is an empty frame. The ML
track already established the honesty vocabulary (ml/availability.py); this
module adopts it for the production read path WITHOUT importing ml (the
import boundary runs the other way).

Three contracts live here, all pure/stateless (persistence and alerting
live in assistant/data_integrity.py so this module stays importable by
research code):

  * ``PriceSource`` -- a provider protocol that must DECLARE
    ``provides_point_in_time_lineage``. yfinance declares False: its
    adjusted history can be rewritten retroactively and it cannot prove
    when a value first became knowable. No source may be used on the
    production read path without an explicit declaration; honesty is the
    requirement, point-in-time-ness is not (promotion gates enforce that
    separately and unchanged).
  * ``ProviderFetchRecord`` -- what one fetch actually returned, including
    what is MISSING. A provider failure or empty response is recorded as a
    failed fetch, never silently normalized into "no tickers matched".
  * Staleness SLAs per data class, with daily bars evaluated against the
    REAL NYSE calendar (a Monday-morning bar set ending Friday is fresh; a
    Wednesday bar set ending Monday is not), not a crude wall-clock delta.

NEVER synthesize a missing price. Nothing in this module fabricates,
interpolates, or carries forward a value; a consumer of a stale or missing
series must refuse or visibly degrade its own surface.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from typing import Protocol

import pandas as pd

from data.market_data import _NYSE_CALENDAR, fetch_historical

BAR_DATA_CLASS = "bar"
EARNINGS_DATA_CLASS = "earnings"

# Staleness SLAs by data class. "quote" is deliberately ABSENT: order-time
# quote freshness is owned by the execution gate's price_freshness check
# against the policy's max quote age -- restating that number here would
# create a second authority that could drift (CLAUDE.md consolidation
# rule). These SLAs govern presentation/research read surfaces only.
#
# Daily bars have no timedelta entry because their SLA is calendar-defined:
# fresh means "includes the latest completed NYSE session" (see
# expected_latest_completed_session). Earnings events tolerate a bounded
# provider lag before the surface must degrade.
STALENESS_SLAS: dict[str, timedelta] = {
    EARNINGS_DATA_CLASS: timedelta(days=7),
}


class PriceSource(Protocol):
    """A daily-bar provider that must declare its lineage honesty."""

    provider_id: str
    provides_point_in_time_lineage: bool

    def fetch_daily_bars(
        self, tickers: list[str], lookback_days: int
    ) -> dict[str, pd.DataFrame]: ...


class YFinanceDailyBars:
    """The current production provider, honestly declared.

    ``provides_point_in_time_lineage`` is False for the same reason
    ml/availability.py pins yfinance datasets to point_in_time_data=false:
    auto-adjusted closes are rewritten retroactively on splits/dividends,
    so the value visible today is not proven to be the value knowable on
    the bar's date.
    """

    provider_id = "yfinance"
    provides_point_in_time_lineage = False

    def fetch_daily_bars(
        self, tickers: list[str], lookback_days: int
    ) -> dict[str, pd.DataFrame]:
        return fetch_historical(tickers, lookback_days=lookback_days)


@dataclasses.dataclass(frozen=True)
class ProviderFetchRecord:
    """What one fetch actually did -- successes, gaps, and lineage.

    ``ok`` is False when the provider raised OR returned no usable data
    for any requested ticker: an all-empty response is a provider outage
    presenting as data, and treating it as "zero matching tickers" is the
    silent failure mode GR-4 exists to remove. ``latest_session`` is the
    newest bar date across returned frames (None on failure) and is what
    freshness derivations consume, so readiness evidence comes from
    recorded fetches rather than a caller's assertion.
    """

    provider_id: str
    data_class: str
    fetched_at: str
    requested_count: int
    returned_count: int
    missing_tickers: tuple[str, ...]
    ok: bool
    error: str | None
    point_in_time_lineage: bool
    latest_session: str | None


def build_fetch_record(
    source: PriceSource,
    requested_tickers: list[str],
    data: dict[str, pd.DataFrame] | None,
    *,
    data_class: str = BAR_DATA_CLASS,
    error: Exception | None = None,
    fetched_at: datetime | None = None,
) -> ProviderFetchRecord:
    at = (fetched_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    returned = {
        ticker: frame
        for ticker, frame in (data or {}).items()
        if isinstance(frame, pd.DataFrame) and not frame.empty
    }
    missing = tuple(
        ticker for ticker in requested_tickers if ticker not in returned
    )
    latest_session: str | None = None
    if returned:
        latest_session = max(
            frame.index.max() for frame in returned.values()
        ).date().isoformat()
    failed = error is not None or not returned
    return ProviderFetchRecord(
        provider_id=source.provider_id,
        data_class=data_class,
        fetched_at=at.isoformat(),
        requested_count=len(requested_tickers),
        returned_count=len(returned),
        missing_tickers=missing,
        ok=not failed,
        error=(
            f"{type(error).__name__}: provider fetch failed"
            if error is not None
            else ("provider returned no usable data" if not returned else None)
        ),
        point_in_time_lineage=source.provides_point_in_time_lineage,
        latest_session=latest_session,
    )


def expected_latest_completed_session(now: datetime | None = None) -> str:
    """The most recent NYSE session whose close has already happened.

    Derived from the real exchange calendar so weekends and holidays never
    count as missing data. Before today's close, today's session is not yet
    expected; a bar set ending at the previous session is still fresh.
    """
    at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = (at - timedelta(days=14)).date().isoformat()
    schedule = _NYSE_CALENDAR.schedule(
        start_date=start, end_date=at.date().isoformat()
    )
    completed = schedule[schedule["market_close"] <= at]
    if completed.empty:
        raise ValueError(
            "No completed NYSE session in the trailing window; refusing to "
            "guess a freshness baseline."
        )
    return completed.index[-1].date().isoformat()


@dataclasses.dataclass(frozen=True)
class BarFreshness:
    fresh: bool
    latest_session: str | None
    expected_session: str
    detail: str


def evaluate_bar_freshness(
    latest_session: str | None, *, now: datetime | None = None
) -> BarFreshness:
    """Daily-bar SLA: the newest bar must reach the latest completed
    session.

    A bar dated TODAY during an in-progress session is fresher than
    required and passes (providers legitimately return the partial current
    bar). Fail-closed directions: no bars at all is stale, and a bar dated
    strictly beyond today (clock skew or a corrupted index) is refused
    rather than treated as extra-fresh -- data from the future is not
    honesty, it is a defect.
    """
    at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    expected = expected_latest_completed_session(at)
    if latest_session is None:
        return BarFreshness(
            fresh=False,
            latest_session=None,
            expected_session=expected,
            detail="no bars available",
        )
    today = at.date().isoformat()
    if latest_session > today:
        return BarFreshness(
            fresh=False,
            latest_session=latest_session,
            expected_session=expected,
            detail=(
                f"bars end {latest_session}, which is beyond today "
                f"({today}); refusing future-dated data"
            ),
        )
    if latest_session < expected:
        return BarFreshness(
            fresh=False,
            latest_session=latest_session,
            expected_session=expected,
            detail=f"bars end {latest_session}; expected session {expected}",
        )
    return BarFreshness(
        fresh=True,
        latest_session=latest_session,
        expected_session=expected,
        detail=(
            f"bars reach {latest_session} (expected completed session "
            f"{expected})"
        ),
    )
