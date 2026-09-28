"""SI-2B-P1A synthetic eligible-population membership, not ranks or seeds.

Build one complete membership partition per settlement, authenticated execution
open and candidate lookback. Inputs are reauthenticated SI-2B-P0 evidence,
never a caller-supplied list of eligible security IDs. Refused snapshots remain
visible; parser refusals remain bound to the source vintage identity. This does
not rescore structural normalizations or turn them into eligible-universe ranks.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from data.hashing import hash_payload
from research.short_interest_etf.pit_eligibility import build_stock_data_readiness
from research.short_interest_etf.stock_investability import StockInvestabilityEvidence

ELIGIBLE_POPULATION_SCHEMA_VERSION = "1.0"
ELIGIBLE_POPULATION_INVENTORY_ID = "si2b-offline-eligible-population-v1"
_CANDIDATE_LOOKBACKS = (20, 60, 120, 252)


class StockEligiblePopulationError(ValueError):
    """Synthetic membership evidence failed closed."""


def _refuse(detail: str) -> StockEligiblePopulationError:
    return StockEligiblePopulationError(f"REFUSED: {detail}")


def _capture_evidence(
    evidence: StockInvestabilityEvidence,
) -> tuple[StockInvestabilityEvidence, dict[str, Any]]:
    if type(evidence) is not StockInvestabilityEvidence:
        raise _refuse("source must be the exact StockInvestabilityEvidence type")
    try:
        original = StockInvestabilityEvidence.to_payload(evidence)
        captured = StockInvestabilityEvidence(
            evidence.vintage, evidence.references, evidence.history,
        )
        payload = StockInvestabilityEvidence.to_payload(captured)
    except (ValueError, TypeError, AttributeError) as exc:
        raise _refuse(f"invalid source eligibility evidence: {exc}") from exc
    if payload != original:
        raise _refuse("source eligibility evidence changed during capture")
    return captured, payload


def _policy(source_policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "grouping": "settlement_date_execution_open_and_candidate_lookback",
        "semantics": "synthetic_membership_only_not_scores_or_seeds",
        "candidate_lookbacks": list(_CANDIDATE_LOOKBACKS),
        "member_identity": "source_event_and_stable_security_identity",
        "eligible_identity_rule": "one_eligible_event_per_security_per_cohort",
        "refusal_rule": "retain_every_authenticated_snapshot_disposition",
        "owner_directive_path": source_policy["owner_directive_path"],
        "owner_directive_commit": source_policy["owner_directive_commit"],
        "owner_directive_sha256": source_policy["owner_directive_sha256"],
        "selected_lookback": None,
        "ranking_authorized": False,
        "seed_authorized": False,
        "outcome_authorized": False,
        "production_authoritative": False,
    }


def _cohorts(
    evidence: StockInvestabilityEvidence,
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    ready = build_stock_data_readiness(evidence.vintage, evidence.references)
    readiness = {row.event_id: row for row in ready}
    expected_slots = {
        (event_id, lookback)
        for event_id in readiness for lookback in _CANDIDATE_LOOKBACKS
    }
    seen_slots: set[tuple[str, int]] = set()
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for row in source["rows"]:
        slot = row["event_id"], row["lookback_sessions"]
        if slot not in expected_slots or slot in seen_slots:
            raise _refuse("eligibility inventory has a duplicate or unknown source slot")
        seen_slots.add(slot)
        upstream = readiness[row["event_id"]]
        if (
            row["security_id"] != upstream.security_id
            or row["security_identity_sha256"] != upstream.security_identity_sha256
            or row["evidence_cutoff_at"] != upstream.execution_at
        ):
            raise _refuse("membership identity or cutoff differs from authenticated readiness")
        if type(row["eligible"]) is not bool or row["eligible"] != (not row["refusal_reasons"]):
            raise _refuse("eligibility state is inconsistent with refusal reasons")
        key = upstream.settlement_date, upstream.execution_at, row["lookback_sessions"]
        groups.setdefault(key, []).append({
            "event_id": row["event_id"],
            "security_id": row["security_id"],
            "security_identity_sha256": row["security_identity_sha256"],
            "eligible": row["eligible"],
            "refusal_reasons": list(row["refusal_reasons"]),
            "eligibility_row_sha256": hash_payload(row),
            "taxonomy_id": upstream.taxonomy_id,
            "sector_code": upstream.sector_code,
            "industry_code": upstream.industry_code,
        })
    if seen_slots != expected_slots:
        raise _refuse("eligibility inventory omits an authenticated source slot")
    results = []
    for (settlement, cutoff, lookback), members in sorted(groups.items()):
        members.sort(key=lambda row: (row["security_id"], row["event_id"]))
        eligible = [row for row in members if row["eligible"]]
        refused = [row for row in members if not row["eligible"]]
        security_ids = [row["security_id"] for row in eligible]
        if len(set(security_ids)) != len(security_ids):
            raise _refuse("cohort has ambiguous eligible events for one security")
        cohort = {
            "settlement_date": settlement,
            "evidence_cutoff_at": cutoff,
            "lookback_sessions": lookback,
            "members": members,
            "source_member_count": len(members),
            "eligible_member_count": len(eligible),
            "refused_member_count": len(refused),
            "eligible_event_ids": sorted(row["event_id"] for row in eligible),
            "refused_event_ids": sorted(row["event_id"] for row in refused),
            "eligible_security_ids": sorted(security_ids),
            "underfill_reasons": [] if eligible else ["no_eligible_members"],
        }
        cohort["cohort_sha256"] = hash_payload(cohort)
        results.append(cohort)
    return results


@dataclasses.dataclass(frozen=True, slots=True)
class StockEligiblePopulationInventory:
    evidence: StockInvestabilityEvidence
    _source_evidence_sha256: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        captured, source = _capture_evidence(self.evidence)
        object.__setattr__(self, "evidence", captured)
        object.__setattr__(self, "_source_evidence_sha256", source["evidence_sha256"])

    def to_payload(self) -> dict[str, Any]:
        try:
            return StockEligiblePopulationInventory._to_payload(self)
        except StockEligiblePopulationError:
            raise
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise _refuse(f"invalid eligible-population inventory: {exc}") from exc

    def _to_payload(self) -> dict[str, Any]:
        if type(self) is not StockEligiblePopulationInventory:
            raise _refuse("inventory must be the exact StockEligiblePopulationInventory type")
        evidence, source = _capture_evidence(self.evidence)
        if (
            type(self._source_evidence_sha256) is not str
            or source["evidence_sha256"] != self._source_evidence_sha256
        ):
            raise _refuse("inventory source binding differs from captured eligibility evidence")
        if source["policy"]["candidate_lookbacks"] != list(_CANDIDATE_LOOKBACKS):
            raise _refuse("source lookbacks differ from the approved candidate grid")
        for flag in ("production_authoritative", "seed_authorized", "outcome_authorized"):
            if source[flag] is not False:
                raise _refuse("source eligibility evidence cannot claim authority")
        if source["selected_lookback"] is not None:
            raise _refuse("source eligibility evidence cannot select a lookback")
        policy = _policy(source["policy"])
        payload = {
            "schema_version": ELIGIBLE_POPULATION_SCHEMA_VERSION,
            "inventory_id": ELIGIBLE_POPULATION_INVENTORY_ID,
            "source_evidence_sha256": source["evidence_sha256"],
            "source_vintage_sha256": source["source_vintage_sha256"],
            "reference_bundle_sha256": source["reference_bundle_sha256"],
            "market_history_sha256": source["market_history_sha256"],
            "eligibility_policy_sha256": source["policy_sha256"],
            "policy": policy,
            "policy_sha256": hash_payload(policy),
            "cohorts": _cohorts(evidence, source),
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
        return StockEligiblePopulationInventory.to_payload(self)["inventory_sha256"]


def build_stock_eligible_population_inventory(
    evidence: StockInvestabilityEvidence,
) -> StockEligiblePopulationInventory:
    inventory = StockEligiblePopulationInventory(evidence)
    StockEligiblePopulationInventory.to_payload(inventory)
    return inventory
