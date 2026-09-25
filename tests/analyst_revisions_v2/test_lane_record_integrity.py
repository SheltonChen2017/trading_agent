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

# A stale handoff reads as completed history ("Claude reviewed section 64"),
# so a bare past tense must not satisfy the forward-looking step. Bind the
# named reviewer to the action as well: an unrelated actor's review, a noun
# phrase, or a negated instruction is not a forward handoff.
_ACTIVE_REVIEW_ACTION = re.compile(
    r"\b(?:Codex|Claude)\b(?!['’]s\b)\s+"
    r"(?:(?:(?:will|shall|must|should|is\s+to|are\s+to|to)\s+)"
    r"(?:counter[- ]?)?review\b"
    r"|(?:is|are)\s+(?:counter[- ]?)?reviewing\b"
    r"|(?:counter[- ]?)?reviews\b)",
    flags=re.IGNORECASE,
)
_PASSIVE_REVIEW_ACTION = re.compile(
    r"\b(?:will|shall|must|should|is\s+to|are\s+to)\s+be\s+"
    r"(?:counter[- ]?)?reviewed\b[^.]{0,80}\bby\s+(?:Codex|Claude)\b",
    flags=re.IGNORECASE,
)
_EXPLICIT_OWNER_REVIEW_WAIVER = re.compile(
    r"\bowner\s+explicitly\s+waives\b[^.]{0,120}"
    r"\bClaude\s+review\s+of\s+section\s+\d+\b",
    flags=re.IGNORECASE,
)


def _names_review_by_agent(sentence: str) -> bool:
    return bool(
        _ACTIVE_REVIEW_ACTION.search(sentence)
        or _PASSIVE_REVIEW_ACTION.search(sentence)
    )


def _names_explicit_owner_review_waiver(sentence: str) -> bool:
    return bool(_EXPLICIT_OWNER_REVIEW_WAIVER.search(sentence))


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


def test_live_banner_retains_the_no_accepted_signal_assertion() -> None:
    """Historical quotations must not satisfy the live safety banner gate."""

    text = RECORD.read_text(encoding="utf-8")
    banner = text.split("\nBranch: `codex/strategy-analyst-revisions-v2`", 1)[0]
    normalized = " ".join(banner.split())

    assert (
        "NO V2 SIGNAL HAS BEEN ACCEPTED AS FORMAL OR PRODUCTION-EXECUTABLE."
        in normalized
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


def test_exact_next_step_names_review_or_owner_waiver_of_latest_section() -> None:
    """The live handoff must name review or an exact owner review exception."""

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
    assert any(
        _names_review_by_agent(sentence)
        or _names_explicit_owner_review_waiver(sentence)
        for sentence in sentences
    ), (
        f"the exact next step cites section {latest} but names neither an "
        "active review nor an explicit owner waiver"
    )


def test_exact_next_step_has_no_stale_immediate_review_direction() -> None:
    """A completed review must not remain the live immediate-next instruction."""

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

    directed_sections = [
        int(match.group(1))
        for match in re.finditer(
            r"\bthe\s+immediate\s+next\s+step\b[^.]*"
            r"\bsection\s+(\d+)\b",
            normalized,
            flags=re.IGNORECASE,
        )
    ]
    assert all(section == latest for section in directed_sections), (
        "the exact-next-step handoff retains a stale directional section: "
        f"{directed_sections!r}; latest is {latest}"
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
        "Claude's review of section 64 is already complete.",
        "Claude must not review section 64.",
        "Section 64 must not be reviewed by Codex.",
        "Codex finished; the process reviews section 64.",
    )

    assert all(_names_review_by_agent(sentence) for sentence in accepted)
    assert not any(_names_review_by_agent(sentence) for sentence in rejected)


SHARED_LOOK_LEDGER = RECORD.parents[1] / "research" / "alpha-result.md"
_CANDIDATE_ID = re.compile(r"\bR-(\d{3})\b")
_RECORDED_BACKTEST = re.compile(
    r"backtest\s+`[0-9a-f]{32}`"
    r"|^\|\s*Backtest\s*\|[^\n]*`[0-9a-f]{32}`",
    flags=re.MULTILINE,
)
_SECTION_HEADING = re.compile(r"(?m)^(#{2,3} .*)$")


def _launched_candidates(record: str) -> dict[str, str]:
    """Candidates whose own record section names a QC backtest identity."""

    parts = _SECTION_HEADING.split(record)
    launched: dict[str, str] = {}
    for heading, body in zip(parts[1::2], parts[2::2]):
        if _RECORDED_BACKTEST.search(body):
            for candidate in _CANDIDATE_ID.findall(heading):
                launched.setdefault(candidate, heading.strip())
    return launched


def test_shared_look_ledger_names_every_launched_candidate() -> None:
    # The shared ledger is the cross-lane look census. This checks that each
    # detected launched candidate has a heading, not that every additional
    # launch under an already-ledgered candidate has its own run-level entry.
    record = RECORD.read_text(encoding="utf-8")
    ledger = SHARED_LOOK_LEDGER.read_text(encoding="utf-8")
    ledger_candidates = {
        candidate
        for line in ledger.splitlines()
        if line.startswith("## ")
        for candidate in _CANDIDATE_ID.findall(line)
    }
    launched = _launched_candidates(record)
    assert launched, "no launched candidate found in the record"
    missing = {
        candidate: heading
        for candidate, heading in launched.items()
        if candidate not in ledger_candidates
    }
    assert not missing, (
        "launched candidates without a shared look-ledger heading: "
        f"{sorted(missing)!r} (first named in {sorted(missing.values())[:3]!r})"
    )


def test_launched_candidate_classifier_requires_a_backtest_identity() -> None:
    record = (
        "## 1. R-900 preregistration\n\nNo launch yet.\n\n"
        "## 2. R-901 completed run\n\nbacktest `" + "a" * 32 + "` reached Completed.\n\n"
        "### 2.1 R-902 attempt\n\nCompiled and launched backtest `" + "b" * 32 + "`.\n"
    )
    assert sorted(_launched_candidates(record)) == ["901", "902"]


def test_launched_candidate_classifier_accepts_backtest_table_rows() -> None:
    record = (
        "## 1. R-900 unlaunched\n\n| Source | `" + "0" * 32 + "` |\n\n"
        "## 2. R-901 completed\n\n| Backtest | `" + "a" * 32 + "`; run name |\n\n"
        "### 2.1 R-902 attempt\n\n| Backtest | `run name`, id `"
        + "b" * 32
        + "` |\n\n"
        "## 3. R-903 planned\n\n| Backtest | `run name only` |\n"
    )
    assert sorted(_launched_candidates(record)) == ["901", "902"]


def test_launched_candidate_classifier_covers_historical_table_rows() -> None:
    launched = _launched_candidates(RECORD.read_text(encoding="utf-8"))
    assert {"053", "173", "174", "175", "176"} <= launched.keys()


def test_owner_review_waiver_classifier_is_exact_and_section_shaped() -> None:
    accepted = (
        "The owner explicitly waives an additional Claude review of section 68.",
        "Owner explicitly waives the Claude review of section 7 before C1.",
    )
    rejected = (
        "Claude review of section 68 is complete.",
        "The owner may waive a Claude review of section 68.",
        "The reviewer explicitly waives Claude review of section 68.",
        "The owner explicitly waives a review of section 68.",
        "The owner explicitly waives Claude review of an unspecified section.",
    )

    assert all(_names_explicit_owner_review_waiver(value) for value in accepted)
    assert not any(
        _names_explicit_owner_review_waiver(value) for value in rejected
    )
