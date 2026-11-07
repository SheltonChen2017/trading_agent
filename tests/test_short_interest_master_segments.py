"""Fabricated-only private-report segmentation; never source fitness evidence."""
from __future__ import annotations

import dataclasses
import io
import json
import zipfile

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf.sharadar_securities_master import (
    CapturedSharadarMasterArchive, TABLES, qualification_protocol,
    qualify_sharadar_securities_master, request_sha256,
)
from research.short_interest_etf.sharadar_master_segments import (
    MAXIMUM_PART_BYTES, MAXIMUM_PARTS, MAXIMUM_REPORT_BYTES, PROTOCOL_SHA256,
    MasterReportIndex, MasterReportPart, MasterReportProvenance, SegmentedMasterReport,
    SharadarMasterSegmentsError, _load_canonical, _total, build_index_for_parts, decode_report, encode_report,
    segment_protocol,
)

CLOCK = "2026-10-11T20:00:00Z"


def provenance():
    return MasterReportProvenance("a" * 64, "b" * 64, "c" * 64, CLOCK)


@pytest.fixture(scope="module")
def report_bytes():
    captures = []
    required = qualification_protocol()["required_headers"]
    for table in TABLES:
        content = ",".join(required[table]) + "\n"
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr(zipfile.ZipInfo(table + ".csv", (2001, 1, 1, 0, 0, 0)), content)
        captures.append(CapturedSharadarMasterArchive(table, stream.getvalue(), request_sha256("download-" + table)))
    payload = qualify_sharadar_securities_master(tuple(captures), retrieved_at=CLOCK).to_payload()
    return canonical_json(payload).encode("utf-8")


def encoded(payload):
    payload["report_sha256"] = hash_payload({key: value for key, value in payload.items() if key != "report_sha256"})
    return canonical_json(payload).encode("utf-8")


def test_pinned_detached_protocol_and_one_part_exact_report_roundtrip(report_bytes):
    policy = segment_protocol()
    assert hash_payload(policy) == PROTOCOL_SHA256 == "a5f158170fcf3803664a93f1f7bdb74b3895729d4e0ed4a3a32b14ba869a3abd"
    assert MAXIMUM_PART_BYTES == 32 * 1024 * 1024 and MAXIMUM_PARTS == 64
    assert MAXIMUM_REPORT_BYTES == 2 * 1024 * 1024 * 1024
    policy["authority"]["source_admitted"] = True
    assert segment_protocol()["authority"]["source_admitted"] is False
    result = encode_report(report_bytes, provenance=provenance())
    assert result.parts == (report_bytes,)
    assert result.index.report_bytes_sha256 == hash_bytes(report_bytes)
    assert decode_report(result.index, result.parts) == report_bytes
    restored = MasterReportIndex.from_bytes(result.index.to_bytes())
    assert restored.to_payload() == result.index.to_payload()
    assert build_index_for_parts(result.parts, provenance=provenance()) == result.index
    assert restored.to_payload()["provenance"]["origin_provider_requests_consumed"] == 12
    assert restored.to_payload()["provenance"]["origin_capture_refusal"] == "private_report_size_limit"
    assert restored.to_payload()["authority"]["new_provider_requests"] == 0
    assert restored.to_payload()["authority"]["source_semantics_requalified"] is False


@pytest.fixture(scope="module")
def large_report(report_bytes):
    # An opaque fabricated lexical string crosses a real production part
    # boundary. Codec integrity does not requalify field/source semantics.
    payload = json.loads(report_bytes)
    captured = payload["tables"][2]
    raw_cells = [""] * len(captured["headers"])
    raw_cells[0] = "fabricated-public-padding:" + "x" * MAXIMUM_PART_BYTES
    origin = {"archive_sha256": captured["archive_sha256"], "CSV_sha256": captured["CSV_sha256"],
              "row_index": 0, "raw_record_sha256": hash_payload({"CSV_sha256": captured["CSV_sha256"], "row_index": 0})}
    captured["rows"] = [{"origin": origin, "raw_cells": raw_cells, "status": "refused",
                         "normalized": None, "refusal_reason": "fabricated_opaque_lexical_fixture_not_source_admission"}]
    captured["input_row_count"] = 1
    raw = encoded(payload)
    assert len(raw) > MAXIMUM_PART_BYTES
    return raw, encode_report(raw, provenance=provenance())


def test_real_32MiB_boundary_order_lengths_hashes_and_exact_complete_bytes(large_report):
    raw, result = large_report
    assert len(result.parts) == 2
    assert len(result.parts[0]) == MAXIMUM_PART_BYTES
    assert 0 < len(result.parts[1]) < MAXIMUM_PART_BYTES
    assert [part.position for part in result.index.parts] == [0, 1]
    assert [part.bytes_sha256 for part in result.index.parts] == [hash_bytes(part) for part in result.parts]
    assert decode_report(result.index, result.parts) == raw
    assert json.loads(raw)["authority"]["source_admitted"] is False


@pytest.mark.parametrize("change", ["reorder", "duplicate", "missing", "extra", "truncate", "flip", "mutable"])
def test_segment_reorder_duplicate_omission_extension_truncation_and_bit_change_refuse(large_report, change):
    _, result = large_report
    first, last = result.parts
    changes = {"reorder": (last, first), "duplicate": (first, first), "missing": (first,),
               "extra": (first, first, last), "truncate": (first, last[:-1]),
               "flip": (b"X" + first[1:], last), "mutable": [first, last]}
    with pytest.raises(SharadarMasterSegmentsError):
        decode_report(result.index, changes[change])


@pytest.mark.parametrize("value", [True, 0, -1, MAXIMUM_REPORT_BYTES + 1, 1.0, "1"])
def test_total_bytes_are_bounded_before_join_or_numeric_coercion(value):
    with pytest.raises(SharadarMasterSegmentsError):
        _total(value)


def test_exact_total_limit_and_boolean_part_records_do_not_need_large_allocations():
    assert _total(MAXIMUM_REPORT_BYTES) == MAXIMUM_REPORT_BYTES
    for fields in ((True, 1, "a" * 64), (0, True, "a" * 64), (MAXIMUM_PARTS, 1, "a" * 64),
                   (0, MAXIMUM_PART_BYTES + 1, "a" * 64)):
        with pytest.raises(SharadarMasterSegmentsError):
            MasterReportPart(*fields)


@pytest.mark.parametrize("mutation", ["schema", "protocol", "report_hash", "capture_hash", "source_authority",
    "counter_bool", "row_count_bool", "unknown_field", "noncanonical", "duplicate_key", "float", "nonfinite"])
def test_report_schema_digest_closed_authority_strict_JSON_and_no_normalization(report_bytes, mutation):
    payload = json.loads(report_bytes)
    if mutation == "schema": payload["schema"] = "other"
    elif mutation == "protocol": payload["protocol_sha256"] = "a" * 64
    elif mutation == "capture_hash": payload["capture_identity_sha256"] = "a" * 64
    elif mutation == "source_authority": payload["authority"]["source_admitted"] = True
    elif mutation == "counter_bool": payload["authority"]["actual_outcome_looks"] = False
    elif mutation == "row_count_bool": payload["tables"][0]["input_row_count"] = False
    elif mutation == "unknown_field": payload["extra"] = "never_source_admission"
    elif mutation == "float": payload["tables"][0]["input_row_count"] = 0.0
    raw = encoded(payload)
    if mutation == "report_hash": raw = raw.replace(payload["report_sha256"].encode(), b"a" * 64)
    elif mutation == "noncanonical": raw += b"\n"
    elif mutation == "duplicate_key": raw = b'{"schema":"duplicate",' + raw[1:]
    elif mutation == "nonfinite": raw = raw[:-1] + b',"bad":NaN}'
    with pytest.raises(SharadarMasterSegmentsError):
        encode_report(raw, provenance=provenance())


@pytest.mark.parametrize("field", ["report_bytes_sha256", "report_payload_sha256", "capture_identity_sha256"])
def test_validly_resealed_wrong_index_bindings_cannot_admit_report_bytes(report_bytes, field):
    result = encode_report(report_bytes, provenance=provenance())
    wrong = dataclasses.replace(result.index, **{field: "f" * 64})
    with pytest.raises(SharadarMasterSegmentsError):
        decode_report(wrong, result.parts)


def test_validly_resealed_part_digest_and_nonfinal_short_part_cannot_bypass_layout(report_bytes):
    result = encode_report(report_bytes, provenance=provenance())
    wrong_part = dataclasses.replace(result.index.parts[0], bytes_sha256="f" * 64)
    wrong_index = dataclasses.replace(result.index, parts=(wrong_part,))
    with pytest.raises(SharadarMasterSegmentsError, match="part_length_or_digest"):
        decode_report(wrong_index, result.parts)
    with pytest.raises(SharadarMasterSegmentsError, match="part_layout"):
        dataclasses.replace(result.index, report_byte_length=2,
                            parts=(MasterReportPart(0, 1, "a" * 64), MasterReportPart(1, 1, "b" * 64)))


@pytest.mark.parametrize("raw", [b'{"number":1.0}', b'{"number":NaN}', b'{"nested":{"number":0.01}}'])
def test_strict_JSON_number_parser_refuses_float_at_every_depth_before_envelope_interpretation(raw):
    with pytest.raises(SharadarMasterSegmentsError, match="floating_or_nonfinite"):
        _load_canonical(raw, 1024)


def test_clock_anchor_source_and_finalizer_provenance_and_index_are_immutable_detached(report_bytes):
    source = provenance()
    result = encode_report(report_bytes, provenance=source)
    changed_clock = dataclasses.replace(source, reconstruction_anchor_utc="2026-10-11T20:00:01Z")
    with pytest.raises(SharadarMasterSegmentsError, match="anchor_mismatch"):
        encode_report(report_bytes, provenance=changed_clock)
    payload = result.index.to_payload()
    payload["parts"].clear(); payload["authority"]["source_admitted"] = True
    assert len(result.index.to_payload()["parts"]) == 1
    object.__setattr__(source, "source_code_identity_sha256", "f" * 64)
    with pytest.raises(SharadarMasterSegmentsError, match="identity_changed"):
        decode_report(result.index, result.parts)


def test_index_parse_rejects_extra_fields_mutated_authority_or_wrong_digest(report_bytes):
    index = encode_report(report_bytes, provenance=provenance()).index
    for change in ("extra", "authority", "authority_integer", "digest", "duplicate"):
        payload = index.to_payload()
        if change == "extra": payload["extra"] = True
        elif change == "authority": payload["authority"]["source_admitted"] = True
        elif change == "authority_integer": payload["authority"]["source_admitted"] = 0
        elif change == "digest": payload["index_sha256"] = "f" * 64
        raw = canonical_json(payload).encode()
        if change == "duplicate": raw = b'{"schema":"duplicate",' + raw[1:]
        with pytest.raises(SharadarMasterSegmentsError):
            MasterReportIndex.from_bytes(raw)


@pytest.mark.parametrize("value", ["{}", bytearray(b"{}"), memoryview(b"{}"), b"", True])
def test_only_exact_immutable_byte_reports_and_exact_provenance_are_allowed(value):
    with pytest.raises(SharadarMasterSegmentsError):
        encode_report(value, provenance=provenance())


def test_no_caller_permission_or_part_size_override_and_exact_contract_types(report_bytes):
    with pytest.raises(TypeError):
        encode_report(report_bytes, provenance=provenance(), part_size=1)
    with pytest.raises(SharadarMasterSegmentsError):
        encode_report(report_bytes, provenance={"source_admitted": True})
    class Child(MasterReportProvenance):
        pass
    with pytest.raises(SharadarMasterSegmentsError):
        Child("a" * 64, "b" * 64, "c" * 64, CLOCK)
    result = encode_report(report_bytes, provenance=provenance())
    with pytest.raises(SharadarMasterSegmentsError):
        SegmentedMasterReport(result.index, (report_bytes + b"X",))


@pytest.mark.parametrize("mutation", [
    "historical_intervals", "nested_mapping_admitted", "nested_effective_at", "nested_terminal_economics",
])
def test_nested_non_admission_semantics_are_closed_under_a_coherently_redigested_envelope(report_bytes, mutation):
    payload = json.loads(report_bytes)
    if mutation == "historical_intervals":
        payload["historical_ticker_intervals"] = [{"ticker": "X", "from": "2000-01-01", "to": "2001-01-01"}]
    elif mutation == "nested_mapping_admitted":
        payload["temporal_event_candidates"] = [{"historical_mapping_admitted": True}]
    elif mutation == "nested_effective_at":
        payload["temporal_event_candidates"] = [{"effective_at": "2026-01-01T00:00:00Z"}]
    else:
        payload["excluded_or_refused_STOCKS_rows"] = [{"row": {"terminal_economics_admitted": True}}]
    # The envelope digest, capture identity and top-level authority all stay coherent;
    # only the recursive non-admission rule stands between this forgery and acceptance.
    raw = encoded(payload)
    with pytest.raises(SharadarMasterSegmentsError, match="master_authority_changed"):
        encode_report(raw, provenance=provenance())
