"""Focused neutral reference contracts; all rows are invented and local."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import unittest
from zoneinfo import ZoneInfo

from research.guidance_revision_drift.research_reference import (
    CalendarInput, CalendarSession, ReferenceBook, ResearchReferenceError,
)


NY = ZoneInfo("America/New_York")


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def instant(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), NY).astimezone(timezone.utc)


def invented_calendar(count: int = 105) -> CalendarInput:
    dates = []
    cursor = date(2025, 9, 2)
    while len(dates) < count:
        # A supplied weekday omission is accepted; the contract does not infer holidays.
        if cursor.weekday() < 5 and cursor != date(2025, 10, 13):
            dates.append(cursor)
        cursor += timedelta(days=1)
    return CalendarInput.from_dict({
        "schema": "gdr.research-calendar.v1",
        "calendar_id": "INVENTED-NYSE-CALENDAR",
        "source_sha256": "a" * 64,
        "covered_from": dates[0].isoformat(),
        "covered_through": dates[-1].isoformat(),
        "sessions": [{"date": d.isoformat(), "open_utc": stamp(instant(d, 9, 30)),
                      "close_utc": stamp(instant(d, 16))} for d in dates],
    })


def invented_book(calendar: CalendarInput, entry_index: int = 75) -> ReferenceBook:
    sessions = calendar.sessions
    old_clock = "2025-09-01T00:00:00Z"
    references = [
        {"security_id": "PERM-A", "issuer_id": "ISSUER-A", "symbol": "A",
         "exchange": "NASDAQ", "instrument_type": "COMMON_STOCK", "primary": True,
         "sector": "TECH", "status": "listed", "listed_on": sessions[0].session_date.isoformat(),
         "valid_from": sessions[0].session_date.isoformat(),
         "valid_through": sessions[-1].session_date.isoformat(),
         "published_at": old_clock, "received_at": old_clock, "validated_at": old_clock},
        {"security_id": "PERM-SPY", "issuer_id": "FUND-SPY", "symbol": "SPY",
         "exchange": "NYSE", "instrument_type": "ETF", "primary": True,
         "sector": None, "status": "listed", "listed_on": sessions[0].session_date.isoformat(),
         "valid_from": sessions[0].session_date.isoformat(),
         "valid_through": sessions[-1].session_date.isoformat(),
         "published_at": old_clock, "received_at": old_clock, "validated_at": old_clock},
    ]
    bars = []
    for session in sessions[entry_index - 20:entry_index]:
        for security, close, volume in (("PERM-A", "20", 2_000_000),
                                         ("PERM-SPY", "500", 1_000_000)):
            published = session.close_utc
            bars.append({
                "security_id": security, "session_date": session.session_date.isoformat(),
                "raw_close": close, "volume": volume,
                "published_at": stamp(published),
                "received_at": stamp(published + timedelta(minutes=1)),
                "validated_at": stamp(published + timedelta(minutes=2)),
            })
    return ReferenceBook.from_dict({
        "schema": "gdr.research-reference.v1", "calendar_sha256": calendar.sha256,
        "references": references, "daily_bars": bars,
    })


class CalendarInputTests(unittest.TestCase):
    def test_exact_calendar_and_times(self):
        calendar = invented_calendar()
        self.assertEqual(len(calendar.sessions), 105)
        self.assertIs(type(calendar.sessions[0]), CalendarSession)
        self.assertEqual(calendar.index(calendar.sessions[75].session_date), 75)
        cutoff = calendar.cutoff(calendar.sessions[75].session_date)
        self.assertEqual(cutoff, instant(calendar.sessions[74].session_date, 18))
        window = calendar.entry_window(instant(calendar.sessions[70].session_date, 16))
        self.assertEqual(window, tuple(s.session_date for s in calendar.sessions[73:76]))
        self.assertEqual(calendar.time_exit(calendar.sessions[75].session_date),
                         calendar.sessions[95].session_date)
        self.assertEqual(CalendarInput.from_bytes(calendar.canonical_bytes).sha256, calendar.sha256)
        self.assertEqual(calendar.to_dict()["source_sha256"], "a" * 64)

    def test_supplied_calendar_refuses_ambiguity_and_protected_callbacks(self):
        calendar = invented_calendar()
        body = calendar.to_dict()
        changed = deepcopy(body)
        changed["sessions"][1] = changed["sessions"][0]
        with self.assertRaises(ResearchReferenceError):
            CalendarInput.from_dict(changed)
        changed = deepcopy(body)
        changed["sessions"][1]["open_utc"] = changed["sessions"][1]["close_utc"]
        with self.assertRaises(ResearchReferenceError):
            CalendarInput.from_dict(changed)
        with self.assertRaises(ResearchReferenceError):
            CalendarInput.from_bytes(calendar.canonical_bytes + b"\n")
        extended = deepcopy(body)
        future = date(2026, 9, 1)
        extended["covered_through"] = future.isoformat()
        extended["sessions"].append({
            "date": future.isoformat(), "open_utc": stamp(instant(future, 9, 30)),
            "close_utc": stamp(instant(future, 16)),
        })
        future_calendar = CalendarInput.from_dict(extended)
        self.assertEqual(future_calendar.index(future), 105)
        for callback in (
            lambda: future_calendar.cutoff(future),
            lambda: future_calendar.time_exit(future),
            lambda: future_calendar.entry_window(instant(future, 9)),
        ):
            with self.subTest(callback=callback), self.assertRaises(ResearchReferenceError):
                callback()


class ReferenceBookTests(unittest.TestCase):
    def setUp(self):
        self.calendar = invented_calendar()
        self.entry = self.calendar.sessions[75].session_date
        self.book = invented_book(self.calendar)

    def test_stock_and_benchmark_are_structural_only(self):
        stock = self.book.eligibility(self.calendar, "PERM-A", self.entry)
        benchmark = self.book.eligibility(self.calendar, "PERM-SPY", self.entry, role="benchmark")
        self.assertTrue(stock["eligible"])
        self.assertEqual(stock["reasons"], [])
        self.assertEqual(stock["previous_close"], "20")
        self.assertEqual(Decimal(stock["adv20"]), Decimal("40000000"))
        self.assertEqual(stock["completed_listing_sessions"], 75)
        self.assertTrue(benchmark["eligible"])
        self.assertEqual(Decimal(benchmark["adv20"]), Decimal("500000000"))
        self.assertIsNone(benchmark["completed_listing_sessions"])
        self.assertEqual(benchmark["symbol"], "SPY")
        for result in (stock, benchmark):
            self.assertEqual(result["reference_sha256"], self.book.sha256)
            self.assertEqual(result["calendar_sha256"], self.calendar.sha256)
            for field in ("provenance_verified", "source_rights_verified",
                          "calendar_verified", "point_in_time_data", "execution_authority"):
                self.assertIs(result[field], False)

    def test_as_of_slicing_preserves_visible_ambiguity_and_no_future_rows(self):
        body = self.book.to_dict()
        later = deepcopy(body["references"][0])
        later["symbol"] = "NEW"
        later["published_at"] = later["received_at"] = later["validated_at"] = "2026-08-01T00:00:00Z"
        body["references"].append(later)
        book = ReferenceBook.from_dict(body)
        before = book.eligibility(self.calendar, "PERM-A", self.entry)
        self.assertTrue(before["eligible"])
        self.assertEqual(before["symbol"], "A")
        visible = deepcopy(body)
        visible["references"][-1]["published_at"] = "2025-09-01T00:00:01Z"
        visible["references"][-1]["received_at"] = "2025-09-01T00:00:02Z"
        visible["references"][-1]["validated_at"] = "2025-09-01T00:00:03Z"
        ambiguous = ReferenceBook.from_dict(visible).eligibility(self.calendar, "PERM-A", self.entry)
        self.assertFalse(ambiguous["eligible"])
        self.assertIn("ambiguous_dated_security_mapping", ambiguous["reasons"])

    def test_missing_or_late_history_refuses_without_fallback(self):
        body = self.book.to_dict()
        stock_bars = [row for row in body["daily_bars"] if row["security_id"] == "PERM-A"]
        missing = deepcopy(body)
        missing["daily_bars"].remove(stock_bars[-1])
        report = ReferenceBook.from_dict(missing).eligibility(self.calendar, "PERM-A", self.entry)
        self.assertIn("missing_history_session", report["reasons"])
        self.assertIsNone(report["adv20"])
        late = deepcopy(body)
        target = next(row for row in late["daily_bars"]
                      if row["security_id"] == "PERM-A" and row["session_date"] == stock_bars[-1]["session_date"])
        target["validated_at"] = "2026-08-01T00:00:00Z"
        report = ReferenceBook.from_dict(late).eligibility(self.calendar, "PERM-A", self.entry)
        self.assertIn("history_unavailable_at_cutoff", report["reasons"])
        self.assertIsNone(report["previous_close"])

    def test_stock_thresholds_and_benchmark_role_are_distinct(self):
        body = self.book.to_dict()
        for row in body["daily_bars"]:
            if row["security_id"] == "PERM-A":
                row["raw_close"] = "4"
                row["volume"] = 1
        report = ReferenceBook.from_dict(body).eligibility(self.calendar, "PERM-A", self.entry)
        self.assertIn("previous_raw_close_below_5", report["reasons"])
        self.assertIn("adv20_below_20000000", report["reasons"])
        spy = ReferenceBook.from_dict(body).eligibility(self.calendar, "PERM-SPY", self.entry, role="benchmark")
        self.assertTrue(spy["eligible"])
        wrong = ReferenceBook.from_dict(body).eligibility(self.calendar, "PERM-A", self.entry, role="benchmark")
        self.assertIn("benchmark_identity_or_type_mismatch", wrong["reasons"])

    def test_hash_binding_clock_order_and_invalid_inputs(self):
        self.assertEqual(ReferenceBook.from_bytes(self.book.canonical_bytes).sha256, self.book.sha256)
        body = self.book.to_dict()
        changed = deepcopy(body)
        changed["daily_bars"][0]["volume"] += 1
        self.assertNotEqual(ReferenceBook.from_dict(changed).sha256, self.book.sha256)
        changed = deepcopy(body)
        changed["calendar_sha256"] = "b" * 64
        with self.assertRaises(ResearchReferenceError):
            ReferenceBook.from_dict(changed).eligibility(self.calendar, "PERM-A", self.entry)
        changed = deepcopy(body)
        changed["daily_bars"][0]["received_at"] = "2025-01-01T00:00:00Z"
        with self.assertRaises(ResearchReferenceError):
            ReferenceBook.from_dict(changed)
        changed = deepcopy(body)
        changed["daily_bars"][0]["volume"] = True
        with self.assertRaises(ResearchReferenceError):
            ReferenceBook.from_dict(changed)
        with self.assertRaises(ResearchReferenceError):
            self.book.eligibility(self.calendar, "PERM-A", self.entry, role="unknown")


if __name__ == "__main__":
    unittest.main()
