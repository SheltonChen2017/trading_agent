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


def _doc_path(name: str) -> Path:
    """Find one active document after the 2026-08-17 docs reorganization."""
    candidates = [ROOT / "docs" / name]
    candidates.extend(
        ROOT / "docs" / folder / name
        for folder in ("Review", "research", "process", "operations", "architecture")
    )
    found = [path for path in candidates if path.is_file()]
    assert len(found) == 1, f"expected one active document named {name!r}, found {found}"
    return found[0]


def _text(name: str) -> str:
    return " ".join(_doc_path(name).read_text(encoding="utf-8").split())


def _root_text(name: str) -> str:
    return " ".join((ROOT / name).read_text(encoding="utf-8").split())


def test_docs_root_contains_only_canonical_milestone_and_alpha_records() -> None:
    allowed = {
        "ACTION_PLAN_2026-08-20.md",
        "SESSION_HANDOFF.md",
        "Alpha_Test_Implementation_Plan.md",
        "alpha-result.md",
        "FEATURE_MILESTONE_RECORD.md",
        "EPOCH_005_ROLL_PLAN.md",
        "REBAL1_MILESTONE_PLAN.md",
    }
    actual = {path.name for path in (ROOT / "docs").iterdir() if path.is_file()}
    assert actual == allowed
    assert not list((ROOT / "docs").glob("REVIEW_*.md"))


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
        "ACTION_PLAN_2026-08-20.md",
        "SESSION_HANDOFF.md",
        "GENERAL_READINESS_STATUS.md",
    ):
        text = _text(name)
        both = _active_epochs(text) & _closed_epochs(text)
        assert not both, f"{name} calls {sorted(both)} both active and closed"


def test_exactly_one_epoch_is_described_as_active_across_current_documents():
    active: dict[str, set[str]] = {}
    for name in ("ACTION_PLAN_2026-08-20.md", "SESSION_HANDOFF.md"):
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
    plan_active = _active_epochs(_text("ACTION_PLAN_2026-08-20.md"))
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
        "ACTION_PLAN_2026-08-20.md": _text("ACTION_PLAN_2026-08-20.md"),
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
        ROOT / "docs" / "ACTION_PLAN_2026-08-20.md"
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
        r"|COUNTER_REVIEW_TREE|SELL_TREE|INTEGRATION_SUITE|SELCR_TREE)_RESULT\b"
    )
    names = (
        "SESSION_HANDOFF.md",
        "FEATURE_MILESTONE_RECORD.md",
        "REVIEW_2026-08-12_AP9_ALLOCATION_REVIEW_VISIBILITY.md",
        "REVIEW_2026-08-13_CLAUDE_COUNTERREVIEW_AND_AP11.md",
        "REVIEW_2026-08-13_SELL1_AND_BRANCH_CLEANUP.md",
        "REVIEW_2026-08-13_BUY1_SUGGESTION_PICKER.md",
        "REVIEW_2026-08-14_TRADE1_DISCRETE_TRADING.md",
    )
    hits = [name for name in names if placeholders.search(_text(name))]
    assert not hits, f"unresolved validation placeholders remain in {hits}"


def test_operator_guide_tells_the_reader_to_read_the_installed_trigger():
    """OBSCLK-001: the observation time must be MEASURED, not derived.

    Two true statements disagree on this host. The installer's rule since
    2026-08-08 is 16:30 Eastern converted to local (13:30 Pacific), but the
    epoch host's task was registered 2026-08-05 with a literal 16:30 local
    trigger, and an epoch roll re-enables existing tasks rather than
    reinstalling them -- so the older trigger persists. An earlier correction
    aligned this guide to the installer SOURCE without re-measuring the
    INSTALLED task, which would have had a Pacific operator shut down three
    hours early and silently lose the session.

    Pinned as a POSITIVE requirement -- the guide must hand the reader the
    command that reads the real trigger -- because that stays correct after
    any future reinstall, whereas asserting either clock would go stale the
    moment the other one applied.
    """
    guide = _root_text("HOW_TO_USE.md")
    assert "Get-ScheduledTask -TaskName 'TradingAgent-Paper-PaperObservation'" in guide, (
        "the guide must show how to READ the installed trigger"
    )
    assert "rather than computing it" in guide or "never derive it" in guide.lower()
    # And it must still name the real hazard: a machine shut down too early.
    assert "does not count toward the 60" in guide


def test_epoch005_roll_record_replaces_its_unexecuted_plan():
    """OBR-001/002: an executed roll cannot remain an actionable draft.

    The submitted tree updated the action-plan summary and operational facts,
    but left the dedicated roll document saying it was unauthorized and had
    not executed.  It also named ``paper-epoch-status``, which is not a CLI
    command.  The retained record must be unmistakably historical and use the
    real read-only status command.
    """
    record = _text("EPOCH_005_ROLL_PLAN.md")
    for stale in (
        "NOT YET AUTHORIZED",
        "Nothing in this document has been executed",
        "If the roll is authorized",
        "paper-epoch-status",
        'The argument against rolling is only ever "we lose accrued evidence"',
    ):
        assert stale not in record, f"epoch-005 record retains stale plan text: {stale!r}"
    assert "executed 2026-08-13" in record.lower()
    assert "paper-evidence-status" in record


def test_epoch005_deployment_status_is_consistent_in_the_action_plan():
    """OBR-003: detail rows must agree with the epoch-005 roll summary."""
    raw = (ROOT / "docs" / "ACTION_PLAN_2026-08-20.md").read_text(
        encoding="utf-8"
    )
    prefixes = (
        "| **Ticker-suggestion disclosure policy (AP-8b)**",
        "| QC-2 research-look registry |",
        "| GR-7d |",
        "| AP-8 |",
        "| AP-9 |",
        "| AP-10 |",
        "| AP-11 |",
        "| SELL-1 |",
    )
    for prefix in prefixes:
        rows = [line for line in raw.splitlines() if line.startswith(prefix)]
        assert len(rows) == 1, f"expected exactly one current row starting {prefix!r}"
        assert "DEPLOYED 2026-08-13" in rows[0], (
            f"{prefix!r} does not agree with the recorded epoch-005 deployment"
        )


def test_current_handoff_records_the_epoch005_roll_and_reviewable_head():
    """OBR-004: durable state changes require a replaced current handoff."""
    handoff = _text("SESSION_HANDOFF.md")
    for stale in (
        "paper-epoch-004 remains the only active evidence epoch",
        "remain development changes not deployed into that frozen epoch",
        "Do not deploy or roll `paper-epoch-004`",
        "awaiting the owner's merge at handoff",
    ):
        assert stale not in handoff, f"current handoff retains pre-roll state: {stale!r}"
    assert "paper-epoch-005" in handoff
    assert "4de784e" in handoff
    assert "1cb8abf" in handoff


def test_roll_freshness_guidance_is_conditional_not_universal():
    """OBR-005: freshness expires only after the configured age window."""
    facts = _doc_path("OPERATIONAL_FACTS.md").read_text(encoding="utf-8")
    assert "`readiness` fails on `reconciliation_freshness` during any roll" not in facts
    assert "can fail" in facts.lower() and "reconciliation_freshness" in facts


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
    """CODCR-001, amended 2026-08-13 when the epoch-005 roll deployed AP-11.

    The original guard pinned "AP-7's site fix is deployed but AP-11's
    orchestration repair is NOT" -- true from 2026-08-13 until that roll, and
    deliberately written as a tripwire that would redden the moment the
    deployment changed, forcing the records to move with reality instead of
    drifting behind it. It fired exactly as intended.

    What remains durably true, and is what this now pins: the original
    two-green-cycles observation must never again be stated as proof that the
    whole production path was fixed, because AP-11 disproved that inference
    from a live alert. That claim can never become true retroactively, so it
    stays banned. The deployment STATE is no longer asserted here -- it moves
    every roll, and other guards already keep the active-epoch records
    self-consistent.
    """
    documents = {
        "ACTION_PLAN_2026-08-20.md": _text("ACTION_PLAN_2026-08-20.md"),
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
        ROOT / "docs" / "ACTION_PLAN_2026-08-20.md"
    ).read_text(encoding="utf-8")
    ap7_rows = [
        line for line in action_plan_raw.splitlines() if line.startswith("| AP-7 |")
    ]
    assert len(ap7_rows) == 1, "the action plan must contain exactly one AP-7 row"
    # The row must still connect AP-7 to AP-11 -- a reader who finds the AP-7
    # row alone must not conclude the site fix was ever the whole story.
    assert "AP-11" in ap7_rows[0], (
        "the AP-7 ledger row must still reference AP-11, which corrected the "
        "production call path its own site fix did not reach"
    )

def test_current_documents_do_not_call_completed_work_unstarted():
    """Known-stale claims only -- each of these should never be true again."""
    plan = _text("ACTION_PLAN_2026-08-20.md")
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
        "ACTION_PLAN_2026-08-20.md",
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
    plan = _text("ACTION_PLAN_2026-08-20.md")
    assert "PR #182" in plan or "PR #184" in plan, (
        "the action plan must retain the CR-W2 merge history"
    )

    action_plan = _text("ACTION_PLAN_2026-08-20.md")
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
        "ACTION_PLAN_2026-08-20.md",
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
        "ACTION_PLAN_2026-08-20.md",
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
    raw = _doc_path(name).read_text(encoding="utf-8")
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
    combined = _doc_path("REVIEW_2026-08-08_COMBINED_SCAN_FIX_LEDGER.md").read_text(
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


def _mainline_ref() -> str | None:
    """The ref that "merged" actually means, preferring the published one."""
    for ref in ("origin/main", "main"):
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            cwd=ROOT, capture_output=True,
        )
        if probe.returncode == 0:
            return ref
    return None


_TOPOLOGY_PATTERNS = {
    "ACTION_PLAN_2026-08-20.md": r"Current development topology.*?`([0-9a-f]{7,40})`",
    "SESSION_HANDOFF.md": r"Published `origin/main` at audit time:\s*`([0-9a-f]{7,40})`",
}


def test_a_declared_current_mainline_hash_is_really_on_the_mainline():
    """HEDGE1CR-001. The declared hash must be REACHABLE from the mainline,
    not equal to its tip.

    The first version of this guard asserted equality with `origin/main`.
    That cannot stay green, and the failure is structural rather than
    careless: merging the very branch that updates the records creates a new
    merge commit, so the hash the records name is one behind the instant it
    lands. A records-only follow-up merges as another commit and is stale
    again -- no state satisfies the equality assertion for longer than one
    merge, and `main` itself would carry the red test.

    Reachability is the durable part, and it still catches what HEDGER-007
    was really about: a declared hash that is fiction, a typo, or a commit
    that only ever existed on a feature branch. Recency cannot be asserted
    from inside the commit being merged -- the same "false by construction"
    rule this module's docstring already states, and the reason its sibling
    guards test relationships instead of today's values.
    """
    mainline = _mainline_ref()
    if mainline is None:  # pragma: no cover - export or detached checkout
        pytest.skip("no mainline ref available")
    for name, pattern in _TOPOLOGY_PATTERNS.items():
        match = re.search(pattern, _text(name), flags=re.IGNORECASE)
        assert match, f"{name} has no parseable current-main declaration"
        declared = match.group(1)
        reachable = subprocess.run(
            ["git", "merge-base", "--is-ancestor", declared, mainline],
            cwd=ROOT, capture_output=True,
        )
        assert reachable.returncode == 0, (
            f"{name} calls {declared} current main, but it is not reachable "
            f"from {mainline} at all"
        )


def test_hedge_docs_do_not_exempt_a_runtime_deployment_from_epoch_lineage():
    """A stable mandate/policy fingerprint does not make a new code commit
    deployable inside an active evidence epoch."""
    handoff = _text("SESSION_HANDOFF.md")
    mandate = _text("MANDATE.md")
    assert "no deployment-closes-the-epoch consequence" not in handoff.lower()
    for text in (handoff, mandate):
        assert not re.search(
            r"active `paper-epoch-005` is (?:therefore )?unaffected",
            text,
            flags=re.IGNORECASE,
        )


def _repository_commits_claimed_unreachable(text: str) -> list[str]:
    """Commit hashes a document asserts are local-only / unpushed / unmerged.

    Matches a short hash in backticks within one clause of an unreachability
    claim, in either order ("`abc1234` is local-only", "local-only: `abc1234`").

    STALLCR-004: the original alternation had `unmerged` as one word only, so
    the phrasing that actually shipped -- "not merged or deployed" -- slipped
    straight through the guard written to catch it, and the STALL-1 row was
    merged by PR #221 still saying it was not merged. Multi-word forms of the
    same claim are now matched too.
    """
    claim = (
        r"(?:local[- ]only|not (?:yet )?(?:been )?(?:pushed|merged|published)"
        r"|unpushed|unmerged|unpublished|cannot fetch)"
    )
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

    STALLCR-004: the base is the MAINLINE, not `HEAD`. "Merged" means merged
    to `main`; measuring against `HEAD` makes every commit on the branch you
    are working on look merged, so a row that correctly says "not merged yet"
    while the work is still under review would fail on its own branch and the
    obvious fix would be to delete the true sentence.
    """
    mainline = _mainline_ref()
    if mainline is None:  # pragma: no cover - export or detached checkout
        pytest.skip("no mainline ref available")

    stale: list[str] = []
    for name in ("SESSION_HANDOFF.md", "ACTION_PLAN_2026-08-20.md"):
        text = _text(name)
        for commit in _repository_commits_claimed_unreachable(text):
            reachable = subprocess.run(
                ["git", "merge-base", "--is-ancestor", commit, mainline],
                cwd=ROOT, capture_output=True,
            )
            if reachable.returncode == 0:
                stale.append(
                    f"{name} calls {commit} unreachable, but it is in {mainline}"
                )
    assert not stale, "; ".join(stale)


def test_no_action_plan_row_calls_its_own_merged_commits_unmerged():
    """STALLCR-004. The sentence-scoped guard above cannot see the shape this
    actually took: the STALL-1 ledger row put "not merged or deployed" in its
    status sentence and the commit hashes in the NEXT sentence, so no claim
    and hash ever shared a clause, and PR #221 merged the row still saying it
    was not merged.

    The durable unit for a ledger is the ROW, not the sentence: one table row
    is one status claim about one named set of commits. Checked against the
    mainline, so a row that truthfully says "not merged" while its work is
    still under review stays green on its own branch.
    """
    mainline = _mainline_ref()
    if mainline is None:  # pragma: no cover - export or detached checkout
        pytest.skip("no mainline ref available")

    claim = re.compile(
        r"not (?:yet )?(?:been )?(?:merged|pushed|published)|unmerged|local[- ]only",
        flags=re.IGNORECASE,
    )
    raw = (ROOT / "docs" / "ACTION_PLAN_2026-08-20.md").read_text(encoding="utf-8")
    stale: list[str] = []
    for line in raw.splitlines():
        if not line.lstrip().startswith("|") or not claim.search(line):
            continue
        # Claim sentence plus the one after it. A ledger row also names the
        # DEPLOYED operational commit several sentences later, which is
        # merged and not what the claim is about, so whole-row scope would
        # red on a correct row and teach the reader to delete true text.
        sentences = line.split(".")
        suspect: set[str] = set()
        for index, sentence in enumerate(sentences):
            if claim.search(sentence):
                window = " ".join(sentences[index : index + 2])
                suspect.update(re.findall(r"`([0-9a-f]{7,40})`", window))
        for commit in sorted(suspect):
            reachable = subprocess.run(
                ["git", "merge-base", "--is-ancestor", commit, mainline],
                cwd=ROOT, capture_output=True,
            )
            if reachable.returncode == 0:
                stale.append(f"row claims unmerged but {commit} is in {mainline}")
    assert not stale, "; ".join(sorted(set(stale)))


def test_the_unreachability_parser_recognizes_multi_word_claims():
    """Pins the parser directly, not through today's documents: a document
    fix alone would leave the guard just as blind to the next phrasing."""
    for phrasing in (
        "`6aa7069`: not merged or deployed",
        "`6aa7069` has not been published",
        "`6aa7069` is not yet pushed",
        "unmerged: `6aa7069`",
        "`6aa7069` is local-only",
    ):
        assert _repository_commits_claimed_unreachable(phrasing) == ["6aa7069"], (
            phrasing
        )
    assert _repository_commits_claimed_unreachable("`6aa7069` merged in PR #221") == []


def test_sell1_current_records_do_not_reopen_merged_review_work():
    """SELL-1 reached main before its independent review was requested.

    Scoped to SELL-1's own ledger row (amended 2026-08-13 when BUY-1 was
    added). The first version banned the literal "PENDING INDEPENDENT REVIEW;
    not merged" across the WHOLE action plan -- but that sentence is exactly
    what every new, genuinely unreviewed feature row has to say, so the guard
    reddened on the very next feature and the obvious "fix" would have been to
    weaken it. That is the rule stated at the top of this module: a banned
    literal must be a claim that can never be true again, never one that must
    stay true. The intent -- SELL-1's record must not describe itself as
    unmerged -- survives, expressed against the row it is actually about.
    """
    handoff = _text("SESSION_HANDOFF.md")
    action_plan_raw = (
        ROOT / "docs" / "ACTION_PLAN_2026-08-20.md"
    ).read_text(encoding="utf-8")
    sell1_rows = [
        line for line in action_plan_raw.splitlines() if line.startswith("| SELL-1 |")
    ]
    assert len(sell1_rows) == 1, "the action plan must contain exactly one SELL-1 row"
    sell1_row = sell1_rows[0]

    row_hits = [
        phrase
        for phrase in ("PENDING INDEPENDENT REVIEW; not merged", "not merged, not deployed")
        if phrase in sell1_row
    ]
    assert not row_hits, (
        "the SELL-1 ledger row still describes merged work as unmerged: "
        + "; ".join(row_hits)
    )

    handoff_hits = [
        phrase
        for phrase in (
            "Independent review of this branch",
            "confirm whether user/claude/user-directed-sell-",
        )
        if phrase in handoff
    ]
    assert not handoff_hits, (
        "the handoff reopens merged SELL-1 work: " + "; ".join(handoff_hits)
    )
    assert "08fde9f" in action_plan_raw and "3ba3d41" in action_plan_raw


def test_buy1_current_records_close_the_merged_review():
    """BUY-1 is merged and independently corrected; current records stay so."""
    action_plan_raw = (
        ROOT / "docs" / "ACTION_PLAN_2026-08-20.md"
    ).read_text(encoding="utf-8")
    buy1_rows = [
        line for line in action_plan_raw.splitlines() if line.startswith("| BUY-1 |")
    ]
    assert len(buy1_rows) == 1, "the action plan must contain exactly one BUY-1 row"
    buy1_row = buy1_rows[0]
    stale = (
        "PENDING INDEPENDENT REVIEW",
        "not merged, not deployed",
    )
    hits = [phrase for phrase in stale if phrase in buy1_row]
    assert not hits, "the BUY-1 row still describes merged work as pending: " + "; ".join(hits)
    assert "e0df810" in buy1_row and "44a7f85" in buy1_row

    handoff = _text("SESSION_HANDOFF.md")
    assert "codex/review-buy1-suggestion-picker-20260813" in handoff
    assert "44a7f85" in handoff


def test_deleted_gr7d_ref_is_not_called_irrecoverable_while_object_remains():
    """Deleting a branch ref is not the same event as pruning its objects."""
    plan = _text("reference/THREE_SLEEVE_ENGINE_PLAN.md")
    assert "no longer exists anywhere" not in plan
    assert "85a77291a3a8de88a82b3670dcf05793b6825c1c" in plan
    assert "may disappear during Git pruning" in plan


def test_closed_alpha_plan_distinguishes_valid_null_runs_from_invalid_legacy_runs():
    """A null result is valid evidence of no detected edge, not an invalid run."""
    plan = _text("Alpha_Test_Implementation_Plan.md")
    action_plan = _text("ACTION_PLAN_2026-08-20.md")

    stale_claims = (
        "No historical alpha result in this program is valid",
        "Every historical QuantConnect result in `docs/alpha-result.md` remains invalid",
    )
    for claim in stale_claims:
        assert claim not in plan
        assert claim not in action_plan

    # SBDCCR-002: assert the RELATIONSHIP, not one blessed phrasing. The
    # original guard pinned the literal "VALID but null", which this
    # module's own docstring warns against -- a legitimate rewording
    # ("valid, and null") would redden it and the obvious fix would be to
    # delete the assertion. A window regex keeps the same strength: each
    # document must state that the reviewed runs are valid AND null.
    validity = re.compile(r"valid[^.]{0,60}null", re.IGNORECASE)
    for label, text in (("alpha plan", plan), ("action plan", action_plan)):
        assert validity.search(text), (
            f"the {label} must state that the reviewed Stage 0/1 runs are "
            "valid and null, not merely avoid calling them invalid"
        )


def test_strongbuy_primary_comparison_keeps_structural_zero_months():
    """Exactly-ten-name months are real strategy months, not missing evidence."""
    plan = _text("reference/STRONGBUY_PORTFOLIO_TEST_PLAN.md")

    assert "remain in the primary P2−P1 series" in plan
    assert "whether those months are excluded" not in plan


def test_strongbuy_amendment_ledger_is_one_contiguous_markdown_table():
    """All amendment rows render under the ledger header instead of as raw pipes."""
    plan = (ROOT / "docs" / "reference" / "STRONGBUY_PORTFOLIO_TEST_PLAN.md").read_text(
        encoding="utf-8"
    )
    lines = plan.splitlines()
    amendments = [f"SBPA-{number:03d}" for number in range(1, 12)]
    positions: dict[str, int] = {}
    for amendment in amendments:
        rows = [
            index
            for index, line in enumerate(lines)
            if line.startswith(f"| {amendment} |")
        ]
        # SBDCCR-003: a missing row raised StopIteration -- an error with
        # no message, rather than a failure naming what vanished.
        assert len(rows) == 1, (
            f"expected exactly one {amendment} ledger row, found {len(rows)}"
        )
        positions[amendment] = rows[0]

    ordered = [positions[amendment] for amendment in amendments]
    assert ordered == list(range(ordered[0], ordered[0] + len(amendments))), (
        "the amendment rows are not one contiguous table: "
        f"{dict(zip(amendments, ordered))}"
    )


def test_a_superseded_program_is_not_also_the_next_owner_decision():
    """A replaced program must not still be advertised as the blocking step.

    2026-08-20: the owner replaced the Strong-Buy program (SBP) with the
    Analyst-Consensus ETF Rotation program. The failure this guards against is
    PARTIAL replacement -- one document marking a plan superseded while the
    action plan still tells the reader its freeze is what happens next. Stated
    as a relationship so it survives the next replacement: whichever plan
    declares itself superseded must not also own the action plan's blocking
    decision.
    """
    plans = {
        "SBP": "reference/STRONGBUY_PORTFOLIO_TEST_PLAN.md",
        "ACER": "reference/ANALYST_CONSENSUS_ETF_ROTATION_PLAN.md",
    }
    action_plan = _text("ACTION_PLAN_2026-08-20.md")
    blocking = re.search(
        r"\*\*([A-Z]+)-0 adoption\*\*[\s\S]{0,300}?only decision blocking",
        action_plan,
    )
    assert blocking, "the action plan must name one blocking -0 adoption"
    blocking_prefix = blocking.group(1)

    for prefix, name in plans.items():
        superseded = _text(name).startswith("# ") and bool(
            re.search(r"Status: \*\*SUPERSEDED", _text(name))
        )
        if superseded:
            assert prefix != blocking_prefix, (
                f"{name} declares itself superseded while the action plan still "
                f"names {prefix}-0 adoption as the blocking decision"
            )
        elif prefix == blocking_prefix:
            assert _doc_path(name).is_file(), (
                f"the action plan blocks on {prefix}-0 but {name} does not exist"
            )


def test_reference_index_matches_a_superseded_program_status():
    """ACERDOC-003: the archive index must not advertise SBP as actionable.

    A plan can remain valuable historical design work after it is superseded,
    but callers that start from the archive index must be sent to the current
    program rather than to an owner decision that no longer exists.
    """
    sbp = _text("reference/STRONGBUY_PORTFOLIO_TEST_PLAN.md")
    index_path = _doc_path("reference/README.md")
    index = index_path.read_text(encoding="utf-8")
    if re.search(r"Status: \*\*SUPERSEDED", sbp):
        # ACRV-001: `next()` raised StopIteration when the row was missing
        # -- an error with no message, the same defect CRV-003 closed in
        # the amendment-ledger guard one round earlier. A deleted row is a
        # legitimate failure mode of this guard and must name itself.
        sbp_rows = [
            line
            for line in index.splitlines()
            if line.startswith("| `STRONGBUY_PORTFOLIO_TEST_PLAN.md`")
        ]
        assert len(sbp_rows) == 1, (
            "expected exactly one STRONGBUY_PORTFOLIO_TEST_PLAN.md row in "
            f"the reference index, found {len(sbp_rows)}"
        )
        sbp_row = sbp_rows[0]
        assert "superseded" in sbp_row.lower(), (
            "the reference index still advertises a superseded plan as actionable"
        )
        assert "pending owner adoption" not in sbp_row.lower()
        assert "ANALYST_CONSENSUS_ETF_ROTATION_PLAN.md" in index


def test_open_acer_freeze_ledger_cannot_be_called_executable():
    """An open preregistration ledger and an executable freeze conflict.

    This survives later completion: once every open item is resolved, remove
    the open-ledger heading and this conditional stops constraining status.
    """
    freeze = _text("ACER_2026-08-20_ACER0A_FREEZE.md")
    reference = _text("reference/ANALYST_CONSENSUS_ETF_ROTATION_PLAN.md")
    action = _text("ACTION_PLAN_2026-08-20.md")
    if "Named open items that must close BEFORE the development run" in freeze:
        assert "not yet an executable preregistration" in freeze
        assert "preregistration is INCOMPLETE" in reference
        assert "executable preregistration incomplete" in action


def test_active_operational_docs_honor_start_when_available_semantics():
    """Installed catch-up semantics must not be documented as a hard skip."""
    installer = _root_text("scripts/install_windows_operational_tasks.ps1")
    facts = _text("OPERATIONAL_FACTS.md")
    diagnosis = _text("RECONCILIATION_ALERTS_2026-08-20_DIAGNOSIS.md")
    if "-StartWhenAvailable" in installer:
        assert "skipped rather than deferred" not in facts
        assert "guarantees the critical check fails" not in diagnosis
        assert "queued" in facts.lower()
        assert "queued" in diagnosis.lower()


def test_measured_sbr_absence_is_not_still_called_unmeasured():
    """The active ACER plan must consume the durable host measurement."""
    facts = _text("OPERATIONAL_FACTS.md")
    acer = _text("reference/ANALYST_CONSENSUS_ETF_ROTATION_PLAN.md")
    if "SBR-1 capture: measured absent" in facts:
        assert "task and artifact state has not been measured" not in acer
