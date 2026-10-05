"""Pure, date-only IB-1C compatibility diagnostic for the fixed 16 filings.

The caller must supply two IB-1B snapshots returned by their raw-bound loader.
This module does not load or authenticate those snapshots, infer a timezone from
the SGML acceptance clock, create a v1 EDGAR metadata source, or publish a
full-quarter acceptance snapshot. It has no network, outcome, or trading I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re

from data.hashing import hash_payload
from research.insider_buying.sec_bulk_parsed_snapshot import (
    MAX_TOTAL_ROWS,
    LoadedSecBulkParsedSnapshot,
    ParsedSecBulkAccession,
    ParsedSecBulkRow,
    SecBulkParsedSnapshotIdentity,
    SecTsvSchemaProfile,
    _source_row_id,
)
from research.insider_buying.sec_complete_submission import SecCompleteSubmissionError
from research.insider_buying_sec_complete_projection_adapter import (
    COMPLETE_PILOT_ADAPTER_VERSION,
    FIXED_ACCESSIONS,
    SecCompletePilotAdapterError,
    SecCompletePilotProjectionReceipt,
    _canonical_object,
)


SEC_COMPLETE_IB1C_PILOT_AVAILABILITY_VERSION = (
    "INSETF-SEC-COMPLETE-IB1C-SIXTEEN-DATE-ONLY-v1"
)
_PERIODS = (("2022Q4", 2022, 4), ("2023Q1", 2023, 1))
_CANDIDATE_KEYS = frozenset({
    "period", "accession_number", "form_type", "filing_date_raw", "filing_date",
    "issuer_cik", "quarterly_zip_sha256", "submission_row_id", "raw_snapshot_id",
    "raw_lineage_sha256",
})
_REQUIRED_SUBMISSION_FIELDS = frozenset({
    "ACCESSION_NUMBER", "DOCUMENT_TYPE", "FILING_DATE", "ISSUERCIK",
})
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_RAW_FILING_DATE = re.compile(r"([0-9]{2})-([A-Z]{3})-([0-9]{4})\Z")
_MONTHS = {name: index for index, name in enumerate((
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
    "NOV", "DEC",
), start=1)}
_AVAILABILITY_TIER = "filing_date_fallback"
_NEXT_OPEN_RULE = "next-open-after-filing-date"
_TOKEN = object()


class SecCompleteIb1cPilotAvailabilityError(ValueError):
    """The noncanonical exact-16 date-only diagnostic failed closed."""


def _refuse(message: str) -> None:
    raise SecCompleteIb1cPilotAvailabilityError(f"REFUSED: {message}")


def _filing_date_from_raw(value: str) -> str:
    """Independently pin the selected IB-1B DD-MON-YYYY source dialect."""
    match = _RAW_FILING_DATE.fullmatch(value) if type(value) is str else None
    if match is None or match.group(2) not in _MONTHS:
        _refuse("IB-1B filing date has an unapproved raw spelling")
    try:
        return date(int(match.group(3)), _MONTHS[match.group(2)],
                    int(match.group(1))).isoformat()
    except ValueError as exc:
        raise SecCompleteIb1cPilotAvailabilityError(
            "REFUSED: IB-1B raw filing date is invalid"
        ) from exc


def _snapshot_rows(
    snapshot: LoadedSecBulkParsedSnapshot, *, period: str, year: int,
    quarter: int, wanted: set[str],
) -> dict[str, tuple[ParsedSecBulkAccession, ParsedSecBulkRow]]:
    if type(snapshot) is not LoadedSecBulkParsedSnapshot:
        _refuse("an exact caller-loaded IB-1B snapshot is required")
    identity = snapshot.identity
    if (type(identity) is not SecBulkParsedSnapshotIdentity
            or type(identity.schema_profile) is not SecTsvSchemaProfile
            or type(identity.tables) is not tuple):
        _refuse("IB-1B identity is not an exact parsed-snapshot identity")
    if (identity.year, identity.quarter) != (year, quarter):
        _refuse("IB-1B snapshots are not the exact ordered two quarters")
    if (identity.schema_profile_hash != hash_payload(identity.schema_profile.to_payload())
            or identity.lineage_hash != hash_payload(identity.lineage_payload())
            or identity.snapshot_id != (
                f"sec-insider-parsed-{year:04d}q{quarter}-{identity.lineage_hash[:16]}"
            )):
        _refuse("IB-1B identity is internally inconsistent")
    if (type(snapshot.rows) is not tuple or len(snapshot.rows) > MAX_TOTAL_ROWS
            or type(snapshot.accessions) is not tuple):
        _refuse("IB-1B row or accession vector is not bounded and immutable")
    tables = [item for item in identity.tables if item.table_name == "SUBMISSION.tsv"]
    if len(tables) != 1 or not _REQUIRED_SUBMISSION_FIELDS.issubset(tables[0].headers):
        _refuse("IB-1B has no exact SUBMISSION table identity")
    table = tables[0]
    if len(table.headers) != len(set(table.headers)) or _SHA.fullmatch(table.raw_member_sha256) is None:
        _refuse("IB-1B SUBMISSION header or raw-member identity is malformed")
    positions = {name: table.headers.index(name) for name in _REQUIRED_SUBMISSION_FIELDS}
    accession_by_number: dict[str, ParsedSecBulkAccession] = {}
    for item in snapshot.accessions:
        if type(item) is not ParsedSecBulkAccession:
            _refuse("IB-1B accession type drifted")
        if item.accession_number in wanted:
            if item.accession_number in accession_by_number:
                _refuse("IB-1B repeats a selected accession")
            accession_by_number[item.accession_number] = item
    row_by_number: dict[str, ParsedSecBulkRow] = {}
    for row in snapshot.rows:
        if type(row) is not ParsedSecBulkRow:
            _refuse("IB-1B row type drifted")
        if row.table_name != "SUBMISSION.tsv" or row.accession_number not in wanted:
            continue
        if row.accession_number in row_by_number:
            _refuse("IB-1B repeats a selected SUBMISSION row")
        if (row.schema_id != table.schema_id or type(row.values) is not tuple
                or len(row.values) != len(table.headers)
                or any(type(value) is not str for value in row.values)
                or type(row.source_row_key) is not tuple
                or row.values[positions["ACCESSION_NUMBER"]] != row.accession_number):
            _refuse("IB-1B selected SUBMISSION row differs from its table schema")
        source_key = tuple(row.values[table.headers.index(name)]
                           for name in table.source_row_key_headers)
        if row.source_row_key != source_key or row.row_id != _source_row_id(
            raw_snapshot_id=identity.raw_snapshot_id,
            raw_lineage_hash=identity.raw_lineage_hash,
            raw_archive_sha256=identity.raw_archive_sha256,
            table_name="SUBMISSION.tsv", raw_member_sha256=table.raw_member_sha256,
            source_record_ordinal=row.source_record_ordinal,
            values=row.values, source_row_key=source_key,
        ):
            _refuse("IB-1B selected SUBMISSION row lineage is inconsistent")
        row_by_number[row.accession_number] = row
    if set(accession_by_number) != wanted or set(row_by_number) != wanted:
        _refuse(f"IB-1B {period} is missing a selected accession or SUBMISSION row")
    result = {}
    for accession in wanted:
        item, row = accession_by_number[accession], row_by_number[accession]
        submission_ids = [ids for name, ids in item.table_rows if name == "SUBMISSION.tsv"]
        if (len(submission_ids) != 1 or submission_ids[0] != (row.row_id,)
                or item.submission_row_id != row.row_id
                or item.document_type != row.values[positions["DOCUMENT_TYPE"]]):
            _refuse("IB-1B accession summary disagrees with its selected SUBMISSION row")
        result[accession] = (item, row)
    return result


@dataclass(frozen=True)
class SecCompleteIb1cPilotAvailabilityRow:
    period: str
    accession_number: str
    form_type: str
    issuer_cik: str
    filing_date: str
    submission_row_id: str
    parsed_snapshot_id: str
    complete_projection_sha256: str
    raw_complete_submission_sha256: str
    derived_header_sha256: str
    derived_primary_xml_sha256: str
    accepted_at_raw_uninterpreted: str
    amendment_status: str

    def to_payload(self) -> dict[str, object]:
        return {
            "period": self.period,
            "accession_number": self.accession_number,
            "form_type": self.form_type,
            "issuer_cik": self.issuer_cik,
            "filing_date": self.filing_date,
            "submission_row_id": self.submission_row_id,
            "parsed_snapshot_id": self.parsed_snapshot_id,
            "complete_projection_sha256": self.complete_projection_sha256,
            "raw_complete_submission_sha256": self.raw_complete_submission_sha256,
            "derived_header_sha256": self.derived_header_sha256,
            "derived_primary_xml_sha256": self.derived_primary_xml_sha256,
            "accepted_at_raw_uninterpreted": self.accepted_at_raw_uninterpreted,
            "amendment_status": self.amendment_status,
            "availability_tier": _AVAILABILITY_TIER,
            "accepted_at": None,
            "next_open_rule": _NEXT_OPEN_RULE,
            "availability_role": "non_executable_diagnostic",
            "next_open_rule_executable": False,
            "signal_authorized": False,
        }


def _checked_rows(
    receipt: SecCompletePilotProjectionReceipt,
    snapshots: tuple[LoadedSecBulkParsedSnapshot, LoadedSecBulkParsedSnapshot],
) -> tuple[str, str, tuple[str, str], tuple[SecCompleteIb1cPilotAvailabilityRow, ...]]:
    if type(receipt) is not SecCompletePilotProjectionReceipt:
        _refuse("an exact complete-text pilot receipt is required")
    if type(snapshots) is not tuple or len(snapshots) != 2:
        _refuse("exactly two ordered caller-loaded IB-1B snapshots are required")
    try:
        source = receipt.to_payload()
        report = _canonical_object(receipt._report_bytes, label="complete pilot report")
    except (SecCompletePilotAdapterError, SecCompleteSubmissionError) as exc:
        raise SecCompleteIb1cPilotAvailabilityError("REFUSED: complete pilot receipt failed replay") from exc
    authority = source.get("authority")
    if (source.get("version") != COMPLETE_PILOT_ADAPTER_VERSION
            or type(authority) is not dict
            or authority.get("input_scope") not in {
                "retained_noncanonical_complete_pilot", "synthetic_test_receipt",
            }
            or any(authority.get(name) is not False for name in (
                "source_authenticated", "quarter_completeness_verified", "point_in_time_data",
                "canonical_evidence", "direct_ib1c_ingest_authorized",
                "official_sec_profile_verified", "timezone_interpretation_verified",
                "outcome_access_authorized", "qc_job_authorized",
                "broker_or_trading_authorized",
            ))
            or any(type(authority.get(name)) is not int or authority[name] != 0
                   for name in ("research_looks", "authorized_outcome_looks",
                                "consumed_outcome_looks"))):
        _refuse("complete pilot receipt claims authority it does not have")
    filings = report.get("filings")
    if (type(filings) is not list or len(filings) != 16
            or type(source.get("rows")) is not list or len(source["rows"]) != 16
            or type(receipt.projections) is not tuple or len(receipt.projections) != 16):
        _refuse("complete pilot does not retain the exact sixteen")
    candidates = [item.get("candidate") if type(item) is dict else None for item in filings]
    if (any(type(item) is not dict or set(item) != _CANDIDATE_KEYS
            or any(type(value) is not str for value in item.values()) for item in candidates)
            or hash_payload(candidates) != receipt.inventory_sha256
            or tuple(item["accession_number"] for item in candidates) != FIXED_ACCESSIONS):
        _refuse("complete pilot candidate inventory is not the pinned sixteen")
    wanted = {
        period: {item["accession_number"] for item in candidates if item["period"] == period}
        for period, _, _ in _PERIODS
    }
    if [len(wanted[period]) for period, _, _ in _PERIODS] != [8, 8]:
        _refuse("complete pilot period allocation is not eight plus eight")
    joined = {}
    for (period, year, quarter), snapshot in zip(_PERIODS, snapshots, strict=True):
        joined[period] = _snapshot_rows(
            snapshot, period=period, year=year, quarter=quarter,
            wanted=wanted[period],
        )
    rows: list[SecCompleteIb1cPilotAvailabilityRow] = []
    for candidate, projection, snapshot in zip(
        candidates, receipt.projections,
        [snapshots[0]] * 8 + [snapshots[1]] * 8, strict=True,
    ):
        period = candidate["period"]
        accession = candidate["accession_number"]
        if period not in joined or accession not in joined[period]:
            _refuse("complete pilot filing period or accession is not in IB-1B")
        _, row = joined[period][accession]
        identity = snapshot.identity
        table = next(item for item in identity.tables if item.table_name == "SUBMISSION.tsv")
        values = {name: row.values[table.headers.index(name)]
                  for name in _REQUIRED_SUBMISSION_FIELDS}
        target = projection.target
        if (candidate["period"] != target.period
                or candidate["accession_number"] != target.accession_number
                or candidate["form_type"] != target.form_type
                or candidate["filing_date"] != target.filing_date
                or candidate["issuer_cik"] != target.issuer_cik
                or candidate["submission_row_id"] != row.row_id
                or candidate["raw_snapshot_id"] != identity.raw_snapshot_id
                or candidate["raw_lineage_sha256"] != identity.raw_lineage_hash
                or candidate["quarterly_zip_sha256"] != identity.raw_archive_sha256
                or values["ACCESSION_NUMBER"] != accession
                or values["DOCUMENT_TYPE"] != target.form_type
                or values["FILING_DATE"] != candidate["filing_date_raw"]
                or _filing_date_from_raw(values["FILING_DATE"]) != target.filing_date
                or values["ISSUERCIK"] != target.issuer_cik):
            _refuse("complete pilot and IB-1B submission identity disagree")
        try:
            date.fromisoformat(candidate["filing_date"])
            parent = projection.to_payload()
        except (ValueError, SecCompletePilotAdapterError, SecCompleteSubmissionError) as exc:
            raise SecCompleteIb1cPilotAvailabilityError(
                "REFUSED: complete pilot filing date or projection is invalid"
            ) from exc
        if not re.fullmatch(r"[0-9]{14}", projection.accepted_at_raw):
            _refuse("complete pilot acceptance clock is not raw 14-digit text")
        # Without an authenticated timezone, even a coherent SGML clock with
        # a later calendar date could make next-open-after-filing-date precede
        # public acceptance. Never emit that rule for such a row.
        if projection.accepted_at_raw[:8] != target.filing_date.replace("-", ""):
            _refuse("raw acceptance date differs from filing date; no safe date-only rule")
        rows.append(SecCompleteIb1cPilotAvailabilityRow(
            period=period, accession_number=accession, form_type=target.form_type,
            issuer_cik=target.issuer_cik, filing_date=target.filing_date,
            submission_row_id=row.row_id, parsed_snapshot_id=identity.snapshot_id,
            complete_projection_sha256=projection.sha256,
            raw_complete_submission_sha256=parent["raw_parent"]["sha256"],
            derived_header_sha256=parent["children"]["header"]["sha256"],
            derived_primary_xml_sha256=parent["children"]["primary_xml"]["sha256"],
            accepted_at_raw_uninterpreted=projection.accepted_at_raw,
            amendment_status=("quarantined_original_link_unverified" if target.form_type == "4/A"
                              else "original_no_link_asserted"),
        ))
    return (authority["input_scope"], receipt.report_sha256,
            tuple(snapshot.identity.snapshot_id for snapshot in snapshots), tuple(rows))


@dataclass(frozen=True)
class SecCompletePilotIb1cAvailabilityReport:
    """An exact-16 diagnostic, not a v1 IB-1C snapshot or source."""

    _receipt: SecCompletePilotProjectionReceipt = field(repr=False, compare=False)
    _snapshots: tuple[LoadedSecBulkParsedSnapshot, LoadedSecBulkParsedSnapshot] = field(
        repr=False, compare=False,
    )
    input_scope: str
    source_report_sha256: str
    parsed_snapshot_ids: tuple[str, str]
    rows: tuple[SecCompleteIb1cPilotAvailabilityRow, ...]
    _token: object = field(repr=False, compare=False)

    def _validate(self) -> None:
        if self._token is not _TOKEN or (
            self.input_scope, self.source_report_sha256,
            self.parsed_snapshot_ids, self.rows,
        ) != _checked_rows(self._receipt, self._snapshots):
            _refuse("date-only pilot report lost its source binding")

    def __post_init__(self) -> None:
        self._validate()

    def to_payload(self) -> dict[str, object]:
        self._validate()
        return {
            "version": SEC_COMPLETE_IB1C_PILOT_AVAILABILITY_VERSION,
            "input_scope": self.input_scope,
            "source_report_sha256": self.source_report_sha256,
            "caller_loaded_ib1b_snapshot_ids": list(self.parsed_snapshot_ids),
            "rows": [row.to_payload() for row in self.rows],
            "authority": {
                "input_snapshots_reloaded_here": False,
                "full_quarter_ib1c_snapshot": False,
                "exact_acceptance_time_available": False,
                "date_only_rule_executable": False,
                "timezone_interpretation_verified": False,
                "source_authenticated": False,
                "canonical_evidence": False,
                "point_in_time_data": False,
                "direct_ib1c_v1_ingest_authorized": False,
                "amendment_lineage_verified": False,
                "signal_authorized": False,
                "outcome_access_authorized": False,
                "qc_job_authorized": False,
                "broker_or_trading_authorized": False,
                "research_looks": 0,
                "authorized_outcome_looks": 0,
                "consumed_outcome_looks": 0,
            },
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def assess_complete_pilot_ib1c_availability(
    receipt: SecCompletePilotProjectionReceipt,
    snapshots: tuple[LoadedSecBulkParsedSnapshot, LoadedSecBulkParsedSnapshot],
) -> SecCompletePilotIb1cAvailabilityReport:
    """Join the fixed 16 to caller-loaded IB-1B without converting clocks."""
    scope, report_sha, snapshot_ids, rows = _checked_rows(receipt, snapshots)
    return SecCompletePilotIb1cAvailabilityReport(
        _receipt=receipt, _snapshots=snapshots, input_scope=scope,
        source_report_sha256=report_sha, parsed_snapshot_ids=snapshot_ids,
        rows=rows, _token=_TOKEN,
    )
