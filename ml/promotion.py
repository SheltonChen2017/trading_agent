"""ML-LR-7 immutable, read-only promotion-review dossier.

The dossier can explain eligibility and enumerate blockers.  It intentionally
has no registry dependency and no transition method; even a fully satisfied
technical dossier retains the separate-owner-review blocker.
"""
from __future__ import annotations

import dataclasses
import math
import re
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ml.hashing import hash_payload

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_EVIDENCE = (
    "discovery_specification",
    "discovery_report",
    "confirmation_specification",
    "confirmation_report",
    "dataset_manifest",
    "availability_manifest",
    "universe_manifest",
    "model_manifest",
    "model_artifact",
    "economic_simulation",
    "shadow_monitoring_report",
)


class PromotionDossierError(ValueError):
    """A dossier would be mutable, internally inconsistent, or misleading."""


def _freeze(value: Any, path: str = "value") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PromotionDossierError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PromotionDossierError(f"{path} contains a non-string key")
            result[key] = _freeze(item, f"{path}.{key}")
        return MappingProxyType(result)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item, f"{path}[{index}]") for index, item in enumerate(value))
    raise PromotionDossierError(
        f"{path} contains unsupported {type(value).__name__}"
    )


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PromotionDossierError(f"{name} must be a non-empty string")
    return value


def _timestamp(value: Any, name: str) -> str:
    text = _required_text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PromotionDossierError(f"{name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PromotionDossierError(f"{name} must be timezone-aware")
    return text


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PromotionDossierError(f"{name} must be a lowercase SHA-256 digest")
    return value


@dataclasses.dataclass(frozen=True)
class PromotionDossier:
    dossier_id: str
    generated_at: str
    task: str
    model_key: str
    evidence_epoch: str
    evidence: Mapping[str, Any]
    review_gate_results: Mapping[str, Any]
    known_limitations: tuple[str, ...]
    unresolved_incidents: tuple[Mapping[str, Any], ...]
    proposed_adapter_scope: Mapping[str, Any]
    promotion_blockers: tuple[str, ...]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.schema_version != "1.0":
            raise PromotionDossierError("unsupported dossier schema_version")
        for name in ("dossier_id", "task", "model_key", "evidence_epoch"):
            _required_text(getattr(self, name), name)
        _timestamp(self.generated_at, "generated_at")
        if not isinstance(self.evidence, Mapping):
            raise PromotionDossierError("evidence must be an object")
        missing_keys = set(REQUIRED_EVIDENCE) - set(self.evidence)
        if missing_keys:
            raise PromotionDossierError(
                f"evidence inventory omits required keys: {sorted(missing_keys)}"
            )
        for name, item in self.evidence.items():
            if item is None:
                continue
            if not isinstance(item, Mapping):
                raise PromotionDossierError(f"evidence.{name} must be an object or null")
            _sha(item.get("sha256"), f"evidence.{name}.sha256")
            if "result" not in item:
                raise PromotionDossierError(f"evidence.{name} must include result")
        limitations = tuple(self.known_limitations)
        if any(not isinstance(item, str) or not item.strip() for item in limitations):
            raise PromotionDossierError("known_limitations must contain non-empty strings")
        blockers = tuple(dict.fromkeys(self.promotion_blockers))
        if any(not isinstance(item, str) or not item.strip() for item in blockers):
            raise PromotionDossierError("promotion_blockers must contain non-empty strings")
        if "separate_owner_promotion_review_required" not in blockers:
            raise PromotionDossierError(
                "every dossier must retain separate_owner_promotion_review_required"
            )
        incidents = tuple(self.unresolved_incidents)
        if any(not isinstance(item, Mapping) for item in incidents):
            raise PromotionDossierError("unresolved_incidents must contain objects")
        if not isinstance(self.review_gate_results, Mapping):
            raise PromotionDossierError("review_gate_results must be an object")
        if not isinstance(self.proposed_adapter_scope, Mapping):
            raise PromotionDossierError("proposed_adapter_scope must be an object")
        object.__setattr__(self, "evidence", _freeze(self.evidence, "evidence"))
        object.__setattr__(self, "review_gate_results", _freeze(self.review_gate_results, "review_gate_results"))
        object.__setattr__(self, "known_limitations", limitations)
        object.__setattr__(self, "unresolved_incidents", _freeze(incidents, "unresolved_incidents"))
        object.__setattr__(self, "proposed_adapter_scope", _freeze(self.proposed_adapter_scope, "proposed_adapter_scope"))
        object.__setattr__(self, "promotion_blockers", blockers)

    @property
    def production_authoritative(self) -> bool:
        return False

    @property
    def eligible_for_separate_owner_review(self) -> bool:
        return self.promotion_blockers == (
            "separate_owner_promotion_review_required",
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "dossier_id": self.dossier_id,
            "generated_at": self.generated_at,
            "task": self.task,
            "model_key": self.model_key,
            "evidence_epoch": self.evidence_epoch,
            "evidence": _plain(self.evidence),
            "review_gate_results": _plain(self.review_gate_results),
            "known_limitations": list(self.known_limitations),
            "unresolved_incidents": _plain(self.unresolved_incidents),
            "proposed_adapter_scope": _plain(self.proposed_adapter_scope),
            "promotion_blockers": list(self.promotion_blockers),
            "eligible_for_separate_owner_review": self.eligible_for_separate_owner_review,
            "production_authoritative": False,
        }
        payload["dossier_hash"] = hash_payload(payload)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PromotionDossier":
        if not isinstance(payload, Mapping):
            raise PromotionDossierError("dossier payload must be an object")
        if payload.get("production_authoritative", False) is not False:
            raise PromotionDossierError("production_authoritative must be false")
        allowed = {field.name for field in dataclasses.fields(cls)} | {
            "production_authoritative",
            "eligible_for_separate_owner_review",
            "dossier_hash",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise PromotionDossierError(f"unknown dossier fields: {sorted(unknown)}")
        claimed_hash = payload.get("dossier_hash")
        if claimed_hash is None:
            raise PromotionDossierError("serialized dossier must include dossier_hash")
        without_hash = {key: value for key, value in payload.items() if key != "dossier_hash"}
        if hash_payload(without_hash) != claimed_hash:
            raise PromotionDossierError("dossier_hash does not match dossier content")
        kwargs = {
            key: value
            for key, value in payload.items()
            if key not in {"production_authoritative", "eligible_for_separate_owner_review", "dossier_hash"}
        }
        for name in ("known_limitations", "unresolved_incidents", "promotion_blockers"):
            if name in kwargs:
                kwargs[name] = tuple(kwargs[name])
        try:
            restored = cls(**kwargs)
        except TypeError as exc:
            raise PromotionDossierError(f"missing dossier fields: {exc}") from exc
        if (
            payload.get("eligible_for_separate_owner_review")
            is not restored.eligible_for_separate_owner_review
        ):
            raise PromotionDossierError(
                "eligible_for_separate_owner_review is inconsistent with blockers"
            )
        return restored


def evidence_snapshot(*, sha256: str, result: Mapping[str, Any]) -> dict[str, Any]:
    """Create one hash/result pair; paths are intentionally not authoritative."""
    return {"sha256": _sha(sha256, "sha256"), "result": dict(result)}


def _artifact_payload(evidence: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    item = evidence.get(name)
    if not isinstance(item, Mapping):
        return None
    result = item.get("result")
    return result if isinstance(result, Mapping) else None


def _gate(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _coverage_manifest_complete(payload: Mapping[str, Any] | None) -> bool:
    if not payload:
        return False
    explicitly_complete = (
        payload.get("complete") is True
        or payload.get("coverage_complete") is True
    )
    unresolved = payload.get("unresolved_count", payload.get("failure_count", 0))
    return (
        explicitly_complete
        and isinstance(unresolved, int)
        and not isinstance(unresolved, bool)
        and unresolved == 0
    )


def build_promotion_dossier(
    *,
    generated_at: str,
    task: str,
    model_key: str,
    evidence_epoch: str,
    evidence: Mapping[str, Any],
    known_limitations: Sequence[str],
    unresolved_incidents: Sequence[Mapping[str, Any]],
    proposed_adapter_scope: Mapping[str, Any],
) -> PromotionDossier:
    """Derive every review result and blocker from frozen evidence snapshots."""
    inventory = {name: evidence.get(name) for name in REQUIRED_EVIDENCE}
    inventory.update({name: item for name, item in evidence.items() if name not in inventory})
    blockers: list[str] = [
        f"missing_{name}" for name in REQUIRED_EVIDENCE if inventory.get(name) is None
    ]
    gates: dict[str, Any] = {}

    discovery_spec = _artifact_payload(inventory, "discovery_specification")
    discovery_report = _artifact_payload(inventory, "discovery_report")
    confirmation_spec = _artifact_payload(inventory, "confirmation_specification")
    confirmation_report = _artifact_payload(inventory, "confirmation_report")
    dataset = _artifact_payload(inventory, "dataset_manifest")
    availability = _artifact_payload(inventory, "availability_manifest")
    universe = _artifact_payload(inventory, "universe_manifest")
    model = _artifact_payload(inventory, "model_manifest")
    economics = _artifact_payload(inventory, "economic_simulation")
    monitoring = _artifact_payload(inventory, "shadow_monitoring_report")
    if monitoring and monitoring.get("evidence_epoch") != evidence_epoch:
        raise PromotionDossierError(
            "a monitoring report from a different evidence epoch cannot enter this dossier"
        )
    monitoring_hash_valid = False
    if monitoring:
        claimed_monitoring_hash = monitoring.get("report_hash")
        monitoring_without_hash = {
            key: value for key, value in monitoring.items() if key != "report_hash"
        }
        if (
            claimed_monitoring_hash is not None
            and claimed_monitoring_hash != hash_payload(monitoring_without_hash)
        ):
            raise PromotionDossierError(
                "shadow monitoring report_hash does not match its content"
            )
        monitoring_hash_valid = bool(
            isinstance(claimed_monitoring_hash, str)
            and _SHA256.fullmatch(claimed_monitoring_hash)
        )

    artifact_lineage_ok = bool(
        model
        and dataset
        and confirmation_spec
        and inventory.get("confirmation_report")
        and model.get("dataset_hash") == dataset.get("dataset_hash")
        and model.get("model_version") == hash_payload(confirmation_spec)
        and model.get("evaluation_report_hash")
        == inventory["confirmation_report"].get("sha256")
        and inventory.get("model_artifact")
        and model.get("artifact_hash") == inventory["model_artifact"].get("sha256")
    )
    gates["artifact_hash_lineage"] = _gate(
        "artifact_hash_lineage",
        artifact_lineage_ok,
        "dataset, evaluation report, model manifest, and model artifact hashes form one lineage",
    )
    if not artifact_lineage_ok:
        blockers.append("artifact_hash_lineage_unverified")

    parent_ok = False
    if discovery_spec and confirmation_spec and discovery_report:
        parent = confirmation_spec.get("confirmation")
        parent_ok = bool(
            confirmation_spec.get("mode") == "confirmation"
            and isinstance(parent, Mapping)
            and parent.get("parent_spec_hash") == hash_payload(discovery_spec)
            and parent.get("parent_report_hash") == inventory["discovery_report"]["sha256"]
            and parent.get("parent_experiment_id") == discovery_spec.get("experiment_id")
            and discovery_spec.get("mode") == "discovery"
        )
    gates["discovery_confirmation_lineage"] = _gate(
        "discovery_confirmation_lineage", parent_ok, "confirmation parent hashes bind to discovery artifacts"
    )
    if not parent_ok:
        blockers.append("discovery_confirmation_lineage_unverified")

    point_in_time = bool(dataset and dataset.get("point_in_time_data") is True)
    coverage_complete = (
        point_in_time
        and _coverage_manifest_complete(availability)
        and _coverage_manifest_complete(universe)
    )
    gates["point_in_time_and_universe_coverage"] = _gate(
        "point_in_time_and_universe_coverage",
        coverage_complete,
        "dataset is point-in-time and availability/universe manifests explicitly declare complete coverage with zero unresolved records",
    )
    if not gates["point_in_time_and_universe_coverage"]["passed"]:
        blockers.append("point_in_time_or_universe_coverage_gate_unmet")

    folds = confirmation_report.get("fold_metrics", ()) if confirmation_report else ()
    three_folds = isinstance(folds, (list, tuple)) and len(folds) >= 3
    gates["three_untouched_walk_forward_folds"] = _gate(
        "three_untouched_walk_forward_folds", three_folds, f"observed fold count={len(folds) if isinstance(folds, (list, tuple)) else 0}"
    )
    if not three_folds:
        blockers.append("fewer_than_three_untouched_walk_forward_folds")

    raw_confirmation_blockers = (
        confirmation_report.get("promotion_blockers", ())
        if confirmation_report
        else ()
    )
    confirmation_blockers = (
        raw_confirmation_blockers
        if isinstance(raw_confirmation_blockers, (list, tuple))
        else ("invalid_confirmation_promotion_blockers",)
    )
    confirmation_verdict_ok = bool(
        confirmation_report
        and confirmation_report.get("verdict") == "promising_unconfirmed"
        and not [
            item
            for item in confirmation_blockers
            if item != "separate_owner_promotion_review_required"
        ]
    )
    gates["confirmation_verdict"] = _gate(
        "confirmation_verdict",
        confirmation_verdict_ok,
        "confirmation verdict is promising_unconfirmed with no technical promotion blockers",
    )
    if not confirmation_verdict_ok:
        blockers.append("confirmation_verdict_or_blockers_unacceptable")

    aggregate = confirmation_report.get("aggregate_metrics") if confirmation_report else None
    candidate_name = str(model.get("model_id", "")).rsplit(".", 1)[-1] if model else ""
    candidate = aggregate.get(candidate_name) if isinstance(aggregate, Mapping) else None
    wins = candidate.get("folds_won") if isinstance(candidate, Mapping) else None
    if wins is None and isinstance(candidate, Mapping):
        wins = candidate.get("win_count")
    multiple_fold_wins = isinstance(wins, int) and not isinstance(wins, bool) and wins > 1
    gates["baseline_wins_in_multiple_folds"] = _gate(
        "baseline_wins_in_multiple_folds", multiple_fold_wins, f"candidate={candidate_name!r}, folds_won={wins!r}"
    )
    if not multiple_fold_wins:
        blockers.append("baseline_not_beaten_in_multiple_folds")

    uncertainty = confirmation_report.get("dependence_aware_uncertainty") if confirmation_report else None
    block_significance = candidate.get("block_significance") if isinstance(candidate, Mapping) else None
    means = [
        item.get("mean") for item in block_significance.values()
        if isinstance(item, Mapping)
    ] if isinstance(block_significance, Mapping) else []
    stable_direction = bool(means and all(isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 0 for value in means))
    alpha = uncertainty.get("bonferroni_alpha_threshold") if isinstance(uncertainty, Mapping) else None
    p_values = [
        item.get("p_value")
        for item in block_significance.values()
        if isinstance(item, Mapping)
    ] if isinstance(block_significance, Mapping) else []
    declared_lengths = (
        confirmation_spec.get("research_gate", {}).get("block_lengths", ())
        if confirmation_spec and isinstance(confirmation_spec.get("research_gate"), Mapping)
        else ()
    )
    expected_block_keys = {str(value) for value in declared_lengths}
    dependence_ok = bool(
        isinstance(uncertainty, Mapping)
        and uncertainty
        and stable_direction
        and isinstance(alpha, (int, float))
        and not isinstance(alpha, bool)
        and p_values
        and len(p_values) == len(expected_block_keys)
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and float(value) < float(alpha)
            for value in p_values
        )
        and expected_block_keys
        and set(block_significance) == expected_block_keys
    )
    gates["multiplicity_dependence_and_block_sensitivity"] = _gate(
        "multiplicity_dependence_and_block_sensitivity", dependence_ok, "multiplicity metadata exists and preregistered block lengths have stable positive direction"
    )
    if not dependence_ok:
        blockers.append("multiplicity_or_dependence_gate_unmet")

    monitoring_blockers = monitoring.get("promotion_blockers", ()) if monitoring else ()
    monitoring_ok = bool(
        monitoring
        and monitoring_hash_valid
        and monitoring.get("evidence_epoch") == evidence_epoch
        and monitoring.get("production_authoritative") is False
        and not monitoring_blockers
    )
    gates["matured_shadow_monitoring"] = _gate(
        "matured_shadow_monitoring", monitoring_ok, f"monitoring blockers={list(monitoring_blockers) if isinstance(monitoring_blockers, (list, tuple)) else 'invalid'}"
    )
    if not monitoring_ok:
        blockers.append("matured_shadow_monitoring_gate_unmet")

    economics_ok = bool(
        economics
        and economics.get("acceptable_after_costs_taxes_shared_capital") is True
        and economics.get("no_material_mandate_degradation") is True
    )
    gates["economics_and_mandate"] = _gate(
        "economics_and_mandate", economics_ok, "economics remain acceptable after costs/taxes/shared capital and mandate degradation is absent"
    )
    if not economics_ok:
        blockers.append("economics_or_mandate_gate_unmet")

    incidents_ok = not unresolved_incidents
    gates["zero_unresolved_incidents"] = _gate(
        "zero_unresolved_incidents", incidents_ok, f"unresolved incident count={len(unresolved_incidents)}"
    )
    if not incidents_ok:
        blockers.append("unresolved_incidents_present")

    scope_ok = bool(proposed_adapter_scope)
    gates["proposed_adapter_scope_declared"] = _gate(
        "proposed_adapter_scope_declared", scope_ok, "scope is descriptive only and grants no authority"
    )
    if not scope_ok:
        blockers.append("proposed_adapter_scope_missing")
    limitations_ok = bool(known_limitations)
    gates["known_limitations_declared"] = _gate(
        "known_limitations_declared",
        limitations_ok,
        f"known limitation count={len(known_limitations)}",
    )
    if not limitations_ok:
        blockers.append("known_limitations_not_declared")

    # Structural/content identities tying the shadow epoch to the selected model.
    identity_ok = bool(
        model
        and f"{model.get('model_id')}:{model.get('model_version')}" == model_key
        and monitoring
        and monitoring.get("evidence_epoch") == evidence_epoch
    )
    gates["model_epoch_identity"] = _gate(
        "model_epoch_identity", identity_ok, "model manifest key and monitoring epoch match the dossier identity"
    )
    if not identity_ok:
        blockers.append("model_or_epoch_identity_mismatch")

    blockers.extend(
        str(item) for item in monitoring_blockers
        if isinstance(item, str) and item
    )
    blockers.append("separate_owner_promotion_review_required")
    generated = _timestamp(generated_at, "generated_at")
    dossier_id = "ml-dossier-" + hash_payload(
        {
            "generated_at": generated,
            "task": task,
            "model_key": model_key,
            "evidence_epoch": evidence_epoch,
            "evidence_hashes": {
                name: item.get("sha256") if isinstance(item, Mapping) else None
                for name, item in inventory.items()
            },
        }
    )[:24]
    return PromotionDossier(
        dossier_id=dossier_id,
        generated_at=generated,
        task=task,
        model_key=model_key,
        evidence_epoch=evidence_epoch,
        evidence=inventory,
        review_gate_results=gates,
        known_limitations=tuple(known_limitations),
        unresolved_incidents=tuple(unresolved_incidents),
        proposed_adapter_scope=dict(proposed_adapter_scope),
        promotion_blockers=tuple(dict.fromkeys(blockers)),
    )
