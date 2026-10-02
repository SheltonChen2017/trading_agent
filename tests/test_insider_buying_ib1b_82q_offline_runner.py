"""Synthetic tests for the read-only 82-quarter IB-1B header preflight."""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from research.insider_buying import ib1b_82q_offline_runner as runner
from research.insider_buying.sec_bulk_snapshot import ALLOWED_SEC_TABLES
from research.insider_buying.sec_ib1b_82q_schema_profile import (
    build_retained_82q_schema_profile_candidate,
)
from research.insider_buying.sec_zip_corpus_census import _census_zip_corpus


_PERIODS = tuple(
    f"{year}Q{quarter}"
    for year in range(2006, 2027)
    for quarter in range(1, 5)
    if (year, quarter) <= (2026, 2)
)
_MANIFEST_NAME = "insider_quarterly_zip_manifest_2006q1_2026q2.csv"
_BASIS = "local filesystem last-write time; not SEC-attested"
_CAPTURE_COMMIT = "a4192546b168470ff1e9c421d8bd53531a1b3c05"
_INDEX_URL = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"


def _source_url(period: str) -> str:
    route = "datastandardsinnovation" if period == "2026Q2" else "structureddata"
    return (
        f"https://www.sec.gov/files/{route}/data/insider-transactions-data-sets/"
        f"{period.lower()}_form345.zip"
    )


def _archive(year: int, quarter: int, *, footnote_drift: bool = False) -> bytes:
    profile = build_retained_82q_schema_profile_candidate()
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for table in ALLOWED_SEC_TABLES:
            variant = profile.variant_for(table, year, quarter)
            header = "\t".join(variant.headers) + "\n"
            if table == "FOOTNOTES.tsv" and footnote_drift:
                header = header.replace("\n", "\tUNREVIEWED_COLUMN\n")
            archive.writestr(table, header)
    return sink.getvalue()


def _fixture(root: Path, *, drift_period: str | None = None) -> str:
    early = _archive(2006, 1)
    late = _archive(2026, 2)
    drift = _archive(2006, 1, footnote_drift=True)
    rows = []
    for period in _PERIODS:
        raw = (
            drift if period == drift_period else
            early if period <= "2022Q4" else late
        )
        filename = f"{period.lower()}_form345.zip"
        (root / filename).write_bytes(raw)
        rows.append((
            period, filename, _source_url(period), str(len(raw)),
            hashlib.sha256(raw).hexdigest(),
            "2026-09-24T22:52:19.7647157Z", _BASIS, _CAPTURE_COMMIT, _INDEX_URL,
        ))
    text = io.StringIO(newline="")
    writer = csv.writer(text, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow((
        "Period", "FileName", "SourceUrl", "SizeBytes", "SHA256",
        "LocalLastWriteUtc", "TimestampBasis", "CaptureCommit", "SourceIndexUrl",
    ))
    writer.writerows(rows)
    manifest = text.getvalue().encode("utf-8")
    (root / _MANIFEST_NAME).write_bytes(manifest)
    return hashlib.sha256(manifest).hexdigest()


def _synthetic_preflight(root: Path, manifest_sha256: str):
    census = _census_zip_corpus(
        root,
        expected_manifest_sha256=manifest_sha256,
        scope="synthetic_test_census",
    )
    return runner._preflight_ib1b_82q_headers(
        root, census, build_retained_82q_schema_profile_candidate()
    )


def test_all_82_synthetic_headers_are_checked_without_publication(tmp_path: Path) -> None:
    digest = _fixture(tmp_path)
    before = {item.name for item in tmp_path.iterdir()}
    report = _synthetic_preflight(tmp_path, digest)
    payload = report.to_payload()

    assert report.scope == "synthetic_test_header_preflight"
    assert len(report.quarters) == 82
    assert report.quarters[0].period == "2006Q1"
    assert report.quarters[-1].period == "2026Q2"
    assert all(len(item.header_line_sha256) == 8 for item in report.quarters)
    assert payload["parser_run_performed"] is False
    assert payload["row_keys_or_counts_verified_by_ib1b"] is False
    assert payload["snapshot_written"] is False
    assert all(value is False for key, value in payload["authority"].items()
               if key not in {"research_looks", "authorized_outcome_looks", "consumed_outcome_looks"})
    assert (payload["authority"]["research_looks"],
            payload["authority"]["authorized_outcome_looks"],
            payload["authority"]["consumed_outcome_looks"]) == (0, 0, 0)
    assert len(report.sha256) == 64
    assert {item.name for item in tmp_path.iterdir()} == before


def test_changed_zip_after_census_refuses_before_receipt(tmp_path: Path) -> None:
    digest = _fixture(tmp_path)
    census = _census_zip_corpus(
        tmp_path, expected_manifest_sha256=digest, scope="synthetic_test_census"
    )
    target = tmp_path / "2006q1_form345.zip"
    target.write_bytes(target.read_bytes() + b"changed")
    with pytest.raises((runner.Ib1b82qOfflinePreflightError, ValueError), match="REFUSED:"):
        runner._preflight_ib1b_82q_headers(
            tmp_path, census, build_retained_82q_schema_profile_candidate()
        )


def test_header_drift_with_coherent_census_refuses(tmp_path: Path) -> None:
    digest = _fixture(tmp_path, drift_period="2006Q1")
    with pytest.raises(runner.Ib1b82qOfflinePreflightError,
                       match="REFUSED: physical TSV header"):
        _synthetic_preflight(tmp_path, digest)


def test_missing_non_submission_table_refuses_at_header_boundary() -> None:
    source = _archive(2006, 1)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as original:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as changed:
            for item in original.infolist():
                if item.filename != "FOOTNOTES.tsv":
                    changed.writestr(item.filename, original.read(item))
    with pytest.raises(runner.Ib1b82qOfflinePreflightError,
                       match="REFUSED: ZIP does not contain"):
        runner._quarter_headers(
            output.getvalue(), "2006Q1", build_retained_82q_schema_profile_candidate()
        )


def test_unchanged_parser_input_budget_is_checked_before_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = _fixture(tmp_path)
    monkeypatch.setattr(runner, "MAX_TOTAL_PARSED_INPUT_BYTES", 1)
    with pytest.raises(runner.Ib1b82qOfflinePreflightError,
                       match="REFUSED: ZIP expanded table inventory"):
        _synthetic_preflight(tmp_path, digest)


def test_report_rejects_rebound_quarter_and_retained_scope(tmp_path: Path) -> None:
    digest = _fixture(tmp_path)
    report = _synthetic_preflight(tmp_path, digest)
    forged = replace(report.quarters[0], header_line_sha256=("0" * 64,) * 8)
    with pytest.raises(runner.Ib1b82qOfflinePreflightError,
                       match="REFUSED:.*inventory changed"):
        replace(report, quarters=(forged, *report.quarters[1:]))
    with pytest.raises(runner.Ib1b82qOfflinePreflightError,
                       match="REFUSED:.*receipt is malformed"):
        replace(
            report,
            scope="retained_noncanonical_header_preflight",
            census_sha256=runner.RETAINED_82Q_CENSUS_SHA256,
        )


def test_public_retained_entry_does_not_adopt_synthetic_manifest(tmp_path: Path) -> None:
    _fixture(tmp_path)
    with pytest.raises(ValueError, match="REFUSED:.*manifest fingerprint"):
        runner.preflight_retained_ib1b_82q_headers(tmp_path)


def test_preflight_refuses_a_caller_mutated_profile(tmp_path: Path) -> None:
    digest = _fixture(tmp_path)
    census = _census_zip_corpus(
        tmp_path, expected_manifest_sha256=digest, scope="synthetic_test_census"
    )
    profile = build_retained_82q_schema_profile_candidate()
    changed = replace(profile, profile_id="fake")
    with pytest.raises(runner.Ib1b82qOfflinePreflightError,
                       match="REFUSED: source census or header-only profile"):
        runner._preflight_ib1b_82q_headers(tmp_path, census, changed)
