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
from research.guidance_revision_drift.readable_transport import (
    COMPACT_SCHEMA, MAX_LINE_BYTES, MAX_LOG_BYTES, MAX_MESSAGES,
    PLATFORM_FIXED_LOG_RESERVE_BYTES, PLATFORM_OVERHEAD_BYTES_PER_MESSAGE,
    ReadableTransportError, reconstruct_readable_evidence,
    readable_evidence_anchor,
)


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
        messages = tuple(row.encode("ascii") for row in algo.log_messages)
        self.assertEqual(json.loads(messages[0])["schema"], COMPACT_SCHEMA)
        self.assertTrue(all(type(json.loads(row)) is dict for row in messages))
        self.assertTrue(all(len(row) <= 200 for row in messages))
        self.assertLessEqual(sum(len(row) + 1 for row in messages), 100000)
        self.assertEqual(algo._gdr_evidence_log_bytes, sum(len(row) + 1 for row in messages))
        self.assertEqual(algo._gdr_evidence_log_messages, len(messages))
        self.assertLessEqual(algo._reserved_evidence_log_bytes(), MAX_LOG_BYTES)
        output = reconstruct_readable_evidence(messages,
            expected_sha256=readable_evidence_anchor(messages),
            expected_runtime_context=algo._gdr_context.to_dict())
        self.assertEqual(output["trace"], algo.bridge.protocol_trace())
        self.assertEqual(output["metadata"]["status"], "complete")
        with patch.object(algo.bridge, "_account_checkpoints", 371), \
             self.assertRaisesRegex(BridgeError, "incomplete native account checkpoint"):
            algo.on_end_of_algorithm()
        algo.portfolio.cash += Decimal(1)
        with self.assertRaisesRegex(BridgeError, "cash mismatch"):
            algo.on_end_of_algorithm()

    def test_repeated_readable_exports_cannot_reopen_the_evidence_log_byte_budget(self):
        from tests.guidance_revision_drift.test_completion_evidence import drive
        from tests.guidance_revision_drift.test_native_dossier import metadata
        algo = self.initialize()
        algo.bridge = drive()
        body = metadata(algo.bridge.protocol_trace())
        algo._emit_trace(body)
        first = list(algo.log_messages)
        first_payload, first_messages = algo._gdr_evidence_log_bytes, algo._gdr_evidence_log_messages
        # RP33 changes the contract from raw payload to an assumed wrapped
        # cumulative budget. Derive refusal from actual retained reservations,
        # not an unconditional assertion that any second export must overflow.
        while (algo._reserved_evidence_log_bytes() + first_payload
               + PLATFORM_OVERHEAD_BYTES_PER_MESSAGE * first_messages <= MAX_LOG_BYTES
               and algo._gdr_evidence_log_messages + first_messages <= MAX_MESSAGES + 1):
            algo._emit_trace(body)
        before = (list(algo.log_messages), algo._gdr_evidence_log_bytes, algo._gdr_evidence_log_messages)
        with self.assertRaisesRegex(ReadableTransportError, "cumulative"):
            algo._emit_trace(body)
        self.assertEqual((algo.log_messages, algo._gdr_evidence_log_bytes, algo._gdr_evidence_log_messages),
                         before, "refuse the complete export before emitting any new line")
        self.assertGreaterEqual(len(algo.log_messages), len(first))
        algo._emit_failure("on_end_of_algorithm", RuntimeError("invented failure"))
        self.assertEqual(algo._gdr_evidence_log_bytes,
                         sum(len(row.encode("ascii")) + 1 for row in algo.log_messages))
        self.assertEqual(algo._gdr_evidence_log_messages, len(algo.log_messages))
        self.assertLessEqual(algo._reserved_evidence_log_bytes(), MAX_LOG_BYTES)
        self.assertTrue(any("diagnostic_export_unavailable" in row for row in algo.log_messages))

    def test_ambiguous_log_delivery_keeps_its_reservation_and_invalid_budget_refuses(self):
        algo = self.initialize()
        def delivered_then_failed(message):
            algo.log_messages.append(message)
            raise RuntimeError("invented ambiguous delivery")
        with patch.object(algo, "log", side_effect=delivered_then_failed):
            with self.assertRaises(RuntimeError):
                algo._log_evidence("SYN-observation")
        retained = len(b"SYN-observation") + 1
        self.assertEqual(algo._gdr_evidence_log_bytes, retained)
        self.assertEqual(algo._gdr_evidence_log_messages, 1)
        self.assertEqual(algo._reserved_evidence_log_bytes(), retained
                         + PLATFORM_OVERHEAD_BYTES_PER_MESSAGE + PLATFORM_FIXED_LOG_RESERVE_BYTES)
        for invalid in (True, -1, 100001, "0"):
            algo._gdr_evidence_log_bytes = invalid
            with self.subTest(budget=invalid), self.assertRaises(ReadableTransportError):
                algo._log_evidence("not emitted")
        algo._gdr_evidence_log_bytes = retained
        for invalid in (True, -1, MAX_MESSAGES + 2, "0", 0):
            algo._gdr_evidence_log_messages = invalid
            with self.subTest(messages=invalid), self.assertRaises(ReadableTransportError):
                algo._log_evidence("not emitted")
            self.assertEqual(algo._gdr_evidence_log_messages, invalid)
        self.assertEqual(algo.log_messages, ["SYN-observation"])


    def test_single_evidence_line_obeys_line_and_remaining_budget_bounds(self):
        # GDR-CR31-007: refusal markers bypass the whole-export pre-check, so
        # the per-line guard alone keeps them inside both bounds.
        algo = self.initialize()
        before = list(algo.log_messages)
        with self.assertRaisesRegex(ReadableTransportError, "budget"):
            algo._log_evidence("x" * (MAX_LINE_BYTES + 1))
        # A supplied coherent prior state leaves exactly 46 reserved bytes:
        # five characters plus LF plus the assumed 40-byte wrapper.
        algo._gdr_evidence_log_messages = 500
        algo._gdr_evidence_log_bytes = (MAX_LOG_BYTES - PLATFORM_FIXED_LOG_RESERVE_BYTES
            - PLATFORM_OVERHEAD_BYTES_PER_MESSAGE * 500 - 46)
        prior = algo._gdr_evidence_log_bytes
        with self.assertRaisesRegex(ReadableTransportError, "budget"):
            algo._log_evidence("123456")
        self.assertEqual(algo._gdr_evidence_log_bytes, prior)
        self.assertEqual(algo._gdr_evidence_log_messages, 500)
        self.assertEqual(algo.log_messages, before)
        algo._log_evidence("12345")
        self.assertEqual(algo._gdr_evidence_log_bytes, prior + 6)
        self.assertEqual(algo._gdr_evidence_log_messages, 501)
        self.assertEqual(algo._reserved_evidence_log_bytes(), MAX_LOG_BYTES)

    def test_cumulative_message_ceiling_refuses_lines_and_whole_exports_atomically(self):
        from research.guidance_revision_drift.native_observation import failure_diagnostics
        algo = self.initialize()
        algo._gdr_evidence_log_messages = MAX_MESSAGES + 1
        algo._gdr_evidence_log_bytes = 2 * (MAX_MESSAGES + 1)
        before = algo._gdr_evidence_log_bytes, algo._gdr_evidence_log_messages
        with self.assertRaises(ReadableTransportError):
            algo._log_evidence("x")
        self.assertEqual((algo._gdr_evidence_log_bytes, algo._gdr_evidence_log_messages), before)
        self.assertFalse(algo.log_messages)
        # A small valid failed-prefix export isolates the count guard from the
        # byte guard; a complete ~95 KB export would hit both at this count.
        body = {"status": "failed", "diagnostics": failure_diagnostics("on_data", RuntimeError(),
            algo.bridge, algo.early_events, algorithm=algo),
            "observations": json.loads(algo._gdr_observations_bytes),
            "valuation_schema": "gdr-native-price-nav-v1", "valuation_rows": []}
        fragments = self.source.export_compact_readable_evidence(algo.bridge.protocol_trace(),
            runtime_context=algo._gdr_context.to_dict(), metadata=body)
        algo._gdr_evidence_log_messages = MAX_MESSAGES + 2 - len(fragments)
        algo._gdr_evidence_log_bytes = 2 * algo._gdr_evidence_log_messages
        self.assertLess(algo._reserved_evidence_log_bytes()
            + sum(len(raw) + 1 for raw in fragments)
            + PLATFORM_OVERHEAD_BYTES_PER_MESSAGE * len(fragments), MAX_LOG_BYTES)
        before = algo._gdr_evidence_log_bytes, algo._gdr_evidence_log_messages
        with self.assertRaises(ReadableTransportError):
            algo._emit_trace(body)
        self.assertEqual((algo._gdr_evidence_log_bytes, algo._gdr_evidence_log_messages), before)
        self.assertFalse(algo.log_messages, "count-only refusal must precede all SDK delivery")

    def test_whole_export_reserves_assumed_wrappers_before_any_sdk_delivery(self):
        from tests.guidance_revision_drift.test_completion_evidence import drive
        from tests.guidance_revision_drift.test_native_dossier import metadata
        algo = self.initialize()
        algo.bridge = drive()
        body = metadata(algo.bridge.protocol_trace())
        fragments = self.source.export_compact_readable_evidence(algo.bridge.protocol_trace(),
            runtime_context=algo._gdr_context.to_dict(), metadata=body)
        payload = sum(len(raw) + 1 for raw in fragments)
        algo._gdr_evidence_log_messages = 200
        algo._gdr_evidence_log_bytes = (MAX_LOG_BYTES - payload - 1
            - PLATFORM_FIXED_LOG_RESERVE_BYTES - PLATFORM_OVERHEAD_BYTES_PER_MESSAGE * 200)
        self.assertLess(algo._reserved_evidence_log_bytes() + payload, MAX_LOG_BYTES)
        self.assertGreater(algo._reserved_evidence_log_bytes() + payload
            + PLATFORM_OVERHEAD_BYTES_PER_MESSAGE * len(fragments), MAX_LOG_BYTES)
        self.assertLessEqual(algo._gdr_evidence_log_messages + len(fragments), MAX_MESSAGES + 1)
        before = algo._gdr_evidence_log_bytes, algo._gdr_evidence_log_messages
        with self.assertRaises(ReadableTransportError):
            algo._emit_trace(body)
        self.assertEqual((algo._gdr_evidence_log_bytes, algo._gdr_evidence_log_messages), before)
        self.assertFalse(algo.log_messages, "raw payload capacity must not allow a partial wrapped-overflow export")

    def test_missing_or_reset_counter_after_delivery_cannot_reopen_reserved_capacity(self):
        # Losing one counter must not drop already reserved wrapper capacity.
        # Deliberately erasing both counters is outside this local-state proof.
        for field, remove in (("_gdr_evidence_log_messages", True), ("_gdr_evidence_log_bytes", True),
                              ("_gdr_evidence_log_messages", False), ("_gdr_evidence_log_bytes", False)):
            with self.subTest(field=field, remove=remove):
                algo = self.initialize()
                algo._log_evidence("SYN-observation")
                before = list(algo.log_messages)
                if remove:
                    delattr(algo, field)
                else:
                    setattr(algo, field, 0)
                with self.assertRaises(ReadableTransportError):
                    algo._log_evidence("not emitted")
                algo._emit_failure("on_data", RuntimeError("invented failure"))
                self.assertEqual(algo.log_messages, before, "failure diagnostics cannot repair/reset poisoned counters")
                if remove:
                    self.assertFalse(hasattr(algo, field))
                else:
                    self.assertEqual(getattr(algo, field), 0)

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
        with self.assertRaisesRegex(ReadableTransportError, "complete fixed synthetic trace"):
            algo.on_end_of_algorithm()
        fragments = tuple(row.encode() for row in algo.log_messages)
        # This deliberately changed simulator is outside the fixed-source
        # digest route. Failure remains visible, but local fixed replay must
        # not manufacture a matching trace from changed protocol economics.
        if not any(row.startswith(b"GDR-NATIVE-REFUSED") for row in fragments):
            with self.assertRaises(ReadableTransportError):
                reconstruct_readable_evidence(fragments,
                    expected_sha256=readable_evidence_anchor(fragments),
                    expected_runtime_context=algo._gdr_context.to_dict())
        else:
            self.assertTrue(any("diagnostic_export_unavailable" in row for row in algo.log_messages))
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
