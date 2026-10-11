"""Fabricated source-only responses; never market/economic outcome evidence."""
from __future__ import annotations

import copy
import dataclasses
from decimal import localcontext

import pytest

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.massive_action_supplement import (
    CapturedMassiveActionResponse, MassiveActionSupplementError,
    MassiveActionSupplementQualification, MAXIMUM_REQUESTS, MAXIMUM_RESPONSE_BYTES,
    PROTOCOL_SHA256, REFERENCE_DATES, REQUEST_IDS, SYMBOLS,
    massive_request, qualify_massive_action_supplement, request_sha256,
    supplement_protocol, validate_massive_response,
)


RETRIEVED_AT = "2026-10-11T22:00:00Z"
FIRST_REFERENCE = REQUEST_IDS[0]


def capture(request_id, rows=(), *, raw=None, count=True, **kwargs):
    value = {"status": "OK", "results": list(rows), "request_id": "fabricated-request"}
    if count:
        value["count"] = len(rows)
    blob = canonical_json(value).encode() if raw is None else raw
    return CapturedMassiveActionResponse(request_id, request_sha256(request_id), blob, **kwargs)


def empty_captures():
    return tuple(capture(item) for item in REQUEST_IDS)


def reference_row():
    return {"ticker": "AAPL", "active": True, "composite_figi": "BBG000000001",
            "share_class_figi": "BBG000000002", "cik": "0000000001",
            "primary_exchange": "XNAS", "type": "CS", "locale": "us",
            "market": "stocks", "currency_name": "usd", "name": "Fabricated Company",
            "last_updated_utc": "2026-10-10T00:00:00Z"}


def dividend_row():
    return {"ticker": "AAPL", "id": "fabricated-dividend", "ex_dividend_date": "2023-03-01",
            "cash_amount": 2, "currency": "USD", "pay_date": "2023-03-15",
            "declaration_date": "2023-02-01", "record_date": "2023-03-02",
            "distribution_type": "recurring", "frequency": 4}


def split_row():
    return {"ticker": "BRK.B", "id": "fabricated-split", "execution_date": "2023-03-01",
            "split_from": 3, "split_to": 2, "adjustment_type": "reverse_split"}


def test_protocol_exact_pinned_private_zero_authority_and_detached():
    protocol = supplement_protocol()
    assert hash_payload(protocol) == PROTOCOL_SHA256 == "3ab6565797ab1bed34e30dda310040aebdab643f457d9384283eacaee0af321f"
    assert MAXIMUM_REQUESTS == 62 == len(REQUEST_IDS) == len(set(REQUEST_IDS))
    assert protocol["candidate_symbols"] == list(SYMBOLS)
    assert protocol["reference_dates"] == list(REFERENCE_DATES)
    assert protocol["maximum_requests"] == 62
    assert protocol["automatic_retries"] == 0
    assert protocol["maximum_pages_per_request"] == 1
    assert protocol["authority"]["ready_for_empirical_backtest"] is False
    protocol["requests"][0]["params"]["active"] = "false"
    protocol["authority"]["qc_authorized"] = True
    assert hash_payload(supplement_protocol()) == PROTOCOL_SHA256


@pytest.mark.parametrize("request_id", REQUEST_IDS)
def test_all_sixty_two_descriptors_are_detached_fixed_routes_and_hash_bound(request_id):
    descriptor = massive_request(request_id)
    assert request_sha256(request_id) == hash_payload(descriptor)
    assert descriptor["method"] == "GET"
    assert descriptor["url"] in {"https://api.massive.com/v3/reference/tickers", "https://api.massive.com/stocks/v1/dividends", "https://api.massive.com/stocks/v1/splits"}
    assert not any("key" in name.lower() for name in descriptor["params"])
    descriptor["params"]["secret"] = "fabricated"
    assert "secret" not in massive_request(request_id)["params"]


def test_exact_scope_no_default_active_aliasing_or_cumulative_adjustment():
    first = massive_request(REQUEST_IDS[0])["params"]
    second = massive_request(REQUEST_IDS[1])["params"]
    assert first["ticker"] == second["ticker"] == "AAPL"
    assert first["date"] == second["date"] == "2022-10-14"
    assert (first["active"], second["active"]) == ("true", "false")
    for request_id, date_field in (("rows-dividends", "ex_dividend_date"), ("rows-splits", "execution_date")):
        params = massive_request(request_id)["params"]
        assert params["ticker.any_of"] == ",".join(SYMBOLS)
        assert params[date_field + ".gte"] == "2022-01-01"
        assert params[date_field + ".lte"] == "2023-12-31"
        assert params["sort"] == date_field + ".asc"
        assert params["limit"] == "5000"
        assert "adjustment_type" not in params


def test_identity_keeps_class_and_composite_figi_distinct_and_no_market_fields():
    row = reference_row()
    row.update({"market_cap": 1234, "share_class_shares_outstanding": 999, "phone_number": "fabricated private text"})
    page = validate_massive_response(capture(FIRST_REFERENCE, [row]))
    normalized = page["rows"][0]["normalized"]
    assert normalized["composite_figi"] == "BBG000000001"
    assert normalized["share_class_figi"] == "BBG000000002"
    assert normalized["query_date"] == "2022-10-14"
    assert normalized["effective_historical_mapping_admitted"] is False
    assert normalized["same_share_class_denominator_admitted"] is False
    assert normalized["historical_availability_verified"] is False
    assert "market_cap" not in normalized and "share_class_shares_outstanding" not in normalized
    assert "phone_number" not in normalized


def test_exact_dividend_and_split_amounts_not_adjusted_or_zero_inferred():
    raw = b'{"status":"OK","results":[{"ticker":"AAPL","id":"fixture","ex_dividend_date":"2023-03-01","cash_amount":0.123456789,"split_adjusted_cash_amount":77,"currency":"USD","pay_date":"2023-03-15"}]}'
    with localcontext() as context:
        context.prec = 2
        normalized = validate_massive_response(capture("rows-dividends", raw=raw))["rows"][0]["normalized"]
    assert normalized["cash_amount"] == {"numerator": 123456789, "denominator": 1000000000}
    assert "split_adjusted_cash_amount" not in normalized
    assert normalized["payment_precision"] == "date_only" and normalized["payment_timestamp"] is None
    assert normalized["payment_cash_settlement_verified"] is False
    normalized = validate_massive_response(capture("rows-splits", [split_row()]))["rows"][0]["normalized"]
    assert normalized["split_ratio"] == {"numerator": 2, "denominator": 3}
    assert normalized["terminal_economics_admitted"] is False


def test_record_provenance_binds_lexical_source_bytes_and_row_position():
    numeric = b'{"status":"OK","results":[{"ticker":"AAPL","ex_dividend_date":"2023-03-01","cash_amount":0.25}]}'
    text = numeric.replace(b':0.25', b':"0.25"')
    first = validate_massive_response(capture("rows-dividends", raw=numeric))
    second = validate_massive_response(capture("rows-dividends", raw=text))
    assert first["source_file_sha256"] != second["source_file_sha256"]
    assert first["rows"][0]["raw_record_sha256"] != second["refusals"][0]["raw_record_sha256"]
    repeated = validate_massive_response(capture("rows-dividends", [dividend_row(), dividend_row()]))
    assert repeated["refusals"][0]["raw_record_sha256"] != repeated["refusals"][1]["raw_record_sha256"]


@pytest.mark.parametrize("kind", ["forward_split", "reverse_split", "stock_dividend"])
def test_all_three_share_change_classes_retained(kind):
    row = split_row()
    row["adjustment_type"] = kind
    row["historical_adjustment_factor"] = 500
    normalized = validate_massive_response(capture("rows-splits", [row]))["rows"][0]["normalized"]
    assert normalized["adjustment_type"] == kind
    assert normalized["split_ratio"] == {"numerator": 2, "denominator": 3}


@pytest.mark.parametrize("request_id,row,missing", [(FIRST_REFERENCE, reference_row(), "share_class_figi"), ("rows-dividends", dividend_row(), "pay_date"), ("rows-dividends", dividend_row(), "currency"), ("rows-dividends", dividend_row(), "cash_amount"), ("rows-splits", split_row(), "split_to")])
def test_missing_optional_documented_fields_are_explicit_incomplete_not_zero(request_id, row, missing):
    row.pop(missing)
    page = validate_massive_response(capture(request_id, [row]))
    normalized = page["rows"][0]["normalized"]
    assert normalized[missing] is None
    assert missing in normalized["missing_fields"]
    assert page["requested_symbol_cells"][0 if row["ticker"] == "AAPL" else 2]["status"] == "incomplete"


def test_special_due_bill_payment_order_is_named_not_rewritten_or_declared_invalid():
    row = dividend_row()
    row["pay_date"] = "2023-02-27"
    normalized = validate_massive_response(capture("rows-dividends", [row]))["rows"][0]["normalized"]
    assert normalized["pay_date"] == "2023-02-27"
    assert normalized["due_bill_or_nonstandard_payment_order_requires_qualification"] is True


@pytest.mark.parametrize("request_id,row,change", [(FIRST_REFERENCE, reference_row(), {"ticker": "META"}), (FIRST_REFERENCE, reference_row(), {"active": False}), (FIRST_REFERENCE, reference_row(), {"active": 1}), (FIRST_REFERENCE, reference_row(), {"market": "otc"}), (FIRST_REFERENCE, reference_row(), {"composite_figi": "fabricated-secret"}), (FIRST_REFERENCE, reference_row(), {"last_updated_utc": "2023-01-01"}), ("rows-dividends", dividend_row(), {"ticker": "AAPL1"}), ("rows-dividends", dividend_row(), {"ex_dividend_date": "2024-01-01"}), ("rows-dividends", dividend_row(), {"cash_amount": -1}), ("rows-dividends", dividend_row(), {"cash_amount": "2"}), ("rows-dividends", dividend_row(), {"cash_amount": True}), ("rows-dividends", dividend_row(), {"pay_date": "2023-03-15T00:00:00Z"}), ("rows-dividends", dividend_row(), {"currency": "usd"}), ("rows-dividends", dividend_row(), {"frequency": True}), ("rows-splits", split_row(), {"split_from": 0}), ("rows-splits", split_row(), {"split_to": -1}), ("rows-splits", split_row(), {"split_to": "2"}), ("rows-splits", split_row(), {"adjustment_type": "merger"})])
def test_invalid_rows_are_named_retained_refusals_without_external_text(request_id, row, change):
    row.update(change)
    page = validate_massive_response(capture(request_id, [row]))
    assert page["rows"] == []
    assert len(page["refusals"]) == 1
    assert page["refusals"][0]["status"] == "malformed"
    assert "fabricated-secret" not in canonical_json(page)
    assert page["raw_row_count"] == 1


@pytest.mark.parametrize("request_id,row,bad_field,bad_value", [(FIRST_REFERENCE, reference_row(), "active", "invalid"), ("rows-dividends", dividend_row(), "cash_amount", "invalid"), ("rows-splits", split_row(), "split_from", 0)])
def test_duplicates_quarantine_good_row_and_malformed_peer_before_values(request_id, row, bad_field, bad_value):
    malformed = copy.deepcopy(row)
    malformed[bad_field] = bad_value
    page = validate_massive_response(capture(request_id, [row, malformed]))
    assert page["rows"] == []
    assert [entry["status"] for entry in page["refusals"]] == ["duplicate", "duplicate"]
    assert page["requested_symbol_cells"][0 if row["ticker"] == "AAPL" else 2]["status"] == "refused"


def test_missing_ids_conservative_same_date_duplicates_not_silently_selected():
    first = dividend_row()
    first.pop("id")
    second = copy.deepcopy(first)
    second["cash_amount"] = 4
    page = validate_massive_response(capture("rows-dividends", [first, second]))
    assert len(page["refusals"]) == 2 and not page["rows"]


@pytest.mark.parametrize("raw", [b'{"status":"OK","status":"OK","results":[]}', b'{"status":"OK","results":[{"ticker":"AAPL","cash_amount":NaN}]}', b'{"status":"OK","results":[{"ticker":"AAPL","cash_amount":Infinity}]}', b'\xff', b'{"status":"OK","results":[{"x":"\\ud800"}]}', b'not-json', b'[]'])
def test_strict_json_and_envelope_refusals_are_safe(raw):
    with pytest.raises(MassiveActionSupplementError, match="REFUSED:"):
        validate_massive_response(capture("rows-dividends", raw=raw))


@pytest.mark.parametrize("change", [{"status": "NOT_AUTHORIZED"}, {"results": {}}, {"count": True}, {"count": 1}, {"next_url": "https://evil.example/fabricated-secret"}, {"next_url": False}, {"request_id": " fabricated "}, {"request_id": True}, {"request_id": -1}, {"unknown": 1}])
def test_bad_envelopes_never_follow_urls_or_hide_incomplete_pages(change):
    value = {"status": "OK", "results": [], "count": 0}
    value.update(change)
    with pytest.raises(MassiveActionSupplementError) as exc:
        validate_massive_response(capture("rows-dividends", raw=canonical_json(value).encode()))
    assert "fabricated-secret" not in str(exc.value)


@pytest.mark.parametrize("next_url", [None, ""])
def test_terminal_page_empty_optional_next_url_and_optional_count(next_url):
    value = {"status": "OK", "results": [], "next_url": next_url}
    assert validate_massive_response(capture("rows-dividends", raw=canonical_json(value).encode()))["page_complete"] is True


@pytest.mark.parametrize("request_id", ["rows-dividends", "rows-splits", FIRST_REFERENCE])
def test_documented_numeric_request_id_discarded_and_omitted_zero_results_explicit(request_id):
    value = {"status": "OK", "count": 0, "request_id": 1}
    page = validate_massive_response(capture(request_id, raw=canonical_json(value).encode()))
    assert page["raw_results_absent"] is True
    assert page["raw_row_count"] == 0
    assert page["rows"] == []


@pytest.mark.parametrize("count", [None, True, -1, 1, "0"])
def test_omitted_results_never_inferred_from_missing_or_invalid_count(count):
    value = {"status": "OK"}
    if count is not None:
        value["count"] = count
    with pytest.raises(MassiveActionSupplementError, match="missing_results_without_explicit_zero_count"):
        validate_massive_response(capture("rows-dividends", raw=canonical_json(value).encode()))


@pytest.mark.parametrize("kwargs", [{"http_status": True}, {"http_status": 204}, {"content_type": "text/html"}, {"content_type": "application/json\nsecret"}])
def test_capture_transport_contracts(kwargs):
    with pytest.raises(MassiveActionSupplementError):
        capture("rows-dividends", **kwargs)


def test_capture_requires_exact_immutable_bytes_size_binding_and_type():
    with pytest.raises(MassiveActionSupplementError):
        CapturedMassiveActionResponse("rows-dividends", "0" * 64, b'{}')
    for raw in (b"", bytearray(b"{}"), "{}", b"x" * (MAXIMUM_RESPONSE_BYTES + 1)):
        with pytest.raises(MassiveActionSupplementError):
            capture("rows-dividends", raw=raw)
    with pytest.raises(MassiveActionSupplementError):
        validate_massive_response(object())
    with pytest.raises(dataclasses.FrozenInstanceError):
        capture("rows-dividends").http_status = 201


def test_report_rebuild_detach_full_ordered_inventory_and_zero_authority():
    report = qualify_massive_action_supplement(empty_captures(), retrieved_at=RETRIEVED_AT)
    payload = report.to_payload()
    assert len(payload["tables"]) == 62
    assert [item["request_id"] for item in payload["tables"]] == list(REQUEST_IDS)
    assert payload["publication_scope"] == "private_only_source_qualification"
    assert payload["authority"]["source_only"] is True
    assert all(value is False for name, value in payload["authority"].items() if name not in {"source_only", "actual_outcome_looks", "allocated_alpha", "qc_attempts"})
    digest = payload.pop("report_sha256")
    assert hash_payload(payload) == report.sha256 == digest
    payload["tables"].clear()
    payload["authority"]["qc_authorized"] = True
    assert len(report.to_payload()["tables"]) == 62
    assert report.to_payload()["authority"]["qc_authorized"] is False
    assert all(cell["status"] == "missing" for page in report.to_payload()["tables"] for cell in page["requested_symbol_cells"])


@pytest.mark.parametrize("bad", ["2026-10-11", "2026-10-11T22:00:00+00:00", "2026-10-11T22:00:00", True])
def test_report_requires_canonical_utc(bad):
    with pytest.raises(MassiveActionSupplementError):
        qualify_massive_action_supplement(empty_captures(), retrieved_at=bad)


def test_report_refuses_missing_reordered_mutable_subclass_or_late_modified_captures():
    values = empty_captures()
    for bad in (values[:-1], tuple(reversed(values)), list(values), (object(),) + values[1:]):
        with pytest.raises(MassiveActionSupplementError):
            qualify_massive_action_supplement(bad, retrieved_at=RETRIEVED_AT)
    report = qualify_massive_action_supplement(values, retrieved_at=RETRIEVED_AT)
    object.__setattr__(values[0], "raw", b'{"status":"OK","results":[],"count":0}')
    with pytest.raises(MassiveActionSupplementError, match="captured_identity_changed"):
        report.to_payload()
    object.__setattr__(values[0], "http_status", 204)
    with pytest.raises(MassiveActionSupplementError, match="HTTP_status_not_200"):
        report.to_payload()
    class Subclass(MassiveActionSupplementQualification):
        pass
    with pytest.raises(MassiveActionSupplementError):
        Subclass(empty_captures(), RETRIEVED_AT)


def test_expected_protocol_mismatch_and_unknown_ids_refused():
    with pytest.raises(MassiveActionSupplementError):
        qualify_massive_action_supplement(empty_captures(), retrieved_at=RETRIEVED_AT, expected_protocol_sha256="0" * 64)
    for unknown in (None, [], "https://evil.example", "rows-prices"):
        with pytest.raises(MassiveActionSupplementError):
            massive_request(unknown)
