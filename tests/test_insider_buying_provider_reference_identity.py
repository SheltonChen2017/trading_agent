"""Invented supplied snapshots only; no licensed rows or provider requests."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import weakref

import pytest

from data.hashing import hash_bytes
import research.insider_buying_provider_reference_identity as identity


def _row(**overrides):
    row = {column: "" for column in identity.DOCUMENTED_COLUMNS}
    row.update(table="stocks", permaticker="1001", ticker="FIXA", name="Invented company",
               exchange="NASDAQ", isdelisted="N", category="Domestic Common Stock",
               secfilings="https://www.sec.gov/edgar/browse/?CIK=123&owner=exclude",
               firstpricedate="2006-01-03", lastupdated="2026-10-05")
    row.update(overrides)
    return row


def _csv(rows, columns=identity.DOCUMENTED_COLUMNS):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(column, "") for column in columns])
    return output.getvalue().encode("utf-8")


def _sec(*pairs):
    return tuple(identity.SecIssuerTitle(cik, title) for cik, title in sorted(set(pairs)))


def _snapshot(raw, columns=identity.DOCUMENTED_COLUMNS, **overrides):
    data = dict(metadata_sha256=hash_bytes(raw), schema_sha256=identity.metadata_schema_sha256(columns),
                provider_vintage_id="invented-snapshot-20261006", observed_at_utc="2026-10-06T12:00:00Z", columns=columns)
    data.update(overrides)
    return identity.SharadarCurrentMetadataSnapshot(**data)


def _build(rows=(), *, raw=None, sec=None, columns=identity.DOCUMENTED_COLUMNS, chunks=None, snapshot=None):
    raw = _csv(rows, columns) if raw is None else raw
    sec = _sec(("0000000123", "Common Stock")) if sec is None else sec
    return identity.assess_sharadar_current_identity(metadata_chunks=iter([raw]) if chunks is None else chunks,
        snapshot=_snapshot(raw, columns) if snapshot is None else snapshot, sec_issuer_titles=iter(sec),
        expected_sec_inventory_sha256=identity.sec_issuer_title_inventory_sha256(sec))


def test_one_current_candidate_is_useful_but_never_pit_title_or_eligibility():
    report = _build([_row(cusips="invented-cusip", figi="invented-figi", relatedtickers="FAKEB")]).to_payload()
    assert report["accounting"]["metadata_rows"] == 1
    assert report["metadata_rows"][0]["issuer_cik_candidate"] == "0000000123"
    coverage = report["sec_identity_coverage"][0]
    assert coverage["provider_permaticker_candidates"] == ["1001"]
    assert coverage["security_title_raw"] == "Common Stock"
    assert coverage["exact_title_matching_performed"] is False
    assert coverage["identity_coverage_disposition"] == "one_current_share_class_candidate_not_corroborated"
    assert report["current_share_class_candidates"][0]["candidate_scope"] == "current-provider-share-class-only-not-pit"
    for flag in ("source_authenticated_here", "rights_authenticated_here", "point_in_time_verified",
                 "first_listing_verified", "canonical_eligibility_released", "qc_authorized"):
        assert report[flag] is False
    assert report["authorized_outcome_looks"] == report["consumed_outcome_looks"] == report["qc_jobs"] == 0
    assert report["metadata_rows"][0]["observed_dates"]["firstpricedate"] == "2006-01-03"
    assert not any("knowledge_at" in key or "first_listing" in key for key in report["metadata_rows"][0])


def test_current_aliases_cross_table_duplicates_and_two_classes_are_all_accounted():
    rows = [_row(), _row(), _row(table="fundamentals"), _row(ticker="FIXA.OLD"),
            _row(permaticker="1002", ticker="FIXB", isdelisted="Y")]
    report = _build(rows).to_payload()
    assert report["accounting"]["metadata_rows"] == 5
    assert report["accounting"]["duplicate_primary_key_rows"] == 1
    assert report["accounting"]["active_rows"] == 4 and report["accounting"]["delisted_rows"] == 1
    candidates = report["current_share_class_candidates"]
    assert candidates[0]["source_row_ordinals"] == [0, 1, 2, 3]
    assert candidates[0]["current_ticker_alias_observations"] == ["FIXA", "FIXA.OLD"]
    assert report["sec_identity_coverage"][0]["provider_permaticker_candidates"] == ["1001", "1002"]
    assert report["sec_identity_coverage"][0]["identity_coverage_disposition"] == "multiple_current_share_class_candidates"


@pytest.mark.parametrize("url", [
    "http://www.sec.gov/edgar/browse/?CIK=123", "https://sec.gov/edgar/browse/?CIK=123",
    "https://www.sec.gov.evil.example/edgar/browse/?CIK=123", "https://user@www.sec.gov/edgar/browse/?CIK=123",
    "https://www.sec.gov:443/edgar/browse/?CIK=123", "https://www.sec.gov/edgar/browse/?CIK=123#CIK=456",
    "https://www.sec.gov/edgar/browse/?CIK=123&CIK=456", "https://www.sec.gov/edgar/browse/?CIK=%31%32%33",
    "https://www.sec.gov/edgar/browse/?CIK=0000000000", "https://www.sec.gov/edgar/browse/?CIK=12345678901",
    "https://www.sec.gov/edgar/browse/?cik=123", "https://www.sec.gov/edgar/browse/?CIK=123&redirect=evil",
    "https://www.sec.gov/Archives/edgar/data/123/filing.xml", "https://www.sec.gov/cgi-bin/browse-edgar?CIK=123",
    "https://www.sec.gov/edgar/browse/?CIK=123 ", "https://www.sec.gov\\@evil.example/edgar/browse/?CIK=123",
])
def test_invalid_sec_urls_never_infer_cik_from_ticker_name_or_untrusted_ids(url):
    report = _build([_row(secfilings=url, name="CIK 0000000123", cusips="0000000123", figi="0000000123")]).to_payload()
    assert report["accounting"]["no_cik_rows"] == 1
    assert report["metadata_rows"][0]["issuer_cik_candidate"] is None
    assert report["sec_identity_coverage"][0]["provider_permaticker_candidates"] == []


def test_canonical_browse_edgar_cik_candidate_and_sec_title_exactness():
    raw_title = "Class A  Common Stock"
    report = _build([_row(secfilings="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000000123&type=&dateb=&owner=exclude&count=40")],
                    sec=_sec(("0000000123", raw_title))).to_payload()
    assert report["metadata_rows"][0]["issuer_cik_candidate"] == "0000000123"
    assert report["sec_identity_coverage"][0]["security_title_raw"] == raw_title
    assert "exact_sec_security_title_not_corroborated" in report["unresolved_gates"]


def test_conflicting_primary_key_or_permaticker_ciks_quarantines_candidate_not_rows():
    for altered in [_row(name="Other current company"), _row(table="fundamentals", secfilings="https://www.sec.gov/edgar/browse/?CIK=456")]:
        report = _build([_row(), altered]).to_payload()
        assert report["accounting"]["metadata_rows"] == 2
        assert report["current_share_class_candidates"][0]["current_provider_identity_conflicted"] is True
        assert report["sec_identity_coverage"][0]["provider_permaticker_candidates"] == []


def test_nonsecurity_missing_cik_and_unknown_delisting_are_retained():
    report = _build([_row(table="holdings_investor", isdelisted="", secfilings="", permaticker=""),
                     _row(isdelisted="maybe", secfilings="")]).to_payload()
    a = report["accounting"]
    assert a["metadata_rows"] == a["unknown_delisting_rows"] == a["no_cik_rows"] == 2
    assert a["nonsecurity_rows"] == 1
    assert len(report["metadata_rows"]) == 2
    assert all(row["canonical_eligibility_released"] is False for row in report["metadata_rows"])


def test_genuine_1024_rows_one_pass_chunk_stream_without_old_256_parent_limit():
    count = 1024
    rows = [_row(permaticker=str(100000 + i), ticker=f"FIX{i}", isdelisted="Y" if i % 2 else "N") for i in range(count)]
    raw = _csv(rows)
    consumed = []
    def chunks():
        for position in range(0, len(raw), 97):
            consumed.append(position)
            yield raw[position:position + 97]
    iterator = chunks()
    result = _build(raw=raw, chunks=iterator)
    assert result.to_payload()["accounting"]["metadata_rows"] == count
    assert len(result.to_payload()["current_share_class_candidates"]) == count
    assert len(result.to_payload()["sec_identity_coverage"][0]["provider_permaticker_candidates"]) == count
    assert next(iterator, None) is None
    assert len(consumed) == (len(raw) + 96) // 97


def test_multiline_unicode_fields_and_split_utf8_preserve_exact_raw_digest():
    raw = _csv([_row(name="Invented café\nquoted company")])
    chunks = (raw[position:position + 1] for position in range(len(raw)))
    report = _build(raw=raw, chunks=chunks).to_payload()
    assert report["metadata_rows"][0]["current_name"] == "Invented café\nquoted company"
    assert report["snapshot"]["metadata_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["accounting"]["metadata_bytes"] == len(raw)


def test_raw_digest_mismatch_refuses_after_consuming_and_accounting_stream():
    raw = _csv([_row()])
    snapshot = _snapshot(raw, metadata_sha256="a" * 64)
    iterator = iter([raw])
    with pytest.raises(identity.ProviderReferenceIdentityError, match="metadata byte anchor"):
        _build(raw=raw, snapshot=snapshot, chunks=iterator)
    assert next(iterator, None) is None


@pytest.mark.parametrize("malformed", [b"", b"table,permaticker\n", b"\xff\n", b"\xef\xbb\xbf" + _csv([_row()]),
    _csv([_row()]) + b"one,two\n", _csv([_row()]).replace(b"Invented company", b"bad\x00name"),
    _csv([_row()]).replace(b"Invented company", b'"unclosed')])
def test_malformed_csv_refuses_without_empty_success(malformed):
    with pytest.raises(identity.ProviderReferenceIdentityError):
        _build(raw=malformed)


def test_only_documented_reference_header_projection_not_prices_or_outcome_fields():
    columns = tuple(column for column in identity.DOCUMENTED_COLUMNS if column in identity.REQUIRED_COLUMNS)
    report = _build([_row()], columns=columns).to_payload()
    assert report["snapshot"]["ordered_columns"] == list(columns)
    for unknown in ("close", "return_20d", "api_key", "qc_symbol_id", "knowledge_at_utc"):
        with pytest.raises(identity.ProviderReferenceIdentityError, match="reference-only"):
            identity.metadata_schema_sha256(columns + (unknown,))


@pytest.mark.parametrize("bad", ["2026-10-06", "2026-10-06T12:00:00+00:00", "2026-10-06T12:00:00.000Z", "2026-13-06T12:00:00Z"])
def test_observation_timestamp_is_exact_capture_clock_not_historical_knowledge(bad):
    with pytest.raises(identity.ProviderReferenceIdentityError):
        _snapshot(_csv([_row()]), observed_at_utc=bad)


def test_sec_inventory_hash_order_duplicates_and_title_cik_validation():
    raw = _csv([_row()])
    record = identity.SecIssuerTitle("0000000123", "Common Stock")
    with pytest.raises(identity.ProviderReferenceIdentityError, match="duplicated"):
        identity.sec_issuer_title_inventory_sha256((record, record))
    with pytest.raises(identity.ProviderReferenceIdentityError, match="anchor differs"):
        identity.assess_sharadar_current_identity(metadata_chunks=iter([raw]), snapshot=_snapshot(raw),
            sec_issuer_titles=iter([record]), expected_sec_inventory_sha256="a" * 64)
    for cik, title in [("123", "Common Stock"), ("0000000000", "Common Stock"), ("0000000123", ""), ("0000000123", "bad\nraw")]:
        with pytest.raises(identity.ProviderReferenceIdentityError):
            identity.SecIssuerTitle(cik, title)


def test_reiterable_mutable_or_empty_chunks_refused():
    raw = _csv([_row()])
    for chunks in ([raw], iter([bytearray(raw)]), iter([b"", raw])):
        with pytest.raises(identity.ProviderReferenceIdentityError):
            _build(raw=raw, chunks=chunks)


def test_caps_are_effective_fail_closed_not_truncating_rows(monkeypatch):
    raw = _csv([_row(), _row(permaticker="1002", ticker="FIXB")])
    monkeypatch.setattr(identity, "MAX_METADATA_ROWS", 1)
    with pytest.raises(identity.ProviderReferenceIdentityError, match="row count"):
        _build(raw=raw)
    monkeypatch.setattr(identity, "MAX_METADATA_ROWS", 1_000_000)
    monkeypatch.setattr(identity, "MAX_METADATA_BYTES", len(raw) - 1)
    with pytest.raises(identity.ProviderReferenceIdentityError, match="byte profile"):
        _build(raw=raw)


def test_output_budget_refuses_before_retaining_an_unbounded_identity_inventory(monkeypatch):
    raw = _csv([_row()])
    monkeypatch.setattr(identity, "MAX_REPORT_BYTES", 1024)
    consumed = []
    def chunks():
        consumed.append(True)
        yield raw
    with pytest.raises(identity.ProviderReferenceIdentityError, match="SEC identity report"):
        _build(raw=raw, chunks=chunks())
    assert consumed == []


def test_unknown_unhashable_schema_members_refuse_cleanly():
    with pytest.raises(identity.ProviderReferenceIdentityError, match="reference-only"):
        identity.metadata_schema_sha256(identity.DOCUMENTED_COLUMNS + ([],))


def test_exact_factory_seal_no_mutable_equal_bytes_or_constructed_payload():
    result = _build([_row()])
    raw = result._bytes
    with pytest.raises(identity.ProviderReferenceIdentityError, match="factory result"):
        identity.SharadarCurrentIdentityAssessment(raw).to_payload()
    object.__setattr__(result, "_bytes", bytearray(raw))
    with pytest.raises(identity.ProviderReferenceIdentityError, match="factory result"):
        result.to_payload()
    object.__setattr__(result, "_bytes", raw + b" ")
    with pytest.raises(identity.ProviderReferenceIdentityError, match="factory result"):
        result.to_payload()


def test_factory_registry_does_not_retain_result_after_release():
    result = _build([_row()])
    ident, reference = id(result), weakref.ref(result)
    assert ident in identity._REGISTRY
    del result
    assert reference() is None and ident not in identity._REGISTRY


def test_snapshot_digest_and_canonical_output_are_stable_without_order_inference():
    rows = [_row(), _row(permaticker="1002", ticker="FIXB", secfilings="")]
    result = _build(rows)
    second = _build(rows)
    assert result.sha256 == second.sha256
    assert json.loads(result._bytes) == result.to_payload()
    assert result.to_payload()["metadata_rows"][1]["ordinal"] == 1
    assert result.to_payload()["metadata_rows"][1]["issuer_cik_candidate"] is None
