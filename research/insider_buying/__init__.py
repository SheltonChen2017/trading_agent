"""Offline, non-executing contracts for the Insider Buying research lane.

This package deliberately has no collection, outcome, portfolio, broker, or
scheduler surface. Its first milestone is limited to immutable in-memory
Form 4 structure, named classification outcomes, and fixture parsing.
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
    build_filing_corpus,
)
from research.insider_buying.form4_xml import Form4ParseError, parse_form4_xml

__all__ = [
    "CANONICAL_SPEC",
    "ClassificationOutcome",
    "FilingCorpus",
    "FilingEnvelope",
    "Form4ParseError",
    "ParsedFiling",
    "ParsedTransaction",
    "PublicAvailability",
    "ReportingOwner",
    "build_filing_corpus",
    "parse_form4_xml",
]
