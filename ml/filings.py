"""ML-8: structured filing/transcript extraction (strategy doc section 12).

The governing distinction (doc 12): the language model is an EXTRACTOR and
ORGANIZER, "not a source of market facts". Every number it returns must be
verifiable against the supplied source text, and anything it cannot support
is rejected rather than trusted.

This module deliberately contains no API client. It owns the CONTRACT and
the VALIDATION -- the deterministic part that has to be right -- and takes
whatever produced the extraction as an argument. That mirrors
assistant/llm/'s existing provider/validator split, keeps this unit-testable
with zero network access, and means a provider swap cannot quietly change
what counts as an acceptable extraction.

Hard boundary (doc 12.2): "never let prose create a TradeIntent". Nothing
in this file imports, constructs, or returns anything execution-shaped, and
`validate_extraction()` rejects an extraction that contains action fields
even if a model tries to emit them.
"""
from __future__ import annotations

import dataclasses
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

from ml.hashing import hash_payload

PROMPT_VERSION = "filing_extraction.v1"
EXTRACTION_SCHEMA_VERSION = "1.0"

# Doc 3.2's forbidden output fields, enforced here too: an extraction is a
# statement about a document, never an instruction about an order.
_FORBIDDEN_FIELDS = frozenset(
    {
        "side", "shares", "quantity", "order_type", "limit_price", "stop_price",
        "approved", "execute", "authorization", "target_weight", "trade_intent",
        "recommendation", "action",
    }
)

# Matches a number the model claims appeared in the source: optional sign,
# digits with optional thousands separators, optional decimal part, optional
# trailing percent.
_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(?:[$€£]\s*)?-?\d[\d,]*(?:\.\d+)?"
    r"(?:\s*(?:%|bps?|thousand|million|billion|trillion|[kmbt]))?",
    re.IGNORECASE,
)
_DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_MONTH_NAME = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?"
)
_MONTH_FIRST_DATE_PATTERN = re.compile(
    rf"\b(?:{_MONTH_NAME})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,\s*|\s+)\d{{4}}\b",
    re.IGNORECASE,
)
_DAY_FIRST_DATE_PATTERN = re.compile(
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTH_NAME})\.?\s+\d{{4}}\b",
    re.IGNORECASE,
)


class FilingExtractionError(ValueError):
    """An extraction cannot be trusted as a faithful reading of its source."""


@dataclasses.dataclass(frozen=True)
class SourceDocument:
    """One document an extraction is allowed to draw from."""

    document_id: str
    ticker: str
    published_at: str
    url: str
    text: str

    def __post_init__(self) -> None:
        for name in ("document_id", "ticker", "published_at", "url", "text"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise FilingExtractionError(f"{name} must be a non-empty string")
        try:
            published = datetime.fromisoformat(self.published_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FilingExtractionError("published_at must be a valid ISO timestamp") from exc
        if published.tzinfo is None or published.utcoffset() is None:
            raise FilingExtractionError("published_at must be timezone-aware")

    @property
    def content_hash(self) -> str:
        """Hash of the exact text an extraction was made from (doc 12.2:
        "store source-document hashes"). If the source is later revised,
        this changes, and the old extraction is visibly stale rather than
        silently attributed to the new text."""
        return hash_payload(
            {
                "document_id": self.document_id,
                "ticker": self.ticker,
                "published_at": self.published_at,
                "url": self.url,
                "text": self.text,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "ticker": self.ticker,
            "published_at": self.published_at,
            "url": self.url,
            "content_hash": self.content_hash,
        }


@dataclasses.dataclass(frozen=True)
class ExtractedClaim:
    """One claim, with mandatory provenance (doc 12.1).

    `claim_kind` separates DIRECT EXTRACTION from MODEL INFERENCE, which
    doc 12.2 requires be "clearly separate". A quoted guidance figure and
    the model's opinion about that figure are not the same epistemic
    object and must never render identically.
    """

    KINDS = ("direct_extraction", "model_inference")

    claim_kind: str
    field: str
    value: str
    document_id: str
    supporting_excerpt: str

    def __post_init__(self) -> None:
        if self.claim_kind not in self.KINDS:
            raise FilingExtractionError(
                f"claim_kind must be one of {self.KINDS}, got {self.claim_kind!r}"
            )
        for name in ("field", "value", "document_id", "supporting_excerpt"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise FilingExtractionError(f"{name} must be a non-empty string")
        normalized_field = re.sub(r"[^a-z0-9]+", "_", self.field.strip().lower()).strip("_")
        field_tokens = set(normalized_field.split("_"))
        if normalized_field in _FORBIDDEN_FIELDS or field_tokens & _FORBIDDEN_FIELDS:
            raise FilingExtractionError(
                f"field {self.field!r} is an execution-shaped field; an extraction "
                "may describe a document, never instruct a trade (doc 12.2)"
            )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class FilingExtraction:
    ticker: str
    prompt_version: str
    model_id: str
    source_documents: tuple[SourceDocument, ...]
    claims: tuple[ExtractedClaim, ...]
    generated_at: str
    schema_version: str = EXTRACTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("ticker", "prompt_version", "model_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise FilingExtractionError(f"{name} must be a non-empty string")
        if self.schema_version != EXTRACTION_SCHEMA_VERSION:
            raise FilingExtractionError(
                f"schema_version must be {EXTRACTION_SCHEMA_VERSION!r}"
            )
        if not isinstance(self.source_documents, tuple) or not all(
            isinstance(item, SourceDocument) for item in self.source_documents
        ):
            raise FilingExtractionError("source_documents must be a tuple of SourceDocument")
        if not isinstance(self.claims, tuple) or not all(
            isinstance(item, ExtractedClaim) for item in self.claims
        ):
            raise FilingExtractionError("claims must be a tuple of ExtractedClaim")
        try:
            generated = datetime.fromisoformat(self.generated_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise FilingExtractionError("generated_at must be a valid ISO timestamp") from exc
        if generated.tzinfo is None or generated.utcoffset() is None:
            raise FilingExtractionError("generated_at must be timezone-aware")
        for document in self.source_documents:
            published = datetime.fromisoformat(
                document.published_at.replace("Z", "+00:00")
            )
            if generated < published:
                raise FilingExtractionError(
                    "generated_at cannot precede a cited document's published_at"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "prompt_version": self.prompt_version,
            "model_id": self.model_id,
            "source_documents": [d.to_dict() for d in self.source_documents],
            "claims": [c.to_dict() for c in self.claims],
            "generated_at": self.generated_at,
            "schema_version": self.schema_version,
            "production_authoritative": False,
        }

    @property
    def input_hash(self) -> str:
        return hash_payload(
            {
                "ticker": self.ticker,
                "prompt_version": self.prompt_version,
                "schema_version": self.schema_version,
                "documents": sorted(d.content_hash for d in self.source_documents),
            }
        )


@dataclasses.dataclass(frozen=True)
class ValidationIssue:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


def _normalize_number(token: str) -> str:
    compact = re.sub(r"\s+", "", token.lower().replace(",", ""))
    match = re.fullmatch(
        r"(?P<currency>[$€£])?(?P<number>-?\d+(?:\.\d+)?)"
        r"(?P<unit>%|bps?|thousand|million|billion|trillion|[kmbt])?",
        compact,
    )
    if match is None:
        return compact
    try:
        number = Decimal(match.group("number"))
    except InvalidOperation:
        return compact
    canonical_number = format(number.normalize(), "f")
    if canonical_number == "-0":
        canonical_number = "0"
    return f"{match.group('currency') or ''}{canonical_number}{match.group('unit') or ''}"


def _numbers_in(text: str) -> set[str]:
    return {_normalize_number(m.group()) for m in _NUMBER_PATTERN.finditer(text)}


def _normalize_date_token(token: str) -> str:
    normalized = token.lower().replace(",", " ").replace(".", " ")
    normalized = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _dates_in(text: str) -> set[str]:
    """Find ISO and common written dates without losing the month name.

    Comparing only the numbers in a date lets ``July 31, 2026`` support a
    fabricated ``August 31, 2026`` claim.  The month therefore remains part
    of the normalized token.
    """
    matches = list(_DATE_PATTERN.finditer(text))
    matches.extend(_MONTH_FIRST_DATE_PATTERN.finditer(text))
    matches.extend(_DAY_FIRST_DATE_PATTERN.finditer(text))
    return {_normalize_date_token(match.group()) for match in matches}


def validate_extraction(
    extraction: FilingExtraction, *, allowed_tickers: Sequence[str] = ()
) -> tuple[ValidationIssue, ...]:
    """Deterministic acceptance rules for one extraction (doc 12.2).

    Returns every issue found rather than raising on the first, so a caller
    reporting a rejection can show all of what was wrong. An extraction with
    ANY issue must be treated as unusable -- there is no partial-credit path
    where some claims are kept.
    """
    issues: list[ValidationIssue] = []
    documents_by_id = {d.document_id: d for d in extraction.source_documents}
    if len(documents_by_id) != len(extraction.source_documents):
        issues.append(
            ValidationIssue(
                "duplicate_document_id", "source document IDs must be unique"
            )
        )
    if not documents_by_id:
        issues.append(
            ValidationIssue("no_source_documents", "extraction cites no source documents")
        )
    if extraction.prompt_version != PROMPT_VERSION:
        issues.append(
            ValidationIssue(
                "unknown_prompt_version",
                f"expected {PROMPT_VERSION!r}, got {extraction.prompt_version!r}",
            )
        )

    permitted_tickers = {t.upper() for t in allowed_tickers} or {
        d.ticker.upper() for d in extraction.source_documents
    }
    if extraction.ticker.upper() not in permitted_tickers:
        issues.append(
            ValidationIssue(
                "unsupported_ticker",
                f"{extraction.ticker!r} is not among the supplied documents' tickers",
            )
        )

    for document in extraction.source_documents:
        if document.ticker.upper() != extraction.ticker.upper():
            issues.append(
                ValidationIssue(
                    "document_ticker_mismatch",
                    f"document {document.document_id!r} is for {document.ticker!r}, "
                    f"not extraction ticker {extraction.ticker!r}",
                )
            )

    for index, claim in enumerate(extraction.claims):
        path = f"claims[{index}]"
        document = documents_by_id.get(claim.document_id)
        if document is None:
            issues.append(
                ValidationIssue(
                    "unknown_document_id",
                    f"{path} cites {claim.document_id!r}, which was not supplied",
                )
            )
            continue
        # The excerpt must genuinely appear in the source text. This is the
        # single most important check here: it is what makes a citation a
        # citation rather than a plausible-sounding invention.
        if claim.supporting_excerpt not in document.text:
            issues.append(
                ValidationIssue(
                    "excerpt_not_in_source",
                    f"{path} excerpt does not appear verbatim in {claim.document_id!r}",
                )
            )
            continue
        # Doc 12.2 says EVERY number must be validated against the supplied
        # source. Labeling a claim as inference does not license invented
        # amounts or percentages; inference changes presentation, not truth.
        claimed_numbers = _numbers_in(claim.value)
        source_numbers = _numbers_in(document.text)
        unsupported = sorted(claimed_numbers - source_numbers)
        if unsupported:
            issues.append(
                ValidationIssue(
                    "unsupported_number",
                    f"{path} asserts number(s) {unsupported} absent from the source",
                )
            )
        if claim.claim_kind == "direct_extraction":
            excerpt_numbers = _numbers_in(claim.supporting_excerpt)
            unsupported_in_excerpt = sorted(claimed_numbers - excerpt_numbers)
            if unsupported_in_excerpt:
                issues.append(
                    ValidationIssue(
                        "number_not_in_supporting_excerpt",
                        f"{path} direct-extraction number(s) {unsupported_in_excerpt} "
                        "are not present in its cited excerpt",
                    )
                )
        claimed_dates = _dates_in(claim.value)
        source_dates = _dates_in(document.text)
        unsupported_dates = sorted(claimed_dates - source_dates)
        if unsupported_dates:
            issues.append(
                ValidationIssue(
                    "unsupported_date",
                    f"{path} asserts date(s) {unsupported_dates} absent from the source",
                )
            )
        if claim.claim_kind == "direct_extraction":
            excerpt_dates = _dates_in(claim.supporting_excerpt)
            dates_missing_from_excerpt = sorted(claimed_dates - excerpt_dates)
            if dates_missing_from_excerpt:
                issues.append(
                    ValidationIssue(
                        "date_not_in_supporting_excerpt",
                        f"{path} direct-extraction date(s) {dates_missing_from_excerpt} "
                        "are not present in its cited excerpt",
                    )
                )

    return tuple(issues)


def build_extraction_audit_record(
    extraction: FilingExtraction, issues: Sequence[ValidationIssue]
) -> dict[str, Any]:
    """Audit payload for assistant.storage.AssistantStore.record_ai_run().

    Reuses the project's existing `ai_runs` audit table rather than adding a
    parallel one (doc 12.2: "use the existing AI-run audit and committee
    validation patterns where applicable"), so every LLM call this project
    makes -- committee reviews and filing extractions alike -- lands in one
    queryable log.
    """
    # Never let a caller accidentally (or deliberately) pass an empty issue
    # list for an invalid extraction and create an audit record that says it
    # was accepted. Re-run the deterministic validator here and preserve any
    # additional provider/workflow issues supplied by the caller.
    combined: list[ValidationIssue] = list(validate_extraction(extraction))
    for issue in issues:
        if not isinstance(issue, ValidationIssue):
            raise FilingExtractionError("audit issues must be ValidationIssue values")
        if issue not in combined:
            combined.append(issue)
    accepted = not combined
    return {
        "function_name": "extract_filing_claims",
        "model": extraction.model_id,
        "prompt_version": extraction.prompt_version,
        "input_hash": extraction.input_hash,
        "success": accepted,
        "response": {
            "accepted": accepted,
            "ticker": extraction.ticker,
            "claim_count": len(extraction.claims),
            "direct_extraction_count": sum(
                1 for c in extraction.claims if c.claim_kind == "direct_extraction"
            ),
            "inference_count": sum(
                1 for c in extraction.claims if c.claim_kind == "model_inference"
            ),
            "source_document_hashes": sorted(
                d.content_hash for d in extraction.source_documents
            ),
            "issues": [i.to_dict() for i in combined],
        },
        "error": None if accepted else ";".join(sorted(i.code for i in combined)),
    }


def sentiment_is_not_a_signal() -> str:
    """Doc 12.2's standing caveat, as an importable string so any surface
    displaying extraction output can render it verbatim rather than
    paraphrasing it into something weaker."""
    return (
        "Sentiment alone is not a trade signal. Any numeric feature derived "
        "from this text must go through the same point-in-time dataset and "
        "out-of-sample research process as every other feature before it can "
        "support any claim."
    )
