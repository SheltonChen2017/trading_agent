"""End-to-end test of run_committee_review() with the REAL
AnthropicCommitteeProvider, mocked only at the SDK boundary (not
_FakeProvider) -- proves the adapter's complete_json() contract actually
satisfies what run_committee_review() expects, not just that the adapter's
own unit tests pass it in isolation."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assistant.llm.anthropic_provider import AnthropicCommitteeProvider
from assistant.llm.committee import run_committee_review
from assistant.llm.projection import project_committee_input
from assistant.llm.schemas import ReviewStatus
from test_committee_foundation import _packet, _proposal, _valid_raw_review  # noqa: E402


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


def _mock_client_returning(response):
    client = MagicMock()
    with_options_mock = MagicMock()
    client.with_options.return_value = with_options_mock
    with_options_mock.messages.create.return_value = response
    return client


def test_real_provider_end_to_end_accepted():
    response = _fake_response(json.dumps(_valid_raw_review()))
    client = _mock_client_returning(response)
    committee_input = project_committee_input(_packet(), _proposal())

    with patch("anthropic.Anthropic", return_value=client):
        result = run_committee_review(committee_input, AnthropicCommitteeProvider())

    assert result.status == ReviewStatus.ACCEPTED
    assert result.accepted
    assert result.provider_id == "anthropic"
    assert result.model_id == "claude-opus-5"


def test_real_provider_end_to_end_validation_rejected():
    raw = _valid_raw_review()
    raw["summary"]["source_ids"] = ["candidate.fabricated_metric"]
    response = _fake_response(json.dumps(raw))
    client = _mock_client_returning(response)
    committee_input = project_committee_input(_packet(), _proposal())

    with patch("anthropic.Anthropic", return_value=client):
        result = run_committee_review(committee_input, AnthropicCommitteeProvider())

    assert result.status == ReviewStatus.REVIEW_UNAVAILABLE
    assert result.error_code == "validation_rejected"
    assert not result.accepted


def test_real_provider_end_to_end_provider_error_fails_closed():
    client = MagicMock()
    client.with_options.return_value.messages.create.side_effect = RuntimeError("network down")
    committee_input = project_committee_input(_packet(), _proposal())

    with patch("anthropic.Anthropic", return_value=client):
        result = run_committee_review(committee_input, AnthropicCommitteeProvider())

    assert result.status == ReviewStatus.REVIEW_UNAVAILABLE
    assert result.error_code == "provider_error"
    assert "network down" not in (result.error_message or "")  # no leaked detail
