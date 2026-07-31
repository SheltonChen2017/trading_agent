"""One-call, fail-closed committee orchestration."""
from __future__ import annotations

import dataclasses
import math
from typing import Any

from assistant.llm.prompt_builder import PROMPT_VERSION, build_committee_request
from assistant.llm.provider import CommitteeProvider, CommitteeProviderError
from assistant.llm.schemas import (
    COMMITTEE_REVIEW_JSON_SCHEMA,
    CommitteeInput,
    CommitteeReview,
    CommitteeSchemaError,
    ReviewStatus,
)
from assistant.llm.validators import ValidationIssue, validate_committee_review


@dataclasses.dataclass(frozen=True)
class CommitteeResult:
    status: ReviewStatus
    prompt_version: str
    provider_id: str
    model_id: str
    review: CommitteeReview | None = None
    issues: tuple[ValidationIssue, ...] = ()
    error_code: str | None = None
    error_message: str | None = None

    @property
    def accepted(self) -> bool:
        return self.status == ReviewStatus.ACCEPTED and self.review is not None


def run_committee_review(
    committee_input: CommitteeInput,
    provider: CommitteeProvider,
    *,
    timeout_seconds: float = 30.0,
) -> CommitteeResult:
    """Request and validate one review.

    Any provider, schema, or grounding failure becomes an explicit
    ``review_unavailable`` result.  No exception and no partial review is
    allowed to masquerade as an accepted committee opinion.
    """

    provider_id = str(getattr(provider, "provider_id", "unknown"))
    model_id = str(getattr(provider, "model_id", "unknown"))
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        return CommitteeResult(
            status=ReviewStatus.REVIEW_UNAVAILABLE,
            prompt_version=PROMPT_VERSION,
            provider_id=provider_id,
            model_id=model_id,
            error_code="invalid_timeout",
            error_message="timeout_seconds must be positive and finite.",
        )
    system_prompt, input_payload = build_committee_request(committee_input)
    try:
        raw: Any = provider.complete_json(
            system_prompt=system_prompt,
            input_payload=input_payload,
            response_schema=COMMITTEE_REVIEW_JSON_SCHEMA,
            timeout_seconds=timeout_seconds,
        )
        review = CommitteeReview.from_mapping(raw)
        report = validate_committee_review(committee_input, review)
        if not report.accepted:
            return CommitteeResult(
                status=ReviewStatus.REVIEW_UNAVAILABLE,
                prompt_version=PROMPT_VERSION,
                provider_id=provider_id,
                model_id=model_id,
                issues=report.issues,
                error_code="validation_rejected",
                error_message="Provider output failed deterministic validation.",
            )
        return CommitteeResult(
            status=ReviewStatus.ACCEPTED,
            prompt_version=PROMPT_VERSION,
            provider_id=provider_id,
            model_id=model_id,
            review=review,
        )
    except CommitteeSchemaError as exc:
        return CommitteeResult(
            status=ReviewStatus.REVIEW_UNAVAILABLE,
            prompt_version=PROMPT_VERSION,
            provider_id=provider_id,
            model_id=model_id,
            error_code="schema_rejected",
            error_message=str(exc),
        )
    except CommitteeProviderError as exc:
        return CommitteeResult(
            status=ReviewStatus.REVIEW_UNAVAILABLE,
            prompt_version=PROMPT_VERSION,
            provider_id=provider_id,
            model_id=model_id,
            error_code=f"provider_{exc.code}",
            error_message="The configured committee provider reported a failure.",
        )
    except Exception as exc:
        return CommitteeResult(
            status=ReviewStatus.REVIEW_UNAVAILABLE,
            prompt_version=PROMPT_VERSION,
            provider_id=provider_id,
            model_id=model_id,
            error_code="provider_error",
            # Generic provider exceptions may contain request or credential
            # details. Preserve the type for diagnosis, not the message.
            error_message=f"{type(exc).__name__}: provider call failed.",
        )
