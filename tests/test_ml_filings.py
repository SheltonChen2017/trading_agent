"""Tests for ml/filings.py (ML-8). The validator is the whole point of the
module, so it gets adversarial coverage: fabricated numbers, invented
excerpts, unsupported tickers, and attempts to smuggle an action field."""
from __future__ import annotations

import pytest

from ml.filings import (
    PROMPT_VERSION,
    ExtractedClaim,
    FilingExtraction,
    FilingExtractionError,
    SourceDocument,
    build_extraction_audit_record,
    sentiment_is_not_a_signal,
    validate_extraction,
)

_TEXT = (
    "NVIDIA Corporation reported revenue of 30,040 million dollars for the "
    "quarter. Management guided next-quarter revenue to approximately 32,500 "
    "million dollars, representing growth of 8.2%. Risks include supply "
    "constraints and export restrictions."
)


def _document(**overrides) -> SourceDocument:
    payload = {
        "document_id": "doc-1",
        "ticker": "NVDA",
        "published_at": "2026-07-30T21:00:00+00:00",
        "url": "https://example.invalid/nvda-q2",
        "text": _TEXT,
    }
    payload.update(overrides)
    return SourceDocument(**payload)


def _claim(**overrides) -> ExtractedClaim:
    payload = {
        "claim_kind": "direct_extraction",
        "field": "next_quarter_revenue_guidance",
        "value": "32,500 million dollars",
        "document_id": "doc-1",
        "supporting_excerpt": (
            "guided next-quarter revenue to approximately 32,500 million dollars"
        ),
    }
    payload.update(overrides)
    return ExtractedClaim(**payload)


def _extraction(**overrides) -> FilingExtraction:
    payload = {
        "ticker": "NVDA",
        "prompt_version": PROMPT_VERSION,
        "model_id": "claude-opus-5",
        "source_documents": (_document(),),
        "claims": (_claim(),),
        "generated_at": "2026-07-31T00:00:00+00:00",
    }
    payload.update(overrides)
    return FilingExtraction(**payload)


# --- contract validation ----------------------------------------------------


def test_a_faithful_extraction_validates_cleanly():
    assert validate_extraction(_extraction()) == ()


def test_source_document_hash_changes_when_the_text_is_revised():
    original = _document()
    revised = _document(text=_TEXT + " Updated after the fact.")
    assert original.content_hash != revised.content_hash


def test_document_requires_every_provenance_field():
    for field in ("document_id", "ticker", "published_at", "url", "text"):
        with pytest.raises(FilingExtractionError, match=field):
            _document(**{field: "  "})


def test_claim_rejects_an_unknown_kind():
    with pytest.raises(FilingExtractionError, match="claim_kind"):
        _claim(claim_kind="vibes")


def test_claim_rejects_an_execution_shaped_field():
    """Doc 12.2: 'never let prose create a TradeIntent.'"""
    for field in ("side", "shares", "order_type", "approved", "recommendation"):
        with pytest.raises(FilingExtractionError, match="execution-shaped"):
            _claim(field=field)


# --- the grounding checks that matter ---------------------------------------


def test_an_invented_excerpt_is_rejected():
    extraction = _extraction(
        claims=(_claim(supporting_excerpt="management is extremely confident"),)
    )
    issues = validate_extraction(extraction)
    assert "excerpt_not_in_source" in {i.code for i in issues}


def test_a_fabricated_number_is_rejected():
    """The core doc-12.2 rule: 'validate every number against supplied
    source text'. The excerpt here IS real -- only the asserted value is
    invented, which is exactly the subtle failure mode that matters."""
    extraction = _extraction(claims=(_claim(value="99,999 million dollars"),))
    issues = validate_extraction(extraction)
    assert "unsupported_number" in {i.code for i in issues}


def test_a_number_present_in_the_source_is_accepted():
    extraction = _extraction(
        claims=(
            _claim(
                field="reported_revenue",
                value="30,040 million dollars",
                supporting_excerpt="reported revenue of 30,040 million dollars",
            ),
        )
    )
    assert validate_extraction(extraction) == ()


def test_percentages_preserve_their_numeric_unit():
    extraction = _extraction(
        claims=(
            _claim(
                field="guided_growth",
                value="8.2%",
                supporting_excerpt="representing growth of 8.2%",
            ),
        )
    )
    assert validate_extraction(extraction) == ()


def test_model_inference_is_labeled_but_cannot_invent_numbers():
    """Inference changes presentation, not the source-of-facts rule."""
    extraction = _extraction(
        claims=(
            _claim(
                claim_kind="model_inference",
                field="guidance_tone",
                value="roughly 15% more optimistic than last quarter",
                supporting_excerpt="Management guided next-quarter revenue",
            ),
        )
    )
    assert "unsupported_number" in {i.code for i in validate_extraction(extraction)}
    assert extraction.claims[0].claim_kind == "model_inference"


def test_percent_cannot_be_sourced_from_an_unqualified_number():
    document = _document(text="Management described growth of 10 dollars.")
    extraction = _extraction(
        source_documents=(document,),
        claims=(
            _claim(
                field="growth",
                value="10%",
                supporting_excerpt="growth of 10 dollars",
            ),
        ),
    )
    assert "unsupported_number" in {i.code for i in validate_extraction(extraction)}


def test_direct_number_must_appear_in_its_supporting_excerpt():
    extraction = _extraction(
        claims=(
            _claim(
                value="8.2%",
                supporting_excerpt="Management guided next-quarter revenue",
            ),
        )
    )
    assert "number_not_in_supporting_excerpt" in {
        i.code for i in validate_extraction(extraction)
    }


def test_citing_an_unsupplied_document_is_rejected():
    extraction = _extraction(claims=(_claim(document_id="doc-does-not-exist"),))
    issues = validate_extraction(extraction)
    assert "unknown_document_id" in {i.code for i in issues}


def test_an_unsupported_ticker_is_rejected():
    extraction = _extraction(ticker="TSLA")
    issues = validate_extraction(extraction)
    assert "unsupported_ticker" in {i.code for i in issues}


def test_an_unknown_prompt_version_is_rejected():
    extraction = _extraction(prompt_version="something.v99")
    issues = validate_extraction(extraction)
    assert "unknown_prompt_version" in {i.code for i in issues}


def test_an_extraction_with_no_documents_is_rejected():
    extraction = _extraction(source_documents=(), claims=())
    issues = validate_extraction(extraction)
    assert "no_source_documents" in {i.code for i in issues}


def test_every_issue_is_reported_not_just_the_first():
    extraction = _extraction(
        ticker="TSLA",
        prompt_version="bad.v0",
        claims=(_claim(supporting_excerpt="not in the source at all"),),
    )
    codes = {i.code for i in validate_extraction(extraction)}
    assert {"unsupported_ticker", "unknown_prompt_version", "excerpt_not_in_source"} <= codes


# --- audit record -----------------------------------------------------------


def test_audit_record_matches_the_existing_ai_runs_shape():
    record = build_extraction_audit_record(_extraction(), [])
    assert record["function_name"] == "extract_filing_claims"
    assert record["prompt_version"] == PROMPT_VERSION
    assert record["success"] is True
    assert record["error"] is None
    assert len(record["input_hash"]) == 64
    assert record["response"]["direct_extraction_count"] == 1


def test_audit_record_records_a_rejection_with_its_codes():
    extraction = _extraction(claims=(_claim(value="99,999 million dollars"),))
    issues = validate_extraction(extraction)
    record = build_extraction_audit_record(extraction, issues)
    assert record["success"] is False
    assert "unsupported_number" in record["error"]


def test_audit_record_cannot_be_tricked_with_an_empty_issue_list():
    extraction = _extraction(claims=(_claim(value="99,999 million dollars"),))
    record = build_extraction_audit_record(extraction, [])
    assert record["success"] is False
    assert "unsupported_number" in record["error"]


def test_audit_record_stores_document_hashes_not_raw_text():
    record = build_extraction_audit_record(_extraction(), [])
    hashes = record["response"]["source_document_hashes"]
    assert all(len(h) == 64 for h in hashes)
    assert _TEXT not in str(record)


def test_input_hash_is_stable_for_identical_inputs():
    assert _extraction().input_hash == _extraction().input_hash


def test_extraction_payload_is_never_authoritative_and_is_serializable():
    import json

    payload = _extraction().to_dict()
    assert payload["production_authoritative"] is False
    json.dumps(payload)


def test_sentiment_caveat_is_available_verbatim():
    assert "not a trade signal" in sentiment_is_not_a_signal()
