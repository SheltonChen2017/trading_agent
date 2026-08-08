"""Current-state documents must not retain known contradictory status claims.

CCX-002. The first version of this guard asserted the CURRENT epoch by name
(`paper-epoch-002` has been active since 2026-08-06). That inverts what a
consistency test is for: rolling to epoch-003 is a legitimate, expected event
that would have failed the suite, and the obvious fix would have been to edit
the assertion -- so the guard would have enforced today's state rather than
preventing contradiction, and would have been "fixed" by weakening every time
reality moved.

What is durable is the *relationship* between documents, not the values:

* the active plan must not simultaneously call an epoch active and closed;
* a document must not describe as unbuilt something another current section
  records as complete; and
* the sweep record must carry exactly one finding count and status.

Those hold whatever the epoch number is. Where a literal string is
unavoidable, it is a phrase that should never be true again (a known-stale
claim), never one that must stay true.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(name: str) -> str:
    return " ".join((ROOT / "docs" / name).read_text(encoding="utf-8").split())


def _active_epochs(text: str) -> set[str]:
    """Epoch ids the document asserts are currently ACTIVE."""
    return set(
        re.findall(r"`(paper-epoch-\d+)` (?:is|has been) [Aa]ctive", text)
    )


def _closed_epochs(text: str) -> set[str]:
    return set(re.findall(r"`(paper-epoch-\d+)` (?:is|was) CLOSED", text))


def test_no_document_calls_the_same_epoch_both_active_and_closed():
    """The contradiction CXL-005 actually found, expressed as a relationship.

    Survives an epoch roll: it constrains how the documents agree, not which
    epoch is running.
    """
    for name in (
        "ACTION_PLAN_2026-08-02.md",
        "SESSION_HANDOFF.md",
        "GENERAL_READINESS_STATUS.md",
    ):
        text = _text(name)
        both = _active_epochs(text) & _closed_epochs(text)
        assert not both, f"{name} calls {sorted(both)} both active and closed"


def test_exactly_one_epoch_is_described_as_active_across_current_documents():
    active: dict[str, set[str]] = {}
    for name in ("ACTION_PLAN_2026-08-02.md", "SESSION_HANDOFF.md"):
        found = _active_epochs(_text(name))
        if found:
            active[name] = found
    claimed = set().union(*active.values()) if active else set()
    assert len(claimed) <= 1, (
        f"current documents disagree about the active epoch: {active}"
    )


def test_current_documents_do_not_call_completed_work_unstarted():
    """Known-stale claims only -- each of these should never be true again."""
    plan = _text("ACTION_PLAN_2026-08-02.md")
    readiness = _text("GENERAL_READINESS_STATUS.md")
    runbook = _text("OPERATIONS_RUNBOOK.md")
    for document, phrase in (
        (plan, "19 statuses, no `dismissed`"),
        (plan, "no Backtest tab"),
        (readiness, "GR-6 .. GR-9 — not started"),
        (runbook, "alert_delivery` remains unproducible"),
    ):
        assert phrase not in document, (
            f"a completed milestone is still described as unbuilt: {phrase!r}"
        )


def test_the_sweep_record_carries_one_finding_count_and_status():
    review = _text("REVIEW_2026-08-07_FULL_CODEBASE_SWEEP.md")
    for stale in (
        "ALL SEVENTEEN findings are FIXED",
        "Everything else remains open and",
        "all twelve P3s are recorded but unfixed",
    ):
        assert stale not in review, f"superseded status claim retained: {stale!r}"
    # Exactly one headline count, whatever it says.
    headlines = re.findall(r"ALL (\w+) findings were fixed", review)
    assert len(set(headlines)) <= 1, f"conflicting headline counts: {headlines}"
