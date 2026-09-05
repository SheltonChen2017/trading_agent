"""Shared exact-byte research files must carry Git EOL protection.

Content-addressed artifacts and byte-compared anchors are only as stable as
their checkout bytes.  On a Windows host with ``core.autocrlf=true`` an
unprotected text file is rewritten to CRLF on checkout, so it no longer
matches its committed blob or any digest recorded against it, while
``git status`` still reports the tree clean through the stat cache.  Four
lanes independently documented this class (TPR-OOL-008/-010, SI-SYNC-001,
Insider #27, Analyst #4) after each lane could protect only its own subtree.

The first guard asserts the resolved attribute, which prevents NEW CRLF
checkouts.  The second asserts the working-copy bytes actually match the
index blob: an attribute added after a file was checked out does not rewrite
the working copy, and ``git status`` keeps reporting the tree clean through
the stat cache, so a stale checkout carries the exact defect while the
attribute test stays green (observed on 2026-09-05 on a checkout of the
commit that added the attribute).  The failure message names the one-time
heal step; a plain ``git checkout -- <path>`` is a no-op on a stat-clean file.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Path -> the attribute state Git must resolve for it.
EXPECTED_ATTRIBUTES: dict[str, dict[str, str]] = {
    # Review-ready ML specs: exact JSON bytes, no conversion either way.
    "research/ml_specs/volatility-discovery-v1.json": {"text": "unset"},
    "research/ml_specs/volatility-discovery-v1.review-request.json": {
        "text": "unset"
    },
    # Shared research package root: byte-compared by lane anchors, so it is
    # normalized to LF in the index AND the working tree.
    "research/__init__.py": {"text": "set", "eol": "lf"},
}


def _resolved_attributes(path: str) -> dict[str, str]:
    completed = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", path],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    resolved: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        # format: <path>: <attribute>: <value>
        _, attribute, value = (part.strip() for part in line.rsplit(":", 2))
        resolved[attribute] = value
    return resolved


@pytest.mark.parametrize("path", sorted(EXPECTED_ATTRIBUTES))
def test_shared_research_file_carries_its_eol_protection(path: str) -> None:
    assert (ROOT / path).is_file(), f"{path} is missing; update this inventory"
    resolved = _resolved_attributes(path)
    for attribute, expected in EXPECTED_ATTRIBUTES[path].items():
        assert resolved.get(attribute) == expected, (
            f"{path}: Git resolves {attribute}={resolved.get(attribute)!r}, "
            f"expected {expected!r}; a CRLF checkout would silently break its "
            "committed-byte identity"
        )


@pytest.mark.parametrize("path", sorted(EXPECTED_ATTRIBUTES))
def test_shared_research_file_working_copy_matches_its_index_blob(path: str) -> None:
    """A stale CRLF checkout is the defect itself, not a harness quirk."""
    line = subprocess.run(
        ["git", "ls-files", "--eol", "--", path],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    # format: i/<index eol>  w/<worktree eol>  attr/<attrs>  <path>
    fields = dict(part.split("/", 1) for part in line.split()[:2])
    assert fields.get("i") is not None and fields.get("w") is not None, line
    if fields["i"] == "none":
        return  # empty blob: no line endings to compare
    assert fields["w"] == fields["i"], (
        f"{path}: working copy is {fields['w']} but the index blob is "
        f"{fields['i']}; the checkout predates its EOL attribute and its bytes "
        "no longer match any recorded digest. Heal this checkout once with: "
        f"rm {path} && git checkout -- {path}"
    )


def test_root_gitattributes_keeps_pdfs_binary() -> None:
    """TPR-OOL-001's owner-approved fix must not regress when this file grows."""
    resolved = subprocess.run(
        ["git", "check-attr", "binary", "diff", "--", "docs/example.pdf"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "binary: set" in resolved or "diff: unset" in resolved, resolved
