"""Pure two-quarter locator manifest for *all* observed Form 4/4-A parents.

This source-relative join is deliberately distinct from the 9,337-filing
observed-P retrieval priority. It checks every Form 4/4-A accession in the
caller-loaded 2022Q4 and 2023Q1 IB-1B snapshots against each supplied master
index, including filings with no observed bulk-data purchase code. Master
archive-path CIKs can be filing agents; they are locators, not issuer proof.

The manifest is a bounded in-memory, streaming-hashed preparation artifact.
It performs no I/O and proves neither SEC origin nor complete XML, acceptance
time, point-in-time identity, a strategy signal, or backtest authority. A
consumer must rebuild it against the exact independently loaded source bytes;
an internally coherent typed object or digest alone is not source evidence.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from typing import Iterable, Iterator

from data.hashing import canonical_json, hash_payload
from research.insider_buying.ib1b_observed_candidate_inventory import (
    Ib1bObservedCandidateInventoryError,
    MAX_ACCESSIONS_PER_QUARTER,
    build_ib1b_observed_candidate_inventory,
)
from research.insider_buying.sec_bulk_parsed_snapshot import (
    LoadedSecBulkParsedSnapshot,
)
from research.insider_buying.sec_master_locator_reconciliation import (
    SecMasterLocatorReconciliationError,
    _filing_date,
)
from research.insider_buying.sec_quarter_master_index import (
    MAX_MASTER_INDEX_ROWS,
    SecMasterIndexExpectedRow,
    SecMasterIndexRow,
    SecQuarterMasterIndexError,
    SecQuarterMasterIndexReceipt,
    join_exact_sec_master_inventory,
)


ALL_FORM4_LOCATOR_KIND = "insider-buying-ib1b-all-form4-parent-locators"
ALL_FORM4_LOCATOR_VERSION = 1
ALL_FORM4_LOCATOR_PERIODS = ((2022, 4), (2023, 1))
MAX_ALL_FORM4_LOCATOR_JSON_BYTES = 16 * 1024
_PERIODS = ("2022Q4", "2023Q1")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_CIK = re.compile(r"[0-9]{1,10}\Z")
_RAW_ID = re.compile(r"sec-insider-bulk-[0-9]{4}q[1-4]-[0-9a-f]{16}\Z")


class AllForm4ParentLocatorError(ValueError):
    """An exact full-population locator join or digest refused."""


def _refuse(reason: str) -> None:
    raise AllForm4ParentLocatorError(f"REFUSED: {reason}")


def _line(value: object, *, label: str) -> bytes:
    try:
        raw = (canonical_json(value) + "\n").encode("utf-8")
    except (TypeError, UnicodeError, ValueError) as exc:
        raise AllForm4ParentLocatorError(
            f"REFUSED: {label} cannot be encoded canonically"
        ) from exc
    if len(raw) > MAX_ALL_FORM4_LOCATOR_JSON_BYTES:
        _refuse(f"{label} exceeds the bounded line budget")
    return raw


def _digest(domain: str, metadata: dict[str, object], records: Iterable[object]) -> str:
    digest = hashlib.sha256()
    digest.update((domain + "\n").encode("ascii"))
    digest.update(_line(metadata, label="manifest metadata"))
    for record in records:
        digest.update(_line(record, label="locator record"))
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class AllForm4ParentQuarterInput:
    parsed_snapshot: LoadedSecBulkParsedSnapshot
    master_index: SecQuarterMasterIndexReceipt


@dataclass(frozen=True, slots=True)
class AllForm4ParentLocator:
    period: str
    accession_number: str
    form_type: str
    filing_date: str
    issuer_cik: str
    archive_path: str
    submission_row_id: str
    candidate_record_sha256: str

    def to_payload(self) -> dict[str, str]:
        if (
            type(self) is not AllForm4ParentLocator
            or type(self.period) is not str
            or self.period not in _PERIODS
            or type(self.accession_number) is not str
            or _ACCESSION.fullmatch(self.accession_number) is None
            or type(self.form_type) is not str
            or self.form_type not in {"4", "4/A"}
            or type(self.filing_date) is not str
            or type(self.issuer_cik) is not str
            or _CIK.fullmatch(self.issuer_cik) is None
            or int(self.issuer_cik) == 0
            or type(self.archive_path) is not str
            or type(self.submission_row_id) is not str
            or _HASH.fullmatch(self.submission_row_id) is None
            or type(self.candidate_record_sha256) is not str
            or _HASH.fullmatch(self.candidate_record_sha256) is None
        ):
            _refuse("locator fields are malformed")
        try:
            _filing_date(
                self.filing_date,
                year=int(self.period[:4]),
                quarter=int(self.period[-1]),
            )
            SecMasterIndexExpectedRow(
                self.accession_number, self.form_type,
                self.filing_date, self.issuer_cik,
            )
            SecMasterIndexRow(
                self.accession_number, self.form_type,
                self.filing_date, self.archive_path,
            )
        except (SecMasterLocatorReconciliationError, SecQuarterMasterIndexError) as exc:
            raise AllForm4ParentLocatorError(
                "REFUSED: locator source identity or archive path is invalid"
            ) from exc
        return {
            "period": self.period,
            "accession_number": self.accession_number,
            "form_type": self.form_type,
            "filing_date": self.filing_date,
            "issuer_cik": self.issuer_cik,
            "archive_path": self.archive_path,
            "submission_row_id": self.submission_row_id,
            "candidate_record_sha256": self.candidate_record_sha256,
        }


@dataclass(frozen=True, slots=True)
class AllForm4ParentLocatorQuarter:
    period: str
    parsed_snapshot_id: str
    parsed_lineage_hash: str
    raw_snapshot_id: str
    candidate_inventory_sha256: str
    master_source_sha256: str
    master_receipt_sha256: str
    master_index_form4_row_count: int
    form4_count: int
    form4a_count: int
    locators: tuple[AllForm4ParentLocator, ...]
    content_sha256: str

    @property
    def total_accessions(self) -> int:
        return self.form4_count + self.form4a_count

    def _metadata(self) -> dict[str, object]:
        return {
            "kind": ALL_FORM4_LOCATOR_KIND,
            "version": ALL_FORM4_LOCATOR_VERSION,
            "source_scope": "IB1B_FULL_FORM4_MASTER_RELATIVE_NONCANONICAL",
            "period": self.period,
            "parsed_snapshot_id": self.parsed_snapshot_id,
            "parsed_lineage_hash": self.parsed_lineage_hash,
            "raw_snapshot_id": self.raw_snapshot_id,
            "candidate_inventory_sha256": self.candidate_inventory_sha256,
            "master_source_sha256": self.master_source_sha256,
            "master_receipt_sha256": self.master_receipt_sha256,
            "master_index_form4_row_count": self.master_index_form4_row_count,
            "form4_count": self.form4_count,
            "form4a_count": self.form4a_count,
            "total_accessions": self.total_accessions,
            "whole_index_join_relative_to_supplied_bytes": True,
            "complete_parent_bytes_acquired": False,
            "source_authenticity_verified": False,
            "acceptance_metadata_verified": False,
            "xml_completeness_verified": False,
            "canonical": False,
            "point_in_time_data": False,
            "outcome_looks": 0,
            "qc_jobs": 0,
        }

    def verify_digest(self) -> None:
        if (
            type(self) is not AllForm4ParentLocatorQuarter
            or type(self.period) is not str
            or self.period not in _PERIODS
            or type(self.parsed_snapshot_id) is not str
            or type(self.raw_snapshot_id) is not str
            or _RAW_ID.fullmatch(self.raw_snapshot_id) is None
            or any(
                type(value) is not str or _HASH.fullmatch(value) is None
                for value in (
                    self.parsed_lineage_hash,
                    self.candidate_inventory_sha256,
                    self.master_source_sha256,
                    self.master_receipt_sha256,
                    self.content_sha256,
                )
            )
            or self.parsed_snapshot_id != (
                f"sec-insider-parsed-{self.period.lower()}-"
                f"{self.parsed_lineage_hash[:16]}"
            )
            or not self.raw_snapshot_id.startswith(
                f"sec-insider-bulk-{self.period.lower()}-"
            )
            or type(self.master_index_form4_row_count) is not int
            or not 0 <= self.master_index_form4_row_count <= MAX_MASTER_INDEX_ROWS
            or any(
                type(value) is not int or not 0 <= value <= MAX_ACCESSIONS_PER_QUARTER
                for value in (self.form4_count, self.form4a_count)
            )
            or self.total_accessions > MAX_ACCESSIONS_PER_QUARTER
            or type(self.locators) is not tuple
            or len(self.locators) != self.total_accessions
            or len(self.locators) > self.master_index_form4_row_count
            or any(type(row) is not AllForm4ParentLocator for row in self.locators)
        ):
            _refuse("quarter locator digest, source identity, or counts changed")
        for row in self.locators:
            if row.period != self.period:
                _refuse("quarter locator period changed")
            row.to_payload()
        if (
            tuple(row.accession_number for row in self.locators)
            != tuple(sorted({row.accession_number for row in self.locators}))
            or len({row.submission_row_id for row in self.locators}) != len(self.locators)
            or sum(row.form_type == "4" for row in self.locators) != self.form4_count
            or sum(row.form_type == "4/A" for row in self.locators) != self.form4a_count
        ):
            _refuse("quarter locator digest, source identity, or counts changed")
        expected = _digest(
            ALL_FORM4_LOCATOR_KIND + "/quarter-v1",
            self._metadata(),
            (row.to_payload() for row in self.locators),
        )
        if expected != self.content_sha256:
            _refuse("quarter locator digest, source identity, or counts changed")


@dataclass(frozen=True, slots=True)
class AllForm4ParentLocatorManifest:
    quarters: tuple[AllForm4ParentLocatorQuarter, ...]
    form4_count: int
    form4a_count: int
    content_sha256: str

    @property
    def total_accessions(self) -> int:
        return self.form4_count + self.form4a_count

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
    def source_authenticity_verified(self) -> bool:
        return False

    @property
    def outcome_looks(self) -> int:
        return 0

    @property
    def qc_jobs(self) -> int:
        return 0

    def _metadata(self) -> dict[str, object]:
        return {
            "kind": ALL_FORM4_LOCATOR_KIND,
            "version": ALL_FORM4_LOCATOR_VERSION,
            "source_scope": "IB1B_FULL_FORM4_MASTER_RELATIVE_NONCANONICAL",
            "periods": list(_PERIODS),
            "form4_count": self.form4_count,
            "form4a_count": self.form4a_count,
            "total_accessions": self.total_accessions,
            "whole_index_join_relative_to_supplied_bytes": True,
            "complete_parent_bytes_acquired": False,
            "source_authenticity_verified": False,
            "acceptance_metadata_verified": False,
            "xml_completeness_verified": False,
            "canonical": False,
            "point_in_time_data": False,
            "outcome_looks": 0,
            "qc_jobs": 0,
        }

    def verify_digest(self) -> None:
        if (
            type(self) is not AllForm4ParentLocatorManifest
            or type(self.quarters) is not tuple
            or len(self.quarters) != 2
            or any(type(row) is not AllForm4ParentLocatorQuarter for row in self.quarters)
            or tuple(row.period for row in self.quarters) != _PERIODS
            or type(self.form4_count) is not int
            or type(self.form4a_count) is not int
            or self.form4_count < 0
            or self.form4a_count < 0
            or self.form4_count != sum(row.form4_count for row in self.quarters)
            or self.form4a_count != sum(row.form4a_count for row in self.quarters)
            or self.total_accessions > 2 * MAX_ACCESSIONS_PER_QUARTER
            or type(self.content_sha256) is not str
            or _HASH.fullmatch(self.content_sha256) is None
        ):
            _refuse("two-quarter locator digest or counts changed")
        for quarter in self.quarters:
            quarter.verify_digest()
        if ({row.accession_number for row in self.quarters[0].locators}
                & {row.accession_number for row in self.quarters[1].locators}):
            _refuse("cross-quarter accession duplicate")
        expected = _digest(
            ALL_FORM4_LOCATOR_KIND + "/two-quarter-v1",
            self._metadata(),
            ({"period": quarter.period, "content_sha256": quarter.content_sha256}
             for quarter in self.quarters),
        )
        if expected != self.content_sha256:
            _refuse("two-quarter locator digest or counts changed")

    def iter_locators(self) -> Iterator[AllForm4ParentLocator]:
        """Yield in period/accession order after checking the bounded manifest."""
        self.verify_digest()
        for quarter in self.quarters:
            yield from quarter.locators


def _build_quarter(
    item: AllForm4ParentQuarterInput, *, year: int, quarter: int
) -> AllForm4ParentLocatorQuarter:
    if (
        type(item) is not AllForm4ParentQuarterInput
        or type(item.parsed_snapshot) is not LoadedSecBulkParsedSnapshot
        or type(item.master_index) is not SecQuarterMasterIndexReceipt
    ):
        _refuse("parsed snapshot or master quarter input is malformed")
    try:
        candidates = build_ib1b_observed_candidate_inventory(item.parsed_snapshot)
        candidates.verify_digest()
    except (Ib1bObservedCandidateInventoryError, AttributeError, TypeError) as exc:
        raise AllForm4ParentLocatorError(
            "REFUSED: parsed snapshot cannot rebuild the full Form 4 inventory"
        ) from exc
    if (candidates.year, candidates.quarter) != (year, quarter):
        _refuse("parsed snapshot quarter is missing or out of order")
    master = item.master_index
    try:
        master.__post_init__()
    except SecQuarterMasterIndexError as exc:
        raise AllForm4ParentLocatorError("REFUSED: master receipt changed") from exc
    if (master.year, master.quarter) != (year, quarter):
        _refuse("master quarter is missing or out of order")
    tables = [
        table for table in item.parsed_snapshot.identity.tables
        if table.table_name == "SUBMISSION.tsv"
    ]
    if len(tables) != 1:
        _refuse("parsed snapshot lacks one exact SUBMISSION table")
    table = tables[0]
    try:
        positions = {
            name: table.headers.index(name)
            for name in ("DOCUMENT_TYPE", "FILING_DATE", "ISSUERCIK")
        }
    except ValueError as exc:
        raise AllForm4ParentLocatorError(
            "REFUSED: SUBMISSION source identity fields are absent"
        ) from exc
    wanted_ids = {record.submission_row_id for record in candidates.records}
    submission_rows = {
        row.row_id: row for row in item.parsed_snapshot.rows
        if row.table_name == "SUBMISSION.tsv" and row.row_id in wanted_ids
    }
    if len(submission_rows) != len(candidates.records):
        _refuse("candidate submission source row is unavailable")
    expected_rows: list[SecMasterIndexExpectedRow] = []
    for candidate in candidates.records:
        row = submission_rows[candidate.submission_row_id]
        if (
            row.accession_number != candidate.accession_number
            or row.values[positions["DOCUMENT_TYPE"]] != candidate.document_type
        ):
            _refuse("candidate accession or form differs from source submission")
        try:
            filing_date = _filing_date(
                row.values[positions["FILING_DATE"]], year=year, quarter=quarter
            )
            expected_rows.append(SecMasterIndexExpectedRow(
                candidate.accession_number, candidate.document_type,
                filing_date, row.values[positions["ISSUERCIK"]],
            ))
        except (SecMasterLocatorReconciliationError, SecQuarterMasterIndexError) as exc:
            raise AllForm4ParentLocatorError(
                "REFUSED: source filing date or issuer CIK is invalid"
            ) from exc
    if expected_rows:
        try:
            indexed_rows = join_exact_sec_master_inventory(master, tuple(expected_rows))
        except SecQuarterMasterIndexError as exc:
            raise AllForm4ParentLocatorError(str(exc)) from exc
    else:
        # The shared exact-join API intentionally refuses an empty expected
        # inventory. Preserve equality at that boundary without bypassing a
        # nonempty master receipt for a zero-Form-4 synthetic quarter.
        if master.rows:
            _refuse("master contains Form 4 rows absent from source inventory")
        indexed_rows = ()
    period = f"{year:04d}Q{quarter}"
    locators = tuple(
        AllForm4ParentLocator(
            period=period,
            accession_number=candidate.accession_number,
            form_type=candidate.document_type,
            filing_date=expected.filing_date,
            issuer_cik=expected.issuer_cik,
            archive_path=indexed.archive_path,
            submission_row_id=candidate.submission_row_id,
            candidate_record_sha256=hash_payload(candidate.to_payload()),
        )
        for candidate, expected, indexed in zip(
            candidates.records, expected_rows, indexed_rows, strict=True
        )
    )
    provisional = AllForm4ParentLocatorQuarter(
        period=period,
        parsed_snapshot_id=item.parsed_snapshot.identity.snapshot_id,
        parsed_lineage_hash=item.parsed_snapshot.identity.lineage_hash,
        raw_snapshot_id=item.parsed_snapshot.identity.raw_snapshot_id,
        candidate_inventory_sha256=candidates.content_sha256,
        master_source_sha256=master.source_sha256,
        master_receipt_sha256=master.receipt_sha256,
        master_index_form4_row_count=len(master.rows),
        form4_count=candidates.form4_count,
        form4a_count=candidates.form4a_count,
        locators=locators,
        content_sha256="",
    )
    result = replace(
        provisional,
        content_sha256=_digest(
            ALL_FORM4_LOCATOR_KIND + "/quarter-v1",
            provisional._metadata(),
            (row.to_payload() for row in locators),
        ),
    )
    result.verify_digest()
    return result


def build_ib1b_all_form4_parent_locator_manifest(
    quarters: Iterable[AllForm4ParentQuarterInput],
) -> AllForm4ParentLocatorManifest:
    """Join every 4/4-A filing in exactly 2022Q4 and 2023Q1; perform no I/O."""
    try:
        stream = iter(quarters)
    except TypeError as exc:
        raise AllForm4ParentLocatorError(
            "REFUSED: exact two-quarter inputs are required"
        ) from exc
    built: list[AllForm4ParentLocatorQuarter] = []
    for year, quarter in ALL_FORM4_LOCATOR_PERIODS:
        item = next(stream, None)
        if item is None:
            _refuse("one of the two required quarter inputs is missing")
        built.append(_build_quarter(item, year=year, quarter=quarter))
    if next(stream, None) is not None:
        _refuse("more than the two approved quarter inputs were supplied")
    frozen = tuple(built)
    provisional = AllForm4ParentLocatorManifest(
        quarters=frozen,
        form4_count=sum(item.form4_count for item in frozen),
        form4a_count=sum(item.form4a_count for item in frozen),
        content_sha256="",
    )
    result = replace(
        provisional,
        content_sha256=_digest(
            ALL_FORM4_LOCATOR_KIND + "/two-quarter-v1",
            provisional._metadata(),
            ({"period": item.period, "content_sha256": item.content_sha256}
             for item in frozen),
        ),
    )
    result.verify_digest()
    return result


__all__ = [
    "ALL_FORM4_LOCATOR_KIND",
    "ALL_FORM4_LOCATOR_VERSION",
    "ALL_FORM4_LOCATOR_PERIODS",
    "AllForm4ParentLocatorError",
    "AllForm4ParentQuarterInput",
    "AllForm4ParentLocator",
    "AllForm4ParentLocatorQuarter",
    "AllForm4ParentLocatorManifest",
    "build_ib1b_all_form4_parent_locator_manifest",
]
