"""Pure supplied-evidence CMP28 account replay; no I/O or native authority.

Private journal chunks must remain in their authorized processing environment.
Native API envelopes/hashes describe supplied observations, not authentication.
A fractional held split makes cash-in-lieu unobserved permanently; this auditor
never learns the missing amount from a later cash snapshot. Chart agreement uses
LEAN's public SmartRounding contract, not a claim about deployed runtime code.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
from fractions import Fraction
import hashlib
import re
from zoneinfo import ZoneInfo

from . import comparison_20261028_completion as c
from . import extended_evidence as e
from . import extended_metrics as metrics
from . import extended_native as native
from . import extended_operations as collector

NY, UTC = ZoneInfo("America/New_York"), timezone.utc
MAX_ORDERS, MAX_EVENTS, MAX_PAGES = 50000, 250000, 2501
MAX_PAGE_BYTES, MAX_API_BYTES = 1024 * 1024, 32 * 1024 * 1024
INPUT_KEYS = frozenset(("schema", "project_id", "job_id", "config_sha256",
    "rendered_source_closure_sha256", "order_pages", "chart"))
MAX_COMPACT_BYTES, MAX_NAV_OBSERVATIONS = 16 * 1024, 2000
IDENTITY_KEYS = frozenset(("study_id", "candidate_id", "arm", "project_id", "job_id", "operation_id",
    "attempt", "config_sha256", "policy_sha256", "calendar_sha256", "source_template_closure_sha256",
    "rendered_source_closure_sha256", "terminal_evidence_sha256", "prior_attempts_looks_sha256"))
COMPACT_KEYS = frozenset(("schema", "identity", "completion_binding_sha256", "source_calendar_sha256",
    "api_input_binding_sha256", "ordered_api_envelopes_sha256", "api_order_page_count", "api_total_envelope_bytes",
    "normalizer_source_sha256", "event_multiset_sha256", "known_event_count", "native_order_census",
    "nonzero_fill_multiset_sha256", "known_nonzero_fill_count", "observed_nonzero_fees",
    "zero_fill_skeleton_sha256", "known_zero_fill_skeleton_count",
    "native_chart", "unknown_reasons", "native_origin_authenticated", "backend_durability_proven",
    "historical_pit_authenticated", "data_rights_authenticated", "share_basis_authenticated",
    "source_inputs_admitted", "strategy_accepted", "canonical_admission", "native_permission",
    "raw_api_pages_revalidated_in_child", "exact_journal_to_event_id_mapping_proven",
    "original_strategy_intent_verified", "moo_order_type_verified", "cancellation_policy_verified", "slippage_model_verified", "native_execution_timing_verified", "normalizer_source_custody_verified"))
NO_AUTHORITY = frozenset(("native_origin_authenticated", "backend_durability_proven", "historical_pit_authenticated",
    "data_rights_authenticated", "share_basis_authenticated", "source_inputs_admitted", "strategy_accepted",
    "canonical_admission", "native_permission", "raw_api_pages_revalidated_in_child",
    "exact_journal_to_event_id_mapping_proven", "original_strategy_intent_verified", "moo_order_type_verified",
    "cancellation_policy_verified", "slippage_model_verified", "native_execution_timing_verified", "normalizer_source_custody_verified"))
CENSUS_KEYS = frozenset(("orders", "events", "nonzero_fills", "absolute_filled_shares", "reported_fees",
    "currency_fields_complete", "currency_inference_performed"))
NATIVE_REASONS = frozenset(("missing_native_symbol_identity", "unobserved_native_events", "missing_native_event_identity",
    "missing_native_event_time", "missing_native_event_economics", "missing_or_non_usd_fill_currency",
    "missing_or_non_usd_fee_currency", "native_zero_fee_currency_unobserved", "native_daily_nav_chart_unavailable", "unobserved_zero_fill_fee"))
FILL_KEYS = frozenset(("order_id", "security_id", "utc", "status", "quantity", "price", "fee",
    "fee_currency", "native_final_exception", "cash_ledger", "quantity_ledger"))


class AccountingRefusal(ValueError):
    """Closed refusal; no private field or value is disclosed."""


def _fail():
    raise AccountingRefusal("CMP28 supplied account replay refused") from None


def _sid(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_. /-]{1,200}", value) is None:
        _fail()
    return value


def _microseconds(fraction):
    if fraction is None:
        return 0
    if (type(fraction) is not str or not 1 <= len(fraction) <= 64
            or re.fullmatch(r"[0-9]+", fraction) is None
            or any(digit != "0" for digit in fraction[6:])):
        _fail()
    return int(fraction[:6].ljust(6, "0"))


def _clock(value, *, warmup=False):
    """Exact aware calendar seconds; no lossy datetime ISO parser.

    Grammar: YYYY-MM-DD[Tt or space]HH:MM:SS[.fraction or ,fraction]
    followed by Z or signed HH:MM[:SS[.fraction or ,fraction]]. Both local
    and offset fractions must be exactly representable as microseconds;
    additional trailing zeroes are equivalent, nonzero finer digits refuse.
    """
    if type(value) is not str or len(value) > 64:
        _fail()
    match = re.fullmatch(
        r"(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})[Tt ]"
        r"(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
        r"(?:[.,](?P<fraction>[0-9]+))?"
        r"(?P<zone>Z|(?P<sign>[+-])(?P<offset_hour>[0-9]{2}):(?P<offset_minute>[0-9]{2})"
        r"(?::(?P<offset_second>[0-9]{2})(?:[.,](?P<offset_fraction>[0-9]+))?)?)", value)
    if match is None:
        _fail()
    microsecond = _microseconds(match["fraction"])
    offset_microsecond = _microseconds(match["offset_fraction"])
    try:
        zone = UTC
        if match["zone"] != "Z":
            hours, minutes, seconds = int(match["offset_hour"]), int(match["offset_minute"]), int(match["offset_second"] or "0")
            if hours > 23 or minutes > 59 or seconds > 59:
                _fail()
            offset = timedelta(hours=hours, minutes=minutes, seconds=seconds, microseconds=offset_microsecond)
            zone = timezone(-offset if match["sign"] == "-" else offset)
        instant = datetime(*(int(match[key]) for key in ("year", "month", "day", "hour", "minute", "second")),
            microsecond=microsecond, tzinfo=zone).astimezone(UTC)
    except (ValueError, OverflowError):
        _fail()
    first = datetime(2020, 9, 1, tzinfo=NY) if warmup else datetime(2021, 1, 4, tzinfo=NY)
    if not first <= instant < datetime(2026, 10, 10, tzinfo=NY):
        _fail()
    return instant


def _text(value):
    # Exact same presentation rule as frozen extended_core._text, not money math.
    value = Fraction(value)
    with localcontext(Context(prec=48)):
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def _smart_round(value):
    """Positive NAV: public LEAN SmartRounding, midpoint ties to even."""
    if value <= 0:
        _fail()
    if value > 1000:
        quantum = Fraction(1, 10000)
    else:
        exponent = len(str(value.numerator)) - len(str(value.denominator))
        power = Fraction(10 ** exponent) if exponent >= 0 else Fraction(1, 10 ** -exponent)
        if value < power:
            exponent -= 1
        quantum = Fraction(10 ** (exponent - 6)) if exponent >= 6 else Fraction(1, 10 ** (6 - exponent))
    scaled = value / quantum
    whole, remainder = divmod(scaled.numerator, scaled.denominator)
    if remainder * 2 > scaled.denominator or remainder * 2 == scaled.denominator and whole % 2:
        whole += 1
    return whole * quantum


def _envelope(raw, descriptor, endpoint, binding):
    c._load(raw, descriptor, MAX_PAGE_BYTES)
    return native._envelope(raw, descriptor["sha256"], endpoint, binding["project_id"], binding["job_id"])


def _orders(pages, descriptors, binding, sessions):
    if type(pages) is not list or type(descriptors) is not list or not 1 <= len(pages) == len(descriptors) <= MAX_PAGES:
        _fail()
    events, zero_skeleton, reasons, order_ids, event_ids, text_ids = Counter(), Counter(), Counter(), set(), set(), set()
    total, cursor, event_count, positive_fills, abs_fills = None, 0, 0, 0, Fraction(0)
    observed_fees, currencies_complete, fees_known, quantities_known = Fraction(0), True, True, True
    for page_number, (raw, descriptor) in enumerate(zip(pages, descriptors)):
        if page_number and cursor >= total:
            _fail()
        envelope = _envelope(raw, descriptor, "backtests/orders/read", binding)
        request, response = envelope["request"], envelope["response"]
        c._closed(request, ("projectId", "backtestId", "start", "end"))
        start, end = c._integer(request["start"], MAX_ORDERS), c._integer(request["end"], MAX_ORDERS + 100)
        if start != cursor or not 1 <= end - start <= 99:
            _fail()
        returned = c._integer(response.get("length"), MAX_ORDERS)
        if total is None:
            total = returned
        if total != returned or start > total:
            _fail()
        rows = response.get("orders")
        if type(rows) is not list or len(rows) != min(end - start, total - start):
            _fail()
        cursor += len(rows)
        for row in rows:
            if type(row) is not dict:
                _fail()
            oid = c._integer(row.get("id"), 2**63 - 1, 1)
            if oid in order_ids:
                _fail()
            order_ids.add(oid)
            sid = None if type(row.get("symbol")) is not dict else row["symbol"].get("id")
            if sid is None:
                reasons["missing_native_symbol_identity"] += 1
            else:
                sid = _sid(sid)
            created = _clock(row.get("time"))
            if created.astimezone(NY).date().isoformat() not in sessions:
                _fail()
            if row.get("createdTime") is not None and _clock(row["createdTime"]) != created:
                _fail()
            native._status(row.get("status"))
            rows_events = row.get("events")
            if rows_events is None or rows_events == []:
                reasons["unobserved_native_events"] += 1
                fees_known = quantities_known = False
                continue
            if type(rows_events) is not list or len(rows_events) > 4096:
                _fail()
            previous = None
            for event in rows_events:
                event_count += 1
                if event_count > MAX_EVENTS or type(event) is not dict:
                    _fail()
                known = sid is not None
                if event.get("algorithmId") is None or event.get("orderId") is None:
                    reasons["missing_native_event_identity"] += 1; known = False
                if event.get("algorithmId") is not None and event["algorithmId"] != binding["job_id"]:
                    _fail()
                if event.get("orderId") is not None and c._integer(event["orderId"]) != oid:
                    _fail()
                identity, text_id = event.get("orderEventId"), event.get("id")
                if identity is None and text_id is None:
                    reasons["missing_native_event_identity"] += 1; known = False
                if identity is not None:
                    identity = (oid, c._integer(identity))
                    if identity in event_ids:
                        _fail()
                    event_ids.add(identity)
                if text_id is not None:
                    e._id(text_id)
                    if text_id in text_ids:
                        _fail()
                    text_ids.add(text_id)
                instant = None if event.get("time") is None else native._instant(event["time"], epoch=True)
                if instant is None:
                    reasons["missing_native_event_time"] += 1; known = False
                elif (instant < created or previous is not None and instant < previous
                        or instant.astimezone(NY).date().isoformat() not in sessions):
                    _fail()
                previous = instant
                status = None if event.get("status") is None else native._status(event["status"], event=True)
                identity_known = known
                quantity, price, fee = (native._number(event.get(key)) for key in ("fillQuantity", "fillPrice", "orderFeeAmount"))
                fees_known &= fee is not None
                quantities_known &= quantity is not None
                if quantity is None or price is None or fee is None or status is None:
                    reasons["missing_native_event_economics"] += 1; known = False
                if quantity is not None and (quantity.denominator != 1 or quantity and status not in ("Filled", "PartiallyFilled")):
                    _fail()
                if price is not None and (price < 0 or quantity and price <= 0) or fee is not None and fee < 0:
                    _fail()
                fill_currency, fee_currency = native._currency(event.get("fillPriceCurrency")), native._currency(event.get("orderFeeCurrency"))
                raw_fee_currency = event.get("orderFeeCurrency")
                if quantity == 0 and identity_known and price is not None and status is not None:
                    zero_skeleton[(oid, sid, instant, status, quantity, price)] += 1
                if quantity == 0 and (fee is None or raw_fee_currency is None):
                    reasons["unobserved_zero_fill_fee"] += 1
                if quantity and fill_currency != "USD":
                    reasons["missing_or_non_usd_fill_currency"] += 1; known = False; currencies_complete = False
                if fee_currency != "USD":
                    currencies_complete = False
                    # Explicit native empty zero fee is retained as empty, never USD.
                    if raw_fee_currency == "" and fee == 0:
                        reasons["native_zero_fee_currency_unobserved"] += 1
                    else:
                        reasons["missing_or_non_usd_fee_currency"] += 1; known = False
                if quantity:
                    positive_fills += 1; abs_fills += abs(quantity)
                if fee is not None:
                    observed_fees += fee
                if known:
                    events[(oid, sid, instant, status, quantity, price, fee, raw_fee_currency)] += 1
    if cursor != total or len(order_ids) != total:
        _fail()
    return events, reasons, {"orders": total, "events": event_count, "nonzero_fills": positive_fills if quantities_known else None,
        "absolute_filled_shares": metrics._out(abs_fills) if quantities_known else None,
        "reported_fees": metrics._out(observed_fees) if fees_known else None,
        "currency_fields_complete": currencies_complete, "currency_inference_performed": False}, zero_skeleton


def _actions(group, quantities, cash, seen, sessions):
    parsed = []
    for row in group:
        action = row.get("action")
        c._closed(row, ("action", "security_id", "utc", "observation") if action == "delisting"
            else ("action", "security_id", "utc", "value", "occurred"))
        sid, instant = _sid(row["security_id"]), _clock(row["utc"], warmup=True)
        day = instant.astimezone(NY).date().isoformat()
        if action == "delisting":
            if type(row["observation"]) is not dict:
                _fail()
            continue  # No priced payoff; any liquidation must be an actual FILL.
        if action not in ("dividend", "split") or type(row["occurred"]) is not bool:
            _fail()
        value = c._fraction(row["value"])
        if action == "dividend" and row["occurred"] is not True or action == "split" and row["occurred"] and value <= 0:
            _fail()
        if not row["occurred"]:
            continue
        key = (action, sid, day)
        if key in seen:
            _fail()
        seen.add(key)
        if day >= sessions[0] and day not in sessions:
            _fail()
        parsed.append((action, sid, day, value))
    remainder_count = 0
    # The producer logs split before dividend AFTER core applies dividend first.
    for action, sid, day, value in sorted(parsed, key=lambda row: row[0] != "dividend"):
        if day < sessions[0]:
            continue
        before = quantities.get(sid, Fraction(0))
        if action == "dividend":
            if cash is not None:
                cash += before * value
        else:
            entitled = before / value
            quantities[sid] = Fraction(int(entitled))
            if entitled != int(entitled):
                remainder_count += 1; cash = None
    return cash, remainder_count


def _event_fingerprint(events, *, domain="all"):
    """Canonical sorted multiset commitment; no individual event is returned."""
    if domain not in ("all", "nonzero") or type(events) is not Counter or len(events) > MAX_EVENTS or sum(events.values()) > MAX_EVENTS:
        _fail()
    digest = hashlib.sha256(("tpr-cmp28-" + domain + "-event-multiset-v1\n").encode("ascii"))
    for (oid, sid, instant, status, quantity, price, fee, currency), count in sorted(events.items()):
        digest.update(e.canonical({"order_id": oid, "security_id": sid, "utc": instant.isoformat(), "status": status,
            "quantity": metrics._out(quantity), "price": metrics._out(price), "fee": metrics._out(fee),
            "fee_currency": currency, "multiplicity": c._integer(count, MAX_EVENTS, 1)}))
    return digest.hexdigest()


def _zero_fingerprint(events):
    """Zero-fill event observations only; no fee or lifecycle proof."""
    if type(events) is not Counter or len(events) > MAX_EVENTS or sum(events.values()) > MAX_EVENTS:
        _fail()
    digest = hashlib.sha256(b"tpr-cmp28-zero-fill-skeleton-v1\n")
    for (oid, sid, instant, status, quantity, price), count in sorted(events.items()):
        if quantity != 0:
            _fail()
        digest.update(e.canonical({"order_id": oid, "security_id": sid, "utc": instant.isoformat(), "status": status,
            "quantity": metrics._out(quantity), "price": metrics._out(price), "multiplicity": c._integer(count, MAX_EVENTS, 1)}))
    return digest.hexdigest()


def _nav_fingerprint(vector):
    """Canonical full-or-partial axis commitment, not a NAV-value export."""
    if type(vector) is not list or len(vector) > 1449:
        _fail()
    digest = hashlib.sha256(b"tpr-cmp28-rounded-nav-vector-v1\n")
    for day, nav in vector:
        digest.update(e.canonical({"session": day, "audit_utc": datetime.fromisoformat(day).replace(hour=16, minute=1, tzinfo=NY).astimezone(UTC).isoformat(),
            "rounded_nav": metrics._out(nav)}))
    return digest.hexdigest()


def _observation_identity(binding, source_calendar_raw):
    # Full completion validation occurs during audit_compact; normalization has
    # no private journal and does not fabricate its missing envelope contents.
    c._closed(binding, c.BINDING_KEYS)
    if (binding["schema"] != "tpr-cmp28-completion-binding-v1" or binding["study_id"] != c.STUDY
            or binding["arm"] not in c.CANDIDATES or binding["candidate_id"] != c.CANDIDATES[binding["arm"]]
            or type(binding["project_id"]) is not int or binding["project_id"] not in (37650980, 37650453)
            or binding["arm"] == "cap_off" and binding["project_id"] != 37650980
            or type(binding["job_id"]) is not str or re.fullmatch(r"[0-9a-f]{32}", binding["job_id"]) is None
            or type(binding["operation_id"]) is not str or re.fullmatch(r"TPR-CMP28-[A-Za-z0-9_.-]{1,150}", binding["operation_id"]) is None
            or type(binding["attempt"]) is not int or not 1 <= binding["attempt"] <= 2**31 - 1
            or binding["terminal_status"] != "Completed"):
        _fail()
    for key in IDENTITY_KEYS - {"study_id", "candidate_id", "arm", "project_id", "job_id", "operation_id", "attempt"}:
        c._hash(binding[key])
    c._closed(binding["envelopes"], c.ENVELOPES)
    c._load(source_calendar_raw, binding["envelopes"]["source_calendar"], c.ENVELOPES["source_calendar"])
    sessions = metrics._calendar(source_calendar_raw)
    return {key: binding[key] for key in IDENTITY_KEYS}, sessions


def normalize_api_observations(order_pages, chart_raw, api_binding, *, binding, source_calendar_raw, normalizer_source_sha256=None):
    """Normalize actual supplied API bytes into a small commitment packet.

    No source authenticity is inferred from the packet or its caller-provided
    hash. The external producer must retain and verify the full API envelopes,
    actual Completed receipt and exact public normalizer-module bytes. A source
    pin is caller-supplied metadata, not self-attestation; None supports only
    conditional software fixtures. Native use requires an external exact pin.
    """
    try:
        identity, sessions = _observation_identity(binding, source_calendar_raw)
        if normalizer_source_sha256 is not None:
            c._hash(normalizer_source_sha256)
        c._closed(api_binding, INPUT_KEYS)
        if api_binding["schema"] != "tpr-cmp28-accounting-inputs-v1":
            _fail()
        for key in ("project_id", "job_id", "config_sha256", "rendered_source_closure_sha256"):
            if not c._same(api_binding[key], binding[key]):
                _fail()
        if (type(order_pages) is not list or not 1 <= len(order_pages) <= MAX_PAGES
                or type(chart_raw) is not bytes or any(type(raw) is not bytes for raw in order_pages)
                or sum(map(len, order_pages)) + len(chart_raw) > MAX_API_BYTES):
            _fail()
        events, reasons, census, zero_skeleton = _orders(order_pages, api_binding["order_pages"], binding, sessions)
        envelope = _envelope(chart_raw, api_binding["chart"], "backtests/chart/read", binding)
        request = {"projectId": binding["project_id"], "backtestId": binding["job_id"], "name": "EXT26 Account NAV",
            "start": collector.CHART_START, "end": collector.CHART_END, "count": collector.CHART_COUNT}
        if not c._same(request, envelope["request"]):
            _fail()
        chart_census, series = collector._account_nav_chart(envelope["response"], sessions)
        vector = None if series is None else [(row["session"], metrics._exact(row["nav"])) for row in e.parse_json(series)]
        if vector is None:
            reasons["native_daily_nav_chart_unavailable"] += 1
        chain = hashlib.sha256(b"tpr-cmp28-ordered-api-envelopes-v1\n")
        for number, raw in enumerate(order_pages):
            chain.update(e.canonical({"kind": "orders", "ordinal": number, "bytes": len(raw), "sha256": c._sha(raw)}))
        chain.update(e.canonical({"kind": "chart", "ordinal": 0, "bytes": len(chart_raw), "sha256": c._sha(chart_raw)}))
        nonzero = Counter({key: count for key, count in events.items() if key[4]})
        compact = {"schema": "tpr-cmp28-compact-native-observations-v1", "identity": identity,
            "nonzero_fill_multiset_sha256": _event_fingerprint(nonzero, domain="nonzero"),
            "known_nonzero_fill_count": sum(nonzero.values()),
            "observed_nonzero_fees": (metrics._out(sum((key[6] * count for key, count in nonzero.items()), Fraction(0)))
                if census["nonzero_fills"] is not None and sum(nonzero.values()) == census["nonzero_fills"] else None),
            "zero_fill_skeleton_sha256": _zero_fingerprint(zero_skeleton),
            "known_zero_fill_skeleton_count": sum(zero_skeleton.values()),
            "normalizer_source_sha256": normalizer_source_sha256, "ordered_api_envelopes_sha256": chain.hexdigest(),
            "api_order_page_count": len(order_pages), "api_total_envelope_bytes": sum(map(len, order_pages)) + len(chart_raw),
            "completion_binding_sha256": c._sha(e.canonical(binding)), "source_calendar_sha256": metrics.CALENDAR_SHA256,
            "api_input_binding_sha256": c._sha(e.canonical(api_binding)), "event_multiset_sha256": _event_fingerprint(events),
            "known_event_count": sum(events.values()), "native_order_census": census,
            "native_chart": {"axis_complete": vector is not None, "observations": chart_census["observations"],
                "axis_vector_sha256": None if vector is None else _nav_fingerprint(vector)},
            "unknown_reasons": dict(sorted(reasons.items())), **dict.fromkeys(NO_AUTHORITY, False)}
        raw = e.canonical(compact)
        if len(raw) > MAX_COMPACT_BYTES:
            _fail()
        return raw
    except AccountingRefusal:
        raise
    except Exception:
        _fail()


def _compact(compact_raw, expected_sha256, binding, source_calendar_raw, expected_normalizer_source_sha256):
    identity, sessions = _observation_identity(binding, source_calendar_raw)
    body = c._load(compact_raw, {"sha256": expected_sha256, "bytes": len(compact_raw)}, MAX_COMPACT_BYTES)
    c._closed(body, COMPACT_KEYS)
    if expected_normalizer_source_sha256 is not None:
        c._hash(expected_normalizer_source_sha256)
    if (body["normalizer_source_sha256"] != expected_normalizer_source_sha256
            or body["schema"] != "tpr-cmp28-compact-native-observations-v1"
            or compact_raw != e.canonical(body) or not c._same(body["identity"], identity)
            or body["completion_binding_sha256"] != c._sha(e.canonical(binding))
            or body["source_calendar_sha256"] != metrics.CALENDAR_SHA256
            or any(body[key] is not False for key in NO_AUTHORITY)):
        _fail()
    for key in ("completion_binding_sha256", "source_calendar_sha256", "api_input_binding_sha256", "ordered_api_envelopes_sha256", "event_multiset_sha256", "nonzero_fill_multiset_sha256", "zero_fill_skeleton_sha256"):
        c._hash(body[key])
    c._integer(body["api_order_page_count"], MAX_PAGES, 1)
    c._integer(body["api_total_envelope_bytes"], MAX_API_BYTES, 1)
    c._closed(body["native_order_census"], CENSUS_KEYS)
    census = dict(body["native_order_census"])
    for key, maximum in (("orders", MAX_ORDERS), ("events", MAX_EVENTS)):
        census[key] = c._integer(census[key], maximum)
    known = c._integer(body["known_event_count"], census["events"])
    known_nonzero = c._integer(body["known_nonzero_fill_count"], known)
    known_zero = c._integer(body["known_zero_fill_skeleton_count"], census["events"])
    nonzero_fees = None if body["observed_nonzero_fees"] is None else c._fraction(body["observed_nonzero_fees"])
    if (nonzero_fees is not None and nonzero_fees < 0 or known_nonzero + known_zero > census["events"]
            or known - known_nonzero > known_zero):
        _fail()
    if not census["orders"] and census["events"]:
        _fail()
    if census["nonzero_fills"] is not None:
        census["nonzero_fills"] = c._integer(census["nonzero_fills"], census["events"])
    for key in ("absolute_filled_shares", "reported_fees"):
        if census[key] is not None:
            value = c._fraction(census[key])
            if value < 0:
                _fail()
            census[key] = metrics._out(value)
    if census["nonzero_fills"] is not None and (known_nonzero > census["nonzero_fills"]
            or known_zero > census["events"] - census["nonzero_fills"]):
        _fail()
    if (nonzero_fees is not None) != (census["nonzero_fills"] is not None and known_nonzero == census["nonzero_fills"]):
        _fail()
    if nonzero_fees is not None and census["reported_fees"] is not None and nonzero_fees > c._fraction(census["reported_fees"]):
        _fail()
    if (type(census["currency_fields_complete"]) is not bool or census["currency_inference_performed"] is not False
            or (census["nonzero_fills"] is None) != (census["absolute_filled_shares"] is None)
            or census["nonzero_fills"] is not None and c._fraction(census["absolute_filled_shares"]) < census["nonzero_fills"]):
        _fail()
    reasons = body["unknown_reasons"]
    if type(reasons) is not dict or not set(reasons) <= NATIVE_REASONS:
        _fail()
    reasons = Counter({key: c._integer(value, 2 * MAX_EVENTS + MAX_ORDERS, 1) for key, value in reasons.items()})
    if census["nonzero_fills"] is not None:
        zero_total = census["events"] - census["nonzero_fills"]
        missing_zero_fee = reasons["unobserved_zero_fill_fee"]
        if missing_zero_fee > zero_total or known - known_nonzero > zero_total - missing_zero_fee:
            _fail()
    if known != census["events"] and not any(reasons[key] for key in NATIVE_REASONS - {
            "native_daily_nav_chart_unavailable", "native_zero_fee_currency_unobserved", "unobserved_native_events"}):
        _fail()
    if (census["currency_fields_complete"] and any(reasons[key] for key in
            ("missing_or_non_usd_fill_currency", "missing_or_non_usd_fee_currency", "native_zero_fee_currency_unobserved"))):
        _fail()
    c._closed(body["native_chart"], ("axis_complete", "observations", "axis_vector_sha256"))
    chart = dict(body["native_chart"])
    if type(chart["axis_complete"]) is not bool:
        _fail()
    if chart["observations"] is not None:
        chart["observations"] = c._integer(chart["observations"], MAX_NAV_OBSERVATIONS)
    if chart["axis_complete"]:
        c._hash(chart["axis_vector_sha256"])
        if chart["observations"] != len(sessions) or reasons["native_daily_nav_chart_unavailable"]:
            _fail()
    elif chart["axis_vector_sha256"] is not None or reasons["native_daily_nav_chart_unavailable"] != 1:
        _fail()
    body.update(native_order_census=census, known_event_count=known, known_nonzero_fill_count=known_nonzero,
        known_zero_fill_skeleton_count=known_zero, observed_nonzero_fees=None if nonzero_fees is None else metrics._out(nonzero_fees),
        unknown_reasons=reasons, native_chart=chart)
    return body, sessions


def audit_accounting(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *,
                     binding, chunks, order_pages, chart_raw, api_binding, normalizer_source_sha256=None):
    """Compatibility wrapper: normalize supplied API bytes, then replay once."""
    compact = normalize_api_observations(order_pages, chart_raw, api_binding,
        binding=binding, source_calendar_raw=source_calendar_raw, normalizer_source_sha256=normalizer_source_sha256)
    return audit_compact(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw,
        binding=binding, chunks=chunks, compact_raw=compact, expected_compact_sha256=c._sha(compact),
        expected_normalizer_source_sha256=normalizer_source_sha256)


def audit_compact(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw, *,
                  binding, chunks, compact_raw, expected_compact_sha256, expected_normalizer_source_sha256=None):
    """Replay against commitments; caller hashes/pins are not native attestation.

    Native composition must independently verify the public normalizer source,
    retained raw API producer and actual terminal receipt, then supply both
    exact hashes. This pure consumer neither verifies that custody nor grants
    retrieval, rights or strategy acceptance.
    """
    try:
        observation, sessions = _compact(compact_raw, expected_compact_sha256, binding, source_calendar_raw, expected_normalizer_source_sha256)
        framing = c.replay_chunks(summary_raw, index_raw, config_raw, calendar_raw, source_calendar_raw,
            binding=binding, chunks=chunks)
        reasons, census = observation["unknown_reasons"], observation["native_order_census"]
        records = iter(e.parse_json(line) for raw in chunks for line in raw.splitlines())
        quantities, seen_actions, matched = {}, set(), Counter()
        cash, fees, max_cash, max_nav = Fraction(100000), Fraction(0), Fraction(0), Fraction(0)
        max_name, name_breaches, fills, absolute_shares, remainders = Fraction(0), 0, 0, Fraction(0), 0
        mismatches_total = risk_breaches = 0
        final_audit = datetime.fromisoformat(sessions[-1]).replace(hour=16, minute=1, tzinfo=NY).astimezone(UTC)
        quantity_ok = ledger_ok = cash_ok = nav_ok = chart_ok = True
        daily, nav_vector, prior_time, pending = [], [], None, None
        while True:
            record = pending if pending is not None else next(records, None)
            pending = None
            if record is None:
                break
            kind, row = record["kind"], record["payload"]
            if kind == "ACTION":
                instant = _clock(row.get("utc"), warmup=True)
                if instant > final_audit or prior_time is not None and instant < prior_time:
                    _fail()
                group = [row]
                while True:
                    candidate = next(records, None)
                    if candidate is None:
                        break
                    if candidate["kind"] != "ACTION" or _clock(candidate["payload"].get("utc"), warmup=True) != instant:
                        pending = candidate; break
                    group.append(candidate["payload"])
                cash, missing = _actions(group, quantities, cash, seen_actions, sessions)
                remainders += missing
                if missing:
                    reasons["unobserved_fractional_split_cash_in_lieu"] += missing
                prior_time = instant
            elif kind == "FILL":
                c._closed(row, FILL_KEYS)
                sid, instant = _sid(row["security_id"]), _clock(row["utc"])
                if (instant > final_audit or instant.astimezone(NY).date().isoformat() not in sessions
                        or prior_time is not None and instant < prior_time):
                    _fail()
                prior_time = instant
                oid, status = c._integer(row["order_id"], 2**63 - 1, 1), row["status"]
                if status not in metrics.STATUSES or type(row["native_final_exception"]) is not bool:
                    _fail()
                quantity, price, fee = (c._fraction(row[key]) for key in ("quantity", "price", "fee"))
                if quantity.denominator != 1 or fee < 0 or price < 0 or quantity and (price <= 0 or status not in ("Filled", "PartiallyFilled")):
                    _fail()
                currency = row["fee_currency"]
                if currency != "USD" and not (currency == "" and fee == 0 and (not quantity or row["native_final_exception"])):
                    _fail()
                matched[(oid, sid, instant, status, quantity, price, fee, currency)] += 1
                if quantity:
                    fills += 1; absolute_shares += abs(quantity)
                    quantities[sid] = quantities.get(sid, Fraction(0)) + quantity
                    if quantities[sid] < 0:
                        _fail()
                fees += fee
                if cash is not None:
                    cash -= quantity * price + fee
                    ledger_ok &= c._fraction(row["cash_ledger"]) == cash
                recorded = None if row["quantity_ledger"] is None else c._fraction(row["quantity_ledger"])
                quantity_ok &= recorded == quantities.get(sid)
            elif kind == "NAV" and "record_type" not in row:
                day = row["session"]
                audit_time = datetime.fromisoformat(day).replace(hour=16, minute=1, tzinfo=NY).astimezone(UTC)
                if prior_time is not None and audit_time < prior_time:
                    _fail()
                prior_time = audit_time
                held, marks = {}, {}
                for item in row["holdings"]:
                    c._closed(item, ("security_id", "quantity", "value")); sid = _sid(item["security_id"])
                    q, value = c._fraction(item["quantity"]), c._fraction(item["value"])
                    if sid in held or q <= 0 or q.denominator != 1 or value <= 0:
                        _fail()
                    held[sid] = (q, value)
                for item in row["raw_marks"]:
                    c._closed(item, ("security_id", "price", "mark_utc")); sid = _sid(item["security_id"])
                    price, stamp = c._fraction(item["price"]), _clock(item["mark_utc"])
                    if sid in marks or price <= 0 or stamp > audit_time or stamp.astimezone(NY).date().isoformat() != day:
                        _fail()
                    marks[sid] = price
                if set(marks) != set(held):
                    _fail()
                replayed = {sid: q for sid, q in quantities.items() if q}
                native_quantities = {sid: value[0] for sid, value in held.items()}
                mismatches = sum(replayed.get(sid, 0) != native_quantities.get(sid, 0)
                    for sid in set(replayed) | set(native_quantities))
                mismatches_total += mismatches
                quantity_ok &= mismatches == 0 and c._integer(row["position_ledger_mismatches"]) == mismatches
                if set(replayed) - set(marks):
                    _fail()
                independent = sum((q * marks[sid] for sid, q in replayed.items()), Fraction(0))
                native_held = sum((value for _, value in held.values()), Fraction(0))
                native_nav, native_cash = c._fraction(row["nav"], text=True), c._fraction(row["cash"], text=True)
                exposure = max((value / native_nav for _, value in held.values()), default=Fraction(0))
                max_name = max(max_name, exposure)
                name_breaches += sum(value / native_nav > Fraction(1, 10) for _, value in held.values())
                holding_residual = abs(native_held - independent)
                risk = native_cash >= -Fraction(1, 100) and 0 <= native_held <= native_nav + Fraction(1, 100)
                risk_breaches += not risk
                nav_ok &= all(abs(value - quantities.get(sid, Fraction(0)) * marks[sid]) <= Fraction(1, 100)
                    for sid, (_, value) in held.items())
                nav_ok &= (c._fraction(row["independent_holdings_value"]) == independent
                    and c._fraction(row["holdings_value_residual"]) == holding_residual
                    and row["gross_exposure"] == _text(native_held / native_nav)
                    and row["max_name_exposure"] == _text(exposure)
                    and c._fraction(row["fees"]) == fees
                    and row["risk_within_unlevered_account"] == risk)
                if cash is not None:
                    cr, nr = abs(native_cash - cash), max(abs(native_nav - cash - independent), holding_residual)
                    max_cash, max_nav = max(max_cash, cr), max(max_nav, nr)
                    ledger_ok &= c._fraction(row["cash_ledger"]) == cash
                    cash_ok &= cr <= Fraction(1, 100) and row["cash_ledger_residual"] == _text(cr)
                    nav_ok &= nr <= Fraction(1, 100) and row["nav_ledger_residual"] == _text(nr)
                daily.append(day)
                nav_vector.append((day, _smart_round(native_nav)))
        summary = e.parse_json(summary_raw)
        event_agreement = (_event_fingerprint(matched) == observation["event_multiset_sha256"]
            and sum(matched.values()) == observation["known_event_count"])
        native_agreement = (event_agreement and census["events"] == sum(matched.values())
            and census["orders"] == len({key[0] for key in matched})
            and census["nonzero_fills"] == fills
            and census["absolute_filled_shares"] is not None and c._fraction(census["absolute_filled_shares"]) == absolute_shares
            and census["reported_fees"] is not None and c._fraction(census["reported_fees"]) == fees)
        native_agreement = native_agreement and not any(reasons[key] for key in reasons if key not in ("native_daily_nav_chart_unavailable", "unobserved_fractional_split_cash_in_lieu", "native_zero_fee_currency_unobserved"))
        nonzero = Counter({key: count for key, count in matched.items() if key[4]})
        zero_skeleton = Counter()
        for key, count in matched.items():
            if not key[4]:
                zero_skeleton[key[:6]] += count
        nonzero_fee_agreement = (census["nonzero_fills"] is not None and observation["observed_nonzero_fees"] is not None
            and census["nonzero_fills"] == sum(nonzero.values()) == observation["known_nonzero_fill_count"]
            and c._fraction(census["absolute_filled_shares"]) == absolute_shares
            and _event_fingerprint(nonzero, domain="nonzero") == observation["nonzero_fill_multiset_sha256"]
            and sum((key[6] * count for key, count in nonzero.items()), Fraction(0)) == c._fraction(observation["observed_nonzero_fees"]))
        zero_observation_agreement = (census["nonzero_fills"] is not None
            and census["events"] - census["nonzero_fills"] == sum(zero_skeleton.values()) == observation["known_zero_fill_skeleton_count"]
            and _zero_fingerprint(zero_skeleton) == observation["zero_fill_skeleton_sha256"])
        zero_fee_complete = (census["nonzero_fills"] is not None
            and observation["known_event_count"] - observation["known_nonzero_fill_count"] == census["events"] - census["nonzero_fills"])
        if not event_agreement:
            reasons["native_journal_event_multiplicity_mismatch"] += 1
        full_axis = tuple(daily) == sessions
        chart_ok = (observation["native_chart"]["axis_complete"] and full_axis
            and _nav_fingerprint(nav_vector) == observation["native_chart"]["axis_vector_sha256"])
        summary_ok = (fills == c._integer(summary["fill_events"]) and absolute_shares == c._fraction(summary["filled_shares"])
            and fees == c._fraction(summary["fees"]) and max_name == c._fraction(summary["max_name_exposure"])
            and name_breaches == c._integer(summary["name_soft_cap_breaches"])
            and mismatches_total == c._integer(summary["position_ledger_mismatches"])
            and risk_breaches == c._integer(summary["risk_breaches"]))
        if cash is not None:
            summary_ok &= max_cash == c._fraction(summary["max_cash_residual"]) and max_nav == c._fraction(summary["max_nav_residual"])
        else:
            cash_ok = nav_ok = ledger_ok = False
        quantity_ok = bool(quantity_ok)
        ledger_ok, cash_ok, nav_ok, chart_ok = bool(ledger_ok), bool(cash_ok), bool(nav_ok), bool(chart_ok)
        reconciled = native_agreement and quantity_ok and ledger_ok and cash_ok and nav_ok and chart_ok and full_axis and summary_ok
        return {"schema": "tpr-cmp28-supplied-accounting-report-v1", "study_id": c.STUDY,
            "candidate_id": binding["candidate_id"], "arm": binding["arm"], "project_id": binding["project_id"],
            "job_id": binding["job_id"], "operation_id": binding["operation_id"], "attempt": binding["attempt"],
            "config_sha256": binding["config_sha256"], "journal_index_sha256": binding["envelopes"]["index"]["sha256"],
            "api_input_binding_sha256": observation["api_input_binding_sha256"], "native_order_census": census,
            "compact_observations_sha256": expected_compact_sha256, "normalizer_source_sha256": observation["normalizer_source_sha256"],
            "ordered_api_envelopes_sha256": observation["ordered_api_envelopes_sha256"],
            "native_journal_fill_fee_agreement": native_agreement,
            "native_nonzero_fill_fee_agreement": nonzero_fee_agreement,
            "native_zero_fill_event_observation_agreement": zero_observation_agreement,
            "native_zero_fill_fee_observation_complete": zero_fee_complete,
            "native_observed_nonzero_fees": observation["observed_nonzero_fees"],
            "quantity_replay_matches_journal": quantity_ok,
            "cash_replay_within_cent": ledger_ok and cash_ok, "daily_nav_replay_within_cent": nav_ok,
            "daily_nav_axis_complete": full_axis, "daily_nav_observations": len(daily),
            "native_chart_rounding_agreement": chart_ok, "summary_replayed_aggregates_agree": bool(summary_ok),
            "fractional_held_splits_with_unobserved_cash_in_lieu": remainders,
            "max_cash_residual": metrics._out(max_cash) if cash is not None else None,
            "max_nav_residual": metrics._out(max_nav) if cash is not None else None,
            "replayed_fees": metrics._out(fees), "replayed_position_mismatches": mismatches_total,
            "replayed_risk_breaches": risk_breaches, "supplied_evidence_accounting_reconciled": bool(reconciled),
            "unknown_reasons": dict(sorted(reasons.items())),
            "chart_rounding_basis": "public LEAN SmartRounding: positive >1000 four decimals, otherwise seven significant digits, ties to even; deployed implementation unverified",
            "journal_framing_replayed": framing["journal_framing_replayed"],
            "native_order_current_quantity_used_for_replay": False, "native_order_price_used_for_replay": False,
            "native_origin_authenticated": False, "backend_durability_proven": False,
            "historical_pit_authenticated": False, "data_rights_authenticated": False,
            "share_basis_authenticated": False, "full_evidence_retrieval_verified": False,
            "source_inputs_admitted": False, "strategy_accepted": False, "canonical_admission": False,
            "native_permission": False, "accepted_performance": None, "raw_api_pages_revalidated_in_child": False,
            "exact_journal_to_event_id_mapping_proven": False, "original_strategy_intent_verified": False,
            "moo_order_type_verified": False, "cancellation_policy_verified": False, "slippage_model_verified": False,
            "native_execution_timing_verified": False, "normalizer_source_custody_verified": False}
    except AccountingRefusal:
        raise
    except Exception:
        _fail()
