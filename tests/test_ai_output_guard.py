"""
Deterministic output guard for the free-text AI surfaces.

Two defects motivated this file (independent review, 2026-07-29):

1. summarize_news_for_ticker() returned the model's text unchanged. The
   guard's own docstring claimed to cover news summaries, but the function
   never called it -- so "You should buy NVDA now." would have been displayed
   verbatim despite the prompt forbidding it. A prompt is not enforcement.
   These are INTEGRATION tests against summarize_news_for_ticker() itself,
   not just unit tests of the helper, because that gap was precisely a
   missing call rather than a broken check.

2. The helper was named for guaranteeing factual grounding while checking
   neither grounding nor numbers. It now checks numbers against the supplied
   source, and is named for what it does. The residual limitation is
   asserted explicitly below rather than left implied.
"""
from __future__ import annotations

import os
import sys
import types

from assistant.ai_advisor import _reject_unsafe_prose, _unsupported_numbers

_HEADLINES = [
    {
        "title": "NVDA reports quarterly revenue of 30 billion",
        "summary": "The company said data-center demand drove the result.",
        "provider": "Reuters",
        "published": "2026-07-28",
        "url": "https://example.com/1",
    },
    {
        "title": "Analysts discuss AMD competition in accelerators",
        "summary": "Coverage notes a competitive dynamic with NVDA.",
        "provider": "Bloomberg",
        "published": "2026-07-28",
        "url": "https://example.com/2",
    },
]


class _FakeAnthropicModule(types.ModuleType):
    """Minimal stand-in for the anthropic SDK returning a canned text block."""

    def __init__(self, response_text: str):
        super().__init__("anthropic")
        outer = self

        class _Block:
            type = "text"

            def __init__(self, text):
                self.text = text

        class _Response:
            def __init__(self, text):
                self.content = [_Block(text)]

        class _Messages:
            def create(self, **kwargs):
                return _Response(outer.response_text)

        class Anthropic:
            def __init__(self, *args, **kwargs):
                self.messages = _Messages()

        self.response_text = response_text
        self.Anthropic = Anthropic


def _summarize_with_model_saying(text: str):
    """Run summarize_news_for_ticker() against a mocked model response."""
    from assistant import news_summary

    real_module = sys.modules.get("anthropic")
    had_key = "ANTHROPIC_API_KEY" in os.environ
    previous_key = os.environ.get("ANTHROPIC_API_KEY")
    sys.modules["anthropic"] = _FakeAnthropicModule(text)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    try:
        return news_summary.summarize_news_for_ticker("NVDA", _HEADLINES)
    finally:
        if real_module is not None:
            sys.modules["anthropic"] = real_module
        else:
            sys.modules.pop("anthropic", None)
        if had_key:
            os.environ["ANTHROPIC_API_KEY"] = previous_key
        else:
            os.environ.pop("ANTHROPIC_API_KEY", None)


# --- integration: summarize_news_for_ticker() actually applies the guard ---

def test_news_summary_rejects_explicit_trade_advice():
    assert _summarize_with_model_saying("You should buy NVDA now.") is None


def test_news_summary_rejects_trimming_and_increasing_advice():
    for advice in (
        "Consider trimming NVDA after this report.",
        "It would be prudent to increase exposure to NVDA.",
        "Investors ought to sell NVDA.",
    ):
        assert _summarize_with_model_saying(advice) is None, advice


def test_news_summary_rejects_a_ticker_absent_from_the_supplied_headlines():
    assert _summarize_with_model_saying(
        "NVDA results were strong, mirroring TSLA's quarter."
    ) is None


def test_news_summary_rejects_an_invented_figure():
    """30 billion is in the headlines; nine trillion is not."""
    assert _summarize_with_model_saying(
        "NVDA reported revenue of 9000 billion for the quarter."
    ) is None


def test_news_summary_allows_a_neutral_summary_grounded_in_the_headlines():
    grounded = (
        "NVDA reported quarterly revenue of 30 billion, which coverage attributes to "
        "data-center demand. Reporting also notes competition from AMD in accelerators."
    )
    assert _summarize_with_model_saying(grounded) == grounded


def test_news_summary_returns_none_so_callers_fall_back_to_raw_headlines():
    """The contract callers rely on: None means "show the deterministic
    headlines instead", never an exception and never partial text."""
    assert _summarize_with_model_saying("You should buy NVDA now.") is None
    # And the deterministic source content is still available to fall back to.
    assert _HEADLINES[0]["title"]


# --- numeric grounding ---

def test_unsupported_numbers_ignores_formatting_differences():
    assert _unsupported_numbers("revenue was 30,000", "revenue was 30000") == []
    assert _unsupported_numbers("revenue was 30000", "revenue was 30,000") == []


def test_unsupported_numbers_flags_invented_figures():
    source = "NVDA reported revenue of 30 billion on 2026-07-28."
    for fabricated in (
        "NVDA reported revenue of 91 billion.",
        "NVDA grew 47% year over year.",
        "The results were announced on 2025-01-15.",
    ):
        assert _unsupported_numbers(fabricated, source), fabricated


def test_guard_rejects_invented_numeric_claims_across_categories():
    """Adversarial sweep over the fabrication categories the review listed that
    are numeric, and therefore deterministically detectable."""
    source = "NVDA reported revenue of 30 billion on 2026-07-28."
    allowed = {"NVDA"}
    for fabricated in (
        "NVDA reported earnings per share of 12.44.",             # earnings figure
        "NVDA raised its dividend by 15%.",                        # percentage
        "NVDA closed the acquisition on 2024-03-02.",               # date
        "NVDA received 4 analyst upgrades this week.",              # rating count
        "NVDA guided to 88 billion in revenue.",                    # revenue
    ):
        assert _reject_unsafe_prose(fabricated, allowed, source_text=source) is not None, fabricated


def test_guard_documents_its_own_limitation_for_non_numeric_fabrication():
    """KNOWN AND ACCEPTED GAP, asserted so it can never be mistaken for
    coverage: a fabricated NON-numeric claim about an allowed ticker is not
    deterministically detectable -- there is no regex for "is this true". The
    mitigation is structural, not a stronger denylist: the model's role stays
    synthesis-only over supplied source text, and deterministic source-derived
    content (the raw headlines) remains the primary UI surface with model prose
    strictly secondary. If this assertion ever starts failing because real
    grounding was implemented, delete it and celebrate."""
    source = "NVDA reported revenue of 30 billion on 2026-07-28."
    fabricated_but_undetectable = "NVDA announced an acquisition of a networking company."
    assert _reject_unsafe_prose(
        fabricated_but_undetectable, {"NVDA"}, source_text=source
    ) is None


def test_guard_without_source_text_still_applies_the_other_two_checks():
    """source_text is optional -- callers that have no trusted source (ticker
    curation) still get action-language and unknown-ticker enforcement."""
    assert _reject_unsafe_prose("You should buy NVDA.", {"NVDA"}) is not None
    assert _reject_unsafe_prose("NVDA relates to TSLA.", {"NVDA"}) is not None
    assert _reject_unsafe_prose("NVDA is in the semiconductor category.", {"NVDA"}) is None


if __name__ == "__main__":
    test_news_summary_rejects_explicit_trade_advice()
    test_news_summary_rejects_trimming_and_increasing_advice()
    test_news_summary_rejects_a_ticker_absent_from_the_supplied_headlines()
    test_news_summary_rejects_an_invented_figure()
    test_news_summary_allows_a_neutral_summary_grounded_in_the_headlines()
    test_news_summary_returns_none_so_callers_fall_back_to_raw_headlines()
    test_unsupported_numbers_ignores_formatting_differences()
    test_unsupported_numbers_flags_invented_figures()
    test_guard_rejects_invented_numeric_claims_across_categories()
    test_guard_documents_its_own_limitation_for_non_numeric_fabrication()
    test_guard_without_source_text_still_applies_the_other_two_checks()
    print("All AI output-guard tests passed.")
