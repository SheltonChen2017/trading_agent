"""Offline paired callback prototype, separate from the approved QC candidate.

Only the invented corpus, SYN-GDR and SYN-SPY are supported. Native-style
receipts are supplied assertions, never authenticated engine evidence. No SDK,
provider, account, file, network or launch route is present.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal

from data.financial_primitives import exact_decimal_sum, to_decimal
from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.assessment import assess_candidate
from research.guidance_revision_drift.comparison import MatchedComparator
from research.guidance_revision_drift.contracts import _decode
from research.guidance_revision_drift.corporate_actions import CorporateAction, apply_corporate_action
from research.guidance_revision_drift.fixtures import example_corpus, fixture_instant, fixture_projection
from research.guidance_revision_drift.simulation import Minute, Quote, Session, Simulation, _at
from research.guidance_revision_drift.timing import NY


class PairedBridgeError(ValueError):
    """A synthetic callback disagrees with its independently retained input."""


SYMBOLS = {"strategy": "SYN-GDR", "comparator": "SYN-SPY"}
MAX_PROTOCOL_RECORDS = 2048


def _bytes(body):
    return canonical_json(fixture_projection(body)).encode("utf-8")


def _canonical(raw, schema):
    if type(raw) is not bytes or len(raw) > 65536:
        raise PairedBridgeError("bounded immutable callback bytes required")
    body = _decode(raw)
    if body.get("schema") != schema or _bytes(body) != raw:
        raise PairedBridgeError("canonical exact callback schema required")
    return body


class PairedSyntheticBridge:
    """Compose existing ledgers with atomic acknowledgement boundaries.

    Orders/fills are shadow effects first; all matching acknowledgements must
    clear before another engine operation or account observation. Comparator
    tranches are created only after their actual source fill is acknowledged.
    Neither sleeve can deposit funds or choose a historical settlement model.
    """

    def __init__(self, mode="base"):
        corpus = example_corpus()
        self._corpus = corpus
        self._sessions = tuple(Session(s.session_date, s.open_utc, s.close_utc)
                               for s in corpus.schedule.sessions)
        self._strategy = Simulation(self._sessions, mode=mode)
        self._comparator = MatchedComparator(self._sessions, mode=mode)
        self._clock = None
        self._orders = {}
        self._bindings = {}
        self._pending = []
        self._receipts = {}
        self._event_ids = {}
        self._source_count = 0
        self._actions = {}
        self._observations = {}
        self._records = []
        self._head = hash_bytes(_bytes({"schema": "gdr.synthetic.paired-genesis.v1",
            "corpus_sha256": corpus.sha256, "mode": mode, "external_authenticity_verified": False}))

    def _trace(self, kind, body):
        if len(self._records) >= MAX_PROTOCOL_RECORDS:
            raise PairedBridgeError("paired protocol capacity exhausted")
        raw = _bytes({"sequence": len(self._records), "previous_sha256": self._head,
                      "kind": kind, "body": body})
        self._records.append(raw)
        self._head = hash_bytes(raw)

    def _ready(self, at):
        _at(at)
        self._strategy._session(at)
        if self._pending:
            raise PairedBridgeError("prior paired receipt acknowledgement missing")
        if self._clock is not None and at < self._clock:
            raise PairedBridgeError("paired callbacks must be chronological")
        self._clock = at

    def _transaction(self, operation):
        draft = deepcopy(self)
        result = operation(draft)
        self.__dict__ = draft.__dict__
        return deepcopy(result)

    def _queue(self, sleeve, order_id, status, *, fill=None, quote=None):
        signed = (fill.quantity if fill.side == "buy" else -fill.quantity) if fill else 0
        receipt = {"sleeve": sleeve, "symbol": SYMBOLS[sleeve], "order_id": order_id,
            "status": status, "at": self._clock, "quantity": signed,
            "price": fill.price if fill else Decimal(0), "fee": fill.fee if fill else Decimal(0)}
        self._pending.append({"receipt": receipt, "fill": fill, "quote": quote})

    def _sync_orders(self):
        pairs = (("strategy", [fixture_projection(vars_order(o)) for o in self._strategy.orders]),
                 ("comparator", self._comparator.snapshot()["orders"]))
        for sleeve, orders in pairs:
            for order in orders:
                key = (sleeve, order["order_id"])
                if key not in self._orders:
                    self._orders[key] = order["status"]
                    if order["quantity"]:
                        self._queue(sleeve, key[1], "submitted")
                elif self._orders[key] == "open" and order["status"] == "cancelled" and sleeve == "comparator":
                    self._queue(sleeve, key[1], "cancel_pending")
                    self._queue(sleeve, key[1], "canceled")
                self._orders[key] = order["status"]

    def pending_receipts(self):
        return tuple(fixture_projection(item["receipt"]) for item in self._pending)

    def bind(self, sleeve, order_id, native_id, symbol):
        def operation(draft):
            key = (sleeve, order_id)
            if (type(sleeve) is not str or sleeve not in SYMBOLS or type(order_id) is not str
                    or type(symbol) is not str or symbol != SYMBOLS[sleeve]
                    or type(native_id) is not int or native_id <= 0 or key not in draft._orders
                    or key in draft._bindings or native_id in draft._bindings.values()
                    or not any(p["receipt"]["sleeve"] == sleeve and p["receipt"]["order_id"] == order_id
                               and p["receipt"]["status"] == "submitted" for p in draft._pending)):
                raise PairedBridgeError("invalid paired native-style binding")
            draft._bindings[key] = native_id
            draft._trace("binding", {"sleeve": sleeve, "symbol": symbol,
                                       "order_id": order_id, "native_id": native_id})
        return self._transaction(operation)

    def acknowledge(self, sleeve, native_id, event_id, *, symbol, status, at, quantity, price, fee):
        def operation(draft):
            if (type(sleeve) is not str or sleeve not in SYMBOLS or type(native_id) is not int
                    or type(event_id) is not int or event_id < 0 or type(quantity) is not int
                    or type(price) is not Decimal or type(fee) is not Decimal
                    or not price.is_finite() or not fee.is_finite() or symbol != SYMBOLS[sleeve]):
                raise PairedBridgeError("malformed paired native-style receipt")
            _at(at)
            receipt = (symbol, status, at, quantity, price, fee)
            identity = (sleeve, native_id, event_id)
            if identity in draft._receipts:
                if draft._receipts[identity] != receipt:
                    raise PairedBridgeError("conflicting paired receipt identity")
                return
            key = next((key for key, value in draft._bindings.items()
                        if key[0] == sleeve and value == native_id), None)
            if key is None or event_id <= draft._event_ids.get((sleeve, native_id), -1):
                raise PairedBridgeError("unknown or reordered paired receipt")
            index = next((i for i, p in enumerate(draft._pending)
                          if (p["receipt"]["sleeve"], p["receipt"]["order_id"]) == key), None)
            if index is None:
                raise PairedBridgeError("unsolicited paired receipt")
            item = draft._pending[index]
            expected = item["receipt"]
            if (status, at, quantity, price, fee) != tuple(expected[n] for n in ("status", "at", "quantity", "price", "fee")):
                raise PairedBridgeError("paired receipt differs from deterministic expectation")
            draft._pending.pop(index)
            fill = item["fill"]
            if fill is not None and sleeve == "strategy":
                draft._source_count += 1
                fill_id = f"SYN-PAIRED-FILL-{draft._source_count:04d}"
                if fill.side == "buy":
                    draft._comparator.record_entry(fill_id, fill, quote=item["quote"], adv20=Decimal("1000000000"))
                else:
                    held = draft._comparator.snapshot()["strategy_remaining"].get(fill.issuer, 0)
                    draft._comparator.record_exit(fill_id, fill, fraction_numerator=fill.quantity,
                        fraction_denominator=held, adv20=Decimal("1000000000"))
                draft._sync_orders()
            if sleeve == "strategy" and status == "canceled":
                draft._strategy.acknowledge_cancel(key[1], at)
                draft._orders[key] = "cancelled"
            draft._receipts[identity] = receipt
            draft._event_ids[(sleeve, native_id)] = event_id
            draft._trace("acknowledgement", {"native_id": native_id, "event_id": event_id, **expected})
        return self._transaction(operation)

    def decision(self, at, quote=None):
        def operation(draft):
            draft._ready(at)
            day = at.astimezone(NY).date()
            if at != fixture_instant(day, 10):
                raise PairedBridgeError("fixed decision clock required")
            draft._strategy.execute_due_exits(at, {"SYN-ISSUER-A": Decimal("25000000")})
            draft._comparator.advance(at)
            if day == date(2025, 4, 4):
                assessment = assess_candidate(book=draft._corpus.archive.book, disclosure_id="SYN-RAISE",
                    as_of=at, schedule=draft._corpus.schedule, permanent_security_id="SYN-SEC-A",
                    references=draft._corpus.references, bars=draft._corpus.bars)
                if assessment.eligible_session != day:
                    raise PairedBridgeError("fixed synthetic assessment failed")
                if quote is not None and type(quote) is not Quote:
                    raise PairedBridgeError("exact synthetic Quote required")
                draft._strategy.submit_entry("SYN-RAISE", "SYN-ISSUER-A", assessment.sector,
                    at, quote, assessment.adv20)
            draft._sync_orders()
            draft._trace("decision", {"at": at})
            return draft.pending_receipts()
        return self._transaction(operation)

    def minute(self, sleeve, minute, *, comparator_quote=None):
        def operation(draft):
            if type(sleeve) is not str or sleeve not in SYMBOLS or type(minute) is not Minute:
                raise PairedBridgeError("exact invented paired Minute required")
            issuer = "SYN-ISSUER-A" if sleeve == "strategy" else "SYN-SPY"
            if minute.issuer != issuer:
                raise PairedBridgeError("real or crossed paired issuer refused")
            draft._ready(minute.at)
            if sleeve == "strategy":
                if type(comparator_quote) is not Quote:
                    raise PairedBridgeError("explicit matched quote required")
                fills = draft._strategy.process_minute(minute)
                orders = {o.order_id: o.remaining for o in draft._strategy.orders}
            else:
                if comparator_quote is not None:
                    raise PairedBridgeError("comparator minute cannot carry a source quote")
                fills = draft._comparator.process_minute(minute)
                orders = {o["order_id"]: o["remaining"] for o in draft._comparator.snapshot()["orders"]}
            for fill in fills:
                status = "filled" if orders[fill.order_id] == 0 else "partially_filled"
                draft._queue(sleeve, fill.order_id, status, fill=fill, quote=comparator_quote)
            draft._trace("minute", {"sleeve": sleeve, "minute": vars_order(minute)})
            return draft.pending_receipts()
        return self._transaction(operation)

    def cancel(self, at):
        def operation(draft):
            draft._ready(at)
            for order in draft._strategy.cancel_entry_remainders(at):
                draft._queue("strategy", order.order_id, "cancel_pending")
                draft._queue("strategy", order.order_id, "canceled")
            draft._trace("cancel", {"at": at})
            return draft.pending_receipts()
        return self._transaction(operation)

    def action_callback(self, action, callback):
        """Reconcile supplied callback with its independent immutable input."""
        def operation(draft):
            if type(action) is not CorporateAction:
                raise PairedBridgeError("exact invented CorporateAction required")
            checked = CorporateAction(action.canonical_bytes)
            expected = action_callback_bytes(checked)
            _canonical(callback, "gdr.synthetic.paired-action-callback.v1")
            if callback != expected:
                raise PairedBridgeError("action callback differs from retained input")
            body = checked.to_dict()
            if body["issuer_id"] not in ("SYN-ISSUER-A", "SYN-SPY"):
                raise PairedBridgeError("real or unknown action issuer refused")
            identity = body["action_id"]
            if identity in draft._actions:
                if draft._actions[identity] != callback:
                    raise PairedBridgeError("conflicting paired action callback")
                return checked.sha256
            at = datetime.fromisoformat(body["effective_at"].replace("Z", "+00:00"))
            draft._ready(at)
            if (any(o.status in ("open", "cancel_requested") for o in draft._strategy.orders)
                    or any(o["status"] == "open" for o in draft._comparator.snapshot()["orders"])):
                raise PairedBridgeError("action requires reconciled terminal paired orders")
            apply_corporate_action(draft._strategy, draft._comparator, checked, schedule=draft._corpus.schedule)
            draft._actions[identity] = callback
            draft._trace("action", {"action_sha256": checked.sha256, "callback_sha256": hash_bytes(callback)})
            return checked.sha256
        return self._transaction(operation)

    def account_observation(self, sleeve, at):
        """Expected synthetic row; not an authenticated account observation."""
        if type(sleeve) is not str or sleeve not in SYMBOLS:
            raise PairedBridgeError("exact paired sleeve required")
        _at(at)
        engine = self._strategy if sleeve == "strategy" else self._comparator
        snap = engine.snapshot()
        quantity = sum(p["quantity"] for p in snap["positions"]) if sleeve == "strategy" else sum(t["quantity"] for t in snap["tranches"])
        cash = to_decimal(snap["settled_cash"])
        immediate = exact_decimal_sum((cash, *(to_decimal(r["amount"]) for r in snap["receivables"])))
        return _bytes({"schema": "gdr.synthetic.paired-account-observation.v1", "sleeve": sleeve,
            "symbol": SYMBOLS[sleeve], "at": at, "quantity": quantity,
            "settled_cash": cash, "reserved_cash": snap["reserved_cash"],
            "available_cash": snap["available_cash"], "receivables": snap["receivables"],
            "immediate_cash": immediate, "settlement_parity_verified": False,
            "external_authenticity_verified": False})

    def observe_accounts(self, at, strategy, comparator, *, settle=False):
        """Atomic explicit-date advance/reconciliation; never infer settlement."""
        def operation(draft):
            if type(settle) is not bool:
                raise PairedBridgeError("strict settlement mode required")
            _at(at)
            rows = {"strategy": strategy, "comparator": comparator}
            for raw in rows.values():
                _canonical(raw, "gdr.synthetic.paired-account-observation.v1")
            identity = (at, settle)
            if identity in draft._observations:
                if draft._observations[identity] != (strategy, comparator):
                    raise PairedBridgeError("conflicting paired account redelivery")
                return
            if not settle and draft._clock != at:
                raise PairedBridgeError("account observation must match the current callback clock")
            draft._ready(at)
            if settle:
                session = draft._strategy._session(at)
                if at != session.opens_at:
                    raise PairedBridgeError("explicit settlement observation requires session open")
                draft._strategy.advance(at)
                draft._comparator.advance(at)
            for sleeve, raw in rows.items():
                if raw != draft.account_observation(sleeve, at):
                    raise PairedBridgeError("paired settlement/account observation mismatch")
            draft._observations[identity] = (strategy, comparator)
            draft._trace("account_observation", {"at": at, "settle": settle,
                "strategy_sha256": hash_bytes(strategy), "comparator_sha256": hash_bytes(comparator)})
        return self._transaction(operation)

    def close(self, day, strategy_mark, comparator_mark):
        def operation(draft):
            if type(day) is not date:
                raise PairedBridgeError("fixed synthetic close date required")
            session = draft._strategy._sessions.get(day)
            if session is None:
                raise PairedBridgeError("fixed synthetic close date required")
            draft._ready(session.closes_at)
            marks = {p.issuer: strategy_mark for p in draft._strategy.positions}
            draft._strategy.close_session(day, marks)
            draft._comparator.close_session(day, comparator_mark)
            draft._trace("close", {"session": day})
            return draft.snapshot()
        return self._transaction(operation)

    def snapshot(self):
        return {"schema": "gdr.synthetic.paired-callback-prototype.v1",
            "strategy": self._strategy.snapshot(), "comparator": self._comparator.snapshot(),
            "protocol": {"clock": fixture_projection(self._clock), "bindings": fixture_projection(
                [{"sleeve": k[0], "order_id": k[1], "native_id": v} for k, v in self._bindings.items()]),
                "pending": list(self.pending_receipts()), "source_fill_count": self._source_count,
                "acknowledgement_count": len(self._receipts), "action_count": len(self._actions),
                "observation_count": len(self._observations), "trace_count": len(self._records),
                "trace_head_sha256": self._head}, "synthetic_only": True,
            "native_runtime_verified": False, "settlement_parity_verified": False,
            "cloud_completed": False, "empirical_evidence": False}


def vars_order(value):
    from dataclasses import asdict
    return asdict(value)


def action_callback_bytes(action):
    if type(action) is not CorporateAction:
        raise PairedBridgeError("exact invented action required")
    checked = CorporateAction(action.canonical_bytes)
    return _bytes({"schema": "gdr.synthetic.paired-action-callback.v1",
                   "action_sha256": checked.sha256, "action": checked.to_dict(),
                   "external_authenticity_verified": False})
