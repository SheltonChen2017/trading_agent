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


def _allocation_payload(summary, observations=()):
    return json.dumps({"summary": summary, "observations": list(observations)})


def test_review_allocation_plan_returns_structured_review_on_success(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload(
        "This split is concentrated in semiconductors.",
        [{"type": "concentration", "severity": "high", "claim": "Both are semiconductor names.", "tickers": ["NVDA", "AMD"]}],
    )
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(
            ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {"NVDA": 2.0, "AMD": 2.5}, {"NVDA": ["semiconductors"], "AMD": ["semiconductors"]}
        )
    assert result.summary == "This split is concentrated in semiconductors."
    assert len(result.observations) == 1
    assert result.observations[0].type == "concentration"
    assert result.observations[0].tickers == ("NVDA", "AMD")


def test_review_allocation_plan_rejects_summary_with_fabricated_percentage(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload("Consider reducing NVDA to 30% and adding AMD at 15%.")
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(
            ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {"NVDA": 2.0, "AMD": 2.5}, {}
        )
    assert result is None


def test_review_allocation_plan_rejects_summary_with_dollar_amount(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload("Allocate $500 more to AMD.")
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}, {})
    assert result is None


def test_review_allocation_plan_drops_observation_mentioning_unknown_ticker(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload(
        "Reasonable split.",
        [
            {"type": "concentration", "severity": "high", "claim": "Both are semis.", "tickers": ["NVDA", "AMD"]},
            {"type": "concentration", "severity": "low", "claim": "TSLA is unrelated.", "tickers": ["TSLA"]},
        ],
    )
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(
            ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}, {}
        )
    assert len(result.observations) == 1
    assert result.observations[0].tickers == ("NVDA", "AMD")


def test_review_allocation_plan_drops_observation_with_disallowed_type(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload(
        "Reasonable split.",
        [
            {"type": "buy_recommendation", "severity": "high", "claim": "Buy more AMD.", "tickers": ["AMD"]},
            {"type": "concentration", "severity": "medium", "claim": "AMD and NVDA are both semiconductors.", "tickers": ["AMD", "NVDA"]},
        ],
    )
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}, {})
    assert len(result.observations) == 1
    assert result.observations[0].type == "concentration"


def test_review_allocation_plan_rejects_whole_response_when_all_observations_fail_validation(monkeypatch):
    # independent review: dropping the one bad observation and silently
    # displaying the summary as "reviewed, nothing flagged" would misrepresent
    # what actually happened -- the model DID try to flag something, and it
    # was invalid; that's different from "nothing to flag" and must not look
    # like a clean bill of health.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload(
        "Reasonable split.",
        [{"type": "buy_recommendation", "severity": "high", "claim": "Buy more AMD.", "tickers": ["AMD"]}],
    )
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}, {})
    assert result is None


def test_review_allocation_plan_accepts_genuinely_empty_observations(monkeypatch):
    # The model returning zero observations from the start ("nothing notable")
    # is a legitimate result and must NOT be rejected by the all-filtered-out rule.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload("Well-diversified split, nothing notable.", [])
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}, {})
    assert result is not None
    assert result.observations == ()


def test_review_allocation_plan_rejects_summary_mentioning_unlisted_ticker(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload("Buy TSLA to improve this basket.", [])
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}, {})
    assert result is None


def test_review_allocation_plan_drops_claim_mentioning_ticker_outside_its_own_scope(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload(
        "Reasonable split.",
        [
            {"type": "diversification", "severity": "high", "claim": "TSLA would provide better diversification.", "tickers": ["NVDA"]},
            {"type": "concentration", "severity": "low", "claim": "Both are semiconductor names.", "tickers": ["NVDA", "AMD"]},
        ],
    )
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}, {})
    assert len(result.observations) == 1
    assert "semiconductor" in result.observations[0].claim


def test_review_allocation_plan_rejects_action_language_even_without_a_number(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload(
        "Reasonable split.",
        [
            {"type": "concentration", "severity": "high", "claim": "Sell NVDA and replace it with cash.", "tickers": ["NVDA"]},
            {"type": "concentration", "severity": "low", "claim": "Both are semiconductor names.", "tickers": ["NVDA", "AMD"]},
        ],
    )
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}, {})
    assert len(result.observations) == 1
    assert "semiconductor" in result.observations[0].claim


def test_review_allocation_plan_rejects_a_different_tickers_weight_reused_as_a_number(monkeypatch):
    # independent review: "reduce NVDA by 40%" would pass the OLD validator
    # because 40 is a real input weight -- it's just AMD's weight, not NVDA's.
    # Scoping the allowed numbers to each observation's OWN tickers closes this.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload(
        "Reasonable split.",
        [
            {"type": "concentration", "severity": "high", "claim": "Reduce NVDA by 40%.", "tickers": ["NVDA"]},
            {"type": "concentration", "severity": "low", "claim": "Both are semiconductor names.", "tickers": ["NVDA", "AMD"]},
        ],
    )
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}, {})
    assert len(result.observations) == 1
    assert "semiconductor" in result.observations[0].claim


def test_review_allocation_plan_allows_a_legitimate_volatility_restatement(monkeypatch):
    # independent review: the old validator only allowed WEIGHT numbers, so
    # a claim honestly restating the supplied volatility would be rejected.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload(
        "Reasonable split.",
        [{"type": "volatility", "severity": "medium", "claim": "NVDA has 2.50% trailing volatility.", "tickers": ["NVDA"]}],
    )
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(
            ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {"NVDA": 2.5, "AMD": 3.0}, {}
        )
    assert len(result.observations) == 1


def test_review_allocation_plan_allows_claim_restating_actual_weight(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload(
        "Reasonable split.",
        [{"type": "concentration", "severity": "medium", "claim": "NVDA is about 60% of the split.", "tickers": ["NVDA"]}],
    )
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}, {})
    assert len(result.observations) == 1


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


# --- AI-run persistence (independent review: AI calls weren't persisted
# anywhere -- model/prompt version/input hash/latency/response/success
# were all unrecoverable after the fact). Uses a real AssistantStore in a
# tempdir rather than mocking, so the actual ai_runs row shape is checked.

def test_review_allocation_plan_persists_a_successful_run(monkeypatch, tmp_path):
    from assistant.storage import AssistantStore

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload("Reasonable split.")
    store = AssistantStore(tmp_path / "assistant.db")
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        ai_advisor.review_allocation_plan(["AAPL"], {"AAPL": 100.0}, {}, {}, store=store)
    runs = store.list_ai_runs(function_name="review_allocation_plan")
    assert len(runs) == 1
    assert runs[0]["success"] is True
    assert runs[0]["model"] == "claude-opus-5"
    assert runs[0]["latency_ms"] >= 0


def test_review_allocation_plan_persists_a_failed_run_with_error(monkeypatch, tmp_path):
    from assistant.storage import AssistantStore

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    store = AssistantStore(tmp_path / "assistant.db")
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")
        mock_anthropic_cls.return_value = mock_client
        ai_advisor.review_allocation_plan(["AAPL"], {"AAPL": 100.0}, {}, {}, store=store)
    runs = store.list_ai_runs(function_name="review_allocation_plan")
    assert len(runs) == 1
    assert runs[0]["success"] is False
    assert runs[0]["error"] == "API error"


def test_review_allocation_plan_with_no_store_does_not_raise(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = _allocation_payload("Fine.")
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.review_allocation_plan(["AAPL"], {"AAPL": 100.0}, {}, {}, store=None)
    assert result.summary == "Fine."


def test_suggest_similar_tickers_persists_a_run(monkeypatch, tmp_path):
    from assistant.storage import AssistantStore

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    store = AssistantStore(tmp_path / "assistant.db")
    payload = json.dumps({"suggestions": [{"ticker": "AMD", "reason": "peer"}]})
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        ai_advisor.suggest_similar_tickers(["NVDA"], store=store)
    runs = store.list_ai_runs(function_name="suggest_similar_tickers")
    assert len(runs) == 1
    assert runs[0]["response"] == [{"ticker": "AMD", "reason": "peer"}]


def test_curate_recommended_tickers_persists_a_run(monkeypatch, tmp_path):
    from assistant.storage import AssistantStore

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    store = AssistantStore(tmp_path / "assistant.db")

    class _Candidate:
        ticker = "AMD"
        reason_category = "ai_suggested"
        detail = "peer"

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response("Worth a look.")
        mock_anthropic_cls.return_value = mock_client
        ai_advisor.curate_recommended_tickers([_Candidate()], store=store)
    runs = store.list_ai_runs(function_name="curate_recommended_tickers")
    assert len(runs) == 1
    assert runs[0]["response"] == "Worth a look."


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
    test_review_allocation_plan_returns_structured_review_on_success(mp)
    test_review_allocation_plan_rejects_summary_with_fabricated_percentage(mp)
    test_review_allocation_plan_rejects_summary_with_dollar_amount(mp)
    test_review_allocation_plan_drops_observation_mentioning_unknown_ticker(mp)
    test_review_allocation_plan_drops_observation_with_disallowed_type(mp)
    test_review_allocation_plan_rejects_whole_response_when_all_observations_fail_validation(mp)
    test_review_allocation_plan_accepts_genuinely_empty_observations(mp)
    test_review_allocation_plan_rejects_summary_mentioning_unlisted_ticker(mp)
    test_review_allocation_plan_drops_claim_mentioning_ticker_outside_its_own_scope(mp)
    test_review_allocation_plan_rejects_action_language_even_without_a_number(mp)
    test_review_allocation_plan_rejects_a_different_tickers_weight_reused_as_a_number(mp)
    test_review_allocation_plan_allows_a_legitimate_volatility_restatement(mp)
    test_review_allocation_plan_allows_claim_restating_actual_weight(mp)
    test_review_allocation_plan_returns_none_on_api_exception(mp)
    test_suggest_similar_tickers_returns_none_when_unconfigured(mp)
    test_suggest_similar_tickers_returns_parsed_list_on_success(mp)
    test_suggest_similar_tickers_returns_none_on_malformed_json(mp)
    test_suggest_similar_tickers_caps_at_max_suggestions(mp)
    test_suggest_similar_tickers_returns_none_on_api_exception(mp)
    test_curate_recommended_tickers_returns_none_when_no_candidates(mp)
    print("All ai_advisor tests passed (except the tmp_path-fixture persistence tests -- run via pytest for those).")
