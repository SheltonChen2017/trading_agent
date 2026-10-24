"""Synthetic dated-universe boundaries; no licensed data or return observations."""
from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, Inexact, Rounded, localcontext
from zoneinfo import ZoneInfo

from research.guidance_revision_drift.timing import Availability, PinnedSchedule, Session, TimingError
from research.guidance_revision_drift.universe import DatedSecurity, RawDailyBar, evaluate_universe


NY = ZoneInfo("America/New_York")
# Explicit synthetic fixture coverage. This is not a verified exchange calendar.
DATES = """2024-01-02 2024-01-03 2024-01-04 2024-01-05 2024-01-08 2024-01-09
2024-01-10 2024-01-11 2024-01-12 2024-01-16 2024-01-17 2024-01-18 2024-01-19
2024-01-22 2024-01-23 2024-01-24 2024-01-25 2024-01-26 2024-01-29 2024-01-30
2024-01-31 2024-02-01 2024-02-02 2024-02-05 2024-02-06 2024-02-07 2024-02-08
2024-02-09 2024-02-12 2024-02-13 2024-02-14 2024-02-15 2024-02-16 2024-02-20
2024-02-21 2024-02-22 2024-02-23 2024-02-26 2024-02-27 2024-02-28 2024-02-29
2024-03-01 2024-03-04 2024-03-05 2024-03-06 2024-03-07 2024-03-08 2024-03-11
2024-03-12 2024-03-13 2024-03-14 2024-03-15 2024-03-18 2024-03-19 2024-03-20
2024-03-21 2024-03-22 2024-03-25 2024-03-26 2024-03-27 2024-03-28 2024-04-01
2024-04-02 2024-04-03 2024-04-04 2024-04-05""".split()


def clock(value, hour=18):
    return datetime.combine(date.fromisoformat(value), time(hour), NY).astimezone(timezone.utc)


def fixtures():
    sessions = tuple(Session(date.fromisoformat(d), datetime.combine(date.fromisoformat(d), time(9, 30), NY).astimezone(timezone.utc), clock(d, 16)) for d in DATES)
    schedule = PinnedSchedule(sessions, sessions[0].session_date, sessions[-1].session_date, "SYNTHETIC-universe-calendar")
    mapping_time = clock(DATES[0], 9)
    security = DatedSecurity("SYN-A", "SYN-ISSUER-A", sessions[0].session_date, sessions[-1].session_date,
                             sessions[0].session_date, "NYSE", "COMMON_STOCK", True, "technology", "listed",
                             Availability("mapping", mapping_time, mapping_time, mapping_time))
    entry = sessions[60].session_date
    bars = tuple(RawDailyBar("SYN-A", s.session_date, Decimal("5"), 4000000,
                            Availability("history", s.close_utc, s.close_utc, s.close_utc)) for s in sessions[40:60])
    return dict(schedule=schedule, entry_session=entry, opportunity_id="SYN-OPPORTUNITY", permanent_security_id="SYN-A", references=(security,), bars=bars)


class UniverseTests(unittest.TestCase):
    def test_exact_price_liquidity_and_listing_boundaries_pass(self):
        result = evaluate_universe(**fixtures())
        self.assertTrue(result.eligible)
        self.assertEqual(result.previous_close, Decimal("5"))
        self.assertEqual(result.adv20, Decimal("20000000"))
        self.assertEqual(result.completed_listing_sessions, 60)
        self.assertEqual(result.refusal_reasons, ())
        self.assertFalse(result.point_in_time_data)
        self.assertFalse(result.execution_authorized)

    def test_price_and_adv_just_below_refuse_exactly(self):
        args = fixtures()
        below = replace(args["bars"][-1], raw_close=Decimal("4.9999999999999999999999999999999"))
        result = evaluate_universe(**dict(args, bars=args["bars"][:-1] + (below,)))
        self.assertIn("previous_raw_close_below_5", result.refusal_reasons)
        self.assertIn("adv20_below_20000000", result.refusal_reasons)
        low_volume = replace(args["bars"][0], volume=3999999)
        result = evaluate_universe(**dict(args, bars=(low_volume,) + args["bars"][1:]))
        self.assertNotIn("previous_raw_close_below_5", result.refusal_reasons)
        self.assertIn("adv20_below_20000000", result.refusal_reasons)

    def test_listing_history_does_not_borrow_sessions_before_listing_or_outside_coverage(self):
        args = fixtures()
        security = args["references"][0]
        too_new = replace(security, listed_on=args["schedule"].sessions[1].session_date)
        result = evaluate_universe(**dict(args, references=(too_new,)))
        self.assertEqual(result.completed_listing_sessions, 59)
        self.assertIn("fewer_than_60_completed_listing_sessions", result.refusal_reasons)
        old = replace(security, listed_on=date(2023, 1, 1))
        result = evaluate_universe(**dict(args, references=(old,)))
        self.assertEqual(result.completed_listing_sessions, 60)
        self.assertTrue(result.eligible)
        shorter = replace(args["schedule"], sessions=args["schedule"].sessions[1:], covered_from=args["schedule"].sessions[1].session_date)
        result = evaluate_universe(**dict(args, schedule=shorter, references=(old,)))
        self.assertEqual(result.completed_listing_sessions, 59)
        self.assertIn("insufficient_listing_schedule_evidence", result.refusal_reasons)

    def test_exact_previous_twenty_sessions_not_any_twenty_surviving_rows(self):
        args = fixtures()
        for bars, reason in ((args["bars"][:-1], "history_requires_exactly_20_rows"),
                             (args["bars"][:-1] + args["bars"][:1], "duplicate_history_session"),
                             (args["bars"][:-1] + (replace(args["bars"][-1], session_date=args["entry_session"]),), "history_date_not_in_previous_20_sessions"),
                             (args["bars"][:-1] + (replace(args["bars"][-1], session_date=args["schedule"].sessions[39].session_date),), "history_date_not_in_previous_20_sessions")):
            with self.subTest(reason=reason):
                result = evaluate_universe(**dict(args, bars=bars))
                self.assertFalse(result.eligible)
                self.assertIn(reason, result.refusal_reasons)
                self.assertIsNone(result.adv20)

    def test_history_input_order_irrelevant_but_wrong_identity_refuses(self):
        args = fixtures()
        self.assertEqual(evaluate_universe(**args), evaluate_universe(**dict(args, bars=tuple(reversed(args["bars"])))))
        bad = replace(args["bars"][0], permanent_security_id="REUSED-TICKER-DIFFERENT-ID")
        result = evaluate_universe(**dict(args, bars=(bad,) + args["bars"][1:]))
        self.assertIn("history_security_identity_mismatch", result.refusal_reasons)

    def test_missing_invalid_and_inactive_companies_are_retained_with_identity(self):
        args = fixtures()
        for references, reason in (((), "missing_dated_security_mapping"), ((object(),), "invalid_security_reference"),
                                   ((replace(args["references"][0], status="delisted"),), "security_not_listed:delisted")):
            with self.subTest(reason=reason):
                result = evaluate_universe(**dict(args, references=references))
                self.assertEqual(result.opportunity_id, "SYN-OPPORTUNITY")
                self.assertEqual(result.permanent_security_id, "SYN-A")
                self.assertFalse(result.eligible)
                self.assertIn(reason, result.refusal_reasons)
        inactive = evaluate_universe(**dict(args, references=(replace(args["references"][0], status="delisted"),)))
        self.assertEqual(inactive.status, "delisted")

    def test_dated_mapping_overlap_current_table_and_missing_sector_refuse(self):
        args = fixtures()
        security = args["references"][0]
        for references, reason in (((security, security), "ambiguous_dated_security_mapping"),
                                   ((replace(security, valid_from=date(2024, 4, 1)),), "missing_dated_security_mapping"),
                                   ((replace(security, valid_through=date(2024, 3, 27)),), "missing_dated_security_mapping"),
                                   ((replace(security, sector=None),), "missing_dated_sector")):
            with self.subTest(reason=reason):
                self.assertIn(reason, evaluate_universe(**dict(args, references=references)).refusal_reasons)

    def test_all_nonbaseline_security_classes_and_nonprimary_shares_refuse(self):
        args = fixtures()
        security = args["references"][0]
        for instrument in ("ADR", "ETF", "PREFERRED", "WARRANT", "UNIT", "REIT", "FFO"):
            with self.subTest(instrument=instrument):
                self.assertIn("not_primary_common_share", evaluate_universe(**dict(args, references=(replace(security, instrument_type=instrument),))).refusal_reasons)
        self.assertIn("not_primary_common_share", evaluate_universe(**dict(args, references=(replace(security, primary=False),))).refusal_reasons)
        self.assertIn("ineligible_exchange", evaluate_universe(**dict(args, references=(replace(security, exchange="OTC"),))).refusal_reasons)

    def test_late_mapping_or_history_and_premature_daily_bar_publication_refuse(self):
        args = fixtures()
        late = clock(args["entry_session"].isoformat(), 9)
        security = args["references"][0]
        delayed = replace(security, availability=replace(security.availability, ingested_at=late))
        self.assertIn("mapping:ingested_at_after_cutoff", evaluate_universe(**dict(args, references=(delayed,))).refusal_reasons)
        bar = args["bars"][-1]
        delayed_bar = replace(bar, availability=replace(bar.availability, received_at=late, ingested_at=late))
        result = evaluate_universe(**dict(args, bars=args["bars"][:-1] + (delayed_bar,)))
        self.assertIn("history:received_at_after_cutoff", result.refusal_reasons)
        premature = replace(bar, availability=replace(bar.availability, published_at=bar.availability.published_at - timedelta(seconds=1)))
        self.assertIn("daily_bar_publication_before_session_close", evaluate_universe(**dict(args, bars=args["bars"][:-1] + (premature,))).refusal_reasons)

    def test_missing_and_nonpositive_bar_values_refuse_without_zero_substitution(self):
        args = fixtures()
        for changes, reason in (({"raw_close": None}, "missing_or_nonpositive_raw_close"),
                                ({"raw_close": Decimal("0")}, "missing_or_nonpositive_raw_close"),
                                ({"raw_close": Decimal("-1")}, "missing_or_nonpositive_raw_close"),
                                ({"volume": None}, "missing_volume")):
            with self.subTest(changes=changes):
                bars = (replace(args["bars"][0], **changes),) + args["bars"][1:]
                result = evaluate_universe(**dict(args, bars=bars))
                self.assertIn(reason, result.refusal_reasons)
                self.assertIsNone(result.adv20)

    def test_bool_float_nan_and_mutated_contracts_refuse(self):
        args = fixtures()
        bar = args["bars"][0]
        for bad in (True, 5.0, Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                replace(bar, raw_close=bad)
        for bad in (True, 4000000.0, -1, 10**19):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                replace(bar, volume=bad)
        with self.assertRaises(FrozenInstanceError):
            bar.volume = 1
        object.__setattr__(bar, "raw_close", True)
        self.assertIn("invalid_history_row", evaluate_universe(**args).refusal_reasons)

    def test_ambient_decimal_context_cannot_change_eligibility_or_adv(self):
        args = fixtures()
        expected = evaluate_universe(**args)
        with localcontext() as context:
            context.prec = 2
            context.Emin = -2
            context.Emax = 2
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            self.assertEqual(evaluate_universe(**args), expected)


if __name__ == "__main__":
    unittest.main()
