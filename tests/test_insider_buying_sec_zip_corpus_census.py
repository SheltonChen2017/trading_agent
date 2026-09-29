"""Synthetic, zero-network checks for the retained 82-ZIP census boundary."""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from research.insider_buying.sec_zip_corpus_census import (
    RETAINED_ZIP_MANIFEST_SHA256,
    SecZipCorpusCensusError,
    _census_zip_corpus,
    census_retained_sec_zip_corpus,
)
from research.insider_buying import sec_zip_corpus_census as census_module


_PERIODS = tuple(
    f"{year}Q{quarter}"
    for year in range(2006, 2027)
    for quarter in range(1, 5)
    if (year, quarter) <= (2026, 2)
)
_HEADER = (
    "ACCESSION_NUMBER\tFILING_DATE\tPERIOD_OF_REPORT\tDOCUMENT_TYPE\t"
    "ISSUERCIK\tISSUERNAME\tISSUERTRADINGSYMBOL\n"
)
_MANIFEST_NAME = "insider_quarterly_zip_manifest_2006q1_2026q2.csv"
_BASIS = "local filesystem last-write time; not SEC-attested"
_CAPTURE_COMMIT = "a4192546b168470ff1e9c421d8bd53531a1b3c05"
_INDEX_URL = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"


def _archive(
    rows: tuple[tuple[str, str], ...] | None = None,
    *, submission_text: str | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    if rows is None:
        rows = (
            ("0000000001-06-000001", "3"),
            ("0000000001-06-000002", "3/A"),
            ("0000000001-06-000003", "4"),
            ("0000000001-06-000004", "4/A"),
            ("0000000001-06-000005", "5"),
            ("0000000001-06-000006", "5/A"),
        )
    submission = submission_text if submission_text is not None else (
        _HEADER + "".join(
            f"{accession}\t01-JAN-2006\t01-JAN-2006\t{form}\t1\tIssuer\tABC\n"
            for accession, form in rows
        )
    )
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w", compression=compression) as archive:
        archive.writestr("SUBMISSION.tsv", submission)
        archive.writestr("REPORTINGOWNER.tsv", "ACCESSION_NUMBER\tRPTOWNERCIK\n")
        archive.writestr("NONDERIV_TRANS.tsv", "ACCESSION_NUMBER\tNONDERIV_TRANS_SK\n")
    return sink.getvalue()


def _source_url(period: str) -> str:
    route = "datastandardsinnovation" if period == "2026Q2" else "structureddata"
    return (
        f"https://www.sec.gov/files/{route}/data/insider-transactions-data-sets/"
        f"{period.lower()}_form345.zip"
    )


def _fixture(
    root: Path, *, target_rows: tuple[tuple[str, str], ...] | None = None,
    archive_bytes: bytes | None = None,
) -> str:
    archive_bytes = archive_bytes if archive_bytes is not None else _archive(target_rows)
    rows = []
    for period in _PERIODS:
        filename = f"{period.lower()}_form345.zip"
        (root / filename).write_bytes(archive_bytes)
        rows.append((
            period, filename, _source_url(period), str(len(archive_bytes)),
            hashlib.sha256(archive_bytes).hexdigest(),
            "2026-09-24T22:52:19.7647157Z", _BASIS, _CAPTURE_COMMIT, _INDEX_URL,
        ))
    text = io.StringIO(newline="")
    writer = csv.writer(text, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow((
        "Period", "FileName", "SourceUrl", "SizeBytes", "SHA256",
        "LocalLastWriteUtc", "TimestampBasis", "CaptureCommit", "SourceIndexUrl",
    ))
    writer.writerows(rows)
    raw = text.getvalue().encode("utf-8")
    (root / _MANIFEST_NAME).write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _run(root: Path, digest: str):
    return _census_zip_corpus(
        root, expected_manifest_sha256=digest, scope="synthetic_test_census"
    )


def test_exact_82_zip_census_is_source_bound_but_noncanonical(tmp_path: Path) -> None:
    digest = _fixture(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())
    result = _run(tmp_path, digest)
    payload = result.to_payload()

    assert len(result.quarters) == 82
    assert result.source_manifest_sha256 == digest
    assert payload["scope"] == "synthetic_test_census"
    assert payload["version"] == 1
    assert result.submission_accessions == 82 * 6
    assert result.form4_accessions == 82
    assert result.form4a_accessions == 82
    assert result.target_accessions == 82 * 2
    assert result.multi_owner_unknown_quarters == 82
    assert result.planned_distinct_artifacts_without_cache == 82 + 82 * 2
    assert result.acceptance_metadata_records_required_without_cache == 82 * 2
    assert result.ideal_minimum_dispatch_span_ms == (82 + 82 * 2 - 1) * 500
    assert result.quarters[0].submission_header_line_sha256 == hashlib.sha256(
        _HEADER.encode("utf-8")
    ).hexdigest()
    assert result.quarters[-1].period == "2026Q2"
    assert payload["authority"] == {
        "zip_bytes_verified_against_source_manifest": True,
        "sec_origin_authenticated": False,
        "quarter_population_complete": False,
        "complete_text_coverage_verified": False,
        "acceptance_metadata_coverage_verified": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "outcome_access_authorized": False,
        "qc_job_authorized": False,
        "broker_or_trading_authorized": False,
        "research_looks": 0,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }
    assert sorted(path.name for path in tmp_path.iterdir()) == before
    assert len(result.sha256) == 64


def test_public_retained_scope_rejects_a_synthetic_manifest(tmp_path: Path) -> None:
    _fixture(tmp_path)
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*manifest fingerprint"):
        census_retained_sec_zip_corpus(tmp_path)
    assert RETAINED_ZIP_MANIFEST_SHA256 != hashlib.sha256(
        (tmp_path / _MANIFEST_NAME).read_bytes()
    ).hexdigest()


def test_changed_zip_refuses_before_census(tmp_path: Path) -> None:
    digest = _fixture(tmp_path)
    path = tmp_path / "2006q1_form345.zip"
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*ZIP.*fingerprint"):
        _run(tmp_path, digest)


def test_duplicate_submission_accession_refuses(tmp_path: Path) -> None:
    digest = _fixture(tmp_path, target_rows=(("0000000001-06-000001", "4"), (
        "0000000001-06-000001", "4/A",
    )))
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*duplicate.*accession"):
        _run(tmp_path, digest)


def test_unknown_form_refuses_instead_of_dropping(tmp_path: Path) -> None:
    digest = _fixture(tmp_path, target_rows=(("0000000001-06-000001", "S-1"),))
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*document type"):
        _run(tmp_path, digest)


def test_ragged_submission_row_refuses(tmp_path: Path) -> None:
    digest = _fixture(tmp_path, target_rows=(("0000000001-06-000001", "4\tEXTRA"),))
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*ragged"):
        _run(tmp_path, digest)


def test_manifest_order_and_url_are_not_inferred(tmp_path: Path) -> None:
    digest = _fixture(tmp_path)
    path = tmp_path / _MANIFEST_NAME
    raw = path.read_bytes().replace(b'"2006Q1"', b'"2006Q2"', 1)
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*period"):
        _run(tmp_path, digest)


def test_extra_zip_is_not_silently_ignored(tmp_path: Path) -> None:
    digest = _fixture(tmp_path)
    (tmp_path / "extra.zip").write_bytes(_archive())
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*ZIP inventory"):
        _run(tmp_path, digest)


def test_symlinked_zip_refuses(tmp_path: Path) -> None:
    digest = _fixture(tmp_path)
    target = tmp_path / "2006q1_form345.zip"
    alias = tmp_path / "2006q1_alias.bin"
    alias.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(alias)
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*regular.*single-link"):
        _run(tmp_path, digest)


def test_root_swap_after_manifest_cannot_redirect_zip_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    digest = _fixture(source)
    outside = tmp_path / "outside"
    outside.mkdir()
    _fixture(outside)
    moved = tmp_path / "moved-source"
    real_parse = census_module._manifest_bindings

    def swap_after_manifest(raw: bytes):
        bindings = real_parse(raw)
        source.rename(moved)
        source.symlink_to(outside, target_is_directory=True)
        return bindings

    monkeypatch.setattr(census_module, "_manifest_bindings", swap_after_manifest)
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*directory.*changed"):
        _run(source, digest)


def test_caller_cannot_forge_retained_scope_from_synthetic_receipt(tmp_path: Path) -> None:
    digest = _fixture(tmp_path)
    synthetic = _run(tmp_path, digest)
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*retained.*scope"):
        replace(
            synthetic,
            scope="retained_noncanonical_zip_census",
            source_manifest_sha256=RETAINED_ZIP_MANIFEST_SHA256,
            source_manifest_size_bytes=34_381,
        )


def test_rebinding_quarter_identity_cannot_keep_verified_source_claim(tmp_path: Path) -> None:
    digest = _fixture(tmp_path)
    receipt = _run(tmp_path, digest)
    forged = replace(receipt.quarters[0], zip_sha256="0" * 64)
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*validated.*quarter"):
        replace(receipt, quarters=(forged, *receipt.quarters[1:]))


def test_source_manifest_symlink_and_hardlinked_zip_refuse(tmp_path: Path) -> None:
    digest = _fixture(tmp_path)
    manifest = tmp_path / _MANIFEST_NAME
    copy = tmp_path / "manifest-copy.bin"
    copy.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(copy)
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*regular single-link"):
        _run(tmp_path, digest)

    manifest.unlink()
    manifest.write_bytes(copy.read_bytes())
    archive = tmp_path / "2006q1_form345.zip"
    (tmp_path / "archive-alias.bin").hardlink_to(archive)
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*regular single-link"):
        _run(tmp_path, digest)


def test_root_symlink_refuses_before_any_zip_read(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    digest = _fixture(source)
    link = tmp_path / "link"
    link.symlink_to(source, target_is_directory=True)
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*root.*redirect"):
        _run(link, digest)


def test_duplicate_zip_member_refuses(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("SUBMISSION.tsv", _HEADER)
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("SUBMISSION.tsv", _HEADER)
        archive.writestr("REPORTINGOWNER.tsv", "ACCESSION_NUMBER\tRPTOWNERCIK\n")
        archive.writestr("NONDERIV_TRANS.tsv", "ACCESSION_NUMBER\tNONDERIV_TRANS_SK\n")
    digest = _fixture(tmp_path, archive_bytes=buffer.getvalue())
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED: ZIP member integrity"):
        _run(tmp_path, digest)


def test_header_drift_and_oversized_field_refuse(tmp_path: Path) -> None:
    bad_header = _HEADER.replace("DOCUMENT_TYPE\t", "")
    digest = _fixture(tmp_path, archive_bytes=_archive(submission_text=bad_header))
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED: SUBMISSION header"):
        _run(tmp_path, digest)

    large = _HEADER + (
        "0000000001-06-000001\t01-JAN-2006\t01-JAN-2006\t4\t1\t"
        + "X" * 65_537 + "\tABC\n"
    )
    digest = _fixture(
        tmp_path,
        archive_bytes=_archive(submission_text=large, compression=zipfile.ZIP_STORED),
    )
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*oversized"):
        _run(tmp_path, digest)


def test_quoted_multiline_row_is_counted_once_without_row_output(tmp_path: Path) -> None:
    text = _HEADER + (
        '0000000001-06-000001\t01-JAN-2006\t01-JAN-2006\t4\t1\t'
        '"Issuer\nTwo Lines"\tABC\n'
    )
    digest = _fixture(tmp_path, archive_bytes=_archive(submission_text=text))
    result = _run(tmp_path, digest)
    assert result.submission_accessions == 82
    assert result.form4_accessions == 82
    assert "Issuer" not in str(result.to_payload())


def test_invalid_manifest_timestamp_and_oversized_integer_refuse_typed(
    tmp_path: Path,
) -> None:
    digest = _fixture(tmp_path)
    manifest = tmp_path / _MANIFEST_NAME
    raw = manifest.read_bytes().replace(b"2026-09-24", b"2026-99-24", 1)
    manifest.write_bytes(raw)
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*timestamp"):
        _run(tmp_path, hashlib.sha256(raw).hexdigest())

    _fixture(tmp_path)
    raw = manifest.read_bytes()
    first_size = str(len(_archive())).encode("ascii")
    raw = raw.replace(b'"' + first_size + b'"', b'"' + b"9" * 5000 + b'"', 1)
    manifest.write_bytes(raw)
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*provenance"):
        _run(tmp_path, hashlib.sha256(raw).hexdigest())


def test_unhashable_private_scope_refuses_typed(tmp_path: Path) -> None:
    with pytest.raises(SecZipCorpusCensusError, match="REFUSED:.*scope"):
        _census_zip_corpus(
            tmp_path, expected_manifest_sha256="a" * 64, scope=[],  # type: ignore[arg-type]
        )
