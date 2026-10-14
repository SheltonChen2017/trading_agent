"""Source-free daily-active evidence; no provider/private input."""
from datetime import date
import io
import json
import zipfile
import pytest
from data.exchange_calendar import trading_sessions
from data.hashing import canonical_json, hash_bytes
import research.short_interest_etf.native_dated_identity as old
import research.short_interest_etf.sharadar_securities_master as master
import research.short_interest_etf.native_daily_active_reference as source

SESSIONS = tuple(at.isoformat() for at in trading_sessions(date(2022, 1, 3), date(2026, 8, 31)))
BEGIN, END = "2026-10-14T00:00:00Z", "2026-10-14T00:00:01Z"

def plan():
    return source.freeze_daily_active_plan(SESSIONS, calendar_sha256="a" * 64)

def index(extra=""):
    raw = ("table,permaticker,ticker,exchange,isdelisted,category,figi\n"
        "stocks,1,SYN,XNYS,N,Domestic Common Stock Primary Class,BBG000000001\n" + extra)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as zipped:
        zipped.writestr("tickers.csv", raw)
    return old.build_composite_native_index(master.CapturedSharadarMasterArchive("tickers", output.getvalue(),
                                             master.request_sha256("download-tickers")))

def row(**changes):
    value = {"ticker": "SYN", "composite_figi": "BBG000000001", "share_class_figi": "BBG000000002",
        "locale": "us", "market": "stocks", "type": "CS", "active": True,
        "primary_exchange": "XNYS", "currency_name": "usd", "cik": "0000000001"}
    value.update(changes)
    return value

def body(rows=None, following=None):
    value = {"status": "OK", "results": [row()] if rows is None else rows}
    if following is not None:
        value["next_url"] = following
    return canonical_json(value).encode()

def captured(raw=None, ordinal=1, url=None, at=None, began=BEGIN, received=END):
    return source.CapturedDailyActiveReferencePage(SESSIONS[0] if at is None else at, ordinal,
        source.first_url(plan(), 1) if url is None else url, body() if raw is None else raw,
        began, received, 200, "application/json")

def qualify(pages=None, original=None, day_ordinal=1, started_at=BEGIN, retrieved_at=END):
    return source.qualify_daily_active_reference(plan(), day_ordinal, (captured(),) if pages is None else pages,
        index() if original is None else original, started_at=started_at, retrieved_at=retrieved_at)

def test_exact_full_plan_and_distinct_active_only_source_report():
    frozen = plan().to_payload()
    assert frozen["day_count"] == 1169 and frozen["maximum_requests"] == 74816
    assert frozen["maximum_total_bytes"] == 4 * 1024 ** 3 and frozen["maximum_rows"] == 74816000
    assert frozen["maximum_concurrent_day_chains"] == 8
    result = qualify()
    value = result.to_payload()
    assert type(result) is source.DailyActiveReferenceQualification and type(result) is not old.DatedIdentityQualification
    record = dict(zip(source.ROW_FIELDS, value["rows"][0], strict=True))
    assert record["provider_security_id"] == "sharadar:permaticker:1" and record["refusal_reasons"] == []
    assert record["share_class_figi"] == "BBG000000002" and record["currency_name"] == "usd"
    assert record["primary_exchange"] == "XNYS" and record["cik"] == "0000000001"
    assert value["active_panel_only"] is True and value["inactive_panel_captured"] is False
    assert value["page_origins"][0]["raw_sha256"] == hash_bytes(captured().raw)
    assert value["authority"]["issuer_domicile_assertion"] is None
    assert value["authority"]["full_listing_lifecycle_coverage_proven"] is False
    assert value["authority"]["outcome_looks"] == value["authority"]["qc_attempts"] == 0

@pytest.mark.parametrize("sessions", [SESSIONS[:-1], SESSIONS[::-1], SESSIONS[:-1] + ("2026-09-01",),
    SESSIONS[:-1] + (SESSIONS[-2],), ("2022-01-03",), ()])
def test_partial_reordered_protected_or_duplicate_calendar_cannot_freeze(sessions):
    with pytest.raises(source.DailyActiveReferenceError):
        source.freeze_daily_active_plan(sessions, calendar_sha256="a" * 64)

@pytest.mark.parametrize("changes,reason", [({"active": False}, "source_active_panel_assertion_conflict"),
    ({"locale": "ca"}, "outside_dated_US_market_common_stock"), ({"market": "otc"}, "outside_dated_US_market_common_stock"),
    ({"type": "ETF"}, "outside_dated_US_market_common_stock"),
    ({"primary_exchange": "OTCM"}, "dated_primary_MIC_nonlisting_namespace"),
    ({"primary_exchange": "IEXG"}, "dated_primary_MIC_outside_finite_qualified_namespace"),
    ({"primary_exchange": None}, "dated_primary_listing_MIC_missing"),
    ({"currency_name": "eur"}, "dated_USD_currency_name_not_observed"),
    ({"currency_name": None}, "dated_USD_currency_name_not_observed"),
    ({"cik": None}, "positive_dated_CIK_missing_or_malformed"),
    ({"cik": "0000000000"}, "positive_dated_CIK_missing_or_malformed"),
    ({"cik": "1"}, "positive_dated_CIK_missing_or_malformed"),
    ({"cik": 1}, "positive_dated_CIK_missing_or_malformed"),
    ({"last_updated_utc": "2022-01-03"}, "malformed_optional_identity_clock"),
    ({"shares_outstanding": 100}, "unknown_source_row_fields"),
    ({"composite_figi": None}, "missing_or_malformed_dated_identity_fields"),
    ({"share_class_figi": "1"}, "missing_or_malformed_dated_identity_fields")])
def test_missing_malformed_or_outside_source_fields_retained_not_transferred(changes, reason):
    record = qualify((captured(body([row(**changes)])),)).to_payload()["rows"][0]
    assert record[:2] == [1, 0] and record[5] is None and reason in record[-1]

def test_duplicate_row_keys_fence_all_identifiable_ticker_tokens():
    first = canonical_json(row()).replace('"ticker":"SYN"', '"ticker":"SYN","ticker":"OTHER"')
    second = canonical_json(row(ticker="OTHER", composite_figi="BBG000000003", share_class_figi="BBG000000004"))
    raw = ('{"status":"OK","results":[' + first + ',' + second + ']}').encode()
    rows = qualify((captured(raw),), index("stocks,2,OTHER,XNYS,N,Domestic Common Stock Primary Class,BBG000000003\n")).to_payload()["rows"]
    assert all(record[5] is None for record in rows)
    assert "duplicate_source_row_JSON_key" in rows[0][-1]
    assert all("duplicate_or_malformed_dated_ticker_peers_quarantined" in record[-1] for record in rows)

def test_malformed_peer_in_later_page_fences_original_and_chain_origins_retained():
    following = source.ENDPOINT + "?cursor=fabricated"
    result = qualify((captured(body(following=following)), captured(body([row(ticker=" SYN ")]), 2,
                     following, began=END, received=END))).to_payload()
    assert all(record[5] is None for record in result["rows"])
    assert [record[:2] for record in result["rows"]] == [[1, 0], [2, 0]]
    assert len(result["page_origins"]) == 2

def test_duplicate_composite_with_aliases_is_ambiguous_not_native_price_alias_admission():
    rows = qualify((captured(body([row(), row(ticker="ALIAS")])),)).to_payload()["rows"]
    assert all(record[5] is None and "duplicate_or_malformed_dated_composite_peers_quarantined" in record[-1] for record in rows)

def test_missing_native_class_peer_never_transfers_identity_or_FIGI():
    rows = qualify((captured(body([row(), row(ticker="OTHER", composite_figi="BBG000000009")])),)).to_payload()["rows"]
    assert all(record[5] is None and "dated_class_native_missing_or_conflicting" in record[-1] for record in rows)

def test_current_update_clock_retained_not_historical_availability():
    value = qualify((captured(body([row(last_updated_utc=END)])),)).to_payload()
    assert value["rows"][0][14] == END and value["rows"][0][-1] == []
    assert value["authority"]["point_in_time_data"] is False and value["query_date"] == "2022-01-03"

@pytest.mark.parametrize("raw", [b'{"status":"OK","status":"OK","results":[]}',
    b'{"status":"OK","results":[],"count":NaN}', b'{"status":"OK","results":[],"count":true}',
    b'{"status":"OK","results":[],"count":1}', b'{"status":"OK","results":{},"unknown":1}', b'null', b'not JSON'])
def test_bad_envelope_cannot_obtain_complete_day(raw):
    with pytest.raises(source.DailyActiveReferenceError):
        qualify((captured(raw),))

@pytest.mark.parametrize("value", ["http://api.massive.com/v3/reference/tickers?cursor=x",
    "https://outside.invalid/v3/reference/tickers?cursor=x", source.ENDPOINT + "?cursor=x&date=2022-01-04",
    source.ENDPOINT + "?cursor=x&active=false", source.ENDPOINT + "?cursor=x&type=ETF",
    source.ENDPOINT + "?cursor=x&apiKey=fabricated", source.ENDPOINT + "?cursor=x&APIKEY=fabricated",
    source.ENDPOINT + "?cursor=x&cursor=y", source.ENDPOINT + "?cursor=x&locale=us"])
def test_cursor_cannot_change_date_panel_or_transmit_secret(value):
    with pytest.raises(source.DailyActiveReferenceError):
        source.next_url(value, SESSIONS[0])

@pytest.mark.parametrize("pages", [(), (captured(ordinal=2),), (captured(at="2022-01-04"),),
    (captured(body(following=source.ENDPOINT + "?cursor=fabricated")),),
    (captured(), captured(ordinal=2, url=source.ENDPOINT + "?cursor=fabricated", began=END, received=END))])
def test_missing_unfinished_wrong_date_or_extra_chain_is_not_complete(pages):
    with pytest.raises(source.DailyActiveReferenceError):
        qualify(pages)

def test_only_one_actual_panel_without_prices_can_be_complete_empty():
    value = qualify((captured(body([])),)).to_payload()
    assert value["rows"] == [] and value["complete_actual_active_chain"] is True and value["inactive_panel_captured"] is False
    query = source.request_descriptor(plan(), 1)["params"]
    assert query["active"] == "true" and query["date"] == "2022-01-03" and "locale" not in query

def test_old_two_panel_type_is_not_accepted_and_raw_body_ceiling_is_enforced():
    old_page = old.CapturedDatedIdentityPage(SESSIONS[0], True, 1, source.first_url(plan(), 1), body(), BEGIN, END, 200, "application/json")
    with pytest.raises(source.DailyActiveReferenceError):
        qualify((old_page,))
    with pytest.raises(source.DailyActiveReferenceError):
        captured(b" " * (source.MAXIMUM_RESPONSE_BYTES + 1))

def test_reflection_cannot_reseal_page_or_mutate_report_after_stream_begins():
    page = captured()
    object.__setattr__(page, "raw", body([]))
    with pytest.raises(source.DailyActiveReferenceError, match="sealed_daily_active_capture"):
        page.__post_init__()
    report = qualify((captured(body([row(), row(ticker="SECOND", composite_figi="BBG000000003", share_class_figi="BBG000000004")])),),
        index("stocks,2,SECOND,XNYS,N,Domestic Common Stock Primary Class,BBG000000003\n"))
    stream = report.iter_rows()
    first = next(stream)
    assert type(first) is tuple and type(first[-1]) is tuple
    object.__setattr__(report, "_rows", (first,))
    with pytest.raises(source.DailyActiveReferenceError, match="sealed_daily_active_report"):
        next(stream)

def test_report_detached_payload_cannot_authorize_actual_execution():
    report = qualify()
    raw = report.to_bytes()
    value = report.to_payload()
    value["authority"]["actual_input_execution_admitted"] = True
    assert report.to_bytes() is raw
    with pytest.raises(source.DailyActiveReferenceError, match="actual_execution"):
        report.require_actual_execution()

def test_report_and_serial_chain_chronology_verified():
    with pytest.raises(source.DailyActiveReferenceError, match="enclosing_serial_day"):
        qualify(started_at=END)
    with pytest.raises(source.DailyActiveReferenceError, match="day_report_chronology"):
        qualify(started_at=END, retrieved_at=BEGIN)

def test_escaped_unpaired_surrogate_is_retained_as_malformed_row_without_losing_valid_peers():
    first = canonical_json(row())
    bad = canonical_json(row(ticker="OTHER", composite_figi="BBG000000003", share_class_figi="BBG000000004"))
    bad = bad.replace('"ticker":"OTHER"', '"ticker":"\\ud800"')
    raw = ('{"status":"OK","results":[' + first + ',' + bad + ']}').encode()
    value = qualify((captured(raw),), index("stocks,2,OTHER,XNYS,N,Domestic Common Stock Primary Class,BBG000000003\n")).to_payload()
    assert value["rows"][0][5] == "sharadar:permaticker:1"
    assert value["rows"][1][2] is None and value["rows"][1][5] is None
    assert "missing_or_malformed_dated_identity_fields" in value["rows"][1][-1]
    assert value["rows"][1][:2] == [1, 1]

def test_same_native_multiple_composites_cannot_create_a_surviving_third_class_peer():
    # A caller cannot manufacture a valid current index mapping two unique
    # composites onto one native: the ORIGINAL master factory quarantines it.
    extra = ("stocks,2,OTHER,XNYS,N,Domestic Common Stock Primary Class,BBG000000003\n"
             "stocks,1,ALIAS,XNYS,N,Domestic Common Stock Primary Class,BBG000000005\n")
    source_index = index(extra)
    assert source_index.lookup("BBG000000001")[0][2] is None
    assert source_index.lookup("BBG000000005")[0][2] is None
    rows = [row(), row(ticker="SYN", composite_figi="BBG000000003", share_class_figi="BBG000000004"),
            row(ticker="ALIAS", composite_figi="BBG000000005")]
    result = qualify((captured(body(rows)),), source_index).to_payload()["rows"]
    assert all(record[5] is None for record in result)
    assert "original_native_composite_owner_missing_or_ambiguous" in result[2][-1]

def test_third_same_class_different_native_peer_is_fenced_before_or_after_global_alias_collision():
    extra = ("stocks,2,OTHER,XNYS,N,Domestic Common Stock Primary Class,BBG000000003\n"
             "stocks,3,THIRD,XNYS,N,Domestic Common Stock Primary Class,BBG000000005\n")
    rows = [row(), row(ticker="SYN", composite_figi="BBG000000003", share_class_figi="BBG000000004"),
            row(ticker="THIRD", composite_figi="BBG000000005")]
    result = qualify((captured(body(rows)),), index(extra)).to_payload()["rows"]
    assert all(record[5] is None for record in result)
    assert "dated_class_native_missing_or_conflicting" in result[2][-1]
