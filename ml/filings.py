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
from typing import Any, Mapping, Sequence

from ml.hashing import hash_payload

PROMPT_VERSION = "filing_extraction.v1"

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
_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*(?:\.\d+)?%?")


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
        if self.field.lower() in _FORBIDDEN_FIELDS:
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "prompt_version": self.prompt_version,
            "model_id": self.model_id,
            "source_documents": [d.to_dict() for d in self.source_documents],
            "claims": [c.to_dict() for c in self.claims],
            "generated_at": self.generated_at,
            "production_authoritative": False,
        }

    @property
    def input_hash(self) -> str:
        return hash_payload(
            {
                "ticker": self.ticker,
                "prompt_version": self.prompt_version,
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
    return token.replace(",", "").rstrip("%")


def _numbers_in(text: str) -> set[str]:
    return {_normalize_number(m.group()) for m in _NUMBER_PATTERN.finditer(text)}


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
        if claim.claim_kind == "direct_extraction":
            # Doc 12.2: "validate every number against supplied source text".
            # Only direct extractions are held to this -- an inference is
            # allowed to reason ABOUT the document, but it is labeled as such
            # and never presented as quoted fact.
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
    accepted = not issues
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
            "issues": [i.to_dict() for i in issues],
        },
        "error": None if accepted else ";".join(sorted(i.code for i in issues)),
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
