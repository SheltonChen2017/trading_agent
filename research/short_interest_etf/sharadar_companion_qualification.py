"""Private, outcome-free direct-Sharadar companion qualification.

The provider's permaticker is retained as its own security identifier; a
composite FIGI is never relabelled a share-class FIGI.  Financial tokens are
parsed without binary floats.  This module makes no network/credential calls
and must not be used as an actual-input or research-look admission override.
Its per-row and per-cell evaluations belong only in protected local storage,
not public Git, chat, or a data-usability publication.
"""
from __future__ import annotations

import dataclasses
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from data.exchange_calendar import parse_session_date
from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp


TABLES = ("stocks", "tickers", "actions", "daily", "fundamentals")
SYMBOLS = ("AAPL", "BRK.A", "BRK.B", "FRC", "SIVB", "TWTR", "META", "FB", "BBBY", "BBBY1")
FIELDS = {
    # Authenticated-free public SQLite schema supplies lowercase spellings;
    # public descriptions documentation currently uses camel-case instead.
    "descriptions": ("table", "indicator", "title", "description", "unittype", "isprimarykey", "isfilter"),
    "tickers": ("table", "permaticker", "ticker", "exchange", "isdelisted", "category", "siccode", "sicsector", "figi", "sector", "currency", "location", "lastupdated", "firstpricedate", "lastpricedate"),
    "stocks": ("ticker", "date", "open", "high", "low", "close", "volume", "closeunadj", "lastupdated"),
    "actions": ("date", "action", "ticker", "name", "value", "contraticker", "contraname"),
    "daily": ("ticker", "date", "marketcap", "lastupdated"),
    "fundamentals": ("ticker", "dimension", "calendardate", "date", "reportperiod", "sharesbas", "sharefactor", "marketcap", "lastupdated"),
}
ROW_TABLES = ("descriptions", "tickers", "stocks", "actions", "daily", "fundamentals")
REQUEST_IDS = tuple("metadata-" + table for table in TABLES) + tuple(
    "schema-" + table for table in TABLES
) + tuple("rows-" + table for table in ROW_TABLES)
SCHEMA = "si-sharadar-companion-qualification-v1"
MAXIMUM_REQUESTS = 16
MAXIMUM_ROW_BYTES = 2 * 1024 * 1024
_LIMIT = 5000
_NUMBER = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
_API = "https://api.sharadar.com/v1.0/"
_SQL_IDENTIFIER = r'(?:"[A-Za-z_][A-Za-z0-9_]*"|`[A-Za-z_][A-Za-z0-9_]*`|\[[A-Za-z_][A-Za-z0-9_]*\]|[A-Za-z_][A-Za-z0-9_]*)'
_PRIMARY_KEYS = {
    "stocks": ("ticker", "date"), "tickers": ("table", "permaticker", "ticker"),
    "actions": ("date", "action", "ticker", "name", "contraticker", "contraname"),
    "daily": ("ticker", "date"), "fundamentals": ("ticker", "dimension", "date", "reportperiod"),
}
_GAPS = (
    "source_only_sample_not_full_historical_population_qualification",
    "original_SI_vintages_all_corrections_and_actual_availability_not_established",
    "effective_historical_ticker_classification_and_same_share_class_matching_not_admitted",
    "primary_share_class_fundamentals_not_secondary_class_denominator_authority",
    "date_only_actions_not_payment_clocks_or_complete_terminal_economics",
    "prospective_actual_outcome_look_and_exact_processing_QC_route_not_registered",
)


class SharadarCompanionQualificationError(ValueError):
    """An unbound, incomplete or invalid response is refused safely."""


def _refuse(reason: str) -> SharadarCompanionQualificationError:
    # Reasons never interpolate provider rows, URLs, authentication or bodies.
    return SharadarCompanionQualificationError("REFUSED: " + reason)


class _NumberToken(str):
    """Exact lexical JSON number; distinguish it from provider text."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise _refuse("duplicate_JSON_key")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise _refuse("nonfinite_JSON_constant")


def _json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_float=_NumberToken, parse_constant=_constant)
    except SharadarCompanionQualificationError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise _refuse("invalid_UTF8_JSON") from exc


def _authority() -> dict[str, Any]:
    return {
        "source_only": True, "source_admitted": False, "point_in_time_data": False,
        "ready_for_empirical_backtest": False, "outcome_access_authorized": False,
        "qc_authorized": False, "production_authoritative": False,
        "trading_authority": False, "actual_outcome_looks": 0,
        "allocated_alpha": 0, "qc_attempts": 0,
    }


def sharadar_request(request_id: str) -> dict[str, Any]:
    """Exact public request descriptor, excluding the runtime-only API key."""
    if request_id not in REQUEST_IDS:
        raise _refuse("unknown_request_id")
    kind, table = request_id.split("-", 1)
    if kind == "schema":
        params = {"format": "sqlite"}
        route = "schema/" + table
    elif kind == "metadata":
        params = {"status": "True", "years": "full"}
        route = "data/" + table
    else:
        params = {"format": "json", "fields": ",".join(FIELDS[table]),
                  "limit": str(_LIMIT), "offset": "0",
                  "sort": "indicator.asc" if table == "descriptions" else "ticker.asc"}
        if table == "descriptions":
            params["tablename"] = "actiontypes"
        else:
            params["ticker"] = ",".join(SYMBOLS)
        if table == "tickers":
            params["table"] = "stocks"
        elif table in {"stocks", "daily"}:
            params.update({"from": "2022-10-01", "to": "2023-05-31"})
        elif table == "actions":
            params.update({"from": "2022-01-01", "to": "2023-12-31"})
        elif table == "fundamentals":
            params.update({"from": "2022-01-01", "to": "2023-05-31", "dimension": "ARQ"})
        route = "data/" + table
    return {"request_id": request_id, "method": "GET", "url": _API + route, "params": params}


def request_sha256(request_id: str) -> str:
    return hash_payload(sharadar_request(request_id))


def qualification_protocol() -> dict[str, Any]:
    payload = {
        "schema": "si-sharadar-companion-qualification-protocol-v1",
        "source_route": "direct_sharadar_personal_API_not_Nasdaq_Data_Link",
        "purpose": "private_source_only_companion_coverage_and_schema_qualification",
        "candidate_symbols": list(SYMBOLS), "symbols_are_distinct_no_aliases": True,
        "request_ids": list(REQUEST_IDS),
        "requests": [sharadar_request(item) for item in REQUEST_IDS],
        "maximum_requests": MAXIMUM_REQUESTS, "automatic_retries": 0,
        "row_page_limit": _LIMIT, "row_page_rule": "one_page_exact_count_equals_data_length_strictly_below_limit",
        "maximum_row_bytes": MAXIMUM_ROW_BYTES,
        "numeric_rule": "lexical_JSON_numbers_exact_Decimal_to_Fraction_no_binary_float",
        "duplicate_rule": "all_identifiable_primary_key_collisions_quarantined_before_value_validation",
        "identity_rule": "provider_permaticker_retained_composite_FIGI_not_share_class_FIGI",
        "stock_imputation": "raw_OHLC=adjusted_OHLC*closeunadj/close_raw_volume=volume*close/closeunadj",
        "daily_market_cap_rule": "USD_millions_times_exact_1000000",
        "fundamentals_rule": "ARQ_date_key_not_calendardate_or_reportperiod_as_availability",
        "publication_rule": "private_only_no_data_usability_public_emitter",
        "authority": _authority(), "public_known_contract_gaps": list(_GAPS),
    }
    if hash_payload(payload) != PROTOCOL_SHA256:
        raise _refuse("frozen_protocol_hash_mismatch")
    return payload


# Independently pinned from the exact detached prospective protocol.
PROTOCOL_SHA256 = "8540ea0adecf781db0323490beed1cf514fa57f92bafe06fbcce11a5569158b4"


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedSharadarResponse:
    request_id: str
    request_sha256: str
    raw: bytes = dataclasses.field(repr=False)
    content_type: str
    http_status: int = 200

    def __post_init__(self) -> None:
        if type(self) is not CapturedSharadarResponse:
            raise _refuse("exact_capture_type_required")
        if self.request_id not in REQUEST_IDS or self.request_sha256 != request_sha256(self.request_id):
            raise _refuse("request_binding_mismatch")
        if type(self.raw) is not bytes or not self.raw:
            raise _refuse("capture_requires_nonempty_immutable_bytes")
        kind = self.request_id.split("-", 1)[0]
        bound = MAXIMUM_ROW_BYTES if kind == "rows" else 131072 if kind == "schema" else 65536
        if len(self.raw) > bound:
            raise _refuse("capture_byte_limit_exceeded")
        if type(self.http_status) is not int or self.http_status != 200:
            raise _refuse("HTTP_status_not_200")
        if type(self.content_type) is not str:
            raise _refuse("invalid_content_type")
        media = self.content_type.split(";", 1)[0].strip().lower()
        if media != ("text/plain" if kind == "schema" else "application/json"):
            raise _refuse("unexpected_content_type")


def _capture(capture: CapturedSharadarResponse, kind: str) -> None:
    if type(capture) is not CapturedSharadarResponse:
        raise _refuse("exact_capture_type_required")
    CapturedSharadarResponse.__post_init__(capture)
    if not capture.request_id.startswith(kind + "-"):
        raise _refuse("capture_kind_mismatch")


def _keys(value: Any, expected: set[str], optional: set[str] | None = None) -> dict:
    if type(value) is not dict or not expected <= set(value) or set(value) - expected - (optional or set()):
        raise _refuse("missing_or_unknown_fields")
    return value


def _text(value: Any, *, nullable: bool = False, blank: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if type(value) is not str or len(value) > 16384 or value != value.strip() or (not value and not blank):
        raise _refuse("invalid_text")
    return value


def _date(value: Any) -> str:
    try:
        parse_session_date(value)
    except (TypeError, ValueError) as exc:
        raise _refuse("invalid_date") from exc
    return value


def _integer(value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 10**18:
        raise _refuse("invalid_integer")
    return value


def _number(value: Any, *, positive: bool = False, nullable: bool = False, signed: bool = False) -> Fraction | None:
    if value is None and nullable:
        return None
    if type(value) is int:
        if abs(value) > 10**30:
            raise _refuse("numeric_bound_exceeded")
        result = Fraction(value)
    elif type(value) is _NumberToken:
        if len(value) > 128 or _NUMBER.fullmatch(value) is None:
            raise _refuse("invalid_number_token")
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise _refuse("invalid_number_token") from exc
        if not parsed.is_finite() or abs(parsed.adjusted()) > 30:
            raise _refuse("numeric_bound_exceeded")
        result = Fraction(parsed)
    else:
        raise _refuse("numeric_JSON_token_required")
    if (result < 0 and not signed) or (positive and result <= 0):
        raise _refuse("positive_number_required" if positive else "nonnegative_number_required")
    return result


def _rational(value: Fraction | None) -> dict[str, int] | None:
    return None if value is None else {"numerator": value.numerator, "denominator": value.denominator}


def _utc(value: Any) -> datetime:
    try:
        return parse_utc_timestamp(value, "retrieved_at")
    except (TypeError, ValueError) as exc:
        raise _refuse("invalid_retrieved_at") from exc


def validate_sharadar_metadata(capture: CapturedSharadarResponse, *, retrieved_at: str) -> dict[str, Any]:
    """Validate full-history file status; status/availability is not entitlement."""
    _capture(capture, "metadata")
    retrieved = _utc(retrieved_at)
    table = capture.request_id.split("-", 1)[1]
    payload = _json(capture.raw)
    if type(payload) is not dict or payload.get("table") != table:
        raise _refuse("metadata_table_mismatch")
    if "files" in payload:
        _keys(payload, {"table", "files"})
        if type(payload["files"]) is not list or len(payload["files"]) != 1:
            raise _refuse("full_history_status_requires_one_file")
        item = _keys(payload["files"][0], {"history", "historyLabel", "name", "size", "sizeLabel", "modified", "available"})
        if item["history"] != "full" or item["historyLabel"] != "Full History":
            raise _refuse("metadata_history_mismatch")
        if type(item["available"]) is not bool:
            raise _refuse("metadata_availability_requires_boolean")
        available = item["available"]
    else:
        item = _keys(payload, {"table", "name", "size", "sizeLabel", "modified"}, {"history", "historyLabel", "available"})
        if item.get("history", "full") != "full":
            raise _refuse("metadata_history_mismatch")
        if "historyLabel" in item and item["historyLabel"] != "Full History":
            raise _refuse("metadata_history_mismatch")
        if "available" in item and type(item["available"]) is not bool:
            raise _refuse("metadata_availability_requires_boolean")
        available = item.get("available")
    if item["name"] != table + ".csv.zip":
        raise _refuse("metadata_filename_mismatch")
    size = _integer(item["size"])
    _text(item["sizeLabel"])
    try:
        modified = datetime.fromisoformat(_text(item["modified"]).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise _refuse("metadata_modified_invalid") from exc
    if modified.tzinfo is None or modified.utcoffset() is None or modified > retrieved:
        raise _refuse("metadata_modified_naive_or_future")
    return {"table": table, "file_name": item["name"], "byte_size": size,
            "modified": item["modified"], "available_assertion": available,
            "full_history_filename_verified": True, "entitlement_inferred": False,
            "historical_availability_inferred": False,
            "source_file_sha256": hash_bytes(capture.raw)}


def validate_sharadar_schema(capture: CapturedSharadarResponse) -> dict[str, Any]:
    """Check public SQLite table/column tokens without executing SQL."""
    _capture(capture, "schema")
    table = capture.request_id.split("-", 1)[1]
    try:
        text = capture.raw.decode("utf-8")
    except UnicodeError as exc:
        raise _refuse("schema_not_UTF8") from exc
    text = re.sub(r"(?m)^\s*--[^\n]*(?:\n|$)", "", text)
    # Capture the first terminated CREATE TABLE only, not a greedy body that
    # can swallow later tables/indexes as if they declared its columns.
    match = re.match(r"\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(" + _SQL_IDENTIFIER + r")\s*\((.*?)\)\s*;", text, re.IGNORECASE | re.DOTALL)
    if match is None:
        raise _refuse("schema_table_or_statement_mismatch")
    if match.group(1).strip('"`[]') != table:
        raise _refuse("schema_table_or_statement_mismatch")
    columns = set()
    for part in match.group(2).split(","):
        # PRIMARY KEY compound members are not column declarations.  Projected
        # columns need concrete datatype declarations, not incidental tokens.
        column = re.match(r"\s*[\"`\[]?([A-Za-z][A-Za-z0-9_]*)[\"`\]]?\s+(INTEGER|REAL|TEXT|BLOB|NUMERIC)\b", part, re.IGNORECASE)
        if column is not None:
            if column.group(1) in columns:
                raise _refuse("duplicate_schema_column")
            columns.add(column.group(1))
    if not set(FIELDS[table]) <= columns:
        raise _refuse("projected_schema_field_missing")
    primary = re.search(r"\bPRIMARY\s+KEY\s*\(([^()]*)\)", match.group(2), re.IGNORECASE)
    if primary is not None:
        names = tuple(item.strip().strip('"`[]') for item in primary.group(1).split(","))
        if names != _PRIMARY_KEYS[table]:
            raise _refuse("public_schema_primary_key_mismatch")
    index_names = set()
    for tail in text[match.end():].split(";"):
        if not tail.strip():
            continue
        index = re.fullmatch(r"\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(" + _SQL_IDENTIFIER + r")\s+ON\s+(" + _SQL_IDENTIFIER + r")\s*\(([^()]*)\)\s*", tail, re.IGNORECASE)
        if index is None or index.group(2).strip('"`[]') != table:
            raise _refuse("unrecognized_or_other_table_schema_tail")
        name = index.group(1).strip('"`[]')
        fields = [item.strip() for item in index.group(3).split(",")]
        if name in index_names or not fields or any(re.fullmatch(_SQL_IDENTIFIER, item) is None or item.strip('"`[]') not in columns for item in fields):
            raise _refuse("invalid_or_duplicate_schema_index")
        index_names.add(name)
    return {"table": table, "projected_fields": list(FIELDS[table]),
            "schema_sha256": hash_bytes(capture.raw), "SQL_executed": False}


def _permaticker(value: Any) -> str:
    if type(value) is int:
        return str(_integer(value, minimum=1))
    value = _text(value)
    if len(value) > 32 or re.fullmatch(r"[1-9][0-9]*", value) is None:
        raise _refuse("invalid_permaticker")
    return value


def _primary_key(table: str, row: Any) -> tuple[Any, ...]:
    if type(row) is not dict:
        raise _refuse("row_not_object")
    if table == "descriptions":
        return (_text(row.get("table")), _text(row.get("indicator")))
    if table == "tickers":
        return (_text(row.get("table")), _permaticker(row.get("permaticker")), _text(row.get("ticker")))
    ticker = _text(row.get("ticker"))
    at = _date(row.get("date"))
    if table == "actions":
        return (at, _text(row.get("action")), ticker, _text(row.get("name"), nullable=True, blank=True),
                _text(row.get("contraticker"), nullable=True, blank=True), _text(row.get("contraname"), nullable=True, blank=True))
    if table == "fundamentals":
        return (ticker, _text(row.get("dimension")), at, _date(row.get("reportperiod")))
    return (ticker, at)


def _row(table: str, row: Any) -> dict[str, Any]:
    _keys(row, set(FIELDS[table]))
    _primary_key(table, row)
    if table == "descriptions":
        if row["table"] != "actiontypes":
            raise _refuse("dictionary_table_filter_mismatch")
        for key in ("title", "description", "unittype"):
            _text(row[key], nullable=True, blank=True)
        if type(row["isprimarykey"]) is not str or type(row["isfilter"]) is not str or row["isprimarykey"] not in {"Y", "N"} or row["isfilter"] not in {"Y", "N"}:
            raise _refuse("dictionary_flag_invalid")
        return {"action": row["indicator"], "title": row["title"], "description": row["description"], "unit_type": row["unittype"]}
    if row["ticker"] not in SYMBOLS:
        raise _refuse("symbol_filter_mismatch_no_alias")
    if table == "tickers":
        if row["table"] != "stocks":
            raise _refuse("ticker_table_filter_mismatch")
        if type(row["isdelisted"]) is not str or row["isdelisted"] not in {"Y", "N"}:
            raise _refuse("delisted_flag_invalid")
        for key in ("exchange", "category", "sicsector", "figi", "sector", "currency", "location"):
            _text(row[key], nullable=True, blank=True)
        sic = row["siccode"]
        if sic is not None:
            if type(sic) is int:
                _integer(sic)
            elif type(sic) is str and re.fullmatch(r"[0-9]{1,4}", sic) is not None:
                pass
            else:
                raise _refuse("siccode_invalid")
        for key in ("lastupdated", "firstpricedate", "lastpricedate"):
            if row[key] is not None:
                _date(row[key])
        if row["firstpricedate"] is not None and row["lastpricedate"] is not None and row["firstpricedate"] > row["lastpricedate"]:
            raise _refuse("price_date_interval_inverted")
        permanent = _permaticker(row["permaticker"])
        return {"ticker": row["ticker"], "provider_security_id": "sharadar:permaticker:" + permanent,
                "permaticker": permanent, "composite_figi_assertion": row["figi"],
                "share_class_figi": None, "current_reference_assertions": {key: row[key] for key in FIELDS[table] if key not in {"ticker", "permaticker", "figi"}},
                "effective_historical_mapping_admitted": False}
    at = _date(row["date"])
    params = sharadar_request("rows-" + table)["params"]
    if not params["from"] <= at <= params["to"]:
        raise _refuse("date_window_filter_mismatch")
    if "lastupdated" in row:
        _date(row["lastupdated"])
    if table == "stocks":
        values = {key: _number(row[key], positive=key != "volume") for key in ("open", "high", "low", "close", "volume", "closeunadj")}
        if not values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]:
            raise _refuse("OHLC_order_invalid")
        ratio = values["closeunadj"] / values["close"]
        return {"ticker": row["ticker"], "session": at,
                "raw_open": _rational(values["open"] * ratio),
                "raw_high": _rational(values["high"] * ratio),
                "raw_low": _rational(values["low"] * ratio),
                "raw_close": _rational(values["closeunadj"]),
                "raw_volume": _rational(values["volume"] / ratio),
                "derived_from_provider_adjusted_tokens": True,
                "historical_availability_verified": False}
    if table == "daily":
        value = _number(row["marketcap"], nullable=True)
        return {"ticker": row["ticker"], "session": at,
                "market_cap_USD": _rational(None if value is None else value * 1000000),
                "provider_units": "USD_millions", "historical_availability_verified": False}
    if table == "fundamentals":
        if row["dimension"] != "ARQ":
            raise _refuse("dimension_filter_mismatch")
        _date(row["calendardate"])
        _date(row["reportperiod"])
        if row["reportperiod"] > at:
            raise _refuse("reportperiod_after_ARQ_date_key")
        shares = _number(row["sharesbas"], positive=True, nullable=True)
        factor = _number(row["sharefactor"], positive=True, nullable=True)
        cap = _number(row["marketcap"], nullable=True)
        return {"ticker": row["ticker"], "dimension": "ARQ", "date_key": at,
                "calendardate": row["calendardate"], "reportperiod": row["reportperiod"],
                "sharesbas": _rational(shares), "sharefactor": _rational(factor),
                "market_cap_USD": _rational(cap), "primary_share_class_only": True,
                "same_share_class_denominator_admitted": False,
                "historical_availability_verified": False}
    for key in ("name", "contraticker", "contraname"):
        _text(row[key], nullable=True, blank=True)
    # SIC/venue changes and some event types may legitimately have negative
    # signed or text-like economic conventions. Do not invent an economics
    # parser from the generic action numeric field. Numeric values must still
    # be finite; missing remains missing and never terminal zero.
    value = _number(row["value"], nullable=True, signed=True)
    return {"ticker": row["ticker"], "date": at, "action": row["action"],
            "value": _rational(value), "contraticker": row["contraticker"],
            "payment_timestamp": None, "terminal_economics_admitted": False,
            "effective_instant_admitted": False}


def _rows(capture: CapturedSharadarResponse) -> dict[str, Any]:
    _capture(capture, "rows")
    table = capture.request_id.split("-", 1)[1]
    envelope = _keys(_json(capture.raw), {"count", "data"})
    count = _integer(envelope["count"])
    if type(envelope["data"]) is not list or count != len(envelope["data"]) or count >= _LIMIT:
        raise _refuse("row_page_count_or_completeness_invalid")
    rows = envelope["data"]
    keys, counts = {}, {}
    for index, row in enumerate(rows):
        try:
            key = _primary_key(table, row)
        except SharadarCompanionQualificationError:
            continue
        keys[index] = key
        counts[key] = counts.get(key, 0) + 1
    accepted, refused = [], []
    for index, raw in enumerate(rows):
        origin = {"row_index": index, "raw_record_sha256": hash_payload(raw),
                  "source_file_sha256": hash_bytes(capture.raw)}
        key = keys.get(index)
        if key is not None and counts[key] > 1:
            refused.append({**origin, "ticker": raw.get("ticker"), "status": "duplicate", "reason": "identifiable_primary_key_collision"})
            continue
        try:
            normalized = _row(table, raw)
        except SharadarCompanionQualificationError as exc:
            refused.append({**origin, "ticker": raw.get("ticker") if type(raw) is dict else None,
                            "status": "malformed", "reason": str(exc)})
        else:
            accepted.append({**origin, "normalized": normalized,
                             "normalized_record_sha256": hash_payload(normalized)})
    cells = []
    if table != "descriptions":
        for ticker in SYMBOLS:
            matches = [row for row in accepted if row["normalized"]["ticker"] == ticker]
            failures = [row for row in refused if row["ticker"] == ticker]
            status = "missing" if not matches and not failures else "refused" if failures else "present"
            if table == "tickers" and len({row["normalized"]["permaticker"] for row in matches}) > 1:
                status = "ambiguous_identity"
            cells.append({"ticker": ticker, "status": status, "valid_row_count": len(matches),
                          "refusal_row_count": len(failures)})
    return {"table": table, "request_sha256": capture.request_sha256,
            "source_file_sha256": hash_bytes(capture.raw), "raw_row_count": count,
            "page_complete_below_limit": True, "rows": accepted,
            "refusals": refused, "requested_symbol_cells": cells}


def _identity(captures: tuple[CapturedSharadarResponse, ...], retrieved_at: str) -> str:
    return hash_payload({"retrieved_at": retrieved_at, "captures": [
        {"request_id": row.request_id, "request_sha256": row.request_sha256,
         "raw_sha256": hash_bytes(row.raw), "content_type": row.content_type,
         "http_status": row.http_status} for row in captures]})


def _build(captures: tuple[CapturedSharadarResponse, ...], retrieved_at: str) -> dict[str, Any]:
    qualification_protocol()
    _utc(retrieved_at)
    if type(captures) is not tuple or len(captures) != MAXIMUM_REQUESTS:
        raise _refuse("complete_sixteen_response_tuple_required")
    if tuple(row.request_id for row in captures if type(row) is CapturedSharadarResponse) != REQUEST_IDS:
        raise _refuse("capture_order_or_exact_type_mismatch")
    metadata = [validate_sharadar_metadata(row, retrieved_at=retrieved_at) for row in captures[:5]]
    schemas = [validate_sharadar_schema(row) for row in captures[5:10]]
    tables = [_rows(row) for row in captures[10:]]
    dictionary = {row["normalized"]["action"] for row in tables[0]["rows"]}
    for row in tables[3]["rows"]:
        normalized = row["normalized"]
        normalized["action_dictionary_definition_present"] = normalized["action"] in dictionary
        row["normalized_record_sha256"] = hash_payload(normalized)
    payload = {"schema": SCHEMA, "protocol_sha256": PROTOCOL_SHA256,
               "capture_identity_sha256": _identity(captures, retrieved_at),
               "retrieved_at": retrieved_at,
               "publication_scope": "private_only_not_data_usability_publication",
               "metadata": metadata, "public_schemas": schemas, "tables": tables,
               "authority": _authority(), "public_known_contract_gaps": list(_GAPS)}
    payload["report_sha256"] = hash_payload(payload)
    return payload


@dataclasses.dataclass(frozen=True, slots=True)
class SharadarCompanionQualification:
    """Rebuild from immutable captures; detached output cannot alter identity."""

    captures: tuple[CapturedSharadarResponse, ...] = dataclasses.field(repr=False)
    retrieved_at: str
    _capture_identity: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self) is not SharadarCompanionQualification:
            raise _refuse("exact_qualification_type_required")
        _build(self.captures, self.retrieved_at)
        object.__setattr__(self, "_capture_identity", _identity(self.captures, self.retrieved_at))

    def to_payload(self) -> dict[str, Any]:
        if type(self) is not SharadarCompanionQualification:
            raise _refuse("exact_qualification_type_required")
        if _identity(self.captures, self.retrieved_at) != self._capture_identity:
            raise _refuse("captured_identity_changed")
        return _build(self.captures, self.retrieved_at)

    @property
    def sha256(self) -> str:
        return self.to_payload()["report_sha256"]


def qualify_sharadar_companion(
    captures: tuple[CapturedSharadarResponse, ...], *, retrieved_at: str,
    expected_protocol_sha256: str = PROTOCOL_SHA256,
) -> SharadarCompanionQualification:
    if expected_protocol_sha256 != PROTOCOL_SHA256:
        raise _refuse("expected_protocol_hash_mismatch")
    return SharadarCompanionQualification(captures, retrieved_at)
