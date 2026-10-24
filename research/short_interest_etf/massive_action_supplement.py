"""Private, outcome-free Massive identity and corporate-action supplement.

This pure module binds an exactly frozen first-page capture inventory.  It
does not request data, admit source rights, manufacture historical intervals,
or supply terminal consideration.  Unknown provider fields remain in bound
raw bytes but are never promoted into the normalized private representation.
"""
from __future__ import annotations

import dataclasses
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from data.hashing import hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp


SYMBOLS = ("AAPL", "BRK.A", "BRK.B", "FRC", "SIVB", "TWTR", "META", "FB", "BBBY", "BBBY1")
REFERENCE_DATES = ("2022-10-14", "2023-02-28", "2023-05-15")
DATE_FROM, DATE_TO = "2022-01-01", "2023-12-31"
MAXIMUM_REQUESTS = 62
MAXIMUM_RESPONSE_BYTES = 2 * 1024 * 1024
_API = "https://api.massive.com"
_REFERENCE = tuple((f"reference-{ticker}-{at.replace('-', '')}-{state}", ticker, at, state == "active")
                   for ticker in SYMBOLS for at in REFERENCE_DATES for state in ("active", "inactive"))
REQUEST_IDS = tuple(item[0] for item in _REFERENCE) + ("rows-dividends", "rows-splits")
_REFERENCE_LOOKUP = {item[0]: item[1:] for item in _REFERENCE}
_FIGI = re.compile(r"BBG[0-9A-Z]{9}\Z")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
_GAPS = (
    "ten_distinct_tokens_and_three_snapshots_not_full_study_population_or_effective_intervals",
    "original_SI_vintages_all_corrections_and_actual_availability_not_established",
    "dated_reference_not_filing_availability_or_same_class_denominator_admission",
    "date_only_dividend_pay_date_not_intraday_or_actual_cash_settlement_proof",
    "acquisition_elections_and_bankruptcy_terminal_payment_economics_not_supplied",
    "source_rights_retention_and_exact_QC_processing_route_separately_qualified",
    "prospective_actual_outcome_look_and_full_input_binding_not_registered",
)


class MassiveActionSupplementError(ValueError):
    """Safely named refusal; provider texts and external exceptions stay out."""


def _refuse(reason: str) -> MassiveActionSupplementError:
    return MassiveActionSupplementError("REFUSED: " + reason)


def _authority() -> dict[str, Any]:
    return {"source_only": True, "source_admitted": False, "point_in_time_data": False,
            "ready_for_empirical_backtest": False, "outcome_access_authorized": False,
            "qc_authorized": False, "production_authoritative": False,
            "trading_authority": False, "actual_outcome_looks": 0,
            "allocated_alpha": 0, "qc_attempts": 0}


def massive_request(request_id: str) -> dict[str, Any]:
    """Detached frozen descriptor; authentication is runtime-header-only."""
    if type(request_id) is not str or request_id not in REQUEST_IDS:
        raise _refuse("unknown_request_id")
    if request_id in _REFERENCE_LOOKUP:
        ticker, at, active = _REFERENCE_LOOKUP[request_id]
        route = "/v3/reference/tickers"
        params = {"ticker": ticker, "market": "stocks", "date": at,
                  "active": "true" if active else "false", "limit": "1000",
                  "sort": "ticker", "order": "asc"}
    else:
        table = request_id.removeprefix("rows-")
        field = "ex_dividend_date" if table == "dividends" else "execution_date"
        route = "/stocks/v1/" + table
        params = {"ticker.any_of": ",".join(SYMBOLS), field + ".gte": DATE_FROM,
                  field + ".lte": DATE_TO, "sort": field + ".asc", "limit": "5000"}
    return {"request_id": request_id, "method": "GET", "url": _API + route, "params": params}


def request_sha256(request_id: str) -> str:
    return hash_payload(massive_request(request_id))


def supplement_protocol() -> dict[str, Any]:
    payload = {
        "schema": "si-massive-action-supplement-protocol-v1",
        "purpose": "private_source_only_identity_dividend_payment_and_split_supplement",
        "candidate_symbols": list(SYMBOLS), "symbols_are_distinct_no_aliases": True,
        "reference_dates": list(REFERENCE_DATES), "action_date_from": DATE_FROM,
        "action_date_to": DATE_TO, "request_ids": list(REQUEST_IDS),
        "requests": [massive_request(item) for item in REQUEST_IDS],
        "maximum_requests": MAXIMUM_REQUESTS, "automatic_retries": 0,
        "maximum_pages_per_request": 1, "maximum_response_bytes": MAXIMUM_RESPONSE_BYTES,
        "page_rule": "next_url_refused_count_matches_array_omitted_results_only_explicit_integer_zero_count",
        "numeric_rule": "lexical_JSON_number_exact_Decimal_to_Fraction_no_binary_float",
        "row_record_hash_rule": "source_file_sha256_row_index_and_parsed_record_sha256_bind_lexical_bytes",
        "duplicate_rule": "all_identifiable_key_collisions_quarantined_before_value_validation",
        "identity_rule": "composite_and_share_class_FIGI_distinct_dated_assertions_not_intervals",
        "dividend_rule": "raw_cash_amount_and_provider_date_only_pay_date_no_zero_or_ex_date_substitution",
        "split_rule": "exact_split_to_over_split_from_including_stock_dividend_no_cumulative_factor",
        "terminal_rule": "no_terminal_payment_endpoint_or_zero_cash_inference",
        "publication_rule": "private_only_no_provider_rows_or_source_fitness_publication",
        "authority": _authority(), "public_known_contract_gaps": list(_GAPS),
    }
    if hash_payload(payload) != PROTOCOL_SHA256:
        raise _refuse("frozen_protocol_hash_mismatch")
    return payload


# Pinned independently after the prospective descriptor was constructed.
PROTOCOL_SHA256 = "3ab6565797ab1bed34e30dda310040aebdab643f457d9384283eacaee0af321f"


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedMassiveActionResponse:
    request_id: str
    request_sha256: str
    raw: bytes = dataclasses.field(repr=False)
    http_status: int = 200
    content_type: str = "application/json"

    def __post_init__(self) -> None:
        if type(self) is not CapturedMassiveActionResponse:
            raise _refuse("exact_capture_type_required")
        if type(self.request_id) is not str or self.request_id not in REQUEST_IDS or self.request_sha256 != request_sha256(self.request_id):
            raise _refuse("request_binding_mismatch")
        if type(self.raw) is not bytes or not self.raw:
            raise _refuse("capture_requires_nonempty_immutable_bytes")
        if len(self.raw) > MAXIMUM_RESPONSE_BYTES:
            raise _refuse("capture_byte_limit_exceeded")
        if type(self.http_status) is not int or self.http_status != 200:
            raise _refuse("HTTP_status_not_200")
        if (type(self.content_type) is not str or len(self.content_type) > 256
                or any(ord(char) < 32 or ord(char) == 127 for char in self.content_type)
                or self.content_type.split(";", 1)[0].strip().lower() != "application/json"):
            raise _refuse("unexpected_content_type")


class _NumberToken(str):
    """Preserve exact numeric lexical text without accepting JSON strings."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise _refuse("duplicate_JSON_key")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise _refuse("nonfinite_JSON_constant")


def _unicode(value: Any) -> None:
    if isinstance(value, str):
        value.encode("utf-8")
    elif type(value) is dict:
        for key, item in value.items():
            key.encode("utf-8")
            _unicode(item)
    elif type(value) is list:
        for item in value:
            _unicode(item)


def _json(raw: bytes) -> Any:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_float=_NumberToken, parse_constant=_constant)
        _unicode(value)
        return value
    except MassiveActionSupplementError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise _refuse("invalid_UTF8_JSON") from None


def _text(value: Any, *, maximum: int = 256) -> str:
    if (type(value) is not str or not value or len(value) > maximum or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise _refuse("invalid_text")
    return value


def _date(value: Any) -> str:
    if type(value) is not str:
        raise _refuse("invalid_canonical_date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise _refuse("invalid_canonical_date") from None
    if parsed.isoformat() != value:
        raise _refuse("invalid_canonical_date")
    return value


def _number(value: Any, *, positive: bool = False) -> Fraction:
    if type(value) is int and abs(value) <= 10**30:
        result = Fraction(value)
    elif type(value) is _NumberToken and len(value) <= 128 and _NUMBER.fullmatch(value):
        try:
            parsed = Decimal(value)
        except InvalidOperation:
            raise _refuse("invalid_number_token") from None
        if not parsed.is_finite() or abs(parsed.adjusted()) > 30:
            raise _refuse("numeric_bound_exceeded")
        result = Fraction(parsed)
    else:
        raise _refuse("numeric_JSON_token_required")
    if result < 0 or (positive and result <= 0):
        raise _refuse("positive_number_required" if positive else "nonnegative_number_required")
    return result


def _rational(value: Fraction | None) -> dict[str, int] | None:
    return None if value is None else {"numerator": value.numerator, "denominator": value.denominator}


def _optional_text(row: dict, name: str, *, maximum: int = 256) -> str | None:
    return None if row.get(name) is None else _text(row[name], maximum=maximum)


def _optional_date(row: dict, name: str) -> str | None:
    return None if row.get(name) is None else _date(row[name])


def _optional_number(row: dict, name: str, *, positive: bool = False) -> Fraction | None:
    return None if row.get(name) is None else _number(row[name], positive=positive)


def _optional_utc(row: dict, name: str) -> str | None:
    value = row.get(name)
    if value is None:
        return None
    try:
        parse_utc_timestamp(value, name)
    except (TypeError, ValueError):
        raise _refuse("invalid_UTC_reference_timestamp") from None
    return value


def _key(table: str, row: Any) -> tuple[Any, ...] | None:
    if type(row) is not dict:
        return None
    if table == "reference":
        # Exact symbol duplicates are ambiguous even when one peer has an
        # invalid active/type/FIGI value.  Validate those values only later.
        try:
            return ("ticker", _text(row.get("ticker")))
        except MassiveActionSupplementError:
            return None
    try:
        if row.get("id") is not None:
            return ("id", _text(row["id"]))
        at = "ex_dividend_date" if table == "dividends" else "execution_date"
        return ("date_ticker", _text(row.get("ticker")), _date(row.get(at)))
    except MassiveActionSupplementError:
        return None


def _normalize_reference(row: dict, request_id: str) -> dict[str, Any]:
    ticker, at, active = _REFERENCE_LOOKUP[request_id]
    if row.get("ticker") != ticker:
        raise _refuse("symbol_filter_mismatch_no_alias")
    if type(row.get("active")) is not bool or row["active"] != active:
        raise _refuse("active_filter_mismatch")
    result = {"ticker": ticker, "query_date": at, "active": active}
    names = ("composite_figi", "share_class_figi", "cik", "primary_exchange", "type",
             "locale", "market", "currency_name", "name")
    for name in names:
        result[name] = _optional_text(row, name)
    for name in ("composite_figi", "share_class_figi"):
        if result[name] is not None and _FIGI.fullmatch(result[name]) is None:
            raise _refuse("invalid_FIGI")
    if result["market"] is not None and result["market"] != "stocks":
        raise _refuse("market_filter_mismatch")
    if result["cik"] is not None and re.fullmatch(r"[0-9]{1,10}", result["cik"]) is None:
        raise _refuse("invalid_CIK")
    result["delisted_utc"] = _optional_utc(row, "delisted_utc")
    result["last_updated_utc"] = _optional_utc(row, "last_updated_utc")
    result["missing_fields"] = [name for name in ("composite_figi", "share_class_figi", "primary_exchange", "type", "locale", "market") if result[name] is None]
    result.update({"effective_historical_mapping_admitted": False, "historical_availability_verified": False,
                   "same_share_class_denominator_admitted": False})
    return result


def _normalize_action(table: str, row: dict) -> dict[str, Any]:
    ticker = _text(row.get("ticker"))
    if ticker not in SYMBOLS:
        raise _refuse("symbol_filter_mismatch_no_alias")
    field = "ex_dividend_date" if table == "dividends" else "execution_date"
    at = _date(row.get(field))
    if not DATE_FROM <= at <= DATE_TO:
        raise _refuse("date_window_filter_mismatch")
    result = {"ticker": ticker, field: at, "id": _optional_text(row, "id"),
              "historical_availability_verified": False, "terminal_economics_admitted": False}
    if table == "dividends":
        cash = _optional_number(row, "cash_amount")
        result.update({"cash_amount": _rational(cash), "currency": _optional_text(row, "currency"),
                       "pay_date": _optional_date(row, "pay_date"),
                       "declaration_date": _optional_date(row, "declaration_date"),
                       "record_date": _optional_date(row, "record_date"),
                       "distribution_type": _optional_text(row, "distribution_type"),
                       "payment_precision": "date_only", "payment_timestamp": None,
                       "payment_cash_settlement_verified": False})
        if result["currency"] is not None and re.fullmatch(r"[A-Z]{3}", result["currency"]) is None:
            raise _refuse("invalid_currency")
        frequency = row.get("frequency")
        if frequency is not None and (type(frequency) is not int or not 0 <= frequency <= 365):
            raise _refuse("invalid_frequency")
        result["frequency"] = frequency
        result["missing_fields"] = [name for name in ("cash_amount", "currency", "pay_date") if result[name] is None]
        # Special due-bill events can have pay_date before ex_date; do not
        # declare such provider records malformed or silently change timing.
        result["due_bill_or_nonstandard_payment_order_requires_qualification"] = result["pay_date"] is not None and result["pay_date"] < at
    else:
        source = _optional_number(row, "split_from", positive=True)
        target = _optional_number(row, "split_to", positive=True)
        kind = _optional_text(row, "adjustment_type")
        if kind is not None and kind not in {"forward_split", "reverse_split", "stock_dividend"}:
            raise _refuse("unsupported_split_adjustment_type")
        result.update({"split_from": _rational(source), "split_to": _rational(target),
                       "split_ratio": _rational(None if source is None or target is None else target / source),
                       "adjustment_type": kind,
                       "missing_fields": [name for name, value in (("split_from", source), ("split_to", target), ("adjustment_type", kind)) if value is None]})
    return result


def validate_massive_response(capture: CapturedMassiveActionResponse) -> dict[str, Any]:
    """Validate one detached page; quarantine rows without silent drops."""
    if type(capture) is not CapturedMassiveActionResponse:
        raise _refuse("exact_capture_type_required")
    CapturedMassiveActionResponse.__post_init__(capture)
    table = "reference" if capture.request_id in _REFERENCE_LOOKUP else capture.request_id.removeprefix("rows-")
    envelope = _json(capture.raw)
    if type(envelope) is not dict or "status" not in envelope or set(envelope) - {"status", "results", "count", "request_id", "next_url"}:
        raise _refuse("missing_or_unknown_envelope_fields")
    if envelope["status"] != "OK":
        raise _refuse("response_status_not_OK")
    if "request_id" in envelope:
        external_id = envelope["request_id"]
        if type(external_id) is int:
            if not 0 <= external_id <= 10**18:
                raise _refuse("invalid_external_request_id")
        elif type(external_id) is str:
            _text(external_id)
        else:
            raise _refuse("invalid_external_request_id")
    absent = "results" not in envelope
    if absent and (type(envelope.get("count")) is not int or envelope["count"] != 0):
        raise _refuse("missing_results_without_explicit_zero_count")
    rows = [] if absent else envelope["results"]
    limit = 1000 if table == "reference" else 5000
    if type(rows) is not list or len(rows) > limit:
        raise _refuse("results_array_or_limit_invalid")
    if "count" in envelope and (type(envelope["count"]) is not int or envelope["count"] != len(rows)):
        raise _refuse("row_count_mismatch")
    if envelope.get("next_url") is not None:
        if type(envelope["next_url"]) is not str:
            raise _refuse("invalid_next_url")
        if envelope["next_url"]:
            raise _refuse("next_page_present_unconsumed")
    keys = [_key(table, row) for row in rows]
    counts: dict[tuple[Any, ...], int] = {}
    for key in keys:
        if key is not None:
            counts[key] = counts.get(key, 0) + 1
    accepted, refused = [], []
    source_digest = hash_bytes(capture.raw)
    for index, row in enumerate(rows):
        # A lexical numeric token is a str subclass, so its canonical parsed
        # digest alone can collide with an ordinary JSON numeric string.
        # Bind the complete original bytes and position into each row receipt;
        # retain the parsed digest only as a separate structural diagnostic.
        parsed_digest = hash_payload(row)
        record_digest = hash_payload({"source_file_sha256": source_digest,
                                      "row_index": index, "parsed_record_sha256": parsed_digest})
        origin = {"row_index": index, "raw_record_sha256": record_digest,
                  "parsed_record_sha256": parsed_digest, "source_file_sha256": source_digest}
        if keys[index] is not None and counts[keys[index]] > 1:
            refused.append({**origin, "status": "duplicate", "reason": "identifiable_key_collision"})
            continue
        try:
            if type(row) is not dict:
                raise _refuse("row_not_object")
            normalized = _normalize_reference(row, capture.request_id) if table == "reference" else _normalize_action(table, row)
        except MassiveActionSupplementError as exc:
            refused.append({**origin, "status": "malformed", "reason": str(exc)})
        else:
            accepted.append({**origin, "normalized": normalized, "normalized_record_sha256": hash_payload(normalized)})
    symbols = (_REFERENCE_LOOKUP[capture.request_id][0],) if table == "reference" else SYMBOLS
    cells = []
    for ticker in symbols:
        matches = [row for row in accepted if row["normalized"]["ticker"] == ticker]
        # An out-of-scope/malformed symbol is not interpolated into an error;
        # its row index and bound record hash retain it in the private report.
        failures = [row for row in refused if type(rows[row["row_index"]]) is dict and rows[row["row_index"]].get("ticker") == ticker]
        status = "refused" if failures else "missing" if not matches else "incomplete" if any(row["normalized"]["missing_fields"] for row in matches) else "present"
        cells.append({"ticker": ticker, "status": status, "valid_row_count": len(matches), "refusal_row_count": len(failures)})
    return {"table": table, "request_id": capture.request_id, "request_sha256": capture.request_sha256,
            "source_file_sha256": source_digest, "raw_row_count": len(rows),
            "page_complete": True, "raw_results_absent": absent, "rows": accepted, "refusals": refused,
            "requested_symbol_cells": cells}


def _check_captures(captures: tuple[CapturedMassiveActionResponse, ...]) -> None:
    if type(captures) is not tuple or len(captures) != MAXIMUM_REQUESTS:
        raise _refuse("complete_sixtytwo_response_tuple_required")
    if tuple(row.request_id for row in captures if type(row) is CapturedMassiveActionResponse) != REQUEST_IDS:
        raise _refuse("capture_order_or_exact_type_mismatch")
    for capture in captures:
        CapturedMassiveActionResponse.__post_init__(capture)


def _identity(captures: tuple[CapturedMassiveActionResponse, ...], retrieved_at: str) -> str:
    _check_captures(captures)
    return hash_payload({"retrieved_at": retrieved_at, "captures": [
        {"request_id": row.request_id, "request_sha256": row.request_sha256,
         "raw_sha256": hash_bytes(row.raw), "content_type": row.content_type,
         "http_status": row.http_status} for row in captures]})


def _build(captures: tuple[CapturedMassiveActionResponse, ...], retrieved_at: str) -> dict[str, Any]:
    supplement_protocol()
    try:
        parse_utc_timestamp(retrieved_at, "retrieved_at")
    except (TypeError, ValueError):
        raise _refuse("invalid_retrieved_at") from None
    _check_captures(captures)
    payload = {"schema": "si-massive-action-supplement-qualification-v1", "protocol_sha256": PROTOCOL_SHA256,
               "capture_identity_sha256": _identity(captures, retrieved_at), "retrieved_at": retrieved_at,
               "publication_scope": "private_only_source_qualification",
               "tables": [validate_massive_response(capture) for capture in captures],
               "authority": _authority(), "public_known_contract_gaps": list(_GAPS)}
    payload["report_sha256"] = hash_payload(payload)
    return payload


@dataclasses.dataclass(frozen=True, slots=True)
class MassiveActionSupplementQualification:
    captures: tuple[CapturedMassiveActionResponse, ...] = dataclasses.field(repr=False)
    retrieved_at: str
    _capture_identity: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self) is not MassiveActionSupplementQualification:
            raise _refuse("exact_qualification_type_required")
        _build(self.captures, self.retrieved_at)
        object.__setattr__(self, "_capture_identity", _identity(self.captures, self.retrieved_at))

    def to_payload(self) -> dict[str, Any]:
        if type(self) is not MassiveActionSupplementQualification:
            raise _refuse("exact_qualification_type_required")
        if _identity(self.captures, self.retrieved_at) != self._capture_identity:
            raise _refuse("captured_identity_changed")
        return _build(self.captures, self.retrieved_at)

    @property
    def sha256(self) -> str:
        return self.to_payload()["report_sha256"]


def qualify_massive_action_supplement(
    captures: tuple[CapturedMassiveActionResponse, ...], *, retrieved_at: str,
    expected_protocol_sha256: str = PROTOCOL_SHA256,
) -> MassiveActionSupplementQualification:
    if expected_protocol_sha256 != PROTOCOL_SHA256:
        raise _refuse("expected_protocol_hash_mismatch")
    return MassiveActionSupplementQualification(captures, retrieved_at)
