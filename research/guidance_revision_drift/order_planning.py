"""Pure proposed order intents, never fills, broker orders or a backtest.

This separate input epoch does not relax the accepted SYN-only order engine.
Supplied cash, marks and references are assertions, not authenticated accounts.
The comparator instruction remains conditional on future actual stock fills.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from data.financial_primitives import (
    exact_decimal_add as add, exact_decimal_multiply as mul,
    exact_decimal_subtract as sub, exact_decimal_sum as total,
)
from data.hashing import hash_bytes
from research.guidance_revision_drift.contracts import Candidate
from research.guidance_revision_drift.guidance_inputs import GuidanceLedger
from research.guidance_revision_drift.historical_market import HistoricalMarketBatch
from research.guidance_revision_drift.input_contracts import (
    InputError, amount, canonical_bytes, day, decode_object, digest, identifier, keys, utc,
)
from research.guidance_revision_drift.research_reference import CalendarInput, ReferenceBook
from research.guidance_revision_drift.simulation import commission_total

ZERO = Decimal(0)
NY = ZoneInfo("America/New_York")
_ACCOUNT = {"schema", "source_sha256", "at", "settled_cash", "receivables",
            "positions", "pending_buys", "attempted_event_sha256s", "entry_controls"}
_CONTROLS = {"program_stop_active", "exits_or_trims_pending", "unresolved_actions", "unresolved_valuations"}
_POSITION = {"security_id", "issuer_id", "sector", "quantity", "raw_mark", "mark_at", "source_sha256"}
_PENDING = {"order_id", "issuer_id", "sector", "reserved_notional", "reserved_fee"}


def _clock(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _floor_ratio(left: Decimal, right: Decimal) -> int:
    an, ad = left.as_integer_ratio()
    bn, bd = right.as_integer_ratio()
    return (an * bd) // (ad * bn)


def _integer(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 10**12:
        raise InputError("bounded positive whole-share quantity required")
    return value


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    """Canonical local assertion, not a broker snapshot or permission token."""

    canonical_bytes: bytes

    def __post_init__(self) -> None:
        value = keys(decode_object(self.canonical_bytes), _ACCOUNT)
        if (value["schema"] != "gdr.offline-account-snapshot.v1"
                or canonical_bytes(value) != self.canonical_bytes):
            raise InputError("canonical offline account assertion required")
        digest(value["source_sha256"])
        at = utc(value["at"])
        amount(value["settled_cash"], nonnegative=True)
        controls = keys(value["entry_controls"], _CONTROLS)
        if any(item is not None and type(item) is not bool for item in controls.values()):
            raise InputError("explicit bool or unknown entry-control assertions required")
        for name, maximum in (("positions", 64), ("pending_buys", 64), ("receivables", 128),
                              ("attempted_event_sha256s", 512)):
            if type(value[name]) is not list or len(value[name]) > maximum:
                raise InputError("bounded account assertion inventory required")
        ids, issuers = set(), set()
        for row in value["positions"]:
            keys(row, _POSITION)
            for field in ("security_id", "issuer_id", "sector"):
                identifier(row[field])
            if row["security_id"] in ids or row["issuer_id"] in issuers:
                raise InputError("duplicate account security or issuer")
            ids.add(row["security_id"])
            issuers.add(row["issuer_id"])
            _integer(row["quantity"])
            amount(row["raw_mark"], positive=True)
            digest(row["source_sha256"])
            marked = utc(row["mark_at"])
            if not marked <= at or at - marked > timedelta(seconds=60):
                raise InputError("account holding mark is future or stale")
        order_ids = set()
        for row in value["pending_buys"]:
            keys(row, _PENDING)
            for field in ("order_id", "issuer_id", "sector"):
                identifier(row[field])
            if row["order_id"] in order_ids:
                raise InputError("duplicate pending account order")
            order_ids.add(row["order_id"])
            amount(row["reserved_notional"], nonnegative=True)
            amount(row["reserved_fee"], nonnegative=True)
        for row in value["receivables"]:
            keys(row, {"amount", "settlement_session"})
            amount(row["amount"], nonnegative=True)
            day(row["settlement_session"])
        for anchor in value["attempted_event_sha256s"]:
            digest(anchor)
        if len(set(value["attempted_event_sha256s"])) != len(value["attempted_event_sha256s"]):
            raise InputError("duplicate attempted event anchor")
        reserved = total(add(amount(row["reserved_notional"]), amount(row["reserved_fee"]))
                         for row in value["pending_buys"])
        if reserved > amount(value["settled_cash"]):
            raise InputError("pending reservations exceed declared settled cash")

    @classmethod
    def from_dict(cls, value: dict) -> AccountSnapshot:
        return cls(canonical_bytes(value))

    @classmethod
    def from_bytes(cls, raw: bytes) -> AccountSnapshot:
        return cls(raw)

    def to_dict(self) -> dict:
        self.__post_init__()
        return decode_object(self.canonical_bytes)

    @property
    def sha256(self) -> str:
        self.__post_init__()
        return hash_bytes(self.canonical_bytes)


def _capacity(account: AccountSnapshot, calendar: CalendarInput, entry_session: date, decision: datetime) -> dict:
    value = account.to_dict()
    if utc(value["at"]) != decision:
        raise InputError("account assertion must match this exact decision instant")
    sectors, gross = {}, ZERO
    for row in value["positions"]:
        marked = mul(Decimal(row["quantity"]), amount(row["raw_mark"]))
        gross = add(gross, marked)
        sectors[row["sector"]] = add(sectors.get(row["sector"], ZERO), marked)
    nav = total((amount(value["settled_cash"]), gross,
                 total(amount(row["amount"]) for row in value["receivables"])))
    if nav <= 0:
        raise InputError("positive declared account NAV required")
    reserved = ZERO
    for row in value["pending_buys"]:
        notional = amount(row["reserved_notional"])
        gross = add(gross, notional)
        sectors[row["sector"]] = add(sectors.get(row["sector"], ZERO), notional)
        reserved = add(reserved, add(notional, amount(row["reserved_fee"])))
    reasons = ["entry_control_" + name for name, state in value["entry_controls"].items() if state is not False]
    for row in value["receivables"]:
        settlement = day(row["settlement_session"])
        # This legacy field names a payment/service DATE assertion. Settlement
        # services and NYSE trading sessions have distinct calendars; the
        # execution contract checks service dates. This planner never credits it.
        if settlement <= entry_session and amount(row["amount"]) > 0:
            reasons.append("due_receivable_requires_reconciliation")
    return {"nav": nav, "gross": gross, "sectors": sectors,
            "cash": sub(amount(value["settled_cash"]), reserved), "reasons": sorted(set(reasons)),
            "occupied": {row["issuer_id"] for row in value["positions"] + value["pending_buys"]},
            "attempted": set(value["attempted_event_sha256s"])}


def _affordable(budget: Decimal, limit: Decimal, mode: str) -> int:
    minimum = Decimal(2 if mode == "stress" else 1)
    if budget <= minimum:
        return 0
    return max(0, min(_floor_ratio(sub(budget, minimum), limit),
                      _floor_ratio(budget, add(limit, Decimal("0.005")))))


def plan_session(candidate: Candidate, calendar: CalendarInput, references: ReferenceBook,
                 guidance: GuidanceLedger, market_batches: tuple[HistoricalMarketBatch, ...],
                 account: AccountSnapshot, entry_session: date, *, mode: str = "base") -> dict:
    """Prepare bounded provisional buy intents; no execution/evaluation occurs.

    A later E+1/E+2 cannot rescue an earlier already-eligible supplied-input
    opportunity. Reference/guidance consistency cannot prove authentic data.
    Missing earlier coverage is a refusal, never permission to pick a price.
    """
    if type(candidate) is not Candidate or type(calendar) is not CalendarInput or type(references) is not ReferenceBook:
        raise InputError("exact candidate calendar and reference inputs required")
    candidate = Candidate(candidate.canonical_bytes)
    calendar = CalendarInput(calendar.canonical_bytes)
    references = ReferenceBook(references.canonical_bytes)
    if type(guidance) is not GuidanceLedger or type(account) is not AccountSnapshot:
        raise InputError("exact local guidance ledger and account assertion required")
    guidance, account = GuidanceLedger(guidance.receipts), AccountSnapshot(account.canonical_bytes)
    if type(entry_session) is not date or mode not in ("base", "stress") or type(mode) is not str:
        raise InputError("explicit planning session and execution-cost mode required")
    if entry_session.isoformat() >= candidate.to_dict()["evidence"]["outcome_quarantine_from"]:
        raise InputError("protected planning session requires a different scope")
    session = calendar.sessions[calendar.index(entry_session)]
    decision = datetime.combine(entry_session, time(10), NY).astimezone(timezone.utc)
    cutoff = calendar.cutoff(entry_session)
    if not session.open_utc <= decision <= session.close_utc:
        raise InputError("planning decision outside declared regular session")
    capacity = _capacity(account, calendar, entry_session, decision)
    if type(market_batches) is not tuple or len(market_batches) > 65:
        raise InputError("bounded immutable market batch inventory required")
    batches, benchmark = {}, None
    for batch in market_batches:
        if type(batch) is not HistoricalMarketBatch:
            raise InputError("exact historical market batch required")
        batch = HistoricalMarketBatch(batch.raw_bytes)
        if (batch.session_date != entry_session or batch.session_open_utc != session.open_utc
                or batch.session_close_utc != session.close_utc or batch.security_id in batches):
            raise InputError("market inventory session or identity mismatch")
        batches[batch.security_id] = batch
        if batch.role == "benchmark":
            if benchmark is not None:
                raise InputError("exactly one benchmark market batch required")
            benchmark = batch
    portfolio = candidate.to_dict()["portfolio"]
    projection = guidance.as_of(_clock(cutoff))
    decision_projection = guidance.as_of(_clock(decision))
    still_active = {row.current_sha256 for row in decision_projection.active_comparisons}
    documents = {row.document.sha256: row.document for row in guidance.receipts}
    candidates, rows = [], []
    for comparison in projection.active_comparisons:
        document = documents[comparison.current_sha256]
        body = document.to_dict()
        security, issuer, event = body["security_id"], body["issuer_id"], document.sha256
        reasons = list(capacity["reasons"])
        # Late positive news cannot create this cutoff cohort; known risk
        # invalidations after cutoff still cancel its proposed new exposure.
        if event not in still_active:
            reasons.append("guidance_invalidated_between_cutoff_and_decision")
        window = calendar.entry_window(utc(body["published_at"]))
        if entry_session not in window:
            reasons.append("outside_first_three_entry_opportunities")
        if utc(body["published_at"]) >= cutoff:
            reasons.append("publication_not_strictly_before_cutoff")
        for prior in (when for when in window if when < entry_session):
            previous = guidance.as_of(_clock(calendar.cutoff(prior)))
            if any(item.current_sha256 == event for item in previous.active_comparisons):
                earlier = references.eligibility(calendar, security, prior)
                if earlier["eligible"]:
                    reasons.append("earlier_supplied_input_opportunity_already_eligible")
                elif any(reason.startswith(("missing_", "ambiguous_", "insufficient_"))
                         for reason in earlier["reasons"]):
                    reasons.append("earlier_opportunity_evidence_incomplete")
        eligibility = references.eligibility(calendar, security, entry_session)
        reasons.extend(eligibility["reasons"])
        if eligibility["issuer_id"] is not None and eligibility["issuer_id"] != issuer:
            reasons.append("guidance_reference_issuer_mismatch")
        if event in capacity["attempted"]:
            reasons.append("event_already_attempted")
        if issuer in capacity["occupied"]:
            reasons.append("issuer_already_held_or_pending")
        stock = batches.get(security)
        stock_quote = None
        if stock is None or stock.role != "stock":
            reasons.append("missing_stock_market_input")
        else:
            if stock.symbol != eligibility["symbol"]:
                reasons.append("stock_symbol_reference_mismatch")
            try:
                stock_quote = stock.decision_quote(decision)
            except InputError:
                reasons.append("stock_decision_quote_refused")
        if benchmark is None or benchmark.security_id == security:
            reasons.append("missing_distinct_spy_market_input")
        else:
            spy_reference = references.eligibility(calendar, benchmark.security_id, entry_session, role="benchmark")
            reasons.extend("benchmark_" + reason for reason in spy_reference["reasons"])
            if spy_reference["symbol"] != benchmark.symbol:
                reasons.append("benchmark_symbol_reference_mismatch")
            try:
                benchmark.decision_quote(decision)
            except InputError:
                reasons.append("benchmark_decision_quote_refused")
        row = {"event_sha256": event, "security_id": security, "issuer_id": issuer,
               "status": "refused" if reasons else "candidate", "reasons": sorted(set(reasons)),
               "intent": None, "priority_rank": None}
        rows.append(row)
        if not reasons:
            # Prior eligible opportunities are refused above. Every admitted
            # candidate's first supplied-input eligible session is this one,
            # not necessarily its theoretical D+3 when receipt was delayed.
            candidates.append((entry_session, comparison, eligibility, stock_quote, row))
    # Exact rational ordering avoids rounded percentage ties.
    from fractions import Fraction
    candidates.sort(key=lambda row: (row[0],
        -Fraction(row[1].arithmetic.current_revenue_midpoint) / Fraction(row[1].arithmetic.previous_revenue_midpoint),
        -Fraction(row[1].arithmetic.current_eps_midpoint) / Fraction(row[1].arithmetic.previous_eps_midpoint),
        row[4]["security_id"]))
    for rank, (_, comparison, eligibility, quote, row) in enumerate(candidates, 1):
        row["priority_rank"] = rank
        sector = eligibility["sector"]
        gross_room = sub(mul(capacity["nav"], amount(portfolio["gross_fraction_max"])), capacity["gross"])
        sector_room = sub(mul(capacity["nav"], amount(portfolio["sector_fraction_max"])), capacity["sectors"].get(sector, ZERO))
        budget = min(mul(capacity["nav"], amount(portfolio["position_fraction_max"])),
                     amount(portfolio["entry_notional_max_usd"]),
                     mul(amount(eligibility["adv20"]), amount(portfolio["daily_adv_fraction_max"])),
                     gross_room, sector_room)
        limit = mul(quote.ask, add(Decimal(1), amount(candidate.to_dict()["execution"]["buy_limit_above_ask_fraction"])))
        # Exposure/ADV caps bound NOTIONAL; fees are reserved separately from
        # settled cash, as in the proposed contract and existing fixture engine.
        quantity = min(max(0, _floor_ratio(budget, limit)), _affordable(capacity["cash"], limit, mode))
        if row["issuer_id"] in capacity["occupied"]:
            row["reasons"] = ["issuer_reserved_by_prior_ranked_intent"]
        elif quantity == 0:
            row["reasons"] = ["insufficient_declared_cash_or_exposure_capacity"]
        elif quantity > 10**12:
            row["reasons"] = ["planned_whole_share_quantity_exceeds_supported_bound"]
        else:
            notional, fee = mul(Decimal(quantity), limit), commission_total(quantity, mode)
            reserved = add(notional, fee)
            if not notional <= budget or reserved > capacity["cash"]:
                raise InputError("planned reservation exceeds declared notional or cash capacity")
            capacity["cash"] = sub(capacity["cash"], reserved)
            capacity["gross"] = add(capacity["gross"], notional)
            capacity["sectors"][sector] = add(capacity["sectors"].get(sector, ZERO), notional)
            capacity["occupied"].add(row["issuer_id"])
            row["status"] = "provisional_entry_intent"
            row["intent"] = {"side": "buy", "type": "marketable_limit", "whole_shares": quantity,
                "limit_price": format(limit, "f"), "reserved_notional": format(notional, "f"),
                "reserved_fee": format(fee, "f"), "sector": sector, "submitted_at": _clock(decision),
                "cancel_remainder_at": _clock(datetime.combine(entry_session, time(10, 5), NY).astimezone(timezone.utc)),
                "proposed_time_exit_session": calendar.time_exit(entry_session).isoformat(),
                "stock_quote_source_sha256": quote.source_sha256,
                "comparator": {"symbol": "SPY", "order_now": False,
                    "trigger": "each_actual_strategy_fill_only_at_next_equivalent_execution_opportunity",
                    "budget": "actual_filled_strategy_notional_plus_incremental_fee",
                    "exit": "actual_strategy_exit_fraction_with_unmatched_or_terminal_cases_blocked"}}
        if row["intent"] is None:
            row["status"] = "refused"
    return {"schema": "gdr.offline-order-plan.v1",
        "status": "offline_plan_with_refusals" if any(row["status"] == "refused" for row in rows)
            or any(row.disposition in ("refused", "quarantined") for row in projection.decisions)
            else "offline_intents_prepared",
        "scope": "one_session_proposed_buy_intents_only_no_fills_or_performance",
        "candidate_sha256": candidate.sha256, "calendar_sha256": calendar.sha256,
        "reference_sha256": references.sha256, "account_sha256": account.sha256,
        "guidance_head_sha256": guidance.head_sha256, "as_of_guidance_head_sha256": projection.head_sha256,
        "decision_guidance_head_sha256": decision_projection.head_sha256,
        "market_source_sha256s": {key: value.sha256 for key, value in sorted(batches.items())},
        "session_date": entry_session.isoformat(), "decision_at": _clock(decision), "cutoff": _clock(cutoff),
        "mode": mode, "nav_from_declared_inputs": format(capacity["nav"], "f"), "candidates": rows,
        "remaining_declared_settled_cash": format(capacity["cash"], "f"),
        "guidance_observations": [{"document_sha256": row.document_sha256,
            "status": row.disposition, "reasons": list(row.refusal_reasons)} for row in projection.decisions],
        "orders_submitted": 0, "fills": [], "native_execution_verified": False,
        "complete_execution_gate": False,
        "additional_execution_requirements": ["authoritative_drawdown_NAV_history",
            "actual_exit_trim_action_reconciliation", "dated_fee_settlement_contract",
            "subsequent_stock_and_SPY_fill_capacity_and_cash_reconciliation"],
        "backtest_ready": False, "point_in_time_data": False, "source_rights_verified": False,
        "account_authenticity_verified": False, "calendar_and_mapping_verified": False,
        "empirical_evaluation_allowed": False, "qc_access_allowed": False, "real_orders_allowed": False}
