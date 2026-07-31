"""Tests for assistant/llm/anthropic_provider.py.

Mocks the SDK boundary the same way tests/test_ai_advisor.py does --
patch("anthropic.Anthropic"), MagicMock, fake text-block response objects --
rather than making real API calls.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic

from assistant.llm.anthropic_provider import AnthropicCommitteeProvider
from assistant.llm.provider import CommitteeProviderError


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


def _fake_response(text, *, stop_reason="end_turn"):
    response = MagicMock()
    response.content = [_FakeTextBlock(text)]
    response.stop_reason = stop_reason
    response.stop_details = None
    return response


def _fake_request():
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _mock_client_returning(response):
    """Build a MagicMock standing in for anthropic.Anthropic() whose
    with_options(...).messages.create(...) returns `response`. Returns
    (client, with_options_mock) so tests can assert on with_options'
    call_args."""
    client = MagicMock()
    with_options_mock = MagicMock()
    client.with_options.return_value = with_options_mock
    with_options_mock.messages.create.return_value = response
    return client, with_options_mock


def _mock_client_raising(exc):
    client = MagicMock()
    with_options_mock = MagicMock()
    client.with_options.return_value = with_options_mock
    with_options_mock.messages.create.side_effect = exc
    return client, with_options_mock


def test_complete_json_returns_parsed_dict_on_success():
    payload = {"verdict": "insufficient_evidence"}
    response = _fake_response(json.dumps(payload))
    client, _ = _mock_client_returning(response)
    with patch("anthropic.Anthropic", return_value=client):
        result = AnthropicCommitteeProvider().complete_json(
            system_prompt="system", input_payload={"a": 1}, response_schema={"type": "object"},
            timeout_seconds=30.0,
        )
    assert result == payload


def test_complete_json_passes_timeout_and_disables_retries():
    response = _fake_response(json.dumps({}))
    client, _ = _mock_client_returning(response)
    with patch("anthropic.Anthropic", return_value=client):
        AnthropicCommitteeProvider().complete_json(
            system_prompt="system", input_payload={}, response_schema={},
            timeout_seconds=42.0,
        )
    client.with_options.assert_called_once_with(timeout=42.0, max_retries=0)


@pytest.mark.parametrize(
    "exc_factory, expected_code",
    [
        (lambda: anthropic.RateLimitError("rate limited", response=httpx.Response(429, request=_fake_request()), body=None), "rate_limited"),
        (lambda: anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=_fake_request()), body=None), "auth_failed"),
        (lambda: anthropic.APITimeoutError(request=_fake_request()), "timeout"),
    ],
)
def test_known_sdk_exceptions_map_to_specific_error_codes(exc_factory, expected_code):
    client, _ = _mock_client_raising(exc_factory())
    with patch("anthropic.Anthropic", return_value=client):
        with pytest.raises(CommitteeProviderError) as exc_info:
            AnthropicCommitteeProvider().complete_json(
                system_prompt="s", input_payload={}, response_schema={}, timeout_seconds=1.0,
            )
    assert exc_info.value.code == expected_code


def test_generic_sdk_exception_propagates_uncaught():
    # Independent review, 2026-07-31: run_committee_review()'s own bare
    # `except Exception` already maps any unrecognized exception to a
    # generic "provider_error" without leaking its message -- duplicating
    # that handling here would add surface area for no benefit. Confirm
    # this provider deliberately does NOT catch an unrecognized anthropic
    # exception type.
    client, _ = _mock_client_raising(
        anthropic.APIConnectionError(request=_fake_request())
    )
    with patch("anthropic.Anthropic", return_value=client):
        with pytest.raises(anthropic.APIConnectionError):
            AnthropicCommitteeProvider().complete_json(
                system_prompt="s", input_payload={}, response_schema={}, timeout_seconds=1.0,
            )


def test_refusal_stop_reason_raises_committee_provider_error():
    response = _fake_response("", stop_reason="refusal")
    response.stop_details = MagicMock(explanation="policy category: cyber")
    client, _ = _mock_client_returning(response)
    with patch("anthropic.Anthropic", return_value=client):
        with pytest.raises(CommitteeProviderError) as exc_info:
            AnthropicCommitteeProvider().complete_json(
                system_prompt="s", input_payload={}, response_schema={}, timeout_seconds=1.0,
            )
    assert exc_info.value.code == "refusal"


def test_empty_content_raises_committee_provider_error():
    response = MagicMock()
    response.content = []
    response.stop_reason = "end_turn"
    client, _ = _mock_client_returning(response)
    with patch("anthropic.Anthropic", return_value=client):
        with pytest.raises(CommitteeProviderError) as exc_info:
            AnthropicCommitteeProvider().complete_json(
                system_prompt="s", input_payload={}, response_schema={}, timeout_seconds=1.0,
            )
    assert exc_info.value.code == "empty_response"


def test_invalid_json_raises_committee_provider_error():
    response = _fake_response("not valid json {")
    client, _ = _mock_client_returning(response)
    with patch("anthropic.Anthropic", return_value=client):
        with pytest.raises(CommitteeProviderError) as exc_info:
            AnthropicCommitteeProvider().complete_json(
                system_prompt="s", input_payload={}, response_schema={}, timeout_seconds=1.0,
            )
    assert exc_info.value.code == "invalid_json"


def test_provider_id_and_model_id_attrs():
    provider = AnthropicCommitteeProvider()
    assert provider.provider_id == "anthropic"
    assert provider.model_id == "claude-opus-5"
