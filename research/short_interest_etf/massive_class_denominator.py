"""Private source-only dated Massive class/denominator pilot, never admission.

One exact ticker overview response keeps composite and share-class identifiers
as distinct source fields and keeps only the particular-class share count.
The provider's date filter uses SEC report periods, not publication availability.
This module has no transport, file access, outcome evaluation or QC capability.
"""
from __future__ import annotations

import dataclasses
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
from research.short_interest_etf.massive_action_supplement import REFERENCE_DATES, SYMBOLS


MAXIMUM_REQUESTS = 30
MAXIMUM_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_IDS = tuple(f"overview-{symbol}-{at.replace('-', '')}"
                    for symbol in SYMBOLS for at in REFERENCE_DATES)
_REQUESTS = {f"overview-{symbol}-{at.replace('-', '')}": (symbol, at)
             for symbol in SYMBOLS for at in REFERENCE_DATES}
_FIGI = re.compile(r"BBG[0-9A-Z]{9}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
_INTEGER = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_GAPS = (
    "ten_distinct_tokens_three_dates_are_a_pilot_not_full_population_or_effective_intervals",
    "SEC_period_filter_not_original_filing_or_public_availability_evidence",
    "no_raw_ticker_to_native_provider_key_historical_mapping_admission",
    "same_response_class_count_evidence_not_independent_denominator_admission",
    "composite_and_class_identifiers_are_distinct_fields_not_casts_or_issuer_transfers",
    "no_corporate_payment_terminal_economics_prices_volume_returns_or_outcomes",
    "source_use_and_exact_processing_rights_are_independent_facts",
    "prospective_evaluation_power_date_look_and_QC_representation_not_registered",
)


class MassiveClassDenominatorError(ValueError):
    """Fixed refusal codes contain no provider body, contact or credential text."""


def _refuse(reason: str) -> MassiveClassDenominatorError:
    return MassiveClassDenominatorError("REFUSED: " + reason)


def _authority() -> dict[str, Any]:
    return {"source_only": True, "latest_revised_only": True,
            "source_admitted": False, "point_in_time_data": False,
            "historical_identity_admitted": False, "same_class_denominator_admitted": False,
            "ready_for_empirical_backtest": False, "outcome_access_authorized": False,
            "qc_authorized": False, "production_authoritative": False,
            "trading_authority": False, "actual_outcome_looks": 0,
            "allocated_alpha": 0, "qc_attempts": 0}


def massive_request(request_id: str) -> dict[str, Any]:
    """Fixed detached descriptor; authentication belongs only in runtime headers."""
    if type(request_id) is not str or request_id not in _REQUESTS:
        raise _refuse("unknown_request_id")
    symbol, at = _REQUESTS[request_id]
    # All frozen tokens are ASCII URL-unreserved characters. Their exact
    # path-segment encoding is unchanged; never accept caller URL fragments.
    if re.fullmatch(r"[A-Z][A-Z0-9.]*", symbol) is None:
        raise _refuse("frozen_symbol_not_URL_unreserved")
    return {"request_id": request_id, "method": "GET",
            "url": "https://api.massive.com/v3/reference/tickers/" + symbol,
            "params": {"date": at}}


def request_sha256(request_id: str) -> str:
    return hash_payload(massive_request(request_id))


def denominator_protocol() -> dict[str, Any]:
    payload = {
        "schema": "si-massive-class-denominator-protocol-v1",
        "purpose": "private_source_only_dated_class_specific_denominator_pilot",
        "candidate_symbols": list(SYMBOLS), "symbols_are_distinct_no_aliases": True,
        "reference_dates": list(REFERENCE_DATES), "request_ids": list(REQUEST_IDS),
        "requests": [massive_request(item) for item in REQUEST_IDS],
        "maximum_requests": MAXIMUM_REQUESTS, "maximum_response_bytes": MAXIMUM_RESPONSE_BYTES,
        "automatic_retries": 0, "maximum_pages_per_request": 1,
        "source_contract": "https://massive.com/docs/rest/stocks/tickers/ticker-overview",
        "date_semantics": "SEC_period_of_report_not_filing_or_publication_availability",
        "number_rule": "exact_positive_integral_JSON_number_not_float_or_string",
        "denominator_rule": "share_class_shares_outstanding_only_never_weighted_issuer_or_other_class",
        "identifier_rule": "optional_BBG12_lexical_source_fields_no_FIGI_cast_or_issuance_proof",
        "equal_identifier_rule": "conservative_ambiguous_relation_not_provider_invalidity_claim",
        "receipt_rule": "each_request_hash_status_body_observation_raw_digest_and_UTC_clock_bound",
        "envelope_rule": "single_object_OK_no_nonnull_next_url_duplicates_nonfinite_or_conflicting_fields",
        "missing_rule": "retain_missing_HTTP404_malformed_ambiguous_and_incomplete_receipts_no_fallback",
        "publication_rule": "private_only_no_provider_rows_or_fitness_publication",
        "authority": _authority(), "public_known_contract_gaps": list(_GAPS),
    }
    if hash_payload(payload) != PROTOCOL_SHA256:
        raise _refuse("frozen_protocol_hash_mismatch")
    return payload


# Pinned after constructing the exact prospective descriptor, before capture.
PROTOCOL_SHA256 = "bd2f76ff97218dd4acda21bd7bc69fa37e2b3254eafbcca95c5750b4acb56d03"


def _utc(value: Any, name: str) -> Any:
    try:
        return parse_utc_timestamp(value, name)
    except (TypeError, ValueError):
        raise _refuse("invalid_canonical_UTC_clock") from None


@dataclasses.dataclass(frozen=True, slots=True)
class CapturedMassiveClassResponse:
    request_id: str
    request_sha256: str
    raw: bytes = dataclasses.field(repr=False)
    received_at: str
    raw_sha256: str
    http_status: int = 200
    content_type: str = "application/json"
    body_observed: bool = True

    def __post_init__(self) -> None:
        if type(self) is not CapturedMassiveClassResponse:
            raise _refuse("exact_capture_type_required")
        if (type(self.request_id) is not str or self.request_id not in _REQUESTS
                or type(self.request_sha256) is not str
                or self.request_sha256 != request_sha256(self.request_id)):
            raise _refuse("request_binding_mismatch")
        if type(self.raw) is not bytes or len(self.raw) > MAXIMUM_RESPONSE_BYTES:
            raise _refuse("bounded_immutable_capture_bytes_required")
        if (type(self.raw_sha256) is not str or _HASH.fullmatch(self.raw_sha256) is None
                or self.raw_sha256 != hash_bytes(self.raw)):
            raise _refuse("capture_byte_hash_mismatch")
        if type(self.http_status) is not int or not 100 <= self.http_status <= 599:
            raise _refuse("invalid_HTTP_status")
        if type(self.body_observed) is not bool:
            raise _refuse("body_observation_boolean_required")
        if not self.body_observed and (self.raw or self.http_status == 200):
            raise _refuse("unobserved_body_placeholder_mismatch")
        if (type(self.content_type) is not str or len(self.content_type) > 256
                or any(ord(char) < 32 or ord(char) > 126 for char in self.content_type)):
            raise _refuse("invalid_content_type_receipt")
        _utc(self.received_at, "received_at")


class _NumberToken(str):
    """JSON numeric lexical bytes, distinct from provider JSON strings."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
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
                           parse_int=_NumberToken, parse_float=_NumberToken,
                           parse_constant=_constant)
        _unicode(value)
        return value
    except MassiveClassDenominatorError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise _refuse("invalid_UTF8_JSON") from None


def _text(value: Any, maximum: int = 256) -> str:
    if (type(value) is not str or not value or len(value) > maximum or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise _refuse("invalid_source_text_field")
    return value


def _optional_text(row: dict[str, Any], name: str) -> str | None:
    return None if row.get(name) is None else _text(row[name])


def _date(value: Any) -> str:
    if type(value) is not str:
        raise _refuse("invalid_canonical_source_date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise _refuse("invalid_canonical_source_date") from None
    if parsed.isoformat() != value:
        raise _refuse("invalid_canonical_source_date")
    return value


def _shares(value: Any) -> dict[str, Any]:
    if type(value) is not _NumberToken or len(value) > 128 or _NUMBER.fullmatch(value) is None:
        raise _refuse("shares_require_JSON_number_token")
    try:
        decimal = Decimal(value)
    except InvalidOperation:
        raise _refuse("invalid_shares_number") from None
    if not decimal.is_finite() or abs(decimal.adjusted()) > 30:
        raise _refuse("shares_number_bound_exceeded")
    exact = Fraction(decimal)
    if exact <= 0 or exact.denominator != 1:
        raise _refuse("shares_require_exact_positive_integer")
    return {"numerator": exact.numerator, "denominator": 1,
            "source_number_token": str(value),
            "source_field": "share_class_shares_outstanding"}


def _small_integer(value: Any) -> int:
    if type(value) is not _NumberToken or _INTEGER.fullmatch(value) is None or len(value) > 8:
        raise _refuse("count_requires_small_JSON_integer")
    return int(value)


def _normalized(row: dict[str, Any], request_id: str) -> dict[str, Any]:
    symbol, at = _REQUESTS[request_id]
    if row.get("ticker") != symbol or type(row.get("ticker")) is not str:
        raise _refuse("exact_symbol_mismatch_no_alias")
    result = {"ticker": symbol, "query_date": at,
              "date_semantics": "SEC_period_of_report_not_filing_or_publication_availability"}
    for name in ("composite_figi", "share_class_figi", "cik", "primary_exchange",
                 "type", "locale", "market", "currency_name"):
        result[name] = _optional_text(row, name)
    for name in ("composite_figi", "share_class_figi"):
        if result[name] is not None and _FIGI.fullmatch(result[name]) is None:
            raise _refuse("invalid_lexical_FIGI_field")
    if result["cik"] is not None and re.fullmatch(r"[0-9]{1,10}", result["cik"]) is None:
        raise _refuse("invalid_source_CIK")
    if result["market"] is not None and result["market"] != "stocks":
        raise _refuse("source_market_not_stocks")
    if result["locale"] is not None and result["locale"] != "us":
        raise _refuse("source_locale_not_us")
    active = row.get("active")
    if active is not None and type(active) is not bool:
        raise _refuse("invalid_source_active_boolean")
    result["active"] = active
    result["list_date"] = None if row.get("list_date") is None else _date(row["list_date"])
    result["delisted_utc"] = None
    if row.get("delisted_utc") is not None:
        _utc(row["delisted_utc"], "delisted_utc")
        result["delisted_utc"] = row["delisted_utc"]
    result["share_class_shares_outstanding"] = (
        None if row.get("share_class_shares_outstanding") is None
        else _shares(row["share_class_shares_outstanding"]))
    result["missing_fields"] = [name for name in (
        "composite_figi", "share_class_figi", "share_class_shares_outstanding",
        "active", "primary_exchange", "type", "locale", "market", "currency_name")
        if result[name] is None]
    # Equal strings are not declared invalid by the provider specification.
    # Conservatively keep the observation, but refuse a positive relation.
    result["relation_ambiguous"] = (result["composite_figi"] is not None
                                    and result["composite_figi"] == result["share_class_figi"])
    result.update({"historical_identity_admitted": False,
                   "same_class_denominator_admitted": False,
                   "historical_availability_verified": False,
                   "FIGI_issuance_verified": False, "issuer_denominator_transfer": False})
    return result


def validate_massive_response(capture: CapturedMassiveClassResponse) -> dict[str, Any]:
    """Retain one private source receipt including every dangerous refusal."""
    if type(capture) is not CapturedMassiveClassResponse:
        raise _refuse("exact_capture_type_required")
    CapturedMassiveClassResponse.__post_init__(capture)
    descriptor = massive_request(capture.request_id)
    source_hash = capture.raw_sha256 if capture.body_observed else None
    origin = {"request_id": capture.request_id, "request_sha256": capture.request_sha256,
              "received_at": capture.received_at, "http_status": capture.http_status,
              "content_type": capture.content_type, "body_observed": capture.body_observed,
              "source_file_sha256": source_hash,
              "placeholder_byte_sha256": None if capture.body_observed else capture.raw_sha256,
              "source_locator": "$.results", "request": descriptor}
    result = {**origin, "status": "refused", "reason": None, "normalized": None,
              "authority": _authority()}
    if capture.http_status != 200:
        result["status"] = "missing" if capture.http_status == 404 else "refused"
        result["reason"] = ("HTTP404_body_unobserved" if not capture.body_observed
                            and capture.http_status == 404 else "HTTP_status_not_200")
        return result
    if not capture.raw:
        return {**result, "status": "missing", "reason": "observed_empty_body"}
    if capture.content_type.split(";", 1)[0].strip().lower() != "application/json":
        return {**result, "reason": "unexpected_JSON_content_type"}
    try:
        envelope = _json(capture.raw)
        if type(envelope) is not dict or set(envelope) - {"status", "results", "count", "request_id", "next_url"}:
            raise _refuse("unknown_or_nonobject_envelope")
        if type(envelope.get("status")) is not str or envelope["status"] != "OK":
            raise _refuse("missing_or_non_OK_status")
        if envelope.get("next_url") is not None:
            raise _refuse("next_url_present_no_paging")
        if "request_id" in envelope:
            external_id = envelope["request_id"]
            if type(external_id) is _NumberToken:
                _small_integer(external_id)
            else:
                _text(external_id)
        row = envelope.get("results")
        count = None if "count" not in envelope else _small_integer(envelope["count"])
        if row is None:
            if count not in (None, 0):
                raise _refuse("count_conflicts_with_missing_result")
            return {**result, "status": "missing", "reason": "missing_result_object"}
        if type(row) is list:
            return {**result, "status": "ambiguous", "reason": "overview_not_single_result_object"}
        if type(row) is not dict or count not in (None, 1):
            raise _refuse("invalid_or_conflicting_single_result")
        normalized = _normalized(row, capture.request_id)
    except MassiveClassDenominatorError as exc:
        # Errors are exclusively fixed local codes, never external exception text.
        return {**result, "status": "malformed", "reason": str(exc).removeprefix("REFUSED: ")}
    status = "ambiguous" if normalized["relation_ambiguous"] else "incomplete" if normalized["missing_fields"] else "present"
    return {**result, "status": status,
            "reason": "equal_identifier_fields_conservative_relation_refusal" if status == "ambiguous" else None,
            "normalized": normalized, "normalized_record_sha256": hash_payload(normalized),
            "source_record_sha256": hash_payload({"request_sha256": capture.request_sha256,
                "source_file_sha256": source_hash, "source_locator": "$.results"})}


def _checked(captures: tuple[CapturedMassiveClassResponse, ...], retrieved_at: str) -> None:
    if type(captures) is not tuple or len(captures) != MAXIMUM_REQUESTS:
        raise _refuse("complete_thirty_capture_tuple_required")
    if tuple(item.request_id for item in captures if type(item) is CapturedMassiveClassResponse) != REQUEST_IDS:
        raise _refuse("capture_order_or_exact_type_mismatch")
    end = _utc(retrieved_at, "retrieved_at")
    previous = None
    for capture in captures:
        CapturedMassiveClassResponse.__post_init__(capture)
        received = _utc(capture.received_at, "received_at")
        if received > end or (previous is not None and received < previous):
            raise _refuse("capture_clock_order_mismatch")
        previous = received


def _capture_identity(captures: tuple[CapturedMassiveClassResponse, ...], retrieved_at: str) -> str:
    _checked(captures, retrieved_at)
    return hash_payload({"retrieved_at": retrieved_at, "captures": [
        {"request_id": item.request_id, "request_sha256": item.request_sha256,
         "raw_sha256": item.raw_sha256, "received_at": item.received_at,
         "http_status": item.http_status, "content_type": item.content_type,
         "body_observed": item.body_observed} for item in captures]})


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class MassiveClassDenominatorQualification:
    _captures: tuple[CapturedMassiveClassResponse, ...] = dataclasses.field(repr=False)
    _retrieved_at: str
    _capture_identity: str = dataclasses.field(repr=False)
    _report_bytes: bytes = dataclasses.field(repr=False)
    _report_sha256: str
    _seal: str = dataclasses.field(repr=False)

    def __init__(self) -> None:
        raise _refuse("qualification_requires_bound_factory")

    def to_bytes(self) -> bytes:
        if type(self) is not MassiveClassDenominatorQualification:
            raise _refuse("exact_qualification_type_required")
        try:
            identity = _capture_identity(self._captures, self._retrieved_at)
            if (identity != self._capture_identity or type(self._report_bytes) is not bytes
                    or hash_payload({"capture_identity": identity, "report_bytes_sha256": hash_bytes(self._report_bytes),
                                     "report_sha256": self._report_sha256}) != self._seal):
                raise _refuse("sealed_qualification_changed")
        except AttributeError:
            raise _refuse("uninitialized_qualification") from None
        return self._report_bytes

    def to_payload(self) -> dict[str, Any]:
        # Parsing stored canonical bytes yields a detached copy; no provider
        # reparse and no caller-owned object can mutate the stored report.
        return json.loads(self.to_bytes())

    @property
    def sha256(self) -> str:
        self.to_bytes()
        return self._report_sha256


def qualify_massive_class_denominator(
    captures: tuple[CapturedMassiveClassResponse, ...], *, retrieved_at: str,
    expected_protocol_sha256: str = PROTOCOL_SHA256,
) -> MassiveClassDenominatorQualification:
    if type(expected_protocol_sha256) is not str or expected_protocol_sha256 != PROTOCOL_SHA256:
        raise _refuse("expected_protocol_hash_mismatch")
    denominator_protocol()
    _checked(captures, retrieved_at)
    # Snapshot exact scalar/byte fields into new frozen objects rather than
    # retaining mutable aliases to caller dataclasses altered via object APIs.
    snapshots = tuple(CapturedMassiveClassResponse(
        item.request_id, item.request_sha256, item.raw, item.received_at, item.raw_sha256,
        item.http_status, item.content_type, item.body_observed) for item in captures)
    identity = _capture_identity(snapshots, retrieved_at)
    payload = {"schema": "si-massive-class-denominator-qualification-v1",
               "protocol_sha256": PROTOCOL_SHA256, "capture_identity_sha256": identity,
               "retrieved_at": retrieved_at, "publication_scope": "private_only_source_qualification",
               "responses": [validate_massive_response(item) for item in snapshots],
               "authority": _authority(), "public_known_contract_gaps": list(_GAPS)}
    digest = hash_payload(payload)
    payload["report_sha256"] = digest
    raw = canonical_json(payload).encode("utf-8")
    value = object.__new__(MassiveClassDenominatorQualification)
    for name, item in (("_captures", snapshots), ("_retrieved_at", retrieved_at),
                       ("_capture_identity", identity), ("_report_bytes", raw),
                       ("_report_sha256", digest), ("_seal", hash_payload({"capture_identity": identity,
                           "report_bytes_sha256": hash_bytes(raw), "report_sha256": digest}))):
        object.__setattr__(value, name, item)
    value.to_bytes()
    return value
