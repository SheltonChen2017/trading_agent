"""Fabricated local pages only; no provider, key, actual source or outcomes."""
from decimal import Decimal
from fractions import Fraction
import json

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_monthly_market_qualification as market


NOW = "2026-10-14T01:00:00Z"
LATER = "2026-10-14T01:00:04Z"


def row(ticker="FABRICATED.UNRELATED", table="stocks", at="2022-01-03", **changes):
    value = {"ticker": ticker, "date": at, "lastupdated": "2026-10-13"}
    if table == "stocks":
        value.update(open=3, high=4, low=2, close=3, volume=1, closeunadj=2)
    else:
        value.update(marketcap=12)
    value.update(changes)
    return value


def page(rows=(), *, table="stocks", month="2022-01", number=0, attempt=1,
         started=NOW, received=NOW, raw=None, **changes):
    raw = json.dumps({"count": len(rows), "data": list(rows)}, separators=(",", ":")).encode() if raw is None else raw
    descriptor = market.inputs.page_request(table, month, number)
    fields = {"page_number": number, "attempt": attempt, "request_json": canonical_json(descriptor),
        "request_sha256": hash_payload(descriptor), "raw": raw, "source_file_sha256": hash_bytes(raw),
        "started_at": started, "received_at": received}
    fields.update(changes)
    return market.CapturedMonthlyMarketPage(**fields)


def qualify(pages, *, table="stocks", month="2022-01"):
    return market.qualify_monthly_market_panel(table, month, pages, retrieved_at=LATER)


def amount(value):
    return Fraction(value["numerator"], value["denominator"])


@pytest.fixture(scope="module")
def full_rows():
    return tuple(row(f"FABRICATED{i:05d}") for i in range(10000))


def test_exact_original_112_panel_protocol_without_pilot_symbols():
    protocol = market.inputs.market_input_protocol()
    assert len(protocol["panels"]) == 112 and protocol["months"] == 56
    assert hash_payload(protocol) == market.CAPTURE_PROTOCOL_SHA256
    report = qualify((page((row(at="2024-05-17"),), month="2024-05"),), month="2024-05")
    assert report.to_payload()["rows"][0]["normalized"]["ticker"] == "FABRICATED.UNRELATED"
    assert report.public_summary()["authority"]["source_admitted"] is False


def test_raw_OHLC_and_fractional_volume_are_exact_without_rounding():
    value = qualify((page((row(),)),)).to_payload()
    normalized = value["rows"][0]["normalized"]
    assert amount(normalized["raw_open"]) == amount(normalized["raw_close"]) == 2
    assert amount(normalized["raw_high"]) == Fraction(8, 3)
    assert amount(normalized["raw_low"]) == Fraction(4, 3)
    assert amount(normalized["raw_volume"]) == Fraction(3, 2)
    assert value["rows"][0]["lastupdated_revision_metadata"] == "2026-10-13"
    assert value["lastupdated_semantic"] == "revision_metadata_not_public_availability"
    assert value["global_historical_controls_authenticated_by_this_layer"] is False


def test_decimal_lexeme_retains_all_digits_and_daily_issuer_cap_units():
    raw = json.dumps({"count": 1, "data": [row(open="MARK", low=0.05, close=1, high=1, closeunadj=3)]}).encode()
    raw = raw.replace(b'"MARK"', b"0.10000000000000000001")
    normalized = qualify((page(raw=raw),)).to_payload()["rows"][0]["normalized"]
    assert amount(normalized["raw_open"]) == Fraction(30000000000000000003, 100000000000000000000)
    cap = qualify((page((row(table="daily", marketcap=12),), table="daily"),), table="daily").to_payload()["rows"][0]["normalized"]
    assert amount(cap["issuer_market_cap_USD"]) == 12000000
    assert cap["same_class_shares"] is None and cap["provider_units"] == "USD_millions"


@pytest.mark.parametrize("value", (True, False, 1.2, "1.2", None, Decimal("1"), Fraction(1, 2), float("nan"), float("inf")))
def test_non_exact_numeric_types_cannot_reach_fraction(value):
    with pytest.raises(market.MonthlyMarketQualificationError, match="exact_lexical_JSON_number"):
        market._number(value)


@pytest.mark.parametrize("value", (market.inputs.NumberToken("1e1000000000"), market.inputs.NumberToken("1e-1000000000"),
    market.inputs.NumberToken("1" * 129), 10 ** 31))
def test_numeric_bounds_precede_fraction_expansion(monkeypatch, value):
    monkeypatch.setattr(market, "Fraction", lambda *args: pytest.fail("expanded a refused numeric token"))
    with pytest.raises(market.MonthlyMarketQualificationError):
        market._number(value)


@pytest.mark.parametrize("changes", ({"close": True}, {"volume": "1.2"}, {"volume": -1}, {"close": 0},
    {"low": 5}, {"lastupdated": "not-a-date"}, {"high": None}))
def test_malformed_financial_rows_are_retained_with_origin_not_normalized(changes):
    report = qualify((page((row(**changes),)),)).to_payload()
    value = report["rows"][0]
    assert value["normalized"] is None and value["refusal_reasons"]
    assert value["source_origin"]["attempt"] == 1 and value["source_origin"]["row_index"] == 0


@pytest.mark.parametrize("at", ("2022-02-01", "2026-09-01", "2022-01-03T00:00:00Z", "private-source-value"))
def test_outside_or_unbound_dates_refuse_before_financial_normalization(monkeypatch, at):
    source = page((row(at=at),))
    monkeypatch.setattr(market, "_normalize", lambda *args: pytest.fail("financial normalization reached"))
    with pytest.raises(market.MonthlyMarketQualificationError, match="page_envelope_scope_or_order") as result:
        qualify((source,))
    assert at not in str(result.value)


@pytest.mark.parametrize("raw", (b'{"count":0,"count":0,"data":[]}', b'{"count":true,"data":[]}',
    b'{"count":0,"data":[],"next_url":"https://fabricated.invalid"}', b'{"count":0,"data":[],"x":NaN}'))
def test_duplicate_keys_nonfinite_and_wrong_envelopes_never_qualify(raw):
    with pytest.raises(market.MonthlyMarketQualificationError):
        qualify((page(raw=raw),))


def test_cross_page_duplicate_quarantines_valid_and_malformed_copies(full_rows):
    first = page(full_rows)
    second = page((row(" FABRICATED00000 ", close="quoted-number"),), number=1, attempt=2)
    records = qualify((first, second)).to_payload()["rows"]
    for index in (0, 10000):
        assert records[index]["normalized"] is None
        assert "all_identifiable_duplicate_peers_quarantined" in records[index]["refusal_reasons"]
    assert records[1]["normalized"] is not None
    assert records[10000]["identifiable_grouping_key"] == records[0]["identifiable_grouping_key"]
    assert records[0]["source_origin"]["source_file_sha256"] == first.source_file_sha256
    assert records[10000]["source_origin"]["source_file_sha256"] == second.source_file_sha256


def test_final_full_page_is_not_exhaustion(full_rows):
    with pytest.raises(market.MonthlyMarketQualificationError, match="final_short_page_exhaustion"):
        qualify((page(full_rows),))


def test_short_page_cannot_have_successor():
    with pytest.raises(market.MonthlyMarketQualificationError, match="only_full_page_may_have_successor"):
        qualify((page((row(),)), page(number=1, attempt=2)))


def test_exact_contiguous_offsets_and_attempts(full_rows):
    with pytest.raises(market.MonthlyMarketQualificationError, match="contiguous_original_attempts"):
        qualify((page(full_rows, attempt=5), page(number=1, attempt=7)))
    with pytest.raises(market.MonthlyMarketQualificationError, match="exact_contiguous_panel_request"):
        qualify((page(number=1),))
    descriptor = market.inputs.page_request("stocks", "2022-01", 0)
    descriptor["params"]["ticker"] = "FABRICATED"
    with pytest.raises(market.MonthlyMarketQualificationError, match="exact_contiguous_panel_request"):
        qualify((page(request_json=canonical_json(descriptor), request_sha256=hash_payload(descriptor)),))


def test_real_clocks_not_rewritten_or_reordered(full_rows):
    with pytest.raises(market.MonthlyMarketQualificationError, match="page_receipt_chronology"):
        page(started=LATER, received=NOW)
    first = page(full_rows, received="2026-10-14T01:00:02Z")
    second = page(number=1, attempt=2, started="2026-10-14T01:00:01Z", received="2026-10-14T01:00:03Z")
    with pytest.raises(market.MonthlyMarketQualificationError, match="serial_panel_and_retrieval"):
        qualify((first, second))
    with pytest.raises(market.MonthlyMarketQualificationError, match="serial_panel_and_retrieval"):
        market.qualify_monthly_market_panel("stocks", "2022-01", (page(received=LATER),), retrieved_at=NOW)


@pytest.mark.parametrize("changes", ({"page_number": True}, {"attempt": True}, {"attempt": 7169},
    {"page_number": 64}, {"http_status": True}, {"http_status": 404}, {"content_type": "text/html"},
    {"source_file_sha256": "a" * 64}, {"started_at": "2026-10-14T01:00:00"}))
def test_capture_bounds_types_status_media_hash_and_UTC(changes):
    with pytest.raises(market.MonthlyMarketQualificationError):
        page(**changes)


def test_frozen_protocol_and_exact_capture_tuple_required(monkeypatch):
    source = page()
    for pages in ([], (source,) * 65, (object(),)):
        with pytest.raises(market.MonthlyMarketQualificationError):
            qualify(pages)
    monkeypatch.setattr(market.inputs, "PAGE_LIMIT", 1)
    with pytest.raises(market.MonthlyMarketQualificationError, match="frozen_monthly_capture_protocol_changed"):
        qualify((source,))


def test_private_payload_detaches_and_repr_public_summary_are_redacted():
    source = page((row(),))
    report = qualify((source,))
    original = report.to_bytes()
    payload = report.to_payload()
    payload["rows"][0]["normalized"]["raw_open"]["numerator"] = 999
    payload["authority"]["source_admitted"] = True
    assert report.to_bytes() == original and report.sha256 == hash_bytes(original)
    assert "FABRICATED.UNRELATED" not in repr(source) + repr(report) + repr(report.public_summary())
    assert set(report.public_summary()) == {"schema", "pages", "attempts", "authority"}
    assert all(value is False for key, value in report.public_summary()["authority"].items()
        if key.endswith("admitted") or key.endswith("authorized"))


def test_reflected_page_mutation_cannot_be_reanchored_or_hidden_by_old_report():
    source = page((row(),))
    report = qualify((source,))
    object.__setattr__(source, "raw", b"changed")
    with pytest.raises(market.MonthlyMarketQualificationError, match="sealed_monthly_capture_changed"):
        source.__post_init__()
    with pytest.raises(market.MonthlyMarketQualificationError, match="sealed_monthly_capture_changed"):
        report.to_bytes()


def test_report_reflection_and_direct_construction_never_lift_authority():
    with pytest.raises(market.MonthlyMarketQualificationError, match="factory_required"):
        market.MonthlyMarketQualification()
    report = qualify((page(),))
    object.__setattr__(report, "_json", "{}")
    with pytest.raises(market.MonthlyMarketQualificationError, match="sealed_monthly_qualification_changed"):
        report.to_payload()


def test_incremental_report_budget_counts_utf8_before_final_serialization(monkeypatch):
    source = page((row(lastupdated="\U0001f600" * 300000),))
    monkeypatch.setattr(market, "MAXIMUM_REPORT_BYTES", 3 * 1024 ** 2)
    original = market.canonical_json
    def serialized(value):
        if type(value) is dict and value.get("schema") == market.SCHEMA:
            pytest.fail("oversized Unicode report reached final serialization")
        return original(value)
    monkeypatch.setattr(market, "canonical_json", serialized)
    with pytest.raises(market.MonthlyMarketQualificationError, match="bounded_private_panel_report_required"):
        qualify((source,))
