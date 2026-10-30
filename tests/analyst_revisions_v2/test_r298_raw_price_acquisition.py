"""Synthetic supplied-AC adapter and CSV tests only; no source admission/ops."""
import copy
import csv
import io
import json
import pickle
import time
from types import SimpleNamespace as NS

import pytest

from scripts import arv2_r298_raw_price_acquisition as m


@pytest.fixture
def supplied(monkeypatch):
    # The frozen AC/native validators have separate production-contract tests.
    # Here synthetic adapters supply full-size inert routing data to exercise
    # new assignment preservation and price_request/CSV bounds without private reads.
    stocks = []
    for index in range(m.VENDOR_STOCK_COUNT + m.NATIVE_STOCK_COUNT + m.CONDITIONAL_COUNT):
        vendor = index < m.VENDOR_STOCK_COUNT
        pending = m.VENDOR_STOCK_COUNT <= index < m.VENDOR_STOCK_COUNT + m.NATIVE_STOCK_COUNT
        binding = {"security_id": "synthetic-stock-" + str(index), "row_sha256": m.digest({"binding": index}),
            "qc_security_id": None, "synthetic_original_class": "common", "synthetic_source_currency": "USD"}
        stocks.append({"binding_ordinal": index, "binding": binding, "potential": vendor or pending,
            "conditional_never_potential": not (vendor or pending),
            "disposition": "routed" if vendor else "refused" if pending else "conditional_never_potential",
            "reason": ("global_collision" if index == m.VENDOR_STOCK_COUNT + m.NATIVE_STOCK_COUNT - 1 else "identity_missing") if pending else None,
            "query_window": [m.FIRST, m.LAST] if vendor else None,
            "route": {"table": "stocks", "current_metadata_row": {"ticker": "ST" + str(index).zfill(5),
                "currency": "USD"}} if vendor else None})
    funds = [{"fund_ordinal": index, "ticker": ticker, "disposition": "routed", "reason": None,
        "query_window": [m.FIRST, m.LAST],
        "route": {"table": "funds", "current_metadata_row": {"ticker": ticker, "currency": "USD"}}}
        for index, ticker in enumerate(("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE", "XLI", "XLF"))]
    record = {"stocks": stocks, "funds": funds}
    axis = ["2020-12-31", "2021-01-04", "2024-01-02", "2026-10-13"]
    monkeypatch.setattr(m, "FULL_AXIS_COUNT", len(axis))
    monkeypatch.setattr(m, "PRICE_SESSION_COUNT", len(axis))
    monkeypatch.setattr(m, "FULL_AXIS_SHA256", m.digest(axis))
    calls = []

    def native(value):
        expected = {"selected_whole_binding_sha256s": sorted(m.digest(row["binding"])
            for row in record["stocks"] if row["disposition"] == "refused")}
        m.require(value == expected, "native_specification")
        return copy.deepcopy(value)
    monkeypatch.setattr(m, "_native_specification", native)

    def source_summary(value):
        calls.append("summary")
        return copy.deepcopy(value)

    def source_record(value, *, expected_summary):
        calls.append("record")
        assert len(value["stocks"]) == 6151 and len(value["funds"]) == 8
        return copy.deepcopy(value)
    monkeypatch.setattr(m.ac, "validate_summary", source_summary)
    monkeypatch.setattr(m.ac, "validate_private_record", source_record)

    def prepare(data=None, spec=None, raw_override=None, summary_override=None):
        data = record if data is None else data
        raw = m.canonical(data) if raw_override is None else raw_override
        summary = {"schema": "synthetic-AC-summary", "private_frame_byte_count": len(m.canonical(data)),
            "private_frame_sha256": m.sha(m.canonical(data))}
        if summary_override is not None:
            summary = summary_override
        selected = {"selected_whole_binding_sha256s": sorted(m.digest(row["binding"])
            for row in record["stocks"] if row["disposition"] == "refused")} if spec is None else spec
        monkeypatch.setattr(m, "AC_SUMMARY_SHA256", m.digest(summary))
        monkeypatch.setattr(m, "NATIVE_SPECIFICATION_SHA256", m.digest(selected))
        return m.prepare_plan(raw, expected_ac_summary=summary,
            native_specification=selected, session_axis=axis)
    return NS(record=record, axis=axis, prepare=prepare, calls=calls)


def csv_bytes(rows, header=m.FIELDS):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header); writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def refuses(code, operation):
    with pytest.raises(m.Refused) as caught:
        operation()
    assert m.finite(caught.value) == code


def test_full_size_plan_preserves_every_assignment_and_fixed_bounded_requests(supplied):
    summary, private = supplied.prepare()
    assert summary["stock_binding_count"] == 6151
    assert summary["vendor_stock_count"] == 5636 and summary["pending_native_stock_count"] == 5
    assert summary["conditional_stock_count"] == 510 and summary["fund_count"] == 8
    assert summary["stock_group_count"] == 209
    assert summary["stock_request_count"] == 1254 and summary["fund_request_count"] == 2
    assert summary["request_count"] == 1256 and summary["maximum_calendar_key_bound"] == 9882
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    graph = json.loads(private._raw)  # Synthetic-only inspection, never a production serializer.
    assert len(graph["assignments"]) == 6159
    roles = [row["role"] for row in graph["assignments"]]
    assert roles.count("pending_native_original_identity_source") == 5
    assert roles.count("conditional_never_potential_empty_initial_holdings_required") == 510
    assert all(price_request["parameters"]["limit"] == "10000" and price_request["parameters"]["skip"] == "0"
        and price_request["parameters"]["format"] == "csv" and price_request["parameters"]["sort"] == "date.asc"
        for price_request in graph["requests"])
    assert max(len(row["tickers"]) for row in graph["requests"] if row["table"] == "stocks") == 27
    for token in ("synthetic-stock", "ST00000", "SPY"):
        assert token.encode() not in m.canonical(summary)
    assert m.validate_plan_summary(summary) == summary
    bad = copy.deepcopy(summary); bad["maximum_calendar_key_bound"] = 1
    refuses("summary", lambda: m.validate_plan_summary(bad))
    assert "ST00000" not in repr(private)
    with pytest.raises(TypeError): json.dumps(private)
    with pytest.raises(TypeError): pickle.dumps(private)
    with pytest.raises(TypeError): private._raw = b"changed"


def test_full_window_is_not_clipped_by_any_source_metadata_or_membership(supplied):
    record = copy.deepcopy(supplied.record)
    record["stocks"][0]["synthetic_current_last_price_date"] = "2020-12-31"
    record["stocks"][0]["synthetic_membership_end"] = "2021-01-04"
    _, private = supplied.prepare(record)
    graph = json.loads(private._raw)
    first_stock = "ST00000"
    windows = [(row["first"], row["last"]) for row in graph["requests"] if first_stock in row["tickers"]]
    assert windows == list(m.STOCK_WINDOWS)
    assert graph["requests"][-2]["first"] == "2020-12-31" and graph["requests"][-1]["last"] == "2026-10-13"


@pytest.mark.parametrize("mode", ["promote_native", "drop_native", "duplicate_locator", "wrong_currency",
    "clip_window", "wrong_native_set", "native_binding_mismatch", "duplicate_fund_locator", "duplicate_security"])
def test_no_refusal_fallback_source_drop_or_collision_filter(supplied, mode):
    record = copy.deepcopy(supplied.record)
    spec = None
    if mode == "promote_native":
        item = record["stocks"][5636]
        item.update(disposition="routed", reason=None, query_window=[m.FIRST, m.LAST],
            route={"table": "stocks", "current_metadata_row": {"ticker": "UNPROVED", "currency": "USD"}})
    elif mode == "drop_native":
        record["stocks"].pop(5636)
    elif mode == "duplicate_locator":
        record["stocks"][1]["route"] = copy.deepcopy(record["stocks"][0]["route"])
    elif mode == "wrong_currency":
        record["stocks"][0]["route"]["current_metadata_row"]["currency"] = "EUR"
    elif mode == "clip_window":
        record["stocks"][0]["query_window"][0] = "2022-01-01"
    elif mode == "wrong_native_set":
        spec = {"selected_whole_binding_sha256s": ["a" * 64] * 5}
    elif mode == "native_binding_mismatch":
        record["stocks"][5636]["binding"]["security_id"] = "synthetic-different-original"
    elif mode == "duplicate_fund_locator":
        record["funds"][1]["route"] = copy.deepcopy(record["funds"][0]["route"])
    else:
        record["stocks"][1]["binding"]["security_id"] = record["stocks"][0]["binding"]["security_id"]
    with pytest.raises((m.Refused, AssertionError)):
        supplied.prepare(record, spec=spec)


def test_external_byte_pin_is_checked_before_JSON_and_old_AC_private_validator(supplied):
    before = list(supplied.calls)
    refuses("ac_pin", lambda: supplied.prepare(raw_override=b"not JSON"))
    assert supplied.calls == before + ["summary"]


def test_equal_length_valid_other_source_bytes_do_not_bypass_the_original_pin(supplied):
    changed = copy.deepcopy(supplied.record)
    changed["stocks"][0]["route"]["current_metadata_row"]["ticker"] = "ST99999"
    raw = m.canonical(changed)
    assert len(raw) == len(m.canonical(supplied.record))
    refuses("ac_pin", lambda: supplied.prepare(raw_override=raw))


def test_canonical_source_JSON_duplicate_or_unknown_numbers_refuse_before_legacy_validation(supplied):
    raw = b'{"stocks":[],"stocks":[],"funds":[]}'
    summary = {"schema": "synthetic", "private_frame_byte_count": len(raw), "private_frame_sha256": m.sha(raw)}
    refuses("ac_json", lambda: supplied.prepare(raw_override=raw, summary_override=summary))


@pytest.fixture
def price_request(supplied):
    summary, private = supplied.prepare()
    return private.request(0)


def test_CSV_exact_rows_positive_RAW_Decimal_and_explicit_NYSE_absences(price_request):
    raw = csv_bytes([("ST00000", "2020-12-31", "1.234500000000000000000001", "2026-10-27"),
        ("ST00001", "2021-01-04", "1e-4", "2021-01-04")])
    summary, private = m.analyze_response(price_request, raw, http_status=200)
    assert summary["row_count"] == 2 and summary["expected_NYSE_cell_count"] == 54
    assert summary["absent_cell_count"] == 52
    assert summary["lastupdated_relation_counts"] == {"after_price_date": 1, "same_as_price_date": 1}
    assert all(summary[key] is False for key in m.FALSE_FLAGS)
    graph = json.loads(private._raw)
    assert graph["rows"][0][2] == "1.234500000000000000000001"
    assert graph["rows"][1][2] == "0.0001"
    assert len(graph["absent_cells"]) == 52
    assert m.validate_response_summary(summary, request=price_request) == summary
    assert b"ST00000" not in m.canonical(summary) and b"1.2345" not in m.canonical(summary)
    with pytest.raises(TypeError): json.dumps(private)
    with pytest.raises(TypeError): pickle.dumps(private)


def test_header_only_is_observed_absence_not_coverage_or_payoff(price_request):
    summary, private = m.analyze_response(price_request, csv_bytes([]), http_status=200)
    assert summary["row_count"] == 0 and summary["absent_cell_count"] == 54
    assert summary["complete_price_coverage_proven"] is summary["terminal_payoff_proven"] is False


def test_request_endpoint_scope_cannot_be_changed_or_add_a_filter(price_request):
    record = json.loads(price_request._raw)
    assert record["endpoint"] == "https://api.sharadar.com/v1.0/data/stocks"
    record["endpoint"] = "https://example.invalid/other"
    altered = m.PrivatePriceRequest(record)
    refuses("request", lambda: m.analyze_response(altered, csv_bytes([]), http_status=200))
    record = json.loads(price_request._raw)
    record["parameters"]["lastupdated.gte"] = "2026-01-01"
    altered = m.PrivatePriceRequest(record)
    refuses("request", lambda: m.analyze_response(altered, csv_bytes([]), http_status=200))


def test_known_CSV_BOM_and_CRLF_decode_but_JSON_or_unclosed_quote_refuse(price_request):
    summary, _ = m.analyze_response(price_request, b"\xef\xbb\xbf" + csv_bytes([]).replace(b"\n", b"\r\n"), http_status=200)
    assert summary["row_count"] == 0
    for raw in (b"[]", b"ticker,date,closeunadj,lastupdated\n\"unclosed\n", b"\xff"):
        with pytest.raises(m.Refused):
            m.analyze_response(price_request, raw, http_status=200)


@pytest.mark.parametrize("mode", ["header_order", "duplicate_header", "extra_header", "extra_column",
    "missing_column", "unknown_ticker", "weekend", "outside_window", "duplicate", "unsorted",
    "zero", "negative", "nan", "infinite", "huge_exponent", "bad_updated", "spaces", "unicode", "control"])
def test_malformed_or_ambiguous_rows_are_never_selected_or_silently_dropped(price_request, mode):
    rows = [["ST00000", "2020-12-31", "123.45", "2026-10-27"]]
    header = m.FIELDS
    if mode == "header_order": header = tuple(reversed(header))
    elif mode == "duplicate_header": header = ("ticker", "date", "closeunadj", "ticker")
    elif mode == "extra_header": header += ("unknown",)
    elif mode == "extra_column": rows[0].append("unknown")
    elif mode == "missing_column": rows[0].pop()
    elif mode == "unknown_ticker": rows[0][0] = "UNPLANNED"
    elif mode == "weekend": rows[0][1] = "2021-01-02"
    elif mode == "outside_window": rows[0][1] = "2022-01-03"
    elif mode == "duplicate": rows.append(list(rows[0]))
    elif mode == "unsorted": rows = [["ST00001", "2021-01-04", "2", "2026-10-27"], rows[0]]
    elif mode == "zero": rows[0][2] = "0"
    elif mode == "negative": rows[0][2] = "-1"
    elif mode == "nan": rows[0][2] = "NaN"
    elif mode == "infinite": rows[0][2] = "Infinity"
    elif mode == "huge_exponent": rows[0][2] = "1e1000000"
    elif mode == "bad_updated": rows[0][3] = "not-date"
    elif mode == "spaces": rows[0][2] = " 1"
    elif mode == "unicode": rows[0][0] = "ST\u00e9000"
    else: rows[0][2] = "1\n2"
    with pytest.raises(m.Refused) as caught:
        m.analyze_response(price_request, csv_bytes(rows, header), http_status=200)
    if mode == "duplicate": assert m.finite(caught.value) == "duplicate_price"
    if mode == "weekend": assert m.finite(caught.value) == "price_date"


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_non200_failed_body_remains_unread_and_absence_unknown(price_request, status):
    summary, private = m.analyze_response(price_request, None, http_status=status)
    assert summary["terminal"] == "HTTP_refused_body_unread"
    assert summary["row_count"] is summary["absent_cell_count"] is summary["raw_body_pin"] is None
    refuses("failed_body", lambda: m.analyze_response(price_request, b"PRIVATE FAILED BODY", http_status=status))
    assert m.validate_response_summary(summary, request=price_request) == summary


@pytest.mark.parametrize("change", ["flag", "extra", "row_bool", "absent", "body_pin", "request_pin", "lastupdated"])
def test_closed_response_metadata_cannot_fabricate_coverage_or_missing_counts(price_request, change):
    summary, _ = m.analyze_response(price_request, csv_bytes([]), http_status=200)
    if change == "flag": summary["price_input_admitted"] = True
    elif change == "extra": summary["ticker"] = "ST00000"
    elif change == "row_bool": summary["row_count"] = False
    elif change == "absent": summary["absent_cell_count"] = 0
    elif change == "body_pin": summary["raw_body_pin"]["sha256"] = "bad"
    elif change == "request_pin": summary["request_sha256"] = "a" * 64
    else: summary["lastupdated_relation_counts"] = {"same_as_price_date": 1}
    refuses("summary", lambda: m.validate_response_summary(summary, request=price_request))


def test_row_limit_hit_body_bound_bool_status_and_deadline_refuse(price_request, monkeypatch):
    record = json.loads(price_request._raw)
    monkeypatch.setattr(m, "ROW_LIMIT", 2)
    record["parameters"]["limit"] = "2"
    bounded = m.PrivatePriceRequest(record)
    raw = csv_bytes([("ST00000", "2020-12-31", "1", "2026-10-27"),
        ("ST00001", "2020-12-31", "1", "2026-10-27")])
    refuses("row_bound", lambda: m.analyze_response(bounded, raw, http_status=200))
    refuses("http_status", lambda: m.analyze_response(bounded, None, http_status=True))
    refuses("deadline", lambda: m.analyze_response(bounded, None, http_status=403, deadline=time.monotonic() - 1))


def test_profile_has_no_quota_rights_or_historical_availability_claim():
    profile = m.profile_record()
    assert profile["format"] == "csv" and profile["first_stock_calendar_bound"] == 9882
    assert "not_original_availability" in profile["lastupdated"]
    assert all(profile[key] is False for key in m.FALSE_FLAGS)
