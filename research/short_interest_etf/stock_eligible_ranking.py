"""Offline eligible-population S1 ranks at the canonical release-next-open.

SI-3C normalization remains over its unchanged structural peers. This adapter
rebuilds authenticated S1 pressure/covering scores, then computes new exact
order statistics over only the SI-2B-eligible, release-open selected and
scoreable events for each candidate lookback. Later evidence is reported but
never backdated into an earlier release-open rank. These are synthetic
threshold candidates, not seeds, outcomes, or execution instructions.
"""
from __future__ import annotations

import dataclasses
from fractions import Fraction
from typing import Any

from data.hashing import hash_payload
from research.short_interest_etf.stock_covering import COVERING_EQUATION
from research.short_interest_etf.stock_features import ExactRational, build_pit_stock_raw_features
from research.short_interest_etf.stock_normalization import (
    STOCK_NORMALIZATION_POLICY,
    RevisionSelectionState,
    StockScoreModel,
    build_pit_stock_normalized_scores,
)
from research.short_interest_etf.stock_population_binding import StockPopulationBindingInventory


ELIGIBLE_RANKING_INVENTORY_ID = "si2b-offline-eligible-s1-ranking-v1"
ELIGIBLE_RANKING_SCHEMA_VERSION = "1.0"
_LOOKBACKS = (20, 60, 120, 252)
_MINIMUM_RANKABLE_FOR_THRESHOLD = 10
_PRESSURE_THRESHOLD = Fraction(9, 10)
_OWNER_FREEZE = (
    "keep the existing structural normalization, rank only stocks eligible "
    "at the release’s next open, and exclude later-arriving evidence from "
    "that cohort."
)


class StockEligibleRankingError(ValueError):
    """Authenticated offline eligible ranking could not be established."""


def _refuse(detail: str) -> StockEligibleRankingError:
    return StockEligibleRankingError(f"REFUSED: {detail}")


def _capture_binding(
    binding: StockPopulationBindingInventory,
) -> tuple[StockPopulationBindingInventory, dict[str, Any]]:
    if type(binding) is not StockPopulationBindingInventory:
        raise _refuse("source must be the exact StockPopulationBindingInventory type")
    original = StockPopulationBindingInventory.to_payload(binding)
    captured = StockPopulationBindingInventory(binding.population)
    payload = StockPopulationBindingInventory.to_payload(captured)
    if payload != original:
        raise _refuse("source binding changed during capture")
    return captured, payload


def _policy(source: dict[str, Any]) -> dict[str, Any]:
    if source["policy"]["candidate_lookbacks"] != list(_LOOKBACKS):
        raise _refuse("source lookbacks differ from the owner-approved grid")
    if STOCK_NORMALIZATION_POLICY.minimum_sector_peers != 20:
        raise _refuse("structural sector peer floor differs from the frozen 20")
    for flag in (
        "production_authoritative", "ranking_authorized", "seed_authorized",
        "outcome_authorized",
    ):
        if source[flag] is not False:
            raise _refuse("source binding claims forbidden authority")
    if source["selected_lookback"] is not None:
        raise _refuse("source binding selected a lookback")
    return {
        "owner_freeze": _OWNER_FREEZE,
        "owner_decision_record": (
            "docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md#59"
        ),
        "normalization_population": "unchanged_full_structural_SI3C",
        "ranking_population": "eligible_selected_S1_scoreable_at_release_next_open",
        "later_evidence": "exclude_and_report_never_retime_or_backdate",
        "missing_release_open_evidence": "empty_rank_with_explicit_underfill",
        "candidate_lookbacks": list(_LOOKBACKS),
        "structural_sector_peer_floor": 20,
        "minimum_eligible_scoreable_for_threshold": _MINIMUM_RANKABLE_FOR_THRESHOLD,
        "percentile_formula": "(2*L+E)/(2*N)",
        "covering_equation": COVERING_EQUATION,
        "threshold": {"numerator": 9, "denominator": 10},
        "threshold_boundary": "inclusive_with_indivisible_exact_ties",
        "normalization_policy_sha256": STOCK_NORMALIZATION_POLICY.sha256,
        "source_binding_policy_sha256": source["policy_sha256"],
        "selected_lookback": None,
        "production_ranking_authorized": False,
        "seed_authorized": False,
        "outcome_authorized": False,
        "production_authoritative": False,
    }


def _covering_source(
    captured: StockPopulationBindingInventory,
    source: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], str]:
    if COVERING_EQUATION != "blueprint_4_20_C_equals_negative_B1":
        raise _refuse("canonical covering equation changed")
    evidence = captured.population.evidence
    scores = tuple(build_pit_stock_normalized_scores(
        build_pit_stock_raw_features(evidence.vintage, evidence.references)
    ))
    summaries = {item["settlement_date"]: item for item in source["normalization_cohorts"]}
    by_event: dict[str, dict[str, Any]] = {}
    cohort_hashes: dict[str, str] = {}
    for item in scores:
        settlement = item.cohort.settlement_date
        summary = summaries.get(settlement)
        if settlement not in cohort_hashes:
            cohort_hashes[settlement] = hash_payload(item.cohort.to_payload())
        outcome = item.outcomes[1]
        if outcome.model is not StockScoreModel.S1_DELTA:
            raise _refuse("canonical score source lost its S1 outcome")
        score = outcome.score
        covering = (
            None if score is None else
            ExactRational.from_fraction(-score.to_fraction())
        )
        row = {
            "event_id": item.current.readiness.event_id,
            "security_id": item.current.readiness.security_id,
            "settlement_date": settlement,
            "decision_at": item.cohort.decision_at,
            "normalization_cohort_sha256": cohort_hashes[settlement],
            "normalization_policy_sha256": STOCK_NORMALIZATION_POLICY.sha256,
            "revision_selection_state": outcome.revision_selection_state.value,
            "selected_event_id": outcome.selected_event_id,
            "source_s1_score": None if score is None else score.to_payload(),
            "covering_score": None if covering is None else covering.to_payload(),
        }
        if summary is None or (
            row["normalization_cohort_sha256"] != summary["normalization_cohort_sha256"]
            or row["decision_at"] != summary["decision_at"]
            or row["normalization_policy_sha256"] != source["normalization_policy_sha256"]
        ):
            raise _refuse("covering source differs from the bound structural cohort")
        if row["event_id"] in by_event:
            raise _refuse("covering source has duplicate event identity")
        by_event[row["event_id"]] = row
    return by_event, hash_payload([by_event[key] for key in sorted(by_event)])


def _rank_rows(
    members: dict[str, dict[str, Any]],
    rankable: set[str],
    projections: dict[str, dict[str, Any]],
    normalization_cohort_sha256: str,
    decision_at: str,
    settlement: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    source_rows: dict[str, dict[str, Any]] = {}
    for event in sorted(rankable):
        source = projections.get(event)
        member = members[event]
        if source is None or (
            source["security_id"] != member["security_id"]
            or source["settlement_date"] != settlement
            or source["decision_at"] != decision_at
            or source["normalization_cohort_sha256"] != normalization_cohort_sha256
            or source["revision_selection_state"] != RevisionSelectionState.SELECTED.value
            or source["selected_event_id"] != event
            or source["source_s1_score"] is None
            or source["covering_score"] is None
        ):
            raise _refuse("eligible scoreable event differs from canonical S1 source")
        source_rows[event] = source
    rows: list[dict[str, Any]] = []
    underfill: list[str] = []
    for role, score_key in (("pressure", "source_s1_score"), ("covering", "covering_score")):
        scores = {
            event: Fraction(source[score_key]["numerator"], source[score_key]["denominator"])
            for event, source in source_rows.items()
        }
        total = len(scores)
        if total < _MINIMUM_RANKABLE_FOR_THRESHOLD:
            underfill.append(f"insufficient_eligible_scoreable_{role}_population")
        for event, score in sorted(scores.items()):
            lower = sum(value < score for value in scores.values())
            equal = sum(value == score for value in scores.values())
            higher = total - lower - equal
            percentile = ExactRational.from_values(2 * lower + equal, 2 * total)
            row = {
                "event_id": event,
                "security_id": members[event]["security_id"],
                "role": role,
                "score": ExactRational.from_fraction(score).to_payload(),
                "derived_s1_covering_row_sha256": hash_payload(source_rows[event]),
                "strictly_lower_count": lower,
                "equal_count": equal,
                "strictly_higher_count": higher,
                "scoreable_count": total,
                "role_percentile": percentile.to_payload(),
                "threshold_candidate": (
                    None if total < _MINIMUM_RANKABLE_FOR_THRESHOLD
                    else percentile.to_fraction() >= _PRESSURE_THRESHOLD
                ),
            }
            row["ranking_row_sha256"] = hash_payload(row)
            rows.append(row)
    return rows, underfill


def _rankings(
    captured: StockPopulationBindingInventory,
    source: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    projections, covering_sha256 = _covering_source(captured, source)
    summaries = {item["settlement_date"]: item for item in source["normalization_cohorts"]}
    groups: dict[tuple[str, int], dict[str, Any]] = {}
    non_open: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for binding in source["bindings"]:
        key = binding["settlement_date"], binding["lookback_sessions"]
        if binding["cutoff_relation"] == "same_open":
            if key in groups:
                raise _refuse("more than one release-open eligibility cohort")
            groups[key] = binding
        else:
            non_open.setdefault(key, []).append(binding)
    expected = {(settlement, lookback) for settlement in summaries for lookback in _LOOKBACKS}
    if set(groups) | set(non_open) != expected:
        raise _refuse("a release/lookback lacks authenticated eligibility evidence")
    rankings = []
    for settlement, lookback in sorted(expected):
        binding = groups.get((settlement, lookback))
        summary = summaries[settlement]
        if binding is None:
            # A release can have only later-published events. Preserve its
            # original next-open decision as an explicit empty cohort.
            members: dict[str, dict[str, Any]] = {}
            eligible: set[str] = set()
            selected: set[str] = set()
            scoreable: set[str] = set()
        else:
            if (
                binding["eligibility_cutoff_at"] != summary["decision_at"]
                or binding["normalization_cutoff_at"] != summary["decision_at"]
                or binding["normalization_cohort_sha256"] != summary["normalization_cohort_sha256"]
                or binding["cutoff_equal"] is not True
            ):
                raise _refuse("release-open binding does not match the canonical cutoff")
            members = {item["event_id"]: item for item in binding["members"]}
            if len(members) != len(binding["members"]):
                raise _refuse("release-open binding has duplicate event identity")
            eligible = set(binding["eligible_event_ids"])
            selected = set(binding["eligible_selected_event_ids"])
            scoreable = set(binding["eligible_scoreable_event_ids_by_model"][StockScoreModel.S1_DELTA.value])
            if not selected <= eligible or not scoreable <= eligible or not eligible <= set(members):
                raise _refuse("release-open binding has inconsistent eligible membership")
        rankable = selected & scoreable
        excluded = []
        for event, member in sorted(members.items()):
            if event in rankable:
                continue
            reasons = list(member["refusal_reasons"])
            if member["eligible"] and event not in selected:
                reasons.append("not_selected_at_release_open")
            elif member["eligible"] and event not in scoreable:
                reasons.append("no_canonical_s1_score")
            excluded.append({
                "event_id": event,
                "security_id": member["security_id"],
                "reasons": sorted(set(reasons)),
            })
        excluded_off_open = sorted(
            non_open.get((settlement, lookback), []),
            key=lambda item: (item["eligibility_cutoff_at"], item["binding_sha256"]),
        )
        late = sorted({
            event for item in excluded_off_open
            if item["cutoff_relation"] == "eligibility_after_normalization"
            for event in item["eligible_event_ids"]
        })
        rows, underfill = _rank_rows(
            members, rankable, projections,
            summary["normalization_cohort_sha256"], summary["decision_at"], settlement,
        )
        if binding is None:
            underfill.insert(0, "no_release_open_eligibility_cohort")
        ranking = {
            "settlement_date": settlement,
            "decision_at": summary["decision_at"],
            "lookback_sessions": lookback,
            "source_binding_cohort_sha256": None if binding is None else binding["binding_sha256"],
            "normalization_cohort_sha256": summary["normalization_cohort_sha256"],
            "release_open_evidence_available": binding is not None,
            "eligible_event_ids": sorted(eligible),
            "ranked_event_ids": sorted(rankable),
            "excluded_members": excluded,
            "excluded_later_event_ids": late,
            "excluded_off_open_bindings": [
                {
                    "source_binding_cohort_sha256": item["binding_sha256"],
                    "evidence_cutoff_at": item["eligibility_cutoff_at"],
                    "cutoff_relation": item["cutoff_relation"],
                    "eligible_event_ids": list(item["eligible_event_ids"]),
                    "refused_event_ids": list(item["refused_event_ids"]),
                }
                for item in excluded_off_open
            ],
            "rows": rows,
            "underfill_reasons": underfill,
        }
        ranking["ranking_sha256"] = hash_payload(ranking)
        rankings.append(ranking)
    return rankings, covering_sha256


@dataclasses.dataclass(frozen=True, slots=True)
class StockEligibleRankingInventory:
    binding: StockPopulationBindingInventory
    _source_binding_sha256: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            captured, source = _capture_binding(self.binding)
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise _refuse(f"invalid source binding: {exc}") from exc
        object.__setattr__(self, "binding", captured)
        object.__setattr__(self, "_source_binding_sha256", source["inventory_sha256"])

    def to_payload(self) -> dict[str, Any]:
        try:
            return StockEligibleRankingInventory._to_payload(self)
        except StockEligibleRankingError:
            raise
        except (ValueError, TypeError, AttributeError, KeyError, ZeroDivisionError) as exc:
            raise _refuse(f"invalid eligible ranking: {exc}") from exc

    def _to_payload(self) -> dict[str, Any]:
        if type(self) is not StockEligibleRankingInventory:
            raise _refuse("ranking inventory must be the exact StockEligibleRankingInventory type")
        captured, source = _capture_binding(self.binding)
        if (type(self._source_binding_sha256) is not str
                or source["inventory_sha256"] != self._source_binding_sha256):
            raise _refuse("ranking source differs from captured binding")
        policy = _policy(source)
        rankings, covering_sha256 = _rankings(captured, source)
        payload = {
            "schema_version": ELIGIBLE_RANKING_SCHEMA_VERSION,
            "inventory_id": ELIGIBLE_RANKING_INVENTORY_ID,
            "source_binding_sha256": source["inventory_sha256"],
            "source_population_sha256": source["source_population_sha256"],
            "source_vintage_sha256": source["source_vintage_sha256"],
            "reference_bundle_sha256": source["reference_bundle_sha256"],
            "source_s1_covering_rows_sha256": covering_sha256,
            "normalization_policy_sha256": STOCK_NORMALIZATION_POLICY.sha256,
            "policy": policy,
            "policy_sha256": hash_payload(policy),
            "rankings": rankings,
            "selected_lookback": None,
            "production_ranking_authorized": False,
            "seed_authorized": False,
            "outcome_authorized": False,
            "production_authoritative": False,
        }
        payload["inventory_sha256"] = hash_payload(payload)
        return payload

    @property
    def sha256(self) -> str:
        return StockEligibleRankingInventory.to_payload(self)["inventory_sha256"]


def build_stock_eligible_ranking_inventory(
    binding: StockPopulationBindingInventory,
) -> StockEligibleRankingInventory:
    inventory = StockEligibleRankingInventory(binding)
    StockEligibleRankingInventory.to_payload(inventory)
    return inventory
