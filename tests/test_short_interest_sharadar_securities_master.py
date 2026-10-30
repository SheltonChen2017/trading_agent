"""Fabricated ZIP/CSV master contracts, never actual rows or source fitness."""
from __future__ import annotations

import copy
import csv
import dataclasses
import io
import json
import zipfile
from decimal import localcontext
from contextlib import nullcontext

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.sharadar_securities_master as master_module
from research.short_interest_etf.sharadar_securities_master import (
    INTERFACE_SCHEMA,
    MAXIMUM_REQUESTS,
    PROTOCOL_SHA256,
    REQUEST_IDS,
    SCHEMA,
    TABLES,
    CapturedSharadarMasterArchive,
    SharadarSecuritiesMasterError,
    SharadarSecuritiesMasterQualification,
    lookup_current_security,
    qualification_protocol,
    qualify_sharadar_securities_master,
    request_sha256,
    sharadar_master_request,
    validate_archive,
)

TICKER_HEADERS = ["table", "permaticker", "ticker", "exchange", "isdelisted", "category",
                  "figi", "siccode", "sicsector", "sector", "currency", "location", "name",
                  "relatedtickers", "lastupdated", "firstpricedate", "lastpricedate"]
ACTION_HEADERS = ["date", "action", "ticker", "name", "value", "contraticker", "contraname"]
DESCRIPTION_HEADERS = ["table", "indicator", "title", "description", "unittype", "isprimarykey", "isfilter"]
HEADERS = {"tickers": TICKER_HEADERS, "actions": ACTION_HEADERS, "descriptions": DESCRIPTION_HEADERS}
CLOCK = "2026-10-11T20:00:00Z"


def ticker(token="FAKE", permaticker="12345", *, category="Domestic Common Stock Primary Class",
           delisted="N", table="stocks"):
    return {"table": table, "permaticker": permaticker, "ticker": token, "exchange": "FAKEVENUE",
            "isdelisted": delisted, "category": category, "figi": "BBG000000001",
            "siccode": "1234", "sicsector": "Fabricated sector", "sector": "Fabricated sector",
            "currency": "USD", "location": "FAKE", "name": "Fabricated issuer", "relatedtickers": "",
            "lastupdated": "2026-10-10", "firstpricedate": "2001-01-03", "lastpricedate": "2026-10-09"}


def documents():
    return {
        "tickers": [ticker(), ticker("FAKE.B", "12346", category="Domestic Common Stock Secondary Class"),
                    ticker("GONE", "12347", delisted="Y"),
                    ticker("FUND", "12348", category="Domestic ETF"),
                    ticker("OTHER", "12349", table="funds", category="Domestic ETF")],
        "actions": [dict(zip(ACTION_HEADERS, ["2023-02-01", "sicchangefrom", "FAKE", "Fabricated issuer", "1234", "", "Old fabricated sector"])),
                    dict(zip(ACTION_HEADERS, ["2023-02-01", "sicchangeto", "FAKE", "Fabricated issuer", "2345", "", "New fabricated sector"]))],
        "descriptions": [dict(zip(DESCRIPTION_HEADERS, ["actiontypes", "sicchangefrom", "Fake old SIC", "Fabricated dictionary: value is prior SIC", "numeric", "N", "N"])),
                         dict(zip(DESCRIPTION_HEADERS, ["actiontypes", "sicchangeto", "Fake new SIC", "Fabricated dictionary: value is new SIC", "numeric", "N", "N"])),
                         dict(zip(DESCRIPTION_HEADERS, ["tickers", "category", "Fake category", "Fabricated category dictionary", "text", "N", "N"]))],
    }


def csv_bytes(table, rows=None, *, headers=None):
    rows = documents()[table] if rows is None else rows
    headers = HEADERS[table] if headers is None else headers
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows([row.get(field, "") for field in headers] if isinstance(row, dict) else row for row in rows)
    return stream.getvalue().encode("utf-8")


def archive_bytes(table, content=None, *, filename=None, compression=zipfile.ZIP_DEFLATED, extra_member=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        archive.writestr(filename or table + ".csv", csv_bytes(table) if content is None else content)
        if extra_member:
            archive.writestr(extra_member, b"fabricated")
    return stream.getvalue()


def archives(docs=None, *, headers=None):
    docs = documents() if docs is None else docs
    return tuple(CapturedSharadarMasterArchive(table, archive_bytes(table, csv_bytes(
        table, docs[table], headers=None if headers is None else headers.get(table))), request_sha256("download-" + table))
        for table in TABLES)


def report(docs=None, *, headers=None):
    return qualify_sharadar_securities_master(archives(docs, headers=headers), retrieved_at=CLOCK)


def table(payload, name):
    return next(item for item in payload["tables"] if item["table"] == name)


def test_prospective_master_protocol_hash_inventory_and_detachment():
    payload = qualification_protocol()
    assert hash_payload(payload) == PROTOCOL_SHA256
    assert MAXIMUM_REQUESTS == len(REQUEST_IDS) == 12
    assert payload["request_ids"] == list(REQUEST_IDS)
    assert REQUEST_IDS[:6] == ("metadata-tickers", "metadata-actions", "metadata-descriptions",
                              "schema-tickers", "schema-actions", "schema-descriptions")
    assert REQUEST_IDS[6:] == ("issue-tickers", "download-tickers", "issue-actions", "download-actions",
                              "issue-descriptions", "download-descriptions")
    payload["authority"]["source_admitted"] = True
    payload["tables"].clear()
    assert hash_payload(qualification_protocol()) == PROTOCOL_SHA256


@pytest.mark.parametrize("table_name", TABLES)
def test_full_history_exact_issuer_descriptors_and_secret_free_download_identity(table_name):
    issue = sharadar_master_request("issue-" + table_name)
    metadata = sharadar_master_request("metadata-" + table_name)
    schema = sharadar_master_request("schema-" + table_name)
    download = sharadar_master_request("download-" + table_name)
    assert issue["url"] == "https://api.sharadar.com/v1.0/data/" + table_name
    assert issue["params"] == {"years": "full"}
    assert metadata["params"] == {"years": "full", "status": "True"}
    assert schema["params"] == {"format": "sqlite"}
    assert download["url"] is None and download["authentication"] == "none"
    assert download["signed_URL_persisted_or_hashed"] is False
    assert request_sha256("download-" + table_name) == hash_payload(download)


@pytest.mark.parametrize("value", [None, False, 1, "other", "rows-tickers", "download-stocks"])
def test_unknown_request_ids_refuse(value):
    with pytest.raises(SharadarSecuritiesMasterError):
        sharadar_master_request(value)


def test_complete_captured_STOCKS_master_keeps_delisted_other_tables_and_excluded_categories():
    payload = report().to_payload()
    assert payload["schema"] == SCHEMA and payload["interface_schema"] == INTERFACE_SCHEMA
    assert payload["STOCKS_master_row_indices"] == [0, 1, 2, 3]
    assert payload["current_common_stock_candidate_indices"] == [0, 1, 2]
    assert payload["excluded_or_refused_STOCKS_rows"] == [{"row_index": 3, "reason": "current_category_not_recognized_common_stock"}]
    rows = table(payload, "tickers")["rows"]
    assert len(rows) == 5 and rows[2]["normalized"]["isdelisted"] is True
    assert rows[4]["normalized"]["table"] == "funds"
    assert payload["authority"]["whole_US_listed_universe_verified"] is False
    assert "all_captured_STOCKS" in payload["population_scope"]


def test_every_raw_CSV_cell_file_hash_and_row_index_is_retained():
    captures = archives()
    payload = qualify_sharadar_securities_master(captures, retrieved_at=CLOCK).to_payload()
    for capture, captured_table in zip(captures, payload["tables"]):
        csv_raw = validate_archive(capture.table, capture.raw)
        expected = list(csv.reader(io.StringIO(csv_raw.decode("utf-8"))))
        assert captured_table["headers"] == expected[0]
        assert [row["raw_cells"] for row in captured_table["rows"]] == expected[1:]
        assert captured_table["archive_sha256"] == hash_bytes(capture.raw)
        assert captured_table["CSV_sha256"] == hash_bytes(csv_raw)
        for index, row in enumerate(captured_table["rows"]):
            assert row["origin"]["row_index"] == index
            assert row["origin"]["raw_record_sha256"] == hash_payload({"CSV_sha256": hash_bytes(csv_raw), "row_index": index})
            assert row["origin"]["archive_sha256"] == hash_bytes(capture.raw)
    assert payload["report_sha256"] == hash_payload({key: value for key, value in payload.items() if key != "report_sha256"})


def test_current_unique_native_lookup_never_casts_permaticker_or_composite_to_share_class_FIGI():
    qualified = report()
    by_ticker = lookup_current_security(qualified, ticker="FAKE")
    by_id = lookup_current_security(qualified, permaticker="12345")
    assert by_ticker == by_id
    normalized = by_ticker["candidate"]
    assert normalized["provider_security_id"] == "sharadar:permaticker:12345"
    assert normalized["composite_figi_assertion"] == "BBG000000001"
    assert normalized["share_class_figi"] is None
    assert normalized["historical_effective_intervals"] == []
    assert by_ticker["point_in_time_data"] is False and by_ticker["historical_mapping_admitted"] is False
    assert by_ticker["same_share_class_denominator"] is None
    assert qualified.to_payload()["historical_ticker_intervals"] == []


@pytest.mark.parametrize("values", [{}, {"ticker": "FAKE", "permaticker": "12345"}, {"permaticker": 12345},
                                     {"permaticker": True}, {"ticker": " FAKE"}, {"ticker": "MISSING"}])
def test_current_lookup_requires_one_exact_unique_selector(values):
    with pytest.raises(SharadarSecuritiesMasterError):
        lookup_current_security(report(), **values)


@pytest.mark.parametrize("value", ["0", "012345", "12345.0", "+12345", "1e3", "-1", "", "123 45", "1" * 31])
def test_noncanonical_provider_ids_refuse_without_losing_STOCKS_rows(value):
    docs = documents()
    docs["tickers"][0]["permaticker"] = value
    qualified = report(docs)
    payload = qualified.to_payload()
    assert len(table(payload, "tickers")["rows"]) == 5
    assert table(payload, "tickers")["rows"][0]["status"] == "refused"
    assert 0 in payload["STOCKS_master_row_indices"]
    with pytest.raises(SharadarSecuritiesMasterError):
        lookup_current_security(qualified, ticker="FAKE")


@pytest.mark.parametrize("category,role,origin", [
    ("Domestic Common Stock", None, "Domestic"),
    ("Domestic Common Stock Primary Class", "Primary Class", "Domestic"),
    ("Domestic Common Stock Secondary Class", "Secondary Class", "Domestic"),
    ("ADR Common Stock", None, "ADR"),
    ("Canadian Common Stock Primary Class", "Primary Class", "Canadian"),
])
def test_common_stock_candidate_roles_are_current_assertions_not_share_denominators(category, role, origin):
    docs = documents()
    docs["tickers"][0]["category"] = category
    row = lookup_current_security(report(docs), ticker="FAKE")["candidate"]
    assert row["current_common_stock_candidate"] is True
    assert row["share_class_role_assertion"] == role and row["filing_origin_assertion"] == origin
    assert row["same_share_class_denominator"] is None
    assert row["point_in_time_data"] is False


@pytest.mark.parametrize("category", ["", "Domestic ETF", "Domestic Preferred Stock", "Common stock", "Domestic Common Stock - Primary Class"])
def test_unknown_or_noncommon_categories_remain_explicit_exclusions_not_dropped(category):
    docs = documents()
    docs["tickers"][0]["category"] = category
    payload = report(docs).to_payload()
    assert 0 not in payload["current_common_stock_candidate_indices"]
    assert 0 in payload["STOCKS_master_row_indices"]
    assert table(payload, "tickers")["rows"][0]["normalized"]["category_assertion"] == category


def test_unknown_headers_keep_every_source_cell_and_schema_refusal_without_interpreting_it():
    docs = documents()
    docs["tickers"][0]["unknown_future_field"] = "not authority"
    headers = {"tickers": TICKER_HEADERS + ["unknown_future_field"]}
    payload = report(docs, headers=headers).to_payload()
    captured = table(payload, "tickers")
    assert captured["schema_refusals"] == [{"reason": "unknown_CSV_columns_not_interpreted", "columns": ["unknown_future_field"]}]
    assert captured["rows"][0]["raw_cells"][-1] == "not authority"
    assert "unknown_future_field" not in captured["rows"][0]["normalized"]


@pytest.mark.parametrize("table_name", TABLES)
def test_all_identifiable_duplicates_quarantined_even_malformed_peer(table_name):
    docs = documents()
    peer = copy.deepcopy(docs[table_name][0])
    if table_name == "tickers":
        peer["isdelisted"] = "INVALID"
    elif table_name == "actions":
        peer["value"] = "NaN"
    else:
        peer["isfilter"] = "INVALID"
    docs[table_name].append(peer)
    payload = report(docs).to_payload()
    rows = table(payload, table_name)["rows"]
    assert rows[0]["refusal_reason"] == rows[-1]["refusal_reason"] == "duplicate_primary_key_all_copies_quarantined"
    assert rows[0]["normalized"] is rows[-1]["normalized"] is None
    assert rows[0]["origin"]["raw_record_sha256"] != rows[-1]["origin"]["raw_record_sha256"]
    assert len(rows) == len(docs[table_name])


@pytest.mark.parametrize("mutation", ["another_id", "same_id_other_ticker", "invalid_id"])
def test_conflicting_current_ticker_and_provider_id_assertions_do_not_select_a_winner(mutation):
    docs = documents()
    peer = copy.deepcopy(docs["tickers"][0])
    if mutation == "another_id":
        peer["permaticker"] = "999"
    elif mutation == "same_id_other_ticker":
        peer["ticker"] = "RENAMED"
    else:
        peer["permaticker"] = "BAD"
    docs["tickers"].append(peer)
    qualified = report(docs)
    for selector in ({"ticker": "FAKE"}, {"permaticker": "12345"}):
        with pytest.raises(SharadarSecuritiesMasterError):
            lookup_current_security(qualified, **selector)
    assert all(candidate["current_native_owner"] is None for candidate in qualified.to_payload()["temporal_event_candidates"])


def test_dictionary_and_unique_current_owner_yield_candidates_never_guessed_historical_field_meanings():
    payload = report().to_payload()
    for event in payload["temporal_event_candidates"]:
        assert event["current_native_owner"] == "sharadar:permaticker:12345"
        assert event["dictionary_label_retained"] is True
        assert event["public_documented_event_class"].startswith("historical_SIC_")
        assert event["historical_mapping_admitted"] is False
        assert event["historical_alias"] is None and event["effective_at"] is None
    assert payload["historical_ticker_intervals"] == []
    normalized = table(payload, "tickers")["rows"][0]["normalized"]
    assert "effective_from" not in normalized and "effective_to" not in normalized
    assert normalized["current_reference_assertions"]["firstpricedate"] == "2001-01-03"


def test_unknown_action_labels_and_duplicate_dictionary_never_invent_semantics():
    docs = documents()
    docs["actions"][0]["action"] = "unknown-future-action"
    docs["descriptions"].append(copy.deepcopy(docs["descriptions"][1]))
    payload = report(docs).to_payload()
    events = payload["temporal_event_candidates"]
    assert events[0]["public_documented_event_class"] is None
    assert all(event["dictionary_row_index"] is None for event in events)
    assert all("missing_or_refused_action_dictionary_entry" in event["refusal_reasons"] for event in events)
    assert len(table(payload, "actions")["rows"]) == 2


@pytest.mark.parametrize("value,expected", [("0.5", {"numerator": 1, "denominator": 2}),
                                           ("1e-3", {"numerator": 1, "denominator": 1000}),
                                           ("-1.25", {"numerator": -5, "denominator": 4}), ("", None)])
def test_date_only_action_values_remain_exact_and_do_not_invent_payment_or_terminal_cash(value, expected):
    docs = documents()
    docs["actions"][0].update(action="acquisitioncash", value=value)
    with localcontext() as context:
        context.prec = 2
        payload = report(docs).to_payload()
    row = table(payload, "actions")["rows"][0]["normalized"]
    assert row["value"] == expected
    assert row["payment_timestamp"] is None and row["effective_at"] is None
    assert row["terminal_economics_admitted"] is False
    assert row["date_precision"] == "calendar_day_only"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1,000", "+1", "01", "1/2", "1e999", " 1", "true"])
def test_bad_financial_lexical_tokens_are_refused_and_retained(value):
    docs = documents()
    docs["actions"][0]["value"] = value
    rows = table(report(docs).to_payload(), "actions")["rows"]
    assert rows[0]["normalized"] is None and rows[0]["raw_cells"][4] == value
    assert len(rows) == 2


@pytest.mark.parametrize("field,value", [("firstpricedate", "2023-02-30"), ("lastupdated", "tomorrow"),
                                       ("lastpricedate", "2000-01-01"), ("isdelisted", "true"),
                                       ("figi", "sharadar:123"), ("exchange", "VENUE\nINJECTION")])
def test_invalid_current_master_assertions_do_not_become_lookup_authority(field, value):
    docs = documents()
    docs["tickers"][0][field] = value
    qualified = report(docs)
    assert table(qualified.to_payload(), "tickers")["rows"][0]["normalized"] is None
    with pytest.raises(SharadarSecuritiesMasterError):
        lookup_current_security(qualified, ticker="FAKE")


@pytest.mark.parametrize("clock", [None, False, "2026-10-11", "2026-10-11T20:00:00", "2026-10-11T20:00:00+00:00", "2026-10-11T20:00:00.000000Z"])
def test_retrieval_clock_requires_canonical_UTC_Z(clock):
    with pytest.raises(SharadarSecuritiesMasterError):
        qualify_sharadar_securities_master(archives(), retrieved_at=clock)


def test_all_authority_stays_closed_and_actual_input_bundle_is_not_implemented():
    qualified = report()
    payload = qualified.to_payload()
    assert not hasattr(qualified, "references") and not hasattr(qualified, "bars")
    assert payload["authority"]["source_only"] is True
    for name, value in payload["authority"].items():
        if name != "source_only":
            assert value is False or (type(value) is int and value == 0)


@pytest.mark.parametrize("compression", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_archive_returns_exact_CSV_bytes_for_admitted_compression(compression):
    content = csv_bytes("tickers")
    raw = archive_bytes("tickers", content, compression=compression)
    assert validate_archive("tickers", raw) == content


def streaming_archive_bytes():
    class Stream(io.BytesIO):
        def seek(self, *args):
            raise OSError("fabricated unseekable stream")
    stream = Stream()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("tickers.csv", csv_bytes("tickers"))
    return stream.getvalue()


def test_streaming_ZIP32_data_descriptor_is_checked_and_valid_baseline_admitted():
    raw = streaming_archive_bytes()
    assert int.from_bytes(raw[6:8], "little") & 8
    assert validate_archive("tickers", raw) == csv_bytes("tickers")
    altered = bytearray(raw)
    descriptor = raw.index(b"PK\x07\x08")
    altered[descriptor + 4] ^= 1
    with pytest.raises(SharadarSecuritiesMasterError, match="descriptor"):
        validate_archive("tickers", bytes(altered))


def test_empty_complete_archives_are_retained_without_fabricated_population():
    docs = {name: [] for name in TABLES}
    payload = report(docs).to_payload()
    assert payload["STOCKS_master_row_indices"] == []
    assert payload["current_common_stock_candidate_indices"] == []
    assert payload["temporal_event_candidates"] == []
    assert [item["input_row_count"] for item in payload["tables"]] == [0, 0, 0]
    with pytest.raises(SharadarSecuritiesMasterError):
        lookup_current_security(report(docs), ticker="FAKE")


@pytest.mark.parametrize("filename", ["../tickers.csv", "/tickers.csv", "nested/tickers.csv", "tickers.csv/", "Tickers.csv", "other.csv"])
def test_archive_exact_basename_no_paths_or_directory(filename):
    with pytest.raises(SharadarSecuritiesMasterError):
        validate_archive("tickers", archive_bytes("tickers", filename=filename))


def test_archive_multiple_and_duplicate_members_are_refused():
    for extra in ("other.csv", "tickers.csv"):
        with pytest.warns(UserWarning) if extra == "tickers.csv" else nullcontext():
            raw = archive_bytes("tickers", extra_member=extra)
        with pytest.raises(SharadarSecuritiesMasterError):
            validate_archive("tickers", raw)


@pytest.mark.parametrize("mode", [0o120777, 0o040700, 0o020600, 0o060600, 0o010600])
def test_archive_symlink_directory_or_special_type_is_refused(mode):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        info = zipfile.ZipInfo("tickers.csv")
        info.create_system = 3
        info.external_attr = mode << 16
        archive.writestr(info, csv_bytes("tickers"))
    with pytest.raises(SharadarSecuritiesMasterError):
        validate_archive("tickers", stream.getvalue())


@pytest.mark.parametrize("compression", [zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA])
def test_unregistered_compression_methods_refuse(compression):
    with pytest.raises(SharadarSecuritiesMasterError):
        validate_archive("tickers", archive_bytes("tickers", compression=compression))


@pytest.mark.parametrize("alteration", ["prefix", "suffix", "truncate", "CRC", "encrypted", "comment"])
def test_archive_structural_corruption_refuses_named_safe_error(alteration):
    raw = archive_bytes("tickers", compression=zipfile.ZIP_STORED)
    if alteration == "prefix":
        raw = b"junk" + raw
    elif alteration == "suffix":
        raw += b"junk"
    elif alteration == "truncate":
        raw = raw[:-1]
    elif alteration == "CRC":
        changed = bytearray(raw)
        changed[changed.index(b"table,permaticker")] = ord("X")
        raw = bytes(changed)
    elif alteration == "encrypted":
        changed = bytearray(raw)
        changed[6] |= 1
        central = raw.index(b"PK\x01\x02")
        changed[central + 8] |= 1
        raw = bytes(changed)
    else:
        stream = io.BytesIO(raw)
        with zipfile.ZipFile(stream, "a") as archive:
            archive.comment = b"fabricated comment"
        raw = stream.getvalue()
    with pytest.raises(SharadarSecuritiesMasterError):
        validate_archive("tickers", raw)


@pytest.mark.parametrize("gap", [b"undeclared archive payload", b"PK\x03\x04" + b"hidden local member" * 5])
def test_archive_undeclared_bytes_between_member_and_central_directory_refuse(gap):
    raw = archive_bytes("tickers", compression=zipfile.ZIP_STORED)
    central = raw.index(b"PK\x01\x02")
    altered = bytearray(raw[:central] + gap + raw[central:])
    eocd = altered.rfind(b"PK\x05\x06")
    altered[eocd + 16:eocd + 20] = (central + len(gap)).to_bytes(4, "little")
    with pytest.raises(SharadarSecuritiesMasterError):
        validate_archive("tickers", bytes(altered))


@pytest.mark.parametrize("raw", [b"", b"not zip", bytearray(b"PK"), "PK"])
def test_archive_requires_immutable_bounded_nonempty_bytes(raw):
    with pytest.raises(SharadarSecuritiesMasterError):
        validate_archive("tickers", raw)


def test_archive_and_decompression_size_bounds_enforced_before_parsing(monkeypatch):
    raw = archive_bytes("tickers")
    monkeypatch.setattr(master_module, "MAXIMUM_ARCHIVE_BYTES", len(raw) - 1)
    with pytest.raises(SharadarSecuritiesMasterError, match="size"):
        validate_archive("tickers", raw)
    monkeypatch.setattr(master_module, "MAXIMUM_ARCHIVE_BYTES", len(raw) + 1)
    monkeypatch.setattr(master_module, "MAXIMUM_CSV_BYTES", 5)
    with pytest.raises(SharadarSecuritiesMasterError, match="size"):
        validate_archive("tickers", raw)


@pytest.mark.parametrize("content", [b"", b"\xff", b"\xef\xbb\xbftable,permaticker", b"table\x00,permaticker", b"table,table\n", b"table,permaticker,ticker,exchange,isdelisted,category\nshort\n", b'"unterminated'])
def test_malformed_CSV_refuses_entire_archive_without_partial_report(content):
    capture = CapturedSharadarMasterArchive("tickers", archive_bytes("tickers", content or b"\n"), request_sha256("download-tickers"))
    with pytest.raises(SharadarSecuritiesMasterError):
        qualify_sharadar_securities_master((capture,) + archives()[1:], retrieved_at=CLOCK)


def test_CSV_rows_and_fields_are_bounded_and_no_blank_row_is_silently_skipped(monkeypatch):
    capture = archives()[0]
    monkeypatch.setitem(master_module.MAXIMUM_ROWS, "tickers", 1)
    with pytest.raises(SharadarSecuritiesMasterError):
        master_module._parsed(capture)
    monkeypatch.setitem(master_module.MAXIMUM_ROWS, "tickers", 200000)
    monkeypatch.setattr(master_module, "MAXIMUM_FIELD_CHARACTERS", 3)
    with pytest.raises(SharadarSecuritiesMasterError):
        master_module._parsed(capture)
    blank = CapturedSharadarMasterArchive("tickers", archive_bytes("tickers", csv_bytes("tickers") + b"\n"), request_sha256("download-tickers"))
    with pytest.raises(SharadarSecuritiesMasterError):
        master_module._parsed(blank)


def test_documented_description_aliases_normalize_only_when_unique():
    docs = documents()
    aliases = {"table": "tablename", "unittype": "unitType", "isprimarykey": "isPrimaryKey", "isfilter": "isFilter"}
    docs["descriptions"] = [{aliases.get(key, key): value for key, value in row.items()} for row in docs["descriptions"]]
    headers = {"descriptions": [aliases.get(field, field) for field in DESCRIPTION_HEADERS]}
    payload = report(docs, headers=headers).to_payload()
    assert table(payload, "descriptions")["normalized_headers"] == DESCRIPTION_HEADERS
    both = DESCRIPTION_HEADERS + ["tablename"]
    raw = archive_bytes("descriptions", csv_bytes("descriptions", headers=both))
    capture = CapturedSharadarMasterArchive("descriptions", raw, request_sha256("download-descriptions"))
    with pytest.raises(SharadarSecuritiesMasterError, match="duplicate_CSV_headers"):
        qualify_sharadar_securities_master(archives()[:2] + (capture,), retrieved_at=CLOCK)


@pytest.mark.parametrize("value", [[], (), ("wrong",), [1, 2, 3]])
def test_complete_exact_type_and_ordered_three_archive_inventory_required(value):
    with pytest.raises(SharadarSecuritiesMasterError):
        qualify_sharadar_securities_master(value, retrieved_at=CLOCK)


def test_swapped_and_duplicate_table_inventory_refuse():
    captured = archives()
    for value in ((captured[1], captured[0], captured[2]), (captured[0], captured[0], captured[2])):
        with pytest.raises(SharadarSecuritiesMasterError):
            qualify_sharadar_securities_master(value, retrieved_at=CLOCK)


def test_archive_request_binding_and_subclasses_cannot_assert_provenance():
    with pytest.raises(SharadarSecuritiesMasterError):
        CapturedSharadarMasterArchive("tickers", archive_bytes("tickers"), "a" * 64)
    class Lookalike(CapturedSharadarMasterArchive):
        pass
    with pytest.raises(SharadarSecuritiesMasterError):
        Lookalike("tickers", archive_bytes("tickers"), request_sha256("download-tickers"))
    class FakeQualification(SharadarSecuritiesMasterQualification):
        pass
    with pytest.raises(SharadarSecuritiesMasterError):
        FakeQualification(archives(), CLOCK)


def test_reports_are_detached_sealed_and_revalidate_capture_identity():
    qualified = report()
    payload = qualified.to_payload()
    payload["tables"][0]["rows"].clear()
    payload["authority"]["source_admitted"] = True
    assert len(qualified.to_payload()["tables"][0]["rows"]) == 5
    assert qualified.to_payload()["authority"]["source_admitted"] is False
    changed = documents()
    changed["tickers"][0]["ticker"] = "MUTATED"
    object.__setattr__(qualified.captures[0], "raw", archives(changed)[0].raw)
    with pytest.raises(SharadarSecuritiesMasterError, match="identity_changed"):
        qualified.to_payload()


@pytest.mark.parametrize("field,value", [("_capture_identity_sha256", "a" * 64), ("_payload_json", "{}"), ("retrieved_at", "2026-10-11T21:00:00Z")])
def test_qualification_seal_mutation_is_refused(field, value):
    qualified = report()
    object.__setattr__(qualified, field, value)
    with pytest.raises(SharadarSecuritiesMasterError):
        qualified.to_payload()
