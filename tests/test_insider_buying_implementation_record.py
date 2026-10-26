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


def test_counter_review_201_records_each_commit_and_the_raw_status_body_boundary() -> None:
    """Review acceptance must not preserve the overly broad no-body claim."""
    raw = RECORD.read_text(encoding="utf-8")
    assert "## 202." in raw, "the current counter-review needs a durable lane handoff"
    section = raw.split("## 202.", 1)[1]
    for commit in (
        "9013b4072bb1d312828a1c58cc71e7e3f12bacd5",
        "11b4cf0d016e3c818d8799da4f7253b1f1ef3c25",
        "8f6ee687a69427f2ee2ea96ab08fb6269db33a57",
    ):
        assert commit in section
    assert "IBREC-CCR20101" in section
    assert "successful status-response bodies" in section
    assert "rejected credential-echo responses" in section
    assert "IBREC-CCR20102" in section
    assert "ctime-only metadata changes are intentionally ignored" in section
    assert "NO next milestone this round" in section
    assert "QC hold remains in force" in section
