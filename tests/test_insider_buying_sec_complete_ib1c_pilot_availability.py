"""Synthetic-only exact-16 complete-text to date-only IB-1C pilot diagnostics."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
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
from research.insider_buying.sec_complete_submission import (
    SecCompleteSubmissionProjection,
    SecCompleteSubmissionTarget,
)
from research.insider_buying import sec_complete_ib1c_pilot_availability as pilot
from research import insider_buying_sec_complete_projection_adapter as adapter


_ISSUER = "0000123456"
_OWNER = "0000002178"
_SUBMISSION_HEADERS = (
    "ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT", "DOCUMENT_TYPE",
    "ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL",
)


def _canonical(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _profile() -> SecTsvSchemaProfile:
    return SecTsvSchemaProfile(
        profile_id="synthetic-ib1b-profile",
        variants=(
            SecTsvSchemaVariant(
                "submission", "SUBMISSION.tsv", _SUBMISSION_HEADERS, (),
                2022, 4, 2023, 1,
            ),
            SecTsvSchemaVariant(
                "owner", "REPORTINGOWNER.tsv",
                ("ACCESSION_NUMBER", "RPTOWNERCIK"), (), 2022, 4, 2023, 1,
            ),
            SecTsvSchemaVariant(
                "transactions", "NONDERIV_TRANS.tsv",
                ("ACCESSION_NUMBER", "TRANS_SK"), ("TRANS_SK",),
                2022, 4, 2023, 1,
            ),
        ),
    )


def _snapshot(period: str, accessions: tuple[str, ...]) -> LoadedSecBulkParsedSnapshot:
    year, quarter = int(period[:4]), int(period[-1])
    filing_date = "2022-11-07" if quarter == 4 else "2023-02-10"
    filing_date_raw = "07-NOV-2022" if quarter == 4 else "10-FEB-2023"
    profile = _profile()
    tables = tuple(
        ParsedSecBulkTableIdentity(
            table_name=variant.table_name, schema_id=variant.schema_id,
            headers=variant.headers, source_row_key_headers=variant.source_row_key_headers,
            header_hash="a" * 64, raw_member_sha256=("b" if index == 0 else "c") * 64,
            raw_member_size_bytes=100, row_count=len(accessions) if index == 0 else 0,
            row_ids_hash="d" * 64,
        )
        for index, variant in enumerate(profile.variants)
    )
    provisional = SecBulkParsedSnapshotIdentity(
        year=year, quarter=quarter, parser_git_commit="a" * 40,
        raw_snapshot_id=f"sec-insider-bulk-{year}q{quarter}-" + "1" * 16,
        raw_lineage_hash="2" * 64, raw_archive_sha256="3" * 64,
        raw_manifest_sha256="4" * 64, schema_profile=profile,
        schema_profile_hash=hash_payload(profile.to_payload()), absent_tables=(),
        tables=tables, artifacts=(), lineage_hash="", snapshot_id="",
    )
    lineage = hash_payload(provisional.lineage_payload())
    identity = replace(
        provisional, lineage_hash=lineage,
        snapshot_id=f"sec-insider-parsed-{year}q{quarter}-{lineage[:16]}",
    )
    rows = []
    summaries = []
    for index, accession in enumerate(accessions, start=1):
        form = "4" if index <= 6 else "4/A"
        values = (accession, filing_date_raw, filing_date, form, _ISSUER,
                  "Invented Issuer", "INVT")
        row_id = _source_row_id(
            raw_snapshot_id=identity.raw_snapshot_id,
            raw_lineage_hash=identity.raw_lineage_hash,
            raw_archive_sha256=identity.raw_archive_sha256,
            table_name="SUBMISSION.tsv", raw_member_sha256=tables[0].raw_member_sha256,
            source_record_ordinal=index, values=values, source_row_key=(),
        )
        rows.append(ParsedSecBulkRow(
            table_name="SUBMISSION.tsv", schema_id="submission",
            source_record_ordinal=index, accession_number=accession,
            values=values, source_row_key=(), row_id=row_id,
        ))
        summaries.append(ParsedSecBulkAccession(
            accession_number=accession, document_type=form,
            submission_row_id=row_id,
            table_rows=(("SUBMISSION.tsv", (row_id,)),
                        ("REPORTINGOWNER.tsv", ()), ("NONDERIV_TRANS.tsv", ())),
        ))
    return LoadedSecBulkParsedSnapshot(identity, tuple(rows), tuple(summaries))


def _complete(accession: str, form: str, date_text: str) -> bytes:
    compact = date_text.replace("-", "")
    return (
        f"<SEC-DOCUMENT>{accession}.txt : {compact}\n"
        f"<SEC-HEADER>{accession}.hdr.sgml : {compact}\n"
        f"<ACCEPTANCE-DATETIME>{compact}101112\n"
        f"<ACCESSION-NUMBER>{accession}\n<TYPE>{form}\n"
        f"<FILING-DATE>{compact}\n"
        f"<REPORTING-OWNER>\n<OWNER-DATA>\n<CIK>{_OWNER}\n"
        "<CONFORMED-NAME>Invented Owner\n</OWNER-DATA>\n</REPORTING-OWNER>\n"
        f"<ISSUER>\n<COMPANY-DATA>\n<CIK>{_ISSUER}\n"
        "</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
        f"<DOCUMENT>\n<TYPE>{form}\n<SEQUENCE>1\n"
        "<FILENAME>ownership.xml\n<TEXT>\n"
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        f"<ownershipDocument><documentType>{form}</documentType>"
        f"<issuer><issuerCik>{_ISSUER}</issuerCik></issuer>"
        f"<reportingOwner><reportingOwnerId><rptOwnerCik>{_OWNER}</rptOwnerCik>"
        "</reportingOwnerId></reportingOwner></ownershipDocument>\n"
        "</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n"
    ).encode("ascii")


def _fixture():
    accessions = adapter.FIXED_ACCESSIONS
    snapshots = (_snapshot("2022Q4", accessions[:8]),
                 _snapshot("2023Q1", accessions[8:]))
    candidates = []
    projections = []
    for index, accession in enumerate(accessions):
        snapshot = snapshots[0] if index < 8 else snapshots[1]
        period = "2022Q4" if index < 8 else "2023Q1"
        form = "4" if index % 8 < 6 else "4/A"
        date_text = "2022-11-07" if index < 8 else "2023-02-10"
        candidate = {
            "period": period, "accession_number": accession, "form_type": form,
            "filing_date_raw": snapshot.rows[index % 8].values[1],
            "filing_date": date_text,
            "issuer_cik": _ISSUER, "quarterly_zip_sha256": snapshot.identity.raw_archive_sha256,
            "submission_row_id": snapshot.rows[index % 8].row_id,
            "raw_snapshot_id": snapshot.identity.raw_snapshot_id,
            "raw_lineage_sha256": snapshot.identity.raw_lineage_hash,
        }
        candidates.append(candidate)
        target = SecCompleteSubmissionTarget(
            period=period, accession_number=accession, form_type=form,
            filing_date=date_text, issuer_cik=_ISSUER,
            quarterly_index_sha256="5" * 64,
            complete_submission_url=(
                "https://www.sec.gov/Archives/edgar/data/123456/" + accession + ".txt"
            ),
        )
        projections.append(SecCompleteSubmissionProjection(
            target, _complete(accession, form, date_text),
        ))
    inventory_sha = hash_payload(candidates)
    report = {
        "kind": "INSETF-SEC-SIXTEEN-COMPLETE-TXT-v1",
        "inventory_sha256": inventory_sha,
        "capture_git_commit_verified": "a" * 40,
        "master_indexes": [{}, {}],
        "filings": [{"candidate": candidate, "projection": projection.to_payload()}
                    for candidate, projection in zip(candidates, projections, strict=True)],
        "attempt_count": 18, "distinct_artifact_count": 18,
        "halted_reason": None, "complete_sample_acquired": True,
        "source_authenticated": False, "canonical_evidence": False,
        "point_in_time_data": False, "direct_ib1c_ingest_authorized": False,
        "official_sec_profile_verified": False, "outcome_access_authorized": False,
        "qc_job_authorized": False, "broker_or_trading_authorized": False,
        "research_looks": 0, "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0, "attempt_journal": {},
    }
    raw_report = _canonical(report)
    receipt = adapter.SecCompletePilotProjectionReceipt(
        report_sha256=hash_bytes(raw_report), inventory_sha256=inventory_sha,
        code_commit="a" * 40, projections=tuple(projections),
        _report_bytes=raw_report,
        _projection_sha256s=tuple(item.sha256 for item in projections),
        _expected_accessions=accessions, _public_pilot=False,
        _loader_token=adapter._LOADER_TOKEN,
    )
    return receipt, snapshots


def test_exact_sixteen_are_date_only_with_four_amendments_quarantined():
    receipt, snapshots = _fixture()
    result = pilot.assess_complete_pilot_ib1c_availability(receipt, snapshots)
    payload = result.to_payload()
    assert len(payload["rows"]) == 16
    assert tuple(row["accession_number"] for row in payload["rows"]) == adapter.FIXED_ACCESSIONS
    assert {row["availability_tier"] for row in payload["rows"]} == {"filing_date_fallback"}
    assert {row["next_open_rule"] for row in payload["rows"]} == {
        "next-open-after-filing-date"
    }
    assert all(row["accepted_at"] is None for row in payload["rows"])
    assert all(row["availability_role"] == "non_executable_diagnostic"
               and row["next_open_rule_executable"] is False for row in payload["rows"])
    assert all(row["signal_authorized"] is False for row in payload["rows"])
    assert all(len(row["accepted_at_raw_uninterpreted"]) == 14 for row in payload["rows"])
    assert sum(row["amendment_status"] == "quarantined_original_link_unverified"
               for row in payload["rows"]) == 4
    assert payload["authority"] == {
        "input_snapshots_reloaded_here": False,
        "full_quarter_ib1c_snapshot": False,
        "exact_acceptance_time_available": False,
        "date_only_rule_executable": False,
        "timezone_interpretation_verified": False,
        "source_authenticated": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "direct_ib1c_v1_ingest_authorized": False,
        "amendment_lineage_verified": False,
        "signal_authorized": False,
        "outcome_access_authorized": False,
        "qc_job_authorized": False,
        "broker_or_trading_authorized": False,
        "research_looks": 0,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }
    assert result.sha256 == hash_payload(payload)


def test_missing_selected_submission_row_refuses():
    receipt, snapshots = _fixture()
    changed = replace(snapshots[0], rows=snapshots[0].rows[:-1])
    with pytest.raises(pilot.SecCompleteIb1cPilotAvailabilityError,
                       match="missing a selected accession or SUBMISSION row"):
        pilot.assess_complete_pilot_ib1c_availability(receipt, (changed, snapshots[1]))


def test_duplicate_selected_accession_refuses():
    receipt, snapshots = _fixture()
    changed = replace(snapshots[0], accessions=snapshots[0].accessions
                      + (snapshots[0].accessions[0],))
    with pytest.raises(pilot.SecCompleteIb1cPilotAvailabilityError,
                       match="repeats a selected accession"):
        pilot.assess_complete_pilot_ib1c_availability(receipt, (changed, snapshots[1]))


def test_duplicate_selected_submission_row_refuses():
    receipt, snapshots = _fixture()
    changed = replace(snapshots[0], rows=snapshots[0].rows
                      + (snapshots[0].rows[0],))
    with pytest.raises(pilot.SecCompleteIb1cPilotAvailabilityError,
                       match="repeats a selected SUBMISSION row"):
        pilot.assess_complete_pilot_ib1c_availability(receipt, (changed, snapshots[1]))


def test_unapproved_ib1b_raw_date_spelling_refuses():
    receipt, snapshots = _fixture()
    snapshot = snapshots[0]
    row = snapshot.rows[0]
    table = snapshot.identity.tables[0]
    values = list(row.values)
    values[table.headers.index("FILING_DATE")] = "2022-11-07"
    values = tuple(values)
    new_row = replace(row, values=values, row_id=_source_row_id(
        raw_snapshot_id=snapshot.identity.raw_snapshot_id,
        raw_lineage_hash=snapshot.identity.raw_lineage_hash,
        raw_archive_sha256=snapshot.identity.raw_archive_sha256,
        table_name="SUBMISSION.tsv", raw_member_sha256=table.raw_member_sha256,
        source_record_ordinal=row.source_record_ordinal, values=values, source_row_key=(),
    ))
    changed = replace(snapshot, rows=(new_row,) + snapshot.rows[1:],
                      accessions=(replace(snapshot.accessions[0],
                                          submission_row_id=new_row.row_id,
                                          table_rows=(("SUBMISSION.tsv", (new_row.row_id,)),
                                                      ("REPORTINGOWNER.tsv", ()),
                                                      ("NONDERIV_TRANS.tsv", ()))),)
                      + snapshot.accessions[1:])
    with pytest.raises(pilot.SecCompleteIb1cPilotAvailabilityError,
                       match="submission identity disagree"):
        pilot.assess_complete_pilot_ib1c_availability(receipt, (changed, snapshots[1]))


@pytest.mark.parametrize("field,value", (
    ("DOCUMENT_TYPE", "5"), ("FILING_DATE", "08-NOV-2022"),
    ("ISSUERCIK", "0000999999"),
))
def test_form_date_or_issuer_drift_refuses_even_with_recomputed_row_id(field, value):
    receipt, snapshots = _fixture()
    snapshot = snapshots[0]
    row = snapshot.rows[0]
    table = snapshot.identity.tables[0]
    values = list(row.values)
    values[table.headers.index(field)] = value
    values = tuple(values)
    new_row = replace(row, values=values, row_id=_source_row_id(
        raw_snapshot_id=snapshot.identity.raw_snapshot_id,
        raw_lineage_hash=snapshot.identity.raw_lineage_hash,
        raw_archive_sha256=snapshot.identity.raw_archive_sha256,
        table_name="SUBMISSION.tsv", raw_member_sha256=table.raw_member_sha256,
        source_record_ordinal=row.source_record_ordinal, values=values, source_row_key=(),
    ))
    changed = replace(snapshot, rows=(new_row,) + snapshot.rows[1:],
                      accessions=(replace(snapshot.accessions[0],
                                          document_type=values[table.headers.index("DOCUMENT_TYPE")],
                                          submission_row_id=new_row.row_id,
                                          table_rows=(("SUBMISSION.tsv", (new_row.row_id,)),
                                                      ("REPORTINGOWNER.tsv", ()),
                                                      ("NONDERIV_TRANS.tsv", ()))),)
                      + snapshot.accessions[1:])
    with pytest.raises(pilot.SecCompleteIb1cPilotAvailabilityError,
                       match="submission identity disagree"):
        pilot.assess_complete_pilot_ib1c_availability(receipt, (changed, snapshots[1]))


def test_submission_row_id_must_match_pinned_complete_pilot_inventory():
    receipt, snapshots = _fixture()
    report = json.loads(receipt._report_bytes)
    report["filings"][0]["candidate"]["submission_row_id"] = "f" * 64
    candidates = [row["candidate"] for row in report["filings"]]
    inventory_sha = hash_payload(candidates)
    report["inventory_sha256"] = inventory_sha
    raw = _canonical(report)
    changed = replace(receipt, _report_bytes=raw, report_sha256=hash_bytes(raw),
                      inventory_sha256=inventory_sha)
    with pytest.raises(pilot.SecCompleteIb1cPilotAvailabilityError,
                       match="submission identity disagree"):
        pilot.assess_complete_pilot_ib1c_availability(changed, snapshots)


def test_unknown_timezone_never_becomes_an_exact_acceptance_instant():
    receipt, snapshots = _fixture()
    result = pilot.assess_complete_pilot_ib1c_availability(receipt, snapshots)
    first = result.to_payload()["rows"][0]
    assert first["accepted_at_raw_uninterpreted"] == "20221107101112"
    assert first["accepted_at"] is None
    assert first["next_open_rule"] == "next-open-after-filing-date"


def test_coherent_later_raw_acceptance_date_refuses_early_date_only_rule():
    receipt, snapshots = _fixture()
    projections = list(receipt.projections)
    original = projections[0]
    changed_raw = original.raw_bytes.replace(
        b"<ACCEPTANCE-DATETIME>20221107101112",
        b"<ACCEPTANCE-DATETIME>20221108101112",
    )
    assert changed_raw != original.raw_bytes
    projections[0] = SecCompleteSubmissionProjection(original.target, changed_raw)
    report = json.loads(receipt._report_bytes)
    report["filings"][0]["projection"] = projections[0].to_payload()
    raw_report = _canonical(report)
    changed = replace(
        receipt, projections=tuple(projections), _report_bytes=raw_report,
        report_sha256=hash_bytes(raw_report),
        _projection_sha256s=tuple(item.sha256 for item in projections),
    )
    with pytest.raises(pilot.SecCompleteIb1cPilotAvailabilityError,
                       match="raw acceptance date differs from filing date"):
        pilot.assess_complete_pilot_ib1c_availability(changed, snapshots)


def test_receipt_revalidates_and_refuses_caller_mutation():
    receipt, snapshots = _fixture()
    result = pilot.assess_complete_pilot_ib1c_availability(receipt, snapshots)
    object.__setattr__(result, "rows", result.rows[:-1])
    with pytest.raises(pilot.SecCompleteIb1cPilotAvailabilityError,
                       match="lost its source binding"):
        result.to_payload()


def test_row_serialization_does_not_leak_unrecognized_positive_authority():
    receipt, snapshots = _fixture()
    result = pilot.assess_complete_pilot_ib1c_availability(receipt, snapshots)
    object.__setattr__(result.rows[0], "canonical_evidence", True)
    assert "canonical_evidence" not in result.to_payload()["rows"][0]


def test_period_order_and_partial_snapshot_refuse():
    receipt, snapshots = _fixture()
    with pytest.raises(pilot.SecCompleteIb1cPilotAvailabilityError,
                       match="exact ordered two quarters"):
        pilot.assess_complete_pilot_ib1c_availability(receipt, snapshots[::-1])
    with pytest.raises(pilot.SecCompleteIb1cPilotAvailabilityError,
                       match="exactly two ordered"):
        pilot.assess_complete_pilot_ib1c_availability(receipt, snapshots[:1])


# Section 107 (Claude review): isolate two guards whose deletion no earlier
# test detected. Each forges one in-memory IB-1B object the raw-bound loader
# would never return, so only the named recheck can refuse it.
def test_selected_row_values_must_reproduce_its_lineage_row_id():
    receipt, snapshots = _fixture()
    index = next(i for i, row in enumerate(snapshots[0].rows)
                 if row.table_name == "SUBMISSION.tsv"
                 and row.accession_number == adapter.FIXED_ACCESSIONS[0])
    row = snapshots[0].rows[index]
    name_at = _SUBMISSION_HEADERS.index("ISSUERNAME")
    values = row.values[:name_at] + ("Invented Other Name",) + row.values[name_at + 1:]
    object.__setattr__(row, "values", values)
    with pytest.raises(pilot.SecCompleteIb1cPilotAvailabilityError,
                       match="selected SUBMISSION row lineage is inconsistent"):
        pilot.assess_complete_pilot_ib1c_availability(receipt, snapshots)


@pytest.mark.parametrize("field", ["schema_profile_hash", "lineage_hash"])
def test_snapshot_identity_must_be_internally_consistent(field):
    receipt, snapshots = _fixture()
    identity = snapshots[0].identity
    object.__setattr__(identity, field, "0" * 64)
    if field == "schema_profile_hash":
        # Re-derive the lineage and ID so only the profile-hash recheck differs.
        lineage = hash_payload(identity.lineage_payload())
        object.__setattr__(identity, "lineage_hash", lineage)
        object.__setattr__(identity, "snapshot_id", f"sec-insider-parsed-2022q4-{lineage[:16]}")
    with pytest.raises(pilot.SecCompleteIb1cPilotAvailabilityError,
                       match="identity is internally inconsistent"):
        pilot.assess_complete_pilot_ib1c_availability(receipt, snapshots)
