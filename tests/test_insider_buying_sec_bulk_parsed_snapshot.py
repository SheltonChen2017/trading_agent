"""IB-1B tests for explicit-schema, offline SEC TSV parsed snapshots."""
from __future__ import annotations

import csv
import io
import json
import stat
import warnings
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import (
    ALLOWED_SEC_TABLES,
    PARSED_SNAPSHOT_CONTRACT_VERSION,
    SEC_TSV_PARSER_VERSION,
    SecBulkParsedSnapshotError,
    SecBulkSource,
    SecTsvSchemaProfile,
    SecTsvSchemaVariant,
    build_sec_bulk_parsed_snapshot,
    load_sec_bulk_parsed_snapshot,
    write_sec_bulk_snapshot,
)
from research.insider_buying import sec_bulk_parsed_snapshot as parsed_module


RETRIEVED = datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc)
CAPTURE_COMMIT = "a" * 40
PARSER_COMMIT = "b" * 40
SOURCE_URL = (
    "https://www.sec.gov/files/dera/data/insider-transactions-data-sets/"
    "2026q2_form345.zip"
)

# These literal profiles are deliberately synthetic test fixtures.  They are
# not exported by product code and do not claim to be an official SEC header
# dictionary.
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
    "TRANSACTIONSHARES",
    "TRANSACTIONPRICEPERSHARE",
    "NOTE",
)
FOOTNOTE_HEADERS = ("ACCESSION_NUMBER", "FOOTNOTE_ID", "FOOTNOTE")

ACCESSION_A = "0000123456-26-000001"
ACCESSION_B = "0000123456-26-000002"
ACCESSION_C = "0000123456-26-000003"


def _source(**overrides) -> SecBulkSource:
    values = {
        "year": 2026,
        "quarter": 2,
        "source_url": SOURCE_URL,
        "git_commit": CAPTURE_COMMIT,
        "retrieved_at": RETRIEVED,
    }
    values.update(overrides)
    return SecBulkSource(**values)


def _tsv(
    headers: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
    *,
    line_terminator: str = "\n",
    bom: bool = False,
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(
        stream,
        delimiter="\t",
        quotechar='"',
        doublequote=True,
        escapechar=None,
        lineterminator=line_terminator,
    )
    writer.writerow(headers)
    writer.writerows(rows)
    encoded = stream.getvalue().encode("utf-8")
    return (b"\xef\xbb\xbf" + encoded) if bom else encoded


def _default_tables() -> dict[str, bytes]:
    return {
        "SUBMISSION.tsv": _tsv(
            SUBMISSION_HEADERS,
            (
                (
                    ACCESSION_A,
                    "2026-05-01",
                    "2026-04-30",
                    "4",
                    "0000123456",
                    "Synthetic Issuer",
                    "SYN",
                ),
            ),
        ),
        "REPORTINGOWNER.tsv": _tsv(
            OWNER_HEADERS,
            (
                (
                    ACCESSION_A,
                    "0000000042",
                    "Doe, Zoë",
                    "1",
                    "0",
                ),
            ),
        ),
        "NONDERIV_TRANS.tsv": _tsv(
            TRANS_HEADERS,
            ((ACCESSION_A, "0000007", "0001.2300", "1e3", ""),),
        ),
    }


def _archive(tables: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for table_name in ALLOWED_SEC_TABLES:
            if table_name not in tables:
                continue
            info = zipfile.ZipInfo(
                table_name,
                date_time=(2026, 8, 20, 18, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Duplicate name")
                archive.writestr(info, tables[table_name])
    return stream.getvalue()


def _profile(
    *,
    profile_id: str = "synthetic-qc-profile-v1",
    headers_by_table: dict[str, tuple[str, ...]] | None = None,
    valid_from: tuple[int, int] = (2026, 1),
    valid_through: tuple[int, int] = (2026, 4),
) -> SecTsvSchemaProfile:
    headers_by_table = headers_by_table or {
        "SUBMISSION.tsv": SUBMISSION_HEADERS,
        "REPORTINGOWNER.tsv": OWNER_HEADERS,
        "NONDERIV_TRANS.tsv": TRANS_HEADERS,
    }
    variants = tuple(
        SecTsvSchemaVariant(
            schema_id=f"synthetic-{table_name.removesuffix('.tsv').lower()}-v1",
            table_name=table_name,
            headers=headers_by_table[table_name],
            source_row_key_headers=(
                ("TRANS_SK",)
                if table_name == "NONDERIV_TRANS.tsv"
                else ()
            ),
            valid_from_year=valid_from[0],
            valid_from_quarter=valid_from[1],
            valid_through_year=valid_through[0],
            valid_through_quarter=valid_through[1],
        )
        for table_name in ALLOWED_SEC_TABLES
        if table_name in headers_by_table
    )
    return SecTsvSchemaProfile(profile_id=profile_id, variants=variants)


def _raw_snapshot(
    tmp_path: Path,
    *,
    tables: dict[str, bytes] | None = None,
    source: SecBulkSource | None = None,
    root_name: str = "raw",
) -> Path:
    raw_root = tmp_path / root_name
    identity = write_sec_bulk_snapshot(
        _archive(tables or _default_tables()),
        source or _source(),
        raw_root,
    )
    return raw_root / identity.snapshot_id


def _publish(
    tmp_path: Path,
    *,
    tables: dict[str, bytes] | None = None,
    profile: SecTsvSchemaProfile | None = None,
    parser_git_commit: str = PARSER_COMMIT,
    raw_root_name: str = "raw",
    parsed_root_name: str = "parsed",
):
    raw = _raw_snapshot(tmp_path, tables=tables, root_name=raw_root_name)
    parsed_root = tmp_path / parsed_root_name
    identity = build_sec_bulk_parsed_snapshot(
        raw,
        parsed_root,
        schema_profile=profile or _profile(),
        parser_git_commit=parser_git_commit,
    )
    return raw, parsed_root / identity.snapshot_id, identity


def _expected_parsed_publication(raw: Path):
    identity, rows, accessions, rows_bytes, accessions_bytes = (
        parsed_module._assemble_parsed_snapshot(
            raw,
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )
    )
    manifest_bytes = (canonical_json(identity.to_payload()) + "\n").encode("utf-8")
    payloads = {
        "rows.jsonl": rows_bytes,
        "accessions.jsonl": accessions_bytes,
        "manifest.json": manifest_bytes,
    }
    commit_bytes = (
        canonical_json(
            {
                "kind": f"{parsed_module.PARSED_SNAPSHOT_KIND}-commit",
                "snapshot_id": identity.snapshot_id,
                "members": {
                    name: hash_bytes(data) for name, data in sorted(payloads.items())
                },
            }
        )
        + "\n"
    ).encode("utf-8")
    return identity, rows, accessions, {**payloads, "snapshot.commit.json": commit_bytes}


def _rewrite_commit(target: Path) -> None:
    commit_path = target / "snapshot.commit.json"
    commit = json.loads(commit_path.read_text(encoding="utf-8"))
    commit["members"] = {
        name: hash_bytes((target / name).read_bytes())
        for name in ("rows.jsonl", "accessions.jsonl", "manifest.json")
    }
    commit_path.write_bytes((canonical_json(commit) + "\n").encode("utf-8"))


def _readdress_parsed_snapshot(target: Path) -> Path:
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lineage_payload = {
        key: value
        for key, value in manifest.items()
        if key not in {"lineage_hash", "snapshot_id"}
    }
    lineage_hash = hash_payload(lineage_payload)
    new_snapshot_id = (
        f"sec-insider-parsed-{manifest['year']:04d}q{manifest['quarter']}-"
        f"{lineage_hash[:16]}"
    )
    manifest["lineage_hash"] = lineage_hash
    manifest["snapshot_id"] = new_snapshot_id
    manifest_path.write_bytes((canonical_json(manifest) + "\n").encode("utf-8"))
    commit_path = target / "snapshot.commit.json"
    commit = json.loads(commit_path.read_text(encoding="utf-8"))
    commit["snapshot_id"] = new_snapshot_id
    commit_path.write_bytes((canonical_json(commit) + "\n").encode("utf-8"))
    destination = target.parent / new_snapshot_id
    target.rename(destination)
    _rewrite_commit(destination)
    return destination


def _symlink_or_skip(link: Path, target: Path, *, is_directory: bool) -> None:
    try:
        link.symlink_to(target.resolve(), target_is_directory=is_directory)
    except OSError as exc:
        pytest.skip(f"filesystem symlinks unavailable: {exc}")


def test_round_trip_preserves_exact_strings_quoted_text_and_lineage(tmp_path):
    note = 'private\tplacement\nsaid "go"'
    tables = _default_tables()
    tables["NONDERIV_TRANS.tsv"] = _tsv(
        TRANS_HEADERS,
        ((ACCESSION_A, "0000007", "0001.2300", "1e3", note),),
        line_terminator="\r\n",
        bom=True,
    )
    raw, parsed, identity = _publish(tmp_path, tables=tables)
    loaded = load_sec_bulk_parsed_snapshot(
        parsed, raw_snapshot_directory=raw
    )

    transaction = next(
        row for row in loaded.rows if row.table_name == "NONDERIV_TRANS.tsv"
    )
    assert transaction.values == (
        ACCESSION_A,
        "0000007",
        "0001.2300",
        "1e3",
        note,
    )
    assert transaction.source_row_key == ("0000007",)
    assert all(isinstance(value, str) for value in transaction.values)
    assert identity == loaded.identity
    assert identity.raw_snapshot_id == raw.name
    assert identity.parser_git_commit == PARSER_COMMIT
    assert identity.schema_profile.profile_id == "synthetic-qc-profile-v1"
    assert identity.to_payload()["parser_version"] == SEC_TSV_PARSER_VERSION
    assert (
        identity.to_payload()["parsed_contract_version"]
        == PARSED_SNAPSHOT_CONTRACT_VERSION
    )
    assert {path.name for path in parsed.iterdir()} == {
        "rows.jsonl",
        "accessions.jsonl",
        "manifest.json",
        "snapshot.commit.json",
    }
    for line in (parsed / "rows.jsonl").read_bytes().splitlines(keepends=True):
        value = json.loads(line)
        assert line == (canonical_json(value) + "\n").encode("utf-8")


def test_owner_rows_do_not_multiply_transaction_rows(tmp_path):
    tables = _default_tables()
    tables["REPORTINGOWNER.tsv"] = _tsv(
        OWNER_HEADERS,
        (
            (ACCESSION_A, "0000000042", "Owner One", "1", "0"),
            (ACCESSION_A, "0000000043", "Owner Two", "0", "1"),
        ),
    )
    tables["NONDERIV_TRANS.tsv"] = _tsv(
        TRANS_HEADERS,
        ((ACCESSION_A, "0000007", "10", "20", ""),),
    )
    raw, parsed, _ = _publish(tmp_path, tables=tables)
    loaded = load_sec_bulk_parsed_snapshot(
        parsed, raw_snapshot_directory=raw
    )

    assert len(loaded.rows) == 4
    accession = loaded.accessions[0]
    references = dict(accession.table_rows)
    assert len(references["REPORTINGOWNER.tsv"]) == 2
    assert len(references["NONDERIV_TRANS.tsv"]) == 1
    assert len(set(references["NONDERIV_TRANS.tsv"])) == 1


def test_distinct_source_keys_preserve_similar_rows_and_exact_retry_is_stable(
    tmp_path,
):
    tables = _default_tables()
    first_lot = (ACCESSION_A, "0000007", "10", "20", "same")
    second_lot = (ACCESSION_A, "0000008", "10", "20", "same")
    tables["NONDERIV_TRANS.tsv"] = _tsv(
        TRANS_HEADERS, (first_lot, second_lot)
    )
    raw, parsed, first = _publish(tmp_path, tables=tables)
    before_mtimes = {path.name: path.stat().st_mtime_ns for path in parsed.iterdir()}
    transaction_rows = tuple(
        row
        for row in load_sec_bulk_parsed_snapshot(
            parsed, raw_snapshot_directory=raw
        ).rows
        if row.table_name == "NONDERIV_TRANS.tsv"
    )
    assert len(transaction_rows) == 2
    assert transaction_rows[0].values[2:] == transaction_rows[1].values[2:]
    assert transaction_rows[0].source_row_key != transaction_rows[1].source_row_key
    assert transaction_rows[0].row_id != transaction_rows[1].row_id

    second = build_sec_bulk_parsed_snapshot(
        raw,
        parsed.parent,
        schema_profile=_profile(),
        parser_git_commit=PARSER_COMMIT,
    )
    assert second == first
    assert {path.name: path.stat().st_mtime_ns for path in parsed.iterdir()} == before_mtimes


def test_duplicate_accession_relative_transaction_source_key_refuses(tmp_path):
    tables = _default_tables()
    tables["NONDERIV_TRANS.tsv"] = _tsv(
        TRANS_HEADERS,
        (
            (ACCESSION_A, "0000007", "10", "20", "first"),
            (ACCESSION_A, "0000007", "11", "21", "second"),
        ),
    )
    raw = _raw_snapshot(tmp_path, tables=tables)
    with pytest.raises(SecBulkParsedSnapshotError, match="duplicate source-row key"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )


@pytest.mark.parametrize("source_key", ["", "   "])
def test_transaction_schema_requires_declared_nonblank_source_row_key(
    tmp_path, source_key
):
    with pytest.raises(SecBulkParsedSnapshotError, match="caller-declared source-row key"):
        SecTsvSchemaVariant(
            schema_id="synthetic-trans-without-key",
            table_name="NONDERIV_TRANS.tsv",
            headers=TRANS_HEADERS,
            source_row_key_headers=(),
            valid_from_year=2026,
            valid_from_quarter=1,
            valid_through_year=2026,
            valid_through_quarter=4,
        )

    tables = _default_tables()
    tables["NONDERIV_TRANS.tsv"] = _tsv(
        TRANS_HEADERS,
        ((ACCESSION_A, source_key, "10", "20", "blank key"),),
    )
    raw = _raw_snapshot(tmp_path, tables=tables)
    with pytest.raises(SecBulkParsedSnapshotError, match="source-row key is blank"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda headers: headers[:-1],
        lambda headers: headers + ("EXTRA",),
        lambda headers: (headers[1], headers[0], *headers[2:]),
        lambda headers: (headers[0].lower(), *headers[1:]),
        lambda headers: (" ACCESSION_NUMBER", *headers[1:]),
        lambda headers: (headers[0], headers[0], *headers[2:]),
    ],
)
def test_observed_header_must_match_exact_order_case_and_width(tmp_path, mutate):
    tables = _default_tables()
    bad_headers = tuple(mutate(TRANS_HEADERS))
    tables["NONDERIV_TRANS.tsv"] = _tsv(
        bad_headers,
        (tuple("x" for _ in bad_headers),),
    )
    raw = _raw_snapshot(tmp_path, tables=tables)
    with pytest.raises(SecBulkParsedSnapshotError, match="header"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )
    assert not (tmp_path / "parsed").exists()


def test_product_has_no_implicit_schema_profile(tmp_path):
    raw = _raw_snapshot(tmp_path)
    with pytest.raises(SecBulkParsedSnapshotError, match="explicit immutable"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed",
            schema_profile=None,
            parser_git_commit=PARSER_COMMIT,
        )


def test_present_optional_table_requires_an_explicit_variant(tmp_path):
    tables = _default_tables()
    tables["FOOTNOTES.tsv"] = _tsv(
        FOOTNOTE_HEADERS,
        ((ACCESSION_A, "F1", "synthetic note"),),
    )
    raw = _raw_snapshot(tmp_path, tables=tables)
    with pytest.raises(SecBulkParsedSnapshotError, match="no exact quarter variant"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )


def test_optional_table_is_preserved_when_profiled_and_absence_is_explicit(tmp_path):
    tables = _default_tables()
    tables["FOOTNOTES.tsv"] = _tsv(
        FOOTNOTE_HEADERS,
        ((ACCESSION_A, "F1", "synthetic note"),),
    )
    headers = {
        "SUBMISSION.tsv": SUBMISSION_HEADERS,
        "REPORTINGOWNER.tsv": OWNER_HEADERS,
        "NONDERIV_TRANS.tsv": TRANS_HEADERS,
        "FOOTNOTES.tsv": FOOTNOTE_HEADERS,
    }
    raw, parsed, identity = _publish(
        tmp_path,
        tables=tables,
        profile=_profile(headers_by_table=headers),
    )
    loaded = load_sec_bulk_parsed_snapshot(
        parsed, raw_snapshot_directory=raw
    )
    assert any(row.table_name == "FOOTNOTES.tsv" for row in loaded.rows)
    assert "FOOTNOTES.tsv" not in identity.absent_tables
    assert "DERIV_TRANS.tsv" in identity.absent_tables


def test_schema_quarter_ranges_are_exact_and_non_overlapping(tmp_path):
    raw = _raw_snapshot(tmp_path)
    gap_profile = _profile(valid_from=(2026, 3), valid_through=(2026, 4))
    with pytest.raises(SecBulkParsedSnapshotError, match="no exact quarter variant"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed",
            schema_profile=gap_profile,
            parser_git_commit=PARSER_COMMIT,
        )

    submission = _profile().variants[0]
    overlapping = SecTsvSchemaVariant(
        schema_id="synthetic-submission-v2",
        table_name="SUBMISSION.tsv",
        headers=SUBMISSION_HEADERS,
        source_row_key_headers=(),
        valid_from_year=2026,
        valid_from_quarter=4,
        valid_through_year=2027,
        valid_through_quarter=1,
    )
    owner, transaction = _profile().variants[1:]
    with pytest.raises(SecBulkParsedSnapshotError, match="overlap"):
        SecTsvSchemaProfile(
            profile_id="overlap",
            variants=(submission, overlapping, owner, transaction),
        )


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"valid_from_year": True}, "exact integer"),
        ({"valid_from_quarter": 0}, "quarter"),
        (
            {
                "valid_from_year": 2027,
                "valid_from_quarter": 1,
                "valid_through_year": 2026,
                "valid_through_quarter": 4,
            },
            "reversed",
        ),
    ],
)
def test_schema_period_contract_rejects_type_confusion_and_reversal(kwargs, message):
    values = {
        "schema_id": "synthetic-submission",
        "table_name": "SUBMISSION.tsv",
        "headers": SUBMISSION_HEADERS,
        "source_row_key_headers": (),
        "valid_from_year": 2026,
        "valid_from_quarter": 1,
        "valid_through_year": 2026,
        "valid_through_quarter": 4,
    }
    values.update(kwargs)
    with pytest.raises(SecBulkParsedSnapshotError, match=message):
        SecTsvSchemaVariant(**values)


def test_zero_byte_member_refuses_but_header_only_tables_are_valid(tmp_path):
    zero = _default_tables()
    zero["NONDERIV_TRANS.tsv"] = b""
    raw = _raw_snapshot(tmp_path, tables=zero, root_name="zero-raw")
    with pytest.raises(SecBulkParsedSnapshotError, match="zero bytes"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "zero-parsed",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )

    header_only = {
        "SUBMISSION.tsv": _tsv(SUBMISSION_HEADERS, ()),
        "REPORTINGOWNER.tsv": _tsv(OWNER_HEADERS, ()),
        "NONDERIV_TRANS.tsv": _tsv(TRANS_HEADERS, ()),
    }
    raw, parsed, _ = _publish(
        tmp_path,
        tables=header_only,
        raw_root_name="empty-raw",
        parsed_root_name="empty-parsed",
    )
    loaded = load_sec_bulk_parsed_snapshot(
        parsed, raw_snapshot_directory=raw
    )
    assert loaded.rows == ()
    assert loaded.accessions == ()


@pytest.mark.parametrize(
    "bad_payload",
    [
        b"ACCESSION_NUMBER\tTRANS_SK\tTRANSACTIONSHARES\tTRANSACTIONPRICEPERSHARE\tNOTE\n\n",
        b"ACCESSION_NUMBER\tTRANS_SK\tTRANSACTIONSHARES\tTRANSACTIONPRICEPERSHARE\tNOTE\n"
        + ACCESSION_A.encode()
        + b"\t1\t2\t3\n",
        b"ACCESSION_NUMBER\tTRANS_SK\tTRANSACTIONSHARES\tTRANSACTIONPRICEPERSHARE\tNOTE\n"
        + ACCESSION_A.encode()
        + b'\t1\t2\t3\t"unterminated\n',
    ],
)
def test_blank_ragged_and_malformed_logical_records_refuse(tmp_path, bad_payload):
    tables = _default_tables()
    tables["NONDERIV_TRANS.tsv"] = bad_payload
    raw = _raw_snapshot(tmp_path, tables=tables)
    with pytest.raises(SecBulkParsedSnapshotError, match="ragged|dialect"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )


@pytest.mark.parametrize(
    "submission_rows, owner_rows, message",
    [
        (
            (
                (ACCESSION_A, "d", "d", "4", "1", "I", "S"),
                (ACCESSION_A, "d", "d", "4/A", "1", "I", "S"),
            ),
            ((ACCESSION_A, "1", "O", "1", "0"),),
            "duplicate accession",
        ),
        (
            ((ACCESSION_A, "d", "d", "4", "1", "I", "S"),),
            ((ACCESSION_B, "1", "O", "1", "0"),),
            "orphan accession",
        ),
        (
            (("１２３4567890-26-000001", "d", "d", "4", "1", "I", "S"),),
            (),
            "not canonical",
        ),
    ],
)
def test_accession_integrity_refuses_duplicate_orphan_and_unicode_digits(
    tmp_path, submission_rows, owner_rows, message
):
    tables = {
        "SUBMISSION.tsv": _tsv(SUBMISSION_HEADERS, submission_rows),
        "REPORTINGOWNER.tsv": _tsv(OWNER_HEADERS, owner_rows),
        "NONDERIV_TRANS.tsv": _tsv(TRANS_HEADERS, ()),
    }
    raw = _raw_snapshot(tmp_path, tables=tables)
    with pytest.raises(SecBulkParsedSnapshotError, match=message):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )


def test_forms_three_four_a_and_five_are_retained_without_classification(tmp_path):
    submissions = tuple(
        (
            accession,
            "2026-05-01",
            "2026-04-30",
            document_type,
            "0000123456",
            "Issuer",
            "SYN",
        )
        for accession, document_type in (
            (ACCESSION_A, "3"),
            (ACCESSION_B, "4/A"),
            (ACCESSION_C, "5"),
        )
    )
    tables = {
        "SUBMISSION.tsv": _tsv(SUBMISSION_HEADERS, submissions),
        "REPORTINGOWNER.tsv": _tsv(OWNER_HEADERS, ()),
        "NONDERIV_TRANS.tsv": _tsv(TRANS_HEADERS, ()),
    }
    raw, parsed, _ = _publish(tmp_path, tables=tables)
    loaded = load_sec_bulk_parsed_snapshot(
        parsed, raw_snapshot_directory=raw
    )
    assert [item.document_type for item in loaded.accessions] == ["3", "4/A", "5"]
    assert not any(
        key in row.to_payload()
        for row in loaded.rows
        for key in ("eligible", "classification", "canonical_event")
    )


def test_parser_profile_git_and_raw_provenance_all_change_parsed_identity(tmp_path):
    tables = _default_tables()
    archive = _archive(tables)
    raw_root = tmp_path / "raw"
    first_raw_identity = write_sec_bulk_snapshot(archive, _source(), raw_root)
    second_raw_identity = write_sec_bulk_snapshot(
        archive,
        _source(retrieved_at=RETRIEVED + timedelta(seconds=1)),
        raw_root,
    )
    first_raw = raw_root / first_raw_identity.snapshot_id
    second_raw = raw_root / second_raw_identity.snapshot_id
    ids = {
        build_sec_bulk_parsed_snapshot(
            first_raw,
            tmp_path / "parsed-a",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        ).snapshot_id,
        build_sec_bulk_parsed_snapshot(
            first_raw,
            tmp_path / "parsed-b",
            schema_profile=_profile(profile_id="synthetic-qc-profile-v2"),
            parser_git_commit=PARSER_COMMIT,
        ).snapshot_id,
        build_sec_bulk_parsed_snapshot(
            first_raw,
            tmp_path / "parsed-c",
            schema_profile=_profile(),
            parser_git_commit="c" * 40,
        ).snapshot_id,
        build_sec_bulk_parsed_snapshot(
            second_raw,
            tmp_path / "parsed-d",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        ).snapshot_id,
    }
    assert len(ids) == 4


def test_public_loader_requires_the_exact_committed_raw_snapshot(tmp_path):
    archive = _archive(_default_tables())
    raw_root = tmp_path / "raw"
    first_identity = write_sec_bulk_snapshot(archive, _source(), raw_root)
    second_identity = write_sec_bulk_snapshot(
        archive,
        _source(retrieved_at=RETRIEVED + timedelta(seconds=1)),
        raw_root,
    )
    first_raw = raw_root / first_identity.snapshot_id
    second_raw = raw_root / second_identity.snapshot_id
    parsed_root = tmp_path / "parsed"
    parsed_identity = build_sec_bulk_parsed_snapshot(
        first_raw,
        parsed_root,
        schema_profile=_profile(),
        parser_git_commit=PARSER_COMMIT,
    )
    parsed = parsed_root / parsed_identity.snapshot_id

    assert load_sec_bulk_parsed_snapshot(
        parsed, raw_snapshot_directory=first_raw
    ).identity == parsed_identity
    with pytest.raises(SecBulkParsedSnapshotError, match="verified raw snapshot"):
        load_sec_bulk_parsed_snapshot(
            parsed, raw_snapshot_directory=second_raw
        )


def test_unverified_or_missing_raw_commit_refuses_before_parsed_publication(tmp_path):
    raw = _raw_snapshot(tmp_path)
    (raw / "snapshot.commit.json").unlink()
    with pytest.raises(SecBulkParsedSnapshotError, match="raw SEC snapshot"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )
    assert not (tmp_path / "parsed").exists()


@pytest.mark.parametrize("artifact_name", ["rows.jsonl", "accessions.jsonl"])
def test_tampered_data_artifact_is_refused_by_commit_hash(tmp_path, artifact_name):
    raw, parsed, _ = _publish(tmp_path)
    path = parsed / artifact_name
    path.write_bytes(path.read_bytes() + b"{}\n")
    with pytest.raises(SecBulkParsedSnapshotError, match="member hash mismatch"):
        load_sec_bulk_parsed_snapshot(parsed, raw_snapshot_directory=raw)


def test_fully_rehashed_cross_linked_accession_index_still_refuses_semantically(
    tmp_path,
):
    tables = _default_tables()
    tables["SUBMISSION.tsv"] = _tsv(
        SUBMISSION_HEADERS,
        (
            (ACCESSION_A, "d", "d", "4", "1", "A", "A"),
            (ACCESSION_B, "d", "d", "4", "2", "B", "B"),
        ),
    )
    raw, parsed, _ = _publish(tmp_path, tables=tables)
    accessions_path = parsed / "accessions.jsonl"
    records = [json.loads(line) for line in accessions_path.read_bytes().splitlines()]
    records[0]["submission_row_id"], records[1]["submission_row_id"] = (
        records[1]["submission_row_id"],
        records[0]["submission_row_id"],
    )
    forged_accessions = b"".join(
        (canonical_json(record) + "\n").encode("utf-8") for record in records
    )
    accessions_path.write_bytes(forged_accessions)

    manifest_path = parsed / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = next(
        item for item in manifest["artifacts"] if item["name"] == "accessions.jsonl"
    )
    artifact["sha256"] = hash_bytes(forged_accessions)
    artifact["size_bytes"] = len(forged_accessions)
    manifest_path.write_bytes((canonical_json(manifest) + "\n").encode("utf-8"))
    forged = _readdress_parsed_snapshot(parsed)

    with pytest.raises(SecBulkParsedSnapshotError, match="accession index"):
        load_sec_bulk_parsed_snapshot(forged, raw_snapshot_directory=raw)


def _two_transaction_tables() -> dict[str, bytes]:
    tables = _default_tables()
    tables["NONDERIV_TRANS.tsv"] = _tsv(
        TRANS_HEADERS,
        (
            (ACCESSION_A, "0000007", "10", "20", "first"),
            (ACCESSION_A, "0000008", "11", "21", "second"),
        ),
    )
    return tables


def _forge_rows_artifact(parsed: Path, transform) -> Path:
    """Rewrite ``rows.jsonl`` and recompute every ordinary hash and identity.

    The per-table row-id lineage, artifact hash, manifest lineage hash,
    snapshot id, and commit marker are all rebuilt so that none of the
    content-addressed guards can be what refuses.  Only the loader's
    row-level semantic rebuild is left to detect the forgery.
    """

    rows_path = parsed / "rows.jsonl"
    records = transform(
        [json.loads(line) for line in rows_path.read_bytes().splitlines()]
    )
    forged = b"".join(
        (canonical_json(record) + "\n").encode("utf-8") for record in records
    )
    rows_path.write_bytes(forged)

    manifest_path = parsed / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = next(
        item for item in manifest["artifacts"] if item["name"] == "rows.jsonl"
    )
    artifact["sha256"] = hash_bytes(forged)
    artifact["size_bytes"] = len(forged)
    artifact["record_count"] = len(records)
    for table in manifest["tables"]:
        table_row_ids = [
            record["row_id"]
            for record in records
            if record["table_name"] == table["table_name"]
        ]
        table["row_count"] = len(table_row_ids)
        table["row_ids_hash"] = hash_payload(table_row_ids)
    manifest_path.write_bytes((canonical_json(manifest) + "\n").encode("utf-8"))
    return _readdress_parsed_snapshot(parsed)


def _transaction_rows(records):
    return [
        record for record in records if record["table_name"] == "NONDERIV_TRANS.tsv"
    ]


def _swap_row_ids(records):
    first, second = _transaction_rows(records)
    first["row_id"], second["row_id"] = second["row_id"], first["row_id"]
    return records


def _forge_schema_id(records):
    _transaction_rows(records)[0]["schema_id"] = "synthetic-trans-2026q1"
    return records


def _reverse_source_ordinals(records):
    others = [
        record for record in records if record["table_name"] != "NONDERIV_TRANS.tsv"
    ]
    return others + list(reversed(_transaction_rows(records)))


def _forge_accession_projection(records):
    _transaction_rows(records)[0]["accession_number"] = ACCESSION_B
    return records


@pytest.mark.parametrize(
    "transform, expected",
    [
        (_swap_row_ids, "row lineage identity is invalid"),
        (_forge_schema_id, "parsed row is invalid"),
        (_reverse_source_ordinals, "parsed row is invalid"),
        (_forge_accession_projection, "accession projection is invalid"),
    ],
)
def test_fully_rehashed_forged_row_artifact_still_refuses_semantically(
    tmp_path, transform, expected
):
    """The row artifact needs the same semantic defence as the accession index.

    Each forgery below rebuilds every hash, the manifest lineage, the snapshot
    id, and the commit marker, so a loader that trusted its own content
    addressing would accept all of them.
    """

    raw, parsed, _ = _publish(tmp_path, tables=_two_transaction_tables())
    forged = _forge_rows_artifact(parsed, transform)
    with pytest.raises(SecBulkParsedSnapshotError, match=expected):
        load_sec_bulk_parsed_snapshot(forged, raw_snapshot_directory=raw)


def test_malformed_unhashable_manifest_and_row_values_map_to_domain_error(tmp_path):
    first_raw, first, _ = _publish(
        tmp_path, parsed_root_name="parsed-manifest"
    )
    manifest_path = first / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["name"] = []
    manifest_path.write_bytes((canonical_json(manifest) + "\n").encode("utf-8"))
    malformed_manifest = _readdress_parsed_snapshot(first)
    with pytest.raises(SecBulkParsedSnapshotError, match="artifact identity"):
        load_sec_bulk_parsed_snapshot(
            malformed_manifest, raw_snapshot_directory=first_raw
        )

    second_raw, second, _ = _publish(
        tmp_path,
        raw_root_name="raw-row",
        parsed_root_name="parsed-row",
    )
    rows_path = second / "rows.jsonl"
    rows = [json.loads(line) for line in rows_path.read_bytes().splitlines()]
    rows[0]["table_name"] = []
    forged_rows = b"".join(
        (canonical_json(row) + "\n").encode("utf-8") for row in rows
    )
    rows_path.write_bytes(forged_rows)
    manifest_path = second / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows_identity = next(
        item for item in manifest["artifacts"] if item["name"] == "rows.jsonl"
    )
    rows_identity["sha256"] = hash_bytes(forged_rows)
    rows_identity["size_bytes"] = len(forged_rows)
    manifest_path.write_bytes((canonical_json(manifest) + "\n").encode("utf-8"))
    malformed_row = _readdress_parsed_snapshot(second)
    with pytest.raises(SecBulkParsedSnapshotError, match="parsed row"):
        load_sec_bulk_parsed_snapshot(
            malformed_row, raw_snapshot_directory=second_raw
        )


def test_loader_refuses_impossible_zero_byte_parsed_table_identity(tmp_path):
    raw, parsed, _ = _publish(tmp_path)
    manifest_path = parsed / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"][0]["raw_member_size_bytes"] = 0
    manifest_path.write_bytes((canonical_json(manifest) + "\n").encode("utf-8"))
    forged = _readdress_parsed_snapshot(parsed)
    with pytest.raises(SecBulkParsedSnapshotError, match="table identity is invalid"):
        load_sec_bulk_parsed_snapshot(forged, raw_snapshot_directory=raw)


def test_noncanonical_manifest_and_unexpected_files_refuse(tmp_path):
    raw, parsed, _ = _publish(tmp_path)
    manifest_path = parsed / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _rewrite_commit(parsed)
    with pytest.raises(SecBulkParsedSnapshotError, match="canonical JSON"):
        load_sec_bulk_parsed_snapshot(parsed, raw_snapshot_directory=raw)

    manifest_path.write_bytes((canonical_json(manifest) + "\n").encode("utf-8"))
    _rewrite_commit(parsed)
    (parsed / "unexpected.txt").write_text("foreign", encoding="utf-8")
    with pytest.raises(SecBulkParsedSnapshotError, match="unexpected files"):
        load_sec_bulk_parsed_snapshot(parsed, raw_snapshot_directory=raw)


def test_redirected_parsed_members_and_directories_refuse(tmp_path):
    raw_snapshot, parsed, _ = _publish(tmp_path)
    rows = parsed / "rows.jsonl"
    outside = tmp_path / "outside-rows"
    rows.replace(outside)
    _symlink_or_skip(rows, outside, is_directory=False)
    with pytest.raises(SecBulkParsedSnapshotError, match="regular immutable file"):
        load_sec_bulk_parsed_snapshot(
            parsed, raw_snapshot_directory=raw_snapshot
        )


def test_resource_caps_refuse_before_any_parsed_publication(monkeypatch, tmp_path):
    raw = _raw_snapshot(tmp_path)
    monkeypatch.setattr(parsed_module, "MAX_TOTAL_PARSED_INPUT_BYTES", 1)
    with pytest.raises(SecBulkParsedSnapshotError, match="total parser input"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed-input",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )
    assert not (tmp_path / "parsed-input").exists()

    monkeypatch.setattr(
        parsed_module, "MAX_TOTAL_PARSED_INPUT_BYTES", 256 * 1024 * 1024
    )
    monkeypatch.setattr(parsed_module, "MAX_FIELD_CHARACTERS", 2)
    with pytest.raises(SecBulkParsedSnapshotError, match="field exceeds"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed-field",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )
    assert not (tmp_path / "parsed-field").exists()

    monkeypatch.setattr(parsed_module, "MAX_FIELD_CHARACTERS", 64 * 1024)
    monkeypatch.setattr(parsed_module, "MAX_ROWS_ARTIFACT_BYTES", 1)
    with pytest.raises(SecBulkParsedSnapshotError, match="artifact-size"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed-output",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )
    assert not (tmp_path / "parsed-output").exists()


@pytest.mark.parametrize(
    "constant, limit, expected",
    [
        ("MAX_ROWS_PER_TABLE", 1, "per-table row limit"),
        ("MAX_TOTAL_ROWS", 2, "total row limit"),
    ],
)
def test_row_count_caps_refuse_before_any_parsed_publication(
    monkeypatch, tmp_path, constant, limit, expected
):
    """The row caps bound memory, so removing one must not stay silent."""

    raw = _raw_snapshot(tmp_path, tables=_two_transaction_tables())
    monkeypatch.setattr(parsed_module, constant, limit)
    with pytest.raises(SecBulkParsedSnapshotError, match=expected):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed-rows",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )
    assert not (tmp_path / "parsed-rows").exists()


def test_parsed_output_cannot_mutate_the_raw_snapshot_directory(tmp_path):
    raw = _raw_snapshot(tmp_path)
    before = {path.name: path.read_bytes() for path in raw.iterdir()}
    with pytest.raises(SecBulkParsedSnapshotError, match="raw snapshot"):
        build_sec_bulk_parsed_snapshot(
            raw,
            raw,
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )
    assert {path.name: path.read_bytes() for path in raw.iterdir()} == before


def test_concurrent_exact_writers_publish_one_valid_identity(tmp_path):
    raw = _raw_snapshot(tmp_path)
    parsed_root = tmp_path / "parsed"

    def publish():
        return build_sec_bulk_parsed_snapshot(
            raw,
            parsed_root,
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = tuple(executor.map(lambda _: publish(), range(8)))
    assert len({item.snapshot_id for item in results}) == 1
    target = parsed_root / results[0].snapshot_id
    assert load_sec_bulk_parsed_snapshot(
        target, raw_snapshot_directory=raw
    ).identity == results[0]


@pytest.mark.parametrize(
    "residue",
    [
        ("rows.jsonl",),
        ("rows.jsonl", "accessions.jsonl"),
        ("rows.jsonl", "accessions.jsonl", "manifest.json"),
        ("rows.jsonl", ".accessions.jsonl.hard-stop.tmp"),
    ],
)
def test_parsed_hard_restart_recovers_only_byte_exact_uncommitted_residue(
    tmp_path, residue
):
    raw = _raw_snapshot(tmp_path)
    identity, _, _, expected = _expected_parsed_publication(raw)
    parsed_root = tmp_path / "parsed"
    target = parsed_root / identity.snapshot_id
    target.mkdir(parents=True)
    for name in residue:
        expected_name = (
            "accessions.jsonl"
            if name == ".accessions.jsonl.hard-stop.tmp"
            else name
        )
        (target / name).write_bytes(expected[expected_name])
    with pytest.raises(SecBulkParsedSnapshotError, match="commit marker"):
        load_sec_bulk_parsed_snapshot(target, raw_snapshot_directory=raw)

    recovered = build_sec_bulk_parsed_snapshot(
        raw,
        parsed_root,
        schema_profile=_profile(),
        parser_git_commit=PARSER_COMMIT,
    )
    assert recovered == identity
    assert {path.name for path in target.iterdir()} == set(expected)
    assert load_sec_bulk_parsed_snapshot(
        target, raw_snapshot_directory=raw
    ).identity == identity


@pytest.mark.parametrize("bad_name", ["manifest.json", "foreign.bin"])
def test_parsed_hard_restart_preserves_whole_unverified_residue(
    tmp_path, bad_name
):
    raw = _raw_snapshot(tmp_path)
    identity, _, _, expected = _expected_parsed_publication(raw)
    parsed_root = tmp_path / "parsed"
    target = parsed_root / identity.snapshot_id
    target.mkdir(parents=True)
    (target / "rows.jsonl").write_bytes(expected["rows.jsonl"])
    (target / bad_name).write_bytes(b"unverified")
    before = {path.name: path.read_bytes() for path in target.iterdir()}

    with pytest.raises(SecBulkParsedSnapshotError, match="unverified files"):
        build_sec_bulk_parsed_snapshot(
            raw,
            parsed_root,
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )
    assert {path.name: path.read_bytes() for path in target.iterdir()} == before


def test_parsed_lock_acquisition_failure_maps_to_domain_error(monkeypatch, tmp_path):
    raw = _raw_snapshot(tmp_path)

    @contextmanager
    def fail_lock(_path):
        raise OSError("synthetic lock denial")
        yield

    monkeypatch.setattr(parsed_module, "exclusive_file_lock", fail_lock)
    with pytest.raises(SecBulkParsedSnapshotError, match="lock could not be acquired"):
        build_sec_bulk_parsed_snapshot(
            raw,
            tmp_path / "parsed",
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )


@pytest.mark.parametrize("fail_call", [1, 2, 3, 4])
@pytest.mark.parametrize("failure_phase", ["before", "after"])
def test_publication_failure_recovers_or_rolls_back_without_partial_commit(
    monkeypatch, tmp_path, fail_call, failure_phase
):
    raw = _raw_snapshot(tmp_path)
    parsed_root = tmp_path / "parsed"
    real_publish = parsed_module.publish_immutable_bytes
    calls = 0

    def fail_selected(path, data):
        nonlocal calls
        calls += 1
        if calls == fail_call and failure_phase == "before":
            raise OSError("synthetic publication failure")
        result = real_publish(path, data)
        if calls == fail_call and failure_phase == "after":
            raise OSError("synthetic post-link failure")
        return result

    monkeypatch.setattr(parsed_module, "publish_immutable_bytes", fail_selected)
    if fail_call == 4 and failure_phase == "after":
        identity = build_sec_bulk_parsed_snapshot(
            raw,
            parsed_root,
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )
        assert load_sec_bulk_parsed_snapshot(
            parsed_root / identity.snapshot_id,
            raw_snapshot_directory=raw,
        ).identity == identity
        return

    with pytest.raises(SecBulkParsedSnapshotError, match="publication"):
        build_sec_bulk_parsed_snapshot(
            raw,
            parsed_root,
            schema_profile=_profile(),
            parser_git_commit=PARSER_COMMIT,
        )
    targets = tuple(
        path
        for path in parsed_root.iterdir()
        if path.is_dir() and path.name.startswith("sec-insider-parsed-")
    )
    assert len(targets) == 1
    assert not any(targets[0].iterdir())

    monkeypatch.setattr(parsed_module, "publish_immutable_bytes", real_publish)
    identity = build_sec_bulk_parsed_snapshot(
        raw,
        parsed_root,
        schema_profile=_profile(),
        parser_git_commit=PARSER_COMMIT,
    )
    assert load_sec_bulk_parsed_snapshot(
        parsed_root / identity.snapshot_id,
        raw_snapshot_directory=raw,
    ).identity == identity


def test_parser_module_has_no_network_outcome_qc_or_execution_imports():
    source = Path(parsed_module.__file__).read_text(encoding="utf-8")
    tree = __import__("ast").parse(source)
    imported_roots = set()
    for node in __import__("ast").walk(tree):
        if isinstance(node, __import__("ast").Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, __import__("ast").ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots.isdisjoint(
        {
            "requests",
            "urllib",
            "httpx",
            "aiohttp",
            "backtest",
            "execution",
            "assistant",
            "risk",
            "streamlit",
            "AlgorithmImports",
        }
    )
