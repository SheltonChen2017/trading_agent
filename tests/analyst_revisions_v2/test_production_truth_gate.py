from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from research.analyst_revisions_v2.production_scoring import (
    ProductionScoringError,
    build_eligible_security_session,
    build_production_scoring_authority,
)
from research.analyst_revisions_v2.production_evidence_acquisition import (
    ProductionEvidenceAcquisitionError,
    render_production_evidence_external_review_pin_candidate,
)
import research.analyst_revisions_v2.production_evidence_acquisition as evidence_core
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2.production_truth_gate import (
    ProductionTruthError,
    TruthSourceKind,
    build_derived_data_quality_evidence,
    build_production_truth_artifact,
    build_production_truth_source_binding,
    build_quality_component_evidence,
    derive_c2_quality_component_projections,
)
from research.analyst_revisions_v2_qc.production_evidence_acquisition_io import (
    ProductionEvidenceAcquisitionIoError,
    load_physically_reviewed_production_evidence_receipt,
)

from .test_production_scoring import (
    _c2_pair,
    _census_row,
    _global_contract,
    _install_offline_physical_receipt_requires,
    _offline_owner_signature,
    _offline_signed_loader,
    _PRODUCTION_PREOPEN_REQUIRE,
    _refused_census_row,
    _truth_artifact,
)


def test_admitted_event_cannot_cross_a_refused_eligibility_terminal() -> None:
    current, censored, labels = _c2_pair()
    accepted = tuple(
        _census_row("2020-01-06", index) for index in range(1, 20)
    )
    truth = _truth_artifact(
        current,
        censored,
        accepted,
        (_refused_census_row("2020-01-06", 0),),
    )

    with pytest.raises(
        ProductionScoringError,
        match="admitted C2 event has a refused eligible-session census terminal",
    ):
        build_production_scoring_authority(
            current,
            censored,
            _global_contract(),
            truth_artifact=truth,
            census_rows=truth.accepted_rows,
            census_refusals=truth.refusals,
            endpoint_labels=labels,
        )


def _write_private_pair(package_bytes: bytes, pin_bytes: bytes):
    directory = tempfile.TemporaryDirectory(dir="/private/tmp")
    package_path = Path(directory.name) / "production-evidence-package.json"
    pin_path = Path(directory.name) / "production-evidence-review-pin.json"
    package_path.write_bytes(package_bytes)
    pin_path.write_bytes(pin_bytes)
    os.chmod(package_path, 0o600)
    os.chmod(pin_path, 0o600)
    return directory, package_path, pin_path


def test_public_production_evidence_pin_candidate_cannot_self_authorize(
    monkeypatch,
) -> None:
    current, censored, _labels = _c2_pair()
    census = tuple(_census_row("2020-01-06", index) for index in range(20))
    truth = _truth_artifact(current, censored, census)
    receipt = truth.production_evidence_receipt
    candidate = render_production_evidence_external_review_pin_candidate(
        authority=truth.c2_evidence_authority,
        preopen_acquisition_receipt=truth.preopen_acquisition_receipt,
        package_bytes=receipt.package_bytes,
    )
    directory, package_path, pin_path = _write_private_pair(
        receipt.package_bytes, candidate
    )
    try:
        with monkeypatch.context() as patch:
            patch.setattr(
                evidence_core,
                "require_reviewed_preopen_control_acquisition_receipt",
                _PRODUCTION_PREOPEN_REQUIRE,
            )
            with pytest.raises(
                ProductionEvidenceAcquisitionIoError,
                match="failed physical authentication",
            ):
                load_physically_reviewed_production_evidence_receipt(
                    authority=truth.c2_evidence_authority,
                    preopen_acquisition_receipt=truth.preopen_acquisition_receipt,
                    package_path=package_path,
                    external_review_pin_path=pin_path,
                    owner_signature=None,
                )
    finally:
        directory.cleanup()


def test_physical_production_evidence_member_tamper_is_refused() -> None:
    current, censored, _labels = _c2_pair()
    census = tuple(_census_row("2020-01-06", index) for index in range(20))
    truth = _truth_artifact(current, censored, census)
    receipt = truth.production_evidence_receipt
    package = json.loads(receipt.package_bytes)
    firm = next(
        item["firm"] for item in package["row_evidence"]
        if item["firm"] is not None
    )
    firm["institution_id"] = firm["institution_id"] + "-tampered"
    tampered_package = canonical_json_bytes(package)
    directory, package_path, pin_path = _write_private_pair(
        tampered_package, receipt.review_pin_bytes
    )
    try:
        with pytest.raises(ProductionEvidenceAcquisitionError):
            _offline_signed_loader(
                load_physically_reviewed_production_evidence_receipt
            )(
                authority=truth.c2_evidence_authority,
                preopen_acquisition_receipt=truth.preopen_acquisition_receipt,
                package_path=package_path,
                external_review_pin_path=pin_path,
                owner_signature=_offline_owner_signature(),
            )
    finally:
        directory.cleanup()


def test_non_event_day_q_data_cannot_be_replaced_by_caller_evidence() -> None:
    current, censored, _labels = _c2_pair()
    census = tuple(
        _census_row(session, index)
        for session in ("2020-01-06", "2020-01-07")
        for index in range(20)
    )
    truth = _truth_artifact(current, censored, census)
    c2_keys = {
        (item.measured_session, item.security_id)
        for item in derive_c2_quality_component_projections(
            truth.c2_evidence_authority.pair,
            truth.c2_evidence_authority.row_evidence,
        )
    }
    target_index = next(
        index for index, item in enumerate(truth.q_data_measurements)
        if item.measured_session == "2020-01-07"
        and (item.measured_session, item.security_id) not in c2_keys
    )
    original_measurement = truth.q_data_measurements[target_index]
    replacement_components = tuple(
        build_quality_component_evidence(
            kind=item.kind,
            value=Decimal("0.1"),
            source_id=item.source_id,
            source_sha256=item.source_sha256,
            payload_sha256=item.payload_sha256,
            available_at=item.available_at,
        )
        for item in original_measurement.components
    )
    replacement_measurement = build_derived_data_quality_evidence(
        security_id=original_measurement.security_id,
        measured_session=original_measurement.measured_session,
        source_id=original_measurement.source_id,
        source_sha256=original_measurement.source_sha256,
        components=replacement_components,
    )
    original_terminal = truth.accepted_rows[target_index]
    replacement_terminal = build_eligible_security_session(
        decision_session=original_terminal.decision_session,
        security_id=original_terminal.security_id,
        issuer_id=original_terminal.issuer_id,
        share_class_id=original_terminal.share_class_id,
        listing_id=original_terminal.listing_id,
        historical_ticker=original_terminal.historical_ticker,
        sector_id=original_terminal.sector_id,
        industry_id=original_terminal.industry_id,
        q_data=replacement_measurement.q_data,
        controls=original_terminal.controls,
        source_id=original_terminal.source_id,
        source_sha256=original_terminal.source_sha256,
        identity_evidence_sha256=original_terminal.identity_evidence_sha256,
        identity_available_at=original_terminal.identity_available_at,
        classification_evidence_sha256=(
            original_terminal.classification_evidence_sha256
        ),
        classification_available_at=original_terminal.classification_available_at,
        q_data_evidence_sha256=replacement_measurement.evidence_sha256,
        q_data_available_at=replacement_measurement.available_at,
        control_evidence_sha256=original_terminal.control_evidence_sha256,
        control_available_at=original_terminal.control_available_at,
    )
    accepted = list(truth.accepted_rows)
    accepted[target_index] = replacement_terminal
    accepted_tuple = tuple(accepted)
    measurements = list(truth.q_data_measurements)
    measurements[target_index] = replacement_measurement
    measurement_tuple = tuple(measurements)
    sources = list(truth.source_bindings)
    universe_index = next(
        index for index, item in enumerate(sources)
        if item.kind is TruthSourceKind.ELIGIBLE_UNIVERSE
    )
    universe = sources[universe_index]
    sources[universe_index] = build_production_truth_source_binding(
        kind=universe.kind,
        artifact_id=universe.artifact_id,
        artifact_sha256=universe.artifact_sha256,
        accepted_rows=accepted_tuple,
        refusals=truth.refusals,
    )

    with pytest.raises(
        ProductionTruthError,
        match="exact physically acquired same-key evidence",
    ):
        build_production_truth_artifact(
            truth.c2_evidence_authority,
            production_evidence_receipt=truth.production_evidence_receipt,
            preopen_acquisition_receipt=truth.preopen_acquisition_receipt,
            source_bindings=tuple(sources),
            accepted_rows=accepted_tuple,
            refusals=truth.refusals,
            q_data_measurements=measurement_tuple,
        )


def test_formal_session_geometry_refuses_fold_boundaries_outside_reviewed_bounds(
    monkeypatch,
):
    """The reviewed 2013..2025 bounds must hold even if the fold constant drifts."""

    from research.analyst_revisions_v2 import production_truth_gate as gate

    def shifted(boundaries, *, train_start=None, test_end=None):
        return tuple(
            (
                fold_id,
                train_start or original_train_start,
                train_end,
                validation_start,
                validation_end,
                test_start,
                test_end or original_test_end,
            )
            for (
                fold_id,
                original_train_start,
                train_end,
                validation_start,
                validation_end,
                test_start,
                original_test_end,
            ) in boundaries
        )

    reviewed = gate.FORMAL_FOLD_BOUNDARIES
    assert gate._formal_session_geometry()[0] == gate.HISTORY_START

    for drifted in (
        shifted(reviewed, train_start="2014-01-02"),
        shifted(reviewed, test_end="2026-07-01"),
    ):
        monkeypatch.setattr(gate, "FORMAL_FOLD_BOUNDARIES", drifted)
        with pytest.raises(
            gate.ProductionTruthError,
            match="formal truth geometry escaped reviewed 2013..2025 bounds",
        ):
            gate._formal_session_geometry()
