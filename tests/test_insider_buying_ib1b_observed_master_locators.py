"""Synthetic, zero-I/O checks of the two-quarter observed-P master locators."""

from __future__ import annotations

from dataclasses import replace

import pytest

from data.hashing import hash_payload
from research.insider_buying.ib1b_observed_candidate_inventory import (
    build_ib1b_observed_candidate_inventory,
)
from research.insider_buying.sec_bulk_parsed_snapshot import (
    _build_accessions,
    _source_row_id,
)
from research.insider_buying.sec_quarter_master_index import parse_sec_quarter_master_index
from test_insider_buying_ib1b_observed_candidate_inventory import _loaded


_MASTER_HEADER = (
    b"Description: Master Index of EDGAR Dissemination Feed\n"
    b"Last Data Received: March 31, 2023\n"
    b"Comments: webmaster@sec.gov\n\n"
    b"CIK|Company Name|Form Type|Date Filed|Filename\n"
    b"--------------------------------------------------------------------------------\n"
)


def _accession(year: int, ordinal: int) -> str:
    return f"0000123456-{year % 100:02d}-{ordinal:06d}"


def _master_row(
    accession: str,
    form: str,
    filing_date: str,
    *,
    archive_cik: str = "123456",
) -> bytes:
    return (
        f"{archive_cik}|Invented issuer|{form}|{filing_date}|"
        f"edgar/data/{archive_cik}/{accession}.txt\n"
    ).encode("ascii")


def _loaded_quarter(year: int, quarter: int, specs):
    loaded = _loaded(specs, period=(year, quarter))
    # The existing synthetic IB-1B fixture uses October for every period.
    # Rebind all submission dates, row IDs, table IDs, and snapshot lineage
    # to an exact Q1 source rather than pretending Q4 dates belong in Q1.
    if (year, quarter) == (2022, 4):
        return loaded
    assert (year, quarter) == (2023, 1)
    table = next(t for t in loaded.identity.tables if t.table_name == "SUBMISSION.tsv")
    date_idx = table.headers.index("FILING_DATE")
    period_idx = table.headers.index("PERIOD_OF_REPORT")
    rows = []
    for row in loaded.rows:
        if row.table_name != "SUBMISSION.tsv":
            rows.append(row)
            continue
        values = list(row.values)
        values[date_idx] = "13-JAN-2023"
        values[period_idx] = "12-JAN-2023"
        values = tuple(values)
        rows.append(replace(
            row,
            values=values,
            row_id=_source_row_id(
                raw_snapshot_id=loaded.identity.raw_snapshot_id,
                raw_lineage_hash=loaded.identity.raw_lineage_hash,
                raw_archive_sha256=loaded.identity.raw_archive_sha256,
                table_name=row.table_name,
                raw_member_sha256=table.raw_member_sha256,
                source_record_ordinal=row.source_record_ordinal,
                values=values,
                source_row_key=row.source_row_key,
            ),
        ))
    rows = tuple(rows)
    tables = tuple(
        replace(table, row_ids_hash=hash_payload([
            row.row_id for row in rows if row.table_name == "SUBMISSION.tsv"
        ])) if table.table_name == "SUBMISSION.tsv" else table
        for table in loaded.identity.tables
    )
    identity = replace(loaded.identity, tables=tables, lineage_hash="", snapshot_id="")
    lineage = hash_payload(identity.lineage_payload())
    identity = replace(
        identity,
        lineage_hash=lineage,
        snapshot_id=f"sec-insider-parsed-{year:04d}q{quarter}-{lineage[:16]}",
    )
    return replace(loaded, identity=identity, rows=rows, accessions=_build_accessions(rows, tables))


def _inputs(*, first_master: bytes | None = None, second_master: bytes | None = None):
    from research.insider_buying.ib1b_observed_master_locators import (
        ObservedMasterLocatorQuarterInput,
    )

    first = _loaded_quarter(2022, 4, (
        (_accession(2022, 1), "4", ("P",), ()),
        (_accession(2022, 2), "4/A", ("S",), ()),
        (_accession(2022, 3), "4", ("S",), ()),
        (_accession(2022, 4), "4", ("p",), ()),
        (_accession(2022, 5), "3", ("P",), ()),
    ))
    second = _loaded_quarter(2023, 1, (
        (_accession(2023, 1), "4", ("P",), ()),
        (_accession(2023, 2), "4", ("S",), ()),
    ))
    if first_master is None:
        first_master = b"".join((
            _master_row(_accession(2022, 1), "4", "2022-10-13", archive_cik="987654"),
            _master_row(_accession(2022, 2), "4/A", "2022-10-13"),
            _master_row(_accession(2022, 3), "4", "2022-10-13"),
            _master_row(_accession(2022, 4), "4", "2022-10-13"),
        ))
    if second_master is None:
        second_master = b"".join((
            _master_row(_accession(2023, 1), "4", "2023-01-13"),
            _master_row(_accession(2023, 2), "4", "2023-01-13"),
        ))
    return (
        ObservedMasterLocatorQuarterInput(
            candidates=build_ib1b_observed_candidate_inventory(first),
            parsed_snapshot=first,
            master_index=parse_sec_quarter_master_index(
                _MASTER_HEADER + first_master, year=2022, quarter=4
            ),
        ),
        ObservedMasterLocatorQuarterInput(
            candidates=build_ib1b_observed_candidate_inventory(second),
            parsed_snapshot=second,
            master_index=parse_sec_quarter_master_index(
                _MASTER_HEADER + second_master, year=2023, quarter=1
            ),
        ),
    )


def test_two_quarter_manifest_retains_denominator_and_selected_paths_only() -> None:
    from research.insider_buying.ib1b_observed_master_locators import (
        build_ib1b_observed_master_locator_manifest,
    )

    inputs = _inputs()
    manifest = build_ib1b_observed_master_locator_manifest(iter(inputs))
    manifest.verify_digest()
    assert tuple(item.period for item in manifest.quarters) == ("2022Q4", "2023Q1")
    assert (manifest.form4_count, manifest.form4a_count) == (5, 1)
    assert (manifest.selected_count, manifest.nonselected_count) == (4, 2)
    assert manifest.ambiguous_code_quarantine_count == 1
    first = manifest.quarters[0]
    assert first.candidate_content_sha256 == inputs[0].candidates.content_sha256
    assert first.master_source_sha256 == inputs[0].master_index.source_sha256
    assert first.master_receipt_sha256 == inputs[0].master_index.receipt_sha256
    assert [row.accession_number for row in first.locators] == [
        _accession(2022, 1), _accession(2022, 2), _accession(2022, 4)
    ]
    assert first.locators[0].archive_path == (
        f"edgar/data/987654/{_accession(2022, 1)}.txt"
    )  # Sole indexed path CIK is not rewritten to the issuer CIK.
    assert first.locators[0].issuer_cik == "0000123456"
    assert first.locators[0].submission_row_id
    assert first.locators[0].observed_p_row_ids_sha256
    assert first.locators[1].selection_reasons == ("FORM4_AMENDMENT",)
    assert first.locators[2].selection_reasons == ("AMBIGUOUS_TRANSACTION_CODE",)
    assert first.locators[2].ambiguous_code_quarantine
    assert not first.locators[0].ambiguous_code_quarantine
    assert manifest.canonical is False
    assert manifest.point_in_time_data is False
    assert manifest.xml_completeness_verified is False
    assert manifest.outcome_looks == 0
    assert manifest.qc_jobs == 0


def test_unselected_master_path_is_not_required_but_selected_is() -> None:
    from research.insider_buying.ib1b_observed_master_locators import (
        ObservedMasterLocatorError,
        build_ib1b_observed_master_locator_manifest,
    )

    selected_only = b"".join((
        _master_row(_accession(2022, 1), "4", "2022-10-13"),
        _master_row(_accession(2022, 2), "4/A", "2022-10-13"),
        _master_row(_accession(2022, 4), "4", "2022-10-13"),
    ))
    inputs = _inputs(first_master=selected_only)
    assert build_ib1b_observed_master_locator_manifest(inputs).nonselected_count == 2
    missing_selected = selected_only.replace(
        _master_row(_accession(2022, 2), "4/A", "2022-10-13"), b""
    )
    with pytest.raises(ObservedMasterLocatorError, match="missing requested"):
        build_ib1b_observed_master_locator_manifest(_inputs(first_master=missing_selected))


@pytest.mark.parametrize("alias_kind, message", (
    ("no_issuer", "issuer CIK"),
    ("two_issuer", "multiple index archive paths"),
    ("wrong_form", "contradicts requested form or date"),
    ("wrong_date", "contradicts requested form or date"),
))
def test_alias_ambiguity_or_identity_mismatch_refuses(alias_kind: str, message: str) -> None:
    from research.insider_buying.ib1b_observed_master_locators import (
        ObservedMasterLocatorError,
        build_ib1b_observed_master_locator_manifest,
    )

    accession = _accession(2022, 1)
    main = _master_row(accession, "4", "2022-10-13", archive_cik="987654")
    if alias_kind == "no_issuer":
        alias = _master_row(accession, "4", "2022-10-13", archive_cik="876543")
    elif alias_kind == "two_issuer":
        main = _master_row(accession, "4", "2022-10-13", archive_cik="123456")
        alias = _master_row(accession, "4", "2022-10-13", archive_cik="0123456")
    elif alias_kind == "wrong_form":
        alias = _master_row(accession, "4/A", "2022-10-13", archive_cik="876543")
    else:
        alias = _master_row(accession, "4", "2022-10-14", archive_cik="876543")
    body = b"".join((
        main, alias,
        _master_row(_accession(2022, 2), "4/A", "2022-10-13"),
        _master_row(_accession(2022, 4), "4", "2022-10-13"),
    ))
    with pytest.raises(ObservedMasterLocatorError, match=message):
        build_ib1b_observed_master_locator_manifest(_inputs(first_master=body))


def test_one_unambiguous_issuer_alias_is_selected_without_dropping_other_index_row() -> None:
    from research.insider_buying.ib1b_observed_master_locators import (
        build_ib1b_observed_master_locator_manifest,
    )

    accession = _accession(2022, 1)
    body = b"".join((
        _master_row(accession, "4", "2022-10-13", archive_cik="987654"),
        _master_row(accession, "4", "2022-10-13", archive_cik="123456"),
        _master_row(_accession(2022, 2), "4/A", "2022-10-13"),
        _master_row(_accession(2022, 4), "4", "2022-10-13"),
    ))
    manifest = build_ib1b_observed_master_locator_manifest(_inputs(first_master=body))
    assert manifest.quarters[0].locators[0].archive_path == f"edgar/data/123456/{accession}.txt"
    assert manifest.quarters[0].master_index_form4_row_count == 4


def test_rebind_of_inventory_loaded_rows_master_or_result_refuses() -> None:
    from research.insider_buying.ib1b_observed_master_locators import (
        ObservedMasterLocatorError,
        build_ib1b_observed_master_locator_manifest,
    )

    first, second = _inputs()
    object.__setattr__(first.candidates.records[0], "selected_for_retrieval", False)
    with pytest.raises(ObservedMasterLocatorError, match="candidate"):
        build_ib1b_observed_master_locator_manifest((first, second))

    first, second = _inputs()
    submission = next(row for row in first.parsed_snapshot.rows if row.table_name == "SUBMISSION.tsv")
    object.__setattr__(submission, "values", submission.values[:-1] + ("changed",))
    with pytest.raises(ObservedMasterLocatorError, match="snapshot"):
        build_ib1b_observed_master_locator_manifest((first, second))

    first, second = _inputs()
    object.__setattr__(first.master_index.rows[0], "archive_path", (
        f"edgar/data/999999/{_accession(2022, 1)}.txt"
    ))
    with pytest.raises(ObservedMasterLocatorError, match="master"):
        build_ib1b_observed_master_locator_manifest((first, second))

    manifest = build_ib1b_observed_master_locator_manifest(_inputs())
    object.__setattr__(manifest.quarters[0].locators[0], "filing_date", "2022-10-14")
    with pytest.raises(ObservedMasterLocatorError, match="digest"):
        manifest.verify_digest()

    manifest = build_ib1b_observed_master_locator_manifest(_inputs())
    object.__setattr__(manifest.quarters[0], "parsed_lineage_hash", 42)
    with pytest.raises(ObservedMasterLocatorError, match="digest"):
        manifest.verify_digest()


@pytest.mark.parametrize("shape", ("reverse", "duplicate", "missing", "extra"))
def test_exact_two_ordered_quarters_required(shape: str) -> None:
    from research.insider_buying.ib1b_observed_master_locators import (
        ObservedMasterLocatorError,
        build_ib1b_observed_master_locator_manifest,
    )

    first, second = _inputs()
    quarters = {
        "reverse": (second, first),
        "duplicate": (first, first),
        "missing": (first,),
        "extra": (first, second, second),
    }[shape]
    with pytest.raises(ObservedMasterLocatorError, match="quarter"):
        build_ib1b_observed_master_locator_manifest(quarters)


def test_no_selected_candidates_returns_empty_but_bound_manifest() -> None:
    from research.insider_buying.ib1b_observed_master_locators import (
        ObservedMasterLocatorQuarterInput,
        build_ib1b_observed_master_locator_manifest,
    )

    inputs = list(_inputs())
    first = _loaded_quarter(2022, 4, ((_accession(2022, 9), "4", ("S",), ()),))
    second = _loaded_quarter(2023, 1, ((_accession(2023, 9), "4", ("S",), ()),))
    for index, loaded in enumerate((first, second)):
        year, quarter = (2022, 4) if index == 0 else (2023, 1)
        filing = "2022-10-13" if index == 0 else "2023-01-13"
        inputs[index] = ObservedMasterLocatorQuarterInput(
            candidates=build_ib1b_observed_candidate_inventory(loaded),
            parsed_snapshot=loaded,
            master_index=parse_sec_quarter_master_index(
                _MASTER_HEADER + _master_row(_accession(year, 9), "4", filing),
                year=year,
                quarter=quarter,
            ),
        )
    manifest = build_ib1b_observed_master_locator_manifest(inputs)
    assert manifest.selected_count == 0
    assert manifest.nonselected_count == 2
    assert manifest.quarters[0].locators == ()
    assert manifest.quarters[1].locators == ()
    manifest.verify_digest()
