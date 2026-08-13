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


def _root_text(name: str) -> str:
    return " ".join((ROOT / name).read_text(encoding="utf-8").split())


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


def test_epoch_host_bullet_agrees_with_the_current_active_epoch():
    """A historical host section must be amended when the epoch rolls.

    The top of OPERATIONAL_FACTS correctly named epoch-004 while the standing
    two-machine section still told operators that the epoch host ran
    epoch-003.  Compare relationships so this survives the next roll without
    pinning today's identifier in the test.
    """
    plan_active = _active_epochs(_text("ACTION_PLAN_2026-08-02.md"))
    facts = _text("OPERATIONAL_FACTS.md")
    match = re.search(
        r"\*\*Epoch host\*\*.*?runs the active `(paper-epoch-\d+)`",
        facts,
        flags=re.IGNORECASE,
    )
    assert match, "OPERATIONAL_FACTS has no standing epoch-host status bullet"
    assert {match.group(1)} == plan_active, (
        "the standing epoch-host bullet disagrees with the action plan: "
        f"{match.group(1)!r} vs {sorted(plan_active)}"
    )


def test_completed_epoch_004_roll_replaced_its_predeployment_queue():
    """Known pre-roll instructions cannot remain current after deployment."""
    documents = {
        "ACTION_PLAN_2026-08-02.md": _text("ACTION_PLAN_2026-08-02.md"),
        "SESSION_HANDOFF.md": _text("SESSION_HANDOFF.md"),
        "OPERATIONAL_FACTS.md": _text("OPERATIONAL_FACTS.md"),
        "FEATURE_MILESTONE_RECORD.md": _text("FEATURE_MILESTONE_RECORD.md"),
    }
    stale = (
        "CR-W2 cash-dividend / explicit cash-transfer handler** — **COMPLETE, MERGED, NOT DEPLOYED",
        "Include this already-merged fix with CR-W2 in one owner-authorized epoch-004 roll",
        "CR-W2/AP-7 are already queued for the same roll",
        "This is undeployed until the complete epoch-004 roll",
        "Standing watch until epoch-004 deployment",
        "This feature is not deployed into the active epoch",
        "will not help the currently running epoch until the corrected branch is merged",
    )
    hits = [
        f"{name}: {phrase}"
        for name, text in documents.items()
        for phrase in stale
        if phrase in text
    ]
    assert not hits, "superseded epoch-004 deployment state remains: " + "; ".join(hits)

    action_plan_raw = (
        ROOT / "docs" / "ACTION_PLAN_2026-08-02.md"
    ).read_text(encoding="utf-8")
    ap7_rows = [line for line in action_plan_raw.splitlines() if line.startswith("| AP-7 |")]
    assert len(ap7_rows) == 1, "the action plan must contain exactly one AP-7 row"
    assert "deployed" in ap7_rows[0].lower() and "b837374" in ap7_rows[0], (
        "the AP-7 ledger row must record its epoch-004 deployment"
    )


def test_current_review_documents_have_no_validation_placeholders():
    """A validation claim must contain a measured result, never a token."""
    placeholders = re.compile(
        r"\b(?:FULL_SUITE|COUNTER_REVIEW_SUITE|FINAL_TREE|FINAL_STATIC"
        r"|COUNTER_REVIEW_TREE|SELL_TREE|INTEGRATION_SUITE)_RESULT\b"
    )
    names = (
        "SESSION_HANDOFF.md",
        "FEATURE_MILESTONE_RECORD.md",
        "REVIEW_2026-08-12_AP9_ALLOCATION_REVIEW_VISIBILITY.md",
        "REVIEW_2026-08-13_CLAUDE_COUNTERREVIEW_AND_AP11.md",
    )
    hits = [name for name in names if placeholders.search(_text(name))]
    assert not hits, f"unresolved validation placeholders remain in {hits}"


def test_operator_guide_uses_the_eastern_paper_observation_clock():
    """The installer converts 16:30 Eastern to the host's local timezone."""
    guide = _root_text("HOW_TO_USE.md")
    assert "observation fires at 16:30 local" not in guide
    assert "16:30 Eastern" in guide


def test_handoff_does_not_describe_the_merged_independent_review_branch_as_stale_topology():
    """Counter-review IPRCR-001 -- the recurrence class IPR-002 itself fixed.

    The independent-review handoff truthfully said its branch was local-only
    and unpushed WHEN COMMITTED, but the owner then pushed and merged it as
    PR #196 (`1a46881`) and the handoff on main kept telling the next operator
    to switch to the branch and verify a pre-merge range. Historical review
    reports may keep their as-written topology; the CURRENT handoff may not.
    Each phrase below is a known-stale claim that should never be true again.
    """
    handoff = _text("SESSION_HANDOFF.md")
    stale = (
        "The branch is local-only by the owner's instruction",
        "Switch to codex/independent-full-review-20260812",
        "Review the ordered range `b356292..HEAD`",
    )
    hits = [phrase for phrase in stale if phrase in handoff]
    assert not hits, (
        "the handoff still describes the pre-merge PR #196 topology: "
        + "; ".join(hits)
    )


def test_ap11_supersedes_the_full_ap7_production_fix_claim():
    """CODCR-001: deployed AP-7 code is not a deployed end-to-end fix.

    AP-11 proved from a later live negative-age alert that the outer
    production call path froze the nested AP-7 clock. Current-state records
    must preserve the original deployment observation without continuing to
    call the complete production path fixed while AP-11 is undeployed.
    """
    documents = {
        "ACTION_PLAN_2026-08-02.md": _text("ACTION_PLAN_2026-08-02.md"),
        "OPERATIONAL_FACTS.md": _text("OPERATIONAL_FACTS.md"),
    }
    stale = (
        "AP-7 confirmed fixed in production",
        "AP-7 is confirmed fixed in production",
    )
    hits = [
        f"{name}: {phrase}"
        for name, text in documents.items()
        for phrase in stale
        if phrase in text
    ]
    assert not hits, (
        "current records retain the full-fix claim invalidated by AP-11: "
        + "; ".join(hits)
    )

    action_plan_raw = (
        ROOT / "docs" / "ACTION_PLAN_2026-08-02.md"
    ).read_text(encoding="utf-8")
    ap7_rows = [
        line for line in action_plan_raw.splitlines() if line.startswith("| AP-7 |")
    ]
    assert len(ap7_rows) == 1, "the action plan must contain exactly one AP-7 row"
    assert "AP-11" in ap7_rows[0] and "not deployed" in ap7_rows[0].lower(), (
        "the AP-7 ledger row must disclose the undeployed AP-11 production-path gap"
    )

    facts_raw = (ROOT / "docs" / "OPERATIONAL_FACTS.md").read_text(
        encoding="utf-8"
    )
    active_epoch = re.search(
        r"### `paper-epoch-\d+` is active.*?(?=\n### )",
        facts_raw,
        flags=re.DOTALL,
    )
    assert active_epoch, "OPERATIONAL_FACTS has no active-epoch section"
    active_epoch_text = active_epoch.group(0)
    assert (
        "AP-11" in active_epoch_text
        and "not deployed" in active_epoch_text.lower()
    ), (
        "the durable active-epoch facts must disclose that AP-11 is not deployed"
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


def test_current_dividend_handler_guidance_is_reviewed_and_date_correct():
    """CR-W2 review must replace its unsafe submitted accounting guidance."""
    for name in (
        "SESSION_HANDOFF.md",
        "ACTION_PLAN_2026-08-02.md",
        "OPERATIONAL_FACTS.md",
        "OPERATIONS_RUNBOOK.md",
    ):
        text = _text(name)
        for stale in (
            "2026-09-09",
            "08-09 ex-date",
            "JNLC`/`CSD`/`CSW` → `record_cash_transfer",
        ):
            assert stale not in text, f"{name} retains stale CR-W2 claim {stale!r}"

    # Contract update 2026-08-11 (epoch-004 roll): these positive assertions
    # originally targeted SESSION_HANDOFF, which declares itself replaced
    # every round. Requiring a status document to keep reciting one
    # milestone's details forever is the mirror of the DCCR-CR-003 mistake --
    # a REQUIRED literal must be a claim that stays true, and "this round is
    # about CR-W2" does not. The durable home for the fact is
    # OPERATIONAL_FACTS, which is explicitly append-and-amend, so assert it
    # there. Stronger, not weaker: the fact can no longer be lost by the next
    # handoff rewrite, which is exactly how it was lost before.
    facts = _text("OPERATIONAL_FACTS.md")
    assert "2026-09-10" in facts, (
        "the AEP payable date must survive in the durable operational record"
    )
    assert "JNLC" in facts and "fail" in facts.lower(), (
        "the durable record must still say generic JNLC fails closed"
    )


def test_current_handoff_replaces_superseded_dividend_review_state():
    """The merged counter-review and first observation must replace old state.

    Counter-review correction (DCCR-CR-003, 2026-08-10): this guard
    originally also banned the literal "It is **not merged and not
    deployed**". That violates this module's own rule at the top of the
    file -- a banned literal must be "a phrase that should never be true
    again", and *every* future review branch is legitimately not merged and
    not deployed. Banning it would force later authors to either describe a
    normal state in contorted language or weaken this guard.

    Replaced with a POSITIVE assertion, which is strictly stronger: the
    handoff must actually record that the dividend handler merged. A
    positive claim cannot be dodged by rephrasing the negative one.
    """
    handoff = _text("SESSION_HANDOFF.md")
    for stale in (
        "main` / `origin/main` at `c36b615",
        "do not alter it or claim evidence is accumulating until its scheduled observation",
    ):
        assert stale not in handoff, f"handoff retains stale state: {stale!r}"

    # Same contract update. The merge fact is durable history, so it belongs
    # in the append-and-amend record rather than in a per-round status file
    # that is legitimately rewritten once the milestone is deployed and
    # superseded.
    plan = _text("ACTION_PLAN_2026-08-02.md")
    assert "PR #182" in plan or "PR #184" in plan, (
        "the action plan must retain the CR-W2 merge history"
    )

    action_plan = _text("ACTION_PLAN_2026-08-02.md")
    for stale in (
        "epoch-003 still had **zero observations**",
        "epoch-003 had zero observations",
    ):
        assert stale not in action_plan, (
            f"action plan retains superseded evidence state: {stale!r}"
        )


def test_current_documents_do_not_publish_exact_account_balances():
    """Account cash/equity are sensitive machine-local facts, not document data.

    Counter-review extension (DCCR-CR-001, 2026-08-10): the original guard
    scanned only the handoff, which is where that round's instance happened
    to be -- but the same absolute balance was still sitting in the action
    plan's AP-6 row and, worse, in `OPERATIONAL_FACTS.md`, the file that is
    explicitly never rewritten. Scan the whole class of current documents.

    The rule this pins (see OPERATIONAL_FACTS §1): a *difference* can be
    load-bearing evidence and stays -- the AP-6 diagnosis needs its $0.03 --
    but an absolute balance proves nothing that `matched` plus a mismatch
    count does not already prove, so it never belongs in a committed
    document.
    """
    patterns = (
        r"\bcash\s+`?\d[\d,]*\.\d+`?",
        r"\btotal equity\s+`?\d[\d,]*\.\d+`?",
    )
    for name in (
        "SESSION_HANDOFF.md",
        "ACTION_PLAN_2026-08-02.md",
        "OPERATIONAL_FACTS.md",
        "OPERATIONS_RUNBOOK.md",
    ):
        text = _text(name)
        for pattern in patterns:
            assert re.search(pattern, text, flags=re.IGNORECASE) is None, (
                f"{name} publishes an exact account balance matching {pattern!r}"
            )


def test_current_documents_do_not_publish_account_identifiers():
    """Even shortened broker account identifiers are machine-local facts.

    Counter-review extension (E3CR, 2026-08-10): the original guard scanned
    only the handoff and only the ellipsis-shortened shape, but the WORSE
    historical case was the FULL dashed identifier committed to the handoff
    at `bf5d5ce` (2026-08-05) -- which the fragment regex never matched.
    Scan every current-state document for both shapes. The full-UUID check
    is unconditional because a dashed UUID has no legitimate reason to
    appear in these documents; the hex-fragment check stays anchored to the
    word "account" so ordinary commit hashes keep passing.
    """
    for name in (
        "SESSION_HANDOFF.md",
        "ACTION_PLAN_2026-08-02.md",
        "OPERATIONAL_FACTS.md",
        "OPERATIONS_RUNBOOK.md",
    ):
        text = _text(name)
        fragment = re.search(
            r"(?:broker\s+)?account\s+`?[0-9a-f]{8,}(?:…|\.\.\.)",
            text,
            flags=re.IGNORECASE,
        )
        assert fragment is None, f"{name} contains an account identifier fragment"
        full_id = re.search(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            text,
            flags=re.IGNORECASE,
        )
        assert full_id is None, f"{name} contains a full dashed identifier"


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
