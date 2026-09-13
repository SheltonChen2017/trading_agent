from __future__ import annotations

import dataclasses
import json
import os
import types
from pathlib import Path

import pytest

from research.analyst_revisions_v2 import firm_ontology as firm_module
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from research.analyst_revisions_v2.firm_ontology import (
    FIRM_ONTOLOGY_SCHEMA,
    FirmRatingMapEntry,
    MappingQuality,
    RatingScope,
    ReviewedFirmRatingOntology,
)
from research.analyst_revisions_v2.preopen_control_acquisition import (
    PreopenControlAcquisitionError,
)
from research.analyst_revisions_v2.production_input_pipeline import (
    AdmissionDisposition,
    EvidenceSourceKind,
    SignalArm,
    build_production_input_batch,
)
from research.analyst_revisions_v2_qc import production_evidence_composer as composer
from research.analyst_revisions_v2_qc import formal_streaming_input as streaming
from research.analyst_revisions_v2_qc.formal_streaming_input import (
    FormalStreamingRunRefusal,
    iter_physical_preopen_terminal_sessions,
    load_physical_production_evidence_terminal_archive,
    require_physical_production_evidence_terminal_archive,
)
from tests.analyst_revisions_v2.test_production_scoring import (
    EARLY,
    SOURCE_HASHES,
    SOURCE_IDS,
    _c2_pair,
    _census_row,
    _install_offline_physical_receipt_requires,
    _offline_physical_requirer,
    _PRODUCTION_PREOPEN_REQUIRE,
    _truth_artifact,
)


LABELS = ("Sell", "Underweight", "Hold", "Buy", "Strong Buy")


@pytest.fixture(autouse=True)
def _install_composer_offline_physical_receipt_requires(
    monkeypatch,
    _install_offline_physical_receipt_requires,
):
    """Route only this module's imported aliases to the test authority."""

    require_preopen = lambda value: _offline_physical_requirer(
        "preopen", value
    )
    monkeypatch.setattr(
        composer,
        "require_reviewed_preopen_control_acquisition_receipt",
        require_preopen,
    )
    monkeypatch.setattr(
        streaming,
        "require_reviewed_preopen_control_acquisition_receipt",
        require_preopen,
    )


def _ontology(*, omit_firm: int | None = None) -> ReviewedFirmRatingOntology:
    entries = []
    for index in range(20):
        if index == omit_firm:
            continue
        for rank, label in enumerate(LABELS, start=1):
            entries.append(FirmRatingMapEntry(
                provider_firm_id=f"firm-{index:02d}",
                firm_name=f"Firm {index:02d}",
                valid_from="2013-01-02",
                valid_to=None,
                raw_label=label,
                ordered_rank=rank,
                scale_size=len(LABELS),
                scope=RatingScope.COMPANY_RELATIVE,
                mapping_quality=MappingQuality.REVIEWED_PRIMARY,
                reviewer="offline-test-reviewer",
                source_evidence_id=f"firm-scale-source-{index:02d}",
                source_evidence_sha256=sha256_bytes(
                    canonical_json_bytes(["firm-scale", index])
                ),
            ))
    entries.sort(key=lambda item: (
        item.provider_firm_id, item.valid_from, "9999-12-31",
        item.ordered_rank, item.raw_label.casefold(), item.raw_label,
    ))
    value = object.__new__(ReviewedFirmRatingOntology)
    fields = {
        "schema": FIRM_ONTOLOGY_SCHEMA,
        "ontology_id": SOURCE_IDS[EvidenceSourceKind.FIRM_ONTOLOGY],
        "version": "offline-composer-fixture-v1",
        "status": "independently_reviewed",
        "reviewed_at": "2026-09-12T12:00:00.000000Z",
        "entries": tuple(entries),
        "payload_sha256": SOURCE_HASHES[EvidenceSourceKind.FIRM_ONTOLOGY],
        "source_path": "/private/tmp/offline-composer-fixture-never-read.json",
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    return value


def _availability(monkeypatch, tmp_path: Path, ontology, *, late_firm=None):
    monkeypatch.setattr(
        firm_module,
        "require_registered_production_firm_ontology",
        lambda value: value,
    )
    entries = []
    for entry in ontology.entries:
        available = (
            "2020-01-06T14:30:00.000000Z"
            if late_firm is not None
            and entry.provider_firm_id == f"firm-{late_firm:02d}"
            else EARLY
        )
        entries.append({
            "ontology_entry_sha256": sha256_bytes(
                canonical_json_bytes(entry.to_record())
            ),
            "source_evidence_id": entry.source_evidence_id,
            "source_evidence_sha256": entry.source_evidence_sha256,
            "available_at": available,
            "valid_to_available_at": None,
        })
    entries.sort(key=lambda item: item["ontology_entry_sha256"])
    payload = canonical_json_bytes({
        "schema": composer.FIRM_AVAILABILITY_SCHEMA,
        "ontology_id": ontology.ontology_id,
        "ontology_sha256": ontology.payload_sha256,
        "entries": entries,
    })
    availability_path = tmp_path / "firm-availability.json"
    availability_path.write_bytes(payload)
    os.chmod(availability_path, 0o600)
    seed = {
        "schema": composer.FIRM_AVAILABILITY_REVIEW_SCHEMA,
        "availability_sha256": sha256_bytes(payload),
        "availability_byte_count": len(payload),
        "ontology_id": ontology.ontology_id,
        "ontology_sha256": ontology.payload_sha256,
        "entry_count": len(entries),
        "entry_projection_sha256": sha256_bytes(canonical_json_bytes(entries)),
        "status": composer.FIRM_AVAILABILITY_REVIEW_STATUS,
        "receipt_id": None,
        "receipt_sha256": None,
        "complete_ontology_entry_census_verified": True,
        "historical_availability_verified_from_external_source_evidence": True,
        "no_review_time_or_valid_from_imputation_verified": True,
        "contains_outcome_or_price": False,
    }
    digest = sha256_bytes(canonical_json_bytes(seed))
    review = {
        **seed,
        "receipt_id": f"arv2-firm-availability-review-{digest[:24]}",
        "receipt_sha256": digest,
    }
    review_path = tmp_path / "firm-availability-review.json"
    review_path.write_bytes(canonical_json_bytes(review))
    os.chmod(review_path, 0o600)
    return composer.load_reviewed_firm_ontology_availability(
        ontology=ontology,
        availability_path=availability_path,
        review_path=review_path,
    ), availability_path, review_path


def _sidecar_record(source, terminal, *, mapping_available_at=None):
    semantic = {
        "schema": "arv2-reviewed-historical-analyst-event-binding-v1",
        "locator_sha256": sha256_bytes(canonical_json_bytes(source.locator.to_record())),
        "raw_row_sha256": source.locator.raw_row_sha256,
        "provider_event_id": source.provider_event_id,
        "common_event_id": "benzinga-event-" + source.provider_event_id,
        "source_role": "analyst_ratings",
        "current_view_disposition": source.current_view.disposition.value,
        "censored_view_disposition": source.censored_view.disposition.value,
        "preopen_composition_disposition": "included",
        "preopen_composition_reason": None,
        "physical_security_id": terminal.security_id,
        "decision_session": terminal.decision_session,
        "decision_session_ordinal": 1,
        "available_at": source.current_view.eligible_at,
        "rating_admitted": True,
        "rating_seed_row_sha256": sha256_bytes(source.raw_row_bytes),
        "binding_disposition": "accepted",
        "binding_reason": None,
        "qc_security_id": terminal.historical_ticker + " R735QTJ8XC9X",
        "cusip": f"{int(source.provider_event_id[-2:]):09d}",
        "issuer_id": terminal.issuer_id,
        "share_class_id": terminal.share_class_id,
        "listing_id": terminal.listing_id,
        "historical_ticker": terminal.historical_ticker,
        "mapping_first_session": "2013-01-02",
        "mapping_last_session": "2025-12-31",
        "mapping_available_at": mapping_available_at or terminal.identity_available_at,
        "mapping_closure_available_at": None,
        "mapping_row_sha256": sha256_bytes(
            canonical_json_bytes(["mapping", terminal.security_id])
        ),
        "q_data": str(terminal.q_data),
        "q_data_evidence_sha256": terminal.q_data_evidence_sha256,
    }
    return {**semantic, "binding_sha256": sha256_bytes(canonical_json_bytes(semantic))}


def _fixture(
    monkeypatch,
    tmp_path: Path,
    *,
    omit_sidecar: int | None = None,
    duplicate_sidecar: int | None = None,
    upstream_refusal: int | None = None,
    omit_firm: int | None = None,
    late_mapping: int | None = None,
    late_firm: int | None = None,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    current, censored, _labels = _c2_pair()
    census = tuple(_census_row("2020-01-06", index) for index in range(20))
    truth, payload = _truth_artifact(current, censored, census, return_payload=True)
    preopen = truth.preopen_acquisition_receipt
    physical_path = tmp_path / "physical-preopen.jsonl.gz"
    physical_path.write_bytes(payload)
    os.chmod(physical_path, 0o600)
    archive = load_physical_production_evidence_terminal_archive(
        preopen_acquisition_receipt=preopen,
        shard_paths=(physical_path,),
    )
    terminals = {
        item.security_id: item
        for block in iter_physical_preopen_terminal_sessions(archive)
        for item in block.accepted
    }
    pair = current.evidence_authority.pair
    rating_sources = [
        item for item in pair.rows if item.locator.source_role.value == "analyst_ratings"
    ]
    sidecars = []
    for index, source in enumerate(rating_sources):
        if index == omit_sidecar:
            continue
        row = _sidecar_record(
            source,
            terminals[f"security-{index:02d}"],
            mapping_available_at=(
                "2020-01-06T14:30:00.000000Z" if index == late_mapping else None
            ),
        )
        if index == upstream_refusal:
            semantic = dict(row)
            semantic.pop("binding_sha256")
            semantic["binding_disposition"] = "named_refusal"
            semantic["binding_reason"] = (
                "analyst_event_has_no_same_session_universe_quality_binding"
            )
            semantic["q_data"] = None
            semantic["q_data_evidence_sha256"] = None
            row = {
                **semantic,
                "binding_sha256": sha256_bytes(canonical_json_bytes(semantic)),
            }
        sidecars.append(row)
        if index == duplicate_sidecar:
            sidecars.append(dict(row))
    payload_lines = b"".join(canonical_json_bytes(item) for item in sidecars)
    shard = types.SimpleNamespace(
        ordinal=0,
        row_count=len(sidecars),
        compressed_sha256=sha256_bytes(b"synthetic-compressed-sidecar"),
        compressed_byte_count=1,
        uncompressed_sha256=sha256_bytes(payload_lines),
        uncompressed_byte_count=len(payload_lines),
        canonical_json_lines=payload_lines,
    )
    truth_sources = {
        kind: (artifact_id, digest)
        for kind, artifact_id, digest in preopen.truth_source_bindings
    }
    bridge = types.SimpleNamespace(
        bridge_id="synthetic-reviewed-historical-bridge",
        bridge_sha256=sha256_bytes(b"synthetic-reviewed-historical-bridge"),
        pair_id=pair.pair_id,
        pair_sha256=pair.pair_sha256,
        derived_capture_id=pair.capture.capture_id,
        derived_capture_sha256=pair.capture.capture_sha256,
        closed_input_manifest_sha256=preopen.input_manifest_sha256,
        input_shard_inventory_sha256=preopen.input_source_inventory_sha256,
        accepted_risk_bridge_id=truth_sources["accepted_risk_capture"][0],
        accepted_risk_bridge_sha256=truth_sources["accepted_risk_capture"][1],
        discovery_eligible_universe_artifact_id=truth_sources["eligible_universe"][0],
        discovery_eligible_universe_artifact_sha256=truth_sources["eligible_universe"][1],
        security_master_artifact_id=truth_sources["security_master"][0],
        security_master_artifact_sha256=truth_sources["security_master"][1],
        physical_candidate_id=truth_sources["preopen_control"][0],
        physical_candidate_sha256=truth_sources["preopen_control"][1],
        first_session=preopen.control_sessions[0].decision_session,
        last_session=preopen.control_sessions[-1].decision_session,
        analyst_event_binding_row_count=len(sidecars),
    )
    monkeypatch.setattr(
        composer.historical_module,
        "require_reviewed_historical_universe_to_preopen_bridge",
        lambda value: value,
    )
    monkeypatch.setattr(
        composer.historical_module,
        "iter_reviewed_historical_analyst_event_binding_shards",
        lambda _value: iter((shard,)),
    )
    ontology = _ontology(omit_firm=omit_firm)
    availability, availability_path, review_path = _availability(
        monkeypatch, tmp_path, ontology, late_firm=late_firm
    )
    return types.SimpleNamespace(
        pair=pair,
        bridge=bridge,
        ontology=ontology,
        availability=availability,
        availability_path=availability_path,
        review_path=review_path,
        preopen=preopen,
        archive=archive,
        physical_path=physical_path,
    )


def _build(fixture):
    return composer.build_physical_production_evidence_candidate(
        pair=fixture.pair,
        historical_bridge=fixture.bridge,
        firm_ontology=fixture.ontology,
        firm_availability=fixture.availability,
        preopen_acquisition_receipt=fixture.preopen,
        terminal_archive=fixture.archive,
    )


def test_physical_composer_builds_exhaustive_package_and_admissible_batch(
    monkeypatch, tmp_path
):
    fixture = _fixture(monkeypatch, tmp_path)
    candidate = _build(fixture)
    batch = build_production_input_batch(
        candidate.authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )

    assert composer.require_physical_production_evidence_candidate(candidate) is candidate
    assert candidate.candidate_rating_row_count == 20
    assert candidate.sidecar_row_count == 20
    assert candidate.physical_terminal_count == 20
    assert len(candidate.authority.row_evidence) == 20
    assert batch.normalized_row_count == 20
    assert all(
        item.disposition
        is AdmissionDisposition.INCLUDED_DIRECTIONAL_RATING_REVISION
        for item in batch.admissions
        if item.source_role.value == "analyst_ratings"
    )
    assert candidate.production_evidence_receipt_available is False
    assert json.loads(candidate.external_review_pin_candidate_bytes)["status"] == (
        "review_required_not_authorized"
    )


def test_composer_test_authority_never_satisfies_production_require(
    monkeypatch, tmp_path,
):
    fixture = _fixture(monkeypatch, tmp_path)
    assert _offline_physical_requirer("preopen", fixture.preopen) is (
        fixture.preopen
    )
    with pytest.raises(
        PreopenControlAcquisitionError,
        match="loader-authenticated",
    ):
        _PRODUCTION_PREOPEN_REQUIRE(fixture.preopen)


def test_missing_ambiguous_security_and_missing_firm_are_never_dropped(
    monkeypatch, tmp_path
):
    missing = _build(_fixture(monkeypatch, tmp_path / "missing", omit_sidecar=0))
    assert len(missing.authority.row_evidence) == 20
    assert missing.composition_terminals[0].security == "missing"
    missing_batch = build_production_input_batch(
        missing.authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    assert missing_batch.admissions[0].disposition is (
        AdmissionDisposition.MISSING_PIT_SECURITY_EVIDENCE
    )

    ambiguous = _build(
        _fixture(monkeypatch, tmp_path / "ambiguous", duplicate_sidecar=0)
    )
    assert ambiguous.composition_terminals[0].security == "ambiguous"
    assert len(ambiguous.authority.row_evidence) == 20

    no_firm = _build(_fixture(monkeypatch, tmp_path / "firm", omit_firm=0))
    no_firm_batch = build_production_input_batch(
        no_firm.authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    assert no_firm.composition_terminals[0].firm == "unreviewed_or_unavailable"
    assert no_firm_batch.admissions[0].disposition is (
        AdmissionDisposition.MISSING_FIRM_ONTOLOGY_EVIDENCE
    )

    upstream_refusal = _build(
        _fixture(monkeypatch, tmp_path / "control", upstream_refusal=0)
    )
    terminal = upstream_refusal.composition_terminals[0]
    assert terminal.security == "upstream_named_refusal"
    assert terminal.control == "upstream_named_refusal"
    assert terminal.q_data == "upstream_named_refusal"
    assert len(upstream_refusal.authority.row_evidence) == 20


def test_historical_availability_and_mapping_cutoff_are_not_backfilled(
    monkeypatch, tmp_path
):
    late_firm = _build(_fixture(monkeypatch, tmp_path / "firm", late_firm=0))
    batch = build_production_input_batch(
        late_firm.authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    assert batch.admissions[0].disposition is AdmissionDisposition.FIRM_MAPPING_LATE

    late_mapping = _build(
        _fixture(monkeypatch, tmp_path / "mapping", late_mapping=0)
    )
    batch = build_production_input_batch(
        late_mapping.authority, signal_arm=SignalArm.CURRENT_VINTAGE
    )
    assert batch.admissions[0].disposition is AdmissionDisposition.SECURITY_IDENTITY_LATE


def test_cross_parent_substitution_is_rejected(monkeypatch, tmp_path):
    fixture = _fixture(monkeypatch, tmp_path)
    fixture.bridge.closed_input_manifest_sha256 = "f" * 64
    with pytest.raises(composer.ProductionEvidenceComposerError, match="lineage"):
        _build(fixture)


def test_availability_symlink_and_post_load_mutation_are_rejected(
    monkeypatch, tmp_path
):
    fixture = _fixture(monkeypatch, tmp_path / "base")
    alias = tmp_path / "availability-link.json"
    alias.symlink_to(fixture.availability_path)
    with pytest.raises(composer.ProductionEvidenceComposerError, match="unavailable|regular"):
        composer.load_reviewed_firm_ontology_availability(
            ontology=fixture.ontology,
            availability_path=alias,
            review_path=fixture.review_path,
        )

    fixture.availability_path.write_bytes(fixture.availability_path.read_bytes() + b" ")
    with pytest.raises(composer.ProductionEvidenceComposerError, match="changed"):
        composer.require_reviewed_firm_ontology_availability(fixture.availability)


def test_physical_archive_mutation_and_fixed_capacity_refuse(
    monkeypatch, tmp_path
):
    fixture = _fixture(monkeypatch, tmp_path / "mutation")
    fixture.physical_path.write_bytes(fixture.physical_path.read_bytes() + b"x")
    with pytest.raises((composer.ProductionEvidenceComposerError, FormalStreamingRunRefusal)):
        require_physical_production_evidence_terminal_archive(fixture.archive)

    capacity_fixture = _fixture(monkeypatch, tmp_path / "capacity")
    monkeypatch.setattr(composer, "MAX_COMPOSER_SIDECAR_ROW_COUNT", 0)
    with pytest.raises(
        composer.ProductionEvidenceComposerCapacityRefusal, match="sidecar row census"
    ):
        _build(capacity_fixture)
