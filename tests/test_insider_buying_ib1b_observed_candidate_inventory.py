"""Synthetic, zero-I/O checks of the noncanonical IB-1B observed inventory."""

from __future__ import annotations

from dataclasses import replace

import pytest

from data.hashing import hash_payload
from research.insider_buying.sec_bulk_parsed_snapshot import (
    LoadedSecBulkParsedSnapshot,
    ParsedSecBulkRow,
    ParsedSecBulkTableIdentity,
    SecBulkParsedSnapshotIdentity,
    _build_accessions,
    _source_row_id,
)
from research.insider_buying.sec_bulk_snapshot import ALLOWED_SEC_TABLES
from research.insider_buying.sec_ib1b_82q_schema_profile import (
    build_retained_82q_schema_profile_candidate,
)
from research.insider_buying.sec_ib1b_pilot_profile import approved_ib1b_schema_profile


_RAW_LINEAGE = "b" * 64
_ARCHIVE_SHA = "c" * 64
_MEMBER_SHA = "d" * 64
_COMMIT = "e" * 40


def _loaded(
    specs: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...],
    *,
    pilot_profile: bool = False,
    period: tuple[int, int] = (2022, 4),
) -> LoadedSecBulkParsedSnapshot:
    """(accession, form, nonderivative codes, derivative codes)."""
    profile = (
        approved_ib1b_schema_profile()
        if pilot_profile else build_retained_82q_schema_profile_candidate()
    )
    year, quarter = period
    raw_id = f"sec-insider-bulk-{year:04d}q{quarter}-" + "a" * 16
    per_table: dict[str, list[ParsedSecBulkRow]] = {name: [] for name in ALLOWED_SEC_TABLES}

    def append(table: str, accession: str, fields: dict[str, str]) -> None:
        variant = profile.variant_for(table, year, quarter)
        ordinal = len(per_table[table]) + 1
        values = tuple(fields.get(header, "") for header in variant.headers)
        source_key = tuple(fields.get(header, "") for header in variant.source_row_key_headers)
        per_table[table].append(
            ParsedSecBulkRow(
                table_name=table,
                schema_id=variant.schema_id,
                source_record_ordinal=ordinal,
                accession_number=accession,
                values=values,
                source_row_key=source_key,
                row_id=_source_row_id(
                    raw_snapshot_id=raw_id,
                    raw_lineage_hash=_RAW_LINEAGE,
                    raw_archive_sha256=_ARCHIVE_SHA,
                    table_name=table,
                    raw_member_sha256=_MEMBER_SHA,
                    source_record_ordinal=ordinal,
                    values=values,
                    source_row_key=source_key,
                ),
            )
        )

    for accession, form, nond_codes, deriv_codes in specs:
        append("SUBMISSION.tsv", accession, {
            "ACCESSION_NUMBER": accession,
            "DOCUMENT_TYPE": form,
            "FILING_DATE": f"13-OCT-{year}",
            "PERIOD_OF_REPORT": f"12-OCT-{year}",
            "ISSUERCIK": "0000123456",
            "ISSUERNAME": "Invented issuer",
            "ISSUERTRADINGSYMBOL": "SYN",
        })
        append("REPORTINGOWNER.tsv", accession, {
            "ACCESSION_NUMBER": accession,
            "RPTOWNERCIK": "0000654321",
        })
        for number, code in enumerate(nond_codes, 1):
            append("NONDERIV_TRANS.tsv", accession, {
                "ACCESSION_NUMBER": accession,
                "NONDERIV_TRANS_SK": str(number),
                "TRANS_CODE": code,
                "TRANS_ACQUIRED_DISP_CD": "D",
            })
        for number, code in enumerate(deriv_codes, 1):
            append("DERIV_TRANS.tsv", accession, {
                "ACCESSION_NUMBER": accession,
                "DERIV_TRANS_SK": str(number),
                "TRANS_CODE": code,
            })

    tables = tuple(
        ParsedSecBulkTableIdentity(
            table_name=table,
            schema_id=(variant := profile.variant_for(table, year, quarter)).schema_id,
            headers=variant.headers,
            source_row_key_headers=variant.source_row_key_headers,
            header_hash=hash_payload(list(variant.headers)),
            raw_member_sha256=_MEMBER_SHA,
            raw_member_size_bytes=1,
            row_count=len(per_table[table]),
            row_ids_hash=hash_payload([row.row_id for row in per_table[table]]),
        )
        for table in ALLOWED_SEC_TABLES
    )
    rows = tuple(row for table in ALLOWED_SEC_TABLES for row in per_table[table])
    accessions = _build_accessions(rows, tables)
    provisional = SecBulkParsedSnapshotIdentity(
        year=year,
        quarter=quarter,
        parser_git_commit=_COMMIT,
        raw_snapshot_id=raw_id,
        raw_lineage_hash=_RAW_LINEAGE,
        raw_archive_sha256=_ARCHIVE_SHA,
        raw_manifest_sha256="f" * 64,
        schema_profile=profile,
        schema_profile_hash=hash_payload(profile.to_payload()),
        absent_tables=(),
        tables=tables,
        artifacts=(),
        lineage_hash="",
        snapshot_id="",
    )
    lineage = hash_payload(provisional.lineage_payload())
    identity = replace(
        provisional, lineage_hash=lineage,
        snapshot_id=f"sec-insider-parsed-{year:04d}q{quarter}-{lineage[:16]}",
    )
    return LoadedSecBulkParsedSnapshot(identity, rows, accessions)


def _spec(n: int, form: str, nond: tuple[str, ...], deriv: tuple[str, ...] = ()):
    return (f"0000123456-22-{n:06d}", form, nond, deriv)


def _relineage(identity: SecBulkParsedSnapshotIdentity) -> SecBulkParsedSnapshotIdentity:
    provisional = replace(identity, lineage_hash="", snapshot_id="")
    lineage = hash_payload(provisional.lineage_payload())
    return replace(
        provisional,
        lineage_hash=lineage,
        snapshot_id=f"sec-insider-parsed-{identity.year:04d}q{identity.quarter}-{lineage[:16]}",
    )


def test_observed_p_priority_and_full_form4_denominator() -> None:
    from research.insider_buying.ib1b_observed_candidate_inventory import (
        build_ib1b_observed_candidate_inventory,
    )

    loaded = _loaded((
        _spec(1, "4", ("S", "P")),
        _spec(2, "4/A", ("S",)),
        _spec(3, "4", ()),
        _spec(4, "4", (), ("P",)),
        _spec(5, "4", ("",)),
        _spec(6, "4", ("S",)),
        _spec(7, "4", ("p",)),
        _spec(8, "3", ("P",)),
    ))
    inventory = build_ib1b_observed_candidate_inventory(loaded)
    assert inventory.quarter == 4
    assert inventory.parsed_snapshot_id == loaded.identity.snapshot_id
    assert inventory.schema_profile_id == loaded.identity.schema_profile.profile_id
    assert inventory.schema_profile_sha256 == loaded.identity.schema_profile_hash
    assert len(inventory.records) == 7  # Form 3 is outside the denominator.
    assert inventory.form4_count == 6
    assert inventory.form4a_count == 1
    by_accession = {item.accession_number: item for item in inventory.records}
    assert [item.accession_number for item in inventory.records] == sorted(by_accession)
    assert all(item.source_row_ids for item in inventory.records)
    assert all(item.submission_row_id for item in inventory.records)
    assert by_accession[_spec(1, "4", ())[0]].selection_reasons == ("OBSERVED_NONDERIV_P",)
    assert by_accession[_spec(2, "4/A", ())[0]].selection_reasons == ("FORM4_AMENDMENT",)
    assert by_accession[_spec(3, "4", ())[0]].nonselection_reason == "NO_TRANSACTION_ROWS"
    assert by_accession[_spec(4, "4", ())[0]].nonselection_reason == "DERIVATIVE_ONLY"
    assert by_accession[_spec(5, "4", ())[0]].selection_reasons == ("AMBIGUOUS_TRANSACTION_CODE",)
    assert by_accession[_spec(6, "4", ())[0]].nonselection_reason == "NO_OBSERVED_NONDERIV_P"
    assert not by_accession[_spec(6, "4", ())[0]].selected_for_retrieval
    assert by_accession[_spec(7, "4", ())[0]].selected_for_retrieval
    assert inventory.selected_count == 4
    assert inventory.nonselected_count == 3
    assert inventory.canonical is False
    assert inventory.point_in_time_data is False
    assert inventory.xml_completeness_verified is False
    assert inventory.outcome_looks == 0
    assert inventory.qc_jobs == 0
    inventory.verify_digest()
    assert build_ib1b_observed_candidate_inventory(loaded).content_sha256 == inventory.content_sha256


def test_p_is_selected_even_with_disposition_d_and_other_code() -> None:
    from research.insider_buying.ib1b_observed_candidate_inventory import (
        build_ib1b_observed_candidate_inventory,
    )

    inventory = build_ib1b_observed_candidate_inventory(_loaded((_spec(1, "4", ("S", "P")),)))
    assert inventory.records[0].selected_for_retrieval
    assert len(inventory.records[0].observed_p_row_ids) == 1


def test_other_well_formed_codes_and_derivatives_do_not_become_false_p_candidates() -> None:
    from research.insider_buying.ib1b_observed_candidate_inventory import (
        build_ib1b_observed_candidate_inventory,
    )

    inventory = build_ib1b_observed_candidate_inventory(_loaded((
        _spec(1, "4", ("A", "M"), ("P",)),
        _spec(2, "4", ("S",), ("P",)),
        _spec(3, "4", ("P", "A"), ("P",)),
        _spec(4, "4/A", ("A",), ("P",)),
        _spec(5, "4", (" p ",)),
    )))
    rows = inventory.records
    assert not rows[0].selected_for_retrieval
    assert rows[0].nonselection_reason == "NO_OBSERVED_NONDERIV_P"
    assert not rows[1].selected_for_retrieval
    assert rows[1].nonselection_reason == "NO_OBSERVED_NONDERIV_P"
    assert rows[2].selection_reasons == ("OBSERVED_NONDERIV_P",)
    assert rows[3].selection_reasons == ("FORM4_AMENDMENT",)
    assert rows[4].selection_reasons == ("AMBIGUOUS_TRANSACTION_CODE",)


def test_exact_approved_pilot_profile_is_accepted_only_in_its_two_quarters() -> None:
    from research.insider_buying.ib1b_observed_candidate_inventory import (
        Ib1bObservedCandidateInventoryError,
        build_ib1b_observed_candidate_inventory,
    )

    loaded = _loaded((_spec(1, "4", ("P",)),), pilot_profile=True)
    inventory = build_ib1b_observed_candidate_inventory(loaded)
    assert inventory.schema_profile_sha256 == loaded.identity.schema_profile_hash
    assert inventory.records[0].selected_for_retrieval
    inventory.verify_digest()

    second = _loaded((_spec(2, "4/A", ("S",)),), pilot_profile=True, period=(2023, 1))
    second_inventory = build_ib1b_observed_candidate_inventory(second)
    assert second_inventory.quarter == 1
    assert second_inventory.records[0].selection_reasons == ("FORM4_AMENDMENT",)

    impossible = _relineage(replace(loaded.identity, year=2023, quarter=2))
    with pytest.raises(Ib1bObservedCandidateInventoryError, match="pilot.*outside"):
        build_ib1b_observed_candidate_inventory(replace(loaded, identity=impossible))


@pytest.mark.parametrize("mutation", ("duplicate", "missing", "orphan", "wrong_form"))
def test_forged_accession_or_row_membership_refuses(mutation: str) -> None:
    from research.insider_buying.ib1b_observed_candidate_inventory import (
        Ib1bObservedCandidateInventoryError,
        build_ib1b_observed_candidate_inventory,
    )

    loaded = _loaded((_spec(1, "4", ("P",)), _spec(2, "4", ("S",))))
    if mutation == "duplicate":
        loaded = replace(loaded, accessions=loaded.accessions + (loaded.accessions[0],))
    elif mutation == "missing":
        loaded = replace(loaded, accessions=loaded.accessions[:-1])
    elif mutation == "orphan":
        loaded = replace(
            loaded,
            rows=loaded.rows + (replace(loaded.rows[-1], accession_number="0000123456-22-999999"),),
        )
    else:
        loaded = replace(
            loaded,
            accessions=(replace(loaded.accessions[0], document_type="5"),) + loaded.accessions[1:],
        )
    with pytest.raises(Ib1bObservedCandidateInventoryError, match="REFUSED:"):
        build_ib1b_observed_candidate_inventory(loaded)


def test_unknown_form_and_drifted_header_refuse() -> None:
    from research.insider_buying.ib1b_observed_candidate_inventory import (
        Ib1bObservedCandidateInventoryError,
        build_ib1b_observed_candidate_inventory,
    )

    loaded = _loaded((_spec(1, "6", ("P",)),))
    with pytest.raises(Ib1bObservedCandidateInventoryError, match="form"):
        build_ib1b_observed_candidate_inventory(loaded)

    loaded = _loaded((_spec(1, "4", ("P",)),))
    changed_table = replace(loaded.identity.tables[2], headers=("ACCESSION_NUMBER", "TRANS_CODE"))
    changed_identity = replace(loaded.identity, tables=(
        *loaded.identity.tables[:2], changed_table, *loaded.identity.tables[3:],
    ))
    with pytest.raises(Ib1bObservedCandidateInventoryError, match="REFUSED:"):
        build_ib1b_observed_candidate_inventory(replace(loaded, identity=changed_identity))


@pytest.mark.parametrize("field,value", (
    ("absent_tables", ("UNEXPECTED.tsv",)),
    ("absent_tables", ("DERIV_TRANS.tsv", "DERIV_TRANS.tsv")),
    ("raw_snapshot_id", "sec-insider-bulk-2022q4-xxxxxxxxxxxxxxxx"),
    ("parser_git_commit", "not-a-commit"),
))
def test_claimed_snapshot_lineage_and_inventory_must_be_canonical(field: str, value: object) -> None:
    from research.insider_buying.ib1b_observed_candidate_inventory import (
        Ib1bObservedCandidateInventoryError,
        build_ib1b_observed_candidate_inventory,
    )

    loaded = _loaded((_spec(1, "4", ("P",)),))
    with pytest.raises(Ib1bObservedCandidateInventoryError, match="REFUSED:"):
        build_ib1b_observed_candidate_inventory(
            replace(loaded, identity=_relineage(replace(loaded.identity, **{field: value})))
        )


def test_content_digest_detects_later_mutation_and_bounded_quarter(monkeypatch: pytest.MonkeyPatch) -> None:
    from research.insider_buying import ib1b_observed_candidate_inventory as inventory_module

    loaded = _loaded((_spec(1, "4", ("P",)), _spec(2, "4", ("S",))))
    inventory = inventory_module.build_ib1b_observed_candidate_inventory(loaded)
    tampered = replace(inventory, records=(replace(inventory.records[0], selected_for_retrieval=False),) + inventory.records[1:])
    with pytest.raises(inventory_module.Ib1bObservedCandidateInventoryError, match="digest"):
        tampered.verify_digest()

    monkeypatch.setattr(inventory_module, "MAX_ACCESSIONS_PER_QUARTER", 1)
    with pytest.raises(inventory_module.Ib1bObservedCandidateInventoryError, match="bound"):
        inventory_module.build_ib1b_observed_candidate_inventory(loaded)
