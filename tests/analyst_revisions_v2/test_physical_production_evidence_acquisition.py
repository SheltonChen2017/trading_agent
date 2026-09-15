from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import (
    physical_production_evidence_acquisition as acquisition,
)
from research.analyst_revisions_v2_qc import (
    physical_production_evidence_bridge as bridge_module,
)
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    OwnerSignatureAuthority,
)
from research.analyst_revisions_v2_qc.physical_production_input_archive import (
    build_test_fixture_physical_production_input_archive,
)
from tests.analyst_revisions_v2.test_production_input_pipeline import _authority


def _exact(message: str) -> str:
    return f"^{re.escape(message)}$"


@pytest.fixture()
def receipt_fixture(monkeypatch, tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    c2 = build_test_fixture_physical_production_input_archive(
        _authority(), output_root=tmp_path
    )
    bridge = object.__new__(bridge_module.PhysicalProductionEvidenceBridge)
    fields = {
        "bridge_id": "arv2-physical-evidence-test",
        "bridge_sha256": "a" * 64,
        "accepted_risk_archive_id": "accepted-risk-test",
        "accepted_risk_archive_sha256": "b" * 64,
        "production_input_archive": c2,
        "preopen_acquisition_receipt": SimpleNamespace(
            control_sessions=(
                SimpleNamespace(decision_session="2020-01-06"),
            )
        ),
        "preopen_acquisition_id": "preopen-acquisition-test",
        "preopen_acquisition_sha256": "c" * 64,
        "composition_terminal_projection_sha256": "d" * 64,
    }
    for name, value in fields.items():
        object.__setattr__(bridge, name, value)
    pending = canonical_json_bytes(
        {
            "schema": "arv2-physical-production-evidence-review-candidate-v1",
            "bridge_id": bridge.bridge_id,
            "production_input_archive_sha256": c2.archive_sha256,
            "status": "pending",
        }
    )
    monkeypatch.setattr(acquisition, "_require_dependencies", lambda: None)
    monkeypatch.setattr(
        acquisition._bridge_module,
        "require_physical_production_evidence_bridge",
        lambda value: value,
    )
    monkeypatch.setattr(
        acquisition._bridge_module,
        "render_physical_production_evidence_review_candidate",
        lambda _value: pending,
    )
    monkeypatch.setattr(
        acquisition._c2_module,
        "require_reviewable_physical_production_archive",
        lambda value: value,
    )
    owner_signature = object.__new__(OwnerSignatureAuthority)
    object.__setattr__(
        owner_signature, "authority_id", "arv2-owner-signature-test"
    )
    object.__setattr__(owner_signature, "authority_sha256", "e" * 64)
    return bridge, c2, pending, owner_signature


def test_affirmative_review_payload_is_exact_but_does_not_mint_authority(
    receipt_fixture,
):
    bridge, c2, pending, _owner_signature = receipt_fixture

    payload = (
        acquisition
        .render_physical_production_evidence_owner_review_payload_candidate(bridge)
    )
    raw = json.loads(payload)

    assert raw["status"] == (
        "independently_reviewed_private_physical_production_evidence"
    )
    assert raw["review_candidate_sha256"] == acquisition.sha256_bytes(pending)
    assert raw["production_input_archive_sha256"] == c2.archive_sha256
    assert raw["complete_member_census_verified"] is True
    assert raw["contains_outcome_or_price"] is False
    assert not acquisition._RECEIPTS


def test_owner_authenticated_receipt_owns_exact_disk_c2_without_pair_graph(
    monkeypatch, receipt_fixture
):
    bridge, c2, _pending, owner_signature = receipt_fixture
    pin = (
        acquisition
        .render_physical_production_evidence_owner_review_payload_candidate(bridge)
    )
    calls = []

    def require_signature(value, *, authority_payload):
        assert value is owner_signature
        assert authority_payload == pin
        calls.append(authority_payload)
        return value

    monkeypatch.setattr(
        acquisition,
        "require_production_evidence_review_owner_signature",
        require_signature,
    )
    receipt = acquisition.load_physically_reviewed_production_evidence_receipt(
        bridge=bridge,
        review_pin_bytes=pin,
        owner_signature=owner_signature,
    )

    assert acquisition.require_reviewed_physical_production_evidence_receipt(
        receipt
    ) is receipt
    assert receipt.production_input_archive is c2
    assert receipt.independently_reviewed is True
    assert receipt.owner_signature_verified is True
    assert receipt.disk_backed_archive is True
    assert receipt.full_pair_materialized is False
    assert receipt.full_evidence_materialized is False
    assert receipt.outcome_access is False
    assert receipt.quantconnect_access is False
    assert len(calls) >= 2
    with pytest.raises(
        acquisition.PhysicalProductionEvidenceAcquisitionError,
        match=_exact("physical production-evidence review pin was already spent"),
    ):
        acquisition.load_physically_reviewed_production_evidence_receipt(
            bridge=bridge,
            review_pin_bytes=pin,
            owner_signature=owner_signature,
        )


def test_review_pin_substitution_is_rejected_before_signature(
    monkeypatch, receipt_fixture
):
    bridge, _c2, _pending, owner_signature = receipt_fixture
    pin = (
        acquisition
        .render_physical_production_evidence_owner_review_payload_candidate(bridge)
    )
    altered = pin.replace(b'"evidence_row_count":2', b'"evidence_row_count":3')
    called = False

    def require_signature(*_args, **_kwargs):
        nonlocal called
        called = True
        return owner_signature

    monkeypatch.setattr(
        acquisition,
        "require_production_evidence_review_owner_signature",
        require_signature,
    )
    with pytest.raises(
        acquisition.PhysicalProductionEvidenceAcquisitionError,
        match=_exact(
            "physical production-evidence review pin does not bind exact C2"
        ),
    ):
        acquisition.load_physically_reviewed_production_evidence_receipt(
            bridge=bridge,
            review_pin_bytes=altered,
            owner_signature=owner_signature,
        )
    assert called is False


def test_pending_review_candidate_cannot_mint_receipt_or_reach_signature(
    monkeypatch, receipt_fixture
):
    bridge, _c2, pending, owner_signature = receipt_fixture
    called = False

    def require_signature(*_args, **_kwargs):
        nonlocal called
        called = True
        return owner_signature

    monkeypatch.setattr(
        acquisition,
        "require_production_evidence_review_owner_signature",
        require_signature,
    )
    with pytest.raises(
        acquisition.PhysicalProductionEvidenceAcquisitionError,
        match=_exact(
            "physical production-evidence review pin does not bind exact C2"
        ),
    ):
        acquisition.load_physically_reviewed_production_evidence_receipt(
            bridge=bridge,
            review_pin_bytes=pending,
            owner_signature=owner_signature,
        )
    assert called is False


def test_invalid_owner_signature_is_a_named_refusal(
    monkeypatch, receipt_fixture
):
    bridge, _c2, _pending, owner_signature = receipt_fixture
    pin = (
        acquisition
        .render_physical_production_evidence_owner_review_payload_candidate(bridge)
    )

    def reject_signature(*_args, **_kwargs):
        raise TypeError("invalid test signature")

    monkeypatch.setattr(
        acquisition,
        "require_production_evidence_review_owner_signature",
        reject_signature,
    )
    with pytest.raises(
        acquisition.PhysicalProductionEvidenceAcquisitionError,
        match=_exact(
            "physical production-evidence review lacks owner signature"
        ),
    ):
        acquisition.load_physically_reviewed_production_evidence_receipt(
            bridge=bridge,
            review_pin_bytes=pin,
            owner_signature=owner_signature,
        )


def _section72_bridge(monkeypatch, receipt_fixture):
    bridge, c2, pending, owner_signature = receipt_fixture
    values = {
        "firm_authority_mode": bridge_module.SECTION72_FIRM_AUTHORITY_MODE,
        "historical_availability_claimed": False,
        "owner_waiver_signature_required": True,
        "owner_waiver_scope": bridge_module.SECTION72_OWNER_WAIVER_SCOPE,
        "owner_waived_firm_admission_id": "arv2-section72-firm-admission-test",
        "owner_waived_firm_admission_sha256": "1" * 64,
        "firm_owner_decision_id": "arv2-firm-owner-decision-test",
        "firm_owner_decision_sha256": "2" * 64,
        "firm_refusal_ledger_id": "arv2-firm-refusal-ledger-test",
        "firm_refusal_ledger_sha256": "3" * 64,
    }
    for name, value in values.items():
        object.__setattr__(bridge, name, value)
    monkeypatch.setattr(
        acquisition._bridge_module,
        "section72_owner_waived_preopen_session_axis",
        lambda value: ("2020-01-06",) if value is bridge else (),
    )
    return bridge, c2, pending, owner_signature


def test_section72_owner_waiver_receipt_is_explicitly_not_independent(
    monkeypatch, receipt_fixture
):
    bridge, c2, _pending, owner_signature = _section72_bridge(
        monkeypatch, receipt_fixture
    )
    pin = acquisition.render_section72_owner_waived_production_evidence_payload_candidate(
        bridge
    )
    calls = []

    def require_signature(value, *, authority_payload):
        assert value is owner_signature
        assert authority_payload == pin
        calls.append(True)
        return value

    monkeypatch.setattr(
        acquisition,
        "require_production_evidence_review_owner_signature",
        require_signature,
    )
    receipt = acquisition.load_section72_owner_waived_production_evidence_receipt(
        bridge=bridge,
        review_pin_bytes=pin,
        owner_signature=owner_signature,
    )

    assert acquisition.require_section72_owner_waived_production_evidence_receipt(
        receipt
    ) is receipt
    assert receipt.production_input_archive is c2
    assert receipt.review_mode == acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE
    assert receipt.independently_reviewed is False
    assert receipt.owner_signature_verified is True
    assert receipt.owner_review_waived is True
    assert receipt.historical_availability_claimed is False
    assert receipt.post_first_formal_backtest_independent_review_required is True
    assert receipt.owner_waived_firm_admission_id == (
        bridge.owner_waived_firm_admission_id
    )
    assert receipt.firm_owner_decision_sha256 == bridge.firm_owner_decision_sha256
    assert receipt.firm_refusal_ledger_sha256 == bridge.firm_refusal_ledger_sha256
    assert receipt.session_axis == ("2020-01-06",)
    assert calls
    with pytest.raises(
        acquisition.PhysicalProductionEvidenceAcquisitionError,
        match=_exact(
            "physical production-evidence receipt is not independently owner reviewed"
        ),
    ):
        acquisition.require_reviewed_physical_production_evidence_receipt(receipt)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("firm_authority_mode", bridge_module.NORMAL_FIRM_AUTHORITY_MODE),
        ("historical_availability_claimed", True),
        ("owner_waiver_signature_required", False),
        ("owner_waiver_scope", "wrong-scope"),
    ),
)
def test_section72_payload_isolates_every_bridge_policy_guard(
    monkeypatch, receipt_fixture, field, value
):
    bridge, _c2, _pending, _owner_signature = _section72_bridge(
        monkeypatch, receipt_fixture
    )
    object.__setattr__(bridge, field, value)
    with pytest.raises(
        acquisition.PhysicalProductionEvidenceAcquisitionError,
        match=_exact("section-72 review pin requires exact owner-waived bridge"),
    ):
        acquisition.render_section72_owner_waived_production_evidence_payload_candidate(
            bridge
        )


def test_section72_pin_substitution_refuses_before_owner_signature(
    monkeypatch, receipt_fixture
):
    bridge, _c2, _pending, owner_signature = _section72_bridge(
        monkeypatch, receipt_fixture
    )
    pin = acquisition.render_section72_owner_waived_production_evidence_payload_candidate(
        bridge
    )
    altered = pin.replace(b'"evidence_row_count":2', b'"evidence_row_count":3')
    calls = []
    monkeypatch.setattr(
        acquisition,
        "require_production_evidence_review_owner_signature",
        lambda *_args, **_kwargs: calls.append(True),
    )
    with pytest.raises(
        acquisition.PhysicalProductionEvidenceAcquisitionError,
        match=_exact(
            "section-72 production-evidence pin does not bind exact C2"
        ),
    ):
        acquisition.load_section72_owner_waived_production_evidence_receipt(
            bridge=bridge,
            review_pin_bytes=altered,
            owner_signature=owner_signature,
        )
    assert calls == []


def test_fixture_receipt_is_explicitly_ineligible_for_reviewed_consumers(
    receipt_fixture,
):
    bridge, _c2, _pending, owner_signature = receipt_fixture
    pin = (
        acquisition
        .render_physical_production_evidence_owner_review_payload_candidate(bridge)
    )
    receipt = acquisition._load_test_fixture_physical_production_evidence_receipt(
        bridge=bridge,
        review_pin_bytes=pin,
        owner_signature=owner_signature,
    )

    assert (
        acquisition.require_physical_production_evidence_receipt(receipt)
        is receipt
    )
    assert receipt.fixture_only is True
    assert receipt.independently_reviewed is False
    with pytest.raises(
        acquisition.PhysicalProductionEvidenceAcquisitionError,
        match=_exact(
            "physical production-evidence receipt is not independently owner reviewed"
        ),
    ):
        acquisition.require_reviewed_physical_production_evidence_receipt(receipt)


def test_receipt_mutation_loses_builder_authority(receipt_fixture):
    bridge, _c2, _pending, owner_signature = receipt_fixture
    pin = (
        acquisition
        .render_physical_production_evidence_owner_review_payload_candidate(bridge)
    )
    receipt = acquisition._load_test_fixture_physical_production_evidence_receipt(
        bridge=bridge,
        review_pin_bytes=pin,
        owner_signature=owner_signature,
    )
    object.__setattr__(receipt, "row_projection_sha256", "f" * 64)

    with pytest.raises(
        acquisition.PhysicalProductionEvidenceAcquisitionError,
        match=_exact(
            "physical production-evidence receipt lost builder authority"
        ),
    ):
        acquisition.require_physical_production_evidence_receipt(receipt)


def test_receipt_builder_authority_is_process_local(
    monkeypatch, receipt_fixture
):
    bridge, _c2, _pending, owner_signature = receipt_fixture
    pin = (
        acquisition
        .render_physical_production_evidence_owner_review_payload_candidate(bridge)
    )
    receipt = acquisition._load_test_fixture_physical_production_evidence_receipt(
        bridge=bridge,
        review_pin_bytes=pin,
        owner_signature=owner_signature,
    )
    builder_pid = os.getpid()
    monkeypatch.setattr(acquisition.os, "getpid", lambda: builder_pid + 1)

    with pytest.raises(
        acquisition.PhysicalProductionEvidenceAcquisitionError,
        match=_exact(
            "physical production-evidence receipt lost builder authority"
        ),
    ):
        acquisition.require_physical_production_evidence_receipt(receipt)


def test_late_receipt_reauthentication_failure_does_not_burn_review_pin(
    monkeypatch, receipt_fixture
):
    bridge, _c2, _pending, owner_signature = receipt_fixture
    pin = (
        acquisition
        .render_physical_production_evidence_owner_review_payload_candidate(bridge)
    )
    pin_sha256 = json.loads(pin)["pin_sha256"]
    acquisition._SPENT_REVIEW_PINS.discard(pin_sha256)
    observed = []

    monkeypatch.setattr(
        acquisition,
        "require_production_evidence_review_owner_signature",
        lambda value, *, authority_payload: value,
    )
    original_require = acquisition.require_physical_production_evidence_receipt

    def reject_late(value):
        observed.append(value)
        raise acquisition.PhysicalProductionEvidenceAcquisitionError(
            "injected late receipt reauthentication failure"
        )

    with monkeypatch.context() as patch:
        patch.setattr(
            acquisition,
            "require_physical_production_evidence_receipt",
            reject_late,
        )
        with pytest.raises(
            acquisition.PhysicalProductionEvidenceAcquisitionError,
            match=_exact("injected late receipt reauthentication failure"),
        ):
            acquisition.load_physically_reviewed_production_evidence_receipt(
                bridge=bridge,
                review_pin_bytes=pin,
                owner_signature=owner_signature,
            )

    assert pin_sha256 not in acquisition._SPENT_REVIEW_PINS
    assert len(observed) == 1
    assert id(observed[0]) not in acquisition._RECEIPTS
    assert acquisition.require_physical_production_evidence_receipt is original_require

    receipt = acquisition.load_physically_reviewed_production_evidence_receipt(
        bridge=bridge,
        review_pin_bytes=pin,
        owner_signature=owner_signature,
    )
    assert acquisition.require_physical_production_evidence_receipt(receipt) is receipt
    assert pin_sha256 in acquisition._SPENT_REVIEW_PINS


def test_acquisition_dependency_rebinding_is_a_named_refusal(monkeypatch):
    monkeypatch.setattr(
        acquisition._bridge_module,
        "render_physical_production_evidence_review_candidate",
        lambda _value: b"{}\n",
    )
    with pytest.raises(
        acquisition.PhysicalProductionEvidenceAcquisitionError,
        match=_exact(
            "physical production-evidence acquisition dependency changed"
        ),
    ):
        acquisition._require_dependencies()
