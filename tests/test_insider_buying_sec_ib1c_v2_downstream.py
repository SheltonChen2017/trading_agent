"""Invented supplied-source coverage; no artifact I/O or research promotion."""
from dataclasses import replace

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying import sec_ib1c_v2_downstream as module
from research.insider_buying.sec_bulk_parsed_snapshot import (
    LoadedSecBulkParsedSnapshot, ParsedSecBulkAccession, ParsedSecBulkRow, _source_row_id,
)
from research.insider_buying.sec_ib1c_identity_v2 import assess_ib1c_v2_quarter_identity
from test_insider_buying_sec_ib1c_identity_v2 import _inputs, _parent
from test_insider_buying_sec_master_locator_reconciliation import _snapshot, _census


def _binding(snapshot, assessment, **changes):
    payload = assessment.to_payload()
    envelope = (canonical_json({"payload": payload, "payload_sha256": assessment.sha256}) + "\n").encode()
    values = dict(
        period=payload["period"], producer_commit="f" * 40,
        producer_source_inventory_sha256="a" * 64, completion_envelope_sha256="b" * 64,
        assessment_envelope_sha256=hash_bytes(envelope), assessment_envelope_bytes=len(envelope),
        raw_snapshot_id=snapshot.identity.raw_snapshot_id,
        raw_lineage_sha256=snapshot.identity.raw_lineage_hash,
        parsed_snapshot_id=snapshot.identity.snapshot_id,
        parsed_lineage_sha256=snapshot.identity.lineage_hash,
        profile_sha256=snapshot.identity.schema_profile_hash,
        census_quarter_sha256=payload["census_quarter_sha256"],
    )
    values.update(changes)
    return module.V2PreparationBinding(**values)


def _coverage(specs=(("4", "15-JAN-2023", "123456", "22"),), *, parents=True, **binding_changes):
    snapshot, census = _inputs(specs)
    supplied = tuple(_parent(row) for row in snapshot.rows if row.values[3] in {"4", "4/A"}) if parents else ()
    assessment = assess_ib1c_v2_quarter_identity(snapshot, census, supplied)
    return module.build_v2_quarter_coverage(assessment, _binding(snapshot, assessment, **binding_changes))


def _other_quarter(period="2023Q2", *, accession=None, **binding_changes):
    snapshot = _snapshot(period)
    if accession is not None:
        original = snapshot.rows[0]
        values = (accession, *original.values[1:])
        row_id = _source_row_id(
            raw_snapshot_id=snapshot.identity.raw_snapshot_id,
            raw_lineage_hash=snapshot.identity.raw_lineage_hash,
            raw_archive_sha256=snapshot.identity.raw_archive_sha256,
            table_name="SUBMISSION.tsv", raw_member_sha256="b" * 64,
            source_record_ordinal=1, values=values, source_row_key=(),
        )
        row = ParsedSecBulkRow("SUBMISSION.tsv", "submission", 1, accession, values, (), row_id)
        table = replace(snapshot.identity.tables[0], row_ids_hash=hash_payload([row_id]))
        provisional = replace(snapshot.identity, tables=(table, *snapshot.identity.tables[1:]),
                              lineage_hash="", snapshot_id="")
        lineage = hash_payload(provisional.lineage_payload())
        identity = replace(provisional, lineage_hash=lineage,
                           snapshot_id=f"sec-insider-parsed-{period.lower()}-{lineage[:16]}")
        summary = ParsedSecBulkAccession(accession, "4", row_id, (("SUBMISSION.tsv", (row_id,)),))
        snapshot = LoadedSecBulkParsedSnapshot(identity, (row,), (summary,))
    census = next(q for q in _census().quarters if q.period == period)
    assessment = assess_ib1c_v2_quarter_identity(snapshot, census)
    return module.build_v2_quarter_coverage(assessment, _binding(snapshot, assessment, **binding_changes))


def _unsafe_resealed_assessment(snapshot, assessment, edit):
    """Isolate consumer guards after deliberately bypassing the input factory.

    This does not represent a public assessor output or a raw-artifact proof.
    """
    body = assessment.to_payload()
    edit(body)
    body["accounting_sha256"] = hash_payload(body["rows"])
    body["whole_quarter_identity_sha256"] = (
        body["accounting_sha256"] if body["rows"] and not body["quarantined_count"] else None)
    raw = canonical_json(body).encode()
    object.__setattr__(assessment, "_canonical_bytes", raw)
    object.__setattr__(assessment, "_digest", hash_bytes(raw))
    object.__setattr__(assessment, "_factory_bytes", raw)
    return assessment, _binding(snapshot, assessment)


def test_positive_corroborated_mismatch_short_cik_is_consumable_not_financial_eligibility():
    coverage = _coverage()
    payload = coverage.to_payload()
    row = coverage.pilot_rows()[0]
    assert payload["submission_count"] == payload["corroborated_count"] == 1
    assert payload["quarantined_count"] == 0
    assert payload["source_identity_complete"] is True
    assert payload["source_identity_sha256"] == payload["rows_sha256"]
    assert payload["accession_year_mismatch_count"] == payload["short_cik_count"] == 1
    assert row["raw_issuer_cik"] == "123456" and row["issuer_comparison_key"] == "0000123456"
    assert row["raw_filing_date"] == "15-JAN-2023" and row["accession_number"][11:13] == "22"
    assert row["accession_year_mismatch"] is True
    assert coverage.admitted_rows() == coverage.pilot_rows()
    assert payload["artifact_loading_verified_here"] is False
    assert payload["binding_is_external_attestation"] is False
    assert all(type(value) is bool and value is False or type(value) is int and value == 0
               for value in payload["authority"].values())
    assert "rows" not in payload and "review" not in canonical_json(payload).lower()


def test_all_six_forms_and_every_quarantine_reason_remain_in_pilot_rows():
    specs = tuple((form, "2023-01-15", "123456", "23") for form in module._FORMS)
    coverage = _coverage(specs)
    body = coverage.to_payload()
    assert body["submission_count"] == 6 and body["corroborated_count"] == 2
    assert body["quarantined_count"] == 4
    assert body["form_counts"] == dict.fromkeys(module._FORMS, 1)
    assert body["quarantine_reason_counts"]["unsupported_parent_corroboration_form"] == 4
    assert body["source_identity_complete"] is False and body["source_identity_sha256"] is None
    assert [row["form_type"] for row in coverage.pilot_rows()] == list(module._FORMS)
    assert [row["form_type"] for row in coverage.admitted_rows()] == ["4", "4/A"]


def test_missing_and_conflicting_parent_evidence_never_becomes_admission_by_presence():
    snapshot, census = _inputs()
    assessment = assess_ib1c_v2_quarter_identity(snapshot, census, (_parent(snapshot.rows[0], cik="0000123457"),))
    conflict = module.build_v2_quarter_coverage(assessment, _binding(snapshot, assessment))
    assert conflict.pilot_rows()[0]["corroboration"] is not None
    assert conflict.admitted_rows() == []
    assert conflict.to_payload()["quarantine_reason_counts"]["complete_parent_identity_conflict"] == 1
    missing = _coverage(parents=False)
    assert missing.admitted_rows() == []
    assert missing.to_payload()["quarantine_reason_counts"]["complete_parent_corroboration_missing"] == 1


@pytest.mark.parametrize("changes", [
    {"period": "2005Q4"}, {"period": "2026Q3"}, {"period": 2023},
    {"producer_commit": "F" * 40}, {"producer_commit": "a" * 39}, {"producer_commit": True},
    {"producer_source_inventory_sha256": "bad"}, {"completion_envelope_sha256": None},
    {"assessment_envelope_sha256": "A" * 64}, {"assessment_envelope_bytes": True},
    {"assessment_envelope_bytes": 0}, {"assessment_envelope_bytes": 128 * 1024 * 1024 + 1},
    {"raw_snapshot_id": "sec-insider-bulk-2023q1-" + "2" * 16},
    {"raw_lineage_sha256": "bad"}, {"parsed_snapshot_id": "../parsed"},
    {"parsed_lineage_sha256": "bad"}, {"profile_sha256": "bad"}, {"census_quarter_sha256": "bad"},
])
def test_preparation_binding_strict_shapes_and_types(changes):
    snapshot, census = _inputs()
    assessment = assess_ib1c_v2_quarter_identity(snapshot, census)
    with pytest.raises(module.V2DownstreamCoverageError):
        _binding(snapshot, assessment, **changes)


@pytest.mark.parametrize("changes", [
    {"assessment_envelope_sha256": "f" * 64}, {"assessment_envelope_bytes": 1},
    {"census_quarter_sha256": "f" * 64},
])
def test_binding_cannot_substitute_assessment_envelope_or_census(changes):
    snapshot, census = _inputs()
    assessment = assess_ib1c_v2_quarter_identity(snapshot, census)
    with pytest.raises(module.V2DownstreamCoverageError):
        module.build_v2_quarter_coverage(assessment, _binding(snapshot, assessment, **changes))


def test_binding_period_parsed_id_and_lineage_cannot_cross_quarters():
    snapshot, census = _inputs()
    assessment = assess_ib1c_v2_quarter_identity(snapshot, census)
    other = _other_quarter().to_payload()["preparation_binding"]
    binding = module.V2PreparationBinding(**other)
    with pytest.raises(module.V2DownstreamCoverageError):
        module.build_v2_quarter_coverage(assessment, binding)
    with pytest.raises(module.V2DownstreamCoverageError):
        module.build_v2_quarter_coverage(assessment.to_payload(), _binding(snapshot, assessment))
    with pytest.raises(module.V2DownstreamCoverageError):
        module.build_v2_quarter_coverage(assessment, _binding(snapshot, assessment).to_payload())


@pytest.mark.parametrize("edit", [
    lambda b: b["rows"][0].update(source_record_ordinal=True),
    lambda b: b["rows"][0].update(source_record_ordinal=2),
    lambda b: b["rows"][0].update(form_type="8-K"),
    lambda b: b["rows"][0].update(accession_number="bad"),
    lambda b: b["rows"][0].update(parsed_lineage_hash="f" * 64),
    lambda b: b["rows"][0].update(raw_archive_sha256="bad"),
    lambda b: b["rows"][0].update(raw_submission_member_sha256="bad"),
    lambda b: b["rows"][0].update(submission_row_id="bad"),
    lambda b: b["rows"][0].update(raw_issuer_cik="１２３"),
    lambda b: b["rows"][0].update(raw_issuer_cik="0"),
    lambda b: b["rows"][0].update(issuer_comparison_key="0000123457"),
    lambda b: b["rows"][0].update(short_cik=1),
    lambda b: b["rows"][0].update(short_cik=False),
    lambda b: b["rows"][0].update(raw_filing_date="2023-04-15", filing_date="2023-04-15"),
    lambda b: b["rows"][0].update(raw_filing_date="2023-02-30"),
    lambda b: b["rows"][0].update(filing_date="2023-01-16"),
    lambda b: b["rows"][0].update(accession_year_mismatch=1),
    lambda b: b["rows"][0].update(accession_year_mismatch=False),
    lambda b: b["rows"][0].update(disposition="corroborated_noncanonical"),
    lambda b: b["rows"][0].update(quarantine_reasons=[]),
    lambda b: b["rows"][0].update(corroboration={"parent_sha256": "a" * 64}),
    lambda b: b["rows"][0].update(unexpected="field"),
    lambda b: b.update(corroborated_count=True),
    lambda b: b.update(evidence_epoch="another-epoch"),
    lambda b: b["authority"].update(source_authenticated=0),
    lambda b: b["authority"].update(qc_jobs=True),
])
def test_consumer_independently_refuses_resealed_bad_row_policy_or_accounting(edit):
    snapshot, census = _inputs((("4", "15-JAN-2023", "123456", "22"),))
    assessment = assess_ib1c_v2_quarter_identity(snapshot, census)
    assessment, binding = _unsafe_resealed_assessment(snapshot, assessment, edit)
    with pytest.raises(module.V2DownstreamCoverageError):
        module.build_v2_quarter_coverage(assessment, binding)


def test_row_archive_member_drift_duplicate_and_mixed_dialect_refuse():
    specs = (("4", "2023-01-15", "123456", "23"), ("4/A", "2023-01-15", "123456", "23"))
    for change in (
        {"raw_archive_sha256": "e" * 64}, {"raw_submission_member_sha256": "e" * 64},
        {"accession_number": "0000123456-23-000001"}, {"raw_filing_date": "15-JAN-2023"},
    ):
        snapshot, census = _inputs(specs)
        assessment = assess_ib1c_v2_quarter_identity(snapshot, census)
        assessment, binding = _unsafe_resealed_assessment(snapshot, assessment,
                                                        lambda b: b["rows"][1].update(change))
        with pytest.raises(module.V2DownstreamCoverageError):
            module.build_v2_quarter_coverage(assessment, binding)


def test_caller_copies_and_binding_mutation_do_not_change_sealed_coverage():
    snapshot, census = _inputs()
    assessment = assess_ib1c_v2_quarter_identity(snapshot, census)
    binding = _binding(snapshot, assessment)
    coverage = module.build_v2_quarter_coverage(assessment, binding)
    original = coverage.to_payload()
    coverage.to_payload()["authority"]["qc_authorized"] = True
    coverage.pilot_rows()[0]["raw_issuer_cik"] = "1"
    object.__setattr__(binding, "producer_commit", "e" * 40)
    assert coverage.to_payload() == original
    assert coverage.pilot_rows()[0]["raw_issuer_cik"] == "123456"
    assert coverage.sha256 == hash_payload(original)
    for forged in (replace(coverage), replace(coverage, _summary_raw=b"{}")):
        with pytest.raises(module.V2DownstreamCoverageError):
            forged.to_payload()


def test_empty_quarter_and_missing_scope_never_emit_identity_completeness():
    empty = _coverage((), parents=False)
    assert empty.to_payload()["source_identity_complete"] is False
    scope = module.compose_v2_scope_coverage((empty,), ("2023Q1",))
    assert scope.to_payload()["loaded_scope_complete"] is True
    assert scope.to_payload()["source_identity_complete"] is False
    assert scope.to_payload()["source_identity_sha256"] is None
    missing = module.compose_v2_scope_coverage((), ("2023Q1",))
    assert missing.to_payload()["missing_periods"] == ["2023Q1"]
    assert missing.pilot_rows() == []
    partial = module.compose_v2_scope_coverage((_coverage(),), ("2023Q1", "2023Q2"))
    assert partial.to_payload()["corroborated_count"] == 1
    assert partial.to_payload()["loaded_scope_complete"] is False
    assert partial.to_payload()["source_identity_sha256"] is None


def test_complete_scope_has_a_positive_identity_path_but_never_financial_authority():
    coverage = _coverage()
    scope = module.compose_v2_scope_coverage((coverage,), ("2023Q1",))
    body = scope.to_payload()
    assert body["loaded_scope_complete"] is True and body["source_identity_complete"] is True
    assert body["source_identity_sha256"] and body["corroborated_count"] == 1
    assert scope.admitted_rows() == coverage.admitted_rows() == scope.pilot_rows()
    assert all(v is False or type(v) is int and v == 0 for v in body["authority"].values())
    assert scope.sha256 == hash_payload(body)


@pytest.mark.parametrize("expected", [(), ["2023Q1"], (True,), ("2026Q3",),
                                     ("2023Q1", "2023Q1"), ("2023Q2", "2023Q1")])
def test_expected_scope_requires_an_ordered_unique_frozen_window_subset(expected):
    with pytest.raises(module.V2DownstreamCoverageError):
        module.compose_v2_scope_coverage((), expected)


def test_repeated_reordered_nonprefix_and_non_tuple_coverage_refuse():
    first, second = _coverage(), _other_quarter()
    for supplied in ((first, first), (second, first), (second,), [first], (first.to_payload(),)):
        with pytest.raises(module.V2DownstreamCoverageError):
            module.compose_v2_scope_coverage(supplied, ("2023Q1", "2023Q2"))


@pytest.mark.parametrize("changes", [
    {"producer_commit": "e" * 40}, {"producer_source_inventory_sha256": "e" * 64},
    {"profile_sha256": "e" * 64},
])
def test_scope_rejects_mixed_producer_or_profile_epochs(changes):
    with pytest.raises(module.V2DownstreamCoverageError, match="epochs"):
        module.compose_v2_scope_coverage((_coverage(), _other_quarter(**changes)), ("2023Q1", "2023Q2"))


def test_scope_rejects_a_different_consumer_evidence_epoch(monkeypatch):
    first = _coverage()
    monkeypatch.setattr(module, "COVERAGE_EVIDENCE_EPOCH", "a-future-invented-epoch")
    second = _other_quarter()
    with pytest.raises(module.V2DownstreamCoverageError, match="epochs"):
        module.compose_v2_scope_coverage((first, second), ("2023Q1", "2023Q2"))


def test_scope_cross_quarter_duplicate_accession_refuses_without_dropping_rows():
    first = _coverage()
    second = _other_quarter(accession=first.pilot_rows()[0]["accession_number"])
    with pytest.raises(module.V2DownstreamCoverageError, match="repeats"):
        module.compose_v2_scope_coverage((first, second), ("2023Q1", "2023Q2"))


def test_scope_copies_reconstruction_and_later_quarter_mutation_cannot_change_result():
    first, second = _coverage(), _other_quarter()
    scope = module.compose_v2_scope_coverage((first, second), ("2023Q1", "2023Q2"))
    body = scope.to_payload()
    assert body["loaded_scope_complete"] is True and body["source_identity_complete"] is False
    assert len(scope.pilot_rows()) == body["submission_count"] == 2
    assert [row["period"] for row in scope.pilot_rows()] == ["2023Q1", "2023Q2"]
    scope.pilot_rows()[0]["raw_issuer_cik"] = "1"
    assert scope.to_payload() == body
    with pytest.raises(module.V2DownstreamCoverageError):
        replace(scope).to_payload()
    object.__setattr__(first, "_rows_raw", b"[]")
    with pytest.raises(module.V2DownstreamCoverageError):
        scope.to_payload()
    with pytest.raises(module.V2DownstreamCoverageError):
        scope.pilot_rows()


def test_unchanged_finite_row_bounds_are_enforced_in_quarter_and_scope(monkeypatch):
    first, second = _coverage(), _other_quarter()
    monkeypatch.setattr(module, "MAX_QUARTER_FILINGS", 0)
    with pytest.raises(module.V2DownstreamCoverageError, match="quarter"):
        _coverage()
    with pytest.raises(module.V2DownstreamCoverageError, match="quarter"):
        module.compose_v2_scope_coverage((first,), ("2023Q1",))
    monkeypatch.setattr(module, "MAX_QUARTER_FILINGS", 500_000)
    monkeypatch.setattr(module, "MAX_TOTAL_FILINGS", 1)
    with pytest.raises(module.V2DownstreamCoverageError, match="total"):
        module.compose_v2_scope_coverage((first, second), ("2023Q1", "2023Q2"))
