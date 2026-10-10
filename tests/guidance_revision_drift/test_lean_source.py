"""Small Python shim executes the real source callbacks, NOT LEAN bindings.

It intentionally cannot certify engine scheduling, fees, subscriptions,
buying power, data reader integration, .NET conversions or cloud completion.
"""
from datetime import datetime, timezone
from dataclasses import replace
from decimal import Decimal
import importlib
import json
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch

from data.financial_primitives import exact_decimal_multiply, exact_decimal_sum
from research.guidance_revision_drift.lean_bridge import BridgeError, fixture_frames, fixture_stream
from research.guidance_revision_drift.contracts import CANDIDATE_SHA256
from research.guidance_revision_drift.native_observation import FIXTURE_SHA256
from research.guidance_revision_drift.simulation import Simulation
from research.guidance_revision_drift.trace_transport import TraceTransportError, reconstruct_trace_fragments, trace_fragment_anchor


class CashAmount:
    def __init__(self, amount, currency):
        self.amount, self.currency = Decimal(amount), currency


class OrderFee:
    def __init__(self, value):
        self.value = value


class OrderEvent:
    def __init__(self, order, at, fee):
        self.order_id, self.utc_time, self.order_fee = order.id, at, fee
        self.fill_quantity, self.fill_price, self.status, self.id = 0, 0, order.status, 0
        self.symbol = order.symbol


class Portfolio(dict):
    cash = Decimal(0)

    @property
    def total_portfolio_value(self):
        if hasattr(self, "nav_override"):
            return self.nav_override
        return exact_decimal_sum((self.cash, *(exact_decimal_multiply(row.quantity, row.security.price) for row in self.values())))


class Slice(dict):
    def contains_key(self, symbol):
        return symbol in self


class QCAlgorithm:
    live_mode = False

    def __init__(self):
        self.portfolio = Portfolio()
        self.native_orders = []
        self.debug_messages = []
        self.log_messages = []

    def set_time_zone(self, value):
        self.zone = value
        self.time_zone = NS(id=value)

    def set_start_date(self, *value):
        self.start = value

    def set_end_date(self, *value):
        self.end = value

    def set_cash(self, value):
        self.portfolio.cash = Decimal(value)

    def set_benchmark(self, value):
        self.benchmark = value

    def add_data(self, data_class, ticker, *args):
        self.asserted_subscription = (data_class, ticker, args)
        security = NS(symbol=ticker, price=Decimal("50"))
        self.portfolio[ticker] = NS(quantity=Decimal(0), security=security)
        def configured(name, model):
            setattr(self, name, model)
            setattr(security, name, model)
        security.set_fill_model = lambda model: configured("fill_model", model)
        security.set_fee_model = lambda model: configured("fee_model", model)
        security.set_settlement_model = lambda model: configured("settlement_model", model)
        return security

    def _order(self, symbol, quantity, kind, tag):
        order = NS(id=len(self.native_orders) + 1, status="submitted", quantity=quantity,
                   symbol=symbol, kind=kind, tag=tag, event_sequence=0)
        self.native_orders.append(order)
        # Exercise synchronous submission callback before bridge.bind.
        self.on_order_event(OrderEvent(order, self.utc_time, OrderFee(CashAmount(0, "QCC"))))
        ticket = NS(order_id=order.id)
        def cancel(reason):
            order.event_sequence += 1
            event = OrderEvent(order, self.utc_time, OrderFee(CashAmount(0, "QCC")))
            event.status, event.id = "cancel_pending", order.event_sequence
            order.status = event.status
            self.on_order_event(event)
            order.event_sequence += 1
            event = OrderEvent(order, self.utc_time, OrderFee(CashAmount(0, "QCC")))
            event.status, event.id = "canceled", order.event_sequence
            order.status = event.status
            self.on_order_event(event)
            return NS(is_success=True)
        ticket.cancel = cancel
        return ticket

    def limit_order(self, symbol, quantity, limit, tag):
        return self._order(symbol, quantity, "limit", tag)

    def market_order(self, symbol, quantity, asynchronous, tag):
        if asynchronous is not True:
            raise AssertionError("market order must be asynchronous")
        return self._order(symbol, quantity, "market", tag)

    def debug(self, value):
        self.debug_messages.append(value)

    def log(self, value):
        self.log_messages.append(value)


def sdk_shim():
    module = ModuleType("AlgorithmImports")
    values = dict(QCAlgorithm=QCAlgorithm, PythonData=Slice, FillModel=type("FillModel", (), {}),
        OrderEvent=OrderEvent, OrderFee=OrderFee, CashAmount=CashAmount,
        OrderStatus=NS(SUBMITTED="submitted", FILLED="filled", PARTIALLY_FILLED="partial",
                       CANCEL_PENDING="cancel_pending", CANCELED="canceled"),
        Resolution=NS(MINUTE="minute"), TimeZones=NS(UTC="UTC"),
        ConstantFeeModel=lambda fee: ("constant", fee), ImmediateSettlementModel=lambda: "immediate",
        SubscriptionTransportMedium=NS(LOCAL_FILE="local"),
        SubscriptionDataSource=lambda path, medium: (path, medium))
    module.__dict__.update(values)
    return module


class LeanSourceTests(unittest.TestCase):
    def setUp(self):
        self.patch_sdk = patch.dict(sys.modules, {"AlgorithmImports": sdk_shim()})
        self.patch_sdk.start()
        self.name = "research.guidance_revision_drift.lean.main"
        sys.modules.pop(self.name, None)
        self.source = importlib.import_module(self.name)

    def tearDown(self):
        sys.modules.pop(self.name, None)
        self.patch_sdk.stop()

    def initialize(self):
        algo = self.source.GuidanceRevisionDriftAlgorithm()
        # Invented shim identity, not actual source/bundle custody or SDK proof.
        algo._gdr_runtime_context = {"runtime_source_sha256": "1" * 64, "bundle_sha256": "2" * 64,
                                     "candidate_sha256": CANDIDATE_SHA256, "fixture_sha256": FIXTURE_SHA256}
        with patch.object(self.source, "_read_regular_file", return_value=fixture_stream()):
            algo.initialize()
        return algo

    def test_real_callbacks_submit_native_orders_emit_exact_fees_and_finish(self):
        algo = self.initialize()
        unsettled_seen = False
        for frame in fixture_frames():
            algo.utc_time = datetime.fromisoformat(frame["at"]).replace(tzinfo=None)
            algo.on_data(Slice({algo.symbol: {"frame_index": frame["index"]}}))
            for order in algo.native_orders:
                method = algo.fill_model.limit_fill if order.kind == "limit" else algo.fill_model.market_fill
                event = method(None, order)
                if not event.fill_quantity:
                    continue
                order.event_sequence += 1
                event.id = order.event_sequence
                algo.portfolio[algo.symbol].quantity += event.fill_quantity
                algo.portfolio.cash = exact_decimal_sum((algo.portfolio.cash,
                    -exact_decimal_multiply(Decimal(event.fill_quantity), event.fill_price),
                    -event.order_fee.value.amount))
                algo.on_order_event(event)
                self.assertEqual(method(None, order).fill_quantity, 0)
            snapshot = algo.bridge.engine.snapshot()
            if snapshot["receivables"]:
                unsettled_seen = True
                self.assertGreater(algo.portfolio.cash, Decimal(snapshot["settled_cash"]))
                self.assertEqual(algo.portfolio.cash, exact_decimal_sum((
                    Decimal(snapshot["settled_cash"]),
                    *(Decimal(item["amount"]) for item in snapshot["receivables"]))))
        algo.on_end_of_algorithm()
        self.assertTrue(unsettled_seen, "exercise the sale-to-dated-settlement boundary")
        self.assertEqual([o.kind for o in algo.native_orders], ["limit", "market"])
        self.assertEqual(algo.fee_model, ("constant", 0))
        self.assertEqual(algo.settlement_model, "immediate")
        self.assertEqual(algo.benchmark, "SYN-GDR")
        self.assertEqual(algo.portfolio.cash, Decimal(algo.bridge.finish()["strategy"]["settled_cash"]))
        self.assertIn("no empirical", algo.debug_messages[-1])
        self.assertEqual(algo.bridge.finish()["native_account_checkpoints"], 372)
        self.assertFalse(algo.bridge.finish()["settlement_parity_verified"])
        self.assertIn("trace_count=752", algo.debug_messages[-1])
        self.assertIn(algo.bridge.finish()["protocol_trace_head_sha256"], algo.debug_messages[-1])
        with patch.object(algo.bridge, "_account_checkpoints", 371), \
             self.assertRaisesRegex(BridgeError, "incomplete native account checkpoint"):
            algo.on_end_of_algorithm()
        algo.portfolio.cash += Decimal(1)
        with self.assertRaisesRegex(BridgeError, "cash mismatch"):
            algo.on_end_of_algorithm()

    def test_live_or_changed_sidecar_cannot_initialize(self):
        algo = self.source.GuidanceRevisionDriftAlgorithm()
        algo.live_mode = True
        with self.assertRaisesRegex(BridgeError, "live"):
            algo.initialize()
        algo.live_mode = False
        with patch.object(self.source, "_read_regular_file", return_value=b"replacement"), self.assertRaises(BridgeError):
            algo.initialize()

    def test_reader_only_accepts_exact_known_frames_and_local_nonlive_source(self):
        reader = self.source.GuidanceSyntheticData()
        config = NS(symbol="SYN-GDR")
        day = datetime(2025, 1, 2)
        line = fixture_stream().splitlines()[0].decode()
        point = reader.reader(config, line, day, False)
        self.assertEqual(point["frame_index"], 0)
        self.assertEqual(reader.reader(config, line, datetime(2025, 1, 3), False)["frame_index"], 0)
        with self.assertRaises(BridgeError):
            reader.reader(config, line.replace('"50"', '"51"'), day, False)
        with self.assertRaises(BridgeError):
            reader.get_source(config, day, True)
        self.assertEqual(reader.get_source(config, day, False)[1], "local")

    def test_multiday_file_uses_record_time_not_reader_creation_day(self):
        reader = self.source.GuidanceSyntheticData()
        points = [reader.reader(NS(symbol="SYN-GDR"), line.decode(), datetime(2025, 1, 2), False)
                  for line in fixture_stream().splitlines()]
        self.assertEqual([point["frame_index"] for point in points if point is not None], list(range(372)))

    def test_reader_refuses_duplicate_keys_float_alias_and_unknown_records(self):
        reader = self.source.GuidanceSyntheticData()
        line = fixture_stream().splitlines()[0].decode()
        invalid = [line.replace('"index":0', '"index":0,"index":0'),
                   line.replace('"index":0', '"index":0.0'),
                   line.replace('"index":0', '"index":false'),
                   json.dumps(json.loads(line) | {"extra": 1}), "[]"]
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(ValueError):
                reader.reader(NS(symbol="SYN-GDR"), body, datetime(2025, 1, 2), False)

    def test_zero_qcc_submission_is_control_only(self):
        algo = self.initialize()
        for frame in fixture_frames():
            algo.utc_time = datetime.fromisoformat(frame["at"]).replace(tzinfo=None)
            algo.on_data(Slice({algo.symbol: {"frame_index": frame["index"]}}))
            if algo.native_orders:
                break
        order = algo.native_orders[0]
        # Re-deliver the original submission with the actual SDK zero sentinel.
        event = OrderEvent(order, algo.utc_time, OrderFee(CashAmount(0, "QCC")))
        algo.on_order_event(event)
        for currency, fee, quantity, price, status in (
                ("QCC", 1, 0, 0, "submitted"), ("EUR", 0, 0, 0, "submitted"),
                ("QCC", 0, 1, 50, "filled"), ("QCC", 0, 0, 0, "filled")):
            event.order_fee = OrderFee(CashAmount(fee, currency))
            event.fill_quantity, event.fill_price, event.status = quantity, price, status
            with self.subTest(currency=currency, status=status), self.assertRaises(BridgeError):
                algo.on_order_event(event)

    def test_missing_frame_and_native_cash_drift_are_visible_failures(self):
        algo = self.initialize()
        algo.utc_time = datetime.fromisoformat(fixture_frames()[1]["at"])
        with self.assertRaises(BridgeError):
            algo.on_data(Slice({algo.symbol: {"frame_index": 1}}))
        with self.assertRaises(BridgeError):
            algo.on_end_of_algorithm()

    def test_transient_native_account_drift_refuses_before_frame_commit(self):
        # A mismatch which self-corrects before the final callback must still
        # refuse at the next frame; no shadow/trace effects may be consumed.
        for field in ("cash", "quantity"):
            with self.subTest(field=field):
                algo = self.initialize()
                first, second = fixture_frames()[:2]
                algo.utc_time = datetime.fromisoformat(first["at"])
                algo.on_data(Slice({algo.symbol: {"frame_index": first["index"]}}))
                account = algo.portfolio if field == "cash" else algo.portfolio[algo.symbol]
                previous = getattr(account, field)
                setattr(account, field, previous + Decimal(1))
                before = algo.bridge.engine.snapshot(), algo.bridge.protocol_trace()
                algo.utc_time = datetime.fromisoformat(second["at"])
                with self.assertRaisesRegex(BridgeError, "native.*mismatch"):
                    algo.on_data(Slice({algo.symbol: {"frame_index": second["index"]}}))
                self.assertEqual((algo.bridge.engine.snapshot(), algo.bridge.protocol_trace()), before)
                self.assertEqual(algo.bridge.current_at, datetime.fromisoformat(first["at"]))
                setattr(account, field, previous)
                algo.on_data(Slice({algo.symbol: {"frame_index": second["index"]}}))
                self.assertEqual(algo.bridge.current_at, datetime.fromisoformat(second["at"]))

    def test_native_account_checkpoint_requires_finite_whole_inventory(self):
        for quantity, cash in ((Decimal("0.5"), Decimal("100000")),
                               (Decimal("NaN"), Decimal("100000")),
                               (Decimal(0), Decimal("Infinity")),
                               (Decimal(-1), Decimal("100000"))):
            with self.subTest(quantity=quantity, cash=cash):
                algo = self.initialize()
                algo.portfolio[algo.symbol].quantity, algo.portfolio.cash = quantity, cash
                frame = fixture_frames()[0]
                algo.utc_time = datetime.fromisoformat(frame["at"])
                before = algo.bridge.engine.snapshot(), algo.bridge.protocol_trace()
                with self.assertRaises(ValueError):
                    algo.on_data(Slice({algo.symbol: {"frame_index": 0}}))
                self.assertEqual((algo.bridge.engine.snapshot(), algo.bridge.protocol_trace()), before)

    def test_account_checkpoint_alias_partial_input_and_trace_failure_are_atomic(self):
        for quantity, cash in ((0, Decimal("100000")), (Decimal(0), "100000"),
                               (False, Decimal("100000")), (Decimal(0), 100000.0),
                               (None, Decimal("100000")), (Decimal(0), None)):
            with self.subTest(quantity=quantity, cash=cash):
                bridge = self.initialize().bridge
                before = bridge.engine.snapshot(), bridge.protocol_trace()
                with self.assertRaisesRegex(BridgeError, "malformed native account"):
                    bridge.step(fixture_frames()[0], native_quantity=quantity, native_cash=cash)
                self.assertEqual((bridge.engine.snapshot(), bridge.protocol_trace()), before)
        bridge = self.initialize().bridge
        before = bridge.engine.snapshot(), bridge.protocol_trace()
        # The checkpoint fits, but the following frame record does not. Neither
        # draft record nor the frame's shadow effects may survive the refusal.
        with patch("research.guidance_revision_drift.lean_bridge.MAX_TRACE_RECORDS", 1), \
             self.assertRaisesRegex(BridgeError, "trace capacity"):
            bridge.step(fixture_frames()[0], native_quantity=Decimal(0), native_cash=Decimal("100000"))
        self.assertEqual((bridge.engine.snapshot(), bridge.protocol_trace()), before)

    def test_bridge_classifies_malformed_account_scalars_itself_atomically(self):
        # The native callback converts LEAN values with to_decimal, which
        # already rejects NaN/Infinity, and the shadow invariants make any
        # negative, fractional or infinite observation a plain mismatch. The
        # bridge's own boundary must still classify such Decimal input as
        # malformed for any direct caller, before comparing it with the shadow.
        for quantity, cash in ((Decimal("NaN"), Decimal("100000")),
                               (Decimal(0), Decimal("Infinity")),
                               (Decimal(0), Decimal("sNaN")),
                               (Decimal(-1), Decimal("100000")),
                               (Decimal(0), Decimal("-0.01")),
                               (Decimal("0.5"), Decimal("100000"))):
            with self.subTest(quantity=quantity, cash=cash):
                bridge = self.initialize().bridge
                before = bridge.engine.snapshot(), bridge.protocol_trace()
                with self.assertRaisesRegex(BridgeError, "malformed native account observation"):
                    bridge.step(fixture_frames()[0], native_quantity=quantity, native_cash=cash)
                self.assertEqual((bridge.engine.snapshot(), bridge.protocol_trace()), before)
                self.assertEqual(bridge._account_checkpoints, 0)

    def test_multiday_reader_and_before_after_data_scans_reconcile_partial_cancel(self):
        # Mirrors the documented synchronous scan order, not .NET execution.
        # LEAN suppresses unchanged, zero-quantity fill-model results.
        algo = self.initialize()
        reader = self.source.GuidanceSyntheticData()
        first_day = datetime(2025, 1, 2)
        config = NS(symbol=algo.symbol)

        def scan():
            for order in algo.native_orders:
                if order.status in {"filled", "canceled"}:
                    continue
                method = algo.fill_model.limit_fill if order.kind == "limit" else algo.fill_model.market_fill
                event = method(None, order)
                if event.status == order.status and event.fill_quantity == 0:
                    continue
                order.event_sequence += 1
                event.id = order.event_sequence
                order.status = event.status
                algo.portfolio[algo.symbol].quantity += event.fill_quantity
                algo.portfolio.cash = exact_decimal_sum((algo.portfolio.cash,
                    -exact_decimal_multiply(Decimal(event.fill_quantity), event.fill_price),
                    -event.order_fee.value.amount))
                algo.on_order_event(event)

        original = Simulation.process_minute
        with patch.object(Simulation, "process_minute",
                          lambda engine, minute: original(engine, replace(minute, volume=1000))):
            for line in fixture_stream().splitlines():
                point = reader.reader(config, line.decode(), first_day, False)
                self.assertIsNotNone(point)
                algo.utc_time = point.end_time
                scan()
                algo.on_data(Slice({algo.symbol: point}))
                scan()
                scan()  # repeated scans must not duplicate receipts or fees
        # Changed shadow source-volume is a deliberate shim diagnostic, not
        # the approved fixed base candidate. Reconciliation remains testable,
        # but a different receipt transcript must not export fixed completion.
        with self.assertRaisesRegex(TraceTransportError, "complete fixed synthetic trace"):
            algo.on_end_of_algorithm()
        fragments = tuple(row.encode() for row in algo.log_messages)
        output = reconstruct_trace_fragments(fragments, expected_sha256=trace_fragment_anchor(fragments),
                                              expected_runtime_context=algo._gdr_context.to_dict())
        self.assertEqual(output["metadata"]["status"], "failed")
        self.assertEqual(output["trace"], algo.bridge.protocol_trace())
        self.assertFalse(algo.debug_messages)
        report = algo.bridge.finish()
        self.assertEqual(report["strategy"]["orders"][0]["status"], "cancelled")
        self.assertEqual(report["strategy"]["orders"][0]["filled_quantity"], 10)
        self.assertEqual(report["strategy"]["reserved_cash"], "0")
        self.assertEqual([row["payload"]["status"] for row in algo.bridge.protocol_trace()["records"]
                          if row["kind"] == "acknowledgement"],
                         ["submitted", "partially_filled", "cancel_pending", "canceled", "submitted", "filled"])


if __name__ == "__main__":
    unittest.main()
