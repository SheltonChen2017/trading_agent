"""Real Claude-API-backed CommitteeProvider.

Mirrors assistant/ai_advisor.py's existing Claude-call pattern exactly (lazy
`import anthropic`, zero-config client, `thinking` disabled, `output_config`
json_schema, first-text-block extraction) rather than inventing a new one.
Owns all network/SDK details; assistant/llm/committee.py's run_committee_review()
already catches whatever this raises and maps it to a fail-closed
REVIEW_UNAVAILABLE result, so this module only needs to distinguish the
failure modes worth a specific error_code in the audit log -- everything
else is allowed to propagate as a generic "provider_error".
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Mapping

from assistant.llm.provider import CommitteeProviderError

_MODEL = "claude-opus-5"  # same model as assistant/ai_advisor.py's _MODEL
# Non-streaming default per this project's Claude API reference, and the
# actual worst case for CommitteeReview's schema: 8 CitedPoints (each up to
# 800 chars text + up to 12 source_ids) x 6 list sections, plus summary and
# confidence_basis, runs closer to ~12-13K tokens -- this must comfortably
# exceed that, not merely approach it.
_MAX_TOKENS = 16000
_EXPERIMENTAL_ENABLE_ENV = "ENABLE_EXPERIMENTAL_COMMITTEE"


class AnthropicCommitteeProvider:
    """CommitteeProvider (assistant/llm/provider.py) backed by the real API."""

    provider_id = "anthropic"

    def __init__(self, *, model: str = _MODEL, max_tokens: int = _MAX_TOKENS) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if (
            isinstance(max_tokens, bool)
            or not isinstance(max_tokens, int)
            or not 0 < max_tokens <= _MAX_TOKENS
        ):
            raise ValueError(f"max_tokens must be an integer between 1 and {_MAX_TOKENS}")
        self.model_id = model.strip()
        self._max_tokens = max_tokens

    def complete_json(
        self,
        *,
        system_prompt: str,
        input_payload: Mapping[str, Any],
        response_schema: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        import anthropic  # imported lazily, same pattern as assistant/ai_advisor.py

        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or timeout_seconds <= 0
        ):
            raise CommitteeProviderError(
                "invalid_timeout", "timeout_seconds must be positive and finite."
            )
        try:
            serialized_payload = json.dumps(
                dict(input_payload),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise CommitteeProviderError(
                "invalid_request", "Provider input was not strict JSON."
            ) from exc

        client = anthropic.Anthropic()
        try:
            response = client.with_options(
                # max_retries=0: the SDK default (2) retries on timeout too, so
                # wall-clock can reach timeout_seconds x 3 -- silently blowing
                # through the caller's own budget. Fail fast instead; a
                # REVIEW_UNAVAILABLE surfaces promptly rather than after two
                # extra retries the caller never asked for.
                timeout=timeout_seconds,
                max_retries=0,
            ).messages.create(
                model=self.model_id,
                max_tokens=self._max_tokens,
                thinking={"type": "disabled"},
                output_config={
                    "format": {"type": "json_schema", "schema": dict(response_schema)}
                },
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": serialized_payload,
                    }
                ],
            )
        except anthropic.RateLimitError as exc:
            raise CommitteeProviderError("rate_limited", str(exc)) from exc
        except anthropic.AuthenticationError as exc:
            raise CommitteeProviderError("auth_failed", str(exc)) from exc
        except anthropic.APITimeoutError as exc:
            raise CommitteeProviderError("timeout", str(exc)) from exc
        # Every other anthropic.* exception (APIConnectionError,
        # APIStatusError/BadRequestError, etc.) is left to propagate
        # uncaught -- run_committee_review()'s own bare `except Exception`
        # already maps it to a generic "provider_error" whose message
        # deliberately discards the exception body (no credential/request
        # detail leakage into the audit log), so duplicating that handling
        # here would add surface area for no benefit.

        if response.stop_reason == "refusal":
            detail = getattr(response.stop_details, "explanation", None) or "no detail"
            raise CommitteeProviderError(
                "refusal", f"Provider declined the request: {detail}"
            )
        if response.stop_reason != "end_turn":
            raise CommitteeProviderError(
                "incomplete_response",
                f"Provider stopped before a complete response ({response.stop_reason}).",
            )
        text = next(
            (block.text for block in response.content if block.type == "text"), None
        )
        if not text:
            raise CommitteeProviderError(
                "empty_response", "Provider returned no text content block."
            )
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CommitteeProviderError(
                "invalid_json", "Provider response was not valid JSON."
            ) from exc
        if not isinstance(parsed, dict):
            raise CommitteeProviderError(
                "invalid_json", "Provider response must be one JSON object."
            )
        return parsed


def is_anthropic_committee_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def is_anthropic_committee_experiment_enabled() -> bool:
    """Explicit opt-in while the ADR's frozen-corpus release gate is open."""
    return os.environ.get(_EXPERIMENTAL_ENABLE_ENV, "").strip() == "1"
