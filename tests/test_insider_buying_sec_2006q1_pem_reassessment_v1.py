"""Invented pure PEM integration fixtures; no actual roots or provider access."""
from __future__ import annotations

import base64
from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("fcntl", reason="existing POSIX caller metadata support")
LANE = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
sys.path.insert(0, str(LANE / "tests"))
from test_insider_buying_ib1c_v2_affected_quarter_runner import _fixture, _run
from test_insider_buying_sec_complete_submission import _complete, _legacy_header

from research import insider_buying_sec_2006q1_pem_reassessment_v1 as module


@pytest.fixture
def supplied(tmp_path, monkeypatch):
    source, output = _fixture(tmp_path, monkeypatch);receipt = _run(source, output)
    original = module.original
    _, _, census, _, _, _ = original.preparation._prepare_inputs(source)
    raw_dir = output / "ib1a" / receipt["raw_snapshot_id"]
    snapshot = original.load_sec_bulk_parsed_snapshot(output / "ib1b" / receipt["parsed_snapshot_id"], raw_snapshot_directory=raw_dir)
    base = module.v2.assess_ib1c_v2_quarter_identity(snapshot, census, ()).to_payload()
    return snapshot, census, original._source_filings(snapshot, base)


def _request(snapshot, filing):
    accession = filing["accession_number"];archive = "edgar/data/987654/" + accession + ".txt"
    return {"period": "2006Q1", "accession_number": accession, "form_type": filing["form_type"],
        "filing_date": filing["filing_date"], "issuer_cik": filing["issuer_cik"], "source_record_ordinal": filing["source_record_ordinal"],
        "archive_path": archive, "url": "https://www.sec.gov/Archives/" + archive,
        "accession_key_sha256": module._sha(accession.encode()), "filing_metadata_sha256": module._sha(module._raw(filing)),
        "submission_inventory_sha256": "c" * 64, "quarterly_zip_sha256": snapshot.identity.raw_archive_sha256,
        "submission_member_sha256": next(t.raw_member_sha256 for t in snapshot.identity.tables if t.table_name == "SUBMISSION.tsv"),
        "master_decoded_sha256": "d" * 64, "master_receipt_sha256": "e" * 64}


def _inner(request):
    raw = _complete(header=_legacy_header()).replace(b"0000999999-22-000001", request["accession_number"].encode()).replace(b"20221107", b"20060115")
    if request["form_type"] == "4/A":
        raw = (raw.replace(b"CONFORMED SUBMISSION TYPE:\t4\n", b"CONFORMED SUBMISSION TYPE:\t4/A\n")
            .replace(b"FORM TYPE:\t4\n", b"FORM TYPE:\t4/A\n")
            .replace(b"<TYPE>4\n", b"<TYPE>4/A\n")
            .replace(b"<documentType>4</documentType>", b"<documentType>4/A</documentType>"))
    return raw


def _wrap(inner):
    key = base64.b64encode(bytes(90));signature = base64.b64encode(bytes(64))
    return b"\n".join((*module.pem.STANDARD_HEADER_LINES, b" " + key[:64], b" " + key[64:],
        module.pem.MIC_INFO, b" " + signature[:64], b" " + signature[64:], b"")) + b"\n" + inner + module.pem.END + b"\n"


def _inputs(supplied, selected=1):
    snapshot, _, filings = supplied
    items = sorted((f for f in filings.values() if f["relevant_form4_or_amendment"]),
        key=lambda f: (f["filing_date"], f["accession_number"], f["source_record_ordinal"]))
    result = []
    for ordinal, filing in enumerate(items[:selected]):
        request = _request(snapshot, filing);raw = _wrap(_inner(request))
        result.append({"prefix_ordinal": ordinal, "request_sha256": module._sha(module._raw(request)), "request": request,
            "result_sha256": "a" * 64, "terminal_disposition": "complete_raw_response_retained_header_quarantined",
            "body_sha256": module._sha(raw), "body_size_bytes": len(raw), "raw_bytes": raw, "header_identity_bound": False})
    return tuple(result)


def _assess(supplied, descriptors=None):
    snapshot, census, _ = supplied
    return module.assess_2006q1_pem_source_view_identity(snapshot, census,
        _inputs(supplied) if descriptors is None else descriptors, expected_capture_report_sha256="f" * 64, fixture_only=True)


def _bridge(item):
    view = module.pem.build_early_pem_source_view(item["raw_bytes"], expected_original_body_sha256=item["body_sha256"])
    return module.project_genuine_pem_source_view(item["request"], view, capture_result_sha256=item["result_sha256"])


def _with_raw(item, raw):return {**item, "raw_bytes": raw, "body_sha256": module._sha(raw), "body_size_bytes": len(raw)}


def test_genuine_original_view_projection_bridge_has_distinct_identities_and_no_admission(supplied):
    item = _inputs(supplied)[0];bridge = _bridge(item);body = bridge.to_payload()
    assert body["original_raw_parent"]["sha256"] == item["body_sha256"]
    assert body["derived_sec_document_source_view"]["sha256"] != item["body_sha256"]
    assert body["frozen_source_view_projection"]["source_view_parent_sha256"] == body["derived_sec_document_source_view"]["sha256"]
    assert bridge.frozen_source_view_projection.raw_bytes == item["raw_bytes"][373:-39]
    assert body["original_capture_header_quarantine_preserved"] is True
    assert body["original_capture_header_identity_bound"] is False
    assert all(value is False or type(value) is int and value == 0 for value in body["authority"].values())


def test_full_six_form_assessment_uses_new_source_view_epoch_not_whole_original_parent_admission(supplied):
    payload = _assess(supplied).to_payload()
    assert len(payload["rows"]) == payload["counts"]["source_filings"] == 6
    assert payload["counts"]["context_filings"] == 4
    assert payload["counts"]["source_view_corroborated_noncanonical"] == 1
    assert payload["counts"]["quarantined_filings"] == 5
    row = payload["rows"][2]
    assert row["accession_year_mismatch"] is True
    assert row["disposition"] == "source_view_corroborated_noncanonical"
    assert row["corroboration_identity_kind"] == "derived_view_not_original_complete_parent"
    assert row["corroboration"]["parent_sha256"] != row["original_parent_custody"]["original_raw_parent"]["sha256"]
    assert payload["evidence_epoch"] == module.EVIDENCE_EPOCH
    assert payload["whole_original_parent_identity_sha256"] is None and payload["whole_quarter_identity_sha256"] is None
    assert payload["v2_contract_alone_admits_original_whole_bodies"] is False
    assert all(row["whole_original_parent_admitted"] is False for row in payload["rows"])
    assert payload["authority"] == module._authority()


def test_both_form4_targets_can_be_source_view_corroborated_without_context_promotion(supplied):
    payload = _assess(supplied, _inputs(supplied, 2)).to_payload()
    assert payload["counts"]["source_view_corroborated_noncanonical"] == 2
    assert payload["counts"]["quarantined_filings"] == 4
    assert [row["form_type"] for row in payload["rows"]] == ["3", "3/A", "4", "4/A", "5", "5/A"]
    assert all(row["disposition"] == "quarantined" for row in payload["rows"] if row["form_type"] not in {"4", "4/A"})


def test_issuer_first_grammar_refusal_stays_unchanged_without_role_reorder(supplied):
    item = _inputs(supplied)[0];view = _inner(item["request"])
    start = view.index(b"REPORTING-OWNER:\n");issuer = view.index(b"ISSUER:\n");end = view.index(b"</SEC-HEADER>\n")
    changed = view[:start] + view[issuer:end] + view[start:issuer] + view[end:]
    payload = _assess(supplied, (_with_raw(item, _wrap(changed)),)).to_payload()
    assert payload["counts"]["exact_pem_source_views"] == 1
    assert payload["counts"]["source_view_parser_quarantined"] == 1
    assert payload["counts"]["source_view_corroborated_noncanonical"] == 0
    assert payload["counts"]["quarantined_filings"] == 6
    assert payload["parent_qualification_ledger"][0]["source_view"]["roles_reordered"] is False


@pytest.mark.parametrize("kind", ["no_wrapper", "bad_marker", "double_marker", "bad_key", "crlf"])
def test_unknown_wrapper_is_explicit_quarantine_never_silently_admitted(supplied, kind):
    item = _inputs(supplied)[0];raw = item["raw_bytes"]
    if kind == "no_wrapper":raw = _inner(item["request"])
    elif kind == "bad_marker":raw = raw.replace(module.pem.END, b"-----OTHER END-----")
    elif kind == "double_marker":raw = raw.replace(b"<ownershipDocument>", b"<ownershipDocument>" + module.pem.BEGIN)
    elif kind == "bad_key":raw = raw.replace(b"Originator-Key-Asymmetric:", b"Other-Key:")
    else:raw = raw.replace(b"\n", b"\r\n")
    payload = _assess(supplied, (_with_raw(item, raw),)).to_payload()
    assert payload["counts"]["pem_profile_quarantined"] == 1
    assert payload["counts"]["source_view_corroborated_noncanonical"] == 0
    assert payload["counts"]["quarantined_filings"] == 6
    assert payload["parent_qualification_ledger"][0]["original_raw_parent"]["sha256"] == module._sha(raw)


@pytest.mark.parametrize("key,value", [("header_identity_bound", True), ("header_identity_bound", 0), ("body_size_bytes", True),
    ("prefix_ordinal", True), ("body_sha256", "b" * 64), ("result_sha256", None),
    ("terminal_disposition", "complete_raw_response_retained_header_bound")])
def test_original_capture_type_and_context_cannot_be_relabelled(supplied, key, value):
    item = {**_inputs(supplied)[0], key: value}
    with pytest.raises(module.PemSourceViewEvidenceError):_assess(supplied, (item,))


@pytest.mark.parametrize("key,value", [("issuer_cik", "0000123457"), ("form_type", "4/A"), ("filing_date", "2006-01-16"),
    ("source_record_ordinal", 4), ("filing_metadata_sha256", "a" * 64)])
def test_rehashed_request_cannot_change_original_filing_identity(supplied, key, value):
    item = _inputs(supplied)[0];request = {**item["request"], key: value}
    altered = {**item, "request": request, "request_sha256": module._sha(module._raw(request))}
    with pytest.raises(module.PemSourceViewEvidenceError, match="original_filing_descriptor_binding_refused"):
        _assess(supplied, (altered,))


def test_genuine_view_factory_type_and_version_are_binding(supplied, monkeypatch):
    item = _inputs(supplied)[0]
    with pytest.raises(module.PemSourceViewEvidenceError, match="genuine_pem_view"):
        module.project_genuine_pem_source_view(item["request"], {}, capture_result_sha256="a" * 64)
    view = module.pem.build_early_pem_source_view(item["raw_bytes"], expected_original_body_sha256=item["body_sha256"])
    for flag in (True, 0, 1, None):
        with pytest.raises(module.PemSourceViewEvidenceError):
            module.project_genuine_pem_source_view(item["request"], view, capture_result_sha256="a" * 64,
                original_capture_header_identity_bound=flag)
    old = module.pem.PROFILE
    monkeypatch.setattr(module.pem, "PROFILE", old + "-unqualified-version")
    with pytest.raises(module.pem.EarlyPemSourceViewError):
        module.project_genuine_pem_source_view(item["request"], view, capture_result_sha256="a" * 64)


def test_bridge_and_inventory_fully_reparse_and_reject_changed_frozen_bytes(supplied):
    bridge = _bridge(_inputs(supplied)[0]);inventory = module.build_pem_source_view_inventory((bridge,))
    assert inventory.frozen_projections_for_v2() == (bridge.frozen_source_view_projection,)
    projection = bridge.frozen_source_view_projection
    object.__setattr__(projection, "raw_bytes", projection.raw_bytes.replace(b"<issuerCik>0000123456", b"<issuerCik>0000123457"))
    with pytest.raises(module.SecCompleteSubmissionError):inventory.to_payload()


def test_bridge_inventory_and_assessment_reconstruction_cannot_grant_admission(supplied):
    bridge = _bridge(_inputs(supplied)[0]);inventory = module.build_pem_source_view_inventory((bridge,));assessment = _assess(supplied)
    for result in (bridge, inventory, assessment):
        payload = result.to_payload();payload["authority"]["whole_original_parent_admitted"] = True
        assert result.to_payload()["authority"]["whole_original_parent_admitted"] is False
        with pytest.raises(module.PemSourceViewEvidenceError):replace(result).to_payload()


def test_unattempted_parent_and_empty_input_retain_complete_quarter(supplied):
    item = _inputs(supplied)[0]
    unavailable = {**item, "raw_bytes": None, "body_sha256": None, "body_size_bytes": None, "result_sha256": None,
        "terminal_disposition": "planned_unattempted"}
    for inputs in ((), (unavailable,)):
        payload = _assess(supplied, inputs).to_payload()
        assert len(payload["rows"]) == payload["counts"]["quarantined_filings"] == 6
        assert payload["counts"]["original_body_admitted"] == 0
        assert payload["counts"]["source_view_corroborated_noncanonical"] == 0


def test_parent_count_duplicates_and_existing_v2_byte_cap_are_preserved(supplied, monkeypatch):
    item = _inputs(supplied)[0];bridge = _bridge(item)
    for value in ([bridge], (bridge, bridge), (bridge,) * 65):
        with pytest.raises(module.PemSourceViewEvidenceError):module.build_pem_source_view_inventory(value)
    with pytest.raises(module.PemSourceViewEvidenceError):_assess(supplied, (item,) * 65)
    monkeypatch.setattr(module.v2, "MAX_CORROBORATING_BYTES", 1)
    with pytest.raises(module.PemSourceViewEvidenceError, match="existing_v2_aggregate"):_assess(supplied)


def test_actual_population_flag_cannot_promote_small_fixture_or_wrong_quarter(supplied):
    snapshot, census, _ = supplied
    with pytest.raises(module.PemSourceViewEvidenceError, match="exact_actual_six_form_population"):
        module.assess_2006q1_pem_source_view_identity(snapshot, census, _inputs(supplied), expected_capture_report_sha256="a" * 64, fixture_only=False)
    wrong_year = replace(snapshot, identity=replace(snapshot.identity, year=2007))
    with pytest.raises(module.PemSourceViewEvidenceError, match="fixed_2006q1"):
        module.assess_2006q1_pem_source_view_identity(wrong_year, census, (), expected_capture_report_sha256="a" * 64, fixture_only=True)


def test_generic_inventory_cannot_change_source_prefix_order(supplied):
    parents = tuple(_bridge(item) for item in _inputs(supplied, 2))
    with pytest.raises(module.PemSourceViewEvidenceError, match="pem_inventory_source_order_refused"):
        module.build_pem_source_view_inventory(tuple(reversed(parents)))


@pytest.mark.parametrize("mutation", ["drop_rows", "bool_count", "wrong_count", "coherent_wrong_counts", "original_hash_in_view_slot"])
def test_final_v2_outputs_cannot_drop_population_or_conflate_original_and_view(supplied, monkeypatch, mutation):
    real = module.v2.assess_ib1c_v2_quarter_identity
    calls = 0
    def observed(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = real(*args, **kwargs)
        if calls != 2:return result
        body = result.to_payload()
        if mutation == "drop_rows":body["rows"] = body["rows"][:-1]
        elif mutation == "bool_count":body["corroborated_count"] = True
        elif mutation == "wrong_count":body["quarantined_count"] = 4
        elif mutation == "coherent_wrong_counts":
            body["corroborated_count"], body["quarantined_count"] = 2, 4
        else:body["rows"][2]["corroboration"]["parent_sha256"] = _inputs(supplied)[0]["body_sha256"]
        body["accounting_sha256"] = module.hash_payload(body["rows"])
        class InventedBadAssessorOutput:
            def to_payload(self):return body
        return InventedBadAssessorOutput()
    monkeypatch.setattr(module.v2, "assess_ib1c_v2_quarter_identity", observed)
    with pytest.raises(module.PemSourceViewEvidenceError):_assess(supplied)
    assert calls == 2


def test_full_output_cap_is_a_refusal_not_permission_to_drop_rows(supplied, monkeypatch):
    monkeypatch.setattr(module, "MAX_OUTPUT_BYTES", 1)
    with pytest.raises(module.PemSourceViewEvidenceError, match="full_source_view_assessment_output_bound_refused"):_assess(supplied)


def test_pure_coordinator_calls_no_filesystem_network_or_process_api(supplied, monkeypatch):
    import os, subprocess
    def forbidden(*args, **kwargs):pytest.fail("pure coordinator escaped supplied source objects")
    monkeypatch.setattr(os, "open", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(module.original.capture, "_selected_sec_transport", forbidden)
    assert _assess(supplied).to_payload()["counts"]["source_filings"] == 6
