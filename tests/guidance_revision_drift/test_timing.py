"""Synthetic calendar/clock tests; dates are explicit fixtures, not market evidence."""
from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, Inexact, Rounded, localcontext
from zoneinfo import ZoneInfo

from research.guidance_revision_drift.timing import (
    Availability, PinnedSchedule, RankedCandidate, REQUIRED_INPUT_NAMES, Session,
    TimingError, availability_refusals, decision_cutoff, entry_window,
    execution_times, historical_update_refusals, rank_candidates,
    select_entry_opportunity, time_exit_session,
)


NY = ZoneInfo("America/New_York")


def day(value):
    return date.fromisoformat(value)


def ny(value, hour=18, minute=0):
    return datetime.combine(day(value), time(hour, minute), NY).astimezone(timezone.utc)


def schedule(values="2024-03-07 2024-03-08 2024-03-11 2024-03-12 2024-03-13 2024-03-14 2024-03-15 2024-03-18"):
    dates = values.split()
    return PinnedSchedule(tuple(Session(day(d), ny(d, 9, 30), ny(d, 16)) for d in dates),
                          day(dates[0]), day(dates[-1]), "SYNTHETIC-test-calendar")


def inputs(received=None):
    received = ny("2024-03-08", 17) if received is None else received
    return tuple(Availability(name, ny("2024-03-08", 12), received, received) for name in REQUIRED_INPUT_NAMES)


class TimingTests(unittest.TestCase):
    def test_publication_is_strictly_before_cutoff_while_receipt_can_equal_it(self):
        cutoff = ny("2024-03-12")
        self.assertEqual(availability_refusals(Availability(
            "payload", cutoff - timedelta(microseconds=1), cutoff, cutoff), cutoff), ())
        self.assertIn("payload:publication_must_precede_cutoff", availability_refusals(
            Availability("payload", cutoff, cutoff, cutoff), cutoff))

    def test_d_plus_three_is_strict_after_announcement_and_dst_changes_cutoff(self):
        fixture = schedule()
        self.assertEqual(entry_window(fixture, day("2024-03-08")), tuple(map(day, ("2024-03-13", "2024-03-14", "2024-03-15"))))
        self.assertEqual(decision_cutoff(fixture, day("2024-03-08")).hour, 23)
        self.assertEqual(decision_cutoff(fixture, day("2024-03-13")).hour, 22)
        self.assertEqual(execution_times(fixture, day("2024-03-13")), (ny("2024-03-13", 10), ny("2024-03-13", 10, 5)))

    def test_holiday_absence_and_early_close_are_respected(self):
        base = schedule("2024-07-02 2024-07-03 2024-07-05 2024-07-08 2024-07-09 2024-07-10 2024-07-11")
        sessions = tuple(replace(s, close_utc=ny("2024-07-03", 13)) if s.session_date == day("2024-07-03") else s for s in base.sessions)
        fixture = replace(base, sessions=sessions)
        self.assertEqual(entry_window(fixture, day("2024-07-03"))[0], day("2024-07-09"))
        self.assertEqual(entry_window(fixture, day("2024-07-04"))[0], day("2024-07-09"))
        self.assertEqual(decision_cutoff(fixture, day("2024-07-05")), ny("2024-07-03", 18))

    def test_exact_cutoff_passes_but_one_microsecond_late_delays_without_backdating(self):
        fixture = schedule()
        cutoff = ny("2024-03-12")
        at = select_entry_opportunity(fixture, day("2024-03-08"), inputs(cutoff))
        late = select_entry_opportunity(fixture, day("2024-03-08"), inputs(cutoff + timedelta(microseconds=1)))
        self.assertEqual(at.eligible_session, day("2024-03-13"))
        self.assertEqual(late.eligible_session, day("2024-03-14"))
        self.assertEqual(len(late.missed_opportunities), 1)
        self.assertFalse(at.point_in_time_data)
        self.assertFalse(at.execution_authorized)

    def test_last_opportunity_cutoff_and_stale_event(self):
        fixture = schedule()
        final = ny("2024-03-14")
        self.assertEqual(select_entry_opportunity(fixture, day("2024-03-08"), inputs(final)).eligible_session, day("2024-03-15"))
        stale = select_entry_opportunity(fixture, day("2024-03-08"), inputs(final + timedelta(microseconds=1)))
        self.assertIsNone(stale.eligible_session)
        self.assertIn("stale_event", stale.refusal_reasons)
        self.assertEqual(len(stale.missed_opportunities), 3)

    def test_missing_required_and_additional_inputs_gate_and_receipt_ingestion_both_matter(self):
        fixture = schedule()
        missing = select_entry_opportunity(fixture, day("2024-03-08"), inputs()[:-1])
        self.assertIn("missing_required_input:history", missing.refusal_reasons)
        for field in ("published_at", "received_at", "ingested_at"):
            with self.subTest(field=field):
                first = replace(inputs()[0], **{field: None})
                result = select_entry_opportunity(fixture, day("2024-03-08"), (first,) + inputs()[1:])
                self.assertIsNone(result.eligible_session)
        additional = inputs() + (Availability("split_basis", None, None, None),)
        self.assertIsNone(select_entry_opportunity(fixture, day("2024-03-08"), additional).eligible_session)
        lagged = (replace(inputs()[0], ingested_at=ny("2024-03-13", 19)),) + inputs()[1:]
        self.assertEqual(select_entry_opportunity(fixture, day("2024-03-08"), lagged).eligible_session, day("2024-03-15"))

    def test_invalid_clock_order_never_passes_a_later_cutoff(self):
        for clock in (Availability("payload", ny("2024-03-08", 17), ny("2024-03-08", 16), ny("2024-03-08", 18)),
                      Availability("payload", ny("2024-03-08", 12), ny("2024-03-08", 17), ny("2024-03-08", 16))):
            self.assertTrue(availability_refusals(clock, ny("2024-03-14")))
            self.assertIsNone(select_entry_opportunity(schedule(), day("2024-03-08"), (clock,) + inputs()[1:]).eligible_session)

    def test_missing_ambiguous_date_and_consumed_attempt_refuse(self):
        self.assertIn("unresolved_announcement_date", select_entry_opportunity(schedule(), None, inputs()).refusal_reasons)
        self.assertIn("entry_attempt_already_consumed", select_entry_opportunity(schedule(), day("2024-03-08"), inputs(), attempt_already_made=True).refusal_reasons)
        shifted = (replace(inputs()[0], published_at=ny("2024-03-11", 12), received_at=ny("2024-03-11", 13), ingested_at=ny("2024-03-11", 13)),) + inputs()[1:]
        self.assertIn("announcement_precedes_publication_date", select_entry_opportunity(schedule(), day("2024-03-08"), shifted).refusal_reasons)

    def test_date_only_update_strictly_precedes_new_york_cutoff_date(self):
        cutoff = ny("2024-03-12")
        self.assertEqual(historical_update_refusals(day("2024-03-11"), cutoff), ())
        self.assertTrue(historical_update_refusals(day("2024-03-12"), cutoff))
        self.assertEqual(historical_update_refusals(cutoff, cutoff), ())
        self.assertTrue(historical_update_refusals(cutoff + timedelta(microseconds=1), cutoff))
        self.assertTrue(historical_update_refusals(None, cutoff))
        with self.assertRaises(TimingError):
            historical_update_refusals(datetime(2024, 3, 12), cutoff)

    def test_twenty_intervals_exit_on_twenty_first_session_and_never_extend_schedule(self):
        fixture = schedule("2024-01-02 2024-01-03 2024-01-04 2024-01-05 2024-01-08 2024-01-09 2024-01-10 2024-01-11 2024-01-12 2024-01-16 2024-01-17 2024-01-18 2024-01-19 2024-01-22 2024-01-23 2024-01-24 2024-01-25 2024-01-26 2024-01-29 2024-01-30 2024-01-31")
        self.assertEqual(time_exit_session(fixture, day("2024-01-02")), day("2024-01-31"))
        with self.assertRaises(TimingError):
            time_exit_session(fixture, day("2024-01-03"))

    def test_schedule_identity_immutability_and_revalidation(self):
        fixture = schedule()
        self.assertEqual(fixture.sha256, schedule().sha256)
        self.assertNotEqual(fixture.sha256, replace(fixture, schedule_id="SYN-other").sha256)
        with self.assertRaises(FrozenInstanceError):
            fixture.schedule_id = "changed"
        object.__setattr__(fixture, "schedule_id", "forged")
        with self.assertRaisesRegex(TimingError, "changed"):
            entry_window(fixture, day("2024-03-08"))

    def test_bad_schedule_and_timestamp_types_are_rejected(self):
        fixture = schedule()
        for changes in ({"sessions": list(fixture.sessions)}, {"sessions": tuple(reversed(fixture.sessions))},
                        {"sessions": fixture.sessions + fixture.sessions[-1:]}, {"provenance": "verified_real_calendar"},
                        {"exchange": "NASDAQ"}, {"covered_from": datetime(2024, 3, 7)}):
            with self.subTest(changes=changes), self.assertRaises(TimingError):
                replace(fixture, **changes)
        for bad in (True, 1.0, datetime(2024, 3, 8), datetime(2024, 3, 8, tzinfo=NY)):
            with self.subTest(bad=bad), self.assertRaises(TimingError):
                Availability("payload", bad, None, None)
        with self.assertRaises(TimingError):
            decision_cutoff(fixture, day("2024-03-07"))
        with self.assertRaises(TimingError):
            entry_window(fixture, day("2024-03-01"))
        with self.assertRaises(TimingError):
            entry_window(fixture, day("2024-03-18"))
        with self.assertRaises(TimingError):
            select_entry_opportunity(fixture, day("2024-03-08"), inputs() + inputs()[:1])

    def test_exact_ranking_beats_rounded_ratios_with_adversarial_context(self):
        def candidate(identity, revenue, eps="1.05", eligible="2024-03-13"):
            return RankedCandidate("event-" + identity, identity, day(eligible), Decimal("100"), Decimal(revenue), Decimal("1"), Decimal(eps))
        low = candidate("AAA", "102.0000000000000000000000000000001")
        high = candidate("ZZZ", "102.0000000000000000000000000000002")
        eps = candidate("YYY", "102.0000000000000000000000000000002", "1.0500000000000000000000000000001")
        earlier = candidate("BBB", "102", eligible="2024-03-12")
        tied = candidate("CCC", "102.0000000000000000000000000000002")
        with localcontext() as ctx:
            ctx.prec = 2
            ctx.traps[Inexact] = True
            ctx.traps[Rounded] = True
            result = rank_candidates((high, low, eps, earlier, tied))
        self.assertEqual(tuple(c.permanent_security_id for c in result), ("BBB", "YYY", "CCC", "ZZZ", "AAA"))
        with self.assertRaises(TimingError):
            rank_candidates((low, low))
        for bad in (True, 1.02, Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                replace(low, current_revenue_sum=bad)


if __name__ == "__main__":
    unittest.main()
