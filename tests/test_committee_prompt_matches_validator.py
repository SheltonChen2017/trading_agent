"""
The prompt must state the rule the validator actually enforces.

Found reviewing the committee foundation (2026-07-30). The v1 prompt said:

    "Never instruct anyone to buy, sell, submit, execute, cancel, ..."

but assistant/llm/validators.py rejects any point whose text merely
CONTAINS an action verb -- ai_advisor._contains_action_language cannot tell
"the candidate is a sell" from "sell NVDA". So a model that obeyed the
prompt perfectly still produced rejected output: the natural sentence

    "The proposal under review is a risk-reducing sell of NVDA."

was discarded as forbidden_action_language, even though describing the
candidate is the committee's entire job. Reproduced end-to-end before the
fix; the whole review is rejected, so the surface degrades to
review_unavailable every time the model phrases things naturally.

That is fail-CLOSED (a missing review, not smuggled advice), so it is a
usability defect rather than a safety one -- but a feature that reliably
returns nothing is indistinguishable from a broken one.

Both halves are pinned here because fixing only one reintroduces the gap.
"""
from __future__ import annotations

import pytest

from assistant.llm.projection import project_committee_input
from assistant.llm.prompt_builder import SYSTEM_PROMPT
from assistant.llm.schemas import CommitteeReview, PrivacyMode
from assistant.llm.validators import validate_committee_review
from tests.test_committee_foundation import _packet, _proposal, _valid_raw_review


def _review_with_supporting_text(text: str) -> CommitteeReview:
    raw = _valid_raw_review()
    raw["supporting_points"][0]["text"] = text
    return CommitteeReview.from_mapping(raw)


def _validate(text: str):
    committee_input = project_committee_input(
        _packet(), _proposal(), privacy_mode=PrivacyMode.PERCENTAGES_ONLY
    )
    return validate_committee_review(committee_input, _review_with_supporting_text(text))


def test_the_validator_really_does_reject_describing_the_candidate():
    """Half one: the behaviour the prompt has to warn about.

    If this ever starts passing, the validator was loosened and the prompt
    rule below became unnecessary friction -- revisit both together.
    """
    report = _validate("The proposal under review is a risk-reducing sell of NVDA.")
    assert not report.accepted
    assert [issue.code for issue in report.issues] == ["forbidden_action_language"]


def test_describing_the_candidate_without_the_side_verb_is_accepted():
    """The phrasing the prompt now steers the model toward must actually work,
    or the instruction sends it somewhere equally rejected."""
    report = _validate(
        "The candidate takes NVDA weight from 50 percent to 25 percent."
    )
    assert report.accepted, [issue.message for issue in report.issues]


def test_formal_committee_directive_is_rejected_end_to_end():
    report = _validate("The committee endorses a lighter allocation to NVDA.")
    assert not report.accepted
    assert [issue.code for issue in report.issues] == ["forbidden_action_language"]


@pytest.mark.parametrize("verb", ["sell", "buy"])
def test_the_prompt_warns_about_the_side_verb(verb):
    """Half two: the prompt states the enforced rule.

    A source assertion is the right tool here -- the defect is that a fixed
    string disagrees with a function's behaviour, which no behavioural
    assertion against either one alone can observe (same reasoning as
    tests/test_significance_multiplicity.py).
    """
    assert verb in SYSTEM_PROMPT, f"prompt no longer mentions {verb!r}"


def test_the_prompt_tells_the_model_not_to_restate_the_side_verb():
    lowered = SYSTEM_PROMPT.lower()
    assert "the candidate" in lowered, (
        "the prompt must name the neutral term the model should use instead"
    )
    assert "even descriptively" in lowered or "descriptively" in lowered, (
        "the prompt must say the ban covers DESCRIPTIVE use, not just "
        "instructions -- that exact gap is what this file exists to prevent"
    )


def test_the_prompt_warns_about_committee_recommendation_framing():
    lowered = SYSTEM_PROMPT.lower()
    assert "committee-recommendation voice" in lowered
    assert "committee endorses" in lowered
    assert "without prescribing" in lowered


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
