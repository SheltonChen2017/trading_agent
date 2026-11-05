"""Invented FirstRate rows only; no USB, provider or runtime access."""
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from itertools import permutations
import unittest
from unittest.mock import patch

from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift.firstrate import (
    MAX_LINE_BYTES, FirstRateLine, QuarantinedRow, Reconciliation, ReconciledRow, SourceRef,
    _member, _minute_bounds, parse_line, reconcile_records, regular_minute,
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


BAR = (Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10"), Decimal("100"))
DAILY_KEY = ("SYN", "daily", "2025-04-04")
MINUTE_KEY = ("SYN", "minute", "2025-04-04 10:00:00")
DAILY_MEMBER = "SYN_full_1day_UNADJUSTED.txt"


def ref(member=DAILY_MEMBER, line=1, sha="a" * 64, source="A"):
    return SourceRef(source, member, line, sha)


def accepted_line(key=DAILY_KEY, values=BAR, source=None, **changes):
    fields = dict(status="accepted", key=key, values=values, reasons=(), warnings=(),
                  source=source or ref(), session_date=date.fromisoformat(key[2][:10]))
    fields.update(changes)
    return FirstRateLine(**fields)


class ReviewCorrectionTests(unittest.TestCase):
    """GDR-CR65 corrections; each case fails on the source Codex published."""

    def test_public_constructors_cannot_relabel_an_adjusted_or_other_symbol_file(self):
        bounds = dict(start_utc=datetime(2025, 4, 4, 14, tzinfo=timezone.utc),
                      end_utc=datetime(2025, 4, 4, 14, 1, tzinfo=timezone.utc))
        for member in ("SYN_full_1min_ADJUSTED.txt", "SYN_full_1min_SPLIT_ADJUSTED.txt",
                       "OTHER_full_1min_UNADJUSTED.txt", "SYN_full_1day_UNADJUSTED.txt", "SYN.txt"):
            source = ref(member)
            with self.subTest(member=member, path="line"), self.assertRaisesRegex(InputError, "raw_member"):
                accepted_line(MINUTE_KEY, source=source, **bounds)
            with self.subTest(member=member, path="reconciled"), self.assertRaisesRegex(InputError, "raw_member"):
                ReconciledRow(MINUTE_KEY, BAR, (source,), ())
            with self.subTest(member=member, path="quarantined"), self.assertRaisesRegex(InputError, "raw_member"):
                QuarantinedRow(MINUTE_KEY, ("reason",), (source,))
            with self.subTest(member=member, path="refused"), self.assertRaisesRegex(InputError, "raw_member"):
                FirstRateLine("refused", MINUTE_KEY, (), ("reason",), (), source, date(2025, 4, 4))
        # Every source of a multi-source row is bound, not only the first.
        with self.assertRaisesRegex(InputError, "raw_member"):
            ReconciledRow(DAILY_KEY, BAR, (ref(), ref("SYN_full_1day_ADJUSTED.txt", source="B")), ())
        with self.assertRaisesRegex(InputError, "raw_member"):
            QuarantinedRow(DAILY_KEY, ("reason",), (ref(), ref("SYN_full_1day_ADJUSTED.txt", source="B")))

    def test_action_files_bind_symbol_and_action_kind(self):
        for kind, member, raw in (("split", "SYN_divs.txt", b"2025-04-04,0.25\n"),
                                  ("dividend", "SYN.txt", b"2025-04-04,2\n"),
                                  ("dividend", "OTHER_divs.txt", b"2025-04-04,0.25\n"),
                                  ("split", "OTHER.txt", b"2025-04-04,2\n")):
            with self.subTest(kind=kind, member=member), self.assertRaisesRegex(InputError, "raw_member"):
                parse_line(raw, source_id="A", member=member, line_number=1, symbol="SYN", kind=kind)
        # The file is bound before any row, including rows that never reach a key.
        for raw in (b"2026-09-01,x\n", b"\n"):
            with self.subTest(raw=raw), self.assertRaisesRegex(InputError, "raw_member"):
                parse_line(raw, source_id="A", member="SYN_full_1day_ADJUSTED.txt", line_number=1,
                           symbol="SYN", kind="daily")
        nested = parse_line(b"2025-04-04,0.25\n", source_id="A", member="Stock_Dividends.zip/3/SYN_divs.txt",
                            line_number=1, symbol="SYN", kind="dividend")
        self.assertEqual(nested.status, "accepted")

    def test_direct_rows_cannot_drop_the_diagnostics_parse_line_requires(self):
        for key, values, member, warnings in (
                (("SYN", "dividend", "2025-04-04"), (Decimal("0"),), "SYN_divs.txt", ()),
                (("SYN", "dividend", "2025-04-04"), (Decimal("1"),), "SYN_divs.txt",
                 ("action_identity_currency_availability_unverified",)),
                (("SYN", "dividend", "2025-04-04"), (Decimal("1"),), "SYN_divs.txt",
                 ("dividend_payment_date_missing",)),
                (("SYN", "dividend", "2025-04-04"), (Decimal("0"),), "SYN_divs.txt",
                 ("action_identity_currency_availability_unverified", "dividend_payment_date_missing")),
                (("SYN", "split", "2025-04-05"), (Decimal("2"),), "SYN.txt",
                 ("action_identity_currency_availability_unverified",)),
                (DAILY_KEY, BAR[:4] + (Decimal("0"),), DAILY_MEMBER, ())):
            with self.subTest(key=key, warnings=warnings, path="line"), self.assertRaisesRegex(InputError, "warning_missing"):
                accepted_line(key, values, ref(member), warnings=warnings)
            with self.subTest(key=key, warnings=warnings, path="row"), self.assertRaisesRegex(InputError, "warning_missing"):
                ReconciledRow(key, values, (ref(member),), warnings)
        parsed_row = parsed(b"2025-04-04,0.25\n", kind="dividend")
        self.assertEqual(parsed_row.warnings, ("action_identity_currency_availability_unverified",
                                               "dividend_payment_date_missing"))
        weekend = parsed(b"2025-04-05,0\n", kind="dividend")
        self.assertEqual(weekend.warnings, ("action_effective_date_requires_reconciliation",
                                            "zero_dividend_requires_reconciliation",
                                            "action_identity_currency_availability_unverified",
                                            "dividend_payment_date_missing"))
        self.assertEqual(parsed(b"2025-04-04,2\n", kind="split").warnings,
                         ("action_identity_currency_availability_unverified",))
        self.assertEqual(parsed(b"2025-04-05,2\n", kind="split").warnings,
                         ("action_effective_date_requires_reconciliation",
                          "action_identity_currency_availability_unverified"))
        self.assertEqual(parsed().warnings, ())

    def test_financial_values_stay_out_of_row_representations(self):
        row = parsed(b"2025-04-04,10,11,9,10.123456,100\n")
        reconciled = reconcile_records([row]).accepted[0]
        for rendered in (repr(row), str(row), repr(reconciled), str(reconciled)):
            self.assertNotIn("10.123456", rendered)
        self.assertEqual(row.values[3], Decimal("10.123456"))

    def test_embedded_terminators_are_not_hashed_as_one_row(self):
        for raw in (b"2025-04-04,10,11,9,10,100\n2026-09-02,1,1,1,1,1\n",
                    b"2025-04-04,10,11,9,10,100\r2026-09-02,1,1,1,1,1\r\n"):
            with self.subTest(raw=raw[25:27]), \
                 patch("research.guidance_revision_drift.firstrate.hash_bytes", side_effect=AssertionError("hashed")):
                row = parsed(raw)
            self.assertEqual(row.status, "refused")
            self.assertEqual(row.reasons, ("embedded_line_terminator",))
            self.assertIsNone(row.key)
            self.assertIsNone(row.source.line_sha256)
        for raw in (b"2025-04-04,10,11,9,10,100", b"2025-04-04,10,11,9,10,100\n", b"2025-04-04,10,11,9,10,100\r\n"):
            self.assertEqual(parsed(raw).status, "accepted")

    def test_dot_segments_cannot_mint_a_second_location_for_one_member(self):
        for member in ("./SYN_full_1day_UNADJUSTED.txt", "a/./SYN_full_1day_UNADJUSTED.txt",
                       "SYN_full_1day_UNADJUSTED.txt/.", "a/../SYN_full_1day_UNADJUSTED.txt"):
            with self.subTest(member=member), self.assertRaises(InputError):
                parsed(member=member)


class EdgePinTests(unittest.TestCase):
    """Boundaries the original methods left unpinned."""

    def assert_refused(self, raw, reason, *, key=DAILY_KEY, kind="daily"):
        row = parsed(raw, kind=kind)
        self.assertEqual(row.status, "refused")
        self.assertEqual(row.reasons, (reason,))
        self.assertEqual(row.key, key)
        self.assertEqual(row.values, ())

    def test_exact_refusal_codes_and_bounds_of_parse_line(self):
        for raw in (b"2025-04-04,0,0,0,0,1\n", b"2025-04-04,-1,-1,-1,-1,1\n"):
            self.assertEqual(parsed(raw).status, "refused")
        self.assert_refused(b"2025-04-04,10,11,9,8,1\n", "firstrate_invalid_ohlc_bounds")
        self.assert_refused(b"2025-04-04,10,11,9,12,1\n", "firstrate_invalid_ohlc_bounds")
        self.assert_refused(b"2025-04-04X10,11,9,10,1\n", "invalid_date_delimiter")
        self.assert_refused(b"2025-04-04,10,11,9,10\n", "invalid_field_count_or_timestamp")
        self.assert_refused(b"2025-04-04,10,11,9,10,1,1\n", "invalid_field_count_or_timestamp")
        self.assert_refused(b"2025-04-04 10:00:00X10,11,9,10,1\n", "invalid_minute_timestamp", key=MINUTE_KEY, kind="minute")
        self.assert_refused(b"2025-04-04 10:00:00,10,11,9,10\n", "invalid_field_count_or_timestamp", key=MINUTE_KEY, kind="minute")
        self.assertEqual(parsed(b"2025-04-04,10,11,9,10,1000000000000\n").values[-1], Decimal(10**12))
        self.assertEqual(parsed(b"2025-04-04," + b"1e" + b"0" * 130 + b"1,11,9,10,1\n").status, "refused")
        self.assertEqual(parsed(b"2025-04-04 10:00:00,10,11,9,10,1\n", kind="minute").status, "accepted")
        self.assertEqual(parsed(b"2025-04-05 10:00:00,10,11,9,10,1\n", kind="minute").reasons, ("weekend_bar_date",))
        self.assertEqual(parsed(b"2025-04-06,10,11,9,10,1\n").reasons, ("weekend_bar_date",))
        # Python's ISO parser accepts week dates; the provider format does not.
        week = parsed(b"2025-W14-5,10,11,9,10,1\n")
        self.assertEqual((week.status, week.reasons, week.key), ("refused", ("invalid_date_prefix",), None))

    def test_exclusion_codes_and_retained_dates(self):
        protected = parsed(b"2026-09-01,x\n")
        self.assertEqual((protected.reasons, protected.session_date), (("protected_date",), date(2026, 9, 1)))
        early = parsed(b"2012-12-31,x\n")
        self.assertEqual((early.reasons, early.session_date), (("outside_requested_window",), date(2012, 12, 31)))
        narrowed = parse_line(b"2025-04-04,x\n", source_id="A", member=DAILY_MEMBER, line_number=1,
                              symbol="SYN", kind="daily", stop=date(2025, 4, 4))
        self.assertEqual(narrowed.reasons, ("outside_requested_window",))
        last = parse_line(b"2026-08-31,10,11,9,10,1\n", source_id="A", member=DAILY_MEMBER, line_number=1,
                          symbol="SYN", kind="daily")
        self.assertEqual(last.status, "accepted")

    def test_member_and_source_labels_refuse_unsafe_text(self):
        for value in (r"a\SYN.txt", "a" * 513, "a\tb", "café.txt", "a\x7fb", "a//b", "/a", "", 1):
            with self.subTest(value=repr(value)[:24]), self.assertRaises(InputError):
                _member(value)
        self.assertEqual(_member("a" * 512), "a" * 512)
        self.assertEqual(_member("~a.txt"), "~a.txt")
        for args in (("bad id", "a.txt", 1, None), ("A", "a.txt", 100_000_001, None),
                     ("A", "a.txt", 1, "A" * 64), ("A", "a.txt", 1, "a" * 63)):
            with self.subTest(args=args[:3]), self.assertRaises(InputError):
                SourceRef(*args)
        self.assertEqual(SourceRef("A", "a.txt", 100_000_000, None).line_number, 100_000_000)
        with self.assertRaises(InputError):
            parse_line(b"2025-04-04,1\n", source_id="A", member="bad id.txt", line_number=1,
                       symbol="bad id", kind="split")

    def test_row_keys_and_values_refuse_every_noncanonical_shape(self):
        sources = (ref(),)
        for key in (list(DAILY_KEY), DAILY_KEY + ("x",), ("bad id", "daily", "2025-04-04"),
                    ("SYN", "daily", "2012-12-31"), ("SYN", "daily", "2025-04-04 extra"),
                    ("SYN", "daily", "20250404"), ("SYN", 1, "2025-04-04"), ("SYN", "daily", 20250404)):
            with self.subTest(key=key), self.assertRaises(InputError):
                ReconciledRow(key, BAR, sources, ())
        with self.assertRaises(InputError):
            ReconciledRow(("SYN", "weekly", "2025-04-04"), (Decimal("1"),), sources, ())
        with self.assertRaises(InputError):
            ReconciledRow(("bad id", "daily", "2025-04-04"), BAR, (ref("bad id_full_1day_UNADJUSTED.txt"),), ())
        for values in (BAR[:4], BAR + (Decimal("1"),), list(BAR), tuple(str(x) for x in BAR)):
            with self.subTest(values=len(values)), self.assertRaises(InputError):
                ReconciledRow(DAILY_KEY, values, sources, ())
        for stamp in ("2025-04-04 10:00:0\u00e9", 1):
            with self.subTest(stamp=stamp), self.assertRaisesRegex(InputError, "invalid_minute_timestamp"):
                _minute_bounds(stamp)

    def test_direct_line_construction_rechecks_each_field(self):
        good = dict(status="accepted", key=DAILY_KEY, values=BAR, reasons=(), warnings=(),
                    source=ref(), session_date=date(2025, 4, 4))
        self.assertEqual(FirstRateLine(**good).status, "accepted")
        bounds = (datetime(2025, 4, 4, 14, tzinfo=timezone.utc), datetime(2025, 4, 4, 14, 1, tzinfo=timezone.utc))
        minute = dict(good, key=MINUTE_KEY, source=ref("SYN_full_1min_UNADJUSTED.txt"),
                      start_utc=bounds[0], end_utc=bounds[1])
        self.assertEqual(FirstRateLine(**minute).status, "accepted")
        tampered = ref()
        object.__setattr__(tampered, "member", "../x")
        for label, fields in (
                ("status", dict(good, status="approved")),
                ("source type", dict(good, source=None)),
                ("tampered source", dict(good, source=tampered)),
                ("values type", dict(good, values=list(BAR))),
                ("empty values type", dict(good, status="refused", values=[], reasons=("reason",))),
                ("unkeyed tampered source", dict(good, status="refused", key=None, values=(), reasons=("reason",),
                                                 session_date=None, source=tampered)),
                ("unkeyed session type", dict(good, status="refused", key=None, values=(), reasons=("reason",),
                                              session_date="2025-04-04")),
                ("reason type", dict(good, status="refused", values=(), reasons=["x"])),
                ("reason text", dict(good, status="refused", values=(), reasons=("bad code",))),
                ("warning text", dict(good, warnings=("bad code",))),
                ("session type", dict(good, session_date="2025-04-04")),
                ("key", dict(good, key=("SYN", "daily", "2026-09-01"), session_date=date(2026, 9, 1))),
                ("date mismatch", dict(good, session_date=date(2025, 4, 3))),
                ("missing hash", dict(good, source=SourceRef("A", DAILY_MEMBER, 1, None))),
                ("accepted reasons", dict(good, reasons=("reason",))),
                ("accepted values", dict(good, values=(Decimal("0"),) * 4 + (Decimal("1"),))),
                ("weekend", dict(good, key=("SYN", "daily", "2025-04-05"), session_date=date(2025, 4, 5))),
                ("minute clock", dict(minute, end_utc=bounds[0])),
                ("refused values", dict(good, status="refused", reasons=("reason",))),
                ("refused reasonless", dict(good, status="refused", values=())),
                ("excluded key", dict(good, status="excluded", values=(), reasons=("reason",),
                                      source=SourceRef("A", DAILY_MEMBER, 1, None))),
                ("excluded hash", dict(good, status="excluded", key=None, values=(), reasons=("reason",)))):
            with self.subTest(label=label), self.assertRaises(InputError):
                FirstRateLine(**fields)
        row = FirstRateLine(**good)
        self.assertEqual(row.projection(include_values=True)["values"], ["10", "11", "9", "10", "100"])
        self.assertNotIn("values", row.projection())
        with self.assertRaises(InputError):
            row.projection(include_values=1)

    def test_diagnostic_and_source_inventories_are_bounded_ordered_and_hashed(self):
        for warnings in (("x",) * 2, tuple(f"code-{i}" for i in range(33)), ["x"], ("bad code",), (1,)):
            with self.subTest(warnings=len(warnings)), self.assertRaises(InputError):
                ReconciledRow(DAILY_KEY, BAR, (ref(),), warnings)
        self.assertEqual(len(ReconciledRow(DAILY_KEY, BAR, (ref(),), tuple(f"code-{i}" for i in range(32))).warnings), 32)
        one, two = ref(line=1), ref(line=2)
        tampered = ref()
        object.__setattr__(tampered, "source_id", "bad id")
        for sources in ((two, one), (SourceRef("A", DAILY_MEMBER, 1, None),), (None,), (tampered,), [one], ()):
            with self.subTest(sources=repr(sources)[:40]), self.assertRaises(InputError):
                ReconciledRow(DAILY_KEY, BAR, sources, ())
        with patch("research.guidance_revision_drift.firstrate.MAX_RECORDS", 1), self.assertRaises(InputError):
            ReconciledRow(DAILY_KEY, BAR, (one, two), ())
        with self.assertRaises(InputError):
            ReconciledRow(("SYN", "daily", "2025-04-05"), BAR, (one,), ())
        with self.assertRaises(InputError):
            QuarantinedRow(DAILY_KEY, ("z", "a"), (one,))
        quarantined = QuarantinedRow(DAILY_KEY, ("a", "z"), (one,))
        self.assertEqual(quarantined.projection(), {"key": list(DAILY_KEY), "reasons": ["a", "z"], "sources": [one.projection()]})
        object.__setattr__(quarantined, "reasons", ())
        with self.assertRaises(InputError):
            quarantined.projection()

    def test_reconciled_projection_flags_hash_and_authority_are_exact(self):
        result = reconcile_records([parsed(source="A"), parsed(source="B")])
        row = result.accepted[0]
        self.assertEqual(row.source_sha256, hash_payload([source.projection() for source in row.sources]))
        flags = {"provider": "firstrate", "normalization": "Raw", "fill_forward": False,
                 "point_in_time_data": False, "coverage_verified": False, "calendar_verified": False,
                 "reference_mapping_verified": False, "historical_availability_verified": False,
                 "execution_authority": False, "native_execution_evidence": False}
        self.assertEqual(row.projection(), {"key": list(DAILY_KEY), "sources": [x.projection() for x in row.sources],
                                            "source_sha256": row.source_sha256, "warnings": []} | flags)
        self.assertEqual(row.projection(include_values=True)["values"], ["10", "11", "9", "10.5", "10000"])
        self.assertEqual(result.projection(), {"schema": "gdr.firstrate-reconciliation.v1", "input_records": 2,
            "accepted": [row.projection()], "quarantined": [], "unkeyed_refusals": [], "excluded": [],
            "supplied_source_inventory_only": True, "source_set_has_unkeyed_refusal": False,
            "backtest_ready": False} | flags)
        self.assertEqual(result.projection(include_values=True)["accepted"][0]["values"][3], "10.5")
        for call in (row.projection, result.projection, reconcile_records([]).projection):
            with self.assertRaises(InputError):
                call(include_values=1)
        action = reconcile_records([parsed(b"2025-04-04,0.25\n", kind="dividend"),
                                    parsed(b"2025-04-04,0.5\n", kind="dividend", source="B")])
        self.assertEqual(action.accepted, ())
        warned = reconcile_records([parsed(b"2025-04-04,10,11,9,10,0\n", source="A"),
                                    parsed(b"2025-04-04,10,11,9,10,0\n", source="B")]).accepted[0]
        self.assertEqual(warned.projection()["warnings"], ["zero_daily_volume_requires_reconciliation"])
        blocked = reconcile_records([parsed(), parsed(b"BAD DATE!!,x\n", source="B")])
        self.assertTrue(blocked.projection()["source_set_has_unkeyed_refusal"])

    def test_reconciliation_rechecks_members_order_and_categories(self):
        row = reconcile_records([parsed()]).accepted[0]
        later = reconcile_records([parsed(b"2025-04-07,10,11,9,10.5,10000\n", source="B")]).accepted[0]
        self.assertEqual(Reconciliation((row, later), (), (), (), 2).accepted, (row, later))
        with self.assertRaises(InputError):
            Reconciliation((later, row), (), (), (), 2)
        with patch("research.guidance_revision_drift.firstrate.MAX_RECORDS", 1), self.assertRaises(InputError):
            Reconciliation((row, later), (), (), (), 1)
        quarantine = QuarantinedRow(row.key, ("reason",), row.sources)
        keyed = parsed(b"2025-04-05,10,11,9,10,1\n", source="B")
        self.assertIsNotNone(keyed.key)
        blank = parsed(b"\n", source="C")
        refused = parsed(b"BAD DATE!!,x\n", source="D")
        for groups in (((quarantine,), (), (), ()), ((), (row,), (), ()), ((), (), (keyed,), ()),
                       ((), (), (blank,), ()), ((), (), (), (refused,)), ((), (), (row,), ())):
            with self.subTest(groups=[len(x) for x in groups]), self.assertRaises(InputError):
                Reconciliation(*groups, 5)
        second = parsed(b"BAD DATE!!,y\n", source="E")
        self.assertEqual(len(Reconciliation((), (), (refused, second), (), 2).refusals), 2)
        with self.assertRaises(InputError):
            Reconciliation((), (), (second, refused), (), 2)
        with self.assertRaises(InputError):
            Reconciliation((), (), (refused, refused), (), 2)
        object.__setattr__(row, "warnings", ("bad code",))
        with self.assertRaises(InputError):
            Reconciliation((row,), (), (), (), 1)

    def test_reconciled_results_recheck_tampering_before_use(self):
        result = reconcile_records([parsed()])
        key = result.accepted[0].key
        object.__setattr__(result, "input_records", -1)
        for call in (result.projection, lambda: result.require(key)):
            with self.assertRaises(InputError):
                call()
        other = reconcile_records([parsed()])
        with self.assertRaisesRegex(InputError, "unprotected|invalid"):
            other.require(("SYN", "daily", "2026-09-01"))
        record = parsed()
        object.__setattr__(record, "reasons", ("reason",))
        with self.assertRaises(InputError):
            reconcile_records([record])
        with self.assertRaisesRegex(InputError, "exact parsed"):
            reconcile_records([object()])

    def test_reconciliation_budget_warning_union_and_input_order(self):
        self.assertEqual(reconcile_records([parsed()], max_records=1).input_records, 1)
        zero = parsed(b"2025-04-05,0\n", kind="dividend", source="B")
        plain = parsed(b"2025-04-05,0.0\n", kind="dividend", source="C")
        self.assertEqual(reconcile_records([zero, plain]).accepted[0].warnings,
                         ("action_effective_date_requires_reconciliation",
                          "action_identity_currency_availability_unverified",
                          "dividend_payment_date_missing",
                          "zero_dividend_requires_reconciliation"))
        bad_b = parsed(b"BAD DATE!!,x\n", source="B")
        bad_a = parsed(b"BAD DATE!!,x\n", source="A")
        self.assertEqual([x.source.source_id for x in reconcile_records([bad_b, bad_a]).refusals], ["A", "B"])
        gap_b = parsed(b"2026-09-01,x\n", source="B")
        gap_a = parsed(b"2026-09-01,x\n", source="A")
        self.assertEqual([x.source.source_id for x in reconcile_records([gap_b, gap_a]).excluded], ["A", "B"])

    def test_regular_minute_carries_exact_lineage_values_and_refuses_other_rows(self):
        raw = b"2025-04-04 10:00:00,10,12,9,11,100\n"
        row = reconcile_records([parsed(raw, kind="minute")]).accepted[0]
        result = regular_minute(row, session=session(), security_id="SYN-SEC")
        self.assertEqual((result.security_id, result.symbol, result.source_sha256), ("SYN-SEC", "SYN", row.source_sha256))
        self.assertEqual((result.open, result.high, result.low, result.close, result.volume),
                         (Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"), 100))
        self.assertEqual(result.start_timestamp_ns, int(datetime(2025, 4, 4, 14, tzinfo=timezone.utc).timestamp()) * 10**9)
        last = reconcile_records([parsed(b"2025-04-04 15:59:00,10,12,9,11,100\n", kind="minute")]).accepted[0]
        self.assertEqual(regular_minute(last, session=session(), security_id="SYN-SEC").volume, 100)
        first = reconcile_records([parsed(b"2025-04-04 09:30:00,10,12,9,11,100\n", kind="minute")]).accepted[0]
        self.assertEqual(regular_minute(first, session=session(), security_id="SYN-SEC").volume, 100)
        daily = reconcile_records([parsed()]).accepted[0]
        with self.assertRaisesRegex(InputError, "regular-minute source required"):
            regular_minute(daily, session=session(), security_id="SYN-SEC")
        warned = ReconciledRow(row.key, row.values, row.sources, ("zero_daily_volume_requires_reconciliation",))
        with self.assertRaisesRegex(InputError, "warnings require reconciliation"):
            regular_minute(warned, session=session(), security_id="SYN-SEC")
        with self.assertRaises(InputError):
            regular_minute(row, session=session(), security_id="bad id")
        forged = session()
        object.__setattr__(forged, "session_date", date(2025, 4, 7))
        with self.assertRaises(InputError):
            regular_minute(row, session=forged, security_id="SYN-SEC")
        other_day = CalendarSession(date(2025, 4, 7), datetime(2025, 4, 7, 13, 30, tzinfo=timezone.utc),
                                    datetime(2025, 4, 7, 20, tzinfo=timezone.utc))
        with self.assertRaisesRegex(InputError, "outside supplied"):
            regular_minute(row, session=other_day, security_id="SYN-SEC")
        widened = session()
        object.__setattr__(widened, "close_utc", datetime(2025, 4, 4, 21, tzinfo=timezone.utc))
        with self.assertRaises(InputError):
            regular_minute(row, session=widened, security_id="SYN-SEC")
        tampered = reconcile_records([parsed(raw, kind="minute")]).accepted[0]
        object.__setattr__(tampered, "values", (Decimal("NaN"),) * 5)
        with self.assertRaises(InputError):
            regular_minute(tampered, session=session(), security_id="SYN-SEC")


if __name__ == "__main__":
    unittest.main()
