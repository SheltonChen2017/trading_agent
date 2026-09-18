"""IB-1F persisted offline integration tests for the IB-1A-to-IB-1E chain.

Every byte and row in this module is synthetic.  The tests exercise the real
immutable publishers and loaders without contacting SEC EDGAR, reading market
outcomes, or granting amendment, completeness, or canonical-filter authority.
"""
from __future__ import annotations

import csv
import io
import warnings
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import (
    ALLOWED_SEC_TABLES,
    ClassificationOutcome,
    Form4MultiPeriodEvidenceError,
    SecBulkSource,
    SecEdgarAcceptancePeriodInput,
    SecEdgarMetadataSchemaProfile,
    SecEdgarMetadataSource,
    SecForm4AmendmentEvidenceProfile,
    SecForm4XmlSource,
    SecTsvSchemaProfile,
    SecTsvSchemaVariant,
    assemble_sec_form4_multi_period_evidence,
    build_sec_bulk_parsed_snapshot,
    build_sec_edgar_acceptance_snapshot,
    write_sec_bulk_snapshot,
)
from research.insider_buying import (
    form4_multi_period_amendment_evidence as evidence_module,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "insider_buying"
ORIGINAL = "0000123456-26-000001"
AMENDMENT = "0000123456-27-000002"
RAW_COMMIT = "a" * 40
PARSED_COMMIT = "b" * 40
METADATA_COMMIT = "c" * 40
ACCEPTANCE_COMMIT = "d" * 40
EVIDENCE_COMMIT = "e" * 40
EXACT_FIELDS = (
    "accession",
    "form",
    "filed",
    "accepted",
    "primary_url",
    "amends_accession",
    "primary_document_sha256",
)
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


@dataclass(frozen=True)
class _PeriodSpec:
    year: int
    quarter: int
    accession: str
    document_type: str
    filing_date: date
    accepted_at: datetime
    fixture_name: str
    amends_accession: str | None


@dataclass(frozen=True)
class _PersistedPeriod:
    spec: _PeriodSpec
    raw_path: Path
    parsed_path: Path
    acceptance_path: Path
    xml_source: SecForm4XmlSource


def _specs() -> tuple[_PeriodSpec, _PeriodSpec]:
    return (
        _PeriodSpec(
            year=2026,
            quarter=4,
            accession=ORIGINAL,
            document_type="4",
            filing_date=date(2026, 12, 29),
            accepted_at=datetime(2026, 12, 29, 18, 0, tzinfo=timezone.utc),
            fixture_name="form4_original.xml",
            amends_accession=None,
        ),
        _PeriodSpec(
            year=2027,
            quarter=1,
            accession=AMENDMENT,
            document_type="4/A",
            filing_date=date(2027, 1, 4),
            accepted_at=datetime(2027, 1, 4, 18, 0, tzinfo=timezone.utc),
            fixture_name="form4_amendment.xml",
            amends_accession=ORIGINAL,
        ),
    )


def _tsv(headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _tables(spec: _PeriodSpec) -> dict[str, bytes]:
    filing_date = spec.filing_date.isoformat()
    return {
        "SUBMISSION.tsv": _tsv(
            SUBMISSION_HEADERS,
            (
                (
                    spec.accession,
                    filing_date,
                    filing_date,
                    spec.document_type,
                    "0000123456",
                    "Synthetic Fixture Issuer",
                    "SYN",
                ),
            ),
        ),
        "REPORTINGOWNER.tsv": _tsv(
            OWNER_HEADERS,
            (
                (
                    spec.accession,
                    "0000000042",
                    "Synthetic Owner",
                    "1",
                    "0",
                ),
            ),
        ),
        "NONDERIV_TRANS.tsv": _tsv(
            TRANS_HEADERS,
            (
                (
                    spec.accession,
                    "0000007",
                    filing_date,
                    "5000",
                    "12.50",
                ),
            ),
        ),
    }


def _archive(spec: _PeriodSpec) -> bytes:
    tables = _tables(spec)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for table_name in ALLOWED_SEC_TABLES:
            if table_name not in tables:
                continue
            info = zipfile.ZipInfo(
                table_name,
                date_time=(spec.year, 1, 5, 18, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Duplicate name")
                archive.writestr(info, tables[table_name])
    return stream.getvalue()


def _parsed_profile() -> SecTsvSchemaProfile:
    headers = {
        "SUBMISSION.tsv": SUBMISSION_HEADERS,
        "REPORTINGOWNER.tsv": OWNER_HEADERS,
        "NONDERIV_TRANS.tsv": TRANS_HEADERS,
    }
    variants = tuple(
        SecTsvSchemaVariant(
            schema_id=f"synthetic-{name.removesuffix('.tsv').lower()}-ib1f-v1",
            table_name=name,
            headers=headers[name],
            source_row_key_headers=(
                ("TRANS_SK",) if name == "NONDERIV_TRANS.tsv" else ()
            ),
            valid_from_year=2026,
            valid_from_quarter=4,
            valid_through_year=2027,
            valid_through_quarter=1,
        )
        for name in ALLOWED_SEC_TABLES
        if name in headers
    )
    return SecTsvSchemaProfile(
        profile_id="synthetic-non-official-ib1f-tsv-v1",
        variants=variants,
    )


def _metadata_profile() -> SecEdgarMetadataSchemaProfile:
    return SecEdgarMetadataSchemaProfile(
        profile_id="synthetic-non-official-ib1f-metadata-v1",
        exact_fields=EXACT_FIELDS,
        accession_number_field="accession",
        form_type_field="form",
        filing_date_field="filed",
        accepted_at_field="accepted",
        primary_document_url_field="primary_url",
        valid_from_year=2026,
        valid_from_quarter=4,
        valid_through_year=2027,
        valid_through_quarter=1,
    )


def _primary_url(spec: _PeriodSpec) -> str:
    return (
        "https://www.sec.gov/Archives/edgar/data/123456/"
        f"{spec.accession.replace('-', '')}/synthetic-primary.xml"
    )


def _metadata_source(
    spec: _PeriodSpec, xml_bytes: bytes
) -> SecEdgarMetadataSource:
    payload = {
        "accession": spec.accession,
        "form": spec.document_type,
        "filed": spec.filing_date.isoformat(),
        "accepted": spec.accepted_at.isoformat(timespec="seconds"),
        "primary_url": _primary_url(spec),
        "amends_accession": spec.amends_accession or "",
        "primary_document_sha256": hash_bytes(xml_bytes),
    }
    metadata_bytes = (canonical_json(payload) + "\n").encode("utf-8")
    return SecEdgarMetadataSource(
        metadata_bytes=metadata_bytes,
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/123456/"
            f"{spec.accession.replace('-', '')}/synthetic-metadata.json"
        ),
        retrieved_at=datetime(2027, 1, 5, 18, 0, tzinfo=timezone.utc),
        capture_git_commit=METADATA_COMMIT,
    )


def _persist_period(
    root: Path,
    spec: _PeriodSpec,
    *,
    parsed_profile: SecTsvSchemaProfile,
    metadata_profile: SecEdgarMetadataSchemaProfile,
) -> _PersistedPeriod:
    period_root = root / f"{spec.year:04d}q{spec.quarter}"
    raw_root = period_root / "raw"
    source = SecBulkSource(
        year=spec.year,
        quarter=spec.quarter,
        source_url=(
            "https://www.sec.gov/files/dera/data/insider-transactions-data-sets/"
            f"{spec.year:04d}q{spec.quarter}_form345.zip"
        ),
        git_commit=RAW_COMMIT,
        retrieved_at=datetime(2027, 1, 5, 18, 0, tzinfo=timezone.utc),
    )
    raw_identity = write_sec_bulk_snapshot(_archive(spec), source, raw_root)
    raw_path = raw_root / raw_identity.snapshot_id

    parsed_root = period_root / "parsed"
    parsed_identity = build_sec_bulk_parsed_snapshot(
        raw_path,
        parsed_root,
        schema_profile=parsed_profile,
        parser_git_commit=PARSED_COMMIT,
    )
    parsed_path = parsed_root / parsed_identity.snapshot_id

    xml_bytes = (FIXTURES / spec.fixture_name).read_bytes()
    acceptance_root = period_root / "acceptance"
    acceptance_identity = build_sec_edgar_acceptance_snapshot(
        parsed_path,
        raw_path,
        acceptance_root,
        sources=(_metadata_source(spec, xml_bytes),),
        metadata_profile=metadata_profile,
        parser_git_commit=ACCEPTANCE_COMMIT,
    )
    acceptance_path = (
        acceptance_root / f"{acceptance_identity.snapshot_id}.json"
    )
    assert acceptance_path.is_file()

    xml_source = SecForm4XmlSource(
        accession_number=spec.accession,
        xml_bytes=xml_bytes,
        primary_document_url=_primary_url(spec),
        retrieved_at=datetime(2027, 1, 5, 18, 0, tzinfo=timezone.utc),
        capture_git_commit=EVIDENCE_COMMIT,
        amends_accession=spec.amends_accession,
    )
    return _PersistedPeriod(
        spec=spec,
        raw_path=raw_path,
        parsed_path=parsed_path,
        acceptance_path=acceptance_path,
        xml_source=xml_source,
    )


def _persisted_pair(tmp_path: Path) -> tuple[
    tuple[_PersistedPeriod, _PersistedPeriod],
    SecForm4AmendmentEvidenceProfile,
]:
    parsed_profile = _parsed_profile()
    metadata_profile = _metadata_profile()
    periods = tuple(
        _persist_period(
            tmp_path,
            spec,
            parsed_profile=parsed_profile,
            metadata_profile=metadata_profile,
        )
        for spec in _specs()
    )
    evidence_profile = SecForm4AmendmentEvidenceProfile(
        profile_id="synthetic-non-official-ib1f-link-v1",
        exact_fields=EXACT_FIELDS,
        amends_accession_field="amends_accession",
        primary_document_sha256_field="primary_document_sha256",
        upstream_metadata_profile_hash=hash_payload(
            metadata_profile.to_payload()
        ),
        valid_from_year=2026,
        valid_from_quarter=4,
        valid_through_year=2027,
        valid_through_quarter=1,
        official_sec_profile_verified=False,
    )
    return periods, evidence_profile


def _period_input(period: _PersistedPeriod) -> SecEdgarAcceptancePeriodInput:
    return SecEdgarAcceptancePeriodInput(
        acceptance_snapshot_path=period.acceptance_path,
        parsed_snapshot_directory=period.parsed_path,
        raw_snapshot_directory=period.raw_path,
    )


def test_persisted_two_period_pipeline_reaches_ib1e_without_loader_substitution(
    tmp_path,
):
    periods, profile = _persisted_pair(tmp_path)
    period_inputs = tuple(_period_input(period) for period in periods)
    sources = tuple(period.xml_source for period in periods)

    result = assemble_sec_form4_multi_period_evidence(
        period_inputs,
        sources=sources,
        evidence_profile=profile,
        parser_git_commit=EVIDENCE_COMMIT,
    )
    reversed_result = assemble_sec_form4_multi_period_evidence(
        tuple(reversed(period_inputs)),
        sources=tuple(reversed(sources)),
        evidence_profile=profile,
        parser_git_commit=EVIDENCE_COMMIT,
    )

    assert reversed_result == result
    assert result.identity.period_inventory[0].year == 2026
    assert result.identity.period_inventory[0].quarter == 4
    assert result.identity.period_inventory[1].year == 2027
    assert result.identity.period_inventory[1].quarter == 1
    assert tuple(
        filing.envelope.accession_number
        for filing in result.as_filed_corpus.filings
    ) == (ORIGINAL, AMENDMENT)
    original = result.as_filed_corpus.filing(ORIGINAL)
    amendment = result.as_filed_corpus.filing(AMENDMENT)
    assert len(original.transactions) == 1
    assert len(amendment.transactions) == 1
    assert original.transactions[0].shares == Decimal("5000")
    assert original.transactions[0].outcomes == (
        ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION,
    )
    assert amendment.transactions[0].shares == Decimal("6000")
    assert amendment.transactions[0].outcomes == (
        ClassificationOutcome.EXCLUDE_AMENDED_FILING,
    )
    assert result.identity.transaction_count == 2
    assert result.lineages[0].original_accession == ORIGINAL
    assert tuple(
        version.accession_number for version in result.lineages[0].versions
    ) == (ORIGINAL, AMENDMENT)
    assert result.declared_period_set_contiguous is True
    assert result.official_amendment_link_verified is False
    assert result.complete_amendment_coverage_verified is False
    assert result.canonical_filter_authorized is False


@pytest.mark.parametrize(
    ("parsed_period_index", "raw_period_index"),
    ((1, 1), (0, 1), (1, 0)),
)
def test_each_persisted_period_path_is_bound_before_xml_parsing(
    tmp_path,
    monkeypatch,
    parsed_period_index,
    raw_period_index,
):
    periods, profile = _persisted_pair(tmp_path)
    original, amendment = periods
    cross_wired = SecEdgarAcceptancePeriodInput(
        acceptance_snapshot_path=original.acceptance_path,
        parsed_snapshot_directory=periods[parsed_period_index].parsed_path,
        raw_snapshot_directory=periods[raw_period_index].raw_path,
    )

    def forbidden_xml_parser(*_args, **_kwargs):
        pytest.fail("XML parsing ran before the persisted period paths agreed")

    monkeypatch.setattr(evidence_module, "parse_form4_xml", forbidden_xml_parser)
    with pytest.raises(
        Form4MultiPeriodEvidenceError,
        match="period is not a verified IB-1C boundary",
    ):
        assemble_sec_form4_multi_period_evidence(
            (cross_wired, _period_input(amendment)),
            sources=tuple(period.xml_source for period in periods),
            evidence_profile=profile,
            parser_git_commit=EVIDENCE_COMMIT,
        )
