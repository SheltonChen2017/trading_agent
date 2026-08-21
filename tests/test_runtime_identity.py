"""One strict definition of runtime identity, exercised against real git.

These use a throwaway repository rather than mocks: the defect being pinned
was a difference between two real git commands, so a mocked subprocess would
have reproduced the bug rather than caught it.
"""
from __future__ import annotations

import subprocess

import pytest

from assistant.runtime_identity import RuntimeIdentityError, current_commit


def _git(repository, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture()
def repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "--quiet")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", "tracked.py")
    _git(root, "commit", "--quiet", "-m", "initial")
    return root


def test_clean_repository_returns_the_head_commit(repository):
    commit = current_commit(require_clean=True, repository=repository)
    assert commit == _git(repository, "rev-parse", "HEAD")
    assert len(commit) in (40, 64)


def test_untracked_file_makes_the_tree_unattributable(repository):
    """The exact blind spot this module exists to close.

    ``git diff --quiet HEAD --`` -- what three of the four former copies
    used -- reports clean here, so a shadow run could stamp a commit while
    importing a module that commit does not contain.
    """
    (repository / "untracked.py").write_text("SNEAKY = True\n", encoding="utf-8")

    # Establish that the weaker check really does miss it, so this test
    # fails for the right reason rather than by coincidence.
    weaker = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--"], cwd=repository, check=False
    )
    assert weaker.returncode == 0, "premise broken: git diff should report clean"

    with pytest.raises(RuntimeIdentityError, match="untracked"):
        current_commit(require_clean=True, repository=repository)


def test_git_config_cannot_hide_an_untracked_runtime_file(repository):
    """Repository/user config must not weaken the evidence boundary."""
    _git(repository, "config", "status.showUntrackedFiles", "no")
    (repository / "untracked.py").write_text("SNEAKY = True\n", encoding="utf-8")

    # Establish the configuration-dependent blind spot before checking the
    # production helper. An explicit command-line policy must override it.
    assert _git(repository, "status", "--porcelain") == ""

    with pytest.raises(RuntimeIdentityError, match="untracked"):
        current_commit(require_clean=True, repository=repository)


def test_git_ignore_cannot_hide_importable_runtime_source(repository):
    source = repository / "ml"
    source.mkdir()
    (source / "ignored.py").write_text("SNEAKY = True\n", encoding="utf-8")
    exclude = repository / ".git" / "info" / "exclude"
    exclude.write_text("ml/ignored.py\n", encoding="utf-8")

    assert _git(repository, "status", "--porcelain", "--untracked-files=all") == ""
    with pytest.raises(RuntimeIdentityError, match="ignored Python source"):
        current_commit(require_clean=True, repository=repository)


def test_git_ignore_cannot_hide_research_runtime_source(repository):
    source = repository / "research"
    source.mkdir()
    (source / "ignored.py").write_text("SNEAKY = True\n", encoding="utf-8")
    exclude = repository / ".git" / "info" / "exclude"
    exclude.write_text("research/ignored.py\n", encoding="utf-8")

    assert _git(repository, "status", "--porcelain", "--untracked-files=all") == ""
    with pytest.raises(RuntimeIdentityError, match="ignored Python source"):
        current_commit(require_clean=True, repository=repository)


def test_modified_tracked_file_is_also_refused(repository):
    (repository / "tracked.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(RuntimeIdentityError):
        current_commit(require_clean=True, repository=repository)


def test_require_clean_false_still_reports_the_commit(repository):
    (repository / "untracked.py").write_text("SNEAKY = True\n", encoding="utf-8")
    commit = current_commit(require_clean=False, repository=repository)
    assert commit == _git(repository, "rev-parse", "HEAD")


def test_expected_commit_is_an_assertion_not_a_caller_override(repository):
    actual = _git(repository, "rev-parse", "HEAD")
    assert current_commit(
        require_clean=True,
        repository=repository,
        expected_commit=actual,
    ) == actual

    other = ("0" if actual[0] != "0" else "1") + actual[1:]
    with pytest.raises(RuntimeIdentityError, match="does not match"):
        current_commit(
            require_clean=True,
            repository=repository,
            expected_commit=other,
        )


def test_a_directory_that_is_not_a_repository_fails_closed(tmp_path, monkeypatch):
    # GIT_CEILING_DIRECTORIES stops git's upward .git discovery at tmp_path,
    # so this test means the same thing regardless of where pytest's basetemp
    # lives. Without it, running with --basetemp inside this repository (the
    # documented validation command pattern does exactly that) put
    # "not-a-repo" INSIDE the repo: on a clean worktree git found the real
    # repository and the test failed; on a dirty worktree it "passed" for the
    # wrong reason (the dirtiness refusal, not the non-repo refusal). Found
    # 2026-08-03 when a clean-tree full run first exposed the trap.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    with pytest.raises(RuntimeIdentityError):
        current_commit(require_clean=True, repository=outside)


def test_every_script_uses_the_shared_definition():
    """No script may reimplement this; the four copies had drifted apart."""
    import ast
    from pathlib import Path

    offenders = []
    for path in (Path(__file__).resolve().parent.parent / "scripts").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            name = getattr(function, "attr", None) or getattr(function, "id", None)
            if name != "run" or not node.args:
                continue
            first = node.args[0]
            if not isinstance(first, ast.List) or not first.elts:
                continue
            head = first.elts[0]
            rest = [
                element.value
                for element in first.elts[1:]
                if isinstance(element, ast.Constant)
            ]
            if (
                isinstance(head, ast.Constant)
                and head.value == "git"
                and ("rev-parse" in rest or "status" in rest)
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        "scripts must call assistant.runtime_identity.current_commit() rather "
        f"than shelling out to git themselves: {offenders}"
    )
