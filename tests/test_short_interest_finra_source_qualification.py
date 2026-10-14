"""Invented SI quantities exercise software, never provider/market evidence."""
from __future__ import annotations

import copy
import dataclasses

import pytest

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.finra_source_qualification import (
    FIELDS,
    PROTOCOL_SHA256,
    SETTLEMENTS,
    TICKERS,
    FinraSourceQualification,
    FinraSourceQualificationError,
    qualification_protocol,
    qualify_finra_snapshot,
)


def _rows() -> list[dict]:
    return [
        {"symbolCode": ticker, "settlementDate": settlement,
         "currentShortPositionQuantity": ticker_index * 100 + date_index * 10,
         "previousShortPositionQuantity": None if date_index == 0 else ticker_index * 100 + (date_index - 1) * 10,
         "revisionFlag": None, "stockSplitFlag": None,
         "marketClassCode": "NMS", "issuerServicesGroupExchangeCode": "TOY",
         "issueName": "FABRICATED SOFTWARE TEST ONLY"}
        for ticker_index, ticker in enumerate(TICKERS)
        for date_index, settlement in enumerate(SETTLEMENTS)
    ]


def _page(rows: list) -> bytes:
    return canonical_json(rows).encode("utf-8")


def _qualify(rows: list | None = None, *, pages: tuple[bytes, ...] | None = None) -> dict:
    return qualify_finra_snapshot(
        (_page(_rows() if rows is None else rows),) if pages is None else pages,
        expected_protocol_sha256=PROTOCOL_SHA256,
    ).to_payload()


def test_frozen_protocol_is_detached_and_pins_exact_denominators_bounds_and_fields():
    protocol = qualification_protocol()
    assert hash_payload(protocol) == PROTOCOL_SHA256
    assert protocol["expected_slots"] == 48 and protocol["target_slots"] == 36
    assert protocol["query_limit"] == 100 and protocol["maximum_pages"] == 8
    assert protocol["maximum_rows"] == 800 and protocol["maximum_page_bytes"] == 1024 * 1024
    assert protocol["requested_fields"] == list(FIELDS)
    assert protocol["predecessor_dates"] == dict(zip(SETTLEMENTS[1:], SETTLEMENTS[:-1]))
    assert protocol["publication_dates"]["2026-06-30"] == "2026-07-10"
    protocol["tickers"].clear()
    protocol["authority"]["source_admitted"] = True
    assert qualification_protocol()["tickers"] == list(TICKERS)
    assert qualification_protocol()["authority"]["source_admitted"] is False


def test_complete_fabricated_sample_reports_all48_slots_and36_targets_without_quantities():
    result = _qualify()
    assert result["totals"] == {
        "expected_slots": 48, "target_slots": 36, "raw_rows": 48,
        "valid_slots": 48, "refused_rows": 0, "out_of_sample_rows": 0,
        "unidentifiable_rows": 0,
    }
    assert result["slot_status_counts"]["valid"] == 48
    assert result["continuity_status_counts"]["matched"] == 36
    assert result["capture_structurally_complete"] is True
    assert result["continuity_comparison_complete"] is True
    assert result["continuity_consistent"] is True
    assert result["refusal_reason_counts"] == {}
    assert result["market_class_counts"] == {"NMS": 48}
    assert result["revision_flag_counts"] == {"R": 0, "missing": 48}
    text = canonical_json(result)
    for forbidden in ("currentShortPositionQuantity", "previousShortPositionQuantity", "FABRICATED SOFTWARE TEST", "AAPL", "issueName"):
        assert forbidden not in text
    assert result["authority"]["latest_stored_snapshot_only"] is True
    for key, value in result["authority"].items():
        if key != "latest_stored_snapshot_only":
            assert value is False or type(value) is int and value == 0


@pytest.mark.parametrize("changes", [
    {"currentShortPositionQuantity": -1},
    {"currentShortPositionQuantity": True},
    {"currentShortPositionQuantity": "0"},
    {"currentShortPositionQuantity": None},
    {"unknown_field": "invented"},
    {"revisionFlag": "X"},
])
@pytest.mark.parametrize("malformed_first", [False, True])
@pytest.mark.parametrize("across_pages", [False, True])
def test_raw_malformed_duplicate_quarantines_valid_peer_before_validation(changes, malformed_first, across_pages):
    rows = _rows()
    good = copy.deepcopy(rows[0])
    bad = {**good, **changes}
    pair = [bad, good] if malformed_first else [good, bad]
    pages = (_page([pair[0], *rows[1:]]), _page([pair[1]])) if across_pages else (_page([*pair, *rows[1:]]),)
    result = _qualify(pages=pages)
    assert result["totals"]["valid_slots"] == 47
    assert result["totals"]["refused_rows"] == 2
    assert result["slot_status_counts"]["duplicate"] == 1
    assert result["refusal_reason_counts"]["duplicate"] == 2
    assert result["continuity_status_counts"]["predecessor_duplicate"] == 1
    assert result["continuity_status_counts"]["matched"] == 35
    assert result["capture_structurally_complete"] is False
    assert result["continuity_consistent"] is False


@pytest.mark.parametrize("different_quantity", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_multiple_market_classes_never_sum_or_deduplicate_even_when_quantities_equal(different_quantity, reverse):
    rows = _rows()
    other = {**rows[0], "marketClassCode": "OTC"}
    if different_quantity:
        other["currentShortPositionQuantity"] += 7
    pair = [other, rows[0]] if reverse else [rows[0], other]
    result = _qualify([*pair, *rows[1:]])
    assert result["slot_status_counts"]["ambiguous_market_class"] == 1
    assert result["refusal_reason_counts"]["ambiguous_market_class"] == 2
    assert result["totals"]["valid_slots"] == 47
    assert result["continuity_status_counts"]["predecessor_ambiguous_market_class"] == 1
    assert result["market_class_counts"] == {"NMS": 47}


def test_well_formed_duplicate_is_quarantined_not_deduplicated():
    rows = _rows()
    result = _qualify([*rows, copy.deepcopy(rows[0])])
    assert result["slot_status_counts"]["duplicate"] == 1
    assert result["totals"]["refused_rows"] == 2
    assert result["refusal_reason_counts"] == {"duplicate": 2}


def test_missing_previous_is_unknown_but_explicit_zero_compares_as_zero():
    rows = _rows()
    assert rows[1]["previousShortPositionQuantity"] == 0
    assert _qualify(rows)["continuity_status_counts"]["matched"] == 36
    rows[1]["previousShortPositionQuantity"] = None
    result = _qualify(rows)
    assert result["slot_status_counts"]["valid"] == 48
    assert result["continuity_status_counts"]["missing_previous_quantity"] == 1
    assert result["continuity_status_counts"]["matched"] == 35
    assert result["continuity_comparison_complete"] is False
    assert result["continuity_consistent"] is False


def test_absent_first_predecessor_is_named_and_not_dropped_from_denominator():
    result = _qualify(_rows()[1:])
    assert result["slot_status_counts"]["missing"] == 1
    assert sum(result["slot_status_counts"].values()) == 48
    assert result["continuity_status_counts"]["predecessor_missing"] == 1
    assert sum(result["continuity_status_counts"].values()) == 36
    assert result["continuity_status_counts"]["matched"] == 35


def test_revision_and_split_flags_do_not_adjust_mismatch_or_assert_PIT():
    rows = _rows()
    rows[1].update(previousShortPositionQuantity=9, revisionFlag="R", stockSplitFlag="S")
    result = _qualify(rows)
    assert result["continuity_status_counts"]["mismatched"] == 1
    assert result["revision_flag_counts"] == {"R": 1, "missing": 47}
    assert result["split_flag_counts"] == {"S": 1, "missing": 47}
    assert result["continuity_comparison_complete"] is True
    assert result["continuity_consistent"] is False
    assert result["authority"]["point_in_time_data"] is False
    assert result["authority"]["correction_timing_verified"] is False


@pytest.mark.parametrize("value", [True, False, -1, "0", "1.0", "NaN", None, 10**18 + 1])
def test_invalid_or_missing_current_quantity_is_named_refusal(value):
    rows = _rows()
    rows[1]["currentShortPositionQuantity"] = value
    result = _qualify(rows)
    assert result["slot_status_counts"]["malformed"] == 1
    assert result["totals"]["refused_rows"] == 1
    assert result["continuity_status_counts"]["target_malformed"] == 1
    assert result["continuity_status_counts"]["predecessor_malformed"] == 1
    assert result["continuity_consistent"] is False


@pytest.mark.parametrize("token", [b"0.0", b"0e3", b"-0.0", b"1.0", b"1e3", b"1000000000000000000.0"])
def test_documented_JSON_number_tokens_are_admitted_when_exactly_integral(token):
    blob = _page(_rows()).replace(b'"currentShortPositionQuantity":0', b'"currentShortPositionQuantity":' + token, 1)
    result = _qualify(pages=(blob,))
    assert result["slot_status_counts"]["valid"] == 48
    assert result["totals"]["refused_rows"] == 0


@pytest.mark.parametrize("token", [b"0.5", b"-1.0", b"1e19", b"1e-999", b'"1.0"'])
def test_fractional_negative_large_or_string_quantity_token_is_refused(token):
    blob = _page(_rows()).replace(b'"currentShortPositionQuantity":0', b'"currentShortPositionQuantity":' + token, 1)
    result = _qualify(pages=(blob,))
    assert result["slot_status_counts"]["malformed"] == 1
    assert result["refusal_reason_counts"]["invalid_quantity"] == 1


@pytest.mark.parametrize("changes,reason", [
    ({"revisionFlag": ""}, "invalid_revision_flag"),
    ({"stockSplitFlag": "R"}, "invalid_split_flag"),
    ({"marketClassCode": " NMS"}, "noncanonical_text"),
    ({"issuerServicesGroupExchangeCode": True}, "noncanonical_text"),
    ({"issueName": 99}, "invalid_issue_name"),
    ({"shortVolume": 123}, "missing_or_unknown_fields"),
])
def test_unknown_fields_or_malformed_metadata_cannot_become_valid_rows(changes, reason):
    rows = _rows()
    rows[0].update(changes)
    result = _qualify(rows)
    assert result["slot_status_counts"]["malformed"] == 1
    assert result["refusal_reason_counts"][reason] == 1


@pytest.mark.parametrize("extra", [42, {"symbolCode": "AAPL", "settlementDate": "2026-6-30"}, {"symbolCode": " AAPL", "settlementDate": "2026-06-30"}])
def test_unidentifiable_row_keeps_capture_incomplete_even_if_all48cells_exist(extra):
    result = _qualify([*_rows(), extra])
    assert result["totals"]["unidentifiable_rows"] == 1
    assert result["totals"]["valid_slots"] == 48
    assert result["capture_structurally_complete"] is False
    assert result["continuity_consistent"] is False


@pytest.mark.parametrize("changes", [{"symbolCode": "BRK-B"}, {"symbolCode": "UNKNOWN"}, {"settlementDate": "2026-08-31"}])
def test_out_of_sample_date_or_symbol_is_explicit_and_never_aliased(changes):
    rows = _rows()
    extra = {**rows[0], **changes}
    result = _qualify([*rows, extra])
    assert result["totals"]["out_of_sample_rows"] == 1
    assert result["refusal_reason_counts"]["out_of_sample_row"] == 1
    assert result["totals"]["valid_slots"] == 48
    assert result["capture_structurally_complete"] is False


def test_empty_provider_array_produces48missing_slots_not_a_success():
    result = _qualify([])
    assert result["slot_status_counts"]["missing"] == 48
    assert result["continuity_status_counts"]["target_missing"] == 36
    assert result["continuity_consistent"] is False


@pytest.mark.parametrize("blob", [b'{"rows":[]}', b'[NaN]', b'[Infinity]', b'[1e999999]', b'[{"a":1,"a":2}]', b'\xff', b'[{'])
def test_bad_page_or_nonfinite_JSON_fails_closed(blob):
    if blob == b'[1e999999]':
        # A finite lexical token in the wrong row shape is a named row refusal.
        assert _qualify(pages=(blob,))["totals"]["unidentifiable_rows"] == 1
    else:
        with pytest.raises(FinraSourceQualificationError):
            _qualify(pages=(blob,))


def test_capture_page_byte_count_and_row_limits_are_frozen():
    with pytest.raises(FinraSourceQualificationError, match="byte bound"):
        _qualify(pages=(b" " * (1024 * 1024 + 1),))
    with pytest.raises(FinraSourceQualificationError, match="one to eight"):
        _qualify(pages=tuple(b"[]" for _ in range(9)))
    with pytest.raises(FinraSourceQualificationError, match="bounded JSON"):
        _qualify(pages=(_page([{}] * 101),))
    with pytest.raises(FinraSourceQualificationError, match="mutable"):
        _qualify(pages=(bytearray(b"[]"),))
    with pytest.raises(FinraSourceQualificationError, match="expected protocol"):
        qualify_finra_snapshot((b"[]",), expected_protocol_sha256="f" * 64)


def test_output_is_detached_and_immutable_and_responds_to_every_source_byte_change():
    report = qualify_finra_snapshot((_page(_rows()),), expected_protocol_sha256=PROTOCOL_SHA256)
    baseline = report.to_payload()
    changed = report.to_payload()
    changed["authority"]["source_admitted"] = True
    changed["slot_status_counts"].clear()
    assert report.to_payload() == baseline
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.payload_json = "{}"
    reversed_report = _qualify(list(reversed(_rows())))
    assert reversed_report["slot_status_counts"] == baseline["slot_status_counts"]
    assert reversed_report["continuity_status_counts"] == baseline["continuity_status_counts"]
    assert reversed_report["report_sha256"] != baseline["report_sha256"]
    repeated = qualify_finra_snapshot((_page(_rows()),), expected_protocol_sha256=PROTOCOL_SHA256)
    assert repeated.payload_json == report.payload_json
    assert repeated.sha256 == report.sha256


@pytest.mark.parametrize("field,value", [("authority", {"source_admitted": True}), ("continuity_consistent", False), ("report_sha256", "f" * 64)])
def test_report_cannot_rehash_forged_authority_or_completeness(field, value):
    result = _qualify()
    result[field] = value
    if field != "report_sha256":
        result["report_sha256"] = hash_payload({key: item for key, item in result.items() if key != "report_sha256"})
    with pytest.raises(FinraSourceQualificationError):
        FinraSourceQualification(canonical_json(result))


@pytest.mark.parametrize("field,value", [("point_in_time_data", 0), ("actual_outcome_looks", False), ("latest_stored_snapshot_only", 1)])
def test_report_authority_requires_exact_boolean_and_integer_types(field, value):
    result = _qualify()
    result["authority"][field] = value
    result["report_sha256"] = hash_payload({key: item for key, item in result.items() if key != "report_sha256"})
    with pytest.raises(FinraSourceQualificationError, match="authority"):
        FinraSourceQualification(canonical_json(result))
