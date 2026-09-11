"""Structural checks for the Analyst Revisions V2 lane handoff record."""
from __future__ import annotations

import re
from pathlib import Path


RECORD = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "Strategy Description"
    / "ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md"
)

_REVIEW_AGENT = re.compile(r"\b(?:Codex|Claude)\b", flags=re.IGNORECASE)
# A stale handoff reads as completed history ("Claude reviewed section 64"),
# so a bare past tense must not satisfy the forward-looking step. Passive
# future and modal forms ("will be reviewed", "must be reviewed") still do.
_REVIEW_VERB = re.compile(
    r"\b(?:(?:will|shall|must|should|is to|are to|to)\s+be\s+"
    r"(?:counter[- ]?)?reviewed"
    r"|(?:counter[- ]?)?review(?:s|ing)?)\b",
    flags=re.IGNORECASE,
)


def _names_review_by_agent(sentence: str) -> bool:
    return bool(_REVIEW_AGENT.search(sentence) and _REVIEW_VERB.search(sentence))


def test_session_push_ledger_is_one_contiguous_gfm_table() -> None:
    """A blank separator must not silently eject later rows from the ledger."""

    text = RECORD.read_text(encoding="utf-8")
    section = text.split("## 5. Session / push ledger\n", 1)[1].split(
        "\n## 6. Project-wide", 1
    )[0]
    table = section[section.index("| UTC date |") :].strip()
    lines = table.splitlines()

    assert len(lines) > 2
    assert lines[1] == "|---|---|---|---|---|---|---|---|"
    assert all(line.startswith("|") for line in lines)

    header_width = lines[0].count("|")
    assert header_width == 9
    over_or_under_width = [
        line for line in lines[2:] if line.count("|") != header_width
    ]
    assert len(over_or_under_width) == 1
    immutable_legacy_row = over_or_under_width[0]
    assert "`e40caf0` -> this record commit" in immutable_legacy_row
    assert immutable_legacy_row.count("|") == header_width + 1
    assert (
        "| A 12-trial independent mutation matrix caught every trial:"
        in immutable_legacy_row
    )


def test_exact_next_step_references_the_latest_numbered_section() -> None:
    """A new review section must not leave the live handoff one round behind."""

    text = RECORD.read_text(encoding="utf-8")
    section_numbers = [
        int(match.group(1))
        for match in re.finditer(r"^## (\d+)\.", text, flags=re.MULTILINE)
    ]
    assert section_numbers
    latest = max(section_numbers)
    exact_next_step = text.split("## 4. Exact next step\n", 1)[1].split(
        "\n## 4A.", 1
    )[0]

    assert f"section {latest}" in exact_next_step.casefold()


def test_exact_next_step_names_the_review_of_the_latest_section() -> None:
    """The live handoff must name both a reviewer and the review action."""

    text = RECORD.read_text(encoding="utf-8")
    section_numbers = [
        int(match.group(1))
        for match in re.finditer(r"^## (\d+)\.", text, flags=re.MULTILINE)
    ]
    assert section_numbers
    latest = max(section_numbers)
    exact_next_step = text.split("## 4. Exact next step\n", 1)[1].split(
        "\n## 4A.", 1
    )[0]
    normalized = " ".join(exact_next_step.split())

    sentences = re.findall(
        rf"[^.]*\bsection {latest}\b[^.]*\.", normalized, flags=re.IGNORECASE
    )
    assert sentences, f"the exact next step never names section {latest}"
    assert any(_names_review_by_agent(sentence) for sentence in sentences), (
        f"the exact next step cites section {latest} but never says who reviews "
        "it; the alternating review step must not drop out of the live handoff"
    )


def test_review_sentence_classifier_requires_agent_and_accepts_verb_forms() -> None:
    accepted = (
        "Claude should review section 64.",
        "Section 64 will be reviewed by Codex.",
        "Codex counter-reviews section 64.",
        "Claude is counter reviewing section 64.",
    )
    rejected = (
        "The process reviews section 64.",
        "Claude receives section 64.",
        "Review section 64 next.",
        "Claude reviewed section 64 in an earlier round.",
        "Section 64 was reviewed by Codex last week.",
        "Codex has counter-reviewed section 64.",
    )

    assert all(_names_review_by_agent(sentence) for sentence in accepted)
    assert not any(_names_review_by_agent(sentence) for sentence in rejected)
