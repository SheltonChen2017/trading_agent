"""Native-source evidence safeguards exercised with invented SDK observations.

These tests are not LEAN scheduling, Python.NET conversion or cloud proof.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import importlib
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from data.financial_primitives import exact_decimal_multiply, exact_decimal_sum
from data.hashing import canonical_json
from research.guidance_revision_drift.contracts import CANDIDATE_SHA256
from research.guidance_revision_drift import native_observation as observations
from research.guidance_revision_drift.lean_bridge import BridgeError, fixture_frames, fixture_stream
from research.guidance_revision_drift.trace_transport import reconstruct_trace_fragments, trace_fragment_anchor
from guidance_revision_drift.test_lean_source import CashAmount, OrderEvent, OrderFee, Slice, sdk_shim


CONTEXT = {"runtime_source_sha256": "1" * 64, "bundle_sha256": "2" * 64,
           "candidate_sha256": CANDIDATE_SHA256, "fixture_sha256": observations.FIXTURE_SHA256}
STATUSES = {"submitted": "submitted", "filled": "filled", "partial": "partially_filled",
            "cancel_pending": "cancel_pending", "canceled": "canceled"}


def receipt(**changes):
    event = NS(order_id=1, id=0, symbol="SYN-GDR", status="submitted",
        utc_time=datetime(2025, 4, 4, 14, 5), fill_quantity=0, fill_price=0,
        order_fee=OrderFee(CashAmount(0, "QCC")))
    event.__dict__.update(changes)
    return event


def snapshot(event):
    return observations.ReceiptSnapshot.capture(event, expected_symbol="SYN-GDR", statuses=STATUSES)


def reflected(name):
    return NS(GetType=lambda: NS(FullName="QuantConnect." + name,
        Assembly=NS(GetName=lambda: NS(Name="InventedSDK", Version=NS(ToString=lambda: "0.0.synthetic")))))


class NativeObservationTests(unittest.TestCase):
    def test_runtime_context_is_immutable_exact_and_fixed(self):
        row = deepcopy(CONTEXT)
        fixed = observations.RuntimeContext.capture(row)
        row["bundle_sha256"] = "3" * 64
        projected = fixed.to_dict()
        projected["bundle_sha256"] = "4" * 64
        self.assertEqual(fixed.to_dict(), CONTEXT)
        for bad in (None, CONTEXT | {"approval": True}, CONTEXT | {"candidate_sha256": "5" * 64},
                    CONTEXT | {"fixture_sha256": "6" * 64}, CONTEXT | {"bundle_sha256": "G" * 64}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                observations.RuntimeContext.capture(bad)

    def test_observations_read_actual_labels_and_missing_sdk_is_unverified(self):
        algorithm = NS(time_zone=NS(id="UTC"))
        security = NS(symbol="SYN-GDR", fill_model=NS(), fee_model=("constant", 0), settlement_model="immediate")
        with patch.dict(sys.modules, {"clr": None, "pythonnet": None}):
            row = observations.observe_runtime(algorithm, security)
        self.assertEqual(row["objects"]["fee_model"]["python_type"], "builtins.tuple")
        self.assertIsNone(row["objects"]["fee_model"]["native_type"])
        self.assertIn("algorithm_assembly_version", row["missing"])
        self.assertIn("pythonnet_version", row["missing"])
        self.assertFalse(row["configuration_verified"])
        self.assertFalse(row["native_binding_verified"])

    def test_reflected_configuration_mismatches_refuse(self):
        algorithm = reflected("QCAlgorithm")
        algorithm.time_zone = NS(id="UTC")
        security = NS(symbol="SYN-GDR", fill_model=reflected("FillModelPythonWrapper"),
                      fee_model=reflected("ConstantFeeModel"), settlement_model=reflected("ImmediateSettlementModel"))
        row = observations.observe_runtime(algorithm, security)
        self.assertEqual(row["objects"]["algorithm"]["assembly_version"], "0.0.synthetic")
        for name, wrong in (("fill_model", "ImmediateFillModel"), ("fee_model", "InteractiveBrokerageFeeModel"),
                            ("settlement_model", "DelayedSettlementModel")):
            before = getattr(security, name)
            setattr(security, name, reflected(wrong))
            with self.subTest(name=name), self.assertRaises(observations.ObservationError):
                observations.observe_runtime(algorithm, security)
            setattr(security, name, before)
        algorithm.time_zone.id = "America/New_York"
        with self.assertRaises(observations.ObservationError):
            observations.observe_runtime(algorithm, security)
        algorithm.time_zone.id = "UTC"
        security.fee_model = NS(GetType=lambda: NS(FullName="QuantConnect.WrongFeeModel"))
        with self.assertRaises(observations.ObservationError):
            observations.observe_runtime(algorithm, security)

    def test_exact_whole_account_valuation_is_context_independent(self):
        with localcontext() as ctx:
            ctx.prec = 2
            row = observations.valuation_checkpoint(0, quantity=Decimal(7), cash=Decimal("9999.123456"),
                                                     price=Decimal(50), nav=Decimal("10349.123456"))
        self.assertEqual(row, (0, "50", "10349.123456"))
        for changed in (dict(price=Decimal(51)), dict(nav=Decimal("10350.123456")),
                        dict(quantity=Decimal("0.5")), dict(cash=Decimal(-1)),
                        dict(nav=Decimal("NaN")), dict(price=Decimal("1E+99999"))):
            args = dict(quantity=Decimal(7), cash=Decimal("9999.123456"), price=Decimal(50), nav=Decimal("10349.123456")) | changed
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                observations.valuation_checkpoint(0, **args)

    def test_early_sdk_object_mutation_cannot_change_snapshot_or_queue(self):
        event = receipt()
        fixed = snapshot(event)
        queue = observations.DeferredReceipts()
        queue.append(fixed)
        event.symbol, event.id, event.status, event.fill_quantity = "OTHER", 9, "filled", 100
        event.order_fee.value.amount = Decimal(123)
        self.assertEqual(queue.snapshots[0].to_dict()["status"], "submitted")
        self.assertEqual(queue.snapshots[0].to_dict()["fee"], "0")
        mutable_projection = fixed.to_dict()
        mutable_projection["quantity"] = 7
        self.assertEqual(fixed.to_dict()["quantity"], 0)
        with self.assertRaises((AttributeError, TypeError)):
            fixed.canonical_bytes = b"changed"

    def test_duplicate_conflict_and_overflow_are_atomic(self):
        queue = observations.DeferredReceipts()
        first = snapshot(receipt())
        queue.append(first)
        queue.append(snapshot(receipt()))
        self.assertEqual(queue.snapshots, (first,))
        before = queue.snapshots
        with self.assertRaisesRegex(observations.ObservationError, "conflicting"):
            queue.append(snapshot(receipt(status="canceled")))
        self.assertEqual(queue.snapshots, before)
        for i in range(1, observations.MAX_DEFERRED_EVENTS):
            queue.append(snapshot(receipt(id=i)))
        before = queue.snapshots
        with self.assertRaisesRegex(observations.ObservationError, "capacity"):
            queue.append(snapshot(receipt(id=observations.MAX_DEFERRED_EVENTS)))
        self.assertEqual(queue.snapshots, before)

    def test_symbol_id_clock_currency_aliases_and_nonfinite_economics_refuse(self):
        invalid = (dict(symbol="OTHER"), dict(order_id=True), dict(order_id=0), dict(id=False),
                   dict(id=-1), dict(utc_time="2025-04-04"), dict(fill_quantity=Decimal("0.5")),
                   dict(fill_price=Decimal("Infinity")), dict(fill_price=Decimal("1E+99999")),
                   dict(order_fee=OrderFee(CashAmount(0, "EUR"))), dict(status="unknown"),
                   dict(status="filled", fill_quantity=1, fill_price=50))
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                snapshot(receipt(**change))


class NativeSourceEvidenceTests(unittest.TestCase):
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
        algo._gdr_runtime_context = deepcopy(CONTEXT)
        with patch.object(self.source, "_read_regular_file", return_value=fixture_stream()):
            algo.initialize()
        return algo

    def output(self, algo):
        fragments = tuple(row.encode("ascii") for row in algo.log_messages)
        envelope = reconstruct_trace_fragments(fragments, expected_sha256=trace_fragment_anchor(fragments),
                                               expected_runtime_context=CONTEXT)
        return observations.validate_native_metadata(envelope["metadata"], envelope["trace"]), envelope

    def frame(self, algo, index):
        row = fixture_frames()[index]
        algo.utc_time = datetime.fromisoformat(row["at"])
        algo.on_data(Slice({algo.symbol: {"frame_index": index}}))

    def walk(self, algo):
        for frame in fixture_frames():
            self.frame(algo, frame["index"])
            for order in algo.native_orders:
                method = algo.fill_model.limit_fill if order.kind == "limit" else algo.fill_model.market_fill
                event = method(None, order)
                if not event.fill_quantity:
                    continue
                order.event_sequence += 1
                event.id = order.event_sequence
                algo.portfolio[algo.symbol].quantity += event.fill_quantity
                algo.portfolio.cash = exact_decimal_sum((algo.portfolio.cash,
                    -exact_decimal_multiply(Decimal(event.fill_quantity), event.fill_price), -event.order_fee.value.amount))
                algo.on_order_event(event)

    def test_complete_actual_transcript_and_all_valuation_rows_export_losslessly(self):
        algo = self.initialize()
        self.walk(algo)
        algo.on_end_of_algorithm()
        metadata, envelope = self.output(algo)
        self.assertEqual(metadata["status"], "complete")
        self.assertEqual(envelope["trace"], algo.bridge.protocol_trace())
        self.assertEqual(envelope["trace"]["count"], 752)
        self.assertEqual([row[0] for row in metadata["valuation_rows"]], list(range(372)))
        self.assertTrue(all(row[1] == "50" for row in metadata["valuation_rows"]))
        self.assertEqual(metadata["terminal"]["native_nav"], metadata["terminal"]["native_cash"])
        self.assertTrue(all(len(row.encode("ascii")) <= 200 for row in algo.log_messages))
        self.assertLess(sum(len(row.encode("ascii")) + 1 for row in algo.log_messages), 100000)
        self.assertFalse(metadata["observations"]["native_binding_verified"])
        self.assertIsNone(metadata["observations"]["pythonnet_version"])
        self.assertIn("no empirical", algo.debug_messages[-1])
        # Matching invented metadata cannot bypass the trace's q/c arithmetic.
        for change in ("nav", "mark", "missing", "promote", "terminal"):
            bad = deepcopy(metadata)
            if change == "nav": bad["valuation_rows"][2][2] = "100001"
            if change == "mark": bad["valuation_rows"][2][1] = "51"
            if change == "missing": bad["valuation_rows"].pop()
            if change == "promote": bad["observations"]["native_binding_verified"] = True
            if change == "terminal": bad["terminal"]["native_cash"] = "1"
            with self.subTest(change=change), self.assertRaises(ValueError):
                observations.validate_native_metadata(bad, envelope["trace"])

    def test_transient_mark_and_nav_drift_refuse_before_bridge_frame_commit(self):
        for field in ("price", "nav_override"):
            algo = self.initialize()
            self.frame(algo, 0)
            target = algo._gdr_security if field == "price" else algo.portfolio
            prior = getattr(target, field, None)
            setattr(target, field, Decimal(51) if field == "price" else Decimal(100001))
            before = algo.bridge.engine.snapshot(), algo.bridge.protocol_trace(), tuple(algo._gdr_valuation_rows)
            with self.subTest(field=field), self.assertRaisesRegex(BridgeError, "native.*mismatch"):
                self.frame(algo, 1)
            self.assertEqual((algo.bridge.engine.snapshot(), algo.bridge.protocol_trace(), tuple(algo._gdr_valuation_rows)), before)
            metadata, envelope = self.output(algo)
            self.assertEqual(metadata["status"], "failed")
            self.assertEqual(metadata["diagnostics"]["stage"], "on_data")
            failed = metadata["diagnostics"]["failed_account_observation"]
            self.assertEqual(failed["raw_mark" if field == "price" else "whole_account_nav"], "51" if field == "price" else "100001")
            self.assertEqual(len(metadata["valuation_rows"]), 1)
            self.assertEqual(envelope["trace"], before[1])
            self.assertFalse(algo.debug_messages)
            if prior is None: delattr(target, field)
            else: setattr(target, field, prior)
            self.frame(algo, 1)
            self.assertEqual(len(algo._gdr_valuation_rows), 2)

    def test_source_replays_original_snapshot_not_mutable_submission_object(self):
        algo = self.initialize()
        original = algo.limit_order
        def mutating_submission(*args, **kwargs):
            ticket = original(*args, **kwargs)
            order = algo.native_orders[-1]
            event = OrderEvent(order, algo.utc_time, OrderFee(CashAmount(0, "QCC")))
            algo.on_order_event(event)  # exact duplicate is harmless
            event.status, event.symbol, event.order_id, event.id = "filled", "OTHER", 999, 99
            event.fill_quantity, event.fill_price = 777, 123
            return ticket
        algo.limit_order = mutating_submission
        for index in range(372):
            self.frame(algo, index)
            if algo.native_orders:
                break
        acknowledgements = [row["payload"] for row in algo.bridge.protocol_trace()["records"] if row["kind"] == "acknowledgement"]
        self.assertEqual(len(acknowledgements), 1)
        self.assertEqual(acknowledgements[0]["status"], "submitted")
        self.assertEqual(acknowledgements[0]["native_id"], 1)
        self.assertFalse(algo.early_events.snapshots)

    def test_failure_diagnostics_keep_pending_ids_partial_trace_and_original_exception(self):
        algo = self.initialize()
        for index in range(372):
            self.frame(algo, index)
            if algo.bridge._pending:
                break
        before = algo.bridge.protocol_trace()
        sentinel = RuntimeError("unbounded-secret-is-not-exported")
        with patch.object(algo.bridge, "issue_fill", side_effect=sentinel):
            with self.assertRaises(RuntimeError) as caught:
                algo.fill_model.limit_fill(None, algo.native_orders[0])
        self.assertIs(caught.exception, sentinel)
        metadata, envelope = self.output(algo)
        self.assertEqual(metadata["status"], "failed")
        self.assertEqual(metadata["diagnostics"]["stage"], "fill_model")
        self.assertEqual(metadata["diagnostics"]["pending_orders"], sorted(algo.bridge._pending))
        self.assertEqual(envelope["trace"], before)
        self.assertNotIn("unbounded-secret", canonical_json(metadata))
        self.assertFalse(algo.debug_messages)

    def test_missing_context_never_gets_expected_hashes_or_completion(self):
        algo = self.source.GuidanceRevisionDriftAlgorithm()
        with patch.object(self.source, "_read_regular_file", return_value=fixture_stream()), self.assertRaises(ValueError):
            algo.initialize()
        self.assertEqual(algo.log_messages, ["GDR-NATIVE-REFUSED stage=initialize context_or_trace_unavailable"])
        self.assertFalse(algo.debug_messages)


if __name__ == "__main__":
    unittest.main()
