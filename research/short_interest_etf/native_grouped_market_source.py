"""Ignored full-study grouped raw-bar source draft; never outcome admission.

The query date and provider window-end millisecond timestamp remain separate.
No currency/native ID, original availability, or exact opening-auction fact is
invented. Later source bindings may select the unadjusted eligible daily open
as the already frozen bar-based simulated-order price proxy.
"""
from __future__ import annotations

from collections import defaultdict
import dataclasses
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
import json
import re
from zoneinfo import ZoneInfo

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp

SCHEMA = "si-massive-grouped-raw-market-draft-v1"
FROM, TO = "2022-01-03", "2026-08-31"
ENDPOINT = "https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/"
MAXIMUM_RESPONSE_BYTES = 8 * 1024 * 1024
MAXIMUM_ROWS = 50_000
MAXIMUM_REPORT_BYTES = 128 * 1024 * 1024
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_INTEGER = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_NUMERIC = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE]([+-]?[0-9]+))?\Z")
ROW_FIELDS = ("ticker", "provider_window_end_milliseconds", "open", "high", "low", "close",
              "volume", "vwap", "transactions", "otc", "refusal_reasons")


class GroupedMarketError(ValueError):
    pass


def _require(value, reason):
    if not value:
        raise GroupedMarketError("REFUSED: " + reason)


def _authority():
    return {"source_only": True, "latest_revised_only": True, "source_admitted": False,
            "price_volume_admitted": False, "historical_identity_admitted": False,
            "USD_currency_admitted": False, "market_cap_admitted": False,
            "same_class_denominator_admitted": False, "exact_listing_auction_price_proven": False,
            "original_availability_known": False, "point_in_time_data": False,
            "actual_input_execution_admitted": False, "outcome_looks": 0,
            "qc_attempts": 0, "trading_authority": False}


def policy():
    return {"schema": SCHEMA + "-policy", "source_contract":
            "https://massive.com/docs/rest/stocks/aggregates/daily-market-summary",
            "endpoint": ENDPOINT, "from": FROM, "to": TO,
            "sessions": "complete_shared_XNYS_calendar_sessions_inclusive_later_exact_source_pin",
            "requests": "one_GET_per_session_adjusted_false_include_otc_false_no_symbol_selection",
            "maximum_response_bytes": MAXIMUM_RESPONSE_BYTES, "maximum_rows_per_request": MAXIMUM_ROWS,
            "maximum_report_bytes_per_session": MAXIMUM_REPORT_BYTES,
            "budget": "exact_session_count_with_whole_8MiB_and_50000_row_reservation_before_attempt",
            "automatic_retries": 0, "pagination": "none_next_url_refused_never_followed",
            "price": "split_unadjusted_eligible_daily_OHLC_not_dividend_adjusted",
            "volume": "exact_rational_genuine_fractional_trade_size_sum_never_round_to_integer",
            "time": "retain_query_session_and_raw_window_end_t_separately_no_start_end_or_availability_cast",
            "date_scope": "recognizable_t_between_NY_midnight_query_date_and_next_midnight_inclusive_before_raw_hash_or_storage_no_RTH_hypothesis",
            "fill_proxy": "later_qualified_daily_raw_open_proxy_not_actual_listing_auction_or_broker_fill",
            "mapping": "independent_dated_native_shareclass_USD_binding_before_price_use",
            "inventory": "retain_all_symbols_outside_structural_population_and_every_malformed_duplicate_peer",
            "half_days": "shared_calendar_close_preserved_no_16h_constant_or_daily_t_to_regular_close_inference",
            "authority": _authority()}


def _date(value):
    _require(type(value) is str and len(value) == 10, "canonical_session_required")
    try:
        _require(date.fromisoformat(value).isoformat() == value, "canonical_session_required")
    except ValueError:
        raise GroupedMarketError("REFUSED: canonical_session_required") from None
    return value


def _clock(value):
    try:
        return parse_utc_timestamp(value, "source_clock")
    except (TypeError, ValueError):
        raise GroupedMarketError("REFUSED: UTC_source_clock_required") from None


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class GroupedSessionPlan:
    _sessions: tuple
    _json: str = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise GroupedMarketError("REFUSED: exact_calendar_plan_factory_required")

    def _guard(self):
        _require(type(self) is GroupedSessionPlan and self._anchor is self._identity
                 and self._sessions is self._anchor[0] and self._json is self._anchor[1], "sealed_grouped_plan_changed")

    def sessions(self):
        self._guard()
        return self._sessions

    def to_payload(self):
        self._guard()
        return json.loads(self._json)

    @property
    def sha256(self):
        self._guard()
        return hash_bytes(self._json.encode())


def freeze_grouped_session_plan(sessions, *, calendar_sha256):
    _require(type(sessions) is tuple and bool(sessions) and sessions == tuple(sorted(set(sessions)))
             and all(FROM <= _date(at) <= TO for at in sessions), "ordered_in_scope_calendar_sessions_required")
    _require(type(calendar_sha256) is str and _HASH.fullmatch(calendar_sha256), "independent_calendar_bytes_pin_required")
    # A factory does not prove full calendar coverage; the runtime's separate
    # frozen shared-calendar loader verifies exact equality before key access.
    value = {"schema": SCHEMA + "-plan", "policy_sha256": hash_payload(policy()),
             "calendar_sha256": calendar_sha256, "sessions_sha256": hash_payload(list(sessions)),
             "request_count": len(sessions), "maximum_total_bytes": len(sessions) * MAXIMUM_RESPONSE_BYTES,
             "maximum_rows": len(sessions) * MAXIMUM_ROWS, "authority": _authority()}
    encoded = canonical_json(value)
    result = object.__new__(GroupedSessionPlan)
    anchor = (sessions, encoded)
    for name, item in (("_sessions", sessions), ("_json", encoded), ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(result, name, item)
    return result


def request_descriptor(plan, ordinal):
    _require(type(plan) is GroupedSessionPlan and type(ordinal) is int
             and 1 <= ordinal <= len(plan.sessions()), "exact_plan_request_ordinal_required")
    return {"method": "GET", "url": ENDPOINT + plan.sessions()[ordinal - 1],
            "params": {"adjusted": "false", "include_otc": "false"},
            "authentication": "Bearer_header_never_recorded", "plan_sha256": plan.sha256,
            "request_ordinal": ordinal}


class _Number(str):
    pass


class _Nonfinite(str):
    pass


class _Pairs(list):
    def values(self, key):
        return [value for name, value in self if name == key]


def _parsed(raw):
    _require(type(raw) is bytes and len(raw) <= MAXIMUM_RESPONSE_BYTES, "bounded_raw_response_required")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_Pairs,
                          parse_int=_Number, parse_float=_Number, parse_constant=_Nonfinite)
    except (UnicodeError, ValueError, RecursionError):
        raise GroupedMarketError("REFUSED: source_UTF8_JSON_refused") from None


def guard_recognizable_window_dates(plan, ordinal, raw):
    """A refusal-only query-scope guard, not an aggregate clock interpretation.

    The grouped spec calls t the window end, whereas historic aggregate
    representations can show the opening midnight. Both query-day boundaries
    remain allowed. September 1 midnight can bound the August 31 window;
    a later September timestamp cannot. Check duplicate/invalid peers too.
    Unparseable bodies remain generic retained refusals, not admitted records.
    """
    at = request_descriptor(plan, ordinal)["url"].removeprefix(ENDPOINT)
    day = date.fromisoformat(at)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    def midnight_milliseconds(value):
        delta = datetime.combine(value, datetime.min.time(), ZoneInfo("America/New_York")).astimezone(timezone.utc) - epoch
        return delta.days * 86_400_000 + delta.seconds * 1000
    lower, upper = midnight_milliseconds(day), midnight_milliseconds(day + timedelta(days=1))
    _require(type(raw) is bytes and len(raw) <= MAXIMUM_RESPONSE_BYTES, "bounded_raw_response_required")
    try:
        value = _parsed(raw)
    except GroupedMarketError:
        return
    if type(value) is not _Pairs:
        return
    for results in value.values("results"):
        if type(results) is not list:
            continue
        for row in results:
            if type(row) is not _Pairs:
                continue
            for token in row.values("t"):
                # Numerical strings and fractional encodings can be invalid
                # row types yet still reveal a protected other-day response.
                if type(token) not in {_Number, str}:
                    continue
                token = token.strip()  # Negative scope recognition only; positive row typing is unchanged.
                if len(token) > 128:
                    continue
                match = _NUMERIC.fullmatch(token)
                if not match or (match.group(1) is not None and abs(int(match.group(1))) > 64):
                    continue
                timestamp = Fraction(token)
                _require(lower <= timestamp <= upper, "recognizable_window_timestamp_outside_query_day_boundaries")


def _decode(raw):
    value = _parsed(raw)
    _require(type(value) is _Pairs, "single_source_envelope_required")
    names = [key for key, _ in value]
    _require(len(names) == len(set(names)) and set(names) <=
             {"adjusted", "queryCount", "request_id", "resultsCount", "status", "results"},
             "duplicate_unknown_envelope_or_pagination_refused")
    fields = dict(value)
    _require(fields.get("adjusted") is False and fields.get("status") == "OK", "raw_unadjusted_OK_envelope_required")
    _require(type(fields.get("results")) is list and len(fields["results"]) <= MAXIMUM_ROWS,
             "bounded_advertised_result_array_required")
    _require(_integer(fields.get("resultsCount")) == len(fields["results"]), "advertised_result_count_mismatch")
    _integer(fields.get("queryCount"))
    _require(type(fields.get("request_id")) is str and 1 <= len(fields["request_id"]) <= 256
             and all(32 <= ord(c) <= 126 for c in fields["request_id"]), "source_request_id_required")
    return fields


def _integer(value):
    _require(type(value) is _Number and len(value) <= 20 and _INTEGER.fullmatch(value)
             and int(value) <= 2 ** 63 - 1, "exact_nonnegative_JSON_integer_required")
    return int(value)


def _rational(value, *, positive):
    _require(type(value) is _Number and len(value) <= 128, "exact_JSON_number_required")
    match = _NUMERIC.fullmatch(value)
    _require(match and (match.group(1) is None or abs(int(match.group(1))) <= 64), "bounded_number_required")
    number = Fraction(value)
    _require(number >= 0 and (not positive or number > 0) and number <= 10 ** 30, "positive_or_nonnegative_number_required")
    return {"source_number_token": str(value), "numerator": str(number.numerator), "denominator": str(number.denominator)}


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class GroupedMarketQualification:
    _plan: GroupedSessionPlan = dataclasses.field(repr=False)
    _json: str = dataclasses.field(repr=False)
    _anchor: tuple = dataclasses.field(repr=False)
    _identity: tuple = dataclasses.field(repr=False)

    def __init__(self):
        raise GroupedMarketError("REFUSED: report_requires_capture_factory")

    def to_bytes(self):
        _require(type(self) is GroupedMarketQualification and self._anchor is self._identity
                 and self._plan is self._anchor[0] and self._json is self._anchor[1], "sealed_grouped_report_changed")
        self._plan._guard()
        return self._json.encode()

    def to_payload(self):
        return json.loads(self.to_bytes())


def qualify_grouped_response(plan, ordinal, *, raw, raw_sha256, request_sha256, started_at,
                             received_at, http_status=200, content_type="application/json"):
    spec = request_descriptor(plan, ordinal)
    _require(type(raw_sha256) is str and hash_bytes(raw) == raw_sha256
             and type(request_sha256) is str and hash_payload(spec) == request_sha256,
             "response_request_or_raw_binding_changed")
    _require(type(http_status) is int and http_status == 200 and type(content_type) is str
             and content_type.split(";", 1)[0].strip().lower() == "application/json", "successful_JSON_receipt_required")
    _require(_clock(started_at) <= _clock(received_at), "capture_receipt_chronology")
    guard_recognizable_window_dates(plan, ordinal, raw)
    fields = _decode(raw)
    rows, groups, origins = [], defaultdict(list), []
    for index, item in enumerate(fields["results"]):
        origin = {"row_index": index, "raw_sha256": raw_sha256}
        origins.append(origin)
        tokens = list(dict.fromkeys(value.strip() for value in item.values("T")
            if type(value) is str and value.strip())) if type(item) is _Pairs else []
        for token in tokens:
            groups[token].append(index)
        row = [tokens[0] if len(tokens) == 1 else None] + [None] * 9 + [[]]
        try:
            _require(type(item) is _Pairs, "source_row_object_required")
            names = [key for key, _ in item]
            _require(len(names) == len(set(names)), "duplicate_row_JSON_key")
            _require({"T", "o", "h", "l", "c", "v", "t"} <= set(names)
                     and set(names) <= {"T", "o", "h", "l", "c", "v", "t", "n", "vw", "otc"},
                     "source_row_fields_required")
            values = dict(item)
            _require(type(values["T"]) is str and 1 <= len(values["T"]) <= 128
                     and all(33 <= ord(c) <= 126 for c in values["T"]), "exact_source_ticker_required")
            prices = [_rational(values[key], positive=True) for key in ("o", "h", "l", "c")]
            amounts = [Fraction(value["source_number_token"]) for value in prices]
            opening, high, low, close = amounts
            _require(low <= min(opening, close) <= max(opening, close) <= high, "OHLC_order_refused")
            otc = values.get("otc", False)
            _require(type(otc) is bool and otc is False, "unexpected_OTC_row_refused")
            row = [values["T"], _integer(values["t"]), *prices,
                   _rational(values["v"], positive=False),
                   None if "vw" not in values else _rational(values["vw"], positive=True),
                   None if "n" not in values else _integer(values["n"]), otc, []]
        except GroupedMarketError as exc:
            row[-1].append(str(exc).removeprefix("REFUSED: "))
        rows.append(row)
    collisions = []
    for ticker, positions in groups.items():
        if len(positions) > 1:
            collisions.append({"ticker": ticker, "row_indices": positions})
            for index in positions:
                rows[index][-1].append("duplicate_or_malformed_identifiable_ticker_peer")
    payload = {"schema": SCHEMA + "-qualification", "plan_sha256": plan.sha256,
               "query_session": plan.sessions()[ordinal - 1], "request_ordinal": ordinal,
               "request_sha256": request_sha256, "raw_sha256": raw_sha256,
               "source_request_id": fields["request_id"], "started_at": started_at, "received_at": received_at,
               "adjusted": False, "provider_timestamp_semantics": "window_end_milliseconds_not_availability_or_auction",
               "row_fields": list(ROW_FIELDS), "rows": rows, "row_origins": origins,
               "duplicate_groups": collisions, "currency": None, "native_identity_binding": None,
               "authority": _authority()}
    encoded = canonical_json(payload)
    _require(len(encoded.encode()) <= MAXIMUM_REPORT_BYTES, "bounded_private_report_required")
    result = object.__new__(GroupedMarketQualification)
    anchor = (plan, encoded)
    for name, item in (("_plan", plan), ("_json", encoded), ("_anchor", anchor), ("_identity", anchor)):
        object.__setattr__(result, name, item)
    return result
