"""Fabricated disclosure inventories; no actual filing or economic evidence."""
from __future__ import annotations

import copy
from dataclasses import replace
import json

import pytest

from data.hashing import hash_bytes, hash_payload
import research.short_interest_etf.terminal_disclosure_evidence as disclosure


CIKS = ("1010101010", "2020202020")
SOURCE = "a" * 64
CLOCK = "2026-10-13T21:00:00Z"


def protocol():
    return disclosure.freeze_disclosure_protocol(CIKS, source_class_report_sha256=SOURCE)


def row(symbol="TWTR", *, accession=None, form="8-K", text="Fabricated Item 2.01 text."):
    position = 0 if symbol == "TWTR" else 1
    accession = accession or ("0000000001-22-000001" if position == 0 else "0000000002-23-000001")
    return {"accession_number": accession, "cik": CIKS[position],
            "filing_date": "2022-10-15" if position == 0 else "2023-05-01",
            "filing_url": "https://www.sec.gov/Archives/edgar/data/" + str(int(CIKS[position])) + "/" + accession + ".txt",
            "form_type": form, "ticker": symbol, "issuer_name": "Fabricated issuer only",
            "items_text": text}


def capture(request_id="text-TWTR", rows=None, *, owner=None, **envelope):
    owner = owner or protocol()
    if rows is None:
        rows = [row(request_id.split("-", 1)[1])]
    payload = {"status": "OK", "results": rows, "count": len(rows), **envelope}
    return disclosure.CapturedDisclosureResponse(
        request_id, owner.request_sha256(request_id), json.dumps(payload).encode(), CLOCK)


def captures(*, owner=None):
    owner = owner or protocol()
    return tuple(capture(rid, owner=owner) for rid in disclosure.REQUEST_IDS)


def report(*, owner=None, pages=None):
    owner = owner or protocol()
    return disclosure.qualify_terminal_disclosure(owner, pages or captures(owner=owner), retrieved_at=CLOCK)


@pytest.mark.parametrize("request_id", disclosure.REQUEST_IDS)
def test_exact_four_fixed_requests_no_current_ticker_fallback(request_id):
    owner = protocol()
    request = owner.request(request_id)
    kind, symbol = request_id.split("-", 1)
    position = 0 if symbol == "TWTR" else 1
    assert request["method"] == "GET"
    assert request["url"] == "https://api.massive.com" + (
        "/stocks/filings/vX/index" if kind == "index" else "/stocks/filings/8-K/vX/text")
    assert request["params"] == {"cik": CIKS[position], "form_type.any_of": "8-K,8-K/A",
        "filing_date.gte": disclosure.WINDOWS[position][1], "filing_date.lte": disclosure.WINDOWS[position][2],
        "limit": "10000" if kind == "index" else "100", "sort": "filing_date.asc"}
    assert owner.request_sha256(request_id) == hash_payload(request)
    assert "ticker" not in request["params"]


@pytest.mark.parametrize("ciks", [[], CIKS[0], (CIKS[0],), (*CIKS, CIKS[0]),
    (CIKS[0], CIKS[0]), ("0000000000", CIKS[1]), ("123", CIKS[1]),
    (1010101010, CIKS[1]), (True, CIKS[1]), (" 1010101010", CIKS[1])])
def test_noncanonical_or_unbound_issuer_protocol_refuses(ciks):
    with pytest.raises(disclosure.TerminalDisclosureError):
        disclosure.freeze_disclosure_protocol(ciks, source_class_report_sha256=SOURCE)


@pytest.mark.parametrize("value", [None, True, "", "a" * 63, "g" * 64, "A" * 64])
def test_source_class_report_hash_required(value):
    with pytest.raises(disclosure.TerminalDisclosureError):
        disclosure.freeze_disclosure_protocol(CIKS, source_class_report_sha256=value)


def test_detached_protocol_and_request_cannot_mutate_frozen_identity():
    owner = protocol()
    digest = owner.sha256
    payload, request = owner.to_payload(), owner.request("text-TWTR")
    payload["issuer_CIKs"][0] = CIKS[1]
    payload["authority"]["ready_for_empirical_backtest"] = True
    request["params"]["ticker"] = "CURRENT"
    assert owner.sha256 == digest
    assert "ticker" not in owner.request("text-TWTR")["params"]


@pytest.mark.parametrize("attribute,value", [("ciks", CIKS[::-1]), ("source_class_report_sha256", "b" * 64)])
def test_object_level_protocol_mutation_refuses(attribute, value):
    owner = protocol()
    object.__setattr__(owner, attribute, value)
    with pytest.raises(disclosure.TerminalDisclosureError, match="protocol_changed"):
        owner.to_payload()


@pytest.mark.parametrize("name,value", [("MAXIMUM_REQUESTS", 5), ("MAXIMUM_RESPONSE_BYTES", True),
    ("WINDOWS", (("TWTR", "2022-10-01", "2022-12-31"), disclosure.WINDOWS[1])),
    ("REQUEST_IDS", disclosure.REQUEST_IDS[::-1])])
def test_fixed_budget_window_or_order_drift_cannot_mint_new_protocol(monkeypatch, name, value):
    monkeypatch.setattr(disclosure, name, value)
    with pytest.raises(disclosure.TerminalDisclosureError, match="fixed_disclosure_policy_changed"):
        protocol()


@pytest.mark.parametrize("field,value", [("raw", b""), ("raw", bytearray(b"{}")),
    ("http_status", True), ("http_status", 201), ("content_type", "text/html"),
    ("content_type", "application/json\nsecret-canary"), ("received_at", "2026-10-13"),
    ("received_at", "2026-10-13T21:00:00+00:00"), ("request_sha256", "x" * 64),
    ("request_id", "text-CURRENT")])
def test_invalid_capture_type_transport_or_clock_refuses(field, value):
    with pytest.raises(disclosure.TerminalDisclosureError):
        replace(capture(), **{field: value})


def test_capture_raw_byte_bound_is_exact():
    good = replace(capture(), raw=b"x" * disclosure.MAXIMUM_RESPONSE_BYTES)
    assert good.raw_sha256 == hash_bytes(good.raw)
    with pytest.raises(disclosure.TerminalDisclosureError, match="bounded_disclosure_bytes"):
        replace(good, raw=good.raw + b"x")


def test_request_hash_must_bind_exact_frozen_issuer_route_and_window():
    page = replace(capture(), request_sha256="b" * 64)
    with pytest.raises(disclosure.TerminalDisclosureError, match="request_binding_mismatch"):
        disclosure.validate_disclosure_response(protocol(), page)


@pytest.mark.parametrize("raw", [b'{"status":"OK","status":"OK","results":[]}',
    b'{"status":"OK","results":[{"cik":"1","cik":"2"}]}',
    b'{"status":"OK","results":[NaN]}', b'{"status":"OK","results":[Infinity]}',
    b'{"status":"OK","results":[-Infinity]}', b'\xff', b'{"results":',
    b'{"status":"OK","results":["\\ud800"]}'])
def test_duplicate_nonfinite_invalid_or_non_unicode_JSON_refuses(raw):
    with pytest.raises(disclosure.TerminalDisclosureError):
        disclosure.validate_disclosure_response(protocol(), replace(capture(), raw=raw))


@pytest.mark.parametrize("envelope", [{"status":"ERROR"}, {"count":True}, {"count":2},
    {"next_url":False}, {"unexpected": 1}, {"results":{}}, {"request_id":42}])
def test_response_envelope_count_and_pagination_shape_refuse(envelope):
    page = replace(capture(), raw=json.dumps({"status":"OK", "results":[row()], "count":1, **envelope}).encode())
    with pytest.raises(disclosure.TerminalDisclosureError):
        disclosure.validate_disclosure_response(protocol(), page)


def test_missing_results_only_explicit_integer_zero_retains_absence_not_zero_cash():
    owner = protocol()
    page = replace(capture(), raw=b'{"status":"OK","count":0}')
    result = disclosure.validate_disclosure_response(owner, page)
    assert result["raw_results_absent"] is True and result["raw_row_count"] == 0
    assert result["records"] == [] and result["authority"]["terminal_economics_admitted"] is False
    with pytest.raises(disclosure.TerminalDisclosureError, match="missing_disclosure_results"):
        disclosure.validate_disclosure_response(owner, replace(page, raw=b'{"status":"OK"}'))


@pytest.mark.parametrize("field,value,reason", [("cik", CIKS[1], "issuer_mismatch"),
    ("cik", "101010101", "ten_digit_CIK"), ("filing_date", "2022-12-01", "window_mismatch"),
    ("filing_date", "2022-10-14T00:00:00Z", "date_required"),
    ("form_type", "10-K", "form_mismatch"), ("accession_number", "bad", "accession_required"),
    ("filing_url", "https://other.example/Archives/file.txt", "SEC_Archives_origin"),
    ("filing_url", "https://user@www.sec.gov/Archives/file.txt", "SEC_Archives_origin"),
    ("filing_url", "https://www.sec.gov/Archives/file.txt?token=private", "SEC_Archives_origin"),
    ("filing_url", "https://www.sec.gov/Archives/../file.txt", "SEC_Archives_origin")])
def test_every_wrong_issuer_window_form_accession_or_URL_row_is_preserved(field,value,reason):
    changed=row(); changed[field]=value
    page=capture(rows=[changed])
    result=disclosure.validate_disclosure_response(protocol(),page)
    assert result["raw_row_count"] == len(result["records"]) == 1
    record=result["records"][0]
    assert record["inventory_status"] == "refused" and reason in record["reason"]
    assert record["source_record"][field] == value
    assert record["origin"]["source_file_sha256"] == hash_bytes(page.raw)


def test_same_accession_malformed_peer_quarantines_all_copies_before_values():
    valid=row(); invalid=copy.deepcopy(valid); invalid["cik"]="not-an-issuer"
    result=disclosure.validate_disclosure_response(protocol(),capture(rows=[valid,invalid]))
    assert [r["reason"] for r in result["records"]] == ["duplicate_accession_quarantined"] * 2
    assert all(r["metadata"] is None for r in result["records"])


def test_amendments_are_distinct_accessions_not_replaced_or_collapsed():
    rows=[row(),row(accession="0000000001-22-000002",form="8-K/A")]
    result=disclosure.validate_disclosure_response(protocol(),capture(rows=rows))
    assert [r["metadata"]["form_type"] for r in result["records"]] == ["8-K","8-K/A"]
    assert all(r["inventory_status"] == "core_Items_inventory" for r in result["records"])


@pytest.mark.parametrize("text", [None,""," \n\t",42,True,"bad\x00text","bad\x7ftext"])
def test_missing_or_unusable_core_text_is_explicitly_retained(text):
    result=disclosure.validate_disclosure_response(protocol(),capture(rows=[row(text=text)]))
    record=result["records"][0]
    assert record["inventory_status"] == "missing_or_unusable_text"
    assert record["source_record"]["items_text"] == text
    assert record["items_text"] is None


def test_metadata_without_text_stays_inventory_and_HTTP_is_unverified_not_followed():
    source=row();source.pop("items_text")
    result=disclosure.validate_disclosure_response(protocol(),capture("index-TWTR",rows=[source]))
    assert result["records"][0]["inventory_status"] == "metadata_inventory"
    source["filing_url"]=source["filing_url"].replace("https://","http://")
    result=disclosure.validate_disclosure_response(protocol(),capture(rows=[source]))
    assert result["records"][0]["inventory_status"] == "source_verification_needed"
    assert result["records"][0]["metadata"]["SEC_URL_is_HTTPS"] is False


def test_next_page_marks_incomplete_keeps_page_and_never_relabels_complete():
    owner=protocol();pages=list(captures(owner=owner))
    pages[1]=capture("text-TWTR",owner=owner,next_url="https://api.massive.com/unused-cursor")
    result=report(owner=owner,pages=tuple(pages)).to_payload()
    assert result["all_four_pages_complete"] is False
    assert result["tables"][1]["pagination_refusal"] == "next_page_unconsumed"
    assert result["tables"][1]["raw_row_count"] == 1
    assert result["authority"]["ready_for_empirical_backtest"] is False


def test_consideration_completion_payment_phrases_never_admit_terminal_economics():
    page=capture(rows=[row(text="Fabricated merger pays $17.13 per share on October 28; completed; actual payment received.")])
    record=disclosure.validate_disclosure_response(protocol(),page)["records"][0]
    assert record["inventory_status"] == "core_Items_inventory"
    for field in ("payment_date","per_share_consideration","effective_cash_available_at"):
        assert record[field] is None
    assert record["terminal_economics_admitted"] is False


def test_private_report_binds_every_origin_and_expected_index_text_replica():
    evidence=report(); result=evidence.to_payload()
    assert result["all_four_pages_complete"] is True
    assert len(result["tables"]) == 4 and len(result["accession_inventory_links"]) == 2
    assert all(link["metadata_agreement"] and link["index_and_text_present"] for link in result["accession_inventory_links"])
    assert all(link["terminal_economics_admitted"] is False for link in result["accession_inventory_links"])
    assert result["source_class_report_sha256"] == SOURCE
    assert result["authority"]["actual_outcome_looks"] == result["authority"]["qc_attempts"] == 0
    assert result["report_sha256"] == evidence.sha256
    payload=copy.deepcopy(result);payload.pop("report_sha256")
    assert hash_payload(payload) == evidence.sha256


def test_cross_route_metadata_conflict_quarantines_both_inventory_copies():
    owner=protocol();pages=list(captures(owner=owner));different=row();different["filing_date"]="2022-10-16"
    pages[1]=capture("text-TWTR",rows=[different],owner=owner)
    result=report(owner=owner,pages=tuple(pages)).to_payload()
    assert [result["tables"][i]["records"][0]["reason"] for i in (0,1)] == ["cross_filing_accession_conflict"]*2


@pytest.mark.parametrize("change", ["reverse","missing","list","wrong_protocol","reverse_clock"])
def test_exact_capture_tuple_lineage_order_and_chronology_required(change):
    owner=protocol();pages=captures(owner=owner)
    if change=="reverse":pages=pages[::-1]
    elif change=="missing":pages=pages[:-1]
    elif change=="list":pages=list(pages)
    elif change=="wrong_protocol":owner=disclosure.freeze_disclosure_protocol(CIKS[::-1],source_class_report_sha256=SOURCE)
    else:pages=(replace(pages[0],received_at="2026-10-13T21:00:01Z"),*pages[1:])
    with pytest.raises(disclosure.TerminalDisclosureError):
        report(owner=owner,pages=pages)


def test_detached_report_mutation_does_not_reclassify_retained_inventory():
    evidence=report();before=evidence.sha256;payload=evidence.to_payload()
    payload["authority"]["ready_for_empirical_backtest"]=True
    payload["tables"][0]["records"][0]["source_record"]["cik"]=CIKS[1]
    assert evidence.sha256 == before
    assert evidence.to_payload()["authority"]["ready_for_empirical_backtest"] is False


def test_retained_capture_mutation_is_detected_and_does_not_reseal_report():
    evidence=report(); page=evidence.captures[0]
    object.__setattr__(page,"raw",capture("index-TWTR",rows=[]).raw)
    with pytest.raises(disclosure.TerminalDisclosureError,match="evidence_changed"):
        evidence.to_payload()


def test_exact_types_not_duck_typed_admission_flags():
    class Duck:
        source_admitted=True
        def to_payload(self):return {"ready_for_empirical_backtest":True}
    with pytest.raises(disclosure.TerminalDisclosureError):
        disclosure.qualify_terminal_disclosure(Duck(),captures(),retrieved_at=CLOCK)
