"""Read-only inventory of unresolved GDR-0A gates, not an execution gate."""
from __future__ import annotations

from dataclasses import dataclass

from research.guidance_revision_drift.contracts import Candidate, CandidateError


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Immutable projection of the pinned draft; no caller-supplied approvals."""

    candidate: Candidate

    def __post_init__(self) -> None:
        if type(self.candidate) is not Candidate:
            raise CandidateError("readiness requires an exact Candidate")
        Candidate(self.candidate.canonical_bytes)

    def to_dict(self) -> dict[str, object]:
        candidate = Candidate(self.candidate.canonical_bytes)
        body = candidate.to_dict()
        return {
            "schema": "gdr.readiness.v1",
            "candidate_id": body["candidate_id"],
            "candidate_sha256": candidate.sha256,
            "draft_valid": True,
            "status": "blocked",
            "ready_for_data_or_outcomes": False,
            "ready_for_orders": False,
            "point_in_time_evidence_verified": False,
            "blockers": sorted(body["unresolved"]),
            "authority": body["authority"],
            "note": "Valid proposed parameters are not approved research or trading authority.",
        }


def preflight(candidate: Candidate) -> ReadinessReport:
    """Return all outstanding gates; this version has no promotion operation."""
    return ReadinessReport(candidate)
