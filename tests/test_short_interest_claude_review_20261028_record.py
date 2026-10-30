"""Claude section-129 record regressions; pure policy call, no source I/O."""
from pathlib import Path

import pytest

from scripts import short_interest_count_source_authority as authority

RECORD = Path(__file__).resolve().parents[1] / "docs/Strategy Description/SHORT_INTEREST_IMPLEMENTATION_RECORD.md"
LEDGER_HEADER = "| UTC date | Role | Start -> end | Milestone | Summary | Validation / looks | Findings | Next |"
REVIEW = "## 129. Claude independent review — 2026-10-28 UTC"


def _text():
    return RECORD.read_text(encoding="utf-8")


def _status():
    return " ".join(_text().split("Current publication rule", 1)[0].split())


def _ledger_rows():
    text = _text()
    body = text.split(LEDGER_HEADER, 1)[1].split("\n## 6. Claude independent review - 2026-08-28", 1)[0]
    return [line for line in body.splitlines() if line.startswith("| 20")]


def _dispatch_blocked_by_unresolved_run():
    try:
        authority.require_dispatch_allowed()
    except authority.CountSourceAuthorityRefusal as error:
        return "count_source_prior_run_unresolved" in str(error)
    return False


def test_status_reports_unresolved_prior_run_while_dispatch_gate_refuses():
    # Couples the handoff to the code gate rather than to a past round: once a
    # frozen resolution policy replaces the refusal, this asks nothing more.
    if not _dispatch_blocked_by_unresolved_run():
        pytest.skip("prior-run dispatch gate no longer refuses")
    status = _status()
    assert "PRIOR COUNT RUN 13448 UNRESOLVED" in status
    assert "SOURCE DISPATCH BLOCKED" in status


def test_blocked_snapshot_publication_has_its_own_ledger_row():
    rows = _ledger_rows()
    assert any("757e3634511d2160f24ef2b274f101f0952c4f84" in row for row in rows)


def test_reused_cr18_identifier_is_disambiguated_without_rewriting_history():
    text = _text()
    review = text.split(REVIEW, 1)[1]
    assert "section-89 SI-CR18-001" in review and "Claude126 SI-CR18-001" in review
    # Both historical uses remain; only the appended note disambiguates them.
    before = text.split(REVIEW, 1)[0]
    assert "(`SI-CR18-001`, closed by correction)" in before
    assert "| SI-CR18-001 | P2 | **Closed by test-only correction" in before
