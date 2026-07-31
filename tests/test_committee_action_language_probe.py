"""
The committee's action-language filter leaks, and this pins how much.

assistant/llm/validators.py reuses ai_advisor._contains_action_language for
committee prose. That guard was tuned against ADVISOR phrasing ("You might
want to offload some NVDA"); committee prose is formal and third-person, a
register it covers poorly. Two prior adversarial probes already forced two
rounds of patching (2026-07-29), so a third register getting a free pass
was not a safe assumption -- and it was not true.

This file exists to make the gap MEASURED rather than assumed. It is a
characterization test: it asserts the leak set has not grown and the
descriptive set has not started over-blocking. It deliberately does not
assert "no leaks", because that would be a red test with no owner.

Why not just fix the regexes: a widening that caught all 14 leaks below was
written and measured, and it newly blocked 6 of 12 legitimate descriptive
sentences -- including "the candidate produces a reduction in NVDA weight
from 50 to 25 percent", which is the committee's core job. The same words
carry both directive and descriptive force. See validate_committee_review's
docstring and docs/ADR_INVESTMENT_COMMITTEE_BOUNDARY.md.
"""
from __future__ import annotations

import pytest

from assistant.ai_advisor import _contains_action_language

TICKERS = {"NVDA", "AMD", "SOXX"}

# Directives in committee voice that the guard DOES catch. If one of these
# starts leaking, coverage has regressed.
CAUGHT_DIRECTIVES = [
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
]

# Directives in committee voice that the guard MISSES. Documented, not
# accepted. Shrinking this list is an improvement; growing it is a
# regression -- both should be deliberate, hence the exact-set assertion.
KNOWN_LEAKS = [
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
]

# Descriptive sentences the guard blocks TODAY. Found while writing this
# file, not previously recorded. Unlike the leaks, these err toward
# refusing -- the review comes back unavailable rather than carrying hidden
# advice -- so they are a usability defect, not a safety one.
#
# The singular/plural split is the tell that this is pattern brittleness
# rather than judgement: _EXPOSURE_ADVICE_PATTERN matches "larger position"
# but not "larger positions", because the trailing \b fails inside the
# plural. Both sentences are equally descriptive.
KNOWN_OVERBLOCKS = [
    "NVDA is a larger position than AMD in this portfolio.",
]


@pytest.mark.parametrize("text", CAUGHT_DIRECTIVES)
def test_directives_the_guard_catches_stay_caught(text):
    assert _contains_action_language(text, TICKERS), (
        "coverage regressed: this directive used to be blocked"
    )


@pytest.mark.parametrize("text", MUST_PASS)
def test_descriptive_analysis_is_not_blocked(text):
    """Over-blocking is a real failure, not a safe default.

    A committee that cannot describe the candidate it reviews returns
    review_unavailable every time, which is indistinguishable from the
    feature being broken.
    """
    assert not _contains_action_language(text, TICKERS), (
        "the guard now blocks legitimate analysis; this is how the feature breaks"
    )


@pytest.mark.parametrize("text", KNOWN_OVERBLOCKS)
def test_known_overblocks_are_still_overblocked(text):
    """Pinned so a future guard change that fixes one is noticed and moved
    into MUST_PASS, rather than the improvement going unrecorded."""
    assert _contains_action_language(text, TICKERS), (
        "this descriptive sentence is no longer blocked -- good. Move it to "
        "MUST_PASS so the improvement is pinned."
    )


def test_the_known_leak_set_has_not_grown():
    """Exact-set assertion, both directions.

    Growth means a new hole. Shrinkage means someone fixed one and should
    move it into CAUGHT_DIRECTIVES so the fix is pinned -- silently leaving
    it here would let the fix regress unnoticed.
    """
    still_leaking = [t for t in KNOWN_LEAKS if not _contains_action_language(t, TICKERS)]
    assert still_leaking == KNOWN_LEAKS, (
        "the known-leak set changed. If you FIXED one, move it to "
        "CAUGHT_DIRECTIVES. If a new one appeared, coverage regressed.\n"
        f"still leaking: {still_leaking}"
    )


def test_the_leak_rate_is_recorded_honestly():
    """Guards against the quiet failure mode: someone trims KNOWN_LEAKS to
    make the file look better without changing any behaviour."""
    total = len(CAUGHT_DIRECTIVES) + len(KNOWN_LEAKS)
    leaked = sum(1 for t in KNOWN_LEAKS if not _contains_action_language(t, TICKERS))
    assert (leaked, total) == (14, 24), (
        f"measured leak rate changed to {leaked}/{total}; update the docstrings in "
        "assistant/llm/validators.py and docs/ADR_INVESTMENT_COMMITTEE_BOUNDARY.md "
        "so the recorded number stays true"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
