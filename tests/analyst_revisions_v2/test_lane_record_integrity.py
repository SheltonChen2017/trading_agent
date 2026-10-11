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


def _stale_completed_shared_ledger_headings(ledger: str) -> dict[str, str]:
    """Headline status must reflect the retained completed-run body census."""

    parts = re.split(r"(?m)^(## R-(\d{3})[^\n]*)\n", ledger)
    sections = {parts[index + 1]: (parts[index], parts[index + 2])
                for index in range(1, len(parts), 3)}
    expected = {"201": ("A1 valid", 261), "202": ("A1 valid", 261),
                "203": ("A1 failed; Mia A2 valid", 61), "205": ("A1 valid", 61)}
    stale = {}
    for candidate, (status, rebalance_count) in expected.items():
        assert candidate in sections, f"shared ledger is missing R-{candidate}"
        heading, body = sections[candidate]
        plain = body.replace("**", "")
        assert "run_valid=true" in plain, f"R-{candidate} lacks an authenticated valid body"
        assert re.search(rf"\b{rebalance_count}\s+(?:completed\s+)?rebalances\b", plain)
        cell_step = re.search(r"\bcells\s+(\d+)\s*(?:→|->)\s*(\d+)", plain, re.IGNORECASE)
        assert cell_step and int(cell_step[2]) == int(cell_step[1]) + 1
        if candidate == "203":
            assert "A1 reached Runtime Error during initialization" in plain
            assert "R203 attempt 2" in plain and "owner/Mia imported read passed" in plain
        if f"; {status} — " not in heading:
            stale[candidate] = heading
    return stale


def test_completed_shared_ledger_headlines_match_authenticated_body_census() -> None:
    ledger = SHARED_LOOK_LEDGER.read_text(encoding="utf-8")
    assert not _stale_completed_shared_ledger_headings(ledger)


def test_completed_heading_classifier_refuses_old_launch_and_mislabeled_mia() -> None:
    ledger = SHARED_LOOK_LEDGER.read_text(encoding="utf-8")
    mutated = ledger.replace("A1 valid — 2026-09-25", "A1 launched — 2026-09-25")
    mutated = mutated.replace("A1 valid — 2026-09-26", "A1 launched — 2026-09-26")
    mutated = mutated.replace("A1 failed; Mia A2 valid", "A1 launched")
    assert set(_stale_completed_shared_ledger_headings(mutated)) == {"201", "202", "203", "205"}
    mislabeled = ledger.replace("A1 failed; Mia A2 valid", "A1 valid")
    assert set(_stale_completed_shared_ledger_headings(mislabeled)) == {"203"}


# A parenthesized "(N.k)" cites subsection N.k. Section 244 once cited
# "(244.6)" for validation that lives in 244.5 (ARV2CR245-001). Sections
# before 100 predate the convention and hold parenthesized amounts such as
# "(473.96)", and a number whose section does not exist is not a citation.
_SUBSECTION_CITATION = re.compile(r"\((\d{3})\.(\d{1,2})\)")
_CITATION_FLOOR_SECTION = 100


def _dangling_subsection_citations(record: str) -> list[tuple[int, str]]:
    sections = list(re.finditer(r"^## (\d+)\. ", record, flags=re.MULTILINE))
    section_numbers = {int(match.group(1)) for match in sections}
    headings = set(re.findall(r"^#{3,4} (\d+\.\d+)\b", record, flags=re.MULTILINE))
    dangling = []
    for index, match in enumerate(sections):
        number = int(match.group(1))
        if number < _CITATION_FLOOR_SECTION:
            continue
        end = sections[index + 1].start() if index + 1 < len(sections) else len(record)
        for citation in _SUBSECTION_CITATION.finditer(record[match.end() : end]):
            cited = f"{citation.group(1)}.{citation.group(2)}"
            if int(citation.group(1)) in section_numbers and cited not in headings:
                dangling.append((number, cited))
    return dangling


def test_parenthesized_subsection_citations_name_existing_subsections() -> None:
    record = RECORD.read_text(encoding="utf-8")
    assert not _dangling_subsection_citations(record)


def test_subsection_citation_classifier_flags_only_missing_subsections() -> None:
    record = (
        "## 99. Before the floor\n\nIgnored (243.9).\n\n"
        "## 243. Earlier\n\n### 243.1 Disposition\n\n"
        "## 244. Review\n\nEvidence (244.5), earlier (243.1), an amount (473.96),"
        " and a dangling (244.6).\n\n### 244.5 Validation\n"
    )
    assert _dangling_subsection_citations(record) == [(244, "244.6")]


# Every standalone 32-hex token in this record is a QuantConnect backtest ID;
# compile IDs are hyphenated and longer digests are not 32 characters, so
# both are excluded. Each backtest ID must also appear in the shared look
# ledger, the look-accounting authority: the six R-177 Runtime Error IDs of
# section 172.1 were missing from it until afb29176 (ARV2R248-006).
_BACKTEST_ID = re.compile(r"(?<![0-9a-f-])[0-9a-f]{32}(?![0-9a-f-])")


def _backtest_ids_missing_from_shared_ledger(record: str, ledger: str) -> list[str]:
    return sorted(set(_BACKTEST_ID.findall(record)) - set(_BACKTEST_ID.findall(ledger)))


def test_every_recorded_backtest_id_appears_in_the_shared_look_ledger() -> None:
    record = RECORD.read_text(encoding="utf-8")
    ledger = SHARED_LOOK_LEDGER.read_text(encoding="utf-8")
    assert not _backtest_ids_missing_from_shared_ledger(record, ledger)


def test_backtest_id_classifier_skips_compile_ids_and_longer_digests() -> None:
    # Only a standalone ledger occurrence counts: an ID that the ledger holds
    # solely inside a hyphenated compile ID is still missing.
    present, absent, hidden = "a" * 32, "b" * 32, "f" * 32
    record = (
        f"runs `{present}`, `{absent}` and `{hidden}`, compile `{'c' * 32}-1234`,"
        f" digest `{'d' * 64}`"
    )
    ledger = f"ledger `{present}`, compile `{hidden}-{'e' * 8}`"
    assert _backtest_ids_missing_from_shared_ledger(record, ledger) == [absent, hidden]
