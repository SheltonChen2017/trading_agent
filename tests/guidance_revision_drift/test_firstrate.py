"""Invented FirstRate rows only; no USB, provider or runtime access."""
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from itertools import permutations
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes
from research.guidance_revision_drift.firstrate import (
    MAX_LINE_BYTES, FirstRateLine, QuarantinedRow, Reconciliation, ReconciledRow, SourceRef,
    parse_line, reconcile_records, regular_minute,
)
from research.guidance_revision_drift.input_contracts import InputError
from research.guidance_revision_drift.research_reference import CalendarSession


def parsed(raw=b"2025-04-04,10,11,9,10.5,10000\n", *, kind="daily", source="A", line=1, member=None):
    member = member or {"daily": "SYN_full_1day_UNADJUSTED.txt",
                        "minute": "SYN_full_1min_UNADJUSTED.txt",
                        "split": "SYN.txt", "dividend": "SYN_divs.txt"}[kind]
    return parse_line(raw, source_id=source, member=member, line_number=line, symbol="SYN", kind=kind)


def session(day=date(2025, 4, 4), close_hour=20):
    return CalendarSession(day, datetime(day.year, day.month, day.day, 13, 30, tzinfo=timezone.utc),
                           datetime(day.year, day.month, day.day, close_hour, tzinfo=timezone.utc))


class FirstRateTests(unittest.TestCase):
    def test_raw_daily_exact_values_lineage_and_immutable_projection(self):
        raw = b"2025-04-04,10,11,9,10.500000000000000000000001,10000\r\n"
        row = parsed(raw)
        self.assertEqual(row.status, "accepted")
        self.assertEqual(row.values[3], Decimal("10.500000000000000000000001"))
        self.assertEqual(row.source.line_sha256, hash_bytes(raw))
        self.assertEqual(row.key, ("SYN", "daily", "2025-04-04"))
        with self.assertRaises(FrozenInstanceError):
            row.status = "changed"
        projection = row.projection()
        self.assertEqual(projection["provider"], "firstrate")
        self.assertNotIn("values", projection)
        self.assertFalse(projection["point_in_time_data"])
        self.assertFalse(projection["coverage_verified"])
        self.assertFalse(projection["native_execution_evidence"])
        projection["source"]["line_number"] = 99
        self.assertEqual(row.source.line_number, 1)

    def test_date_gate_precedes_payload_hash_and_financial_parser(self):
        for raw in (b"2026-09-01,\xff,NaN,DO_NOT_PARSE\n", b"2012-12-31,\xff\n"):
            with self.subTest(date=raw[:10]), \
                 patch("research.guidance_revision_drift.firstrate.amount", side_effect=AssertionError("payload parsed")), \
                 patch("research.guidance_revision_drift.firstrate.hash_bytes", side_effect=AssertionError("payload hashed")):
                row = parsed(raw)
            self.assertEqual(row.status, "excluded")
            self.assertIsNone(row.key)
            self.assertIsNone(row.source.line_sha256)
            self.assertEqual(row.values, ())
        with patch("research.guidance_revision_drift.firstrate.hash_bytes", side_effect=AssertionError("payload hashed")):
            row = parsed(b"BAD DATE!!,not-readable\n")
        self.assertEqual(row.status, "refused")
        self.assertIsNone(row.source.line_sha256)

    def test_blank_metadata_lines_are_retained_exclusions_not_ambiguous_data(self):
        for raw in (b"\n", b"\r\n", b" \t\r\n"):
            with self.subTest(raw=repr(raw)), \
                 patch("research.guidance_revision_drift.firstrate.hash_bytes", side_effect=AssertionError("hashed blank")):
                row = parsed(raw, source="B")
            self.assertEqual(row.status, "excluded")
            self.assertEqual(row.reasons, ("blank_nondata_line",))
            self.assertIsNone(row.source.line_sha256)
            result = reconcile_records([parsed(), row])
            self.assertFalse(result.refusals)
            self.assertEqual(len(result.excluded), 1)
            self.assertEqual(result.require(("SYN", "daily", "2025-04-04")).values[0], Decimal("10"))

    def test_window_cannot_expand_into_protected_or_earlier_data(self):
        for start, stop in ((date(2012, 1, 1), date(2025, 1, 1)),
                            (date(2013, 1, 1), date(2026, 9, 2)),
                            (date(2025, 1, 1), date(2025, 1, 1))):
            with self.subTest(start=start, stop=stop), self.assertRaises(InputError):
                parse_line(b"2025-04-04,10,11,9,10,1\n", source_id="A",
                           member="SYN_full_1day_UNADJUSTED.txt", line_number=1,
                           symbol="SYN", kind="daily", start=start, stop=stop)
        row = parse_line(b"2025-04-04,not-a-number", source_id="A",
                         member="SYN_full_1day_UNADJUSTED.txt", line_number=1,
                         symbol="SYN", kind="daily", stop=date(2025, 4, 4))
        self.assertEqual(row.status, "excluded")

    def test_numeric_and_range_failures_refuse_with_no_source_value_echo(self):
        values = ("0,11,9,10,1", "-1,11,9,10,1", "NaN,11,9,10,1",
                  "Infinity,11,9,10,1", "10,9,11,10,1", "10,11,9,10,-1",
                  "10,11,9,10,0.5", "10,11,9,10,1000000000001",
                  "1e+,11,9,10,1", "10,11,9,10,true")
        for value in values:
            with self.subTest(case=value):
                row = parsed(("2025-04-04," + value + "\n").encode())
                self.assertEqual(row.status, "refused")
                self.assertEqual(row.key, ("SYN", "daily", "2025-04-04"))
                self.assertEqual(row.values, ())
                self.assertNotIn(value, str(row.projection()))

    def test_scientific_provider_values_are_exact_and_context_independent(self):
        with localcontext() as ctx:
            ctx.prec = 2
            row = parsed(b"2025-04-04,1e1,1.1e1,9E+0,1.05e+1,1.0001e4\n")
            self.assertEqual(row.status, "accepted")
            self.assertEqual(row.values, tuple(Decimal(x) for x in ("10", "11", "9", "10.5", "10001")))
            tiny = parsed(b"2025-04-04,1.000000000000000000000001e-6,2e-6,9e-7,1.1e-6,1e3\n")
            self.assertEqual(tiny.status, "accepted")
            self.assertEqual(tiny.values[0], Decimal("0.000001000000000000000000000001"))
            dividend = parsed(b"2025-04-04,2.5E-7\n", kind="dividend")
            split = parsed(b"2025-04-04,2e0\n", kind="split")
            self.assertEqual(dividend.values, (Decimal("0.00000025"),))
            self.assertEqual(split.values, (Decimal("2"),))
            self.assertIn("dividend_payment_date_missing", dividend.warnings)

    def test_scientific_duplicates_are_numeric_equal_not_conflicting(self):
        scientific = parsed(b"2025-04-04,1e1,1.1e1,9E0,1.05e1,1e4\n", source="A")
        plain = parsed(source="B")
        result = reconcile_records([scientific, plain])
        self.assertEqual(len(result.accepted), 1)
        self.assertFalse(result.quarantined)
        self.assertEqual(len(result.accepted[0].sources), 2)
        self.assertNotEqual(scientific.source.line_sha256, plain.source.line_sha256)
        self.assertEqual(result.accepted[0].projection(include_values=True)["values"],
                         ["10", "11", "9", "10.5", "10000"])

    def test_scientific_grammar_and_existing_magnitude_and_volume_caps_refuse(self):
        for token in (b"1e", b"1e+", b"1e1.0", b"1_e1", b"+1e1", b"01e1",
                      b".1e1", b"1.e1", b" 1e1", b"1e1 ", b"NaN", b"sNaN", b"Inf",
                      b"Infinity", b"-Infinity", b"1e33", b"1e-33", b"1e-1000000",
                      b"1e99999999999999999999999999", b"1" * 65 + b"e0",
                      b"1" * 129, b"\xffe1"):
            with self.subTest(token_length=len(token)):
                row = parsed(b"2025-04-04," + token + b",11,9,10,100\n")
                self.assertEqual(row.status, "refused")
                self.assertEqual(row.values, ())
        for raw in (b"2025-04-04,1e1,1.1e1,9e0,1e1,1.5e-1\n",
                    b"2025-04-04,1e1,1.1e1,9e0,1e1,-1e1\n",
                    b"2025-04-04,0e0,1.1e1,9e0,1e1,1e1\n"):
            self.assertEqual(parsed(raw).status, "refused")

    def test_daily_zero_volume_is_explicit_warning_not_imputed(self):
        row = parsed(b"2025-04-04,10,11,9,10,0\n")
        self.assertEqual(row.status, "accepted")
        self.assertIn("zero_daily_volume_requires_reconciliation", row.warnings)
        self.assertEqual(row.values[-1], 0)
        minute = parsed(b"2025-04-04 10:00:00,10,11,9,10,0\n", kind="minute")
        self.assertEqual(minute.status, "refused")

    def test_numeric_duplicate_formatting_collapses_but_preserves_every_ref(self):
        one = parsed(b"2025-04-04,10,11,9,10.5,10000\n", source="A")
        two = parsed(b"2025-04-04,10.0,11.00,9.0,10.50,10000.0\r\n", source="B")
        with localcontext() as ctx:
            ctx.prec = 2
            result = reconcile_records([two, one])
        self.assertEqual(len(result.accepted), 1)
        self.assertFalse(result.quarantined)
        self.assertEqual(len(result.accepted[0].sources), 2)
        self.assertNotEqual(one.source.line_sha256, two.source.line_sha256)
        self.assertEqual(result.accepted[0].values[3], Decimal("10.5"))
        reverse = reconcile_records([one, two])
        self.assertEqual(result.projection(include_values=True), reverse.projection(include_values=True))

    def test_numeric_conflict_quarantines_whole_key_in_every_order(self):
        records = (parsed(source="A"), parsed(b"2025-04-04,10,12,9,10.5,10000\n", source="B"),
                   parsed(source="C"))
        for order in permutations(records):
            with self.subTest(order=[x.source.source_id for x in order]):
                result = reconcile_records(order)
                self.assertFalse(result.accepted)
                self.assertEqual(len(result.quarantined), 1)
                self.assertIn("conflicting_numeric_values", result.quarantined[0].reasons)
                self.assertEqual(len(result.quarantined[0].sources), 3)
                with self.assertRaisesRegex(InputError, "quarantined"):
                    result.require(records[0].key)

    def test_invalid_copy_poisons_key_even_when_followed_by_valid_duplicate(self):
        invalid = parsed(b"2025-04-04,0,11,9,10.5,10000\n", source="A")
        valid = parsed(source="B")
        for records in ((invalid, valid), (valid, invalid)):
            result = reconcile_records(records)
            self.assertFalse(result.accepted)
            self.assertEqual(len(result.quarantined), 1)
            self.assertEqual(len(result.quarantined[0].sources), 2)

    def test_unkeyed_fault_blocks_source_set_without_hiding_other_rows(self):
        valid = parsed()
        bad = parsed(b"2025-04-04 25:00:00,10,11,9,10,100\n", source="B", kind="minute")
        self.assertIsNone(bad.key)
        result = reconcile_records([valid, bad])
        self.assertEqual(len(result.accepted), 1)
        self.assertEqual(len(result.refusals), 1)
        with self.assertRaisesRegex(InputError, "unkeyed"):
            result.require(valid.key)
        with self.assertRaisesRegex(InputError, "missing"):
            reconcile_records([valid]).require(("SYN", "daily", "2025-04-03"))

    def test_same_source_line_identity_is_idempotent_or_hard_conflict(self):
        row = parsed()
        result = reconcile_records([row, row])
        self.assertEqual(len(result.accepted[0].sources), 1)
        self.assertEqual(result.input_records, 2)
        different = parsed(b"2025-04-04,10,12,9,10.5,10000\n")
        with self.assertRaisesRegex(InputError, "source_line_identity"):
            reconcile_records([row, different])

    def test_strict_raw_member_labels_and_bounded_lineage(self):
        for member in ("../SYN_full_1day_UNADJUSTED.txt", "/SYN_full_1day_UNADJUSTED.txt",
                       "SYN_full_1day_ADJUSTED.txt", "SYN_full_1min_UNADJUSTED.txt",
                       "OTHER_full_1day_UNADJUSTED.txt"):
            with self.subTest(member=member), self.assertRaises(InputError):
                parsed(member=member)
        for raw in (b"", b"x" * (MAX_LINE_BYTES + 1), "not bytes"):
            with self.subTest(kind=type(raw)), self.assertRaises(InputError):
                parsed(raw)
        for value in (0, True, -1):
            with self.subTest(line=value), self.assertRaises(InputError):
                parsed(line=value)
        for kind in (None, True, [], "adjusted"):
            with self.subTest(kind=repr(kind)), self.assertRaises(InputError):
                parse_line(b"x", source_id="A", member="SYN.txt", line_number=1, symbol="SYN", kind=kind)

    def test_budget_exhaustion_never_returns_partial_acceptance(self):
        with self.assertRaisesRegex(InputError, "budget exceeded"):
            reconcile_records([parsed(), parsed(source="B")], max_records=1)
        for budget in (0, True, 100001):
            with self.subTest(budget=budget), self.assertRaises(InputError):
                reconcile_records([], max_records=budget)

    def test_minute_new_york_period_start_conversion_and_regular_bounds(self):
        row = parsed(b"2025-04-04 10:00:00,10,11,9,10,100\n", kind="minute")
        self.assertEqual(row.start_utc, datetime(2025, 4, 4, 14, tzinfo=timezone.utc))
        self.assertEqual(row.end_utc, datetime(2025, 4, 4, 14, 1, tzinfo=timezone.utc))
        reconciled = reconcile_records([row]).require(row.key)
        result = regular_minute(reconciled, session=session(), security_id="SYN-SEC")
        self.assertEqual(result.security_id, "SYN-SEC")
        self.assertEqual(result.symbol, "SYN")
        self.assertEqual(result.open, Decimal("10"))
        self.assertEqual(result.volume, 100)
        self.assertEqual(result.end_timestamp_ns - result.start_timestamp_ns, 60_000_000_000)
        self.assertEqual(reconciled.projection()["provider"], "firstrate")

    def test_dst_offsets_and_ambiguous_or_nonexistent_local_clocks(self):
        before = parsed(b"2025-03-07 10:00:00,10,11,9,10,100\n", kind="minute")
        after = parsed(b"2025-03-10 10:00:00,10,11,9,10,100\n", kind="minute")
        self.assertEqual(before.start_utc.hour, 15)
        self.assertEqual(after.start_utc.hour, 14)
        for stamp in (b"2025-03-09 02:30:00", b"2025-11-02 01:30:00"):
            row = parsed(stamp + b",10,11,9,10,100\n", kind="minute")
            self.assertEqual(row.status, "refused")
            self.assertIn("ambiguous_or_nonexistent_local_minute", row.reasons)

    def test_no_holiday_halfday_or_extended_hour_inference(self):
        for stamp in (b"2025-04-04 09:29:00", b"2025-04-04 16:00:00"):
            row = parsed(stamp + b",10,11,9,10,100\n", kind="minute")
            self.assertEqual(row.status, "accepted")
            selected = reconcile_records([row]).require(row.key)
            with self.assertRaisesRegex(InputError, "outside supplied"):
                regular_minute(selected, session=session(), security_id="SYN-SEC")
        row = parsed(b"2025-04-04 13:00:00,10,11,9,10,100\n", kind="minute")
        selected = reconcile_records([row]).require(row.key)
        with self.assertRaisesRegex(InputError, "outside supplied"):
            regular_minute(selected, session=session(close_hour=17), security_id="SYN-SEC")
        with self.assertRaises(InputError):
            regular_minute(selected, session=None, security_id="SYN-SEC")
        # No official holiday knowledge is claimed: a supplied date is not authenticated.
        self.assertFalse(selected.projection()["calendar_verified"])

    def test_non_whole_minute_and_bad_date_refusals_preserve_safety(self):
        for raw in (b"2025-04-04 10:00:01,10,11,9,10,100\n",
                    b"2025-04-04 10:60:00,10,11,9,10,100\n",
                    b"2025-02-30 10:00:00,10,11,9,10,100\n"):
            row = parsed(raw, kind="minute")
            self.assertEqual(row.status, "refused")
        daily = parsed(b"2025-04-05,10,11,9,10,100\n")
        self.assertEqual(daily.status, "refused")
        self.assertIn("weekend_bar_date", daily.reasons)

    def test_actions_never_invent_payment_currency_identity_or_cash_posting(self):
        dividend = parsed(b"2025-04-04,0.25\n", kind="dividend")
        split = parsed(b"2025-04-04,2\n", kind="split", source="B")
        self.assertEqual(dividend.status, "accepted")
        self.assertEqual(split.status, "accepted")
        rows = reconcile_records([dividend, split]).accepted
        for row in rows:
            body = row.projection(include_values=True)
            for field in ("security_id", "currency", "published_at", "received_at", "validated_at", "payment_date"):
                self.assertIsNone(body[field])
            self.assertFalse(body["cash_posting_permitted"])
            self.assertFalse(body["execution_authority"])
        self.assertEqual(rows[0].projection()["date_role"], "dividend_ex_date")
        self.assertEqual(rows[1].projection()["date_role"], "split_effective_date")
        for kind, raw in (("split", b"2025-04-04,0\n"), ("split", b"2025-04-04,-1\n"),
                          ("dividend", b"2025-04-04,-1\n")):
            self.assertEqual(parsed(raw, kind=kind).status, "refused")
        zero = parsed(b"2025-04-04,0\n", kind="dividend")
        self.assertIn("zero_dividend_requires_reconciliation", zero.warnings)
        weekend = parsed(b"2025-04-05,0.25\n", kind="dividend")
        self.assertEqual(weekend.status, "accepted")
        self.assertIn("action_effective_date_requires_reconciliation", weekend.warnings)

    def test_symbol_is_not_silently_remapped_or_stripped(self):
        row = parse_line(b"2025-04-04,10,11,9,10,100\n", source_id="A",
                         member="SYN-DELISTED_full_1day_UNADJUSTED.txt", line_number=1,
                         symbol="SYN-DELISTED", kind="daily")
        self.assertEqual(row.key[0], "SYN-DELISTED")
        result = reconcile_records([row, parsed()])
        self.assertEqual(len(result.accepted), 2)
        self.assertFalse(result.projection()["reference_mapping_verified"])

    def test_direct_invalid_constructs_cannot_skip_numeric_contract(self):
        with self.assertRaises(InputError):
            ReconciledRow(("SYN", "daily", "2025-04-04"), (Decimal("NaN"),) * 5,
                          (SourceRef("A", "SYN.txt", 1, "a" * 64),), ())
        with self.assertRaises(InputError):
            FirstRateLine("excluded", None, (), ("protected_date",), (),
                          SourceRef("A", "SYN.txt", 1, "a" * 64), date(2026, 9, 1))
        for stamp in ("2025-03-09 02:30:00", "2025-11-02 01:30:00"):
            with self.subTest(stamp=stamp), self.assertRaisesRegex(InputError, "ambiguous_or_nonexistent"):
                ReconciledRow(("SYN", "minute", stamp),
                              (Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10"), Decimal("100")),
                              (SourceRef("A", "SYN.txt", 1, "a" * 64),), ())

    def test_direct_reconciliation_conflicting_or_duplicate_key_refuses(self):
        one = reconcile_records([parsed(source="A")]).accepted[0]
        two = reconcile_records([parsed(b"2025-04-04,10,12,9,10.5,10000\n", source="B")]).accepted[0]
        for accepted in ((one, two), (one, one)):
            with self.subTest(duplicate=accepted[0] == accepted[1]), self.assertRaises(InputError):
                Reconciliation(accepted, (), (), (), 2).require(one.key)
        quarantine = QuarantinedRow(one.key, ("conflicting_numeric_values",), two.sources)
        with self.assertRaises(InputError):
            Reconciliation((one,), (quarantine,), (), (), 2)

    def test_direct_reconciliation_lists_and_inconsistent_counts_refuse(self):
        row = reconcile_records([parsed()]).accepted[0]
        for fields in (([row], (), (), ()), ((), [], (), ()),
                       ((), (), [], ()), ((), (), (), [])):
            with self.subTest(field_types=[type(x).__name__ for x in fields]), self.assertRaises(InputError):
                Reconciliation(*fields, 1)
        for count in (True, -1, 0, 100001):
            with self.subTest(count=count), self.assertRaises(InputError):
                Reconciliation((row,), (), (), (), count)
        with self.assertRaises(InputError):
            Reconciliation((), (), (), (), 1)
        two_sources = reconcile_records([parsed(), parsed(source="B")]).accepted[0]
        with self.assertRaises(InputError):
            Reconciliation((two_sources,), (), (), (), 1)
        # Re-delivery count may exceed the unique represented source count.
        self.assertEqual(Reconciliation((row,), (), (), (), 2).require(row.key), row)

    def test_direct_quarantine_and_cross_group_source_identity_refuse(self):
        row = reconcile_records([parsed()]).accepted[0]
        for key, reasons, sources in ((row.key, [], row.sources),
                                      (row.key, (), row.sources),
                                      (row.key, ("reason", "reason"), row.sources),
                                      (row.key, ("reason",), list(row.sources)),
                                      (row.key, ("reason",), ()),
                                      (row.key, ("reason",), (row.sources[0], row.sources[0])),
                                      (("SYN", "daily", "2026-09-01"), ("reason",), row.sources)):
            with self.subTest(key=key, reasons=reasons), self.assertRaises(InputError):
                QuarantinedRow(key, reasons, sources)
        refused = parsed(b"2025-04-04 BAD CLOCK,not-a-value\n", source="B", kind="minute")
        with self.assertRaises(InputError):
            Reconciliation((row,), (), (parsed(source="B"),), (), 2)
        with self.assertRaises(InputError):
            Reconciliation((row,), (), (), (refused,), 2)
        other_key_same_source = ReconciledRow(("SYN", "daily", "2025-04-03"), row.values, row.sources, ())
        with self.assertRaises(InputError):
            Reconciliation((other_key_same_source, row), (), (), (), 2)
        # A changed hash at an existing location cannot become a second source.
        changed = SourceRef(row.sources[0].source_id, row.sources[0].member,
                            row.sources[0].line_number, "a" * 64)
        with self.assertRaises(InputError):
            QuarantinedRow(row.key, ("reason",), tuple(sorted((row.sources[0], changed))))



if __name__ == "__main__":
    unittest.main()
