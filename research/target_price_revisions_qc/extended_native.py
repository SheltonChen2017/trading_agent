"""Pure normalization of explicitly retained own-account native API bytes.

No file, credential, provider, QC or outcome opener exists here. Supplied bytes,
request scope and hashes are bindings, not independent source authentication.
The existing collector alone owns native chart normalization; this module proves
exact byte parity with it. Missing events, fees, currencies and ambiguous share
bases remain null. Reported native Order.Quantity/Price are not original intent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import re
from zoneinfo import ZoneInfo

from . import extended_evidence as e
from . import extended_metrics as metrics
from . import extended_operations as collector

NativeError = e.EvidenceError
NY, UTC = ZoneInfo("America/New_York"), timezone.utc
MAX_ORDERS, PAGE_SIZE, MAX_EVENTS = 50000, 99, 4096
STATUS = {0: "New", 1: "Submitted", 2: "PartiallyFilled", 3: "Filled", 5: "Canceled",
          6: "None", 7: "Invalid", 8: "CancelPending", 9: "UpdateSubmitted"}
EVENT_STATUS = {name[0].lower() + name[1:]: name for name in STATUS.values()}
UNAVAILABLE = "unobserved_events missing_event_identity missing_event_time ambiguous_event_basis incomplete_fill_history missing_fill_observation missing_fee_observation".split()


def _fail():
    raise NativeError("native observations incomplete, inconsistent or outside exact collected scope")


def _ordinal(value, maximum, *, zero=True):
    if type(value) is not e.JsonNumber or re.fullmatch(r"0|[1-9][0-9]{0,18}", value.lexeme) is None:
        _fail()
    number = int(value.lexeme)
    if not (0 if zero else 1) <= number <= maximum: _fail()
    return number


def _status(value, *, event=False):
    if type(value) is e.JsonNumber:
        result = STATUS.get(_ordinal(value, 9))
    elif type(value) is str:
        result = value if value in STATUS.values() else EVENT_STATUS.get(value) if event else None
    else:
        result = None
    if result is None: _fail()
    return result


def _number(value):
    if value is None: return None
    if type(value) is not e.JsonNumber: _fail()
    result = value.fraction()
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > 4096: _fail()
    return result


def _currency(value):
    if value == "" and type(value) is str: return None  # Observed empty native field, not USD.
    if value is not None and (type(value) is not str or re.fullmatch(r"[A-Z][A-Z0-9]{0,11}", value) is None):
        _fail()
    return value


def _instant(value, *, epoch=False):
    if epoch:
        stamp = _number(value)
        if stamp is None or (stamp * 1000000).denominator != 1: _fail()
        try:
            result = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=int(stamp * 1000000))
        except (OverflowError, ValueError): _fail()
    else:
        if type(value) is not str or len(value) > 64: _fail()
        try: result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError: _fail()
        if result.tzinfo is None or result.utcoffset() is None: _fail()
        result = result.astimezone(UTC)
    if not datetime(2021, 1, 4, tzinfo=NY) <= result < datetime(2026, 10, 10, tzinfo=NY): _fail()
    return result


def _decimal_token(value):
    """Exact finite decimal aggregation, never context-rounded native authority."""
    value, denominator = Fraction(value), Fraction(value).denominator
    twos = fives = 0
    while denominator % 2 == 0: denominator //= 2; twos += 1
    while denominator % 5 == 0: denominator //= 5; fives += 1
    if denominator != 1: return None
    places = max(twos, fives)
    integer = value.numerator * (2 ** (places - twos)) * (5 ** (places - fives))
    text = str(abs(integer)).rjust(places + 1, "0")
    if places: text = text[:-places] + "." + text[-places:]
    return e.JsonNumber(("-" if integer < 0 else "") + text)


def _ratio(value):
    value = Fraction(value)
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def _vwap(value):
    token = _decimal_token(value)
    return token if token is not None else {"schema": "tpr-ext26-derived-fill-vwap-v1", **_ratio(value)}


def _binding(candidate_id, project_id, backtest_id, attempt):
    if (type(candidate_id) is not str or candidate_id not in e.CANDIDATES or type(project_id) is not int
            or type(attempt) is not int or not 1 <= attempt <= 3): _fail()
    e._integer(project_id); e._id(backtest_id)
    return {"candidate_id": candidate_id, "project_id": project_id, "backtest_id": backtest_id, "attempt": attempt}


def _envelope(raw, expected_sha256, endpoint, project_id, backtest_id):
    if e.digest(raw) != e._hash(expected_sha256): _fail()
    envelope = e.parse_json(raw)
    e._closed(envelope, {"schema", "endpoint", "request", "response", "returned_identity_checks"})
    if envelope["schema"] != "tpr-ext26-native-read-envelope-v1" or envelope["endpoint"] != endpoint: _fail()
    request, response = envelope["request"], envelope["response"]
    if (type(request) is not dict or e._integer(request.get("projectId")) != project_id
            or request.get("backtestId") != backtest_id or type(response) is not dict
            or response.get("success") is not True): _fail()
    checks = collector._returned_identity(response, project_id, backtest_id)
    if e.canonical(checks) != e.canonical(envelope["returned_identity_checks"]): _fail()
    return envelope


@dataclass(frozen=True)
class NormalizedOrders:
    pages: tuple[bytes, ...]
    observations: tuple[bytes, ...]
    public: bytes


def normalize_nav(series_raw, envelope_raw, calendar_raw, *, expected_series_sha256,
                  expected_envelope_sha256, candidate_id, project_id, backtest_id, attempt):
    """Reuse collector's chart oracle; no alternate clock or interpolation path."""
    binding = _binding(candidate_id, project_id, backtest_id, attempt)
    sessions = metrics._calendar(calendar_raw)
    metrics._series(series_raw, expected_series_sha256, sessions)
    envelope = _envelope(envelope_raw, expected_envelope_sha256, "backtests/chart/read", project_id, backtest_id)
    expected = {"projectId": project_id, "backtestId": backtest_id, "name": "EXT26 Account NAV",
                "start": collector.CHART_START, "end": collector.CHART_END, "count": collector.CHART_COUNT}
    if e.canonical(envelope["request"]) != e.canonical(expected): _fail()
    census, original = collector._account_nav_chart(envelope["response"], sessions)
    if original is None or original != series_raw or census["complete_daily_account_nav"] is not True: _fail()
    return series_raw, e.canonical({"schema": "tpr-ext26-normalized-native-nav-v1", "study_id": e.STUDY_ID,
        **binding, "calendar_sha256": metrics.CALENDAR_SHA256, "envelope_sha256": e.digest(envelope_raw),
        "normalized_series_sha256": e.digest(series_raw), "observations": len(sessions),
        "first_session": sessions[0], "last_session": sessions[-1], "observation_clock": "16:01:00 America/New_York",
        "native_numeric_tokens_preserved": True, "provider_authenticity_attested": False,
        "private_journal_replay_verified": False, "new_looks": 0, "quantconnect_attempts": 0})


def _events(row, order_id, job, created, session, status, quantity, sessions):
    native = row.get("events")
    empty = {"fill_quantity": None, "fill_price": None, "fill_currency": None,
             "reported_fee": None, "fee_currency": None}
    reasons, observations = set(), []
    if native is None or native == []:
        return empty, observations, {"unobserved_events"}, 0, None
    if type(native) is not list or len(native) > MAX_EVENTS: _fail()
    ids, textual_ids, quantities, notionals, fees, fill_currencies, fee_currencies = set(), set(), [], [], [], set(), set()
    fill_known = fee_known = basis_known = True
    last_time = None
    for event in native:
        if type(event) is not dict: _fail()
        identity = event.get("orderEventId")
        text_id = event.get("id")
        if identity is None and text_id is None:
            reasons.add("missing_event_identity"); basis_known = False
        if identity is not None:
            identity = _ordinal(identity, 2**63 - 1)
            if identity in ids: _fail()
            ids.add(identity)
        if text_id is not None:
            e._id(text_id)
            if text_id in textual_ids: _fail()
            textual_ids.add(text_id)
        observed_order, algorithm = event.get("orderId"), event.get("algorithmId")
        if observed_order is None or algorithm is None:
            reasons.add("missing_event_identity"); basis_known = False
        if observed_order is not None and e._integer(observed_order) != order_id: _fail()
        if algorithm is not None and e._id(algorithm) != job: _fail()
        event_status = None if event.get("status") is None else _status(event["status"], event=True)
        if event.get("time") is None:
            instant = None; reasons.add("missing_event_time"); basis_known = False
        else:
            instant = _instant(event["time"], epoch=True)
            event_session = instant.astimezone(NY).date().isoformat()
            if event_session not in sessions or instant < created or last_time is not None and instant < last_time: _fail()
            last_time = instant
            if event_session != session: reasons.add("ambiguous_event_basis"); basis_known = False
        observed_basis = _number(event.get("quantity"))
        if observed_basis is None or observed_basis != quantity:
            reasons.add("ambiguous_event_basis"); basis_known = False
        filled, price, fee = (_number(event.get(key)) for key in ("fillQuantity", "fillPrice", "orderFeeAmount"))
        fill_currency, fee_currency = _currency(event.get("fillPriceCurrency")), _currency(event.get("orderFeeCurrency"))
        if filled is None or (filled and (price is None or fill_currency is None)):
            fill_known = False; reasons.add("missing_fill_observation")
        if filled is not None:
            if filled.denominator != 1 or filled and (not quantity or (filled > 0) != (quantity > 0)): _fail()
            if filled and event_status is not None and event_status not in ("Filled", "PartiallyFilled"): _fail()
            quantities.append(filled)
            if filled:
                if price is not None and price <= 0: _fail()
                if price is not None: notionals.append(filled * price)
                if fill_currency is not None: fill_currencies.add(fill_currency)
        if fee is None or fee_currency is None:
            fee_known = False; reasons.add("missing_fee_observation")
        if fee is not None:
            if fee < 0: _fail()
            fees.append(fee)
            if fee_currency is not None: fee_currencies.add(fee_currency)
        observations.append({key: event.get(key) for key in ("orderId", "algorithmId", "orderEventId", "id", "time",
            "status", "quantity", "fillQuantity", "fillPrice", "fillPriceCurrency", "orderFeeAmount", "orderFeeCurrency")})
        if event_status is None: basis_known = False; reasons.add("missing_event_identity")
    amount = sum(quantities, Fraction(0))
    if (status == "Filled" and (not fill_known or amount != quantity)
            or status == "PartiallyFilled" and (not fill_known or not 0 < abs(amount) < abs(quantity))
            or abs(amount) > abs(quantity)):
        reasons.add("incomplete_fill_history"); basis_known = False
    if len(fill_currencies) > 1 or len(fee_currencies) > 1:
        reasons.add("ambiguous_event_basis"); basis_known = False
    result = dict(empty)
    if basis_known and fill_known:
        result["fill_quantity"] = _decimal_token(amount)
        if amount:
            result["fill_price"] = _vwap(sum(notionals, Fraction(0)) / amount)
            result["fill_currency"] = next(iter(fill_currencies))
    if basis_known and fee_known:
        result["reported_fee"] = _decimal_token(sum(fees, Fraction(0)))
        result["fee_currency"] = next(iter(fee_currencies))
    notional = _ratio(sum(notionals, Fraction(0))) if basis_known and fill_known else None
    return result, observations, reasons, len(native), notional


def normalize_orders(page_envelopes, collection_raw, calendar_raw, *, expected_collection_sha256,
                     candidate_id, project_id, backtest_id, attempt):
    """Normalize complete collected pages without manufacturing missing native facts.

    Fill VWAP is explicitly derived from observed events, never NativeOrder.Price.
    Same-day reported event quantities must equal the reported current order
    quantity; missing/post-split or cross-session basis stays unavailable. This
    coherent observed basis is not historical RAW/PIT or complete journal proof.
    """
    binding = _binding(candidate_id, project_id, backtest_id, attempt)
    sessions = metrics._calendar(calendar_raw)
    if e.digest(collection_raw) != e._hash(expected_collection_sha256): _fail()
    collection = e.parse_json(collection_raw)
    e._closed(collection, {"schema", "candidate_id", "attempt", "backtest_id", "order_count", "pages", "strategy_accepted", "new_looks"})
    if (collection["schema"] != "tpr-ext26-order-collection-v1" or collection["candidate_id"] != candidate_id
            or _ordinal(collection["attempt"], 3, zero=False) != attempt or collection["backtest_id"] != backtest_id
            or collection["strategy_accepted"] is not False or _ordinal(collection["new_looks"], 0) != 0): _fail()
    total = _ordinal(collection["order_count"], MAX_ORDERS)
    expected_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if (type(page_envelopes) is not list or type(collection["pages"]) is not list
            or len(page_envelopes) != expected_pages or len(collection["pages"]) != expected_pages): _fail()
    pages, observations, ids = [], [], set()
    statuses = dict.fromkeys(STATUS.values(), 0)
    reasons, events, missing_fill, missing_fee, derived = dict.fromkeys(UNAVAILABLE, 0), 0, 0, 0, 0
    for page_index, (raw, descriptor) in enumerate(zip(page_envelopes, collection["pages"])):
        e._closed(descriptor, {"start", "end", "response_projection_sha256", "request_response_envelope_sha256", "returned_identity_checks"})
        start, end = _ordinal(descriptor["start"], MAX_ORDERS + PAGE_SIZE), _ordinal(descriptor["end"], MAX_ORDERS + PAGE_SIZE)
        if (start, end) != (page_index * PAGE_SIZE, (page_index + 1) * PAGE_SIZE): _fail()
        envelope = _envelope(raw, descriptor["request_response_envelope_sha256"], "backtests/orders/read", project_id, backtest_id)
        expected_request = {"projectId": project_id, "backtestId": backtest_id, "start": start, "end": end}
        if (e.canonical(envelope["request"]) != e.canonical(expected_request)
                or e.canonical(envelope["returned_identity_checks"]) != e.canonical(descriptor["returned_identity_checks"])): _fail()
        response = envelope["response"]
        if e.digest(e.canonical(response)) != e._hash(descriptor["response_projection_sha256"]): _fail()
        native = response.get("orders")
        if (type(native) is not list or len(native) != min(PAGE_SIZE, total - start)
                or _ordinal(response.get("length"), MAX_ORDERS) != total): _fail()
        normalized, observed = [], []
        for row in native:
            if type(row) is not dict: _fail()
            order_id = e._integer(row.get("id"))
            if order_id in ids: _fail()
            ids.add(order_id)
            created = _instant(row.get("time"))
            if row.get("createdTime") is not None and _instant(row["createdTime"]) != created: _fail()
            session = created.astimezone(NY).date().isoformat()
            if session not in sessions: _fail()
            quantity = _number(row.get("quantity"))
            if quantity is None or quantity.denominator != 1: _fail()
            status = _status(row.get("status")); statuses[status] += 1
            price, currency = _number(row.get("price")), _currency(row.get("priceCurrency"))
            aggregate, event_rows, unavailable, count, notional = _events(row, order_id, backtest_id, created, session, status, quantity, sessions)
            events += count
            for reason in unavailable: reasons[reason] += 1
            missing_fill += aggregate["fill_quantity"] is None or aggregate["fill_quantity"].fraction() != 0 and aggregate["fill_currency"] is None
            missing_fee += aggregate["reported_fee"] is None or aggregate["fee_currency"] is None
            derived += type(aggregate["fill_price"]) is dict
            normalized.append({"order_id": order_id, "session": session, "status": status,
                               "requested_quantity": row["quantity"], **aggregate})
            observed.append({"order_id": order_id, "created_utc": created.isoformat(), "reported_order_price": row.get("price"),
                "reported_order_price_currency": currency, "reported_order_quantity": row["quantity"], "events": event_rows,
                "observed_event_fill_notional": notional,
                "unavailable_reasons": sorted(unavailable), "normalized": normalized[-1],
                "share_basis": "reported same-session current order/event quantity, not original strategy intent"})
        pages.append(e.canonical(normalized)); observations.append(e.canonical(observed))
    if len(ids) != total: _fail()
    public = {"schema": "tpr-ext26-normalized-native-orders-v1", "study_id": e.STUDY_ID, **binding,
        "calendar_sha256": metrics.CALENDAR_SHA256, "collection_sha256": e.digest(collection_raw),
        "page_count": len(pages), "order_count": total, "status_counts": statuses,
        "native_event_count": events, "unavailable_order_counts": reasons,
        "orders_missing_fill_observations": missing_fill, "orders_missing_fee_observations": missing_fee,
        "derived_rational_vwap_orders": derived, "normalized_page_sha256": [e.digest(raw) for raw in pages],
        "observation_page_sha256": [e.digest(raw) for raw in observations],
        "orders_sha256": metrics.order_pages_identity(pages), "original_strategy_intent_verified": False,
        "private_journal_replay_verified": False, "provider_authenticity_attested": False,
        "new_looks": 0, "quantconnect_attempts": 0}
    return NormalizedOrders(tuple(pages), tuple(observations), e.canonical(public))
