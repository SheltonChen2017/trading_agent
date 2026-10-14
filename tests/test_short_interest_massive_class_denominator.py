"""Fabricated provider-schema examples: source software, not market evidence."""
from __future__ import annotations

import dataclasses
import json
from decimal import localcontext

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.massive_class_denominator import (
    CapturedMassiveClassResponse, MassiveClassDenominatorError,
    MassiveClassDenominatorQualification, MAXIMUM_REQUESTS, MAXIMUM_RESPONSE_BYTES,
    PROTOCOL_SHA256, REQUEST_IDS, REFERENCE_DATES, SYMBOLS, denominator_protocol,
    massive_request, qualify_massive_class_denominator, request_sha256,
    validate_massive_response,
)


RECEIVED = "2026-10-13T21:00:00Z"
RETRIEVED = "2026-10-13T21:01:00Z"
FIRST = REQUEST_IDS[0]


def fixture_row(symbol="AAPL"):
    return {"ticker": symbol, "active": True, "market": "stocks", "locale": "us",
            "composite_figi": "BBG000000001", "share_class_figi": "BBG000000002",
            "share_class_shares_outstanding": 123, "weighted_shares_outstanding": 999,
            "cik": "0000000001", "primary_exchange": "XNAS", "type": "CS",
            "currency_name": "usd", "list_date": "2001-01-01"}


def capture(request_id=FIRST, row=None, *, raw=None, **kwargs):
    if raw is None:
        symbol = massive_request(request_id)["url"].rsplit("/", 1)[1]
        raw = canonical_json({"status": "OK", "results": fixture_row(symbol) if row is None else row,
                              "request_id": "fabricated-response", "count": 1}).encode()
    return CapturedMassiveClassResponse(
        request_id, request_sha256(request_id), raw,
        kwargs.pop("received_at", RECEIVED), kwargs.pop("raw_sha256", hash_bytes(raw)), **kwargs)


def all_captures():
    return tuple(capture(request_id) for request_id in REQUEST_IDS)


def test_protocol_pin_exact_order_routes_limits_authority_and_detached():
    protocol = denominator_protocol()
    assert hash_payload(protocol) == PROTOCOL_SHA256 == "bd2f76ff97218dd4acda21bd7bc69fa37e2b3254eafbcca95c5750b4acb56d03"
    assert MAXIMUM_REQUESTS == len(REQUEST_IDS) == len(set(REQUEST_IDS)) == 30
    assert protocol["candidate_symbols"] == list(SYMBOLS)
    assert protocol["reference_dates"] == list(REFERENCE_DATES)
    assert protocol["maximum_pages_per_request"] == 1
    assert protocol["automatic_retries"] == 0
    assert protocol["authority"]["source_only"] is True
    assert protocol["authority"]["latest_revised_only"] is True
    assert protocol["authority"]["ready_for_empirical_backtest"] is False
    assert protocol["authority"]["actual_outcome_looks"] == 0
    protocol["requests"][0]["url"] = "https://untrusted.invalid"
    protocol["authority"]["qc_authorized"] = True
    assert hash_payload(denominator_protocol()) == PROTOCOL_SHA256


@pytest.mark.parametrize("request_id", REQUEST_IDS)
def test_all_thirty_fixed_single_overview_requests_are_hash_bound(request_id):
    value = massive_request(request_id)
    assert value["method"] == "GET"
    symbol = value["url"].rsplit("/", 1)[1]
    assert symbol in SYMBOLS
    assert value["url"] == "https://api.massive.com/v3/reference/tickers/" + symbol
    assert set(value["params"]) == {"date"}
    assert value["params"]["date"] in REFERENCE_DATES
    assert request_sha256(request_id) == hash_payload(value)
    value["params"]["date"] = "2026-10-13"
    assert request_sha256(request_id) != hash_payload(value)


def test_source_origin_same_response_exact_count_and_closed_admissions():
    source = capture()
    value = validate_massive_response(source)
    assert value["status"] == "present"
    normalized = value["normalized"]
    assert normalized["composite_figi"] == "BBG000000001"
    assert normalized["share_class_figi"] == "BBG000000002"
    assert normalized["share_class_shares_outstanding"] == {
        "numerator": 123, "denominator": 1, "source_number_token": "123",
        "source_field": "share_class_shares_outstanding"}
    assert normalized["query_date"] == "2022-10-14"
    assert normalized["date_semantics"] == "SEC_period_of_report_not_filing_or_publication_availability"
    assert "weighted_shares_outstanding" not in normalized
    assert normalized["same_class_denominator_admitted"] is False
    assert normalized["historical_identity_admitted"] is False
    assert normalized["historical_availability_verified"] is False
    assert normalized["FIGI_issuance_verified"] is False
    assert value["source_locator"] == "$.results"
    assert value["source_file_sha256"] == hash_bytes(source.raw)
    assert value["received_at"] == RECEIVED
    assert value["request_sha256"] == request_sha256(FIRST)
    assert value["source_record_sha256"] == hash_payload({
        "source_file_sha256": hash_bytes(source.raw),
        "request_sha256": request_sha256(FIRST), "source_locator": "$.results"})


@pytest.mark.parametrize("field", ["composite_figi", "share_class_figi", "share_class_shares_outstanding",
                                    "market", "locale", "active", "type", "primary_exchange", "currency_name"])
def test_missing_optional_is_retained_incomplete_without_fallback(field):
    row = fixture_row()
    row.pop(field)
    value = validate_massive_response(capture(row=row))
    assert value["status"] == "incomplete"
    assert value["normalized"][field] is None
    assert field in value["normalized"]["missing_fields"]
    assert value["normalized"]["same_class_denominator_admitted"] is False
    if field == "share_class_shares_outstanding":
        assert "weighted_shares_outstanding" not in value["normalized"]


@pytest.mark.parametrize("token,number", [
    ("9007199254740993", 9007199254740993), ("123.0", 123), ("1.234e3", 1234),
    ("1000000000000000000000000000000", 10**30), ("1E+3", 1000)])
def test_exact_integral_numeric_tokens_keep_lexical_precision_and_ignore_decimal_context(token, number):
    raw = canonical_json({"status": "OK", "results": fixture_row()}).replace(
        '"share_class_shares_outstanding":123', '"share_class_shares_outstanding":' + token).encode()
    with localcontext() as context:
        context.prec = 2
        row = validate_massive_response(capture(raw=raw))["normalized"]
    assert row["share_class_shares_outstanding"]["numerator"] == number
    assert row["share_class_shares_outstanding"]["denominator"] == 1
    assert row["share_class_shares_outstanding"]["source_number_token"] == token


@pytest.mark.parametrize("token", ['"123"', 'true', 'false', '0', '-1', '123.5', '1e31', '1e-999999', 'NaN', 'Infinity', '-Infinity'])
def test_bad_count_tokens_never_become_weighted_count_or_zero(token):
    raw = canonical_json({"status": "OK", "results": fixture_row()}).replace(
        '"share_class_shares_outstanding":123', '"share_class_shares_outstanding":' + token).encode()
    value = validate_massive_response(capture(raw=raw))
    assert value["status"] == "malformed"
    assert value["normalized"] is None
    assert value["source_file_sha256"] == hash_bytes(raw)
    assert value["authority"]["same_class_denominator_admitted"] is False


@pytest.mark.parametrize("raw", [
    b'{"status":"OK","status":"OK","results":{}}',
    b'{"status":"OK","results":{"ticker":"AAPL","ticker":"AAPL"}}',
    b'{"status":"OK","results":{},"future":NaN}',
    b'{"status":"OK","results":{},"request_id":"\\ud800"}',
    b'\xff', b'{broken'])
def test_duplicate_nonfinite_unicode_and_invalid_JSON_retained_with_fixed_refusal(raw):
    value = validate_massive_response(capture(raw=raw))
    assert value["status"] == "malformed"
    assert value["normalized"] is None
    assert value["source_file_sha256"] == hash_bytes(raw)
    assert "broken" not in value["reason"]


@pytest.mark.parametrize("field,value", [
    ("status", None), ("status", "ERROR"), ("status", True),
    ("next_url", "https://api.massive.com/next"), ("next_url", ""), ("next_url", False),
    ("count", 0), ("count", 2), ("count", True), ("count", "1"),
    ("request_id", False), ("date", "2023-05-15")])
def test_envelope_status_paging_count_and_unknown_date_conflicts_are_refused(field, value):
    envelope = {"status": "OK", "results": fixture_row(), field: value}
    result = validate_massive_response(capture(raw=canonical_json(envelope).encode()))
    assert result["status"] == "malformed"
    assert result["normalized"] is None


def test_missing_status_is_not_success():
    result = validate_massive_response(capture(raw=canonical_json({"results": fixture_row()}).encode()))
    assert result["status"] == "malformed"
    assert result["reason"] == "missing_or_non_OK_status"


@pytest.mark.parametrize("envelope", [{"status": "OK"}, {"status": "OK", "count": 0},
                                     {"status": "OK", "results": None, "count": 0}])
def test_missing_results_retained_not_filled_from_another_date(envelope):
    result = validate_massive_response(capture(raw=canonical_json(envelope).encode()))
    assert result["status"] == "missing"
    assert result["normalized"] is None


def test_array_result_is_ambiguous_not_first_row_selected():
    rows = [fixture_row(), fixture_row()]
    result = validate_massive_response(capture(raw=canonical_json({"status": "OK", "results": rows}).encode()))
    assert result["status"] == "ambiguous"
    assert result["normalized"] is None


def test_equal_identifier_fields_are_conservative_ambiguity_not_cast_or_provider_invalidity():
    row = fixture_row()
    row["share_class_figi"] = row["composite_figi"]
    result = validate_massive_response(capture(row=row))
    assert result["status"] == "ambiguous"
    assert result["reason"] == "equal_identifier_fields_conservative_relation_refusal"
    assert result["normalized"]["composite_figi"] == result["normalized"]["share_class_figi"]
    assert result["normalized"]["same_class_denominator_admitted"] is False


@pytest.mark.parametrize("field,value", [("ticker", "FB"), ("active", 1), ("market", "otc"),
                                        ("locale", "global"), ("composite_figi", "forged"),
                                        ("share_class_figi", " BBG000000002"), ("cik", 1),
                                        ("cik", "00000000001"), ("list_date", "20230101"),
                                        ("delisted_utc", "2023-01-01"), ("type", "CS\n")])
def test_malformed_class_fields_keep_source_receipt(field, value):
    row = fixture_row()
    row[field] = value
    result = validate_massive_response(capture(row=row))
    assert result["status"] == "malformed"
    assert result["normalized"] is None
    assert result["source_file_sha256"] is not None


def test_404_without_observed_error_body_does_not_invent_provider_empty_body():
    result = validate_massive_response(capture(raw=b"", http_status=404, body_observed=False))
    assert result["status"] == "missing"
    assert result["reason"] == "HTTP404_body_unobserved"
    assert result["source_file_sha256"] is None
    assert result["placeholder_byte_sha256"] == hash_bytes(b"")
    assert result["body_observed"] is False


@pytest.mark.parametrize("status", [201, 401, 403, 404, 429, 500, 599])
def test_non200_never_promotes_OK_body(status):
    result = validate_massive_response(capture(http_status=status))
    assert result["status"] == ("missing" if status == 404 else "refused")
    assert result["normalized"] is None
    assert result["source_file_sha256"] is not None


def test_empty_observed_200_body_and_unexpected_type_are_explicit_refusals():
    assert validate_massive_response(capture(raw=b""))["reason"] == "observed_empty_body"
    assert validate_massive_response(capture(content_type="text/plain"))["reason"] == "unexpected_JSON_content_type"
    assert validate_massive_response(capture(content_type="application/json; charset=utf-8"))["status"] == "present"


@pytest.mark.parametrize("kwargs", [{"raw_sha256": "0" * 64}, {"received_at": "2026-10-13"},
                                   {"http_status": True}, {"http_status": 600},
                                   {"body_observed": 0}, {"body_observed": False},
                                   {"content_type": "application/json\n"}])
def test_capture_refuses_wrong_hash_clock_status_or_observation_binding(kwargs):
    with pytest.raises(MassiveClassDenominatorError):
        capture(**kwargs)


def test_wrong_request_id_date_source_descriptor_and_raw_mutation_refused():
    source = capture()
    for replacement in ("unknown", REQUEST_IDS[1]):
        with pytest.raises(MassiveClassDenominatorError):
            CapturedMassiveClassResponse(replacement, source.request_sha256, source.raw,
                                        RECEIVED, source.raw_sha256)
    descriptor = massive_request(FIRST)
    for key, value in (("url", "https://other.invalid/v3/reference/tickers/AAPL"),
                       ("params", {"date": "2023-02-28"})):
        wrong = dict(descriptor)
        wrong[key] = value
        with pytest.raises(MassiveClassDenominatorError, match="request_binding"):
            CapturedMassiveClassResponse(FIRST, hash_payload(wrong), source.raw, RECEIVED, source.raw_sha256)
    object.__setattr__(source, "raw", source.raw + b" ")
    with pytest.raises(MassiveClassDenominatorError, match="capture_byte_hash"):
        validate_massive_response(source)


def test_maximum_response_and_mutable_bytes_refused():
    raw = b"x" * (MAXIMUM_RESPONSE_BYTES + 1)
    with pytest.raises(MassiveClassDenominatorError, match="bounded_immutable"):
        capture(raw=raw)
    with pytest.raises(MassiveClassDenominatorError, match="bounded_immutable"):
        CapturedMassiveClassResponse(FIRST, request_sha256(FIRST), bytearray(b"{}"), RECEIVED, hash_bytes(b"{}"))


def test_all_thirty_receipts_preserved_with_immutable_detached_stored_report():
    sources = all_captures()
    qualified = qualify_massive_class_denominator(sources, retrieved_at=RETRIEVED)
    payload = qualified.to_payload()
    assert len(payload["responses"]) == 30
    assert tuple(row["request_id"] for row in payload["responses"]) == REQUEST_IDS
    digest = payload.pop("report_sha256")
    assert hash_payload(payload) == digest == qualified.sha256
    assert canonical_json(qualified.to_payload()).encode() == qualified.to_bytes()
    assert qualified.to_bytes().endswith(b"}")
    payload["authority"]["same_class_denominator_admitted"] = True
    payload["responses"][0]["normalized"]["share_class_shares_outstanding"]["numerator"] = 999999
    assert qualified.to_payload()["authority"]["same_class_denominator_admitted"] is False
    assert qualified.to_payload()["responses"][0]["normalized"]["share_class_shares_outstanding"]["numerator"] == 123
    # The input object is snapshotted; low-level caller mutation is not a retained alias.
    object.__setattr__(sources[0], "raw", b"arbitrary mutation")
    assert qualified.sha256 == digest
    with pytest.raises(dataclasses.FrozenInstanceError):
        qualified._report_bytes = b"wrong"


@pytest.mark.parametrize("field,value", [("_report_bytes", b"{}"), ("_report_sha256", "0" * 64),
                                        ("_capture_identity", "0" * 64), ("_retrieved_at", RECEIVED)])
def test_low_level_sealed_report_tampering_detected(field, value):
    qualified = qualify_massive_class_denominator(all_captures(), retrieved_at=RETRIEVED)
    object.__setattr__(qualified, field, value)
    with pytest.raises(MassiveClassDenominatorError, match="sealed_qualification"):
        qualified.to_payload()


def test_low_level_stored_capture_mutation_is_checked():
    qualified = qualify_massive_class_denominator(all_captures(), retrieved_at=RETRIEVED)
    object.__setattr__(qualified._captures[0], "received_at", "2026-10-13T20:59:00Z")
    with pytest.raises(MassiveClassDenominatorError, match="sealed_qualification"):
        qualified.to_payload()


@pytest.mark.parametrize("mode", ["incomplete", "list", "reordered", "protocol", "future_clock", "reversed_clock"])
def test_incomplete_inventory_wrong_protocol_and_chronology_refused(mode):
    sources = all_captures()
    kwargs = {"retrieved_at": RETRIEVED}
    if mode == "incomplete":
        sources = sources[:-1]
    elif mode == "list":
        sources = list(sources)
    elif mode == "reordered":
        sources = (sources[1], sources[0]) + sources[2:]
    elif mode == "protocol":
        kwargs["expected_protocol_sha256"] = "0" * 64
    elif mode == "future_clock":
        sources = sources[:-1] + (capture(REQUEST_IDS[-1], received_at="2026-10-13T21:02:00Z"),)
    else:
        sources = sources[:-1] + (capture(REQUEST_IDS[-1], received_at="2026-10-13T20:59:00Z"),)
    with pytest.raises(MassiveClassDenominatorError):
        qualify_massive_class_denominator(sources, **kwargs)


def test_qualification_direct_constructor_and_uninitialized_objects_refused():
    with pytest.raises(MassiveClassDenominatorError, match="bound_factory"):
        MassiveClassDenominatorQualification()
    uninitialized = object.__new__(MassiveClassDenominatorQualification)
    with pytest.raises(MassiveClassDenominatorError, match="uninitialized"):
        uninitialized.to_payload()


def test_numeric_string_and_number_bytes_have_distinct_capture_record_identity():
    row = fixture_row()
    first = capture(row=row)
    row["share_class_shares_outstanding"] = "123"
    second = capture(row=row)
    assert validate_massive_response(first)["source_file_sha256"] != validate_massive_response(second)["source_file_sha256"]
    assert validate_massive_response(first)["status"] == "present"
    assert validate_massive_response(second)["status"] == "malformed"


def test_report_retains_all_404_missing_malformed_ambiguous_results_without_cross_date_fill():
    sources = list(all_captures())
    sources[0] = capture(REQUEST_IDS[0], raw=b"", http_status=404, body_observed=False)
    sources[1] = capture(REQUEST_IDS[1], raw=b'{"status":"OK"}')
    sources[2] = capture(REQUEST_IDS[2], raw=b'not JSON')
    sources[3] = capture(REQUEST_IDS[3], raw=b'{"status":"OK","results":[]}')
    report = qualify_massive_class_denominator(tuple(sources), retrieved_at=RETRIEVED).to_payload()
    assert [row["status"] for row in report["responses"][:4]] == ["missing", "missing", "malformed", "ambiguous"]
    assert all(row["normalized"] is None for row in report["responses"][:4])
    assert len(report["responses"]) == 30
    assert report["authority"]["actual_outcome_looks"] == 0
    assert report["authority"]["qc_attempts"] == 0
