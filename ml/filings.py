"""Compatibility facade for the product-neutral filing extraction contract."""

from data.filing_extraction import (
    EXTRACTION_SCHEMA_VERSION,
    PROMPT_VERSION,
    ExtractedClaim,
    FilingExtraction,
    FilingExtractionError,
    SourceDocument,
    ValidationIssue,
    build_extraction_audit_record,
    sentiment_is_not_a_signal,
    validate_extraction,
)

__all__ = [
    "EXTRACTION_SCHEMA_VERSION",
    "PROMPT_VERSION",
    "ExtractedClaim",
    "FilingExtraction",
    "FilingExtractionError",
    "SourceDocument",
    "ValidationIssue",
    "build_extraction_audit_record",
    "sentiment_is_not_a_signal",
    "validate_extraction",
]
