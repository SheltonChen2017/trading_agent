"""Synthetic full-window and dangerous-direction tests for offline IB-1B publication."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_payload
from research import insider_buying_ib1b_82q_snapshot_runner as runner
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
_PARSER_COMMIT = "b" * 40
_CAPTURE_COMMIT = "a4192546b168470ff1e9c421d8bd53531a1b3c05"
_STAMP = "2026-09-24T22:52:19.7647157Z"


def _url(period: str) -> str:
    route = "datastandardsinnovation" if period == "2026Q2" else "structureddata"
    return (
        f"https://www.sec.gov/files/{route}/data/insider-transactions-data-sets/"
        f"{period.lower()}_form345.zip"
    )


def _archive(period: str, *, duplicate_transaction: bool = False) -> bytes:
    profile = build_retained_82q_schema_profile_candidate()
    accession = f"0000123456-{int(period[:4]) % 100:02d}-{int(period[-1]):06d}"
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for table in ALLOWED_SEC_TABLES:
            headers = profile.variant_for(table, int(period[:4]), int(period[-1])).headers
            lines = ["\t".join(headers)]
            if table == "SUBMISSION.tsv":
                values = {header: "" for header in headers}
                values.update(
                    ACCESSION_NUMBER=accession,
                    FILING_DATE=f"{period[:4]}-01-15",
                    PERIOD_OF_REPORT=f"{period[:4]}-01-14",
                    DOCUMENT_TYPE="4",
                    ISSUERCIK="0000123456",
                    ISSUERNAME="Synthetic issuer",
                    ISSUERTRADINGSYMBOL="SYN",
                )
                lines.append("\t".join(values[header] for header in headers))
            if table == "NONDERIV_TRANS.tsv" and duplicate_transaction:
                values = {header: "" for header in headers}
                values.update(ACCESSION_NUMBER=accession, NONDERIV_TRANS_SK="1")
                line = "\t".join(values[header] for header in headers)
                lines.extend((line, line))
            archive.writestr(table, ("\n".join(lines) + "\n").encode("utf-8"))
    return sink.getvalue()


def _fixture(root: Path, *, duplicate_transaction: bool = False):
    source = root / "source"
    source.mkdir()
    rows = []
    for period in _PERIODS:
        raw = _archive(period, duplicate_transaction=duplicate_transaction and period == "2006Q1")
        name = f"{period.lower()}_form345.zip"
        (source / name).write_bytes(raw)
        rows.append((
            period, name, _url(period), str(len(raw)), hashlib.sha256(raw).hexdigest(),
            _STAMP, "local filesystem last-write time; not SEC-attested",
            _CAPTURE_COMMIT,
            "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets",
        ))
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow((
        "Period", "FileName", "SourceUrl", "SizeBytes", "SHA256",
        "LocalLastWriteUtc", "TimestampBasis", "CaptureCommit", "SourceIndexUrl",
    ))
    writer.writerows(rows)
    manifest = buffer.getvalue().encode("utf-8")
    (source / "insider_quarterly_zip_manifest_2006q1_2026q2.csv").write_bytes(manifest)
    census = _census_zip_corpus(
        source, expected_manifest_sha256=hashlib.sha256(manifest).hexdigest(),
        scope="synthetic_test_census",
    )
    return source, root / "output", census


def _run(source: Path, destination: Path, census):
    return runner._run_bound_ib1b_82q(
        source, destination, _PARSER_COMMIT,
        census=census, profile=build_retained_82q_schema_profile_candidate(),
    )


def _payload(path: Path):
    raw = path.read_bytes()
    envelope = json.loads(raw)
    assert raw == (canonical_json(envelope) + "\n").encode("utf-8")
    assert envelope["payload_sha256"] == hash_payload(envelope["payload"])
    return envelope["payload"]


def test_82_synthetic_quarters_resume_after_interruption_and_publish_only_at_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, destination, census = _fixture(tmp_path.resolve())
    original = runner.build_sec_bulk_parsed_snapshot
    calls = 0

    def stop_on_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "build_sec_bulk_parsed_snapshot", stop_on_second)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        _run(source, destination, census)
    assert (destination / "journal" / "quarter-2006Q1.json").is_file()
    assert not (destination / "journal" / "quarter-2006Q2.json").exists()
    assert not (destination / "ib1b-82q-completion.json").exists()
    assert len(list((destination / "ib1a").glob("sec-insider-bulk-*"))) == 2

    monkeypatch.setattr(runner, "build_sec_bulk_parsed_snapshot", original)
    report = _run(source, destination, census)
    payload = _payload(report)
    assert payload["archive_counts"] == {"accepted": 82, "refused": 0, "quarantined": 0}
    assert len(payload["quarters"]) == 82
    assert tuple(item["period"] for item in payload["quarters"]) == _PERIODS
    assert all(item["accession_count"] == 1 for item in payload["quarters"])
    assert all(item["document_forms"] == {"3": 0, "3/A": 0, "4": 1, "4/A": 0, "5": 0, "5/A": 0}
               for item in payload["quarters"])
    assert all(item["legacy_field_is_verified_retrieval"] is False for item in payload["quarters"])
    assert payload["canonical"] is False
    assert payload["point_in_time_data"] is False
    assert payload["source_provenance_verified"] is False
    assert payload["acceptance_metadata_verified"] is False
    assert payload["parser_git_commit_verified"] is False
    assert all(item["parser_git_commit_verified"] is False for item in payload["quarters"])
    assert all(value == (0 if name.endswith("looks") else False)
               for name, value in payload["authority"].items())
    assert len(list((destination / "journal").glob("quarter-*.json"))) == 82
    assert len(list((destination / "ib1a").glob("sec-insider-bulk-*"))) == 82
    assert len(list((destination / "ib1b").glob("sec-insider-parsed-*"))) == 82
    assert b"Synthetic issuer" not in report.read_bytes()


def test_source_change_after_census_refuses_before_output(tmp_path: Path) -> None:
    source, destination, census = _fixture(tmp_path.resolve())
    target = source / "2006q1_form345.zip"
    target.write_bytes(target.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="REFUSED:"):
        _run(source, destination, census)
    assert not destination.exists()


def test_profile_drift_and_bad_parser_commit_refuse_before_output(tmp_path: Path) -> None:
    source, destination, census = _fixture(tmp_path.resolve())
    profile = build_retained_82q_schema_profile_candidate()
    with pytest.raises(ValueError, match="REFUSED:"):
        runner._run_bound_ib1b_82q(
            source, destination, _PARSER_COMMIT,
            census=census, profile=replace(profile, profile_id="unreviewed"),
        )
    with pytest.raises(runner.Ib1b82qSnapshotError, match="parser Git commit"):
        runner._run_bound_ib1b_82q(
            source, destination, "BAD", census=census, profile=profile,
        )
    assert not destination.exists()


def test_retained_entry_rejects_unverified_commit_before_source_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        runner, "census_retained_sec_zip_corpus", lambda _: calls.append("source")
    )
    with pytest.raises(runner.Ib1b82qSnapshotError, match="parser.*commit|clean.*HEAD"):
        runner.run_retained_ib1b_82q(
            tmp_path / "source", tmp_path / "output", "b" * 40
        )
    assert calls == []
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_output_lock_link_refuses_without_writing_outside_root(
    tmp_path: Path, link_kind: str,
) -> None:
    source, destination, census = _fixture(tmp_path.resolve())
    destination.mkdir()
    sentinel = tmp_path / "unrelated-empty-sentinel"
    sentinel.write_bytes(b"")
    lock = destination / ".ib1b-82q.lock"
    if link_kind == "symlink":
        lock.symlink_to(sentinel)
    else:
        os.link(sentinel, lock)
    with pytest.raises(runner.Ib1b82qSnapshotError, match="lock"):
        _run(source, destination, census)
    assert sentinel.read_bytes() == b""
    assert not (destination / "run-binding.json").exists()


def test_parser_key_failure_retains_no_aggregate_success(tmp_path: Path) -> None:
    source, destination, census = _fixture(tmp_path.resolve(), duplicate_transaction=True)
    with pytest.raises(ValueError, match="duplicate source-row key"):
        _run(source, destination, census)
    assert not (destination / "ib1b-82q-completion.json").exists()
    assert not list((destination / "journal").glob("quarter-*.json"))


def test_output_overlap_and_public_retained_entry_reject_synthetic_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, destination, census = _fixture(tmp_path.resolve())
    with pytest.raises(runner.Ib1b82qSnapshotError, match="outside"):
        _run(source, source / "output", census)
    monkeypatch.setattr(runner, "_verify_retained_parser_commit", lambda _: None)
    with pytest.raises(ValueError, match="REFUSED:.*manifest fingerprint"):
        runner.run_retained_ib1b_82q(source, destination, _PARSER_COMMIT)
    assert not destination.exists()


def test_foreign_output_and_forged_resume_receipt_refuse(tmp_path: Path) -> None:
    source, destination, census = _fixture(tmp_path.resolve())
    destination.mkdir()
    (destination / "foreign.txt").write_text("unbound")
    with pytest.raises(runner.Ib1b82qSnapshotError, match="unbound or unexpected"):
        _run(source, destination, census)
    (destination / "foreign.txt").unlink()
    report = _run(source, destination, census)
    assert report.is_file()
    journal = destination / "journal" / "quarter-2006Q1.json"
    envelope = json.loads(journal.read_bytes())
    envelope["payload"]["accession_count"] = 2
    envelope["payload_sha256"] = hash_payload(envelope["payload"])
    journal.write_bytes((canonical_json(envelope) + "\n").encode("utf-8"))
    with pytest.raises(runner.Ib1b82qSnapshotError, match="replayed immutable snapshots"):
        _run(source, destination, census)


def test_interrupted_receipt_temporaries_recover_only_from_matching_bytes(
    tmp_path: Path,
) -> None:
    source, destination, census = _fixture(tmp_path.resolve())
    report = _run(source, destination, census)
    journal = destination / "journal" / "quarter-2006Q1.json"
    linked_temp = journal.with_name(".quarter-2006Q1.json." + "a" * 32 + ".tmp")
    os.link(journal, linked_temp)
    assert journal.stat().st_nlink == 2
    assert _run(source, destination, census) == report
    assert not linked_temp.exists()
    assert journal.stat().st_nlink == 1

    original = journal.read_bytes()
    journal.unlink()
    partial_temp = journal.with_name(".quarter-2006Q1.json." + "b" * 32 + ".tmp")
    partial_temp.write_bytes(original[:20])
    assert _run(source, destination, census) == report
    assert not partial_temp.exists()
    assert journal.read_bytes() == original

    journal.unlink()
    wrong_temp = journal.with_name(".quarter-2006Q1.json." + "c" * 32 + ".tmp")
    wrong_temp.write_bytes(b"foreign")
    with pytest.raises(runner.Ib1b82qSnapshotError, match="temporary differs"):
        _run(source, destination, census)
    assert not journal.exists()
    assert wrong_temp.read_bytes() == b"foreign"


# Section 119 (Claude review): regression for IBOFF-CR02. Deeply nested JSON
# inside the receipt byte cap raises RecursionError, which must be a typed
# refusal like every other malformed receipt.
def test_deeply_nested_receipt_is_a_typed_refusal() -> None:
    with pytest.raises(runner.Ib1b82qSnapshotError, match="not canonical JSON"):
        runner._parse_envelope(("[" * 16000).encode("ascii"))
