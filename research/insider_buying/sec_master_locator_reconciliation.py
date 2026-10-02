"""Pure, noncanonical reconciliation of ZIP targets to quarterly master locators.

The caller supplies a validated 82-ZIP census, one caller-loaded IB-1B parsed
snapshot per quarter, and one parsed EDGAR master index per quarter. This module
performs no I/O. It rechecks the supplied identities, derives target tuples
from hash-bound SUBMISSION rows, and compares the *entire* Form 4/4-A master
inventory. A discrepancy leaves the whole report unavailable, with no locator
inventory digest; it never returns a partial list of usable filings.

An internally coherent parsed snapshot or index is not proof of SEC origin,
historic publication, complete XML, acceptance metadata, PIT, or permission to
download or backtest. The existing independently validated loaders remain the
caller's responsibility. The result retains aggregate diagnostics only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from data.hashing import hash_payload
from research.insider_buying.sec_bulk_parsed_snapshot import (
    MAX_ROWS_PER_TABLE,
    MAX_TOTAL_ROWS,
    LoadedSecBulkParsedSnapshot,
    ParsedSecBulkAccession,
    ParsedSecBulkRow,
    ParsedSecBulkTableIdentity,
    SecBulkParsedSnapshotError,
    SecBulkParsedSnapshotIdentity,
    SecTsvSchemaProfile,
    _source_row_id,
)
from research.insider_buying.sec_quarter_master_index import (
    SecMasterIndexExpectedRow,
    SecMasterIndexRow,
    SecQuarterMasterIndexError,
    SecQuarterMasterIndexReceipt,
    join_exact_sec_master_inventory,
)
from research.insider_buying.sec_zip_corpus_census import (
    SecZipCensusQuarter,
    SecZipCorpusCensus,
    SecZipCorpusCensusError,
)


SEC_MASTER_LOCATOR_RECONCILIATION_VERSION = (
    "INSETF-SEC-MASTER-LOCATOR-RECONCILIATION-v1"
)
_PERIODS = tuple(
    f"{year}Q{quarter}"
    for year in range(2006, 2027)
    for quarter in range(1, 5)
    if (year, quarter) <= (2026, 2)
)
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_RAW_DATE = re.compile(r"([0-9]{2})-([A-Z]{3})-([0-9]{4})\Z")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_CIK = re.compile(r"[0-9]{1,10}\Z")
_FORMS = ("3", "3/A", "4", "4/A", "5", "5/A")
_MONTHS = {name: index for index, name in enumerate((
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
    "NOV", "DEC",
), start=1)}
_RESULT_TOKEN = object()


class SecMasterLocatorReconciliationError(ValueError):
    """A malformed input or forged/partial report failed closed."""


def _refuse(message: str) -> None:
    raise SecMasterLocatorReconciliationError(f"REFUSED: {message}")


def _filing_date(raw: str, *, year: int, quarter: int) -> str:
    if type(raw) is not str:
        _refuse("SUBMISSION filing date is not a string")
    try:
        if _ISO_DATE.fullmatch(raw) is not None:
            value = date.fromisoformat(raw)
        else:
            match = _RAW_DATE.fullmatch(raw)
            if match is None or match.group(2) not in _MONTHS:
                _refuse("SUBMISSION filing date has an unsupported spelling")
            value = date(int(match.group(3)), _MONTHS[match.group(2)],
                         int(match.group(1)))
    except ValueError as exc:
        raise SecMasterLocatorReconciliationError(
            "REFUSED: SUBMISSION filing date is invalid"
        ) from exc
    if (value.year, (value.month - 1) // 3 + 1) != (year, quarter):
        _refuse("SUBMISSION filing date is outside its ZIP quarter")
    return value.isoformat()


@dataclass(frozen=True)
class SecMasterLocatorQuarterInput:
    """One quarter's caller-loaded parsed ZIP and caller-parsed master bytes."""

    period: str
    parsed_snapshot: LoadedSecBulkParsedSnapshot
    master_index: SecQuarterMasterIndexReceipt


def _target_inventory(
    snapshot: LoadedSecBulkParsedSnapshot, census: SecZipCensusQuarter,
) -> tuple[SecMasterIndexExpectedRow, ...]:
    if type(snapshot) is not LoadedSecBulkParsedSnapshot:
        _refuse("an exact caller-loaded IB-1B snapshot is required")
    identity = snapshot.identity
    year, quarter = int(census.period[:4]), int(census.period[-1])
    if (
        type(identity) is not SecBulkParsedSnapshotIdentity
        or (identity.year, identity.quarter) != (year, quarter)
        or identity.raw_archive_sha256 != census.zip_sha256
        or type(identity.schema_profile) is not SecTsvSchemaProfile
        or identity.schema_profile_hash != hash_payload(
            identity.schema_profile.to_payload()
        )
        or type(identity.tables) is not tuple
        or type(identity.artifacts) is not tuple
        or type(identity.absent_tables) is not tuple
        or type(identity.raw_lineage_hash) is not str
        or _HASH.fullmatch(identity.raw_lineage_hash) is None
        or type(identity.raw_manifest_sha256) is not str
        or _HASH.fullmatch(identity.raw_manifest_sha256) is None
        or identity.raw_snapshot_id != (
            f"sec-insider-bulk-{year}q{quarter}-"
            f"{identity.raw_lineage_hash[:16]}"
        )
        or identity.lineage_hash != hash_payload(identity.lineage_payload())
        or identity.snapshot_id != (
            f"sec-insider-parsed-{year}q{quarter}-{identity.lineage_hash[:16]}"
        )
    ):
        _refuse("IB-1B parsed identity is not bound to the census ZIP")
    submission = tuple(
        table for table in identity.tables if table.table_name == "SUBMISSION.tsv"
    )
    try:
        variant = identity.schema_profile.variant_for("SUBMISSION.tsv", year, quarter)
    except SecBulkParsedSnapshotError as exc:
        raise SecMasterLocatorReconciliationError(
            "REFUSED: IB-1B has no exact SUBMISSION schema variant"
        ) from exc
    if (
        len(submission) != 1
        or type(submission[0]) is not ParsedSecBulkTableIdentity
        or submission[0].schema_id != variant.schema_id
        or submission[0].headers != variant.headers
        or submission[0].headers != census.submission_headers
        or submission[0].source_row_key_headers != variant.source_row_key_headers
        or submission[0].header_hash != hash_payload(list(submission[0].headers))
        or submission[0].raw_member_sha256 != census.submission_member_sha256
        or submission[0].raw_member_size_bytes != census.submission_member_size_bytes
        or submission[0].row_count != census.submission_accessions
        or type(submission[0].headers) is not tuple
        or len(submission[0].headers) != len(set(submission[0].headers))
        or not {"ACCESSION_NUMBER", "DOCUMENT_TYPE", "FILING_DATE", "ISSUERCIK"}
        <= set(submission[0].headers)
        or type(snapshot.rows) is not tuple
        or type(snapshot.accessions) is not tuple
        or len(snapshot.rows) > MAX_TOTAL_ROWS
        or len(snapshot.accessions) != census.submission_accessions
        or len(snapshot.accessions) > MAX_ROWS_PER_TABLE
    ):
        _refuse("IB-1B SUBMISSION identity or population disagrees with ZIP census")
    table = submission[0]
    positions = {
        key: table.headers.index(key)
        for key in ("ACCESSION_NUMBER", "DOCUMENT_TYPE", "FILING_DATE", "ISSUERCIK")
    }
    by_accession: dict[str, tuple[str, str]] = {}
    expected: list[SecMasterIndexExpectedRow] = []
    form_counts = {form: 0 for form in _FORMS}
    submission_row_ids: list[str] = []
    for row in snapshot.rows:
        if type(row) is not ParsedSecBulkRow:
            _refuse("IB-1B contains a non-exact row")
        if row.table_name != "SUBMISSION.tsv":
            continue
        if (
            row.schema_id != table.schema_id
            or type(row.accession_number) is not str
            or _ACCESSION.fullmatch(row.accession_number) is None
            or type(row.source_record_ordinal) is not int
            or not 1 <= row.source_record_ordinal <= table.row_count
            or type(row.values) is not tuple
            or len(row.values) != len(table.headers)
            or any(type(value) is not str for value in row.values)
            or type(row.source_row_key) is not tuple
            or row.values[positions["ACCESSION_NUMBER"]] != row.accession_number
            or row.source_row_key != tuple(
                row.values[table.headers.index(name)]
                for name in table.source_row_key_headers
            )
            or row.row_id != _source_row_id(
                raw_snapshot_id=identity.raw_snapshot_id,
                raw_lineage_hash=identity.raw_lineage_hash,
                raw_archive_sha256=identity.raw_archive_sha256,
                table_name="SUBMISSION.tsv",
                raw_member_sha256=table.raw_member_sha256,
                source_record_ordinal=row.source_record_ordinal,
                values=row.values,
                source_row_key=row.source_row_key,
            )
        ):
            _refuse("IB-1B SUBMISSION row lineage is inconsistent")
        if row.accession_number in by_accession:
            _refuse("IB-1B repeats a SUBMISSION accession")
        form = row.values[positions["DOCUMENT_TYPE"]]
        if form not in form_counts:
            _refuse("IB-1B SUBMISSION form is outside the six-form scope")
        form_counts[form] += 1
        submission_row_ids.append(row.row_id)
        by_accession[row.accession_number] = (form, row.row_id)
        if form in {"4", "4/A"}:
            issuer = row.values[positions["ISSUERCIK"]]
            if type(issuer) is not str or _CIK.fullmatch(issuer) is None or int(issuer) == 0:
                _refuse("IB-1B target issuer CIK is invalid")
            filing = _filing_date(
                row.values[positions["FILING_DATE"]], year=year, quarter=quarter
            )
            try:
                expected.append(SecMasterIndexExpectedRow(
                    row.accession_number, form, filing, issuer
                ))
            except SecQuarterMasterIndexError as exc:
                raise SecMasterLocatorReconciliationError(
                    "REFUSED: IB-1B target identity is invalid"
                ) from exc
    if (
        len(by_accession) != census.submission_accessions
        or tuple(form_counts[name] for name in _FORMS) != census.form_counts
        or hash_payload(submission_row_ids) != table.row_ids_hash
    ):
        _refuse("IB-1B SUBMISSION counts disagree with ZIP census")
    observed_summaries: set[str] = set()
    for item in snapshot.accessions:
        if (
            type(item) is not ParsedSecBulkAccession
            or type(item.accession_number) is not str
            or _ACCESSION.fullmatch(item.accession_number) is None
            or item.accession_number in observed_summaries
            or by_accession.get(item.accession_number)
            != (item.document_type, item.submission_row_id)
            or type(item.table_rows) is not tuple
            or [ids for name, ids in item.table_rows if name == "SUBMISSION.tsv"]
            != [(item.submission_row_id,)]
        ):
            _refuse("IB-1B accession summary disagrees with its SUBMISSION row")
        observed_summaries.add(item.accession_number)
    if len(observed_summaries) != len(by_accession):
        _refuse("IB-1B accession summary population is incomplete")
    return tuple(sorted(expected, key=lambda item: item.accession_number))


@dataclass(frozen=True)
class SecMasterLocatorQuarterComparison:
    """Exact-count diagnostics; selected locators exist only for an exact match."""

    period: str
    zip_sha256: str
    parsed_lineage_hash: str
    master_source_sha256: str
    master_receipt_sha256: str
    expected_inventory_sha256: str
    target_count: int
    index_unique_target_count: int
    index_alias_row_count: int
    matched_count: int
    missing_count: int
    extra_count: int
    conflict_count: int
    selected_locator_sha256: str | None

    @property
    def exact(self) -> bool:
        return self.missing_count == self.extra_count == self.conflict_count == 0

    def to_payload(self) -> dict[str, object]:
        if (
            type(self) is not SecMasterLocatorQuarterComparison
            or type(self.period) is not str
            or self.period not in _PERIODS
            or any(type(value) is not str or _HASH.fullmatch(value) is None
                   for value in (
                       self.zip_sha256, self.parsed_lineage_hash,
                       self.master_source_sha256, self.master_receipt_sha256,
                       self.expected_inventory_sha256,
                   ))
            or any(type(value) is not int or value < 0 or value > MAX_ROWS_PER_TABLE
                   for value in (
                       self.target_count, self.index_unique_target_count,
                       self.index_alias_row_count, self.matched_count,
                       self.missing_count, self.extra_count, self.conflict_count,
                   ))
            or self.matched_count + self.missing_count + self.conflict_count
            != self.target_count
            or self.matched_count + self.extra_count + self.conflict_count
            != self.index_unique_target_count
            or (
                self.exact
                and (type(self.selected_locator_sha256) is not str
                     or _HASH.fullmatch(self.selected_locator_sha256) is None)
            )
            or (not self.exact and self.selected_locator_sha256 is not None)
        ):
            _refuse("quarter locator comparison is inconsistent")
        return {
            "period": self.period,
            "zip_sha256": self.zip_sha256,
            "parsed_lineage_hash": self.parsed_lineage_hash,
            "master_source_sha256": self.master_source_sha256,
            "master_receipt_sha256": self.master_receipt_sha256,
            "expected_inventory_sha256": self.expected_inventory_sha256,
            "target_count": self.target_count,
            "index_unique_target_count": self.index_unique_target_count,
            "index_alias_row_count": self.index_alias_row_count,
            "matched_count": self.matched_count,
            "missing_count": self.missing_count,
            "extra_count": self.extra_count,
            "conflict_count": self.conflict_count,
            "selected_locator_sha256": self.selected_locator_sha256,
            "exact": self.exact,
        }


def _compare_quarter(
    item: SecMasterLocatorQuarterInput, census: SecZipCensusQuarter,
) -> SecMasterLocatorQuarterComparison:
    if type(item) is not SecMasterLocatorQuarterInput or item.period != census.period:
        _refuse("quarter locator input is missing or out of order")
    expected = _target_inventory(item.parsed_snapshot, census)
    master = item.master_index
    if type(master) is not SecQuarterMasterIndexReceipt:
        _refuse("an exact parsed master-index receipt is required")
    try:
        master.__post_init__()
    except SecQuarterMasterIndexError as exc:
        raise SecMasterLocatorReconciliationError(
            "REFUSED: master-index receipt changed or is invalid"
        ) from exc
    year, quarter = int(item.period[:4]), int(item.period[-1])
    if (master.year, master.quarter) != (year, quarter):
        _refuse("master-index quarter differs from ZIP quarter")
    wanted = {row.accession_number: row for row in expected}
    indexed: dict[str, list[SecMasterIndexRow]] = {}
    for row in master.rows:
        indexed.setdefault(row.accession_number, []).append(row)
    missing = len(set(wanted) - set(indexed))
    extra = len(set(indexed) - set(wanted))
    conflicts = 0
    selected: list[SecMasterIndexRow] = []
    for accession, target in wanted.items():
        aliases = indexed.get(accession)
        if aliases is None:
            continue
        if any(row.form_type != target.form_type or row.filing_date != target.filing_date
               for row in aliases):
            conflicts += 1
            continue
        if len(aliases) == 1:
            selected.append(aliases[0])
            continue
        issuer_matches = [row for row in aliases if (
            row.archive_path.split("/")[2].lstrip("0")
            == target.issuer_cik.lstrip("0")
        )]
        if len(issuer_matches) != 1:
            conflicts += 1
            continue
        selected.append(issuer_matches[0])
    exact = missing == extra == conflicts == 0
    if exact:
        try:
            if tuple(selected) != join_exact_sec_master_inventory(master, expected):
                _refuse("locator selection differs from the exact index join")
        except SecQuarterMasterIndexError as exc:
            raise SecMasterLocatorReconciliationError(
                "REFUSED: exact master-index join failed"
            ) from exc
    return SecMasterLocatorQuarterComparison(
        period=item.period,
        zip_sha256=census.zip_sha256,
        parsed_lineage_hash=item.parsed_snapshot.identity.lineage_hash,
        master_source_sha256=master.source_sha256,
        master_receipt_sha256=master.receipt_sha256,
        expected_inventory_sha256=hash_payload([{
            "accession_number": row.accession_number,
            "form_type": row.form_type,
            "filing_date": row.filing_date,
            "issuer_cik": row.issuer_cik,
        } for row in expected]),
        target_count=len(expected),
        index_unique_target_count=len(indexed),
        index_alias_row_count=len(master.rows) - len(indexed),
        matched_count=len(selected),
        missing_count=missing,
        extra_count=extra,
        conflict_count=conflicts,
        selected_locator_sha256=(
            hash_payload([row.to_payload() for row in selected]) if exact else None
        ),
    )


@dataclass(frozen=True)
class SecMasterLocatorReconciliation:
    """Full 82-quarter report. No partial locator inventory can be promoted."""

    census_sha256: str
    source_scope: str
    quarters: tuple[SecMasterLocatorQuarterComparison, ...]
    all_quarters_exact: bool
    locator_inventory_sha256: str | None
    report_sha256: str
    _token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        self.to_payload()

    def to_payload(self) -> dict[str, object]:
        if (
            type(self) is not SecMasterLocatorReconciliation
            or self._token is not _RESULT_TOKEN
            or type(self.census_sha256) is not str
            or _HASH.fullmatch(self.census_sha256) is None
            or type(self.source_scope) is not str
            or self.source_scope not in {
                "retained_noncanonical_zip_census", "synthetic_test_census"
            }
            or type(self.quarters) is not tuple
            or len(self.quarters) != 82
            or any(type(item) is not SecMasterLocatorQuarterComparison
                   for item in self.quarters)
            or tuple(item.period for item in self.quarters) != _PERIODS
            or type(self.all_quarters_exact) is not bool
            or self.all_quarters_exact != all(item.exact for item in self.quarters)
            or (
                self.all_quarters_exact
                and (type(self.locator_inventory_sha256) is not str
                     or _HASH.fullmatch(self.locator_inventory_sha256) is None)
            )
            or (not self.all_quarters_exact and self.locator_inventory_sha256 is not None)
        ):
            _refuse("82-quarter locator report is invalid or partially promoted")
        quarter_payloads = [item.to_payload() for item in self.quarters]
        expected_inventory_hash = (
            hash_payload([item.selected_locator_sha256 for item in self.quarters])
            if self.all_quarters_exact else None
        )
        if self.locator_inventory_sha256 != expected_inventory_hash:
            _refuse("82-quarter locator digest changed")
        payload = {
            "version": SEC_MASTER_LOCATOR_RECONCILIATION_VERSION,
            "census_sha256": self.census_sha256,
            "source_scope": self.source_scope,
            "quarters": quarter_payloads,
            "all_quarters_exact": self.all_quarters_exact,
            "locator_inventory_sha256": self.locator_inventory_sha256,
            "counts": {
                "target_accessions": sum(item.target_count for item in self.quarters),
                "index_alias_rows": sum(item.index_alias_row_count for item in self.quarters),
                "missing": sum(item.missing_count for item in self.quarters),
                "extra": sum(item.extra_count for item in self.quarters),
                "conflicting": sum(item.conflict_count for item in self.quarters),
            },
            "authority": {
                "caller_loaded_source_only": True,
                "sec_origin_authenticated": False,
                "master_index_completeness_proven": False,
                "issuer_identity_confirmed_from_master": False,
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
            },
        }
        if self.report_sha256 != hash_payload(payload):
            _refuse("82-quarter locator report fingerprint changed")
        return payload


def reconcile_sec_master_locators(
    census: SecZipCorpusCensus,
    quarters: Iterable[SecMasterLocatorQuarterInput],
) -> SecMasterLocatorReconciliation:
    """Consume exactly 82 quarter inputs once; keep only aggregate diagnostics.

    The caller must load/validate each parsed ZIP and index through their own
    reviewed boundaries. This pure function rechecks internal content hashes
    and exact census counts but cannot independently authenticate those bytes.
    """
    if type(census) is not SecZipCorpusCensus:
        _refuse("an exact 82-quarter ZIP census is required")
    try:
        census.to_payload()
        census_sha256 = census.sha256
    except SecZipCorpusCensusError as exc:
        raise SecMasterLocatorReconciliationError(
            "REFUSED: ZIP census changed after its source read"
        ) from exc
    try:
        stream = iter(quarters)
    except TypeError as exc:
        raise SecMasterLocatorReconciliationError(
            "REFUSED: quarter locators must be iterable"
        ) from exc
    summaries: list[SecMasterLocatorQuarterComparison] = []
    sentinel = object()
    for census_quarter in census.quarters:
        item = next(stream, sentinel)
        if item is sentinel:
            _refuse("82-quarter locator inventory is incomplete")
        summary = _compare_quarter(item, census_quarter)
        summary.to_payload()
        summaries.append(summary)
    if next(stream, sentinel) is not sentinel:
        _refuse("82-quarter locator inventory has an extra quarter")
    if census.sha256 != census_sha256:
        _refuse("ZIP census changed during locator reconciliation")
    frozen = tuple(summaries)
    exact = all(item.exact for item in frozen)
    locator_hash = (
        hash_payload([item.selected_locator_sha256 for item in frozen])
        if exact else None
    )
    payload = {
        "version": SEC_MASTER_LOCATOR_RECONCILIATION_VERSION,
        "census_sha256": census_sha256,
        "source_scope": census.scope,
        "quarters": [item.to_payload() for item in frozen],
        "all_quarters_exact": exact,
        "locator_inventory_sha256": locator_hash,
        "counts": {
            "target_accessions": sum(item.target_count for item in frozen),
            "index_alias_rows": sum(item.index_alias_row_count for item in frozen),
            "missing": sum(item.missing_count for item in frozen),
            "extra": sum(item.extra_count for item in frozen),
            "conflicting": sum(item.conflict_count for item in frozen),
        },
        "authority": {
            "caller_loaded_source_only": True,
            "sec_origin_authenticated": False,
            "master_index_completeness_proven": False,
            "issuer_identity_confirmed_from_master": False,
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
        },
    }
    return SecMasterLocatorReconciliation(
        census_sha256=census_sha256,
        source_scope=census.scope,
        quarters=frozen,
        all_quarters_exact=exact,
        locator_inventory_sha256=locator_hash,
        report_sha256=hash_payload(payload),
        _token=_RESULT_TOKEN,
    )


__all__ = [
    "SEC_MASTER_LOCATOR_RECONCILIATION_VERSION",
    "SecMasterLocatorQuarterComparison",
    "SecMasterLocatorQuarterInput",
    "SecMasterLocatorReconciliation",
    "SecMasterLocatorReconciliationError",
    "reconcile_sec_master_locators",
]
