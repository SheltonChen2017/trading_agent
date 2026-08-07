"""Provider-neutral boundary for committee JSON completion."""
from __future__ import annotations

from typing import Any, Mapping, Protocol


class CommitteeProviderError(RuntimeError):
    """Stable provider failure surfaced as an unavailable review."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CommitteeProvider(Protocol):
    provider_id: str
    model_id: str

    def complete_json(
        self,
        *,
        system_prompt: str,
        input_payload: Mapping[str, Any],
        response_schema: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """Return one JSON object; implementations own network details."""

