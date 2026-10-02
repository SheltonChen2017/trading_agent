"""Synthetic, zero-I/O tests for the complete two-quarter Form 4 locator set."""

from __future__ import annotations

from dataclasses import replace

import pytest

from data.hashing import hash_payload
from test_insider_buying_ib1b_observed_master_locators import (
    _MASTER_HEADER,
    _accession,
    _inputs,
    _master_row,
)


def _all_inputs(*, first_master: bytes | None = None, second_master: bytes | None = None):
    from research.insider_buying.ib1b_all_form4_parent_locators import (
        AllForm4ParentQuarterInput,
    )

    selected_inputs = _inputs(first_master=first_master, second_master=second_master)
    return tuple(
        AllForm4ParentQuarterInput(item.parsed_snapshot, item.master_index)
        for item in selected_inputs
    )


def test_all_form4_and_form4a_accessions_have_source_bound_paths() -> None:
    from research.insider_buying.ib1b_all_form4_parent_locators import (
        build_ib1b_all_form4_parent_locator_manifest,
    )

    first, second = _all_inputs()
    manifest = build_ib1b_all_form4_parent_locator_manifest(iter((first, second)))
    manifest.verify_digest()
    assert tuple(quarter.period for quarter in manifest.quarters) == (
        "2022Q4", "2023Q1"
    )
    assert (manifest.form4_count, manifest.form4a_count, manifest.total_accessions) == (
        5, 1, 6
    )
    assert tuple(len(quarter.locators) for quarter in manifest.quarters) == (4, 2)
    assert [row.accession_number for row in manifest.iter_locators()] == [
        *(_accession(2022, ordinal) for ordinal in (1, 2, 3, 4)),
        *(_accession(2023, ordinal) for ordinal in (1, 2)),
    ]
    first_rows = manifest.quarters[0].locators
    assert first_rows[0].archive_path == (
        f"edgar/data/987654/{_accession(2022, 1)}.txt"
    )  # A sole index-path CIK is not rewritten to the IB-1B issuer CIK.
    assert first_rows[0].issuer_cik == "0000123456"
    assert first_rows[2].archive_path == (
        f"edgar/data/123456/{_accession(2022, 3)}.txt"
    )  # Even the observed non-priority Form 4 receives a checked locator.
    assert first_rows[2].candidate_record_sha256 == hash_payload(
        _inputs()[0].candidates.records[2].to_payload()
    )
    assert first_rows[2].submission_row_id
    assert manifest.quarters[0].master_index_form4_row_count == 4
    assert manifest.canonical is False
    assert manifest.point_in_time_data is False
    assert manifest.xml_completeness_verified is False
    assert manifest.source_authenticity_verified is False
    assert manifest.outcome_looks == 0
    assert manifest.qc_jobs == 0


def test_missing_nonpriority_form4_master_path_refuses_whole_manifest() -> None:
    from research.insider_buying.ib1b_all_form4_parent_locators import (
        AllForm4ParentLocatorError,
        build_ib1b_all_form4_parent_locator_manifest,
    )

    first_body = b"".join(
        _master_row(_accession(2022, ordinal), "4/A" if ordinal == 2 else "4", "2022-10-13")
        for ordinal in (1, 2, 4)
    )
    with pytest.raises(AllForm4ParentLocatorError, match="missing requested"):
        build_ib1b_all_form4_parent_locator_manifest(
            _all_inputs(first_master=first_body)
        )


def test_extra_form4_master_path_refuses_whole_manifest() -> None:
    from research.insider_buying.ib1b_all_form4_parent_locators import (
        AllForm4ParentLocatorError,
        build_ib1b_all_form4_parent_locator_manifest,
    )

    first_body = b"".join(
        _master_row(_accession(2022, ordinal), "4/A" if ordinal == 2 else "4", "2022-10-13")
        for ordinal in (1, 2, 3, 4, 99)
    )
    with pytest.raises(AllForm4ParentLocatorError, match="extra Form 4"):
        build_ib1b_all_form4_parent_locator_manifest(
            _all_inputs(first_master=first_body)
        )


def test_nonpriority_alias_requires_one_unambiguous_issuer_path() -> None:
    from research.insider_buying.ib1b_all_form4_parent_locators import (
        AllForm4ParentLocatorError,
        build_ib1b_all_form4_parent_locator_manifest,
    )

    target = _accession(2022, 3)
    base = b"".join(
        _master_row(_accession(2022, ordinal), "4/A" if ordinal == 2 else "4", "2022-10-13")
        for ordinal in (1, 2, 4)
    )
    ambiguous = b"".join((
        base,
        _master_row(target, "4", "2022-10-13", archive_cik="987654"),
        _master_row(target, "4", "2022-10-13", archive_cik="876543"),
    ))
    with pytest.raises(AllForm4ParentLocatorError, match="issuer CIK"):
        build_ib1b_all_form4_parent_locator_manifest(
            _all_inputs(first_master=ambiguous)
        )
    resolvable = b"".join((
        base,
        _master_row(target, "4", "2022-10-13", archive_cik="987654"),
        _master_row(target, "4", "2022-10-13", archive_cik="123456"),
    ))
    manifest = build_ib1b_all_form4_parent_locator_manifest(
        _all_inputs(first_master=resolvable)
    )
    assert manifest.quarters[0].locators[2].archive_path == (
        f"edgar/data/123456/{target}.txt"
    )
    assert manifest.quarters[0].master_index_form4_row_count == 5


@pytest.mark.parametrize("shape", ("reverse", "missing", "extra"))
def test_exact_two_ordered_quarters_required(shape: str) -> None:
    from research.insider_buying.ib1b_all_form4_parent_locators import (
        AllForm4ParentLocatorError,
        build_ib1b_all_form4_parent_locator_manifest,
    )

    first, second = _all_inputs()
    items = {
        "reverse": (second, first),
        "missing": (first,),
        "extra": (first, second, second),
    }[shape]
    with pytest.raises(AllForm4ParentLocatorError, match="quarter"):
        build_ib1b_all_form4_parent_locator_manifest(items)


def test_changed_source_or_manifest_row_refuses() -> None:
    from research.insider_buying.ib1b_all_form4_parent_locators import (
        AllForm4ParentLocatorError,
        build_ib1b_all_form4_parent_locator_manifest,
    )

    first, second = _all_inputs()
    submission = next(
        row for row in first.parsed_snapshot.rows
        if row.table_name == "SUBMISSION.tsv"
    )
    object.__setattr__(submission, "values", submission.values[:-1] + ("changed",))
    with pytest.raises(AllForm4ParentLocatorError, match="parsed snapshot"):
        build_ib1b_all_form4_parent_locator_manifest((first, second))

    first, second = _all_inputs()
    object.__setattr__(first.master_index.rows[0], "archive_path", (
        f"edgar/data/999999/{_accession(2022, 1)}.txt"
    ))
    with pytest.raises(AllForm4ParentLocatorError, match="master"):
        build_ib1b_all_form4_parent_locator_manifest((first, second))

    manifest = build_ib1b_all_form4_parent_locator_manifest(_all_inputs())
    object.__setattr__(manifest.quarters[0].locators[2], "archive_path", (
        f"edgar/data/999999/{_accession(2022, 3)}.txt"
    ))
    with pytest.raises(AllForm4ParentLocatorError, match="digest"):
        manifest.verify_digest()


@pytest.mark.parametrize("field", ("accession_number", "submission_row_id"))
def test_mutated_unhashable_locator_field_refuses_with_typed_error(
    field: str,
) -> None:
    from research.insider_buying.ib1b_all_form4_parent_locators import (
        AllForm4ParentLocatorError,
        build_ib1b_all_form4_parent_locator_manifest,
    )

    manifest = build_ib1b_all_form4_parent_locator_manifest(_all_inputs())
    object.__setattr__(manifest.quarters[0].locators[0], field, [])
    with pytest.raises(AllForm4ParentLocatorError, match="locator fields are malformed"):
        manifest.verify_digest()


def test_no_form4_in_one_quarter_still_checks_full_index_equality() -> None:
    from research.insider_buying.ib1b_all_form4_parent_locators import (
        AllForm4ParentLocatorError,
        AllForm4ParentQuarterInput,
        build_ib1b_all_form4_parent_locator_manifest,
    )
    from research.insider_buying.sec_quarter_master_index import (
        parse_sec_quarter_master_index,
    )
    from test_insider_buying_ib1b_observed_master_locators import _loaded_quarter

    first, second = _all_inputs()
    empty = _loaded_quarter(
        2023, 1, ((_accession(2023, 9), "3", ("P",), ()),)
    )
    second = AllForm4ParentQuarterInput(
        parsed_snapshot=empty,
        master_index=parse_sec_quarter_master_index(
            _MASTER_HEADER + _master_row(
                _accession(2023, 9), "3", "2023-01-13"
            ),
            year=2023,
            quarter=1,
        ),
    )
    manifest = build_ib1b_all_form4_parent_locator_manifest((first, second))
    assert len(manifest.quarters[1].locators) == 0
    assert manifest.total_accessions == 4
    manifest.verify_digest()
    second_with_extra_form4 = AllForm4ParentQuarterInput(
        parsed_snapshot=empty,
        master_index=parse_sec_quarter_master_index(
            _MASTER_HEADER + _master_row(
                _accession(2023, 9), "4", "2023-01-13"
            ),
            year=2023,
            quarter=1,
        ),
    )
    with pytest.raises(AllForm4ParentLocatorError, match="absent from source"):
        build_ib1b_all_form4_parent_locator_manifest(
            (first, second_with_extra_form4)
        )


# Section 119 (Claude review): regression for IBOFF-CR01. A forged
# non-integer quarter count must refuse, not raise TypeError in sum().
def test_forged_non_integer_quarter_count_is_a_typed_refusal() -> None:
    from research.insider_buying.ib1b_all_form4_parent_locators import (
        AllForm4ParentLocatorError,
        build_ib1b_all_form4_parent_locator_manifest,
    )

    manifest = build_ib1b_all_form4_parent_locator_manifest(_all_inputs())
    object.__setattr__(manifest.quarters[0], "form4_count", "4")
    with pytest.raises(AllForm4ParentLocatorError, match="REFUSED"):
        manifest.verify_digest()
