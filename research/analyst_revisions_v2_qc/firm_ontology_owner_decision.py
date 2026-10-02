"""Mixed owner-policy decisions for the authenticated 74-firm proposal.

The owner has authorized one deterministic rule: accept the proposal defaults
only for firms that the proposal itself marks clean, and retain every other
firm as a named refusal.  This module records that rule without converting a
proposal into reviewed firm truth.  In particular, its NYSE-open timestamps
are explicitly labelled conservative proxies; they are not historical
``available_at`` evidence and are not compatible with the production
availability loader or registry.
"""
from __future__ import annotations

import dataclasses
import enum
import os
import threading
import weakref
from typing import Any, Iterator, Mapping, NoReturn

from research.analyst_revisions_v2 import availability as _availability
from research.analyst_revisions_v2 import canonical as _canonical
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    require_identifier,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2_qc import (
    firm_ontology_proposal_generator as _proposal,
)
from research.analyst_revisions_v2_qc import (
    physical_firm_ontology_review_packet as _packet,
)
from research.analyst_revisions_v2_qc.firm_ontology_proposal_generator import (
    FirmOntologyProposalArtifact,
)
from research.analyst_revisions_v2_qc.physical_firm_ontology_review_packet import (
    PhysicalFirmOntologyReviewPacket,
)


OWNER_DECISION_SCHEMA = "arv2-firm-ontology-mixed-owner-decision-v1"
REFUSAL_LEDGER_SCHEMA = "arv2-firm-ontology-named-refusal-ledger-v1"
REFUSAL_ENTRY_SCHEMA = "arv2-firm-ontology-named-refusal-v1"
AVAILABILITY_PROXY_SCHEMA = "arv2-firm-ontology-conservative-availability-proxy-v1"
EXPECTED_FIRM_COUNT = 74
MAX_DECISION_BYTES = 32 * 1024 * 1024
MAX_REFUSAL_LEDGER_BYTES = 16 * 1024 * 1024
AVAILABILITY_PROXY_KIND = (
    "next_XNYS_open_strictly_after_authenticated_mapping_first_event_date_"
    "not_true_historical_availability"
)


class FirmOntologyOwnerDecisionStatus(str, enum.Enum):
    """The only two owner-authorized dispositions."""

    ACCEPTED_DETERMINISTIC_DEFAULT = "accepted_deterministic_default"
    NAMED_REFUSAL = "named_refusal"


_STATUS_VALUES = tuple(item.value for item in FirmOntologyOwnerDecisionStatus)
_CAPABILITY_NAMES = (
    "owner_reviewed_complete",
    "independently_reviewed",
    "availability_authority_created",
    "registry_authority_created",
    "production_authority",
    "provider_access",
    "quantconnect_access",
    "outcome_access",
    "result_access",
    "deployment",
    "orders",
    "trading",
)
_DECISION_KEYS = frozenset(
    {
        "schema",
        "decision_id",
        "decision_sha256",
        "source",
        "policy",
        "census",
        "refusal_ledger",
        "firms",
        "capabilities",
    }
)
_LEDGER_KEYS = frozenset(
    {
        "schema",
        "ledger_id",
        "ledger_sha256",
        "source",
        "expected_firm_count",
        "refused_firm_count",
        "entries",
    }
)
_DECISION_FIRM_KEYS = frozenset(
    {
        "ranking_ordinal",
        "provider_firm_id",
        "proposal_firm_row_sha256",
        "firm_evidence_row_sha256",
        "decision_status",
        "accepted_proposal_defaults",
        "accepted_proposal_defaults_sha256",
        "availability_proxies",
        "refusal_id",
        "refusal_sha256",
    }
)
_REFUSAL_KEYS = frozenset(
    {
        "schema",
        "refusal_id",
        "refusal_sha256",
        "ranking_ordinal",
        "provider_firm_id",
        "proposal_firm_row_sha256",
        "firm_evidence_row_sha256",
        "decision_status",
        "unresolved_labels",
        "unresolved_labels_sha256",
        "exception_reasons",
        "exception_reasons_sha256",
    }
)

_PINNED_PROPOSAL_TYPE = FirmOntologyProposalArtifact
_PINNED_PROPOSAL_REQUIRE = _proposal.require_firm_ontology_proposal
_PINNED_PROPOSAL_ITERATOR = _proposal.iter_firm_ontology_proposal_firms
_PINNED_PACKET_TYPE = PhysicalFirmOntologyReviewPacket
_PINNED_PACKET_REQUIRE = _packet.require_physical_firm_ontology_review_packet
_PINNED_AVAILABILITY_RESOLVER = (
    _availability.resolve_delayed_date_only_session_open
)
_PINNED_CANONICAL = canonical_json_bytes
_PINNED_SHA256 = sha256_bytes
_PINNED_DECODE = decode_utf8
_PINNED_STRICT_LOADS = strict_json_loads
_PINNED_REQUIRE_IDENTIFIER = require_identifier
_PINNED_REQUIRE_SHA256 = require_sha256
_PINNED_STATUS_TYPE = FirmOntologyOwnerDecisionStatus
_PINNED_STATUS_VALUES = tuple(_STATUS_VALUES)
_BUILD_HELPER_NAMES = (
    "_policy_record",
    "_canonical_copy",
    "_record_sha256",
    "_address_record",
    "_address_is_current",
    "_availability_proxy",
    "_named_refusal",
    "_compose_documents",
    "_require_documents",
)


class FirmOntologyOwnerDecisionError(ValueError):
    """A mixed decision or one of its authenticated parents was refused."""


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class FirmOntologyOwnerDecisionArtifact:
    """Current-process authority over two non-production decision documents."""

    schema: str
    decision_id: str
    decision_sha256: str
    decision_payload_sha256: str
    decision_bytes: bytes = dataclasses.field(repr=False)
    refusal_ledger_id: str
    refusal_ledger_sha256: str
    refusal_ledger_payload_sha256: str
    refusal_ledger_bytes: bytes = dataclasses.field(repr=False)
    packet_id: str
    packet_sha256: str
    proposal_id: str
    proposal_sha256: str
    proposal_payload_sha256: str
    firm_count: int
    accepted_firm_count: int
    refused_firm_count: int
    availability_proxy_count: int
    owner_reviewed_complete: bool
    independently_reviewed: bool
    availability_authority_created: bool
    registry_authority_created: bool
    production_authority: bool
    provider_access: bool
    quantconnect_access: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool


_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[FirmOntologyOwnerDecisionArtifact],
        tuple[object, ...],
        weakref.ReferenceType[FirmOntologyProposalArtifact],
        weakref.ReferenceType[PhysicalFirmOntologyReviewPacket],
        int,
    ],
] = {}
_AUTHORITY_LOCK = threading.RLock()
_AUTHORITY_PID = os.getpid()


def _reset_authorities_after_fork() -> None:
    global _AUTHORITIES, _AUTHORITY_LOCK, _AUTHORITY_PID
    _AUTHORITIES = {}
    _AUTHORITY_LOCK = threading.RLock()
    _AUTHORITY_PID = os.getpid()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_authorities_after_fork)


def _forget(identity: int, reference: object) -> None:
    with _AUTHORITY_LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _AUTHORITIES.pop(identity, None)


def _fingerprint(
    value: FirmOntologyOwnerDecisionArtifact,
) -> tuple[object, ...]:
    return tuple(getattr(value, field.name) for field in dataclasses.fields(value))


def _refuse(message: str) -> NoReturn:
    raise FirmOntologyOwnerDecisionError(message)


def _require_dependencies() -> None:
    if (
        _proposal.FirmOntologyProposalArtifact is not _PINNED_PROPOSAL_TYPE
        or _proposal.require_firm_ontology_proposal
        is not _PINNED_PROPOSAL_REQUIRE
        or _proposal.iter_firm_ontology_proposal_firms
        is not _PINNED_PROPOSAL_ITERATOR
        or _packet.PhysicalFirmOntologyReviewPacket is not _PINNED_PACKET_TYPE
        or _packet.require_physical_firm_ontology_review_packet
        is not _PINNED_PACKET_REQUIRE
        or _availability.resolve_delayed_date_only_session_open
        is not _PINNED_AVAILABILITY_RESOLVER
        or _canonical.canonical_json_bytes is not _PINNED_CANONICAL
        or _canonical.sha256_bytes is not _PINNED_SHA256
        or _canonical.decode_utf8 is not _PINNED_DECODE
        or _canonical.strict_json_loads is not _PINNED_STRICT_LOADS
        or _canonical.require_identifier is not _PINNED_REQUIRE_IDENTIFIER
        or _canonical.require_sha256 is not _PINNED_REQUIRE_SHA256
        or canonical_json_bytes is not _PINNED_CANONICAL
        or sha256_bytes is not _PINNED_SHA256
        or decode_utf8 is not _PINNED_DECODE
        or strict_json_loads is not _PINNED_STRICT_LOADS
        or require_identifier is not _PINNED_REQUIRE_IDENTIFIER
        or require_sha256 is not _PINNED_REQUIRE_SHA256
        or FirmOntologyOwnerDecisionStatus is not _PINNED_STATUS_TYPE
        or tuple(item.value for item in FirmOntologyOwnerDecisionStatus)
        != _PINNED_STATUS_VALUES
        or tuple(globals().get(name) for name in _BUILD_HELPER_NAMES)
        != _PINNED_BUILD_HELPERS
    ):
        _refuse("firm owner-decision dependency binding changed")


def _policy_record() -> dict[str, object]:
    return {
        "status_enum": list(_STATUS_VALUES),
        "clean_firm_rule": (
            "accept_only_authenticated_proposal_bulk_eligible_with_zero_"
            "unresolved_labels_and_zero_exception_reasons"
        ),
        "exception_rule": (
            "every_nonclean_firm_is_a_named_refusal_with_no_mappings"
        ),
        "accepted_mapping_source": (
            "authenticated_proposal_defaults_exact_copy_no_override"
        ),
        "availability_proxy_rule": AVAILABILITY_PROXY_KIND,
        "true_historical_availability_claimed": False,
        "independent_production_review_still_required": True,
    }


def _canonical_copy(value: object, name: str) -> Any:
    try:
        payload = _PINNED_CANONICAL(value)
        copied = _PINNED_STRICT_LOADS(
            _PINNED_DECODE(payload, name),
            name,
        )
    except (CanonicalEvidenceError, TypeError, ValueError, RecursionError) as exc:
        raise FirmOntologyOwnerDecisionError(
            f"{name} is not bounded canonical JSON"
        ) from exc
    return copied


def _record_sha256(value: object) -> str:
    return _PINNED_SHA256(_PINNED_CANONICAL(value))


def _address_record(
    raw: dict[str, object],
    *,
    identifier_field: str,
    digest_field: str,
    prefix: str,
) -> dict[str, object]:
    seed = dict(raw)
    seed[identifier_field] = None
    seed[digest_field] = None
    digest = _record_sha256(seed)
    raw[identifier_field] = f"{prefix}{digest[:24]}"
    raw[digest_field] = digest
    return raw


def _address_is_current(
    raw: Mapping[str, object],
    *,
    identifier_field: str,
    digest_field: str,
    prefix: str,
) -> bool:
    seed = dict(raw)
    identifier = seed.get(identifier_field)
    digest = seed.get(digest_field)
    seed[identifier_field] = None
    seed[digest_field] = None
    expected = _record_sha256(seed)
    return (
        type(identifier) is str
        and type(digest) is str
        and digest == expected
        and identifier == f"{prefix}{expected[:24]}"
    )


def _availability_proxy(
    *,
    firm: Mapping[str, object],
    mapping: Mapping[str, object],
    mapping_role: str,
    packet_id: str,
    packet_sha256: str,
) -> dict[str, object]:
    evidence = mapping.get("mapping_evidence")
    if type(evidence) is not dict:
        _refuse("accepted proposal mapping lacks exact evidence")
    try:
        evidence_id = _PINNED_REQUIRE_IDENTIFIER(
            evidence.get("evidence_id"), "proposal mapping evidence_id"
        )
        evidence_sha = _PINNED_REQUIRE_SHA256(
            evidence.get("evidence_sha256"),
            "proposal mapping evidence_sha256",
        )
        provider_firm_id = _PINNED_REQUIRE_IDENTIFIER(
            firm.get("provider_firm_id"), "proposal provider_firm_id"
        )
    except CanonicalEvidenceError as exc:
        raise FirmOntologyOwnerDecisionError(
            "accepted proposal mapping evidence identity is invalid"
        ) from exc
    evidence_seed = dict(evidence)
    evidence_seed["evidence_id"] = None
    evidence_seed["evidence_sha256"] = None
    if (
        evidence_sha != _record_sha256(evidence_seed)
        or evidence_id != f"arv2-firm-proposal-evidence-{evidence_sha[:24]}"
        or evidence.get("packet_id") != packet_id
        or evidence.get("packet_sha256") != packet_sha256
        or evidence.get("provider_firm_id") != provider_firm_id
        or evidence.get("firm_evidence_row_sha256")
        != firm.get("firm_evidence_row_sha256")
        or evidence.get("raw_label") != mapping.get("raw_label")
        or evidence.get("availability_time_proposed") is not None
        or evidence.get("owner_confirmation_required") is not True
        or mapping.get("owner_confirmation_required") is not True
        or mapping_role not in {"ordered_scale", "alias_mapping"}
    ):
        _refuse("accepted proposal mapping evidence lost its exact binding")
    first_event_date = evidence.get("first_event_date")
    try:
        session, market_open = _PINNED_AVAILABILITY_RESOLVER(
            public_date=first_event_date,
            session_lag=1,
        )
    except (_availability.AvailabilityError, TypeError, ValueError) as exc:
        raise FirmOntologyOwnerDecisionError(
            "conservative availability proxy cannot resolve its evidence date"
        ) from exc
    return {
        "schema": AVAILABILITY_PROXY_SCHEMA,
        "proxy_kind": AVAILABILITY_PROXY_KIND,
        "provider_firm_id": provider_firm_id,
        "mapping_role": mapping_role,
        "raw_label": mapping["raw_label"],
        "proposed_ordered_rank": mapping["proposed_ordered_rank"],
        "source_evidence_id": evidence_id,
        "source_evidence_sha256": evidence_sha,
        "authenticated_first_event_date": first_event_date,
        "proxy_session": session,
        "proxy_open_at": market_open.isoformat(),
        "historical_availability_claimed": False,
    }


def _named_refusal(firm: Mapping[str, object]) -> dict[str, object]:
    unresolved = _canonical_copy(
        firm.get("unresolved_labels"), "proposal unresolved labels"
    )
    reasons = _canonical_copy(
        firm.get("exception_reasons"), "proposal exception reasons"
    )
    if (
        type(unresolved) is not list
        or type(reasons) is not list
        or not reasons
        or any(type(reason) is not str or not reason for reason in reasons)
    ):
        _refuse("named refusal lacks exact unresolved labels or reasons")
    record: dict[str, object] = {
        "schema": REFUSAL_ENTRY_SCHEMA,
        "refusal_id": None,
        "refusal_sha256": None,
        "ranking_ordinal": firm.get("ranking_ordinal"),
        "provider_firm_id": firm.get("provider_firm_id"),
        "proposal_firm_row_sha256": _record_sha256(firm),
        "firm_evidence_row_sha256": firm.get("firm_evidence_row_sha256"),
        "decision_status": FirmOntologyOwnerDecisionStatus.NAMED_REFUSAL.value,
        "unresolved_labels": unresolved,
        "unresolved_labels_sha256": _record_sha256(unresolved),
        "exception_reasons": reasons,
        "exception_reasons_sha256": _record_sha256(reasons),
    }
    return _address_record(
        record,
        identifier_field="refusal_id",
        digest_field="refusal_sha256",
        prefix="arv2-firm-named-refusal-",
    )


def _compose_documents(
    *,
    proposal_firms: tuple[dict[str, object], ...],
    packet_id: str,
    packet_sha256: str,
    proposal_id: str,
    proposal_sha256: str,
    proposal_payload_sha256: str,
) -> tuple[dict[str, object], dict[str, object]]:
    if type(proposal_firms) is not tuple or len(proposal_firms) != EXPECTED_FIRM_COUNT:
        _refuse("mixed owner decision requires the exact 74-firm proposal census")
    source = {
        "packet_id": packet_id,
        "packet_sha256": packet_sha256,
        "proposal_id": proposal_id,
        "proposal_sha256": proposal_sha256,
        "proposal_payload_sha256": proposal_payload_sha256,
    }
    decision_firms: list[dict[str, object]] = []
    refusal_entries: list[dict[str, object]] = []
    seen: set[str] = set()
    proxy_count = 0
    for ordinal, firm in enumerate(proposal_firms, start=1):
        if type(firm) is not dict:
            _refuse("mixed owner decision proposal firm row changed type")
        firm_id = firm.get("provider_firm_id")
        if (
            type(firm_id) is not str
            or not firm_id
            or firm_id in seen
            or firm.get("ranking_ordinal") != ordinal
        ):
            _refuse("mixed owner decision firm identity is duplicated or out of order")
        seen.add(firm_id)
        eligible = firm.get("bulk_ratification_eligible")
        unresolved = firm.get("unresolved_labels")
        reasons = firm.get("exception_reasons")
        if (
            type(eligible) is not bool
            or type(unresolved) is not list
            or type(reasons) is not list
        ):
            _refuse("mixed owner decision proposal policy fields changed type")
        clean = eligible is True and not unresolved and not reasons
        exception = eligible is False and bool(reasons)
        if clean is exception or not (clean or exception):
            _refuse("mixed owner decision proposal policy partition is inconsistent")
        proposal_row_sha = _record_sha256(firm)
        if clean:
            defaults = _canonical_copy(
                firm.get("proposed_defaults"), "accepted proposal defaults"
            )
            if type(defaults) is not dict:
                _refuse("accepted proposal defaults changed type")
            primary = defaults.get("ordered_scale")
            aliases = defaults.get("alias_mappings")
            if type(primary) is not list or type(aliases) is not list or not primary:
                _refuse("accepted proposal defaults lack an explicit scale")
            proxies = [
                _availability_proxy(
                    firm=firm,
                    mapping=mapping,
                    mapping_role=role,
                    packet_id=packet_id,
                    packet_sha256=packet_sha256,
                )
                for role, mappings in (
                    ("ordered_scale", primary),
                    ("alias_mapping", aliases),
                )
                for mapping in mappings
                if type(mapping) is dict
            ]
            if len(proxies) != len(primary) + len(aliases):
                _refuse("accepted proposal mapping row changed type")
            proxy_count += len(proxies)
            decision_firms.append(
                {
                    "ranking_ordinal": ordinal,
                    "provider_firm_id": firm_id,
                    "proposal_firm_row_sha256": proposal_row_sha,
                    "firm_evidence_row_sha256": firm.get(
                        "firm_evidence_row_sha256"
                    ),
                    "decision_status": (
                        FirmOntologyOwnerDecisionStatus.ACCEPTED_DETERMINISTIC_DEFAULT.value
                    ),
                    "accepted_proposal_defaults": defaults,
                    "accepted_proposal_defaults_sha256": _record_sha256(defaults),
                    "availability_proxies": proxies,
                    "refusal_id": None,
                    "refusal_sha256": None,
                }
            )
        else:
            refusal = _named_refusal(firm)
            refusal_entries.append(refusal)
            decision_firms.append(
                {
                    "ranking_ordinal": ordinal,
                    "provider_firm_id": firm_id,
                    "proposal_firm_row_sha256": proposal_row_sha,
                    "firm_evidence_row_sha256": firm.get(
                        "firm_evidence_row_sha256"
                    ),
                    "decision_status": FirmOntologyOwnerDecisionStatus.NAMED_REFUSAL.value,
                    "accepted_proposal_defaults": None,
                    "accepted_proposal_defaults_sha256": None,
                    "availability_proxies": [],
                    "refusal_id": refusal["refusal_id"],
                    "refusal_sha256": refusal["refusal_sha256"],
                }
            )
    ledger: dict[str, object] = {
        "schema": REFUSAL_LEDGER_SCHEMA,
        "ledger_id": None,
        "ledger_sha256": None,
        "source": source,
        "expected_firm_count": EXPECTED_FIRM_COUNT,
        "refused_firm_count": len(refusal_entries),
        "entries": refusal_entries,
    }
    _address_record(
        ledger,
        identifier_field="ledger_id",
        digest_field="ledger_sha256",
        prefix="arv2-firm-refusal-ledger-",
    )
    accepted_count = EXPECTED_FIRM_COUNT - len(refusal_entries)
    decision: dict[str, object] = {
        "schema": OWNER_DECISION_SCHEMA,
        "decision_id": None,
        "decision_sha256": None,
        "source": source,
        "policy": _policy_record(),
        "census": {
            "expected_firm_count": EXPECTED_FIRM_COUNT,
            "decision_firm_count": len(decision_firms),
            "accepted_firm_count": accepted_count,
            "refused_firm_count": len(refusal_entries),
            "availability_proxy_count": proxy_count,
            "refusal_ledger_entry_count": len(refusal_entries),
        },
        "refusal_ledger": {
            "ledger_id": ledger["ledger_id"],
            "ledger_sha256": ledger["ledger_sha256"],
            "ledger_payload_sha256": _record_sha256(ledger),
        },
        "firms": decision_firms,
        "capabilities": {name: False for name in _CAPABILITY_NAMES},
    }
    _address_record(
        decision,
        identifier_field="decision_id",
        digest_field="decision_sha256",
        prefix="arv2-firm-owner-decision-",
    )
    _require_documents(
        decision=decision,
        ledger=ledger,
        proposal_firms=proposal_firms,
        expected_source=source,
    )
    return decision, ledger


def _require_documents(
    *,
    decision: object,
    ledger: object,
    proposal_firms: tuple[dict[str, object], ...],
    expected_source: Mapping[str, object],
) -> tuple[int, int, int]:
    if type(decision) is not dict or set(decision) != _DECISION_KEYS:
        _refuse("mixed owner-decision document fields changed")
    if type(ledger) is not dict or set(ledger) != _LEDGER_KEYS:
        _refuse("named-refusal ledger fields changed")
    if decision.get("source") != expected_source or ledger.get("source") != expected_source:
        _refuse("mixed owner-decision parent bindings changed")
    if (
        decision.get("schema") != OWNER_DECISION_SCHEMA
        or ledger.get("schema") != REFUSAL_LEDGER_SCHEMA
    ):
        _refuse("mixed owner-decision schema changed")
    if not _address_is_current(
        ledger,
        identifier_field="ledger_id",
        digest_field="ledger_sha256",
        prefix="arv2-firm-refusal-ledger-",
    ):
        _refuse("named-refusal ledger content address changed")
    if not _address_is_current(
        decision,
        identifier_field="decision_id",
        digest_field="decision_sha256",
        prefix="arv2-firm-owner-decision-",
    ):
        _refuse("mixed owner-decision content address changed")
    capabilities = decision.get("capabilities")
    if capabilities != {name: False for name in _CAPABILITY_NAMES}:
        _refuse("mixed owner-decision non-authority capabilities changed")
    if decision.get("policy") != _policy_record():
        _refuse("mixed owner-decision frozen policy changed")
    firms = decision.get("firms")
    entries = ledger.get("entries")
    if (
        type(firms) is not list
        or len(firms) != EXPECTED_FIRM_COUNT
        or type(proposal_firms) is not tuple
        or len(proposal_firms) != EXPECTED_FIRM_COUNT
    ):
        _refuse("mixed owner-decision firm coverage is not exactly 74")
    if type(entries) is not list:
        _refuse("named-refusal ledger entries changed type")
    ledger_by_id: dict[str, dict[str, object]] = {}
    for entry in entries:
        if type(entry) is not dict or set(entry) != _REFUSAL_KEYS:
            _refuse("named-refusal ledger entry fields changed")
        refusal_id = entry.get("refusal_id")
        if type(refusal_id) is not str or refusal_id in ledger_by_id:
            _refuse("named-refusal ledger repeats an entry identity")
        if (
            entry.get("schema") != REFUSAL_ENTRY_SCHEMA
            or entry.get("decision_status")
            != FirmOntologyOwnerDecisionStatus.NAMED_REFUSAL.value
            or not _address_is_current(
                entry,
                identifier_field="refusal_id",
                digest_field="refusal_sha256",
                prefix="arv2-firm-named-refusal-",
            )
        ):
            _refuse("named-refusal ledger entry status or content address changed")
        ledger_by_id[refusal_id] = entry
    accepted_ids: set[str] = set()
    refused_ids: set[str] = set()
    seen_ids: set[str] = set()
    proxy_count = 0
    expected_refusal_ids: list[str] = []
    for ordinal, (row, source_firm) in enumerate(
        zip(firms, proposal_firms, strict=True), start=1
    ):
        if type(row) is not dict or set(row) != _DECISION_FIRM_KEYS:
            _refuse("mixed owner-decision firm row fields changed")
        firm_id = row.get("provider_firm_id")
        if (
            type(firm_id) is not str
            or not firm_id
            or firm_id in seen_ids
            or row.get("ranking_ordinal") != ordinal
            or source_firm.get("provider_firm_id") != firm_id
            or source_firm.get("ranking_ordinal") != ordinal
        ):
            _refuse("mixed owner-decision firm coverage overlaps or is out of order")
        seen_ids.add(firm_id)
        if (
            row.get("proposal_firm_row_sha256") != _record_sha256(source_firm)
            or row.get("firm_evidence_row_sha256")
            != source_firm.get("firm_evidence_row_sha256")
        ):
            _refuse("mixed owner-decision firm source binding changed")
        status = row.get("decision_status")
        if type(status) is not str or status not in _STATUS_VALUES:
            _refuse("mixed owner-decision status is outside the exact enum")
        eligible = source_firm.get("bulk_ratification_eligible")
        unresolved = source_firm.get("unresolved_labels")
        reasons = source_firm.get("exception_reasons")
        expected_status = (
            FirmOntologyOwnerDecisionStatus.ACCEPTED_DETERMINISTIC_DEFAULT.value
            if eligible is True and unresolved == [] and reasons == []
            else FirmOntologyOwnerDecisionStatus.NAMED_REFUSAL.value
        )
        if status != expected_status:
            _refuse("mixed owner-decision status contradicts authenticated proposal policy")
        if status == FirmOntologyOwnerDecisionStatus.ACCEPTED_DETERMINISTIC_DEFAULT.value:
            accepted_ids.add(firm_id)
            defaults = row.get("accepted_proposal_defaults")
            if (
                type(defaults) is not dict
                or defaults != source_firm.get("proposed_defaults")
                or row.get("accepted_proposal_defaults_sha256")
                != _record_sha256(defaults)
            ):
                _refuse("accepted firm defaults are not the exact authenticated proposal copy")
            expected_proxies = [
                _availability_proxy(
                    firm=source_firm,
                    mapping=mapping,
                    mapping_role=role,
                    packet_id=expected_source["packet_id"],
                    packet_sha256=expected_source["packet_sha256"],
                )
                for role, mappings in (
                    ("ordered_scale", defaults.get("ordered_scale")),
                    ("alias_mapping", defaults.get("alias_mappings")),
                )
                for mapping in mappings
            ]
            if (
                row.get("availability_proxies") != expected_proxies
                or row.get("refusal_id") is not None
                or row.get("refusal_sha256") is not None
            ):
                _refuse("accepted firm proxy or refusal binding changed")
            proxy_count += len(expected_proxies)
        else:
            refused_ids.add(firm_id)
            if (
                row.get("accepted_proposal_defaults") is not None
                or row.get("accepted_proposal_defaults_sha256") is not None
                or row.get("availability_proxies") != []
            ):
                _refuse("named-refusal firm carries mappings or accepted defaults")
            refusal = ledger_by_id.get(row.get("refusal_id"))
            if (
                refusal is None
                or row.get("refusal_sha256") != refusal.get("refusal_sha256")
                or refusal.get("ranking_ordinal") != ordinal
                or refusal.get("provider_firm_id") != firm_id
                or refusal.get("proposal_firm_row_sha256")
                != row.get("proposal_firm_row_sha256")
                or refusal.get("firm_evidence_row_sha256")
                != row.get("firm_evidence_row_sha256")
                or refusal.get("unresolved_labels") != unresolved
                or refusal.get("unresolved_labels_sha256")
                != _record_sha256(unresolved)
                or refusal.get("exception_reasons") != reasons
                or refusal.get("exception_reasons_sha256")
                != _record_sha256(reasons)
            ):
                _refuse("named refusal does not bind exact proposal labels and reasons")
            expected_refusal_ids.append(refusal["refusal_id"])
    if list(ledger_by_id) != expected_refusal_ids:
        _refuse("named-refusal ledger order, coverage, or decision binding changed")
    census = decision.get("census")
    expected_census = {
        "expected_firm_count": EXPECTED_FIRM_COUNT,
        "decision_firm_count": len(firms),
        "accepted_firm_count": len(accepted_ids),
        "refused_firm_count": len(refused_ids),
        "availability_proxy_count": proxy_count,
        "refusal_ledger_entry_count": len(ledger_by_id),
    }
    refusal_ledger_binding = decision.get("refusal_ledger")
    if census != expected_census:
        _refuse("mixed owner-decision census changed")
    if (
        ledger.get("expected_firm_count") != EXPECTED_FIRM_COUNT
        or ledger.get("refused_firm_count") != len(refused_ids)
        or refusal_ledger_binding
        != {
            "ledger_id": ledger["ledger_id"],
            "ledger_sha256": ledger["ledger_sha256"],
            "ledger_payload_sha256": _record_sha256(ledger),
        }
    ):
        _refuse("mixed owner-decision refusal-ledger binding changed")
    return len(accepted_ids), len(refused_ids), proxy_count


_PINNED_BUILD_HELPERS = tuple(globals()[name] for name in _BUILD_HELPER_NAMES)


def _parents(
    review_packet: PhysicalFirmOntologyReviewPacket,
    proposal: FirmOntologyProposalArtifact,
) -> tuple[PhysicalFirmOntologyReviewPacket, FirmOntologyProposalArtifact]:
    if (
        type(review_packet) is not _PINNED_PACKET_TYPE
        or type(proposal) is not _PINNED_PROPOSAL_TYPE
    ):
        _refuse("firm owner-decision requires exact parent authority types")
    try:
        packet = _PINNED_PACKET_REQUIRE(review_packet)
        authenticated_proposal = _PINNED_PROPOSAL_REQUIRE(proposal)
    except (
        _packet.PhysicalFirmOntologyReviewPacketError,
        _proposal.FirmOntologyProposalError,
    ) as exc:
        raise FirmOntologyOwnerDecisionError(
            "firm owner-decision parent did not reauthenticate"
        ) from exc
    if (
        authenticated_proposal.packet_id != packet.packet_id
        or authenticated_proposal.packet_sha256 != packet.packet_sha256
    ):
        _refuse("firm owner-decision proposal and packet parents do not bind")
    return packet, authenticated_proposal


def build_firm_ontology_owner_decision(
    *,
    review_packet: PhysicalFirmOntologyReviewPacket,
    proposal: FirmOntologyProposalArtifact,
) -> FirmOntologyOwnerDecisionArtifact:
    """Apply the owner's deterministic-default-or-named-refusal rule."""

    _require_dependencies()
    packet, authenticated_proposal = _parents(review_packet, proposal)
    try:
        proposal_firms = tuple(
            _PINNED_PROPOSAL_ITERATOR(authenticated_proposal)
        )
    except _proposal.FirmOntologyProposalError as exc:
        raise FirmOntologyOwnerDecisionError(
            "firm owner-decision proposal rows did not reauthenticate"
        ) from exc
    decision, ledger = _compose_documents(
        proposal_firms=proposal_firms,
        packet_id=packet.packet_id,
        packet_sha256=packet.packet_sha256,
        proposal_id=authenticated_proposal.proposal_id,
        proposal_sha256=authenticated_proposal.proposal_sha256,
        proposal_payload_sha256=authenticated_proposal.payload_sha256,
    )
    decision_bytes = _PINNED_CANONICAL(decision)
    ledger_bytes = _PINNED_CANONICAL(ledger)
    if len(decision_bytes) > MAX_DECISION_BYTES:
        _refuse("mixed owner-decision document exceeds its fixed byte bound")
    if len(ledger_bytes) > MAX_REFUSAL_LEDGER_BYTES:
        _refuse("named-refusal ledger exceeds its fixed byte bound")
    _PINNED_PACKET_REQUIRE(packet)
    _PINNED_PROPOSAL_REQUIRE(authenticated_proposal)
    accepted, refused, proxies = _require_documents(
        decision=decision,
        ledger=ledger,
        proposal_firms=proposal_firms,
        expected_source=decision["source"],
    )
    false_capabilities = {name: False for name in _CAPABILITY_NAMES}
    values: dict[str, object] = {
        "schema": OWNER_DECISION_SCHEMA,
        "decision_id": decision["decision_id"],
        "decision_sha256": decision["decision_sha256"],
        "decision_payload_sha256": _PINNED_SHA256(decision_bytes),
        "decision_bytes": decision_bytes,
        "refusal_ledger_id": ledger["ledger_id"],
        "refusal_ledger_sha256": ledger["ledger_sha256"],
        "refusal_ledger_payload_sha256": _PINNED_SHA256(ledger_bytes),
        "refusal_ledger_bytes": ledger_bytes,
        "packet_id": packet.packet_id,
        "packet_sha256": packet.packet_sha256,
        "proposal_id": authenticated_proposal.proposal_id,
        "proposal_sha256": authenticated_proposal.proposal_sha256,
        "proposal_payload_sha256": authenticated_proposal.payload_sha256,
        "firm_count": EXPECTED_FIRM_COUNT,
        "accepted_firm_count": accepted,
        "refused_firm_count": refused,
        "availability_proxy_count": proxies,
        **false_capabilities,
    }
    value = FirmOntologyOwnerDecisionArtifact(**values)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget(key, ref)
    )
    with _AUTHORITY_LOCK:
        _AUTHORITIES[identity] = (
            reference,
            _fingerprint(value),
            weakref.ref(authenticated_proposal),
            weakref.ref(packet),
            os.getpid(),
        )
    return require_firm_ontology_owner_decision(value)


def _decode_object(payload: bytes, name: str) -> dict[str, Any]:
    try:
        value = _PINNED_STRICT_LOADS(_PINNED_DECODE(payload, name), name)
    except CanonicalEvidenceError as exc:
        raise FirmOntologyOwnerDecisionError(
            f"{name} is not strict JSON"
        ) from exc
    if type(value) is not dict or _PINNED_CANONICAL(value) != payload:
        _refuse(f"{name} is not one canonical object")
    return value


def require_firm_ontology_owner_decision(
    value: FirmOntologyOwnerDecisionArtifact,
) -> FirmOntologyOwnerDecisionArtifact:
    """Reauthenticate the artifact, proposal, and physical review packet."""

    _require_dependencies()
    current_pid = os.getpid()
    if (
        type(value) is not FirmOntologyOwnerDecisionArtifact
        or current_pid != _AUTHORITY_PID
    ):
        _refuse("firm owner-decision is not current process authority")
    with _AUTHORITY_LOCK:
        authority = _AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or authority[1] != _fingerprint(value)
        or authority[4] != current_pid
        or any(getattr(value, name) is not False for name in _CAPABILITY_NAMES)
    ):
        _refuse("firm owner-decision is not current builder authority")
    proposal = authority[2]()
    packet = authority[3]()
    if proposal is None or packet is None:
        _refuse("firm owner-decision parent authority is unavailable")
    packet, proposal = _parents(packet, proposal)
    if (
        value.packet_id != packet.packet_id
        or value.packet_sha256 != packet.packet_sha256
        or value.proposal_id != proposal.proposal_id
        or value.proposal_sha256 != proposal.proposal_sha256
        or value.proposal_payload_sha256 != proposal.payload_sha256
        or type(value.decision_bytes) is not bytes
        or type(value.refusal_ledger_bytes) is not bytes
        or value.decision_payload_sha256 != _PINNED_SHA256(value.decision_bytes)
        or value.refusal_ledger_payload_sha256
        != _PINNED_SHA256(value.refusal_ledger_bytes)
    ):
        _refuse("firm owner-decision artifact or parent binding changed")
    decision = _decode_object(value.decision_bytes, "mixed owner decision")
    ledger = _decode_object(value.refusal_ledger_bytes, "named refusal ledger")
    try:
        proposal_firms = tuple(_PINNED_PROPOSAL_ITERATOR(proposal))
    except _proposal.FirmOntologyProposalError as exc:
        raise FirmOntologyOwnerDecisionError(
            "firm owner-decision proposal rows did not reauthenticate"
        ) from exc
    accepted, refused, proxies = _require_documents(
        decision=decision,
        ledger=ledger,
        proposal_firms=proposal_firms,
        expected_source={
            "packet_id": value.packet_id,
            "packet_sha256": value.packet_sha256,
            "proposal_id": value.proposal_id,
            "proposal_sha256": value.proposal_sha256,
            "proposal_payload_sha256": value.proposal_payload_sha256,
        },
    )
    if (
        value.schema != OWNER_DECISION_SCHEMA
        or value.decision_id != decision["decision_id"]
        or value.decision_sha256 != decision["decision_sha256"]
        or value.refusal_ledger_id != ledger["ledger_id"]
        or value.refusal_ledger_sha256 != ledger["ledger_sha256"]
        or value.firm_count != EXPECTED_FIRM_COUNT
        or value.accepted_firm_count != accepted
        or value.refused_firm_count != refused
        or value.availability_proxy_count != proxies
    ):
        _refuse("firm owner-decision artifact projection changed")
    _PINNED_PACKET_REQUIRE(packet)
    _PINNED_PROPOSAL_REQUIRE(proposal)
    return value


def iter_firm_ontology_owner_decisions(
    value: FirmOntologyOwnerDecisionArtifact,
) -> Iterator[dict[str, object]]:
    artifact = require_firm_ontology_owner_decision(value)
    decision = _decode_object(artifact.decision_bytes, "mixed owner decision")
    for row in decision["firms"]:
        yield row
    require_firm_ontology_owner_decision(artifact)


def iter_firm_ontology_named_refusals(
    value: FirmOntologyOwnerDecisionArtifact,
) -> Iterator[dict[str, object]]:
    artifact = require_firm_ontology_owner_decision(value)
    ledger = _decode_object(artifact.refusal_ledger_bytes, "named refusal ledger")
    for row in ledger["entries"]:
        yield row
    require_firm_ontology_owner_decision(artifact)


__all__ = [
    "AVAILABILITY_PROXY_KIND",
    "AVAILABILITY_PROXY_SCHEMA",
    "EXPECTED_FIRM_COUNT",
    "FirmOntologyOwnerDecisionArtifact",
    "FirmOntologyOwnerDecisionError",
    "FirmOntologyOwnerDecisionStatus",
    "OWNER_DECISION_SCHEMA",
    "REFUSAL_ENTRY_SCHEMA",
    "REFUSAL_LEDGER_SCHEMA",
    "build_firm_ontology_owner_decision",
    "iter_firm_ontology_named_refusals",
    "iter_firm_ontology_owner_decisions",
    "require_firm_ontology_owner_decision",
]
