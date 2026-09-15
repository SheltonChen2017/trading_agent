"""Deterministic, non-authorizing proposals for the 74-firm ontology review.

Only an authenticated physical firm-review packet and the checked-in frozen
global comparator are read.  Comparator levels are suggestions, never firm
semantics: named ambiguous aliases, refusals, unknowns, cycles, opposite
directions, and tier collapses remain explicit owner exceptions.  The output
contains no owner review, availability, registry, production, QC, outcome,
deployment, order, or trading authority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import stat
import threading
import weakref
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator, Mapping

from research.analyst_revisions_v2 import global_benchmark_contract as global_map
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2.global_benchmark_contract import (
    GlobalBenchmarkContract,
    GlobalRatingMapping,
    GlobalRatingMappingRefusal,
    GlobalRatingRefusalReason,
)
from research.analyst_revisions_v2_qc import (
    physical_firm_ontology_review_packet as packet_module,
)
from research.analyst_revisions_v2_qc.physical_firm_ontology_review_packet import (
    PhysicalFirmOntologyReviewPacket,
)


PROPOSAL_SCHEMA = "arv2-firm-ontology-bulk-default-proposal-v1"
MAPPING_EVIDENCE_SCHEMA = "arv2-firm-ontology-proposal-evidence-v1"
EXPECTED_FIRM_COUNT = 74
MAX_LABELS_PER_FIRM = 512
MAX_TRANSITIONS_PER_FIRM = 4096
MAX_PROPOSAL_BYTES = 16 * 1024 * 1024
AMBIGUOUS_GLOBAL_ALIASES = frozenset(
    {"accumulate", "positive", "sector perform", "top pick"}
)
SPEC_ROOT = Path(__file__).resolve().parents[1] / "analyst_revisions_v2" / "specs"
_GLOBAL_PATHS = {
    "map_path": SPEC_ROOT / "arv2_global_rating_map.structural.json",
    "matched_contract_path": SPEC_ROOT
    / "arv2_global_matched_comparison.structural.json",
    "successor_spec_path": SPEC_ROOT
    / "arv2_stock_historical_successor.structural.json",
    "parent_stock_spec_path": SPEC_ROOT / "arv2_stock_historical.structural.json",
    "fold_manifest_path": SPEC_ROOT
    / "arv2_stock_walk_forward_folds.structural.json",
    "qc_first_plan_path": SPEC_ROOT / "arv2_qc_first.draft.json",
}
NON_AUTHORITY_FIELDS = (
    "owner_reviewed_complete",
    "owner_ratification_received",
    "availability_authority_created",
    "registry_authority_created",
    "production_authority",
    "provider_access",
    "quantconnect_access",
    "credential_access",
    "outcome_access",
    "result_access",
    "deployment",
    "orders",
    "trading",
)
_FALSE_FIELDS = NON_AUTHORITY_FIELDS
_PATH_TYPE = type(Path("."))

_PINNED_PACKET_TYPE = PhysicalFirmOntologyReviewPacket
_PINNED_PACKET_REQUIRE = packet_module.require_physical_firm_ontology_review_packet
_PINNED_TEMPLATE_ITERATOR = (
    packet_module.iter_physical_firm_owner_adjudication_template
)
_PINNED_EVIDENCE_ITERATOR = packet_module.iter_physical_firm_ontology_review_rows
_PINNED_GLOBAL_TYPE = GlobalBenchmarkContract
_PINNED_GLOBAL_LOAD = global_map.load_global_benchmark_contract
_PINNED_GLOBAL_REQUIRE = global_map.require_loaded_global_benchmark_contract
_PINNED_GLOBAL_RESOLVE = global_map.resolve_global_rating
_PINNED_GLOBAL_MAPPING_TYPE = GlobalRatingMapping
_PINNED_GLOBAL_REFUSAL_TYPE = GlobalRatingMappingRefusal
_PINNED_GLOBAL_REFUSAL_ENUM = GlobalRatingRefusalReason
_PINNED_CANONICAL = canonical_json_bytes
_PINNED_AMBIGUOUS = frozenset(AMBIGUOUS_GLOBAL_ALIASES)
_BUILD_HELPER_NAMES = (
    "_load_global_map",
    "_canonical",
    "_sha_record",
    "_template_bindings",
    "_observed_labels",
    "_transition_conflicts",
    "_mapping_evidence",
    "_propose_firm",
    "_require_non_authorizing_proposal",
    "_compose_proposal",
    "_identity",
    "_write_private",
    "_read_private",
)


class FirmOntologyProposalError(ValueError):
    """The proposal input, construction, or private output is invalid."""


class FirmOntologyProposalCapacityError(FirmOntologyProposalError):
    """A fixed proposal count or byte bound was exceeded."""


@dataclasses.dataclass(frozen=True, slots=True)
class _FileIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int
    owner: int
    mode: int
    links: int


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FirmOntologyProposalArtifact:
    schema: str
    proposal_id: str
    proposal_sha256: str
    payload_sha256: str
    byte_count: int
    path: Path
    packet_id: str
    packet_sha256: str
    global_map_id: str
    global_map_sha256: str
    firm_count: int
    bulk_ratification_eligible_firm_count: int
    exception_firm_count: int
    proposed_primary_mapping_count: int
    proposed_alias_mapping_count: int
    unresolved_label_count: int
    owner_reviewed_complete: bool
    owner_ratification_received: bool
    availability_authority_created: bool
    registry_authority_created: bool
    production_authority: bool
    provider_access: bool
    quantconnect_access: bool
    credential_access: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool


_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[FirmOntologyProposalArtifact],
        tuple[object, ...],
        _FileIdentity,
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


def _fingerprint(value: FirmOntologyProposalArtifact) -> tuple[object, ...]:
    return tuple(getattr(value, field.name) for field in dataclasses.fields(value))


def _require_dependencies() -> None:
    if (
        packet_module.PhysicalFirmOntologyReviewPacket is not _PINNED_PACKET_TYPE
        or packet_module.require_physical_firm_ontology_review_packet
        is not _PINNED_PACKET_REQUIRE
        or packet_module.iter_physical_firm_owner_adjudication_template
        is not _PINNED_TEMPLATE_ITERATOR
        or packet_module.iter_physical_firm_ontology_review_rows
        is not _PINNED_EVIDENCE_ITERATOR
        or global_map.GlobalBenchmarkContract is not _PINNED_GLOBAL_TYPE
        or global_map.load_global_benchmark_contract is not _PINNED_GLOBAL_LOAD
        or global_map.require_loaded_global_benchmark_contract
        is not _PINNED_GLOBAL_REQUIRE
        or global_map.resolve_global_rating is not _PINNED_GLOBAL_RESOLVE
        or global_map.GlobalRatingMapping is not _PINNED_GLOBAL_MAPPING_TYPE
        or global_map.GlobalRatingMappingRefusal is not _PINNED_GLOBAL_REFUSAL_TYPE
        or global_map.GlobalRatingRefusalReason is not _PINNED_GLOBAL_REFUSAL_ENUM
        or canonical_json_bytes is not _PINNED_CANONICAL
        or type(AMBIGUOUS_GLOBAL_ALIASES) is not frozenset
        or AMBIGUOUS_GLOBAL_ALIASES != _PINNED_AMBIGUOUS
        or tuple(globals().get(name) for name in _BUILD_HELPER_NAMES)
        != _PINNED_BUILD_HELPERS
    ):
        raise FirmOntologyProposalError(
            "firm-ontology proposal dependency authority changed"
        )


def _load_global_map() -> GlobalBenchmarkContract:
    try:
        contract = _PINNED_GLOBAL_LOAD(**_GLOBAL_PATHS)
        return _PINNED_GLOBAL_REQUIRE(contract)
    except global_map.GlobalBenchmarkContractError as exc:
        raise FirmOntologyProposalError(
            "frozen global-map proposal policy did not authenticate"
        ) from exc


def _canonical(value: object) -> bytes:
    try:
        return _PINNED_CANONICAL(value)
    except (TypeError, ValueError, RecursionError) as exc:
        raise FirmOntologyProposalError(
            "firm-ontology proposal value is not canonical"
        ) from exc


def _sha_record(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _template_bindings(
    packet: PhysicalFirmOntologyReviewPacket,
) -> tuple[tuple[str, Mapping[str, object]], ...]:
    bindings: list[tuple[str, Mapping[str, object]]] = []
    expected_ordinal = 1
    for row in _PINNED_TEMPLATE_ITERATOR(packet):
        if type(row) is not dict:
            raise FirmOntologyProposalError("proposal template row type changed")
        firm_id = row.get("provider_firm_id")
        ordinal = row.get("ranking_ordinal")
        volume = row.get("predeclared_2021_2025_volume_count")
        names = row.get("observed_firm_names")
        if (
            type(firm_id) is not str
            or not firm_id
            or type(ordinal) is not int
            or ordinal != expected_ordinal
            or type(volume) is not int
            or volume <= 0
            or type(names) is not list
            or any(type(name) is not str or not name for name in names)
            or row.get("ontology_authority_created") is not False
            or row.get("availability_authority_created") is not False
            or row.get("production_authority") is not False
        ):
            raise FirmOntologyProposalError(
                "proposal template identity or non-authority fields changed"
            )
        bindings.append(
            (
                firm_id,
                {
                    "ranking_ordinal": ordinal,
                    "provider_firm_id": firm_id,
                    "predeclared_2021_2025_volume_count": volume,
                    "observed_firm_names": list(names),
                    "template_row_sha256": _sha_record(row),
                },
            )
        )
        expected_ordinal += 1
        if len(bindings) > EXPECTED_FIRM_COUNT:
            raise FirmOntologyProposalCapacityError(
                "proposal template exceeds the fixed 74-firm census"
            )
    if len(bindings) != EXPECTED_FIRM_COUNT:
        raise FirmOntologyProposalError(
            "proposal requires the exact authenticated 74-firm template"
        )
    return tuple(bindings)


def _observed_labels(evidence: Mapping[str, object]) -> dict[str, dict[str, object]]:
    raw = evidence.get("observed_labels")
    if type(raw) is not list or len(raw) > MAX_LABELS_PER_FIRM:
        raise FirmOntologyProposalCapacityError(
            "proposal observed-label census exceeds its fixed per-firm bound"
        )
    result: dict[str, dict[str, object]] = {}
    for item in raw:
        if type(item) is not dict:
            raise FirmOntologyProposalError("proposal observed label changed type")
        label = item.get("raw_label")
        field = item.get("field")
        count = item.get("observed_count")
        first = item.get("first_event_date")
        last = item.get("last_event_date")
        if (
            type(label) is not str
            or not label
            or type(field) is not str
            or field not in {"rating", "previous_rating"}
            or type(count) is not int
            or count <= 0
            or type(first) is not str
            or type(last) is not str
        ):
            raise FirmOntologyProposalError(
                "proposal observed-label evidence changed"
            )
        aggregate = result.setdefault(
            label,
            {
                "raw_label": label,
                "observed_count": 0,
                "first_event_date": first,
                "last_event_date": last,
                "fields": [],
            },
        )
        aggregate["observed_count"] += count
        aggregate["first_event_date"] = min(
            aggregate["first_event_date"], first
        )
        aggregate["last_event_date"] = max(aggregate["last_event_date"], last)
        aggregate["fields"].append(
            {
                "field": field,
                "observed_count": count,
                "first_event_date": first,
                "last_event_date": last,
            }
        )
    for value in result.values():
        value["fields"].sort(key=lambda item: item["field"])
    return result


def _transition_conflicts(
    evidence: Mapping[str, object],
    labels: Mapping[str, Mapping[str, object]],
    resolutions: Mapping[str, GlobalRatingMapping | GlobalRatingMappingRefusal],
) -> tuple[set[str], set[str], set[str], dict[str, int]]:
    raw = evidence.get("transition_counts")
    if type(raw) is not list or len(raw) > MAX_TRANSITIONS_PER_FIRM:
        raise FirmOntologyProposalCapacityError(
            "proposal transition census exceeds its fixed per-firm bound"
        )
    adjacency: dict[str, set[str]] = {label: set() for label in labels}
    opposite: set[str] = set()
    collapsed: set[str] = set()
    directional_rows = 0
    direct_edges: set[tuple[str, str]] = set()
    for item in raw:
        if type(item) is not dict:
            raise FirmOntologyProposalError("proposal transition changed type")
        previous = item.get("previous_rating")
        current = item.get("current_rating")
        action = item.get("action_label")
        count = item.get("observed_count")
        if (
            type(previous) is not str
            or type(current) is not str
            or previous not in labels
            or current not in labels
            or type(action) is not str
            or type(count) is not int
            or count <= 0
        ):
            raise FirmOntologyProposalError(
                "proposal transition evidence changed"
            )
        if action not in {"upgrades", "downgrades"}:
            continue
        directional_rows += count
        lower, higher = (
            (previous, current) if action == "upgrades" else (current, previous)
        )
        if lower != higher:
            adjacency[lower].add(higher)
            direct_edges.add((lower, higher))
        low_mapping = resolutions[lower]
        high_mapping = resolutions[higher]
        if (
            type(low_mapping) is _PINNED_GLOBAL_MAPPING_TYPE
            and type(high_mapping) is _PINNED_GLOBAL_MAPPING_TYPE
            and low_mapping.canonical_label not in _PINNED_AMBIGUOUS
            and high_mapping.canonical_label not in _PINNED_AMBIGUOUS
        ):
            low_level = low_mapping.entry.legacy_level
            high_level = high_mapping.entry.legacy_level
            if low_level > high_level:
                opposite.update((lower, higher))
            elif low_level == high_level:
                collapsed.update((lower, higher))

    reachable: dict[str, set[str]] = {}
    for origin in adjacency:
        seen: set[str] = set()
        pending = list(adjacency[origin])
        while pending:
            item = pending.pop()
            if item in seen:
                continue
            seen.add(item)
            pending.extend(adjacency[item] - seen)
        reachable[origin] = seen
    cycle = {
        label
        for label in adjacency
        if any(
            other != label
            and other in reachable[label]
            and label in reachable[other]
            for other in adjacency
        )
    }
    direct_conflict_pairs = sum(
        1
        for lower, higher in direct_edges
        if lower < higher and (higher, lower) in direct_edges
    )
    diagnostics = evidence.get("conflict_and_connectedness_diagnostics")
    if (
        type(diagnostics) is not dict
        or diagnostics.get("directional_preference_cycle_detected")
        is not bool(cycle)
        or diagnostics.get("directional_preference_conflict_pair_count")
        != direct_conflict_pairs
    ):
        raise FirmOntologyProposalError(
            "proposal conflict diagnostics do not reauthenticate"
        )
    return cycle, opposite, collapsed, {
        "directional_transition_observation_count": directional_rows,
        "directional_cycle_label_count": len(cycle),
        "global_opposite_direction_label_count": len(opposite),
        "global_tier_collapse_label_count": len(collapsed),
        "direct_conflict_pair_count": direct_conflict_pairs,
    }


def _mapping_evidence(
    *,
    packet: PhysicalFirmOntologyReviewPacket,
    firm_id: str,
    evidence_sha256: str,
    observation: Mapping[str, object],
) -> dict[str, object]:
    seed: dict[str, object] = {
        "schema": MAPPING_EVIDENCE_SCHEMA,
        "evidence_id": None,
        "evidence_sha256": None,
        "packet_id": packet.packet_id,
        "packet_sha256": packet.packet_sha256,
        "provider_firm_id": firm_id,
        "firm_evidence_row_sha256": evidence_sha256,
        "raw_label": observation["raw_label"],
        "observed_count": observation["observed_count"],
        "first_event_date": observation["first_event_date"],
        "last_event_date": observation["last_event_date"],
        "fields": observation["fields"],
        "availability_time_proposed": None,
        "owner_confirmation_required": True,
    }
    digest = _sha_record(seed)
    seed["evidence_id"] = f"arv2-firm-proposal-evidence-{digest[:24]}"
    seed["evidence_sha256"] = digest
    return seed


def _propose_firm(
    *,
    packet: PhysicalFirmOntologyReviewPacket,
    contract: GlobalBenchmarkContract,
    template: Mapping[str, object],
    evidence: Mapping[str, object],
    resolver_cache: dict[
        str, GlobalRatingMapping | GlobalRatingMappingRefusal
    ],
) -> dict[str, object]:
    firm_id = template["provider_firm_id"]
    if evidence.get("provider_firm_id") != firm_id:
        raise FirmOntologyProposalError(
            "proposal evidence/template firm binding changed"
        )
    evidence_bytes = _canonical(evidence)
    if len(evidence_bytes) > packet_module.MAX_REVIEW_ROW_BYTES:
        raise FirmOntologyProposalCapacityError(
            "proposal evidence row exceeds the packet row bound"
        )
    evidence_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
    labels = _observed_labels(evidence)
    for label in labels:
        if label not in resolver_cache:
            try:
                resolver_cache[label] = _PINNED_GLOBAL_RESOLVE(contract, label)
            except global_map.GlobalBenchmarkContractError as exc:
                raise FirmOntologyProposalError(
                    "global-map proposal resolution lost authority"
                ) from exc
    resolutions = {label: resolver_cache[label] for label in labels}
    cycle, opposite, collapsed, conflict_census = _transition_conflicts(
        evidence, labels, resolutions
    )

    unresolved: list[dict[str, object]] = []
    eligible_by_level: dict[int, list[tuple[str, GlobalRatingMapping]]] = defaultdict(list)
    for raw_label in sorted(labels, key=lambda value: (value.casefold(), value)):
        resolution = resolutions[raw_label]
        reasons: list[str] = []
        disposition: str
        canonical_label: str | None
        if type(resolution) is _PINNED_GLOBAL_REFUSAL_TYPE:
            canonical_label = resolution.canonical_label
            disposition = resolution.reason.value
            reasons.append(
                "frozen_global_refusal"
                if resolution.reason
                is _PINNED_GLOBAL_REFUSAL_ENUM.MEASURED_REFUSAL
                else "unknown_or_invalid_global_label"
            )
        elif type(resolution) is _PINNED_GLOBAL_MAPPING_TYPE:
            canonical_label = resolution.canonical_label
            disposition = "mapped_39_alias"
            if canonical_label in _PINNED_AMBIGUOUS:
                reasons.append("global_map_named_ambiguous_alias")
            if raw_label in cycle:
                reasons.append("firm_directional_cycle")
            if raw_label in opposite:
                reasons.append("firm_global_opposite_direction")
            if raw_label in collapsed:
                reasons.append("firm_global_tier_collapse")
            if not reasons:
                eligible_by_level[resolution.entry.legacy_level].append(
                    (raw_label, resolution)
                )
        else:
            raise FirmOntologyProposalError(
                "global-map resolver returned an unknown result type"
            )
        if reasons:
            unresolved.append(
                {
                    "raw_label": raw_label,
                    "canonical_label": canonical_label,
                    "global_disposition": disposition,
                    "reasons": sorted(reasons),
                    "observation": labels[raw_label],
                    "proposed_rank": None,
                    "owner_adjudication_required": True,
                }
            )

    proposed_primary: list[dict[str, object]] = []
    proposed_aliases: list[dict[str, object]] = []
    interval = {
        "valid_from": evidence.get("first_event_date"),
        "valid_to": None,
        "owner_confirmation_required": True,
    }
    if type(interval["valid_from"]) is not str:
        raise FirmOntologyProposalError("proposal firm date span changed")
    for rank, level in enumerate(sorted(eligible_by_level), start=1):
        items = sorted(
            eligible_by_level[level],
            key=lambda item: (
                -labels[item[0]]["observed_count"],
                item[1].canonical_label,
                item[0],
            ),
        )
        for index, (raw_label, resolution) in enumerate(items):
            record = {
                "raw_label": raw_label,
                "canonical_global_label": resolution.canonical_label,
                "proposed_ordered_rank": rank,
                "proposed_scale_size": len(eligible_by_level),
                "global_legacy_level": level,
                "valid_from": interval["valid_from"],
                "valid_to": None,
                "mapping_evidence": _mapping_evidence(
                    packet=packet,
                    firm_id=firm_id,
                    evidence_sha256=evidence_sha256,
                    observation=labels[raw_label],
                ),
                "proposal_basis": "frozen_global_map_alias_only_not_firm_truth",
                "owner_confirmation_required": True,
            }
            (proposed_primary if index == 0 else proposed_aliases).append(record)

    names = evidence.get("observed_firm_names")
    if type(names) is not list:
        raise FirmOntologyProposalError("proposal firm-name evidence changed")
    name_candidates: list[tuple[int, str]] = []
    for item in names:
        if (
            type(item) is not dict
            or type(item.get("firm_name")) is not str
            or not item["firm_name"]
            or type(item.get("observed_count")) is not int
            or item["observed_count"] <= 0
        ):
            raise FirmOntologyProposalError("proposal firm-name evidence changed")
        name_candidates.append((item["observed_count"], item["firm_name"]))
    ranking = evidence.get("predeclared_2021_2025_volume_ranking")
    if (
        type(ranking) is not dict
        or ranking.get("ranking_ordinal") != template.get("ranking_ordinal")
        or ranking.get("volume_count")
        != template.get("predeclared_2021_2025_volume_count")
        or ranking.get("selected_for_owner_adjudication") is not True
        or [item[1] for item in name_candidates]
        != template.get("observed_firm_names")
    ):
        raise FirmOntologyProposalError(
            "proposal evidence/template selection binding changed"
        )
    canonical_name = (
        None
        if not name_candidates
        else sorted(name_candidates, key=lambda item: (-item[0], item[1]))[0][1]
    )
    firm_reasons = sorted(
        {
            reason
            for item in unresolved
            for reason in item["reasons"]
        }
        | ({"canonical_name_unavailable"} if canonical_name is None else set())
        | (
            {"fewer_than_two_nonconflicted_global_levels"}
            if len(eligible_by_level) < 2
            else set()
        )
    )
    return {
        **dict(template),
        "firm_evidence_row_sha256": evidence_sha256,
        "observed_first_event_date": evidence.get("first_event_date"),
        "observed_last_event_date": evidence.get("last_event_date"),
        "proposed_defaults": {
            "canonical_firm_name": canonical_name,
            "canonical_name_basis": "highest_observed_count_then_lexical",
            "validity_intervals": [interval],
            "scope": "company_relative",
            "scope_basis": "owner_ratifiable_default_not_firm_truth",
            "ordered_scale": proposed_primary,
            "alias_mappings": proposed_aliases,
            "reviewer": None,
            "reviewed_at": None,
            "owner_reviewed_complete": False,
        },
        "unresolved_labels": unresolved,
        "conflict_census": conflict_census,
        "bulk_ratification_eligible": not firm_reasons,
        "exception_reasons": firm_reasons,
        "owner_reviewed_complete": False,
        "availability_authority_created": False,
        "registry_authority_created": False,
        "production_authority": False,
    }


def _require_non_authorizing_proposal(
    proposal: object,
    *,
    expected_counts: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """Recompute census and reject authority hidden anywhere in the proposal."""

    if type(proposal) is not dict:
        raise FirmOntologyProposalError("proposal document changed type")

    pending: list[object] = [proposal]
    while pending:
        current = pending.pop()
        if type(current) is dict:
            for key, value in current.items():
                if key in _FALSE_FIELDS and value is not False:
                    raise FirmOntologyProposalError(
                        "proposal nested non-authority field changed"
                    )
                if type(value) in {dict, list}:
                    pending.append(value)
        elif type(current) is list:
            pending.extend(
                value for value in current if type(value) in {dict, list}
            )

    firms = proposal.get("firms")
    if type(firms) is not list or len(firms) != EXPECTED_FIRM_COUNT:
        raise FirmOntologyProposalError(
            "proposal requires the exact 74-firm output census"
        )
    seen_ids: set[str] = set()
    bulk_count = 0
    primary_count = 0
    alias_count = 0
    unresolved_count = 0
    expected_exceptions: list[dict[str, object]] = []
    for ordinal, firm in enumerate(firms, start=1):
        if type(firm) is not dict:
            raise FirmOntologyProposalError("proposal firm row changed type")
        firm_id = firm.get("provider_firm_id")
        defaults = firm.get("proposed_defaults")
        unresolved = firm.get("unresolved_labels")
        eligible = firm.get("bulk_ratification_eligible")
        reasons = firm.get("exception_reasons")
        if (
            type(firm_id) is not str
            or not firm_id
            or firm_id in seen_ids
            or firm.get("ranking_ordinal") != ordinal
            or type(defaults) is not dict
            or defaults.get("owner_reviewed_complete") is not False
            or type(defaults.get("ordered_scale")) is not list
            or type(defaults.get("alias_mappings")) is not list
            or type(unresolved) is not list
            or type(eligible) is not bool
            or type(reasons) is not list
            or any(type(reason) is not str or not reason for reason in reasons)
        ):
            raise FirmOntologyProposalError(
                "proposal firm census or non-authority fields changed"
            )
        seen_ids.add(firm_id)
        if eligible is not (not reasons):
            raise FirmOntologyProposalError(
                "proposal bulk-ratification eligibility changed"
            )
        bulk_count += int(eligible)
        primary_count += len(defaults["ordered_scale"])
        alias_count += len(defaults["alias_mappings"])
        unresolved_count += len(unresolved)
        for item in defaults["ordered_scale"] + defaults["alias_mappings"]:
            if (
                type(item) is not dict
                or item.get("owner_confirmation_required") is not True
                or type(item.get("mapping_evidence")) is not dict
                or item["mapping_evidence"].get("owner_confirmation_required")
                is not True
                or item["mapping_evidence"].get("availability_time_proposed")
                is not None
            ):
                raise FirmOntologyProposalError(
                    "proposal mapping remains insufficiently owner-bound"
                )
        for item in unresolved:
            if (
                type(item) is not dict
                or item.get("proposed_rank") is not None
                or item.get("owner_adjudication_required") is not True
                or type(item.get("reasons")) is not list
                or not item["reasons"]
            ):
                raise FirmOntologyProposalError(
                    "proposal unresolved label was guessed or hidden"
                )
        if not eligible:
            expected_exceptions.append(
                {
                    "ranking_ordinal": ordinal,
                    "provider_firm_id": firm_id,
                    "unresolved_label_count": len(unresolved),
                    "reasons": reasons,
                }
            )
    counts = {
        "firm_count": len(firms),
        "bulk_ratification_eligible_firm_count": bulk_count,
        "exception_firm_count": len(firms) - bulk_count,
        "proposed_primary_mapping_count": primary_count,
        "proposed_alias_mapping_count": alias_count,
        "unresolved_label_count": unresolved_count,
    }
    census = proposal.get("census")
    if (
        type(census) is not dict
        or any(type(census.get(name)) is not int for name in counts)
        or any(census.get(name) != count for name, count in counts.items())
        or proposal.get("exception_census") != expected_exceptions
        or (
            expected_counts is not None
            and (
                type(expected_counts) is not dict
                or dict(expected_counts) != counts
            )
        )
    ):
        raise FirmOntologyProposalError(
            "proposal census or compact exception inventory changed"
        )
    return counts


def _compose_proposal(
    packet: PhysicalFirmOntologyReviewPacket,
    contract: GlobalBenchmarkContract,
) -> tuple[dict[str, object], dict[str, int]]:
    templates = _template_bindings(packet)
    template_by_id = dict(templates)
    proposed: list[dict[str, object]] = []
    observed = 0
    prior_id: str | None = None
    resolver_cache: dict[
        str, GlobalRatingMapping | GlobalRatingMappingRefusal
    ] = {}
    for evidence in _PINNED_EVIDENCE_ITERATOR(packet):
        observed += 1
        if observed > packet.firm_count or type(evidence) is not dict:
            raise FirmOntologyProposalError(
                "proposal evidence census or row type changed"
            )
        firm_id = evidence.get("provider_firm_id")
        if (
            type(firm_id) is not str
            or not firm_id
            or (prior_id is not None and firm_id <= prior_id)
        ):
            raise FirmOntologyProposalError(
                "proposal evidence identity is duplicated or out of order"
            )
        prior_id = firm_id
        template = template_by_id.get(firm_id)
        if template is not None:
            proposed.append(
                _propose_firm(
                    packet=packet,
                    contract=contract,
                    template=template,
                    evidence=evidence,
                    resolver_cache=resolver_cache,
                )
            )
    if (
        observed != packet.firm_count
        or len(proposed) != EXPECTED_FIRM_COUNT
        or {item["provider_firm_id"] for item in proposed} != set(template_by_id)
    ):
        raise FirmOntologyProposalError(
            "proposal did not exhaust the exact selected evidence census"
        )
    proposed.sort(key=lambda item: item["ranking_ordinal"])
    reason_counts = Counter(
        reason
        for firm in proposed
        for item in firm["unresolved_labels"]
        for reason in item["reasons"]
    )
    bulk_count = sum(item["bulk_ratification_eligible"] for item in proposed)
    primary_count = sum(
        len(item["proposed_defaults"]["ordered_scale"]) for item in proposed
    )
    alias_count = sum(
        len(item["proposed_defaults"]["alias_mappings"]) for item in proposed
    )
    unresolved_count = sum(len(item["unresolved_labels"]) for item in proposed)
    counts = {
        "firm_count": len(proposed),
        "bulk_ratification_eligible_firm_count": bulk_count,
        "exception_firm_count": len(proposed) - bulk_count,
        "proposed_primary_mapping_count": primary_count,
        "proposed_alias_mapping_count": alias_count,
        "unresolved_label_count": unresolved_count,
    }
    proposal = {
        "schema": PROPOSAL_SCHEMA,
        "proposal_id": None,
        "proposal_sha256": None,
        "source": {
            "packet_id": packet.packet_id,
            "packet_sha256": packet.packet_sha256,
            "packet_files": [item.to_record() for item in packet.files],
            "global_map_id": contract.map_id,
            "global_map_sha256": contract.map_hash,
            "mapped_alias_count": len(contract.entries),
            "measured_refusal_count": len(contract.measured_refusals),
        },
        "proposal_policy": {
            "rank_source": "frozen_global_39_alias_comparator_only",
            "rank_semantics": "compressed_contiguous_ascending_legacy_levels",
            "canonical_name": "highest_observed_count_then_lexical",
            "validity_interval": "one_open_interval_from_first_observed_event_date",
            "scope": "company_relative_owner_ratifiable_default",
            "named_ambiguous_aliases": sorted(_PINNED_AMBIGUOUS),
            "refusal_rule": "ambiguous_refused_unknown_cycle_opposite_and_tier_collapse_unresolved",
        },
        "census": {
            **counts,
            "unresolved_reason_counts": dict(sorted(reason_counts.items())),
        },
        "remaining_owner_choices": [
            "ratify_or_override_each_proposed_canonical_firm_name",
            "ratify_or_replace_each_open_validity_interval",
            "ratify_or_replace_company_relative_scope",
            "ratify_or_replace_each_compressed_rank_and_alias_classification",
            "adjudicate_every_named_ambiguous_refusal_unknown_cycle_opposite_or_tier_collapse_exception",
            "supply_final_mapping_availability_evidence_and_closure_times",
            "supply_reviewer_identity_review_time_and_optional_notes",
            "complete_independent_availability_and_registry_review_separately",
        ],
        "exception_census": [
            {
                "ranking_ordinal": firm["ranking_ordinal"],
                "provider_firm_id": firm["provider_firm_id"],
                "unresolved_label_count": len(firm["unresolved_labels"]),
                "reasons": firm["exception_reasons"],
            }
            for firm in proposed
            if not firm["bulk_ratification_eligible"]
        ],
        "firms": proposed,
        "owner_reviewed_complete": False,
        "owner_ratification_received": False,
        "availability_authority_created": False,
        "registry_authority_created": False,
        "production_authority": False,
        "provider_access": False,
        "quantconnect_access": False,
        "credential_access": False,
        "outcome_access": False,
        "result_access": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    _require_non_authorizing_proposal(proposal, expected_counts=counts)
    digest = _sha_record(proposal)
    proposal["proposal_id"] = f"arv2-firm-ontology-proposal-{digest[:24]}"
    proposal["proposal_sha256"] = digest
    return proposal, counts


def _identity(path: Path, *, directory: bool) -> _FileIdentity:
    try:
        value = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise FirmOntologyProposalError("proposal private path is unavailable") from exc
    expected = stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode)
    mode = 0o700 if directory else 0o600
    if (
        not expected
        or stat.S_IMODE(value.st_mode) != mode
        or (not directory and value.st_nlink != 1)
        or (hasattr(os, "getuid") and value.st_uid != os.getuid())
    ):
        raise FirmOntologyProposalError(
            "proposal output must remain owner-only regular storage"
        )
    return _FileIdentity(
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_uid,
        stat.S_IMODE(value.st_mode),
        value.st_nlink,
    )


def _write_private(path: Path, payload: bytes) -> _FileIdentity:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, 0o600)
    created = os.fstat(descriptor)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise FirmOntologyProposalError("proposal private writer stalled")
            view = view[written:]
        os.fsync(descriptor)
    except BaseException as exc:
        os.close(descriptor)
        descriptor = -1
        try:
            named = path.stat(follow_symlinks=False)
            if (
                stat.S_ISREG(named.st_mode)
                and (named.st_dev, named.st_ino) == (created.st_dev, created.st_ino)
                and named.st_nlink == 1
                and stat.S_IMODE(named.st_mode) == 0o600
                and (
                    not hasattr(os, "getuid") or named.st_uid == os.getuid()
                )
            ):
                path.unlink()
        except OSError:
            pass
        if isinstance(exc, FirmOntologyProposalError):
            raise
        if isinstance(exc, OSError):
            raise FirmOntologyProposalError(
                "proposal private writer failed"
            ) from exc
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return _identity(path, directory=False)


def _read_private(path: Path, expected: _FileIdentity) -> bytes:
    before = _identity(path, directory=False)
    if before != expected or before.size > MAX_PROPOSAL_BYTES:
        raise FirmOntologyProposalError("proposal output identity changed")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        payload = bytearray()
        while len(payload) <= MAX_PROPOSAL_BYTES:
            chunk = os.read(
                descriptor, min(1024 * 1024, MAX_PROPOSAL_BYTES + 1 - len(payload))
            )
            if not chunk:
                break
            payload.extend(chunk)
        opened = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = _identity(path, directory=False)
    if (
        len(payload) > MAX_PROPOSAL_BYTES
        or (opened.st_dev, opened.st_ino, opened.st_size)
        != (before.device, before.inode, before.size)
        or after != before
    ):
        raise FirmOntologyProposalError("proposal output changed while read")
    return bytes(payload)


_PINNED_BUILD_HELPERS = tuple(globals()[name] for name in _BUILD_HELPER_NAMES)


def build_firm_ontology_proposal(
    *,
    review_packet: PhysicalFirmOntologyReviewPacket,
    output_root: Path,
) -> FirmOntologyProposalArtifact:
    """Write one private owner-ratifiable proposal without review authority."""

    _require_dependencies()
    if type(review_packet) is not _PINNED_PACKET_TYPE:
        raise FirmOntologyProposalError("proposal requires exact packet authority")
    try:
        packet = _PINNED_PACKET_REQUIRE(review_packet)
    except packet_module.PhysicalFirmOntologyReviewPacketError as exc:
        raise FirmOntologyProposalError("proposal packet did not authenticate") from exc
    if (
        packet.adjudication_firm_count != EXPECTED_FIRM_COUNT
        or packet.ranked_firm_count < EXPECTED_FIRM_COUNT
    ):
        raise FirmOntologyProposalError("proposal requires exactly 74 selected firms")
    contract = _load_global_map()
    proposal, counts = _compose_proposal(packet, contract)
    _PINNED_PACKET_REQUIRE(packet)
    _PINNED_GLOBAL_REQUIRE(contract)
    payload = _canonical(proposal)
    if len(payload) > MAX_PROPOSAL_BYTES:
        raise FirmOntologyProposalCapacityError(
            "firm-ontology proposal exceeds its fixed byte bound"
        )
    if (
        type(output_root) is not _PATH_TYPE
        or not output_root.is_absolute()
        or ".." in output_root.parts
        or output_root != Path(os.path.abspath(output_root))
        or output_root.exists()
        or output_root.is_symlink()
    ):
        raise FirmOntologyProposalError(
            "proposal output root must be a fresh exact absolute Path"
        )
    output_root.mkdir(mode=0o700)
    _identity(output_root, directory=True)
    path = output_root / f"{proposal['proposal_id']}.json"
    try:
        identity = _write_private(path, payload)
    except BaseException:
        try:
            output_root.rmdir()
        except OSError:
            pass
        raise
    values: dict[str, object] = {
        "schema": PROPOSAL_SCHEMA,
        "proposal_id": proposal["proposal_id"],
        "proposal_sha256": proposal["proposal_sha256"],
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "byte_count": len(payload),
        "path": path,
        "packet_id": packet.packet_id,
        "packet_sha256": packet.packet_sha256,
        "global_map_id": contract.map_id,
        "global_map_sha256": contract.map_hash,
        **counts,
        **{name: False for name in _FALSE_FIELDS},
    }
    value = object.__new__(FirmOntologyProposalArtifact)
    if set(values) != {field.name for field in dataclasses.fields(value)}:
        raise FirmOntologyProposalError("proposal artifact field inventory changed")
    for name, item in values.items():
        object.__setattr__(value, name, item)
    key = id(value)
    reference = weakref.ref(value, lambda ref, identity=key: _forget(identity, ref))
    with _AUTHORITY_LOCK:
        _AUTHORITIES[key] = (reference, _fingerprint(value), identity, os.getpid())
    return require_firm_ontology_proposal(value)


def require_firm_ontology_proposal(
    value: FirmOntologyProposalArtifact,
) -> FirmOntologyProposalArtifact:
    """Reauthenticate process authority and immutable non-authorizing bytes."""

    _require_dependencies()
    current_pid = os.getpid()
    if type(value) is not FirmOntologyProposalArtifact or current_pid != _AUTHORITY_PID:
        raise FirmOntologyProposalError("proposal is not current process authority")
    with _AUTHORITY_LOCK:
        authority = _AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or authority[1] != _fingerprint(value)
        or authority[3] != current_pid
        or any(getattr(value, name) is not False for name in _FALSE_FIELDS)
    ):
        raise FirmOntologyProposalError("proposal is not current builder authority")
    payload = _read_private(value.path, authority[2])
    if (
        len(payload) != value.byte_count
        or hashlib.sha256(payload).hexdigest() != value.payload_sha256
    ):
        raise FirmOntologyProposalError("proposal output content changed")
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise FirmOntologyProposalError("proposal output is not strict JSON") from exc
    if (
        type(raw) is not dict
        or _canonical(raw) != payload
        or raw.get("schema") != PROPOSAL_SCHEMA
        or raw.get("proposal_id") != value.proposal_id
        or raw.get("proposal_sha256") != value.proposal_sha256
    ):
        raise FirmOntologyProposalError("proposal output authority fields changed")
    counts = _require_non_authorizing_proposal(raw)
    source = raw.get("source")
    if (
        type(source) is not dict
        or source.get("packet_id") != value.packet_id
        or source.get("packet_sha256") != value.packet_sha256
        or source.get("global_map_id") != value.global_map_id
        or source.get("global_map_sha256") != value.global_map_sha256
        or any(getattr(value, name) != count for name, count in counts.items())
    ):
        raise FirmOntologyProposalError(
            "proposal source binding or recomputed census changed"
        )
    seed = dict(raw)
    seed["proposal_id"] = None
    seed["proposal_sha256"] = None
    if (
        hashlib.sha256(_canonical(seed)).hexdigest() != value.proposal_sha256
        or raw["proposal_id"]
        != f"arv2-firm-ontology-proposal-{value.proposal_sha256[:24]}"
    ):
        raise FirmOntologyProposalError("proposal content address changed")
    return value


def iter_firm_ontology_proposal_firms(
    value: FirmOntologyProposalArtifact,
) -> Iterator[dict[str, object]]:
    artifact = require_firm_ontology_proposal(value)
    payload = _read_private(artifact.path, _AUTHORITIES[id(artifact)][2])
    raw = json.loads(payload.decode("utf-8"))
    firms = raw.get("firms")
    if type(firms) is not list or len(firms) != artifact.firm_count:
        raise FirmOntologyProposalError("proposal firm census changed")
    for item in firms:
        if type(item) is not dict:
            raise FirmOntologyProposalError("proposal firm row changed type")
        yield item
    require_firm_ontology_proposal(artifact)


__all__ = [
    "AMBIGUOUS_GLOBAL_ALIASES",
    "EXPECTED_FIRM_COUNT",
    "FirmOntologyProposalArtifact",
    "FirmOntologyProposalCapacityError",
    "FirmOntologyProposalError",
    "NON_AUTHORITY_FIELDS",
    "PROPOSAL_SCHEMA",
    "build_firm_ontology_proposal",
    "iter_firm_ontology_proposal_firms",
    "require_firm_ontology_proposal",
]
