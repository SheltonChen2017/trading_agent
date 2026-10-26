"""Invented original complete-submission bytes only; no source/account I/O."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from research import insider_buying_pilot_sec_parent_structure as m


@pytest.fixture(scope="module")
def supplied():
    spec = importlib.util.spec_from_file_location("invented_pilot_structure_fixture",
        Path(__file__).with_name("test_insider_buying_sec_complete_submission.py"))
    fixture = importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    return fixture


def _candidate(supplied, body=None, *, issuer="0000123456"):
    body = supplied._complete() if body is None else body
    target = supplied._target().to_payload()
    raw_target = {key:target[key] for key in ("accession_number","period","filing_date","form_type","issuer_cik")}
    raw_target["issuer_cik"] = issuer
    request = {**raw_target,"url":target["complete_submission_url"],"master_source_sha256":"a"*64,
        "archive_path":target["complete_submission_url"].removeprefix("https://www.sec.gov/Archives/")}
    return {"root_id":"invented-root","control_name":"request-000-result.json","control_sha256":"b"*64,
        "request_sha256":m._sha(m._raw(request)),"request":request,"request_url":request["url"],"retained_target":raw_target,
        "raw_object":{"relative_path":"objects/"+m._sha(body)+".bin","sha256":m._sha(body),"size_bytes":len(body)},
        "body_currently_hash_verified":True,"complete_parent_parsed_here":False}


def _evidence():
    return [{"root_id":"original-root","journal_sha256":"1"*64,"state":"ambiguous"},
        {"root_id":"separate-diagnostic","journal_sha256":"2"*64,"state":"completed"}]


def _process(supplied, body=None, candidate=None, **changes):
    body = supplied._complete() if body is None else body
    candidate = _candidate(supplied,body) if candidate is None else candidate
    arguments = dict(expected_candidate_sha256=m._sha(m._raw(candidate)),expected_body_sha256=m._sha(body),
        expected_master_decoded_sha256="a"*64,prior_exposure_evidence=_evidence())
    arguments.update(changes)
    return m.process_candidate(body,candidate,**arguments)


def test_full_original_and_children_bound_without_any_authority_or_ambiguity_resolution(supplied):
    body = supplied._complete();candidate = _candidate(supplied,body)
    result = _process(supplied,body,candidate);value = result.to_payload()
    projection = supplied._project(body)
    assert value["full_original_structurally_bound"] is True and value["quarantine_code"] is None
    assert value["raw_parent"] == {"sha256":m._sha(body),"size_bytes":len(body)}
    assert value["children"] == projection.to_payload()["children"]
    assert value["frozen_projection_sha256"] == projection.sha256
    assert value["request"] == candidate["request"] and value["retained_target"] == candidate["retained_target"]
    assert value["historical_ambiguous_start_preserved"] is True
    assert value["original_unmatched_start_resolved"] is value["consumed_accession_released_for_redispatch"] is False
    assert value["authority"] == m.audit._AUTHORITY
    assert value["named_file_custody_verified_here"] is value["canonical_or_ib1c_identity_admitted"] is False
    assert b"<ownershipDocument>" not in result.canonical_bytes() and b"<SEC-HEADER>" not in result.canonical_bytes()


def test_raw_short_cik_is_preserved_and_only_parser_comparison_target_is_padded(supplied):
    body = supplied._complete();candidate = _candidate(supplied,body,issuer="123456")
    value = _process(supplied,body,candidate).to_payload()
    assert value["retained_target"]["issuer_cik"] == value["request"]["issuer_cik"] == "123456"
    assert value["frozen_parser_comparison_target"]["issuer_cik"] == "0000123456"
    assert value["issuer_comparison_padding_applied"] is True and value["raw_request_target_rewritten"] is False
    assert value["source_body_modified"] is False


@pytest.mark.parametrize("text",[b"NOT-A-FINANCIAL-NUMBER",b"1e9999999999999999999",b"NaN",b"-Infinity"])
def test_transaction_financial_text_is_not_numerically_converted_or_projected(supplied,text):
    xml = supplied._xml().replace(b"</ownershipDocument>",
        b"<nonDerivativeTable><nonDerivativeTransaction><transactionAmounts><transactionShares><value>"+text+
        b"</value></transactionShares><transactionPricePerShare><value>"+text+
        b"</value></transactionPricePerShare></transactionAmounts></nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>")
    body = supplied._complete(xml=xml)
    value = _process(supplied,body).to_payload()
    assert value["full_original_structurally_bound"] is True
    assert value["financial_numeric_fields_converted"] is value["financial_values_projected"] is False
    assert text not in m._raw(value)


@pytest.mark.parametrize("change",[
    lambda body:body.replace(b"</SEC-DOCUMENT>\n",b""),
    lambda body:body.replace(b"<SEC-DOCUMENT>0000999999-22-000001",b"<SEC-DOCUMENT>0000999999-22-000002"),
    lambda body:body.replace(b"<TYPE>4\n<FILING-DATE>",b"<TYPE>4/A\n<FILING-DATE>"),
    lambda body:body.replace(b"<FILING-DATE>20221107",b"<FILING-DATE>20221108"),
    lambda body:body.replace(b"<CIK>0000123456",b"<CIK>0000123457"),
    lambda body:body.replace(b"<issuerCik>0000123456",b"<issuerCik>0000123457"),
    lambda body:body.replace(b"<rptOwnerCik>0000999999",b"<rptOwnerCik>0000999998"),
    lambda body:body.replace(b"<documentType>4</documentType>",b"<documentType>4/A</documentType>"),
    lambda body:body.replace(b"<ownershipDocument>",b"<!DOCTYPE ownershipDocument><ownershipDocument>"),
    lambda body:body+b"PRIVATE-TRAILING-MATERIAL",
    lambda body:body.replace(b"<SEQUENCE>1",b"<SEQUENCE>0"),
    lambda body:body.replace(b"<FILENAME>ownership.xml",b"<FILENAME>../ownership.xml"),
])
def test_genuine_structure_or_identity_refusal_is_fixed_quarantine_not_integrity_success(supplied,change):
    body = change(supplied._complete());value = _process(supplied,body).to_payload()
    assert value["full_original_structurally_bound"] is False
    assert value["quarantine_code"] == m.QUARANTINE_CODE
    assert value["children"] is value["source_declared_fields"] is value["frozen_projection_sha256"] is None
    assert value["raw_parent"]["sha256"] == m._sha(body)
    assert value["historical_ambiguous_start_preserved"] is True and value["authority"] == m.audit._AUTHORITY
    assert b"PRIVATE-TRAILING-MATERIAL" not in m._raw(value)


@pytest.mark.parametrize("fault",["body_hash","candidate_hash","body_size","body_descriptor_hash","master_hash",
    "unverified_body","request_hash","request_target","request_unknown","empty_evidence","no_evidence","bad_state",
    "float_authority","nonbytes_body","oversize_body"])
def test_integrity_lineage_refusals_cannot_be_reclassified_as_grammar_quarantines(supplied,fault):
    body = supplied._complete();candidate = _candidate(supplied,body);changes = {}
    if fault == "body_hash":changes["expected_body_sha256"] = "0"*64
    if fault == "candidate_hash":changes["expected_candidate_sha256"] = "0"*64
    if fault == "body_size":candidate["raw_object"]["size_bytes"] += 1
    if fault == "body_descriptor_hash":candidate["raw_object"]["sha256"] = "0"*64
    if fault == "master_hash":changes["expected_master_decoded_sha256"] = "0"*64
    if fault == "unverified_body":candidate["body_currently_hash_verified"] = False
    if fault == "request_hash":candidate["request_sha256"] = "0"*64
    if fault == "request_target":candidate["request"]["issuer_cik"] = "999";candidate["request_sha256"] = m._sha(m._raw(candidate["request"]))
    if fault == "request_unknown":candidate["request"]["private_field"] = "PRIVATE";candidate["request_sha256"] = m._sha(m._raw(candidate["request"]))
    if fault == "empty_evidence":changes["prior_exposure_evidence"] = []
    if fault == "no_evidence":changes["prior_exposure_evidence"] = None
    if fault == "bad_state":changes["prior_exposure_evidence"] = [{"root_id":"invented","journal_sha256":"1"*64,"state":"planned"}]
    if fault == "float_authority":candidate["body_currently_hash_verified"] = 1.0
    if fault == "nonbytes_body":body = bytearray(body)
    if fault == "oversize_body":body = b"x"*(m.MAX_BODY_BYTES+1);candidate = _candidate(supplied,body)
    with pytest.raises(m.PilotSecParentStructureError):_process(supplied,body,candidate,**changes)


def test_parser_cannot_return_fake_projection_or_different_original(supplied,monkeypatch):
    genuine_payload = supplied._project().to_payload()
    monkeypatch.setattr(m.frozen,"project_sec_complete_submission",lambda *_:SimpleNamespace(
        raw_bytes=supplied._complete(),to_payload=lambda:deepcopy(genuine_payload)))
    with pytest.raises(m.PilotSecParentStructureError,match="exact_original_projection"):_process(supplied)


def test_frozen_payload_children_must_bind_full_original_not_another_parent(supplied,monkeypatch):
    original = m.frozen.SecCompleteSubmissionProjection.to_payload
    def changed(self):
        payload = original(self);payload["children"]["header"]["parent_sha256"] = "0"*64
        return payload
    monkeypatch.setattr(m.frozen.SecCompleteSubmissionProjection,"to_payload",changed)
    with pytest.raises(m.PilotSecParentStructureError,match="projection_original_parent_binding"):_process(supplied)


def test_invented_parser_refusal_text_is_never_in_result(supplied,monkeypatch):
    def refuse(*_):raise m.frozen.SecCompleteSubmissionError("PRIVATE-SOURCE-TEXT-AND-CONTACT")
    monkeypatch.setattr(m.frozen,"project_sec_complete_submission",refuse)
    result = _process(supplied)
    assert result.to_payload()["quarantine_code"] == m.QUARANTINE_CODE
    assert b"PRIVATE" not in result.canonical_bytes()


def test_input_and_returned_metadata_copies_and_factory_registry_are_binding(supplied):
    candidate = _candidate(supplied);evidence = _evidence()
    result = _process(supplied,candidate=candidate,prior_exposure_evidence=evidence)
    before = result.canonical_bytes();candidate["request"]["issuer_cik"] = "99";evidence.clear()
    copied = result.to_payload();copied["authority"]["backtest_authorized"] = True
    assert result.canonical_bytes() == before
    with pytest.raises(m.PilotSecParentStructureError):m.validate_pilot_sec_parent_structure(replace(result))
    with pytest.raises(m.PilotSecParentStructureError):m.validate_pilot_sec_parent_structure(SimpleNamespace(to_payload=result.to_payload))


def test_bound_exceptions_cannot_escape_with_private_internal_text(supplied,monkeypatch):
    def refuse(*_):raise ValueError("PRIVATE-INTERNAL-PARSER-TEXT")
    monkeypatch.setattr(m.frozen,"project_sec_complete_submission",refuse)
    with pytest.raises(m.PilotSecParentStructureError,match="^unexpected_structural_parser_refusal$"):_process(supplied)
