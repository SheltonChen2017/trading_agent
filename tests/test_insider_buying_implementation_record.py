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
