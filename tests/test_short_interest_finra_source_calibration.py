"""Invented byte pages prove source-only calibration behavior, never an edge."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.finra_source_calibration as calibration
from research.short_interest_etf.finra_source_calibration import (
    CapturedFinraCalibrationPage,
    FinraCalibrationReport,
    FinraSourceCalibrationError,
    PROTOCOL_SHA256,
    calibrate_finra_sources,
    calibration_protocol,
    calibration_request,
)


def _rows(query: dict) -> list[dict]:
    return [{
        "symbolCode": symbol, "settlementDate": query["settlement_date"],
        "currentShortPositionQuantity": 918273645012345678,
        "previousShortPositionQuantity": 182736450123456789,
        "revisionFlag": None, "stockSplitFlag": None,
        "marketClassCode": "TOY", "issuerServicesGroupExchangeCode": "TOY",
        "issueName": "PRIVATE_FAKE_ISSUER_NAME",
    } for symbol in query["raw_symbols"]]


def _bound(query_id: str, rows: list, *, offset: int = 0, total: int | None = None,
           raw: bytes | None = None, http_status: int = 200):
    return CapturedFinraCalibrationPage(
        query_id=query_id, offset=offset, total=len(rows) if total is None else total,
        limit=100, max_limit=5000, data_version="1",
        request_sha256=hash_payload(calibration_request(query_id, offset)),
        raw=canonical_json(rows).encode() if raw is None else raw,
        http_status=http_status,
    )


def _pages(*, empty: bool = False):
    return tuple(_bound(query["query_id"], [] if empty else _rows(query)) for query in calibration_protocol()["queries"])


def _result(pages=None):
    return calibrate_finra_sources(_pages() if pages is None else pages, expected_protocol_sha256=PROTOCOL_SHA256).to_payload()


def _rehash(payload: dict) -> FinraCalibrationReport:
    payload["report_sha256"] = hash_payload({key: value for key, value in payload.items() if key != "report_sha256"})
    return FinraCalibrationReport(canonical_json(payload))


def test_protocol_freezes_exact18historical_and5independent_formats():
    protocol = calibration_protocol()
    assert hash_payload(protocol) == PROTOCOL_SHA256
    assert protocol["historical_cells"] == 18 and protocol["format_cells"] == 5
    assert [query["query_id"] for query in protocol["queries"]] == [
        "hist-2022-10-14", "hist-2022-11-15", "hist-2023-02-28", "hist-2023-03-15",
        "hist-2023-04-14", "hist-2023-05-15", "format-2026-06-30",
    ]
    assert protocol["queries"][0]["raw_symbols"] == ["FRC", "SIVB", "TWTR"]
    assert protocol["queries"][-1]["raw_symbols"] == ["BRK.B", "BRK/B", "BRK-B", "BRKB", "BRK B"]
    assert protocol["maximum_source_posts"] == 8 and protocol["maximum_pages_per_query"] == 2
    assert protocol["source_retries"] == 0
    protocol["queries"][0]["raw_symbols"].clear()
    assert calibration_protocol()["queries"][0]["raw_symbols"] == ["FRC", "SIVB", "TWTR"]


def test_request_is_detached_exact_query_bound_and_source_only():
    request = calibration_request("format-2026-06-30", 3)
    assert request["compareFilters"] == [{"fieldName": "settlementDate", "fieldValue": "2026-06-30", "compareType": "equal"}]
    assert request["domainFilters"][0]["values"] == ["BRK.B", "BRK/B", "BRK-B", "BRKB", "BRK B"]
    assert request["sortFields"] == ["symbolCode"] and request["async"] is False
    assert request["limit"] == 100 and request["offset"] == 3
    assert hash_payload(request) == hash_bytes(canonical_json(request).encode())
    request["fields"].clear()
    assert len(calibration_request("format-2026-06-30", 3)["fields"]) == 9


def test_all_cells_present_but_nonadjacent_quantities_are_never_compared_or_reported():
    report = _result()
    assert report["totals"] == {"expected_cells": 23, "historical_cells": 18, "format_cells": 5,
                                 "raw_rows": 23, "valid_cells": 23, "refused_rows": 0, "unidentifiable_rows": 0}
    assert report["cell_status_counts"]["historical"]["valid"] == 18
    assert report["cell_status_counts"]["format"]["valid"] == 5
    assert report["query_capture_complete"] is True and report["all_cells_present_valid"] is True
    assert report["previous_field_status_counts"] == {"unknown": 0, "present": 23}
    text = canonical_json(report)
    for forbidden in ("currentShortPositionQuantity", "previousShortPositionQuantity", "issueName",
                      "PRIVATE_FAKE_ISSUER_NAME", "918273645012345678", "182736450123456789", "continuity"):
        assert forbidden not in text
    assert report["authority"]["latest_stored_snapshot_only"] is True
    for key, value in report["authority"].items():
        if key != "latest_stored_snapshot_only":
            assert value is False or type(value) is int and value == 0


def test_complete_empty_queries_keep23missing_cells_without_zero_or_alias_inference():
    report = _result(_pages(empty=True))
    assert report["query_capture_complete"] is True
    assert report["all_cells_present_valid"] is False
    assert report["cell_status_counts"]["historical"]["missing"] == 18
    assert report["cell_status_counts"]["format"]["missing"] == 5
    assert all(cell["raw_row_count"] == 0 for cell in report["cells"])
    assert report["authority"]["raw_symbol_alias_selected"] is False


def test_format_spellings_are_never_aliased_when_only_space_form_is_returned():
    pages = list(_pages())
    query = calibration_protocol()["queries"][-1]
    pages[-1] = _bound(query["query_id"], [_rows(query)[-1]])
    report = _result(tuple(pages))
    cells = report["cells"][-5:]
    assert [cell["status"] for cell in cells] == ["missing"] * 4 + ["valid"]
    assert cells[-1]["raw_symbol"] == "BRK B"
    assert report["authority"]["raw_symbol_alias_selected"] is False


def test_zero_current_and_previous_are_valid_but_null_previous_is_unknown():
    pages = list(_pages())
    query = calibration_protocol()["queries"][0]
    rows = _rows(query)
    rows[0].update(currentShortPositionQuantity=0, previousShortPositionQuantity=0)
    rows[1]["previousShortPositionQuantity"] = None
    pages[0] = _bound(query["query_id"], rows)
    report = _result(tuple(pages))
    assert report["totals"]["valid_cells"] == 23
    assert report["previous_field_status_counts"] == {"unknown": 1, "present": 22}


@pytest.mark.parametrize("changes,reason", [
    ({"currentShortPositionQuantity": None}, "missing_current_quantity"),
    ({"currentShortPositionQuantity": True}, "invalid_quantity"),
    ({"currentShortPositionQuantity": "0"}, "invalid_quantity"),
    ({"unknown": True}, "missing_or_unknown_fields"),
    ({"stockSplitFlag": "R"}, "invalid_split_flag"),
])
def test_malformed_cell_is_explicit_and_keeps_frozen_denominator(changes, reason):
    pages = list(_pages())
    query = calibration_protocol()["queries"][0]
    rows = _rows(query)
    rows[0].update(changes)
    pages[0] = _bound(query["query_id"], rows)
    report = _result(tuple(pages))
    assert report["totals"]["valid_cells"] == 22
    assert report["cell_status_counts"]["historical"]["malformed"] == 1
    assert report["refusal_reason_counts"][reason] == 1
    assert len(report["cells"]) == 23


@pytest.mark.parametrize("across_pages", [False, True])
@pytest.mark.parametrize("malformed_first", [False, True])
def test_raw_duplicate_quarantines_valid_twin_before_schema_validation(across_pages, malformed_first):
    pages = list(_pages())
    query = calibration_protocol()["queries"][0]
    rows = _rows(query)
    bad = {**rows[0], "currentShortPositionQuantity": None}
    pair = [bad, rows[0]] if malformed_first else [rows[0], bad]
    replacements = ([_bound(query["query_id"], [pair[0], *rows[1:]], total=4),
                     _bound(query["query_id"], [pair[1]], offset=3, total=4)] if across_pages
                    else [_bound(query["query_id"], [*pair, *rows[1:]])])
    report = _result(tuple([*replacements, *pages[1:]]))
    assert report["cell_status_counts"]["historical"]["duplicate"] == 1
    assert report["totals"]["valid_cells"] == 22 and report["totals"]["refused_rows"] == 2
    assert report["refusal_reason_counts"]["duplicate"] == 2


def test_different_market_classes_remain_ambiguous_even_with_equal_quantities():
    pages = list(_pages())
    query = calibration_protocol()["queries"][0]
    rows = _rows(query)
    pages[0] = _bound(query["query_id"], [*rows, {**rows[0], "marketClassCode": "OTHER"}])
    report = _result(tuple(pages))
    assert report["cell_status_counts"]["historical"]["ambiguous_market_class"] == 1
    assert report["totals"]["valid_cells"] == 22
    assert report["market_class_counts"] == {"TOY": 22}


def test_unidentifiable_extra_row_prevents_complete_valid_sample():
    pages = list(_pages())
    query = calibration_protocol()["queries"][0]
    pages[0] = _bound(query["query_id"], [*_rows(query), 42])
    report = _result(tuple(pages))
    assert report["totals"]["unidentifiable_rows"] == 1
    assert report["totals"]["valid_cells"] == 23
    assert report["all_cells_present_valid"] is False


@pytest.mark.parametrize("changes", [{"symbolCode": "AAPL"}, {"settlementDate": "2022-11-15"}])
def test_identifiable_out_of_query_row_refuses_instead_of_appearing_valid(changes):
    pages = list(_pages())
    query = calibration_protocol()["queries"][0]
    rows = _rows(query)
    rows[0].update(changes)
    pages[0] = _bound(query["query_id"], rows)
    with pytest.raises(FinraSourceCalibrationError, match="bound query"):
        _result(tuple(pages))


@pytest.mark.parametrize("raw", [b'[{"x":1,"x":2}]', b'[NaN]', b'[Infinity]', b'{"rows":[]}', b'\xff'])
def test_shared_strict_parser_rejects_duplicate_keys_nonfinite_or_wrong_page(raw):
    pages = list(_pages())
    pages[0] = replace(pages[0], raw=raw)
    with pytest.raises(FinraSourceCalibrationError):
        _result(tuple(pages))


def test_exact_integral_numeric_tokens_reuse_v1_semantics_and_typed_hashes():
    pages = list(_pages())
    query = calibration_protocol()["queries"][0]
    rows = _rows(query)
    rows[0]["currentShortPositionQuantity"] = 0
    blob = canonical_json(rows).encode().replace(b'"currentShortPositionQuantity":0', b'"currentShortPositionQuantity":0e3', 1)
    pages[0] = _bound(query["query_id"], rows, raw=blob)
    assert _result(tuple(pages))["totals"]["valid_cells"] == 23
    bad = blob.replace(b'"currentShortPositionQuantity":0e3', b'"currentShortPositionQuantity":"0e3"', 1)
    pages[0] = replace(pages[0], raw=bad)
    assert _result(tuple(pages))["totals"]["valid_cells"] == 22


def test_eighth_page_can_complete_one_query_using_exact_returned_count_offsets():
    pages = list(_pages())
    query = calibration_protocol()["queries"][0]
    rows = _rows(query)
    split = [_bound(query["query_id"], rows[:2], total=3), _bound(query["query_id"], rows[2:], offset=2, total=3)]
    report = _result(tuple([*split, *pages[1:]]))
    assert len(report["pages"]) == 8 and report["totals"]["valid_cells"] == 23
    assert report["pages"][1]["offset"] == 2


@pytest.mark.parametrize("change", ["request", "offset", "total", "max_limit", "repeated", "empty"])
def test_stale_mixed_or_nonprogressing_pagination_refuses(change):
    pages = list(_pages())
    query = calibration_protocol()["queries"][0]
    rows = _rows(query)
    first = _bound(query["query_id"], rows[:2], total=3)
    second = _bound(query["query_id"], rows[2:], offset=2, total=3)
    if change == "request":
        second = replace(second, request_sha256="f" * 64)
    elif change == "offset":
        second = _bound(query["query_id"], rows[2:], offset=1, total=3)
    elif change == "total":
        second = replace(second, total=4)
    elif change == "max_limit":
        second = replace(second, max_limit=6000)
    elif change == "repeated":
        second = replace(second, raw=first.raw, total=4)
        first = replace(first, total=4)
    else:
        second = _bound(query["query_id"], [], offset=2, total=3)
    with pytest.raises(FinraSourceCalibrationError):
        _result(tuple([first, second, *pages[1:]]))


def test_reordered_or_missing_queries_and_ninth_page_refuse():
    pages = list(_pages())
    with pytest.raises(FinraSourceCalibrationError, match="query pagination"):
        _result(tuple([pages[1], pages[0], *pages[2:]]))
    with pytest.raises(FinraSourceCalibrationError):
        _result(tuple(pages[:-1]))
    with pytest.raises(FinraSourceCalibrationError):
        _result(tuple([*pages, pages[0], pages[0]]))


@pytest.mark.parametrize("changes", [
    {"query_id": "arbitrary-query"}, {"offset": True}, {"limit": 99},
    {"max_limit": 99}, {"data_version": "2"}, {"total": 201},
    {"raw": bytearray(b"[]")}, {"raw": b" " * (1024 * 1024 + 1)},
])
def test_page_boundary_is_exact_and_bounded(changes):
    with pytest.raises(FinraSourceCalibrationError):
        replace(_pages()[0], **changes)


def test_expected_protocol_and_runtime_protocol_drift_refuse(monkeypatch):
    with pytest.raises(FinraSourceCalibrationError, match="expected calibration protocol"):
        calibrate_finra_sources(_pages(), expected_protocol_sha256="f" * 64)
    monkeypatch.setattr(calibration, "_HISTORICAL_DATES", ("2022-10-14",))
    with pytest.raises(FinraSourceCalibrationError, match="protocol hash"):
        calibration_protocol()


def test_report_revalidates_ordered_query_binding_even_after_rehash():
    payload = _result(_pages(empty=True))
    payload["pages"][0], payload["pages"][1] = payload["pages"][1], payload["pages"][0]
    for index, page in enumerate(payload["pages"]):
        page["page_index"] = index
    with pytest.raises(FinraSourceCalibrationError, match="query order"):
        _rehash(payload)


def test_report_revalidates_repeated_empty_second_page_even_after_rehash():
    payload = _result(_pages(empty=True))
    payload["pages"].insert(1, dict(payload["pages"][0]))
    for index, page in enumerate(payload["pages"]):
        page["page_index"] = index
    with pytest.raises(FinraSourceCalibrationError, match="repeated page|no progress"):
        _rehash(payload)


@pytest.mark.parametrize("field,value", [
    ("authority", {"source_admitted": True}), ("query_capture_complete", False),
    ("all_cells_present_valid", False), ("report_sha256", "f" * 64),
])
def test_report_cannot_rehash_changed_authority_or_completeness(field, value):
    payload = _result()
    payload[field] = value
    with pytest.raises(FinraSourceCalibrationError):
        if field == "report_sha256":
            FinraCalibrationReport(canonical_json(payload))
        else:
            _rehash(payload)


def test_counts_require_exact_integer_types_and_previous_field_reconciliation():
    payload = _result()
    payload["cell_status_counts"]["historical"]["missing"] = False
    with pytest.raises(FinraSourceCalibrationError, match="status counts"):
        _rehash(payload)
    payload = _result()
    payload["previous_field_status_counts"] = {"present": 22, "unknown": 1}
    with pytest.raises(FinraSourceCalibrationError, match="previous-field counts"):
        _rehash(payload)


def test_report_is_detached_immutable_and_captured_identity_bound():
    report = calibrate_finra_sources(_pages(), expected_protocol_sha256=PROTOCOL_SHA256)
    baseline = report.to_payload()
    mutation = report.to_payload()
    mutation["cells"].clear()
    assert report.to_payload() == baseline
    with pytest.raises(FrozenInstanceError):
        report.payload_json = "{}"
    changed = _result(_pages(empty=True))
    object.__setattr__(report, "payload_json", canonical_json(changed))
    with pytest.raises(FinraSourceCalibrationError, match="captured report"):
        report.to_payload()


def test_noncanonical_or_subclassed_report_cannot_substitute():
    payload = _result()
    with pytest.raises(FinraSourceCalibrationError, match="canonical"):
        FinraCalibrationReport(json.dumps(payload))
    class Subclass(FinraCalibrationReport):
        pass
    with pytest.raises(FinraSourceCalibrationError, match="exact canonical"):
        Subclass(canonical_json(payload))


def test_204_requires_header_proven_zero_rows_and_preserves_actual_empty_digest(monkeypatch):
    pages = list(_pages())
    pages[5] = _bound(pages[5].query_id, [], raw=b"", http_status=204)
    original_json = calibration._v1._json
    def no_empty_json(blob):
        assert blob != b"", "204 bytes must not be parsed or replaced with invented JSON"
        return original_json(blob)
    monkeypatch.setattr(calibration._v1, "_json", no_empty_json)
    report = _result(tuple(pages))
    descriptor = report["pages"][5]
    assert descriptor["http_status"] == 204
    assert descriptor["row_count"] == descriptor["total"] == descriptor["offset"] == 0
    assert descriptor["raw_sha256"] == hash_bytes(b"")
    assert descriptor["raw_sha256"] != hash_bytes(b"[]")
    assert report["cell_status_counts"]["historical"]["missing"] == 3
    assert report["totals"]["valid_cells"] == 20
    assert report["query_capture_complete"] is True
    assert report["all_cells_present_valid"] is False
    assert report["authority"]["source_admitted"] is False


def test_all_zero_proven204_queries_keep_the_full_missing_denominator():
    pages = tuple(_bound(query["query_id"], [], raw=b"", http_status=204)
                  for query in calibration_protocol()["queries"])
    report = _result(pages)
    assert report["totals"]["raw_rows"] == 0
    assert report["cell_status_counts"]["historical"]["missing"] == 18
    assert report["cell_status_counts"]["format"]["missing"] == 5
    assert all(page["http_status"] == 204 for page in report["pages"])


@pytest.mark.parametrize("changes", [
    {"raw": b"[]"}, {"raw": b"\n"}, {"raw": b"[{\"x\":1}]"},
    {"total": 1}, {"offset": 1}, {"total": None}, {"offset": None},
    {"total": False}, {"offset": False}, {"limit": 99}, {"max_limit": 99},
    {"data_version": "2"}, {"data_version": None},
])
def test_204_nonempty_stale_or_unproven_header_combination_refuses(changes):
    page = _bound("hist-2023-05-15", [], raw=b"", http_status=204)
    with pytest.raises(FinraSourceCalibrationError):
        replace(page, **changes)


@pytest.mark.parametrize("status", [201, 202, 206, 400, 404, 500, True, False, "204", None])
def test_other_http_status_or_noninteger_status_is_never_zero_record_proof(status):
    with pytest.raises(FinraSourceCalibrationError, match="HTTP status"):
        replace(_pages()[0], http_status=status)


def test_200_empty_body_still_requires_actual_JSON_array():
    pages = list(_pages())
    pages[5] = _bound(pages[5].query_id, [], raw=b"", http_status=200)
    with pytest.raises(FinraSourceCalibrationError):
        _result(tuple(pages))


@pytest.mark.parametrize("changes", [
    {"raw_sha256": hash_bytes(b"[]")}, {"raw_sha256": "f" * 64},
    {"http_status": 200}, {"http_status": True}, {"http_status": "204"},
    {"offset": 1}, {"total": 1}, {"row_count": 1}, {"limit": 99}, {"max_limit": 99},
])
def test_report_revalidates204_proof_after_rehash(changes):
    pages = list(_pages())
    pages[5] = _bound(pages[5].query_id, [], raw=b"", http_status=204)
    payload = _result(tuple(pages))
    payload["pages"][5].update(changes)
    with pytest.raises(FinraSourceCalibrationError):
        _rehash(payload)


def test_report_cannot_omit_http_status_from_zero_record_proof():
    payload = _result(_pages(empty=True))
    payload["pages"][5].pop("http_status")
    with pytest.raises(FinraSourceCalibrationError, match="page schema"):
        _rehash(payload)


def test_transport_erratum_is_explicit_but_scientific_request_and_cells_are_unchanged():
    protocol = calibration_protocol()
    assert protocol["http_response_rule"] == "200_strict_JSON_array_or_204_exact_empty_body_zero_total_zero_offset_required_pagination_headers_v1"
    assert protocol["expected_cells"] == 23 and protocol["maximum_source_posts"] == 8
    assert protocol["requested_fields"] == list(calibration._v1.FIELDS)
    assert protocol["authority"]["actual_outcome_looks"] == 0
