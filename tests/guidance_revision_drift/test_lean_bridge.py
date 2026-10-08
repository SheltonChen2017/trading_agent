"""Local callback contracts only; this test does not import or run LEAN."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import unittest
from unittest.mock import patch

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift import lean_bridge
from research.guidance_revision_drift.lean_bridge import (
    BridgeError, SyntheticOrderBridge, fixture_frames, fixture_stream,
)
from research.guidance_revision_drift.scenario import run_example
from research.guidance_revision_drift.simulation import Simulation


def drive(mode="base", stop_at_fill=False, stop_at_cancel=False, return_bridge=False):
    bridge = SyntheticOrderBridge(mode)
    ids = {}
    events = {}
    for frame in fixture_frames():
        actions = bridge.step(frame)
        for order in actions["submit"]:
            native = len(ids) + 1
            bridge.bind(order.order_id, native)
            ids[order.order_id] = native
            events[native] = 0
            bridge.order_event(native_id=native, event_id=0, status="submitted", at=bridge.current_at,
                               quantity=0, price=Decimal(0), fee=Decimal(0))
        for order_id, native in ids.items():
            fill = bridge.issue_fill(native, bridge.current_at)
            if fill is None:
                continue
            if stop_at_fill:
                return bridge, fill, native
            remaining = next(o.remaining for o in bridge.engine.orders if o.order_id == order_id)
            events[native] += 1
            receipt = dict(native_id=native, event_id=events[native], at=fill.at,
                status="filled" if remaining == 0 else "partially_filled",
                quantity=fill.quantity if fill.side == "buy" else -fill.quantity,
                price=fill.price, fee=fill.fee)
            bridge.order_event(**receipt)
            bridge.order_event(**receipt)  # exact redelivery has no second effect
            if bridge.issue_fill(native, bridge.current_at) is not None:
                raise AssertionError("duplicate model invocation reissued a fill")
        for order_id in actions["cancel"]:
            native = ids[order_id]
            if stop_at_cancel:
                return bridge, native, events[native] + 1
            events[native] += 1
            bridge.order_event(native_id=native, event_id=events[native], status="cancel_pending",
                               at=bridge.current_at, quantity=0, price=Decimal(0), fee=Decimal(0))
            events[native] += 1
            bridge.order_event(native_id=native, event_id=events[native], status="canceled",
                               at=bridge.current_at, quantity=0, price=Decimal(0), fee=Decimal(0))
    report = bridge.finish()
    return bridge if return_bridge else report


class LeanBridgeTests(unittest.TestCase):
    def test_order_based_callbacks_match_strategy_in_both_modes(self):
        for mode in ("base", "stress"):
            with self.subTest(mode=mode):
                report = drive(mode)
                expected = run_example(mode)["strategy"]
                actual = report["strategy"]
                for key in ("settled_cash", "fills", "orders", "positions", "completion_blocked"):
                    self.assertEqual(actual[key], expected[key], key)
                self.assertEqual(len(actual["navs"]), 93)
                self.assertEqual(report["native_orders"], 2)
                self.assertEqual(report["acknowledged_fills"], 2)
                self.assertFalse(report["runtime_verified"])
                self.assertFalse(report["cloud_completed"])

    def test_missing_ack_prevents_next_frame(self):
        bridge, fill, native = drive(stop_at_fill=True)
        with self.assertRaisesRegex(BridgeError, "acknowledgement"):
            bridge.step(fixture_frames()[bridge._index + 1])
        self.assertIsNone(bridge.issue_fill(native, fill.at))

    def test_partial_fill_cancel_ack_and_cumulative_floor_callbacks(self):
        original = Simulation.process_minute
        with patch.object(Simulation, "process_minute",
                          lambda engine, minute: original(engine, replace(minute, volume=1000))):
            report = drive()
        entry = report["strategy"]["orders"][0]
        self.assertEqual(entry["filled_quantity"], 10)
        self.assertEqual(entry["status"], "cancelled")
        self.assertEqual(entry["fees_paid"], "1")
        self.assertEqual(report["strategy"]["reserved_cash"], "0")
        self.assertFalse(report["strategy"]["completion_blocked"])

    def test_wrong_native_economics_conflicts_and_rejection_fail_closed(self):
        bridge, fill, native = drive(stop_at_fill=True)
        receipt = dict(native_id=native, event_id=1, status="filled", at=fill.at,
                       quantity=fill.quantity, price=fill.price, fee=fill.fee)
        for change in ({"fee": Decimal(0)}, {"price": Decimal(50)}, {"quantity": fill.quantity + 1},
                       {"at": fill.at + timedelta(minutes=1)}, {"status": "rejected"}):
            with self.subTest(change=change), self.assertRaises(BridgeError):
                bridge.order_event(**(receipt | change))
        bridge.order_event(**receipt)
        with self.assertRaisesRegex(BridgeError, "conflicting"):
            bridge.order_event(**(receipt | {"quantity": 1}))

    def test_stream_and_sequence_cannot_be_replaced_or_skipped(self):
        self.assertEqual(len(fixture_stream().splitlines()), 372)
        bridge = SyntheticOrderBridge()
        before = bridge.engine.snapshot()
        for frame in (fixture_frames()[1], fixture_frames()[0] | {"price": "51"},
                      fixture_frames()[0] | {"index": False}):
            with self.assertRaises(BridgeError):
                bridge.step(frame)
        self.assertEqual(before, bridge.engine.snapshot())
        bridge.step(fixture_frames()[0])
        with self.assertRaises(BridgeError):
            bridge.step(fixture_frames()[0])
        with self.assertRaises(BridgeError):
            bridge.finish()

    def test_native_fill_processed_at_a_shifted_minute_is_refused_before_issue(self):
        # README contract: native fill evaluation must occur in the exact
        # minute of the shadow receipt. A fill model invoked one minute later
        # (or earlier) must not receive the receipt, and the receipt must stay
        # pending so the correctly timed invocation can still issue it once.
        bridge = SyntheticOrderBridge()
        native = None
        for frame in fixture_frames():
            actions = bridge.step(frame)
            for order in actions["submit"]:
                native = 1
                bridge.bind(order.order_id, native)
            if bridge._pending:
                break
        self.assertIsNotNone(native)
        pending_at = next(iter(bridge._pending.values())).at
        for shift in (timedelta(minutes=1), -timedelta(minutes=1), timedelta(seconds=1)):
            with self.subTest(shift=shift), self.assertRaisesRegex(BridgeError, "shifted"):
                bridge.issue_fill(native, pending_at + shift)
        self.assertEqual(len(bridge._pending), 1)
        fill = bridge.issue_fill(native, pending_at)
        self.assertEqual(fill.at, pending_at)
        self.assertIsNone(bridge.issue_fill(native, pending_at))

    def test_finish_refuses_a_report_while_the_shadow_strategy_is_incomplete(self):
        # After the entry fills, every later minute carries no capacity, so the
        # time exit can never execute: the run ends with an open position and
        # an active sell. finish() must refuse rather than emit a report whose
        # lineage counts happen to reconcile.
        original = Simulation.process_minute

        def starve_exits(engine, minute):
            if engine.positions:
                minute = replace(minute, volume=0)
            return original(engine, minute)

        with patch.object(Simulation, "process_minute", starve_exits):
            with self.assertRaisesRegex(BridgeError, "incomplete"):
                drive()

    def test_unknown_duplicate_binding_and_unrequested_cancel_refuse(self):
        bridge, fill, native = drive(stop_at_fill=True)
        for name, number in ((fill.order_id, native), ("SYN-UNKNOWN", 2), (fill.order_id, True)):
            with self.assertRaises(BridgeError):
                bridge.bind(name, number)
        with self.assertRaises(BridgeError):
            bridge.order_event(native_id=native, event_id=2, status="canceled", at=fill.at,
                               quantity=0, price=Decimal(0), fee=Decimal(0))
        with self.assertRaises(BridgeError):
            bridge.issue_fill(999, fill.at)
        for native_id, instant in ((True, fill.at), (native, None), (native, fill.at.replace(tzinfo=None))):
            with self.subTest(native_id=native_id, instant=instant), self.assertRaises(BridgeError):
                bridge.issue_fill(native_id, instant)

    def test_cancel_pending_keeps_reservations_until_ordered_terminal_ack(self):
        original = Simulation.process_minute
        with patch.object(Simulation, "process_minute",
                          lambda engine, minute: original(engine, replace(minute, volume=1000))):
            bridge, native, event_id = drive(stop_at_cancel=True)
        before = bridge.engine.snapshot()
        self.assertGreater(Decimal(before["reserved_cash"]), 0)
        receipt = dict(native_id=native, event_id=10, status="cancel_pending", at=bridge.current_at,
                       quantity=0, price=Decimal(0), fee=Decimal(0))
        trace = bridge.protocol_trace()
        for change in ({"status": "canceled"}, {"quantity": 1}, {"price": Decimal(1)}, {"fee": Decimal(1)}):
            with self.subTest(change=change), self.assertRaises(BridgeError):
                bridge.order_event(**(receipt | change))
            self.assertEqual(bridge.protocol_trace(), trace)
            self.assertEqual(bridge.engine.snapshot(), before)
        bridge.order_event(**receipt)
        acknowledged_trace = bridge.protocol_trace()
        bridge.order_event(**receipt)
        self.assertEqual(bridge.protocol_trace(), acknowledged_trace)
        self.assertEqual(bridge.engine.snapshot(), before)
        for change in ({"event_id": 11}, {"event_id": 9, "status": "canceled"}):
            with self.subTest(change=change), self.assertRaises(BridgeError):
                bridge.order_event(**(receipt | change))
        terminal = receipt | {"event_id": 11, "status": "canceled"}
        bridge.order_event(**terminal)
        self.assertEqual(bridge.engine.snapshot()["reserved_cash"], "0")
        terminal_trace = bridge.protocol_trace()
        bridge.order_event(**terminal)
        self.assertEqual(bridge.protocol_trace(), terminal_trace)
        with self.assertRaises(BridgeError):
            bridge.order_event(**(receipt | {"event_id": 12}))

    def test_transcript_is_reproducible_hash_linked_and_detached(self):
        bridge = drive(return_bridge=True)
        trace = bridge.protocol_trace()
        self.assertEqual(trace, drive(return_bridge=True).protocol_trace())
        self.assertNotEqual(trace["head_sha256"], drive("stress", return_bridge=True).protocol_trace()["head_sha256"])
        previous = hash_bytes(canonical_json(trace["genesis"]).encode())
        self.assertEqual(previous, trace["genesis_sha256"])
        for sequence, record in enumerate(trace["records"]):
            self.assertEqual(record["sequence"], sequence)
            self.assertEqual(record["previous_sha256"], previous)
            previous = hash_bytes(canonical_json(record).encode())
        self.assertEqual(previous, trace["head_sha256"])
        self.assertEqual(trace["count"], 380)
        self.assertEqual({row["kind"] for row in trace["records"]},
                         {"frame", "binding", "fill_issue", "acknowledgement"})
        self.assertEqual(bridge.finish()["protocol_trace_count"], trace["count"])
        self.assertEqual(bridge.finish()["protocol_trace_head_sha256"], trace["head_sha256"])
        self.assertFalse(trace["native_runtime_verified"])
        self.assertFalse(trace["cloud_completed"])
        trace["records"][0]["payload"]["price"] = "500"
        self.assertNotEqual(trace, bridge.protocol_trace())

    def test_trace_capacity_refuses_frame_binding_issue_and_ack_atomically(self):
        bridge = SyntheticOrderBridge()
        before = bridge.engine.snapshot(), bridge.protocol_trace()
        with patch.object(lean_bridge, "MAX_TRACE_RECORDS", 0), self.assertRaisesRegex(BridgeError, "capacity"):
            bridge.step(fixture_frames()[0])
        self.assertEqual(before, (bridge.engine.snapshot(), bridge.protocol_trace()))
        native = None
        for frame in fixture_frames():
            actions = bridge.step(frame)
            for order in actions["submit"]:
                cap = len(bridge.protocol_trace()["records"])
                with patch.object(lean_bridge, "MAX_TRACE_RECORDS", cap), self.assertRaisesRegex(BridgeError, "capacity"):
                    bridge.bind(order.order_id, 1)
                self.assertEqual(bridge._bindings, {})
                bridge.bind(order.order_id, 1)
                native = 1
                bridge.order_event(native_id=1, event_id=0, status="submitted", at=bridge.current_at,
                                   quantity=0, price=Decimal(0), fee=Decimal(0))
            if bridge._pending:
                break
        before = bridge.engine.snapshot(), bridge.protocol_trace()
        cap = len(before[1]["records"])
        with patch.object(lean_bridge, "MAX_TRACE_RECORDS", cap), self.assertRaisesRegex(BridgeError, "capacity"):
            bridge.issue_fill(native, bridge.current_at)
        self.assertEqual(bridge._issued, set())
        self.assertEqual(before, (bridge.engine.snapshot(), bridge.protocol_trace()))
        fill = bridge.issue_fill(native, bridge.current_at)
        before = bridge.engine.snapshot(), bridge.protocol_trace()
        receipt = dict(native_id=native, event_id=1, status="filled", at=fill.at,
                       quantity=fill.quantity, price=fill.price, fee=fill.fee)
        with patch.object(lean_bridge, "MAX_TRACE_RECORDS", len(before[1]["records"])), self.assertRaisesRegex(BridgeError, "capacity"):
            bridge.order_event(**receipt)
        self.assertEqual(before, (bridge.engine.snapshot(), bridge.protocol_trace()))
        self.assertEqual(len(bridge._pending), 1)
        bridge.order_event(**receipt)

    def test_trace_record_bound_is_fail_closed(self):
        bridge = SyntheticOrderBridge()
        with patch.object(lean_bridge, "MAX_TRACE_RECORD_BYTES", 1), self.assertRaisesRegex(BridgeError, "record exceeds"):
            bridge.step(fixture_frames()[0])
        self.assertEqual(bridge.protocol_trace()["count"], 0)
        self.assertEqual(bridge._index, -1)


if __name__ == "__main__":
    unittest.main()
