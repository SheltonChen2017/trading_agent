"""Invented byte images only: no SEC access, real artifact, or IB-1C ingest."""
from __future__ import annotations

import json
import builtins
from dataclasses import replace
from pathlib import Path

import pytest

from data.hashing import hash_bytes, hash_payload
from research.insider_buying.sec_acquisition_preparation import SecAcquisitionTarget
from research.insider_buying.sec_raw_parent_projection import (
    SEC_RAW_PARENT_PROJECTION_VERSION,
    SecRawParentProjectionError,
    derive_sec_raw_parent_projection,
)


def _target() -> SecAcquisitionTarget:
    return SecAcquisitionTarget(
        period="2022Q4", accession_number="0000999999-22-000001",
        form_type="4", filing_date="2022-11-07", issuer_cik="0000123456",
        quarterly_zip_sha256="a" * 64, submission_row_id="b" * 64,
        primary_xml_filename="ownership.xml",
    )


def _index(filename: str = "ownership.xml") -> bytes:
    return json.dumps({"directory": {"item": [{"name": filename}]}},
                      separators=(",", ":")).encode("ascii")


def _owner(cik: str) -> str:
    return ("<REPORTING-OWNER>\n<OWNER-DATA>\n"
            f"<CIK>{cik}\n<CONFORMED-NAME>Invented Owner\n"
            "</OWNER-DATA>\n</REPORTING-OWNER>\n")


def _header(owners: tuple[str, ...] = ("0000999999",)) -> bytes:
    return (
        "<SEC-HEADER>0000999999-22-000001.hdr.sgml : 20221107\n"
        "<ACCEPTANCE-DATETIME>20221107101112\n"
        "<ACCESSION-NUMBER>0000999999-22-000001\n"
        "<TYPE>4\n<FILING-DATE>20221107\n"
        + "".join(_owner(owner) for owner in owners)
        + "<ISSUER>\n<COMPANY-DATA>\n<CIK>0000123456\n"
          "</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
    ).encode("ascii")


def _xml(owners: tuple[str, ...] = ("0000999999",)) -> bytes:
    return (
        "<ownershipDocument><documentType>4</documentType>"
        "<issuer><issuerCik>0000123456</issuerCik></issuer>"
        + "".join("<reportingOwner><reportingOwnerId>"
                  f"<rptOwnerCik>{owner}</rptOwnerCik>"
                  "</reportingOwnerId></reportingOwner>" for owner in owners)
        + "</ownershipDocument>"
    ).encode("ascii")


def _derive(*, owners: tuple[str, ...] = ("0000999999",),
            index: bytes | None = None, header: bytes | None = None,
            xml: bytes | None = None):
    return derive_sec_raw_parent_projection(
        _target(), _index() if index is None else index,
        _header(owners) if header is None else header,
        _xml(owners) if xml is None else xml,
    )


@pytest.mark.parametrize("owners", [
    ("0000999999",),
    ("0000999999", "0000888888"),
    tuple(f"{index:010d}" for index in range(1, 11)),
])
def test_three_exact_raw_parents_bind_all_owner_identities_without_authority(owners):
    projection = _derive(owners=owners)
    payload = projection.to_payload()
    assert payload["version"] == SEC_RAW_PARENT_PROJECTION_VERSION
    assert set(payload["raw_parents"]) == {"index", "header", "xml"}
    assert payload["raw_parents"]["header"]["sha256"] == hash_bytes(_header(owners))
    assert payload["raw_parents"]["xml"]["sha256"] == hash_bytes(_xml(owners))
    assert payload["raw_parents"]["index"]["declared_source_url"] == (
        _target().archive_root + "index.json"
    )
    assert payload["raw_parents"]["header"]["declared_source_url"] == _target().header_url
    assert payload["raw_parents"]["xml"]["declared_source_url"] == _target().primary_xml_url
    assert payload["raw_parent_identity_sha256"] == hash_payload({
        "version": SEC_RAW_PARENT_PROJECTION_VERSION,
        "target": payload["target"],
        "raw_parents": payload["raw_parents"],
        "source_fields": payload["source_fields"],
    })
    assert payload["derived_projection"]["sha256"] == hash_bytes(projection.derived_json_bytes)
    assert payload["derived_projection"]["flat_payload"] == json.loads(
        projection.derived_json_bytes
    )
    assert payload["derived_projection"]["ib1c_profile_compatible"] is False
    assert projection.derived_json_bytes.endswith(b"\n")
    assert projection.derived_json_bytes.count(b"\n") == 1
    assert payload["derived_projection"]["field_lineage"]["accepted_at"] == {
        "source_role": "header",
        "source_sha256": hash_bytes(_header(owners)),
        "transform": "unverified-eastern-timezone-interpretation-v1",
    }
    assert payload["source_fields"]["header_owner_ciks_raw"] == list(owners)
    assert payload["source_fields"]["xml_owner_ciks_text"] == list(owners)
    assert payload["derived_projection"]["reporting_owner_count"] == len(owners)
    assert payload["derived_projection"]["buyer_attribution_available"] is False
    assert payload["authority"]["direct_ib1c_ingest_authorized"] is False
    assert payload["authority"]["canonical_evidence"] is False
    assert payload["authority"]["source_authenticated"] is False
    assert payload["authority"]["timezone_interpretation_verified"] is False
    assert payload["authority"]["prior_code_sha_artifact_verified"] is False
    assert payload["authority"]["first_pass_pacing_trace_verified"] is False
    assert payload["authority"]["research_looks"] == 0
    assert projection.sha256 == _derive(owners=owners).sha256


def test_owner_permutation_changes_parent_and_projection_identity_without_collapsing():
    owners = ("0000999999", "0000888888")
    reordered = tuple(reversed(owners))
    first = _derive(owners=owners)
    second = _derive(owners=reordered)
    assert first.sha256 != second.sha256
    assert first.to_payload()["source_fields"]["header_owner_ciks_raw"] == list(owners)
    assert second.to_payload()["source_fields"]["header_owner_ciks_raw"] == list(reordered)


def test_cross_source_owner_order_can_differ_but_both_source_orders_are_retained():
    owners = ("0000999999", "0000888888")
    projection = _derive(owners=owners, xml=_xml(tuple(reversed(owners))))
    fields = projection.to_payload()["source_fields"]
    assert fields["header_owner_ciks_raw"] == list(owners)
    assert fields["xml_owner_ciks_text"] == list(reversed(owners))
    assert projection.to_payload()["derived_projection"]["buyer_attribution_available"] is False


@pytest.mark.parametrize("header", [
    _header(("0000999999", "0000888888")).replace(b"<CIK>0000888888", b"<CIK>0"),
    _header(("0000999999", "0000888888")).replace(b"<CIK>0000888888", b"<CIK>0000999999"),
    _header().replace(b"<CIK>0000999999\n", b""),
    _header().replace(b"</OWNER-DATA>", b"<CIK>0000999999\n</OWNER-DATA>"),
    _header().replace(b"</REPORTING-OWNER>\n", b""),
    _header().replace(b"<ISSUER>", b"<REPORTING-OWNER>\n<ISSUER>"),
    _header().replace(b"</ISSUER>\n", b"</ISSUER>\n" + _owner("0000888888").encode()),
    _header().replace(b"<CIK>0000123456", b"<CIK>0000999999"),
    _header().replace(b"<TYPE>4\n", b"<TYPE>4\n<TYPE>4\n"),
    _header().replace(b"<OWNER-DATA>\n", b"", 1),
    _header().replace(b"<OWNER-DATA>\n", b"<OWNER-DATA>\n<OWNER-DATA>extra\n", 1),
    _header().replace(b"<COMPANY-DATA>\n", b"<COMPANY-DATA>\n<COMPANY-DATA>extra\n", 1),
])
def test_malformed_or_ambiguous_owner_or_role_is_refused(header):
    with pytest.raises(SecRawParentProjectionError, match="REFUSED"):
        _derive(header=header)


def _real_shape_header(owners: tuple[str, ...] = ("0000999999", "0000888888")) -> bytes:
    # Invented values in the section layout every acquired pilot header uses:
    # owner data, filing values, mail address; issuer data, business and mail
    # addresses, and repeated former-company blocks.
    owner_blocks = "".join(
        "<REPORTING-OWNER>\n<OWNER-DATA>\n<CONFORMED-NAME>Invented Owner\n"
        f"<CIK>{owner}\n</OWNER-DATA>\n<FILING-VALUES>\n<FORM-TYPE>4\n<ACT>34\n"
        "<FILE-NUMBER>000-00000\n<FILM-NUMBER>00000000\n</FILING-VALUES>\n"
        "<MAIL-ADDRESS>\n<STREET1>1 Invented Way\n<CITY>Nowhere\n<STATE>XX\n"
        "<ZIP>00000\n</MAIL-ADDRESS>\n</REPORTING-OWNER>\n"
        for owner in owners
    )
    return (
        "<SEC-HEADER>0000999999-22-000001.hdr.sgml : 20221107\n"
        "<ACCEPTANCE-DATETIME>20221107101112\n"
        "<ACCESSION-NUMBER>0000999999-22-000001\n"
        "<TYPE>4\n<PUBLIC-DOCUMENT-COUNT>1\n<PERIOD>20221103\n"
        "<FILING-DATE>20221107\n<DATE-OF-FILING-DATE-CHANGE>20221107\n"
        + owner_blocks
        + "<ISSUER>\n<COMPANY-DATA>\n<CONFORMED-NAME>Invented Issuer\n<CIK>0000123456\n"
          "<ASSIGNED-SIC>0000\n<IRS-NUMBER>000000000\n<STATE-OF-INCORPORATION>XX\n"
          "<FISCAL-YEAR-END>1231\n</COMPANY-DATA>\n"
          "<BUSINESS-ADDRESS>\n<STREET1>2 Invented Way\n<CITY>Nowhere\n<STATE>XX\n"
          "<ZIP>00000\n<PHONE>0000000000\n</BUSINESS-ADDRESS>\n"
          "<MAIL-ADDRESS>\n<STREET1>2 Invented Way\n<CITY>Nowhere\n<STATE>XX\n"
          "<ZIP>00000\n</MAIL-ADDRESS>\n"
          "<FORMER-COMPANY>\n<FORMER-CONFORMED-NAME>Older Invented Name\n"
          "<DATE-CHANGED>20200101\n</FORMER-COMPANY>\n"
          "<FORMER-COMPANY>\n<FORMER-CONFORMED-NAME>Oldest Invented Name\n"
          "<DATE-CHANGED>20100101\n</FORMER-COMPANY>\n</ISSUER>\n</SEC-HEADER>\n"
    ).encode("ascii")


def test_real_section_layout_with_trailing_subsections_is_accepted():
    owners = ("0000999999", "0000888888")
    payload = _derive(owners=owners, header=_real_shape_header(owners)).to_payload()
    assert payload["source_fields"]["header_owner_ciks_raw"] == list(owners)
    assert payload["source_fields"]["issuer_cik_raw"] == "0000123456"
    assert payload["derived_projection"]["reporting_owner_count"] == 2


@pytest.mark.parametrize(("old", "new", "match"), [
    (b"<MAIL-ADDRESS>\n<STREET1>1 Invented Way", b"<UNKNOWN-SECTION>\n<STREET1>1 Invented Way",
     "unsupported or repeated subsection"),
    (b"</MAIL-ADDRESS>\n</REPORTING-OWNER>", b"</MAIL-ADDRESS>\n<MAIL-ADDRESS>\n<CITY>Again\n</MAIL-ADDRESS>\n</REPORTING-OWNER>",
     "unsupported or repeated subsection"),
    (b"<ZIP>00000\n</MAIL-ADDRESS>\n</REPORTING-OWNER>", b"<ZIP>00000\n<CIK>0000777777\n</MAIL-ADDRESS>\n</REPORTING-OWNER>",
     "nested, malformed, or identity fields"),
    (b"<PHONE>0000000000\n</BUSINESS-ADDRESS>", b"<PHONE>0000000000\n<MAIL-ADDRESS>\n</BUSINESS-ADDRESS>",
     "nested, malformed, or identity fields"),
    (b"</FILING-VALUES>\n", b"", "unbalanced"),
    (b"<FORMER-COMPANY>\n<FORMER-CONFORMED-NAME>Older", b"<FILING-VALUES>\n<FORMER-CONFORMED-NAME>Older",
     "unsupported or repeated subsection"),
])
def test_trailing_subsections_admit_only_known_flat_identity_free_blocks(old, new, match):
    header = _real_shape_header()
    assert old in header
    with pytest.raises(SecRawParentProjectionError, match=match):
        _derive(owners=("0000999999", "0000888888"), header=header.replace(old, new, 1))


def test_xml_owner_set_mismatch_or_duplicate_refused_without_attribution():
    for xml in (_xml(("0000888888",)), _xml(("0000999999", "0000999999")),
                _xml(())):
        with pytest.raises(SecRawParentProjectionError, match="REFUSED"):
            _derive(xml=xml)


@pytest.mark.parametrize("extra", [
    b'<x:reportingOwner xmlns:x="urn:synthetic"><x:reportingOwnerId>'
    b'<x:rptOwnerCik>0000888888</x:rptOwnerCik></x:reportingOwnerId>'
    b'</x:reportingOwner>',
    b'<x:documentType xmlns:x="urn:synthetic">4/A</x:documentType>',
    b'<x:issuer xmlns:x="urn:synthetic"><x:issuerCik>0000888888</x:issuerCik>'
    b'</x:issuer>',
])
def test_qualified_xml_identity_nodes_cannot_be_hidden_from_scope_checks(extra):
    xml = _xml().replace(b"</ownershipDocument>", extra + b"</ownershipDocument>")
    with pytest.raises(SecRawParentProjectionError, match="REFUSED"):
        _derive(xml=xml)


@pytest.mark.parametrize("before,after", [
    (b"<documentType>4</documentType>",
     b"<documentType>4<other>4/A</other></documentType>"),
    (b"<issuerCik>0000123456</issuerCik>",
     b"<issuerCik>0000123456<other>0000999999</other></issuerCik>"),
    (b"<rptOwnerCik>0000999999</rptOwnerCik>",
     b"<rptOwnerCik>0000999999<other>0000888888</other></rptOwnerCik>"),
])
def test_xml_identity_nodes_must_be_scalar_leaves(before, after):
    with pytest.raises(SecRawParentProjectionError, match="REFUSED"):
        _derive(xml=_xml().replace(before, after))


def test_header_owner_cap_is_explicit_and_later_owner_is_not_discarded():
    at_cap = tuple(f"{index:010d}" for index in range(1, 257))
    assert _derive(owners=at_cap).to_payload()["derived_projection"]["reporting_owner_count"] == 256
    beyond = at_cap + ("0000000257",)
    with pytest.raises(SecRawParentProjectionError, match="REFUSED"):
        _derive(owners=beyond)


def test_header_crlf_and_short_cik_are_distinct_raw_byte_identities():
    original = _derive()
    crlf = _derive(header=_header().replace(b"\n", b"\r\n"))
    short_cik = _derive(owners=("999999",), xml=_xml(("999999",)))
    assert crlf.sha256 != original.sha256
    assert short_cik.to_payload()["source_fields"]["header_owner_ciks_raw"] == ["999999"]
    assert short_cik.to_payload()["source_fields"]["header_owner_ciks_normalized"] == ["0000999999"]


def test_form_4_amendment_projection_keeps_original_link_unavailable():
    target = replace(_target(), form_type="4/A")
    header = _header().replace(b"<TYPE>4\n", b"<TYPE>4/A\n")
    xml = _xml().replace(b"<documentType>4</documentType>",
                         b"<documentType>4/A</documentType>")
    projection = derive_sec_raw_parent_projection(target, _index(), header, xml)
    payload = projection.to_payload()
    assert payload["derived_projection"]["amendment_original_accession_unavailable"] is True
    assert "original_accession_number" not in payload["derived_projection"]["flat_payload"]
    assert payload["authority"]["direct_ib1c_ingest_authorized"] is False


@pytest.mark.parametrize("index,xml", [
    (b'{"directory":{"item":[{"name":"wrong.xml"}]}}', None),
    (b'{"directory":{"item":[{"name":"ownership.xml"},{"name":"other.xml"}]}}', None),
    (b'{"directory":{"item":[],"item":[]}}', None),
    (None, b"<!DOCTYPE ownershipDocument><ownershipDocument/>"),
    (None, _xml().replace(b"<documentType>4", b"<documentType>4/A")),
])
def test_index_or_xml_identity_ambiguity_refused(index, xml):
    with pytest.raises(SecRawParentProjectionError, match="REFUSED"):
        _derive(index=index, xml=xml)


def test_deep_index_nesting_refuses_with_contract_error_not_recursion_error():
    index = (b'{"directory":{"item":[{"name":"ownership.xml"}]},"unused":'
             + b"[" * 10000 + b"0" + b"]" * 10000 + b"}")
    with pytest.raises(SecRawParentProjectionError, match="REFUSED"):
        _derive(index=index)


def test_input_types_and_payload_mutation_do_not_change_projection():
    with pytest.raises(SecRawParentProjectionError, match="REFUSED"):
        derive_sec_raw_parent_projection(_target(), bytearray(_index()), _header(), _xml())
    projection = _derive()
    before = projection.sha256
    payload = projection.to_payload()
    payload["source_fields"]["header_owner_ciks_raw"].append("0000000001")
    payload["authority"]["canonical_evidence"] = True
    assert projection.sha256 == before


def test_derivation_and_serialization_perform_no_file_io(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("zero-I/O contract attempted filesystem access")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    projection = _derive(owners=("0000999999", "0000888888"))
    assert projection.to_payload()["derived_projection"]["reporting_owner_count"] == 2
    assert projection.sha256
