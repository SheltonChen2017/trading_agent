"""In-memory, order-based GDR engineering fixture engine; never market evidence.

All identifiers must be visibly synthetic (``SYN-``). Calendar sessions,
settlement dates and normalized quote/minute fixtures are supplied explicitly;
this module does not discover, read or fetch data, call a broker, or establish
source rights/PIT status. Its fills are modeling assumptions, not QC fills.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from functools import wraps
from zoneinfo import ZoneInfo

from data.financial_primitives import (
    decimal_text,
    exact_decimal_add as add,
    exact_decimal_multiply as mul,
    exact_decimal_subtract as sub,
    exact_decimal_sum as total,
)

NY = ZoneInfo("America/New_York")
ZERO = Decimal("0")
ACTIVE = frozenset(("open", "cancel_requested"))
EXIT_PRIORITY = {"program_drawdown": 1, "position_stop": 2,
                 "guidance_invalidation": 3, "time": 4, "trim": 5}


class SimulationError(ValueError):
    """Invalid synthetic input/state transition; the operation is atomic."""


def _money(value: object, name: str, *, zero: bool = False) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise SimulationError(f"{name} requires an exact finite Decimal")
    parts = value.as_tuple()
    if (len(parts.digits) > 64 or abs(int(parts.exponent)) > 32
            or (value and abs(value.adjusted()) > 32)):
        raise SimulationError(f"{name} exceeds fixture arithmetic bounds")
    if value < 0 or (not zero and value == 0):
        raise SimulationError(f"{name} must be {'nonnegative' if zero else 'positive'}")
    return value


def _integer(value: object, name: str, *, zero: bool = False) -> int:
    if type(value) is not int or value < (0 if zero else 1) or value > 10**12:
        raise SimulationError(f"{name} must be a bounded exact integer")
    return value


def _id(value: object, name: str) -> str:
    if (type(value) is not str or not value.startswith("SYN-")
            or not 5 <= len(value) <= 100
            or any(not (c.isascii() and (c.isalnum() or c in "-_.")) for c in value)):
        raise SimulationError(f"{name} must be a bounded SYN- fixture identifier")
    return value


def _sector(value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= 80 or not value.isascii() or not value.isprintable():
        raise SimulationError("sector must be a bounded printable fixture label")
    return value


def _at(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise SimulationError("timestamp must be an explicit aware UTC datetime")
    return value


def _floor_ratio(a: Decimal, b: Decimal) -> int:
    an, ad = a.as_integer_ratio()
    bn, bd = b.as_integer_ratio()
    return (an * bd) // (ad * bn)


def commission_total(cumulative_quantity: int, mode: str = "base") -> Decimal:
    """Cumulative order commission; incremental fills charge the difference."""
    _integer(cumulative_quantity, "cumulative_quantity", zero=True)
    if type(mode) is not str or mode not in ("base", "stress"):
        raise SimulationError("unknown execution mode")
    return max(Decimal("2" if mode == "stress" else "1"),
               mul(Decimal(cumulative_quantity), Decimal("0.005"))) if cumulative_quantity else ZERO


def execution_price(side: str, bid: Decimal, ask: Decimal, mode: str = "base") -> Decimal:
    """Quote-side execution plus adverse impact; the spread is counted once."""
    if type(side) is not str or side not in ("buy", "sell"):
        raise SimulationError("unknown order side")
    if type(mode) is not str or mode not in ("base", "stress"):
        raise SimulationError("unknown execution mode")
    if _money(bid, "bid") > _money(ask, "ask"):
        raise SimulationError("quote is crossed")
    factor = (Decimal("1.0005" if mode == "base" else "1.0015") if side == "buy"
              else Decimal("0.9995" if mode == "base" else "0.9985"))
    return mul(ask if side == "buy" else bid, factor)


def _json(value: object) -> object:
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(v) for v in value]
    return value


@dataclass(frozen=True, slots=True)
class Session:
    """Explicit regular-session bounds, including any early close."""
    day: date
    opens_at: datetime
    closes_at: datetime

    def __post_init__(self) -> None:
        if type(self.day) is not date:
            raise SimulationError("session day must be an exact date")
        start, end = _at(self.opens_at), _at(self.closes_at)
        if (start.astimezone(NY).date() != self.day
                or end.astimezone(NY).date() != self.day
                or start.astimezone(NY).time() != time(9, 30)
                or end.astimezone(NY).time() not in (time(13), time(16))
                or start >= end):
            raise SimulationError("unsupported regular-session bounds")


@dataclass(frozen=True, slots=True)
class Quote:
    at: datetime
    bid: Decimal
    ask: Decimal

    def __post_init__(self) -> None:
        _at(self.at)
        if _money(self.bid, "bid") > _money(self.ask, "ask"):
            raise SimulationError("quote is crossed")


@dataclass(frozen=True, slots=True)
class Minute:
    issuer: str
    at: datetime
    bid: Decimal
    ask: Decimal
    volume: int
    adv20: Decimal
    settlement_session: date

    def __post_init__(self) -> None:
        _id(self.issuer, "issuer")
        Quote(self.at, self.bid, self.ask)
        _integer(self.volume, "volume", zero=True)
        _money(self.adv20, "adv20")
        if type(self.settlement_session) is not date:
            raise SimulationError("settlement session requires an exact date")


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    event_id: str
    issuer: str
    sector: str
    side: str
    quantity: int
    remaining: int
    limit: Decimal | None
    submitted_at: datetime
    execution_session: date
    adv20: Decimal
    status: str = "open"
    filled_quantity: int = 0
    fees_paid: Decimal = ZERO
    reserved_notional: Decimal = ZERO
    reserved_fee: Decimal = ZERO
    execution_after: datetime | None = None
    exit_reason: str | None = None


@dataclass(frozen=True, slots=True)
class Fill:
    order_id: str
    event_id: str
    issuer: str
    side: str
    quantity: int
    price: Decimal
    fee: Decimal
    at: datetime
    settlement_session: date


@dataclass(frozen=True, slots=True)
class Position:
    issuer: str
    sector: str
    quantity: int
    entry_notional: Decimal
    reference_quantity: Decimal
    entry_session: date


def _atomic(function):
    @wraps(function)
    def transactional(self, *args, **kwargs):
        previous = deepcopy(self._state)
        try:
            result = function(self, *args, **kwargs)
            self._check_cash()
            return deepcopy(result)
        except Exception:
            self._state = previous
            raise
    return transactional


class Simulation:
    """Incremental synthetic sleeve with exact money and explicit unresolved state.

    Input calendar correctness remains an upstream audited contract. A sequence
    cannot silently supply a calendar or settlement policy from the machine.
    Each public mutation rolls back fully on malformed input or invalid state.
    Snapshots/records are detached copies; this is not a persisted recovery or
    adversarial process-isolation/security boundary.
    """

    def __init__(self, sessions: tuple[Session, ...], *, mode: str = "base",
                 initial_cash: Decimal = Decimal("100000")) -> None:
        if type(sessions) is not tuple or not 2 <= len(sessions) <= 10000:
            raise SimulationError("provide a bounded immutable session tuple")
        verified = []
        for session in sessions:
            if type(session) is not Session:
                raise SimulationError("provide exact Session records")
            verified.append(Session(session.day, session.opens_at, session.closes_at))
        days = tuple(s.day for s in verified)
        if days != tuple(sorted(set(days))):
            raise SimulationError("sessions must be unique and increasing")
        if type(mode) is not str or mode not in ("base", "stress"):
            raise SimulationError("unknown execution mode")
        if _money(initial_cash, "initial cash") != Decimal("100000"):
            raise SimulationError("candidate initial cash is pinned to USD 100000")
        self._sessions = {s.day: s for s in verified}
        self._days = days
        self._index = {d: i for i, d in enumerate(days)}
        self._mode = mode
        self._state = {"clock": None, "cash": initial_cash, "orders": {},
                       "positions": {}, "fills": [], "receivables": [],
                       "attempts": {}, "minutes": {}, "daily_used": {},
                       "marks": {}, "last_close": None, "navs": [],
                       "high_water": initial_cash, "stopped": False,
                       "due": {}, "refusals": [], "actions": {},
                       "unresolved": {}, "cancel_acks": {},
                       "cancel_requests": {}, "invalidations": {},
                       "terminated": {},
                       "missing_session_closes": [],
                       "order_amendments": [],
                       "cash_movements": [{"kind": "opening_cash", "reference": "SYN-OPENING",
                                           "at": None, "delta": initial_cash, "balance": initial_cash}]}

    @property
    def fills(self) -> tuple[Fill, ...]:
        return deepcopy(tuple(self._state["fills"]))

    @property
    def orders(self) -> tuple[Order, ...]:
        return deepcopy(tuple(self._state["orders"].values()))

    @property
    def positions(self) -> tuple[Position, ...]:
        return deepcopy(tuple(self._state["positions"].values()))

    def snapshot(self) -> dict:
        state = self._state
        return _json({"schema": "gdr.synthetic_simulation.v1", "synthetic_only": True,
                      "market_evidence": False, "order_authority": False,
                      "mode": self._mode, "clock": state["clock"],
                      "settled_cash": state["cash"],
                      "reserved_cash": self._reserved(),
                      "available_cash": sub(state["cash"], self._reserved()),
                      "stopped": state["stopped"],
                      "positions": [asdict(p) for p in self.positions],
                      "orders": [asdict(o) for o in self.orders],
                      "order_amendments": deepcopy(state["order_amendments"]),
                      "fills": [asdict(f) for f in self.fills],
                      "receivables": deepcopy(state["receivables"]),
                      "cash_movements": deepcopy(state["cash_movements"]),
                      "corporate_actions": deepcopy(state["actions"]),
                      "navs": deepcopy(state["navs"]),
                      "refusals": deepcopy(state["refusals"]),
                      "scheduled_exits": deepcopy(state["due"]),
                      "unresolved": deepcopy(state["unresolved"]),
                      "terminated_issuers": deepcopy(state["terminated"]),
                      "missing_session_closes": deepcopy(state["missing_session_closes"]),
                      "missing_valuation_sessions": [r["session"] for r in state["navs"] if r["nav"] is None],
                      "open_positions_block_study_completion": bool(state["positions"]),
                      "completion_blocked": bool(state["positions"] or state["receivables"]
                                                 or state["unresolved"]
                                                 or state["missing_session_closes"]
                                                 or any(r["nav"] is None for r in state["navs"])
                                                 or any(o.status in ACTIVE for o in self.orders))})

    def _session(self, at: datetime) -> Session:
        _at(at)
        session = self._sessions.get(at.astimezone(NY).date())
        if session is None:
            raise SimulationError("timestamp is outside the explicit session calendar")
        return session

    def _tick(self, at: datetime) -> Session:
        session = self._session(at)
        if self._state["clock"] is not None and at < self._state["clock"]:
            raise SimulationError("operations must be chronological")
        self._state["clock"] = at
        if at >= session.opens_at:
            pending = []
            for item in self._state["receivables"]:
                if item["pay_session"] <= session.day:
                    self._state["cash"] = add(self._state["cash"], item["amount"])
                    self._state["cash_movements"].append({"kind": "settlement", "reference": item["id"],
                                                          "at": at, "delta": item["amount"],
                                                          "balance": self._state["cash"]})
                else:
                    pending.append(item)
            self._state["receivables"] = pending
        return session

    def _reserved(self) -> Decimal:
        return total(add(o.reserved_notional, o.reserved_fee)
                     for o in self._state["orders"].values() if o.status in ACTIVE)

    def _check_cash(self) -> None:
        if self._state["cash"] < 0 or self._reserved() > self._state["cash"]:
            raise SimulationError("cash/reservation invariant violated")

    def _fee(self, quantity: int) -> Decimal:
        return commission_total(quantity, self._mode)

    def _nav(self) -> Decimal | None:
        if any(self._state["marks"].get(i) is None for i in self._state["positions"]):
            return None
        return total((self._state["cash"],
                      total(r["amount"] for r in self._state["receivables"]),
                      total(mul(self._state["marks"][i], Decimal(p.quantity))
                            for i, p in self._state["positions"].items())))

    def _refuse(self, event_id: str, at: datetime, reason: str) -> None:
        self._state["refusals"].append({"event_id": event_id, "at": at, "reason": reason})

    def _active(self, issuer: str, side: str | None = None) -> list[Order]:
        return [o for o in self._state["orders"].values()
                if o.issuer == issuer and o.status in ACTIVE and (side is None or o.side == side)]

    def _new_order(self, **kwargs) -> Order:
        oid = f"SYN-ORDER-{len(self._state['orders']) + 1:06d}"
        order = Order(order_id=oid, execution_after=kwargs["submitted_at"], **kwargs)
        self._state["orders"][oid] = order
        return order

    @_atomic
    def advance(self, at: datetime) -> None:
        """Advance the synthetic clock and settle explicitly due receivables."""
        self._tick(at)

    @_atomic
    def submit_entry(self, event_id: str, issuer: str, sector: str, at: datetime,
                     quote: Quote | None, adv20: Decimal, *,
                     valuation_quotes: dict[str, Quote] | None = None) -> Order | None:
        _id(event_id, "event_id"), _id(issuer, "issuer"), _sector(sector), _money(adv20, "adv20")
        if quote is not None:
            if type(quote) is not Quote:
                raise SimulationError("exact Quote or explicit missing quote required")
            quote = Quote(quote.at, quote.bid, quote.ask)
        if valuation_quotes is not None and type(valuation_quotes) is not dict:
            raise SimulationError("valuation_quotes must be an exact dictionary")
        verified_valuations = {}
        for held_id, held_quote in (valuation_quotes or {}).items():
            _id(held_id, "valuation issuer")
            if type(held_quote) is not Quote:
                raise SimulationError("valuation requires exact Quote records")
            verified_valuations[held_id] = Quote(held_quote.at, held_quote.bid, held_quote.ask)
        _at(at)
        fingerprint = (issuer, sector, at, quote, adv20, tuple(sorted(verified_valuations.items())))
        old = self._state["attempts"].get(event_id)
        if old is not None:
            if old[0] != fingerprint:
                raise SimulationError("conflicting or repeated event attempt")
            return self._state["orders"].get(old[1])
        session = self._tick(at)
        if at.astimezone(NY).time() != time(10):
            raise SimulationError("entry decisions must occur at 10:00 New York")
        self._state["attempts"][event_id] = (fingerprint, None)
        reason = None
        if self._state["stopped"]:
            reason = "program_stopped"
        elif issuer in self._state["terminated"]:
            reason = "issuer_terminated"
        elif issuer in self._state["positions"] or self._active(issuer):
            reason = "issuer_already_active"
        elif any(d["session"] <= session.day for d in self._state["due"].values()) or any(o.side == "sell" and o.status in ACTIVE for o in self.orders):
            reason = "exits_must_precede_entries"
        elif self._state["positions"] and (self._state["last_close"] is None or self._index[self._state["last_close"]] != self._index[session.day] - 1):
            reason = "missing_previous_session_valuation"
        elif self._nav() is None or self._state["unresolved"]:
            reason = "missing_valuation"
        elif set(verified_valuations) != set(self._state["positions"]):
            reason = "missing_current_portfolio_quotes"
        elif any(q.at > at or at - q.at > timedelta(seconds=60) for q in verified_valuations.values()):
            reason = "stale_current_portfolio_quote"
        elif quote is None:
            reason = "missing_quote"
        elif quote.at > at or at - quote.at > timedelta(seconds=60):
            reason = "stale_or_future_quote"
        elif mul(sub(quote.ask, quote.bid), Decimal("2")) > mul(add(quote.ask, quote.bid), Decimal("0.005")):
            reason = "spread_too_wide"
        elif adv20 < Decimal("20000000"):
            reason = "insufficient_adv20"
        if reason:
            self._refuse(event_id, at, reason)
            return None
        self._state["marks"].update({i: mul(add(q.bid, q.ask), Decimal("0.5"))
                                     for i, q in verified_valuations.items()})
        nav = self._nav()
        gross = total(mul(self._state["marks"][i], Decimal(p.quantity)) for i, p in self._state["positions"].items())
        sector_value = total(mul(self._state["marks"][i], Decimal(p.quantity)) for i, p in self._state["positions"].items() if p.sector == sector)
        pending = [o for o in self.orders if o.side == "buy" and o.status in ACTIVE]
        gross = add(gross, total(o.reserved_notional for o in pending))
        sector_value = add(sector_value, total(o.reserved_notional for o in pending if o.sector == sector))
        limit = mul(quote.ask, Decimal("1.01"))
        budget = min(mul(nav, Decimal("0.05")), Decimal("5000"), mul(adv20, Decimal("0.001")), sub(mul(nav, Decimal("0.5")), gross), sub(mul(nav, Decimal("0.15")), sector_value))
        cash = sub(self._state["cash"], self._reserved())
        quantity = max(0, _floor_ratio(max(ZERO, budget), limit))
        lo, hi = 0, quantity
        while lo < hi:
            middle = (lo + hi + 1) // 2
            if add(mul(Decimal(middle), limit), self._fee(middle)) <= cash:
                lo = middle
            else:
                hi = middle - 1
        quantity = lo
        if not quantity:
            self._refuse(event_id, at, "zero_affordable_shares_or_capacity")
            return None
        order = self._new_order(event_id=event_id, issuer=issuer, sector=sector,
                                side="buy", quantity=quantity, remaining=quantity,
                                limit=limit, submitted_at=at, execution_session=session.day,
                                adv20=adv20, reserved_notional=mul(limit, Decimal(quantity)),
                                reserved_fee=self._fee(quantity))
        self._state["attempts"][event_id] = (fingerprint, order.order_id)
        return order

    @_atomic
    def request_cancel(self, order_id: str, at: datetime) -> Order:
        order = self._state["orders"].get(_id(order_id, "order_id"))
        if order is None:
            raise SimulationError("unknown order")
        _at(at)
        if self._state["cancel_requests"].get(order_id) == at:
            return order
        self._tick(at)
        if order.status == "open":
            order = replace(order, status="cancel_requested")
            self._state["orders"][order_id] = order
            self._state["cancel_requests"][order_id] = at
        return order

    @_atomic
    def cancel_entry_remainders(self, at: datetime) -> tuple[Order, ...]:
        session = self._tick(at)
        if at.astimezone(NY).time() != time(10, 5):
            raise SimulationError("scheduled entry cancellation is at 10:05")
        result = []
        for order in self.orders:
            if order.side == "buy" and order.execution_session == session.day and order.status == "open":
                updated = replace(order, status="cancel_requested")
                self._state["orders"][order.order_id] = updated
                self._state["cancel_requests"].setdefault(order.order_id, at)
                result.append(updated)
        return tuple(result)

    @_atomic
    def acknowledge_cancel(self, order_id: str, at: datetime) -> Order:
        _id(order_id, "order_id"), _at(at)
        if order_id in self._state["cancel_acks"]:
            if at != self._state["cancel_acks"][order_id]:
                raise SimulationError("conflicting cancellation acknowledgment replay")
            return self._state["orders"][order_id]
        order = self._state["orders"].get(order_id)
        if (order is None or order.status not in ("cancel_requested", "filled")
                or order_id not in self._state["cancel_requests"]):
            raise SimulationError("cancellation was not requested")
        self._tick(at)
        if order.status == "cancel_requested":
            order = replace(order, status="cancelled", reserved_notional=ZERO, reserved_fee=ZERO)
            self._state["orders"][order_id] = order
        self._state["cancel_acks"][order_id] = at
        return order

    def _settlement(self, day: date, execution_day: date) -> None:
        if type(day) is not date or day not in self._index or day < execution_day:
            raise SimulationError("explicit settlement must be a known nonpast session")

    @_atomic
    def process_minute(self, minute: Minute) -> tuple[Fill, ...]:
        if type(minute) is not Minute:
            raise SimulationError("exact Minute required")
        minute = Minute(**asdict(minute))
        key = (minute.issuer, minute.at)
        previous = self._state["minutes"].get(key)
        if previous is not None:
            if previous != minute:
                raise SimulationError("conflicting minute replay")
            return ()
        session = self._tick(minute.at)
        if not session.opens_at < minute.at <= session.closes_at or minute.at.second or minute.at.microsecond:
            raise SimulationError("completed regular-session minute boundary required")
        self._settlement(minute.settlement_session, session.day)
        active = [o for o in self._active(minute.issuer) if o.execution_session == session.day]
        if any(o.adv20 != minute.adv20 for o in active):
            raise SimulationError("minute ADV must match the decision-pinned order ADV")
        self._state["minutes"][key] = minute
        if minute.issuer in self._state["unresolved"]:
            self._refuse(f"SYN-EXIT-{minute.issuer}", minute.at, "unresolved_terminal_action")
            return ()
        capacity = minute.volume // 100
        result = []
        for order in sorted(active, key=lambda o: (o.side != "sell", o.order_id)):
            # No fill on the quote/minute used to decide; cancellation requests
            # still race with executions until a terminal acknowledgment.
            if minute.at <= (order.execution_after or order.submitted_at) or not capacity:
                continue
            if order.side == "buy" and minute.at.astimezone(NY).time() >= time(10, 5) and order.status == "open":
                order = replace(order, status="cancel_requested")
                self._state["orders"][order.order_id] = order
                self._state["cancel_requests"].setdefault(order.order_id, minute.at)
            price = execution_price(order.side, minute.bid, minute.ask, self._mode)
            if order.limit is not None and price > order.limit:
                continue
            used_key = (minute.issuer, session.day)
            available = sub(mul(order.adv20, Decimal("0.001")), self._state["daily_used"].get(used_key, ZERO))
            quantity = min(order.remaining, capacity, max(0, _floor_ratio(max(ZERO, available), price)))
            if not quantity:
                continue
            fee_total = self._fee(order.filled_quantity + quantity)
            fee = sub(fee_total, order.fees_paid)
            notional = mul(price, Decimal(quantity))
            remaining = order.remaining - quantity
            updated = replace(order, remaining=remaining, filled_quantity=order.filled_quantity + quantity,
                              fees_paid=fee_total, status="filled" if not remaining else order.status,
                              reserved_notional=mul(order.limit, Decimal(remaining)) if order.side == "buy" else ZERO,
                              reserved_fee=max(ZERO, sub(self._fee(order.quantity), fee_total)) if order.side == "buy" and remaining else ZERO)
            self._state["orders"][order.order_id] = updated
            if order.side == "buy":
                self._state["cash"] = sub(self._state["cash"], add(notional, fee))
                self._state["cash_movements"].append({"kind": "buy_fill", "reference": f"{order.order_id}-{updated.filled_quantity}",
                                                      "at": minute.at, "delta": sub(ZERO, add(notional, fee)),
                                                      "balance": self._state["cash"]})
                position = self._state["positions"].get(order.issuer)
                if position is None:
                    position = Position(order.issuer, order.sector, quantity, notional, Decimal(quantity), session.day)
                else:
                    position = replace(position, quantity=position.quantity + quantity,
                                       entry_notional=add(position.entry_notional, notional),
                                       reference_quantity=add(position.reference_quantity, Decimal(quantity)))
                self._state["positions"][order.issuer] = position
                self._state["marks"][order.issuer] = price
                if order.order_id in self._state["invalidations"]:
                    self._schedule(order.issuer, self._state["invalidations"][order.order_id], "guidance_invalidation", position.quantity)
            else:
                position = self._state["positions"][order.issuer]
                if quantity > position.quantity:
                    raise SimulationError("sale exceeds position")
                if quantity == position.quantity:
                    del self._state["positions"][order.issuer]
                    self._state["marks"].pop(order.issuer, None)
                    self._state["due"].pop(order.issuer, None)
                else:
                    self._state["positions"][order.issuer] = replace(position, quantity=position.quantity - quantity)
                    due = self._state["due"].get(order.issuer)
                    if due is not None:
                        if due["quantity"] <= quantity:
                            self._state["due"].pop(order.issuer)
                        else:
                            due["quantity"] -= quantity
                # A tiny legitimate exit may have a fee above its proceeds.
                # Pay the shortfall from settled cash, never invent a negative
                # receivable or suppress the exit because a mark is missing.
                fee_shortfall = max(ZERO, sub(fee, notional))
                self._state["cash"] = sub(self._state["cash"], fee_shortfall)
                if fee_shortfall:
                    self._state["cash_movements"].append({"kind": "exit_fee_shortfall", "reference": f"{order.order_id}-{updated.filled_quantity}",
                                                          "at": minute.at, "delta": sub(ZERO, fee_shortfall),
                                                          "balance": self._state["cash"]})
                self._state["receivables"].append({"id": f"{order.order_id}-{updated.filled_quantity}",
                                                   "kind": "sale", "amount": max(ZERO, sub(notional, fee)),
                                                   "pay_session": minute.settlement_session})
            self._state["daily_used"][used_key] = add(self._state["daily_used"].get(used_key, ZERO), notional)
            capacity -= quantity
            fill = Fill(order.order_id, order.event_id, order.issuer, order.side, quantity, price, fee, minute.at, minute.settlement_session)
            self._state["fills"].append(fill)
            result.append(fill)
        return tuple(result)

    def _schedule(self, issuer: str, day: date, reason: str, quantity: int) -> None:
        current = self._state["due"].get(issuer)
        proposed = {"session": day, "reason": reason, "quantity": quantity}
        if current is None:
            self._state["due"][issuer] = proposed
        else:
            current["session"] = min(current["session"], day)
            current["quantity"] = max(current["quantity"], quantity)
            if EXIT_PRIORITY[reason] < EXIT_PRIORITY[current["reason"]]:
                current["reason"] = reason

    @_atomic
    def schedule_invalidation(self, issuer: str, effective_session: date, at: datetime) -> None:
        _id(issuer, "issuer")
        self._tick(at)
        if type(effective_session) is not date or effective_session not in self._index or self._index[effective_session] == 0:
            raise SimulationError("known invalidation session with predecessor required")
        prior_day = self._days[self._index[effective_session] - 1]
        cutoff = datetime.combine(prior_day, time(18), NY).astimezone(timezone.utc)
        if at > cutoff:
            raise SimulationError("invalidation missed the specified session cutoff")
        for order in self._active(issuer, "buy"):
            self._state["orders"][order.order_id] = replace(order, status="cancel_requested")
            self._state["cancel_requests"].setdefault(order.order_id, at)
            self._state["invalidations"][order.order_id] = effective_session
        if issuer in self._state["positions"]:
            self._schedule(issuer, effective_session, "guidance_invalidation", self._state["positions"][issuer].quantity)

    def _exit(self, issuer: str, at: datetime, reason: str, adv20: Decimal, quantity: int | None) -> Order | None:
        _id(issuer, "issuer"), _money(adv20, "adv20")
        session = self._tick(at)
        if at.astimezone(NY).time() != time(10) or reason not in EXIT_PRIORITY:
            raise SimulationError("supported exits submit at 10:00 New York")
        position = self._state["positions"].get(issuer)
        if position is None:
            raise SimulationError("no position to sell")
        quantity = position.quantity if quantity is None else _integer(quantity, "quantity")
        if quantity > position.quantity:
            raise SimulationError("exit exceeds position")
        existing = self._active(issuer, "sell")
        if existing:
            if len(existing) != 1:
                raise SimulationError("ambiguous pending exit")
            order = existing[0]
            if order.execution_session == session.day and order.adv20 != adv20:
                raise SimulationError("same-session exit ADV cannot change")
            upgraded_reason = (reason if order.exit_reason is None
                               or EXIT_PRIORITY[reason] < EXIT_PRIORITY[order.exit_reason]
                               else order.exit_reason)
            if quantity > order.remaining or upgraded_reason != order.exit_reason:
                if order.status == "cancel_requested":
                    self._refuse(order.event_id, at, "reconcile_cancelled_exit_before_amendment")
                    return None
                # This is an explicit in-memory order amendment, not a broker
                # cancellation acknowledgment. Preserve prior executions and
                # the cumulative commission basis; do not let an old partial
                # trim restrict a subsequently required full liquidation.
                new_remaining = max(quantity, order.remaining)
                self._state["order_amendments"].append({
                    "order_id": order.order_id, "at": at,
                    "previous_quantity": order.quantity,
                    "previous_remaining": order.remaining,
                    "previous_reason": order.exit_reason,
                    "quantity": order.filled_quantity + new_remaining,
                    "remaining": new_remaining, "reason": upgraded_reason,
                    "filled_quantity": order.filled_quantity,
                    "fees_paid": order.fees_paid,
                    "synthetic_only": True})
                order = replace(order, quantity=order.filled_quantity + new_remaining,
                                remaining=new_remaining, exit_reason=upgraded_reason,
                                execution_after=at)
                self._state["orders"][order.order_id] = order
            if order.execution_session < session.day and order.status == "open":
                order = replace(order, execution_session=session.day, adv20=adv20, execution_after=at)
                self._state["orders"][order.order_id] = order
            return order
        if self._active(issuer, "buy"):
            self._refuse(f"SYN-EXIT-{issuer}", at, "reconcile_racing_entry_before_exit")
            return None
        return self._new_order(event_id=f"SYN-EXIT-{len(self._state['orders']) + 1}", issuer=issuer,
                               sector=position.sector, side="sell", quantity=quantity, remaining=quantity,
                               limit=None, submitted_at=at, execution_session=session.day, adv20=adv20,
                               exit_reason=reason)

    @_atomic
    def request_exit(self, issuer: str, at: datetime, reason: str, adv20: Decimal,
                     quantity: int | None = None) -> Order | None:
        return self._exit(issuer, at, reason, adv20, quantity)

    @_atomic
    def execute_due_exits(self, at: datetime, adv20_by_issuer: dict[str, Decimal]) -> tuple[Order, ...]:
        session = self._tick(at)
        if type(adv20_by_issuer) is not dict:
            raise SimulationError("explicit per-issuer exit ADV dictionary required")
        for issuer, value in adv20_by_issuer.items():
            _id(issuer, "issuer"), _money(value, "adv20")
        result = []
        for issuer, due in sorted(self._state["due"].items(), key=lambda item: (EXIT_PRIORITY[item[1]["reason"]], item[0])):
            if due["session"] > session.day:
                continue
            if issuer not in adv20_by_issuer:
                self._refuse(f"SYN-EXIT-{issuer}", at, "missing_exit_liquidity")
                continue
            order = self._exit(issuer, at, due["reason"], adv20_by_issuer[issuer], min(due["quantity"], self._state["positions"][issuer].quantity))
            if order is not None:
                result.append(order)
        return tuple(result)

    @_atomic
    def close_session(self, session: date, marks: dict[str, Decimal | None]) -> dict:
        if type(session) is not date or session not in self._sessions or type(marks) is not dict:
            raise SimulationError("known session and raw-close marks dictionary required")
        for issuer, mark in marks.items():
            _id(issuer, "issuer")
            if mark is not None:
                _money(mark, "raw close")
        if set(marks) - set(self._state["positions"]):
            raise SimulationError("marks contain an issuer not held")
        prior = self._state["last_close"]
        if prior is not None and session <= prior:
            raise SimulationError("session already closed or out of order")
        first_missing = self._index[prior] + 1 if prior is not None else 0
        self._state["missing_session_closes"].extend(self._days[first_missing:self._index[session]])
        self._tick(self._sessions[session].closes_at)
        self._state["marks"] = {
            i: None if self._state["unresolved"].get(i) == "unresolved_terminal_action" else marks.get(i)
            for i in self._state["positions"]}
        self._state["last_close"] = session
        nav = self._nav()
        next_index = self._index[session] + 1
        next_day = self._days[next_index] if next_index < len(self._days) else None
        if nav is not None:
            self._state["high_water"] = max(nav, self._state["high_water"])
            if nav <= mul(self._state["high_water"], Decimal("0.85")):
                self._state["stopped"] = True
        for order in self.orders:
            if order.side == "buy" and order.status == "open":
                self._state["orders"][order.order_id] = replace(order, status="cancel_requested")
                self._state["cancel_requests"].setdefault(order.order_id, self._sessions[session].closes_at)
        gross_room = mul(nav, Decimal("0.5")) if nav is not None else ZERO
        sector_room = {}
        for issuer, position in sorted(self._state["positions"].items()):
            reason = None
            mark = self._state["marks"][issuer]
            if self._state["stopped"]:
                reason = "program_drawdown"
            elif mark is not None and mul(mark, position.reference_quantity) <= mul(position.entry_notional, Decimal("0.9")):
                reason = "position_stop"
            elif next_day is not None and next_index >= self._index[position.entry_session] + 20:
                reason = "time"
            quantity = position.quantity
            if reason is None and nav is not None and mark is not None:
                remaining_sector = sector_room.get(position.sector, mul(nav, Decimal("0.15")))
                target = max(ZERO, min(mul(nav, Decimal("0.05")), remaining_sector, gross_room))
                retain = min(position.quantity, _floor_ratio(target, mark))
                retained_value = mul(mark, Decimal(retain))
                sector_room[position.sector] = sub(remaining_sector, retained_value)
                gross_room = sub(gross_room, retained_value)
                if retain < position.quantity:
                    reason, quantity = "trim", position.quantity - retain
            if reason:
                if next_day is None:
                    self._state["unresolved"][issuer] = "exit_beyond_fixture_window"
                else:
                    self._schedule(issuer, next_day, reason, quantity)
        record = {"session": session, "nav": nav,
                  "settled_cash": self._state["cash"],
                  "receivables": total(r["amount"] for r in self._state["receivables"]),
                  "missing_marks": tuple(sorted(i for i, value in self._state["marks"].items() if value is None)),
                  "stopped": self._state["stopped"], "synthetic_only": True}
        self._state["navs"].append(record)
        return record

    def _action(self, action_id: str, fingerprint: tuple, at: datetime) -> bool:
        _id(action_id, "action_id"), _at(at)
        old = self._state["actions"].get(action_id)
        if old is not None:
            if old != fingerprint:
                raise SimulationError("conflicting corporate-action replay")
            return False
        self._tick(at)
        self._state["actions"][action_id] = fingerprint
        return True

    @_atomic
    def apply_split(self, action_id: str, issuer: str, ratio: Decimal, at: datetime) -> None:
        _id(issuer, "issuer"), _money(ratio, "split ratio")
        if not self._action(action_id, ("split", issuer, ratio, at), at):
            return
        session = self._session(at)
        if at != session.opens_at or self._active(issuer):
            raise SimulationError("split requires session open and reconciled terminal orders")
        position = self._state["positions"].get(issuer)
        if position is None:
            raise SimulationError("split requires a held issuer")
        shares = mul(Decimal(position.quantity), ratio)
        whole = _floor_ratio(shares, Decimal("1"))
        if shares != Decimal(whole) or whole == 0:
            raise SimulationError("fractional split/cash-in-lieu requires a separately modeled action")
        _integer(whole, "split shares")
        reference_quantity = _money(mul(position.reference_quantity, ratio), "split reference quantity")
        self._state["positions"][issuer] = replace(position, quantity=whole, reference_quantity=reference_quantity)
        # Invalidate the old price; a post-split raw mark is required. Never
        # mix pre-split prices with the new share count or fabricate a mark.
        self._state["marks"][issuer] = None
        if issuer in self._state["due"]:
            due_shares = mul(Decimal(self._state["due"][issuer]["quantity"]), ratio)
            if due_shares != Decimal(_floor_ratio(due_shares, Decimal("1"))):
                raise SimulationError("fractional scheduled split trim is unsupported")
            self._state["due"][issuer]["quantity"] = int(due_shares)

    @_atomic
    def credit_dividend(self, action_id: str, issuer: str, per_share: Decimal,
                        at: datetime, pay_session: date) -> None:
        _id(issuer, "issuer"), _money(per_share, "dividend", zero=True)
        if not self._action(action_id, ("dividend", issuer, per_share, at, pay_session), at):
            return
        session = self._session(at)
        self._settlement(pay_session, session.day)
        if at != session.opens_at:
            raise SimulationError("dividend entitlement requires explicit ex-session open")
        position = self._state["positions"].get(issuer)
        if position is None:
            raise SimulationError("dividend requires a held issuer")
        self._state["receivables"].append({"id": action_id, "kind": "dividend",
                                           "amount": mul(per_share, Decimal(position.quantity)),
                                           "pay_session": pay_session})

    @_atomic
    def terminal_settlement(self, action_id: str, issuer: str, at: datetime,
                            proceeds: Decimal | None, pay_session: date | None) -> None:
        """Explicit synthetic terminal payout or a visible unresolved position.

        No last-close liquidation is substituted. Noncash mergers/conversions
        require a future dedicated contract and are not guessed here.
        """
        _id(issuer, "issuer")
        if proceeds is not None:
            _money(proceeds, "terminal proceeds", zero=True)
        if (proceeds is None) != (pay_session is None):
            raise SimulationError("terminal amount and payment session must be supplied together")
        if not self._action(action_id, ("terminal", issuer, at, proceeds, pay_session), at):
            return
        session = self._session(at)
        held = issuer in self._state["positions"]
        if not held and not self._active(issuer):
            raise SimulationError("terminal action requires a held issuer")
        if not held and proceeds is not None:
            raise SimulationError("terminal payout without a held entitlement")
        self._state["terminated"][issuer] = action_id
        for order in self._active(issuer):
            self._state["orders"][order.order_id] = replace(order, status="cancelled", reserved_notional=ZERO, reserved_fee=ZERO)
        if proceeds is None:
            if held:
                self._state["unresolved"][issuer] = "unresolved_terminal_action"
                self._state["marks"][issuer] = None
            return
        self._settlement(pay_session, session.day)
        self._state["positions"].pop(issuer)
        self._state["marks"].pop(issuer, None)
        self._state["due"].pop(issuer, None)
        self._state["unresolved"].pop(issuer, None)
        self._state["receivables"].append({"id": action_id, "kind": "terminal",
                                           "amount": proceeds, "pay_session": pay_session})
