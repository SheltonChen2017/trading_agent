"""Invented complete six-form quarter and original PEM parents, never real data."""
from dataclasses import replace
from pathlib import Path
import sys

import pytest

pytest.importorskip("fcntl", reason="macOS/POSIX custody support")
LANE = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
sys.path.insert(0, str(LANE / "tests"))
from test_insider_buying_sec_2006q1_parent_projection_v1 import supplied, _inputs as _old_inputs
from test_insider_buying_sec_early_original_parent_v1 import _wrap
from research import insider_buying_sec_2006q1_original_admission_v1 as module


def _inputs(supplied, selected=1, *, issuer_first=False):
    result = []
    for item in _old_inputs(supplied, selected=selected):
        inner = item["raw_bytes"]
        if issuer_first:
            begin, issuer, end = (inner.index(mark) for mark in
                (b"REPORTING-OWNER:\n", b"ISSUER:\n", b"</SEC-HEADER>\n"))
            inner = inner[:begin] + inner[issuer:end] + b"\n" + inner[begin:issuer] + inner[end:]
        raw = _wrap(inner)
        result.append({**item, "raw_bytes": raw, "body_sha256": module._sha(raw), "body_size_bytes": len(raw),
            "terminal_disposition": "complete_raw_response_retained_header_quarantined", "header_identity_bound": False})
    return tuple(result)


def _assess(supplied, inputs=None, *, fixture_only=True):
    snapshot, census, _ = supplied
    return module.assess_original_admission(snapshot, census, _inputs(supplied) if inputs is None else inputs,
        expected_capture_report_sha256="f" * 64, fixture_only=fixture_only)


@pytest.mark.parametrize("issuer_first", [False, True])
def test_full_original_binding_is_additive_noncanonical_and_conserves_six_forms(supplied, issuer_first):
    result = _assess(supplied, _inputs(supplied, 2, issuer_first=issuer_first)); body = result.to_payload()
    counts = body["counts"]
    assert counts["source_filings"] == len(body["rows"]) == 6
    assert counts["context_filings"] == counts["quarantined_filings"] == 4
    assert counts["structurally_bound_noncanonical_filings"] == counts["structurally_bound_original_parents"] == 2
    assert counts["preserved_capture_header_quarantines"] == 2
    assert counts["target_original_binding_missing"] == 0
    assert body["rows"][2]["accession_year_mismatch"] is True
    assert body["whole_quarter_identity_sha256"] is None
    assert all(value is False or type(value) is int and value == 0 for value in body["authority"].values())
    for row in body["rows"]:
        assert row["frozen_baseline_disposition"] == "quarantined"
        assert row["frozen_baseline_quarantine_reasons"]
    for row in body["parent_ledger"]:
        assert row["terminal_disposition"] == "complete_raw_response_retained_header_quarantined"
        assert row["original_projection"]["capture_header_identity_bound"] is False
        assert row["original_projection"]["accepted_clock_verified"] is False
        assert row["original_projection"]["header_topology"] == ("issuer-first" if issuer_first else "owner-first")
    assert b"<ownershipDocument>" not in result.canonical_bytes()
    assert b"Invented one-quarter issuer" not in result.canonical_bytes()
    assert body["accounting_sha256"] == module.hash_payload(body["rows"])
    assert body["parent_ledger_sha256"] == module._sha(module._raw(body["parent_ledger"]))


@pytest.mark.parametrize("mutation", ["issuer", "owner", "dtd", "namespace", "malformed", "envelope", "bare"])
def test_bad_original_is_quarantined_without_dropping_parent_or_source_row(supplied, mutation):
    item = _inputs(supplied)[0]; raw = item["raw_bytes"]
    if mutation == "issuer":raw = raw.replace(b"<issuerCik>0000123456", b"<issuerCik>0000123457")
    elif mutation == "owner":raw = raw.replace(b"<rptOwnerCik>0000999999", b"<rptOwnerCik>0000003333")
    elif mutation == "dtd":raw = raw.replace(b"<ownershipDocument>", b"<!DOCTYPE ownershipDocument><ownershipDocument>")
    elif mutation == "namespace":raw = raw.replace(b"<ownershipDocument>", b"<ownershipDocument xmlns='invented'>")
    elif mutation == "malformed":raw = raw.replace(b"</ownershipDocument>", b"<not-closed>")
    elif mutation == "envelope":raw = raw.replace(b"Proc-Type: 2001", b"Proc-Type: 2002")
    else:raw = raw[raw.index(b"<SEC-DOCUMENT>"):raw.index(b"-----END PRIVACY-ENHANCED MESSAGE-----")]
    body = _assess(supplied, ({**item, "raw_bytes": raw, "body_sha256": module._sha(raw), "body_size_bytes": len(raw)},)).to_payload()
    assert body["counts"]["parser_quarantined_parents"] == 1
    assert body["counts"]["quarantined_filings"] == body["counts"]["source_filings"] == 6
    assert body["parent_ledger"][0]["original_projection_refusal"] == "early_original_parser_refused"
    assert body["parent_ledger"][0]["original_projection"] is None


@pytest.mark.parametrize("terminal", ["planned_unattempted", "http_refused_no_retry", "ambiguous_transport_failure_no_retry",
    "response_privacy_framing_or_custody_refused_no_retry"])
def test_all_selected_terminal_states_remain_explicit(supplied, terminal):
    item = _inputs(supplied)[0]
    missing = {**item, "raw_bytes": None, "body_sha256": None, "body_size_bytes": None,
        "header_identity_bound": False, "terminal_disposition": terminal,
        "result_sha256": None if terminal == "planned_unattempted" else "a" * 64}
    body = _assess(supplied, (missing,)).to_payload()
    assert body["counts"]["unavailable_selected_parents"] == body["counts"]["selected_parents"] == 1
    assert body["counts"]["target_original_binding_missing"] == 2
    assert body["counts"]["retained_parent_bytes"] == 0
    assert body["parent_ledger"][0]["terminal_disposition"] == terminal


@pytest.mark.parametrize("key,value", [("body_size_bytes", True), ("body_sha256", "a" * 64), ("prefix_ordinal", True),
    ("result_sha256", None), ("header_identity_bound", 1), ("terminal_disposition", "planned_unattempted"),
    ("header_identity_bound", True)])
def test_descriptor_forgeries_are_refused(supplied, key, value):
    with pytest.raises(module.OriginalAdmissionError):_assess(supplied, ({**_inputs(supplied)[0], key: value},))


@pytest.mark.parametrize("key", ["source_record_ordinal", "filing_metadata_sha256", "quarterly_zip_sha256", "submission_member_sha256"])
def test_request_is_bound_to_complete_original_quarter_row(supplied, key):
    item = _inputs(supplied)[0]; request = {**item["request"], key: 4 if key == "source_record_ordinal" else "a" * 64}
    with pytest.raises(module.OriginalAdmissionError):
        _assess(supplied, ({**item, "request": request, "request_sha256": module._sha(module._raw(request))},))


def test_full_actual_profile_cannot_be_asserted_from_invented_small_corpus(supplied):
    with pytest.raises(module.OriginalAdmissionError, match="actual_full_quarter_and64_profile_required"):
        _assess(supplied, fixture_only=False)


def test_factory_receipt_cannot_be_forged_mutated_or_replaced(supplied):
    result = _assess(supplied); body = result.to_payload(); body["authority"]["backtesting_ready"] = True
    assert result.to_payload()["authority"]["backtesting_ready"] is False
    for forged in (replace(result), module.OriginalAdmissionAssessment(result.canonical_bytes(), object())):
        with pytest.raises(module.OriginalAdmissionError):forged.to_payload()
    object.__setattr__(result, "_bytes", b"{}")
    with pytest.raises(module.OriginalAdmissionError):result.to_payload()


def test_fake_parser_projection_is_not_accepted(supplied, monkeypatch):
    monkeypatch.setattr(module.parser, "project_early_original_parent", lambda *_a, **_k: object())
    with pytest.raises(module.OriginalAdmissionError):_assess(supplied)


def test_bounds_order_duplicate_and_output_caps(supplied, monkeypatch):
    one, two = _inputs(supplied, 2)
    for descriptors in ((one,) * 65, (one, {**one, "prefix_ordinal": 1}), (two, one), [one]):
        with pytest.raises(module.OriginalAdmissionError):_assess(supplied, descriptors)
    monkeypatch.setattr(module.original.identity_v2, "MAX_CORROBORATING_BYTES", 1)
    with pytest.raises(module.OriginalAdmissionError, match="original_aggregate_byte_bound_refused"):_assess(supplied)


def test_zero_descriptors_conserves_all_six_source_forms(supplied):
    body = _assess(supplied, ()).to_payload()
    assert body["counts"]["source_filings"] == body["counts"]["quarantined_filings"] == 6
    assert body["counts"]["selected_parents"] == 0
    assert body["form_counts"] == {form: 1 for form in module.FORM_COUNTS}


def test_no_frozen_projection_factory_is_invoked(supplied, monkeypatch):
    monkeypatch.setattr(module.original, "project_sec_complete_submission", lambda *_a, **_k: pytest.fail("frozen factory forbidden"))
    assert _assess(supplied).to_payload()["counts"]["structurally_bound_original_parents"] == 1
