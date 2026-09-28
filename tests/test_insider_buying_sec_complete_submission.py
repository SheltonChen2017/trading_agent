"""Invented complete-submission images only; no SEC request or real filing."""
from __future__ import annotations

from dataclasses import replace

import pytest

from data.hashing import hash_bytes
from research.insider_buying import sec_complete_submission as module
from research.insider_buying.sec_complete_submission import (
    SEC_COMPLETE_SUBMISSION_VERSION,
    SecCompleteSubmissionError,
    SecCompleteSubmissionTarget,
    project_sec_complete_submission,
)


def _target() -> SecCompleteSubmissionTarget:
    return SecCompleteSubmissionTarget(
        period="2022Q4",
        accession_number="0000999999-22-000001",
        form_type="4",
        filing_date="2022-11-07",
        issuer_cik="0000123456",
        quarterly_index_sha256="a" * 64,
        # The index CIK can be a reporting owner, not the issuer or accession prefix.
        complete_submission_url=(
            "https://www.sec.gov/Archives/edgar/data/888888/"
            "0000999999-22-000001.txt"
        ),
    )


def _owner(cik: str) -> bytes:
    return ("<REPORTING-OWNER>\n<OWNER-DATA>\n"
            f"<CIK>{cik}\n<CONFORMED-NAME>Invented Owner\n"
            "</OWNER-DATA>\n</REPORTING-OWNER>\n").encode("ascii")


def _header(owners: tuple[str, ...] = ("0000999999",)) -> bytes:
    return (
        b"<SEC-HEADER>0000999999-22-000001.hdr.sgml : 20221107\n"
        b"<ACCEPTANCE-DATETIME>20221107101112\n"
        b"<ACCESSION-NUMBER>0000999999-22-000001\n"
        b"<TYPE>4\n<FILING-DATE>20221107\n"
        + b"".join(_owner(owner) for owner in owners)
        + b"<ISSUER>\n<COMPANY-DATA>\n<CIK>0000123456\n"
          b"</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
    )


def _xml(owners: tuple[str, ...] = ("0000999999",)) -> bytes:
    return (
        b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        b"<ownershipDocument><documentType>4</documentType>"
        b"<issuer><issuerCik>0000123456</issuerCik></issuer>"
        + b"".join(
            ("<reportingOwner><reportingOwnerId>"
             f"<rptOwnerCik>{owner}</rptOwnerCik>"
             "</reportingOwnerId></reportingOwner>").encode("ascii")
            for owner in owners
        )
        + b"</ownershipDocument>\n"
    )


def _document(xml: bytes, *, filename: bytes = b"ownership.xml",
              form: bytes = b"4") -> bytes:
    return (b"<DOCUMENT>\n<TYPE>" + form + b"\n<SEQUENCE>1\n<FILENAME>"
            + filename + b"\n<DESCRIPTION>Invented ownership document\n<TEXT>\n"
            + xml + b"</TEXT>\n</DOCUMENT>\n")


def _complete(*, header: bytes | None = None, xml: bytes | None = None,
              document: bytes | None = None,
              owners: tuple[str, ...] = ("0000999999",)) -> bytes:
    return (b"<SEC-DOCUMENT>0000999999-22-000001.txt : 20221107\n"
            + (_header(owners) if header is None else header)
            + (_document(_xml(owners) if xml is None else xml)
               if document is None else document)
            + b"</SEC-DOCUMENT>\n")


def _project(raw: bytes | None = None, *, target: SecCompleteSubmissionTarget | None = None):
    return project_sec_complete_submission(
        _target() if target is None else target,
        _complete() if raw is None else raw,
    )


def test_exact_raw_and_derived_children_are_hash_bound_without_authority():
    raw = _complete(owners=("0000999999", "0000888888"))
    projection = _project(raw)
    payload = projection.to_payload()
    assert payload["version"] == SEC_COMPLETE_SUBMISSION_VERSION
    assert projection.raw_bytes == raw
    assert projection.header_bytes == _header(("0000999999", "0000888888"))
    assert projection.xml_bytes == _xml(("0000999999", "0000888888"))
    assert projection.primary_xml_filename == "ownership.xml"
    assert projection.accepted_at_raw == "20221107101112"
    assert payload["raw_parent"]["sha256"] == hash_bytes(raw)
    assert payload["raw_parent"]["declared_complete_submission_url"] == _target().complete_submission_url
    assert payload["children"]["header"]["sha256"] == hash_bytes(projection.header_bytes)
    assert payload["children"]["primary_xml"]["sha256"] == hash_bytes(projection.xml_bytes)
    assert payload["raw_parent"]["size_bytes"] == len(raw)
    assert payload["children"]["primary_xml"]["size_bytes"] == len(projection.xml_bytes)
    assert payload["authority"]["source_authenticated"] is False
    assert payload["authority"]["real_shape_verified"] is False
    assert payload["authority"]["point_in_time_data"] is False
    assert payload["authority"]["canonical_evidence"] is False
    assert payload["authority"]["direct_ib1c_ingest_authorized"] is False
    assert payload["authority"]["research_looks"] == 0
    assert projection.sha256 == _project(raw).sha256


def test_line_endings_remain_verbatim_in_each_child():
    raw = _complete().replace(b"\n", b"\r\n")
    projection = _project(raw)
    assert projection.header_bytes == _header().replace(b"\n", b"\r\n")
    assert projection.xml_bytes == _xml().replace(b"\n", b"\r\n")


def test_optional_xml_wrapper_and_non_xml_attachment_do_not_change_primary_choice():
    attachment = (b"<DOCUMENT>\n<TYPE>EX-99\n<SEQUENCE>2\n"
                  b"<FILENAME>attachment.txt\n<TEXT>\nInvented attachment\n"
                  b"</TEXT>\n</DOCUMENT>\n")
    wrapped = _document(b"<XML>\n" + _xml() + b"</XML>\n")
    raw = _complete(document=wrapped + attachment)
    assert _project(raw).xml_bytes == _xml()


def test_index_directory_cik_is_not_assumed_to_be_issuer_or_accession_prefix():
    compact = replace(
        _target(),
        complete_submission_url=(
            "https://www.sec.gov/Archives/edgar/data/888888/"
            "000099999922000001/0000999999-22-000001.txt"
        ),
    )
    assert _project(target=compact).to_payload()["target"]["complete_submission_url"] == compact.complete_submission_url


def test_published_projection_revalidates_derived_bytes():
    projection = _project()
    object.__setattr__(projection, "xml_bytes", b"<ownershipDocument/>")
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        projection.to_payload()


@pytest.mark.parametrize("url", [
    "https://evil.example/Archives/edgar/data/888888/0000999999-22-000001.txt",
    "http://www.sec.gov/Archives/edgar/data/888888/0000999999-22-000001.txt",
    "https://www.sec.gov/Archives/edgar/data/888888/0000999999-22-000002.txt",
    "https://www.sec.gov/Archives/edgar/data/888888/0000999999-22-000001.txt?x=1",
    "https://www.sec.gov/Archives/edgar/data/0/0000999999-22-000001.txt",
    "https://www.sec.gov/Archives/edgar/data/888888/000099999922000002/0000999999-22-000001.txt",
])
def test_target_refuses_foreign_or_unsafe_index_path(url):
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        replace(_target(), complete_submission_url=url)


@pytest.mark.parametrize("old,new", [
    (b"<ACCESSION-NUMBER>0000999999-22-000001", b"<ACCESSION-NUMBER>0000999999-22-000002"),
    (b"<TYPE>4\n<FILING-DATE>", b"<TYPE>4/A\n<FILING-DATE>"),
    (b"<FILING-DATE>20221107", b"<FILING-DATE>20221108"),
    (b"<CIK>0000123456", b"<CIK>0000777777"),
    (b"<ACCEPTANCE-DATETIME>20221107101112", b"<ACCEPTANCE-DATETIME>bad"),
])
def test_header_identity_must_match_target(old, new):
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        _project(_complete(header=_header().replace(old, new)))


@pytest.mark.parametrize("old,new", [
    (b"<documentType>4</documentType>", b"<documentType>4/A</documentType>"),
    (b"<issuerCik>0000123456</issuerCik>", b"<issuerCik>0000777777</issuerCik>"),
    (b"<rptOwnerCik>0000999999</rptOwnerCik>", b"<rptOwnerCik>0000888888</rptOwnerCik>"),
    (b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n", b"<!DOCTYPE ownershipDocument>\n"),
])
def test_xml_identity_and_unsafe_declarations_refuse(old, new):
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        _project(_complete(xml=_xml().replace(old, new)))


@pytest.mark.parametrize("raw", [
    _complete()[:-len(b"</SEC-DOCUMENT>\n")],
    _complete().replace(b"</SEC-HEADER>\n", b""),
    _complete().replace(b"</DOCUMENT>\n", b""),
    _complete().replace(b"</TEXT>\n", b""),
    _complete().replace(b"<DOCUMENT>\n", b"<DOCUMENT>\n<TYPE>4\n"),
    _complete().replace(b"<FILENAME>ownership.xml", b"<FILENAME>../ownership.xml"),
    _complete().replace(b"</DOCUMENT>\n", b"</DOCUMENT>\n" + _document(_xml())),
    _complete().replace(b"</SEC-HEADER>\n", b"</SEC-HEADER>\nforeign\n"),
    _complete().replace(b"</DOCUMENT>\n", b"</DOCUMENT>\n" + _document(_xml(), filename=b"other.xml")),
])
def test_truncated_ambiguous_or_unsafe_envelopes_refuse(raw):
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        _project(raw)


def test_non_bytes_and_oversize_refuse():
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        _project(bytearray(_complete()))
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        _project(b"X" * (8 * 1024 * 1024 + 1))


def test_pre_split_line_cap_refuses_before_materializing_many_lines(monkeypatch):
    raw = _complete()
    assert raw.count(b"\n") > 8
    monkeypatch.setattr(module, "MAX_COMPLETE_SUBMISSION_LINES", 8, raising=False)
    with pytest.raises(SecCompleteSubmissionError, match="line count"):
        _project(raw)


def test_document_cap_refuses_extra_non_xml_attachment(monkeypatch):
    extra = (b"<DOCUMENT>\n<TYPE>EX-99\n<SEQUENCE>2\n"
             b"<FILENAME>invented.txt\n<TEXT>\nInvented\n</TEXT>\n</DOCUMENT>\n")
    monkeypatch.setattr(module, "MAX_COMPLETE_DOCUMENTS", 1)
    with pytest.raises(SecCompleteSubmissionError, match="too many documents"):
        _project(_complete(document=_document(_xml()) + extra))
