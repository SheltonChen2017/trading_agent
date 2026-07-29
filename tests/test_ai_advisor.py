"""Tests for assistant/ai_advisor.py. Run with:
python tests/test_ai_advisor.py"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant import ai_advisor


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


def _fake_response(text):
    response = MagicMock()
    response.content = [_FakeTextBlock(text)]
    return response


def test_is_ai_advisor_configured_false_when_key_unset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ai_advisor.is_ai_advisor_configured() is False


def test_is_ai_advisor_configured_true_when_key_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert ai_advisor.is_ai_advisor_configured() is True


def test_review_allocation_plan_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = ai_advisor.review_allocation_plan(["AAPL"], {"AAPL": 100.0}, {"AAPL": 1.0}, {"AAPL": ["tech"]})
    assert result is None


def test_review_allocation_plan_returns_none_when_no_tickers(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert ai_advisor.review_allocation_plan([], {}, {}, {}) is None


def test_review_allocation_plan_returns_text_on_success(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response("This split is concentrated in semiconductors.")
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(
            ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {"NVDA": 2.0, "AMD": 2.5}, {"NVDA": ["semiconductors"], "AMD": ["semiconductors"]}
        )
    assert result == "This split is concentrated in semiconductors."


def test_review_allocation_plan_returns_none_on_api_exception(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(["AAPL"], {"AAPL": 100.0}, {"AAPL": 1.0}, {"AAPL": []})
    assert result is None


def test_suggest_similar_tickers_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ai_advisor.suggest_similar_tickers(["NVDA"]) is None


def test_suggest_similar_tickers_returns_parsed_list_on_success(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = json.dumps({"suggestions": [{"ticker": "AMD", "reason": "Also a semiconductor company"}]})
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.suggest_similar_tickers(["NVDA"])
    assert result == [{"ticker": "AMD", "reason": "Also a semiconductor company"}]


def test_suggest_similar_tickers_returns_none_on_malformed_json(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response("not valid json")
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.suggest_similar_tickers(["NVDA"])
    assert result is None


def test_suggest_similar_tickers_caps_at_max_suggestions(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = json.dumps({"suggestions": [{"ticker": t, "reason": "r"} for t in ["A", "B", "C", "D"]]})
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.suggest_similar_tickers(["NVDA"], max_suggestions=2)
    assert len(result) == 2


def test_suggest_similar_tickers_returns_none_on_api_exception(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.suggest_similar_tickers(["NVDA"])
    assert result is None


def test_curate_recommended_tickers_returns_none_when_no_candidates(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert ai_advisor.curate_recommended_tickers([]) is None


if __name__ == "__main__":
    import types

    class _Dummy:
        pass

    # Minimal pytest-monkeypatch-free runner for direct execution.
    import os

    class _MonkeyPatch:
        def setenv(self, k, v):
            os.environ[k] = v

        def delenv(self, k, raising=False):
            os.environ.pop(k, None)

    mp = _MonkeyPatch()
    test_is_ai_advisor_configured_false_when_key_unset(mp)
    test_is_ai_advisor_configured_true_when_key_set(mp)
    test_review_allocation_plan_returns_none_when_unconfigured(mp)
    test_review_allocation_plan_returns_none_when_no_tickers(mp)
    test_review_allocation_plan_returns_text_on_success(mp)
    test_review_allocation_plan_returns_none_on_api_exception(mp)
    test_suggest_similar_tickers_returns_none_when_unconfigured(mp)
    test_suggest_similar_tickers_returns_parsed_list_on_success(mp)
    test_suggest_similar_tickers_returns_none_on_malformed_json(mp)
    test_suggest_similar_tickers_caps_at_max_suggestions(mp)
    test_suggest_similar_tickers_returns_none_on_api_exception(mp)
    test_curate_recommended_tickers_returns_none_when_no_candidates(mp)
    print("All ai_advisor tests passed.")
