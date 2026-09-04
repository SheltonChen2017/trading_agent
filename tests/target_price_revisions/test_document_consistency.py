"""Target-owned documentation guards for the Target-Price Revisions lane."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
import subprocess

import pytest
from pathlib import Path

from research.target_price_revisions import PRIMARY_CELL_ID, PRIMARY_LOOK_ID
from research.target_price_revisions.preregistration import (
    POLICY_CODE_REPO_PATHS,
    load_algorithm_candidate,
)


ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = ROOT / "docs" / "Strategy Description"
LANE_BRANCH = "codex/strategy-target-price-revisions"
BLUEPRINT = "TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf"
RECORD = "TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md"
LANE_BRANCH_REF = "refs/heads/" + LANE_BRANCH
WORKTREE_RESOLUTION = "git worktree list"
SPEC_PATH = (
    ROOT / "research" / "target_price_revisions" / "specs"
    / "tpr_round0a.candidate.json"
)
BLUEPRINT_CONTENT_SHA256 = (
    "f6e98eef0dd5d54a0deb45718d64b00a8e9b0c3d211ffbe0edebdb4e80eec30b"
)
MALFORMED_SUBMITTED_SOURCE_PIN = (
    "53c549aef18aa1a63e6db8deb184bd654eb8ec637bb4ff3ae03f29abc4a2df0"
)
CANDIDATE_RELATIVE = Path(
    "research/target_price_revisions/specs/tpr_round0a.candidate.json"
)
EXPECTED_CANDIDATE_ID = "tpr-round0a-candidate-74b096af24c8d481"
EXPECTED_CANDIDATE_HASH = (
    "74b096af24c8d48196054f56deb562924380884c1b14b747ba432cc57658df2c"
)
EXPECTED_CANDIDATE_ARTIFACT_SHA256 = (
    "17a2a902060031ee9680c7d07f6102b0da47b0b593a2c89569d782023942650a"
)
# Convention, clarified TPR-CR6-002: each role's pointer names the other
# role's completed commits. A round cannot name its own final commit -- that
# hash does not exist until the commit is written -- so a Codex counter-review
# pins the exact Claude range it just reviewed.
LATEST_COUNTERREVIEWED_CLAUDE_BASE = (
    "5f98c3aa757f420efac13f682f4e210fa9688e5b"
)
LATEST_COUNTERREVIEWED_CLAUDE_HEAD = (
    "1981233424f25b48ebec2273fa4822c249e2a041"
)
LATEST_COUNTERREVIEWED_CLAUDE_RANGE = (
    f"{LATEST_COUNTERREVIEWED_CLAUDE_BASE}.."
    f"{LATEST_COUNTERREVIEWED_CLAUDE_HEAD}"
)
LATEST_COUNTERREVIEWED_CLAUDE_SHORT_RANGE = "5f98c3aa..19812334"
LATEST_CLAUDE_REVIEWED_CODEX_RANGE = (
    "25c1c378448bf41a60c31a81e11ca398354c36d0.."
    "5f98c3aa757f420efac13f682f4e210fa9688e5b"
)
LATEST_COUNTERREVIEWED_CLAUDE_COMMITS = (
    "26a4fc6fb85af492ef34a3f5a93b84b9f037a665",
    "34aa8eda2432d05a6a955fe3dbf4cf9a3fd98724",
    "1981233424f25b48ebec2273fa4822c249e2a041",
)
# A Claude round cannot pin its own head either, so it pins the Codex range
# it just reviewed and routes the counter-review that follows it.
LATEST_REVIEWED_CODEX_BASE = (
    "1981233424f25b48ebec2273fa4822c249e2a041"
)
LATEST_REVIEWED_CODEX_HEAD = (
    "49caa886a63c4a24b6be0a4d8dbd71d9d95e9ad3"
)
LATEST_REVIEWED_CODEX_RANGE = (
    f"{LATEST_REVIEWED_CODEX_BASE}.."
    f"{LATEST_REVIEWED_CODEX_HEAD}"
)
LATEST_REVIEWED_CODEX_SHORT_RANGE = "19812334..49caa886"
LATEST_REVIEWED_CODEX_COMMITS = (
    "7f55652403660b8fa8e8c5d57bd7b4669032a3c8",
    "49caa886a63c4a24b6be0a4d8dbd71d9d95e9ad3",
)
# The superseded pointer token that must no longer appear in current blocks.
PREVIOUS_COUNTERREVIEWED_CLAUDE_HEAD = (
    "5f98c3aa757f420efac13f682f4e210fa9688e5b"
)
PREVIOUS_COUNTERREVIEWED_CLAUDE_SHORT_HEAD = "5f98c3aa"
EXPECTED_POLICY_CODE_REPO_PATHS = (
    "research/__init__.py",
    "research/target_price_revisions/__init__.py",
    "research/target_price_revisions/canonical.py",
    "research/target_price_revisions/import_firewall.py",
    "research/target_price_revisions/preregistration.py",
    "research/target_price_revisions/trust_root.py",
    "research/target_price_revisions/windows_acl.py",
    "research/target_price_revisions/specs/.gitattributes",
)


def _doc(name: str) -> str:
    return (ROOT / "docs" / name).read_text(encoding="utf-8")


def _bounded(text: str, start: str, end: str, name: str) -> str:
    """Return one explicitly bounded block and fail if either anchor is absent."""
    if text.count(start) != 1:
        raise AssertionError(f"{name} must contain exactly one opening anchor")
    tail = text.partition(start)[2]
    if end not in tail:
        raise AssertionError(f"{name} is missing its closing anchor")
    return tail.partition(end)[0]


def _action_current() -> str:
    return _bounded(
        _doc("ACTION_PLAN_2026-08-20.md"),
        "**Current bounded status,",
        "**Owner multiplicity amendment, 2026-08-30",
        "Action Plan current target block",
    )


def _action_tpr_row() -> str:
    return next(
        line
        for line in _doc("ACTION_PLAN_2026-08-20.md").splitlines()
        if line.startswith("| Target-Price Revisions (TPR) |")
    )


def _handoff_current() -> str:
    return _bounded(
        _doc("SESSION_HANDOFF.md"),
        "## 0. Target-Price Revision fourth-lane planning addition",
        "\n## ",
        "Session Handoff target section",
    )


def _handoff_current_review() -> str:
    section = _handoff_current()
    return _bounded(
        section,
        "- **Current review state,",
        "\n- ",
        "Session Handoff current review bullet",
    )


def _handoff_target_summary() -> str:
    return _bounded(
        _doc("SESSION_HANDOFF.md"),
        "### Target-Price Revisions",
        "\n## ",
        "Session Handoff target summary",
    )


def _record_preamble() -> str:
    record = _doc(f"Strategy Description/{RECORD}")
    return record[: record.index("## 1. Decision and canonical strategy boundary")]


def test_blueprint_is_pinned_to_the_lane_record() -> None:
    """Bind the exact binary PDF content to the lane record."""
    record = (STRATEGY_DIR / RECORD).read_text(encoding="utf-8")
    raw = (STRATEGY_DIR / BLUEPRINT).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()

    assert digest == BLUEPRINT_CONTENT_SHA256
    assert digest in record.lower()
    assert "Governing plan page count: **29**." in record
    assert LANE_BRANCH in record
    assert "docs/ACTION_PLAN_2026-08-20.md" in record
    assert "docs/SESSION_HANDOFF.md" in record
    for name in ("ACTION_PLAN_2026-08-20.md", "SESSION_HANDOFF.md"):
        assert LANE_BRANCH in _doc(name)


def test_blueprint_resolves_as_binary_in_git() -> None:
    """TPR-CR1-001: prevent checkout filters from rewriting the PDF."""
    relative = f"docs/Strategy Description/{BLUEPRINT}"
    completed = subprocess.run(
        ["git", "check-attr", "binary", "diff", "merge", "text", "--", relative],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    resolved = {
        line.rsplit(": ", 2)[-2]: line.rsplit(": ", 1)[-1]
        for line in completed.stdout.splitlines()
    }

    assert resolved == {
        "binary": "set",
        "diff": "unset",
        "merge": "unset",
        "text": "unset",
    }


SHARED_POLICY_PATH = "research/__init__.py"


def test_policy_code_is_checked_out_as_exact_bytes() -> None:
    """TPR-CR4-001/TPR-CCR5-001: keep the anchor exact on Windows.

    `_review_anchor` compares every `POLICY_CODE_REPO_PATHS` entry's working
    bytes against its committed blob.  The inventory here is intentionally
    independent of the runtime tuple so a path cannot disappear from both the
    loader and this guard in one edit.  Direct blob comparison catches every
    byte difference, not only CRLF translation.  Lane text is normalized to
    LF on checkout and add; the tracked migration markers force ordinary
    fast-forwards from the defective tree to rewrite the five nonempty files.

    `research/__init__.py` is shared surface outside this lane's attribute
    scope, so it is covered only while it stays empty.  This guard turns red
    rather than passing silently if that stops being true.
    """
    assert POLICY_CODE_REPO_PATHS == EXPECTED_POLICY_CODE_REPO_PATHS
    for policy_path in EXPECTED_POLICY_CODE_REPO_PATHS:
        working = (ROOT / policy_path).read_bytes()
        committed = subprocess.run(
            ["git", "show", f"HEAD:{policy_path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        assert working == committed, (
            f"{policy_path} differs from its HEAD blob, so the reviewed-"
            "algorithm anchor cannot accept this checkout"
        )
        if policy_path == SHARED_POLICY_PATH:
            assert working == b"", (
                f"{policy_path} is outside this lane's attribute scope and is "
                f"safe only while empty; route a shared .gitattributes change "
                f"to the owner before giving it content"
            )
            continue
        completed = subprocess.run(
            ["git", "check-attr", "text", "eol", "--", policy_path],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        resolved = {
            line.rsplit(": ", 2)[-2]: line.rsplit(": ", 1)[-1]
            for line in completed.stdout.splitlines()
        }
        assert resolved == {"text": "set", "eol": "lf"}, (
            f"{policy_path} must normalize to LF on checkout and add; got "
            f"{resolved}"
        )


def _git_lines(*args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.splitlines()


def _registered_lane_worktree() -> Path | None:
    """Return the worktree Git registers for the lane branch, or None."""
    path: str | None = None
    for line in _git_lines("worktree", "list", "--porcelain"):
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line.strip() == "branch " + LANE_BRANCH_REF and path is not None:
            return Path(path)
    return None


def test_lane_documents_resolve_the_worktree_from_git() -> None:
    """TPR-CR4-002, superseding TPR-CR1-005 and TPR-CR2-003.

    The lane is developed from more than one host, so pinning one absolute
    directory made the resume instruction wrong everywhere except the host
    that wrote it, and this guard previously enforced that wrong name.  The
    owner directed that the worktree be resolved from `git worktree list`
    instead.

    So the invariant is machine-independent and target-scoped: each current
    target block must carry the resolution instruction and pin no directory
    name, while sibling-lane text elsewhere in shared documents remains out of
    this guard's scope.  The instruction must actually resolve when this
    checkout is on the lane branch.
    """
    current_surfaces = {
        "ACTION_PLAN_2026-08-20.md target block": _action_current(),
        "SESSION_HANDOFF.md target section": _handoff_current(),
        f"Strategy Description/{RECORD} preamble": _record_preamble(),
    }
    for name, content in current_surfaces.items():
        assert WORKTREE_RESOLUTION in content, (
            f"{name} must tell the reader to resolve the lane worktree with "
            f"`{WORKTREE_RESOLUTION}` instead of naming a directory"
        )

    for name, content in current_surfaces.items():
        directories = set(re.findall(r"trading_agent_[A-Za-z0-9_]+", content))
        assert not directories, (
            f"{name} pins a machine-specific lane worktree {sorted(directories)}; "
            f"resolve it with `{WORKTREE_RESOLUTION}` instead"
        )

    # The instruction has to work, not merely be written down.  A detached
    # historical clone may have no registered lane branch, but an active lane
    # checkout must always resolve itself.
    on_lane = _git_lines("rev-parse", "--abbrev-ref", "HEAD") == [LANE_BRANCH]
    registered = _registered_lane_worktree()
    if on_lane:
        assert registered is not None, (
            f"this checkout is on {LANE_BRANCH}, but `{WORKTREE_RESOLUTION}` "
            "does not register that branch"
        )
    if registered is None:
        return
    assert registered.is_dir(), (
        f"`{WORKTREE_RESOLUTION}` registers {registered} for {LANE_BRANCH}, "
        f"but that directory does not exist"
    )
    if on_lane:
        assert registered.resolve() == ROOT.resolve(), (
            f"this checkout is on {LANE_BRANCH} but Git registers the lane "
            f"worktree at {registered}, not {ROOT}"
        )


def test_target_documents_do_not_present_the_malformed_source_pin_as_valid() -> None:
    """TPR-CR1-004: retire the unavailable proposal as a gate or authority."""
    record = (STRATEGY_DIR / RECORD).read_text(encoding="utf-8")
    handoff = _doc("SESSION_HANDOFF.md")
    normalized_record = " ".join(record.lower().split())
    normalized_handoff = " ".join(handoff.lower().split())

    assert MALFORMED_SUBMITTED_SOURCE_PIN not in record.lower()
    assert MALFORMED_SUBMITTED_SOURCE_PIN not in handoff.lower()
    assert "historical, and non-authoritative" in normalized_record
    assert "63 hexadecimal characters" in record
    assert "63-character value is historical evidence" in normalized_handoff
    for document in (normalized_record, normalized_handoff):
        assert "sole normative" in document
        assert "cannot satisfy or block" in document
        assert "until the owner re-supplies" not in document


def test_tpr0a_candidate_identity_and_zero_authority_handoff_are_exact() -> None:
    """Bind current TPR-0A bytes, inventory, and handoff status to target docs."""
    candidate_path = ROOT / CANDIDATE_RELATIVE
    payload = candidate_path.read_bytes()
    raw = json.loads(payload)
    candidate = load_algorithm_candidate(candidate_path)
    cells = {cell["cell_id"]: cell["value"] for cell in raw["cells"]}
    empirical = cells["empirical_binding_contract"]["required_bindings"]

    assert raw["spec_id"] == candidate.spec_id == EXPECTED_CANDIDATE_ID
    assert raw["spec_hash"] == candidate.spec_hash == EXPECTED_CANDIDATE_HASH
    assert (
        hashlib.sha256(payload).hexdigest()
        == EXPECTED_CANDIDATE_ARTIFACT_SHA256
    )
    assert len(raw["cells"]) == 24
    assert len(empirical) == 39
    assert all(value is None for value in empirical.values())
    assert len(candidate.pending_bindings) == 48
    assert len(raw["looks"]) == 1
    look = raw["looks"][0]
    assert look["state"] == "planned_unbound"
    for field in (
        "dataset_id",
        "code_identity",
        "structural_binding_id",
        "structural_binding_sha256",
    ):
        assert look[field] is None

    for authority_name in (
        "research_source_authority.json",
        "permanent_look_authority.json",
    ):
        authority = json.loads(
            (candidate_path.parent / authority_name).read_bytes()
        )
        assert authority["authority_mode"] == "zero_access"
        assert authority["entries"] == []
    registry = json.loads(
        (candidate_path.parent / "reviewed_spec_registry.json").read_bytes()
    )
    assert registry["schema"] == "tpr-reviewed-algorithm-registry-v2"
    assert registry["signature_policy"] == {
        "allowed_signers_path_id": (
            "windows-programdata-customizedagent-trust-tpr-allowed-signers-v1"
        ),
        "format": "ssh",
        "key_type": "ssh-ed25519",
        "namespace": "git",
        "principal": "shelton-tpr-reviewer",
    }
    assert registry["entries"] == []

    record = (STRATEGY_DIR / RECORD).read_text(encoding="utf-8").lower()
    handoff = _doc("SESSION_HANDOFF.md").lower()
    for document in (record, handoff):
        assert EXPECTED_CANDIDATE_ID in document
        assert EXPECTED_CANDIDATE_HASH in document
        assert EXPECTED_CANDIDATE_ARTIFACT_SHA256 in document
        assert "39 null empirical" in document
        assert "48 total pending" in document
        assert "planned_unbound" in document
        assert "no look is authorized or spent" in document
        assert "reviewed-spec registry remains empty" in document
        assert "candidate remains unreviewed for its own registry" in document


def test_shared_family_alpha_allocation_is_exact_and_unrecycled() -> None:
    """Bind the document-level guard to the authenticated v2.2 candidate.

    The four named slots remain fixed even if a lane is unused or withdrawn;
    its 1/80 expires rather than being recomputed or redistributed.  Explicit
    per-cell/look allocations make the within-lane ceiling summable instead of
    inferring it from inventory length.
    """
    candidate = load_algorithm_candidate(SPEC_PATH)
    multiplicity = candidate.cell("family_multiplicity")

    family_count = multiplicity["shared_family_count"]
    shared = Decimal(multiplicity["shared_family_wise_alpha"])
    assigned = Decimal(multiplicity["assigned_family_alpha"])
    ceiling = Decimal(multiplicity["within_lane_confirmatory_alpha_ceiling"])
    allocations = multiplicity["confirmatory_alpha_allocations"]

    assert multiplicity["fixed_lane_ids"] == (
        "analyst-revisions-v2",
        "insider-buying",
        "short-interest",
        "target-price-revisions",
    )
    assert multiplicity["assigned_lane_id"] == "target-price-revisions"
    assert family_count == 4, "the shared selection family has four attempts"
    assert shared == Decimal("0.05"), "total two-sided FWER is 0.05"
    assert assigned * family_count == shared, (
        f"fixed-slot equal allocation requires {assigned} x {family_count} "
        f"== {shared}; unused alpha may not be redistributed"
    )
    assert assigned == ceiling == Decimal("0.0125")
    assert multiplicity["slot_reallocation"] == {
        "transferable": False,
        "unused": "EXPIRES",
        "withdrawn": "EXPIRES",
        "redistribution": "PROHIBITED",
    }

    allocated = sum(
        (Decimal(entry["two_sided_alpha"]) for entry in allocations),
        start=Decimal("0"),
    )
    assert allocated <= ceiling
    assert allocated == assigned
    assert tuple(entry["look_id"] for entry in allocations) == (
        PRIMARY_LOOK_ID,
    )
    assert tuple(entry["primary_cell_id"] for entry in allocations) == (
        PRIMARY_CELL_ID,
    )
    assert multiplicity["look_budget"] == len(allocations) == 1
    assert multiplicity["external_append_only_authority_required"] is True


def _record_section(heading: str) -> str:
    """The text of one numbered record section, up to the next `## ` heading."""
    text = (STRATEGY_DIR / RECORD).read_text(encoding="utf-8")
    start = text.index(heading)
    nxt = text.find("\n## ", start + len(heading))
    return text[start:] if nxt == -1 else text[start:nxt]


def _current_qualification(section: str) -> str:
    """Return only section 8's explicitly current block, not its history."""
    start = section.index("**Current qualification,")
    end = section.index("\n### Historical progression", start)
    return section[start:end]


def _current_integration_state(section: str) -> str:
    """Return section 8's current topology block, including both hard anchors."""
    return _bounded(
        section,
        "**Integration state, 2026-08-31.**",
        # Date-independent: this heading carries the review date and moved
        # every round, so pinning it re-broke the extractor each time. The
        # opening anchor keeps its date because it names a fixed merge event.
        "**Current qualification,",
        "record current integration state",
    )


@pytest.mark.parametrize("missing", ["opening", "closing"])
def test_current_document_extractors_fail_closed_on_missing_anchor(missing: str) -> None:
    """TPR-CCR7-003: an absent boundary cannot silently widen a current block."""
    text = "before <start> current <end> after"
    if missing == "opening":
        text = text.replace("<start>", "")
    else:
        text = text.replace("<end>", "")
    with pytest.raises(AssertionError):
        _bounded(text, "<start>", "<end>", "probe")


def test_exact_next_step_names_the_current_artifacts() -> None:
    """TPR-CCR4-001/002: bind exact current identities and resume state.

    Exact labeled-value sets reject a stale candidate that coexists with the
    current one, while the explicit block boundary lets section 8 retain its
    clearly marked historical progression.
    """
    section = _record_section("## 8. Exact next step")
    current = _current_qualification(section)
    normalized_current = " ".join(current.split())

    assert re.findall(
        r"raw SHA-256\s+`([0-9a-f]{64})`", current, flags=re.IGNORECASE
    ) == [BLUEPRINT_CONTENT_SHA256], (
        "the current block must name exactly one current blueprint digest"
    )
    assert re.findall(
        r"spec ID\s+`(tpr-round0a-candidate-[0-9a-f]{16})`",
        current,
        flags=re.IGNORECASE,
    ) == [EXPECTED_CANDIDATE_ID], (
        "the current block must name exactly one current candidate spec id"
    )
    assert re.findall(
        r"semantic hash\s+`([0-9a-f]{64})`", current, flags=re.IGNORECASE
    ) == [EXPECTED_CANDIDATE_HASH], (
        "the current block must name exactly one current candidate semantic hash"
    )
    assert re.findall(
        r"artifact SHA-256\s+`([0-9a-f]{64})`",
        current,
        flags=re.IGNORECASE,
    ) == [EXPECTED_CANDIDATE_ARTIFACT_SHA256], (
        "the current block must name exactly one current candidate artifact digest"
    )
    assert "29-page v2.2" in normalized_current
    assert re.findall(
        r"`([0-9a-f]{40}\.{2}[0-9a-f]{40})`", normalized_current
    ) == [LATEST_REVIEWED_CODEX_RANGE]
    assert PREVIOUS_COUNTERREVIEWED_CLAUDE_HEAD not in normalized_current
    assert PREVIOUS_COUNTERREVIEWED_CLAUDE_SHORT_HEAD not in normalized_current
    assert (
        "Claude has independently reviewed Codex's exact two-commit range"
        in normalized_current
    )
    assert (
        "the non-authorizing tpr-tr0-i implementation candidate is checkpointed but remains incomplete"
        in normalized_current.lower()
    )
    assert "no key provisioning or positive authority is authorized" in (
        normalized_current.lower()
    )
    assert "TPR-TR0" in normalized_current
    assert "TPR-1 remains blocked" in normalized_current
    assert "reviewed-spec registry remains empty" in normalized_current
    assert "pending Claude review of this Codex round" not in normalized_current
    assert "comprehensive whole-lane audit is complete" in normalized_current.lower()
    assert "beginning after `49caa886`" in normalized_current

    routing_row = next(
        line
        for line in _record_section("## 9. Out-of-lane findings ledger").splitlines()
        if "`TPR-OOL-001-R1`" in line
    )
    assert "29-page v2.2" in routing_row
    assert BLUEPRINT_CONTENT_SHA256 in routing_row.lower()

    # The shared Session Handoff is frozen for lanes (owner direction
    # 2026-09-04); the lane's current pointers live in this record and the
    # Action Plan target block only.
    for current_pointer in (_action_current(),):
        normalized_pointer = " ".join(current_pointer.split())
        assert re.findall(
            r"`([0-9a-f]{40}\.{2}[0-9a-f]{40})`", normalized_pointer
        ) == [LATEST_REVIEWED_CODEX_RANGE]
        assert PREVIOUS_COUNTERREVIEWED_CLAUDE_HEAD not in normalized_pointer
        assert PREVIOUS_COUNTERREVIEWED_CLAUDE_SHORT_HEAD not in normalized_pointer
        assert (
            "Claude has independently reviewed Codex's exact two-commit range"
            in normalized_pointer
        )
        assert (
            "the non-authorizing tpr-tr0-i implementation candidate is checkpointed but remains incomplete"
            in normalized_pointer.lower()
        )
        assert "no key provisioning or positive authority is authorized" in (
            normalized_pointer.lower()
        )
        assert "TPR-TR0" in normalized_pointer
        assert "comprehensive whole-lane audit is complete" in normalized_pointer.lower()
        assert "beginning after `49caa886`" in normalized_pointer
        normalized_pointer_lower = normalized_pointer.lower()
        stale_current_claims = (
            "pending claude review of this codex round",
            "receive one last narrow identity/document guard run",
            "before commit and the single push",
            "after this counter-review correction round's single push",
            "after this counter-review round's single push",
            "claude has independently reviewed codex's exact three-commit range",
            "beginning after `25c1c378`",
            "codex has counter-reviewed claude's exact three-commit range",
            "beginning after `19812334`",
        )
        for stale_claim in stale_current_claims:
            assert stale_claim not in normalized_pointer_lower

    for summary_pointer in (
        _record_preamble(),
        _action_tpr_row(),
        # the shared handoff summary is frozen for lanes (owner direction 2026-09-04)
    ):
        normalized_summary = " ".join(summary_pointer.split())
        normalized_summary_lower = normalized_summary.lower()
        assert re.findall(
            r"`([0-9a-f]{8}\.{2}[0-9a-f]{8})`", normalized_summary
        ) == [LATEST_REVIEWED_CODEX_SHORT_RANGE]
        assert PREVIOUS_COUNTERREVIEWED_CLAUDE_SHORT_HEAD not in normalized_summary
        assert "claude reviewed both codex commits" in normalized_summary_lower
        assert "section 38" in normalized_summary_lower
        assert (
            "the non-authorizing tpr-tr0-i implementation candidate is checkpointed but remains incomplete"
            in normalized_summary_lower
        )
        assert "no key provisioning or positive authority is authorized" in normalized_summary_lower
        assert "comprehensive claude whole-lane audit is complete" in normalized_summary_lower


def test_latest_counterreview_records_the_exact_claude_output() -> None:
    """TPR-CCR12-001/002: preserve the exact multi-host review handoff."""
    section = _record_section(
        "## 37. Codex counter-review of Claude's TPR-TR0-I checkpoint review"
    )
    assert LATEST_CLAUDE_REVIEWED_CODEX_RANGE in section
    assert LATEST_COUNTERREVIEWED_CLAUDE_RANGE in section
    ordered_commits = tuple(
        re.search(r"`([0-9a-f]{40})`", line).group(1)
        for line in section.splitlines()
        if line.startswith("| Claude commit ")
    )
    assert ordered_commits == LATEST_COUNTERREVIEWED_CLAUDE_COMMITS
    assert "Cumulative disposition: accepted after correction" in section
    assert "No next implementation milestone is authorized" in section


def test_out_of_lane_ledger_has_unique_well_formed_ids() -> None:
    """TPR-CCR8-003/004: keep the owner-routing ledger unambiguous."""
    section = _record_section("## 9. Out-of-lane findings ledger")
    rows = [
        line
        for line in section.splitlines()
        if line.startswith("| `TPR-OOL-")
    ]
    assert rows
    for row in rows:
        assert row.count("|") == 6, (
            "each out-of-lane ledger row must have exactly five columns: "
            f"{row}"
        )
    identifiers = [row.split("|")[1].strip().strip("`") for row in rows]
    assert len(identifiers) == len(set(identifiers)), (
        "out-of-lane ledger identifiers must be unique"
    )
    for identifier in identifiers:
        assert re.fullmatch(r"TPR-OOL-\d{3}(?:-R\d+)?", identifier), (
            f"malformed out-of-lane identifier: {identifier}"
        )
    assert "TPR-OOL-009" in identifiers
    assert "TPR-OOL-009-C" not in _doc(
        "Strategy Description/TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md"
    )


def test_closed_cr7_findings_are_not_described_as_current_residuals() -> None:
    """TPR-CCR8-005: a closed design finding is not an open blocker."""
    section = _record_section(
        "## 26. Claude independent review - 2026-09-01 "
        "(TPR-TR0 trust-root design freeze)"
    )
    assert "The residual is exactly `TPR-CR7-001`" not in section


def test_current_state_blocks_do_not_call_the_lane_unmerged() -> None:
    """TPR-CR5-001/TPR-CCR6-002/004: keep current routing truthful.

    "Deliberately unmerged" was true when the propagation routing was written
    and is now false, so it is exactly the shape this module's docstring calls
    durable: a phrase that should never be true again in current state. Merge
    visibility does not supersede the owner's per-lane branch/review rule.

    Scoped to the current-state surfaces only. Historical sections keep their
    original wording under an explicit supersession note, which is how this
    record retains evidence without misrouting the next role.
    """
    record = (STRATEGY_DIR / RECORD).read_text(encoding="utf-8")
    stale = "deliberately unmerged"
    branch_rule = (
        "sibling-lane changes and their independent reviews remain on their "
        "respective branches"
    )
    unauthorized_routing = (
        "one coordinated change instead of four isolated branch rounds"
    )

    preamble = record[: record.index("\n## 1.")]
    next_step = _current_qualification(_record_section("## 8. Exact next step"))
    current_surfaces = {
        "record preamble": preamble,
        "record section 8 current qualification": next_step,
        # SESSION_HANDOFF.md is deliberately absent: the shared handoff is
        # frozen for lanes (owner direction 2026-09-04) and carries no
        # lane-current pointer.
        "ACTION_PLAN_2026-08-20.md target block": _action_current(),
        "ACTION_PLAN_2026-08-20.md target row": _action_tpr_row(),
    }
    for name, block in current_surfaces.items():
        assert stale not in block.lower(), (
            f"{name} still calls this lane unmerged; all four lanes are in main"
        )
        assert branch_rule in " ".join(block.lower().split()), (
            f"{name} must preserve the owner-directed per-lane correction rule"
        )
        assert unauthorized_routing not in " ".join(block.lower().split()), (
            f"{name} must not infer cross-lane edit authority from integration"
        )

    # The historical block must not silently lose its supersession marker.
    propagation_tail = record[record.index("### 15.4"):]
    next_subsection = propagation_tail.find("\n### ", len("### 15.4"))
    propagation = (
        propagation_tail
        if next_subsection == -1
        else propagation_tail[:next_subsection]
    )
    if stale in propagation.lower():
        assert "superseded in part" in propagation.lower(), (
            "section 15.4 keeps the stale branch premise without marking it superseded"
        )


def test_a_present_tense_sync_claim_matches_real_ancestry() -> None:
    """TPR-CR6-001. Being behind `main` is normal; claiming otherwise is not.

    An absolute "the lane must contain main" assertion would be wrong: a lane
    is routinely behind `main` mid-round, and such a guard would be red for
    ordinary reasons and get weakened. The durable rule is conditional -- a
    current surface may say the lane is synchronized only while it actually
    contains `origin/main`.

    This caught a claim written by the reviewer who added the surrounding
    guards: the lane was fast-forwarded onto `main`, `main` then advanced, and
    the present-tense sentence survived the divergence.
    """
    mainline = None
    for ref in ("origin/main", "main"):
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            cwd=ROOT, capture_output=True,
        )
        if probe.returncode == 0:
            mainline = ref
            break
    if mainline is None:  # pragma: no cover - export or detached checkout
        pytest.skip("no mainline ref available")

    lane_ref = None
    for ref in (LANE_BRANCH_REF, f"origin/{LANE_BRANCH}"):
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            cwd=ROOT, capture_output=True,
        )
        if probe.returncode == 0:
            lane_ref = ref
            break
    if lane_ref is None:  # pragma: no cover - export without lane refs
        pytest.skip("no target-price lane ref available")

    contains_main = subprocess.run(
        ["git", "merge-base", "--is-ancestor", mainline, lane_ref],
        cwd=ROOT, capture_output=True,
    ).returncode == 0
    main_contains_lane = subprocess.run(
        ["git", "merge-base", "--is-ancestor", lane_ref, mainline],
        cwd=ROOT, capture_output=True,
    ).returncode == 0

    claims = (
        "is now synchronized to",
        "is synchronized to the integrated",
        "now contains every sibling lane",
    )
    surfaces = {
        "record preamble": _record_preamble(),
        "record section 8 integration state": _current_integration_state(
            _record_section("## 8. Exact next step")
        ),
        "record section 8 current qualification": _current_qualification(
            _record_section("## 8. Exact next step")
        ),
        "SESSION_HANDOFF.md target section": _handoff_current(),
        "SESSION_HANDOFF.md target summary": _handoff_target_summary(),
        "ACTION_PLAN_2026-08-20.md target block": _action_current(),
    }
    for name, block in surfaces.items():
        normalized = " ".join(block.lower().split())
        assert not re.search(r"\b\d+\s+(?:commits?\s+)?(?:ahead|behind)\b", normalized), (
            f"{name} contains a self-invalidating live topology count"
        )
        if "neither contains the other" in normalized or "have diverged" in normalized:
            assert not contains_main and not main_contains_lane, (
                f"{name} claims divergence, but {lane_ref} and {mainline} are "
                "now in an ancestor relationship"
            )
        if not contains_main:
            for claim in claims:
                assert claim not in normalized, (
                    f"{name} claims present-tense synchronization with {mainline}, "
                    f"but {lane_ref} does not contain it"
                )


def test_policy_inventory_equals_the_verifier_import_closure() -> None:
    """TPR-CR7-001. The signed policy set must be import-closed, not enumerated.

    TPR-TR0 binds an *enumerated* policy-path set to the signed registry
    anchor, and its test matrix checks only that the set matches and includes
    the verifier. Nothing requires the set to cover everything the verifier
    actually imports. A future internal module that the verifier depends on but
    that nobody adds to the tuple would stay mutable after the signed anchor --
    reintroducing the self-mutable-inventory class `TPR-CCR5-004` exists to
    close, one level out.

    The closure machinery already exists, so the requirement is enforceable
    today rather than left as design prose. This test is deliberately two-way:
    an unlisted internal dependency and a stale listed module both fail.
    """
    from research.target_price_revisions.import_firewall import (
        validate_transitive_import_closure,
    )
    from research.target_price_revisions.preregistration import (
        POLICY_CODE_REPO_PATHS,
    )

    # Non-module policy members are declared, not inferred, so adding one
    # silently is a deliberate act rather than an accident of this comparison.
    NON_MODULE_POLICY_PATHS = frozenset(
        {"research/target_price_revisions/specs/.gitattributes"}
    )

    closure_paths: set[str] = set()
    for module in validate_transitive_import_closure(ROOT):
        relative = Path(*module.split("."))
        for candidate in (
            relative.with_suffix(".py"),
            relative / "__init__.py",
        ):
            if (ROOT / candidate).is_file():
                closure_paths.add(candidate.as_posix())
                break
        else:  # pragma: no cover - a closure module must exist on disk
            raise AssertionError(f"closure module {module} has no source file")

    declared = set(POLICY_CODE_REPO_PATHS)
    module_members = declared - NON_MODULE_POLICY_PATHS

    assert closure_paths <= declared, (
        "the verifier imports internal modules that the signed policy inventory "
        f"does not bind: {sorted(closure_paths - declared)}"
    )
    assert module_members == closure_paths, (
        "the policy inventory's module members must equal the verifier's import "
        f"closure exactly; extra={sorted(module_members - closure_paths)} "
        f"missing={sorted(closure_paths - module_members)}"
    )
    assert NON_MODULE_POLICY_PATHS <= declared, (
        "a declared non-module policy path left the inventory"
    )


def test_session_ledger_rows_have_exact_column_count() -> None:
    """TPR-CR10-001. The out-of-lane ledger is guarded; the session ledger was not.

    A row that drops a column does not fail loudly -- Markdown simply renders
    every later cell under the wrong header, so validation evidence appears as
    findings and the final column silently disappears. That is how a row lost
    its entire `Validation / looks` cell, with the evidence absorbed into the
    summary cell by a later append and nobody noticing.

    Derives the expected width from the table's own header rather than pinning
    a constant, so adding a column to the ledger updates the guard with it.
    """
    record = _record_section("## 10. Session / commit ledger").splitlines()

    headers = [line for line in record if line.startswith("| UTC date |")]
    assert len(headers) == 1, "expected exactly one session-ledger header row"
    expected = headers[0].count("|") - 1

    rows = [line for line in record if line.startswith("| 20") or line.startswith("| YYYY-")]
    assert rows, "session ledger has no data rows"

    malformed = [
        f"{line.split('|')[1].strip()} / {line.split('|')[2].strip()}: "
        f"{line.count('|') - 1} columns"
        for line in rows
        if line.count("|") - 1 != expected
    ]
    assert not malformed, (
        f"session-ledger rows must have exactly {expected} columns; "
        f"malformed: {malformed}"
    )

ISSUE_ROW = r"^\| `(TPR-[A-Z0-9-]+)` \| (P[0-3]) \| ([^|]*)\|"
REGISTER_ROW = r"^\| `(TPR-[A-Z0-9-]+)` \| (P[0-3]) \|"
MALFORMED_PRIORITY_ROW = (
    r"^\| `TPR-(?!OOL-)[A-Z0-9-]+` \| "
    r"(?!P[0-3] \|)(?:\*+)?P[0-9](?:\*+)? \|"
)


def _open_issue_register() -> str:
    """Return section 8's register of every still-open lane finding."""
    return _bounded(
        _record_section("## 8. Exact next step"),
        "### Open-issue register",
        "### Historical progression",
        "open-issue register",
    )


def test_open_issue_register_matches_every_issue_row() -> None:
    """One current answer to what is still open.

    The register prevents a canonical finding row and the current routing from
    drifting apart.  The guard also pins that the owner-approved TPR-0A/0B
    phase split closed `TPR-CCR1-004` and `TPR-CCR1-005`; a later census must
    not reopen those historical blockers merely because their original rows
    were stale.

    The register makes the open set explicit, and this guard makes it
    checkable in both directions: closing a finding without delisting it
    fails, and delisting one without closing its row fails too.  Out-of-lane
    findings live in section 9 and are excluded by construction, since their
    third column is an area rather than a status.
    """
    record = (STRATEGY_DIR / RECORD).read_text(encoding="utf-8")
    register = _open_issue_register()
    outside = record.replace(register, "", 1)
    assert register not in outside, "the register block must appear once"

    rows = re.findall(ISSUE_ROW, outside, re.MULTILINE)
    malformed_priority_rows = re.findall(
        MALFORMED_PRIORITY_ROW, outside, re.MULTILINE
    )
    assert not malformed_priority_rows, (
        "issue-looking rows must use one exact unformatted P0-P3 priority"
    )
    assert len(rows) > 50, (
        f"only {len(rows)} issue rows parsed; the row shape changed and this "
        f"guard would silently stop covering the ledgers"
    )
    identifiers = [identifier for identifier, _priority, _status in rows]
    assert len(identifiers) == len(set(identifiers)), (
        "each finding must have exactly one row so its status cannot fork"
    )

    open_priorities = {
        identifier: priority
        for identifier, priority, status in rows
        if status.replace("**", "").strip().lower().startswith("open")
    }
    registered_rows = re.findall(REGISTER_ROW, register, re.MULTILINE)
    registered_ids = [identifier for identifier, _priority in registered_rows]
    assert len(registered_ids) == len(set(registered_ids)), (
        "the open-issue register must not collapse duplicate identifiers"
    )
    registered_priorities = dict(registered_rows)
    assert registered_priorities == open_priorities, (
        "the open-issue register and canonical finding rows disagree in id or "
        f"priority; register={registered_priorities}, open={open_priorities}"
    )
    assert {"TPR-CCR1-004", "TPR-CCR1-005"}.isdisjoint(registered_priorities)

    for line in register.splitlines():
        if not line.startswith("| `TPR-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 4 and all(cells), (
            f"register row {cells[0]} must name a priority, what it blocks, and "
            f"why it cannot be closed in lane"
        )

def test_latest_claude_review_records_the_exact_codex_range() -> None:
    """TPR-CR13-001/002: keep this round's handoff exact and reproducible.

    The counter-review preceding this one was faulted for leaving every
    current pointer on the completed round (`TPR-CCR12-001`).  A Claude round
    can fail the same way, so its own review section is pinned here.
    """
    section = _record_section(
        "## 38. Claude independent review of the Codex counter-review round"
    )
    assert LATEST_REVIEWED_CODEX_RANGE in section
    ordered_commits = tuple(
        re.search(r"`([0-9a-f]{40})`", line).group(1)
        for line in section.splitlines()
        if re.match(r"[|] Codex commit [0-9]+ [|]", line)
    )
    assert ordered_commits == LATEST_REVIEWED_CODEX_COMMITS
    assert "Cumulative disposition: accepted after correction" in section
    assert "No next implementation milestone is authorized" in section
