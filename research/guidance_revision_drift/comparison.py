"""Bounded synthetic order/tranche mirror and permanent comparison-parity audit.

Each supplied strategy Fill is an input assertion from a fixture engine, not
proof of an external execution. This module supplies no market evidence, cloud
parity, corporate-action adjustment, statistical inference, or authorization. It models
cash and whole-share tranches with its limitations explicit in every report.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps

from data.financial_primitives import exact_decimal_add as add
from data.financial_primitives import exact_decimal_multiply as mul
from data.financial_primitives import exact_decimal_subtract as sub
from data.financial_primitives import exact_decimal_sum as total
from research.guidance_revision_drift.simulation import (
    Fill, Minute, NY, Quote, Session, ZERO,
    _at, _floor_ratio, _id, _integer, _json, _money,
    commission_total, execution_price,
)


class ComparisonError(ValueError):
    """Invalid fixture transition; state is left unchanged."""


def _atomic(function):
    @wraps(function)
    def transactional(self, *args, **kwargs):
        before = deepcopy(self._state)
        try:
            result = function(self, *args, **kwargs)
            if self._state["cash"] < 0 or self._reserved() > self._state["cash"]:
                raise ComparisonError("comparator cash/reservation invariant violated")
            return deepcopy(result)
        except Exception:
            self._state = before
            raise
    return transactional


class MatchedComparator:
    """In-memory SYN-SPY mirror, with fixed initial cash and no deposit method.

    An entry creates one order and tranche per actual strategy partial Fill.
    Each strategy exit Fill creates a separate sell order for each affected
    tranche. Commission floors therefore apply to these comparator orders,
    not retroactively to the source strategy's order. A failed/partial/tardy
    match is permanently reported even if its pending order later completes.
    """

    def __init__(self, sessions: tuple[Session, ...], *, mode: str = "base"):
        if type(sessions) is not tuple or not 2 <= len(sessions) <= 10000:
            raise ComparisonError("provide an immutable bounded session tuple")
        for session in sessions:
            if type(session) is not Session:
                raise ComparisonError("exact simulation.Session records required")
            Session.__post_init__(session)
        days = tuple(s.day for s in sessions)
        if days != tuple(sorted(set(days))):
            raise ComparisonError("sessions must be unique and increasing")
        commission_total(0, mode)
        self._sessions = {s.day: Session(s.day, s.opens_at, s.closes_at) for s in sessions}
        self._days = days
        self._mode = mode
        self._state = {"clock": None, "cash": Decimal("100000"), "tranches": {},
                       "orders": {}, "source_receipts": {}, "source_identities": {}, "strategy_remaining": {},
                       "minutes": {}, "daily_used": {}, "receivables": [],
                       "fills": [], "blockers": [], "navs": [], "last_close": None,
                       "missing_session_closes": []}

    def _session(self, at):
        _at(at)
        session = self._sessions.get(at.astimezone(NY).date())
        if session is None:
            raise ComparisonError("timestamp outside explicit fixture sessions")
        return session

    def _tick(self, at):
        session = self._session(at)
        if self._state["clock"] is not None and at < self._state["clock"]:
            raise ComparisonError("operations must be chronological")
        self._state["clock"] = at
        if at >= session.opens_at:
            pending = []
            for receivable in self._state["receivables"]:
                if receivable["settlement_session"] <= session.day:
                    self._state["cash"] = add(self._state["cash"], receivable["amount"])
                else:
                    pending.append(receivable)
            self._state["receivables"] = pending
        return session

    def _source(self, fill, side):
        if type(fill) is not Fill:
            raise ComparisonError("exact strategy Fill required")
        for name in ("order_id", "event_id", "issuer"):
            _id(getattr(fill, name), name)
        if fill.side != side or fill.issuer == "SYN-SPY":
            raise ComparisonError("wrong source side or comparator security used as strategy")
        _integer(fill.quantity, "source quantity")
        _money(fill.price, "source price")
        _money(fill.fee, "source fee", zero=True)
        session = self._session(fill.at)
        if not session.opens_at < fill.at <= session.closes_at or fill.at.second or fill.at.microsecond:
            raise ComparisonError("strategy fill must have a completed regular-minute timestamp")
        if type(fill.settlement_session) is not date or fill.settlement_session not in self._sessions or fill.settlement_session < session.day:
            raise ComparisonError("source settlement must be a known nonpast session")
        return Fill(**asdict(fill))

    def _reserved(self):
        return total(o["reserved"] for o in self._state["orders"].values() if o["side"] == "buy" and o["status"] == "open")

    def _block(self, source_id, reason, at):
        key = (source_id, reason)
        if not any((item["source_fill_id"], item["reason"]) == key for item in self._state["blockers"]):
            self._state["blockers"].append({"source_fill_id": source_id, "reason": reason, "first_observed_at": at})

    def _order(self, source_id, tranche_id, side, quantity, at, adv20, limit=None):
        order_id = f"SYN-MATCH-{len(self._state['orders']) + 1:06d}"
        order = {"order_id": order_id, "source_fill_id": source_id, "tranche_id": tranche_id,
                 "side": side, "quantity": quantity, "remaining": quantity, "filled": 0,
                 "fee": ZERO, "at": at, "adv20": adv20, "limit": limit,
                 "reserved": add(mul(limit, Decimal(quantity)), commission_total(quantity, self._mode)) if side == "buy" else ZERO,
                 "status": "open" if quantity else "rounded_to_zero"}
        self._state["orders"][order_id] = order
        return order

    @_atomic
    def record_entry(self, fill_id: str, strategy_fill: Fill, *, quote: Quote, adv20: Decimal):
        """Reserve a distinct matched entry using a quote known at source-fill time.

        Sizing uses a marketable buy limit 1% above ask and worst-case order fee.
        Cash left by whole-share rounding stays idle; it is never injected into
        a later tranche to conceal comparator funding divergence.
        """
        _id(fill_id, "fill_id")
        source = self._source(strategy_fill, "buy")
        if type(quote) is not Quote:
            raise ComparisonError("exact Quote required")
        quote = Quote(quote.at, quote.bid, quote.ask)
        _money(adv20, "adv20")
        fingerprint = ("entry", source, quote, adv20)
        prior = self._state["source_receipts"].get(fill_id)
        if prior is not None:
            if prior != fingerprint:
                raise ComparisonError("conflicting source fill replay")
            return self._state["tranches"][fill_id]
        identity = (source.order_id, source.at, source.side)
        if identity in self._state["source_identities"]:
            raise ComparisonError("source order/minute fill identity was already assigned another fill_id")
        if quote.at > source.at or source.at - quote.at > timedelta(seconds=60):
            raise ComparisonError("entry quote is future or stale")
        self._tick(source.at)
        self._state["source_receipts"][fill_id] = fingerprint
        self._state["source_identities"][identity] = fill_id
        budget = add(mul(Decimal(source.quantity), source.price), source.fee)
        available = sub(self._state["cash"], self._reserved())
        allocated = min(budget, available)
        limit = mul(quote.ask, Decimal("1.01"))
        max_quantity = min(10**12, _floor_ratio(allocated, limit))
        lo, hi = 0, max_quantity
        while lo < hi:
            middle = (lo + hi + 1) // 2
            if add(mul(Decimal(middle), limit), commission_total(middle, self._mode)) <= allocated:
                lo = middle
            else:
                hi = middle - 1
        if allocated < budget:
            self._block(fill_id, "funding_mismatch", source.at)
        if mul(sub(quote.ask, quote.bid), Decimal("2")) > mul(add(quote.ask, quote.bid), Decimal("0.005")):
            lo = 0
            self._block(fill_id, "entry_spread_refusal", source.at)
        order = self._order(fill_id, fill_id, "buy", lo, source.at, adv20, limit)
        tranche = {"tranche_id": fill_id, "security": "SYN-SPY", "strategy_issuer": source.issuer,
                   "source_quantity": source.quantity, "source_budget": budget,
                   "allocated_budget": allocated, "quantity": 0, "entry_spent": ZERO,
                   "entry_order_id": order["order_id"], "entry_at": source.at}
        self._state["tranches"][fill_id] = tranche
        self._state["strategy_remaining"][source.issuer] = self._state["strategy_remaining"].get(source.issuer, 0) + source.quantity
        return tranche

    @_atomic
    def record_exit(self, fill_id: str, strategy_fill: Fill, *, fraction_numerator: int, fraction_denominator: int,
                    adv20: Decimal):
        """Close the actual strategy position's executed fraction, tranche by tranche.

        Remaining quantities exclude already pending comparator sells. Integer
        rounding may retain fractional-share-equivalent cash/exposure until the
        final strategy exit, which requests every remaining whole share.
        """
        _id(fill_id, "fill_id")
        source = self._source(strategy_fill, "sell")
        _integer(fraction_numerator, "fraction_numerator")
        _integer(fraction_denominator, "fraction_denominator")
        _money(adv20, "adv20")
        fingerprint = ("exit", source, fraction_numerator, fraction_denominator, adv20)
        prior = self._state["source_receipts"].get(fill_id)
        if prior is not None:
            if prior != fingerprint:
                raise ComparisonError("conflicting source fill replay")
            return tuple(o for o in self._state["orders"].values() if o["source_fill_id"] == fill_id)
        identity = (source.order_id, source.at, source.side)
        if identity in self._state["source_identities"]:
            raise ComparisonError("source order/minute fill identity was already assigned another fill_id")
        held = self._state["strategy_remaining"].get(source.issuer, 0)
        if not held or fraction_numerator != source.quantity or fraction_denominator != held or fraction_numerator > held:
            raise ComparisonError("unknown strategy position or wrong actual exit fraction")
        self._tick(source.at)
        self._state["source_receipts"][fill_id] = fingerprint
        self._state["source_identities"][identity] = fill_id
        result = []
        for tranche_id, tranche in self._state["tranches"].items():
            if tranche["strategy_issuer"] != source.issuer:
                continue
            entry = self._state["orders"][tranche["entry_order_id"]]
            if entry["status"] == "open":
                entry["status"], entry["reserved"] = "cancelled", ZERO
                self._block(tranche_id, "entry_unmatched_at_strategy_exit", source.at)
            pending = sum(o["remaining"] for o in self._state["orders"].values()
                          if o["tranche_id"] == tranche_id and o["side"] == "sell" and o["status"] == "open")
            available = tranche["quantity"] - pending
            quantity = available * fraction_numerator // fraction_denominator
            if quantity:
                result.append(self._order(fill_id, tranche_id, "sell", quantity, source.at, adv20))
        self._state["strategy_remaining"][source.issuer] = held - fraction_numerator
        return tuple(result)

    @_atomic
    def process_minute(self, minute: Minute) -> tuple[Fill, ...]:
        """Execute strictly later paired SYN-SPY quotes under shared capacity."""
        if type(minute) is not Minute:
            raise ComparisonError("exact Minute required")
        minute = Minute(**asdict(minute))
        if minute.issuer != "SYN-SPY":
            raise ComparisonError("only the synthetic comparator security is supported")
        prior = self._state["minutes"].get(minute.at)
        if prior is not None:
            if prior != minute:
                raise ComparisonError("conflicting comparator minute replay")
            return ()
        session = self._session(minute.at)
        if not session.opens_at < minute.at <= session.closes_at or minute.at.second or minute.at.microsecond:
            raise ComparisonError("completed regular-session minute boundary required")
        if minute.settlement_session not in self._sessions or minute.settlement_session < session.day:
            raise ComparisonError("known nonpast comparator settlement session required")
        active = [o for o in self._state["orders"].values() if o["status"] == "open"]
        if any(o["at"] >= minute.at for o in active):
            raise ComparisonError("same-bar or earlier comparator fills are forbidden")
        if any(o["adv20"] != minute.adv20 for o in active):
            raise ComparisonError("minute ADV differs from decision-pinned comparator ADV")
        self._tick(minute.at)
        self._state["minutes"][minute.at] = minute
        capacity = minute.volume // 100
        result = []
        for order in sorted(active, key=lambda o: (o["side"] != "sell", o["order_id"])):
            if minute.at != order["at"] + timedelta(minutes=1) and not order["filled"]:
                self._block(order["source_fill_id"], "timing_mismatch", minute.at)
            price = execution_price(order["side"], minute.bid, minute.ask, self._mode)
            daily_left = sub(mul(minute.adv20, Decimal("0.001")), self._state["daily_used"].get(session.day, ZERO))
            quantity = min(order["remaining"], capacity, max(0, _floor_ratio(max(ZERO, daily_left), price)))
            if order["limit"] is not None and price > order["limit"]:
                quantity = 0
                self._block(order["source_fill_id"], "limit_price_mismatch", minute.at)
            if quantity < order["remaining"]:
                self._block(order["source_fill_id"], "partial_or_unmatched_execution", minute.at)
            if not quantity:
                continue
            notional = mul(price, Decimal(quantity))
            fee_total = commission_total(order["filled"] + quantity, self._mode)
            fee = sub(fee_total, order["fee"])
            tranche = self._state["tranches"][order["tranche_id"]]
            if order["side"] == "buy":
                spend = add(notional, fee)
                self._state["cash"] = sub(self._state["cash"], spend)
                tranche["quantity"] += quantity
                tranche["entry_spent"] = add(tranche["entry_spent"], spend)
            else:
                if quantity > tranche["quantity"]:
                    raise ComparisonError("comparator sale exceeds tranche holdings")
                tranche["quantity"] -= quantity
                self._state["cash"] = sub(self._state["cash"], max(ZERO, sub(fee, notional)))
                self._state["receivables"].append({"order_id": order["order_id"],
                    "amount": max(ZERO, sub(notional, fee)), "settlement_session": minute.settlement_session})
            order["filled"] += quantity
            order["remaining"] -= quantity
            order["fee"] = fee_total
            order["status"] = "open" if order["remaining"] else "filled"
            if order["side"] == "buy" and not order["remaining"]:
                # Conservative limit sizing can leave more than whole-share
                # rounding after a better execution. Disclose that mismatch;
                # never top up with a newly timed, unregistered comparator buy.
                residual = sub(tranche["source_budget"], tranche["entry_spent"])
                next_share_cost = add(price, sub(commission_total(order["filled"] + 1, self._mode), fee_total))
                if residual >= next_share_cost:
                    self._block(order["source_fill_id"], "budget_mismatch_beyond_rounding", minute.at)
            order["reserved"] = add(mul(order["limit"], Decimal(order["remaining"])),
                max(ZERO, sub(commission_total(order["quantity"], self._mode), fee_total))) if order["side"] == "buy" and order["remaining"] else ZERO
            capacity -= quantity
            self._state["daily_used"][session.day] = add(self._state["daily_used"].get(session.day, ZERO), notional)
            fill = Fill(order["order_id"], order["source_fill_id"], "SYN-SPY", order["side"], quantity, price, fee,
                        minute.at, minute.settlement_session)
            self._state["fills"].append(fill)
            result.append(fill)
        return tuple(result)

    @_atomic
    def advance(self, at: datetime):
        """Only advance time and settle recorded receivables; never deposit funds."""
        self._tick(at)

    def mark_nav(self, mark: Decimal | None) -> Decimal | None:
        """Read-only whole-sleeve NAV including idle cash and sale receivables.

        This accepts an explicit raw synthetic mark; no quote is fetched or
        carried forward. An unavailable mark with any holding returns None.
        """
        if mark is not None:
            _money(mark, "comparator raw mark")
        quantity = sum(t["quantity"] for t in self._state["tranches"].values())
        if quantity and mark is None:
            return None
        return total((self._state["cash"], total(r["amount"] for r in self._state["receivables"]),
                      mul(Decimal(quantity), mark) if quantity else ZERO))

    @_atomic
    def close_session(self, session: date, mark: Decimal | None) -> dict:
        """Append a dated synthetic NAV observation, retaining calendar/mark gaps."""
        if type(session) is not date or session not in self._sessions:
            raise ComparisonError("known exact session date required")
        if mark is not None:
            _money(mark, "comparator raw close")
        prior = self._state["last_close"]
        if prior is not None and session <= prior:
            raise ComparisonError("comparator session already closed or out of order")
        first = self._days.index(prior) + 1 if prior is not None else 0
        missing = self._days[first:self._days.index(session)]
        self._state["missing_session_closes"].extend(missing)
        self._tick(self._sessions[session].closes_at)
        for missing_day in missing:
            self._block("SYN-CALENDAR", f"missing_daily_observation:{missing_day.isoformat()}", self._state["clock"])
        nav = self.mark_nav(mark)
        if nav is None:
            self._block("SYN-VALUATION", f"missing_mark:{session.isoformat()}", self._state["clock"])
        record = {"session": session, "nav": nav, "mark": mark,
                  "settled_cash": self._state["cash"],
                  "receivables": total(r["amount"] for r in self._state["receivables"]),
                  "quantity": sum(t["quantity"] for t in self._state["tranches"].values()),
                  "synthetic_only": True}
        self._state["last_close"] = session
        self._state["navs"].append(record)
        return record

    @property
    def fills(self):
        return deepcopy(tuple(self._state["fills"]))

    def snapshot(self):
        state = self._state
        pending = any(o["status"] == "open" for o in state["orders"].values())
        return _json(deepcopy({
            "schema": "gdr.synthetic_matched_comparator.v1", "synthetic_only": True,
            "market_evidence": False, "empirical_inference_permitted": False,
            "cloud_parity_verified": False, "execution_authorized": False,
            "mode": self._mode, "initial_cash": Decimal("100000"), "settled_cash": state["cash"],
            "reserved_cash": self._reserved(), "available_cash": sub(state["cash"], self._reserved()),
            "clock": state["clock"], "tranches": list(state["tranches"].values()),
            "orders": list(state["orders"].values()), "fills": [asdict(f) for f in state["fills"]],
            "receivables": state["receivables"], "permanent_parity_blockers": state["blockers"],
            "navs": state["navs"], "missing_session_closes": state["missing_session_closes"],
            "source_fill_count": len(state["source_receipts"]),
            "synthetic_schedule_parity_blocked": bool(state["blockers"] or pending),
            "study_completion_blocked": bool(pending or state["receivables"] or any(t["quantity"] for t in state["tranches"].values())
                                              or any(state["strategy_remaining"].values())
                                              or state["missing_session_closes"]
                                              or any(row["nav"] is None for row in state["navs"])),
            "limitations": ["No corporate-action adjustments", "No statistical inference",
                "One comparator entry order per source fill and exit order per affected tranche",
                "Only explicitly supplied synthetic sessions and settlement dates", "Whole-share rounding cash is retained"],
        }))
