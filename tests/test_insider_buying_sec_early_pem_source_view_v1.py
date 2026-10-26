"""Invented PEM bodies only, no actual capture/provider/credential interaction."""
from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path
import sys

import pytest

LANE = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
sys.path.insert(0, str(LANE / "tests"))
from test_insider_buying_sec_complete_submission import _complete, _legacy_header, _target

from research import insider_buying_sec_early_pem_source_view_v1 as module


def _parent(*, inner=None, key=bytes(90), signature=bytes(64)):
    encoded_key, encoded_signature = base64.b64encode(key), base64.b64encode(signature)
    prefix = b"\n".join((*module.STANDARD_HEADER_LINES,
        b" " + encoded_key[:64], b" " + encoded_key[64:], module.MIC_INFO,
        b" " + encoded_signature[:64], b" " + encoded_signature[64:], b"")) + b"\n"
    view = _complete(header=_legacy_header()) if inner is None else inner
    return prefix + view + module.END + b"\n", view


def _build(raw):return module.build_early_pem_source_view(raw, expected_original_body_sha256=module._sha(raw))


def test_exact_source_view_preserves_complete_original_and_no_positive_authority():
    raw, view = _parent();receipt = _build(raw);payload = receipt.to_payload()
    assert receipt.original_bytes == raw and receipt.source_view_bytes == view
    assert raw[module.PREFIX_BYTES:-module.SUFFIX_BYTES] == view
    assert len(raw) == len(view) + 412
    assert payload["original_raw_parent"]["sha256"] == module._sha(raw)
    assert payload["derived_sec_document_source_view"]["sha256"] == module._sha(view)
    assert module._sha(raw) != module._sha(view)
    assert payload["original_body_unchanged"] is True and payload["sgml_or_xml_normalized"] is False
    assert payload["roles_reordered"] is False and payload["source_clocks_normalized"] is False
    assert payload["full_xml_or_header_identity_assessed"] is False
    assert all(value is False for value in payload["authority"].values())
    assert "no_signature_authenticity_publication_PIT_or_rights_verification" in payload["support"]


def test_frozen_original_failure_is_not_relabelled_as_original_projection_success():
    raw, view = _parent()
    with pytest.raises(module.frozen.SecCompleteSubmissionError, match="SEC-DOCUMENT envelope"):
        module.frozen.project_sec_complete_submission(_target(), raw)
    receipt = _build(raw)
    result = module.frozen.project_sec_complete_submission(_target(), receipt.source_view_bytes)
    assert result.raw_bytes == view and result.to_payload()["raw_parent"]["sha256"] == module._sha(view)
    assert result.to_payload()["raw_parent"]["sha256"] != receipt.to_payload()["original_raw_parent"]["sha256"]


def test_extraction_does_not_fix_or_reorder_unsupported_issuer_first_header():
    view = _complete(header=_legacy_header())
    begin = view.index(b"REPORTING-OWNER:\n");issuer = view.index(b"ISSUER:\n");end = view.index(b"</SEC-HEADER>\n")
    altered = view[:begin] + view[issuer:end] + view[begin:issuer] + view[end:]
    raw, _ = _parent(inner=altered);receipt = _build(raw)
    assert receipt.source_view_bytes == altered
    with pytest.raises(module.frozen.SecCompleteSubmissionError):
        module.frozen.project_sec_complete_submission(_target(), receipt.source_view_bytes)


@pytest.mark.parametrize("mutation", ["proc", "originator", "key_tag", "mic", "leading", "trailing", "blank", "crlf", "nul", "missing_lf"])
def test_unknown_or_modified_outer_envelope_refuses_without_normalization(mutation):
    raw, _ = _parent()
    if mutation == "proc":raw = raw.replace(b"Proc-Type: 2001,MIC-CLEAR", b"Proc-Type: 2002,MIC-CLEAR")
    elif mutation == "originator":raw = raw.replace(b"Originator-Name: webmaster@www.sec.gov", b"Originator-Name: invented@unit.test")
    elif mutation == "key_tag":raw = raw.replace(b"Originator-Key-Asymmetric:", b"Originator-Key-Asymmetric: extra")
    elif mutation == "mic":raw = raw.replace(b"MIC-Info: RSA-MD5,RSA,", b"MIC-Info: OTHER,OTHER,")
    elif mutation == "leading":raw = b"\n" + raw
    elif mutation == "trailing":raw += b"extra\n"
    elif mutation == "blank":raw = raw.replace(b"\n\n<SEC-DOCUMENT>", b"\n\n\n<SEC-DOCUMENT>")
    elif mutation == "crlf":raw = raw.replace(b"\n", b"\r\n")
    elif mutation == "nul":raw = raw.replace(b"<ownershipDocument>", b"<ownershipDocument>\0")
    else:raw = raw[:-1]
    with pytest.raises(module.EarlyPemSourceViewError):_build(raw)


@pytest.mark.parametrize("marker", [module.BEGIN, module.END, b"<SEC-DOCUMENT>", b"</SEC-DOCUMENT>", b"<SEC-HEADER>", b"</SEC-HEADER>"])
def test_nested_or_duplicate_envelope_marker_is_not_silently_stripped(marker):
    raw, _ = _parent()
    raw = raw.replace(b"<ownershipDocument>", b"<ownershipDocument>" + marker)
    with pytest.raises(module.EarlyPemSourceViewError, match="duplicate_or_ambiguous"):_build(raw)


@pytest.mark.parametrize("kind", ["key", "signature"])
@pytest.mark.parametrize("mutation", ["bad_character", "double_indent", "wrong_length", "bad_padding"])
def test_strict_bounded_base64_shape_without_signature_verification(kind, mutation):
    raw, _ = _parent();lines = raw.splitlines(keepends=True);index = 4 if kind == "key" else 7
    if mutation == "bad_character":lines[index] = lines[index].replace(b"A", b"!", 1)
    elif mutation == "double_indent":lines[index] = b" " + lines[index]
    elif mutation == "wrong_length":lines[index] = lines[index][:-2] + b"\n"
    else:lines[index] = b" " + b"=" * (len(lines[index])-2) + b"\n"
    with pytest.raises(module.EarlyPemSourceViewError):_build(b"".join(lines))


def test_arbitrary_structurally_valid_key_and_signature_cannot_claim_authentication():
    raw, _ = _parent(key=b"x" * 90, signature=b"y" * 64)
    payload = _build(raw).to_payload()
    assert payload["outer_envelope"]["public_key_base64_structure_checked_only"] is True
    assert payload["outer_envelope"]["signature_base64_structure_checked_only"] is True
    assert payload["authority"]["signature_verified"] is False
    assert payload["authority"]["sec_origin_authenticated"] is False


@pytest.mark.parametrize("mutation", ["doc_accessor", "header_accessor", "doc_date", "header_date", "bare_view"])
def test_source_container_date_and_accession_shapes_are_not_synthesized(mutation):
    raw, view = _parent()
    if mutation == "doc_accessor":raw = raw.replace(b"<SEC-DOCUMENT>0000999999-22-000001", b"<SEC-DOCUMENT>0000999999-22-000002")
    elif mutation == "header_accessor":raw = raw.replace(b"<SEC-HEADER>0000999999-22-000001", b"<SEC-HEADER>0000999999-22-000002")
    elif mutation == "doc_date":raw = raw.replace(b".txt : 20221107", b".txt : 20221307")
    elif mutation == "header_date":raw = raw.replace(b".hdr.sgml : 20221107", b".hdr.sgml : 20221307")
    else:raw = view
    with pytest.raises(module.EarlyPemSourceViewError):_build(raw)


def test_external_original_hash_is_required_not_computed_as_its_own_authority():
    raw, _ = _parent()
    for supplied in (None, "a" * 64, True, "INVALID"):
        with pytest.raises(module.EarlyPemSourceViewError, match="external_original_body_hash_required"):
            module.build_early_pem_source_view(raw, expected_original_body_sha256=supplied)


def test_full_reparse_refuses_changed_original_view_or_metadata():
    raw, _ = _parent()
    for key in ("_original", "_view", "_payload"):
        receipt = _build(raw)
        value = getattr(receipt, key)
        object.__setattr__(receipt, key, value + b"different")
        with pytest.raises(module.EarlyPemSourceViewError):receipt.to_payload()


def test_reconstruction_subclass_and_returned_payload_mutation_cannot_grant_authority():
    raw, _ = _parent();receipt = _build(raw)
    payload = receipt.to_payload();payload["authority"]["signature_verified"] = True
    assert receipt.to_payload()["authority"]["signature_verified"] is False
    for changed in (replace(receipt), module.EarlyPemSourceView(raw,module._sha(raw),receipt.source_view_bytes,receipt._payload,object())):
        with pytest.raises(module.EarlyPemSourceViewError, match="genuine_unchanged"):
            changed.to_payload()


def test_existing_complete_body_byte_and_line_bounds_still_apply(monkeypatch):
    raw, _ = _parent()
    monkeypatch.setattr(module, "MAX_ORIGINAL_BODY_BYTES", len(raw)-1)
    with pytest.raises(module.EarlyPemSourceViewError, match="bounded_original_body"):_build(raw)
    monkeypatch.setattr(module, "MAX_ORIGINAL_BODY_BYTES", 8*1024*1024)
    monkeypatch.setattr(module, "MAX_ORIGINAL_LINES", 12)
    with pytest.raises(module.EarlyPemSourceViewError, match="line_count_profile"):_build(raw)
