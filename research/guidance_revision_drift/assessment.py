"""As-of composition of synthetic event, timing and universe checks.

The output is a local software observation, not an approval or order. Replay
is cut at validation time before constructing candidates; future disclosures
and future price rows cannot change an earlier positive assessment.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from research.guidance_revision_drift.events import EventBook, EventCandidate, EventError
from research.guidance_revision_drift.timing import (
    Availability, NY, PinnedSchedule, _utc, availability_refusals,
    decision_cutoff, entry_window,
)
from research.guidance_revision_drift.universe import DatedSecurity, RawDailyBar, evaluate_universe


@dataclass(frozen=True, slots=True)
class FixtureAssessment:
    disclosure_id: str
    eligible_session: date | None
    sector: str | None
    adv20: Decimal | None
    candidate: EventCandidate | None
    refusals: tuple[tuple[date | None, tuple[str, ...]], ...]
    schedule_sha256: str


def visible_book(book: EventBook, as_of: datetime) -> EventBook:
    _utc(as_of, "as_of")
    if type(book) is not EventBook:
        raise EventError("exact EventBook required")
    checked = EventBook(book.entries)
    return EventBook(tuple(entry for entry in checked.entries if entry[0].validated_at <= as_of))


def active_candidates(book: EventBook, as_of: datetime) -> tuple[EventCandidate, ...]:
    active = {}
    for decision in visible_book(book, as_of).decisions:
        for identity in decision.invalidated_disclosure_ids:
            active.pop(identity, None)
        if decision.candidate is not None:
            active[decision.candidate.disclosure_id] = decision.candidate
    return tuple(active[key] for key in sorted(active))


def _visible_input(value: Availability, cutoff: datetime) -> bool:
    if type(value) is not Availability:
        raise EventError("exact input availability record required")
    Availability.__post_init__(value)
    # Unknown clocks remain present to produce an explicit refusal; only
    # known future versions are excluded from this earlier decision corpus.
    return not any(clock is not None and clock > cutoff for clock in (
        value.published_at, value.received_at, value.ingested_at))


def assess_candidate(
    *, book: EventBook, disclosure_id: str, as_of: datetime,
    schedule: PinnedSchedule, permanent_security_id: str,
    references: tuple[DatedSecurity, ...], bars: tuple[RawDailyBar, ...],
) -> FixtureAssessment:
    """Find the first fully eligible opportunity visible as of the decision.

    All earlier opportunities are tested, so calling later cannot select a
    convenient later price after an earlier eligible opportunity was missed.
    The universe receives exactly its previous 20 rows, not future rows. An
    unavailable prior close is retained as a refusal rather than forward-filled.
    """
    _utc(as_of, "as_of")
    if type(schedule) is not PinnedSchedule:
        raise EventError("exact pinned fixture schedule required")
    schedule.validate()
    if (type(disclosure_id) is not str or not disclosure_id.startswith("SYN-")
            or type(permanent_security_id) is not str or not permanent_security_id.startswith("SYN-")):
        raise EventError("explicit synthetic identities required")
    if type(references) is not tuple or type(bars) is not tuple:
        raise EventError("immutable reference and bar tuples required")
    candidates = [c for c in active_candidates(book, as_of) if c.disclosure_id == disclosure_id]
    if len(candidates) != 1:
        return FixtureAssessment(disclosure_id, None, None, None, None,
                                 ((None, ("no_active_as_of_candidate",)),), schedule.sha256)
    candidate = candidates[0]
    opportunities = entry_window(schedule, candidate.published_at.astimezone(NY).date())
    refusals = []
    for opportunity in opportunities:
        cutoff = decision_cutoff(schedule, opportunity)
        # Do not inspect observations for decisions not yet reached.
        if opportunity > as_of.astimezone(NY).date():
            break
        index = schedule.index(opportunity)
        expected = {s.session_date for s in schedule.sessions[max(0, index - 20):index]}
        selected_bars = []
        for bar in bars:
            if type(bar) is not RawDailyBar:
                raise EventError("exact raw daily bar required")
            if (bar.permanent_security_id == permanent_security_id and bar.session_date in expected
                    and _visible_input(bar.availability, cutoff)):
                selected_bars.append(bar)
        selected_references = []
        for reference in references:
            if type(reference) is not DatedSecurity:
                raise EventError("exact dated security reference required")
            if _visible_input(reference.availability, cutoff):
                selected_references.append(reference)
        event_reasons = []
        for name, record in (("payload", candidate.current), ("predecessor", candidate.previous)):
            event_reasons.extend(availability_refusals(Availability(
                name, record.published_at, record.received_at, record.validated_at), cutoff))
        universe = evaluate_universe(
            schedule=schedule, entry_session=opportunity, opportunity_id=disclosure_id,
            permanent_security_id=permanent_security_id, references=tuple(selected_references),
            bars=tuple(selected_bars),
        )
        if universe.issuer_id is not None and universe.issuer_id != candidate.issuer_id:
            event_reasons.append("event_security_issuer_mismatch")
        reasons = tuple(event_reasons) + universe.refusal_reasons
        if reasons:
            refusals.append((opportunity, reasons))
            continue
        if opportunity < as_of.astimezone(NY).date():
            return FixtureAssessment(disclosure_id, None, None, None, candidate,
                tuple(refusals) + ((opportunity, ("earlier_eligible_opportunity_was_missed",)),), schedule.sha256)
        return FixtureAssessment(disclosure_id, opportunity, universe.sector, universe.adv20,
                                 candidate, tuple(refusals), schedule.sha256)
    if not refusals:
        refusals.append((None, ("no_entry_opportunity_reached",)))
    return FixtureAssessment(disclosure_id, None, None, None, candidate, tuple(refusals), schedule.sha256)
