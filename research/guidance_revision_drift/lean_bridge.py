"""Strict synthetic order/callback bridge, independent of the LEAN runtime.

The deterministic engine is a shadow ledger. Native fills must acknowledge
its exact receipts before the next frame; a callback mismatch stops the run.
This is an order-based integration candidate, not a real-data adapter.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
import json

from data.financial_primitives import exact_decimal_sum, to_decimal
from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.assessment import assess_candidate
from research.guidance_revision_drift.fixtures import example_corpus, fixture_instant, fixture_projection
from research.guidance_revision_drift.simulation import Fill, Minute, Quote, Session, Simulation
from research.guidance_revision_drift.timing import NY


class BridgeError(ValueError):
    """Native callback order or economics differ from the pinned fixture."""


MAX_TRACE_RECORDS = 1024
MAX_TRACE_RECORD_BYTES = 4096


def fixture_frames() -> tuple[dict, ...]:
    frames = []
    for session in example_corpus().schedule.sessions:
        for phase, at in (("decision", fixture_instant(session.session_date, 10)),
                          ("minute", fixture_instant(session.session_date, 10, 1)),
                          ("cancel", fixture_instant(session.session_date, 10, 5)),
                          ("close", session.close_utc)):
            frames.append({"index": len(frames), "phase": phase, "at": at.isoformat(),
                           "schema": "gdr.lean.synthetic-frame.v1", "price": "50"})
    return tuple(frames)


def fixture_stream() -> bytes:
    return ("\n".join(canonical_json(frame) for frame in fixture_frames()) + "\n").encode("utf-8")


class SyntheticOrderBridge:
    """Single invented security. No alternate symbol, dates, prices or route.

    Each step returns newly created deterministic orders and cancellation
    requests. Native order IDs are bound once by the caller. Fill issuance and
    acknowledgement are separate, so duplicate model calls cannot double fill.
    Native rejections, unacknowledged fills/cancels, or amendments are visible
    failures, not silently repaired using a hypothetical portfolio.
    """

    def __init__(self, mode: str = "base"):
        self.corpus = example_corpus()
        self.sessions = tuple(Session(s.session_date, s.open_utc, s.close_utc)
                              for s in self.corpus.schedule.sessions)
        self.engine = Simulation(self.sessions, mode=mode)
        self._frames = fixture_frames()
        self._index = -1
        self._bindings: dict[str, int] = {}
        self._pending: dict[str, Fill] = {}
        self._issued: set[str] = set()
        self._cancels: set[str] = set()
        self._receipts: dict[tuple[int, int], tuple] = {}
        self._submitted: dict[str, tuple] = {}
        self._submission_acks: set[str] = set()
        self._cancel_pending_acks: set[str] = set()
        self._last_event_ids: dict[int, int] = {}
        self._acknowledged = 0
        self._account_checkpoints = 0
        self._trace_genesis = canonical_json({"schema": "gdr.lean.protocol-genesis.v1",
            "mode": mode, "fixture_sha256": hash_bytes(fixture_stream()),
            "native_runtime_verified": False}).encode("utf-8")
        self._trace_head = hash_bytes(self._trace_genesis)
        self._trace_records: list[bytes] = []

    def _prepare_trace(self, kind: str, payload: dict) -> bytes:
        if len(self._trace_records) >= MAX_TRACE_RECORDS:
            raise BridgeError("native protocol trace capacity exhausted")
        raw = canonical_json({"sequence": len(self._trace_records),
            "previous_sha256": self._trace_head, "kind": kind,
            "payload": fixture_projection(payload)}).encode("utf-8")
        if len(raw) > MAX_TRACE_RECORD_BYTES:
            raise BridgeError("native protocol trace record exceeds bound")
        return raw

    def _publish_trace(self, raw: bytes) -> None:
        self._trace_records.append(raw)
        self._trace_head = hash_bytes(raw)

    def protocol_trace(self) -> dict:
        """Detached bounded protocol evidence, not a native execution receipt.

        Records hash their exact canonical bytes and link to their predecessor;
        genesis binds the fixed fixture and execution mode. This in-memory
        transcript has no durable/external trust root or authorization meaning.
        """
        return {"schema": "gdr.lean.protocol-trace.v1",
                "genesis": json.loads(self._trace_genesis),
                "genesis_sha256": hash_bytes(self._trace_genesis),
                "records": [json.loads(raw) for raw in self._trace_records],
                "count": len(self._trace_records), "head_sha256": self._trace_head,
                "native_runtime_verified": False, "cloud_completed": False}

    @property
    def current_at(self) -> datetime:
        if self._index < 0:
            raise BridgeError("no callback frame")
        return datetime.fromisoformat(self._frames[self._index]["at"])

    def step(self, frame: dict, *, native_quantity: Decimal | None = None,
             native_cash: Decimal | None = None) -> dict:
        if self._pending or self._cancels:
            raise BridgeError("prior native fill/cancel acknowledgement missing")
        next_index = self._index + 1
        if (type(frame) is not dict or type(frame.get("index")) is not int
                or next_index >= len(self._frames) or frame != self._frames[next_index]):
            raise BridgeError("missing, duplicated, reordered or modified synthetic frame")
        draft = deepcopy(self)
        if native_quantity is not None or native_cash is not None:
            draft._check_account(frame, native_quantity, native_cash)
        result = draft._step(frame)
        draft._publish_trace(draft._prepare_trace("frame", frame))
        self.__dict__ = draft.__dict__
        return result

    def _check_account(self, frame: dict, quantity: Decimal, cash: Decimal) -> None:
        """Compare an acknowledged single-security immediate-cash envelope.

        This is not native settled buying power: outstanding shadow sale
        receivables are already cash in the immediate-settlement native model.
        Checks run on step's draft before any new shadow fill is booked, and
        only after the prior frame's fill/cancel acknowledgements are complete.
        The no-observation path remains available for offline bridge diagnostics.
        """
        if (type(quantity) is not Decimal or type(cash) is not Decimal
                or not quantity.is_finite() or not cash.is_finite()
                or quantity < 0 or cash < 0
                or quantity != quantity.to_integral_value()):
            raise BridgeError("malformed native account observation")
        snapshot = self.engine.snapshot()
        if any(position["issuer"] != "SYN-ISSUER-A" for position in snapshot["positions"]):
            raise BridgeError("native account checkpoint supports only the fixed source identity")
        expected_quantity = sum(position["quantity"] for position in snapshot["positions"])
        expected_cash = exact_decimal_sum((to_decimal(snapshot["settled_cash"]),
            *(to_decimal(item["amount"]) for item in snapshot["receivables"])))
        if quantity != expected_quantity:
            raise BridgeError("native/shadow inventory mismatch before frame")
        if cash != expected_cash:
            raise BridgeError("native/shadow cash mismatch before frame")
        raw = self._prepare_trace("account_checkpoint", {"before_frame_index": frame["index"],
            "at": frame["at"], "quantity": quantity, "immediate_cash": cash,
            "shadow_settled_cash": snapshot["settled_cash"],
            "shadow_receivables": snapshot["receivables"],
            "settlement_parity_verified": False})
        self._publish_trace(raw)
        self._account_checkpoints += 1

    def _step(self, frame: dict) -> dict:
        self._index = frame["index"]
        at = self.current_at
        day = at.astimezone(NY).date()
        session_index = next(i for i, s in enumerate(self.sessions) if s.day == day)
        cancel = []
        if frame["phase"] == "decision":
            self.engine.execute_due_exits(at, {"SYN-ISSUER-A": Decimal("25000000")})
            if day == date(2025, 4, 4):
                assessment = assess_candidate(book=self.corpus.archive.book, disclosure_id="SYN-RAISE",
                    as_of=at, schedule=self.corpus.schedule, permanent_security_id="SYN-SEC-A",
                    references=self.corpus.references, bars=self.corpus.bars)
                if assessment.eligible_session != day:
                    raise BridgeError("fixture assessment did not qualify")
                self.engine.submit_entry("SYN-RAISE", "SYN-ISSUER-A", assessment.sector,
                    at, Quote(at, Decimal("49.99"), Decimal("50")), assessment.adv20)
        elif frame["phase"] == "minute":
            settlement = self.sessions[min(session_index + 1, len(self.sessions) - 1)].day
            for fill in self.engine.process_minute(Minute("SYN-ISSUER-A", at, Decimal("49.99"),
                    Decimal("50"), 10000, Decimal("25000000"), settlement)):
                self._pending[fill.order_id] = fill
        elif frame["phase"] == "cancel":
            for order in self.engine.cancel_entry_remainders(at):
                self._cancels.add(order.order_id)
                cancel.append(order.order_id)
        else:
            self.engine.close_session(day, {p.issuer: Decimal("50") for p in self.engine.positions})
        submit = []
        for order in self.engine.orders:
            signature = (order.side, order.quantity, order.limit)
            if order.order_id not in self._submitted:
                self._submitted[order.order_id] = signature
                submit.append(order)
            elif self._submitted[order.order_id] != signature:
                raise BridgeError("native order amendment needs separately validated bridge support")
        return {"submit": tuple(submit), "cancel": tuple(cancel)}

    def bind(self, order_id: str, native_id: int) -> None:
        if (order_id not in self._submitted or order_id in self._bindings or type(native_id) is not int
                or native_id <= 0 or native_id in self._bindings.values()):
            raise BridgeError("invalid or duplicate native order binding")
        raw = self._prepare_trace("binding", {"order_id": order_id, "native_id": native_id,
            "at": self.current_at, "side_quantity_limit": self._submitted[order_id]})
        self._bindings[order_id] = native_id
        self._publish_trace(raw)

    def issue_fill(self, native_id: int, at: datetime) -> Fill | None:
        if (type(native_id) is not int or native_id <= 0 or type(at) is not datetime
                or at.tzinfo is None or at.utcoffset() != timezone.utc.utcoffset(at)):
            raise BridgeError("malformed native fill request")
        order_id = next((key for key, value in self._bindings.items() if value == native_id), None)
        if order_id is None:
            raise BridgeError("unknown native order")
        fill = self._pending.get(order_id)
        if fill is None or order_id in self._issued:
            return None
        if at != fill.at:
            raise BridgeError("native fill processing shifted outside its exact minute")
        raw = self._prepare_trace("fill_issue", {"native_id": native_id,
            "order_id": fill.order_id, "at": fill.at, "side": fill.side,
            "quantity": fill.quantity, "price": fill.price, "fee": fill.fee,
            "settlement_session": fill.settlement_session})
        self._issued.add(order_id)
        self._publish_trace(raw)
        return fill

    def order_event(self, *, native_id: int, event_id: int, status: str, at: datetime,
                    quantity: int, price: Decimal, fee: Decimal) -> None:
        if (type(native_id) is not int or type(event_id) is not int or event_id < 0
                or type(quantity) is not int or type(price) is not Decimal or type(fee) is not Decimal
                or not price.is_finite() or not fee.is_finite() or type(at) is not datetime or at.tzinfo is None
                or at.utcoffset() != timezone.utc.utcoffset(at)):
            raise BridgeError("malformed native receipt")
        key = (native_id, event_id)
        receipt = (status, at, quantity, price, fee)
        if key in self._receipts:
            if self._receipts[key] != receipt:
                raise BridgeError("conflicting native receipt identity")
            return
        order_id = next((key for key, value in self._bindings.items() if value == native_id), None)
        if order_id is None:
            raise BridgeError("receipt for unknown native order")
        if event_id <= self._last_event_ids.get(native_id, -1):
            raise BridgeError("native receipt event identity is out of order")
        if at != self.current_at:
            raise BridgeError("native receipt clock differs from current frame")
        raw = self._prepare_trace("acknowledgement", {"native_id": native_id,
            "event_id": event_id, "order_id": order_id, "status": status,
            "at": at, "quantity": quantity, "price": price, "fee": fee})
        if status == "submitted":
            if quantity != 0 or price != 0 or fee != 0 or order_id in self._submission_acks:
                raise BridgeError("invalid repeated or economic submission")
            self._submission_acks.add(order_id)
        elif status == "cancel_pending":
            if (order_id not in self._cancels or order_id not in self._submission_acks
                    or order_id in self._cancel_pending_acks
                    or quantity != 0 or price != 0 or fee != 0):
                raise BridgeError("unsolicited, repeated or economic cancel-pending receipt")
            # This acknowledges the request only. The shadow still holds all
            # reservations and may not advance until terminal cancellation.
            self._cancel_pending_acks.add(order_id)
        elif status == "canceled":
            if (order_id not in self._cancels or order_id not in self._cancel_pending_acks
                    or quantity != 0 or price != 0 or fee != 0):
                raise BridgeError("unsolicited or economic cancellation receipt")
            self.engine.acknowledge_cancel(order_id, at)
            self._cancels.remove(order_id)
            self._cancel_pending_acks.remove(order_id)
        elif status in {"filled", "partially_filled"}:
            fill = self._pending.get(order_id)
            if fill is None or order_id not in self._issued or order_id not in self._submission_acks:
                raise BridgeError("unsolicited native fill")
            signed = fill.quantity if fill.side == "buy" else -fill.quantity
            expected_status = "filled" if next(o for o in self.engine.orders if o.order_id == order_id).remaining == 0 else "partially_filled"
            if (status, at, quantity, price, fee) != (expected_status, fill.at, signed, fill.price, fill.fee):
                raise BridgeError("native fill differs from deterministic receipt")
            del self._pending[order_id]
            self._issued.remove(order_id)
            self._acknowledged += 1
        else:
            raise BridgeError("native rejected/unsupported order status: " + str(status))
        self._receipts[key] = receipt
        self._last_event_ids[native_id] = event_id
        self._publish_trace(raw)

    def finish(self) -> dict:
        if self._index != len(self._frames) - 1 or self._pending or self._cancels:
            raise BridgeError("incomplete callback/calendar sequence")
        snapshot = self.engine.snapshot()
        if snapshot["completion_blocked"]:
            raise BridgeError("shadow strategy remains incomplete")
        if (len(self._bindings) != len(self._submitted)
                or len(self._submission_acks) != len(self._bindings)
                or self._acknowledged != len(snapshot["fills"])):
            raise BridgeError("native/shadow order lineage incomplete")
        return {"schema": "gdr.lean.callback-contract.v1", "strategy": snapshot,
                "acknowledged_fills": self._acknowledged, "native_orders": len(self._bindings),
                "native_account_checkpoints": self._account_checkpoints,
                "settlement_parity_verified": False,
                "fixture_sha256": hash_bytes(fixture_stream()), "runtime_verified": False,
                "cloud_completed": False, "empirical_evidence": False,
                "protocol_trace_count": len(self._trace_records),
                "protocol_trace_head_sha256": self._trace_head,
                "protocol_trace_genesis_sha256": hash_bytes(self._trace_genesis)}
