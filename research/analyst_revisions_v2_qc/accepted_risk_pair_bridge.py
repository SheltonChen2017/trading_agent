"""Authenticate the physical accepted-risk pair for the formal QC protocol.

This host-only bridge closes the gap between the physical Massive capture
adapter and :class:`formal_run_protocol.AcceptedRiskPairBinding`.  It accepts
no caller-authored counts or safety flags.  Every value is re-derived from the
builder-authenticated Massive bridge and the two builder-authenticated C2
production-input batches that share its exact pair.

The canonical artifact is the C1 pair's exact semantic document.  Its content
hash therefore reproduces ``AcceptedRiskInputPair.pair_sha256``; a separate
domain-separated hash gives that serialization its formal artifact identity.
This module renders but does not persist it, and performs no filesystem,
provider, credential, QuantConnect, outcome, deployment, order, or trading
action.
"""
from __future__ import annotations

import hashlib

from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskInputError,
    AcceptedRiskInputPair,
    MassiveSourceRole,
)
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    sha256_bytes,
)
from research.analyst_revisions_v2.production_input_pipeline import (
    ProductionInputBatch,
    ProductionInputError,
    SignalArm,
    require_production_input_batch,
)
from scripts.build_arv2_massive_input_pair import (
    MassiveAcceptedRiskBridge,
    MassiveInputPairBridgeError,
    require_massive_accepted_risk_bridge,
)

from .formal_run_protocol import (
    AcceptedRiskPairBinding,
    ArtifactBinding,
    FormalRunProtocolError,
    require_accepted_risk_pair_binding,
)


PAIR_ARTIFACT_DOMAIN = b"arv2-formal-accepted-risk-pair-artifact-v1\0"


class AcceptedRiskPairBridgeError(ValueError):
    """The physical pair cannot be bound to the formal-run protocol."""


def _pair_semantic_record(pair: AcceptedRiskInputPair) -> dict[str, object]:
    """Reproduce the complete C1 semantic document from authenticated state."""

    return {
        "schema": pair.schema,
        "contract_id": pair.contract_id,
        "contract_sha256": pair.contract_sha256,
        "capture_id": pair.capture.capture_id,
        "capture_sha256": pair.capture.capture_sha256,
        "rows": [row.to_record() for row in pair.rows],
        "report": pair.report.to_record(),
        "current_view_label": pair.current_view_label,
        "censored_view_label": pair.censored_view_label,
        "pristine_point_in_time": pair.pristine_point_in_time,
        "earlier_version_imputation_performed": (
            pair.earlier_version_imputation_performed
        ),
        "views_share_one_capture": pair.views_share_one_capture,
        "guidance_clock_authenticated": pair.guidance_clock_authenticated,
        "identity_mapping_authenticated": pair.identity_mapping_authenticated,
        "rating_mapping_authenticated": pair.rating_mapping_authenticated,
        "signal_rows_constructed": pair.signal_rows_constructed,
        "production_input_authority": pair.production_input_authority,
        "outcome_gate_open": pair.outcome_gate_open,
        "provider_binding": pair.provider_binding,
        "security_master_binding": pair.security_master_binding,
        "outcome_binding": pair.outcome_binding,
        "provider_io_performed": pair.provider_io_performed,
        "credential_access_performed": pair.credential_access_performed,
        "filesystem_io_performed": pair.filesystem_io_performed,
        "quantconnect_io_performed": pair.quantconnect_io_performed,
        "object_store_io_performed": pair.object_store_io_performed,
        "market_data_access_performed": pair.market_data_access_performed,
        "outcome_access_performed": pair.outcome_access_performed,
        "deployment_performed": pair.deployment_performed,
        "order_access_performed": pair.order_access_performed,
        "trading_performed": pair.trading_performed,
    }


_PINNED_REQUIRE_MASSIVE_BRIDGE = require_massive_accepted_risk_bridge
_PINNED_REQUIRE_BATCH = require_production_input_batch
_PINNED_CANONICAL_JSON_BYTES = canonical_json_bytes
_PINNED_SHA256_BYTES = sha256_bytes
_PINNED_PAIR_SEMANTIC_RECORD = _pair_semantic_record
_PINNED_ACCEPTED_BINDING_TYPE = AcceptedRiskPairBinding
_PINNED_ARTIFACT_BINDING_TYPE = ArtifactBinding
_PINNED_REQUIRE_ACCEPTED_BINDING = require_accepted_risk_pair_binding
_PINNED_HASHLIB_SHA256 = hashlib.sha256


def _authenticated_pair(
    bridge: MassiveAcceptedRiskBridge,
) -> AcceptedRiskInputPair:
    try:
        authenticated_bridge = _PINNED_REQUIRE_MASSIVE_BRIDGE(bridge)
    except (
        AcceptedRiskInputError,
        CanonicalEvidenceError,
        MassiveInputPairBridgeError,
        AttributeError,
        TypeError,
        ValueError,
    ) as exc:
        raise AcceptedRiskPairBridgeError(
            "Massive accepted-risk bridge did not authenticate"
        ) from exc
    # The bridge authenticator itself reauthenticates this pair.  Retain that
    # exact object rather than doing a second full-history derivation pass.
    return authenticated_bridge.pair


def _render_authenticated_pair(pair: AcceptedRiskInputPair) -> bytes:
    """Render a pair already authenticated by its physical bridge."""

    try:
        payload = _PINNED_CANONICAL_JSON_BYTES(
            _PINNED_PAIR_SEMANTIC_RECORD(pair)
        )
    except (CanonicalEvidenceError, AttributeError, TypeError, ValueError) as exc:
        raise AcceptedRiskPairBridgeError(
            "accepted-risk pair artifact could not be rendered"
        ) from exc
    if _PINNED_SHA256_BYTES(payload) != pair.pair_sha256:
        raise AcceptedRiskPairBridgeError(
            "accepted-risk pair artifact does not reproduce its content hash"
        )
    return payload


def render_formal_accepted_risk_pair_artifact_bytes(
    bridge: MassiveAcceptedRiskBridge,
) -> bytes:
    """Render the exact canonical C1 semantic document after reauthentication."""

    pair = _authenticated_pair(bridge)
    return _render_authenticated_pair(pair)


def _artifact_binding(pair: AcceptedRiskInputPair) -> ArtifactBinding:
    payload = _render_authenticated_pair(pair)
    try:
        artifact_hasher = _PINNED_HASHLIB_SHA256()
        artifact_hasher.update(PAIR_ARTIFACT_DOMAIN)
        artifact_hasher.update(payload)
        return _PINNED_ARTIFACT_BINDING_TYPE(
            artifact_id=pair.pair_id,
            content_sha256=pair.pair_sha256,
            artifact_sha256=artifact_hasher.hexdigest(),
            byte_count=len(payload),
        )
    except (FormalRunProtocolError, AttributeError, TypeError, ValueError) as exc:
        raise AcceptedRiskPairBridgeError(
            "accepted-risk pair artifact binding could not be built"
        ) from exc


def _authenticated_source_views(
    *,
    pair: AcceptedRiskInputPair,
    current_batch: ProductionInputBatch,
    censored_batch: ProductionInputBatch,
) -> tuple[ProductionInputBatch, ProductionInputBatch]:
    try:
        current = _PINNED_REQUIRE_BATCH(current_batch)
        censored = _PINNED_REQUIRE_BATCH(censored_batch)
    except (
        AcceptedRiskInputError,
        CanonicalEvidenceError,
        ProductionInputError,
        AttributeError,
        TypeError,
        ValueError,
    ) as exc:
        raise AcceptedRiskPairBridgeError(
            "accepted-risk production batches did not authenticate"
        ) from exc
    if (
        current.signal_arm is not SignalArm.CURRENT_VINTAGE
        or censored.signal_arm is not SignalArm.CONSERVATIVE_CENSORED
        or current.evidence_authority is not censored.evidence_authority
        or current.evidence_authority.pair is not pair
        or censored.evidence_authority.pair is not pair
        or current.pair_id != pair.pair_id
        or censored.pair_id != pair.pair_id
        or current.pair_sha256 != pair.pair_sha256
        or censored.pair_sha256 != pair.pair_sha256
        or current.total_source_row_count != len(pair.rows)
        or censored.total_source_row_count != len(pair.rows)
        or current.source_view_included_count
        != pair.report.current_included_count
        or censored.source_view_included_count
        != pair.report.censored_included_count
    ):
        raise AcceptedRiskPairBridgeError(
            "current and censored batches do not share the exact Massive pair"
        )
    return current, censored


def build_formal_accepted_risk_pair_binding(
    *,
    bridge: MassiveAcceptedRiskBridge,
    current_batch: ProductionInputBatch,
    censored_batch: ProductionInputBatch,
) -> AcceptedRiskPairBinding:
    """Derive the formal binding without accepting caller-authored assertions."""

    pair = _authenticated_pair(bridge)
    current, censored = _authenticated_source_views(
        pair=pair,
        current_batch=current_batch,
        censored_batch=censored_batch,
    )
    guidance_admitted_count = 0
    pre_2013_admitted_count = 0
    # Do not construct a third full-history tuple merely to count two refusal
    # classes.  Production batches can be large, and both source tuples are
    # already authenticated above.
    for rows in (current.normalized_rows, censored.normalized_rows):
        for row in rows:
            guidance_admitted_count += (
                row.source_role is MassiveSourceRole.CORPORATE_GUIDANCE
            )
            pre_2013_admitted_count += int(row.event_date[:4]) < 2013
    pair_artifact = _artifact_binding(pair)
    try:
        binding = _PINNED_ACCEPTED_BINDING_TYPE(
            pair=pair_artifact,
            capture_id=pair.capture.capture_id,
            capture_sha256=pair.capture.capture_sha256,
            current_source_included_count=current.source_view_included_count,
            censored_source_included_count=censored.source_view_included_count,
            current_admitted_decision_count=current.normalized_row_count,
            current_named_preoutcome_refusal_count=(
                current.source_view_included_count - current.normalized_row_count
            ),
            censored_admitted_decision_count=censored.normalized_row_count,
            censored_named_preoutcome_refusal_count=(
                censored.source_view_included_count - censored.normalized_row_count
            ),
            guidance_admitted_count=guidance_admitted_count,
            pre_2013_admitted_count=pre_2013_admitted_count,
            pristine_point_in_time=pair.pristine_point_in_time,
            views_share_one_capture=pair.views_share_one_capture,
        )
        return _PINNED_REQUIRE_ACCEPTED_BINDING(binding)
    except (
        FormalRunProtocolError,
        AttributeError,
        TypeError,
        ValueError,
    ) as exc:
        raise AcceptedRiskPairBridgeError(
            "formal accepted-risk pair binding refused derived state"
        ) from exc


__all__ = [
    "PAIR_ARTIFACT_DOMAIN",
    "AcceptedRiskPairBridgeError",
    "build_formal_accepted_risk_pair_binding",
    "render_formal_accepted_risk_pair_artifact_bytes",
]
