"""Target-owned documentation guards for the Target-Price Revisions lane."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
import subprocess
from pathlib import Path

from research.target_price_revisions import PRIMARY_CELL_ID, PRIMARY_LOOK_ID
from research.target_price_revisions.preregistration import load_algorithm_candidate


ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = ROOT / "docs" / "Strategy Description"
LANE_BRANCH = "codex/strategy-target-price-revisions"
BLUEPRINT = "TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf"
RECORD = "TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md"
EXPECTED_WORKTREE = "trading_agent_target_price"
SPEC_PATH = (
    ROOT / "research" / "target_price_revisions" / "specs"
    / "tpr_round0a.candidate.json"
)
OBSOLETE_WORKTREE = "trading_agent_TargetPriceRevision"
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
CLAUDE_V22_REVIEW_HEAD = "db6a721d45eb47e1a133744387bf43a1aa1f310c"


def _doc(name: str) -> str:
    return (ROOT / "docs" / name).read_text(encoding="utf-8")


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


def test_lane_documents_agree_on_one_worktree() -> None:
    """TPR-CR1-005: every coordination pointer names the real worktree."""
    expected_pointers = {
        "ACTION_PLAN_2026-08-20.md": (
            f"`{EXPECTED_WORKTREE}` worktree"
        ),
        "SESSION_HANDOFF.md": (
            rf"`C:\git\customizedagent\{EXPECTED_WORKTREE}` on branch"
        ),
        f"Strategy Description/{RECORD}": (
            f"Worktree:\n`C:\\git\\customizedagent\\{EXPECTED_WORKTREE}`"
        ),
    }
    for name, pointer in expected_pointers.items():
        assert pointer in _doc(name), (
            f"{name} must carry the registered target-price worktree pointer"
        )

    # TPR-CR2-003: the exact-pointer checks above prove the right name is
    # present, but not that a wrong one is absent.  A third spelling could be
    # introduced anywhere and every assertion above would still pass, which is
    # the same hole that let one nonexistent directory sit in three documents.
    # The two pure coordination documents must carry no other worktree name at
    # all; the lane record may name the obsolete directory only as historical
    # finding evidence, never as an additional active pointer.
    active: set[str] = set()
    for name in expected_pointers:
        names = set(re.findall(r"\w*trading_agent\w*", _doc(name))) - {"trading_agent"}
        if name != f"Strategy Description/{RECORD}":
            assert OBSOLETE_WORKTREE not in names, (
                f"{name} is a current-state pointer and must not name the "
                f"obsolete worktree at all"
            )
        active |= names - {OBSOLETE_WORKTREE}

    assert active == {EXPECTED_WORKTREE}, (
        f"lane documents name more than one active worktree: {sorted(active)}"
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
    start = section.index("**Current qualification")
    end = section.index("\n### Historical progression", start)
    return section[start:end]


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
    assert CLAUDE_V22_REVIEW_HEAD in normalized_current
    assert "Claude's independent review is complete" in normalized_current
    assert "No next implementation milestone is authorized" in normalized_current
    assert "TPR-1 remains blocked" in normalized_current
    assert "reviewed-spec registry remains empty" in normalized_current
    assert "pending Claude review of this Codex round" not in normalized_current

    routing_row = next(
        line
        for line in _record_section("## 9. Out-of-lane findings ledger").splitlines()
        if "`TPR-OOL-001-R1`" in line
    )
    assert "29-page v2.2" in routing_row
    assert BLUEPRINT_CONTENT_SHA256 in routing_row.lower()

    for name in ("ACTION_PLAN_2026-08-20.md", "SESSION_HANDOFF.md"):
        document = _doc(name)
        assert CLAUDE_V22_REVIEW_HEAD in document
        assert "No next implementation milestone is authorized" in document
