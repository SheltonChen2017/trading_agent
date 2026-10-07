from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import unittest

from research.guidance_revision_drift.controls import ResearchControlError
from research.guidance_revision_drift.qc_adapter import (
    QcAdapterError, QcFixtureAdapter, QcQuoteSnapshot, QcTradeSnapshot,
    SecurityBinding, adapter_manifest,
)
from research.guidance_revision_drift.simulation import Quote, Session, Simulation, SimulationError


D = Decimal


def at(day, hour=14, minute=30):
    return datetime(2025, 4, day, hour, minute, tzinfo=timezone.utc)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(tuple(Session(date(2025, 4, d), at(d, 13, 30), at(d, 20, 0)) for d in (3, 4, 7, 8)))
        self.bindings = (SecurityBinding("SYN-SEC", "SYN-ISSUER", date(2025, 1, 1), date(2025, 12, 31)),)
        self.adapter = QcFixtureAdapter(self.sim, self.bindings)
        self.quote = QcQuoteSnapshot("SYN-SEC", at(4, 14, 0), at(4, 14, 1), D("49.99"), D("50"))
        self.trade = QcTradeSnapshot("SYN-SEC", self.quote.start_utc, self.quote.end_utc, 10000)

    def callback(self, quote=None, trade=None):
        return self.adapter.on_minute(quote or self.quote, trade or self.trade,
                                      adv20=D("20000000"), settlement_session=date(2025, 4, 7))

    def test_normalized_pair_fills_only_local_order_and_is_idempotent(self):
        order = self.sim.submit_entry("SYN-EVENT", "SYN-ISSUER", "tech", at(4, 14, 0),
                                     Quote(at(4, 14, 0), D("49.99"), D("50")), D("20000000"))
        fills = self.callback()
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].order_id, order.order_id)
        self.assertEqual(fills[0].price, D("50.025"))
        before = self.sim.snapshot()
        self.assertEqual(self.callback(), ())
        self.assertEqual(self.sim.snapshot(), before)
        self.assertEqual(len(self.adapter.receipt_hashes), 1)

    def test_quote_trade_mismatch_or_conflicting_replay_is_atomic(self):
        for change in ({"security_id": "SYN-OTHER"}, {"start_utc": at(4, 14, 1), "end_utc": at(4, 14, 2)}):
            before = self.sim.snapshot()
            with self.assertRaises(QcAdapterError):
                self.callback(trade=replace(self.trade, **change))
            self.assertEqual(self.sim.snapshot(), before)
        self.callback()
        before = self.sim.snapshot()
        with self.assertRaises(QcAdapterError):
            self.callback(trade=replace(self.trade, volume=20000))
        self.assertEqual(self.sim.snapshot(), before)

    def test_raw_nonfillforward_exact_prices_and_utc_are_required(self):
        for changes in ({"normalization": "Adjusted"}, {"fill_forward": True},
                        {"fill_forward": 0}, {"bid_close": 50.0}, {"bid_close": D("NaN")},
                        {"bid_close": D("51")}, {"end_utc": datetime(2025, 4, 4, 14, 1)},
                        {"end_utc": at(4, 14, 2)}, {"security_id": "AAPL"}):
            with self.subTest(changes=changes), self.assertRaises(QcAdapterError):
                replace(self.quote, **changes)
        for volume in (True, 100.0, -1):
            with self.assertRaises(QcAdapterError):
                replace(self.trade, volume=volume)

    def test_dated_binding_and_no_sdk_or_external_host_injection(self):
        binding = replace(self.bindings[0], valid_through=date(2025, 4, 3))
        self.adapter = QcFixtureAdapter(self.sim, (binding,))
        with self.assertRaises(QcAdapterError):
            self.callback()
        with self.assertRaises(QcAdapterError):
            QcFixtureAdapter(object(), self.bindings)
        with self.assertRaises(QcAdapterError):
            QcFixtureAdapter(self.sim, self.bindings * 2)

    def test_forged_snapshot_revalidated_before_callback(self):
        object.__setattr__(self.quote, "fill_forward", True)
        with self.assertRaises(QcAdapterError):
            self.callback()
        self.assertEqual(self.adapter.receipt_hashes, ())

    def test_binding_uses_new_york_date_without_permitting_extended_hours(self):
        # 00:01 UTC on Apr-4 is still Apr-3 in New York. A valid Apr-3 mapping
        # reaches the regular-session gate; a UTC-only Apr-4 mapping must not.
        quote = replace(self.quote, start_utc=at(4, 0, 0), end_utc=at(4, 0, 1))
        trade = replace(self.trade, start_utc=quote.start_utc, end_utc=quote.end_utc)
        before = self.sim.snapshot()
        for bound_day, error, message in (
            (date(2025, 4, 3), SimulationError, "regular-session"),
            (date(2025, 4, 4), QcAdapterError, "dated validity"),
        ):
            with self.subTest(bound_day=bound_day):
                self.adapter = QcFixtureAdapter(self.sim, (replace(self.bindings[0],
                    valid_from=bound_day, valid_through=bound_day),))
                with self.assertRaisesRegex(error, message):
                    self.callback(quote=quote, trade=trade)
                self.assertEqual(self.sim.snapshot(), before)
                self.assertEqual(self.adapter.receipt_hashes, ())

    def test_mutating_original_binding_cannot_redirect_market_data(self):
        self.sim.submit_entry("SYN-EVENT", "SYN-ISSUER", "tech", at(4, 14, 0),
                              Quote(at(4, 14, 0), D("49.99"), D("50")), D("20000000"))
        object.__setattr__(self.bindings[0], "issuer_id", "SYN-OTHER")
        fills = self.callback()
        self.assertEqual(fills[0].issuer, "SYN-ISSUER")

    def test_manifest_has_no_cloud_completion_or_permission_and_launch_refuses(self):
        manifest = adapter_manifest()
        self.assertIsNone(manifest["qc_engine_version"])
        self.assertIsNone(manifest["qc_backtest_id"])
        self.assertFalse(manifest["cloud_completed"])
        self.assertFalse(manifest["qc_launch"])
        with self.assertRaises(ResearchControlError):
            self.adapter.launch()


if __name__ == "__main__":
    unittest.main()
