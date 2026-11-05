"""Fabricated source-only grouped-bar contracts; never provider rows."""
from pathlib import Path
from datetime import datetime
import json
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from data.hashing import hash_bytes, hash_payload
import research.short_interest_etf.native_grouped_market_source as source

ROW = '{"T":"SAMPLE","o":9.25,"h":12,"l":8,"c":10.5,"v":9007199254740993.25,"t":1641254400000,"vw":10.125,"n":12}'


def plan(sessions=("2022-01-03",)):
    return source.freeze_grouped_session_plan(sessions, calendar_sha256="a" * 64)


def envelope(rows=ROW):
    count = 0 if rows == "" else len(json.loads("[" + rows + "]"))
    return ('{"adjusted":false,"queryCount":' + str(count) + ',"request_id":"fabricated-1",'
            '"resultsCount":' + str(count) + ',"status":"OK","results":[' + rows + ']}').encode()


def qualify(raw=None, **overrides):
    frozen = plan()
    raw = envelope() if raw is None else raw
    kwargs = {"raw": raw, "raw_sha256": hash_bytes(raw),
              "request_sha256": hash_payload(source.request_descriptor(frozen, 1)),
              "started_at": "2026-10-13T01:00:00Z", "received_at": "2026-10-13T01:00:01Z"}
    kwargs.update(overrides)
    return source.qualify_grouped_response(frozen, 1, **kwargs)


def test_exact_rational_raw_volume_not_float_or_integer_rounding():
    payload = qualify().to_payload()
    row = payload["rows"][0]
    assert row[6] == {"source_number_token": "9007199254740993.25",
                      "numerator": "36028797018963973", "denominator": "4"}
    assert row[2]["numerator"] == "37" and row[2]["denominator"] == "4"
    assert row[1] == 1641254400000
    assert payload["query_session"] == "2022-01-03"
    assert payload["currency"] is None and payload["native_identity_binding"] is None
    assert payload["authority"]["price_volume_admitted"] is False
    assert payload["authority"]["outcome_looks"] == payload["authority"]["qc_attempts"] == 0


def test_zero_volume_and_missing_optional_fields_not_synthetic_missing_bar():
    payload = qualify(envelope('{"T":"SAMPLE","o":1,"h":1,"l":1,"c":1,"v":0,"t":1641254400000}')).to_payload()
    assert payload["rows"][0][6]["numerator"] == "0"
    assert payload["rows"][0][7:10] == [None, None, False]
    assert payload["rows"][0][-1] == []
    assert qualify(envelope("")).to_payload()["rows"] == []


@pytest.mark.parametrize("field,value", [("o", '"9.25"'), ("v", '"2"'), ("v", "NaN"),
                                         ("v", "Infinity"), ("v", "-1"), ("v", "1e999"),
                                         ("o", "0"), ("n", "1.5"), ("t", "true"), ("t", "1641254400000.0")])
def test_bad_numeric_cell_preserves_row_and_raw_origin(field, value):
    original = {"o": "9.25", "v": "9007199254740993.25", "n": "12", "t": "1641254400000"}[field]
    raw = envelope(ROW.replace('"' + field + '":' + original, '"' + field + '":' + value))
    payload = qualify(raw).to_payload()
    assert len(payload["rows"]) == 1 and payload["rows"][0][-1]
    assert payload["row_origins"] == [{"row_index": 0, "raw_sha256": hash_bytes(raw)}]


@pytest.mark.parametrize("rows", [ROW.replace('"h":12', '"h":8'),
                                  ROW.replace('"l":8', '"l":11'),
                                  ROW.replace('"T":"SAMPLE"', '"T":" SAMPLE"'),
                                  ROW[:-1] + ',"otc":true}',
                                  ROW[:-1] + ',"currency":"USD"}', "null"])
def test_invalid_row_not_dropped_or_admitted(rows):
    payload = qualify(envelope(rows)).to_payload()
    assert len(payload["rows"]) == 1 and payload["rows"][0][-1]
    assert payload["authority"]["historical_identity_admitted"] is False


def test_duplicate_and_malformed_identifiable_peers_both_fenced():
    malformed = ROW[:-1] + ',"v":4}'
    payload = qualify(envelope(ROW + "," + malformed)).to_payload()
    assert payload["duplicate_groups"] == [{"ticker": "SAMPLE", "row_indices": [0, 1]}]
    for row in payload["rows"]:
        assert "duplicate_or_malformed_identifiable_ticker_peer" in row[-1]
    assert "duplicate_row_JSON_key" in payload["rows"][1][-1]


def test_duplicate_ticker_fields_fence_all_known_collision_tokens():
    malformed = ROW.replace('"T":"SAMPLE"', '"T":"SAMPLE","T":"OTHER"')
    other = ROW.replace("SAMPLE", "OTHER")
    payload = qualify(envelope(malformed + "," + other)).to_payload()
    assert payload["rows"][0][0] is None
    assert payload["duplicate_groups"] == [{"ticker": "OTHER", "row_indices": [0, 1]}]
    assert all("duplicate_or_malformed_identifiable_ticker_peer" in row[-1] for row in payload["rows"])


@pytest.mark.parametrize("change", [lambda raw: raw[:-1] + b',"status":"OK"}',
                                    lambda raw: raw[:-1] + b',"next_url":"https://outside.invalid"}',
                                    lambda raw: raw.replace(b'"adjusted":false', b'"adjusted":true'),
                                    lambda raw: raw.replace(b'"resultsCount":1', b'"resultsCount":2'),
                                    lambda raw: raw.replace(b'"queryCount":1', b'"queryCount":true'),
                                    lambda raw: raw.replace(b'"status":"OK"', b'"status":"ERROR"')])
def test_bad_envelope_or_paging_refused(change):
    with pytest.raises(source.GroupedMarketError):
        qualify(change(envelope()))


@pytest.mark.parametrize("overrides", [{"raw_sha256": "b" * 64}, {"request_sha256": "b" * 64},
                                       {"http_status": True}, {"http_status": 404},
                                       {"content_type": "text/html"},
                                       {"received_at": "2026-10-13T00:59:59Z"},
                                       {"started_at": "2026-10-13T01:00:00"}])
def test_response_custody_status_and_chronology_refused(overrides):
    with pytest.raises(source.GroupedMarketError):
        qualify(**overrides)


@pytest.mark.parametrize("sessions", [("2022-01-03", "2022-01-03"), ("2022-01-04", "2022-01-03"),
                                      ("2026-09-01",), ("2022-01-03suffix",), ()])
def test_bad_session_plan_refused(sessions):
    with pytest.raises(source.GroupedMarketError):
        plan(sessions)


def test_sealed_report_and_plan_detached_payload_and_reflective_change_refused():
    frozen = plan()
    payload = frozen.to_payload()
    payload["request_count"] = 99
    assert frozen.to_payload()["request_count"] == 1
    result = qualify()
    detached = result.to_payload()
    detached["authority"]["price_volume_admitted"] = True
    assert result.to_payload()["authority"]["price_volume_admitted"] is False
    object.__setattr__(result, "_json", result._json + " ")
    with pytest.raises(source.GroupedMarketError, match="sealed_grouped_report_changed"):
        result.to_bytes()
    object.__setattr__(frozen, "_sessions", ("2022-01-04",))
    with pytest.raises(source.GroupedMarketError, match="sealed_grouped_plan_changed"):
        frozen.sessions()


def test_fixed_descriptor_has_no_symbol_filter_and_no_query_secret():
    request = source.request_descriptor(plan(), 1)
    assert request["url"] == source.ENDPOINT + "2022-01-03"
    assert request["params"] == {"adjusted": "false", "include_otc": "false"}
    assert "apikey" not in json.dumps(request)
    with pytest.raises(source.GroupedMarketError):
        source.request_descriptor(plan(), True)


def local_midnight_milliseconds(at):
    value = datetime.fromisoformat(at).replace(tzinfo=ZoneInfo("America/New_York"))
    return int(value.timestamp()) * 1000


@pytest.mark.parametrize("at", ["2022-01-03T00:00:00", "2022-01-03T19:59:59", "2022-01-04T00:00:00"])
def test_requested_day_and_both_midnight_metadata_conventions_preserved(at):
    timestamp = local_midnight_milliseconds(at)
    payload = qualify(envelope(ROW.replace("1641254400000", str(timestamp)))).to_payload()
    assert payload["rows"][0][1] == timestamp and payload["rows"][0][-1] == []
    assert payload["authority"]["original_availability_known"] is False


@pytest.mark.parametrize("timestamp", [local_midnight_milliseconds("2022-01-02T23:59:59"),
                                      local_midnight_milliseconds("2022-01-04T00:00:01"),
                                      local_midnight_milliseconds("2026-09-02T00:00:00")])
def test_recognizable_other_day_window_timestamp_refused(timestamp):
    with pytest.raises(source.GroupedMarketError, match="window_timestamp_outside_query_day"):
        qualify(envelope(ROW.replace("1641254400000", str(timestamp))))


def test_last_august_day_next_midnight_is_boundary_not_september_price():
    frozen = plan(("2026-08-31",))
    timestamp = local_midnight_milliseconds("2026-09-01T00:00:00")
    raw = envelope(ROW.replace("1641254400000", str(timestamp)))
    payload = source.qualify_grouped_response(frozen, 1, raw=raw, raw_sha256=hash_bytes(raw),
              request_sha256=hash_payload(source.request_descriptor(frozen, 1)),
              started_at="2026-10-13T01:00:00Z", received_at="2026-10-13T01:00:01Z").to_payload()
    assert payload["query_session"] == "2026-08-31" and payload["rows"][0][1] == timestamp


@pytest.mark.parametrize("encoding", ["integer", "string", "decimal", "duplicate"])
def test_protected_timestamp_in_malformed_identifiable_peer_still_refused(encoding):
    timestamp = local_midnight_milliseconds("2026-09-02T00:00:00")
    value = str(timestamp) if encoding != "string" else '"' + str(timestamp) + '"'
    if encoding == "decimal":
        value += ".0"
    row = ROW.replace("1641254400000", value)
    if encoding == "duplicate":
        row = ROW[:-1] + ',"t":' + value + "}"
    with pytest.raises(source.GroupedMarketError, match="window_timestamp_outside_query_day"):
        qualify(envelope(row))
