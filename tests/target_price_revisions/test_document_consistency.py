"""Target-owned documentation guards for the Target-Price Revisions lane."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from research.target_price_revisions.preregistration import load_algorithm_candidate


ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = ROOT / "docs" / "Strategy Description"
LANE_BRANCH = "codex/strategy-target-price-revisions"
BLUEPRINT = "TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf"
RECORD = "TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md"
EXPECTED_WORKTREE = "trading_agent_target_price"
OBSOLETE_WORKTREE = "trading_agent_TargetPriceRevision"
BLUEPRINT_CONTENT_SHA256 = (
    "55ce6703c9b07580db9d09c22154dff86001765f8ec93391ed5f0b763314ba14"
)
MALFORMED_SUBMITTED_SOURCE_PIN = (
    "53c549aef18aa1a63e6db8deb184bd654eb8ec637bb4ff3ae03f29abc4a2df0"
)
CANDIDATE_RELATIVE = Path(
    "research/target_price_revisions/specs/tpr_round0a.candidate.json"
)
EXPECTED_CANDIDATE_ID = "tpr-round0a-candidate-f595992a3f5b8396"
EXPECTED_CANDIDATE_HASH = (
    "f595992a3f5b8396e5f26ba5a3b0a3f32649eec3fd581071b349a5e12203af86"
)
EXPECTED_CANDIDATE_ARTIFACT_SHA256 = (
    "99aae28d5b055aa24b84ce153467dfdbe7ee65f8ee2cef2a870efe1e68b2ea49"
)


def _doc(name: str) -> str:
    return (ROOT / "docs" / name).read_text(encoding="utf-8")


def test_blueprint_is_pinned_to_the_lane_record() -> None:
    """Bind the exact binary PDF content to the lane record."""
    record = (STRATEGY_DIR / RECORD).read_text(encoding="utf-8")
    raw = (STRATEGY_DIR / BLUEPRINT).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()

    assert digest == BLUEPRINT_CONTENT_SHA256
    assert digest in record.lower()
    assert "Governing plan page count: **28**." in record
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
        assert "pending claude" in document
