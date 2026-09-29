"""Two-quarter, zero-I/O locator manifest for IB-1B-observed retrieval priority.

This deliberately does *not* perform the whole-population master-index join.
All observed Form 4/4-A accessions stay in the bound IB-1B denominator, but
only observed nonderivative P, amendments, and ambiguous transaction-code
filings receive retrieval locators. A nonselected filing could still contain
an XML purchase; no XML, source-completeness, PIT, or backtest claim follows.

Inputs must be exact caller-loaded IB-1B snapshots and caller-parsed master
receipts. This pure function rebinds their in-memory content and emits neither
requests nor files. The as-indexed archive-path CIK can name a filing agent;
it is never reconstructed from the IB-1B issuer CIK.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from typing import Iterable

from data.hashing import canonical_json, hash_payload
from research.insider_buying.ib1b_observed_candidate_inventory import (
    Ib1bObservedCandidateInventoryError,
    MAX_ACCESSIONS_PER_QUARTER,
    MAX_ROWS_PER_ACCESSION,
    ObservedCandidateQuarter,
    build_ib1b_observed_candidate_inventory,
)
from research.insider_buying.sec_bulk_parsed_snapshot import LoadedSecBulkParsedSnapshot
from research.insider_buying.sec_master_locator_reconciliation import (
    SecMasterLocatorReconciliationError,
    _filing_date,
)
from research.insider_buying.sec_quarter_master_index import (
    SecMasterIndexExpectedRow,
    SecMasterIndexRow,
    SecQuarterMasterIndexError,
    SecQuarterMasterIndexReceipt,
    MAX_MASTER_INDEX_ROWS,
    select_sec_master_index_subset,
)


LOCATOR_MANIFEST_KIND = "insider-buying-ib1b-observed-master-locators"
LOCATOR_MANIFEST_VERSION = 1
PERIODS = ((2022, 4), (2023, 1))
MAX_LOCATOR_JSON_BYTES = 16 * 1024
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_CIK_RE = re.compile(r"[0-9]{1,10}\Z")
_ACCESSION_RE = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_REASON_ORDER = (
    "FORM4_AMENDMENT", "OBSERVED_NONDERIV_P", "AMBIGUOUS_TRANSACTION_CODE"
)
_EMPTY_P_IDS_SHA256 = hash_payload([])


class ObservedMasterLocatorError(ValueError):
    """An observed-priority input, master path, or manifest refused."""


def _refuse(message: str) -> None:
    raise ObservedMasterLocatorError(f"REFUSED: {message}")


def _json_line(value: object, *, label: str) -> bytes:
    try:
        encoded = (canonical_json(value) + "\n").encode("utf-8")
    except (TypeError, UnicodeError, ValueError) as exc:
        raise ObservedMasterLocatorError(
            f"REFUSED: {label} cannot be represented canonically"
        ) from exc
    if len(encoded) > MAX_LOCATOR_JSON_BYTES:
        _refuse(f"{label} exceeds the per-record byte budget")
    return encoded


def _stream_digest(
    domain: str, metadata: dict[str, object], records: Iterable[object]
) -> str:
    digest = hashlib.sha256()
    digest.update((domain + "\n").encode("ascii"))
    digest.update(_json_line(metadata, label="locator metadata"))
    for record in records:
        digest.update(_json_line(record, label="locator record"))
    return digest.hexdigest()


@dataclass(frozen=True)
class ObservedMasterLocatorQuarterInput:
    candidates: ObservedCandidateQuarter
    parsed_snapshot: LoadedSecBulkParsedSnapshot
    master_index: SecQuarterMasterIndexReceipt


@dataclass(frozen=True)
class ObservedMasterLocator:
    accession_number: str
    form_type: str
    filing_date: str
    issuer_cik: str
    archive_path: str
    submission_row_id: str
    selection_reasons: tuple[str, ...]
    observed_p_row_count: int
    observed_p_row_ids_sha256: str
    ambiguous_code_quarantine: bool

    def to_payload(self) -> dict[str, object]:
        if (
            type(self) is not ObservedMasterLocator
            or type(self.accession_number) is not str
            or _ACCESSION_RE.fullmatch(self.accession_number) is None
            or type(self.form_type) is not str
            or self.form_type not in {"4", "4/A"}
            or type(self.filing_date) is not str
            or type(self.issuer_cik) is not str
            or _CIK_RE.fullmatch(self.issuer_cik) is None
            or int(self.issuer_cik) == 0
            or type(self.archive_path) is not str
            or type(self.submission_row_id) is not str
            or _HASH_RE.fullmatch(self.submission_row_id) is None
            or type(self.selection_reasons) is not tuple
            or not self.selection_reasons
            or self.selection_reasons != tuple(
                reason for reason in _REASON_ORDER if reason in self.selection_reasons
            )
            or (self.form_type == "4/A")
            != ("FORM4_AMENDMENT" in self.selection_reasons)
            or type(self.observed_p_row_count) is not int
            or not 0 <= self.observed_p_row_count <= MAX_ROWS_PER_ACCESSION
            or (self.observed_p_row_count > 0)
            != ("OBSERVED_NONDERIV_P" in self.selection_reasons)
            or type(self.observed_p_row_ids_sha256) is not str
            or _HASH_RE.fullmatch(self.observed_p_row_ids_sha256) is None
            or (self.observed_p_row_count == 0
                and self.observed_p_row_ids_sha256 != _EMPTY_P_IDS_SHA256)
            or type(self.ambiguous_code_quarantine) is not bool
            or self.ambiguous_code_quarantine
            != ("AMBIGUOUS_TRANSACTION_CODE" in self.selection_reasons)
        ):
            _refuse("selected locator identity, reason, or source-row binding is invalid")
        try:
            SecMasterIndexRow(
                self.accession_number, self.form_type,
                self.filing_date, self.archive_path
            )
        except SecQuarterMasterIndexError as exc:
            raise ObservedMasterLocatorError(
                "REFUSED: selected locator archive path is invalid"
            ) from exc
        return {
            "accession_number": self.accession_number,
            "form_type": self.form_type,
            "filing_date": self.filing_date,
            "issuer_cik": self.issuer_cik,
            "archive_path": self.archive_path,
            "submission_row_id": self.submission_row_id,
            "selection_reasons": list(self.selection_reasons),
            "observed_p_row_count": self.observed_p_row_count,
            "observed_p_row_ids_sha256": self.observed_p_row_ids_sha256,
            "ambiguous_code_quarantine": self.ambiguous_code_quarantine,
        }


@dataclass(frozen=True)
class ObservedMasterLocatorQuarter:
    period: str
    parsed_snapshot_id: str
    parsed_lineage_hash: str
    raw_snapshot_id: str
    candidate_content_sha256: str
    master_source_sha256: str
    master_receipt_sha256: str
    master_index_form4_row_count: int
    form4_count: int
    form4a_count: int
    selected_count: int
    nonselected_count: int
    ambiguous_code_quarantine_count: int
    locators: tuple[ObservedMasterLocator, ...]
    content_sha256: str

    def _metadata(self) -> dict[str, object]:
        return {
            "kind": LOCATOR_MANIFEST_KIND,
            "version": LOCATOR_MANIFEST_VERSION,
            "source_scope": "IB1B_OBSERVED_NONCANONICAL",
            "period": self.period,
            "parsed_snapshot_id": self.parsed_snapshot_id,
            "parsed_lineage_hash": self.parsed_lineage_hash,
            "raw_snapshot_id": self.raw_snapshot_id,
            "candidate_content_sha256": self.candidate_content_sha256,
            "master_source_sha256": self.master_source_sha256,
            "master_receipt_sha256": self.master_receipt_sha256,
            "master_index_form4_row_count": self.master_index_form4_row_count,
            "form4_count": self.form4_count,
            "form4a_count": self.form4a_count,
            "selected_count": self.selected_count,
            "nonselected_count": self.nonselected_count,
            "ambiguous_code_quarantine_count": self.ambiguous_code_quarantine_count,
            "nonselected_master_paths_validated": False,
            "master_index_completeness_verified": False,
            "xml_completeness_verified": False,
            "canonical": False,
            "point_in_time_data": False,
            "source_authenticity_verified": False,
            "outcome_looks": 0,
            "qc_jobs": 0,
        }

    def verify_digest(self) -> None:
        if (
            type(self) is not ObservedMasterLocatorQuarter
            or type(self.period) is not str
            or self.period not in {"2022Q4", "2023Q1"}
            or type(self.parsed_snapshot_id) is not str
            or any(type(value) is not str or _HASH_RE.fullmatch(value) is None
                   for value in (
                       self.parsed_lineage_hash, self.candidate_content_sha256,
                       self.master_source_sha256, self.master_receipt_sha256,
                       self.content_sha256,
                   ))
            or self.parsed_snapshot_id != (
                f"sec-insider-parsed-{self.period.lower()}-"
                f"{self.parsed_lineage_hash[:16]}"
            )
            or type(self.raw_snapshot_id) is not str
            or re.fullmatch(
                rf"sec-insider-bulk-{self.period.lower()}-[0-9a-f]{{16}}\Z",
                self.raw_snapshot_id,
            ) is None
            or any(type(value) is not int or not 0 <= value <= MAX_ACCESSIONS_PER_QUARTER
                   for value in (
                       self.form4_count, self.form4a_count,
                       self.selected_count, self.nonselected_count,
                       self.ambiguous_code_quarantine_count,
                   ))
            or type(self.master_index_form4_row_count) is not int
            or not self.selected_count <= self.master_index_form4_row_count <= MAX_MASTER_INDEX_ROWS
            or self.form4_count + self.form4a_count
            != self.selected_count + self.nonselected_count
            or self.form4_count + self.form4a_count > MAX_ACCESSIONS_PER_QUARTER
            or type(self.locators) is not tuple
            or len(self.locators) != self.selected_count
            or any(type(item) is not ObservedMasterLocator for item in self.locators)
            or tuple(item.accession_number for item in self.locators)
            != tuple(sorted({item.accession_number for item in self.locators}))
            or len({item.submission_row_id for item in self.locators}) != len(self.locators)
            or sum(item.ambiguous_code_quarantine for item in self.locators)
            != self.ambiguous_code_quarantine_count
            or sum(item.form_type == "4" for item in self.locators) > self.form4_count
            or sum(item.form_type == "4/A" for item in self.locators) > self.form4a_count
        ):
            _refuse("quarter locator digest or denominator changed")
        for item in self.locators:
            item.to_payload()
            try:
                _filing_date(item.filing_date,
                             year=int(self.period[:4]), quarter=int(self.period[-1]))
            except SecMasterLocatorReconciliationError as exc:
                raise ObservedMasterLocatorError(
                    "REFUSED: selected locator filing date is outside its quarter"
                ) from exc
        expected = _stream_digest(
            LOCATOR_MANIFEST_KIND + "/quarter-v1",
            self._metadata(),
            (item.to_payload() for item in self.locators),
        )
        if expected != self.content_sha256:
            _refuse("quarter locator digest or denominator changed")

@dataclass(frozen=True)
class ObservedMasterLocatorManifest:
    quarters: tuple[ObservedMasterLocatorQuarter, ...]
    form4_count: int
    form4a_count: int
    selected_count: int
    nonselected_count: int
    ambiguous_code_quarantine_count: int
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
            "kind": LOCATOR_MANIFEST_KIND,
            "version": LOCATOR_MANIFEST_VERSION,
            "source_scope": "IB1B_OBSERVED_NONCANONICAL",
            "periods": ["2022Q4", "2023Q1"],
            "form4_count": self.form4_count,
            "form4a_count": self.form4a_count,
            "selected_count": self.selected_count,
            "nonselected_count": self.nonselected_count,
            "ambiguous_code_quarantine_count": self.ambiguous_code_quarantine_count,
            "nonselected_master_paths_validated": False,
            "master_index_completeness_verified": False,
            "xml_completeness_verified": False,
            "canonical": False,
            "point_in_time_data": False,
            "source_authenticity_verified": False,
            "outcome_looks": 0,
            "qc_jobs": 0,
        }

    def verify_digest(self) -> None:
        if (
            type(self) is not ObservedMasterLocatorManifest
            or type(self.quarters) is not tuple
            or len(self.quarters) != 2
            or any(type(item) is not ObservedMasterLocatorQuarter for item in self.quarters)
            or tuple(item.period for item in self.quarters) != ("2022Q4", "2023Q1")
            or any(type(value) is not int or value < 0 for value in (
                self.form4_count, self.form4a_count, self.selected_count,
                self.nonselected_count, self.ambiguous_code_quarantine_count,
            ))
            or self.form4_count != sum(item.form4_count for item in self.quarters)
            or self.form4a_count != sum(item.form4a_count for item in self.quarters)
            or self.selected_count != sum(item.selected_count for item in self.quarters)
            or self.nonselected_count != sum(item.nonselected_count for item in self.quarters)
            or self.ambiguous_code_quarantine_count != sum(
                item.ambiguous_code_quarantine_count for item in self.quarters
            )
            or type(self.content_sha256) is not str
            or _HASH_RE.fullmatch(self.content_sha256) is None
        ):
            _refuse("two-quarter locator digest or counts changed")
        for quarter in self.quarters:
            quarter.verify_digest()
        expected = _stream_digest(
            LOCATOR_MANIFEST_KIND + "/two-quarter-v1",
            self._metadata(),
            ({"period": quarter.period, "content_sha256": quarter.content_sha256}
             for quarter in self.quarters),
        )
        if expected != self.content_sha256:
            _refuse("two-quarter locator digest or counts changed")


def _build_quarter(
    item: ObservedMasterLocatorQuarterInput,
    *,
    year: int,
    quarter: int,
) -> ObservedMasterLocatorQuarter:
    if (
        type(item) is not ObservedMasterLocatorQuarterInput
        or type(item.candidates) is not ObservedCandidateQuarter
        or type(item.parsed_snapshot) is not LoadedSecBulkParsedSnapshot
        or type(item.master_index) is not SecQuarterMasterIndexReceipt
        or (item.candidates.year, item.candidates.quarter) != (year, quarter)
    ):
        _refuse("candidate, snapshot, or master quarter is missing or out of order")
    try:
        item.candidates.verify_digest()
    except Ib1bObservedCandidateInventoryError as exc:
        raise ObservedMasterLocatorError(
            "REFUSED: candidate inventory digest changed"
        ) from exc
    try:
        rebuilt = build_ib1b_observed_candidate_inventory(item.parsed_snapshot)
    except (Ib1bObservedCandidateInventoryError, AttributeError, TypeError) as exc:
        raise ObservedMasterLocatorError(
            "REFUSED: parsed snapshot cannot rebind candidate inventory"
        ) from exc
    if rebuilt != item.candidates:
        _refuse("candidate inventory does not match exact parsed snapshot")
    identity = item.parsed_snapshot.identity
    master = item.master_index
    try:
        master.__post_init__()
    except SecQuarterMasterIndexError as exc:
        raise ObservedMasterLocatorError(
            "REFUSED: master receipt changed after parsing"
        ) from exc
    if (master.year, master.quarter) != (year, quarter):
        _refuse("master quarter does not match candidate and parsed snapshot")
    submission_table = next(
        table for table in identity.tables if table.table_name == "SUBMISSION.tsv"
    )
    positions = {name: submission_table.headers.index(name) for name in (
        "DOCUMENT_TYPE", "FILING_DATE", "ISSUERCIK"
    )}
    selected_records = tuple(
        candidate for candidate in rebuilt.records if candidate.selected_for_retrieval
    )
    selected_ids = {candidate.submission_row_id for candidate in selected_records}
    submission_rows = {
        row.row_id: row for row in item.parsed_snapshot.rows
        if row.table_name == "SUBMISSION.tsv" and row.row_id in selected_ids
    }
    if len(submission_rows) != len(selected_records):
        _refuse("selected candidate submission source row is unavailable")
    expected_rows: list[SecMasterIndexExpectedRow] = []
    for candidate in selected_records:
        row = submission_rows[candidate.submission_row_id]
        if (
            row.accession_number != candidate.accession_number
            or row.values[positions["DOCUMENT_TYPE"]] != candidate.document_type
        ):
            _refuse("candidate form or accession differs from source submission")
        try:
            filing_date = _filing_date(
                row.values[positions["FILING_DATE"]], year=year, quarter=quarter
            )
        except SecMasterLocatorReconciliationError as exc:
            raise ObservedMasterLocatorError(
                "REFUSED: selected source filing date is invalid"
            ) from exc
        issuer_cik = row.values[positions["ISSUERCIK"]]
        try:
            expected_rows.append(SecMasterIndexExpectedRow(
                candidate.accession_number, candidate.document_type,
                filing_date, issuer_cik
            ))
        except SecQuarterMasterIndexError as exc:
            raise ObservedMasterLocatorError(
                "REFUSED: selected source issuer CIK or identity is invalid"
            ) from exc
    try:
        selected_master_rows = (
            select_sec_master_index_subset(master, tuple(expected_rows))
            if expected_rows else ()
        )
    except SecQuarterMasterIndexError as exc:
        raise ObservedMasterLocatorError(str(exc)) from exc
    locators = tuple(
        ObservedMasterLocator(
            accession_number=candidate.accession_number,
            form_type=candidate.document_type,
            filing_date=expected.filing_date,
            issuer_cik=expected.issuer_cik,
            archive_path=index_row.archive_path,
            submission_row_id=candidate.submission_row_id,
            selection_reasons=candidate.selection_reasons,
            observed_p_row_count=len(candidate.observed_p_row_ids),
            observed_p_row_ids_sha256=hash_payload(list(candidate.observed_p_row_ids)),
            ambiguous_code_quarantine=(
                "AMBIGUOUS_TRANSACTION_CODE" in candidate.selection_reasons
            ),
        )
        for candidate, expected, index_row in zip(
            selected_records, expected_rows, selected_master_rows, strict=True
        )
    )
    period = f"{year:04d}Q{quarter}"
    provisional = ObservedMasterLocatorQuarter(
        period=period,
        parsed_snapshot_id=identity.snapshot_id,
        parsed_lineage_hash=identity.lineage_hash,
        raw_snapshot_id=identity.raw_snapshot_id,
        candidate_content_sha256=rebuilt.content_sha256,
        master_source_sha256=master.source_sha256,
        master_receipt_sha256=master.receipt_sha256,
        master_index_form4_row_count=len(master.rows),
        form4_count=rebuilt.form4_count,
        form4a_count=rebuilt.form4a_count,
        selected_count=rebuilt.selected_count,
        nonselected_count=rebuilt.nonselected_count,
        ambiguous_code_quarantine_count=sum(
            locator.ambiguous_code_quarantine for locator in locators
        ),
        locators=locators,
        content_sha256="",
    )
    result = replace(
        provisional,
        content_sha256=_stream_digest(
            LOCATOR_MANIFEST_KIND + "/quarter-v1",
            provisional._metadata(),
            (locator.to_payload() for locator in locators),
        ),
    )
    result.verify_digest()
    return result


def build_ib1b_observed_master_locator_manifest(
    quarters: Iterable[ObservedMasterLocatorQuarterInput],
) -> ObservedMasterLocatorManifest:
    """Bind only 2022Q4/2023Q1, one quarter at a time, with no real I/O.

    Every selected priority must resolve to one exact as-indexed path via the
    existing subset selector. Nonselected master coverage is deliberately not
    verified and cannot be mistaken for an 82-quarter or canonical inventory.
    """
    try:
        stream = iter(quarters)
    except TypeError as exc:
        raise ObservedMasterLocatorError(
            "REFUSED: exact two-quarter locator inputs are required"
        ) from exc
    built = []
    for year, quarter in PERIODS:
        item = next(stream, None)
        if item is None:
            _refuse("one of the two required quarter inputs is missing")
        built.append(_build_quarter(item, year=year, quarter=quarter))
    if next(stream, None) is not None:
        _refuse("more than the two approved quarter inputs were supplied")
    frozen = tuple(built)
    provisional = ObservedMasterLocatorManifest(
        quarters=frozen,
        form4_count=sum(item.form4_count for item in frozen),
        form4a_count=sum(item.form4a_count for item in frozen),
        selected_count=sum(item.selected_count for item in frozen),
        nonselected_count=sum(item.nonselected_count for item in frozen),
        ambiguous_code_quarantine_count=sum(
            item.ambiguous_code_quarantine_count for item in frozen
        ),
        content_sha256="",
    )
    result = replace(
        provisional,
        content_sha256=_stream_digest(
            LOCATOR_MANIFEST_KIND + "/two-quarter-v1",
            provisional._metadata(),
            ({"period": item.period, "content_sha256": item.content_sha256}
             for item in frozen),
        ),
    )
    result.verify_digest()
    return result


__all__ = [
    "LOCATOR_MANIFEST_KIND",
    "LOCATOR_MANIFEST_VERSION",
    "ObservedMasterLocatorError",
    "ObservedMasterLocatorQuarterInput",
    "ObservedMasterLocator",
    "ObservedMasterLocatorQuarter",
    "ObservedMasterLocatorManifest",
    "build_ib1b_observed_master_locator_manifest",
]
