"""Exact continuous order books for the separate latest-revised exploration.

The file-fed exploratory path never calls the synthetic accounting kernel.
Every frozen lookback, cost and allocation role has one cash book. Raw opens
plus explicit corporate actions determine value; source and trading authority
remain false even when the accounting is complete.
"""
from __future__ import annotations

import dataclasses
import json
from decimal import Decimal
from fractions import Fraction
from typing import Any

from data.financial_primitives import decimal_text
from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
from research.short_interest_etf.latest_revised_source import LatestRevisedBundle
from research.short_interest_etf.latest_revised_protocol import (
    ALLOCATION_ROLES, COSTS_BPS, EPOCH_ID, EVALUATION_END, EVALUATION_START,
    INITIAL_CASH_USD, LOOKBACKS, PROTOCOL_SHA256, protocol_payload,
)
from research.short_interest_etf.latest_revised_rankings import LatestRevisedRankings

LATEST_REVISED_ORDER_SCHEMA = "si-latest-revised-continuous-orders-v1"
_EVENT_PRIORITY = {"split": 0, "dividend_entitlement": 1, "dividend_payment": 2,
                   "terminal": 3, "suspension": 4, "unknown_terminal": 5}


class LatestRevisedOrderError(ValueError):
    """An exploratory accounting contract failed closed."""


def _refuse(reason: str) -> LatestRevisedOrderError:
    return LatestRevisedOrderError(f"REFUSED: {reason}")


def _fraction(value: Any, name: str, *, positive: bool = False) -> Fraction:
    if type(value) is not str or len(value) > 128:
        raise _refuse(f"{name} must be canonical decimal text")
    try:
        amount = Decimal(value)
    except ArithmeticError as exc:
        raise _refuse(f"{name} must be finite decimal text") from exc
    if not amount.is_finite() or decimal_text(amount) != value:
        raise _refuse(f"{name} must be canonical finite decimal text")
    if amount < 0 or (positive and amount == 0):
        raise _refuse(f"{name} must be {'positive' if positive else 'nonnegative'}")
    return Fraction(amount)


def _amount(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _authority() -> dict[str, Any]:
    return {"latest_revised": True, "point_in_time_data": False,
            "source_admitted": False, "confirmatory_eligible": False,
            "outcome_access_authorized": False, "qc_backtest_authorized": False,
            "production_authoritative": False, "trading_authority": False}


def _inputs(bundle, rankings):
    frozen = protocol_payload()
    if (list(LOOKBACKS) != frozen["candidate_lookbacks"]
            or list(COSTS_BPS) != frozen["cost_bps_per_side"]
            or list(ALLOCATION_ROLES) != frozen["allocation_roles"]
            or INITIAL_CASH_USD != frozen["initial_cash_usd"]
            or EVALUATION_START != frozen["evaluation_start"]
            or EVALUATION_END != frozen["evaluation_end"]
            or EPOCH_ID != frozen["evidence_epoch"]
            or _EVENT_PRIORITY != {"split": 0, "dividend_entitlement": 1, "dividend_payment": 2,
                                   "terminal": 3, "suspension": 4, "unknown_terminal": 5}):
        raise _refuse("order rules differ from the frozen exploratory protocol")
    if type(bundle) is not LatestRevisedBundle:
        raise _refuse("bundle must be the exact LatestRevisedBundle type")
    if type(rankings) is not LatestRevisedRankings:
        raise _refuse("rankings must be the exact LatestRevisedRankings type")
    source, ranked = bundle.to_payload(), rankings.to_payload()
    if ranked["source_bundle_sha256"] != source["bundle_sha256"]:
        raise _refuse("rankings belong to a different source bundle")
    if ranked["protocol_sha256"] != PROTOCOL_SHA256:
        raise _refuse("rankings belong to a different exploratory protocol")
    if len(source["releases"]) != len(ranked["releases"]):
        raise _refuse("rankings do not preserve every calendar release")
    for original, release in zip(source["releases"], ranked["releases"]):
        if any(release[key] != original[key] for key in (
            "settlement_date", "publication_date", "entry_session", "entry_at"
        )):
            raise _refuse("ranking calendar differs from source calendar")
        if tuple(row["lookback_sessions"] for row in release["lookbacks"]) != LOOKBACKS:
            raise _refuse("ranking calendar does not preserve the four lookbacks")
    if hash_payload(protocol_payload()) != PROTOCOL_SHA256:
        raise _refuse("exploratory protocol differs from its frozen digest")
    return source, ranked


def _at(event):
    return parse_utc_timestamp(event["at"], "event.at")


def _events(source):
    end = parse_utc_timestamp(EVALUATION_END + "T23:59:59.999999Z", "evaluation_end")
    return sorted((event for event in source["events"] if _at(event) <= end),
                  key=lambda event: (_at(event), _EVENT_PRIORITY[event["kind"]],
                                     event["security_id"], event["event_id"]))


def _window_records(releases, lookback):
    records = []
    for index, release in enumerate(releases):
        row = next(item for item in release["lookbacks"] if item["lookback_sessions"] == lookback)
        common, high, low = (row[key] for key in (
            "common_security_ids", "high_tail_security_ids", "low_tail_security_ids"))
        if any(security not in common for security in high + low):
            raise _refuse("tail routing leaves the original common cohort")
        reasons = sorted(set(release["refusal_reasons"] + row["refusal_reasons"]))
        final = index == len(releases) - 1
        records.append({
            "settlement_date": release["settlement_date"], "entry_session": release["entry_session"],
            "entry_at": release["entry_at"], "next_settlement_date": None if final else releases[index+1]["settlement_date"],
            "exit_session": None if final else releases[index+1]["entry_session"],
            "exit_at": None if final else releases[index+1]["entry_at"], "ranking_status": release["status"],
            "status": "final_no_successor" if final else release["status"],
            "common_security_ids": list(common), "high_tail_security_ids": list(high),
            "low_tail_security_ids": list(low),
            "original_high_tail_security_ids": list(row["original_high_tail_security_ids"]),
            "original_low_tail_security_ids": list(row["original_low_tail_security_ids"]),
            "refusal_reasons": sorted(set(reasons + (["no_successor_release"] if final else [])))})
    return records


def _executable(record):
    return (record["status"] == "ready" and bool(record["common_security_ids"])
            and EVALUATION_START <= record["entry_session"] <= EVALUATION_END)


def _preflight(records, bars, events):
    """Validate all original members before any role constructs a ledger."""
    errors = set()
    by_security = {}
    for event in events:
        by_security.setdefault(event["security_id"], []).append(event)
    for record in records:
        if not _executable(record):
            continue
        start = parse_utc_timestamp(record["entry_at"], "entry_at")
        end = parse_utc_timestamp(record["exit_at"], "exit_at")
        local = set()
        if record["exit_session"] > EVALUATION_END:
            local.add("successor_exit_after_evaluation_end")
        for security in record["common_security_ids"]:
            relevant = by_security.get(security, [])
            terminal = [item for item in relevant if item["kind"] == "terminal" and start < _at(item) <= end]
            if (security, record["entry_session"]) not in bars:
                local.add(f"missing_entry_raw_open:{security}:{record['entry_session']}")
            if (security, record["exit_session"]) not in bars and not terminal:
                local.add(f"missing_exit_raw_open:{security}:{record['exit_session']}")
            if len(terminal) > 1:
                local.add(f"duplicate_terminal:{security}")
            for event in relevant:
                at, kind = _at(event), event["kind"]
                if kind in ("terminal", "unknown_terminal", "suspension") and at <= start:
                    local.add(f"entry_after_{kind}:{security}:{event['event_id']}")
                if start < at <= end and kind in ("suspension", "unknown_terminal"):
                    local.add(f"{kind}:{security}:{event['event_id']}")
                if kind != "dividend_entitlement" or not (start < at <= end):
                    continue
                dividend = event["dividend_id"]
                entitlements = [item for item in relevant if item["kind"] == "dividend_entitlement" and item["dividend_id"] == dividend]
                payments = [item for item in relevant if item["kind"] == "dividend_payment" and item["dividend_id"] == dividend]
                if len(entitlements) != 1 or len(payments) > 1:
                    local.add(f"ambiguous_dividend_events:{security}:{dividend}")
                for payment in payments:
                    if _at(payment) < at:
                        local.add(f"dividend_payment_precedes_entitlement:{security}:{dividend}")
                    if _fraction(payment["cash_per_share"], "payment cash_per_share") != _fraction(event["cash_per_share"], "entitlement cash_per_share"):
                        local.add(f"dividend_payment_amount_mismatch:{security}:{dividend}")
        if local:
            record["status"] = "incomplete_common_cohort"
            record["refusal_reasons"] = sorted(set(record["refusal_reasons"]) | local)
        errors.update(local)
    return sorted(errors)


def _allocation(record, role):
    if role == "equal_weight_common":
        return list(record["common_security_ids"])
    if role == "avoid_high_pressure":
        high = set(record["high_tail_security_ids"])
        return [security for security in record["common_security_ids"] if security not in high]
    return list(record["low_tail_security_ids"])


def _book(base_records, bars, events, lookback, cost, role, preflight_errors=None):
    records = json.loads(canonical_json(base_records))
    envelope = {"lookback_sessions": lookback, "cost_bps_per_side": cost,
                "cost_role": "primary" if cost == 10 else "sensitivity", "allocation_role": role,
                "initial_cash_usd": INITIAL_CASH_USD, "release_records": records}
    errors = _preflight(records, bars, events) if preflight_errors is None else preflight_errors
    if errors:
        return {**envelope, "complete": False, "refusal_reasons": errors, "financial_result": None}
    initial = _fraction(INITIAL_CASH_USD, "initial_cash_usd", positive=True)
    cash, fees, dividends, terminal_cash = initial, Fraction(0), Fraction(0), Fraction(0)
    fee_rate = Fraction(cost, 10000)
    positions, receivables = {}, {}
    orders, cashflows, splits = [], [], []
    event_index = 0
    start = parse_utc_timestamp(EVALUATION_START + "T00:00:00Z", "evaluation_start")

    def process_until(until):
        nonlocal cash, dividends, terminal_cash, event_index
        while event_index < len(events):
            event = events[event_index]
            at = _at(event)
            if at > until:
                break
            event_index += 1
            if at < start:
                continue
            security, kind = event["security_id"], event["kind"]
            quantity = positions.get(security, Fraction(0))
            base = {"event_id": event["event_id"], "at": event["at"], "kind": kind, "security_id": security}
            if kind == "split" and quantity:
                ratio = Fraction(event["split_numerator"], event["split_denominator"])
                positions[security] = quantity * ratio
                splits.append({**base, "ratio": _amount(ratio), "quantity_before": _amount(quantity), "quantity_after": _amount(positions[security])})
            elif kind == "dividend_entitlement" and quantity:
                key = security, event["dividend_id"]
                if key in receivables:
                    raise _refuse("duplicate held dividend entitlement reached ledger")
                amount = quantity * _fraction(event["cash_per_share"], "cash_per_share")
                receivables[key] = amount
                cashflows.append({**base, "dividend_id": event["dividend_id"], "shares_entitled": _amount(quantity), "amount": _amount(amount)})
            elif kind == "dividend_payment":
                key = security, event["dividend_id"]
                if key in receivables:
                    amount = receivables.pop(key)
                    cash += amount
                    dividends += amount
                    cashflows.append({**base, "dividend_id": event["dividend_id"], "amount": _amount(amount)})
            elif kind == "terminal" and quantity:
                amount = quantity * _fraction(event["cash_per_share"], "cash_per_share")
                cash += amount
                terminal_cash += amount
                del positions[security]
                cashflows.append({**base, "shares_terminated": _amount(quantity), "amount": _amount(amount)})
            elif kind in ("suspension", "unknown_terminal") and quantity:
                raise _refuse("unresolved held corporate action passed cohort preflight")

    def order(record, security, side, quantity):
        nonlocal cash, fees
        raw_open = bars[(security, record["entry_session"])]["open"]
        price = _fraction(raw_open, "raw_open", positive=True)
        notional, fee = quantity * price, quantity * price * fee_rate
        cash += notional - fee if side == "sell" else -(notional + fee)
        fees += fee
        if cash < 0:
            raise _refuse("continuous book would borrow cash")
        if side == "buy":
            positions[security] = quantity
        else:
            del positions[security]
        orders.append({"at": record["entry_at"], "session": record["entry_session"],
                       "settlement_date": record["settlement_date"], "security_id": security, "side": side,
                       "quantity": _amount(quantity), "raw_open_usd": raw_open, "notional": _amount(notional),
                       "fee": _amount(fee), "cash_after": _amount(cash),
                       "position_after": _amount(positions.get(security, Fraction(0)))})

    for record in records:
        at = parse_utc_timestamp(record["entry_at"], "entry_at")
        if not EVALUATION_START <= record["entry_session"] <= EVALUATION_END:
            record["execution_status"] = "outside_evaluation_warmup_only"
            continue
        process_until(at)
        record["cash_before_rebalance"] = _amount(cash)
        # Same-time actions apply to the preceding basket, then exits precede
        # sizing. Receivables are not available buying power until payment.
        for security in sorted(positions):
            order(record, security, "sell", positions[security])
        record["cash_after_exit"] = _amount(cash)
        chosen = _allocation(record, role) if _executable(record) else []
        record["allocation_security_ids"] = chosen
        if chosen and cash > 0:
            allocation = cash / len(chosen)
            for security in chosen:
                price = _fraction(bars[(security, record["entry_session"])]["open"], "raw_open", positive=True)
                order(record, security, "buy", allocation / (price * (1 + fee_rate)))
            record["execution_status"] = "rebalanced"
        elif _executable(record):
            record["execution_status"] = "empty_allocation" if not chosen else "zero_available_cash"
        elif record["status"] == "final_no_successor":
            record["execution_status"] = "final_exit_only"
        else:
            record["execution_status"] = "retained_refusal_cash_only"
        record["cash_after_rebalance"] = _amount(cash)
    process_until(parse_utc_timestamp(EVALUATION_END + "T23:59:59.999999Z", "evaluation_end"))
    errors = sorted(f"unsettled_dividend_receivable:{security}:{dividend}"
                    for (security, dividend), amount in receivables.items() if amount > 0)
    if positions:
        errors.append("open_positions_at_evaluation_end")
    if errors:
        # Never expose a partial financial path as cumulative performance.
        for record in records:
            for key in ("cash_before_rebalance", "cash_after_exit", "cash_after_rebalance"):
                record.pop(key, None)
        return {**envelope, "complete": False, "refusal_reasons": sorted(errors), "financial_result": None}
    financial = {"initial_cash": _amount(initial), "ending_cash": _amount(cash), "total_equity": _amount(cash),
                 "realized_pnl": _amount(cash-initial), "net_return": _amount((cash-initial)/initial),
                 "total_fees": _amount(fees), "dividends_paid": _amount(dividends),
                 "terminal_cash_paid": _amount(terminal_cash), "outstanding_dividend_receivables": _amount(Fraction(0)),
                 "final_positions": []}
    return {**envelope, "complete": True, "refusal_reasons": [], "financial_result": financial,
            "orders": orders, "cashflows": cashflows, "splits": splits}


def _replay(bundle, rankings, authenticated_inputs=None):
    source, ranked = _inputs(bundle, rankings) if authenticated_inputs is None else authenticated_inputs
    bars = {(row["security_id"], row["session"]): row for row in source["bars"]}
    events, books = _events(source), []
    for lookback in LOOKBACKS:
        records = _window_records(ranked["releases"], lookback)
        errors = _preflight(records, bars, events)
        for cost in COSTS_BPS:
            for role in ALLOCATION_ROLES:
                books.append(_book(records, bars, events, lookback, cost, role, errors))
    payload = {"schema": LATEST_REVISED_ORDER_SCHEMA, "evidence_epoch": EPOCH_ID,
               "protocol_sha256": PROTOCOL_SHA256, "source_bundle_sha256": source["bundle_sha256"],
               "rankings_sha256": ranked["rankings_sha256"], "authority": _authority(),
               "actual_outcome_access_authority": False, "look_accounting": "runner_managed",
               "revision_biased_descriptive": True,
               "allocated_alpha": _amount(Fraction(0)),
               "evaluation_start": EVALUATION_START, "evaluation_end": EVALUATION_END,
               "initial_cash_usd": INITIAL_CASH_USD, "selected_lookback": None,
               "price_rule": "raw_opens_plus_explicit_corporate_actions",
               "event_clock_order": list(_EVENT_PRIORITY),
               "portfolio_rule": "one_continuous_self_financing_fractional_long_only_book_per_cell",
               "complete": all(book["complete"] for book in books), "books": books}
    payload["order_replay_sha256"] = hash_payload(payload)
    return payload


@dataclasses.dataclass(frozen=True, slots=True)
class LatestRevisedOrderReplay:
    """Immutable result bound to exact revalidated source and ranking records."""

    bundle: LatestRevisedBundle = dataclasses.field(repr=False)
    rankings: LatestRevisedRankings = dataclasses.field(repr=False)
    _source_sha256: str = dataclasses.field(init=False, repr=False)
    _rankings_sha256: str = dataclasses.field(init=False, repr=False)
    _payload_json: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self):
        if type(self) is not LatestRevisedOrderReplay:
            raise _refuse("replay must be the exact LatestRevisedOrderReplay type")
        payload = _replay(self.bundle, self.rankings)
        object.__setattr__(self, "_source_sha256", payload["source_bundle_sha256"])
        object.__setattr__(self, "_rankings_sha256", payload["rankings_sha256"])
        object.__setattr__(self, "_payload_json", canonical_json(payload))

    def to_payload(self):
        if type(self) is not LatestRevisedOrderReplay:
            raise _refuse("replay must be the exact LatestRevisedOrderReplay type")
        source, ranked = _inputs(self.bundle, self.rankings)
        if source["bundle_sha256"] != self._source_sha256 or ranked["rankings_sha256"] != self._rankings_sha256:
            raise _refuse("replay source or ranking binding changed")
        expected = canonical_json(_replay(self.bundle, self.rankings, (source, ranked)))
        if type(self._payload_json) is not str or self._payload_json != expected:
            raise _refuse("replay payload differs from deterministic source-bound accounting")
        return json.loads(expected)

    @property
    def sha256(self):
        return self.to_payload()["order_replay_sha256"]

    @property
    def payload_json(self):
        return canonical_json(self.to_payload())


def replay_latest_revised_orders(bundle: LatestRevisedBundle, rankings: LatestRevisedRankings) -> LatestRevisedOrderReplay:
    """Construct the 48 frozen books without selecting a winning cell."""
    return LatestRevisedOrderReplay(bundle, rankings)
