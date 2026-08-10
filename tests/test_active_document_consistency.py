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
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _text(name: str) -> str:
    return " ".join((ROOT / "docs" / name).read_text(encoding="utf-8").split())


def _active_epochs(text: str) -> set[str]:
    """Epoch ids the document asserts are currently ACTIVE."""
    return set(
        re.findall(
            r"`(paper-epoch-\d+)` (?:(?:is|has been) )?active",
            text,
            flags=re.IGNORECASE,
        )
    )


def _closed_epochs(text: str) -> set[str]:
    return set(
        re.findall(
            r"`(paper-epoch-\d+)` (?:(?:is|was) )?closed",
            text,
            flags=re.IGNORECASE,
        )
    )


def test_epoch_status_parser_is_case_insensitive():
    """CCR-002: the canonical handoff deliberately spells status `ACTIVE`."""
    assert _active_epochs("`paper-epoch-003` ACTIVE") == {"paper-epoch-003"}
    assert _closed_epochs("`paper-epoch-002` closed") == {"paper-epoch-002"}


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


def test_current_handoff_does_not_retain_superseded_epoch_swap_instructions():
    """A completed epoch swap must replace, not merely precede, its old plan."""
    handoff = _text("SESSION_HANDOFF.md")
    for stale in (
        "Operational truth — epoch-002 is active but stalled",
        "Nothing below has been performed.",
        "paper-epoch-002 remains active in storage but stalled",
        "If deployment is authorized",
    ):
        assert stale not in handoff, (
            f"the current handoff retains a superseded epoch-swap instruction: {stale!r}"
        )


def test_current_handoff_does_not_publish_account_identifier_fragments():
    """Even shortened broker account identifiers are machine-local facts."""
    handoff = _text("SESSION_HANDOFF.md")
    fragment = re.search(
        r"(?:broker\s+)?account\s+`?[0-9a-f]{8,}(?:…|\.\.\.)",
        handoff,
        flags=re.IGNORECASE,
    )
    assert fragment is None, "SESSION_HANDOFF.md contains an account identifier fragment"


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


def _finding_statuses(name: str) -> dict[str, str]:
    """Every `| ID | Pri | Status |` row in a finding ledger."""
    raw = (ROOT / "docs" / name).read_text(encoding="utf-8")
    return {
        match.group(1): match.group(2)
        for match in re.finditer(r"^\| ((?:CXL|FCS|CCX)-\d+) \| \*{0,2}P\d\*{0,2} \| \*{0,2}(\w+)\*{0,2} \|", raw, re.M)
    }


def test_no_finding_is_open_in_one_ledger_and_fixed_in_another():
    """CCX-004. The gap that made this guard necessary in the first place.

    Codex's line-by-line review was merged in the SAME commit as the fixes for
    every finding it recorded, with all 24 rows still reading "Open" and
    "Pending owner instruction". That is precisely the active-document
    contradiction the review itself filed as CXL-005 -- reproduced inside the
    document that reported it.

    The first version of this guard checked plans, readiness and the runbook
    but not the finding ledgers, so it would not have caught it. Cross-check
    the ledgers against each other: a finding may not be Open in one place and
    Fixed in another.
    """
    review = _finding_statuses("REVIEW_2026-08-07_CODEX_LINE_BY_LINE.md")
    combined = (ROOT / "docs" / "REVIEW_2026-08-08_COMBINED_SCAN_FIX_LEDGER.md").read_text(
        encoding="utf-8"
    )
    assert review, "no finding rows parsed; the ledger format changed"
    contradictions = [
        f"{finding} is '{status}' in the line-by-line review but the combined "
        "ledger records it corrected"
        for finding, status in review.items()
        if status.lower() == "open"
        and re.search(rf"\| {finding} \|[^\n]*Fixed", combined)
    ]
    assert not contradictions, "; ".join(contradictions)


def test_a_finding_ledger_does_not_claim_everything_is_open_while_listing_fixes():
    """A headline count must agree with the rows beneath it."""
    for name in (
        "REVIEW_2026-08-07_CODEX_LINE_BY_LINE.md",
        "REVIEW_2026-08-07_FULL_CODEBASE_SWEEP.md",
    ):
        statuses = _finding_statuses(name)
        if not statuses:
            continue
        text = _text(name)
        claims_all_open = re.search(r"All \d+ remain open", text)
        any_fixed = any(v.lower() == "fixed" for v in statuses.values())
        assert not (claims_all_open and any_fixed), (
            f"{name} says everything is open while its own rows record fixes"
        )


def _repository_commits_claimed_unreachable(text: str) -> list[str]:
    """Commit hashes a document asserts are local-only / unpushed / unmerged.

    Matches a short hash in backticks within one clause of an unreachability
    claim, in either order ("`abc1234` is local-only", "local-only: `abc1234`").
    """
    claim = r"(?:local[- ]only|not pushed|unpushed|unmerged|cannot fetch)"
    near = rf"(?:`([0-9a-f]{{7,40}})`[^.]{{0,80}}?{claim}|{claim}[^.]{{0,80}}?`([0-9a-f]{{7,40}})`)"
    return [a or b for a, b in re.findall(near, text, flags=re.IGNORECASE)]


def test_no_document_calls_a_merged_commit_unreachable():
    """CCR-005. Reachability claims go stale the instant they are merged.

    This has now happened three times: Claude's handoff said "local only, not
    pushed" after pushing; Codex's line-by-line review was merged with all 24
    findings still "Open" (CCX-004); and Codex's fix for THAT was itself merged
    still saying its own commits were local-only and unmerged.

    It is structural, not carelessness. **Any statement about push or merge
    state, written in the commit that is being pushed or merged, is false by
    construction the moment it lands.** So it cannot be fixed by being more
    careful -- it needs a check that runs after the merge, which is this one.

    Skips when git is unavailable so the suite stays runnable from an export.
    """
    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=ROOT, capture_output=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        pytest.skip("not a git checkout")

    stale: list[str] = []
    for name in ("SESSION_HANDOFF.md", "ACTION_PLAN_2026-08-02.md"):
        text = _text(name)
        for commit in _repository_commits_claimed_unreachable(text):
            reachable = subprocess.run(
                ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
                cwd=ROOT, capture_output=True,
            )
            if reachable.returncode == 0:
                stale.append(f"{name} calls {commit} unreachable, but it is in HEAD")
    assert not stale, "; ".join(stale)
