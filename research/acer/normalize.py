"""Normalize a verified ratings snapshot into canonical analyst events.

This is the ACER data backbone's first stage: verified raw snapshot in,
canonical event records out. It is deliberately *dumb* about research
semantics, and three of its non-behaviours matter more than its behaviour:

- **No price, return, universe, or evaluation import exists here**
  (AST-pinned by ``tests/test_acer_normalization.py``). Joining events to
  outcomes is a research look and is forbidden until an ACER-0 freeze.
- **Raw rating strings are preserved untouched.** Mapping broker
  vocabularies onto a numeric scale is an ACER-0 specification decision
  (plan section 4.1: "a specification decision recorded in advance, not a
  data-cleaning step performed while looking at results"). Baking one in
  here would freeze a research value nobody has adopted.
- **Rows are never silently dropped.** Every excluded row becomes a refusal
  record with a named reason, and the refusal counts are part of the
  dataset's content identity.

Availability follows the rule frozen by the ACER-1 audit and its review
(`docs/research/BENZINGA_RATINGS_2026-08-20_DATA_AUDIT.md` section 5), and
that rule is **date-level on purpose**::

    available_date = max(action_date, last_updated UTC date)

Eligibility is then the next trading session strictly after that date. This
deliberately gives up same-day trading so the study does not depend on the
vendor's clock convention, which is evidenced but not vendor-confirmed: the
2017+ ``time`` field measures as US Eastern against ``last_updated``, but a
measurement of internal consistency is not a semantic guarantee. Because the
frozen rule needs no intraday instant, **this module derives no UTC action
timestamp at all** — the vendor's ``time`` string is preserved verbatim and
nothing converts it. Restoring intraday timing requires authoritative field
semantics and a new preregistration, not a code change here.

The session-calendar step ("next trading session after ``available_date``")
also does not live here: it needs an exchange calendar and belongs to the
evaluation layer that only exists after ACER-0.
"""
from __future__ import annotations

import collections
import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Iterable

# Measured era boundary for the vendor `time` field: 2011-2015 rows carry the
# UTC ingestion clock (no independent action timing), 2017+ rows are
# consistent with US Eastern, and 2016 is the mixed transition year. The
# vendor has not confirmed those field semantics. 2016 is grouped
# with the unreliable era on purpose -- treating a mixed year as reliable
# would grant some rows a timing quality they do not have.
#
# This classification is RECORDED, never USED for availability. It exists so
# a later reader can see which rows could ever support intraday work under a
# future preregistration, and so the claim stays visible enough to challenge.
ERA_SPLIT_YEAR = 2017
ERA_INGESTION_CLOCK = "ingestion_clock_era"
ERA_EASTERN_CONSISTENT_CLOCK = "eastern_consistent_clock_era"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REFUSAL_MISSING_ID = "missing_benzinga_id"
REFUSAL_DUPLICATE_ID = "duplicate_benzinga_id"
REFUSAL_MISSING_DATE = "missing_or_malformed_date"
REFUSAL_MISSING_RATING = "missing_rating"
REFUSAL_MISSING_FIRM = "missing_firm"
REFUSAL_MISSING_TICKER = "missing_ticker"
REFUSAL_MISSING_LAST_UPDATED = "missing_or_malformed_last_updated"
REFUSAL_UPDATE_BEFORE_ACTION = "update_precedes_action_date"
REFUSAL_INCONSISTENT_TRANSITION = "inconsistent_transition"

# `rating_action` values whose claimed transition must actually change the
# rating. Everything else (maintains, initiates, reiterates, ...) may
# legitimately carry previous == current, or no previous rating at all.
_DIRECTIONAL_ACTIONS = frozenset({"upgrades", "downgrades"})


@dataclass(frozen=True)
class NormalizedEvent:
    """One analyst action: vendor facts preserved, availability derived.

    Every ``*_raw`` field is vendor vocabulary carried through unmapped.
    ``available_date`` is the only derived research-relevant value, and it is
    a date rather than an instant by design (see the module docstring).
    """

    benzinga_id: str
    action_date: str  # YYYY-MM-DD, as reported by the vendor
    last_updated_utc: str  # ISO-8601 Z, as reported by the vendor
    last_updated_date_utc: str  # YYYY-MM-DD, derived from the above
    available_date: str  # max(action_date, last_updated_date_utc)
    time_field_era: str  # recorded classification; never used for timing
    action_time_raw: str | None  # vendor `time` string, unconverted
    ticker: str
    company_name: str | None
    firm: str
    analyst: str | None
    rating_action: str | None
    rating_raw: str
    previous_rating_raw: str | None
    price_target_raw: str | None  # text; no arithmetic happens in this layer
    previous_price_target_raw: str | None

    def to_payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class Refusal:
    """One excluded row, with the reason it could not become an event."""

    benzinga_id: str | None
    action_date: str | None
    reason: str
    detail: str

    def to_payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def parse_last_updated(value: Any) -> dt.datetime | None:
    """Parse a vendor ``last_updated`` value to aware UTC, or return None.

    Snapshot A's 587,046 values are all ISO-8601 with a ``Z`` suffix. A
    value that carries no offset is treated as malformed rather than assumed
    to be UTC: silently assuming a timezone is how an availability bound
    becomes wrong in the unsafe direction.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def normalize_rows(
    rows: Iterable[dict],
) -> tuple[list[NormalizedEvent], list[Refusal]]:
    """Normalize vendor rows; every exclusion becomes a named refusal.

    Input rows are treated as caller-owned and are never mutated. Output is
    ordered by ``(action_date, benzinga_id)`` so the dataset's content hash
    does not depend on vendor page ordering.

    Identity is tracked across *every* row encountered, including refused
    ones. If the vendor ever emits a repeated ``benzinga_id``, the repeat is
    refused even when the first occurrence was itself refused: a duplicated
    identity key breaks the restatement measurement and the dedup story
    alike, so the fail-closed direction is to surface both rows rather than
    let the second silently take the slot.
    """
    materialized_rows = list(rows)
    id_counts = collections.Counter(
        raw_id.strip()
        for row in materialized_rows
        if isinstance((raw_id := row.get("benzinga_id")), str)
        and raw_id.strip()
    )
    events: list[NormalizedEvent] = []
    refusals: list[Refusal] = []

    for row in materialized_rows:
        raw_id = row.get("benzinga_id")
        date = row.get("date")
        date_for_refusal = date if isinstance(date, str) else None

        if not isinstance(raw_id, str) or not raw_id.strip():
            refusals.append(
                Refusal(
                    None,
                    date_for_refusal,
                    REFUSAL_MISSING_ID,
                    f"benzinga_id={raw_id!r}",
                )
            )
            continue
        rid = raw_id.strip()
        if id_counts[rid] > 1:
            refusals.append(
                Refusal(
                    rid,
                    date_for_refusal,
                    REFUSAL_DUPLICATE_ID,
                    f"benzinga_id appears {id_counts[rid]} times in this snapshot",
                )
            )
            continue

        if not isinstance(date, str) or not _DATE_RE.match(date):
            refusals.append(Refusal(rid, None, REFUSAL_MISSING_DATE, f"date={date!r}"))
            continue
        try:
            action_date = dt.date.fromisoformat(date)
        except ValueError:
            refusals.append(Refusal(rid, None, REFUSAL_MISSING_DATE, f"date={date!r}"))
            continue

        rating = row.get("rating")
        if not isinstance(rating, str) or not rating.strip():
            refusals.append(
                Refusal(rid, date, REFUSAL_MISSING_RATING, f"rating={rating!r}")
            )
            continue
        firm = row.get("firm")
        if not isinstance(firm, str) or not firm.strip():
            refusals.append(Refusal(rid, date, REFUSAL_MISSING_FIRM, f"firm={firm!r}"))
            continue
        ticker = row.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            # No ticker means no path to a security at all. The issuer-identity
            # problem is hard even WITH a ticker (the feed carries no ISIN or
            # exchange); without one the row cannot be mapped by any means.
            refusals.append(
                Refusal(rid, date, REFUSAL_MISSING_TICKER, f"ticker={ticker!r}")
            )
            continue

        last_updated = parse_last_updated(row.get("last_updated"))
        if last_updated is None:
            refusals.append(
                Refusal(
                    rid,
                    date,
                    REFUSAL_MISSING_LAST_UPDATED,
                    f"last_updated={row.get('last_updated')!r}",
                )
            )
            continue
        last_updated_date = last_updated.date()
        if last_updated_date < action_date:
            # Measured in Snapshot A on 39 rows: `time` matches the update
            # instant's Eastern wall clock while `date` sits one day later.
            # The vendor's own two fields disagree about when this happened,
            # so no availability bound derived from them can be trusted.
            refusals.append(
                Refusal(
                    rid,
                    date,
                    REFUSAL_UPDATE_BEFORE_ACTION,
                    f"last_updated={last_updated_date.isoformat()} precedes date={date}",
                )
            )
            continue

        action = row.get("rating_action") or None
        previous = row.get("previous_rating") or None
        if (
            isinstance(action, str)
            and action.strip().lower() in _DIRECTIONAL_ACTIONS
            and previous is not None
            and _comparison_text(previous) == _comparison_text(rating)
        ):
            refusals.append(
                Refusal(
                    rid,
                    date,
                    REFUSAL_INCONSISTENT_TRANSITION,
                    f"action={action!r} but previous_rating={previous!r} and "
                    f"rating={rating!r} are the same rating",
                )
            )
            continue

        time_raw = row.get("time")
        era = (
            ERA_EASTERN_CONSISTENT_CLOCK
            if action_date.year >= ERA_SPLIT_YEAR
            else ERA_INGESTION_CLOCK
        )
        available_date = max(action_date, last_updated_date)

        events.append(
            NormalizedEvent(
                benzinga_id=rid,
                action_date=date,
                last_updated_utc=_iso_z(last_updated),
                last_updated_date_utc=last_updated_date.isoformat(),
                available_date=available_date.isoformat(),
                time_field_era=era,
                action_time_raw=time_raw if isinstance(time_raw, str) and time_raw else None,
                ticker=ticker.strip(),
                company_name=_optional_text(row.get("company_name")),
                firm=firm.strip(),
                analyst=_optional_text(row.get("analyst")),
                rating_action=_optional_text(action),
                rating_raw=rating.strip(),
                previous_rating_raw=_optional_text(previous),
                price_target_raw=_optional_text(row.get("price_target")),
                previous_price_target_raw=_optional_text(
                    row.get("previous_price_target")
                ),
            )
        )

    events.sort(key=lambda event: (event.action_date, event.benzinga_id))
    refusals.sort(
        key=lambda refusal: (
            refusal.action_date or "",
            refusal.benzinga_id or "",
            refusal.reason,
        )
    )
    return events, refusals


def _optional_text(value: Any) -> str | None:
    """Preserve a vendor value as text, mapping empty and absent to None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _comparison_text(value: Any) -> str | None:
    """Return a conservative comparison key without mapping vocabulary.

    Case and repeated whitespace are presentation differences, not rating
    changes. Punctuation is deliberately retained: deciding that, for
    example, ``Buy`` and ``Buy+`` are aliases belongs to ACER-0's frozen
    firm-specific rating map rather than this plumbing layer.
    """
    if not isinstance(value, str):
        return None
    return " ".join(value.split()).casefold() or None


def _iso_z(timestamp: dt.datetime) -> str:
    return (
        timestamp.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    )
