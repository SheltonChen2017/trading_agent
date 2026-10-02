"""Disk-bounded physical composer for ARV2 production evidence.

This host-only boundary joins exact accepted-risk rating rows to the reviewed
historical QC/Sharadar identity sidecar and to physically authenticated
pre-open terminals.  The result is the existing C2 evidence-package bytes and
an external-review pin *candidate*.  It never turns those bytes into a reviewed
receipt and grants no provider, QuantConnect, outcome, result, or trading
capability.

Firm-scale availability is deliberately a separate reviewed artifact.  An
ontology's review timestamp or validity interval is never treated as proof
that its source evidence was historically available.
"""
from __future__ import annotations

import dataclasses
import os
import re
import sqlite3
import stat
import tempfile
import threading
import weakref
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterator, Mapping

from research.analyst_revisions_v2 import firm_ontology as firm_module
from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskInputPair,
    AcceptedRiskSourceRow,
    MassiveSourceRole,
    require_accepted_risk_input_pair,
)
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    parse_date,
    parse_utc_timestamp,
    require_exact_bool,
    require_identifier,
    require_int,
    require_sha256,
    require_text,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2.firm_ontology import (
    FirmRatingMapEntry,
    ReviewedFirmRatingOntology,
)
from research.analyst_revisions_v2.preopen_control_acquisition import (
    PreopenControlAcquisitionReceipt,
    acquisition_truth_source_binding_records,
    require_reviewed_preopen_control_acquisition_receipt,
)
from research.analyst_revisions_v2.production_evidence_acquisition import (
    MAX_PACKAGE_BYTES,
    render_production_evidence_external_review_pin_candidate,
    render_production_evidence_package_bytes,
)
from research.analyst_revisions_v2.production_input_pipeline import (
    CommonEventIdentityEvidence,
    DataQualityEvidence,
    EvidenceSourceBinding,
    EvidenceSourceKind,
    FirmOntologyEvidence,
    SECTION72_OWNER_WAIVED_FIRM_ADMISSION_MODE,
    SECTION72_OWNER_WAIVER_SCOPE as C2_SECTION72_OWNER_WAIVER_SCOPE,
    Section72OwnerWaivedFirmOntologyEvidence,
    PreopenControlEvidence,
    ProductionEvidenceAuthority,
    ProductionRowEvidence,
    SectorClassificationEvidence,
    SecurityIdentityEvidence,
    build_production_evidence_authority,
    require_production_evidence_authority,
)
from research.analyst_revisions_v2.production_truth_gate import QUALITY_METHOD_ID
from scripts import build_arv2_historical_preopen_bridge as historical_module

from . import firm_ontology_owner_decision as _firm_decision
from .firm_ontology_owner_decision import FirmOntologyOwnerDecisionArtifact
from . import physical_firm_ontology_review_packet as _firm_packet
from .physical_firm_ontology_review_packet import PhysicalFirmOntologyReviewPacket

from .formal_streaming_input import (
    PhysicalPreopenTerminalArchive,
    PhysicalProductionEvidenceTerminalArchive,
    PhysicalTerminalSessionBlock,
    iter_physical_preopen_terminal_sessions,
    require_physical_preopen_terminal_archive,
    require_physical_production_evidence_terminal_archive,
)


FIRM_AVAILABILITY_SCHEMA = "arv2-firm-ontology-historical-availability-v1"
FIRM_AVAILABILITY_REVIEW_SCHEMA = (
    "arv2-firm-ontology-historical-availability-review-v1"
)
FIRM_AVAILABILITY_REVIEW_STATUS = (
    "independently_reviewed_historical_firm_ontology_availability_affirmative"
)
COMPOSER_SCHEMA = "arv2-physical-production-evidence-composer-candidate-v1"
COMPOSITION_TERMINAL_SCHEMA = "arv2-production-evidence-composition-terminal-v1"
SECTION72_FIRM_ADMISSION_SCHEMA = (
    "arv2-section72-owner-waived-firm-admission-v1"
)
SECTION72_OWNER_WAIVER_SCOPE = C2_SECTION72_OWNER_WAIVER_SCOPE

MAX_FIRM_AVAILABILITY_BYTES = 64 * 1024 * 1024
MAX_FIRM_AVAILABILITY_REVIEW_BYTES = 1024 * 1024
MAX_COMPOSER_RATING_ROW_COUNT = 2_000_000
MAX_COMPOSER_SIDECAR_ROW_COUNT = 4_000_000
MAX_COMPOSER_SPOOL_BYTES = 2 * 1024 * 1024 * 1024
MAX_COMPOSER_ROW_BYTES = 8 * 1024 * 1024

_AVAILABILITY_FIELDS = frozenset(
    {"schema", "ontology_id", "ontology_sha256", "entries"}
)
_AVAILABILITY_ENTRY_FIELDS = frozenset(
    {
        "ontology_entry_sha256",
        "source_evidence_id",
        "source_evidence_sha256",
        "available_at",
        "valid_to_available_at",
    }
)
_REVIEW_FIELDS = frozenset(
    {
        "schema",
        "availability_sha256",
        "availability_byte_count",
        "ontology_id",
        "ontology_sha256",
        "entry_count",
        "entry_projection_sha256",
        "status",
        "receipt_id",
        "receipt_sha256",
        "complete_ontology_entry_census_verified",
        "historical_availability_verified_from_external_source_evidence",
        "no_review_time_or_valid_from_imputation_verified",
        "contains_outcome_or_price",
    }
)
_SIDECAR_FIELDS = frozenset(
    {
        "schema",
        "locator_sha256",
        "raw_row_sha256",
        "provider_event_id",
        "common_event_id",
        "source_role",
        "current_view_disposition",
        "censored_view_disposition",
        "preopen_composition_disposition",
        "preopen_composition_reason",
        "physical_security_id",
        "decision_session",
        "decision_session_ordinal",
        "available_at",
        "rating_admitted",
        "rating_seed_row_sha256",
        "binding_disposition",
        "binding_reason",
        "qc_security_id",
        "cusip",
        "issuer_id",
        "share_class_id",
        "listing_id",
        "historical_ticker",
        "mapping_first_session",
        "mapping_last_session",
        "mapping_available_at",
        "mapping_closure_available_at",
        "mapping_row_sha256",
        "q_data",
        "q_data_evidence_sha256",
        "binding_sha256",
    }
)
_HEX = re.compile(r"[0-9a-f]{64}\Z")


class ProductionEvidenceComposerError(ValueError):
    """A physical parent or deterministic composition invariant failed."""


class ProductionEvidenceComposerCapacityRefusal(ProductionEvidenceComposerError):
    """A fixed host capacity ceiling was exceeded without truncation."""


@dataclasses.dataclass(frozen=True, slots=True)
class OwnerWaivedFirmMapping:
    """One exact proposal mapping admitted under the bounded owner waiver."""

    provider_firm_id: str
    firm_name: str
    raw_label: str
    ordered_rank: int
    scale_size: int
    scope: str
    valid_from: str
    valid_to: str | None
    mapping_role: str
    source_evidence_id: str
    source_evidence_sha256: str
    proxy_kind: str
    proxy_open_at: str
    mapping_sha256: str

    @property
    def normalized_score(self) -> Fraction:
        return Fraction(
            2 * (self.ordered_rank - 1) - (self.scale_size - 1),
            self.scale_size - 1,
        )

    def semantic_record(self) -> dict[str, object]:
        return {
            "provider_firm_id": self.provider_firm_id,
            "firm_name": self.firm_name,
            "raw_label": self.raw_label,
            "ordered_rank": self.ordered_rank,
            "scale_size": self.scale_size,
            "scope": self.scope,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "mapping_role": self.mapping_role,
            "source_evidence_id": self.source_evidence_id,
            "source_evidence_sha256": self.source_evidence_sha256,
            "proxy_kind": self.proxy_kind,
            "proxy_open_at": self.proxy_open_at,
        }

    def to_record(self) -> dict[str, object]:
        return {**self.semantic_record(), "mapping_sha256": self.mapping_sha256}


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class OwnerWaivedAcceptedRiskFirmAdmission:
    """Non-registry admission candidate for the exact section-72 waiver.

    This object deliberately does not assert independent review or true
    historical availability.  A later owner-signed physical acquisition
    receipt must bind it before a formal session index can be admitted.
    """

    schema: str
    admission_id: str
    admission_sha256: str
    owner_decision: FirmOntologyOwnerDecisionArtifact = dataclasses.field(
        repr=False
    )
    review_packet: PhysicalFirmOntologyReviewPacket = dataclasses.field(repr=False)
    review_packet_id: str
    review_packet_sha256: str
    owner_decision_id: str
    owner_decision_sha256: str
    owner_decision_payload_sha256: str
    refusal_ledger_id: str
    refusal_ledger_sha256: str
    refusal_ledger_payload_sha256: str
    mappings: tuple[OwnerWaivedFirmMapping, ...]
    refused_provider_firm_ids: tuple[str, ...]
    mapping_projection_sha256: str
    refusal_projection_sha256: str
    accepted_firm_count: int
    refused_firm_count: int
    mapping_count: int
    owner_waiver_scope: str
    deterministic_defaults_only: bool
    named_refusals_excluded: bool
    conservative_availability_proxy_only: bool
    owner_signature_required_downstream: bool
    independently_reviewed: bool
    historical_availability_claimed: bool
    normal_registry_populated: bool
    production_authority: bool

    def to_record(self) -> dict[str, object]:
        return _owner_waived_admission_record(self)


_OWNER_WAIVED_FIRM_ADMISSIONS: dict[
    int,
    tuple[
        weakref.ReferenceType[OwnerWaivedAcceptedRiskFirmAdmission],
        bytes,
        tuple[object, ...],
        weakref.ReferenceType[FirmOntologyOwnerDecisionArtifact],
        int,
    ],
] = {}
_OWNER_WAIVED_FIRM_LOCK = threading.RLock()


def _forget_owner_waived_firm_admission(identity: int, reference: object) -> None:
    with _OWNER_WAIVED_FIRM_LOCK:
        current = _OWNER_WAIVED_FIRM_ADMISSIONS.get(identity)
        if current is not None and current[0] is reference:
            _OWNER_WAIVED_FIRM_ADMISSIONS.pop(identity, None)


def _owner_waived_mapping(
    *,
    decision_row: Mapping[str, object],
    proposal_mapping: Mapping[str, object],
    proxy: Mapping[str, object],
    mapping_role: str,
) -> OwnerWaivedFirmMapping:
    defaults = decision_row.get("accepted_proposal_defaults")
    if type(defaults) is not dict:
        raise ProductionEvidenceComposerError(
            "owner-waived accepted firm lost authenticated proposal defaults"
        )
    evidence = proposal_mapping.get("mapping_evidence")
    if type(evidence) is not dict:
        raise ProductionEvidenceComposerError(
            "owner-waived firm mapping lost authenticated proposal evidence"
        )
    if (
        proxy.get("mapping_role") != mapping_role
        or proxy.get("provider_firm_id") != decision_row.get("provider_firm_id")
        or proxy.get("raw_label") != proposal_mapping.get("raw_label")
        or proxy.get("proposed_ordered_rank")
        != proposal_mapping.get("proposed_ordered_rank")
        or proxy.get("source_evidence_id") != evidence.get("evidence_id")
        or proxy.get("source_evidence_sha256") != evidence.get("evidence_sha256")
        or proxy.get("proxy_kind") != _firm_decision.AVAILABILITY_PROXY_KIND
        or proxy.get("historical_availability_claimed") is not False
    ):
        raise ProductionEvidenceComposerError(
            "owner-waived firm mapping proxy lost exact proposal lineage"
        )
    values: dict[str, object] = {
        "provider_firm_id": decision_row.get("provider_firm_id"),
        "firm_name": defaults.get("canonical_firm_name"),
        "raw_label": proposal_mapping.get("raw_label"),
        "ordered_rank": proposal_mapping.get("proposed_ordered_rank"),
        "scale_size": proposal_mapping.get("proposed_scale_size"),
        "scope": defaults.get("scope"),
        "valid_from": proposal_mapping.get("valid_from"),
        "valid_to": proposal_mapping.get("valid_to"),
        "mapping_role": mapping_role,
        "source_evidence_id": evidence.get("evidence_id"),
        "source_evidence_sha256": evidence.get("evidence_sha256"),
        "proxy_kind": proxy.get("proxy_kind"),
        "proxy_open_at": proxy.get("proxy_open_at"),
    }
    if (
        any(type(values[name]) is not str or not values[name] for name in (
            "provider_firm_id", "firm_name", "raw_label", "scope",
            "valid_from", "mapping_role", "source_evidence_id",
            "source_evidence_sha256", "proxy_kind", "proxy_open_at",
        ))
        or type(values["ordered_rank"]) is not int
        or type(values["scale_size"]) is not int
        or not 1 <= values["ordered_rank"] <= values["scale_size"]
        or values["scale_size"] < 2
        or values["valid_to"] is not None
        or mapping_role not in {"ordered_scale", "alias_mapping"}
    ):
        raise ProductionEvidenceComposerError(
            "owner-waived firm mapping scalar contract changed"
        )
    parse_date(values["valid_from"], "owner-waived firm valid_from")
    try:
        proxy_timestamp = datetime.fromisoformat(values["proxy_open_at"])
    except ValueError as exc:
        raise ProductionEvidenceComposerError(
            "owner-waived firm proxy timestamp changed"
        ) from exc
    if (
        proxy_timestamp.tzinfo is None
        or proxy_timestamp.utcoffset() != timedelta(0)
        or proxy_timestamp.isoformat() != values["proxy_open_at"]
    ):
        raise ProductionEvidenceComposerError(
            "owner-waived firm proxy timestamp changed"
        )
    require_identifier(values["provider_firm_id"], "owner-waived provider firm")
    require_identifier(values["source_evidence_id"], "owner-waived evidence")
    require_sha256(values["source_evidence_sha256"], "owner-waived evidence")
    digest = sha256_bytes(canonical_json_bytes(values))
    return OwnerWaivedFirmMapping(**values, mapping_sha256=digest)


def _owner_waived_admission_material(
    decision: FirmOntologyOwnerDecisionArtifact,
) -> tuple[tuple[OwnerWaivedFirmMapping, ...], tuple[str, ...]]:
    decision = _firm_decision.require_firm_ontology_owner_decision(decision)
    mappings: list[OwnerWaivedFirmMapping] = []
    refusals: list[str] = []
    seen_mapping_keys: set[tuple[str, str]] = set()
    seen_firms: set[str] = set()
    rows = tuple(_firm_decision.iter_firm_ontology_owner_decisions(decision))
    if len(rows) != _firm_decision.EXPECTED_FIRM_COUNT:
        raise ProductionEvidenceComposerError(
            "owner-waived firm admission requires exact 74-firm coverage"
        )
    for row in rows:
        if type(row) is not dict:
            raise ProductionEvidenceComposerError(
                "owner-waived firm decision row changed type"
            )
        firm_id = row.get("provider_firm_id")
        if type(firm_id) is not str or not firm_id or firm_id in seen_firms:
            raise ProductionEvidenceComposerError(
                "owner-waived firm decision coverage overlaps"
            )
        seen_firms.add(firm_id)
        status = row.get("decision_status")
        if status == "named_refusal":
            if (
                row.get("accepted_proposal_defaults") is not None
                or row.get("availability_proxies") != []
                or type(row.get("refusal_id")) is not str
                or type(row.get("refusal_sha256")) is not str
            ):
                raise ProductionEvidenceComposerError(
                    "owner-waived named refusal carried mappings or lost identity"
                )
            refusals.append(firm_id)
            continue
        if status != "accepted_deterministic_default":
            raise ProductionEvidenceComposerError(
                "owner-waived firm decision status changed"
            )
        defaults = row.get("accepted_proposal_defaults")
        proxies = row.get("availability_proxies")
        if type(defaults) is not dict or type(proxies) is not list:
            raise ProductionEvidenceComposerError(
                "owner-waived accepted firm lost mappings or proxies"
            )
        proposal_rows: list[tuple[str, Mapping[str, object]]] = []
        for role, key in (
            ("ordered_scale", "ordered_scale"),
            ("alias_mapping", "alias_mappings"),
        ):
            values = defaults.get(key)
            if type(values) is not list:
                raise ProductionEvidenceComposerError(
                    "owner-waived accepted firm mapping collection changed type"
                )
            if any(type(item) is not dict for item in values):
                raise ProductionEvidenceComposerError(
                    "owner-waived accepted firm mapping row changed type"
                )
            proposal_rows.extend((role, item) for item in values)
        if len(proposal_rows) != len(proxies):
            raise ProductionEvidenceComposerError(
                "owner-waived accepted firm mapping/proxy census changed"
            )
        for (role, proposal_mapping), proxy in zip(
            proposal_rows, proxies, strict=True
        ):
            if type(proxy) is not dict:
                raise ProductionEvidenceComposerError(
                    "owner-waived firm availability proxy changed type"
                )
            mapping = _owner_waived_mapping(
                decision_row=row,
                proposal_mapping=proposal_mapping,
                proxy=proxy,
                mapping_role=role,
            )
            key = (mapping.provider_firm_id, mapping.raw_label)
            if key in seen_mapping_keys:
                raise ProductionEvidenceComposerError(
                    "owner-waived firm admission repeats a firm-label mapping"
                )
            seen_mapping_keys.add(key)
            mappings.append(mapping)
    if (
        len(seen_firms) != _firm_decision.EXPECTED_FIRM_COUNT
        or len(seen_firms) != decision.accepted_firm_count + decision.refused_firm_count
        or len(refusals) != decision.refused_firm_count
        or len(mappings) != decision.availability_proxy_count
    ):
        raise ProductionEvidenceComposerError(
            "owner-waived firm admission census contradicts its decision"
        )
    _firm_decision.require_firm_ontology_owner_decision(decision)
    return tuple(mappings), tuple(refusals)


def _owner_waived_admission_record(
    value: OwnerWaivedAcceptedRiskFirmAdmission,
) -> dict[str, object]:
    return {
        "schema": value.schema,
        "owner_decision_id": value.owner_decision_id,
        "owner_decision_sha256": value.owner_decision_sha256,
        "owner_decision_payload_sha256": value.owner_decision_payload_sha256,
        "review_packet_id": value.review_packet_id,
        "review_packet_sha256": value.review_packet_sha256,
        "refusal_ledger_id": value.refusal_ledger_id,
        "refusal_ledger_sha256": value.refusal_ledger_sha256,
        "refusal_ledger_payload_sha256": value.refusal_ledger_payload_sha256,
        "mapping_projection_sha256": value.mapping_projection_sha256,
        "refusal_projection_sha256": value.refusal_projection_sha256,
        "accepted_firm_count": value.accepted_firm_count,
        "refused_firm_count": value.refused_firm_count,
        "mapping_count": value.mapping_count,
        "owner_waiver_scope": value.owner_waiver_scope,
        "deterministic_defaults_only": value.deterministic_defaults_only,
        "named_refusals_excluded": value.named_refusals_excluded,
        "conservative_availability_proxy_only": (
            value.conservative_availability_proxy_only
        ),
        "owner_signature_required_downstream": (
            value.owner_signature_required_downstream
        ),
        "independently_reviewed": value.independently_reviewed,
        "historical_availability_claimed": value.historical_availability_claimed,
        "normal_registry_populated": value.normal_registry_populated,
        "production_authority": value.production_authority,
    }


def build_section72_owner_waived_firm_admission(
    *,
    decision: FirmOntologyOwnerDecisionArtifact,
    review_packet: PhysicalFirmOntologyReviewPacket,
) -> OwnerWaivedAcceptedRiskFirmAdmission:
    """Admit exact clean defaults; retain every exception as a refusal."""

    if type(decision) is not FirmOntologyOwnerDecisionArtifact:
        raise ProductionEvidenceComposerError(
            "owner-waived firm admission requires exact owner-decision type"
        )
    if type(review_packet) is not PhysicalFirmOntologyReviewPacket:
        raise ProductionEvidenceComposerError(
            "owner-waived firm admission requires exact review-packet type"
        )
    try:
        decision = _firm_decision.require_firm_ontology_owner_decision(decision)
        review_packet = _firm_packet.require_physical_firm_ontology_review_packet(
            review_packet
        )
        mappings, refusals = _owner_waived_admission_material(decision)
    except (_firm_decision.FirmOntologyOwnerDecisionError, TypeError, ValueError) as exc:
        raise ProductionEvidenceComposerError(
            "owner-waived firm decision did not authenticate"
        ) from exc
    if (
        decision.packet_id != review_packet.packet_id
        or decision.packet_sha256 != review_packet.packet_sha256
    ):
        raise ProductionEvidenceComposerError(
            "owner-waived firm decision and review packet do not bind"
        )
    value = object.__new__(OwnerWaivedAcceptedRiskFirmAdmission)
    fields: dict[str, object] = {
        "schema": SECTION72_FIRM_ADMISSION_SCHEMA,
        "admission_id": "",
        "admission_sha256": "",
        "owner_decision": decision,
        "review_packet": review_packet,
        "review_packet_id": review_packet.packet_id,
        "review_packet_sha256": review_packet.packet_sha256,
        "owner_decision_id": decision.decision_id,
        "owner_decision_sha256": decision.decision_sha256,
        "owner_decision_payload_sha256": decision.decision_payload_sha256,
        "refusal_ledger_id": decision.refusal_ledger_id,
        "refusal_ledger_sha256": decision.refusal_ledger_sha256,
        "refusal_ledger_payload_sha256": decision.refusal_ledger_payload_sha256,
        "mappings": mappings,
        "refused_provider_firm_ids": refusals,
        "mapping_projection_sha256": sha256_bytes(canonical_json_bytes(
            [item.to_record() for item in mappings]
        )),
        "refusal_projection_sha256": sha256_bytes(canonical_json_bytes(
            list(refusals)
        )),
        "accepted_firm_count": decision.accepted_firm_count,
        "refused_firm_count": decision.refused_firm_count,
        "mapping_count": len(mappings),
        "owner_waiver_scope": SECTION72_OWNER_WAIVER_SCOPE,
        "deterministic_defaults_only": True,
        "named_refusals_excluded": True,
        "conservative_availability_proxy_only": True,
        "owner_signature_required_downstream": True,
        "independently_reviewed": False,
        "historical_availability_claimed": False,
        "normal_registry_populated": False,
        "production_authority": False,
    }
    if set(fields) != {item.name for item in dataclasses.fields(value)}:
        raise ProductionEvidenceComposerError(
            "owner-waived firm admission field inventory changed"
        )
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    digest = sha256_bytes(canonical_json_bytes(_owner_waived_admission_record(value)))
    object.__setattr__(value, "admission_sha256", digest)
    object.__setattr__(
        value, "admission_id", f"arv2-section72-firm-admission-{digest[:24]}"
    )
    identity = id(value)
    reference = weakref.ref(
        value,
        lambda ref, key=identity: _forget_owner_waived_firm_admission(key, ref),
    )
    with _OWNER_WAIVED_FIRM_LOCK:
        _OWNER_WAIVED_FIRM_ADMISSIONS[identity] = (
            reference,
            canonical_json_bytes(_owner_waived_admission_record(value)),
            (
                id(value.owner_decision), id(value.review_packet),
                id(value.mappings),
                *(id(item) for item in value.mappings),
                id(value.refused_provider_firm_ids),
            ),
            weakref.ref(decision),
            os.getpid(),
        )
    return require_section72_owner_waived_firm_admission(value)


def require_section72_owner_waived_firm_admission(
    value: OwnerWaivedAcceptedRiskFirmAdmission,
) -> OwnerWaivedAcceptedRiskFirmAdmission:
    if type(value) is not OwnerWaivedAcceptedRiskFirmAdmission:
        raise ProductionEvidenceComposerError(
            "owner-waived firm admission changed type"
        )
    with _OWNER_WAIVED_FIRM_LOCK:
        authority = _OWNER_WAIVED_FIRM_ADMISSIONS.get(id(value))
    topology = (
        id(value.owner_decision), id(value.review_packet),
        id(value.mappings),
        *(id(item) for item in value.mappings),
        id(value.refused_provider_firm_ids),
    )
    if (
        authority is None
        or authority[0]() is not value
        or authority[1] != canonical_json_bytes(_owner_waived_admission_record(value))
        or authority[2] != topology
        or authority[3]() is not value.owner_decision
        or authority[4] != os.getpid()
    ):
        raise ProductionEvidenceComposerError(
            "owner-waived firm admission lost builder authority"
        )
    try:
        decision = _firm_decision.require_firm_ontology_owner_decision(
            value.owner_decision
        )
        packet = _firm_packet.require_physical_firm_ontology_review_packet(
            value.review_packet
        )
        mappings, refusals = _owner_waived_admission_material(decision)
    except (_firm_decision.FirmOntologyOwnerDecisionError, TypeError, ValueError) as exc:
        raise ProductionEvidenceComposerError(
            "owner-waived firm admission parent did not reauthenticate"
        ) from exc
    true_flags = (
        value.deterministic_defaults_only,
        value.named_refusals_excluded,
        value.conservative_availability_proxy_only,
        value.owner_signature_required_downstream,
    )
    false_flags = (
        value.independently_reviewed,
        value.historical_availability_claimed,
        value.normal_registry_populated,
        value.production_authority,
    )
    digest = sha256_bytes(canonical_json_bytes(_owner_waived_admission_record(value)))
    if (
        any(type(item) is not bool or item is not True for item in true_flags)
        or any(type(item) is not bool or item is not False for item in false_flags)
        or value.schema != SECTION72_FIRM_ADMISSION_SCHEMA
        or value.owner_waiver_scope != SECTION72_OWNER_WAIVER_SCOPE
        or value.owner_decision_id != decision.decision_id
        or value.owner_decision_sha256 != decision.decision_sha256
        or value.owner_decision_payload_sha256 != decision.decision_payload_sha256
        or value.review_packet_id != packet.packet_id
        or value.review_packet_sha256 != packet.packet_sha256
        or decision.packet_id != packet.packet_id
        or decision.packet_sha256 != packet.packet_sha256
        or value.refusal_ledger_id != decision.refusal_ledger_id
        or value.refusal_ledger_sha256 != decision.refusal_ledger_sha256
        or value.refusal_ledger_payload_sha256
        != decision.refusal_ledger_payload_sha256
        or value.mappings != mappings
        or value.refused_provider_firm_ids != refusals
        or value.mapping_projection_sha256 != sha256_bytes(canonical_json_bytes(
            [item.to_record() for item in mappings]
        ))
        or value.refusal_projection_sha256 != sha256_bytes(canonical_json_bytes(
            list(refusals)
        ))
        or value.accepted_firm_count != decision.accepted_firm_count
        or value.refused_firm_count != decision.refused_firm_count
        or value.mapping_count != len(mappings)
        or value.admission_sha256 != digest
        or value.admission_id
        != f"arv2-section72-firm-admission-{digest[:24]}"
    ):
        raise ProductionEvidenceComposerError(
            "owner-waived firm admission semantic binding changed"
        )
    return value


def iter_section72_owner_waived_firm_mappings(
    value: OwnerWaivedAcceptedRiskFirmAdmission,
) -> Iterator[OwnerWaivedFirmMapping]:
    admission = require_section72_owner_waived_firm_admission(value)
    yield from admission.mappings
    require_section72_owner_waived_firm_admission(admission)


@dataclasses.dataclass(frozen=True, slots=True)
class FirmOntologyAvailabilityEntry:
    ontology_entry_sha256: str
    source_evidence_id: str
    source_evidence_sha256: str
    available_at: str
    valid_to_available_at: str | None

    def __post_init__(self) -> None:
        require_sha256(self.ontology_entry_sha256, "ontology_entry_sha256")
        require_identifier(self.source_evidence_id, "source_evidence_id")
        require_sha256(self.source_evidence_sha256, "source_evidence_sha256")
        base = parse_utc_timestamp(self.available_at, "firm availability")
        if self.valid_to_available_at is not None:
            if type(self.valid_to_available_at) is not str:
                raise ProductionEvidenceComposerError(
                    "valid_to_available_at must be exact text or null"
                )
            if parse_utc_timestamp(
                self.valid_to_available_at, "firm closure availability"
            ) < base:
                raise ProductionEvidenceComposerError(
                    "firm closure availability predates base evidence"
                )

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, init=False)
class ReviewedFirmOntologyAvailability:
    schema: str
    artifact_id: str
    artifact_sha256: str
    ontology: ReviewedFirmRatingOntology
    ontology_id: str
    ontology_sha256: str
    entries: tuple[FirmOntologyAvailabilityEntry, ...]
    entry_projection_sha256: str
    review_receipt_id: str
    review_receipt_sha256: str
    availability_path: Path = dataclasses.field(repr=False)
    review_path: Path = dataclasses.field(repr=False)
    availability_path_fingerprint: tuple[object, ...] = dataclasses.field(repr=False)
    review_path_fingerprint: tuple[object, ...] = dataclasses.field(repr=False)
    availability_bytes: bytes = dataclasses.field(repr=False)
    review_bytes: bytes = dataclasses.field(repr=False)
    independently_reviewed: bool
    complete_entry_census: bool
    contains_outcome_or_price: bool
    provider_access: bool
    quantconnect_access: bool
    outcome_access: bool


_AVAILABILITY_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[ReviewedFirmOntologyAvailability],
        tuple[object, ...],
    ],
] = {}
_AVAILABILITY_LOCK = threading.RLock()


def _forget_availability(identity: int, reference: object) -> None:
    with _AVAILABILITY_LOCK:
        current = _AVAILABILITY_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _AVAILABILITY_AUTHORITIES.pop(identity, None)


def _read_private_regular(
    path: Path, *, maximum_bytes: int, name: str
) -> tuple[bytes, tuple[object, ...]]:
    if type(path) is not type(Path()) or not path.is_absolute() or ".." in path.parts:
        raise ProductionEvidenceComposerError(f"{name} path is not exact absolute Path")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ProductionEvidenceComposerError(f"{name} is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.getuid()
            or before.st_mode & 0o077
            or not 0 < before.st_size <= maximum_bytes
        ):
            raise ProductionEvidenceComposerError(
                f"{name} is not one bounded owner-only regular file"
            )
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ProductionEvidenceComposerError(f"{name} ended early")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ProductionEvidenceComposerError(f"{name} grew while read")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = (
        str(path), before.st_dev, before.st_ino, before.st_size,
        before.st_mtime_ns, before.st_ctime_ns, before.st_mode,
        before.st_uid, before.st_nlink,
    )
    after_identity = (
        str(path), after.st_dev, after.st_ino, after.st_size,
        after.st_mtime_ns, after.st_ctime_ns, after.st_mode,
        after.st_uid, after.st_nlink,
    )
    if identity != after_identity:
        raise ProductionEvidenceComposerError(f"{name} changed while read")
    return b"".join(chunks), identity


def _canonical_object(payload: bytes, name: str) -> dict[str, Any]:
    if type(payload) is not bytes or not payload:
        raise ProductionEvidenceComposerError(f"{name} bytes are absent")
    try:
        parsed = strict_json_loads(decode_utf8(payload, name), name)
    except CanonicalEvidenceError as exc:
        raise ProductionEvidenceComposerError(f"{name} is not strict JSON") from exc
    if type(parsed) is not dict or canonical_json_bytes(parsed) != payload:
        raise ProductionEvidenceComposerError(f"{name} is not canonical JSON")
    return parsed


def _entry_sha(entry: FirmRatingMapEntry) -> str:
    return sha256_bytes(canonical_json_bytes(entry.to_record()))


def _availability_fingerprint(
    value: ReviewedFirmOntologyAvailability,
) -> tuple[object, ...]:
    return (
        id(value.ontology), value.schema, value.artifact_id, value.artifact_sha256,
        value.ontology_id, value.ontology_sha256,
        tuple(canonical_json_bytes(item.to_record()) for item in value.entries),
        value.entry_projection_sha256, value.review_receipt_id,
        value.review_receipt_sha256, id(value.availability_path), id(value.review_path),
        value.availability_path_fingerprint, value.review_path_fingerprint,
        value.availability_bytes, value.review_bytes,
        value.independently_reviewed, value.complete_entry_census,
        value.contains_outcome_or_price, value.provider_access,
        value.quantconnect_access, value.outcome_access,
    )


def load_reviewed_firm_ontology_availability(
    *,
    ontology: ReviewedFirmRatingOntology,
    availability_path: Path,
    review_path: Path,
) -> ReviewedFirmOntologyAvailability:
    """Load exact external historical-availability evidence and its review."""

    ontology = firm_module.require_registered_production_firm_ontology(ontology)
    availability_bytes, availability_stat = _read_private_regular(
        availability_path,
        maximum_bytes=MAX_FIRM_AVAILABILITY_BYTES,
        name="firm ontology availability",
    )
    review_bytes, review_stat = _read_private_regular(
        review_path,
        maximum_bytes=MAX_FIRM_AVAILABILITY_REVIEW_BYTES,
        name="firm ontology availability review",
    )
    raw = _canonical_object(availability_bytes, "firm ontology availability")
    if set(raw) != _AVAILABILITY_FIELDS or raw["schema"] != FIRM_AVAILABILITY_SCHEMA:
        raise ProductionEvidenceComposerError("firm availability fields changed")
    if (
        raw["ontology_id"] != ontology.ontology_id
        or raw["ontology_sha256"] != ontology.payload_sha256
        or type(raw["entries"]) is not list
    ):
        raise ProductionEvidenceComposerError("firm availability ontology parent changed")
    parsed_entries: list[FirmOntologyAvailabilityEntry] = []
    for item in raw["entries"]:
        if type(item) is not dict or set(item) != _AVAILABILITY_ENTRY_FIELDS:
            raise ProductionEvidenceComposerError("firm availability entry fields changed")
        try:
            parsed_entries.append(FirmOntologyAvailabilityEntry(**item))
        except (CanonicalEvidenceError, TypeError, ValueError) as exc:
            raise ProductionEvidenceComposerError("firm availability entry is invalid") from exc
    entries = tuple(parsed_entries)
    if entries != tuple(sorted(entries, key=lambda item: item.ontology_entry_sha256)):
        raise ProductionEvidenceComposerError("firm availability entries are not sorted")
    if len({item.ontology_entry_sha256 for item in entries}) != len(entries):
        raise ProductionEvidenceComposerError("firm availability entry repeats")
    ontology_by_hash = {_entry_sha(item): item for item in ontology.entries}
    if set(ontology_by_hash) != {item.ontology_entry_sha256 for item in entries}:
        raise ProductionEvidenceComposerError(
            "firm availability is not an exhaustive ontology-entry census"
        )
    for item in entries:
        ontology_entry = ontology_by_hash[item.ontology_entry_sha256]
        if (
            item.source_evidence_id != ontology_entry.source_evidence_id
            or item.source_evidence_sha256 != ontology_entry.source_evidence_sha256
            or (ontology_entry.valid_to is None)
            != (item.valid_to_available_at is None)
        ):
            raise ProductionEvidenceComposerError(
                "firm availability source or closure binding changed"
            )
    projection = sha256_bytes(canonical_json_bytes([item.to_record() for item in entries]))
    review = _canonical_object(review_bytes, "firm ontology availability review")
    if set(review) != _REVIEW_FIELDS:
        raise ProductionEvidenceComposerError("firm availability review fields changed")
    booleans = (
        review["complete_ontology_entry_census_verified"],
        review["historical_availability_verified_from_external_source_evidence"],
        review["no_review_time_or_valid_from_imputation_verified"],
    )
    if (
        review["schema"] != FIRM_AVAILABILITY_REVIEW_SCHEMA
        or review["availability_sha256"] != sha256_bytes(availability_bytes)
        or review["availability_byte_count"] != len(availability_bytes)
        or review["ontology_id"] != ontology.ontology_id
        or review["ontology_sha256"] != ontology.payload_sha256
        or review["entry_count"] != len(entries)
        or review["entry_projection_sha256"] != projection
        or review["status"] != FIRM_AVAILABILITY_REVIEW_STATUS
        or any(type(flag) is not bool or flag is not True for flag in booleans)
        or type(review["contains_outcome_or_price"]) is not bool
        or review["contains_outcome_or_price"] is not False
    ):
        raise ProductionEvidenceComposerError(
            "firm availability review is not exact and affirmative"
        )
    seed = dict(review)
    seed["receipt_id"] = None
    seed["receipt_sha256"] = None
    digest = sha256_bytes(canonical_json_bytes(seed))
    if (
        review["receipt_sha256"] != digest
        or review["receipt_id"] != f"arv2-firm-availability-review-{digest[:24]}"
    ):
        raise ProductionEvidenceComposerError("firm availability review identity changed")
    artifact_sha = sha256_bytes(availability_bytes)
    value = object.__new__(ReviewedFirmOntologyAvailability)
    values: dict[str, object] = {
        "schema": FIRM_AVAILABILITY_SCHEMA,
        "artifact_id": f"arv2-firm-availability-{artifact_sha[:24]}",
        "artifact_sha256": artifact_sha,
        "ontology": ontology,
        "ontology_id": ontology.ontology_id,
        "ontology_sha256": ontology.payload_sha256,
        "entries": entries,
        "entry_projection_sha256": projection,
        "review_receipt_id": review["receipt_id"],
        "review_receipt_sha256": digest,
        "availability_path": availability_path,
        "review_path": review_path,
        "availability_path_fingerprint": availability_stat,
        "review_path_fingerprint": review_stat,
        "availability_bytes": availability_bytes,
        "review_bytes": review_bytes,
        "independently_reviewed": True,
        "complete_entry_census": True,
        "contains_outcome_or_price": False,
        "provider_access": False,
        "quantconnect_access": False,
        "outcome_access": False,
    }
    for name, item in values.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_availability(key, ref)
    )
    with _AVAILABILITY_LOCK:
        _AVAILABILITY_AUTHORITIES[identity] = (
            reference,
            _availability_fingerprint(value),
        )
    return require_reviewed_firm_ontology_availability(value)


def require_reviewed_firm_ontology_availability(
    value: ReviewedFirmOntologyAvailability,
) -> ReviewedFirmOntologyAvailability:
    if type(value) is not ReviewedFirmOntologyAvailability:
        raise ProductionEvidenceComposerError("firm availability changed type")
    with _AVAILABILITY_LOCK:
        authority = _AVAILABILITY_AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or authority[1] != _availability_fingerprint(value)
    ):
        raise ProductionEvidenceComposerError("firm availability lost loader authority")
    ontology = firm_module.require_registered_production_firm_ontology(value.ontology)
    if (
        ontology is not value.ontology
        or value.ontology_id != ontology.ontology_id
        or value.ontology_sha256 != ontology.payload_sha256
        or any(
            type(flag) is not bool or flag is not expected
            for flag, expected in (
                (value.independently_reviewed, True),
                (value.complete_entry_census, True),
                (value.contains_outcome_or_price, False),
                (value.provider_access, False),
                (value.quantconnect_access, False),
                (value.outcome_access, False),
            )
        )
    ):
        raise ProductionEvidenceComposerError("firm availability authority changed")
    availability, availability_stat = _read_private_regular(
        value.availability_path,
        maximum_bytes=MAX_FIRM_AVAILABILITY_BYTES,
        name="firm ontology availability",
    )
    review, review_stat = _read_private_regular(
        value.review_path,
        maximum_bytes=MAX_FIRM_AVAILABILITY_REVIEW_BYTES,
        name="firm ontology availability review",
    )
    if (
        availability_stat != value.availability_path_fingerprint
        or review_stat != value.review_path_fingerprint
        or availability != value.availability_bytes
        or review != value.review_bytes
    ):
        raise ProductionEvidenceComposerError("firm availability source changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class ProductionEvidenceCompositionTerminal:
    locator_sha256: str
    security: str
    firm: str
    common_event: str
    sector: str
    control: str
    q_data: str
    upstream_reason: str | None
    terminal_sha256: str

    def __post_init__(self) -> None:
        require_sha256(self.locator_sha256, "composition locator_sha256")
        for name in ("security", "firm", "common_event", "sector", "control", "q_data"):
            value = getattr(self, name)
            if type(value) is not str or value not in {
                "accepted", "missing", "ambiguous", "upstream_named_refusal",
                "physical_terminal_missing", "physical_terminal_refused",
                "physical_terminal_mismatch", "unreviewed_or_unavailable",
            }:
                raise ProductionEvidenceComposerError(
                    f"unknown composition disposition for {name}"
                )
        if self.upstream_reason is not None:
            require_text(self.upstream_reason, "upstream_reason", maximum_length=2048)
        require_sha256(self.terminal_sha256, "composition terminal_sha256")
        if self.terminal_sha256 != sha256_bytes(canonical_json_bytes(self.semantic_record())):
            raise ProductionEvidenceComposerError(
                "composition terminal hash is not content-derived"
            )

    def semantic_record(self) -> dict[str, object]:
        return {
            "schema": COMPOSITION_TERMINAL_SCHEMA,
            "locator_sha256": self.locator_sha256,
            "components": {
                "security": self.security,
                "firm": self.firm,
                "common_event": self.common_event,
                "sector": self.sector,
                "control": self.control,
                "q_data": self.q_data,
            },
            "upstream_reason": self.upstream_reason,
        }

    def to_record(self) -> dict[str, object]:
        return {**self.semantic_record(), "terminal_sha256": self.terminal_sha256}


def _composition_terminal(
    *, locator_sha256: str, dispositions: Mapping[str, str], upstream_reason: str | None
) -> ProductionEvidenceCompositionTerminal:
    semantic = {
        "schema": COMPOSITION_TERMINAL_SCHEMA,
        "locator_sha256": locator_sha256,
        "components": dict(dispositions),
        "upstream_reason": upstream_reason,
    }
    return ProductionEvidenceCompositionTerminal(
        locator_sha256=locator_sha256,
        security=dispositions["security"],
        firm=dispositions["firm"],
        common_event=dispositions["common_event"],
        sector=dispositions["sector"],
        control=dispositions["control"],
        q_data=dispositions["q_data"],
        upstream_reason=upstream_reason,
        terminal_sha256=sha256_bytes(canonical_json_bytes(semantic)),
    )


@dataclasses.dataclass(frozen=True, init=False)
class ProductionEvidenceComposerCandidate:
    schema: str
    candidate_id: str
    candidate_sha256: str
    pair: AcceptedRiskInputPair
    pair_id: str
    pair_sha256: str
    historical_bridge: historical_module.ReviewedHistoricalUniverseToPreopenBridge
    historical_bridge_id: str
    historical_bridge_sha256: str
    firm_ontology: ReviewedFirmRatingOntology
    firm_ontology_id: str
    firm_ontology_sha256: str
    firm_availability: ReviewedFirmOntologyAvailability
    firm_availability_id: str
    firm_availability_sha256: str
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt
    preopen_acquisition_id: str
    preopen_acquisition_sha256: str
    terminal_archive: PhysicalPreopenTerminalArchive | PhysicalProductionEvidenceTerminalArchive
    terminal_archive_id: str
    terminal_archive_sha256: str
    authority: ProductionEvidenceAuthority
    authority_id: str
    authority_sha256: str
    evidence_package_bytes: bytes = dataclasses.field(repr=False)
    evidence_package_sha256: str
    external_review_pin_candidate_bytes: bytes = dataclasses.field(repr=False)
    external_review_pin_candidate_sha256: str
    composition_terminals: tuple[ProductionEvidenceCompositionTerminal, ...]
    composition_terminal_projection_sha256: str
    candidate_rating_row_count: int
    sidecar_row_count: int
    physical_terminal_count: int
    physical_accepted_count: int
    physical_refusal_count: int
    sqlite_peak_page_bytes: int
    package_byte_count: int
    complete_candidate_rating_census: bool
    physical_sources_reauthenticated: bool
    independent_package_review_required: bool
    production_evidence_receipt_available: bool
    provider_access: bool
    credential_access: bool
    quantconnect_access: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool


_COMPOSER_AUTHORITIES: dict[
    int,
    tuple[weakref.ReferenceType[ProductionEvidenceComposerCandidate], tuple[object, ...]],
] = {}
_COMPOSER_LOCK = threading.RLock()


def _forget_composer(identity: int, reference: object) -> None:
    with _COMPOSER_LOCK:
        current = _COMPOSER_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _COMPOSER_AUTHORITIES.pop(identity, None)


def _candidate_semantic(value: ProductionEvidenceComposerCandidate) -> dict[str, object]:
    return {
        "schema": COMPOSER_SCHEMA,
        "pair_id": value.pair_id,
        "pair_sha256": value.pair_sha256,
        "historical_bridge_id": value.historical_bridge_id,
        "historical_bridge_sha256": value.historical_bridge_sha256,
        "firm_ontology_id": value.firm_ontology_id,
        "firm_ontology_sha256": value.firm_ontology_sha256,
        "firm_availability_id": value.firm_availability_id,
        "firm_availability_sha256": value.firm_availability_sha256,
        "preopen_acquisition_id": value.preopen_acquisition_id,
        "preopen_acquisition_sha256": value.preopen_acquisition_sha256,
        "terminal_archive_id": value.terminal_archive_id,
        "terminal_archive_sha256": value.terminal_archive_sha256,
        "authority_id": value.authority_id,
        "authority_sha256": value.authority_sha256,
        "evidence_package_sha256": value.evidence_package_sha256,
        "evidence_package_byte_count": value.package_byte_count,
        "external_review_pin_candidate_sha256": (
            value.external_review_pin_candidate_sha256
        ),
        "composition_terminal_projection_sha256": (
            value.composition_terminal_projection_sha256
        ),
        "census": {
            "candidate_rating_row_count": value.candidate_rating_row_count,
            "sidecar_row_count": value.sidecar_row_count,
            "physical_terminal_count": value.physical_terminal_count,
            "physical_accepted_count": value.physical_accepted_count,
            "physical_refusal_count": value.physical_refusal_count,
        },
        "observed_capacity": {
            "sqlite_peak_page_bytes": value.sqlite_peak_page_bytes,
            "package_byte_count": value.package_byte_count,
            "maximum_sqlite_page_bytes": MAX_COMPOSER_SPOOL_BYTES,
            "maximum_package_byte_count": MAX_PACKAGE_BYTES,
        },
        "complete_candidate_rating_census": True,
        "physical_sources_reauthenticated": True,
        "independent_package_review_required": True,
        "production_evidence_receipt_available": False,
        "capabilities": {
            "provider_access": False,
            "credential_access": False,
            "quantconnect_access": False,
            "outcome_access": False,
            "result_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


def _candidate_fingerprint(value: ProductionEvidenceComposerCandidate) -> tuple[object, ...]:
    return (
        id(value.pair), id(value.historical_bridge), id(value.firm_ontology),
        id(value.firm_availability), id(value.preopen_acquisition_receipt),
        id(value.terminal_archive), id(value.authority),
        id(value.composition_terminals),
        tuple(id(item) for item in value.composition_terminals),
        value.evidence_package_bytes, value.external_review_pin_candidate_bytes,
        canonical_json_bytes(_candidate_semantic(value)),
    )


def _require_terminal_archive(
    archive: PhysicalPreopenTerminalArchive | PhysicalProductionEvidenceTerminalArchive,
) -> PhysicalPreopenTerminalArchive | PhysicalProductionEvidenceTerminalArchive:
    if type(archive) is PhysicalPreopenTerminalArchive:
        return require_physical_preopen_terminal_archive(archive)
    if type(archive) is PhysicalProductionEvidenceTerminalArchive:
        return require_physical_production_evidence_terminal_archive(archive)
    raise ProductionEvidenceComposerError("physical terminal archive changed type")


def _truth_sources(receipt: PreopenControlAcquisitionReceipt) -> dict[str, tuple[str, str]]:
    records = acquisition_truth_source_binding_records(receipt)
    return {
        item["kind"]: (item["artifact_id"], item["artifact_sha256"])
        for item in records
    }


def _reauthenticate_parents(
    *,
    pair: AcceptedRiskInputPair,
    bridge: historical_module.ReviewedHistoricalUniverseToPreopenBridge,
    ontology: ReviewedFirmRatingOntology,
    availability: ReviewedFirmOntologyAvailability,
    preopen: PreopenControlAcquisitionReceipt,
    archive: PhysicalPreopenTerminalArchive | PhysicalProductionEvidenceTerminalArchive,
) -> tuple[dict[str, tuple[str, str]], tuple[EvidenceSourceBinding, ...]]:
    pair = require_accepted_risk_input_pair(pair)
    bridge = historical_module.require_reviewed_historical_universe_to_preopen_bridge(
        bridge
    )
    ontology = firm_module.require_registered_production_firm_ontology(ontology)
    availability = require_reviewed_firm_ontology_availability(availability)
    preopen = require_reviewed_preopen_control_acquisition_receipt(preopen)
    archive = _require_terminal_archive(archive)
    sources = _truth_sources(preopen)
    required_truth = {
        "accepted_risk_capture", "eligible_universe", "security_master",
        "firm_ontology", "common_event", "sector_classification",
        "preopen_control", "data_quality",
    }
    if set(sources) != required_truth:
        raise ProductionEvidenceComposerError("pre-open truth-source census changed")
    if (
        bridge.pair_id != pair.pair_id
        or bridge.pair_sha256 != pair.pair_sha256
        or bridge.derived_capture_id != pair.capture.capture_id
        or bridge.derived_capture_sha256 != pair.capture.capture_sha256
        or preopen.input_manifest_sha256 != bridge.closed_input_manifest_sha256
        or preopen.input_source_inventory_sha256 != bridge.input_shard_inventory_sha256
        or sources["accepted_risk_capture"]
        != (bridge.accepted_risk_bridge_id, bridge.accepted_risk_bridge_sha256)
        or sources["eligible_universe"]
        != (
            bridge.discovery_eligible_universe_artifact_id,
            bridge.discovery_eligible_universe_artifact_sha256,
        )
        or sources["security_master"]
        != (bridge.security_master_artifact_id, bridge.security_master_artifact_sha256)
        or sources["preopen_control"]
        != (bridge.physical_candidate_id, bridge.physical_candidate_sha256)
        or sources["firm_ontology"] != (ontology.ontology_id, ontology.payload_sha256)
        or availability.ontology is not ontology
        or archive.preopen_acquisition_receipt is not preopen
        or tuple(item.decision_session for item in preopen.control_sessions)[0]
        != bridge.first_session
        or tuple(item.decision_session for item in preopen.control_sessions)[-1]
        != bridge.last_session
    ):
        raise ProductionEvidenceComposerError(
            "production-evidence parents do not share exact reviewed lineage"
        )
    kind_by_truth = {
        EvidenceSourceKind.SECURITY_MASTER: "security_master",
        EvidenceSourceKind.FIRM_ONTOLOGY: "firm_ontology",
        EvidenceSourceKind.COMMON_EVENT: "common_event",
        EvidenceSourceKind.SECTOR_CLASSIFICATION: "sector_classification",
        EvidenceSourceKind.PREOPEN_CONTROL: "preopen_control",
        EvidenceSourceKind.DATA_QUALITY: "data_quality",
    }
    bindings = tuple(
        EvidenceSourceBinding(
            kind=kind,
            artifact_id=sources[kind_by_truth[kind]][0],
            artifact_sha256=sources[kind_by_truth[kind]][1],
            reviewed=True,
            point_in_time=True,
        )
        for kind in EvidenceSourceKind
    )
    return sources, bindings


def _sqlite_bytes(connection: sqlite3.Connection) -> int:
    page_count = connection.execute("PRAGMA page_count").fetchone()[0]
    page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    if type(page_count) is not int or type(page_size) is not int:
        raise ProductionEvidenceComposerError("SQLite capacity counters changed type")
    observed = page_count * page_size
    if observed > MAX_COMPOSER_SPOOL_BYTES:
        raise ProductionEvidenceComposerCapacityRefusal(
            "production-evidence SQLite spool exceeded the fixed byte ceiling"
        )
    return observed


def _open_spool(root: Path) -> tuple[sqlite3.Connection, Path]:
    path = root / "production-evidence.sqlite3"
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=FILE")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "CREATE TABLE sidecars(locator_sha256 TEXT NOT NULL, record BLOB NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX sidecars_locator ON sidecars(locator_sha256)"
        )
        connection.execute(
            "CREATE TABLE terminals("
            "decision_session TEXT NOT NULL, security_id TEXT NOT NULL, "
            "disposition TEXT NOT NULL, record BLOB NOT NULL, "
            "PRIMARY KEY(decision_session, security_id))"
        )
    except Exception:
        connection.close()
        raise
    os.chmod(path, 0o600)
    return connection, path


def _validate_sidecar_record(value: object) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _SIDECAR_FIELDS:
        raise ProductionEvidenceComposerError("analyst-event sidecar fields changed")
    semantic = dict(value)
    declared = semantic.pop("binding_sha256")
    if (
        value["schema"] != historical_module.ANALYST_EVENT_BINDING_SCHEMA
        or type(declared) is not str
        or _HEX.fullmatch(declared) is None
        or sha256_bytes(canonical_json_bytes(semantic)) != declared
        or value["source_role"] != MassiveSourceRole.ANALYST_RATINGS.value
        or type(value["locator_sha256"]) is not str
        or _HEX.fullmatch(value["locator_sha256"]) is None
        or type(value["raw_row_sha256"]) is not str
        or _HEX.fullmatch(value["raw_row_sha256"]) is None
        or value["binding_disposition"] not in ("accepted", "named_refusal")
    ):
        raise ProductionEvidenceComposerError(
            "analyst-event sidecar identity or disposition changed"
        )
    if value["binding_disposition"] == "accepted":
        required_text = (
            "provider_event_id", "common_event_id", "physical_security_id",
            "decision_session", "available_at", "rating_seed_row_sha256",
            "qc_security_id", "cusip", "issuer_id", "share_class_id",
            "listing_id", "historical_ticker", "mapping_first_session",
            "mapping_last_session", "mapping_available_at",
            "mapping_row_sha256", "q_data", "q_data_evidence_sha256",
        )
        if (
            value["binding_reason"] is not None
            or value["rating_admitted"] is not True
            or type(value["decision_session_ordinal"]) is not int
            or value["mapping_closure_available_at"] is not None
            or any(type(value[name]) is not str for name in required_text)
        ):
            raise ProductionEvidenceComposerError(
                "accepted analyst-event sidecar lost an exact member"
            )
        for name in (
            "rating_seed_row_sha256", "mapping_row_sha256",
            "q_data_evidence_sha256",
        ):
            require_sha256(value[name], name)
        for name in (
            "provider_event_id", "common_event_id", "physical_security_id",
            "issuer_id", "share_class_id", "listing_id",
        ):
            require_identifier(value[name], name)
        for name in (
            "decision_session", "mapping_first_session", "mapping_last_session"
        ):
            parse_date(value[name], name)
        parse_utc_timestamp(value["available_at"], "rating sidecar availability")
        parse_utc_timestamp(value["mapping_available_at"], "mapping availability")
        try:
            q_data = Decimal(value["q_data"])
        except (InvalidOperation, ValueError) as exc:
            raise ProductionEvidenceComposerError("sidecar q_data is not Decimal") from exc
        if not q_data.is_finite() or not Decimal(0) <= q_data <= Decimal(1):
            raise ProductionEvidenceComposerError("sidecar q_data is outside [0,1]")
    elif value["binding_disposition"] == "named_refusal":
        if type(value["binding_reason"]) is not str or not value["binding_reason"]:
            raise ProductionEvidenceComposerError(
                "named analyst-event refusal lost its reason"
            )
    else:
        raise ProductionEvidenceComposerError("unknown analyst-event disposition")
    return value


def _spool_sidecars(
    connection: sqlite3.Connection,
    bridge: historical_module.ReviewedHistoricalUniverseToPreopenBridge,
) -> tuple[int, int]:
    count = 0
    peak = _sqlite_bytes(connection)
    connection.execute("BEGIN")
    try:
        for shard in historical_module.iter_reviewed_historical_analyst_event_binding_shards(
            bridge
        ):
            payload = shard.canonical_json_lines
            if (
                type(payload) is not bytes
                or len(payload) != shard.uncompressed_byte_count
                or sha256_bytes(payload) != shard.uncompressed_sha256
                or len(payload) > historical_module.MAX_EVIDENCE_UNCOMPRESSED_BYTES
            ):
                raise ProductionEvidenceComposerError(
                    "analyst-event sidecar shard content changed"
                )
            shard_count = 0
            for line in payload.splitlines(keepends=True):
                if not line.endswith(b"\n") or len(line) > MAX_COMPOSER_ROW_BYTES:
                    raise ProductionEvidenceComposerError(
                        "analyst-event sidecar line exceeds canonical bounds"
                    )
                raw = _canonical_object(line, "analyst-event sidecar row")
                raw = _validate_sidecar_record(raw)
                connection.execute(
                    "INSERT INTO sidecars(locator_sha256, record) VALUES (?, ?)",
                    (raw["locator_sha256"], sqlite3.Binary(line)),
                )
                count += 1
                shard_count += 1
                if count > MAX_COMPOSER_SIDECAR_ROW_COUNT:
                    raise ProductionEvidenceComposerCapacityRefusal(
                        "analyst-event sidecar row census exceeded fixed capacity"
                    )
                if count % 1024 == 0:
                    peak = max(peak, _sqlite_bytes(connection))
            if shard_count != shard.row_count:
                raise ProductionEvidenceComposerError(
                    "analyst-event sidecar shard row count changed"
                )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    if count != bridge.analyst_event_binding_row_count:
        raise ProductionEvidenceComposerError(
            "analyst-event sidecar exhaustive row count changed"
        )
    return count, max(peak, _sqlite_bytes(connection))


def _spool_terminals(
    connection: sqlite3.Connection,
    archive: PhysicalPreopenTerminalArchive | PhysicalProductionEvidenceTerminalArchive,
) -> tuple[tuple[int, int, int], int]:
    total = accepted_count = refusal_count = 0
    peak = _sqlite_bytes(connection)
    connection.execute("BEGIN")
    try:
        for block in iter_physical_preopen_terminal_sessions(archive):
            if type(block) is not PhysicalTerminalSessionBlock:
                raise ProductionEvidenceComposerError(
                    "physical terminal iterator changed block type"
                )
            for item in block.accepted:
                payload = canonical_json_bytes(item.to_record())
                connection.execute(
                    "INSERT INTO terminals(decision_session, security_id, disposition, record) "
                    "VALUES (?, ?, 'accepted', ?)",
                    (item.decision_session, item.security_id, sqlite3.Binary(payload)),
                )
                total += 1
                accepted_count += 1
            for item in block.refused:
                payload = canonical_json_bytes(item.to_record())
                connection.execute(
                    "INSERT INTO terminals(decision_session, security_id, disposition, record) "
                    "VALUES (?, ?, 'named_refusal', ?)",
                    (item.decision_session, item.security_id, sqlite3.Binary(payload)),
                )
                total += 1
                refusal_count += 1
            if total % 1024 == 0:
                peak = max(peak, _sqlite_bytes(connection))
        connection.execute("COMMIT")
    except sqlite3.IntegrityError as exc:
        connection.execute("ROLLBACK")
        raise ProductionEvidenceComposerError(
            "physical terminal security/session repeats"
        ) from exc
    except Exception:
        connection.execute("ROLLBACK")
        raise
    if (
        total != archive.terminal_count
        or accepted_count != archive.accepted_count
        or refusal_count != archive.refusal_count
    ):
        raise ProductionEvidenceComposerError("physical terminal census changed")
    return (total, accepted_count, refusal_count), max(peak, _sqlite_bytes(connection))


def _one_sidecar(
    connection: sqlite3.Connection, locator_sha256: str
) -> tuple[dict[str, Any] | None, str]:
    records = connection.execute(
        "SELECT record FROM sidecars WHERE locator_sha256=? ORDER BY record",
        (locator_sha256,),
    ).fetchall()
    if not records:
        return None, "missing"
    if len(records) != 1:
        return None, "ambiguous"
    return _validate_sidecar_record(
        _canonical_object(bytes(records[0][0]), "spooled analyst-event sidecar")
    ), "accepted"


def _one_terminal(
    connection: sqlite3.Connection, session: str, security_id: str
) -> tuple[str | None, dict[str, Any] | None]:
    records = connection.execute(
        "SELECT disposition, record FROM terminals "
        "WHERE decision_session=? AND security_id=?",
        (session, security_id),
    ).fetchall()
    if not records:
        return None, None
    if len(records) != 1:
        raise ProductionEvidenceComposerError("spooled physical terminal repeats")
    return records[0][0], _canonical_object(
        bytes(records[0][1]), "spooled physical terminal"
    )


def _rating_object(source: AcceptedRiskSourceRow) -> dict[str, Any] | None:
    try:
        raw = strict_json_loads(
            decode_utf8(source.raw_row_bytes, "production rating row"),
            "production rating row",
        )
    except CanonicalEvidenceError:
        return None
    return raw if type(raw) is dict else None


def _firm_component(
    *,
    source: AcceptedRiskSourceRow,
    raw: dict[str, Any] | None,
    ontology: ReviewedFirmRatingOntology,
    availability: ReviewedFirmOntologyAvailability,
) -> tuple[FirmOntologyEvidence | None, str]:
    if raw is None or source.event_date is None or source.provider_event_id is None:
        return None, "missing"
    provider_firm_id = raw.get("benzinga_firm_id")
    firm_name = raw.get("firm")
    current_label = raw.get("rating")
    previous_label = raw.get("previous_rating")
    if any(type(item) is not str or not item for item in (
        provider_firm_id, firm_name, current_label, previous_label
    )):
        return None, "missing"
    when = parse_date(source.event_date, "rating event date")
    active = tuple(
        item for item in ontology.entries
        if item.provider_firm_id == provider_firm_id
        and parse_date(item.valid_from, "firm valid_from") <= when
        and (item.valid_to is None or when < parse_date(item.valid_to, "firm valid_to"))
    )
    current = tuple(item for item in active if item.raw_label == current_label)
    previous = tuple(item for item in active if item.raw_label == previous_label)
    if len(current) != 1 or len(previous) != 1:
        return None, "unreviewed_or_unavailable"
    current_entry, previous_entry = current[0], previous[0]
    scale_identity = lambda item: (
        item.provider_firm_id, item.firm_name, item.valid_from, item.valid_to,
        item.scale_size, item.scope,
    )
    if (
        scale_identity(current_entry) != scale_identity(previous_entry)
        or current_entry.firm_name != firm_name
        or provider_firm_id != source.firm_label
    ):
        return None, "ambiguous"
    by_hash = {item.ontology_entry_sha256: item for item in availability.entries}
    current_availability = by_hash.get(_entry_sha(current_entry))
    previous_availability = by_hash.get(_entry_sha(previous_entry))
    if current_availability is None or previous_availability is None:
        return None, "unreviewed_or_unavailable"
    closure_values = {
        current_availability.valid_to_available_at,
        previous_availability.valid_to_available_at,
    }
    if len(closure_values) != 1:
        return None, "ambiguous"
    available_at = max(
        (current_availability.available_at, previous_availability.available_at),
        key=lambda value: parse_utc_timestamp(value, "firm availability"),
    )
    evidence_hash = sha256_bytes(canonical_json_bytes({
        "ontology_id": ontology.ontology_id,
        "current": current_entry.to_record(),
        "previous": previous_entry.to_record(),
        "current_availability": current_availability.to_record(),
        "previous_availability": previous_availability.to_record(),
    }))
    return FirmOntologyEvidence(
        provider_event_id=source.provider_event_id,
        provider_firm_id=provider_firm_id,
        raw_firm_name=firm_name,
        raw_current_label=current_label,
        raw_previous_label=previous_label,
        institution_id=provider_firm_id,
        ontology_id=ontology.ontology_id,
        ontology_sha256=ontology.payload_sha256,
        ontology_entry_sha256=evidence_hash,
        valid_from=current_entry.valid_from,
        valid_to=current_entry.valid_to,
        valid_to_available_at=current_availability.valid_to_available_at,
        available_at=available_at,
        current_score=current_entry.normalized_score,
        previous_score=previous_entry.normalized_score,
        candidate_count=1,
        ontology_reviewed=True,
        labels_reviewed=True,
    ), "accepted"


def _owner_waived_firm_component(
    *,
    source: AcceptedRiskSourceRow,
    raw: dict[str, Any] | None,
    admission: OwnerWaivedAcceptedRiskFirmAdmission,
) -> tuple[FirmOntologyEvidence | None, str]:
    """Resolve only exact accepted defaults under the section-72 waiver."""

    admission = require_section72_owner_waived_firm_admission(admission)
    if raw is None or source.event_date is None or source.provider_event_id is None:
        return None, "missing"
    provider_firm_id = raw.get("benzinga_firm_id")
    firm_name = raw.get("firm")
    current_label = raw.get("rating")
    previous_label = raw.get("previous_rating")
    if any(type(item) is not str or not item for item in (
        provider_firm_id, firm_name, current_label, previous_label
    )):
        return None, "missing"
    if provider_firm_id in admission.refused_provider_firm_ids:
        return None, "upstream_named_refusal"
    when = parse_date(source.event_date, "rating event date")
    active = tuple(
        item for item in admission.mappings
        if item.provider_firm_id == provider_firm_id
        and parse_date(item.valid_from, "owner-waived firm valid_from") <= when
        and (
            item.valid_to is None
            or when < parse_date(item.valid_to, "owner-waived firm valid_to")
        )
    )
    current = tuple(item for item in active if item.raw_label == current_label)
    previous = tuple(item for item in active if item.raw_label == previous_label)
    if len(current) != 1 or len(previous) != 1:
        return None, "unreviewed_or_unavailable"
    current_entry, previous_entry = current[0], previous[0]
    scale_identity = lambda item: (
        item.provider_firm_id,
        item.firm_name,
        item.valid_from,
        item.valid_to,
        item.scale_size,
        item.scope,
    )
    if (
        scale_identity(current_entry) != scale_identity(previous_entry)
        or current_entry.firm_name != firm_name
        or provider_firm_id != source.firm_label
    ):
        return None, "ambiguous"
    def canonical_proxy(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ProductionEvidenceComposerError(
                "owner-waived firm proxy timestamp changed"
            ) from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ProductionEvidenceComposerError(
                "owner-waived firm proxy timestamp changed"
            )
        return parsed.astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )

    available_at = max(
        (canonical_proxy(current_entry.proxy_open_at),
         canonical_proxy(previous_entry.proxy_open_at)),
        key=lambda value: parse_utc_timestamp(
            value, "owner-waived firm proxy availability"
        ),
    )
    evidence_hash = sha256_bytes(canonical_json_bytes({
        "admission_id": admission.admission_id,
        "admission_sha256": admission.admission_sha256,
        "owner_decision_id": admission.owner_decision_id,
        "owner_decision_sha256": admission.owner_decision_sha256,
        "refusal_ledger_id": admission.refusal_ledger_id,
        "refusal_ledger_sha256": admission.refusal_ledger_sha256,
        "current": current_entry.to_record(),
        "previous": previous_entry.to_record(),
        "availability_semantics": (
            "conservative_proxy_not_true_historical_availability"
        ),
        "independently_reviewed": False,
    }))
    return Section72OwnerWaivedFirmOntologyEvidence(
        provider_event_id=source.provider_event_id,
        provider_firm_id=provider_firm_id,
        raw_firm_name=firm_name,
        raw_current_label=current_label,
        raw_previous_label=previous_label,
        institution_id=provider_firm_id,
        ontology_id=admission.admission_id,
        ontology_sha256=admission.admission_sha256,
        ontology_entry_sha256=evidence_hash,
        valid_from=current_entry.valid_from,
        valid_to=current_entry.valid_to,
        valid_to_available_at=None,
        available_at=available_at,
        current_score=current_entry.normalized_score,
        previous_score=previous_entry.normalized_score,
        candidate_count=1,
        ontology_reviewed=False,
        labels_reviewed=False,
        admission_mode=SECTION72_OWNER_WAIVED_FIRM_ADMISSION_MODE,
        owner_waiver_scope=SECTION72_OWNER_WAIVER_SCOPE,
        independently_reviewed=False,
        historical_availability_claimed=False,
        deterministic_default=True,
        named_refusal=False,
    ), "accepted"


def _max_timestamp(*values: str) -> str:
    return max(values, key=lambda item: parse_utc_timestamp(item, "evidence availability"))


def _common_event_id(provider_event_id: str) -> str:
    candidate = "benzinga-event-" + provider_event_id
    try:
        return require_identifier(candidate, "common_event_id")
    except CanonicalEvidenceError:
        digest = sha256_bytes(canonical_json_bytes({
            "kind": "benzinga-event", "value": provider_event_id,
        }))
        return "benzinga-event-" + digest[:24]


def _common_component(
    *,
    source: AcceptedRiskSourceRow,
    sidecar: dict[str, Any] | None,
    truth_sources: Mapping[str, tuple[str, str]],
) -> tuple[CommonEventIdentityEvidence | None, str]:
    if (
        source.provider_event_id is None
        or source.event_date is None
        or source.raw_event_time is None
    ):
        return None, "missing"
    # Analyst-rating ``time`` is a documented UTC event clock.  The accepted-risk
    # eligibility timestamp is the conservative *decision-session* boundary and
    # is therefore exactly equal to that session's cutoff; using it as evidence
    # availability would mechanically make every otherwise valid identity late.
    # Keep the two concepts separate and derive identity availability only from
    # the physically captured provider event date/time.
    event_available_at = (
        f"{source.event_date}T{source.raw_event_time}.000000Z"
    )
    parse_utc_timestamp(event_available_at, "common-event source clock")
    common_event_id = _common_event_id(source.provider_event_id)
    if sidecar is not None and (
        sidecar["provider_event_id"] != source.provider_event_id
        or sidecar["common_event_id"] != common_event_id
    ):
        return None, "ambiguous"
    common_source = truth_sources["common_event"]
    evidence_hash = sha256_bytes(canonical_json_bytes({
        "schema": "arv2-benzinga-common-event-identity-evidence-v1",
        "provider_event_id": source.provider_event_id,
        "common_event_id": common_event_id,
        "raw_row_sha256": source.locator.raw_row_sha256,
        "sidecar_binding_sha256": (
            None if sidecar is None else sidecar["binding_sha256"]
        ),
    }))
    return CommonEventIdentityEvidence(
        provider_event_id=source.provider_event_id,
        common_event_id=common_event_id,
        source_id=common_source[0],
        source_sha256=common_source[1],
        evidence_sha256=evidence_hash,
        available_at=event_available_at,
        candidate_count=1,
    ), "accepted"


def _physical_components(
    *,
    source: AcceptedRiskSourceRow,
    sidecar: dict[str, Any],
    terminal: dict[str, Any],
    truth_sources: Mapping[str, tuple[str, str]],
) -> tuple[
    SecurityIdentityEvidence,
    SectorClassificationEvidence,
    PreopenControlEvidence,
    DataQualityEvidence,
]:
    if source.event_date is None or source.provider_event_id is None:
        raise ProductionEvidenceComposerError("accepted sidecar targets invalid source row")
    expected_locator = sha256_bytes(canonical_json_bytes(source.locator.to_record()))
    current_session = source.current_view.eligible_session
    if current_session is None:
        raise ProductionEvidenceComposerError("accepted rating has no current session")
    identity_fields = (
        ("security_id", "physical_security_id"),
        ("issuer_id", "issuer_id"),
        ("share_class_id", "share_class_id"),
        ("listing_id", "listing_id"),
        ("historical_ticker", "historical_ticker"),
    )
    if (
        sidecar["locator_sha256"] != expected_locator
        or sidecar["raw_row_sha256"] != source.locator.raw_row_sha256
        or sidecar["provider_event_id"] != source.provider_event_id
        or sidecar["current_view_disposition"] != source.current_view.disposition.value
        or sidecar["censored_view_disposition"] != source.censored_view.disposition.value
        or sidecar["decision_session"] != current_session
        or sidecar["available_at"] != source.current_view.eligible_at
        or sidecar["rating_admitted"] is not True
        or any(terminal[left] != sidecar[right] for left, right in identity_fields)
        or terminal["q_data"] != sidecar["q_data"]
        or terminal["q_data_evidence_sha256"] != sidecar["q_data_evidence_sha256"]
        or not (
            sidecar["mapping_first_session"]
            <= source.event_date
            <= sidecar["mapping_last_session"]
        )
    ):
        raise ProductionEvidenceComposerError(
            "accepted sidecar and physical terminal are not the same-key evidence"
        )
    security_source = truth_sources["security_master"]
    mapping_available = _max_timestamp(
        sidecar["mapping_available_at"], terminal["identity_available_at"]
    )
    security = SecurityIdentityEvidence(
        provider_event_id=source.provider_event_id,
        source_current_restated_ticker=source.current_restated_security_label,
        historical_ticker=terminal["historical_ticker"],
        issuer_id=terminal["issuer_id"],
        security_id=terminal["security_id"],
        share_class_id=terminal["share_class_id"],
        listing_id=terminal["listing_id"],
        security_master_id=security_source[0],
        security_master_sha256=security_source[1],
        mapping_version_id="arv2-security-map-" + sidecar["binding_sha256"][:24],
        mapping_evidence_sha256=sidecar["binding_sha256"],
        valid_from=sidecar["mapping_first_session"],
        valid_to=None,
        valid_to_available_at=None,
        available_at=mapping_available,
        candidate_count=1,
        point_in_time=True,
        current_ticker_only=False,
    )
    sector_source = truth_sources["sector_classification"]
    next_day = (date.fromisoformat(current_session) + timedelta(days=1)).isoformat()
    sector = SectorClassificationEvidence(
        security_id=terminal["security_id"],
        sector_id=terminal["sector_id"],
        source_id=sector_source[0],
        source_sha256=sector_source[1],
        evidence_sha256=terminal["classification_evidence_sha256"],
        valid_from=current_session,
        valid_to=next_day,
        valid_to_available_at=terminal["classification_available_at"],
        available_at=terminal["classification_available_at"],
        candidate_count=1,
        point_in_time=True,
    )
    control_source = truth_sources["preopen_control"]
    control = PreopenControlEvidence(
        security_id=terminal["security_id"],
        industry_id=terminal["industry_id"],
        decision_session=current_session,
        source_id=control_source[0],
        source_sha256=control_source[1],
        evidence_sha256=terminal["control_evidence_sha256"],
        available_at=terminal["control_available_at"],
        control_vector_sha256=terminal["control_vector_sha256"],
        complete=True,
        point_in_time=True,
        contains_outcome_or_price=False,
    )
    quality_source = truth_sources["data_quality"]
    quality = DataQualityEvidence(
        security_id=terminal["security_id"],
        measured_session=current_session,
        source_id=quality_source[0],
        source_sha256=quality_source[1],
        evidence_sha256=terminal["q_data_evidence_sha256"],
        available_at=terminal["q_data_available_at"],
        measurement_method_id=QUALITY_METHOD_ID,
        q_data=Decimal(terminal["q_data"]),
        point_in_time=True,
    )
    return security, sector, control, quality


def build_physical_production_evidence_candidate(
    *,
    pair: AcceptedRiskInputPair,
    historical_bridge: historical_module.ReviewedHistoricalUniverseToPreopenBridge,
    firm_ontology: ReviewedFirmRatingOntology,
    firm_availability: ReviewedFirmOntologyAvailability,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    terminal_archive: PhysicalPreopenTerminalArchive
    | PhysicalProductionEvidenceTerminalArchive,
) -> ProductionEvidenceComposerCandidate:
    """Compose a non-authorizing, externally reviewable C2 package candidate."""

    truth_sources, source_bindings = _reauthenticate_parents(
        pair=pair,
        bridge=historical_bridge,
        ontology=firm_ontology,
        availability=firm_availability,
        preopen=preopen_acquisition_receipt,
        archive=terminal_archive,
    )
    candidates = tuple(
        item for item in pair.rows
        if item.locator.source_role is MassiveSourceRole.ANALYST_RATINGS
        and item.current_view.included
    )
    if len(candidates) > MAX_COMPOSER_RATING_ROW_COUNT:
        raise ProductionEvidenceComposerCapacityRefusal(
            "candidate rating-row census exceeded fixed composition capacity"
        )
    evidence_rows: list[ProductionRowEvidence] = []
    composition: list[ProductionEvidenceCompositionTerminal] = []
    with tempfile.TemporaryDirectory(
        prefix="arv2-production-evidence-"
    ) as directory_text:
        directory = Path(directory_text)
        os.chmod(directory, 0o700)
        connection, _database_path = _open_spool(directory)
        try:
            sidecar_count, sidecar_peak = _spool_sidecars(
                connection, historical_bridge
            )
            physical_counts, terminal_peak = _spool_terminals(
                connection, terminal_archive
            )
            peak = max(sidecar_peak, terminal_peak, _sqlite_bytes(connection))
            for source in candidates:
                locator_sha = sha256_bytes(
                    canonical_json_bytes(source.locator.to_record())
                )
                sidecar, sidecar_status = _one_sidecar(connection, locator_sha)
                dispositions = {
                    "security": "missing",
                    "firm": "missing",
                    "common_event": "missing",
                    "sector": "missing",
                    "control": "missing",
                    "q_data": "missing",
                }
                upstream_reason: str | None = None
                if sidecar_status == "ambiguous":
                    dispositions["security"] = "ambiguous"
                    upstream_reason = "analyst_event_binding_ambiguous"
                elif sidecar is None:
                    upstream_reason = "analyst_event_binding_missing"
                elif sidecar["binding_disposition"] == "named_refusal":
                    dispositions["security"] = "upstream_named_refusal"
                    dispositions["sector"] = "upstream_named_refusal"
                    dispositions["control"] = "upstream_named_refusal"
                    dispositions["q_data"] = "upstream_named_refusal"
                    upstream_reason = sidecar["binding_reason"]

                raw = _rating_object(source)
                firm, firm_status = _firm_component(
                    source=source,
                    raw=raw,
                    ontology=firm_ontology,
                    availability=firm_availability,
                )
                dispositions["firm"] = firm_status
                common, common_status = _common_component(
                    source=source,
                    sidecar=sidecar,
                    truth_sources=truth_sources,
                )
                dispositions["common_event"] = common_status

                security = sector = control = quality = None
                if sidecar is not None and sidecar["binding_disposition"] == "accepted":
                    terminal_disposition, terminal = _one_terminal(
                        connection,
                        sidecar["decision_session"],
                        sidecar["physical_security_id"],
                    )
                    if terminal_disposition is None:
                        for name in ("security", "sector", "control", "q_data"):
                            dispositions[name] = "physical_terminal_missing"
                        upstream_reason = "same_key_physical_terminal_missing"
                    elif terminal_disposition == "named_refusal":
                        for name in ("security", "sector", "control", "q_data"):
                            dispositions[name] = "physical_terminal_refused"
                        upstream_reason = str(terminal.get("reason"))
                    elif terminal_disposition == "accepted" and terminal is not None:
                        try:
                            security, sector, control, quality = _physical_components(
                                source=source,
                                sidecar=sidecar,
                                terminal=terminal,
                                truth_sources=truth_sources,
                            )
                        except (CanonicalEvidenceError, KeyError, TypeError, ValueError) as exc:
                            raise ProductionEvidenceComposerError(
                                "accepted physical evidence parents contradict each other"
                            ) from exc
                        for name in ("security", "sector", "control", "q_data"):
                            dispositions[name] = "accepted"
                    else:
                        raise ProductionEvidenceComposerError(
                            "spooled physical terminal disposition changed"
                        )
                evidence_rows.append(ProductionRowEvidence(
                    locator=source.locator,
                    security=security,
                    firm=firm,
                    common_event=common,
                    sector=sector,
                    control=control,
                    q_data=quality,
                ))
                composition.append(_composition_terminal(
                    locator_sha256=locator_sha,
                    dispositions=dispositions,
                    upstream_reason=upstream_reason,
                ))
        finally:
            connection.close()

    if len(evidence_rows) != len(candidates) or len(composition) != len(candidates):
        raise ProductionEvidenceComposerError(
            "production-evidence candidate row census is not exhaustive"
        )
    authority = build_production_evidence_authority(
        pair,
        source_bindings=source_bindings,
        row_evidence=tuple(evidence_rows),
    )
    package_bytes = render_production_evidence_package_bytes(authority)
    if len(package_bytes) > MAX_PACKAGE_BYTES:
        raise ProductionEvidenceComposerCapacityRefusal(
            "production-evidence package exceeded its fixed physical byte ceiling"
        )
    pin_bytes = render_production_evidence_external_review_pin_candidate(
        authority=authority,
        preopen_acquisition_receipt=preopen_acquisition_receipt,
        package_bytes=package_bytes,
    )
    composition_tuple = tuple(composition)
    composition_projection = sha256_bytes(
        canonical_json_bytes([item.to_record() for item in composition_tuple])
    )
    value = object.__new__(ProductionEvidenceComposerCandidate)
    values: dict[str, object] = {
        "schema": COMPOSER_SCHEMA,
        "candidate_id": "",
        "candidate_sha256": "",
        "pair": pair,
        "pair_id": pair.pair_id,
        "pair_sha256": pair.pair_sha256,
        "historical_bridge": historical_bridge,
        "historical_bridge_id": historical_bridge.bridge_id,
        "historical_bridge_sha256": historical_bridge.bridge_sha256,
        "firm_ontology": firm_ontology,
        "firm_ontology_id": firm_ontology.ontology_id,
        "firm_ontology_sha256": firm_ontology.payload_sha256,
        "firm_availability": firm_availability,
        "firm_availability_id": firm_availability.artifact_id,
        "firm_availability_sha256": firm_availability.artifact_sha256,
        "preopen_acquisition_receipt": preopen_acquisition_receipt,
        "preopen_acquisition_id": preopen_acquisition_receipt.artifact_id,
        "preopen_acquisition_sha256": preopen_acquisition_receipt.artifact_sha256,
        "terminal_archive": terminal_archive,
        "terminal_archive_id": terminal_archive.archive_id,
        "terminal_archive_sha256": terminal_archive.archive_sha256,
        "authority": authority,
        "authority_id": authority.authority_id,
        "authority_sha256": authority.authority_sha256,
        "evidence_package_bytes": package_bytes,
        "evidence_package_sha256": sha256_bytes(package_bytes),
        "external_review_pin_candidate_bytes": pin_bytes,
        "external_review_pin_candidate_sha256": sha256_bytes(pin_bytes),
        "composition_terminals": composition_tuple,
        "composition_terminal_projection_sha256": composition_projection,
        "candidate_rating_row_count": len(candidates),
        "sidecar_row_count": sidecar_count,
        "physical_terminal_count": physical_counts[0],
        "physical_accepted_count": physical_counts[1],
        "physical_refusal_count": physical_counts[2],
        "sqlite_peak_page_bytes": peak,
        "package_byte_count": len(package_bytes),
        "complete_candidate_rating_census": True,
        "physical_sources_reauthenticated": True,
        "independent_package_review_required": True,
        "production_evidence_receipt_available": False,
        "provider_access": False,
        "credential_access": False,
        "quantconnect_access": False,
        "outcome_access": False,
        "result_access": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    if set(values) != {field.name for field in dataclasses.fields(value)}:
        raise ProductionEvidenceComposerError("composer candidate field inventory changed")
    for name, item in values.items():
        object.__setattr__(value, name, item)
    digest = sha256_bytes(canonical_json_bytes(_candidate_semantic(value)))
    object.__setattr__(value, "candidate_sha256", digest)
    object.__setattr__(value, "candidate_id", f"arv2-production-evidence-composer-{digest[:24]}")
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget_composer(key, ref))
    with _COMPOSER_LOCK:
        _COMPOSER_AUTHORITIES[identity] = (reference, _candidate_fingerprint(value))
    return require_physical_production_evidence_candidate(value)


def require_physical_production_evidence_candidate(
    value: ProductionEvidenceComposerCandidate,
) -> ProductionEvidenceComposerCandidate:
    if type(value) is not ProductionEvidenceComposerCandidate:
        raise ProductionEvidenceComposerError("composer candidate changed type")
    with _COMPOSER_LOCK:
        registered = _COMPOSER_AUTHORITIES.get(id(value))
    if (
        registered is None
        or registered[0]() is not value
        or registered[1] != _candidate_fingerprint(value)
    ):
        raise ProductionEvidenceComposerError("composer candidate lost builder authority")
    _reauthenticate_parents(
        pair=value.pair,
        bridge=value.historical_bridge,
        ontology=value.firm_ontology,
        availability=value.firm_availability,
        preopen=value.preopen_acquisition_receipt,
        archive=value.terminal_archive,
    )
    require_production_evidence_authority(value.authority)
    flags = (
        (value.complete_candidate_rating_census, True),
        (value.physical_sources_reauthenticated, True),
        (value.independent_package_review_required, True),
        (value.production_evidence_receipt_available, False),
        (value.provider_access, False),
        (value.credential_access, False),
        (value.quantconnect_access, False),
        (value.outcome_access, False),
        (value.result_access, False),
        (value.deployment, False),
        (value.orders, False),
        (value.trading, False),
    )
    semantic = _candidate_semantic(value)
    digest = sha256_bytes(canonical_json_bytes(semantic))
    if (
        any(type(flag) is not bool or flag is not expected for flag, expected in flags)
        or value.schema != COMPOSER_SCHEMA
        or value.candidate_sha256 != digest
        or value.candidate_id != f"arv2-production-evidence-composer-{digest[:24]}"
        or value.authority_id != value.authority.authority_id
        or value.authority_sha256 != value.authority.authority_sha256
        or value.evidence_package_bytes
        != render_production_evidence_package_bytes(value.authority)
        or value.evidence_package_sha256 != sha256_bytes(value.evidence_package_bytes)
        or value.package_byte_count != len(value.evidence_package_bytes)
        or value.package_byte_count > MAX_PACKAGE_BYTES
        or value.external_review_pin_candidate_bytes
        != render_production_evidence_external_review_pin_candidate(
            authority=value.authority,
            preopen_acquisition_receipt=value.preopen_acquisition_receipt,
            package_bytes=value.evidence_package_bytes,
        )
        or value.external_review_pin_candidate_sha256
        != sha256_bytes(value.external_review_pin_candidate_bytes)
        or value.composition_terminal_projection_sha256
        != sha256_bytes(canonical_json_bytes(
            [item.to_record() for item in value.composition_terminals]
        ))
        or value.candidate_rating_row_count != len(value.authority.row_evidence)
        or value.sqlite_peak_page_bytes > MAX_COMPOSER_SPOOL_BYTES
    ):
        raise ProductionEvidenceComposerError("composer candidate changed after construction")
    return value


__all__ = (
    "COMPOSER_SCHEMA",
    "FIRM_AVAILABILITY_REVIEW_SCHEMA",
    "FIRM_AVAILABILITY_SCHEMA",
    "FirmOntologyAvailabilityEntry",
    "OwnerWaivedAcceptedRiskFirmAdmission",
    "OwnerWaivedFirmMapping",
    "ProductionEvidenceComposerCandidate",
    "ProductionEvidenceComposerCapacityRefusal",
    "ProductionEvidenceComposerError",
    "ProductionEvidenceCompositionTerminal",
    "ReviewedFirmOntologyAvailability",
    "SECTION72_FIRM_ADMISSION_SCHEMA",
    "SECTION72_OWNER_WAIVER_SCOPE",
    "build_section72_owner_waived_firm_admission",
    "build_physical_production_evidence_candidate",
    "load_reviewed_firm_ontology_availability",
    "iter_section72_owner_waived_firm_mappings",
    "require_physical_production_evidence_candidate",
    "require_reviewed_firm_ontology_availability",
    "require_section72_owner_waived_firm_admission",
)
