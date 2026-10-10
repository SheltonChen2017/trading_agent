"""Invented example corpus; no external inputs or verified exchange history.

Dates below are an explicit *test schedule*. They must not be used as a
production calendar. Prices, volumes and disclosures are invented constants.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal

from data.financial_primitives import decimal_text
from data.hashing import hash_payload
from research.guidance_revision_drift.archive import FixtureArchive
from research.guidance_revision_drift.events import NormalizedDisclosure
from research.guidance_revision_drift.timing import Availability, NY, PinnedSchedule, Session
from research.guidance_revision_drift.universe import DatedSecurity, RawDailyBar


DATES = """
2025-01-02 2025-01-03 2025-01-06 2025-01-07 2025-01-08 2025-01-09 2025-01-10
2025-01-13 2025-01-14 2025-01-15 2025-01-16 2025-01-17 2025-01-21 2025-01-22
2025-01-23 2025-01-24 2025-01-27 2025-01-28 2025-01-29 2025-01-30 2025-01-31
2025-02-03 2025-02-04 2025-02-05 2025-02-06 2025-02-07 2025-02-10 2025-02-11
2025-02-12 2025-02-13 2025-02-14 2025-02-18 2025-02-19 2025-02-20 2025-02-21
2025-02-24 2025-02-25 2025-02-26 2025-02-27 2025-02-28 2025-03-03 2025-03-04
2025-03-05 2025-03-06 2025-03-07 2025-03-10 2025-03-11 2025-03-12 2025-03-13
2025-03-14 2025-03-17 2025-03-18 2025-03-19 2025-03-20 2025-03-21 2025-03-24
2025-03-25 2025-03-26 2025-03-27 2025-03-28 2025-03-31 2025-04-01 2025-04-02
2025-04-03 2025-04-04 2025-04-07 2025-04-08 2025-04-09 2025-04-10 2025-04-11
2025-04-14 2025-04-15 2025-04-16 2025-04-17 2025-04-21 2025-04-22 2025-04-23
2025-04-24 2025-04-25 2025-04-28 2025-04-29 2025-04-30 2025-05-01 2025-05-02
2025-05-05 2025-05-06 2025-05-07 2025-05-08 2025-05-09 2025-05-12 2025-05-13
2025-05-14 2025-05-15
"""


def fixture_instant(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), NY).astimezone(timezone.utc)


def fixture_projection(value):
    """Exact JSON projection of fixture values, without permissive str fallback."""
    if type(value) in (str, int, bool) or value is None:
        return value
    if type(value) is Decimal:
        return decimal_text(value)
    if type(value) in (date, datetime):
        return value.isoformat()
    if type(value) in (list, tuple):
        return [fixture_projection(v) for v in value]
    if type(value) is dict and all(type(k) is str for k in value):
        return {k: fixture_projection(v) for k, v in value.items()}
    raise ValueError("unsupported fixture projection type")


@dataclass(frozen=True, slots=True)
class FixtureCorpus:
    schedule: PinnedSchedule
    archive: FixtureArchive
    references: tuple[DatedSecurity, ...]
    bars: tuple[RawDailyBar, ...]

    @property
    def sha256(self) -> str:
        return hash_payload({
            "schema": "gdr.synthetic.corpus.v1", "recipe": "constant-prices-50-and-100-v1",
            "schedule": self.schedule.sha256, "archive": self.archive.head_sha256,
            "references": fixture_projection([asdict(r) for r in self.references]),
            "bars": fixture_projection([asdict(b) for b in self.bars]),
        })


def example_corpus() -> FixtureCorpus:
    days = tuple(date.fromisoformat(d) for d in DATES.split())
    schedule = PinnedSchedule(tuple(Session(d, fixture_instant(d, 9, 30), fixture_instant(d, 16))
                                    for d in days), days[0], days[-1], "SYN-GDR-EXAMPLE-1")
    def disclosure(identity, day, revenue, eps):
        clock = f"{day}T12:00:00Z"
        return NormalizedDisclosure.from_dict({
            "schema": "gdr.synthetic.disclosure.v1", "issuer_id": "SYN-ISSUER-A",
            "disclosure_id": identity, "version": 1, "kind": "disclosure",
            "published_at": clock, "received_at": f"{day}T12:01:00Z",
            "validated_at": f"{day}T12:02:00Z", "supersedes": None,
            "release_type": "official", "positioning": "primary", "metadata": "invented fixture",
            "periods": [{"fiscal_year": 2025, "fiscal_start": "2025-01-01", "fiscal_end": "2025-12-31",
                "period": "FY", "currency": "USD", "revenue_units": "USD_millions",
                "eps_units": "USD_per_share", "revenue_basis": "gaap", "eps_basis": "adj",
                "adjustment_definition": "adj-v1", "share_basis": "shares-v1", "scope": "organic-v1",
                "revenue": {"lower": revenue, "upper": revenue, "kind": "point"},
                "eps": {"lower": eps, "upper": eps, "kind": "point"}}],
        })
    archive = FixtureArchive().append(disclosure("SYN-OLD", "2025-03-03", "100", "1"), bootstrap=True)
    archive = archive.append(disclosure("SYN-RAISE", "2025-04-01", "102", "1.05"))
    known = fixture_instant(days[0], 8)
    reference = DatedSecurity("SYN-SEC-A", "SYN-ISSUER-A", days[0], days[-1], days[0],
        "NYSE", "COMMON_STOCK", True, "technology", "listed", Availability("mapping", known, known, known))
    bars = tuple(RawDailyBar("SYN-SEC-A", s.session_date, Decimal("50"), 500000,
                  Availability("history", s.close_utc, s.close_utc, s.close_utc)) for s in schedule.sessions)
    return FixtureCorpus(schedule, archive, (reference,), bars)
