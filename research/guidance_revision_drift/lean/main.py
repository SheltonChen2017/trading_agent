"""Order-based LEAN synthetic integration candidate; no real symbol/data route.

Requires the exact locally exported gdr-synthetic.jsonl beside this file.
Python compilation and shim tests do NOT verify LEAN Python/.NET bindings.
See README before any separately authorized engine evaluation.
"""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from AlgorithmImports import (
    QCAlgorithm, PythonData, SubscriptionDataSource, SubscriptionTransportMedium,
    Resolution, TimeZones, FillModel, OrderEvent, OrderFee, CashAmount, OrderStatus,
    ConstantFeeModel, ImmediateSettlementModel,
)
from data.financial_primitives import decimal_text, to_decimal
from data.hashing import canonical_json
from research.guidance_revision_drift.contracts import _decode, _read_regular_file
from research.guidance_revision_drift.lean_bridge import (
    BridgeError, SyntheticOrderBridge, fixture_frames, fixture_stream,
)
from research.guidance_revision_drift.native_observation import (
    DeferredReceipts, ObservationError, ReceiptSnapshot, RuntimeContext,
    failure_diagnostics, observe_runtime, validate_native_metadata, valuation_checkpoint,
)
from research.guidance_revision_drift.trace_transport import export_trace_fragments, trace_fragment_anchor


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
        if type(line) is not str:
            raise BridgeError("synthetic reader requires a text record")
        frame = _decode(line.encode("utf-8"))
        frames = fixture_frames()
        index = frame.get("index")
        if type(index) is not int or not 0 <= index < len(frames) or frame != frames[index]:
            raise BridgeError("nonfixture or modified stream record")
        instant = datetime.fromisoformat(frame["at"])
        # This is one multiday file. LEAN retains the source-creation day for
        # every Reader call; filtering against it would discard later sessions.
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
        try:
            return self._observed_fill(order)
        except Exception as exc:
            self.algorithm._emit_failure("fill_model", exc)
            raise

    def _observed_fill(self, order):
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
        try:
            self._initialize()
        except Exception as exc:
            self._emit_failure("initialize", exc)
            raise

    def _initialize(self):
        if self.live_mode:
            raise BridgeError("no live, paper or broker route")
        if _read_regular_file(DATA_PATH, 256 * 1024) != fixture_stream():
            raise BridgeError("exact synthetic sidecar required")
        self._gdr_context = RuntimeContext.capture(getattr(self, "_gdr_runtime_context", None))
        self._gdr_valuation_rows = []
        self._gdr_observations_bytes = None
        self.bridge = SyntheticOrderBridge("base")
        self.tickets = {}
        self.early_events = DeferredReceipts()
        self.submitting = False
        self.set_time_zone(TimeZones.UTC)
        self.set_start_date(2025, 1, 2)
        self.set_end_date(2025, 5, 15)
        self.set_cash(100000)
        security = self.add_data(GuidanceSyntheticData, "SYN-GDR", Resolution.MINUTE,
                                 TimeZones.UTC, False, 1)
        self.symbol = security.symbol
        self._gdr_security = security
        self.set_benchmark(self.symbol)
        security.set_fill_model(GuidanceReceiptFillModel(self))
        # Fees and spread/slippage are already explicit in each emitted receipt.
        security.set_fee_model(ConstantFeeModel(0))
        # Native cash is an immediate-settlement envelope. The shadow ledger
        # alone authorizes spending after its explicit dated settlement. Do not
        # interpret native settled cash as a validated equity cash-account model.
        security.set_settlement_model(ImmediateSettlementModel())
        self._gdr_observations_bytes = canonical_json(observe_runtime(self, security)).encode()

    def on_data(self, data):
        try:
            self._on_data(data)
        except Exception as exc:
            self._emit_failure("on_data", exc)
            raise

    def _on_data(self, data):
        if not data.contains_key(self.symbol):
            return
        index_value = to_decimal(data[self.symbol]["frame_index"])
        if index_value != index_value.to_integral_value() or not 0 <= index_value < len(fixture_frames()):
            raise BridgeError("invalid frame index")
        frame = fixture_frames()[int(index_value)]
        if utc(self.utc_time) != datetime.fromisoformat(frame["at"]):
            raise BridgeError("engine callback clock differs from fixture")
        # Configuration is read back from the configured objects. Missing CLR
        # observations remain unverified; a changed/mismatched label refuses.
        try:
            observations = canonical_json(observe_runtime(self, self._gdr_security)).encode()
            if observations != self._gdr_observations_bytes:
                raise ObservationError("native runtime configuration observation changed")
            checkpoint = valuation_checkpoint(frame["index"],
                quantity=self.portfolio[self.symbol].quantity, cash=self.portfolio.cash,
                price=self._gdr_security.price, nav=self.portfolio.total_portfolio_value)
        except ObservationError as exc:
            raise BridgeError(str(exc)) from exc
        # Prior native receipts must be fully acknowledged before this boundary.
        # Immediate native cash includes the shadow's unsettled receivables;
        # reservations and spendable settled cash remain shadow-only authority.
        actions = self.bridge.step(frame,
            native_quantity=to_decimal(self.portfolio[self.symbol].quantity),
            native_cash=to_decimal(self.portfolio.cash))
        self._gdr_valuation_rows.append(checkpoint)
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
            while self.early_events.snapshots:
                self._acknowledge_snapshot(self.early_events.snapshots[0])
                self.early_events.discard_first()
        for order_id in actions["cancel"]:
            response = self.tickets[order_id].cancel("synthetic remainder expiry")
            if not response.is_success:
                raise BridgeError("native cancellation request rejected")

    def on_order_event(self, event):
        try:
            self._on_order_event(event)
        except Exception as exc:
            self._emit_failure("on_order_event", exc)
            raise

    def _on_order_event(self, event):
        statuses = {OrderStatus.SUBMITTED: "submitted", OrderStatus.FILLED: "filled",
                    OrderStatus.CANCEL_PENDING: "cancel_pending",
                    OrderStatus.PARTIALLY_FILLED: "partially_filled", OrderStatus.CANCELED: "canceled"}
        try:
            snapshot = ReceiptSnapshot.capture(event, expected_symbol=self.symbol, statuses=statuses)
            if self.submitting:
                self.early_events.append(snapshot)
                return
        except ObservationError as exc:
            raise BridgeError(str(exc)) from exc
        self._acknowledge_snapshot(snapshot)

    def _acknowledge_snapshot(self, snapshot):
        row = snapshot.to_dict()
        self.bridge.order_event(native_id=row["native_id"], event_id=row["event_id"],
            status=row["status"], at=datetime.fromisoformat(row["at"]),
            quantity=row["quantity"], price=to_decimal(row["price"]), fee=to_decimal(row["fee"]))

    def on_end_of_algorithm(self):
        try:
            self._on_end_of_algorithm()
        except Exception as exc:
            self._emit_failure("on_end_of_algorithm", exc)
            raise

    def _on_end_of_algorithm(self):
        report = self.bridge.finish()
        if report["native_account_checkpoints"] != len(fixture_frames()):
            raise BridgeError("incomplete native account checkpoint sequence")
        if to_decimal(self.portfolio[self.symbol].quantity) != 0:
            raise BridgeError("native inventory remains after shadow liquidation")
        expected = to_decimal(report["strategy"]["settled_cash"])
        if to_decimal(self.portfolio.cash) != expected:
            raise BridgeError("terminal native/shadow cash mismatch")
        if len(self._gdr_valuation_rows) != len(fixture_frames()) or self.early_events.snapshots:
            raise BridgeError("incomplete native valuation/deferred receipt sequence")
        try:
            terminal = valuation_checkpoint(len(fixture_frames()) - 1,
                quantity=self.portfolio[self.symbol].quantity, cash=self.portfolio.cash,
                price=self._gdr_security.price, nav=self.portfolio.total_portfolio_value)
            if canonical_json(observe_runtime(self, self._gdr_security)).encode() != self._gdr_observations_bytes:
                raise ObservationError("native runtime configuration observation changed")
        except ObservationError as exc:
            raise BridgeError(str(exc)) from exc
        self._emit_trace({"status": "complete", "terminal": {
            "native_quantity": "0", "native_cash": decimal_text(self.portfolio.cash),
            "native_price": terminal[1], "native_nav": terminal[2]},
            "valuation_schema": "gdr-native-price-nav-v1", "valuation_rows": [list(row) for row in self._gdr_valuation_rows],
            "observations": _decode(self._gdr_observations_bytes)})
        self.debug("Synthetic native callback reconciliation finished; "
                   f"trace_count={report['protocol_trace_count']} "
                   f"trace_head_sha256={report['protocol_trace_head_sha256']}; "
                   "no empirical or cloud-parity acceptance.")

    def _emit_trace(self, metadata):
        trace = self.bridge.protocol_trace()
        metadata = validate_native_metadata(metadata, trace)
        fragments = export_trace_fragments(trace,
            runtime_context=self._gdr_context.to_dict(), metadata=metadata)
        for fragment in fragments:
            self.log(fragment.decode("ascii"))
        # This anchor describes the emitted bytes only. Retrieval/authentication
        # and independent replay remain separate evidence requirements.
        self._gdr_last_export_anchor = trace_fragment_anchor(fragments)

    def _emit_failure(self, stage, error):
        # Diagnostic errors must never replace the original runtime exception.
        # Before valid context/bridge initialization, only a refusal marker can
        # be emitted; missing identities are never filled with expected hashes.
        if getattr(self, "_gdr_last_failure", None) is error:
            return
        self._gdr_last_failure = error
        try:
            bridge = getattr(self, "bridge", None)
            deferred = getattr(self, "early_events", None)
            if bridge is None or not hasattr(self, "_gdr_context"):
                self.log("GDR-NATIVE-REFUSED stage=" + stage + " context_or_trace_unavailable")
                return
            observations = getattr(self, "_gdr_observations_bytes", None)
            self._emit_trace({"status": "failed", "diagnostics": failure_diagnostics(stage, error, bridge, deferred, algorithm=self),
                "observations": _decode(observations) if observations is not None else None,
                "valuation_schema": "gdr-native-price-nav-v1",
                "valuation_rows": [list(row) for row in getattr(self, "_gdr_valuation_rows", [])]})
        except Exception:
            try:
                self.log("GDR-NATIVE-REFUSED stage=" + stage + " diagnostic_export_unavailable")
            except Exception:
                pass
