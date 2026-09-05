"""Outcome-free four-family multiplicity overlay for Analyst Revisions V2.

The owner replaced the earlier three-lane allocation with four permanent
strategy-selection slots on 2026-08-30.  This additive overlay authenticates
that correction without rewriting any accepted ancestor.  It grants no data,
outcome, look-spend, QuantConnect, deployment, or order authority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
import weakref
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .qc_first_plan import (
    QcFirstPlanError,
    QcFirstStudyPlan,
    load_qc_first_study_plan,
)


class FourFamilyMultiplicityError(ValueError):
    """The overlay, its ancestry, or its claimed effective policy is invalid."""


SCHEMA = "arv2-four-family-multiplicity-overlay-structural-v1"
STATUS = "owner_approved_refreeze_frozen_outcome_free_pending_independent_review"
AUTHORITY = (
    "multiplicity_policy_only_no_source_outcome_look_qc_deployment_or_order_authority"
)
ID_PREFIX = "arv2-four-family-multiplicity-"

STRATEGY_PDF_SHA256 = (
    "eae7b9954aaf94212108505c52e31a558facd744967fd2526040d5147c616193"
)
QC_PLAN_ID = "arv2-qc-first-plan-36e455e72b8750fe"
QC_PLAN_HASH = (
    "36e455e72b8750fe3f34773382870e10e62f3f40b5392ae587690bda081b85dc"
)
QC_PLAN_ARTIFACT_SHA256 = (
    "8339238dd5ce32ed7b351aab2662fb408cc7d9a3c62ff89bf8b1d14f20acd081"
)
QC_BASE_FILENAME = "arv2_round0.draft.json"
QC_BASE_ID = "arv2-round0-candidate-8d13a0a4577df322"
QC_BASE_HASH = (
    "8d13a0a4577df3223c96c4c11722457e059b4ade63f578ab860ce7364494e847"
)
QC_BASE_ARTIFACT_SHA256 = (
    "b40a76f5f2f7726f328f1e444a41ecb0670234055a7c9c7245a26ffab601af2f"
)
ZERO_LOOK_AUTHORITY_ARTIFACT_SHA256 = (
    "819cb514dfcefd770bd1c0113cfa2484f521ac6dda0c0a36e98f977903ad5990"
)
OVERLAY_ARTIFACT_SHA256 = (
    "2e9f390ec54f01e6635b67972711c38212a5f853489e16c1de2a508212278648"
)

FIXED_LANE_IDS = (
    "analyst-revisions-v2",
    "insider-buying",
    "short-interest",
    "target-price-revisions",
)
ANALYST_LANE_ID = "analyst-revisions-v2"
ANALYST_FAMILY_ID = "arv2-rating-only-v2-qc-first"
ANALYST_LOOK_ID = "arv2-look-etf-paper-prospective-001"

SHARED_FAMILY_ALPHA = {"numerator": 1, "denominator": 20}
PERMANENT_LANE_ALPHA = {"numerator": 1, "denominator": 80}
SUPERSEDED_ANALYST_ALPHA = {"numerator": 1, "denominator": 60}

SUPERSEDED_PARENT_PATHS = (
    "multiplicity_contract.three_lane_correction_factor",
    "multiplicity_contract.prospective_permanent_look_alpha",
    "multiplicity_contract.correction",
    "prospective_paper_contract.power_plan_required_fields.two_sided_alpha_one_over_60",
    "prospective_paper_contract.alpha_commitment_timing.sole_one_over_60",
    "inheritance_contract.inherited_cell_ids.three_lane_selection_correction",
)

EXTERNAL_BINDINGS = MappingProxyType(
    {
        "independent_review_commit": None,
        "counter_review_commit": None,
        "cross_lane_review_completion_receipt": None,
        "external_append_only_look_authority_id": None,
        "external_zero_observation_receipt": None,
        "look_spend_receipt_id": None,
        "source_rights_receipt_id": None,
        "dataset_id": None,
        "outcome_artifact_sha256": None,
        "qc_project_id": None,
        "qc_run_id": None,
        "evaluation_receipt_id": None,
        "paper_epoch_id": None,
        "funded_live_authority_id": None,
    }
)
CAPABILITIES = MappingProxyType(
    {
        "source_access": False,
        "outcome_access": False,
        "confirmatory_look_registration": False,
        "confirmatory_look_commitment": False,
        "confirmatory_look_spend": False,
        "qc_upload": False,
        "qc_compile": False,
        "qc_launch": False,
        "result_disposition": False,
        "paper_deployment": False,
        "funded_deployment": False,
        "orders": False,
    }
)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise FourFamilyMultiplicityError("noncanonical JSON value") from exc


def _render(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise FourFamilyMultiplicityError("noncanonical JSON value") from exc


def _content_identity(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(raw)
    value["overlay_id"] = None
    value["overlay_hash"] = None
    digest = hashlib.sha256(_canonical(value)).hexdigest()
    value["overlay_hash"] = digest
    value["overlay_id"] = f"{ID_PREFIX}{digest[:16]}"
    return value


def _binding(
    *, artifact_id: str, content_sha256: str, artifact_sha256: str
) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "content_sha256": content_sha256,
        "artifact_sha256": artifact_sha256,
    }


def _overlay_document() -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "overlay_id": None,
        "overlay_hash": None,
        "owner_direction": {
            "decision": "2026-08-30_four_named_strategy_selection_lanes",
            "scope": (
                "shared_selection_accounting_only_lane_families_epochs_and_"
                "look_inventories_remain_distinct"
            ),
            "effective_policy_requires_this_overlay": True,
            "missing_or_unauthenticated_overlay": "REFUSED_no_fallback_to_three_lane_policy",
        },
        "bound_ancestry": {
            "strategy_pdf_sha256": STRATEGY_PDF_SHA256,
            "superseded_qc_base": _binding(
                artifact_id=QC_BASE_ID,
                content_sha256=QC_BASE_HASH,
                artifact_sha256=QC_BASE_ARTIFACT_SHA256,
            ),
            "qc_first_plan": _binding(
                artifact_id=QC_PLAN_ID,
                content_sha256=QC_PLAN_HASH,
                artifact_sha256=QC_PLAN_ARTIFACT_SHA256,
            ),
        },
        "shared_family_contract": {
            "fixed_lane_ids": list(FIXED_LANE_IDS),
            "fixed_lane_count": 4,
            "two_sided_family_wise_alpha": dict(SHARED_FAMILY_ALPHA),
            "permanent_maximum_per_lane": dict(PERMANENT_LANE_ALPHA),
            "allocation": "fixed_equal_bonferroni_across_four_permanent_lane_slots",
            "lane_level_family_ids_look_budgets_and_evidence_epochs_remain_distinct": True,
            "slot_reallocation": {
                "transferable": False,
                "unused": "EXPIRES",
                "withdrawn": "EXPIRES",
                "redistribution": "PROHIBITED",
                "denominator_recomputation": "PROHIBITED",
            },
        },
        "analyst_lane_contract": {
            "assigned_lane_id": ANALYST_LANE_ID,
            "lane_family_id": ANALYST_FAMILY_ID,
            "within_lane_confirmatory_alpha_ceiling": dict(PERMANENT_LANE_ALPHA),
            "permanent_look_ids": [ANALYST_LOOK_ID],
            "confirmatory_alpha_allocations": [
                {
                    "allocation_level": "look",
                    "look_id": ANALYST_LOOK_ID,
                    "primary_cell_id": None,
                    "exact_estimand_sha256": None,
                    "cell_binding_state": (
                        "deferred_exact_cell_and_estimand_required_before_"
                        "first_observation"
                    ),
                    "two_sided_alpha": dict(PERMANENT_LANE_ALPHA),
                }
            ],
            "allocation_sum": dict(PERMANENT_LANE_ALPHA),
            "look_budget": 1,
            "current_look_state": "planned_unbound_supersession_only",
            "external_append_only_authority_required": True,
            "future_cell_or_look_policy": (
                "reviewed_successor_must_bind_or_subdivide_this_allocation_"
                "never_add_alpha"
            ),
            "effective_power_plan_alpha_field": "two_sided_alpha_one_over_80",
            "effective_alpha_commitment_timing": (
                "sole_one_over_80_allocation_becomes_irrevocably_nonreusable_"
                "at_first_accepted_observation"
            ),
            "development_evaluations_consume_confirmatory_alpha": False,
        },
        "supersession_contract": {
            "predecessor_plan_id": QC_PLAN_ID,
            "predecessor_plan_hash": QC_PLAN_HASH,
            "predecessor_policy": {
                "lane_count": 3,
                "analyst_prospective_alpha": dict(SUPERSEDED_ANALYST_ALPHA),
                "look_id": ANALYST_LOOK_ID,
                "state_at_supersession": "planned_unbound_before_period_or_epoch_freeze",
                "repository_recorded_accepted_observations": 0,
                "authorized_confirmatory_alpha_spent": False,
                "state_provenance": (
                    "owner_record_plus_repository_zero_access_gate_"
                    "without_external_zero_observation_receipt"
                ),
            },
            "superseded_parent_paths": list(SUPERSEDED_PARENT_PATHS),
            "disposition": "superseded_unspent_nonrevivable",
            "revival": "PROHIBITED",
            "fallback_without_overlay": "REFUSED",
            "ancestor_bytes_must_remain_unchanged": True,
        },
        "repository_zero_look_state": {
            "authority_id": "arv2-zero-access-no-external-authority",
            "authority_mode": "zero_access",
            "authority_entries": [],
            "authority_artifact_sha256": ZERO_LOOK_AUTHORITY_ARTIFACT_SHA256,
            "parent_paper_start": None,
            "parent_paper_end": None,
            "parent_paper_evidence_epoch_id": None,
            "parent_paper_deployment_authorized": False,
            "evidence_scope": "repository_gate_state_not_proof_of_unobserved_external_activity",
        },
        "future_composition_gate": {
            "every_outcome_bearing_successor_must_authenticate_reviewed_overlay": True,
            "all_four_lane_review_completion_receipt_required": True,
            "ARV2_4D_A_nonconfirmatory_planning_size_one_over_20_unchanged": True,
            "ARV2_4D_B_authorized_by_this_overlay": False,
            "other_independent_lineage_leaves_must_be_authenticated_separately": True,
        },
        "acyclic_lineage": {
            "edge_direction": "child_to_parent",
            "ordered_nodes": [
                {"node": "strategy_pdf", "parents": []},
                {"node": "qc_base", "parents": ["strategy_pdf"]},
                {
                    "node": "qc_first_plan",
                    "parents": ["strategy_pdf", "qc_base"],
                },
                {
                    "node": "four_family_multiplicity_overlay",
                    "parents": ["strategy_pdf", "qc_base", "qc_first_plan"],
                },
            ],
            "overlay_is_leaf": True,
            "overlay_parent_set_excludes_power_protocol": True,
            "power_protocol_relationship_not_bound_by_this_artifact": True,
            "accepted_ancestor_nodes_and_edges_unchanged": True,
        },
        "external_bindings": dict(EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
    }
    return _content_identity(raw)


def _reject_float(value: str) -> None:
    raise FourFamilyMultiplicityError(f"binary floating-point is forbidden: {value}")


def _reject_constant(value: str) -> None:
    raise FourFamilyMultiplicityError(f"non-finite JSON is forbidden: {value}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FourFamilyMultiplicityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _is_link_like(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(
            getattr(path, "is_junction", lambda: False)()
        )
    except OSError:
        return True


def _read_stable_regular(path: Path, name: str) -> tuple[Path, bytes]:
    candidate = Path(path)
    absolute = candidate.absolute()
    if any(_is_link_like(item) for item in (absolute, *absolute.parents)):
        raise FourFamilyMultiplicityError(f"{name} must not traverse a link")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise FourFamilyMultiplicityError(f"{name} is unavailable") from exc
    if _is_link_like(resolved) or not resolved.is_file():
        raise FourFamilyMultiplicityError(f"{name} must be a regular file")
    try:
        before = resolved.stat()
        first = resolved.read_bytes()
        second = resolved.read_bytes()
        after = resolved.stat()
    except OSError as exc:
        raise FourFamilyMultiplicityError(f"{name} is unreadable") from exc
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity or first != second:
        raise FourFamilyMultiplicityError(f"{name} changed while being read")
    return resolved, first


def _revalidate(path: Path, payload: bytes, name: str) -> None:
    if _is_link_like(path) or not path.is_file():
        raise FourFamilyMultiplicityError(f"{name} changed or disappeared")
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise FourFamilyMultiplicityError(f"{name} changed or disappeared") from exc
    if current != payload:
        raise FourFamilyMultiplicityError(f"{name} changed after authentication")


def _parse_artifact(payload: bytes, name: str) -> dict[str, Any]:
    if payload.startswith(
        (
            b"\xef\xbb\xbf",
            b"\xff\xfe",
            b"\xfe\xff",
            b"\xff\xfe\x00\x00",
            b"\x00\x00\xfe\xff",
        )
    ):
        raise FourFamilyMultiplicityError(f"{name} must not contain a BOM")
    try:
        raw = json.loads(
            payload.decode("utf-8", errors="strict"),
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_object,
        )
    except UnicodeDecodeError as exc:
        raise FourFamilyMultiplicityError(f"{name} is not strict UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise FourFamilyMultiplicityError(f"{name} is invalid JSON") from exc
    if type(raw) is not dict:
        raise FourFamilyMultiplicityError(f"{name} must be a JSON object")
    if _render(raw) != payload:
        raise FourFamilyMultiplicityError(
            f"{name} bytes are not canonical sorted UTF-8 JSON"
        )
    return raw


def _validate_content_identity(raw: Mapping[str, Any]) -> None:
    declared_hash = raw.get("overlay_hash")
    if (
        type(declared_hash) is not str
        or len(declared_hash) != 64
        or any(character not in "0123456789abcdef" for character in declared_hash)
    ):
        raise FourFamilyMultiplicityError("overlay content hash is invalid")
    payload = dict(raw)
    payload["overlay_id"] = None
    payload["overlay_hash"] = None
    actual = hashlib.sha256(_canonical(payload)).hexdigest()
    if declared_hash != actual:
        raise FourFamilyMultiplicityError("overlay content hash mismatch")
    if raw.get("overlay_id") != f"{ID_PREFIX}{actual[:16]}":
        raise FourFamilyMultiplicityError("overlay ID is not content-derived")


def _require_exact(actual: object, expected: object, name: str) -> None:
    if (
        type(actual) is not type(expected)
        or _canonical(actual) != _canonical(expected)
    ):
        raise FourFamilyMultiplicityError(f"{name} changed from the frozen contract")


def _fraction(value: object, name: str) -> Fraction:
    if type(value) is not dict or set(value) != {"numerator", "denominator"}:
        raise FourFamilyMultiplicityError(f"{name} must be an exact rational")
    numerator = value["numerator"]
    denominator = value["denominator"]
    if (
        type(numerator) is not int
        or type(denominator) is not int
        or numerator <= 0
        or denominator <= 0
    ):
        raise FourFamilyMultiplicityError(f"{name} must be a positive rational")
    result = Fraction(numerator, denominator)
    if result.numerator != numerator or result.denominator != denominator:
        raise FourFamilyMultiplicityError(f"{name} must be reduced")
    return result


def _validate_arithmetic(raw: Mapping[str, Any]) -> None:
    shared = raw["shared_family_contract"]
    analyst = raw["analyst_lane_contract"]
    family_alpha = _fraction(
        shared["two_sided_family_wise_alpha"], "shared family alpha"
    )
    lane_alpha = _fraction(
        shared["permanent_maximum_per_lane"], "permanent lane alpha"
    )
    ceiling = _fraction(
        analyst["within_lane_confirmatory_alpha_ceiling"], "Analyst ceiling"
    )
    if tuple(shared["fixed_lane_ids"]) != FIXED_LANE_IDS:
        raise FourFamilyMultiplicityError("fixed strategy lane inventory changed")
    if (
        type(shared["fixed_lane_count"]) is not int
        or shared["fixed_lane_count"] != len(FIXED_LANE_IDS)
    ):
        raise FourFamilyMultiplicityError("fixed strategy lane count changed")
    if family_alpha != Fraction(1, 20) or lane_alpha != Fraction(1, 80):
        raise FourFamilyMultiplicityError("four-family alpha constants changed")
    if len(FIXED_LANE_IDS) * lane_alpha != family_alpha:
        raise FourFamilyMultiplicityError("four-family alpha arithmetic does not close")
    # The lane may never define its own ceiling: it is the shared slot itself.
    # Without this, a lane contract could raise its ceiling above 1/80 while
    # the shared contract still reads 1/80 once the exact-literal match is
    # relaxed by a reviewed successor.
    if ceiling != lane_alpha:
        raise FourFamilyMultiplicityError(
            "Analyst ceiling is not the shared lane slot"
        )
    allocations = analyst["confirmatory_alpha_allocations"]
    if type(allocations) is not list:
        raise FourFamilyMultiplicityError("Analyst allocations must be a list")
    allocated = sum(
        (
            _fraction(item["two_sided_alpha"], "Analyst look alpha")
            for item in allocations
        ),
        Fraction(0),
    )
    if allocated > ceiling or allocated != _fraction(
        analyst["allocation_sum"], "Analyst allocation sum"
    ):
        raise FourFamilyMultiplicityError("Analyst allocation exceeds its fixed slot")
    if tuple(item["look_id"] for item in allocations) != tuple(
        analyst["permanent_look_ids"]
    ):
        raise FourFamilyMultiplicityError("Analyst allocation inventory changed")
    look_budget = analyst["look_budget"]
    if type(look_budget) is not int or look_budget != len(
        analyst["permanent_look_ids"]
    ):
        raise FourFamilyMultiplicityError(
            "Analyst look budget does not match its look inventory"
        )


def _validate_parent_state(plan: QcFirstStudyPlan) -> None:
    multiplicity = plan.multiplicity_contract
    paper = plan.prospective_paper_contract
    historical = plan.qc_historical_contract
    if (
        plan.plan_id != QC_PLAN_ID
        or plan.plan_hash != QC_PLAN_HASH
        or plan.supersession["legacy_spec_id"] != QC_BASE_ID
        or plan.supersession["legacy_spec_hash"] != QC_BASE_HASH
        or multiplicity["three_lane_correction_factor"] != 3
        or _fraction(
            dict(multiplicity["prospective_permanent_look_alpha"]),
            "superseded Analyst alpha",
        )
        != Fraction(1, 60)
        or multiplicity["correction"]
        != "bonferroni_three_lanes_for_one_prospective_lane_look"
        or tuple(multiplicity["prospective_permanent_look_ids"])
        != (ANALYST_LOOK_ID,)
        or paper["look_id"] != ANALYST_LOOK_ID
        or paper["start"] is not None
        or paper["end"] is not None
        or paper["evidence_epoch_id"] is not None
        or paper["pre_observation_power_plan_sha256"] is not None
        or paper["deployment_authorized"] is not False
        or "two_sided_alpha_one_over_60"
        not in paper["power_plan_required_fields"]
        or not paper["alpha_commitment_timing"].startswith("sole_one_over_60_")
        or historical["stock_stage"]["confirmatory_alpha_spent"] is not False
        or historical["topology_stage"]["confirmatory_alpha_spent"] is not False
        or "three_lane_selection_correction"
        not in plan.inheritance_contract["inherited_cell_ids"]
    ):
        raise FourFamilyMultiplicityError(
            "superseded three-lane parent state cannot be authenticated"
        )


def _validate_zero_look_authority(payload: bytes) -> None:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FourFamilyMultiplicityError(
            "zero-access look authority is invalid"
        ) from exc
    expected = {
        "authority_id": "arv2-zero-access-no-external-authority",
        "authority_mode": "zero_access",
        "entries": [],
        "schema": "arv2-permanent-look-authority-v1",
    }
    _require_exact(value, expected, "zero-access look authority")


def _freeze(value: Any) -> Any:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


@dataclasses.dataclass(frozen=True, init=False)
class FourFamilyMultiplicityOverlay:
    """Loader-authenticated effective multiplicity policy with no action authority."""

    overlay_id: str
    overlay_hash: str
    definition: Mapping[str, Any]
    fixed_lane_ids: tuple[str, ...]
    _authority: object = dataclasses.field(repr=False, compare=False)

    @property
    def shared_family_alpha(self) -> Fraction:
        require_loaded_four_family_multiplicity_overlay(self)
        return Fraction(1, 20)

    @property
    def analyst_confirmatory_alpha_ceiling(self) -> Fraction:
        require_loaded_four_family_multiplicity_overlay(self)
        return Fraction(1, 80)

    @property
    def analyst_prospective_look_alpha(self) -> Fraction:
        require_loaded_four_family_multiplicity_overlay(self)
        return Fraction(1, 80)

    @property
    def grants_action_authority(self) -> bool:
        return False

    @property
    def source_access_available(self) -> bool:
        return False

    @property
    def outcome_access_available(self) -> bool:
        return False

    @property
    def look_spend_available(self) -> bool:
        return False

    @property
    def qc_action_available(self) -> bool:
        return False

    @property
    def deployment_available(self) -> bool:
        return False

    @property
    def orders_available(self) -> bool:
        return False


_LOADED_FOUR_FAMILY_MULTIPLICITY_AUTHORITY = object()
_FOUR_FAMILY_MULTIPLICITY_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[FourFamilyMultiplicityOverlay],
        Path,
        bytes,
        Path,
        bytes,
        Path,
        bytes,
        Path,
        bytes,
        tuple[object, ...],
    ],
] = {}
_FOUR_FAMILY_MULTIPLICITY_AUTHORITIES_LOCK = threading.RLock()


def _fingerprint_value(value: object) -> object:
    if type(value) is MappingProxyType:
        pairs = []
        for key, item in value.items():
            if type(key) is not str:
                raise FourFamilyMultiplicityError("overlay contains a noncanonical key")
            pairs.append((key, _fingerprint_value(item)))
        return ("mapping", tuple(sorted(pairs)))
    if type(value) is tuple:
        return ("tuple", tuple(_fingerprint_value(item) for item in value))
    if type(value) is str:
        return ("str", value)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", value)
    if value is None:
        return ("none", None)
    raise FourFamilyMultiplicityError("overlay contains noncanonical authority state")


def _overlay_fingerprint(
    overlay: FourFamilyMultiplicityOverlay,
) -> tuple[object, ...]:
    if type(overlay.overlay_id) is not str or type(overlay.overlay_hash) is not str:
        raise FourFamilyMultiplicityError("overlay identity fields changed type")
    if type(overlay.fixed_lane_ids) is not tuple or any(
        type(item) is not str for item in overlay.fixed_lane_ids
    ):
        raise FourFamilyMultiplicityError("overlay lane inventory changed type")
    return (
        overlay.overlay_id,
        overlay.overlay_hash,
        overlay.fixed_lane_ids,
        _fingerprint_value(overlay.definition),
    )


def _forget_authority(
    identity: int, reference: weakref.ReferenceType[FourFamilyMultiplicityOverlay]
) -> None:
    with _FOUR_FAMILY_MULTIPLICITY_AUTHORITIES_LOCK:
        current = _FOUR_FAMILY_MULTIPLICITY_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _FOUR_FAMILY_MULTIPLICITY_AUTHORITIES.pop(identity, None)


def load_four_family_multiplicity_overlay(
    overlay_path: Path,
    *,
    look_authority_path: Path,
    qc_first_plan_path: Path,
) -> FourFamilyMultiplicityOverlay:
    """Authenticate the parallel-leaf overlay and its exact QC ancestry."""
    resolved, payload = _read_stable_regular(overlay_path, "multiplicity overlay")
    if hashlib.sha256(payload).hexdigest() != OVERLAY_ARTIFACT_SHA256:
        raise FourFamilyMultiplicityError("multiplicity overlay artifact bytes changed")
    raw = _parse_artifact(payload, "multiplicity overlay")
    _validate_content_identity(raw)
    _require_exact(raw, _overlay_document(), "multiplicity overlay")
    _validate_arithmetic(raw)

    qc_resolved, qc_payload = _read_stable_regular(qc_first_plan_path, "QC-first plan")
    base_resolved, base_payload = _read_stable_regular(
        qc_resolved.with_name(QC_BASE_FILENAME), "superseded QC base"
    )
    look_resolved, look_payload = _read_stable_regular(
        look_authority_path, "zero-access look authority"
    )
    if hashlib.sha256(qc_payload).hexdigest() != QC_PLAN_ARTIFACT_SHA256:
        raise FourFamilyMultiplicityError("QC-first parent bytes changed")
    if hashlib.sha256(base_payload).hexdigest() != QC_BASE_ARTIFACT_SHA256:
        raise FourFamilyMultiplicityError("superseded QC base bytes changed")
    if hashlib.sha256(look_payload).hexdigest() != ZERO_LOOK_AUTHORITY_ARTIFACT_SHA256:
        raise FourFamilyMultiplicityError("zero-access look authority bytes changed")
    _validate_zero_look_authority(look_payload)

    try:
        plan = load_qc_first_study_plan(qc_first_plan_path)
    except QcFirstPlanError as exc:
        raise FourFamilyMultiplicityError("multiplicity ancestry failed") from exc
    _validate_parent_state(plan)

    for path, original, name in (
        (qc_resolved, qc_payload, "QC-first plan"),
        (base_resolved, base_payload, "superseded QC base"),
        (look_resolved, look_payload, "zero-access look authority"),
        (resolved, payload, "multiplicity overlay"),
    ):
        _revalidate(path, original, name)
    _revalidate(resolved, payload, "multiplicity overlay")

    value = object.__new__(FourFamilyMultiplicityOverlay)
    for name, item in {
        "overlay_id": raw["overlay_id"],
        "overlay_hash": raw["overlay_hash"],
        "definition": _freeze(raw),
        "fixed_lane_ids": FIXED_LANE_IDS,
        "_authority": _LOADED_FOUR_FAMILY_MULTIPLICITY_AUTHORITY,
    }.items():
        object.__setattr__(value, name, item)
    fingerprint = _overlay_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget_authority(key, ref))
    with _FOUR_FAMILY_MULTIPLICITY_AUTHORITIES_LOCK:
        _FOUR_FAMILY_MULTIPLICITY_AUTHORITIES[identity] = (
            reference,
            resolved,
            payload,
            qc_resolved,
            qc_payload,
            base_resolved,
            base_payload,
            look_resolved,
            look_payload,
            fingerprint,
        )
    return value


def require_loaded_four_family_multiplicity_overlay(
    overlay: FourFamilyMultiplicityOverlay | None,
) -> FourFamilyMultiplicityOverlay:
    """Resolve the effective 1/80 policy; absence never falls back to 1/60."""
    if (
        type(overlay) is not FourFamilyMultiplicityOverlay
        or getattr(overlay, "_authority", None)
        is not _LOADED_FOUR_FAMILY_MULTIPLICITY_AUTHORITY
    ):
        raise FourFamilyMultiplicityError(
            "effective four-family multiplicity requires the authenticated overlay"
        )
    with _FOUR_FAMILY_MULTIPLICITY_AUTHORITIES_LOCK:
        authority = _FOUR_FAMILY_MULTIPLICITY_AUTHORITIES.get(id(overlay))
    if authority is None or authority[0]() is not overlay:
        raise FourFamilyMultiplicityError("multiplicity overlay authority is absent")
    if _overlay_fingerprint(overlay) != authority[9]:
        raise FourFamilyMultiplicityError("multiplicity overlay changed after loading")
    _revalidate(authority[1], authority[2], "multiplicity overlay")
    _revalidate(authority[3], authority[4], "QC-first plan")
    _revalidate(authority[5], authority[6], "superseded QC base")
    _revalidate(authority[7], authority[8], "zero-access look authority")
    _revalidate(authority[1], authority[2], "multiplicity overlay")
    return overlay


def render_expected_four_family_multiplicity_overlay() -> str:
    """Render the one canonical checked-in structural artifact."""
    return _render(_overlay_document()).decode("utf-8")
