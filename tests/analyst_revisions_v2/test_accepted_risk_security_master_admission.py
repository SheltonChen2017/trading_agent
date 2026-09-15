"""Isolating tests for the owner-accepted Sharadar identity fallback."""
from __future__ import annotations

import dataclasses
import json
import os
import weakref
from pathlib import Path

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from research.analyst_revisions_v2_qc import (
    accepted_risk_security_master_admission as module,
)
from research.analyst_revisions_v2_qc.accepted_risk_security_master_admission import (
    AcceptedRiskSecurityMasterAdmission,
    AcceptedRiskSecurityMasterAdmissionError,
    build_accepted_risk_security_master_admission,
    iter_accepted_risk_security_master_mappings,
    iter_accepted_risk_security_master_refusals,
    require_accepted_risk_security_master_admission,
)
from research.analyst_revisions_v2_qc.physical_preopen_seed_archive import (
    _build_physical_preopen_seed_archive_for_test,
    iter_physical_universe_candidates,
)
from tests.analyst_revisions_v2.test_physical_preopen_seed_archive import _sources


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _row(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "security_id": "sharadar-composite-figi-BBG000000001",
        "issuer_id": "sharadar-permaticker-1001",
        "source_composite_figi": "BBG000000001",
        "listing_id": "sharadar-listing-aaaaaaaaaaaaaaaaaaaaaaaa",
        "sharadar_cusip_join_candidates": ["000000001"],
        "current_snapshot_ticker_display": "AAA",
        "current_snapshot_listing_exchange": "XNAS",
        "current_snapshot_sector_id": "sharadar-sector-Technology",
        "current_snapshot_industry_id": "sharadar-industry-Software",
        "candidate_first_session": "2013-01-02",
        "candidate_last_session": "2025-12-31",
        "source_row_sha256": HASH_A,
        "identity_evidence_sha256": HASH_B,
        "classification_evidence_sha256": HASH_C,
        "source_snapshot_available_at": "2026-09-14T00:00:00+00:00",
        "qc_security_id": None,
        "mapping_status": "requires_outcome_free_qc_discovery",
        "membership_status": "review_required_current_snapshot_not_PIT",
        "point_in_time": False,
    }
    value.update(changes)
    return value


def _source(count: int = 1, **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "seed_archive_id": "arv2-physical-preopen-seed-aaaaaaaaaaaaaaaaaaaaaaaa",
        "seed_archive_sha256": HASH_A,
        "eligible_universe_artifact_sha256": HASH_B,
        "sharadar_capture_id": "arv2-sharadar-source-aaaaaaaaaaaaaaaaaaaaaaaa",
        "sharadar_capture_sha256": HASH_C,
        "source_snapshot_available_at": "2026-09-14T00:00:00+00:00",
        "source_candidate_count": count,
    }
    value.update(changes)
    return value


def _document(*rows: dict[str, object]) -> dict[str, object]:
    return module._compose_document(rows, _source(len(rows)))


def _second_row(**changes: object) -> dict[str, object]:
    value = _row(
        security_id="sharadar-composite-figi-BBG000000002",
        issuer_id="sharadar-permaticker-1002",
        source_composite_figi="BBG000000002",
        listing_id="sharadar-listing-bbbbbbbbbbbbbbbbbbbbbbbb",
        sharadar_cusip_join_candidates=["000000002"],
        current_snapshot_ticker_display="BBB",
        source_row_sha256="d" * 64,
        identity_evidence_sha256="e" * 64,
        classification_evidence_sha256="f" * 64,
    )
    value.update(changes)
    return value


def _reason_codes(document: dict[str, object]) -> list[list[str]]:
    return [row["reason_codes"] for row in document["named_refusals"]]


def test_unique_current_snapshot_mapping_is_admitted_with_every_risk_flag():
    document = _document(_row())
    mapping = document["admitted_mappings"][0]

    assert document["census"] == {
        "source_candidate_count": 1,
        "admitted_mapping_count": 1,
        "named_refusal_count": 0,
        "refusal_reason_counts": {},
    }
    assert document["named_refusals"] == []
    assert mapping["mapping_status"] == module.MAPPING_STATUS
    assert mapping["security_id"] == "sharadar-composite-figi-BBG000000001"
    assert mapping["ticker"] == "AAA"
    assert mapping["qc_security_id"] is None
    for name in (
        "qc_sid_available",
        "point_in_time",
        "independently_reviewed",
        "historical_availability_claimed",
    ):
        assert mapping[name] is False
        assert document["policy"][name] is False
    assert mapping["current_snapshot_identity_basis"] is True
    assert mapping["owner_accepted_current_snapshot_risk"] is True
    assert document["policy"]["current_snapshot_identity_basis"] is True
    assert document["policy"]["owner_accepted_current_snapshot_risk"] is True
    assert document["capabilities"] == {
        name: False for name in module._CAPABILITY_NAMES
    }
    assert module._address_is_current(
        document,
        identifier="admission_id",
        digest="admission_sha256",
        prefix="arv2-security-master-admission-",
    )


@pytest.mark.parametrize("field", sorted(module._SOURCE_KEYS))
def test_every_missing_source_field_has_its_own_named_refusal(field: str):
    row = _row()
    row.pop(field)
    document = _document(row)

    assert document["admitted_mappings"] == []
    assert document["census"]["named_refusal_count"] == 1
    assert f"missing_{field}" in _reason_codes(document)[0]


def test_unexpected_source_field_is_a_named_refusal():
    document = _document(_row(unreviewed_extra="must-not-pass"))
    assert _reason_codes(document) == [["unexpected_source_candidate_fields"]]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"security_id": "bad id"}, "invalid_security_id"),
        ({"issuer_id": "bad id"}, "invalid_issuer_id"),
        ({"source_composite_figi": "NOT-FIGI"}, "invalid_composite_figi"),
        ({"listing_id": "bad id"}, "invalid_listing_id"),
        ({"current_snapshot_ticker_display": "bad ticker"}, "invalid_current_snapshot_ticker"),
        ({"current_snapshot_listing_exchange": "ARCX"}, "invalid_current_snapshot_exchange"),
        ({"current_snapshot_sector_id": "bad id"}, "invalid_current_snapshot_sector_id"),
        ({"current_snapshot_industry_id": "bad id"}, "invalid_current_snapshot_industry_id"),
        ({"candidate_first_session": "01/02/2013"}, "invalid_candidate_first_session"),
        ({"candidate_last_session": "12/31/2025"}, "invalid_candidate_last_session"),
        ({"candidate_first_session": "2025-12-31", "candidate_last_session": "2013-01-02"}, "reversed_candidate_session_interval"),
        ({"source_row_sha256": "bad"}, "invalid_source_row_sha256"),
        ({"identity_evidence_sha256": "bad"}, "invalid_identity_evidence_sha256"),
        ({"classification_evidence_sha256": "bad"}, "invalid_classification_evidence_sha256"),
        ({"source_snapshot_available_at": "2026-09-14"}, "invalid_source_snapshot_available_at"),
        ({"sharadar_cusip_join_candidates": ["000000001", "000000001"]}, "invalid_or_duplicate_cusip_join_candidates"),
        ({"qc_security_id": "QC-SID"}, "unexpected_qc_security_id_claim"),
        ({"mapping_status": "resolved"}, "source_mapping_status_changed"),
        ({"membership_status": "PIT"}, "source_membership_risk_disclosure_changed"),
        ({"point_in_time": True}, "unexpected_point_in_time_claim"),
    ],
)
def test_each_invalid_or_overclaiming_field_has_distinct_named_refusal(
    changes: dict[str, object], reason: str
):
    document = _document(_row(**changes))
    assert document["admitted_mappings"] == []
    assert reason in _reason_codes(document)[0]


@pytest.mark.parametrize(
    ("second_changes", "reason"),
    [
        ({"current_snapshot_ticker_display": "AAA"}, "ambiguous_ticker_mapping"),
        ({"security_id": "sharadar-composite-figi-BBG000000001"}, "ambiguous_security_id_mapping"),
        ({"source_composite_figi": "BBG000000001"}, "ambiguous_composite_figi_mapping"),
        ({"listing_id": "sharadar-listing-aaaaaaaaaaaaaaaaaaaaaaaa"}, "ambiguous_listing_id_mapping"),
    ],
)
def test_each_identity_collision_refuses_every_group_member(
    second_changes: dict[str, object], reason: str
):
    document = _document(_row(), _second_row(**second_changes))
    assert document["admitted_mappings"] == []
    assert document["census"]["named_refusal_count"] == 2
    assert document["census"]["refusal_reason_counts"][reason] == 2
    assert all(reason in codes for codes in _reason_codes(document))


def test_exact_duplicate_refuses_both_occurrences_and_names_every_collision():
    row = _row()
    document = _document(row, dict(row))
    expected = {
        "duplicate_source_evidence",
        "ambiguous_ticker_mapping",
        "ambiguous_security_id_mapping",
        "ambiguous_composite_figi_mapping",
        "ambiguous_listing_id_mapping",
    }

    assert document["admitted_mappings"] == []
    assert all(set(codes) == expected for codes in _reason_codes(document))
    assert document["census"]["refusal_reason_counts"] == {
        reason: 2 for reason in sorted(expected)
    }


def test_structurally_bad_collision_taints_the_otherwise_valid_group_member():
    document = _document(
        _row(),
        _second_row(
            current_snapshot_ticker_display="AAA",
            qc_security_id="forbidden-claim",
        ),
    )
    assert document["admitted_mappings"] == []
    assert all(
        "ambiguous_ticker_mapping" in reasons
        for reasons in _reason_codes(document)
    )
    assert "unexpected_qc_security_id_claim" in _reason_codes(document)[1]


def test_named_refusal_is_content_addressed_and_cannot_carry_authority():
    refusal = _document(_row(point_in_time=True))["named_refusals"][0]
    assert refusal["mapping_admitted"] is False
    assert refusal["qc_sid_available"] is False
    assert refusal["point_in_time"] is False
    assert refusal["independently_reviewed"] is False
    assert refusal["historical_availability_claimed"] is False
    assert module._address_is_current(
        refusal,
        identifier="refusal_id",
        digest="refusal_sha256",
        prefix="arv2-security-master-refusal-",
    )


def test_source_candidate_count_mismatch_refuses_by_name():
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="source candidate census changed",
    ):
        module._compose_document((_row(),), _source(2))


def test_source_binding_shape_and_value_refusals_are_distinct():
    extra = _source()
    extra["unreviewed"] = True
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="source binding fields changed",
    ):
        module._compose_document((_row(),), extra)
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="source binding is invalid",
    ):
        module._compose_document(
            (_row(),), _source(source_snapshot_available_at="not-an-instant")
        )


def test_non_object_source_row_refuses_by_name():
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="source row is not an exact object",
    ):
        module._compose_document((object(),), _source())


def _refresh_admission(document: dict[str, object]) -> None:
    module._address_record(
        document,
        identifier="admission_id",
        digest="admission_sha256",
        prefix="arv2-security-master-admission-",
    )


def test_document_content_address_guard_is_isolated():
    document = _document(_row())
    document["census"]["admitted_mapping_count"] = 0
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="admission content address changed",
    ):
        module._require_document(document)


def test_document_policy_and_capability_guards_are_isolated():
    policy = _document(_row())
    policy["policy"]["qc_sid_available"] = True
    _refresh_admission(policy)
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="admission policy changed",
    ):
        module._require_document(policy)

    capability = _document(_row())
    capability["capabilities"]["quantconnect_access"] = True
    _refresh_admission(capability)
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="capabilities changed",
    ):
        module._require_document(capability)


def test_admitted_mapping_risk_and_overlap_guards_are_isolated():
    risk = _document(_row())
    risk["admitted_mappings"][0]["point_in_time"] = True
    _refresh_admission(risk)
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="mapping risk flags changed",
    ):
        module._require_document(risk)

    overlap = _document(_row(), _second_row())
    overlap["admitted_mappings"][1]["ticker"] = overlap["admitted_mappings"][0][
        "ticker"
    ]
    _refresh_admission(overlap)
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="admitted mappings overlap",
    ):
        module._require_document(overlap)


def test_refusal_status_and_census_guards_are_isolated():
    status = _document(_row(point_in_time=True))
    refusal = status["named_refusals"][0]
    refusal["mapping_admitted"] = True
    module._address_record(
        refusal,
        identifier="refusal_id",
        digest="refusal_sha256",
        prefix="arv2-security-master-refusal-",
    )
    _refresh_admission(status)
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="refusal status changed",
    ):
        module._require_document(status)

    census = _document(_row())
    census["census"]["admitted_mapping_count"] = 0
    _refresh_admission(census)
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="disposition census changed",
    ):
        module._require_document(census)


def test_source_row_bound_refuses_before_silent_truncation(monkeypatch):
    monkeypatch.setattr(module, "MAX_SOURCE_ROWS", 1)
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="source exceeds row bound",
    ):
        module._compose_document((_row(), _second_row()), _source(1))


@pytest.fixture(scope="module")
def physical_context(tmp_path_factory):
    root = tmp_path_factory.mktemp("security-master-admission")
    _massive, c1, sharadar = _sources(root)
    seed = _build_physical_preopen_seed_archive_for_test(
        c1, sharadar, root / "preopen-seed"
    )
    artifact = build_accepted_risk_security_master_admission(seed)
    return seed, artifact


def test_physical_seed_builds_exact_process_authority(physical_context):
    seed, artifact = physical_context
    second = build_accepted_risk_security_master_admission(seed)

    assert type(artifact) is AcceptedRiskSecurityMasterAdmission
    assert require_accepted_risk_security_master_admission(artifact) is artifact
    assert artifact.admission_id == second.admission_id
    assert artifact.admission_sha256 == second.admission_sha256
    assert artifact.document_bytes == second.document_bytes
    assert artifact.seed_archive_id == seed.archive_id
    assert artifact.seed_archive_sha256 == seed.archive_sha256
    assert artifact.source_candidate_count == seed.candidate_security_count == 2
    assert artifact.admitted_mapping_count == 2
    assert artifact.named_refusal_count == 0
    assert artifact.refusal_reason_counts == ()
    assert artifact.payload_sha256 == sha256_bytes(artifact.document_bytes)
    assert artifact.qc_sid_available is False
    assert artifact.point_in_time is False
    assert artifact.independently_reviewed is False
    assert artifact.historical_availability_claimed is False
    assert artifact.current_snapshot_identity_basis is True
    assert artifact.owner_accepted_current_snapshot_risk is True
    assert all(getattr(artifact, name) is False for name in module._CAPABILITY_NAMES)


def test_physical_mapping_iterator_exposes_only_admitted_rows(physical_context):
    _seed, artifact = physical_context
    mappings = tuple(iter_accepted_risk_security_master_mappings(artifact))
    refusals = tuple(iter_accepted_risk_security_master_refusals(artifact))

    assert len(mappings) == artifact.admitted_mapping_count
    assert refusals == ()
    assert [row["ticker"] for row in mappings] == sorted(
        row["ticker"] for row in mappings
    )
    assert all(row["qc_security_id"] is None for row in mappings)


def test_physical_source_snapshot_missing_and_ambiguity_refuse_distinctly(
    physical_context,
):
    seed, _artifact = physical_context
    rows = tuple(iter_physical_universe_candidates(seed))
    missing = tuple(
        {**row, "source_snapshot_available_at": None} for row in rows
    )
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="source snapshot binding is missing",
    ):
        module._source_binding(seed, missing)

    ambiguous = list(rows)
    ambiguous[1] = {
        **ambiguous[1],
        "source_snapshot_available_at": "2026-09-15T00:00:00+00:00",
    }
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="source snapshot binding is ambiguous",
    ):
        module._source_binding(seed, tuple(ambiguous))


def test_document_byte_bound_refuses_without_truncation(physical_context, monkeypatch):
    seed, _artifact = physical_context
    monkeypatch.setattr(module, "MAX_DOCUMENT_BYTES", 1)
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="admission exceeds byte bound",
    ):
        build_accepted_risk_security_master_admission(seed)


def test_equal_dataclass_copy_is_not_builder_authority(physical_context):
    _seed, artifact = physical_context
    clone = dataclasses.replace(artifact)
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="not current builder authority",
    ):
        require_accepted_risk_security_master_admission(clone)


def test_exact_parent_type_is_checked_before_parent_access():
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="requires exact physical seed type",
    ):
        build_accepted_risk_security_master_admission(object())


def test_dependency_rebinding_refuses_before_parent_access(physical_context, monkeypatch):
    _seed_value, artifact = physical_context
    monkeypatch.setattr(
        module._seed,
        "iter_physical_universe_candidates",
        lambda _value: iter(()),
    )
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="dependency binding changed",
    ):
        require_accepted_risk_security_master_admission(artifact)


def test_authority_cannot_cross_process(physical_context, monkeypatch):
    _seed, artifact = physical_context
    owner_pid = os.getpid()
    monkeypatch.setattr(module.os, "getpid", lambda: owner_pid + 1)
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="not current process authority",
    ):
        require_accepted_risk_security_master_admission(artifact)


def test_payload_mutation_cannot_become_authority(physical_context):
    _seed, artifact = physical_context
    document = json.loads(artifact.document_bytes)
    document["policy"]["qc_sid_available"] = True
    forged = dataclasses.replace(
        artifact,
        document_bytes=canonical_json_bytes(document),
        payload_sha256=sha256_bytes(canonical_json_bytes(document)),
    )
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="not current builder authority",
    ):
        require_accepted_risk_security_master_admission(forged)


def test_registered_payload_hash_mutation_is_refused_by_payload_guard(
    physical_context,
):
    _seed, artifact = physical_context
    clone = dataclasses.replace(artifact, payload_sha256="0" * 64)
    parent_authority = module._AUTHORITIES[id(artifact)]
    reference = weakref.ref(clone)
    module._AUTHORITIES[id(clone)] = (
        reference,
        module._fingerprint(clone),
        parent_authority[2],
        parent_authority[3],
    )
    try:
        with pytest.raises(
            AcceptedRiskSecurityMasterAdmissionError,
            match="payload binding changed",
        ):
            require_accepted_risk_security_master_admission(clone)
    finally:
        module._AUTHORITIES.pop(id(clone), None)


def test_physical_parent_mutation_is_refused_by_name(tmp_path):
    _massive, c1, sharadar = _sources(tmp_path)
    seed = _build_physical_preopen_seed_archive_for_test(
        c1, sharadar, tmp_path / "preopen-seed"
    )
    artifact = build_accepted_risk_security_master_admission(seed)
    universe = next(
        item for item in seed.shards if item.role == "universe_candidates"
    )
    with (seed.archive_path / universe.relative_path).open("ab") as handle:
        handle.write(b"\n")
    with pytest.raises(
        AcceptedRiskSecurityMasterAdmissionError,
        match="physical seed did not reauthenticate",
    ):
        require_accepted_risk_security_master_admission(artifact)


def test_security_admission_does_not_import_or_reuse_firm_waiver():
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "firm_ontology_owner_decision" not in source
    assert "FirmOntologyOwnerDecision" not in source
