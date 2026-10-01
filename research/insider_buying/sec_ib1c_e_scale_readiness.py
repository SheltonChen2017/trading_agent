"""Pure 82-quarter IB-1C..IB-1E scale/readiness boundary.

The inputs are caller declarations, not loaded SEC artifacts or official
attestations.  One quarter is appended at a time, with a strict finite bound
on retained accession identities and no XML or metadata bytes.  Exact
cross-quarter uniqueness and link checks require that retained identity
index; this is a planning boundary, not a four-million-filing processor.

Even a complete and internally consistent declaration never authenticates
source origin, acceptance time, amendment coverage, the PIT security master,
or the trading calendar.  Every output has false canonical, PIT, signal, and
backtest authority.  No network, filesystem, outcome, QC, or trading access
exists in this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from data.hashing import hash_payload


SEC_IB1C_E_SCALE_READINESS_VERSION = "INSETF-IB1C-E-SCALE-READINESS-v1"
EXPECTED_PERIODS = tuple(
    f"{year}Q{quarter}"
    for year in range(2006, 2027)
    for quarter in range(1, 5)
    if (year, quarter) <= (2026, 2)
)
MAX_QUARTER_FILINGS = 500_000
MAX_TOTAL_FILINGS = 5_000_000
LEGACY_IB1E_MAX_PERIODS = 16
LEGACY_IB1E_MAX_XML_SOURCES = 256
MAX_REPORTING_OWNERS_PER_FILING = 256

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_ACCESSION_RE = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
_CIK_RE = re.compile(r"[0-9]{10}\Z")
_UTC_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00\Z")


class SecIb1cEScaleReadinessError(ValueError):
    """The caller-declared IB-1C..IB-1E scale candidate failed closed."""


def _sha(value: object, *, label: str, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise SecIb1cEScaleReadinessError(f"REFUSED: {label} must be an exact SHA-256")
    return value


def _accession(value: object, *, label: str) -> str:
    if type(value) is not str or _ACCESSION_RE.fullmatch(value) is None:
        raise SecIb1cEScaleReadinessError(f"REFUSED: {label} is not a canonical accession")
    return value


def _accepted_at(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _UTC_RE.fullmatch(value) is None:
        raise SecIb1cEScaleReadinessError(
            "REFUSED: declared acceptance time must be exact second-resolution UTC"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SecIb1cEScaleReadinessError(
            "REFUSED: declared acceptance time is invalid"
        ) from exc
    if parsed.utcoffset() != timedelta(0) or parsed.isoformat(timespec="seconds") != value:
        raise SecIb1cEScaleReadinessError(
            "REFUSED: declared acceptance time is not canonical UTC"
        )
    return value


@dataclass(frozen=True)
class DeclaredIb1ceFiling:
    """One as-filed accession, without XML bytes or an official link claim."""

    accession_number: str
    form_type: str
    issuer_cik: str
    reporting_owner_ciks: tuple[str, ...] = ()
    accepted_at_utc: str | None = None
    complete_parent_sha256: str | None = None
    complete_xml_sha256: str | None = None
    acceptance_metadata_sha256: str | None = None
    asserted_original_accession: str | None = None

    def __post_init__(self) -> None:
        if type(self) is not DeclaredIb1ceFiling:
            raise SecIb1cEScaleReadinessError("REFUSED: exact filing declaration required")
        _accession(self.accession_number, label="filing")
        if type(self.form_type) is not str or self.form_type not in {"4", "4/A"}:
            raise SecIb1cEScaleReadinessError("REFUSED: only Form 4/4-A belongs here")
        if type(self.issuer_cik) is not str or _CIK_RE.fullmatch(self.issuer_cik) is None or int(self.issuer_cik) == 0:
            raise SecIb1cEScaleReadinessError("REFUSED: issuer CIK is invalid")
        if (type(self.reporting_owner_ciks) is not tuple
                or len(self.reporting_owner_ciks) > MAX_REPORTING_OWNERS_PER_FILING
                or any(type(cik) is not str or _CIK_RE.fullmatch(cik) is None or int(cik) == 0
                       for cik in self.reporting_owner_ciks)
                or len(set(self.reporting_owner_ciks)) != len(self.reporting_owner_ciks)):
            raise SecIb1cEScaleReadinessError(
                "REFUSED: reporting-owner CIKs must be a bounded unique tuple"
            )
        _accepted_at(self.accepted_at_utc)
        _sha(self.complete_parent_sha256, label="complete parent", optional=True)
        _sha(self.complete_xml_sha256, label="complete XML", optional=True)
        _sha(self.acceptance_metadata_sha256, label="acceptance metadata", optional=True)
        if self.asserted_original_accession is not None:
            _accession(self.asserted_original_accession, label="asserted original")
        if self.form_type == "4" and self.asserted_original_accession is not None:
            raise SecIb1cEScaleReadinessError("REFUSED: an original Form 4 cannot link to an original")
        if self.asserted_original_accession == self.accession_number:
            raise SecIb1cEScaleReadinessError("REFUSED: an amendment cannot link to itself")

    def to_payload(self) -> dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "form_type": self.form_type,
            "issuer_cik": self.issuer_cik,
            "reporting_owner_ciks": list(self.reporting_owner_ciks),
            "accepted_at_utc": self.accepted_at_utc,
            "complete_parent_sha256": self.complete_parent_sha256,
            "complete_xml_sha256": self.complete_xml_sha256,
            "acceptance_metadata_sha256": self.acceptance_metadata_sha256,
            "asserted_original_accession": self.asserted_original_accession,
        }


@dataclass(frozen=True)
class DeclaredIb1ceQuarter:
    """A bounded caller-declared quarter; hashes do not authenticate SEC origin."""

    period: str
    parsed_ib1b_sha256: str
    filings: tuple[DeclaredIb1ceFiling, ...]
    quarter_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self) is not DeclaredIb1ceQuarter:
            raise SecIb1cEScaleReadinessError("REFUSED: exact quarter declaration required")
        if type(self.period) is not str or self.period not in EXPECTED_PERIODS:
            raise SecIb1cEScaleReadinessError("REFUSED: quarter is outside frozen 82-period window")
        _sha(self.parsed_ib1b_sha256, label="parsed IB-1B receipt")
        if type(self.filings) is not tuple or len(self.filings) > MAX_QUARTER_FILINGS or any(type(row) is not DeclaredIb1ceFiling for row in self.filings):
            raise SecIb1cEScaleReadinessError("REFUSED: quarter filings are not a bounded exact tuple")
        accessions = tuple(row.accession_number for row in self.filings)
        # A forged unhashable accession must refuse, not raise TypeError.
        if any(type(value) is not str for value in accessions):
            raise SecIb1cEScaleReadinessError("REFUSED: quarter accession is not exact text")
        if accessions != tuple(sorted(set(accessions))):
            raise SecIb1cEScaleReadinessError("REFUSED: quarter accessions repeat or are unordered")
        year_suffix = self.period[2:4]
        if any(row.accession_number[11:13] != year_suffix for row in self.filings):
            raise SecIb1cEScaleReadinessError("REFUSED: accession year differs from quarter")
        expected_sha256 = hash_payload(self.to_payload())
        prior_sha256 = getattr(self, "quarter_sha256", None)
        if prior_sha256 is not None and (
            type(prior_sha256) is not str or prior_sha256 != expected_sha256
        ):
            raise SecIb1cEScaleReadinessError("REFUSED: quarter lineage hash changed")
        object.__setattr__(self, "quarter_sha256", expected_sha256)

    def to_payload(self) -> dict[str, object]:
        return {
            "period": self.period,
            "parsed_ib1b_sha256": self.parsed_ib1b_sha256,
            "filings": [row.to_payload() for row in self.filings],
        }


@dataclass(frozen=True)
class Ib1ceScaleCheckpoint:
    """Immutable chain of quarter declarations, including every supplied row."""

    quarters: tuple[DeclaredIb1ceQuarter, ...]
    chain_sha256: str

    def __post_init__(self) -> None:
        if type(self) is not Ib1ceScaleCheckpoint or type(self.quarters) is not tuple or len(self.quarters) > len(EXPECTED_PERIODS):
            raise SecIb1cEScaleReadinessError("REFUSED: checkpoint shape is invalid")
        if any(type(item) is not DeclaredIb1ceQuarter for item in self.quarters):
            raise SecIb1cEScaleReadinessError("REFUSED: checkpoint quarter type is invalid")
        for item in self.quarters:
            item.__post_init__()
        if tuple(item.period for item in self.quarters) != EXPECTED_PERIODS[:len(self.quarters)]:
            raise SecIb1cEScaleReadinessError("REFUSED: checkpoint periods are missing or reordered")
        if sum(len(item.filings) for item in self.quarters) > MAX_TOTAL_FILINGS:
            raise SecIb1cEScaleReadinessError("REFUSED: checkpoint filing cap exceeded")
        if self.chain_sha256 != _chain_hash(self.quarters):
            raise SecIb1cEScaleReadinessError("REFUSED: checkpoint lineage hash changed")

    @property
    def canonical_filter_authorized(self) -> bool:
        return False

    @property
    def point_in_time_mapping_verified(self) -> bool:
        return False

    @property
    def signal_authorized(self) -> bool:
        return False

    @property
    def backtest_ready(self) -> bool:
        return False


def _chain_hash(quarters: tuple[DeclaredIb1ceQuarter, ...]) -> str:
    return hash_payload({
        "version": SEC_IB1C_E_SCALE_READINESS_VERSION,
        "quarter_hashes": [item.quarter_sha256 for item in quarters],
    })


def _check_links(quarters: tuple[DeclaredIb1ceQuarter, ...]) -> int:
    by_accession: dict[str, tuple[int, DeclaredIb1ceFiling]] = {}
    for quarter_index, quarter in enumerate(quarters):
        for row in quarter.filings:
            if row.accession_number in by_accession:
                raise SecIb1cEScaleReadinessError(
                    "REFUSED: duplicate accession across quarters"
                )
            by_accession[row.accession_number] = (quarter_index, row)
    unresolved = 0
    for quarter_index, quarter in enumerate(quarters):
        for row in quarter.filings:
            if row.form_type != "4/A":
                continue
            if row.asserted_original_accession is None:
                unresolved += 1
                continue
            original = by_accession.get(row.asserted_original_accession)
            if original is None:
                unresolved += 1
                continue
            original_index, original_row = original
            if original_index > quarter_index or original_row.form_type != "4":
                raise SecIb1cEScaleReadinessError("REFUSED: amendment link does not point to an earlier original")
            if original_row.issuer_cik != row.issuer_cik:
                raise SecIb1cEScaleReadinessError("REFUSED: amendment link crosses issuers")
            if (original_row.accepted_at_utc is not None and row.accepted_at_utc is not None and row.accepted_at_utc <= original_row.accepted_at_utc):
                raise SecIb1cEScaleReadinessError("REFUSED: amendment acceptance does not follow original")
    return unresolved


def append_declared_ib1ce_quarter(
    checkpoint: Ib1ceScaleCheckpoint | None,
    quarter: DeclaredIb1ceQuarter,
) -> Ib1ceScaleCheckpoint:
    """Append exactly the next quarter without reading or publishing data."""

    if checkpoint is not None and type(checkpoint) is not Ib1ceScaleCheckpoint:
        raise SecIb1cEScaleReadinessError("REFUSED: exact checkpoint required")
    if type(quarter) is not DeclaredIb1ceQuarter:
        raise SecIb1cEScaleReadinessError("REFUSED: exact quarter required")
    quarter.__post_init__()
    prior = () if checkpoint is None else checkpoint.quarters
    if checkpoint is not None:
        checkpoint.__post_init__()
    if len(prior) >= len(EXPECTED_PERIODS) or quarter.period != EXPECTED_PERIODS[len(prior)]:
        raise SecIb1cEScaleReadinessError("REFUSED: quarter is missing, repeated or reordered")
    if sum(len(item.filings) for item in prior) + len(quarter.filings) > MAX_TOTAL_FILINGS:
        raise SecIb1cEScaleReadinessError("REFUSED: total filing cap exceeded")
    combined = (*prior, quarter)
    _check_links(combined)
    return Ib1ceScaleCheckpoint(combined, _chain_hash(combined))


@dataclass(frozen=True)
class Ib1ceScaleReadinessReport:
    checkpoint_sha256: str
    quarter_sha256s: tuple[tuple[str, str], ...]
    filing_count: int
    amendment_count: int
    multi_owner_filing_count: int
    missing_owner_identity_count: int
    unresolved_link_count: int
    missing_exact_acceptance_count: int
    missing_parent_count: int
    missing_xml_count: int
    missing_metadata_count: int
    blockers: tuple[str, ...]

    @property
    def canonical_filter_authorized(self) -> bool:
        return False

    @property
    def point_in_time_mapping_verified(self) -> bool:
        return False

    @property
    def signal_authorized(self) -> bool:
        return False

    @property
    def backtest_ready(self) -> bool:
        return False

    def to_payload(self) -> dict[str, object]:
        return {
            "version": SEC_IB1C_E_SCALE_READINESS_VERSION,
            "checkpoint_sha256": self.checkpoint_sha256,
            "quarter_sha256s": [list(item) for item in self.quarter_sha256s],
            "filing_count": self.filing_count,
            "amendment_count": self.amendment_count,
            "multi_owner_filing_count": self.multi_owner_filing_count,
            "missing_owner_identity_count": self.missing_owner_identity_count,
            "unresolved_link_count": self.unresolved_link_count,
            "missing_exact_acceptance_count": self.missing_exact_acceptance_count,
            "missing_parent_count": self.missing_parent_count,
            "missing_xml_count": self.missing_xml_count,
            "missing_metadata_count": self.missing_metadata_count,
            "legacy_ib1e_max_periods": LEGACY_IB1E_MAX_PERIODS,
            "legacy_ib1e_max_xml_sources": LEGACY_IB1E_MAX_XML_SOURCES,
            "blockers": list(self.blockers),
            "official_sec_source_authenticated": False,
            "complete_amendment_coverage_verified": False,
            "official_pit_security_master_verified": False,
            "trading_calendar_session_mapping_verified": False,
            "canonical_filter_authorized": False,
            "point_in_time_mapping_verified": False,
            "signal_authorized": False,
            "backtest_ready": False,
        }


def assess_declared_ib1ce_scale_readiness(
    checkpoint: Ib1ceScaleCheckpoint,
) -> Ib1ceScaleReadinessReport:
    """Require all 82 periods and report structural gaps without promotion."""

    if type(checkpoint) is not Ib1ceScaleCheckpoint:
        raise SecIb1cEScaleReadinessError("REFUSED: exact checkpoint required")
    checkpoint.__post_init__()
    if len(checkpoint.quarters) != len(EXPECTED_PERIODS):
        raise SecIb1cEScaleReadinessError("REFUSED: all 82 quarters are required")
    filings = tuple(row for quarter in checkpoint.quarters for row in quarter.filings)
    unresolved = _check_links(checkpoint.quarters)
    missing_acceptance = sum(row.accepted_at_utc is None for row in filings)
    missing_parent = sum(row.complete_parent_sha256 is None for row in filings)
    missing_xml = sum(row.complete_xml_sha256 is None for row in filings)
    missing_metadata = sum(row.acceptance_metadata_sha256 is None for row in filings)
    missing_owners = sum(not row.reporting_owner_ciks for row in filings)
    blockers = [
        "caller_declarations_do_not_authenticate_sec_source_or_completeness",
        "acceptance_timestamp_and_timezone_provenance_unverified",
        "official_amendment_link_and_coverage_unverified",
        "real_multi_owner_header_profile_unverified",
        "pit_security_master_and_share_class_mapping_missing",
        "trading_calendar_session_map_missing",
        "legacy_ib1e_16_period_cap_requires_streaming_successor",
    ]
    if len(filings) > LEGACY_IB1E_MAX_XML_SOURCES:
        blockers.append("legacy_ib1e_256_xml_cap_exceeded")
    if unresolved:
        blockers.append("amendment_links_unresolved")
    if missing_acceptance:
        blockers.append("exact_acceptance_timestamps_missing")
    if missing_parent:
        blockers.append("complete_parent_declarations_missing")
    if missing_xml:
        blockers.append("complete_xml_declarations_missing")
    if missing_metadata:
        blockers.append("acceptance_metadata_declarations_missing")
    if missing_owners:
        blockers.append("reporting_owner_identity_declarations_missing")
    return Ib1ceScaleReadinessReport(
        checkpoint_sha256=checkpoint.chain_sha256,
        quarter_sha256s=tuple(
            (quarter.period, quarter.quarter_sha256) for quarter in checkpoint.quarters
        ),
        filing_count=len(filings),
        amendment_count=sum(row.form_type == "4/A" for row in filings),
        multi_owner_filing_count=sum(len(row.reporting_owner_ciks) > 1 for row in filings),
        missing_owner_identity_count=missing_owners,
        unresolved_link_count=unresolved,
        missing_exact_acceptance_count=missing_acceptance,
        missing_parent_count=missing_parent,
        missing_xml_count=missing_xml,
        missing_metadata_count=missing_metadata,
        blockers=tuple(blockers),
    )


__all__ = [
    "SEC_IB1C_E_SCALE_READINESS_VERSION",
    "EXPECTED_PERIODS",
    "MAX_QUARTER_FILINGS",
    "MAX_TOTAL_FILINGS",
    "LEGACY_IB1E_MAX_PERIODS",
    "LEGACY_IB1E_MAX_XML_SOURCES",
    "MAX_REPORTING_OWNERS_PER_FILING",
    "SecIb1cEScaleReadinessError",
    "DeclaredIb1ceFiling",
    "DeclaredIb1ceQuarter",
    "Ib1ceScaleCheckpoint",
    "Ib1ceScaleReadinessReport",
    "append_declared_ib1ce_quarter",
    "assess_declared_ib1ce_scale_readiness",
]
