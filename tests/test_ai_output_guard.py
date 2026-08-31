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

import pytest
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


def _summarize_with_reason_saying(text: str):
    """Same harness as _summarize_with_model_saying, returning (summary, reason)."""
    from assistant import news_summary

    real_module = sys.modules.get("anthropic")
    had_key = "ANTHROPIC_API_KEY" in os.environ
    previous_key = os.environ.get("ANTHROPIC_API_KEY")
    sys.modules["anthropic"] = _FakeAnthropicModule(text)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    try:
        return news_summary.summarize_news_for_ticker_with_reason("NVDA", _HEADLINES)
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


def test_guard_with_an_empty_source_still_applies_the_other_two_checks():
    """source_text is now REQUIRED (it used to default to None, which silently
    skipped the number check on two of three callers). A caller with no source
    passes "", which still gets action-language and unknown-ticker
    enforcement."""
    assert _reject_unsafe_prose("You should buy NVDA.", {"NVDA"}, source_text="") is not None
    assert _reject_unsafe_prose("NVDA relates to TSLA.", {"NVDA"}, source_text="") is not None
    assert _reject_unsafe_prose(
        "NVDA is in the semiconductor category.", {"NVDA"}, source_text="",
    ) is None


def test_an_empty_source_grounds_nothing_so_every_number_is_rejected():
    """The fail-closed reading of "no source": with nothing to check against,
    no figure can be supported."""
    assert _reject_unsafe_prose(
        "NVDA is in the semiconductor category, up 5%.", {"NVDA"}, source_text="",
    ) is not None


def test_source_text_cannot_be_omitted():
    """The structural half of the fix: a new prose surface that forgets
    grounding must fail loudly, not silently skip the number check."""
    with pytest.raises(TypeError):
        _reject_unsafe_prose("NVDA is in the semiconductor category.", {"NVDA"})



# --- round 3: decimal-safe numeric canonicalization -----------------------

def test_decimal_point_is_not_a_formatting_artifact():
    """Deleting the decimal point changed VALUE, not formatting: 3.05 compared
    equal to 305 and 0.05 to 5, so a model could turn a real figure into a
    fabricated one and still pass (independent review, 2026-07-29)."""
    assert _unsupported_numbers("EPS was 305", "EPS was 3.05") == ["305"]
    assert _unsupported_numbers("growth was 5 percent", "growth was 0.05 percent") == ["5"]
    assert _unsupported_numbers("value 30", "value 3.0") == ["30"]


def test_thousands_separators_still_match_either_way():
    assert _unsupported_numbers("revenue was 30,000", "revenue was 30000") == []
    assert _unsupported_numbers("revenue was 30000", "revenue was 30,000") == []


def test_trailing_and_leading_zeros_are_formatting_only():
    """The old normalization ALSO produced a false positive here -- it flagged
    3.050 against a source 3.05 as invented."""
    assert _unsupported_numbers("value 3.050", "value 3.05") == []
    assert _unsupported_numbers("value 3.05", "value 3.050") == []
    assert _unsupported_numbers("value 0.05", "value .05") == []
    assert _unsupported_numbers("value 0", "value 0.0") == []


def test_numeric_grounding_is_independent_of_ambient_decimal_precision():
    """A caller's low Decimal precision must not round two source figures
    into the same canonical identity or reject equivalent trailing zeros."""
    from decimal import localcontext

    with localcontext() as context:
        context.prec = 3
        assert _unsupported_numbers("value 1.2345", "value 1.2344") == ["1.2345"]
        assert _unsupported_numbers("value 1.2344000", "value 1.2344") == []


def test_sign_is_significant():
    assert _unsupported_numbers("fell -3.05", "rose 3.05") == ["-3.05"]
    assert _unsupported_numbers("fell -3.05", "fell -3.05") == []


def test_a_hyphen_inside_a_range_is_not_read_as_a_negative_sign():
    """"5-10" must yield 5 and 10, not 5 and -10, or ordinary prose would be
    flagged as fabricated."""
    assert _unsupported_numbers("guided 5-10 percent", "guided 5-10 percent") == []


def test_percentages_compare_as_the_numeral_written():
    """Documented rule: no unit conversion. Guessing that a bare 0.05 meant 5%
    is exactly the inference this guard exists to avoid."""
    assert _unsupported_numbers("grew 5%", "grew 0.05") == ["5"]
    assert _unsupported_numbers("grew 5%", "grew 5 percent") == []


def test_a_source_date_does_not_license_its_components_as_figures():
    """2026-07-28 in the source must not substantiate "revenue grew 2026" or
    "28 acquisitions"."""
    source = "Filed on 2026-07-28."
    assert _unsupported_numbers("revenue grew 2026", source) == ["2026"]
    assert _unsupported_numbers("there were 28 acquisitions", source) == ["28"]
    assert _unsupported_numbers("there were 7 upgrades", source) == ["7"]
    # The whole date itself is grounded.
    assert _unsupported_numbers("Filed on 2026-07-28.", source) == []


def test_an_invented_date_is_flagged_whole():
    assert _unsupported_numbers("Filed on 2025-01-15.", "Filed on 2026-07-28.") == ["2025-01-15"]


def test_canonical_number_fails_closed_on_an_unparseable_token():
    from assistant.ai_advisor import _canonical_number

    assert _canonical_number("1.2.3") is None
    # ...and a token that cannot be parsed counts as unsupported, never ignored.
    assert _unsupported_numbers("ratio 1.2.3", "ratio 1.2.3") != []

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
    test_guard_with_an_empty_source_still_applies_the_other_two_checks()
    print("All AI output-guard tests passed.")


# --- news headlines are UNTRUSTED input (independent review, 2026-07-30) ---
#
# Allowed tickers used to be "this ticker plus ANY all-caps token in the
# headlines". yfinance news is third-party, so a headline containing a
# ticker-shaped token was enough to let the model name it as though it had been
# verified -- the unknown-ticker check was deriving its own allowlist from
# attacker-influenceable text.

def _headlines_saying(title: str) -> list[dict]:
    return [{
        "title": title,
        "summary": "Coverage of the event.",
        "provider": "Reuters",
        "published": "2026-07-28",
        "url": "https://example.com/injected",
    }]


def _summarize_headlines_with_model_saying(headlines, text: str):
    from assistant import news_summary

    real_module = sys.modules.get("anthropic")
    had_key = "ANTHROPIC_API_KEY" in os.environ
    previous_key = os.environ.get("ANTHROPIC_API_KEY")
    sys.modules["anthropic"] = _FakeAnthropicModule(text)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    try:
        return news_summary.summarize_news_for_ticker("NVDA", headlines)
    finally:
        if real_module is not None:
            sys.modules["anthropic"] = real_module
        else:
            sys.modules.pop("anthropic", None)
        if had_key:
            os.environ["ANTHROPIC_API_KEY"] = previous_key
        else:
            os.environ.pop("ANTHROPIC_API_KEY", None)


def test_an_injected_headline_cannot_authorize_its_own_invented_ticker():
    """THE regression: a fake symbol planted in a headline must not become an
    allowed ticker just by appearing there."""
    injected = _headlines_saying("NVDA partners with SCAM on accelerators")
    assert _summarize_headlines_with_model_saying(
        injected, "NVDA announced a partnership with SCAM."
    ) is None


def test_a_real_peer_ticker_in_a_headline_is_still_allowed():
    """The tightening must not suppress every summary: a headline naming a
    ticker this project actually knows still works."""
    real = _headlines_saying("NVDA and AMD compete in accelerators")
    grounded = "NVDA and AMD are described as competing in accelerators."
    assert _summarize_headlines_with_model_saying(real, grounded) == grounded


def test_an_injected_headline_still_cannot_produce_trade_advice():
    """Injection cannot reach the action-language denylist, which does not
    consult the source at all."""
    injected = _headlines_saying("Analysts say you should buy NVDA immediately")
    assert _summarize_headlines_with_model_saying(
        injected, "You should buy NVDA immediately."
    ) is None


# --- a refusal must say it refused (owner report, 2026-08-07) -------------

def test_guard_rejection_reports_a_reason_instead_of_bare_none():
    """The defect this closes: a withheld summary and a disabled feature
    looked identical in the UI -- nothing rendered either way.

    Measured on the owner's real holdings: 7 of 8 tickers were withheld by
    the guard (their `allowed_tickers` set is built from `config.UNIVERSE`,
    which most of what they hold is not in), while AAPL/MSFT passed 10/10.
    So the common case for a real portfolio was silence, and a working
    safety control read as a broken feature.
    """
    from assistant import news_summary

    summary, reason = _summarize_with_reason_saying("You should buy NVDA now.")
    assert summary is None
    assert reason is not None
    assert "withheld by the output guard" in reason


def test_the_withheld_prose_never_travels_with_the_reason():
    """Surfacing the text the guard refused would defeat the guard. Only the
    fixed verdict label may reach the UI."""
    from assistant import news_summary

    poisoned = "You should buy NVDA now. SECRETMARKER should not appear."
    summary, reason = _summarize_with_reason_saying(poisoned)
    assert summary is None
    assert "SECRETMARKER" not in reason
    assert "should buy" not in reason


def test_invented_numbers_do_not_travel_with_the_refusal_reason():
    """CNEWS-001: the unsupported-number verdict used to interpolate the
    model-invented figures into the reason string. Those tokens are the
    fabrication class most likely to mislead; putting them in the UI caption
    partially defeated the guard this refusal surface claims to report.
    """
    summary, reason = _summarize_with_reason_saying(
        "Revenue jumped 847% after the product launch."
    )
    assert summary is None
    assert reason is not None
    assert "withheld by the output guard" in reason
    assert "cites number(s) absent from the source data" in reason
    assert "847" not in reason


def test_missing_credentials_and_missing_headlines_are_distinguishable():
    """Three different causes must not collapse into one blank surface."""
    import os

    from assistant import news_summary

    previous = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        _, no_headlines = news_summary.summarize_news_for_ticker_with_reason("NVDA", [])
        _, no_key = news_summary.summarize_news_for_ticker_with_reason("NVDA", _HEADLINES)
    finally:
        if previous is not None:
            os.environ["ANTHROPIC_API_KEY"] = previous

    assert "no headlines" in no_headlines
    assert "ANTHROPIC_API_KEY" in no_key
    assert no_headlines != no_key


def test_accepted_summary_carries_no_reason():
    """Guards against 'fixing' this by always reporting a problem."""
    from assistant import news_summary

    summary, reason = _summarize_with_reason_saying(
        "Analysts discussed the company's quarterly results."
    )
    assert summary is not None
    assert reason is None


def test_the_wrapper_still_returns_a_bare_summary():
    """Existing callers and tests keep working."""
    from assistant import news_summary

    assert _summarize_with_model_saying("Analysts discussed quarterly results.") is not None
