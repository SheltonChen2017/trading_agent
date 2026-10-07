"""Strict synthetic order/callback bridge, independent of the LEAN runtime.

The deterministic engine is a shadow ledger. Native fills must acknowledge
its exact receipts before the next frame; a callback mismatch stops the run.
This is an order-based integration candidate, not a real-data adapter.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.assessment import assess_candidate
from research.guidance_revision_drift.fixtures import example_corpus, fixture_instant
from research.guidance_revision_drift.simulation import Fill, Minute, Quote, Session, Simulation
from research.guidance_revision_drift.timing import NY


class BridgeError(ValueError):
    """Native callback order or economics differ from the pinned fixture."""


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
        self._acknowledged = 0

    @property
    def current_at(self) -> datetime:
        if self._index < 0:
            raise BridgeError("no callback frame")
        return datetime.fromisoformat(self._frames[self._index]["at"])

    def step(self, frame: dict) -> dict:
        if self._pending or self._cancels:
            raise BridgeError("prior native fill/cancel acknowledgement missing")
        next_index = self._index + 1
        if (type(frame) is not dict or type(frame.get("index")) is not int
                or next_index >= len(self._frames) or frame != self._frames[next_index]):
            raise BridgeError("missing, duplicated, reordered or modified synthetic frame")
        draft = deepcopy(self)
        result = draft._step(frame)
        self.__dict__ = draft.__dict__
        return result

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
        self._bindings[order_id] = native_id

    def issue_fill(self, native_id: int, at: datetime) -> Fill | None:
        order_id = next((key for key, value in self._bindings.items() if value == native_id), None)
        if order_id is None:
            raise BridgeError("unknown native order")
        fill = self._pending.get(order_id)
        if fill is None or order_id in self._issued:
            return None
        if at != fill.at:
            raise BridgeError("native fill processing shifted outside its exact minute")
        self._issued.add(order_id)
        return fill

    def order_event(self, *, native_id: int, event_id: int, status: str, at: datetime,
                    quantity: int, price: Decimal, fee: Decimal) -> None:
        if (type(native_id) is not int or type(event_id) is not int or event_id < 0
                or type(quantity) is not int or type(price) is not Decimal or type(fee) is not Decimal
                or not price.is_finite() or not fee.is_finite() or at.tzinfo is None
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
        if at != self.current_at:
            raise BridgeError("native receipt clock differs from current frame")
        if status == "submitted":
            if quantity != 0 or price != 0 or fee != 0:
                raise BridgeError("submission cannot carry economics")
        elif status == "canceled":
            if order_id not in self._cancels or quantity != 0 or price != 0 or fee != 0:
                raise BridgeError("unsolicited or economic cancellation receipt")
            self.engine.acknowledge_cancel(order_id, at)
            self._cancels.remove(order_id)
        elif status in {"filled", "partially_filled"}:
            fill = self._pending.get(order_id)
            if fill is None or order_id not in self._issued:
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

    def finish(self) -> dict:
        if self._index != len(self._frames) - 1 or self._pending or self._cancels:
            raise BridgeError("incomplete callback/calendar sequence")
        snapshot = self.engine.snapshot()
        if snapshot["completion_blocked"]:
            raise BridgeError("shadow strategy remains incomplete")
        if len(self._bindings) != len(self._submitted) or self._acknowledged != len(snapshot["fills"]):
            raise BridgeError("native/shadow order lineage incomplete")
        return {"schema": "gdr.lean.callback-contract.v1", "strategy": snapshot,
                "acknowledged_fills": self._acknowledged, "native_orders": len(self._bindings),
                "fixture_sha256": hash_bytes(fixture_stream()), "runtime_verified": False,
                "cloud_completed": False, "empirical_evidence": False}
