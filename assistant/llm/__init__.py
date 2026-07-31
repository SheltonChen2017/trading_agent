"""Read-only investment-committee contracts.

This package is intentionally isolated from broker, proposal-generation,
policy, and execution modules.  It can project an already-computed
``DecisionPacket`` and an already-created risk-reduction proposal into a
privacy-controlled input, validate a model-shaped review, and orchestrate a
provider supplied by the caller.  It cannot create or change a proposal.
"""

from assistant.llm.committee import CommitteeResult, run_committee_review
from assistant.llm.projection import ProjectionError, project_committee_input
from assistant.llm.schemas import (
    CommitteeInput,
    CommitteeReview,
    PrivacyMode,
    ReviewStatus,
    Verdict,
)

__all__ = [
    "CommitteeInput",
    "CommitteeResult",
    "CommitteeReview",
    "PrivacyMode",
    "ProjectionError",
    "ReviewStatus",
    "Verdict",
    "project_committee_input",
    "run_committee_review",
]
