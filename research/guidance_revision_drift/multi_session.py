"""Invented-only normalized multi-session order rehearsal; never native evidence.

Neutral identifiers do not turn the accepted SYN-only engine into a real-data
engine. This is a separate source epoch. It performs no I/O or provider calls,
accepts only an explicitly invented run class, and never grants evaluation or
order authority. Supplied calendars, receipts and action economics are claims.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from data.financial_primitives import (
    exact_decimal_add as add, exact_decimal_multiply as mul,
    exact_decimal_subtract as sub, exact_decimal_sum as total,
)
from data.hashing import hash_bytes
from research.guidance_revision_drift.contracts import Candidate
from research.guidance_revision_drift.execution_contract import ExecutionContract
from research.guidance_revision_drift.guidance_inputs import GuidanceLedger
from research.guidance_revision_drift.historical_market import HistoricalMarketBatch, instant_ns
from research.guidance_revision_drift.input_contracts import (
    InputError, amount, canonical_bytes, day, digest, identifier, keys, utc,
)
from research.guidance_revision_drift.order_planning import AccountSnapshot, plan_session
from research.guidance_revision_drift.research_reference import CalendarInput, ReferenceBook, NY, PROTECTED_FROM

ZERO = Decimal(0)
ACTIVE = {"open", "cancel_requested"}
PRIORITY = {"program_drawdown": 1, "position_stop": 2, "guidance_invalidation": 3,
            "time": 4, "trim": 5, "terminal_entitlement": 0}
_ACTION = {"action_id", "security_id", "kind", "effective_at", "received_at", "validated_at",
           "source_sha256", "ratio", "cash_per_share", "pay_date"}
_EXIT_WINDOW_UNRESOLVED = {"required_exit_outside_replay_window", "invalidation_exit_outside_replay_window"}


def _text(value):
    if type(value) is Decimal:
        return format(value, "f")
    if type(value) in (date, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if type(value) is dict:
        return {key: _text(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_text(item) for item in value]
    if type(value) is set:
        return sorted(value)
    return value


def _floor(left, right):
    an, ad = left.as_integer_ratio()
    bn, bd = right.as_integer_ratio()
    return an * bd // (ad * bn)


def _at(session_date, hour, minute=0):
    return datetime.combine(session_date, time(hour, minute), NY).astimezone(timezone.utc)


def _ns_clock(stamp):
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=stamp // 1000)


def _action(value):
    value = deepcopy(keys(value, _ACTION))
    for name in ("action_id", "security_id"):
        identifier(value[name])
    digest(value["source_sha256"])
    effective, received, validated = (utc(value[name]) for name in
                                      ("effective_at", "received_at", "validated_at"))
    if not received <= validated or max(effective, validated).astimezone(NY).date() >= PROTECTED_FROM:
        raise InputError("action clocks or protected action date refused")
    if type(value["kind"]) is not str or value["kind"] not in {"split", "dividend", "terminal_cash", "terminal_unresolved", "noncash_merger", "cvr"}:
        raise InputError("unknown normalized action kind")
    if value["kind"] == "split":
        amount(value["ratio"], positive=True)
        if value["cash_per_share"] is not None or value["pay_date"] is not None:
            raise InputError("split cash-in-lieu is not supported")
    elif value["kind"] in {"dividend", "terminal_cash"}:
        amount(value["cash_per_share"], nonnegative=True)
        if value["ratio"] is not None or day(value["pay_date"]) < effective.astimezone(NY).date():
            raise InputError("cash action payment or ratio refused")
    elif any(value[name] is not None for name in ("ratio", "cash_per_share", "pay_date")):
        raise InputError("unsupported action cannot assert guessed economics")
    if value["kind"] in {"split", "dividend"} and validated > effective:
        raise InputError("late split or dividend entitlement requires a separate reconciliation")
    return value


class MultiSessionReplay:
    """Bounded in-memory rehearsal with atomic sessions and duplicate receipts.

    A repeated step returns its original detached receipt, without replaying
    effects or rewinding a later state. This is not crash-safe persistence.
    """

    def __init__(self, candidate, calendar, references, guidance, market_batches, contract, *,
                 first_session, last_session, actions=(), data_class="invented_fixture", mode="base",
                 producing_source_sha256=None):
        if data_class != "invented_fixture" or type(data_class) is not str:
            raise InputError("this runner permits invented rehearsals only; no provider or empirical run")
        if type(candidate) is not Candidate or type(calendar) is not CalendarInput or type(references) is not ReferenceBook:
            raise InputError("exact replay candidate calendar and reference contracts required")
        if type(guidance) is not GuidanceLedger or type(contract) is not ExecutionContract:
            raise InputError("exact guidance and execution contracts required")
        if type(first_session) is not date or type(last_session) is not date or first_session > last_session:
            raise InputError("explicit ordered replay sessions required")
        if last_session >= PROTECTED_FROM or type(mode) is not str or mode not in {"base", "stress"}:
            raise InputError("protected replay dates or execution mode refused")
        if producing_source_sha256 is not None:
            digest(producing_source_sha256)
        self.candidate = Candidate(candidate.canonical_bytes)
        self.calendar = CalendarInput(calendar.canonical_bytes)
        self.references = ReferenceBook(references.canonical_bytes)
        self.guidance = GuidanceLedger(guidance.receipts)
        self.contract = ExecutionContract(contract.canonical_bytes)
        self.mode = mode
        first, last = self.calendar.index(first_session), self.calendar.index(last_session)
        self.days = tuple(item.session_date for item in self.calendar.sessions[first:last + 1])
        if not self.days or len(self.days) > 512:
            raise InputError("bounded nonempty multi-session replay window required")
        if type(market_batches) is not tuple or len(market_batches) > 20000 or type(actions) is not tuple or len(actions) > 1024:
            raise InputError("bounded immutable replay input inventories required")
        self.market, raw_bytes, spy_ids = {}, 0, set()
        for batch in market_batches:
            if type(batch) is not HistoricalMarketBatch:
                raise InputError("exact normalized market batch required")
            batch = HistoricalMarketBatch(batch.raw_bytes)
            raw_bytes += len(batch.raw_bytes)
            if raw_bytes > 64 * 1024 * 1024 or batch.session_date not in self.days:
                raise InputError("market input byte budget or replay date mismatch")
            session = self.calendar.sessions[self.calendar.index(batch.session_date)]
            if (batch.session_open_utc, batch.session_close_utc) != (session.open_utc, session.close_utc):
                raise InputError("market and pinned trading session differ")
            key = (batch.session_date, batch.security_id)
            if key in self.market and self.market[key].sha256 != batch.sha256:
                raise InputError("conflicting market batch identity")
            self.market[key] = batch
            if batch.role == "benchmark":
                spy_ids.add(batch.security_id)
        if len(spy_ids) != 1:
            raise InputError("one stable supplied SPY security identity required")
        self.spy = next(iter(spy_ids))
        self.actions = {}
        action_instants = {}
        for supplied in actions:
            value = _action(supplied)
            effective = utc(value["effective_at"])
            known = max(effective, utc(value["validated_at"]))
            if not first_session <= known.astimezone(NY).date() <= last_session:
                raise InputError("action outside explicit replay window")
            if value["kind"] in {"split", "dividend"}:
                session = self.calendar.sessions[self.calendar.index(effective.astimezone(NY).date())]
                if effective != session.open_utc:
                    raise InputError("split or dividend requires explicit ex-session open")
            if value["pay_date"] is not None and value["pay_date"] not in self.contract.to_dict()["settlement_business_days"]:
                raise InputError("cash payment date absent from supplied service-day inventory")
            previous = self.actions.get(value["action_id"])
            if previous is not None and previous != value:
                raise InputError("conflicting normalized action replay")
            instant_key = (value["security_id"], effective)
            if instant_key in action_instants and action_instants[instant_key] != value["action_id"]:
                raise InputError("same-security simultaneous actions require an explicit share-basis ordering contract")
            action_instants[instant_key] = value["action_id"]
            self.actions[value["action_id"]] = value
        self.lineage = {"candidate_sha256": self.candidate.sha256, "calendar_sha256": self.calendar.sha256,
            "reference_sha256": self.references.sha256, "guidance_head_sha256": self.guidance.head_sha256,
            "execution_contract_sha256": self.contract.sha256, "producing_source_sha256": producing_source_sha256,
            "market_sha256s": {d.isoformat() + ":" + security: batch.sha256 for (d, security), batch in sorted(self.market.items())},
            "action_sha256s": {key: hash_bytes(canonical_bytes(value)) for key, value in sorted(self.actions.items())},
            "first_session": first_session.isoformat(), "last_session": last_session.isoformat(),
            "data_class": data_class, "mode": mode, "spy_security_id": self.spy}
        self.input_sha256 = hash_bytes(canonical_bytes(self.lineage))
        self._bound_lineage = canonical_bytes(self.lineage)
        self._state = {"clock": None, "cash": {"strategy": Decimal("100000"), "comparator": Decimal("100000")},
            "orders": {}, "positions": {}, "tranches": {}, "receivables": [], "fills": [],
            "refusals": [], "parity": [], "unresolved": {}, "attempted": set(), "minutes": {},
            "daily_used": {}, "due": {}, "stopped": False, "high_water": Decimal("100000"),
            "daily_nav": [], "actions": {}, "cash_movements": [], "terminal": set()}
        self._receipts = {}
        self._reference_cache = {}

    def _verify_inputs(self):
        expected_days = tuple(item.session_date for item in self.calendar.sessions[
            self.calendar.index(self.days[0]):self.calendar.index(self.days[-1]) + 1])
        if self.days != expected_days:
            raise InputError("replay session inventory changed after binding")
        current = {"candidate_sha256": Candidate(self.candidate.canonical_bytes).sha256,
            "calendar_sha256": CalendarInput(self.calendar.canonical_bytes).sha256,
            "reference_sha256": ReferenceBook(self.references.canonical_bytes).sha256,
            "guidance_head_sha256": GuidanceLedger(self.guidance.receipts).head_sha256,
            "execution_contract_sha256": ExecutionContract(self.contract.canonical_bytes).sha256,
            "producing_source_sha256": self.lineage["producing_source_sha256"],
            "market_sha256s": {d.isoformat() + ":" + security: HistoricalMarketBatch(batch.raw_bytes).sha256
                for (d, security), batch in sorted(self.market.items())},
            "action_sha256s": {key: hash_bytes(canonical_bytes(_action(value))) for key, value in sorted(self.actions.items())},
            "first_session": self.days[0].isoformat(), "last_session": self.days[-1].isoformat(),
            "data_class": "invented_fixture", "mode": self.mode, "spy_security_id": self.spy}
        if canonical_bytes(current) != self._bound_lineage or canonical_bytes(self.lineage) != self._bound_lineage:
            raise InputError("replay inputs changed after their retained binding")

    def _refuse(self, reason, at, reference=None, *, parity=False):
        row = {"reason": reason, "at": _text(at), "reference": reference}
        self._state["parity" if parity else "refusals"].append(row)

    def _advance(self, at):
        state = self._state
        if state["clock"] is not None and at < state["clock"]:
            raise InputError("replay operations must be chronological")
        state["clock"] = at
        local_day = at.astimezone(NY).date()
        payable = []
        for row in state["receivables"]:
            if row["pay_date"] <= local_day and at >= _at(local_day, 9, 30):
                state["cash"][row["sleeve"]] = add(state["cash"][row["sleeve"]], row["amount"])
                state["cash_movements"].append({"kind": "settlement", "at": at, **row})
            else:
                payable.append(row)
        state["receivables"] = payable

    def _active(self, sleeve=None, security=None, side=None):
        return [row for row in self._state["orders"].values() if row["status"] in ACTIVE
                and (sleeve is None or row["sleeve"] == sleeve)
                and (security is None or row["security_id"] == security)
                and (side is None or row["side"] == side)]

    def _reserved(self, sleeve):
        return total(add(row["reserved_notional"], row["reserved_fee"])
                     for row in self._active(sleeve, side="buy"))

    def _quote(self, security, at, *, entry=False):
        batch = self.market.get((at.astimezone(NY).date(), security))
        if batch is None:
            raise InputError("missing supplied market batch")
        reference = self._reference_fields(security, at.astimezone(NY).date())
        if batch.symbol != reference["symbol"] or batch.role != ("benchmark" if security == self.spy else "stock"):
            raise InputError("market symbol or role differs from current dated identity")
        return batch._latest(at, entry_spread=entry)

    def _reference_fields(self, security, session_date):
        key = (security, session_date)
        if key not in self._reference_cache:
            cutoff = self.calendar.cutoff(session_date)
            rows = [row for row in self.references.to_dict()["references"] if row["security_id"] == security
                and day(row["valid_from"]) <= session_date <= day(row["valid_through"])
                and utc(row["published_at"]) < cutoff and utc(row["validated_at"]) <= cutoff]
            if len(rows) != 1:
                raise InputError("missing or ambiguous current dated identity")
            row = rows[0]
            if row["status"] != "listed" or row["instrument_type"] != ("ETF" if security == self.spy else "COMMON_STOCK"):
                raise InputError("untradeable or unsupported dated security identity")
            if security == self.spy and row["symbol"] != "SPY":
                raise InputError("dated benchmark is not SPY")
            self._reference_cache[key] = deepcopy(row)
        return deepcopy(self._reference_cache[key])

    def _liquidity(self, security, session_date):
        result = self.references.eligibility(self.calendar, security, session_date,
                                             role="benchmark" if security == self.spy else "stock")
        if result["adv20"] is None or amount(result["adv20"]) <= 0:
            raise InputError("missing exit liquidity history")
        return amount(result["adv20"])

    def _order(self, sleeve, security, side, quantity, at, adv20, *, limit=None, issuer=None,
               sector=None, event=None, tranche=None, reason=None):
        if type(quantity) is not int or not 1 <= quantity <= 10**12:
            raise InputError("bounded replay whole-share quantity required")
        sequence = len(self._state["orders"]) + 1
        key = "OFFLINE-ORDER-" + str(sequence)
        row = {"order_id": key, "sequence": sequence, "sleeve": sleeve, "security_id": security, "issuer_id": issuer,
            "sector": sector, "side": side, "quantity": quantity, "remaining": quantity,
            "filled_quantity": 0, "fees_paid": ZERO, "submitted_at": at, "execution_after": at,
            "session_date": at.astimezone(NY).date(), "adv20": adv20, "limit": limit,
            "status": "open", "event_sha256": event, "tranche_id": tranche, "exit_reason": reason,
            "reserved_notional": mul(limit, Decimal(quantity)) if side == "buy" else ZERO,
            "reserved_fee": self.contract.commission(quantity, self.mode) if side == "buy" else ZERO}
        if sleeve == "comparator":
            row["issuer_id"] = self._reference_fields(self.spy, at.astimezone(NY).date())["issuer_id"]
        if side == "buy" and add(row["reserved_notional"], row["reserved_fee"]) > sub(self._state["cash"][sleeve], self._reserved(sleeve)):
            raise InputError("replay order exceeds settled cash after reservations")
        self._state["orders"][key] = row
        return row

    def _cancel(self, order, at):
        if order["status"] == "open":
            order["status"], order["cancel_requested_at"] = "cancel_requested", at

    def _acknowledge(self, at):
        for row in self._active():
            if row["status"] == "cancel_requested" and row["cancel_requested_at"] <= at:
                row.update(status="cancelled", cancel_acknowledged_at=at,
                           reserved_notional=ZERO, reserved_fee=ZERO)

    def _schedule(self, security, when, reason, quantity):
        requests = self._state["due"].setdefault(security, {})
        old = requests.get(reason)
        if old is None:
            requests[reason] = {"session": when, "quantity": quantity}
        else:
            old["session"], old["quantity"] = min(old["session"], when), max(old["quantity"], quantity)

    def _invalidation(self, at):
        active = {item.current_sha256 for item in self.guidance.as_of(_text(at)).active_comparisons}
        for order in self._active("strategy", side="buy"):
            if order["event_sha256"] not in active:
                self._cancel(order, at)
        for security, position in self._state["positions"].items():
            if position["event_sha256"] not in active and security not in self._state["terminal"]:
                future = [d for d in self.days if _at(d, 10) >= at and self.calendar.cutoff(d) >= at]
                if future:
                    self._schedule(security, future[0], "guidance_invalidation", position["quantity"])
                else:
                    self._state["unresolved"].setdefault(security, "invalidation_exit_outside_replay_window")

    def _submit_exits(self, at):
        today = at.astimezone(NY).date()
        for security, requests in sorted(tuple(self._state["due"].items())):
            due = {reason: row for reason, row in requests.items() if row["session"] <= today}
            if not due or security not in self._state["positions"]:
                continue
            reason = min(due, key=lambda item: PRIORITY[item])
            position = self._state["positions"][security]
            if security in self._state["terminal"]:
                continue
            try:
                reference = self._reference_fields(security, today)
                if reference["issuer_id"] != position["issuer_id"]:
                    raise InputError("held issuer changed across dated reference")
                position["sector"], position["symbol"] = reference["sector"], reference["symbol"]
                liquidity = self._liquidity(security, today)
            except InputError:
                self._refuse("missing_exit_liquidity", at, security)
                continue
            pending = self._active("strategy", security, "sell")
            if self._active("strategy", security, "buy"):
                self._refuse("reconcile_entry_before_risk_reduction", at, security)
                continue
            quantity = min(position["quantity"], max(row["quantity"] for row in due.values()))
            if pending:
                order = pending[0]
                order.update(remaining=max(order["remaining"], quantity), execution_after=at,
                    session_date=today, adv20=liquidity, exit_reason=reason)
                order["quantity"] = order["filled_quantity"] + order["remaining"]
            else:
                self._order("strategy", security, "sell", quantity, at, liquidity,
                    issuer=position["issuer_id"], sector=position["sector"], reason=reason)
        # Cash-terminal entitlements have their own explicit proposed schedule,
        # not a fabricated strategy trade or payout to the comparator sleeve.
        for tranche in self._state["tranches"].values():
            if tranche.get("terminal_unwind_at") == at and tranche["quantity"]:
                self._spy_exit(tranche, tranche["quantity"], at, "terminal_entitlement")
        for order in self._active("comparator", side="sell"):
            if order["session_date"] < today:
                try:
                    order.update(session_date=today, execution_after=at, adv20=self._liquidity(self.spy, today))
                except InputError:
                    self._refuse("comparator_carried_exit_liquidity_refused", at, order["tranche_id"], parity=True)

    def _entries(self, at):
        today = at.astimezone(NY).date()
        if self.calendar.index(today) == 0:
            return
        positions = []
        missing = False
        for security, position in self._state["positions"].items():
            try:
                reference = self._reference_fields(security, today)
                if reference["issuer_id"] != position["issuer_id"]:
                    raise InputError("held issuer differs from current dated identity")
                position["sector"], position["symbol"] = reference["sector"], reference["symbol"]
                if position["sector"] is None:
                    raise InputError("missing dated sector blocks new exposure")
                quote = self._quote(security, at)
                mark = mul(add(quote.bid, quote.ask), Decimal("0.5"))
                positions.append({"security_id": security, "issuer_id": position["issuer_id"],
                    "sector": position["sector"], "quantity": position["quantity"], "raw_mark": _text(mark),
                    "mark_at": _text(at), "source_sha256": quote.source_sha256})
            except InputError:
                missing = True
        if missing:
            self._refuse("missing_current_portfolio_valuation_blocks_entries", at)
            return
        prior = self._state["daily_nav"][-1] if self._state["daily_nav"] else None
        controls = {"program_stop_active": self._state["stopped"],
            "exits_or_trims_pending": bool(self._state["due"] or self._active("strategy", side="sell")),
            "unresolved_actions": bool(self._state["unresolved"] or self.spy in self._state["terminal"]),
            "unresolved_valuations": bool((positions and prior is None) or (prior is not None and
                (prior["strategy_nav"] is None or prior["comparator_nav"] is None)))}
        account = AccountSnapshot.from_dict({"schema": "gdr.offline-account-snapshot.v1",
            "source_sha256": self.input_sha256, "at": _text(at), "settled_cash": _text(self._state["cash"]["strategy"]),
            "positions": positions, "pending_buys": [{"order_id": row["order_id"], "issuer_id": row["issuer_id"],
                "sector": row["sector"], "reserved_notional": _text(row["reserved_notional"]), "reserved_fee": _text(row["reserved_fee"])}
                for row in self._active("strategy", side="buy")],
            "receivables": [{"amount": _text(row["amount"]), "settlement_session": _text(row["pay_date"])}
                for row in self._state["receivables"] if row["sleeve"] == "strategy"],
            "attempted_event_sha256s": sorted(self._state["attempted"]), "entry_controls": controls})
        batches = tuple(batch for (d, _), batch in sorted(self.market.items()) if d == today)
        plan = plan_session(self.candidate, self.calendar, self.references, self.guidance, batches, account, today, mode=self.mode)
        documents = {receipt.document.sha256: receipt.document for receipt in self.guidance.receipts}
        for row in sorted(plan["candidates"], key=lambda item: (item["priority_rank"] is None, item["priority_rank"] or 0, item["security_id"])):
            event, security = row["event_sha256"], row["security_id"]
            window = self.calendar.entry_window(utc(documents[event].to_dict()["published_at"]))
            eligible = self.references.eligibility(self.calendar, security, today)["eligible"]
            if today in window and eligible:
                self._state["attempted"].add(event)
            if row["intent"] is None:
                for reason in row["reasons"]:
                    self._refuse(reason, at, event)
                continue
            if security in self._state["terminal"]:
                self._refuse("terminal_security_cannot_reopen", at, event)
                continue
            intent = row["intent"]
            self._order("strategy", security, "buy", intent["whole_shares"], at,
                amount(self.references.eligibility(self.calendar, security, today)["adv20"]),
                limit=amount(intent["limit_price"]), issuer=row["issuer_id"], sector=intent["sector"], event=event)

    def _spy_entry(self, fill, at):
        key = fill["fill_id"]
        budget = add(mul(Decimal(fill["quantity"]), fill["price"]), fill["fee"])
        tranche = {"tranche_id": key, "source_security_id": fill["security_id"], "quantity": 0,
                   "source_budget": budget, "entry_spent": ZERO}
        self._state["tranches"][key] = tranche
        try:
            if self.spy in self._state["terminal"] or self.spy in self._state["unresolved"]:
                raise InputError("terminal comparator cannot receive new exposure")
            quote = self._quote(self.spy, at, entry=True)
            liquidity = self._liquidity(self.spy, at.astimezone(NY).date())
            available = sub(self._state["cash"]["comparator"], self._reserved("comparator"))
            allocated = min(budget, available)
            limit = mul(quote.ask, Decimal("1.01"))
            lo, hi = 0, max(0, min(10**12, _floor(allocated, limit)))
            while lo < hi:
                middle = (lo + hi + 1) // 2
                if add(mul(Decimal(middle), limit), self.contract.commission(middle, self.mode)) <= allocated:
                    lo = middle
                else:
                    hi = middle - 1
            quantity = lo
            if allocated < budget:
                self._refuse("comparator_funding_mismatch", at, key, parity=True)
            if quantity:
                self._order("comparator", self.spy, "buy", quantity, at, liquidity,
                            limit=limit, tranche=key)
            else:
                self._refuse("comparator_rounded_to_zero", at, key, parity=True)
        except InputError:
            self._refuse("comparator_entry_market_input_refused", at, key, parity=True)

    def _spy_exit(self, tranche, quantity, at, reason):
        pending = sum(row["remaining"] for row in self._active("comparator", self.spy, "sell")
                      if row["tranche_id"] == tranche["tranche_id"])
        quantity = min(quantity, tranche["quantity"] - pending)
        if quantity <= 0:
            return
        try:
            self._order("comparator", self.spy, "sell", quantity, at,
                        self._liquidity(self.spy, at.astimezone(NY).date()),
                        tranche=tranche["tranche_id"], reason=reason)
        except InputError:
            self._refuse("comparator_exit_liquidity_refused", at, tranche["tranche_id"], parity=True)

    def _source_exit(self, fill, held_before, at):
        for tranche in self._state["tranches"].values():
            if tranche["source_security_id"] != fill["security_id"]:
                continue
            for order in self._active("comparator", side="buy"):
                if order["tranche_id"] == tranche["tranche_id"]:
                    self._cancel(order, at)
                    self._refuse("comparator_entry_unmatched_at_source_exit", at, tranche["tranche_id"], parity=True)
            pending = sum(row["remaining"] for row in self._active("comparator", side="sell")
                          if row["tranche_id"] == tranche["tranche_id"])
            available = tranche["quantity"] - pending
            quantity = available if fill["quantity"] == held_before else available * fill["quantity"] // held_before
            self._spy_exit(tranche, quantity, at, fill["exit_reason"])

    def _fill_orders(self, sleeve, at):
        today = at.astimezone(NY).date()
        by_security = {}
        for order in self._active(sleeve):
            if order["session_date"] == today and order["execution_after"] < at:
                by_security.setdefault(order["security_id"], []).append(order)
        for security, orders in sorted(by_security.items()):
            if security in self._state["terminal"] or security in self._state["unresolved"]:
                self._refuse("terminal_or_unreconciled_action_blocks_execution", at, security,
                             parity=sleeve == "comparator")
                continue
            batch = self.market.get((today, security))
            if batch is None:
                self._refuse("missing_execution_market_input", at, security, parity=sleeve == "comparator")
                continue
            capacity = None
            for order in sorted(orders, key=lambda row: (row["side"] != "sell", row["submitted_at"], row["sequence"])):
                if sleeve == "comparator" and order["side"] == "buy" and self._state["tranches"][order["tranche_id"]]["source_security_id"] in self._state["terminal"]:
                    self._cancel(order, at)
                    self._refuse("source_terminal_cancels_unmatched_comparator_entry", at, order["tranche_id"], parity=True)
                    continue
                try:
                    reference = self._reference_fields(security, today)
                    if (batch.symbol != reference["symbol"] or batch.role != ("benchmark" if sleeve == "comparator" else "stock")
                            or reference["issuer_id"] != order["issuer_id"]):
                        raise InputError("execution source differs from current dated identity")
                    sample = batch.subsequent_minute(submitted_at=order["execution_after"], callback_at=at)
                    settlement = self.contract.settlement_on(self.calendar, today)
                except InputError:
                    self._refuse("subsequent_quote_minute_or_settlement_refused", at, order["order_id"], parity=sleeve == "comparator")
                    continue
                capacity = sample.minute.volume // 100 if capacity is None else capacity
                key = sleeve + "|" + security + "|" + today.isoformat()
                daily_left = max(ZERO, sub(mul(order["adv20"], Decimal("0.001")), self._state["daily_used"].get(key, ZERO)))
                impact = amount(self.contract.to_dict()["execution_costs"][self.mode + "_impact_fraction"])
                price = mul(sample.quote.ask if order["side"] == "buy" else sample.quote.bid,
                            add(Decimal(1), impact) if order["side"] == "buy" else sub(Decimal(1), impact))
                quantity = min(order["remaining"], capacity, max(0, _floor(daily_left, price)))
                if order["limit"] is not None and price > order["limit"]:
                    quantity = 0
                if sleeve == "comparator" and quantity < order["remaining"]:
                    self._refuse("comparator_partial_or_unmatched_execution", at, order["tranche_id"], parity=True)
                if not quantity:
                    continue
                if sleeve == "comparator" and not order["filled_quantity"] and at != order["submitted_at"] + timedelta(minutes=1):
                    self._refuse("comparator_timing_mismatch", at, order["tranche_id"], parity=True)
                fee_total = self.contract.commission(order["filled_quantity"] + quantity, self.mode)
                fee = sub(fee_total, order["fees_paid"])
                notional = mul(price, Decimal(quantity))
                held_before = 0
                if sleeve == "strategy":
                    held = self._state["positions"].get(security)
                    held_before = held["quantity"] if held else 0
                    if order["side"] == "buy":
                        if held is None:
                            held = {"security_id": security, "issuer_id": order["issuer_id"], "sector": order["sector"],
                                "entry_sector": order["sector"], "entry_symbol": batch.symbol, "symbol": batch.symbol,
                                "quantity": 0, "entry_notional": ZERO, "reference_quantity": ZERO,
                                "entry_session": today, "event_sha256": order["event_sha256"]}
                            self._state["positions"][security] = held
                        held["quantity"] += quantity
                        held["reference_quantity"] = add(held["reference_quantity"], Decimal(quantity))
                        held["entry_notional"] = add(held["entry_notional"], notional)
                    else:
                        if held is None or quantity > held["quantity"]:
                            raise InputError("strategy sale exceeds held quantity")
                        held["quantity"] -= quantity
                        if held["quantity"] == 0:
                            del self._state["positions"][security]
                            self._state["due"].pop(security, None)
                        elif security in self._state["due"]:
                            for reason, request in tuple(self._state["due"][security].items()):
                                request["quantity"] = max(0, request["quantity"] - quantity)
                                if not request["quantity"]:
                                    del self._state["due"][security][reason]
                            if not self._state["due"][security]:
                                del self._state["due"][security]
                else:
                    tranche = self._state["tranches"][order["tranche_id"]]
                    tranche["quantity"] += quantity if order["side"] == "buy" else -quantity
                    if tranche["quantity"] < 0:
                        raise InputError("comparator sale exceeds tranche quantity")
                    if order["side"] == "buy":
                        tranche["entry_spent"] = add(tranche["entry_spent"], add(notional, fee))
                if order["side"] == "buy":
                    self._state["cash"][sleeve] = sub(self._state["cash"][sleeve], add(notional, fee))
                else:
                    self._state["cash"][sleeve] = sub(self._state["cash"][sleeve], max(ZERO, sub(fee, notional)))
                    self._state["receivables"].append({"receipt_id": order["order_id"] + ":" + str(order["filled_quantity"] + quantity),
                        "sleeve": sleeve, "amount": max(ZERO, sub(notional, fee)), "pay_date": settlement, "kind": "sale"})
                order["filled_quantity"] += quantity
                order["remaining"] -= quantity
                order.update(fees_paid=fee_total, status="filled" if not order["remaining"] else order["status"],
                    reserved_notional=mul(order["limit"], Decimal(order["remaining"])) if order["side"] == "buy" else ZERO,
                    reserved_fee=max(ZERO, sub(self.contract.commission(order["quantity"], self.mode), fee_total))
                        if order["side"] == "buy" and order["remaining"] else ZERO)
                self._state["daily_used"][key] = add(self._state["daily_used"].get(key, ZERO), notional)
                capacity -= quantity
                fill = {"fill_id": order["order_id"] + ":" + str(order["filled_quantity"]),
                    "order_id": order["order_id"], "sleeve": sleeve, "security_id": security,
                    "side": order["side"], "quantity": quantity, "price": price, "fee": fee,
                    "at": at, "settlement_date": settlement, "exit_reason": order["exit_reason"],
                    "market_source_sha256": batch.sha256, "quote_sip_ns": sample.quote.sip_timestamp_ns,
                    "minute_start_ns": sample.minute.start_timestamp_ns, "minute_end_ns": sample.minute.end_timestamp_ns}
                self._state["fills"].append(fill)
                self._state["cash_movements"].append({"kind": "fill", "fill_id": fill["fill_id"], "sleeve": sleeve,
                    "at": at, "cash_after": self._state["cash"][sleeve]})
                if sleeve == "strategy":
                    if order["side"] == "buy":
                        # A fill racing a known cancellation remains a real
                        # modeled holding; its entire enlarged quantity must
                        # enter the already-known invalidation exit schedule.
                        self._invalidation(at)
                        self._spy_entry(fill, at)
                    else:
                        self._source_exit(fill, held_before, at)
                elif order["side"] == "buy" and not order["remaining"]:
                    residual = sub(tranche["source_budget"], tranche["entry_spent"])
                    if residual >= add(price, sub(self.contract.commission(order["filled_quantity"] + 1, self.mode), fee_total)):
                        self._refuse("comparator_budget_mismatch_beyond_rounding", at, order["tranche_id"], parity=True)

    def _apply_action(self, value, at):
        key, security, kind = value["action_id"], value["security_id"], value["kind"]
        if key in self._state["actions"]:
            return
        self._state["actions"][key] = hash_bytes(canonical_bytes(value))
        held = self._state["positions"].get(security)
        tranches = [row for row in self._state["tranches"].values()
                    if security == self.spy or row["source_security_id"] == security]
        effective = utc(value["effective_at"])
        if kind == "terminal_cash" and effective < at:
            self._refuse("late_known_terminal_comparator_timing_mismatch", at, key, parity=True)
        intervening_fill = any(row["security_id"] == security and effective < row["at"] <= at for row in self._state["fills"])
        intervening_action = any(other != key and other in self._state["actions"] and row["security_id"] == security
            and effective < utc(row["effective_at"]) <= at for other, row in self.actions.items())
        if effective < at and (intervening_fill or intervening_action):
            self._state["unresolved"][security] = "late_terminal_entitlement_changed_after_effective_time"
            self._state["terminal"].add(security)
            for order in self._active(security=security):
                self._cancel(order, at)
            self._refuse("late_terminal_entitlement_requires_reconciliation", at, key)
            return
        # Only an exit beyond this rehearsal's boundary becomes moot after a
        # verified payout. Unknown share or action economics need explicit
        # reconciliation; a later action cannot make the old share basis true.
        unresolved = self._state["unresolved"].get(security)
        uncertain_economics = unresolved is not None and unresolved not in _EXIT_WINDOW_UNRESOLVED
        if kind in {"split", "dividend"} and uncertain_economics:
            self._refuse("unresolved_action_economics_requires_reconciliation", at, key, parity=True)
            return
        if kind in {"noncash_merger", "cvr", "terminal_unresolved"} or (kind == "terminal_cash" and uncertain_economics):
            self._state["terminal"].add(security)
            if held or (security == self.spy and any(row["quantity"] for row in tranches)):
                self._state["unresolved"][security] = "unsupported_or_unresolved_terminal_economics"
            for order in self._active(security=security):
                self._cancel(order, at)
            for order in self._active("comparator", side="buy"):
                if self._state["tranches"][order["tranche_id"]] in tranches:
                    self._cancel(order, at)
            self._refuse("unsupported_or_unresolved_terminal_economics", at, key)
            if held or any(row["quantity"] for row in tranches):
                self._refuse("unsupported_terminal_comparison_schedule", at, key, parity=True)
            return
        if kind == "split":
            if self._active(security=security):
                self._state["unresolved"][security] = "split_requires_reconciled_orders"
                return
            ratio = amount(value["ratio"])
            affected = tranches if security == self.spy else ([held] if held else [])
            quantities = [mul(Decimal(row["quantity"]), ratio) for row in affected]
            if security in self._state["due"]:
                quantities.extend(mul(Decimal(row["quantity"]), ratio) for row in self._state["due"][security].values())
            if any(shares != Decimal(_floor(shares, Decimal(1))) or shares > Decimal(10**12) for shares in quantities):
                self._state["unresolved"][security] = "fractional_split_cash_in_lieu_unsupported"
                return
            for row in affected:
                row["quantity"] = int(mul(Decimal(row["quantity"]), ratio))
                if "reference_quantity" in row:
                    row["reference_quantity"] = mul(row["reference_quantity"], ratio)
            if security in self._state["due"]:
                for request in self._state["due"][security].values():
                    request["quantity"] = int(mul(Decimal(request["quantity"]), ratio))
            return
        quantity = sum(row["quantity"] for row in tranches) if security == self.spy else (held["quantity"] if held else 0)
        if quantity:
            pay = day(value["pay_date"])
            self._state["receivables"].append({"receipt_id": key, "sleeve": "comparator" if security == self.spy else "strategy",
                "amount": mul(Decimal(quantity), amount(value["cash_per_share"])), "pay_date": pay, "kind": kind})
        if kind == "terminal_cash":
            self._state["terminal"].add(security)
            self._state["unresolved"].pop(security, None)
            for order in self._active(security=security):
                self._cancel(order, at)
            for order in self._active("comparator", side="buy"):
                if self._state["tranches"][order["tranche_id"]] in tranches:
                    self._cancel(order, at)
                    self._refuse("source_terminal_cancels_unmatched_comparator_entry", at, order["tranche_id"], parity=True)
            if security == self.spy:
                for tranche in tranches:
                    tranche["quantity"] = 0
                self._refuse("comparator_terminal_ends_matched_schedule", at, key, parity=True)
            else:
                self._state["positions"].pop(security, None)
                self._state["due"].pop(security, None)
                unwind = self.contract.terminal_spy_unwind_at(self.calendar, at)
                for tranche in tranches:
                    tranche["terminal_unwind_at"] = unwind

    def _mark(self, security, session, at):
        unresolved = self._state["unresolved"].get(security)
        if unresolved is not None and unresolved not in _EXIT_WINDOW_UNRESOLVED:
            return None
        rows = [row for row in self.references.to_dict()["daily_bars"] if row["security_id"] == security
                and day(row["session_date"]) == session and utc(row["published_at"]) <= at
                and utc(row["published_at"]) >= self.calendar.sessions[self.calendar.index(session)].close_utc
                and utc(row["validated_at"]) <= at]
        if len(rows) != 1 or rows[0]["raw_close"] is None or amount(rows[0]["raw_close"]) <= 0:
            return None
        return amount(rows[0]["raw_close"])

    def _close(self, session, at):
        positions = self._state["positions"]
        for security, position in positions.items():
            try:
                reference = self._reference_fields(security, session)
                if reference["issuer_id"] != position["issuer_id"]:
                    raise InputError("changed held issuer")
                position["sector"], position["symbol"] = reference["sector"], reference["symbol"]
            except InputError:
                position["sector"] = None
                self._refuse("held_dated_identity_unavailable_for_close", at, security)
        marks = {security: self._mark(security, session, at) for security in positions}
        spy_quantity = sum(row["quantity"] for row in self._state["tranches"].values())
        spy_mark = self._mark(self.spy, session, at) if spy_quantity else ZERO
        receivables = lambda sleeve: total(row["amount"] for row in self._state["receivables"] if row["sleeve"] == sleeve)
        nav = None if any(value is None for value in marks.values()) else total((self._state["cash"]["strategy"], receivables("strategy"),
            total(mul(marks[security], Decimal(position["quantity"])) for security, position in positions.items())))
        comparator_nav = None if spy_mark is None else total((self._state["cash"]["comparator"], receivables("comparator"), mul(Decimal(spy_quantity), spy_mark)))
        if nav is None or comparator_nav is None:
            self._refuse("missing_daily_valuation", at, session.isoformat(), parity=True)
        self._state["daily_nav"].append({"session_date": session, "observed_at": at,
            "strategy_nav": nav, "comparator_nav": comparator_nav,
            "strategy_settled_cash": self._state["cash"]["strategy"], "strategy_receivables": receivables("strategy"),
            "comparator_settled_cash": self._state["cash"]["comparator"], "comparator_receivables": receivables("comparator")})
        for order in self._active("comparator", side="buy"):
            self._cancel(order, at)
            self._refuse("comparator_unfilled_remainder_at_close", at, order["tranche_id"], parity=True)
        self._acknowledge(at)
        next_index = self.calendar.index(session) + 1
        future = self.calendar.sessions[next_index].session_date if next_index < len(self.calendar.sessions) else None
        if nav is not None:
            self._state["high_water"] = max(nav, self._state["high_water"])
            if nav <= mul(self._state["high_water"], Decimal("0.85")):
                self._state["stopped"] = True
        gross_room, sectors = mul(nav, Decimal("0.5")) if nav is not None else ZERO, {}
        for security, position in sorted(positions.items()):
            mark, reason, quantity = marks[security], None, position["quantity"]
            if self._state["stopped"]:
                reason = "program_drawdown"
            elif mark is not None and mul(mark, position["reference_quantity"]) <= mul(position["entry_notional"], Decimal("0.9")):
                reason = "position_stop"
            elif self.calendar.index(session) + 1 >= self.calendar.index(position["entry_session"]) + 20:
                reason = "time"
            elif nav is not None and mark is not None:
                if position["sector"] is None:
                    self._refuse("missing_dated_sector_blocks_rebalance", at, security)
                    continue
                room = sectors.get(position["sector"], mul(nav, Decimal("0.15")))
                target = max(ZERO, min(mul(nav, Decimal("0.05")), room, gross_room))
                retain = min(position["quantity"], _floor(target, mark))
                sectors[position["sector"]] = sub(room, mul(mark, Decimal(retain)))
                gross_room = sub(gross_room, mul(mark, Decimal(retain)))
                if retain < quantity:
                    reason, quantity = "trim", quantity - retain
            if reason:
                if future is None or future not in self.days:
                    self._state["unresolved"].setdefault(security, "required_exit_outside_replay_window")
                else:
                    self._schedule(security, future, reason, quantity)

    def step_session(self, session_date):
        self._verify_inputs()
        if type(session_date) is not date or session_date not in self.days:
            raise InputError("explicit replay session required")
        if session_date in self._receipts:
            return deepcopy(self._receipts[session_date])
        if session_date != self.days[len(self._receipts)]:
            raise InputError("replay sessions must be processed without omissions")
        before = deepcopy(self._state)
        try:
            session = self.calendar.sessions[self.calendar.index(session_date)]
            callbacks = set()
            for (d, _), batch in self.market.items():
                if d == session_date:
                    callbacks.update(_ns_clock(row["end_timestamp_ns"]) for row in batch.projection()["minutes"])
            close_observation = _at(session_date, 18)
            clock_events = {session.open_utc, _at(session_date, 10), _at(session_date, 10, 5), close_observation} | callbacks
            clock_events.update(utc(row.validated_at) for row in self.guidance.receipts
                if (before["clock"] is None or utc(row.validated_at) > before["clock"]) and utc(row.validated_at) <= close_observation)
            clock_events.update(max(utc(row["effective_at"]), utc(row["validated_at"])) for row in self.actions.values()
                if (before["clock"] is None or max(utc(row["effective_at"]), utc(row["validated_at"])) > before["clock"])
                and max(utc(row["effective_at"]), utc(row["validated_at"])) <= close_observation)
            for at in sorted(clock_events):
                self._advance(at)
                self._invalidation(at)
                for _, value in sorted(self.actions.items()):
                    if max(utc(value["effective_at"]), utc(value["validated_at"])) == at:
                        self._apply_action(value, at)
                if at == _at(session_date, 10):
                    self._submit_exits(at)
                    self._entries(at)
                if at == _at(session_date, 10, 5):
                    for order in self._active("strategy", side="buy"):
                        self._cancel(order, at)
                if at in callbacks:
                    # Older SPY orders execute before this callback can create
                    # new tranches. Same-callback fills are never permitted.
                    self._fill_orders("comparator", at)
                    self._fill_orders("strategy", at)
                self._acknowledge(at)
                if at == close_observation:
                    self._close(session_date, at)
                for sleeve in ("strategy", "comparator"):
                    if self._state["cash"][sleeve] < 0 or self._reserved(sleeve) > self._state["cash"][sleeve]:
                        raise InputError("replay cash or reservation invariant failed")
            report = {"session_date": session_date.isoformat(), "input_sha256": self.input_sha256,
                      "state_sha256": hash_bytes(canonical_bytes(_text(self._state)))}
            self._receipts[session_date] = report
            return deepcopy(report)
        except Exception:
            self._state = before
            raise

    def snapshot(self):
        self._verify_inputs()
        state = deepcopy(self._state)
        complete = (len(self._receipts) == len(self.days) and not state["positions"]
            and not any(row["quantity"] for row in state["tranches"].values())
            and not self._active() and not state["receivables"] and not state["unresolved"]
            and all(row["strategy_nav"] is not None and row["comparator_nav"] is not None for row in state["daily_nav"]))
        sleeve = lambda name: {"settled_cash": state["cash"][name], "reserved_cash": self._reserved(name),
            "orders": [row for row in state["orders"].values() if row["sleeve"] == name],
            "fills": [row for row in state["fills"] if row["sleeve"] == name],
            "receivables": [row for row in state["receivables"] if row["sleeve"] == name],
            "positions": list(state["positions"].values()) if name == "strategy" else list(state["tranches"].values())}
        parity = list(state["parity"])
        if len(self._receipts) == len(self.days):
            parity.extend({"reason": "unmatched_comparator_order_at_replay_boundary", "at": _text(state["clock"]),
                           "reference": row["order_id"]} for row in self._active("comparator"))
            # An exited or terminal source can leave SPY held with no order,
            # e.g. a terminal unwind scheduled after the last replay session.
            parity.extend({"reason": "unmatched_comparator_exposure_at_replay_boundary", "at": _text(state["clock"]),
                           "reference": key} for key, row in sorted(state["tranches"].items())
                          if row["quantity"] and row["source_security_id"] not in state["positions"])
        return _text({"schema": "gdr.invented-multi-session-replay.v1", "data_class": "invented_fixture",
            "input_sha256": self.input_sha256, "lineage": deepcopy(self.lineage),
            "complete_software_replay": bool(complete), "comparison_parity_blocked": bool(parity or self._active("comparator")),
            "strategy": sleeve("strategy"), "comparator": sleeve("comparator"), "daily_nav": state["daily_nav"],
            "refusals": state["refusals"], "permanent_parity_blockers": parity,
            "unresolved": state["unresolved"], "actions": state["actions"], "cash_movements": state["cash_movements"],
            "scheduled_exits": state["due"],
            "program_stop_active": state["stopped"], "session_receipts": list(self._receipts.values()),
            "orders_are_simulated": True, "native_execution_verified": False, "backtest_ready": False,
            "point_in_time_data": False, "source_rights_verified": False, "calendar_and_mapping_verified": False,
            "settlement_calendar_verified": False, "historical_fees_verified": False,
            "independent_review_complete": False, "empirical_evaluation_allowed": False,
            "qc_access_allowed": False, "real_orders_allowed": False, "empirical_looks": 0, "qc_attempts": 0})

    def run(self):
        for session_date in self.days:
            self.step_session(session_date)
        return self.snapshot()


def run_replay(candidate, calendar, references, guidance, market_batches, contract, *,
               first_session, last_session, actions=(), data_class="invented_fixture", mode="base",
               producing_source_sha256=None):
    return MultiSessionReplay(candidate, calendar, references, guidance, market_batches, contract,
        first_session=first_session, last_session=last_session, actions=actions, data_class=data_class,
        mode=mode, producing_source_sha256=producing_source_sha256).run()
