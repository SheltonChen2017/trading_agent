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
# The current Codex round received one exact Claude review commit followed by
# an owner-directed integration/main-merge series.  Do not infer a reviewer
# role from author metadata: section 40 records the two provenance classes and
# dispositions every commit in the cumulative Git range.
LATEST_COUNTERREVIEWED_RECEIVED_BASE = (
    "49caa886a63c4a24b6be0a4d8dbd71d9d95e9ad3"
)
LATEST_COUNTERREVIEWED_RECEIVED_HEAD = (
    "d54ce1b2c6816532ef82906c49998a93574172fc"
)
LATEST_COUNTERREVIEWED_RECEIVED_RANGE = (
    f"{LATEST_COUNTERREVIEWED_RECEIVED_BASE}.."
    f"{LATEST_COUNTERREVIEWED_RECEIVED_HEAD}"
)
LATEST_COUNTERREVIEWED_RECEIVED_SHORT_RANGE = "49caa886..d54ce1b2"
LATEST_CLAUDE_CORRECTION_COMMIT = (
    "dff9b11238f35c5c411669197bc078936fbf9c9a"
)
CURRENT_MAIN_SYNC_LANE_HEAD = (
    "e74da9ef34fac111cef838dbbe9814030daf3cf4"
)
CURRENT_MAIN_SYNC_MAIN_HEAD = (
    "9e834713cd8be0f184af730118199b2cab90336a"
)
CURRENT_MAIN_SYNC_MERGE_BASE = (
    "df388ce64cd705f2ed26fab3442a0229f52a447b"
)
CURRENT_MAIN_SYNC_MERGE_COMMIT = (
    "6590d890509f75d8b7b87fa9b665b48fa1dbd0aa"
)
CURRENT_MAIN_IMPORTED_CLOSURE_COMMITS = (
    "e53ba26bec6f12861edeaff4383dce4db2ccd37e",
    "37dc424fee28fd71fbd23951e267c6997088a889",
    "3aedfffc05a3108f554555d3d22d7b58d8299175",
    "89f385cd442ea16f39ae7599c738797c64a2fba1",
    "64edf355cc5afce4df770100ef2772d024dc3649",
    "c83218c7583c9cbfc7840f02324a431ab00a33ad",
    "6baa13d2acbeac48e9dec3f81acbdeb1cae8c370",
    "b3b202d2a8bf0ecc8a3613dcbfdb3690483ad767",
    "2c392cd30ce4979d4f36d0b6e1b8b7323f8bc6ef",
    "726c4dcf85fd71e0e175e5e01be5f614c76dab66",
    "66f0fef4ac66f7d8f8805fa02ec0b918fbb10463",
    "143b18859c923d183e657531d17d88833c995006",
    "35c467e53a788d7a6416ee22c1d2ad53901cd2b1",
    "0ebce0132b4cc60e518dff089ab982be74f14e89",
    "d774195d4c62fc93c81e02b3887cd58bfa918629",
    "9047375ece396ce39c48dec088e233313446daa3",
    "22a889d03879b74c09bbccc80c6d4ef07a061bcf",
)
LATEST_RECEIVED_FIRST_PARENT_COMMITS = (
    "dff9b11238f35c5c411669197bc078936fbf9c9a",
    "e0270c8bbf425f85af43b13eda6cb6bb59b252f4",
    "09c296ee14c3beb6f81d4f887040a4814e1dab3c",
    "1e3757c241948609edf598388dd64e711d925810",
    "38ca96fefb38cc0fa859e51adb6d5914bd8ac5ee",
    "636b8dd0467f7f068f0d4dd1546462e4afe18b5d",
    "06f61dfa908f6bf43acfe0475f373fa548d63075",
    "55df4ebdb14b824e005e32706a09a3ef3fd4f8ac",
    "16b3435bcf83a76ebee04679c4c266b6f2daeab4",
    "522da19881f03c1c80c216b1618ab2005612a5db",
    "47103e4a3299d0707725d75729fcd8da35e23831",
    "c71dcd9b3c2eea26deb11c3ee0d3eaa2189705f1",
    "ce5d355f9ce23b005f6a021e6330f346986ce31f",
    "e989872988a943b476502bd5573abbc0e0406122",
    "4e4840df4bb323a3a4dbe9854d5909996f754771",
    "2f4e087cd29d635bbc2dad215dac05c4a0f490ca",
    "c78f3451c569970b554a948606bfce063ee71ac0",
    "f6ed271b0b67af1161f3cd2823dde53413e4cbb7",
    "6a673d0ab226e29d3ed1911aa38644599591557d",
    "903a857455c4525097b60aa18d06c8e9ef8d2111",
    "f67c633208d238b960919024ae910385065c3def",
    "7e1f18b61b91774caf4b7bcf55df0f2d33495da3",
    "15bedb56ad7238d70a2cbea78b8e30ba37b2aea0",
    "9ee3b3ed8a62b4533b44c038dbcdac16c3d899e0",
    "d54ce1b2c6816532ef82906c49998a93574172fc",
)
# The one commit section 40 rejects; every other first-parent row is accepted,
# accepted after correction, or accepted after qualification.
LATEST_RECEIVED_REJECTED_COMMIT = "903a857455c4525097b60aa18d06c8e9ef8d2111"
# Claude's 2026-10-02 review (section 42) covers the cumulative Codex range
# that followed the mixed-role interval: the counter-review, its validation
# record, the main merge, and the two synchronization-record commits.
CURRENT_CLAUDE_REVIEWED_CODEX_BASE = (
    "d54ce1b2c6816532ef82906c49998a93574172fc"
)
CURRENT_CLAUDE_REVIEWED_CODEX_HEAD = (
    "ea97bd4fc03779b7947cf35cd8e4432b0b9fa516"
)
CURRENT_CLAUDE_REVIEWED_CODEX_RANGE = (
    f"{CURRENT_CLAUDE_REVIEWED_CODEX_BASE}.."
    f"{CURRENT_CLAUDE_REVIEWED_CODEX_HEAD}"
)
CURRENT_CLAUDE_REVIEWED_CODEX_SHORT_RANGE = "d54ce1b2..ea97bd4f"
CURRENT_COUNTERREVIEWED_CLAUDE_BASE = "ea97bd4fc03779b7947cf35cd8e4432b0b9fa516"
CURRENT_COUNTERREVIEWED_CLAUDE_HEAD = "3de5bbef3a25d8a37647869ad840808543927a82"
CURRENT_COUNTERREVIEWED_CLAUDE_RANGE = (
    f"{CURRENT_COUNTERREVIEWED_CLAUDE_BASE}..{CURRENT_COUNTERREVIEWED_CLAUDE_HEAD}"
)
CURRENT_COUNTERREVIEWED_CLAUDE_SHORT_RANGE = "ea97bd4f..3de5bbef"
CURRENT_COUNTERREVIEWED_CLAUDE_COMMITS = (
    "174a546c2d3ea6c8d9f41a38f42ecf2a197f6437",
    "299492af461d4f611bb4a32f899b6d5f94de92ed",
    "3de5bbef3a25d8a37647869ad840808543927a82",
)
# Claude's second 2026-10-02 review (section 45) covers the counter-review
# snapshot and the owner-scoped shared remediation that followed it.
SECTION45_REVIEWED_CODEX_BASE = "3de5bbef3a25d8a37647869ad840808543927a82"
SECTION45_REVIEWED_CODEX_HEAD = "9958a459f5cd56c29cb9a0de13d38737e2c3412d"
SECTION45_REVIEWED_CODEX_RANGE = (
    f"{SECTION45_REVIEWED_CODEX_BASE}..{SECTION45_REVIEWED_CODEX_HEAD}"
)
SECTION45_REVIEWED_CODEX_SHORT_RANGE = "3de5bbef..9958a459"
SECTION45_REVIEWED_CODEX_COMMITS = (
    "b639ea46c8d184eb7971de67dcdc091659ad4d65",
    "37598fa5b686a14e906c92dcea4c17b9d9b933b7",
    "a8e4afefe3232f6515c17e9dbde1ae9781fe0776",
    "9958a459f5cd56c29cb9a0de13d38737e2c3412d",
)
SECTION45_OWNER_INPUT_IDS = tuple(f"TPR-OWN-{index}" for index in range(1, 6))
# The Codex range this Claude round (section 48) reviewed.
SECTION48_CODEX_BASE = "c0bfb21393180d44c16c10be1e667ea741098531"
SECTION48_CODEX_HEAD = "c5c060e6712afa75c0eeb05482ef469322d311cf"
SECTION48_CODEX_RANGE = f"{SECTION48_CODEX_BASE}..{SECTION48_CODEX_HEAD}"
SECTION48_CODEX_SHORT_RANGE = "c0bfb213..c5c060e6"
SECTION48_CODEX_COMMITS = (
    "cf11788f39a2148d7bc3b801e88807bd2caca5ea",
    "8dcfb71851ff22db6f0727395e18292c19f080ef",
    "c5c060e6712afa75c0eeb05482ef469322d311cf",
)
SECTION49_CLAUDE_BASE = "c5c060e6712afa75c0eeb05482ef469322d311cf"
SECTION49_CLAUDE_HEAD = "c15dfee552eafb5489bdc545d0150b85ca96ef52"
SECTION49_CLAUDE_RANGE = f"{SECTION49_CLAUDE_BASE}..{SECTION49_CLAUDE_HEAD}"
SECTION49_CLAUDE_SHORT_RANGE = "c5c060e6..c15dfee5"
SECTION49_CLAUDE_COMMITS = (
    "ff05d6b2fdf7fc56bd7164de5192ad72ec3581db",
    "c15dfee552eafb5489bdc545d0150b85ca96ef52",
)
# Claude's 2026-10-05 review (section 51) of the Codex counter-review and the
# fixture-only TPR-D1 candidate.
SECTION51_CODEX_BASE = "c15dfee552eafb5489bdc545d0150b85ca96ef52"
SECTION51_CODEX_HEAD = "01e703906df838fd9cbb91a2d1fd03ce7d18f288"
SECTION51_CODEX_RANGE = f"{SECTION51_CODEX_BASE}..{SECTION51_CODEX_HEAD}"
SECTION51_CODEX_SHORT_RANGE = "c15dfee5..01e70390"
SECTION51_CODEX_COMMITS = (
    "1e6365917c292c2e1ada5b1f837ed8d069cc697d",
    "7baddbbc303e76ef91850b3e4a53cfe4030f4fea",
    "01e703906df838fd9cbb91a2d1fd03ce7d18f288",
)
SECTION51_CODEX_DISPOSITIONS = (
    "accepted", "accepted after correction", "accepted after correction",
)
SECTION52_CLAUDE_BASE = "01e703906df838fd9cbb91a2d1fd03ce7d18f288"
SECTION52_CLAUDE_HEAD = "67aade0e47d6f4d6c6290018bbe7b52831a465c7"
SECTION52_CLAUDE_RANGE = f"{SECTION52_CLAUDE_BASE}..{SECTION52_CLAUDE_HEAD}"
SECTION52_CLAUDE_SHORT_RANGE = "01e70390..67aade0e"
SECTION52_CLAUDE_COMMITS = (
    "3e2be6bcaf06ff4b1f806a04d61bf8895e83ce38",
    "40f849b2d1a956ea3abf6a2c60f453f3b703f302",
    "67aade0e47d6f4d6c6290018bbe7b52831a465c7",
)
SECTION52_OWNER_REVIEW_SCOPE = (
    "Claude reviewed, start the counterreview before moving to the next milestone"
)
SECTION52_OWNER_HANDOFF_SCOPE = (
    "when you are done. push. then arm a monitor for Claude's subsequent review"
)
SECTION52_SCOPE_BOUNDARIES = {
    "Counter-review": "Every incoming Claude commit and cumulative tree",
    "Next milestone": "Not authorized",
    "Data inputs": "Synthetic fixtures and committed D0 aggregate report only",
    "Additional data access": "Forbidden",
    "Trust provisioning": "Forbidden",
    "Outcome/QC/trading": "Forbidden",
    "Publication": "One matching-lane non-force push",
    "Monitor": "One completed Claude review of this published counter-review",
}
SECTION50_OWNER_SCOPE = (
    "Counter-review both Claude commits. If accepted, implement one fixture-only "
    "TPR-D1 candidate using synthetic fixtures and the committed D0 aggregate "
    "report. No additional data access. Stop for Claude review."
)
SECTION50_D0_REPORT_SHA256 = (
    "fbe99ce620689c61052330a220b9f989b29a8ea732a45204d88b02e6f5648148"
)
SECTION50_SCOPE_BOUNDARIES = {
    "Inputs": "Synthetic fixtures and the committed D0 aggregate report only",
    "Additional data access": "Forbidden",
    "Retained-row processing": "Forbidden",
    "Provider requests": "Forbidden",
    "Price/outcome access": "Forbidden",
    "QuantConnect": "Forbidden",
    "Trust provisioning": "Forbidden",
    "Real raw/normalized row publication": "Forbidden",
    "TPR-D2": "Not authorized",
    "Review handoff": "Stop for independent Claude review",
}
# TPR-CR16-002: commit identities section 8 may name besides its own range.
# Stable identities change only when that artifact changes; branch-relation
# commits change only when the lane is synchronized with main.  Both are
# deliberate, reviewed edits -- never a per-round routing update.
SECTION8_STABLE_COMMITS = frozenset({
    "20e20d7f68d39d17af84d6a5c65e22b78dc57eb1",  # TPR-TR0-I code checkpoint
    "bb8dfb6e8d718f9371bbbd85b30f5f9a769f396e",  # reviewed TPR-0A snapshot
})
SECTION8_BRANCH_RELATION_COMMITS = frozenset({"9e834713", "6590d890", "15bedb56"})
SECTION8_ROLE_STATEMENT = (
    r"\b(?:Claude|Codex) (?:has )?(?:independently )?(?:reviewed|counter-reviewed)\b"
)
SECTION8_NEXT_ACTION_STATEMENT = r"\b(?:Claude|Codex) next (?:reviews|counter-reviews)\b"
SECTION46_CLAUDE_BASE = "9958a459f5cd56c29cb9a0de13d38737e2c3412d"
SECTION46_CLAUDE_HEAD = "c0bfb21393180d44c16c10be1e667ea741098531"
SECTION46_CLAUDE_RANGE = f"{SECTION46_CLAUDE_BASE}..{SECTION46_CLAUDE_HEAD}"
SECTION46_CLAUDE_SHORT_RANGE = "9958a459..c0bfb213"
SECTION46_CLAUDE_COMMITS = (
    "1a4fd3778ec3caa43c794eb08be4ef901da5c706",
    "c2c0672feb3d33069c553d861481591d556dca29",
    "29c87ae75d777e4b071f93f476596e1724aac636",
    "c0bfb21393180d44c16c10be1e667ea741098531",
)
CURRENT_CLAUDE_REVIEWED_FIRST_PARENT_COMMITS = (
    "059c93e73cc17b4bc0b01c1d14ab637acf285b7e",
    "e74da9ef34fac111cef838dbbe9814030daf3cf4",
    "6590d890509f75d8b7b87fa9b665b48fa1dbd0aa",
    "0d070266d84a05dc73a2c7b405c0f337ca7c3c97",
    "ea97bd4fc03779b7947cf35cd8e4432b0b9fa516",
)
CURRENT_OWNER_DECISION_IDS = (
    "TPR-OD-001",
    "TPR-OD-002",
    "TPR-OD-003",
    "TPR-OD-004",
)
# Role-pending wording that makes a shared, non-per-round surface go stale the
# moment the named role acts (TPR-CR14-003).
PER_ROUND_PENDING_PHRASES = (
    "awaits independent claude review",
    "awaits claude review",
    "awaits codex counter-review",
    "claude next reviews",
    "codex next counter-reviews",
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
        encoding="utf-8",
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
            encoding="utf-8",
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
        encoding="utf-8",
    )
    return completed.stdout.splitlines()


def test_git_document_output_is_utf8_under_a_non_utf8_locale(monkeypatch) -> None:
    """The same UTF-8 Git blob must decode identically on Windows and POSIX."""
    monkeypatch.setattr(subprocess, "_text_encoding", lambda: "cp1252")
    lines = _git_lines("show", f"{CURRENT_MAIN_SYNC_MERGE_COMMIT}:docs/ACTION_PLAN_2026-08-20.md")
    assert "**Owner multiplicity amendment, 2026-08-30 \u2014 affects all four strategy lanes:**" in lines


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
        "**Integration state, 2026-10-02.**",
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
    ) == [SECTION52_CLAUDE_RANGE]
    assert PREVIOUS_COUNTERREVIEWED_CLAUDE_HEAD not in normalized_current
    assert PREVIOUS_COUNTERREVIEWED_CLAUDE_SHORT_HEAD not in normalized_current
    assert (
        "Codex has counter-reviewed the exact Claude range"
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
    assert "comprehensive whole-lane audit remains complete" in normalized_current.lower()
    assert CURRENT_MAIN_SYNC_MERGE_COMMIT[:8] in current
    # The owner directly selected bounded D0 decisions on 2026-10-05.
    # Historical wait states cannot override that scope or widen it to outcomes.
    assert "awaits independent Claude review" not in normalized_current
    assert "Fixture-only TPR-D1 candidate awaits independent Claude review" not in normalized_current
    assert "fixture-only TPR-D1 candidate is accepted" in normalized_current
    assert "Claude next reviews sections 43 and 44" not in normalized_current
    assert "Codex next counter-reviews section 42" not in normalized_current
    assert "Codex next counter-reviews section 45" not in normalized_current
    assert "Claude next reviews sections 46 and 47" not in normalized_current
    assert "Claude next reviews sections 49 and 50" not in normalized_current
    assert "Codex next counter-reviews section 51" not in normalized_current
    assert "Claude next reviews section 52" in normalized_current
    assert "TPR-D1 is authorized only as a fixture-only candidate" in normalized_current
    assert "D0's one completed audit is not renewed" in normalized_current
    assert "TPR-D2 is not authorized" in normalized_current
    assert "TPR-D0 is not authorized" not in normalized_current
    assert "No next implementation milestone is authorized" not in normalized_current
    assert "remain historical proposals" in normalized_current
    assert "owner working assumption" in normalized_current
    assert "2026-10-12" in normalized_current
    assert "`TPR-CR15-001`" in normalized_current
    assert "`TPR-OWN-1` through `TPR-OWN-5`" in normalized_current
    for decision in CURRENT_OWNER_DECISION_IDS:
        assert f"`{decision}`" in normalized_current

    routing_row = next(
        line
        for line in _record_section("## 9. Out-of-lane findings ledger").splitlines()
        if "`TPR-OOL-001-R1`" in line
    )
    assert "29-page v2.2" in routing_row
    assert BLUEPRINT_CONTENT_SHA256 in routing_row.lower()

    # The shared Session Handoff is frozen for lanes, while the Action Plan is
    # changed only by an owner-coordinated concise status amendment. Section 8
    # of this record remains the only per-round current-state pointer.

    for summary_pointer in (
        _record_preamble(),
        # the shared handoff remains frozen; Action Plan changes require owner coordination
    ):
        normalized_summary = " ".join(summary_pointer.split())
        normalized_summary_lower = normalized_summary.lower()
        assert re.findall(
            r"`([0-9a-f]{8}\.{2}[0-9a-f]{8})`", normalized_summary
        ) == [SECTION52_CLAUDE_SHORT_RANGE]
        assert PREVIOUS_COUNTERREVIEWED_CLAUDE_SHORT_HEAD not in normalized_summary
        assert "codex has counter-reviewed every claude commit" in normalized_summary_lower
        assert "section 52" in normalized_summary_lower
        assert "awaits claude review" not in normalized_summary_lower
        assert "fixture-only tpr-d1 candidate is accepted" in normalized_summary_lower
        assert "claude next reviews the counter-review and tpr-d0" not in normalized_summary_lower
        assert "claude next reviews sections 49 and 50" not in normalized_summary_lower
        assert "codex next counter-reviews section 51" not in normalized_summary_lower
        assert "claude next reviews section 52" in normalized_summary_lower
        assert "tpr-d2 is not authorized" in normalized_summary_lower
        assert "tpr-d0 is not authorized" not in normalized_summary_lower
        assert "no next implementation milestone is authorized" not in normalized_summary_lower
        assert (
            "the non-authorizing tpr-tr0-i implementation candidate is checkpointed but remains incomplete"
            in normalized_summary_lower
        )
        assert "no key provisioning or positive authority is authorized" in normalized_summary_lower
        assert "comprehensive claude whole-lane audit remains complete" in (
            normalized_summary_lower
        )


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


def test_current_counterreview_records_every_received_commit_and_provenance() -> None:
    """TPR-CCR13-001: pin the mixed-role range without author inference."""
    section = _record_section(
        "## 40. Codex counter-review of the recent mixed-role range"
    )
    assert LATEST_COUNTERREVIEWED_RECEIVED_RANGE in section
    assert LATEST_CLAUDE_CORRECTION_COMMIT in section
    first_parent = _bounded(
        section,
        "### 40.2 First-parent commit dispositions",
        "### 40.3 Merge-inherited commit dispositions",
        "section 40 first-parent dispositions",
    )
    ordered_commits = tuple(
        re.search(r"`([0-9a-f]{40})`", line).group(1)
        for line in first_parent.splitlines()
        if line.startswith("| `")
    )
    assert ordered_commits == LATEST_RECEIVED_FIRST_PARENT_COMMITS
    assert "Cumulative disposition: rejected" in section
    assert "No next implementation milestone is authorized" in section

    # TPR-CR14-004: the order pin above let a flipped disposition and a deleted
    # merge-inherited row through.  Pin the one rejection and derive the
    # inherited set from Git so "every received commit" is checked, not named.
    first_parent_dispositions = {
        match.group(1): match.group(2).lower()
        for line in first_parent.splitlines()
        if (
            match := re.match(
                r"\| `([0-9a-f]{40})` \| \*\*([a-z ]+)\*\* \|", line
            )
        )
    }
    assert set(first_parent_dispositions) == set(
        LATEST_RECEIVED_FIRST_PARENT_COMMITS
    )
    assert {
        commit
        for commit, disposition in first_parent_dispositions.items()
        if disposition == "rejected"
    } == {LATEST_RECEIVED_REJECTED_COMMIT}
    admitted_dispositions = {
        "accepted",
        "accepted after correction",
        "accepted after qualification",
        "rejected",
    }
    assert set(first_parent_dispositions.values()) <= admitted_dispositions

    inherited = _bounded(
        section,
        "### 40.3 Merge-inherited commit dispositions",
        "### 40.4 P0-P3 ledger",
        "section 40 merge-inherited dispositions",
    )
    inherited_rows = [
        re.match(r"\| `([0-9a-f]{40})` \|", line).group(1)
        for line in inherited.splitlines()
        if line.startswith("| `")
    ]
    reachable = set(_git_lines("rev-list", LATEST_COUNTERREVIEWED_RECEIVED_RANGE))
    assert len(inherited_rows) == len(set(inherited_rows))
    assert set(inherited_rows) == reachable - set(
        LATEST_RECEIVED_FIRST_PARENT_COMMITS
    )
    # The rejected shared patch also arrives through the merge.  Its row must
    # retain the same disposition as the first-parent twin, not merely its ID.
    inherited_dispositions = {
        match.group(1): match.group(2).lower()
        for line in inherited.splitlines()
        if (
            match := re.match(
                r"\| `([0-9a-f]{40})` \| \*\*([a-z ]+)\*\* \|", line
            )
        )
    }
    assert set(inherited_dispositions) == set(inherited_rows)
    assert set(inherited_dispositions.values()) <= admitted_dispositions
    assert {
        commit
        for commit, disposition in inherited_dispositions.items()
        if disposition == "rejected"
    } == {"f4764671b9f3ee0de50ab36a7cf61854bca72c4f"}


def test_current_main_sync_records_exact_merge_and_safe_conflict_union() -> None:
    """The owner-directed sync must preserve both intended Action Plan updates."""
    section = _record_section("## 41. Codex synchronization with current main")
    for identity in (
        CURRENT_MAIN_SYNC_LANE_HEAD,
        CURRENT_MAIN_SYNC_MAIN_HEAD,
        CURRENT_MAIN_SYNC_MERGE_BASE,
        CURRENT_MAIN_SYNC_MERGE_COMMIT,
        *CURRENT_MAIN_IMPORTED_CLOSURE_COMMITS,
    ):
        assert identity in section

    merge_base = subprocess.run(
        [
            "git",
            "merge-base",
            CURRENT_MAIN_SYNC_LANE_HEAD,
            CURRENT_MAIN_SYNC_MAIN_HEAD,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    assert merge_base == CURRENT_MAIN_SYNC_MERGE_BASE

    parents = subprocess.run(
        ["git", "show", "-s", "--format=%P", CURRENT_MAIN_SYNC_MERGE_COMMIT],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.split()
    assert parents == [CURRENT_MAIN_SYNC_LANE_HEAD, CURRENT_MAIN_SYNC_MAIN_HEAD]
    assert subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            CURRENT_MAIN_SYNC_MERGE_COMMIT,
            "HEAD",
        ],
        cwd=ROOT,
        capture_output=True,
    ).returncode == 0
    for commit in CURRENT_MAIN_IMPORTED_CLOSURE_COMMITS:
        assert subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                commit,
                CURRENT_MAIN_SYNC_MAIN_HEAD,
            ],
            cwd=ROOT,
            capture_output=True,
        ).returncode == 0

    target_paths = (
        "research/target_price_revisions",
        "tests/target_price_revisions",
        "docs/Strategy Description/TARGET_PRICE_REVISION_IMPLEMENTATION_RECORD.md",
        "docs/Strategy Description/TARGET_PRICE_REVISION_ETF_ALPHA_RESEARCH_QC_BLUEPRINT_V2_EN.pdf",
    )
    assert subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            CURRENT_MAIN_SYNC_LANE_HEAD,
            CURRENT_MAIN_SYNC_MERGE_COMMIT,
            "--",
            *target_paths,
        ],
        cwd=ROOT,
        capture_output=True,
    ).returncode == 0

    merge_blobs = {
        relative: subprocess.run(
            ["git", "show", f"{CURRENT_MAIN_SYNC_MERGE_COMMIT}:{relative}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
        for relative in (
            "docs/ACTION_PLAN_2026-08-20.md",
            "docs/SESSION_HANDOFF.md",
        )
    }
    merge_action_plan = merge_blobs["docs/ACTION_PLAN_2026-08-20.md"]
    assert merge_action_plan.count(
        "**Owner-directed Insider paper-stage sequencing amendment, 2026-09-18:**"
    ) == 1
    assert merge_action_plan.count("**Current bounded status, 2026-09-04:**") == 1
    assert "**Current bounded status, 2026-08-30:**" not in merge_action_plan
    assert merge_action_plan.count(
        "**Owner multiplicity amendment, 2026-08-30 — affects all four strategy lanes:**"
    ) == 1

    # TPR-CR14-003: the merge blob above is immutable, but the working Action
    # Plan is a shared document that is frozen on lanes (parallel workflow
    # section 2; owner direction 2026-09-04, record section 39).  Section 42
    # restored it to the merge result.  Pin only what must stay true across a
    # later owner-coordinated amendment: one target block, no revived stale
    # block, and no role-pending sentence that the next round falsifies.
    action_plan = _doc("ACTION_PLAN_2026-08-20.md")
    assert action_plan.count("**Current bounded status,") == 1
    assert "**Current bounded status, 2026-08-30:**" not in action_plan
    for name, surface in (
        ("Action Plan target block", _action_current()),
        ("Action Plan target row", _action_tpr_row()),
    ):
        normalized_surface = " ".join(surface.lower().split())
        for phrase in PER_ROUND_PENDING_PHRASES:
            assert phrase not in normalized_surface, (
                f"{name} carries per-round role state: {phrase!r}"
            )

    for text in (*merge_blobs.values(), action_plan, _doc("SESSION_HANDOFF.md")):
        assert not re.search(r"^(?:<<<<<<< |=======|>>>>>>> )", text, flags=re.MULTILINE)


def test_out_of_lane_current_disposition_index_matches_integration_closures() -> None:
    """TPR-CCR13-001: historical rows cannot masquerade as current routing."""
    section = _record_section("## 9. Out-of-lane findings ledger")
    index_heading = (
        "### Current disposition index (successor qualification, 2026-10-02)"
    )
    assert section.count(index_heading) == 1
    index = section.partition(index_heading)[2]
    dispositions = {
        match.group(1): match.group(2).lower()
        for line in index.splitlines()
        if (
            match := re.fullmatch(
                r"\| `(TPR-OOL-[0-9]{3}(?:-R[0-9]+)?)` \| \*\*(Open|Closed)\*\* \|.*",
                line,
            )
        )
    }
    assert set(dispositions) == {
        "TPR-OOL-001",
        "TPR-OOL-002",
        "TPR-OOL-003",
        "TPR-OOL-004",
        "TPR-OOL-005",
        "TPR-OOL-006",
        "TPR-OOL-007",
        "TPR-OOL-008",
        "TPR-OOL-009",
        "TPR-OOL-010",
        "TPR-OOL-011",
        "TPR-OOL-012",
        "TPR-OOL-013",
        "TPR-OOL-014",
        "TPR-OOL-015",
        "TPR-OOL-016",
        "TPR-OOL-017",
        "TPR-OOL-018",
    }
    assert {identifier for identifier, status in dispositions.items() if status == "closed"} == {
        "TPR-OOL-001",
        "TPR-OOL-002",
        "TPR-OOL-003",
        "TPR-OOL-004",
        "TPR-OOL-005",
        "TPR-OOL-006",
        "TPR-OOL-007",
        "TPR-OOL-008",
        "TPR-OOL-009",
        "TPR-OOL-010",
    }


def test_out_of_lane_ledger_has_unique_well_formed_ids() -> None:
    """TPR-CCR8-003/004: keep the owner-routing ledger unambiguous."""
    section = _record_section("## 9. Out-of-lane findings ledger")
    details = section.partition(
        "### Current disposition index (successor qualification, 2026-10-02)"
    )[0]
    rows = [
        line
        for line in details.splitlines()
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
        # SESSION_HANDOFF.md is deliberately absent because it is frozen for
        # this lane. The Action Plan may receive owner-coordinated concise
        # status amendments, but remains outside the per-round pointer set.
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


def test_current_claude_review_records_the_exact_range_and_owner_decisions() -> None:
    """TPR-CR14: pin this round's review section and the decisions it records.

    The reviewed range is one merge wide and 627 commits deep, so the section
    dispositions the five first-parent commits individually and the inherited
    commits by provenance class.  Both the order and the totals are derived
    from Git here, not restated, so the section cannot drift from the graph.
    """
    section = _record_section(
        "## 42. Claude independent review of the counter-review, main merge, "
        "and synchronization"
    )
    assert "Historical review report." in section
    assert "Section 43 supersedes" in section
    assert CURRENT_CLAUDE_REVIEWED_CODEX_RANGE in section
    ordered_commits = tuple(
        re.search(r"`([0-9a-f]{40})`", line).group(1)
        for line in section.splitlines()
        if re.match(r"[|] Codex commit [0-9]+ [|]", line)
    )
    assert ordered_commits == CURRENT_CLAUDE_REVIEWED_FIRST_PARENT_COMMITS
    assert ordered_commits == tuple(
        _git_lines(
            "rev-list",
            "--first-parent",
            "--reverse",
            CURRENT_CLAUDE_REVIEWED_CODEX_RANGE,
        )
    )

    reachable = len(_git_lines("rev-list", CURRENT_CLAUDE_REVIEWED_CODEX_RANGE))
    inherited = reachable - len(ordered_commits)
    classes = _bounded(
        section,
        "### 42.3 Merge-inherited commits by provenance class",
        "### 42.4 P0-P3 ledger",
        "section 42 inherited classes",
    )
    class_counts = [
        int(match.group(1))
        for line in classes.splitlines()
        if (
            match := re.match(
                r"\| [^|]+ \| ([0-9]+) \| \*\*(?:accepted|rejected)\*\*", line
            )
        )
    ]
    assert class_counts and sum(class_counts) == inherited
    assert f"**{inherited}**" in classes

    assert "Cumulative disposition: accepted after correction" in section
    decisions = _bounded(
        section,
        "### 42.6 Owner direction and decisions taken under pre-authorization",
        "### 42.7 Milestone and authority decision",
        "section 42 owner decisions",
    )
    decision_rows = [
        match.group(1)
        for line in decisions.splitlines()
        if (match := re.match(r"\| `(TPR-OD-[0-9]{3})` \|", line))
    ]
    assert tuple(decision_rows) == CURRENT_OWNER_DECISION_IDS
    authority = _bounded(
        section,
        "### 42.7 Milestone and authority decision",
        "### 42.8 Validation",
        "section 42 authority decision",
    )
    normalized_authority = " ".join(authority.split())
    assert "TPR-D0" in normalized_authority
    assert "outcome-free" in normalized_authority
    for forbidden in (
        "QuantConnect job",
        "provider request",
        "broker",
        "paper",
        "live",
        "trading authority",
    ):
        assert forbidden in normalized_authority, (
            f"the authority decision must name what stays closed: {forbidden}"
        )


def test_current_counterreview_records_all_claude_commits_without_new_authority() -> None:
    section = _record_section("## 43. Codex counter-review of Claude section 42")
    assert CURRENT_COUNTERREVIEWED_CLAUDE_RANGE in section
    table = _bounded(
        section,
        "### 43.2 Every incoming commit disposition",
        "### 43.3 P0-P3 ledger",
        "section 43 commit dispositions",
    )
    rows = [
        (match.group(1), match.group(2).lower())
        for line in table.splitlines()
        if (match := re.match(
            r"\| `([0-9a-f]{40})` \| \*\*([a-z ]+)\*\* \|", line, re.IGNORECASE
        ))
    ]
    assert tuple(commit for commit, _ in rows) == CURRENT_COUNTERREVIEWED_CLAUDE_COMMITS
    assert tuple(commit for commit, _ in rows) == tuple(
        _git_lines("rev-list", "--reverse", CURRENT_COUNTERREVIEWED_CLAUDE_RANGE)
    )
    assert {disposition for _, disposition in rows} == {"accepted after correction"}
    assert "Cumulative disposition: accepted after correction" in section
    authority = " ".join(_bounded(
        section,
        "### 43.5 Milestone, gates, and next authorized action",
        "### 43.6 Validation and exclusions",
        "section 43 gate decision",
    ).split())
    for required in (
        "No next implementation milestone is authorized",
        "TPR-D0 is not authorized",
        "retained licensed rows",
        "review alone cannot authorize",
        "TPR-OOL-011",
        "rollback",
        "parent custody",
        "adversarial matrix",
        "TPR-1",
        "TPR-2",
        "TPR-0B",
        "monitor remains paused",
    ):
        assert required in authority


def test_owner_scoped_remediation_does_not_adopt_trust_or_source_drafts() -> None:
    """A shared-test exception and decision draft cannot mint adjacent authority."""
    section = _record_section("## 44. Owner-scoped shared remediation and decision drafts")
    normalized = " ".join(section.split())
    assert "37598fa5b686a14e906c92dcea4c17b9d9b933b7" in normalized
    assert "start implementing" in normalized
    assert "Implementation candidate; independent review pending" in normalized
    scope = _bounded(
        section,
        "### 44.1 Owner direction and exact scope",
        "### 44.2 Shared correction and acceptance plan",
        "section 44 owner scope",
    )
    assert "tests/conftest.py" in scope
    assert "tests/test_runtime_stop_leak_guard.py" in scope
    assert "No cross-lane synchronization is performed" in " ".join(scope.split())
    trust = _bounded(
        section,
        "### 44.3 Trust decisions - DRAFT, not selected",
        "### 44.4 Source evidence checklist - DRAFT, zero access",
        "section 44 trust draft",
    )
    trust_rows = re.findall(r"\| `(TPR-TR-D[1-4])` \| ([A-Z]+) \|", trust)
    assert trust_rows == [(f"TPR-TR-D{i}", "PENDING") for i in range(1, 5)]
    assert "No trust policy is adopted by this draft" in " ".join(trust.split())
    source = _bounded(
        section,
        "### 44.4 Source evidence checklist - DRAFT, zero access",
        "### 44.5 Remaining gates and serialized review",
        "section 44 source checklist",
    )
    source_rows = re.findall(r"\| `(TPR-SRC-E[1-8])` \| ([A-Z]+) \|", source)
    assert source_rows == [(f"TPR-SRC-E{i}", "UNESTABLISHED") for i in range(1, 9)]
    assert "No source access is admitted by this checklist" in " ".join(source.split())
    gates = " ".join(_bounded(
        section,
        "### 44.5 Remaining gates and serialized review",
        "### 44.6 Validation and handoff",
        "section 44 gates",
    ).split())
    for required in (
        "TPR-OOL-011 remains open pending independent review",
        "prior section-40 rejection is not waived",
        "TPR-D0 is not authorized",
        "TPR-TR0-I remains incomplete",
        "TPR-1 remains blocked",
        "TPR-0B still requires reviewed TPR-1/TPR-2 manifests",
        "monitor remains paused",
    ):
        assert required in gates


def test_section_45_review_records_the_exact_range_and_grants_nothing() -> None:
    """TPR-CR15: pin this review, its open finding, and its owner routing.

    The section accepts a shared-test correction and two drafts and must not
    turn either the withdrawn section-42 proposals or its own recommendations
    into authority.
    """
    section = _record_section(
        "## 45. Claude independent review of the counter-review and "
        "owner-scoped remediation"
    )
    assert SECTION45_REVIEWED_CODEX_RANGE in section
    ordered_commits = tuple(
        re.search(r"`([0-9a-f]{40})`", line).group(1)
        for line in section.splitlines()
        if re.match(r"[|] Codex commit [0-9]+ [|]", line)
    )
    assert ordered_commits == SECTION45_REVIEWED_CODEX_COMMITS
    assert ordered_commits == tuple(
        _git_lines("rev-list", "--reverse", SECTION45_REVIEWED_CODEX_RANGE)
    )
    dispositions = _bounded(
        section,
        "### 45.2 Commit-by-commit dispositions",
        "### 45.3 P0-P3 ledger",
        "section 45 dispositions",
    )
    rows = [
        (match.group(1), match.group(2).lower())
        for line in dispositions.splitlines()
        if (
            match := re.match(
                r"\| `([0-9a-f]{40})` \| \*\*([A-Za-z ]+)\*\* \|", line
            )
        )
    ]
    assert tuple(commit for commit, _ in rows) == SECTION45_REVIEWED_CODEX_COMMITS
    assert {disposition for _, disposition in rows} <= {
        "accepted",
        "accepted after correction",
    }
    assert "Cumulative disposition: accepted after correction" in section

    ledger = _bounded(
        section,
        "### 45.3 P0-P3 ledger",
        "### 45.4 Shared correction: status and what remains",
        "section 45 ledger",
    )
    statuses = dict(
        re.findall(r"^\| `(TPR-CR15-[0-9]{3})` \| P[0-3] \| \*\*([^*]+)\*\*", ledger, re.M)
    )
    assert statuses == {
        "TPR-CR15-001": "Closed by scoped test correction",
        "TPR-CR15-002": "Closed by qualification",
        "TPR-CR15-003": "Closed by qualification",
        "TPR-CR15-004": "Closed by correction",
    }

    owner = _bounded(
        section,
        "### 45.6 Two owner instructions that conflict",
        "### 45.7 Assessment of the two drafts",
        "section 45 owner inputs",
    )
    owner_rows = tuple(
        match.group(1)
        for line in owner.splitlines()
        if (match := re.match(r"\| `(TPR-OWN-[0-9])` \|", line))
    )
    assert owner_rows == SECTION45_OWNER_INPUT_IDS
    normalized_owner = " ".join(owner.split())
    assert "does not re-assert the section-42 decisions" in normalized_owner
    assert "remain proposals" in normalized_owner

    authority = " ".join(section.partition("### 45.9 Milestone and authority decision")[2].split())
    for required in (
        "No next implementation milestone is authorized",
        "TPR-D0 is not authorized",
        "Codex next counter-reviews section 45",
        "retained licensed row",
        "provider request",
        "QuantConnect project",
        "until the owner has answered",
    ):
        assert required in authority, required


def test_section_46_reviews_every_claude_commit_and_pins_owner_scope() -> None:
    section = _record_section("## 46. Codex counter-review and bounded owner decisions")
    assert SECTION46_CLAUDE_RANGE in section
    table = _bounded(section, "### 46.1 Exact range and dispositions", "### 46.2 Owner decisions", "section 46 dispositions")
    commits = tuple(re.findall(r"^\| `([0-9a-f]{40})` \|", table, re.M))
    assert commits == SECTION46_CLAUDE_COMMITS
    assert commits == tuple(_git_lines("rev-list", "--reverse", SECTION46_CLAUDE_RANGE))
    assert "Cumulative disposition: accepted after correction" in section
    owner = _bounded(section, "### 46.2 Owner decisions", "### 46.3 P0-P3 ledger", "section 46 owner scope")
    assert tuple(re.findall(r"^\| `(TPR-OWN-[1-5])` \|", owner, re.M)) == SECTION45_OWNER_INPUT_IDS
    for required in ("OK, do 1 2 3", "51954daea8432136b9c99fb4d5088e0c672664e9384475635110dd33e08a2e85",
                     "596 pages", "587,046 rows", "415,780,520 bytes", "600-second cooperative",
                     "2026-10-12", "not vendor-attested", "no new capture", "no outcome",
                     "no QC", "no trading", "parked", "not an autouse"):
        assert required.lower() in owner.lower(), required
    assert "13 of 17 mutations" in _record_section("## 9. Out-of-lane findings ledger")
    assert "9 of 13 mutations" not in _record_section("## 9. Out-of-lane findings ledger")


def test_section_8_carries_one_current_role_and_no_stale_commit() -> None:
    """TPR-CR16-002: refuse stale identities and duplicate recognized routing.

    The recognized role grammar is Claude/Codex, optional has/independently,
    and reviewed/counter-reviewed; next actions use next reviews/counter-reviews.
    This is an explicit grammar, not an arbitrary-prose classifier. Exactly
    one recognized role and next-action statement must occur in the current
    block. Lowercase 7-12 or 40-hex commit identities, quoted or unquoted,
    must be range endpoints or known stable/branch-relation identities.
    Short ranges cannot duplicate the current block's single full range.
    """
    current = _current_qualification(_record_section("## 8. Exact next step"))
    normalized = " ".join(current.split())
    roles = re.findall(SECTION8_ROLE_STATEMENT, normalized)
    assert len(roles) == 1, f"section 8 must state one current role: {roles}"
    next_actions = re.findall(SECTION8_NEXT_ACTION_STATEMENT, normalized)
    assert len(next_actions) == 1, f"section 8 must name one next action: {next_actions}"
    ranges = re.findall(r"`([0-9a-f]{40})\.{2}([0-9a-f]{40})`", normalized)
    assert len(ranges) == 1, ranges
    allowed = {*ranges[0], *SECTION8_STABLE_COMMITS}
    full = set(re.findall(r"(?<![0-9a-f])([0-9a-f]{40})(?![0-9a-f])", normalized))
    assert full <= allowed, f"section 8 names a stale commit: {sorted(full - allowed)}"
    short = set(re.findall(r"\b([0-9a-f]{7,12})\b", normalized))
    stale_short = {
        token for token in short
        if token not in SECTION8_BRANCH_RELATION_COMMITS
        and not any(identity.startswith(token) for identity in allowed)
    }
    assert not stale_short, f"section 8 names a stale commit: {sorted(stale_short)}"
    assert re.findall(r"\b[0-9a-f]{7,12}\.{2}[0-9a-f]{7,12}\b", normalized) == [], (
        "section 8 names its range in full; a short range there is stale"
    )


@pytest.mark.parametrize(
    ("stale_sentence", "failure"),
    [
        (
            "Earlier pending review d54ce1b2..ea97bd4f.",
            "stale commit",
        ),
        (
            "Codex independently counter-reviewed the prior snapshot.",
            "one current role",
        ),
    ],
)
def test_section_8_guard_refuses_unquoted_or_alternate_stale_claims(
    monkeypatch, stale_sentence: str, failure: str,
) -> None:
    """Exercise the actual rule after proving the unmodified pointer is valid."""
    test_section_8_carries_one_current_role_and_no_stale_commit()
    original_section = _record_section
    section = original_section("## 8. Exact next step")
    mutated = section.replace(
        "\n### Historical progression",
        f"\n{stale_sentence}\n\n### Historical progression",
        1,
    )
    assert mutated != section
    monkeypatch.setitem(
        globals(), "_record_section",
        lambda heading: mutated if heading == "## 8. Exact next step"
        else original_section(heading),
    )
    with pytest.raises(AssertionError, match=failure):
        test_section_8_carries_one_current_role_and_no_stale_commit()


def test_claude_review_of_the_d0_round_is_exact() -> None:
    """TPR-CR16-001/002: pin this Claude round's exact range and commits."""
    section = _record_section(
        "## 48. Claude independent review of the Codex D0 round"
    )
    assert SECTION48_CODEX_RANGE in section
    commits = tuple(
        re.search(r"`([0-9a-f]{40})`", line).group(1)
        for line in section.splitlines()
        if re.match(r"[|] Codex commit [0-9]+ [|]", line)
    )
    assert commits == SECTION48_CODEX_COMMITS
    assert "Cumulative disposition: accepted after correction" in section
    assert "TPR-D1 is not authorized" in section


def test_section_49_counterreviews_both_claude_commits_after_correction() -> None:
    """The new owner scope starts only after both incoming commits are accepted."""
    section = _record_section("## 49.")
    assert SECTION49_CLAUDE_RANGE in section
    table = _bounded(section, "### 49.1", "### 49.2", "section 49 dispositions")
    rows = tuple(
        (match.group(1), match.group(2).strip("*").lower())
        for line in table.splitlines()
        if (match := re.match(r"\| `([0-9a-f]{40})` \| ([^|]+?) \|", line))
    )
    assert rows == tuple(
        (commit, "accepted after correction") for commit in SECTION49_CLAUDE_COMMITS
    )
    assert tuple(commit for commit, _ in rows) == tuple(
        _git_lines("rev-list", "--reverse", SECTION49_CLAUDE_RANGE)
    )
    assert "Cumulative disposition: accepted after correction" in section


def test_section_50_preserves_exact_fixture_only_owner_scope() -> None:
    """Freeze this development authorization, not a new retained-data permit."""
    section = _record_section("## 50.")
    normalized = " ".join(re.sub(r"(?m)^\s*> ?", "", section).split())
    assert SECTION50_OWNER_SCOPE in normalized
    assert SECTION50_D0_REPORT_SHA256 in section
    assert "D0's one completed audit is not renewed" in normalized
    assert "No additional data access is authorized" in normalized
    assert "TPR-D2 is not authorized" in normalized
    assert "Fixture-only TPR-D1 candidate awaits independent Claude review" in normalized
    boundary = _bounded(
        section,
        "<!-- TPR-D1-FIXTURE-SCOPE:START -->",
        "<!-- TPR-D1-FIXTURE-SCOPE:END -->",
        "section 50 fixture-only scope",
    )
    rows = tuple(re.findall(r"^\| ([^|]+) \| ([^|]+) \|$", boundary, re.M))
    assert rows == (("Boundary", "Scope"), *SECTION50_SCOPE_BOUNDARIES.items()), (
        "the closed fixture-only boundary cannot add, remove, duplicate or grant a scope"
    )


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        (
            "| Additional data access | Forbidden |",
            "| Additional data access | Permitted |",
        ),
        (
            "| Retained-row processing | Forbidden |",
            "| Retained-row processing | Permitted |",
        ),
        (
            "| TPR-D2 | Not authorized |",
            "| TPR-D2 | Authorized |",
        ),
        (
            "| Review handoff | Stop for independent Claude review |",
            "| Review handoff | Stop for independent Claude review |\n"
            "| New provider capture | Permitted |",
        ),
        (
            "| QuantConnect | Forbidden |",
            "| QuantConnect | Forbidden |\n| QuantConnect | Permitted |",
        ),
        (
            "| Provider requests | Forbidden |",
            "",
        ),
    ],
)
def test_section_50_scope_guard_rejects_added_or_widened_permissions(
    monkeypatch, original: str, replacement: str,
) -> None:
    """Prove the real guard is sensitive after its unchanged record passes."""
    test_section_50_preserves_exact_fixture_only_owner_scope()
    original_section = _record_section
    section = original_section("## 50.")
    assert section.count(original) == 1
    mutated = section.replace(original, replacement, 1)
    monkeypatch.setitem(
        globals(), "_record_section",
        lambda heading: mutated if heading == "## 50."
        else original_section(heading),
    )
    with pytest.raises(AssertionError, match="closed fixture-only boundary"):
        test_section_50_preserves_exact_fixture_only_owner_scope()


def test_section_51_review_records_the_exact_range_and_grants_nothing() -> None:
    """Pin exact dispositions and reject two recognized affirmative grants.

    The grant rule recognizes affirmative TPR-D2/Real-row D1 followed by is
    authorized at a sentence start, case-insensitively. Embedded negative
    clauses are not grants. This is not an arbitrary-prose classifier.
    """
    section = _record_section(
        "## 51. Claude independent review of the counter-review and the "
        "fixture-only TPR-D1 candidate"
    )
    assert SECTION51_CODEX_RANGE in section
    ordered_commits = tuple(
        re.search(r"`([0-9a-f]{40})`", line).group(1)
        for line in section.splitlines()
        if re.match(r"[|] Codex commit [0-9]+ [|]", line)
    )
    assert ordered_commits == SECTION51_CODEX_COMMITS
    assert ordered_commits == tuple(
        _git_lines("rev-list", "--reverse", SECTION51_CODEX_RANGE)
    )
    dispositions = _bounded(
        section,
        "### 51.2 Commit-by-commit dispositions",
        "### 51.3 P0-P3 ledger",
        "section 51 dispositions",
    )
    rows = [
        (match.group(1), match.group(2).lower())
        for line in dispositions.splitlines()
        if (
            match := re.match(
                r"\| `([0-9a-f]{40})` \| \*\*([A-Za-z ]+)\*\* \|", line
            )
        )
    ]
    assert tuple(rows) == tuple(zip(SECTION51_CODEX_COMMITS, SECTION51_CODEX_DISPOSITIONS)), (
        "exact section 51 dispositions must retain every correction qualification"
    )
    assert "Cumulative disposition: accepted after correction" in section
    ledger = _bounded(
        section,
        "### 51.3 P0-P3 ledger",
        "### 51.4 Mutation evidence",
        "section 51 ledger",
    )
    statuses = dict(
        re.findall(r"^\| `(TPR-CR17-[0-9]{3})` \| P[0-3] \| \*\*([^*]+)\*\*", ledger, re.M)
    )
    assert statuses == {
        "TPR-CR17-001": "Closed by correction",
        "TPR-CR17-002": "Closed by correction",
        "TPR-CR17-003": "Closed by qualification",
    }
    authority = " ".join(_bounded(
        section, "### 51.6 Milestone and authority decision", "### 51.7 Validation",
        "section 51 authority",
    ).split())
    assert re.search(
        r"(?:^|[.!?])\s*(?:TPR-D2|real-row D1)\s+is\s+authorized\b", authority, re.I,
    ) is None, "contradictory section 51 authority grants a prohibited next scope"
    for required in (
        "fixture-only TPR-D1 candidate is accepted",
        "TPR-D2 is not authorized",
        "Codex next counter-reviews section 51",
        "retained row",
        "provider request",
        "QuantConnect",
        "trading authority",
    ):
        assert required in authority, required


@pytest.mark.parametrize(
    "commit",
    [
        "7baddbbc303e76ef91850b3e4a53cfe4030f4fea",
        "01e703906df838fd9cbb91a2d1fd03ce7d18f288",
    ],
)
def test_section_51_guard_refuses_disposition_drift(monkeypatch, commit: str) -> None:
    """Exercise the actual review pin after its unchanged record passes."""
    test_section_51_review_records_the_exact_range_and_grants_nothing()
    original_section = _record_section
    section = original_section("## 51.")
    original = f"| `{commit}` | **Accepted after correction** |"
    assert section.count(original) == 1
    mutated = section.replace(original, f"| `{commit}` | **Accepted** |", 1)
    monkeypatch.setitem(
        globals(), "_record_section",
        lambda heading: mutated if heading.startswith("## 51.")
        else original_section(heading),
    )
    with pytest.raises(AssertionError, match="exact section 51 dispositions"):
        test_section_51_review_records_the_exact_range_and_grants_nothing()


@pytest.mark.parametrize(
    "added_grant",
    ["TPR-D2 is authorized.", "Real-row D1 is authorized."],
)
def test_section_51_guard_refuses_contradictory_authority(
    monkeypatch, added_grant: str,
) -> None:
    """A recognized affirmative grant cannot coexist with the required refusal."""
    test_section_51_review_records_the_exact_range_and_grants_nothing()
    original_section = _record_section
    section = original_section("## 51.")
    mutated = section.replace(
        "\n### 51.7 Validation",
        f"\n{added_grant}\n\n### 51.7 Validation",
        1,
    )
    assert mutated != section
    monkeypatch.setitem(
        globals(), "_record_section",
        lambda heading: mutated if heading.startswith("## 51.")
        else original_section(heading),
    )
    with pytest.raises(AssertionError, match="contradictory section 51 authority"):
        test_section_51_review_records_the_exact_range_and_grants_nothing()


def test_section_52_counterreviews_every_incoming_commit_and_stops() -> None:
    """The completed counter-review adds publication/monitoring, not development."""
    section = _record_section("## 52.")
    assert SECTION52_CLAUDE_RANGE in section
    normalized = " ".join(re.sub(r"(?m)^\s*> ?", "", section).split())
    assert SECTION52_OWNER_REVIEW_SCOPE in normalized
    assert SECTION52_OWNER_HANDOFF_SCOPE in normalized
    table = _bounded(section, "### 52.2", "### 52.3", "section 52 dispositions")
    rows = tuple(
        (match.group(1), match.group(2).strip("*").lower())
        for line in table.splitlines()
        if (match := re.match(r"\| `([0-9a-f]{40})` \| ([^|]+?) \|", line))
    )
    assert rows == tuple(
        (commit, "accepted after correction") for commit in SECTION52_CLAUDE_COMMITS
    )
    assert tuple(commit for commit, _ in rows) == tuple(
        _git_lines("rev-list", "--reverse", SECTION52_CLAUDE_RANGE)
    )
    assert "Cumulative disposition: accepted after correction" in section
    boundary = _bounded(
        section,
        "<!-- TPR-CCR18-SCOPE:START -->",
        "<!-- TPR-CCR18-SCOPE:END -->",
        "section 52 counter-review scope",
    )
    scope_rows = tuple(re.findall(r"^\| ([^|]+) \| ([^|]+) \|$", boundary, re.M))
    assert scope_rows == (("Boundary", "Scope"), *SECTION52_SCOPE_BOUNDARIES.items()), (
        "the closed counter-review boundary cannot add, remove, duplicate or grant a scope"
    )


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        (
            "| Next milestone | Not authorized |",
            "| Next milestone | Authorized |",
        ),
        (
            "| Additional data access | Forbidden |",
            "| Additional data access | Permitted |",
        ),
    ],
)
def test_section_52_scope_guard_rejects_added_authority(
    monkeypatch, original: str, replacement: str,
) -> None:
    """Run the actual closed guard after proving the unmodified scope is valid."""
    test_section_52_counterreviews_every_incoming_commit_and_stops()
    original_section = _record_section
    section = original_section("## 52.")
    assert section.count(original) == 1
    mutated = section.replace(original, replacement, 1)
    monkeypatch.setitem(
        globals(), "_record_section",
        lambda heading: mutated if heading.startswith("## 52.")
        else original_section(heading),
    )
    with pytest.raises(AssertionError, match="closed counter-review boundary"):
        test_section_52_counterreviews_every_incoming_commit_and_stops()
