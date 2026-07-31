"""Measured committee-language coverage without sacrificing description.

The shared advisor filter originally missed 14 of these 24 formal,
third-person directives.  The committee validator now adds narrowly-scoped
directive framing while retaining neutral descriptions of the candidate and
its measured effects.  This is a regression corpus, not a claim that lexical
filtering can prove arbitrary prose advice-free.
"""
from __future__ import annotations

import pytest

from assistant.llm.validators import _contains_committee_action_language

TICKERS = {"NVDA", "AMD", "SOXX"}

DIRECTIVES = [
    "NVDA should be brought within the policy limit.",
    "Trimming NVDA is consistent with the stated risk policy.",
    "The portfolio would benefit from reduced NVDA weight.",
    "NVDA's weight ought to come down.",
    "A prudent response is to cut NVDA exposure.",
    "The committee favors decreasing NVDA.",
    "The sensible path is a lower NVDA allocation.",
    "This analysis implies NVDA exposure should fall.",
    "The committee would support offloading part of NVDA.",
    "De-risking the NVDA position is warranted by these figures.",
    "The committee's view is that NVDA exposure is best brought down.",
    "The appropriate response to this concentration is a smaller NVDA position.",
    "Risk-adjusted, the portfolio is better served by less NVDA.",
    "A reduction in the NVDA holding follows from the concentration data.",
    "The evidence points toward paring the semiconductor sleeve.",
    "The committee endorses a lighter allocation to NVDA.",
    "Bringing NVDA closer to target would address the breach.",
    "The indicated course is to lighten NVDA.",
    "The natural remedy here is a partial NVDA sale.",
    "Corrective action on NVDA is supported by the risk data.",
    "The committee sees a case for unwinding part of the NVDA position.",
    "The data supports stepping back from NVDA.",
    "The committee's recommendation is a smaller NVDA footprint.",
    "Rightsizing NVDA would resolve the concentration warning.",
]

# Genuine analysis the committee must be able to write. Over-blocking these
# makes the feature useless, so they matter as much as the leaks.
MUST_PASS = [
    "NVDA represents 31.2% of portfolio value.",
    "The concentration limit in the stated policy is 25%.",
    "NVDA's realized volatility is roughly twice the portfolio average.",
    "The research registry records this strategy as rejected.",
    "Position-level cost basis is unavailable for NVDA.",
    "Semiconductor names moved together during the observed window.",
    "This figure was computed from the portfolio snapshot, not estimated.",
    "The drawdown finding was confirmed; the return finding was not.",
    "The candidate produces a reduction in NVDA weight from 50 to 25 percent.",
    "The strategy showed a reduction in maximum drawdown.",
    "The smaller positions in the portfolio total under 5 percent.",
    "NVDA is a larger position than AMD in this portfolio.",
    "The committee's view is that the evidence is incomplete.",
    "The evidence points toward higher volatility in the observed window.",
]


@pytest.mark.parametrize("text", DIRECTIVES)
def test_measured_committee_directives_are_rejected(text):
    assert _contains_committee_action_language(text, TICKERS)


@pytest.mark.parametrize("text", MUST_PASS)
def test_descriptive_analysis_is_not_blocked(text):
    """Over-blocking is a real failure, not a safe default.

    A committee that cannot describe the candidate it reviews returns
    review_unavailable every time, which is indistinguishable from the
    feature being broken.
    """
    assert not _contains_committee_action_language(text, TICKERS), (
        "the guard now blocks legitimate analysis; this is how the feature breaks"
    )


def test_the_measured_probe_size_is_not_quietly_reduced():
    assert len(DIRECTIVES) == 24
    assert len(MUST_PASS) == 14


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
