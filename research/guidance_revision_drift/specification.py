"""Executable proposed semantics and closed decision/rights inventory.

This is a consistency check for offline engineering, not an owner freeze or
an authorization registry. The original pinned candidate is never rewritten.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.contracts import Candidate, CandidateError
from research.guidance_revision_drift.fixtures import example_corpus
from research.guidance_revision_drift.formulas import GuidanceRange, evaluate_range_revisions
from research.guidance_revision_drift.readiness import preflight
from research.guidance_revision_drift.timing import decision_cutoff, entry_window, time_exit_session


def check_proposed_semantics() -> tuple[str, ...]:
    """Execute exact boundary witnesses against the implementation, not copies.

    Other stateful financial contracts are exercised by their focused tests.
    These checks never read observations, execute orders or confer authority.
    """
    def point(value: str) -> GuidanceRange:
        return GuidanceRange(Decimal(value), Decimal(value))

    common = {"previous_revenue": point("100"), "previous_eps": point("1")}
    exact = evaluate_range_revisions(**common, current_revenue=point("102"), current_eps=point("1.05"))
    below = evaluate_range_revisions(**common, current_revenue=point("101.999999999999999999999999999999"),
                                    current_eps=point("1.05"))
    eps_below = evaluate_range_revisions(**common, current_revenue=point("102"),
                                        current_eps=point("1.049999999999999999999999999999"))
    schedule = example_corpus().schedule
    window = entry_window(schedule, date(2025, 4, 1))
    witnesses = {
        "inclusive_raise_thresholds": exact.passes_arithmetic,
        "subthreshold_revenue_refuses": not below.passes_arithmetic,
        "subthreshold_eps_refuses": not eps_below.passes_arithmetic,
        "third_session_window": window == (date(2025, 4, 4), date(2025, 4, 7), date(2025, 4, 8)),
        "previous_session_cutoff": decision_cutoff(schedule, window[0]).isoformat() == "2025-04-03T22:00:00+00:00",
        "twenty_session_intervals": time_exit_session(schedule, window[0]) == date(2025, 5, 5),
    }
    failed = tuple(name for name, passed in witnesses.items() if not passed)
    if failed:
        raise CandidateError("proposed implementation semantics drift: " + ",".join(failed))
    return tuple(witnesses)


@dataclass(frozen=True, slots=True)
class ExecutableSpecification:
    candidate: Candidate

    def __post_init__(self) -> None:
        if type(self.candidate) is not Candidate:
            raise CandidateError("exact pinned Candidate required")
        # Retain a separately constructed value rather than a caller object.
        object.__setattr__(self, "candidate", Candidate(self.candidate.canonical_bytes))

    def to_dict(self) -> dict:
        candidate = Candidate(self.candidate.canonical_bytes)
        body = candidate.to_dict()
        checks = check_proposed_semantics()
        return {
            "schema": "gdr.offline.executable-specification.v1",
            "candidate_sha256": candidate.sha256,
            "sources": body["source_documents"],
            "status": "proposed_not_owner_frozen",
            "parameters": {key: body[key] for key in (
                "signal", "universe", "timing", "portfolio", "execution", "exits", "evidence", "statistics")},
            "semantics": {
                "same_id_metadata": "retain_original_no_fresh_entry",
                "explicit_correction": "invalidate_now_no_direct_positive_entry; corrected_predecessor_for_later_disclosures",
                "withdrawal": "invalidate_without_skipping_to_older_predecessor",
                "trim_tolerance": "none; whole_share_floor_to_proposed_caps",
                "opportunity": "first_fully_eligible_E_through_E_plus_2; no_retry_after_attempt",
                "publication": "strictly_before_cutoff; receipt_and_validation_may_equal",
                "entry_cost_stop_basis": "split_adjusted_execution_price; fees_separate",
                "commission": "cumulative_per_filled_order_floor_once; stress_floor_doubled",
                "settlement": "explicit_fixture_pay_session_after_trade; open_before_spending; real_contract_unresolved",
                "unsupported_actions": "refuse_or_retain_named_incomplete_blocker; no_invented_payout",
                "calendar": "explicit_fixture_sessions; no_audited_NYSE_claim",
            },
            "decision_rights": [
                {"action": key, "allowed": False, "required_decision": "separate_exact_human_authorization"}
                for key in sorted(body["authority"]) if key != "research_looks"
            ],
            "owner_decisions": [
                {"decision": key, "status": "unresolved", "approval": None}
                for key in sorted(body["unresolved"])
            ],
            "engineering_witnesses": list(checks),
            "readiness": preflight(candidate).to_dict(),
            "research_looks": 0,
            "qc_attempts": 0,
            "point_in_time_data": False,
        }

    def to_bytes(self) -> bytes:
        return canonical_json(self.to_dict()).encode("utf-8")

    @property
    def sha256(self) -> str:
        return hash_bytes(self.to_bytes())
