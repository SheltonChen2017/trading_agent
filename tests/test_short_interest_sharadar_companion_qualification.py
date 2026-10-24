"""Fabricated direct-Sharadar responses; no market or outcome observations."""
from __future__ import annotations

import copy
from dataclasses import replace
from decimal import localcontext
from fractions import Fraction

import pytest

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.sharadar_companion_qualification import (
    CapturedSharadarResponse,
    FIELDS,
    PROTOCOL_SHA256,
    REQUEST_IDS,
    SYMBOLS,
    TABLES,
    SharadarCompanionQualification,
    SharadarCompanionQualificationError,
    qualification_protocol,
    qualify_sharadar_companion,
    request_sha256,
    sharadar_request,
    validate_sharadar_metadata,
    validate_sharadar_schema,
)


RETRIEVED_AT = "2026-10-11T12:00:00Z"


def capture(request_id, value, *, raw=None):
    blob = canonical_json(value).encode("utf-8") if raw is None else raw
    content = "text/plain; charset=utf-8" if request_id.startswith("schema-") else "application/json; charset=utf-8"
    return CapturedSharadarResponse(request_id, request_sha256(request_id), blob, content)


def documents():
    docs = {}
    for table in TABLES:
        docs["metadata-" + table] = {"table": table, "name": table + ".csv.zip", "size": 1234,
                                     "sizeLabel": "1.2 KB", "modified": "2026-10-10T03:00:00+00:00"}
        columns = [field + " TEXT" for field in FIELDS[table]]
        docs["schema-" + table] = ("-- Public schema fixture\nCREATE TABLE IF NOT EXISTS " + table + " (\n" + ",\n".join(columns) + ");\n").encode()
    rows = {
        "descriptions": [{"table": "actiontypes", "indicator": "split", "title": "Stock split", "description": "Fixture split ratio description", "unittype": "ratio", "isprimarykey": "N", "isfilter": "N"}],
        "tickers": [{"table": "stocks", "permaticker": 12345, "ticker": "AAPL", "exchange": "NASDAQ", "isdelisted": "N", "category": "Domestic Common Stock", "siccode": 3571, "sicsector": "Manufacturing", "figi": "BBG000000001", "sector": "Technology", "currency": "USD", "location": "California; U.S.A", "lastupdated": "2026-10-10", "firstpricedate": "2000-01-03", "lastpricedate": "2026-10-09"}],
        "stocks": [{"ticker": "AAPL", "date": "2023-03-01", "open": 10, "high": 12, "low": 8, "close": 9, "volume": 7, "closeunadj": 6, "lastupdated": "2026-10-10"}],
        "actions": [{"date": "2023-03-01", "action": "split", "ticker": "AAPL", "name": "Fixture Inc", "value": 2, "contraticker": None, "contraname": None}],
        "daily": [{"ticker": "AAPL", "date": "2023-03-01", "marketcap": 12, "lastupdated": "2026-10-10"}],
        "fundamentals": [{"ticker": "AAPL", "dimension": "ARQ", "calendardate": "2022-12-31", "date": "2023-02-01", "reportperiod": "2022-12-31", "sharesbas": 100000, "sharefactor": 1, "marketcap": 50000000, "lastupdated": "2026-10-10"}],
    }
    for table, values in rows.items():
        docs["rows-" + table] = {"count": len(values), "data": values}
    return docs


def captures(docs=None):
    docs = documents() if docs is None else docs
    return tuple(capture(request_id, None, raw=docs[request_id]) if request_id.startswith("schema-")
                 else capture(request_id, docs[request_id]) for request_id in REQUEST_IDS)


def report(docs=None):
    return qualify_sharadar_companion(captures(docs), retrieved_at=RETRIEVED_AT)


def table_payload(payload, table):
    return next(row for row in payload["tables"] if row["table"] == table)


def normalized(payload, table):
    return table_payload(payload, table)["rows"][0]["normalized"]


def test_exact_protocol_and_requests_detach_without_secret_or_authority():
    protocol = qualification_protocol()
    assert PROTOCOL_SHA256 == "8540ea0adecf781db0323490beed1cf514fa57f92bafe06fbcce11a5569158b4"
    assert hash_payload(protocol) == PROTOCOL_SHA256
    assert len(protocol["requests"]) == 16
    assert protocol["request_ids"] == list(REQUEST_IDS)
    assert protocol["maximum_requests"] == 16 and protocol["automatic_retries"] == 0
    assert protocol["candidate_symbols"] == list(SYMBOLS)
    assert "api_key" not in canonical_json(protocol)
    assert "rights_verified" not in canonical_json(protocol)
    protocol["requests"][0]["params"]["years"] = "5"
    protocol["authority"]["source_admitted"] = True
    assert hash_payload(qualification_protocol()) == PROTOCOL_SHA256


@pytest.mark.parametrize("request_id", REQUEST_IDS)
def test_all_public_request_descriptors_are_exact_and_hash_bound(request_id):
    descriptor = sharadar_request(request_id)
    assert request_sha256(request_id) == hash_payload(descriptor)
    assert descriptor["method"] == "GET"
    assert descriptor["url"].startswith("https://api.sharadar.com/v1.0/")
    assert all("key" not in name for name in descriptor["params"])
    descriptor["params"]["secret"] = "fabricated"
    assert "secret" not in sharadar_request(request_id)["params"]


def test_dictionary_public_schema_spelling_and_filter_discrepancy_are_explicit():
    request = sharadar_request("rows-descriptions")
    assert request["params"]["tablename"] == "actiontypes"
    assert request["params"]["fields"] == "table,indicator,title,description,unittype,isprimarykey,isfilter"
    assert request["params"]["sort"] == "indicator.asc"


def test_provider_identifiers_and_exact_raw_imputation_do_not_fake_FIGI_or_round_volume():
    payload = report().to_payload()
    ticker = normalized(payload, "tickers")
    assert ticker["provider_security_id"] == "sharadar:permaticker:12345"
    assert ticker["composite_figi_assertion"] == "BBG000000001"
    assert ticker["share_class_figi"] is None
    assert ticker["effective_historical_mapping_admitted"] is False
    stock = normalized(payload, "stocks")
    assert stock["raw_open"] == {"numerator": 20, "denominator": 3}
    assert stock["raw_volume"] == {"numerator": 21, "denominator": 2}
    assert stock["raw_close"] == {"numerator": 6, "denominator": 1}


def test_daily_million_units_are_distinct_from_fundamental_USD():
    payload = report().to_payload()
    assert normalized(payload, "daily")["market_cap_USD"] == {"numerator": 12000000, "denominator": 1}
    assert normalized(payload, "fundamentals")["market_cap_USD"] == {"numerator": 50000000, "denominator": 1}
    assert normalized(payload, "fundamentals")["date_key"] == "2023-02-01"
    assert normalized(payload, "fundamentals")["calendardate"] == "2022-12-31"
    assert normalized(payload, "fundamentals")["same_share_class_denominator_admitted"] is False


def test_report_detaches_but_always_retains_private_zero_authority_and_missing_names():
    receipt = report()
    payload = receipt.to_payload()
    assert payload["publication_scope"] == "private_only_not_data_usability_publication"
    assert payload["authority"]["source_only"] is True
    assert all(value is False for key, value in payload["authority"].items()
               if key not in {"source_only", "actual_outcome_looks", "allocated_alpha", "qc_attempts"})
    assert payload["authority"]["actual_outcome_looks"] == 0
    assert payload["authority"]["qc_attempts"] == 0
    for name in TABLES:
        cells = table_payload(payload, name)["requested_symbol_cells"]
        assert [row["ticker"] for row in cells] == list(SYMBOLS)
        assert next(row for row in cells if row["ticker"] == "FB")["status"] == "missing"
        assert next(row for row in cells if row["ticker"] == "META")["status"] == "missing"
    digest = payload.pop("report_sha256")
    assert hash_payload(payload) == digest == receipt.sha256
    payload["tables"].clear()
    assert len(receipt.to_payload()["tables"]) == 6


def test_decimal_lexical_numbers_are_exact_under_low_ambient_precision():
    values = list(captures())
    index = REQUEST_IDS.index("rows-stocks")
    raw = b'{"count":1,"data":[{"ticker":"AAPL","date":"2023-03-01","open":1.23456789,"high":2,"low":1,"close":1.5,"volume":7.25,"closeunadj":2.25,"lastupdated":"2026-10-10"}]}'
    values[index] = capture("rows-stocks", None, raw=raw)
    with localcontext() as context:
        context.prec = 2
        stock = normalized(qualify_sharadar_companion(tuple(values), retrieved_at=RETRIEVED_AT).to_payload(), "stocks")
    expected = Fraction("1.23456789") * Fraction("2.25") / Fraction("1.5")
    assert stock["raw_open"] == {"numerator": expected.numerator, "denominator": expected.denominator}
    assert stock["raw_volume"] == {"numerator": 29, "denominator": 6}


@pytest.mark.parametrize("table,changes", [
    ("stocks", {"close": 0}), ("stocks", {"closeunadj": 0}),
    ("stocks", {"open": "10"}), ("stocks", {"volume": True}),
    ("stocks", {"volume": -1}), ("stocks", {"high": 7}),
    ("stocks", {"ticker": "AAPL1"}), ("stocks", {"date": "2023-06-01"}),
    ("daily", {"marketcap": -1}), ("daily", {"marketcap": "12"}),
    ("fundamentals", {"dimension": "MRQ"}),
    ("fundamentals", {"date": "2021-12-31"}),
    ("fundamentals", {"reportperiod": "2023-03-31"}),
    ("fundamentals", {"sharesbas": 0}), ("fundamentals", {"sharefactor": 0}),
    ("tickers", {"table": "funds"}), ("tickers", {"permaticker": True}),
    ("tickers", {"permaticker": "00123"}), ("tickers", {"isdelisted": []}),
    ("tickers", {"siccode": True}), ("tickers", {"lastpricedate": "1999-01-01"}),
    ("descriptions", {"table": "actions"}), ("descriptions", {"isfilter": True}),
])
def test_invalid_rows_stay_named_refusals_without_zero_substitution(table, changes):
    docs = documents()
    docs["rows-" + table]["data"][0].update(changes)
    block = table_payload(report(docs).to_payload(), table)
    assert block["rows"] == []
    assert len(block["refusals"]) == 1 and block["refusals"][0]["status"] == "malformed"
    assert block["raw_row_count"] == 1


@pytest.mark.parametrize("table,value_field", [("stocks", "open"), ("daily", "marketcap"), ("actions", "value"), ("fundamentals", "sharesbas"), ("tickers", "currency"), ("descriptions", "unittype")])
@pytest.mark.parametrize("malformed_first", [False, True])
def test_identifiable_duplicate_malformed_peer_quarantines_every_collision(table, value_field, malformed_first):
    docs = documents()
    valid = docs["rows-" + table]["data"][0]
    bad = copy.deepcopy(valid)
    bad[value_field] = True
    docs["rows-" + table] = {"count": 2, "data": [bad, valid] if malformed_first else [valid, bad]}
    block = table_payload(report(docs).to_payload(), table)
    assert block["rows"] == []
    assert len(block["refusals"]) == 2
    assert {row["status"] for row in block["refusals"]} == {"duplicate"}


def test_null_numeric_companions_remain_unknown_and_zero_cash_is_not_imputed():
    docs = documents()
    docs["rows-daily"]["data"][0]["marketcap"] = None
    docs["rows-fundamentals"]["data"][0]["sharesbas"] = None
    docs["rows-fundamentals"]["data"][0]["sharefactor"] = None
    docs["rows-actions"]["data"][0]["value"] = None
    payload = report(docs).to_payload()
    assert normalized(payload, "daily")["market_cap_USD"] is None
    assert normalized(payload, "fundamentals")["sharesbas"] is None
    assert normalized(payload, "fundamentals")["sharefactor"] is None
    assert normalized(payload, "actions")["value"] is None
    assert normalized(payload, "actions")["payment_timestamp"] is None
    assert normalized(payload, "actions")["terminal_economics_admitted"] is False


def test_signed_opaque_actions_and_dictionary_absence_grant_no_economics():
    docs = documents()
    docs["rows-actions"]["data"][0].update(action="unqualified_action", value=-3)
    action = normalized(report(docs).to_payload(), "actions")
    assert action["value"] == {"numerator": -3, "denominator": 1}
    assert action["action_dictionary_definition_present"] is False
    assert action["terminal_economics_admitted"] is False


@pytest.mark.parametrize("table", ["stocks", "daily", "actions", "fundamentals", "tickers"])
def test_empty_complete_page_preserves_every_requested_symbol(table):
    docs = documents()
    docs["rows-" + table] = {"count": 0, "data": []}
    cells = table_payload(report(docs).to_payload(), table)["requested_symbol_cells"]
    assert len(cells) == 10 and {row["status"] for row in cells} == {"missing"}


@pytest.mark.parametrize("value", [
    {"count": 2, "data": []}, {"count": True, "data": []},
    {"count": 0, "data": {},}, {"count": 0, "data": [], "next_url": "https://example.invalid"},
])
def test_row_count_and_envelope_contract_refuse_incomplete_unknown_pages(value):
    docs = documents()
    docs["rows-stocks"] = value
    with pytest.raises(SharadarCompanionQualificationError):
        report(docs)


def test_limit_hit_cannot_claim_completion_even_with_count_equality():
    docs = documents()
    docs["rows-stocks"] = {"count": 5000, "data": [docs["rows-stocks"]["data"][0]] * 5000}
    with pytest.raises(SharadarCompanionQualificationError, match="completeness"):
        report(docs)


@pytest.mark.parametrize("raw", [b'{"count":0,"count":0,"data":[]}', b'{"count":0,"data":[NaN]}', b'{"count":0,"data":[Infinity]}', b'\xff', b'not JSON'])
def test_duplicate_keys_nonfinite_and_invalid_JSON_refuse(raw):
    values = list(captures())
    values[REQUEST_IDS.index("rows-stocks")] = capture("rows-stocks", None, raw=raw)
    with pytest.raises(SharadarCompanionQualificationError):
        qualify_sharadar_companion(tuple(values), retrieved_at=RETRIEVED_AT)


@pytest.mark.parametrize("changes", [{"table": "funds"}, {"name": "stocks-5Y.csv.zip"}, {"size": True}, {"size": -1}, {"modified": "2026-10-10T03:00:00"}, {"modified": "2026-10-12T00:00:00Z"}, {"account_id": "fabricated"}, {"available": 1}, {"history": "5y"}])
def test_metadata_rejects_wrong_table_filename_scalar_time_or_unknown_fields(changes):
    item = documents()["metadata-stocks"]
    item.update(changes)
    with pytest.raises(SharadarCompanionQualificationError):
        validate_sharadar_metadata(capture("metadata-stocks", item), retrieved_at=RETRIEVED_AT)


def test_metadata_documented_full_files_shape_has_no_entitlement_inference():
    single = documents()["metadata-actions"]
    item = {key: value for key, value in single.items() if key != "table"}
    item.update(history="full", historyLabel="Full History", available=False)
    payload = {"table": "actions", "files": [item]}
    result = validate_sharadar_metadata(capture("metadata-actions", payload), retrieved_at=RETRIEVED_AT)
    assert result["available_assertion"] is False
    assert result["entitlement_inferred"] is False
    assert result["historical_availability_inferred"] is False


def metadata_inventory(*, selected=True):
    base = documents()["metadata-stocks"]
    base.update(history="full", historyLabel="Full History", available=True)
    full = {key: value for key, value in base.items() if key != "table"}
    five = {**full, "history": "5y", "historyLabel": "5 Years", "name": "stocks-5Y.csv.zip", "size": 500}
    ten = {**full, "history": "10y", "historyLabel": "10 Years", "name": "stocks-10Y.csv.zip", "size": 900}
    payload = base if selected else {"table": "stocks"}
    return {**payload, "files": [five, ten, full]}


@pytest.mark.parametrize("selected", [False, True])
def test_metadata_inventory_selects_unique_matching_full_history_without_entitlement(selected):
    payload = metadata_inventory(selected=selected)
    result = validate_sharadar_metadata(capture("metadata-stocks", payload), retrieved_at=RETRIEVED_AT)
    assert result["file_name"] == "stocks.csv.zip"
    assert result["byte_size"] == 1234
    assert result["available_assertion"] is True
    assert result["entitlement_inferred"] is False
    assert result["historical_availability_inferred"] is False


@pytest.mark.parametrize("selected", [False, True])
def test_metadata_inventory_optional_opaque_key_is_bound_but_never_followed_or_emitted(selected):
    payload = metadata_inventory(selected=selected)
    for item in payload["files"]:
        item["key"] = "opaque-storage/" + item["name"]
    result = validate_sharadar_metadata(capture("metadata-stocks", payload), retrieved_at=RETRIEVED_AT)
    assert result["file_name"] == "stocks.csv.zip"
    assert "key" not in result
    assert "opaque-storage" not in canonical_json(result)
    assert result["entitlement_inferred"] is False


@pytest.mark.parametrize("value", ["", " leading-space", "new\nline", "x" * 513, 1, None, []])
def test_inventory_opaque_storage_key_requires_only_bounded_canonical_text(value):
    payload = metadata_inventory()
    payload["files"][0]["key"] = value
    with pytest.raises(SharadarCompanionQualificationError):
        validate_sharadar_metadata(capture("metadata-stocks", payload), retrieved_at=RETRIEVED_AT)


def test_opaque_inventory_storage_key_is_not_a_selected_top_field():
    payload = metadata_inventory()
    payload["key"] = "not-a-top-field"
    with pytest.raises(SharadarCompanionQualificationError):
        validate_sharadar_metadata(capture("metadata-stocks", payload), retrieved_at=RETRIEVED_AT)


@pytest.mark.parametrize("field,value", [("size", 1235), ("modified", "2026-10-10T04:00:00+00:00"), ("available", False), ("history", "5y"), ("name", "stocks-5Y.csv.zip"), ("sizeLabel", "different display size"), ("historyLabel", "Other History")])
def test_metadata_selected_top_full_item_must_exactly_match_inventory(field, value):
    payload = metadata_inventory()
    payload[field] = value
    with pytest.raises(SharadarCompanionQualificationError):
        validate_sharadar_metadata(capture("metadata-stocks", payload), retrieved_at=RETRIEVED_AT)


@pytest.mark.parametrize("changes", [{"size": True}, {"modified": "2026-10-10T00:00:00"}, {"modified": "2026-10-12T00:00:00Z"}, {"history": "unsupported"}, {"name": "funds-5Y.csv.zip"}, {"historyLabel": "Full History"}, {"available": "true"}, {"extra": "unknown"}])
def test_metadata_even_unselected_inventory_items_require_valid_exact_contract(changes):
    payload = metadata_inventory()
    payload["files"][0].update(changes)
    with pytest.raises(SharadarCompanionQualificationError):
        validate_sharadar_metadata(capture("metadata-stocks", payload), retrieved_at=RETRIEVED_AT)


@pytest.mark.parametrize("mutation", ["missing_full", "duplicate_full", "duplicate_five", "partial_top"])
def test_metadata_inventory_missing_duplicate_history_or_partial_selection_refuses(mutation):
    payload = metadata_inventory()
    if mutation == "missing_full":
        payload["files"].pop()
    elif mutation == "duplicate_full":
        payload["files"].append(copy.deepcopy(payload["files"][-1]))
    elif mutation == "duplicate_five":
        payload["files"].append(copy.deepcopy(payload["files"][0]))
    else:
        payload.pop("history")
    with pytest.raises(SharadarCompanionQualificationError):
        validate_sharadar_metadata(capture("metadata-stocks", payload), retrieved_at=RETRIEVED_AT)


@pytest.mark.parametrize("history,label,count", [("5y", "5 Years", 1), ("full", "Full History", 2), ("full", "Full History", 0)])
def test_wrong_or_multiple_metadata_history_shapes_refuse(history, label, count):
    item = documents()["metadata-actions"]
    item.pop("table")
    item.update(history=history, historyLabel=label, available=True)
    with pytest.raises(SharadarCompanionQualificationError):
        validate_sharadar_metadata(capture("metadata-actions", {"table": "actions", "files": [item] * count}), retrieved_at=RETRIEVED_AT)


@pytest.mark.parametrize("raw", [b'CREATE TABLE funds(ticker TEXT);', b'CREATE TABLE stocks(ticker TEXT);', b'CREATE TABLE stocks(ticker TEXT); DROP TABLE stocks;', b'CREATE TABLE stocks(ticker TEXT,ticker TEXT);'])
def test_public_schema_requires_expected_table_and_projected_declarations(raw):
    with pytest.raises(SharadarCompanionQualificationError):
        validate_sharadar_schema(capture("schema-stocks", None, raw=raw))


@pytest.mark.parametrize("tail", [
    b'CREATE TABLE funds(ticker TEXT);',
    b'CREATE INDEX wrong_table_idx ON funds (ticker);',
    b'CREATE INDEX bad_column_idx ON stocks (not_a_column);',
])
def test_schema_cannot_swallow_another_table_or_invalid_index_tail(tail):
    raw = documents()["schema-stocks"] + tail
    with pytest.raises(SharadarCompanionQualificationError):
        validate_sharadar_schema(capture("schema-stocks", None, raw=raw))


def test_schema_accepts_recognized_same_table_indexes_without_executing_them():
    raw = documents()["schema-stocks"] + b'CREATE INDEX IF NOT EXISTS "stocks_date_idx" ON "stocks" ("date");\n'
    assert validate_sharadar_schema(capture("schema-stocks", None, raw=raw))["SQL_executed"] is False


def test_multiple_distinct_permatickers_for_same_raw_ticker_are_private_identity_ambiguity():
    docs = documents()
    row = copy.deepcopy(docs["rows-tickers"]["data"][0])
    row["permaticker"] = 67890
    docs["rows-tickers"]["data"].append(row)
    docs["rows-tickers"]["count"] = 2
    block = table_payload(report(docs).to_payload(), "tickers")
    cell = next(item for item in block["requested_symbol_cells"] if item["ticker"] == "AAPL")
    assert cell["status"] == "ambiguous_identity"
    assert len(block["rows"]) == 2 and block["refusals"] == []
    assert all(item["normalized"]["effective_historical_mapping_admitted"] is False for item in block["rows"])


@pytest.mark.parametrize("changes", [{"request_id": "unknown"}, {"request_sha256": "a" * 64}, {"http_status": 204}, {"http_status": True}, {"content_type": "text/html"}, {"raw": b''}, {"raw": bytearray(b'{}')}])
def test_capture_binding_status_content_and_immutable_byte_contract(changes):
    value = captures()[0]
    with pytest.raises(SharadarCompanionQualificationError):
        replace(value, **changes)


@pytest.mark.parametrize("mutation", ["missing", "reordered", "duplicated", "list", "alien"])
def test_complete_exact_sixteen_response_order_is_required(mutation):
    values = list(captures())
    if mutation == "missing":
        values.pop()
    elif mutation == "reordered":
        values[0], values[1] = values[1], values[0]
    elif mutation == "duplicated":
        values[1] = values[0]
    elif mutation == "alien":
        values[0] = object()
    value = values if mutation == "list" else tuple(values)
    with pytest.raises(SharadarCompanionQualificationError):
        qualify_sharadar_companion(value, retrieved_at=RETRIEVED_AT)


def test_captured_raw_identity_mutation_cannot_be_rehashed_into_same_receipt():
    receipt = report()
    old = receipt.captures[-1]
    object.__setattr__(old, "raw", b'{"count":0,"data":[]}')
    with pytest.raises(SharadarCompanionQualificationError, match="captured_identity_changed"):
        receipt.to_payload()


def test_receipt_metadata_mutation_and_wrong_expected_protocol_refuse():
    receipt = report()
    object.__setattr__(receipt, "retrieved_at", "2026-10-11T13:00:00Z")
    with pytest.raises(SharadarCompanionQualificationError, match="captured_identity_changed"):
        receipt.to_payload()
    with pytest.raises(SharadarCompanionQualificationError, match="expected_protocol"):
        qualify_sharadar_companion(captures(), retrieved_at=RETRIEVED_AT, expected_protocol_sha256="a" * 64)


def test_subclasses_cannot_override_capture_or_qualification_checks():
    class CaptureSubclass(CapturedSharadarResponse):
        pass
    with pytest.raises(SharadarCompanionQualificationError, match="exact_capture"):
        CaptureSubclass("metadata-stocks", request_sha256("metadata-stocks"), b'{}', "application/json")
    class ReceiptSubclass(SharadarCompanionQualification):
        pass
    with pytest.raises(SharadarCompanionQualificationError, match="exact_qualification"):
        ReceiptSubclass(captures(), RETRIEVED_AT)
