from __future__ import annotations

import dataclasses
import copy
import hashlib
import json
import os
import sys
import tempfile
import types
import weakref
from datetime import date
from decimal import Context, Decimal, ROUND_DOWN, localcontext
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2.accepted_risk_input_pair import (
    MassiveSourceRole,
    bind_capture_page,
    build_accepted_risk_input_pair,
    build_capture_binding,
    render_redacted_capture_query_bytes,
)
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from research.analyst_revisions_v2.global_benchmark_contract import (
    load_global_benchmark_contract,
)
from research.analyst_revisions_v2.production_input_pipeline import (
    CommonEventIdentityEvidence,
    DataQualityEvidence,
    EvidenceSourceBinding,
    EvidenceSourceKind,
    FirmOntologyEvidence,
    PreopenControlEvidence,
    ProductionRowEvidence,
    SectorClassificationEvidence,
    SecurityIdentityEvidence,
    SignalArm,
    build_production_evidence_authority,
    build_production_input_batch,
)
from research.analyst_revisions_v2.production_evidence_acquisition import (
    ProductionEvidenceAcquisitionError,
    require_production_evidence_acquisition_receipt,
    render_production_evidence_external_review_pin_candidate,
    render_production_evidence_owner_review_payload_candidate,
    render_production_evidence_package_bytes,
)
import research.analyst_revisions_v2.production_evidence_acquisition as evidence_core
import research.analyst_revisions_v2.production_scoring as module
from research.analyst_revisions_v2.production_scoring import (
    BINARY_COLUMNS,
    SCORING_CONTRACT_ID,
    SCORING_CONTRACT_SHA256,
    CONTINUOUS_COLUMNS,
    CensusRefusalReason,
    EligibleSecuritySession,
    EndpointLabelEvidence,
    FoldPartition,
    ProductionControlVector,
    ProductionScoringAuthority,
    ProductionScoringError,
    ProductionScoringFold,
    ScoreState,
    apply_production_control_models,
    build_eligible_security_session,
    build_eligible_security_session_refusal,
    build_endpoint_label_evidence,
    build_formal_production_scoring_fold,
    build_precontrol_scoring_batch,
    build_production_scoring_authority,
    fit_production_control_models,
    formal_horizon_fold_boundary,
    require_precontrol_scoring_batch,
    require_production_scoring_authority,
    require_production_scoring_result,
    render_scoring_contract_bytes,
)
from research.analyst_revisions_v2.production_truth_gate import (
    FORMAL_SESSION_GEOMETRY,
    ProductionTruthArtifact,
    ProductionTruthError,
    QualityComponentKind,
    TruthSourceKind,
    build_derived_data_quality_evidence,
    build_production_truth_artifact,
    build_production_truth_source_binding,
    build_quality_component_evidence,
    derive_c2_quality_component_projections,
    project_c2_data_quality_evidence,
    quality_measurement_projection_sha256,
    render_production_truth_artifact_bytes,
    require_production_truth_artifact,
)
import research.analyst_revisions_v2.production_truth_gate as truth_module
from research.analyst_revisions_v2.preopen_control_acquisition import (
    CONTROL_SESSION_COMMITMENT_SCHEMA,
    OUTPUT_TERMINAL_SCHEMA,
    REVIEW_RECEIPT_SCHEMA,
    UNIVERSE_SESSION_COMMITMENT_SCHEMA,
)
import research.analyst_revisions_v2.preopen_control_acquisition as preopen_core
from research.analyst_revisions_v2_qc.preopen_control_acquisition_io import (
    load_physically_reviewed_preopen_control_acquisition_receipt,
    render_preopen_control_external_review_pin_candidate,
    render_preopen_qc_execution_receipt,
)
from research.analyst_revisions_v2_qc.preopen_control_stage import (
    CONSTRUCTION_INTERMEDIATE_SCHEMA,
    build_preopen_output_manifest_bytes,
    build_preopen_output_shard,
)
from research.analyst_revisions_v2_qc.production_evidence_acquisition_io import (
    ProductionEvidenceAcquisitionIoError,
    load_physically_reviewed_production_evidence_receipt,
)
import research.analyst_revisions_v2_qc.production_evidence_acquisition_io as production_evidence_io
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    OwnerSignatureAuthority,
)


SPEC_ROOT = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "analyst_revisions_v2"
    / "specs"
)
FILENAMES = {
    "map": "arv2_global_rating_map.structural.json",
    "matched": "arv2_global_matched_comparison.structural.json",
    "successor": "arv2_stock_historical_successor.structural.json",
    "stock": "arv2_stock_historical.structural.json",
    "folds": "arv2_stock_walk_forward_folds.structural.json",
    "plan": "arv2_qc_first.draft.json",
}
STARTED = "2026-09-11T18:00:00.000000Z"
COMPLETED = "2026-09-11T18:04:00.000000Z"
EARLY = "2020-01-06T14:00:00.000000Z"
FIRST = "2011-01-01"
LAST = "2025-12-31"
SOURCE_HASHES = {
    kind: hashlib.sha256(kind.value.encode()).hexdigest()
    for kind in EvidenceSourceKind
}
SOURCE_IDS = {kind: f"scoring-{kind.value}-1" for kind in EvidenceSourceKind}


def _closure_cell(value: object):
    def capture():
        return value

    assert capture.__closure__ is not None
    return capture.__closure__[0]


def _with_closure_value(function, name: str, value: object):
    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    assert name in cells
    rebound = types.FunctionType(
        function.__code__,
        function.__globals__,
        function.__name__,
        function.__defaults__,
        tuple(
            _closure_cell(value) if freevar == name else cells[freevar]
            for freevar in function.__code__.co_freevars
        ),
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    rebound.__annotations__ = function.__annotations__
    return rebound


def _offline_owner_signature() -> OwnerSignatureAuthority:
    value = object.__new__(OwnerSignatureAuthority)
    object.__setattr__(value, "authority_sha256", "a" * 64)
    return value


_OFFLINE_PHYSICAL_AUTHORITIES = {
    "preopen": {},
    "evidence": {},
}
_PRODUCTION_PREOPEN_REQUIRE = (
    preopen_core.require_reviewed_preopen_control_acquisition_receipt
)
_PRODUCTION_EVIDENCE_REQUIRE = (
    evidence_core.require_production_evidence_acquisition_receipt
)


def _offline_physical_requirer(kind, value):
    record = _OFFLINE_PHYSICAL_AUTHORITIES[kind].get(id(value))
    authority = None
    if record is not None and record[0] == os.getpid():
        authority = record[1]
    production_require = (
        _PRODUCTION_EVIDENCE_REQUIRE
        if kind == "evidence"
        else _PRODUCTION_PREOPEN_REQUIRE
    )
    require_cells = dict(zip(
        production_require.__code__.co_freevars,
        production_require.__closure__,
        strict=True,
    ))
    return require_cells["require_implementation"].cell_contents(
        value,
        authority,
    )


@pytest.fixture(autouse=True)
def _install_offline_physical_receipt_requires(monkeypatch):
    """Keep synthetic physical receipts in a test-only authority domain."""

    for records in _OFFLINE_PHYSICAL_AUTHORITIES.values():
        records.clear()
    require_preopen = lambda value: _offline_physical_requirer(
        "preopen", value
    )
    require_evidence = lambda value: _offline_physical_requirer(
        "evidence", value
    )
    monkeypatch.setattr(
        preopen_core,
        "require_reviewed_preopen_control_acquisition_receipt",
        require_preopen,
    )
    monkeypatch.setattr(
        evidence_core,
        "require_reviewed_preopen_control_acquisition_receipt",
        require_preopen,
    )
    monkeypatch.setattr(
        truth_module,
        "require_reviewed_preopen_control_acquisition_receipt",
        require_preopen,
    )
    monkeypatch.setattr(
        truth_module,
        "require_production_evidence_acquisition_receipt",
        require_evidence,
    )
    yield
    for records in _OFFLINE_PHYSICAL_AUTHORITIES.values():
        records.clear()


def _offline_signed_loader(function):
    """Exercise physical validation, then mint only test-local authority."""

    def require_typed_owner_signature(value, *, authority_payload):
        assert type(value) is OwnerSignatureAuthority
        assert type(authority_payload) is bytes and authority_payload
        return value

    loader_cells = dict(zip(
        function.__code__.co_freevars,
        function.__closure__,
        strict=True,
    ))
    implementation = loader_cells["implementation"].cell_contents
    production_minter = loader_cells["receipt_minter"].cell_contents
    minter_cells = dict(zip(
        production_minter.__code__.co_freevars,
        production_minter.__closure__,
        strict=True,
    ))
    raw_mint = minter_cells["mint_implementation"].cell_contents
    fingerprint = minter_cells["fingerprint"].cell_contents
    kind = (
        "evidence"
        if function.__name__
        == "load_physically_reviewed_production_evidence_receipt"
        else "preopen"
    )

    def load(**kwargs):
        verified = implementation(
            **kwargs,
            require_owner_signature=require_typed_owner_signature,
        )
        if kind == "evidence":
            value = raw_mint(
                authority=verified[0],
                preopen_acquisition_receipt=verified[1],
                package_bytes=verified[2],
                review_pin_bytes=verified[3],
            )
        else:
            value = raw_mint(
                output_manifest_bytes=verified[0],
                independent_review_receipt_bytes=verified[1],
                qc_execution_receipt_id=verified[2],
                qc_execution_receipt_sha256=verified[3],
                external_review_pin_id=verified[4],
                external_review_pin_sha256=verified[5],
                output_shard_payload_projection_sha256=verified[6],
            )
        reference = weakref.ref(
            value,
            lambda _ref, category=kind, key=id(value): (
                _OFFLINE_PHYSICAL_AUTHORITIES[category].pop(key, None)
            ),
        )
        _OFFLINE_PHYSICAL_AUTHORITIES[kind][id(value)] = (
            os.getpid(),
            (reference, fingerprint(value)),
        )
        return _offline_physical_requirer(kind, value)

    return load


def _global_contract():
    return load_global_benchmark_contract(
        map_path=SPEC_ROOT / FILENAMES["map"],
        matched_contract_path=SPEC_ROOT / FILENAMES["matched"],
        successor_spec_path=SPEC_ROOT / FILENAMES["successor"],
        parent_stock_spec_path=SPEC_ROOT / FILENAMES["stock"],
        fold_manifest_path=SPEC_ROOT / FILENAMES["folds"],
        qc_first_plan_path=SPEC_ROOT / FILENAMES["plan"],
    )


def _control_vector(seed: int) -> ProductionControlVector:
    values = []
    for index, name in enumerate(CONTINUOUS_COLUMNS):
        digest = hashlib.sha256(f"{seed}:{index}".encode()).digest()
        value = int.from_bytes(digest[:6], "big") % 1_000_003 + 1
        values.append((name, Decimal(value)))
    for index, name in enumerate(BINARY_COLUMNS):
        digest = hashlib.sha256(f"binary:{seed}:{index}".encode()).digest()
        values.append((name, int(digest[0] & 1)))
    return ProductionControlVector(tuple(values))


def _census_row(session: str, index: int) -> EligibleSecuritySession:
    controls = _control_vector(index + int(session[-2:]) * 1000)
    return build_eligible_security_session(
        decision_session=session,
        security_id=f"security-{index:02d}",
        issuer_id=f"issuer-{index:02d}",
        share_class_id=f"share-{index:02d}",
        listing_id=f"listing-{index:02d}",
        historical_ticker=f"S{index:02d}",
        sector_id="sector-one",
        industry_id="industry-one" if index < 10 else "industry-two",
        q_data=Decimal("0.9"),
        controls=controls,
        source_id="pit-census-source-1",
        source_sha256="a" * 64,
        identity_evidence_sha256="b" * 64,
        identity_available_at=(date.fromisoformat(session).isoformat() + "T13:00:00.000000Z"),
        classification_evidence_sha256="c" * 64,
        classification_available_at=(date.fromisoformat(session).isoformat() + "T13:00:00.000000Z"),
        q_data_evidence_sha256="d" * 64,
        q_data_available_at=(date.fromisoformat(session).isoformat() + "T13:00:00.000000Z"),
        control_evidence_sha256="e" * 64,
        control_available_at=(date.fromisoformat(session).isoformat() + "T13:00:00.000000Z"),
    )


def _refused_census_row(session: str, index: int):
    return build_eligible_security_session_refusal(
        decision_session=session,
        security_id=f"security-{index:02d}",
        issuer_id=f"issuer-{index:02d}",
        share_class_id=f"share-{index:02d}",
        listing_id=f"listing-{index:02d}",
        historical_ticker=f"S{index:02d}",
        reason=CensusRefusalReason.MISSING_PREOPEN_CONTROLS,
        source_id="pit-census-source-1",
        source_sha256="a" * 64,
        available_at=None,
    )


def _rating(
    index: int,
    *,
    identity_index: int | None = None,
    include_time: bool = True,
    event_date: str = "2020-01-02",
    last_updated: str = "2020-01-03T12:00:00Z",
) -> dict[str, object]:
    if identity_index is None:
        identity_index = index
    pairs = (
        ("Sell", "Underweight"),
        ("Sell", "Hold"),
        ("Sell", "Buy"),
        ("Sell", "Strong Buy"),
    )
    previous, current = pairs[index % len(pairs)]
    result: dict[str, object] = {
        "benzinga_id": f"event-{index:02d}",
        "date": event_date,
        "last_updated": last_updated,
        "ticker": f"S{identity_index:02d}",
        "rating_action": "upgrades",
        "rating": current,
        "previous_rating": previous,
        "benzinga_firm_id": f"firm-{index:02d}",
        "firm": f"Firm {index:02d}",
    }
    if include_time:
        result["time"] = "09:31:00"
    return result


def _rows_bytes(rows) -> bytes:
    return b"".join(canonical_json_bytes(row) for row in rows)


def _page(role: MassiveSourceRole, rows, receipt: str):
    return bind_capture_page(
        source_role=role,
        redacted_query_bytes=render_redacted_capture_query_bytes(
            source_role=role,
            requested_first_event_date=FIRST,
            requested_last_event_date=LAST,
        ),
        page_number=1,
        request_cursor_sha256=None,
        next_cursor_sha256=None,
        terminal_page=True,
        response_received_at=receipt,
        raw_response_sha256=hashlib.sha256((role.value + "response").encode()).hexdigest(),
        provider_rows_bytes=_rows_bytes(rows),
    )


def _c2_pair(
    count: int = 20,
    *,
    duplicate_last_with_zero: bool = False,
    missing_last_time: bool = False,
    event_date: str = "2020-01-02",
    last_updated: str = "2020-01-03T12:00:00Z",
    decision_session: str = "2020-01-06",
    evidence_available_at: str = EARLY,
    refresh_event_date: str | None = None,
    refresh_last_updated: str | None = None,
    refresh_decision_session: str | None = None,
    refresh_evidence_available_at: str | None = None,
):
    refresh_values = (
        refresh_event_date,
        refresh_last_updated,
        refresh_decision_session,
        refresh_evidence_available_at,
    )
    if any(item is not None for item in refresh_values) and any(
        item is None for item in refresh_values
    ):
        raise AssertionError("refresh fixture inputs must be supplied together")
    include_refresh = refresh_event_date is not None
    event_count = count * (2 if include_refresh else 1)

    def identity_for_event(index: int) -> int:
        if duplicate_last_with_zero and index == count - 1:
            return 0
        return index % count

    def event_value(index: int, original: str, refreshed: str | None) -> str:
        return str(refreshed) if index >= count else original

    ratings = [
        _rating(
            index,
            identity_index=identity_for_event(index),
            include_time=not (missing_last_time and index == count - 1),
            event_date=event_value(index, event_date, refresh_event_date),
            last_updated=event_value(
                index, last_updated, refresh_last_updated
            ),
        )
        for index in range(event_count)
    ]
    capture = build_capture_binding(
        capture_started_at=STARTED,
        capture_completed_at=COMPLETED,
        pages=(
            _page(MassiveSourceRole.ANALYST_RATINGS, ratings, "2026-09-11T18:01:00.000000Z"),
            _page(
                MassiveSourceRole.EARNINGS,
                [{"benzinga_id": "earn-1", "date": "2020-01-02", "time": "09:31:00", "last_updated": "2020-01-03T12:00:00Z", "ticker": "S00"}],
                "2026-09-11T18:02:00.000000Z",
            ),
            _page(
                MassiveSourceRole.CORPORATE_GUIDANCE,
                [{"benzinga_id": "guide-1", "date": "2020-01-02", "time": "09:31:00", "last_updated": "2020-01-03T12:00:00Z", "ticker": "S00"}],
                "2026-09-11T18:03:00.000000Z",
            ),
        ),
    )
    pair = build_accepted_risk_input_pair(capture)
    sources = tuple(
        EvidenceSourceBinding(
            kind=kind,
            artifact_id=SOURCE_IDS[kind],
            artifact_sha256=SOURCE_HASHES[kind],
            reviewed=True,
            point_in_time=True,
        )
        for kind in EvidenceSourceKind
    )
    evidence = []
    raw_by_id = {row["benzinga_id"]: row for row in ratings}
    source_by_provider_id = {
        row.provider_event_id: row
        for row in pair.rows
        if row.locator.source_role is MassiveSourceRole.ANALYST_RATINGS
    }
    for source in pair.rows:
        if source.locator.source_role is not MassiveSourceRole.ANALYST_RATINGS:
            continue
        index = int(source.provider_event_id[-2:])
        identity_index = identity_for_event(index)
        row_decision_session = event_value(
            index, decision_session, refresh_decision_session
        )
        row_evidence_available_at = event_value(
            index, evidence_available_at, refresh_evidence_available_at
        )
        raw = raw_by_id[source.provider_event_id]
        delta = Fraction(identity_index + 1, 25)
        component_index = index if index >= count else identity_index
        evidence.append(
            ProductionRowEvidence(
                locator=source.locator,
                security=SecurityIdentityEvidence(
                    provider_event_id=source.provider_event_id,
                    source_current_restated_ticker=source.current_restated_security_label,
                    historical_ticker=f"S{identity_index:02d}",
                    issuer_id=f"issuer-{identity_index:02d}",
                    security_id=f"security-{identity_index:02d}",
                    share_class_id=f"share-{identity_index:02d}",
                    listing_id=f"listing-{identity_index:02d}",
                    security_master_id=SOURCE_IDS[EvidenceSourceKind.SECURITY_MASTER],
                    security_master_sha256=SOURCE_HASHES[EvidenceSourceKind.SECURITY_MASTER],
                    mapping_version_id=f"mapping-{identity_index:02d}",
                    mapping_evidence_sha256=(
                        source_by_provider_id[
                            f"event-{identity_index:02d}"
                        ].locator.raw_row_sha256
                    ),
                    valid_from="2013-01-02",
                    valid_to=None,
                    valid_to_available_at=None,
                    available_at=row_evidence_available_at,
                    candidate_count=1,
                    point_in_time=True,
                    current_ticker_only=False,
                ),
                firm=FirmOntologyEvidence(
                    provider_event_id=source.provider_event_id,
                    provider_firm_id=f"firm-{index:02d}",
                    raw_firm_name=f"Firm {index:02d}",
                    raw_current_label=str(raw["rating"]),
                    raw_previous_label=str(raw["previous_rating"]),
                    institution_id=f"institution-{identity_index:02d}",
                    ontology_id=SOURCE_IDS[EvidenceSourceKind.FIRM_ONTOLOGY],
                    ontology_sha256=SOURCE_HASHES[EvidenceSourceKind.FIRM_ONTOLOGY],
                    ontology_entry_sha256=hashlib.sha256(f"ontology:{index}".encode()).hexdigest(),
                    valid_from="2013-01-02",
                    valid_to=None,
                    valid_to_available_at=None,
                    available_at=row_evidence_available_at,
                    current_score=delta / 2,
                    previous_score=-delta / 2,
                    candidate_count=1,
                    ontology_reviewed=True,
                    labels_reviewed=True,
                ),
                common_event=CommonEventIdentityEvidence(
                    provider_event_id=source.provider_event_id,
                    common_event_id=f"common-{component_index // 2:02d}",
                    source_id=SOURCE_IDS[EvidenceSourceKind.COMMON_EVENT],
                    source_sha256=SOURCE_HASHES[EvidenceSourceKind.COMMON_EVENT],
                    evidence_sha256=hashlib.sha256(
                        f"common:{component_index // 2}".encode()
                    ).hexdigest(),
                    available_at=row_evidence_available_at,
                    candidate_count=1,
                ),
                sector=SectorClassificationEvidence(
                    security_id=f"security-{identity_index:02d}",
                    sector_id="sector-one",
                    source_id=SOURCE_IDS[EvidenceSourceKind.SECTOR_CLASSIFICATION],
                    source_sha256=SOURCE_HASHES[EvidenceSourceKind.SECTOR_CLASSIFICATION],
                    evidence_sha256=hashlib.sha256(
                        f"sector:{identity_index}".encode()
                    ).hexdigest(),
                    valid_from="2013-01-02",
                    valid_to=None,
                    valid_to_available_at=None,
                    available_at=row_evidence_available_at,
                    candidate_count=1,
                    point_in_time=True,
                ),
                control=PreopenControlEvidence(
                    security_id=f"security-{identity_index:02d}",
                    industry_id=(
                        "industry-one" if identity_index < 10 else "industry-two"
                    ),
                    decision_session=row_decision_session,
                    source_id=SOURCE_IDS[EvidenceSourceKind.PREOPEN_CONTROL],
                    source_sha256=SOURCE_HASHES[EvidenceSourceKind.PREOPEN_CONTROL],
                    evidence_sha256=hashlib.sha256(
                        f"control:{identity_index}".encode()
                    ).hexdigest(),
                    available_at=row_evidence_available_at,
                    control_vector_sha256=_control_vector(
                        identity_index
                        + int(row_decision_session[-2:]) * 1000
                    ).vector_sha256,
                    complete=True,
                    point_in_time=True,
                    contains_outcome_or_price=False,
                ),
                q_data=None,
            )
        )
    projections = {
        (item.measured_session, item.security_id): item
        for item in derive_c2_quality_component_projections(pair, tuple(evidence))
    }
    measurements = {}
    for key, projection in projections.items():
        session, security_id = key
        components = (
            build_quality_component_evidence(
                kind=QualityComponentKind.TIMESTAMP_QUALITY,
                value=Decimal("0.9"),
                source_id=pair.pair_id,
                source_sha256=pair.pair_sha256,
                payload_sha256=projection.timestamp_payload_sha256,
                available_at=next(
                    item.security.available_at
                    for item in evidence
                    if item.security is not None
                    and item.security.security_id == security_id
                    and source_by_provider_id[
                        item.security.provider_event_id
                    ].current_view.eligible_session == session
                ),
            ),
            build_quality_component_evidence(
                kind=QualityComponentKind.FIRM_LABEL_MAPPING_QUALITY,
                value=Decimal("0.9"),
                source_id=SOURCE_IDS[EvidenceSourceKind.FIRM_ONTOLOGY],
                source_sha256=SOURCE_HASHES[EvidenceSourceKind.FIRM_ONTOLOGY],
                payload_sha256=projection.firm_label_payload_sha256,
                available_at=next(
                    item.firm.available_at
                    for item in evidence
                    if item.firm is not None
                    and item.security is not None
                    and item.security.security_id == security_id
                    and source_by_provider_id[
                        item.security.provider_event_id
                    ].current_view.eligible_session == session
                ),
            ),
            build_quality_component_evidence(
                kind=QualityComponentKind.SECURITY_ENTITY_MAPPING_QUALITY,
                value=Decimal("0.9"),
                source_id=SOURCE_IDS[EvidenceSourceKind.SECURITY_MASTER],
                source_sha256=SOURCE_HASHES[EvidenceSourceKind.SECURITY_MASTER],
                payload_sha256=projection.security_entity_payload_sha256,
                available_at=next(
                    item.security.available_at
                    for item in evidence
                    if item.security is not None
                    and item.security.security_id == security_id
                    and source_by_provider_id[
                        item.security.provider_event_id
                    ].current_view.eligible_session == session
                ),
            ),
        )
        measurements[key] = build_derived_data_quality_evidence(
            security_id=security_id,
            measured_session=session,
            source_id=SOURCE_IDS[EvidenceSourceKind.DATA_QUALITY],
            source_sha256=SOURCE_HASHES[EvidenceSourceKind.DATA_QUALITY],
            components=components,
        )
    evidence = [
        dataclasses.replace(
            item,
            q_data=project_c2_data_quality_evidence(
                measurements[(
                    source_by_provider_id[item.security.provider_event_id].current_view.eligible_session,
                    item.security.security_id,
                )]
            ),
        )
        for item in evidence
        if item.security is not None
    ]
    authority = build_production_evidence_authority(
        pair, source_bindings=sources, row_evidence=tuple(evidence)
    )
    current = build_production_input_batch(authority, signal_arm=SignalArm.CURRENT_VINTAGE)
    censored = build_production_input_batch(authority, signal_arm=SignalArm.CONSERVATIVE_CENSORED)
    labels = tuple(
        sorted(
            (
                build_endpoint_label_evidence(
                    c2_row_sha256=row.row_sha256,
                    provider_event_id=row.provider_event_id,
                    raw_previous_label=next(item.firm.raw_previous_label for item in evidence if item.locator == row.source_locator and item.firm is not None),
                    raw_current_label=next(item.firm.raw_current_label for item in evidence if item.locator == row.source_locator and item.firm is not None),
                    source_sha256=row.source_locator.raw_row_sha256,
                    available_at=next(
                        item.security.available_at
                        for item in evidence
                        if item.security is not None
                        and item.locator == row.source_locator
                    ),
                )
                for row in {item.row_sha256: item for item in (*current.normalized_rows, *censored.normalized_rows)}.values()
            ),
            key=lambda item: item.c2_row_sha256,
        )
    )
    return current, censored, labels


def _generic_payload(kind: QualityComponentKind, session: str, security_id: str) -> str:
    return hashlib.sha256(f"{kind.value}:{session}:{security_id}".encode()).hexdigest()


def _reviewed_preopen_acquisition(
    accepted, refusals, source_bindings, q_data_measurements, *, return_payload=False
):
    summaries = truth_module._session_summaries(accepted, refusals)
    measurement_by_key = {
        (item.measured_session, item.security_id): item
        for item in q_data_measurements
    }
    assert len(measurement_by_key) == len(q_data_measurements) == len(accepted)
    market_root = hashlib.sha256(b"fixture-market-observations").hexdigest()
    input_roots = {
        "universe": hashlib.sha256(b"universe").hexdigest(),
        "sid_mapping": hashlib.sha256(b"sid-mapping").hexdigest(),
        "fundamentals": hashlib.sha256(b"fundamentals").hexdigest(),
        "earnings": hashlib.sha256(b"earnings").hexdigest(),
        "guidance": hashlib.sha256(b"guidance").hexdigest(),
        "ratings": hashlib.sha256(b"ratings").hexdigest(),
        "market_observations": market_root,
    }
    terminals = []
    for item in accepted:
        terminal = {
            "schema": OUTPUT_TERMINAL_SCHEMA,
            "decision_session": item.decision_session,
            "security_id": item.security_id,
            "qc_security_id": item.security_id,
            "issuer_id": item.issuer_id,
            "share_class_id": item.share_class_id,
            "listing_id": item.listing_id,
            "security_master_row_sha256": item.identity_evidence_sha256,
            "disposition": "accepted", "detail_reason": None,
            "eligible_security_session": item.to_record(),
            "q_data_measurement": measurement_by_key[
                (item.decision_session, item.security_id)
            ].to_record(),
            "census_refusal": None, "input_roots": input_roots,
        }
        terminal["terminal_sha256"] = sha256_bytes(canonical_json_bytes(terminal))
        terminals.append(terminal)
    for item in refusals:
        terminal = {
            "schema": OUTPUT_TERMINAL_SCHEMA,
            "decision_session": item.decision_session,
            "security_id": item.security_id,
            "qc_security_id": item.security_id,
            "issuer_id": item.issuer_id,
            "share_class_id": item.share_class_id,
            "listing_id": item.listing_id,
            "security_master_row_sha256": hashlib.sha256(
                (item.security_id + "-master").encode()
            ).hexdigest(),
            "disposition": "named_refusal",
            "detail_reason": "carried_universe_refusal",
            "eligible_security_session": None,
            "q_data_measurement": None,
            "census_refusal": item.to_record(), "input_roots": input_roots,
        }
        terminal["terminal_sha256"] = sha256_bytes(canonical_json_bytes(terminal))
        terminals.append(terminal)
    shard = build_preopen_output_shard(
        ordinal=0, terminal_rows=terminals
    )
    universe_sessions = [
        {
            "schema": UNIVERSE_SESSION_COMMITMENT_SCHEMA,
            "decision_session": item.decision_session,
            "accepted_count": item.accepted_count,
            "refusal_count": item.refusal_count,
            "terminal_count": item.terminal_count,
            "terminal_merkle_root": item.terminal_merkle_root,
        }
        for item in summaries
    ]
    control_sessions = [
        {
            "schema": CONTROL_SESSION_COMMITMENT_SCHEMA,
            "decision_session": item.decision_session,
            "accepted_count": item.accepted_count,
            "refusal_count": item.refusal_count,
            "terminal_count": item.terminal_count,
            "terminal_merkle_root": truth_module._merkle_root(
                sorted(
                    [row for row in terminals if row["decision_session"]
                     == item.decision_session],
                    key=lambda row: row["security_id"],
                )
            ),
            "market_observation_count": 0,
            "market_observation_sha256": market_root,
        }
        for item in summaries
    ]
    inventory = hashlib.sha256(b"fixture-source-inventory").hexdigest()
    policy = {
        "rating_source_view": (
            "conservative_censored_current_vintage_non_pristine_pit"
        ),
        "rating_source_complete": True,
        "earnings_source_complete": True,
        "earnings_pit_policy_id": "fixture-reviewed-earnings-policy-v1",
        "guidance_source_complete": True,
        "guidance_clock_policy_id": (
            "massive_guidance_date_only_three_session_lag_prior_date_censor-v1"
        ),
        "unknown_event_archive_or_clock_is_zero": False,
    }
    census = {
        "fixture": "bounded",
        "maximum_logical_merge_compressed_bytes": 32 * 1024 * 1024,
    }
    sid_mapping = {
        "artifact_id": "fixture-reviewed-qc-sid-map-1",
        "content_sha256": hashlib.sha256(b"sid_mapping").hexdigest(),
        "artifact_sha256": hashlib.sha256(b"sid_mapping").hexdigest(),
        "byte_count": 456,
        "row_count": len({
            item.security_id for item in (*accepted, *refusals)
        }),
        "mapping_semantics": (
            "canonical_content_addressed_exact_QC_SecurityIdentifier_to_"
            "Sharadar_CUSIP_permaticker_FIGI_binding;_current_ticker_is_"
            "display_only_and_the_runtime_must_use_self.symbol_encoded_SID"
        ),
    }
    role_bindings = [{
        "role": role, "descriptor_projection_sha256": hashlib.sha256(
            role.encode()
        ).hexdigest(), "shard_count": 1,
        "row_count": sid_mapping["row_count"] if role == "sid_mapping" else 0,
        "compressed_byte_count": 0, "uncompressed_byte_count": 0,
    } for role in ("universe", "sid_mapping", "fundamentals", "earnings", "guidance", "ratings")]
    truth_sources = [{
        "kind": item.kind.value, "artifact_id": item.artifact_id,
        "artifact_sha256": item.artifact_sha256,
    } for item in source_bindings]
    input_bytes = canonical_json_bytes({
            "input_source_inventory_sha256": inventory,
            "input_role_bindings": role_bindings,
            "truth_source_bindings": truth_sources,
            "eligible_universe_source": {
                "artifact_id": "pit-census-source-1",
                "content_sha256": "a" * 64,
                "artifact_sha256": "a" * 64,
                "byte_count": 123,
            },
            "qc_sid_mapping_source": sid_mapping,
            "source_policy": policy,
            "resource_census": census,
            "construction_gate": {"external_private_run_authority": {
                "schema": "arv2-preopen-control-private-run-authority-v1",
                "pin_id": "fixture-run-pin-1",
                "pin_sha256": hashlib.sha256(b"run-pin").hexdigest(),
                "closed_input_manifest_sha256": hashlib.sha256(b"closed").hexdigest(),
                "input_source_inventory_sha256": inventory,
                "source_policy_sha256": sha256_bytes(canonical_json_bytes(policy)),
                "resource_census_sha256": sha256_bytes(canonical_json_bytes(census)),
                "qc_sid_mapping_source_sha256": sha256_bytes(
                    canonical_json_bytes(sid_mapping)
                ),
                "target_qc_capacity_reviewed": True,
                "qc_sid_mapping_reviewed": True,
            }},
        })
    output = build_preopen_output_manifest_bytes(
        input_manifest_bytes=input_bytes,
        input_manifest_id="fixture-preopen-input-1",
        project_source_set_sha256="9" * 64,
        output_shards=(shard,),
        universe_sessions=universe_sessions,
        control_sessions=control_sessions,
        construction_intermediates={
            "schema": CONSTRUCTION_INTERMEDIATE_SCHEMA,
            "peer_aggregate_record_count": 0,
            "peer_aggregate_projection_sha256": hashlib.sha256(
                b"fixture-peer-aggregate-projection"
            ).hexdigest(),
            "market_session_commitment_count": len(control_sessions),
            "market_session_projection_sha256": hashlib.sha256(
                b"fixture-market-session-projection"
            ).hexdigest(),
            "physical_terminal_shard_count": 1,
            "logical_terminal_order": "decision_session_then_security_id",
            "q_data_measurement_count": len(q_data_measurements),
            "q_data_measurement_projection_sha256": (
                quality_measurement_projection_sha256(q_data_measurements)
            ),
        },
    )
    output_hash = hashlib.sha256(output).hexdigest()
    parsed = json.loads(output)
    review = {
        "schema": REVIEW_RECEIPT_SCHEMA,
        "output_manifest": {
            "artifact_id": f"arv2-preopen-control-output-{output_hash[:24]}",
            "content_sha256": output_hash,
            "artifact_sha256": output_hash,
            "byte_count": len(output),
        },
        "input_source_inventory_sha256": parsed[
            "input_source_inventory_sha256"
        ],
        "project_source_set_sha256": parsed["project_source_set_sha256"],
        "output_shard_inventory_sha256": parsed[
            "output_shard_inventory_sha256"
        ],
        "universe_terminal_projection_sha256": parsed[
            "universe_terminal_projection_sha256"
        ],
        "control_terminal_projection_sha256": parsed[
            "control_terminal_projection_sha256"
        ],
        "review_receipt_id": None,
        "review_receipt_sha256": None,
        "complete_source_inventory_verified": True,
        "per_session_universe_terminal_completeness_verified": True,
        "control_formula_equivalence_verified": True,
        "strict_preopen_timing_verified": True,
        "no_outcomes_verified": True,
        "object_store_persistence_verified": True,
        "formal_runtime_direct_consumption_verified": True,
    }
    digest = sha256_bytes(canonical_json_bytes(review))
    review["review_receipt_id"] = (
        f"arv2-preopen-control-review-{digest[:24]}"
    )
    review["review_receipt_sha256"] = digest
    review_bytes = canonical_json_bytes(review)
    summary = canonical_json_bytes({
        "schema": "arv2-preopen-control-summary-receipt-v1",
        "manifest_sha256": output_hash, "manifest_byte_count": len(output),
        "source_set_sha256": "9" * 64, "terminal_count": len(terminals),
        "accepted_count": len(accepted), "refusal_count": len(refusals),
        "shard_count": 1,
    })
    execution = render_preopen_qc_execution_receipt(
        project_id="fixture-project", compile_id="fixture-compile",
        backtest_id="fixture-backtest",
        input_manifest_sha256=sha256_bytes(input_bytes),
        project_source_set_sha256="9" * 64,
        output_manifest_sha256=output_hash,
        summary_receipt_sha256=sha256_bytes(summary),
    )
    pin = render_preopen_control_external_review_pin_candidate(
        output_manifest_bytes=output, output_shard_payloads=(shard.payload,),
        independent_review_receipt_bytes=review_bytes,
        qc_execution_receipt_bytes=execution, summary_receipt_bytes=summary,
    )
    with tempfile.TemporaryDirectory(dir="/private/tmp") as directory:
        pin_path = Path(directory) / "preopen-acquisition-pin.json"
        pin_path.write_bytes(pin)
        os.chmod(pin_path, 0o600)
        receipt = _offline_signed_loader(
            load_physically_reviewed_preopen_control_acquisition_receipt
        )(
            output_manifest_bytes=output, output_shard_payloads=(shard.payload,),
            independent_review_receipt_bytes=review_bytes,
            qc_execution_receipt_bytes=execution, summary_receipt_bytes=summary,
            external_review_pin_path=pin_path,
            owner_signature=_offline_owner_signature(),
        )
        return (receipt, shard.payload) if return_payload else receipt


def _truth_artifact(
    current,
    censored,
    census,
    refusals=(),
    *,
    return_payload=False,
    evidence_material=None,
):
    evidence_authority = current.evidence_authority
    assert evidence_authority is censored.evidence_authority
    projections = {
        (item.measured_session, item.security_id): item
        for item in derive_c2_quality_component_projections(
            evidence_authority.pair, evidence_authority.row_evidence
        )
    }
    source_by_locator = {
        item.locator: item for item in evidence_authority.pair.rows
    }
    overlap_evidence = {}
    for item in evidence_authority.row_evidence:
        if item.security is None:
            continue
        source = source_by_locator[item.locator]
        if source.current_view.eligible_session is not None:
            overlap_evidence[
                (source.current_view.eligible_session, item.security.security_id)
            ] = item
    measurements = []
    rebuilt = []
    for row in census:
        key = (row.decision_session, row.security_id)
        projection = projections.get(key)
        evidence = overlap_evidence.get(key)
        payloads = (
            _generic_payload(QualityComponentKind.TIMESTAMP_QUALITY, *key)
            if projection is None else projection.timestamp_payload_sha256,
            _generic_payload(QualityComponentKind.FIRM_LABEL_MAPPING_QUALITY, *key)
            if projection is None else projection.firm_label_payload_sha256,
            _generic_payload(QualityComponentKind.SECURITY_ENTITY_MAPPING_QUALITY, *key)
            if projection is None else projection.security_entity_payload_sha256,
        )
        components = (
            build_quality_component_evidence(
                kind=QualityComponentKind.TIMESTAMP_QUALITY,
                value=Decimal("0.9"),
                source_id=evidence_authority.pair_id,
                source_sha256=evidence_authority.pair_sha256,
                payload_sha256=payloads[0],
                available_at=(
                    row.q_data_available_at
                    if evidence is None or evidence.q_data is None
                    else evidence.q_data.available_at
                ),
            ),
            build_quality_component_evidence(
                kind=QualityComponentKind.FIRM_LABEL_MAPPING_QUALITY,
                value=Decimal("0.9"),
                source_id=SOURCE_IDS[EvidenceSourceKind.FIRM_ONTOLOGY],
                source_sha256=SOURCE_HASHES[EvidenceSourceKind.FIRM_ONTOLOGY],
                payload_sha256=payloads[1],
                available_at=(
                    row.q_data_available_at
                    if evidence is None or evidence.q_data is None
                    else evidence.q_data.available_at
                ),
            ),
            build_quality_component_evidence(
                kind=QualityComponentKind.SECURITY_ENTITY_MAPPING_QUALITY,
                value=Decimal("0.9"),
                source_id=SOURCE_IDS[EvidenceSourceKind.SECURITY_MASTER],
                source_sha256=SOURCE_HASHES[EvidenceSourceKind.SECURITY_MASTER],
                payload_sha256=payloads[2],
                available_at=(
                    row.q_data_available_at
                    if evidence is None or evidence.q_data is None
                    else evidence.q_data.available_at
                ),
            ),
        )
        measurement = build_derived_data_quality_evidence(
            security_id=row.security_id,
            measured_session=row.decision_session,
            source_id=SOURCE_IDS[EvidenceSourceKind.DATA_QUALITY],
            source_sha256=SOURCE_HASHES[EvidenceSourceKind.DATA_QUALITY],
            components=components,
        )
        measurements.append(measurement)
        rebuilt.append(
            build_eligible_security_session(
                decision_session=row.decision_session,
                security_id=row.security_id,
                issuer_id=row.issuer_id,
                share_class_id=row.share_class_id,
                listing_id=row.listing_id,
                historical_ticker=row.historical_ticker,
                sector_id=row.sector_id,
                industry_id=row.industry_id,
                q_data=measurement.q_data,
                controls=row.controls,
                source_id=row.source_id,
                source_sha256=row.source_sha256,
                identity_evidence_sha256=(
                    row.identity_evidence_sha256
                    if evidence is None or evidence.security is None
                    else evidence.security.mapping_evidence_sha256
                ),
                identity_available_at=(
                    row.identity_available_at
                    if evidence is None or evidence.security is None
                    else evidence.security.available_at
                ),
                classification_evidence_sha256=(
                    row.classification_evidence_sha256
                    if evidence is None or evidence.sector is None
                    else evidence.sector.evidence_sha256
                ),
                classification_available_at=(
                    row.classification_available_at
                    if evidence is None or evidence.sector is None
                    else evidence.sector.available_at
                ),
                q_data_evidence_sha256=measurement.evidence_sha256,
                q_data_available_at=measurement.available_at,
                control_evidence_sha256=(
                    row.control_evidence_sha256
                    if evidence is None or evidence.control is None
                    else evidence.control.evidence_sha256
                ),
                control_available_at=(
                    row.control_available_at
                    if evidence is None or evidence.control is None
                    else evidence.control.available_at
                ),
            )
        )
    accepted = tuple(rebuilt)
    source_bindings = []
    c2_by_kind = {item.kind: item for item in evidence_authority.source_bindings}
    for kind in TruthSourceKind:
        if kind is TruthSourceKind.ACCEPTED_RISK_CAPTURE:
            source_bindings.append(
                build_production_truth_source_binding(
                    kind=kind,
                    artifact_id=evidence_authority.pair_id,
                    artifact_sha256=evidence_authority.pair_sha256,
                )
            )
        elif kind is TruthSourceKind.ELIGIBLE_UNIVERSE:
            source_bindings.append(
                build_production_truth_source_binding(
                    kind=kind,
                    artifact_id="pit-census-source-1",
                    artifact_sha256="a" * 64,
                    accepted_rows=accepted,
                    refusals=refusals,
                )
            )
        else:
            c2_kind = EvidenceSourceKind(kind.value)
            source = c2_by_kind[c2_kind]
            source_bindings.append(
                build_production_truth_source_binding(
                    kind=kind,
                    artifact_id=source.artifact_id,
                    artifact_sha256=source.artifact_sha256,
                )
            )
    measurement_tuple = tuple(measurements)
    acquired = _reviewed_preopen_acquisition(
        accepted, refusals, tuple(source_bindings), measurement_tuple,
        return_payload=return_payload,
    )
    acquisition, physical_payload = (
        acquired if return_payload else (acquired, None)
    )
    package_bytes = render_production_evidence_package_bytes(evidence_authority)
    pin_bytes = render_production_evidence_owner_review_payload_candidate(
        authority=evidence_authority,
        preopen_acquisition_receipt=acquisition,
        package_bytes=package_bytes,
    )
    with tempfile.TemporaryDirectory(dir="/private/tmp") as directory:
        package_path = Path(directory) / "production-evidence-package.json"
        pin_path = Path(directory) / "production-evidence-review-pin.json"
        package_path.write_bytes(package_bytes)
        pin_path.write_bytes(pin_bytes)
        os.chmod(package_path, 0o600)
        os.chmod(pin_path, 0o600)
        production_evidence_receipt = (
            _offline_signed_loader(
                load_physically_reviewed_production_evidence_receipt
            )(
                authority=evidence_authority,
                preopen_acquisition_receipt=acquisition,
                package_path=package_path,
                external_review_pin_path=pin_path,
                owner_signature=_offline_owner_signature(),
            )
        )
    if evidence_material is not None:
        evidence_material.update({
            "authority": evidence_authority,
            "preopen_acquisition_receipt": acquisition,
            "package_bytes": package_bytes,
            "pin_bytes": pin_bytes,
            "receipt": production_evidence_receipt,
        })
    truth = build_production_truth_artifact(
        evidence_authority,
        production_evidence_receipt=production_evidence_receipt,
        preopen_acquisition_receipt=acquisition,
        source_bindings=tuple(source_bindings),
        accepted_rows=accepted,
        refusals=refusals,
        q_data_measurements=measurement_tuple,
    )
    return (truth, physical_payload) if return_payload else truth


def _scoring_authority(current, censored, labels, census, refusals=()):
    truth = _truth_artifact(current, censored, census, refusals)
    return build_production_scoring_authority(
        current,
        censored,
        _global_contract(),
        truth_artifact=truth,
        census_rows=truth.accepted_rows,
        census_refusals=truth.refusals,
        endpoint_labels=labels,
    )


def _authority_and_fold(session_count: int = 4):
    current, censored, labels = _c2_pair()
    sessions = ("2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09")[:session_count]
    census = tuple(
        _census_row(session, index)
        for session in sessions
        for index in range(20)
    )
    authority = _scoring_authority(current, censored, labels, census)
    fold = ProductionScoringFold(
        fold_id="arv2-test-fold",
        train_start="2020-01-06",
        train_end_exclusive="2020-01-09",
        validation_start="2020-01-09",
        validation_end_exclusive="2020-01-10",
        test_start="2020-01-10",
        test_end_exclusive="2020-01-13",
    )
    return authority, fold


def test_production_evidence_review_requires_signature_and_is_fork_local(
    tmp_path, monkeypatch,
):
    current, censored, _ = _c2_pair()
    sessions = ("2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09")
    census = tuple(
        _census_row(session, index)
        for session in sessions
        for index in range(20)
    )
    material = {}
    _truth_artifact(
        current,
        censored,
        census,
        evidence_material=material,
    )
    authority = material["authority"]
    acquisition = material["preopen_acquisition_receipt"]
    package_bytes = material["package_bytes"]
    signed_payload_candidate = material["pin_bytes"]
    receipt = material["receipt"]
    assert _offline_physical_requirer("evidence", receipt) is receipt
    with pytest.raises(ProductionEvidenceAcquisitionError):
        require_production_evidence_acquisition_receipt(receipt)

    flipped = json.loads(
        render_production_evidence_external_review_pin_candidate(
            authority=authority,
            preopen_acquisition_receipt=acquisition,
            package_bytes=package_bytes,
        )
    )
    flipped["status"] = "independently_reviewed_private_production_evidence"
    flipped["complete_member_census_verified"] = True
    flipped["source_membership_verified"] = True
    flipped["same_key_identity_lineage_verified"] = True
    semantic = dict(flipped)
    semantic["pin_id"] = None
    semantic["pin_sha256"] = None
    digest = sha256_bytes(canonical_json_bytes(semantic))
    flipped["pin_id"] = f"arv2-production-evidence-review-{digest[:24]}"
    flipped["pin_sha256"] = digest
    flipped_bytes = canonical_json_bytes(flipped)
    assert flipped_bytes == signed_payload_candidate

    package_path = tmp_path / "production-evidence-package.json"
    pin_path = tmp_path / "production-evidence-review-pin.json"
    package_path.write_bytes(package_bytes)
    pin_path.write_bytes(flipped_bytes)
    package_path.chmod(0o600)
    pin_path.chmod(0o600)
    kwargs = {
        "authority": authority,
        "preopen_acquisition_receipt": acquisition,
        "package_path": package_path,
        "external_review_pin_path": pin_path,
        "owner_signature": None,
    }
    with pytest.raises(ProductionEvidenceAcquisitionIoError):
        load_physically_reviewed_production_evidence_receipt(**kwargs)

    calls = []
    with monkeypatch.context() as patch:
        patch.setattr(
            production_evidence_io,
            "require_production_evidence_review_owner_signature",
            lambda *args, **values: calls.append((args, values)),
            raising=False,
        )
        with pytest.raises(ProductionEvidenceAcquisitionIoError):
            production_evidence_io.load_physically_reviewed_production_evidence_receipt(
                **kwargs
            )
    assert calls == []

    external_callbacks = []

    def hostile_open(*args, **values):
        external_callbacks.append((args, values))
        raise AssertionError("hostile file open executed")

    with monkeypatch.context() as patch:
        patch.setattr(
            evidence_core,
            "require_reviewed_preopen_control_acquisition_receipt",
            _PRODUCTION_PREOPEN_REQUIRE,
        )
        patch.setattr(production_evidence_io.os, "open", hostile_open)
        with pytest.raises(
            ProductionEvidenceAcquisitionIoError,
            match="physical loader authority changed",
        ):
            production_evidence_io.load_physically_reviewed_production_evidence_receipt(
                **kwargs
            )
    assert external_callbacks == []

    signer_callbacks = []

    def require_typed_owner_signature(value, *, authority_payload):
        signer_callbacks.append((value, authority_payload))
        assert type(value) is OwnerSignatureAuthority
        assert type(authority_payload) is bytes and authority_payload
        return value

    loader = production_evidence_io.load_physically_reviewed_production_evidence_receipt
    clone = _with_closure_value(
        loader,
        "owner_signature_requirer",
        require_typed_owner_signature,
    )
    signed_kwargs = {
        **kwargs,
        "owner_signature": _offline_owner_signature(),
    }
    loader_cells = dict(
        zip(loader.__code__.co_freevars, loader.__closure__, strict=True)
    )
    minter = loader_cells["receipt_minter"].cell_contents
    minter_cells = dict(
        zip(minter.__code__.co_freevars, minter.__closure__, strict=True)
    )
    records_before = minter_cells["records"].cell_contents
    with pytest.raises(
        ProductionEvidenceAcquisitionIoError,
        match="physical loader authority changed",
    ):
        clone(**signed_kwargs)
    assert signer_callbacks == []
    assert minter_cells["records"].cell_contents is records_before

    physical_reads = []

    def unexpected_read(*args, **values):
        physical_reads.append((args, values))
        raise AssertionError("physical read executed")

    with monkeypatch.context() as patch:
        patch.setattr(production_evidence_io, "_private_regular", unexpected_read)
        patch.setattr(
            production_evidence_io, "any", lambda _values: False, raising=False
        )
        patch.setattr(
            production_evidence_io,
            "_unexpected_physical_loader_global",
            object(),
            raising=False,
        )
        with pytest.raises(
            ProductionEvidenceAcquisitionIoError,
            match="physical loader authority changed",
        ):
            clone(**signed_kwargs)
    assert signer_callbacks == []
    assert physical_reads == []
    assert minter_cells["records"].cell_contents is records_before

    hostile_callbacks = []

    class HostileModule:
        def __getattr__(self, name):
            hostile_callbacks.append(name)
            raise AssertionError("hostile module callback executed")

    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, loader.__module__, HostileModule())
        with pytest.raises(
            ProductionEvidenceAcquisitionIoError,
            match="physical loader authority changed",
        ):
            clone(**signed_kwargs)
    assert hostile_callbacks == []
    assert signer_callbacks == []
    assert physical_reads == []
    assert minter_cells["records"].cell_contents is records_before
    assert type(minter_cells["records"].cell_contents) is tuple
    with pytest.raises(
        ProductionEvidenceAcquisitionError,
        match="mint is loader-private",
    ):
        minter(
            authority=authority,
            preopen_acquisition_receipt=acquisition,
            package_bytes=package_bytes,
            review_pin_bytes=flipped_bytes,
        )
    assert _offline_physical_requirer("evidence", receipt) is receipt

    for name in (
        "_PRODUCTION_EVIDENCE_ACQUISITION_AUTHORITIES",
        "_PRODUCTION_EVIDENCE_ACQUISITION_AUTHORITIES_LOCK",
        "_claim_production_evidence_receipt_minter",
        "_build_physically_reviewed_production_evidence_receipt",
        "_build_physically_reviewed_production_evidence_receipt_implementation",
        "_make_production_evidence_receipt_authority",
    ):
        assert not hasattr(evidence_core, name)

    if not hasattr(os, "fork"):
        pytest.skip("fork is unavailable")
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_descriptor)
        try:
            _offline_physical_requirer("evidence", receipt)
        except ProductionEvidenceAcquisitionError:
            result = b"refused"
        else:
            result = b"accepted"
        os.write(write_descriptor, result)
        os.close(write_descriptor)
        os._exit(0)
    os.close(write_descriptor)
    result = os.read(read_descriptor, 32)
    os.close(read_descriptor)
    _, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    assert result == b"refused"
    assert _offline_physical_requirer("evidence", receipt) is receipt


def test_control_vector_is_exact_complete_ordered_and_content_addressed():
    vector = _control_vector(1)
    assert len(vector.values) == 25
    assert vector.vector_sha256 == sha256_bytes(canonical_json_bytes(vector.to_record()))
    with pytest.raises(ProductionScoringError, match="reordered"):
        ProductionControlVector(tuple(reversed(vector.values)))
    hostile = list(vector.values)
    hostile[-1] = (hostile[-1][0], True)
    with pytest.raises(ProductionScoringError, match="binary control"):
        ProductionControlVector(tuple(hostile))


def test_census_is_pit_strictly_before_open_and_content_derived():
    row = _census_row("2020-01-06", 0)
    assert row.point_in_time is True
    assert row.control_vector_sha256 == row.controls.vector_sha256
    with pytest.raises(ProductionScoringError, match="before open"):
        build_eligible_security_session(
            decision_session="2020-01-06",
            security_id="security-00",
            issuer_id="issuer-00",
            share_class_id="share-00",
            listing_id="listing-00",
            historical_ticker="S00",
            sector_id="sector-one",
            industry_id="industry-one",
            q_data=Decimal("0.9"),
            controls=_control_vector(0),
            source_id="source-1",
            source_sha256="a" * 64,
            identity_evidence_sha256="b" * 64,
            identity_available_at="2020-01-06T14:30:00.000000Z",
            classification_evidence_sha256="c" * 64,
            classification_available_at="2020-01-06T13:00:00.000000Z",
            q_data_evidence_sha256="d" * 64,
            q_data_available_at="2020-01-06T13:00:00.000000Z",
            control_evidence_sha256="e" * 64,
            control_available_at="2020-01-06T13:00:00.000000Z",
        )
    with pytest.raises(ProductionScoringError, match="content-derived"):
        dataclasses.replace(row, evidence_sha256="f" * 64)


def test_endpoint_label_evidence_is_not_an_arbitrary_score_channel():
    evidence = build_endpoint_label_evidence(
        c2_row_sha256="a" * 64,
        provider_event_id="event-1",
        raw_previous_label="Sell",
        raw_current_label="Buy",
        source_sha256="b" * 64,
        available_at=EARLY,
    )
    assert set(dataclasses.asdict(evidence)) == {
        "c2_row_sha256", "provider_event_id", "raw_previous_label",
        "raw_current_label", "source_sha256", "available_at", "evidence_sha256",
    }
    assert not any("score" in field.name for field in dataclasses.fields(EndpointLabelEvidence))
    with pytest.raises(ProductionScoringError, match="content-derived"):
        dataclasses.replace(evidence, raw_current_label="Hold")


def test_decimal_qr_solves_exact_full_rank_and_refuses_rank_deficiency():
    design = (
        (Decimal(1), Decimal(0)),
        (Decimal(1), Decimal(1)),
        (Decimal(1), Decimal(2)),
    )
    coefficients = module._solve_ols(
        design, (Decimal(1), Decimal(3), Decimal(5))
    )
    assert abs(coefficients[0] - Decimal(1)) < Decimal("1e-40")
    assert abs(coefficients[1] - Decimal(2)) < Decimal("1e-40")
    with pytest.raises(ProductionScoringError, match="rank deficient"):
        module._solve_ols(
            ((Decimal(1), Decimal(1)), (Decimal(1), Decimal(1))),
            (Decimal(1), Decimal(2)),
        )


def test_forged_scoring_authority_is_refused():
    forged = object.__new__(ProductionScoringAuthority)
    with pytest.raises(ProductionScoringError, match="builder-authenticated"):
        require_production_scoring_authority(forged)


def test_production_truth_is_complete_serializable_and_derives_quality_minimum():
    current, censored, _labels = _c2_pair()
    census = tuple(_census_row("2020-01-06", index) for index in range(20))
    truth = _truth_artifact(current, censored, census)
    assert require_production_truth_artifact(truth) is truth
    assert len(truth.session_summaries) == len(FORMAL_SESSION_GEOMETRY)
    summary = next(
        item for item in truth.session_summaries
        if item.decision_session == "2020-01-06"
    )
    assert (summary.accepted_count, summary.refusal_count, summary.terminal_count) == (
        20, 0, 20
    )
    assert truth.terminal_projection_sha256 == truth.source_bindings[1].projection_sha256
    assert render_production_truth_artifact_bytes(truth)

    # Rebuild valid component hashes; the aggregate itself is never an input.
    rebuilt_components = tuple(
        build_quality_component_evidence(
            kind=item.kind,
            value=quality,
            source_id=item.source_id,
            source_sha256=item.source_sha256,
            payload_sha256=item.payload_sha256,
            available_at=item.available_at,
        )
        for item, quality in zip(
            truth.q_data_measurements[0].components,
            (Decimal("0.95"), Decimal("0.8"), Decimal("0.9")),
            strict=True,
        )
    )
    quality = build_derived_data_quality_evidence(
        security_id="security-quality-example",
        measured_session="2020-01-06",
        source_id=SOURCE_IDS[EvidenceSourceKind.DATA_QUALITY],
        source_sha256=SOURCE_HASHES[EvidenceSourceKind.DATA_QUALITY],
        components=rebuilt_components,
    )
    assert quality.q_data == Decimal("0.8")


def test_production_truth_refuses_measurement_omission_copy_tamper_and_source_mismatch():
    current, censored, labels = _c2_pair()
    census = tuple(_census_row("2020-01-06", index) for index in range(20))
    truth = _truth_artifact(current, censored, census)

    with pytest.raises(ProductionTruthError, match="do not exhaust"):
        build_production_truth_artifact(
            truth.c2_evidence_authority,
            production_evidence_receipt=truth.production_evidence_receipt,
            preopen_acquisition_receipt=truth.preopen_acquisition_receipt,
            source_bindings=truth.source_bindings,
            accepted_rows=truth.accepted_rows,
            refusals=truth.refusals,
            q_data_measurements=truth.q_data_measurements[:-1],
        )

    copied = copy.copy(truth)
    assert copied == truth and copied is not truth
    with pytest.raises(ProductionTruthError, match="builder-authenticated"):
        require_production_truth_artifact(copied)

    original = truth.terminal_projection_sha256
    object.__setattr__(truth, "terminal_projection_sha256", "f" * 64)
    try:
        with pytest.raises(ProductionTruthError, match="semantic binding"):
            require_production_truth_artifact(truth)
    finally:
        object.__setattr__(truth, "terminal_projection_sha256", original)
    assert require_production_truth_artifact(truth) is truth

    copied_census = tuple(list(truth.accepted_rows))
    with pytest.raises(ProductionScoringError, match="exact authenticated production truth"):
        build_production_scoring_authority(
            current,
            censored,
            _global_contract(),
            truth_artifact=truth,
            census_rows=copied_census,
            endpoint_labels=labels,
        )

    sources = list(truth.source_bindings)
    target = sources[2]
    sources[2] = build_production_truth_source_binding(
        kind=target.kind,
        artifact_id=target.artifact_id,
        artifact_sha256="f" * 64,
    )
    with pytest.raises(
        ProductionTruthError,
        match="security_master is not the physically reviewed acquisition source",
    ):
        build_production_truth_artifact(
            truth.c2_evidence_authority,
            production_evidence_receipt=truth.production_evidence_receipt,
            preopen_acquisition_receipt=truth.preopen_acquisition_receipt,
            source_bindings=tuple(sources),
            accepted_rows=truth.accepted_rows,
            refusals=truth.refusals,
            q_data_measurements=truth.q_data_measurements,
        )


def test_production_scoring_builds_paired_exhaustive_precontrol_census():
    authority, fold = _authority_and_fold()
    assert require_production_scoring_authority(authority) is authority
    batch = build_precontrol_scoring_batch(authority, fold)
    assert require_precontrol_scoring_batch(batch) is batch
    assert batch.eligible_census_count == 160
    assert len(batch.rows) + len(batch.refusals) == 160
    assert not batch.refusals
    assert {row.signal_arm for row in batch.rows} == set(SignalArm)
    assert {row.partition for row in batch.rows} == {
        FoldPartition.TRAIN,
        FoldPartition.VALIDATION,
    }
    assert all(row.state is ScoreState.ACTIVE for row in batch.rows)
    assert all(len(row.contributing_c2_row_sha256s) == 1 for row in batch.rows)
    assert all(len(row.contributions) == 1 for row in batch.rows)
    assert all(
        row.contributions[0].linked_c2_row_sha256s
        == row.contributing_c2_row_sha256s
        and row.contributions[0].publication_at_utc
        == "2020-01-02T09:31:00.000000Z"
        and row.contributions[0].firm_absolute_decayed_weight > 0
        for row in batch.rows
    )
    assert len({row.common_event_component_id for row in batch.rows}) == 40
    assert all(terminal.terminal_sha256 for terminal in batch.event_terminals)


def test_fit_and_apply_are_training_only_paired_and_keep_capabilities_closed():
    authority, fold = _authority_and_fold()
    batch = build_precontrol_scoring_batch(authority, fold)
    models = fit_production_control_models(batch)
    assert tuple(model.signal_arm for model in models) == tuple(SignalArm)
    assert all(model.active_training_rows == 60 for model in models)
    result = apply_production_control_models(batch, models)
    assert require_production_scoring_result(result) is result
    assert len(result.rows) == result.eligible_census_count == 160
    assert not result.refusals
    assert all(-4 <= row.firm_specific_score <= 4 for row in result.rows)
    assert all(-4 <= row.global_score <= 4 for row in result.rows)
    assert all(
        row.contributions
        == next(
            source.contributions
            for source in batch.rows
            if source.row_sha256 == row.precontrol_row_sha256
        )
        for row in result.rows
    )
    assert {
        result.provider_access,
        result.outcome_access,
        result.qc_access,
        result.deployment,
        result.orders,
        result.trading,
    } == {False}


def test_structural_zero_is_preserved_and_does_not_enter_active_fit():
    current, censored, labels = _c2_pair(count=19)
    census = tuple(
        _census_row(session, index)
        for session in ("2020-01-06", "2020-01-07", "2020-01-08")
        for index in range(20)
    )
    authority = _scoring_authority(current, censored, labels, census)
    fold = ProductionScoringFold(
        "arv2-zero-fold",
        "2020-01-06", "2020-01-09",
        "2020-01-09", "2020-01-10",
        "2020-01-10", "2020-01-13",
    )
    batch = build_precontrol_scoring_batch(authority, fold)
    zeros = [row for row in batch.rows if row.security_id == "security-19"]
    assert zeros and all(row.state is ScoreState.STRUCTURAL_ZERO for row in zeros)
    assert all(row.firm_reliable_score == row.global_reliable_score == 0 for row in zeros)
    assert all(not row.contributions for row in zeros)


def test_deduped_contribution_lineage_is_content_addressed_and_topology_pinned():
    authority, fold = _authority_and_fold()
    batch = build_precontrol_scoring_batch(authority, fold)
    row = batch.rows[0]
    contribution = row.contributions[0]
    assert contribution.representative_c2_row_sha256 in (
        contribution.linked_c2_row_sha256s
    )
    assert contribution.rating_action in {"upgrades", "downgrades"}
    assert contribution.lineage_sha256 == sha256_bytes(
        canonical_json_bytes(contribution.semantic_record())
    )
    with pytest.raises(ProductionScoringError, match="content-derived"):
        dataclasses.replace(
            contribution,
            firm_absolute_decayed_weight=(
                contribution.firm_absolute_decayed_weight + Decimal("1")
            ),
        )
    with pytest.raises(ProductionScoringError, match="rating action"):
        dataclasses.replace(contribution, rating_action="maintains")

    original = row.contributions
    clone = dataclasses.replace(contribution)
    assert clone == contribution and clone is not contribution
    object.__setattr__(row, "contributions", (clone, *original[1:]))
    try:
        with pytest.raises(ProductionScoringError, match="changed after authentication"):
            require_precontrol_scoring_batch(batch)
    finally:
        object.__setattr__(row, "contributions", original)
    assert require_precontrol_scoring_batch(batch) is batch


def test_dedupe_retains_missing_linked_publication_as_named_downstream_input():
    current, censored, labels = _c2_pair(
        count=21,
        duplicate_last_with_zero=True,
        missing_last_time=True,
    )
    census = tuple(_census_row("2020-01-06", index) for index in range(20))
    authority = _scoring_authority(current, censored, labels, census)
    fold = ProductionScoringFold(
        "arv2-publication-lineage-fold",
        "2020-01-06", "2020-01-07",
        "2020-01-07", "2020-01-08",
        "2020-01-08", "2020-01-09",
    )
    batch = build_precontrol_scoring_batch(authority, fold)
    rows = tuple(
        item
        for item in batch.rows
        if item.security_id == "security-00"
    )
    assert len(rows) == 2
    for row in rows:
        assert len(row.contributions) == 1
        contribution = row.contributions[0]
        assert contribution.representative_provider_event_id == "event-00"
        assert len(contribution.linked_c2_row_sha256s) == 2
        assert contribution.publication_at_utc is None
        assert contribution.firm_absolute_decayed_weight > 0


def test_mapped_and_refused_dedupe_siblings_have_one_terminal_each():
    current, _censored, labels = _c2_pair(
        count=21,
        duplicate_last_with_zero=True,
    )
    duplicate = next(
        item for item in labels if item.provider_event_id == "event-20"
    )
    refused = build_endpoint_label_evidence(
        c2_row_sha256=duplicate.c2_row_sha256,
        provider_event_id=duplicate.provider_event_id,
        raw_previous_label=duplicate.raw_previous_label,
        raw_current_label="Unknown Future Label",
        source_sha256=duplicate.source_sha256,
        available_at=duplicate.available_at,
    )
    changed = tuple(sorted(
        (refused, *(item for item in labels if item is not duplicate)),
        key=lambda item: item.c2_row_sha256,
    ))

    contributions, terminals = module._daily_contributions_from_inputs(
        _global_contract(), changed, current
    )
    by_event = {item.provider_event_id: item for item in terminals}
    original = by_event["event-00"]
    rejected = by_event["event-20"]

    assert len(terminals) == len(current.normalized_rows)
    assert len(by_event) == len(terminals)
    assert original.disposition is module.ScoreDisposition.INCLUDED_ACTIVE
    assert rejected.disposition is module.ScoreDisposition.GLOBAL_LABEL_REFUSED
    assert original.linked_c2_row_sha256s == (original.c2_row_sha256,)
    assert rejected.linked_c2_row_sha256s == (rejected.c2_row_sha256,)
    contribution = next(
        item for item in contributions if item.provider_event_id == "event-00"
    )
    assert contribution.linked_c2_row_sha256s == (original.c2_row_sha256,)


def test_firm_dedupe_conflict_precedes_global_label_exclusion():
    current, _censored, labels = _c2_pair(
        count=21,
        duplicate_last_with_zero=True,
    )
    duplicate_row = next(
        item for item in current.normalized_rows
        if item.provider_event_id == "event-20"
    )
    conflicting_row = copy.copy(duplicate_row)
    object.__setattr__(conflicting_row, "previous_score", Fraction(-9, 10))
    object.__setattr__(conflicting_row, "current_score", Fraction(9, 10))
    object.__setattr__(conflicting_row, "rating_change", Fraction(9, 5))
    rows = tuple(
        conflicting_row if item is duplicate_row else item
        for item in current.normalized_rows
    )
    duplicate_label = next(
        item for item in labels if item.provider_event_id == "event-20"
    )
    refused_label = build_endpoint_label_evidence(
        c2_row_sha256=duplicate_label.c2_row_sha256,
        provider_event_id=duplicate_label.provider_event_id,
        raw_previous_label=duplicate_label.raw_previous_label,
        raw_current_label="Unknown Future Label",
        source_sha256=duplicate_label.source_sha256,
        available_at=duplicate_label.available_at,
    )
    changed_labels = tuple(sorted(
        (refused_label, *(item for item in labels if item is not duplicate_label)),
        key=lambda item: item.c2_row_sha256,
    ))

    contributions, terminals = module._daily_contributions_from_inputs(
        _global_contract(),
        changed_labels,
        SimpleNamespace(
            normalized_rows=rows,
            signal_arm=current.signal_arm,
        ),
    )
    by_event = {item.provider_event_id: item for item in terminals}

    assert by_event["event-00"].disposition is module.ScoreDisposition.DAILY_DEDUPE_CONFLICT
    assert by_event["event-20"].disposition is module.ScoreDisposition.DAILY_DEDUPE_CONFLICT
    assert not any(
        item.security_id == "security-00" for item in contributions
    )


def test_global_label_refusal_is_named_and_excluded_from_both_score_families():
    current, censored, labels = _c2_pair()
    target = labels[0]
    replacement = build_endpoint_label_evidence(
        c2_row_sha256=target.c2_row_sha256,
        provider_event_id=target.provider_event_id,
        raw_previous_label=target.raw_previous_label,
        raw_current_label="Unknown Future Label",
        source_sha256=target.source_sha256,
        available_at=target.available_at,
    )
    # Binding to C2 raw labels refuses caller-side substitution before scoring.
    changed = tuple(sorted((replacement, *labels[1:]), key=lambda item: item.c2_row_sha256))
    census = tuple(_census_row("2020-01-06", index) for index in range(20))
    with pytest.raises(ProductionScoringError, match="not exact"):
        _scoring_authority(current, censored, changed, census)


def test_authority_rejects_incomplete_census_and_mismatched_permanent_identity():
    current, censored, labels = _c2_pair()
    census = tuple(_census_row("2020-01-06", index) for index in range(20))
    with pytest.raises(ProductionScoringError, match="no matching"):
        _scoring_authority(current, censored, labels, census[1:])
    hostile = list(census)
    hostile[0] = build_eligible_security_session(
        decision_session="2020-01-06",
        security_id="security-00",
        issuer_id="issuer-wrong",
        share_class_id="share-00",
        listing_id="listing-00",
        historical_ticker="S00",
        sector_id="sector-one",
        industry_id="industry-one",
        q_data=Decimal("0.9"),
        controls=_control_vector(0),
        source_id="pit-census-source-1",
        source_sha256="a" * 64,
        identity_evidence_sha256="b" * 64,
        identity_available_at="2020-01-06T13:00:00.000000Z",
        classification_evidence_sha256="c" * 64,
        classification_available_at="2020-01-06T13:00:00.000000Z",
        q_data_evidence_sha256="d" * 64,
        q_data_available_at="2020-01-06T13:00:00.000000Z",
        control_evidence_sha256="e" * 64,
        control_available_at="2020-01-06T13:00:00.000000Z",
    )
    with pytest.raises(ProductionScoringError, match="permanent census identity"):
        _scoring_authority(current, censored, labels, tuple(hostile))


def test_static_scoring_contract_and_formal_nominal_folds_are_content_pinned(monkeypatch):
    rendered = render_scoring_contract_bytes()
    assert sha256_bytes(rendered) == SCORING_CONTRACT_SHA256
    assert SCORING_CONTRACT_ID.endswith(SCORING_CONTRACT_SHA256[:16])
    fold = build_formal_production_scoring_fold(2020)
    assert fold.to_record() == {
        "fold_id": "arv2-wf-test-2020",
        "train_start": "2013-01-02",
        "train_end_exclusive": "2018-01-02",
        "validation_start": "2018-01-03",
        "validation_end_exclusive": "2020-01-02",
        "test_start": "2020-01-03",
        "test_end_exclusive": "2021-01-04",
    }
    with pytest.raises(ProductionScoringError, match="2020 through 2025"):
        build_formal_production_scoring_fold(True)

    calls = 0

    def hostile_sum(_values):
        nonlocal calls
        calls += 1
        return Decimal(0)

    monkeypatch.setattr(module, "_stable_sum", hostile_sum)
    with pytest.raises(ProductionScoringError, match="callable contract"):
        render_scoring_contract_bytes()
    assert calls == 0


def test_all_24_formal_horizon_boundaries_equal_the_reviewed_fold_artifact():
    document = json.loads(
        (SPEC_ROOT / FILENAMES["folds"]).read_text(encoding="utf-8")
    )
    expected = tuple(
        (
            fold["fold_id"],
            boundary["horizon_sessions"],
            boundary["train_start"],
            boundary["train_end_exclusive"],
            boundary["validation_start"],
            boundary["validation_end_exclusive"],
            boundary["test_start"],
            boundary["test_end_exclusive"],
        )
        for fold in document["walk_forward_contract"]["folds"]
        for boundary in fold["horizon_boundaries"]
    )
    assert module.FORMAL_HORIZON_FOLD_BOUNDARIES == expected
    assert len(expected) == 24
    assert tuple(
        formal_horizon_fold_boundary(fold_id, horizon)
        for fold_id in module.FORMAL_PRIMARY_FOLD_IDS
        for horizon in (1, 5, 20, 60)
    ) == expected
    assert formal_horizon_fold_boundary("arv2-wf-test-2025", 60)[6:] == (
        "2025-04-01",
        "2026-01-02",
    )
    for fold_id, horizon in (("unknown", 20), ("arv2-wf-test-2020", True)):
        with pytest.raises(ProductionScoringError, match="formal horizon"):
            formal_horizon_fold_boundary(fold_id, horizon)


def test_paired_sector_zero_mad_totalizes_only_an_exact_zero_range():
    members = tuple(f"security-{index:02d}" for index in range(20))
    active = set(members[:5])
    normalized, reason = module._normalize_sector(
        {security_id: Decimal(0) for security_id in members}, active, members
    )
    assert reason is None
    assert normalized == {security_id: Decimal(0) for security_id in members}

    nonconstant = {security_id: Decimal(0) for security_id in members}
    nonconstant[members[-1]] = Decimal(1)
    normalized, reason = module._normalize_sector(nonconstant, active, members)
    assert normalized is None
    assert reason is module.ScoreDisposition.SECTOR_ZERO_MAD_FIRM


def test_named_census_refusals_are_exhaustive_and_charge_control_coverage():
    current, censored, labels = _c2_pair()
    census = tuple(_census_row("2020-01-06", index) for index in range(20))
    fold = ProductionScoringFold(
        "arv2-refusal-fold",
        "2020-01-06", "2020-01-07",
        "2020-01-07", "2020-01-08",
        "2020-01-08", "2020-01-09",
    )
    contract = _global_contract()
    for refusal_count in (1, 2):
        refused = tuple(
            _refused_census_row("2020-01-06", index)
            for index in range(20, 20 + refusal_count)
        )
        truth = _truth_artifact(current, censored, census, refused)
        authority = build_production_scoring_authority(
            current,
            censored,
            contract,
            truth_artifact=truth,
            census_rows=truth.accepted_rows,
            census_refusals=truth.refusals,
            endpoint_labels=labels,
        )
        batch = build_precontrol_scoring_batch(authority, fold)
        assert batch.eligible_census_count == (20 + refusal_count) * 2
        census_refusals = tuple(
            item
            for item in batch.refusals
            if item.disposition is module.ScoreDisposition.CENSUS_EVIDENCE_REFUSAL
        )
        assert len(census_refusals) == refusal_count * 2
        if refusal_count == 1:
            assert len(batch.rows) == 40
            assert len(batch.refusals) == 2
        else:
            assert not batch.rows
            assert len(batch.refusals) == 44
            assert sum(
                item.disposition is module.ScoreDisposition.CONTROL_DATE_UNDERFILLED
                for item in batch.refusals
            ) == 40


def test_equal_value_container_substitution_is_refused_by_authority_topology():
    authority, _ = _authority_and_fold()
    original = authority.census_rows
    clone = dataclasses.replace(original[0])
    assert clone == original[0] and clone is not original[0]
    object.__setattr__(authority, "census_rows", (clone, *original[1:]))
    try:
        with pytest.raises(ProductionScoringError, match="changed after authentication"):
            require_production_scoring_authority(authority)
    finally:
        object.__setattr__(authority, "census_rows", original)
    assert require_production_scoring_authority(authority) is authority


def test_scoring_hashes_do_not_depend_on_the_ambient_decimal_context():
    authority, fold = _authority_and_fold()
    baseline_batch = build_precontrol_scoring_batch(authority, fold)
    baseline_models = fit_production_control_models(baseline_batch)
    baseline = apply_production_control_models(baseline_batch, baseline_models)
    hostile = Context(prec=6, rounding=ROUND_DOWN, Emin=-99, Emax=99, capitals=0, clamp=1)
    with localcontext(hostile):
        candidate_batch = build_precontrol_scoring_batch(authority, fold)
        candidate_models = fit_production_control_models(candidate_batch)
        candidate = apply_production_control_models(candidate_batch, candidate_models)
    assert candidate_batch.batch_sha256 == baseline_batch.batch_sha256
    assert tuple(item.model_sha256 for item in candidate_models) == tuple(
        item.model_sha256 for item in baseline_models
    )
    assert candidate.result_sha256 == baseline.result_sha256
