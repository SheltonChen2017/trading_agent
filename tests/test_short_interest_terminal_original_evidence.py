"""Fabricated quotations only, never actual original/cashflow evidence."""
from __future__ import annotations

import dataclasses
import json

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.terminal_original_evidence as contract

NOW = "2026-10-14T00:00:00Z"


def descriptor(case="TWTR"):
    cik = "0001234567" if case == "TWTR" else "0002345678"
    return {"request_id": "original-" + case, "case": case, "method": "GET",
            "url": "https://www.sec.gov/Archives/edgar/data/" + str(int(cik)) + "/original.htm",
            "headers": {"Accept": "text/html", "User-Agent": "fabricated-only"},
            "issuer_CIK": cik, "filing_date": "2022-10-27" if case == "TWTR" else "2023-05-01",
            "accession_number": cik + "-22-000001", "source_row_origin": {"source_file_sha256": "a" * 64}}


def document(raw=None, *, case="TWTR", media="text/html"):
    if raw is None:
        raw = (b"<html><style>paid $99 per share</style><script>paid $98 per share</script>"
               b"<p>Each share of Class A common stock has a right to receive USD 12.50 per share, "
               b"except treasury shares and holders seeking appraisal.</p>"
               b"<p>Payment is conditional upon surrender to the paying agent. Closing occurred October 27, 2022.</p></html>")
    value = descriptor(case)
    return contract.CapturedTerminalOriginal(canonical_json(value), hash_payload(value), raw, hash_bytes(raw), NOW,
                                            media, "b" * 64, "c" * 64)


def test_frozen_policy_digest_and_private_semantic_boundary():
    protocol = contract.evidence_protocol()
    assert hash_payload(protocol) == contract.PROTOCOL_SHA256
    assert protocol["authority"]["terminal_economics_admitted"] is False
    assert protocol["authority"]["payment_cash_settlement_verified"] is False


def test_exact_quote_cues_normalized_digest_and_raw_origin_without_economic_admission():
    source = document()
    report = contract.qualify_terminal_original_evidence((source,), retrieved_at=NOW)
    payload = report.to_payload()
    parsed = payload["documents"][0]
    text = parsed["normalized_text"]
    assert "$99" not in text and "$98" not in text
    assert "USD 12.50 per share" in text
    assert parsed["raw_document_sha256"] == source.raw_sha256
    assert parsed["normalized_text_UTF8_sha256"] == hash_bytes(text.encode())
    assert {row["category"] for row in parsed["assertions"]} == {
        "consideration_language", "class_eligibility_language", "exclusion_or_election_language",
        "payment_language", "effective_or_completion_language"}
    for assertion in parsed["assertions"]:
        assert assertion["assertion_id"] == hash_payload({"policy_sha256": contract.PROTOCOL_SHA256,
            "raw_document_sha256": source.raw_sha256, "normalized_text_UTF8_sha256": parsed["normalized_text_UTF8_sha256"],
            "category": assertion["category"], "cue_start": assertion["cue"]["start_character"],
            "cue_end": assertion["cue"]["end_character"]})
        for name in ("quote", "cue"):
            span = assertion[name]
            assert text[span["start_character"]:span["end_character"]] == span["text"]
            assert span["UTF8_sha256"] == hash_bytes(span["text"].encode())
        assert assertion["consideration_cash_per_share"] is None
        assert assertion["eligible_share_class"] is None
        assert assertion["payment_date"] is assertion["effective_cash_available_at"] is None
        assert assertion["authority"]["terminal_economics_admitted"] is False
        assert assertion["authority"]["payment_cash_settlement_verified"] is False
    lexical = [item for row in parsed["assertions"] for item in row["lexical_candidates"]]
    assert any(item["span"]["text"] == "USD 12.50" for item in lexical)
    assert any(item["span"]["text"] == "October 27, 2022" for item in lexical)
    assert all(item["financial_or_payment_meaning_admitted"] is False for item in lexical)


@pytest.mark.parametrize("text", [
    "Aggregate deal size $12,500,000. Closing October 27, 2022. No per-share claim.",
    "The merger completed January 2, 2023. Payment will be made upon surrender of certificates.",
    "Treasury shares were cancelled without payment; appraisal holders excluded from merger consideration.",
    "$12.50 per share may be paid if a shareholder elects cash instead of stock.",
])
def test_money_units_conditions_completion_or_exclusions_never_create_cash_event(text):
    report = contract.qualify_terminal_original_evidence((document(text.encode(), media="text/plain"),), retrieved_at=NOW)
    payload = report.to_payload()
    assert payload["authority"]["actual_outcome_looks"] == payload["authority"]["qc_attempts"] == 0
    for row in payload["documents"][0]["assertions"]:
        assert row["consideration_cash_per_share"] is None
        assert row["payment_date"] is None and row["eligible_share_class"] is None


def test_entities_inline_tags_and_blocks_have_deterministic_normalized_quotes():
    source = document(b"<p>USD&nbsp;12.<span>50</span> per share</p><p>Class A common stock</p>")
    payload = contract.qualify_terminal_original_evidence((source,), retrieved_at=NOW).to_payload()
    assert payload["documents"][0]["normalized_text"] == "USD 12.50 per share Class A common stock"


def test_plain_text_angle_brackets_are_not_discarded_as_HTML():
    source = document(b"Payment condition x < 3 and y > 2", media="text/plain")
    assert contract.qualify_terminal_original_evidence((source,), retrieved_at=NOW).to_payload()["documents"][0]["normalized_text"] == "Payment condition x < 3 and y > 2"


@pytest.mark.parametrize("raw,media,reason", [
    (b"\xff per share", "text/plain", "original_not_UTF8"),
    (b"per share", "text/html; charset=windows-1252", "unsupported_declared_encoding"),
])
def test_no_lossy_or_guessed_encoding(raw, media, reason):
    with pytest.raises(contract.TerminalOriginalEvidenceError, match=reason):
        contract.qualify_terminal_original_evidence((document(raw, media=media),), retrieved_at=NOW)


def test_cue_cap_is_explicit_not_silent_exhaustive_semantics():
    source = document(("per share " * 140).encode(), media="text/plain")
    parsed = contract.qualify_terminal_original_evidence((source,), retrieved_at=NOW).to_payload()["documents"][0]
    row = next(row for row in parsed["cue_inventory"] if row["category"] == "consideration_language")
    assert row == {"category": "consideration_language", "total_cues": 140, "quoted_cues": 128, "unquoted_cues": 12}


@pytest.mark.parametrize("field,value", [("raw_sha256", "d" * 64), ("descriptor_sha256", "d" * 64),
    ("received_at", "2026-10-14T00:00:00"), ("content_type", "application/json"), ("original_protocol_sha256", "invalid")])
def test_capture_digest_media_and_clock_refuse(field, value):
    with pytest.raises(contract.TerminalOriginalEvidenceError):
        dataclasses.replace(document(), **{field: value})


def test_duplicate_document_or_descriptor_refuses_before_evidence():
    source = document()
    with pytest.raises(contract.TerminalOriginalEvidenceError, match="duplicate_original"):
        contract.qualify_terminal_original_evidence((source, source), retrieved_at=NOW)
    with pytest.raises(contract.TerminalOriginalEvidenceError, match="precedes_capture"):
        contract.qualify_terminal_original_evidence((source,), retrieved_at="2026-10-13T23:59:59Z")


def test_subclass_cannot_supply_override_source_or_evidence():
    class Substitute(contract.CapturedTerminalOriginal):
        pass
    source = document()
    with pytest.raises(contract.TerminalOriginalEvidenceError, match="exact_original"):
        Substitute(*(getattr(source, field.name) for field in dataclasses.fields(source)))


def test_detached_payload_and_retained_source_mutation_are_sealed():
    source = document()
    report = contract.qualify_terminal_original_evidence((source,), retrieved_at=NOW)
    first = report.to_payload()
    first["documents"][0]["assertions"][0]["payment_date"] = "2022-10-27"
    assert report.to_payload()["documents"][0]["assertions"][0]["payment_date"] is None
    object.__setattr__(source, "raw", b"changed source")
    with pytest.raises(contract.TerminalOriginalEvidenceError):
        report.to_payload()


def test_coherent_source_replacement_and_equality_spoof_cannot_change_private_assertions():
    source = document()
    report = contract.qualify_terminal_original_evidence((source,), retrieved_at=NOW)
    altered = report.to_payload()
    altered["documents"][0]["assertions"][0]["payment_date"] = "2022-10-27"
    altered["report_sha256"] = hash_payload({name: value for name, value in altered.items() if name != "report_sha256"})
    class EqualitySpoof(str):
        def __eq__(self, other):
            return True
    object.__setattr__(report, "_payload_json", EqualitySpoof(canonical_json(altered)))
    with pytest.raises(contract.TerminalOriginalEvidenceError):
        report.to_payload()
    clean = contract.qualify_terminal_original_evidence((source,), retrieved_at=NOW)
    replacement = b"Payment language from a different source."
    object.__setattr__(source, "raw", replacement)
    object.__setattr__(source, "raw_sha256", hash_bytes(replacement))
    with pytest.raises(contract.TerminalOriginalEvidenceError, match="sealed_evidence_changed"):
        clean.to_payload()
