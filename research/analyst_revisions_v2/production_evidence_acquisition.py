"""Physical authority for the production-shaped ARV2 C2 evidence package.

``production_input_pipeline`` intentionally accepts caller-shaped records so
that their semantics can be tested without I/O.  Those objects are not allowed
to become scoring authority merely because they are internally consistent.
This module closes that gap: a separately reviewed, owner-signed private
package is parsed back to exact typed members, cross-bound to the reviewed
pre-open acquisition, and retained in a process-local authenticated receipt.

The filesystem read is isolated in
``research.analyst_revisions_v2_qc.production_evidence_acquisition_io``.  This
module is pure and retains only immutable bytes and typed parents.
"""
from __future__ import annotations

import dataclasses
import os
import sys
import threading
import weakref
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from .accepted_risk_input_pair import (
    AcceptedRiskInputPair,
    CaptureRowLocator,
    MassiveSourceRole,
    require_accepted_risk_input_pair,
)
from .canonical import (
    canonical_json_bytes,
    require_exact_bool,
    require_int,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)
from .preopen_control_acquisition import (
    PreopenControlAcquisitionReceipt,
    require_reviewed_preopen_control_acquisition_receipt,
)
from .production_input_pipeline import (
    CommonEventIdentityEvidence,
    DataQualityEvidence,
    EvidenceSourceBinding,
    EvidenceSourceKind,
    FirmOntologyEvidence,
    PreopenControlEvidence,
    ProductionEvidenceAuthority,
    ProductionInputError,
    ProductionRowEvidence,
    SecurityIdentityEvidence,
    SectorClassificationEvidence,
    build_production_evidence_authority,
    require_production_evidence_authority,
)


class ProductionEvidenceAcquisitionError(ValueError):
    """The physical production-evidence package or review pin is invalid."""


PACKAGE_SCHEMA = "arv2-production-evidence-package-v1"
SOURCE_PROJECTION_SCHEMA = "arv2-production-evidence-source-projection-v1"
ROW_PROJECTION_SCHEMA = "arv2-production-evidence-row-projection-v1"
PIN_SCHEMA = "arv2-production-evidence-external-review-pin-v1"
RECEIPT_SCHEMA = "arv2-production-evidence-acquisition-receipt-v1"
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_REVIEW_PIN_BYTES = 256 * 1024

_SOURCE_ORDER = tuple(EvidenceSourceKind)
_ROW_FIELDS = frozenset(
    {"locator", "security", "firm", "common_event", "sector", "control", "q_data"}
)
_LOCATOR_FIELDS = frozenset(
    {
        "capture_id",
        "source_role",
        "page_number",
        "provider_rows_sha256",
        "row_offset",
        "raw_row_sha256",
    }
)
_COMPONENT_TYPES: tuple[tuple[str, type[object]], ...] = (
    ("security", SecurityIdentityEvidence),
    ("firm", FirmOntologyEvidence),
    ("common_event", CommonEventIdentityEvidence),
    ("sector", SectorClassificationEvidence),
    ("control", PreopenControlEvidence),
    ("q_data", DataQualityEvidence),
)


def _exact_object(value: object, fields: frozenset[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise ProductionEvidenceAcquisitionError(f"{name} fields changed")
    return value


def _canonical_object(payload: bytes, name: str) -> dict[str, Any]:
    if type(payload) is not bytes or not payload:
        raise ProductionEvidenceAcquisitionError(f"{name} must be nonempty exact bytes")
    try:
        value = strict_json_loads(payload.decode("utf-8"), name)
    except (UnicodeError, ValueError) as exc:
        raise ProductionEvidenceAcquisitionError(f"{name} is not strict UTF-8 JSON") from exc
    if type(value) is not dict or canonical_json_bytes(value) != payload:
        raise ProductionEvidenceAcquisitionError(f"{name} is not canonical JSON")
    return value


def _source_projection(sources: tuple[EvidenceSourceBinding, ...]) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": SOURCE_PROJECTION_SCHEMA,
                "sources": [item.to_record() for item in sources],
            }
        )
    )


def _row_projection(rows: tuple[ProductionRowEvidence, ...]) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": ROW_PROJECTION_SCHEMA,
                "rows": [item.to_record() for item in rows],
            }
        )
    )


def production_evidence_package_record(
    authority: ProductionEvidenceAuthority,
) -> dict[str, Any]:
    require_production_evidence_authority(authority)
    counts = [
        {
            "kind": "security",
            "present_count": sum(
                item.security is not None for item in authority.row_evidence
            ),
        },
        {
            "kind": "firm",
            "present_count": sum(item.firm is not None for item in authority.row_evidence),
        },
        {
            "kind": "common_event",
            "present_count": sum(
                item.common_event is not None for item in authority.row_evidence
            ),
        },
        {
            "kind": "sector",
            "present_count": sum(
                item.sector is not None for item in authority.row_evidence
            ),
        },
        {
            "kind": "control",
            "present_count": sum(
                item.control is not None for item in authority.row_evidence
            ),
        },
        {
            "kind": "q_data",
            "present_count": sum(
                item.q_data is not None for item in authority.row_evidence
            ),
        },
    ]
    return {
        "schema": PACKAGE_SCHEMA,
        "pair_id": authority.pair_id,
        "pair_sha256": authority.pair_sha256,
        "source_bindings": [item.to_record() for item in authority.source_bindings],
        "row_evidence": [item.to_record() for item in authority.row_evidence],
        "source_count": len(authority.source_bindings),
        "row_count": len(authority.row_evidence),
        "component_present_counts": counts,
        "source_projection_sha256": _source_projection(authority.source_bindings),
        "row_projection_sha256": _row_projection(authority.row_evidence),
    }


def render_production_evidence_package_bytes(
    authority: ProductionEvidenceAuthority,
) -> bytes:
    """Render the exact package an independent reviewer must approve."""

    return canonical_json_bytes(production_evidence_package_record(authority))


def _decode_fraction(value: object, name: str) -> Fraction:
    if (
        type(value) is not list
        or len(value) != 2
        or type(value[0]) is not int
        or type(value[1]) is not int
        or value[1] == 0
    ):
        raise ProductionEvidenceAcquisitionError(f"{name} is not an exact fraction")
    return Fraction(value[0], value[1])


def _decode_locator(value: object) -> CaptureRowLocator:
    raw = _exact_object(value, _LOCATOR_FIELDS, "row locator")
    try:
        role = MassiveSourceRole(raw["source_role"])
        return CaptureRowLocator(
            capture_id=raw["capture_id"],
            source_role=role,
            page_number=raw["page_number"],
            provider_rows_sha256=raw["provider_rows_sha256"],
            row_offset=raw["row_offset"],
            raw_row_sha256=raw["raw_row_sha256"],
        )
    except (TypeError, ValueError) as exc:
        raise ProductionEvidenceAcquisitionError("row locator is invalid") from exc


def _decode_component(name: str, value: object) -> object | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise ProductionEvidenceAcquisitionError(f"{name} member is not an object or null")
    raw = dict(value)
    try:
        if name == "security":
            result = SecurityIdentityEvidence(**raw)
        elif name == "firm":
            raw["current_score"] = _decode_fraction(raw.get("current_score"), "current_score")
            raw["previous_score"] = _decode_fraction(
                raw.get("previous_score"), "previous_score"
            )
            result = FirmOntologyEvidence(**raw)
        elif name == "common_event":
            result = CommonEventIdentityEvidence(**raw)
        elif name == "sector":
            result = SectorClassificationEvidence(**raw)
        elif name == "control":
            result = PreopenControlEvidence(**raw)
        elif name == "q_data":
            encoded = raw.get("q_data")
            if type(encoded) is not str:
                raise ProductionEvidenceAcquisitionError("q_data is not canonical decimal text")
            try:
                raw["q_data"] = Decimal(encoded)
            except InvalidOperation as exc:
                raise ProductionEvidenceAcquisitionError(
                    "q_data is not canonical decimal text"
                ) from exc
            result = DataQualityEvidence(**raw)
        else:  # pragma: no cover - closed internal inventory
            raise ProductionEvidenceAcquisitionError("unknown evidence member")
    except ProductionEvidenceAcquisitionError:
        raise
    except (ProductionInputError, TypeError, ValueError) as exc:
        raise ProductionEvidenceAcquisitionError(f"{name} member is invalid") from exc
    return result


def _decode_package(
    pair: AcceptedRiskInputPair,
    payload: bytes,
) -> tuple[ProductionEvidenceAuthority, dict[str, Any]]:
    require_accepted_risk_input_pair(pair)
    raw = _exact_object(
        _canonical_object(payload, "production evidence package"),
        frozenset(
            {
                "schema",
                "pair_id",
                "pair_sha256",
                "source_bindings",
                "row_evidence",
                "source_count",
                "row_count",
                "component_present_counts",
                "source_projection_sha256",
                "row_projection_sha256",
            }
        ),
        "production evidence package",
    )
    if (
        raw["schema"] != PACKAGE_SCHEMA
        or raw["pair_id"] != pair.pair_id
        or raw["pair_sha256"] != pair.pair_sha256
    ):
        raise ProductionEvidenceAcquisitionError("production evidence pair binding changed")
    try:
        require_int(raw["source_count"], "source_count", minimum=0)
        require_int(raw["row_count"], "row_count", minimum=0)
    except ValueError as exc:
        raise ProductionEvidenceAcquisitionError(
            "production evidence package counts have wrong types"
        ) from exc
    source_rows = raw["source_bindings"]
    if type(source_rows) is not list or len(source_rows) != len(_SOURCE_ORDER):
        raise ProductionEvidenceAcquisitionError("production evidence source census changed")
    sources = []
    for expected_kind, item in zip(_SOURCE_ORDER, source_rows, strict=True):
        parsed = _exact_object(
            item,
            frozenset({"kind", "artifact_id", "artifact_sha256", "reviewed", "point_in_time"}),
            "production evidence source binding",
        )
        if parsed["kind"] != expected_kind.value:
            raise ProductionEvidenceAcquisitionError("production evidence sources reordered")
        try:
            sources.append(
                EvidenceSourceBinding(
                    kind=expected_kind,
                    artifact_id=parsed["artifact_id"],
                    artifact_sha256=parsed["artifact_sha256"],
                    reviewed=parsed["reviewed"],
                    point_in_time=parsed["point_in_time"],
                )
            )
        except (ProductionInputError, TypeError, ValueError) as exc:
            raise ProductionEvidenceAcquisitionError(
                "production evidence source binding is invalid"
            ) from exc
    rows_raw = raw["row_evidence"]
    if type(rows_raw) is not list:
        raise ProductionEvidenceAcquisitionError("production evidence row census changed")
    rows = []
    for item in rows_raw:
        parsed = _exact_object(item, _ROW_FIELDS, "production row evidence")
        rows.append(
            ProductionRowEvidence(
                locator=_decode_locator(parsed["locator"]),
                security=_decode_component("security", parsed["security"]),
                firm=_decode_component("firm", parsed["firm"]),
                common_event=_decode_component("common_event", parsed["common_event"]),
                sector=_decode_component("sector", parsed["sector"]),
                control=_decode_component("control", parsed["control"]),
                q_data=_decode_component("q_data", parsed["q_data"]),
            )
        )
    source_tuple = tuple(sources)
    row_tuple = tuple(rows)
    component_counts = raw["component_present_counts"]
    if type(component_counts) is not list or len(component_counts) != len(
        _COMPONENT_TYPES
    ):
        raise ProductionEvidenceAcquisitionError(
            "production evidence component census changed"
        )
    for (expected_kind, _), item in zip(
        _COMPONENT_TYPES, component_counts, strict=True
    ):
        parsed_count = _exact_object(
            item,
            frozenset({"kind", "present_count"}),
            "production evidence component count",
        )
        try:
            require_int(parsed_count["present_count"], "present_count", minimum=0)
        except ValueError as exc:
            raise ProductionEvidenceAcquisitionError(
                "production evidence component count has wrong type"
            ) from exc
        if parsed_count["kind"] != expected_kind:
            raise ProductionEvidenceAcquisitionError(
                "production evidence component counts reordered"
            )
    try:
        authority = build_production_evidence_authority(
            pair,
            source_bindings=source_tuple,
            row_evidence=row_tuple,
        )
    except ProductionInputError as exc:
        raise ProductionEvidenceAcquisitionError(
            "production evidence members do not form an admissible authority"
        ) from exc
    expected = production_evidence_package_record(authority)
    if raw != expected:
        raise ProductionEvidenceAcquisitionError(
            "production evidence counts, order, hashes, or members changed"
        )
    return authority, raw


def _truth_source_records(
    acquisition: PreopenControlAcquisitionReceipt,
) -> list[dict[str, str]]:
    return [
        {"kind": kind, "artifact_id": artifact_id, "artifact_sha256": artifact_sha256}
        for kind, artifact_id, artifact_sha256 in acquisition.truth_source_bindings
    ]


def _quality_projection(acquisition: PreopenControlAcquisitionReceipt) -> str:
    value = acquisition.q_data_measurement_projection_sha256
    if type(value) is not str:
        raise ProductionEvidenceAcquisitionError(
            "pre-open acquisition lacks physical q_data measurement authority"
        )
    require_sha256(value, "q_data_measurement_projection_sha256")
    return value


def _pin_binding(
    *,
    authority: ProductionEvidenceAuthority,
    acquisition: PreopenControlAcquisitionReceipt,
    package_bytes: bytes,
) -> dict[str, Any]:
    package_sha = sha256_bytes(package_bytes)
    package = _canonical_object(package_bytes, "production evidence package")
    return {
        "schema": PIN_SCHEMA,
        "package_sha256": package_sha,
        "package_byte_count": len(package_bytes),
        "package_row_count": package["row_count"],
        "source_projection_sha256": package["source_projection_sha256"],
        "row_projection_sha256": package["row_projection_sha256"],
        "pair_id": authority.pair_id,
        "pair_sha256": authority.pair_sha256,
        "c2_authority_id": authority.authority_id,
        "c2_authority_sha256": authority.authority_sha256,
        "preopen_acquisition_id": acquisition.artifact_id,
        "preopen_acquisition_sha256": acquisition.artifact_sha256,
        "input_source_inventory_sha256": acquisition.input_source_inventory_sha256,
        "truth_source_bindings": _truth_source_records(acquisition),
        "qc_sid_mapping_artifact_id": acquisition.qc_sid_mapping_artifact_id,
        "qc_sid_mapping_artifact_sha256": acquisition.qc_sid_mapping_artifact_sha256,
        "q_data_measurement_projection_sha256": _quality_projection(acquisition),
    }


def render_production_evidence_external_review_pin_candidate(
    *,
    authority: ProductionEvidenceAuthority,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    package_bytes: bytes,
) -> bytes:
    """Render a non-authorizing candidate for independent private review."""

    require_production_evidence_authority(authority)
    require_reviewed_preopen_control_acquisition_receipt(preopen_acquisition_receipt)
    decoded, _ = _decode_package(authority.pair, package_bytes)
    if decoded.authority_sha256 != authority.authority_sha256:
        raise ProductionEvidenceAcquisitionError(
            "reviewed package does not reconstruct the requested C2 authority"
        )
    return canonical_json_bytes(
        {
            **_pin_binding(
                authority=authority,
                acquisition=preopen_acquisition_receipt,
                package_bytes=package_bytes,
            ),
            "status": "review_required_not_authorized",
            "pin_id": None,
            "pin_sha256": None,
            "complete_member_census_verified": False,
            "source_membership_verified": False,
            "same_key_identity_lineage_verified": False,
            "contains_outcome_or_price": False,
        }
    )


def render_production_evidence_owner_review_payload_candidate(
    *,
    authority: ProductionEvidenceAuthority,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    package_bytes: bytes,
) -> bytes:
    """Render exact affirmative review bytes; unsigned bytes grant no authority."""

    require_production_evidence_authority(authority)
    require_reviewed_preopen_control_acquisition_receipt(
        preopen_acquisition_receipt
    )
    decoded, _ = _decode_package(authority.pair, package_bytes)
    if decoded.authority_sha256 != authority.authority_sha256:
        raise ProductionEvidenceAcquisitionError(
            "reviewed package does not reconstruct the requested C2 authority"
        )
    raw = {
        **_pin_binding(
            authority=authority,
            acquisition=preopen_acquisition_receipt,
            package_bytes=package_bytes,
        ),
        "status": "independently_reviewed_private_production_evidence",
        "pin_id": None,
        "pin_sha256": None,
        "complete_member_census_verified": True,
        "source_membership_verified": True,
        "same_key_identity_lineage_verified": True,
        "contains_outcome_or_price": False,
    }
    digest = sha256_bytes(canonical_json_bytes(raw))
    raw["pin_id"] = f"arv2-production-evidence-review-{digest[:24]}"
    raw["pin_sha256"] = digest
    return canonical_json_bytes(raw)


def _validate_pin(
    *,
    authority: ProductionEvidenceAuthority,
    acquisition: PreopenControlAcquisitionReceipt,
    package_bytes: bytes,
    pin_bytes: bytes,
) -> dict[str, Any]:
    raw = _canonical_object(pin_bytes, "production evidence external review pin")
    binding = _pin_binding(
        authority=authority,
        acquisition=acquisition,
        package_bytes=package_bytes,
    )
    expected_fields = frozenset(
        {
            *binding,
            "status",
            "pin_id",
            "pin_sha256",
            "complete_member_census_verified",
            "source_membership_verified",
            "same_key_identity_lineage_verified",
            "contains_outcome_or_price",
        }
    )
    _exact_object(raw, expected_fields, "production evidence external review pin")
    try:
        require_int(raw["package_byte_count"], "package_byte_count", minimum=1)
        require_int(raw["package_row_count"], "package_row_count", minimum=0)
    except ValueError as exc:
        raise ProductionEvidenceAcquisitionError(
            "production evidence review pin counts have wrong types"
        ) from exc
    semantic = dict(raw)
    pin_id = semantic["pin_id"]
    pin_sha = semantic["pin_sha256"]
    semantic["pin_id"] = None
    semantic["pin_sha256"] = None
    digest = sha256_bytes(canonical_json_bytes(semantic))
    if pin_id != f"arv2-production-evidence-review-{digest[:24]}" or pin_sha != digest:
        raise ProductionEvidenceAcquisitionError("production evidence review pin hash changed")
    if any(raw[name] != value for name, value in binding.items()):
        raise ProductionEvidenceAcquisitionError(
            "production evidence review pin does not bind exact physical inputs"
        )
    if raw["status"] != "independently_reviewed_private_production_evidence":
        raise ProductionEvidenceAcquisitionError(
            "production evidence package requires independent private review"
        )
    for name in (
        "complete_member_census_verified",
        "source_membership_verified",
        "same_key_identity_lineage_verified",
    ):
        try:
            require_exact_bool(raw[name], name)
        except ValueError as exc:
            raise ProductionEvidenceAcquisitionError(
                f"{name} has wrong type"
            ) from exc
        if raw[name] is not True:
            raise ProductionEvidenceAcquisitionError(f"{name} is not independently verified")
    try:
        require_exact_bool(raw["contains_outcome_or_price"], "contains_outcome_or_price")
    except ValueError as exc:
        raise ProductionEvidenceAcquisitionError(
            "contains_outcome_or_price has wrong type"
        ) from exc
    if raw["contains_outcome_or_price"] is not False:
        raise ProductionEvidenceAcquisitionError("production evidence package contains outcomes")
    return raw


@dataclasses.dataclass(frozen=True, init=False)
class ProductionEvidenceAcquisitionReceipt:
    schema: str
    receipt_id: str
    receipt_sha256: str
    authority: ProductionEvidenceAuthority
    authority_id: str
    authority_sha256: str
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt
    preopen_acquisition_id: str
    preopen_acquisition_sha256: str
    package_bytes: bytes
    package_sha256: str
    package_byte_count: int
    package_row_count: int
    source_projection_sha256: str
    row_projection_sha256: str
    review_pin_bytes: bytes
    review_pin_id: str
    review_pin_sha256: str
    q_data_measurement_projection_sha256: str
    complete_member_census_verified: bool
    source_membership_verified: bool
    same_key_identity_lineage_verified: bool
    filesystem_access: bool
    provider_access: bool
    outcome_access: bool
    quantconnect_access: bool
    object_store_access: bool
    deployment: bool
    orders: bool
    trading: bool


def _receipt_record(value: ProductionEvidenceAcquisitionReceipt) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "authority_id": value.authority_id,
        "authority_sha256": value.authority_sha256,
        "preopen_acquisition_id": value.preopen_acquisition_id,
        "preopen_acquisition_sha256": value.preopen_acquisition_sha256,
        "package_sha256": value.package_sha256,
        "package_byte_count": value.package_byte_count,
        "package_row_count": value.package_row_count,
        "source_projection_sha256": value.source_projection_sha256,
        "row_projection_sha256": value.row_projection_sha256,
        "review_pin_id": value.review_pin_id,
        "review_pin_sha256": value.review_pin_sha256,
        "q_data_measurement_projection_sha256": value.q_data_measurement_projection_sha256,
        "complete_member_census_verified": value.complete_member_census_verified,
        "source_membership_verified": value.source_membership_verified,
        "same_key_identity_lineage_verified": value.same_key_identity_lineage_verified,
        "capabilities": {
            "filesystem_access": False,
            "provider_access": False,
            "outcome_access": False,
            "quantconnect_access": False,
            "object_store_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


def _receipt_fingerprint(
    value: ProductionEvidenceAcquisitionReceipt,
) -> tuple[object, ...]:
    semantic = _receipt_record(value)
    digest = sha256_bytes(canonical_json_bytes(semantic))
    return (
        id(value.authority),
        id(value.preopen_acquisition_receipt),
        id(value.package_bytes),
        id(value.review_pin_bytes),
        canonical_json_bytes(semantic),
        digest,
    )


def _build_physically_reviewed_production_evidence_receipt_implementation(
    *,
    authority: ProductionEvidenceAuthority,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    package_bytes: bytes,
    review_pin_bytes: bytes,
) -> ProductionEvidenceAcquisitionReceipt:
    """Mint after the I/O boundary has performed private regular-file reads."""

    require_production_evidence_authority(authority)
    require_reviewed_preopen_control_acquisition_receipt(preopen_acquisition_receipt)
    decoded, package = _decode_package(authority.pair, package_bytes)
    if decoded.authority_sha256 != authority.authority_sha256:
        raise ProductionEvidenceAcquisitionError(
            "physical package reconstructed a different C2 authority"
        )
    acquired = {
        kind: (artifact_id, artifact_sha256)
        for kind, artifact_id, artifact_sha256
        in preopen_acquisition_receipt.truth_source_bindings
    }
    for source in authority.source_bindings:
        if acquired.get(source.kind.value) != (source.artifact_id, source.artifact_sha256):
            raise ProductionEvidenceAcquisitionError(
                f"{source.kind.value} package source is not the reviewed pre-open source"
            )
    pin = _validate_pin(
        authority=authority,
        acquisition=preopen_acquisition_receipt,
        package_bytes=package_bytes,
        pin_bytes=review_pin_bytes,
    )
    value = object.__new__(ProductionEvidenceAcquisitionReceipt)
    values: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "authority": authority,
        "authority_id": authority.authority_id,
        "authority_sha256": authority.authority_sha256,
        "preopen_acquisition_receipt": preopen_acquisition_receipt,
        "preopen_acquisition_id": preopen_acquisition_receipt.artifact_id,
        "preopen_acquisition_sha256": preopen_acquisition_receipt.artifact_sha256,
        "package_bytes": package_bytes,
        "package_sha256": sha256_bytes(package_bytes),
        "package_byte_count": len(package_bytes),
        "package_row_count": package["row_count"],
        "source_projection_sha256": package["source_projection_sha256"],
        "row_projection_sha256": package["row_projection_sha256"],
        "review_pin_bytes": review_pin_bytes,
        "review_pin_id": pin["pin_id"],
        "review_pin_sha256": pin["pin_sha256"],
        "q_data_measurement_projection_sha256": pin[
            "q_data_measurement_projection_sha256"
        ],
        "complete_member_census_verified": True,
        "source_membership_verified": True,
        "same_key_identity_lineage_verified": True,
        "filesystem_access": False,
        "provider_access": False,
        "outcome_access": False,
        "quantconnect_access": False,
        "object_store_access": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    for name, item in values.items():
        object.__setattr__(value, name, item)
    semantic = _receipt_record(value)
    digest = sha256_bytes(canonical_json_bytes(semantic))
    object.__setattr__(value, "receipt_id", f"arv2-production-evidence-{digest[:24]}")
    object.__setattr__(value, "receipt_sha256", digest)
    return value


def _require_production_evidence_acquisition_receipt_implementation(
    value: ProductionEvidenceAcquisitionReceipt,
    registered,
) -> ProductionEvidenceAcquisitionReceipt:
    if type(value) is not ProductionEvidenceAcquisitionReceipt:
        raise ProductionEvidenceAcquisitionError(
            "production evidence receipt requires exact built type"
        )
    if registered is None or registered[0]() is not value:
        raise ProductionEvidenceAcquisitionError(
            "production evidence receipt is not builder-authenticated"
        )
    require_production_evidence_authority(value.authority)
    require_reviewed_preopen_control_acquisition_receipt(
        value.preopen_acquisition_receipt
    )
    if type(value.package_bytes) is not bytes or type(value.review_pin_bytes) is not bytes:
        raise ProductionEvidenceAcquisitionError("production evidence retained bytes changed")
    decoded, package = _decode_package(value.authority.pair, value.package_bytes)
    if decoded.authority_sha256 != value.authority.authority_sha256:
        raise ProductionEvidenceAcquisitionError("production evidence package changed")
    pin = _validate_pin(
        authority=value.authority,
        acquisition=value.preopen_acquisition_receipt,
        package_bytes=value.package_bytes,
        pin_bytes=value.review_pin_bytes,
    )
    false_flags = (
        value.filesystem_access,
        value.provider_access,
        value.outcome_access,
        value.quantconnect_access,
        value.object_store_access,
        value.deployment,
        value.orders,
        value.trading,
    )
    if any(type(item) is not bool or item for item in false_flags):
        raise ProductionEvidenceAcquisitionError(
            "production evidence receipt acquired a forbidden capability"
        )
    if (
        value.schema != RECEIPT_SCHEMA
        or value.authority_id != value.authority.authority_id
        or value.authority_sha256 != value.authority.authority_sha256
        or value.preopen_acquisition_id != value.preopen_acquisition_receipt.artifact_id
        or value.preopen_acquisition_sha256
        != value.preopen_acquisition_receipt.artifact_sha256
        or value.package_sha256 != sha256_bytes(value.package_bytes)
        or value.package_byte_count != len(value.package_bytes)
        or value.package_row_count != package["row_count"]
        or value.source_projection_sha256 != package["source_projection_sha256"]
        or value.row_projection_sha256 != package["row_projection_sha256"]
        or value.review_pin_id != pin["pin_id"]
        or value.review_pin_sha256 != pin["pin_sha256"]
        or value.q_data_measurement_projection_sha256
        != _quality_projection(value.preopen_acquisition_receipt)
        or value.complete_member_census_verified is not True
        or value.source_membership_verified is not True
        or value.same_key_identity_lineage_verified is not True
    ):
        raise ProductionEvidenceAcquisitionError(
            "production evidence receipt semantic binding changed"
        )
    semantic = _receipt_record(value)
    digest = sha256_bytes(canonical_json_bytes(semantic))
    if (
        value.receipt_id != f"arv2-production-evidence-{digest[:24]}"
        or value.receipt_sha256 != digest
        or registered[1]
        != (
            id(value.authority),
            id(value.preopen_acquisition_receipt),
            id(value.package_bytes),
            id(value.review_pin_bytes),
            canonical_json_bytes(semantic),
            digest,
        )
    ):
        raise ProductionEvidenceAcquisitionError(
            "production evidence receipt changed after authentication"
        )
    return value


def _make_production_evidence_receipt_authority(
    mint_implementation,
    require_implementation,
):
    """Seal receipt registration and issue one minter to the exact I/O module."""

    records: tuple[
        tuple[
            int,
            weakref.ReferenceType[ProductionEvidenceAcquisitionReceipt],
            tuple[object, ...],
        ],
        ...,
    ] = ()
    rlock_factory = threading.RLock
    getpid = os.getpid
    realpath = os.path.realpath
    exact_type = type
    exact_tuple = tuple
    any_true = any
    identity = id
    read_vars = vars
    zip_strict = zip
    system_module = sys
    module_registry = system_module.modules
    weak_reference = weakref.ref
    lock = rlock_factory()
    authority_pid = getpid()
    minter_claimed = False
    fingerprint = _receipt_fingerprint
    receipt_type = ProductionEvidenceAcquisitionReceipt
    error_type = ProductionEvidenceAcquisitionError
    expected_module_name = (
        "research.analyst_revisions_v2_qc.production_evidence_acquisition_io"
    )
    expected_module_path = realpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "analyst_revisions_v2_qc",
            "production_evidence_acquisition_io.py",
        )
    )
    expected_loader_name = (
        "load_physically_reviewed_production_evidence_receipt"
    )
    function_type = exact_type(lambda: None)

    def current(value: ProductionEvidenceAcquisitionReceipt):
        if getpid() != authority_pid:
            return None
        with lock:
            value_identity = identity(value)
            for key, reference, registered_fingerprint in records:
                if key == value_identity:
                    return reference, registered_fingerprint
            return None

    def require_production_evidence_acquisition_receipt(
        value: ProductionEvidenceAcquisitionReceipt,
    ) -> ProductionEvidenceAcquisitionReceipt:
        return require_implementation(value, current(value))

    def forget(identity: int, reference: object) -> None:
        nonlocal records
        with lock:
            records = exact_tuple(
                item
                for item in records
                if not (item[0] == identity and item[1] is reference)
            )

    def claim_production_evidence_receipt_minter(loader_function):
        nonlocal minter_claimed
        try:
            import inspect

            caller = inspect.currentframe().f_back
            currentframe = inspect.currentframe
            caller_globals = caller.f_globals
            caller_name = caller_globals.get("__name__")
            caller_path = realpath(caller.f_code.co_filename)
            caller_code_name = caller.f_code.co_name
            registered = module_registry.get(expected_module_name)
            loader_code = loader_function.__code__
            loader_globals = loader_function.__globals__
            loader_module = loader_function.__module__
            loader_path = realpath(loader_code.co_filename)
            loader_name = loader_code.co_name
        except (AttributeError, OSError, TypeError):
            caller = None
            caller_globals = None
            caller_name = None
            caller_path = ""
            caller_code_name = ""
            registered = None
            loader_code = None
            loader_globals = None
            loader_module = None
            loader_path = ""
            loader_name = ""
        if (
            getpid() != authority_pid
            or caller_name != expected_module_name
            or registered is None
            or read_vars(registered) is not caller_globals
            or caller_path != expected_module_path
            or caller_code_name != "<module>"
            or exact_type(loader_function) is not function_type
            or loader_globals is not caller_globals
            or loader_module != expected_module_name
            or loader_path != expected_module_path
            or loader_name != expected_loader_name
        ):
            raise error_type(
                "production evidence receipt minter claim is loader-private"
            )
        with lock:
            if minter_claimed:
                raise error_type(
                    "production evidence receipt minter is already claimed"
                )
            minter_claimed = True
        minter_pid = getpid()
        expected_loader_globals = loader_globals
        expected_loader_freevars = exact_tuple(loader_code.co_freevars)
        expected_loader_bindings = exact_tuple(
            (name, cell.cell_contents)
            for name, cell in zip_strict(
                expected_loader_freevars,
                loader_function.__closure__ or (),
                strict=True,
            )
            if name not in ("loader_guard", "receipt_minter")
        )

        def mint(**kwargs) -> ProductionEvidenceAcquisitionReceipt:
            nonlocal records
            try:
                mint_caller = currentframe().f_back
                mint_caller_globals = mint_caller.f_globals
                mint_caller_code = mint_caller.f_code
                mint_caller_path = realpath(mint_caller_code.co_filename)
                mint_caller_locals = mint_caller.f_locals
            except (AttributeError, OSError, TypeError):
                mint_caller = None
                mint_caller_globals = None
                mint_caller_code = None
                mint_caller_path = ""
                mint_caller_locals = {}
            if (
                getpid() != minter_pid
                or mint_caller_code is not loader_code
                or mint_caller_globals is not expected_loader_globals
                or mint_caller_path != expected_module_path
                or system_module.modules is not module_registry
                or module_registry.get(expected_module_name) is not registered
                or read_vars(registered) is not mint_caller_globals
                or mint_caller_globals.get(expected_loader_name)
                is not loader_function
                or exact_tuple(mint_caller_code.co_freevars)
                != expected_loader_freevars
                or any_true(
                    mint_caller_locals.get(name) is not expected
                    for name, expected in expected_loader_bindings
                )
                or mint_caller_locals.get("receipt_minter") is not mint
            ):
                raise error_type(
                    "production evidence mint is loader-private"
                )
            del mint_caller
            value = mint_implementation(**kwargs)
            if exact_type(value) is not receipt_type:
                raise error_type("production evidence minter type changed")
            value_identity = identity(value)
            reference = weak_reference(
                value,
                lambda ref, key=value_identity: forget(key, ref),
            )
            with lock:
                if any_true(item[0] == value_identity for item in records):
                    raise error_type(
                        "production evidence identity is already registered"
                    )
                records = (
                    *records,
                    (value_identity, reference, fingerprint(value)),
                )
            return require_production_evidence_acquisition_receipt(value)

        globals().pop("_claim_production_evidence_receipt_minter", None)
        if caller_globals is not None:
            caller_globals.pop("_claim_production_evidence_receipt_minter", None)
        del caller
        return mint

    def reset_after_fork() -> None:
        nonlocal records, lock
        records = ()
        lock = rlock_factory()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)
    return (
        claim_production_evidence_receipt_minter,
        require_production_evidence_acquisition_receipt,
    )


(
    _claim_production_evidence_receipt_minter,
    require_production_evidence_acquisition_receipt,
) = _make_production_evidence_receipt_authority(
    _build_physically_reviewed_production_evidence_receipt_implementation,
    _require_production_evidence_acquisition_receipt_implementation,
)
del _make_production_evidence_receipt_authority
del _build_physically_reviewed_production_evidence_receipt_implementation
del _require_production_evidence_acquisition_receipt_implementation


__all__ = [
    "MAX_PACKAGE_BYTES",
    "MAX_REVIEW_PIN_BYTES",
    "PACKAGE_SCHEMA",
    "PIN_SCHEMA",
    "ProductionEvidenceAcquisitionError",
    "ProductionEvidenceAcquisitionReceipt",
    "production_evidence_package_record",
    "render_production_evidence_external_review_pin_candidate",
    "render_production_evidence_owner_review_payload_candidate",
    "render_production_evidence_package_bytes",
    "require_production_evidence_acquisition_receipt",
]
