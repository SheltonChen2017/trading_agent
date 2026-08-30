"""Target-owned documentation guards for the Target-Price Revisions lane."""
from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = ROOT / "docs" / "Strategy Description"
LANE_BRANCH = "codex/strategy-target-price-revisions"
BLUEPRINT = "TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf"
RECORD = "TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md"
EXPECTED_WORKTREE = "trading_agent_target_price"
OBSOLETE_WORKTREE = "trading_agent_TargetPriceRevision"
BLUEPRINT_CONTENT_SHA256 = (
    "9f00dd56bf7bec79b3f5362bba61fe71768d1f25e6e4350631dafd1253682633"
)
MALFORMED_SUBMITTED_SOURCE_PIN = (
    "53c549aef18aa1a63e6db8deb184bd654eb8ec637bb4ff3ae03f29abc4a2df0"
)


def _doc(name: str) -> str:
    return (ROOT / "docs" / name).read_text(encoding="utf-8")


def test_blueprint_is_pinned_to_the_lane_record() -> None:
    """TPR-CR1-002: bind the checked-out PDF content to its lane record."""
    record = (STRATEGY_DIR / RECORD).read_text(encoding="utf-8")
    raw = (STRATEGY_DIR / BLUEPRINT).read_bytes()
    digest = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()

    assert digest == BLUEPRINT_CONTENT_SHA256
    assert digest in record.lower()
    assert LANE_BRANCH in record
    assert "docs/ACTION_PLAN_2026-08-20.md" in record
    assert "docs/SESSION_HANDOFF.md" in record
    for name in ("ACTION_PLAN_2026-08-20.md", "SESSION_HANDOFF.md"):
        assert LANE_BRANCH in _doc(name)


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
    """TPR-CR1-004: the known 63-hex source value is not valid provenance."""
    record = (STRATEGY_DIR / RECORD).read_text(encoding="utf-8")
    handoff = _doc("SESSION_HANDOFF.md")

    assert MALFORMED_SUBMITTED_SOURCE_PIN not in record.lower()
    assert MALFORMED_SUBMITTED_SOURCE_PIN not in handoff.lower()
    assert "Submitted source-plan SHA-256: **MALFORMED AND UNVERIFIABLE.**" in record
    assert "63 hexadecimal characters" in record
    assert "63 hexadecimal characters" in handoff
