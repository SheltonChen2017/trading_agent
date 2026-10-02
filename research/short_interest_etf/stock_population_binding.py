"""SI-2B-P1B relations between eligibility and existing structural normalization.

Rebuild the unchanged canonical SI-3A/SI-3C source, then report its cutoff,
revision selection and populations beside each SI-2B-P1A membership cohort.
Intersections are diagnostics, not a chosen normalization/ranking universe.
No eligible-universe scores, ranks, percentiles, seeds or authority are emitted.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from data.hashing import hash_payload
from research.short_interest_etf.contracts import parse_utc_timestamp
from research.short_interest_etf.stock_eligible_population import StockEligiblePopulationInventory
from research.short_interest_etf.stock_features import build_pit_stock_raw_features
from research.short_interest_etf.stock_normalization import (
    STOCK_NORMALIZATION_POLICY,
    RevisionSelectionState,
    StockNormalizationCohort,
    build_pit_stock_normalized_scores,
)


class StockPopulationBindingError(ValueError):
    """An authenticated population relationship could not be established."""


def _refuse(detail: str) -> StockPopulationBindingError:
    return StockPopulationBindingError(f"REFUSED: {detail}")


def _capture_population(
    population: StockEligiblePopulationInventory,
) -> tuple[StockEligiblePopulationInventory, dict[str, Any]]:
    if type(population) is not StockEligiblePopulationInventory:
        raise _refuse("source must be the exact StockEligiblePopulationInventory type")
    original = StockEligiblePopulationInventory.to_payload(population)
    captured = StockEligiblePopulationInventory(population.evidence)
    payload = StockEligiblePopulationInventory.to_payload(captured)
    if payload != original:
        raise _refuse("source population changed during capture")
    return captured, payload


def _relations(
    population: StockEligiblePopulationInventory,
    source: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence = population.evidence
    raw = build_pit_stock_raw_features(evidence.vintage, evidence.references)
    scores = build_pit_stock_normalized_scores(raw)
    by_event = {item.current.readiness.event_id: item for item in scores}
    cohorts: dict[str, StockNormalizationCohort] = {}
    summaries: dict[str, dict[str, Any]] = {}
    for item in scores:
        cohort = item.cohort
        settlement = cohort.settlement_date
        if settlement in cohorts:
            continue
        if (
            cohort.source_vintage_sha256 != source["source_vintage_sha256"]
            or cohort.reference_bundle_sha256 != source["reference_bundle_sha256"]
        ):
            raise _refuse("normalization source differs from eligibility source")
        cohorts[settlement] = cohort
        summaries[settlement] = {
            "normalization_cohort_sha256": hash_payload(cohort.to_payload()),
            "settlement_date": settlement,
            "release_calendar_key": cohort.release_calendar_key,
            "release_sha256": cohort.release_sha256,
            "decision_at": cohort.decision_at,
            "candidate_event_ids": sorted(row.event_id for row in cohort.candidate_members),
            "structural_peer_event_ids": sorted(row.event_id for row in cohort.eligible_members),
            "scoreable_event_ids_by_model": {
                model.value: sorted(
                    row.current.readiness.event_id for row in scores
                    if row.cohort.settlement_date == settlement
                    and any(outcome.model is model and outcome.score is not None
                            for outcome in row.outcomes)
                )
                for model in STOCK_NORMALIZATION_POLICY.models
            },
        }
    bindings = []
    for eligibility in source["cohorts"]:
        settlement = eligibility["settlement_date"]
        cohort = cohorts.get(settlement)
        if cohort is None:
            raise _refuse("eligibility cohort has no authenticated normalization release")
        summary = summaries[settlement]
        candidates = set(summary["candidate_event_ids"])
        peers = set(summary["structural_peer_event_ids"])
        scoreable = {
            model: set(events)
            for model, events in summary["scoreable_event_ids_by_model"].items()
        }
        members = []
        for member in eligibility["members"]:
            event = member["event_id"]
            normalized = by_event.get(event)
            if normalized is None:
                raise _refuse("eligibility member has no canonical normalization disposition")
            ready = normalized.current.readiness
            if (
                ready.settlement_date != settlement
                or ready.security_id != member["security_id"]
                or ready.security_identity_sha256 != member["security_identity_sha256"]
            ):
                raise _refuse("normalization event or stable identity differs from eligibility")
            selection = cohort.selection_for_event(event)
            if selection is None:
                raise _refuse("eligibility event lacks canonical revision selection")
            state, selected = selection
            members.append({
                **member,
                "revision_selection_state": state.value,
                "selected_event_id": selected,
                "structural_candidate": event in candidates,
                "structural_peer": event in peers,
                "scoreable_models": sorted(model for model, events in scoreable.items() if event in events),
            })
        eligible = set(eligibility["eligible_event_ids"])
        selected = {
            row["event_id"] for row in members
            if row["revision_selection_state"] == RevisionSelectionState.SELECTED.value
        }
        eligibility_at = parse_utc_timestamp(eligibility["evidence_cutoff_at"], "eligibility cutoff")
        normalization_at = parse_utc_timestamp(cohort.decision_at, "normalization cutoff")
        cutoff_equal = eligibility_at == normalization_at
        relation = (
            "same_open" if cutoff_equal else
            "eligibility_after_normalization" if eligibility_at > normalization_at else
            "eligibility_before_normalization"
        )
        observations = []
        if not cutoff_equal:
            observations.append("different_evidence_cutoff")
        if eligible - selected:
            observations.append("eligible_events_not_selected_at_normalization_cutoff")
        if eligible - candidates:
            observations.append("eligible_events_outside_structural_candidate_population")
        if eligible - peers:
            observations.append("eligible_events_outside_structural_peer_population")
        binding = {
            "source_cohort_sha256": eligibility["cohort_sha256"],
            "normalization_cohort_sha256": summary["normalization_cohort_sha256"],
            "settlement_date": settlement,
            "lookback_sessions": eligibility["lookback_sessions"],
            "eligibility_cutoff_at": eligibility["evidence_cutoff_at"],
            "normalization_cutoff_at": cohort.decision_at,
            "cutoff_equal": cutoff_equal,
            "cutoff_relation": relation,
            "eligible_event_ids": list(eligibility["eligible_event_ids"]),
            "refused_event_ids": list(eligibility["refused_event_ids"]),
            "eligible_selected_event_ids": sorted(eligible & selected),
            "eligible_candidate_event_ids": sorted(eligible & candidates),
            "eligible_structural_peer_event_ids": sorted(eligible & peers),
            "eligible_scoreable_event_ids_by_model": {
                model: sorted(eligible & events) for model, events in scoreable.items()
            },
            "eligible_outside_structural_peer_event_ids": sorted(eligible - peers),
            "binding_observations": observations,
            "members": members,
        }
        binding["binding_sha256"] = hash_payload(binding)
        bindings.append(binding)
    return [summaries[key] for key in sorted(summaries)], bindings


@dataclasses.dataclass(frozen=True, slots=True)
class StockPopulationBindingInventory:
    population: StockEligiblePopulationInventory
    _source_population_sha256: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            captured, source = _capture_population(self.population)
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise _refuse(f"invalid source population: {exc}") from exc
        object.__setattr__(self, "population", captured)
        object.__setattr__(self, "_source_population_sha256", source["inventory_sha256"])

    def to_payload(self) -> dict[str, Any]:
        try:
            return StockPopulationBindingInventory._to_payload(self)
        except StockPopulationBindingError:
            raise
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise _refuse(f"invalid population binding: {exc}") from exc

    def _to_payload(self) -> dict[str, Any]:
        if type(self) is not StockPopulationBindingInventory:
            raise _refuse("binding inventory must be the exact StockPopulationBindingInventory type")
        captured, source = _capture_population(self.population)
        if (type(self._source_population_sha256) is not str
                or source["inventory_sha256"] != self._source_population_sha256):
            raise _refuse("binding source differs from captured population")
        cohorts, bindings = _relations(captured, source)
        policy = {
            "semantics": "existing_structural_normalization_relationships_only",
            "cutoff_rule": "compare_existing_cutoffs_never_retime_or_pool",
            "membership_rule": "match_event_and_stable_security_identity_not_ticker",
            "population_rule": "report_intersections_never_select_a_ranking_universe",
            "candidate_lookbacks": source["policy"]["candidate_lookbacks"],
            "owner_directive_path": source["policy"]["owner_directive_path"],
            "owner_directive_commit": source["policy"]["owner_directive_commit"],
            "owner_directive_sha256": source["policy"]["owner_directive_sha256"],
            "normalization_policy_sha256": STOCK_NORMALIZATION_POLICY.sha256,
            "financial_population_policy_required": True,
        }
        payload = {
            "schema_version": "1.0",
            "binding_id": "si2b-offline-population-normalization-binding-v1",
            "source_population_sha256": source["inventory_sha256"],
            "source_evidence_sha256": source["source_evidence_sha256"],
            "source_vintage_sha256": source["source_vintage_sha256"],
            "reference_bundle_sha256": source["reference_bundle_sha256"],
            "market_history_sha256": source["market_history_sha256"],
            "normalization_policy_sha256": STOCK_NORMALIZATION_POLICY.sha256,
            "policy": policy,
            "policy_sha256": hash_payload(policy),
            "normalization_cohorts": cohorts,
            "bindings": bindings,
            "financial_population_policy_required": True,
            "production_authoritative": False,
            "ranking_authorized": False,
            "seed_authorized": False,
            "outcome_authorized": False,
            "selected_lookback": None,
        }
        payload["inventory_sha256"] = hash_payload(payload)
        return payload

    @property
    def sha256(self) -> str:
        return StockPopulationBindingInventory.to_payload(self)["inventory_sha256"]


def build_stock_population_binding_inventory(
    population: StockEligiblePopulationInventory,
) -> StockPopulationBindingInventory:
    inventory = StockPopulationBindingInventory(population)
    StockPopulationBindingInventory.to_payload(inventory)
    return inventory
