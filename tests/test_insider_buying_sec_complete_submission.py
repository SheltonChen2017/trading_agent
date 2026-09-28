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


def _legacy_owner(cik: str) -> bytes:
    return (
        "REPORTING-OWNER:\n\n"
        "\tOWNER DATA:\n"
        "\t\tCOMPANY CONFORMED NAME:\tInvented Owner\n"
        f"\t\tCENTRAL INDEX KEY:\t{cik}\n"
        "\n\tFILING VALUES:\n"
        "\t\tFORM TYPE:\t4\n"
        "\n\tMAIL ADDRESS:\n"
        "\t\tSTREET 1:\tInvented Street\n"
    ).encode("ascii")


def _legacy_header(owners: tuple[str, ...] = ("0000999999",)) -> bytes:
    return (
        b"<SEC-HEADER>0000999999-22-000001.hdr.sgml : 20221107\n"
        b"<ACCEPTANCE-DATETIME>20221107101112\n"
        b"ACCESSION NUMBER:\t0000999999-22-000001\n"
        b"CONFORMED SUBMISSION TYPE:\t4\n"
        b"PUBLIC DOCUMENT COUNT:\t1\n"
        b"CONFORMED PERIOD OF REPORT:\t20221107\n"
        b"FILED AS OF DATE:\t20221107\n"
        b"DATE AS OF CHANGE:\t20221107\n\n"
        + b"".join(_legacy_owner(owner) for owner in owners)
        + b"\nISSUER:\n\n"
          b"\tCOMPANY DATA:\n"
          b"\t\tCOMPANY CONFORMED NAME:\tInvented Issuer\n"
          b"\t\tCENTRAL INDEX KEY:\t0000123456\n"
          b"\n\tBUSINESS ADDRESS:\n"
          b"\t\tSTREET 1:\tInvented Road\n"
          b"\n\tMAIL ADDRESS:\n"
          b"\t\tSTREET 1:\tInvented Road\n"
          b"\n\tFORMER COMPANY:\n"
          b"\t\tFORMER CONFORMED NAME:\tInvented Previous\n"
          b"\n\tFORMER COMPANY:\n"
          b"\t\tFORMER CONFORMED NAME:\tInvented Earlier\n"
          b"</SEC-HEADER>\n"
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


def test_legacy_column_header_retains_exact_bytes_and_identity_without_promotion():
    header = _legacy_header(("0000999999", "0000888888"))
    raw = _complete(header=header, owners=("0000999999", "0000888888"))
    projection = _project(raw)
    payload = projection.to_payload()
    assert projection.header_bytes == header
    assert projection.xml_bytes == _xml(("0000999999", "0000888888"))
    assert projection.accepted_at_raw == "20221107101112"
    assert projection.header_owner_ciks == ("0000999999", "0000888888")
    assert payload["children"]["header"]["sha256"] == hash_bytes(header)
    assert payload["authority"]["canonical_evidence"] is False
    assert payload["authority"]["real_shape_verified"] is False


def test_legacy_structural_labels_allow_only_bounded_trailing_tabs():
    header = (_legacy_header()
              .replace(b"REPORTING-OWNER:\n", b"REPORTING-OWNER:\t\n")
              .replace(b"\tOWNER DATA:\n", b"\tOWNER DATA:\t\n")
              .replace(b"ISSUER:\n", b"ISSUER:\t\t\n")
              .replace(b"\tCOMPANY DATA:\n", b"\tCOMPANY DATA:\t\n"))
    assert _project(_complete(header=header)).header_bytes == header
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        _project(_complete(header=header.replace(
            b"REPORTING-OWNER:\t\n", b"REPORTING-OWNER:\t\t\t\t\t\n"
        )))


@pytest.mark.parametrize("old,new", [
    (b"ACCESSION NUMBER:\t0000999999-22-000001", b"ACCESSION NUMBER:\t0000999999-22-000002"),
    (b"CONFORMED SUBMISSION TYPE:\t4", b"CONFORMED SUBMISSION TYPE:\t4/A"),
    (b"FILED AS OF DATE:\t20221107", b"FILED AS OF DATE:\t20221108"),
    (b"<ACCEPTANCE-DATETIME>20221107101112", b"<ACCEPTANCE-DATETIME>20221107101199"),
    (b"CENTRAL INDEX KEY:\t0000123456", b"CENTRAL INDEX KEY:\t0000777777"),
    (b"\t\tFORM TYPE:\t4", b"\t\tFORM TYPE:\t4/A"),
    (b"PUBLIC DOCUMENT COUNT:\t1", b"PUBLIC DOCUMENT COUNT:\t0"),
    (b"CONFORMED PERIOD OF REPORT:\t20221107", b"CONFORMED PERIOD OF REPORT:\tbad"),
])
def test_legacy_column_header_refuses_wrong_identity(old, new):
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        _project(_complete(header=_legacy_header().replace(old, new)))


def test_legacy_declared_document_count_must_match_envelope():
    header = _legacy_header().replace(
        b"PUBLIC DOCUMENT COUNT:\t1", b"PUBLIC DOCUMENT COUNT:\t2"
    )
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        _project(_complete(header=header))


@pytest.mark.parametrize("old,new", [
    (b"ACCESSION NUMBER:\t0000999999-22-000001\n", b"ACCESSION NUMBER:\t0000999999-22-000001\nACCESSION NUMBER:\t0000999999-22-000001\n"),
    (b"PUBLIC DOCUMENT COUNT:\t1\n", b"UNKNOWN FIELD:\t1\n"),
    (b"REPORTING-OWNER:\n", b"\tREPORTING-OWNER:\n"),
    (b"\tOWNER DATA:\n", b"\tFOREIGN DATA:\n"),
    (b"\t\tCENTRAL INDEX KEY:\t0000999999", b"\tCENTRAL INDEX KEY:\t0000999999"),
    (b"\t\tCENTRAL INDEX KEY:\t0000999999\n", b"\t\tCENTRAL INDEX KEY:\t0000999999\n\t\tCENTRAL INDEX KEY:\t0000999999\n"),
    (b"\tMAIL ADDRESS:\n", b"\tOWNER DATA:\n"),
    (b"\t\tSTREET 1:\tInvented Street", b"\t\tCENTRAL INDEX KEY:\t0000999999"),
    (b"\t\tSTREET 1:\tInvented Street", b"\t\tISSUER:\tInvented Street"),
    (b"ISSUER:\n", b"REPORTING-OWNER:\n"),
    (b"\tFORMER COMPANY:\n", b"\tFILING VALUES:\n"),
])
def test_legacy_column_header_refuses_ambiguous_or_foreign_scope(old, new):
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        _project(_complete(header=_legacy_header().replace(old, new)))


def test_legacy_blank_line_is_not_allowed_inside_a_leaf_block():
    header = _legacy_header().replace(
        b"\t\tCOMPANY CONFORMED NAME:\tInvented Owner\n",
        b"\t\tCOMPANY CONFORMED NAME:\tInvented Owner\n\n",
    )
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        _project(_complete(header=header))


def test_legacy_blank_line_run_is_bounded():
    header = _legacy_header().replace(b"REPORTING-OWNER:\n\n", b"REPORTING-OWNER:\n\n\n\n")
    with pytest.raises(SecCompleteSubmissionError, match="REFUSED"):
        _project(_complete(header=header))


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


# Section 107 (Claude review): regression for IBSECCOM-CR01. A document
# header that carries DESCRIPTION but lacks a required field must be a typed
# refusal, not a KeyError.
@pytest.mark.parametrize("missing", ["TYPE", "SEQUENCE", "FILENAME"])
def test_document_header_missing_required_field_is_a_typed_refusal(missing):
    fields = {
        "TYPE": b"<TYPE>4\n",
        "SEQUENCE": b"<SEQUENCE>1\n",
        "FILENAME": b"<FILENAME>ownership.xml\n",
    }
    document = (b"<DOCUMENT>\n"
                + b"".join(line for name, line in fields.items() if name != missing)
                + b"<DESCRIPTION>Invented ownership document\n<TEXT>\n"
                + _xml() + b"</TEXT>\n</DOCUMENT>\n")
    with pytest.raises(SecCompleteSubmissionError,
                       match="lacks type, sequence, or filename"):
        _project(_complete(document=document))
