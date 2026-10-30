"""Independent invented-only probes of provisional direct-NC routes."""
from __future__ import annotations

import hashlib
import json

import pytest

from research import insider_buying_sec_feed_nc_route_v1 as m


CONTACT = "invented-route-private@unit.test"
ACCESSION = "0123456789-20-123456"
SECOND = "0123456789-20-123457"


def _nc(accession=ACCESSION, *, form="4", prefix=b"", group=b"", body=b"invented opaque document text"):
    front = (b"<SUBMISSION>\n<ACCESSION-NUMBER>"+accession.encode()+b"\n<TYPE>"+form.encode()
        +b"\n<PUBLIC-DOCUMENT-COUNT>1\n<FILING-DATE>20201008\n"+prefix+group)
    return (front+b"<DOCUMENT>\n<TYPE>"+form.encode()+b"\n<SEQUENCE>1\n<FILENAME>unreturned.xml\n<TEXT>\n"
        +body+b"\n</TEXT>\n</DOCUMENT>\n</SUBMISSION>\n")


def _one(raw, **kwargs):
    return m.assess_nc_route(raw, privacy_contact=CONTACT, fixture_only=True, **kwargs)


def _batch(raws, consumed=frozenset(), **kwargs):
    return m.assess_nc_route_batch(tuple(raws), consumed_accessions=consumed,
        privacy_contact=CONTACT, fixture_only=True, **kwargs)


def test_review_route_claim_is_private_provisional_exact_original_and_public_copy_is_detached():
    raw = _nc(body=b"<ownershipDocument>private-invented-financial-text</ownershipDocument>")
    assessed = _one(raw)
    claim = assessed.claim
    assert claim is not None and claim.accession_number == ACCESSION and claim.form_type == "4"
    assert claim.filing_date == "2020-10-08" and claim.public_document_count == 1
    assert claim.payload_bytes() == raw
    public = assessed.public_witness()
    assert public["route_claim_available"] is True
    assert public["acceptance_evidence"] == "not_established_no_clock_substitution"
    rendered = json.dumps(public)+repr(assessed)+repr(claim)
    for forbidden in (ACCESSION, "20201008", "2020-10-08", "unreturned.xml", "private-invented-financial-text",
            hashlib.sha256(raw).hexdigest(), CONTACT):
        assert forbidden not in rendered
    public["authority"]["backtesting_ready"] = True
    assert assessed.public_witness()["authority"]["backtesting_ready"] is False


def test_review_malformed_inline_canonical_accession_shadow_quarantines_all_copies():
    valid = _nc()
    malformed = _nc().replace(b"<ACCESSION-NUMBER>"+ACCESSION.encode()+b"\n",
        b"<ACCESSION-NUMBER>"+ACCESSION.encode()+b"</UNKNOWN>\n", 1)
    assert _one(malformed).claim is None
    result = _batch((valid, malformed))
    assert result.eligible_claims() == ()
    assert result.public_witness()["member_dispositions"] == ["duplicate_route_all_copies_quarantined"]*2


@pytest.mark.parametrize("field", [b"ACCESSION-NUMBER", b"TYPE", b"PUBLIC-DOCUMENT-COUNT", b"FILING-DATE"])
def test_review_equal_duplicate_direct_identity_fields_never_deduplicate_into_route(field):
    raw = _nc()
    line = next(line for line in raw.splitlines() if line.startswith(b"<"+field+b">"))
    raw = raw.replace(line+b"\n", line+b"\n"+line+b"\n", 1)
    assert _one(raw).claim is None


@pytest.mark.parametrize("extra", [b"<UNKNOWN>invented\n", b"<UNKNOWN>\n</UNKNOWN>\n",
    b"<HEADER>\n</HEADER>\n", b"<TYPE>4</TYPE>\n", b"<FILING-DATE>20201008</WRONG>\n"])
def test_review_unknown_inline_or_wrapper_grammar_cannot_mint_route(extra):
    assert _one(_nc(prefix=extra)).claim is None


@pytest.mark.parametrize("tag", ["TIMESTAMP", "PAPER", "PAC", "DELETION", "PRIVATE-TO-PUBLIC", "VERSION", "CORRECTION"])
def test_review_status_or_control_lexemes_remain_unqualified(tag):
    result = _one(_nc(prefix=("<"+tag+">20201008120000\n").encode()))
    assert result.claim is None
    assert result.public_witness()["authority"]["paper_PAC_or_release_lineage_resolved"] is False


def test_review_required_route_fields_inside_nested_registrant_cannot_supply_front():
    nested = (b"<FILER>\n<COMPANY-DATA>\n<CONFORMED-NAME>invented issuer\n<CIK>123456789\n"
        b"<ACCESSION-NUMBER>"+ACCESSION.encode()+b"\n</COMPANY-DATA>\n</FILER>\n")
    raw = _nc(group=nested).replace(b"<ACCESSION-NUMBER>"+ACCESSION.encode()+b"\n", b"", 1)
    assert _one(raw).claim is None


def test_review_front_fields_cannot_resume_after_closed_registrant_group():
    group = (b"<FILER>\n<COMPANY-DATA>\n<CONFORMED-NAME>invented issuer\n<CIK>123456789\n"
        b"</COMPANY-DATA>\n</FILER>\n")
    assert _one(_nc(group=group)).claim is not None
    assert _one(_nc(group=group+b"<PERIOD>20200930\n")).claim is None


def test_review_group_capacity_is_exact_whole_refusal_not_grammar_failure():
    group = (b"<FILER>\n<COMPANY-DATA>\n<CONFORMED-NAME>invented issuer\n<CIK>123456789\n"
        b"</COMPANY-DATA>\n</FILER>\n")
    raw = _nc(group=group)
    assert _one(raw, limits=m.NCRouteLimits(groups=2)).claim is not None
    with pytest.raises(m.NCRouteError) as caught:
        _one(raw, limits=m.NCRouteLimits(groups=1))
    assert (caught.value.phase, caught.value.code) == ("capacity", "group_count_bound")


def test_review_TEXT_is_opaque_not_a_replacement_route_or_acceptance_source():
    text = (b"<ACCESSION-NUMBER>"+SECOND.encode()+b"\n<ACCEPTANCE-DATETIME>20201008121212\n"
        b"<SOURCE>17\n<ownershipDocument/>")
    result = _one(_nc(body=text))
    assert result.claim is not None and result.claim.accession_number == ACCESSION
    assert result.public_witness()["canonical_preamble_accession_occurrences"] == 1
    assert result.public_witness()["authority"]["acceptance_or_availability_or_PIT_verified"] is False


@pytest.mark.parametrize("form", ["4", "4/A"])
def test_review_same_accession_distinct_payloads_quarantine_every_copy_not_first_or_latest(form):
    result = _batch((_nc(), _nc(form=form, body=b"different invented document"), _nc(SECOND)))
    assert tuple(index for index, _ in result.eligible_claims()) == (2,)
    assert result.public_witness()["member_dispositions"][:2] == ["duplicate_route_all_copies_quarantined"]*2


def test_review_consumed_route_is_not_released_and_batch_preserves_unmatched_rows():
    raw = _nc(SECOND).replace(b"<FILING-DATE>20201008", b"<FILING-DATE>not-a-date")
    result = _batch((_nc(), raw), frozenset({ACCESSION}))
    assert result.eligible_claims() == () and result.bound_consumed_accessions() == frozenset({ACCESSION})
    public = result.public_witness()
    assert public["members"] == 2 and public["payload_bytes"] == len(_nc())+len(raw)
    assert public["member_dispositions"] == ["prior_consumed_route_quarantined", "unsupported_or_ambiguous_structure"]


@pytest.mark.parametrize("contact", [CONTACT, "invented-route-%70rivate@unit.test", "invented-route-private&#64;unit.test"])
def test_review_encoded_contact_refuses_even_invalid_payload_before_parser_or_hash(monkeypatch, contact):
    raw = b"invalid invented body\n"+contact.encode()
    monkeypatch.setattr(m, "_assessment", lambda *a, **k: pytest.fail("parsed before complete privacy"))
    monkeypatch.setattr(hashlib, "sha256", lambda *a, **k: pytest.fail("source hashed before privacy"))
    with pytest.raises(m.NCRouteError) as caught:
        _one(raw)
    assert (caught.value.phase, caught.value.code) == ("privacy", "finite_payload_screen_refused")


def test_review_late_member_privacy_precedes_first_batch_claim(monkeypatch):
    monkeypatch.setattr(m, "_assessment", lambda *a, **k: pytest.fail("first claim preceded late member privacy"))
    with pytest.raises(m.NCRouteError) as caught:
        _batch((_nc(), _nc(SECOND, body=b"invented-route-private&#64;unit.test")))
    assert (caught.value.phase, caught.value.code) == ("privacy", "finite_payload_screen_refused")


@pytest.mark.parametrize("limits,code", [
    (m.NCRouteLimits(payload_bytes=1), "payload_byte_bound"),
    (m.NCRouteLimits(lines=2), "line_count_bound"),
    (m.NCRouteLimits(line_bytes=5), "line_byte_bound"),
    (m.NCRouteLimits(preamble_bytes=20), "preamble_byte_bound"),
])
def test_review_payload_and_preamble_capacities_refuse_whole_unit(limits, code):
    with pytest.raises(m.NCRouteError) as caught:
        _one(_nc(), limits=limits)
    assert (caught.value.phase, caught.value.code) == ("capacity", code)


@pytest.mark.parametrize("limits,code", [
    (m.NCRouteLimits(members=1), "member_count_bound"),
    (m.NCRouteLimits(batch_bytes=1), "batch_byte_bound"),
])
def test_review_batch_capacity_refusal_precedes_any_member_assessment(monkeypatch, limits, code):
    monkeypatch.setattr(m, "_assessment", lambda *a, **k: pytest.fail("partial convenient batch assessed"))
    with pytest.raises(m.NCRouteError) as caught:
        _batch((_nc(), _nc(SECOND)), limits=limits)
    assert (caught.value.phase, caught.value.code) == ("capacity", code)


@pytest.mark.parametrize("kind", ["extra", "ready", "bool_count", "object", "recursive", "nonfinite"])
def test_review_public_witness_rejects_forgery_with_finite_local_error(kind):
    value = _one(_nc()).public_witness()
    if kind == "extra": value["raw_private_value"] = CONTACT
    elif kind == "ready": value["authority"]["backtesting_ready"] = True
    elif kind == "bool_count": value["document_frames_qualified"] = True
    elif kind == "object": value["authority"] = object()
    elif kind == "recursive": value["authority"] = value
    else: value["payload_bytes"] = float("nan")
    with pytest.raises(m.NCRouteError) as caught:
        m.validate_nc_route_witness(value, fixture_only=True)
    assert (caught.value.phase, caught.value.code) in m.SAFE_ERROR_CODES
    assert CONTACT not in str(caught.value)


def test_review_private_factory_and_payload_are_immutable_not_dataclass_shape_authority():
    assessment = _one(_nc());claim = assessment.claim
    object.__setattr__(claim, "accession_number", SECOND)
    with pytest.raises(m.NCRouteError, match="genuine_unchanged_claim_required"):
        assessment.public_witness()
