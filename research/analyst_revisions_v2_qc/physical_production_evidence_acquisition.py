"""Owner-reviewed authority for the disk-backed ARV2 production C2 archive.

The legacy production-evidence acquisition receipt retains a decoded
``ProductionEvidenceAuthority`` and its complete package bytes.  A physical
C2 package can be larger than that in-memory boundary.  This module instead
binds either the normal independently reviewed decision or the exact bounded
section-72 owner waiver to the ``PhysicalProductionEvidenceBridge`` and its
authenticated C2 archive.  The waiver path remains explicitly not
independently reviewed and makes no historical-availability claim.

Rendering either review document is inert.  Only the affirmative payload,
authenticated with the lane's existing production-evidence owner-signature
purpose, can mint a production receipt.  The receipt grants no provider,
outcome, QuantConnect, object-store, deployment, order, or trading access.
"""
from __future__ import annotations

import dataclasses
import os
import threading
import weakref
from typing import Any, Callable

from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes,
    decode_utf8,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2_qc import (
    physical_production_evidence_bridge as _bridge_module,
)
from research.analyst_revisions_v2_qc import (
    physical_production_input_archive as _c2_module,
)
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    OwnerSignatureAuthority,
    OwnerSignatureAuthorityError,
    require_production_evidence_review_owner_signature,
)
from research.analyst_revisions_v2_qc.physical_production_evidence_bridge import (
    PhysicalProductionEvidenceBridge,
)


REVIEW_PIN_SCHEMA = "arv2-physical-production-evidence-review-pin-v1"
SECTION72_REVIEW_PIN_SCHEMA = (
    "arv2-section72-owner-waived-production-evidence-pin-v1"
)
RECEIPT_SCHEMA = "arv2-physical-production-evidence-acquisition-receipt-v1"
MAX_REVIEW_DOCUMENT_BYTES = 1_048_576
NORMAL_REVIEW_MODE = "independently_reviewed"
SECTION72_OWNER_WAIVED_REVIEW_MODE = "section72_owner_waived"
FIXTURE_REVIEW_MODE = "test_fixture"


class PhysicalProductionEvidenceAcquisitionError(ValueError):
    """The physical C2 review decision or retained authority is invalid."""


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class PhysicalProductionEvidenceAcquisitionReceipt:
    schema: str
    receipt_id: str
    receipt_sha256: str
    bridge: PhysicalProductionEvidenceBridge = dataclasses.field(repr=False)
    production_input_archive: object = dataclasses.field(repr=False)
    preopen_acquisition_receipt: object = dataclasses.field(repr=False)
    owner_signature: OwnerSignatureAuthority = dataclasses.field(repr=False)
    review_mode: str
    session_axis: tuple[str, ...]
    bridge_id: str
    bridge_sha256: str
    accepted_risk_archive_id: str
    accepted_risk_archive_sha256: str
    production_input_archive_id: str
    production_input_archive_sha256: str
    evidence_authority_id: str
    evidence_authority_sha256: str
    preopen_acquisition_id: str
    preopen_acquisition_sha256: str
    review_candidate_sha256: str
    review_pin_bytes: bytes = dataclasses.field(repr=False)
    review_pin_id: str
    review_pin_sha256: str
    owner_signature_authority_id: str
    owner_signature_authority_sha256: str
    owner_waived_firm_admission_id: str | None
    owner_waived_firm_admission_sha256: str | None
    firm_owner_decision_id: str | None
    firm_owner_decision_sha256: str | None
    firm_refusal_ledger_id: str | None
    firm_refusal_ledger_sha256: str | None
    owner_waiver_scope: str | None
    source_projection_sha256: str
    row_projection_sha256: str
    composition_terminal_projection_sha256: str
    evidence_row_count: int
    complete_member_census_verified: bool
    source_membership_verified: bool
    same_key_identity_lineage_verified: bool
    independently_reviewed: bool
    owner_signature_verified: bool
    owner_review_waived: bool
    historical_availability_claimed: bool
    post_first_formal_backtest_independent_review_required: bool
    disk_backed_archive: bool
    full_pair_materialized: bool
    full_evidence_materialized: bool
    fixture_only: bool
    filesystem_access_retained: bool
    provider_access: bool
    credential_access: bool
    outcome_access: bool
    quantconnect_access: bool
    object_store_access: bool
    deployment: bool
    orders: bool
    trading: bool

    def to_record(self) -> dict[str, object]:
        return _receipt_record(self)


_RECEIPTS: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalProductionEvidenceAcquisitionReceipt],
        bytes,
        tuple[object, ...],
        int,
        Callable[..., OwnerSignatureAuthority] | None,
    ],
] = {}
_SPENT_REVIEW_PINS: set[str] = set()
_LOCK = threading.RLock()
_MISSING = object()


def _forget(identity: int, reference: object) -> None:
    with _LOCK:
        current = _RECEIPTS.get(identity)
        if current is not None and current[0] is reference:
            _RECEIPTS.pop(identity, None)


_PINNED_DEPENDENCIES = (
    (
        _bridge_module,
        "require_physical_production_evidence_bridge",
        _bridge_module.require_physical_production_evidence_bridge,
    ),
    (
        _bridge_module,
        "render_physical_production_evidence_review_candidate",
        _bridge_module.render_physical_production_evidence_review_candidate,
    ),
    (
        _bridge_module,
        "section72_owner_waived_preopen_session_axis",
        _bridge_module.section72_owner_waived_preopen_session_axis,
    ),
    (
        _c2_module,
        "require_physical_production_input_archive",
        _c2_module.require_physical_production_input_archive,
    ),
    (
        _c2_module,
        "require_reviewable_physical_production_archive",
        _c2_module.require_reviewable_physical_production_archive,
    ),
)
_PINNED_LOCALS = (
    ("canonical_json_bytes", canonical_json_bytes),
    ("decode_utf8", decode_utf8),
    ("require_sha256", require_sha256),
    ("sha256_bytes", sha256_bytes),
    ("strict_json_loads", strict_json_loads),
    (
        "require_production_evidence_review_owner_signature",
        require_production_evidence_review_owner_signature,
    ),
)


def _require_dependencies() -> None:
    if any(
        getattr(module, name, _MISSING) is not expected
        for module, name, expected in _PINNED_DEPENDENCIES
    ) or any(
        globals().get(name, _MISSING) is not expected
        for name, expected in _PINNED_LOCALS
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence acquisition dependency changed"
        )


def _strict_object(payload: bytes, name: str) -> dict[str, Any]:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_REVIEW_DOCUMENT_BYTES:
        raise PhysicalProductionEvidenceAcquisitionError(
            f"{name} is not bounded exact bytes"
        )
    try:
        parsed = strict_json_loads(decode_utf8(payload, name), name)
    except (TypeError, ValueError) as exc:
        raise PhysicalProductionEvidenceAcquisitionError(
            f"{name} is not strict UTF-8 JSON"
        ) from exc
    if type(parsed) is not dict or canonical_json_bytes(parsed) != payload:
        raise PhysicalProductionEvidenceAcquisitionError(
            f"{name} is not canonical JSON"
        )
    return parsed


def _review_seed(bridge: PhysicalProductionEvidenceBridge) -> dict[str, object]:
    bridge = _bridge_module.require_physical_production_evidence_bridge(bridge)
    if getattr(
        bridge,
        "firm_authority_mode",
        _bridge_module.NORMAL_FIRM_AUTHORITY_MODE,
    ) != _bridge_module.NORMAL_FIRM_AUTHORITY_MODE:
        raise PhysicalProductionEvidenceAcquisitionError(
            "independent review pin requires the normal firm authority mode"
        )
    c2 = _c2_module.require_reviewable_physical_production_archive(
        bridge.production_input_archive
    )
    candidate = _bridge_module.render_physical_production_evidence_review_candidate(
        bridge
    )
    if len(candidate) > MAX_REVIEW_DOCUMENT_BYTES:
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence review candidate exceeded capacity"
        )
    return {
        "schema": REVIEW_PIN_SCHEMA,
        "status": "independently_reviewed_private_physical_production_evidence",
        "pin_id": None,
        "pin_sha256": None,
        "review_candidate_sha256": sha256_bytes(candidate),
        "review_candidate_byte_count": len(candidate),
        "bridge_id": bridge.bridge_id,
        "bridge_sha256": bridge.bridge_sha256,
        "accepted_risk_archive_id": bridge.accepted_risk_archive_id,
        "accepted_risk_archive_sha256": bridge.accepted_risk_archive_sha256,
        "production_input_archive_id": c2.archive_id,
        "production_input_archive_sha256": c2.archive_sha256,
        "evidence_authority_id": c2.evidence_authority_id,
        "evidence_authority_sha256": c2.evidence_authority_sha256,
        "preopen_acquisition_id": bridge.preopen_acquisition_id,
        "preopen_acquisition_sha256": bridge.preopen_acquisition_sha256,
        "source_projection_sha256": c2.source_projection_sha256,
        "row_projection_sha256": c2.row_projection_sha256,
        "composition_terminal_projection_sha256": (
            bridge.composition_terminal_projection_sha256
        ),
        "evidence_row_count": c2.evidence_row_count,
        "complete_member_census_verified": True,
        "source_membership_verified": True,
        "same_key_identity_lineage_verified": True,
        "contains_outcome_or_price": False,
        "maximum_receipts_per_process": 1,
    }


def render_physical_production_evidence_owner_review_payload_candidate(
    bridge: PhysicalProductionEvidenceBridge,
) -> bytes:
    """Render exact affirmative bytes; without owner signature they are inert."""

    _require_dependencies()
    raw = _review_seed(bridge)
    digest = sha256_bytes(canonical_json_bytes(raw))
    raw["pin_id"] = f"arv2-physical-production-evidence-review-{digest[:24]}"
    raw["pin_sha256"] = digest
    return canonical_json_bytes(raw)


def _validate_pin(
    bridge: PhysicalProductionEvidenceBridge,
    pin_bytes: bytes,
) -> dict[str, Any]:
    parsed = _strict_object(pin_bytes, "physical production-evidence review pin")
    expected = render_physical_production_evidence_owner_review_payload_candidate(
        bridge
    )
    if pin_bytes != expected:
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence review pin does not bind exact C2"
        )
    semantic = dict(parsed)
    pin_id = semantic["pin_id"]
    pin_sha256 = semantic["pin_sha256"]
    semantic["pin_id"] = None
    semantic["pin_sha256"] = None
    digest = sha256_bytes(canonical_json_bytes(semantic))
    if (
        pin_id != f"arv2-physical-production-evidence-review-{digest[:24]}"
        or pin_sha256 != digest
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence review pin identity changed"
        )
    return parsed


def _section72_review_seed(
    bridge: PhysicalProductionEvidenceBridge,
) -> dict[str, object]:
    bridge = _bridge_module.require_physical_production_evidence_bridge(bridge)
    if (
        bridge.firm_authority_mode
        != _bridge_module.SECTION72_FIRM_AUTHORITY_MODE
        or bridge.historical_availability_claimed is not False
        or bridge.owner_waiver_signature_required is not True
        or bridge.owner_waiver_scope
        != _bridge_module.SECTION72_OWNER_WAIVER_SCOPE
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "section-72 review pin requires exact owner-waived bridge"
        )
    c2 = _c2_module.require_reviewable_physical_production_archive(
        bridge.production_input_archive
    )
    candidate = _bridge_module.render_physical_production_evidence_review_candidate(
        bridge
    )
    if len(candidate) > MAX_REVIEW_DOCUMENT_BYTES:
        raise PhysicalProductionEvidenceAcquisitionError(
            "section-72 production-evidence review candidate exceeded capacity"
        )
    axis = _bridge_module.section72_owner_waived_preopen_session_axis(bridge)
    return {
        "schema": SECTION72_REVIEW_PIN_SCHEMA,
        "status": "owner_waived_section72_physical_production_evidence",
        "pin_id": None,
        "pin_sha256": None,
        "owner_waiver_scope": bridge.owner_waiver_scope,
        "independently_reviewed": False,
        "historical_availability_claimed": False,
        "post_first_formal_backtest_independent_review_required": True,
        "deterministic_clean_firm_defaults_only": True,
        "all_named_firm_refusals_excluded": True,
        "review_candidate_sha256": sha256_bytes(candidate),
        "review_candidate_byte_count": len(candidate),
        "bridge_id": bridge.bridge_id,
        "bridge_sha256": bridge.bridge_sha256,
        "accepted_risk_archive_id": bridge.accepted_risk_archive_id,
        "accepted_risk_archive_sha256": bridge.accepted_risk_archive_sha256,
        "production_input_archive_id": c2.archive_id,
        "production_input_archive_sha256": c2.archive_sha256,
        "evidence_authority_id": c2.evidence_authority_id,
        "evidence_authority_sha256": c2.evidence_authority_sha256,
        "preopen_prereview_archive_id": bridge.preopen_acquisition_id,
        "preopen_prereview_archive_sha256": bridge.preopen_acquisition_sha256,
        "owner_waived_firm_admission_id": bridge.owner_waived_firm_admission_id,
        "owner_waived_firm_admission_sha256": (
            bridge.owner_waived_firm_admission_sha256
        ),
        "firm_owner_decision_id": bridge.firm_owner_decision_id,
        "firm_owner_decision_sha256": bridge.firm_owner_decision_sha256,
        "firm_refusal_ledger_id": bridge.firm_refusal_ledger_id,
        "firm_refusal_ledger_sha256": bridge.firm_refusal_ledger_sha256,
        "session_axis_sha256": sha256_bytes(canonical_json_bytes(list(axis))),
        "session_count": len(axis),
        "source_projection_sha256": c2.source_projection_sha256,
        "row_projection_sha256": c2.row_projection_sha256,
        "composition_terminal_projection_sha256": (
            bridge.composition_terminal_projection_sha256
        ),
        "evidence_row_count": c2.evidence_row_count,
        "complete_member_census_verified": True,
        "source_membership_verified": True,
        "same_key_identity_lineage_verified": True,
        "contains_outcome_or_price": False,
        "maximum_receipts_per_process": 1,
    }


def render_section72_owner_waived_production_evidence_payload_candidate(
    bridge: PhysicalProductionEvidenceBridge,
) -> bytes:
    """Render the exact owner-waiver bytes; rendering grants no authority."""

    _require_dependencies()
    raw = _section72_review_seed(bridge)
    digest = sha256_bytes(canonical_json_bytes(raw))
    raw["pin_id"] = f"arv2-section72-production-evidence-{digest[:24]}"
    raw["pin_sha256"] = digest
    return canonical_json_bytes(raw)


def _validate_section72_pin(
    bridge: PhysicalProductionEvidenceBridge,
    pin_bytes: bytes,
) -> dict[str, Any]:
    parsed = _strict_object(pin_bytes, "section-72 production-evidence pin")
    expected = render_section72_owner_waived_production_evidence_payload_candidate(
        bridge
    )
    if pin_bytes != expected:
        raise PhysicalProductionEvidenceAcquisitionError(
            "section-72 production-evidence pin does not bind exact C2"
        )
    semantic = dict(parsed)
    pin_id = semantic["pin_id"]
    pin_sha256 = semantic["pin_sha256"]
    semantic["pin_id"] = None
    semantic["pin_sha256"] = None
    digest = sha256_bytes(canonical_json_bytes(semantic))
    if (
        pin_id != f"arv2-section72-production-evidence-{digest[:24]}"
        or pin_sha256 != digest
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "section-72 production-evidence pin identity changed"
        )
    return parsed


def _receipt_record(
    value: PhysicalProductionEvidenceAcquisitionReceipt,
) -> dict[str, object]:
    return {
        "schema": value.schema,
        "review_mode": value.review_mode,
        "session_axis": list(value.session_axis),
        "bridge_id": value.bridge_id,
        "bridge_sha256": value.bridge_sha256,
        "accepted_risk_archive_id": value.accepted_risk_archive_id,
        "accepted_risk_archive_sha256": value.accepted_risk_archive_sha256,
        "production_input_archive_id": value.production_input_archive_id,
        "production_input_archive_sha256": value.production_input_archive_sha256,
        "evidence_authority_id": value.evidence_authority_id,
        "evidence_authority_sha256": value.evidence_authority_sha256,
        "preopen_acquisition_id": value.preopen_acquisition_id,
        "preopen_acquisition_sha256": value.preopen_acquisition_sha256,
        "review_candidate_sha256": value.review_candidate_sha256,
        "review_pin_id": value.review_pin_id,
        "review_pin_sha256": value.review_pin_sha256,
        "owner_signature_authority_id": value.owner_signature_authority_id,
        "owner_signature_authority_sha256": value.owner_signature_authority_sha256,
        "owner_waived_firm_admission_id": value.owner_waived_firm_admission_id,
        "owner_waived_firm_admission_sha256": (
            value.owner_waived_firm_admission_sha256
        ),
        "firm_owner_decision_id": value.firm_owner_decision_id,
        "firm_owner_decision_sha256": value.firm_owner_decision_sha256,
        "firm_refusal_ledger_id": value.firm_refusal_ledger_id,
        "firm_refusal_ledger_sha256": value.firm_refusal_ledger_sha256,
        "owner_waiver_scope": value.owner_waiver_scope,
        "source_projection_sha256": value.source_projection_sha256,
        "row_projection_sha256": value.row_projection_sha256,
        "composition_terminal_projection_sha256": (
            value.composition_terminal_projection_sha256
        ),
        "evidence_row_count": value.evidence_row_count,
        "complete_member_census_verified": value.complete_member_census_verified,
        "source_membership_verified": value.source_membership_verified,
        "same_key_identity_lineage_verified": (
            value.same_key_identity_lineage_verified
        ),
        "independently_reviewed": value.independently_reviewed,
        "owner_signature_verified": value.owner_signature_verified,
        "owner_review_waived": value.owner_review_waived,
        "historical_availability_claimed": (
            value.historical_availability_claimed
        ),
        "post_first_formal_backtest_independent_review_required": (
            value.post_first_formal_backtest_independent_review_required
        ),
        "disk_backed_archive": value.disk_backed_archive,
        "full_pair_materialized": value.full_pair_materialized,
        "full_evidence_materialized": value.full_evidence_materialized,
        "fixture_only": value.fixture_only,
        "capabilities": {
            "filesystem_access_retained": value.filesystem_access_retained,
            "provider_access": value.provider_access,
            "credential_access": value.credential_access,
            "outcome_access": value.outcome_access,
            "quantconnect_access": value.quantconnect_access,
            "object_store_access": value.object_store_access,
            "deployment": value.deployment,
            "orders": value.orders,
            "trading": value.trading,
        },
    }


def _receipt_topology(
    value: PhysicalProductionEvidenceAcquisitionReceipt,
) -> tuple[object, ...]:
    return (
        id(value.bridge),
        id(value.production_input_archive),
        id(value.preopen_acquisition_receipt),
        id(value.owner_signature),
        id(value.review_pin_bytes),
        id(value.session_axis),
    )


def _validate_receipt_surface(
    value: PhysicalProductionEvidenceAcquisitionReceipt,
) -> None:
    if type(value.bridge) is not PhysicalProductionEvidenceBridge:
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt bridge type changed"
        )
    if type(value.owner_signature) is not OwnerSignatureAuthority:
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt signature type changed"
        )
    string_fields = (
        "schema",
        "review_mode",
        "receipt_id",
        "receipt_sha256",
        "bridge_id",
        "bridge_sha256",
        "accepted_risk_archive_id",
        "accepted_risk_archive_sha256",
        "production_input_archive_id",
        "production_input_archive_sha256",
        "evidence_authority_id",
        "evidence_authority_sha256",
        "preopen_acquisition_id",
        "preopen_acquisition_sha256",
        "review_candidate_sha256",
        "review_pin_id",
        "review_pin_sha256",
        "owner_signature_authority_id",
        "owner_signature_authority_sha256",
        "source_projection_sha256",
        "row_projection_sha256",
        "composition_terminal_projection_sha256",
    )
    if any(type(getattr(value, name)) is not str for name in string_fields):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt scalar type changed"
        )
    if (
        type(value.session_axis) is not tuple
        or not value.session_axis
        or any(type(item) is not str for item in value.session_axis)
        or value.session_axis != tuple(sorted(set(value.session_axis)))
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt session axis changed"
        )
    optional_string_fields = (
        "owner_waived_firm_admission_id",
        "owner_waived_firm_admission_sha256",
        "firm_owner_decision_id",
        "firm_owner_decision_sha256",
        "firm_refusal_ledger_id",
        "firm_refusal_ledger_sha256",
        "owner_waiver_scope",
    )
    if any(
        getattr(value, name) is not None
        and type(getattr(value, name)) is not str
        for name in optional_string_fields
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt waiver scalar changed type"
        )
    if type(value.review_pin_bytes) is not bytes:
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt pin bytes changed type"
        )
    if type(value.evidence_row_count) is not int or value.evidence_row_count < 0:
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt row count changed type"
        )
    bool_fields = (
        "complete_member_census_verified",
        "source_membership_verified",
        "same_key_identity_lineage_verified",
        "independently_reviewed",
        "owner_signature_verified",
        "owner_review_waived",
        "historical_availability_claimed",
        "post_first_formal_backtest_independent_review_required",
        "disk_backed_archive",
        "full_pair_materialized",
        "full_evidence_materialized",
        "fixture_only",
        "filesystem_access_retained",
        "provider_access",
        "credential_access",
        "outcome_access",
        "quantconnect_access",
        "object_store_access",
        "deployment",
        "orders",
        "trading",
    )
    if any(type(getattr(value, name)) is not bool for name in bool_fields):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt flag type changed"
        )


def _mint_receipt(
    *,
    bridge: PhysicalProductionEvidenceBridge,
    review_pin_bytes: bytes,
    owner_signature: OwnerSignatureAuthority,
    fixture_only: bool,
    review_mode: str,
    signature_requirer: Callable[..., OwnerSignatureAuthority] | None,
) -> PhysicalProductionEvidenceAcquisitionReceipt:
    bridge = _bridge_module.require_physical_production_evidence_bridge(bridge)
    c2 = _c2_module.require_physical_production_input_archive(
        bridge.production_input_archive
    )
    normal = review_mode == NORMAL_REVIEW_MODE
    waived = review_mode == SECTION72_OWNER_WAIVED_REVIEW_MODE
    fixture = review_mode == FIXTURE_REVIEW_MODE
    if (
        sum((normal, waived, fixture)) != 1
        or fixture_only is not fixture
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence review mode changed"
        )
    if fixture:
        pin = _strict_object(
            review_pin_bytes, "physical production-evidence fixture review pin"
        )
        expected_status = (
            "independently_reviewed_private_physical_production_evidence"
        )
        if pin.get("status") != expected_status:
            raise PhysicalProductionEvidenceAcquisitionError(
                "physical production-evidence fixture pin status changed"
            )
    else:
        _c2_module.require_reviewable_physical_production_archive(c2)
        pin = (
            _validate_pin(bridge, review_pin_bytes)
            if normal
            else _validate_section72_pin(bridge, review_pin_bytes)
        )
        if type(owner_signature) is not OwnerSignatureAuthority:
            raise PhysicalProductionEvidenceAcquisitionError(
                "physical production-evidence owner signature changed type"
            )
        if signature_requirer is None:
            raise PhysicalProductionEvidenceAcquisitionError(
                "physical production-evidence signature verifier is unavailable"
            )
        try:
            signature_requirer(owner_signature, authority_payload=review_pin_bytes)
        except (OwnerSignatureAuthorityError, TypeError, ValueError) as exc:
            raise PhysicalProductionEvidenceAcquisitionError(
                "physical production-evidence review lacks owner signature"
            ) from exc
        bridge = _bridge_module.require_physical_production_evidence_bridge(bridge)
        _c2_module.require_reviewable_physical_production_archive(c2)
        if normal:
            _validate_pin(bridge, review_pin_bytes)
        else:
            _validate_section72_pin(bridge, review_pin_bytes)
        with _LOCK:
            pin_sha256 = pin["pin_sha256"]
            if pin_sha256 in _SPENT_REVIEW_PINS:
                raise PhysicalProductionEvidenceAcquisitionError(
                    "physical production-evidence review pin was already spent"
                )

    value = object.__new__(PhysicalProductionEvidenceAcquisitionReceipt)
    mechanically_verified = not fixture
    try:
        session_axis = (
            _bridge_module.section72_owner_waived_preopen_session_axis(bridge)
            if waived
            else tuple(
                item.decision_session
                for item in bridge.preopen_acquisition_receipt.control_sessions
            )
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence session axis is unavailable"
        ) from exc
    if (
        not session_axis
        or session_axis != tuple(sorted(set(session_axis)))
        or any(type(item) is not str for item in session_axis)
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence session axis changed"
        )
    signature_id = (
        "fixture-owner-signature"
        if fixture
        else owner_signature.authority_id
    )
    signature_sha = "0" * 64 if fixture else owner_signature.authority_sha256
    fields: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": "",
        "receipt_sha256": "",
        "bridge": bridge,
        "production_input_archive": c2,
        "preopen_acquisition_receipt": bridge.preopen_acquisition_receipt,
        "owner_signature": owner_signature,
        "review_mode": review_mode,
        "session_axis": session_axis,
        "bridge_id": bridge.bridge_id,
        "bridge_sha256": bridge.bridge_sha256,
        "accepted_risk_archive_id": bridge.accepted_risk_archive_id,
        "accepted_risk_archive_sha256": bridge.accepted_risk_archive_sha256,
        "production_input_archive_id": c2.archive_id,
        "production_input_archive_sha256": c2.archive_sha256,
        "evidence_authority_id": c2.evidence_authority_id,
        "evidence_authority_sha256": c2.evidence_authority_sha256,
        "preopen_acquisition_id": bridge.preopen_acquisition_id,
        "preopen_acquisition_sha256": bridge.preopen_acquisition_sha256,
        "review_candidate_sha256": pin["review_candidate_sha256"],
        "review_pin_bytes": review_pin_bytes,
        "review_pin_id": pin["pin_id"],
        "review_pin_sha256": pin["pin_sha256"],
        "owner_signature_authority_id": signature_id,
        "owner_signature_authority_sha256": signature_sha,
        "owner_waived_firm_admission_id": (
            bridge.owner_waived_firm_admission_id if waived else None
        ),
        "owner_waived_firm_admission_sha256": (
            bridge.owner_waived_firm_admission_sha256 if waived else None
        ),
        "firm_owner_decision_id": (
            bridge.firm_owner_decision_id if waived else None
        ),
        "firm_owner_decision_sha256": (
            bridge.firm_owner_decision_sha256 if waived else None
        ),
        "firm_refusal_ledger_id": (
            bridge.firm_refusal_ledger_id if waived else None
        ),
        "firm_refusal_ledger_sha256": (
            bridge.firm_refusal_ledger_sha256 if waived else None
        ),
        "owner_waiver_scope": bridge.owner_waiver_scope if waived else None,
        "source_projection_sha256": c2.source_projection_sha256,
        "row_projection_sha256": c2.row_projection_sha256,
        "composition_terminal_projection_sha256": (
            bridge.composition_terminal_projection_sha256
        ),
        "evidence_row_count": c2.evidence_row_count,
        "complete_member_census_verified": mechanically_verified,
        "source_membership_verified": mechanically_verified,
        "same_key_identity_lineage_verified": mechanically_verified,
        "independently_reviewed": normal,
        "owner_signature_verified": mechanically_verified,
        "owner_review_waived": waived,
        "historical_availability_claimed": not waived,
        "post_first_formal_backtest_independent_review_required": waived,
        "disk_backed_archive": True,
        "full_pair_materialized": False,
        "full_evidence_materialized": False,
        "fixture_only": fixture_only,
        "filesystem_access_retained": False,
        "provider_access": False,
        "credential_access": False,
        "outcome_access": False,
        "quantconnect_access": False,
        "object_store_access": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    if set(fields) != {item.name for item in dataclasses.fields(value)}:
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt field inventory changed"
        )
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    digest = sha256_bytes(canonical_json_bytes(_receipt_record(value)))
    object.__setattr__(value, "receipt_sha256", digest)
    object.__setattr__(
        value, "receipt_id", f"arv2-physical-production-evidence-{digest[:24]}"
    )
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget(key, ref))
    with _LOCK:
        if not fixture and pin["pin_sha256"] in _SPENT_REVIEW_PINS:
            raise PhysicalProductionEvidenceAcquisitionError(
                "physical production-evidence review pin was already spent"
            )
        _RECEIPTS[identity] = (
            reference,
            canonical_json_bytes(_receipt_record(value)),
            _receipt_topology(value),
            os.getpid(),
            signature_requirer,
        )
        if not fixture:
            _SPENT_REVIEW_PINS.add(pin["pin_sha256"])
    try:
        return require_physical_production_evidence_receipt(value)
    except BaseException:
        with _LOCK:
            current = _RECEIPTS.get(identity)
            if current is not None and current[0] is reference:
                _RECEIPTS.pop(identity, None)
                if not fixture:
                    _SPENT_REVIEW_PINS.discard(pin["pin_sha256"])
        raise


def load_physically_reviewed_production_evidence_receipt(
    *,
    bridge: PhysicalProductionEvidenceBridge,
    review_pin_bytes: bytes,
    owner_signature: OwnerSignatureAuthority,
) -> PhysicalProductionEvidenceAcquisitionReceipt:
    """Authenticate one externally reviewed and owner-signed physical C2 pin."""

    _require_dependencies()
    return _mint_receipt(
        bridge=bridge,
        review_pin_bytes=review_pin_bytes,
        owner_signature=owner_signature,
        fixture_only=False,
        review_mode=NORMAL_REVIEW_MODE,
        signature_requirer=require_production_evidence_review_owner_signature,
    )


def _load_test_fixture_physical_production_evidence_receipt(
    *,
    bridge: PhysicalProductionEvidenceBridge,
    review_pin_bytes: bytes,
    owner_signature: OwnerSignatureAuthority,
) -> PhysicalProductionEvidenceAcquisitionReceipt:
    """Test oracle only; reviewed consumers reject the returned receipt."""

    return _mint_receipt(
        bridge=bridge,
        review_pin_bytes=review_pin_bytes,
        owner_signature=owner_signature,
        fixture_only=True,
        review_mode=FIXTURE_REVIEW_MODE,
        signature_requirer=None,
    )


def load_section72_owner_waived_production_evidence_receipt(
    *,
    bridge: PhysicalProductionEvidenceBridge,
    review_pin_bytes: bytes,
    owner_signature: OwnerSignatureAuthority,
) -> PhysicalProductionEvidenceAcquisitionReceipt:
    """Authenticate the exact section-72 owner waiver, never independent review."""

    _require_dependencies()
    return _mint_receipt(
        bridge=bridge,
        review_pin_bytes=review_pin_bytes,
        owner_signature=owner_signature,
        fixture_only=False,
        review_mode=SECTION72_OWNER_WAIVED_REVIEW_MODE,
        signature_requirer=require_production_evidence_review_owner_signature,
    )


def require_physical_production_evidence_receipt(
    value: PhysicalProductionEvidenceAcquisitionReceipt,
) -> PhysicalProductionEvidenceAcquisitionReceipt:
    _require_dependencies()
    if type(value) is not PhysicalProductionEvidenceAcquisitionReceipt:
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt changed type"
        )
    _validate_receipt_surface(value)
    with _LOCK:
        registered = _RECEIPTS.get(id(value))
    if (
        registered is None
        or registered[0]() is not value
        or registered[1] != canonical_json_bytes(_receipt_record(value))
        or registered[2] != _receipt_topology(value)
        or registered[3] != os.getpid()
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt lost builder authority"
        )
    try:
        bridge = _bridge_module.require_physical_production_evidence_bridge(
            value.bridge
        )
        c2 = _c2_module.require_physical_production_input_archive(
            value.production_input_archive
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt parent changed"
        ) from exc
    if value.review_mode == FIXTURE_REVIEW_MODE:
        if value.fixture_only is not True:
            raise PhysicalProductionEvidenceAcquisitionError(
                "physical production-evidence fixture review mode changed"
            )
        pin = _strict_object(
            value.review_pin_bytes,
            "physical production-evidence fixture review pin",
        )
    elif value.review_mode in {
        NORMAL_REVIEW_MODE, SECTION72_OWNER_WAIVED_REVIEW_MODE
    }:
        if value.fixture_only is not False:
            raise PhysicalProductionEvidenceAcquisitionError(
                "physical production-evidence production review mode changed"
            )
        _require_dependencies()
        _c2_module.require_reviewable_physical_production_archive(c2)
        pin = (
            _validate_pin(bridge, value.review_pin_bytes)
            if value.review_mode == NORMAL_REVIEW_MODE
            else _validate_section72_pin(bridge, value.review_pin_bytes)
        )
        verifier = registered[4]
        if verifier is not require_production_evidence_review_owner_signature:
            raise PhysicalProductionEvidenceAcquisitionError(
                "physical production-evidence signature verifier changed"
            )
        try:
            verifier(value.owner_signature, authority_payload=value.review_pin_bytes)
        except (OwnerSignatureAuthorityError, TypeError, ValueError) as exc:
            raise PhysicalProductionEvidenceAcquisitionError(
                "physical production-evidence owner signature no longer authenticates"
            ) from exc
    else:
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence review mode changed"
        )

    false_flags = (
        value.full_pair_materialized,
        value.full_evidence_materialized,
        value.filesystem_access_retained,
        value.provider_access,
        value.credential_access,
        value.outcome_access,
        value.quantconnect_access,
        value.object_store_access,
        value.deployment,
        value.orders,
        value.trading,
    )
    fixture = value.review_mode == FIXTURE_REVIEW_MODE
    normal = value.review_mode == NORMAL_REVIEW_MODE
    waived = value.review_mode == SECTION72_OWNER_WAIVED_REVIEW_MODE
    verified = not fixture
    expected_axis = (
        _bridge_module.section72_owner_waived_preopen_session_axis(bridge)
        if waived
        else tuple(
            item.decision_session
            for item in bridge.preopen_acquisition_receipt.control_sessions
        )
    )
    waiver_fields_are_exact = (
        value.owner_waived_firm_admission_id
        == (bridge.owner_waived_firm_admission_id if waived else None)
        and value.owner_waived_firm_admission_sha256
        == (bridge.owner_waived_firm_admission_sha256 if waived else None)
        and value.firm_owner_decision_id
        == (bridge.firm_owner_decision_id if waived else None)
        and value.firm_owner_decision_sha256
        == (bridge.firm_owner_decision_sha256 if waived else None)
        and value.firm_refusal_ledger_id
        == (bridge.firm_refusal_ledger_id if waived else None)
        and value.firm_refusal_ledger_sha256
        == (bridge.firm_refusal_ledger_sha256 if waived else None)
        and value.owner_waiver_scope
        == (bridge.owner_waiver_scope if waived else None)
    )
    digest = sha256_bytes(canonical_json_bytes(_receipt_record(value)))
    if (
        any(type(item) is not bool or item for item in false_flags)
        or type(value.fixture_only) is not bool
        or type(value.disk_backed_archive) is not bool
        or value.disk_backed_archive is not True
        or not waiver_fields_are_exact
        or value.session_axis != expected_axis
        or value.complete_member_census_verified is not verified
        or value.source_membership_verified is not verified
        or value.same_key_identity_lineage_verified is not verified
        or value.independently_reviewed is not normal
        or value.owner_signature_verified is not verified
        or value.owner_review_waived is not waived
        or value.historical_availability_claimed is not (not waived)
        or value.post_first_formal_backtest_independent_review_required
        is not waived
        or value.schema != RECEIPT_SCHEMA
        or value.bridge is not bridge
        or value.production_input_archive is not c2
        or value.preopen_acquisition_receipt is not bridge.preopen_acquisition_receipt
        or value.bridge_id != bridge.bridge_id
        or value.bridge_sha256 != bridge.bridge_sha256
        or value.accepted_risk_archive_id != bridge.accepted_risk_archive_id
        or value.accepted_risk_archive_sha256
        != bridge.accepted_risk_archive_sha256
        or value.production_input_archive_id != c2.archive_id
        or value.production_input_archive_sha256 != c2.archive_sha256
        or value.evidence_authority_id != c2.evidence_authority_id
        or value.evidence_authority_sha256 != c2.evidence_authority_sha256
        or value.preopen_acquisition_id != bridge.preopen_acquisition_id
        or value.preopen_acquisition_sha256 != bridge.preopen_acquisition_sha256
        or value.review_candidate_sha256 != pin["review_candidate_sha256"]
        or value.review_pin_id != pin["pin_id"]
        or value.review_pin_sha256 != pin["pin_sha256"]
        or value.source_projection_sha256 != c2.source_projection_sha256
        or value.row_projection_sha256 != c2.row_projection_sha256
        or value.composition_terminal_projection_sha256
        != bridge.composition_terminal_projection_sha256
        or type(value.evidence_row_count) is not int
        or value.evidence_row_count != c2.evidence_row_count
        or value.receipt_sha256 != digest
        or value.receipt_id
        != f"arv2-physical-production-evidence-{digest[:24]}"
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt semantic binding changed"
        )
    if not value.fixture_only and (
        value.owner_signature_authority_id != value.owner_signature.authority_id
        or value.owner_signature_authority_sha256
        != value.owner_signature.authority_sha256
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence owner signature binding changed"
        )
    return value


def require_reviewed_physical_production_evidence_receipt(
    value: PhysicalProductionEvidenceAcquisitionReceipt,
) -> PhysicalProductionEvidenceAcquisitionReceipt:
    receipt = require_physical_production_evidence_receipt(value)
    if (
        receipt.fixture_only
        or receipt.review_mode != NORMAL_REVIEW_MODE
        or not receipt.independently_reviewed
        or not receipt.owner_signature_verified
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt is not independently owner reviewed"
        )
    return receipt


def require_section72_owner_waived_production_evidence_receipt(
    value: PhysicalProductionEvidenceAcquisitionReceipt,
) -> PhysicalProductionEvidenceAcquisitionReceipt:
    receipt = require_physical_production_evidence_receipt(value)
    if (
        receipt.fixture_only
        or receipt.review_mode != SECTION72_OWNER_WAIVED_REVIEW_MODE
        or receipt.independently_reviewed is not False
        or receipt.owner_signature_verified is not True
        or receipt.owner_review_waived is not True
        or receipt.historical_availability_claimed is not False
        or receipt.post_first_formal_backtest_independent_review_required
        is not True
    ):
        raise PhysicalProductionEvidenceAcquisitionError(
            "physical production-evidence receipt is not exact section-72 waiver"
        )
    return receipt


__all__ = (
    "FIXTURE_REVIEW_MODE",
    "MAX_REVIEW_DOCUMENT_BYTES",
    "NORMAL_REVIEW_MODE",
    "RECEIPT_SCHEMA",
    "REVIEW_PIN_SCHEMA",
    "SECTION72_OWNER_WAIVED_REVIEW_MODE",
    "SECTION72_REVIEW_PIN_SCHEMA",
    "PhysicalProductionEvidenceAcquisitionError",
    "PhysicalProductionEvidenceAcquisitionReceipt",
    "load_physically_reviewed_production_evidence_receipt",
    "load_section72_owner_waived_production_evidence_receipt",
    "render_physical_production_evidence_owner_review_payload_candidate",
    "render_section72_owner_waived_production_evidence_payload_candidate",
    "require_physical_production_evidence_receipt",
    "require_reviewed_physical_production_evidence_receipt",
    "require_section72_owner_waived_production_evidence_receipt",
)
