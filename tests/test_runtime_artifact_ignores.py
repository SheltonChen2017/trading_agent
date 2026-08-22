"""AP-2 (ACTION_PLAN 2026-08-02): runtime artifact paths must be ignored.

``data/runtime_identity.py`` refuses evidence capture when ``git
status --porcelain --untracked-files=all`` reports ANYTHING, so every path
the documented operational commands write inside the repository must be
git-ignored -- otherwise the first scheduled run dirties the worktree and
the evidence cadence silently stops. The paths below are the ones the
operations runbook and CLI documentation actually name (supervisor/shadow
configs and outputs, model bundles, experiment datasets/outputs, review
attestations, licensed Databento snapshots).

This is a repository-configuration invariant, so the test asks the real
``git check-ignore`` rather than parsing .gitignore itself.

Run with: python -m pytest tests/test_runtime_artifact_ignores.py
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# One representative file per documented runtime write location.
RUNTIME_ARTIFACT_PATHS = [
    "artifacts/shadow.json",
    "artifacts/model/model.joblib",
    "artifacts/ml-shadow-monitoring.json",
    "artifacts/ml-evidence-supervisor.json",
    "artifacts/ml-shadow-status.json",
    "artifacts/datasets/volatility-v1/dataset.csv.gz",
    "artifacts/experiments/volatility-v1/report.json",
    "artifacts/reviews/spec-review-attestation.json",
    "artifacts/databento/manifest.json",
    "data/swap_disable_result_20260810.json",
    "data/swap_enable_result_20260810.json",
]


def test_every_documented_runtime_artifact_path_is_git_ignored():
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("requires git and the repository checkout")
    # Bytes mode on purpose: text=True would translate the piped "\n" to
    # "\r\n" on Windows, and git would then look up every path except the
    # last with a trailing carriage return -- silently matching nothing.
    completed = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        input="\n".join(RUNTIME_ARTIFACT_PATHS).encode("utf-8"),
        capture_output=True,
        cwd=REPO_ROOT,
    )
    ignored = set(completed.stdout.decode("utf-8").splitlines())
    not_ignored = [p for p in RUNTIME_ARTIFACT_PATHS if p not in ignored]
    assert not not_ignored, (
        "these runtime artifact paths are NOT git-ignored; a scheduled run "
        "writing them would dirty the worktree and stop evidence capture: "
        f"{not_ignored}"
    )
