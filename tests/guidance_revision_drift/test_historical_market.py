"""Invented structural projections only; no provider data or execution result."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import unittest

from research.guidance_revision_drift.historical_market import HistoricalMarketBatch, HistoricalQuote, instant_ns
from research.guidance_revision_drift.input_contracts import InputError, canonical_bytes


DECISION = datetime(2025, 4, 4, 14, tzinfo=timezone.utc)
CALLBACK = DECISION + timedelta(minutes=1)


def quote(at, *, sequence=1, bid="9.99", ask="10.01"):
    return {"bid_price": bid, "ask_price": ask, "bid_size": 100, "ask_size": 100,
        "sip_timestamp": instant_ns(at), "participant_timestamp": instant_ns(at),
        "sequence_number": sequence, "conditions": []}


def market_body():
    return {"schema": "gdr.historical-market.v1", "provider": "massive",
        "security_id": "INVENTED-SECURITY", "symbol": "INVENTED", "role": "stock",
        "session_date": "2025-04-04", "session_open_utc": "2025-04-04T13:30:00Z",
        "session_close_utc": "2025-04-04T20:00:00Z", "adjusted": False,
        "fill_forward": False, "quotes_complete": True, "minutes_complete": True,
        "quotes": [quote(DECISION - timedelta(seconds=1)),
                   quote(CALLBACK - timedelta(seconds=1), sequence=2)],
        "minutes": [{"o": "10", "h": "11", "l": "9", "c": "10.5", "v": 10000,
                     "t": instant_ns(DECISION) // 1_000_000}]}


def batch(body=None):
    return HistoricalMarketBatch.from_bytes(canonical_bytes(body or market_body()))


class HistoricalMarketTests(unittest.TestCase):
    def test_exact_normalization_and_post_submission_volume_slice(self):
        value = batch()
        decision = value.decision_quote(DECISION)
        execution = value.subsequent_minute(submitted_at=DECISION, callback_at=CALLBACK,
                                           decision_quote=decision)
        self.assertEqual(decision.bid, Decimal("9.99"))
        self.assertEqual(execution.minute.start_timestamp_ns, instant_ns(DECISION))
        self.assertEqual(execution.minute.end_timestamp_ns, instant_ns(CALLBACK))
        self.assertEqual(execution.projection()["minute_participation_cap_shares"], 100)
        self.assertGreater(execution.quote.sip_timestamp_ns, decision.sip_timestamp_ns)
        self.assertEqual(value.security_id, "INVENTED-SECURITY")
        self.assertEqual(value.symbol, "INVENTED")
        self.assertEqual(value.role, "stock")
        self.assertEqual(value.session_date.isoformat(), "2025-04-04")

    def test_provider_numeric_lexemes_are_decoded_without_binary_rounding(self):
        raw = canonical_bytes(market_body()).replace(b'"9.99"', b'9.9900000000000000000000000001')
        value = HistoricalMarketBatch.from_bytes(raw)
        self.assertEqual(value.decision_quote(DECISION).bid, Decimal("9.9900000000000000000000000001"))
        self.assertIn(b'"bid":"9.9900000000000000000000000001"', value.canonical_projection())

    def test_nan_infinity_duplicate_fields_and_bad_numeric_types_refuse(self):
        raw = canonical_bytes(market_body())
        for invalid in (raw.replace(b'"9.99"', b'NaN'), raw.replace(b'"9.99"', b'Infinity'),
                        raw.replace(b'"9.99"', b'true'),
                        raw.replace(b'"provider":"massive"', b'"provider":"massive","provider":"massive"')):
            with self.subTest(raw=invalid[:20]), self.assertRaises(InputError):
                HistoricalMarketBatch.from_bytes(invalid)
        for field, invalid in (("sip_timestamp", True), ("sequence_number", "1"),
                               ("bid_size", -1), ("conditions", [True])):
            body = market_body()
            body["quotes"][0][field] = invalid
            with self.subTest(field=field), self.assertRaises(InputError):
                batch(body)

    def test_nanosecond_future_quote_is_not_rounded_back_into_decision(self):
        body = market_body()
        body["quotes"] = [quote(DECISION)]
        body["quotes"][0]["sip_timestamp"] += 1
        body["quotes"][0]["participant_timestamp"] += 1
        value = batch(body)
        self.assertEqual(value.projection()["quotes"][0]["sip_timestamp_ns"], instant_ns(DECISION) + 1)
        with self.assertRaisesRegex(InputError, "no quote"):
            value.decision_quote(DECISION)
        self.assertEqual(instant_ns(datetime(1970, 1, 1, 0, 0, 1, 1, tzinfo=timezone.utc)), 1_000_001_000)

    def test_latest_bad_quote_never_falls_back_to_older_convenient_quote(self):
        for change in ({"bid_price": "12", "ask_price": "10"}, {"bid_price": "0"},
                       {"ask_size": 0}, {"conditions": [7]},
                       {"participant_timestamp": instant_ns(DECISION) + 1}):
            body = market_body()
            newest = quote(DECISION, sequence=3)
            newest.update(change)
            body["quotes"].append(newest)
            with self.subTest(change=change), self.assertRaises(InputError):
                batch(body).decision_quote(DECISION)

    def test_quote_freshness_exact_boundary_and_participant_clock(self):
        body = market_body()
        body["quotes"] = [quote(DECISION - timedelta(seconds=60))]
        self.assertEqual(batch(body).decision_quote(DECISION).bid, Decimal("9.99"))
        body["quotes"][0]["sip_timestamp"] -= 1
        body["quotes"][0]["participant_timestamp"] -= 1
        with self.assertRaisesRegex(InputError, "stale"):
            batch(body).decision_quote(DECISION)
        body["quotes"] = [quote(DECISION)]
        body["quotes"][0]["participant_timestamp"] -= 60_000_000_001
        with self.assertRaisesRegex(InputError, "stale"):
            batch(body).decision_quote(DECISION)

    def test_entry_spread_is_exact_and_independent_of_decimal_context(self):
        body = market_body()
        body["quotes"] = [quote(DECISION, bid="399", ask="401")]
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(batch(body).decision_quote(DECISION).ask, Decimal("401"))
            body["quotes"][0]["ask_price"] = "401.00000000000000001"
            with self.assertRaisesRegex(InputError, "spread"):
                batch(body).decision_quote(DECISION)

    def test_subminute_submission_never_borrows_earlier_minute_volume(self):
        value = batch()
        with self.assertRaisesRegex(InputError, "wholly subsequent"):
            value.subsequent_minute(submitted_at=DECISION + timedelta(microseconds=1), callback_at=CALLBACK)
        for callback in (DECISION, CALLBACK - timedelta(microseconds=1), CALLBACK + timedelta(microseconds=1)):
            with self.subTest(callback=callback), self.assertRaises(InputError):
                value.subsequent_minute(submitted_at=DECISION, callback_at=callback)

    def test_same_or_pre_submission_quote_cannot_supply_execution_price(self):
        body = market_body()
        body["quotes"] = [quote(DECISION)]
        value = batch(body)
        with self.assertRaisesRegex(InputError, "reuse"):
            value.subsequent_minute(submitted_at=DECISION, callback_at=CALLBACK,
                                    decision_quote=value.decision_quote(DECISION))
        other = batch(dict(market_body(), security_id="INVENTED-OTHER"))
        with self.assertRaisesRegex(InputError, "belong"):
            batch().subsequent_minute(submitted_at=DECISION, callback_at=CALLBACK,
                                     decision_quote=other.decision_quote(DECISION))

    def test_exact_duplicate_minutes_do_not_double_reported_capacity(self):
        body = market_body()
        body["minutes"].append(deepcopy(body["minutes"][0]))
        body["quotes"].append(deepcopy(body["quotes"][0]))
        value = batch(body)
        self.assertEqual(value.projection()["minute_duplicates"], 1)
        self.assertEqual(value.projection()["quote_duplicates"], 1)
        self.assertEqual(value.subsequent_minute(submitted_at=DECISION, callback_at=CALLBACK)
                         .projection()["minute_participation_cap_shares"], 100)
        body["minutes"][1]["v"] = 20000
        with self.assertRaisesRegex(InputError, "conflicting minute"):
            batch(body)
        body = market_body()
        body["quotes"].append(dict(body["quotes"][0], bid_price="9.98"))
        with self.assertRaisesRegex(InputError, "conflicting quote"):
            batch(body)

    def test_adjusted_fill_forward_and_partial_pages_are_never_assumed_raw_complete(self):
        for field, invalid in (("adjusted", True), ("fill_forward", True),
                               ("quotes_complete", False), ("minutes_complete", False),
                               ("adjusted", 0), ("quotes_complete", 1)):
            with self.subTest(field=field), self.assertRaises(InputError):
                batch(dict(market_body(), **{field: invalid}))
        body = market_body()
        body["permission"] = True
        with self.assertRaises(InputError):
            batch(body)

    def test_minute_start_units_ohlc_and_whole_share_volume_are_explicit(self):
        for field, invalid in (("t", instant_ns(DECISION)), ("t", True), ("t", "1743775200000"),
                               ("l", "10.1"), ("c", "12"), ("v", "100.5"), ("v", -1)):
            body = market_body()
            body["minutes"][0][field] = invalid
            with self.subTest(field=field), self.assertRaises(InputError):
                batch(body)
        body = market_body()
        body["minutes"][0]["t"] += 1
        with self.assertRaisesRegex(InputError, "aligned"):
            batch(body)

    def test_stock_and_explicit_spy_benchmark_use_identical_slice_contracts(self):
        body = dict(market_body(), role="benchmark", symbol="SPY", security_id="INVENTED-SPY")
        value = batch(body)
        execution = value.subsequent_minute(submitted_at=DECISION, callback_at=CALLBACK,
                                           decision_quote=value.decision_quote(DECISION))
        self.assertEqual(execution.minute.security_id, "INVENTED-SPY")
        self.assertEqual(value.role, "benchmark")
        with self.assertRaisesRegex(InputError, "SPY"):
            batch(dict(body, symbol="INVENTED"))

    def test_detached_projection_has_no_pit_rights_coverage_or_order_authority(self):
        body = market_body()
        value = batch(body)
        original = value.canonical_projection()
        body["quotes"][0]["bid_price"] = "999"
        detached = value.projection()
        detached["quotes"][0]["bid"] = "999"
        self.assertEqual(value.canonical_projection(), original)
        for key in ("point_in_time_data", "coverage_verified", "reference_mapping_verified",
                    "calendar_verified", "historical_availability_verified", "execution_authority",
                    "native_execution_evidence"):
            self.assertIs(value.projection()[key], False)
        self.assertIs(value.projection()["supplied_completeness_only"], True)
        self.assertEqual(HistoricalMarketBatch.from_bytes(value.raw_bytes).sha256, value.sha256)

    def test_wrong_session_overnight_naive_and_nondecision_clocks_refuse(self):
        for at in (DECISION.replace(tzinfo=None), DECISION + timedelta(seconds=1),
                   DECISION + timedelta(days=1)):
            with self.subTest(at=at), self.assertRaises(InputError):
                batch().decision_quote(at)
        with self.assertRaises(InputError):
            batch(dict(market_body(), session_open_utc="2025-04-04T14:30:00Z"))
        body = market_body()
        body["quotes"][0]["sip_timestamp"] = instant_ns(DECISION - timedelta(hours=1))
        with self.assertRaisesRegex(InputError, "outside"):
            batch(body)


    def test_envelope_and_regular_session_rules_each_refuse_alone(self):
        # GDR-CR49-002: each case keeps every other rule satisfied.
        day_ns, day_ms = 86_400 * 10**9, 86_400 * 10**3
        weekend = market_body()
        for row in weekend["quotes"]:
            row["sip_timestamp"] += day_ns
            row["participant_timestamp"] += day_ns
        for row in weekend["minutes"]:
            row["t"] += day_ms
        weekend.update(session_date="2025-04-05", session_open_utc="2025-04-05T13:30:00Z",
                       session_close_utc="2025-04-05T20:00:00Z")
        cases = {"other provider": dict(market_body(), provider="other-vendor"),
                 "unknown role": dict(market_body(), role="index"),
                 "weekend session": weekend,
                 "nonstandard open": dict(market_body(), session_open_utc="2025-04-04T13:00:00Z"),
                 "nonstandard close": dict(market_body(), session_close_utc="2025-04-04T19:00:00Z"),
                 "bounds on another day": dict(market_body(), session_date="2025-04-03")}
        for label, body in cases.items():
            with self.subTest(case=label), self.assertRaises(InputError):
                batch(body)

    def test_execution_rejects_late_decision_quote_and_quote_at_submission_instant(self):
        # GDR-CR49-002: a caller-supplied decision quote stamped after submission,
        # and an execution quote stamped exactly at submission, are each refused
        # while every other slicing rule holds.
        body = market_body()
        body["quotes"].append(quote(CALLBACK - timedelta(milliseconds=500), sequence=3))
        value = batch(body)
        stamp = instant_ns(CALLBACK - timedelta(seconds=1))  # the fixture's sequence-2 quote
        late = HistoricalQuote(value.security_id, value.symbol, value.sha256, stamp, stamp, 2,
                               Decimal("9.99"), Decimal("10.01"), 100, 100, ())
        self.assertGreater(late.sip_timestamp_ns, instant_ns(DECISION))
        with self.assertRaisesRegex(InputError, "before submission"):
            value.subsequent_minute(submitted_at=DECISION, callback_at=CALLBACK, decision_quote=late)
        body = market_body()
        later = DECISION + timedelta(minutes=1)
        body["quotes"].append(quote(later, sequence=3))
        body["minutes"].append({"o": "10", "h": "11", "l": "9", "c": "10.5", "v": 10000,
                                "t": instant_ns(later) // 1_000_000})
        value = batch(body)
        decision = value.decision_quote(DECISION)
        with self.assertRaisesRegex(InputError, "reuse decision or pre-submission"):
            value.subsequent_minute(submitted_at=later, callback_at=later + timedelta(minutes=1),
                                    decision_quote=decision)

    def test_bounded_rows_and_unknown_row_fields_refuse(self):
        for field in ("quotes", "minutes"):
            with self.subTest(field=field), self.assertRaises(InputError):
                batch(dict(market_body(), **{field: []}))
        body = market_body()
        body["quotes"][0]["unknown"] = 1
        with self.assertRaises(InputError):
            batch(body)
        with self.assertRaises(InputError):
            HistoricalMarketBatch.from_bytes(b" " * 1_048_577)


if __name__ == "__main__":
    unittest.main()
