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

import hashlib
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _doc_path(name: str) -> Path:
    """Resolve one document after the 2026-08-21 lifecycle reorganization."""
    direct = ROOT / "docs" / name
    if direct.is_file():
        return direct
    found = list((ROOT / "docs").rglob(name)) if "/" not in name else []
    assert len(found) == 1, f"expected one document named {name!r}, found {found}"
    return found[0]


def _text(name: str) -> str:
    return " ".join(_doc_path(name).read_text(encoding="utf-8").split())


def _root_text(name: str) -> str:
    return " ".join((ROOT / name).read_text(encoding="utf-8").split())


def _archived_handoff_text() -> str:
    path = (
        ROOT
        / "docs"
        / "Archive"
        / "Session"
        / "SESSION_HANDOFF_THROUGH_2026-08-25_SEP3_EIGHTH_DRY_RUN.md"
    )
    return " ".join(path.read_text(encoding="utf-8").split())


def test_docs_root_contains_only_current_coordination_and_active_plan() -> None:
    allowed = {
        "ACTION_PLAN_2026-08-20.md",
        "SESSION_HANDOFF.md",
        "FEATURE_MILESTONE_RECORD.md",
        "PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md",
        "README.md",
        "THREE_STRATEGY_PROJECT_DIRECTION.md",
    }
    actual = {path.name for path in (ROOT / "docs").iterdir() if path.is_file()}
    assert actual == allowed
    assert not list((ROOT / "docs").glob("REVIEW_*.md"))
    archived_handoff = (
        ROOT
        / "docs"
        / "Archive"
        / "Session"
        / "SESSION_HANDOFF_THROUGH_2026-08-25_SEP3_EIGHTH_DRY_RUN.md"
    )
    assert archived_handoff.is_file()
    assert "not a current instruction source" in " ".join(
        archived_handoff.read_text(encoding="utf-8").split()
    )


def test_current_handoff_is_a_bounded_unique_resume_snapshot() -> None:
    """A replaced handoff must not silently become another append-only archive."""
    path = ROOT / "docs" / "SESSION_HANDOFF.md"
    raw = path.read_text(encoding="utf-8")
    assert path.stat().st_size < 50_000, (
        "the current handoff has accumulated enough history to require another "
        "archive-and-replace cycle"
    )
    identifiers = re.findall(r"^##\s+(\d+)\.", raw, flags=re.MULTILINE)
    assert identifiers
    assert len(identifiers) == len(set(identifiers)), (
        f"current handoff section identifiers are ambiguous: {identifiers}"
    )


def test_open_root_p2_p3_findings_are_durably_queued_after_strategy_merge() -> None:
    """The post-integration backlog must carry every open reviewed issue.

    The archived counter-review owns the finding evidence.  The queued plan
    owns future closure.  Deriving the IDs from the review prevents a finding
    from disappearing because one status document was edited without the
    other; the exact 2/5 distribution is deliberately load-bearing.
    """
    report_path = (
        ROOT
        / "docs"
        / "Archive"
        / "Review"
        / "COUNTER_REVIEW_2026-08-27_ROOT_REMEDIATION.md"
    )
    plan_name = (
        "POST_INTEGRATION_FULL_PROJECT_REVIEW_AND_P2_P3_REMEDIATION.md"
    )
    plan_path = ROOT / "docs" / "Plan" / plan_name
    report = report_path.read_text(encoding="utf-8")
    plan = plan_path.read_text(encoding="utf-8")

    open_rows = re.findall(
        r"^\| `(RCR-\d{3})` \| (P[23]) \| Open \|",
        report,
        flags=re.MULTILINE,
    )
    assert len(open_rows) == 7, open_rows
    assert sum(priority == "P2" for _issue_id, priority in open_rows) == 2
    assert sum(priority == "P3" for _issue_id, priority in open_rows) == 5

    queued_rows = re.findall(
        r"^\| `(RCR-\d{3})` \| (P[23]) \| Open — queued \|",
        plan,
        flags=re.MULTILINE,
    )
    assert dict(queued_rows) == dict(open_rows)

    for document in (
        ROOT / "docs" / "Plan" / "README.md",
        ROOT / "docs" / "ACTION_PLAN_2026-08-20.md",
        ROOT / "docs" / "SESSION_HANDOFF.md",
    ):
        assert plan_name in document.read_text(encoding="utf-8")

    lowered = " ".join(plan.split()).lower()
    assert all(branch.lower() in lowered for branch in _THREE_STRATEGY_LANES)
    assert "merged into `main`" in lowered
    assert "owner explicitly starts" in lowered
    assert "does not unfreeze sep-3" in lowered
    assert "strategy research / quantconnect" in lowered
    assert "trading assistant / paper-live operations" in lowered


def test_three_strategy_parallel_baseline_is_exact_and_fail_closed() -> None:
    """The owner-directed lanes must not drift into competing coordination."""
    strategy_dir = ROOT / "docs" / "Strategy Description"
    workflow = _text("Strategy Description/THREE_STRATEGY_PARALLEL_WORKFLOW.md")
    handoff = _text("SESSION_HANDOFF.md")
    action = _text("ACTION_PLAN_2026-08-20.md")
    direction = _text("THREE_STRATEGY_PROJECT_DIRECTION.md")

    lanes = {
        "codex/strategy-analyst-revisions-v2": (
            "ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md",
            "ANALYST_REVISIONS_ETF_STRATEGY_BLUEPRINT_V2_EN.pdf",
            "eae7b9954aaf94212108505c52e31a558facd744967fd2526040d5147c616193",
        ),
        "codex/strategy-insider-buying": (
            "INSIDER_BUYING_IMPLEMENTATION_RECORD.md",
            "INSIDER_BUYING_ETF_STRATEGY_BLUEPRINT.pdf",
            "f8834e13bb22d63a1a5a055a24cc2638ecb2e535b733c1fdd1741a28c65db88c",
        ),
        "codex/strategy-short-interest": (
            "SHORT_INTEREST_IMPLEMENTATION_RECORD.md",
            "SHORT_INTEREST_ETF_STRATEGY_BLUEPRINT_EN.pdf",
            "2f7ccff9bcd35810b11350314fd6e47c7c92e24ac35a866addb82ce66645b14c",
        ),
    }
    for branch, (record_name, pdf_name, digest) in lanes.items():
        record = (strategy_dir / record_name).read_text(encoding="utf-8")
        with (strategy_dir / pdf_name).open("rb") as source:
            actual_digest = hashlib.file_digest(source, "sha256").hexdigest()
        assert branch in workflow and branch in handoff and branch in direction
        assert branch in record
        assert actual_digest == digest
        assert actual_digest in record.lower()
        assert "docs/ACTION_PLAN_2026-08-20.md" in record
        assert "docs/SESSION_HANDOFF.md" in record

    for document in (workflow, handoff, action, direction):
        assert "same" in document.lower() and "branch" in document.lower()
    assert "must not edit" in workflow.lower()
    assert "leverage" in workflow.lower()
    assert "neither codex nor claude creates an implementation, review" in workflow.lower()
    assert "counter-review" in workflow.lower()
    # Owner clarification 2026-08-26: the standing three-step lane loop keeps
    # Codex counter-review and combines it with the next bounded milestone.
    for document in (workflow, handoff, direction):
        assert "codex counter-review" in document.lower()
    assert "codex counter-review and next milestone" in workflow.lower()
    assert "standing codex counter-review step" in direction.lower()
    assert "one combined push" in workflow.lower()
    assert "one combined push" in handoff.lower()
    assert "counter-review step is removed" not in workflow.lower()
    assert "there is no codex counter-review step" not in direction.lower()
    assert "review disposition is final" not in handoff.lower()

    archived = ROOT / "docs" / "Archive" / "Plans" / (
        "ANALYST_CONSENSUS_ETF_ROTATION_PLAN_V1.md"
    )
    assert archived.is_file()
    assert "SUPERSEDED" in archived.read_text(encoding="utf-8")
    assert not (ROOT / "docs" / "ANALYST_CONSENSUS_ETF_ROTATION_PLAN.md").exists()


_THREE_STRATEGY_LANES = (
    "codex/strategy-analyst-revisions-v2",
    "codex/strategy-insider-buying",
    "codex/strategy-short-interest",
)


def test_three_strategy_review_exception_preserves_both_branch_topologies() -> None:
    """The later same-lane rule must not erase or inherit the generic default.

    This is intentionally relational. Merely mentioning ``counter-review`` is
    insufficient: all four governing sources must bind the exact three lanes
    to the complete serialized cycle, while AGENTS and the process document
    must continue to state the separate-review-branch default outside it.
    """
    governance = {
        "AGENTS": _root_text("AGENTS.md"),
        "review process": _text(
            "process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md"
        ),
        "project direction": _text("THREE_STRATEGY_PROJECT_DIRECTION.md"),
        "parallel workflow": _text(
            "Strategy Description/THREE_STRATEGY_PARALLEL_WORKFLOW.md"
        ),
    }

    for label in ("AGENTS", "review process"):
        lowered = governance[label].lower()
        assert "generic/legacy acer" in lowered, (
            f"{label} lost the generic/legacy ACER scope of the default"
        )
        assert re.search(r"separate\s+`?user/claude/[^ ]*`?\s+review branch", lowered), (
            f"{label} no longer preserves the generic separate review branch"
        )
        assert "three-strategy" in lowered and "exception" in lowered, (
            f"{label} no longer identifies the later strategy-lane exception"
        )
        assert "lane implementation record" in lowered
        assert "root session handoff" in lowered and "frozen" in lowered, (
            f"{label} still routes per-lane pushes through the frozen root handoff"
        )

    no_extra_branch = re.compile(
        r"(?:no|neither codex nor claude creates an) implementation, review, "
        r"counter-review, checkpoint, or handoff branch",
        re.IGNORECASE,
    )
    for label, document in governance.items():
        lowered = document.lower()
        for branch in _THREE_STRATEGY_LANES:
            assert branch in document, f"{label} omits governed lane {branch}"
        assert "same lane branch" in lowered or "same branch" in lowered, (
            f"{label} no longer binds Claude review to the lane branch"
        )
        assert "counter-reviews every claude commit" in lowered, (
            f"{label} weakens the required Codex counter-review scope"
        )
        assert "accepted or accepted-after-correction" in lowered, (
            f"{label} lost the acceptance gate before the next milestone"
        )
        assert "no owner decision blocks progress" in lowered, (
            f"{label} lost the owner-decision stop gate"
        )
        assert "next bounded" in lowered and "one combined push" in lowered, (
            f"{label} no longer couples counter-review to the next bounded milestone"
        )
        assert no_extra_branch.search(document), (
            f"{label} permits a forbidden per-lane review/checkpoint branch"
        )


def test_one_time_common_remediation_is_narrow_and_non_authorizing() -> None:
    """The temporary synchronization cannot become cross-lane authority.

    Each governing source must preserve both routing directions (shared fixes
    to all lanes, Analyst-only fixes to one lane), withhold acceptance, and
    deny every external/operational authority named by the owner. Deleting one
    half of that relationship or broadening it to future shared work reddens
    this test even if the heading remains.
    """
    governance = {
        "AGENTS": _root_text("AGENTS.md"),
        "review process": _text(
            "process/CODE_REVIEW_AND_SESSION_HANDOFF_PROCESS.md"
        ),
        "project direction": _text("THREE_STRATEGY_PROJECT_DIRECTION.md"),
        "parallel workflow": _text(
            "Strategy Description/THREE_STRATEGY_PARALLEL_WORKFLOW.md"
        ),
    }
    source = "codex/full-review-p1-remediation-20260826"
    analyst_lane = "codex/strategy-analyst-revisions-v2"

    for label, document in governance.items():
        lowered = document.lower()
        assert "one-time common-remediation exception" in lowered, (
            f"{label} no longer scopes the remediation as one-time"
        )
        assert source in document, f"{label} lost the exact remediation source"
        assert re.search(
            r"shared safety fixes.{0,140}synchronized identically to all three",
            lowered,
        ), f"{label} no longer routes identical shared fixes to all three lanes"
        assert re.search(
            r"analyst-specific research-layer fixes.{0,140}synchronized only to\s+"
            + re.escape(f"`{analyst_lane}`"),
            lowered,
        ), f"{label} no longer confines Analyst-specific fixes to Analyst V2"
        assert "must not enter" in lowered, (
            f"{label} lost the explicit prohibition on Analyst code in other lanes"
        )
        assert re.search(r"each (?:target )?lane.{0,90}own .*record", lowered), (
            f"{label} no longer requires a lane-owned synchronization record"
        )
        assert "synchronization is not acceptance" in lowered
        assert "acceptance remains withheld" in lowered
        assert "exact pushed" in lowered and "same lane branch" in lowered
        assert "codex counter-reviews every claude commit" in lowered

        for denied in (
            "provider",
            "outcome",
            "qc",
            "broker",
            "deployment",
            "trading authority",
        ):
            assert re.search(rf"\bno\b[^.;]{{0,180}}\b{denied}\b", lowered), (
                f"{label} no longer explicitly denies remediation {denied!r} authority"
            )

        assert "expires" in lowered, f"{label} made the exception permanent"
        assert (
            "by inference" in lowered or "separate owner decision" in lowered
        ), f"{label} permits later shared work without renewed owner authority"


def test_main_strategy_direction_preserves_integration_and_authority_gates() -> None:
    direction = _text("THREE_STRATEGY_PROJECT_DIRECTION.md")
    action = _text("ACTION_PLAN_2026-08-20.md")
    handoff = _text("SESSION_HANDOFF.md")

    assert "c9dcdb647914acbfcefce187a138f52fcdad0c68" in direction
    for phrase in (
        "three Codex implementation sessions",
        "three Claude review sessions",
        "separate integration milestone",
        "No branch may add leverage",
        "paper-epoch-006",
        "SEP-3 remains frozen and incomplete",
    ):
        assert phrase.lower() in direction.lower()
    assert "daily short-sale volume is not a substitute" in direction.lower()
    assert "THREE_STRATEGY_PROJECT_DIRECTION.md" in action
    assert "THREE_STRATEGY_PROJECT_DIRECTION.md" in handoff


def test_main_strategy_direction_pins_reviewed_parallel_coordination_gates() -> None:
    """Claude's accepted amendments must remain explicit and fail closed."""
    direction = _text("THREE_STRATEGY_PROJECT_DIRECTION.md").lower()

    for phrase in (
        "own clone or worktree",
        "requirements.txt",
        "config.py",
        "ci/tooling configuration",
        "lane-owned modules",
        "one audit, one agent performs it",
        "common-baseline amendment",
        "one shared final-holdout boundary",
        "shared period unconsumed",
        "one selection family",
        "selected from three parallel attempts",
    ):
        assert phrase in direction

    assert "must not tune or rerun that family to make it pass" in direction
    assert "separately preregistered family" in direction
    assert "new owner-authorized permanent look budget" in direction
    assert "cannot retroactively rescue the canonical result" in direction


def test_sep3_freeze_record_pins_the_reviewed_pause_without_authorizing_extraction():
    freeze = _text("architecture/SEP3_FREEZE_STATE_2026-08-25.md")
    separation = _text("PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md")
    action = _text("ACTION_PLAN_2026-08-20.md")
    handoff = _text("SESSION_HANDOFF.md")
    manifest = (ROOT / "architecture" / "sep3_extraction_manifest.json").read_text(
        encoding="utf-8"
    )

    for expected in (
        "FROZEN BY OWNER",
        "80b9a7ed006210d80f89ff798b4f2477cb027f82",
        "441f790535676ff819724bb43713280d5b0b7837",
        "ba915eec55b8cd1e6ae84f9ec4d2bcaf6b8a8e05",
        "5916ffcff7e5d86d5aab3aead0d2aa489cc0fdd87476908e2b94208205921b1e",
        "757 tracked paths",
        "507 trading assistant / 246 strategy research / 4 shared",
        "physical extraction false",
    ):
        assert expected.lower() in freeze.lower()

    assert '"independent_review_status": "accepted"' in manifest
    assert '"physical_extraction_authorized": false' in manifest
    assert "pending independent review" not in separation.lower()
    for document in (separation, action, handoff):
        assert "paused" in document.lower()
        assert "SEP3_FREEZE_STATE_2026-08-25.md" in document


def test_documentation_update_policy_keeps_action_plan_as_reference_index():
    """Owner decision: update relevant records + handoff, without duplication."""
    action = _text("ACTION_PLAN_2026-08-20.md")
    instructions = _root_text("CLAUDE.md")
    agents = _root_text("AGENTS.md")

    for text in (action, instructions, agents):
        lowered = text.lower()
        assert "unrelated documents" in lowered
        assert "concise reference" in lowered
    assert "sequencing index" in instructions.lower()
    assert "docs/session_handoff.md" in instructions.lower()


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
    history = _archived_handoff_text()
    assert "paper-epoch-005" in history
    assert "4de784e" in history
    assert "1cb8abf" in history


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
    "ACTION_PLAN_2026-08-20.md": (
        r"Current (?:development|reviewed) topology.*?`([0-9a-f]{7,40})`"
    ),
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
    It also recognizes the narrow handoff form where one sentence names a
    branch and its commits and the immediately following sentence says that
    same branch currently remains local-only.

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
    sentences = re.split(r"(?<=[.!?])\s+", text)
    found: list[str] = []

    def valid_claims(sentence: str) -> list[re.Match[str]]:
        matches: list[re.Match[str]] = []
        for match in re.finditer(claim, sentence, flags=re.IGNORECASE):
            prefix = sentence[max(0, match.start() - 24) : match.start()]
            suffix = sentence[match.end() : match.end() + 80]
            # "not local-only" and "no longer unmerged" say the opposite
            # of the matched token. Do not turn corrections into findings.
            if re.search(r"\b(?:not|no longer|never)\s+$", prefix, re.IGNORECASE):
                continue
            # A dated description of an earlier branch state is not a claim
            # about its current reachability.
            if re.search(
                r"\bwhen (?:this|the) (?:section|entry|note) was written\b",
                suffix,
                re.IGNORECASE,
            ):
                continue
            matches.append(match)
        return matches

    for index, sentence in enumerate(sentences):
        claims = valid_claims(sentence)
        hashes = list(re.finditer(r"`([0-9a-f]{7,40})`", sentence, re.IGNORECASE))
        for hash_match in hashes:
            if any(
                max(
                    claim_match.start() - hash_match.end(),
                    hash_match.start() - claim_match.end(),
                    0,
                )
                <= 80
                for claim_match in claims
            ):
                value = hash_match.group(1)
                if value not in found:
                    found.append(value)

        # CDR-003b/CDCR-002: the shipped handoff shape named one branch and
        # its commits, then said "The branch remains local-only" in the next
        # sentence. Scope only to that explicit deictic current-state form;
        # whole-paragraph matching conflates unrelated merged/unmerged work.
        if index == 0 or not claims or not re.search(
            r"\b(?:the|this|that) branch\s+(?:remains?|is|are)\b",
            sentence,
            re.IGNORECASE,
        ):
            continue
        prior = sentences[index - 1]
        if not re.search(
            r"\bbranch\s+`(?:codex|user/claude)/[^`]+`",
            prior,
            re.IGNORECASE,
        ):
            continue
        for value in re.findall(r"`([0-9a-f]{7,40})`", prior, re.IGNORECASE):
            if value not in found:
                found.append(value)
    return found


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


def test_unreachability_parser_links_current_branch_claim_to_prior_sentence():
    """CDCR-002. A handoff commonly names the branch and commits first,
    then states the branch's current reachability in the next sentence."""
    text = (
        "The implementation is on branch `codex/example`: commits `2f4e41d`, "
        "`88d517c`, `67877f8`, and `dfefecf`. "
        "The branch remains local-only at this handoff and must not be treated "
        "as reviewed or merged."
    )
    assert set(_repository_commits_claimed_unreachable(text)) == {
        "2f4e41d",
        "88d517c",
        "67877f8",
        "dfefecf",
    }


def test_unreachability_parser_ignores_negated_and_historical_claims():
    """CDCR-002. Wider scope must not turn corrections into new findings."""
    examples = (
        "`2f4e41d` is merged mainline, not local-only.",
        (
            "The work was on branch `codex/example`: commit `2f4e41d`. "
            "That branch was local-only when this section was written; it has "
            "since merged."
        ),
        (
            "Merged branch `codex/complete` contains `2f4e41d`. "
            "A separate branch remains local-only while its review continues."
        ),
    )
    for text in examples:
        assert _repository_commits_claimed_unreachable(text) == [], text


def test_the_capability_audit_authorization_state_agrees_across_documents():
    """CDR2-002. The handoff and the Action Plan must agree on whether the
    capability audit is already authorized.

    The original guard (CDCR-004) pinned one side of this: it required the
    resume block to describe the audit as authorized and FORBADE it from
    asking the owner to authorize one. But the Action Plan -- the sequencing
    authority -- still lists that authorization as an open decision, and its
    scope covers the Massive account, which the freeze never mentions. A test
    that locks in the more permissive reading of an authorization boundary is
    pointed the wrong way for this repository, and it locks it in the place
    hardest to reverse casually.

    Stated as a relationship instead, so it survives either resolution: if the
    Action Plan still lists the audit as a decision the owner must make, the
    resume block must not tell the next agent it is already granted.
    """
    action_plan = _text("ACTION_PLAN_2026-08-20.md")
    handoff = _text("SESSION_HANDOFF.md")
    current_resume = handoff

    pending = re.search(
        r"\*\*Authorize a read-only, zero-outcome capability audit\*\*",
        action_plan,
    )
    granted = re.search(
        r"(?:the\s+)?authorized[^.]{0,60}(?:zero-outcome|read-only)[^.]{0,80}"
        r"(?:QuantConnect|Cloud)[^.]{0,80}capability audit",
        current_resume,
        flags=re.IGNORECASE,
    )
    assert not (pending and granted), (
        "the Action Plan lists the capability audit as an open owner decision "
        "while the resume block calls it already authorized; resolve in one "
        "direction rather than leaving an authorization boundary ambiguous"
    )
    if pending:
        assert re.search(
            r"(?:obtain|get)\s+that\s+authorization|open\s+owner\s+decision",
            current_resume,
            flags=re.IGNORECASE,
        ), "a pending authorization must be visible in the resume block"


def test_separation_milestone_state_agrees_across_active_documents():
    """SEP0CR-001. Review completion must advance every sequencing authority.

    A handoff that sends the next agent to SEP-1 is unsafe when the active
    separation plan and Action Plan still call SEP-0 current or in progress.
    Keep the three current-state declarations aligned so a new session cannot
    legitimately choose two different milestones depending on which required
    document it reads first.

    SEP1R-002: the first version pinned five exact literals, including the
    plan's status line and two section headings. Those are claims that must
    STAY true, which this module's own docstring forbids -- and the cost was
    immediate rather than theoretical: the guard was written in `02d7a9e` and
    had to be edited in `4f4d6c8`, then again, inside the same session,
    because the milestone legitimately advanced. A guard that must be edited
    every time reality moves correctly is enforcing today's state, not
    consistency.

    Stated as a relationship instead, the way the epoch guards already are:
    derive the current milestone id from the separation plan's own status
    line, then require the other two sequencing authorities to name that same
    milestone. It survives SEP-2, SEP-3, and any renaming of the prose.
    """
    separation_plan = _text("PROJECT_SEPARATION_IMPLEMENTATION_PLAN.md")
    action_plan = _text("ACTION_PLAN_2026-08-20.md")
    handoff = _text("SESSION_HANDOFF.md")

    status = re.search(
        r"Status: \*\*(ACTIVE|PAUSED) — (SEP-\d+)\b", separation_plan
    )
    assert status, (
        "the separation plan must declare an ACTIVE or PAUSED SEP-n status "
        "line; fix the document, not this guard"
    )
    lifecycle = status.group(1)
    current = status.group(2)

    # The plan must mark exactly this milestone current, and every earlier one
    # as finished -- not still 'current'.
    assert re.search(rf"### {current} — [^#]*?\(current(?:, paused)?\)", separation_plan), (
        f"{current} is the declared status but no milestone heading marks it current"
    )
    others = {
        milestone
        for milestone in re.findall(
            r"### (SEP-\d+) — [^#]*?\(current(?:, paused)?\)", separation_plan
        )
        if milestone != current
    }
    assert not others, f"more than one milestone marked current: {sorted(others | {current})}"

    # Merely mentioning the milestone anywhere in these long historical
    # records is not enough. SEP1CR-001 found that the resume block still told
    # the next agent to review an already-reviewed branch while this guard was
    # green because "SEP-1" appeared thousands of lines earlier. Require one
    # stable, value-derived marker in each *current* sequencing surface. The
    # marker text stays stable while ``current`` advances, so the test itself
    # does not need a milestone-specific edit.
    current_marker = f"{current} is the current bounded milestone"
    current_action_plan = action_plan.split(
        "**Architecture-track sequencing:**", 1
    )[1].split("**How the two tracks relate", 1)[0]
    assert current_marker in current_action_plan, (
        "the Action Plan does not identify the separation plan's current "
        f"milestone with the canonical marker: {current_marker!r}"
    )

    assert current_marker in handoff
    if lifecycle == "PAUSED":
        for document in (separation_plan, action_plan, handoff):
            assert "paused" in document.lower()
            assert "SEP3_FREEZE_STATE_2026-08-25.md" in document


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

    history = _archived_handoff_text()
    assert "codex/review-buy1-suggestion-picker-20260813" in history
    assert "44a7f85" in history


def test_deleted_gr7d_ref_is_not_called_irrecoverable_while_object_remains():
    """Deleting a branch ref is not the same event as pruning its objects."""
    plan = _text("Plan/THREE_SLEEVE_ENGINE_PLAN.md")
    assert "no longer exists anywhere" not in plan
    assert "85a77291a3a8de88a82b3670dcf05793b6825c1c" in plan
    assert "may disappear during Git pruning" in plan


def test_closed_alpha_plan_distinguishes_valid_null_runs_from_invalid_legacy_runs():
    """A null result is valid evidence of no detected edge, not an invalid run."""
    plan = _text("Alpha_Test_Implementation_Plan.md")
    action_plan = _text("ACTION_PLAN_2026-08-20.md")

    stale_claims = (
        "No historical alpha result in this program is valid",
        "Every historical QuantConnect result in `docs/research/alpha-result.md` remains invalid",
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
    plan = _text("Archive/Plans/STRONGBUY_PORTFOLIO_TEST_PLAN.md")

    assert "remain in the primary P2−P1 series" in plan
    assert "whether those months are excluded" not in plan


def test_strongbuy_amendment_ledger_is_one_contiguous_markdown_table():
    """All amendment rows render under the ledger header instead of as raw pipes."""
    plan = _doc_path("Archive/Plans/STRONGBUY_PORTFOLIO_TEST_PLAN.md").read_text(
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


_SUPERSEDED_STATUS = re.compile(r"Status: \*\*(SUPERSEDED[^*]*)\*\*")


def _superseded_status(name: str) -> str:
    """Return a plan's superseded status, failing loudly if it cannot parse.

    CDR-001. Both lifecycle guards below wrapped their entire body in
    ``if re.search(r"Status: \\*\\*SUPERSEDED", sbp):``. That inverts the guard:
    rewording the status line disarms it silently instead of failing it, which
    is the mirror case of the drift it exists to catch. Mutation-proved on the
    reviewed tree -- replacing ``SUPERSEDED`` with ``RETIRED`` left both tests
    green while every downstream assertion went unrun.

    Parsing once, loudly, keeps the relationship enforced: if the owner ever
    un-supersedes SBP, this fails and the guards are updated deliberately.
    """
    match = _SUPERSEDED_STATUS.search(_text(name))
    assert match, (
        f"{name} no longer declares a SUPERSEDED status. Update these guards "
        "deliberately if that is intended; a reworded status line must never "
        "silently disable them."
    )
    return match.group(1)


def test_a_superseded_program_is_not_also_the_next_owner_decision():
    """A replaced program must not still be advertised as the blocking step.

    2026-08-20: the owner replaced the Strong-Buy program (SBP) with the
    Analyst-Consensus ETF Rotation program. The failure this guards against is
    PARTIAL replacement -- one document marking a plan superseded while the
    action plan still tells the reader its freeze is what happens next.
    """
    _superseded_status("Archive/Plans/STRONGBUY_PORTFOLIO_TEST_PLAN.md")
    action_plan = _text("ACTION_PLAN_2026-08-20.md")
    assert "ACER" in action_plan and "priority 1" in action_plan.lower()
    assert not re.search(
        r"\*\*SBP-0 adoption\*\*[\s\S]{0,300}?only decision blocking",
        action_plan,
    )
    assert (ROOT / "docs" / "Strategy Description" / (
        "ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md"
    )).is_file()
    assert (ROOT / "docs" / "Archive" / "Plans" / (
        "ANALYST_CONSENSUS_ETF_ROTATION_PLAN_V1.md"
    )).is_file()


def test_lifecycle_indexes_do_not_advertise_superseded_sbp_as_actionable():
    """The new lifecycle indexes must route current and superseded plans."""
    _superseded_status("Archive/Plans/STRONGBUY_PORTFOLIO_TEST_PLAN.md")
    queued = _doc_path("Plan/README.md").read_text(encoding="utf-8")
    archived = _doc_path("Archive/README.md").read_text(encoding="utf-8")
    assert "STRONGBUY_PORTFOLIO_TEST_PLAN.md" not in queued
    assert "superseded" in archived.lower()
    assert "ANALYST_CONSENSUS_ETF_ROTATION_PLAN_V1.md" in archived
    assert (ROOT / "docs" / "Strategy Description" / (
        "ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md"
    )).is_file()


def test_archived_open_acer_freeze_is_not_current_or_executable():
    """The superseded V1 freeze remains reproducible but cannot govern V2."""
    freeze = _text("Archive/Research/ACER_V1/ACER_2026-08-20_ACER0A_FREEZE.md")
    reference = _text("Archive/Plans/ANALYST_CONSENSUS_ETF_ROTATION_PLAN_V1.md")
    active = _text("Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md")
    if "Named open items that must close BEFORE the development run" in freeze:
        assert "not yet an executable preregistration" in freeze
        assert "preregistration is INCOMPLETE" in reference
    assert "SUPERSEDED" in freeze
    assert "SUPERSEDED" in reference
    assert "NO V2 SIGNAL" in active


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
    """The archived V1 plan must preserve the durable host measurement."""
    facts = _text("OPERATIONAL_FACTS.md")
    acer = _text("Archive/Plans/ANALYST_CONSENSUS_ETF_ROTATION_PLAN_V1.md")
    if "SBR-1 capture: measured absent" in facts:
        assert "task and artifact state has not been measured" not in acer


def test_v2_acer_identity_docs_do_not_turn_missing_evidence_into_safety():
    """The name-only diagnostic is a lower bound, never an allowlist."""
    measurement = _text(
        "Archive/Research/ACER_V1/ACER_2026-08-21_ISSUER_IDENTITY_MEASUREMENT.md"
    )
    active = _text("Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md")
    handoff = _text("SESSION_HANDOFF.md")

    for document in (measurement, active, handoff):
        assert "768" in document

    assert "BBBY scores *unambiguous*" not in handoff
    assert "allowlist" in measurement.lower()
    assert "lower bound" in measurement.lower()
    assert "current-ticker joins are prohibited" in active.lower()
    assert "security master" in active.lower()


def test_every_active_analyst_summary_pins_identity_and_source_precedence():
    """AR-P3-006: active summaries must carry the complete safety meaning."""
    active_documents = (
        _text("ACTION_PLAN_2026-08-20.md"),
        _text("Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md"),
        _text("SESSION_HANDOFF.md"),
    )
    for document in active_documents:
        lowered = document.lower()
        assert "768" in document
        assert "lower bound" in lowered
        assert "allowlist" in lowered
        assert "current-ticker joins are prohibited" in lowered
        assert "normative strategy design" in lowered
        assert "observed provider" in lowered


def test_analyst_v2_milestones_enforce_stock_first_before_etf_topology():
    """AR-P2-016: milestone presence is insufficient; order is binding."""
    record = _text("Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md")
    stock = record.index("ARV2-4")
    etf = record.index("ARV2-5")
    assert stock < etf
    assert "valid null closes the canonical family" in record.lower()
    assert "only after an arv2-4 pass" in record.lower()


def test_stock_first_direction_and_historical_qc_calls_are_not_denied():
    """AR-P3-007: mandate scope and factual QC history cannot drift backward."""
    mandate = _text("operations/MANDATE.md").lower()
    direction = _text("THREE_STRATEGY_PROJECT_DIRECTION.md").lower()
    readme = _root_text("README.md").lower()
    facts = _text("operations/OPERATIONAL_FACTS.md").lower()
    ledger = _text("research/alpha-result.md")
    assert "stock-first" in mandate and "stock-first" in direction
    assert "grants no execution" in mandate
    assert "R-001" in ledger and "cloud" in ledger.lower()
    for document in (readme, facts):
        assert "historical authenticated research calls" in document
        assert "no live call has ever been made" not in document


def test_acer_completion_proposal_does_not_normalize_away_decay():
    """Half-life cells must attenuate stale events, not only reweight firms."""
    proposal = _text("Archive/Research/ACER_V1/ACER_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md")
    assert "sum(w * notch) / N_live" in proposal
    assert "sum(w * notch) / sum(w)" not in proposal
    assert "age <= 2 * H" in proposal


def test_acer_completion_proposal_defines_a_real_out_of_sample_residual():
    """Validation outcomes cannot fit their own control residualization."""
    proposal = _text("Archive/Research/ACER_V1/ACER_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md")
    assert "training rows only" in proposal
    assert "without refitting on validation outcomes" in proposal
    assert "immediately before each validation block" in proposal
    assert "embargo after the test window" not in proposal


def test_acer_completion_proposal_names_the_existing_bootstrap_contract():
    """The frozen method must match the repository function it delegates to."""
    proposal = _text("Archive/Research/ACER_V1/ACER_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md")
    engine = _root_text("backtest/engine.py")
    assert "circular moving-block bootstrap" in proposal
    assert "stationary block bootstrap" not in proposal
    assert "synthetic null calibration" in proposal
    assert "Uses a circular moving-block bootstrap" in engine


def test_acer_completion_proposal_discloses_every_measured_unmapped_rating():
    """Owner review needs the complete refusal vocabulary, not four examples."""
    proposal = _text("Archive/Research/ACER_V1/ACER_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md")
    for rating in (
        "developing",
        "equalweight",
        "gradually accumulate",
        "hold neutral",
        "performer",
        "sector overweight",
        "sector performer",
        "sector underweight",
        "speculative hold",
        "trading buy",
        "trading sell",
    ):
        assert f"`{rating}`" in proposal


def test_acer_state_semantics_measurement_does_not_overclaim_raw_keys():
    """A pre-identity raw-ticker scan cannot be called same-issuer evidence."""
    proposal = _text("Archive/Research/ACER_V1/ACER_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md")
    counterreview = _text(
        "Archive/Review/REVIEW_2026-08-21_ACER_PREREG_COUNTERREVIEW.md"
    )

    for document in (proposal, counterreview):
        assert "raw ticker" in document.lower()
        assert "raw firm" in document.lower()
        assert "not decision-grade" in document.lower()

    assert "exact NYSE trading sessions" in proposal
    assert "7.1%" not in proposal
    assert "32.2%" not in proposal


def test_acer_local_capability_audit_includes_existing_databento_path():
    """Repository capability cannot be inferred from the production reader alone."""
    audit = _text("Archive/Research/ACER_V1/ACER_2026-08-21_LOCAL_DATA_CAPABILITY_AUDIT.md")
    source = _root_text("ml/databento_source.py")
    pit = _root_text("ml/databento_pit.py")
    authority = _root_text("ml/databento_authoritative.py")

    assert "EQUS.SUMMARY" in source
    assert "security_master" in pit
    assert "build_authoritative_feature_batch" in authority
    for path in (
        "ml/databento_source.py",
        "ml/databento_pit.py",
        "ml/databento_authoritative.py",
    ):
        assert f"`{path}`" in audit
    assert "unmeasured candidate" in audit.lower()
    assert "sole local price provider" not in audit.lower()
    assert "magnitude and direction" in audit
    assert "are unresolved" in audit


def test_v2_plan_does_not_promote_an_unaudited_price_route():
    """Archived provider evidence must remain a blocker, never a V2 solution."""
    audit = _text("Archive/Research/ACER_V1/ACER_2026-08-21_LOCAL_DATA_CAPABILITY_AUDIT.md")
    active = _text("Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md")
    register = _text("Strategy Description/THREE_STRATEGY_DATA_SOURCE_REGISTER.md")

    assert "EDGAR/yfinance path" in audit
    assert "Databento" in audit
    assert "repository-wide local feasibility remains unresolved" in audit.lower()
    assert "Databento remains unmeasured" in active
    assert "delistings/terminal returns" in register


def test_active_strategy_docs_require_exact_vendor_to_qc_processing_rights():
    """A subscription is not permission to move arbitrary rows into QC."""
    workflow = _text("Strategy Description/THREE_STRATEGY_PARALLEL_WORKFLOW.md")
    analyst = _text("Strategy Description/ANALYST_REVISIONS_IMPLEMENTATION_RECORD.md")
    register = _text("Strategy Description/THREE_STRATEGY_DATA_SOURCE_REGISTER.md")
    handoff = _text("SESSION_HANDOFF.md")

    for document in (workflow, analyst, register, handoff):
        lowered = document.lower()
        assert "quantconnect" in lowered or "qc" in lowered
        assert "permission" in lowered or "rights" in lowered
    assert "subscription name" in register.lower()
    assert "not evidence" in register.lower()
    assert "raw, normalized, or derived" in register.lower()


# SEP2F-002. A review's own two records must agree on what it found.
#
# Twice in consecutive rounds a finding was added to a review report after its
# verdict line was written, and the corresponding SESSION_HANDOFF section kept
# the earlier count: SEP2L-002 and SEP2D-002 were each in the archived report's
# ledger and absent from the handoff's summary. Codex caught both. Writing the
# resolution down did not prevent the repeat, so this asserts the relationship
# instead: every finding ID a SEP-2 review report raises must appear somewhere
# in the current handoff.
#
# Scoped to the separation milestone's review reports, whose handoff sections
# are current. Archived rounds are historical records and are never retro-edited.
#
# SEP2F-004: this was originally globbed on the literal
# "REVIEW_2026-08-22_SEP2_*.md". The day SEP-3 became the current milestone the
# guard would have kept passing while silently covering nothing current -- a
# guard that quietly narrows to history is the vacuous-check failure this
# module exists to prevent. The glob follows the milestone instead of a date.
# SEP3AR-001: counter-review records escaped these globs — "COUNTER_REVIEW_*"
# does not start with "REVIEW_", so a CRSEP finding raised only in a
# counter-review could vanish from the current handoff without failing
# anything. Same risk class as SEP2F-002; measured green across all nine
# existing counter-review files before extending.
_SEPARATION_REVIEW_GLOBS = (
    "REVIEW_*_SEP2_*.md",
    "REVIEW_*_SEP3_*.md",
    "COUNTER_REVIEW_*_SEP2_*.md",
    "COUNTER_REVIEW_*_SEP3_*.md",
)
# CRSEP3R-001: one optional letter recognized SEP3X-001 but silently ignored
# multi-part round identifiers such as SEP3CR-001 and SEP3CR2-002. Those forms
# already occur in adjacent separation review chains, so the guard must parse
# the complete milestone-local suffix rather than the one example it mutated.
_FINDING_ID = re.compile(r"\b(?:CR)?SEP[23][A-Z0-9]*-\d{3}\b")


def test_separation_finding_id_pattern_accepts_multi_part_round_ids():
    assert _FINDING_ID.fullmatch("SEP2F-004")
    assert _FINDING_ID.fullmatch("SEP3CR-001")
    assert _FINDING_ID.fullmatch("SEP3CR2-002")
    assert _FINDING_ID.fullmatch("CRSEP3R2-001")


def _separation_review_reports() -> list[Path]:
    review_dir = ROOT / "docs" / "Archive" / "Review"
    found: set[Path] = set()
    for pattern in _SEPARATION_REVIEW_GLOBS:
        found.update(review_dir.glob(pattern))
    return sorted(found)


def test_separation_review_reports_exist_so_this_guard_cannot_pass_vacuously():
    assert _separation_review_reports(), (
        "no separation review report found; the guard would be vacuous"
    )


def test_every_separation_review_finding_appears_in_the_current_handoff():
    handoff = _text("SESSION_HANDOFF.md")
    missing: dict[str, list[str]] = {}
    for report in _separation_review_reports():
        ids = {
            match
            for match in _FINDING_ID.findall(report.read_text(encoding="utf-8"))
        }
        absent = sorted(one for one in ids if one not in handoff)
        if absent:
            missing[report.name] = absent
    assert missing == {}, (
        "a separation review report raises findings the current handoff never "
        f"mentions: {missing!r}"
    )
