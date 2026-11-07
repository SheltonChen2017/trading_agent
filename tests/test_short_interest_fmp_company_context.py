"""Fabricated identifiers/caps only; no provider or local private inputs."""
from __future__ import annotations

import io
import json
import zipfile
from urllib.parse import urlencode

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_dated_identity as identity
import research.short_interest_etf.sharadar_securities_master as master
import research.short_interest_etf.fmp_company_context as context

START = "2026-10-14T00:00:00Z"
RECEIVED = "2026-10-14T00:00:01Z"
CAP_START = "2026-10-14T00:00:02Z"
CAP_RECEIVED = "2026-10-14T00:00:03Z"
AT = "2023-01-13"


def ticket(symbol="SYN", cik="1"):
    raw = canonical_json({"schema": context.SCHEMA + "-target-proposal", "symbol": symbol, "cik": cik,
        "source_origins": [{"artifact_sha256": "a" * 64, "locator": "/fabricated/source-row/0"}]}).encode()
    return context.seal_target_ticket(raw, expected_sha256=hash_bytes(raw))


def lookup_row(**changes):
    value = {"symbol": "SYN", "companyName": "Fabricated Company", "cik": "0000000001",
             "exchangeFullName": "Fabricated Exchange", "exchange": "SYNTHETIC", "currency": "EUR"}
    value.update(changes)
    return value


def qualify_lookup(rows=None, *, raw=None, selected=None, **changes):
    source = ticket() if selected is None else selected
    raw = canonical_json([lookup_row()] if rows is None else rows).encode() if raw is None else raw
    kwargs = {"raw": raw, "raw_sha256": hash_bytes(raw),
              "request_sha256": hash_payload(context.request_descriptor(source, "lookup")),
              "started_at": START, "received_at": RECEIVED}
    kwargs.update(changes)
    return context.qualify_context(source, **kwargs)


def qualify_cap(rows=None, *, raw=None, company=None, **changes):
    company = qualify_lookup() if company is None else company
    raw = canonical_json([{"symbol": "SYN", "date": AT, "marketCap": 10}]
                         if rows is None else rows).encode() if raw is None else raw
    kwargs = {"raw": raw, "raw_sha256": hash_bytes(raw),
        "request_sha256": hash_payload(context.request_descriptor(company._refs[0], "cap")),
        "started_at": CAP_START, "received_at": CAP_RECEIVED}
    kwargs.update(changes)
    return context.qualify_company_cap(company, **kwargs)


def daily_row(**changes):
    value = {"ticker": "SYN", "composite_figi": "BBG000000001", "share_class_figi": "BBG000000002",
        "locale": "us", "market": "stocks", "type": "CS", "active": True,
        "cik": "0000000001", "primary_exchange": "XNYS", "currency_name": "usd"}
    value.update(changes)
    return value


def dated(rows=None, *, at=AT):
    raw = ("table,permaticker,ticker,exchange,isdelisted,category,figi\n"
        "stocks,1,SYN,XNYS,N,Domestic Common Stock Primary Class,BBG000000001\n"
        "stocks,2,SECOND,XNYS,N,Domestic Common Stock Secondary Class,BBG000000003\n"
        "stocks,3,OTHER,XNYS,N,Domestic Common Stock Primary Class,BBG000000005\n")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as zipped:
        zipped.writestr("tickers.csv", raw)
    captured = master.CapturedSharadarMasterArchive("tickers", output.getvalue(), master.request_sha256("download-tickers"))
    pages = []
    for active in (True, False):
        url = identity.ENDPOINT + "?" + urlencode(identity.request_descriptor(at, active)["params"])
        body = canonical_json({"status": "OK", "results": [daily_row()] if rows is None and active else
                              (rows if active else [])}).encode()
        pages.append(identity.CapturedDatedIdentityPage(at, active, 1, url, body,
                     START if active else RECEIVED, RECEIVED, 200, "application/json"))
    return identity.qualify_dated_identity(tuple(pages), identity.build_composite_native_index(captured),
        query_date=at, started_at=START, retrieved_at=RECEIVED)


def test_current_company_context_does_not_backdate_currency_sector_class_or_authority():
    value = qualify_lookup().to_payload()
    assert value["selected_row_index"] == 0
    assert value["rows"][0]["source_fields"]["currency"] == "EUR"
    assert value["historical_currency_from_lookup"] is None
    assert value["historical_class_from_lookup"] is value["historical_sector_from_lookup"] is None
    assert value["authority"]["same_class_denominator_admitted"] is False
    assert value["authority"]["qc_attempts"] == value["authority"]["outcome_looks"] == 0


@pytest.mark.parametrize("raw", [b'[{"symbol":"SYN","cik":"1","price":8}]',
    b'[{"symbol":"SYN","cik":"1","marketCap":8}]', b'[{"symbol":"SYN","cik":"1","cik":"1"}]',
    b'[{"symbol":"SYN","cik":"1","currency":NaN}]', b'[{"symbol":"SYN","cik":1}]',
    b'[{"symbol":"SYN","cik":"1","unknown":"value"}]', b'{}', b'null'])
def test_financial_unknown_duplicate_nonfinite_or_wrong_type_lookup_refuses_pre_hash(raw):
    with pytest.raises(context.FmpContextError):
        context.preflight_lookup_scope(raw)


@pytest.mark.parametrize("value", ["0", "0000000000", "-1", "1.0", " 1", "1 ", "10000000000", 1, True])
def test_CIK_zero_malformed_or_numeric_is_not_entity_identity(value):
    with pytest.raises(context.FmpContextError):
        ticket(cik=value)


def test_CIK_only_zero_padding_preserves_original_selection_and_exact_query():
    value = ticket(cik="1")
    assert value.to_payload()["cik"] == "1"
    assert context.request_descriptor(value, "lookup")["params"] == {"cik": "0000000001", "limit": 50}
    assert "apikey" not in context.clean_url(value, "lookup")


@pytest.mark.parametrize("rows", [[], [lookup_row(symbol="OTHER")], [lookup_row(cik="2")],
    [lookup_row(), lookup_row(cik="2")], [lookup_row(), lookup_row(symbol=" SYN ", cik=None)]])
def test_missing_mismatched_or_malformed_selected_symbol_peer_blocks_cap_without_fallback(rows):
    company = qualify_lookup(rows)
    assert company.to_payload()["selected_row_index"] is None
    with pytest.raises(context.FmpContextError, match="no_cap_fallback"):
        qualify_cap(company=company)


def test_another_symbol_same_company_is_retained_not_an_arbitrary_selected_class():
    value = qualify_lookup([lookup_row(symbol="SECOND"), lookup_row()]).to_payload()
    assert value["selected_row_index"] == 1
    assert value["rows"][0]["reason"] == "not_selected_request_target"


@pytest.mark.parametrize("changes", [{"raw_sha256": "b" * 64}, {"request_sha256": "b" * 64},
    {"received_at": "2026-10-13T23:59:59Z"}, {"http_status": 404}, {"http_status": True},
    {"content_type": "text/html"}])
def test_context_binding_hash_status_media_or_clock_refused(changes):
    with pytest.raises(context.FmpContextError):
        qualify_lookup(**changes)


def test_market_cap_preserves_exact_numeric_token_and_is_issuer_amount_not_denominator():
    result = qualify_cap(raw=b'[{"symbol":"SYN","date":"2023-01-13","marketCap":9007199254740993.125}]').to_payload()
    row = result["rows"][0]
    assert row["market_cap"]["lexical"] == "9007199254740993.125"
    assert row["market_cap"]["numerator"] == "72057594037927945"
    assert row["market_cap"]["denominator"] == "8"
    assert row["issuer_cik"] == "0000000001"
    assert result["same_class_shares"] is None and result["currency_from_current_context"] is None


def test_duplicate_cap_date_including_malformed_peer_never_chooses_good_copy():
    value = qualify_cap(raw=b'[{"symbol":"SYN","date":"2023-01-13","marketCap":8},'
        b'{"symbol":"OTHER","date":"2023-01-13","marketCap":null}]').to_payload()
    assert all(row["status"] == "refused" for row in value["rows"])


@pytest.mark.parametrize("raw", [b'[{"symbol":"SYN","date":"2026-09-01","marketCap":1}]',
                                 b'[{"symbol":"SYN","date":"2023-01-13suffix","marketCap":1}]'])
def test_protected_and_unrecognizable_cap_dates_refuse(raw):
    with pytest.raises(context.cap.FmpCapError):
        qualify_cap(raw=raw)


def test_lookup_must_physically_precede_cap_request():
    with pytest.raises(context.FmpContextError, match="precede_cap"):
        qualify_cap(started_at=START)


def test_same_date_exact_issuer_and_USD_request_target_can_bind_candidate_without_count_or_execution():
    result = context.bind_dated_issuer_cap(qualify_cap(), dated()).to_payload()
    assert result["bindings"][0]["status"] == "dated_issuer_USD_cap_source_candidate"
    assert result["bindings"][0]["same_class_shares"] is None
    assert result["current_metadata_backdated"] is False
    assert result["authority"]["market_cap_admitted"] is False


@pytest.mark.parametrize("changes,reason", [({"cik": "0000000002"}, "daily_issuer_CIK_missing_or_mismatched"),
    ({"cik": None}, "daily_issuer_CIK_missing_or_mismatched"),
    ({"currency_name": "eur"}, "same_date_request_target_USD_not_independently_observed"),
    ({"ticker": "OLDALIAS"}, "same_date_request_target_USD_not_independently_observed")])
def test_current_lookup_metadata_or_same_issuer_other_alias_cannot_supply_historical_USD(changes, reason):
    result = context.bind_dated_issuer_cap(qualify_cap(), dated([daily_row(**changes)])).to_payload()
    assert result["bindings"][0]["status"] == "refused"
    assert reason in result["bindings"][0]["refusal_reasons"]


def test_dated_identity_is_never_projected_over_future_or_missing_daily_dates():
    result = context.bind_dated_issuer_cap(qualify_cap(), dated(at="2023-01-31")).to_payload()
    assert "same_date_cap_missing_or_ambiguous" in result["bindings"][0]["refusal_reasons"]


def test_same_issuer_secondary_class_can_use_issuer_size_never_primary_class_shares():
    second = daily_row(ticker="SECOND", composite_figi="BBG000000003", share_class_figi="BBG000000004")
    unrelated = daily_row(ticker="OTHER", composite_figi="BBG000000005", share_class_figi="BBG000000006", cik="0000000002")
    result = context.bind_dated_issuer_cap(qualify_cap(), dated([daily_row(), second, unrelated])).to_payload()
    assert len(result["bindings"]) == 2 and result["complete_daily_identity_source_row_count"] == 3
    assert all(row["status"] == "dated_issuer_USD_cap_source_candidate" and row["same_class_shares"] is None
               for row in result["bindings"])


@pytest.mark.parametrize("factory", [ticket, qualify_lookup, qualify_cap,
    lambda: context.bind_dated_issuer_cap(qualify_cap(), dated())])
def test_reports_are_detached_sealed_and_cannot_authorize_actual_execution(factory):
    value = factory()
    original = value.to_bytes()
    payload = value.to_payload()
    payload["authority"]["qc_authorized"] = True
    assert value.to_bytes() is original
    with pytest.raises(context.FmpContextError, match="actual_execution"):
        value.require_actual_execution()
    object.__setattr__(value, "_bytes", canonical_json(payload).encode())
    with pytest.raises(context.FmpContextError, match="sealed_context"):
        value.to_bytes()


def test_plan_is_exact_finite_two_stage_budget_and_refuses_duplicate_selection():
    source = ticket()
    plan = context.freeze_context_plan((source,)).to_payload()
    assert plan["maximum_requests"] == 2
    assert plan["maximum_total_bytes"] == 9 * 1024 * 1024
    assert plan["maximum_rows"] == 5050
    with pytest.raises(context.FmpContextError, match="unique"):
        context.freeze_context_plan((source, source))
