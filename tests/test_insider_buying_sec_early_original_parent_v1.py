"""Invented full PEM parents only; no retained corpus, transport or credentials."""
from __future__ import annotations

import base64
from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

LANE = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
sys.path.insert(0, str(LANE / "tests"))
from test_insider_buying_sec_complete_submission import (
    _complete, _legacy_header, _legacy_owner, _former_owner_name, _document, _xml,
)
from research import insider_buying_sec_early_original_parent_v1 as module


def _request(*, form="4"):
    accession = "0000999999-06-000001"
    archive = "edgar/data/888888/" + accession + ".txt"
    return {
        "period": "2006Q1", "accession_number": accession, "form_type": form,
        "filing_date": "2006-01-15", "issuer_cik": "0000123456", "archive_path": archive,
        "url": "https://www.sec.gov/Archives/" + archive, "source_record_ordinal": 17,
        "accession_key_sha256": module._sha(accession.encode()),
        **{key: "a" * 64 for key in (
            "filing_metadata_sha256", "submission_inventory_sha256", "quarterly_zip_sha256",
            "submission_member_sha256", "master_decoded_sha256", "master_receipt_sha256")},
    }


def _inner(*, issuer_first=False, owners=("0000999999",), form="4", header=None, document=None):
    body = _complete(header=_legacy_header(owners) if header is None else header,
                     owners=owners, document=document)
    body = body.replace(b"0000999999-22-000001", b"0000999999-06-000001").replace(b"20221107", b"20060115")
    if form == "4/A":
        body = (body.replace(b"CONFORMED SUBMISSION TYPE:\t4\n", b"CONFORMED SUBMISSION TYPE:\t4/A\n")
            .replace(b"FORM TYPE:\t4\n", b"FORM TYPE:\t4/A\n")
            .replace(b"<TYPE>4\n", b"<TYPE>4/A\n")
            .replace(b"<documentType>4</documentType>", b"<documentType>4/A</documentType>"))
    if issuer_first:
        begin = body.index(b"REPORTING-OWNER:\n")
        issuer = body.index(b"ISSUER:\n")
        end = body.index(b"</SEC-HEADER>\n")
        body = body[:begin] + body[issuer:end] + b"\n" + body[begin:issuer] + body[end:]
    return body


def _wrap(inner):
    key = base64.b64encode(bytes(90))
    signature = base64.b64encode(bytes(64))
    return b"\n".join((*module.pem.STANDARD_HEADER_LINES, b" " + key[:64], b" " + key[64:],
        module.pem.MIC_INFO, b" " + signature[:64], b" " + signature[64:], b"")) + b"\n" + inner + module.pem.END + b"\n"


def _project(raw=None, request=None):
    raw = _wrap(_inner()) if raw is None else raw
    return module.project_early_original_parent(_request() if request is None else request, raw,
        expected_original_body_sha256=module._sha(raw), capture_result_sha256="c" * 64)


@pytest.mark.parametrize("issuer_first", (False, True))
@pytest.mark.parametrize("form", ("4", "4/A"))
@pytest.mark.parametrize("owners", (("0000999999",), ("0000999999", "0000888888")))
def test_full_original_parent_directly_coordinates_both_role_orders_without_promotion(issuer_first, form, owners):
    inner = _inner(issuer_first=issuer_first, owners=owners, form=form)
    raw = _wrap(inner)
    result = _project(raw, _request(form=form))
    payload = module.validate_early_original_parent(result)
    assert type(result) is module.EarlyOriginalParentProjection
    assert type(result) is not module.frozen.SecCompleteSubmissionProjection
    assert result.raw_bytes == raw and result.target.to_payload() == payload["target"]
    assert payload["original_raw_parent"] == {"sha256": module._sha(raw), "size_bytes": len(raw)}
    assert payload["embedded_sec_document"]["sha256"] == module._sha(inner) != module._sha(raw)
    assert payload["header_topology"] == ("issuer-first" if issuer_first else "owner-first")
    assert payload["source_fields"] == {"accepted_at_raw": "20060115101112", "header_owner_ciks": list(owners)}
    header = inner[inner.index(b"<SEC-HEADER>"):inner.index(b"</SEC-HEADER>\n") + len(b"</SEC-HEADER>\n")]
    xml = _xml(owners)
    if form == "4/A":
        xml = xml.replace(b"<documentType>4</documentType>", b"<documentType>4/A</documentType>")
    assert payload["children"]["header"]["sha256"] == module._sha(header)
    assert payload["children"]["primary_xml"]["sha256"] == module._sha(xml)
    assert all(child["parent_sha256"] == module._sha(raw) for child in payload["children"].values())
    assert payload["capture_result_sha256"] == "c" * 64 and payload["full_original_structurally_bound"] is True
    assert all(value is False or type(value) is int and value == 0 for value in payload["authority"].values())
    assert payload["roles_reordered"] is payload["sgml_or_xml_normalized"] is payload["source_clocks_normalized"] is False
    assert result.sha256 == module._sha(module._raw(payload))
    # The unchanged frozen contract still refuses the original PEM body.
    with pytest.raises(module.frozen.SecCompleteSubmissionError):
        module.frozen.project_sec_complete_submission(result.target, raw)
    if issuer_first:
        with pytest.raises(module.frozen.SecCompleteSubmissionError):
            module.frozen.project_sec_complete_submission(result.target, inner)


@pytest.mark.parametrize("issuer_first", (False, True))
def test_existing_former_name_and_short_explicit_separator_rules_preserve_bytes(issuer_first):
    header = _legacy_header().replace(
        _legacy_owner("0000999999"),
        _legacy_owner("0000999999") + _former_owner_name(changed="20050102"))
    raw = _wrap(_inner(header=header, issuer_first=issuer_first))
    assert _project(raw).raw_bytes == raw


@pytest.mark.parametrize("field,value", [
    ("period", "2006Q2"), ("filing_date", "2006-01-32"), ("form_type", "3"),
    ("issuer_cik", "0000000000"), ("accession_key_sha256", "b" * 64),
    ("source_record_ordinal", True), ("source_record_ordinal", 0),
    ("source_record_ordinal", 250001), ("master_decoded_sha256", "INVALID"),
    ("url", "https://invented.invalid/private"), ("archive_path", "edgar/data/0/0000999999-06-000001.txt"),
])
def test_invalid_request_refuses_with_fixed_codes(field, value):
    with pytest.raises(module.EarlyOriginalParentError) as caught:
        _project(request={**_request(), field: value})
    assert re_safe_code(str(caught.value))
    assert "invented.invalid" not in str(caught.value)


def re_safe_code(value):
    return value and all(char in "abcdefghijklmnopqrstuvwxyz0123456789_" for char in value)


@pytest.mark.parametrize("mutation", ("extra", "missing", "subclass", "nested"))
def test_request_schema_types_and_returned_copy_are_strict(mutation):
    request = _request()
    if mutation == "extra":request["foreign"] = "private"
    elif mutation == "missing":request.pop("master_receipt_sha256")
    elif mutation == "subclass":request = type("Request", (dict,), {})(request)
    else:request["issuer_cik"] = {"private": "value"}
    with pytest.raises(module.EarlyOriginalParentError):_project(request=request)


def test_original_hash_and_capture_receipt_digest_are_external_requirements():
    raw = _wrap(_inner())
    for kwargs in (
        {"expected_original_body_sha256": "b" * 64, "capture_result_sha256": "c" * 64},
        {"expected_original_body_sha256": True, "capture_result_sha256": "c" * 64},
        {"expected_original_body_sha256": module._sha(raw), "capture_result_sha256": "private-value"},
    ):
        with pytest.raises(module.EarlyOriginalParentError):
            module.project_early_original_parent(_request(), raw, **kwargs)
    with pytest.raises(module.EarlyOriginalParentError):
        module.project_early_original_parent(_request(), bytearray(raw),
            expected_original_body_sha256=module._sha(raw), capture_result_sha256="c" * 64)


@pytest.mark.parametrize("old,new,code", [
    (b"Proc-Type: 2001,MIC-CLEAR", b"Proc-Type: 2002,MIC-CLEAR", "original_pem_envelope_refused"),
    (b"Originator-Name: webmaster@www.sec.gov", b"Originator-Name: PRIVATE", "original_pem_envelope_refused"),
    (b"<SEC-DOCUMENT>0000999999-06-000001", b"<SEC-DOCUMENT>0000999999-06-000002", "original_pem_envelope_refused"),
    (b"ACCESSION NUMBER:\t0000999999-06-000001", b"ACCESSION NUMBER:\t0000999999-06-000002", "original_header_target_refused"),
    (b"CONFORMED SUBMISSION TYPE:\t4\n", b"CONFORMED SUBMISSION TYPE:\t4/A\n", "original_header_target_refused"),
    (b"FILED AS OF DATE:\t20060115", b"FILED AS OF DATE:\t20060116", "original_header_target_refused"),
    (b"<ACCEPTANCE-DATETIME>20060115101112", b"<ACCEPTANCE-DATETIME>20060115101199", "original_acceptance_clock_refused"),
    (b"PUBLIC DOCUMENT COUNT:\t1", b"PUBLIC DOCUMENT COUNT:\t2", "original_document_inventory_refused"),
    (b"CONFORMED PERIOD OF REPORT:\t20060115", b"CONFORMED PERIOD OF REPORT:\t20060230", "legacy_preamble_date_refused"),
    (b"\t\tCENTRAL INDEX KEY:\t0000123456", b"\t\tCENTRAL INDEX KEY:\t0000777777", "original_header_issuer_or_owner_identity_refused"),
    (b"\t\tFORM TYPE:\t4\n", b"\t\tFORM TYPE:\t4/A\n", "legacy_role_subsections_refused"),
    (b"<rptOwnerCik>0000999999</rptOwnerCik>", b"<rptOwnerCik>0000888888</rptOwnerCik>", "original_header_xml_owner_conflict"),
    (b"<issuerCik>0000123456</issuerCik>", b"<issuerCik>0000777777</issuerCik>", "original_xml_identity_or_security_refused"),
    (b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>", b"<!DOCTYPE ownershipDocument>", "original_xml_identity_or_security_refused"),
    (b"<FILENAME>ownership.xml", b"<FILENAME>../ownership.xml", "original_document_inventory_refused"),
    (b"<TYPE>4\n", b"<TYPE>4/A\n", "original_xml_type_or_bound_refused"),
])
@pytest.mark.parametrize("issuer_first", (False, True))
def test_identity_and_document_guards_have_specific_safe_refusals(old, new, code, issuer_first):
    raw = _wrap(_inner(issuer_first=issuer_first)).replace(old, new)
    with pytest.raises(module.EarlyOriginalParentError, match="^" + code + "$"):_project(raw)


@pytest.mark.parametrize("mutation", ("duplicate_issuer", "interleaved", "no_owner", "material_before",
    "blank_inside_leaf", "blank_run", "foreign_scope", "duplicate_cik", "misplaced_cik", "duplicate_owner"))
def test_legacy_topology_and_scope_refusals_do_not_reorder_or_guess(mutation):
    header = _legacy_header()
    if mutation == "duplicate_issuer":header = header.replace(b"ISSUER:\n", b"ISSUER:\nISSUER:\n")
    elif mutation == "interleaved":header = header.replace(b"</SEC-HEADER>\n", _legacy_owner("0000888888") + b"</SEC-HEADER>\n")
    elif mutation == "no_owner":header = header.replace(_legacy_owner("0000999999"), b"")
    elif mutation == "material_before":header = header.replace(b"DATE AS OF CHANGE:\t20221107\n", b"DATE AS OF CHANGE:\t20221107\nPRIVATE\n")
    elif mutation == "blank_inside_leaf":header = header.replace(b"NAME:\tInvented Owner\n", b"NAME:\tInvented Owner\n\n")
    elif mutation == "blank_run":header = header.replace(b"REPORTING-OWNER:\n\n", b"REPORTING-OWNER:\n\n\n\n")
    elif mutation == "foreign_scope":header = header.replace(b"\tOWNER DATA:", b"\tFOREIGN DATA:")
    elif mutation == "duplicate_cik":header = header.replace(b"CENTRAL INDEX KEY:\t0000999999\n", b"CENTRAL INDEX KEY:\t0000999999\n\t\tCENTRAL INDEX KEY:\t0000999999\n")
    elif mutation == "misplaced_cik":header = header.replace(b"STREET 1:\tInvented Street", b"CENTRAL INDEX KEY:\t0000999999")
    else:header = header.replace(_legacy_owner("0000999999"), _legacy_owner("0000999999") * 2)
    with pytest.raises(module.EarlyOriginalParentError):_project(_wrap(_inner(header=header)))


@pytest.mark.parametrize("mutation", ("second_xml", "duplicate_sequence", "missing_type", "trailing_text"))
def test_frozen_document_inventory_guards_are_reused_without_frozen_projection_imitation(mutation):
    document = _document(_xml())
    if mutation == "second_xml":
        document += _document(_xml(), filename=b"other.xml").replace(b"<SEQUENCE>1", b"<SEQUENCE>2")
    elif mutation == "duplicate_sequence":
        document += b"<DOCUMENT>\n<TYPE>EX-99\n<SEQUENCE>1\n<FILENAME>note.txt\n<TEXT>\nInvented\n</TEXT>\n</DOCUMENT>\n"
    elif mutation == "missing_type":document = document.replace(b"<TYPE>4\n", b"")
    else:document = document.replace(b"</TEXT>\n</DOCUMENT>", b"</TEXT>\nPRIVATE\n</DOCUMENT>")
    with pytest.raises(module.EarlyOriginalParentError):_project(_wrap(_inner(document=document)))


@pytest.mark.parametrize("attribute", ("_original", "_expected_original_sha256", "_context", "_payload_bytes", "_token"))
def test_typed_projection_reparses_all_bytes_and_factory_metadata(attribute):
    result = _project()
    value = getattr(result, attribute)
    replacement = object() if attribute == "_token" else value + (b"changed" if isinstance(value, bytes) else "x")
    object.__setattr__(result, attribute, replacement)
    with pytest.raises(module.EarlyOriginalParentError):result.to_payload()
    with pytest.raises(module.EarlyOriginalParentError):_ = result.raw_bytes
    with pytest.raises(module.EarlyOriginalParentError):_ = result.sha256


def test_caller_and_payload_mutation_cannot_alter_sealed_identity_or_authority():
    request = _request()
    result = _project(request=request)
    request["issuer_cik"] = "0000777777"
    body = result.to_payload()
    body["source_fields"]["header_owner_ciks"].append("0000777777")
    body["authority"]["signature_verified"] = True
    body["request"]["filing_date"] = "2006-03-01"
    assert result.to_payload()["authority"]["signature_verified"] is False
    assert result.target.issuer_cik == "0000123456"
    assert result.to_payload()["source_fields"]["header_owner_ciks"] == ["0000999999"]


def test_reconstruction_subclass_and_fake_payload_contract_are_refused_before_method_call():
    result = _project()
    with pytest.raises(module.EarlyOriginalParentError):replace(result).to_payload()
    fake = type("Fake", (), {"to_payload": lambda self: pytest.fail("untrusted method called")})()
    with pytest.raises(module.EarlyOriginalParentError):module.validate_early_original_parent(fake)
    subclass = type("Subclass", (module.EarlyOriginalParentProjection,), {})
    forged = subclass(result._original, result._expected_original_sha256, result._context, result._payload_bytes, result._token)
    object.__setattr__(forged, "_factory_bytes", forged._payload_bytes)
    with pytest.raises(module.EarlyOriginalParentError):module.validate_early_original_parent(forged)


def test_coherent_derived_metadata_change_is_refused_not_just_malformed_json():
    result = _project()
    body = result.to_payload()
    body["header_topology"] = "issuer-first"
    altered = module._raw(body)
    object.__setattr__(result, "_payload_bytes", altered)
    object.__setattr__(result, "_factory_bytes", altered)
    with pytest.raises(module.EarlyOriginalParentError, match="original_projection_metadata_changed"):result.to_payload()


def test_coherent_context_byte_change_is_refused_even_when_semantics_are_identical():
    result = _project()
    altered = json.dumps(json.loads(result._context), indent=1).encode()
    assert altered != result._context
    object.__setattr__(result, "_context", altered)
    with pytest.raises(module.EarlyOriginalParentError, match="original_projection_context_changed"):result.to_payload()


def test_current_frozen_parser_functions_are_never_patched_or_instantiated(monkeypatch):
    def forbidden(*args, **kwargs):pytest.fail("frozen projection or header coordinator used")
    monkeypatch.setattr(module.frozen, "project_sec_complete_submission", forbidden)
    monkeypatch.setattr(module.frozen, "_header_identity", forbidden)
    monkeypatch.setattr(module.frozen, "_extract", forbidden)
    assert _project(_wrap(_inner(issuer_first=True))).to_payload()["header_topology"] == "issuer-first"


def test_original_body_byte_and_line_limits_are_enforced_before_materialization(monkeypatch):
    raw = _wrap(_inner())
    monkeypatch.setattr(module, "MAX_ORIGINAL_BODY_BYTES", len(raw) - 1)
    with pytest.raises(module.EarlyOriginalParentError, match="external_original_body_hash_required"):_project(raw)
    monkeypatch.setattr(module, "MAX_ORIGINAL_BODY_BYTES", 8 * 1024 * 1024)
    monkeypatch.setattr(module.pem, "MAX_ORIGINAL_LINES", 16)
    with pytest.raises(module.EarlyOriginalParentError, match="original_pem_envelope_refused"):_project(raw)


# Claude review section 218: three grammar guards that in-memory mutants
# survived. Each test fails if its guard is removed.

def test_duplicate_document_sequence_is_refused_while_distinct_sequences_pass():
    two = _document(_xml(), filename=b"ownership.xml") + _document(
        b"<html>invented</html>\n", filename=b"cover.htm", form=b"EX-99")
    header = _legacy_header().replace(b"PUBLIC DOCUMENT COUNT:\t1", b"PUBLIC DOCUMENT COUNT:\t2")
    distinct = two.replace(b"<SEQUENCE>1\n<FILENAME>cover.htm", b"<SEQUENCE>2\n<FILENAME>cover.htm")
    assert _project(_wrap(_inner(header=header, document=distinct))).raw_bytes
    with pytest.raises(module.EarlyOriginalParentError, match="^original_duplicate_document_sequence_refused$"):
        _project(_wrap(_inner(header=header, document=two)))


def test_unknown_header_line_directly_before_the_first_role_is_not_skipped():
    # The existing material_before case puts a blank line after the extra
    # line, so the separator guard refuses it first.
    header = _legacy_header().replace(b"DATE AS OF CHANGE:\t20221107\n\n",
                                      b"DATE AS OF CHANGE:\t20221107\nPRIVATE\n")
    with pytest.raises(module.EarlyOriginalParentError, match="^legacy_role_topology_refused$"):
        _project(_wrap(_inner(header=header)))


def test_rendered_xsl_named_xml_document_is_not_taken_as_the_ownership_xml():
    raw = _wrap(_inner()).replace(b"<FILENAME>ownership.xml", b"<FILENAME>xslownership.xml")
    with pytest.raises(module.EarlyOriginalParentError, match="^original_xml_filename_refused$"):
        _project(raw)
