"""Dated synthetic opportunity eligibility with retained named refusals.

There is no provider access or survivorship filter. A supplied delisted issuer
remains a refused opportunity, and these inputs never establish verified PIT.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from data.financial_primitives import exact_decimal_multiply, exact_decimal_sum
from research.guidance_revision_drift.formulas import _bounded_decimal
from research.guidance_revision_drift.timing import (
    Availability, PinnedSchedule, TimingError, _date, _name,
    availability_refusals, decision_cutoff,
)


@dataclass(frozen=True, slots=True)
class DatedSecurity:
    permanent_security_id: str
    issuer_id: str
    valid_from: date
    valid_through: date
    listed_on: date
    exchange: str
    instrument_type: str
    primary: bool
    sector: str | None
    status: str
    availability: Availability

    def __post_init__(self) -> None:
        for name in ("permanent_security_id", "issuer_id", "exchange", "instrument_type", "status"):
            _name(getattr(self, name), name)
        for name in ("valid_from", "valid_through", "listed_on"):
            _date(getattr(self, name), name)
        if self.valid_from > self.valid_through:
            raise TimingError("security validity range is inverted")
        if type(self.primary) is not bool:
            raise TimingError("primary must be an exact bool")
        if self.sector is not None:
            _name(self.sector, "sector")
        if type(self.availability) is not Availability:
            raise TimingError("security availability must be an exact Availability")
        Availability.__post_init__(self.availability)


@dataclass(frozen=True, slots=True)
class RawDailyBar:
    permanent_security_id: str
    session_date: date
    raw_close: Decimal | None
    volume: int | None
    availability: Availability

    def __post_init__(self) -> None:
        _name(self.permanent_security_id, "permanent_security_id")
        _date(self.session_date, "session_date")
        if self.raw_close is not None:
            _bounded_decimal(self.raw_close, "raw_close")
        if self.volume is not None and (type(self.volume) is not int or self.volume < 0 or self.volume > 10**18):
            raise TimingError("volume must be a bounded nonnegative exact int or missing")
        if type(self.availability) is not Availability:
            raise TimingError("bar availability must be an exact Availability")
        Availability.__post_init__(self.availability)


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    opportunity_id: str
    permanent_security_id: str
    entry_session: date
    issuer_id: str | None
    sector: str | None
    status: str | None
    eligible: bool
    refusal_reasons: tuple[str, ...]
    previous_close: Decimal | None
    adv20: Decimal | None
    completed_listing_sessions: int | None
    schedule_sha256: str
    point_in_time_data: bool = field(default=False, init=False)
    execution_authorized: bool = field(default=False, init=False)


def evaluate_universe(
    *, schedule: PinnedSchedule, entry_session: date, opportunity_id: str,
    permanent_security_id: str, references: tuple[DatedSecurity, ...],
    bars: tuple[RawDailyBar, ...],
) -> EligibilityResult:
    """Evaluate one opportunity without deleting missing, invalid or inactive names.

    `bars` must be exactly the 20 preceding pinned sessions, never simply 20
    surviving rows. Dated reference intervals are inclusive; overlaps refuse.
    All data, including dated identity/sector metadata, must clear the cutoff.
    """
    _name(opportunity_id, "opportunity_id")
    _name(permanent_security_id, "permanent_security_id")
    index = schedule.index(entry_session)
    cutoff = decision_cutoff(schedule, entry_session)
    if type(references) is not tuple or type(bars) is not tuple:
        raise TimingError("reference and bar inputs must be immutable tuples")
    reasons = []
    matching = []
    for reference in references:
        try:
            if type(reference) is not DatedSecurity:
                raise TimingError("invalid reference type")
            DatedSecurity.__post_init__(reference)
        except ValueError:
            reasons.append("invalid_security_reference")
            continue
        if reference.permanent_security_id == permanent_security_id and reference.valid_from <= entry_session <= reference.valid_through:
            matching.append(reference)
    security = matching[0] if len(matching) == 1 else None
    listing_sessions = None
    if not matching:
        reasons.append("missing_dated_security_mapping")
    elif len(matching) > 1:
        reasons.append("ambiguous_dated_security_mapping")
    if security is not None:
        reasons.extend(availability_refusals(security.availability, cutoff))
        if security.exchange not in ("NYSE", "NASDAQ", "NYSE_AMERICAN"):
            reasons.append("ineligible_exchange")
        if security.instrument_type != "COMMON_STOCK" or not security.primary:
            reasons.append("not_primary_common_share")
        if security.sector is None:
            reasons.append("missing_dated_sector")
        if security.status != "listed":
            reasons.append(f"security_not_listed:{security.status}")
        # This count is a conservative lower bound within pinned coverage. A
        # long-listed issuer needs 60 proved completed sessions, not a schedule
        # extending all the way back to its IPO. No outside sessions are added.
        listing_sessions = sum(security.listed_on <= session.session_date < entry_session for session in schedule.sessions)
        if listing_sessions < 60:
            if security.listed_on < schedule.covered_from:
                reasons.append("insufficient_listing_schedule_evidence")
            else:
                reasons.append("fewer_than_60_completed_listing_sessions")
    if index < 20:
        reasons.append("insufficient_prior_schedule_sessions")
        expected = ()
    else:
        expected = tuple(session.session_date for session in schedule.sessions[index - 20:index])
    if len(bars) != 20:
        reasons.append("history_requires_exactly_20_rows")
    by_session = {}
    valid_history = index >= 20 and len(bars) == 20
    for bar in bars:
        try:
            if type(bar) is not RawDailyBar:
                raise TimingError("invalid bar type")
            RawDailyBar.__post_init__(bar)
        except ValueError:
            reasons.append("invalid_history_row")
            valid_history = False
            continue
        if bar.permanent_security_id != permanent_security_id:
            reasons.append("history_security_identity_mismatch")
            valid_history = False
        if bar.session_date not in expected:
            reasons.append("history_date_not_in_previous_20_sessions")
            valid_history = False
        if bar.session_date in by_session:
            reasons.append("duplicate_history_session")
            valid_history = False
        by_session[bar.session_date] = bar
        clock_reasons = availability_refusals(bar.availability, cutoff)
        reasons.extend(clock_reasons)
        if clock_reasons:
            valid_history = False
        if bar.session_date in expected and bar.availability.published_at is not None:
            bar_close = schedule.sessions[schedule.index(bar.session_date)].close_utc
            if bar.availability.published_at < bar_close:
                reasons.append("daily_bar_publication_before_session_close")
                valid_history = False
        if bar.raw_close is None or bar.raw_close <= 0:
            reasons.append("missing_or_nonpositive_raw_close")
            valid_history = False
        if bar.volume is None:
            reasons.append("missing_volume")
            valid_history = False
    if tuple(sorted(by_session)) != expected:
        reasons.append("missing_or_extra_history_session")
        valid_history = False
    previous_close = None
    adv20 = None
    if valid_history:
        previous_close = by_session[expected[-1]].raw_close
        # Multiplication by 1/20 is finite/exact, never a rounded decision ratio.
        dollar_total = exact_decimal_sum(exact_decimal_multiply(by_session[d].raw_close, Decimal(by_session[d].volume)) for d in expected)
        adv20 = exact_decimal_multiply(dollar_total, Decimal("0.05"))
        if previous_close < Decimal("5"):
            reasons.append("previous_raw_close_below_5")
        if dollar_total < Decimal("400000000"):
            reasons.append("adv20_below_20000000")
    return EligibilityResult(
        opportunity_id=opportunity_id, permanent_security_id=permanent_security_id,
        entry_session=entry_session, issuer_id=security.issuer_id if security else None,
        sector=security.sector if security else None, status=security.status if security else None,
        eligible=not reasons, refusal_reasons=tuple(dict.fromkeys(reasons)),
        previous_close=previous_close, adv20=adv20,
        completed_listing_sessions=listing_sessions, schedule_sha256=schedule.sha256,
    )
