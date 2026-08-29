"""Offline, non-executing contracts for the Insider Buying research lane.

This package deliberately has no network collection, outcome, portfolio,
broker, or scheduler surface. It contains immutable in-memory Form 4
structure, a fixture parser, and a caller-supplied SEC quarterly ZIP integrity
and raw-snapshot boundary.
"""

from research.insider_buying.contracts import (
    CANONICAL_SPEC,
    ClassificationOutcome,
    FilingCorpus,
    FilingEnvelope,
    ParsedFiling,
    ParsedTransaction,
    PublicAvailability,
    ReportingOwner,
    TransactionDiagnostic,
    build_filing_corpus,
)
from research.insider_buying.form4_xml import Form4ParseError, parse_form4_xml
from research.insider_buying.sec_bulk_snapshot import (
    ALLOWED_SEC_TABLES,
    LoadedSecBulkSnapshot,
    SecBulkMember,
    SecBulkSnapshotError,
    SecBulkSnapshotIdentity,
    SecBulkSource,
    REQUIRED_SEC_TABLES,
    inspect_sec_bulk_archive,
    load_sec_bulk_snapshot,
    write_sec_bulk_snapshot,
)

__all__ = [
    "ALLOWED_SEC_TABLES",
    "CANONICAL_SPEC",
    "ClassificationOutcome",
    "FilingCorpus",
    "FilingEnvelope",
    "Form4ParseError",
    "LoadedSecBulkSnapshot",
    "ParsedFiling",
    "ParsedTransaction",
    "PublicAvailability",
    "ReportingOwner",
    "REQUIRED_SEC_TABLES",
    "SecBulkMember",
    "SecBulkSnapshotError",
    "SecBulkSnapshotIdentity",
    "SecBulkSource",
    "TransactionDiagnostic",
    "build_filing_corpus",
    "inspect_sec_bulk_archive",
    "load_sec_bulk_snapshot",
    "parse_form4_xml",
    "write_sec_bulk_snapshot",
]
