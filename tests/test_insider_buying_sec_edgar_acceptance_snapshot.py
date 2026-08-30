"""IB-1C tests for offline SEC acceptance-metadata snapshots.

All evidence in this module is synthetic.  These tests make no network call,
read no market outcome, and do not claim compatibility with an official SEC
metadata schema.  The caller-supplied profile is intentionally labelled as a
non-official QC fixture.
"""
from __future__ import annotations

import ast
import csv
import io
import json
import os
import stat
import warnings
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import (
    ALLOWED_SEC_TABLES,
    SecBulkSource,
    SecEdgarAcceptanceSnapshotError,
    SecEdgarAvailabilityRecord,
    SecEdgarAvailabilityRule,
    SecEdgarAvailabilityTier,
    SecEdgarMetadataSchemaProfile,
    SecEdgarMetadataSource,
    SecTsvSchemaProfile,
    SecTsvSchemaVariant,
    build_sec_bulk_parsed_snapshot,
    build_sec_edgar_acceptance_snapshot,
    load_sec_bulk_parsed_snapshot,
    load_sec_edgar_acceptance_snapshot,
    write_sec_bulk_snapshot,
)
from research.insider_buying import sec_edgar_acceptance_snapshot as acceptance_module


RAW_RETRIEVED = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)
METADATA_RETRIEVED = datetime(2026, 5, 5, 18, 0, tzinfo=timezone.utc)
RAW_COMMIT = "a" * 40
PARSED_COMMIT = "b" * 40
METADATA_COMMIT = "c" * 40
ACCEPTANCE_COMMIT = "d" * 40
RAW_SOURCE_URL = (
    "https://www.sec.gov/files/dera/data/insider-transactions-data-sets/"
    "2026q2_form345.zip"
)


class _MutableOffsetTimezone(tzinfo):
    def __init__(self, hours: int) -> None:
        self.offset = timedelta(hours=hours)

    def utcoffset(self, _value):
        return self.offset

    def dst(self, _value):
        return timedelta(0)

    def tzname(self, _value):
        return f"mutable-{self.offset}"

# Literal field vectors below are synthetic and intentionally non-official.
SUBMISSION_HEADERS = (
    "ACCESSION_NUMBER",
    "FILING_DATE",
    "PERIOD_OF_REPORT",
    "DOCUMENT_TYPE",
    "ISSUERCIK",
    "ISSUERNAME",
    "ISSUERTRADINGSYMBOL",
)
OWNER_HEADERS = (
    "ACCESSION_NUMBER",
    "RPTOWNERCIK",
    "RPTOWNERNAME",
    "ISDIRECTOR",
    "ISOFFICER",
)
TRANS_HEADERS = (
    "ACCESSION_NUMBER",
    "TRANS_SK",
    "TRANSACTIONDATE",
    "TRANSACTIONSHARES",
    "TRANSACTIONPRICEPERSHARE",
)

ACCESSION_A = "0000123456-26-000001"
ACCESSION_B = "0000123456-26-000002"
ACCESSION_C = "0000123456-26-000003"
ACCESSION_D = "0000123456-26-000004"
ACCESSIONS = (ACCESSION_A, ACCESSION_B, ACCESSION_C, ACCESSION_D)
FILING_DATES = {
    ACCESSION_A: "2026-05-01",
    ACCESSION_B: "2026-05-02",
    ACCESSION_C: "2026-05-03",
    ACCESSION_D: "2026-05-04",
}
FORM_TYPES = {
    ACCESSION_A: "4",
    ACCESSION_B: "4/A",
    ACCESSION_C: "5",
    ACCESSION_D: "3",
}
ACCEPTED_AT = {
    ACCESSION_A: "2026-05-01T17:30:00-04:00",
    ACCESSION_C: "2026-05-03T21:15:00+00:00",
}
METADATA_FIELDS = (
    "accession",
    "form",
    "filed",
    "accepted",
    "primary_url",
)


def _tsv(headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _tables(
    *,
    filing_dates: dict[str, str] | None = None,
    form_types: dict[str, str] | None = None,
    issuer_ciks: dict[str, str] | None = None,
) -> dict[str, bytes]:
    filing_dates = filing_dates or FILING_DATES
    form_types = form_types or FORM_TYPES
    issuer_ciks = issuer_ciks or {
        accession: "0000123456" for accession in ACCESSIONS
    }
    submissions = tuple(
        (
            accession,
            filing_dates[accession],
            "2026-04-29",
            form_types[accession],
            issuer_ciks[accession],
            "Synthetic Fixture Issuer",
            "SYN",
        )
        for accession in ACCESSIONS
    )
    return {
        "SUBMISSION.tsv": _tsv(SUBMISSION_HEADERS, submissions),
        "REPORTINGOWNER.tsv": _tsv(
            OWNER_HEADERS,
            ((ACCESSION_A, "0000000042", "Synthetic Owner", "1", "0"),),
        ),
        "NONDERIV_TRANS.tsv": _tsv(
            TRANS_HEADERS,
            ((ACCESSION_A, "0000007", "2026-04-29", "5000", "12.34"),),
        ),
    }


def _archive(tables: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for table_name in ALLOWED_SEC_TABLES:
            if table_name not in tables:
                continue
            info = zipfile.ZipInfo(table_name, date_time=(2026, 8, 20, 18, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Duplicate name")
                archive.writestr(info, tables[table_name])
    return stream.getvalue()


def _raw_source(**overrides) -> SecBulkSource:
    values = {
        "year": 2026,
        "quarter": 2,
        "source_url": RAW_SOURCE_URL,
        "git_commit": RAW_COMMIT,
        "retrieved_at": RAW_RETRIEVED,
    }
    values.update(overrides)
    return SecBulkSource(**values)


def _parsed_profile() -> SecTsvSchemaProfile:
    headers_by_table = {
        "SUBMISSION.tsv": SUBMISSION_HEADERS,
        "REPORTINGOWNER.tsv": OWNER_HEADERS,
        "NONDERIV_TRANS.tsv": TRANS_HEADERS,
    }
    variants = tuple(
        SecTsvSchemaVariant(
            schema_id=f"synthetic-{name.removesuffix('.tsv').lower()}-v1",
            table_name=name,
            headers=headers_by_table[name],
            source_row_key_headers=("TRANS_SK",) if name == "NONDERIV_TRANS.tsv" else (),
            valid_from_year=2026,
            valid_from_quarter=1,
            valid_through_year=2026,
            valid_through_quarter=4,
        )
        for name in ALLOWED_SEC_TABLES
        if name in headers_by_table
    )
    return SecTsvSchemaProfile(
        profile_id="synthetic-non-official-qc-tsv-v1",
        variants=variants,
    )


def _metadata_profile(**overrides) -> SecEdgarMetadataSchemaProfile:
    values = {
        "profile_id": "synthetic-non-official-qc-edgar-metadata-v1",
        "exact_fields": METADATA_FIELDS,
        "accession_number_field": "accession",
        "form_type_field": "form",
        "filing_date_field": "filed",
        "accepted_at_field": "accepted",
        "primary_document_url_field": "primary_url",
        "valid_from_year": 2026,
        "valid_from_quarter": 1,
        "valid_through_year": 2026,
        "valid_through_quarter": 4,
    }
    values.update(overrides)
    return SecEdgarMetadataSchemaProfile(**values)


def _metadata_payload(_accession: str, **overrides) -> dict[str, object]:
    values: dict[str, object] = {
        "accession": _accession,
        "form": FORM_TYPES[_accession],
        "filed": FILING_DATES[_accession],
        "accepted": ACCEPTED_AT[_accession],
        "primary_url": (
            "https://www.sec.gov/Archives/edgar/data/123456/"
            f"{_accession.replace('-', '')}/synthetic-primary.xml"
        ),
    }
    values.update(overrides)
    return values


def _metadata_bytes(_accession: str, **overrides) -> bytes:
    return (
        canonical_json(_metadata_payload(_accession, **overrides)) + "\n"
    ).encode("utf-8")


def _metadata_source(
    _accession: str,
    *,
    metadata_bytes: bytes | None = None,
    source_url: str | None = None,
    retrieved_at: datetime = METADATA_RETRIEVED,
    capture_git_commit: str = METADATA_COMMIT,
    **payload_overrides,
) -> SecEdgarMetadataSource:
    return SecEdgarMetadataSource(
        metadata_bytes=(
            metadata_bytes
            if metadata_bytes is not None
            else _metadata_bytes(_accession, **payload_overrides)
        ),
        source_url=(
            source_url
            or (
                "https://www.sec.gov/Archives/edgar/data/123456/"
                f"{_accession.replace('-', '')}/synthetic-metadata.json"
            )
        ),
        retrieved_at=retrieved_at,
        capture_git_commit=capture_git_commit,
    )


def _sources() -> tuple[SecEdgarMetadataSource, ...]:
    # B intentionally has no metadata source and must remain date-only.
    return (_metadata_source(ACCESSION_A), _metadata_source(ACCESSION_C))


def _upstream(
    tmp_path: Path,
    *,
    root_suffix: str = "",
    tables: dict[str, bytes] | None = None,
    raw_source: SecBulkSource | None = None,
) -> tuple[Path, Path]:
    raw_root = tmp_path / f"raw{root_suffix}"
    raw_identity = write_sec_bulk_snapshot(
        _archive(tables or _tables()), raw_source or _raw_source(), raw_root
    )
    raw_path = raw_root / raw_identity.snapshot_id
    parsed_root = tmp_path / f"parsed{root_suffix}"
    parsed_identity = build_sec_bulk_parsed_snapshot(
        raw_path,
        parsed_root,
        schema_profile=_parsed_profile(),
        parser_git_commit=PARSED_COMMIT,
    )
    return raw_path, parsed_root / parsed_identity.snapshot_id


def _build(
    tmp_path: Path,
    *,
    raw_path: Path | None = None,
    parsed_path: Path | None = None,
    sources: tuple[SecEdgarMetadataSource, ...] | None = None,
    metadata_profile: SecEdgarMetadataSchemaProfile | None = None,
    parser_git_commit: str = ACCEPTANCE_COMMIT,
    output_name: str = "acceptance",
):
    if raw_path is None or parsed_path is None:
        raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / output_name
    identity = build_sec_edgar_acceptance_snapshot(
        parsed_path,
        raw_path,
        output_root,
        sources=_sources() if sources is None else sources,
        metadata_profile=metadata_profile or _metadata_profile(),
        parser_git_commit=parser_git_commit,
    )
    bundle_path = output_root / f"{identity.snapshot_id}.json"
    assert bundle_path.is_file()
    return raw_path, parsed_path, bundle_path, identity


def _load(bundle_path: Path, parsed_path: Path, raw_path: Path):
    return load_sec_edgar_acceptance_snapshot(
        bundle_path,
        parsed_snapshot_directory=parsed_path,
        raw_snapshot_directory=raw_path,
    )


def _build_with_source_bytes(
    tmp_path: Path,
    metadata_bytes: bytes,
    *,
    source_url: str | None = None,
) -> None:
    raw_path, parsed_path = _upstream(tmp_path)
    source = _metadata_source(
        ACCESSION_A,
        metadata_bytes=metadata_bytes,
        source_url=source_url,
    )
    build_sec_edgar_acceptance_snapshot(
        parsed_path,
        raw_path,
        tmp_path / "acceptance",
        sources=(source, _metadata_source(ACCESSION_C)),
        metadata_profile=_metadata_profile(),
        parser_git_commit=ACCEPTANCE_COMMIT,
    )


def test_exact_acceptance_and_date_only_fallback_cover_every_upstream_accession(
    tmp_path,
):
    raw_path, parsed_path, bundle_path, identity = _build(tmp_path)
    loaded = _load(bundle_path, parsed_path, raw_path)
    parsed = load_sec_bulk_parsed_snapshot(
        parsed_path, raw_snapshot_directory=raw_path
    )

    assert loaded.identity == identity
    assert tuple(record.accession_number for record in loaded.records) == ACCESSIONS
    assert {record.accession_number for record in loaded.records} == {
        item.accession_number for item in parsed.accessions
    }
    by_accession = {record.accession_number: record for record in loaded.records}

    exact_a = by_accession[ACCESSION_A]
    assert (
        exact_a.availability_tier
        is SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
    )
    assert exact_a.accepted_at == datetime.fromisoformat(ACCEPTED_AT[ACCESSION_A])
    assert exact_a.filing_date == date(2026, 5, 1)
    assert (
        exact_a.next_open_rule
        is SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE
    )
    assert exact_a.metadata_source_sha256 == hash_bytes(_metadata_bytes(ACCESSION_A))
    assert exact_a.primary_document_url.endswith("synthetic-primary.xml")

    fallback = by_accession[ACCESSION_B]
    assert fallback.availability_tier is SecEdgarAvailabilityTier.FILING_DATE_FALLBACK
    assert fallback.accepted_at is None
    assert fallback.filing_date == date(2026, 5, 2)
    assert (
        fallback.next_open_rule
        is SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_FILING_DATE
    )
    assert fallback.primary_document_url is None
    assert fallback.metadata_source_sha256 is None

    exact_c = by_accession[ACCESSION_C]
    assert (
        exact_c.availability_tier
        is SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
    )
    assert exact_c.accepted_at == datetime.fromisoformat(ACCEPTED_AT[ACCESSION_C])
    assert all(record.submission_row_id for record in loaded.records)
    assert len(loaded.sources) == 2


def test_all_accessions_conservatively_fall_back_when_no_metadata_is_supplied(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    _, _, bundle_path, _ = _build(
        tmp_path,
        raw_path=raw_path,
        parsed_path=parsed_path,
        sources=(),
    )
    loaded = _load(bundle_path, parsed_path, raw_path)
    assert tuple(record.accession_number for record in loaded.records) == ACCESSIONS
    assert all(
        record.availability_tier
        is SecEdgarAvailabilityTier.FILING_DATE_FALLBACK
        for record in loaded.records
    )
    assert all(record.accepted_at is None for record in loaded.records)
    assert all(
        record.next_open_rule
        is SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_FILING_DATE
        for record in loaded.records
    )
    assert tuple(record.filing_date.isoformat() for record in loaded.records) == (
        FILING_DATES[ACCESSION_A],
        FILING_DATES[ACCESSION_B],
        FILING_DATES[ACCESSION_C],
        FILING_DATES[ACCESSION_D],
    )


def test_forms_3_4a_and_5_are_retained_without_amendment_or_xml_inference(tmp_path):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path)
    loaded = _load(bundle_path, parsed_path, raw_path)
    by_accession = {record.accession_number: record for record in loaded.records}
    assert by_accession[ACCESSION_B].document_type == "4/A"
    assert by_accession[ACCESSION_C].document_type == "5"
    assert by_accession[ACCESSION_D].document_type == "3"
    # The acceptance boundary preserves as-filed forms; it does not create an
    # amendment graph, parse XML, or classify a filing as eligible.
    assert not hasattr(by_accession[ACCESSION_B], "amends_accession")
    assert not hasattr(by_accession[ACCESSION_C], "transactions")


def test_transaction_date_never_becomes_public_availability(tmp_path):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path)
    loaded = _load(bundle_path, parsed_path, raw_path)
    record = next(item for item in loaded.records if item.accession_number == ACCESSION_A)

    assert record.filing_date != date(2026, 4, 29)
    assert "TRANSACTIONDATE" not in _metadata_profile().exact_fields
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="transaction"):
        _metadata_profile(
            exact_fields=("accession", "form", "filed", "transaction_date", "primary_url"),
            accepted_at_field="transaction_date",
        )


@pytest.mark.parametrize(
    ("payload_override", "match"),
    [
        ({"accession": ACCESSION_B}, "accession|duplicate"),
        ({"form": "3"}, "form|document"),
        ({"filed": "2026-05-02"}, "filing date|filed"),
    ],
)
def test_metadata_must_match_upstream_accession_form_and_filing_date(
    tmp_path, payload_override, match
):
    source = _metadata_source(ACCESSION_A, **payload_override)
    raw_path, parsed_path = _upstream(tmp_path)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match=match):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            tmp_path / "acceptance",
            sources=(source, _metadata_source(ACCESSION_C)),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert not tuple((tmp_path / "acceptance").glob("sec-edgar-acceptance-*.json"))


def test_deep_metadata_json_maps_recursion_to_the_public_refusal(tmp_path):
    deeply_nested = b"[" * 2_000 + b"0" + b"]" * 2_000
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="JSON|REFUSED"):
        _build_with_source_bytes(tmp_path, deeply_nested)
    assert not tuple((tmp_path / "acceptance").glob("sec-edgar-acceptance-*.json"))


def test_metadata_nesting_cap_runs_before_json_decoder(monkeypatch):
    source = _metadata_source(
        ACCESSION_A,
        metadata_bytes=b"[[0]]",
    )

    def decoder_must_not_run(*_args, **_kwargs):
        raise AssertionError("JSON decoder ran before the source nesting cap")

    monkeypatch.setattr(acceptance_module.json, "loads", decoder_must_not_run)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="JSON|REFUSED"):
        acceptance_module._parse_source_json(source, _metadata_profile())


def test_unknown_and_duplicate_metadata_evidence_refuse(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    unknown_accession = "0000999999-26-999999"
    compact_unknown = unknown_accession.replace("-", "")
    unknown_primary_url = (
        "https://www.sec.gov/Archives/edgar/data/999999/"
        f"{compact_unknown}/synthetic-primary.xml"
    )
    unknown_payload = _metadata_payload(
        ACCESSION_A,
        accession=unknown_accession,
        primary_url=unknown_primary_url,
    )
    unknown = _metadata_source(
        ACCESSION_A,
        metadata_bytes=(canonical_json(unknown_payload) + "\n").encode("utf-8"),
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/999999/"
            f"{compact_unknown}/synthetic-metadata.json"
        ),
    )
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="unknown|accession"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            tmp_path / "unknown",
            sources=(*_sources(), unknown),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )

    duplicate = _metadata_source(
        ACCESSION_A,
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/123456/"
            "000012345626000001/duplicate-metadata.json"
        ),
    )
    with pytest.raises(
        SecEdgarAcceptanceSnapshotError, match="duplicate|more than one"
    ):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            tmp_path / "duplicate",
            sources=(*_sources(), duplicate),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )


@pytest.mark.parametrize(
    "metadata_bytes",
    [
        b"{",
        b"[]\n",
        (
            b'{"accession":"x","accession":"y","form":"4",'
            b'"filed":"2026-05-01","accepted":"2026-05-01T17:30:00-04:00",'
            b'"primary_url":"https://example.test/x"}\n'
        ),
        b"\xff\xfe\x00\x00",
        (
            b'{"accession":"0000123456-26-000001","form":"4",'
            b'"filed":"2026-05-01","accepted":"2026-05-01T17:30:00-04:00",'
            b'"primary_url":"https://example.test/x"}\x00'
        ),
        (
            b'{"accession":{"nested":"0000123456-26-000001"},"form":"4",'
            b'"filed":"2026-05-01","accepted":"2026-05-01T17:30:00-04:00",'
            b'"primary_url":"https://example.test/x"}\n'
        ),
        (
            b'{"accession":"0000123456-26-000001","form":true,'
            b'"filed":"2026-05-01","accepted":"2026-05-01T17:30:00-04:00",'
            b'"primary_url":"https://example.test/x"}\n'
        ),
        (
            b'{"accession":"0000123456-26-000001","form":"4",'
            b'"filed":"2026-05-01","accepted":"2026-05-01T17:30:00-04:00",'
            b'"primary_url":"https://example.test/x","unknown":"value"}\n'
        ),
    ],
    ids=(
        "malformed",
        "top-level-array",
        "duplicate-key",
        "non-utf8",
        "nul",
        "nested",
        "boolean",
        "unknown-field",
    ),
)
def test_metadata_json_is_strict_flat_utf8_with_exact_unique_string_fields(
    tmp_path, metadata_bytes
):
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="REFUSED"):
        _build_with_source_bytes(tmp_path, metadata_bytes)
    # Supplied-but-invalid evidence must fail the whole build; it must never be
    # silently treated as absent Tier-C evidence.
    assert not tuple((tmp_path / "acceptance").glob("sec-edgar-acceptance-*.json"))


@pytest.mark.parametrize(
    "accepted",
    [
        "2026-05-01T17:30:00",
        "2026-05-01 17:30:00-04:00",
        "2026-05-01T17:30:00Z",
        "2026-05-01T17:30:00.123-04:00",
        "2026-05-01T17:30:00-00:00",
        "2026-05-01",
        "",
    ],
)
def test_acceptance_requires_nonblank_explicit_offset_second_resolution(
    tmp_path, accepted
):
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="accept|timestamp|offset"):
        _build_with_source_bytes(tmp_path, _metadata_bytes(ACCESSION_A, accepted=accepted))


def test_retrieval_cannot_predate_acceptance(tmp_path):
    source = _metadata_source(
        ACCESSION_A,
        retrieved_at=datetime(2026, 5, 1, 21, 29, 59, tzinfo=timezone.utc),
    )
    raw_path, parsed_path = _upstream(tmp_path)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="retriev|accept"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            tmp_path / "acceptance",
            sources=(source,),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert not tuple((tmp_path / "acceptance").glob("sec-edgar-acceptance-*.json"))


def test_mutated_timezone_cannot_change_frozen_retrieval_instant(tmp_path):
    mutable_zone = _MutableOffsetTimezone(1)
    source = _metadata_source(
        ACCESSION_A,
        retrieved_at=datetime(2026, 5, 1, 22, 0, tzinfo=mutable_zone),
    )
    assert source.retrieved_at_utc == "2026-05-01T21:00:00+00:00"
    assert source.retrieved_at == datetime(2026, 5, 1, 21, 0, tzinfo=timezone.utc)
    mutable_zone.offset = timedelta(hours=-1)
    assert source.retrieved_at == datetime(2026, 5, 1, 21, 0, tzinfo=timezone.utc)

    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="retrieval|acceptance"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=(source, _metadata_source(ACCESSION_C)),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    _assert_no_acceptance_bundle(output_root)


def test_frozen_retrieval_instant_survives_later_timezone_mutation(tmp_path):
    mutable_zone = _MutableOffsetTimezone(-1)
    source = _metadata_source(
        ACCESSION_A,
        retrieved_at=datetime(2026, 5, 1, 22, 0, tzinfo=mutable_zone),
    )
    assert source.retrieved_at_utc == "2026-05-01T23:00:00+00:00"
    assert source.retrieved_at == datetime(2026, 5, 1, 23, 0, tzinfo=timezone.utc)
    mutable_zone.offset = timedelta(hours=1)
    assert source.retrieved_at == datetime(2026, 5, 1, 23, 0, tzinfo=timezone.utc)

    raw_path, parsed_path = _upstream(tmp_path)
    _, _, bundle_path, _ = _build(
        tmp_path,
        raw_path=raw_path,
        parsed_path=parsed_path,
        sources=(source, _metadata_source(ACCESSION_C)),
        output_name="mutated-timezone",
    )
    loaded = _load(bundle_path, parsed_path, raw_path)
    assert loaded.sources[0].retrieved_at_utc == "2026-05-01T23:00:00+00:00"


@pytest.mark.parametrize(
    "retrieved_at",
    [
        datetime(2026, 5, 5, 18, 0),
        datetime(2026, 5, 5, 18, 0, 0, 1, tzinfo=timezone.utc),
        date(2026, 5, 5),
        True,
    ],
)
def test_metadata_retrieval_timestamp_must_be_an_aware_datetime(retrieved_at):
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="retriev|timestamp|datetime"):
        _metadata_source(ACCESSION_A, retrieved_at=retrieved_at)


def test_acceptance_on_prior_sec_filing_calendar_date_refuses(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="accept|filing date"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=(
                _metadata_source(
                    ACCESSION_A, accepted="2026-04-30T23:59:59-04:00"
                ),
                _metadata_source(ACCESSION_C),
            ),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert not tuple(output_root.glob("sec-edgar-acceptance-*.json"))


def test_acceptance_instant_cannot_predate_sec_filing_calendar_date(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="accept|filing"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=(
                _metadata_source(
                    ACCESSION_A, accepted="2026-05-01T00:00:00+14:00"
                ),
                _metadata_source(ACCESSION_C),
            ),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert not tuple(output_root.glob("sec-edgar-acceptance-*.json"))


def test_conservative_sec_floor_not_source_wall_date_controls_acceptance(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    same_sec_day = "2026-04-30T22:00:00-10:00"
    _, _, bundle_path, _ = _build(
        tmp_path,
        raw_path=raw_path,
        parsed_path=parsed_path,
        sources=(
            _metadata_source(ACCESSION_A, accepted=same_sec_day),
            _metadata_source(ACCESSION_C),
        ),
    )

    loaded = _load(bundle_path, parsed_path, raw_path)
    record = next(item for item in loaded.records if item.accession_number == ACCESSION_A)
    assert record.accepted_at == datetime.fromisoformat(same_sec_day)
    assert (
        record.availability_tier
        is SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
    )
    assert (
        record.next_open_rule
        is SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE
    )


@pytest.mark.parametrize(
    ("accepted", "refuses"),
    (
        ("2026-05-01T04:59:59+00:00", True),
        ("2026-05-01T05:00:00+00:00", False),
    ),
)
def test_conservative_sec_filing_day_utc_floor_is_exact(
    tmp_path, accepted, refuses
):
    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"
    call = lambda: build_sec_edgar_acceptance_snapshot(
        parsed_path,
        raw_path,
        output_root,
        sources=(
            _metadata_source(ACCESSION_A, accepted=accepted),
            _metadata_source(ACCESSION_C),
        ),
        metadata_profile=_metadata_profile(),
        parser_git_commit=ACCEPTANCE_COMMIT,
    )
    if refuses:
        with pytest.raises(SecEdgarAcceptanceSnapshotError, match="accept|filing"):
            call()
        assert not tuple(output_root.glob("sec-edgar-acceptance-*.json"))
    else:
        identity = call()
        loaded = _load(
            output_root / f"{identity.snapshot_id}.json", parsed_path, raw_path
        )
        assert loaded.records[0].accepted_at == datetime.fromisoformat(accepted)


def test_public_availability_record_enforces_the_sec_filing_day_window():
    values = {
        "accession_number": ACCESSION_A,
        "document_type": "4",
        "submission_row_id": "0" * 64,
        "filing_date": date(2026, 5, 1),
        "availability_tier": SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP,
        "next_open_rule": SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE,
        "primary_document_url": (
            "https://www.sec.gov/Archives/edgar/data/123456/"
            f"{ACCESSION_A.replace('-', '')}/synthetic-primary.xml"
        ),
        "metadata_source_sha256": "1" * 64,
    }
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="exact|accept|filing"):
        SecEdgarAvailabilityRecord(
            **values,
            accepted_at=datetime.fromisoformat("2026-05-01T00:00:00+14:00"),
        )
    record = SecEdgarAvailabilityRecord(
        **values,
        accepted_at=datetime.fromisoformat("2026-05-01T05:00:00+00:00"),
    )
    assert record.accepted_at == datetime.fromisoformat("2026-05-01T05:00:00+00:00")
    record = SecEdgarAvailabilityRecord(
        **values,
        accepted_at=datetime.fromisoformat("2026-05-02T04:59:59+00:00"),
    )
    assert record.accepted_at == datetime.fromisoformat("2026-05-02T04:59:59+00:00")
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="exact|accept|filing"):
        SecEdgarAvailabilityRecord(
            **values,
            accepted_at=datetime.fromisoformat("2026-05-02T05:00:00+00:00"),
        )


@pytest.mark.parametrize(
    ("tier", "overrides"),
    [
        ("exact", {"accepted_at": None}),
        (
            "exact",
            {
                "next_open_rule": (
                    SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_FILING_DATE
                )
            },
        ),
        ("exact", {"primary_document_url": None}),
        ("exact", {"metadata_source_sha256": None}),
        ("exact", {"metadata_source_sha256": "g" * 64}),
        ("fallback", {"accepted_at": datetime(2026, 5, 1, 21, 30, tzinfo=timezone.utc)}),
        (
            "fallback",
            {
                "next_open_rule": (
                    SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE
                )
            },
        ),
        (
            "fallback",
            {
                "primary_document_url": (
                    "https://www.sec.gov/Archives/edgar/data/123456/"
                    f"{ACCESSION_A.replace('-', '')}/synthetic-primary.xml"
                )
            },
        ),
        ("fallback", {"metadata_source_sha256": "a" * 64}),
    ],
)
def test_public_availability_record_refuses_inconsistent_tier_evidence(
    tier, overrides
):
    common = {
        "accession_number": ACCESSION_A,
        "document_type": "4",
        "submission_row_id": "a" * 64,
        "filing_date": date(2026, 5, 1),
    }
    if tier == "exact":
        values = {
            **common,
            "availability_tier": (
                SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
            ),
            "next_open_rule": SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE,
            "accepted_at": datetime(2026, 5, 1, 21, 30, tzinfo=timezone.utc),
            "primary_document_url": (
                "https://www.sec.gov/Archives/edgar/data/123456/"
                f"{ACCESSION_A.replace('-', '')}/synthetic-primary.xml"
            ),
            "metadata_source_sha256": "a" * 64,
        }
    else:
        values = {
            **common,
            "availability_tier": SecEdgarAvailabilityTier.FILING_DATE_FALLBACK,
            "next_open_rule": (
                SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_FILING_DATE
            ),
            "accepted_at": None,
            "primary_document_url": None,
            "metadata_source_sha256": None,
        }
    values.update(overrides)

    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="REFUSED|availability"):
        SecEdgarAvailabilityRecord(**values)


@pytest.mark.parametrize(
    "accepted_at",
    [
        datetime(
            2026,
            5,
            1,
            22,
            0,
            tzinfo=_MutableOffsetTimezone(-1),
        ),
        datetime(
            2026,
            5,
            1,
            23,
            0,
            30,
            tzinfo=timezone(timedelta(seconds=30)),
        ),
    ],
)
def test_public_availability_record_freezes_and_round_trips_acceptance_instant(
    accepted_at,
):
    record = SecEdgarAvailabilityRecord(
        accession_number=ACCESSION_A,
        document_type="4",
        submission_row_id="a" * 64,
        filing_date=date(2026, 5, 1),
        availability_tier=SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP,
        next_open_rule=SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE,
        accepted_at=accepted_at,
        primary_document_url=(
            "https://www.sec.gov/Archives/edgar/data/123456/"
            f"{ACCESSION_A.replace('-', '')}/synthetic-primary.xml"
        ),
        metadata_source_sha256="a" * 64,
    )
    payload = record.to_payload()
    if isinstance(accepted_at.tzinfo, _MutableOffsetTimezone):
        accepted_at.tzinfo.offset = timedelta(hours=14)

    assert record.accepted_at.tzinfo is timezone.utc
    assert record.to_payload() == payload
    assert acceptance_module._record_from_payload(payload) == record


def test_acceptance_later_than_filing_date_remains_exact_and_conservative(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    later = "2026-05-02T00:00:00-04:00"
    _, _, bundle_path, _ = _build(
        tmp_path,
        raw_path=raw_path,
        parsed_path=parsed_path,
        sources=(
            _metadata_source(ACCESSION_A, accepted=later),
            _metadata_source(ACCESSION_C),
        ),
    )
    loaded = _load(bundle_path, parsed_path, raw_path)
    record = next(item for item in loaded.records if item.accession_number == ACCESSION_A)
    assert record.filing_date == date(2026, 5, 1)
    assert record.accepted_at == datetime.fromisoformat(later)
    assert (
        record.availability_tier
        is SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
    )
    assert (
        record.next_open_rule
        is SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE
    )


@pytest.mark.parametrize(
    ("accepted", "refuses"),
    [
        ("2026-05-02T04:59:59+00:00", False),
        ("2026-05-02T05:00:00+00:00", True),
        ("2026-06-01T12:00:00+00:00", True),
    ],
)
def test_exact_acceptance_cannot_extend_beyond_filing_day_window(
    tmp_path, accepted, refuses
):
    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"

    def call():
        return build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=(
                _metadata_source(ACCESSION_A, accepted=accepted),
                _metadata_source(ACCESSION_C),
            ),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )

    if refuses:
        with pytest.raises(SecEdgarAcceptanceSnapshotError, match="accept|filing"):
            call()
        _assert_no_acceptance_bundle(output_root)
    else:
        identity = call()
        loaded = _load(
            output_root / f"{identity.snapshot_id}.json", parsed_path, raw_path
        )
        assert loaded.records[0].accepted_at == datetime.fromisoformat(accepted)


@pytest.mark.parametrize("filing_date", ["", "2026-02-30", "05/01/2026"])
def test_missing_or_malformed_upstream_filing_date_refuses_whole_build(
    tmp_path, filing_date
):
    filing_dates = dict(FILING_DATES)
    filing_dates[ACCESSION_B] = filing_date
    raw_path, parsed_path = _upstream(
        tmp_path, tables=_tables(filing_dates=filing_dates)
    )
    output_root = tmp_path / "acceptance"
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="filing date|FILING_DATE"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert not tuple(output_root.glob("sec-edgar-acceptance-*.json"))


@pytest.mark.parametrize(
    "filing_date",
    ("2025-05-01", "2026-03-31", "2026-07-01"),
)
def test_upstream_filing_date_must_match_snapshot_quarter_and_accession_year(
    tmp_path, filing_date
):
    filing_dates = dict(FILING_DATES)
    filing_dates[ACCESSION_B] = filing_date
    raw_path, parsed_path = _upstream(
        tmp_path, tables=_tables(filing_dates=filing_dates)
    )
    output_root = tmp_path / "acceptance"
    with pytest.raises(
        SecEdgarAcceptanceSnapshotError,
        match="filing date|snapshot quarter|accession year",
    ):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert not tuple(output_root.glob("sec-edgar-acceptance-*.json"))


def test_upstream_accession_year_must_match_same_quarter_filing_date(tmp_path):
    wrong_year_accession = ACCESSION_B.replace("-26-", "-25-")
    tables = _tables()
    tables["SUBMISSION.tsv"] = tables["SUBMISSION.tsv"].replace(
        ACCESSION_B.encode("ascii"), wrong_year_accession.encode("ascii")
    )
    raw_path, parsed_path = _upstream(tmp_path, tables=tables)
    output_root = tmp_path / "acceptance"

    with pytest.raises(
        SecEdgarAcceptanceSnapshotError, match="filing date|accession year"
    ):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert not tuple(output_root.glob("sec-edgar-acceptance-*.json"))


@pytest.mark.parametrize("issuer_cik", ["", "0000000000", "123", "not-a-cik"])
def test_upstream_issuer_cik_must_be_canonical_and_nonzero(tmp_path, issuer_cik):
    issuer_ciks = {accession: "0000123456" for accession in ACCESSIONS}
    issuer_ciks[ACCESSION_B] = issuer_cik
    raw_path, parsed_path = _upstream(
        tmp_path,
        tables=_tables(issuer_ciks=issuer_ciks),
    )
    output_root = tmp_path / "acceptance"
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="issuer CIK|CIK"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert not tuple(output_root.glob("sec-edgar-acceptance-*.json"))


@pytest.mark.parametrize(
    "source_url",
    [
        "http://www.sec.gov/Archives/synthetic.json",
        "https://www.sec.gov/Archives/synthetic.json?revision=1",
        "https://www.sec.gov/Archives/synthetic.json#fragment",
        "https://user@example.test/synthetic.json",
        "https://example.test/Archives/synthetic.json",
        " https://www.sec.gov/Archives/synthetic.json",
        "https://www.sec.gov/Archives/../synthetic.json",
    ],
)
def test_metadata_source_url_must_be_canonical_absolute_https(source_url):
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="URL|url|canonical|HTTPS"):
        _metadata_source(ACCESSION_A, source_url=source_url)


@pytest.mark.parametrize(
    "primary_url",
    [
        "http://www.sec.gov/Archives/synthetic.xml",
        "https://example.test/Archives/synthetic.xml",
        "relative/synthetic.xml",
        "https://www.sec.gov/Archives/synthetic.xml?download=1",
        "https://www.sec.gov/Archives/../synthetic.xml",
        "",
        (
            "https://www.sec.gov/Archives/edgar/data/123456/"
            "000012345626999999/synthetic-primary.xml"
        ),
    ],
)
def test_primary_document_url_must_be_canonical_absolute_https(
    tmp_path, primary_url
):
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="URL|url|canonical|HTTPS"):
        _build_with_source_bytes(
            tmp_path, _metadata_bytes(ACCESSION_A, primary_url=primary_url)
        )


def test_source_url_path_must_bind_to_metadata_accession(tmp_path):
    source = _metadata_source(
        ACCESSION_A,
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/123456/"
            f"{ACCESSION_B.replace('-', '')}/synthetic-metadata.json"
        ),
    )
    raw_path, parsed_path = _upstream(tmp_path)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="URL|url|accession|path"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            tmp_path / "acceptance",
            sources=(source, _metadata_source(ACCESSION_C)),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert not tuple((tmp_path / "acceptance").glob("sec-edgar-acceptance-*.json"))


@pytest.mark.parametrize(
    "source_url",
    (
        (
            "https://www.sec.gov/Archives/edgar/data/999999/"
            f"{ACCESSION_A.replace('-', '')}/synthetic-metadata.json"
        ),
        (
            "https://data.sec.gov/Archives/edgar/data/123456/"
            f"{ACCESSION_A.replace('-', '')}/synthetic-metadata.json"
        ),
    ),
)
def test_source_url_archive_path_must_bind_to_upstream_issuer_cik_and_host(
    tmp_path, source_url
):
    source = _metadata_source(
        ACCESSION_A,
        source_url=source_url,
    )
    raw_path, parsed_path = _upstream(tmp_path)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="URL|url|issuer|lineage"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            tmp_path / "acceptance",
            sources=(source, _metadata_source(ACCESSION_C)),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert not tuple((tmp_path / "acceptance").glob("sec-edgar-acceptance-*.json"))


def test_primary_document_url_must_bind_to_upstream_issuer_cik(tmp_path):
    source = _metadata_source(
        ACCESSION_A,
        primary_url=(
            "https://www.sec.gov/Archives/edgar/data/999999/"
            f"{ACCESSION_A.replace('-', '')}/synthetic-primary.xml"
        ),
    )
    raw_path, parsed_path = _upstream(tmp_path)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="URL|url|issuer|CIK"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            tmp_path / "acceptance",
            sources=(source, _metadata_source(ACCESSION_C)),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert not tuple((tmp_path / "acceptance").glob("sec-edgar-acceptance-*.json"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"profile_id": ""},
        {"exact_fields": ("accession", "form", "filed", "accepted", "accepted")},
        {"accession_number_field": "absent"},
        {"form_type_field": "accession"},
        {"accepted_at_field": "transactionDate"},
        {"valid_from_quarter": True},
        {"valid_through_year": 2025},
    ],
)
def test_metadata_profile_guards_exact_distinct_mappings_and_range(overrides):
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="REFUSED"):
        _metadata_profile(**overrides)


def test_profile_must_cover_verified_upstream_quarter(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="profile|quarter|period"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            tmp_path / "acceptance",
            sources=_sources(),
            metadata_profile=_metadata_profile(
                valid_from_year=2026,
                valid_from_quarter=3,
            ),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )


@pytest.mark.parametrize("git_commit", ["d" * 39, "D" * 40, "g" * 40, True])
def test_parser_git_sha_guard(tmp_path, git_commit):
    raw_path, parsed_path = _upstream(tmp_path)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="Git|commit|SHA"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            tmp_path / "acceptance",
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=git_commit,
        )


@pytest.mark.parametrize("git_commit", ["d" * 39, "D" * 40, "g" * 40, True])
def test_capture_git_sha_guard(git_commit):
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="Git|commit|SHA"):
        _metadata_source(ACCESSION_A, capture_git_commit=git_commit)


def test_source_tuple_order_and_exact_retry_are_deterministic(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    first_sources = _sources()
    _, _, first_path, first_identity = _build(
        tmp_path,
        raw_path=raw_path,
        parsed_path=parsed_path,
        sources=first_sources,
        output_name="first",
    )
    first_bytes = first_path.read_bytes()

    _, _, reversed_path, reversed_identity = _build(
        tmp_path,
        raw_path=raw_path,
        parsed_path=parsed_path,
        sources=tuple(reversed(first_sources)),
        output_name="reversed",
    )
    assert reversed_identity == first_identity
    assert reversed_path.read_bytes() == first_bytes

    _, _, retry_path, retry_identity = _build(
        tmp_path,
        raw_path=raw_path,
        parsed_path=parsed_path,
        sources=first_sources,
        output_name="first",
    )
    assert retry_identity == first_identity
    assert retry_path == first_path
    assert retry_path.read_bytes() == first_bytes


def test_ambiguous_fold_retrieval_time_round_trips_and_retries_canonically(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    ambiguous_retrieval = datetime(
        2026,
        11,
        1,
        1,
        30,
        tzinfo=ZoneInfo("America/New_York"),
        fold=0,
    )
    sources = (
        _metadata_source(ACCESSION_A, retrieved_at=ambiguous_retrieval),
        _metadata_source(ACCESSION_C),
    )

    _, _, bundle_path, identity = _build(
        tmp_path,
        raw_path=raw_path,
        parsed_path=parsed_path,
        sources=sources,
        output_name="ambiguous-fold",
    )
    _, _, retry_path, retry_identity = _build(
        tmp_path,
        raw_path=raw_path,
        parsed_path=parsed_path,
        sources=sources,
        output_name="ambiguous-fold",
    )
    loaded = _load(bundle_path, parsed_path, raw_path)

    assert retry_identity == identity
    assert retry_path == bundle_path
    assert next(
        source.retrieved_at_utc
        for source in loaded.sources
        if source.metadata_bytes == sources[0].metadata_bytes
    ) == "2026-11-01T05:30:00+00:00"


def test_source_hash_and_every_declared_provenance_change_snapshot_identity(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)

    def publish_one(
        output_name: str,
        source_a: SecEdgarMetadataSource,
        *,
        profile: SecEdgarMetadataSchemaProfile | None = None,
        parser_commit: str = ACCEPTANCE_COMMIT,
    ):
        return _build(
            tmp_path,
            raw_path=raw_path,
            parsed_path=parsed_path,
            sources=(source_a, _metadata_source(ACCESSION_C)),
            metadata_profile=profile,
            parser_git_commit=parser_commit,
            output_name=output_name,
        )[3]

    baseline = publish_one("baseline", _metadata_source(ACCESSION_A))
    changed_bytes = publish_one(
        "bytes",
        _metadata_source(
            ACCESSION_A,
            primary_url=(
                "https://www.sec.gov/Archives/edgar/data/123456/"
                "000012345626000001/alternate-primary.xml"
            ),
        ),
    )
    changed_url = publish_one(
        "url",
        _metadata_source(
            ACCESSION_A,
            source_url=(
                "https://www.sec.gov/Archives/edgar/data/123456/"
                "000012345626000001/alternate-metadata.json"
            ),
        ),
    )
    changed_retrieval = publish_one(
        "retrieval",
        _metadata_source(
            ACCESSION_A, retrieved_at=METADATA_RETRIEVED + timedelta(seconds=1)
        ),
    )
    changed_capture_commit = publish_one(
        "capture-commit",
        _metadata_source(ACCESSION_A, capture_git_commit="e" * 40),
    )
    changed_profile = publish_one(
        "profile",
        _metadata_source(ACCESSION_A),
        profile=_metadata_profile(
            profile_id="synthetic-non-official-qc-edgar-metadata-v2"
        ),
    )
    changed_parser_commit = publish_one(
        "parser-commit",
        _metadata_source(ACCESSION_A),
        parser_commit="f" * 40,
    )

    identities = {
        item.snapshot_id
        for item in (
            baseline,
            changed_bytes,
            changed_url,
            changed_retrieval,
            changed_capture_commit,
            changed_profile,
            changed_parser_commit,
        )
    }
    assert len(identities) == 7


def test_build_refuses_mismatched_raw_and_parsed_upstream_snapshots(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path, root_suffix="-one")
    alternate_raw, _ = _upstream(
        tmp_path,
        root_suffix="-two",
        raw_source=_raw_source(retrieved_at=RAW_RETRIEVED + timedelta(seconds=1)),
    )
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="raw|parsed|upstream"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            alternate_raw,
            tmp_path / "acceptance",
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert raw_path.is_dir()
    assert parsed_path.is_dir()


def test_loader_rebinds_bundle_to_exact_raw_and_parsed_upstreams(tmp_path):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path, output_name="bundle")
    alternate_dates = dict(FILING_DATES)
    alternate_dates[ACCESSION_B] = "2026-05-04"
    alternate_raw, alternate_parsed = _upstream(
        tmp_path,
        root_suffix="-alternate",
        tables=_tables(filing_dates=alternate_dates),
    )

    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="raw|parsed|upstream|match"):
        _load(bundle_path, alternate_parsed, alternate_raw)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="raw|parsed|upstream|match"):
        _load(bundle_path, parsed_path, alternate_raw)
    assert _load(bundle_path, parsed_path, raw_path).identity.snapshot_id


def test_bundle_filename_is_part_of_content_addressed_identity(tmp_path):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path)
    wrong_path = bundle_path.with_name(
        "sec-edgar-acceptance-2026q2-0000000000000000.json"
    )
    wrong_path.write_bytes(bundle_path.read_bytes())
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="identity|filename|path"):
        _load(wrong_path, parsed_path, raw_path)


@pytest.mark.parametrize("mutation", ["corrupt", "unknown-top", "record"])
def test_bundle_corruption_and_tampering_refuse(mutation, tmp_path):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path)
    original = bundle_path.read_bytes()
    tampered_path = tmp_path / f"tampered-{mutation}" / bundle_path.name
    tampered_path.parent.mkdir()
    if mutation == "corrupt":
        tampered = original[:-1] + b"!"
    else:
        payload = json.loads(original)
        if mutation == "unknown-top":
            payload["unknown"] = "forged"
        else:
            payload["records"][0]["document_type"] = "3"
        tampered = (canonical_json(payload) + "\n").encode("utf-8")
    tampered_path.write_bytes(tampered)

    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="REFUSED"):
        _load(tampered_path, parsed_path, raw_path)


def test_bundle_duplicate_json_key_and_trailing_nul_refuse(tmp_path):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path)
    duplicate_path = tmp_path / "duplicate-key" / bundle_path.name
    duplicate_path.parent.mkdir()
    raw = bundle_path.read_bytes().rstrip()
    assert raw.startswith(b"{")
    duplicate_path.write_bytes(b'{"identity":{},' + raw[1:] + b"\n")
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="REFUSED"):
        _load(duplicate_path, parsed_path, raw_path)

    # Avoid Windows' reserved ``NUL`` device name for this directory.
    nul_path = tmp_path / "trailing-nul" / bundle_path.name
    nul_path.parent.mkdir()
    nul_path.write_bytes(bundle_path.read_bytes() + b"\x00")
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="REFUSED"):
        _load(nul_path, parsed_path, raw_path)


def test_deep_bundle_json_maps_recursion_to_the_public_refusal(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    parent = tmp_path / "deep-bundle"
    parent.mkdir()
    path = parent / "sec-edgar-acceptance-2026q2-0000000000000000.json"
    path.write_bytes(b"[" * 2_000 + b"0" + b"]" * 2_000)

    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="JSON|REFUSED"):
        _load(path, parsed_path, raw_path)


def test_bundle_nesting_cap_runs_before_json_decoder(monkeypatch):
    def decoder_must_not_run(*_args, **_kwargs):
        raise AssertionError("JSON decoder ran before the bundle nesting cap")

    monkeypatch.setattr(acceptance_module.json, "loads", decoder_must_not_run)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="JSON|REFUSED"):
        acceptance_module._parse_canonical_bundle(b"[" * 9 + b"0" + b"]" * 9)


def _readdress_bundle(payload: dict[str, object], parent: Path) -> Path:
    identity = payload["identity"]
    identity["records_hash"] = hash_payload(payload["records"])
    lineage_payload = {
        key: value
        for key, value in identity.items()
        if key not in {"lineage_hash", "snapshot_id"}
    }
    lineage_hash = hash_payload(lineage_payload)
    identity["lineage_hash"] = lineage_hash
    identity["snapshot_id"] = (
        f"sec-edgar-acceptance-{identity['year']}q{identity['quarter']}-"
        f"{lineage_hash[:16]}"
    )
    path = parent / f"{identity['snapshot_id']}.json"
    parent.mkdir()
    path.write_bytes((canonical_json(payload) + "\n").encode("utf-8"))
    return path


@pytest.mark.parametrize(
    "mutation",
    ["record-order", "source-inventory-order", "source-payload-order"],
)
def test_loader_refuses_rehashed_noncanonical_record_and_source_order(
    tmp_path, mutation
):
    _, _, bundle_path, _ = _build(tmp_path)
    payload = json.loads(bundle_path.read_bytes())

    if mutation == "record-order":
        payload["records"].reverse()
    elif mutation == "source-inventory-order":
        payload["sources"].reverse()
        payload["identity"]["source_inventory"].reverse()
        payload["identity"]["source_inventory_hash"] = hash_payload(
            payload["identity"]["source_inventory"]
        )
    else:
        payload["sources"].reverse()

    tampered_path = _readdress_bundle(payload, tmp_path / mutation)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="REFUSED"):
        acceptance_module._load_self_consistent_bundle(tampered_path)


@pytest.mark.parametrize("forgery", ["submission-link", "filing-date"])
def test_fully_rehashed_record_only_forgery_is_caught_by_upstream_rebuild(
    tmp_path, forgery
):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path)
    payload = json.loads(bundle_path.read_bytes())
    if forgery == "submission-link":
        payload["records"][0]["submission_row_id"], payload["records"][1][
            "submission_row_id"
        ] = (
            payload["records"][1]["submission_row_id"],
            payload["records"][0]["submission_row_id"],
        )
    else:
        payload["records"][1]["filing_date"] = "2026-05-03"
    forged_path = _readdress_bundle(payload, tmp_path / f"forged-{forgery}")

    # Ordinary record/lineage hashes and the content-addressed filename agree.
    # Only reconstruction from the verified upstream can reject this forgery.
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="upstream|semantics|match"):
        _load(forged_path, parsed_path, raw_path)


@pytest.mark.parametrize("encoded", ["@@@", "eA", "eA==="])
def test_bundled_metadata_base64_must_be_strict_and_canonical(
    tmp_path, encoded
):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path)
    payload = json.loads(bundle_path.read_bytes())
    payload["sources"][0]["metadata_bytes_base64"] = encoded
    tampered = tmp_path / "bad-base64" / bundle_path.name
    tampered.parent.mkdir()
    tampered.write_bytes((canonical_json(payload) + "\n").encode("utf-8"))
    with pytest.raises(
        SecEdgarAcceptanceSnapshotError,
        match="base64|source|identity|metadata bytes",
    ):
        _load(tampered, parsed_path, raw_path)


@pytest.mark.parametrize("encoded", ["!A==", "eB=="])
def test_bundled_metadata_base64_checks_run_after_declared_length_preflight(encoded):
    payload = {
        "metadata_bytes_base64": encoded,
        "metadata_sha256": hash_bytes(b"x"),
        "metadata_size_bytes": 1,
        "source_url": "https://data.sec.gov/submissions/0000123456-metadata.json",
        "retrieved_at_utc": "2026-05-05T18:00:00+00:00",
        "capture_git_commit": METADATA_COMMIT,
    }
    assert len(encoded) == 4
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="base64"):
        acceptance_module._source_from_bundle_payload(payload)


def test_output_root_cannot_overlap_raw_or_parsed_snapshot(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    for output_root in (
        raw_path,
        raw_path / "acceptance",
        raw_path.parent / "unused" / ".." / raw_path.name / "deep" / "acceptance",
        parsed_path,
        parsed_path / "acceptance",
        parsed_path.parent
        / "unused"
        / ".."
        / parsed_path.name
        / "deep"
        / "acceptance",
    ):
        with pytest.raises(SecEdgarAcceptanceSnapshotError, match="output|raw|parsed|descendant"):
            build_sec_edgar_acceptance_snapshot(
                parsed_path,
                raw_path,
                output_root,
                sources=_sources(),
                metadata_profile=_metadata_profile(),
                parser_git_commit=ACCEPTANCE_COMMIT,
            )


def test_output_root_symlink_is_refused_when_platform_permits(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    actual_root = tmp_path / "actual-output"
    actual_root.mkdir()
    output_link = tmp_path / "output-link"
    try:
        os.symlink(actual_root, output_link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="output|redirect|reparse|link"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_link,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )


def test_behavioral_reparse_classification_refuses_output_root(tmp_path, monkeypatch):
    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"
    output_root.mkdir()
    actual_identity = (output_root.lstat().st_dev, output_root.lstat().st_ino)
    real_status_is_redirect = acceptance_module._status_is_redirect

    def classify(status):
        return (
            (status.st_dev, status.st_ino) == actual_identity
            or real_status_is_redirect(status)
        )

    monkeypatch.setattr(acceptance_module, "_status_is_redirect", classify)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="output|redirect|reparse"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )


def test_concurrent_exact_writers_publish_one_identical_bundle(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"

    def publish():
        return build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        identities = tuple(pool.map(lambda _: publish(), range(16)))
    assert len({item.snapshot_id for item in identities}) == 1
    bundles = tuple(output_root.glob("sec-edgar-acceptance-*.json"))
    assert len(bundles) == 1
    assert _load(bundles[0], parsed_path, raw_path).identity == identities[0]


def test_one_output_root_retains_multiple_content_addressed_versions(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"
    first = build_sec_edgar_acceptance_snapshot(
        parsed_path,
        raw_path,
        output_root,
        sources=_sources(),
        metadata_profile=_metadata_profile(),
        parser_git_commit=ACCEPTANCE_COMMIT,
    )
    second_sources = (
        _metadata_source(
            ACCESSION_A, retrieved_at=METADATA_RETRIEVED + timedelta(seconds=1)
        ),
        _metadata_source(ACCESSION_C),
    )
    unrelated = output_root / ".sec-edgar-acceptance-2026q2-ffffffffffffffff.json.other.tmp"
    unrelated.write_bytes(b"unrelated snapshot residue")
    second = build_sec_edgar_acceptance_snapshot(
        parsed_path,
        raw_path,
        output_root,
        sources=second_sources,
        metadata_profile=_metadata_profile(),
        parser_git_commit=ACCEPTANCE_COMMIT,
    )

    assert first.snapshot_id != second.snapshot_id
    first_path = output_root / f"{first.snapshot_id}.json"
    second_path = output_root / f"{second.snapshot_id}.json"
    assert _load(first_path, parsed_path, raw_path).identity == first
    assert _load(second_path, parsed_path, raw_path).identity == second
    assert unrelated.read_bytes() == b"unrelated snapshot residue"


def _expected_bundle(tmp_path: Path):
    raw_path, parsed_path = _upstream(tmp_path, root_suffix="-expected")
    _, _, bundle_path, identity = _build(
        tmp_path,
        raw_path=raw_path,
        parsed_path=parsed_path,
        output_name="expected",
    )
    return raw_path, parsed_path, identity, bundle_path.read_bytes()


def _publisher_temp(output_root: Path, filename: str, tag: str) -> Path:
    return output_root / f".{filename}.{tag}.tmp"


@pytest.mark.parametrize("prefix_kind", ["empty", "one-byte", "all-but-last", "exact"])
def test_uncommitted_partial_prefix_temporary_is_recovered(tmp_path, prefix_kind):
    raw_path, parsed_path, identity, expected = _expected_bundle(tmp_path)
    output_root = tmp_path / "recover-prefix"
    output_root.mkdir()
    filename = f"{identity.snapshot_id}.json"
    residue = _publisher_temp(output_root, filename, "crash")
    prefix_size = {
        "empty": 0,
        "one-byte": 1,
        "all-but-last": len(expected) - 1,
        "exact": len(expected),
    }[prefix_kind]
    residue.write_bytes(expected[:prefix_size])

    rebuilt = build_sec_edgar_acceptance_snapshot(
        parsed_path,
        raw_path,
        output_root,
        sources=_sources(),
        metadata_profile=_metadata_profile(),
        parser_git_commit=ACCEPTANCE_COMMIT,
    )
    final_path = output_root / filename
    assert rebuilt == identity
    assert final_path.read_bytes() == expected
    assert not residue.exists()


def test_committed_bundle_refuses_and_preserves_partial_temporary(tmp_path):
    raw_path, parsed_path, bundle_path, identity = _build(tmp_path)
    original = bundle_path.read_bytes()
    residue = _publisher_temp(bundle_path.parent, bundle_path.name, "crash")
    residue.write_bytes(original[:17])

    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="temporary|residue|unverified"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            bundle_path.parent,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert bundle_path.read_bytes() == original
    assert residue.read_bytes() == original[:17]
    assert _load(bundle_path, parsed_path, raw_path).identity == identity


def test_committed_bundle_cleans_only_byte_exact_publisher_temporary(tmp_path):
    raw_path, parsed_path, bundle_path, identity = _build(tmp_path)
    original = bundle_path.read_bytes()
    residue = _publisher_temp(bundle_path.parent, bundle_path.name, "exact")
    residue.write_bytes(original)
    rebuilt = build_sec_edgar_acceptance_snapshot(
        parsed_path,
        raw_path,
        bundle_path.parent,
        sources=_sources(),
        metadata_profile=_metadata_profile(),
        parser_git_commit=ACCEPTANCE_COMMIT,
    )
    assert rebuilt == identity
    assert not residue.exists()
    assert bundle_path.read_bytes() == original


def test_nonprefix_and_mixed_temporary_residue_refuses_without_deleting_anything(
    tmp_path,
):
    raw_path, parsed_path, identity, expected = _expected_bundle(tmp_path)
    output_root = tmp_path / "mixed-residue"
    output_root.mkdir()
    filename = f"{identity.snapshot_id}.json"
    good_prefix = _publisher_temp(output_root, filename, "prefix")
    bad_prefix = _publisher_temp(output_root, filename, "foreign")
    good_prefix.write_bytes(expected[:13])
    bad_prefix.write_bytes(b"not a prefix")

    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="residue|unverified|temporary"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert good_prefix.read_bytes() == expected[:13]
    assert bad_prefix.read_bytes() == b"not a prefix"
    assert not (output_root / filename).exists()


def test_publisher_temporary_count_cap_refuses_before_deleting_any_residue(
    tmp_path, monkeypatch
):
    raw_path, parsed_path, identity, expected = _expected_bundle(tmp_path)
    output_root = tmp_path / "too-many-temporaries"
    output_root.mkdir()
    filename = f"{identity.snapshot_id}.json"
    first = _publisher_temp(output_root, filename, "first")
    second = _publisher_temp(output_root, filename, "second")
    first.write_bytes(expected[:11])
    second.write_bytes(expected[:13])
    monkeypatch.setattr(acceptance_module, "MAX_PUBLISHER_TEMPORARIES", 1)

    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="temporary|count|limit"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert first.read_bytes() == expected[:11]
    assert second.read_bytes() == expected[:13]
    assert not (output_root / filename).exists()


def _assert_no_acceptance_bundle(output_root: Path) -> None:
    assert not tuple(output_root.glob("sec-edgar-acceptance-*.json"))


def test_source_count_cap_refuses_before_publication(tmp_path, monkeypatch):
    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"
    monkeypatch.setattr(acceptance_module, "MAX_METADATA_SOURCES", 1)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="source|count|limit"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    _assert_no_acceptance_bundle(output_root)


def test_per_source_byte_cap_refuses_before_publication(tmp_path, monkeypatch):
    source_bytes = _metadata_bytes(ACCESSION_A)
    monkeypatch.setattr(
        acceptance_module, "MAX_METADATA_SOURCE_BYTES", len(source_bytes) - 1
    )
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="source|byte|limit"):
        _metadata_source(ACCESSION_A)
    _assert_no_acceptance_bundle(tmp_path / "acceptance")


def test_total_source_byte_cap_refuses_before_publication(tmp_path, monkeypatch):
    raw_path, parsed_path = _upstream(tmp_path)
    sources = _sources()
    total = sum(len(source.metadata_bytes) for source in sources)
    monkeypatch.setattr(
        acceptance_module, "MAX_TOTAL_METADATA_SOURCE_BYTES", total - 1
    )
    output_root = tmp_path / "acceptance"
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="total|source|byte|limit"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=sources,
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    _assert_no_acceptance_bundle(output_root)


def test_acceptance_record_cap_refuses_before_publication(tmp_path, monkeypatch):
    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"
    monkeypatch.setattr(acceptance_module, "MAX_ACCEPTANCE_RECORDS", 3)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="record|accession|limit"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    _assert_no_acceptance_bundle(output_root)


def test_metadata_profile_field_count_cap(monkeypatch):
    monkeypatch.setattr(acceptance_module, "MAX_METADATA_FIELDS", 4)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="field|limit"):
        _metadata_profile()


def test_metadata_field_name_character_cap(monkeypatch):
    monkeypatch.setattr(acceptance_module, "MAX_METADATA_FIELD_NAME_CHARACTERS", 7)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="field|name|limit"):
        _metadata_profile()


def test_metadata_field_value_character_cap_refuses_before_publication(
    tmp_path, monkeypatch
):
    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"
    monkeypatch.setattr(acceptance_module, "MAX_METADATA_FIELD_CHARACTERS", 10)
    with pytest.raises(
        SecEdgarAcceptanceSnapshotError,
        match="field|character|limit|bounded strings",
    ):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    _assert_no_acceptance_bundle(output_root)


def test_url_character_cap_refuses_source(monkeypatch):
    monkeypatch.setattr(acceptance_module, "MAX_URL_CHARACTERS", 20)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="URL|url|limit"):
        _metadata_source(ACCESSION_A)


def test_final_bundle_byte_cap_refuses_before_publication(tmp_path, monkeypatch):
    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"
    monkeypatch.setattr(acceptance_module, "MAX_ACCEPTANCE_BUNDLE_BYTES", 64)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="bundle|byte|limit"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    _assert_no_acceptance_bundle(output_root)


def test_loader_enforces_final_bundle_and_decoded_source_caps(tmp_path, monkeypatch):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path)
    bundle_size = bundle_path.stat().st_size
    monkeypatch.setattr(
        acceptance_module, "MAX_ACCEPTANCE_BUNDLE_BYTES", bundle_size - 1
    )
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="bundle|byte|limit"):
        _load(bundle_path, parsed_path, raw_path)

    monkeypatch.setattr(
        acceptance_module, "MAX_ACCEPTANCE_BUNDLE_BYTES", bundle_size
    )
    monkeypatch.setattr(
        acceptance_module,
        "MAX_METADATA_SOURCE_BYTES",
        len(_metadata_bytes(ACCESSION_A)) - 1,
    )

    def decode_before_cap_check(*_args, **_kwargs):
        raise AssertionError("base64 decoder ran before the declared-size cap")

    monkeypatch.setattr(acceptance_module.base64, "b64decode", decode_before_cap_check)
    source_payload = json.loads(bundle_path.read_bytes())["sources"][0]
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="source|byte|bounded"):
        acceptance_module._source_from_bundle_payload(source_payload)


def test_loader_enforces_total_source_cap_before_any_base64_decode(
    tmp_path, monkeypatch
):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path)
    total = sum(len(source.metadata_bytes) for source in _sources())
    monkeypatch.setattr(
        acceptance_module, "MAX_TOTAL_METADATA_SOURCE_BYTES", total - 1
    )

    def decode_before_total_cap_check(*_args, **_kwargs):
        raise AssertionError("base64 decoder ran before the aggregate-size cap")

    monkeypatch.setattr(
        acceptance_module.base64, "b64decode", decode_before_total_cap_check
    )
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="total|source|byte"):
        _load(bundle_path, parsed_path, raw_path)


def test_conflicting_final_bundle_is_immutable_and_preserved(tmp_path):
    raw_path, parsed_path, identity, _ = _expected_bundle(tmp_path)
    output_root = tmp_path / "conflict"
    output_root.mkdir()
    final_path = output_root / f"{identity.snapshot_id}.json"
    final_path.write_bytes(b"foreign immutable content")

    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="conflict|bundle|publication"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert final_path.read_bytes() == b"foreign immutable content"


@pytest.mark.parametrize("failure_phase", ["before", "after"])
def test_publication_failure_recovers_or_leaves_retryable_state(
    tmp_path, monkeypatch, failure_phase
):
    raw_path, parsed_path = _upstream(tmp_path)
    output_root = tmp_path / "acceptance"
    real_publish = acceptance_module.publish_immutable_bytes

    def fail_publish(path, data):
        if failure_phase == "before":
            raise OSError("synthetic disk failure")
        result = real_publish(path, data)
        raise OSError("synthetic post-link failure")

    monkeypatch.setattr(acceptance_module, "publish_immutable_bytes", fail_publish)
    if failure_phase == "after":
        completed = build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
        assert _load(
            output_root / f"{completed.snapshot_id}.json", parsed_path, raw_path
        ).identity == completed
        return

    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="publication|publish"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    monkeypatch.setattr(acceptance_module, "publish_immutable_bytes", real_publish)
    completed = build_sec_edgar_acceptance_snapshot(
        parsed_path,
        raw_path,
        output_root,
        sources=_sources(),
        metadata_profile=_metadata_profile(),
        parser_git_commit=ACCEPTANCE_COMMIT,
    )
    assert _load(
        output_root / f"{completed.snapshot_id}.json", parsed_path, raw_path
    ).identity == completed


def test_publication_lock_failure_maps_to_acceptance_error(tmp_path, monkeypatch):
    raw_path, parsed_path = _upstream(tmp_path)

    @contextmanager
    def fail_lock(_path):
        raise OSError("synthetic lock denial")
        yield

    monkeypatch.setattr(acceptance_module, "exclusive_file_lock", fail_lock)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="lock"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            tmp_path / "acceptance",
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )


def test_existing_hardlinked_lock_slot_refuses_without_mutating_its_peer(tmp_path):
    raw_path, parsed_path = _upstream(tmp_path)
    identity = _build(
        tmp_path,
        raw_path=raw_path,
        parsed_path=parsed_path,
        output_name="identity",
    )[3]
    output_root = tmp_path / "hardlinked-lock"
    output_root.mkdir()
    victim = tmp_path / "victim.bin"
    victim.write_bytes(b"")
    lock_path = output_root / f".{identity.snapshot_id}.publication.lock"
    try:
        os.link(victim, lock_path)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"hard-link creation is unavailable: {exc}")

    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="lock|single-link"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )
    assert victim.read_bytes() == b""
    assert not tuple(output_root.glob("sec-edgar-acceptance-*.json"))


def test_hardlinked_final_bundle_refuses_load_and_exact_retry(tmp_path):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path)
    external_peer = tmp_path / "external-bundle-peer.json"
    try:
        os.link(bundle_path, external_peer)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"hard-link creation is unavailable: {exc}")
    expected = bundle_path.read_bytes()

    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="single-link|immutable"):
        _load(bundle_path, parsed_path, raw_path)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="single-link|immutable"):
        _build(
            tmp_path,
            raw_path=raw_path,
            parsed_path=parsed_path,
            output_name="acceptance",
        )

    assert bundle_path.read_bytes() == expected
    assert external_peer.read_bytes() == expected


def test_loader_refuses_hardlink_added_during_upstream_rebuild(tmp_path, monkeypatch):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path)
    external_peer = tmp_path / "mid-load-external-peer.json"
    expected = bundle_path.read_bytes()
    real_assemble = acceptance_module._assemble_acceptance_snapshot

    def assemble_then_link(*args, **kwargs):
        result = real_assemble(*args, **kwargs)
        try:
            os.link(bundle_path, external_peer)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"hard-link creation is unavailable: {exc}")
        return result

    monkeypatch.setattr(
        acceptance_module, "_assemble_acceptance_snapshot", assemble_then_link
    )
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="single-link|immutable"):
        _load(bundle_path, parsed_path, raw_path)

    assert bundle_path.read_bytes() == expected
    assert external_peer.read_bytes() == expected


def test_loader_refuses_symlink_bundle_when_platform_permits(tmp_path):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path)
    link = tmp_path / "link" / bundle_path.name
    link.parent.mkdir()
    try:
        os.symlink(bundle_path, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="regular|redirect|reparse|link"):
        _load(link, parsed_path, raw_path)


def test_windows_reparse_flag_is_recognized_without_link_privileges(monkeypatch):
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024) or 1024
    monkeypatch.setattr(
        acceptance_module.stat,
        "FILE_ATTRIBUTE_REPARSE_POINT",
        reparse_flag,
        raising=False,
    )
    normal = SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0)
    redirected = SimpleNamespace(
        st_mode=stat.S_IFREG,
        st_file_attributes=reparse_flag,
    )
    symlink = SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
    assert not acceptance_module._status_is_redirect(normal)
    assert acceptance_module._status_is_redirect(redirected)
    assert acceptance_module._status_is_redirect(symlink)


def test_behavioral_reparse_classification_refuses_bundle_and_lock(
    tmp_path, monkeypatch
):
    raw_path, parsed_path, bundle_path, _ = _build(tmp_path, output_name="loaded")
    real_status_is_redirect = acceptance_module._status_is_redirect

    def file_identity(status):
        return status.st_dev, status.st_ino

    redirected: set[tuple[int, int]] = {file_identity(bundle_path.lstat())}

    def classify(status):
        return file_identity(status) in redirected or real_status_is_redirect(status)

    monkeypatch.setattr(acceptance_module, "_status_is_redirect", classify)
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="regular|redirect|reparse"):
        _load(bundle_path, parsed_path, raw_path)

    redirected.clear()
    output_root = tmp_path / "lock"
    output_root.mkdir()
    # Obtain the deterministic target identity without publishing to this root.
    identity = _build(
        tmp_path,
        raw_path=raw_path,
        parsed_path=parsed_path,
        output_name="identity",
    )[3]
    lock_path = output_root / f".{identity.snapshot_id}.publication.lock"
    lock_path.write_bytes(b"")
    redirected.add(file_identity(lock_path.lstat()))
    with pytest.raises(SecEdgarAcceptanceSnapshotError, match="lock"):
        build_sec_edgar_acceptance_snapshot(
            parsed_path,
            raw_path,
            output_root,
            sources=_sources(),
            metadata_profile=_metadata_profile(),
            parser_git_commit=ACCEPTANCE_COMMIT,
        )


def test_acceptance_module_has_no_network_outcome_execution_or_ui_imports():
    module_path = Path(acceptance_module.__file__)
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])

    forbidden = {
        "assistant",
        "backtest",
        "execution",
        "httpx",
        "outcomes",
        "quantconnect",
        "requests",
        "risk",
        "signals",
        "socket",
        "strategies",
        "streamlit",
        "yfinance",
    }
    assert imported.isdisjoint(forbidden), imported & forbidden
    assert all(
        not isinstance(node, ast.ImportFrom)
        or not node.module
        or not node.module.startswith("urllib")
        or node.module == "urllib.parse"
        for node in ast.walk(tree)
    )
