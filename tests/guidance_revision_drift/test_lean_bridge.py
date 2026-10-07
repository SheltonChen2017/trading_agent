"""Local callback contracts only; this test does not import or run LEAN."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import unittest
from unittest.mock import patch

from research.guidance_revision_drift.lean_bridge import (
    BridgeError, SyntheticOrderBridge, fixture_frames, fixture_stream,
)
from research.guidance_revision_drift.scenario import run_example
from research.guidance_revision_drift.simulation import Simulation


def drive(mode="base", stop_at_fill=False):
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
            events[native] += 1
            bridge.order_event(native_id=native, event_id=events[native], status="canceled",
                               at=bridge.current_at, quantity=0, price=Decimal(0), fee=Decimal(0))
    return bridge.finish()


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


if __name__ == "__main__":
    unittest.main()
