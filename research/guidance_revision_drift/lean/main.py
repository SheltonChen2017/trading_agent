"""Order-based LEAN synthetic integration candidate; no real symbol/data route.

Requires the exact locally exported gdr-synthetic.jsonl beside this file.
Python compilation and shim tests do NOT verify LEAN Python/.NET bindings.
See README before any separately authorized engine evaluation.
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from AlgorithmImports import (
    QCAlgorithm, PythonData, SubscriptionDataSource, SubscriptionTransportMedium,
    Resolution, TimeZones, FillModel, OrderEvent, OrderFee, CashAmount, OrderStatus,
    ConstantFeeModel, ImmediateSettlementModel,
)
from data.financial_primitives import to_decimal
from research.guidance_revision_drift.contracts import _read_regular_file
from research.guidance_revision_drift.lean_bridge import (
    BridgeError, SyntheticOrderBridge, fixture_frames, fixture_stream,
)


DATA_PATH = Path(__file__).resolve().with_name("gdr-synthetic.jsonl")


def utc(value):
    # LEAN exposes UTC DateTime without Python tzinfo on some bindings.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class GuidanceSyntheticData(PythonData):
    def get_source(self, config, day, is_live_mode):
        if is_live_mode:
            raise BridgeError("live data forbidden")
        return SubscriptionDataSource(str(DATA_PATH), SubscriptionTransportMedium.LOCAL_FILE)

    def reader(self, config, line, day, is_live_mode):
        if is_live_mode:
            raise BridgeError("live data forbidden")
        frame = json.loads(line)
        frames = fixture_frames()
        index = frame.get("index")
        if type(index) is not int or not 0 <= index < len(frames) or frame != frames[index]:
            raise BridgeError("nonfixture or modified stream record")
        instant = datetime.fromisoformat(frame["at"])
        if instant.date() != day.date():
            return None
        point = GuidanceSyntheticData()
        point.symbol = config.symbol
        point.time = instant.replace(tzinfo=None)
        point.end_time = point.time
        point.value = Decimal("50")
        point["frame_index"] = index
        return point


class GuidanceReceiptFillModel(FillModel):
    def __init__(self, algorithm):
        self.algorithm = algorithm

    def _fill(self, order):
        at = utc(self.algorithm.utc_time)
        event = OrderEvent(order, self.algorithm.utc_time, OrderFee(CashAmount(0, "USD")))
        if self.algorithm.submitting:
            return event
        fill = self.algorithm.bridge.issue_fill(order.id, at)
        if fill is None:
            return event
        event.fill_quantity = fill.quantity if fill.side == "buy" else -fill.quantity
        event.fill_price = fill.price
        event.order_fee = OrderFee(CashAmount(fill.fee, "USD"))
        shadow = next(o for o in self.algorithm.bridge.engine.orders if o.order_id == fill.order_id)
        event.status = OrderStatus.FILLED if shadow.remaining == 0 else OrderStatus.PARTIALLY_FILLED
        return event

    def limit_fill(self, asset, order):
        return self._fill(order)

    def market_fill(self, asset, order):
        return self._fill(order)


class GuidanceRevisionDriftAlgorithm(QCAlgorithm):
    def initialize(self):
        if self.live_mode:
            raise BridgeError("no live, paper or broker route")
        if _read_regular_file(DATA_PATH, 256 * 1024) != fixture_stream():
            raise BridgeError("exact synthetic sidecar required")
        self.bridge = SyntheticOrderBridge("base")
        self.tickets = {}
        self.early_events = []
        self.submitting = False
        self.set_time_zone(TimeZones.UTC)
        self.set_start_date(2025, 1, 2)
        self.set_end_date(2025, 5, 15)
        self.set_cash(100000)
        security = self.add_data(GuidanceSyntheticData, "SYN-GDR", Resolution.MINUTE,
                                 TimeZones.UTC, False, 1)
        self.symbol = security.symbol
        self.set_benchmark(self.symbol)
        security.set_fill_model(GuidanceReceiptFillModel(self))
        # Fees and spread/slippage are already explicit in each emitted receipt.
        security.set_fee_model(ConstantFeeModel(0))
        # Native cash is an immediate-settlement envelope. The shadow ledger
        # alone authorizes spending after its explicit dated settlement. Do not
        # interpret native settled cash as a validated equity cash-account model.
        security.set_settlement_model(ImmediateSettlementModel())

    def on_data(self, data):
        if not data.contains_key(self.symbol):
            return
        index_value = to_decimal(data[self.symbol]["frame_index"])
        if index_value != index_value.to_integral_value() or not 0 <= index_value < len(fixture_frames()):
            raise BridgeError("invalid frame index")
        frame = fixture_frames()[int(index_value)]
        if utc(self.utc_time) != datetime.fromisoformat(frame["at"]):
            raise BridgeError("engine callback clock differs from fixture")
        actions = self.bridge.step(frame)
        for order in actions["submit"]:
            self.submitting = True
            try:
                if order.side == "buy":
                    ticket = self.limit_order(self.symbol, order.quantity, order.limit, tag=order.order_id)
                else:
                    ticket = self.market_order(self.symbol, -order.quantity, True, order.order_id)
                self.bridge.bind(order.order_id, ticket.order_id)
                self.tickets[order.order_id] = ticket
            finally:
                self.submitting = False
            for event in self.early_events:
                self.on_order_event(event)
            self.early_events.clear()
        for order_id in actions["cancel"]:
            response = self.tickets[order_id].cancel("synthetic remainder expiry")
            if not response.is_success:
                raise BridgeError("native cancellation request rejected")

    def on_order_event(self, event):
        if self.submitting:
            self.early_events.append(event)
            return
        statuses = {OrderStatus.SUBMITTED: "submitted", OrderStatus.FILLED: "filled",
                    OrderStatus.PARTIALLY_FILLED: "partially_filled", OrderStatus.CANCELED: "canceled"}
        quantity = to_decimal(event.fill_quantity)
        if quantity != quantity.to_integral_value() or event.order_fee.value.currency != "USD":
            raise BridgeError("non-whole-share or non-USD native receipt")
        self.bridge.order_event(native_id=event.order_id, event_id=event.id,
            status=statuses.get(event.status, "unsupported"), at=utc(event.utc_time),
            quantity=int(quantity), price=to_decimal(event.fill_price), fee=to_decimal(event.order_fee.value.amount))

    def on_end_of_algorithm(self):
        report = self.bridge.finish()
        if to_decimal(self.portfolio[self.symbol].quantity) != 0:
            raise BridgeError("native inventory remains after shadow liquidation")
        expected = to_decimal(report["strategy"]["settled_cash"])
        if to_decimal(self.portfolio.cash) != expected:
            raise BridgeError("terminal native/shadow cash mismatch")
        self.debug("Synthetic native callback reconciliation finished; no empirical or cloud-parity acceptance.")
