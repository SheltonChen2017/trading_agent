"""Best-effort persistence wrapper around one committee review call.

Deliberately outside committee.py: that module's tested contract is a pure
(input, provider, timeout) -> CommitteeResult call with no I/O side effects,
and it's governed by docs/ADR_INVESTMENT_COMMITTEE_BOUNDARY.md plus its own
test suite (tests/test_committee_foundation.py) -- adding a `store` param
there would mix concerns into a narrower-scoped module for no reason. This
wrapper adds exactly one thing, an audit-log row via the existing
assistant.storage.AssistantStore.record_ai_run(), mirroring how
assistant/ai_advisor.py separates its own Claude calls from its
_record_run() audit write.

Still lives inside assistant/llm/, so the package's forbidden-import AST
guard (tests/test_committee_foundation.py) applies to this file too --
assistant.storage is not in that forbidden set.
"""
from __future__ import annotations

import hashlib
import json
import time

from assistant.llm.committee import CommitteeResult, run_committee_review
from assistant.llm.provider import CommitteeProvider
from assistant.llm.schemas import CommitteeInput
from assistant.storage import AssistantStore

_FUNCTION_NAME = "run_committee_review"


def _input_hash(committee_input: CommitteeInput) -> str:
    canonical = json.dumps(committee_input.to_dict(), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_committee_review_and_record(
    committee_input: CommitteeInput,
    provider: CommitteeProvider,
    store: AssistantStore | None = None,
    *,
    timeout_seconds: float = 30.0,
) -> CommitteeResult:
    """Same contract as run_committee_review(), plus a best-effort audit row.

    A persistence failure must never break the advisory feature itself --
    matches assistant/ai_advisor.py's _record_run() convention exactly:
    `store` is optional, and the write is wrapped in its own bare
    `except Exception: pass`.
    """
    start = time.monotonic()
    result = run_committee_review(committee_input, provider, timeout_seconds=timeout_seconds)
    if store is not None:
        try:
            store.record_ai_run(
                function_name=_FUNCTION_NAME,
                model=result.model_id,
                prompt_version=result.prompt_version,
                input_hash=_input_hash(committee_input),
                latency_ms=(time.monotonic() - start) * 1000,
                success=result.accepted,
                response=result.review.to_dict() if result.review is not None else None,
                error=None if result.accepted else (result.error_message or result.error_code),
            )
        except Exception:
            pass
    return result
