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
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

import pandas as pd

from data.market_data import (
    _NYSE_CALENDAR,
    canonical_ticker,
    fetch_historical,
    validated_daily_bar_frame,
)

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

    ``transport_ok`` records whether the provider call itself completed;
    ``usable_tickers``/``missing_tickers`` record data usability;
    ``universe_complete`` records requested-universe coverage; and
    ``ticker_latest_sessions`` retains each usable ticker's freshness input.
    The legacy persisted ``ok`` field remains the provider-health verdict:
    transport succeeded and at least one requested ticker was usable.

    ``latest_session`` is deliberately the *oldest* latest-session among
    usable requested tickers. It is the batch's worst required-symbol
    freshness input, so one fresh sibling cannot mask a stale one.
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
    transport_ok: bool
    usable_tickers: tuple[str, ...]
    universe_complete: bool
    ticker_latest_sessions: tuple[tuple[str, str], ...]
    ticker_errors: tuple[tuple[str, str], ...]


@dataclasses.dataclass(frozen=True)
class ProviderOutputValidation:
    """Validated requested-universe output, preserving usable frame objects."""

    requested_tickers: tuple[str, ...]
    usable_data: dict[str, pd.DataFrame] = dataclasses.field(
        compare=False, repr=False
    )
    missing_tickers: tuple[str, ...] = ()
    ticker_latest_sessions: tuple[tuple[str, str], ...] = ()
    ticker_errors: tuple[tuple[str, str], ...] = ()

    @property
    def universe_complete(self) -> bool:
        return not self.missing_tickers


def canonical_requested_tickers(
    requested_tickers: list[str],
) -> tuple[str, ...]:
    requested = tuple(canonical_ticker(ticker) for ticker in requested_tickers)
    if not requested:
        raise ValueError("requested_tickers must contain at least one ticker")
    if len(set(requested)) != len(requested):
        raise ValueError("requested_tickers must be unique after canonicalization")
    return requested


def validate_provider_output(
    requested_tickers: list[str],
    data: dict[str, pd.DataFrame] | None,
) -> ProviderOutputValidation:
    """Validate every requested ticker independently at the provider boundary.

    Invalid or absent tickers do not erase clean siblings. Response keys are
    canonicalized before matching, while duplicate keys that collapse to the
    same canonical symbol are rejected as ambiguous for that symbol.
    """

    requested = canonical_requested_tickers(requested_tickers)

    by_ticker: dict[str, object] = {}
    collisions: set[str] = set()
    malformed_response = data is not None and not isinstance(data, dict)
    if isinstance(data, dict):
        for raw_ticker, frame in data.items():
            try:
                ticker = canonical_ticker(raw_ticker)
            except ValueError:
                continue
            if ticker not in requested:
                continue
            if ticker in by_ticker:
                collisions.add(ticker)
            else:
                by_ticker[ticker] = frame

    usable_data: dict[str, pd.DataFrame] = {}
    sessions: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    for ticker in requested:
        if malformed_response:
            errors.append((ticker, "provider response is not a ticker mapping"))
            continue
        if ticker in collisions:
            errors.append((ticker, "provider response has duplicate canonical keys"))
            continue
        if ticker not in by_ticker:
            errors.append((ticker, "ticker absent from provider response"))
            continue
        validation, usable_frame = validated_daily_bar_frame(
            ticker, by_ticker[ticker]
        )
        if not validation.usable or usable_frame is None:
            errors.append((ticker, validation.error or "ticker data is unusable"))
            continue
        usable_data[ticker] = usable_frame
        sessions.append((ticker, validation.latest_session or ""))

    missing = tuple(ticker for ticker in requested if ticker not in usable_data)
    return ProviderOutputValidation(
        requested_tickers=requested,
        usable_data=usable_data,
        missing_tickers=missing,
        ticker_latest_sessions=tuple(sessions),
        ticker_errors=tuple(errors),
    )


def build_validated_fetch(
    source: PriceSource,
    requested_tickers: list[str],
    data: dict[str, pd.DataFrame] | None,
    *,
    data_class: str = BAR_DATA_CLASS,
    error: Exception | None = None,
    fetched_at: datetime | None = None,
) -> tuple[dict[str, pd.DataFrame], ProviderFetchRecord]:
    """Build the durable fetch metadata and return only validated siblings."""

    provider_id = getattr(source, "provider_id", None)
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError("PriceSource.provider_id must be a non-empty string")
    lineage = getattr(source, "provides_point_in_time_lineage", None)
    if not isinstance(lineage, bool):
        raise ValueError(
            "PriceSource.provides_point_in_time_lineage must be a boolean "
            "declaration"
        )
    at = fetched_at or datetime.now(timezone.utc)
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("fetched_at must be timezone-aware")
    at = at.astimezone(timezone.utc)

    validation = validate_provider_output(requested_tickers, data)
    transport_ok = error is None
    if transport_ok:
        usable_data = validation.usable_data
        missing = validation.missing_tickers
        sessions = validation.ticker_latest_sessions
        ticker_errors = validation.ticker_errors
    else:
        # A raised call has no coherent response even if a direct caller also
        # supplied a dict. Never persist or return partial data from a failed
        # transport attempt.
        usable_data = {}
        missing = validation.requested_tickers
        sessions = ()
        ticker_errors = tuple(
            (ticker, "provider transport failed") for ticker in missing
        )

    latest_session = min((session for _, session in sessions), default=None)
    ok = transport_ok and bool(usable_data)
    record = ProviderFetchRecord(
        provider_id=provider_id.strip(),
        data_class=data_class,
        fetched_at=at.isoformat(),
        requested_count=len(validation.requested_tickers),
        returned_count=len(usable_data),
        missing_tickers=missing,
        ok=ok,
        error=(
            f"{type(error).__name__}: provider fetch failed"
            if error is not None
            else (
                "provider transport succeeded but returned no usable requested data"
                if not usable_data
                else None
            )
        ),
        point_in_time_lineage=lineage,
        latest_session=latest_session,
        transport_ok=transport_ok,
        usable_tickers=tuple(usable_data),
        universe_complete=transport_ok and not missing,
        ticker_latest_sessions=sessions,
        ticker_errors=ticker_errors,
    )
    return usable_data, record


def build_fetch_record(
    source: PriceSource,
    requested_tickers: list[str],
    data: dict[str, pd.DataFrame] | None,
    *,
    data_class: str = BAR_DATA_CLASS,
    error: Exception | None = None,
    fetched_at: datetime | None = None,
) -> ProviderFetchRecord:
    _, record = build_validated_fetch(
        source,
        requested_tickers,
        data,
        data_class=data_class,
        error=error,
        fetched_at=fetched_at,
    )
    return record


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
    today_date = at.date()
    today = today_date.isoformat()
    try:
        latest_date = date.fromisoformat(latest_session)
    except (TypeError, ValueError):
        return BarFreshness(
            fresh=False,
            latest_session=latest_session,
            expected_session=expected,
            detail=f"bars end on an invalid session date: {latest_session!r}",
        )
    if latest_date > today_date:
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
    if latest_session > expected:
        # The only valid bar later than the latest completed session is a
        # partial bar for today's currently open NYSE session. A Saturday,
        # holiday, or pre-market current-date row is malformed data, not
        # evidence that the provider is extra fresh.
        schedule = _NYSE_CALENDAR.schedule(
            start_date=today, end_date=today
        )
        in_progress = (
            not schedule.empty
            and schedule.iloc[0]["market_open"] <= at
            and at < schedule.iloc[0]["market_close"]
        )
        if latest_session != today or not in_progress:
            return BarFreshness(
                fresh=False,
                latest_session=latest_session,
                expected_session=expected,
                detail=(
                    f"bars end {latest_session}, which is later than the "
                    f"latest completed session {expected} but is not an "
                    "in-progress NYSE session"
                ),
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
