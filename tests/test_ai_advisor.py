"""Tests for assistant/ai_advisor.py. Run with:
python tests/test_ai_advisor.py"""
import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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


# --- Direct _validate_allocation_review reproductions (independent review,
# third pass: unknown-ticker detection only rejected tokens that were ALSO
# config.UNIVERSE members, so a real-but-out-of-universe or hallucinated
# ticker like "RDDT" read as an innocent acronym; summary percentages were
# checked against the FULL cart pool, so a real weight could be reattached
# to the wrong ticker in prose; "should"/"deserves"/etc. weren't in the
# action-verb blocklist at all, or only matched the bare infinitive.)

def test_rejects_summary_with_unknown_external_ticker():
    raw = {"summary": "RDDT would improve diversification.", "observations": []}
    result = ai_advisor._validate_allocation_review(raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {})
    assert result is None


def test_rejects_summary_with_fabricated_ticker_symbol():
    raw = {"summary": "ZZQZX would improve diversification.", "observations": []}
    result = ai_advisor._validate_allocation_review(raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {})
    assert result is None


def test_rejects_summary_reassigning_another_tickers_weight():
    raw = {"summary": "NVDA should be 40% of the split.", "observations": []}
    result = ai_advisor._validate_allocation_review(raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {})
    assert result is None


def test_rejects_summary_advice_language_without_a_number():
    cases = [
        "NVDA ought to be smaller.",
        "AMD deserves a larger share.",
        "The portfolio would benefit from RDDT.",
        "Prefer AMD over NVDA.",
    ]
    for summary in cases:
        raw = {"summary": summary, "observations": []}
        result = ai_advisor._validate_allocation_review(raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {})
        assert result is None, f"expected rejection for: {summary!r}"


def test_rejects_multi_ticker_observation_reassigning_another_tickers_weight():
    # Independent review, 2026-07-31 (P2 #8): a multi-ticker observation's
    # allowed numbers used to be the UNION of every ticker in its
    # `tickers` field, so a claim entirely about NVDA could cite AMD's
    # real 40% weight (present in the union just because AMD is also
    # listed on this observation) instead of NVDA's own 60%.
    raw = {
        "summary": "This split is concentrated in semiconductors.",
        "observations": [
            {
                "type": "concentration",
                "severity": "medium",
                "claim": "NVDA is a large 40% position here.",  # 40% is AMD's weight, not NVDA's
                "tickers": ["NVDA", "AMD"],
            }
        ],
    }
    result = ai_advisor._validate_allocation_review(
        raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}
    )
    # The lone observation fails number validation, and per this
    # function's own "no false all-clear" rule, a response whose only
    # proposed observation was rejected is rejected wholesale.
    assert result is None


def test_allows_multi_ticker_observation_citing_each_tickers_own_weight():
    raw = {
        "summary": "This split is concentrated in semiconductors.",
        "observations": [
            {
                "type": "concentration",
                "severity": "medium",
                "claim": "NVDA is 60% while AMD is 40% of this split.",
                "tickers": ["NVDA", "AMD"],
            }
        ],
    }
    result = ai_advisor._validate_allocation_review(
        raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}
    )
    assert result is not None
    assert len(result.observations) == 1


def test_rejects_multi_ticker_observation_with_swapped_real_weights():
    raw = {
        "summary": "This split is concentrated in semiconductors.",
        "observations": [
            {
                "type": "concentration",
                "severity": "medium",
                "claim": "NVDA is 40% while AMD is 60% of this split.",
                "tickers": ["NVDA", "AMD"],
            }
        ],
    }

    result = ai_advisor._validate_allocation_review(
        raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}
    )

    assert result is None


def test_allows_benign_summary_with_no_ticker_dollar_or_advice_language():
    raw = {"summary": "This split is concentrated in semiconductors.", "observations": []}
    result = ai_advisor._validate_allocation_review(raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {})
    assert result is not None


# --- Overblocking fix (independent review, fourth pass): the third pass's
# blanket \w* verb stems (allocat\w*, target\w*, increas\w*, reduc\w*) caught
# ordinary descriptive prose along with real advice, e.g. "This allocation is
# concentrated in semiconductors." and "The target volatility is elevated."
# were both wrongly rejected. Action-verb detection is now split into
# unambiguous verbs (buy/sell/rebalance/replace), advice markers (should/
# consider/prefer/deserve/...), and context-sensitive verbs (allocate/
# increase/reduce/target) that only count as advice when paired with an
# actual change-object (position/weight/exposure noun, a comparative, or a
# percentage) nearby.

def test_allows_summary_using_allocation_as_a_noun():
    raw = {
        "summary": "This allocation is concentrated in semiconductors.",
        "observations": [],
    }
    result = ai_advisor._validate_allocation_review(
        raw,
        ["NVDA", "AMD"],
        {"NVDA": 60.0, "AMD": 40.0},
        {},
    )
    assert result is not None


def test_allows_summary_using_target_descriptively():
    raw = {
        "summary": "The volatility target is based on trailing data.",
        "observations": [],
    }
    result = ai_advisor._validate_allocation_review(
        raw,
        ["NVDA", "AMD"],
        {"NVDA": 60.0, "AMD": 40.0},
        {},
    )
    assert result is not None


def test_allows_descriptive_relative_position_size():
    raw = {
        "summary": "NVDA is a larger position than AMD in this portfolio.",
        "observations": [],
    }
    result = ai_advisor._validate_allocation_review(
        raw,
        ["NVDA", "AMD"],
        {"NVDA": 60.0, "AMD": 40.0},
        {},
    )
    assert result is not None


def test_allows_observation_describing_increased_volatility():
    raw = {
        "summary": "The split has differing volatility characteristics.",
        "observations": [
            {
                "type": "volatility",
                "severity": "medium",
                "claim": "NVDA has increased volatility relative to its recent behavior.",
                "tickers": ["NVDA"],
            }
        ],
    }
    result = ai_advisor._validate_allocation_review(
        raw,
        ["NVDA", "AMD"],
        {"NVDA": 60.0, "AMD": 40.0},
        {"NVDA": 2.5, "AMD": 1.5},
    )
    assert result is not None
    assert len(result.observations) == 1


@pytest.mark.parametrize(
    "summary",
    [
        "Allocate more to NVDA.",
        "Increase the NVDA position.",
        "Reduce AMD exposure.",
        "Target a larger NVDA weight.",
        "Consider increasing NVDA.",
        "NVDA deserves a larger allocation.",
        "Prefer NVDA over AMD.",
        "The portfolio would benefit from more NVDA exposure.",
    ],
)
def test_rejects_explicit_allocation_advice(summary):
    raw = {"summary": summary, "observations": []}
    assert ai_advisor._validate_allocation_review(
        raw,
        ["NVDA", "AMD"],
        {"NVDA": 60.0, "AMD": 40.0},
        {},
    ) is None


@pytest.mark.parametrize(
    "summary",
    [
        "RDDT would improve diversification.",
        "ZZQZX would improve diversification.",
        "NVDA should be 40% of the split.",
        "AMD deserves a larger share.",
    ],
)
def test_rejects_previously_reproduced_bypasses(summary):
    raw = {"summary": summary, "observations": []}
    assert ai_advisor._validate_allocation_review(
        raw,
        ["NVDA", "AMD"],
        {"NVDA": 60.0, "AMD": 40.0},
        {},
    ) is None


# --- Ticker-directed action + modal/passive bypass (independent review,
# fifth pass): tier 4's trigger nouns (position/weight/share/exposure/
# holding/allocation/comparatives/percentages) never included a bare ticker
# symbol, so "Increase NVDA." carried no recognized trigger at all; modal/
# passive constructions ("We can increase NVDA.", "AMD could be reduced.")
# carried no trigger either. Also fixed: the percentage alternative had a
# trailing \b appended after "%", which never matches (% is not a word
# char), so "Target NVDA at 60%." silently bypassed the percent trigger too.

@pytest.mark.parametrize(
    "summary",
    [
        "Increase NVDA.",
        "Reduce AMD.",
        "Allocate NVDA.",
        "We can increase NVDA.",
        "We could reduce AMD.",
        "NVDA can be increased.",
        "AMD could be reduced.",
        "Please increase NVDA.",
        "Increase NVDA and reduce AMD.",
    ],
)
def test_rejects_ticker_directed_allocation_actions_in_summary(summary):
    raw = {"summary": summary, "observations": []}
    assert ai_advisor._validate_allocation_review(
        raw,
        ["NVDA", "AMD"],
        {"NVDA": 60.0, "AMD": 40.0},
        {},
    ) is None


@pytest.mark.parametrize(
    "claim,tickers",
    [
        ("Increase NVDA.", ["NVDA"]),
        ("Reduce AMD.", ["AMD"]),
        ("Allocate NVDA.", ["NVDA"]),
        ("Target NVDA at 60%.", ["NVDA"]),
        ("We can increase NVDA.", ["NVDA"]),
        ("We could reduce AMD.", ["AMD"]),
        ("NVDA can be increased.", ["NVDA"]),
        ("AMD could be reduced.", ["AMD"]),
        ("Please increase NVDA.", ["NVDA"]),
        ("Increase NVDA and reduce AMD.", ["NVDA", "AMD"]),
    ],
)
def test_rejects_ticker_directed_allocation_actions_in_observation_claim(claim, tickers):
    raw = {
        "summary": "The computed split has been reviewed.",
        "observations": [
            {"type": "concentration", "severity": "medium", "claim": claim, "tickers": tickers}
        ],
    }
    result = ai_advisor._validate_allocation_review(
        raw,
        ["NVDA", "AMD"],
        {"NVDA": 60.0, "AMD": 40.0},
        {},
    )
    assert result is None


@pytest.mark.parametrize(
    "summary",
    [
        "This allocation is concentrated in semiconductors.",
        "The volatility target is based on trailing data.",
        "The allocation has reduced diversification.",
    ],
)
def test_allows_descriptive_allocation_language_in_summary(summary):
    raw = {"summary": summary, "observations": []}
    result = ai_advisor._validate_allocation_review(
        raw,
        ["NVDA", "AMD"],
        {"NVDA": 60.0, "AMD": 40.0},
        {},
    )
    assert result is not None


@pytest.mark.parametrize(
    "claim,tickers",
    [
        ("NVDA has increased volatility relative to its recent behavior.", ["NVDA"]),
        ("AMD has reduced correlation with NVDA over the sampled period.", ["AMD", "NVDA"]),
    ],
)
def test_allows_descriptive_change_verbs_in_observations(claim, tickers):
    raw = {
        "summary": "The split has differing characteristics.",
        "observations": [
            {"type": "volatility", "severity": "medium", "claim": claim, "tickers": tickers}
        ],
    }
    result = ai_advisor._validate_allocation_review(
        raw,
        ["NVDA", "AMD"],
        {"NVDA": 60.0, "AMD": 40.0},
        {"NVDA": 2.5, "AMD": 1.5},
    )
    assert result is not None
    assert len(result.observations) == 1


# --- Lowercase-ticker and action-synonym bypass (independent review, sixth
# pass): the ticker-directed check matched ONLY exact-case tickers, so
# "Increase nvda." bypassed it entirely (lowercase "nvda" isn't caught by
# the unknown-ticker scanner either, since that only looks at uppercase-
# shaped tokens -- correctly, since ordinary lowercase words shouldn't be
# treated as tickers). And _SIZE_CHANGE_VERBS only covered allocate/
# increase/reduce/target -- ordinary synonyms (add/raise/boost/trim/cut/
# lower/shift/move/...) and intervening portfolio-object phrases (stake,
# "amount invested", capital, funds, holding) were never recognized as
# advisory triggers at all.

def _obs_reject(claim, tickers):
    raw = {
        "summary": "The computed split has been reviewed.",
        "observations": [
            {"type": "concentration", "severity": "medium", "claim": claim, "tickers": tickers}
        ],
    }
    result = ai_advisor._validate_allocation_review(
        raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}
    )
    return result is None or len(result.observations) == 0


@pytest.mark.parametrize(
    "summary",
    [
        "Increase nvda.",
        "Reduce amd.",
        "Raise Nvda.",
        "Trim aMd.",
    ],
)
def test_rejects_lowercase_or_mixed_case_ticker_instructions_in_summary(summary):
    raw = {"summary": summary, "observations": []}
    assert ai_advisor._validate_allocation_review(
        raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}
    ) is None


@pytest.mark.parametrize(
    "claim,tickers",
    [
        ("Increase nvda.", ["NVDA"]),
        ("Reduce amd.", ["AMD"]),
        ("Raise Nvda.", ["NVDA"]),
        ("Trim aMd.", ["AMD"]),
    ],
)
def test_rejects_lowercase_or_mixed_case_ticker_instructions_in_observation_claim(claim, tickers):
    assert _obs_reject(claim, tickers)


@pytest.mark.parametrize(
    "summary",
    [
        "Raise NVDA.",
        "Boost NVDA.",
        "Add NVDA.",
        "Trim AMD.",
        "Cut AMD.",
        "Lower AMD.",
        "Exit AMD.",
        "Overweight NVDA.",
        "Underweight AMD.",
        "Shift capital to NVDA.",
        "Move exposure from AMD to NVDA.",
        "Rotate from AMD into NVDA.",
    ],
)
def test_rejects_action_synonyms_in_summary(summary):
    raw = {"summary": summary, "observations": []}
    assert ai_advisor._validate_allocation_review(
        raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}
    ) is None


@pytest.mark.parametrize(
    "summary",
    [
        "Increase our stake in NVDA.",
        "Reduce the amount invested in AMD.",
        "Raise the portfolio's NVDA holding.",
        "Lower the current allocation assigned to AMD.",
        "Move a portion of the available capital to NVDA.",
    ],
)
def test_rejects_intervening_portfolio_object_phrases_in_summary(summary):
    raw = {"summary": summary, "observations": []}
    assert ai_advisor._validate_allocation_review(
        raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}
    ) is None


@pytest.mark.parametrize(
    "summary",
    [
        "We can raise NVDA.",
        "NVDA could be boosted.",
        "AMD may be trimmed.",
        "The AMD holding might be lowered.",
        "We could gradually add NVDA.",
    ],
)
def test_rejects_modal_and_passive_action_synonyms_in_summary(summary):
    raw = {"summary": summary, "observations": []}
    assert ai_advisor._validate_allocation_review(
        raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}
    ) is None


@pytest.mark.parametrize(
    "summary",
    [
        "This allocation is concentrated in semiconductors.",
        "The volatility target is based on trailing data.",
        "The allocation has reduced diversification.",
    ],
)
def test_allows_descriptive_allocation_language_sixth_pass(summary):
    raw = {"summary": summary, "observations": []}
    result = ai_advisor._validate_allocation_review(
        raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}
    )
    assert result is not None


@pytest.mark.parametrize(
    "claim,tickers",
    [
        ("NVDA has increased volatility relative to its recent behavior.", ["NVDA"]),
        ("AMD has reduced correlation with NVDA over the sampled period.", ["AMD", "NVDA"]),
    ],
)
def test_allows_descriptive_change_verbs_sixth_pass(claim, tickers):
    assert not _obs_reject(claim, tickers)


@pytest.mark.parametrize(
    "summary",
    [
        "NVDA raised its revenue guidance.",
        "AMD cut operating expenses.",
        "NVDA added a new product category.",
        "AMD lowered its reported debt.",
    ],
)
def test_allows_company_business_facts_using_advisory_looking_verbs(summary):
    # These verbs (raised/cut/added/lowered) are only advisory when they
    # govern a ticker/portfolio-object as a proposed CHANGE TARGET -- here
    # the ticker is the grammatical SUBJECT of a fact about the underlying
    # business, not the object of a proposed portfolio action.
    raw = {"summary": summary, "observations": []}
    result = ai_advisor._validate_allocation_review(
        raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}
    )
    assert result is not None


@pytest.mark.parametrize(
    "summary",
    [
        # Independent adversarial probe, 2026-07-29: every one of these
        # carried a concrete allocation recommendation and passed all six
        # existing guardrail layers -- advisability adjectives and
        # size-change synonyms the denylists simply didn't enumerate.
        "NVDA warrants a bigger slice of the portfolio.",
        "It may be prudent to scale back NVDA.",
        "Scaling into AMD is sensible.",
        "A tilt toward AMD is advisable.",
        "You might want to offload some NVDA.",
        "NVDA looks like a candidate for downsizing.",
        "Dial back NVDA.",
        "Take some profits in NVDA.",
        "Divest part of the AMD position.",
        "Paring NVDA is worth considering.",
    ],
)
def test_rejects_advisability_and_size_synonym_bypasses_in_summary(summary):
    raw = {"summary": summary, "observations": []}
    assert ai_advisor._validate_allocation_review(
        raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}
    ) is None


@pytest.mark.parametrize(
    "claim,tickers",
    [
        ("NVDA warrants a larger share of the split.", ["NVDA"]),
        ("Offload part of the AMD leg.", ["AMD"]),
        ("Dial back NVDA.", ["NVDA"]),
    ],
)
def test_rejects_advisability_bypasses_in_observation_claim(claim, tickers):
    assert _obs_reject(claim, tickers)


@pytest.mark.parametrize(
    "summary",
    [
        # The widened lists must not start blocking neutral description.
        # "scaled" here is a fact about the business, not a proposed
        # portfolio change, and carries no advisability marker.
        "NVDA has scaled its manufacturing operations.",
        "The split has differing characteristics.",
        "AMD reported a sensible-sounding restructuring plan.",
    ],
)
def test_allows_descriptive_text_after_widening_the_denylists(summary):
    raw = {"summary": summary, "observations": []}
    assert ai_advisor._validate_allocation_review(
        raw, ["NVDA", "AMD"], {"NVDA": 60.0, "AMD": 40.0}, {}
    ) is not None


def test_size_change_verb_group_never_matches_the_empty_string():
    # A stray "||" while widening this alternation would make every
    # consumer of the group match anywhere, silently blocking all output.
    assert "||" not in ai_advisor._SIZE_CHANGE_VERBS
    assert not re.compile(ai_advisor._SIZE_CHANGE_VERBS).fullmatch("")


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
    test_rejects_summary_with_unknown_external_ticker()
    test_rejects_summary_with_fabricated_ticker_symbol()
    test_rejects_summary_reassigning_another_tickers_weight()
    test_rejects_summary_advice_language_without_a_number()
    test_allows_benign_summary_with_no_ticker_dollar_or_advice_language()
    test_allows_summary_using_allocation_as_a_noun()
    test_allows_summary_using_target_descriptively()
    test_allows_observation_describing_increased_volatility()
    for _summary in [
        "Allocate more to NVDA.",
        "Increase the NVDA position.",
        "Reduce AMD exposure.",
        "Target a larger NVDA weight.",
        "Consider increasing NVDA.",
        "NVDA deserves a larger allocation.",
        "Prefer NVDA over AMD.",
        "The portfolio would benefit from more NVDA exposure.",
    ]:
        test_rejects_explicit_allocation_advice(_summary)
    for _summary in [
        "RDDT would improve diversification.",
        "ZZQZX would improve diversification.",
        "NVDA should be 40% of the split.",
        "AMD deserves a larger share.",
    ]:
        test_rejects_previously_reproduced_bypasses(_summary)
    for _summary in [
        "Increase NVDA.",
        "Reduce AMD.",
        "Allocate NVDA.",
        "We can increase NVDA.",
        "We could reduce AMD.",
        "NVDA can be increased.",
        "AMD could be reduced.",
        "Please increase NVDA.",
        "Increase NVDA and reduce AMD.",
    ]:
        test_rejects_ticker_directed_allocation_actions_in_summary(_summary)
    for _claim, _tickers in [
        ("Increase NVDA.", ["NVDA"]),
        ("Reduce AMD.", ["AMD"]),
        ("Allocate NVDA.", ["NVDA"]),
        ("Target NVDA at 60%.", ["NVDA"]),
        ("We can increase NVDA.", ["NVDA"]),
        ("We could reduce AMD.", ["AMD"]),
        ("NVDA can be increased.", ["NVDA"]),
        ("AMD could be reduced.", ["AMD"]),
        ("Please increase NVDA.", ["NVDA"]),
        ("Increase NVDA and reduce AMD.", ["NVDA", "AMD"]),
    ]:
        test_rejects_ticker_directed_allocation_actions_in_observation_claim(_claim, _tickers)
    for _summary in [
        "This allocation is concentrated in semiconductors.",
        "The volatility target is based on trailing data.",
        "The allocation has reduced diversification.",
    ]:
        test_allows_descriptive_allocation_language_in_summary(_summary)
    for _claim, _tickers in [
        ("NVDA has increased volatility relative to its recent behavior.", ["NVDA"]),
        ("AMD has reduced correlation with NVDA over the sampled period.", ["AMD", "NVDA"]),
    ]:
        test_allows_descriptive_change_verbs_in_observations(_claim, _tickers)
    for _summary in ["Increase nvda.", "Reduce amd.", "Raise Nvda.", "Trim aMd."]:
        test_rejects_lowercase_or_mixed_case_ticker_instructions_in_summary(_summary)
    for _claim, _tickers in [
        ("Increase nvda.", ["NVDA"]),
        ("Reduce amd.", ["AMD"]),
        ("Raise Nvda.", ["NVDA"]),
        ("Trim aMd.", ["AMD"]),
    ]:
        test_rejects_lowercase_or_mixed_case_ticker_instructions_in_observation_claim(_claim, _tickers)
    for _summary in [
        "Raise NVDA.", "Boost NVDA.", "Add NVDA.", "Trim AMD.", "Cut AMD.", "Lower AMD.",
        "Exit AMD.", "Overweight NVDA.", "Underweight AMD.", "Shift capital to NVDA.",
        "Move exposure from AMD to NVDA.", "Rotate from AMD into NVDA.",
    ]:
        test_rejects_action_synonyms_in_summary(_summary)
    for _summary in [
        "Increase our stake in NVDA.", "Reduce the amount invested in AMD.",
        "Raise the portfolio's NVDA holding.", "Lower the current allocation assigned to AMD.",
        "Move a portion of the available capital to NVDA.",
    ]:
        test_rejects_intervening_portfolio_object_phrases_in_summary(_summary)
    for _summary in [
        "We can raise NVDA.", "NVDA could be boosted.", "AMD may be trimmed.",
        "The AMD holding might be lowered.", "We could gradually add NVDA.",
    ]:
        test_rejects_modal_and_passive_action_synonyms_in_summary(_summary)
    for _summary in [
        "This allocation is concentrated in semiconductors.",
        "The volatility target is based on trailing data.",
        "The allocation has reduced diversification.",
    ]:
        test_allows_descriptive_allocation_language_sixth_pass(_summary)
    for _claim, _tickers in [
        ("NVDA has increased volatility relative to its recent behavior.", ["NVDA"]),
        ("AMD has reduced correlation with NVDA over the sampled period.", ["AMD", "NVDA"]),
    ]:
        test_allows_descriptive_change_verbs_sixth_pass(_claim, _tickers)
    for _summary in [
        "NVDA raised its revenue guidance.", "AMD cut operating expenses.",
        "NVDA added a new product category.", "AMD lowered its reported debt.",
    ]:
        test_allows_company_business_facts_using_advisory_looking_verbs(_summary)
    test_review_allocation_plan_returns_none_on_api_exception(mp)
    test_suggest_similar_tickers_returns_none_when_unconfigured(mp)
    test_suggest_similar_tickers_returns_parsed_list_on_success(mp)
    test_suggest_similar_tickers_returns_none_on_malformed_json(mp)
    test_suggest_similar_tickers_caps_at_max_suggestions(mp)
    test_suggest_similar_tickers_returns_none_on_api_exception(mp)
    test_curate_recommended_tickers_returns_none_when_no_candidates(mp)
    print("All ai_advisor tests passed (except the tmp_path-fixture persistence tests -- run via pytest for those).")


def test_free_text_surfaces_reject_trade_action_language():
    """curate_recommended_tickers / similar-ticker reasons / news summaries were
    PROMPT-guarded only -- nothing checked their output, unlike the allocation
    path (GPT review, 2026-07-29). They cannot trade, but could display
    ungrounded financial advice."""
    from assistant.ai_advisor import _reject_unsafe_prose

    allowed = {"NVDA", "AMD"}
    for advice in (
        "You should buy NVDA now.",
        "Consider trimming AMD.",
        "It would be prudent to increase your NVDA position.",
        "Take profits on NVDA.",
    ):
        assert _reject_unsafe_prose(advice, allowed, source_text="") is not None, advice


def test_free_text_surfaces_reject_tickers_outside_the_verified_set():
    from assistant.ai_advisor import _reject_unsafe_prose

    rejection = _reject_unsafe_prose(
        "NVDA and TSLA both design their own silicon.", {"NVDA", "AMD"}, source_text="",
    )
    assert rejection is not None
    assert "outside the verified" in rejection


def test_free_text_surfaces_allow_grounded_descriptive_prose():
    """The guard must not be so broad that it suppresses everything -- that
    would make the feature useless rather than safe."""
    from assistant.ai_advisor import _reject_unsafe_prose

    assert _reject_unsafe_prose(
        "NVDA and AMD both operate in the semiconductor category.", {"NVDA", "AMD"},
        source_text="",
    ) is None


# --- numeric grounding at the CALL SITES (independent review, 2026-07-30) ---
#
# suggest_similar_tickers() and curate_recommended_tickers() both called
# _reject_unsafe_prose() WITHOUT source_text, so its number check never ran on
# either surface -- while the system prompt told the model every number it
# wrote would be checked. These are integration tests against the public
# functions, not the helper, because the defect was a missing ARGUMENT at a
# call site: a helper-only test passes either way.

def test_similar_ticker_reasons_with_invented_numbers_are_dropped(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = json.dumps({"suggestions": [
        {"ticker": "AMD", "reason": "Also a semiconductor company"},
        # Deliberately free of action words: an earlier version of this test
        # used "Grew revenue 45% last quarter", which the ACTION-LANGUAGE
        # denylist rejected, so the test passed without ever exercising the
        # number check it was written for (caught by mutation testing).
        {"ticker": "INTC", "reason": "Also a semiconductor company with 45 fabrication sites"},
    ]})
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(payload)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.suggest_similar_tickers(["NVDA"])
    assert result == [{"ticker": "AMD", "reason": "Also a semiconductor company"}]


def test_curated_recommendation_prose_with_an_invented_number_is_suppressed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class _Candidate:
        ticker = "AMD"
        reason_category = "momentum"
        detail = "appeared in a screen"

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(
            "AMD looks worth a closer look after rising 32% this month."
        )
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.curate_recommended_tickers([_Candidate()])
    assert result is None


def test_curated_recommendation_prose_grounded_in_the_candidate_list_passes(monkeypatch):
    """The guard must reject invented figures without rejecting everything."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class _Candidate:
        ticker = "AMD"
        reason_category = "momentum"
        detail = "appeared in a screen"

    grounded = "AMD appeared in a screen and looks worth a closer look."
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response(grounded)
        mock_anthropic_cls.return_value = mock_client
        result = ai_advisor.curate_recommended_tickers([_Candidate()])
    assert result == grounded
