"""Lane-local structural checks for the Insider Buying implementation record."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORD = (
    ROOT
    / "docs"
    / "Strategy Description"
    / "INSIDER_BUYING_IMPLEMENTATION_RECORD.md"
)


def test_session_ledger_is_one_contiguous_markdown_table() -> None:
    """A wrapped ledger row silently renders as prose instead of one durable row."""
    raw = RECORD.read_text(encoding="utf-8")
    start = raw.index("| UTC date |")
    end = raw.index("\n## 6.", start)
    lines = raw[start:end].splitlines()

    expected_pipes = lines[0].count("|")
    assert expected_pipes > 2
    assert all(line.strip() for line in lines)
    assert all(line.startswith("|") and line.endswith("|") for line in lines)
    assert all(line.count("|") == expected_pipes for line in lines)


def test_context_revision_requires_focused_package_guard_not_implicit_full_suite() -> None:
    raw = RECORD.read_text(encoding="utf-8")
    section = raw[raw.index("## 83."):]
    assert "tests/test_insider_buying_form4.py::test_package_has_no_provider_outcome_execution_or_scheduler_imports" in section
    assert "Full lane suite is not authorized by inference" in section
    assert "actual affected-quarter and accession counts are unmeasured" in section
