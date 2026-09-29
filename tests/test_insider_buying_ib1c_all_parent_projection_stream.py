"""Invented parent bytes only; no source, outcome, or QC operation."""

from __future__ import annotations

import pytest

from data.hashing import hash_payload
from test_insider_buying_ib1b_all_form4_parent_locators import _all_inputs


def _manifest():
    from research.insider_buying.ib1b_all_form4_parent_locators import (
        build_ib1b_all_form4_parent_locator_manifest,
    )

    return build_ib1b_all_form4_parent_locator_manifest(_all_inputs())


def _parent(locator, *, owners: tuple[str, ...] = ("0000876543",)) -> bytes:
    accession = locator.accession_number
    filed = locator.filing_date.replace("-", "")
    issuer = locator.issuer_cik
    form = locator.form_type
    owner_header = b"".join(
        ("<REPORTING-OWNER>\n<OWNER-DATA>\n"
         f"<CIK>{cik}\n<CONFORMED-NAME>Invented Owner\n"
         "</OWNER-DATA>\n</REPORTING-OWNER>\n").encode("ascii")
        for cik in owners
    )
    owner_xml = b"".join(
        ("<reportingOwner><reportingOwnerId>"
         f"<rptOwnerCik>{cik}</rptOwnerCik>"
         "</reportingOwnerId></reportingOwner>").encode("ascii")
        for cik in owners
    )
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        + (f"<ownershipDocument><documentType>{form}</documentType>"
           f"<issuer><issuerCik>{issuer}</issuerCik></issuer>").encode("ascii")
        + owner_xml + b"</ownershipDocument>\n"
    )
    return (
        (f"<SEC-DOCUMENT>{accession}.txt : {filed}\n"
         f"<SEC-HEADER>{accession}.hdr.sgml : {filed}\n"
         f"<ACCEPTANCE-DATETIME>{filed}101112\n"
         f"<ACCESSION-NUMBER>{accession}\n<TYPE>{form}\n"
         f"<FILING-DATE>{filed}\n").encode("ascii")
        + owner_header
        + (f"<ISSUER>\n<COMPANY-DATA>\n<CIK>{issuer}\n"
           "</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
           "<DOCUMENT>\n<TYPE>").encode("ascii")
        + form.encode("ascii")
        + b"\n<SEQUENCE>1\n<FILENAME>ownership.xml\n<TEXT>\n"
        + xml
        + b"</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n"
    )


def _inputs(manifest, *, missing: int | None = None,
            malformed: int | None = None):
    from research.insider_buying.ib1c_all_parent_projection_stream import (
        RawParentProjectionInput,
    )

    for index, locator in enumerate(manifest.iter_locators()):
        raw = None if index == missing else (
            b"not an SEC parent" if index == malformed else _parent(locator)
        )
        yield RawParentProjectionInput(locator.accession_number, raw)


def test_complete_stream_accounts_for_every_form4_including_nonpriority() -> None:
    from research.insider_buying.ib1c_all_parent_projection_stream import (
        build_all_parent_projection_receipt,
    )

    manifest = _manifest()
    observed = []
    receipt = build_all_parent_projection_receipt(
        manifest, _inputs(manifest), on_row=observed.append
    )
    receipt.verify_digest()
    assert (receipt.expected_count, receipt.accounted_count,
            receipt.projected_count, receipt.refused_count) == (6, 6, 6, 0)
    assert receipt.all_projected is True
    assert receipt.locator_manifest_sha256 == manifest.content_sha256
    assert [row.accession_number for row in observed] == [
        locator.accession_number for locator in manifest.iter_locators()
    ]
    assert all(row.status == "PROJECTED" for row in observed)
    assert all(row.raw_parent_sha256 and row.projection_sha256
               and row.accepted_at_raw_sha256 and row.ordered_owner_ciks_sha256
               for row in observed)
    assert observed[0].locator_sha256 == hash_payload(
        manifest.quarters[0].locators[0].to_payload()
    )
    assert receipt.canonical is False
    assert receipt.source_authenticated is False
    assert receipt.acceptance_timezone_verified is False
    assert receipt.point_in_time_data is False
    assert receipt.amendment_lineage_verified is False
    assert receipt.outcome_looks == 0
    assert receipt.qc_jobs == 0
    assert "raw_bytes" not in receipt.to_payload()
    assert "accepted_at_raw" not in receipt.to_payload()
    assert "owner_ciks" not in receipt.to_payload()
    assert "accepted_at_raw" not in observed[0].to_payload()
    assert "owner_ciks" not in observed[0].to_payload()


def test_missing_and_unparseable_parent_are_counted_not_dropped() -> None:
    from research.insider_buying.ib1c_all_parent_projection_stream import (
        build_all_parent_projection_receipt,
    )

    manifest = _manifest()
    observed = []
    receipt = build_all_parent_projection_receipt(
        manifest, _inputs(manifest, missing=2, malformed=5), on_row=observed.append
    )
    assert (receipt.expected_count, receipt.accounted_count,
            receipt.projected_count, receipt.refused_count) == (6, 6, 4, 2)
    assert receipt.all_projected is False
    assert receipt.refusal_counts == (("MISSING_RAW", 1), ("PROJECTION_REFUSED", 1))
    assert [row.status for row in observed] == [
        "PROJECTED", "PROJECTED", "MISSING_RAW", "PROJECTED",
        "PROJECTED", "PROJECTION_REFUSED",
    ]
    assert receipt.refusal_examples == (
        (observed[2].accession_number, "MISSING_RAW"),
        (observed[5].accession_number, "PROJECTION_REFUSED"),
    )
    assert observed[2].raw_parent_sha256 is None
    assert observed[5].raw_parent_sha256 is not None
    assert observed[5].projection_sha256 is None
    receipt.verify_digest()


@pytest.mark.parametrize("shape", ("short", "extra", "out_of_order"))
def test_incomplete_or_misaligned_stream_emits_no_receipt(shape: str) -> None:
    from research.insider_buying.ib1c_all_parent_projection_stream import (
        AllParentProjectionError,
        RawParentProjectionInput,
        build_all_parent_projection_receipt,
    )

    manifest = _manifest()
    supplied = list(_inputs(manifest))
    if shape == "short":
        supplied.pop()
    elif shape == "extra":
        supplied.append(RawParentProjectionInput("0000123456-23-999999", None))
    else:
        supplied[2], supplied[3] = supplied[3], supplied[2]
    with pytest.raises(AllParentProjectionError, match="missing|extra|order"):
        build_all_parent_projection_receipt(manifest, supplied)


def test_oversize_and_wrong_type_are_bounded_refusals() -> None:
    from research.insider_buying.ib1c_all_parent_projection_stream import (
        MAX_PARENT_BYTES,
        RawParentProjectionInput,
        build_all_parent_projection_receipt,
    )

    manifest = _manifest()
    supplied = list(_inputs(manifest))
    supplied[0] = RawParentProjectionInput(supplied[0].accession_number, b"x" * (MAX_PARENT_BYTES + 1))
    supplied[1] = RawParentProjectionInput(supplied[1].accession_number, "not bytes")
    observed = []
    receipt = build_all_parent_projection_receipt(manifest, supplied, on_row=observed.append)
    assert receipt.refused_count == 2
    assert [row.status for row in observed[:2]] == ["UNBOUNDED_RAW", "MALFORMED_RAW"]
    assert observed[0].raw_parent_sha256 is None
    assert observed[1].raw_parent_sha256 is None


def test_ordered_owners_and_raw_acceptance_change_projection_digest() -> None:
    from research.insider_buying.ib1c_all_parent_projection_stream import (
        RawParentProjectionInput,
        build_all_parent_projection_receipt,
    )

    manifest = _manifest()
    locator = manifest.quarters[0].locators[0]

    def run(owners, *, accepted_hour="10"):
        supplied = list(_inputs(manifest))
        raw = _parent(locator, owners=owners)
        raw = raw.replace(b"<ACCEPTANCE-DATETIME>20221013101112",
                          ("<ACCEPTANCE-DATETIME>20221013"
                           f"{accepted_hour}1112").encode("ascii"))
        supplied[0] = RawParentProjectionInput(
            locator.accession_number, raw
        )
        rows = []
        receipt = build_all_parent_projection_receipt(manifest, supplied, on_row=rows.append)
        return receipt, rows[0]

    left, left_row = run(("0000876543", "0000765432"))
    right, right_row = run(("0000765432", "0000876543"))
    assert left.all_projected and right.all_projected
    assert left_row.ordered_owner_ciks_sha256 != right_row.ordered_owner_ciks_sha256
    assert left.row_inventory_sha256 != right.row_inventory_sha256
    later, later_row = run(("0000876543", "0000765432"), accepted_hour="11")
    assert later.all_projected
    assert left_row.accepted_at_raw_sha256 != later_row.accepted_at_raw_sha256
    assert left.row_inventory_sha256 != later.row_inventory_sha256


def test_mutated_manifest_or_callback_failure_has_no_receipt() -> None:
    from research.insider_buying.ib1c_all_parent_projection_stream import (
        AllParentProjectionError,
        build_all_parent_projection_receipt,
    )

    manifest = _manifest()
    object.__setattr__(manifest.quarters[0].locators[0], "archive_path", "changed")
    with pytest.raises(AllParentProjectionError, match="locator manifest"):
        build_all_parent_projection_receipt(manifest, ())

    manifest = _manifest()

    def fail(_row):
        raise RuntimeError("caller failed")

    with pytest.raises(AllParentProjectionError, match="row observer"):
        build_all_parent_projection_receipt(manifest, _inputs(manifest), on_row=fail)


def test_receipt_mutation_refuses() -> None:
    from research.insider_buying.ib1c_all_parent_projection_stream import (
        AllParentProjectionError,
        build_all_parent_projection_receipt,
    )

    manifest = _manifest()
    receipt = build_all_parent_projection_receipt(manifest, _inputs(manifest))
    object.__setattr__(receipt, "projected_count", 5)
    with pytest.raises(AllParentProjectionError, match="receipt"):
        receipt.verify_digest()


def test_unhashable_mutated_row_period_refuses_with_contract_error() -> None:
    from research.insider_buying.ib1c_all_parent_projection_stream import (
        AllParentProjectionError,
        build_all_parent_projection_receipt,
    )

    manifest = _manifest()
    rows = []
    build_all_parent_projection_receipt(manifest, _inputs(manifest), on_row=rows.append)
    object.__setattr__(rows[0], "period", [])
    with pytest.raises(AllParentProjectionError, match="projection row"):
        rows[0].to_payload()


def test_unhashable_mutated_refusal_status_refuses_with_contract_error() -> None:
    from research.insider_buying.ib1c_all_parent_projection_stream import (
        AllParentProjectionError,
        build_all_parent_projection_receipt,
    )

    manifest = _manifest()
    receipt = build_all_parent_projection_receipt(
        manifest, _inputs(manifest, missing=2)
    )

    class EqualButUnhashable:
        __hash__ = None

        def __eq__(self, other):
            return other == "MISSING_RAW"

    object.__setattr__(receipt, "refusal_counts", ((EqualButUnhashable(), 1),))
    with pytest.raises(AllParentProjectionError, match="receipt"):
        receipt.verify_digest()
