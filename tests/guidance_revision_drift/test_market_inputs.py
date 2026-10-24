"""Invented raw market/reference contracts, not historical observations."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
import unittest

from research.guidance_revision_drift.fixtures import example_corpus, fixture_instant
from research.guidance_revision_drift.market_inputs import MarketInputError, SyntheticMarketInput


def market_body(schedule=None):
    schedule = schedule or example_corpus().schedule
    interval = dict(security_id="SYN-SEC-A", start_utc="2025-04-04T13:59:00Z",
                    end_utc="2025-04-04T14:00:00Z", normalization="Raw", fill_forward=False)
    return dict(schema="gdr.synthetic.market-input.v1", source_id="SYN-MARKET",
        calendar_sha256=schedule.sha256, session_date="2025-04-04",
        received_at="2025-04-04T14:00:00Z", validated_at="2025-04-04T14:00:00Z",
        reference=dict(security_id="SYN-SEC-A", issuer_id="SYN-ISSUER-A", exchange="NASDAQ",
            instrument_type="COMMON_STOCK", primary=True, sector="technology",
            valid_from="2025-01-02", valid_through="2025-05-15", available_at="2025-01-02T12:00:00Z"),
        quote=dict(interval, bid="49.99", ask="50"), trade=dict(interval, volume=100000))


class MarketInputTests(unittest.TestCase):
    def setUp(self):
        self.schedule = example_corpus().schedule
        self.at = fixture_instant(date(2025, 4, 4), 10)
        self.body = market_body(self.schedule)

    def prepare(self, body=None, **changes):
        args = dict(as_of=self.at, adv20=Decimal("25000000"), settlement_session=date(2025, 4, 7))
        args.update(changes)
        return SyntheticMarketInput.from_dict(body or self.body).prepare(self.schedule, **args)

    def test_raw_paired_input_maps_permanent_identity_and_exact_prices(self):
        value = self.prepare()
        self.assertEqual(value.security_id, "SYN-SEC-A")
        self.assertEqual(value.minute.issuer, "SYN-ISSUER-A")
        self.assertEqual(value.quote.ask, Decimal("50"))
        self.assertEqual(value.minute.at, self.at)
        self.assertEqual(value.calendar_sha256, self.schedule.sha256)

    def test_immutable_raw_provenance_and_strict_roundtrip(self):
        value = SyntheticMarketInput.from_dict(self.body)
        original = value.canonical_bytes
        self.body["quote"]["ask"] = "900"
        value.to_dict()["reference"]["issuer_id"] = "SYN-OTHER"
        self.assertEqual(value.canonical_bytes, original)
        self.assertEqual(SyntheticMarketInput.from_bytes(original), value)
        self.assertEqual(value.sha256, SyntheticMarketInput.from_bytes(original).sha256)

    def test_missing_unknown_duplicate_float_and_malformed_fields_refuse(self):
        for raw in (b'{"schema":1,"schema":1}', b'{"value":NaN}', b'{"value":1.1}', b"\xff", b"{}" * 20000):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                SyntheticMarketInput.from_bytes(raw)
        for target, field, value in (("quote", "bid", None), ("quote", "ask", 50.0),
                ("quote", "ask", "NaN"), ("quote", "ask", "1e2"), ("quote", "ask", "49"),
                ("trade", "volume", True), ("reference", "primary", 1),
                ("reference", "security_id", "AAPL"), ("reference", "exchange", "OTC"),
                ("reference", "instrument_type", "ETF"), ("reference", "sector", None)):
            body = deepcopy(self.body)
            body[target][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                SyntheticMarketInput.from_dict(body)
        for field in ("quote", "reference", "received_at"):
            body = deepcopy(self.body)
            del body[field]
            with self.assertRaises(ValueError):
                SyntheticMarketInput.from_dict(body)
        body = deepcopy(self.body)
        body["reference"]["alternate_mapping"] = "SYN-OTHER"
        with self.assertRaisesRegex(ValueError, "unknown"):
            SyntheticMarketInput.from_dict(body)

    def test_adjustment_fillforward_identity_and_interval_alignment_refuse(self):
        for target, field, value in (("quote", "normalization", "Adjusted"),
                ("trade", "normalization", "SplitAdjusted"), ("quote", "fill_forward", True),
                ("trade", "security_id", "SYN-OTHER"), ("trade", "start_utc", "2025-04-04T13:58:00Z"),
                ("quote", "end_utc", "2025-04-04T14:00:01Z")):
            body = deepcopy(self.body)
            body[target][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.prepare(body)

    def test_quote_freshness_boundary_and_delayed_minutes_never_backdate_fills(self):
        value = SyntheticMarketInput.from_dict(self.body)
        self.assertEqual(value.quote_at(self.schedule, as_of=self.at + timedelta(seconds=60)).at, self.at)
        for shift in (timedelta(microseconds=-1), timedelta(seconds=60, microseconds=1)):
            with self.assertRaisesRegex(MarketInputError, "future or stale"):
                value.quote_at(self.schedule, as_of=self.at + shift)
        with self.assertRaisesRegex(MarketInputError, "backdated"):
            self.prepare(as_of=self.at + timedelta(seconds=1))

    def test_future_availability_and_reference_cutoff_refuse(self):
        body = deepcopy(self.body)
        body["validated_at"] = "2025-04-04T14:00:01Z"
        with self.assertRaisesRegex(MarketInputError, "unavailable"):
            self.prepare(body)
        body = deepcopy(self.body)
        body["reference"]["available_at"] = "2025-04-03T22:00:00.000001Z"
        with self.assertRaisesRegex(MarketInputError, "preceding-session cutoff"):
            self.prepare(body)
        body["reference"]["available_at"] = "2025-04-03T22:00:00Z"
        self.assertEqual(self.prepare(body).issuer_id, "SYN-ISSUER-A")

    def test_calendar_mapping_dates_and_settlement_are_explicit(self):
        for change in ({"calendar_sha256": "0" * 64}, {"session_date": "2025-04-07"}):
            body = dict(self.body, **change)
            with self.assertRaises(ValueError):
                self.prepare(body)
        body = deepcopy(self.body)
        body["reference"]["valid_through"] = "2025-04-03"
        with self.assertRaisesRegex(MarketInputError, "dated mapping"):
            self.prepare(body)
        for day in (date(2025, 4, 3), date(2025, 4, 5)):
            with self.assertRaises(ValueError):
                self.prepare(settlement_session=day)

    def test_extended_hours_and_protected_year_are_not_execution_inputs(self):
        body = deepcopy(self.body)
        for name in ("quote", "trade"):
            body[name].update(start_utc="2025-04-04T21:59:00Z", end_utc="2025-04-04T22:00:00Z")
        body.update(received_at="2025-04-04T22:00:00Z", validated_at="2025-04-04T22:00:00Z")
        with self.assertRaisesRegex(MarketInputError, "regular session"):
            self.prepare(body, as_of=fixture_instant(date(2025, 4, 4), 18))
        body["validated_at"] = "2026-09-01T22:00:00Z"
        with self.assertRaisesRegex(MarketInputError, "2024/2025"):
            SyntheticMarketInput.from_dict(body)

    def test_comparator_requires_explicit_etf_reference_and_retains_identity(self):
        body = deepcopy(self.body)
        body["reference"].update(issuer_id="SYN-SPY", instrument_type="ETF")
        self.assertEqual(self.prepare(body).minute.issuer, "SYN-SPY")


if __name__ == "__main__":
    unittest.main()
