"""Fabricated class/identity contracts only; no private/provider input."""
from __future__ import annotations

import io
import json
import urllib.parse
import zipfile

import pytest

from data.hashing import canonical_json
import research.short_interest_etf.native_dated_identity as identity
import research.short_interest_etf.sharadar_securities_master as master

AT = "2023-01-13"
NOW = "2026-10-14T01:00:00Z"
COMPOSITE, CLASS = "BBG000000001", "BBG000000002"


def archive(extra=""):
    data = ("table,permaticker,ticker,exchange,isdelisted,category,figi\n"
            f"stocks,1,SYN,XNYS,N,Domestic Common Stock Primary Class,{COMPOSITE}\n" + extra)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as zipped:
        zipped.writestr("tickers.csv", data)
    return master.CapturedSharadarMasterArchive("tickers", output.getvalue(), master.request_sha256("download-tickers"))


def row(**changes):
    value = {"ticker": "SYN", "composite_figi": COMPOSITE, "share_class_figi": CLASS,
             "locale": "us", "market": "stocks", "type": "CS", "active": True,
             "cik": "0000000001", "primary_exchange": "XNYS", "currency_name": "usd"}
    value.update(changes)
    return value


def page(active, rows=(), *, ordinal=1, following=None, url=None, raw=None, at=AT):
    payload = {"status": "OK", "results": list(rows)}
    if following is not None:
        payload["next_url"] = following
    return identity.CapturedDatedIdentityPage(at, active, ordinal,
        url or identity.ENDPOINT + "?" + urllib.parse.urlencode(identity.request_descriptor(at, active)["params"]),
        canonical_json(payload).encode() if raw is None else raw, NOW, NOW, 200, "application/json")


def qualify(pages=None, source=None):
    return identity.qualify_dated_identity(
        (page(True, [row()]), page(False)) if pages is None else pages,
        identity.build_composite_native_index(archive()) if source is None else source,
        query_date=AT, started_at=NOW, retrieved_at=NOW)


def test_full_two_panel_identity_retains_native_class_and_no_denominator_or_interval_authority():
    payload = qualify().to_payload()
    record = dict(zip(identity.ROW_FIELDS, payload["rows"][0]))
    assert record["provider_security_id"] == "sharadar:permaticker:1"
    assert record["share_class_figi"] == CLASS
    assert record["refusal_reasons"] == []
    assert [origin["active_panel"] for origin in payload["page_origins"]] == [True, False]
    assert payload["authority"]["same_class_denominator_admitted"] is False
    assert payload["authority"]["historical_effective_intervals_admitted"] is False
    assert payload["authority"]["outcome_looks"] == payload["authority"]["qc_attempts"] == 0
    assert "country" not in identity.ROW_FIELDS
    assert "shares_outstanding" not in identity.ROW_FIELDS


@pytest.mark.parametrize("bad", [b'{"status":"OK","status":"OK","results":[]}',
    b'{"status":"OK","results":[],"count":NaN}', b'{"status":"OK","results":[],"count":Infinity}',
    b'{"status":"OK","results":[],"count":true}', b'{"status":"OK","results":[],"count":1}', b'not JSON'])
def test_duplicate_nonfinite_counts_and_malformed_JSON_refuse(bad):
    with pytest.raises(identity.NativeDatedIdentityError):
        qualify((page(True, raw=bad), page(False)))


@pytest.mark.parametrize("changes,reason", [({"locale": "ca"}, "outside_dated_US_listing_common_stock"),
    ({"market": "otc"}, "outside_dated_US_listing_common_stock"),
    ({"type": "ETF"}, "outside_dated_US_listing_common_stock"),
    ({"active": False}, "active_panel_assertion_conflict"),
    ({"composite_figi": None}, "missing_or_malformed_dated_identity_fields"),
    ({"share_class_figi": "1"}, "missing_or_malformed_dated_identity_fields"),
    ({"new_shares": 100}, "unknown_source_row_fields"),
    ({"last_updated_utc": "2023-01-13"}, "malformed_optional_identity_clock")])
def test_outside_and_malformed_rows_are_retained_not_admitted(changes, reason):
    payload = qualify((page(True, [row(**changes)]), page(False))).to_payload()
    assert len(payload["rows"]) == 1
    assert reason in payload["rows"][0][-1]
    assert payload["rows"][0][5] is None


def test_malformed_identifiable_ticker_peer_quarantines_every_copy_across_panels():
    rows = qualify((page(True, [row()]), page(False, [row(ticker=" SYN ", active=False)]))).to_payload()["rows"]
    assert len(rows) == 2 and all(record[5] is None for record in rows)
    assert all("duplicate_dated_ticker_all_copies_quarantined" in record[-1] for record in rows)


def test_missing_and_malformed_rows_keep_every_original_row_locator():
    payload = qualify((page(True, [row(), {}, 15]), page(False))).to_payload()
    assert [record[:2] for record in payload["rows"]] == [[1, 0], [1, 1], [1, 2]]
    assert "source_row_not_object" in payload["rows"][2][-1]


def test_conflicting_composite_class_rows_all_refuse_even_when_tickers_differ():
    rows = qualify((page(True, [row(), row(ticker="ALT", share_class_figi="BBG000000003")]), page(False))).to_payload()["rows"]
    assert all(record[5] is None and "conflicting_composite_class_assertions" in record[-1] for record in rows)


def test_original_master_composite_or_native_collisions_include_malformed_peers():
    for extra in (f"stocks,2,OTHER,XNYS,invalid,Domestic Common Stock,{COMPOSITE}\n",
                  "stocks,01,OTHER,XNYS,N,Domestic Common Stock,BBG000000003\n"):
        index = identity.build_composite_native_index(archive(extra))
        records = qualify(source=index).to_payload()["rows"]
        assert records[0][5] is None
        assert "original_native_composite_owner_missing_or_ambiguous" in records[0][-1]


def test_a_native_class_cannot_be_backfilled_from_matching_ticker_without_composite_relation():
    records = qualify((page(True, [row(composite_figi="BBG000000009")]), page(False))).to_payload()["rows"]
    assert records[0][5] is None


@pytest.mark.parametrize("value", ["http://api.massive.com/v3/reference/tickers?cursor=x",
    "https://outside.invalid/v3/reference/tickers?cursor=x",
    "https://api.massive.com/v3/reference/tickers?cursor=x&apiKey=fabricated",
    "https://api.massive.com/v3/reference/tickers?cursor=x&APIKEY=fabricated",
    "https://api.massive.com/v3/reference/tickers?cursor=x&date=2024-01-01",
    "https://api.massive.com/v3/reference/tickers?cursor=x&active=false",
    "https://api.massive.com/v3/reference/tickers?cursor=x&cursor=y",
    "https://api.massive.com/v3/reference/tickers/other?cursor=x"])
def test_fixed_origin_cursor_never_broadens_date_panel_or_forwards_URL_secret(value):
    with pytest.raises(identity.NativeDatedIdentityError):
        identity.next_url(value, AT, True)


def test_exact_two_page_chain_keeps_row_and_page_origins():
    following = identity.ENDPOINT + "?cursor=fabricated"
    payload = qualify((page(True, [row()], following=following),
        page(True, ordinal=2, url=following), page(False))).to_payload()
    assert len(payload["page_origins"]) == 3
    assert payload["rows"][0][:2] == [1, 0]


@pytest.mark.parametrize("pages", [(page(True),), (page(True, following=identity.ENDPOINT + "?cursor=fabricated"), page(False)),
    (page(True, at="2023-01-31"), page(False)), (page(True, ordinal=2), page(False))])
def test_missing_panel_incomplete_page_wrong_date_or_ordinal_cannot_qualify(pages):
    with pytest.raises(identity.NativeDatedIdentityError):
        qualify(pages)


def test_completed_qualification_is_detached_and_refuses_reflection_reseal():
    value = qualify()
    original = value.to_bytes()
    payload = value.to_payload()
    payload["rows"][0][5] = "sharadar:permaticker:999"
    assert value.to_bytes() is original
    object.__setattr__(value, "_bytes", canonical_json(payload).encode())
    with pytest.raises(identity.NativeDatedIdentityError, match="sealed_dated_identity_changed"):
        value.to_bytes()


def test_native_owner_with_two_different_class_assertions_is_ambiguous():
    records = qualify((page(True, [row(), row(ticker="OTHER", share_class_figi="BBG000000003")]), page(False))).to_payload()["rows"]
    assert all(record[5] is None for record in records)


def test_capture_reflection_change_cannot_replace_original_page_under_the_same_receipt():
    captured = page(True, [row()])
    object.__setattr__(captured, "raw", canonical_json({"status": "OK", "results": [row(ticker="ALTERED")]}).encode())
    with pytest.raises(identity.NativeDatedIdentityError, match="capture_page_changed"):
        qualify((captured, page(False)))


def test_both_panels_require_original_capture_order_not_reordered_receipts():
    with pytest.raises(identity.NativeDatedIdentityError, match="ordered_capture_inventory"):
        qualify((page(False), page(True, [row()])))


def test_capture_revalidation_cannot_reset_original_anchor_after_byte_replacement():
    captured = page(True, [row()])
    original_anchor = captured._anchor
    object.__setattr__(captured, "raw", canonical_json({"status": "OK", "results": [row(ticker="ALTERED")]}).encode())
    with pytest.raises(identity.NativeDatedIdentityError, match="capture_page_changed"):
        captured.__post_init__()
    assert captured._anchor is original_anchor
