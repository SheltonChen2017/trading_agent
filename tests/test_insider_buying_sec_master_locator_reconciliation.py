"""Synthetic, zero-I/O checks for 82-quarter master locator reconciliation."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from data.hashing import hash_payload
from research.insider_buying.sec_bulk_parsed_snapshot import (
    LoadedSecBulkParsedSnapshot,
    ParsedSecBulkAccession,
    ParsedSecBulkRow,
    ParsedSecBulkTableIdentity,
    SecBulkParsedSnapshotIdentity,
    SecTsvSchemaProfile,
    SecTsvSchemaVariant,
    _source_row_id,
)
from research.insider_buying.sec_corpus_scale_preflight import (
    SecQuarterScaleDescriptor,
    build_sec_corpus_scale_preflight,
)
from research.insider_buying.sec_master_locator_reconciliation import (
    SecMasterLocatorQuarterInput,
    SecMasterLocatorReconciliationError,
    reconcile_sec_master_locators,
)
from research.insider_buying.sec_quarter_master_index import (
    parse_sec_quarter_master_index,
)
from research.insider_buying.sec_zip_corpus_census import (
    SecZipCensusQuarter,
    SecZipCorpusCensus,
    _SYNTHETIC_CONSTRUCTION_TOKEN,
    _expected_url,
)


_PERIODS = tuple(
    f"{year}Q{quarter}"
    for year in range(2006, 2027)
    for quarter in range(1, 5)
    if (year, quarter) <= (2026, 2)
)
_HEADERS = (
    "ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT", "DOCUMENT_TYPE",
    "ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL",
)
_MASTER_HEADER = (
    b"Description: Master Index of EDGAR Dissemination Feed\n"
    b"Last Data Received: March 31, 2023\n"
    b"Comments: webmaster@sec.gov\n\n"
    b"CIK|Company Name|Form Type|Date Filed|Filename\n"
    b"--------------------------------------------------------------------------------\n"
)
_PROFILE = SecTsvSchemaProfile(
    profile_id="synthetic-locator-profile",
    variants=(
        SecTsvSchemaVariant("submission", "SUBMISSION.tsv", _HEADERS, (),
                            2006, 1, 2026, 2),
        SecTsvSchemaVariant("owner", "REPORTINGOWNER.tsv",
                            ("ACCESSION_NUMBER", "RPTOWNERCIK"), (),
                            2006, 1, 2026, 2),
        SecTsvSchemaVariant("transaction", "NONDERIV_TRANS.tsv",
                            ("ACCESSION_NUMBER", "TRANS_SK"), ("TRANS_SK",),
                            2006, 1, 2026, 2),
    ),
)


def _accession(period: str, sequence: int = 1) -> str:
    return f"0000123456-{int(period[:4]) % 100:02d}-{int(period[-1]) * 100 + sequence:06d}"


def _filing(period: str) -> str:
    month = (int(period[-1]) - 1) * 3 + 1
    return date(int(period[:4]), month, 15).isoformat()


def _census() -> SecZipCorpusCensus:
    quarters = tuple(SecZipCensusQuarter(
        period=period, zip_sha256="a" * 64, zip_size_bytes=1000,
        source_url_from_retained_manifest=_expected_url(period),
        local_last_write_utc_unverified="2026-09-24T22:52:19.7647157Z",
        submission_member_sha256="b" * 64,
        submission_member_size_bytes=100,
        submission_header_line_sha256="c" * 64,
        submission_headers=_HEADERS,
        form_counts=(0, 0, 1, 0, 0, 0),
    ) for period in _PERIODS)
    preflight = build_sec_corpus_scale_preflight(
        SecQuarterScaleDescriptor(
            period=item.period, zip_sha256=item.zip_sha256,
            zip_size_bytes=item.zip_size_bytes,
            submission_accession_count=item.submission_accessions,
            form4_accession_count=item.form4_accessions,
            form4a_accession_count=item.form4a_accessions,
            multi_owner_target_count=None,
        ) for item in quarters
    )
    return SecZipCorpusCensus(
        scope="synthetic_test_census", source_manifest_sha256="d" * 64,
        source_manifest_size_bytes=100, quarters=quarters,
        existing_zip_bytes=preflight.existing_zip_bytes,
        submission_accessions=preflight.declared_submission_accessions,
        form4_accessions=preflight.declared_form4_accessions,
        form4a_accessions=preflight.declared_form4a_accessions,
        target_accessions=preflight.declared_target_accessions,
        multi_owner_unknown_quarters=preflight.multi_owner_unknown_quarters,
        planned_distinct_artifacts_without_cache=(
            preflight.planned_distinct_artifacts_without_cache
        ),
        maximum_attempts_at_three_per_artifact=(
            preflight.maximum_attempts_at_three_per_artifact
        ),
        ideal_minimum_dispatch_span_ms=preflight.ideal_minimum_dispatch_span_ms,
        successful_raw_parent_cap_bytes=preflight.successful_raw_parent_cap_bytes,
        existing_zip_plus_successful_parent_cap_bytes=(
            preflight.existing_zip_plus_successful_parent_cap_bytes
        ),
        acceptance_metadata_records_required_without_cache=(
            preflight.declared_target_accessions
        ),
        _validated_quarters_sha256=hash_payload([
            item.to_payload() for item in quarters
        ]),
        _construction_token=_SYNTHETIC_CONSTRUCTION_TOKEN,
    )


def _snapshot(period: str, *, form: str = "4", raw_date: str | None = None,
              issuer: str = "123456") -> LoadedSecBulkParsedSnapshot:
    year, quarter = int(period[:4]), int(period[-1])
    accession, filing = _accession(period), _filing(period)
    tables = tuple(ParsedSecBulkTableIdentity(
        table_name=variant.table_name, schema_id=variant.schema_id,
        headers=variant.headers,
        source_row_key_headers=variant.source_row_key_headers,
        header_hash=hash_payload(list(variant.headers)),
        raw_member_sha256=("b" if index == 0 else "e") * 64,
        raw_member_size_bytes=100, row_count=1 if index == 0 else 0,
        row_ids_hash="f" * 64,
    ) for index, variant in enumerate(_PROFILE.variants))
    provisional = SecBulkParsedSnapshotIdentity(
        year=year, quarter=quarter, parser_git_commit="f" * 40,
        raw_snapshot_id=f"sec-insider-bulk-{year}q{quarter}-" + "1" * 16,
        raw_lineage_hash="1" * 64, raw_archive_sha256="a" * 64,
        raw_manifest_sha256="2" * 64, schema_profile=_PROFILE,
        schema_profile_hash=hash_payload(_PROFILE.to_payload()),
        absent_tables=(), tables=tables, artifacts=(), lineage_hash="",
        snapshot_id="",
    )
    lineage = hash_payload(provisional.lineage_payload())
    identity = replace(
        provisional, lineage_hash=lineage,
        snapshot_id=f"sec-insider-parsed-{year}q{quarter}-{lineage[:16]}",
    )
    values = (accession, raw_date or filing, filing, form, issuer,
              "Invented Issuer", "INVT")
    row_id = _source_row_id(
        raw_snapshot_id=identity.raw_snapshot_id,
        raw_lineage_hash=identity.raw_lineage_hash,
        raw_archive_sha256=identity.raw_archive_sha256,
        table_name="SUBMISSION.tsv", raw_member_sha256=tables[0].raw_member_sha256,
        source_record_ordinal=1, values=values, source_row_key=(),
    )
    tables = (replace(tables[0], row_ids_hash=hash_payload([row_id])), *tables[1:])
    provisional = replace(provisional, tables=tables)
    lineage = hash_payload(provisional.lineage_payload())
    identity = replace(
        provisional, lineage_hash=lineage,
        snapshot_id=f"sec-insider-parsed-{year}q{quarter}-{lineage[:16]}",
    )
    row = ParsedSecBulkRow(
        table_name="SUBMISSION.tsv", schema_id="submission",
        source_record_ordinal=1, accession_number=accession, values=values,
        source_row_key=(), row_id=row_id,
    )
    summary = ParsedSecBulkAccession(
        accession_number=accession, document_type=form,
        submission_row_id=row_id,
        table_rows=(("SUBMISSION.tsv", (row_id,)),),
    )
    return LoadedSecBulkParsedSnapshot(identity, (row,), (summary,))


def _master_row(period: str, *, sequence: int = 1, form: str = "4",
                filing: str | None = None, archive_cik: str = "123456") -> bytes:
    return (
        f"123456|Invented Issuer|{form}|{filing or _filing(period)}|"
        f"edgar/data/{archive_cik}/{_accession(period, sequence)}.txt\n"
    ).encode("ascii")


def _input(period: str, *, rows: tuple[bytes, ...] | None = None,
           snapshot: LoadedSecBulkParsedSnapshot | None = None
           ) -> SecMasterLocatorQuarterInput:
    year, quarter = int(period[:4]), int(period[-1])
    receipt = parse_sec_quarter_master_index(
        _MASTER_HEADER + b"".join(rows or (_master_row(period),)),
        year=year, quarter=quarter,
    )
    return SecMasterLocatorQuarterInput(
        period=period, parsed_snapshot=snapshot or _snapshot(period),
        master_index=receipt,
    )


def _inputs(*, replacement: SecMasterLocatorQuarterInput | None = None):
    return (
        replacement if replacement is not None and period == replacement.period
        else _input(period)
        for period in _PERIODS
    )


def test_exact_82_quarters_bind_census_and_whole_index_without_authority():
    census = _census()
    receipt = reconcile_sec_master_locators(census, _inputs())
    payload = receipt.to_payload()
    assert receipt.all_quarters_exact is True
    assert receipt.census_sha256 == census.sha256
    assert payload["counts"] == {
        "target_accessions": 82, "index_alias_rows": 0,
        "missing": 0, "extra": 0, "conflicting": 0,
    }
    assert len(receipt.locator_inventory_sha256) == 64
    assert receipt.report_sha256 == hash_payload(payload)
    assert payload["authority"] == {
        "caller_loaded_source_only": True,
        "sec_origin_authenticated": False,
        "master_index_completeness_proven": False,
        "issuer_identity_confirmed_from_master": False,
        "complete_text_coverage_verified": False,
        "acceptance_metadata_coverage_verified": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "outcome_access_authorized": False,
        "qc_job_authorized": False,
        "broker_or_trading_authorized": False,
        "research_looks": 0,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }


@pytest.mark.parametrize("case,expected", (
    ("missing", (1, 0, 0)),
    ("extra", (0, 1, 0)),
    ("conflicting_form", (0, 0, 1)),
    ("conflicting_date", (0, 0, 1)),
    ("ambiguous_alias", (0, 0, 1)),
))
def test_any_one_quarter_discrepancy_invalidates_whole_manifest(case, expected):
    period = _PERIODS[17]
    alternate = _master_row(period, sequence=2)
    date_changed = _filing(period)[:-2] + "16"
    variants = {
        "missing": (b"123456|Invented Issuer|8-K|" + _filing(period).encode()
                    + b"|edgar/data/123456/0000123456-10-000099.txt\n",),
        "extra": (_master_row(period), alternate),
        "conflicting_form": (_master_row(period, form="4/A"),),
        "conflicting_date": (_master_row(period, filing=date_changed),),
        "ambiguous_alias": (_master_row(period, archive_cik="777777"),
                            _master_row(period, archive_cik="888888")),
    }
    item = _input(period, rows=variants[case])
    receipt = reconcile_sec_master_locators(_census(), _inputs(replacement=item))
    quarter = receipt.quarters[17]
    assert (quarter.missing_count, quarter.extra_count, quarter.conflict_count) == expected
    assert receipt.all_quarters_exact is False
    assert receipt.locator_inventory_sha256 is None
    assert quarter.selected_locator_sha256 is None
    assert receipt.to_payload()["locator_inventory_sha256"] is None


def test_unique_issuer_archive_alias_is_resolved_but_both_rows_are_counted():
    period = _PERIODS[7]
    item = _input(period, rows=(
        _master_row(period, archive_cik="777777"),
        _master_row(period, archive_cik="123456"),
    ))
    receipt = reconcile_sec_master_locators(_census(), _inputs(replacement=item))
    assert receipt.all_quarters_exact is True
    assert receipt.quarters[7].index_alias_row_count == 1
    assert receipt.quarters[7].matched_count == 1


def test_single_agent_archive_path_is_not_mislabelled_issuer_confirmation():
    period = _PERIODS[8]
    item = _input(period, rows=(_master_row(period, archive_cik="777777"),))
    receipt = reconcile_sec_master_locators(_census(), _inputs(replacement=item))
    assert receipt.all_quarters_exact is True
    assert receipt.to_payload()["authority"]["issuer_identity_confirmed_from_master"] is False


@pytest.mark.parametrize("change,reason", (
    ("parsed_lineage", "parsed identity"),
    ("master_source_hash", "master-index receipt"),
    ("submission_row_hash", "SUBMISSION row lineage"),
    ("form_count", "SUBMISSION counts"),
    ("zip_hash", "ZIP census"),
))
def test_changed_digests_or_counts_refuse_without_partial_report(change, reason):
    period = _PERIODS[0]
    source = _input(period)
    census = _census()
    if change == "parsed_lineage":
        bad = replace(source.parsed_snapshot.identity, lineage_hash="0" * 64)
        source = replace(source, parsed_snapshot=replace(
            source.parsed_snapshot, identity=bad,
        ))
    elif change == "master_source_hash":
        object.__setattr__(source.master_index, "source_sha256", "0" * 64)
    elif change == "submission_row_hash":
        row = replace(source.parsed_snapshot.rows[0], row_id="0" * 64)
        source = replace(source, parsed_snapshot=replace(
            source.parsed_snapshot, rows=(row,),
        ))
    elif change == "form_count":
        old = source.parsed_snapshot.rows[0]
        values = (*old.values[:3], "4/A", *old.values[4:])
        updated = replace(old, values=values, row_id=_source_row_id(
            raw_snapshot_id=source.parsed_snapshot.identity.raw_snapshot_id,
            raw_lineage_hash=source.parsed_snapshot.identity.raw_lineage_hash,
            raw_archive_sha256=source.parsed_snapshot.identity.raw_archive_sha256,
            table_name="SUBMISSION.tsv", raw_member_sha256="b" * 64,
            source_record_ordinal=1, values=values, source_row_key=(),
        ))
        summary = replace(source.parsed_snapshot.accessions[0],
                          document_type="4/A", submission_row_id=updated.row_id,
                          table_rows=(("SUBMISSION.tsv", (updated.row_id,)),))
        source = replace(source, parsed_snapshot=replace(
            source.parsed_snapshot, rows=(updated,), accessions=(summary,),
        ))
    else:
        object.__setattr__(census.quarters[0], "zip_sha256", "0" * 64)
    with pytest.raises(SecMasterLocatorReconciliationError, match=reason):
        reconcile_sec_master_locators(census, _inputs(replacement=source))


def test_missing_extra_or_reordered_quarter_inputs_refuse():
    census = _census()
    with pytest.raises(SecMasterLocatorReconciliationError, match="incomplete"):
        reconcile_sec_master_locators(census, (_input(p) for p in _PERIODS[:-1]))
    with pytest.raises(SecMasterLocatorReconciliationError, match="extra quarter"):
        reconcile_sec_master_locators(census, (*_inputs(), _input(_PERIODS[-1])))
    items = list(_inputs())
    items[0], items[1] = items[1], items[0]
    with pytest.raises(SecMasterLocatorReconciliationError, match="out of order"):
        reconcile_sec_master_locators(census, items)


def test_rebinding_result_cannot_promote_a_partial_locator_inventory():
    period = _PERIODS[0]
    item = _input(period, rows=(_master_row(period), _master_row(period, sequence=2)))
    receipt = reconcile_sec_master_locators(_census(), _inputs(replacement=item))
    with pytest.raises(SecMasterLocatorReconciliationError, match="partially promoted"):
        replace(receipt, all_quarters_exact=True,
                locator_inventory_sha256="a" * 64)
    with pytest.raises(SecMasterLocatorReconciliationError, match="digest changed"):
        good = reconcile_sec_master_locators(_census(), _inputs())
        replace(good, locator_inventory_sha256="a" * 64)
