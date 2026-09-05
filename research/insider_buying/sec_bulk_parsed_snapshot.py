"""Offline explicit-schema parsing for a verified SEC insider raw snapshot.

This IB-1B boundary accepts only a committed IB-1A snapshot and a caller-
supplied, versioned schema profile.  The repository intentionally ships no
guessed SEC header registry: the governing strategy document names key fields
but is not an exhaustive historical data dictionary.  Every supported header
vector must therefore be frozen from separately audited source material before
use.

The parser preserves as-filed strings and source-row lineage.  It does not
download data, infer types, reconcile amendments, multiply owner and
transaction rows, classify purchases, aggregate lots, construct signals, or
interact with QuantConnect, a broker, or an application UI.

Publication requires a caller-controlled output root with no untrusted actor
concurrently replacing path components.  Cooperative writers are serialized
and pre-existing redirects are refused; adversarial filesystem-race resistance
is outside this boundary.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path

from data.hashing import canonical_json, hash_bytes, hash_payload
from ml.immutable_io import (
    ImmutableFileConflictError,
    exclusive_file_lock,
    publish_immutable_bytes,
)
from research.insider_buying.sec_bulk_snapshot import (
    ALLOWED_SEC_TABLES,
    REQUIRED_SEC_TABLES,
    SecBulkSnapshotError,
    load_sec_bulk_snapshot,
)


PARSED_SNAPSHOT_KIND = "sec-insider-parsed-quarter"
PARSED_SNAPSHOT_CONTRACT_VERSION = 1
SEC_TSV_PARSER_VERSION = "INSETF-IB1B-TSV-v1"

# The first implementation deliberately stays below IB-1A's multi-gigabyte
# expanded-archive allowance because publication currently builds canonical
# JSONL byte images in memory.  Raising these limits requires an independently
# reviewed streaming publisher rather than a constant-only change.
MAX_PARSED_TABLE_INPUT_BYTES = 256 * 1024 * 1024
MAX_TOTAL_PARSED_INPUT_BYTES = 256 * 1024 * 1024
MAX_HEADER_COLUMNS = 512
MAX_HEADER_NAME_CHARACTERS = 128
MAX_SCHEMA_VARIANTS = 1024
MAX_FIELD_CHARACTERS = 64 * 1024
MAX_ROWS_PER_TABLE = 2_000_000
MAX_TOTAL_ROWS = 5_000_000
MAX_TOTAL_FIELD_CHARACTERS = 256 * 1024 * 1024
MAX_ROWS_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_ACCESSIONS_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_PARSED_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_PARSED_COMMIT_BYTES = 32 * 1024

_ROWS_NAME = "rows.jsonl"
_ACCESSIONS_NAME = "accessions.jsonl"
_MANIFEST_NAME = "manifest.json"
_COMMIT_NAME = "snapshot.commit.json"
_LOCK_SUFFIX = ".publication.lock"
_ARTIFACT_NAMES = (_ROWS_NAME, _ACCESSIONS_NAME)
_PUBLICATION_NAMES = (_ROWS_NAME, _ACCESSIONS_NAME, _MANIFEST_NAME)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_HEADER_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_RAW_SNAPSHOT_ID_RE = re.compile(
    r"^sec-insider-bulk-[0-9]{4}q[1-4]-[0-9a-f]{16}$"
)
_PARSED_SNAPSHOT_ID_RE = re.compile(
    r"^sec-insider-parsed-[0-9]{4}q[1-4]-[0-9a-f]{16}$"
)

_REQUIRED_HEADERS_BY_TABLE = {
    "SUBMISSION.tsv": frozenset(
        {
            "ACCESSION_NUMBER",
            "FILING_DATE",
            "PERIOD_OF_REPORT",
            "DOCUMENT_TYPE",
            "ISSUERCIK",
            "ISSUERNAME",
            "ISSUERTRADINGSYMBOL",
        }
    ),
    "REPORTINGOWNER.tsv": frozenset({"ACCESSION_NUMBER", "RPTOWNERCIK"}),
}

_VARIANT_KEYS = {
    "schema_id",
    "table_name",
    "headers",
    "source_row_key_headers",
    "valid_from_year",
    "valid_from_quarter",
    "valid_through_year",
    "valid_through_quarter",
}
_PROFILE_KEYS = {"profile_id", "variants"}
_ROW_KEYS = {
    "table_name",
    "schema_id",
    "source_record_ordinal",
    "accession_number",
    "values",
    "source_row_key",
    "row_id",
}
_TABLE_ROWS_KEYS = {"table_name", "row_ids"}
_ACCESSION_KEYS = {
    "accession_number",
    "document_type",
    "submission_row_id",
    "table_rows",
}
_TABLE_IDENTITY_KEYS = {
    "table_name",
    "schema_id",
    "headers",
    "source_row_key_headers",
    "header_hash",
    "raw_member_sha256",
    "raw_member_size_bytes",
    "row_count",
    "row_ids_hash",
}
_ARTIFACT_IDENTITY_KEYS = {"name", "sha256", "size_bytes", "record_count"}
_MANIFEST_KEYS = {
    "kind",
    "parsed_contract_version",
    "parser_version",
    "parser_git_commit",
    "year",
    "quarter",
    "raw_snapshot_id",
    "raw_lineage_hash",
    "raw_archive_sha256",
    "raw_manifest_sha256",
    "schema_profile",
    "schema_profile_hash",
    "absent_tables",
    "tables",
    "artifacts",
    "lineage_hash",
    "snapshot_id",
}


class SecBulkParsedSnapshotError(ValueError):
    """The parsed SEC snapshot contract failed closed."""


class _ParsedPublicationLock:
    """Translate only lock entry/exit failures into the domain contract."""

    def __init__(self, lock_path: Path) -> None:
        self._manager = exclusive_file_lock(lock_path)

    def __enter__(self):
        try:
            return self._manager.__enter__()
        except OSError as exc:
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed snapshot publication lock could not be acquired"
            ) from exc

    def __exit__(self, exc_type, exc, traceback):
        try:
            return self._manager.__exit__(exc_type, exc, traceback)
        except OSError as lock_exc:
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed snapshot publication lock could not be released"
            ) from lock_exc


def _period_index(year: object, quarter: object, *, label: str) -> int:
    if type(year) is not int or not 2006 <= year <= 9999:
        raise SecBulkParsedSnapshotError(
            f"REFUSED: {label} year must be an exact integer from 2006"
        )
    if type(quarter) is not int or quarter not in {1, 2, 3, 4}:
        raise SecBulkParsedSnapshotError(
            f"REFUSED: {label} quarter must be an exact integer from 1 through 4"
        )
    return year * 4 + quarter - 1


@dataclass(frozen=True)
class SecTsvSchemaVariant:
    """One exact ordered header vector for an inclusive quarter range."""

    schema_id: str
    table_name: str
    headers: tuple[str, ...]
    source_row_key_headers: tuple[str, ...]
    valid_from_year: int
    valid_from_quarter: int
    valid_through_year: int
    valid_through_quarter: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schema_id, str)
            or _IDENTIFIER_RE.fullmatch(self.schema_id) is None
        ):
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema ID must be a canonical bounded identifier"
            )
        if self.table_name not in ALLOWED_SEC_TABLES:
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema variant names an unsupported SEC table"
            )
        if type(self.headers) is not tuple or not self.headers:
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema headers must be a non-empty immutable tuple"
            )
        if len(self.headers) > MAX_HEADER_COLUMNS:
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema header exceeds the column-count limit"
            )
        if any(
            not isinstance(header, str)
            or len(header) > MAX_HEADER_NAME_CHARACTERS
            or _HEADER_RE.fullmatch(header) is None
            for header in self.headers
        ):
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema headers must be canonical uppercase ASCII names"
            )
        if len(self.headers) != len(set(self.headers)) or len(self.headers) != len(
            {header.casefold() for header in self.headers}
        ):
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema headers must be unique without case collisions"
            )
        required_headers = _REQUIRED_HEADERS_BY_TABLE.get(
            self.table_name, frozenset({"ACCESSION_NUMBER"})
        )
        if not required_headers.issubset(self.headers):
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema variant omits a required as-filed key column"
            )
        if type(self.source_row_key_headers) is not tuple or any(
            not isinstance(header, str) or header not in self.headers
            for header in self.source_row_key_headers
        ):
            raise SecBulkParsedSnapshotError(
                "REFUSED: source-row key headers must be an immutable schema subset"
            )
        if (
            len(self.source_row_key_headers)
            != len(set(self.source_row_key_headers))
            or "ACCESSION_NUMBER" in self.source_row_key_headers
        ):
            raise SecBulkParsedSnapshotError(
                "REFUSED: source-row key headers must be unique and accession-relative"
            )
        if self.table_name in {"NONDERIV_TRANS.tsv", "DERIV_TRANS.tsv"} and not (
            self.source_row_key_headers
        ):
            raise SecBulkParsedSnapshotError(
                "REFUSED: transaction schemas require a caller-declared source-row key"
            )
        start = _period_index(
            self.valid_from_year,
            self.valid_from_quarter,
            label="schema start",
        )
        end = _period_index(
            self.valid_through_year,
            self.valid_through_quarter,
            label="schema end",
        )
        if start > end:
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema quarter range is reversed"
            )

    @property
    def start_period(self) -> int:
        return self.valid_from_year * 4 + self.valid_from_quarter - 1

    @property
    def end_period(self) -> int:
        return self.valid_through_year * 4 + self.valid_through_quarter - 1

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_id": self.schema_id,
            "table_name": self.table_name,
            "headers": list(self.headers),
            "source_row_key_headers": list(self.source_row_key_headers),
            "valid_from_year": self.valid_from_year,
            "valid_from_quarter": self.valid_from_quarter,
            "valid_through_year": self.valid_through_year,
            "valid_through_quarter": self.valid_through_quarter,
        }

    @classmethod
    def from_payload(cls, payload: object) -> "SecTsvSchemaVariant":
        if not isinstance(payload, dict) or set(payload) != _VARIANT_KEYS:
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema variant payload fields are not exact"
            )
        headers = payload.get("headers")
        source_row_key_headers = payload.get("source_row_key_headers")
        if not isinstance(headers, list) or not isinstance(
            source_row_key_headers, list
        ):
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema variant headers are malformed"
            )
        return cls(
            schema_id=payload.get("schema_id"),
            table_name=payload.get("table_name"),
            headers=tuple(headers),
            source_row_key_headers=tuple(source_row_key_headers),
            valid_from_year=payload.get("valid_from_year"),
            valid_from_quarter=payload.get("valid_from_quarter"),
            valid_through_year=payload.get("valid_through_year"),
            valid_through_quarter=payload.get("valid_through_quarter"),
        )


@dataclass(frozen=True)
class SecTsvSchemaProfile:
    """Caller-supplied registry of separately audited, non-overlapping variants."""

    profile_id: str
    variants: tuple[SecTsvSchemaVariant, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or _IDENTIFIER_RE.fullmatch(self.profile_id) is None
        ):
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema profile ID must be a canonical bounded identifier"
            )
        if (
            type(self.variants) is not tuple
            or not self.variants
            or len(self.variants) > MAX_SCHEMA_VARIANTS
            or any(type(item) is not SecTsvSchemaVariant for item in self.variants)
        ):
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema profile variants must be an immutable tuple"
            )
        if len({item.schema_id for item in self.variants}) != len(self.variants):
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema profile IDs must be globally unique"
            )
        table_order = {name: index for index, name in enumerate(ALLOWED_SEC_TABLES)}
        canonical = tuple(
            sorted(
                self.variants,
                key=lambda item: (
                    table_order[item.table_name],
                    item.start_period,
                    item.end_period,
                    item.schema_id,
                ),
            )
        )
        if self.variants != canonical:
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema profile variants are not in canonical order"
            )
        by_table: dict[str, list[SecTsvSchemaVariant]] = {}
        for item in self.variants:
            by_table.setdefault(item.table_name, []).append(item)
        if not set(REQUIRED_SEC_TABLES).issubset(by_table):
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema profile omits a required core table"
            )
        for table_variants in by_table.values():
            for previous, current in zip(table_variants, table_variants[1:]):
                if current.start_period <= previous.end_period:
                    raise SecBulkParsedSnapshotError(
                        "REFUSED: schema profile quarter ranges overlap"
                    )

    def variant_for(
        self, table_name: str, year: int, quarter: int
    ) -> SecTsvSchemaVariant:
        period = _period_index(year, quarter, label="raw snapshot")
        matches = tuple(
            item
            for item in self.variants
            if item.table_name == table_name
            and item.start_period <= period <= item.end_period
        )
        if len(matches) != 1:
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema profile has no exact quarter variant for a present table"
            )
        return matches[0]

    def to_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "variants": [item.to_payload() for item in self.variants],
        }

    @classmethod
    def from_payload(cls, payload: object) -> "SecTsvSchemaProfile":
        if not isinstance(payload, dict) or set(payload) != _PROFILE_KEYS:
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema profile payload fields are not exact"
            )
        variants = payload.get("variants")
        if not isinstance(variants, list) or len(variants) > MAX_SCHEMA_VARIANTS:
            raise SecBulkParsedSnapshotError(
                "REFUSED: schema profile variants are malformed"
            )
        return cls(
            profile_id=payload.get("profile_id"),
            variants=tuple(SecTsvSchemaVariant.from_payload(item) for item in variants),
        )


@dataclass(frozen=True)
class ParsedSecBulkRow:
    table_name: str
    schema_id: str
    source_record_ordinal: int
    accession_number: str
    values: tuple[str, ...]
    source_row_key: tuple[str, ...]
    row_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "table_name": self.table_name,
            "schema_id": self.schema_id,
            "source_record_ordinal": self.source_record_ordinal,
            "accession_number": self.accession_number,
            "values": list(self.values),
            "source_row_key": list(self.source_row_key),
            "row_id": self.row_id,
        }


@dataclass(frozen=True)
class ParsedSecBulkAccession:
    accession_number: str
    document_type: str
    submission_row_id: str
    table_rows: tuple[tuple[str, tuple[str, ...]], ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "document_type": self.document_type,
            "submission_row_id": self.submission_row_id,
            "table_rows": [
                {"table_name": table_name, "row_ids": list(row_ids)}
                for table_name, row_ids in self.table_rows
            ],
        }


@dataclass(frozen=True)
class ParsedSecBulkTableIdentity:
    table_name: str
    schema_id: str
    headers: tuple[str, ...]
    source_row_key_headers: tuple[str, ...]
    header_hash: str
    raw_member_sha256: str
    raw_member_size_bytes: int
    row_count: int
    row_ids_hash: str

    def to_payload(self) -> dict[str, object]:
        return {
            "table_name": self.table_name,
            "schema_id": self.schema_id,
            "headers": list(self.headers),
            "source_row_key_headers": list(self.source_row_key_headers),
            "header_hash": self.header_hash,
            "raw_member_sha256": self.raw_member_sha256,
            "raw_member_size_bytes": self.raw_member_size_bytes,
            "row_count": self.row_count,
            "row_ids_hash": self.row_ids_hash,
        }


@dataclass(frozen=True)
class ParsedSecBulkArtifactIdentity:
    name: str
    sha256: str
    size_bytes: int
    record_count: int

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "record_count": self.record_count,
        }


@dataclass(frozen=True)
class SecBulkParsedSnapshotIdentity:
    year: int
    quarter: int
    parser_git_commit: str
    raw_snapshot_id: str
    raw_lineage_hash: str
    raw_archive_sha256: str
    raw_manifest_sha256: str
    schema_profile: SecTsvSchemaProfile
    schema_profile_hash: str
    absent_tables: tuple[str, ...]
    tables: tuple[ParsedSecBulkTableIdentity, ...]
    artifacts: tuple[ParsedSecBulkArtifactIdentity, ...]
    lineage_hash: str
    snapshot_id: str

    def lineage_payload(self) -> dict[str, object]:
        return {
            "kind": PARSED_SNAPSHOT_KIND,
            "parsed_contract_version": PARSED_SNAPSHOT_CONTRACT_VERSION,
            "parser_version": SEC_TSV_PARSER_VERSION,
            "parser_git_commit": self.parser_git_commit,
            "year": self.year,
            "quarter": self.quarter,
            "raw_snapshot_id": self.raw_snapshot_id,
            "raw_lineage_hash": self.raw_lineage_hash,
            "raw_archive_sha256": self.raw_archive_sha256,
            "raw_manifest_sha256": self.raw_manifest_sha256,
            "schema_profile": self.schema_profile.to_payload(),
            "schema_profile_hash": self.schema_profile_hash,
            "absent_tables": list(self.absent_tables),
            "tables": [item.to_payload() for item in self.tables],
            "artifacts": [item.to_payload() for item in self.artifacts],
        }

    def to_payload(self) -> dict[str, object]:
        return {
            **self.lineage_payload(),
            "lineage_hash": self.lineage_hash,
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True)
class LoadedSecBulkParsedSnapshot:
    identity: SecBulkParsedSnapshotIdentity
    rows: tuple[ParsedSecBulkRow, ...]
    accessions: tuple[ParsedSecBulkAccession, ...]


def _canonical_json_bytes(payload: object) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _append_json_line(
    target: bytearray, payload: object, *, max_bytes: int, label: str
) -> None:
    try:
        encoded = _canonical_json_bytes(payload)
    except (TypeError, UnicodeError, ValueError) as exc:
        raise SecBulkParsedSnapshotError(
            f"REFUSED: {label} cannot be represented as canonical JSON"
        ) from exc
    if len(target) + len(encoded) > max_bytes:
        raise SecBulkParsedSnapshotError(
            f"REFUSED: {label} exceeds its canonical artifact-size limit"
        )
    target.extend(encoded)


def _source_row_id(
    *,
    raw_snapshot_id: str,
    raw_lineage_hash: str,
    raw_archive_sha256: str,
    table_name: str,
    raw_member_sha256: str,
    source_record_ordinal: int,
    values: tuple[str, ...],
    source_row_key: tuple[str, ...],
) -> str:
    return hash_payload(
        {
            "kind": "sec-insider-as-filed-source-row",
            "raw_snapshot_id": raw_snapshot_id,
            "raw_lineage_hash": raw_lineage_hash,
            "raw_archive_sha256": raw_archive_sha256,
            "table_name": table_name,
            "raw_member_sha256": raw_member_sha256,
            "source_record_ordinal": source_record_ordinal,
            "values": list(values),
            "source_row_key": list(source_row_key),
        }
    )


def _parse_table(
    *,
    member_bytes: bytes,
    table_name: str,
    raw_member_sha256: str,
    raw_snapshot_id: str,
    raw_lineage_hash: str,
    raw_archive_sha256: str,
    year: int,
    quarter: int,
    schema_profile: SecTsvSchemaProfile,
) -> tuple[SecTsvSchemaVariant, tuple[ParsedSecBulkRow, ...], int]:
    if not member_bytes:
        raise SecBulkParsedSnapshotError(
            "REFUSED: a present SEC table member is zero bytes"
        )
    if len(member_bytes) > MAX_PARSED_TABLE_INPUT_BYTES:
        raise SecBulkParsedSnapshotError(
            "REFUSED: SEC table exceeds the bounded parser input limit"
        )
    try:
        text = member_bytes.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise SecBulkParsedSnapshotError(
            "REFUSED: SEC table is not strict UTF-8 text"
        ) from exc
    reader = csv.reader(
        io.StringIO(text, newline=""),
        delimiter="\t",
        quotechar='"',
        doublequote=True,
        escapechar=None,
        skipinitialspace=False,
        strict=True,
    )
    try:
        observed_header = next(reader)
    except StopIteration as exc:
        raise SecBulkParsedSnapshotError(
            "REFUSED: SEC table has no header record"
        ) from exc
    except csv.Error as exc:
        raise SecBulkParsedSnapshotError(
            "REFUSED: SEC table header violates the frozen TSV dialect"
        ) from exc

    schema = schema_profile.variant_for(table_name, year, quarter)
    if tuple(observed_header) != schema.headers:
        raise SecBulkParsedSnapshotError(
            "REFUSED: SEC table header does not match its exact schema variant"
        )

    accession_index = schema.headers.index("ACCESSION_NUMBER")
    source_row_key_indexes = tuple(
        schema.headers.index(header) for header in schema.source_row_key_headers
    )
    observed_source_row_keys: set[tuple[str, tuple[str, ...]]] = set()
    rows: list[ParsedSecBulkRow] = []
    field_characters = sum(len(value) for value in observed_header)
    try:
        for source_record_ordinal, values in enumerate(reader, start=1):
            if source_record_ordinal > MAX_ROWS_PER_TABLE:
                raise SecBulkParsedSnapshotError(
                    "REFUSED: SEC table exceeds the per-table row limit"
                )
            if len(values) != len(schema.headers):
                raise SecBulkParsedSnapshotError(
                    "REFUSED: SEC table contains a blank or ragged logical record"
                )
            if any(len(value) > MAX_FIELD_CHARACTERS for value in values):
                raise SecBulkParsedSnapshotError(
                    "REFUSED: SEC table field exceeds the character limit"
                )
            field_characters += sum(len(value) for value in values)
            if field_characters > MAX_TOTAL_FIELD_CHARACTERS:
                raise SecBulkParsedSnapshotError(
                    "REFUSED: SEC table fields exceed the character budget"
                )
            accession_number = values[accession_index]
            if _ACCESSION_RE.fullmatch(accession_number) is None:
                raise SecBulkParsedSnapshotError(
                    "REFUSED: SEC table accession number is not canonical"
                )
            source_row_key = tuple(values[index] for index in source_row_key_indexes)
            if source_row_key and any(not value.strip() for value in source_row_key):
                raise SecBulkParsedSnapshotError(
                    "REFUSED: SEC table source-row key is blank"
                )
            accession_relative_key = (accession_number, source_row_key)
            if source_row_key and accession_relative_key in observed_source_row_keys:
                raise SecBulkParsedSnapshotError(
                    "REFUSED: SEC table contains a duplicate source-row key"
                )
            if source_row_key:
                observed_source_row_keys.add(accession_relative_key)
            rows.append(
                ParsedSecBulkRow(
                    table_name=table_name,
                    schema_id=schema.schema_id,
                    source_record_ordinal=source_record_ordinal,
                    accession_number=accession_number,
                    values=tuple(values),
                    source_row_key=source_row_key,
                    row_id=_source_row_id(
                        raw_snapshot_id=raw_snapshot_id,
                        raw_lineage_hash=raw_lineage_hash,
                        raw_archive_sha256=raw_archive_sha256,
                        table_name=table_name,
                        raw_member_sha256=raw_member_sha256,
                        source_record_ordinal=source_record_ordinal,
                        values=tuple(values),
                        source_row_key=source_row_key,
                    ),
                )
            )
    except csv.Error as exc:
        raise SecBulkParsedSnapshotError(
            "REFUSED: SEC table violates the frozen TSV dialect"
        ) from exc
    return schema, tuple(rows), field_characters


def _build_accessions(
    rows: tuple[ParsedSecBulkRow, ...],
    tables: tuple[ParsedSecBulkTableIdentity, ...],
) -> tuple[ParsedSecBulkAccession, ...]:
    present_tables = tuple(item.table_name for item in tables)
    table_by_name = {item.table_name: item for item in tables}
    submission_table = table_by_name["SUBMISSION.tsv"]
    document_type_index = submission_table.headers.index("DOCUMENT_TYPE")
    row_ids_by_accession: dict[str, dict[str, list[str]]] = {}
    submission_by_accession: dict[str, ParsedSecBulkRow] = {}

    for row in rows:
        by_table = row_ids_by_accession.setdefault(
            row.accession_number,
            {table_name: [] for table_name in present_tables},
        )
        by_table[row.table_name].append(row.row_id)
        if row.table_name == "SUBMISSION.tsv":
            if row.accession_number in submission_by_accession:
                raise SecBulkParsedSnapshotError(
                    "REFUSED: SUBMISSION contains a duplicate accession"
                )
            submission_by_accession[row.accession_number] = row

    orphans = sorted(set(row_ids_by_accession) - set(submission_by_accession))
    if orphans:
        raise SecBulkParsedSnapshotError(
            "REFUSED: a child SEC table contains an orphan accession"
        )

    accessions: list[ParsedSecBulkAccession] = []
    for accession_number in sorted(submission_by_accession):
        submission = submission_by_accession[accession_number]
        table_rows = row_ids_by_accession[accession_number]
        accessions.append(
            ParsedSecBulkAccession(
                accession_number=accession_number,
                document_type=submission.values[document_type_index],
                submission_row_id=submission.row_id,
                table_rows=tuple(
                    (table_name, tuple(table_rows[table_name]))
                    for table_name in present_tables
                ),
            )
        )
    return tuple(accessions)


def _artifact_identity(
    name: str, raw: bytes, *, record_count: int
) -> ParsedSecBulkArtifactIdentity:
    return ParsedSecBulkArtifactIdentity(
        name=name,
        sha256=hash_bytes(raw),
        size_bytes=len(raw),
        record_count=record_count,
    )


def _assemble_parsed_snapshot(
    raw_snapshot_directory: str | Path,
    *,
    schema_profile: SecTsvSchemaProfile,
    parser_git_commit: str,
) -> tuple[
    SecBulkParsedSnapshotIdentity,
    tuple[ParsedSecBulkRow, ...],
    tuple[ParsedSecBulkAccession, ...],
    bytes,
    bytes,
]:
    if type(schema_profile) is not SecTsvSchemaProfile:
        raise SecBulkParsedSnapshotError(
            "REFUSED: an explicit immutable schema profile is required"
        )
    if (
        not isinstance(parser_git_commit, str)
        or _GIT_COMMIT_RE.fullmatch(parser_git_commit) is None
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parser Git commit must be a full lowercase SHA-1"
        )
    try:
        loaded_raw = load_sec_bulk_snapshot(raw_snapshot_directory)
    except SecBulkSnapshotError as exc:
        raise SecBulkParsedSnapshotError(
            "REFUSED: raw SEC snapshot failed committed integrity validation"
        ) from exc

    raw_identity = loaded_raw.identity
    members_by_name = {item.name: item for item in raw_identity.members}
    if sum(item.size_bytes for item in raw_identity.members) > (
        MAX_TOTAL_PARSED_INPUT_BYTES
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: raw SEC tables exceed the bounded total parser input limit"
        )
    rows: list[ParsedSecBulkRow] = []
    table_identities: list[ParsedSecBulkTableIdentity] = []
    total_field_characters = 0
    try:
        with zipfile.ZipFile(io.BytesIO(loaded_raw.archive_bytes), "r") as archive:
            for member in raw_identity.members:
                if member.size_bytes > MAX_PARSED_TABLE_INPUT_BYTES:
                    raise SecBulkParsedSnapshotError(
                        "REFUSED: SEC table exceeds the bounded parser input limit"
                    )
                member_bytes = archive.read(member.name)
                if (
                    len(member_bytes) != member.size_bytes
                    or hash_bytes(member_bytes) != member.sha256
                ):
                    raise SecBulkParsedSnapshotError(
                        "REFUSED: extracted SEC table disagrees with raw lineage"
                    )
                schema, table_rows, table_field_characters = _parse_table(
                    member_bytes=member_bytes,
                    table_name=member.name,
                    raw_member_sha256=member.sha256,
                    raw_snapshot_id=raw_identity.snapshot_id,
                    raw_lineage_hash=raw_identity.lineage_hash,
                    raw_archive_sha256=raw_identity.archive_sha256,
                    year=raw_identity.year,
                    quarter=raw_identity.quarter,
                    schema_profile=schema_profile,
                )
                rows.extend(table_rows)
                if len(rows) > MAX_TOTAL_ROWS:
                    raise SecBulkParsedSnapshotError(
                        "REFUSED: parsed snapshot exceeds the total row limit"
                    )
                total_field_characters += table_field_characters
                if total_field_characters > MAX_TOTAL_FIELD_CHARACTERS:
                    raise SecBulkParsedSnapshotError(
                        "REFUSED: parsed snapshot exceeds the total field budget"
                    )
                table_identities.append(
                    ParsedSecBulkTableIdentity(
                        table_name=member.name,
                        schema_id=schema.schema_id,
                        headers=schema.headers,
                        source_row_key_headers=schema.source_row_key_headers,
                        header_hash=hash_payload(list(schema.headers)),
                        raw_member_sha256=member.sha256,
                        raw_member_size_bytes=member.size_bytes,
                        row_count=len(table_rows),
                        row_ids_hash=hash_payload(
                            [item.row_id for item in table_rows]
                        ),
                    )
                )
    except SecBulkParsedSnapshotError:
        raise
    except (zipfile.BadZipFile, KeyError, RuntimeError, OSError) as exc:
        raise SecBulkParsedSnapshotError(
            "REFUSED: verified raw archive could not be parsed"
        ) from exc

    # The raw loader already guarantees the member inventory.  This assertion
    # prevents a future refactor from silently dropping a verified member.
    if set(members_by_name) != {item.table_name for item in table_identities}:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed table inventory disagrees with raw lineage"
        )

    frozen_rows = tuple(rows)
    frozen_tables = tuple(table_identities)
    accessions = _build_accessions(frozen_rows, frozen_tables)

    rows_buffer = bytearray()
    for row in frozen_rows:
        _append_json_line(
            rows_buffer,
            row.to_payload(),
            max_bytes=MAX_ROWS_ARTIFACT_BYTES,
            label="rows artifact",
        )
    accessions_buffer = bytearray()
    for accession in accessions:
        _append_json_line(
            accessions_buffer,
            accession.to_payload(),
            max_bytes=MAX_ACCESSIONS_ARTIFACT_BYTES,
            label="accessions artifact",
        )
    rows_bytes = bytes(rows_buffer)
    accessions_bytes = bytes(accessions_buffer)
    artifacts = (
        _artifact_identity(_ROWS_NAME, rows_bytes, record_count=len(frozen_rows)),
        _artifact_identity(
            _ACCESSIONS_NAME,
            accessions_bytes,
            record_count=len(accessions),
        ),
    )
    absent_tables = tuple(
        name for name in ALLOWED_SEC_TABLES if name not in members_by_name
    )
    raw_manifest_bytes = _canonical_json_bytes(raw_identity.to_payload())
    profile_hash = hash_payload(schema_profile.to_payload())
    provisional = SecBulkParsedSnapshotIdentity(
        year=raw_identity.year,
        quarter=raw_identity.quarter,
        parser_git_commit=parser_git_commit,
        raw_snapshot_id=raw_identity.snapshot_id,
        raw_lineage_hash=raw_identity.lineage_hash,
        raw_archive_sha256=raw_identity.archive_sha256,
        raw_manifest_sha256=hash_bytes(raw_manifest_bytes),
        schema_profile=schema_profile,
        schema_profile_hash=profile_hash,
        absent_tables=absent_tables,
        tables=frozen_tables,
        artifacts=artifacts,
        lineage_hash="",
        snapshot_id="",
    )
    lineage_hash = hash_payload(provisional.lineage_payload())
    identity = SecBulkParsedSnapshotIdentity(
        **{
            **provisional.__dict__,
            "lineage_hash": lineage_hash,
            "snapshot_id": (
                f"sec-insider-parsed-{raw_identity.year:04d}q"
                f"{raw_identity.quarter}-{lineage_hash[:16]}"
            ),
        }
    )
    return identity, frozen_rows, accessions, rows_bytes, accessions_bytes


def _status_is_redirect(status: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(status, "st_file_attributes", 0)
    return stat.S_ISLNK(status.st_mode) or bool(
        reparse_flag and file_attributes & reparse_flag
    )


def _require_regular_directory(
    path: Path, *, label: str, missing_ok: bool = False
) -> bool:
    try:
        status = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return False
        raise SecBulkParsedSnapshotError(f"REFUSED: {label} is missing") from None
    except OSError as exc:
        raise SecBulkParsedSnapshotError(f"REFUSED: {label} is unreadable") from exc
    if _status_is_redirect(status) or not stat.S_ISDIR(status.st_mode):
        raise SecBulkParsedSnapshotError(
            f"REFUSED: {label} must be a non-redirected directory"
        )
    return True


def _same_file_identity(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino


def _same_file_version(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        _same_file_identity(first, second)
        and first.st_size == second.st_size
        and first.st_mtime_ns == second.st_mtime_ns
    )


def _read_regular_bytes(
    path: Path,
    *,
    label: str,
    max_bytes: int,
    require_single_link: bool = False,
) -> bytes:
    try:
        before = path.lstat()
        if (
            _status_is_redirect(before)
            or not stat.S_ISREG(before.st_mode)
            or (require_single_link and before.st_nlink != 1)
        ):
            raise SecBulkParsedSnapshotError(
                f"REFUSED: {label} must be a regular immutable file"
            )
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                _status_is_redirect(opened)
                or not stat.S_ISREG(opened.st_mode)
                or not _same_file_identity(before, opened)
                or (require_single_link and opened.st_nlink != 1)
            ):
                raise SecBulkParsedSnapshotError(
                    f"REFUSED: {label} changed while it was opened"
                )
            if opened.st_size > max_bytes:
                raise SecBulkParsedSnapshotError(
                    f"REFUSED: {label} exceeds its byte-size limit"
                )
            raw = handle.read(max_bytes + 1)
            after_read = os.fstat(handle.fileno())
        after_path = path.lstat()
        if (
            not _same_file_version(opened, after_read)
            or not _same_file_version(after_read, after_path)
            or (
                require_single_link
                and (after_read.st_nlink != 1 or after_path.st_nlink != 1)
            )
        ):
            raise SecBulkParsedSnapshotError(
                f"REFUSED: {label} changed while it was read"
            )
        if len(raw) != after_read.st_size:
            raise SecBulkParsedSnapshotError(
                f"REFUSED: {label} was not read as one complete byte image"
            )
        return raw
    except SecBulkParsedSnapshotError:
        raise
    except OSError as exc:
        raise SecBulkParsedSnapshotError(
            f"REFUSED: {label} is missing or unreadable"
        ) from exc


def _canonical_object(raw: bytes, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
        canonical = _canonical_json_bytes(value) if isinstance(value, dict) else None
    except (TypeError, UnicodeError, ValueError) as exc:
        raise SecBulkParsedSnapshotError(
            f"REFUSED: {label} is missing or invalid"
        ) from exc
    if not isinstance(value, dict) or raw != canonical:
        raise SecBulkParsedSnapshotError(
            f"REFUSED: {label} is not canonical JSON"
        )
    return value


def _read_canonical_object(
    path: Path,
    *,
    label: str,
    max_bytes: int,
    require_single_link: bool = False,
) -> dict[str, object]:
    return _canonical_object(
        _read_regular_bytes(
            path,
            label=label,
            max_bytes=max_bytes,
            require_single_link=require_single_link,
        ),
        label=label,
    )


def _prepare_output_root(output_root: str | Path) -> Path:
    try:
        root = Path(output_root)
        existed = _require_regular_directory(
            root, label="parsed snapshot output root", missing_ok=True
        )
        if not existed:
            root.mkdir(parents=True, exist_ok=True)
        _require_regular_directory(root, label="parsed snapshot output root")
        canonical_root = root.resolve(strict=True)
        _require_regular_directory(
            canonical_root, label="parsed snapshot output root"
        )
        return canonical_root
    except SecBulkParsedSnapshotError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot output root is invalid or unavailable"
        ) from exc


def _require_regular_lock_slot(lock_path: Path) -> None:
    try:
        status = lock_path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot publication lock is unreadable"
        ) from exc
    if _status_is_redirect(status) or not stat.S_ISREG(status.st_mode):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot publication lock must be a regular file"
        )


def _verify_publication_residue(
    target: Path,
    expected_files: tuple[tuple[str, bytes], ...],
    *,
    include_final_files: bool,
) -> tuple[Path, ...]:
    """Classify residue before cleanup without weakening committed evidence.

    During an uncommitted rollback, a recognized publisher temporary may be
    an exact prefix of its expected bytes because a hard stop can interrupt
    the sequential write.  Final-name files always remain exact-only, as do
    all temporaries once a commit marker has been observed.
    """

    expected_by_name = dict(expected_files)
    try:
        leftovers = tuple(target.iterdir())
    except OSError as exc:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot residue is unreadable"
        ) from exc
    failures: list[str] = []
    verified: list[Path] = []
    for path in leftovers:
        expected = expected_by_name.get(path.name)
        is_final = expected is not None
        if expected is None:
            matched_name = next(
                (
                    name
                    for name in expected_by_name
                    if path.name.startswith(f".{name}.")
                    and path.name.endswith(".tmp")
                ),
                None,
            )
            if matched_name is None:
                failures.append(path.name)
                continue
            expected = expected_by_name[matched_name]
        if is_final and not include_final_files:
            continue
        try:
            status = path.lstat()
            actual = _read_regular_bytes(
                path,
                label=f"partial {path.name}",
                max_bytes=len(expected),
            )
            if (
                _status_is_redirect(status)
                or not stat.S_ISREG(status.st_mode)
                or (
                    actual != expected
                    and (
                        is_final
                        or not include_final_files
                        or not expected.startswith(actual)
                    )
                )
            ):
                failures.append(path.name)
                continue
            verified.append(path)
        except (OSError, SecBulkParsedSnapshotError):
            failures.append(path.name)
    if failures:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed publication left unverified files: "
            + ", ".join(sorted(set(failures)))
        )
    return tuple(verified)


def _unlink_verified(paths: tuple[Path, ...]) -> None:
    failures: list[str] = []
    for path in reversed(paths):
        try:
            path.unlink()
        except OSError:
            failures.append(path.name)
    if failures:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed publication left unverified files: "
            + ", ".join(sorted(set(failures)))
        )


def _rollback_uncommitted(
    target: Path, expected_files: tuple[tuple[str, bytes], ...]
) -> None:
    _unlink_verified(
        _verify_publication_residue(
            target, expected_files, include_final_files=True
        )
    )


def _clean_verified_temporaries(
    target: Path, expected_files: tuple[tuple[str, bytes], ...]
) -> None:
    _unlink_verified(
        _verify_publication_residue(
            target, expected_files, include_final_files=False
        )
    )


def _parse_jsonl_objects(
    raw: bytes, *, label: str, max_records: int
) -> tuple[dict[str, object], ...]:
    if not raw:
        return ()
    if not raw.endswith(b"\n"):
        raise SecBulkParsedSnapshotError(
            f"REFUSED: {label} is not canonical newline-delimited JSON"
        )
    objects: list[dict[str, object]] = []
    for line in raw.splitlines(keepends=True):
        if len(objects) >= max_records:
            raise SecBulkParsedSnapshotError(
                f"REFUSED: {label} exceeds its record-count limit"
            )
        try:
            value = json.loads(line)
            canonical = _canonical_json_bytes(value)
        except (TypeError, UnicodeError, ValueError) as exc:
            raise SecBulkParsedSnapshotError(
                f"REFUSED: {label} contains invalid JSON"
            ) from exc
        if not isinstance(value, dict) or line != canonical:
            raise SecBulkParsedSnapshotError(
                f"REFUSED: {label} is not canonical newline-delimited JSON"
            )
        objects.append(value)
    return tuple(objects)


def _table_identity_from_payload(payload: object) -> ParsedSecBulkTableIdentity:
    if not isinstance(payload, dict) or set(payload) != _TABLE_IDENTITY_KEYS:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed table identity fields are not exact"
        )
    headers = payload.get("headers")
    source_row_key_headers = payload.get("source_row_key_headers")
    if (
        not isinstance(headers, list)
        or not isinstance(source_row_key_headers, list)
        or any(not isinstance(item, str) for item in headers)
        or any(not isinstance(item, str) for item in source_row_key_headers)
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed table identity headers are malformed"
        )
    item = ParsedSecBulkTableIdentity(
        table_name=payload.get("table_name"),
        schema_id=payload.get("schema_id"),
        headers=tuple(headers),
        source_row_key_headers=tuple(source_row_key_headers),
        header_hash=payload.get("header_hash"),
        raw_member_sha256=payload.get("raw_member_sha256"),
        raw_member_size_bytes=payload.get("raw_member_size_bytes"),
        row_count=payload.get("row_count"),
        row_ids_hash=payload.get("row_ids_hash"),
    )
    if (
        item.table_name not in ALLOWED_SEC_TABLES
        or not isinstance(item.schema_id, str)
        or _IDENTIFIER_RE.fullmatch(item.schema_id) is None
        or not item.headers
        or len(item.headers) > MAX_HEADER_COLUMNS
        or hash_payload(list(item.headers)) != item.header_hash
        or not isinstance(item.raw_member_sha256, str)
        or _SHA256_RE.fullmatch(item.raw_member_sha256) is None
        or type(item.raw_member_size_bytes) is not int
        or not 0 < item.raw_member_size_bytes <= MAX_PARSED_TABLE_INPUT_BYTES
        or type(item.row_count) is not int
        or not 0 <= item.row_count <= MAX_ROWS_PER_TABLE
        or not isinstance(item.row_ids_hash, str)
        or _SHA256_RE.fullmatch(item.row_ids_hash) is None
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed table identity is invalid"
        )
    return item


def _artifact_identity_from_payload(
    payload: object,
) -> ParsedSecBulkArtifactIdentity:
    if not isinstance(payload, dict) or set(payload) != _ARTIFACT_IDENTITY_KEYS:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed artifact identity fields are not exact"
        )
    item = ParsedSecBulkArtifactIdentity(
        name=payload.get("name"),
        sha256=payload.get("sha256"),
        size_bytes=payload.get("size_bytes"),
        record_count=payload.get("record_count"),
    )
    if not isinstance(item.name, str):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed artifact identity is invalid"
        )
    byte_limit = {
        _ROWS_NAME: MAX_ROWS_ARTIFACT_BYTES,
        _ACCESSIONS_NAME: MAX_ACCESSIONS_ARTIFACT_BYTES,
    }.get(item.name)
    record_limit = {
        _ROWS_NAME: MAX_TOTAL_ROWS,
        _ACCESSIONS_NAME: MAX_TOTAL_ROWS,
    }.get(item.name)
    if (
        byte_limit is None
        or not isinstance(item.sha256, str)
        or _SHA256_RE.fullmatch(item.sha256) is None
        or type(item.size_bytes) is not int
        or not 0 <= item.size_bytes <= byte_limit
        or type(item.record_count) is not int
        or not 0 <= item.record_count <= record_limit
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed artifact identity is invalid"
        )
    return item


def _identity_from_manifest(
    manifest: dict[str, object], *, directory_name: str
) -> SecBulkParsedSnapshotIdentity:
    if set(manifest) != _MANIFEST_KEYS:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot manifest fields are not exact"
        )
    if (
        manifest.get("kind") != PARSED_SNAPSHOT_KIND
        or type(manifest.get("parsed_contract_version")) is not int
        or manifest.get("parsed_contract_version")
        != PARSED_SNAPSHOT_CONTRACT_VERSION
        or manifest.get("parser_version") != SEC_TSV_PARSER_VERSION
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot contract identity is invalid"
        )
    parser_git_commit = manifest.get("parser_git_commit")
    if (
        not isinstance(parser_git_commit, str)
        or _GIT_COMMIT_RE.fullmatch(parser_git_commit) is None
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot parser provenance is invalid"
        )
    year = manifest.get("year")
    quarter = manifest.get("quarter")
    _period_index(year, quarter, label="parsed snapshot")
    raw_snapshot_id = manifest.get("raw_snapshot_id")
    raw_lineage_hash = manifest.get("raw_lineage_hash")
    raw_archive_sha256 = manifest.get("raw_archive_sha256")
    raw_manifest_sha256 = manifest.get("raw_manifest_sha256")
    if (
        not isinstance(raw_snapshot_id, str)
        or _RAW_SNAPSHOT_ID_RE.fullmatch(raw_snapshot_id) is None
        or not raw_snapshot_id.startswith(f"sec-insider-bulk-{year:04d}q{quarter}-")
        or any(
            not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None
            for value in (
                raw_lineage_hash,
                raw_archive_sha256,
                raw_manifest_sha256,
            )
        )
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot raw lineage is invalid"
        )
    schema_profile = SecTsvSchemaProfile.from_payload(
        manifest.get("schema_profile")
    )
    schema_profile_hash = manifest.get("schema_profile_hash")
    if (
        not isinstance(schema_profile_hash, str)
        or schema_profile_hash != hash_payload(schema_profile.to_payload())
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot schema profile hash is invalid"
        )
    absent_payload = manifest.get("absent_tables")
    if not isinstance(absent_payload, list) or any(
        item not in ALLOWED_SEC_TABLES for item in absent_payload
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot absent-table inventory is invalid"
        )
    absent_tables = tuple(absent_payload)
    canonical_absent = tuple(name for name in ALLOWED_SEC_TABLES if name in absent_tables)
    if absent_tables != canonical_absent or len(set(absent_tables)) != len(absent_tables):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot absent-table inventory is not canonical"
        )
    present_tables = tuple(
        name for name in ALLOWED_SEC_TABLES if name not in absent_tables
    )
    if not set(REQUIRED_SEC_TABLES).issubset(present_tables):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot omits a required core table"
        )
    table_payloads = manifest.get("tables")
    if not isinstance(table_payloads, list):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot table identities are malformed"
        )
    tables = tuple(_table_identity_from_payload(item) for item in table_payloads)
    if tuple(item.table_name for item in tables) != present_tables:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot table identity order is invalid"
        )
    for table in tables:
        variant = schema_profile.variant_for(table.table_name, year, quarter)
        if table.schema_id != variant.schema_id or table.headers != variant.headers:
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed table identity disagrees with schema profile"
            )
        if table.source_row_key_headers != variant.source_row_key_headers:
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed source-row key disagrees with schema profile"
            )
    artifact_payloads = manifest.get("artifacts")
    if not isinstance(artifact_payloads, list):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot artifact identities are malformed"
        )
    artifacts = tuple(
        _artifact_identity_from_payload(item) for item in artifact_payloads
    )
    if tuple(item.name for item in artifacts) != _ARTIFACT_NAMES:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot artifact identity order is invalid"
        )
    lineage_hash = manifest.get("lineage_hash")
    snapshot_id = manifest.get("snapshot_id")
    provisional = SecBulkParsedSnapshotIdentity(
        year=year,
        quarter=quarter,
        parser_git_commit=parser_git_commit,
        raw_snapshot_id=raw_snapshot_id,
        raw_lineage_hash=raw_lineage_hash,
        raw_archive_sha256=raw_archive_sha256,
        raw_manifest_sha256=raw_manifest_sha256,
        schema_profile=schema_profile,
        schema_profile_hash=schema_profile_hash,
        absent_tables=absent_tables,
        tables=tables,
        artifacts=artifacts,
        lineage_hash=lineage_hash,
        snapshot_id=snapshot_id,
    )
    expected_lineage = hash_payload(provisional.lineage_payload())
    expected_snapshot_id = (
        f"sec-insider-parsed-{year:04d}q{quarter}-{expected_lineage[:16]}"
    )
    if (
        not isinstance(lineage_hash, str)
        or lineage_hash != expected_lineage
        or snapshot_id != expected_snapshot_id
        or directory_name != expected_snapshot_id
        or manifest != provisional.to_payload()
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot lineage identity is invalid"
        )
    return provisional


def _validate_rows(
    objects: tuple[dict[str, object], ...],
    identity: SecBulkParsedSnapshotIdentity,
) -> tuple[ParsedSecBulkRow, ...]:
    table_by_name = {item.table_name: item for item in identity.tables}
    table_order = {item.table_name: index for index, item in enumerate(identity.tables)}
    expected_ordinal = {item.table_name: 1 for item in identity.tables}
    previous_table_index = 0
    observed_source_row_keys: dict[str, set[tuple[str, tuple[str, ...]]]] = {
        item.table_name: set() for item in identity.tables
    }
    rows: list[ParsedSecBulkRow] = []
    total_field_characters = 0
    for payload in objects:
        if set(payload) != _ROW_KEYS:
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed row fields are not exact"
            )
        table_name = payload.get("table_name")
        if not isinstance(table_name, str):
            raise SecBulkParsedSnapshotError("REFUSED: parsed row is invalid")
        table = table_by_name.get(table_name)
        if table is None or table_order[table_name] < previous_table_index:
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed row table order is invalid"
            )
        previous_table_index = table_order[table_name]
        schema_id = payload.get("schema_id")
        ordinal = payload.get("source_record_ordinal")
        accession_number = payload.get("accession_number")
        values = payload.get("values")
        source_row_key = payload.get("source_row_key")
        row_id = payload.get("row_id")
        if (
            schema_id != table.schema_id
            or type(ordinal) is not int
            or ordinal != expected_ordinal[table_name]
            or not isinstance(accession_number, str)
            or _ACCESSION_RE.fullmatch(accession_number) is None
            or not isinstance(values, list)
            or len(values) != len(table.headers)
            or any(not isinstance(value, str) for value in values)
            or any(len(value) > MAX_FIELD_CHARACTERS for value in values)
            or not isinstance(source_row_key, list)
            or any(not isinstance(value, str) for value in source_row_key)
            or not isinstance(row_id, str)
            or _SHA256_RE.fullmatch(row_id) is None
        ):
            raise SecBulkParsedSnapshotError("REFUSED: parsed row is invalid")
        total_field_characters += sum(len(value) for value in values)
        if total_field_characters > MAX_TOTAL_FIELD_CHARACTERS:
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed rows exceed the total field budget"
            )
        if values[table.headers.index("ACCESSION_NUMBER")] != accession_number:
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed row accession projection is invalid"
            )
        expected_source_row_key = tuple(
            values[table.headers.index(header)]
            for header in table.source_row_key_headers
        )
        if tuple(source_row_key) != expected_source_row_key or any(
            not value.strip() for value in expected_source_row_key
        ):
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed row source-key projection is invalid"
            )
        accession_relative_key = (accession_number, expected_source_row_key)
        if (
            expected_source_row_key
            and accession_relative_key in observed_source_row_keys[table_name]
        ):
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed rows contain a duplicate source-row key"
            )
        if expected_source_row_key:
            observed_source_row_keys[table_name].add(accession_relative_key)
        expected_id = _source_row_id(
            raw_snapshot_id=identity.raw_snapshot_id,
            raw_lineage_hash=identity.raw_lineage_hash,
            raw_archive_sha256=identity.raw_archive_sha256,
            table_name=table_name,
            raw_member_sha256=table.raw_member_sha256,
            source_record_ordinal=ordinal,
            values=tuple(values),
            source_row_key=expected_source_row_key,
        )
        if row_id != expected_id:
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed row lineage identity is invalid"
            )
        rows.append(
            ParsedSecBulkRow(
                table_name=table_name,
                schema_id=schema_id,
                source_record_ordinal=ordinal,
                accession_number=accession_number,
                values=tuple(values),
                source_row_key=expected_source_row_key,
                row_id=row_id,
            )
        )
        expected_ordinal[table_name] += 1
    for table in identity.tables:
        table_rows = tuple(row for row in rows if row.table_name == table.table_name)
        if (
            len(table_rows) != table.row_count
            or hash_payload([row.row_id for row in table_rows])
            != table.row_ids_hash
        ):
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed table row lineage is invalid"
            )
    return tuple(rows)


def _load_self_consistent_sec_bulk_parsed_snapshot(
    parsed_snapshot_directory: str | Path,
) -> LoadedSecBulkParsedSnapshot:
    """Validate the parsed artifact's internal content-addressed contract."""

    directory = Path(parsed_snapshot_directory)
    if _PARSED_SNAPSHOT_ID_RE.fullmatch(directory.name) is None:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot directory name is invalid"
        )
    _require_regular_directory(directory, label="parsed snapshot directory")
    try:
        names = {path.name for path in directory.iterdir()}
    except OSError as exc:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot directory is unreadable"
        ) from exc
    allowed = set(_PUBLICATION_NAMES) | {_COMMIT_NAME}
    if _COMMIT_NAME not in names:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot is incomplete; commit marker is missing"
        )
    if names != allowed:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot has missing or unexpected files"
        )

    commit = _read_canonical_object(
        directory / _COMMIT_NAME,
        label="parsed commit marker",
        max_bytes=MAX_PARSED_COMMIT_BYTES,
        require_single_link=True,
    )
    if set(commit) != {"kind", "snapshot_id", "members"}:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed commit marker fields are not exact"
        )
    members = commit.get("members")
    if (
        commit.get("kind") != f"{PARSED_SNAPSHOT_KIND}-commit"
        or commit.get("snapshot_id") != directory.name
        or not isinstance(members, dict)
        or set(members) != set(_PUBLICATION_NAMES)
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed commit marker identity is invalid"
        )
    payload_bytes = {
        _ROWS_NAME: _read_regular_bytes(
            directory / _ROWS_NAME,
            label="parsed rows artifact",
            max_bytes=MAX_ROWS_ARTIFACT_BYTES,
            require_single_link=True,
        ),
        _ACCESSIONS_NAME: _read_regular_bytes(
            directory / _ACCESSIONS_NAME,
            label="parsed accessions artifact",
            max_bytes=MAX_ACCESSIONS_ARTIFACT_BYTES,
            require_single_link=True,
        ),
        _MANIFEST_NAME: _read_regular_bytes(
            directory / _MANIFEST_NAME,
            label="parsed manifest",
            max_bytes=MAX_PARSED_MANIFEST_BYTES,
            require_single_link=True,
        ),
    }
    if members != {name: hash_bytes(raw) for name, raw in payload_bytes.items()}:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed committed member hash mismatch"
        )
    manifest = _canonical_object(payload_bytes[_MANIFEST_NAME], label="parsed manifest")
    identity = _identity_from_manifest(manifest, directory_name=directory.name)
    artifacts_by_name = {item.name: item for item in identity.artifacts}
    for name in _ARTIFACT_NAMES:
        artifact = artifacts_by_name[name]
        raw = payload_bytes[name]
        if artifact.sha256 != hash_bytes(raw) or artifact.size_bytes != len(raw):
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed artifact disagrees with manifest identity"
            )
    row_objects = _parse_jsonl_objects(
        payload_bytes[_ROWS_NAME], label="parsed rows artifact", max_records=MAX_TOTAL_ROWS
    )
    rows = _validate_rows(row_objects, identity)
    accessions = _build_accessions(rows, identity.tables)
    accession_objects = _parse_jsonl_objects(
        payload_bytes[_ACCESSIONS_NAME],
        label="parsed accessions artifact",
        max_records=MAX_TOTAL_ROWS,
    )
    if accession_objects != tuple(item.to_payload() for item in accessions):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed accession index does not match source rows"
        )
    if (
        artifacts_by_name[_ROWS_NAME].record_count != len(rows)
        or artifacts_by_name[_ACCESSIONS_NAME].record_count != len(accessions)
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed artifact record counts are invalid"
        )
    return LoadedSecBulkParsedSnapshot(
        identity=identity,
        rows=rows,
        accessions=accessions,
    )


def load_sec_bulk_parsed_snapshot(
    parsed_snapshot_directory: str | Path,
    *,
    raw_snapshot_directory: str | Path,
) -> LoadedSecBulkParsedSnapshot:
    """Revalidate a parsed artifact against its committed raw snapshot.

    Internal hashes alone cannot prove that claimed row values were produced
    from claimed raw bytes.  Every public load therefore requires the raw
    snapshot, runs the IB-1A loader, deterministically reparses it under the
    persisted profile/parser provenance, and compares the complete result.
    """

    loaded = _load_self_consistent_sec_bulk_parsed_snapshot(
        parsed_snapshot_directory
    )
    expected_identity, expected_rows, expected_accessions, _, _ = (
        _assemble_parsed_snapshot(
            raw_snapshot_directory,
            schema_profile=loaded.identity.schema_profile,
            parser_git_commit=loaded.identity.parser_git_commit,
        )
    )
    if (
        loaded.identity != expected_identity
        or loaded.rows != expected_rows
        or loaded.accessions != expected_accessions
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot does not match the verified raw snapshot"
        )
    return loaded


def _recover_committed(
    target: Path,
    expected_files: tuple[tuple[str, bytes], ...],
    identity: SecBulkParsedSnapshotIdentity,
    rows: tuple[ParsedSecBulkRow, ...],
    accessions: tuple[ParsedSecBulkAccession, ...],
    raw_snapshot_directory: str | Path,
) -> LoadedSecBulkParsedSnapshot | None:
    try:
        (target / _COMMIT_NAME).lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed commit-marker state is unreadable"
        ) from exc
    _clean_verified_temporaries(target, expected_files)
    loaded = load_sec_bulk_parsed_snapshot(
        target, raw_snapshot_directory=raw_snapshot_directory
    )
    if (
        loaded.identity != identity
        or loaded.rows != rows
        or loaded.accessions != accessions
    ):
        raise SecBulkParsedSnapshotError(
            "REFUSED: committed parsed snapshot conflicts with attempted publication"
        )
    return loaded


def _settle_failed_publication(
    target: Path,
    expected_files: tuple[tuple[str, bytes], ...],
    identity: SecBulkParsedSnapshotIdentity,
    rows: tuple[ParsedSecBulkRow, ...],
    accessions: tuple[ParsedSecBulkAccession, ...],
    raw_snapshot_directory: str | Path,
) -> LoadedSecBulkParsedSnapshot | None:
    recovered = _recover_committed(
        target,
        expected_files,
        identity,
        rows,
        accessions,
        raw_snapshot_directory,
    )
    if recovered is None:
        _rollback_uncommitted(target, expected_files)
    return recovered


def build_sec_bulk_parsed_snapshot(
    raw_snapshot_directory: str | Path,
    output_root: str | Path,
    *,
    schema_profile: SecTsvSchemaProfile,
    parser_git_commit: str,
) -> SecBulkParsedSnapshotIdentity:
    """Parse and immutably publish one verified raw quarterly snapshot."""

    identity, rows, accessions, rows_bytes, accessions_bytes = (
        _assemble_parsed_snapshot(
            raw_snapshot_directory,
            schema_profile=schema_profile,
            parser_git_commit=parser_git_commit,
        )
    )
    try:
        raw_directory = Path(raw_snapshot_directory).resolve(strict=True)
        prospective_root = Path(output_root).resolve(strict=False)
    except (OSError, TypeError, ValueError) as exc:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed snapshot paths are invalid"
        ) from exc
    if prospective_root == raw_directory or raw_directory in prospective_root.parents:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed output root cannot be the raw snapshot or its descendant"
        )
    root = _prepare_output_root(output_root)
    if root == raw_directory or raw_directory in root.parents:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed output root cannot be the raw snapshot or its descendant"
        )
    manifest_bytes = _canonical_json_bytes(identity.to_payload())
    if len(manifest_bytes) > MAX_PARSED_MANIFEST_BYTES:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed manifest exceeds its byte-size limit"
        )
    payloads = {
        _ROWS_NAME: rows_bytes,
        _ACCESSIONS_NAME: accessions_bytes,
        _MANIFEST_NAME: manifest_bytes,
    }
    commit_bytes = _canonical_json_bytes(
        {
            "kind": f"{PARSED_SNAPSHOT_KIND}-commit",
            "snapshot_id": identity.snapshot_id,
            "members": {
                name: hash_bytes(data) for name, data in sorted(payloads.items())
            },
        }
    )
    if len(commit_bytes) > MAX_PARSED_COMMIT_BYTES:
        raise SecBulkParsedSnapshotError(
            "REFUSED: parsed commit marker exceeds its byte-size limit"
        )
    publication = tuple(payloads.items()) + ((_COMMIT_NAME, commit_bytes),)
    target = root / identity.snapshot_id
    lock_path = root / f".{identity.snapshot_id}{_LOCK_SUFFIX}"
    _require_regular_lock_slot(lock_path)
    with _ParsedPublicationLock(lock_path):
        _require_regular_directory(root, label="parsed snapshot output root")
        _require_regular_lock_slot(lock_path)
        if not _require_regular_directory(
            target, label="parsed snapshot target", missing_ok=True
        ):
            try:
                target.mkdir()
            except OSError as exc:
                raise SecBulkParsedSnapshotError(
                    "REFUSED: parsed snapshot target could not be created"
                ) from exc
            _require_regular_directory(target, label="parsed snapshot target")
        try:
            existing = {path.name for path in target.iterdir()}
        except OSError as exc:
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed snapshot target is unreadable"
            ) from exc
        if _COMMIT_NAME in existing:
            loaded = _recover_committed(
                target,
                publication,
                identity,
                rows,
                accessions,
                raw_snapshot_directory,
            )
            if loaded is None:
                raise SecBulkParsedSnapshotError(
                    "REFUSED: parsed commit marker disappeared during retry"
                )
            return loaded.identity
        if existing:
            _rollback_uncommitted(target, publication)
        try:
            for name, data in payloads.items():
                publish_immutable_bytes(target / name, data)
            publish_immutable_bytes(target / _COMMIT_NAME, commit_bytes)
            loaded = load_sec_bulk_parsed_snapshot(
                target, raw_snapshot_directory=raw_snapshot_directory
            )
            if (
                loaded.identity != identity
                or loaded.rows != rows
                or loaded.accessions != accessions
            ):
                raise SecBulkParsedSnapshotError(
                    "REFUSED: published parsed snapshot failed final verification"
                )
        except SecBulkParsedSnapshotError as exc:
            try:
                recovered = _settle_failed_publication(
                    target,
                    publication,
                    identity,
                    rows,
                    accessions,
                    raw_snapshot_directory,
                )
            except SecBulkParsedSnapshotError as recovery_exc:
                raise recovery_exc from exc
            if recovered is not None:
                return recovered.identity
            raise
        except (ImmutableFileConflictError, OSError) as exc:
            try:
                recovered = _settle_failed_publication(
                    target,
                    publication,
                    identity,
                    rows,
                    accessions,
                    raw_snapshot_directory,
                )
            except SecBulkParsedSnapshotError as recovery_exc:
                raise SecBulkParsedSnapshotError(
                    "REFUSED: parsed snapshot publication recovery failed"
                ) from recovery_exc
            if recovered is not None:
                return recovered.identity
            raise SecBulkParsedSnapshotError(
                "REFUSED: parsed snapshot publication conflicted or failed"
            ) from exc
        except BaseException as exc:
            try:
                _settle_failed_publication(
                    target,
                    publication,
                    identity,
                    rows,
                    accessions,
                    raw_snapshot_directory,
                )
            except SecBulkParsedSnapshotError as recovery_exc:
                raise recovery_exc from exc
            raise
    return loaded.identity
