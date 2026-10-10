"""Pure original-wire order observations, permanently non-authorizing.

Jointly absent fees on one exact native-tagged final Market close stay UNKNOWN.
Tags/serialized enums are not independent custody proof. Nothing here repairs
raw evidence, assumes a currency, attests a zero fee, or changes old auditors.
"""
from datetime import datetime, timezone
from fractions import Fraction
import re

from . import matched_audit as accounting

AuditError = accounting.AuditError
_refuse, _number, _integer, _text = accounting._refuse, accounting._number, accounting._integer, accounting._text
_GROUPS = ("strategy_tagged_moo", "engine_tagged_delisting_market", "unclassified")
_FEE_KEYS = {"orderFeeAmount", "orderFeeCurrency"}
_STATUSES = {0, 1, 2, 3, 5, 6, 7, 8, 9}
_EVENT_STATUSES = {"new", "submitted", "partiallyFilled", "partially_filled", "filled", "canceled",
                  "none", "invalid", "cancelPending", "cancel_pending", "updateSubmitted", "update_submitted"}


def _id(value):
    if type(value) is not int or value < 0:
        _refuse("exact native integer identity required")
    return value


def _filled(status):
    return type(status) is int and status == 3 or type(status) is str and status == "filled"


def _fill(status):
    return (type(status) is int and status in (2, 3)
            or type(status) is str and status in ("filled", "partiallyFilled", "partially_filled"))


def _event_identity(event, oid, receipt):
    eid = _id(event.get("orderEventId", event.get("id")))
    algorithm = event.get("algorithmId")
    if "algorithmId" in event and (type(algorithm) is not str or not 0 < len(algorithm) <= 128
            or algorithm != receipt.get("backtest_id")):
        _refuse("foreign native event algorithm identity")
    if "id" in event:
        alias = event["id"]
        if type(alias) is str:
            # SerializedOrderEvent.Id is the native composite, not event.Id.
            if algorithm is None or alias != f"{algorithm}-{oid}-{eid}":
                _refuse("ambiguous native fill event identity")
        elif type(alias) is not int or alias != eid:
            _refuse("ambiguous native fill event identity")
    if any(key in event for key in ("order-id", "order-event-id", "algorithm-id")):
        _refuse("ambiguous native fill event identity")
    return oid, eid


def _group(order):
    raw = type(order.get("priceAdjustmentMode")) is int and order["priceAdjustmentMode"] == 0
    kind, tag = order.get("type"), order.get("tag")
    if (type(kind) is int and kind == 4 and raw and order.get("priceCurrency") == "USD"
            and type(tag) is str and re.fullmatch(r"TPRM:[0-9a-f]{20}", tag)):
        return "strategy_tagged_moo"
    if type(kind) is int and kind == 0 and raw and tag == "Liquidate from delisting":
        return "engine_tagged_delisting_market"
    return "unclassified"


def _currency(row, key, allow_unknown):
    if key not in row or row[key] == "":
        if allow_unknown:
            return None
        _refuse("unknown currency outside exact native final close")
    value = row[key]
    if type(value) is not str or re.fullmatch(r"[A-Z]{3}", value) is None:
        _refuse("invalid native currency metadata")
    return value


def _empty_group():
    return {"orders": 0, "fill_events": 0, "filled_orders": 0, "submitted_shares": Fraction(0),
        "filled_shares": Fraction(0), "observed_fees": Fraction(0), "api_unreported_fee_events": 0,
        "non_usd_nonzero_fee_events": 0, "observed_usd_fill_notional": Fraction(0),
        "native_fill_currency_unknown_fill_events": 0, "zero_fee_qcc_fill_events": 0,
        "zero_fee_usd_fill_events": 0, "other_fee_or_currency_fill_events": 0}


def orders(pages, receipt, summary, stats, config, reasons):
    """Return orders/partition/fee_provenance; append fixed diagnostic reasons.

    The outer reporter MUST first bind the original response/page hashes and
    candidate identity. Numeric observed subtotals are USD only. All-native
    totals are None if unit/fee/inventory evidence is incomplete.
    """
    if (type(pages) is not list or len(pages) > 100 or type(receipt) is not dict
            or type(summary) is not dict or type(stats) is not dict or type(config) is not dict
            or config.get("arm") not in ("tpr_on", "tpr_off") or config.get("cost") != "baseline"
            or type(reasons) is not list):
        _refuse("bounded cap diagnostic inputs required")
    required = {"submitted_orders", "submitted_shares", "fill_events", "filled_shares", "fees",
                "native_final_delisting_compatibility_exceptions"}
    if not required.issubset(summary):
        _refuse("complete original order summary required")
    counts = {key: _integer(summary[key]) for key in required - {"fees"}}
    summary_fee = _number(summary["fees"])
    if summary_fee < 0:
        _refuse("negative original summary fees")
    rows, total, expected_start, complete = [], None, 0, bool(pages)
    if not pages:
        reasons.append("order_inventory_missing")
    for page in pages:
        if type(page) is not dict:
            _refuse("native order page object required")
        if page.get("success") is not True:
            complete = False
            reasons.append("order_inventory_loading_or_failed")
            continue
        if "loading" in page and type(page["loading"]) is not bool:
            _refuse("exact native loading flag required")
        if page.get("loading") is True:
            complete = False
            reasons.append("order_inventory_loading_or_failed")
        if "start" not in page or "end" not in page:
            complete = False
            reasons.append("order_page_boundary_missing")
            width = 99
        else:
            start, end = _id(page["start"]), _id(page["end"])
            if start != expected_start or not 0 < end - start < 100:
                _refuse("overlapping unordered or unbounded order page")
            expected_start, width = end, end - start
        length = _id(page.get("length"))
        if length > 5000:
            _refuse("bounded native order inventory required")
        if total is not None and length != total:
            _refuse("changing native order inventory length")
        total = length
        inventory = page.get("orders")
        if type(inventory) is not list or len(inventory) > width:
            _refuse("bounded native order inventory required")
        if "start" in page and "end" in page:
            if inventory and start >= length:
                _refuse("native rows outside page inventory domain")
            if len(inventory) != min(width, max(0, length - start)):
                complete = False
                reasons.append("order_inventory_incomplete")
        for key, authority in (("projectId", "project_id"), ("backtestId", "backtest_id")):
            if key in page and (type(page[key]) is not type(receipt.get(authority)) or page[key] != receipt.get(authority)):
                _refuse("foreign native order page identity")
        rows.extend(inventory)
        if len(rows) > 5000:
            _refuse("bounded native order inventory required")
    if total is None or len(rows) != total:
        complete = False
        reasons.append("order_inventory_incomplete")
    groups = {name: _empty_group() for name in _GROUPS}
    ids, event_ids, currency_totals = set(), set(), {}
    failures = 0
    for order in rows:
        if type(order) is not dict:
            _refuse("native order object required")
        oid = _id(order.get("id"))
        if oid in ids:
            _refuse("duplicate native order identity")
        ids.add(oid)
        if type(order.get("status")) is not int or order["status"] not in _STATUSES:
            _refuse("exact native order status required")
        group_name = _group(order)
        group = groups[group_name]
        group["orders"] += 1
        if (type(order.get("type")) is not int or order["type"] != 4
                or type(order.get("priceAdjustmentMode")) is not int or order["priceAdjustmentMode"] != 0
                or order.get("priceCurrency") != "USD"):
            reasons.append("non_moo_raw_usd_order")
        created = accounting._clock(order.get("createdTime"))
        if created.date().isoformat() not in accounting.DECISIONS or created.strftime("%H:%M:%S") != "09:20:00":
            reasons.append("order_clock_outside_frozen_schedule")
        quantity = _number(order.get("quantity"))
        if quantity == 0 or quantity.denominator != 1:
            _refuse("whole nonzero native order quantity required")
        group["submitted_shares"] += abs(quantity)
        events = order.get("events")
        if type(events) is not list or len(events) > 100:
            _refuse("bounded native order events required")
        order_fill = Fraction(0)
        for event in events:
            if type(event) is not dict:
                _refuse("native event object required")
            status = event.get("status")
            if not (type(status) is int and status in _STATUSES or type(status) is str and status in _EVENT_STATUSES):
                _refuse("exact known native event status required")
            if not _fill(event.get("status")):
                continue
            if _id(event.get("orderId")) != oid:
                _refuse("fill references a different native order")
            identity = _event_identity(event, oid, receipt)
            if identity in event_ids:
                _refuse("duplicate native fill event identity")
            event_ids.add(identity)
            amount, price = _number(event.get("fillQuantity")), _number(event.get("fillPrice"))
            if amount == 0 or amount.denominator != 1 or price <= 0 or (amount > 0) != (quantity > 0):
                _refuse("invalid native fill economics")
            native_final = (group_name == "engine_tagged_delisting_market" and order["status"] == 3
                and _filled(event["status"]) and quantity < 0 and amount == quantity
                and event.get("isAssignment") is False)
            order_currency = _currency(order, "priceCurrency", native_final)
            fill_currency = _currency(event, "fillPriceCurrency", native_final)
            if order_currency is None:
                reasons.append("native_order_currency_empty_or_missing")
            if fill_currency != "USD":
                reasons.append("non_usd_native_fill")
                group["native_fill_currency_unknown_fill_events"] += 1
                if fill_currency is None:
                    reasons.append("native_fill_currency_empty_or_missing")
            else:
                group["observed_usd_fill_notional"] += abs(amount) * price
            present = _FEE_KEYS.intersection(event)
            if any(type(key) is not str or "fee" in key.lower() and key not in _FEE_KEYS for key in event):
                _refuse("ambiguous native fee fields")
            if not present:
                if not native_final:
                    _refuse("unreported fee outside exact native final close")
                group["api_unreported_fee_events"] += 1
                reasons.extend(("api_unreported_native_fee", "native_fee_schedule_unverifiable"))
            elif present != _FEE_KEYS:
                _refuse("one-sided native fee fields")
            else:
                fee = _number(event["orderFeeAmount"])
                fee_currency = _currency(event, "orderFeeCurrency", False)
                if fee < 0:
                    _refuse("negative native fee")
                currency_totals[fee_currency] = currency_totals.get(fee_currency, Fraction(0)) + fee
                if fee_currency == "USD":
                    group["observed_fees"] += fee
                elif fee != 0:
                    group["non_usd_nonzero_fee_events"] += 1
                if fee_currency != "USD":
                    reasons.append("non_usd_native_fill")
                if fee != abs(amount) * accounting.PENNY:
                    reasons.append("native_fee_schedule_mismatch")
                label = ("zero_fee_qcc_fill_events" if fee == 0 and fee_currency == "QCC" else
                    "zero_fee_usd_fill_events" if fee == 0 and fee_currency == "USD" else "other_fee_or_currency_fill_events")
                group[label] += 1
                if group_name == "engine_tagged_delisting_market" and (fee != 0 or amount >= 0):
                    reasons.append("engine_tagged_market_economics_not_final_zero_fee_close")
            stamp = _number(event.get("time"))
            if stamp.denominator != 1:
                _refuse("whole native fill timestamp required")
            try:
                fill_clock = datetime.fromtimestamp(int(stamp), timezone.utc).astimezone(accounting.NY)
            except (ValueError, OverflowError, OSError):
                _refuse("invalid native fill timestamp")
            if fill_clock < created:
                _refuse("native fill precedes order creation")
            if fill_clock.date() != created.date() or not "09:30:00" <= fill_clock.strftime("%H:%M:%S") < "09:35:00":
                reasons.append("fill_clock_outside_frozen_schedule")
            order_fill += amount
            group["fill_events"] += 1
            group["filled_shares"] += abs(amount)
        if abs(order_fill) > abs(quantity):
            _refuse("native order overfilled")
        if order["status"] == 3 and order_fill == quantity:
            group["filled_orders"] += 1
        else:
            failures += 1
        if group_name == "engine_tagged_delisting_market" and (quantity >= 0 or order_fill != quantity or order["status"] != 3):
            reasons.append("engine_tagged_market_not_full_negative_close")
    aggregate = {key: sum((group[key] for group in groups.values()), Fraction(0))
        for key in ("filled_shares", "observed_fees", "observed_usd_fill_notional")}
    aggregate.update({key: sum(group[key] for group in groups.values()) for key in
        ("fill_events", "filled_orders", "api_unreported_fee_events", "non_usd_nonzero_fee_events", "native_fill_currency_unknown_fill_events")})
    if failures:
        reasons.append("unfilled_or_failed_native_orders")
    if not aggregate["fill_events"]:
        reasons.append("zero_trade_diagnostic")
    strategy, engine = groups[_GROUPS[0]], groups[_GROUPS[1]]
    if groups["unclassified"]["orders"]:
        reasons.append("unclassified_native_orders")
    if strategy["orders"] != counts["submitted_orders"] or strategy["submitted_shares"] != counts["submitted_shares"]:
        reasons.append("strategy_tagged_moo_summary_mismatch")
    if aggregate["fill_events"] != counts["fill_events"] or aggregate["filled_shares"] != counts["filled_shares"]:
        reasons.append("all_native_fill_summary_mismatch")
    if engine["fill_events"] != counts["native_final_delisting_compatibility_exceptions"]:
        reasons.append("native_final_compatibility_count_mismatch")
    if "Total Orders" not in stats:
        reasons.append("native_order_statistic_missing")
    elif _integer(stats["Total Orders"]) != len(rows):
        reasons.append("native_order_statistic_mismatch")
    statistic_fee = None
    if "Total Fees" not in stats:
        reasons.append("native_fee_statistic_missing")
    else:
        statistic_fee = _number(str(stats["Total Fees"]).removeprefix("$"))
        if statistic_fee < 0:
            _refuse("negative native fee statistic")
    strategy_known = complete and not strategy["api_unreported_fee_events"] and not strategy["non_usd_nonzero_fee_events"]
    summary_matches = strategy_known and summary_fee == strategy["observed_fees"]
    statistic_matches = strategy_known and statistic_fee is not None and statistic_fee == strategy["observed_fees"]
    if not summary_matches:
        reasons.append("known_strategy_fees_and_summary_mismatch_or_unknown")
    if not statistic_matches:
        reasons.append("known_strategy_fees_and_statistic_mismatch_or_unknown")
    fee_complete = complete and not aggregate["api_unreported_fee_events"] and not aggregate["non_usd_nonzero_fee_events"]
    notional_complete = complete and not aggregate["native_fill_currency_unknown_fill_events"]
    if fee_complete and summary_fee != aggregate["observed_fees"]:
        reasons.append("all_native_fill_summary_mismatch")
    if fee_complete and statistic_fee is not None and statistic_fee != aggregate["observed_fees"]:
        reasons.append("native_fee_statistic_mismatch")
    provenance = {"api_reported_usd_fee_subtotal": _text(aggregate["observed_fees"]),
        "api_reported_fee_totals_by_currency": {key: _text(value) for key, value in sorted(currency_totals.items())},
        "api_unreported_fee_events": aggregate["api_unreported_fee_events"], "all_native_fee_total_known": fee_complete,
        "all_native_fee_total": _text(aggregate["observed_fees"]) if fee_complete else None,
        "original_summary_fee_claim": _text(summary_fee), "original_qc_statistic_fee_claim": _text(statistic_fee) if statistic_fee is not None else None,
        "strategy_reported_usd_fee_subtotal": _text(strategy["observed_fees"]), "strategy_fee_evidence_complete": strategy_known,
        "summary_matches_reported_strategy_fees": summary_matches, "statistic_matches_reported_strategy_fees": statistic_matches,
        "unreported_fee_zero_attested": False, "unreported_fee_currency_attested": False}
    formatted_groups = {}
    for name, group in groups.items():
        values = {key: _text(value) if isinstance(value, Fraction) else value for key, value in group.items()}
        known = complete and not group["api_unreported_fee_events"] and not group["non_usd_nonzero_fee_events"]
        values.update(fees=values["observed_fees"] if known else None, native_fee_complete=known,
            fill_notional=values["observed_usd_fill_notional"] if complete and not group["native_fill_currency_unknown_fill_events"] else None,
            native_fee_fields_missing_fill_events=group["api_unreported_fee_events"])
        formatted_groups[name] = values
    observed = {key: _text(value) if isinstance(value, Fraction) else value for key, value in aggregate.items()}
    observed.update(orders=len(rows), observed_order_count=len(rows), order_inventory_complete=complete,
        fees=observed["observed_fees"] if fee_complete else None, native_fee_complete=fee_complete,
        fill_notional=observed["observed_usd_fill_notional"] if notional_complete else None,
        native_usd_notional_complete=notional_complete,
        native_fee_fields_missing_fill_events=aggregate["api_unreported_fee_events"],
        order_failures=failures, etf_instrument_execution=None)
    return {"orders": observed, "native_order_partition": {"inventory_complete": complete, **formatted_groups,
        "engine_tag_is_not_independent_custody_proof": True}, "fee_provenance": provenance}
