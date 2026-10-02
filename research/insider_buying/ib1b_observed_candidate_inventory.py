"""One-quarter, zero-I/O inventory of IB-1B-observed Form 4/4-A accessions.

This is a retrieval *priority*, not a complete Form 4 XML population or a
canonical purchase filter. Every exact observed nonderivative code-P filing,
every amendment, and every malformed transaction-code filing is prioritized.
Other filings remain in the denominator; an omitted or misclassified bulk TSV
row could still hide a purchase in its complete XML. The caller must obtain
the input through ``load_sec_bulk_parsed_snapshot`` with its raw parent.  A
typed object alone cannot prove SEC origin, source completeness, or PIT status.

The boundary deliberately accepts one loaded quarter, not an 82-quarter
collection. It performs no filesystem, provider, outcome, or QC operation.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace

from data.hashing import canonical_json, hash_payload
from research.insider_buying.sec_bulk_parsed_snapshot import (
    MAX_FIELD_CHARACTERS,
    MAX_TOTAL_FIELD_CHARACTERS,
    MAX_TOTAL_ROWS,
    LoadedSecBulkParsedSnapshot,
    ParsedSecBulkAccession,
    ParsedSecBulkRow,
    ParsedSecBulkTableIdentity,
    SecBulkParsedSnapshotError,
    SecBulkParsedSnapshotIdentity,
    _build_accessions,
    _source_row_id,
)
from research.insider_buying.sec_bulk_snapshot import (
    ALLOWED_SEC_TABLES,
    REQUIRED_SEC_TABLES,
)
from research.insider_buying.sec_ib1b_82q_schema_profile import (
    RETAINED_82Q_SCHEMA_PROFILE_SHA256,
    Retained82qSchemaProfileError,
    verify_retained_82q_schema_profile,
)
from research.insider_buying.sec_ib1b_pilot_profile import (
    PILOT_PERIODS,
    PILOT_SCHEMA_PROFILE_SHA256,
    Ib1bPilotProfileError,
    verify_approved_ib1b_schema_profile,
)


INVENTORY_KIND = "insider-buying-ib1b-observed-candidate-quarter"
INVENTORY_VERSION = 1
MAX_ACCESSIONS_PER_QUARTER = 500_000
MAX_ROWS_PER_ACCESSION = 100_000
MAX_RECORD_JSON_BYTES = 8 * 1024 * 1024
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_ACCESSION_RE = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_FORMS = frozenset({"3", "3/A", "4", "4/A", "5", "5/A"})
_TARGET_FORMS = frozenset({"4", "4/A"})


class Ib1bObservedCandidateInventoryError(ValueError):
    """A caller-loaded quarter or its observed candidate projection refused."""


@dataclass(frozen=True)
class ObservedCandidateAccession:
    accession_number: str
    document_type: str
    submission_row_id: str
    source_row_ids: tuple[tuple[str, tuple[str, ...]], ...]
    observed_p_row_ids: tuple[str, ...]
    selected_for_retrieval: bool
    selection_reasons: tuple[str, ...]
    nonselection_reason: str | None

    def to_payload(self) -> dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "document_type": self.document_type,
            "submission_row_id": self.submission_row_id,
            "source_row_ids": [
                {"table_name": name, "row_ids": list(ids)}
                for name, ids in self.source_row_ids
            ],
            "observed_p_row_ids": list(self.observed_p_row_ids),
            "selected_for_retrieval": self.selected_for_retrieval,
            "selection_reasons": list(self.selection_reasons),
            "nonselection_reason": self.nonselection_reason,
        }


def _digest(
    *, metadata: dict[str, object], records: tuple[ObservedCandidateAccession, ...]
) -> str:
    """Canonical, domain-separated JSONL digest without an all-quarter blob."""

    digest = hashlib.sha256()
    digest.update((INVENTORY_KIND + "/v1\n").encode("ascii"))
    digest.update((canonical_json(metadata) + "\n").encode("utf-8"))
    for record in records:
        line = (canonical_json(record.to_payload()) + "\n").encode("utf-8")
        if len(line) > MAX_RECORD_JSON_BYTES:
            raise Ib1bObservedCandidateInventoryError(
                "REFUSED: one candidate exceeds the bounded record-size limit"
            )
        digest.update(line)
    return digest.hexdigest()


@dataclass(frozen=True)
class ObservedCandidateQuarter:
    year: int
    quarter: int
    parsed_snapshot_id: str
    parsed_lineage_hash: str
    raw_snapshot_id: str
    schema_profile_id: str
    schema_profile_sha256: str
    records: tuple[ObservedCandidateAccession, ...]
    form4_count: int
    form4a_count: int
    selected_count: int
    nonselected_count: int
    content_sha256: str

    @property
    def canonical(self) -> bool:
        return False

    @property
    def point_in_time_data(self) -> bool:
        return False

    @property
    def xml_completeness_verified(self) -> bool:
        return False

    @property
    def outcome_looks(self) -> int:
        return 0

    @property
    def qc_jobs(self) -> int:
        return 0

    def _metadata(self) -> dict[str, object]:
        return {
            "kind": INVENTORY_KIND,
            "version": INVENTORY_VERSION,
            "source_scope": "IB1B_OBSERVED_NONCANONICAL",
            "year": self.year,
            "quarter": self.quarter,
            "parsed_snapshot_id": self.parsed_snapshot_id,
            "parsed_lineage_hash": self.parsed_lineage_hash,
            "raw_snapshot_id": self.raw_snapshot_id,
            "schema_profile_id": self.schema_profile_id,
            "schema_profile_sha256": self.schema_profile_sha256,
            "form4_count": self.form4_count,
            "form4a_count": self.form4a_count,
            "selected_count": self.selected_count,
            "nonselected_count": self.nonselected_count,
            "canonical": False,
            "point_in_time_data": False,
            "xml_completeness_verified": False,
            "source_authenticity_verified": False,
            "acceptance_metadata_verified": False,
            "outcome_looks": 0,
            "qc_jobs": 0,
        }

    def verify_digest(self) -> None:
        if (
            type(self.records) is not tuple
            or any(type(item) is not ObservedCandidateAccession for item in self.records)
            or len(self.records) != self.form4_count + self.form4a_count
            or len(self.records) != self.selected_count + self.nonselected_count
            or sum(item.selected_for_retrieval for item in self.records) != self.selected_count
            or tuple(item.accession_number for item in self.records)
            != tuple(sorted({item.accession_number for item in self.records}))
            or not isinstance(self.content_sha256, str)
            or _SHA256_RE.fullmatch(self.content_sha256) is None
            or _digest(metadata=self._metadata(), records=self.records) != self.content_sha256
        ):
            raise Ib1bObservedCandidateInventoryError(
                "REFUSED: observed candidate inventory digest or counts changed"
            )


def _validate_loaded_quarter(
    loaded: LoadedSecBulkParsedSnapshot,
) -> tuple[SecBulkParsedSnapshotIdentity, dict[str, ParsedSecBulkTableIdentity]]:
    if type(loaded) is not LoadedSecBulkParsedSnapshot or type(loaded.identity) is not SecBulkParsedSnapshotIdentity:
        raise Ib1bObservedCandidateInventoryError(
            "REFUSED: one exact loaded IB-1B quarter is required"
        )
    identity = loaded.identity
    if (
        type(identity.year) is not int
        or type(identity.quarter) is not int
        or not (2006, 1) <= (identity.year, identity.quarter) <= (2026, 2)
        or identity.quarter not in {1, 2, 3, 4}
        or type(loaded.rows) is not tuple
        or type(loaded.accessions) is not tuple
        or len(loaded.rows) > MAX_TOTAL_ROWS
        or len(loaded.accessions) > MAX_ACCESSIONS_PER_QUARTER
    ):
        raise Ib1bObservedCandidateInventoryError(
            "REFUSED: loaded quarter exceeds its exact period or count bound"
        )
    try:
        if identity.schema_profile_hash == RETAINED_82Q_SCHEMA_PROFILE_SHA256:
            verify_retained_82q_schema_profile(identity.schema_profile)
        elif identity.schema_profile_hash == PILOT_SCHEMA_PROFILE_SHA256:
            if (identity.year, identity.quarter) not in PILOT_PERIODS:
                raise Ib1bObservedCandidateInventoryError(
                    "REFUSED: approved pilot header profile is outside its two quarters"
                )
            verify_approved_ib1b_schema_profile(identity.schema_profile)
        else:
            raise Ib1bObservedCandidateInventoryError(
                "REFUSED: loaded quarter has no exact pinned IB-1B header profile"
            )
    except (Retained82qSchemaProfileError, Ib1bPilotProfileError, AttributeError, TypeError, ValueError) as exc:
        if isinstance(exc, Ib1bObservedCandidateInventoryError):
            raise
        raise Ib1bObservedCandidateInventoryError(
            "REFUSED: loaded quarter does not use an exact pinned IB-1B header profile"
        ) from exc
    if (
        identity.schema_profile_hash != hash_payload(identity.schema_profile.to_payload())
        or type(identity.absent_tables) is not tuple
        or identity.absent_tables
        != tuple(name for name in ALLOWED_SEC_TABLES if name in identity.absent_tables)
        or type(identity.tables) is not tuple
        or any(type(table) is not ParsedSecBulkTableIdentity for table in identity.tables)
        or tuple(table.table_name for table in identity.tables)
        != tuple(name for name in ALLOWED_SEC_TABLES if name not in identity.absent_tables)
        or not set(REQUIRED_SEC_TABLES).issubset({table.table_name for table in identity.tables})
        or type(identity.parser_git_commit) is not str
        or _GIT_COMMIT_RE.fullmatch(identity.parser_git_commit) is None
        or type(identity.raw_snapshot_id) is not str
        or re.fullmatch(
            rf"sec-insider-bulk-{identity.year:04d}q{identity.quarter}-[0-9a-f]{{16}}\Z",
            identity.raw_snapshot_id,
        ) is None
        or any(
            type(value) is not str or _SHA256_RE.fullmatch(value) is None
            for value in (
                identity.raw_lineage_hash,
                identity.raw_archive_sha256,
                identity.raw_manifest_sha256,
            )
        )
        or type(identity.lineage_hash) is not str
        or identity.lineage_hash != hash_payload(identity.lineage_payload())
        or identity.snapshot_id
        != f"sec-insider-parsed-{identity.year:04d}q{identity.quarter}-{identity.lineage_hash[:16]}"
    ):
        raise Ib1bObservedCandidateInventoryError(
            "REFUSED: loaded quarter lineage or table inventory is inconsistent"
        )
    by_table = {table.table_name: table for table in identity.tables}
    for table in identity.tables:
        try:
            variant = identity.schema_profile.variant_for(
                table.table_name, identity.year, identity.quarter
            )
        except SecBulkParsedSnapshotError as exc:
            raise Ib1bObservedCandidateInventoryError(
                "REFUSED: loaded quarter has an unprofiled table header"
            ) from exc
        if (
            table.headers != variant.headers
            or table.schema_id != variant.schema_id
            or table.source_row_key_headers != variant.source_row_key_headers
            or table.header_hash != hash_payload(list(variant.headers))
            or type(table.row_count) is not int
            or table.row_count < 0
            or type(table.raw_member_sha256) is not str
            or _SHA256_RE.fullmatch(table.raw_member_sha256) is None
            or type(table.row_ids_hash) is not str
            or _SHA256_RE.fullmatch(table.row_ids_hash) is None
        ):
            raise Ib1bObservedCandidateInventoryError(
                "REFUSED: loaded quarter table header or identity drifted"
            )
    if "TRANS_CODE" not in by_table["NONDERIV_TRANS.tsv"].headers:
        raise Ib1bObservedCandidateInventoryError(
            "REFUSED: NONDERIV_TRANS transaction-code header is missing"
        )
    return identity, by_table


def _validate_rows_and_index(
    loaded: LoadedSecBulkParsedSnapshot,
    tables: dict[str, ParsedSecBulkTableIdentity],
) -> dict[str, str]:
    """Rebind source-row IDs and exact accession membership, including orphans."""

    identity = loaded.identity
    row_ids_by_table: dict[str, list[str]] = {name: [] for name in tables}
    transaction_codes: dict[str, str] = {}
    seen_ids: set[str] = set()
    total_field_characters = 0
    for row in loaded.rows:
        if (
            type(row) is not ParsedSecBulkRow
            or type(row.table_name) is not str
            or row.table_name not in tables
        ):
            raise Ib1bObservedCandidateInventoryError("REFUSED: parsed row table is invalid")
        table = tables[row.table_name]
        if (
            row.schema_id != table.schema_id
            or type(row.source_record_ordinal) is not int
            or row.source_record_ordinal != len(row_ids_by_table[row.table_name]) + 1
            or type(row.accession_number) is not str
            or _ACCESSION_RE.fullmatch(row.accession_number) is None
            or type(row.values) is not tuple
            or len(row.values) != len(table.headers)
            or any(type(value) is not str for value in row.values)
            or any(len(value) > MAX_FIELD_CHARACTERS for value in row.values)
            or type(row.source_row_key) is not tuple
            or any(type(value) is not str for value in row.source_row_key)
            or row.source_row_key != tuple(
                row.values[table.headers.index(name)]
                for name in table.source_row_key_headers
            )
            or row.values[table.headers.index("ACCESSION_NUMBER")] != row.accession_number
            or type(row.row_id) is not str
            or _SHA256_RE.fullmatch(row.row_id) is None
            or row.row_id in seen_ids
        ):
            raise Ib1bObservedCandidateInventoryError(
                "REFUSED: parsed source-row identity or projection is invalid"
            )
        total_field_characters += sum(map(len, row.values))
        if total_field_characters > MAX_TOTAL_FIELD_CHARACTERS:
            raise Ib1bObservedCandidateInventoryError(
                "REFUSED: parsed source rows exceed the field-character bound"
            )
        expected = _source_row_id(
            raw_snapshot_id=identity.raw_snapshot_id,
            raw_lineage_hash=identity.raw_lineage_hash,
            raw_archive_sha256=identity.raw_archive_sha256,
            table_name=row.table_name,
            raw_member_sha256=table.raw_member_sha256,
            source_record_ordinal=row.source_record_ordinal,
            values=row.values,
            source_row_key=row.source_row_key,
        )
        if row.row_id != expected:
            raise Ib1bObservedCandidateInventoryError(
                "REFUSED: parsed source-row content hash is invalid"
            )
        seen_ids.add(row.row_id)
        row_ids_by_table[row.table_name].append(row.row_id)
        if row.table_name == "NONDERIV_TRANS.tsv":
            transaction_codes[row.row_id] = row.values[table.headers.index("TRANS_CODE")]
    for name, table in tables.items():
        ids = row_ids_by_table[name]
        if len(ids) != table.row_count or hash_payload(ids) != table.row_ids_hash:
            raise Ib1bObservedCandidateInventoryError(
                "REFUSED: parsed table row count or lineage hash is invalid"
            )
    if any(type(item) is not ParsedSecBulkAccession for item in loaded.accessions):
        raise Ib1bObservedCandidateInventoryError(
            "REFUSED: parsed accession index type is invalid"
        )
    try:
        rebuilt = _build_accessions(loaded.rows, identity.tables)
    except (SecBulkParsedSnapshotError, KeyError, TypeError) as exc:
        raise Ib1bObservedCandidateInventoryError(
            "REFUSED: parsed accession index has duplicate or orphan source rows"
        ) from exc
    if loaded.accessions != rebuilt:
        raise Ib1bObservedCandidateInventoryError(
            "REFUSED: parsed accession index omits or mislabels source rows"
        )
    return transaction_codes


def build_ib1b_observed_candidate_inventory(
    loaded_quarter: LoadedSecBulkParsedSnapshot,
) -> ObservedCandidateQuarter:
    """Prioritize a *loaded* IB-1B quarter; retain all observed 4/4-A rows.

    Exact ``P`` is selected regardless of other as-filed fields. Amendments
    and non-canonical transaction-code spellings are also selected. Other
    observations remain in the denominator with full source-row lineage,
    including no-transaction and derivative-only filings. This is complete
    only relative to observed exact bulk code-P rows, never underlying XML.
    """

    identity, tables = _validate_loaded_quarter(loaded_quarter)
    transaction_codes = _validate_rows_and_index(loaded_quarter, tables)
    records: list[ObservedCandidateAccession] = []
    for accession in loaded_quarter.accessions:
        if accession.document_type not in _FORMS:
            raise Ib1bObservedCandidateInventoryError(
                "REFUSED: parsed submission has an unexpected form type"
            )
        if accession.document_type not in _TARGET_FORMS:
            continue
        source_rows = dict(accession.table_rows)
        nond_ids = source_rows["NONDERIV_TRANS.tsv"]
        deriv_ids = source_rows.get("DERIV_TRANS.tsv", ())
        p_ids = tuple(row_id for row_id in nond_ids if transaction_codes[row_id] == "P")
        reasons: list[str] = []
        if accession.document_type == "4/A":
            reasons.append("FORM4_AMENDMENT")
        if p_ids:
            reasons.append("OBSERVED_NONDERIV_P")
        if any(
            re.fullmatch(r"[A-Z]", transaction_codes[row_id]) is None
            for row_id in nond_ids
        ):
            reasons.append("AMBIGUOUS_TRANSACTION_CODE")
        selected = bool(reasons)
        if selected:
            nonselection_reason = None
        elif not nond_ids and not deriv_ids:
            nonselection_reason = "NO_TRANSACTION_ROWS"
        elif not nond_ids:
            nonselection_reason = "DERIVATIVE_ONLY"
        else:
            nonselection_reason = "NO_OBSERVED_NONDERIV_P"
        if sum(len(ids) for _, ids in accession.table_rows) > MAX_ROWS_PER_ACCESSION:
            raise Ib1bObservedCandidateInventoryError(
                "REFUSED: accession exceeds the bounded source-row limit"
            )
        records.append(
            ObservedCandidateAccession(
                accession_number=accession.accession_number,
                document_type=accession.document_type,
                submission_row_id=accession.submission_row_id,
                source_row_ids=accession.table_rows,
                observed_p_row_ids=p_ids,
                selected_for_retrieval=selected,
                selection_reasons=tuple(reasons),
                nonselection_reason=nonselection_reason,
            )
        )
    frozen = tuple(records)
    quarter = ObservedCandidateQuarter(
        year=identity.year,
        quarter=identity.quarter,
        parsed_snapshot_id=identity.snapshot_id,
        parsed_lineage_hash=identity.lineage_hash,
        raw_snapshot_id=identity.raw_snapshot_id,
        schema_profile_id=identity.schema_profile.profile_id,
        schema_profile_sha256=identity.schema_profile_hash,
        records=frozen,
        form4_count=sum(item.document_type == "4" for item in frozen),
        form4a_count=sum(item.document_type == "4/A" for item in frozen),
        selected_count=sum(item.selected_for_retrieval for item in frozen),
        nonselected_count=sum(not item.selected_for_retrieval for item in frozen),
        content_sha256="",
    )
    quarter = replace(
        quarter,
        content_sha256=_digest(metadata=quarter._metadata(), records=frozen),
    )
    quarter.verify_digest()
    return quarter


__all__ = [
    "INVENTORY_KIND",
    "INVENTORY_VERSION",
    "Ib1bObservedCandidateInventoryError",
    "ObservedCandidateAccession",
    "ObservedCandidateQuarter",
    "build_ib1b_observed_candidate_inventory",
]
