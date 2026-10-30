"""Pure fixed Sharadar RAW price acquisition plan and supplied CSV validation.

This has no file, credential, HTTP, QC, publication or retry interface. A future
one-use caller must authenticate source bytes/security and retain secret-scanned
HTTP200 bodies before parsing. Prices remain qualified current-vintage source
observations, never executable quotes, formal/PIT evidence or price admission.
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
import re
import time

from scripts import arv2_r298_price_lineage_routes as ac
from research.analyst_revisions_v2_qc import newrule_native_price_source_diagnostic as native

SCHEMA = "arv2-r298-raw-price-acquisition-v1"
PLAN_PRIVATE_SCHEMA = SCHEMA + "-private-plan"
REQUEST_SCHEMA = SCHEMA + "-private-request"
RESPONSE_SCHEMA = SCHEMA + "-response"
RESPONSE_PRIVATE_SCHEMA = SCHEMA + "-private-response"
FIRST, LAST = "2020-12-31", "2026-10-13"
FIELDS = ("ticker", "date", "closeunadj", "lastupdated")
ENDPOINTS = {table: "https://api.sharadar.com/v1.0/data/" + table for table in ("stocks", "funds")}
STOCK_WINDOWS = (("2020-12-31", "2021-12-31"), ("2022-01-01", "2022-12-31"),
    ("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"),
    ("2025-01-01", "2025-12-31"), ("2026-01-01", "2026-10-13"))
FUND_WINDOWS = (("2020-12-31", "2023-12-31"), ("2024-01-01", "2026-10-13"))
AC_SUMMARY_SHA256 = "112daa665daefaaef723e3fd3379196f4d85a7d920f80edf0b9d0fdb063ee5ef"
NATIVE_SPECIFICATION_SHA256 = "9da6813b4807d7ebf0ea32fddd38ab0740ff6c6edbc3bd05cdc5889775eb1f66"
FULL_AXIS_SHA256 = "4ac84a2d01e18691a152812851857195ef56dac16b82ceb72bcf7dd068f86585"
FULL_AXIS_COUNT, PRICE_SESSION_COUNT = 3466, 1452
VENDOR_STOCK_COUNT, NATIVE_STOCK_COUNT, CONDITIONAL_COUNT, FUND_COUNT = 5636, 5, 510, 8
MAX_TICKERS, ROW_LIMIT, MAX_SOURCE_BYTES, MAX_BODY_BYTES = 27, 10000, 32 * 1024 * 1024, 4 * 1024 * 1024
MAX_PRIVATE_BYTES, MAX_PRICE_TEXT, MAX_SUMMARY_BYTES = 16 * 1024 * 1024, 128, 16384
FALSE_FLAGS = {"provider_contact": False, "credential_access": False, "QC_contact": False,
    "vendor_quota_or_rate_proven": False, "price_input_admitted": False,
    "complete_price_coverage_proven": False, "native_five_source_admitted": False,
    "conditional_never_is_unconditional": False, "initial_or_terminal_holdings_proven": False,
    "terminal_payoff_proven": False, "source_rights_granted": False, "QC_processing_rights_granted": False,
    "executable_quote_substitution": False, "point_in_time_proven": False,
    "formal_identity_admitted": False, "formal_forward_ready": False, "paper_or_live_ready": False}
FINITE = frozenset(("deadline", "ac_summary", "ac_pin", "ac_json", "ac_record", "native_specification",
    "axis", "assignment", "route_collision", "plan_bound", "plan", "request", "http_status",
    "failed_body", "csv", "header", "row_shape", "row_bound", "ticker", "price_date",
    "duplicate_price", "sort", "price_value", "lastupdated", "summary", "unknown"))
TICKER = ac.routes.current.previous.composer._TICKER
PRICE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_SOURCE_PINS = {"scripts/arv2_r298_price_lineage_routes.py": "5a7a289a9f09cc30dc2155a00d23726cb8238d75993cb6d7c40049862e977d5a",
    "research/analyst_revisions_v2_qc/newrule_native_price_source_diagnostic.py":
        "57450eac9126831bc9d1c106325ed1832c10ba32e883563bb85e10060948e697"}


class Refused(ValueError):
    """Finite predicates only; never a route, price or raw exception."""


def require(value, code):
    if not value: raise Refused(code)


def finite(error):
    args = BaseException.args.__get__(error) if type(error) is Refused else ()
    return args[0] if len(args) == 1 and type(args[0]) is str and args[0] in FINITE else "unknown"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


def _hash(value):
    return type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None


def _deadline(value):
    if value is not None:
        require(type(value) in (int, float) and math.isfinite(value) and time.monotonic() < value, "deadline")


def _date(value, code):
    require(type(value) is str and len(value) == 10 and value.isascii(), code)
    try: parsed = date.fromisoformat(value)
    except ValueError: raise Refused(code) from None
    require(parsed.isoformat() == value, code)
    return parsed


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "ac_json")
        result[key] = value
    return result


def _source_ac(raw, expected):
    require(type(expected) is dict and digest(expected) == AC_SUMMARY_SHA256, "ac_summary")
    try: summary = ac.validate_summary(expected)
    except Exception: raise Refused("ac_summary") from None
    require(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE_BYTES
        and len(raw) == summary["private_frame_byte_count"] and sha(raw) == summary["private_frame_sha256"], "ac_pin")
    try:
        record = json.loads(raw.decode("ascii"), object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(Refused("ac_json")))
        require(canonical(record) == raw, "ac_json")
    except Refused: raise
    except (ValueError, UnicodeError, RecursionError): raise Refused("ac_json") from None
    try: return ac.validate_private_record(record, expected_summary=summary)
    except Exception: raise Refused("ac_record") from None


def _native_specification(value):
    try: checked = native.validate_specification(value)
    except Exception: raise Refused("native_specification") from None
    require(digest(checked) == NATIVE_SPECIFICATION_SHA256, "native_specification")
    return checked


def _axis(values):
    require(type(values) in (tuple, list) and len(values) == FULL_AXIS_COUNT
        and all(type(value) is str for value in values) and list(values) == sorted(set(values))
        and digest(list(values)) == FULL_AXIS_SHA256, "axis")
    for value in values: _date(value, "axis")
    sessions = [value for value in values if FIRST <= value <= LAST]
    require(len(sessions) == PRICE_SESSION_COUNT and sessions[0] == FIRST and sessions[-1] == LAST, "axis")
    return sessions


def _parameters(tickers, window):
    return {"ticker": ",".join(tickers), "from": window[0], "to": window[1],
        "fields": ",".join(FIELDS), "format": "csv", "limit": str(ROW_LIMIT), "skip": "0", "sort": "date.asc"}


class _PrivateValue:
    __slots__ = ("_raw", "sha256", "byte_count")
    def __init__(self, record):
        raw = canonical(record); require(0 < len(raw) <= MAX_PRIVATE_BYTES, "plan_bound")
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "sha256", sha(raw))
        object.__setattr__(self, "byte_count", len(raw))
    def __setattr__(self, name, value): raise TypeError("private price acquisition data are immutable")
    def __repr__(self): return "<Private price acquisition data redacted; no authority or raw serializer>"
    def __reduce_ex__(self, protocol): raise TypeError("private price acquisition data need a separately frozen consumer")


class PrivatePriceRequest(_PrivateValue):
    __slots__ = ()


class PrivateAcquisitionPlan(_PrivateValue):
    __slots__ = ()
    def request(self, ordinal):
        require(type(ordinal) is int, "request")
        require(sha(self._raw) == self.sha256 and len(self._raw) == self.byte_count, "plan")
        record = json.loads(self._raw)
        require(0 <= ordinal < len(record["requests"]), "request")
        item = record["requests"][ordinal]
        sessions = [value for value in record["price_sessions"] if item["first"] <= value <= item["last"]]
        return PrivatePriceRequest({"schema": REQUEST_SCHEMA, "plan_sha256": self.sha256,
            "request_ordinal": ordinal, "table": item["table"], "tickers": item["tickers"],
            "endpoint": ENDPOINTS[item["table"]],
            "first": item["first"], "last": item["last"], "parameters": item["parameters"],
            "expected_sessions": sessions})


class PrivatePriceResponse(_PrivateValue):
    __slots__ = ()


def prepare_plan(ac_raw, *, expected_ac_summary, native_specification, session_axis, deadline=None):
    """Authenticate supplied AC metadata; no read/contact or source grant occurs."""
    _deadline(deadline)
    record = _source_ac(ac_raw, expected_ac_summary)
    spec, sessions = _native_specification(native_specification), _axis(session_axis)
    require(type(record) is dict and type(record["stocks"]) is list
        and len(record["stocks"]) == VENDOR_STOCK_COUNT + NATIVE_STOCK_COUNT + CONDITIONAL_COUNT
        and type(record["funds"]) is list and len(record["funds"]) == FUND_COUNT, "assignment")
    assignments, stocks, funds, pending, seen = [], [], [], [], set()
    for ordinal, item in enumerate(record["stocks"]):
        _deadline(deadline)
        require(item["binding_ordinal"] == ordinal and type(item["potential"]) is bool
            and item["conditional_never_potential"] is (not item["potential"]), "assignment")
        binding = item["binding"]; whole_pin = digest(binding)
        require(type(binding["security_id"]) is str and _hash(binding["row_sha256"])
            and binding["security_id"] not in seen, "assignment")
        seen.add(binding["security_id"])
        entry = {"binding_ordinal": ordinal, "security_id": binding["security_id"],
            "whole_binding_sha256": whole_pin, "semantic_binding_sha256": binding["row_sha256"],
            "role": None, "table": None, "ticker": None, "refusal_reason": item["reason"]}
        if not item["potential"]:
            require(item["disposition"] == "conditional_never_potential" and item["query_window"] is None, "assignment")
            entry["role"] = "conditional_never_potential_empty_initial_holdings_required"
        elif item["disposition"] == "refused":
            require(item["route"] is None and item["reason"] in ("identity_missing", "global_collision")
                and item["query_window"] is None, "assignment")
            pending.append(whole_pin); entry["role"] = "pending_native_original_identity_source"
        else:
            require(item["disposition"] == "routed" and item["reason"] is None
                and item["query_window"] == [FIRST, LAST] and item["route"]["table"] == "stocks", "assignment")
            ticker = item["route"]["current_metadata_row"]["ticker"]
            require(type(ticker) is str and TICKER.fullmatch(ticker) is not None
                and item["route"]["current_metadata_row"]["currency"] == "USD", "assignment")
            entry.update(role="Sharadar_RAW_full_window", table="stocks", ticker=ticker)
            stocks.append(ticker)
        assignments.append(entry)
    require(len(stocks) == VENDOR_STOCK_COUNT and len(pending) == NATIVE_STOCK_COUNT
        and sorted(pending) == spec["selected_whole_binding_sha256s"]
        and len(stocks) == len(set(stocks)), "route_collision")
    require(sum(item["role"].startswith("conditional_never") for item in assignments) == CONDITIONAL_COUNT, "assignment")
    for ordinal, item in enumerate(record["funds"]):
        require(item["fund_ordinal"] == ordinal and item["disposition"] == "routed"
            and item["reason"] is None and item["query_window"] == [FIRST, LAST]
            and item["route"]["table"] == "funds", "assignment")
        row = item["route"]["current_metadata_row"]
        ticker = row["ticker"]
        require(type(ticker) is str and TICKER.fullmatch(ticker) is not None and row["currency"] == "USD", "assignment")
        funds.append(ticker)
        assignments.append({"fund_ordinal": ordinal, "own_ETF": item["ticker"],
            "role": "Sharadar_RAW_full_window", "table": "funds", "ticker": ticker,
            "route_sha256": digest(item["route"])})
    require(len(set(funds)) == FUND_COUNT and not set(stocks) & set(funds), "route_collision")
    requests = []
    for table, tickers, windows, group_size in (("stocks", sorted(stocks), STOCK_WINDOWS, MAX_TICKERS),
            ("funds", sorted(funds), FUND_WINDOWS, FUND_COUNT)):
        for offset in range(0, len(tickers), group_size):
            group = tickers[offset:offset + group_size]
            for first, last in windows:
                _deadline(deadline)
                calendar_bound = len(group) * ((_date(last, "request") - _date(first, "request")).days + 1)
                require(calendar_bound < ROW_LIMIT, "request")
                requests.append({"ordinal": len(requests), "table": table, "tickers": group,
                    "first": first, "last": last, "calendar_key_bound": calendar_bound,
                    "parameters": _parameters(group, (first, last))})
    private = PrivateAcquisitionPlan({"schema": PLAN_PRIVATE_SCHEMA,
        "ac_summary_sha256": digest(expected_ac_summary),
        "ac_frame_pin": {"byte_count": len(ac_raw), "sha256": sha(ac_raw)},
        "native_specification_sha256": digest(spec), "full_axis_sha256": FULL_AXIS_SHA256,
        "price_sessions": sessions, "assignments": assignments, "requests": requests})
    summary = {"schema": SCHEMA, "scope": "fixed_full_window_source_observation_plan_not_price_admission",
        "ac_summary_sha256": digest(expected_ac_summary), "ac_frame_pin": {"byte_count": len(ac_raw), "sha256": sha(ac_raw)},
        "native_specification_sha256": digest(spec), "full_axis_sha256": FULL_AXIS_SHA256,
        "stock_binding_count": len(record["stocks"]), "vendor_stock_count": len(stocks),
        "pending_native_stock_count": len(pending), "conditional_stock_count": CONDITIONAL_COUNT,
        "fund_count": len(funds), "price_session_count": len(sessions),
        "stock_group_count": (len(stocks) + MAX_TICKERS - 1) // MAX_TICKERS,
        "stock_request_count": sum(item["table"] == "stocks" for item in requests),
        "fund_request_count": sum(item["table"] == "funds" for item in requests),
        "request_count": len(requests), "maximum_calendar_key_bound": max(item["calendar_key_bound"] for item in requests),
        "vendor_requested_NYSE_cells": (len(stocks) + len(funds)) * len(sessions),
        "pending_native_NYSE_cells": len(pending) * len(sessions),
        "assignment_inventory_sha256": digest(assignments), "request_inventory_sha256": digest(requests),
        "private_plan_byte_count": private.byte_count, "private_plan_sha256": private.sha256, **FALSE_FLAGS}
    _deadline(deadline)
    return validate_plan_summary(summary), private


def validate_plan_summary(value):
    keys = {"schema", "scope", "ac_summary_sha256", "ac_frame_pin", "native_specification_sha256",
        "full_axis_sha256", "stock_binding_count", "vendor_stock_count", "pending_native_stock_count",
        "conditional_stock_count", "fund_count", "price_session_count", "stock_group_count",
        "stock_request_count", "fund_request_count", "request_count", "maximum_calendar_key_bound",
        "vendor_requested_NYSE_cells", "pending_native_NYSE_cells", "assignment_inventory_sha256",
        "request_inventory_sha256", "private_plan_byte_count", "private_plan_sha256", *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value["schema"] == SCHEMA
        and value["scope"] == "fixed_full_window_source_observation_plan_not_price_admission"
        and all(value[key] is False for key in FALSE_FLAGS)
        and value["ac_summary_sha256"] == AC_SUMMARY_SHA256
        and value["native_specification_sha256"] == NATIVE_SPECIFICATION_SHA256
        and value["full_axis_sha256"] == FULL_AXIS_SHA256, "summary")
    expected = {"stock_binding_count": VENDOR_STOCK_COUNT + NATIVE_STOCK_COUNT + CONDITIONAL_COUNT,
        "vendor_stock_count": VENDOR_STOCK_COUNT, "pending_native_stock_count": NATIVE_STOCK_COUNT,
        "conditional_stock_count": CONDITIONAL_COUNT, "fund_count": FUND_COUNT,
        "price_session_count": PRICE_SESSION_COUNT, "stock_group_count": (VENDOR_STOCK_COUNT + MAX_TICKERS - 1) // MAX_TICKERS,
        "stock_request_count": ((VENDOR_STOCK_COUNT + MAX_TICKERS - 1) // MAX_TICKERS) * len(STOCK_WINDOWS),
        "fund_request_count": len(FUND_WINDOWS),
        "vendor_requested_NYSE_cells": (VENDOR_STOCK_COUNT + FUND_COUNT) * PRICE_SESSION_COUNT,
        "pending_native_NYSE_cells": NATIVE_STOCK_COUNT * PRICE_SESSION_COUNT}
    require(all(type(value[key]) is int and value[key] == count for key, count in expected.items())
        and type(value["request_count"]) is int and value["request_count"] == value["stock_request_count"] + value["fund_request_count"]
        and type(value["maximum_calendar_key_bound"]) is int and value["maximum_calendar_key_bound"]
            == max(MAX_TICKERS * max((_date(last, "summary") - _date(first, "summary")).days + 1
                for first, last in STOCK_WINDOWS), FUND_COUNT * max((_date(last, "summary") - _date(first, "summary")).days + 1
                for first, last in FUND_WINDOWS)) < ROW_LIMIT
        and type(value["private_plan_byte_count"]) is int and 0 < value["private_plan_byte_count"] <= MAX_PRIVATE_BYTES
        and all(_hash(value[key]) for key in ("assignment_inventory_sha256", "request_inventory_sha256", "private_plan_sha256"))
        and type(value["ac_frame_pin"]) is dict and set(value["ac_frame_pin"]) == {"byte_count", "sha256"}
        and type(value["ac_frame_pin"]["byte_count"]) is int and 0 < value["ac_frame_pin"]["byte_count"] <= MAX_SOURCE_BYTES
        and _hash(value["ac_frame_pin"]["sha256"]) and len(canonical(value)) <= MAX_SUMMARY_BYTES, "summary")
    return json.loads(canonical(value))


def _request(value):
    require(type(value) is PrivatePriceRequest and sha(value._raw) == value.sha256, "request")
    record = json.loads(value._raw)
    require(set(record) == {"schema", "plan_sha256", "request_ordinal", "table", "tickers", "endpoint",
        "first", "last", "parameters", "expected_sessions"} and record["schema"] == REQUEST_SCHEMA
        and _hash(record["plan_sha256"]) and type(record["request_ordinal"]) is int and record["request_ordinal"] >= 0
        and record["table"] in ("stocks", "funds") and type(record["tickers"]) is list
        and record["endpoint"] == ENDPOINTS[record["table"]]
        and 0 < len(record["tickers"]) <= (MAX_TICKERS if record["table"] == "stocks" else FUND_COUNT)
        and all(type(ticker) is str and TICKER.fullmatch(ticker) is not None for ticker in record["tickers"])
        and record["tickers"] == sorted(set(record["tickers"])), "request")
    windows = STOCK_WINDOWS if record["table"] == "stocks" else FUND_WINDOWS
    require((record["first"], record["last"]) in windows
        and record["parameters"] == _parameters(record["tickers"], (record["first"], record["last"]))
        and type(record["expected_sessions"]) is list and len(record["expected_sessions"]) <= PRICE_SESSION_COUNT
        and record["expected_sessions"] == sorted(set(record["expected_sessions"])), "request")
    for session in record["expected_sessions"]:
        _date(session, "request")
        require(record["first"] <= session <= record["last"], "request")
    return record


def _price(text):
    require(type(text) is str and 0 < len(text) <= MAX_PRICE_TEXT
        and text.isascii() and PRICE.fullmatch(text) is not None, "price_value")
    try: value = Decimal(text)
    except InvalidOperation: raise Refused("price_value") from None
    require(value.is_finite() and value > 0 and abs(value.adjusted()) <= MAX_PRICE_TEXT, "price_value")
    result = format(value, "f")
    require(len(result) <= MAX_PRICE_TEXT, "price_value")
    if "." in result: result = result.rstrip("0").rstrip(".")
    return result


def analyze_response(request, raw, *, http_status, deadline=None):
    """Validate supplied CSV only; actual HTTP/body provenance is external."""
    _deadline(deadline)
    planned = _request(request)
    require(type(http_status) is int and 100 <= http_status <= 599, "http_status")
    tickers, sessions = planned["tickers"], planned["expected_sessions"]
    rows, seen, updated = None, set(), Counter()
    if http_status != 200:
        require(raw is None, "failed_body")
        absent, raw_pin = None, None
    else:
        require(type(raw) is bytes and 0 < len(raw) <= MAX_BODY_BYTES, "csv")
        raw_pin = {"byte_count": len(raw), "sha256": sha(raw)}
        rows = []
        try:
            text = raw.decode("utf-8-sig", errors="strict")
            require("\x00" not in text, "csv")
            reader = csv.reader(io.StringIO(text, newline=""), strict=True)
            require(tuple(next(reader, ())) == FIELDS, "header")
            previous_date = None
            for values in reader:
                _deadline(deadline)
                require(len(rows) + 1 < ROW_LIMIT, "row_bound")
                require(len(values) == len(FIELDS) and all(type(value) is str and value.isascii()
                    and len(value) <= MAX_PRICE_TEXT and value == value.strip()
                    and not any(ord(char) < 32 or ord(char) == 127 for char in value)
                    for value in values), "row_shape")
                ticker, session, close, modified = values
                require(ticker in tickers, "ticker")
                _date(session, "price_date"); _date(modified, "lastupdated")
                require(planned["first"] <= session <= planned["last"] and session in sessions, "price_date")
                require(previous_date is None or previous_date <= session, "sort"); previous_date = session
                key = (ticker, session)
                require(key not in seen, "duplicate_price"); seen.add(key)
                close = _price(close)
                relation = "before_price_date" if modified < session else "same_as_price_date" if modified == session else "after_price_date"
                updated[relation] += 1
                rows.append([ticker, session, close, modified])
        except Refused: raise
        except (csv.Error, UnicodeError, ValueError, RecursionError): raise Refused("csv") from None
        absent = [[ti, si] for ti, ticker in enumerate(tickers) for si, session in enumerate(sessions)
            if (ticker, session) not in seen]
        rows.sort(key=lambda row: (row[1], row[0]))
    private = PrivatePriceResponse({"schema": RESPONSE_PRIVATE_SCHEMA, "request_sha256": request.sha256,
        "http_status": http_status, "raw_body_pin": raw_pin, "rows": rows, "absent_cells": absent})
    summary = {"schema": RESPONSE_SCHEMA, "scope": "supplied_CSV_observations_not_price_admission",
        "plan_sha256": planned["plan_sha256"], "request_sha256": request.sha256,
        "request_ordinal": planned["request_ordinal"], "table": planned["table"],
        "first": planned["first"], "last": planned["last"], "ticker_count": len(tickers),
        "expected_NYSE_cell_count": len(tickers) * len(sessions), "http_status": http_status,
        "terminal": "CSV_rows_validated" if http_status == 200 else "HTTP_refused_body_unread",
        "raw_body_pin": raw_pin, "row_count": None if rows is None else len(rows),
        "absent_cell_count": None if absent is None else len(absent),
        "lastupdated_relation_counts": dict(sorted(updated.items())),
        "private_response_byte_count": private.byte_count, "private_response_sha256": private.sha256,
        **FALSE_FLAGS}
    _deadline(deadline)
    return validate_response_summary(summary, request=request), private



def validate_response_summary(value, *, request=None):
    keys = {"schema", "scope", "plan_sha256", "request_sha256", "request_ordinal", "table", "first", "last",
        "ticker_count", "expected_NYSE_cell_count", "http_status", "terminal", "raw_body_pin", "row_count",
        "absent_cell_count", "lastupdated_relation_counts", "private_response_byte_count",
        "private_response_sha256", *FALSE_FLAGS}
    require(type(value) is dict and set(value) == keys and value["schema"] == RESPONSE_SCHEMA
        and value["scope"] == "supplied_CSV_observations_not_price_admission"
        and all(value[key] is False for key in FALSE_FLAGS)
        and _hash(value["plan_sha256"]) and _hash(value["request_sha256"])
        and _hash(value["private_response_sha256"])
        and type(value["request_ordinal"]) is int and value["request_ordinal"] >= 0
        and value["table"] in ("stocks", "funds")
        and type(value["ticker_count"]) is int and 0 < value["ticker_count"] <= MAX_TICKERS
        and type(value["expected_NYSE_cell_count"]) is int and 0 <= value["expected_NYSE_cell_count"] < ROW_LIMIT
        and type(value["http_status"]) is int and 100 <= value["http_status"] <= 599
        and type(value["private_response_byte_count"]) is int
        and 0 < value["private_response_byte_count"] <= MAX_PRIVATE_BYTES, "summary")
    _date(value["first"], "summary"); _date(value["last"], "summary")
    require((value["first"], value["last"]) in (STOCK_WINDOWS if value["table"] == "stocks" else FUND_WINDOWS), "summary")
    if value["http_status"] == 200:
        require(value["terminal"] == "CSV_rows_validated"
            and type(value["row_count"]) is int and 0 <= value["row_count"] < ROW_LIMIT
            and type(value["absent_cell_count"]) is int and value["absent_cell_count"] >= 0
            and value["row_count"] + value["absent_cell_count"] == value["expected_NYSE_cell_count"]
            and type(value["raw_body_pin"]) is dict and set(value["raw_body_pin"]) == {"byte_count", "sha256"}
            and type(value["raw_body_pin"]["byte_count"]) is int and 0 < value["raw_body_pin"]["byte_count"] <= MAX_BODY_BYTES
            and _hash(value["raw_body_pin"]["sha256"])
            and type(value["lastupdated_relation_counts"]) is dict
            and set(value["lastupdated_relation_counts"]) <= {"before_price_date", "same_as_price_date", "after_price_date"}
            and all(type(count) is int and count > 0 for count in value["lastupdated_relation_counts"].values())
            and sum(value["lastupdated_relation_counts"].values()) == value["row_count"], "summary")
    else:
        require(value["terminal"] == "HTTP_refused_body_unread" and value["row_count"] is None
            and value["absent_cell_count"] is None and value["raw_body_pin"] is None
            and value["lastupdated_relation_counts"] == {}, "summary")
    if request is not None:
        expected = _request(request)
        require(value["request_sha256"] == request.sha256 and value["plan_sha256"] == expected["plan_sha256"]
            and all(value[field] == expected[field] for field in ("request_ordinal", "table", "first", "last"))
            and value["ticker_count"] == len(expected["tickers"])
            and value["expected_NYSE_cell_count"] == len(expected["tickers"]) * len(expected["expected_sessions"]), "summary")
    require(len(canonical(value)) <= MAX_SUMMARY_BYTES, "summary")
    return json.loads(canonical(value))


def profile_record():
    return {"schema": SCHEMA, "frozen_dependency_pins": dict(_SOURCE_PINS),
        "window": [FIRST, LAST], "endpoints": dict(ENDPOINTS), "fields": list(FIELDS), "format": "csv",
        "stock_tickers_per_request": MAX_TICKERS, "stock_windows": [list(item) for item in STOCK_WINDOWS],
        "fund_windows": [list(item) for item in FUND_WINDOWS], "limit": ROW_LIMIT, "skip": 0, "sort": "date.asc",
        "first_stock_calendar_bound": 27 * 366,
        "row_limit_policy": "strictly_fewer_than_limit_never_silent_pagination_or_limit_hit_acceptance",
        "source_assignments": "all6151_originals_retained_5636vendor_5pendingnative_510conditional_plus8funds",
        "source_window": "full_window_never_clip_by_binding_membership_or_current_first_last_metadata",
        "absence": "exact_supplied_authenticated_NYSE_grid_only_not_halt_delisting_payoff_or_complete_coverage",
        "lastupdated": "date_observation_not_original_availability_or_PIT",
        "CSV": "optional_UTF8_BOM_exact_ordered_four_columns_strict_rows_no_control_or_unicode_fields",
        "Decimal": "direct_from_text_positive_finite_bounded_plain_canonical_string_no_float_or_adjustment",
        "retention": "future_caller_retains_secret_scanned_HTTP200_raw_before_semantics_no_failed_status_body",
        "rights": "no_new_rights_or_QC_processing_authority_from_plan",
        "quota": "no_unlimited_quota_rate_or_actual_request_count_claim",
        "private_consumer": "opaque_objects_no_raw_serializer_no_callback_or_HTTP_interface",
        "maximum_source_bytes": MAX_SOURCE_BYTES, "maximum_response_body_bytes": MAX_BODY_BYTES,
        "maximum_private_bytes": MAX_PRIVATE_BYTES, "documentation": ["https://sharadar.com/docs/stocks",
            "https://sharadar.com/docs/funds", "https://sharadar.com/docs/getting-started"], **FALSE_FLAGS}
