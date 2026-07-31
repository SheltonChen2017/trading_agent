"""Audited persistence wrapper around one committee review call.

Deliberately outside committee.py: that module's tested contract is a pure
(input, provider, timeout) -> CommitteeResult call with no I/O side effects,
and it's governed by docs/ADR_INVESTMENT_COMMITTEE_BOUNDARY.md plus its own
test suite (tests/test_committee_foundation.py) -- adding a `store` param
there would mix concerns into a narrower-scoped module for no reason. This
wrapper adds the audit-log row required by the committee ADR via the existing
assistant.storage.AssistantStore.record_ai_run(). Unlike older presentation
helpers' best-effort logs, a supplied store is mandatory for a displayable
committee result: write failure returns REVIEW_UNAVAILABLE.

Still lives inside assistant/llm/, so the package's forbidden-import AST
guard (tests/test_committee_foundation.py) applies to this file too --
assistant.storage is not in that forbidden set.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import time

from assistant.llm.committee import CommitteeResult, run_committee_review
from assistant.llm.provider import CommitteeProvider
from assistant.llm.schemas import CommitteeInput, ReviewStatus
from assistant.storage import AssistantStore

_FUNCTION_NAME = "run_committee_review"


def committee_input_hash(committee_input: CommitteeInput) -> str:
    """Content identity for both persistence and UI cache binding."""
    canonical = json.dumps(
        committee_input.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_committee_review_and_record(
    committee_input: CommitteeInput,
    provider: CommitteeProvider,
    store: AssistantStore | None = None,
    *,
    timeout_seconds: float = 30.0,
) -> CommitteeResult:
    """Same contract as run_committee_review(), plus a mandatory audit row.

    ``store=None`` retains the pure/testing behavior. When a store is supplied,
    an accepted review is not returned to the UI unless its audit record was
    persisted. This committee's ADR explicitly makes persistence a release
    gate for daily model-backed use; silently displaying an unaudited review
    would violate that boundary even though older prose helpers use
    best-effort logging.
    """
    start = time.monotonic()
    result = run_committee_review(committee_input, provider, timeout_seconds=timeout_seconds)
    if store is not None:
        try:
            audit_response = {
                "status": result.status.value,
                "accepted": result.accepted,
                "provider_id": result.provider_id,
                "model_id": result.model_id,
                "prompt_version": result.prompt_version,
                "error_code": result.error_code,
                "issues": [dataclasses.asdict(issue) for issue in result.issues],
                "review": (
                    result.review.to_dict() if result.review is not None else None
                ),
            }
            store.record_ai_run(
                function_name=_FUNCTION_NAME,
                model=result.model_id,
                prompt_version=result.prompt_version,
                input_hash=committee_input_hash(committee_input),
                latency_ms=(time.monotonic() - start) * 1000,
                success=result.accepted,
                response=audit_response,
                error=None if result.accepted else (result.error_code or result.error_message),
            )
        except Exception:
            return dataclasses.replace(
                result,
                status=ReviewStatus.REVIEW_UNAVAILABLE,
                review=None,
                error_code="audit_persistence_failed",
                error_message=(
                    "Review unavailable because its required audit record "
                    "could not be persisted."
                ),
            )
    return result
