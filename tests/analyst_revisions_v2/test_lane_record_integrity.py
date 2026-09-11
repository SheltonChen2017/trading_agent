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


def test_session_push_ledger_is_one_contiguous_gfm_table() -> None:
    """A blank separator must not silently eject later rows from the ledger."""

    text = RECORD.read_text(encoding="utf-8")
    section = text.split("## 5. Session / push ledger\n", 1)[1].split(
        "\n## 6. Project-wide", 1
    )[0]
    table = section[section.index("| UTC date |") :].strip()
    lines = table.splitlines()

    assert len(lines) > 2
    assert lines[1].startswith("|---|")
    assert all(line.startswith("|") for line in lines)


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
    """Citing the newest section is not enough; the live handoff must say who reviews it."""

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
        re.search(r"\b(?:counter-)?reviews\b", sentence, flags=re.IGNORECASE)
        for sentence in sentences
    ), (
        f"the exact next step cites section {latest} but never says who reviews "
        "it; the alternating review step must not drop out of the live handoff"
    )
