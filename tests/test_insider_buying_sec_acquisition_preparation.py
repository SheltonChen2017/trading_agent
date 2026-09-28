"""Synthetic-only request planning and SEC-header projection boundary tests.

Nothing here downloads a filing, publishes a metadata source, selects a real
accession, authenticates SEC origin, or claims point-in-time/source authority.
The SGML examples are invented fixtures; filename and capture fields remain
caller declarations even when all internal-consistency checks pass.
"""
from __future__ import annotations

import ast
import base64
import dataclasses
import json
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import sec_acquisition_preparation as preparation
from research.insider_buying.sec_acquisition_preparation import (
    SecAcquisitionPreparationError,
    SecAcquisitionTarget,
    build_sec_acquisition_plan,
    derive_sec_header_projection,
)


RETRIEVED = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
CAPTURE_COMMIT = "d" * 40
QUARTER_HASH = "a" * 64
ROW_HASH = "b" * 64
ACCESSION = "0000999999-22-000001"
ISSUER_CIK = "0000123456"


def _target(**overrides) -> SecAcquisitionTarget:
    values = {
        "period": "2022Q4",
        "accession_number": ACCESSION,
        "form_type": "4",
        "filing_date": "2022-11-07",
        "issuer_cik": ISSUER_CIK,
        "quarterly_zip_sha256": QUARTER_HASH,
        "submission_row_id": ROW_HASH,
        "primary_xml_filename": "ownership.xml",
    }
    values.update(overrides)
    return SecAcquisitionTarget(**values)


def _header(
    target: SecAcquisitionTarget | None = None,
    *,
    acceptance: str = "20221107101112",
    issuer_cik: str = ISSUER_CIK,
) -> bytes:
    target = target or _target()
    return (
        "<SEC-HEADER>\n"
        f"ACCESSION NUMBER: {target.accession_number}\n"
        f"CONFORMED SUBMISSION TYPE: {target.form_type}\n"
        f"FILED AS OF DATE: {target.filing_date.replace('-', '')}\n"
        f"<ACCEPTANCE-DATETIME>{acceptance}\n"
        "ISSUER:\n"
        " COMPANY DATA:\n"
        f"  CENTRAL INDEX KEY: {issuer_cik}\n"
        "REPORTING-OWNER:\n"
        " COMPANY DATA:\n"
        "  CENTRAL INDEX KEY: 0000999999\n"
        "</SEC-HEADER>\n"
    ).encode("ascii")


def _projection(
    target: SecAcquisitionTarget | None = None,
    header: bytes | None = None,
    **overrides,
):
    target = target or _target()
    values = {
        "target": target,
        "header_bytes": _header(target) if header is None else header,
        "source_url": target.header_url,
        "retrieved_at": RETRIEVED,
        "capture_git_commit": CAPTURE_COMMIT,
    }
    values.update(overrides)
    return derive_sec_header_projection(**values)


def _assert_zero_authority(payload: dict[str, object]) -> None:
    authority = payload["authority"]
    assert type(authority) is dict
    assert len(authority) >= 8
    look_fields = {"research_looks", "authorized_outcome_looks", "consumed_outcome_looks"}
    for key in look_fields:
        assert type(authority[key]) is int
        assert authority[key] == 0
    assert all(
        type(value) is bool and value is False
        for key, value in authority.items()
        if key not in look_fields
    )


def test_target_urls_bind_issuer_not_accession_prefix_and_keep_source_claims():
    target = _target()
    root = (
        "https://www.sec.gov/Archives/edgar/data/123456/"
        "000099999922000001/"
    )
    assert target.header_url == root + ACCESSION + ".hdr.sgml"
    assert target.index_url == root + ACCESSION + "-index.htm"
    assert target.primary_xml_url == root + "ownership.xml"
    assert target.to_payload() == {
        "period": "2022Q4",
        "accession_number": ACCESSION,
        "form_type": "4",
        "filing_date": "2022-11-07",
        "issuer_cik": ISSUER_CIK,
        "quarterly_zip_sha256": QUARTER_HASH,
        "submission_row_id": ROW_HASH,
        "primary_xml_filename": "ownership.xml",
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        target.form_type = "4/A"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("period", "2022q4"),
        ("period", "2022Q3"),
        ("period", "2023Q2"),
        ("period", "2024Q1"),
        ("period", True),
        ("accession_number", "000099999922000001"),
        ("accession_number", "0000999999-23-000001"),
        ("accession_number", "0000999999-22-000001\n"),
        ("accession_number", True),
        ("form_type", "3"),
        ("form_type", "5/A"),
        ("form_type", "4-a"),
        ("form_type", " 4"),
        ("form_type", True),
        ("filing_date", "2022-11-31"),
        ("filing_date", "2022-09-30"),
        ("filing_date", "2023-01-01"),
        ("filing_date", "20221107"),
        ("filing_date", datetime(2022, 11, 7)),
        ("issuer_cik", "123456"),
        ("issuer_cik", "0000000000"),
        ("issuer_cik", "000012345x"),
        ("issuer_cik", 123456),
        ("quarterly_zip_sha256", "A" * 64),
        ("quarterly_zip_sha256", "a" * 63),
        ("quarterly_zip_sha256", True),
        ("submission_row_id", "B" * 64),
        ("submission_row_id", "b" * 65),
        ("submission_row_id", True),
        ("primary_xml_filename", ""),
        ("primary_xml_filename", "../ownership.xml"),
        ("primary_xml_filename", "/ownership.xml"),
        ("primary_xml_filename", "x/ownership.xml"),
        ("primary_xml_filename", "x\\ownership.xml"),
        ("primary_xml_filename", "ownership.xml?x=1"),
        ("primary_xml_filename", "ownership.xml#part"),
        ("primary_xml_filename", "%2e%2e.xml"),
        ("primary_xml_filename", "ownership.XML"),
        ("primary_xml_filename", "ownership.xsl"),
        ("primary_xml_filename", "xslF345X05.xml"),
        ("primary_xml_filename", "xslF345X05/ownership.xml"),
        ("primary_xml_filename", "ownership..xml"),
        ("primary_xml_filename", " ownership.xml"),
        ("primary_xml_filename", "ownership.xml\n"),
        ("primary_xml_filename", "ü.xml"),
        ("primary_xml_filename", True),
    ],
)
def test_target_dangerous_spelling_scope_and_type_directions_refused(field, value):
    with pytest.raises(SecAcquisitionPreparationError):
        _target(**{field: value})


def test_plan_has_canonical_order_source_bindings_and_nonexecuting_policy():
    first = _target()
    second = _target(
        period="2023Q1",
        accession_number="0000999999-23-000002",
        filing_date="2023-03-13",
        form_type="4/A",
        submission_row_id="c" * 64,
    )
    plan = build_sec_acquisition_plan((second, first))
    replay = build_sec_acquisition_plan((first, second))
    assert plan.targets == (first, second)
    assert plan.to_payload() == replay.to_payload()
    assert plan.sha256 == replay.sha256 == hash_payload(plan.to_payload())
    payload = plan.to_payload()
    assert payload["targets"] == [first.to_payload(), second.to_payload()]
    assert payload["requests"] == [
        {
            "target_accession": target.accession_number,
            "header_url": target.header_url,
            "index_url": target.index_url,
            "primary_xml_url": target.primary_xml_url,
        }
        for target in (first, second)
    ]
    assert payload["transport_policy"] == {
        "current_external_request_budget": 0,
        "requests_per_second_ceiling": 2,
        "max_attempts_per_artifact": 3,
        "redirects_allowed": False,
        "identifying_contact_required": True,
        "backoff_and_checkpoint_required": True,
        "immutable_accession_cache_required": True,
        "executable_transport_supplied": False,
    }
    _assert_zero_authority(payload)
    assert payload["authority"]["target_inventory_verified"] is False
    assert payload["authority"]["sample_owner_approved"] is False
    payload["authority"]["sample_owner_approved"] = True
    payload["targets"][0]["quarterly_zip_sha256"] = "f" * 64
    payload["requests"][0]["header_url"] = "https://example.test/evil"
    assert plan.to_payload() == replay.to_payload()


def test_plan_limit_is_exactly_64_not_a_full_window_or_256_document_pilot():
    targets = tuple(
        _target(accession_number=f"0000999999-22-{index:06d}")
        for index in range(1, 66)
    )
    assert len(build_sec_acquisition_plan(targets[:64]).targets) == 64
    with pytest.raises(SecAcquisitionPreparationError):
        build_sec_acquisition_plan(targets)


@pytest.mark.parametrize("targets", [(), [], [_target()], (True,), None, True])
def test_plan_refuses_empty_non_tuple_and_non_exact_target_inputs(targets):
    with pytest.raises(SecAcquisitionPreparationError):
        build_sec_acquisition_plan(targets)


def test_builder_refuses_caller_iterators_without_executing_their_callbacks():
    consumed = []

    def candidates():
        for index in range(1, 100):
            consumed.append(index)
            yield _target(accession_number=f"0000999999-22-{index:06d}")

    with pytest.raises(SecAcquisitionPreparationError):
        build_sec_acquisition_plan(candidates())
    assert consumed == []

    class IterableCallback:
        calls = 0

        def __iter__(self):
            self.calls += 1
            return iter((_target(),))

    callback = IterableCallback()
    with pytest.raises(SecAcquisitionPreparationError):
        build_sec_acquisition_plan(callback)
    assert callback.calls == 0

    class TupleSubclass(tuple):
        calls = 0

        def __iter__(self):
            self.calls += 1
            return super().__iter__()

    subclass = TupleSubclass((_target(),))
    with pytest.raises(SecAcquisitionPreparationError):
        build_sec_acquisition_plan(subclass)
    assert subclass.calls == 0


def test_plan_refuses_duplicate_accessions_even_if_different_filename_or_claim():
    target = _target()
    for duplicate in (target, _target(primary_xml_filename="another.xml")):
        with pytest.raises(SecAcquisitionPreparationError):
            build_sec_acquisition_plan((target, duplicate))


def test_target_subclass_and_mutated_target_cannot_enter_plan_or_projection():
    class TargetSubclass(SecAcquisitionTarget):
        pass

    with pytest.raises(SecAcquisitionPreparationError):
        TargetSubclass(**_target().to_payload())
    subclass = object.__new__(TargetSubclass)
    for name, value in _target().to_payload().items():
        object.__setattr__(subclass, name, value)
    with pytest.raises(SecAcquisitionPreparationError):
        build_sec_acquisition_plan((subclass,))
    with pytest.raises(SecAcquisitionPreparationError):
        derive_sec_header_projection(
            subclass, _header(), source_url=_target().header_url,
            retrieved_at=RETRIEVED, capture_git_commit=CAPTURE_COMMIT,
        )
    forged = _target()
    object.__setattr__(forged, "issuer_cik", "0000000000")
    with pytest.raises(SecAcquisitionPreparationError):
        build_sec_acquisition_plan((forged,))
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(target=forged, header=_header())


@pytest.mark.parametrize(
    ("period", "accession", "day", "raw", "expected"),
    [
        ("2022Q4", ACCESSION, "2022-10-03", "20221003101112", "2022-10-03T10:11:12-04:00"),
        ("2022Q4", ACCESSION, "2022-11-07", "20221107101112", "2022-11-07T10:11:12-05:00"),
        ("2022Q4", ACCESSION, "2022-11-06", "20221106020000", "2022-11-06T02:00:00-05:00"),
        ("2023Q1", "0000999999-23-000001", "2023-03-10", "20230310101112", "2023-03-10T10:11:12-05:00"),
        ("2023Q1", "0000999999-23-000001", "2023-03-12", "20230312030000", "2023-03-12T03:00:00-04:00"),
        ("2023Q1", "0000999999-23-000001", "2023-03-13", "20230313101112", "2023-03-13T10:11:12-04:00"),
    ],
)
def test_header_exact_acceptance_offsets_are_versioned_not_host_zoneinfo(
    period, accession, day, raw, expected
):
    target = _target(period=period, accession_number=accession, filing_date=day)
    projection = _projection(target, _header(target, acceptance=raw))
    assert projection.accepted_at_text == expected
    assert projection.raw_acceptance_text == raw
    assert projection.flat_payload()["accepted_at"] == expected


@pytest.mark.parametrize("raw", ["20221106010000", "20221106013000", "20221106015959"])
def test_fall_ambiguous_hour_is_refused_not_assigned_an_earlier_fold(raw):
    target = _target(filing_date="2022-11-06")
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(target, _header(target, acceptance=raw))


@pytest.mark.parametrize("raw", ["20230312020000", "20230312023000", "20230312025959"])
def test_spring_nonexistent_hour_is_refused_not_shifted_forward(raw):
    target = _target(
        period="2023Q1", accession_number="0000999999-23-000001", filing_date="2023-03-12"
    )
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(target, _header(target, acceptance=raw))


@pytest.mark.parametrize("raw", ["202211070959", "202211070959599", "20221107240000", "20221107106000", "20221107101160", "20221307101112", "20220230101112", "2022110710111x"])
def test_malformed_or_impossible_raw_acceptance_is_refused(raw):
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(header=_header(acceptance=raw))


def test_fixed_conservative_filing_day_window_refuses_first_edt_hour_and_endpoint():
    target = _target(filing_date="2022-10-03")
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(target, _header(target, acceptance="20221003005959"))
    assert _projection(target, _header(target, acceptance="20221003010000"))
    winter = _target()
    assert _projection(winter, _header(winter, acceptance="20221107000000"))
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(winter, _header(winter, acceptance="20221108000000"))


def test_retrieval_before_acceptance_refused_and_equal_instant_allowed():
    accepted_utc = datetime(2022, 11, 7, 15, 11, 12, tzinfo=timezone.utc)
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(retrieved_at=accepted_utc - timedelta(seconds=1))
    assert _projection(retrieved_at=accepted_utc).accepted_at_text == "2022-11-07T10:11:12-05:00"


def test_header_projection_is_derived_not_verbatim_and_retains_exact_lineage():
    target = _target(form_type="4/A")
    header = _header(target)
    projection = _projection(target, header)
    payload = projection.to_payload()
    assert payload["target"] == target.to_payload()
    assert projection.header_bytes == header
    assert projection.header_sha256 == hash_bytes(header)
    assert projection.derived_json_bytes != header
    assert projection.derived_json_bytes == (canonical_json(projection.flat_payload()) + "\n").encode("utf-8")
    assert projection.derived_json_sha256 == hash_bytes(projection.derived_json_bytes)
    assert json.loads(projection.derived_json_bytes) == projection.flat_payload()
    assert projection.sha256 == hash_payload(payload)
    assert payload["raw_header"] == {
        "sha256": hash_bytes(header),
        "size_bytes": len(header),
        "bytes_base64": base64.b64encode(header).decode("ascii"),
        "source_url": target.header_url,
        "retrieved_at_utc": RETRIEVED.isoformat(timespec="seconds"),
        "capture_git_commit": CAPTURE_COMMIT,
    }
    assert payload["source_fields"] == {
        "accession_number": ACCESSION,
        "form_type": "4/A",
        "filing_date_raw": "20221107",
        "accepted_at_raw": "20221107101112",
        "issuer_cik_raw": ISSUER_CIK,
    }
    assert payload["derivation"]["timezone_policy"]
    assert payload["derivation"]["primary_xml_filename_caller_declared"] is True
    assert payload["derivation"]["primary_document_url_verified"] is False
    assert payload["derivation"]["timezone_interpretation_verified"] is False
    assert payload["derivation"]["verbatim_sec_json_claim"] is False
    assert payload["derivation"]["amendment_original_inferred"] is False
    assert payload["derivation"]["field_transforms"] == {
        "accession_number": "sec-header-accession-number-v1",
        "form_type": "sec-header-conformed-submission-type-v1",
        "filing_date": "sec-header-filed-as-of-date-yyyymmdd-to-iso-v1",
        "accepted_at": "sec-header-acceptance-datetime-eastern-2022q4-2023q1-v1",
        "primary_document_url": "caller-declared-filename-plus-candidate-issuer-archives-path-v1",
    }
    assert projection.flat_payload() == {
        "accession_number": ACCESSION,
        "form_type": "4/A",
        "filing_date": "2022-11-07",
        "accepted_at": "2022-11-07T10:11:12-05:00",
        "primary_document_url": target.primary_xml_url,
    }
    _assert_zero_authority(payload)
    assert type(projection).__name__ != "SecEdgarMetadataSource"
    profile = payload["derived_json"]["profile"]
    assert payload["derived_json"]["profile_sha256"] == hash_payload(profile)
    assert profile["exact_fields"] == sorted(projection.flat_payload())
    assert profile["official_sec_profile_verified"] is False
    assert profile["direct_ib1c_ingest_authorized"] is False
    assert profile["timezone_policy"] == payload["derivation"]["timezone_policy"]
    assert payload["derived_json"]["size_bytes"] == len(projection.derived_json_bytes)
    assert payload["derived_json"]["encoding"] == "utf-8"
    assert payload["derived_json"]["terminal_lf_count"] == 1
    payload["authority"]["research_looks"] = 99
    payload["derivation"]["primary_document_url_verified"] = True
    payload["raw_header"]["sha256"] = "f" * 64
    flat = projection.flat_payload()
    flat["accepted_at"] = "2022-11-07T00:00:00+00:00"
    assert projection.sha256 == hash_payload(projection.to_payload())
    assert projection.flat_payload()["accepted_at"] == "2022-11-07T10:11:12-05:00"
    _assert_zero_authority(projection.to_payload())


def test_reporting_owner_cik_does_not_replace_issuer_cik():
    header = _header(issuer_cik="0000000042").replace(b"CENTRAL INDEX KEY: 0000999999", b"CENTRAL INDEX KEY: 0000123456")
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(header=header)
    assert _projection().target.issuer_cik == ISSUER_CIK


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b"ACCESSION NUMBER: " + ACCESSION.encode(), b"ACCESSION NUMBER: 0000999999-22-000002"),
        (b"CONFORMED SUBMISSION TYPE: 4", b"CONFORMED SUBMISSION TYPE: 4/A"),
        (b"FILED AS OF DATE: 20221107", b"FILED AS OF DATE: 20221108"),
        (b"ISSUER:", b"FILER:"),
        (b"CENTRAL INDEX KEY: 0000123456", b"CENTRAL INDEX KEY: 0000000000"),
        (b"CENTRAL INDEX KEY: 0000123456", b"CENTRAL INDEX KEY: 12345"),
    ],
)
def test_header_mismatch_or_missing_exact_issuer_role_refused(old, new):
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(header=_header().replace(old, new, 1))


@pytest.mark.parametrize(
    "line",
    [
        b"ACCESSION NUMBER: " + ACCESSION.encode() + b"\n",
        b"CONFORMED SUBMISSION TYPE: 4\n",
        b"FILED AS OF DATE: 20221107\n",
        b"<ACCEPTANCE-DATETIME>20221107101112\n",
        b"ISSUER:\n",
        b"  CENTRAL INDEX KEY: 0000123456\n",
    ],
)
def test_required_header_field_missing_or_duplicate_refused(line):
    header = _header()
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(header=header.replace(line, b"", 1))
    duplicated = header.replace(line, line + line, 1)
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(header=duplicated)


def test_core_header_metadata_inside_reporting_owner_is_not_preamble_provenance():
    header = _header()
    core_lines = (
        b"ACCESSION NUMBER: " + ACCESSION.encode() + b"\n",
        b"CONFORMED SUBMISSION TYPE: 4\n",
        b"FILED AS OF DATE: 20221107\n",
        b"<ACCEPTANCE-DATETIME>20221107101112\n",
    )
    for line in core_lines:
        header = header.replace(line, b"", 1)
    nested = b"".join(b"  " + line for line in core_lines)
    header = header.replace(b"REPORTING-OWNER:\n COMPANY DATA:\n", b"REPORTING-OWNER:\n COMPANY DATA:\n" + nested)
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(header=header)


def test_raw_unpadded_issuer_cik_is_preserved_while_matching_padded_target():
    projection = _projection(header=_header(issuer_cik="123456"))
    assert projection.target.issuer_cik == ISSUER_CIK
    assert projection.to_payload()["source_fields"]["issuer_cik_raw"] == "123456"


@pytest.mark.parametrize(
    "issuer_block",
    [
        b"ISSUER:\n  CENTRAL INDEX KEY: 0000123456\n",
        b"ISSUER:\n BUSINESS ADDRESS:\n  CENTRAL INDEX KEY: 0000123456\n",
        b"ISSUER:\n COMPANY DATA:\n  COMPANY CONFORMED NAME: Synthetic\n MAIL ADDRESS:\n  CENTRAL INDEX KEY: 0000123456\n",
        b"ISSUER:\n COMPANY DATA:\n  CENTRAL INDEX KEY: 0000123456\n COMPANY DATA:\n",
        b"ISSUER:\n COMPANY DATA:\n  COMPANY CONFORMED NAME: Synthetic\n FORMER COMPANY:\n  CENTRAL INDEX KEY: 0000123456\n",
    ],
)
def test_issuer_cik_requires_unique_exact_company_data_section(issuer_block):
    original = b"ISSUER:\n COMPANY DATA:\n  CENTRAL INDEX KEY: 0000123456\n"
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(header=_header().replace(original, issuer_block, 1))


@pytest.mark.parametrize(
    "role_body",
    [
        b"REPORTING-OWNER:\n COMPANY DATA:\n  CENTRAL INDEX KEY: 0000999999\n  ISSUER:\n   COMPANY DATA:\n    CENTRAL INDEX KEY: 0000123456\n",
        b"ISSUER:\n BUSINESS ADDRESS:\n  COMPANY DATA:\n   CENTRAL INDEX KEY: 0000123456\n",
        b"ISSUER:\n FORMER COMPANY:\n  COMPANY DATA:\n   CENTRAL INDEX KEY: 0000123456\n",
    ],
)
def test_indented_fake_issuer_and_late_nested_company_data_are_not_issuer_roles(role_body):
    preamble = _header().split(b"ISSUER:\n", 1)[0]
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(header=preamble + role_body + b"</SEC-HEADER>\n")


@pytest.mark.parametrize(
    "line",
    [
        b"ACCESSION NUMBER: " + ACCESSION.encode() + b"\n",
        b"CONFORMED SUBMISSION TYPE: 4\n",
        b"FILED AS OF DATE: 20221107\n",
        b"<ACCEPTANCE-DATETIME>20221107101112\n",
    ],
)
def test_header_core_preamble_fields_require_column_zero(line):
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(header=_header().replace(line, b"  " + line, 1))


@pytest.mark.parametrize(
    "header",
    [
        b"",
        b"<SEC-HEADER>\n</SEC-HEADER>\n",
        _header().replace(b"<SEC-HEADER>\n", b"", 1),
        _header().replace(b"</SEC-HEADER>\n", b"", 1),
        _header() + b"<DOCUMENT>unexpected body</DOCUMENT>\n",
        _header() + _header(),
        _header().replace(b"ISSUER:", b"ISSUER:\x00"),
        _header().replace(b"ISSUER:", b"ISSUER:\xff"),
        bytearray(_header()),
        memoryview(_header()),
        _header().decode("ascii"),
    ],
)
def test_nonexact_incomplete_or_nonheader_byte_images_refused(header):
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(header=header)


def test_header_bound_is_frozen_at_two_mib_and_refuses_larger_input():
    assert preparation.MAX_SEC_HEADER_BYTES == 2 * 1024 * 1024
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(header=b" " * (preparation.MAX_SEC_HEADER_BYTES + 1))


def test_crlf_source_bytes_are_preserved_not_normalized_in_source_hash():
    original = _header()
    crlf = original.replace(b"\n", b"\r\n")
    projection = _projection(header=crlf)
    assert projection.header_bytes == crlf
    assert projection.header_sha256 == hash_bytes(crlf) != hash_bytes(original)
    assert projection.flat_payload() == _projection(header=original).flat_payload()
    assert projection.sha256 != _projection(header=original).sha256


@pytest.mark.parametrize(
    "source_url",
    [
        "https://example.test/" + ACCESSION + ".hdr.sgml",
        _target().header_url.replace("https://", "http://"),
        _target().index_url,
        _target().primary_xml_url,
        _target().header_url + "?x=1",
        _target().header_url + "#x",
        _target().header_url.replace("/123456/", "/999999/"),
        _target().header_url.replace(ACCESSION + ".hdr", "0000999999-22-000002.hdr"),
        _target().header_url.replace("www.sec.gov", "data.sec.gov"),
        True,
    ],
)
def test_header_source_url_must_be_exact_bound_header_url(source_url):
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(source_url=source_url)


@pytest.mark.parametrize(
    "retrieved_at",
    [datetime(2026, 9, 27, 18, 0), RETRIEVED.replace(microsecond=1), "2026-09-27T18:00:00+00:00", True, None],
)
def test_retrieval_requires_exact_aware_datetime_at_second_precision(retrieved_at):
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(retrieved_at=retrieved_at)


@pytest.mark.parametrize("capture_git_commit", ["D" * 40, "d" * 39, "d" * 41, "g" * 40, True, None])
def test_capture_commit_requires_canonical_full_git_sha(capture_git_commit):
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(capture_git_commit=capture_git_commit)


def test_mutable_timezone_is_refused_before_any_caller_callback_runs():
    class MutableTimezone(tzinfo):
        offset = timedelta(hours=-4)
        calls = 0

        def utcoffset(self, value):
            self.calls += 1
            return self.offset

        def dst(self, value):
            return timedelta(0)

    caller_timezone = MutableTimezone()
    retrieved = datetime(2026, 9, 27, 14, 0, tzinfo=caller_timezone)
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(retrieved_at=retrieved)
    assert caller_timezone.calls == 0
    caller_timezone.offset = timedelta(hours=5)
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(retrieved_at=retrieved)
    assert caller_timezone.calls == 0


def test_native_fixed_timezone_capture_is_detached_to_canonical_utc():
    retrieved = datetime(2026, 9, 27, 14, 0, tzinfo=timezone(timedelta(hours=-4)))
    projection = _projection(retrieved_at=retrieved)
    assert projection.retrieved_at == RETRIEVED
    assert projection.retrieved_at.tzinfo is timezone.utc
    assert projection.to_payload() == _projection().to_payload()
    assert projection.sha256 == _projection().sha256


def test_caller_timezone_callback_cannot_run_after_url_guard_or_change_source():
    class ReentrantTimezone(tzinfo):
        projection = None
        calls = 0

        def utcoffset(self, value):
            self.calls += 1
            if self.projection is not None:
                object.__setattr__(self.projection, "source_url", "https://evil.example/arbitrary")
            return timedelta(0)

        def dst(self, value):
            return timedelta(0)

    caller_timezone = ReentrantTimezone()
    projection = _projection()
    before = projection.to_payload()
    caller_timezone.projection = projection
    with pytest.raises(SecAcquisitionPreparationError):
        _projection(retrieved_at=RETRIEVED.replace(tzinfo=caller_timezone))
    assert caller_timezone.calls == 0
    assert projection.to_payload() == before
    assert projection.source_url == _target().header_url


def test_plans_and_projections_detach_caller_target_objects():
    target = _target()
    plan = build_sec_acquisition_plan((target,))
    projection = _projection(target)
    before_plan = plan.to_payload()
    before_projection = projection.to_payload()
    object.__setattr__(target, "issuer_cik", "0000000000")
    assert plan.to_payload() == before_plan
    assert projection.to_payload() == before_projection


def test_forged_projection_cannot_serialize_an_unbound_header_or_url():
    for field, value in (
        ("source_url", "https://example.test/forged"),
        ("header_bytes", _header().replace(ACCESSION.encode(), b"0000999999-22-000002")),
        ("capture_git_commit", "x" * 40),
    ):
        projection = _projection()
        object.__setattr__(projection, field, value)
        with pytest.raises(SecAcquisitionPreparationError):
            projection.to_payload()


def test_preparation_module_has_zero_io_and_no_host_timezone_database_dependency():
    source = Path(preparation.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_roots = {
        "os", "pathlib", "socket", "urllib", "http", "requests", "httpx",
        "subprocess", "zoneinfo", "sqlite3", "pickle", "joblib", "quantconnect",
        "execution", "assistant", "broker", "ml",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name.split(".")[0] in forbidden_roots for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden_roots
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "eval", "exec", "__import__"}
    assert "SecEdgarMetadataSource" not in {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }


# Each case below is otherwise valid, so only the named guard can refuse it.


def test_coherent_target_outside_the_approved_window_is_refused_by_scope():
    with pytest.raises(SecAcquisitionPreparationError, match=r"outside 2022Q4\.\.2023Q1"):
        _target(
            period="2023Q2",
            accession_number="0000999999-23-000001",
            filing_date="2023-04-10",
        )


def test_acceptance_outside_the_policy_window_but_inside_the_filing_day_is_refused():
    # 00:30 EDT on 2023-04-01 is 04:30Z, inside the conservative filing-day
    # envelope for a 2023-03-31 filing, so only the timezone-policy window
    # refuses it.
    target = _target(
        period="2023Q1",
        accession_number="0000999999-23-000001",
        filing_date="2023-03-31",
    )
    with pytest.raises(SecAcquisitionPreparationError, match="outside the frozen Eastern policy"):
        _projection(target, _header(target, acceptance="20230401003000"))


def _header_with(target, old: str, new: str) -> bytes:
    text = _header(target).decode("ascii")
    assert old in text
    return text.replace(old, new, 1).encode("latin-1")


def test_embedded_second_sec_header_tag_is_refused():
    target = _target()
    header = _header_with(
        target, "  CENTRAL INDEX KEY: 0000999999\n",
        "  CENTRAL INDEX KEY: 0000999999\n  COMPANY CONFORMED NAME: X <SEC-HEADER> Y\n",
    )
    with pytest.raises(SecAcquisitionPreparationError, match="exactly one complete SEC-HEADER"):
        _projection(target, header)


def test_indented_root_role_name_is_refused():
    target = _target()
    header = _header_with(
        target, "  CENTRAL INDEX KEY: 0000999999\n",
        "  CENTRAL INDEX KEY: 0000999999\n FILED BY:\n",
    )
    with pytest.raises(SecAcquisitionPreparationError, match="root roles must begin at column zero"):
        _projection(target, header)


def test_second_issuer_section_is_refused_not_ignored():
    target = _target()
    header = _header_with(
        target, "</SEC-HEADER>\n",
        "ISSUER:\n COMPANY DATA:\n  CENTRAL INDEX KEY: 0000777777\n</SEC-HEADER>\n",
    )
    with pytest.raises(SecAcquisitionPreparationError, match="exactly one ISSUER section"):
        _projection(target, header)


def test_control_byte_inside_the_header_is_refused():
    target = _target()
    header = _header_with(
        target, "  CENTRAL INDEX KEY: 0000999999\n",
        "  CENTRAL INDEX KEY: 0000999999\n  COMPANY CONFORMED NAME: X\x01Y\n",
    )
    with pytest.raises(SecAcquisitionPreparationError, match="unsupported control bytes"):
        _projection(target, header)


def test_non_ascii_byte_inside_the_header_is_refused():
    target = _target()
    header = _header_with(
        target, "  CENTRAL INDEX KEY: 0000999999\n",
        "  CENTRAL INDEX KEY: 0000999999\n  COMPANY CONFORMED NAME: CAFÉ\n",
    )
    with pytest.raises(SecAcquisitionPreparationError, match="strict ASCII"):
        _projection(target, header)


def test_structurally_valid_header_above_two_mib_is_refused_by_the_size_cap():
    target = _target()
    long_name = "X" * (2 * 1024 * 1024)
    header = _header_with(
        target, "  CENTRAL INDEX KEY: 0000999999\n",
        f"  CENTRAL INDEX KEY: 0000999999\n  COMPANY CONFORMED NAME: {long_name}\n",
    )
    assert len(header) > preparation.MAX_SEC_HEADER_BYTES
    with pytest.raises(SecAcquisitionPreparationError, match="nonempty bounded exact byte image"):
        _projection(target, header)


def test_well_formed_primary_filename_longer_than_255_characters_is_refused():
    filename = "a" * 252 + ".xml"
    assert len(filename) == 256
    with pytest.raises(SecAcquisitionPreparationError, match="raw root XML filename"):
        _target(primary_xml_filename=filename)


def test_forged_plan_target_order_is_refused_at_serialization():
    plan = build_sec_acquisition_plan((
        _target(),
        _target(accession_number="0000999999-22-000002"),
    ))
    object.__setattr__(plan, "targets", tuple(reversed(plan.targets)))
    with pytest.raises(SecAcquisitionPreparationError, match="order was altered"):
        plan.to_payload()


def test_plan_subclass_is_refused_at_construction():
    class DerivedPlan(preparation.SecAcquisitionPlan):
        pass

    with pytest.raises(SecAcquisitionPreparationError, match="exact acquisition plan"):
        DerivedPlan((_target(),))
